"""Read-only access to a legacy ``ASC606.db`` copy (BUILD_SPEC LMG-1; 04 T-MIG-01 ``profile``,
T-MIG-02 ``legacy_row``; ENGINE_SPEC §7.4 S07-R-11; REQ-MIG-004; PRD J-20.1, J-20-ALT-2; legacy
01 §4.3; DG-LAY-11).

This is the only module of ``erev_api`` that imports ``sqlite3`` (DG-ARC-05 allow-list
``backend/erev_api/domain/migration/``). SQLite is a file format here, never a database server
(D-40a): every connection opens the file-store copy through the URI
``file:<path>?mode=ro&immutable=1``, so the source is never written and its SHA-256 is the same
before and after profiling (J-20-AC-2).

``profile`` gives the T-MIG-01 ``profile`` figures (row counts, contracts, legacy POB rows, SSP
versions, selling entities, the latest ``Current Period``, the version tokens). ``rows`` gives
every ``Contract_Live`` row as the 71 legacy column names with values as text exactly as stored
(T-MIG-02 ``legacy_row``; integers as digits, reals as their shortest round-trip decimal, NULL
as ``None``), and ``latest_rows`` selects the latest version per ``Record Unique ID without
time`` by ``Processing Time Log`` then SQLite ``rowid`` (S07-R-11; legacy 01 §4.3). A file
without the table ``Contract_Live`` is refused with 422 ``legacy-database-unrecognized``
(ERR-20).
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from erev_engine.canonical import sha256_hex

from erev_api.problems import Problem

__all__ = [
    "CONTRACT",
    "CONTRACT_LIVE",
    "CURRENT_PERIOD",
    "NUMERIC_TYPES",
    "POB",
    "PROCESSING_TIME_LOG",
    "RECORD_KEY",
    "RECORD_UNIQUE_ID",
    "SELLING_ENTITY",
    "SKU",
    "SKU_SSP",
    "SSP_VERSION",
    "STRATIFICATION",
    "UNRECOGNISED_DETAIL",
    "LegacyColumn",
    "LegacyProfile",
    "LegacyRow",
    "decimal_of",
    "file_sha256",
    "latest_rows",
    "load_legacy_rows",
    "parse_period",
    "profile",
    "read_only_uri",
    "recognise",
    "rows",
    "schema",
    "sku_ssp_rows",
    "text_of",
]

CONTRACT_LIVE: Final = "Contract_Live"
SKU_SSP: Final = "SKU_SSP"
# Legacy column names this module reads by name (04 §17.2; the wording is legacy's, D-33).
CONTRACT: Final = "Contract Unique Name"
POB: Final = "POB Unique ID"
SKU: Final = "SKU Name"
STRATIFICATION: Final = "ASC 606 Stratification"
SELLING_ENTITY: Final = "Selling Entity"
SSP_VERSION: Final = "SSP Version"
CURRENT_PERIOD: Final = "Current Period"
PROCESSING_TIME_LOG: Final = "Processing Time Log"
RECORD_KEY: Final = "Record Unique ID without time"
RECORD_UNIQUE_ID: Final = "Record Unique ID"
# SQLite declared types the comparison treats as numeric
# (compare-shipped/point_in_time_column_diffs.csv).
NUMERIC_TYPES: Final = frozenset({"INTEGER", "REAL", "NUMERIC"})
UNRECOGNISED_DETAIL: Final = (
    "The file is not a legacy eRev database: table Contract_Live was not found."
)
_UNRECOGNISED: Final = "legacy-database-unrecognized"
_TABLE_QUERY: Final = "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"


@dataclass(frozen=True, slots=True)
class LegacyColumn:
    """One column of a legacy table: its name and SQLite declared type."""

    name: str
    declared_type: str

    @property
    def is_numeric(self) -> bool:
        return self.declared_type.upper() in NUMERIC_TYPES


@dataclass(frozen=True, slots=True)
class LegacyRow:
    """One ``Contract_Live`` row: SQLite ``rowid`` and the 71 columns as text (T-MIG-02)."""

    source_rowid: int
    values: Mapping[str, str | None]

    @property
    def contract_external_id(self) -> str:
        return self.values.get(CONTRACT) or ""

    @property
    def obligation_key(self) -> str:
        return self.values.get(POB) or ""

    @property
    def product_code(self) -> str:
        return self.values.get(SKU) or ""

    @property
    def record_key(self) -> str:
        return self.values.get(RECORD_KEY) or ""

    @property
    def processing_time_log(self) -> str:
        return self.values.get(PROCESSING_TIME_LOG) or ""

    @property
    def record_unique_id(self) -> str:
        return self.values.get(RECORD_UNIQUE_ID) or ""

    @property
    def current_period(self) -> date | None:
        return parse_period(self.values.get(CURRENT_PERIOD))

    @property
    def sha256(self) -> str:
        """T-MIG-02 ``legacy_row_sha256``: the canonical JSON of the 71 text values."""
        return sha256_hex(dict(self.values))


@dataclass(frozen=True, slots=True)
class LegacyProfile:
    """T-MIG-01 ``profile`` (PRD J-20.1; SCREENS_B §10.3 "Key figures")."""

    source_sha256: str
    tables: Mapping[str, int]
    contract_live_rows: int
    contracts: int
    legacy_pob_rows: int
    sku_ssp_rows: int
    ssp_versions: tuple[str, ...]
    selling_entities: tuple[str, ...]
    latest_current_period: date | None
    version_tokens: tuple[str, ...]
    columns: tuple[LegacyColumn, ...]
    # 04 rev 1.72 (D-98 133 AMENDMENT 4): the SKU_SSP replay evidence the /import confirmation binds
    sku_ssp_sha256: str = ""
    sku_ssp_findings: tuple[Mapping[str, Any], ...] = ()
    sku_ssp_keys: tuple[tuple[str, str, str], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "tables": dict(self.tables),
            "contract_live_rows": self.contract_live_rows,
            "contracts": self.contracts,
            "legacy_pob_rows": self.legacy_pob_rows,
            "sku_ssp_rows": self.sku_ssp_rows,
            "ssp_versions": list(self.ssp_versions),
            "selling_entities": list(self.selling_entities),
            "latest_current_period": (
                None
                if self.latest_current_period is None
                else self.latest_current_period.isoformat()
            ),
            "version_tokens": list(self.version_tokens),
            "columns": [[column.name, column.declared_type] for column in self.columns],
            "sku_ssp_sha256": self.sku_ssp_sha256,
            "sku_ssp_findings": [dict(finding) for finding in self.sku_ssp_findings],
            "sku_ssp_keys": [list(key) for key in self.sku_ssp_keys],
        }


def read_only_uri(path: Path) -> str:
    """The SQLite URI of a read-only, immutable open (REQ-MIG-004; DG-LAY-11)."""
    return f"{path.resolve().as_uri()}?mode=ro&immutable=1"


def connect_read_only(path: Path) -> sqlite3.Connection:
    """05 UPL-09 (REQ-MIG-004; SAR-42): the read-only, immutable open with ``trusted_schema`` off
    and ``query_only`` on, so no trigger, view or schema-embedded SQL of an uploaded database can
    run or write. The URI already refuses writes; the pragmas close the schema-trust and
    query-only gaps for any statement the reader issues."""
    connection = sqlite3.connect(read_only_uri(path), uri=True)
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("PRAGMA query_only = ON")
    return connection


def _connect(path: Path) -> sqlite3.Connection:
    return connect_read_only(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_of(value: object) -> str | None:
    """A stored SQLite value as text exactly as stored (T-MIG-02): digits for an integer, the
    shortest round-trip decimal for a real, the text itself, ``None`` for NULL.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported legacy value {type(value).__name__}")


