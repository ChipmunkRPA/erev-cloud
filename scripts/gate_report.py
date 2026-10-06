#!/usr/bin/env python3
"""Run a gate's stages in order and write .run/reports/<target>/report.json (DG-MK-00g), bound to
the source the stages actually executed (GATE-BIND-1; DG-MK-00i; 05 REL-02; D-80).

usage: gate_report.py <target> --command "make <target> ..." --stage NAME=COMMAND [...]
                      [--refuse NAME=VALUE ...] [--junit LABEL=PATH ...]
                      [--fail-on-skipped LABEL ...] [--counts-junit PATH] [--reports-dir DIR]
       gate_report.py <target> --exec -- COMMAND [ARG ...]

A --refuse option names a make variable the target does not accept; any non-empty value fails the
run before the first stage (ruling D-78: make ci takes no narrowing variables). Stages run through
the shell and stop at the first failure. JUnit files named with --junit are removed before the run
and summarised into counts under their label after it; the file named with --counts-junit is
summarised at the top level of counts (make properties reports counts.passed). A run whose stages
pass fails when a JUnit summary is missing, and when a label named with --fail-on-skipped reports a
skipped test (DG-TST-09). --fail-on-skipped may name the target itself when --counts-junit is given,
which checks that flat summary (ruling D-79: make properties). The final output line is
"OK <target>" or "FAIL <target>: <reason>" (DG-MK-00a).

Source binding (GATE-BIND-1). The stages never read the mutable worktree. With a clean repository
they run in an IMMUTABLE EXECUTION CONTEXT: a scratch `git clone --shared --no-checkout` of the
repository checked out `--detach` at the captured HEAD under .run/gates/ctx-<target>-<sha12>-<pid>/
(never the worktree, never a write to the shared .git), with .env copied (mode 0600, never
printed), backend/.venv and frontend/node_modules symlinked from the worktree (the reused
artifacts; their identities are recorded), PYTHONPATH=<ctx>/backend so the context's packages
shadow the editable install, and cwd=<ctx>. Before the stages the binding is PROVED: when the source
holds backend/erev_api, `erev_api.__file__`, `erev_engine.__file__`, `REPO_ROOT`, `ALEMBIC_INI`
and the Alembic versions directory must resolve under the context, and the console script's
interpreter must import the context's `erev_api.cli`. After the stages the context's tree sha and
the content hash of its tracked files must equal their start values, else the report is FAIL with
failures[].stage "source". Relative --junit paths resolve against the execution root; files the
stages left under <ctx>/.run/reports/<target>/ are copied back. The report gains `source_binding`
(mode, captured sha, hashes before and after, executed module origins, interpreter and artifact
identities, the worktree's HEAD and dirty state after the run). A dirty worktree, or no repository,
runs in place with mode "worktree-dirty (development; not release evidence)" and a printed
warning: the manifest classified such runs NOT_RUN before (dirty state was merely recorded); now
the run itself is labelled. When EREV_GATE_CONTEXT names this repository the process already runs
inside a context made by `scripts/gate_context.sh`: no clone, in-place execution, same proof and
hash checks. --exec runs one command instead of stages (the wrapper for the answer-keys, parity,
controls-report and e2e writers) and enriches the report that command wrote. Contexts are removed
on exit unless EREV_GATE_KEEP_CONTEXT=1; contexts whose recorded pid is dead are swept at start.
This module imports the standard library only, so a copy of it runs anywhere.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODE_CONTEXT = "immutable-context"
MODE_DIRTY = "worktree-dirty (development; not release evidence)"
CONTEXT_ENV = "EREV_GATE_CONTEXT"
CAPTURED_ENV = "EREV_GATE_CAPTURED_SHA"
KEEP_ENV = "EREV_GATE_KEEP_CONTEXT"
RUN_ID_ENV = "EREV_GATE_RUN_ID"  # minted per run; inner commands stamp it into their reports

PROOF_PROGRAM = r"""
import json, sys
from pathlib import Path
context = Path(sys.argv[1]).resolve()
import erev_api, erev_engine
from erev_api import cli, config
from erev_api.db import migration_ops
observed = {
    "executed_erev_api": erev_api.__file__,
    "executed_erev_engine": erev_engine.__file__,
    "executed_repo_root": str(config.REPO_ROOT),
    "executed_alembic_ini": str(cli.ALEMBIC_INI),
    "executed_versions_dir": str(migration_ops.VERSIONS_DIR),
    "executed_python": sys.executable,
    "executed_python_version": sys.version.split()[0],
}
outside = {k: v for k, v in observed.items()
           if not k.startswith("executed_python") and not Path(v).resolve().is_relative_to(context)}
if outside:
    sys.stderr.write("binding proof failed: %s\n" % json.dumps(outside, sort_keys=True))
    sys.exit(1)
