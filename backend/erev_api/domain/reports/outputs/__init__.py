"""Report datasets and run stamps rendered by the output writers (BUILD_SPEC RPS-2; 04 T-RPT-02,
§16.9; SCREENS_B RV-02, RV-07, RPT-R-02, RPT-R-03; DESIGN_SYSTEM DS-FMT-25, DS-FMT-26).

A builder returns ``ReportData``: typed columns, rows that carry ``row_key`` and the column keys,
the control totals and the tie-out results. Row values are Python values of the column kind:
``text`` and ``code`` a str; ``codes`` a sequence of str; ``integer`` an int; ``decimal`` a decimal
string written as it is, without grouping, rounding or the formula guard (the full-precision amounts
of the legacy exports, 04 §17.1 rule 4; BUILD_SPEC RPS-5); ``money`` API-S-Money
``{"amount": <decimal string with the currency's minor unit>, "currency": <ISO 4217>}``; ``date`` a
date; ``timestamp`` an aware datetime; ``boolean`` a bool; ``actor`` API-S-Actor. None is empty.
``NOT_SHOWN`` is a value that exists and is held back from the reader: the API answers null for it
and CSV writes nothing, as for an empty cell; XLSX and PDF print "Not shown" in place of the
column's ``empty_text``.

``layout`` gives the output columns of CSV, XLSX and PDF: a money column whose values share one
currency carries the code in its header (``<header> (<ISO>)``); a money column of several currencies
is followed by a ``<header> currency`` column (RPT-R-03). ``RunStamp`` holds the RV-02 fields that
the XLSX header block and the PDF first page print (RV-07).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Literal

type ColumnKind = Literal[
    "text", "code", "codes", "integer", "decimal", "money", "date", "timestamp", "boolean", "actor"
]
type LayoutPart = Literal["value", "currency"]

COLUMN_KINDS: Final = (
    "text",
    "code",
    "codes",
    "integer",
    "decimal",
    "money",
    "date",
    "timestamp",
    "boolean",
    "actor",
)
ROW_KEY: Final = "row_key"
NOT_SHOWN_TEXT: Final = "Not shown"
NEGATIVE_STYLES: Final = ("PARENTHESES", "MINUS")
_MONTHS: Final = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class NotShown:
    """The type of ``NOT_SHOWN``: a cell whose value is held back from the reader."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_SHOWN"


# A cell whose value exists and is not shown to the workspace (04 T-PLT-02 rev 1.316; item
# IDENTITY-WITHHELD-BY-STATUS-1). A column has ONE ``empty_text``, and "Never" is untrue of a last
# sign-in that is withheld: the writers print ``NOT_SHOWN_TEXT`` for this value, and the API and
# CSV give what they give for an empty cell. One builder emits it — RPT-24, for the MFA state
# and the last sign-in of a membership that is INVITED or REMOVED
# (``tests/unit/reports/test_not_shown.py``).
NOT_SHOWN: Final = NotShown()


@dataclass(frozen=True, slots=True)
class Column:
    """One report column: the row field ``key``, its header copy and its kind (RPT-R-02).
    ``empty_text`` is what XLSX and PDF show for an empty value, for example "Never"."""

    key: str
    header: str
    kind: ColumnKind
    empty_text: str = ""


@dataclass(frozen=True, slots=True)
class ReportData:
    columns: tuple[Column, ...]
    rows: tuple[Mapping[str, Any], ...]
    control_totals: Mapping[str, Any]
    tie_out_results: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        keys = [column.key for column in self.columns]
        if len(set(keys)) != len(keys) or ROW_KEY in keys:
            raise ValueError("column keys are unique and never row_key")
        if any(column.kind not in COLUMN_KINDS for column in self.columns):
            raise ValueError("unknown column kind")
        if any(not isinstance(row.get(ROW_KEY), str) for row in self.rows):
            raise ValueError("every row carries a row_key")

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class RunStamp:
    """The RV-02 run stamp of one run, with the tenant negative style of DS-FMT-06."""

    report_code: str
    report_name: str
    report_version: int
    report_run_no: str
    parameters: Mapping[str, Any]
    entity_codes: tuple[str, ...]
    book: str | None
    as_of: str | None
    source: str
    engine_version: str
    build_sha: str
    run_by: str
    run_at: datetime
    output_sha256: str
    negative_number_style: str = "PARENTHESES"


@dataclass(frozen=True, slots=True)
class LayoutColumn:
    column: Column
    part: LayoutPart
    header: str


