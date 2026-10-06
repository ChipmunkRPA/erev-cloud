"""The 71 legacy ``Contract_Live`` columns and their export rules (04 §17.1, §17.2 LM-CL-01 to
LM-CL-71; D-33; SCREENS_B §5.6.2 RPT-10, RPT-12; legacy 01 §3.6; BUILD_SPEC RPS-5).

This module holds the legacy column names, which the legacy exports keep verbatim (D-33). It is on
the allow-list of DG-MK-vocab-check (dev-guide §4.3), so the builders take the names from here.

``legacy_row`` writes one obligation version as the 71 columns, in legacy order, keyed by the legacy
names:

- dates as ``YYYY-MM-DD 00:00:00``; ``Processing Time Log`` is ``contract_computation.created_at``
  in UTC as ``YYYY-MM-DD HH:MM:SS.ffffff`` (rule 3);
- amounts and quantities at full stored precision without trailing zeros, account codes and SKU
  numbers as text (rule 4);
- the "Previous …" columns from the previous obligation version, or for a first version the setup
  values of legacy 01 §3.6: no previous period, the original quantity, extended SSP, allocation,
  stated price, unit SSP and unit revenue rate, and 0 for every cumulative, position and reclass
  column (rule 2);
- the position columns as stored, billing − revenue, which is the D-12 sign without inversion
  (rule 6);
- D-98 candidate 89 (04 §17.1 rule 4 rev 1.66; SCREENS_B RPT-10 rev 1.21;
  DG-PAR-05): the six columns whose stored ``erev.money`` value is posted cents while legacy
  holds the unrounded value
  — ``Previous Remaining Allocation``, ``Current Remaining Allocation``, ``Current Rev Rec -
  Cumulative``, ``Current Contract Position - POB``, ``Current Contract Position - Contract Level``
  and ``Current Reclass to UAR`` — write the EXACT value the engine produced: ``exact(m)`` = the
  row's OWN version's trace node ``value + rounding_residue`` (the previous version's own node for
  the "Previous" column), as exact decimal text. The builder attaches those texts under
  ``EXACT_TEXT_KEY`` (``exact_sources.attach_exact_texts``); a row without them fails closed by
  name — never a silent posted fallback.
- 04 §17.1 rule 4a (rev 1.75; D-98 89 RULING 2 + AMENDMENT 1; D-98 candidate 149; dev-guide
  DG-KRN-EXP-08): ``Current Rev Rec`` (LM-CL-55) is the exact revenue ACTIVITY of the row's own
  trace — the OWN serialized value of the companion the posted ``revenue_amount`` node names in
  ``params["exact_node"]`` (never the posted node's ``value + rounding_residue``), attached under
  the same key by the same builder call; the literal ``UNAVAILABLE_TEXT`` where the producer
  names an adjusted endpoint (``exact_basis``) — a text cell in a decimal column; a legacy trace
  or a missing / redirected / invalid companion refuses the whole run by name. Never posted
  cents, never manufactured from rounded output.

[J] L7-1-Q-3: rule 5 (rows before a migration cutover from ``migrated_legacy_row.legacy_row``) is
not built. The rc has no migration batch and no table object for ``migrated_legacy_row``. A contract
without migrated rows exports from its obligation versions only.
[J] ``Deferred Revenue Account``, ``Unbilled A/R Account`` and ``Revenue Account`` write the raw
legacy column (``legacy_deferred_revenue_account`` and the others) when the import stored one, else
the ``account_overrides`` value of the role (LM-CL-11, LM-CL-12, LM-CL-22). ``Current Delivery`` and
``Current Billing`` write ``delivered_quantity`` and ``billed_amount`` as stored, because the
version already nets returns and credit memos with their signs (LM-CL-54, LM-CL-57).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Final

from erev_api.domain.reports.outputs import Column, ColumnKind

__all__ = [
    "BOOK",
    "COLUMNS",
    "CONTRACT_LIVE",
    "ACTIVITY_COLUMNS",
    "EXACT_COLUMNS",
    "EXACT_TEXT_COLUMNS",
    "EXACT_TEXT_KEY",
    "NAMES",
    "POSITION_CONTRACT_LEVEL",
    "UNAVAILABLE_TEXT",
    "LegacyColumn",
    "date_text",
    "decimal_text",
    "exact_text",
    "legacy_row",
    "time_log",
]

# 04 §17.1: the legacy exports read the ASC606 book.
BOOK: Final = "ASC606"
ZERO_TEXT: Final = "0"
# D-98 candidate 89 (04 §17.1 rule 4 rev 1.66): the ``obligation_version`` money columns
# the exports write as exact(m); the builder attaches ``{column: exact decimal text}`` under
# this row key.
EXACT_TEXT_KEY: Final = "exact_text"
EXACT_COLUMNS: Final[tuple[str, ...]] = (
    "remaining_allocation",
    "revenue_cum",
    "position_obligation",
    "position_contract_entity",
    "netting_reclass_amount",
)
# 04 §17.1 rule 4a (rev 1.75; D-98 89 RULING 2 + AMENDMENT 1; D-98 candidate 149): the posted
# money column the exports write as the exact ACTIVITY of the row's own trace — the companion
# the posted node names in ``params["exact_node"]`` (DG-KRN-EXP-08), or the literal below
ACTIVITY_COLUMNS: Final[tuple[str, ...]] = ("revenue_amount",)
EXACT_TEXT_COLUMNS: Final[tuple[str, ...]] = (*EXACT_COLUMNS, *ACTIVITY_COLUMNS)
# the UNAVAILABLE branch's cell: a text cell in a decimal column (SCREENS_B RPT-10 rev 1.24)
UNAVAILABLE_TEXT: Final = "unavailable"

type Row = Mapping[str, Any]
type Value = Callable[[Row, Row | None], str | None]


def decimal_text(value: Any) -> str | None:
    """A stored number at full precision without trailing zeros and without a negative zero."""
    if value is None:
        return None
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if number == 0:
        return ZERO_TEXT
    return format(number.normalize(), "f")


def date_text(value: date | None) -> str | None:
    """A legacy timestamp column of a date: ``YYYY-MM-DD 00:00:00``."""
    return None if value is None else f"{value.isoformat()} 00:00:00"


def time_log(value: datetime) -> str:
    """``Processing Time Log``: the instant in UTC as ``YYYY-MM-DD HH:MM:SS.ffffff``."""
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _literal(value: Any) -> str | None:
    return None if value is None else str(getattr(value, "value", value))


@dataclass(frozen=True, slots=True)
class LegacyColumn:
    """One ``Contract_Live`` column: its 04 §17.2 id, legacy name, output kind and value."""

    id: str
    name: str
    kind: ColumnKind
    value: Value


def _text(name: str) -> Value:
    return lambda row, _previous: _literal(row[name])


def _date(name: str) -> Value:
    return lambda row, _previous: date_text(row[name])


def _number(name: str) -> Value:
    return lambda row, _previous: decimal_text(row[name])


def _account(raw: str, role: str) -> Value:
    def value(row: Row, _previous: Row | None) -> str | None:
        found = row.get(raw)
        if found not in (None, ""):
            return str(found)
        overrides = row.get("account_overrides") or {}
        named = overrides.get(role) if isinstance(overrides, Mapping) else None
        return None if named is None else str(named)

    return value


def exact_text(row: Row, name: str) -> str:
    """The builder-attached exact decimal text of ``row``'s ``name`` (D-98 candidate 89; 04 §17.1
    rules 4 and 4a rev 1.75; for an activity column the companion's own value or the
    ``unavailable`` literal). A row without it fails closed by name — the posted cents are never
    written in its place."""
    values = row.get(EXACT_TEXT_KEY)
    if not isinstance(values, Mapping) or not isinstance(values.get(name), str):
        raise ValueError(
            f"obligation version {row.get('id')!s} carries no exact value for {name}: the export "
            "writes DG-PAR-05 exact(m), never the posted cents (D-98 candidate 89)"
        )
    return str(values[name])


def _exact(name: str) -> Value:
    return lambda row, _previous: exact_text(row, name)


def _previous_exact(name: str, setup: str) -> Value:
    """The previous version's exact ``name`` (its own trace node); for a first version the RAW
    exact ``setup`` column of this version (rule 2; already exact)."""

    def value(row: Row, previous: Row | None) -> str | None:
        if previous is not None:
            return exact_text(previous, name)
        return decimal_text(row[setup])

    return value


def _previous(name: str, setup: str | None = None) -> Value:
    """The previous version's ``name``; for a first version ``setup`` of this version, else 0."""

    def value(row: Row, previous: Row | None) -> str | None:
        if previous is not None:
            return decimal_text(previous[name])
        return ZERO_TEXT if setup is None else decimal_text(row[setup])

    return value


