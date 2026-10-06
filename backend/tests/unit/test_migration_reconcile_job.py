"""``domain.migration.jobs`` — the ``MIGRATION_RECONCILE`` composition over fakes (BUILD_SPEC LMG-3;
PRD SM-12, BR-MIG-02, WLD-X-27; SCREENS_B RPT-41 "Value representation"; Codex
``PRODUCTION-LMG3-EXTRACTOR-REVIEW-a2aad104.md`` F1 / C1).

The eRev side is the batch's BOUND comparison population (``population.ComparisonPopulation``:
mode, cutover, book, the contract / version / trace identities of the captured computation) — never
the latest live version. The legacy side is the shipped WLD-F-15 fixture. ``_erev_world`` builds
obligation-version rows and traces that reproduce the legacy values from the exact sources; that
makes the 136-line run COMPOSITION evidence (lines written once, status moved), not independent
engine-output evidence (C1) — the independent source checks live in
``test_migration_exact_values.py``; the selection witness here shows that a later competing live
version of the same contract is not read; a bound version carries its member contract SET and,
separately, its captured EXPECTED output — the obligation-version ids the computation produced,
possibly EMPTY (D-98-78: a voided member's version has none) — and the loaded rows must equal
that output exactly (C2; the legacy fixture's versions are singletons and are no evidence for
combined groups; the shared-version case is a synthetic row-bearing witness). The database path
(``tests/pg/test_migration_reconcile_job_pg.py``) is written and NOT RUN on the lane.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace as dataclasses_replace
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.migration import (
    exact_values,
    jobs,
    legacy_db,
    population,
    reconciliation,
    repository,
)
from erev_api.domain.migration.exact_values import ExactSourceError
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.domain.migration.population import ComparisonPopulation, VersionRef
from erev_api.domain.migration.reconciliation import DeviationIndex
from erev_api.enums import JobKind, MigrationMode, PrincipalKind
from erev_api.explain.store import trace_document
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import HANDLERS
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.trace import Trace, TraceNode
from sqlalchemy.dialects import postgresql
from support.architecture import ROOT

FIXTURE = ROOT / "backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db"
BATCH = UUID(int=31)
JOB = UUID(int=32)
TENANT = UUID(int=1)
CUTOVER = date(2023, 1, 31)
CENTS = Decimal("0.01")
BOOK = population.BOOK
# the fakes carry no retained input evidence; its verification has its own tests below
_VERIFIED = lambda _uow, _population: None  # noqa: E731


class _Result:
    def __init__(self, *, rows: tuple[Any, ...] = (), scalar: Any = None) -> None:
        self._rows, self._scalar = rows, scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._scalar


class _Session:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, Any]] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        self.calls.append((str(statement.compile(dialect=postgresql.dialect())), params))
        return self.results.pop(0) if self.results else _Result()


def _uow(*results: _Result) -> tuple[UnitOfWork, _Session]:
    session = _Session(*results)
    uow = SimpleNamespace(
        session=session,
        now=datetime(2026, 9, 20, 19, 0, tzinfo=UTC),  # SC stamps only; never a selection cutoff
        principal=SimpleNamespace(id=UUID(int=9), kind=PrincipalKind.SYSTEM, tenant_id=TENANT),
        commits=0,
    )
    return cast(UnitOfWork, uow), session


def _legacy() -> tuple[LegacyRow, ...]:
    return legacy_db.rows(FIXTURE)


def _source() -> dict[reconciliation.LineKey, Fraction]:
    return reconciliation.legacy_values(legacy_db.latest_rows(_legacy()))


def _node(exact: Fraction) -> SimpleNamespace:
    """A posted-cents node with the exact residue (DG-KRN-EXP-03)."""
    posted = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(CENTS)
    residue = reconciliation.exact_decimal_text(exact - Fraction(posted))
    return SimpleNamespace(value=format(posted, "f"), rounding_residue=residue)


def _contract_ids(source: dict[reconciliation.LineKey, Fraction]) -> dict[str, UUID]:
    return {
        contract: UUID(int=1 + index)
        for index, contract in enumerate(sorted({k[0] for k in source}))
    }


def _erev_world(
    source: dict[reconciliation.LineKey, Fraction],
    perturb: reconciliation.LineKey | None = None,
    *,
    version_base: int = 100,
    trace_base: int = 200,
    shift: Fraction = Fraction(1),
) -> tuple[list[dict[str, Any]], dict[UUID, dict[str, Any]], tuple[VersionRef, ...]]:
    """Obligation-version rows, per-version node lookups and the version identities of a world
    that reproduces ``source`` from the exact sources (RAW columns, posted-cents nodes + residue,
    stored billed cents), with one optional perturbed measure (``+ shift`` on ``perturb``). Version
    and trace ids are offset by the bases so two worlds of the same contracts are distinct."""
    rows: list[dict[str, Any]] = []
    traces: dict[UUID, dict[str, Any]] = {}
    contracts = _contract_ids(source)
    versions = {c: UUID(int=version_base + i) for i, c in enumerate(sorted(contracts))}
    trace_ids = {c: UUID(int=trace_base + i) for i, c in enumerate(sorted(contracts))}
    for index, legacy in enumerate(legacy_db.latest_rows(_legacy())):
        contract, obligation = legacy.contract_external_id, legacy.obligation_key

        def value(measure: str, contract: str = contract, obligation: str = obligation) -> Fraction:
            amount = source[(contract, obligation, measure)]
            return amount + shift if perturb == (contract, obligation, measure) else amount

        version_id = versions[contract]
        nodes = traces.setdefault(version_id, {})
        revenue, remaining = value("REVENUE_CUM"), value("ALLOCATION") - value("REVENUE_CUM")
        node_ids = {}
        for column, exact in (
            ("revenue_cum", revenue),
            ("remaining_allocation", remaining),
            ("position_obligation", value("NET_POSITION")),
            ("netting_reclass_amount", value("RECLASS")),
        ):
            node_id = f"{column}:{obligation}"  # node ids repeat across traces on purpose
            nodes[node_id] = _node(exact)
            node_ids[column] = node_id
        rows.append(
            {
                "id": UUID(int=version_base * 1000 + index),  # the obligation_version row id
                "contract_version_id": version_id,
                "contract_id": contracts[contract],
                "book_code": BOOK,
                "contract_external_id": contract,
                "obligation_key": obligation,
                "obligation_kind": "VC_LINE"
                if legacy.values.get("ASC 606 Stratification") == "VC"
                else "STANDARD",
                "original_allocated_exact": Decimal(
                    reconciliation.exact_decimal_text(value("ORIGINAL_ALLOCATION"))
                ),
                "remaining_quantity": Decimal(
                    reconciliation.exact_decimal_text(value("REMAINING_QTY"))
                ),
                "revenue_cum": Decimal(nodes[node_ids["revenue_cum"]].value),
                "remaining_allocation": Decimal(nodes[node_ids["remaining_allocation"]].value),
                "billed_cum": Decimal(reconciliation.exact_decimal_text(value("BILLED_CUM"))),
                "position_obligation": Decimal(nodes[node_ids["position_obligation"]].value),
                "netting_reclass_amount": Decimal(nodes[node_ids["netting_reclass_amount"]].value),
                "trace_nodes": node_ids,
            }
        )
    # one contract per version in this fixture: a SINGLETON membership — the shipped legacy
    # database has no combined groups, so this is no evidence for shared (group) versions (C2)
    refs = tuple(
        VersionRef(
            contract_ids=frozenset({contracts[c]}),
            contract_version_id=versions[c],
            calc_trace_id=trace_ids[c],
            book_code=BOOK,
            # the captured EXPECTED output: the obligation-version ids the computation produced
            obligation_version_ids=frozenset(
                row["id"] for row in rows if row["contract_version_id"] == versions[c]
            ),
        )
        for c in sorted(contracts)
    )
    return rows, traces, refs


def _population(refs: tuple[VersionRef, ...], **over: Any) -> ComparisonPopulation:
    fields: dict[str, Any] = {
        "batch_id": BATCH,
        "mode": MigrationMode.OPENING_BALANCES,
        "cutover_date": CUTOVER,
        "book_code": BOOK,
        "versions": refs,
    }
    fields.update(over)
    return ComparisonPopulation(**fields)


def _batch(status: str = "IMPORTED", **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": BATCH,
        "status": status,
        "mode": MigrationMode.OPENING_BALANCES.value,
        "cutover_date": CUTOVER,
        "sandbox_tenant_id": None,
        "import_upload_ids": [],
        "profile": {"contracts": 4, "legacy_pob_rows": 16},
    }
    row.update(over)
    return row


def _by_ids(store: list[dict[str, Any]]) -> Any:
    """A versions reader over ``store`` that selects exactly the population's version ids."""

    def reader(_uow: UnitOfWork, pop: ComparisonPopulation) -> list[dict[str, Any]]:
        wanted = {ref.contract_version_id for ref in pop.versions}
        return [row for row in store if row["contract_version_id"] in wanted]

    return reader


