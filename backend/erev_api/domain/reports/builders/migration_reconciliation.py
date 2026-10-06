"""RPT-41 ``migration_reconciliation`` Migration reconciliation, the pure part (SCREENS_B §5.6.7
RPT-41, §0.5; 04 T-MIG-03, T-RPT-01 ``migration_reconciliation``; PRD BR-MIG-02, WLD-X-27,
WLD-X-28; BUILD_SPEC LMG-3; REQ-MIG-003).

``report_data`` renders T-MIG-03 lines as the report: one row per line with ``row_key``
``line:<contract external id>:<obligation key or contract>:<measure>``, the RPT-41 columns
(legacy and eRev values as exact decimal text with trailing zeros trimmed — ``exact_text`` renders
the exact finite decimal, never a rounded one; Codex review of ed5173f, finding R3 — the signed
difference, the tolerance ``0.0001``, "Yes" / "No" within tolerance, the deviation reference,
the exception item), the control totals ``line_count``, ``differences_above_tolerance``,
``explained`` and ``unexplained``, and the tie-out ``TO_MIGRATION_UNEXPLAINED_ZERO`` (PASS when
nothing is unexplained). With ``only_differences`` the rows outside tolerance remain. Rows are
ordered by contract, obligation ("Contract level" first) and measure, so a rerun reproduces the
output. ``lines_from_rows`` turns stored T-MIG-03 rows into lines. The framework builder
``build(uow, params)`` (registered in ``framework.BUILDERS`` under ``migration_reconciliation``;
SCREENS_B RPT-41 "Reader and registration") reads only migration tables — no engine call: the
tenant's T-MIG-01 row of ``migration_id`` first (absent or invisible → 422 ``validation-failed``
on ``parameters.migration_id``, "Choose a migration."), then the batch's T-MIG-03 rows through
``rows_reader`` (``repository.reconciliation_rows``) and the exception numbers of the linked
``exception_item`` rows; the KPI totals ``contracts`` and ``legacy_obligation_rows`` come from the
batch's T-MIG-01 ``profile`` (0 while unprofiled). Values render as stored: exact, trace-sourced
(D-98 89), never posted cents. ``build_with(reader, uow, params, batch_reader=…,
exception_reader=…)`` is the seam tests use with supplied rows.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from erev_api.domain.migration import reconciliation, repository
from erev_api.domain.migration.reconciliation import Line, LineKey
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

__all__ = [
    "BatchReader",
    "CHOOSE_A_MIGRATION",
    "CODE",
    "COLUMNS",
    "ExceptionReader",
    "KPI_TOTALS",
    "MEASURE_LABELS",
    "RowsReader",
    "build",
    "build_with",
    "exact_text",
    "lines_from_rows",
    "report_data",
    "rows_reader",
]

CODE: Final = "migration_reconciliation"
MEASURE_LABELS: Final[Mapping[str, str]] = {
    "POB_COUNT": "Obligation count",
    "TRANSACTION_PRICE": "Transaction price",
    "ORIGINAL_ALLOCATION": "Original allocation",  # 04 rev 1.35; SCREENS_B rev 1.8
    "ALLOCATION": "Allocation",
    "REVENUE_CUM": "Revenue to date",
    "BILLED_CUM": "Billed to date",
    "NET_POSITION": "Billed less recognized",
    "RECLASS": "Reclassification to contract asset",
    "REMAINING_QTY": "Remaining quantity",
}
CONTRACT_LEVEL: Final = "Contract level"
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("measure", "Measure", "text"),
    Column("source_value", "Legacy value", "decimal"),
    Column("erev_value", "eRev value", "decimal"),
    Column("difference", "Difference", "decimal"),
    Column("tolerance", "Tolerance", "decimal"),
    Column("is_within_tolerance", "Within tolerance", "text"),
    Column("deviation_ref", "Deviation", "code"),
    Column("exception_item_id", "Exception", "code"),
)
_MEASURE_ORDER: Final[Mapping[str, int]] = {
    measure: index for index, measure in enumerate(reconciliation.MEASURES)
}
_RULE: Final = "RPT-41"
CHOOSE_A_MIGRATION: Final = "Choose a migration."  # SCREENS_B §5.6.7 RPT-41 validation copy
# SCREENS_B RPT-41 KPI strip (rev 1.13): the two totals read from the T-MIG-01 ``profile``.
KPI_TOTALS: Final[Mapping[str, str]] = {
    "contracts": "contracts",
    "legacy_obligation_rows": "legacy_pob_rows",
}


def exact_text(value: Fraction) -> str:
    """An exact amount as decimal text with trailing zeros trimmed (RPT-41 "exact decimal text"):
    ``reconciliation.exact_decimal_text`` — the finite decimal expansion by integer arithmetic,
    never rounded; ``ValueError`` for a non-terminating value (T-MIG-03 values are ``erev.exact``
    decimals, whose differences terminate)."""
    return reconciliation.exact_decimal_text(value)


def _row(line: Line, exception_items: Mapping[LineKey, str]) -> dict[str, Any]:
    return {
        "row_key": line.row_key,
        "contract_external_id": line.contract_external_id,
        "obligation_key": CONTRACT_LEVEL if line.obligation_key is None else line.obligation_key,
        "measure": MEASURE_LABELS.get(line.measure, line.measure),
        "source_value": exact_text(line.source_value),
        "erev_value": exact_text(line.erev_value),
        "difference": exact_text(line.difference),
        "tolerance": exact_text(line.tolerance),
        "is_within_tolerance": "Yes" if line.is_within_tolerance else "No",
        "deviation_ref": line.deviation_ref,
        "exception_item_id": (
            (line.exception_ref or exception_items.get(line.key)) if line.needs_exception else None
        ),
    }


def report_data(
    lines: Sequence[Line],
    *,
    only_differences: bool = False,
    exception_items: Mapping[LineKey, str] | None = None,
    kpis: Mapping[str, int] | None = None,
) -> ReportData:
    """The RPT-41 report of T-MIG-03 lines; an unexplained line shows its own ``exception_ref``
    (the exception number, attached by ``lines_from_rows`` from the row's ``exception_item_id`` —
    row identity, never the display key; Codex RPT41-ID-1) or, on the pure path, the number
    ``exception_items`` maps to its STRUCTURAL ``Line.key``; ``kpis`` are the two T-MIG-01 profile
    totals (``contracts``, ``legacy_obligation_rows``; 0 when not supplied), which lead the control
    totals as SCREENS_B RPT-41 lists them.
    """
    ordered = sorted(
        lines,
        key=lambda line: (
            line.contract_external_id,
            line.obligation_key is not None,
            line.obligation_key or "",
            _MEASURE_ORDER.get(line.measure, len(_MEASURE_ORDER)),
        ),
    )
    totals = reconciliation.control_totals(ordered)
    shown = [line for line in ordered if not only_differences or not line.is_within_tolerance]
    items = {} if exception_items is None else exception_items
    leading = {key: int((kpis or {}).get(key, 0)) for key in KPI_TOTALS}
    return ReportData(
        columns=COLUMNS,
        rows=tuple(_row(line, items) for line in shown),
        control_totals={**leading, **totals.as_json()},
        tie_out_results=(reconciliation.tie_out_result(totals),),
    )


def _exact(value: object) -> Fraction:
    try:
        return Fraction(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"not an exact value: {value!r}") from error


def lines_from_rows(
    rows: Iterable[Mapping[str, Any]], exception_numbers: Mapping[UUID, str] | None = None
) -> tuple[Line, ...]:
    """T-MIG-03 rows (04 §17.4 columns, values as stored decimals or their text) → ``Line``
    values; ``needs_exception`` follows the stored ``is_within_tolerance`` and ``deviation_ref``;
    each row's ``exception_item_id`` becomes the line's ``exception_ref`` — its exception number
    when ``exception_numbers`` resolves it, else the id — by row identity (Codex RPT41-ID-1).
    """
    numbers = {} if exception_numbers is None else exception_numbers
    found: list[Line] = []
    for row in rows:
        within = bool(row["is_within_tolerance"])
        ref = row.get("deviation_ref")
        item = row.get("exception_item_id")
        exception_ref = None
        if item is not None:
            item_id = UUID(str(item))
            exception_ref = numbers.get(item_id, str(item_id))
        found.append(
            Line(
                contract_external_id=str(row["contract_external_id"]),
                obligation_key=None
                if row.get("obligation_key") is None
                else str(row["obligation_key"]),
                measure=str(row["measure"]),
                source_value=_exact(row["source_value"]),
                erev_value=_exact(row["erev_value"]),
                difference=_exact(row["difference"]),
                tolerance=_exact(row.get("tolerance", reconciliation.TOLERANCE)),
                is_within_tolerance=within,
                deviation_ref=None if ref is None else str(ref),
                needs_exception=not within and ref is None,
                exception_ref=exception_ref,
            )
        )
    return tuple(found)


type RowsReader = Callable[[UnitOfWork, UUID], Iterable[Mapping[str, Any]]]
type BatchReader = Callable[[UnitOfWork, UUID], Mapping[str, Any]]
type ExceptionReader = Callable[[UnitOfWork, Iterable[UUID]], Mapping[UUID, str]]

# The T-MIG-03 read of the batch's lines (SCREENS_B RPT-41 "Reader and registration").
rows_reader: RowsReader = repository.reconciliation_rows


def _choose_a_migration() -> Problem:
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[
            ProblemError(field="parameters.migration_id", rule_id=_RULE, message=CHOOSE_A_MIGRATION)
        ],
    )


def _migration_id(params: ReportParams) -> UUID:
    raw = params.parameters.get("migration_id")
    if raw is None or raw == "":
        raise _choose_a_migration()
    try:
        return UUID(str(raw))
    except ValueError:
        raise _choose_a_migration() from None


def _batch(reader: BatchReader, uow: UnitOfWork, migration_id: UUID) -> Mapping[str, Any]:
    """The tenant's T-MIG-01 row; a row that is absent or not visible is the same refusal."""
    try:
        return reader(uow, migration_id)
    except Problem as problem:
        if problem.slug == "not-found":
            raise _choose_a_migration() from problem
        raise


