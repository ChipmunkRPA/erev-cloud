"""Metric definitions of 05 MET-01 to MET-11 (SOP-4; REQ-OPS-012; lane P5 preparation slice).

Kernel module (DG-LAY-03 ``controls``) so that both the api route and the worker emitters may import
it without an upward import (DG-ARC-01).

Pure definitions and label-safety predicates only — the ``GET /metrics`` route, the Prometheus
registry and the sampled worker figures are the integration slice (``erev_api/api/metrics.py``,
served by the api process only per BS1-D-36, bearer ``EREV_METRICS_TOKEN``). The one rule this
module enforces early: **labels never hold tenant ids, user ids or amounts** (05 MET; SOP-4).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

__all__ = [
    "FORBIDDEN_LABEL_KEYS",
    "HTTP_DURATION_BUCKETS",
    "METRICS",
    "METRICS_BY_NAME",
    "MetricDefinition",
    "label_value_allowed",
    "validate_labels",
]

MetricKind = Literal["counter", "histogram", "gauge"]

# MET-02: histogram buckets 0.025 to 10 s.
HTTP_DURATION_BUCKETS: Final = (0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    id: str  # MET-nn
    name: str
    kind: MetricKind
    labels: tuple[str, ...]
    buckets: tuple[float, ...] | None = None
    note: str | None = None


METRICS: Final[tuple[MetricDefinition, ...]] = (
    MetricDefinition(
        "MET-01", "erev_http_requests_total", "counter", ("route", "method", "status_class")
    ),
    MetricDefinition(
        "MET-02",
        "erev_http_request_duration_seconds",
        "histogram",
        ("route", "method"),
        HTTP_DURATION_BUCKETS,
    ),
    MetricDefinition("MET-03", "erev_jobs_total", "counter", ("kind", "outcome")),
    MetricDefinition("MET-04", "erev_job_duration_seconds", "histogram", ("kind",)),
    MetricDefinition(
        "MET-05", "erev_job_queue_depth", "gauge", ("queue",), note="sampled every 30 s"
    ),
    MetricDefinition(
        "MET-06", "erev_computation_duration_seconds", "histogram", ("trigger", "status")
    ),
    MetricDefinition("MET-07", "erev_close_step_duration_seconds", "histogram", ("step",)),
    MetricDefinition("MET-08", "erev_outbox_messages", "gauge", ("topic", "status")),
    MetricDefinition("MET-09", "erev_export_failures_total", "counter", ("adapter",)),
    MetricDefinition("MET-10", "erev_audit_chain_verification_failures_total", "counter", ()),
    MetricDefinition("MET-11", "erev_db_pool_in_use", "gauge", ("component",)),
)
METRICS_BY_NAME: Final[Mapping[str, MetricDefinition]] = {item.name: item for item in METRICS}

# Label keys that would carry an identity or a value the endpoint must never expose.
FORBIDDEN_LABEL_KEYS: Final = frozenset(
    {"tenant", "tenant_id", "user", "user_id", "amount", "amount_txn", "amount_functional"}
)
_UUID: Final = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_AMOUNT: Final = re.compile(r"^-?[0-9]+\.[0-9]+$")


def label_value_allowed(value: str) -> bool:
    """False for a UUID (tenant or user id) or a decimal amount; the SOP-4 acceptance asserts no
    label value matches either shape."""
    return not (_UUID.match(value) or _AMOUNT.match(value))


def validate_labels(definition: MetricDefinition, labels: Mapping[str, str]) -> None:
    """The label set of a sample: exactly the definition's keys, no forbidden key, no forbidden
    value shape. Raises ``ValueError`` — the emitter must drop or generalise the sample."""
    if set(labels) != set(definition.labels):
        raise ValueError(
            f"{definition.name}: labels {sorted(labels)} != {sorted(definition.labels)}"
        )
    forbidden = sorted(set(labels) & FORBIDDEN_LABEL_KEYS)
    if forbidden:
        raise ValueError(f"{definition.name}: forbidden label keys {forbidden}")
    for key, value in labels.items():
        if not label_value_allowed(value):
            raise ValueError(f"{definition.name}: label {key} carries an id or an amount")
