"""RPS-SNAP SNAP-1 CPU witnesses for `erev_api.domain.reports.snapshots` (design note
PRODUCTION-F-RPS-RPS-SNAP-DESIGN.md D1–D8, A1, A2; record §50). No database: the registry's shape
and its key contract against the re-lock consumer, the derived request parameters and their parity
with ``framework._resolve``, the S15-R-18 encoding with required / optional / currency semantics,
the long-form WATERFALL and RPO producers over fixed populations (one contract, TWO obligations →
two rows), the per-kind cutoff, and F-CLO's ``freeze_datasets`` refusing by name with the real
registry before any unit of work is touched."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.auth.principal import system_principal
from erev_api.domain.close import dependencies as close_dependencies
from erev_api.domain.close import relock_diff
from erev_api.domain.close import snapshots as close_snapshots
from erev_api.domain.reports import elections, framework, locked, snapshots, tie_outs
from erev_api.domain.reports.builders import contract_balance_rollforward as cbr_builder
from erev_api.domain.reports.builders import revenue_waterfall as waterfall_builder
from erev_api.domain.reports.builders import rpo as rpo_builder
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.domain.reports.outputs.sanitise import guard
from erev_engine.stages.s15_disclosures import snapshots as engine

K = datetime(2026, 9, 30, 23, 59, 59, 123456, tzinfo=UTC)
FREEZE = datetime(2026, 10, 2, 9, 0, 0, tzinfo=UTC)
US01 = uuid5(NAMESPACE_URL, "erev://tests/entity/US01")
P09 = uuid5(NAMESPACE_URL, "erev://tests/period/FY2026-P09")
SCOPE = snapshots.SnapshotScope(entity_id=US01, book_code="ASC606", period_id=P09, known_at=K)
DEPENDENT: tuple[str, ...] = ()  # twelve of twelve: F-CLO's manual_adjustment_register landed
ADAPTER_CODES = (
    "revenue_waterfall",
    "contract_balances",
    "contract_balance_rollforward",
    "rpo",
    "rpo_rollforward",
    "disaggregation",
    "revenue_from_prior_period_obligations",
    "contract_cost_rollforward",
    "je_population",
    "out_of_period_register",
    "modification_register",  # SNAP-2 (§14): DATE-selected by the lock period's bounds
    "manual_adjustment_register",  # F-CLO RPS-8 RPT-18: PERIOD-selected (from = to = the lock)
)
PERIOD_BOUNDS = (date(2026, 9, 1), date(2026, 9, 30))  # FY2026-P09 on the AVM-US calendar


def _money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


# --- shape and the key contract -----------------------------------------------------------------


def test_the_registry_covers_every_e64_kind_as_an_adapter_or_a_named_dependency() -> None:
    adapters, dependencies = set(snapshots.SNAPSHOT_DATASETS), set(snapshots.SNAPSHOT_DEPENDENCIES)
    assert adapters | dependencies == set(engine.SNAPSHOT_KINDS)
    assert not (adapters & dependencies) and dependencies == set(DEPENDENT)
    by_kind = {kind: code for code, kind in locked.SNAPSHOT_KIND_BY_REPORT.items()}
    assert adapters == {k for k, code in by_kind.items() if code in framework.BUILDERS}
    assert dependencies == {k for k, code in by_kind.items() if code not in framework.BUILDERS}
    assert snapshots.SNAPSHOT_DATASETS["WATERFALL"] is snapshots.freeze_waterfall
    assert snapshots.SNAPSHOT_DATASETS["RPO"] is snapshots.freeze_rpo
    for kind in adapters - {"WATERFALL", "RPO"}:
        assert snapshots.SNAPSHOT_DATASETS[kind].__name__ == f"freeze_{by_kind[kind]}"


def test_the_key_contract_equals_the_relock_consumers_for_all_twelve_kinds() -> None:
    """A2-1: the canonical grain is `close/relock_diff.KEY_COLUMNS`, restated and pinned."""
    for kind in engine.SNAPSHOT_KINDS:
        assert snapshots.KEY_COLUMNS[kind] == relock_diff.key_columns_of(kind), kind
        assert set(snapshots.KEY_COLUMNS[kind]) <= set(snapshots.REQUIRED[kind])
        assert set(snapshots.CURRENCY_COLUMNS[kind]) <= set(snapshots.REQUIRED[kind])
    assert snapshots.CURRENCY_COLUMNS["JE_POPULATION"] == ("txn_currency", "functional_currency")
    assert snapshots.CURRENCY_OF["JE_POPULATION"]["debit_functional"] == "functional_currency"


def test_dataset_for_returns_the_adapter_or_refuses_by_name() -> None:
    assert (
        snapshots.dataset_for("CONTRACT_BALANCES")
        is snapshots.SNAPSHOT_DATASETS["CONTRACT_BALANCES"]
    )
    # SNAP-2 and F-CLO RPS-8: both register producers landed — each kind resolves to its adapter
    assert (
        snapshots.dataset_for("MODIFICATION_REGISTER")
        is snapshots.SNAPSHOT_DATASETS["MODIFICATION_REGISTER"]
    )
    assert (
        snapshots.dataset_for("MANUAL_ADJUSTMENT_REGISTER")
        is snapshots.SNAPSHOT_DATASETS["MANUAL_ADJUSTMENT_REGISTER"]
    )
    assert snapshots.SNAPSHOT_DEPENDENCIES == {}
    with pytest.raises(snapshots.SnapshotRefusal) as unknown:
        snapshots.dataset_for("NOT_A_KIND")
    assert "NOT_A_KIND" in str(unknown.value)


def test_f_clo_freeze_refuses_by_name_a_registry_missing_one_kind_before_any_write() -> None:
    """Twelve of twelve: the real registry refuses nothing; the by-name refusal is proven against
    a registry with F-CLO's kind removed — exactly that kind is named, before any write."""
    engine_dep = close_dependencies.snapshot_engine()
    assert set(snapshots.SNAPSHOT_DATASETS) == set(engine.SNAPSHOT_KINDS)
    partial = {
        k: v for k, v in snapshots.SNAPSHOT_DATASETS.items() if k != "MANUAL_ADJUSTMENT_REGISTER"
    }
    with pytest.raises(close_dependencies.ProducerMissing) as refused:
        close_snapshots.freeze_datasets(
            None,  # type: ignore[arg-type]  # never reached: the kind check precedes every call
            US01,
            "ASC606",
            P09,
            K,
            registry=partial,
            scope_type=snapshots.SnapshotScope,
            engine=engine_dep,
        )
    assert refused.value.names == ("MANUAL_ADJUSTMENT_REGISTER",)
    assert refused.value.module == close_dependencies.SNAPSHOT_REGISTRY
    assert close_snapshots.NO_PARTIAL_MANIFEST in str(refused.value)


