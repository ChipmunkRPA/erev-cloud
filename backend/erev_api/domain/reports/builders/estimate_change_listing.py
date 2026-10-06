"""RPT-29 ``estimate_change_listing`` Estimate change listing (SCREENS_B §5.6.2 RPT-29; 04 T-CON-08,
T-CON-11, T-CON-12, T-CON-13, T-PLT-17, T-PLT-20, E-09, E-10; PRD J-06-AC-2, J-07-AC-2, WLD-X-12,
WLD-X-16; D-20; POL-182; 03 REQ-RPT-023, REQ-TP-004, REQ-TP-005; research 07 A-07; BUILD_SPEC
RPS-11).

One row per approved estimate version (now APPROVED or SUPERSEDED) whose ``effective_date`` lies in
``from_date`` .. ``to_date`` (defaults: the first day of the context fiscal year and the end of the
context period), of the contracts of the run's entities, narrowed by ``estimate_kind`` (E-09) when
given. A version approved after the record cutoff is not listed; a portfolio-scoped estimate
(CTR-13) belongs to no entity and lies outside the entity scope. Rows are ordered by contract,
element and version; ``row_key`` ``estimate:<contract external id>:<element code>:<version no>``
(an element code is unique within its contract only, T-CON-12).

- ``version_pair`` names the version with the one it supersedes (``v1 → v2``; ``v1`` for an
  element's first version, whose "before" cells are empty).
- ``measure_label`` names the measure of the version's kind and ``before_value`` / ``after_value``
  carry it for the superseded and the listed version: "Constrained amount" (variable
  consideration, implicit price concession), else "Expected total" (estimate at completion,
  expected purchases), else "Rate" — an amount as a decimal with the currency's minor unit, a rate
  as an exact ratio with an empty ``currency``.
- ``pnl_effect`` is the catch-up the computation recorded when the version was applied: the sum of
  ``obligation_version.catch_up_amount`` over the contract versions of the run's book that the
  version's ``ESTIMATE_CHANGED`` events caused (``contract_version.cause_event_ids``). A contract
  version caused together with another estimate version or a modification carries a joint
  catch-up, which is not apportioned: the cell is then empty, as it is while no computed version
  exists. A later event effective on the same day may re-attribute cumulative catch-up by cause
  (the modification register shows a modification's own).
- ``preparer`` and ``approver`` come from the version's ``ESTIMATE_VERSION`` approval request;
  ``approved_at`` is its approval instant; ``attachment_count`` counts the version's attachments
  that are not voided.

Control totals ``row_count`` and ``pnl_effect_total`` per currency, with the date range applied.
``currency_view`` ``transaction`` is served; another view only when every row's currency is its
entity's functional currency, else refused by name (RPT-14's rule; no FX conversion here).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Uuid, and_, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    estimate,
    estimate_version,
    file_attachment,
    legal_entity,
    obligation,
    obligation_version,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ConfigStatus, ContractEventType
from erev_api.uow import UnitOfWork

CODE: Final = "estimate_change_listing"
ROW_KEY_PREFIX: Final = "estimate:"  # RPT-29: `estimate:<external id>:<element code>:<version no>`
DEFAULT_CURRENCY_VIEW: Final = "transaction"
ATTACHMENT_SUBJECT: Final = "estimate_version"  # file_attachment.subject_type of a version
APPROVED_STATUSES: Final = (ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value)
# Events that open a catch-up boundary of a contract version (ENGINE_SPEC §6; S06-R-26).
BOUNDARY_EVENTS: Final = (
    ContractEventType.ESTIMATE_CHANGED.value,
    ContractEventType.CONTRACT_AMENDED.value,
)
CONSTRAINED: Final = "Constrained amount"
EXPECTED_TOTAL: Final = "Expected total"
RATE: Final = "Rate"
FUNCTIONAL_ONLY: Final = (
    "The functional currency view is available when every estimate is in its entity's functional "
    "currency; choose the transaction view."
)
HISTORY_UNAVAILABLE: Final = (
    "The estimate change listing cannot state {element_code} version {version_no} as of {cutoff}: "
    "the version carries no approval request and last changed at {updated_at}, after the cutoff, "
    "and T-CON-13 keeps no history of its status (not reconstructed). Run the listing at a later "
    "known_at or current."
)
COLUMNS: Final = (
    Column("element_code", "Element", "code"),
    Column("estimate_kind", "Kind", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("version_pair", "Versions", "text"),
    Column("effective_date", "Effective date", "date"),
    Column("method", "Method", "code"),
    Column("no_change_attestation", "No-change attestation", "boolean"),
    Column("measure_label", "Measure", "text"),
    Column("currency", "Currency", "code"),
    Column("before_value", "Before", "decimal"),
    Column("after_value", "After", "decimal"),
    Column("pnl_effect", "P&L effect", "money"),
    Column("preparer", "Preparer", "text"),
    Column("approver", "Approver", "text"),
    Column("approved_at", "Approved", "timestamp"),
    Column("attachment_count", "Evidence", "integer"),
)


@dataclass(frozen=True, slots=True)
class Measure:
    """The measure of an estimate version with its predecessor's value."""

    label: str | None
    currency: str | None  # None for a rate
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class Source:
    """One approved estimate version with its approval and effect — the input of
    ``dataset_rows``."""

    element_code: str
    estimate_kind: str
    contract_external_id: str
    obligation_key: str | None
    version_no: int
    previous_version_no: int | None
    effective_date: date
    method: str
    no_change_attestation: bool
    measure: Measure
    currency: str  # of the contract: the currency of the effect
    functional_currency: str
    pnl_effect: Decimal | None
    preparer: tuple[UUID | None, str]
    approvers: tuple[tuple[UUID | None, str], ...]
    approved_at: datetime | None
    attachment_count: int