print(json.dumps(observed, sort_keys=True))
"""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_sha(root: Path = ROOT) -> str:
    completed = _git(root, "rev-parse", "HEAD")
    if completed is None or completed.returncode != 0:
        return "nogit"
    sha = completed.stdout.strip()
    return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else "nogit"


def worktree_dirty(root: Path = ROOT) -> bool:
    completed = _git(root, "status", "--porcelain")
    if completed is None or completed.returncode != 0:
        return False
    return bool(completed.stdout.strip())


def tree_sha(root: Path) -> str | None:
    completed = _git(root, "rev-parse", "HEAD^{tree}")
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def content_hash(root: Path) -> str | None:
    """SHA-256 over the sorted tracked paths and their bytes (symlinks by their target)."""
    completed = _git(root, "ls-files", "-z")
    if completed is None or completed.returncode != 0:
        return None
    names = sorted(name for name in completed.stdout.split("\0") if name)
    if not names:
        return None
    digest = hashlib.sha256()
    for name in names:
        path = root / name
        digest.update(name.encode() + b"\0")
        if path.is_symlink():
            digest.update(b"link:" + os.readlink(path).encode() + b"\0")
        elif path.is_file():
            digest.update(hashlib.sha256(path.read_bytes()).digest() + b"\0")
        else:
            digest.update(b"missing\0")
    return digest.hexdigest()


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def junit_counts(path: Path) -> dict[str, int] | None:
    """Count the test cases of a JUnit XML file written by pytest or Vitest: ``passed``,
    ``failed`` (failures and errors), ``skipped``, and ``xfailed`` — pytest writes an expected
    failure as ``<skipped type="pytest.xfail">``, which must not be folded into ``skipped``
    (DG-TST-09 reasons about skips; JUnit does not record strict versus non-strict). A suite
    without ``testcase`` children is counted from its totals (no xfailed information)."""
    if not path.is_file():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0}
    for suite in suites:
        cases = list(suite.iter("testcase"))
        if not cases:
            tests = int(suite.get("tests", "0") or 0)
            failed = int(suite.get("failures", "0") or 0) + int(suite.get("errors", "0") or 0)
            skipped = int(suite.get("skipped", "0") or 0)
            counts["failed"] += failed
            counts["skipped"] += skipped
            counts["passed"] += tests - failed - skipped
            continue
        for case in cases:
            if case.find("failure") is not None or case.find("error") is not None:
                counts["failed"] += 1
            elif (skipped_el := case.find("skipped")) is not None:
                kind = "xfailed" if (skipped_el.get("type") or "").endswith("xfail") else "skipped"
                counts[kind] += 1
            else:
                counts["passed"] += 1
    return counts


REPORT_KEYS = (
    "target",
    "command",
    "build_sha",
    "worktree_dirty",
    "started_at",
    "finished_at",
    "exit_code",
    "counts",
    "failures",
)


def _figure(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def has_population(counts: Mapping[str, Any]) -> bool:
    """DG-MK-00g evidence population: at least one figure in ``counts`` (top level or one level
    down), or a non-empty ``stages`` map whose stages all passed."""
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


# RFC 3339 date-time only: `YYYY-MM-DDThh:mm:ss[.fraction](Z|±hh:mm)`. datetime.fromisoformat
# alone also accepts ISO week dates, ordinal dates and a space separator, which the DG-MK-00i
# contract does not promise.
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})")


def _instant(value: Any) -> dt.datetime | None:
    """An RFC 3339 date-time with an offset (``Z`` or ``±hh:mm``), else None."""
    if not isinstance(value, str) or RFC3339.fullmatch(value) is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def usable_evidence(
    report: Mapping[str, Any],
    target: str,
    captured_sha: str,
    *,
    run_id: str | None = None,
    run_started_at: str | None = None,
) -> str | None:
    """Why an inner DG-MK-00g report is not usable gate evidence (None when it is): the nine keys
    with their types, the target and the captured build (identity), a populated ``counts`` when
    the report claims success, and — the run binding — a ``run_id`` equal to this run's when the
    report stamps one, and a ``started_at`` not before this run began (a previous or archived
    file is never this run's evidence)."""
    missing = [key for key in REPORT_KEYS if key not in report]
    if missing:
        return "schema: missing " + ", ".join(missing)
    if not isinstance(report["target"], str):
        return "schema: target is not a string"
    if not isinstance(report["command"], str) or not report["command"]:
        return "schema: command is not a non-empty string"
    build = report["build_sha"]
    if not isinstance(build, str) or re.fullmatch(r"[0-9a-f]{40}", build) is None:
        return "schema: build_sha is not a 40-hex sha"
    if not isinstance(report["worktree_dirty"], bool):
        return "schema: worktree_dirty is not a boolean"
    started, finished = _instant(report["started_at"]), _instant(report["finished_at"])
    if started is None:
        return "schema: started_at is not an RFC 3339 instant with an offset"
    if finished is None:
        return "schema: finished_at is not an RFC 3339 instant with an offset"
    if finished < started:
        return "schema: finished_at precedes started_at"
    if not _figure(report["exit_code"]):
        return "schema: exit_code is not an integer"
    if not isinstance(report["counts"], dict):
        return "schema: counts is not an object"
    if not isinstance(report["failures"], list):
        return "schema: failures is not a list"
    if report["target"] != target:
        return f"identity: target {report['target']!r} is not {target!r}"
    if build != captured_sha:
        return f"identity: build_sha {build[:12]} is not the captured {captured_sha[:12]}"
    if report["exit_code"] == 0 and not has_population(report["counts"]):
        return "population: counts carries no figure"  # a recorded failure needs no population
    stamped = report.get("run_id")
    if run_id is not None and stamped is not None and stamped != run_id:
        return f"stale: run_id {str(stamped)[:12]} is not this run's {run_id[:12]}"
    if run_started_at is not None:
        began = _instant(run_started_at)
        if began is not None and started < began:
            return (
                f"stale: started_at {report['started_at']} precedes this run's start "
                f"{run_started_at}"
            )
    return None


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def installed_distributions(venv: Path) -> dict[str, str]:
    """``{normalised name: version}`` of the ``*.dist-info`` directories under the venv."""
    found: dict[str, str] = {}
    for metadata in sorted(venv.glob("lib/python*/site-packages/*.dist-info/METADATA")):
        try:
            text = metadata.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        name = re.search(r"^Name:\s*(.+?)\s*$", text, re.M)
        version = re.search(r"^Version:\s*(.+?)\s*$", text, re.M)
        if name and version:
            found[_normalise(name.group(1))] = version.group(1)
    return found


def locked_python(lock: Path) -> dict[str, set[str]] | None:
    """``{normalised name: {versions}}`` from ``uv.lock`` (universal: a name may carry several)."""
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11 fallback interpreter
        return None
    try:
        data = tomllib.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    locked: dict[str, set[str]] = {}
    for package in data.get("package") or []:
        if isinstance(package, dict) and isinstance(package.get("name"), str):
            locked.setdefault(_normalise(package["name"]), set()).add(str(package.get("version")))
    return locked


def _npm_packages(path: Path) -> dict[str, str] | None:
    """``{node_modules/<name>: version}`` of an npm lock file (the root entry dropped)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    packages = data.get("packages") if isinstance(data, dict) else None
    if not isinstance(packages, dict):
        return None
    return {
        name: str(entry.get("version"))
        for name, entry in packages.items()
        if name and isinstance(entry, dict)
    }


def _pairs(
    values: Sequence[str], option: str, *, allow_empty: bool = False
) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep or not name or not (rest or allow_empty):
            raise SystemExit(f"{option} expects NAME=VALUE, got {value!r}")
        pairs.append((name, rest))
    return pairs


def _join(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _hardlink_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    for entry in source.iterdir():
        if entry.is_symlink():
            (target / entry.name).symlink_to(os.readlink(entry))
        elif entry.is_dir():
            _hardlink_tree(entry, target / entry.name)
        else:
            os.link(entry, target / entry.name)


def clone_tree(source: Path, target: Path) -> str:
    """Materialise ``source`` at ``target`` as a real directory the tools treat as the context's
    own (npm resolves real paths and calls every package of a symlinked node_modules extraneous):
    one APFS ``clonefile`` of the whole hierarchy (copy-on-write, under a second for node_modules),
    else GNU ``cp --reflink=auto``, else a hardlink tree, else a symlink. Returns the kind."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        try:
            libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
            if libc.clonefile(os.fsencode(source), os.fsencode(target), 0) == 0:
                return "clone"
        except (OSError, AttributeError):
            pass
        shutil.rmtree(target, ignore_errors=True)
    else:
        copied = subprocess.run(
            ["cp", "-a", "--reflink=auto", str(source), str(target)],
            capture_output=True,
            check=False,
        )
        if copied.returncode == 0:
            return "clone"
        shutil.rmtree(target, ignore_errors=True)
    try:
        _hardlink_tree(source, target)
        return "hardlink"
    except OSError:
        shutil.rmtree(target, ignore_errors=True)
    target.symlink_to(source, target_is_directory=True)
    return "symlink"


class ExecutionContext:
    """Where the stages run and how the report is bound to it (GATE-BIND-1)."""

    def __init__(self, target: str, root: Path) -> None:
        self.target = target
        self.root = root
        self.captured_sha = build_sha(root)
        self.dirty = worktree_dirty(root)
        inside = os.environ.get(CONTEXT_ENV)
        self.inner = bool(inside) and Path(inside).resolve() == root.resolve()
        if self.inner:
            self.mode = MODE_CONTEXT
            self.captured_sha = os.environ.get(CAPTURED_ENV) or self.captured_sha
        elif self.captured_sha == "nogit" or self.dirty:
            self.mode = MODE_DIRTY
        else:
            self.mode = MODE_CONTEXT
        # Run binding (REL-COV-1 / Codex 1510): one id per wrapper run — adopted from the outer
        # wrapper for an inner invocation — and the run's start; the inner report must carry this
        # id (when it stamps one) and must not have started before the run began.
        self.run_id = os.environ.get(RUN_ID_ENV) or uuid.uuid4().hex
        self.run_started_at = utc_now()
        self.exec_root = root
        self.context: Path | None = None
        self.keep = os.environ.get(KEEP_ENV) == "1"
        self.tree_start: str | None = None
        self.tree_end: str | None = None
        self.content_start: str | None = None
        self.content_end: str | None = None
        self.proof: dict[str, Any] = {}
        self.venv_identity: dict[str, Any] | None = None
        self.node_identity: dict[str, Any] | None = None
        self.venv_binding = "in-place"
        self.node_binding = "in-place"
        self.dependencies: dict[str, Any] = {
            "venv": "not checked",
            "node_modules": "not checked",
            "mismatches": [],
        }
        self.env = dict(os.environ)
        self.env[RUN_ID_ENV] = self.run_id

    # -- context life cycle ---------------------------------------------------------------------

    def sweep_orphans(self) -> None:
        gates = self.root / ".run" / "gates"
        if not gates.is_dir():
            return
        for stale in gates.glob("ctx-*"):
            pid_file = stale / ".run" / "gate-pid"
            try:
                pid = int(pid_file.read_text().strip()) if pid_file.is_file() else None
            except ValueError:
                pid = None
            alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
            if not alive:
                shutil.rmtree(stale, ignore_errors=True)

    def create(self) -> str | None:
        """Clone and check out the captured commit; returns a reason on failure."""
        if self.mode != MODE_CONTEXT or self.inner:
            return None
        self.sweep_orphans()
        gates = self.root / ".run" / "gates"
        gates.mkdir(parents=True, exist_ok=True)
        ctx = gates / f"ctx-{self.target}-{self.captured_sha[:12]}-{os.getpid()}"
        if ctx.exists():
            shutil.rmtree(ctx, ignore_errors=True)
        clone = _git(
            self.root, "clone", "--quiet", "--shared", "--no-checkout", str(self.root), str(ctx)
        )
        if clone is None or clone.returncode != 0:
            return "cannot clone the repository into the execution context"
        self.context = ctx
        # The orphan-sweep marker lives under .run/ (an allowed top-level entry): a wrapper file at
        # the context root is an unexpected entry for the repository-layout test (DG-LAY-01).
        (ctx / ".run").mkdir(parents=True, exist_ok=True)
        (ctx / ".run" / "gate-pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
        checkout = _git(ctx, "checkout", "--quiet", "--detach", self.captured_sha)
        if checkout is None or checkout.returncode != 0 or build_sha(ctx) != self.captured_sha:
            return f"cannot check out {self.captured_sha[:12]} in the execution context"
        env_file = self.root / ".env"
        if env_file.is_file():
            shutil.copyfile(env_file, ctx / ".env")
            (ctx / ".env").chmod(stat.S_IRUSR | stat.S_IWUSR)
        venv_source, venv_link = self.root / "backend" / ".venv", ctx / "backend" / ".venv"
        if venv_source.is_dir() and not venv_link.exists():
            venv_link.parent.mkdir(parents=True, exist_ok=True)
            venv_link.symlink_to(venv_source, target_is_directory=True)
            self.venv_binding = "symlink"
        modules_source = self.root / "frontend" / "node_modules"
        modules_target = ctx / "frontend" / "node_modules"
        if modules_source.is_dir() and not modules_target.exists():
            self.node_binding = clone_tree(modules_source, modules_target)
        (ctx / ".run" / "tmp").mkdir(parents=True, exist_ok=True)
        (ctx / ".run" / "reports").mkdir(parents=True, exist_ok=True)
        self.exec_root = ctx
        self.env[CONTEXT_ENV] = str(ctx)
        self.env[CAPTURED_ENV] = self.captured_sha
        backend = str(ctx / "backend")
        existing = self.env.get("PYTHONPATH")
        self.env["PYTHONPATH"] = backend if not existing else f"{backend}{os.pathsep}{existing}"
        # Tool caches stay under <ctx>/backend/ whatever a stage's invocation (DG-LAY-01): the
        # Makefile exports the same for its own recipes; this covers every other producer.
        self.env["RUFF_CACHE_DIR"] = str(ctx / "backend" / ".ruff_cache")
        self.env["MYPY_CACHE_DIR"] = str(ctx / "backend" / ".mypy_cache")
        return None

    def snapshot_start(self) -> None:
        if self.mode == MODE_CONTEXT:
            self.tree_start = tree_sha(self.exec_root)
            self.content_start = content_hash(self.exec_root)

    def snapshot_end(self) -> bool:
        """False when the executed source changed during the run."""
        if self.mode != MODE_CONTEXT:
            return True
        self.tree_end = tree_sha(self.exec_root)
        self.content_end = content_hash(self.exec_root)
        return (
            self.tree_start is not None
            and self.content_start is not None
            and self.tree_start == self.tree_end
            and self.content_start == self.content_end
        )

    def prove(self) -> str | None:
        """Module-origin proof inside the execution root; returns a reason on failure."""
        if self.mode != MODE_CONTEXT:
            return None
        if not (self.exec_root / "backend" / "erev_api").is_dir():
            self.proof = {"module_origin": "not applicable (no backend/erev_api in the source)"}
            return None
        env = dict(self.env)
        backend = str(self.exec_root / "backend")
        env["PYTHONPATH"] = (
            backend if not env.get("PYTHONPATH") else f"{backend}{os.pathsep}{env['PYTHONPATH']}"
        )
        completed = subprocess.run(
            [sys.executable, "-c", PROOF_PROGRAM, str(self.exec_root)],
            cwd=self.exec_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return "binding proof failed: a module or path resolves outside the execution context"
        self.proof = json.loads(completed.stdout.strip().splitlines()[-1])
        console = self.exec_root / "backend" / ".venv" / "bin" / "erev"
        interpreter = self.exec_root / "backend" / ".venv" / "bin" / "python"
        if console.exists() and interpreter.exists():
            check = subprocess.run(
                [str(interpreter), "-c", "import erev_api.cli as cli; print(cli.__file__)"],
                cwd=self.exec_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            resolved = check.stdout.strip()
            if check.returncode != 0 or not Path(resolved).resolve().is_relative_to(
                self.exec_root.resolve()
            ):
                return "the console script would import erev_api.cli from outside the context"
            self.proof["console_script"] = str(console)
            self.proof["console_script_cli"] = resolved
        return None

    # -- reused artifacts (GATE-BIND-1 dependency policy) --------------------------------------

    def _venv_digest(self) -> tuple[dict[str, str], str]:
        installed = installed_distributions(self.exec_root / "backend" / ".venv")
        listing = "\n".join(f"{name}=={version}" for name, version in sorted(installed.items()))
        return installed, hashlib.sha256(listing.encode("utf-8")).hexdigest()

    def check_dependencies(self) -> str | None:
        """The installed venv and node_modules the context reuses must agree with the executed
        source's lock files; returns the reason when they do not. Identities are recorded."""
        mismatches: list[str] = []
        venv = self.exec_root / "backend" / ".venv"
        if venv.is_dir():
            installed, digest = self._venv_digest()
            self.venv_identity = {
                "path": str(venv.resolve()),
                "source": str((self.root / "backend" / ".venv").resolve()),
                "binding": self.venv_binding,
                "python": sys.executable,
                "python_version": ".".join(str(part) for part in sys.version_info[:3]),
                "installed_sha256": digest,
                "installed_sha256_end": None,
                "distributions": len(installed),
            }
            lock = self.exec_root / "backend" / "uv.lock"
            if not lock.is_file():
                mismatches.append("backend/uv.lock absent in the executed source")
            else:
                locked = locked_python(lock)
                if locked is None:
                    mismatches.append("backend/uv.lock unreadable in the executed source")
                else:
                    for name, version in sorted(installed.items()):
                        if name not in locked:
                            mismatches.append(f"{name} {version} (not in backend/uv.lock)")
                        elif version not in locked[name]:
                            wanted = "/".join(sorted(locked[name]))
                            mismatches.append(f"{name} {version} (backend/uv.lock {wanted})")
            venv_status = "mismatch" if mismatches else "consistent"
        else:
            venv_status = "not applicable (no backend/.venv)"
        before = len(mismatches)
        modules = self.exec_root / "frontend" / "node_modules"
        if modules.is_dir():
            hidden = modules / ".package-lock.json"
            installed_node = _npm_packages(hidden) if hidden.is_file() else None
            self.node_identity = {
                "path": str(modules),
                "source": str((self.root / "frontend" / "node_modules").resolve()),
                "binding": self.node_binding,
                "installed_sha256": file_sha256(hidden),
                "installed_sha256_end": None,
                "packages": len(installed_node) if installed_node is not None else None,
            }
            if installed_node is None:
                mismatches.append(
                    "frontend/node_modules/.package-lock.json absent or unreadable "
                    "(node_modules not installed from the lock file)"
                )
            else:
                locked_node = _npm_packages(self.exec_root / "frontend" / "package-lock.json")
                if locked_node is None:
                    mismatches.append(
                        "frontend/package-lock.json absent or unreadable in the executed source"
                    )
                else:
                    for name, version in sorted(installed_node.items()):
                        if name not in locked_node:
                            mismatches.append(
                                f"{name} {version} (not in frontend/package-lock.json)"
                            )
                        elif locked_node[name] != version:
                            mismatches.append(
                                f"{name} {version} (frontend/package-lock.json {locked_node[name]})"
                            )
            node_status = "mismatch" if len(mismatches) > before else "consistent"
        else:
            node_status = "not applicable (no frontend/node_modules)"
        self.dependencies = {
            "venv": venv_status,
            "node_modules": node_status,
            "mismatches": mismatches,
        }
        if mismatches:
            return (
                "installed dependencies differ from the executed source's lock files: "
                + "; ".join(mismatches)
            )
        return None

    def artifacts_drift(self) -> list[str]:
        """Reused artifacts that changed during the run (identities re-taken at the end)."""
        drift: list[str] = []
        if self.venv_identity is not None:
            _, digest = self._venv_digest()
            self.venv_identity["installed_sha256_end"] = digest
            if digest != self.venv_identity["installed_sha256"]:
                drift.append("backend/.venv changed during the run")
        if self.node_identity is not None:
            digest = file_sha256(
                self.exec_root / "frontend" / "node_modules" / ".package-lock.json"
            )
            self.node_identity["installed_sha256_end"] = digest
            if digest != self.node_identity["installed_sha256"]:
                drift.append("frontend/node_modules changed during the run")
        if drift:
            self.dependencies["mismatches"] = list(self.dependencies["mismatches"]) + drift
        return drift

    def copy_back(self, reports_dir: Path) -> None:
        """Files the stages left under <ctx>/.run/reports/<target>/; report.json is written here."""
        if self.exec_root == self.root:
            return
        source = self.exec_root / ".run" / "reports" / self.target
        if not source.is_dir():
            return
        destination = reports_dir / self.target
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            if item.name == "report.json":
                continue
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copyfile(item, target)

    def inner_report(self) -> tuple[dict[str, Any] | None, str | None]:
        """The report an --exec command wrote in the execution root, or why there is none."""
        path = self.exec_root / ".run" / "reports" / self.target / "report.json"
        if not path.is_file():
            return None, "missing"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError:
            return None, "unreadable"
        except ValueError:
            return None, "malformed (not JSON)"
        if not isinstance(data, dict):
            return None, "malformed (not a JSON object)"
        return data, None

    def cleanup(self) -> None:
        if self.context is not None and self.context.exists() and not self.keep:
            shutil.rmtree(self.context, ignore_errors=True)

    def binding(self) -> dict[str, Any]:
        binding: dict[str, Any] = {
            "mode": self.mode,
            "captured_sha": self.captured_sha,
            "run_id": self.run_id,
            "run_started_at": self.run_started_at,
            "tree_sha": self.tree_start,
            "tree_sha_end": self.tree_end,
            "context_sha256_start": self.content_start,
            "context_sha256_end": self.content_end,
            "context_path": str(self.exec_root) if self.mode == MODE_CONTEXT else None,
            "context_kept": bool(self.context is not None and self.keep),
            "context_inner": self.inner,
            "worktree_head_after": build_sha(self.root),
            "worktree_dirty_after": worktree_dirty(self.root),
            "python": sys.executable,
            # The executed source's lock files (the context), never the worktree's.
            "uv_lock_sha256": file_sha256(self.exec_root / "backend" / "uv.lock"),
            "package_lock_sha256": file_sha256(self.exec_root / "frontend" / "package-lock.json"),
            # The reused installed artifacts, identified by content, and the policy verdict.
            "venv": self.venv_identity,
            "node_modules": self.node_identity,
            "dependencies": self.dependencies,
        }
        binding.update(self.proof)
        return binding


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target")
    parser.add_argument("--command", default=None)
    parser.add_argument("--stage", action="append", default=[])
    parser.add_argument("--refuse", action="append", default=[])
    parser.add_argument("--junit", action="append", default=[])
    parser.add_argument("--fail-on-skipped", action="append", default=[])
    # A gate with one suite reports its counts at the top level (make properties: counts.passed).
    parser.add_argument("--counts-junit", type=Path, default=None)
    # Tests write their reports elsewhere so they never replace a real gate report.
    parser.add_argument("--reports-dir", type=Path, default=ROOT / ".run" / "reports")
    # GATE-BIND-1 wrapper mode: `<target> --exec -- COMMAND…` runs one command (the writers that
    # are not stage lists). The command is split off before argparse sees it, so its own options
    # and the leading `--` never reach the parser; the flag below only documents the usage.
    parser.add_argument("--exec", action="store_true", help="run one command: --exec -- COMMAND…")
    given = list(sys.argv[1:] if argv is None else argv)
    exec_command: list[str] | None = None
    if "--exec" in given:
        index = given.index("--exec")
        exec_command = given[index + 1 :]
        given = given[:index]
        if exec_command and exec_command[0] == "--":
            exec_command = exec_command[1:]
        if not exec_command:
            raise SystemExit("--exec expects a command after --")
    args = parser.parse_args(given)
    if exec_command is not None and args.stage:
        raise SystemExit("--exec and --stage are exclusive")
    command = args.command or (f"make {args.target}" if exec_command else "")
    if not exec_command and not args.command:
        raise SystemExit("--command is required with --stage")
    stages = _pairs(args.stage, "--stage")
    refused = _pairs(args.refuse, "--refuse", allow_empty=True)
    junits = [(label, Path(path)) for label, path in _pairs(args.junit, "--junit")]
    flat_junit = Path(args.counts_junit) if args.counts_junit is not None else None
    labels = [label for label, _ in junits]
    for label in args.fail_on_skipped:
        if label not in labels and not (label == args.target and flat_junit is not None):
            raise SystemExit(
                f"--fail-on-skipped names {label!r}, which no --junit option labels and which is "
                "not a target with --counts-junit"
            )

    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = ROOT / reports_dir
    context = ExecutionContext(args.target, ROOT)
    report: dict[str, Any] = {
        "target": args.target,
        "command": command,
        "build_sha": context.captured_sha,
        "worktree_dirty": context.dirty,
        "started_at": utc_now(),
    }
    stage_results = {name: "not run" for name, _ in stages}
    failures: list[dict[str, Any]] = []
    reason = ""
    rule = f"DG-MK-{args.target}"

    def finish(exit_code: int, counts: dict[str, Any], inner: dict[str, Any] | None = None) -> int:
        body = dict(inner) if inner else report
        if inner:
            body["target"] = args.target
            if not isinstance(body.get("command"), str) or not body.get("command"):
                body["command"] = command
            body["build_sha"] = context.captured_sha
            body["worktree_dirty"] = context.dirty
            body.setdefault("started_at", report["started_at"])
            existing = body.get("failures")
            if failures:
                body["failures"] = (existing if isinstance(existing, list) else []) + failures
            if exit_code:
                body["exit_code"] = exit_code
        else:
            body.update(exit_code=exit_code, counts=counts, failures=failures)
        body["finished_at"] = utc_now()
        body.setdefault("run_id", context.run_id)
        inner_binding = (
            body.get("source_binding") if isinstance(body.get("source_binding"), dict) else {}
        )
        outer_binding = context.binding()
        merged = dict(inner_binding)
        merged.update(
            {
                key: value
                for key, value in outer_binding.items()
                if value is not None or key not in merged
            }
        )
        body["source_binding"] = merged
        out_dir = reports_dir / args.target
        out_dir.mkdir(parents=True, exist_ok=True)
        context.copy_back(reports_dir)
        (out_dir / "report.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
        context.cleanup()
        return exit_code

    given = [name for name, value in refused if value]
    if given:
        failures.append({"stage": "variables", "exit_code": 1, "variables": given})
        names = [name for name, _ in refused]
        reason = f"{_join(names)} {'is' if len(names) == 1 else 'are'} not accepted ({rule})"
        finish(1, {"stages": stage_results})
        print(f"FAIL {args.target}: {reason}")
        return 1

    if context.mode == MODE_DIRTY:
        print(
            f"gate-context: {args.target} runs in the worktree ({MODE_DIRTY}); "
            "commit first for release evidence",
            flush=True,
        )
    problem = context.create()
    if problem is None:
        context.snapshot_start()
        problem = context.prove()
    if problem is not None:
        failures.append({"stage": "binding", "exit_code": 1})
        finish(1, {"stages": stage_results})
        print(f"FAIL {args.target}: {problem}")
        return 1
    problem = context.check_dependencies()
    if problem is not None:
        failures.append({"stage": "source", "exit_code": 1, "check": "dependencies"})
        finish(1, {"stages": stage_results})
        print(f"FAIL {args.target}: {problem}")
        return 1
    if context.mode == MODE_CONTEXT and not context.inner:
        print(
            f"gate-context: {args.target} runs in {context.exec_root} "
            f"({context.captured_sha[:12]}, tree {(context.tree_start or '')[:12]})",
            flush=True,
        )

    def resolve(path: Path) -> Path:
        return path if path.is_absolute() else context.exec_root / path

    junit_paths = [(label, resolve(path)) for label, path in junits]
    flat_path = resolve(flat_junit) if flat_junit is not None else None
    for path in [path for _, path in junit_paths] + ([flat_path] if flat_path else []):
        path.unlink(missing_ok=True)

    inner_report: dict[str, Any] | None = None
    evidence_problem: str | None = None
    if exec_command:
        print(f"== {args.target}: exec ==", flush=True)
        completed = subprocess.run(
            exec_command, cwd=context.exec_root, env=context.env, check=False
        )
        exec_code = completed.returncode
        inner_report, evidence_problem = context.inner_report()
        if inner_report is not None:
            evidence_problem = usable_evidence(
                inner_report,
                args.target,
                context.captured_sha,
                run_id=context.run_id,
                run_started_at=context.run_started_at,
            )
        if exec_code != 0 and (inner_report is None or inner_report.get("exit_code") in (0, None)):
            failures.append({"stage": "exec", "exit_code": exec_code})
            reason = f"command failed (exit {exec_code})"
        if evidence_problem is not None:
            # The command left no usable DG-MK-00g report: FAIL, never a successful empty record.
            failures.append({"stage": "report", "exit_code": 1, "detail": evidence_problem})
            reason = reason or f"no usable gate report from the command ({evidence_problem})"
    else:
        exec_code = 0
        for name, stage_command in stages:
            print(f"== {args.target}: stage {name} ==", flush=True)
            completed = subprocess.run(
                stage_command, shell=True, cwd=context.exec_root, env=context.env, check=False
            )
            if completed.returncode != 0:
                stage_results[name] = "fail"
                failures.append({"stage": name, "exit_code": completed.returncode})
                reason = f"stage {name} failed (exit {completed.returncode})"
                exec_code = completed.returncode
                break
            stage_results[name] = "pass"

    counts: dict[str, Any] = {"stages": stage_results}
    for label, path in junit_paths:
        summary = junit_counts(path)
        if summary is not None:
            counts[label] = summary
    flat = junit_counts(flat_path) if flat_path is not None else None
    if flat is not None:
        counts.update(flat)

    if not failures and not exec_command:
        # D-78: a gate whose JUnit summary is missing fails.
        missing = [label for label in labels if label not in counts]
        if flat_junit is not None and flat is None:
            missing.append(args.target)
        for label in missing:
            failures.append({"stage": "junit", "exit_code": 1, "label": label})
        if missing:
            reason = f"JUnit summary {_join(missing)} missing ({rule})"
    if not failures and not exec_command:
        for label in args.fail_on_skipped:
            summary = counts[label] if label in labels else flat
            skipped = summary["skipped"] if summary is not None else 0
            xfailed = summary.get("xfailed", 0) if summary is not None else 0
            if skipped or xfailed:
                # DG-TST-09 forbids skips AND expected failures in the suites that name this option.
                failures.append({"stage": "skipped", "exit_code": 1, "label": label})
                parts = ([f"{skipped} skipped"] if skipped else []) + (
                    [f"{xfailed} xfailed"] if xfailed else []
                )
                plural = "test" if skipped + xfailed == 1 else "tests"
                reason = f"{' and '.join(parts)} {plural} in {label} (DG-TST-09)"
                break

    unchanged = context.snapshot_end()
    if not unchanged:
        failures.append({"stage": "source", "exit_code": 1})
        reason = "source changed in the execution context during the run"
    drift = context.artifacts_drift()
    if drift:
        failures.append({"stage": "source", "exit_code": 1, "check": "dependencies"})
        reason = "reused artifacts changed during the run: " + "; ".join(drift)
        unchanged = False

    if exec_command:
        inner_exit = inner_report.get("exit_code") if inner_report else None
        if not unchanged:
            exit_code = 1
        elif exec_code:
            exit_code = exec_code
        elif evidence_problem is not None:
            exit_code = 1
        else:
            exit_code = inner_exit if isinstance(inner_exit, int) else 1
    else:
        exit_code = failures[0]["exit_code"] if failures else 0
        if not unchanged:
            exit_code = 1
    finish(exit_code, counts, inner_report)

    if not exec_command:

        def summary_text(c: Mapping[str, Any]) -> str:
            text = f"{c['passed']} passed, {c['failed']} failed, {c['skipped']} skipped"
            return text + (f", {c['xfailed']} xfailed" if c.get("xfailed") else "")

        summaries = [
            f"{label} {summary_text(c)}"
            for label, c in counts.items()
            if label != "stages" and isinstance(c, dict) and "passed" in c
        ]
        if flat is not None:
            summaries.insert(0, summary_text(flat))
        if summaries:
            print(f"{args.target} counts: " + "; ".join(summaries))
    if exit_code == 0:
        if not exec_command or not unchanged:
            print(f"OK {args.target}")
    elif not unchanged or not exec_command or evidence_problem is not None:
        print(f"FAIL {args.target}: {reason}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
