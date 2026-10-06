"""The lock-snapshot dataset registry (BUILD_SPEC RPS-4 / RPS-SNAP; 04 T-CLS-05, E-64; ENGINE_SPEC_B
§15.2.7 S15-R-18 to S15-R-20a; design note PRODUCTION-F-RPS-RPS-SNAP-DESIGN.md D1–D8, A1, A2; record
§50).

F-CLO's ``close/snapshots.py::freeze_datasets`` resolves this module by name (``SNAPSHOT_DATASETS``,
``SnapshotScope``) at the PERIOD_LOCK decision and at CLO-20's ``DATASET_FREEZE``, calls one
``DatasetBuilder`` per E-64 kind with the lock's ``SnapshotScope`` and stores the returned engine
``Encoded`` bytes as the T-CLS-05 file of that kind (``report_run_id`` NULL, ruling Q-10).

The canonical shape of every kind is the re-lock consumer's key contract
(``close/relock_diff.py::KEY_COLUMNS``, ENGINE_SPEC_B §15.2.7 / S15-R-20a), restated here as
``REQUIRED`` and pinned equal by a CPU witness — NOT the live report's default presentation (A2-1).
TWO kinds are produced LONG-FORM from the builders' REAL consumed populations with the report's own
figure helpers: ``WATERFALL`` from ``revenue_waterfall.population`` at (entity, contract,
obligation, period key) and ``RPO`` from ``rpo._run`` at (entity, contract, obligation) — one row
per governed key, never a proxy identity, never a second calculation. TEN kinds wrap the real
``build`` of their registered report with the presentation ``TOTAL:<ISO>`` rows removed (their NULL
identity would collide under the re-lock key; the totals live in ``control_totals``). Every adapter
derives the request a user would make for the lock's entity, book and period at the cutoff and
normalises it exactly as ``framework._resolve`` does — ``PARAMETER_DEFAULTS``, false booleans, the
closed schema — WITHOUT the caller's ``report.run`` scope filter (A1: the freeze's authorisation is
the lock decision's; the lock's entity is the scope by construction). Encoding (D5 / A2-2 / A2-3):
the engine's S15-R-18 ``encode`` over ``row_key`` + every report column as text-kind canonical
cells — RAW (A4 13.1): identity and text cells carry the admitted value itself, never the
spreadsheet-guarded display text (the guard is applied at the export boundary,
``locked.export_csv``);
the long-form ``row_key`` is ``obligation:`` + the CV-21-encoded declared key tuple (A4 13.2,
``row_key_of`` / ``decode_row_key``; D-98 candidate 104 precedent) — injective, reversible, never
an unescaped join;
REQUIRED columns (the key columns and the kind's currency column(s)) are read by name and refused by
name when absent or, outside the per-kind admitted-empty components, empty (the rollforwards' line
rows state ``contract_external_id`` empty and their by-contract rows ``line_code`` — each row
carries one of the two, ``ROW_IDENTITY``); optional cells encode
None as ""; every money-bearing row carries its currency as an explicit code column bound to each
money column by ``CURRENCY_OF``; ``control_totals`` are the builder's (or the long-form producer's
kinds-table totals) verbatim. The per-kind cutoff (A2-4) is ``known_at`` for eleven kinds and the
FREEZE INSTANT (``frozen_at`` or ``known_at``) for ``JE_POPULATION`` (S15-R-18b Q5). No source
binding is recorded for a frozen dataset (D6).

TWELVE adapters, NO named dependency: SNAP-2 (design §14) adopted F-CTR's ``modification_register``
(CTR-17 slice 1) as the eleventh adapter — a wrapped kind selected by the lock period's DATE bounds
(``from_date`` / ``to_date``) with the SCREENS_B status / currency-view defaults from
``PARAMETER_DEFAULTS``; APPROVED rows are impact-preview figures identified by ``status`` — and
F-CLO's ``manual_adjustment_register`` (BUILD_SPEC RPS-8 RPT-18; ENGINE_SPEC_B S15-R-20d) is
the twelfth — a wrapped kind selected by the lock's PERIOD key (``from_period_key`` =
``to_period_key``) with the functional currency view from ``PARAMETER_DEFAULTS``.
``SNAPSHOT_DEPENDENCIES`` is EMPTY and kept as the registry's shape for a future kind: a kind
absent from ``SNAPSHOT_DATASETS`` is still refused by name (``dataset_for``; F-CLO's
``freeze_datasets`` before any write) — never an empty
dataset, never a stub (Codex production-20260921-1505 §3 / 1521 §5). Twelve registered
producers complete the REGISTRY; public close completion still requires the actual approved
lock path of Codex production-20260921-1505 §3 (CLO-8c: the request, a different Controller's
approval, the certified gates, twelve stored datasets, CLOSED, the next period's opening) —
the registry alone closes nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.stages.s15_disclosures import snapshots as engine
from sqlalchemy import select

from erev_api.db.tables import legal_entity, period
from erev_api.domain.reports import elections, framework, locked, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as cbr_builder
from erev_api.domain.reports.builders import contract_balances as balances_builder
from erev_api.domain.reports.builders import contract_cost_rollforward as cost_builder
from erev_api.domain.reports.builders import disaggregation as disaggregation_builder
from erev_api.domain.reports.builders import je_population as je_builder
from erev_api.domain.reports.builders import manual_adjustment_register as mar_builder
from erev_api.domain.reports.builders import modification_register as modreg_builder
from erev_api.domain.reports.builders import out_of_period_register as oop_builder
from erev_api.domain.reports.builders import revenue_from_opening_liability as ppr_builder
from erev_api.domain.reports.builders import revenue_waterfall as waterfall_builder
from erev_api.domain.reports.builders import rpo as rpo_builder
from erev_api.domain.reports.builders import rpo_rollforward as rpo_rf_builder
from erev_api.domain.reports.builders.out_of_period_register import ENCODED, encode_component
from erev_api.domain.reports.outputs import ROW_KEY, Column, ReportData, utc_text
from erev_api.domain.reports.outputs import csv as csv_output

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "CURRENCY_OF",
    "CUTOFF_OF",
    "EMPTY_KEY_ADMITTED",
    "REQUIRED",
    "ROW_IDENTITY",
    "SNAPSHOT_DATASETS",
    "SNAPSHOT_DEPENDENCIES",
    "ROW_KEY_PREFIX",
    "TOTAL_PREFIX",
    "DatasetBuilder",
    "SnapshotDependency",
    "SnapshotDependencyMissing",
    "SnapshotRefusal",
    "SnapshotScope",
    "cutoff_of",
    "dataset_for",
    "declared_kinds",
    "decode_row_key",
    "encode_report",
    "row_key_of",
    "scope_parameters",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotScope:
    """The lock's scope a dataset is frozen for (F-CLO-prep :101): one entity, its book, the
    period, the cutoff instant and — A2-4 — the freeze instant (``None`` = the cutoff). The lock
    decision and the close run's ``DATASET_FREEZE`` step both pass one instant as ``known_at`` and
    as ``frozen_at`` (ENGINE_SPEC_B S15-R-18 rev 1.82, S15-R-18c)."""

    entity_id: UUID
    book_code: str
    period_id: UUID
    known_at: datetime
    frozen_at: datetime | None = None


type DatasetBuilder = Callable[["UnitOfWork", SnapshotScope], engine.Encoded]


class SnapshotRefusal(RuntimeError):
    """One kind's freeze refused by NAME (kind, reason); nothing is saved."""

    def __init__(self, kind: str, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(f"{kind}: {reason}")


@dataclass(frozen=True, slots=True)
class SnapshotDependency:
    """A kind whose producer another lane owns and has not landed: named, interim, never
    substituted."""

    kind: str
    report_code: str
    owner: str
    producer: str
    row_key: str
    control_totals: str


class SnapshotDependencyMissing(SnapshotRefusal):
    """The named dependency of a register kind whose producer has not landed."""

    def __init__(self, dependency: SnapshotDependency) -> None:
        self.dependency = dependency
        super().__init__(
            dependency.kind,
            f"no dataset builder — the producer is {dependency.producer} ({dependency.owner}); "
            "no empty dataset is substituted (design D3; Codex production-20260921-1505 §3)",
        )


# Twelve of twelve producers registered (F-CLO's manual_adjustment_register landed): no named
# dependency remains; the mapping keeps the registry's shape for a future E-64 kind.
SNAPSHOT_DEPENDENCIES: Final[Mapping[str, SnapshotDependency]] = MappingProxyType({})

# --- the canonical key contract per kind (= close/relock_diff.KEY_COLUMNS; pinned by a test) ---
KEY_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "WATERFALL": ("entity_code", "contract_external_id", "obligation_key", "period_key"),
        "CONTRACT_BALANCES": ("entity_code", "contract_external_id"),
        "CONTRACT_BALANCE_ROLLFORWARD": ("line_code", "contract_external_id", "currency"),
        "RPO": ("entity_code", "contract_external_id", "obligation_key"),
        "RPO_ROLLFORWARD": ("line_code", "contract_external_id", "currency"),
        "DISAGGREGATION": ("dimension_code", "dimension_value", "timing_code", "currency"),
        "PRIOR_PERIOD_POB_REVENUE": ("entity_code", "contract_external_id", "obligation_key"),
        "COST_ROLLFORWARD": ("cost_kind", "line_code"),
        "JE_POPULATION": ("entity_code", "book", "je_no", "line_no"),
        "OUT_OF_PERIOD_REGISTER": ("origin_period_key", "posting_period_key", "event_key"),
        "MODIFICATION_REGISTER": ("contract_external_id", "modification_no", "obligation_key"),
        "MANUAL_ADJUSTMENT_REGISTER": ("entity_code", "adjustment_no"),
    }
)
# A2-3: the currency column(s) of a kind; every money column not named here binds to ``currency``.
CURRENCY_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        **{kind: ("currency",) for kind in KEY_COLUMNS},
        "JE_POPULATION": ("txn_currency", "functional_currency"),
    }
)
CURRENCY_OF: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "JE_POPULATION": MappingProxyType(
            {
                "debit_txn": "txn_currency",
                "credit_txn": "txn_currency",
                "debit_functional": "functional_currency",
                "credit_functional": "functional_currency",
            }
        )
    }
)
# REQUIRED = the key columns plus the currency column(s): read by name, refused by name (A2-2).
REQUIRED: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        kind: tuple(dict.fromkeys((*KEY_COLUMNS[kind], *CURRENCY_COLUMNS[kind])))
        for kind in KEY_COLUMNS
    }
)
# A2-2: key components a kind's contract makes legitimately EMPTY on some rows. The rollforwards
# hold two row types under one key (04 T-CLS-05 "Dataset identity", D-98 85: ``line_code`` (+
# ``contract_external_id``, ``currency`` for the by-contract rows)): a LINE row names no contract,
# a BY-CONTRACT row no line — each leaves the other's component empty (``ROW_IDENTITY`` below).
EMPTY_KEY_ADMITTED: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "CONTRACT_BALANCE_ROLLFORWARD": frozenset({"line_code", "contract_external_id"}),
        "RPO_ROLLFORWARD": frozenset({"line_code", "contract_external_id"}),
        "DISAGGREGATION": frozenset({"dimension_value", "timing_code"}),  # timing / non-timing rows
        "OUT_OF_PERIOD_REGISTER": frozenset(),
    }
)
# S15-R-20a (a key that cannot be obtained from the builder refuses by name): the admitted-empty
# components of which every row still carries AT LEAST ONE — a rollforward row is a line row or a
# by-contract row; a row with neither has no identity and is never frozen.
ROW_IDENTITY: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "CONTRACT_BALANCE_ROLLFORWARD": ("line_code", "contract_external_id"),
        "RPO_ROLLFORWARD": ("line_code", "contract_external_id"),
    }
)
# A2-4: the cutoff each kind is frozen at — the FREEZE INSTANT for JE_POPULATION (S15-R-18b Q5).
CUTOFF_OF: Final[Mapping[str, str]] = MappingProxyType(
    {**{kind: "known_at" for kind in KEY_COLUMNS}, "JE_POPULATION": "frozen_at"}
)
TOTAL_PREFIX: Final = "TOTAL:"  # presentation totals of the wrapped reports (removed; Q7)
# A4 13.2: the long-form row key is the declared key tuple, each component CV-21-encoded
# (``%`` → ``%25`` first, then ``/`` ``@`` ``#`` ``:``, and ``|``; D-98 candidate 104), joined with
# ``:`` after the prefix — injective and reversible; never an unescaped join, never a display value.
ROW_KEY_PREFIX: Final = "obligation:"
_ROW_KEY_JOINER: Final = ":"
# the reports whose period is one key; the others take a range (from = to = the lock's period)
_PERIOD_KEY_REPORTS: Final = frozenset({"contract_balances", "rpo"})
# SNAP-2 (design §14): reports selected by a DATE range take the lock period's bounds — its first
# and last day (`period.start_date` / `period.end_date`) — as `from_date` / `to_date`; F-CTR's
# `modification_register` filters `modification.effective_date` inclusively on them.
_DATE_RANGE_REPORTS: Final = frozenset({"modification_register"})
ENTITY_MISSING: Final = "the lock's entity {entity_id} is not on this tree"
PERIOD_MISSING: Final = (
    "the lock's period {period_id} is not on this tree or not on the entity's calendar"
)
DEFINITION_MISSING: Final = "the report {code} has no current definition"
PERIOD_BOUNDS_MISSING: Final = "the date-selected report {code} needs the lock period's bounds"
FINDINGS: Final = "the report request the lock's scope implies is refused: {findings}"
HEADER_MISSING: Final = "the report header lacks the required column(s) {columns}"
COLUMN_MISSING: Final = "row {row_key} lacks the required column {column}"
COLUMN_EMPTY: Final = "row {row_key}: the required column {column} is empty"
IDENTITY_EMPTY: Final = "row {row_key}: every identity column ({columns}) is empty"
CURRENCY_MISMATCH: Final = "row {row_key}: {column} is in {found} but {bound} is {expected}"
NOT_A_DATASET: Final = "the rows do not form a dataset: {reason}"
MULTI_PERIOD: Final = (
    "a snapshot covers the lock's one period; the range resolved to {count} periods (Q6)"
)