def _traces(traces: dict[UUID, dict[str, Any]], seen: list[VersionRef] | None = None) -> Any:
    def loader(_uow: UnitOfWork, ref: VersionRef) -> Any:
        if seen is not None:
            seen.append(ref)
        return traces[ref.contract_version_id].get

    return loader


def test_handler_is_registered_for_the_job_kind() -> None:
    assert HANDLERS[JobKind.MIGRATION_RECONCILE].handler is jobs.reconcile


def test_reconcile_composes_the_bound_population_into_lines_written_once() -> None:
    # COMPOSITION evidence (C1): the eRev world reproduces the legacy values from the exact
    # sources, so the run gives 136 lines, no difference, tie-out PASS; the lines are inserted once
    # and the batch moves IMPORTED → RECONCILED with the job id. Extraction correctness is proved
    # by test_migration_exact_values, selection by the witness below.
    rows, traces, refs = _erev_world(_source())
    updated = {"id": BATCH, "status": "RECONCILED", "row_version": 2}
    # results in call order: the batch row, the line count, the INSERT, the UPDATE … RETURNING
    uow, session = _uow(
        _Result(rows=(_batch(),)), _Result(scalar=0), _Result(), _Result(rows=(updated,))
    )
    totals = jobs.reconcile_batch(
        uow,
        BATCH,
        job_id=JOB,
        legacy_rows_reader=lambda _uow, _id: _legacy(),
        population_reader=lambda _uow, _batch: _population(refs),
        evidence_verifier=_VERIFIED,
        versions_reader=_by_ids(rows),
        trace_loader=_traces(traces),
        deviations=DeviationIndex.empty,
    )
    assert totals.as_json() == {
        "line_count": 136,
        "differences_above_tolerance": 0,
        "explained": 0,
        "unexplained": 0,
    }
    kinds = [call[0].split()[0] for call in session.calls]
    assert kinds == ["SELECT", "SELECT", "INSERT", "UPDATE"]  # batch, count, lines, transition
    inserted = session.calls[2][1]
    assert len(inserted) == 136 and {row["migration_batch_id"] for row in inserted} == {BATCH}
    original = next(
        row
        for row in inserted
        if (row["contract_external_id"], row["obligation_key"], row["measure"])
        == ("Contract 1", "POB #1", "ORIGINAL_ALLOCATION")
    )
    assert original["erev_value"] == original["source_value"] and original["is_within_tolerance"]
    assert "RECONCILED" in session.calls[3][0] or "status" in session.calls[3][0]


def test_selection_witness_the_bound_version_is_read_not_a_later_live_one() -> None:
    # Two computations of the same four contracts exist: V1 (bound by the population; reproduces
    # the legacy values) and V2, later, with every REVENUE_CUM shifted by +5 and traces whose node
    # ids collide with V1's. The reconcile reads V1's rows and V1's own traces (the bound
    # calc_trace ids), never V2 — and never a knowledge-time "latest".
    source = _source()
    v1_rows, v1_traces, v1_refs = _erev_world(source)
    v2_rows, v2_traces, _ = _erev_world(
        source,
        perturb=("Contract 1", "POB #1", "REVENUE_CUM"),
        version_base=300,
        trace_base=400,
        shift=Fraction(5),
    )
    store = v2_rows + v1_rows  # the later version first, as a "latest" reader would find it
    traces = {**v1_traces, **v2_traces}
    seen: list[VersionRef] = []
    updated = {"id": BATCH, "status": "RECONCILED", "row_version": 2}
    uow, session = _uow(
        _Result(rows=(_batch(),)), _Result(scalar=0), _Result(), _Result(rows=(updated,))
    )
    totals = jobs.reconcile_batch(
        uow,
        BATCH,
        job_id=JOB,
        legacy_rows_reader=lambda _uow, _id: _legacy(),
        population_reader=lambda _uow, _batch: _population(v1_refs),
        evidence_verifier=_VERIFIED,
        versions_reader=_by_ids(store),
        trace_loader=_traces(traces, seen),
    )
    assert totals.unexplained == 0 and totals.line_count == 136
    # own-trace identity: each contract version's trace was requested once, by its bound ref
    assert sorted(seen, key=lambda r: str(r.contract_version_id)) == sorted(
        v1_refs, key=lambda r: str(r.contract_version_id)
    )
    assert {ref.calc_trace_id for ref in seen} == {ref.calc_trace_id for ref in v1_refs}
    inserted = session.calls[2][1]
    revenue = next(
        row
        for row in inserted
        if (row["contract_external_id"], row["obligation_key"], row["measure"])
        == ("Contract 1", "POB #1", "REVENUE_CUM")
    )
    assert revenue["erev_value"] == revenue["source_value"]  # V1's value, not V2's (+5)


