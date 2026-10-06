"""SOP-1 control-evidence registry, the database-free half: ``RunRefType`` mirrors 04 T-PLT-39,
``validate_execution`` applies the helper-side rules every producer shares (agreed with lane F-CLO;
supervisor rulings of 2026-09-19), and the API-R-52 schemas carry the T-PLT-39 / T-PLT-38 columns.

``record_execution`` (the insert) and the producers land with the T-PLT-39 revision
(``tests/domain/platform/test_control_evidence.py``); this module never touches a database.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.controls.evidence import (
    CONTROL_ID,
    ExecutionRecord,
    RunRefType,
    validate_execution,
)
from erev_api.controls.registry import controls
from erev_api.enums import BookCode, ControlResult
from erev_api.schemas.controls import ControlExecutionOut, ReleaseOut

ROOT = Path(__file__).resolve().parents[3]
RUN_ID = UUID("00000000-0000-4000-8000-000000000001")
NON_FINITE = "detail must not contain non-finite numbers"
NESTED_KEYS = "detail nested objects must have string keys"


def _valid(**overrides: Any) -> ExecutionRecord:
    values: dict[str, Any] = {
        "control_id": "CTL-039",
        "run_ref_type": RunRefType.AUDIT_CHAIN_VERIFICATION,
        "run_ref_id": RUN_ID,
        "population_count": 120,
        "exception_count": 0,
        "result": ControlResult.PASS,
    }
    values.update(overrides)
    return validate_execution(**values)


def test_run_ref_type_mirrors_04_t_plt_39() -> None:
    text = (ROOT / "docs/04-DATA_MODEL.md").read_text(encoding="utf-8")
    start = text.index("### T-PLT-39 `control_execution`")
    row = next(
        line for line in text[start:].splitlines() if line.startswith("| `run_ref_type` | text |")
    )
    listed = re.findall(r"`([A-Z_]+)`", row.split("|")[5].split("(rev")[0])
    assert [member.value for member in RunRefType] == listed
    assert listed[-2:] == ["RECONCILIATION_RUN", "PERIOD_LOCK"]
    assert len(RunRefType) == 10


def test_validate_execution_accepts_the_agreed_shape() -> None:
    record = _valid(
        detail={"checked": [1, 2], "note": "as given", "Nested": {"z": 1, "a": 2}},
        entity_id=UUID("00000000-0000-4000-8000-0000000000e1"),
        book_code="ASC606",
        period_id=UUID("00000000-0000-4000-8000-0000000000a1"),
    )
    assert (
        record.control_id == "CTL-039"
        and record.run_ref_type is RunRefType.AUDIT_CHAIN_VERIFICATION
    )
    assert record.result is ControlResult.PASS and record.book_code is BookCode.ASC606
    # detail is stored as given: keys and order untouched, nested values intact.
    assert list(record.detail) == ["checked", "note", "Nested"]
    assert record.detail["Nested"] == {"z": 1, "a": 2}
    assert _valid().detail == {} and _valid().exceptions_file_id is None
    failing = _valid(result=ControlResult.FAIL, exception_count=3, exceptions_file_id=uuid4())
    assert failing.exception_count == 3
    not_applicable = _valid(result=ControlResult.NOT_APPLICABLE, population_count=0)
    assert not_applicable.population_count == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"control_id": "CTL-50"}, "control_id must match"),
        ({"control_id": "ctl-039"}, "control_id must match"),
        ({"control_id": "CTL-999"}, "not in controls.yaml"),
        ({"run_ref_type": "AUDIT_CHAIN_VERIFICATION"}, "run_ref_type must be a RunRefType"),
        ({"run_ref_id": "not-a-uuid"}, "run_ref_id must be a UUID"),
        ({"population_count": -1}, "population_count must be a non-negative int"),
        ({"exception_count": True}, "exception_count must be a non-negative int"),
        ({"population_count": 1.0}, "population_count must be a non-negative int"),
        ({"result": "PASS"}, "result must be a ControlResult"),
        (
            {"result": ControlResult.PASS, "exception_count": 1},
            "PASS requires exception_count == 0",
        ),
        (
            {"result": ControlResult.FAIL, "exception_count": 0},
            "FAIL requires exception_count >= 1",
        ),
        (
            {"result": ControlResult.NOT_APPLICABLE, "population_count": 2},
            "NOT_APPLICABLE requires population_count == 0",
        ),
        ({"detail": ["not", "a", "mapping"]}, "detail must be a mapping with string keys"),
        ({"detail": {1: "x"}}, "detail must be a mapping with string keys"),
        ({"detail": {"when": object()}}, "detail must be JSON-serialisable"),
        # Codex P4-S1-R1 (exact inputs): non-finite numbers anywhere in detail.
        ({"detail": {"totals": {"value": float("nan")}}}, NON_FINITE),
        ({"detail": {"totals": {"value": float("inf")}}}, NON_FINITE),
        ({"detail": {"totals": {"value": float("-inf")}}}, NON_FINITE),
        ({"detail": {"value": float("nan")}}, NON_FINITE),
        ({"detail": {"rows": [[1.0, float("inf")]]}}, NON_FINITE),
        # Codex P4-S1-R2 (exact input): non-string object keys below the top level.
        ({"detail": {"counts": {1: "first", "1": "second"}}}, NESTED_KEYS),
        ({"detail": {"rows": [{1: "x"}]}}, NESTED_KEYS),
        ({"detail": {"a": {"b": [[{"c": {None: 0}}]]}}}, NESTED_KEYS),
        ({"book_code": "GAAP"}, "book_code must be a BookCode"),
        ({"entity_id": "e1"}, "entity_id must be a UUID or None"),
        ({"period_id": 7}, "period_id must be a UUID or None"),
        ({"exceptions_file_id": "f"}, "exceptions_file_id must be a UUID or None"),
    ],
)
def test_validate_execution_refuses_a_producer_bug(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        _valid(**overrides)


def test_detail_is_strict_json_at_every_depth_and_stored_as_given() -> None:
    """Codex P4-S1-R1/R2 positives: finite nested numbers and nested all-string keys, objects
    inside arrays included, are valid and round-trip through strict JSON unchanged."""
    given = {
        "totals": {"value": 1.5, "ratios": [0.25, -2.0, 1e300, 0]},
        "counts": {"1": "first", "01": "second"},
        "rows": [{"k": [{"z": 0, "ok": True, "none": None}]}, [[]], {}],
    }
    record = _valid(detail=given)
    assert record.detail == given and list(record.detail) == list(given)
    assert json.loads(json.dumps(record.detail, allow_nan=False)) == given


def test_fail_with_empty_population_stays_admitted() -> None:
    """No ``exception_count <= population_count`` rule exists (Codex P4-S1 disposition)."""
    record = _valid(result=ControlResult.FAIL, population_count=0, exception_count=1)
    assert (record.population_count, record.exception_count) == (0, 1)


def test_control_ids_come_from_the_registry() -> None:
    assert CONTROL_ID.fullmatch("CTL-001") and not CONTROL_ID.fullmatch("CTL-1")
    assert all(CONTROL_ID.fullmatch(control_id) for control_id in controls())
    # Every producer P4 or F-CLO wires is a registered control.
    for control_id in (
        "CTL-001",
        "CTL-002",
        "CTL-012",
        "CTL-016",
        "CTL-019",
        "CTL-020",
        "CTL-021",
        "CTL-022",
        "CTL-024",
        "CTL-025",
        "CTL-026",
        "CTL-029",
        "CTL-030",
        "CTL-039",
        "CTL-044",
    ):
        assert control_id in controls(), control_id


def test_api_r_52_schemas_carry_the_table_columns() -> None:
    assert set(ControlExecutionOut.model_fields) == {
        "id",
        "control_id",
        "run_ref_type",
        "run_ref_id",
        "entity_id",
        "book_code",
        "period_id",
        "population_count",
        "exception_count",
        "result",
        "detail",
        "exceptions_file_id",
        "engine_release_id",
        "executed_at",
    }
    assert set(ReleaseOut.model_fields) == {
        "id",
        "engine_version",
        "build_sha",
        "schema_revision",
        "control_impact_tags",
        "gate_results",
        "deployed_at",
    }
    assert ControlExecutionOut.model_fields["run_ref_type"].annotation is RunRefType