# --- the DECLARED column kinds of every frozen kind (A4 13.1 (b); Codex 1739 §3 (c)) ------------
# The artefact stores every cell as text; at the export boundary (`locked.export_csv`) a cell is
# guarded by its DECLARED DS-FMT-25 type — text kinds (code, text, codes, actor) guarded, machine
# kinds (money, integer, decimal, date, timestamp, boolean) never — so a code id "-1" stays text and
# is guarded while a declared money cell "-5.00" follows the numeric branch. Static column tables
# come from the builders themselves; the two dynamic families are declared by rule (RPO's time
# bands, DISAGGREGATION's `period:` columns → money). An undeclared header is TEXT (guarded).
_STATIC_COLUMN_KINDS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "CONTRACT_BALANCES": MappingProxyType(
            {
                "contract_external_id": "code",
                "customer_name": "text",
                "entity_code": "code",
                "currency": "code",
                **{name: "money" for name, _ in balances_builder.MEASURE_COLUMNS},
            }
        ),
        "CONTRACT_BALANCE_ROLLFORWARD": MappingProxyType(
            {column.key: column.kind for column in cbr_builder.COLUMNS}
        ),
        "RPO_ROLLFORWARD": MappingProxyType(
            {column.key: column.kind for column in rpo_rf_builder.COLUMNS}
        ),
        "PRIOR_PERIOD_POB_REVENUE": MappingProxyType(
            {column.key: column.kind for column in ppr_builder.COLUMNS}
        ),
        "COST_ROLLFORWARD": MappingProxyType(
            {column.key: column.kind for column in cost_builder.COLUMNS}
        ),
        "JE_POPULATION": MappingProxyType(
            {column.key: column.kind for column in je_builder.COLUMNS}
        ),
        "MODIFICATION_REGISTER": MappingProxyType(
            {column.key: column.kind for column in modreg_builder.COLUMNS}
        ),
        "MANUAL_ADJUSTMENT_REGISTER": MappingProxyType(
            {column.key: column.kind for column in mar_builder.COLUMNS}
        ),
        "OUT_OF_PERIOD_REGISTER": MappingProxyType(
            {column.key: column.kind for column in oop_builder.COLUMNS}
        ),
        "DISAGGREGATION": MappingProxyType(
            {
                "dimension_code": "code",
                "dimension_value": "code",
                "timing_code": "code",
                "dimension_value_label": "text",
                "timing": "text",
                "currency": "code",
                "total": "money",
            }
        ),
    }
)