def remaining_ssp_after_deliveries(row: Row) -> str | None:
    """04 §17.1 rule 7 (D-98 candidate 90; ENGINE_SPEC CV-47 (c)): the legacy ``Current Remaining
    SSP`` = remaining quantity × unit SSP of the version, exact — legacy's remaining SSP after
    deliveries (legacy 01 §3.7) — a DERIVED export value; the stored ``remaining_ssp`` keeps its
    allocation semantics and is the fallback when the version has no unit SSP."""
    quantity, unit = row.get("remaining_quantity"), row.get("unit_ssp")
    if quantity is None or unit is None:
        return decimal_text(row["remaining_ssp"])
    with localcontext() as context:
        context.prec = 60  # two stored exact numbers multiply exactly well within 60 digits
        return decimal_text(_as_decimal(quantity) * _as_decimal(unit))


def _as_decimal(value: Any) -> Decimal:
    """A stored number (Decimal, int, str) or an engine ``Fraction`` as a Decimal."""
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _current_remaining_ssp(row: Row, _previous: Row | None) -> str | None:
    return remaining_ssp_after_deliveries(row)


def _previous_remaining_ssp(row: Row, previous: Row | None) -> str | None:
    """The previous version's derived remaining SSP; for a first version the setup value
    ``original_ssp_selected`` (§17.1 rule 2; legacy 01 §3.6)."""
    if previous is not None:
        return remaining_ssp_after_deliveries(previous)
    return decimal_text(row["original_ssp_selected"])


