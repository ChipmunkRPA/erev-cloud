"""CSV v2 template ``ssp_values``: a DRAFT SSP book version and its entries (04 T-IMP-01, NC-19,
T-REF-29 to T-REF-31; API-R-26; PRD SM-04; BUILD_SPEC DIN-9; SSP declarations on import, 04 rev
1.19, D-97 (3), (3a) — ``ssp_declarations``).

[J] L5-1-Q-22: column ``ssp_book_code`` names the book (the path member ``{id}`` of ``POST
/ssp-books/{id}/versions``); the version members of API-S-SspBookVersionCreate are repeated on each
row, and each row is one entry of ``POST /ssp-book-versions/{id}/entries`` with at most one band
(``lines.ranges.*``); rows of one entry key merge their bands. The version stays DRAFT and follows
the RFD lifecycle (submission, study, approval).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import product, ssp_book, ssp_book_version, ssp_entry, ssp_range
from erev_api.domain.imports.csv_v2 import ssp_declarations
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    Repeated,
    flatten,
    grouped,
    header_cells,
    line_cells,
    row_model,
    unflatten,
)
from erev_api.domain.ssp.commands import create_ssp_book_version, upsert_ssp_entries
from erev_api.enums import SourceObjectType
from erev_api.problems import Problem
from erev_api.schemas.ssp_books import SspBookVersionIn, SspEntriesIn, SspEntryIn, SspRangeIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "SspValuesIn"]

CODE: Final = "ssp_values"
BOOK_UNKNOWN: Final = "No SSP book has the code {code}."
ENTRY_KEY: Final = (
    "product_code",
    "stratification",
    "region",
    "channel",
    "segment",
    "deal_size_band",
    "term_band",
    "currency",
    "method",
)


class SspEntryRowIn(SspEntryIn):
    """An entry with at most one band per row (L5-1-Q-22).

    The T-REF-30 declarations are carried as text so that a blank cell stays *omitted* (the API's
    ``value_basis`` default is applied by the API to a non-series product only, D-97 (3a)) and so
    that the E-49 / E-125 vocabularies are validated by ``ssp_declarations`` at validation time,
    as row-located findings, before any request reaches the API (schema bridge to ENG-C1b: the
    ``quantity_unit`` member of API-S-SspEntry and its column landed with C1b's migration 0056,
    04 1.41).
    """

    value_basis: str | None = None  # type: ignore[assignment]
    # API-S-SspEntry types this member SspQuantityUnit (ENG-C1b, 04 1.41); the import carries text
    # and validates the E-125 vocabulary as a row-located finding (same bridge as value_basis).
    quantity_unit: str | None = None  # type: ignore[assignment]
    ranges: SspRangeIn | None = None  # type: ignore[assignment]


class SspValuesIn(BaseModel):
    """A DRAFT version of one book with its entries (L5-1-Q-22)."""

    model_config = ConfigDict(extra="forbid")

    ssp_book_code: str
    legacy_version_label: str | None = None
    effective_from_date: date | None = None
    effective_to_date: date | None = None
    methodology_label: str
    is_methodology_change: bool = False
    lines: list[SspEntryRowIn]


COLUMNS: Final = tuple(flatten(SspValuesIn))
ROW_MODEL: Final = row_model("CsvSspValuesRow", COLUMNS)
_LINES: Final = frozenset({"lines"})
# The rows of one book, label and effective-from date make one version, and within it the band
# rows of one entry key make one entry. The version's other members are read from its first row
# and an entry's members from the entry's first row, so a later row states them alike or not at
# all (05 IPL-05 rev 1.210). A row states its own band; the two declarations of an entry keep
# their own rule and sentence (``ssp_declarations``: SSP_ENTRY_DECLARATION_DISAGREES).
KEY: Final = ("ssp_book_code", "legacy_version_label", "effective_from_date")
ENTRY: Final = (*KEY, *(f"lines.{name}" for name in ENTRY_KEY))
REPEATS: Final = (
    Repeated(
        "SSP book version",
        KEY,
        header_cells(COLUMNS, KEY),
        ("ssp_book_code", "legacy_version_label"),
    ),
    Repeated(
        "SSP entry",
        ENTRY,
        line_cells(
            COLUMNS,
            ENTRY,
            own=("lines.ranges.", ssp_declarations.BASIS_COLUMN, ssp_declarations.UNIT_COLUMN),
        ),
        ("lines.product_code",),
    ),
)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per (book, label, effective from) in worksheet order."""
    return [
        Plan(
            key=code,
            rows=tuple(members),
            body={
                **unflatten(members[0].normalized, skip=_LINES),
                "lines": [unflatten(row.normalized).get("lines", {}) for row in members],
            },
        )
        for (code, _, _), members in grouped(rows, KEY).items()
    ]


