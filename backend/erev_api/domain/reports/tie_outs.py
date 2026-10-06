"""Built-in tie-outs of the disclosure reports and the population reads they share (04 table 10-T,
T-RPT-02 ``tie_out_results``; SCREENS_B RPT-R-04, RPT-R-08; ENGINE_SPEC_B §15.1, §15.2.1 to
§15.2.3; 03 REQ-RPT-003; BUILD_SPEC RPS-3, RPS-4).

A tie-out result is ``{code, result, expected, actual}``: ``result`` an E-98 literal, and
``expected`` and ``actual`` lists of API-S-Money, one per currency in code order. ``compared``
passes when every currency agrees. ``TO_ROLLFORWARD_EQ_GL`` is ``NOT_APPLICABLE`` without a trial
balance (SCREENS_B RPT-R-08).

The platform part of stage 15 reads persisted engine outputs (ENGINE_SPEC_B §15.1):

- ``read_from`` and ``latest_versions``: the version each contract is read from at the cutoff —
  the last ``contract_version`` of the book along the contract's chain of combination groups
  (04 T-CON-04 reading rule). [J] L6-3-Q-19: ``contract_version.known_at`` is the computation's
  record cutoff, the later of the application clock and the server transaction timestamp
  (``bundles.record_cutoff``, L3-1-Q-25), so a report reads versions by the same rule at its
  ``known_at``. Subledger and journal rows carry the application clock and are read by
  ``known_at`` itself.
- ``balances_at``: the labelled balances of each member contract and contracting entity at a period
  end (ENGINE_SPEC_B S15-R-07a, ``presented_at``), from the version's trace nodes
  ``<measure>:<contract>@<entity>:<period key>`` (T-ENG-03), looked up under the ENGINE'S subject
  key — ``contract_entity_subject_key``: the contract's external id and the entity code each
  CV-21-encoded, the one table every node-id lookup keys on (ENGINE_SPEC CV-21, CV-50). A period
  before the first node is 0, a period after the last node holds the last node's value. A measure
  without period nodes is one the engine does not publish per member contract (DG-KRN-EXP-01:
  every published T-CON-09 column has its node, zeros included — the current parts, measured per
  group, and ``accounts_receivable`` outside ``ENGINE`` mode stay at the T-CON-09 default 0): it
  takes the stored ``contract_version_balance`` column, which is the version's LATEST period — so
  a non-zero stored figure answers only a period at or after that latest period. Everything else
  is refused by NAME (``BalanceUnreadable``, rule ``S15-R-07a``; supervisor ruling R-16,
  2026-09-29): a member row whose subject carries no balance node in its version's trace, and a
  non-zero stored figure asked for an EARLIER period — one error per member, the whole read
  refused. The latest figure is never answered for an earlier period.
- ``journal_revenue``: Σ credit − debit of the ``REVENUE`` journal lines of the runs not cancelled
  and created by ``known_at`` (CTL-019, CTL-028, CTL-030). D-87 L6-3-Q-32: only runs of the POL-005
  posting mode (``je.posting_mode``) resolved for the entity and book count, because DB-16 lets
  ``GROSS`` and ``DELTA`` runs of one period coexist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final, Protocol
from uuid import UUID

from erev_engine.currencies import ISO_4217
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from sqlalchemy import (
    ColumnElement,
    Select,
    Text,
    and_,
    cast,
    false,
    func,
    literal,
    or_,
    select,
    tuple_,
    union,
    union_all,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from erev_api.clock import to_entity_date
from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    contract_version,
    contract_version_balance,
    customer,
    journal_batch,
    journal_line,
    journal_run,
    legal_entity,
    period,
)
from erev_api.domain.policies.registry_versions import primary_book
from erev_api.domain.reports.builders import ReportParams
from erev_api.explain import store
from erev_api.problems import Problem, ProblemError

TO_WATERFALL_EQ_JE_REVENUE: Final = "TO_WATERFALL_EQ_JE_REVENUE"
TO_ROLLFORWARD_EQ_GL: Final = "TO_ROLLFORWARD_EQ_GL"
TO_RPO_ROLLFORWARD_EQ_RPO: Final = "TO_RPO_ROLLFORWARD_EQ_RPO"
TO_DISAGGREGATION_EQ_JE_REVENUE: Final = "TO_DISAGGREGATION_EQ_JE_REVENUE"
TO_ROLLFORWARD_BALANCES: Final = "TO_ROLLFORWARD_BALANCES"
TO_BALANCES_EQ_ROLLFORWARD: Final = "TO_BALANCES_EQ_ROLLFORWARD"
# BUILD_SPEC RPS-12 (04 table 10-T): the tie-outs of RPT-32, RPT-33, RPT-35 and RPT-36.
TO_COST_ROLLFORWARD_BALANCES: Final = "TO_COST_ROLLFORWARD_BALANCES"
TO_BRIDGE_DRIVERS_EQ_DIFFERENCE: Final = "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE"
TO_IC_UNMATCHED_ZERO: Final = "TO_IC_UNMATCHED_ZERO"
TO_AGING_EQ_BALANCES: Final = "TO_AGING_EQ_BALANCES"
PASS: Final = "PASS"
FAIL: Final = "FAIL"
NOT_APPLICABLE: Final = "NOT_APPLICABLE"
REVENUE: Final = "REVENUE"
CANCELLED_RUN: Final = "cancelled"
# E-06 contract statuses whose versions enter the disclosures; drafts and non-contracts do not.
INCLUDED_STATUSES: Final = frozenset({"ACTIVE", "COMPLETED", "TERMINATED"})
# ENGINE_SPEC_B S15-R-12 rev 1.161 "groups activated in the period" (item RPT-RPO-ROLLFWD-1;
# supervisor ruling R-121 (g)): the events at whose effective date a contract enters the
# disclosures — it is activated, its criteria are met for the run's book (the event's payload
# names the book it admits), or its opening balance is established. The first included version of
# a contract counts from that date in the RPO report, its rollforward and RPT-11.
ENTRY_EVENTS: Final = frozenset(
    {"CONTRACT_ACTIVATED", "CONTRACT_CRITERIA_MET", "OPENING_BALANCE_ESTABLISHED"}
)
CRITERIA_MET: Final = "CONTRACT_CRITERIA_MET"
RULE_PARAMETERS: Final = "T-RPT-01"
UNKNOWN_PERIOD: Final = "Choose a period of the entity's calendar."
UNKNOWN_CONTRACT: Final = "No contract {value} in this workspace."
ZERO: Final = Decimal(0)
# ENGINE_SPEC_B S15-R-07a (R-16): a period balance is read from the version's member-balance nodes
# or refused by name — the rule id is the refusal's ``rule_id``.
RULE_PERIOD_BALANCE: Final = "S15-R-07a"
BALANCE_SUBJECT_UNTRACED: Final = (
    "Contract {external_id} in entity {entity_code}: the calc trace of contract version "
    "{version_id} holds no balance node under the subject key {subject}, so its balances at "
    "{period_key} cannot be read. Nothing is answered from the version's latest stored figures."
)
BALANCE_MEASURE_UNTRACED: Final = (
    "Contract {external_id} in entity {entity_code}: contract version {version_id} stores "
    "{measure} {amount} {currency} for its latest period {latest_period_key}, and its calc trace "
    "holds no period node of {measure} under {subject}, so the balance at the earlier period "
    "{period_key} cannot be read. The latest figure is not answered for an earlier period."
)
# T-CON-09 labelled balances. The engine publishes a node per member contract, entity and period
# end for every one it measures per member (stage 10 / 11; DG-KRN-EXP-01, zeros included); the
# current parts (measured per GROUP, ENGINE_SPEC_B §10.2.8) and ``accounts_receivable`` outside
# ``ENGINE`` mode (S10-R-19) have none and stay at the column default.
BALANCE_MEASURES: Final = (
    "contract_liability",
    "contract_liability_current",
    "contract_asset",
    "contract_asset_current",
    "unbilled_receivable",
    "accounts_receivable",
    "refund_liability",
    "return_asset",
    "deposit_liability",
    "customer_incentive_asset",
    "consideration_payable",
    "cost_asset_carrying",
    "loss_provision",
)
ROLLFORWARD_BALANCES: Final = ("contract_liability", "contract_asset", "unbilled_receivable")
# ENGINE_SPEC_B S10-R-08 B_u, §10.5: the billing the engine counts in the position of a member
# contract and entity, cumulative per period end — the measure JET-03 posts in ENGINE mode.
BILLED_UNCONDITIONAL: Final = "billed_unconditional_cum"


# --- money and results --------------------------------------------------------------------------


def minor_unit(currency: str) -> int:
    spec = ISO_4217.get(currency)
    if spec is None:
        raise ValueError(f"{currency} is not in the currency table")
    return spec.minor_unit


def quantized(amount: Decimal, currency: str) -> Decimal:
    """``amount`` at the currency's minor unit (DG-KRN-MONEY-06)."""
    return amount.quantize(Decimal(1).scaleb(-minor_unit(currency)), rounding=ROUND_HALF_UP)


