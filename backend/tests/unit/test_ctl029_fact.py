"""CTL-029 fact derivation (P4-CTL029-R1; D-98 candidate 100; REQ-RPT-002; 03 CTL-029): the
control fact recorded for a report run is derived from the rerun comparison computed BEFORE
recording, by the pure ``ctl029_fact`` of ``domain/reports/framework.py``.

First run: PASS with the reproducibility stamp. Rerun of a SUCCEEDED original with equal hash and
totals: PASS. Hash-only or totals-only mismatch: FAIL with one exception and both sides' evidence
retained. Rerun of an original without output: NOT_APPLICABLE, reason ``ORIGINAL_WITHOUT_OUTPUT``.
The run status and job outcome stay SUCCEEDED in every case — a reproducibility failure is a
control exception, not a job failure (05 §5.6 names no FAILED-on-mismatch rule).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from erev_api.controls.evidence import RunRefType, validate_execution
from erev_api.domain.reports.framework import ORIGINAL_WITHOUT_OUTPUT, Ctl029Fact, ctl029_fact
from erev_api.enums import ControlResult

ORIGINAL_ID = UUID("00000000-0000-4000-8000-00000000c029")
SHA_A = "a" * 64
SHA_B = "b" * 64
TOTALS_A: dict[str, Any] = {"client_count": 3}
TOTALS_B: dict[str, Any] = {"client_count": 4}


def _run(sha: str | None = SHA_A, totals: dict[str, Any] | None = TOTALS_A) -> dict[str, Any]:
    return {"output_sha256": sha, "control_totals": totals, "row_count": 3}


def _original(
    status: str = "SUCCEEDED", sha: str | None = SHA_A, totals: dict[str, Any] | None = TOTALS_A
) -> dict[str, Any]:
    return {"status": status, "output_sha256": sha, "control_totals": totals}


def _admitted(fact: Ctl029Fact) -> None:
    """The fact passes the SOP-1 helper rules (PASS ⇒ 0 exceptions, FAIL ⇒ ≥ 1, N/A ⇒ population 0;
    detail strict JSON) — what ``record_execution`` will enforce."""
    validate_execution(
        control_id="CTL-029",
        run_ref_type=RunRefType.REPORT_RUN,
        run_ref_id=ORIGINAL_ID,
        population_count=fact.population_count,
        exception_count=fact.exception_count,
        result=fact.result,
        detail=fact.detail,
    )
    json.dumps(fact.detail, allow_nan=False)


def test_first_run_passes_with_the_reproducibility_stamp() -> None:
    fact = ctl029_fact(_run(), None, rerun_of=None)
    assert (fact.result, fact.population_count, fact.exception_count) == (ControlResult.PASS, 1, 0)
    assert fact.detail["first_run"] is True
    assert fact.detail["output_sha256"] == SHA_A and fact.detail["control_totals"] == TOTALS_A
    assert fact.detail["row_count"] == 3
    assert "rerun_of" not in fact.detail
    assert fact.flags == {}  # a first run's job result carries no equality flags
    _admitted(fact)


def test_rerun_with_identical_hash_and_totals_passes() -> None:
    fact = ctl029_fact(_run(), _original(), rerun_of=ORIGINAL_ID)
    assert (fact.result, fact.population_count, fact.exception_count) == (ControlResult.PASS, 1, 0)
    assert fact.flags == {"output_sha256_equal": True, "control_totals_equal": True}
    assert fact.detail["first_run"] is False and fact.detail["rerun_of"] == str(ORIGINAL_ID)
    assert (
        fact.detail["output_sha256_equal"] is True and fact.detail["control_totals_equal"] is True
    )
    _admitted(fact)


@pytest.mark.parametrize(
    ("original", "expected_flags"),
    [
        (_original(sha=SHA_B), {"output_sha256_equal": False, "control_totals_equal": True}),
        (_original(totals=TOTALS_B), {"output_sha256_equal": True, "control_totals_equal": False}),
        (
            _original(sha=SHA_B, totals=TOTALS_B),
            {"output_sha256_equal": False, "control_totals_equal": False},
        ),
    ],
    ids=["hash-only-mismatch", "totals-only-mismatch", "both-mismatch"],
)
def test_rerun_mismatch_fails_and_retains_both_sides(
    original: dict[str, Any], expected_flags: dict[str, bool]
) -> None:
    fact = ctl029_fact(_run(), original, rerun_of=ORIGINAL_ID)
    assert (fact.result, fact.population_count, fact.exception_count) == (ControlResult.FAIL, 1, 1)
    assert fact.flags == expected_flags
    detail = fact.detail
    assert detail["first_run"] is False and detail["rerun_of"] == str(ORIGINAL_ID)
    assert {k: detail[k] for k in expected_flags} == expected_flags
    # Evidence retained, never overwritten: the original's AND the rerun's hash / totals.
    assert detail["original"] == {
        "output_sha256": original["output_sha256"],
        "control_totals": original["control_totals"],
    }
    assert detail["rerun"] == {"output_sha256": SHA_A, "control_totals": TOTALS_A, "row_count": 3}
    _admitted(fact)


@pytest.mark.parametrize(
    "original",
    [
        _original(status="FAILED", sha=None, totals=None),
        _original(status="SUCCEEDED", sha=None, totals=TOTALS_A),
        _original(status="SUCCEEDED", sha=SHA_A, totals=None),
    ],
    ids=["original-FAILED", "hash-null", "totals-null"],
)
def test_rerun_of_original_without_output_is_not_applicable(original: dict[str, Any]) -> None:
    fact = ctl029_fact(_run(), original, rerun_of=ORIGINAL_ID)
    assert (fact.result, fact.population_count, fact.exception_count) == (
        ControlResult.NOT_APPLICABLE,
        0,
        0,
    )
    assert fact.detail["reason"] == ORIGINAL_WITHOUT_OUTPUT == "ORIGINAL_WITHOUT_OUTPUT"
    assert fact.detail["rerun_of"] == str(ORIGINAL_ID) and fact.detail["first_run"] is False
    assert fact.detail["original"]["status"] == original["status"]
    # The job result keeps today's shape: a missing side compares unequal.
    assert fact.flags == {"output_sha256_equal": False, "control_totals_equal": False}
    _admitted(fact)


def test_fact_is_pure_and_does_not_mutate_its_inputs() -> None:
    run, original = _run(), _original(totals=TOTALS_B)
    before = (json.dumps(run, sort_keys=True), json.dumps(original, sort_keys=True))
    ctl029_fact(run, original, rerun_of=ORIGINAL_ID)
    assert (json.dumps(run, sort_keys=True), json.dumps(original, sort_keys=True)) == before
