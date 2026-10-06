"""Answer-key gate driver and report (docs/dev-guide.md §4.4 DG-MK-answer-keys; §9.5.8 DG-AK-42,
DG-AK-43; BUILD_SPEC EKC-12).

``make answer-keys`` runs ``python -m support.answer_keys.report`` from the repository root with
``PYTHONPATH=backend/tests``. The driver (1) loads and validates every key file, so an invalid file
fails the run whatever the filter (DG-AK-30 to DG-AK-32); (2) selects keys through ``FAMILY``,
``ID`` and ``REQ`` and runs ``backend/tests/answer_keys`` in process with ``-m answer_key``, where
each test hands its outcome to :func:`record` through ``config.stash``; (3) without filters, runs
the DG-AK-33 coverage check; (4) writes ``.run/reports/answer-keys/report.json`` with the DG-MK-00g
fields, one DG-AK-43 entry per selected key and the count of selected keys whose review status is
not ``approved``, and prints ``OK answer-keys`` or ``FAIL answer-keys: <reason>`` (DG-MK-00a).
Withdrawn keys are validated and listed, never run, and a selection holding no active key fails
the run before pytest starts (DG-AK-13; D-79).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest
from support.answer_keys.loader import (
    COVERAGE_HEADING,
    REPO_ROOT,
    LoadedKey,
    coverage,
    load_all,
    select_keys,
    selection_from_env,
    selection_is_filtered,
)
from support.answer_keys.runners import CheckpointMismatchError, Mismatch

__all__ = ["OUTCOMES", "KeyOutcome", "build_report", "key_entry", "main", "outcome_of", "record"]

TARGET: Final = "answer-keys"
# A run with any of FAMILY / ID / REQ is a distinct, named diagnostic (DG-AK-42 rev 1.43;
# REL-COV-1): its own target name and report directory, never the canonical answer-keys report.
FILTERED_TARGET: Final = "answer-keys-filtered"
TESTS_DIR: Final = REPO_ROOT / "backend" / "tests" / "answer_keys"
REPORTS_DIR: Final = REPO_ROOT / ".run" / "reports"


@dataclass(frozen=True, slots=True)
class KeyOutcome:
    """How one selected key ended: ``passed`` or ``failed``, with its mismatches or message, and the
    run note of the inputs the runner derived from the key (D-85)."""

    result: str
    mismatches: tuple[Mismatch, ...] = ()
    message: str | None = None
    notes: tuple[str, ...] = ()


OUTCOMES: Final = pytest.StashKey[dict[str, KeyOutcome]]()


def record(config: pytest.Config, loaded: LoadedKey, outcome: KeyOutcome) -> None:
    """Keep a key's outcome for the report; a session the driver did not start keeps none."""
    outcomes = config.stash.get(OUTCOMES, None)
    if outcomes is not None:
        outcomes[loaded.key.id] = outcome


def outcome_of(error: Exception) -> KeyOutcome:
    """The failed outcome of an exception raised while running or asserting a key."""
    if isinstance(error, CheckpointMismatchError):
        count = len(error.mismatches)
        noun = "mismatch" if count == 1 else "mismatches"
        return KeyOutcome("failed", error.mismatches, f"{count} {noun}")
    return KeyOutcome("failed", message=f"{type(error).__name__}: {error}")


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def key_entry(loaded: LoadedKey, outcome: KeyOutcome | None) -> dict[str, Any]:
    """DG-AK-43: id, path, sha256, runner, result, mismatches and review status of one key, and its
    run notes (D-85)."""
    key = loaded.key
    if outcome is None:
        outcome = KeyOutcome("withdrawn" if key.status == "withdrawn" else "not_run")
    return {
        "id": key.id,
        "path": _relative(loaded.path),
        "sha256": loaded.sha256,
        "runner": key.runner,
        "result": outcome.result,
        "mismatches": [mismatch.to_json() for mismatch in outcome.mismatches],
        "message": outcome.message,
        "notes": list(outcome.notes),
        "review_status": key.review.status,
    }