def test_the_witness_is_sensitive_binding_the_later_version_changes_the_result() -> None:
    # The same store; a population bound to V2 instead reads V2 — its shifted REVENUE_CUM is an
    # unexplained difference and the run refuses. So the selection, not the fixture, decided above.
    source = _source()
    v1_rows, v1_traces, _ = _erev_world(source)
    v2_rows, v2_traces, v2_refs = _erev_world(
        source,
        perturb=("Contract 1", "POB #1", "REVENUE_CUM"),
        version_base=300,
        trace_base=400,
        shift=Fraction(5),
    )
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _uow, _id: _legacy(),
            population_reader=lambda _uow, _batch: _population(v2_refs),
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(v2_rows + v1_rows),
            trace_loader=_traces({**v1_traces, **v2_traces}),
        )
    # +5 on REVENUE_CUM moves the obligation's and the contract's REVENUE_CUM (the remaining
    # allocation absorbs it, so ALLOCATION and TRANSACTION_PRICE stay): 2 unexplained
    assert refused.value.detail == jobs.UNEXPLAINED_COPY.format(count=2)
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]  # no write


def test_reconcile_refuses_before_any_write_when_the_batch_is_not_imported() -> None:
    uow, session = _uow(_Result(rows=(_batch("PROFILED"),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(uow, BATCH, legacy_rows_reader=lambda _u, _i: _legacy())
    assert refused.value.slug == "invalid-transition"
    assert "PROFILED" in (refused.value.detail or "")
    assert len(session.calls) == 1  # the batch read only


@pytest.mark.parametrize(
    ("mode", "over"),
    [
        (MigrationMode.OPENING_BALANCES, {}),
        (MigrationMode.REPLAY, {"cutover_date": None, "sandbox_tenant_id": UUID(int=77)}),
    ],
)
def test_reconcile_refuses_by_name_when_the_population_is_not_captured(
    mode: MigrationMode, over: dict[str, Any]
) -> None:
    # F1: no captured comparison population → the job names the missing source of THIS mode and
    # refuses; it does not read the latest live computation in its place. The default reader is
    # the repository's, which captures nothing yet (the import / replay slices supply it).
    batch = _batch(mode=mode.value, **over)
    assert repository.comparison_population(_uow()[0], batch) is None
    uow, session = _uow(_Result(rows=(batch,)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            versions_reader=lambda _u, _p: pytest.fail("no population, so no version read"),
        )
    assert refused.value.slug == "invalid-transition"
    assert refused.value.detail == population.not_captured_copy(mode)
    assert population.SOURCE_BY_MODE[mode] in (refused.value.detail or "")
    assert mode.value in (refused.value.detail or "")
    # the batch read and the T-MIG-04 capture read (empty) — no engine table, no write
    assert [call[0].split()[0] for call in session.calls] == ["SELECT", "SELECT"]
    assert "migration_population_version" in session.calls[1][0]


@pytest.mark.parametrize(
    "over",
    [
        {"batch_id": UUID(int=99)},
        {"cutover_date": date(2023, 2, 28)},
        {"mode": MigrationMode.REPLAY, "cutover_date": None},
    ],
)
def test_reconcile_refuses_a_population_that_is_not_the_batchs_own(over: dict[str, Any]) -> None:
    _rows, _traces, refs = _erev_world(_source())
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs, **over),
            evidence_verifier=_VERIFIED,
            versions_reader=lambda _u, _p: pytest.fail("a foreign population is never read"),
        )
    assert refused.value.slug == "invalid-transition"
    assert (refused.value.detail or "").startswith(population.FOREIGN_COPY.split("{")[0])
    assert len(session.calls) == 1


def test_reconcile_refuses_rows_outside_or_short_of_the_bound_population() -> None:
    source = _source()
    rows, traces, refs = _erev_world(source)
    stray_rows, _, _ = _erev_world(source, version_base=300, trace_base=400)
    # (1) a row of a version the population does not bind
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=lambda _u, _p: rows + stray_rows[:1],
            trace_loader=_traces(traces),
        )
    assert "not bound by the population" in (refused.value.detail or "")
    assert len(session.calls) == 1
    # (2) a bound version with no obligation rows
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=lambda _u, _p: [
                r for r in rows if r["contract_external_id"] != "Contract 4"
            ],
            trace_loader=_traces(traces),
        )
    assert "did not load" in (refused.value.detail or "")  # MISSING_OUTPUT_COPY, by name
    assert len(session.calls) == 1
    # (3) a row whose book is not the bound one, or whose contract is not a bound member
    for column, value in (("book_code", "LEGACY"), ("contract_id", UUID(int=555))):
        wrong = [dict(rows[0], **{column: value}), *rows[1:]]
        uow, session = _uow(_Result(rows=(_batch(),)))
        with pytest.raises(Problem) as refused:
            jobs.reconcile_batch(
                uow,
                BATCH,
                legacy_rows_reader=lambda _u, _i: _legacy(),
                population_reader=lambda _u, _b: _population(refs),
                evidence_verifier=_VERIFIED,
                versions_reader=lambda _u, _p, wrong=wrong: wrong,
                trace_loader=_traces(traces),
            )
        assert column in (refused.value.detail or "") and len(session.calls) == 1


def test_reconcile_refuses_unexplained_differences_until_exception_items_exist() -> None:
    # one perturbed exact source (+1 on Contract 1 POB #1 REVENUE_CUM): unexplained → refused with
    # the count; no line written, no status change
    rows, traces, refs = _erev_world(_source(), perturb=("Contract 1", "POB #1", "REVENUE_CUM"))
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(rows),
            trace_loader=_traces(traces),
        )
    assert refused.value.detail == jobs.UNEXPLAINED_COPY.format(count=2)
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]


def test_missing_or_wrong_trace_evidence_fails_closed() -> None:
    rows, _traces, refs = _erev_world(_source())
    uow, _ = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(rows),
            trace_loader=lambda _u, _ref: lambda _node_id: None,  # a trace without the nodes
        )
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].rule_id == "DG-PAR-05"

    def wrong_trace(_u: UnitOfWork, ref: VersionRef) -> Any:
        raise ExactSourceError(
            f"calc trace of version {ref.contract_version_id} is not the bound one"
        )

    uow, _ = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(rows),
            trace_loader=wrong_trace,
        )
    assert refused.value.errors[0].rule_id == "DG-PAR-05"
    assert "not the bound one" in refused.value.errors[0].message


