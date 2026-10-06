"""RPT-20 ``ssp_version_diff`` SSP version diff (SCREENS_B §5.6.4 RPT-20; 04 T-REF-29, T-REF-30,
T-REF-31, §16.4 ``GET /ssp-book-versions/{id}/diff``; PRD J-02-AC-2; 03 REQ-SSP-007, REQ-SSP-012;
BUILD_SPEC RPS-9).

One row per entry key (product, stratification, region, channel, segment, deal-size band, term
band, currency) present in ``ssp_book_version_id`` or in the version it is compared with:
``against_version_id`` (a version of the same book), by default the prior approved version — the
approved version of the book with the highest version number below the chosen version's, approved
by the record cutoff; without one every entry is "Added". ``change`` is "Added" (only in the
version), "Removed" (only in the compared version), "Changed" (both, with different content) or
"Unchanged"; ``only_changes`` (default true, SCREENS_B RPT-20) omits the unchanged entries. The
comparison is ``domain.ssp.books.diff``, the one the version's ``diff_summary`` and the approval
routing use (REQ-SSP-007).

Values: ``method_before`` / ``method_after`` are E-47 literals; low, mid, high and point are the
values of the entry's ``NONE`` band (T-REF-31) as exact text with at least the currency's minor-unit
decimals (DS-FMT-13 cells; never rounded; the ratios of a ``PERCENT_OF_LIST`` entry as exact
ratios) — an entry that holds only quantity, deal-size or term
bands has no such values and its row carries the change alone; ``mid_change_ratio`` is (after mid −
before mid) ÷ before mid of the ``NONE`` bands as an exact ratio, empty for added and removed rows.
Rows are ordered by the entry key; ``row_key`` ``entry:<product code>:<stratification>:<dimension
keys>:<currency>`` with every component percent-encoded (CV-21) and the five dimension keys joined
with ``|``. Control totals ``added``, ``removed`` and ``changed`` count every entry, whatever
``only_changes`` shows; no totals and no tie-out.

Scope and cutoff: the book is one of the run's entities' books or a tenant-wide book; both versions
were created by the record cutoff. The entries of a version are frozen from its approval (DB-04),
so an explicit historical run is served for versions approved by the cutoff and refused by name for
a version that changed after it and was not yet approved then (REGISTER-CUTOFF-1); a live run never
refuses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import ssp_book, ssp_book_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.builders.out_of_period_register import encode_component
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.ssp import books, queries
from erev_api.enums import ConfigStatus, SspValueBasis
from erev_api.uow import UnitOfWork

CODE: Final = "ssp_version_diff"
ROW_KEY_PREFIX: Final = "entry:"
ADDED: Final = "Added"
REMOVED: Final = "Removed"
CHANGED: Final = "Changed"
UNCHANGED: Final = "Unchanged"
CHANGES: Final = (ADDED, REMOVED, CHANGED, UNCHANGED)  # SCREENS_B RPT-20 ``change``
ONLY_CHANGES_DEFAULT: Final = True  # SCREENS_B RPT-20 "Only changed entries: default true"
NOT_COMPARED: Final = "—"  # RPT-20 "em dash for added and removed rows"
CHOOSE_VERSION: Final = "Choose a version."
SAME_BOOK: Final = "Choose a version of the same SSP book."
HISTORY_UNAVAILABLE: Final = (
    "The SSP version diff cannot state the entries of {version} as of {cutoff}: the version last "
    "changed at {updated_at} and was not approved by the cutoff, so its entries were still "
    "editable and T-REF-30 keeps no row history (not reconstructed). Run the diff at a later "
    "known_at or current."
)
VALUES: Final = ("low", "mid", "high", "point")
PERCENT_OF_LIST: Final = SspValueBasis.PERCENT_OF_LIST.value
COLUMNS: Final = (
    Column("change", "Change", "text"),
    Column("product_code", "Product", "code"),
    Column("stratification", "Stratification", "text"),
    Column("region", "Region", "text"),
    Column("channel", "Channel", "text"),
    Column("segment", "Segment", "text"),
    Column("currency", "Currency", "code"),
    Column("method_before", "Method before", "code"),
    Column("method_after", "Method after", "code"),
    Column("low_before", "Low before", "decimal"),
    Column("low_after", "Low after", "decimal"),
    Column("mid_before", "Mid before", "decimal"),
    Column("mid_after", "Mid after", "decimal"),
    Column("high_before", "High before", "decimal"),
    Column("high_after", "High after", "decimal"),
    Column("point_before", "Point before", "decimal"),
    Column("point_after", "Point after", "decimal"),
    Column("mid_change_ratio", "Mid change", "decimal", empty_text=NOT_COMPARED),
)


def row_key(key: books.EntryKey) -> str:
    """``entry:<product code>:<stratification>:<dimension keys>:<currency>`` (module docstring)."""
    dimensions = "|".join(
        encode_component(getattr(key, name) or "") for name in books.DIMENSION_KEYS
    )
    return (
        f"{ROW_KEY_PREFIX}{encode_component(key.product_code)}:"
        f"{encode_component(key.stratification)}:{dimensions}:{encode_component(key.currency)}"
    )


def _order(key: books.EntryKey) -> tuple[str, ...]:
    return tuple("" if value is None else str(value) for value in key)


def _none_band(entry: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if entry is None:
        return None
    for band in entry["ranges"]:
        if band["band_dimension"] == books.BAND_NONE:
            found: Mapping[str, Any] = band
            return found
    return None


def _side(entry: Mapping[str, Any] | None, suffix: str, currency: str) -> dict[str, Any]:
    """The method and ``NONE`` band values of one side of a row (empty for an absent entry); a
    ``PERCENT_OF_LIST`` entry (E-49) holds ratios, written as exact ratios."""
    band = _none_band(entry)
    values: dict[str, Any] = {
        f"method_{suffix}": None if entry is None else str(support.text(entry["method"]))
    }
    ratio = entry is not None and support.text(entry["value_basis"]) == PERCENT_OF_LIST
    for name in VALUES:
        stored = None if band is None else band[f"{name}_value"]
        value = None if stored is None else Decimal(str(stored))
        values[f"{name}_{suffix}"] = (
            support.ratio_text(value) if ratio else support.rate_text(value, currency)
        )
    return values


def dataset_rows(
    entries: Sequence[Mapping[str, Any]],
    against: Sequence[Mapping[str, Any]],
    *,
    only_changes: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """(rows, control totals) of the entries of a version against the compared version's; both
    lists are API-S-SspEntry items (``domain.ssp.queries.entries_of``). Pure."""
    found = books.diff(entries, against)
    after = {books.key_of(entry): entry for entry in entries}
    before = {books.key_of(entry): entry for entry in against}
    changed = {books.EntryKey(**item["key"]): item for item in found["changed"]}
    rows: list[dict[str, Any]] = []
    for key in sorted(after.keys() | before.keys(), key=_order):
        old, new = before.get(key), after.get(key)
        if old is None:
            change = ADDED
        elif new is None:
            change = REMOVED
        else:
            change = CHANGED if key in changed else UNCHANGED
        if only_changes and change == UNCHANGED:
            continue
        ratio = changed[key]["mid_change_ratio"] if key in changed else None
        rows.append(
            {
                "row_key": row_key(key),
                "change": change,
                "product_code": key.product_code,
                "stratification": key.stratification or None,
                "region": key.region,
                "channel": key.channel,
                "segment": key.segment,
                "currency": key.currency,
                **_side(old, "before", key.currency),
                **_side(new, "after", key.currency),
                "mid_change_ratio": None if ratio is None else str(ratio),
            }
        )
    totals = {
        "added": len(found["added"]),
        "removed": len(found["removed"]),
        "changed": len(found["changed"]),
    }
    return rows, totals


def frozen_by(row: Mapping[str, Any], cutoff: datetime) -> bool:
    """The version's entries cannot have moved after ``cutoff``: it was approved by then (DB-04),
    or it has not changed since. Pure."""
    approved = (
        support.text(row["status"]) == ConfigStatus.APPROVED.value
        and row["published_at"] is not None
        and row["published_at"] <= cutoff
    )
    return bool(approved or row["updated_at"] <= cutoff)


def _versions(
    session: Session, params: ReportParams, *, cutoff: datetime
) -> dict[UUID, dict[str, Any]]:
    """Every version of the books in the run's scope created by the cutoff, by id."""
    joined = ssp_book_version.join(
        ssp_book,
        and_(
            ssp_book.c.tenant_id == ssp_book_version.c.tenant_id,
            ssp_book.c.id == ssp_book_version.c.ssp_book_id,
        ),
    )
    statement = (
        select(ssp_book_version, ssp_book.c.code.label("book_code"), ssp_book.c.entity_id)
        .select_from(joined)
        .where(ssp_book_version.c.created_at <= cutoff)
    )
    allowed = {None, *params.entity_ids}
    return {
        UUID(str(row["id"])): dict(row)
        for row in session.execute(statement).mappings()
        if support.uuid_of(row["entity_id"]) in allowed
    }


