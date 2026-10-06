"""RPT-16 ``out_of_period_register`` Out-of-period register (SCREENS_B §5.6.3 RPT-16; ENGINE_SPEC_B
§15.2.7 ``OUT_OF_PERIOD_REGISTER``, S15-R-18a, S15-R-18b, S14-R-13a; 04 T-CLS-05, T-SL-12, E-64,
E-87; 03 REQ-CLS-004, REQ-CLS-006, REQ-PLT-030; D-19; POL-180; D-98 candidates 85, 95, 96, 102;
BUILD_SPEC RPS-5).

One row per attribution whose effect posted in a period other than the period of its effective
date — the subledger lines carrying an ``origin_period_id`` that differs from their posting
``period_id``, each attributed exactly once and aggregated per (origin period, posting period,
attribution key) — with the frozen-dataset column shape of S15-R-18a: the key code columns first
(``origin_period_key``, ``posting_period_key``, ``event_key``; F-CLO's KeySpec names, D-98 85),
then ``attribution_kind``, ``lineage_scope`` and the other code and measure columns, and the display
attributes last
(``event_type_label``, ``recorded_by``).

Attribution (S15-R-18b; Codex C6-RPT-R3; D-98 102 Q1). ``EVENT_SET``: a line's single
``contract_event_id`` when set, else the T-SL-12 ``subledger_line_event`` rows of its cumulative
delta in set order (S14-R-13a); ``event_key`` = ``event:<contract external id>:<stream version>``
per member, joined with ``|`` for a set of several — every member a stored identity, never a proxy
tuple of contract, type and date (two events of one contract, type and date are two rows).
An ``EVENT_SET`` row carries ``lineage_scope``: ``SUBJECT`` when the set holds an event of the
line's single-member subject (``dimensions.contract_key``) or the subject has several members,
``GROUP`` when it is the group's first-included events taken because the subject's own were empty
(S14-R-13a; D-98 candidate 102b — a combination group is one allocation unit). The scope is part
of the row identity (D-98 candidate 102c): the string ``event_key`` ends with the encoded scope
(``…:SUBJECT`` / ``…:GROUP``) and the aggregation key carries it, so one event set's
SUBJECT and GROUP populations are two rows with distinct stable identities whatever the input
order; line count and monetary conservation hold across the split. ``TRIGGER``: a line
of a computation with no first-included event for the whole group, keyed
``trigger:<E-87 trigger code>:<contract_computation id>`` in place of the event set, carrying the
trigger's label, the computation's ``created_at`` as its recording time, its creating actor and
the line's contract — only on persisted, subject-specific proof (D-98 candidate 102a; Codex packet
1130; 102b): the computation's stored ``contract_version.cause_event_ids`` of the book is empty
(``cause_event_count == 0``, read by ``build``) AND the computation's trigger is a non-event
trigger (``POLICY_RERUN``, ``FX_REPUBLISH``, ``RESTATE``); an empty T-SL-12 set without that proof
— an event-driven trigger, a computation with first-included events, or a proof the reader could
not establish — is missing lineage and refuses, so a NULL-event cumulative line persisted before
T-SL-12 refuses as Q2 requires. The identity of an attribution is the structural
tuple of its typed
components; its single-string form (``event_key``, the CSV cell) percent-encodes
every component before joining — the CV-21 table (``%`` first, then ``/`` ``@`` ``#`` ``:``) and
the set delimiter ``|`` → ``%7C`` — so a contract external id containing a delimiter cannot make
two sets one key (D-98 candidate 104; Codex C6-RPT-R5; no identifier is prohibited).

Row key (S15-R-18a rev 1.110; SCREENS_B RPT-16 rev 1.46; item RPT-OOP-ROWKEY-1, supervisor ruling
R-112 (j)). A row is one (origin period, posting period, attribution), and its ``row_key`` — the
row's identity in a run and the S15-R-18 sort key of the frozen file — is the single-string form
of all three: ``<origin period key>:<posting period key>:<event key>``, the period keys encoded
as every other component (``row_key``). The event key alone repeats: a contract booked after
several of its periods were closed posts each closed month into the first open period with its
own origin, so one event set has a row per origin period; with the event key as ``row_key`` those
rows formed no dataset and the lock of the posting period was refused (``duplicate row_key``).

Each line enters exactly one row, so the effects are conserved across both
kinds: per currency Σ ``revenue_effect`` and Σ ``balance_effect`` equal the credit-positive sums of
the selected lines, and ``line_count`` counts the lines. A multi-event row carries the members'
distinct codes joined with ``|`` in set order, its ``effective_date`` and ``recorded_by`` only when
every member agrees, and ``recorded_at`` = the latest member's; the latest event alone is never
assigned. A selected line with neither an event set nor a computation is refused by name
(``OUT_OF_PERIOD_ATTRIBUTION_MISSING``, one error per line) — never omitted; a line persisted
before T-SL-12 existed is such a line (no backfill before 1.0; D-98 102 Q2).

Recorder and approval (supervisor ruling R-63 (c); ``event_provenance``): an event an import
commit wrote as the ``SYSTEM`` principal shows its upload's uploader as ``recorded_by`` and the
upload's ``IMPORT_COMMIT`` request as ``approval_request_no``; every other event shows its own.

Effects (subledger amounts are signed, debit positive, T-SL-04 ``dr_cr``): [J] ``revenue_effect``
is the credit-positive sum of the set's lines on the revenue roles (``REVENUE``,
``PRE_STANDARD_REVENUE``), so recognised revenue shows positive; ``balance_effect`` is the
credit-positive sum of its lines on the contract-position roles (contract liability, contract
asset, unbilled receivable, deposit, refund and consideration-payable liabilities, return and
incentive assets, loss and warranty provisions), so a contract-liability decrease shows in
parentheses (SCREENS_B RPT-16). Both are typed Money in the line's transaction currency (Codex
C6-RPT-R1). Control totals: ``row_count``, ``line_count`` and per currency ``revenue_effect_total``
/ ``balance_effect_total``. Tie-out: none.

Sources (S15-R-18b; REQ-PLT-030; C6-RPT-R4): lines recorded by the run's ``known_at``; a
``period_lock_id`` source is refused by name until the framework's lock-snapshot branch lands
(CLO-8). ``aggregate`` / ``rows_from`` and ``control_totals`` are pure over flat line records so
the shape, the attribution and the refusal are CPU-testable; ``build`` reads the lines and their
event sets through the unit of work.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import (
    approval_request,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    period,
    subledger_line,
    subledger_line_event,
    subledger_posting,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, event_provenance
from erev_api.domain.reports.builders.je_population import LOCKED_SOURCE_PENDING
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

CODE: Final = "out_of_period_register"
ATTRIBUTION_MISSING: Final = "OUT_OF_PERIOD_ATTRIBUTION_MISSING"
EVENT_SET: Final = "EVENT_SET"
TRIGGER: Final = "TRIGGER"
SUBJECT: Final = "SUBJECT"
GROUP: Final = "GROUP"
# E-87 triggers that recompute without a new event (D-98 102a): the only ones a TRIGGER row may
# name.
NON_EVENT_TRIGGERS: Final = frozenset({"POLICY_RERUN", "FX_REPUBLISH", "RESTATE"})
# S15-R-18b rev 1.166 (item FX-REPUBLISH-DIRTY-1; the supervisor's ruling of 2026-10-02): the
# republication of a rate moves functional amounts only, so its trigger attributes a line only
# when the line's transaction amount is nil.
FUNCTIONAL_ONLY_TRIGGERS: Final = frozenset({"FX_REPUBLISH"})
JOINER: Final = "|"
# CV-21 percent-encoding of a key component (ENGINE_SPEC CV-21: ``%`` first, then ``/`` ``@`` ``#``
# ``:``) plus the set delimiter ``|`` (D-98 candidate 104), applied before any join.
ENCODED: Final = (
    ("%", "%25"),
    ("/", "%2F"),
    ("@", "%40"),
    ("#", "%23"),
    (":", "%3A"),
    ("|", "%7C"),
)
LABEL_JOINER: Final = " | "
# S15-R-18a: the row key as code columns first (F-CLO KeySpec).
KEY_COLUMNS: Final = ("origin_period_key", "posting_period_key", "event_key")
COLUMNS: Final = (
    Column("origin_period_key", "Origin period", "code"),
    Column("posting_period_key", "Posting period", "code"),
    Column("event_key", "Event key", "code"),
    Column("attribution_kind", "Attribution", "code"),  # EVENT_SET | TRIGGER (D-98 102 Q1)
    Column("lineage_scope", "Lineage", "code"),  # SUBJECT | GROUP, null on a trigger row (102b)
    Column("contract_external_id", "Contract", "code"),
    Column("event_type", "Event", "code"),
    Column("effective_date", "Effective date", "date"),
    Column("recorded_at", "Recorded", "timestamp"),
    Column("reason_code", "Reason", "code"),
    Column("origin", "Origin", "code"),
    Column("currency", "Currency", "code"),
    Column("revenue_effect", "Revenue effect", "money"),
    Column("balance_effect", "Balance effect", "money"),
    Column("approval_request_no", "Approval", "code"),
    # attributes (display labels; never key)
    Column("event_type_label", "Event", "text"),
    Column("recorded_by", "Recorded by", "actor"),
)
REVENUE_ROLES: Final = frozenset({"REVENUE", "PRE_STANDARD_REVENUE"})
POSITION_ROLES: Final = frozenset(
    {
        "CONTRACT_LIABILITY",
        "CONTRACT_ASSET",
        "UNBILLED_RECEIVABLE",
        "DEPOSIT_LIABILITY",
        "REFUND_LIABILITY",
        "CONSIDERATION_PAYABLE",
        "RETURN_ASSET",
        "CUSTOMER_INCENTIVE_ASSET",
        "LOSS_PROVISION",
        "WARRANTY_PROVISION",
    }
)
# The members of one event of a set (a flat single-event line carries them at the top level).
EVENT_FIELDS: Final = (
    "contract_external_id",
    "stream_version",
    "event_type",
    "effective_date",
    "recorded_at",
    "origin",
    "approval_request_no",
    "recorded_by",
)
ZERO: Final = Decimal(0)


@dataclass(frozen=True, slots=True)
class Aggregation:
    """The register rows and the number of subledger lines they attribute (conservation)."""

    rows: tuple[dict[str, Any], ...]
    line_count: int


@dataclass(frozen=True, slots=True)
class Attribution:
    """One line's attribution (S15-R-18b): its event set, or its computation's trigger."""

    kind: str  # EVENT_SET | TRIGGER
    events: tuple[Mapping[str, Any], ...] = ()
    trigger: str | None = None
    computation_id: str | None = None
    scope: str | None = None  # SUBJECT | GROUP for an event set (D-98 102b); None for a trigger

    @property
    def identity(self) -> tuple[Any, ...]:
        """The structural identity (D-98 104): typed components, never a joined string; the
        lineage scope is part of it (D-98 102c), so one event set's SUBJECT and GROUP populations
        are two identities."""
        if self.kind == TRIGGER:
            return (TRIGGER, str(self.trigger), str(self.computation_id))
        return (
            EVENT_SET,
            tuple(
                (str(event["contract_external_id"]), int(event["stream_version"]))
                for event in self.events
            ),
            str(self.scope),
        )

    @property
    def key(self) -> str:
        """The single-string form: every component CV-21-encoded before joining (injective); an
        event set's key ends with its encoded lineage scope (``…:SUBJECT`` / ``…:GROUP``; D-98
        102c), a trigger row's key has no scope component."""
        if self.kind == TRIGGER:
            trigger = encode_component(str(self.trigger))
            computation = encode_component(str(self.computation_id))
            return f"trigger:{trigger}:{computation}"
        members = JOINER.join(
            event_key(str(event["contract_external_id"]), int(event["stream_version"]))
            for event in self.events
        )
        return f"{members}:{encode_component(str(self.scope))}"


