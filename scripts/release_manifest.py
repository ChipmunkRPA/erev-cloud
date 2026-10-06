#!/usr/bin/env python3
"""Write release-manifest.json (docs/05-ARCHITECTURE.md §7.8 REL-01, REL-02, REL-04; dev-guide
§4.4 DG-MK-release-manifest, §4.1 DG-MK-00g; 04 T-PLT-38; BUILD_SPEC SOP-2).

usage: release_manifest.py [--root DIR] [--reports-dir DIR] [--out FILE] [--controls FILE]
                           [--command TEXT] [--strict] [--embedded]
                           [--validation-level {PATCH,MINOR,MAJOR}]
  (or VALIDATION_LEVEL in the environment, read whole before any write)

Offline; never runs a gate. (1) engine_version (erev_engine.ENGINE_VERSION), build_sha and
worktree_dirty (DG-MK-00g), schema_revision (the single Alembic head of the code) and created_at;
(2) gate_results for ci, parity, answer-keys, properties, test-pg, controls-report, e2e and perf
from .run/reports/<gate>/report.json, each {result, command, output_sha256, finished_at} with result
decided in this order: NOT_RUN when the report is absent or names another build_sha, FAIL when its
exit_code is not 0, NOT_RUN when it was produced on a dirty worktree, NOT_RUN when it lacks a
source_binding of mode immutable-context with equal hashes (GATE-BIND-1), else PASS;
output_sha256 is
the SHA-256 of the report file; (3) control_impact_tags: the sorted CTL ids whose impact_paths
globs in controls.yaml match a path of `git diff --name-only <base>..HEAD`, <base> being the latest
v* tag or the empty tree; (4) dependency_lock_sha256 of backend/uv.lock and
frontend/package-lock.json (null when absent); (5) images from .run/reports/docker-build/report.json
and audit_deps from .run/reports/audit-deps/report.json, null when absent or from another build;
(6) write the manifest (keys sorted, 2-space indent, trailing newline) and
.run/reports/release-manifest/report.json.

Evidence boundary (production hardening): image identities are copied only from a docker-build
report of this build that finished (exit_code 0), on a clean worktree, with every image identified;
a skipped, failed, dirty or incomplete report is dispositioned in the target's report
(images_evidence) and never presented as complete image metadata. --embedded writes the pre-build
manifest that the api and worker images carry: it never holds image identities (acyclic; the
docker-build attestation binds the manifest's SHA-256 to the image ids afterwards).

Exit 0 after writing; --strict (or the make variable STRICT=1) exits 1 unless every gate is PASS,
the worktree is clean and no unusable image evidence is present. A non-strict manifest is labelled
"non-strict (not release acceptance)" in the report and on stdout. The api and worker read the
manifest at startup (erev_api.controls.release).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
TARGET: Final = "release-manifest"
MANIFEST_NAME: Final = "release-manifest.json"
GATE_KEYS: Final = (
    "ci",
    "parity",
    "answer-keys",
    "properties",
    "test-pg",
    "controls-report",
    "e2e",
    "perf",
)
IMAGE_NAMES: Final = ("api", "worker", "web")
LOCK_FILES: Final = {"uv_lock": "backend/uv.lock", "package_lock": "frontend/package-lock.json"}
# The SHA-1 of git's empty tree: the diff base when no v* tag exists (05 REL-04).
EMPTY_TREE: Final = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
NOGIT: Final = "nogit"
PASS: Final = "PASS"
FAIL: Final = "FAIL"
NOT_RUN: Final = "NOT_RUN"
_TAG_PATTERN: Final = "v*"
# Dispositions of the docker-build report (images_evidence.status).
IMAGES_COMPLETE: Final = "complete"
IMAGES_EMBEDDED: Final = "embedded"
# Present evidence of this build that cannot be trusted as a complete image set; STRICT refuses it.
IMAGES_UNUSABLE: Final = frozenset({"malformed", "skipped", "failed", "dirty", "incomplete"})
ACCEPTANCE_STRICT: Final = "strict"
ACCEPTANCE_NON_STRICT: Final = "non-strict (not release acceptance)"


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- git (read-only: rev-parse, status, describe, diff) --------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_sha(root: Path) -> str:
    """``git rev-parse HEAD``, or ``"nogit"`` outside a repository (DG-MK-00g)."""
    completed = _git(root, "rev-parse", "HEAD")
    if completed is None or completed.returncode != 0:
        return NOGIT
    sha = completed.stdout.strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else NOGIT


def worktree_dirty(root: Path) -> bool:
    completed = _git(root, "status", "--porcelain")
    if completed is None or completed.returncode != 0:
        return False
    return bool(completed.stdout.strip())


def impact_base(root: Path) -> str | None:
    """The latest ``v*`` tag, else the empty tree inside a repository, else None (REL-04)."""
    if build_sha(root) == NOGIT:
        return None
    completed = _git(root, "describe", "--tags", "--abbrev=0", "--match", _TAG_PATTERN)
    if completed is not None and completed.returncode == 0 and completed.stdout.strip():
        return completed.stdout.strip()
    return EMPTY_TREE


def changed_paths(root: Path, base: str) -> list[str]:
    """``git diff --name-only <base>..HEAD`` as repository-relative POSIX paths."""
    completed = _git(root, "diff", "--name-only", f"{base}..HEAD")
    if completed is None or completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


# --- gate evidence (REL-02) ----------------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    result: str
    command: str | None
    output_sha256: str | None
    finished_at: str | None
    # Why a NOT_RUN was refused by name (REL-COV-1); recorded in the report, not the manifest.
    reason: str | None = None

    def as_json(self) -> dict[str, str | None]:
        return {
            "result": self.result,
            "command": self.command,
            "output_sha256": self.output_sha256,
            "finished_at": self.finished_at,
        }


def _read_report(path: Path) -> dict[str, Any] | None:
    """The report as a JSON object, or None when absent, unreadable or not an object."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_bytes())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _exit_code(report: Mapping[str, Any]) -> int | None:
    value = report.get("exit_code")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