# --- the per-kind cutoff (A2-4) -------------------------------------------------------------------


def test_je_population_is_frozen_at_the_freeze_instant_and_every_other_kind_at_the_cutoff() -> None:
    with_freeze = snapshots.SnapshotScope(
        entity_id=US01, book_code="ASC606", period_id=P09, known_at=K, frozen_at=FREEZE
    )
    for kind in engine.SNAPSHOT_KINDS:
        expected = FREEZE if kind == "JE_POPULATION" else K
        assert snapshots.cutoff_of(kind, with_freeze) == expected, kind
        assert snapshots.cutoff_of(kind, SCOPE) == K, kind  # frozen_at None = the cutoff
    assert SCOPE.frozen_at is None


# --- the request a user would make (D4 / A1 / A2-5) and its parity with _resolve ------------------


def _definition(code: str) -> dict[str, Any]:
    from erev_api.domain.reports import catalogue

    row = catalogue.DEFINITIONS_BY_CODE[code]
    return {"code": code, "version": row.version, "parameters_schema": dict(row.parameters_schema)}


class _EntityRows:
    """A session stub for ``framework._resolve``: its only read outside a lock is the
    ``legal_entity`` (id, code) listing behind ``_in_scope_entities``."""

    def __init__(self, rows: list[tuple[Any, str]]) -> None:
        self.rows = rows

    def execute(self, statement: Any) -> _EntityRows:
        return self

    def tuples(self) -> list[tuple[Any, str]]:
        return self.rows


@pytest.mark.parametrize("code", ADAPTER_CODES)
def test_scope_parameters_equal_the_frameworks_resolution_for_an_in_scope_principal(
    code: str,
) -> None:
    """A1 / A2-5: the same parameters (exactly ``PARAMETER_DEFAULTS`` and false booleans — no
    schema-default interpreter), the microsecond-exact ``known_at``, the ``historical`` basis, the
    book and the lock's entity as ``_resolve`` yields for a principal whose scope holds the entity
    (a system principal has no scope entry: unrestricted)."""
    definition = _definition(code)
    parameters, historical = snapshots.scope_parameters(
        definition,
        SCOPE,
        entity_code="AVM-US",
        period_key="FY2026-P09",
        period_bounds=PERIOD_BOUNDS if code == "modification_register" else None,
    )
    if code in ("contract_balances", "rpo"):
        assert parameters["period_key"] == "FY2026-P09" and "from_period_key" not in parameters
    elif code == "modification_register":  # SNAP-2: the lock period's first / last day
        assert (parameters["from_date"], parameters["to_date"]) == ("2026-09-01", "2026-09-30")
        assert parameters["status"] == [
            "APPLIED",
            "APPROVED",
        ]  # PARAMETER_DEFAULTS (SCREENS_B RPT-14)
        assert parameters["currency_view"] == "transaction" and "from_period_key" not in parameters
    else:
        assert parameters["from_period_key"] == parameters["to_period_key"] == "FY2026-P09"
    assert parameters["known_at"] == "2026-09-30T23:59:59.123456Z" and historical is True
    assert parameters.get("period_lock_id") is None and "filters" not in parameters
    given = {
        k: v
        for k, v in parameters.items()
        if k
        in (
            "entity_codes",
            "book",
            "period_key",
            "from_period_key",
            "to_period_key",
            "from_date",
            "to_date",
            "known_at",
        )
    }
    uow = SimpleNamespace(
        session=_EntityRows([(US01, "AVM-US")]),
        principal=system_principal(uuid5(NAMESPACE_URL, "erev://tests/tenant")),
        now=FREEZE,
    )
    resolved, findings = framework._resolve(
        uow,  # type: ignore[arg-type]
        definition["parameters_schema"],
        given,
        code=code,
    )
    assert findings == [] and dict(resolved.parameters) == parameters
    assert (resolved.known_at, resolved.historical) == (K, True)
    assert resolved.entity_ids == (US01,) and resolved.book_code == "ASC606"
    assert resolved.as_of_date is None and resolved.period_lock_id is None


def test_a_date_selected_report_refuses_without_the_lock_periods_bounds() -> None:
    """SNAP-2 (§14): the modification register is selected by dates; without the period's bounds the
    adapter refuses by name rather than letting the builder default to the fiscal year to date."""
    with pytest.raises(snapshots.SnapshotRefusal) as refused:
        snapshots.scope_parameters(
            _definition("modification_register"),
            SCOPE,
            entity_code="AVM-US",
            period_key="FY2026-P09",
        )
    assert refused.value.kind == "MODIFICATION_REGISTER" and "bounds" in str(refused.value)


def test_scope_parameters_refuse_a_request_the_closed_schema_refuses() -> None:
    definition = _definition("contract_balances")
    definition["parameters_schema"] = {
        **definition["parameters_schema"],
        "properties": {
            k: v
            for k, v in definition["parameters_schema"]["properties"].items()
            if k != "known_at"
        },
    }
    with pytest.raises(snapshots.SnapshotRefusal) as refused:
        snapshots.scope_parameters(definition, SCOPE, entity_code="AVM-US", period_key="FY2026-P09")
    assert refused.value.kind == "CONTRACT_BALANCES" and "known_at" in str(refused.value)


# --- encoding (D5 / A2-2 / A2-3) ------------------------------------------------------------------

BALANCE_COLUMNS = (
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("entity_code", "Entity", "code"),
    Column("currency", "Currency", "code"),
    Column("contract_liability", "Contract liability", "money"),
    Column("is_open", "Open", "boolean"),
    Column("as_of", "As of", "date"),
    Column("line_count", "Lines", "integer"),
)
K01_ROW = {
    "row_key": "contract:K01:AVM-US",
    "contract_external_id": "K01",
    "customer_name": "Pellworth, Ltd.",  # a comma: the engine quotes it
    "entity_code": "AVM-US",
    "currency": "USD",
    "contract_liability": _money("29944.11"),
    "is_open": True,
    "as_of": date(2026, 9, 30),
    "line_count": 3,
}
TOTAL_ROW = {
    "row_key": "TOTAL:USD",
    "contract_external_id": None,
    "customer_name": None,
    "entity_code": None,
    "currency": "USD",
    "contract_liability": _money("29944.11"),
    "is_open": False,
    "as_of": None,
    "line_count": 0,
}
TOTALS = {"contract_liability": {"USD": "29944.11"}}