def refuse_locked_source(params: ReportParams) -> None:
    """S15-R-18b / REQ-PLT-030: a ``period_lock_id`` source is refused by name until the framework
    reads lock snapshots (CLO-8)."""
    if params.period_lock_id is not None:
        raise tie_outs.invalid("period_lock_id", LOCKED_SOURCE_PENDING)


def encode_component(component: str) -> str:
    """CV-21 percent-encoding of one key component plus ``|`` → ``%7C`` (D-98 candidate 104):
    ``%`` first so the result decodes uniquely; every other character is kept."""
    for plain, encoded in ENCODED:
        component = component.replace(plain, encoded)
    return component


def event_key(contract_external_id: str, stream_version: int) -> str:
    """``event:<external id>:<stream version>`` with the id CV-21-encoded (SCREENS_B RPT-16; D-98
    85, D-98 104); a plain id such as ``K-01`` is unchanged."""
    return f"event:{encode_component(contract_external_id)}:{int(stream_version)}"


def row_key(origin_period_key: str, posting_period_key: str, attribution_key: str) -> str:
    """The single-string form of a row's whole key (S15-R-18a rev 1.110): the origin and the
    posting period key, each CV-21-encoded, then the attribution's key — an event key or a
    trigger key, encoded component by component already — joined with ``:``. Injective: an
    encoded period key holds no ``:``, so the first two fields are the periods and the rest is
    the attribution's key."""
    origin, posting = encode_component(origin_period_key), encode_component(posting_period_key)
    return f"{origin}:{posting}:{attribution_key}"


