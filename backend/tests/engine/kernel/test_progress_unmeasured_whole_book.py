"""T1F-LP-PR-1 (ENGINE_SPEC CV-50 rev 1.31; ENGINE_SPEC_B §9.5 rev 1.36; D-98 candidate 134): the
T-CON-11 ``progress_ratio`` column always links a stage-09 producer. Under the V4 status guard of a
book that was never activated (S02-R-03) the producer is the ``rec.progress.unmeasured.v1`` node —
the rule-produced 0 carrying its guard, status and date — never the missing-node zero default.

Two SEPARATE whole-engine witnesses (Codex production-20260921-1249's acceptance map): the
UNMODIFIED golden Contract 2 step 07 ``LEGACY_PARITY`` world (four obligations; fail-first: at
62b430d6 whole-book ``check_book`` with no exceptions is red on ``progress_ratio`` for all four) and
the MODIFIED five-obligation world of the zero-total module (VC #2 created under DEV-054; all its
allocation / zero-total / created-VC / NULL-SSP controls kept). The fixtures are NOT activated to
dodge the gap. The unguarded measured path stays a distinct positive path (the activated world).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from fractions import Fraction
from pathlib import Path
from types import ModuleType

from erev_engine import compute
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.trace import reevaluate
from support import golden_streams, intent_totals, trace_linkage
from support.answer_keys import loader

S06_TESTS = Path(__file__).resolve().parents[1] / "s06_modifications"
UNMEASURED = "rec.progress.unmeasured.v1"
BASELINE = frozenset(
    {"Contract 2/POB %231", "Contract 2/POB %232", "Contract 2/POB %233", "Contract 2/VC %231"}
)


def _module(name: str) -> ModuleType:
    if str(S06_TESTS) not in sys.path:
        sys.path.insert(0, str(S06_TESTS))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, S06_TESTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _book(bundle: InputBundle) -> BookOutput:
    output = compute(bundle)
    return next(item for item in output.books if item.book_code == "ASC606")


def _unlinked_value_columns(book: BookOutput) -> set[tuple[str, str]]:
    types = loader.obligation_columns()
    return {
        (item.subject_key, column)
        for item in book.obligation_versions
        for column in trace_linkage.expected_columns(item.columns, types) - set(item.trace_nodes)
    }


def _iso(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _assert_unmeasured(bundle: InputBundle, book: BookOutput, subjects: frozenset[str]) -> None:
    """Every obligation version of a never-activated book: status guard V4:DRAFT on the revenue
    target, progress 0 published, its producer the version-date unmeasured node (formula, value,
    reason = the guard string, as_of = the version date), a node at every period key too, the
    whole book linked with NO exception, and the trace replaying."""
    nodes = {node.id: node for node in book.trace.nodes}
    versions = {item.subject_key: item for item in book.obligation_versions}
    assert set(versions) == subjects
    for subject, version in versions.items():
        assert nodes[version.trace_nodes["revenue_cum"]].params["guard"] == "V4:DRAFT"
        assert version.columns["progress_ratio"] == 0
        link = version.trace_nodes["progress_ratio"]
        assert link == f"progress_ratio:{subject}:-"
        node = nodes[link]
        assert node.formula_id == UNMEASURED and node.inputs == ()
        assert Fraction(node.value) == 0 and node.rounding_residue is None
        assert node.params == {
            "as_of": _iso(version.columns["effective_date"]),
            "reason": "V4:DRAFT",
        }
        periods = [
            item
            for item in nodes.values()
            if item.measure == "progress_ratio"
            and item.id.startswith(f"progress_ratio:{subject}:")
            and not item.id.endswith(":-")
        ]
        assert periods and all(item.formula_id == UNMEASURED for item in periods)
    assert _unlinked_value_columns(book) == set()  # the T1F-LP-PR-1 gap is closed for every row
    trace_linkage.check_book(book, bundle, exceptions=trace_linkage.NO_EXCEPTIONS)
    replayed = reevaluate(book.trace)
    for version in versions.values():
        link = version.trace_nodes["progress_ratio"]
        assert replayed[link] == nodes[link].value


def test_unmodified_baseline_world_links_the_unmeasured_progress_producer() -> None:
    """The four-obligation UNMODIFIED golden world (no delivery appended, no amendment, never
    activated): the committed witness of the baseline Codex 1249 asked for."""
    bundle = golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    _assert_unmeasured(bundle, _book(bundle), BASELINE)


def test_modified_five_obligation_world_links_the_unmeasured_progress_producer() -> None:
    """The five-obligation MODIFIED world (deliveries + the LEGACY_PROSPECTIVE ADD of VC #2): the
    created line inherits the same guard and the same producer; its DEV-054 controls hold."""
    zero_total = _module("test_s06_legacy_prospective_zero_total")
    bundle = zero_total.zero_total_world()
    book = _book(bundle)
    _assert_unmeasured(bundle, book, BASELINE | {"Contract 2/VC %232"})
    created = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "VC #2"
    )
    assert created.columns["original_allocated_amount"] == 0
    assert created.columns["allocation_weight"] == 0
    assert created.trace_nodes["allocation_weight"] == "absent:zero-total"
    assert created.trace_nodes["original_ssp_selected"] == "absent:no-ssp-resolution"
    assert created.columns["original_unit_ssp"] is None
    assert created.trace_nodes["original_total_contract_ssp"].startswith(
        "original_total_contract_ssp@"
    )


def test_activated_world_keeps_the_measured_progress_path() -> None:
    """The unguarded positive path, distinct from the unmeasured zero: the activated step 07 world
    measures POB #1 at 1/8 and POB #3 at 2/5 through ``rec.progress.units.v1``; POB #2's MEASURED 0
    (nothing delivered) is a measurement, not the unmeasured node; the whole book links."""
    bundle = intent_totals.activated(
        golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    )
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    expected = {"POB #1": Fraction(1, 8), "POB #2": Fraction(0), "POB #3": Fraction(2, 5)}
    for key, ratio in expected.items():
        version = next(
            item for item in book.obligation_versions if item.columns["obligation_key"] == key
        )
        node = nodes[version.trace_nodes["progress_ratio"]]
        assert version.columns["progress_ratio"] == ratio
        assert node.formula_id == "rec.progress.units.v1" and "reason" not in node.params
        assert Fraction(node.value) == ratio
        assert "guard" not in nodes[version.trace_nodes["revenue_cum"]].params
    assert _unlinked_value_columns(book) == set()
    trace_linkage.check_book(book, bundle, exceptions=trace_linkage.NO_EXCEPTIONS)