def compared_versions(
    versions: Mapping[UUID, Mapping[str, Any]],
    *,
    version_id: UUID | None,
    against_id: UUID | None,
    cutoff: datetime,
) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    """(the version, the version it is compared with or None): 422 by name for an absent or
    unknown version and for a compared version of another book (SCREENS_B RPT-20 copy). Pure."""
    chosen = None if version_id is None else versions.get(version_id)
    if chosen is None:
        raise tie_outs.invalid("ssp_book_version_id", CHOOSE_VERSION)
    if against_id is not None:
        other = versions.get(against_id)
        if other is None or other["ssp_book_id"] != chosen["ssp_book_id"]:
            raise tie_outs.invalid("against_version_id", SAME_BOOK)
        return chosen, other
    prior = [
        row
        for row in versions.values()
        if row["ssp_book_id"] == chosen["ssp_book_id"]
        and int(row["version_no"]) < int(chosen["version_no"])
        and support.text(row["status"]) == ConfigStatus.APPROVED.value
        and row["published_at"] is not None
        and row["published_at"] <= cutoff
    ]
    prior.sort(key=lambda row: int(row["version_no"]))
    return chosen, (prior[-1] if prior else None)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    chosen, other = compared_versions(
        _versions(session, params, cutoff=cutoff),
        version_id=support.uuid_of(params.parameters.get("ssp_book_version_id")),
        against_id=support.uuid_of(params.parameters.get("against_version_id")),
        cutoff=cutoff,
    )
    if params.historical:
        for row in (chosen, other):
            if row is not None and not frozen_by(row, cutoff):
                raise tie_outs.invalid(
                    "known_at",
                    HISTORY_UNAVAILABLE.format(
                        version=support.version_name(
                            row["book_code"], row["legacy_version_label"], row["version_no"]
                        ),
                        cutoff=cutoff.isoformat(),
                        updated_at=row["updated_at"].isoformat(),
                    ),
                )
    only_changes = params.parameters.get("only_changes")
    rows, totals = dataset_rows(
        queries.entries_of(session, UUID(str(chosen["id"]))),
        [] if other is None else queries.entries_of(session, UUID(str(other["id"]))),
        only_changes=ONLY_CHANGES_DEFAULT if only_changes is None else bool(only_changes),
    )
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "ADDED",
    "CHANGED",
    "CHANGES",
    "CODE",
    "COLUMNS",
    "ONLY_CHANGES_DEFAULT",
    "REMOVED",
    "UNCHANGED",
    "build",
    "compared_versions",
    "dataset_rows",
    "frozen_by",
    "row_key",
]
