"""Source binding of gate evidence (GATE-BIND-1; dev-guide DG-MK-00i; 05 REL-02; D-80):
``scripts/gate_report.py`` executes its stages in an immutable execution context and
``scripts/gate_context.sh`` runs the other report writers through the same mechanism.

Adapted from Codex's gate source-binding probe (`PRODUCTION-GATE-SOURCE-BINDING-8784f13.md`, v4):
the committed wrapper is copied into a scratch repository with a source marker at commit A and a
commit B; a synthetic stage reads the marker from its working directory and records where it ran,
while an actor moves the ORIGINAL checkout A → B (persistently, or back to A). Every successful
report must be bound to A. The scratch repository carries stub ``erev_api`` and ``erev_engine``
packages, so the module-origin proof runs against the lane's interpreter with the context ahead of
the editable install.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from support.release_manifest import commit, git, load_script, scratch_repo

ROOT = Path(__file__).resolve().parents[3]
GATE_REPORT = ROOT / "scripts" / "gate_report.py"
GATE_CONTEXT = ROOT / "scripts" / "gate_context.sh"
MODE_CONTEXT = "immutable-context"
MODE_DIRTY = "worktree-dirty (development; not release evidence)"

STUBS = {
    "backend/erev_api/__init__.py": '"""stub"""\n',
    "backend/erev_api/config.py": (
        "from pathlib import Path\n\nREPO_ROOT = Path(__file__).resolve().parents[2]\n"
    ),
    "backend/erev_api/cli.py": (
        "from pathlib import Path\n\n"
        "ALEMBIC_INI = Path(__file__).resolve().parents[1] / 'alembic.ini'\n"
    ),
    "backend/erev_api/db/__init__.py": "",
    "backend/erev_api/db/migration_ops.py": (
        "from pathlib import Path\n\n"
        "VERSIONS_DIR = Path(__file__).resolve().parent / 'migrations' / 'versions'\n"
    ),
    "backend/erev_engine/__init__.py": 'ENGINE_VERSION = "0.0.0"\n',
    "marker.txt": "SOURCE_A\n",
    ".gitignore": ".run/\n.env\nbackend/.venv\nfrontend/node_modules\n",
}

# The synthetic stage of the v4 probe, extended: it records the marker of its working directory
# into the ORIGINAL root (absolute path, so it survives context removal), moves the original
# checkout when asked (ACTOR_TO / ACTOR_BACK), may edit a tracked file where it runs
# (MUTATE_CWD=1), and writes the dummy JUnit file the gate expects.
HOOK = r"""
import hashlib, json, os, subprocess, sys
from pathlib import Path
origin = Path(sys.argv[1]).resolve()
gate = sys.argv[2]
executed_root = Path.cwd().resolve()
def actor(*args):
    completed = subprocess.run(
        ["git", *args], cwd=origin, text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()
if os.environ.get("ACTOR_TO"):
    actor("checkout", "--detach", "--quiet", os.environ["ACTOR_TO"])
marker = (executed_root / "marker.txt").read_bytes()
if os.environ.get("MUTATE_CWD") == "1":
    (executed_root / "marker.txt").write_bytes(b"edited during the run\n")
observed = {
    "marker": marker.decode().strip(),
    "marker_sha256": hashlib.sha256(marker).hexdigest(),
    "executed_root": str(executed_root),
    "context_env": os.environ.get("EREV_GATE_CONTEXT", ""),
    "pythonpath": os.environ.get("PYTHONPATH", ""),
    "actor_head": actor("rev-parse", "HEAD"),
    "ruff_cache_dir": os.environ.get("RUFF_CACHE_DIR", ""),
    "mypy_cache_dir": os.environ.get("MYPY_CACHE_DIR", ""),
}
(origin / ".run").mkdir(exist_ok=True)
(origin / ".run" / f"observed-{gate}.json").write_text(json.dumps(observed))
(origin / ".run" / f"dummy-{gate}.xml").write_text(
    '<testsuite tests="1" failures="0" errors="0" skipped="0">'
    '<testcase name="observation"/></testsuite>'
)
if os.environ.get("HOOK_REPORT") == "1":
    # As a wrapped writer (exec mode) the hook also leaves a DG-MK-00g report where it ran.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=executed_root, text=True, capture_output=True, check=True
    ).stdout.strip()
    report_dir = executed_root / ".run" / "reports" / gate
    report_dir.mkdir(parents=True, exist_ok=True)
    import datetime as _dt
    _now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    (report_dir / "report.json").write_text(json.dumps({
        "target": gate, "command": f"make {gate}", "build_sha": head, "worktree_dirty": False,
        "started_at": _now, "finished_at": _now,
        "exit_code": 0, "counts": {"observed": 1, "marker": observed["marker"]}, "failures": []}))
if os.environ.get("ACTOR_BACK"):
    actor("checkout", "--detach", "--quiet", os.environ["ACTOR_BACK"])