def money(amount: Decimal, currency: str) -> dict[str, str]:
    """API-S-Money with exactly the minor-unit decimals; negative zero without its sign."""
    value = quantized(amount, currency)
    if value == 0:
        value = abs(value)
    return {"amount": format(value, "f"), "currency": currency}


def by_currency(values: Mapping[str, Decimal]) -> dict[str, str]:
    """A control total per currency: ``{<ISO>: <amount>}`` in code order."""
    return {code: money(values[code], code)["amount"] for code in sorted(values)}


def add(totals: dict[str, Decimal], currency: str, amount: Decimal) -> None:
    totals[currency] = totals.get(currency, ZERO) + amount


def compared(
    code: str, expected: Mapping[str, Decimal], actual: Mapping[str, Decimal]
) -> dict[str, Any]:
    """``PASS`` when ``expected`` equals ``actual`` in every currency, else ``FAIL``."""
    currencies = sorted(set(expected) | set(actual))
    agree = all(
        quantized(expected.get(code_, ZERO), code_) == quantized(actual.get(code_, ZERO), code_)
        for code_ in currencies
    )
    return {
        "code": code,
        "result": PASS if agree else FAIL,
        "expected": [money(expected.get(item, ZERO), item) for item in currencies],
        "actual": [money(actual.get(item, ZERO), item) for item in currencies],
    }


def not_applicable(code: str) -> dict[str, Any]:
    return {"code": code, "result": NOT_APPLICABLE, "expected": None, "actual": None}


def difference(item: Mapping[str, Any]) -> list[dict[str, str]] | None:
    """API-S-ReportRun ``tie_out_results[].difference`` of a stored T-RPT-02 item (D-88 L7-3-Q-3):
    ``actual − expected`` per currency in code order, through ``money`` (minor-unit quantize, no
    negative zero). It is computed when the run is serialised; the stored ``tie_out_results``, the
    JSON dataset, manifests, XLSX and PDF do not carry it, so output hashes and rerun identity are
    unaffected. None when either side carries no amounts (``NOT_APPLICABLE``)."""
    expected, actual = _by_code(item.get("expected")), _by_code(item.get("actual"))
    if expected is None or actual is None:
        return None
    return [
        money(actual.get(code, ZERO) - expected.get(code, ZERO), code)
        for code in sorted(set(expected) | set(actual))
    ]


def _by_code(value: Any) -> dict[str, Decimal] | None:
    """The amounts of a list of API-S-Money by currency; None for anything but a list."""
    if not isinstance(value, list):
        return None
    found: dict[str, Decimal] = {}
    for entry in value:
        add(found, str(entry["currency"]), Decimal(str(entry["amount"])))
    return found


def invalid(name: str, message: str) -> Problem:
    """422 ``validation-failed`` on one run parameter (T-RPT-01 rule 1)."""
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field=f"parameters.{name}", rule_id=RULE_PARAMETERS, message=message)],
    )


# --- entities and periods -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntityRef:
    id: UUID
    code: str
    calendar_id: UUID
    functional_currency: str
    time_zone: str


@dataclass(frozen=True, slots=True)
class PeriodRef:
    id: UUID
    key: str
    name: str
    fiscal_year: int
    period_no: int
    quarter_no: int | None
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class Calendar:
    periods: tuple[PeriodRef, ...]  # start date order

    def named(self, key: str, parameter: str) -> PeriodRef:
        for item in self.periods:
            if item.key == key:
                return item
        raise invalid(parameter, UNKNOWN_PERIOD)

    def holding(self, day: date) -> PeriodRef | None:
        for item in self.periods:
            if item.start <= day <= item.end:
                return item
        return None

    def between(self, first: PeriodRef, last: PeriodRef) -> tuple[PeriodRef, ...]:
        return tuple(item for item in self.periods if first.start <= item.start <= last.start)

    def before(self, item: PeriodRef) -> PeriodRef | None:
        earlier = [found for found in self.periods if found.end < item.start]
        return earlier[-1] if earlier else None

    def fiscal_year(self, item: PeriodRef) -> tuple[PeriodRef, ...]:
        return tuple(found for found in self.periods if found.fiscal_year == item.fiscal_year)


def entities(
    session: Session, entity_ids: Sequence[UUID], *, params: ReportParams | None = None
) -> tuple[EntityRef, ...]:
    """The run's entities in code order. With ``params`` (S15-R-24 / frps3c-1): a bound run reads
    the RETAINED configuration evidence — never today's ``legal_entity`` rows — and refuses by name
    an entity the binding does not hold; a live build records the rows it consumed."""
    if not entity_ids:
        return ()
    if params is not None and params.binding is not None:
        stored = _retained_mapping(
            "configuration.entities", bound_configuration(params).get("entities"), "entities"
        )
        wanted = [str(entity_id) for entity_id in entity_ids]
        missing = [key for key in wanted if key not in stored]
        if missing:
            raise missing_input("configuration.entities", missing)
        return tuple(
            sorted((_retained_entity(key, stored[key]) for key in wanted), key=lambda i: i.code)
        )
    rows = session.execute(
        select(
            legal_entity.c.id,
            legal_entity.c.code,
            legal_entity.c.calendar_id,
            legal_entity.c.functional_currency,
            legal_entity.c.time_zone,
        )
        .where(legal_entity.c.id.in_(list(entity_ids)))
        .order_by(legal_entity.c.code)
    ).mappings()
    found = tuple(
        EntityRef(
            id=UUID(str(row["id"])),
            code=str(row["code"]),
            calendar_id=UUID(str(row["calendar_id"])),
            functional_currency=str(row["functional_currency"]).strip(),
            time_zone=str(row["time_zone"]),
        )
        for row in rows
    )
    if params is not None:
        record_configuration(
            params,
            entities={
                str(item.id): {
                    "code": item.code,
                    "calendar_id": str(item.calendar_id),
                    "functional_currency": item.functional_currency,
                    "time_zone": item.time_zone,
                }
                for item in found
            },
        )
    return found


