"""Lock snapshot datasets: canonical CSV bytes, control totals and the manifest hash (ENGINE_SPEC_B
§15.2.7 S15-R-18 to S15-R-20; S15-INV-06; 04 T-CLS-04, T-CLS-05, E-64; DEV-099; BUILD_SPEC EDS-6).

A ``Dataset`` is the pure content of one E-64 snapshot kind: typed columns and rows keyed by
``row_key``. ``encode`` writes UTF-8 CSV with a header row, rows sorted by row key, money with
exactly the currency's minor-unit places (DG-KRN-MONEY-06), exact values trimmed
(``format_exact``), dates ISO, integers plain, and no index column (DEV-099); ``file_sha256`` is
the SHA-256 of those bytes, so two builds from the same state give identical bytes and control
totals (S15-INV-06). ``manifest_sha256`` is the SHA-256 of the lines
``<snapshot kind>:<file_sha256>`` sorted by kind joined with ``\\n`` (S15-R-19;
``period_lock.snapshot_manifest_sha256``).
``opening_from_rollforward`` reads the ``CLOSING`` row of a ``CONTRACT_BALANCE_ROLLFORWARD`` dataset
as the next period's opening (S15-R-20).

Values are typed by the column kind: ``money`` cells are ``Money(minor, currency)``; ``exact`` cells
are ``Fraction``; ``integer`` cells ``int``; ``date`` cells ``date``; ``text`` cells ``str``. No
float ever enters (CV-30). The platform writes the bytes to a file, the row count and control totals
to T-CLS-05, and the manifest hash to the lock (CLO-6, F-CLO); this module is the engine half.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Any, Final

from erev_engine.currencies import ISO_4217
from erev_engine.money import format_exact, format_money

__all__ = [
    "COLUMN_KINDS",
    "SNAPSHOT_KINDS",
    "Column",
    "Dataset",
    "Encoded",
    "Money",
    "encode",
    "manifest_sha256",
    "opening_from_rollforward",
    "sum_money",
]

# 04 E-64 ``snapshot_kind``.
SNAPSHOT_KINDS: Final = (
    "WATERFALL",
    "CONTRACT_BALANCES",
    "CONTRACT_BALANCE_ROLLFORWARD",
    "RPO",
    "RPO_ROLLFORWARD",
    "DISAGGREGATION",
    "PRIOR_PERIOD_POB_REVENUE",
    "COST_ROLLFORWARD",
    "JE_POPULATION",
    "OUT_OF_PERIOD_REGISTER",
    "MODIFICATION_REGISTER",
    "MANUAL_ADJUSTMENT_REGISTER",
)
COLUMN_KINDS: Final = frozenset({"text", "money", "exact", "integer", "date"})
ROW_KEY: Final = "row_key"


@dataclass(frozen=True, slots=True)
class Money:
    """A money cell: minor units of ``currency`` (DG-KRN-MONEY-06)."""

    minor: int
    currency: str
    minor_unit: int  # the currency's places (from the currency table; 2 for USD, 0 for JPY)

    def __post_init__(self) -> None:
        """The scale is validated against the currency table (Codex review of 642363e, R3)."""
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise TypeError("Money.minor is an int of minor units")
        if isinstance(self.minor_unit, bool) or not isinstance(self.minor_unit, int):
            raise ValueError("Money.minor_unit is an int number of places")
        if not 0 <= self.minor_unit <= 6:
            raise ValueError(f"Money.minor_unit {self.minor_unit} is not a number of places")
        spec = ISO_4217.get(self.currency)
        if spec is not None and spec.minor_unit != self.minor_unit:
            raise ValueError(
                f"{self.currency}: minor_unit {self.minor_unit} differs from the currency table "
                f"({spec.minor_unit})"
            )

    def text(self) -> str:
        return format_money(self.minor, self.minor_unit)


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    kind: str  # COLUMN_KINDS

    def __post_init__(self) -> None:
        if self.kind not in COLUMN_KINDS:
            raise ValueError(f"column {self.key!r}: unknown kind {self.kind!r}")
        if not self.key or "," in self.key or "\n" in self.key or '"' in self.key:
            raise ValueError(f"column key {self.key!r} is not a plain CSV header")


@dataclass(frozen=True, slots=True)
class Dataset:
    """The content of one snapshot kind before encoding."""

    kind: str  # SNAPSHOT_KINDS
    columns: tuple[Column, ...]  # in output order; the first is the row key
    rows: tuple[Mapping[str, object], ...]  # each with ROW_KEY and a value per column key

    def __post_init__(self) -> None:
        if self.kind not in SNAPSHOT_KINDS:
            raise ValueError(f"unknown snapshot kind {self.kind!r} (04 E-64)")
        if not self.columns or self.columns[0].key != ROW_KEY or self.columns[0].kind != "text":
            raise ValueError("the first column is the text row_key (S15-R-18 sort key)")
        keys = [column.key for column in self.columns]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate column keys")
        seen: set[str] = set()
        for row in self.rows:
            key = row.get(ROW_KEY)
            if not isinstance(key, str) or not key:
                raise ValueError("every row carries a non-empty text row_key")
            if key in seen:
                raise ValueError(f"duplicate row_key {key!r}")
            seen.add(key)


@dataclass(frozen=True, slots=True)
class Encoded:
    """T-CLS-05 members of one snapshot: the bytes, their hash, the row count and control totals."""

    kind: str
    content: bytes
    file_sha256: str
    row_count: int
    # RPS-SNAP (D-98 139 Q2): the builder's totals verbatim — a per-currency mapping per measure, a
    # scalar count or a list — never flattened (04 T-CLS-05 rows 1.40 / 1.44 / 1.58; ENGINE_SPEC_B
    # S15-R-18 rev 1.37).
    control_totals: Mapping[str, Any]


def _cell(column: Column, value: object) -> str:
    """The canonical text of one cell; a value of the wrong type raises (no coercion, CV-30)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"column {column.key!r}: {type(value).__name__} is not a dataset value")
    if column.kind == "text":
        if not isinstance(value, str):
            raise TypeError(f"column {column.key!r}: text cell is not str")
        return value
    if column.kind == "money":
        if not isinstance(value, Money):
            raise TypeError(f"column {column.key!r}: money cell is not Money")
        return value.text()
    if column.kind == "exact":
        if not isinstance(value, Fraction | int):
            raise TypeError(f"column {column.key!r}: exact cell is not Fraction")
        return format_exact(Fraction(value))
    if column.kind == "integer":
        if not isinstance(value, int):
            raise TypeError(f"column {column.key!r}: integer cell is not int")
        return str(value)
    if not isinstance(value, date):
        raise TypeError(f"column {column.key!r}: date cell is not date")
    return value.isoformat()


