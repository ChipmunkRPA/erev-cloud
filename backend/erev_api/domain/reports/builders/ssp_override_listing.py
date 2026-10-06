"""RPT-22 ``ssp_override_listing`` SSP override listing (SCREENS_B §5.6.4 RPT-22; 04 T-CON-11
``ssp_override_approval_request_id``, §16.2 ``request-ssp-override``, T-PLT-17, T-PLT-20; PRD
BR-SSP-03; 03 REQ-SSP-006, REQ-SSP-012; CTL-010; BUILD_SPEC RPS-9).

One row per obligation and approved ``SSP_OVERRIDE`` request: the obligation versions that carry
``ssp_override_approval_request_id`` (the computation stores the request behind an obligation's
corrected SSP pin, CTR-15), read as of the run's record cutoff for the contracting entities in
scope, reduced to the first version that carries each request. The request's approval instant lies
in ``from_date`` .. ``to_date`` (UTC days; defaults: the first day of the context fiscal year and
the run's day).

``override_version_label`` names the SSP book version the obligation is priced from under the
override and ``default_version_label`` the version it is priced from without one — the pin of the
obligation's latest earlier version that carries no override — both as ``<book code> <version
label>``. ``justification`` is the preparer's justification (the request's comment, 04 §16.2),
``requested_by`` the request's preparer, ``approved_by`` its approving deciders in decision order
and ``approved_at`` the approval instant. Rows are ordered by contract, obligation key and request
number; ``row_key`` ``override:<external id>:<obligation key>:<request no>``. Control totals
``row_count`` and the range applied; no totals and no tie-out.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_version,
    obligation_version,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "ssp_override_listing"
ROW_KEY_PREFIX: Final = "override:"
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("default_version_label", "Default version", "code"),
    Column("override_version_label", "Override version", "code"),
    Column("justification", "Justification", "text"),
    Column("requested_by", "Requested by", "text"),
    Column("approved_by", "Approved by", "text"),
    Column("approved_at", "Approved", "timestamp"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One overridden obligation with its request resolved — the input of ``dataset_rows``."""

    contract_external_id: str
    obligation_key: str
    product_code: str
    default_version_label: str | None
    override_version_label: str | None
    request: support.Request


def row_key(contract_external_id: str, obligation_key: str, request_no: str) -> str:
    return f"{ROW_KEY_PREFIX}{contract_external_id}:{obligation_key}:{request_no}"


def dataset_rows(found: Iterable[Source], names: Mapping[UUID, str]) -> list[dict[str, Any]]:
    """The RPT-22 rows in (contract, obligation key, request number) order. Pure."""
    rows: list[dict[str, Any]] = []
    ordered = sorted(
        found,
        key=lambda item: (item.contract_external_id, item.obligation_key, item.request.request_no),
    )
    for item in ordered:
        request = item.request
        rows.append(
            {
                "row_key": row_key(
                    item.contract_external_id, item.obligation_key, request.request_no
                ),
                "contract_external_id": item.contract_external_id,
                "obligation_key": item.obligation_key,
                "product_code": item.product_code,
                "default_version_label": item.default_version_label,
                "override_version_label": item.override_version_label,
                "justification": request.comment,
                "requested_by": support.actor_names([request.preparer], names)[0],
                "approved_by": support.joined(support.actor_names(request.approvers, names)),
                "approved_at": request.approved_at,
            }
        )
    return rows


def _version_names(session: Session, version_ids: Iterable[UUID | None]) -> dict[UUID, str]:
    wanted = sorted({value for value in version_ids if value is not None}, key=str)
    if not wanted:
        return {}
    statement = (
        select(
            ssp_book_version.c.id,
            ssp_book.c.code,
            ssp_book_version.c.legacy_version_label,
            ssp_book_version.c.version_no,
        )
        .select_from(
            ssp_book_version.join(
                ssp_book,
                and_(
                    ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
                    ssp_book.c.id == ssp_book_version.c.ssp_book_id,
                ),
            )
        )
        .where(ssp_book_version.c.id.in_(wanted))
    )
    return {
        UUID(str(version_id)): support.version_name(code, label, number)
        for version_id, code, label, number in session.execute(statement)
    }