def calendars(
    session: Session, found: Sequence[EntityRef], *, params: ReportParams | None = None
) -> dict[UUID, Calendar]:
    """Each entity's calendar periods by entity id. With ``params`` (frps3c-1): a bound run reads
    the RETAINED period definitions of each consumed calendar (refusing an absent calendar by
    name); a live build records every period row it read."""
    calendar_ids = sorted({item.calendar_id for item in found}, key=str)
    if not calendar_ids:
        return {}
    if params is not None and params.binding is not None:
        stored = _retained_mapping(
            "configuration.periods", bound_configuration(params).get("periods"), "periods"
        )
        missing = [
            str(calendar_id) for calendar_id in calendar_ids if str(calendar_id) not in stored
        ]
        if missing:
            raise missing_input("configuration.periods", missing)
        retained = {
            UUID(key): tuple(
                _retained_period(key, item) for item in _retained_list(key, stored[key])
            )
            for key in (str(calendar_id) for calendar_id in calendar_ids)
        }
        return {item.id: Calendar(retained[item.calendar_id]) for item in found}
    rows = session.execute(
        select(period).where(period.c.calendar_id.in_(calendar_ids)).order_by(period.c.start_date)
    ).mappings()
    by_calendar: dict[UUID, list[PeriodRef]] = {}
    for row in rows:
        by_calendar.setdefault(UUID(str(row["calendar_id"])), []).append(
            PeriodRef(
                id=UUID(str(row["id"])),
                key=str(row["period_key"]),
                name=str(row["name"]),
                fiscal_year=int(row["fiscal_year"]),
                period_no=int(row["period_no"]),
                quarter_no=None if row["quarter_no"] is None else int(row["quarter_no"]),
                start=row["start_date"],
                end=row["end_date"],
            )
        )
    if params is not None:
        record_configuration(
            params,
            periods={
                str(calendar_id): [
                    {
                        "id": str(period_ref.id),
                        "key": period_ref.key,
                        "name": period_ref.name,
                        "fiscal_year": period_ref.fiscal_year,
                        "period_no": period_ref.period_no,
                        "quarter_no": period_ref.quarter_no,
                        "start": period_ref.start.isoformat(),
                        "end": period_ref.end.isoformat(),
                    }
                    for period_ref in by_calendar.get(calendar_id, [])
                ]
                for calendar_id in calendar_ids
            },
        )
    return {item.id: Calendar(tuple(by_calendar.get(item.calendar_id, ()))) for item in found}


def run_day(params: ReportParams, entity: EntityRef) -> date:
    """The run's as-of date for an entity: ``as_of``, else ``known_at`` in its time zone."""
    if params.as_of_date is not None:
        return params.as_of_date
    return to_entity_date(params.known_at, entity.time_zone)


def period_of(params: ReportParams, calendar: Calendar, entity: EntityRef) -> PeriodRef:
    """``period_key``, else the period holding the run's as-of date (SCREENS_B RPT-02, RPT-06)."""
    key = params.parameters.get("period_key")
    if key is not None:
        return calendar.named(str(key), "period_key")
    found = calendar.holding(run_day(params, entity))
    if found is None:
        raise invalid("period_key", UNKNOWN_PERIOD)
    return found


def range_of(
    params: ReportParams, calendar: Calendar, entity: EntityRef, *, year_default: bool = False
) -> tuple[PeriodRef, ...]:
    """``from_period_key`` to ``to_period_key``. Defaults: the period holding the as-of date, and
    with ``year_default`` its fiscal year's first and last periods (SCREENS_B RPT-01)."""
    given_from = params.parameters.get("from_period_key")
    given_to = params.parameters.get("to_period_key")
    current = calendar.holding(run_day(params, entity))
    if given_to is not None:
        last = calendar.named(str(given_to), "to_period_key")
    elif current is not None and year_default:
        last = calendar.fiscal_year(current)[-1]
    elif current is not None:
        last = current
    else:
        raise invalid("to_period_key", UNKNOWN_PERIOD)
    if given_from is not None:
        first = calendar.named(str(given_from), "from_period_key")
    elif year_default:
        first = calendar.fiscal_year(current or last)[0]
    else:
        first = current if current is not None and current.start <= last.start else last
    return calendar.between(first, last)


def book_of(session: Session, params: ReportParams) -> str:
    """The run's book, else the tenant's primary book (API-C-11). The default is CONFIGURATION
    (frps3c-1): a live build records the primary book it read; a bound run reads the retained one
    and refuses by name when the binding holds none."""
    given = params.book_code or params.parameters.get("book")
    if given is not None:
        return str(given)
    if params.binding is not None:
        stored = bound_configuration(params).get("book_code")
        if stored is None:
            raise missing_input("configuration.book_code", ("primary",))
        return str(stored)
    code = str(primary_book(session).value)
    record_configuration(params, book_code=code)
    return code


# --- versions and balances ----------------------------------------------------------------------


def effective_cutoff(
    known_at: datetime, transaction_at: datetime, *, historical: bool = False
) -> datetime:
    """The record cutoff of a report read, on one of two bases (F-RPS-CUTOFF-R1, record §43).

    *Record basis* (``historical=False``; L6-3-Q-19): the later of ``known_at`` and the job's
    transaction timestamp — right for a run whose ``known_at`` defaulted to the application clock,
    which in a FrozenClock world lags the server time that stamps ``contract_version.known_at``
    (``computation.persist``: the greatest ``event.recorded_at``). *Historical basis*
    (``historical=True``; READ-1): an explicit as-of read keeps the supplied ``known_at`` exactly,
    so a report requested as of an earlier checkpoint never selects a version recorded after it.
    """
    if not isinstance(transaction_at, datetime):
        raise TypeError("transaction_timestamp() returned no timestamp")
    if historical:
        return known_at
    return max(known_at, transaction_at)


def version_cutoff(session: Session, known_at: datetime, *, historical: bool = False) -> datetime:
    """``effective_cutoff`` against this transaction's timestamp: L6-3-Q-19 by default, READ-1 for
    an explicit historical read (``ReportParams.historical``)."""
    started = session.execute(select(func.transaction_timestamp())).scalar_one()
    return effective_cutoff(known_at, started, historical=historical)


def cutoff_for(session: Session, params: ReportParams) -> datetime:
    """The record cutoff a build applies (S15-R-24; frps3b): the BOUND cutoff of a bound run —
    never the current transaction time — else ``version_cutoff`` on the run's basis, recorded into
    ``params.sources`` so the framework binds it with the run."""
    if params.binding is not None:
        return params.binding.cutoff
    cutoff = version_cutoff(session, params.known_at, historical=params.historical)
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    return cutoff


def versions_for(
    session: Session, params: ReportParams, *, book_code: str, cutoff: datetime
) -> tuple[UUID, ...]:
    """The contract-version ids a build consumes for ``book_code``: the BOUND ids of a bound run
    (never a new "latest" query), else ``latest_versions`` at ``cutoff`` executed once and
    recorded into ``params.sources`` (S15-R-24)."""
    if params.binding is not None:
        return params.binding.version_ids(book_code)
    ids = tuple(
        UUID(str(value))
        for value in session.execute(
            latest_versions(session, book_code=book_code, cutoff=cutoff)
        ).scalars()
    )
    if params.sources is not None:
        params.sources.record_versions(book_code, ids)
    return ids


def rows_read(
    session: Session,
    params: ReportParams,
    contract_id: ColumnElement[Any],
    version_id: ColumnElement[Any],
    *,
    book_code: str,
    cutoff: datetime,
    only_contract: UUID | None = None,
) -> ColumnElement[bool]:
    """Whether a row of contract ``contract_id`` in contract version ``version_id`` is one a build
    reads at ``cutoff`` (``read_from``; 04 T-CON-04 reading rule, form (1)). A live build records
    the versions it reads (``versions_for``, S15-R-24); a bound run forms the pairs among its
    bound versions with the memberships recorded by the bound cutoff (S15-R-24a (d)), so a rerun
    repeats a run taken while a group awaited its computation pair for pair. A version alone does
    not say which contract's rows to read from it: a group's version can still carry the rows of
    a contract that is read from another. ``only_contract`` is the one contract the build is
    restricted to."""
    consumed = versions_for(session, params, book_code=book_code, cutoff=cutoff)
    return read_from(
        contract_id,
        version_id,
        book_code=book_code,
        cutoff=cutoff,
        versions=consumed if params.binding is not None else None,
        only_contract=only_contract,
    )


def record_consumed_versions(params: ReportParams, book_code: str, ids: Iterable[UUID]) -> None:
    """A builder that selects versions itself (RPO's history, contract history) records the ids
    it consumed for the binding (S15-R-24); nothing under a bound run."""
    if params.binding is None and params.sources is not None:
        params.sources.record_versions(book_code, ids)