def measure_of(
    after: Mapping[str, Any], before: Mapping[str, Any] | None, *, currency: str
) -> Measure:
    """The measure a version carries, read on it and on the version it supersedes. Pure."""

    def amount(row: Mapping[str, Any] | None, column: str) -> str | None:
        if row is None or row[column] is None:
            return None
        return tie_outs.money(Decimal(row[column]), currency)["amount"]

    if after["constrained_amount"] is not None:
        column = "constrained_amount"
        return Measure(CONSTRAINED, currency, amount(before, column), amount(after, column))
    if after["expected_total_amount"] is not None:
        column = "expected_total_amount"
        return Measure(EXPECTED_TOTAL, currency, amount(before, column), amount(after, column))
    if after["rate"] is not None:
        earlier = None if before is None or before["rate"] is None else Decimal(before["rate"])
        return Measure(
            RATE, None, support.ratio_text(earlier), support.ratio_text(Decimal(after["rate"]))
        )
    return Measure(None, None, None, None)


def version_pair(version_no: int, previous_version_no: int | None) -> str:
    """``v<m> → v<n>``; ``v<n>`` for a version that supersedes none. Pure."""
    if previous_version_no is None:
        return f"v{version_no}"
    return f"v{previous_version_no} → v{version_no}"


def attributed_effects(
    versions: Iterable[tuple[UUID, Sequence[UUID], Decimal]],
    boundaries: Mapping[UUID, UUID | None],
) -> dict[UUID, Decimal]:
    """Per estimate version id, the catch-up of the contract versions it alone caused.

    ``versions`` holds (contract version id, its cause event ids, its catch-up); ``boundaries``
    maps each boundary event (``ESTIMATE_CHANGED``, ``CONTRACT_AMENDED``) among those causes to
    its estimate version id (None for a modification). A contract version whose boundary events
    belong to one estimate version is attributed to it; a joint one to none. Pure."""
    effects: dict[UUID, Decimal] = {}
    for _, causes, catch_up in versions:
        owners = {boundaries[event] for event in causes if event in boundaries}
        if len(owners) != 1:
            continue
        (owner,) = owners
        if owner is not None:
            effects[owner] = effects.get(owner, Decimal(0)) + catch_up
    return effects


