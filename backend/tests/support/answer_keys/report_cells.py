"""Report-block cells of platform answer keys: resolution and comparison (BUILD_SPEC PRP-3 prep).

A checkpoint ``reports`` block (dev-guide §9.5.6) names cells by ``row_key`` and ``column_key`` in
the OQ-AK-11 vocabulary; the "Report cell keys" table of §9.5.6 maps them to the rows and fields of
a report run (``GET /report-runs/{id}/data`` items: ``row_key`` plus the definition's fields).
This module is the pure half of that comparison: ``resolve`` turns one cell into a ``CellRef`` (the
run rows it reads, the field, whether it sums), ``compare_block`` evaluates a block against the rows
a run exposes and returns the mismatches under DG-AK-51 to DG-AK-53. It reads no database and
executes no run; the platform runner (``run_platform``, PRP-1, not built) will feed it the rows of
the report runs its plan names. ``PLATFORM_RUNNER_MISSING`` stays in force (XR-12).

Row shapes (the builders on main eb5546a):

- ``rpo``: section 1 rows ``contract:<external id>`` (dimension ``CONTRACT``) and ``TOTAL:<ISO>``;
  the bands are flat fields named by the band key (``within_12_months``, ``months_13_to_24``,
  ``after_24_months``) beside ``total``, ``current`` and ``noncurrent``. The dev-guide table writes
  "field ``bands.<k>``"; the run data rows carry the flat keys, so the comparison reads those and
  the difference is recorded for the docs lane (F-RPS-ENG-E1-prep.md Q-1).
- ``contract_balance_rollforward``: section 1 rows are the line codes (``OPENING``, ``BILLINGS``,
  ``REVENUE_FROM_OPENING``, ``REVENUE_FROM_PERIOD_BILLINGS``, ``FX_REMEASUREMENT``, ``CLOSING``),
  ``<line>:<ISO>`` when the run mixes currencies; fields ``contract_liability``, ``contract_asset``,
  ``unbilled_receivable``. Activity is signed, so a revenue line is negative.
- ``revenue_from_opening_liability``: section 2 rows ``contract:<external id>:<entity code>`` with
  fields ``opening_contract_liability``, ``revenue_recognized``, ``revenue_from_opening``; an entity
  row key sums the entity's contract rows.
- ``disaggregation``: rows ``timing:<pattern>`` (timing-only entities) or ``<label>:<pattern>``
  (``<label>`` alone without timing), ``:<ISO>`` appended when currencies mix; field ``total``.
- any other code: the ``row_key`` and field as written (``balance_aging``: ``contract:<id>:<role>``
  with ``bucket_0_30`` … ``total``; CHK-117).

Money cells are ``{"amount": "<decimal>", "currency": "<ISO>"}`` mappings (``tie_outs.money``) or
plain decimal strings; the expected string carries exactly the currency's minor-unit places
(DG-AK-51) and the comparison is exact.

Currency identity (Codex review of 642363e, F-RPS-E1-R1): every comparison runs for ONE selected
currency (the ``currency`` argument, else the key's single transaction currency; a multi-currency
key needs the argument). A row belongs to that currency through its row-key suffix ``:<ISO>``, its
``currency`` field and its money mapping's ``currency``; rows of another currency never enter a
cell, rows whose three signals disagree are diagnosed as ``<inconsistent currency>``, and a plain
decimal string (no currency of its own) compares only under an explicit ``currency`` argument, the
trusted context, else ``<no currency context>``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from erev_engine.currencies import ISO_4217
from support.answer_keys.loader import report_columns, report_row_key
from support.answer_keys.models import AnswerKey, ReportBlock, ReportCell

__all__ = [
    "ABSENT",
    "INCONSISTENT_CURRENCY",
    "NO_CURRENCY_CONTEXT",
    "ROLLFORWARD_LINES",
    "CellMismatch",
    "CellRef",
    "compare_block",
    "resolve",
    "row_matches",
]

ABSENT: Final = "<absent>"
INCONSISTENT_CURRENCY: Final = "<inconsistent currency>"  # R1: row / money / suffix disagree
NO_CURRENCY_CONTEXT: Final = "<no currency context>"  # R1: plain string without a trusted currency
TOTAL_PREFIX: Final = "TOTAL:"
# dev-guide §9.5.6: rollforward column key -> (section 1 line code, field).
ROLLFORWARD_LINES: Final[Mapping[str, str]] = {
    "opening_contract_liability": "OPENING",
    "billings": "BILLINGS",
    "revenue_from_opening_liability": "REVENUE_FROM_OPENING",
    "revenue_from_period_billings": "REVENUE_FROM_PERIOD_BILLINGS",
    "fx": "FX_REMEASUREMENT",
    "closing_contract_liability": "CLOSING",
}
OPENING_LIABILITY_FIELDS: Final[Mapping[str, str]] = {
    "opening_contract_liability": "opening_contract_liability",
    "revenue_recognized": "revenue_recognized",
    "revenue_from_opening_liability": "revenue_from_opening",
}
_ROLLFORWARD: Final = "contract_balance_rollforward"
_OPENING_LIABILITY: Final = "revenue_from_opening_liability"
_DISAGGREGATION: Final = "disaggregation"
_RPO: Final = "rpo"


@dataclass(frozen=True, slots=True)
class CellRef:
    """Where one key cell reads in a run: the rows (by row key predicate), the field, the mode."""

    report_code: str
    row_key: str  # the key's row key, normalised (DG-AK-35)
    column_key: str
    field: str  # the run field read
    mode: str  # "row" (one row) | "sum" (every matching row summed)
    candidates: tuple[str, ...] = ()  # exact run row keys accepted in "row" mode
    suffix: str | None = None  # "sum" mode over disaggregation rows: the ":<pattern>" suffix
    prefix: str | None = None  # "sum" mode: the "<label>:" (dimension value) or "contract:" prefix


@dataclass(frozen=True, slots=True)
class CellMismatch:
    """One cell that differs (DG-AK-55 fields; the runner maps it to its ``Mismatch``)."""

    report_code: str
    row_key: str
    column_key: str
    expected: str
    actual: str


def _currencies(key: AnswerKey) -> tuple[str, ...]:
    return tuple(sorted({contract.transaction_currency for contract in key.contracts}))


def _entity_codes(key: AnswerKey) -> frozenset[str]:
    return frozenset(entity.code for entity in key.world.entities)


def _selected_currency(key: AnswerKey, currency: str | None) -> str:
    """The one currency a comparison runs for (R1); a multi-currency key needs it explicitly."""
    if currency is not None:
        return currency
    currencies = _currencies(key)
    if len(currencies) == 1:
        return currencies[0]
    raise ValueError("compare_block needs an explicit currency for a multi-currency key (DG-AK-35)")


def _split_currency(row_key: str) -> tuple[str, str | None]:
    """(bare row key, ISO code) when the row key ends with ``:<ISO>`` of the currency table."""
    bare, _, tail = row_key.rpartition(":")
    if bare and tail in ISO_4217:
        return bare, tail
    return row_key, None


def resolve(
    key: AnswerKey, block: ReportBlock, cell: ReportCell, currency: str | None = None
) -> CellRef:
    """The ``CellRef`` of ``cell`` under the §9.5.6 "Report cell keys" table.

    Raises ``ValueError`` for a column key outside the report's vocabulary (``report_columns``), a
    row key DG-AK-35 cannot normalise, or a multi-currency key without ``currency``.
    """
    code = block.report_code
    columns = report_columns(key, block)
    if columns is not None and cell.column_key not in columns:
        raise ValueError(
            f"report {code}: column {cell.column_key!r} is not one of {', '.join(sorted(columns))}"
        )
    row_key = report_row_key(key, block, cell.row_key)
    selected = _selected_currency(key, currency)
    if code == _RPO:
        return CellRef(code, row_key, cell.column_key, cell.column_key, "row", (row_key,))
    if code == _ROLLFORWARD:
        line = ROLLFORWARD_LINES[cell.column_key]
        candidates = (line, f"{line}:{selected}")
        return CellRef(code, row_key, cell.column_key, "contract_liability", "row", candidates)
    if code == _OPENING_LIABILITY:
        field = OPENING_LIABILITY_FIELDS[cell.column_key]
        if row_key.startswith("contract:"):
            external_id = row_key[len("contract:") :]
            return CellRef(
                code, row_key, cell.column_key, field, "sum", prefix=f"contract:{external_id}:"
            )
        if row_key.startswith("entity:"):
            return CellRef(
                code, row_key, cell.column_key, field, "sum", suffix=f":{row_key[len('entity:') :]}"
            )
        raise ValueError(
            f"report {code}: row key {cell.row_key!r} is neither a contract nor an entity"
        )
    if code == _DISAGGREGATION:
        dimension, _, value = row_key.partition(":")
        if dimension == "timing":
            return CellRef(code, row_key, cell.column_key, "total", "sum", suffix=f":{value}")
        return CellRef(code, row_key, cell.column_key, "total", "sum", prefix=f"{value}:")
    return CellRef(code, row_key, cell.column_key, cell.column_key, "row", (row_key,))


def row_matches(ref: CellRef, row_key: str, currency: str) -> bool:
    """Whether a run row with ``row_key`` contributes to ``ref`` for the selected ``currency``: a
    row key suffixed with another ISO code never does (R1)."""
    bare, suffix = _split_currency(row_key)
    if suffix is not None and suffix != currency:
        return False
    if ref.mode == "row":
        return row_key in ref.candidates or bare in ref.candidates
    if ref.report_code == _OPENING_LIABILITY:
        if ref.prefix is not None:
            return bare.startswith(ref.prefix)
        return bare.startswith("contract:") and ref.suffix is not None and bare.endswith(ref.suffix)
    if ref.report_code == _DISAGGREGATION:
        if bare.startswith(TOTAL_PREFIX) or bare == TOTAL_PREFIX[:-1]:
            return False
        if ref.suffix is not None:
            return bare.endswith(ref.suffix)
        return ref.prefix is not None and (bare.startswith(ref.prefix) or bare == ref.prefix[:-1])
    return False


def _row_amount(
    row: Mapping[str, Any], field: str, currency: str, trusted: bool
) -> Decimal | str | None:
    """The row's amount in the selected currency; None for a row of another currency (excluded);
    ``INCONSISTENT_CURRENCY`` when suffix, row field and money mapping disagree;
    ``NO_CURRENCY_CONTEXT`` for a plain string without a trusted currency; ``ABSENT`` when the
    field is missing or unreadable."""
    _, suffix = _split_currency(str(row.get("row_key", "")))
    signals: set[str] = set()
    if suffix is not None:
        signals.add(suffix)
    row_currency = row.get("currency")
    if isinstance(row_currency, str) and row_currency.strip():
        signals.add(row_currency.strip())
    value = row.get(field)
    if isinstance(value, Mapping):
        money_currency = value.get("currency")
        if isinstance(money_currency, str) and money_currency.strip():
            signals.add(money_currency.strip())
        raw = value.get("amount")
    else:
        raw = value
    if len(signals) > 1:
        return INCONSISTENT_CURRENCY
    if signals and next(iter(signals)) != currency:
        return None
    if raw is None or isinstance(raw, bool):
        return ABSENT
    if not isinstance(value, Mapping) and not signals and not trusted:
        return NO_CURRENCY_CONTEXT
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return ABSENT


def _places(currency: str) -> int:
    spec = ISO_4217.get(currency)
    return 2 if spec is None else spec.minor_unit


def _row_of_zeros(block: ReportBlock, row_key: str) -> bool:
    """Whether every expected measure of the block's row ``row_key`` is exactly zero."""
    for cell in block.cells:
        if cell.row_key != row_key:
            continue
        try:
            if Decimal(cell.value) != 0:
                return False
        except InvalidOperation:
            return False
    return True


