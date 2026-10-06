"""``erev_api.metrics``: MET-01 to MET-11 definitions equal the 05 table; label safety (SOP-4;
REQ-OPS-012; lane P5 preparation slice). DB-free."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from erev_api.controls.metrics import (
    FORBIDDEN_LABEL_KEYS,
    HTTP_DURATION_BUCKETS,
    METRICS,
    METRICS_BY_NAME,
    label_value_allowed,
    validate_labels,
)

ARCHITECTURE = Path(__file__).resolve().parents[3] / "docs" / "05-ARCHITECTURE.md"


def _table_05() -> list[tuple[str, str, str, tuple[str, ...]]]:
    rows: list[tuple[str, str, str, tuple[str, ...]]] = []
    for line in ARCHITECTURE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| MET-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        met_id, name, kind, labels = cells[0], cells[1].strip("`"), cells[2], cells[3]
        kind_word = kind.split(" ")[0]
        label_names = tuple(re.findall(r"`([a-z_]+)`", labels)) if labels != "none" else ()
        rows.append((met_id, name, kind_word, label_names))
    return rows


def test_definitions_equal_the_05_met_table() -> None:
    table = _table_05()
    assert len(table) == 11
    assert [(m.id, m.name, m.kind, m.labels) for m in METRICS] == table
    assert set(METRICS_BY_NAME) == {row[1] for row in table}
    assert METRICS_BY_NAME["erev_http_request_duration_seconds"].buckets == HTTP_DURATION_BUCKETS
    assert HTTP_DURATION_BUCKETS[0] == 0.025 and HTTP_DURATION_BUCKETS[-1] == 10.0
    assert METRICS_BY_NAME["erev_audit_chain_verification_failures_total"].labels == ()


def test_labels_never_carry_ids_or_amounts() -> None:
    assert not label_value_allowed(str(uuid4()))
    assert not label_value_allowed("1200.00") and not label_value_allowed("-0.01")
    assert (
        label_value_allowed("compute") and label_value_allowed("2xx") and label_value_allowed("42")
    )
    jobs = METRICS_BY_NAME["erev_jobs_total"]
    validate_labels(jobs, {"kind": "CONTRACT_COMPUTE", "outcome": "SUCCEEDED"})
    with pytest.raises(ValueError, match="labels"):
        validate_labels(jobs, {"kind": "CONTRACT_COMPUTE"})
    with pytest.raises(ValueError, match="id or an amount"):
        validate_labels(jobs, {"kind": str(uuid4()), "outcome": "SUCCEEDED"})
    http = METRICS_BY_NAME["erev_http_requests_total"]
    with pytest.raises(ValueError, match="labels"):
        validate_labels(
            http, {"route": "/x", "method": "GET", "status_class": "2xx", "tenant_id": "t"}
        )
    assert {"tenant_id", "user_id", "amount"} <= FORBIDDEN_LABEL_KEYS
    assert not any(set(m.labels) & FORBIDDEN_LABEL_KEYS for m in METRICS)
