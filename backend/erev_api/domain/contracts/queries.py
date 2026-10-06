"""Contract reads (dev-guide §6.1 DG-CMD-13; 04 §15.1 API-C-08 to API-C-11, §15.3 API-R-28,
§16.1, §16.2, §16.14; 03 REQ-CON-014, REQ-CON-017, REQ-PLT-012, REQ-PLT-030, REQ-ALC-009;
BUILD_SPEC CTR-4).

Every read runs in ``tenant_session(read_only=True)`` under the caller's tenant context and entity
scope, so a contract outside the scope answers 404 exactly as a missing one (REQ-PLT-012). Commands
build their response through ``contract_out`` in their own session.

Time travel (API-C-10; [J] L3-1-Q-37):
- ``known_at`` selects the contract version: the latest ``contract_version`` of the contract's
  combination group (the membership in force at ``known_at``) and book with ``known_at ≤`` the
  parameter; without the parameter, the latest version.
- ``as_of`` dates the to-date measures (04 rev 1.132; ``to_date``): the contract, obligation and
  balance reads serve them at the end of the period that contains ``as_of``, not later than the
  version's horizon, from the period nodes of the version's trace; a measure the trace cannot answer
  is refused by name and a ``GET /contracts`` row of such a contract carries ``kpis: null``. The
  version reads answer the version as stored.
- ``as_of`` bounds ledger and schedule reads to lines whose period ends on or before the end of the
  period of the line's entity that contains ``as_of``. Subledger lines default ``as_of`` to today in
  the contracting entity's time zone; schedules are bounded only when ``as_of`` is sent.
- ``book`` defaults to the primary book (API-C-11).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import contract_subject_key
from sqlalchemy import (
    Column,
    Date,
    Integer,
    Select,
    Table,
    Text,
    Uuid,
    and_,
    case,
    exists,
    false,
    func,
    literal,
    not_,
    null,
    or_,
    select,
    text,
    union_all,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from erev_api.auth.principal import SYSTEM_DISPLAY_NAME, RequestContext
from erev_api.clock import to_entity_date
from erev_api.db.session import system_entity_scope, tenant_session
from erev_api.db.tables import (
    api_client,
    app_user,
    approval_decision,
    approval_request,
    book,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_hold,
    contract_version,
    contract_version_balance,
    customer,
    gl_account,
    legal_entity,
    obligation,
    obligation_version,
    period,
    pob_template,
    pob_template_version,
    product,
    schedule,
    schedule_line,
    subledger_line,
)
from erev_api.db.types import ExactType, MoneyType
from erev_api.domain.contracts import repo, to_date
from erev_api.domain.journals import subledger
from erev_api.domain.reports import tie_outs
from erev_api.enums import (
    AccountRole,
    ApprovalRequestStatus,
    ApprovalSubjectType,
    BookCode,
    ContractEventType,
    ContractQuickList,
    ContractStep,
    ContractStepState,
    HistoryItemKind,
    PrincipalKind,
    ScheduleKind,
    SourceSystem,
    SspRangePosition,
)
from erev_api.money import MoneyOut, money_out
from erev_api.problems import Problem
from erev_api.schemas.common import ActorOut, ContextOut, MeasuredPeriodOut, RefOut
from erev_api.schemas.contracts import (
    AllocationLineOut,
    AllocationTotalsOut,
    AllocationWalkOut,
    BalanceLinksOut,
    CauseEventOut,
    CombinationGroupOut,
    ContractBalanceFunctionalOut,
    ContractBalanceOut,
    ContractHistoryItemOut,
    ContractLinksOut,
    ContractListItemOut,
    ContractOut,
    ContractStepOut,
    ContractVersionOut,
    ContractVersionSummaryOut,
    HoldOut,
    KpiRatiosOut,
    NettingReclassOut,
    ObligationCurrentOut,
    ObligationLinksOut,
    ObligationOriginalOut,
    ObligationOut,
    ObligationRatiosOut,
    ObligationRemainingOut,
    ObligationSspOut,
    ObligationToDateOut,
    PositionOut,
    ScheduleLineLinksOut,
    ScheduleLineOut,
    SchedulePeriodOut,
    SspVersionRefOut,
    TemplateVersionRefOut,
    TerminationOut,
    TransactionPriceBuildupOut,
    VersionChangeOut,
    VersionCompareOut,
    VersionRefOut,
)
from erev_api.schemas.subledger import SubledgerLineOut

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore

__all__ = [
    "LIST_PRICE",
    "ListFilters",
    "ReadParams",
    "allocation_walk",
    "balances",
    "compare_versions",
    "contract_list_items",
    "contract_out",
    "get_contract",
    "get_version",
    "history_items",
    "history_statement",
    "list_contracts",
    "measured_out",
    "obligations_at",
    "primary_book",
    "range_position",
    "read",
    "schedule_items",
    "schedule_statement",
    "subledger_statement",
    "version_summaries",
    "versions_by_id",
    "versions_statement",
]

API: Final = "/api/v1"
OUTSIDE_POLICY: Final = "ssp.outside_range_point"  # POL-072
TERM_MEMBERS: Final = ("payment_schedule", "noncash_consideration", "consideration_payable")
TERM_EVENTS: Final = (
    ContractEventType.CONTRACT_BOOKED.value,
    ContractEventType.CONTRACT_AMENDED.value,
    ContractEventType.EVENT_VOIDED.value,
)
INTEGRATION_SOURCES: Final = (
    SourceSystem.SALESFORCE.value,
    SourceSystem.STRIPE.value,
    SourceSystem.API.value,
)
BALANCE_NAMES: Final = (
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
# API-S-Contract ``kpis.balances``: the balances the header shows per entity (04 §16.1).
HEADER_BALANCES: Final = (
    "contract_liability",
    "contract_asset",
    "unbilled_receivable",
    "refund_liability",
)
# The balances whose Explain a balance entry names (04 API-S-Contract ``kpis.balances[].links``
# and API-S-ContractBalance ``links``, rev 1.174): the three figures of the workbench's sixth KPI
# cell.
EXPLAINED_BALANCES: Final = ("contract_liability", "contract_asset", "unbilled_receivable")
# REQ-CON-014 compare: identity, lineage and stamps differ between any two versions by design.
VERSION_SKIPPED: Final = frozenset(
    {
        "tenant_id",
        "id",
        "combination_group_id",
        "contract_computation_id",
        "book_code",
        "version_no",
        "previous_version_id",
        "known_at",
        "cause_event_ids",
        "output_sha256",
        "calc_trace_id",
        "created_at",
        "created_by",
        "created_by_kind",
    }
)
OBLIGATION_SKIPPED: Final = frozenset(
    {
        "tenant_id",
        "id",
        "contract_version_id",
        "obligation_id",
        "contract_id",
        "combination_group_id",
        "book_code",
        "version_no",
        "previous_obligation_version_id",
        "obligation_key",
        "trace_nodes",
        "created_at",
        "created_by",
        "created_by_kind",
    }
)


@dataclass(frozen=True, slots=True)
class ReadParams:
    """The API-C-10 and API-C-11 parameters of a computed read; None takes the default."""

    book: str | None = None
    as_of: date | None = None
    known_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ListFilters:
    """``GET /contracts`` filters the resource applies itself (04 §15.3 API-R-28, E-111)."""

    entity: tuple[str, ...] = ()
    customer: tuple[str, ...] = ()
    on_hold: bool | None = None
    modified_in_period: str | None = None
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    has_exceptions: bool | None = None
    quick_list: ContractQuickList | None = None


# --- formatting -----------------------------------------------------------------------------------


def _money(value: Any, currency: Any) -> MoneyOut:
    return money_out(Decimal(value), str(currency).strip(), ISO_4217)


def _exact(value: Any) -> str:
    return format_exact(Decimal(value))


def _maybe_exact(value: Any) -> str | None:
    return None if value is None else _exact(value)


def _ratio(numerator: Any, denominator: Any) -> str | None:
    below = Decimal(denominator)
    if below == 0:
        return None
    return format_exact(Fraction(Decimal(numerator)) / Fraction(below))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def range_position(low: Any, high: Any, price: Any) -> SspRangePosition | None:
    """E-114: the stated price against the extended SSP range; None for a point entry."""
    if low is None or high is None or price is None:
        return None
    stated = Decimal(price)
    if stated < Decimal(low):
        return SspRangePosition.BELOW
    if stated > Decimal(high):
        return SspRangePosition.ABOVE
    return SspRangePosition.INSIDE


def _outside_policy(version: Mapping[str, Any]) -> str | None:
    """The POL-072 literal the version pinned (``pinned_policies``, L3-1-Q-22)."""
    found = (version.get("pinned_policies") or {}).get(OUTSIDE_POLICY)
    value = found.get("value") if isinstance(found, Mapping) else None
    return value if isinstance(value, str) else None


def _outside_point(position: SspRangePosition | None, policy: str | None) -> str | None:
    return None if position in (None, SspRangePosition.INSIDE) else policy


# --- shared lookups -------------------------------------------------------------------------------


def primary_book(session: Session) -> str:
    found = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    return BookCode.ASC606.value if found is None else str(found)


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def _refs(session: Session, table: Table, ids: Iterable[Any]) -> dict[UUID, RefOut]:
    wanted = sorted({_uuid(value) for value in ids if value is not None})
    if not wanted:
        return {}
    statement = select(table.c.id, table.c.code, table.c.name).where(table.c.id.in_(wanted))
    return {
        _uuid(found.id): RefOut(id=found.id, code=found.code, name=found.name)
        for found in session.execute(statement)
    }


def _entity_refs(session: Session, ids: Iterable[Any]) -> dict[UUID, RefOut]:
    """The references of the legal entities of ``ids``, an entity outside the caller's entity
    scope included (04 API-S-Obligation rev 1.132; supervisor ruling R-85 (d); item
    CTR-OBL-PERF-ENTITY-SCOPE-1).

    ``legal_entity`` is RLS-TE, and the performing entity of an obligation may lie outside the
    scope of a caller who reads the contract through its contracting entity. Who may read the
    contract reads its obligations whole, so such a reference — id, code and name, nothing else of
    the entity — is read under the tenant's scope, entered for that one statement
    (``system_entity_scope``, DG-KRN-DB-05)."""
    wanted = {_uuid(value) for value in ids if value is not None}
    found = _refs(session, legal_entity, wanted)
    missing = sorted(wanted - set(found))
    if missing:
        with system_entity_scope(session):
            found |= _refs(session, legal_entity, missing)
    return found


def _time_zone(session: Session, entity_id: Any) -> str:
    statement = select(legal_entity.c.time_zone).where(legal_entity.c.id == entity_id)
    return str(session.execute(statement).scalar_one())


def _as_of(
    session: Session, contract_row: Mapping[str, Any], params: ReadParams, now: datetime
) -> date:
    if params.as_of is not None:
        return params.as_of
    return to_entity_date(now, _time_zone(session, contract_row["contracting_entity_id"]))


def _key_or_id(column_key: Any, column_id: Any, value: str) -> Any:
    try:
        return column_id == UUID(value)
    except ValueError:
        return column_key == value


def period_end_containing(entity_id: Any, as_of: date) -> Any:
    """The end date of the period of ``entity_id``'s calendar that contains ``as_of``."""
    bound_period = period.alias("bound_period")
    bound_entity = legal_entity.alias("bound_entity")
    return (
        select(bound_period.c.end_date)
        .select_from(
            bound_period.join(
                bound_entity,
                and_(
                    bound_entity.c.tenant_id == bound_period.c.tenant_id,
                    bound_entity.c.calendar_id == bound_period.c.calendar_id,
                ),
            )
        )
        .where(
            bound_entity.c.id == entity_id,
            bound_period.c.start_date <= as_of,
            bound_period.c.end_date >= as_of,
        )
        .limit(1)
        .scalar_subquery()
    )


