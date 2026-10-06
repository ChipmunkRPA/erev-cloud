"""RPT-18 ``manual_adjustment_register`` Manual adjustment register — the governed
``MANUAL_ADJUSTMENT_REGISTER`` dataset producer (ENGINE_SPEC_B §15.2.7 S15-R-20d rev 1.39; 04
T-SL-05, T-CLS-05; 03 REQ-JE-019, REQ-RPT-022; SCREENS_B §5.6.3 RPT-18; BUILD_SPEC RPS-8; lane
F-CLO).

One row per manual adjustment (T-SL-05) of the selected entities and book whose POSTING period lies
in ``from_period_key`` .. ``to_period_key`` (RPT-18: the context period by default), narrowed by
``status`` (E-94) and ``kind`` (E-93) when given (default: every value). The amount is the
adjustment's absolute functional impact (``amount_functional_abs``); the served view is
``functional`` and a ``transaction`` view is refused by name (T-SL-05 carries no transaction amount
for every kind); the row's ``currency`` is the entity's FUNCTIONAL currency — the currency of
``amount_functional_abs`` (T-SL-05's own ``currency`` is the transaction currency the refused view
would need). Approvals: the preparer is the request's preparer, else the row's creator;
``approvers`` are the APPROVE / AUTO_APPROVE deciders by the cutoff in decision order;
``approved_at`` the last such decision; ``decision_comment`` the last decision's comment of any
kind by the cutoff (a REJECT's comment for a rejected adjustment); ``attachment_count`` counts the
adjustment's non-voided ``file_attachment`` rows. Historical runs follow REGISTER-CUTOFF-1 (D-98
140-A10 / A11 / A13): a row changed after the cutoff refuses by name — T-SL-05 keeps no row history;
a live run never refuses. The as-locked surface (``period_lock_id``) is the framework's (CLO-8,
CLO-8b): a lock source here refuses by name, as every register does. Control totals: ``row_count``,
per currency ``amount_functional_abs_total`` (Σ|amount| over every row — the §15.2.7 pair) and
``posted_total`` (RPT-18's footer: POSTED adjustments only). Labels are attribute columns; the key
is (``entity_code``, ``adjustment_no``) — the KeySpec ``close/relock_diff.py`` pins.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    file_attachment,
    legal_entity,
    manual_adjustment,
    obligation,
    period,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalDecisionKind, ManualAdjustmentKind, ManualAdjustmentStatus
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "manual_adjustment_register"
KEY_COLUMNS: Final = ("entity_code", "adjustment_no")  # S15-R-20d; relock_diff KeySpec
MEASURES: Final = ("amount_functional_abs",)  # the one declared measure
DEFAULT_CURRENCY_VIEW: Final = "functional"  # SCREENS_B RPT-18 "default functional"
# file_attachment.subject_type of an adjustment: the table name, as 04 T-PLT-30's CHECK lists it
# (the E-08 literal was used here until CLO-12 attached the first file — it matched no row).
ATTACHMENT_SUBJECT: Final = "manual_adjustment"
ROW_KEY_PREFIX: Final = "adjustment:"  # RPT-18: row_key `adjustment:<adjustment no>`
VIEW_UNSUPPORTED: Final = (
    "The manual adjustment register serves the functional view only: T-SL-05 carries the absolute "
    "functional impact of every adjustment and no transaction amount for every kind."
)
HISTORY_UNAVAILABLE: Final = (
    "The manual adjustment register cannot state {adjustment_no} as of {cutoff}: the row last "
    "changed at {updated_at}, after the cutoff, and T-SL-05 keeps no row history — the history is "
    "unavailable (not reconstructed, not narrowed). Run the register at a later known_at or "
    "without the historical basis."
)
FIELDS: Final = (
    "adjustment_no",
    "kind",
    "contract_external_id",
    "obligation_key",
    "entity_code",
    "period_key",
    "effective_date",
    "status",
    "reason_code",
    "memo",
    "currency",
    "amount_functional_abs",
    "preparer",
    "approvers",
    "preparer_differs",
    "approved_at",
    "attachment_count",
    "is_deferred_past_lock",
    "decision_comment",
)
COLUMNS: Final = (
    Column("adjustment_no", "Adjustment", "code"),
    Column("kind", "Kind", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("entity_code", "Entity", "code"),
    Column("period_key", "Period", "code"),
    Column("effective_date", "Effective date", "date"),
    Column("status", "Status", "code"),
    Column("reason_code", "Reason", "code"),
    Column("memo", "Memo", "text"),
    Column("currency", "Currency", "code"),
    Column("amount_functional_abs", "Amount", "money"),
    Column("preparer", "Preparer", "text"),
    Column("approvers", "Approvers", "text"),
    Column("preparer_differs", "Preparer differs from approver", "boolean"),
    Column("approved_at", "Approved", "timestamp", empty_text="Never"),
    Column("attachment_count", "Attachments", "integer"),
    Column("is_deferred_past_lock", "Deferred past lock", "boolean"),
    Column("decision_comment", "Decision comment", "text"),
)
APPROVING: Final = (ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value)


@dataclass(frozen=True, slots=True)
class Source:
    """One adjustment with its approvals resolved — the input of ``dataset_rows``."""

    adjustment_id: UUID
    adjustment_no: str
    kind: str
    status: str
    contract_external_id: str
    obligation_key: str | None
    entity_code: str
    period_key: str
    effective_date: date
    reason_code: str
    memo: str
    currency: str
    amount_functional_abs: Decimal
    preparer_id: UUID | None
    preparer_kind: str
    approvers: tuple[tuple[UUID | None, str], ...]
    approved_at: datetime | None
    decision_comment: str | None
    attachment_count: int
    is_deferred_past_lock: bool


def _text(value: object) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


def check_view(params: ReportParams) -> None:
    """RPT-18 serves the functional view; any other view is refused by name (no silent fallback)."""
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    if view != DEFAULT_CURRENCY_VIEW:
        raise tie_outs.invalid("currency_view", VIEW_UNSUPPORTED)


def _values(params: ReportParams, key: str, admitted: Iterable[str]) -> tuple[str, ...]:
    given = params.parameters.get(key)
    if not given:
        return tuple(admitted)
    return tuple(str(value) for value in given)


def historical_refusal(
    rows: Iterable[Mapping[str, Any]], *, cutoff: datetime, historical: bool
) -> str | None:
    """REGISTER-CUTOFF-1 for T-SL-05 (no row history): on an explicit historical read a row whose
    last change follows the cutoff refuses by name; a live run never refuses. Pure."""
    if not historical:
        return None
    for row in rows:
        if row["updated_at"] > cutoff:
            return HISTORY_UNAVAILABLE.format(
                adjustment_no=row["adjustment_no"],
                cutoff=cutoff.isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
    return None


def dataset_rows(found: Iterable[Source], names: Mapping[UUID, str]) -> list[dict[str, Any]]:
    """The register rows (RPT-18 fields plus ``row_key``); display names are attributes."""
    rows: list[dict[str, Any]] = []
    for item in found:
        preparer = approval_queries.actor(item.preparer_id, item.preparer_kind, names)
        approver_ids = {user_id for user_id, _ in item.approvers if user_id is not None}
        approver_names = [
            str(approval_queries.actor(user_id, kind, names)["display_name"])
            for user_id, kind in item.approvers
        ]
        rows.append(
            {
                "row_key": f"{ROW_KEY_PREFIX}{item.adjustment_no}",
                "adjustment_no": item.adjustment_no,
                "kind": item.kind,
                "contract_external_id": item.contract_external_id,
                "obligation_key": item.obligation_key,
                "entity_code": item.entity_code,
                "period_key": item.period_key,
                "effective_date": item.effective_date,
                "status": item.status,
                "reason_code": item.reason_code,
                "memo": item.memo,
                "currency": item.currency,
                "amount_functional_abs": tie_outs.money(item.amount_functional_abs, item.currency),
                "preparer": str(preparer["display_name"]),
                "approvers": ", ".join(approver_names) if approver_names else None,
                "preparer_differs": bool(item.approvers)
                and (item.preparer_id is None or item.preparer_id not in approver_ids),
                "approved_at": item.approved_at,
                "attachment_count": item.attachment_count,
                "is_deferred_past_lock": item.is_deferred_past_lock,
                "decision_comment": item.decision_comment,
            }
        )
    return rows


def check_key_columns(rows: Sequence[Mapping[str, Any]]) -> None:
    """S15-R-20a / 20d: every row supplies (entity_code, adjustment_no) and the key occurs once;
    otherwise refuse by name."""
    seen: set[tuple[str, str]] = set()
    for row in rows:
        values = tuple(row.get(column) for column in KEY_COLUMNS)
        for column, value in zip(KEY_COLUMNS, values, strict=True):
            if value is None or str(value) == "":
                raise tie_outs.invalid(column, f"row {row.get('row_key')!r} supplies no {column}")
        key = (str(values[0]), str(values[1]))
        if key in seen:
            raise tie_outs.invalid("adjustment_no", f"the key {':'.join(key)} occurs twice")
        seen.add(key)


def control_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``row_count``; per currency ``amount_functional_abs_total`` over every row (the §15.2.7
    pair) and ``posted_total`` over POSTED rows (RPT-18's footer)."""
    every: dict[str, Decimal] = {}
    posted: dict[str, Decimal] = {}
    for row in rows:
        amount = Decimal(str(row["amount_functional_abs"]["amount"]))
        currency = str(row["currency"])
        tie_outs.add(every, currency, abs(amount))
        if str(row["status"]) == ManualAdjustmentStatus.POSTED.value:
            tie_outs.add(posted, currency, abs(amount))
    return {
        "row_count": len(rows),
        "amount_functional_abs_total": tie_outs.by_currency(every),
        "posted_total": tie_outs.by_currency(posted),
    }