print("observed", observed["marker"])
"""

# A stand-in for the writers that are not stage lists (answer-keys, parity, controls-report, e2e):
# it writes its own DG-MK-00g report under its working directory and exits as told. MODE (third
# argument, default valid) shapes the evidence: absent (no report), malformed (not JSON), list (a
# JSON array), schema (no counts), identity (another build_sha), empty (counts without a figure);
# WRITER_PATCH (a JSON object) is merged into the report before it is written.
WRITER = r"""
import json, os, subprocess, sys
from pathlib import Path
gate, exit_code = sys.argv[1], int(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else "valid"
cwd = Path.cwd()
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
report_dir = cwd / ".run" / "reports" / gate
report_dir.mkdir(parents=True, exist_ok=True)
(report_dir / "extra.txt").write_text("kept\n")
import datetime as _dt
_now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
report = {"target": gate, "command": f"make {gate}", "build_sha": head, "worktree_dirty": False,
          "started_at": _now, "finished_at": _now,
          "exit_code": exit_code,
          "counts": {"selected": 1, "passed": 1 if exit_code == 0 else 0,
                     "failed": 0 if exit_code == 0 else 1,
                     "marker": (cwd / "marker.txt").read_text().strip(), "cwd": str(cwd)},
          "failures": [] if exit_code == 0 else [{"stage": "writer", "exit_code": exit_code}],
          "argv": sys.argv[1:], "run_id": os.environ.get("EREV_GATE_RUN_ID")}
report.update(json.loads(os.environ.get("WRITER_PATCH") or "{}"))
if mode == "schema":
    del report["counts"]
elif mode == "identity":
    report["build_sha"] = "0" * 40
elif mode == "empty":
    report["counts"] = {"stages": {}}
if mode == "malformed":
    (report_dir / "report.json").write_text("{not json")
elif mode == "list":
    (report_dir / "report.json").write_text("[1, 2]\n")
elif mode != "absent":
    (report_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print(("OK " if exit_code == 0 else "FAIL ") + gate)
sys.exit(exit_code)
"""


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _repo(
    scratch: Path,
    extra_a: dict[str, str] | None = None,
    extra_b: dict[str, str] | None = None,
) -> tuple[Path, str, str]:
    """Scratch repository at commit A (marker SOURCE_A) with commit B (SOURCE_B) on a side branch,
    carrying the committed wrapper scripts and the stub packages (plus ``extra_a`` at A and
    ``extra_b`` changed at B)."""
    files = dict(STUBS) | (extra_a or {})
    files["scripts/gate_report.py"] = GATE_REPORT.read_text(encoding="utf-8")
    files["scripts/gate_context.sh"] = GATE_CONTEXT.read_text(encoding="utf-8")
    repo = scratch_repo(scratch / "repo", files=files)
    for name in ("gate_report.py", "gate_context.sh"):
        path = repo / "scripts" / name
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    git(repo, "update-index", "--chmod=+x", "scripts/gate_report.py", "scripts/gate_context.sh")
    git(repo, "commit", "-q", "-m", "executable scripts")
    head_a = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "other")
    head_b = commit(repo, {"marker.txt": "SOURCE_B\n"} | (extra_b or {}), "B")
    git(repo, "checkout", "-q", "--detach", head_a)
    (repo / ".env").write_text("EREV_STUB=1\n", encoding="utf-8")
    (repo / ".run").mkdir(exist_ok=True)
    (repo / ".run" / "hook.py").write_text(HOOK, encoding="utf-8")
    (repo / ".run" / "writer.py").write_text(WRITER, encoding="utf-8")
    assert git(repo, "status", "--porcelain") == ""
    return repo, head_a, head_b


def _env(**values: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "ACTOR_", "MUTATE_", "EREV_GATE_"))
    }
    env |= values
    return env


def _gate(root: Path, gate: str, **values: str) -> subprocess.CompletedProcess[str]:
    """The v4 probe invocation: the copied wrapper, one observing stage, a dummy JUnit file."""
    hook = shlex.join([sys.executable, str(root / ".run" / "hook.py"), str(root), gate])
    return subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "gate_report.py"),
            gate,
            "--command",
            f"synthetic {gate} observation",
            "--stage",
            f"observe={hook}",
            "--junit",
            f"dummy={root}/.run/dummy-{gate}.xml",
            "--fail-on-skipped",
            "dummy",
        ],
        cwd=root,
        env=_env(**values),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def _report(root: Path, gate: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (root / ".run" / "reports" / gate / "report.json").read_text(encoding="utf-8")
    )
    return data


def _observed(root: Path, gate: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (root / ".run" / f"observed-{gate}.json").read_text(encoding="utf-8")
    )
    return data


def _assert_bound(
    report: dict[str, Any], observed: dict[str, Any], root: Path, head_a: str, tree_a: str
) -> str:
    assert (report["exit_code"], report["worktree_dirty"], report["build_sha"]) == (
        0,
        False,
        head_a,
    )
    assert report["counts"]["dummy"] == {"passed": 1, "failed": 0, "skipped": 0, "xfailed": 0}
    assert observed["marker"] == "SOURCE_A"
    binding = report["source_binding"]
    assert binding["mode"] == MODE_CONTEXT and binding["captured_sha"] == head_a
    assert binding["tree_sha"] == tree_a == binding["tree_sha_end"]
    assert binding["context_sha256_start"] == binding["context_sha256_end"]
    assert len(binding["context_sha256_start"]) == 64
    context = binding["context_path"]
    assert context.startswith(str(root / ".run" / "gates" / "ctx-"))
    assert observed["executed_root"] == context and observed["context_env"] == context
    assert observed["pythonpath"].split(os.pathsep)[0] == f"{context}/backend"
    for key in (
        "executed_erev_api",
        "executed_erev_engine",
        "executed_repo_root",
        "executed_alembic_ini",
        "executed_versions_dir",
    ):
        assert binding[key].startswith(context), key
    assert binding["executed_python"] == sys.executable == binding["python"]
    # Run binding (Codex 1510): a run id minted per run and the run's start, for the manifest to
    # bind the inner report to the run that produced it.
    assert re.fullmatch(r"[0-9a-f]{32}", binding["run_id"]), binding["run_id"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", binding["run_started_at"])
    assert report["started_at"] >= binding["run_started_at"]
    assert binding["context_kept"] is False and not Path(context).exists(), "removed on exit"
    assert binding["worktree_dirty_after"] is False
    # The stub source has no lock files and no reused artifacts: recorded as such, never failed.
    assert binding["uv_lock_sha256"] is None and binding["package_lock_sha256"] is None
    assert binding["venv"] is None and binding["node_modules"] is None
    assert binding["dependencies"] == {
        "venv": "not applicable (no backend/.venv)",
        "node_modules": "not applicable (no frontend/node_modules)",
        "mismatches": [],
    }
    return str(context)


def test_scripts_parse_and_use_the_ruled_mechanism() -> None:
    assert subprocess.run(["bash", "-n", str(GATE_CONTEXT)], check=False).returncode == 0
    text = GATE_REPORT.read_text(encoding="utf-8")
    assert '"clone", "--quiet", "--shared", "--no-checkout"' in text
    assert '"checkout", "--quiet", "--detach"' in text
    assert "git worktree" not in text, "the shared repository's .git is never written"
    assert "import erev" not in text.split("PROOF_PROGRAM")[0], "standard library only"
    wrapper = GATE_CONTEXT.read_text(encoding="utf-8")
    assert 'scripts/gate_report.py" "$GATE" --exec -- "$@"' in wrapper


def test_stable_source_is_bound_to_the_captured_commit(scratch: Path) -> None:
    repo, head_a, _ = _repo(scratch)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    result = _gate(repo, "ci")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK ci"
    assert "gate-context: ci runs in " in result.stdout and MODE_DIRTY not in result.stdout
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    _assert_bound(report, observed, repo, head_a, tree_a)
    assert report["failures"] == []
    assert report["source_binding"]["worktree_head_after"] == head_a
    assert report["source_binding"]["context_inner"] is False


def test_persistent_move_of_the_worktree_never_reaches_the_stage(scratch: Path) -> None:
    # A → B, stays B (v4 "persistent"): the stage reads A in the context; the report is bound to A
    # and records that the worktree ended at B.
    repo, head_a, head_b = _repo(scratch)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    result = _gate(repo, "ci", ACTOR_TO=head_b)
    assert result.returncode == 0, result.stdout + result.stderr
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    _assert_bound(report, observed, repo, head_a, tree_a)
    assert observed["actor_head"] == head_b, "the actor really moved the original checkout"
    assert report["source_binding"]["worktree_head_after"] == head_b
    assert (repo / "marker.txt").read_text() == "SOURCE_B\n"


def test_transient_move_of_the_worktree_never_reaches_the_stage(scratch: Path) -> None:
    # A → B → A (v4 "transient"): the schedule Codex modelled; A throughout, bound to A.
    repo, head_a, head_b = _repo(scratch)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    result = _gate(repo, "ci", ACTOR_TO=head_b, ACTOR_BACK=head_a)
    assert result.returncode == 0, result.stdout + result.stderr
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    _assert_bound(report, observed, repo, head_a, tree_a)
    assert report["source_binding"]["worktree_head_after"] == head_a
    assert git(repo, "status", "--porcelain") == ""


def test_change_inside_the_context_fails_the_run(scratch: Path) -> None:
    repo, head_a, _ = _repo(scratch)
    result = _gate(repo, "ci", MUTATE_CWD="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        "FAIL ci: source changed in the execution context during the run"
    )
    report = _report(repo, "ci")
    binding = report["source_binding"]
    assert binding["mode"] == MODE_CONTEXT
    assert binding["context_sha256_start"] != binding["context_sha256_end"]
    assert binding["tree_sha"] == binding["tree_sha_end"], "the tree sha alone misses an edit"
    assert report["exit_code"] == 1
    assert report["failures"][-1] == {"stage": "source", "exit_code": 1}
    assert _observed(repo, "ci")["marker"] == "SOURCE_A"


def test_dirty_worktree_runs_in_place_and_is_labelled(scratch: Path) -> None:
    repo, head_a, _ = _repo(scratch)
    (repo / "marker.txt").write_text("edited, uncommitted\n", encoding="utf-8")
    result = _gate(repo, "ci")
    assert result.returncode == 0, result.stdout + result.stderr
    assert MODE_DIRTY in result.stdout
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    assert report["worktree_dirty"] is True and report["exit_code"] == 0
    binding = report["source_binding"]
    assert binding["mode"] == MODE_DIRTY and binding["captured_sha"] == head_a
    assert binding["context_path"] is None and binding["tree_sha"] is None
    assert binding["worktree_dirty_after"] is True
    assert observed["executed_root"] == str(repo) and observed["context_env"] == ""
    assert observed["marker"] == "edited, uncommitted"


def test_inner_invocation_inside_a_context_executes_in_place(scratch: Path) -> None:
    # `make <gate>-gate` inside a context made by gate_context.sh: EREV_GATE_CONTEXT names this
    # repository, so no second clone; the same proof and hash checks apply and the binding says so.
    repo, head_a, _ = _repo(scratch)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    result = _gate(repo, "ci", EREV_GATE_CONTEXT=str(repo), EREV_GATE_CAPTURED_SHA=head_a)
    assert result.returncode == 0, result.stdout + result.stderr
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    binding = report["source_binding"]
    assert binding["mode"] == MODE_CONTEXT and binding["context_inner"] is True
    assert binding["context_path"] == str(repo) and observed["executed_root"] == str(repo)
    assert binding["tree_sha"] == tree_a == binding["tree_sha_end"]
    assert binding["executed_erev_api"].startswith(str(repo))
    assert (
        not (repo / ".run" / "gates").exists()
        or list((repo / ".run" / "gates").glob("ctx-*")) == []
    )


def test_module_origin_proof_fails_closed(scratch: Path) -> None:
    # A source whose erev_api cannot resolve inside the context fails before any stage runs.
    repo, head_a, _ = _repo(scratch)
    commit(repo, {"backend/erev_api/__init__.py": "raise ImportError('stub broken')\n"}, "broken")
    result = _gate(repo, "ci")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith("FAIL ci: binding proof failed")
    report = _report(repo, "ci")
    assert report["failures"] == [{"stage": "binding", "exit_code": 1}]
    assert report["counts"]["stages"] == {"observe": "not run"}
    assert not (repo / ".run" / "observed-ci.json").exists(), "no stage ran"


def test_exec_mode_wraps_a_writer_and_copies_its_report_back(scratch: Path) -> None:
    # scripts/gate_context.sh <gate> -- <writer>: the writer runs in the context, its report and
    # files come back to the worktree's .run/reports/<gate>/ stamped with source_binding, its exit
    # code passes through.
    repo, head_a, head_b = _repo(scratch)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    ok = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "gate_context.sh"),
            "answer-keys",
            "--",
            sys.executable,
            str(repo / ".run" / "writer.py"),
            "answer-keys",
            "0",
        ],
        cwd=repo,
        env=_env(EREV_GATE_PY=sys.executable),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert ok.stdout.splitlines()[-1] == "OK answer-keys"
    report = _report(repo, "answer-keys")
    binding = report["source_binding"]
    assert binding["mode"] == MODE_CONTEXT and binding["captured_sha"] == head_a
    assert binding["tree_sha"] == tree_a == binding["tree_sha_end"]
    assert report["counts"]["marker"] == "SOURCE_A"
    assert report["counts"]["cwd"] == binding["context_path"]
    assert report["exit_code"] == 0 and report["build_sha"] == head_a
    assert (repo / ".run" / "reports" / "answer-keys" / "extra.txt").read_text() == "kept\n"
    assert not Path(binding["context_path"]).exists()

    failing = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "gate_context.sh"),
            "parity",
            "--",
            sys.executable,
            str(repo / ".run" / "writer.py"),
            "parity",
            "3",
        ],
        cwd=repo,
        env=_env(EREV_GATE_PY=sys.executable),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert failing.returncode == 3, failing.stdout + failing.stderr
    report = _report(repo, "parity")
    assert report["exit_code"] == 3 and report["failures"] == [{"stage": "writer", "exit_code": 3}]
    assert report["source_binding"]["mode"] == MODE_CONTEXT

    # The writer that runs while the original checkout moves still sees A (the wrapper's context).
    moved = subprocess.run(
        [
            "bash",
            str(repo / "scripts" / "gate_context.sh"),
            "controls-report",
            "--",
            sys.executable,
            str(repo / ".run" / "hook.py"),
            str(repo),
            "controls-report",
        ],
        cwd=repo,
        env=_env(EREV_GATE_PY=sys.executable, ACTOR_TO=head_b, ACTOR_BACK=head_a, HOOK_REPORT="1"),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert moved.returncode == 0, moved.stdout + moved.stderr
    observed = _observed(repo, "controls-report")
    assert observed["marker"] == "SOURCE_A", "the writer read the context, not the moved checkout"
    assert _report(repo, "controls-report")["counts"] == {"observed": 1, "marker": "SOURCE_A"}
    assert observed["actor_head"] == head_b, "the original checkout was at B while it ran"
    assert git(repo, "rev-parse", "HEAD") == head_a


def test_linked_worktree_is_cloned_and_checked_out(scratch: Path) -> None:
    # Lanes are linked worktrees (a .git file pointing at the shared repository): the clone and the
    # detached checkout must work from one, and the shared .git gains no worktree entry.
    repo, head_a, _ = _repo(scratch)
    linked = scratch / "linked"
    git(repo, "worktree", "add", "-q", "--detach", str(linked), head_a)  # scratch repository only
    assert (linked / ".git").is_file()
    (linked / ".env").write_text("EREV_STUB=1\n", encoding="utf-8")
    (linked / ".run").mkdir()
    (linked / ".run" / "hook.py").write_text(HOOK, encoding="utf-8")
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    worktrees_before = git(repo, "worktree", "list")
    result = _gate(linked, "test-pg")
    assert result.returncode == 0, result.stdout + result.stderr
    report, observed = _report(linked, "test-pg"), _observed(linked, "test-pg")
    _assert_bound(report, observed, linked, head_a, tree_a)
    assert git(repo, "worktree", "list") == worktrees_before
    git(repo, "worktree", "remove", "--force", str(linked))


def test_orphaned_contexts_are_swept_and_kept_contexts_stay(scratch: Path) -> None:
    repo, head_a, _ = _repo(scratch)
    gates = repo / ".run" / "gates"
    orphan = gates / "ctx-ci-000000000000-999999"
    orphan.mkdir(parents=True)
    (orphan / ".run").mkdir()
    (orphan / ".run" / "gate-pid").write_text("999999\n", encoding="utf-8")  # no such process
    kept = _gate(repo, "ci", EREV_GATE_KEEP_CONTEXT="1")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    assert not orphan.exists(), "the dead context was swept at start"
    report = _report(repo, "ci")
    context = Path(report["source_binding"]["context_path"])
    assert context.exists() and report["source_binding"]["context_kept"] is True
    assert (context / ".env").exists() and stat.S_IMODE((context / ".env").stat().st_mode) == 0o600
    assert git(context, "rev-parse", "HEAD") == head_a
    assert (context / ".run" / "gate-pid").read_text().strip().isdigit()
    assert not (context / ".gate-pid").exists(), "no wrapper file at the context root"
    again = _gate(repo, "ci")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not context.exists()
    assert list(gates.glob("ctx-*")) == []


def _entry(repo: Path, gate: str, *command: str, **values: str) -> subprocess.CompletedProcess[str]:
    """The exact entry the Makefile uses: scripts/gate_context.sh <gate> -- <command…>."""
    return subprocess.run(
        ["bash", str(repo / "scripts" / "gate_context.sh"), gate, "--", *command],
        cwd=repo,
        env=_env(EREV_GATE_PY=sys.executable, **values),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def test_exec_entry_syntax_is_the_one_the_shell_emits(scratch: Path) -> None:
    # Codex draft review issue 1: the shell entry emits `gate_report.py <gate> --exec -- <command>`;
    # the parser must accept exactly that and hand the command over intact, its own options and
    # any `--` of its own included. The supported form without `--` keeps working.
    wrapper = GATE_CONTEXT.read_text(encoding="utf-8")
    assert 'exec "$PY" "$ROOT/scripts/gate_report.py" "$GATE" --exec -- "$@"' in wrapper
    repo, head_a, _ = _repo(scratch)
    writer = str(repo / ".run" / "writer.py")
    command = [sys.executable, writer, "answer-keys", "0", "valid", "--flag=x", "--", "tail"]
    result = _entry(repo, "answer-keys", *command)
    assert result.returncode == 0, result.stdout + result.stderr
    report = _report(repo, "answer-keys")
    assert report["argv"] == ["answer-keys", "0", "valid", "--flag=x", "--", "tail"]
    assert report["build_sha"] == head_a and report["exit_code"] == 0
    for form in (["--exec", "--", *command], ["--exec", *command]):
        direct = subprocess.run(
            [sys.executable, str(repo / "scripts" / "gate_report.py"), "answer-keys", *form],
            cwd=repo,
            env=_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        assert direct.returncode == 0, direct.stdout + direct.stderr
        assert _report(repo, "answer-keys")["argv"] == command[2:]
    empty = subprocess.run(
        [sys.executable, str(repo / "scripts" / "gate_report.py"), "parity", "--exec", "--"],
        cwd=repo,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert empty.returncode != 0 and "--exec expects a command" in empty.stderr
    assert not (repo / ".run" / "reports" / "parity").exists()


@pytest.mark.parametrize(
    ("mode", "detail"),
    [
        ("absent", "missing"),
        ("malformed", "malformed (not JSON)"),
        ("list", "malformed (not a JSON object)"),
        ("schema", "schema: missing counts"),
        ("identity", "identity: build_sha 000000000000 is not the captured"),
        ("empty", "population: counts carries no figure"),
    ],
)
def test_exec_mode_fails_closed_without_usable_inner_evidence(
    scratch: Path, mode: str, detail: str
) -> None:
    # Codex draft review issue 2: a command that exits 0 but leaves no usable DG-MK-00g report is
    # a FAIL with failures[].stage "report"; the wrapper never writes a successful empty record and
    # the manifest consumer classifies the result FAIL.
    repo, head_a, _ = _repo(scratch)
    result = _entry(
        repo, "parity", sys.executable, str(repo / ".run" / "writer.py"), "parity", "0", mode
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith("FAIL parity: no usable gate report")
    report = _report(repo, "parity")
    assert report["exit_code"] == 1 and report["build_sha"] == head_a
    (failure,) = [entry for entry in report["failures"] if entry["stage"] == "report"]
    assert failure["exit_code"] == 1 and failure["detail"].startswith(detail), failure
    if mode in ("absent", "malformed", "list"):
        assert report["counts"] == {"stages": {}}, "nothing invented in place of the evidence"
    assert report["source_binding"]["mode"] == MODE_CONTEXT
    consumer = load_script()
    verdict = consumer.gate_result(repo / ".run" / "reports" / "parity" / "report.json", head_a)
    assert verdict.result == "FAIL"


def test_exec_mode_binds_the_inner_report_to_this_run(scratch: Path) -> None:
    # Codex 1510 (b): the wrapper hands EREV_GATE_RUN_ID to the command; an inner report from
    # another run (foreign run_id) or written before this run began (stale started_at) is refused
    # — an archived or previous file never passes as this run's evidence.
    repo, head_a, _ = _repo(scratch)
    ok = _entry(repo, "parity", sys.executable, str(repo / ".run" / "writer.py"), "parity", "0")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    report = _report(repo, "parity")
    assert report["run_id"] == report["source_binding"]["run_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", report["run_id"])
    for patch, detail in (
        ({"run_id": "0" * 32}, "stale: run_id"),
        (
            {
                "started_at": "2020-01-01T00:00:00.000000Z",
                "finished_at": "2020-01-01T00:00:01.000000Z",
            },
            "stale: started_at",
        ),
    ):
        result = _entry(
            repo,
            "parity",
            sys.executable,
            str(repo / ".run" / "writer.py"),
            "parity",
            "0",
            WRITER_PATCH=json.dumps(patch),
        )
        assert result.returncode == 1, (patch, result.stdout, result.stderr)
        failure = _report(repo, "parity")["failures"][-1]
        assert failure["stage"] == "report" and failure["detail"].startswith(detail), failure


def test_stubbed_inner_make_can_never_produce_a_pass(scratch: Path) -> None:
    # Codex retest of 84e1879: the Makefile's documented test stub `GATE_MAKE=true` turns the inner
    # `make <gate>-gate` into `true`, which writes no report. Through the exact entry that is a
    # FAIL {stage: report, detail: missing} with a non-zero exit and a FAIL at the consumer, never
    # a manufactured PASS entry.
    repo, head_a, _ = _repo(scratch)
    result = _entry(repo, "ci", "true", "--no-print-directory", "ci-gate")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        "FAIL ci: no usable gate report from the command (missing)"
    )
    report = _report(repo, "ci")
    assert report["exit_code"] == 1 and report["counts"] == {"stages": {}}
    assert report["failures"] == [{"stage": "report", "exit_code": 1, "detail": "missing"}]
    assert report["build_sha"] == head_a
    assert report["source_binding"]["mode"] == MODE_CONTEXT, "binding diagnostics preserved"
    verdict = load_script().gate_result(repo / ".run" / "reports" / "ci" / "report.json", head_a)
    assert verdict.result == "FAIL"


JUNIT_MIXED = """<testsuites><testsuite name="pytest" tests="5" failures="1" errors="0" skipped="3">
<testcase classname="t" name="ok"/>
<testcase classname="t" name="bad"><failure message="boom"/></testcase>
<testcase classname="t" name="skipped_one"><skipped type="pytest.skip" message="reason"/></testcase>
<testcase classname="t" name="xfail_one"><skipped type="pytest.xfail" message="post-rc"/></testcase>
<testcase classname="t" name="xfail_two"><skipped type="pytest.xfail" message="post-rc"/></testcase>
</testsuite></testsuites>
"""


def test_junit_counts_reports_xfailed_in_its_own_count(scratch: Path) -> None:
    # Codex on 209120c: the ci report said `skipped: 5` for five xfails. pytest writes an xfail
    # as `<skipped type="pytest.xfail">`; the counter must keep it apart from a real skip.
    gate_report = _load_gate_report()
    path = scratch / "mixed.xml"
    path.write_text(JUNIT_MIXED, encoding="utf-8")
    assert gate_report.junit_counts(path) == {
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "xfailed": 2,
    }
    vitest = scratch / "vitest.xml"
    vitest.write_text(
        '<testsuites><testsuite name="v" tests="2" failures="0" errors="0" skipped="1">'
        '<testcase name="a"/><testcase name="b"><skipped/></testcase></testsuite></testsuites>',
        encoding="utf-8",
    )
    assert gate_report.junit_counts(vitest) == {
        "passed": 1,
        "failed": 0,
        "skipped": 1,
        "xfailed": 0,
    }


def _load_gate_report() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("gate_report_under_test", GATE_REPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID_INNER: dict[str, Any] = {
    "target": "parity",
    "command": "make parity",
    "build_sha": "a" * 40,
    "worktree_dirty": False,
    "started_at": "2026-09-19T18:00:00.000000Z",
    "finished_at": "2026-09-19T18:00:01.000000Z",
    "exit_code": 0,
    "counts": {"selected": 3, "passed": 3},
    "failures": [],
}

TYPED_FIELD_NEGATIVES: dict[str, tuple[dict[str, Any], str]] = {
    # Codex retest of 5e29be6: the three accepted shapes.
    "command-object": ({"command": {"x": 1}}, "schema: command is not a non-empty string"),
    "started_at-null": (
        {"started_at": None},
        "schema: started_at is not an RFC 3339 instant with an offset",
    ),
    "worktree_dirty-string": (
        {"worktree_dirty": "false"},
        "schema: worktree_dirty is not a boolean",
    ),
    # One wrong type per remaining key, plus the instant rules.
    "target-int": ({"target": 7}, "schema: target is not a string"),
    "command-empty": ({"command": ""}, "schema: command is not a non-empty string"),
    "build_sha-short": ({"build_sha": "abc123"}, "schema: build_sha is not a 40-hex sha"),
    "build_sha-int": ({"build_sha": 12}, "schema: build_sha is not a 40-hex sha"),
    "finished_at-naive": (
        {"finished_at": "2026-09-19T18:00:01"},
        "schema: finished_at is not an RFC 3339 instant with an offset",
    ),
    "finished-before-started": (
        {"finished_at": "2026-09-19T17:59:59Z"},
        "schema: finished_at precedes started_at",
    ),
    "exit_code-string": ({"exit_code": "0"}, "schema: exit_code is not an integer"),
    "exit_code-bool": ({"exit_code": False}, "schema: exit_code is not an integer"),
    "counts-list": ({"counts": [1]}, "schema: counts is not an object"),
    "failures-object": ({"failures": {}}, "schema: failures is not a list"),
}


# Codex retest of 2b98f7c: the accepted lexical profile is RFC 3339 date-time only
# (`YYYY-MM-DDThh:mm:ss[.fraction](Z|±hh:mm)`); datetime.fromisoformat alone also takes ISO week
# dates, ordinal dates and a space separator.
INSTANT_NEGATIVES = (
    "2026-W38-6T12:00:00+00:00",  # ISO week date
    "2026-262T12:00:00Z",  # ordinal date
    "2026-09-19 18:00:00Z",  # space separator
    "2026-09-19T18:00Z",  # no seconds
    "20260919T180000Z",  # basic format
    "2026-09-19T18:00:00",  # no offset
    "2026-09-19",  # date only
)
INSTANT_POSITIVES = (
    "2026-09-19T18:00:00Z",
    "2026-09-19T18:00:00.000000Z",
    "2026-09-19T18:00:00.5+02:00",
    "2026-09-19T18:00:00-05:00",
)


def test_usable_evidence_types_every_primitive_field() -> None:
    # DG-MK-00i promises typed fields: every one of the nine keys is type-checked, not only
    # exit_code, counts and failures. Identity and population follow the type checks.
    gate_report = _load_gate_report()
    assert gate_report.usable_evidence(VALID_INNER, "parity", "a" * 40) is None
    for name, (patch, detail) in TYPED_FIELD_NEGATIVES.items():
        report = dict(VALID_INNER) | patch
        assert gate_report.usable_evidence(report, "parity", "a" * 40) == detail, name
    other_offset = dict(VALID_INNER) | {"finished_at": "2026-09-19T20:00:01+02:00"}
    assert gate_report.usable_evidence(other_offset, "parity", "a" * 40) is None, "same instant"
    for value in INSTANT_NEGATIVES:
        for key in ("started_at", "finished_at"):
            report = dict(VALID_INNER) | {key: value}
            assert gate_report.usable_evidence(report, "parity", "a" * 40) == (
                f"schema: {key} is not an RFC 3339 instant with an offset"
            ), (key, value)
    for value in INSTANT_POSITIVES:
        report = dict(VALID_INNER) | {"started_at": value, "finished_at": "2026-09-20T00:00:00Z"}
        assert gate_report.usable_evidence(report, "parity", "a" * 40) is None, value
    assert gate_report.usable_evidence(VALID_INNER, "ci", "a" * 40) == (
        "identity: target 'parity' is not 'ci'"
    )
    assert gate_report.usable_evidence(VALID_INNER, "parity", "b" * 40).startswith(
        "identity: build_sha aaaaaaaaaaaa is not the captured bbbbbbbbbbbb"
    )
    unpopulated = dict(VALID_INNER) | {"counts": {"stages": {}}}
    assert gate_report.usable_evidence(unpopulated, "parity", "a" * 40) == (
        "population: counts carries no figure"
    )
    # A report that itself reports a failure needs no population (a stage list that stopped at
    # lint has no figure; FAIL is FAIL) — 458e01d's ci FAIL carried a spurious population reason.
    failed_early = dict(VALID_INNER) | {
        "exit_code": 2,
        "counts": {"stages": {"env": "pass", "lint": "fail", "test": "not run"}},
        "failures": [{"stage": "lint", "exit_code": 2}],
    }
    assert gate_report.usable_evidence(failed_early, "parity", "a" * 40) is None


@pytest.mark.parametrize(
    ("name", "patch", "detail"),
    [(name, patch, detail) for name, (patch, detail) in TYPED_FIELD_NEGATIVES.items()][:3],
)
def test_exec_mode_refuses_wrongly_typed_inner_fields(
    scratch: Path, name: str, patch: dict[str, Any], detail: str
) -> None:
    # The three shapes Codex's retest of 5e29be6 saw accepted, through the exact entry: wrapper
    # exit 1, FAIL {stage: report}, the wrapper's own command string kept, consumer FAIL.
    repo, head_a, _ = _repo(scratch)
    result = _entry(
        repo,
        "parity",
        sys.executable,
        str(repo / ".run" / "writer.py"),
        "parity",
        "0",
        WRITER_PATCH=json.dumps(patch),
    )
    assert result.returncode == 1, name + result.stdout + result.stderr
    assert (
        result.stdout.splitlines()[-1]
        == f"FAIL parity: no usable gate report from the command ({detail})"
    )
    report = _report(repo, "parity")
    assert report["exit_code"] == 1 and report["build_sha"] == head_a
    assert report["failures"][-1] == {"stage": "report", "exit_code": 1, "detail": detail}
    assert report["command"] == "make parity", "the wrapper's command string, never an object"
    assert report["worktree_dirty"] is False, "the wrapper's own measurement stays authoritative"
    verdict = load_script().gate_result(
        repo / ".run" / "reports" / "parity" / "report.json", head_a
    )
    assert verdict.result == "FAIL"


UV_LOCK_A = 'version = 1\n\n[[package]]\nname = "Foo_Bar"\nversion = "1.0"\n'
UV_LOCK_B = 'version = 1\n\n[[package]]\nname = "Foo_Bar"\nversion = "1.1"\n'
NPM_LOCK_A = json.dumps(
    {"packages": {"": {"name": "stub"}, "node_modules/bar": {"version": "2.0"}}}
)
NPM_LOCK_B = json.dumps(
    {"packages": {"": {"name": "stub"}, "node_modules/bar": {"version": "2.1"}}}
)
LOCKS_A = {"backend/uv.lock": UV_LOCK_A, "frontend/package-lock.json": NPM_LOCK_A}
LOCKS_B = {"backend/uv.lock": UV_LOCK_B, "frontend/package-lock.json": NPM_LOCK_B}


def _artifacts(repo: Path, *, foo_version: str = "1.0", bar_version: str = "2.0") -> None:
    """Untracked reused artifacts: a venv with one installed distribution and node_modules with
    npm's hidden lock file, as make setup leaves them."""
    dist = repo / "backend" / ".venv" / "lib" / "python3.12" / "site-packages"
    dist = dist / f"foo_bar-{foo_version}.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: foo-bar\nVersion: {foo_version}\n"
    )
    modules = repo / "frontend" / "node_modules"
    modules.mkdir(parents=True)
    (modules / ".package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/bar": {"version": bar_version}}})
    )
    assert git(repo, "status", "--porcelain") == ""


