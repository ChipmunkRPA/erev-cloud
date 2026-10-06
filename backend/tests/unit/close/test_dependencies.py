"""Producers other lanes own are resolved by name and, when absent, refused by name (F-CLO record
§17: P4 ``controls.evidence``; F-RPS ``reports.snapshots``; EDS-6 ``s15_disclosures.snapshots``).
Each resolver test holds whether or not the producer is on the tree: it asserts the agreed shape
when present and the named refusal when absent, so landing a producer never breaks it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from erev_api.domain.close import dependencies


def _outcome(resolve: Callable[[], Any]) -> tuple[str, Any]:
    try:
        return "present", resolve()
    except dependencies.ProducerMissing as exc:
        return "missing", exc


def test_control_evidence_resolves_or_refuses_by_name() -> None:
    state, value = _outcome(dependencies.control_evidence)
    if state == "missing":
        assert value.module == dependencies.CONTROL_EVIDENCE
        assert "record_execution" in value.names or "RunRefType" in value.names
        assert "P4" in str(value) and "refuses" in str(value)
    else:
        assert callable(value.record_execution)
        assert hasattr(value.run_ref_type, "PERIOD_LOCK")
        assert hasattr(value.run_ref_type, "RECONCILIATION_RUN")


def test_snapshot_engine_resolves_or_refuses_by_name() -> None:
    state, value = _outcome(dependencies.snapshot_engine)
    if state == "missing":
        assert value.module == dependencies.SNAPSHOT_ENGINE
        assert "GATE-EDS" in str(value)
    else:
        assert len(value.kinds) == 12 and callable(value.manifest_sha256)


def test_snapshot_registry_resolves_or_refuses_by_name() -> None:
    state, value = _outcome(dependencies.snapshot_registry)
    if state == "missing":
        assert value.module == dependencies.SNAPSHOT_REGISTRY
        assert "SNAPSHOT_DATASETS" in value.names or "SnapshotScope" in value.names
        assert "F-RPS" in str(value)
    else:
        assert all(callable(builder) for builder in value.datasets.values())


def test_resolution_names_a_missing_module_and_a_missing_symbol() -> None:
    with pytest.raises(dependencies.ProducerMissing) as absent:
        dependencies.resolve("erev_api.domain.close.no_such_module", ("anything",), "probe lane")
    assert absent.value.module == "erev_api.domain.close.no_such_module"
    assert absent.value.names == ("anything",) and absent.value.owner == "probe lane"
    assert "erev_api.domain.close.no_such_module.anything" in str(absent.value)
    with pytest.raises(dependencies.ProducerMissing) as partial:
        dependencies.resolve(
            "erev_api.domain.close.gates", ("GATE_CHECK_CODES", "NOT_A_SYMBOL"), "probe lane"
        )
    assert partial.value.names == ("NOT_A_SYMBOL",)
    (codes,) = dependencies.resolve("erev_api.domain.close.gates", ("GATE_CHECK_CODES",), "probe")
    assert len(codes) == 14  # 04 T-CLS-02 rev 1.172: CLOSE_RUN_COMPLETED (ruling R-114 (b))
    assert issubclass(dependencies.ProducerMissing, RuntimeError)