def _scale(scales: dict[str, int], value: Money) -> None:
    """Record ``value``'s scale per currency; a second scale of one currency is refused (R3)."""
    known = scales.setdefault(value.currency, value.minor_unit)
    if known != value.minor_unit:
        raise ValueError(
            f"{value.currency}: inconsistent currency scale ({known} and {value.minor_unit} places)"
        )


def _csv_field(text: str) -> str:
    """RFC 4180 quoting only when needed, so plain figures stay byte-stable."""
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def encode(dataset: Dataset, control_totals: Mapping[str, Any] | None = None) -> Encoded:
    """S15-R-18: UTF-8 CSV, header row, rows sorted by row key, canonical cells, no index column."""
    scales: dict[str, int] = {}
    for row in dataset.rows:  # R3: one scale per currency across the dataset, before encoding
        for column in dataset.columns:
            if column.kind == "money" and isinstance(row.get(column.key), Money):
                _scale(scales, row[column.key])  # type: ignore[arg-type]
    lines = [",".join(_csv_field(column.key) for column in dataset.columns)]
    for row in sorted(dataset.rows, key=lambda item: str(item[ROW_KEY])):
        cells = []
        for column in dataset.columns:
            if column.key not in row:
                raise ValueError(f"row {row[ROW_KEY]!r} lacks column {column.key!r}")
            cells.append(_csv_field(_cell(column, row[column.key])))
        lines.append(",".join(cells))
    content = ("\n".join(lines) + "\n").encode("utf-8")
    return Encoded(
        kind=dataset.kind,
        content=content,
        file_sha256=hashlib.sha256(content).hexdigest(),
        row_count=len(dataset.rows),
        control_totals=dict(sorted((control_totals or {}).items())),
    )


def sum_money(rows: Iterable[Mapping[str, object]], key: str) -> dict[str, str]:
    """Σ of a money column per currency as canonical text: the §15.2.7 control totals."""
    totals: dict[str, tuple[int, int]] = {}
    scales: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        if not isinstance(value, Money):
            raise TypeError(f"column {key!r}: money cell is not Money")
        _scale(scales, value)  # R3: refuse a second scale of one currency before aggregating
        minor, unit = totals.get(value.currency, (0, value.minor_unit))
        totals[value.currency] = (minor + value.minor, unit)
    return {
        currency: format_money(minor, unit) for currency, (minor, unit) in sorted(totals.items())
    }


def manifest_sha256(files: Mapping[str, str]) -> str:
    """S15-R-19: SHA-256 of the ``<kind>:<file_sha256>`` lines sorted by kind, joined by ``\\n``."""
    for kind, digest in files.items():
        if kind not in SNAPSHOT_KINDS:
            raise ValueError(f"unknown snapshot kind {kind!r} (04 E-64)")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"{kind}: file_sha256 is not a lowercase hex SHA-256")
    lines = "\n".join(f"{kind}:{files[kind]}" for kind in sorted(files))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def opening_from_rollforward(
    rows: Sequence[Mapping[str, object]], balances: Sequence[str], *, line: str = "CLOSING"
) -> dict[str, Money]:
    """S15-R-20: the ``CLOSING`` row of the previous ``CONTRACT_BALANCE_ROLLFORWARD`` dataset as the
    opening balances of the next period (row key ``CLOSING`` or ``CLOSING:<ISO>``)."""
    found = [row for row in rows if str(row.get(ROW_KEY, "")).split(":", 1)[0] == line]
    if len(found) != 1:
        raise ValueError(f"{len(found)} {line} rows in the snapshot; one expected")
    (closing,) = found
    opening: dict[str, Money] = {}
    for balance in balances:
        value = closing.get(balance)
        if not isinstance(value, Money):
            raise ValueError(f"{line} row carries no money {balance!r}")
        opening[balance] = value
    return opening