def test_encode_report_drops_presentation_totals_and_encodes_canonical_cell_texts() -> None:
    """D5 / Q7: row_key first, every report column in report order, text kind; money = the amount
    text; None = ""; booleans true / false; dates ISO; the TOTAL:<ISO> presentation row of a
    wrapped report is not a dataset row; the builder's control totals verbatim."""
    data = ReportData(columns=BALANCE_COLUMNS, rows=(K01_ROW, TOTAL_ROW), control_totals=TOTALS)
    encoded = snapshots.encode_report("CONTRACT_BALANCES", data, drop_presentation_totals=True)
    lines = encoded.content.decode("utf-8").split("\n")
    assert lines[0] == (
        "row_key,contract_external_id,customer_name,entity_code,currency,contract_liability,"
        "is_open,as_of,line_count"
    )
    assert (
        lines[1]
        == 'contract:K01:AVM-US,K01,"Pellworth, Ltd.",AVM-US,USD,29944.11,true,2026-09-30,3'
    )
    assert lines[2] == "" and encoded.row_count == 1
    assert encoded.control_totals == TOTALS
    keyed = relock_diff._keyed(
        "CONTRACT_BALANCES",
        *locked._rows(encoded.content),
        relock_diff.key_columns_of("CONTRACT_BALANCES"),
    )
    assert set(keyed) == {("AVM-US", "K01")}  # the re-lock consumer accepts the frozen shape


def test_encode_report_refuses_a_missing_or_empty_required_column_by_name() -> None:
    """A2-2: required = the key columns + the currency column(s); absent → refused by name;
    empty → refused unless the kind admits that component empty; optional None → ""."""
    lacking = {k: v for k, v in K01_ROW.items() if k != "entity_code"}
    with pytest.raises(snapshots.SnapshotRefusal) as absent:
        snapshots.encode_report(
            "CONTRACT_BALANCES",
            ReportData(columns=BALANCE_COLUMNS, rows=(lacking,), control_totals={}),
            drop_presentation_totals=True,
        )
    assert "lacks the required column entity_code" in str(absent.value)
    with pytest.raises(snapshots.SnapshotRefusal) as empty:
        snapshots.encode_report(
            "CONTRACT_BALANCES",
            ReportData(
                columns=BALANCE_COLUMNS,
                rows=({**K01_ROW, "contract_external_id": None},),
                control_totals={},
            ),
            drop_presentation_totals=True,
        )
    assert "required column contract_external_id is empty" in str(empty.value)
    no_currency = tuple(c for c in BALANCE_COLUMNS if c.key != "currency")
    with pytest.raises(snapshots.SnapshotRefusal) as header:
        snapshots.encode_report(
            "CONTRACT_BALANCES",
            ReportData(columns=no_currency, rows=(), control_totals={}),
            drop_presentation_totals=True,
        )
    assert "header lacks the required column(s) currency" in str(header.value)
    # a legitimately empty key component (a rollforward LINE row has no contract) is admitted
    line_columns = (
        Column("line_code", "Line code", "code"),
        Column("contract_external_id", "Contract", "code"),
        Column("currency", "Currency", "code"),
        Column("opening", "Opening", "money"),
    )
    line = {
        "row_key": "OPENING",
        "line_code": "OPENING",
        "contract_external_id": None,
        "currency": "USD",
        "opening": _money("1.00"),
    }
    encoded = snapshots.encode_report(
        "CONTRACT_BALANCE_ROLLFORWARD",
        ReportData(columns=line_columns, rows=(line,), control_totals={}),
        drop_presentation_totals=True,
    )
    assert encoded.content.decode().split("\n")[1] == "OPENING,OPENING,,USD,1.00"
    # optional cells: None → ""
    sparse = {**K01_ROW, "as_of": None, "customer_name": None}
    encoded = snapshots.encode_report(
        "CONTRACT_BALANCES",
        ReportData(columns=BALANCE_COLUMNS, rows=(sparse,), control_totals={}),
        drop_presentation_totals=True,
    )
    assert (
        encoded.content.decode().split("\n")[1]
        == "contract:K01:AVM-US,K01,,AVM-US,USD,29944.11,true,,3"
    )


# --- the two rollforwards: two row types under one key (04 T-CLS-05 dataset identity, D-98 85) ----