def _decisions(
    session: Session, request_ids: Sequence[UUID], *, cutoff: datetime
) -> tuple[dict[UUID, list[tuple[UUID | None, str]]], dict[UUID, datetime], dict[UUID, str]]:
    """Per request by the cutoff, in decision order: the approving deciders, the last approval
    instant and the last decision's comment of any kind (REGISTER-CUTOFF-1)."""
    approvers: dict[UUID, list[tuple[UUID | None, str]]] = {}
    approved_at: dict[UUID, datetime] = {}
    comments: dict[UUID, str] = {}
    wanted = sorted(set(request_ids), key=str)
    if not wanted:
        return approvers, approved_at, comments
    statement = (
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.decision,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decided_at,
            approval_decision.c.comment,
        )
        .where(
            approval_decision.c.approval_request_id.in_(wanted),
            approval_decision.c.decided_at <= cutoff,
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    )
    for request_id, decision, approver_id, kind, decided_at, comment in session.execute(statement):
        key = UUID(str(request_id))
        if _text(decision) in APPROVING:
            approvers.setdefault(key, []).append(
                (None if approver_id is None else UUID(str(approver_id)), str(_text(kind)))
            )
            approved_at[key] = decided_at
        if comment is not None and str(comment) != "":
            comments[key] = str(comment)
    return approvers, approved_at, comments


