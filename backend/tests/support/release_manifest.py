"""Helpers for the release-manifest tests (05 REL-01 to REL-04; DG-MK-release-manifest; SOP-2).

``scripts/release_manifest.py`` is loaded as a module through ``importlib`` (as ``test_compose``
loads ``secrets_check``), scratch git repositories are built under the caller's temporary directory
(inside ``.run``, never the system
temporary directory), and gate reports are written in the DG-MK-00g shape.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "release_manifest.py"
# The commit identity of the scratch repositories; nothing is signed and no global config is read.
GIT_IDENTITY = (
    "-c",
    "user.name=erev-tests",
    "-c",
    "user.email=erev-tests@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_manifest", SCRIPT)
    assert spec is not None and spec.loader is not None, SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *GIT_IDENTITY, *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


def scratch_repo(base: Path, *, files: dict[str, str] | None = None) -> Path:
    """A git repository at ``base`` with one commit of ``files`` (default: a README)."""
    base.mkdir(parents=True, exist_ok=True)
    git(base, "init", "-q", "-b", "main")
    commit(base, files or {"README.md": "scratch\n"}, "initial")
    return base


def commit(root: Path, files: dict[str, str], message: str) -> str:
    """Write ``files`` (relative paths) and commit them; returns the new HEAD."""
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        git(root, "add", "--", relative)
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def gate_report(
    reports: Path,
    gate: str,
    *,
    build_sha: str,
    exit_code: int = 0,
    worktree_dirty: bool = False,
    command: str | None = None,
    extra: dict[str, Any] | None = None,
    bound: bool = True,
) -> Path:
    """Write ``<reports>/<gate>/report.json`` in the DG-MK-00g shape and return its path.

    ``bound`` adds the GATE-BIND-1 ``source_binding`` of a clean immutable-context run for
    ``build_sha`` (mode ``immutable-context``, equal tree and content hashes), which
    ``release_manifest.gate_result`` requires before it classifies a report PASS.
    """
    report: dict[str, Any] = {
        "target": gate,
        "command": command or f"make {gate}",
        "build_sha": build_sha,
        "worktree_dirty": worktree_dirty,
        "started_at": "2026-09-19T10:00:00.000000Z",
        "finished_at": "2026-09-19T10:05:00.000000Z",
        "exit_code": exit_code,
        # Populated evidence (DG-MK-00g): the consumer classifies an unpopulated report NOT_RUN.
        "counts": {"backend": {"passed": 1, "failed": 1 if exit_code else 0, "skipped": 0}},
        "failures": [] if exit_code == 0 else [{"stage": "test", "exit_code": exit_code}],
    }
    if bound:
        report["source_binding"] = source_binding(build_sha)
    report.update(extra or {})
    if bound and "run_id" in report and report["run_id"] is None:
        report["run_id"] = report["source_binding"]["run_id"]  # bound to the run that produced it
    path = reports / gate / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


RUN_ID = "run-0123456789abcdef"


def source_binding(build_sha: str, **changes: Any) -> dict[str, Any]:
    """A GATE-BIND-1 binding of a clean immutable-context run for ``build_sha``."""
    tree = hashlib.sha1(f"tree:{build_sha}".encode()).hexdigest()
    content = hashlib.sha256(f"content:{build_sha}".encode()).hexdigest()
    binding: dict[str, Any] = {
        "mode": "immutable-context",
        "captured_sha": build_sha,
        "tree_sha": tree,
        "tree_sha_end": tree,
        "context_sha256_start": content,
        "context_sha256_end": content,
        "context_path": None,
        "context_kept": False,
        "worktree_head_after": build_sha,
        "worktree_dirty_after": False,
        # Run binding (REL-COV-1 / Codex 1510): the wrapper's run id and start, which the inner
        # report must match (run_id) and not precede (started_at).
        "run_id": RUN_ID,
        "run_started_at": "2026-09-19T10:00:00.000000Z",
    }
    binding.update(changes)
    return binding


def scratch_corpus(repo: Path, count: int = 2) -> list[Any]:
    """Commit the first ``count`` real answer-key files into ``repo`` (family directories kept) and
    return them loaded through the corpus loader with its root override — a small corpus a
    scratch repository's manifest can bind answer-keys evidence to (REL-COV-1)."""
    from support.answer_keys import loader

    sources = loader.discover()[:count]
    files = {
        f"docs/accounting/answer-keys/{src.parent.name}/{src.name}": src.read_text(encoding="utf-8")
        for src in sources
    }
    commit(repo, files, "scratch answer-key corpus")
    return sorted(
        loader.load_all(include_withdrawn=True, root=repo / "docs" / "accounting" / "answer-keys"),
        key=lambda item: item.key.id,
    )


def answer_keys_report_body(loaded: Sequence[Any]) -> dict[str, Any]:
    """The full-scope answer-keys report body the manifest accepts (REL-COV-1): every corpus key
    with its file hash, an empty selection, the corpus binding and complete coverage."""
    ordered = sorted(loaded, key=lambda item: item.key.id)
    keys = [
        {
            "id": item.key.id,
            "path": f"docs/accounting/answer-keys/{item.path.parent.name}/{item.path.name}",
            "sha256": item.sha256,
            "runner": item.key.runner,
            "result": "passed" if item.key.status == "active" else "withdrawn",
            "mismatches": [],
            "message": None,
            "notes": [],
            "review_status": item.key.review.status,
        }
        for item in ordered
    ]
    active = sum(1 for item in ordered if item.key.status == "active")
    digest = hashlib.sha256(
        "\n".join(f"{item.key.id}:{item.sha256}" for item in ordered).encode("utf-8")
    ).hexdigest()
    return {
        "counts": {
            "selected": len(keys),
            "passed": active,
            "failed": 0,
            "not_run": 0,
            "withdrawn": len(keys) - active,
            "not_approved": sum(1 for entry in keys if entry["review_status"] != "approved"),
        },
        "keys": keys,
        "scope": {
            "kind": "full",
            "mode": "canonical",
            "platform": "db",
            "cleared": [],
            "selection": {"families": [], "ids": [], "requirements": []},
        },
        "corpus": {
            "ids": [item.key.id for item in ordered],
            "sha256": digest,
            "active": active,
            "withdrawn": len(keys) - active,
        },
        "coverage": complete_coverage(),
        # The manifest requires equality with source_binding.run_id; gate_report() fills it.
        "run_id": None,
    }


COVERAGE_SECTIONS = ("List A", "List B", "List C", "AK: hints", "AK-FAM: slugs", "family codes")


def complete_coverage(total: int = 3) -> dict[str, Any]:
    """The loader's complete coverage schema: six named sections, each covered == total, no gaps."""
    return {
        "counts": {name: {"covered": total, "total": total} for name in COVERAGE_SECTIONS},
        "gaps": [],
    }


def all_gates_pass(
    reports: Path, gates: Iterable[str], *, build_sha: str, corpus: Sequence[Any] | None = None
) -> None:
    for gate in gates:
        if gate == "answer-keys" and corpus is not None:
            gate_report(reports, gate, build_sha=build_sha, extra=answer_keys_report_body(corpus))
        else:
            gate_report(reports, gate, build_sha=build_sha)