def event_type_label(event_type: str) -> str:
    """The E-03 display label ("Billing recorded", "Contract voided", …)."""
    return event_type.replace("_", " ").capitalize()


def trigger_label(trigger: str) -> str:
    """The E-87 display label ("Policy rerun", "Fx republish", …)."""
    return trigger.replace("_", " ").capitalize()


def attribution(line: Mapping[str, Any]) -> Attribution | None:
    """The attribution of a flat line record (S15-R-18b; D-98 102 Q1, 102a, 102b): its ``events``
    (the T-SL-12 set of a cumulative delta, in set order) when present and non-empty — scope
    ``SUBJECT`` when the set holds an event of the line's single-member subject
    (``subject_contract_external_id``, the line's ``dimensions.contract_key``) or the subject has
    several members, ``GROUP`` when it is the group's set taken because the subject's own was empty
    — else the single event carried at the top level (``stream_version`` set; ``SUBJECT``), else
    its computation's trigger, only with persisted proof: ``cause_event_count`` read as exactly 0
    (the computation's stored lineage is empty for the whole group) and a non-event ``trigger`` —
    and, under ``FX_REPUBLISH``, only for a line whose transaction amount is nil (rev 1.166: a
    republished rate moves the functional amount alone, so a line that moves a transaction
    amount under that trigger was not made by the republication) — else None, the
    missing-lineage case."""
    events = line.get("events")
    if events:
        members = tuple(events)
        subject = line.get("subject_contract_external_id")
        own = subject is None or any(
            str(event["contract_external_id"]) == str(subject) for event in members
        )
        return Attribution(EVENT_SET, events=members, scope=SUBJECT if own else GROUP)
    if line.get("stream_version") is not None:
        return Attribution(
            EVENT_SET,
            events=({name: line.get(name) for name in EVENT_FIELDS},),
            scope=SUBJECT,
        )
    trigger = line.get("trigger")
    if (
        trigger is not None
        and line.get("computation_id") is not None
        and str(trigger) in NON_EVENT_TRIGGERS
        and line.get("cause_event_count") == 0
        and (
            str(trigger) not in FUNCTIONAL_ONLY_TRIGGERS
            or Decimal(str(line.get("amount_txn") or ZERO)) == ZERO
        )
    ):
        return Attribution(
            TRIGGER, trigger=str(trigger), computation_id=str(line["computation_id"])
        )
    return None