def bound_version_where(
    params: ReportParams, column: ColumnElement[Any], book_code: str
) -> list[ColumnElement[bool]]:
    """Under a bound run, the extra predicate restricting a version selection to the bound ids
    (S15-R-24); nothing for a live build."""
    if params.binding is None:
        return []
    return [in_versions(column, params.binding.version_ids(book_code))]


def _bound_members(params: ReportParams, kind: str) -> tuple[str, ...]:
    """The CAPTURED membership of ``kind`` of a bound run (Codex production-20260921-1004 R1; design
    §10.5 EMPTY versus ABSENT): the kind's PRESENCE is checked before any id is obtained — a
    binding whose readers did not capture it (a pre-3c-2 ADAPTER binding) refuses by NAME and is
    never completed from today's rows, never a count comparison; an explicit EMPTY population
    (``[]``) is a genuinely captured membership and reads nothing."""
    assert params.binding is not None
    if kind not in params.binding.members:
        raise Problem(
            "invalid-transition", INCOMPLETE_BINDING.format(kind=f"members.{kind}", key="the run")
        )
    return params.binding.member_ids(kind)


def bound_member_where(
    params: ReportParams, kind: str, column: ColumnElement[Any]
) -> list[ColumnElement[bool]]:
    """Under a bound run, the predicate restricting a non-version read to the bound membership of
    ``kind`` (subledger lines, journal runs; S15-R-24 / Codex 2154) — an absent kind refuses by
    name first (``_bound_members``); nothing for a live build."""
    if params.binding is None:
        return []
    ids = _bound_members(params, kind)
    return [column.in_([UUID(item) for item in ids]) if ids else false()]


def record_members(params: ReportParams, kind: str, ids: Iterable[object]) -> None:
    """A live build records the non-version rows it consumed (by id) for the binding."""
    if params.binding is None and params.sources is not None:
        params.sources.record_members(kind, ids)


def require_members(params: ReportParams, kind: str, found: Iterable[object]) -> None:
    """Codex fa64924e D4 (frps3c-2): under a bound run the rows a bound read obtained must be
    EXACTLY the bound members of ``kind`` — a bound id the read did not return (deleted, hidden by
    today's scope or authorization) refuses by NAME with the missing identities, never a count
    comparison, never a later CTL-029 mismatch as the only detection. Nothing for a live build."""
    if params.binding is None:
        return
    bound = set(_bound_members(params, kind))  # an absent kind refuses here too (R1)
    missing = sorted(bound - {str(item) for item in found})
    if missing:
        raise missing_input(f"members.{kind}", missing)


def in_versions(column: ColumnElement[Any], ids: Sequence[UUID]) -> ColumnElement[bool]:
    """``column IN (ids)``; ``false`` for no ids (never an empty IN)."""
    return column.in_(list(ids)) if ids else false()


def label_for(params: ReportParams, kind: str, key: object, live: str | None) -> str | None:
    """A material grouping value (customer segment, product family / revenue category) as the run
    consumed it (S15-R-24): the BOUND value of a bound run — never the live join — else ``live``,
    recorded into ``params.sources``. A None ``key`` (an outer join without a row) is not bound."""
    if key is None:
        return live
    if params.binding is not None:
        bound, value = params.binding.label(kind, str(key))
        if not bound:
            # Codex 2216 (B): an incomplete binding is refused by NAME — never a silent live
            # fallback.
            raise Problem("invalid-transition", INCOMPLETE_BINDING.format(kind=kind, key=key))
        return value
    if params.sources is not None:
        params.sources.record_label(kind, str(key), live)
    return live


INCOMPLETE_BINDING: Final = (
    "The run's source binding holds no {kind} for {key}: the same-source read is incomplete and "
    "is not completed from today's rows. Run the report current instead."
)


def record_evidence(params: ReportParams, kind: str, value: Any) -> None:
    """A live build of a retained-inputs builder records the JSON-safe input facts it consumed
    (Codex 2225); nothing under a bound run."""
    if params.binding is None and params.sources is not None:
        params.sources.record_evidence(kind, value)


CONFIGURATION: Final = "configuration"  # evidence kind: entities, periods per calendar, book_code
CUSTOMER_ASSOCIATION: Final = (
    "customer_association"  # evidence kind: contract id → customer id | None
)
ENTITY_CODE: Final = "entity_code"  # label kind
CUSTOMER_NAME: Final = "customer_name"  # label kind
BOUND_INPUT_MISSING: Final = (
    "The run's source binding holds no {kind} for {keys}: the same-source read cannot be "
    "completed and is not completed from today's rows (S15-R-24). Run the report current instead."
)


def missing_input(kind: str, keys: Iterable[object]) -> Problem:
    """Codex fa64924e D4: a bound input the binding does not hold is refused by NAME with the exact
    identities — never completed from today's rows, never detected only by a later mismatch."""
    return Problem(
        "invalid-transition",
        BOUND_INPUT_MISSING.format(kind=kind, keys=", ".join(sorted(str(key) for key in keys))),
    )


def record_configuration(params: ReportParams, **parts: Any) -> None:
    """A live build merges the configuration it consumed (``entities`` and ``periods`` are merged by
    id; ``book_code`` is set) into ``evidence.configuration``; nothing under a bound run."""
    if params.binding is not None or params.sources is None:
        return
    current = dict(params.sources.evidence.get(CONFIGURATION) or {})
    for name, value in parts.items():
        if name in ("entities", "periods"):
            merged = dict(current.get(name) or {})
            merged.update(value)
            current[name] = merged
        else:
            current[name] = value
    params.sources.record_evidence(CONFIGURATION, current)


_ENTITY_FIELDS: Final = ("code", "calendar_id", "functional_currency", "time_zone")
_PERIOD_FIELDS: Final = (
    "id",
    "key",
    "name",
    "fiscal_year",
    "period_no",
    "quarter_no",
    "start",
    "end",
)


def _retained_entity(key: str, item: Any) -> EntityRef:
    """A retained entity row validated field by field (Codex 8ede60b7 R2; design §10.4 / §10.5):
    a missing required key or a malformed known value refuses by NAME with the entity id and the
    key — never a raw KeyError / ValueError, never a live read."""
    if not isinstance(item, Mapping):
        raise missing_input("configuration.entities (row)", (key,))
    for field_name in _ENTITY_FIELDS:
        if field_name not in item or item[field_name] is None:
            raise missing_input(f"configuration.entities.{field_name}", (key,))
    try:
        return EntityRef(
            id=UUID(key),
            code=str(item["code"]),
            calendar_id=UUID(str(item["calendar_id"])),
            functional_currency=str(item["functional_currency"]),
            time_zone=str(item["time_zone"]),
        )
    except ValueError as exc:
        raise missing_input(f"configuration.entities (malformed: {exc})", (key,)) from exc


def _retained_list(calendar_key: str, value: Any) -> list[Any]:
    if not isinstance(value, list):  # an EMPTY list is admitted (a calendar without periods)
        raise missing_input("configuration.periods (list)", (calendar_key,))
    return value


def _retained_period(calendar_key: str, item: Any) -> PeriodRef:
    """A retained period row validated field by field; ``quarter_no`` may be null (admitted NULL),
    every other field is required and typed."""
    if not isinstance(item, Mapping):
        raise missing_input("configuration.periods (row)", (calendar_key,))
    for field_name in _PERIOD_FIELDS:
        if field_name not in item:
            raise missing_input(f"configuration.periods.{field_name}", (calendar_key,))
        if item[field_name] is None and field_name != "quarter_no":
            raise missing_input(f"configuration.periods.{field_name}", (calendar_key,))
    identity = f"{calendar_key}:{item['id']}"
    try:
        return PeriodRef(
            id=UUID(str(item["id"])),
            key=str(item["key"]),
            name=str(item["name"]),
            fiscal_year=_retained_int(item["fiscal_year"]),
            period_no=_retained_int(item["period_no"]),
            quarter_no=None if item["quarter_no"] is None else _retained_int(item["quarter_no"]),
            start=date.fromisoformat(str(item["start"])),
            end=date.fromisoformat(str(item["end"])),
        )
    except (ValueError, TypeError) as exc:
        raise missing_input(f"configuration.periods (malformed: {exc})", (identity,)) from exc