def decimal_of(text: str | None) -> Decimal | None:
    """The exact decimal of a stored numeric text (the shortest decimal string, S07-R-11)."""
    if text is None or text == "":
        return None
    return Decimal(text)


def parse_period(text: str | None) -> date | None:
    """A legacy timestamp column (``YYYY-MM-DD HH:MM:SS`` or a date) as a date."""
    if text is None or text == "":
        return None
    return datetime.fromisoformat(text).date()


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [str(name) for (name,) in connection.execute(_TABLE_QUERY)]


def recognise(path: Path) -> None:
    """Refuse a file without ``Contract_Live`` (ERR-20; PRD J-20-ALT-2)."""
    try:
        with _connect(path) as connection:
            tables = _tables(connection)
    except sqlite3.DatabaseError:
        tables = []
    if CONTRACT_LIVE not in tables:
        raise Problem(_UNRECOGNISED, UNRECOGNISED_DETAIL)


def schema(path: Path, table: str = CONTRACT_LIVE) -> tuple[LegacyColumn, ...]:
    """The columns of ``table`` with their declared types, in table order."""
    with _connect(path) as connection:
        info = connection.execute(_SCHEMA_SQL[table]).fetchall()
    return tuple(LegacyColumn(str(row[1]), str(row[2] or "")) for row in info)