EvidenceCheck = Callable[[Mapping[str, Any]], str | None]


def gate_result(path: Path, build: str, check: EvidenceCheck | None = None) -> GateResult:
    """REL-02 / DG-MK-release-manifest step (2): the verdict a report file supports. ``check`` is
    a gate-specific evidence rule applied last (REL-COV-1 for answer-keys): it returns the reason a
    successful, bound, populated report is still refused — recorded by name, never PASS."""
    if not path.is_file():
        return GateResult(NOT_RUN, None, None, None)
    digest = sha256_of(path)
    report = _read_report(path)
    if report is None:
        return GateResult(NOT_RUN, None, digest, None)
    command, finished_at = _text(report.get("command")), _text(report.get("finished_at"))
    reason: str | None = None
    if report.get("build_sha") != build:
        result = NOT_RUN
    else:
        exit_code = _exit_code(report)
        if exit_code is None:
            result = NOT_RUN  # a report without an exit code proves neither outcome
        elif exit_code != 0:
            result = FAIL
        elif report.get("worktree_dirty") is not False:
            result = NOT_RUN  # produced on a dirty worktree, or the DG-MK-00g field is missing
        elif not source_bound(report):
            result = NOT_RUN  # GATE-BIND-1: no proof the stages executed this build's source
        elif not has_population(report.get("counts")):
            result = NOT_RUN  # DG-MK-00g: no evidence population behind the exit code
        elif (stale := stale_run(report)) is not None:
            result, reason = NOT_RUN, stale  # bound to a run it did not come from (Codex 1510)
        else:
            reason = check(report) if check is not None else None
            result = NOT_RUN if reason else PASS
    return GateResult(result, command, digest, finished_at, reason)


# --- answer-keys: full-corpus evidence only (REL-COV-1; DG-MK-release-manifest step 2, rev 1.43) --

ANSWER_KEYS: Final = "answer-keys"
CORPUS_DIR: Final = Path("docs") / "accounting" / "answer-keys"