def first_overrides(
    versions: Iterable[Mapping[str, Any]],
) -> dict[tuple[UUID, UUID], tuple[Mapping[str, Any], UUID | None]]:
    """(obligation id, request id) → (the first version carrying the request, the default pin):
    ``versions`` are obligation versions in record order; the default pin is the SSP book version
    of the latest earlier version of the same obligation and book that carries no override. Pure."""
    plain: dict[tuple[UUID, str], UUID | None] = {}
    found: dict[tuple[UUID, UUID], tuple[Mapping[str, Any], UUID | None]] = {}
    for row in versions:
        obligation_id = UUID(str(row["obligation_id"]))
        book = (obligation_id, str(support.text(row["book_code"])))
        request_id = support.uuid_of(row["ssp_override_approval_request_id"])
        if request_id is None:
            plain[book] = support.uuid_of(row["ssp_book_version_id"])
            continue
        found.setdefault((obligation_id, request_id), (row, plain.get(book)))
    return found


def sources(uow: UnitOfWork, params: ReportParams, *, cutoff: datetime) -> list[Source]:
    """Every overridden obligation in scope by the cutoff whose request is approved by then."""
    session = uow.session
    if not params.entity_ids:
        return []
    tenant = obligation_version.c.tenant_id
    joined = obligation_version.join(
        contract_version,
        and_(
            contract_version.c.tenant_id == tenant,
            contract_version.c.id == obligation_version.c.contract_version_id,
        ),
    ).join(
        contract,
        and_(contract.c.tenant_id == tenant, contract.c.id == obligation_version.c.contract_id),
    )
    scope = (
        obligation_version.c.contracting_entity_id.in_(list(params.entity_ids)),
        contract_version.c.known_at <= cutoff,
    )
    overridden = (
        select(obligation_version.c.obligation_id)
        .select_from(joined)
        .where(obligation_version.c.ssp_override_approval_request_id.is_not(None), *scope)
    )
    statement = (
        select(
            obligation_version.c.obligation_id,
            obligation_version.c.book_code,
            obligation_version.c.obligation_key,
            obligation_version.c.product_code,
            obligation_version.c.ssp_book_version_id,
            obligation_version.c.ssp_override_approval_request_id,
            contract.c.external_id.label("contract_external_id"),
        )
        .select_from(joined)
        .where(obligation_version.c.obligation_id.in_(overridden), *scope)
        .order_by(
            contract_version.c.known_at,
            obligation_version.c.book_code,
            obligation_version.c.version_no,
        )
    )
    first = first_overrides(dict(row) for row in session.execute(statement).mappings())
    if not first:
        return []
    version_names = _version_names(
        session,
        [support.uuid_of(row["ssp_book_version_id"]) for row, _ in first.values()]
        + [pin for _, pin in first.values()],
    )
    approvals = support.requests_by_id(session, (key[1] for key in first), cutoff=cutoff)
    found: list[Source] = []
    for (_, request_id), (row, default_pin) in first.items():
        request = approvals.get(request_id)
        if request is None or request.approved_at is None:
            continue
        override_pin = support.uuid_of(row["ssp_book_version_id"])
        found.append(
            Source(
                contract_external_id=str(row["contract_external_id"]),
                obligation_key=str(row["obligation_key"]),
                product_code=str(row["product_code"]),
                default_version_label=(
                    None if default_pin is None else version_names.get(default_pin)
                ),
                override_version_label=(
                    None if override_pin is None else version_names.get(override_pin)
                ),
                request=request,
            )
        )
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    first, last = support.date_range(session, params, today=True)
    bounds = support.instants(first, last)
    found = [
        item
        for item in sources(uow, params, cutoff=cutoff)
        if support.within(item.request.approved_at, bounds)
    ]
    names = support.names_of(session, (item.request for item in found))
    rows = dataset_rows(found, names)
    totals = {"row_count": len(rows), "from_date": first.isoformat(), "to_date": last.isoformat()}
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "Source",
    "build",
    "dataset_rows",
    "first_overrides",
    "row_key",
    "sources",
]