def _versions() -> Select[Any]:
    return select(
        contract_version,
        contract_computation.c.engine_version,
        contract_computation.c.input_sha256,
        contract_computation.c.pinned_refs,
        # API-S-Context ``computed_at`` (04 rev 1.132): when the computation made the version
        contract_computation.c.created_at.label("computed_at"),
    ).select_from(
        contract_version.join(
            contract_computation,
            and_(
                contract_computation.c.tenant_id == contract_version.c.tenant_id,
                contract_computation.c.id == contract_version.c.contract_computation_id,
            ),
        )
    )


def group_at(session: Session, contract_row: Mapping[str, Any], known_at: datetime | None) -> UUID:
    """The contract's combination group at ``known_at`` (T-CON-04), else its current group."""
    current = _uuid(contract_row["combination_group_id"])
    if known_at is None:
        return current
    member = combination_group_member
    statement = (
        select(member.c.combination_group_id)
        .where(
            member.c.contract_id == contract_row["id"],
            member.c.valid_from_known_at <= known_at,
            or_(member.c.valid_to_known_at.is_(None), member.c.valid_to_known_at > known_at),
        )
        .order_by(member.c.valid_from_known_at.desc())
        .limit(1)
    )
    found = session.execute(statement).scalar()
    return current if found is None else _uuid(found)


def version_at(
    session: Session,
    contract_row: Mapping[str, Any],
    *,
    book_code: str,
    known_at: datetime | None,
) -> dict[str, Any] | None:
    """API-C-10: the latest version of the group and book recorded by ``known_at``."""
    statement = _versions().where(
        contract_version.c.combination_group_id == group_at(session, contract_row, known_at),
        contract_version.c.book_code == book_code,
    )
    if known_at is not None:
        statement = statement.where(contract_version.c.known_at <= known_at)
    found = (
        session.execute(statement.order_by(contract_version.c.version_no.desc()).limit(1))
        .mappings()
        .first()
    )
    return None if found is None else dict(found)


def versions_by_id(session: Session, version_ids: Iterable[Any]) -> dict[UUID, dict[str, Any]]:
    """The contract versions of ``version_ids`` with their computation's facts."""
    wanted = sorted({_uuid(value) for value in version_ids})
    if not wanted:
        return {}
    statement = _versions().where(contract_version.c.id.in_(wanted))
    return {_uuid(found["id"]): dict(found) for found in session.execute(statement).mappings()}


def _versions_of(
    session: Session, group_ids: Iterable[UUID], *, book_code: str, known_at: datetime | None
) -> dict[UUID, dict[str, Any]]:
    """API-C-10 for the groups of one read: per combination group, the latest version of the book
    recorded by ``known_at`` — what ``version_at`` answers for one contract, in one statement."""
    wanted = sorted(set(group_ids))
    if not wanted:
        return {}
    statement = _versions().where(
        contract_version.c.combination_group_id.in_(wanted),
        contract_version.c.book_code == book_code,
    )
    if known_at is not None:
        statement = statement.where(contract_version.c.known_at <= known_at)
    statement = statement.distinct(contract_version.c.combination_group_id).order_by(
        contract_version.c.combination_group_id, contract_version.c.version_no.desc()
    )
    return {
        _uuid(found["combination_group_id"]): dict(found)
        for found in session.execute(statement).mappings()
    }


def _version_numbered(
    session: Session, contract_row: Mapping[str, Any], book_code: str, version_no: int
) -> dict[str, Any]:
    statement = _versions().where(
        contract_version.c.combination_group_id == contract_row["combination_group_id"],
        contract_version.c.book_code == book_code,
        contract_version.c.version_no == version_no,
    )
    found = session.execute(statement).mappings().one_or_none()
    if found is None:
        raise Problem("not-found", f"The contract has no version {version_no} in {book_code}.")
    return dict(found)


def _obligation_versions(
    session: Session, version_ids: Sequence[Any], *, contract_ids: Sequence[Any] | None = None
) -> list[dict[str, Any]]:
    """Obligation versions of the versions in display order (line sequence, then key)."""
    if not version_ids:
        return []
    statement = (
        select(obligation_version, obligation.c.line_sequence)
        .select_from(
            obligation_version.join(
                obligation,
                and_(
                    obligation.c.tenant_id == obligation_version.c.tenant_id,
                    obligation.c.id == obligation_version.c.obligation_id,
                ),
            )
        )
        .where(obligation_version.c.contract_version_id.in_(list(version_ids)))
        .order_by(
            obligation_version.c.contract_id,
            obligation.c.line_sequence,
            obligation_version.c.obligation_key,
        )
    )
    if contract_ids is not None:
        statement = statement.where(obligation_version.c.contract_id.in_(list(contract_ids)))
    return [dict(found) for found in session.execute(statement).mappings()]


def _balance_rows(
    session: Session, version_ids: Sequence[Any], contract_ids: Sequence[Any]
) -> list[dict[str, Any]]:
    if not version_ids:
        return []
    statement = (
        select(
            contract_version_balance,
            legal_entity.c.code.label("entity_code"),
            legal_entity.c.name.label("entity_name"),
        )
        .select_from(
            contract_version_balance.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract_version_balance.c.tenant_id,
                    legal_entity.c.id == contract_version_balance.c.entity_id,
                ),
            )
        )
        .where(
            contract_version_balance.c.contract_version_id.in_(list(version_ids)),
            contract_version_balance.c.contract_id.in_(list(contract_ids)),
        )
        .order_by(legal_entity.c.code)
    )
    return [dict(found) for found in session.execute(statement).mappings()]


# --- API-S-Contract -------------------------------------------------------------------------------


def _members(
    session: Session, group_ids: Iterable[UUID], known_at: datetime | None
) -> tuple[dict[UUID, list[UUID]], dict[UUID, int]]:
    """Per group, the members the session reads (by contract id) and how many members the group
    has in all (head R28-READS; supervisor ruling R-28): T-CON-04 carries no entity, and the
    contract of another entity is named to nobody who does not read it — the count says that the
    figures are a group's of that many contracts (``combination._members_read`` for API-R-28's
    groups)."""
    wanted = sorted(set(group_ids))
    member = combination_group_member
    read = contract.alias("member_contract")
    statement = (
        select(member.c.combination_group_id, member.c.contract_id, read.c.id)
        .select_from(
            member.outerjoin(
                read,
                and_(read.c.tenant_id == member.c.tenant_id, read.c.id == member.c.contract_id),
            )
        )
        .where(member.c.combination_group_id.in_(wanted))
    )
    if known_at is None:
        statement = statement.where(member.c.valid_to_known_at.is_(None))
    else:
        statement = statement.where(
            member.c.valid_from_known_at <= known_at,
            or_(member.c.valid_to_known_at.is_(None), member.c.valid_to_known_at > known_at),
        )
    found: dict[UUID, list[UUID]] = defaultdict(list)
    counted: dict[UUID, int] = defaultdict(int)
    for group_id, contract_id, visible in session.execute(statement.order_by(member.c.contract_id)):
        counted[_uuid(group_id)] += 1
        if visible is not None:
            found[_uuid(group_id)].append(_uuid(contract_id))
    return found, counted


def _terms(
    session: Session, contract_ids: Sequence[UUID], known_at: datetime | None
) -> dict[UUID, dict[str, list[Any]]]:
    """Current terms: per member, the latest ``CONTRACT_BOOKED`` or ``CONTRACT_AMENDED`` payload
    that carries it, voided events left out (04 §16.1 API-S-Contract, rev 1.2)."""
    statement = select(
        contract_event.c.id,
        contract_event.c.contract_id,
        contract_event.c.event_type,
        contract_event.c.payload,
        contract_event.c.supersedes_event_id,
    ).where(
        contract_event.c.contract_id.in_(list(contract_ids)),
        contract_event.c.event_type.in_(TERM_EVENTS),
    )
    if known_at is not None:
        statement = statement.where(contract_event.c.recorded_at <= known_at)
    rows = list(
        session.execute(statement.order_by(contract_event.c.stream_version.desc())).mappings()
    )
    voided = {
        _uuid(found["supersedes_event_id"])
        for found in rows
        if found["supersedes_event_id"] is not None
    }
    terms: dict[UUID, dict[str, list[Any]]] = defaultdict(dict)
    for found in rows:
        if _text(found["event_type"]) == ContractEventType.EVENT_VOIDED.value:
            continue
        if _uuid(found["id"]) in voided:
            continue
        members = terms[_uuid(found["contract_id"])]
        payload = found["payload"] or {}
        for name in TERM_MEMBERS:
            if name not in members and payload.get(name) is not None:
                members[name] = list(payload[name])
    return terms


IN_REVIEW_FROM: Final = frozenset({"DRAFT", "NOT_A_CONTRACT"})


def _read_status(stored: Any, *, in_review: bool) -> str:
    """[J] L4-1-Q-18 (BUILD_SPEC CTR-9): SM-02 DRAFT → PENDING_REVIEW appends no event and DB-18
    admits no header change without one, so a DRAFT contract with a PENDING ``CONTRACT_ACTIVATION``
    request reads PENDING_REVIEW. The same holds for SM-02 NOT_A_CONTRACT → PENDING_REVIEW since
    supervisor ruling R-20 (c) (04 T-CON-01 rev 1.105): ``CONTRACT_CRITERIA_MET`` is appended by
    the approved activation, so the stored status stays NOT_A_CONTRACT while the request is
    PENDING."""
    status = str(getattr(stored, "value", stored))
    if in_review and status in IN_REVIEW_FROM:
        return "PENDING_REVIEW"
    return status


def _in_review(session: Session, contract_ids: Sequence[UUID]) -> set[UUID]:
    statement = select(approval_request.c.subject_id).where(
        approval_request.c.subject_type == ApprovalSubjectType.CONTRACT_ACTIVATION.value,
        approval_request.c.subject_id.in_(list(contract_ids)),
        approval_request.c.status == ApprovalRequestStatus.PENDING.value,
    )
    return {_uuid(found) for found in session.execute(statement).scalars()}


ENFORCEABLE_TERMS: Final = text(
    "SELECT ct.contract_version_id, node ->> 'id' AS node_id, node -> 'params' AS params "
    "FROM erev.calc_trace ct CROSS JOIN LATERAL jsonb_array_elements(ct.trace -> 'nodes') AS node "
    "WHERE ct.contract_version_id = ANY(:version_ids) "
    "AND node ->> 'measure' = 'enforceable_end_date'"
)


