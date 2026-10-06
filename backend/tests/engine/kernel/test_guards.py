"""Bundle guards and engine errors (dev-guide §7 DG-ENG-03, DG-ENG-06; ENGINE_SPEC CV-45)."""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import erev_engine
import pytest
from erev_engine.errors import EngineError
from erev_engine.guards import assert_sorted, no_floats


@dataclass(frozen=True, slots=True)
class Holder:
    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Clean:
    ratio: Fraction
    amount: Decimal
    minor: int
    key: str
    effective: date


def test_no_floats_detects_nested_float() -> None:
    with pytest.raises(EngineError) as error:
        no_floats(Holder(values=(Fraction(1, 2), 0.5)))
    assert error.value.code == "FLOAT_DETECTED"
    assert error.value.detail == {"path": "$.values[1]"}
    no_floats(Clean(Fraction(1, 3), Decimal("1.25"), 125, "POB-001", date(2026, 1, 31)))
    no_floats({"lines": [Clean(Fraction(0), Decimal(0), 0, "", date(2026, 1, 1))], "x": None})
    with pytest.raises(EngineError):
        no_floats({"weights": frozenset({1, 2.0})})
    with pytest.raises(TypeError):
        no_floats(Holder(values=(object(),)))


_NO_FLOATS_PROBE = (
    "import json, sys\n"
    "from erev_engine.errors import EngineError\n"
    "from erev_engine.guards import no_floats\n"
    "try:\n"
    "    no_floats(frozenset({'alpha', 'beta', 'gamma', 'delta', 1.5}))\n"
    "except EngineError as error:\n"
    "    sys.stdout.write(json.dumps([error.code, error.detail], sort_keys=True))\n"
)


def test_no_floats_detail_independent_of_hash_seed() -> None:
    # Set iteration order follows string hashes, which PYTHONHASHSEED randomises (DG-ENG-02).
    backend = Path(erev_engine.__file__).resolve().parents[1]
    outputs = []
    for seed in ("1", "3", "10"):
        environment = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(backend)}
        completed = subprocess.run(
            [sys.executable, "-c", _NO_FLOATS_PROBE],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        outputs.append(json.loads(completed.stdout))
    assert outputs[0][0] == "FLOAT_DETECTED"
    assert outputs == [outputs[0]] * 3
    assert outputs[0][1] == {"path": "$[0]"}


def test_assert_sorted_rejects_unsorted_and_duplicate_keys() -> None:
    events = [("2026-01-01", 1), ("2026-01-01", 2), ("2026-02-01", 1)]
    assert_sorted(events, key=lambda event: event, name="events")
    with pytest.raises(ValueError, match="events"):
        assert_sorted(events[::-1], key=lambda event: event, name="events")
    with pytest.raises(ValueError):
        assert_sorted(["a", "a"], key=str, name="keys")
    assert_sorted(["a", "a"], key=str, name="keys", unique=False)


def test_engine_error_fields_and_pickling() -> None:
    error = EngineError(
        "NEGATIVE_WEIGHT", "an allocation weight is negative", subject_key="POB-002", detail={}
    )
    assert str(error) == "NEGATIVE_WEIGHT: an allocation weight is negative"
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - round trip of our own object
    assert (restored.code, restored.subject_key, restored.detail) == (
        "NEGATIVE_WEIGHT",
        "POB-002",
        {},
    )