_ROWS_SQL: Final[Mapping[str, str]] = MappingProxyType(
    {
        CONTRACT_LIVE: 'SELECT rowid, * FROM "Contract_Live" ORDER BY rowid',
        SKU_SSP: 'SELECT rowid, * FROM "SKU_SSP" ORDER BY rowid',
    }
)
_COUNT_SQL: Final[Mapping[str, str]] = MappingProxyType(
    {
        CONTRACT_LIVE: 'SELECT COUNT(*) FROM "Contract_Live"',
        SKU_SSP: 'SELECT COUNT(*) FROM "SKU_SSP"',
    }
)
_SCHEMA_SQL: Final[Mapping[str, str]] = MappingProxyType(
    {
        CONTRACT_LIVE: 'PRAGMA table_info("Contract_Live")',
        SKU_SSP: 'PRAGMA table_info("SKU_SSP")',
    }
)


def _select_rows(
    connection: sqlite3.Connection, table: str
) -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
    cursor = connection.execute(_ROWS_SQL[table])
    names = tuple(str(column[0]) for column in cursor.description)[1:]
    return names, cursor.fetchall()


def rows(path: Path) -> tuple[LegacyRow, ...]:
    """Every ``Contract_Live`` row in ``rowid`` order, values as stored text."""
    recognise(path)
    with _connect(path) as connection:
        names, found = _select_rows(connection, CONTRACT_LIVE)
    return tuple(
        LegacyRow(
            source_rowid=int(record[0]),
            values=MappingProxyType(
                {name: text_of(value) for name, value in zip(names, record[1:], strict=True)}
            ),
        )
        for record in found
    )


def load_legacy_rows(path: Path) -> tuple[Mapping[str, str | None], ...]:
    """The ``Contract_Live`` rows as plain mappings of the 71 legacy names to stored text, in
    ``rowid`` order — the legacy side of ``reconciliation.compare_point_in_time`` (the T1 reader's
    loader; DG-LAY-11 read-only open)."""
    return tuple(row.values for row in rows(path))


def sku_ssp_rows(path: Path) -> tuple[Mapping[str, str | None], ...]:
    """Every ``SKU_SSP`` row as text; empty when the table is absent."""
    with _connect(path) as connection:
        if SKU_SSP not in _tables(connection):
            return ()
        names, found = _select_rows(connection, SKU_SSP)
    return tuple(
        MappingProxyType(
            {name: text_of(value) for name, value in zip(names, record[1:], strict=True)}
        )
        for record in found
    )


def latest_rows(found: Iterable[LegacyRow]) -> tuple[LegacyRow, ...]:
    """The latest version per ``Record Unique ID without time``: greatest ``Processing Time Log``,
    then greatest ``rowid`` (S07-R-11; legacy 01 §4.3), ordered by record key.
    """
    latest: dict[str, LegacyRow] = {}
    for row in found:
        current = latest.get(row.record_key)
        if current is None or (row.processing_time_log, row.source_rowid) > (
            current.processing_time_log,
            current.source_rowid,
        ):
            latest[row.record_key] = row
    return tuple(latest[key] for key in sorted(latest))


def _distinct(values: Iterable[str | None]) -> tuple[str, ...]:
    found: set[str] = set()
    for value in values:
        if value is not None and value != "":
            found.add(value)
    return tuple(sorted(found))


def sku_ssp_digest(rows: Sequence[Mapping[str, str | None]]) -> str:
    """SHA-256 of the canonical ``SKU_SSP`` row list, values as stored text (04 rev 1.72): what the
    ``MIGRATION_SSP_REPLAY`` request binds and the import job re-verifies over the spooled source.
    """
    return sha256_hex([dict(sorted(row.items())) for row in rows])