def enforceable_terms(
    session: Session,
    versions: Mapping[UUID, Mapping[str, Any] | None],
    external_ids: Mapping[UUID, str],
) -> dict[UUID, dict[str, Any]]:
    """Per contract, ``{end_date, basis}`` of the ``enforceable_end_date`` node that stage 02 wrote
    into the version's trace (ENGINE_SPEC S02-R-06, §2.1 ``EnforceableTerm``; BUILD_SPEC CTR-7).
    [J] L4-1-Q-14: a contract without such a node (no stated end) has no detail member."""
    wanted = {
        UUID(str(version["id"])): contract_id
        for contract_id, version in versions.items()
        if version is not None
    }
    if not wanted:
        return {}
    node_ids = {
        f"enforceable_end_date:{contract_subject_key(external_ids[contract_id])}:-": contract_id
        for contract_id in wanted.values()
    }
    found: dict[UUID, dict[str, Any]] = {}
    for row in session.execute(ENFORCEABLE_TERMS, {"version_ids": sorted(wanted)}).mappings():
        contract_id = node_ids.get(str(row["node_id"]))
        if contract_id is None or wanted.get(UUID(str(row["contract_version_id"]))) != contract_id:
            continue
        params = dict(row["params"] or {})
        found[contract_id] = {"end_date": params.get("date"), "basis": params.get("basis")}
    return found


def _step_detail(
    step: ContractStep,
    version: Mapping[str, Any] | None,
    obligations: Sequence[Mapping[str, Any]],
    term: Mapping[str, Any] | None = None,
    recognized: str | None = None,
) -> dict[str, Any]:
    """[J] L3-1-Q-38: the detail members the stored version carries; ``recognized`` is the
    to-date ratio of revenue to the transaction price at the cut (04 API-C-10 rev 1.132)."""
    if version is None:
        return {}
    currency = version["transaction_currency"]
    match step:
        case ContractStep.CONTRACT:
            return {} if term is None else {"enforceable_term": dict(term)}
        case ContractStep.TRANSACTION_PRICE:
            adjustment = Decimal(version["financing_adjustment_amount"])
            return {
                "financing_note": {
                    "assessed": adjustment != 0,
                    "significant": None if adjustment == 0 else True,
                    "exception_32_17": None,
                    "financing_adjustment": _money(adjustment, currency).model_dump(),
                }
            }
        case ContractStep.RECOGNITION:
            return {
                "recognized_ratio": recognized,
                "obligations": [
                    {
                        "obligation_key": item["obligation_key"],
                        "next_trigger": {
                            "recognition_method": _text(item["recognition_method"]),
                            "expected_date": None,
                        },
                    }
                    for item in obligations
                ],
            }
        case _:
            return {}


def _steps(
    version: Mapping[str, Any] | None,
    obligations: Sequence[Mapping[str, Any]],
    *,
    in_review: bool,
    term: Mapping[str, Any] | None = None,
    recognized: str | None = None,
) -> list[ContractStepOut]:
    """04 §16.14 step rule with the facts stored so far ([J] L3-1-Q-38): IN_REVIEW for CONTRACT
    while a CONTRACT_ACTIVATION request is PENDING; NOT_STARTED for the other steps while no version
    exists; otherwise COMPLETE."""
    steps: list[ContractStepOut] = []
    for step in ContractStep:
        if step is ContractStep.CONTRACT and in_review:
            state = ContractStepState.IN_REVIEW
        elif step is not ContractStep.CONTRACT and version is None:
            state = ContractStepState.NOT_STARTED
        else:
            state = ContractStepState.COMPLETE
        steps.append(
            ContractStepOut(
                step=step,
                state=state,
                status_code=None,
                detail=_step_detail(step, version, obligations, term, recognized),
            )
        )
    return steps


def _kpis(version: Mapping[str, Any]) -> dict[str, Any]:
    currency = version["transaction_currency"]
    return {
        "transaction_price": _money(version["transaction_price"], currency),
        "revenue_to_date": _money(version["revenue_cum"], currency),
        "billed_to_date": _money(version["billed_cum"], currency),
        "scheduled": _money(version["scheduled_amount"], currency),
        "awaiting_trigger": _money(version["awaiting_trigger_amount"], currency),
        "rpo": _money(version["rpo_amount"], currency),
    }


def measured_out(measured: to_date.Measured | None) -> MeasuredPeriodOut | None:
    """API-S-Context ``measured_period`` of a period the to-date measures were read at."""
    if measured is None:
        return None
    return MeasuredPeriodOut(period_key=measured.period_key, end_date=measured.end_date)


def _moved(version: Mapping[str, Any], at: to_date.VersionAt) -> dict[str, Any]:
    """The version with its to-date figures at the cut (04 API-C-10 rev 1.132): the group's
    figures moved by the sum of its obligations' movements since d_v, and its revenue net of the
    JET-14 release of the cut's period instead of the period of d_v (ENGINE_SPEC S04-R-02). The
    scheduled and the awaiting-trigger amount each lose what left them (``to_date.remainder_at``;
    item CTR-TODATE-AWAITING-1)."""
    return {
        **version,
        "transaction_price": Decimal(version["transaction_price"]) - at.returns_moved,
        "revenue_cum": Decimal(version["revenue_cum"]) + at.revenue_moved - at.release_moved,
        "billed_cum": Decimal(version["billed_cum"]) + at.billed_moved,
        "scheduled_amount": Decimal(version["scheduled_amount"]) - at.scheduled_moved,
        "awaiting_trigger_amount": (
            Decimal(version["awaiting_trigger_amount"]) - at.awaiting_moved
        ),
        "rpo_amount": Decimal(version["rpo_amount"]) - at.rpo_moved,
    }


def _external_ids(
    session: Session, known: Mapping[UUID, str], contract_ids: Iterable[Any]
) -> dict[UUID, str]:
    """The external id of each contract of ``contract_ids`` the caller sees (``contract`` is
    RLS-TE, so a member contract outside the caller's entities is absent)."""
    found = dict(known)
    missing = sorted({_uuid(value) for value in contract_ids} - set(found))
    if missing:
        statement = select(contract.c.id, contract.c.external_id).where(contract.c.id.in_(missing))
        found |= {_uuid(row.id): str(row.external_id) for row in session.execute(statement)}
    return found


def obligations_at(
    session: Session,
    contract_row: Mapping[str, Any],
    version: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
) -> Mapping[UUID, to_date.ObligationAt]:
    """The obligation versions ``rows`` of a visible contract at the cut of ``as_of`` (04
    API-C-10 rev 1.132), by obligation-version id; ``to_date.Unreadable`` names a measure the
    version's trace cannot answer."""
    version_id = _uuid(version["id"])
    found = to_date.load_nodes(session, [version_id], balances=False)
    nodes = found.get(version_id, to_date.EMPTY)
    external_ids = {_uuid(contract_row["id"]): str(contract_row["external_id"])}
    at = to_date.version_at(version, rows, nodes=nodes, external_ids=external_ids, as_of=as_of)
    return at.obligations


def shown_statuses(session: Session, stored: Mapping[UUID, Any]) -> dict[UUID, str]:
    """E-17 of each contract as the contract reads show it (``_read_status``): its stored status,
    and ``PENDING_REVIEW`` while its activation awaits a decision — for a page of contracts in
    one statement (04 §16.13 rev 1.195: the search answers what the single read answers)."""
    in_review = _in_review(session, list(stored))
    return {
        contract_id: _read_status(status, in_review=contract_id in in_review)
        for contract_id, status in stored.items()
    }


def satisfaction_at(
    session: Session, obligation_ids: Sequence[UUID], *, now: datetime
) -> dict[UUID, str]:
    """E-22 of each obligation as ``obligations.obligation_out`` answers it without parameters
    (04 API-C-10; API-S-Obligation ``satisfaction_status``, rev 1.132): in the newest version of
    its contract's group in the primary book, at the cut of today in the entity's time zone — for
    a page of obligations in a constant number of statements (dev-guide DG-LST-10).

    An obligation has no entry while the book has no version that holds it, while its contract is
    not visible to the session, or while the version's trace cannot answer the cut
    (``to_date.Unreadable``, which the single read refuses by name)."""
    wanted = sorted(set(obligation_ids))
    if not wanted:
        return {}
    of_contract = and_(
        contract.c.tenant_id == obligation.c.tenant_id, contract.c.id == obligation.c.contract_id
    )
    of_entity = and_(
        legal_entity.c.tenant_id == contract.c.tenant_id,
        legal_entity.c.id == contract.c.contracting_entity_id,
    )
    owners = {
        _uuid(found["id"]): found
        for found in session.execute(
            select(
                obligation.c.id,
                contract.c.id.label("contract_id"),
                contract.c.external_id,
                contract.c.combination_group_id,
                legal_entity.c.time_zone,
            )
            .select_from(obligation.join(contract, of_contract).join(legal_entity, of_entity))
            .where(obligation.c.id.in_(wanted))
        ).mappings()
    }
    latest = _versions_of(
        session,
        (_uuid(found["combination_group_id"]) for found in owners.values()),
        book_code=primary_book(session),
        known_at=None,
    )
    versions = {_uuid(version["id"]): version for version in latest.values()}
    if not versions:
        return {}
    rows = session.execute(
        select(obligation_version).where(
            obligation_version.c.contract_version_id.in_(sorted(versions)),
            obligation_version.c.obligation_id.in_(sorted(owners)),
        )
    ).mappings()
    # One cut per version and day: the entities of a group's contracts share the group's version,
    # and each obligation is read at the today of its own contract's entity.
    at_cut: dict[tuple[UUID, date], list[dict[str, Any]]] = defaultdict(list)
    for stored in rows:
        owner = owners[_uuid(stored["obligation_id"])]
        version = latest.get(_uuid(owner["combination_group_id"]))
        if version is not None and _uuid(version["id"]) == _uuid(stored["contract_version_id"]):
            as_of = to_entity_date(now, str(owner["time_zone"]))
            at_cut[_uuid(version["id"]), as_of].append(dict(stored))
    traced = to_date.load_nodes(session, sorted(versions), balances=False)
    external_ids = {
        _uuid(found["contract_id"]): str(found["external_id"]) for found in owners.values()
    }
    statuses: dict[UUID, str] = {}
    for (version_id, as_of), held in at_cut.items():
        try:
            cut = to_date.version_at(
                versions[version_id],
                held,
                nodes=traced.get(version_id, to_date.EMPTY),
                external_ids=external_ids,
                as_of=as_of,
            )
        except to_date.Unreadable:
            continue
        for item in held:
            statuses[_uuid(item["obligation_id"])] = cut.obligations[
                _uuid(item["id"])
            ].satisfaction_status
    return statuses


def _links(contract_id: UUID, version: Mapping[str, Any] | None) -> ContractLinksOut:
    base = f"{API}/contracts/{contract_id}"
    return ContractLinksOut(
        self=base,
        obligations=f"{base}/obligations",
        events=f"{base}/events",
        versions=f"{base}/versions",
        allocation=f"{base}/allocation",
        schedule=f"{base}/schedule",
        balances=f"{base}/balances",
        history=f"{base}/history",
        explain_transaction_price=None
        if version is None
        else f"{API}/explain/contract_version/{version['id']}/transaction_price",
    )


