"""PRF-3 harness rules (dev-guide DG-PERF-02, DG-PERF-05, DG-PERF-06, DG-PERF-08; DG-MK-00e; 05
AIA-02). CPU only: fakes stand in for the database, the processes and the sandbox job; the
ports-lock
test runs ``scripts/perf.sh`` against a scratch ``EREV_RUN_DIR`` and exits before anything starts.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.config import settings_override
from perf.support import processes, rules, sandbox, tenant

CONFTEST = Path(__file__).resolve().parents[2] / "perf" / "conftest.py"

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "perf.sh"
CLEARED = ("EREV_PERF_RUN", "EREV_PERF_COMMAND", "EREV_REPORTS_DIR")


@pytest.fixture
def run_dir() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _env(run_dir: Path, **values: str) -> dict[str, str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in CLEARED and not key.startswith(prefixes)
    }
    return env | {"EREV_RUN_DIR": str(run_dir), "EREV_DOTENV": str(run_dir / "absent.env")} | values


def test_perf_tests_deselected_by_default(pytester: pytest.Pytester) -> None:
    """DG-PERF-06 (Codex 2316 R1): without EREV_PERF_RUN every perf item is deselected and every
    ordinary item is kept — the pure rule, and the real conftest over a mixed scratch tree with a
    sibling ordinary test that must execute."""
    perf_items = [SimpleNamespace(nodeid=f"perf/test_x.py::test_{n}", perf=True) for n in range(3)]
    other = [SimpleNamespace(nodeid=f"unit/test_y.py::test_{n}", perf=False) for n in range(2)]
    kept, dropped = rules.deselect_unless_perf_run(
        [*perf_items, *other], perf_run=False, is_perf=lambda item: bool(item.perf)
    )
    assert (kept, dropped) == (other, perf_items)
    assert rules.deselect_unless_perf_run([*perf_items, *other], perf_run=True) == (
        [*perf_items, *other],
        [],
    )
    assert rules.is_perf_run({}) is False and rules.is_perf_run({"EREV_PERF_RUN": "1"}) is True

    conftest = (ROOT / "backend/tests/perf/conftest.py").read_text(encoding="utf-8")
    perf_dir = pytester.mkdir(
        "perf"
    )  # no __init__: the scratch conftest must not shadow perf.conftest
    (perf_dir / "conftest.py").write_text(conftest, encoding="utf-8")
    (perf_dir / "test_perf_probe.py").write_text(
        textwrap.dedent(
            """
            import pytest

            @pytest.mark.perf
            def test_probe():
                raise AssertionError("a perf test ran without EREV_PERF_RUN=1")
            """
        ),
        encoding="utf-8",
    )
    pytester.makepyfile(
        test_ordinary=textwrap.dedent(
            """
            def test_ordinary_runs():
                assert 1 + 1 == 2
            """
        )
    )
    pytester.makeini("[pytest]\nmarkers =\n    perf: performance benchmark (G9)\n")
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("EREV_PERF_RUN", raising=False)
        result = pytester.runpytest_inprocess("-q", "-p", "no:cacheprovider")
    result.assert_outcomes(passed=1, deselected=1)


def test_stale_tenant_message() -> None:
    """DG-PERF-06: perf-volume absent, built from another manifest, month 23 unlocked or without a
    succeeded stored snapshot → every perf test fails with one message. The read is two
    scopes (Codex 2316 R2 (a)): directory identity, then the snapshot in the tenant's context.
    The snapshot is the ``STORED_BACKUP`` the seed's step 5 asks (DG-MK-perf-seed (5); item
    PERF-SEED-LOCK-1): a snapshot of a sandbox purpose is not it."""
    current = "perf:0123456789abcdef"
    tenant_id, snapshot_id = uuid4(), uuid4()
    at = datetime(2026, 12, 1, tzinfo=UTC)
    assert tenant.SEED_PURPOSE == "STORED_BACKUP"
    seed = tenant.SnapshotFacts(snapshot_id, "SUCCEEDED", at, "STORED_BACKUP")
    good = tenant.TenantFacts(tenant_id, current, True, seed)
    found = tenant.check_perf_tenant(lambda: good, expected_cluster=current)
    assert found == tenant.PerfTenant(tenant_id, current, seed)
    assert found.seed_snapshot_id == snapshot_id
    stale: Sequence[tenant.TenantFacts | None] = (
        None,
        tenant.TenantFacts(tenant_id, "perf:fedcba9876543210", True, seed),
        tenant.TenantFacts(tenant_id, current, False, seed),
        tenant.TenantFacts(tenant_id, current, True, None),
        tenant.TenantFacts(
            tenant_id,
            current,
            True,
            tenant.SnapshotFacts(snapshot_id, "RUNNING", at, "STORED_BACKUP"),
        ),
        tenant.TenantFacts(
            tenant_id,
            current,
            True,
            tenant.SnapshotFacts(snapshot_id, "SUCCEEDED", at, "SANDBOX_SEED"),
        ),
        tenant.TenantFacts(
            tenant_id,
            current,
            True,
            tenant.SnapshotFacts(snapshot_id, "SUCCEEDED", at, "SANDBOX_COPY"),
        ),
    )
    for facts in stale:
        with pytest.raises(tenant.PerfTenantStale) as raised:
            tenant.check_perf_tenant(lambda facts=facts: facts, expected_cluster=current)
        assert str(raised.value) == "perf tenant missing or stale; run make perf-seed"
        assert raised.value.__notes__  # the reason travels beside the message, for the log
    assert rules.STALE_MESSAGE == "perf tenant missing or stale; run make perf-seed"
    # The reader seam: the directory read resolves the identity, the snapshot read receives it.
    seen: list[UUID] = []

    def snapshot_of(found_id: UUID) -> tenant.SnapshotFacts | None:
        seen.append(found_id)
        return seed

    composed = tenant.compose_facts(lambda: (tenant_id, current), snapshot_of)
    assert composed == good and seen == [tenant_id]
    assert tenant.compose_facts(lambda: None, snapshot_of) is None and seen == [tenant_id]
    unlocked = tenant.compose_facts(lambda: (tenant_id, current), lambda _: None)
    assert unlocked is not None and unlocked.month_23_locked is False and unlocked.snapshot is None


def test_processes_stopped_on_readiness_failure(run_dir: Path) -> None:
    """DG-PERF-05, DG-PERF-08: a failed readiness check stops every started process by PID file
    and reports the last 40 log lines of the failing process."""
    calls: list[list[str]] = []

    def runner(command: Sequence[str], env: Mapping[str, str]) -> Any:
        calls.append(list(command))
        assert env["EREV_RUN_DIR"] == str(run_dir)
        if command[1] == "start":
            name = command[2]
            lines = [f"{name} line {n}" for n in range(1, 61)]
            (run_dir / f"{name}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (run_dir / f"{name}.pid").write_text("4242\n", encoding="utf-8")
            return SimpleNamespace(returncode=1 if name == "perf-worker-2" else 0)
        return SimpleNamespace(returncode=0)

    stack = processes.PerfStack(ROOT, run_dir, runner=runner)
    assert [spec.name for spec in stack.specs] == [
        "api-perf",
        "perf-worker-1",
        "perf-worker-2",
        "perf-worker-3",
        "perf-worker-4",
    ]
    assert stack.specs[0].port == "8199" and all(spec.port == "-" for spec in stack.specs[1:])
    with pytest.raises(processes.ReadinessFailed) as raised:
        stack.start_all()
    assert raised.value.name == "perf-worker-2"
    tail = raised.value.log_tail.splitlines()
    assert (
        len(tail) == 40
        and tail[0] == "perf-worker-2 line 21"
        and tail[-1] == "perf-worker-2 line 60"
    )
    starts = [c[2] for c in calls if c[1] == "start"]
    stops = [c[2] for c in calls if c[1] == "stop"]
    assert starts == ["api-perf", "perf-worker-1", "perf-worker-2"]
    assert stops == [
        "perf-worker-2",
        "perf-worker-1",
        "api-perf",
    ]  # every started one, reverse order
    assert stack.started == []
    assert all(c[0].endswith("scripts/proc.sh") for c in calls)


def test_fake_ai_provider_enforced() -> None:
    """05 AIA-02: EREV_PERF_RUN=1 with EREV_AI_PROVIDER=anthropic fails in Settings, before any
    process starts."""
    started: list[str] = []
    with (
        pytest.raises(ValueError, match="EREV_AI_PROVIDER"),
        settings_override(env="dev", perf_run=True, ai_provider="anthropic") as settings,
    ):
        rules.preflight(lambda: settings, lambda: started.append("started"))
    assert started == []
    # The fake provider passes and the processes start only after the settings are built.
    with settings_override(env="dev", perf_run=True, ai_provider="fake") as settings:
        built = rules.preflight(lambda: settings, lambda: started.append("started"))
    assert built.perf_run is True and built.ai_provider == "fake" and started == ["started"]


def test_e2e_ports_lock(run_dir: Path) -> None:
    """DG-MK-00e: a live holder of .run/locks/e2e-ports makes scripts/perf.sh exit with the busy
    message before anything starts; the holder's lock stays."""
    lock = run_dir / "locks" / "e2e-ports"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=_env(run_dir),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == f"e2e ports busy (pid {os.getpid()})"
    assert (lock / "pid").read_text(encoding="utf-8").strip() == str(os.getpid())
    assert list(run_dir.glob("*.pid")) == []
    assert not (run_dir / "pytest-perf").exists()
    # DG-MK-00g: a report exists even for the refused run, and it names no harness result.
    report = run_dir / "reports" / "perf" / "report.json"
    assert report.exists() and '"exit_code": 1' in report.read_text(encoding="utf-8")