def declared_kinds(
    kind: str, headers: Sequence[str], control_totals: Mapping[str, Any] | None = None
) -> dict[str, str]:
    """The DECLARED DS-FMT-25 kind of every frozen column of ``kind`` under ``headers`` (A4 13.1
    (b); Codex 1739 §3 (c); Codex 1824 §2 RPS-TYPE-RPO-1): ``row_key`` text; the static tables
    above; ``WATERFALL`` and ``RPO`` from this module's own column tables; an RPO time band is
    money ONLY when it is bound in the dataset's own control totals (``control_totals["bands"]``,
    the ``Band.out()`` records the producer wrote — bound metadata, never a lexical inference, so
    an unknown RPO header is text and guarded); ``DISAGGREGATION`` ``period:<key>`` columns →
    money; anything else TEXT — the safe default that is guarded at the export boundary."""
    if kind == "WATERFALL":
        static: Mapping[str, str] = {column.key: column.kind for column in WATERFALL_COLUMNS}
    elif kind == "RPO":
        static = {column.key: column.kind for column in _rpo_columns(())}
    else:
        static = _STATIC_COLUMN_KINDS.get(kind, {})
    bound_bands: set[str] = set()
    if kind == "RPO" and control_totals is not None:
        bands = control_totals.get("bands")
        if isinstance(bands, list):
            bound_bands = {str(band["key"]) for band in bands if isinstance(band, Mapping)}
    kinds: dict[str, str] = {}
    for header in headers:
        if header == ROW_KEY:
            kinds[header] = "text"
        elif header in static:
            kinds[header] = static[header]
        elif header in bound_bands or (
            kind == "DISAGGREGATION" and header.startswith(disaggregation_builder.PERIOD_PREFIX)
        ):
            kinds[header] = "money"
        else:
            kinds[header] = "text"
    return kinds