def sku_ssp_keys(rows: Sequence[Mapping[str, str | None]]) -> tuple[tuple[str, str, str], ...]:
    """The distinct (``SSP Version``, ``SKU Name``, ``ASC 606 Stratification``) keys, sorted."""
    return tuple(
        sorted(
            {
                (
                    str(row.get(SSP_VERSION) or ""),
                    str(row.get(SKU) or ""),
                    str(row.get(STRATIFICATION) or ""),
                )
                for row in rows
            }
        )
    )


def sku_ssp_findings(rows: Sequence[Mapping[str, str | None]]) -> list[dict[str, Any]]:
    """The LM-SSP-01..09 row findings of the ``SKU_SSP`` rows, typed exactly as the
    ``legacy_sku_ssp``
    template types them (blank required cells, non-numeric numbers, the template's row rules) —
    ``[{row, code, column, message}]``, ``row`` = 1-based position (04 rev 1.72). Empty = the replay
    request may be submitted at ``/import``."""
    # local imports: legacy_db is a leaf the import layer must not pull in at import time
    from erev_api.domain.imports import validate as import_validate
    from erev_api.domain.imports.legacy_templates import LEGACY_HEADER_TYPES
    from erev_api.domain.imports.legacy_v1 import sku_ssp

    found: list[dict[str, Any]] = []
    headers = LEGACY_HEADER_TYPES["legacy_sku_ssp"]
    for number, row in enumerate(rows, 1):
        typed: dict[str, Any] = {}
        row_findings: list[tuple[str, str, str]] = []
        for name, kind, required in headers:
            value, code = import_validate.coerce(kind, row.get(name))
            if code == "VALUE_NOT_NUMERIC":
                row_findings.append(
                    (code, name, import_validate.not_numeric(name, str(row.get(name) or "")))
                )
            elif code == "DATE_INVALID":
                row_findings.append((code, name, import_validate.date_invalid(name)))
            elif value is None and required:
                row_findings.append(
                    ("REQUIRED_VALUE_BLANK", name, import_validate.required_blank(name))
                )
            typed[name] = value
        for rule in sku_ssp.ROW_RULES:
            for finding in rule(typed):
                if finding.severity == "ERROR":
                    row_findings.append((finding.code, finding.column or "", finding.message))
        found.extend(
            {"row": number, "code": code, "column": column, "message": message}
            for code, column, message in row_findings
        )
    return found


def profile(path: Path) -> LegacyProfile:
    """The T-MIG-01 ``profile`` of a legacy database copy (PRD J-20.1)."""
    recognise(path)
    found = rows(path)
    ssp = sku_ssp_rows(path)
    with _connect(path) as connection:
        tables = {
            name: int(connection.execute(_COUNT_SQL[name]).fetchone()[0])
            for name in _tables(connection)
            if name in _COUNT_SQL
        }
    # J-20.1 "latest Current Period": the period of the latest processed version (legacy 01 §4.3
    # "latest" is the most recently processed), the rows carrying the greatest Processing Time Log.
    newest = max((row.processing_time_log for row in found), default="")
    periods = [
        row.current_period
        for row in found
        if row.processing_time_log == newest and row.current_period is not None
    ]
    return LegacyProfile(
        source_sha256=file_sha256(path),
        tables=MappingProxyType(tables),
        contract_live_rows=len(found),
        contracts=len(_distinct(row.contract_external_id for row in found)),
        legacy_pob_rows=len(_distinct(row.record_key for row in found)),
        sku_ssp_rows=len(ssp),
        ssp_versions=_distinct(row.get(SSP_VERSION) for row in ssp),
        selling_entities=_distinct(row.values.get(SELLING_ENTITY) for row in found),
        latest_current_period=max(periods, default=None),
        version_tokens=_distinct(row.processing_time_log for row in found),
        columns=schema(path),
        sku_ssp_sha256=sku_ssp_digest(ssp),
        sku_ssp_findings=tuple(sku_ssp_findings(ssp)),
        sku_ssp_keys=sku_ssp_keys(ssp),
    )


def column_names(columns: Sequence[LegacyColumn]) -> tuple[str, ...]:
    return tuple(column.name for column in columns)