def _build(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    params: ReadParams,
    now: datetime,
    detail: bool,
    refuse: bool = False,
) -> list[dict[str, Any]]:
    """API-S-Contract of each row; ``detail`` adds ``kpis.balances`` and ``links``. With ``refuse``
    a to-date measure the trace cannot answer is refused by name (04 API-C-10: the contract read);
    without it the item carries ``kpis: null`` (a list row, and the contract a command answers
    with: a command is not undone by the read of its result)."""
    if not rows:
        return []
    book_code = params.book or primary_book(session)
    ids = [_uuid(found["id"]) for found in rows]
    customers = _refs(session, customer, (found["customer_id"] for found in rows))
    entity_rows = {
        _uuid(found.id): found
        for found in session.execute(
            select(
                legal_entity.c.id,
                legal_entity.c.code,
                legal_entity.c.name,
                legal_entity.c.time_zone,
            ).where(legal_entity.c.id.in_({found["contracting_entity_id"] for found in rows}))
        )
    }
    group_ids = {
        contract_id: group_at(session, found, params.known_at)
        for contract_id, found in zip(ids, rows, strict=True)
    }
    groups = {
        _uuid(found["id"]): found
        for found in session.execute(
            select(combination_group).where(combination_group.c.id.in_(set(group_ids.values())))
        ).mappings()
    }
    members, member_counts = _members(session, group_ids.values(), params.known_at)
    latest = _versions_of(
        session, group_ids.values(), book_code=book_code, known_at=params.known_at
    )
    versions = {contract_id: latest.get(group_ids[contract_id]) for contract_id in ids}
    version_ids = sorted({_uuid(version["id"]) for version in versions.values() if version})
    # The version's figures are the group's, so its to-date movement reads every obligation of the
    # group (``obligation_version`` is tenant-wide), the contract's own obligations being a part.
    obligations: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    grouped: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for item in _obligation_versions(session, version_ids):
        obligations[_uuid(item["contract_id"])].append(item)
        grouped[_uuid(item["contract_version_id"])].append(item)
    balance_rows: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    if detail:
        for item in _balance_rows(session, version_ids, ids):
            balance_rows[_uuid(item["contract_id"])].append(item)
    terms = _terms(session, ids, params.known_at)
    own_ids = {
        contract_id: str(found["external_id"]) for contract_id, found in zip(ids, rows, strict=True)
    }
    enforceable = enforceable_terms(session, versions, own_ids)
    external_ids = _external_ids(session, own_ids, obligations)
    traced = to_date.load_nodes(session, version_ids, balances=detail)
    cuts: dict[tuple[UUID, date], to_date.VersionAt] = {}
    in_review = _in_review(session, ids)
    held = _held(session, ids)
    # API-S-Contract ``holds`` (detail): the open holds of the whole contract, read where a hold
    # stands at all — a list row answers ``on_hold`` alone.
    listed = hold_outs(session, sorted(held)) if detail else {}
    items: list[dict[str, Any]] = []
    for contract_id, found in zip(ids, rows, strict=True):
        version = versions[contract_id]
        entity = entity_rows[_uuid(found["contracting_entity_id"])]
        own = [
            item
            for item in obligations[contract_id]
            if version is not None and item["contract_version_id"] == version["id"]
        ]
        group = groups[group_ids[contract_id]]
        as_of = params.as_of or to_entity_date(now, str(entity.time_zone))
        kpis: dict[str, Any] | None = None
        context: ContextOut | None = None
        ratios = KpiRatiosOut(billed=None, recognized=None, pending_trigger_count=0)
        recognized: str | None = None
        if version is not None:
            version_id = _uuid(version["id"])
            nodes = traced.get(version_id, to_date.EMPTY)
            pending = sum(1 for item in own if Decimal(item["awaiting_trigger_amount"]) != 0)
            ratios = KpiRatiosOut(billed=None, recognized=None, pending_trigger_count=pending)
            measured: to_date.Measured | None = None
            try:
                if (version_id, as_of) not in cuts:
                    cuts[version_id, as_of] = to_date.version_at(
                        version,
                        grouped[version_id],
                        nodes=nodes,
                        external_ids=external_ids,
                        as_of=as_of,
                    )
                cut = cuts[version_id, as_of]
                shown = _moved(version, cut)
                # a trigger is pending for an obligation that still awaits one at the cut
                pending = sum(1 for item in own if cut.obligations[_uuid(item["id"])].awaiting != 0)
                measured = to_date.measured_at(
                    version,
                    nodes=nodes,
                    external_id=own_ids[contract_id],
                    entity_code=str(entity.code),
                    as_of=as_of,
                )
                balances = [
                    (
                        item,
                        to_date.balance_at(
                            item,
                            version=version,
                            nodes=nodes,
                            external_id=own_ids[contract_id],
                            moved=to_date.net_moved(own, cut.obligations, item),
                            as_of=as_of,
                        ),
                    )
                    for item in balance_rows[contract_id]
                ]
            except (to_date.Unreadable, tie_outs.BalanceUnreadable):
                # 04 API-C-10: a measure the trace cannot answer is refused by name on the contract
                # read; a list row or a command's answer carries no figure in its place.
                if refuse:
                    raise
                measured = None
            else:
                kpis = _kpis(shown)
                recognized = _ratio(shown["revenue_cum"], shown["transaction_price"])
                ratios = KpiRatiosOut(
                    billed=_ratio(shown["billed_cum"], shown["transaction_price"]),
                    recognized=recognized,
                    pending_trigger_count=pending,
                )
                if detail:
                    kpis["balances"] = [
                        {
                            "entity": RefOut(
                                id=item["entity_id"],
                                code=item["entity_code"],
                                name=item["entity_name"],
                            ),
                            **{
                                name: _money(at.values[name], item["txn_currency"])
                                for name in HEADER_BALANCES
                            },
                            "links": _balance_links(item["id"], at),
                        }
                        for item, at in balances
                    ]
            context = ContextOut(
                book=BookCode(book_code),
                as_of=as_of,
                known_at=params.known_at or now,
                contract_version_id=version["id"],
                version_no=version["version_no"],
                computed_at=version["computed_at"],
                measured_period=measured_out(measured),
            )
        termination = None
        if found["termination_party"] is not None:
            termination = TerminationOut(
                party=found["termination_party"],
                has_penalty=found["termination_has_penalty"],
                notice_days=found["termination_notice_days"],
            )
        out: dict[str, Any] = {
            "id": contract_id,
            "contract_no": found["contract_no"],
            "external_id": found["external_id"],
            "status": _read_status(found["status"], in_review=contract_id in in_review),
            "customer": customers[_uuid(found["customer_id"])],
            "contracting_entity": RefOut(id=entity.id, code=entity.code, name=entity.name),
            "transaction_currency": str(found["transaction_currency"]).strip(),
            "inception_date": found["inception_date"],
            "combination_group": CombinationGroupOut(
                id=group["id"],
                code=group["code"],
                is_singleton=group["is_singleton"],
                member_contract_ids=members.get(group_ids[contract_id], []),
                member_count=member_counts.get(group_ids[contract_id], 0),
            ),
            "head_stream_version": found["head_stream_version"],
            "signature_date": found["signature_date"],
            "document_ref": found["document_ref"],
            "payment_terms": found["payment_terms"],
            "termination": termination,
            "has_commercial_substance": found["has_commercial_substance"],
            "region": found["region"],
            "channel": found["channel"],
            "contract_type": found["contract_type"],
            "memo_1": found["memo_1"],
            "memo_2": found["memo_2"],
            "memo_3": found["memo_3"],
            "custom_attributes": dict(found["custom_attributes"] or {}),
            "activation_checklist": found["activation_checklist"],
            "activated_at": found["activated_at"],
            "completed_at": found["completed_at"],
            "terminated_at": found["terminated_at"],
            "voided_at": found["voided_at"],
            "renewal_of_contract_id": found["renewal_of_contract_id"],
            "source_system": found["source_system"],
            "on_hold": contract_id in held,
            "open_exception_count": 0,
            "status_reason": None if version is None else version["status_reason_in_book"],
            "scope_605_35": found["scope_605_35"],
            **{name: terms[contract_id].get(name, []) for name in TERM_MEMBERS},
            "steps": _steps(
                version,
                own,
                in_review=contract_id in in_review,
                term=enforceable.get(contract_id),
                recognized=recognized,
            ),
            "kpis_ratios": ratios,
            "context": context,
            "kpis": kpis,
            "created_at": found["created_at"],
            "updated_at": found["updated_at"],
        }
        if detail:
            out["holds"] = listed.get((contract_id, None), [])
            out["links"] = _links(contract_id, version)
        items.append(out)
    return items


def contract_out(
    session: Session,
    contract_id: UUID,
    *,
    params: ReadParams | None = None,
    now: datetime,
    refuse: bool = False,
) -> ContractOut:
    """API-S-Contract of a visible contract in ``session``; 404 ``not-found`` otherwise. A command
    builds its answer without ``refuse``: to-date measures its trace cannot answer leave ``kpis``
    null instead of undoing the command."""
    found = repo.get_contract(session, contract_id)
    (item,) = _build(
        session, [found], params=params or ReadParams(), now=now, detail=True, refuse=refuse
    )
    return ContractOut.model_validate(item)


def get_contract(
    ctx: RequestContext, contract_id: UUID, *, params: ReadParams, now: datetime
) -> ContractOut:
    """``GET /contracts/{id}``: a to-date measure the trace cannot answer is refused by name."""
    return read(
        ctx,
        lambda session: contract_out(session, contract_id, params=params, now=now, refuse=True),
    )


def contract_list_items(
    session: Session, rows: Sequence[Mapping[str, Any]], *, params: ReadParams, now: datetime
) -> list[ContractListItemOut]:
    return [
        ContractListItemOut.model_validate(item)
        for item in _build(session, rows, params=params, now=now, detail=False)
    ]


# --- GET /contracts -------------------------------------------------------------------------------

_LIST_VERSION: Final = contract_version.alias("list_version")
_PRIMARY_BOOK: Final = select(book.c.code).where(book.c.is_primary.is_(True)).scalar_subquery()
_LIST_PRICE_VALUE: Final = (
    select(_LIST_VERSION.c.transaction_price)
    .where(
        _LIST_VERSION.c.tenant_id == contract.c.tenant_id,
        _LIST_VERSION.c.combination_group_id == contract.c.combination_group_id,
        _LIST_VERSION.c.book_code == _PRIMARY_BOOK,
    )
    .order_by(_LIST_VERSION.c.version_no.desc())
    .limit(1)
    .scalar_subquery()
)
# The sort key ``transaction_price``: the latest primary-book version's price (L3-1-Q-40).
LIST_PRICE: Final = _LIST_PRICE_VALUE.label("transaction_price")


def _on_hold_clause() -> Any:
    """API-S-Contract ``on_hold``: any open hold (04 §16.1, T-CON-20; BUILD_SPEC CTR-10)."""
    return exists(
        select(contract_hold.c.id).where(
            contract_hold.c.tenant_id == contract.c.tenant_id,
            contract_hold.c.contract_id == contract.c.id,
            contract_hold.c.released_at.is_(None),
        )
    )


def _held(session: Session, contract_ids: Sequence[UUID]) -> set[UUID]:
    """The contracts with an open hold (T-CON-20)."""
    statement = select(contract_hold.c.contract_id).where(
        contract_hold.c.contract_id.in_(list(contract_ids)), contract_hold.c.released_at.is_(None)
    )
    return {_uuid(found) for found in session.execute(statement).scalars()}


