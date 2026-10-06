"""Release manifest generator and production startup (05 §7.8 REL-01 to REL-04; 04 T-PLT-38;
dev-guide DG-MK-release-manifest, DG-MK-00g, DG-ENG-10; BUILD_SPEC PLF-20, SOP-2).

``scripts/release_manifest.py`` runs offline against scratch git repositories and scratch report
directories under ``.run``; it never runs a gate. The startup tests build the api and call the
worker entry point with production settings and no database: the manifest check of REL-03 fires
before any session is opened, so a production process without a manifest exits before it connects.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from erev_api import worker as worker_module
from erev_api.config import Environment, Settings
from erev_api.controls import release
from erev_api.controls.release import ReleaseManifestError, release_facts
from erev_api.controls.validation_level import DeclaredLevel, declared_validation_level
from erev_api.db.migration_ops import code_head
from erev_api.main import create_app
from erev_engine import ENGINE_VERSION
from support.production import production_settings
from support.release_manifest import (
    ROOT,
    all_gates_pass,
    answer_keys_report_body,
    commit,
    gate_report,
    git,
    load_script,
    scratch_corpus,
    scratch_repo,
)

_ABSENT = object()
GATES = ("ci", "parity", "answer-keys", "properties", "test-pg", "controls-report", "e2e", "perf")
MANIFEST_KEYS = (
    "audit_deps",
    "build_sha",
    "control_impact_tags",
    "created_at",
    "dependency_lock_sha256",
    "engine_version",
    "gate_results",
    "images",
    "schema_revision",
)
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _run(
    *args: str,
    strict_env: str | None = None,
    cwd: Path = ROOT,
    git_ceiling: Path | None = None,
    env_values: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os
    import sys

    # VALIDATION_LEVEL is data the generator reads from the environment (step 7): the tests start
    # from an environment without it and add exactly what each case declares.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("STRICT", "VALIDATION_LEVEL", "EREV_VALIDATION_LEVEL_RAW")
    }
    if strict_env is not None:
        env["STRICT"] = strict_env
    if env_values:
        env.update(env_values)
    if git_ceiling is not None:
        # Scratch directories live under .run inside the worktree; the ceiling keeps git from
        # walking up into it, so the directory is outside any repository.
        env["GIT_CEILING_DIRECTORIES"] = str(git_ceiling)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "release_manifest.py"), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _generate(
    root: Path,
    reports: Path,
    out: Path,
    *extra: str,
    git_ceiling: Path | None = None,
    env_values: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run(
        "--root",
        str(root),
        "--reports-dir",
        str(reports),
        "--out",
        str(out),
        "--command",
        "make release-manifest",
        *extra,
        git_ceiling=git_ceiling,
        env_values=env_values,
    )


def _read(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.control("CTL-032")
def test_rel_02_result_rules(scratch: Path) -> None:
    """CTL-032, the manifest's half ("release manifest with gate evidence"): a gate's
    result and its output hash are its report's — PASS only for a clean report of
    this build that ended 0, FAIL for one that failed, NOT_RUN otherwise. Not
    witnessed here: what binds a report to its build
    (``test_gate_bind_1_only_bound_reports_pass``), which keys the manifest holds
    (``test_rel_01_manifest_keys``), the control-impact tags
    (``test_rel_04_control_impact_tags``), and the stamp on the run records
    (``tests/domain/platform/test_release_stamping.py``).
    """
    # REL-02 / DG-MK-release-manifest step (2): NOT_RUN (absent or another build_sha), FAIL
    # (exit_code ≠ 0), NOT_RUN (dirty worktree), else PASS; output_sha256 is the report file's.
    script = load_script()
    head = "a" * 40
    reports = scratch / "reports"
    cases = {
        "ci": dict(build_sha=head, exit_code=0, worktree_dirty=False),
        "parity": dict(build_sha=head, exit_code=1, worktree_dirty=False),
        "answer-keys": dict(build_sha="b" * 40, exit_code=0, worktree_dirty=False),
        "properties": dict(build_sha=head, exit_code=0, worktree_dirty=True),
        # FAIL takes precedence over the dirty rule: the report proves a failure.
        "test-pg": dict(build_sha=head, exit_code=2, worktree_dirty=True),
    }
    for gate, values in cases.items():
        gate_report(reports, gate, **values)  # type: ignore[arg-type]
    expected = {
        "ci": "PASS",
        "parity": "FAIL",
        "answer-keys": "NOT_RUN",
        "properties": "NOT_RUN",
        "test-pg": "FAIL",
        "controls-report": "NOT_RUN",
    }
    for gate, result in expected.items():
        path = reports / gate / "report.json"
        found = script.gate_result(path, head)
        assert found.result == result, gate
        if path.is_file():
            assert found.output_sha256 == hashlib.sha256(path.read_bytes()).hexdigest(), gate
            assert found.command == f"make {gate}"
            assert found.finished_at == "2026-09-19T10:05:00.000000Z"
        else:
            assert (found.output_sha256, found.command, found.finished_at) == (None, None, None)
    # A report that is not a JSON object is evidence of nothing: NOT_RUN, digest still recorded.
    broken = reports / "e2e" / "report.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{not json", encoding="utf-8")
    found = script.gate_result(broken, head)
    assert found.result == "NOT_RUN"
    assert found.output_sha256 == hashlib.sha256(broken.read_bytes()).hexdigest()
    # A report without an integer exit_code proves neither a pass nor a failure.
    gate_report(reports, "perf", build_sha=head, extra={"exit_code": None})
    assert script.gate_result(reports / "perf" / "report.json", head).result == "NOT_RUN"


@pytest.mark.control("CTL-032")
def test_gate_bind_1_only_bound_reports_pass(scratch: Path) -> None:
    """CTL-032, the manifest's half ("gate evidence"): a clean, successful report of
    this build is PASS only when it is bound to an immutable execution context of
    this build, did not start before the run that bound it and counts at least one
    figure; any other binding, an absent, invalid or stale timestamp, or counts
    without a figure are NOT_RUN, and a failure stays FAIL without proof of
    identity. Not witnessed here: the rules of exit code, build and worktree
    (``test_rel_02_result_rules``) and the full-corpus rule of the answer-keys gate
    (``test_rel_cov_1_answer_keys_evidence_is_full_corpus_only``).
    """
    # GATE-BIND-1 (DG-MK-00i; 05 REL-02): a successful, clean report of this build is PASS only
    # when scripts/gate_context.sh bound it to an immutable execution context of this build; any
    # other binding, or none, is NOT_RUN. FAIL stays FAIL (a failure needs no proof of identity).
    from support.release_manifest import source_binding

    script = load_script()
    head = "a" * 40
    reports = scratch / "reports"
    bound = gate_report(reports, "ci", build_sha=head)
    assert script.gate_result(bound, head).result == "PASS"
    unbound = gate_report(reports, "parity", build_sha=head, bound=False)
    assert script.gate_result(unbound, head).result == "NOT_RUN"
    failed_unbound = gate_report(reports, "e2e", build_sha=head, exit_code=1, bound=False)
    assert script.gate_result(failed_unbound, head).result == "FAIL"
    dirty_mode = "worktree-dirty (development; not release evidence)"
    cases: dict[str, Any] = {
        "dirty-mode": source_binding(head, mode=dirty_mode),
        "other-sha": source_binding(head, captured_sha="b" * 40),
        "tree-changed": source_binding(head, tree_sha_end="0" * 40),
        "content-changed": source_binding(head, context_sha256_end="0" * 64),
        "no-tree": source_binding(head, tree_sha=None, tree_sha_end=None),
        "not-an-object": "immutable-context",
    }
    for name, binding in cases.items():
        path = gate_report(
            reports, "properties", build_sha=head, bound=False, extra={"source_binding": binding}
        )
        assert script.gate_result(path, head).result == "NOT_RUN", name
    assert script.source_bound({"build_sha": head, "source_binding": source_binding(head)})

    # REL-COV-RUN-TIME-R1 (Codex 1546): the chronology check needs valid timezone-aware instants on
    # both sides — an absent, non-string or invalid timestamp is refused by name, never skipped —
    # and compares parsed instants, so an RFC 3339 offset cannot make an older report look newer.
    def bound_result(**changes: Any) -> Any:
        binding = source_binding(head)
        extra: dict[str, Any] = {"source_binding": binding}
        for key, value in changes.items():
            if key == "started_at":
                extra["started_at"] = value
            elif value is _ABSENT:
                binding.pop(key)
            else:
                binding[key] = value
        return script.gate_result(
            gate_report(reports, "ci", build_sha=head, bound=False, extra=extra), head
        )

    for changes, needle in (
        ({"run_started_at": _ABSENT}, "run_started_at"),
        ({"run_started_at": None}, "run_started_at"),
        ({"run_started_at": "yesterday"}, "run_started_at"),
        ({"run_started_at": "2026-09-19T10:00:00"}, "run_started_at"),  # no offset
        ({"started_at": "2026-09-19"}, "started_at"),
        ({"started_at": None}, "started_at"),
        # 11:00+02:00 = 09:00Z precedes the run's 10:00Z although it compares later as text.
        ({"started_at": "2026-09-19T11:00:00+02:00"}, "stale"),
        ({"started_at": "2026-09-19T09:59:59.999999Z"}, "stale"),
    ):
        verdict = bound_result(**changes)
        assert verdict.result == "NOT_RUN" and verdict.reason and needle in verdict.reason, (
            changes,
            verdict,
        )
    # Offset-equivalent instants are the same instant: accepted; a later start is accepted.
    for started in (
        "2026-09-19T12:00:00+02:00",
        "2026-09-19T10:00:00.000000Z",
        "2026-09-19T10:00:01Z",
    ):
        verdict = bound_result(started_at=started)
        assert verdict.result == "PASS", (started, verdict)
    # Evidence population (DG-MK-00g; Codex draft review issue 2): a bound, clean, successful
    # report whose counts carry no figure proves nothing and is NOT_RUN; FAIL stays FAIL.
    population: dict[str, tuple[Any, str]] = {
        "empty": ({}, "NOT_RUN"),
        "empty-stages": ({"stages": {}}, "NOT_RUN"),
        "stage-not-run": ({"stages": {"pg": "not run"}}, "NOT_RUN"),
        "strings-only": ({"marker": "SOURCE_A"}, "NOT_RUN"),
        "not-an-object": ("3 passed", "NOT_RUN"),
        "stages-all-pass": ({"stages": {"env": "pass", "lint": "pass"}}, "PASS"),
        "figure": ({"selected": 236, "passed": 236}, "PASS"),
        "nested-figure": ({"backend": {"passed": 0, "failed": 0, "skipped": 0}}, "PASS"),
    }
    for name, (counts, expected) in population.items():
        path = gate_report(reports, "answer-keys", build_sha=head, extra={"counts": counts})
        assert script.gate_result(path, head).result == expected, name
    failed = gate_report(reports, "answer-keys", build_sha=head, exit_code=1, extra={"counts": {}})
    assert script.gate_result(failed, head).result == "FAIL"


@pytest.mark.control("CTL-032")
def test_rel_01_manifest_keys(scratch: Path) -> None:
    """CTL-032, the manifest's half (03 REQ-CTL-003): the manifest records the engine
    version, the build, the migration head and, for every gate, its result with the
    hash of its report — null where no report was read. Not witnessed here: how a
    gate's result is decided (``test_rel_02_result_rules``), the control-impact
    tags (``test_rel_04_control_impact_tags``), and that the release row carries
    the manifest (``tests/pg/test_engine_release.py``).
    """
    # REL-01 / DG-MK-release-manifest steps (1), (4) to (6): the manifest's keys and layout.
    repo = scratch_repo(scratch / "repo")
    head = git(repo, "rev-parse", "HEAD")
    reports, out = scratch / "reports", scratch / "release-manifest.json"
    gate_report(reports, "ci", build_sha=head)
    result = _generate(repo, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK release-manifest"

    text = out.read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert text == json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    assert tuple(manifest) == MANIFEST_KEYS
    assert manifest["engine_version"] == ENGINE_VERSION
    assert manifest["build_sha"] == head
    assert manifest["schema_revision"] == code_head()
    assert TIMESTAMP.match(manifest["created_at"])
    assert tuple(manifest["gate_results"]) == tuple(sorted(GATES))
    for gate, entry in manifest["gate_results"].items():
        assert tuple(entry) == ("command", "finished_at", "output_sha256", "result"), gate
    ci = manifest["gate_results"]["ci"]
    assert ci["result"] == "PASS" and SHA256.match(ci["output_sha256"])
    assert ci["command"] == "make ci" and TIMESTAMP.match(ci["finished_at"])
    for gate in GATES:
        if gate != "ci":
            assert manifest["gate_results"][gate] == {
                "result": "NOT_RUN",
                "command": None,
                "output_sha256": None,
                "finished_at": None,
            }, gate
    assert manifest["control_impact_tags"] == sorted(manifest["control_impact_tags"])
    # The scratch repository has no lock files: the digests are null, never fabricated.
    assert manifest["dependency_lock_sha256"] == {"uv_lock": None, "package_lock": None}
    assert manifest["images"] == {
        name: {"tag": None, "digest": None} for name in ("api", "worker", "web")
    }
    assert manifest["audit_deps"] is None

    # REL-01 `validation_level` (05 rev 1.16; DG-MK-release-manifest step 7): absent unless the
    # author declares it, and then the stderr line says the release is undeclared (PATCH by the
    # T-PLT-38 default) — the generator never writes PATCH on its own.
    assert "validation_level" not in manifest
    assert declared_validation_level(manifest) == DeclaredLevel("PATCH", False)
    assert "validation_level undeclared" in result.stderr and "PATCH" in result.stderr
    declared_out = scratch / "declared.json"
    declared = _generate(repo, reports, declared_out, "--validation-level", "MINOR")
    assert declared.returncode == 0, declared.stdout + declared.stderr
    assert "undeclared" not in declared.stderr
    declared_manifest = _read(declared_out)
    assert tuple(declared_manifest) == (*MANIFEST_KEYS, "validation_level")
    assert declared_manifest["validation_level"] == "MINOR"
    assert declared_validation_level(declared_manifest) == DeclaredLevel("MINOR", True)
    assert {k: v for k, v in declared_manifest.items() if k != "validation_level"} == {
        k: v for k, v in manifest.items() if k != "created_at"
    } | {"created_at": declared_manifest["created_at"]}
    declared_report = _read(reports / "release-manifest" / "report.json")
    assert declared_report["validation_level"] == "MINOR"
    for level in ("PATCH", "MAJOR"):
        again = _generate(repo, reports, scratch / f"{level}.json", "--validation-level", level)
        assert again.returncode == 0, again.stdout + again.stderr
        assert _read(scratch / f"{level}.json")["validation_level"] == level
    invalid_out = scratch / "invalid.json"
    invalid = _generate(repo, reports, invalid_out, "--validation-level", "minor")
    assert invalid.returncode == 2, invalid.stdout + invalid.stderr
    assert "--validation-level" in invalid.stderr and "invalid choice" in invalid.stderr
    assert not invalid_out.exists(), "nothing is written on a refused literal"
    # P1-VL-S1: the whole authored value arrives as one literal (the recipe quotes it) and is
    # refused whole, before any manifest or report write; a repeated option is refused too.
    refused_reports = scratch / "reports-refused"
    whole = _generate(
        repo,
        refused_reports,
        scratch / "whole.json",
        "--validation-level",
        "MINOR --validation-level MAJOR",
    )
    assert whole.returncode == 2, whole.stdout + whole.stderr
    assert "--validation-level" in whole.stderr and "invalid choice" in whole.stderr
    assert not (scratch / "whole.json").exists()
    assert not (refused_reports / "release-manifest" / "report.json").exists()
    repeated = _generate(
        repo,
        refused_reports,
        scratch / "repeated.json",
        "--validation-level",
        "MINOR",
        "--validation-level",
        "MAJOR",
    )
    assert repeated.returncode == 2, repeated.stdout + repeated.stderr
    assert "--validation-level" in repeated.stderr and "once" in repeated.stderr
    assert not (scratch / "repeated.json").exists()
    assert not (refused_reports / "release-manifest" / "report.json").exists()

    # DG-MK-00g: the target's own report next to the gate reports it read.
    result = _generate(repo, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    report = _read(reports / "release-manifest" / "report.json")
    assert report["validation_level"] is None
    assert report["target"] == "release-manifest"
    assert report["command"] == "make release-manifest"
    assert report["build_sha"] == head
    assert report["worktree_dirty"] is False
    assert TIMESTAMP.match(report["started_at"]) and TIMESTAMP.match(report["finished_at"])
    assert report["exit_code"] == 0
    assert report["failures"] == []
    assert report["counts"]["gates"] == {"PASS": 1, "FAIL": 0, "NOT_RUN": 7}
    assert report["counts"]["control_impact_tags"] == len(manifest["control_impact_tags"])

    # The real repository's lock files are digested when present (step 4).
    real_out = scratch / "real-release-manifest.json"
    real = _generate(ROOT, scratch / "real-reports", real_out)
    assert real.returncode == 0, real.stdout + real.stderr
    locks = _read(real_out)["dependency_lock_sha256"]
    for key, relative in (
        ("uv_lock", "backend/uv.lock"),
        ("package_lock", "frontend/package-lock.json"),
    ):
        path = ROOT / relative
        if path.is_file():
            assert locks[key] == hashlib.sha256(path.read_bytes()).hexdigest(), key
        else:
            assert locks[key] is None, key


@pytest.mark.control("CTL-032")
def test_rel_04_control_impact_tags(scratch: Path) -> None:
    """CTL-032, the manifest's half (03 REQ-CTL-003 "control-impact tags"): the tags
    are the ids of the controls whose impact paths the release changed since the
    last version tag — every committed path where no version is tagged — sorted;
    outside a repository there is none. Not witnessed here: the gate evidence
    (``test_rel_01_manifest_keys``, ``test_rel_02_result_rules``).
    """
    # REL-04: sorted CTL ids whose impact_paths globs match `git diff --name-only <base>..HEAD`,
    # <base> the latest v* tag, else the empty tree.
    script = load_script()
    controls = script.load_impact_globs()
    by_id = dict(controls)
    assert "CTL-022" in by_id
    assert "backend/erev_engine/money.py" in by_id["CTL-022"]

    repo = scratch_repo(scratch / "repo", files={"docs/README.md": "scratch\n"})
    git(repo, "tag", "v0.1.0")
    commit(repo, {"backend/erev_engine/money.py": "# changed after the tag\n"}, "money")
    reports, out = scratch / "reports", scratch / "release-manifest.json"
    result = _generate(repo, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    tags = _read(out)["control_impact_tags"]
    assert "CTL-022" in tags
    assert tags == sorted(tags)
    changed = ["backend/erev_engine/money.py"]
    for control_id in tags:
        assert any(
            script.path_matches(glob, path) for glob in by_id[control_id] for path in changed
        ), control_id
    untouched = [
        control_id
        for control_id, globs in controls
        if not any(script.path_matches(glob, path) for glob in globs for path in changed)
    ]
    assert untouched and not set(untouched) & set(tags)
    report = _read(reports / "release-manifest" / "report.json")
    assert report["impact_base"] == "v0.1.0"
    assert report["counts"]["changed_paths"] == 1

    # Without a tag the base is the empty tree: every committed path counts as changed.
    untagged = scratch_repo(
        scratch / "untagged", files={"backend/erev_api/auth/sod.py": "# sod\n", "x.txt": "x\n"}
    )
    result = _generate(untagged, scratch / "reports-untagged", scratch / "untagged.json")
    assert result.returncode == 0, result.stdout + result.stderr
    tags = _read(scratch / "untagged.json")["control_impact_tags"]
    assert "CTL-034" in tags and "CTL-022" not in tags
    report = _read(scratch / "reports-untagged" / "release-manifest" / "report.json")
    assert report["impact_base"] == script.EMPTY_TREE
    assert report["counts"]["changed_paths"] == 2

    # Outside a repository there is no diff: no tag, build "nogit" (DG-MK-00g).
    plain = scratch / "plain"
    plain.mkdir()
    result = _generate(
        plain, scratch / "reports-plain", scratch / "plain.json", git_ceiling=scratch
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = _read(scratch / "plain.json")
    assert manifest["build_sha"] == "nogit"
    assert manifest["control_impact_tags"] == []
    report = _read(scratch / "reports-plain" / "release-manifest" / "report.json")
    assert report["impact_base"] is None and report["worktree_dirty"] is False


def test_impact_glob_semantics() -> None:
    # `**` spans directories, `*` and `?` stay within one path segment; matches are whole paths.
    script = load_script()
    matches = script.path_matches
    assert matches("backend/erev_engine/stages/**", "backend/erev_engine/stages/s01/a.py")
    assert matches("backend/erev_engine/stages/**", "backend/erev_engine/stages/a.py")
    assert not matches("backend/erev_engine/stages/**", "backend/erev_engine/stages_extra/a.py")
    assert not matches("backend/erev_engine/stages/**", "backend/erev_engine/stages")
    assert matches("backend/erev_engine/money.py", "backend/erev_engine/money.py")
    assert not matches("backend/erev_engine/money.py", "backend/erev_engine/money.pyc")
    assert not matches("backend/erev_engine/money.py", "other/backend/erev_engine/money.py")
    assert matches("backend/erev_api/db/*.py", "backend/erev_api/db/lint.py")
    assert not matches("backend/erev_api/db/*.py", "backend/erev_api/db/tables/platform.py")
    assert matches("**/migrations/**", "backend/erev_api/db/migrations/versions/0001_x.py")
    assert matches("docs/0?-GOAL.md", "docs/00-GOAL.md")
    assert not matches("docs/0?-GOAL.md", "docs/000-GOAL.md")
    assert not matches("backend/(erev)/x.py", "backend/erev/x.py"), "no regex leakage"


def test_strict_mode_exit_codes(scratch: Path) -> None:
    # DG-MK-release-manifest step (6): exit 0 after writing; STRICT exits 1 unless every gate is
    # PASS and the worktree is clean. Both `--strict` and the make variable STRICT=1 select it.
    repo = scratch_repo(scratch / "repo")
    corpus = scratch_corpus(repo)  # committed before head is read (REL-COV-1)
    head = git(repo, "rev-parse", "HEAD")
    reports, out = scratch / "reports", scratch / "release-manifest.json"

    relaxed = _generate(repo, reports, out)
    assert relaxed.returncode == 0, relaxed.stdout + relaxed.stderr
    assert relaxed.stdout.splitlines()[-1] == "OK release-manifest"
    assert all(gate["result"] == "NOT_RUN" for gate in _read(out)["gate_results"].values())

    strict = _generate(repo, reports, out, "--strict")
    assert strict.returncode == 1, strict.stdout + strict.stderr
    assert strict.stdout.splitlines()[-1].startswith("FAIL release-manifest: ")
    assert "NOT_RUN" in strict.stdout.splitlines()[-1]
    assert out.is_file(), "the manifest is written before the strict verdict"
    report = _read(reports / "release-manifest" / "report.json")
    assert report["exit_code"] == 1
    assert report["failures"][0]["stage"] == "strict"
    assert sorted(report["failures"][0]["gates"]) == sorted(GATES)

    all_gates_pass(reports, GATES, build_sha=head, corpus=corpus)
    passing = _generate(repo, reports, out, "--strict")
    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert passing.stdout.splitlines()[-1] == "OK release-manifest"
    assert all(gate["result"] == "PASS" for gate in _read(out)["gate_results"].values())

    (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    dirty = _generate(repo, reports, out, "--strict")
    assert dirty.returncode == 1, dirty.stdout + dirty.stderr
    assert "worktree" in dirty.stdout.splitlines()[-1]
    assert _read(reports / "release-manifest" / "report.json")["worktree_dirty"] is True
    (repo / "untracked.txt").unlink()

    via_variable = _run(
        "--root", str(repo), "--reports-dir", str(reports), "--out", str(out), strict_env="1"
    )
    assert via_variable.returncode == 0, via_variable.stdout + via_variable.stderr
    gate_report(reports, "perf", build_sha=head, exit_code=1)
    failing = _run(
        "--root", str(repo), "--reports-dir", str(reports), "--out", str(out), strict_env="1"
    )
    assert failing.returncode == 1, failing.stdout + failing.stderr
    assert "perf" in failing.stdout.splitlines()[-1]


def test_images_and_audit_deps_come_from_reports(scratch: Path) -> None:
    # DG-MK-release-manifest step (5): `images` from the docker-build report of this build,
    # `audit_deps` as {result, output_sha256} from the audit-deps report; stale evidence is null.
    repo = scratch_repo(scratch / "repo")
    head = git(repo, "rev-parse", "HEAD")
    reports, out = scratch / "reports", scratch / "release-manifest.json"
    images = {
        name: {"tag": f"erev-{name}:{head[:12]}", "digest": f"sha256:{name:0<64}"}
        for name in ("api", "worker", "web")
    }
    gate_report(
        reports, "docker-build", build_sha=head, extra={"images": images, "result": "built"}
    )
    audit = gate_report(reports, "audit-deps", build_sha=head, extra={"output_sha256": "d" * 64})
    result = _generate(repo, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = _read(out)
    assert manifest["images"] == images
    assert manifest["audit_deps"] == {"result": "PASS", "output_sha256": "d" * 64}
    report = _read(reports / "release-manifest" / "report.json")
    assert report["images_evidence"]["status"] == "complete"
    assert report["acceptance"] == "non-strict (not release acceptance)"
    assert report["embedded"] is False
    assert report["manifest_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert "non-strict (not release acceptance)" in result.stdout

    # A docker-build report of another build describes other images: null, never copied.
    gate_report(
        reports, "docker-build", build_sha="e" * 40, extra={"images": images, "result": "built"}
    )
    # An audit-deps report without its own digest is digested as a file; a failed run is FAIL.
    gate_report(reports, "audit-deps", build_sha=head, exit_code=1)
    result = _generate(repo, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = _read(out)
    assert manifest["images"] == {
        name: {"tag": None, "digest": None} for name in ("api", "worker", "web")
    }
    assert manifest["audit_deps"] == {
        "result": "FAIL",
        "output_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
    }
    evidence = _read(reports / "release-manifest" / "report.json")["images_evidence"]
    assert (evidence["status"], evidence["report_build_sha"]) == ("another-build", "e" * 40)


def _images(head: str, *names: str) -> dict[str, dict[str, str]]:
    return {
        name: {"tag": f"erev-{name}:{head[:12]}", "digest": f"sha256:{name:0<64}"}
        for name in (names or ("api", "worker", "web"))
    }


def test_image_evidence_boundary(scratch: Path) -> None:
    # Production hardening: a docker-build report of this build that is skipped, failed, dirty or
    # incomplete is never presented as complete image metadata; in STRICT mode it fails the run
    # (stage `images`); absent or foreign reports stay null and do not fail STRICT.
    script = load_script()
    repo = scratch_repo(scratch / "repo")
    corpus = scratch_corpus(repo)  # committed before head is read (REL-COV-1)
    head = git(repo, "rev-parse", "HEAD")
    reports, out = scratch / "reports", scratch / "release-manifest.json"
    all_gates_pass(reports, GATES, build_sha=head, corpus=corpus)
    nulls = {name: {"tag": None, "digest": None} for name in ("api", "worker", "web")}
    cases: dict[str, dict[str, Any]] = {
        "skipped": {"extra": {"result": "skipped-no-daemon"}},
        "failed": {"exit_code": 1, "extra": {"images": _images(head), "result": "FAIL"}},
        "dirty": {"worktree_dirty": True, "extra": {"images": _images(head), "result": "PASS"}},
        "incomplete": {"extra": {"images": _images(head, "api", "worker"), "result": "built"}},
    }
    for status, values in cases.items():
        gate_report(reports, "docker-build", build_sha=head, **values)
        images, evidence = script.image_evidence(reports, head)
        assert evidence["status"] == status, status
        if status == "incomplete":
            assert images["web"] == {"tag": None, "digest": None}
            assert images["api"] == _images(head)["api"] and evidence["missing"] == ["web"]
        else:
            assert images == nulls, status
        relaxed = _generate(repo, reports, out)
        assert relaxed.returncode == 0, relaxed.stdout + relaxed.stderr
        assert _read(out)["images"] != _images(head), status
        report = _read(reports / "release-manifest" / "report.json")
        assert report["images_evidence"]["status"] == status
        assert f"images {status}" in relaxed.stdout
        strict = _generate(repo, reports, out, "--strict")
        assert strict.returncode == 1, (status, strict.stdout + strict.stderr)
        assert strict.stdout.splitlines()[-1] == f"FAIL release-manifest: STRICT: images {status}"
        failures = _read(reports / "release-manifest" / "report.json")["failures"]
        assert failures == [{"stage": "images", "exit_code": 1, "status": status}]

    # Absent, foreign and complete evidence under STRICT.
    (reports / "docker-build" / "report.json").unlink()
    absent = _generate(repo, reports, out, "--strict")
    assert absent.returncode == 0, absent.stdout + absent.stderr
    assert _read(reports / "release-manifest" / "report.json")["images_evidence"] == {
        "status": "absent",
        "detail": "no docker-build report",
    }
    gate_report(reports, "docker-build", build_sha="e" * 40, exit_code=1, extra={"images": {}})
    foreign = _generate(repo, reports, out, "--strict")
    assert foreign.returncode == 0, foreign.stdout + foreign.stderr
    gate_report(
        reports, "docker-build", build_sha=head, extra={"images": _images(head), "result": "built"}
    )
    complete = _generate(repo, reports, out, "--strict")
    assert complete.returncode == 0, complete.stdout + complete.stderr
    assert _read(out)["images"] == _images(head)
    report = _read(reports / "release-manifest" / "report.json")
    assert report["images_evidence"]["status"] == "complete"
    assert report["acceptance"] == "strict"
    # A malformed report is not evidence either.
    (reports / "docker-build" / "report.json").write_text("{not json", encoding="utf-8")
    images, evidence = script.image_evidence(reports, head)
    assert images == nulls and evidence["status"] == "malformed"
    assert _generate(repo, reports, out, "--strict").returncode == 1


def test_embedded_manifest_carries_no_image_identities(scratch: Path) -> None:
    # The manifest the images carry is written before the build: whatever docker-build report
    # exists, its `images` are null (acyclic; the attestation binds the ids to this file's SHA-256).
    repo = scratch_repo(scratch / "repo")
    corpus = scratch_corpus(repo)  # committed before head is read (REL-COV-1)
    head = git(repo, "rev-parse", "HEAD")
    reports, out = scratch / "reports", scratch / "release-manifest.json"
    all_gates_pass(reports, GATES, build_sha=head, corpus=corpus)
    gate_report(
        reports, "docker-build", build_sha=head, extra={"images": _images(head), "result": "built"}
    )
    result = _generate(repo, reports, out, "--embedded", "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = _read(out)
    assert manifest["images"] == {
        name: {"tag": None, "digest": None} for name in ("api", "worker", "web")
    }
    assert tuple(manifest) == MANIFEST_KEYS, "the REL-01 shape is unchanged"
    report = _read(reports / "release-manifest" / "report.json")
    assert report["embedded"] is True
    declared = _generate(
        repo,
        reports,
        scratch / "embedded-declared.json",
        "--embedded",
        "--validation-level",
        "MAJOR",
    )
    assert declared.returncode == 0, declared.stdout + declared.stderr
    assert _read(scratch / "embedded-declared.json")["validation_level"] == "MAJOR"
    assert report["images_evidence"]["status"] == "embedded"
    assert "embedded" in result.stdout.splitlines()[0]
    # The same reports without --embedded copy the complete set (the external manifest).
    external = _generate(repo, reports, scratch / "external.json")
    assert external.returncode == 0, external.stdout + external.stderr
    assert _read(scratch / "external.json")["images"] == _images(head)


def test_rel_01_validation_level_is_data_from_the_environment(scratch: Path) -> None:
    # P1-VL-S2 (Codex packet 1041): the recipe passes VALIDATION_LEVEL as data through the
    # environment; the generator reads it byte-exactly before any write and validates it whole.
    repo = scratch_repo(scratch / "repo")
    head = git(repo, "rev-parse", "HEAD")
    reports = scratch / "reports"
    gate_report(reports, "ci", build_sha=head)
    for level in ("PATCH", "MINOR", "MAJOR"):
        out = scratch / f"env-{level}.json"
        result = _generate(repo, reports, out, env_values={"VALIDATION_LEVEL": level})
        assert result.returncode == 0, result.stdout + result.stderr
        assert _read(out)["validation_level"] == level
        assert "undeclared" not in result.stderr
        assert _read(reports / "release-manifest" / "report.json")["validation_level"] == level
    # Omission: unset (the default environment) and the empty string (Make's `?=` default and
    # `VALIDATION_LEVEL=` on the command line both yield it) — key absent, the undeclared line.
    for env_values in ({}, {"VALIDATION_LEVEL": ""}):
        out = scratch / "omitted.json"
        result = _generate(repo, reports, out, env_values=env_values)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "validation_level" not in _read(out)
        assert "validation_level undeclared" in result.stderr
    # Refused whole, before any write: lowercase, the multi-option value, Codex's two quote bytes
    # (shell quote removal would have made it MINOR), and whitespace around a literal.
    for raw in ("minor", "MINOR --validation-level MAJOR", 'MIN"OR"', " MINOR", "MINOR\n"):
        refused_reports = scratch / "refused"
        out = scratch / "refused.json"
        result = _generate(repo, refused_reports, out, env_values={"VALIDATION_LEVEL": raw})
        assert result.returncode == 2, (raw, result.stdout, result.stderr)
        assert "VALIDATION_LEVEL" in result.stderr and "PATCH, MINOR, MAJOR" in result.stderr, raw
        assert not out.exists() and not (refused_reports / "release-manifest").exists(), raw
    # P1-VL-S3: the Makefile's $(value) capture EREV_VALIDATION_LEVEL_RAW carries the authored
    # bytes; the generator reads it first. Make's expansion of the plain variable is named.
    for raw, plain in (("MIN$(P1_UNSET)OR", "MINOR"), ("MIN$$OR", "MIN$OR")):
        expanded_reports = scratch / "expanded"
        out = scratch / "expanded.json"
        result = _generate(
            repo,
            expanded_reports,
            out,
            env_values={"EREV_VALIDATION_LEVEL_RAW": raw, "VALIDATION_LEVEL": plain},
        )
        assert result.returncode == 2, (raw, result.stdout, result.stderr)
        assert "EREV_VALIDATION_LEVEL_RAW" in result.stderr and raw in result.stderr
        assert "expan" in result.stderr and plain in result.stderr, result.stderr
        assert not out.exists() and not (expanded_reports / "release-manifest").exists()
    for raw in ("MIN$(P1_UNSET)OR", 'MIN"OR"', "minor"):
        alone_reports = scratch / "raw-alone"
        result = _generate(
            repo,
            alone_reports,
            scratch / "raw-alone.json",
            env_values={"EREV_VALIDATION_LEVEL_RAW": raw},
        )
        assert result.returncode == 2, (raw, result.stdout, result.stderr)
        assert (
            "EREV_VALIDATION_LEVEL_RAW" in result.stderr and "PATCH, MINOR, MAJOR" in result.stderr
        )
        assert not (scratch / "raw-alone.json").exists()
        assert not (alone_reports / "release-manifest").exists()
    for raw in ("PATCH", "MINOR", "MAJOR"):
        out = scratch / f"raw-{raw}.json"
        both = _generate(
            repo,
            reports,
            out,
            env_values={"EREV_VALIDATION_LEVEL_RAW": raw, "VALIDATION_LEVEL": raw},
        )
        assert both.returncode == 0, both.stdout + both.stderr
        assert _read(out)["validation_level"] == raw
    for env_values in (
        {"EREV_VALIDATION_LEVEL_RAW": "", "VALIDATION_LEVEL": ""},
        {"EREV_VALIDATION_LEVEL_RAW": ""},
    ):
        out = scratch / "raw-omitted.json"
        result = _generate(repo, reports, out, env_values=env_values)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "validation_level" not in _read(out) and "undeclared" in result.stderr

    # The option stays for direct invocations; it must agree with an environment value.
    agree = _generate(
        repo,
        reports,
        scratch / "agree.json",
        "--validation-level",
        "MINOR",
        env_values={"VALIDATION_LEVEL": "MINOR"},
    )
    assert agree.returncode == 0, agree.stdout + agree.stderr
    assert _read(scratch / "agree.json")["validation_level"] == "MINOR"
    disagree = _generate(
        repo,
        scratch / "disagree-reports",
        scratch / "disagree.json",
        "--validation-level",
        "MINOR",
        env_values={"VALIDATION_LEVEL": "MAJOR"},
    )
    assert disagree.returncode == 2, disagree.stdout + disagree.stderr
    assert "disagree" in disagree.stderr and "--validation-level" in disagree.stderr
    assert "VALIDATION_LEVEL" in disagree.stderr
    assert not (scratch / "disagree.json").exists()
    assert not (scratch / "disagree-reports" / "release-manifest").exists()


def _corpus_keys() -> list[Any]:
    from support.answer_keys.loader import load_all

    return sorted(load_all(include_withdrawn=True), key=lambda item: item.key.id)


@pytest.mark.control("CTL-032")
def test_rel_cov_1_answer_keys_evidence_is_full_corpus_only(scratch: Path) -> None:
    """CTL-032, the manifest's half ("gate evidence") of the answer-keys gate: PASS
    only as the canonical full-scope run on the database platform, bound to its
    wrapper's run, whose keys are the corpus in the tree — ids and file hashes —
    with complete coverage. A filtered, forged, coverage-less, incomplete or
    tampered report is NOT_RUN by name, and a failure of the full corpus followed
    by a passing subset never becomes PASS. Not witnessed here: the rules every
    gate shares (``test_rel_02_result_rules``,
    ``test_gate_bind_1_only_bound_reports_pass``).
    """
    # REL-COV-1 (Codex FULL-KEY-GATE-SCOPE-R1): answer-keys is PASS only as the canonical full-scope
    # report whose membership equals the corpus in the tree (ids and file hashes) with complete
    # coverage; a filtered, coverage-less, incomplete or mismatched report is refused by name.
    head = git(ROOT, "rev-parse", "HEAD")
    loaded = _corpus_keys()
    reports, out = scratch / "reports", scratch / "manifest.json"
    full = answer_keys_report_body(loaded)

    def verdict(extra: dict[str, Any], *, exit_code: int = 0) -> tuple[str, str | None]:
        gate_report(reports, "answer-keys", build_sha=head, exit_code=exit_code, extra=extra)
        result = _generate(ROOT, reports, out)
        assert result.returncode == 0, result.stdout + result.stderr
        report = _read(reports / "release-manifest" / "report.json")
        return _read(out)["gate_results"]["answer-keys"]["result"], report["gate_reasons"].get(
            "answer-keys"
        )

    assert verdict(full) == ("PASS", None)
    # 1. A full-corpus FAIL followed by a passing subset on the same head never becomes PASS.
    failing = dict(full) | {"exit_code": 1}
    assert verdict(failing, exit_code=1)[0] == "FAIL"
    subset_keys = full["keys"][:5]
    subset = dict(full) | {
        "target": "answer-keys-filtered",
        "keys": subset_keys,
        "counts": dict(full["counts"]) | {"selected": 5, "passed": 5, "withdrawn": 0},
        "scope": {
            "kind": "filtered",
            "selection": {
                "families": [],
                "ids": [k["id"] for k in subset_keys],
                "requirements": [],
            },
        },
    }
    subset.pop("coverage")
    result, reason = verdict(subset)
    assert result == "NOT_RUN" and reason and "filtered" in reason, reason
    # 2. A filtered report forged under the canonical target and scope is refused by membership.
    forged = dict(full) | {"keys": subset_keys, "counts": dict(full["counts"]) | {"selected": 5}}
    result, reason = verdict(forged)
    assert result == "NOT_RUN" and reason and "membership" in reason, reason
    # 3. Filtered scope declared under the canonical target.
    scoped = dict(full) | {"scope": dict(subset["scope"])}
    result, reason = verdict(scoped)
    assert result == "NOT_RUN" and reason and "filtered" in reason, reason
    # 4. Coverage missing or incomplete.
    no_coverage = dict(full)
    no_coverage.pop("coverage")
    result, reason = verdict(no_coverage)
    assert result == "NOT_RUN" and reason and "coverage" in reason, reason
    gaps = dict(full) | {
        "coverage": {"counts": {"List A": {"covered": 2, "total": 3}}, "gaps": ["AK:x"]}
    }
    result, reason = verdict(gaps)
    assert result == "NOT_RUN" and reason and "coverage" in reason, reason
    # 5. A key whose hash is not the corpus file's, and an extra id, are refused by name.
    tampered_keys = [dict(k) for k in full["keys"]]
    tampered_keys[0]["sha256"] = "0" * 64
    result, reason = verdict(dict(full) | {"keys": tampered_keys})
    assert result == "NOT_RUN" and reason and "sha256" in reason, reason
    extra_keys = [*full["keys"], dict(full["keys"][0]) | {"id": "ZZZ-NOT-IN-CORPUS"}]
    result, reason = verdict(
        dict(full)
        | {"keys": extra_keys, "counts": dict(full["counts"]) | {"selected": len(extra_keys)}}
    )
    assert result == "NOT_RUN" and reason and "corpus" in reason, reason
    # 6. Under a root without a corpus the evidence cannot be bound and is refused, never PASS.
    repo = scratch_repo(scratch / "repo")
    scratch_head = git(repo, "rev-parse", "HEAD")
    gate_report(scratch / "r2", "answer-keys", build_sha=scratch_head, extra=full)
    result = _generate(repo, scratch / "r2", scratch / "m2.json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _read(scratch / "m2.json")["gate_results"]["answer-keys"]["result"] == "NOT_RUN"
    assert (
        "corpus"
        in _read(scratch / "r2" / "release-manifest" / "report.json")["gate_reasons"]["answer-keys"]
    )
    # 7. Codex 1510: only the canonical G4 run on the database platform, bound to its wrapper run.
    for patch, needle in (
        ({"scope": dict(full["scope"]) | {"mode": "unfiltered-implicit"}}, "canonical"),
        ({"scope": dict(full["scope"]) | {"platform": "in-memory"}}, "platform"),
        ({"run_id": "0" * 32}, "run_id"),
        ({"run_id": ""}, "run_id"),
    ):
        result, reason = verdict(dict(full) | patch)
        assert result == "NOT_RUN" and reason and needle in reason, (patch, reason)
    # 8. Codex 1517 (REL-COV-1-COVERAGE-R1): coverage must carry the loader's complete schema.
    sections = list(full["coverage"]["counts"])
    for coverage, needle in (
        ({"gaps": []}, "coverage"),
        ({"counts": {}, "gaps": []}, "coverage"),
        (
            {
                "counts": {
                    k: v for k, v in full["coverage"]["counts"].items() if k != "AK-FAM: slugs"
                },
                "gaps": [],
            },
            "AK-FAM: slugs",
        ),
        ({"counts": dict(full["coverage"]["counts"]) | {"List A": 3}, "gaps": []}, "List A"),
        (
            {
                "counts": dict(full["coverage"]["counts"]) | {"List B": {"covered": 2, "total": 3}},
                "gaps": [],
            },
            "List B",
        ),
        (
            {
                "counts": dict(full["coverage"]["counts"])
                | {"List C": {"covered": "3", "total": 3}},
                "gaps": [],
            },
            "List C",
        ),
        ({"counts": full["coverage"]["counts"], "gaps": "none"}, "gaps"),
        ("complete", "coverage"),
    ):
        result, reason = verdict(dict(full) | {"coverage": coverage})
        assert result == "NOT_RUN" and reason and needle in reason, (coverage, reason)
    assert len(sections) == 6
    # Strict mode names the refusal.
    gate_report(reports, "answer-keys", build_sha=head, extra=subset)
    strict = _generate(ROOT, reports, out, "--strict")
    assert strict.returncode == 1 and "answer-keys NOT_RUN" in strict.stdout


def test_generated_manifest_is_accepted_at_production_startup(scratch: Path) -> None:
    # REL-03 round trip without a database: the manifest the generator writes for this checkout
    # names the running engine version and schema head, so `release_facts` under production
    # returns its build and gate results instead of raising.
    out = scratch / "release-manifest.json"
    reports = scratch / "reports"
    head = git(ROOT, "rev-parse", "HEAD")
    gate_report(reports, "test-pg", build_sha=head)
    result = _generate(ROOT, reports, out)
    assert result.returncode == 0, result.stdout + result.stderr
    facts = release_facts(Environment.PRODUCTION, manifest_path=out)
    assert (facts.engine_version, facts.build_sha, facts.schema_revision) == (
        ENGINE_VERSION,
        head,
        code_head(),
    )
    assert facts.control_impact_tags == tuple(_read(out)["control_impact_tags"])
    digest = hashlib.sha256((reports / "test-pg" / "report.json").read_bytes()).hexdigest()
    assert facts.gate_results["test-pg"] == {"result": "PASS", "output_sha256": digest}
    assert facts.gate_results["ci"] == {"result": "NOT_RUN", "output_sha256": None}
    assert set(facts.gate_results) == set(release.GATE_KEYS), "e2e and perf are not stored"
    assert facts.validation_level == "PATCH", "undeclared → the T-PLT-38 default"
    declared_out = scratch / "declared-release-manifest.json"
    declared = _generate(ROOT, reports, declared_out, "--validation-level", "MINOR")
    assert declared.returncode == 0, declared.stdout + declared.stderr
    assert release_facts(Environment.PRODUCTION, manifest_path=declared_out).validation_level == (
        "MINOR"
    )

    # The same manifest for another engine version or schema head is refused (REL-03).
    manifest = _read(out)
    for changes in ({"engine_version": "999.0.0"}, {"schema_revision": "0000"}):
        out.write_text(json.dumps(manifest | changes), encoding="utf-8")
        with pytest.raises(ReleaseManifestError):
            release_facts(Environment.PRODUCTION, manifest_path=out)


def _production(settings: Settings) -> Settings:
    # A production process holds the smtp backend: since 05 SAR-40 rev 1.53 the fake one is
    # refused before the manifest is read, and this test is about the manifest.
    return production_settings(settings)


@pytest.mark.control("CTL-032")
def test_production_refuses_before_any_database_access(
    app_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CTL-032, the manifest's half where it prevents: a production api and a
    production worker without their release manifest do not start — the refusal
    comes before any database access and before the worker's first heartbeat;
    outside production the facts are derived. Not witnessed here: a manifest of
    another release (``tests/pg/test_engine_release.py``).
    """
    # REL-03: the api lifespan and the worker entry point evaluate the manifest before they open
    # a session. With no manifest and every database path trapped, production raises
    # ReleaseManifestError and the traps never fire.
    absent = tmp_path / "release-manifest.json"
    monkeypatch.setattr(release, "MANIFEST_PATH", absent)

    def trapped(*args: object, **kwargs: object) -> object:
        raise AssertionError("the database was reached before the manifest check")

    monkeypatch.setattr(release, "release_session", trapped)
    production = _production(app_settings)

    app = create_app(production)

    async def start() -> None:
        async with app.router.lifespan_context(app):
            pass  # pragma: no cover - startup raises first

    with pytest.raises(ReleaseManifestError, match="required in production"):
        asyncio.run(start())

    monkeypatch.setattr(worker_module, "get_settings", lambda: production)
    monkeypatch.setattr(worker_module, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(worker_module, "_run_worker", trapped)
    with pytest.raises(ReleaseManifestError, match="required in production"):
        worker_module.main(heartbeat_file=tmp_path / "worker.heartbeat")
    assert not (tmp_path / "worker.heartbeat").exists(), "no heartbeat before the release check"

    # Outside production the same processes derive their facts (dev behaviour unchanged).
    facts = release_facts(Environment.DEV, manifest_path=absent, build_sha=lambda: "dev")
    assert (facts.engine_version, facts.build_sha, facts.schema_revision) == (
        ENGINE_VERSION,
        "dev",
        code_head(),
    )