def row_key_of(kind: str, row: Mapping[str, Any]) -> str:
    """A4 13.2: ``obligation:`` + the kind's key columns (``KEY_COLUMNS[kind]``), each component
    CV-21 percent-encoded (``out_of_period_register.encode_component``), joined with ``:`` — a
    pure function of the identity columns, so ``(A:B, C)`` and ``(A, B:C)`` are two keys."""
    return ROW_KEY_PREFIX + _ROW_KEY_JOINER.join(
        encode_component(str(row[column])) for column in KEY_COLUMNS[kind]
    )


def decode_row_key(row_key: str) -> tuple[str, ...]:
    """The key tuple a long-form ``row_key`` encodes (the inverse of ``row_key_of``); ``%25`` is
    decoded last so a literal ``%`` never re-expands. A key without the prefix is refused by
    name."""
    if not row_key.startswith(ROW_KEY_PREFIX):
        raise ValueError(f"not a long-form row key: {row_key!r}")
    components = row_key[len(ROW_KEY_PREFIX) :].split(_ROW_KEY_JOINER)
    decoded = []
    for component in components:
        for plain, encoded in reversed(ENCODED):  # ``|`` ``:`` ``#`` ``@`` ``/`` then ``%``
            component = component.replace(encoded, plain)
        decoded.append(component)
    return tuple(decoded)


