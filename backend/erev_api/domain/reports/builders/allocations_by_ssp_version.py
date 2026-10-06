"""RPT-21 ``allocations_by_ssp_version`` Allocations by SSP version (SCREENS_B §5.6.4 RPT-21; 04
T-CON-08, T-CON-11, T-REF-28, T-REF-29, E-114; ENGINE_SPEC S05-R-01, S06 boundaries; D-18; PRD
J-03-AC-2, WLD-X-23; 03 REQ-SSP-011, REQ-SSP-012, REQ-SSP-014, REQ-ALC-008; CTL-011; BUILD_SPEC
RPS-9).

One row per obligation allocation event of the run's book whose contracting entity is in scope and
whose date lies in ``from_date`` .. ``to_date`` (defaults: the first day of the context fiscal year
and the end of the context period); ``ssp_book_version_id`` keeps the allocations priced from one
SSP book version. The allocation lineage is what T-CON-11 stores with every obligation version
(REQ-SSP-011), read as of the run's record cutoff (``contract_version.known_at``), from the
versions whose contract status enters the disclosures (ACTIVE, COMPLETED, TERMINATED) of the
combination group the obligation is in at the cutoff.

An obligation's versions fall into allocation segments in record order: the first segment, and a
new one at each version whose ``modification_boundary_no`` exceeds the version before it — a
606-10-25-13(a) reallocation (REQ-MOD-020). Each segment is one allocation event, read from the
LATEST version of the segment at the cutoff, which the row key names: a later correction of the
same allocation — an approved SSP override re-allocates the group from inception (S06-R-26) — is
the allocation the row shows, and its Explain links resolve on that version.

- **Inception**: the first segment of a booking line. ``allocation_date`` is the contract's
  inception date (S05-R-01: booking lines are priced at the group inception date). The row is the
  obligation's original lineage: the SSP range (low, mid, high, extended), the selected SSP and the
  E-114 range check of the original stated price (``original_ssp_*``), the original allocation and
  its adjustment against the original stated price; ``allocation_weight`` is the version's.
- **Modification**: a later segment, and the first segment of an obligation a boundary created.
  ``allocation_date`` is the effective date of the modification event among the cause events of the
  segment's first version, else that version's effective date. An obligation the boundary created
  is priced at that date and carries its original lineage like an inception row; an obligation that
  existed before carries the re-based extended SSP of the boundary as ``selected_ssp``
  (``remaining_ssp``), its stated price, allocation, adjustment and weight after the reallocation
  and no range — T-CON-11 keeps the range of the obligation's own pricing date only, and the row
  never shows that older range as the boundary's.

``ssp_version_label`` names the SSP book version as ``<book code> <version label>`` and
``ssp_entry_id`` its value row (REQ-SSP-011 "value row id"; export and API only); ``is_override``
is true when the version carries an approved SSP override (REQ-SSP-006; RPT-22). Money cells are in
the transaction currency (RPT-21 "Currency view: no"); ``allocation_weight`` is the stored exact
ratio. Rows are ordered by contract, obligation key and version number; ``row_key``
``allocation:<external id>:<obligation key>:<version no>`` with the number of the version read; one
``TOTAL:<ISO>`` row per currency and control totals per currency for stated price, allocation and
allocation adjustment, beside ``row_count`` and the range applied. No tie-out.

The number of the version read is its number along the contract's chain
(``contract_history.chain_numbers``; item S-1 of lane F-RPS-REG after RPT-FORMER-GROUP-READERS-1,
supervisor ruling R-117 (a)): ``version_no`` counts the versions of ONE group, so the first
version of a group that a contract joined after it had been computed in its own is that group's
1 and the contract's 2 — the number the contract history gives the same version.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    obligation_version,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.contracts.queries import range_position
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, contract_history
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.uow import UnitOfWork

CODE: Final = "allocations_by_ssp_version"
ROW_KEY_PREFIX: Final = "allocation:"
TOTAL_PREFIX: Final = "TOTAL:"
INCEPTION: Final = "Inception"  # SCREENS_B RPT-21 ``cause``
MODIFICATION: Final = "Modification"
CAUSES: Final = (INCEPTION, MODIFICATION)
# E-03 types whose event opens a 25-13(a) boundary (the modification register's set).
MODIFICATION_EVENT_TYPES: Final = frozenset(
    {"CONTRACT_AMENDED", "CONTRACT_TERMINATED", "REGROUPED"}
)
TOTALLED: Final = ("stated_price", "allocated_amount", "allocation_adjustment")
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("allocation_date", "Allocated on", "date"),
    Column("cause", "Cause", "text"),
    Column("ssp_version_label", "SSP book version", "code"),
    Column("ssp_entry_id", "SSP entry", "code"),
    Column("ssp_method", "SSP method", "code"),
    Column("currency", "Currency", "code"),
    Column("ssp_low", "SSP low", "money"),
    Column("ssp_mid", "SSP mid", "money"),
    Column("ssp_high", "SSP high", "money"),
    Column("stated_price", "Stated price", "money"),
    Column("range_status", "Range check", "code"),
    Column("selected_ssp", "Selected SSP", "money"),
    Column("allocation_weight", "Weight", "decimal"),
    Column("allocated_amount", "Allocated", "money"),
    Column("allocation_adjustment", "Allocation adjustment", "money"),
    Column("is_override", "Override", "boolean"),
)


@dataclass(frozen=True, slots=True)
class Allocation:
    """One allocation event of one obligation — the input of ``dataset_rows``."""

    contract_external_id: str
    obligation_key: str
    version_no: int
    product_code: str
    allocation_date: date
    cause: str  # CAUSES
    ssp_book_version_id: UUID | None
    ssp_version_label: str | None
    ssp_entry_id: UUID | None
    ssp_method: str | None
    currency: str
    ssp_low: Decimal | None
    ssp_mid: Decimal | None
    ssp_high: Decimal | None
    stated_price: Decimal
    range_status: str | None  # E-114
    selected_ssp: Decimal
    allocation_weight: Decimal
    allocated_amount: Decimal
    allocation_adjustment: Decimal
    is_override: bool


def row_key(contract_external_id: str, obligation_key: str, version_no: int) -> str:
    return f"{ROW_KEY_PREFIX}{contract_external_id}:{obligation_key}:{version_no}"


@dataclass(frozen=True, slots=True)
class Segment:
    """One allocation segment of an obligation: the version that opened it (its cause events date
    the allocation) and its latest version at the cutoff (the lineage read)."""

    first: Mapping[str, Any]
    latest: Mapping[str, Any]
    cause: str  # CAUSES
    created: bool  # the obligation's first segment


def segments_of(versions: Sequence[Mapping[str, Any]]) -> list[Segment]:
    """The allocation segments of one obligation's versions (record order, one combination
    group): the first, and a new one at each rise of ``modification_boundary_no``. Pure."""
    found: list[Segment] = []
    boundary = 0
    for row in versions:
        number = int(row["modification_boundary_no"])
        if not found:
            cause = INCEPTION if number == 0 else MODIFICATION
            found.append(Segment(first=row, latest=row, cause=cause, created=True))
        elif number > boundary:
            found.append(Segment(first=row, latest=row, cause=MODIFICATION, created=False))
        else:
            last = found[-1]
            found[-1] = Segment(
                first=last.first, latest=row, cause=last.cause, created=last.created
            )
            continue
        boundary = number
    return found


def current_group(versions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The versions of the combination group the obligation is in at its latest version (record
    order kept). Pure."""
    if not versions:
        return []
    group = versions[-1]["combination_group_id"]
    return [row for row in versions if row["combination_group_id"] == group]


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def allocation(
    segment: Segment, *, allocation_date: date, chain_no: int | None = None
) -> Allocation:
    """The lineage of one allocation event from the latest version of its segment (module
    docstring): the obligation's original lineage for its first segment, the reallocation's
    figures for a later one. ``chain_no`` is the number of that version along its contract's
    chain; a version outside the chain keeps its stored number. Pure."""
    row = segment.latest
    if segment.created:
        low, mid, high = (
            _decimal(row[name])
            for name in ("original_ssp_low", "original_ssp_mid", "original_ssp_high")
        )
        stated = Decimal(row["original_stated_price"])
        position = range_position(low, high, stated)
        selected = Decimal(row["original_ssp_selected"])
        allocated = Decimal(row["original_allocated_amount"])
        adjustment = allocated - stated
    else:
        low = mid = high = position = None
        stated = Decimal(row["stated_price"])
        selected = Decimal(row["remaining_ssp"])
        allocated = Decimal(row["allocated_amount"])
        adjustment = Decimal(row["allocation_adjustment"])
    return Allocation(
        contract_external_id=str(row["contract_external_id"]),
        obligation_key=str(row["obligation_key"]),
        version_no=int(row["version_no"]) if chain_no is None else chain_no,
        product_code=str(row["product_code"]),
        allocation_date=allocation_date,
        cause=segment.cause,
        ssp_book_version_id=support.uuid_of(row["ssp_book_version_id"]),
        ssp_version_label=(
            None
            if row["ssp_book_version_id"] is None
            else support.version_name(
                row["ssp_book_code"], row["ssp_legacy_version_label"], row["ssp_version_no"]
            )
        ),
        ssp_entry_id=support.uuid_of(row["ssp_entry_id"]),
        ssp_method=support.text(row["ssp_method"]),
        currency=str(row["txn_currency"]).strip(),
        ssp_low=low,
        ssp_mid=mid,
        ssp_high=high,
        stated_price=stated,
        range_status=None if position is None else str(position.value),
        selected_ssp=selected,
        allocation_weight=Decimal(row["allocation_weight"]),
        allocated_amount=allocated,
        allocation_adjustment=adjustment,
        is_override=row["ssp_override_approval_request_id"] is not None,
    )