def test_reader_validation_failure_is_the_named_refusal_at_the_reconcile_boundary() -> None:
    # Codex 0629 N1: the versions reader's retained kind / parent / batch / operation / duplicate
    # checks raise ExactSourceError INSIDE the population block — it must reach the caller as the
    # named DG-PAR-05 refusal (not the registry's sanitized generic 500 with empty errors), with
    # no reconciliation line written and no transition; PopulationError keeps its own mapping.
    _rows, _traces, refs = _erev_world(_source())

    def reader_refuses(_u: UnitOfWork, _population: ComparisonPopulation) -> Any:
        raise ExactSourceError(
            "obligation version 555: obligation_kind 'standard' is not the canonical 'STANDARD'"
        )

    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            versions_reader=reader_refuses,
            evidence_verifier=_VERIFIED,
            trace_loader=lambda _u, _ref: lambda _node_id: None,
        )
    assert refused.value.slug == "validation-failed"
    assert refused.value.errors[0].rule_id == "DG-PAR-05"
    assert "obligation_kind 'standard' is not the canonical" in refused.value.errors[0].message
    # the read boundary held: only the batch SELECT ran — no INSERT, no UPDATE, no transition
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]
    # and the registered handler stores the NAMED problem, never the sanitized generic failure
    from erev_api.jobs.registry import failure_problem

    stored = failure_problem(refused.value, UUID(int=42))
    assert stored["status"] != 500 and stored["errors"][0]["rule_id"] == "DG-PAR-05"


def _trace_row(version_id: UUID, trace_id: UUID, *, book: str = BOOK) -> dict[str, Any]:
    """A T-MIG-04 row's trace mirror (the reconcile reads the capture, never calc_trace)."""
    node = TraceNode(
        id="revenue_cum:POB #1",
        measure="revenue_cum",
        value="123.45",
        currency="USD",
        formula_id="f",
        inputs=(),
        params={},
        rounding_residue="0.001234567800000000",
        narrative_key="k",
    )
    trace = Trace(format_version=1, engine_version="test", nodes=(node,), root_measures={})
    return {
        "id": UUID(int=9000),
        "migration_batch_id": BATCH,
        "contract_version_id": version_id,
        "calc_trace_id": trace_id,
        "book_code": book,
        "format_version": 1,
        "engine_version": "test",
        "trace_sha256": trace.sha256(),
        "root_measures": {},
        "trace": trace_document(trace),
    }


def _shared_version_world() -> tuple[list[dict[str, Any]], dict[UUID, dict[str, Any]], VersionRef]:
    """One contract version shared by TWO member contracts (a combination group: 04 T-CON-04
    ``combination_group_member``; the computation persists the members' obligation rows in the
    one version, ``computation.py``) — SYNTHETIC, ROW-BEARING rows: a composition witness of the
    member-set shape, not the legacy fixture and not a persisted combined-group computation."""
    version_id, trace_id = UUID(int=700), UUID(int=800)
    members = {"Contract A": UUID(int=71), "Contract B": UUID(int=72)}
    nodes: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for index, (contract, amount) in enumerate(
        (("Contract A", Fraction(100)), ("Contract B", Fraction(250)))
    ):
        node_ids = {}
        for column, exact in (
            ("revenue_cum", amount),
            ("remaining_allocation", Fraction(0)),
            ("position_obligation", Fraction(0)),
            ("netting_reclass_amount", Fraction(0)),
        ):
            node_id = f"{column}:{contract}:POB #1"
            nodes[node_id] = _node(exact)
            node_ids[column] = node_id
        rows.append(
            {
                "id": UUID(int=900 + index),
                "contract_version_id": version_id,
                "contract_id": members[contract],
                "book_code": BOOK,
                "contract_external_id": contract,
                "obligation_key": "POB #1",
                "obligation_kind": "STANDARD",
                "original_allocated_exact": Decimal(reconciliation.exact_decimal_text(amount)),
                "remaining_quantity": Decimal("1"),
                "revenue_cum": Decimal(nodes[node_ids["revenue_cum"]].value),
                "remaining_allocation": Decimal("0.00"),
                "billed_cum": Decimal("0.00"),
                "position_obligation": Decimal("0.00"),
                "netting_reclass_amount": Decimal("0.00"),
                "trace_nodes": node_ids,
            }
        )
    ref = VersionRef(
        contract_ids=frozenset(members.values()),
        contract_version_id=version_id,
        calc_trace_id=trace_id,
        book_code=BOOK,
        obligation_version_ids=frozenset(row["id"] for row in rows),
    )
    return rows, {version_id: nodes}, ref


def test_a_shared_version_binds_its_members_and_exactly_its_captured_output() -> None:
    # C2: a version's admitted contract membership is bound as a SET, separately from its output;
    # the loaded rows must equal the captured EXPECTED output exactly. Both members' rows bind and
    # extract per contract; a non-member's row, an unexpected extra row, or an expected row that
    # is missing is refused BY NAME. Membership is never inferred from rows, output is never
    # fabricated or trimmed to what loaded. The fixture is synthetic and row-bearing — no evidence
    # for a persisted combined group.
    rows, traces, ref = _shared_version_world()
    bound = _population((ref,))
    assert [row["contract_external_id"] for row in bound.bind(rows)] == ["Contract A", "Contract B"]
    values = exact_values.erev_values(rows, lambda _row: traces[ref.contract_version_id].get)
    assert values[("Contract A", None, "REVENUE_CUM")] == 100
    assert values[("Contract B", None, "REVENUE_CUM")] == 250
    with pytest.raises(population.PopulationError, match="not a bound member"):
        bound.bind(
            [*rows, dict(rows[0], contract_id=UUID(int=73), contract_external_id="Contract C")]
        )
    # an unexpected extra row of a member (an id the capture did not record)
    with pytest.raises(
        population.PopulationError, match=population.UNEXPECTED_OUTPUT_COPY.split("{")[0]
    ):
        bound.bind([*rows, dict(rows[0], id=UUID(int=999))])
    # an expected row that did not load (Contract B's) — refused by name, never a silent zero
    with pytest.raises(population.PopulationError, match="did not load"):  # MISSING_OUTPUT_COPY
        bound.bind(rows[:1])
    # a version whose membership is not bound is refused BY NAME — the capability is incomplete
    # until capture supplies the membership; it is never inferred from the rows
    with pytest.raises(
        population.PopulationError, match=population.UNBOUND_MEMBERSHIP_COPY.split("{")[0]
    ):
        VersionRef(
            contract_ids=frozenset(),
            contract_version_id=UUID(int=700),
            calc_trace_id=UUID(int=800),
            book_code=BOOK,
            obligation_version_ids=frozenset(),
        )