def test_lock_identity_comes_from_the_executed_context_not_the_moved_worktree(
    scratch: Path,
) -> None:
    # Codex draft review issue 3: under a persistent A → B move the report must carry A's lock
    # hashes (the executed source) and, separately, the identity of the reused venv/node_modules.
    repo, head_a, head_b = _repo(scratch, LOCKS_A, LOCKS_B)
    _artifacts(repo)
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    result = _gate(repo, "ci", ACTOR_TO=head_b)
    assert result.returncode == 0, result.stdout + result.stderr
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    assert observed["marker"] == "SOURCE_A" and observed["actor_head"] == head_b
    assert (repo / "backend" / "uv.lock").read_text() == UV_LOCK_B, "the worktree is at B"
    binding = report["source_binding"]
    assert binding["mode"] == MODE_CONTEXT and binding["captured_sha"] == head_a
    assert binding["tree_sha"] == tree_a == binding["tree_sha_end"]
    assert binding["uv_lock_sha256"] == hashlib.sha256(UV_LOCK_A.encode()).hexdigest()
    assert binding["package_lock_sha256"] == hashlib.sha256(NPM_LOCK_A.encode()).hexdigest()
    assert binding["uv_lock_sha256"] != hashlib.sha256(UV_LOCK_B.encode()).hexdigest()
    venv = binding["venv"]
    assert venv["path"] == str((repo / "backend" / ".venv").resolve())
    assert venv["python"] == sys.executable and venv["python_version"] == platform_version()
    assert venv["distributions"] == 1 and len(venv["installed_sha256"]) == 64
    assert venv["installed_sha256"] == venv["installed_sha256_end"]
    modules = binding["node_modules"]
    assert modules["source"] == str((repo / "frontend" / "node_modules").resolve())
    assert modules["path"] == f"{binding['context_path']}/frontend/node_modules"
    assert modules["binding"] in ("clone", "hardlink"), modules
    assert modules["packages"] == 1 and len(modules["installed_sha256"]) == 64
    assert venv["binding"] == "symlink" and venv["source"] == venv["path"]
    assert binding["dependencies"] == {
        "venv": "consistent",
        "node_modules": "consistent",
        "mismatches": [],
    }
    assert binding["worktree_head_after"] == head_b


