"""RPT-09 ``contract_history`` Contract history, and the obligation-version population shared by the
history and latest-status reports (SCREENS_B §5.6.2 RPT-09 to RPT-12; 04 §17.1 rule 1, T-CON-08,
T-CON-11; legacy 06 §7.3 TC-REP-01, TC-REP-02, TC-REP-04 to TC-REP-06; 03 REQ-RPT-012,
REQ-RPT-013, REQ-SEC-006; BUILD_SPEC RPS-5).

Population (``population``): the obligation versions of the book whose contract version the run
can see (``tie_outs.version_cutoff``, L6-3-Q-19) and whose contracting entity is in the run's scope.
With ``contract_external_id`` it keeps that contract, compared as a bound parameter (REQ-SEC-006):
a name that no contract has gives no rows and no error (TC-REP-04, TC-REP-05). Rows are ordered by
contract external id, the version's number along the contract's chain and ``line_sequence`` (04
§17.1 rule 1). The history keeps the versions effective from ``from_date`` to ``to_date``
inclusive; the framework refuses a start after its end with 422 (TC-REP-06).

The number of a version (``chain_numbers``; item RPT-FORMER-GROUP-READERS-1, supervisor ruling
R-117 (a); 04 T-CON-04): ``version_no`` counts the versions of one combination group, so a contract
computed in its own group and combined later holds a version 1 twice — the history listed two rows
under one row key and the Version column read 1, 1. A contract's versions are numbered along its
chain in record order: the versions computed with it during each of its memberships, membership
after membership. For a contract that never changed its group that is the stored number.

The latest rule (``latest_where``, RPT-11): per contract, the contract version with the latest
effective date on or before ``as_of`` among the versions the contract is read from. A version's
effective date is the latest effective date its obligation versions include (LM-CL-13). [J] Ties
are broken by the record time of the version and then ``version_no``, which follows the record
order of the computations, and so the ``record_seq`` of the events they include.

Entry at activation (``latest_where(entered=True)``, RPT-11 alone; ENGINE_SPEC_B S15-R-24a and
S15-R-12 rev 1.161; item RPT-RPO-ROLLFWD-1; supervisor ruling R-121 (g)): the first included
version along a contract's chain counts from the contract's entry — the effective date of its
``CONTRACT_ACTIVATED``, ``CONTRACT_CRITERIA_MET`` (for the run's book) or
``OPENING_BALANCE_ESTABLISHED`` event among that version's causes — where that is earlier than
the latest effective date of the version, and never earlier than a version before it on the
chain. A computation takes in every event recorded so far, so a first version is often caused by
the activation and by later measurements; dated by the last of them, the contract was missing
from the report at every date in between. RPT-12 and RPT-30 keep the stored rule: the legacy
export prints the version as the legacy system did.

The versions a contract is read from (item RPT-FORMER-GROUP-VERSIONS-1; 04 T-CON-04): a version
counts for a member contract only while that contract is a member of the version's group — the
versions recorded during one of its memberships in that group (``counted``). The rule was per
combination group: a contract computed in its own group and combined later was listed twice, by
the last version of the group it had left and by the combined group's, with one row key. A date
before the combination took effect still answers the former group's version. The contracts of a
group share its versions, so for a group whose members never changed the answer is the same.

RPT-09 rows ``version:<external id>:<version no>:<obligation key>`` — the number along the chain —
carry the version, its record time, the E-03 types of the events that caused it in record order,
the obligation's quantity, allocation, revenue and billing to date, remaining allocation, schedule
amounts, the version's catch-up and the E-22 status text. Control totals ``row_count`` and
``contract_count``; no totals and no tie-out.

[J] L7-1-Q-2: SCREENS_B RPT-09 gives "No contract <value> in this workspace." as the combobox copy.
The run answers 0 rows for a name without a contract, as TC-REP-04 and TC-REP-05 require.
[J] Defaults: ``from_date`` is the first day of the fiscal year, and ``to_date`` the last day of the
period, holding the run's as-of date for the first entity of the run with a period there; without
such a period both are that date.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import Uuid, and_, case, column, func, or_, select, true, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause, Subquery

from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    legal_entity,
    obligation,
    obligation_version,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.legacy_columns import decimal_text
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "contract_history"
START_AFTER_END: Final = "Start date must be on or before end date."
# E-22 display text (SCREENS_B RPT-09 "Status").
STATUS_TEXT: Final[Mapping[str, str]] = {
    "UNSATISFIED": "Unsatisfied",
    "PARTIALLY_SATISFIED": "Partially satisfied",
    "SATISFIED": "Satisfied",
    "CANCELLED": "Cancelled",
}
MONEY: Final = (
    "allocated_amount",
    "revenue_cum",
    "billed_cum",
    "remaining_allocation",
    "scheduled_amount",
    "awaiting_trigger_amount",
    "catch_up_amount",
)
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("version_no", "Version", "integer"),
    Column("effective_date", "Effective date", "date"),
    Column("known_at", "Known at", "timestamp"),
    Column("cause_event_types", "Cause", "codes"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("currency", "Currency", "code"),
    Column("quantity", "Quantity", "decimal"),
    Column("allocated_amount", "Allocated", "money"),
    Column("revenue_cum", "Revenue to date", "money"),
    Column("billed_cum", "Billed to date", "money"),
    Column("remaining_allocation", "Remaining allocation", "money"),
    Column("scheduled_amount", "Scheduled", "money"),
    Column("awaiting_trigger_amount", "Awaiting trigger", "money"),
    Column("catch_up_amount", "Catch-up in version", "money"),
    Column("satisfaction_status", "Status", "text"),
)

type Row = Mapping[str, Any]


def literal(value: Any) -> str:
    """The literal of an enum column value."""
    return str(getattr(value, "value", value))


def status_text(value: Any) -> str:
    found = literal(value)
    return STATUS_TEXT.get(found, found)


def default_dates(session: Session, params: ReportParams, *, year: bool) -> tuple[date, date]:
    """The context range of a run: the period holding the as-of date (with ``year``, from the
    first day of its fiscal year) for the first entity with such a period; else that date."""
    found = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found, params=params)
    for entity in found:
        calendar = found_calendars[entity.id]
        current = calendar.holding(tie_outs.run_day(params, entity))
        if current is not None:
            first = calendar.fiscal_year(current)[0] if year else current
            return first.start, current.end
    day = params.as_of_date or params.known_at.date()
    return day, day


def date_range(session: Session, params: ReportParams, *, year: bool) -> tuple[date, date]:
    """``from_date`` and ``to_date``, defaulted by ``default_dates``; 422 for a start after end."""
    given_from, given_to = params.parameters.get("from_date"), params.parameters.get("to_date")
    if given_from is None or given_to is None:
        first, last = default_dates(session, params, year=year)
    else:
        first = last = params.known_at.date()
    start = first if given_from is None else date.fromisoformat(str(given_from))
    end = last if given_to is None else date.fromisoformat(str(given_to))
    if start > end:
        raise tie_outs.invalid("from_date", START_AFTER_END)
    return start, end


def history_where(from_date: date, to_date: date) -> list[ColumnElement[bool]]:
    return [
        obligation_version.c.effective_date >= from_date,
        obligation_version.c.effective_date <= to_date,
    ]


def counted(cutoff: Any) -> ColumnElement[bool]:
    """Whether an ``obligation_version`` row — joined to its ``contract_version`` — is of a version
    its contract is read from (module docstring): the version was recorded while the contract
    was a member of the version's group (T-CON-04, record time). A version of a group without
    any membership row by ``cutoff`` (rows written outside the product's commands) is read as
    recorded. Both conditions enter T-CON-04 by ``ix_combination_group_member__group`` and
    compare uuid and timestamp columns only."""
    member = combination_group_member
    of_group = (
        member.c.tenant_id == obligation_version.c.tenant_id,
        member.c.combination_group_id == obligation_version.c.combination_group_id,
    )
    during = (
        select(member.c.id)
        .where(
            *of_group,
            member.c.contract_id == obligation_version.c.contract_id,
            member.c.valid_from_known_at <= contract_version.c.known_at,
            or_(
                member.c.valid_to_known_at.is_(None),
                contract_version.c.known_at < member.c.valid_to_known_at,
            ),
        )
        .exists()
    )
    any_membership = (
        select(member.c.id).where(*of_group, member.c.valid_from_known_at <= cutoff).exists()
    )
    return or_(during, ~any_membership)


def _entries(
    per_version: Subquery, *, book_code: str, cutoff: datetime, versions: Sequence[UUID] | None
) -> Subquery:
    """(contract version, contract, entry date) of the first included version along each
    contract's chain that names an entry event of the contract among its causes (module
    docstring "Entry at activation"). The chain is the one every reader takes
    (``tie_outs.chain_versions``): the versions computed with the contract during its
    memberships, in the order of the memberships and of ``version_no``; ``versions`` are a bound
    run's. The entry date is the earliest effective date of the contract's
    ``tie_outs.ENTRY_EVENTS`` among that version's causes — ``CONTRACT_CRITERIA_MET`` for
    ``book_code`` alone — and never earlier than the latest effective date of a version before
    it on the chain (``per_version`` is ``latest_where``'s own). The events are found by id from
    the version's causes: an equality on a uuid, which an index under the row-level-security
    policy can bound."""
    on_chain = tie_outs.chain_versions(
        book_code=book_code, cutoff=cutoff, versions=versions
    ).subquery("entry_chain")
    included = on_chain.c.status_in_book.in_(sorted(tie_outs.INCLUDED_STATUSES))
    along = (on_chain.c.member_from, on_chain.c.version_no)
    ranked = (
        select(
            on_chain.c.contract_id,
            on_chain.c.id.label("contract_version_id"),
            included.label("included"),
            func.sum(case((included, 1), else_=0))
            .over(partition_by=on_chain.c.contract_id, order_by=along)
            .label("included_so_far"),
            func.max(per_version.c.effective_date)
            .over(partition_by=on_chain.c.contract_id, order_by=along, rows=(None, -1))
            .label("effective_before"),
        )
        .select_from(on_chain.join(per_version, per_version.c.contract_version_id == on_chain.c.id))
        .subquery("entry_ranked")
    )
    cause = (
        func.unnest(contract_version.c.cause_event_ids)
        .table_valued(column("event_id", Uuid()), name="entry_cause")
        .render_derived()
    )
    entered = func.min(contract_event.c.effective_date)
    causes: FromClause = (
        ranked.join(contract_version, contract_version.c.id == ranked.c.contract_version_id)
        .join(cause, true())
        .join(
            contract_event,
            and_(
                contract_event.c.tenant_id == contract_version.c.tenant_id,
                contract_event.c.id == cause.c.event_id,
            ),
        )
    )
    return (
        select(
            ranked.c.contract_version_id,
            ranked.c.contract_id,
            func.greatest(entered, func.coalesce(ranked.c.effective_before, entered)).label(
                "entry_date"
            ),
        )
        .select_from(causes)
        .where(
            ranked.c.included,
            ranked.c.included_so_far == 1,  # the first included version on the chain
            contract_event.c.contract_id == ranked.c.contract_id,
            contract_event.c.event_type.in_(sorted(tie_outs.ENTRY_EVENTS)),
            or_(
                contract_event.c.event_type != tie_outs.CRITERIA_MET,
                contract_event.c.payload["book"].as_string() == book_code,
            ),
        )
        .group_by(ranked.c.contract_version_id, ranked.c.contract_id, ranked.c.effective_before)
        .subquery("entry")
    )


def latest_where(
    session: Session,
    params: ReportParams,
    *,
    book_code: str,
    as_of: date,
    entered: bool = False,
) -> list[ColumnElement[bool]]:
    """The obligation versions of each contract's latest contract version effective on or before
    ``as_of`` (module docstring). With ``entered`` the first included version along a contract's
    chain counts from the contract's entry (``_entries``)."""
    tenant = obligation_version.c.tenant_id
    cutoff = tie_outs.cutoff_for(session, params)
    versioned = obligation_version.join(
        contract_version,
        and_(
            contract_version.c.tenant_id == tenant,
            contract_version.c.id == obligation_version.c.contract_version_id,
        ),
    )
    recorded = [
        obligation_version.c.book_code == book_code,
        contract_version.c.known_at <= cutoff,
        *tie_outs.bound_version_where(params, contract_version.c.id, book_code),
    ]
    per_version = (
        select(
            obligation_version.c.contract_version_id,
            obligation_version.c.version_no,
            contract_version.c.known_at,
            func.max(obligation_version.c.effective_date).label("effective_date"),
        )
        .select_from(versioned)
        .where(*recorded)
        .group_by(
            obligation_version.c.contract_version_id,
            obligation_version.c.version_no,
            contract_version.c.known_at,
        )
        .subquery()
    )
    held = (
        select(obligation_version.c.contract_version_id, obligation_version.c.contract_id)
        .select_from(versioned)
        .where(*recorded, counted(cutoff))
        .distinct()
        .subquery()
    )
    candidates: FromClause = held.join(
        per_version, per_version.c.contract_version_id == held.c.contract_version_id
    )
    effective: ColumnElement[Any] = per_version.c.effective_date
    if entered:
        entry = _entries(
            per_version,
            book_code=book_code,
            cutoff=cutoff,
            versions=None if params.binding is None else params.binding.version_ids(book_code),
        )
        candidates = candidates.outerjoin(
            entry,
            and_(
                entry.c.contract_version_id == held.c.contract_version_id,
                entry.c.contract_id == held.c.contract_id,
            ),
        )
        effective = func.least(
            per_version.c.effective_date,
            func.coalesce(entry.c.entry_date, per_version.c.effective_date),
        )
    latest = (
        select(held.c.contract_version_id, held.c.contract_id)
        .select_from(candidates)
        .where(effective <= as_of)
        .distinct(held.c.contract_id)
        .order_by(
            held.c.contract_id,
            effective.desc(),
            per_version.c.known_at.desc(),
            per_version.c.version_no.desc(),
        )
        .subquery()
    )
    return [
        tuple_(obligation_version.c.contract_version_id, obligation_version.c.contract_id).in_(
            select(latest.c.contract_version_id, latest.c.contract_id)
        )
    ]


def chain_numbers(
    session: Session, *, book_code: str, contract_ids: Iterable[UUID], cutoff: datetime
) -> dict[tuple[UUID, UUID], int]:
    """``(contract, contract version)`` → the version's number along the contract's chain (module
    docstring; ``tie_outs.chain_versions``): the versions of ``book_code`` computed with the
    contract among their members during each of its memberships, numbered from 1 in the order of
    the memberships and, within one, of ``version_no``. A version a group computed after the
    contract had left it does not count. A version outside the chain — rows written outside the
    product's commands — has no entry; the caller keeps its stored number.

    The number is a fact of the record, not a selection: versions and memberships are appended
    and never renumbered, so a version's number is the same at every cutoff from its own record
    time on and under every binding (S15-R-24a (d): the memberships are those recorded by the
    cutoff)."""
    wanted = sorted(set(contract_ids), key=str)
    if not wanted:
        return {}
    on_chain = tie_outs.chain_versions(book_code=book_code, cutoff=cutoff).subquery("on_chain")
    numbered = select(
        on_chain.c.contract_id,
        on_chain.c.id,
        func.row_number()
        .over(
            partition_by=on_chain.c.contract_id,
            order_by=(on_chain.c.member_from, on_chain.c.version_no),
        )
        .label("chain_no"),
    ).where(on_chain.c.contract_id.in_(wanted))
    return {
        (UUID(str(contract_id)), UUID(str(version_id))): int(chain_no)
        for contract_id, version_id, chain_no in session.execute(numbered)
    }


def in_chain_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``rows`` — in the statement's order, each with its ``chain_version_no`` — ordered by
    contract, the version's number along the chain and ``line_sequence`` (04 §17.1 rule 1). The
    order of the contracts, and of obligations that share a line, stays the statement's (the
    database's collation), so rows whose contract never changed its group keep their places.
    Pure."""
    first: dict[str, int] = {}
    for row in rows:
        first.setdefault(str(row["contract_external_id"]), len(first))
    placed = sorted(
        enumerate(rows),
        key=lambda item: (
            first[str(item[1]["contract_external_id"])],
            int(item[1]["chain_version_no"]),
            int(item[1]["line_sequence"]),
            item[0],
        ),
    )
    return [row for _, row in placed]


def population(
    session: Session,
    params: ReportParams,
    *,
    book_code: str,
    where: Iterable[ColumnElement[bool]],
) -> list[dict[str, Any]]:
    """The obligation versions of the run (module docstring), each with ``contract_external_id``,
    ``line_sequence``, ``version_known_at``, ``cause_event_ids``, ``processed_at`` (the
    computation's ``created_at``), ``entity_code`` (the contracting entity) and
    ``chain_version_no`` (the version's number along its contract's chain), in chain order."""
    if not params.entity_ids:
        return []
    tenant = obligation_version.c.tenant_id
    joined = (
        obligation_version.join(
            contract_version,
            and_(
                contract_version.c.tenant_id == tenant,
                contract_version.c.id == obligation_version.c.contract_version_id,
            ),
        )
        .join(
            contract_computation,
            and_(
                contract_computation.c.tenant_id == tenant,
                contract_computation.c.id == contract_version.c.contract_computation_id,
            ),
        )
        .join(
            contract,
            and_(contract.c.tenant_id == tenant, contract.c.id == obligation_version.c.contract_id),
        )
        .join(
            obligation,
            and_(
                obligation.c.tenant_id == tenant,
                obligation.c.id == obligation_version.c.obligation_id,
            ),
        )
        .join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant,
                legal_entity.c.id == obligation_version.c.contracting_entity_id,
            ),
        )
    )
    statement = (
        select(
            obligation_version,
            contract.c.external_id.label("contract_external_id"),
            obligation.c.line_sequence,
            contract_version.c.known_at.label("version_known_at"),
            contract_version.c.cause_event_ids,
            contract_computation.c.created_at.label("processed_at"),
            legal_entity.c.code.label("entity_code"),
        )
        .select_from(joined)
        .where(
            obligation_version.c.book_code == book_code,
            obligation_version.c.contracting_entity_id.in_(list(params.entity_ids)),
            contract_version.c.known_at <= tie_outs.cutoff_for(session, params),
            *tie_outs.bound_version_where(params, contract_version.c.id, book_code),
            *where,
        )
        .order_by(
            contract.c.external_id,
            obligation_version.c.version_no,
            obligation.c.line_sequence,
            obligation_version.c.obligation_key,
        )
    )
    name = params.parameters.get("contract_external_id")
    if name is not None:
        statement = statement.where(contract.c.external_id == str(name))
    rows = [dict(row) for row in session.execute(statement).mappings()]
    # S15-R-24: the contract versions this population consumed, for the binding.
    tie_outs.record_consumed_versions(
        params, book_code, {UUID(str(row["contract_version_id"])) for row in rows}
    )
    numbers = chain_numbers(
        session,
        book_code=book_code,
        contract_ids={UUID(str(row["contract_id"])) for row in rows},
        cutoff=tie_outs.cutoff_for(session, params),
    )
    for row in rows:
        key = (UUID(str(row["contract_id"])), UUID(str(row["contract_version_id"])))
        row["chain_version_no"] = numbers.get(key, int(row["version_no"]))
    rows = in_chain_order(rows)
    # frps3c-1: the contracting entity's code as consumed (`labels.entity_code`) — the live join's
    # value is recorded by a live build and replaced by the bound value under a binding.
    for row in rows:
        row["entity_code"] = tie_outs.entity_code_for(
            params, UUID(str(row["contracting_entity_id"])), str(row["entity_code"])
        )
    return rows


def previous_versions(session: Session, rows: Sequence[Row]) -> dict[UUID, dict[str, Any]]:
    """The previous obligation versions of ``rows`` by id (04 §17.1 rule 2)."""
    ids = sorted(
        {
            UUID(str(row["previous_obligation_version_id"]))
            for row in rows
            if row["previous_obligation_version_id"] is not None
        },
        key=str,
    )
    if not ids:
        return {}
    return {
        UUID(str(found["id"])): dict(found)
        for found in session.execute(
            select(obligation_version).where(obligation_version.c.id.in_(ids))
        ).mappings()
    }


def previous_of(previous: Mapping[UUID, Row], row: Row) -> Row | None:
    value = row["previous_obligation_version_id"]
    return None if value is None else previous.get(UUID(str(value)))


def cause_types(session: Session, rows: Sequence[Row]) -> dict[UUID, tuple[int, str]]:
    """``(record_seq, event_type)`` of each causing event of ``rows``."""
    ids = sorted({UUID(str(value)) for row in rows for value in row["cause_event_ids"]}, key=str)
    if not ids:
        return {}
    return {
        UUID(str(found["id"])): (int(found["record_seq"]), literal(found["event_type"]))
        for found in session.execute(
            select(
                contract_event.c.id, contract_event.c.record_seq, contract_event.c.event_type
            ).where(contract_event.c.id.in_(ids))
        ).mappings()
    }


def event_types(row: Row, causes: Mapping[UUID, tuple[int, str]]) -> list[str]:
    ordered = sorted(
        causes[UUID(str(value))] for value in row["cause_event_ids"] if UUID(str(value)) in causes
    )
    return list(dict.fromkeys(event_type for _, event_type in ordered))


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    from_date, to_date = date_range(session, params, year=True)
    rows = population(session, params, book_code=book_code, where=history_where(from_date, to_date))
    causes = cause_types(session, rows)
    items: list[dict[str, Any]] = []
    for row in rows:
        currency = str(row["txn_currency"]).strip()
        external_id = str(row["contract_external_id"])
        items.append(
            {
                "row_key": (
                    f"version:{external_id}:{row['chain_version_no']}:{row['obligation_key']}"
                ),
                "contract_external_id": external_id,
                "version_no": int(row["chain_version_no"]),
                "effective_date": row["effective_date"],
                "known_at": row["version_known_at"],
                "cause_event_types": event_types(row, causes),
                "obligation_key": str(row["obligation_key"]),
                "product_code": str(row["product_code"]),
                "currency": currency,
                "quantity": decimal_text(row["quantity"]),
                **{name: tie_outs.money(Decimal(row[name]), currency) for name in MONEY},
                "satisfaction_status": status_text(row["satisfaction_status"]),
            }
        )
    return ReportData(
        columns=COLUMNS,
        rows=tuple(items),
        control_totals={
            "row_count": len(items),
            "contract_count": len({item["contract_external_id"] for item in items}),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
        },
    )