ROLLFORWARD_KINDS = ("CONTRACT_BALANCE_ROLLFORWARD", "RPO_ROLLFORWARD")
ROLLFORWARD_COLUMNS = (
    Column("line_code", "Line code", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("currency", "Currency", "code"),
    Column("opening", "Opening", "money"),
)


@pytest.mark.parametrize("kind", ROLLFORWARD_KINDS)
def test_a_rollforward_row_is_a_line_row_or_a_by_contract_row(kind: str) -> None:
    """A line row states ``contract_external_id`` empty and a by-contract row ``line_code``; each
    carries one of the two (``ROW_IDENTITY``). A row with neither has no identity and refuses by
    name; a row that leaves a key column OUT still refuses by name (S15-R-18: read by name — the
    shape the builders emitted until lane FIX-D2, which no populated rollforward survived)."""
    line = {
        "row_key": "OPENING",
        "line_code": "OPENING",
        "contract_external_id": None,
        "currency": "USD",
        "opening": _money("100.00"),
    }
    by_contract = {
        "row_key": "contract:K01",
        "line_code": None,
        "contract_external_id": "K01",
        "currency": "USD",
        "opening": _money("100.00"),
    }
    encoded = snapshots.encode_report(
        kind,
        ReportData(columns=ROLLFORWARD_COLUMNS, rows=(line, by_contract), control_totals={}),
        drop_presentation_totals=True,
    )
    assert encoded.content.decode().split("\n")[1:3] == [
        "OPENING,OPENING,,USD,100.00",
        "contract:K01,,K01,USD,100.00",
    ]
    keyed = relock_diff._keyed(
        kind, *locked._rows(encoded.content), relock_diff.key_columns_of(kind)
    )
    assert set(keyed) == {("OPENING", "", "USD"), ("", "K01", "USD")}
    assert snapshots.EMPTY_KEY_ADMITTED[kind] == frozenset(snapshots.ROW_IDENTITY[kind])
    assert set(snapshots.ROW_IDENTITY[kind]) < set(snapshots.KEY_COLUMNS[kind])
    for nameless in (None, ""):
        with pytest.raises(snapshots.SnapshotRefusal) as refused:
            snapshots.encode_report(
                kind,
                ReportData(
                    columns=ROLLFORWARD_COLUMNS,
                    rows=({**line, "row_key": "X", "line_code": nameless},),
                    control_totals={},
                ),
                drop_presentation_totals=True,
            )
        assert "row X: every identity column (line_code, contract_external_id) is empty" in str(
            refused.value
        )
    for left_out in ("contract_external_id", "line_code"):
        source = line if left_out == "contract_external_id" else by_contract
        lacking = {key: value for key, value in source.items() if key != left_out}
        with pytest.raises(snapshots.SnapshotRefusal) as absent:
            snapshots.encode_report(
                kind,
                ReportData(columns=ROLLFORWARD_COLUMNS, rows=(lacking,), control_totals={}),
                drop_presentation_totals=True,
            )
        assert f"lacks the required column {left_out}" in str(absent.value)


def _stub_rollforward_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """The database reads of the two rollforward builders replaced by fixed populations (two
    contracts, two currencies); the ROWS are still built by the builders' own ``build``."""
    lines = {
        line: dict.fromkeys(tie_outs.ROLLFORWARD_BALANCES, Decimal(0)) for line in cbr_builder.LINES
    }
    balances = tuple(
        cbr_builder.ContractRollforward(
            contract_id=uuid5(NAMESPACE_URL, f"erev://tests/contract/{external_id}"),
            external_id=external_id,
            customer_name="Pellworth, Ltd.",
            entity_id=US01,
            entity_code="AVM-US",
            currency=currency,
            lines={
                **lines,
                "OPENING": {**lines["OPENING"], cbr_builder.LIABILITY: Decimal(opening)},
                "CLOSING": {**lines["CLOSING"], cbr_builder.LIABILITY: Decimal(closing)},
            },
        )
        for external_id, currency, opening, closing in (
            ("K01", "USD", "100.00", "60.00"),
            ("=K02", "EUR", "0", "40.00"),
        )
    )
    rpo_lines = tuple(
        rpo_builder.ContractLines(
            external_id=item.external_id,
            customer_name=item.customer_name,
            entity_code=item.entity_code,
            currency=item.currency,
            lines={
                **dict.fromkeys(rpo_builder.ROLLFORWARD_LINES, Decimal(0)),
                "OPENING": item.lines["OPENING"][cbr_builder.LIABILITY],
                "CLOSING": item.lines["CLOSING"][cbr_builder.LIABILITY],
            },
        )
        for item in balances
    )
    monkeypatch.setattr(tie_outs, "book_of", lambda session, params: "ASC606")
    monkeypatch.setattr(tie_outs, "contract_named", lambda session, params: None)
    monkeypatch.setattr(tie_outs, "cutoff_for", lambda session, params: K)
    monkeypatch.setattr(tie_outs, "balances_at", lambda session, **_: ())
    monkeypatch.setattr(cbr_builder, "ranges", lambda session, params: ((), {}, {}))
    monkeypatch.setattr(cbr_builder, "rollforwards", lambda session, **_: balances)
    monkeypatch.setattr(rpo_builder, "load", lambda session, **_: None)
    # S15-R-08 rev 1.127 (RPT-ASOF-FIGURES-1): the builder reads its obligations at its dates
    monkeypatch.setattr(rpo_builder, "measure", lambda session, store, days: None)
    monkeypatch.setattr(rpo_builder, "applied_expedients", lambda session, found, **_: {})
    monkeypatch.setattr(rpo_builder, "rollforward_lines", lambda store, **_: rpo_lines)
    monkeypatch.setattr(rpo_builder, "rows_at", lambda store, **_: ())


@pytest.mark.parametrize(
    ("kind", "code", "line_codes"),
    [
        ("CONTRACT_BALANCE_ROLLFORWARD", "contract_balance_rollforward", cbr_builder.LINES),
        ("RPO_ROLLFORWARD", "rpo_rollforward", rpo_builder.ROLLFORWARD_LINES),
    ],
)
def test_a_populated_rollforward_freezes_from_the_real_builders_rows(
    monkeypatch: pytest.MonkeyPatch, kind: str, code: str, line_codes: tuple[str, ...]
) -> None:
    """Supervisor ruling R-4 (2026-09-29; P1): the registered adapter over the builder's OWN rows of
    a populated range — line rows and by-contract rows, two currencies — freezes, every row under
    the governed key (``line_code``, ``contract_external_id``, ``currency``) with the other row
    type's component empty, and the re-lock consumer accepts it. Fail-first: the builders left the
    inapplicable key column out of the row, so ``encode_report`` refused the first line row by name
    (``row OPENING:EUR lacks the required column contract_external_id``) and every period lock
    with contract-balance activity failed."""
    _stub_params(monkeypatch, code)
    _stub_rollforward_reads(monkeypatch)
    uow = SimpleNamespace(session=None)
    built = framework.BUILDERS[code](uow, snapshots._params(uow, kind, code, SCOPE))  # type: ignore[arg-type]
    assert built.rows and all(set(snapshots.REQUIRED[kind]) <= set(row) for row in built.rows)
    encoded = snapshots.SNAPSHOT_DATASETS[kind](uow, SCOPE)  # type: ignore[arg-type]
    headers, rows = locked._rows(encoded.content)
    assert encoded.row_count == len(rows) == 2 * len(line_codes) + 2
    keyed = relock_diff._keyed(kind, headers, rows, relock_diff.key_columns_of(kind))
    assert set(keyed) == {
        *((line, "", currency) for line in line_codes for currency in ("EUR", "USD")),
        ("", "K01", "USD"),
        ("", "=K02", "EUR"),  # raw identity (A4 13.1): never the export-guarded text
    }
    by_section = {row["section"] for row in rows}
    assert by_section == {"1", "2"}
    for row in rows:
        is_line = row["section"] == "1"
        assert (
            bool(row["line_code"]) is is_line and bool(row["contract_external_id"]) is not is_line
        )
    assert keyed[("OPENING", "", "USD")]["currency"] == "USD"
    assert keyed[("", "K01", "USD")]["opening"] == "100.00"
    assert keyed[("", "K01", "USD")]["closing"] == "60.00"
    assert encoded.control_totals == built.control_totals


def test_encode_report_refuses_a_money_cell_whose_currency_differs_from_the_bound_column() -> None:
    """A2-3: the row's currency column IS the money cells' currency identity."""
    with pytest.raises(snapshots.SnapshotRefusal) as mismatch:
        snapshots.encode_report(
            "CONTRACT_BALANCES",
            ReportData(
                columns=BALANCE_COLUMNS,
                rows=({**K01_ROW, "contract_liability": _money("1.00", "EUR")},),
                control_totals={},
            ),
            drop_presentation_totals=True,
        )
    assert "contract_liability is in EUR but currency is USD" in str(mismatch.value)
    je_columns = (
        Column("entity_code", "Entity", "code"),
        Column("book", "Book", "code"),
        Column("je_no", "JE", "code"),
        Column("line_no", "Line", "integer"),
        Column("txn_currency", "Txn currency", "code"),
        Column("functional_currency", "Functional currency", "code"),
        Column("debit_txn", "Debit", "money"),
        Column("debit_functional", "Debit (functional)", "money"),
    )
    je = {
        "row_key": "line:JE-1:1",
        "entity_code": "AVM-DE",
        "book": "ASC606",
        "je_no": "JE-1",
        "line_no": 1,
        "txn_currency": "EUR",
        "functional_currency": "USD",
        "debit_txn": _money("10.00", "EUR"),
        "debit_functional": _money("11.00", "USD"),
    }
    encoded = snapshots.encode_report(
        "JE_POPULATION",
        ReportData(columns=je_columns, rows=(je,), control_totals={}),
        drop_presentation_totals=True,
    )
    assert (
        encoded.content.decode().split("\n")[1]
        == "line:JE-1:1,AVM-DE,ASC606,JE-1,1,EUR,USD,10.00,11.00"
    )


def test_encode_report_refuses_a_repeated_row_key_by_name() -> None:
    with pytest.raises(snapshots.SnapshotRefusal) as refused:
        snapshots.encode_report(
            "CONTRACT_BALANCES",
            ReportData(columns=BALANCE_COLUMNS, rows=(K01_ROW, K01_ROW), control_totals={}),
            drop_presentation_totals=True,
        )
    assert "duplicate row_key" in str(refused.value)


def test_the_frozen_bytes_round_trip_through_the_as_locked_reader() -> None:
    data = ReportData(columns=BALANCE_COLUMNS, rows=(K01_ROW, TOTAL_ROW), control_totals=TOTALS)
    encoded = snapshots.encode_report("CONTRACT_BALANCES", data, drop_presentation_totals=True)
    dataset = locked.LockedDataset(
        lock_id=uuid5(NAMESPACE_URL, "erev://tests/lock/1"),
        kind="CONTRACT_BALANCES",
        file_id=uuid5(NAMESPACE_URL, "erev://tests/file/1"),
        file_sha256=encoded.file_sha256,
        row_count=encoded.row_count,
        control_totals=dict(encoded.control_totals),
        content=encoded.content,
    )
    shown = locked.report_data(locked.verify(dataset))
    assert [c.key for c in shown.columns] == [c.key for c in BALANCE_COLUMNS]
    assert [row["row_key"] for row in shown.rows] == ["contract:K01:AVM-US"]
    assert shown.rows[0]["contract_liability"] == "29944.11"


# --- long-form WATERFALL and RPO from the builders' real populations (A2-1) -----------------------


def _obligation(
    external_id: str,
    obligation_key: str,
    recognized: dict[str, str],
    scheduled: dict[str, str],
    awaiting: str,
) -> Any:
    return waterfall_builder._Obligation(
        version_row_id=uuid5(NAMESPACE_URL, f"erev://tests/v/{external_id}/{obligation_key}"),
        obligation_id=uuid5(NAMESPACE_URL, f"erev://tests/ob/{external_id}/{obligation_key}"),
        external_id=external_id,
        obligation_key=obligation_key,
        line_sequence=1,
        product_code="PLATFORM",
        revenue_category="SUBSCRIPTION",
        customer_name="Pellworth, Ltd.",
        entity_id=US01,
        entity_code="AVM-US",
        currency="USD",
        awaiting=Decimal(awaiting),
        recognized={k: Decimal(v) for k, v in recognized.items()},
        scheduled={k: Decimal(v) for k, v in scheduled.items()},
    )


def _stub_params(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    """The adapters' DB reads (definition, entity code, period key) replaced by the fixture's."""
    monkeypatch.setattr(
        framework, "definition_row", lambda session, c, version=None: _definition(c)
    )
    monkeypatch.setattr(snapshots, "_entity_code", lambda uow, kind, scope: "AVM-US")
    monkeypatch.setattr(snapshots, "_period_key", lambda uow, kind, scope: "FY2026-P09")
    monkeypatch.setattr(snapshots, "_period_bounds", lambda uow, kind, scope: PERIOD_BOUNDS)


def test_waterfall_is_frozen_long_form_one_row_per_obligation_and_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2-1: one contract with TWO obligations → two rows at (entity, contract, obligation,
    period_key) with the report's per-obligation figures; the currency column always present;
    awaiting_trigger on the lock's single period; the re-lock consumer accepts the header."""
    _stub_params(monkeypatch, "revenue_waterfall")
    obligations = (
        _obligation("K01", "OB-1", {"FY2026-P09": "100.00"}, {"FY2026-P09": "25.00"}, "0"),
        _obligation("K01", "OB-2", {"FY2026-P09": "0"}, {"FY2026-P09": "40.00"}, "5.00"),
        _obligation("K02", "OB-1", {}, {}, "0"),  # nothing in the range: no row
    )
    population = waterfall_builder.Population(
        book_code="ASC606",
        obligations=obligations,
        buckets=(waterfall_builder._Bucket("FY2026-P09", "September 2026", ("FY2026-P09",)),),
        period_ids=(P09,),
        entity_ids=(US01,),
        restricted=False,
    )
    monkeypatch.setattr(waterfall_builder, "population", lambda session, params: population)
    encoded = snapshots.freeze_waterfall(SimpleNamespace(session=None), SCOPE)  # type: ignore[arg-type]
    headers, rows = locked._rows(encoded.content)
    assert headers[:5] == [
        "row_key",
        "entity_code",
        "contract_external_id",
        "obligation_key",
        "period_key",
    ]
    assert encoded.row_count == 2 and [r["obligation_key"] for r in rows] == ["OB-1", "OB-2"]
    assert [r["currency"] for r in rows] == ["USD", "USD"]
    assert [(r["recognised"], r["scheduled"], r["awaiting_trigger"], r["total"]) for r in rows] == [
        ("100.00", "25.00", "0.00", "125.00"),
        ("0.00", "40.00", "5.00", "45.00"),
    ]
    keyed = relock_diff._keyed("WATERFALL", headers, rows, relock_diff.key_columns_of("WATERFALL"))
    assert set(keyed) == {
        ("AVM-US", "K01", "OB-1", "FY2026-P09"),
        ("AVM-US", "K01", "OB-2", "FY2026-P09"),
    }
    assert encoded.control_totals == {
        "row_count": 2,
        "recognized_total": {"USD": "100.00"},
        "scheduled_total": {"USD": "65.00"},
        "awaiting_trigger_total": {"USD": "5.00"},
    }


def test_waterfall_refuses_a_multi_period_range_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Q6 (D-98 139 amendment 3): a snapshot is per lock period — a range that resolves to two
    periods is refused by name, never encoded with an overloaded awaiting_trigger placement."""
    _stub_params(monkeypatch, "revenue_waterfall")
    population = waterfall_builder.Population(
        book_code="ASC606",
        obligations=(_obligation("K01", "OB-1", {"FY2026-P08": "1.00"}, {}, "0"),),
        buckets=(
            waterfall_builder._Bucket("FY2026-P08", "August 2026", ("FY2026-P08",)),
            waterfall_builder._Bucket("FY2026-P09", "September 2026", ("FY2026-P09",)),
        ),
        period_ids=(P09,),
        entity_ids=(US01,),
        restricted=False,
    )
    monkeypatch.setattr(waterfall_builder, "population", lambda session, params: population)
    with pytest.raises(snapshots.SnapshotRefusal) as refused:
        snapshots.freeze_waterfall(SimpleNamespace(session=None), SCOPE)  # type: ignore[arg-type]
    assert refused.value.kind == "WATERFALL" and "resolved to 2 periods" in str(refused.value)


def _rpo_item(
    external_id: str,
    obligation_key: str,
    total: str,
    placed: tuple[str, ...],
    current: str,
    exemption: str | None = None,
) -> Any:
    ob = rpo_builder._Ob(
        row_id=uuid5(NAMESPACE_URL, f"erev://tests/row/{external_id}/{obligation_key}"),
        version_id=uuid5(NAMESPACE_URL, f"erev://tests/v/{external_id}"),
        obligation_id=uuid5(NAMESPACE_URL, f"erev://tests/ob/{external_id}/{obligation_key}"),
        contract_id=uuid5(NAMESPACE_URL, f"erev://tests/c/{external_id}"),
        external_id=external_id,
        obligation_key=obligation_key,
        product_name="Platform subscription",
        product_family="Platform",
        customer_name="Pellworth, Ltd.",
        customer_segment="Enterprise",
        entity_id=US01,
        entity_code="AVM-US",
        currency="USD",
        recognition_method="RATABLE",
        end_date=None,
        inception=date(2026, 1, 1),
        allocated=Decimal(total),
        cancelled=False,
    )
    return rpo_builder.ObligationRpo(
        ob=ob,
        as_of=date(2026, 9, 30),
        total=Decimal(total),
        placed=tuple(Decimal(p) for p in placed),
        current=Decimal(current),
        contributors=(),
        exemption=exemption,
        remaining_months=6,
    )


def test_rpo_is_frozen_long_form_one_row_per_obligation_with_exempt_rows_and_no_hiding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2-1 / A2-2: ordinary and exempt obligations of one contract are two rows keyed (entity,
    contract, obligation); `section` discriminates; the elected RPO relief hides nothing (it is
    recorded in control_totals); the re-lock consumer accepts the header."""
    _stub_params(monkeypatch, "rpo")
    items = (
        _rpo_item("K01", "OB-1", "300.00", ("100.00", "200.00", "0"), "100.00"),
        _rpo_item(
            "K01", "OB-2", "50.00", ("0", "0", "0"), "0", exemption=rpo_builder.EXPEDIENTS[0][0]
        ),
    )
    run = rpo_builder._Run(
        book_code="ASC606",
        entities=(SimpleNamespace(id=US01, code="AVM-US"),),  # type: ignore[arg-type]
        as_of={US01: date(2026, 9, 30)},
        period_starts={US01: date(2026, 9, 1)},
        bands=(12, 24),
        store=None,  # type: ignore[arg-type]
        applied={},
        found=items,
    )
    monkeypatch.setattr(rpo_builder, "_run", lambda session, params: run)
    monkeypatch.setattr(
        elections,
        "entity_elections",
        lambda session, *, entity_id, book_code, known_at: SimpleNamespace(
            is_elected=lambda code: True
        ),
    )
    encoded = snapshots.freeze_rpo(SimpleNamespace(session=None), SCOPE)  # type: ignore[arg-type]
    headers, rows = locked._rows(encoded.content)
    assert encoded.row_count == 2 and [r["section"] for r in rows] == ["1", "2"]
    ordinary, exempt = rows
    assert (
        ordinary["total"],
        ordinary["within_12_months"],
        ordinary["months_13_to_24"],
        ordinary["current"],
    ) == ("300.00", "100.00", "200.00", "100.00")
    assert ordinary["excluded_amount"] == "" and exempt["total"] == ""  # legitimate sparse cells
    assert (
        exempt["expedient"],
        exempt["excluded_amount"],
        exempt["remaining_duration_months"],
    ) == (rpo_builder.EXPEDIENTS[0][0], "50.00", "6")
    keyed = relock_diff._keyed("RPO", headers, rows, relock_diff.key_columns_of("RPO"))
    assert set(keyed) == {("AVM-US", "K01", "OB-1"), ("AVM-US", "K01", "OB-2")}
    assert encoded.control_totals["total"] == {"USD": "300.00"}
    assert encoded.control_totals["excluded_total"] == {"USD": "50.00"}
    assert encoded.control_totals["rpo_relief_elected"] == [
        "AVM-US"
    ]  # recorded, never a row filter
    assert (
        encoded.control_totals["as_of"] == "2026-09-30" and encoded.control_totals["row_count"] == 2
    )


# --- A4 13.1 / 13.2 (Codex 1653): raw identity, injective row keys --------------------------------

ID1_PAIR = ("=A", "'=A")  # the guard would merge them: both admitted, both distinct contracts
ID2_PAIR = (("A:B", "C"), ("A", "B:C"))  # an unescaped ``:`` join would merge them


def _balance_row(external_id: str) -> dict[str, Any]:
    return {
        **K01_ROW,
        "row_key": f"contract:{external_id}:AVM-US",
        "contract_external_id": external_id,
    }


def test_identity_cells_are_raw_and_distinct_for_ids_the_export_guard_would_merge() -> None:
    """A4 13.1 (Codex 1653 ID-1): the frozen artefact carries the admitted value itself — `=A` and
    `'=A` are two rows for the re-lock consumer; the live CSV export still guards them (its text is
    `guard(canonical)`), so the defence moved to the export boundary, it did not disappear."""
    data = ReportData(
        columns=BALANCE_COLUMNS,
        rows=tuple(_balance_row(external_id) for external_id in ID1_PAIR),
        control_totals=TOTALS,
    )
    encoded = snapshots.encode_report("CONTRACT_BALANCES", data, drop_presentation_totals=True)
    headers, rows = locked._rows(encoded.content)
    assert [r["contract_external_id"] for r in rows] == ["'=A", "=A"]  # sorted by row key; RAW
    keyed = relock_diff._keyed(
        "CONTRACT_BALANCES", headers, rows, relock_diff.key_columns_of("CONTRACT_BALANCES")
    )
    assert set(keyed) == {("AVM-US", "=A"), ("AVM-US", "'=A")}
    column = BALANCE_COLUMNS[0]
    assert csv_output.canonical(column, "value", "=A") == "=A"
    assert csv_output.cell(column, "value", "=A") == "'=A" == guard("=A")  # the live export


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (Column("c", "C", "code"), "=A"),
        (Column("t", "T", "text"), "+1"),
        (Column("l", "L", "codes"), ["-x", "y"]),
        (Column("a", "A", "actor"), {"display_name": "@maya"}),
        (Column("m", "M", "money"), {"amount": "-5.00", "currency": "USD"}),
        (Column("i", "I", "integer"), -3),
        (Column("d", "D", "decimal"), Decimal("-0.5")),
        (Column("as_of", "As of", "date"), date(2026, 9, 30)),
        (Column("b", "B", "boolean"), True),
        (Column("c", "C", "code"), None),
    ],
)
def test_cell_is_canonical_plus_the_guard_for_text_kinds_and_canonical_alone_otherwise(
    column: Column, value: Any
) -> None:
    canonical = csv_output.canonical(column, "value", value)
    cell = csv_output.cell(column, "value", value)
    if value is None or column.kind in csv_output.MACHINE_KINDS:
        assert cell == canonical  # numeric / date / flag cells never pass the guard (DS-FMT-25)
    else:
        assert cell == guard(canonical)
    assert csv_output.cell(column, "currency", {"currency": "=X"}) == "'=X"
    assert csv_output.canonical(column, "currency", {"currency": "=X"}) == "=X"