def hold_outs(
    session: Session, contract_ids: Iterable[Any]
) -> dict[tuple[UUID, UUID | None], list[HoldOut]]:
    """API-S-Contract and API-S-Obligation ``holds`` (04 §16.1, §16.2 rev 1.299; item
    HOLD-RELEASE-READ-1): the open holds of the contracts the session sees
    (``holds.listed_holds``), each as the member's model, under (contract id, obligation id) —
    obligation None for a hold of the whole contract. ``holds`` answers its commands with this
    module's ``contract_out``, so it is imported here and not at the head of the module, as
    ``compute_job`` imports the modules that import it."""
    from erev_api.domain.contracts import holds

    rows = holds.listed_holds(session, contract_ids)
    names = _actor_names(
        session,
        [
            {"actor_id": row["applied_by"], "actor_kind": _text(row["applied_by_kind"])}
            for row in rows
        ],
    )
    outs: dict[tuple[UUID, UUID | None], list[HoldOut]] = {}
    for row in rows:
        applied_by = row["applied_by"]
        obligation_id = None if row["obligation_id"] is None else _uuid(row["obligation_id"])
        outs.setdefault((_uuid(row["contract_id"]), obligation_id), []).append(
            HoldOut(
                id=row["id"],
                level=row["level"],
                hold_type=row["hold_type"],
                hold_source=row["hold_source"],
                reason=row["reason"],
                applied_by=ActorOut(
                    id=applied_by,
                    kind=row["applied_by_kind"],
                    display_name=SYSTEM_DISPLAY_NAME
                    if applied_by is None
                    else names.get(_uuid(applied_by), SYSTEM_DISPLAY_NAME),
                ),
                applied_at=row["applied_at"],
                release_refusal=row["release_refusal"],
            )
        )
    return outs


def _created_this_period(now: datetime) -> Any:
    """Created within the period of the contracting entity's calendar that contains today."""
    today = sql_cast(func.timezone(legal_entity.c.time_zone, literal(now)), Date)
    created = sql_cast(func.timezone(legal_entity.c.time_zone, contract.c.created_at), Date)
    return exists(
        select(period.c.id).where(
            period.c.tenant_id == contract.c.tenant_id,
            period.c.calendar_id == legal_entity.c.calendar_id,
            period.c.start_date <= today,
            period.c.end_date >= today,
            period.c.start_date <= created,
            period.c.end_date >= created,
        )
    )


def list_statement(filters: ListFilters, *, now: datetime) -> Select[Any]:
    """The visible contracts under ``filters`` with the ``transaction_price`` sort column."""
    tenant = contract.c.tenant_id
    statement = select(contract, LIST_PRICE).select_from(
        contract.join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant,
                legal_entity.c.id == contract.c.contracting_entity_id,
            ),
        ).join(
            customer, and_(customer.c.tenant_id == tenant, customer.c.id == contract.c.customer_id)
        )
    )
    if filters.entity:
        statement = statement.where(
            or_(
                *(
                    _key_or_id(legal_entity.c.code, legal_entity.c.id, item)
                    for item in filters.entity
                )
            )
        )
    if filters.customer:
        statement = statement.where(
            or_(*(_key_or_id(customer.c.code, customer.c.id, item) for item in filters.customer))
        )
    if filters.value_min is not None:
        statement = statement.where(_LIST_PRICE_VALUE >= filters.value_min)
    if filters.value_max is not None:
        statement = statement.where(_LIST_PRICE_VALUE <= filters.value_max)
    if filters.on_hold is not None:
        clause = _on_hold_clause()
        statement = statement.where(clause if filters.on_hold else not_(clause))
    if filters.has_exceptions:
        # [J] L3-1-Q-40: T-IMP-05 exception items arrive with CTR-5, so no contract has one yet.
        statement = statement.where(false())
    if filters.modified_in_period is not None:
        # [J] L3-1-Q-40: T-CON-06 modifications are post-rc (R-RC-1, CTR-17).
        statement = statement.where(false())
    match filters.quick_list:
        case ContractQuickList.ON_HOLD:
            statement = statement.where(_on_hold_clause())
        case ContractQuickList.CREATED_MANUALLY:
            statement = statement.where(contract.c.source_system == SourceSystem.MANUAL_UI.value)
        case ContractQuickList.CREATED_FROM_INTEGRATIONS_THIS_PERIOD:
            statement = statement.where(
                contract.c.source_system.in_(INTEGRATION_SOURCES), _created_this_period(now)
            )
        case ContractQuickList.RECENTLY_VIEWED | ContractQuickList.MODIFIED_THIS_PERIOD:
            # [J] L3-1-Q-40: no store of opened contracts and no modifications exist yet.
            statement = statement.where(false())
        case ContractQuickList.LARGEST_VALUE | None:
            pass
    return statement


def list_contracts[T](
    ctx: RequestContext,
    filters: ListFilters,
    *,
    now: datetime,
    page: Callable[[Session, Select[Any]], T],
) -> T:
    """One page of contracts; ``page`` applies the list parameters and builds the items."""
    return read(ctx, lambda session: page(session, list_statement(filters, now=now)))


# --- versions ------------------------------------------------------------------------------------


def versions_statement(
    session: Session, contract_id: UUID, *, book_code: str | None
) -> Select[Any]:
    """The versions of the contract's current group in the book (default the primary book)."""
    found = repo.get_contract(session, contract_id)
    return _versions().where(
        contract_version.c.combination_group_id == found["combination_group_id"],
        contract_version.c.book_code == (book_code or primary_book(session)),
    )


def _cause_events(
    session: Session, versions: Sequence[Mapping[str, Any]]
) -> dict[UUID, CauseEventOut]:
    ids = sorted({_uuid(value) for version in versions for value in version["cause_event_ids"]})
    if not ids:
        return {}
    statement = (
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.recorded_at,
        )
        .where(contract_event.c.id.in_(ids))
        .order_by(contract_event.c.record_seq)
    )
    return {
        _uuid(found.id): CauseEventOut(
            id=found.id,
            event_type=_text(found.event_type) or "",
            effective_date=found.effective_date,
            recorded_at=found.recorded_at,
        )
        for found in session.execute(statement)
    }


def _version_fields(
    version: Mapping[str, Any], events: Mapping[UUID, CauseEventOut]
) -> dict[str, Any]:
    currency = version["transaction_currency"]

    def money(name: str) -> MoneyOut:
        return _money(version[name], currency)

    cause = [_uuid(value) for value in version["cause_event_ids"]]
    return {
        "id": version["id"],
        "version_no": version["version_no"],
        "book": version["book_code"],
        "known_at": version["known_at"],
        "cause_events": [events[value] for value in events if value in cause],
        "engine_version": version["engine_version"],
        "input_sha256": str(version["input_sha256"]),
        "output_sha256": str(version["output_sha256"]),
        "status_in_book": version["status_in_book"],
        "status_reason_in_book": version["status_reason_in_book"],
        "transaction_price_buildup": TransactionPriceBuildupOut(
            fixed=money("fixed_consideration"),
            vc_constrained=money("vc_constrained_amount"),
            vc_excluded=money("vc_excluded_amount"),
            expected_returns=money("expected_returns_amount"),
            consideration_payable=money("consideration_payable_amount"),
            financing_adjustment=money("financing_adjustment_amount"),
            noncash=money("noncash_consideration_amount"),
            sales_tax_excluded=money("sales_tax_excluded_amount"),
            out_of_scope=money("out_of_scope_amount"),
            total=money("transaction_price"),
        ),
        "total_ssp": _exact(version["total_ssp"]),
        "revenue_to_date": money("revenue_cum"),
        "billed_to_date": money("billed_cum"),
        "rpo": money("rpo_amount"),
        "scheduled": money("scheduled_amount"),
        "awaiting_trigger": money("awaiting_trigger_amount"),
        "modification_boundary_no": version["modification_boundary_no"],
        "pinned_refs": dict(version["pinned_refs"] or {}),
        "pinned_policies": dict(version["pinned_policies"] or {}),
    }