def test_captured_empty_output_binds_and_still_validates_the_versions_trace() -> None:
    # D-98-78 (tests/engine/s05_allocation/test_s05_voided_member.py): a contract_version with NO
    # obligation_versions is an admitted computed result — membership is authoritative, the
    # captured expected output is EMPTY. Such a version binds with zero rows, and the job still
    # validates its own calc trace (id / book / hash) — a trace check that fired only when rows
    # exist would skip it. Distinguished from expected rows that are unexpectedly missing (above).
    source = _source()
    rows, traces, refs = _erev_world(source)
    voided = VersionRef(
        contract_ids=frozenset({UUID(int=55)}),
        contract_version_id=UUID(int=555),
        calc_trace_id=UUID(int=556),
        book_code=BOOK,
        obligation_version_ids=frozenset(),  # captured-empty
    )
    bound = _population((*refs, voided))
    assert len(bound.bind(rows)) == len(rows)  # zero rows for the voided member is exact
    seen: list[VersionRef] = []
    traces = {**traces, voided.contract_version_id: {}}
    updated = {"id": BATCH, "status": "RECONCILED", "row_version": 2}
    uow, session = _uow(
        _Result(rows=(_batch(),)), _Result(scalar=0), _Result(), _Result(rows=(updated,))
    )
    totals = jobs.reconcile_batch(
        uow,
        BATCH,
        job_id=JOB,
        legacy_rows_reader=lambda _uow, _id: _legacy(),
        population_reader=lambda _uow, _batch: bound,
        evidence_verifier=_VERIFIED,
        versions_reader=_by_ids(rows),
        trace_loader=_traces(traces, seen),
    )
    assert totals.line_count == 136 and totals.unexplained == 0
    assert voided in seen  # the empty version's own trace was validated
    assert len(seen) == len(refs) + 1

    # the same voided version whose trace evidence is wrong → refused, even with no rows
    def loader(_u: UnitOfWork, ref: VersionRef) -> Any:
        if ref is voided:
            raise ExactSourceError("calc trace of version 555 is not the bound calc trace")
        return traces[ref.contract_version_id].get

    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _uow, _id: _legacy(),
            population_reader=lambda _uow, _batch: bound,
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(rows),
            trace_loader=loader,
        )
    assert refused.value.errors[0].rule_id == "DG-PAR-05"
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]


def test_a_population_that_fails_validation_at_the_read_boundary_is_a_named_refusal() -> None:
    # C2-R2: a supplier that materialises an invalid binding raises PopulationError inside the
    # reader; the job translates it into the named invalid-transition refusal instead of letting
    # it escape to the registry's sanitized 500 ("The job stopped with an unexpected error.").
    def invalid_reader(_u: UnitOfWork, _b: Any) -> ComparisonPopulation:
        return _population(
            (
                VersionRef(
                    contract_ids=frozenset(),
                    contract_version_id=UUID(int=1),
                    calc_trace_id=None,
                    book_code=BOOK,
                    obligation_version_ids=frozenset(),
                ),
            )
        )

    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=invalid_reader,
            evidence_verifier=_VERIFIED,
        )
    assert refused.value.slug == "invalid-transition"
    assert (refused.value.detail or "").startswith(population.UNBOUND_MEMBERSHIP_COPY.split("{")[0])
    assert len(session.calls) == 1

    # an unexpected error in the reader is NOT translated (it stays sanitized upstream)
    def broken_reader(_u: UnitOfWork, _b: Any) -> ComparisonPopulation:
        raise RuntimeError("boom")

    uow, _ = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(RuntimeError):
        jobs.reconcile_batch(
            uow, BATCH, legacy_rows_reader=lambda _u, _i: _legacy(), population_reader=broken_reader
        )


def test_repository_trace_reader_binds_the_versions_own_trace() -> None:
    version_id, trace_id = UUID(int=100), UUID(int=200)
    ref = VersionRef(
        contract_ids=frozenset({UUID(int=1)}),
        obligation_version_ids=frozenset({UUID(int=1000)}),
        contract_version_id=version_id,
        calc_trace_id=trace_id,
        book_code=BOOK,
    )
    # the stored trace row of the version whose id is the bound calc_trace_id → the node lookup
    uow, session = _uow(_Result(rows=(_trace_row(version_id, trace_id),)))
    lookup = repository.trace_nodes(uow, ref)
    node = lookup("revenue_cum:POB #1")
    assert node is not None and (node.value, node.rounding_residue) == (
        "123.45",
        "0.001234567800000000",
    )
    assert "migration_population_version.contract_version_id" in session.calls[0][0]
    # the capture's trace mirror, never the live engine table
    assert "FROM erev.migration_population_version" in session.calls[0][0]
    assert "FROM erev.calc_trace" not in session.calls[0][0]
    # a different trace id than the bound one → refused (a same-named node of another trace is
    # not evidence for this version)
    uow, _ = _uow(_Result(rows=(_trace_row(version_id, UUID(int=201)),)))
    with pytest.raises(ExactSourceError, match="not the bound calc trace"):
        repository.trace_nodes(uow, ref)
    # another book, no row, no bound id, a tampered hash — each refused, never 0
    uow, _ = _uow(_Result(rows=(_trace_row(version_id, trace_id, book="LEGACY"),)))
    with pytest.raises(ExactSourceError, match="book"):
        repository.trace_nodes(uow, ref)
    uow, _ = _uow(_Result())
    with pytest.raises(ExactSourceError, match="no captured calc trace"):
        repository.trace_nodes(uow, ref)
    uow, _ = _uow(_Result(rows=(_trace_row(version_id, trace_id),)))
    with pytest.raises(ExactSourceError, match="records no calc trace"):
        repository.trace_nodes(
            uow,
            VersionRef(
                contract_ids=frozenset({UUID(int=1)}),
                obligation_version_ids=frozenset({UUID(int=1000)}),
                contract_version_id=version_id,
                calc_trace_id=None,
                book_code=BOOK,
            ),
        )
    tampered = dict(_trace_row(version_id, trace_id), trace_sha256="0" * 64)
    uow, _ = _uow(_Result(rows=(tampered,)))
    with pytest.raises(ExactSourceError, match="trace_sha256"):
        repository.trace_nodes(uow, ref)