def test_context_root_carries_only_the_source_plus_run_and_env(scratch: Path) -> None:
    # ci on 89b5f10: the repository-layout test, running inside the context, saw the wrapper's
    # `.gate-pid` marker as an unexpected top-level entry. The context root may carry nothing
    # beyond the commit's tracked top-level entries, `.git`, `.run` and `.env`; the marker lives
    # under `.run/`, and the stages see tool caches pinned under `<ctx>/backend/`.
    repo, head_a, _ = _repo(scratch)
    kept = _gate(repo, "ci", EREV_GATE_KEEP_CONTEXT="1")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    report, observed = _report(repo, "ci"), _observed(repo, "ci")
    context = Path(report["source_binding"]["context_path"])
    tracked = {
        line.split("/", 1)[0] for line in git(repo, "ls-tree", "--name-only", head_a).splitlines()
    }
    entries = {path.name for path in context.iterdir()}
    assert entries <= tracked | {".git", ".run", ".env"}, sorted(entries - tracked)
    assert (context / ".run" / "gate-pid").read_text().strip().isdigit()
    assert observed["ruff_cache_dir"] == f"{context}/backend/.ruff_cache"
    assert observed["mypy_cache_dir"] == f"{context}/backend/.mypy_cache"
    again = _gate(repo, "ci")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not context.exists()