def build_report(
    *,
    command: str,
    selected: Sequence[LoadedKey],
    outcomes: Mapping[str, KeyOutcome],
    started_at: str,
    finished_at: str,
    exit_code: int,
    failures: Sequence[Mapping[str, Any]],
    build_sha: str,
    worktree_dirty: bool,
    coverage_report: Mapping[str, Any] | None = None,
    selection: Mapping[str, Iterable[str]] | None = None,
    corpus: Sequence[LoadedKey] | None = None,
    scope: Mapping[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """The report document: DG-MK-00g fields, the DG-AK-43 key entries and their counts, the
    explicit ``scope`` (full or filtered, with the selection) and — when the corpus loaded — the
    ``corpus`` binding (every key id, the SHA-256 over the sorted ``id:sha256`` lines, the active
    and withdrawn counts) a consumer compares with the tree (REL-COV-1)."""
    keys = [key_entry(item, outcomes.get(item.key.id)) for item in selected]
    results = [entry["result"] for entry in keys]
    if scope is None:
        chosen = (
            {name: sorted(selection.get(name, ())) for name in ("families", "ids", "requirements")}
            if selection
            else {"families": [], "ids": [], "requirements": []}
        )
        filtered = any(chosen.values())
        scope = {
            "kind": "filtered" if filtered else "full",
            "mode": "filtered" if filtered else "unfiltered-implicit",
            "platform": IN_MEMORY_PLATFORM,
            "cleared": [],
            "selection": chosen,
        }
    filtered = scope.get("kind") == "filtered"
    report: dict[str, Any] = {
        "target": FILTERED_TARGET if filtered else TARGET,
        "command": command,
        "build_sha": build_sha,
        "worktree_dirty": worktree_dirty,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "counts": {
            "selected": len(keys),
            "passed": results.count("passed"),
            "failed": results.count("failed"),
            "not_run": results.count("not_run"),
            "withdrawn": results.count("withdrawn"),
            "not_approved": sum(1 for entry in keys if entry["review_status"] != "approved"),
        },
        "failures": [dict(failure) for failure in failures],
        "keys": keys,
        "scope": dict(scope),
        # The wrapper's EREV_GATE_RUN_ID; the manifest binds the report to the run that wrote it.
        "run_id": run_id,
    }
    if corpus is not None:
        report["corpus"] = corpus_binding(corpus)
    if coverage_report is not None:
        report["coverage"] = dict(coverage_report)
    return report


SCOPE_ENV: Final = "EREV_AK_SCOPE"
CLEARED_ENV: Final = "EREV_AK_CLEARED"
PLATFORM_ENV: Final = "EREV_AK_PLATFORM"
RUN_ID_ENV: Final = "EREV_GATE_RUN_ID"
IN_MEMORY_PLATFORM: Final = "in-memory"


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    """The selection to apply and the ``scope`` the report records (DG-MK-answer-keys (5))."""

    selection: dict[str, tuple[str, ...]]
    scope: dict[str, Any]


def scope_from_env(environ: Mapping[str, str] | None = None) -> ScopeResolution:
    """Resolve the run's scope from the environment (Codex 1510). ``EREV_AK_SCOPE=full`` is the
    canonical G4 release run: the recipe has cleared FAMILY / ID / REQ explicitly and names what
    it cleared in ``EREV_AK_CLEARED``; a canonical run whose selection variables are still set,
    or any other ``EREV_AK_SCOPE`` value, is refused. Otherwise a run with a selection is
    ``filtered`` and a run without one is ``unfiltered-implicit``: named modes that never become
    release evidence."""
    source = os.environ if environ is None else environ
    mode_value = source.get(SCOPE_ENV, "")
    if mode_value not in ("", "full"):
        raise ValueError(f"{SCOPE_ENV} must be 'full' (got {mode_value!r}); DG-MK-answer-keys (5)")
    selection = selection_from_env(source)
    filtered = selection_is_filtered(selection)
    platform = source.get(PLATFORM_ENV) or IN_MEMORY_PLATFORM
    if mode_value == "full":
        if filtered:
            names = (("FAMILY", "families"), ("ID", "ids"), ("REQ", "requirements"))
            given = ", ".join(
                f"{variable}={','.join(selection[key])}"
                for variable, key in names
                if selection[key]
            )
            raise ValueError(
                "AK_SCOPE=full requires the selection variables cleared (FAMILY= ID= REQ=); "
                f"found {given}"
            )
        mode = "canonical"
        cleared = source.get(CLEARED_ENV, "").split()
    else:
        mode = "filtered" if filtered else "unfiltered-implicit"
        cleared = []
    scope = {
        "kind": "filtered" if filtered else "full",
        "mode": mode,
        "platform": platform,
        "cleared": cleared,
        "selection": {
            "families": sorted(selection["families"]),
            "ids": sorted(selection["ids"]),
            "requirements": sorted(selection["requirements"]),
        },
    }
    return ScopeResolution(selection=selection, scope=scope)


def corpus_binding(corpus: Sequence[LoadedKey]) -> dict[str, Any]:
    """The complete corpus as the writer saw it: sorted ids, the digest over ``id:sha256`` lines
    in id order, and the active / withdrawn counts — never a hard-coded count."""
    ordered = sorted(corpus, key=lambda item: item.key.id)
    lines = "\n".join(f"{item.key.id}:{item.sha256}" for item in ordered)
    return {
        "ids": [item.key.id for item in ordered],
        "sha256": hashlib.sha256(lines.encode("utf-8")).hexdigest(),
        "active": sum(1 for item in ordered if item.key.status == "active"),
        "withdrawn": sum(1 for item in ordered if item.key.status != "active"),
    }


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git(*args: str) -> str | None:
    """Git output for the DG-MK-00g fields, read as scripts/gate_report.py reads them."""
    try:
        completed = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


class _OutcomeCollector:
    """Plugin that gives the in-process session the mapping :func:`record` fills."""

    def __init__(self, outcomes: dict[str, KeyOutcome]) -> None:
        self.outcomes = outcomes

    def pytest_configure(self, config: pytest.Config) -> None:
        config.stash[OUTCOMES] = self.outcomes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make answer-keys (DG-MK-answer-keys)")
    parser.add_argument("--command", required=True)
    parser.add_argument("--basetemp", type=Path, default=REPO_ROOT / ".run" / "pytest-answer-keys")
    # Tests write their reports elsewhere so they never replace a real gate report.
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)
    started_at = _utc_now()
    build_sha = (_git("rev-parse", "HEAD") or "nogit").strip()
    worktree_dirty = bool((_git("status", "--porcelain") or "").strip())
    selected: list[LoadedKey] = []
    scope: dict[str, Any] | None = None
    selection: dict[str, tuple[str, ...]] = {"families": (), "ids": (), "requirements": ()}
    outcomes: dict[str, KeyOutcome] = {}
    failures: list[dict[str, Any]] = []
    reasons: list[str] = []
    coverage_json: dict[str, Any] | None = None
    every: list[LoadedKey] | None = None

    try:
        resolution = scope_from_env()
        selection, scope = resolution.selection, resolution.scope
        every = load_all(include_withdrawn=True)
        selected = select_keys(every, include_withdrawn=True, **selection)
    except ExceptionGroup as group:
        messages = [str(error) for error in group.exceptions]
        _say("\n".join(messages))
        failures.append({"stage": "validate", "exit_code": 1, "errors": messages})
        reasons.append(f"{len(messages)} invalid answer-key files (DG-AK-32)")
    except ValueError as error:
        stage = "scope" if scope is None else "select"
        failures.append({"stage": stage, "exit_code": 1, "message": str(error)})
        reasons.append(str(error))
    else:
        active = [item for item in selected if item.key.status == "active"]
        if active:
            pytest_exit = int(
                pytest.main(
                    [str(TESTS_DIR), "-m", "answer_key", f"--basetemp={args.basetemp}"],
                    plugins=[_OutcomeCollector(outcomes)],
                )
            )
            failed = [
                item.key.id
                for item in active
                if item.key.id not in outcomes or outcomes[item.key.id].result != "passed"
            ]
            if pytest_exit != 0 or failed:
                failures.append({"stage": "keys", "exit_code": pytest_exit or 1, "keys": failed})
                reasons.append(
                    f"{len(failed)} of {len(active)} selected answer keys failed"
                    if failed
                    else f"pytest exited {pytest_exit}"
                )
        else:
            message = "the selection holds no active answer key (DG-AK-13)"
            failures.append({"stage": "select", "exit_code": 1, "message": message})
            reasons.append(message)
        if not selection_is_filtered(selection):
            gaps = coverage(every)
            _say(gaps.render())
            coverage_json = {
                "counts": {
                    name: {"covered": count.covered, "total": count.total}
                    for name, count in gaps.counts.items()
                },
                "gaps": [gap.message for gap in gaps.gaps],
            }
            if not gaps.ok:
                failures.append({"stage": "coverage", "exit_code": 1, "gaps": len(gaps.gaps)})
                reasons.append(f"{len(gaps.gaps)} corpus gaps ({COVERAGE_HEADING})")

    exit_code = int(failures[0]["exit_code"]) if failures else 0
    document = build_report(
        command=args.command,
        selected=selected,
        outcomes=outcomes,
        started_at=started_at,
        finished_at=_utc_now(),
        exit_code=exit_code,
        failures=failures,
        build_sha=build_sha,
        worktree_dirty=worktree_dirty,
        coverage_report=coverage_json,
        selection=selection,
        corpus=every,
        scope=scope,
        run_id=os.environ.get(RUN_ID_ENV),
    )
    target = str(document["target"])
    out_dir = args.reports_dir / target  # a filtered run never touches the canonical directory
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (out_dir / "report.json").write_text(text, encoding="utf-8")
    counts = document["counts"]
    _say(
        f"{target} counts: {counts['selected']} selected; {counts['passed']} passed, "
        f"{counts['failed']} failed, {counts['not_run']} not run, {counts['withdrawn']} withdrawn; "
        f"{counts['not_approved']} not approved"
    )
    _say(f"OK {target}" if exit_code == 0 else f"FAIL {target}: {reasons[0]}")
    return exit_code


if __name__ == "__main__":
    # Run the copy that test modules import, so record() and the collector share OUTCOMES.
    from support.answer_keys import report as _report

    sys.exit(_report.main())