def load_corpus(root: Path) -> dict[str, tuple[str, str]] | str:
    """``{id: (sha256, status)}`` of every key under ``<root>/docs/accounting/answer-keys/``,
    read through the same loader the writer uses (``backend/tests/support``), or the reason it
    cannot be read. Never a hard-coded count."""
    corpus_root = root / CORPUS_DIR
    if not corpus_root.is_dir():
        return f"corpus not readable: {CORPUS_DIR.as_posix()} is not a directory under the root"
    # The checkout's own loader when it has one (production: --root is this checkout); the
    # generator's loader otherwise (a scratch --root in tests carries key files only).
    tests_dir = root / "backend" / "tests"
    if not (tests_dir / "support" / "answer_keys" / "loader.py").is_file():
        tests_dir = ROOT / "backend" / "tests"
    if not (tests_dir / "support" / "answer_keys" / "loader.py").is_file():
        return "corpus not readable: backend/tests/support/answer_keys/loader.py is absent"
    inserted = False
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
        inserted = True
    try:
        from support.answer_keys.loader import load_all

        loaded = load_all(include_withdrawn=True, root=corpus_root)
    except Exception as error:  # noqa: BLE001 - every loader failure is one named refusal
        return f"corpus not readable: {type(error).__name__}: {str(error)[:160]}"
    finally:
        if inserted:
            sys.path.remove(str(tests_dir))
    return {item.key.id: (item.sha256, item.key.status) for item in loaded}


def _names(values: Iterable[str], limit: int = 3) -> str:
    listed = sorted(values)
    shown = ", ".join(listed[:limit])
    return shown + (f" and {len(listed) - limit} more" if len(listed) > limit else "")


def answer_keys_evidence(
    report: Mapping[str, Any], corpus: Callable[[], dict[str, tuple[str, str]] | str]
) -> str | None:
    """Why a successful answer-keys report is not full-corpus evidence (None when it is): the
    canonical target, a full unfiltered scope, complete coverage, and a membership equal to the
    corpus in the tree — every id once, with its file hash, nothing extra."""
    target = report.get("target")
    if target != ANSWER_KEYS:
        return f"filtered diagnostic report (target {target!r}) is not full-corpus evidence"
    scope = report.get("scope")
    if not isinstance(scope, dict):
        return "scope missing: a report without scope (before rev 1.43) is not full-corpus evidence"
    selection = scope.get("selection") if isinstance(scope.get("selection"), dict) else {}
    chosen = {name: values for name, values in selection.items() if values}
    if scope.get("kind") != "full" or chosen:
        return "filtered scope refused: " + (
            ", ".join(f"{name}={_names(values)}" for name, values in sorted(chosen.items()))
            or f"kind {scope.get('kind')!r}"
        )
    mode = scope.get("mode")
    if mode != "canonical":
        return (
            f"not the canonical G4 run: scope.mode {mode!r} "
            "(the release run is `make answer-keys AK_SCOPE=full`)"
        )
    platform = scope.get("platform")
    if platform != "db":
        return f"platform {platform!r} is not the database platform (EREV_AK_PLATFORM=db)"
    coverage_problem = coverage_schema_problem(report.get("coverage"))
    if coverage_problem:
        return coverage_problem
    keys = report.get("keys")
    if not isinstance(keys, list) or not keys:
        return "membership missing: no key entries"
    ids = [entry.get("id") for entry in keys if isinstance(entry, dict)]
    if len(set(ids)) != len(ids):
        return "membership refused: repeated key ids"
    expected = corpus()
    if isinstance(expected, str):
        return expected
    present, wanted = set(ids), set(expected)
    if present != wanted:
        missing, extra = wanted - present, present - wanted
        parts = [f"{len(present & wanted)} of {len(wanted)} corpus keys present"]
        if missing:
            parts.append(f"missing {_names(missing)}")
        if extra:
            parts.append(f"not in the corpus: {_names(extra)}")
        return "membership incomplete: " + "; ".join(parts)
    for entry in keys:
        if isinstance(entry, dict) and entry.get("sha256") != expected[entry["id"]][0]:
            return f"key {entry['id']} sha256 differs from the corpus file"
    selected = (
        report.get("counts", {}).get("selected") if isinstance(report.get("counts"), dict) else None
    )
    if selected != len(keys):
        return f"counts.selected {selected!r} differs from the {len(keys)} key entries"
    binding = report.get("corpus")
    if isinstance(binding, dict):
        lines = "\n".join(f"{key}:{expected[key][0]}" for key in sorted(expected))
        digest = hashlib.sha256(lines.encode("utf-8")).hexdigest()
        if binding.get("sha256") != digest:
            return "corpus digest differs from the tree"
    source = report.get("source_binding") if isinstance(report.get("source_binding"), dict) else {}
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not run_id or run_id != source.get("run_id"):
        return (
            f"run_id {run_id!r} does not match the wrapper run {source.get('run_id')!r}: "
            "the report is not bound to the run that produced it"
        )
    return None


