"""Supported overrides execute normally; unsupported declarations can never pass by omission."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from support.answer_keys.loader import LoadedKey
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, load_platform_key
from support.answer_keys.platform_runner import (
    COMPARED,
    DB,
    ERROR,
    BlockOutcome,
    PlatformCheckpoint,
    PlatformRunResult,
    key_verdict,
    override_finding,
    run_platform,
)
from support.answer_keys.report import OUTCOMES, KeyOutcome
from support.answer_keys.runners import Mismatch

CLEAN = "every block compared clean on the db platform"


def _clean_on_the_database(loaded: LoadedKey) -> PlatformRunResult:
    checkpoints = tuple(
        PlatformCheckpoint(
            point.name,
            point.after_seq,
            datetime(2026, 1, 31, 12, tzinfo=UTC),
            (BlockOutcome("contracts", COMPARED),),
        )
        for point in loaded.key.checkpoints
    )
    return PlatformRunResult(loaded.key.id, "platform", DB, (), {}, checkpoints, ("platform: db",))


def _unsupported() -> LoadedKey:
    loaded = load_platform_key(PLATFORM_KEY_IDS[0])
    first, *rest = loaded.key.contracts
    original = (first.policy_overrides or ())[0]
    changed = original.model_copy(
        update={
            "policy_key": "fx.cl_historical_layering",
            "obligation_key": None,
            "value": "DISABLED_REMEASURE_AS_MONETARY",
        }
    )
    contract = first.model_copy(update={"policy_overrides": (changed,)})
    return replace(loaded, key=loaded.key.model_copy(update={"contracts": (contract, *rest)}))


@pytest.mark.parametrize("key_id", PLATFORM_KEY_IDS)
def test_supported_declared_policies_add_no_obsolete_failure(key_id: str) -> None:
    loaded = load_platform_key(key_id)
    assert override_finding(loaded.key) is None
    assert key_verdict(loaded, _clean_on_the_database(loaded)) == ("passed", (), CLEAN)


def test_unsupported_policy_stays_a_failure_even_if_every_figure_compares_clean() -> None:
    loaded = _unsupported()
    finding = override_finding(loaded.key)
    assert finding is not None
    assert "POL-163" in finding.expected and "1 APPROVED" in finding.expected
    status, mismatches, message = key_verdict(loaded, _clean_on_the_database(loaded))
    assert status == "failed" and mismatches == (finding,)
    assert "POLICY_OVERRIDE_NOT_OFFERED" in message


def test_in_memory_and_error_results_cannot_be_promoted_to_passed() -> None:
    loaded = load_platform_key(PLATFORM_KEY_IDS[0])
    assert key_verdict(loaded, run_platform(loaded))[0] == "not_run"
    unsupported = _unsupported()
    result = _clean_on_the_database(unsupported)
    first, *rest = result.checkpoints
    figure = Mismatch(loaded.key.id, first.name, "contract", "revenue_cum", "80000.00", "0.00")
    wrong = replace(
        result,
        checkpoints=(
            replace(first, blocks=(BlockOutcome("contracts", COMPARED, (figure,)),)),
            *rest,
        ),
    )
    status, mismatches, _ = key_verdict(unsupported, wrong)
    assert status == "failed" and mismatches == (figure, override_finding(unsupported.key))
    stopped = replace(
        result,
        checkpoints=(
            replace(first, blocks=(BlockOutcome("contracts", ERROR, reason="E-1 x"),)),
            *rest,
        ),
    )
    assert key_verdict(loaded, stopped)[0] == "failed"


def _node_module() -> ModuleType:
    """``tests/answer_keys/test_answer_keys.py``, the module of the keys' pytest nodes, loaded
    under a name of its own (the test directories are no packages)."""
    path = Path(__file__).resolve().parents[2] / "answer_keys" / "test_answer_keys.py"
    spec = importlib.util.spec_from_file_location("answer_key_nodes_for_the_override_tie", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_pytest_node_records_supported_pass_and_unsupported_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = _node_module()
    monkeypatch.setattr(node, "run_platform", _clean_on_the_database)
    outcomes: dict[str, KeyOutcome] = {}
    request: Any = SimpleNamespace(config=SimpleNamespace(stash={OUTCOMES: outcomes}))
    supported = load_platform_key(PLATFORM_KEY_IDS[0])
    node._platform_key(supported, request)
    assert outcomes[supported.key.id] == KeyOutcome("passed", (), CLEAN, ("platform: db",))
    unsupported = _unsupported()
    with pytest.raises(pytest.fail.Exception, match="POLICY_OVERRIDE_NOT_OFFERED"):
        node._platform_key(unsupported, request)
    assert outcomes[unsupported.key.id].result == "failed"