def _attachment_counts(session: Session, adjustment_ids: Sequence[UUID]) -> dict[UUID, int]:
    if not adjustment_ids:
        return {}
    statement = (
        select(file_attachment.c.subject_id, func.count())
        .where(
            file_attachment.c.subject_type == ATTACHMENT_SUBJECT,
            file_attachment.c.subject_id.in_(list(adjustment_ids)),
            file_attachment.c.voided_by.is_(None),
        )
        .group_by(file_attachment.c.subject_id)
    )
    return {UUID(str(subject)): int(count) for subject, count in session.execute(statement)}


def sources(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    book_code: str,
    period_ids: Sequence[UUID],
    statuses: Sequence[str],
    kinds: Sequence[str],
) -> list[Source]:
    """The adjustments of the run with their approvals resolved (module docstring)."""
    session = uow.session
    if not params.entity_ids or not period_ids:
        return []
    tenant = manual_adjustment.c.tenant_id
    joined = (
        manual_adjustment.join(
            contract,
            and_(contract.c.tenant_id == tenant, contract.c.id == manual_adjustment.c.contract_id),
        )
        .join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant,
                legal_entity.c.id == manual_adjustment.c.entity_id,
            ),
        )
        .join(
            period,
            and_(period.c.tenant_id == tenant, period.c.id == manual_adjustment.c.period_id),
        )
        .outerjoin(
            obligation,
            and_(
                obligation.c.tenant_id == tenant,
                obligation.c.id == manual_adjustment.c.obligation_id,
            ),
        )
    )
    cutoff = tie_outs.cutoff_for(session, params)
    statement = (
        select(
            manual_adjustment,
            contract.c.external_id.label("contract_external_id"),
            legal_entity.c.code.label("entity_code"),
            legal_entity.c.functional_currency.label("functional_currency"),
            period.c.period_key.label("period_key"),
            obligation.c.obligation_key.label("obligation_key"),
        )
        .select_from(joined)
        .where(
            manual_adjustment.c.entity_id.in_(list(params.entity_ids)),
            manual_adjustment.c.book_code == book_code,
            manual_adjustment.c.period_id.in_(list(period_ids)),
            manual_adjustment.c.created_at <= cutoff,
        )
        .order_by(legal_entity.c.code, manual_adjustment.c.adjustment_no)
    )
    candidates = [dict(row) for row in session.execute(statement).mappings()]
    # REGISTER-CUTOFF-1: inspect the whole population in scope before the status / kind filters.
    refusal = historical_refusal(candidates, cutoff=cutoff, historical=params.historical)
    if refusal is not None:
        raise tie_outs.invalid("known_at", refusal)
    wanted_status = {str(value) for value in statuses}
    wanted_kind = {str(value) for value in kinds}
    rows = [
        row
        for row in candidates
        if _text(row["status"]) in wanted_status and _text(row["kind"]) in wanted_kind
    ]
    if not rows:
        return []
    request_ids = [
        UUID(str(row["approval_request_id"])) for row in rows if row["approval_request_id"]
    ]
    approvers, approved_at, comments = _decisions(session, request_ids, cutoff=cutoff)
    preparers: dict[UUID, tuple[UUID | None, str]] = {}
    if request_ids:
        for request_id, preparer_id, kind in session.execute(
            select(
                approval_request.c.id,
                approval_request.c.preparer_id,
                approval_request.c.preparer_kind,
            ).where(approval_request.c.id.in_(sorted(set(request_ids), key=str)))
        ):
            preparers[UUID(str(request_id))] = (
                None if preparer_id is None else UUID(str(preparer_id)),
                str(_text(kind)),
            )
    counts = _attachment_counts(session, [UUID(str(row["id"])) for row in rows])
    found: list[Source] = []
    for row in rows:
        request_id = (
            None if row["approval_request_id"] is None else UUID(str(row["approval_request_id"]))
        )
        preparer_id, preparer_kind = (
            preparers.get(request_id, (None, "SYSTEM"))
            if request_id is not None
            else (
                None if row["created_by"] is None else UUID(str(row["created_by"])),
                str(_text(row["created_by_kind"])),
            )
        )
        found.append(
            Source(
                adjustment_id=UUID(str(row["id"])),
                adjustment_no=str(row["adjustment_no"]),
                kind=str(_text(row["kind"])),
                status=str(_text(row["status"])),
                contract_external_id=str(row["contract_external_id"]),
                obligation_key=(
                    None if row["obligation_key"] is None else str(row["obligation_key"])
                ),
                entity_code=str(row["entity_code"]),
                period_key=str(row["period_key"]),
                effective_date=row["effective_date"],
                reason_code=str(row["reason_code"]),
                memo=str(row["memo"]),
                currency=str(row["functional_currency"]),  # the served view is functional
                amount_functional_abs=Decimal(str(row["amount_functional_abs"])),
                preparer_id=preparer_id,
                preparer_kind=preparer_kind,
                approvers=tuple(approvers.get(request_id, [])) if request_id else (),
                approved_at=approved_at.get(request_id) if request_id else None,
                decision_comment=comments.get(request_id) if request_id else None,
                attachment_count=counts.get(UUID(str(row["id"])), 0),
                is_deferred_past_lock=bool(row["is_deferred_past_lock"]),
            )
        )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    check_view(params)
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    entities = tie_outs.entities(session, params.entity_ids)
    calendars = tie_outs.calendars(session, entities)
    period_ids: list[UUID] = []
    for entity in entities:
        for item in tie_outs.range_of(params, calendars[entity.id], entity):
            period_ids.append(item.id)
    found = sources(
        uow,
        params,
        book_code=book_code,
        period_ids=period_ids,
        statuses=_values(params, "status", (s.value for s in ManualAdjustmentStatus)),
        kinds=_values(params, "kind", (k.value for k in ManualAdjustmentKind)),
    )
    names = approval_queries.display_names(
        session,
        [item.preparer_id for item in found]
        + [user_id for item in found for user_id, _ in item.approvers],
    )
    rows = dataset_rows(found, names)
    check_key_columns(rows)
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=control_totals(rows))


__all__ = [
    "CODE",
    "COLUMNS",
    "FIELDS",
    "KEY_COLUMNS",
    "MEASURES",
    "Problem",
    "Source",
    "build",
    "check_key_columns",
    "check_view",
    "control_totals",
    "dataset_rows",
    "historical_refusal",
    "sources",
]