def version_summaries(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> list[ContractVersionSummaryOut]:
    events = _cause_events(session, rows)
    return [ContractVersionSummaryOut.model_validate(_version_fields(row, events)) for row in rows]


def _balance_links(balance_id: Any, at: to_date.BalanceAt | None) -> BalanceLinksOut:
    """The Explain addresses of a T-CON-09 row's balances (item EXPLAIN-BALANCE-LINKS-1; 04
    §16.11): the route takes the row's id, which only these links carry. At a cut each names the
    period the balance was read at; a cut before the first period the version measures has no
    node to explain, so the links are null. Without a cut (``at`` None: the version read) they
    name no period and explain the stored figure, the node of the version's latest period."""
    period = ""
    if at is not None:
        if at.measured is None:
            return BalanceLinksOut()
        period = f"?period={at.measured.period_key}"
    base = f"{API}/explain/contract_version_balance/{balance_id}"
    return BalanceLinksOut(
        **{f"explain_{name}": f"{base}/{name}{period}" for name in EXPLAINED_BALANCES}
    )


def _explain_link(version_id: Any, measure: str, measured: to_date.Measured | None) -> str:
    """The Explain link of an obligation version's to-date measure: the period node read at the
    cut when there is one (04 API-S-Obligation ``links``, rev 1.132), else the version's node."""
    link = f"{API}/explain/obligation_version/{version_id}/{measure}"
    return link if measured is None else f"{link}?period={measured.period_key}"


def obligation_outs(
    session: Session,
    version: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    context: ContextOut,
    at: Mapping[UUID, to_date.ObligationAt] | None = None,
) -> list[ObligationOut]:
    """API-S-Obligation of each obligation version (holds and material rights: L3-1-Q-38).

    With ``at`` (``obligations_at``) the to-date members are served at the cut of the context's
    ``as_of`` and each item's context names the period they were read at (04 API-C-10 rev 1.132);
    without it the rows answer the version as stored (the version reads)."""
    products = _refs(session, product, (row["product_id"] for row in rows))
    entities = _entity_refs(
        session,
        [row["contracting_entity_id"] for row in rows]
        + [row["performing_entity_id"] for row in rows],
    )
    template_ids = sorted({_uuid(row["pob_template_version_id"]) for row in rows})
    templates: dict[UUID, TemplateVersionRefOut] = {}
    if template_ids:
        statement = (
            select(
                pob_template_version.c.id, pob_template_version.c.version_no, pob_template.c.code
            )
            .select_from(
                pob_template_version.join(
                    pob_template,
                    and_(
                        pob_template.c.tenant_id == pob_template_version.c.tenant_id,
                        pob_template.c.id == pob_template_version.c.pob_template_id,
                    ),
                )
            )
            .where(pob_template_version.c.id.in_(template_ids))
        )
        templates = {
            _uuid(found.id): TemplateVersionRefOut(
                id=found.id, template_code=found.code, version_no=found.version_no
            )
            for found in session.execute(statement)
        }
    codes = sorted(
        {str(code) for row in rows for code in (row["account_overrides"] or {}).values()}
    )
    accounts: dict[str, RefOut] = {}
    if codes:
        statement = select(gl_account.c.id, gl_account.c.code, gl_account.c.name).where(
            gl_account.c.code.in_(codes)
        )
        accounts = {
            str(found.code): RefOut(id=found.id, code=found.code, name=found.name)
            for found in session.execute(statement)
        }
    policy = _outside_policy(version)
    # API-S-Obligation ``holds`` (04 §16.2 rev 1.299): the obligation's open holds, in the reads
    # that serve the obligation at a cut; a version read lists none.
    listed = {} if at is None else hold_outs(session, {row["contract_id"] for row in rows})
    outs: list[ObligationOut] = []
    for row in rows:
        currency = str(row["txn_currency"]).strip()

        def money(name: str, source: Mapping[str, Any] = row, unit: str = currency) -> MoneyOut:
            return _money(source[name], unit)

        position = range_position(
            row["original_ssp_low"], row["original_ssp_high"], row["original_stated_price"]
        )
        obligation_id = row["obligation_id"]
        version_id = row["id"]
        # The to-date members: the stored row is the obligation at d_v; ``found`` moves it to the
        # cut (Δ of revenue, the billing since d_v and the movement of the returns reduction).
        found = None if at is None else at[_uuid(version_id)]
        allocated = Decimal(row["allocated_amount"])
        revenue = Decimal(row["revenue_cum"])
        billed = Decimal(row["billed_cum"])
        progress = row["progress_ratio"]
        remaining = Decimal(row["remaining_allocation"])
        remaining_billing = Decimal(row["remaining_billing"])
        scheduled = Decimal(row["scheduled_amount"])
        awaiting = Decimal(row["awaiting_trigger_amount"])
        net = Decimal(row["position_obligation"])
        status = _text(row["satisfaction_status"]) or ""
        own = context
        if found is not None:
            allocated -= found.shift
            revenue, billed, progress = found.revenue, found.billed, found.progress_ratio
            remaining -= found.delta + found.shift
            remaining_billing -= found.billed_delta
            scheduled, awaiting = found.scheduled, found.awaiting
            net = billed - revenue  # ENGINE_SPEC_B S10-R-12
            status = found.satisfaction_status
            own = context.model_copy(update={"measured_period": measured_out(found.measured)})
        label = "CONTRACT_LIABILITY" if net > 0 else "CONTRACT_ASSET" if net < 0 else "NONE"
        overrides = {
            str(role): accounts[str(code)]
            for role, code in (row["account_overrides"] or {}).items()
            if str(code) in accounts
        }
        outs.append(
            ObligationOut(
                id=obligation_id,
                obligation_version_id=version_id,
                contract_id=row["contract_id"],
                obligation_key=row["obligation_key"],
                legacy_record_key=row["legacy_record_key"],
                product=products[_uuid(row["product_id"])],
                stratification=row["stratification"],
                obligation_kind=_text(row["obligation_kind"]) or "",
                distinctness=_text(row["distinctness"]) or "",
                series_increment_unit=row["series_increment_unit"],
                pob_template_version=templates[_uuid(row["pob_template_version_id"])],
                scope_flag=_text(row["scope_flag"]) or "",
                satisfaction_pattern=_text(row["satisfaction_pattern"]) or "",
                over_time_criterion=_text(row["over_time_criterion"]) or "",
                recognition_method=_text(row["recognition_method"]) or "",
                ratable_convention=_text(row["ratable_convention"]),
                principal_agent=_text(row["principal_agent"]) or "",
                licence_nature=_text(row["licence_nature"]) or "",
                warranty_type=_text(row["warranty_type"]) or "",
                start_date=row["start_date"],
                end_date=row["end_date"],
                contracting_entity=entities[_uuid(row["contracting_entity_id"])],
                performing_entity=entities[_uuid(row["performing_entity_id"])],
                currency=currency,
                memo_1=row["memo_1"],
                memo_2=row["memo_2"],
                memo_3=row["memo_3"],
                account_overrides=overrides,
                original=ObligationOriginalOut(
                    quantity=_exact(row["original_quantity"]),
                    ssp_low=_maybe_exact(row["original_ssp_low"]),
                    ssp_mid=_maybe_exact(row["original_ssp_mid"]),
                    ssp_high=_maybe_exact(row["original_ssp_high"]),
                    ssp_selected=_exact(row["original_ssp_selected"]),
                    total_contract_ssp=_exact(row["original_total_contract_ssp"]),
                    unit_ssp=_maybe_exact(row["original_unit_ssp"]),
                    unit_revenue_rate=_maybe_exact(row["original_unit_revenue_rate"]),
                    stated_price=money("original_stated_price"),
                    allocated_amount=money("original_allocated_amount"),
                    total_contract_price=money("original_total_contract_price"),
                    ssp_in_range=row["original_ssp_in_range"],
                ),
                current=ObligationCurrentOut(
                    quantity=_exact(row["quantity"]),
                    allocation_weight=_exact(row["allocation_weight"]),
                    unit_ssp=_maybe_exact(row["unit_ssp"]),
                    remaining_unit_revenue_rate=_maybe_exact(row["remaining_unit_revenue_rate"]),
                    stated_price=money("stated_price"),
                    allocated_amount=_money(allocated, currency),
                    allocation_adjustment=money("allocation_adjustment"),
                ),
                ssp=ObligationSspOut(
                    book_version_id=row["ssp_book_version_id"],
                    version_label=row["ssp_version_label"],
                    entry_id=row["ssp_entry_id"],
                    method=_text(row["ssp_method"]),
                    unit_list_price=_maybe_exact(row["ssp_unit_list_price"]),
                    midpoint_discount_ratio=_maybe_exact(row["ssp_midpoint_discount_ratio"]),
                    range_ratio=_maybe_exact(row["ssp_range_ratio"]),
                    override_approval_request_id=row["ssp_override_approval_request_id"],
                    range_position=position,
                    outside_range_point=_outside_point(position, policy),
                ),
                to_date=ObligationToDateOut(
                    delivered_quantity=_exact(row["delivered_quantity_cum"]),
                    returned_quantity=_exact(row["returned_quantity_cum"]),
                    progress_ratio=_exact(progress),
                    ssp_delivered=_exact(row["ssp_delivered_cum"]),
                    revenue=_money(revenue, currency),
                    billed=_money(billed, currency),
                    catch_up=money("catch_up_cum"),
                    catch_up_modification=money("catch_up_modification_cum"),
                    catch_up_tp_change=money("catch_up_tp_change_cum"),
                    catch_up_estimate=money("catch_up_estimate_cum"),
                    pre_standard_revenue=money("pre_standard_revenue_cum"),
                ),
                remaining=ObligationRemainingOut(
                    quantity=_exact(row["remaining_quantity"]),
                    ssp=_exact(row["remaining_ssp"]),
                    allocation=_money(remaining, currency),
                    billing=_money(remaining_billing, currency),
                ),
                scheduled=_money(scheduled, currency),
                awaiting_trigger=_money(awaiting, currency),
                ratios=ObligationRatiosOut(
                    recognized=_ratio(revenue, allocated),
                    scheduled=_ratio(scheduled, allocated),
                    awaiting_trigger=_ratio(awaiting, allocated),
                ),
                position=PositionOut(label=label, amount=_money(abs(net), currency)),
                netting_reclass=NettingReclassOut(
                    amount=money("netting_reclass_amount"),
                    role=_text(row["netting_reclass_role"]),
                ),
                satisfaction_status=status,
                satisfied_date=row["satisfied_date"],
                holds=listed.get((_uuid(row["contract_id"]), _uuid(obligation_id)), []),
                material_right=None,
                context=own,
                links=ObligationLinksOut(
                    self=f"{API}/obligations/{obligation_id}",
                    versions=f"{API}/obligations/{obligation_id}/versions",
                    schedule=f"{API}/obligations/{obligation_id}/schedule",
                    events=f"{API}/obligations/{obligation_id}/events",
                    explain_revenue_to_date=_explain_link(
                        version_id, to_date.REVENUE, None if found is None else found.measured
                    ),
                    explain_billed_to_date=_explain_link(
                        version_id, to_date.BILLED, None if found is None else found.billed_measured
                    ),
                    explain_allocated_amount=(
                        f"{API}/explain/obligation_version/{version_id}/allocated_amount"
                    ),
                ),
            )
        )
    return outs


def balance_outs(
    rows: Sequence[Mapping[str, Any]],
    *,
    context: ContextOut,
    at: Mapping[UUID, to_date.BalanceAt] | None = None,
) -> list[ContractBalanceOut]:
    """API-S-ContractBalance of each T-CON-09 row (L3-1-Q-38 for the functional members).

    With ``at`` (``to_date.balance_at`` by row id) the balances are those of the cut of the
    context's ``as_of`` and each item's context names the period read (04 rev 1.132): the engine
    publishes no functional balance node per period, so at a cut earlier than the version's latest
    period every functional member is null. Without it the rows are the version's stored balances,
    those of its latest period (API-S-ContractVersion)."""
    outs: list[ContractBalanceOut] = []
    for row in rows:
        txn = str(row["txn_currency"]).strip()
        functional = str(row["functional_currency"]).strip()
        found = None if at is None else at[_uuid(row["id"])]
        stored = found is None or found.latest
        outs.append(
            ContractBalanceOut(
                contract_id=row["contract_id"],
                entity=RefOut(
                    id=row["entity_id"], code=row["entity_code"], name=row["entity_name"]
                ),
                book=row["book_code"],
                net_position=_money(
                    row["net_position_txn"] if found is None else found.net_position, txn
                ),
                **{
                    name: _money(row[f"{name}_txn"] if found is None else found.values[name], txn)
                    for name in BALANCE_NAMES
                },
                functional=ContractBalanceFunctionalOut(
                    **{
                        name: _money(row[f"{name}_functional"], functional)
                        if stored and f"{name}_functional" in row
                        else None
                        for name in ("net_position", *BALANCE_NAMES)
                    }
                ),
                links=_balance_links(row["id"], found),
                context=context
                if found is None
                else context.model_copy(update={"measured_period": measured_out(found.measured)}),
            )
        )
    return outs


def _context(
    session: Session,
    contract_row: Mapping[str, Any],
    version: Mapping[str, Any],
    *,
    params: ReadParams,
    now: datetime,
) -> ContextOut:
    return ContextOut(
        book=BookCode(version["book_code"]),
        as_of=_as_of(session, contract_row, params, now),
        known_at=params.known_at or now,
        contract_version_id=version["id"],
        version_no=version["version_no"],
        computed_at=version["computed_at"],
    )


def get_version(
    ctx: RequestContext,
    contract_id: UUID,
    version_no: int,
    *,
    params: ReadParams,
    now: datetime,
) -> ContractVersionOut:
    """API-S-ContractVersion with the contract's obligations and balances at the version: the
    version as stored, whatever ``as_of`` (04 API-C-10 rev 1.132)."""

    def load(session: Session) -> ContractVersionOut:
        found = repo.get_contract(session, contract_id)
        version = _version_numbered(
            session, found, params.book or primary_book(session), version_no
        )
        context = _context(session, found, version, params=params, now=now)
        obligations = obligation_outs(
            session,
            version,
            _obligation_versions(session, [version["id"]], contract_ids=[contract_id]),
            context=context,
        )
        balances = balance_outs(
            _balance_rows(session, [version["id"]], [contract_id]), context=context
        )
        fields = _version_fields(version, _cause_events(session, [version]))
        return ContractVersionOut.model_validate(
            {**fields, "obligations": obligations, "balances": balances}
        )

    return read(ctx, load)


def _plain(column: Column[Any], value: Any, currency: str) -> Any:
    """A JSON value of a stored column; money at the currency's minor unit, exact values trimmed."""
    if value is None:
        return None
    if isinstance(column.type, MoneyType):
        return _money(value, currency).amount
    if isinstance(column.type, ExactType):
        return _exact(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [_text(item) for item in value]
    return value


def _changes(
    columns: Iterable[Column[Any]],
    skipped: frozenset[str],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    currency: tuple[str, str],
    obligation_key: str | None,
) -> list[VersionChangeOut]:
    changes: list[VersionChangeOut] = []
    for column in columns:
        if column.name in skipped:
            continue
        old = _plain(column, before[column.name], currency[0])
        new = _plain(column, after[column.name], currency[1])
        if old != new:
            changes.append(
                VersionChangeOut(
                    field=column.name, obligation_key=obligation_key, before=old, after=new
                )
            )
    return changes


def compare_versions(
    ctx: RequestContext, contract_id: UUID, *, from_no: int, to_no: int, book_code: str | None
) -> VersionCompareOut:
    """REQ-CON-014: the fields whose values differ between two versions of the group and book
    ([J] L3-1-Q-39)."""

    def load(session: Session) -> VersionCompareOut:
        found = repo.get_contract(session, contract_id)
        code = book_code or primary_book(session)
        before = _version_numbered(session, found, code, from_no)
        after = _version_numbered(session, found, code, to_no)
        currencies = (
            str(before["transaction_currency"]).strip(),
            str(after["transaction_currency"]).strip(),
        )
        changes = _changes(
            contract_version.c,
            VERSION_SKIPPED,
            before,
            after,
            currency=currencies,
            obligation_key=None,
        )
        old = {
            (_uuid(item["contract_id"]), str(item["obligation_key"])): item
            for item in _obligation_versions(session, [before["id"]])
        }
        new = {
            (_uuid(item["contract_id"]), str(item["obligation_key"])): item
            for item in _obligation_versions(session, [after["id"]])
        }
        for key in [*new, *(key for key in old if key not in new)]:
            earlier, later = old.get(key), new.get(key)
            if earlier is None or later is None:
                changes.append(
                    VersionChangeOut(
                        field="obligation",
                        obligation_key=key[1],
                        before=None if earlier is None else key[1],
                        after=None if later is None else key[1],
                    )
                )
                continue
            changes += _changes(
                obligation_version.c,
                OBLIGATION_SKIPPED,
                earlier,
                later,
                currency=(
                    str(earlier["txn_currency"]).strip(),
                    str(later["txn_currency"]).strip(),
                ),
                obligation_key=key[1],
            )

        def ref(version: Mapping[str, Any]) -> VersionRefOut:
            return VersionRefOut(
                id=version["id"], version_no=version["version_no"], known_at=version["known_at"]
            )

        return VersionCompareOut(
            book=BookCode(code), from_version=ref(before), to_version=ref(after), changes=changes
        )

    return read(ctx, load)


# --- balances and the allocation walk ----------------------------------------------------------


def balances(
    ctx: RequestContext, contract_id: UUID, *, params: ReadParams, now: datetime
) -> list[ContractBalanceOut]:
    def load(session: Session) -> list[ContractBalanceOut]:
        found = repo.get_contract(session, contract_id)
        version = version_at(
            session, found, book_code=params.book or primary_book(session), known_at=params.known_at
        )
        if version is None:
            return []
        context = _context(session, found, version, params=params, now=now)
        rows = _balance_rows(session, [version["id"]], [contract_id])
        version_id = _uuid(version["id"])
        nodes = to_date.load_nodes(session, [version_id]).get(version_id, to_date.EMPTY)
        external_id = str(found["external_id"])
        own = _obligation_versions(session, [version_id], contract_ids=[contract_id])
        moved = to_date.version_at(
            version,
            own,
            nodes=nodes,
            external_ids={_uuid(contract_id): external_id},
            as_of=context.as_of,
        ).obligations
        at = {
            _uuid(row["id"]): to_date.balance_at(
                row,
                version=version,
                nodes=nodes,
                external_id=external_id,
                moved=to_date.net_moved(own, moved, row),
                as_of=context.as_of,
            )
            for row in rows
        }
        return balance_outs(rows, context=context, at=at)

    return read(ctx, load)


def allocation_walk(
    ctx: RequestContext, contract_id: UUID, *, params: ReadParams, now: datetime
) -> AllocationWalkOut:
    """API-S-AllocationWalk of the version in context over the group's obligations (REQ-ALC-009;
    [J] L3-1-Q-38): the range test and selected SSP of the original allocation, the current weight,
    exact quota, rounding residue (exact − allocated) and allocated amount."""

    def load(session: Session) -> AllocationWalkOut:
        found = repo.get_contract(session, contract_id)
        version = version_at(
            session, found, book_code=params.book or primary_book(session), known_at=params.known_at
        )
        if version is None:
            raise Problem("not-found", "The contract has no computed version yet.")
        rows = _obligation_versions(session, [version["id"]])
        products = _refs(session, product, (row["product_id"] for row in rows))
        policy = _outside_policy(version)
        currency = str(version["transaction_currency"]).strip()
        lines: list[AllocationLineOut] = []
        allocated_total = Decimal(0)
        adjustment_total = Decimal(0)
        for row in rows:
            unit = str(row["txn_currency"]).strip()
            allocated = Decimal(row["allocated_amount"])
            exact = Decimal(row["allocated_exact"])
            adjustment = Decimal(row["allocation_adjustment"])
            allocated_total += allocated
            adjustment_total += adjustment
            position = range_position(
                row["original_ssp_low"], row["original_ssp_high"], row["original_stated_price"]
            )
            lines.append(
                AllocationLineOut(
                    obligation_key=row["obligation_key"],
                    product=products[_uuid(row["product_id"])],
                    ssp_book_version=None
                    if row["ssp_book_version_id"] is None
                    else SspVersionRefOut(
                        id=row["ssp_book_version_id"], label=row["ssp_version_label"]
                    ),
                    ssp_entry_id=row["ssp_entry_id"],
                    ssp_method=_text(row["ssp_method"]),
                    low=_maybe_exact(row["original_ssp_low"]),
                    mid=_maybe_exact(row["original_ssp_mid"]),
                    high=_maybe_exact(row["original_ssp_high"]),
                    stated_price=_money(row["stated_price"], unit),
                    in_range=row["original_ssp_in_range"],
                    range_position=position,
                    outside_range_point=_outside_point(position, policy),
                    selected_ssp=_exact(row["original_ssp_selected"]),
                    weight=_exact(row["allocation_weight"]),
                    exact_quota=_exact(exact),
                    rounding_residue=format_exact(exact - allocated),
                    allocated=_money(allocated, unit),
                    allocation_adjustment=_money(adjustment, unit),
                )
            )
        return AllocationWalkOut(
            context=_context(session, found, version, params=params, now=now),
            transaction_price=_money(version["transaction_price"], currency),
            total_ssp=_exact(version["total_ssp"]),
            lines=lines,
            totals=AllocationTotalsOut(
                allocated=_money(allocated_total, currency),
                allocation_adjustment=_money(adjustment_total, currency),
            ),
        )

    return read(ctx, load)


# --- schedule and subledger lines -----------------------------------------------------------------


def _line_state(known_at: datetime | None) -> Any:
    """API-S-ScheduleLine ``state`` (04 rev 1.132; supervisor rulings R-76 (b) and R-79 (f)): a
    ``REVENUE`` schedule line of an obligation is RECOGNIZED when a ledger line recorded by
    ``known_at`` exists for its contract, obligation, book and the ``REVENUE`` role in its period —
    the ledger line's origin period when it has one, else its posting period. The engine posts
    cumulative role deltas and a posting intent names no schedule line, so
    ``subledger_line.schedule_line_id`` stays unwritten and is not the rule. A line of another
    schedule kind reads SCHEDULED."""
    posted = select(subledger_line.c.id).where(
        subledger_line.c.tenant_id == schedule_line.c.tenant_id,
        subledger_line.c.contract_id == schedule_line.c.contract_id,
        subledger_line.c.obligation_id == schedule_line.c.subject_id,
        subledger_line.c.book_code == schedule_line.c.book_code,
        subledger_line.c.account_role == AccountRole.REVENUE.value,
        func.coalesce(subledger_line.c.origin_period_id, subledger_line.c.period_id)
        == schedule_line.c.period_id,
    )
    if known_at is not None:
        posted = posted.where(subledger_line.c.recorded_at <= known_at)
    recognized = and_(
        schedule.c.schedule_kind == ScheduleKind.REVENUE.value,
        schedule_line.c.subject_type == "obligation",
        exists(posted),
    )
    return case((recognized, literal("RECOGNIZED")), else_=literal("SCHEDULED")).label("state")


def schedule_statement(session: Session, contract_id: UUID, *, params: ReadParams) -> Select[Any]:
    """API-S-ScheduleLine rows of the contract at the version in context; ``as_of`` bounds the
    periods (L3-1-Q-37); ``state`` follows ``_line_state``."""
    found = repo.get_contract(session, contract_id)
    version = version_at(
        session, found, book_code=params.book or primary_book(session), known_at=params.known_at
    )
    tenant = schedule_line.c.tenant_id
    statement = (
        select(
            schedule_line,
            schedule.c.schedule_kind,
            period.c.period_key,
            period.c.name.label("period_name"),
            period.c.end_date.label("period_end"),
            obligation.c.obligation_key,
            legal_entity.c.code.label("entity_code"),
            legal_entity.c.name.label("entity_name"),
            _line_state(params.known_at),
        )
        .select_from(
            schedule_line.join(
                schedule,
                and_(schedule.c.tenant_id == tenant, schedule.c.id == schedule_line.c.schedule_id),
            )
            .join(
                period, and_(period.c.tenant_id == tenant, period.c.id == schedule_line.c.period_id)
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == tenant,
                    legal_entity.c.id == schedule_line.c.entity_id,
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == tenant,
                    schedule_line.c.subject_type == "obligation",
                    obligation.c.id == schedule_line.c.subject_id,
                ),
            )
        )
        .where(schedule_line.c.contract_id == contract_id)
    )
    if version is None:
        return statement.where(false())
    statement = statement.where(schedule_line.c.contract_version_id == version["id"])
    if params.as_of is not None:
        statement = statement.where(
            schedule_line.c.period_end_date
            <= period_end_containing(schedule_line.c.entity_id, params.as_of)
        )
    return statement


@dataclass(frozen=True, slots=True)
class ScheduleLineFilters:
    """API-R-35 ``GET /schedule-lines`` parameters (BUILD_SPEC CTR-5)."""

    contract_id: UUID | None = None
    obligation: str | None = None  # key or id
    entity: str | None = None  # code or id
    from_period: str | None = None  # period key
    to_period: str | None = None  # period key
    line_type: str | None = None
    schedule_kind: str | None = None


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def schedule_lines_statement(
    session: Session, filters: ScheduleLineFilters, *, params: ReadParams
) -> Select[Any]:
    """API-S-ScheduleLine rows of the version each contract is read from in the book at
    ``known_at`` (API-C-10; 04 T-CON-04 reading rule). ``from_period`` and ``to_period`` bound the
    periods of each line's calendar by start date; ``as_of`` bounds them as ``schedule_statement``
    does. [J] L4-1-Q-7: without ``contract`` every visible contract's lines are listed."""
    book_code = params.book or primary_book(session)
    # Item RPT-FORMER-GROUP-READERS-1 (supervisor ruling R-117 (a)): the statement read each
    # group's latest version, and a group keeps its last version when its contract joins another:
    # the lines of a combined contract were listed twice (measured: 3,202.55 and 2,956.20 of
    # revenue for one contract and period, the cost line twice).
    read = tie_outs.read_from(
        schedule_line.c.contract_id,
        schedule_line.c.contract_version_id,
        book_code=book_code,
        cutoff=params.known_at,
        statuses=None,
        only_contract=filters.contract_id,
    )
    tenant = schedule_line.c.tenant_id
    statement = (
        select(
            schedule_line,
            schedule.c.schedule_kind,
            period.c.period_key,
            period.c.name.label("period_name"),
            period.c.end_date.label("period_end"),
            obligation.c.obligation_key,
            legal_entity.c.code.label("entity_code"),
            legal_entity.c.name.label("entity_name"),
            _line_state(params.known_at),
        )
        .select_from(
            schedule_line.join(
                schedule,
                and_(schedule.c.tenant_id == tenant, schedule.c.id == schedule_line.c.schedule_id),
            )
            .join(
                period, and_(period.c.tenant_id == tenant, period.c.id == schedule_line.c.period_id)
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == tenant,
                    legal_entity.c.id == schedule_line.c.entity_id,
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == tenant,
                    schedule_line.c.subject_type == "obligation",
                    obligation.c.id == schedule_line.c.subject_id,
                ),
            )
        )
        .where(read)
    )
    if filters.contract_id is not None:
        statement = statement.where(schedule_line.c.contract_id == filters.contract_id)
    if filters.obligation is not None:
        obligation_id = _as_uuid(filters.obligation)
        statement = statement.where(
            obligation.c.obligation_key == filters.obligation
            if obligation_id is None
            else obligation.c.id == obligation_id
        )
    if filters.entity is not None:
        entity_id = _as_uuid(filters.entity)
        statement = statement.where(
            legal_entity.c.code == filters.entity
            if entity_id is None
            else legal_entity.c.id == entity_id
        )
    for key, below in ((filters.from_period, False), (filters.to_period, True)):
        if key is None:
            continue
        bound = period.alias("to_period" if below else "from_period")
        start = (
            select(bound.c.start_date)
            .where(
                bound.c.tenant_id == period.c.tenant_id,
                bound.c.calendar_id == period.c.calendar_id,
                bound.c.period_key == key,
            )
            .scalar_subquery()
        )
        statement = statement.where(
            period.c.start_date <= start if below else period.c.start_date >= start
        )
    if filters.line_type is not None:
        statement = statement.where(schedule_line.c.line_type == filters.line_type)
    if filters.schedule_kind is not None:
        statement = statement.where(schedule.c.schedule_kind == filters.schedule_kind)
    if params.as_of is not None:
        statement = statement.where(
            schedule_line.c.period_end_date
            <= period_end_containing(schedule_line.c.entity_id, params.as_of)
        )
    return statement