def test_node_modules_is_a_real_directory_in_the_context(scratch: Path) -> None:
    # ci gate on 458e01d: `npm --prefix <ctx>/frontend ls` reported every package extraneous
    # because the context's node_modules was a symlink into the worktree (npm resolves real paths).
    # The context now carries a copy-on-write clone (APFS clonefile; hardlink tree elsewhere): a
    # real directory with the worktree's content identity, removed with the context.
    repo, head_a, _ = _repo(scratch, LOCKS_A)
    _artifacts(repo)
    kept = _gate(repo, "ci", EREV_GATE_KEEP_CONTEXT="1")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    binding = _report(repo, "ci")["source_binding"]
    context = Path(binding["context_path"])
    modules = context / "frontend" / "node_modules"
    assert modules.is_dir() and not modules.is_symlink()
    assert (modules / ".package-lock.json").read_bytes() == (
        repo / "frontend" / "node_modules" / ".package-lock.json"
    ).read_bytes()
    assert (modules / ".package-lock.json").resolve() != (
        repo / "frontend" / "node_modules" / ".package-lock.json"
    ).resolve()
    venv = context / "backend" / ".venv"
    assert venv.is_symlink() and venv.resolve() == (repo / "backend" / ".venv").resolve()
    assert binding["node_modules"]["binding"] in ("clone", "hardlink")
    assert binding["node_modules"]["path"] == str(modules)
    again = _gate(repo, "ci")
    assert again.returncode == 0, again.stdout + again.stderr
    assert not context.exists(), "the clone goes with the context"
    assert (repo / "frontend" / "node_modules" / ".package-lock.json").is_file(), "source intact"