def attribution_missing(lines: Sequence[Mapping[str, Any]]) -> Problem:
    """The named refusal of S15-R-18b: one error per line with neither an event set nor a
    computation (a line persisted before T-SL-12 among them; D-98 102 Q2)."""
    errors = [
        ProblemError(
            field="rows",
            rule_id=ATTRIBUTION_MISSING,
            message=(
                f"subledger line {line.get('line_id')}: origin {line.get('origin_period_key')}, "
                f"posting {line.get('posting_period_key')}, reason {line.get('reason_code')}, "
                f"contract {line.get('contract_external_id')} carries no source event "
                "(S15-R-18b)"
            ),
        )
        for line in lines
    ]
    return Problem(
        "validation-failed",
        f"{len(lines)} out-of-period subledger line(s) carry no source event attribution "
        "(S15-R-18b).",
        errors=errors,
    )


def aggregate(lines: Iterable[Mapping[str, Any]]) -> Aggregation:
    """One row per (origin period, posting period, event set) from flat subledger-line records;
    each line enters exactly one row (conservation), the effects are summed per row and the reason
    codes joined with ``|`` in code order; the rows' ``row_key`` carries the three (``row_key``),
    so no two rows share one. Lines with no attribution refuse the whole run by name."""
    grouped: dict[tuple[str, str, str, tuple[Any, ...]], dict[str, Any]] = {}
    totals: dict[tuple[str, str, str, tuple[Any, ...]], list[Decimal]] = {}
    reasons: dict[tuple[str, str, str, tuple[Any, ...]], set[str]] = {}
    missing: list[Mapping[str, Any]] = []
    count = 0
    for line in lines:
        count += 1
        found = attribution(line)
        if found is None:
            missing.append(line)
            continue
        origin_key = str(line["origin_period_key"])
        posting_key = str(line["posting_period_key"])
        key_value = found.key
        # grouped by the structural identity (D-98 104); the encoded key orders the rows
        key = (origin_key, posting_key, key_value, found.identity)
        if key not in grouped:
            grouped[key] = (
                _row(origin_key, posting_key, key_value, found, line)
                if found.kind == EVENT_SET
                else _trigger_row(origin_key, posting_key, found, line)
            )
            totals[key] = [ZERO, ZERO]
            reasons[key] = set()
        role = str(line.get("account_role") or "")
        amount = Decimal(str(line.get("amount_txn") or ZERO))
        if role in REVENUE_ROLES:
            totals[key][0] -= amount  # credit-positive
        if role in POSITION_ROLES:
            totals[key][1] -= amount  # credit-positive: a liability decrease is negative
        reason = line.get("reason_code")
        if reason:
            reasons[key].add(str(reason))
    if missing:
        raise attribution_missing(missing)
    rows: list[dict[str, Any]] = []
    for key in sorted(grouped):
        row = grouped[key]
        currency = str(row["currency"])
        row["revenue_effect"] = tie_outs.money(totals[key][0], currency)
        row["balance_effect"] = tie_outs.money(totals[key][1], currency)
        row["reason_code"] = JOINER.join(sorted(reasons[key]))
        rows.append(row)
    return Aggregation(rows=tuple(rows), line_count=count)