def test_repository_population_reader_binds_the_captured_rows() -> None:
    # comparison_population reads T-MIG-04: members → contract_ids, the expected output ids, the
    # trace id, the provenance (cutover / payload batch id); None when nothing is captured.
    stored = {
        "contract_version_id": UUID(int=100),
        "calc_trace_id": UUID(int=200),
        "book_code": BOOK,
        "members": [
            {"contract_id": str(UUID(int=1)), "contract_external_id": "Contract 1"},
            {"contract_id": str(UUID(int=2)), "contract_external_id": "Contract 2"},
        ],
        "obligation_version_ids": [UUID(int=1000), UUID(int=1001)],
        "cutover_date": CUTOVER,
        "payload_migration_batch_id": BATCH,
        "trace_sha256": "d" * 64,
        "expected_output_captured": True,
    }
    uow, session = _uow(_Result(rows=(stored,)))
    bound = repository.comparison_population(uow, _batch())
    assert bound is not None and bound.batch_id == BATCH and bound.book_code == BOOK
    (ref,) = bound.versions
    assert ref.contract_ids == {UUID(int=1), UUID(int=2)}
    assert ref.obligation_version_ids == {UUID(int=1000), UUID(int=1001)}
    assert ref.trace_sha256 == "d" * 64 and ref.expected_output_captured is True
    # a stored row whose output was NOT captured cannot bind (omitted ≠ empty; Codex 0422 (d))
    uow, _ = _uow(_Result(rows=(dict(stored, expected_output_captured=False),)))
    with pytest.raises(population.PopulationError, match="was not captured"):
        repository.comparison_population(uow, _batch())
    assert (ref.calc_trace_id, ref.cutover_date, ref.payload_migration_batch_id) == (
        UUID(int=200),
        CUTOVER,
        BATCH,
    )
    assert "migration_population_version.migration_batch_id" in session.calls[0][0]
    bound.check_batch(_batch())  # its own batch and cutover
    with pytest.raises(population.PopulationError, match="cutover"):
        bound.check_batch(_batch(cutover_date=date(2023, 2, 28)))
    # the per-version provenance: the same population claim, but a version whose OWN input named
    # another cutover — refused even though the population's cutover matches the batch
    drifted = ComparisonPopulation(
        batch_id=BATCH,
        mode=MigrationMode.OPENING_BALANCES,
        cutover_date=CUTOVER,
        book_code=BOOK,
        versions=(
            VersionRef(
                contract_ids=ref.contract_ids,
                contract_version_id=ref.contract_version_id,
                calc_trace_id=ref.calc_trace_id,
                book_code=BOOK,
                obligation_version_ids=ref.obligation_version_ids,
                cutover_date=date(2023, 2, 28),
                payload_migration_batch_id=BATCH,
            ),
        ),
    )
    with pytest.raises(population.PopulationError, match="was computed at cutover"):
        drifted.check_batch(_batch())
    # a capture recorded for another batch is foreign, even when stored under this batch id
    foreign = dict(stored, payload_migration_batch_id=UUID(int=99))
    uow, _ = _uow(_Result(rows=(foreign,)))
    other = repository.comparison_population(uow, _batch())
    assert other is not None
    with pytest.raises(population.PopulationError, match="was computed for migration"):
        other.check_batch(_batch())


def test_repository_readers_validate_the_captured_hashes_and_both_representations() -> None:
    # Codex 0408 / 0422 (g): the trace the reader rebuilds must hash to the BOUND captured hash,
    # and a T-MIG-05 row's typed columns must agree with its retained canonical row and row_sha256
    # before any measure is extracted.
    version_id, trace_id = UUID(int=100), UUID(int=200)
    row = _trace_row(version_id, trace_id)
    bound = VersionRef(
        contract_ids=frozenset({UUID(int=1)}),
        contract_version_id=version_id,
        calc_trace_id=trace_id,
        book_code=BOOK,
        obligation_version_ids=frozenset({UUID(int=1000)}),
        trace_sha256=row["trace_sha256"],
        expected_output_captured=True,
    )
    uow, _ = _uow(_Result(rows=(row,)))
    assert repository.trace_nodes(uow, bound)("revenue_cum:POB #1") is not None
    other = VersionRef(
        contract_ids=frozenset({UUID(int=1)}),
        contract_version_id=version_id,
        calc_trace_id=trace_id,
        book_code=BOOK,
        obligation_version_ids=frozenset({UUID(int=1000)}),
        trace_sha256="e" * 64,
        expected_output_captured=True,
    )
    uow, _ = _uow(_Result(rows=(row,)))
    with pytest.raises(ExactSourceError, match="not the bound"):
        repository.trace_nodes(uow, other)
    # the dual representation of a captured obligation version
    from erev_api.domain.migration.capture import canonical_row

    retained = {
        "id": str(UUID(int=1000)),
        "contract_version_id": str(version_id),
        "contract_id": str(UUID(int=1)),
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": "1300.000000000000000000",
        "remaining_quantity": "0.000000000000000000",
        "billed_cum": "300.00",
        "revenue_cum": "295.69",
        "remaining_allocation": "1004.31",
        "position_obligation": "4.31",
        "netting_reclass_amount": "0.00",
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
    }
    document, digest = canonical_row(retained)
    parent = {
        "id": UUID(int=9000),
        "contract_version_id": version_id,
        "migration_batch_id": BATCH,
        "capture_operation_id": UUID(int=32),
    }
    stored = {
        "migration_batch_id": BATCH,
        "population_version_id": UUID(int=9000),
        "capture_operation_id": UUID(int=32),
        "obligation_version_id": UUID(int=1000),
        "contract_version_id": version_id,
        "contract_id": UUID(int=1),
        "contract_external_id": "Contract 1",
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": Decimal("1300"),
        "remaining_quantity": Decimal("0"),
        "billed_cum": Decimal("300.00"),
        "revenue_cum": Decimal("295.69"),
        "remaining_allocation": Decimal("1004.31"),
        "position_obligation": Decimal("4.31"),
        "netting_reclass_amount": Decimal("0.00"),
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
        "row": document,
        "row_sha256": digest,
    }
    population_ = _population((bound,))
    # reads in order: the parents of the bound versions in this batch, then the children
    uow, _ = _uow(_Result(rows=(parent,)), _Result(rows=(stored,)))
    (shaped,) = repository.population_obligation_versions(uow, population_)
    assert shaped["id"] == UUID(int=1000) and shaped["revenue_cum"] == Decimal("295.69")
    for broken, what in (
        (dict(stored, revenue_cum=Decimal("295.70")), "disagrees with the retained row"),
        (dict(stored, row_sha256="0" * 64), "row_sha256"),
        (dict(stored, contract_id=UUID(int=2)), "contract_id"),
        (dict(stored, trace_nodes={"revenue_cum": "other"}), "trace_nodes"),
    ):
        uow, _ = _uow(_Result(rows=(parent,)), _Result(rows=(broken,)))
        with pytest.raises(ExactSourceError, match=what):
            repository.population_obligation_versions(uow, population_)


