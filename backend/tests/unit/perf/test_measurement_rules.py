"""PRF-4 / PRF-5 pure measurement rules (dev-guide DG-PERF-02 to DG-PERF-04; 05 PERF-30, PERF-50):
nearest-rank percentiles, seeded and stratified sampling, the PERF-30 plan, the request-log parser,
close-step seconds and the trial-balance aggregation. CPU only; the perf modules themselves stay
deselected here (DG-PERF-06)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from perf.support import close, latency, report, sandbox

ROOT = Path(__file__).resolve().parents[4]


def test_nearest_rank_percentiles() -> None:
    samples = [float(n) for n in range(1, 101)]  # 1 … 100
    assert latency.p95(samples) == 95.0
    assert latency.nearest_rank(samples, 0.50) == 50.0
    assert latency.nearest_rank(samples, 0.99) == 99.0
    assert latency.p95([7.0]) == 7.0
    assert latency.p95([3.0, 1.0, 2.0]) == 3.0  # ceil(0.95 × 3) = 3 → the largest
    with pytest.raises(ValueError):
        latency.p95([])
    assert latency.summarise([10.0, 20.0, 30.0, 40.0]) == {
        "count": 4.0,
        "p50": 20.0,
        "p95": 40.0,
        "p99": 40.0,
    }


def test_seeded_and_stratified_sampling() -> None:
    ids = [f"c{n:04d}" for n in range(1, 1001)]
    first = latency.sample_ids(ids, 200)
    assert first == latency.sample_ids(ids, 200) and len(set(first)) == 200
    assert (
        latency.sample_ids(ids[:5], 200) == latency.sample_ids(ids[:5], 200)
        and len(latency.sample_ids(ids[:5], 200)) == 5
    )
    contracts = [(f"c{n:04d}", 1 + n % 12) for n in range(1, 1201)]  # 100 per obligation count
    chosen = latency.stratified_sample(contracts, 200)
    assert chosen == latency.stratified_sample(contracts, 200) and len(set(chosen)) == 200
    by_count = {c: 0 for c in range(1, 13)}
    lookup = dict(contracts)
    for contract_id in chosen:
        by_count[lookup[contract_id]] += 1
    assert set(by_count.values()) <= {16, 17}  # 200 over 12 equal strata: 16 or 17 each
    assert (
        latency.stratified_sample([], 200) == [] and latency.stratified_sample(contracts, 0) == []
    )


def test_mix_plan_proportions() -> None:
    plan = latency.mix_plan(latency.MIX, latency.MIX_REQUESTS)
    assert len(plan) == 2_000 and plan == latency.mix_plan(latency.MIX, latency.MIX_REQUESTS)
    counts = {name: plan.count(name) for name in latency.MIX}
    assert counts == {
        "contract_list": 500,
        "contract_header": 400,
        "obligations": 300,
        "schedule": 200,
        "balances": 200,
        "events": 200,
        "subledger_lines": 100,
        "explain": 100,
    }
    assert sum(weight for _, weight in latency.MIX.values()) == 100
    assert set(latency.ENDPOINTS) == {
        "contract",
        "obligations",
        "schedule",
        "balances",
        "allocation",
        "history",
        "list",
    }


def test_request_log_parser() -> None:
    lines = [
        json.dumps(
            {
                "event": "http.request",
                "route": "/api/v1/contracts/{contract_id}",
                "method": "GET",
                "status": 200,
                "duration_ms": 12.5,
            }
        ),
        json.dumps(
            {
                "event": "http.request",
                "route": "/api/v1/contracts",
                "method": "GET",
                "status": 200,
                "duration_ms": 40.0,
            }
        ),
        json.dumps({"event": "job.started", "job_kind": "CLOSE_RUN"}),
        "not json at all",
        json.dumps(
            {"event": "http.request", "route": "/api/v1/contracts", "method": "GET", "status": 500}
        ),  # no duration
    ]
    parsed = latency.parse_request_log(lines)
    assert [(p.route, p.duration_ms, p.status) for p in parsed] == [
        ("/api/v1/contracts/{contract_id}", 12.5, 200),
        ("/api/v1/contracts", 40.0, 200),
    ]


def test_close_step_seconds_and_problems() -> None:
    steps = [
        {
            "step": "CUTOFF",
            "started_at": "2026-12-31T10:00:00+00:00",
            "finished_at": "2026-12-31T10:00:02+00:00",
            "state": "DONE",
        },
        {
            "step": "RECOMPUTE_DIRTY",
            "started_at": "2026-12-31T10:00:02Z",
            "finished_at": "2026-12-31T10:02:32Z",
            "state": "DONE",
        },
        {
            "step": "DATASET_FREEZE",
            "started_at": "2026-12-31T10:05:00+00:00",
            "finished_at": None,
            "state": "RUNNING",
        },
    ]
    assert close.step_seconds(steps) == {"CUTOFF": 2.0, "RECOMPUTE_DIRTY": 150.0}
    assert close.step_problem(steps) is None
    assert close.step_problem([*steps, {"step": "EXPORT", "state": "FAILED"}]) == "EXPORT"
    assert (
        close.step_problem([{"step": "INVARIANTS", "problem": {"code": "invariant-violated"}}])
        == "INVARIANTS"
    )
    assert (
        close.is_terminal("COMPLETED")
        and close.is_terminal("failed")
        and not close.is_terminal("RUNNING")
    )
    window = close.CloseWindow(started_at="t0", seconds=599.9)
    assert window.within_limit
    window.seconds = 600.1
    assert not window.within_limit
    window.seconds = 10.0
    window.problems.append("VOL-DE first pass: EXPORT")
    assert not window.within_limit
    assert (
        close.ENTITIES == ("VOL-DE", "VOL-UK", "VOL-US")
        and close.PERIOD_KEY == "FY2026-P12"
        and close.BOOK == "ASC606"
    )


def test_trial_balance_from_batches() -> None:
    batch_a = "account,debit,credit\n4000,0.00,100.00\n1200,100.00,0.00\n"
    batch_b = "account,debit,credit,memo\n4000,0.00,50.00,x\n2400,50.00,0.00,y\nbad line\n"
    csv = close.trial_balance_csv([batch_a, batch_b, "no,header,here\n"])
    assert csv == "account,debit,credit\n1200,100.00,0.00\n2400,50.00,0.00\n4000,0.00,150.00\n"


def test_a_journal_run_without_lines_is_left_as_the_close_run_calculated_it() -> None:
    """DG-PERF-02 (2), rev 1.243: between the passes the harness submits, has approved, exports
    and acknowledges the journal runs of the month. A run that states no line (API-S-JournalRun
    ``totals.line_count`` 0) — the run of an entity without activity in the month — is left as
    it stands: its submission is refused (409; item JRN-EMPTY-RUN-1), and there is nothing in it
    to approve or export. It is still named among the window's journal runs. On the dataset's
    manifest every entity has events in every month; a smaller scale has such months."""
    empty, posting, batch = str(uuid4()), str(uuid4()), str(uuid4())
    runs = [
        {"id": empty, "state": "draft", "totals": {"line_count": 0}},
        {"id": posting, "state": "draft", "totals": {"line_count": 3}},
    ]
    assert close.without_lines(runs[0]) and not close.without_lines(runs[1])
    assert not close.without_lines({"id": empty, "state": "draft"})  # a count not stated

    class Recorded:
        def __init__(self) -> None:
            self.posts: list[str] = []
            self.reads: list[str] = []

        def get(self, path: str, params: Any = None) -> dict[str, Any]:
            self.reads.append(path)
            if path == close.JOURNAL_RUNS:
                return {"items": runs}
            if path == f"{close.JOURNAL_RUNS}/{posting}/batches":
                return {"items": [{"id": batch}]}
            return {"items": []}

        def post(self, path: str, body: Any = None, **_: Any) -> dict[str, Any]:
            self.posts.append(path)
            return {}

        def get_response(self, path: str) -> Any:
            class Answer:
                status_code = 404
                text = ""

            return Answer()

    client = Recorded()
    window = close.EntityWindow("VOL-DE")
    # The attach route is still BLOCKED by name (CLO-17), after the journal runs are finished.
    with pytest.raises(close.BlockedRoute, match="CLO-17"):
        close._finish_journal_runs(client, client, client, window, "close-run")  # type: ignore[arg-type]  # noqa: SLF001
    assert window.journal_runs == [empty, posting]
    assert client.posts == [
        f"{close.JOURNAL_RUNS}/{posting}/submit",
        f"{close.JOURNAL_RUNS}/{posting}/export",
        f"{close.JOURNAL_BATCHES}/{batch}/acknowledge",
    ]
    assert not any(empty in path for path in (*client.posts, *client.reads))
    assert window.batches_acknowledged == 1


def test_report_document_shape(tmp_path: Path) -> None:
    doc = report.PerfReport(command="make perf")
    doc.manifest_sha256 = "ab" * 32
    restored = sandbox.RestoredSandbox(
        sandbox_tenant_id=uuid4(), snapshot_id=uuid4(), derived_mismatches=0, groups_recomputed=3
    )
    doc.with_sandbox(sandbox.with_note(restored, "waiting for SANDBOX_RESET"))  # Codex 2353 §3
    window = close.CloseWindow(started_at="t0", finished_at="t1", seconds=42.0)
    window.entities["VOL-US"] = close.EntityWindow(
        "VOL-US", first_run_id="r1", second_run_id="r2", steps_second={"DATASET_FREEZE": 3.0}
    )
    doc.close = report.close_section(window)
    written = doc.write(tmp_path / "perf" / "report.json")
    body = json.loads(written.read_text(encoding="utf-8"))
    assert body["close"]["seconds"] == 42.0 and body["close"]["within_limit"] is True
    assert body["close"]["entities"]["VOL-US"]["steps_second"] == {"DATASET_FREEZE": 3.0}
    assert body["manifest_sha256"] == "ab" * 32 and body["finished_at"]
    assert body["snapshot_id"] == str(restored.snapshot_id)
    assert body["sandbox_tenant_id"] == str(restored.sandbox_tenant_id)
    assert body["notes"] == ["waiting for SANDBOX_RESET"]  # the restored sandbox's notes arrive


def test_perf_modules_deselected_without_flag() -> None:
    """DG-PERF-06 over the real modules: collecting backend/tests/perf without EREV_PERF_RUN
    deselects the three PRF-4 / PRF-5 tests and runs none."""
    env = {k: v for k, v in __import__("os").environ.items() if k != "EREV_PERF_RUN"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/perf",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-header",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert "3 deselected" in result.stdout, result.stdout + result.stderr
    assert "passed" not in result.stdout and "failed" not in result.stdout


def test_routes_bound_to_governed_text_or_blocked_by_name() -> None:
    """Q5 ruling: no guessed bodies. Bound routes carry the exact 04 members; blocked routes refuse
    by name with the owning F-CLO item before anything is posted."""
    assert close.multi_entity_body(close.ENTITIES) == {
        "entity_codes": ["VOL-DE", "VOL-UK", "VOL-US"],
        "book": "ASC606",
        "period_key": "FY2026-P12",
    }
    ack = close.acknowledge_body("0123456789abcdef")
    assert set(ack) <= {"gl_document_id", "gl_posted_date", "message"} and ack["gl_document_id"]
    for name in (
        "close_runs_multi_entity",
        "close_run_read",
        "journal_run_submit",
        "journal_run_export",
        "journal_batch_acknowledge",
    ):
        assert close.require_bound(name).status == "bound" and "04 " in close.ROUTES[name].clause
    for name, item in (("attach_trial_balance", "CLO-17"), ("close_run_single", "CLO-19")):
        with pytest.raises(close.BlockedRoute) as raised:
            close.require_bound(name)
        assert "BLOCKED on F-CLO " + item in str(raised.value) and close.ROUTES[name].path in str(
            raised.value
        )
    # Codex 2353 §4: the window's routes are preflighted before its first request, so the BLOCKED
    # attach refuses the whole window up front — not after the close runs, journal runs and
    # acknowledgements have been posted.
    assert set(close.WINDOW_ROUTES) <= set(close.ROUTES) and "attach_trial_balance" in (
        close.WINDOW_ROUTES
    )
    with pytest.raises(close.BlockedRoute, match="CLO-17"):
        close.preflight()
    assert len(close.preflight(close.WINDOW_ROUTES[:-1])) == len(close.WINDOW_ROUTES) - 1

    class NoRequests:
        def __getattr__(self, name: str) -> Any:
            pytest.fail(f"a request ({name}) was made before the preflight refused the window")

    with pytest.raises(close.BlockedRoute, match="CLO-17"):
        close.run_close_window(NoRequests(), NoRequests(), NoRequests())  # type: ignore[arg-type]