def check_view(view: str, found: Iterable[Source]) -> None:
    """``transaction`` always; another view only when every row is in its entity's functional
    currency, else refused by name."""
    if view != DEFAULT_CURRENCY_VIEW and any(
        item.currency != item.functional_currency for item in found
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def row_key(item: Source) -> str:
    return f"{ROW_KEY_PREFIX}{item.contract_external_id}:{item.element_code}:{item.version_no}"


def dataset_rows(
    found: Iterable[Source], names: Mapping[UUID, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in contract, element and version order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {}
    ordered = sorted(
        found,
        key=lambda item: (item.contract_external_id, item.element_code, item.version_no),
    )
    for item in ordered:
        effect = None
        if item.pnl_effect is not None:
            effect = tie_outs.money(item.pnl_effect, item.currency)
            tie_outs.add(totals, item.currency, item.pnl_effect)
        rows.append(
            {
                "row_key": row_key(item),
                "element_code": item.element_code,
                "estimate_kind": item.estimate_kind,
                "contract_external_id": item.contract_external_id,
                "obligation_key": item.obligation_key,
                "version_pair": version_pair(item.version_no, item.previous_version_no),
                "effective_date": item.effective_date,
                "method": item.method,
                "no_change_attestation": item.no_change_attestation,
                "measure_label": item.measure.label,
                "currency": item.measure.currency,
                "before_value": item.measure.before,
                "after_value": item.measure.after,
                "pnl_effect": effect,
                "preparer": support.actor_names([item.preparer], names)[0],
                "approver": support.joined(support.actor_names(item.approvers, names)),
                "approved_at": item.approved_at,
                "attachment_count": item.attachment_count,
            }
        )
    return rows, {"row_count": len(rows), "pnl_effect_total": tie_outs.by_currency(totals)}


# --- reads ----------------------------------------------------------------------------------------


def _versions(
    session: Session, params: ReportParams, *, first: date, last: date, cutoff: datetime
) -> list[dict[str, Any]]:
    if not params.entity_ids:
        return []
    scope: ColumnElement[bool] = contract.c.contracting_entity_id.in_(list(params.entity_ids))
    statement = (
        select(
            estimate_version,
            estimate.c.element_code,
            estimate.c.estimate_kind,
            estimate.c.method,
            contract.c.external_id.label("contract_external_id"),
            contract.c.transaction_currency.label("contract_currency"),
            legal_entity.c.functional_currency,
            obligation.c.obligation_key,
        )
        .select_from(
            estimate_version.join(
                estimate,
                and_(
                    estimate.c.tenant_id == estimate_version.c.tenant_id,
                    estimate.c.id == estimate_version.c.estimate_id,
                ),
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == estimate.c.tenant_id,
                    contract.c.id == estimate.c.contract_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                    legal_entity.c.id == contract.c.contracting_entity_id,
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == estimate.c.tenant_id,
                    obligation.c.id == estimate.c.obligation_id,
                ),
            )
        )
        .where(
            scope,
            estimate_version.c.status.in_(APPROVED_STATUSES),
            estimate_version.c.created_at <= cutoff,
            estimate_version.c.effective_date >= first,
            estimate_version.c.effective_date <= last,
        )
    )
    kinds = params.parameters.get("estimate_kind")
    if kinds:
        statement = statement.where(estimate.c.estimate_kind.in_([str(value) for value in kinds]))
    return [dict(row) for row in session.execute(statement).mappings()]


def _effects(
    session: Session, rows: Sequence[Mapping[str, Any]], *, book_code: str, cutoff: datetime
) -> dict[UUID, Decimal]:
    """``attributed_effects`` over the contract versions of the book that the versions' applied
    events caused by the cutoff."""
    events = sorted(
        {UUID(str(value)) for row in rows for value in row["applied_event_ids"] or ()}, key=str
    )
    if not events:
        return {}
    caused = [
        (UUID(str(version_id)), [UUID(str(value)) for value in causes])
        for version_id, causes in session.execute(
            select(contract_version.c.id, contract_version.c.cause_event_ids).where(
                contract_version.c.book_code == book_code,
                contract_version.c.known_at <= cutoff,
                contract_version.c.cause_event_ids.op("&&")(literal(events, type_=ARRAY(Uuid()))),
            )
        )
    ]
    if not caused:
        return {}
    catch_ups = {
        UUID(str(version_id)): Decimal(total)
        for version_id, total in session.execute(
            select(
                obligation_version.c.contract_version_id,
                func.sum(obligation_version.c.catch_up_amount),
            )
            .where(obligation_version.c.contract_version_id.in_([item[0] for item in caused]))
            .group_by(obligation_version.c.contract_version_id)
        )
    }
    causes = sorted({event for _, found in caused for event in found}, key=str)
    boundaries = {
        UUID(str(event_id)): support.uuid_of(version_id)
        for event_id, version_id in session.execute(
            select(contract_event.c.id, contract_event.c.estimate_version_id).where(
                contract_event.c.id.in_(causes),
                contract_event.c.event_type.in_(BOUNDARY_EVENTS),
            )
        )
    }
    return attributed_effects(
        (
            (version_id, found, catch_ups[version_id])
            for version_id, found in caused
            if version_id in catch_ups
        ),
        boundaries,
    )


def _attachments(
    session: Session, version_ids: Sequence[UUID], *, cutoff: datetime
) -> dict[UUID, int]:
    if not version_ids:
        return {}
    statement = (
        select(file_attachment.c.subject_id, func.count())
        .where(
            file_attachment.c.subject_type == ATTACHMENT_SUBJECT,
            file_attachment.c.subject_id.in_(list(version_ids)),
            file_attachment.c.created_at <= cutoff,
            or_(file_attachment.c.voided_at.is_(None), file_attachment.c.voided_at > cutoff),
        )
        .group_by(file_attachment.c.subject_id)
    )
    return {UUID(str(subject)): int(count) for subject, count in session.execute(statement)}


def sources(
    uow: UnitOfWork, params: ReportParams, *, first: date, last: date, book_code: str
) -> tuple[list[Source], list[support.Request]]:
    """The approved versions in scope and range with their approvals and effects, as they stood at
    the record cutoff; and their approval requests (for the display names)."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    rows = _versions(session, params, first=first, last=last, cutoff=cutoff)
    requests = support.requests_by_id(
        session,
        [UUID(str(row["approval_request_id"])) for row in rows if row["approval_request_id"]],
        cutoff=cutoff,
    )
    kept: list[dict[str, Any]] = []
    for row in rows:
        request = (
            None
            if row["approval_request_id"] is None
            else requests.get(UUID(str(row["approval_request_id"])))
        )
        if row["approval_request_id"] is None:
            if params.historical and row["updated_at"] > cutoff:  # REGISTER-CUTOFF-1
                raise tie_outs.invalid(
                    "known_at",
                    HISTORY_UNAVAILABLE.format(
                        element_code=row["element_code"],
                        version_no=int(row["version_no"]),
                        cutoff=cutoff.isoformat(),
                        updated_at=row["updated_at"].isoformat(),
                    ),
                )
        elif request is None or request.status != support.APPROVED:
            continue  # approved after the cutoff
        kept.append(row)
    earlier = sorted(
        {UUID(str(row["supersedes_version_id"])) for row in kept if row["supersedes_version_id"]},
        key=str,
    )
    previous: dict[UUID, dict[str, Any]] = {}
    if earlier:
        previous = {
            UUID(str(row["id"])): dict(row)
            for row in session.execute(
                select(estimate_version).where(estimate_version.c.id.in_(earlier))
            ).mappings()
        }
    effects = _effects(session, kept, book_code=book_code, cutoff=cutoff)
    attachments = _attachments(session, [UUID(str(row["id"])) for row in kept], cutoff=cutoff)
    found: list[Source] = []
    for row in kept:
        version_id = UUID(str(row["id"]))
        request = (
            None
            if row["approval_request_id"] is None
            else requests[UUID(str(row["approval_request_id"]))]
        )
        before = (
            None
            if row["supersedes_version_id"] is None
            else previous.get(UUID(str(row["supersedes_version_id"])))
        )
        currency = str(row["contract_currency"]).strip()
        own = currency if row["currency"] is None else str(row["currency"]).strip()
        creator = (support.uuid_of(row["created_by"]), str(support.text(row["created_by_kind"])))
        parameters = row["parameters"] or {}
        found.append(
            Source(
                element_code=str(row["element_code"]),
                estimate_kind=str(support.text(row["estimate_kind"])),
                contract_external_id=str(row["contract_external_id"]),
                obligation_key=support.text(row["obligation_key"]),
                version_no=int(row["version_no"]),
                previous_version_no=None if before is None else int(before["version_no"]),
                effective_date=row["effective_date"],
                method=str(support.text(row["method"])),
                no_change_attestation=bool(parameters.get("no_change_attestation", False)),
                measure=measure_of(row, before, currency=own),
                currency=currency,
                functional_currency=str(row["functional_currency"]).strip(),
                pnl_effect=effects.get(version_id),
                preparer=creator if request is None else request.preparer,
                approvers=() if request is None else request.approvers,
                approved_at=None if request is None else request.approved_at,
                attachment_count=attachments.get(version_id, 0),
            )
        )
    return found, list(requests.values())


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    first, last = support.date_range(session, params)
    found, requests = sources(
        uow, params, first=first, last=last, book_code=tie_outs.book_of(session, params)
    )
    check_view(str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW), found)
    names = support.names_of(session, requests, (item.preparer[0] for item in found))
    rows, totals = dataset_rows(found, names)
    totals["from_date"], totals["to_date"] = first.isoformat(), last.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "DEFAULT_CURRENCY_VIEW",
    "Measure",
    "Source",
    "attributed_effects",
    "build",
    "check_view",
    "dataset_rows",
    "measure_of",
    "sources",
    "version_pair",
]
