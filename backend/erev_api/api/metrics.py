"""``GET /metrics`` (04 API-R-53; 05 MET-01 to MET-11; BUILD_SPEC SOP-4; REQ-OPS-012).

Served by the api process only (BS1-D-36), outside ``/api/v1`` and outside the OpenAPI document,
when ``EREV_METRICS_ENABLED`` is true; the caller presents ``Authorization: Bearer
<EREV_METRICS_TOKEN>``. The exposition is the Prometheus text format 0.0.4. Metric names, kinds
and label sets come from ``erev_api.controls.metrics`` (kernel definitions); this module holds the
process registry and the route.

What this process measures itself: MET-01 / MET-02 from ``RequestLifecycleMiddleware`` (route
template, method, status class, duration) and MET-11 from the api engine's pool. The worker-side
figures MET-03 to MET-10 are exposed with their ``# HELP`` / ``# TYPE`` lines and the samples the
process has observed (none until the scrape-time database read of BS1-D-36 lands — recorded OPEN in
the lane record). Label values never hold tenant ids, user ids or amounts: every sample passes
``controls.metrics.validate_labels`` before it is stored.
"""

from __future__ import annotations

import math
import secrets
import threading
from collections.abc import Mapping
from typing import Final

from fastapi import Request, Response
from starlette.responses import PlainTextResponse

from erev_api.config import Settings
from erev_api.controls.metrics import (
    HTTP_DURATION_BUCKETS,
    METRICS,
    METRICS_BY_NAME,
    MetricDefinition,
    validate_labels,
)
from erev_api.db.session import app_engine
from erev_api.problems import Problem

CONTENT_TYPE: Final = "text/plain; version=0.0.4"
UNMATCHED_ROUTE: Final = "unmatched"
BEARER: Final = "bearer"
Labels = tuple[tuple[str, str], ...]


class MetricsRegistry:
    """In-process counters, histograms and gauges keyed by metric name and sorted label pairs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, Labels], float] = {}
        self._gauges: dict[tuple[str, Labels], float] = {}
        self._histograms: dict[tuple[str, Labels], tuple[list[int], float, int]] = {}

    @staticmethod
    def _key(definition: MetricDefinition, labels: Mapping[str, str]) -> tuple[str, Labels]:
        validate_labels(definition, labels)
        return definition.name, tuple(sorted(labels.items()))

    def increment(self, name: str, labels: Mapping[str, str], value: float = 1.0) -> None:
        key = self._key(METRICS_BY_NAME[name], labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, labels: Mapping[str, str], value: float) -> None:
        key = self._key(METRICS_BY_NAME[name], labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, labels: Mapping[str, str], value: float) -> None:
        key = self._key(METRICS_BY_NAME[name], labels)
        with self._lock:
            buckets, total, count = self._histograms.get(
                key, ([0] * (len(HTTP_DURATION_BUCKETS) + 1), 0.0, 0)
            )
            for index, upper in enumerate(HTTP_DURATION_BUCKETS):
                if value <= upper:
                    buckets[index] += 1
            buckets[-1] += 1  # +Inf
            self._histograms[key] = (buckets, total + value, count + 1)

    def render(self) -> str:
        """Prometheus text format 0.0.4: every MET definition, samples where observed."""
        lines: list[str] = []
        with self._lock:
            for definition in METRICS:
                lines.append(f"# HELP {definition.name} {definition.id} ({definition.kind})")
                lines.append(f"# TYPE {definition.name} {definition.kind}")
                if definition.kind == "counter":
                    for (name, labels), value in sorted(self._counters.items()):
                        if name == definition.name:
                            lines.append(f"{name}{_labels(labels)} {_number(value)}")
                elif definition.kind == "gauge":
                    for (name, labels), value in sorted(self._gauges.items()):
                        if name == definition.name:
                            lines.append(f"{name}{_labels(labels)} {_number(value)}")
                else:
                    for (name, labels), (buckets, total, count) in sorted(self._histograms.items()):
                        if name != definition.name:
                            continue
                        for index, upper in enumerate(HTTP_DURATION_BUCKETS):
                            bucket = _labels(labels, le=_number(upper))
                            lines.append(f"{name}_bucket{bucket} {buckets[index]}")
                        lines.append(f"{name}_bucket{_labels(labels, le='+Inf')} {buckets[-1]}")
                        lines.append(f"{name}_sum{_labels(labels)} {_number(total)}")
                        lines.append(f"{name}_count{_labels(labels)} {count}")
        return "\n".join(lines) + "\n"


def _labels(labels: Labels, **extra: str) -> str:
    pairs = [*labels, *sorted(extra.items())]
    if not pairs:
        return ""
    return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in pairs) + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    return str(int(value)) if float(value).is_integer() else repr(float(value))


REGISTRY: Final = MetricsRegistry()


def status_class(status: int | None) -> str:
    """``2xx`` … ``5xx``; ``unknown`` when the response never started."""
    return "unknown" if status is None else f"{status // 100}xx"


def observe_http(route: str | None, method: str, status: int | None, seconds: float) -> None:
    """MET-01 and MET-02 for one request (called by the lifecycle middleware)."""
    template = route or UNMATCHED_ROUTE
    REGISTRY.increment(
        "erev_http_requests_total",
        {"route": template, "method": method.upper(), "status_class": status_class(status)},
    )
    REGISTRY.observe(
        "erev_http_request_duration_seconds",
        {"route": template, "method": method.upper()},
        max(seconds, 0.0),
    )


def _pool_in_use() -> None:
    """MET-11 for this process: connections checked out of the api engine's pool."""
    pool = app_engine().pool
    checked_out = getattr(pool, "checkedout", None)
    if callable(checked_out):
        REGISTRY.set_gauge("erev_db_pool_in_use", {"component": "api"}, float(checked_out()))


def _authorised(request: Request, settings: Settings) -> bool:
    token = settings.metrics_token
    if token is None:
        return False
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != BEARER or not presented.strip():
        return False
    # Compared as bytes: ``compare_digest`` refuses a str with a non-ASCII character, which made a
    # malformed bearer a 500 instead of a 401 (R-34 SD-4). Starlette decodes header bytes as
    # latin-1, so encoding them back gives the bytes the client sent.
    return secrets.compare_digest(
        presented.strip().encode("latin-1", "replace"), token.get_secret_value().encode("utf-8")
    )


def metrics_endpoint(request: Request) -> Response:
    """``GET /metrics``: 404 while disabled (REQ-OPS-012 default), 401 without the bearer, else
    the exposition. No tenant context is read or required."""
    settings: Settings = request.app.state.settings
    if not settings.metrics_enabled:
        raise Problem("not-found")
    if not _authorised(request, settings):
        raise Problem("unauthenticated")
    _pool_in_use()
    return PlainTextResponse(REGISTRY.render(), media_type=CONTENT_TYPE)