def test_sandbox_copy_determinism_required() -> None:
    """DG-PERF-02 / SBX-05: derived_mismatches > 0 fails with the one message; 0 passes and the
    restored sandbox carries the job's counts. The restore params carry the snapshot's own
    known_at and purpose (Codex 2316 R2 (b)) and satisfy the real ``snapshot_job.parse_params``;
    the TENANT_SNAPSHOT handler is registered (R2 (c) seam)."""
    from erev_api.domain.platform import sandboxes, snapshot_job
    from erev_api.enums import JobKind
    from erev_api.jobs import registry

    with pytest.raises(sandbox.SandboxNotDeterministic) as raised:
        sandbox.require_deterministic({"derived_mismatches": 2})
    assert str(raised.value) == "perf sandbox copy not deterministic"
    assert sandbox.require_deterministic({"derived_mismatches": 0}) == 0
    assert sandbox.require_deterministic({}) == 0

    snapshot_id, sandbox_id, requester = uuid4(), uuid4(), uuid4()
    at = datetime(2026, 12, 1, 12, 30, tzinfo=UTC)
    seed = tenant.SnapshotFacts(snapshot_id, "SUCCEEDED", at, "STORED_BACKUP")
    load_params = sandboxes.load_params_of(
        sandbox_tenant_id=sandbox_id,
        name="perf-run-a1b2",
        requested_by=sandbox.require_requester(requester),  # the resolved perf-controller
        restore=True,
    )
    params = sandbox.restore_params(seed, load_params)
    parsed = snapshot_job.parse_params(params)  # the real validator, no defaults
    load = sandboxes.parse_load(params)  # the real load parser the handler uses
    assert load is not None and load.requested_by == requester and load.restore is True
    assert (parsed.tenant_snapshot_id, parsed.known_at, parsed.purpose) == (
        snapshot_id,
        at,
        "STORED_BACKUP",
    )
    assert "load" in params and str(params["load"]["sandbox_tenant_id"]) == str(sandbox_id)
    assert params["load"]["name"].startswith(sandbox.SANDBOX_PREFIX)
    assert JobKind.TENANT_SNAPSHOT in registry.HANDLERS  # the registered handler the run calls
    naive = tenant.SnapshotFacts(
        snapshot_id, "SUCCEEDED", datetime(2026, 12, 1, 12, 30), "STORED_BACKUP"
    )
    with pytest.raises(ValueError, match="UTC offset"):
        sandbox.restore_params(naive, load_params)

    seen: list[Mapping[str, Any]] = []

    def run(received: Mapping[str, Any]) -> Mapping[str, Any]:
        seen.append(received)
        return {
            "counts": {"derived_mismatches": 0, "groups_recomputed": 7},
            "sandbox_tenant_id": str(sandbox_id),
        }

    restored = sandbox.restore_seed(
        run, snapshot=seed, sandbox_tenant_id=sandbox_id, load_params=load_params
    )
    assert restored == sandbox.RestoredSandbox(sandbox_id, snapshot_id, 0, 7)
    assert seen == [params]
    noted = sandbox.with_note(restored, "waiting for SANDBOX_RESET")
    assert noted.notes == ("waiting for SANDBOX_RESET",) and noted.sandbox_tenant_id == sandbox_id

    def mismatching(received: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"counts": {"derived_mismatches": 1}}

    with pytest.raises(
        sandbox.SandboxNotDeterministic, match="perf sandbox copy not deterministic"
    ):
        sandbox.restore_seed(
            mismatching, snapshot=seed, sandbox_tenant_id=UUID(int=1), load_params={}
        )


