"""Formula ownership: every node a stage package emits carries a formula id the stage declares
(ENGINE_SPEC §0.10 ``STAGES`` ``formula_ids``; Table 0.11-A; D-91 C606-03 (6)).

``stages/__init__.py`` and ``test_stage_registry.py`` check registry membership only (every declared
id is registered), never that a stage emits only what it declares. This test wraps
``TraceBuilder.node`` and attributes each node to the ``erev_engine.stages.sNN_*`` package on the
call stack that emitted it (stage 05 calls the stage 04 price binding and stage 09 the stage 08
estimate routing, so attribution by package, not by book-loop position), then requires
``node.formula_id in spec.formula_ids`` for every registered stage; ``tp.cpc_release.v1`` is
declared by stages 04 and 10 (ENGINE_SPEC §4.4, ENGINE_SPEC_B §10.5; D-91). Nodes emitted by
packages without a ``STAGES`` entry (stage 01, stage 13) must be registered formulas. No database.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence

import erev_engine
import pytest
from erev_engine import trace
from erev_engine.formulas import FORMULAS
from erev_engine.stages import STAGES
from support import cpc_worlds as w
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

KEYS = (
    "cpc/CPC-CHK-120-SHARE-BASED-WARRANTS-PROBABLE",
    "cpc/CPC-CHK-133-S3-EX32",
    "fx/FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED",
    "ret/RET-CHK-029-S3-EX22",
    "stp1/STP1-S1-EX1-CASEB-C-VARC",
)
_PACKAGE = re.compile(r"^erev_engine\.stages\.s(\d{2})_")


def _bundles() -> list[object]:
    found: list[object] = []
    for name in KEYS:
        for checkpoint in _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / f"{name}.yaml")):
            found.extend(checkpoint.bundles)
    found.append(
        w.units_world(
            [("D", w.Y1, "400000"), ("I", w.Y1, "400000.00")],
            [w.sbc_version(1, w.JAN, True, "1000000.00")],
        )
    )
    return found


def _emitting_stage() -> str | None:
    """The innermost ``erev_engine.stages.sNN_*`` package on the stack, or None."""
    frame = sys._getframe(2)
    while frame is not None:
        found = _PACKAGE.match(frame.f_globals.get("__name__", ""))
        if found:
            return found.group(1)
        frame = frame.f_back
    return None


def _attributed(
    monkeypatch: pytest.MonkeyPatch, bundles: Sequence[object]
) -> tuple[dict[str, set[str]], set[str]]:
    """{stage: formula ids its package emitted}, and the ids emitted by no stage package."""
    by_stage: dict[str, set[str]] = {}
    outside: set[str] = set()
    original = trace.TraceBuilder.node

    def node(self: trace.TraceBuilder, **kwargs: object) -> str:
        formula_id = str(kwargs["formula_id"])
        stage = _emitting_stage()
        if stage is None:
            outside.add(formula_id)
        else:
            by_stage.setdefault(stage, set()).add(formula_id)
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(trace.TraceBuilder, "node", node)
    for bundle in bundles:
        erev_engine.compute(bundle)  # type: ignore[arg-type]
    return by_stage, outside


def test_formula_ownership_every_emitted_node_declared_by_its_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_stage, outside = _attributed(monkeypatch, _bundles())
    declared = {spec.stage: set(spec.formula_ids) for spec in STAGES}
    undeclared = {
        stage: sorted(ids - declared[stage])
        for stage, ids in sorted(by_stage.items())
        if stage in declared and ids - declared[stage]
    }
    assert undeclared == {}, f"formulas emitted outside their stage's FORMULA_IDS: {undeclared}"
    unregistered = {
        stage: sorted(ids - set(FORMULAS))
        for stage, ids in sorted(by_stage.items())
        if stage not in declared and ids - set(FORMULAS)
    }
    assert unregistered == {}
    assert outside <= set(FORMULAS)
    # The worlds exercised the stage 04 ordinary series and the stage 10 share-based measure.
    assert {"tp.cpc_release.v1", "tp.cpc_reduction.v1"} <= by_stage["04"]
    assert {"tp.cpc_share_based.v1", "tp.cpc_release.v1"} <= by_stage["10"]
    assert "tp.cpc_share_based.v1" not in by_stage["04"]
    assert "rec.revenue_cum.v1" in by_stage["09"]