def cutoff_of(kind: str, scope: SnapshotScope) -> datetime:
    """The instant ``kind`` is frozen at (A2-4)."""
    if CUTOFF_OF.get(kind) == "frozen_at":
        return scope.frozen_at or scope.known_at
    return scope.known_at


def scope_parameters(
    definition: Mapping[str, Any],
    scope: SnapshotScope,
    *,
    entity_code: str,
    period_key: str,
    known_at: datetime | None = None,
    period_bounds: tuple[date, date] | None = None,
) -> tuple[dict[str, Any], bool]:
    """The report parameters of a freeze (D4 / A1 / A2-5): the request a user would make for the
    lock's scope — entity code, book, the report's own period selector, ``known_at`` (the kind's
    cutoff) as UTC text — normalised exactly as ``framework._resolve`` does: ``PARAMETER_DEFAULTS``
    and ``False`` for boolean properties without a value (no JSON-schema default interpreter), the
    read basis from the supplied cutoff (``historical``), the closed schema guarded by
    ``parameter_errors`` — WITHOUT the caller's ``report.run`` scope filter. Returns (parameters,
    historical)."""
    code = str(definition["code"])
    kind = str(locked.snapshot_kind_of(code))
    schema: Mapping[str, Any] = definition["parameters_schema"]
    properties: Mapping[str, Any] = schema.get("properties", {})
    given: dict[str, Any] = {"entity_codes": [entity_code], "book": scope.book_code}
    if code in _PERIOD_KEY_REPORTS:
        given["period_key"] = period_key
    elif code in _DATE_RANGE_REPORTS:
        if period_bounds is None:
            raise SnapshotRefusal(kind, PERIOD_BOUNDS_MISSING.format(code=code))
        given["from_date"] = period_bounds[0].isoformat()  # the lock period's first day (§14)
        given["to_date"] = period_bounds[1].isoformat()  # … and its last day, inclusive
    else:
        given["from_period_key"] = period_key
        given["to_period_key"] = period_key
    given[framework.KNOWN_AT] = utc_text(known_at or scope.known_at)
    findings = framework.parameter_errors(schema, given)
    if findings:
        raise SnapshotRefusal(
            kind, FINDINGS.format(findings="; ".join(f"{f.field}: {f.message}" for f in findings))
        )
    parameters = dict(given)
    defaults = framework.PARAMETER_DEFAULTS.get(code, {})
    for key, spec in properties.items():
        if key in parameters:
            continue
        if key in defaults:
            parameters[key] = defaults[key]
        elif spec.get("type") == "boolean":
            parameters[key] = False
    basis, basis_findings = framework.resolve_basis(given, known_at_given=True)
    if basis_findings:
        raise SnapshotRefusal(
            kind, FINDINGS.format(findings="; ".join(f.message for f in basis_findings))
        )
    if framework.KNOWN_AT_BASIS in properties:
        parameters[framework.KNOWN_AT_BASIS] = basis
    return parameters, basis == framework.HISTORICAL_BASIS