def test_a_load_that_compared_nothing_is_refused_with_its_counts() -> None:
    """DG-PERF-02 (1), rev 1.243: ``derived_mismatches = 0`` is no evidence when the load compared
    nothing. Measured on 2026-10-02 in the story of the perf seed, over a snapshot cut before
    every event of its world: the load ended SUCCEEDED with 0 mismatches, 0 groups recomputed
    and 10 not recomputed, in a sandbox without a contract event — the source had no version as
    of that cutoff either. The harness refuses both by name, with the counts: a contract group
    the load did not recompute, and a sandbox that does not hold the contract events
    ``perf-volume`` recorded at or before the snapshot's ``known_at``, or holds none. A copy
    that passes carries the count into the report."""
    measured = {
        "rows": 1580,
        "datasets": 78,
        "loaded_rows": 1580,
        "already_done": 1,
        "blocked_periods": 24,
        "groups_recomputed": 0,
        "derived_mismatches": 0,
        "groups_not_recomputed": 10,
    }
    with pytest.raises(sandbox.SandboxNotVerified) as refused:
        sandbox.require_deterministic(measured)
    assert str(refused.value) == (
        "perf sandbox copy proves nothing: the load recomputed 0 contract group(s) and left 10 "
        "without a result to compare"
    )
    complete = {**measured, "groups_recomputed": 10, "groups_not_recomputed": 0}
    assert sandbox.require_deterministic(complete) == 0
    # A differing result is named first: it is the stronger finding.
    with pytest.raises(sandbox.SandboxNotDeterministic):
        sandbox.require_deterministic({**measured, "derived_mismatches": 3})

    snapshot_id, source_id, sandbox_id = uuid4(), uuid4(), uuid4()
    cut = datetime(2026, 9, 12, 12, 15, tzinfo=UTC)
    seed = tenant.SnapshotFacts(snapshot_id, "SUCCEEDED", cut, "STORED_BACKUP")
    with pytest.raises(sandbox.SandboxNotVerified, match="left 10 without a result to compare"):
        sandbox.restore_seed(
            lambda received: {"counts": measured},
            snapshot=seed,
            sandbox_tenant_id=sandbox_id,
            load_params={},
        )

    # The run's own figures again: nothing was recorded at or before that cutoff, 421 after it.
    with pytest.raises(sandbox.SandboxNotVerified) as empty:
        sandbox.require_events_copied(source=0, sandbox=0, known_at=cut)
    assert str(empty.value) == (
        "perf sandbox copy is not perf-volume as of the snapshot: the sandbox holds 0 contract "
        "event(s); perf-volume recorded 0 at or before 2026-09-12T12:15:00+00:00"
    )
    with pytest.raises(sandbox.SandboxNotVerified, match=r"holds 420 contract event\(s\); perf"):
        sandbox.require_events_copied(source=421, sandbox=420, known_at=cut)
    assert sandbox.require_events_copied(source=421, sandbox=421, known_at=cut) == 421

    restored = sandbox.RestoredSandbox(sandbox_id, snapshot_id, 0, 10)
    asked: list[tuple[UUID, datetime | None]] = []

    def events(tenant_id: UUID, until: datetime | None) -> int:
        asked.append((tenant_id, until))
        return 421

    verified = sandbox.verify_copy(
        restored, source_tenant_id=source_id, known_at=cut, events=events
    )
    # perf-volume as of the cutoff, the sandbox whole — it holds nothing else yet.
    assert asked == [(source_id, cut), (sandbox_id, None)]
    assert verified.notes == ("contract events of perf-volume as of the snapshot, all copied: 421",)
    with pytest.raises(sandbox.SandboxNotVerified, match=r"holds 0 contract event\(s\)"):
        sandbox.verify_copy(
            restored,
            source_tenant_id=source_id,
            known_at=cut,
            events=lambda tenant_id, until: 421 if tenant_id == source_id else 0,
        )
    # Measured the same day on a whole copy: perf-volume had recorded one event after its
    # snapshot — 421 in all, 420 at or before the cutoff — and the sandbox held those 420. The
    # count is taken as of the cutoff: taken whole, it would refuse a copy that is complete.
    moved = sandbox.verify_copy(
        restored,
        source_tenant_id=source_id,
        known_at=cut,
        events=lambda tenant_id, until: 421 if (tenant_id, until) == (source_id, None) else 420,
    )
    assert moved.notes == ("contract events of perf-volume as of the snapshot, all copied: 420",)
    # The session fixture asks it of the restored sandbox before anything is appended, and ends
    # the run by name on either refusal.
    fixture = CONFTEST.read_text(encoding="utf-8")
    body = fixture[fixture.index("def perf_sandbox(") : fixture.index("def perf_processes(")]
    assert body.index("sandbox.restore_seed(") < body.index("sandbox.verify_copy(")
    assert "events=_contract_events," in body
    assert "except (sandbox.SandboxNotDeterministic, sandbox.SandboxNotVerified) as exc:" in body
    assert "contract_event.c.recorded_at <= until" in fixture