def test_repository_versions_reader_selects_the_bound_version_ids_only() -> None:
    _rows, _traces, refs = _erev_world(_source())
    uow, session = _uow(_Result(rows=()), _Result(rows=()))
    assert repository.population_obligation_versions(uow, _population(refs)) == []
    parents_sql, sql = session.calls[0][0], session.calls[1][0]
    assert "FROM erev.migration_population_version" in parents_sql  # the durable parents first
    assert "migration_population_obligation.contract_version_id IN" in sql
    assert "migration_population_obligation.migration_batch_id =" in sql  # scoped to the batch
    assert "FROM erev.migration_population_obligation" in sql
    assert "erev.obligation_version " not in sql and "erev.obligation_version\n" not in sql
    # the selection is by the bound ids alone: no knowledge-time filter, no latest-by-version-number
    where = sql[sql.index("WHERE") :]
    assert "known_at" not in where and "version_no" not in where and "DISTINCT" not in sql


def test_job_handler_commits_and_reports_the_counts() -> None:
    rows, traces, refs = _erev_world(_source())
    updated = {"id": BATCH, "status": "RECONCILED", "row_version": 2}
    uow, session = _uow(
        _Result(rows=(_batch(),)), _Result(scalar=0), _Result(), _Result(rows=(updated,))
    )
    commits: list[int] = []
    cast(Any, uow).commit = lambda: commits.append(1)

    @contextmanager
    def unit_of_work() -> Iterator[UnitOfWork]:
        yield uow

    jc = cast(JobContext, SimpleNamespace(unit_of_work=unit_of_work, job_id=JOB))
    default_readers = (
        jobs.repository.legacy_records,
        jobs.repository.comparison_population,
        jobs.repository.population_obligation_versions,
        jobs.repository.trace_nodes,
    )
    assert all(callable(reader) for reader in default_readers)
    # drive the handler through reconcile_batch's ports by patching the module defaults
    original = jobs.reconcile_batch
    try:
        jobs.reconcile_batch = lambda u, b, *, job_id=None, **_: original(  # type: ignore[assignment]
            u,
            b,
            job_id=job_id,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            evidence_verifier=_VERIFIED,
            versions_reader=_by_ids(rows),
            trace_loader=_traces(traces),
        )
        outcome = jobs.reconcile(jc, {"migration_id": str(BATCH)})
    finally:
        jobs.reconcile_batch = original  # type: ignore[assignment]
    assert outcome.state == "SUCCEEDED" and outcome.result["counts"]["line_count"] == 136
    assert outcome.result["href"] == f"/api/v1/migrations/{BATCH}" and commits == [1]


def test_repository_verifies_the_retained_input_evidence_by_name() -> None:
    # Codex 0515 R1: the retained T-CON-25 evidence must be the producing bundle — raw digest,
    # CV-25 input_sha256, bundle known_at, member keys and the admitted OPENING event's batch /
    # cutover all agree — else refused by name; missing evidence is refused, never read past.
    from erev_api.domain.migration.capture import opening_event_binding
    from support.migration_capture import capture_world

    world = capture_world(BATCH)
    opening_event_id = UUID(int=700)
    row = {
        "migration_batch_id": BATCH,
        "contract_version_id": UUID(int=100),
        "calc_trace_id": UUID(int=200),
        "input_sha256": world.input_sha256,
        "bundle_known_at": world.bundle.known_at,
        # Codex 0605 R1: the declared opening event UUID bound to the bundle's logical event
        "opening_event_id": opening_event_id,
        "opening_event_key": world.opening_event_key,
        "opening_event_binding_sha256": opening_event_binding(
            opening_event_id, world.opening_event_key, world.opening_payload_sha256
        ),
        "members": [{"contract_id": str(UUID(int=1)), "contract_external_id": world.contract_key}],
        "payload_migration_batch_id": BATCH,
        "cutover_date": CUTOVER,
        "input_evidence": world.evidence_document,
        "input_evidence_sha256": world.evidence_sha256,
    }
    repository.verify_input_evidence(row)  # the consistent capture passes
    for broken, what in (
        (dict(row, input_evidence=None), "no input evidence"),
        (dict(row, input_evidence_sha256="0" * 64), "input_evidence_sha256"),
        (dict(row, input_sha256="f" * 64), "input_sha256"),
        (dict(row, bundle_known_at=datetime(2030, 1, 1, tzinfo=UTC)), "bundle_known_at"),
        (
            dict(row, members=[{"contract_id": str(UUID(int=1)), "contract_external_id": "Z"}]),
            "members",
        ),
        (dict(row, payload_migration_batch_id=UUID(int=99)), "OPENING_BALANCE_ESTABLISHED"),
        (dict(row, cutover_date=date(2023, 2, 28)), "OPENING_BALANCE_ESTABLISHED"),
        # Codex 0605 R1 — the token-only witness: every hash-bound fact identical, only the
        # declared opening event UUID changed; the binding no longer recomputes → refused by name
        (dict(row, opening_event_id=UUID(int=701)), "opening_event_binding_sha256 mismatch"),
        (dict(row, opening_event_binding_sha256="0" * 64), "opening_event_binding_sha256"),
        (dict(row, opening_event_key=f"{world.contract_key}/EV-000009"), "opening_event_key"),
    ):
        with pytest.raises(ExactSourceError, match=what):
            repository.verify_input_evidence(broken)
    # verify_capture_evidence selects the intended capture — the population's batch AND the bound
    # version (the unique key) — binds it to the ref and refuses a missing, duplicate or foreign row
    # (Codex 0605 R2b extension)
    ref = VersionRef(
        contract_ids=frozenset({UUID(int=1)}),
        contract_version_id=UUID(int=100),
        calc_trace_id=UUID(int=200),
        book_code=BOOK,
        obligation_version_ids=frozenset(),
        trace_sha256="d" * 64,
        expected_output_captured=True,
    )
    uow, session = _uow(_Result(rows=(row,)))
    repository.verify_capture_evidence(uow, _population((ref,)))
    statement = session.calls[0][0]
    assert "FROM erev.migration_population_version" in statement
    assert "migration_population_version.migration_batch_id = %(migration_batch_id_1)s" in statement
    assert "migration_population_version.contract_version_id IN " in statement
    uow, _ = _uow(_Result(rows=()))
    with pytest.raises(ExactSourceError, match="no captured row to verify"):
        repository.verify_capture_evidence(uow, _population((ref,)))
    uow, _ = _uow(_Result(rows=(row, dict(row))))
    with pytest.raises(ExactSourceError, match="more than one evidence row"):
        repository.verify_capture_evidence(uow, _population((ref,)))
    uow, _ = _uow(_Result(rows=(dict(row, calc_trace_id=UUID(int=201)),)))
    with pytest.raises(ExactSourceError, match="calc_trace_id differs"):
        repository.verify_capture_evidence(uow, _population((ref,)))
    # and the job maps a failed verification to the DG-PAR-05 refusal before any extraction
    rows, traces, refs = _erev_world(_source())
    uow, session = _uow(_Result(rows=(_batch(),)))
    with pytest.raises(Problem) as refused:
        jobs.reconcile_batch(
            uow,
            BATCH,
            legacy_rows_reader=lambda _u, _i: _legacy(),
            population_reader=lambda _u, _b: _population(refs),
            versions_reader=_by_ids(rows),
            trace_loader=_traces(traces),
            evidence_verifier=lambda _u, _p: (_ for _ in ()).throw(
                ExactSourceError("contract version x: the input evidence does not hash")
            ),
        )
    assert refused.value.errors[0].rule_id == "DG-PAR-05"
    assert [call[0].split()[0] for call in session.calls] == ["SELECT"]