def encode_report(kind: str, data: ReportData, *, drop_presentation_totals: bool) -> engine.Encoded:
    """D5 / A2-2 / A2-3: the engine's S15-R-18 encoding over the report's canonical cell texts —
    ``row_key`` first, every report column in report order, text kind. REQUIRED columns (the
    kind's key columns and currency column(s)) are read by name: a header or row lacking one, or
    an empty required cell outside ``EMPTY_KEY_ADMITTED[kind]``, refuses by name — so a builder
    states an inapplicable key component as None on its rows, never by leaving the field out — and
    a row whose ``ROW_IDENTITY[kind]`` components are all empty (a rollforward row that is neither
    a line row nor a by-contract row) refuses by name; optional cells
    encode None as "". A money cell whose currency differs from the row's bound currency column
    refuses by name. Presentation ``TOTAL:<ISO>`` rows are dropped for the wrapped reports (their
    totals are the control totals). The builder's control totals pass through verbatim. A4 13.1:
    every cell is the CANONICAL DS-FMT-25 text (``csv_output.canonical``) — identity and text
    cells carry the admitted value itself, never the spreadsheet-guarded display text (``=A`` and
    ``'=A`` are two contracts); the formula guard belongs to the export boundary
    (``locked.export_csv`` for the as-locked CSV), not to the frozen artefact."""
    required = REQUIRED.get(kind, ())
    admitted_empty = EMPTY_KEY_ADMITTED.get(kind, frozenset())
    header = {column.key for column in data.columns}
    missing_header = [column for column in required if column not in header]
    if missing_header:
        raise SnapshotRefusal(kind, HEADER_MISSING.format(columns=", ".join(missing_header)))
    bound_of = CURRENCY_OF.get(kind, {})
    columns = (
        engine.Column(engine.ROW_KEY, "text"),
        *(engine.Column(column.key, "text") for column in data.columns),
    )
    rows: list[dict[str, object]] = []
    for row in data.rows:
        row_key = str(row[ROW_KEY])
        if drop_presentation_totals and row_key.startswith(TOTAL_PREFIX):
            continue
        cells: dict[str, object] = {engine.ROW_KEY: row_key}
        for column in data.columns:
            if column.key in required:
                if column.key not in row:
                    raise SnapshotRefusal(
                        kind, COLUMN_MISSING.format(row_key=row_key, column=column.key)
                    )
                value = row[column.key]
                if value is None and column.key not in admitted_empty:
                    raise SnapshotRefusal(
                        kind, COLUMN_EMPTY.format(row_key=row_key, column=column.key)
                    )
            else:
                value = row.get(column.key)
            if column.kind == "money" and value is not None:
                bound = bound_of.get(column.key, "currency")
                expected = row.get(bound)
                if expected is not None and str(value["currency"]) != str(expected):
                    raise SnapshotRefusal(
                        kind,
                        CURRENCY_MISMATCH.format(
                            row_key=row_key,
                            column=column.key,
                            found=value["currency"],
                            bound=bound,
                            expected=expected,
                        ),
                    )
            cells[column.key] = csv_output.canonical(column, "value", value)  # raw (A4 13.1)
        identity = ROW_IDENTITY.get(kind, ())
        if identity and not any(cells[column] for column in identity):
            raise SnapshotRefusal(
                kind, IDENTITY_EMPTY.format(row_key=row_key, columns=", ".join(identity))
            )
        rows.append(cells)
    try:
        dataset = engine.Dataset(kind, columns, tuple(rows))
    except ValueError as exc:
        raise SnapshotRefusal(kind, NOT_A_DATASET.format(reason=exc)) from None
    return engine.encode(dataset, dict(data.control_totals))


def _entity_code(uow: UnitOfWork, kind: str, scope: SnapshotScope) -> str:
    code = uow.session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == scope.entity_id)
    ).scalar_one_or_none()
    if code is None:
        raise SnapshotRefusal(kind, ENTITY_MISSING.format(entity_id=scope.entity_id))
    return str(code)


def _period_key(uow: UnitOfWork, kind: str, scope: SnapshotScope) -> str:
    """The period's key, verified to lie on the lock entity's calendar (A2-5)."""
    key = uow.session.execute(
        select(period.c.period_key)
        .join(legal_entity, legal_entity.c.calendar_id == period.c.calendar_id)
        .where(period.c.id == scope.period_id, legal_entity.c.id == scope.entity_id)
    ).scalar_one_or_none()
    if key is None:
        raise SnapshotRefusal(kind, PERIOD_MISSING.format(period_id=scope.period_id))
    return str(key)


def _period_bounds(uow: UnitOfWork, kind: str, scope: SnapshotScope) -> tuple[date, date]:
    """The lock period's first and last day (SNAP-2, §14) — the `from_date` / `to_date` of a
    date-selected report; the period must lie on the lock entity's calendar (A2-5)."""
    row = uow.session.execute(
        select(period.c.start_date, period.c.end_date)
        .join(legal_entity, legal_entity.c.calendar_id == period.c.calendar_id)
        .where(period.c.id == scope.period_id, legal_entity.c.id == scope.entity_id)
    ).one_or_none()
    if row is None:
        raise SnapshotRefusal(kind, PERIOD_MISSING.format(period_id=scope.period_id))
    return row[0], row[1]


def _params(uow: UnitOfWork, kind: str, code: str, scope: SnapshotScope) -> ReportParams:
    """The builder parameters of a freeze of ``kind`` through report ``code``."""
    definition = framework.definition_row(uow.session, code)
    if definition is None:
        raise SnapshotRefusal(kind, DEFINITION_MISSING.format(code=code))
    entity_code = _entity_code(uow, kind, scope)
    period_key = _period_key(uow, kind, scope)
    cutoff = cutoff_of(kind, scope)
    bounds = _period_bounds(uow, kind, scope) if code in _DATE_RANGE_REPORTS else None
    parameters, historical = scope_parameters(
        definition,
        scope,
        entity_code=entity_code,
        period_key=period_key,
        known_at=cutoff,
        period_bounds=bounds,
    )
    return ReportParams(
        report_code=code,
        report_version=int(definition["version"]),
        parameters=MappingProxyType(parameters),
        entity_ids=(scope.entity_id,),
        known_at=cutoff,
        book_code=scope.book_code,
        as_of_date=None,
        period_lock_id=None,
        historical=historical,
    )