def test_restore_refused_without_a_real_requester(tmp_path: Path) -> None:
    """Codex 2353 PRF3-RESTORE-ACTOR-1: the REAL loader (``sandboxes.load_sandbox``, the function
    the registered TENANT_SNAPSHOT handler calls after its no-op re-export of a SUCCEEDED row)
    refuses ``requested_by = None`` with 403 ``SANDBOX_ACTOR_REQUIRED`` before any unit of work;
    the harness refuses earlier, by name, and never invents an actor."""
    from erev_api.domain.platform import sandboxes
    from erev_api.problems import Problem
    from support.clock import frozen_clock

    def no_db_work() -> None:
        pytest.fail("the loader touched the database before the actor check")

    jc = SimpleNamespace(
        runtime=SimpleNamespace(keyring=object(), files=object()),
        tenant_id=uuid4(),
        job_id=uuid4(),
        clock=frozen_clock(),
        unit_of_work=no_db_work,
        heartbeat=None,
    )
    load = sandboxes.LoadParams(uuid4(), "perf-run-a1b2", None, True)
    with pytest.raises(Problem) as refused:
        sandboxes.load_sandbox(jc, snapshot_id=uuid4(), load=load)
    assert refused.value.slug == "forbidden"
    (error,) = refused.value.errors
    assert (error.field, error.rule_id) == ("requested_by", sandboxes.RULE_ACTOR)
    assert sandboxes.RULE_ACTOR == "SANDBOX_ACTOR_REQUIRED"

    with pytest.raises(sandbox.RequesterMissing) as missing:
        sandbox.require_requester(None)
    assert str(missing.value) == rules.REQUESTER_MISSING_MESSAGE
    assert "run make perf-seed" in str(missing.value)
    user_id = uuid4()
    assert sandbox.require_requester(user_id) == user_id