def _retained_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"not an integer: {value!r}")
    return int(value)


def _retained_mapping(kind: str, value: Any, identity: str) -> dict[str, Any]:
    """An enclosing retained container must be a mapping BEFORE any ``dict(...)`` conversion (Codex
    7da28840 -0414: a JSON-safe malformed container survives ``from_stored``); ``None`` / absent is
    the caller's admitted-empty case, anything else that is not a mapping refuses by name."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise missing_input(f"{kind} (shape: not a mapping)", (identity,))
    return dict(value)


def bound_configuration(params: ReportParams) -> Mapping[str, Any]:
    """The retained configuration of a bound run (refused by name when the binding holds none or
    when its container is not a mapping)."""
    value = bound_evidence(params, CONFIGURATION)
    if not isinstance(value, Mapping):  # `None` is not admitted here: the kind is present but empty
        raise missing_input(f"{CONFIGURATION} (shape: not a mapping)", (CONFIGURATION,))
    return dict(value)


def customer_of(params: ReportParams, contract_id: UUID, live: UUID | None) -> UUID | None:
    """The customer a contract was associated with AS CONSUMED (D1): a bound run reads the retained
    association — a retained NULL is "no customer", a contract absent from it refuses by name; a
    live build records ``live``."""
    if params.binding is not None:
        stored = dict(bound_evidence(params, CUSTOMER_ASSOCIATION))
        key = str(contract_id)
        if key not in stored:
            raise missing_input(CUSTOMER_ASSOCIATION, (contract_id,))
        return None if stored[key] is None else UUID(str(stored[key]))
    if params.sources is not None:
        current = dict(params.sources.evidence.get(CUSTOMER_ASSOCIATION) or {})
        current[str(contract_id)] = None if live is None else str(live)
        params.sources.record_evidence(CUSTOMER_ASSOCIATION, current)
    return live


def entity_code_for(params: ReportParams, entity_id: UUID, live: str) -> str:
    """An entity code as the run consumed it (`labels.entity_code`): the bound value under a bound
    run — a binding without it refuses by name — else ``live``, recorded."""
    value = label_for(params, ENTITY_CODE, entity_id, live)
    if value is None:  # a code is never null; a retained null would be an incomplete binding
        raise missing_input(ENTITY_CODE, (entity_id,))
    return value


def _customer_name(params: ReportParams | None, row: Mapping[str, Any]) -> str | None:
    """``balances_at``'s customer name: the live join for a dashboard read (no ``params``); under a
    report build the association and the name are retained / bound (D1: NULL vs absent explicit)."""
    live_name = None if row["customer_name"] is None else str(row["customer_name"])
    if params is None:
        return live_name
    live_customer = None if row["customer_id"] is None else UUID(str(row["customer_id"]))
    customer_id = customer_of(params, UUID(str(row["contract_id"])), live_customer)
    if customer_id is None:
        return None
    return label_for(params, CUSTOMER_NAME, customer_id, live_name)


def bound_evidence(params: ReportParams, kind: str) -> Any:
    """The retained input facts of ``kind`` a bound run rebuilds from; a binding without them is
    refused by name (Codex 2216 (B) / 2225)."""
    assert params.binding is not None
    if kind not in params.binding.evidence:
        raise Problem("invalid-transition", INCOMPLETE_BINDING.format(kind=kind, key="evidence"))
    return params.binding.evidence[kind]


def group_held_at(
    tenant_id: ColumnElement[Any], group_id: ColumnElement[Any], cutoff: datetime | None
) -> ColumnElement[bool]:
    """Whether a combination group holds a member contract at ``cutoff`` — now, for None (04
    T-CON-04: a membership is valid from ``valid_from_known_at`` until ``valid_to_known_at``,
    record time). A group every contract has left — the singleton group of a contract that
    joined a combined group (ENGINE_SPEC S02-R-10), a combined group all of whose members were
    uncombined — keeps its versions as history and is no longer the group of any contract. A
    group without any membership row by ``cutoff`` (rows written outside the product's commands,
    which record a membership with every booking) is read as recorded: its versions are never
    dropped silently. Both conditions enter T-CON-04 by ``ix_combination_group_member__group``
    and compare uuid and timestamp columns only."""
    member = combination_group_member
    of_group = [member.c.tenant_id == tenant_id, member.c.combination_group_id == group_id]
    open_ended = member.c.valid_to_known_at.is_(None)
    if cutoff is None:
        held = select(member.c.id).where(*of_group, open_ended)
    else:
        of_group.append(member.c.valid_from_known_at <= cutoff)
        held = select(member.c.id).where(
            *of_group, or_(open_ended, member.c.valid_to_known_at > cutoff)
        )
    return or_(held.exists(), ~select(member.c.id).where(*of_group).exists())


def chain_versions(
    *,
    book_code: str,
    cutoff: datetime | None,
    versions: Sequence[UUID] | None = None,
    only_contract: UUID | None = None,
) -> Select[Any]:
    """The versions on each contract's chain (04 T-CON-04 reading rule; supervisor ruling R-117
    (a)): one row per contract and version of ``book_code`` that was computed with the contract
    among its members (``contract_computation.stream_heads``) during one of the contract's
    memberships in the version's group (record time) — ``contract_id``, ``id``, ``member_from``
    (the membership's start), ``version_no`` and ``status_in_book``. The chain's order is
    ``member_from``, then ``version_no``.

    The members a computation names decide, not the record time alone: a version's ``known_at``
    is that of its latest event, so a version a group computes after a contract has left it can
    be stamped inside that contract's membership (the members that stay may have no later
    event). ``cutoff`` None reads the present; ``versions`` keeps the bound ids of a bound run
    (S15-R-24a (d): the memberships are those recorded by the bound cutoff); ``only_contract``
    keeps one contract's chain. The statement enters T-CON-04 and ``contract_version`` by uuid
    and timestamp columns and filters the book and the members afterwards."""
    member = combination_group_member.alias("chain_member")
    version = contract_version.alias("chain_version")
    computation = contract_computation.alias("chain_computation")
    conditions = [
        version.c.book_code == book_code,
        member.c.valid_from_known_at <= version.c.known_at,
        or_(member.c.valid_to_known_at.is_(None), version.c.known_at < member.c.valid_to_known_at),
        computation.c.stream_heads.has_key(cast(member.c.contract_id, Text)),
    ]
    if cutoff is not None:
        conditions.append(version.c.known_at <= cutoff)
    if versions is not None:
        conditions.append(in_versions(version.c.id, versions))
    if only_contract is not None:
        conditions.append(member.c.contract_id == only_contract)
    return (
        select(
            member.c.contract_id,
            version.c.id,
            member.c.valid_from_known_at.label("member_from"),
            version.c.version_no,
            version.c.status_in_book,
        )
        .select_from(
            member.join(
                version,
                and_(
                    version.c.tenant_id == member.c.tenant_id,
                    version.c.combination_group_id == member.c.combination_group_id,
                ),
            ).join(
                computation,
                and_(
                    computation.c.tenant_id == version.c.tenant_id,
                    computation.c.id == version.c.contract_computation_id,
                ),
            )
        )
        .where(*conditions)
    )


def chain_latest(
    *,
    book_code: str,
    cutoff: datetime | None,
    versions: Sequence[UUID] | None = None,
    only_contract: UUID | None = None,
) -> Select[Any]:
    """Per contract, the last version along its chain recorded by ``cutoff`` (``chain_versions``):
    ``contract_id``, ``id`` and ``status_in_book``. A contract stays where it was last computed:
    between an approved combination and the combined group's first computation — deferred for a
    group above the inline budget, DG-CMD-09, or failed — that is its own group's last version; a
    contract that left a group is read from that group's last version with it until its own
    group is computed."""
    on_chain = chain_versions(
        book_code=book_code, cutoff=cutoff, versions=versions, only_contract=only_contract
    ).subquery("on_chain")
    return (
        select(on_chain.c.contract_id, on_chain.c.id, on_chain.c.status_in_book)
        .distinct(on_chain.c.contract_id)
        .order_by(
            on_chain.c.contract_id, on_chain.c.member_from.desc(), on_chain.c.version_no.desc()
        )
    )


def recorded_latest(
    *,
    book_code: str,
    cutoff: datetime | None,
    versions: Sequence[UUID] | None = None,
    only_contract: UUID | None = None,
) -> Select[Any]:
    """Versions read as recorded — ``id`` and ``status_in_book``: of the versions of ``book_code``
    whose computation names no member, each group's latest by ``cutoff``, for the groups that
    hold a member contract then or have no membership row (``group_held_at``). The product's
    computations name their members, so these are rows written outside its commands; they are
    never dropped silently and take no part in a chain. ``only_contract`` keeps the groups one
    contract is or was in."""
    version = contract_version.alias("recorded_version")
    computation = contract_computation.alias("recorded_computation")
    conditions = [
        version.c.book_code == book_code,
        computation.c.stream_heads == literal({}, JSONB()),
        group_held_at(version.c.tenant_id, version.c.combination_group_id, cutoff),
    ]
    if cutoff is not None:
        conditions.append(version.c.known_at <= cutoff)
    if versions is not None:
        conditions.append(in_versions(version.c.id, versions))
    if only_contract is not None:
        member = combination_group_member.alias("recorded_member")
        conditions.append(
            or_(
                version.c.combination_group_id.in_(
                    select(member.c.combination_group_id).where(
                        member.c.contract_id == only_contract
                    )
                ),
                version.c.combination_group_id.in_(
                    select(contract.c.combination_group_id).where(contract.c.id == only_contract)
                ),
            )
        )
    return (
        select(version.c.id, version.c.status_in_book)
        .select_from(
            version.join(
                computation,
                and_(
                    computation.c.tenant_id == version.c.tenant_id,
                    computation.c.id == version.c.contract_computation_id,
                ),
            )
        )
        .where(*conditions)
        .distinct(version.c.combination_group_id)
        .order_by(version.c.combination_group_id, version.c.version_no.desc())
    )


def read_from(
    contract_id: ColumnElement[Any],
    version_id: ColumnElement[Any],
    *,
    book_code: str,
    cutoff: datetime | None,
    statuses: Iterable[str] | None = INCLUDED_STATUSES,
    versions: Sequence[UUID] | None = None,
    only_contract: UUID | None = None,
) -> ColumnElement[bool]:
    """Whether a row of contract ``contract_id`` in contract version ``version_id`` is read at
    ``cutoff`` (04 T-CON-04 reading rule, form (1); item RPT-FORMER-GROUP-READERS-1): the version
    is the contract's — the last along its chain (``chain_latest``) — or a version read as
    recorded (``recorded_latest``). A row of a version counts for a contract only when that
    version is the contract's, so a group's version that still carries the rows of a contract
    read elsewhere does not state it a second time. ``statuses`` keeps the versions whose status
    in the book is among them (default: those that enter the disclosures; None: any) — the
    status of the version the contract is read from, never an earlier one in its stead.
    ``cutoff`` None reads the present; ``versions`` keeps a bound run's version ids;
    ``only_contract`` is the one contract a caller reads (the pairs of the others are not
    formed).

    The two selections are common table expressions, formed once for the statement. The first
    condition — the version is one that is read — lets the caller's table be entered by the
    version, an index condition on uuid columns as under form (1); the second keeps each
    contract to its own version."""
    pairs = chain_latest(
        book_code=book_code, cutoff=cutoff, versions=versions, only_contract=only_contract
    ).cte()
    recorded = recorded_latest(
        book_code=book_code, cutoff=cutoff, versions=versions, only_contract=only_contract
    ).cte()
    named = select(pairs.c.contract_id, pairs.c.id)
    named_versions = select(pairs.c.id)
    unnamed = select(recorded.c.id)
    if statuses is not None:
        kept = sorted(statuses)
        named = named.where(pairs.c.status_in_book.in_(kept))
        named_versions = named_versions.where(pairs.c.status_in_book.in_(kept))
        unnamed = unnamed.where(recorded.c.status_in_book.in_(kept))
    return and_(
        version_id.in_(union_all(named_versions, unnamed)),
        or_(tuple_(contract_id, version_id).in_(named), version_id.in_(unnamed)),
    )


def latest_versions(session: Session, *, book_code: str, cutoff: datetime) -> Select[Any]:
    """Ids of the versions of ``book_code`` read at ``cutoff`` whose status in the book enters
    the disclosures: the version each contract is read from (``chain_latest``) and the versions
    read as recorded (``recorded_latest``). A contract is read once, from the last version along
    its chain — never from the last version of a group it has left beside that of its present
    group (measured before item RPT-FORMER-GROUP-VERSIONS-1: each member of a combined group was
    read twice — RPT-02 held two rows with one row key, the lock's ``CONTRACT_BALANCES`` dataset
    was refused for it), and never from nowhere while its present group awaits its first
    computation (measured before item RPT-FORMER-GROUP-READERS-1: RPT-02 and the waterfall lost
    both members of a combined group whose computation was deferred). A cutoff before the
    combination was recorded reads the former group. The rows of these versions are read with
    ``read_from``, which keeps each contract to its own version."""
    included = sorted(INCLUDED_STATUSES)
    pairs = chain_latest(book_code=book_code, cutoff=cutoff).subquery("chain_latest")
    recorded = recorded_latest(book_code=book_code, cutoff=cutoff).subquery("recorded_versions")
    read = union(
        select(pairs.c.id).where(pairs.c.status_in_book.in_(included)),
        select(recorded.c.id).where(recorded.c.status_in_book.in_(included)),
    ).subquery("versions_read")
    return select(read.c.id)


def contract_named(session: Session, params: ReportParams) -> UUID | None:
    """``contract_external_id`` as a contract id; 422 for an unknown contract (SCREENS_B RPT-01)."""
    value = params.parameters.get("contract_external_id")
    if value is None:
        return None
    found = session.execute(
        select(contract.c.id).where(contract.c.external_id == str(value))
    ).scalar_one_or_none()
    if found is None:
        raise invalid("contract_external_id", UNKNOWN_CONTRACT.format(value=value))
    return UUID(str(found))


@dataclass(frozen=True, slots=True)
class BalanceRow:
    """The labelled balances of one member contract and contracting entity at a period end."""

    contract_id: UUID
    external_id: str
    customer_name: str | None
    entity_id: UUID
    entity_code: str
    currency: str
    version_id: UUID
    values: Mapping[str, Decimal] = field(default_factory=dict)

    def value(self, measure: str) -> Decimal:
        return self.values.get(measure, ZERO)


@dataclass(frozen=True, slots=True)
class LockedRow:
    """One contract's balances at a locked period end, as the lock's dataset states them."""

    currency: str
    values: Mapping[str, Decimal]


@dataclass(frozen=True, slots=True)
class LockedEnd:
    """What a lock states of one entity's period end (``reports.locked_ends``): the rows of its
    ``CONTRACT_BALANCES`` dataset by contract external id, the instant its datasets were frozen
    at (``period_lock.cutoff_known_at``) and the two files read."""

    lock_id: UUID
    period_key: str
    frozen_at: datetime
    balances_sha256: str
    rollforward_sha256: str
    rows: Mapping[str, LockedRow]


class LockedEnds(Protocol):
    """The locked period ends of one build (ENGINE_SPEC_B S15-R-20 rev 1.168;
    ``reports.locked_ends.Reader``)."""

    def at(self, entity_id: UUID, period: PeriodRef) -> LockedEnd | None:
        """The lock's statement of the entity's balances at the end of ``period``; None where
        the end is read from the versions."""

    def unknown(self, entity_id: UUID, period: PeriodRef, contract: str) -> Problem:
        """The refusal of a dataset row whose contract the read does not hold."""


def balances_at(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    period_keys: Mapping[UUID, PeriodRef | None],
    cutoff: datetime,
    contract_id: UUID | None = None,
    params: ReportParams | None = None,
    traces: dict[UUID, TracedBalances] | None = None,
    locked_ends: LockedEnds | None = None,
) -> tuple[BalanceRow, ...]:
    """Balances at the end of each entity's period of ``period_keys`` (None: zero balances). With
    ``params`` (a report build) the versions are ``versions_for`` — bound ids under a bound run,
    else those read at ``cutoff``, recorded (S15-R-24); without (the dashboard's current reads)
    those read at ``cutoff``. Each contract's rows are those of the version it is read from
    (``read_from``). ``traces`` is the caller's cache of the versions' traced nodes: a
    build that reads several period ends, or the billed amounts beside them, loads each trace
    once.

    With ``locked_ends`` (ENGINE_SPEC_B S15-R-20 rev 1.168; 04 §16.9 rev 1.313 — the contract
    balance roll-forward and ``contract_balances`` alone) a period end that is locked at the
    run's cutoff is the lock's: the ids, the labels and the version of each row stay those read
    at ``cutoff``, the VALUES are the lock's dataset row of the contract, a contract the dataset
    does not hold has no row at that end, and a dataset row of a contract this read does not
    hold is refused by name. Every other caller reads the versions at ``cutoff``."""
    if not entity_ids:
        return ()
    balance = contract_version_balance.c
    version_where = (
        read_from(
            balance.contract_id,
            balance.contract_version_id,
            book_code=book_code,
            cutoff=cutoff,
            only_contract=contract_id,
        )
        if params is None
        else rows_read(
            session,
            params,
            balance.contract_id,
            balance.contract_version_id,
            book_code=book_code,
            cutoff=cutoff,
            only_contract=contract_id,
        )
    )
    statement = (
        select(
            contract_version_balance,
            contract.c.external_id,
            contract.c.customer_id,
            customer.c.name.label("customer_name"),
            legal_entity.c.code.label("entity_code"),
        )
        .select_from(
            contract_version_balance.join(
                contract,
                and_(
                    contract.c.tenant_id == contract_version_balance.c.tenant_id,
                    contract.c.id == contract_version_balance.c.contract_id,
                ),
            )
            .outerjoin(
                customer,
                and_(
                    customer.c.tenant_id == contract.c.tenant_id,
                    customer.c.id == contract.c.customer_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract_version_balance.c.tenant_id,
                    legal_entity.c.id == contract_version_balance.c.entity_id,
                ),
            )
        )
        .where(version_where, contract_version_balance.c.entity_id.in_(list(entity_ids)))
        .order_by(contract.c.external_id, legal_entity.c.code)
    )
    if contract_id is not None:
        statement = statement.where(contract_version_balance.c.contract_id == contract_id)
    rows = [dict(row) for row in session.execute(statement).mappings()]
    if traces is None:
        traces = {}
    found: list[BalanceRow] = []
    unreadable: list[ProblemError] = []
    stated: dict[UUID, set[str]] = {}  # per entity, the contracts read from its lock's dataset
    for row in rows:
        version_id = UUID(str(row["contract_version_id"]))
        if version_id not in traces:
            traces[version_id] = _balance_nodes(session, version_id)
        entity_id = UUID(str(row["entity_id"]))
        # frps3c-1 (Codex 8ede60b7 R1): the entity code is consumed by ENTITY ID — the retained
        # code under a binding, the joined current code (recorded) on a live build — and that
        # consumed code drives the trace subject key and the row identity, never the current
        # column.
        code = (
            str(row["entity_code"])
            if params is None
            else entity_code_for(params, entity_id, str(row["entity_code"]))
        )
        at = period_keys.get(entity_id)
        values: dict[str, Decimal] = {}
        end = None if at is None or locked_ends is None else locked_ends.at(entity_id, at)
        if end is not None:
            # S15-R-20 rev 1.168: the end is locked at the run's cutoff — the lock's row
            external_id = str(row["external_id"])
            locked_row = end.rows.get(external_id)
            if locked_row is None:
                continue  # the lock's dataset does not hold the contract: no row at that end
            stated.setdefault(entity_id, set()).add(external_id)
            values = dict(locked_row.values)
        elif at is not None:
            try:
                values = period_balances(
                    traces[version_id],
                    external_id=str(row["external_id"]),
                    entity_code=code,
                    period_key=at.key,
                    stored=row,
                    version_id=version_id,
                )
            except BalanceUnreadable as refused:
                unreadable.extend(refused.errors)  # S15-R-07a: every member named, none served
                continue
        found.append(
            BalanceRow(
                contract_id=UUID(str(row["contract_id"])),
                external_id=str(row["external_id"]),
                customer_name=_customer_name(params, row),
                entity_id=entity_id,
                entity_code=code,
                currency=str(row["txn_currency"]).strip(),
                version_id=version_id,
                values=values,
            )
        )
    if unreadable:
        raise BalanceUnreadable(unreadable)
    if locked_ends is not None and contract_id is None:
        # every row of a lock's dataset is a contract of this read; an entity without a row
        # above is resolved here too, so that the run records every end it asked
        for entity_id in entity_ids:
            at = period_keys.get(entity_id)
            end = None if at is None else locked_ends.at(entity_id, at)
            if at is None or end is None:
                continue
            missing = sorted(set(end.rows) - stated.get(entity_id, set()))
            if missing:
                raise locked_ends.unknown(entity_id, at, missing[0])
    # the SQL ordered by the CURRENT code; the consumed code orders the rows a build sees
    found.sort(key=lambda item: (item.external_id, item.entity_code))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class TracedBalances:
    """The member-balance period nodes of one contract version's trace (stage 10 / 11; T-ENG-03):
    ``nodes`` maps ``<measure>:<subject>`` to its (period key, value) pairs in period order, and
    ``latest`` each subject to the last period key any of its balance nodes carries — the period
    the stored ``contract_version_balance`` row holds. ``billed`` maps each subject to the
    (period key, value) pairs of its ``billed_unconditional_cum`` nodes (S10-R-08)."""

    nodes: Mapping[str, tuple[tuple[str, str], ...]]
    latest: Mapping[str, str]
    billed: Mapping[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)


def traced_balances(node_values: Iterable[tuple[str, str]]) -> TracedBalances:
    """``TracedBalances`` of a trace's (node id, value) pairs: the ``BALANCE_MEASURES`` nodes whose
    subject is a ``<contract>@<entity>`` key, grouped by measure and subject. Period keys sort in
    period order. Pure."""
    found: dict[str, list[tuple[str, str]]] = {}
    latest: dict[str, str] = {}
    billed: dict[str, list[tuple[str, str]]] = {}
    for node_id, value in node_values:
        measure, _, rest = node_id.partition(":")
        if "@" not in rest:
            continue
        subject, _, period_key = rest.rpartition(":")
        if measure == BILLED_UNCONDITIONAL:
            billed.setdefault(subject, []).append((period_key, value))
            continue
        if measure not in BALANCE_MEASURES:
            continue
        found.setdefault(f"{measure}:{subject}", []).append((period_key, value))
        if period_key > latest.get(subject, ""):
            latest[subject] = period_key
    return TracedBalances(
        nodes={key: tuple(sorted(pairs)) for key, pairs in found.items()},
        latest=latest,
        billed={key: tuple(sorted(pairs)) for key, pairs in billed.items()},
    )


def billed_through(
    traced: TracedBalances, *, external_id: str, entity_code: str, period_key: str | None
) -> Decimal:
    """The billing the engine counts in the position of one member contract and entity through
    the end of ``period_key`` (ENGINE_SPEC_B S10-R-08 B_u, node ``billed_unconditional_cum``),
    read as S15-R-07a reads a balance: the value of the latest period node at or before the
    period, 0 before the first node and for no period at all (the period before an entity's
    first). A subject without a node has no billing the engine counted: 0. Pure."""
    value = ZERO
    if period_key is None:
        return value
    subject = contract_entity_subject_key(external_id, entity_code)
    for node_period, amount in traced.billed.get(subject, ()):
        if node_period > period_key:
            break
        value = Decimal(amount)
    return value


def _balance_nodes(session: Session, version_id: UUID) -> TracedBalances:
    """The member-balance nodes of the version's stored trace (none when it has no trace)."""
    trace = store.load_trace(session, version_id)
    return traced_balances(() if trace is None else ((node.id, node.value) for node in trace.nodes))


class BalanceUnreadable(Problem):
    """ENGINE_SPEC_B S15-R-07a (R-16): the named refusal of period balances a version's trace
    cannot answer — 422 ``validation-failed`` with one error per member contract and entity, each
    carrying rule ``S15-R-07a`` and naming the contract, the entity, the contract version and the
    period. No figure is served in place of the balance."""

    def __init__(self, errors: Sequence[ProblemError]) -> None:
        count = len(errors)
        super().__init__(
            "validation-failed",
            "1 field needs attention." if count == 1 else f"{count} fields need attention.",
            errors=errors,
        )


def _unreadable(
    template: str, *, external_id: str, entity_code: str, **facts: object
) -> BalanceUnreadable:
    message = template.format(external_id=external_id, entity_code=entity_code, **facts)
    return BalanceUnreadable(
        [
            ProblemError(
                field=f"balances[{external_id}@{entity_code}]",
                rule_id=RULE_PERIOD_BALANCE,
                message=message,
            )
        ]
    )


def period_balances(
    traced: TracedBalances,
    *,
    external_id: str,
    entity_code: str,
    period_key: str,
    stored: Mapping[str, Any],
    version_id: object,
) -> dict[str, Decimal]:
    """Every ``BALANCE_MEASURES`` balance of one member contract and entity at the end of
    ``period_key``, read from its version's ``traced`` nodes under the engine's subject key
    (``contract_entity_subject_key``: both components CV-21-encoded), or refused by name
    (``BalanceUnreadable``; module docstring; ENGINE_SPEC_B S15-R-07a). ``stored`` is the version's
    ``contract_version_balance`` row — the balances at its latest period. Pure."""
    subject = contract_entity_subject_key(external_id, entity_code)
    latest = traced.latest.get(subject)
    if latest is None:
        raise _unreadable(
            BALANCE_SUBJECT_UNTRACED,
            external_id=external_id,
            entity_code=entity_code,
            version_id=version_id,
            subject=subject,
            period_key=period_key,
        )
    values: dict[str, Decimal] = {}
    for measure in BALANCE_MEASURES:
        nodes = traced.nodes.get(f"{measure}:{subject}")
        if nodes:
            value = ZERO  # a period before the first node: nothing measured yet
            for node_period, amount in nodes:
                if node_period > period_key:
                    break
                value = Decimal(amount)
            values[measure] = value
            continue
        # no period node: a measure the engine does not publish per member contract — its stored
        # column is the version's latest period, the T-CON-09 default 0 unless something wrote it
        held = stored.get(f"{measure}_txn")
        amount_held = ZERO if held is None else Decimal(held)
        if amount_held != 0 and period_key < latest:
            currency = str(stored.get("txn_currency") or "").strip()
            raise _unreadable(
                BALANCE_MEASURE_UNTRACED,
                external_id=external_id,
                entity_code=entity_code,
                version_id=version_id,
                subject=subject,
                period_key=period_key,
                measure=measure,
                amount=quantized(amount_held, currency) if currency in ISO_4217 else amount_held,
                currency=currency,
                latest_period_key=latest,
            )
        values[measure] = amount_held
    return values


def _journal_run_membership(
    session: Session,
    params: ReportParams | None,
    known_at: datetime,
    *,
    scope: Sequence[ColumnElement[bool]],
) -> list[ColumnElement[bool]]:
    """The journal runs a revenue tie-out sums: bound ids under a bound run; else the live rule
    (not cancelled, created by ``known_at``, whatever the run's mode: supervisor ruling R-52 (a))
    — whose CONTRIBUTING run ids a live build records so its reruns sum the same runs (S15-R-24 /
    Codex 2154). The capture carries the SAME ``scope`` predicates as the sum (book, entities,
    periods; Codex 2245 (c)): a recorded member is a run whose revenue lines are in the summed
    population — an eligible run of another period or book is a candidate, not a contributor, and
    is not recorded."""
    if params is not None and params.binding is not None:
        return bound_member_where(params, "journal_run", journal_run.c.id)
    live = [journal_run.c.state != CANCELLED_RUN, journal_run.c.created_at <= known_at]
    if params is not None and params.sources is not None:
        consumed = session.execute(
            select(journal_run.c.id)
            .select_from(
                journal_run.join(
                    journal_batch,
                    and_(
                        journal_batch.c.tenant_id == journal_run.c.tenant_id,
                        journal_batch.c.journal_run_id == journal_run.c.id,
                    ),
                ).join(
                    journal_line,
                    and_(
                        journal_line.c.tenant_id == journal_batch.c.tenant_id,
                        journal_line.c.journal_batch_id == journal_batch.c.id,
                    ),
                )
            )
            .where(journal_line.c.account_role == REVENUE, *scope, *live)
            .distinct()
        ).scalars()
        record_members(params, "journal_run", consumed)
    return live


def journal_revenue(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    period_ids: Iterable[UUID],
    known_at: datetime,
    params: ReportParams | None = None,
) -> dict[str, Decimal]:
    """Σ credit − debit of the ``REVENUE`` journal lines of every run not cancelled, whatever its
    mode, per currency. Supervisor ruling R-52 (a) supersedes D-87 L6-3-Q-32 (only the runs of the
    entity's POL-005 posting mode): since DB-16 keys journal coverage on entity, book and period
    alone (04 rev 1.106, revision 0085; security finding SC-7) a seal is journalised by one run
    only, so nothing can count twice, and a run requested in the other mode journalises seals no
    other run covers. The LEGACY lines a ``DELTA`` run adds carry the role ``PRE_STANDARD_REVENUE``
    (JET-15; D-89 L7-6-Q-8) and never enter this sum. With ``params`` (S15-R-24 / Codex 2154) the
    journal-run MEMBERSHIP is bound: a bound run sums exactly the runs the original consumed (a
    later cancellation cannot move the tie-out); a live build records the run ids it consumed."""
    ids = sorted(set(period_ids), key=str)
    if not entity_ids or not ids:
        return {}
    # The summed population's scope — the ONE list both the sum and the membership capture apply.
    scope: list[ColumnElement[bool]] = [
        journal_line.c.book_code == book_code,
        journal_line.c.entity_id.in_(list(entity_ids)),
        journal_line.c.period_id.in_(ids),
    ]
    statement = (
        select(
            journal_line.c.txn_currency,
            func.sum(journal_line.c.credit_txn - journal_line.c.debit_txn),
        )
        .select_from(
            journal_line.join(
                journal_batch,
                and_(
                    journal_batch.c.tenant_id == journal_line.c.tenant_id,
                    journal_batch.c.id == journal_line.c.journal_batch_id,
                ),
            ).join(
                journal_run,
                and_(
                    journal_run.c.tenant_id == journal_batch.c.tenant_id,
                    journal_run.c.id == journal_batch.c.journal_run_id,
                ),
            )
        )
        .where(
            journal_line.c.account_role == REVENUE,
            *scope,
            *_journal_run_membership(session, params, known_at, scope=scope),
        )
        .group_by(journal_line.c.txn_currency)
    )
    return {
        str(currency).strip(): Decimal(total)
        for currency, total in session.execute(statement).tuples()
        if total is not None
    }