def schedule_items(rows: Sequence[Mapping[str, Any]]) -> list[ScheduleLineOut]:
    return [
        ScheduleLineOut(
            id=row["id"],
            period=SchedulePeriodOut(
                id=row["period_id"],
                period_key=row["period_key"],
                name=row["period_name"],
                end_date=row["period_end"],
            ),
            obligation_key=row["obligation_key"],
            schedule_kind=_text(row["schedule_kind"]) or "",
            line_type=_text(row["line_type"]) or "",
            amount=_money(row["amount"], row["currency"]),
            cumulative_amount=_money(row["cumulative_amount"], row["currency"]),
            quantity=_maybe_exact(row["quantity"]),
            state=str(row["state"]),
            entity=RefOut(id=row["entity_id"], code=row["entity_code"], name=row["entity_name"]),
            contract_version_id=row["contract_version_id"],
            links=ScheduleLineLinksOut(explain=f"{API}/explain/schedule_line/{row['id']}/amount"),
        )
        for row in rows
    ]


def subledger_statement(
    session: Session, contract_id: UUID, *, params: ReadParams, now: datetime
) -> Select[Any]:
    """API-R-36 lines of the contract recorded by ``known_at`` whose periods end by the period of
    ``as_of`` (default today in the contracting entity's time zone; API-C-10)."""
    found = repo.get_contract(session, contract_id)
    statement = subledger.line_statement(
        session,
        subledger.LineFilters(book=params.book, contract=contract_id, known_at=params.known_at),
    )
    as_of = _as_of(session, found, params, now)
    return statement.where(
        subledger_line.c.period_end_date <= period_end_containing(subledger_line.c.entity_id, as_of)
    )