def test_prior_active_sandbox_refused_before_restore() -> None:
    """Codex 2353 A4 (conditional): only an EXISTING ACTIVE perf-run-* sandbox requires
    SANDBOX_RESET; a first run proceeds. The check runs before the restore and before any process
    starts (the fixture order: prior-active → requester → restore → processes)."""
    from erev_api.domain.platform import sandboxes

    assert sandboxes.sandbox_code("perf-run-a1b2").startswith(sandbox.SANDBOX_CODE_PREFIX)
    assert sandbox.prior_active_refusal([], reset_available=False) is None
    assert sandbox.prior_active_refusal(["sbx-other-copy"], reset_available=False) is None
    absent = sandbox.prior_active_refusal(["sbx-perf-run-a1b2"], reset_available=False)
    assert absent == rules.PRIOR_ACTIVE_RESET_ABSENT_MESSAGE and "SANDBOX_RESET" in absent
    unbound = sandbox.prior_active_refusal(
        ["sbx-other-copy", "sbx-perf-run-a1b2"], reset_available=True
    )
    assert unbound == rules.PRIOR_ACTIVE_RESET_UNBOUND_MESSAGE and "PRF-4" in unbound
    # The fixture body checks the prior-active condition and the requester before the restore
    # and before worker.build_runtime; the source order is the witness the lane can run.
    source = (CONFTEST).read_text(encoding="utf-8")
    body = source[source.index("def perf_sandbox(") :]
    order = [
        body.index("prior_active_refusal("),
        body.index("require_requester("),
        body.index("worker.build_runtime("),
        body.index("sandbox.restore_seed("),
    ]
    assert order == sorted(order)
    assert source.index("def perf_sandbox(") < source.index("def perf_processes(")