COVERAGE_SECTIONS: Final = (
    "List A",
    "List B",
    "List C",
    "AK: hints",
    "AK-FAM: slugs",
    "family codes",
)


def coverage_schema_problem(coverage: Any) -> str | None:
    """REL-COV-1-COVERAGE-R1 (Codex 1517): the loader's complete coverage schema — the six named
    sections, each an object with integer ``covered`` and ``total`` and ``covered == total``, and
    ``gaps`` an empty list. Absent, empty, partial or malformed coverage is refused by name; a
    malformed entry is a named refusal, never a crash."""
    if not isinstance(coverage, dict):
        return "coverage missing: an unfiltered run records the corpus coverage (DG-AK-33)"
    gaps = coverage.get("gaps")
    if not isinstance(gaps, list):
        return "coverage schema: gaps is not a list"
    if gaps:
        return f"coverage incomplete: {len(gaps)} gaps"
    counts = coverage.get("counts")
    if not isinstance(counts, dict) or not counts:
        return "coverage schema: counts is absent or empty (six sections expected)"
    missing = [name for name in COVERAGE_SECTIONS if name not in counts]
    if missing:
        return "coverage schema: section " + ", ".join(repr(name) for name in missing) + " missing"
    unexpected = sorted(set(counts) - set(COVERAGE_SECTIONS))
    if unexpected:
        return "coverage schema: unexpected section " + ", ".join(repr(n) for n in unexpected)
    for name in COVERAGE_SECTIONS:
        entry = counts[name]
        if (
            not isinstance(entry, dict)
            or not _figure(entry.get("covered"))
            or not _figure(entry.get("total"))
        ):
            return f"coverage schema: {name} is not an object with integer covered and total"
        if entry["covered"] != entry["total"]:
            return f"coverage incomplete: {name} {entry['covered']}/{entry['total']}"
    return None


SOURCE_BINDING_MODE: Final = "immutable-context"


RFC3339: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})")


def _instant(value: Any) -> dt.datetime | None:
    """An RFC 3339 date-time with an offset, as ``scripts/gate_report.py`` reads them; None for
    anything else (absent, non-string, week or ordinal dates, no offset)."""
    if not isinstance(value, str) or RFC3339.fullmatch(value) is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def stale_run(report: Mapping[str, Any]) -> str | None:
    """The run binding's chronology (REL-COV-RUN-TIME-R1, Codex 1546): the report's ``started_at``
    and its wrapper run's ``run_started_at`` must both be RFC 3339 instants with an offset — an
    absent, non-string or invalid timestamp is refused by name, never skipped — and are compared
    as parsed instants, so an offset cannot make an older report look newer; a report that started
    before its run was not written by that run (an archived or previous file surviving a
    refusal)."""
    binding = report.get("source_binding")
    if not isinstance(binding, dict):
        return "run binding missing: no source_binding object"
    began_raw, started_raw = binding.get("run_started_at"), report.get("started_at")
    began = _instant(began_raw)
    if began is None:
        return (
            f"run binding: source_binding.run_started_at {began_raw!r} is not an RFC 3339 "
            "instant with an offset"
        )
    started = _instant(started_raw)
    if started is None:
        return f"run binding: started_at {started_raw!r} is not an RFC 3339 instant with an offset"
    if started < began:
        return (
            f"stale report: started_at {started_raw} precedes its wrapper run's start {began_raw}"
        )
    return None