def compare_block(
    key: AnswerKey,
    block: ReportBlock,
    rows: Sequence[Mapping[str, Any]],
    *,
    currency: str | None = None,
) -> list[CellMismatch]:
    """Every cell of ``block`` against the run ``rows`` for one currency; an empty list when all
    match.

    A cell that matches no row of the selected currency is ``<absent>`` (DG-AK-55). Money compares
    exactly at the currency's minor-unit places (DG-AK-51); the expected string must already carry
    those places, otherwise the mismatch names the authoring defect. ``currency`` defaults to the
    key's single transaction currency and is the trusted context plain-string cells need (R1).

    A row of zeros the report does not state (dev-guide §9.5.6 "Report cell keys", rev 1.219): a
    row every expected measure of which is exactly zero compares clean when no row of the run
    matches it — a report states the rows it has figures for, not a grid of zeros. A row with any
    other expected measure that the report lacks is a mismatch in every cell, the zero ones too.
    The rule is of report blocks alone: a subledger line, a balance and a contract figure are
    compared as stated.
    """
    code = _selected_currency(key, currency)
    trusted = currency is not None
    places = _places(code)
    found: list[CellMismatch] = []
    for cell in block.cells:
        ref = resolve(key, block, cell, code)
        expected_text = cell.value

        def miss(actual: str, ref: CellRef = ref, cell: ReportCell = cell) -> CellMismatch:
            return CellMismatch(ref.report_code, cell.row_key, cell.column_key, cell.value, actual)

        matching = [row for row in rows if row_matches(ref, str(row.get("row_key", "")), code)]
        if ref.mode == "row" and len(matching) > 1:
            found.append(miss(f"{len(matching)} rows match"))
            continue
        values: list[Decimal] = []
        problem: str | None = None
        for row in matching:
            outcome = _row_amount(row, ref.field, code, trusted)
            if outcome is None:
                continue  # a row of another currency
            if isinstance(outcome, str):
                problem = outcome
                break
            values.append(outcome)
        if problem is not None:
            found.append(miss(problem))
            continue
        if not values:
            if not matching and _row_of_zeros(block, cell.row_key):
                continue
            found.append(miss(ABSENT))
            continue
        actual = sum(values, Decimal(0))
        try:
            expected = Decimal(expected_text)
        except InvalidOperation:
            found.append(miss(f"{actual:f}"))
            continue
        expected_places = -expected.as_tuple().exponent if expected.as_tuple().exponent < 0 else 0
        if expected_places != places or expected != actual:
            found.append(miss(f"{actual:.{places}f}" if expected == actual else f"{actual:f}"))
    return found