def test_ctr_6_month_24_requests_that_wait_are_approved_by_the_reviewer() -> None:
    """BUILD_SPEC CTR-6 at the harness (dev-guide DG-PERF-02 (1); CPU only, fakes stand in for the
    two signed-in clients): a month-24 request of the accountant that holds a manual event is
    answered 201 with an event submission and appends nothing, so the reviewer approves its
    request with the hash the request shows — once, before the events are counted — and a
    request that was appended directly is approved by nobody. The entity's evidence document of
    the month is uploaded once, at its first use, and named by the requests the product asks
    evidence of (``volume.needs_evidence``)."""
    from fractions import Fraction

    from erev_api.domain.contracts.events import MANUAL_TYPES
    from erev_api.domain.demo import volume
    from perf.support import prepare

    manual = {member.value for member in MANUAL_TYPES}
    small = volume.manifest(Fraction(1, 1000))
    by_external = {c.external_id: c for c in small.contracts}

    class Accountant:
        def __init__(self) -> None:
            self.posts: list[tuple[str, Mapping[str, Any]]] = []
            self.uploads: list[tuple[str, str, bytes]] = []

        def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
            assert path == "/contracts" and params is not None
            return {"items": [{"external_id": params["q"], "id": f"id-{params['q']}"}]}

        def get_response(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
            return SimpleNamespace(headers={"etag": '"s9"'})

        def upload(self, path: str, **form: Any) -> Any:
            assert (path, form["fields"], form["media_type"]) == (
                "/files",
                {"purpose": "ATTACHMENT"},
                "text/csv",
            )
            self.uploads.append(
                (form["filename"], f"file-{len(self.uploads) + 1}", form["content"])
            )
            return {"id": self.uploads[-1][1]}

        def post(self, path: str, body: Mapping[str, Any] | None = None, **headers: Any) -> Any:
            assert body is not None and headers["if_match"] == '"s9"'
            self.posts.append((path, body))
            types = {item["event_type"] for item in body["events"]}
            if types & manual:  # the product's rule: a person's manual event waits
                return {
                    "event_submission_id": f"sub-{len(self.posts)}",
                    "approval_request_id": f"req-{len(self.posts)}",
                }
            return {"contract": {}, "events": [{} for _ in body["events"]], "computation": {}}

    class Reviewer:
        def __init__(self) -> None:
            self.approved: list[tuple[str, Mapping[str, Any]]] = []

        def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
            request_id = path.removeprefix("/approvals/")
            return {"subject": {"content_sha256": f"sha-{request_id}"}, "impact_preview": None}

        def post(self, path: str, body: Mapping[str, Any] | None = None, **headers: Any) -> Any:
            assert body is not None
            self.approved.append((path, body))
            return {"status": "APPROVED"}

    accountant, reviewer = Accountant(), Reviewer()
    prepared = prepare.append_month_24(accountant, reviewer, small)  # type: ignore[arg-type]

    waiting = [
        (index, body)
        for index, (_path, body) in enumerate(accountant.posts, 1)
        if {item["event_type"] for item in body["events"]} & manual
    ]
    direct = [body for _path, body in accountant.posts if body not in [b for _i, b in waiting]]
    assert waiting, "month 24 of the small manifest holds manual events"
    # each request that waits is approved once, in order, with the hash its request shows
    assert reviewer.approved == [
        (
            f"/approvals/req-{index}/approve",
            {"subject_content_sha256": f"sha-req-{index}", "comment": "perf harness"},
        )
        for index, _body in waiting
    ]
    assert len(reviewer.approved) + len(direct) == len(accountant.posts)
    # the evidence: one document per entity, uploaded at its first use, named where it is asked
    assert len({name for name, _id, _content in accountant.uploads}) == len(accountant.uploads)
    file_of = {name: file_id for name, file_id, _content in accountant.uploads}
    for path, body in accountant.posts:
        external_id = path.removeprefix("/contracts/id-").removesuffix("/events")
        entity = by_external[external_id].entity_code
        needs = any(
            item["event_type"] in {"PROGRESS_RECORDED", "MILESTONE_ACHIEVED", "COST_INCURRED"}
            or (
                item["event_type"] == "DELIVERY_RECORDED"
                and item["payload"].get("trigger") == "ACCEPTANCE"
            )
            for item in body["events"]
        )
        expected = [file_of[volume.evidence_filename(entity, 24)]] if needs else []
        assert body["evidence_file_ids"] == expected, (external_id, body["evidence_file_ids"])
        assert body["comment"] == "perf month 24"
    for name, _id, content in accountant.uploads:
        lines = content.decode("utf-8").split("\n")
        assert name.endswith("-month-24-evidence.csv") and lines[0] == volume.EVIDENCE_HEADER
        assert len(lines) > 2 and {line.split(",")[1] for line in lines[1:-1]} <= manual
    assert prepared.events_appended == sum(len(body["events"]) for _path, body in accountant.posts)
    assert prepared.contracts_touched == len({e.contract_seq for e in small.events_for_month(24)})