def _figure(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def has_population(counts: object) -> bool:
    """DG-MK-00g evidence population (the same rule as ``scripts/gate_report.py``): ``counts`` is
    an object with at least one figure at the top level or one level down, or a non-empty
    ``stages`` map whose stages all passed. ``{"stages": {}}`` or ``{}`` proves nothing."""
    if not isinstance(counts, dict):
        return False
    for key, value in counts.items():
        if key == "stages":
            if isinstance(value, dict) and value and all(v == "pass" for v in value.values()):
                return True
            continue
        if _figure(value):
            return True
        if isinstance(value, dict) and any(_figure(v) for v in value.values()):
            return True
    return False


def source_bound(report: Mapping[str, Any]) -> bool:
    """GATE-BIND-1: the report carries ``source_binding`` from ``scripts/gate_report.py`` with mode
    ``immutable-context``, the captured sha equal to ``build_sha``, and equal tree and content
    hashes before and after the run. Anything else cannot become PASS."""
    binding = report.get("source_binding")
    if not isinstance(binding, dict) or binding.get("mode") != SOURCE_BINDING_MODE:
        return False
    if binding.get("captured_sha") != report.get("build_sha"):
        return False
    tree, tree_end = binding.get("tree_sha"), binding.get("tree_sha_end")
    start, end = binding.get("context_sha256_start"), binding.get("context_sha256_end")
    return (
        isinstance(tree, str)
        and bool(tree)
        and tree == tree_end
        and isinstance(start, str)
        and bool(start)
        and start == end
    )


# --- control impact tags (REL-04) ------------------------------------------------------------


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """``**`` spans directories, ``*`` and ``?`` stay within one segment; whole-path matches."""
    regex = ""
    index, length = 0, len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**", index):
                after = index + 2
                if after < length and pattern[after] == "/":
                    regex += "(?:.*/)?"  # zero or more directories
                    index = after + 1
                    continue
                regex += ".*"
                index = after
                continue
            regex += "[^/]*"
        elif char == "?":
            regex += "[^/]"
        else:
            regex += re.escape(char)
        index += 1
    return re.compile(f"^{regex}$")


def path_matches(pattern: str, path: str) -> bool:
    return glob_to_regex(pattern).match(path) is not None


def load_impact_globs(path: Path | None = None) -> list[tuple[str, tuple[str, ...]]]:
    """``(control id, impact_paths)`` for every control of controls.yaml, in file order."""
    from erev_api.controls.registry import CONTROLS_PATH, load_controls

    return [(spec.id, tuple(spec.impact_paths)) for spec in load_controls(path or CONTROLS_PATH)]


def control_impact_tags(
    changed: Iterable[str], controls: Iterable[tuple[str, Iterable[str]]]
) -> list[str]:
    paths = list(changed)
    tags = {
        control_id
        for control_id, globs in controls
        if any(path_matches(glob, path) for glob in globs for path in paths)
    }
    return sorted(tags)


# --- supervisor evidence (DPL-05; DG-MK-audit-deps) -----------------------------------------


def _null_images() -> dict[str, dict[str, str | None]]:
    return {name: {"tag": None, "digest": None} for name in IMAGE_NAMES}


def image_evidence(
    reports_dir: Path, build: str
) -> tuple[dict[str, dict[str, str | None]], dict[str, Any]]:
    """``images`` and the disposition of the docker-build report (DPL-05; evidence boundary).

    Only a report of this build that finished with exit code 0, on a clean worktree and with every
    image identified is copied as ``complete``. A report of another build, a skipped run, a failed
    run or a dirty worktree yields null identities; an incomplete set copies only the images it
    identifies. The disposition names why, so unusable evidence is never mistaken for a trusted set.
    """
    empty = _null_images()
    path = reports_dir / "docker-build" / "report.json"
    if not path.is_file():
        return empty, {"status": "absent", "detail": "no docker-build report"}
    digest = sha256_of(path)
    report = _read_report(path)
    if report is None:
        return empty, {"status": "malformed", "report_sha256": digest}
    if report.get("build_sha") != build:
        return empty, {
            "status": "another-build",
            "report_build_sha": _text(report.get("build_sha")),
            "report_sha256": digest,
        }
    result = _text(report.get("result"))
    exit_code = _exit_code(report)
    if result == "skipped-no-daemon":
        return empty, {"status": "skipped", "report_sha256": digest}
    if exit_code != 0 or (result is not None and result.lower() in ("failed", "fail")):
        return empty, {
            "status": "failed",
            "exit_code": exit_code,
            "result": result,
            "report_sha256": digest,
        }
    if report.get("worktree_dirty") is not False:
        return empty, {"status": "dirty", "report_sha256": digest}
    found = report.get("images")
    images = _null_images()
    missing: list[str] = []
    for name in IMAGE_NAMES:
        entry = found.get(name) if isinstance(found, dict) else None
        tag = _text(entry.get("tag")) if isinstance(entry, dict) else None
        image_id = _text(entry.get("digest")) if isinstance(entry, dict) else None
        if tag is not None and image_id is not None:
            images[name] = {"tag": tag, "digest": image_id}
        else:
            missing.append(name)
    if missing:
        return images, {"status": "incomplete", "missing": missing, "report_sha256": digest}
    return images, {"status": IMAGES_COMPLETE, "report_sha256": digest}


def audit_deps(reports_dir: Path, build: str) -> dict[str, str | None] | None:
    """``{result, output_sha256}`` of the audit-deps report, or None without one."""
    path = reports_dir / "audit-deps" / "report.json"
    if not path.is_file():
        return None
    gate = gate_result(path, build)
    report = _read_report(path)
    digest = _text(report.get("output_sha256")) if report is not None else None
    return {"result": gate.result, "output_sha256": digest or gate.output_sha256}


def dependency_lock_sha256(root: Path) -> dict[str, str | None]:
    return {
        key: sha256_of(root / relative) if (root / relative).is_file() else None
        for key, relative in LOCK_FILES.items()
    }


# --- the manifest ---------------------------------------------------------------------------


def engine_version() -> str:
    from erev_engine import ENGINE_VERSION

    return str(ENGINE_VERSION)


def schema_revision() -> str:
    from erev_api.db.migration_ops import code_head

    return code_head()


def build_manifest(
    *,
    root: Path,
    reports_dir: Path,
    controls: Sequence[tuple[str, tuple[str, ...]]],
    created_at: str,
    embedded: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The manifest and the facts its report records (build, dirty flag, base, changed paths,
    gates, image evidence). ``embedded`` writes the pre-build manifest of the images: no image
    identities, whatever docker-build report exists."""
    build = build_sha(root)
    base = impact_base(root)
    changed = changed_paths(root, base) if base is not None else []
    corpus_cache: list[dict[str, tuple[str, str]] | str] = []

    def corpus() -> dict[str, tuple[str, str]] | str:
        if not corpus_cache:
            corpus_cache.append(load_corpus(root))
        return corpus_cache[0]

    gates = {
        key: gate_result(
            reports_dir / key / "report.json",
            build,
            (lambda report: answer_keys_evidence(report, corpus)) if key == ANSWER_KEYS else None,
        )
        for key in GATE_KEYS
    }
    if embedded:
        images: dict[str, dict[str, str | None]] = _null_images()
        evidence: dict[str, Any] = {
            "status": IMAGES_EMBEDDED,
            "detail": "pre-build manifest carried by the images; the docker-build attestation "
            "binds this manifest's SHA-256 to the image ids",
        }
    else:
        images, evidence = image_evidence(reports_dir, build)
    manifest: dict[str, Any] = {
        "engine_version": engine_version(),
        "build_sha": build,
        "schema_revision": schema_revision(),
        "created_at": created_at,
        "gate_results": {key: gate.as_json() for key, gate in gates.items()},
        "control_impact_tags": control_impact_tags(changed, controls),
        "dependency_lock_sha256": dependency_lock_sha256(root),
        "images": images,
        "audit_deps": audit_deps(reports_dir, build),
    }
    facts = {
        "build_sha": build,
        "worktree_dirty": worktree_dirty(root),
        "impact_base": base,
        "changed_paths": changed,
        "gates": gates,
        "gate_reasons": {key: gate.reason for key, gate in gates.items() if gate.reason},
        "images_evidence": evidence,
    }
    return manifest, facts


VALIDATION_LEVELS: Final = ("PATCH", "MINOR", "MAJOR")


def declare_validation_level(manifest: Mapping[str, Any], level: str) -> dict[str, Any]:
    """REL-01 ``validation_level`` (05 rev 1.16; DG-MK-release-manifest step 7): the author's
    declaration, written only through ``controls.validation_level.with_validation_level`` — the
    key's sole writer. Without a declaration the key stays absent and the consumer reads the
    release as undeclared PATCH (04 T-PLT-38 default); the generator never invents a level."""
    from erev_api.controls.validation_level import with_validation_level

    if level not in VALIDATION_LEVELS:
        raise ValueError(f"{level!r} is not a validation level")
    return with_validation_level(manifest, level)  # type: ignore[arg-type]


def render(manifest: Mapping[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


class _SingleUse(argparse.Action):
    """An option that may be given once: a repeated `--validation-level` is a named exit-2 error
    (P1-VL-S1), never a silent last-wins store."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"argument {option_string}: may be given once")
        setattr(namespace, self.dest, values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this)")
    parser.add_argument(
        "--reports-dir", type=Path, default=None, help="default <root>/.run/reports"
    )
    parser.add_argument("--out", type=Path, default=None, help=f"default <root>/{MANIFEST_NAME}")
    parser.add_argument("--controls", type=Path, default=None, help="controls.yaml to read")
    parser.add_argument("--command", default=f"make {TARGET}", help="invocation for the report")
    parser.add_argument("--strict", action="store_true", help="exit 1 unless every gate is PASS")
    parser.add_argument(
        "--embedded",
        action="store_true",
        help="the pre-build manifest the images carry: no image identities",
    )
    parser.add_argument(
        "--validation-level",
        choices=VALIDATION_LEVELS,
        default=None,
        action=_SingleUse,
        help="the author's REL-01 declaration; absent = undeclared (read as PATCH, T-PLT-38)",
    )
    args = parser.parse_args(argv)
    # P1-VL-S2: the Makefile passes the declaration as DATA through the environment (never into
    # shell source). Read byte-exactly and validated whole here, before any manifest or report
    # write; unset or empty is the omission (Make's `?=` and `VALIDATION_LEVEL=` both yield "").
    # P1-VL-S3: the authored bytes are the declaration. Under make, EREV_VALIDATION_LEVEL_RAW is
    # the $(value) capture of the unexpanded text and is read first; the plain VALIDATION_LEVEL
    # (Make's expansion on export) may only agree with it. Outside make the plain variable is read.
    raw_level = os.environ.get("EREV_VALIDATION_LEVEL_RAW")
    plain_level = os.environ.get("VALIDATION_LEVEL")
    if raw_level is not None:
        if plain_level not in (None, "") and plain_level != raw_level:
            parser.error(
                f"environment VALIDATION_LEVEL={plain_level!r} is Make's expansion of the "
                f"authored bytes EREV_VALIDATION_LEVEL_RAW={raw_level!r}; the authored bytes are "
                "the declaration and are not one of " + ", ".join(VALIDATION_LEVELS)
            )
        source, environment_level = "EREV_VALIDATION_LEVEL_RAW", raw_level
    else:
        source, environment_level = "VALIDATION_LEVEL", plain_level
    if environment_level is not None and environment_level != "":
        if environment_level not in VALIDATION_LEVELS:
            parser.error(
                f"environment {source}={environment_level!r}: not one of "
                f"{', '.join(VALIDATION_LEVELS)}"
            )
        if args.validation_level is not None and args.validation_level != environment_level:
            parser.error(
                f"--validation-level {args.validation_level} and environment "
                f"{source}={environment_level!r} disagree"
            )
        args.validation_level = environment_level
    root: Path = args.root.resolve()
    reports_dir: Path = (args.reports_dir or root / ".run" / "reports").resolve()
    out: Path = (args.out or root / MANIFEST_NAME).resolve()
    strict = bool(args.strict) or os.environ.get("STRICT") == "1"
    embedded = bool(args.embedded)
    validation_level: str | None = args.validation_level

    started_at = utc_now()
    controls = load_impact_globs(args.controls)
    manifest, facts = build_manifest(
        root=root,
        reports_dir=reports_dir,
        controls=controls,
        created_at=started_at,
        embedded=embedded,
    )
    if validation_level is not None:
        manifest = declare_validation_level(manifest, validation_level)
    else:
        print(
            f"{TARGET}: validation_level undeclared — the consumer reads PATCH (04 T-PLT-38 "
            "default); pass VALIDATION_LEVEL=PATCH|MINOR|MAJOR to declare the release",
            file=sys.stderr,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(manifest), encoding="utf-8")

    gates: dict[str, GateResult] = facts["gates"]
    evidence: dict[str, Any] = facts["images_evidence"]
    tally = {verdict: 0 for verdict in (PASS, FAIL, NOT_RUN)}
    for gate in gates.values():
        tally[gate.result] += 1
    failures: list[dict[str, Any]] = []
    reasons: list[str] = []
    if strict:
        not_passed = sorted(key for key, gate in gates.items() if gate.result != PASS)
        if not_passed or facts["worktree_dirty"]:
            failures.append(
                {
                    "stage": "strict",
                    "exit_code": 1,
                    "gates": not_passed,
                    "worktree_dirty": facts["worktree_dirty"],
                }
            )
            reasons.extend(
                f"{key} {gates[key].result}"
                + (f" ({gates[key].reason})" if gates[key].reason else "")
                for key in not_passed
            )
            if facts["worktree_dirty"]:
                reasons.append("worktree dirty")
        if evidence["status"] in IMAGES_UNUSABLE:
            failures.append({"stage": "images", "exit_code": 1, "status": evidence["status"]})
            reasons.append(f"images {evidence['status']}")
    exit_code = 1 if failures else 0

    report = {
        "target": TARGET,
        "command": args.command,
        "build_sha": facts["build_sha"],
        "worktree_dirty": facts["worktree_dirty"],
        "started_at": started_at,
        "finished_at": utc_now(),
        "exit_code": exit_code,
        "counts": {
            "gates": tally,
            "control_impact_tags": len(manifest["control_impact_tags"]),
            "changed_paths": len(facts["changed_paths"]),
        },
        "failures": failures,
        "manifest": str(out),
        "manifest_sha256": sha256_of(out),
        "impact_base": facts["impact_base"],
        "strict": strict,
        "embedded": embedded,
        "validation_level": validation_level,
        "acceptance": ACCEPTANCE_STRICT if strict else ACCEPTANCE_NON_STRICT,
        "images_evidence": evidence,
        "gate_reasons": facts["gate_reasons"],
    }
    report_dir = reports_dir / TARGET
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(render(report), encoding="utf-8")

    label = "embedded, " if embedded else ""
    print(
        f"{TARGET}: {out} ({label}build {facts['build_sha'][:12]}, "
        f"gates PASS {tally[PASS]} FAIL {tally[FAIL]} NOT_RUN {tally[NOT_RUN]}, "
        f"control impact tags {len(manifest['control_impact_tags'])}, "
        f"images {evidence['status']}; {report['acceptance']})"
    )
    if exit_code == 0:
        print(f"OK {TARGET}")
    else:
        print(f"FAIL {TARGET}: STRICT: " + ", ".join(reasons))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
