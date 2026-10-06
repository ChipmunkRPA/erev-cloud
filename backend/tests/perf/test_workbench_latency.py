"""PRF-5 workbench latency and endpoint mix (dev-guide DG-PERF-03, DG-PERF-04; 05 PERF-02, PERF-30;
REQ-OPS-008; G9). Runs only under ``make perf`` against the perf sandbox — Ray-side; NOT RUN in
the
lane. ``test_workbench_p95`` is the pass criterion; ``test_endpoint_mix_reported`` reports only.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from perf.support import latency, report
from perf.support.client import PerfClient, PerfClients

pytestmark = pytest.mark.perf
ROOT = Path(__file__).resolve().parents[3]


def _contracts(controller: PerfClient, limit: int = 2_000) -> list[tuple[str, int]]:
    """(contract id, obligation count) over the sandbox's contract list (keyset pages)."""
    out: list[tuple[str, int]] = []
    cursor: str | None = None
    while len(out) < limit:
        params: dict[str, object] = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        page = controller.get("/contracts", params)
        for item in page.get("items", []):
            out.append((str(item["id"]), int(item.get("obligation_count", 0))))
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return out


@pytest.fixture(scope="module")
def sampled(perf_prepared: object, perf_clients: PerfClients) -> list[tuple[str, int]]:
    return _contracts(perf_clients.controller)


def test_workbench_p95(
    sampled: list[tuple[str, int]],
    perf_client_factory: object,
    perf_report: report.PerfReport,
) -> None:
    """For the seven DG-PERF-03 endpoints: 20 warm-up then 200 measured requests from 4 concurrent
    httpx clients over contract ids sampled with seed 20260912; nearest-rank p95 ≤ 300 ms each."""
    ids = latency.sample_ids([contract_id for contract_id, _ in sampled], latency.MEASURED)
    measurements = {
        name: latency.measure_endpoint(
            perf_client_factory,  # type: ignore[arg-type]
            path,
            ids,
            endpoint=name,
        )
        for name, path in latency.ENDPOINTS.items()
    }
    perf_report.latency = report.latency_section(measurements)
    slow = {name: m.p95_ms for name, m in measurements.items() if m.p95_ms > latency.P95_LIMIT_MS}
    failed = {name: m.failures for name, m in measurements.items() if m.failures}
    assert not failed, f"requests failed: {failed}"
    assert not slow, f"p95 above {latency.P95_LIMIT_MS:.0f} ms: {slow}"


def test_endpoint_mix_reported(
    sampled: list[tuple[str, int]],
    perf_client_factory: object,
    perf_report: report.PerfReport,
) -> None:
    """2,000 requests with concurrency 8 over the PERF-30 mix against 200 contracts stratified by
    obligation count; p95 server time per endpoint from ``duration_ms`` in .run/api-perf.log is
    recorded in the report and not asserted (DG-PERF-04)."""
    ids = latency.stratified_sample(sampled, latency.MIX_CONTRACTS)
    log_path = Path(os.environ.get("EREV_RUN_DIR", str(ROOT / ".run"))) / "api-perf.log"
    before = (
        len(log_path.read_text(encoding="utf-8", errors="replace").splitlines())
        if log_path.exists()
        else 0
    )
    sent = latency.replay_mix(perf_client_factory, ids)  # type: ignore[arg-type]
    lines = (
        log_path.read_text(encoding="utf-8", errors="replace").splitlines()[before:]
        if log_path.exists()
        else []
    )
    by_route: dict[str, list[float]] = {}
    for logged in latency.parse_request_log(lines):
        by_route.setdefault(logged.route, []).append(logged.duration_ms)
    perf_report.mix = {
        "requests": sum(sent.values()),
        "concurrency": latency.MIX_CONCURRENCY,
        "contracts": len(ids),
        "sent_by_family": sent,
        "server_ms_by_route": {
            route: latency.summarise(samples) for route, samples in sorted(by_route.items())
        },
    }
    assert sum(sent.values()) == latency.MIX_REQUESTS