def _kpis(batch: Mapping[str, Any]) -> dict[str, int]:
    profile = batch.get("profile") or {}
    return {total: int(profile.get(member) or 0) for total, member in KPI_TOTALS.items()}


def build_with(
    reader: RowsReader,
    uow: UnitOfWork,
    params: ReportParams,
    *,
    batch_reader: BatchReader = repository.get_batch,
    exception_reader: ExceptionReader = repository.exception_numbers,
) -> ReportData:
    """RPT-41 over the T-MIG-01 row, the T-MIG-03 rows ``reader`` returns and the exception numbers
    ``exception_reader`` resolves for the run's ``migration_id`` (the test seam takes fakes)."""
    migration_id = _migration_id(params)
    batch = _batch(batch_reader, uow, migration_id)
    only_differences = bool(params.parameters.get("only_differences", False))
    rows = tuple(reader(uow, migration_id))
    linked = {UUID(str(row["exception_item_id"])) for row in rows if row.get("exception_item_id")}
    numbers = exception_reader(uow, sorted(linked)) if linked else {}
    lines = lines_from_rows(rows, numbers)
    return report_data(lines, only_differences=only_differences, kpis=_kpis(batch))


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    """The framework builder (``Builder = Callable[[UnitOfWork, ReportParams], ReportData]``),
    registered in ``framework.BUILDERS`` under ``migration_reconciliation``: parameters
    ``migration_id`` (required; "Choose a migration.") and ``only_differences``; reads through
    ``rows_reader``, ``repository.get_batch`` and ``repository.exception_numbers``."""
    return build_with(rows_reader, uow, params)