def _money(value: Decimal | None, currency: str) -> dict[str, str] | None:
    return None if value is None else tie_outs.money(value, currency)


def dataset_rows(found: Iterable[Allocation]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows with one ``TOTAL:<ISO>`` row per currency, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    ordered = sorted(
        found, key=lambda item: (item.contract_external_id, item.obligation_key, item.version_no)
    )
    for item in ordered:
        rows.append(
            {
                "row_key": row_key(item.contract_external_id, item.obligation_key, item.version_no),
                "contract_external_id": item.contract_external_id,
                "obligation_key": item.obligation_key,
                "product_code": item.product_code,
                "allocation_date": item.allocation_date,
                "cause": item.cause,
                "ssp_version_label": item.ssp_version_label,
                "ssp_entry_id": None if item.ssp_entry_id is None else str(item.ssp_entry_id),
                "ssp_method": item.ssp_method,
                "currency": item.currency,
                "ssp_low": _money(item.ssp_low, item.currency),
                "ssp_mid": _money(item.ssp_mid, item.currency),
                "ssp_high": _money(item.ssp_high, item.currency),
                "stated_price": tie_outs.money(item.stated_price, item.currency),
                "range_status": item.range_status,
                "selected_ssp": tie_outs.money(item.selected_ssp, item.currency),
                "allocation_weight": support.ratio_text(item.allocation_weight),
                "allocated_amount": tie_outs.money(item.allocated_amount, item.currency),
                "allocation_adjustment": tie_outs.money(item.allocation_adjustment, item.currency),
                "is_override": item.is_override,
            }
        )
        into = totals.setdefault(item.currency, {})
        tie_outs.add(into, "stated_price", item.stated_price)
        tie_outs.add(into, "allocated_amount", item.allocated_amount)
        tie_outs.add(into, "allocation_adjustment", item.allocation_adjustment)
    count = len(rows)
    for currency, values in sorted(totals.items()):
        rows.append(
            {
                "row_key": f"{TOTAL_PREFIX}{currency}",
                "currency": currency,
                **{name: tie_outs.money(values[name], currency) for name in TOTALLED},
            }
        )
    control: dict[str, Any] = {"row_count": count}
    for name in TOTALLED:
        control[f"{name}_total"] = tie_outs.by_currency(
            {currency: values[name] for currency, values in totals.items()}
        )
    return rows, control


def _versions(
    session: Session, params: ReportParams, *, book_code: str, cutoff: datetime
) -> dict[UUID, list[dict[str, Any]]]:
    """Per obligation, its versions of the book in scope recorded by the cutoff, in record order
    (``contract_version.known_at``, then version number)."""
    if not params.entity_ids:
        return {}
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
            contract,
            and_(contract.c.tenant_id == tenant, contract.c.id == obligation_version.c.contract_id),
        )
        .outerjoin(
            ssp_book_version,
            and_(
                ssp_book_version.c.tenant_id == tenant,
                ssp_book_version.c.id == obligation_version.c.ssp_book_version_id,
            ),
        )
        .outerjoin(
            ssp_book,
            and_(ssp_book.c.tenant_id == tenant, ssp_book.c.id == ssp_book_version.c.ssp_book_id),
        )
    )
    statement = (
        select(
            obligation_version,
            contract_version.c.known_at.label("known_at"),
            contract_version.c.cause_event_ids.label("cause_event_ids"),
            contract.c.external_id.label("contract_external_id"),
            contract.c.inception_date.label("inception_date"),
            ssp_book.c.code.label("ssp_book_code"),
            ssp_book_version.c.legacy_version_label.label("ssp_legacy_version_label"),
            ssp_book_version.c.version_no.label("ssp_version_no"),
        )
        .select_from(joined)
        .where(
            obligation_version.c.book_code == book_code,
            obligation_version.c.contracting_entity_id.in_(list(params.entity_ids)),
            contract_version.c.known_at <= cutoff,
            contract_version.c.status_in_book.in_(sorted(tie_outs.INCLUDED_STATUSES)),
        )
        .order_by(contract_version.c.known_at, obligation_version.c.version_no)
    )
    found: dict[UUID, list[dict[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        found.setdefault(UUID(str(row["obligation_id"])), []).append(dict(row))
    return found


def _modification_dates(session: Session, event_ids: Iterable[UUID]) -> dict[UUID, date]:
    """Effective date per modification event among ``event_ids``."""
    wanted = sorted(set(event_ids), key=str)
    if not wanted:
        return {}
    statement = select(contract_event.c.id, contract_event.c.effective_date).where(
        contract_event.c.id.in_(wanted),
        contract_event.c.event_type.in_(sorted(MODIFICATION_EVENT_TYPES)),
    )
    return {UUID(str(event_id)): day for event_id, day in session.execute(statement)}


def allocations(uow: UnitOfWork, params: ReportParams, *, book_code: str) -> list[Allocation]:
    """Every allocation event in scope by the cutoff, before the date and version filters."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    segments: list[Segment] = []
    for versions in _versions(session, params, book_code=book_code, cutoff=cutoff).values():
        segments += segments_of(current_group(versions))
    dates = _modification_dates(
        session,
        (
            UUID(str(event_id))
            for segment in segments
            if segment.cause == MODIFICATION
            for event_id in segment.first["cause_event_ids"] or ()
        ),
    )
    numbers = contract_history.chain_numbers(
        session,
        book_code=book_code,
        contract_ids={UUID(str(segment.latest["contract_id"])) for segment in segments},
        cutoff=cutoff,
    )
    found: list[Allocation] = []
    for segment in segments:
        if segment.cause == INCEPTION:
            day: date = segment.first["inception_date"]
        else:
            caused = [
                dates[UUID(str(event_id))]
                for event_id in segment.first["cause_event_ids"] or ()
                if UUID(str(event_id)) in dates
            ]
            day = max(caused) if caused else segment.first["effective_date"]
        read = segment.latest
        version = (UUID(str(read["contract_id"])), UUID(str(read["contract_version_id"])))
        found.append(allocation(segment, allocation_date=day, chain_no=numbers.get(version)))
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    first, last = support.date_range(session, params)
    version_id = support.uuid_of(params.parameters.get("ssp_book_version_id"))
    found = [
        item
        for item in allocations(uow, params, book_code=book_code)
        if first <= item.allocation_date <= last
        and (version_id is None or item.ssp_book_version_id == version_id)
    ]
    rows, control = dataset_rows(found)
    control["from_date"], control["to_date"] = first.isoformat(), last.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=control)


__all__ = [
    "CAUSES",
    "CODE",
    "COLUMNS",
    "INCEPTION",
    "MODIFICATION",
    "Allocation",
    "Segment",
    "allocation",
    "allocations",
    "build",
    "current_group",
    "dataset_rows",
    "row_key",
    "segments_of",
]