def test_child_rows_are_bound_to_their_parent_batch_and_operation_and_labelled_by_the_map() -> None:
    # Codex 0533 R2a / R2b: a T-MIG-05 row must belong to its durable parent (population_version_id,
    # same batch, same operation), be supplied once, carry the kind its canonical row holds, and
    # carry the external id the parent's retained member map gives its contract — before extraction.
    from erev_api.domain.migration.capture import canonical_row

    version_id, trace_id, parent_id, operation = (
        UUID(int=100),
        UUID(int=200),
        UUID(int=9000),
        UUID(int=32),
    )
    retained = {
        "id": str(UUID(int=1000)),
        "contract_version_id": str(version_id),
        "contract_id": str(UUID(int=1)),
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": "1300.000000000000000000",
        "remaining_quantity": "0.000000000000000000",
        "billed_cum": "300.00",
        "revenue_cum": "295.69",
        "remaining_allocation": "1004.31",
        "position_obligation": "4.31",
        "netting_reclass_amount": "0.00",
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
    }
    document, digest = canonical_row(retained)
    parent = {
        "id": parent_id,
        "contract_version_id": version_id,
        "migration_batch_id": BATCH,
        "capture_operation_id": operation,
    }
    child = {
        "migration_batch_id": BATCH,
        "population_version_id": parent_id,
        "capture_operation_id": operation,
        "obligation_version_id": UUID(int=1000),
        "contract_version_id": version_id,
        "contract_id": UUID(int=1),
        "contract_external_id": "Contract 1",
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": Decimal("1300"),
        "remaining_quantity": Decimal("0"),
        "billed_cum": Decimal("300.00"),
        "revenue_cum": Decimal("295.69"),
        "remaining_allocation": Decimal("1004.31"),
        "position_obligation": Decimal("4.31"),
        "netting_reclass_amount": Decimal("0.00"),
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
        "row": document,
        "row_sha256": digest,
    }
    ref = VersionRef(
        contract_ids=frozenset({UUID(int=1)}),
        contract_version_id=version_id,
        calc_trace_id=trace_id,
        book_code=BOOK,
        obligation_version_ids=frozenset({UUID(int=1000)}),
        trace_sha256="d" * 64,
        expected_output_captured=True,
        members={UUID(int=1): "Contract 1"},
        capture_batch_id=BATCH,
    )
    pop = _population((ref,))
    # reads in order: the parent rows of the bound versions in this batch, then the child rows
    uow, session = _uow(_Result(rows=(parent,)), _Result(rows=(child,)))
    (shaped,) = repository.population_obligation_versions(uow, pop)
    assert shaped["id"] == UUID(int=1000) and shaped["contract_external_id"] == "Contract 1"
    assert "migration_batch_id" in session.calls[0][0]  # the parents are read in THIS batch
    assert "migration_batch_id" in session.calls[1][0]  # and the children scoped to it
    pop.bind([shaped])  # the label matches the retained member map
    # R2a: a typed kind the canonical row does not hold (STANDARD → VC_LINE would flip POB_COUNT)
    uow, _ = _uow(_Result(rows=(parent,)), _Result(rows=(dict(child, obligation_kind="VC_LINE"),)))
    with pytest.raises(ExactSourceError, match="obligation_kind"):
        repository.population_obligation_versions(uow, pop)
    # R2a: a typed label that is not the retained external id of the member
    with pytest.raises(population.PopulationError, match="contract_external_id"):
        pop.bind([dict(shaped, contract_external_id="Contract 9")])
    # R2b: another parent, another batch, another operation, a duplicate child — each refused
    for broken, what in (
        (dict(child, population_version_id=UUID(int=9001)), "is not its parent"),
        (dict(child, migration_batch_id=UUID(int=99)), "not the population's batch"),
        (dict(child, capture_operation_id=UUID(int=77)), "capture_operation_id"),
    ):
        uow, _ = _uow(_Result(rows=(parent,)), _Result(rows=(broken,)))
        with pytest.raises(ExactSourceError, match=what):
            repository.population_obligation_versions(uow, pop)
    uow, _ = _uow(_Result(rows=(parent,)), _Result(rows=(child, dict(child))))
    with pytest.raises(ExactSourceError, match="supplied twice"):
        repository.population_obligation_versions(uow, pop)
    uow, _ = _uow(_Result(rows=()), _Result(rows=(child,)))
    with pytest.raises(ExactSourceError, match="no captured parent version in this batch"):
        repository.population_obligation_versions(uow, pop)
    # R2b: the trace mirror is read within the same capture (the batch is in the WHERE clause)
    row = _trace_row(version_id, trace_id)
    uow, session = _uow(_Result(rows=(row,)))
    repository.trace_nodes(uow, dataclasses_replace(ref, trace_sha256=row["trace_sha256"]))
    where = session.calls[0][0][session.calls[0][0].index("WHERE") :]
    assert "migration_batch_id" in where and "contract_version_id" in where
    # a member map that does not name exactly the bound members is refused at construction
    with pytest.raises(population.PopulationError, match="retained member map"):
        VersionRef(
            contract_ids=frozenset({UUID(int=1)}),
            contract_version_id=version_id,
            calc_trace_id=trace_id,
            book_code=BOOK,
            obligation_version_ids=frozenset(),
            members={UUID(int=2): "Contract 2"},
        )