def _previous_period(row: Row, previous: Row | None) -> str | None:
    return None if previous is None else date_text(previous["effective_date"])


def _distinctness(row: Row, _previous: Row | None) -> str:
    # LM-CL-18: a series exports ``Nondistinct``.
    return "Distinct" if _literal(row["distinctness"]) == "distinct" else "Nondistinct"


def _time_log(row: Row, _previous: Row | None) -> str:
    return time_log(row["processed_at"])


def _record_id(row: Row, _previous: Row | None) -> str:
    return f"{time_log(row['processed_at'])} {row['legacy_record_key']}"


def _column(number: int, name: str, kind: ColumnKind, value: Value) -> LegacyColumn:
    return LegacyColumn(id=f"LM-CL-{number:02d}", name=name, kind=kind, value=value)


CONTRACT_LIVE: Final[tuple[LegacyColumn, ...]] = (
    _column(1, "Contract Unique Name", "text", _text("contract_external_id")),
    _column(2, "POB Unique ID", "text", _text("obligation_key")),
    _column(3, "SKU Name", "text", _text("product_code")),
    _column(4, "POB Start Date", "text", _date("start_date")),
    _column(5, "POB End Date", "text", _date("end_date")),
    _column(6, "ASC 606 Stratification", "text", _text("stratification")),
    _column(7, "Original POB Total Selling Price", "decimal", _number("original_stated_price")),
    _column(8, "Original POB Total Qty", "decimal", _number("original_quantity")),
    _column(9, "Selling Entity", "text", _text("entity_code")),
    _column(10, "SSP Version", "text", _text("ssp_version_label")),
    _column(
        11,
        "Deferred Revenue Account",
        "text",
        _account("legacy_deferred_revenue_account", "CONTRACT_LIABILITY"),
    ),
    _column(
        12, "Unbilled A/R Account", "text", _account("legacy_unbilled_ar_account", "CONTRACT_ASSET")
    ),
    _column(13, "Current Period", "text", _date("effective_date")),
    _column(14, "Memo 1", "text", _text("memo_1")),
    _column(15, "Memo 2", "text", _text("memo_2")),
    _column(16, "Memo 3", "text", _text("memo_3")),
    _column(17, "SKU Unique ID", "text", _text("sku_number")),
    _column(18, "Distinct or Nondistinct", "text", _distinctness),
    _column(19, "SKU Unit List Price", "decimal", _number("ssp_unit_list_price")),
    _column(20, "Midpoint Discount Percentage", "decimal", _number("ssp_midpoint_discount_ratio")),
    _column(21, "SSP Range Method (+-)", "decimal", _number("ssp_range_ratio")),
    _column(22, "Revenue Account", "text", _account("legacy_revenue_account", "REVENUE")),
    _column(23, "Original SSP - Midpoint", "decimal", _number("original_ssp_mid")),
    _column(24, "Original SSP - Higher", "decimal", _number("original_ssp_high")),
    _column(25, "Original SSP - Lower", "decimal", _number("original_ssp_low")),
    _column(26, "Original Extended SSP", "decimal", _number("original_ssp_selected")),
    _column(
        27, "Original Total Contract Price", "decimal", _number("original_total_contract_price")
    ),
    _column(28, "Original Total Contract SSP", "decimal", _number("original_total_contract_ssp")),
    # LM-CL-29: the export writes the exact allocation (D-17).
    _column(29, "Original Allocation", "decimal", _number("original_allocated_exact")),
    _column(30, "Original Unit SSP", "decimal", _number("original_unit_ssp")),
    _column(31, "Original Unit Rev Rec", "decimal", _number("original_unit_revenue_rate")),
    _column(32, "Previous Period", "text", _previous_period),
    _column(
        33,
        "Previous Remaining Qty",
        "decimal",
        _previous("remaining_quantity", "original_quantity"),
    ),
    _column(34, "Previous Remaining SSP", "decimal", _previous_remaining_ssp),  # §17.1 rule 7
    _column(  # D-98 89: the previous version's own exact node; first version RAW
        35,
        "Previous Remaining Allocation",
        "decimal",
        _previous_exact("remaining_allocation", "original_allocated_exact"),
    ),
    _column(
        36,
        "Previous Remaining Billing",
        "decimal",
        _previous("remaining_billing", "original_stated_price"),
    ),
    _column(37, "Previous Unit SSP", "decimal", _previous("unit_ssp", "original_unit_ssp")),
    _column(
        38,
        "Previous Remaining Unit Rev Rec",
        "decimal",
        _previous("remaining_unit_revenue_rate", "original_unit_revenue_rate"),
    ),
    _column(39, "Previous Delivery - Cumulative", "decimal", _previous("delivered_quantity_cum")),
    _column(40, "Previous Rev Rec - Cumulative", "decimal", _previous("revenue_cum")),
    _column(
        41,
        "Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative",
        "decimal",
        _previous("pre_standard_revenue_cum"),
    ),
    _column(42, "Previous Billing - Cumulative", "decimal", _previous("billed_cum")),
    _column(
        43,
        "Previous Cumulative Catchup - Cumulative - Disclosure Only",
        "decimal",
        _previous("catch_up_cum"),
    ),
    _column(44, "Previous SSP Delivered - Cumulative", "decimal", _previous("ssp_delivered_cum")),
    _column(45, "Previous Contract Position - POB", "decimal", _previous("position_obligation")),
    _column(
        46,
        "Previous Contract Position - Contract Level",
        "decimal",
        _previous("position_contract_entity"),
    ),
    _column(47, "Previous Reclass to UAR", "decimal", _previous("netting_reclass_amount")),
    _column(48, "Current Remaining Qty", "decimal", _number("remaining_quantity")),
    _column(49, "Current Remaining SSP", "decimal", _current_remaining_ssp),  # §17.1 rule 7
    _column(50, "Current Remaining Allocation", "decimal", _exact("remaining_allocation")),
    _column(51, "Current Remaining Billing", "decimal", _number("remaining_billing")),
    _column(52, "Current Unit SSP", "decimal", _number("unit_ssp")),
    _column(
        53, "Current Remaining Unit Rev Rec", "decimal", _number("remaining_unit_revenue_rate")
    ),
    _column(54, "Current Delivery", "decimal", _number("delivered_quantity")),
    # 04 §17.1 rule 4a (rev 1.75): the exact activity — the posted node's own companion value,
    # or the `unavailable` literal; never the posted cents (D-98 89 RULING 2, candidate 149)
    _column(55, "Current Rev Rec", "decimal", _exact("revenue_amount")),
    _column(
        56,
        "Current Pre-ASC606 Revenue (Net Design Only)",
        "decimal",
        _number("pre_standard_revenue_amount"),
    ),
    _column(57, "Current Billing", "decimal", _number("billed_amount")),
    _column(
        58, "Current Cumulative Catchup - Disclosure Only", "decimal", _number("catch_up_amount")
    ),
    _column(59, "Current SSP Delivered", "decimal", _number("ssp_delivered")),
    _column(60, "Current Delivery - Cumulative", "decimal", _number("delivered_quantity_cum")),
    _column(61, "Current Rev Rec - Cumulative", "decimal", _exact("revenue_cum")),
    _column(
        62,
        "Current Pre-ASC606 Revenue (Net Design Only) - Cumulative",
        "decimal",
        _number("pre_standard_revenue_cum"),
    ),
    _column(63, "Current Billing - Cumulative", "decimal", _number("billed_cum")),
    _column(
        64,
        "Current Cumulative Catchup - Cumulative - Disclosure Only",
        "decimal",
        _number("catch_up_cum"),
    ),
    _column(65, "Current SSP Delivered - Cumulative", "decimal", _number("ssp_delivered_cum")),
    _column(66, "Current Contract Position - POB", "decimal", _exact("position_obligation")),
    _column(
        67,
        "Current Contract Position - Contract Level",
        "decimal",
        _exact("position_contract_entity"),
    ),
    _column(68, "Current Reclass to UAR", "decimal", _exact("netting_reclass_amount")),
    _column(69, "Processing Time Log", "text", _time_log),
    _column(70, "Record Unique ID without time", "text", _text("legacy_record_key")),
    _column(71, "Record Unique ID", "text", _record_id),
)
if len(CONTRACT_LIVE) != 71 or len({column.name for column in CONTRACT_LIVE}) != 71:
    raise ValueError("04 §17.2 Contract_Live has exactly 71 distinct columns")

NAMES: Final[tuple[str, ...]] = tuple(column.name for column in CONTRACT_LIVE)
COLUMNS: Final[tuple[Column, ...]] = tuple(
    Column(column.name, column.name, column.kind) for column in CONTRACT_LIVE
)
POSITION_CONTRACT_LEVEL: Final = CONTRACT_LIVE[66].name


def legacy_row(row: Row, previous: Row | None) -> dict[str, str | None]:
    """The 71 columns of one obligation version (module docstring). ``row`` holds the version's
    ``obligation_version`` columns with ``contract_external_id``, ``entity_code`` (the contracting
    entity) and ``processed_at``; ``previous`` is the previous obligation version, else None."""
    return {column.name: column.value(row, previous) for column in CONTRACT_LIVE}
