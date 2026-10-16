"""Comparison evidence cannot silently lose details when assembled into a dataset."""

from typing import Any
from uuid import uuid4

import pytest
from erev_api.domain.contracts import validation_artifacts
from erev_api.problems import Problem


@pytest.mark.parametrize("outcome", ["MATCH", "DIFFERENCES"])
def test_candidate_comparison_requires_retained_detail(outcome: str) -> None:
    row: dict[str, Any] = {
        "trigger": "UPGRADE_VALIDATE",
        "outcome": outcome,
        "difference_summary": None,
        "difference_file_id": None,
    }
    with pytest.raises(Problem):
        validation_artifacts.differences(None, row)  # type: ignore[arg-type]


@pytest.mark.parametrize("mutation", ["format", "task", "identity", "category", "summary", "shape"])
def test_difference_reader_refuses_malformed_bound_content(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    row: dict[str, Any] = {
        name: uuid4()
        for name in (
            "id",
            "release_validation_attempt_id",
            "combination_group_id",
            "source_computation_id",
            "process_engine_release_id",
            "job_id",
            "difference_file_id",
        )
    }
    summary = {"M": 0, "P": 0, "T": 1, "R": 0, "changed_r_paths": []}
    row.update(
        trigger="UPGRADE_VALIDATE",
        outcome="DIFFERENCES",
        engine_executed=True,
        task_id=1,
        attempt=1,
        difference_summary=summary,
    )
    payload = {
        key: str(row[key])
        for key in (
            "release_validation_attempt_id",
            "combination_group_id",
            "source_computation_id",
            "process_engine_release_id",
            "job_id",
        )
    }
    content: dict[str, Any] = {
        **payload,
        "verification_id": str(row["id"]),
        "difference_format": 1,
        "task_id": 1,
        "attempt": 1,
        "summary": summary,
        "differences": [{"path": "diagnostics", "category": "T", "before": [], "after": ["x"]}],
    }
    monkeypatch.setattr(validation_artifacts, "_read", lambda *args: content)
    assert len(validation_artifacts.differences(None, row)) == 1  # type: ignore[arg-type]
    if mutation == "format":
        content["difference_format"] = True
    elif mutation == "task":
        content["task_id"] = True
    elif mutation == "identity":
        content["verification_id"] = str(uuid4())
    elif mutation == "category":
        content["differences"][0]["category"] = []
    elif mutation == "summary":
        content["differences"] = []
    else:
        del content["differences"][0]["before"]
    with pytest.raises(Problem):
        validation_artifacts.differences(None, row)  # type: ignore[arg-type]