def layout(data: ReportData) -> tuple[LayoutColumn, ...]:
    """The output columns of ``data`` under RPT-R-03."""
    items: list[LayoutColumn] = []
    for column in data.columns:
        if column.kind != "money":
            items.append(LayoutColumn(column, "value", column.header))
            continue
        currencies = sorted(
            {
                str(row[column.key]["currency"])
                for row in data.rows
                if row.get(column.key) is not None
            }
        )
        if len(currencies) == 1:
            items.append(LayoutColumn(column, "value", f"{column.header} ({currencies[0]})"))
        else:
            items.append(LayoutColumn(column, "value", column.header))
            if currencies:
                items.append(LayoutColumn(column, "currency", f"{column.header} currency"))
    return tuple(items)


def utc_text(moment: datetime) -> str:
    """RFC 3339 in UTC with ``Z`` (API-C-07; DS-FMT-25)."""
    if moment.tzinfo is None:
        raise ValueError("report timestamps are timezone-aware")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def display_date(value: date) -> str:
    """``DD MMM YYYY`` (SCREENS_B RV-02)."""
    return f"{value.day:02d} {_MONTHS[value.month - 1]} {value.year:04d}"


def display_timestamp(moment: datetime) -> str:
    """``DD MMM YYYY HH:mm UTC`` (SCREENS_B RV-02)."""
    at = moment.astimezone(UTC)
    return f"{display_date(at.date())} {at.hour:02d}:{at.minute:02d} UTC"


def minor_unit(amount: str) -> int:
    """The decimals of an API-S-Money amount, which carries the currency's minor unit (API-C-06)."""
    return len(amount.split(".", 1)[1]) if "." in amount else 0


def display_amount(amount: str, style: str) -> str:
    """A grouped amount under the tenant negative style: ``(4,000.00)`` or ``-4,000.00``."""
    value = Decimal(amount)
    grouped = f"{abs(value):,.{minor_unit(amount)}f}"
    if value >= 0:
        return grouped
    return f"({grouped})" if style == "PARENTHESES" else f"-{grouped}"


def json_value(column: Column, value: Any) -> Any:
    """The API value of a row field (04 §16.9 run data; API-C-06, API-C-07); null for an empty
    cell and for one that is not shown (``NOT_SHOWN``)."""
    if value is None or value is NOT_SHOWN:
        return None
    match column.kind:
        case "codes":
            return [str(item) for item in value]
        case "integer":
            return int(value)
        case "money":
            return {"amount": str(value["amount"]), "currency": str(value["currency"])}
        case "date":
            return value.isoformat()
        case "timestamp":
            return utc_text(value)
        case "boolean":
            return bool(value)
        case "actor":
            return {
                "id": None if value.get("id") is None else str(value["id"]),
                "kind": str(value["kind"]),
                "display_name": str(value["display_name"]),
            }
        case _:
            return str(value)


def json_rows(data: ReportData) -> list[dict[str, Any]]:
    """Every row as its API object: ``row_key`` and the column fields."""
    return [
        {
            ROW_KEY: str(row[ROW_KEY]),
            **{column.key: json_value(column, row.get(column.key)) for column in data.columns},
        }
        for row in data.rows
    ]


def display_text(column: Column, part: LayoutPart, value: Any, style: str) -> str:
    """The human-readable cell text of XLSX headers and PDF cells."""
    if value is NOT_SHOWN:
        return NOT_SHOWN_TEXT
    if value is None or (column.kind == "codes" and not value):
        return column.empty_text
    if part == "currency":
        return str(value["currency"])
    match column.kind:
        case "codes":
            return ", ".join(str(item) for item in value)
        case "integer":
            return f"{int(value):,}"
        case "money":
            return display_amount(str(value["amount"]), style)
        case "date":
            return display_date(value)
        case "timestamp":
            return display_timestamp(value)
        case "boolean":
            return "Yes" if value else "No"
        case "actor":
            return str(value["display_name"])
        case _:
            return str(value)


def parameter_text(value: Any) -> str:
    """A parameter value as stamp text: lists joined with ", ", flags true or false."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Sequence) and not isinstance(value, str):
        return ", ".join(parameter_text(item) for item in value)
    if isinstance(value, Mapping):
        return ", ".join(f"{key}={parameter_text(item)}" for key, item in sorted(value.items()))
    return str(value)


def total_text(value: Any, style: str) -> str:
    """A control total as stamp text: counts grouped, money with its currency code."""
    if isinstance(value, Mapping) and "amount" in value and "currency" in value:
        return f"{value['currency']} {display_amount(str(value['amount']), style)}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return parameter_text(value)