def test_declared_kinds_follow_the_builders_tables_and_the_dynamic_rules() -> None:
    """A4 13.1 (b) / Codex 1739 §3 (c): every frozen column has a DECLARED kind — text kinds are
    guarded at the export boundary, machine kinds never; RPO time bands and DISAGGREGATION
    `period:` columns are money by rule; an undeclared header is text."""
    waterfall = snapshots.declared_kinds(
        "WATERFALL", ["row_key", *(c.key for c in snapshots.WATERFALL_COLUMNS), "mystery"]
    )
    assert waterfall["row_key"] == "text" and waterfall["recognised"] == "money"
    assert waterfall["contract_external_id"] == "code" and waterfall["mystery"] == "text"
    bands = {"bands": [{"key": "within_12_months"}, {"key": "after_12_months"}]}  # bound metadata
    rpo = snapshots.declared_kinds(
        "RPO",
        ["row_key", "section", "within_12_months", "after_12_months", "mystery", "currency"],
        bands,
    )
    assert (rpo["section"], rpo["within_12_months"], rpo["after_12_months"]) == (
        "integer",
        "money",
        "money",
    )
    assert (rpo["mystery"], rpo["currency"]) == (
        "text",
        "code",
    )  # RPS-TYPE-RPO-1: never money by default
    assert (
        snapshots.declared_kinds("RPO", ["months_13_to_24"])["months_13_to_24"] == "text"
    )  # unbound
    dis = snapshots.declared_kinds("DISAGGREGATION", ["dimension_value", "period:FY2026-P09", "x"])
    assert (dis["dimension_value"], dis["period:FY2026-P09"], dis["x"]) == ("code", "money", "text")
    balances = snapshots.declared_kinds(
        "CONTRACT_BALANCES", ["contract_liability", "customer_name"]
    )
    assert (balances["contract_liability"], balances["customer_name"]) == ("money", "text")
    for kind in ("JE_POPULATION", "OUT_OF_PERIOD_REGISTER", "COST_ROLLFORWARD"):
        assert set(snapshots.declared_kinds(kind, ["row_key"]).values()) == {"text"}
    modreg = snapshots.declared_kinds(  # SNAP-2: F-CTR's COLUMNS declare the eleventh kind
        "MODIFICATION_REGISTER",
        ["tp_change", "catch_up_amount", "effective_date", "treatment_override", "reference", "x"],
    )
    assert (modreg["tp_change"], modreg["catch_up_amount"]) == ("money", "money")
    assert (modreg["effective_date"], modreg["treatment_override"]) == ("date", "boolean")
    assert (modreg["reference"], modreg["x"]) == ("text", "text")
    mar = snapshots.declared_kinds(  # F-CLO RPS-8 RPT-18: the twelfth kind from its COLUMNS
        "MANUAL_ADJUSTMENT_REGISTER",
        ["amount_functional_abs", "effective_date", "approved_at", "attachment_count", "memo", "x"],
    )
    assert (mar["amount_functional_abs"], mar["effective_date"]) == ("money", "date")
    assert (mar["approved_at"], mar["attachment_count"]) == ("timestamp", "integer")
    assert (mar["memo"], mar["x"]) == ("text", "text")