@pytest.mark.parametrize(
    ("artifacts", "extra", "mismatch"),
    [
        ({"foo_version": "1.1"}, {}, "foo-bar 1.1 (backend/uv.lock 1.0)"),
        ({"bar_version": "2.1"}, {}, "node_modules/bar 2.1 (frontend/package-lock.json 2.0)"),
        ({}, {"backend/uv.lock": None}, "backend/uv.lock absent in the executed source"),
    ],
)
def test_reused_artifacts_inconsistent_with_the_context_lock_fail_closed(
    scratch: Path, artifacts: dict[str, str], extra: dict[str, None], mismatch: str
) -> None:
    # The explicit dependency policy of GATE-BIND-1: the installed venv/node_modules must agree with
    # the executed source's lock files, else the run fails with failures[].stage "source" before
    # any stage executes.
    locks = {k: v for k, v in LOCKS_A.items() if k not in extra}
    repo, head_a, _ = _repo(scratch, locks)
    _artifacts(repo, **artifacts)
    result = _gate(repo, "ci")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        "FAIL ci: installed dependencies differ from the executed source's lock files: " + mismatch
    )
    report = _report(repo, "ci")
    assert report["failures"] == [{"stage": "source", "exit_code": 1, "check": "dependencies"}]
    assert report["counts"]["stages"] == {"observe": "not run"}
    assert not (repo / ".run" / "observed-ci.json").exists(), "no stage ran"
    dependencies = report["source_binding"]["dependencies"]
    assert dependencies["mismatches"] == [mismatch]
    assert "mismatch" in (dependencies["venv"], dependencies["node_modules"])
    assert report["build_sha"] == head_a


def platform_version() -> str:
    return ".".join(str(part) for part in sys.version_info[:3])