def _wrapped(kind: str, code: str) -> DatasetBuilder:
    """The eight wrapped kinds: the REAL builder's rows, presentation totals removed."""

    def build(uow: UnitOfWork, scope: SnapshotScope) -> engine.Encoded:
        params = _params(uow, kind, code, scope)
        data = framework.BUILDERS[code](uow, params)
        return encode_report(kind, data, drop_presentation_totals=True)

    build.__name__ = build.__qualname__ = f"freeze_{code}"
    return build


# --- WATERFALL: long form from the report's real population (A2-1) --------------------------------

WATERFALL_COLUMNS: Final[tuple[Column, ...]] = (
    Column("entity_code", "Entity", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("period_key", "Period", "code"),
    Column("currency", "Currency", "code"),
    Column("customer_name", "Customer", "text"),
    Column("product_code", "Product", "code"),
    Column("revenue_category", "Revenue category", "text"),
    Column("recognised", "Recognised", "money"),
    Column("scheduled", "Scheduled", "money"),
    Column("awaiting_trigger", "Awaiting trigger", "money"),
    Column("total", "Total", "money"),
)


def freeze_waterfall(uow: UnitOfWork, scope: SnapshotScope) -> engine.Encoded:
    """``WATERFALL`` at (entity, contract, obligation, period key): the obligations
    ``revenue_waterfall.population`` consumed for the lock's scope, one row per obligation and
    period key of the range with a non-zero recognised, scheduled or awaiting amount; the figures
    are the report's own per-obligation amounts (``_Obligation.recognized / scheduled / awaiting``).
    A snapshot is per LOCK PERIOD (Q6, D-98 139 amendment 3): the scope's one period is the whole
    range, ``awaiting_trigger`` (an obligation-level amount) sits on that period's row, and a range
    of any other length is refused by name — a multi-period WATERFALL snapshot does not exist.
    Control totals as the kinds table: row count and Σ recognised / scheduled / awaiting per
    currency."""
    params = _params(uow, "WATERFALL", waterfall_builder.CODE, scope)
    found = waterfall_builder.population(uow.session, params)
    period_keys = [key for bucket in found.buckets for key in bucket.period_keys]
    if len(period_keys) != 1:  # Q6 (D-98 139 amendment 3): a snapshot covers the lock's ONE period
        raise SnapshotRefusal("WATERFALL", MULTI_PERIOD.format(count=len(period_keys)))
    (only,) = period_keys
    rows: list[dict[str, Any]] = []
    recognised: dict[str, Decimal] = {}
    scheduled: dict[str, Decimal] = {}
    awaiting: dict[str, Decimal] = {}
    for ob in found.obligations:
        for key in period_keys:
            rec = ob.recognized.get(key, tie_outs.ZERO)
            sch = ob.scheduled.get(key, tie_outs.ZERO)
            wait = ob.awaiting  # the lock's single period carries the obligation-level amount
            if rec == 0 and sch == 0 and wait == 0:
                continue
            row: dict[str, Any] = {
                "entity_code": ob.entity_code,
                "contract_external_id": ob.external_id,
                "obligation_key": ob.obligation_key,
                "period_key": key,
                "currency": ob.currency,
                "customer_name": ob.customer_name,
                "product_code": ob.product_code,
                "revenue_category": ob.revenue_category,
                "recognised": tie_outs.money(rec, ob.currency),
                "scheduled": tie_outs.money(sch, ob.currency),
                "awaiting_trigger": tie_outs.money(wait, ob.currency),
                "total": tie_outs.money(rec + sch + wait, ob.currency),
            }
            row[ROW_KEY] = row_key_of("WATERFALL", row)  # A4 13.2: the encoded key tuple
            rows.append(row)
            tie_outs.add(recognised, ob.currency, rec)
            tie_outs.add(scheduled, ob.currency, sch)
            tie_outs.add(awaiting, ob.currency, wait)
    data = ReportData(
        columns=WATERFALL_COLUMNS,
        rows=tuple(rows),
        control_totals={
            "row_count": len(rows),
            "recognized_total": tie_outs.by_currency(recognised),
            "scheduled_total": tie_outs.by_currency(scheduled),
            "awaiting_trigger_total": tie_outs.by_currency(awaiting),
        },
    )
    return encode_report("WATERFALL", data, drop_presentation_totals=False)


# --- RPO: long form from the report's real population (A2-1) --------------------------------------


def _rpo_columns(bands: tuple[rpo_builder.Band, ...]) -> tuple[Column, ...]:
    return (
        Column("section", "Section", "integer"),
        Column("entity_code", "Entity", "code"),
        Column("contract_external_id", "Contract", "code"),
        Column("obligation_key", "Obligation", "code"),
        Column("customer_name", "Customer", "text"),
        Column("nature", "Nature of goods or services", "text"),
        Column("currency", "Currency", "code"),
        Column(rpo_builder.TOTAL, "Total", "money"),
        *(Column(band.key, band.key, "money") for band in bands),
        Column(rpo_builder.CURRENT, "Current", "money"),
        Column(rpo_builder.NONCURRENT, "Noncurrent", "money"),
        Column("expedient", "Expedient", "code"),
        Column("expedient_label", "Expedient name", "text"),
        Column("remaining_duration_months", "Remaining duration (months)", "integer"),
        Column("excluded_amount", "Excluded amount", "money"),
        Column("excluded_descriptor", "Excluded consideration", "text"),
    )


def freeze_rpo(uow: UnitOfWork, scope: SnapshotScope) -> engine.Encoded:
    """``RPO`` at (entity, contract, obligation): every obligation ``rpo._run`` found for the lock's
    scope — ordinary obligations (section 1) with the report's own ``_figures`` (total, the bands,
    current, noncurrent) and exempt obligations (section 2) with the excluded amount, expedient and
    remaining duration; ``section`` is a discriminator, never identity. The RPO-relief election
    hides nothing here (A2-2: the report hides elected entities' rows only for its JSON output);
    the elected entity codes are recorded in ``control_totals.rpo_relief_elected``. Control totals
    as the report's: as_of, bands, Σ total and Σ excluded per currency, plus the row count."""
    params = _params(uow, "RPO", rpo_builder.CODE, scope)
    session = uow.session
    run = rpo_builder._run(session, params)  # the report's own population and calculation
    bands = rpo_builder.bands_of(run.bands)
    labels = {pol: (label, description) for pol, _, label, description in rpo_builder.EXPEDIENTS}
    elected = sorted(
        entity.code
        for entity in run.entities
        if elections.entity_elections(
            session, entity_id=entity.id, book_code=run.book_code, known_at=params.known_at
        ).is_elected(elections.RPO_RELIEF)
    )
    rows: list[dict[str, Any]] = []
    actual: dict[str, Decimal] = {}
    excluded: dict[str, Decimal] = {}
    for item in run.found:
        ob = item.ob
        row: dict[str, Any] = {
            "entity_code": ob.entity_code,
            "contract_external_id": ob.external_id,
            "obligation_key": ob.obligation_key,
            "customer_name": ob.customer_name,
            "nature": ob.product_name,
            "currency": ob.currency,
        }
        row[ROW_KEY] = row_key_of("RPO", row)  # A4 13.2: the encoded key tuple
        if item.exemption is None:
            row["section"] = 1
            row.update(rpo_builder._figures([item], bands, ob.currency))
            tie_outs.add(actual, ob.currency, item.total)
        else:
            label, description = labels[item.exemption]
            row.update(
                {
                    "section": 2,
                    "expedient": item.exemption,
                    "expedient_label": label,
                    "remaining_duration_months": item.remaining_months,
                    "excluded_amount": tie_outs.money(item.total, ob.currency),
                    "excluded_descriptor": description,
                }
            )
            tie_outs.add(excluded, ob.currency, item.total)
        rows.append(row)
    days = sorted({day.isoformat() for day in run.as_of.values()})
    data = ReportData(
        columns=_rpo_columns(bands),
        rows=tuple(rows),
        control_totals={
            "row_count": len(rows),
            "as_of": days[0] if len(days) == 1 else days,
            "bands": [band.out() for band in bands],
            "total": tie_outs.by_currency(actual),
            "excluded_total": tie_outs.by_currency(excluded),
            "rpo_relief_elected": elected,
        },
    )
    return encode_report("RPO", data, drop_presentation_totals=False)


_LONG_FORM: Final[Mapping[str, DatasetBuilder]] = MappingProxyType(
    {"WATERFALL": freeze_waterfall, "RPO": freeze_rpo}
)

SNAPSHOT_DATASETS: Final[Mapping[str, DatasetBuilder]] = MappingProxyType(
    {
        kind: _LONG_FORM.get(kind) or _wrapped(kind, code)
        for code, kind in locked.SNAPSHOT_KIND_BY_REPORT.items()
        if code in framework.BUILDERS
    }
)


def dataset_for(kind: str) -> DatasetBuilder:
    """``SNAPSHOT_DATASETS[kind]``; the named dependency refusal for a register kind whose producer
    has not landed; a named refusal for a kind outside E-64."""
    builder = SNAPSHOT_DATASETS.get(kind)
    if builder is not None:
        return builder
    dependency = SNAPSHOT_DEPENDENCIES.get(kind)
    if dependency is not None:
        raise SnapshotDependencyMissing(dependency)
    raise SnapshotRefusal(kind, "not an E-64 snapshot kind")