def test_an_unknown_rpo_header_is_text_and_guarded_at_the_export_beside_real_band_positives() -> (
    None
):
    """Codex 1824 §2 (RPS-TYPE-RPO-1): the money exemption of an RPO frozen dataset covers ONLY the
    bands bound in its control totals; an unknown header holding `=A` is text and guarded at the
    export boundary, while the bound band's `-5.00` follows the numeric branch."""
    columns = tuple(
        engine.Column(key, "text")
        for key in (
            "row_key",
            "entity_code",
            "contract_external_id",
            "obligation_key",
            "mystery",
            "within_12_months",
            "currency",
        )
    )
    rows = (
        {
            "row_key": "obligation:AVM-US:K01:OB-1",
            "entity_code": "AVM-US",
            "contract_external_id": "K01",
            "obligation_key": "OB-1",
            "mystery": "=A",
            "within_12_months": "-5.00",
            "currency": "USD",
        },
    )
    encoded = engine.encode(
        engine.Dataset("RPO", columns, rows), {"bands": [{"key": "within_12_months"}]}
    )
    dataset = locked.LockedDataset(
        lock_id=uuid5(NAMESPACE_URL, "erev://tests/lock/rpo"),
        kind="RPO",
        file_id=uuid5(NAMESPACE_URL, "erev://tests/file/rpo"),
        file_sha256=encoded.file_sha256,
        row_count=encoded.row_count,
        control_totals=dict(encoded.control_totals),
        content=encoded.content,
    )
    kinds = snapshots.declared_kinds("RPO", locked.headers_of(dataset), dataset.control_totals)
    assert (kinds["mystery"], kinds["within_12_months"]) == ("text", "money")
    content, sha256 = locked.export_csv(dataset, kinds)
    cells = content.decode("utf-8").split("\n")[1].split(",")
    assert (cells[4], cells[5]) == ("'=A", "-5.00")  # unknown header guarded; bound band numeric
    assert sha256 != encoded.file_sha256 and b",=A," in encoded.content  # the artefact stays raw