def _key(line: SspEntryRowIn) -> tuple[Any, ...]:
    return tuple(getattr(line, name) for name in ENTRY_KEY)


def _declared(members: dict[str, Any]) -> dict[str, Any]:
    """The entry request with its declarations as the API carries them: an omitted declaration
    is not sent (the API applies its T-REF-30 default; the cross rule has already refused an
    omitted series basis), and ``quantity_unit`` is sent only when API-S-SspEntry has the member
    (schema bridge, ENG-C1b)."""
    for name in ("value_basis", "quantity_unit"):
        if members.get(name) is None or name not in SspEntryIn.model_fields:
            members.pop(name, None)
    return members


def _merged_entries(
    lines: Sequence[SspEntryRowIn],
) -> dict[tuple[Any, ...], tuple[SspEntryRowIn, list[SspRangeIn]]]:
    """The rows grouped into entries (one band per row, L5-1-Q-22), refused before any command
    when the band rows of one entry declare differently (F-DIN-SSP-R1 defensive refusal: the
    cross rule refused this at validation; a merge must never collapse the rows' declarations
    into the first row's)."""
    entries: dict[tuple[Any, ...], tuple[SspEntryRowIn, list[SspRangeIn]]] = {}
    for line in lines:
        lead, bands = entries.setdefault(_key(line), (line, []))
        if (lead.value_basis, lead.quantity_unit) != (line.value_basis, line.quantity_unit):
            raise Problem(
                "validation-failed",
                ssp_declarations.ENTRY_DISAGREES.format(
                    member="declaration",
                    first=lead.product_code,
                    expected=(lead.value_basis, lead.quantity_unit),
                    actual=(line.value_basis, line.quantity_unit),
                ),
            )
        if line.ranges is not None:
            bands.append(line.ranges)
    return entries


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """A DRAFT version with the entries of the rows; the declarations were admitted by the cross
    rule at validation (``ssp_declarations``). Every check of the plan runs before the first
    mutating command (Codex's retest of bb54f6c): a refused plan issues neither
    ``create_ssp_book_version`` nor ``upsert_ssp_entries``."""
    del context
    body = SspValuesIn.model_validate(dict(plan.body))
    entries = _merged_entries(body.lines)  # refuses before any command
    found = uow.session.execute(
        select(ssp_book.c.id).where(ssp_book.c.code == body.ssp_book_code)
    ).scalar_one_or_none()
    if found is None:
        raise Problem("validation-failed", BOOK_UNKNOWN.format(code=body.ssp_book_code))
    version_id = create_ssp_book_version(
        uow,
        UUID(str(found)),
        body=SspBookVersionIn(
            legacy_version_label=body.legacy_version_label,
            effective_from_date=body.effective_from_date,
            effective_to_date=body.effective_to_date,
            methodology_label=body.methodology_label,
            is_methodology_change=body.is_methodology_change,
        ),
    )
    requests = [
        SspEntryIn.model_validate(
            {
                **_declared(line.model_dump(exclude={"ranges"})),
                "ranges": [band.model_dump() for band in bands] or None,
            }
        )
        for line, bands in entries.values()
    ]
    ids = dict(
        zip(
            entries,
            upsert_ssp_entries(uow, version_id, body=SspEntriesIn(entries=requests)),
            strict=True,
        )
    )
    applied = Applied()
    applied.targets.append(("ssp_book_version", version_id))
    for row, line in zip(plan.rows, body.lines, strict=True):
        applied.row_targets[row.id] = [("ssp_entry", ids[_key(line)])]
    return applied