def rows_from(lines: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """The rows of ``aggregate``."""
    return aggregate(lines).rows


def _row(
    origin_key: str,
    posting_key: str,
    key_value: str,
    found: Attribution,
    line: Mapping[str, Any],
) -> dict[str, Any]:
    """The identity and attribute cells of a row: a singleton set is the event row; a set of
    several carries the members' distinct codes joined in set order, a date or actor only when
    every member agrees, and the latest recording time (S15-R-18b)."""
    events = found.events
    types = _distinct(str(event["event_type"]) for event in events)
    recorded: list[datetime] = [
        event["recorded_at"] for event in events if event.get("recorded_at") is not None
    ]
    return {
        "row_key": row_key(origin_key, posting_key, key_value),
        "origin_period_key": origin_key,
        "posting_period_key": posting_key,
        "event_key": key_value,
        "attribution_kind": EVENT_SET,
        "lineage_scope": found.scope,
        "contract_external_id": JOINER.join(
            _distinct(str(event["contract_external_id"]) for event in events)
        ),
        "event_type": JOINER.join(types),
        "effective_date": _unanimous(event.get("effective_date") for event in events),
        "recorded_at": max(recorded) if recorded else None,
        "reason_code": "",
        "origin": _joined(event.get("origin") for event in events),
        "currency": str(line["txn_currency"]).strip(),
        "revenue_effect": None,
        "balance_effect": None,
        "approval_request_no": _joined(event.get("approval_request_no") for event in events),
        "event_type_label": LABEL_JOINER.join(event_type_label(item) for item in types),
        "recorded_by": _unanimous(event.get("recorded_by") for event in events),
    }


def _trigger_row(
    origin_key: str, posting_key: str, found: Attribution, line: Mapping[str, Any]
) -> dict[str, Any]:
    """The identity and attribute cells of a TRIGGER row (D-98 102 Q1): the computation's trigger
    and id in place of the event set, its ``created_at`` as the recording time, its creating actor,
    the line's contract; no event type, date, origin or approval is manufactured."""
    trigger = str(found.trigger)
    return {
        "row_key": row_key(origin_key, posting_key, found.key),
        "origin_period_key": origin_key,
        "posting_period_key": posting_key,
        "event_key": found.key,
        "attribution_kind": TRIGGER,
        "lineage_scope": None,
        "contract_external_id": _text(line.get("contract_external_id")),
        "event_type": None,
        "effective_date": None,
        "recorded_at": line.get("computation_created_at"),
        "reason_code": "",
        "origin": None,
        "currency": str(line["txn_currency"]).strip(),
        "revenue_effect": None,
        "balance_effect": None,
        "approval_request_no": None,
        "event_type_label": trigger_label(trigger),
        "recorded_by": line.get("computation_recorded_by"),
    }


def _distinct(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _joined(values: Iterable[object]) -> str | None:
    found = _distinct(str(value) for value in values if value is not None)
    return JOINER.join(found) if found else None


def _unanimous(values: Iterable[object]) -> Any:
    """The one value every member carries, else None (never a proxy of one member)."""
    found = [value for value in values if value is not None]
    if not found or any(value != found[0] for value in found[1:]):
        return None
    return found[0]


def control_totals(
    rows: Sequence[Mapping[str, Any]], *, line_count: int | None = None
) -> dict[str, Any]:
    """``row_count``, the per-currency effect totals and, when the caller aggregated the lines
    (``Aggregation.line_count``; ``build`` always does), ``line_count`` (S15-R-18a rev 1.25). Over
    rows alone the count of aggregated lines is not derivable, so a rows-only call carries the
    rev 1.24 keys unchanged (Codex's frozen totals control)."""
    revenue: dict[str, Decimal] = {}
    balance: dict[str, Decimal] = {}
    for row in rows:
        currency = str(row["currency"])
        tie_outs.add(revenue, currency, Decimal(str(row["revenue_effect"]["amount"])))
        tie_outs.add(balance, currency, Decimal(str(row["balance_effect"]["amount"])))
    totals: dict[str, Any] = {"row_count": len(rows)}
    if line_count is not None:
        totals["line_count"] = int(line_count)
    totals["revenue_effect_total"] = tie_outs.by_currency(revenue)
    totals["balance_effect_total"] = tie_outs.by_currency(balance)
    return totals


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found = tie_outs.entities(session, params.entity_ids)
    calendars = tie_outs.calendars(session, found)
    posting_ids: list[UUID] = []
    origin_ids: list[UUID] = []
    origin_key = params.parameters.get("origin_period_key")
    for entity in found:
        calendar = calendars[entity.id]
        for item in tie_outs.range_of(params, calendar, entity):
            posting_ids.append(item.id)
        if origin_key is not None:
            origin_ids.append(calendar.named(str(origin_key), "origin_period_key").id)
    records: list[dict[str, Any]] = []
    if found and posting_ids:
        tenant_id = subledger_line.c.tenant_id
        origin = period.alias("origin_period")
        joined = (
            subledger_line.join(
                contract,
                and_(
                    contract.c.tenant_id == tenant_id, contract.c.id == subledger_line.c.contract_id
                ),
            )
            .join(
                period,
                and_(period.c.tenant_id == tenant_id, period.c.id == subledger_line.c.period_id),
            )
            .join(
                origin,
                and_(
                    origin.c.tenant_id == tenant_id,
                    origin.c.id == subledger_line.c.origin_period_id,
                ),
            )
            # S15-R-18b: the single source event when the line carries one; a cumulative line
            # carries none here and is attributed through its T-SL-12 set below.
            .outerjoin(
                contract_event,
                and_(
                    contract_event.c.tenant_id == tenant_id,
                    contract_event.c.id == subledger_line.c.contract_event_id,
                ),
            )
            .outerjoin(
                approval_request,
                and_(
                    approval_request.c.tenant_id == tenant_id,
                    approval_request.c.id == contract_event.c.approval_request_id,
                ),
            )
            # D-98 102 Q1: the computation behind a line with no first-included event of its
            # subject attributes the line to its trigger.
            .join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
            .outerjoin(
                contract_computation,
                and_(
                    contract_computation.c.tenant_id == tenant_id,
                    contract_computation.c.id == subledger_posting.c.contract_computation_id,
                ),
            )
        )
        statement = (
            select(
                subledger_line.c.id.label("line_id"),
                subledger_line.c.period_end_date,
                subledger_line.c.contract_id,
                subledger_line.c.dimensions,
                contract_computation.c.id.label("computation_id"),
                contract_computation.c.trigger,
                contract_computation.c.created_at.label("computation_created_at"),
                contract_computation.c.created_by.label("computation_created_by"),
                contract_computation.c.created_by_kind.label("computation_created_by_kind"),
                origin.c.period_key.label("origin_period_key"),
                period.c.period_key.label("posting_period_key"),
                contract.c.external_id.label("contract_external_id"),
                contract_event.c.stream_version,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.recorded_at,
                contract_event.c.origin,
                contract_event.c.created_by,
                contract_event.c.created_by_kind,
                contract_event.c.import_upload_id,
                subledger_line.c.reason_code,
                subledger_line.c.account_role,
                subledger_line.c.txn_currency,
                subledger_line.c.amount_txn,
                approval_request.c.request_no.label("approval_request_no"),
            )
            .select_from(joined)
            .where(
                subledger_line.c.book_code == book_code,
                subledger_line.c.entity_id.in_([entity.id for entity in found]),
                subledger_line.c.period_id.in_(posting_ids),
                subledger_line.c.origin_period_id.is_not(None),
                subledger_line.c.origin_period_id != subledger_line.c.period_id,
                subledger_line.c.recorded_at <= params.known_at,
            )
        )
        if origin_ids:
            statement = statement.where(subledger_line.c.origin_period_id.in_(origin_ids))
        rows = [dict(row) for row in session.execute(statement).mappings()]
        cumulative = [UUID(str(row["line_id"])) for row in rows if row["stream_version"] is None]
        sets = _event_sets(session, cumulative)
        # R-63 (c): an event an import commit wrote names its upload's uploader and approval —
        # the single source events and the members of every set, from one read of the uploads.
        uploads = event_provenance.uploads(
            session, [*rows, *(event for members in sets.values() for event in members)]
        )
        rows = event_provenance.resolved(rows, uploads)
        sets = {
            line_id: tuple(event_provenance.resolved(members, uploads))
            for line_id, members in sets.items()
        }
        # D-98 102a / 102b: the persisted proof of a trigger-only delta — the computation's stored
        # lineage (contract_version.cause_event_ids of this book) is empty for the whole group.
        proofs = _cause_event_counts(
            session,
            book_code,
            sorted(
                {
                    UUID(str(row["computation_id"]))
                    for row in rows
                    if row["stream_version"] is None
                    and row["computation_id"] is not None
                    and UUID(str(row["line_id"])) not in sets
                },
                key=str,
            ),
        )
        names = approval_queries.display_names(
            session,
            [row["created_by"] for row in rows]
            + [row["computation_created_by"] for row in rows]
            + [event["created_by"] for members in sets.values() for event in members],
        )
        for row in rows:
            record = dict(row)
            if row["stream_version"] is not None:
                record["recorded_by"] = _actor(record, names)
            else:
                record["events"] = tuple(
                    {**event, "recorded_by": _actor(event, names)}
                    for event in sets.get(UUID(str(row["line_id"])), ())
                )
                dimensions = row["dimensions"] or {}
                record["subject_contract_external_id"] = _text(dimensions.get("contract_key"))
                if row["computation_id"] is not None:
                    record["computation_recorded_by"] = approval_queries.actor(
                        None
                        if row["computation_created_by"] is None
                        else UUID(str(row["computation_created_by"])),
                        str(row["computation_created_by_kind"]),
                        names,
                    )
                    record["cause_event_count"] = proofs.get(UUID(str(row["computation_id"])))
            records.append(record)
    found_rows = aggregate(records)
    return ReportData(
        columns=COLUMNS,
        rows=found_rows.rows,
        control_totals=control_totals(found_rows.rows, line_count=found_rows.line_count),
    )


def _cause_event_counts(
    session: Any, book_code: str, computation_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Per computation: how many first-included events its stored version of the report's book
    records (``contract_version.cause_event_ids``) — the persisted proof a TRIGGER row needs to be 0
    (D-98 102a; 102b: the whole group's lineage, since the subject's set widens to the group's
    before a trigger is considered). A computation without a stored version of this book yields no
    entry (no proof), never a zero."""
    if not computation_ids:
        return {}
    rows = session.execute(
        select(
            contract_version.c.contract_computation_id, contract_version.c.cause_event_ids
        ).where(
            contract_version.c.contract_computation_id.in_(list(computation_ids)),
            contract_version.c.book_code == book_code,
        )
    ).mappings()
    counts: dict[UUID, int] = {}
    for row in rows:
        computation_id = UUID(str(row["contract_computation_id"]))
        counts[computation_id] = counts.get(computation_id, 0) + len(row["cause_event_ids"] or ())
    return counts


def _actor(row: Mapping[str, Any], names: Mapping[UUID, str]) -> dict[str, Any]:
    return approval_queries.actor(
        None if row["created_by"] is None else UUID(str(row["created_by"])),
        str(row["created_by_kind"]),
        names,
    )


def _event_sets(session: Any, line_ids: Sequence[UUID]) -> dict[UUID, tuple[dict[str, Any], ...]]:
    """The T-SL-12 event sets of cumulative lines, each in ``ordinal`` order (S14-R-13a)."""
    if not line_ids:
        return {}
    tenant_id = subledger_line_event.c.tenant_id
    statement = (
        select(
            subledger_line_event.c.subledger_line_id.label("line_id"),
            subledger_line_event.c.ordinal,
            contract.c.external_id.label("contract_external_id"),
            contract_event.c.stream_version,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.recorded_at,
            contract_event.c.origin,
            contract_event.c.created_by,
            contract_event.c.created_by_kind,
            contract_event.c.import_upload_id,
            approval_request.c.request_no.label("approval_request_no"),
        )
        .select_from(
            subledger_line_event.join(
                contract_event,
                and_(
                    contract_event.c.tenant_id == tenant_id,
                    contract_event.c.id == subledger_line_event.c.contract_event_id,
                ),
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == tenant_id, contract.c.id == contract_event.c.contract_id
                ),
            )
            .outerjoin(
                approval_request,
                and_(
                    approval_request.c.tenant_id == tenant_id,
                    approval_request.c.id == contract_event.c.approval_request_id,
                ),
            )
        )
        .where(subledger_line_event.c.subledger_line_id.in_(list(line_ids)))
        .order_by(subledger_line_event.c.subledger_line_id, subledger_line_event.c.ordinal)
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        found.setdefault(UUID(str(row["line_id"])), []).append(dict(row))
    return {line_id: tuple(items) for line_id, items in found.items()}