def test_decode_row_key_inverts_the_cv21_encoding_for_every_table_character() -> None:
    row = {
        "entity_code": "AVM-US",
        "contract_external_id": "a%b/c@d#e:f|g",
        "obligation_key": "B:C",
        "period_key": "FY2026-P09",
    }
    key = snapshots.row_key_of("WATERFALL", row)
    assert key.startswith(snapshots.ROW_KEY_PREFIX) and key.count(":") == 4  # only the joiners
    assert snapshots.decode_row_key(key) == ("AVM-US", "a%b/c@d#e:f|g", "B:C", "FY2026-P09")
    with pytest.raises(ValueError):
        snapshots.decode_row_key("contract:K01:AVM-US")


def test_waterfall_keeps_both_collision_pairs_as_four_distinct_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A4 13.2 / 13.1 through the ACTUAL adapter: `(A:B, C)` and `(A, B:C)` are two row keys and
    two identity tuples; `=A` and `'=A` are two raw contracts; the re-lock consumer accepts all
    four (Codex 1653 C1 / C2: no false refusal of admitted rows)."""
    _stub_params(monkeypatch, "revenue_waterfall")
    obligations = tuple(
        _obligation(external_id, key, {"FY2026-P09": "10.00"}, {}, "0")
        for external_id, key in (*ID2_PAIR, *((c, "POB1") for c in ID1_PAIR))
    )
    population = waterfall_builder.Population(
        book_code="ASC606",
        obligations=obligations,
        buckets=(waterfall_builder._Bucket("FY2026-P09", "September 2026", ("FY2026-P09",)),),
        period_ids=(P09,),
        entity_ids=(US01,),
        restricted=False,
    )
    monkeypatch.setattr(waterfall_builder, "population", lambda session, params: population)
    encoded = snapshots.freeze_waterfall(SimpleNamespace(session=None), SCOPE)  # type: ignore[arg-type]
    headers, rows = locked._rows(encoded.content)
    assert encoded.row_count == 4 and len({r["row_key"] for r in rows}) == 4
    keyed = relock_diff._keyed("WATERFALL", headers, rows, relock_diff.key_columns_of("WATERFALL"))
    assert set(keyed) == {
        ("AVM-US", "A:B", "C", "FY2026-P09"),
        ("AVM-US", "A", "B:C", "FY2026-P09"),
        ("AVM-US", "=A", "POB1", "FY2026-P09"),
        ("AVM-US", "'=A", "POB1", "FY2026-P09"),
    }
    for key, row in keyed.items():
        assert snapshots.decode_row_key(str(row["row_key"])) == key  # the key IS the tuple
    assert encoded.control_totals["recognized_total"] == {"USD": "40.00"}


def test_rpo_keeps_both_collision_pairs_as_four_distinct_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_params(monkeypatch, "rpo")
    items = tuple(
        _rpo_item(external_id, key, "100.00", ("100.00", "0", "0"), "100.00")
        for external_id, key in (*ID2_PAIR, *((c, "POB1") for c in ID1_PAIR))
    )
    run = rpo_builder._Run(
        book_code="ASC606",
        entities=(SimpleNamespace(id=US01, code="AVM-US"),),  # type: ignore[arg-type]
        as_of={US01: date(2026, 9, 30)},
        period_starts={US01: date(2026, 9, 1)},
        bands=(12, 24),
        store=None,  # type: ignore[arg-type]
        applied={},
        found=items,
    )
    monkeypatch.setattr(rpo_builder, "_run", lambda session, params: run)
    monkeypatch.setattr(
        elections,
        "entity_elections",
        lambda session, *, entity_id, book_code, known_at: SimpleNamespace(
            is_elected=lambda code: False
        ),
    )
    encoded = snapshots.freeze_rpo(SimpleNamespace(session=None), SCOPE)  # type: ignore[arg-type]
    headers, rows = locked._rows(encoded.content)
    keyed = relock_diff._keyed("RPO", headers, rows, relock_diff.key_columns_of("RPO"))
    assert encoded.row_count == 4 and set(keyed) == {
        ("AVM-US", "A:B", "C"),
        ("AVM-US", "A", "B:C"),
        ("AVM-US", "=A", "POB1"),
        ("AVM-US", "'=A", "POB1"),
    }
    for key, row in keyed.items():
        assert snapshots.decode_row_key(str(row["row_key"])) == key
    assert encoded.control_totals["total"] == {"USD": "400.00"}


def test_a_frozen_modification_register_preserves_status_per_row() -> None:
    """FROZEN-MODREG-PREVIEW-1 (supervisor engineering ruling on F-CTR's flag): the adapter keeps
    F-CTR's status defaults (APPLIED + APPROVED); an APPROVED row's figures come from the stored
    impact preview, so the frozen dataset must carry `status` (and `impact_preview_sha256`) per row
    — a preview-based row is identifiable in the snapshot."""
    from erev_api.domain.reports.builders import modification_register as modreg

    def row(no: str, status: str, preview: str | None) -> dict[str, Any]:
        cells: dict[str, Any] = {c.key: None for c in modreg.COLUMNS}
        cells.update(
            {
                "row_key": f"modification:{no}:OB-1",
                "contract_external_id": "K01",
                "modification_no": no,
                "obligation_key": "OB-1",
                "kind": "SCOPE_CHANGE",
                "status": status,
                "currency": "USD",
                "tp_change": _money("100.00"),
                "impact_preview_sha256": preview,
                "treatment_override": False,
                "added_goods_distinct": True,
                "priced_at_ssp": True,
                "remaining_goods_distinct_from_transferred": False,
            }
        )
        return cells

    data = ReportData(
        columns=modreg.COLUMNS,
        rows=(row("1", "APPLIED", None), row("2", "APPROVED", "a" * 64)),
        control_totals={"row_count": 2},
    )
    encoded = snapshots.encode_report("MODIFICATION_REGISTER", data, drop_presentation_totals=True)
    headers, rows = locked._rows(encoded.content)
    assert [(r["status"], r["impact_preview_sha256"]) for r in rows] == [
        ("APPLIED", ""),
        ("APPROVED", "a" * 64),
    ]
    kinds = snapshots.declared_kinds("MODIFICATION_REGISTER", headers)
    assert kinds["status"] == "code" and kinds["impact_preview_sha256"] == "code"


def test_f_clo_exposes_the_machine_artefact_constants_the_db_witness_imports() -> None:
    """A4 13.5 (ii) / Q11 (F-CLO line 2, landed before this merge): the frozen file is stored as a
    machine artefact through F-CLO's constants — the DB witness plants and asserts ONLY through
    these imports (Codex 1824 §3), so their presence is measured here without a database."""
    assert close_snapshots.MEDIA_TYPE == "application/octet-stream"
    assert close_snapshots.FILE_SUFFIX == ".snapshot"
    assert (
        close_snapshots.dataset_filename("WATERFALL") == f"WATERFALL{close_snapshots.FILE_SUFFIX}"
    )