def subledger_items(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    files: FileStore | None,
    keyring: KeyRing | None,
) -> list[SubledgerLineOut]:
    """API-S-SubledgerLine of the rows of one page, read in ``session``: each line names the
    journal run that journalises it (``subledger.journal_runs_of``, which is handed the file
    store and the key ring as the gate hands them; 04 rev 1.288, lane F-CLO-A, item
    SUBLEDGER-LINE-JOURNAL-RUN-1)."""
    runs = subledger.journal_runs_of(session, rows, files=files, keyring=keyring)
    return subledger.line_outs(rows, runs)


# --- history -------------------------------------------------------------------------------------


def history_statement(session: Session, contract_id: UUID, *, include_system: bool) -> Select[Any]:
    """API-S-ContractHistoryItem sources ([J] L3-1-Q-41): EVENT items from ``contract_event``,
    CALCULATION items from ``contract_computation`` of the groups the contract belonged to,
    APPROVAL items from ``approval_decision`` on requests whose subject is the contract.
    ``occurred_at`` is the application timestamp (``created_at``, ``decided_at``); SYSTEM actors
    appear only with ``include_system``."""
    repo.get_contract(session, contract_id)
    events = select(
        contract_event.c.id.label("id"),
        contract_event.c.created_at.label("occurred_at"),
        literal(HistoryItemKind.EVENT.value, Text).label("kind"),
        contract_event.c.created_by.label("actor_id"),
        sql_cast(contract_event.c.created_by_kind, Text).label("actor_kind"),
        sql_cast(contract_event.c.event_type, Text).label("code"),
        contract_event.c.stream_version.label("seq"),
        contract_event.c.effective_date.label("effective_date"),
        contract_event.c.supersedes_event_id.label("ref_id"),
        sql_cast(null(), Text).label("label"),
        sql_cast(contract_event.c.origin, Text).label("extra"),
    ).where(contract_event.c.contract_id == contract_id)
    groups = select(combination_group_member.c.combination_group_id).where(
        combination_group_member.c.contract_id == contract_id
    )
    calculations = select(
        contract_computation.c.id,
        contract_computation.c.created_at,
        literal(HistoryItemKind.CALCULATION.value, Text),
        contract_computation.c.created_by,
        sql_cast(contract_computation.c.created_by_kind, Text),
        sql_cast(contract_computation.c.status, Text),
        sql_cast(null(), Integer),
        sql_cast(null(), Date),
        contract_computation.c.combination_group_id,
        sql_cast(contract_computation.c.engine_version, Text),
        sql_cast(contract_computation.c.trigger, Text),
    ).where(contract_computation.c.combination_group_id.in_(groups))
    approvals = (
        select(
            approval_decision.c.id,
            approval_decision.c.decided_at,
            literal(HistoryItemKind.APPROVAL.value, Text),
            approval_decision.c.approver_id,
            sql_cast(approval_decision.c.approver_kind, Text),
            sql_cast(approval_decision.c.decision, Text),
            sql_cast(null(), Integer),
            sql_cast(null(), Date),
            sql_cast(approval_decision.c.approval_request_id, Uuid),
            sql_cast(approval_request.c.request_no, Text),
            sql_cast(approval_request.c.subject_type, Text),
        )
        .select_from(
            approval_decision.join(
                approval_request,
                and_(
                    approval_request.c.tenant_id == approval_decision.c.tenant_id,
                    approval_request.c.id == approval_decision.c.approval_request_id,
                ),
            )
        )
        .where(approval_request.c.subject_id == contract_id)
    )
    history = union_all(events, calculations, approvals).subquery("history")
    statement = select(history)
    if not include_system:
        statement = statement.where(history.c.actor_kind != PrincipalKind.SYSTEM.value)
    return statement


def _actor_names(session: Session, rows: Sequence[Mapping[str, Any]]) -> dict[UUID, str]:
    users = {
        _uuid(row["actor_id"])
        for row in rows
        if row["actor_id"] is not None and row["actor_kind"] == PrincipalKind.USER.value
    }
    clients = {
        _uuid(row["actor_id"])
        for row in rows
        if row["actor_id"] is not None and row["actor_kind"] == PrincipalKind.API_CLIENT.value
    }
    names: dict[UUID, str] = {}
    if users:
        statement = select(app_user.c.id, app_user.c.display_name).where(
            app_user.c.id.in_(sorted(users))
        )
        names |= {_uuid(found.id): str(found.display_name) for found in session.execute(statement)}
    if clients:
        statement = select(api_client.c.id, api_client.c.name).where(
            api_client.c.id.in_(sorted(clients))
        )
        names |= {_uuid(found.id): str(found.name) for found in session.execute(statement)}
    return names


def history_items(
    session: Session, contract_id: UUID, rows: Sequence[Mapping[str, Any]]
) -> list[ContractHistoryItemOut]:
    names = _actor_names(session, rows)
    items: list[ContractHistoryItemOut] = []
    for row in rows:
        kind = HistoryItemKind(row["kind"])
        actor_id = row["actor_id"]
        actor = ActorOut(
            id=actor_id,
            kind=PrincipalKind(row["actor_kind"]),
            display_name=SYSTEM_DISPLAY_NAME
            if actor_id is None
            else names.get(_uuid(actor_id), SYSTEM_DISPLAY_NAME),
        )
        match kind:
            case HistoryItemKind.EVENT:
                summary_key = f"contract_event.{row['code']}"
                params: dict[str, Any] = {
                    "event_type": row["code"],
                    "stream_version": row["seq"],
                    "effective_date": row["effective_date"].isoformat(),
                    "origin": row["extra"],
                }
                links = {"event": f"{API}/contracts/{contract_id}/events/{row['id']}"}
            case HistoryItemKind.CALCULATION:
                summary_key = f"contract_computation.{row['code']}"
                params = {
                    "status": row["code"],
                    "trigger": row["extra"],
                    "engine_version": row["label"],
                }
                links = {"versions": f"{API}/contracts/{contract_id}/versions"}
            case _:
                summary_key = f"approval_decision.{row['code']}"
                params = {
                    "decision": row["code"],
                    "subject_type": row["extra"],
                    "request_no": row["label"],
                }
                links = {"approval": f"{API}/approvals/{row['ref_id']}"}
        items.append(
            ContractHistoryItemOut(
                occurred_at=row["occurred_at"],
                kind=kind,
                actor=actor,
                summary_key=summary_key,
                params=params,
                links=links,
            )
        )
    return items