ENTRY_NUMBERS: Final = (
    "unit_list_price",
    "midpoint_discount_ratio",
    "range_ratio",
    "cost_basis",
    "margin_ratio",
    "observable_point",
)
BAND_NUMBERS: Final = (
    "band_from",
    "band_to",
    "point_value",
    "low_value",
    "mid_value",
    "high_value",
)


def _stored_exact(value: Any) -> str | None:
    """TY-02 NUMERIC(38,18), including PostgreSQL's half-away-from-zero rounding."""
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        rounded = Decimal(str(value)).quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP)
        return format(rounded.normalize(), "f") if rounded else "0"


def _band_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "band_dimension": values.get("band_dimension") or "NONE",
        **{name: _stored_exact(values.get(name)) for name in BAND_NUMBERS},
    }


def _entry_values(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **{name: values.get(name) for name in ENTRY_KEY},
        "value_basis": values.get("value_basis") or "AMOUNT",
        "quantity_unit": values.get("quantity_unit"),
        **{name: _stored_exact(values.get(name)) for name in ENTRY_NUMBERS},
    }


def _ordered(values: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(values, key=lambda value: json.dumps(value, sort_keys=True))


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """CTL-002: reconstruct SSP inputs from file rows and read stored entries/bands.

    These numeric fields are text columns in the flattened template. Their monetary
    and ratio evidence is retained explicitly; an empty amount_sums is not coverage.
    """
    del context
    expected_entries: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in plan.rows:
        value = SspEntryRowIn.model_validate(unflatten(row.normalized)["lines"]).model_dump(
            mode="json"
        )
        key = tuple(value[name] for name in ENTRY_KEY)
        entry = expected_entries.setdefault(key, {**_entry_values(value), "bands": []})
        if value.get("ranges") is not None:
            entry["bands"].append(_band_values(value["ranges"]))
        elif value["method"] == "legacy_range" and not entry["bands"]:
            with localcontext() as ctx:
                ctx.prec = 80
                mid = Decimal(value["unit_list_price"]) * (
                    1 - Decimal(value["midpoint_discount_ratio"])
                )
                ratio = Decimal(value["range_ratio"])
                entry["bands"].append(
                    _band_values(
                        {
                            "low_value": mid * (1 - ratio),
                            "mid_value": mid,
                            "high_value": mid * (1 + ratio),
                        }
                    )
                )
    for entry in expected_entries.values():
        entry["bands"] = _ordered(entry["bands"])
    expected = {
        "books": [str(plan.rows[0].normalized["ssp_book_code"])],
        "entries": _ordered(list(expected_entries.values())),
    }
    ids = [key for kind, key in applied.targets if kind == "ssp_book_version"]
    books = list(
        session.scalars(
            select(ssp_book.c.code)
            .join(
                ssp_book_version,
                and_(
                    ssp_book_version.c.tenant_id == ssp_book.c.tenant_id,
                    ssp_book_version.c.ssp_book_id == ssp_book.c.id,
                ),
            )
            .where(ssp_book_version.c.id.in_(ids))
        )
    )
    entries = list(
        session.execute(
            select(ssp_entry, product.c.code.label("product_code"))
            .join(
                product,
                and_(
                    product.c.tenant_id == ssp_entry.c.tenant_id,
                    product.c.id == ssp_entry.c.product_id,
                ),
            )
            .where(ssp_entry.c.ssp_book_version_id.in_(ids))
        ).mappings()
    )
    bands = list(
        session.execute(
            select(ssp_range).where(
                ssp_range.c.ssp_entry_id.in_([entry["id"] for entry in entries])
            )
        ).mappings()
    )
    by_entry: dict[UUID, list[Mapping[str, Any]]] = {}
    for band in bands:
        by_entry.setdefault(band["ssp_entry_id"], []).append(_band_values(dict(band)))
    actual = {
        "books": sorted(str(code) for code in books),
        "entries": _ordered(
            [
                {
                    **_entry_values(dict(entry)),
                    "bands": _ordered(by_entry.get(entry["id"], [])),
                }
                for entry in entries
            ]
        ),
    }
    return expected, actual


CROSS_RULE: Final = ssp_declarations.cross_findings

TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.SSP_ROW,
    target_type="ssp_book_version",
    key_column="ssp_book_code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    repeats=REPEATS,
    reconcile_amounts=reconcile_amounts,
)
