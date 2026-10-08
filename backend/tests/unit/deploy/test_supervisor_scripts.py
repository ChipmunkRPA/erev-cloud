"""Supervisor target scripts, static rules (dev-guide §4.5, DG-MK-00h, DG-FORBID-07, DG-FORBID-12;
05 DPL-42; BUILD_SPEC DEP-5). This module holds the ``tf-validate`` part (lane P3); the docker,
compose, zap, audit-deps and backup parts are added by their lanes (P1 covers ``docker_build.sh``
in ``test_docker_build.py``).

The loop never runs a supervisor target. ``scripts/tf_validate.sh`` is exercised here only against
a stand-in ``terraform`` binary in a scratch root, so no provider is downloaded, no network is used
and the worktree's own reports are never touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from support.gate_evidence import REPORT_KEYS, has_population, usable_evidence

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "tf_validate.sh"
MAKEFILE = ROOT / "Makefile"

# The stand-in records every invocation and fails the subcommand named by STUB_FAIL.
TERRAFORM_STUB = """#!/usr/bin/env bash
echo "$*" >>"$STUB_CALLS"
sub=""
for arg in "$@"; do
  case "$arg" in
    -chdir=*|-json|-no-color|-backend=*|-input=*|-check|-recursive) ;;
    *) sub="$arg"; break ;;
  esac
done
if [[ "$sub" == "version" ]]; then
  printf '{"terraform_version":"9.9.9-stub"}\\n'
  exit 0
fi
if [[ "$sub" == "${STUB_FAIL:-}" ]]; then
  echo "stub: $sub failed" >&2
  exit 1
fi
if [[ "$sub" == "validate" && -n "${STUB_MUTATE_FILE:-}" ]]; then
  echo "# mutated during validation" >>"$STUB_MUTATE_FILE"
fi
exit 0
"""


@pytest.fixture
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        root = Path(directory)
        tf_dir = root / "deploy" / "terraform" / "gcp"
        tf_dir.mkdir(parents=True)
        (tf_dir / "versions.tf").write_text(
            'terraform {\n  required_version = ">= 1.6"\n}\n', "utf-8"
        )
        (tf_dir / ".terraform.lock.hcl").write_text(
            'provider "registry.terraform.io/hashicorp/google" {\n'
            '  version     = "6.50.0"\n'
            '  constraints = "~> 6.0"\n'
            '  hashes = [\n    "h1:stub",\n  ]\n}\n',
            "utf-8",
        )
        stub_dir = root / "bin"
        stub_dir.mkdir()
        stub = stub_dir / "terraform"
        stub.write_text(TERRAFORM_STUB, "utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        yield root


def _run(
    root: Path,
    *,
    stub: bool = True,
    fail: str = "",
    mutate: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    calls = root / "calls.log"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("TF_") and not k.startswith("EREV_GATE_")
    }
    env.update(
        {
            "EREV_TF_VALIDATE_ROOT": str(root),
            "EREV_RUN_DIR": str(root / ".run"),
            "EREV_TF_VALIDATE_COMMAND": "make tf-validate",
            "STUB_CALLS": str(calls),
            "STUB_FAIL": fail,
            "STUB_MUTATE_FILE": str(mutate) if mutate else "",
            "TMPDIR": str(ROOT / ".run" / "tmp"),
            # The scratch root sits inside the repository; git must not discover the outer one.
            "GIT_CEILING_DIRECTORIES": str(root.parent),
        }
    )
    env.update(extra_env or {})
    env["EREV_TERRAFORM_BIN"] = (
        str(root / "bin" / "terraform") if stub else str(root / "bin" / "absent")
    )
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        # The execution context is the current directory: identity is sampled there.
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    recorded = calls.read_text("utf-8").splitlines() if calls.exists() else []
    return result, recorded


def _report(root: Path) -> dict[str, object]:
    report: dict[str, object] = json.loads(
        (root / ".run" / "reports" / "tf-validate" / "report.json").read_text("utf-8")
    )
    return report


def _git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(root.parent)}
    return subprocess.run(
        ["git", "-c", "user.email=p3c@local", "-c", "user.name=p3c", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _as_repository(root: Path) -> str:
    """Turn the scratch root into a repository with one commit; returns HEAD."""
    (root / ".gitignore").write_text(".run/\ncalls.log\nelsewhere/\nbin/\n", "utf-8")
    _git(root, "init", "-q", ".")
    _git(root, "add", ".gitignore", "deploy")
    _git(root, "commit", "-q", "-m", "scratch context")
    return _git(root, "rev-parse", "HEAD")


def test_tf_validate_provider_socket_works_with_long_inherited_tmpdir(scratch: Path) -> None:
    """A real Unix socket models the provider handshake inside Terraform's -chdir directory."""
    inherited = scratch / ("long-context-" * 12)
    inherited.mkdir()
    stub = scratch / "bin" / "terraform"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os, socket, sys\n"
        "if 'version' in sys.argv:\n"
        "    print(json.dumps({'terraform_version': '9.9.9-stub'}))\n"
        "elif 'validate' in sys.argv:\n"
        "    directories = [a.split('=', 1)[1] for a in sys.argv if a.startswith('-chdir=')]\n"
        "    directory = directories[0]\n"
        "    os.chdir(directory)\n"
        "    address = os.path.join(os.environ['TMPDIR'], 'plugin-socket-regression')\n"
        "    with socket.socket(socket.AF_UNIX) as sock:\n"
        "        sock.bind(address)\n"
        "    os.unlink(address)\n",
        encoding="utf-8",
    )
    result, _ = _run(scratch, extra_env={"TMPDIR": str(inherited)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(scratch)["result"] == "validated"


def test_tf_validate_report_is_usable_gate_evidence(scratch: Path) -> None:
    # P1 candidate 8 (Q-13): under the wrapper the inner report must pass usable_evidence, on every
    # path, or the wrapper FAILs {stage: report}. Same predicate, ported; captured = the report's
    # own identity here (a scratch without git: "nogit" on both sides).
    cases: dict[str, dict[str, object]] = {}
    _, _ = _run(scratch)
    cases["validated"] = _report(scratch)
    _, _ = _run(scratch, stub=False)
    cases["skipped-not-installed"] = _report(scratch)
    _, _ = _run(scratch, fail="fmt")
    cases["fmt-failed"] = _report(scratch)
    _, _ = _run(scratch, mutate=scratch / "deploy" / "terraform" / "gcp" / "versions.tf")
    cases["source-changed"] = _report(scratch)

    for name, report in cases.items():
        assert report["result"] == name, name
        assert all(key in report for key in REPORT_KEYS), name
        assert report["target"] == "tf-validate", name
        assert isinstance(report["exit_code"], int) and isinstance(report["counts"], dict), name
        assert isinstance(report["failures"], list) and isinstance(report["worktree_dirty"], bool)
        assert has_population(report["counts"]), name  # type: ignore[arg-type]
        assert usable_evidence(report, "tf-validate", str(report["build_sha"])) is None, name
        assert usable_evidence(report, "tf-validate", "0" * 40) is not None, name  # identity
        stages = report["counts"]["stages"]  # type: ignore[index]
        assert set(stages) >= {"init", "fmt", "validate"}, name
    # The skipped path is a populated, classifiable record, not an empty one.
    skipped = cases["skipped-not-installed"]
    assert skipped["counts"]["stages"] == {  # type: ignore[index]
        "init": "skipped",
        "fmt": "skipped",
        "validate": "skipped",
    }
    assert skipped["exit_code"] == 0 and skipped["failures"] == []
    assert cases["fmt-failed"]["counts"]["stages"] == {  # type: ignore[index]
        "init": "pass",
        "fmt": "fail",
        "validate": "not-run",
    }
    assert cases["validated"]["counts"]["stages"] == {  # type: ignore[index]
        "init": "pass",
        "fmt": "pass",
        "validate": "pass",
    }


def test_tf_validate_writes_report_in_gate_context(scratch: Path) -> None:
    # Under the GATE-BIND-1 wrapper EREV_GATE_CONTEXT names the immutable execution context: the
    # report must land in <context>/.run/reports/tf-validate/ (where the wrapper reads it, whatever
    # EREV_RUN_DIR says) and build_sha must be that context's HEAD.
    head = _as_repository(scratch)
    decoy = scratch / "elsewhere"
    for stub in (True, False):
        result, _ = _run(
            scratch,
            stub=stub,
            extra_env={"EREV_GATE_CONTEXT": str(scratch), "EREV_RUN_DIR": str(decoy)},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        report_path = scratch / ".run" / "reports" / "tf-validate" / "report.json"
        assert report_path.is_file(), "the report is written in the execution context"
        assert not (decoy / "reports").exists(), "EREV_RUN_DIR does not divert the wrapped report"
        report = json.loads(report_path.read_text("utf-8"))
        assert report["build_sha"] == head
        assert report["build_sha_end"] == head
        assert report["worktree_dirty"] is False
        assert report["execution_root"] == str(scratch)
        assert report["module_root"] == str(scratch)
        assert usable_evidence(report, "tf-validate", head) is None
        assert report["result"] == ("validated" if stub else "skipped-not-installed")
        report_path.unlink()


def _foreign_module(root: Path) -> Path:
    """A second module tree, marked FOREIGN, outside the execution context."""
    foreign = root.parent / f"{root.name}-foreign"
    tf_dir = foreign / "deploy" / "terraform" / "gcp"
    tf_dir.mkdir(parents=True)
    (tf_dir / "versions.tf").write_text(
        '# FOREIGN_SOURCE_B\nterraform {\n  required_version = ">= 1.6"\n}\n', "utf-8"
    )
    return foreign


def test_tf_validate_rejects_foreign_module_root_under_gate_context(scratch: Path) -> None:
    # P3c-IF1: under the wrapper an EREV_TF_VALIDATE_ROOT that is not the captured context is
    # refused before any terraform call; the report is bound to the context, names the rejected
    # override, fails closed ({stage: source}) and validates nothing.
    head = _as_repository(scratch)
    foreign = _foreign_module(scratch)
    try:
        result, calls = _run(
            scratch,
            extra_env={"EREV_GATE_CONTEXT": str(scratch), "EREV_TF_VALIDATE_ROOT": str(foreign)},
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert result.stdout.splitlines()[-1].startswith("FAIL tf-validate: EREV_TF_VALIDATE_ROOT=")
        assert "does not resolve to the execution context" in result.stdout
        assert calls == [], "no terraform subcommand ran against the foreign module"
        report = _report(scratch)
        assert report["result"] == "foreign-module-root"
        assert report["exit_code"] == 1
        assert report["failures"] == [{"stage": "source", "exit_code": 1}]
        assert report["build_sha"] == head and report["execution_root"] == str(scratch)
        assert report["module_root"] == str(scratch.resolve())
        assert report["module_root_override"] == str(foreign)
        assert report["module_root_rejected"] is True
        assert report["counts"]["stages"] == {  # type: ignore[index]
            "source": "fail",
            "init": "skipped",
            "fmt": "skipped",
            "validate": "skipped",
        }
        assert not (foreign / ".run").exists()
        # Still a well-formed DG-MK-00g record (the wrapper reads it and FAILs on exit_code 1).
        assert usable_evidence(report, "tf-validate", head) is None
    finally:
        shutil.rmtree(foreign, ignore_errors=True)


def test_tf_validate_accepts_matching_override_under_gate_context(scratch: Path) -> None:
    # An override that resolves to the context itself is the ordinary case: validated normally.
    head = _as_repository(scratch)
    result, calls = _run(
        scratch,
        extra_env={"EREV_GATE_CONTEXT": str(scratch), "EREV_TF_VALIDATE_ROOT": str(scratch)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    subcommands = [next(arg for arg in call.split() if not arg.startswith("-")) for call in calls]
    assert subcommands == ["version", "init", "fmt", "validate"]
    report = _report(scratch)
    assert report["result"] == "validated"
    assert report["build_sha"] == head
    assert report["module_root"] == str(scratch.resolve())
    assert report["module_root_override"] == str(scratch)
    assert report["module_root_rejected"] is False
    assert usable_evidence(report, "tf-validate", head) is None


def test_tf_validate_override_is_test_only_without_gate_context(scratch: Path) -> None:
    # Without the wrapper the scratch override serves isolated tests (EREV_ENV=test, the ordinary
    # positive path of every test here); under any other EREV_ENV it is refused the same way.
    result, calls = _run(scratch, extra_env={"EREV_ENV": "dev"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "is a test-only override" in result.stdout.splitlines()[-1]
    assert calls == []
    # The report goes to the script's own run directory in this case (module root = the script's
    # repository), so read it from EREV_RUN_DIR, which the run passed explicitly.
    report = json.loads(
        (scratch / ".run" / "reports" / "tf-validate" / "report.json").read_text("utf-8")
    )
    assert report["result"] == "foreign-module-root"
    assert report["module_root_rejected"] is True
    assert report["failures"] == [{"stage": "source", "exit_code": 1}]
    # The positive path: EREV_ENV=test (inherited from pytest) keeps the override.
    result, calls = _run(scratch, extra_env={"EREV_ENV": "test"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(scratch)["module_root_rejected"] is False


def test_tf_validate_script_parses() -> None:
    # DEP-5 test_scripts_parse (tf_validate part): bash -n succeeds; the script is executable.
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


def test_tf_validate_rules() -> None:
    # DG-MK-tf-validate: init -backend=false -input=false, fmt -check -recursive, validate; the
    # plugin cache under .run/; skipped-not-installed without Terraform; no state-changing or
    # credentialed subcommand anywhere in the script (DG-FORBID-07).
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"init -backend=false -input=false", text)
    assert re.search(r"fmt -check -recursive", text)
    assert re.search(r'"\$TERRAFORM" -chdir="\$ROOT/\$TF_DIR" validate', text)
    assert "-chdir=" in text and "deploy/terraform/gcp" in text
    assert "terraform-plugin-cache" in text
    assert "skipped-not-installed" in text
    assert "provider download failed; supervisor verification needed" in text
    # Provenance binding: start and end samples of HEAD, dirty state, input and lock hashes.
    for token in (
        "sample_start",
        "sample_end",
        "SOURCE_SHA_START",
        "SOURCE_SHA_END",
        "LOCK_SHA_START",
        "LOCK_SHA_END",
        "source-changed",
        '"start_end_bound"',
        "GATE-BIND-1",
        # DG-MK-00g shape under the wrapper (P1 Q-13): execution-context identity and report path,
        # skipped stages populated.
        'EXEC_ROOT="${EREV_GATE_CONTEXT:-$PWD}"',
        'git -C "$EXEC_ROOT" rev-parse HEAD',
        'REPORT_DIR="$EXEC_ROOT/.run/reports/$TARGET"',
        'STAGES_SKIPPED="init fmt validate"',
        # P3c-IF1: the module root is the context under the wrapper; a foreign override fails
        # closed before any terraform call, and the override is test-only otherwise.
        'MODULE_ROOT_OVERRIDE="${EREV_TF_VALIDATE_ROOT:-}"',
        'ROOT="$CONTEXT_REAL"',
        'fail "source" 1 "foreign-module-root"',
        '"${EREV_ENV:-}" == "test"',
    ):
        assert token in text, token
    # The rejection precedes the first terraform invocation in the script text.
    assert text.index('fail "source" 1 "foreign-module-root"') < text.index('"$TERRAFORM" version')
    for word in ("plan", "apply", "destroy", "console", "login", "gcloud"):
        assert re.search(rf"\b{word}\b", text) is None, word
    # Every terraform invocation runs one of the four read-only subcommands; `import` occurs only
    # as a Python import in the report writer.
    invocations = [
        line
        for line in text.splitlines()
        if '"$TERRAFORM"' in line and "command -v" not in line  # the presence probe runs nothing
    ]
    assert len(invocations) >= 4
    for line in invocations:
        match = re.search(r'"\$TERRAFORM"((?:\s+-\S+)*)\s+([a-z]+)', line)
        assert match is not None, line
        assert match.group(2) in {"version", "init", "fmt", "validate"}, line
    # DG-FORBID-04 forbids host-global temporary paths, not the required .run/tmp directory.
    assert re.search(r'(?<![A-Za-z0-9_.])/(?:private/)?tmp(?:/|["\s])', text) is None
    assert "credentials" not in text.lower()
    # The report is written through the environment, never by interpolating values into code.
    assert "REPORT_TF_VERSION=" in text and "json.dump(report" in text


def test_makefile_tf_validate_target() -> None:
    # DEP-5 test_makefile_supervisor_targets (tf-validate part; DG-MK-00h): phony, banner first,
    # no $(MAKE) so `make -n` executes nothing. Under GATE-BIND-1 (DG-MK-00i; lane P1 merge cdcf372)
    # the supervisor target runs through the execution-context wrapper and the deploy lane's script
    # is called by the inner `tf-validate-gate` recipe, so the script assertion reads that recipe.
    text = MAKEFILE.read_text(encoding="utf-8")
    phony = {
        name
        for line in text.splitlines()
        if line.startswith(".PHONY:")
        for name in line.split()[1:]
    }
    assert "tf-validate" in phony
    recipe = text.split("\ntf-validate:\n", 1)[1].split("\n\n", 1)[0]
    lines = [line.strip() for line in recipe.splitlines() if line.strip()]
    assert lines[0] == '@echo "SUPERVISOR TARGET tf-validate (D-48a)"'
    assert any("scripts/gate_context.sh tf-validate" in line for line in lines)
    inner = text.split("\ntf-validate-gate:\n", 1)[1].split("\n\n", 1)[0]
    inner_lines = [line.strip() for line in inner.splitlines() if line.strip()]
    assert any("scripts/tf_validate.sh" in line for line in inner_lines)
    assert "$(MAKE)" not in recipe and "$(MAKE)" not in inner
    for block in (recipe, inner):
        assert re.search(r"\bterraform\b", block) is None, "the script owns every terraform call"


def test_tf_validate_skipped_not_installed(scratch: Path) -> None:
    # (1) without Terraform: skipped-not-installed report, supervisor line, exit 0, no call made.
    result, calls = _run(scratch, stub=False)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout.splitlines()
    assert "SUPERVISOR VERIFICATION NEEDED: Terraform not installed" in out
    assert out[-1] == "OK tf-validate (skipped-not-installed)"
    assert calls == []
    report = _report(scratch)
    assert report["result"] == "skipped-not-installed"
    assert report["exit_code"] == 0
    assert report["target"] == "tf-validate"
    assert report["command"] == "make tf-validate"
    assert report["failures"] == []
    assert report["build_sha"] == "nogit"  # the scratch root is not a repository
    for key in ("worktree_dirty", "started_at", "finished_at", "counts"):
        assert key in report


def test_tf_validate_runs_init_fmt_validate_in_order(scratch: Path) -> None:
    # (2) to (5): the three subcommands in order, plugin cache under the run dir, provider versions
    # read from the lock file, OK line last.
    result, calls = _run(scratch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK tf-validate"
    subcommands = [next(arg for arg in call.split() if not arg.startswith("-")) for call in calls]
    assert subcommands == ["version", "init", "fmt", "validate"]
    init = calls[1].split()
    assert "-backend=false" in init and "-input=false" in init
    assert any(arg.startswith("-chdir=") and arg.endswith("deploy/terraform/gcp") for arg in init)
    fmt = calls[2].split()
    assert "-check" in fmt and "-recursive" in fmt
    for call in calls:
        for word in ("plan", "apply", "import", "destroy"):
            assert word not in call.split(), call
    report = _report(scratch)
    assert report["result"] == "validated"
    assert report["exit_code"] == 0
    assert report["terraform_version"] == "9.9.9-stub"
    assert report["providers"] == {
        "registry.terraform.io/hashicorp/google": {"version": "6.50.0", "constraints": "~> 6.0"}
    }
    assert report["counts"] == {
        "tf_files": 1,
        "providers": 1,
        "stages": {"init": "pass", "fmt": "pass", "validate": "pass"},
    }
    assert str(report["plugin_cache_dir"]).startswith(str(scratch / ".run"))
    assert (scratch / ".run" / "terraform-plugin-cache").is_dir()
    # Provenance: identity and input hashes sampled before init and after validate agree
    # (start/end-bound; immutable execution is pending GATE-BIND-1).
    assert report["start_end_bound"] is True
    assert "source_bound" not in report
    assert report["build_sha_end"] == report["build_sha"]
    assert report["worktree_dirty_end"] == report["worktree_dirty"]
    assert re.fullmatch(r"[0-9a-f]{64}", str(report["source_sha256_start"]))
    assert report["source_sha256_end"] == report["source_sha256_start"]
    assert re.fullmatch(r"[0-9a-f]{64}", str(report["lock_sha256"]))


def test_tf_validate_detects_source_change(scratch: Path) -> None:
    # A module file that changes between the start sample and the end sample makes the run
    # unattributable: result source-changed, exit 1, start_end_bound false, both hashes recorded.
    target = scratch / "deploy" / "terraform" / "gcp" / "versions.tf"
    result, calls = _run(scratch, mutate=target)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith(
        "FAIL tf-validate: source changed during validation"
    )
    subcommands = [next(arg for arg in call.split() if not arg.startswith("-")) for call in calls]
    assert subcommands == ["version", "init", "fmt", "validate"]  # every stage ran
    report = _report(scratch)
    assert report["result"] == "source-changed"
    assert report["exit_code"] == 1
    assert report["start_end_bound"] is False
    assert report["source_sha256_end"] != report["source_sha256_start"]
    assert report["failures"] == [{"stage": "provenance", "exit_code": 1}]
    assert report["counts"]["stages"] == {  # type: ignore[index]
        "init": "pass",
        "fmt": "pass",
        "validate": "pass",
        "provenance": "fail",
    }


@pytest.mark.parametrize(
    ("stage", "result_name", "reason"),
    [
        (
            "init",
            "provider-download-failed",
            "provider download failed; supervisor verification needed",
        ),
        ("fmt", "fmt-failed", "terraform fmt -check found unformatted files"),
        ("validate", "validate-failed", "terraform validate failed"),
    ],
)
def test_tf_validate_failures_exit_1(
    scratch: Path, stage: str, result_name: str, reason: str
) -> None:
    result, calls = _run(scratch, fail=stage)
    assert result.returncode == 1, result.stdout + result.stderr
    last = result.stdout.splitlines()[-1]
    assert last.startswith(f"FAIL tf-validate: {reason}")
    subcommands = [next(arg for arg in call.split() if not arg.startswith("-")) for call in calls]
    expected = ["version", "init", "fmt", "validate"]
    assert subcommands == expected[: expected.index(stage) + 1]  # stops at the failing stage
    report = _report(scratch)
    assert report["result"] == result_name
    assert report["exit_code"] == 1
    assert report["failures"] == [{"stage": stage, "exit_code": 1}]
    assert report["counts"]["stages"][stage] == "fail"  # type: ignore[index]


# ---- DEP-5 completion (lane P6; BUILD_SPEC §26 DEP-5 acceptance; D-98 148 A2) -----------------
# The six supervisor scripts are exercised only against stand-in `uv`, `npm` and `docker` binaries
# and a scratch HTTP server in a scratch root; no dependency audit, image pull, compose project or
# ZAP scan is ever executed (DG-FORBID-12). The keep-up contract between compose_verify.sh and
# zap_baseline.sh is a rule: one source of the bring-up steps.

TMP_RULE = re.compile(
    r"(?<![\w.])/" + r"tmp\b"
)  # tests/architecture/test_forbidden_patterns.py "tmp"
SIX_TARGETS = {
    "audit-deps": "scripts/audit_deps.sh",
    "zap-baseline": "scripts/zap_baseline.sh",
    "docker-build": "scripts/docker_build.sh",
    "compose-verify": "scripts/compose_verify.sh",
    "tf-validate": "scripts/tf_validate.sh",
    "backup": "scripts/backup.sh",
}
UV_STUB = """#!/usr/bin/env bash
# uv stand-in: `export` copies the requirements file the test names (STUB_UV_EXPORT, in uv's own
# shape: `name==version[ ; marker] \\` and an indented `--hash=` line); `tool run` prints the
# pip-audit document the test names.
echo "uv $*" >>"$STUB_CALLS"
case "$1" in
  export)
    out=""; prev=""
    for arg in "$@"; do if [[ "$prev" == "--output-file" ]]; then out="$arg"; fi; prev="$arg"; done
    cp "$STUB_UV_EXPORT" "$out"
    exit "${STUB_UV_EXPORT_RC:-0}" ;;
  tool)
    cat "$STUB_PIP_AUDIT_JSON"
    exit "${STUB_PIP_AUDIT_RC:-0}" ;;
  *) exit 0 ;;
esac
"""
NPM_STUB = """#!/usr/bin/env bash
echo "npm $*" >>"$STUB_CALLS"
cat "$STUB_NPM_AUDIT_JSON"
exit "${STUB_NPM_AUDIT_RC:-0}"
"""
DOCKER_STUB = """#!/usr/bin/env bash
# docker stand-in for compose_verify.sh / zap_baseline.sh: records every call; `info` per
# STUB_DOCKER_INFO_RC; `compose … ps --format json` reports the worker health per
# STUB_WORKER_HEALTH; `run` (the ZAP image) writes STUB_ZAP_JSON into the mounted work directory
# and exits per STUB_ZAP_RC; `compose … build`, `up` and `down` exit per STUB_COMPOSE_BUILD_RC,
# STUB_COMPOSE_UP_RC and STUB_COMPOSE_DOWN_RC;
# `image inspect` prints a fixed digest. Nothing is built, pulled, started or scanned. Every
# `compose` call also records the three CFG-26 key variables it was handed (STUB_KEYS) and the
# three database passwords (STUB_PASSWORDS). `compose … build` copies the release manifest it
# finds at the build root to STUB_MANIFEST_AT_BUILD, and `run` (the scan) to STUB_MANIFEST_AT_SCAN
# - an empty file with the suffix `.absent` when none lies there.
manifest_at() {
  [[ -n "$1" ]] || return 0
  rm -f "$1" "$1.absent"
  cp "$EREV_COMPOSE_VERIFY_ROOT/release-manifest.json" "$1" 2>/dev/null || : >"$1.absent"
}
echo "docker $*" >>"$STUB_CALLS"
if [[ "$1" == "compose" && -n "${STUB_KEYS:-}" ]]; then
  first="${EREV_COMPOSE_ENCRYPTION_KEY:-}"
  second="${EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY:-}"
  third="${EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY:-}"
  echo "$first $second $third" >>"$STUB_KEYS"
fi
if [[ "$1" == "compose" && -n "${STUB_PASSWORDS:-}" ]]; then
  first="${EREV_COMPOSE_POSTGRES_PASSWORD:-}"
  second="${EREV_COMPOSE_OWNER_PASSWORD:-}"
  third="${EREV_COMPOSE_APP_PASSWORD:-}"
  echo "$first $second $third" >>"$STUB_PASSWORDS"
fi
case "$1" in
  info) exit "${STUB_DOCKER_INFO_RC:-0}" ;;
  compose)
    sub=""
    for arg in "$@"; do case "$arg" in build|up|down|ps) sub="$arg"; break ;; esac; done
    if [[ "$sub" == "ps" ]]; then
      health="${STUB_WORKER_HEALTH:-healthy}"
      printf '{"Service":"worker","State":"running","Health":"%s"}\\n' "$health"
      printf '{"Service":"api","State":"running","Health":"healthy"}\\n'
    fi
    if [[ "$sub" == "build" ]]; then
      manifest_at "${STUB_MANIFEST_AT_BUILD:-}"
      exit "${STUB_COMPOSE_BUILD_RC:-0}"
    fi
    if [[ "$sub" == "up" ]]; then exit "${STUB_COMPOSE_UP_RC:-0}"; fi
    if [[ "$sub" == "down" ]]; then exit "${STUB_COMPOSE_DOWN_RC:-0}"; fi
    exit 0 ;;
  run)
    manifest_at "${STUB_MANIFEST_AT_SCAN:-}"
    mount=""; prev=""
    for arg in "$@"; do if [[ "$prev" == "-v" ]]; then mount="${arg%%:*}"; fi; prev="$arg"; done
    if [[ -n "$mount" && -n "${STUB_ZAP_JSON:-}" ]]; then
      cp "$STUB_ZAP_JSON" "$mount/zap.json" && : >"$mount/zap.html"
    fi
    exit "${STUB_ZAP_RC:-0}" ;;
  image) echo "ghcr.io/zaproxy/zaproxy@sha256:stubdigest"; exit 0 ;;
  push|login) echo "forbidden: $1" >&2; exit 99 ;;
  *) exit 0 ;;
esac
"""
# The export pins third-party distributions only (`--no-emit-project`: the project itself is not
# a published distribution), and a pip-audit result must name exactly the pinned set.
CLEAN_PIP_AUDIT = {
    "dependencies": [{"name": "alembic", "version": "1.20.0", "vulns": []}],
    "fixes": [],
}
VULN_PIP_AUDIT = {
    "dependencies": [
        {
            "name": "requests",
            "version": "2.0.0",
            "vulns": [{"id": "PYSEC-STUB-1", "fix_versions": ["2.1.0"]}],
        }
    ],
    "fixes": [],
}


def _uv_export(scratch: Path, name: str, *requirements: str) -> Path:
    """A requirements file in uv export's shape under ``scratch``: a header comment, then each of
    ``requirements`` (``name==version`` with an optional `` ; marker``) continued onto one
    ``--hash`` line; a requirement starting with ``-`` or lacking ``==`` is written verbatim."""
    lines = ["# This file was autogenerated by uv via the following command:", "#    uv export"]
    for requirement in requirements:
        if requirement.startswith("-") or "==" not in requirement:
            lines.append(requirement)
        else:
            lines += [
                f"{requirement} \\",
                "    --hash=sha256:" + "0" * 64,
                "    # via erev-backend",
            ]
    path = scratch / f"{name}.txt"
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path


def _npm_audit(**severities: int) -> dict[str, object]:
    counts = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, **severities}
    counts["total"] = sum(counts.values())
    entries = {
        f"pkg-{severity}-{index}": {
            "name": f"pkg-{severity}-{index}",
            "severity": severity,
            "via": [],
        }
        for severity, number in severities.items()
        for index in range(number)
    }
    return {
        "auditReportVersion": 2,
        "vulnerabilities": entries,
        "metadata": {"vulnerabilities": counts},
    }


def _zap_json(*riskcodes: int) -> dict[str, object]:
    return {
        "site": [
            {
                "@name": "http://host.docker.internal:8195",
                "alerts": [{"riskcode": str(r)} for r in riskcodes],
            }
        ]
    }


def _stub_binary(root: Path, name: str, text: str) -> Path:
    binary = root / "bin" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(text, "utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def _dep5_root(scratch: Path) -> Path:
    root = scratch / "dep5"
    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "deploy").mkdir()
    (root / "deploy" / "compose.yaml").write_text("services: {}\n", "utf-8")
    (root / "deploy" / "compose.env.example").write_text(
        "EREV_COMPOSE_POSTGRES_PASSWORD=\n", "utf-8"
    )
    return root


def _dep5_env(scratch: Path, root: Path, **extra: str) -> dict[str, str]:
    calls = scratch / "dep5-calls.log"
    calls.touch()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EREV_", "STUB_", "MAKE"))}
    env.update(
        {
            "EREV_ENV": "test",
            "EREV_RUN_DIR": str(root / ".run"),
            "STUB_CALLS": str(calls),
            "STUB_KEYS": str(scratch / "dep5-keys.log"),
            "STUB_PASSWORDS": str(scratch / "dep5-passwords.log"),
            "TMPDIR": str(ROOT / ".run" / "tmp"),
            "GIT_CEILING_DIRECTORIES": str(root.parent),
            "EREV_UV_BIN": str(_stub_binary(scratch, "uv", UV_STUB)),
            # The default export pins what CLEAN_PIP_AUDIT audits; a case names its own.
            "STUB_UV_EXPORT": str(_uv_export(scratch, "export-default", "alembic==1.20.0")),
            "EREV_NPM_BIN": str(_stub_binary(scratch, "npm", NPM_STUB)),
            "EREV_DOCKER_BIN": str(_stub_binary(scratch, "docker", DOCKER_STUB)),
            "EREV_AUDIT_DEPS_ROOT": str(root),
            "EREV_COMPOSE_VERIFY_ROOT": str(root),
            "EREV_ZAP_BASELINE_ROOT": str(root),
            # Isolation from other processes on this machine (DEPLOY-PORT-FLAKE-1): the port probe
            # targets two ephemeral ports of this test's own, never the published 8195 / 5436, and
            # the readiness budget is generous because the polls return on the first 200 / healthy
            # (only the two negative witnesses set a short budget, since they must expire).
            "EREV_COMPOSE_VERIFY_PORTS": " ".join(str(p) for p in _free_ports(2)),
            "EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS": "120",
        }
    )
    env.update(extra)
    return env


def _free_ports(count: int) -> list[int]:
    """``count`` free loopback ports (bind at 0, read, close; no ``socket`` import: DG-ARC-12)."""
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler) for _ in range(count)]
    try:
        return [int(server.server_address[1]) for server in servers]
    finally:
        for server in servers:
            server.server_close()


def _run_dep5(script: str, root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / script)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,  # a slow-but-correct run under load is never killed by the harness
    )


def _report_of(root: Path, target: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (root / ".run" / "reports" / target / "report.json").read_text("utf-8")
    )
    assert all(key in document for key in REPORT_KEYS), target
    assert has_population(document["counts"]), target
    assert usable_evidence(document, target, str(document["build_sha"])) is None, target
    return document


def _calls(scratch: Path) -> str:
    return (scratch / "dep5-calls.log").read_text("utf-8")


def _passwords_seen(scratch: Path) -> list[tuple[str, ...]]:
    """The three database passwords each ``docker compose`` call of the run was handed, in order;
    the log is emptied so the next run starts clean."""
    log = scratch / "dep5-passwords.log"
    seen = [tuple(line.split(" ")) for line in log.read_text("utf-8").splitlines()]
    log.write_text("", "utf-8")
    return seen


def _keys_seen(scratch: Path) -> list[tuple[str, ...]]:
    """The CFG-26 key variables each ``docker compose`` call of the run was handed, in order;
    the log is emptied so the next run starts clean."""
    log = scratch / "dep5-keys.log"
    seen = [tuple(line.split(" ")) for line in log.read_text("utf-8").splitlines()]
    log.write_text("", "utf-8")
    return seen


@contextmanager
def _scratch_http(
    csp: bool = True,
    ready: bool = True,
    port: int = 0,
    hits: dict[str, int] | None = None,
    polled: threading.Event | None = None,
) -> Iterator[str]:
    """A loopback HTTP server standing in for the compose web port: /api/v1/readyz and /.

    With ``port`` it also holds a busy port for the port-in-use case (no ``socket`` import:
    DG-ARC-12). ``hits`` (optional) counts the readyz requests, for the first-poll witness;
    ``polled`` (optional) is set once a readyz request has been answered - the bring-up is then in
    its readiness wait, after its ``up``.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path == "/api/v1/readyz":
                if hits is not None:
                    hits["readyz"] = hits.get("readyz", 0) + 1
                self.send_response(200 if ready else 503)
                self.end_headers()
                if polled is not None:
                    polled.set()
                return
            self.send_response(200)
            if csp:
                self.send_header("Content-Security-Policy", "default-src 'self'")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_makefile_supervisor_targets() -> None:
    # BUILD_SPEC DEP-5: each of the six targets exists, is .PHONY, prints its banner first and calls
    # its script (DG-MK-00h). Under GATE-BIND-1 the wrapped ones call it from <target>-gate (the
    # tf-validate shape); docker-build calls it directly. No recipe runs another make (rev 1.97:
    # docker-build's `make release-manifest EMBEDDED=1` step moved into its script, R-53 (4)).
    text = MAKEFILE.read_text(encoding="utf-8")
    phony = {
        name
        for line in text.splitlines()
        if line.startswith(".PHONY:")
        for name in line.split()[1:]
    }
    for target, script in SIX_TARGETS.items():
        assert target in phony, target
        assert f"\n{target}:\n" in text, target
        recipe = text.split(f"\n{target}:\n", 1)[1].split("\n\n", 1)[0]
        lines = [line.strip() for line in recipe.splitlines() if line.strip()]
        assert lines[0] == f'@echo "SUPERVISOR TARGET {target} (D-48a)"', target
        assert "$(MAKE)" not in recipe, target
        if any(f"scripts/gate_context.sh {target} " in line for line in lines):
            inner = text.split(f"\n{target}-gate:\n", 1)[1].split("\n\n", 1)[0]
            assert script in inner, target
        else:
            assert script in recipe, target


def test_scripts_parse() -> None:
    # BUILD_SPEC DEP-5: bash -n succeeds for every one of the six scripts; each is executable.
    for script in SIX_TARGETS.values():
        path = ROOT / script
        result = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, (script, result.stderr)
        assert path.stat().st_mode & stat.S_IXUSR, script
        assert path.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n"), script


def test_docker_and_compose_rules() -> None:
    # BUILD_SPEC DEP-5 (DG-MK-docker-build, DG-MK-compose-verify, DG-MK-zap-baseline).
    docker_build = (ROOT / "scripts" / "docker_build.sh").read_text(encoding="utf-8")
    assert "docker push" not in docker_build and "docker login" not in docker_build
    assert "image inspect" in docker_build  # records the image ids
    compose = (ROOT / "scripts" / "compose_verify.sh").read_text(encoding="utf-8")
    assert 'PROJECT="erev-verify"' in compose
    # every `docker compose` call site names the project: the helper carries -p "$PROJECT" and no
    # other compose invocation exists (the comment header restates the plan in prose)
    compose_calls = [
        line
        for line in compose.splitlines()
        if "compose " in line and not line.lstrip().startswith("#")
    ]
    assert compose_calls and all(
        '-p "$PROJECT"' in line for line in compose_calls if '"$DOCKER" compose' in line
    )
    assert (
        sum('"$DOCKER" compose' in line for line in compose_calls) == 1
    )  # one helper, one project
    assert 'PORTS_DEFAULT="8195 5436"' in compose  # the published ports (D-47), unchanged
    # the test-only port override is gated exactly like the root override (DEPLOY-PORT-FLAKE-1)
    assert 'PORTS_OVERRIDE="${EREV_COMPOSE_VERIFY_PORTS:-}"' in compose
    assert '"${EREV_ENV:-}" != "test"' in compose and "foreign-ports" in compose
    module = Path(__file__).read_text(encoding="utf-8")
    for published in ("8195", "5436"):  # no test binds a published port (needle split: this line)
        assert ("port=" + published) not in module
    assert "/api/v1/readyz" in compose and "TIMEOUT_SECONDS:-180" in compose
    assert "skipped-no-daemon" in compose and "Content-Security-Policy" in compose
    assert "down -v" in compose and "EREV_COMPOSE_VERIFY_KEEP_UP" in compose
    for word in ("plan", "apply", "push", "login"):
        assert re.search(rf"\b{word}\b", compose) is None, word
    zap = (ROOT / "scripts" / "zap_baseline.sh").read_text(encoding="utf-8")
    assert "skipped-no-daemon" in zap
    assert 'ZAP_IMAGE="ghcr.io/zaproxy/zaproxy:stable"' in zap
    assert 'zap-baseline.py -t "$ZAP_TARGET_URL" -J zap.json -r zap.html' in zap
    assert 'ZAP_TARGET_URL="http://host.docker.internal:8195/"' in zap
    assert 'PROJECT="erev-verify"' in zap
    # Single source of the bring-up (D-98 148 A2 (2)): zap_baseline.sh calls compose_verify.sh under
    # keep-up contract and never runs `compose build` or `compose up` itself; it owns the `down -v`.
    assert "EREV_COMPOSE_VERIFY_KEEP_UP=1" in zap and '"$COMPOSE_VERIFY"' in zap
    assert re.search(r'(?m)^[^#\n]*"\$DOCKER" compose\b[^\n]*\b(build|up)\b', zap) is None
    assert "compose()" not in zap  # no second bring-up helper
    assert "down -v" in zap
    for word in ("push", "login"):
        assert re.search(rf"\b{word}\b", zap) is None, word
    for text in (docker_build, compose, zap):
        assert re.search(TMP_RULE, text) is None  # DG-FORBID-04 (the architecture suite's regex)


def test_audit_deps_and_backup_rules() -> None:
    # BUILD_SPEC DEP-5 (DG-MK-audit-deps, DG-MK-backup).
    audit = (ROOT / "scripts" / "audit_deps.sh").read_text(encoding="utf-8")
    assert (
        re.search(r"uv\b.*export .*--no-dev --frozen", audit)
        or 'export --project "$ROOT/backend" --no-dev --frozen' in audit
    )
    assert "pip-audit --strict --require-hashes" in audit
    # Rev 1.81 (first run with the real tools, lane OPS): the audited set is the runtime set the
    # images install — every extra, without the project itself — and pip-audit reads the pinned,
    # hashed file without pip (no virtual environment: its copied interpreter cannot start under a
    # uv-managed Python on macOS), so every `--extra` a Dockerfile syncs is inside the audit.
    assert (
        'export --project "$ROOT/backend" --no-dev --frozen --no-emit-project --all-extras' in audit
    )
    assert "pip-audit --strict --require-hashes --disable-pip -r" in audit
    for dockerfile in ("api.Dockerfile", "worker.Dockerfile"):
        image = (ROOT / "deploy" / "docker" / dockerfile).read_text(encoding="utf-8")
        syncs = re.findall(r"^RUN uv sync (.*)$", image, re.MULTILINE)
        assert syncs and all("--frozen" in sync and "--no-dev" in sync for sync in syncs), (
            dockerfile
        )
        assert {extra for sync in syncs for extra in re.findall(r"--extra (\S+)", sync)} == {"gcp"}
        assert not any("--group" in sync or "--all-groups" in sync for sync in syncs), dockerfile
    assert "audit --omit=dev --json" in audit and '--prefix "$ROOT/frontend"' in audit
    assert "skipped-not-installed" in audit and "output_sha256" in audit
    assert re.search(TMP_RULE, audit) is None
    backup = (ROOT / "scripts" / "backup.sh").read_text(encoding="utf-8")
    assert 'env["PGPASSWORD"]' in backup and re.search(r"--dbname\W", backup) is None
    assert "chmod 600" in backup
    assert not re.search(r"echo\s+\"?\$\{?EREV_(DB|RESTORE|BACKUP)_[A-Z_]*URL", backup)
    assert not re.search(r"echo\s+\"?\$\{?(ENCRYPTION_KEY|AUDIT_KEY|SECURITY_KEY)", backup)


# BUILD_SPEC §26 DEP-5 acceptance: "PROGRESS.md lists `SUPERVISOR VERIFICATION NEEDED: make
# audit-deps`, `make zap-baseline`, `make docker-build`, `make compose-verify`, `make tf-validate`,
# `make backup`". Each lane writes the line for its own target; all six are on the branch.


def test_progress_lists_the_supervisor_targets() -> None:
    progress = (ROOT / "PROGRESS.md").read_text(encoding="utf-8")
    for target in SIX_TARGETS:
        assert f"SUPERVISOR VERIFICATION NEEDED: make {target}" in progress, target


def test_audit_deps_reports_counts_digest_and_verdict(scratch: Path) -> None:
    root = _dep5_root(scratch)
    clean, vuln = scratch / "pip-clean.json", scratch / "pip-vuln.json"
    clean.write_text(json.dumps(CLEAN_PIP_AUDIT), "utf-8")
    vuln.write_text(json.dumps(VULN_PIP_AUDIT), "utf-8")
    npm_clean, npm_high = scratch / "npm-clean.json", scratch / "npm-high.json"
    npm_clean.write_text(json.dumps(_npm_audit(moderate=2)), "utf-8")
    npm_high.write_text(json.dumps(_npm_audit(high=1, critical=1)), "utf-8")
    # clean: exit 0, digest over the two captured outputs in order, stages all pass; npm exits 1 for
    # its two moderate advisories (npm's semantics), which the low/moderate policy accepts
    env = _dep5_env(
        scratch,
        root,
        STUB_PIP_AUDIT_JSON=str(clean),
        STUB_NPM_AUDIT_JSON=str(npm_clean),
        STUB_NPM_AUDIT_RC="1",
    )
    done = _run_dep5("scripts/audit_deps.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1] == "OK audit-deps"
    report = _report_of(root, "audit-deps")
    assert report["result"] == "clean" and report["exit_code"] == 0
    assert report["counts"]["stages"] == {
        "export": "pass",
        "pip-audit": "pass",
        "npm-audit": "pass",
        "digest": "pass",
    }
    assert report["counts"]["python_vulnerabilities"] == 0
    assert (
        report["counts"]["npm_advisories"]["moderate"] == 2
        and report["counts"]["npm_high_or_critical"] == 0
    )
    captured = root / ".run" / "reports" / "audit-deps"
    expected = hashlib.sha256(
        (captured / "pip-audit.json").read_bytes() + (captured / "npm-audit.json").read_bytes()
    ).hexdigest()
    assert report["output_sha256"] == expected
    assert report["scanners"] == {
        "pip_audit": {"exit_code": 0, "dependencies_audited": 1, "accepted": True},
        "npm_audit": {"exit_code": 1, "total": 2, "accepted": True},
    }
    calls = _calls(scratch)
    assert (
        f"uv export --project {root}/backend --no-dev --frozen --no-emit-project --all-extras "
        f"--output-file {root}/.run/tmp/audit-requirements.txt" in calls
    )
    assert (
        "uv tool run pip-audit --strict --require-hashes --disable-pip "
        f"-r {captured}/audited-requirements.txt --format json" in calls
    )
    assert report["requirements"] == {
        "file": "audited-requirements.txt",
        "pinned": 1,
        "markers_removed": 0,
        "sha256": hashlib.sha256((captured / "audited-requirements.txt").read_bytes()).hexdigest(),
    }
    assert f"npm --prefix {root}/frontend audit --omit=dev --json" in calls
    # a python vulnerability: exit 1, result vulnerabilities-found, counts populated
    env = _dep5_env(
        scratch,
        root,
        STUB_UV_EXPORT=str(_uv_export(scratch, "export-requests", "requests==2.0.0")),
        STUB_PIP_AUDIT_JSON=str(vuln),
        STUB_PIP_AUDIT_RC="1",
        STUB_NPM_AUDIT_JSON=str(npm_clean),
        STUB_NPM_AUDIT_RC="1",
    )
    done = _run_dep5("scripts/audit_deps.sh", root, env)
    assert done.returncode == 1 and done.stdout.splitlines()[-1].startswith(
        "FAIL audit-deps: 1 python vulnerabilities"
    )
    report = _report_of(root, "audit-deps")
    assert (
        report["result"] == "vulnerabilities-found"
        and report["counts"]["python_vulnerabilities"] == 1
    )
    # npm high/critical only: exit 1
    env = _dep5_env(
        scratch,
        root,
        STUB_PIP_AUDIT_JSON=str(clean),
        STUB_NPM_AUDIT_JSON=str(npm_high),
        STUB_NPM_AUDIT_RC="1",
    )
    done = _run_dep5("scripts/audit_deps.sh", root, env)
    assert done.returncode == 1 and "2 npm high or critical advisories" in done.stdout
    # uv absent: skipped-not-installed, exit 0, populated skipped stages, nothing called
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    env = _dep5_env(
        scratch,
        root,
        STUB_PIP_AUDIT_JSON=str(clean),
        STUB_NPM_AUDIT_JSON=str(npm_clean),
        STUB_NPM_AUDIT_RC="1",
        EREV_UV_BIN=str(scratch / "bin" / "absent"),
    )
    done = _run_dep5("scripts/audit_deps.sh", root, env)
    assert (
        done.returncode == 0
        and "SUPERVISOR VERIFICATION NEEDED: uv or npm not installed" in done.stdout
    )
    report = _report_of(root, "audit-deps")
    assert report["result"] == "skipped-not-installed" and set(
        report["counts"]["stages"].values()
    ) == {"skipped"}
    assert _calls(scratch) == ""
    # a pip-audit that produces no JSON is a tool failure, not a verdict
    broken = scratch / "pip-broken.json"
    broken.write_text("not json", "utf-8")
    env = _dep5_env(
        scratch,
        root,
        STUB_PIP_AUDIT_JSON=str(broken),
        STUB_PIP_AUDIT_RC="2",
        STUB_NPM_AUDIT_JSON=str(npm_clean),
        STUB_NPM_AUDIT_RC="1",
    )
    done = _run_dep5("scripts/audit_deps.sh", root, env)
    assert (
        done.returncode == 1
        and "FAIL audit-deps: pip-audit produced no JSON (exit 2" in done.stdout
    )
    assert _report_of(root, "audit-deps")["counts"]["stages"]["pip-audit"] == "fail"


def test_audit_deps_rejects_error_incomplete_and_inconsistent_results(scratch: Path) -> None:
    # Codex production-20260922-0105 §6 (P6-DEP5-AUDIT-1): a parseable error object, an incomplete
    # result and a disagreement between the scanner's exit code and its result are tool failures
    # with their own results, never `clean`; the low/moderate npm policy is not a blanket rejection.
    root = _dep5_root(scratch)
    pip_clean, npm_clean = scratch / "pip-clean.json", scratch / "npm-clean.json"
    pip_clean.write_text(json.dumps(CLEAN_PIP_AUDIT), "utf-8")
    npm_clean.write_text(json.dumps(_npm_audit()), "utf-8")
    good_npm = {"STUB_NPM_AUDIT_JSON": str(npm_clean), "STUB_NPM_AUDIT_RC": "0"}
    good_pip = {"STUB_PIP_AUDIT_JSON": str(pip_clean), "STUB_PIP_AUDIT_RC": "0"}
    requests_export = _uv_export(scratch, "export-requests", "requests==2.0.0")

    def run(
        name: str, document: object, **extra: str
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        path = scratch / f"{name}.json"
        path.write_text(json.dumps(document), "utf-8")
        pip_side = name.startswith("pip")
        key = "STUB_PIP_AUDIT_JSON" if pip_side else "STUB_NPM_AUDIT_JSON"
        if document is VULN_PIP_AUDIT:  # the export pins what that result audits
            extra = {"STUB_UV_EXPORT": str(requests_export), **extra}
        env = _dep5_env(
            scratch, root, **(good_npm if pip_side else good_pip), **{key: str(path)}, **extra
        )
        done = _run_dep5("scripts/audit_deps.sh", root, env)
        return done, _report_of(root, "audit-deps")

    # error objects (pip-audit and npm each): invalid, exit 1, the stage fails, not accepted
    done, report = run("pip-error", {"error": "resolver failure"}, STUB_PIP_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    assert "FAIL audit-deps: pip-audit result rejected: error object" in done.stdout
    assert (
        report["counts"]["stages"]["pip-audit"] == "fail"
        and report["scanners"]["pip_audit"]["accepted"] is False
    )
    assert report["counts"]["python_vulnerabilities"] == 0 and report["result"] != "clean"
    npm_error = {
        "error": {
            "code": "ENOLOCK",
            "summary": "This command requires an existing lockfile.",
            "detail": "",
        }
    }
    done, report = run("npm-error", npm_error, STUB_NPM_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "npm-audit-invalid"
    assert "npm audit result rejected: error object" in done.stdout
    assert (
        report["counts"]["stages"]["npm-audit"] == "fail"
        and report["scanners"]["npm_audit"]["accepted"] is False
    )
    # incomplete results: a skipped dependency (pip-audit --strict) and a missing severity (npm)
    skipped = {
        "dependencies": [{"name": "alembic", "skip_reason": "not on PyPI"}],
        "fixes": [],
    }
    done, report = run("pip-skipped", skipped, STUB_PIP_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    assert "dependency alembic skipped (incomplete audit)" in done.stdout
    no_vulns_field = {"dependencies": [{"name": "alembic", "version": "1.20.0"}], "fixes": []}
    done, report = run("pip-incomplete", no_vulns_field, STUB_PIP_AUDIT_RC="0")
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    partial: dict[str, Any] = _npm_audit()  # type: ignore[assignment]
    del partial["metadata"]["vulnerabilities"]["high"]
    done, report = run("npm-partial", partial, STUB_NPM_AUDIT_RC="0")
    assert done.returncode == 1 and report["result"] == "npm-audit-invalid"
    assert "metadata.vulnerabilities.high missing or not a count" in done.stdout
    # exit code and result disagree, in both directions, for both scanners
    done, report = run("pip-vuln-rc0", VULN_PIP_AUDIT, STUB_PIP_AUDIT_RC="0")
    assert done.returncode == 1 and report["result"] == "pip-audit-inconsistent"
    assert "pip-audit exit 0 with 1 vulnerabilities: exit code and result disagree" in done.stdout
    done, report = run("pip-clean-rc1", CLEAN_PIP_AUDIT, STUB_PIP_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "pip-audit-inconsistent"
    done, report = run("npm-two-rc0", _npm_audit(moderate=2), STUB_NPM_AUDIT_RC="0")
    assert done.returncode == 1 and report["result"] == "npm-audit-inconsistent"
    assert "exit 0 with total 2" in done.stdout
    done, report = run("npm-zero-rc1", _npm_audit(), STUB_NPM_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "npm-audit-inconsistent"
    # another exit code is not a verdict either
    done, report = run("npm-rc2", _npm_audit(), STUB_NPM_AUDIT_RC="2")
    assert done.returncode == 1 and report["result"] == "npm-audit-invalid"
    # the policy witness: npm exit 1 with low + moderate advisories only is a valid, clean result
    done, report = run("npm-low-moderate", _npm_audit(low=1, moderate=2), STUB_NPM_AUDIT_RC="1")
    assert done.returncode == 0 and report["result"] == "clean"
    assert report["scanners"]["npm_audit"] == {"exit_code": 1, "total": 3, "accepted": True}
    # and the vulnerability verdicts still stand on consistent results
    done, report = run("pip-vuln-rc1", VULN_PIP_AUDIT, STUB_PIP_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "vulnerabilities-found"
    done, report = run("npm-high-rc1", _npm_audit(high=1), STUB_NPM_AUDIT_RC="1")
    assert done.returncode == 1 and report["result"] == "vulnerabilities-found"


def test_audit_deps_audits_the_whole_pinned_set_without_pip(scratch: Path) -> None:
    # Rev 1.81 (lane OPS; the first run with the real tools, 2026-09-29): (a) pip-audit reads the
    # pinned, hashed export with --disable-pip, so no virtual environment is built; (b) environment
    # markers are removed from the audited copy, because pip-audit evaluates them on the auditing
    # host and drops what that host would not install (greenlet on macOS arm64, which the Linux
    # images carry); (c) a result that does not name exactly the pinned set is incomplete, never a
    # verdict; (d) a requirement that is not `name==version` is refused before any scanner runs.
    root = _dep5_root(scratch)
    npm_clean = scratch / "npm-clean.json"
    npm_clean.write_text(json.dumps(_npm_audit()), "utf-8")
    npm = {"STUB_NPM_AUDIT_JSON": str(npm_clean), "STUB_NPM_AUDIT_RC": "0"}
    marker = "platform_machine == 'aarch64' or platform_machine == 'x86_64'"
    export = _uv_export(
        scratch,
        "export-markers",
        "--index-url https://pypi.org/simple",
        "alembic==1.20.0",
        f"greenlet==3.5.5 ; {marker}",
        "Typing_Extensions==4.15.0 ; python_full_version < '3.13'",
    )
    both = {
        "dependencies": [
            {"name": "alembic", "version": "1.20.0", "vulns": []},
            {"name": "greenlet", "version": "3.5.5", "vulns": []},
            {"name": "typing-extensions", "version": "4.15.0", "vulns": []},
        ],
        "fixes": [],
    }

    def run(
        name: str, document: object, *, export_file: Path = export, rc: str = "0"
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        path = scratch / f"{name}.json"
        path.write_text(json.dumps(document), "utf-8")
        (scratch / "dep5-calls.log").write_text("", "utf-8")
        env = _dep5_env(
            scratch,
            root,
            **npm,
            STUB_UV_EXPORT=str(export_file),
            STUB_PIP_AUDIT_JSON=str(path),
            STUB_PIP_AUDIT_RC=rc,
        )
        done = _run_dep5("scripts/audit_deps.sh", root, env)
        return done, _report_of(root, "audit-deps")

    done, report = run("pip-complete", both)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1] == "OK audit-deps"
    assert "python vulnerabilities 0 in 3 audited of 3 pinned (2 environment markers removed)" in (
        done.stdout
    )
    captured = root / ".run" / "reports" / "audit-deps"
    exported = (root / ".run" / "tmp" / "audit-requirements.txt").read_text("utf-8")
    audited = (captured / "audited-requirements.txt").read_text("utf-8")
    assert marker in exported and ";" not in audited  # the export is kept as uv wrote it
    assert audited == exported.replace(f" ; {marker}", "").replace(
        " ; python_full_version < '3.13'", ""
    )
    assert report["result"] == "clean" and report["scanners"]["pip_audit"] == {
        "exit_code": 0,
        "dependencies_audited": 3,
        "accepted": True,
    }
    assert report["requirements"] == {
        "file": "audited-requirements.txt",
        "pinned": 3,
        "markers_removed": 2,
        "sha256": hashlib.sha256(audited.encode()).hexdigest(),
    }
    calls = _calls(scratch)
    assert "--disable-pip" in calls and f"-r {captured}/audited-requirements.txt" in calls
    assert f"-r {root}/.run/tmp/audit-requirements.txt" not in calls  # never the marked file
    # (c) incomplete: the scanner dropped a pinned requirement (what host markers do); and an
    # audited dependency the requirements do not pin
    dropped = {"dependencies": both["dependencies"][:1], "fixes": []}
    done, report = run("pip-dropped", dropped)
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    assert (
        "pip-audit result rejected: 2 pinned requirement(s) not audited: "
        "greenlet==3.5.5, typing-extensions==4.15.0" in done.stdout
    )
    assert report["scanners"]["pip_audit"]["accepted"] is False
    assert report["counts"]["stages"]["pip-audit"] == "fail"
    other_version = {
        "dependencies": [
            *both["dependencies"][:2],
            {"name": "typing-extensions", "version": "4.14.0", "vulns": []},
        ],
        "fixes": [],
    }
    done, report = run("pip-other-version", other_version)
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    assert "1 pinned requirement(s) not audited: typing-extensions==4.15.0" in done.stdout
    extra = {
        "dependencies": [*both["dependencies"], {"name": "leftpad", "version": "1.0", "vulns": []}],
        "fixes": [],
    }
    done, report = run("pip-extra", extra)
    assert done.returncode == 1 and report["result"] == "pip-audit-invalid"
    assert "1 audited dependency(ies) not pinned by the requirements: leftpad==1.0" in done.stdout
    # (d) the project line, an unpinned name and a URL requirement are refused by line, before
    # pip-audit or npm is called
    for name, line, number in (
        ("editable", "-e .", 3),
        ("unpinned", "requests>=2.0", 3),
        ("url", "demo @ https://example.invalid/demo-1.0.tar.gz", 3),
    ):
        bad = _uv_export(scratch, f"export-{name}", line, "alembic==1.20.0")
        done, report = run(f"pip-{name}", CLEAN_PIP_AUDIT, export_file=bad)
        assert done.returncode == 1 and report["result"] == "export-invalid", name
        assert (
            "FAIL audit-deps: the exported requirements cannot be audited: "
            f"line {number} is not a pinned requirement (name==version)" in done.stdout
        ), name
        assert report["counts"]["stages"] == {
            "export": "fail",
            "pip-audit": "not-run",
            "npm-audit": "not-run",
            "digest": "not-run",
        }, name
        assert (
            report["requirements"] is None and report["scanners"]["pip_audit"]["accepted"] is False
        )
        calls = _calls(scratch)
        assert "uv tool run" not in calls and "npm " not in calls, name
        assert not (captured / "audited-requirements.txt").exists(), name
    empty = _uv_export(scratch, "export-empty")
    done, report = run("pip-empty", CLEAN_PIP_AUDIT, export_file=empty)
    assert done.returncode == 1 and report["result"] == "export-invalid"
    assert "no pinned requirement in the export" in done.stdout


def test_compose_verify_cleanup_failure_decides_the_verdict(scratch: Path) -> None:
    # Codex production-20260922-0105 §7 (P6-DEP5-CLEANUP-1): a failed required `down -v` is never
    # `verified` with exit 0; its exit code is kept, alongside a primary failure when there is one.
    root = _dep5_root(scratch)
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_COMPOSE_DOWN_RC="3",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1].startswith(
        "FAIL compose-verify: project erev-verify verified but compose down -v failed (exit 3)"
    )
    report = _report_of(root, "compose-verify")
    assert report["result"] == "cleanup-failed" and report["exit_code"] == 1
    assert (
        report["counts"]["stages"]["down"] == "fail"
        and report["counts"]["stages"]["worker"] == "pass"
    )
    assert report["failures"] == [{"stage": "down", "exit_code": 3}]
    assert report["cleanup"] == {"stage": "down", "result": "failed", "exit_code": 3}
    assert report["kept_up"] is False
    # primary failure plus cleanup failure: both exit codes, composite verdict
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    with _scratch_http(csp=False) as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_COMPOSE_DOWN_RC="3",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1 and "; and compose down -v failed (exit 3)" in done.stdout
    report = _report_of(root, "compose-verify")
    assert report["result"] == "smoke-failed+cleanup-failed"
    assert report["failures"] == [
        {"stage": "smoke", "exit_code": 1},
        {"stage": "down", "exit_code": 3},
    ]
    assert report["cleanup"]["exit_code"] == 3 and report["counts"]["stages"]["smoke"] == "fail"
    # a successful down records done; keep-up owes no down and records kept-up
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
        assert done.returncode == 0
        assert _report_of(root, "compose-verify")["cleanup"] == {
            "stage": "down",
            "result": "done",
            "exit_code": 0,
        }
        env["EREV_COMPOSE_VERIFY_KEEP_UP"] = "1"
        env["STUB_COMPOSE_DOWN_RC"] = "3"  # irrelevant: no down is owed under keep-up
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0
    report = _report_of(root, "compose-verify")
    assert report["result"] == "verified" and report["failures"] == []
    assert report["cleanup"] == {"stage": "down", "result": "kept-up", "exit_code": None}


def test_zap_baseline_cleanup_failure_decides_the_verdict(scratch: Path) -> None:
    # Codex production-20260922-0105 §7 (P6-DEP5-CLEANUP-1) for the down zap_baseline.sh owns.
    root = _dep5_root(scratch)
    zap_json = scratch / "zap.json"
    zap_json.write_text(json.dumps(_zap_json(1)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="2",
            STUB_COMPOSE_DOWN_RC="3",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 1, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1].startswith(
        "FAIL zap-baseline: scan clean but compose down -v failed (exit 3)"
    )
    report = _report_of(root, "zap-baseline")
    assert report["result"] == "cleanup-failed" and report["exit_code"] == 1
    assert (
        report["counts"]["stages"]["down"] == "fail" and report["counts"]["stages"]["zap"] == "pass"
    )
    assert report["failures"] == [{"stage": "down", "exit_code": 3}]
    assert report["cleanup"] == {"stage": "down", "result": "failed", "exit_code": 3}
    # FAIL alerts plus a failed down: composite verdict, the down's code kept
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    zap_json.write_text(json.dumps(_zap_json(3)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="1",
            STUB_COMPOSE_DOWN_RC="3",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 1 and "; and compose down -v failed (exit 3)" in done.stdout
    report = _report_of(root, "zap-baseline")
    assert report["result"] == "fail-alerts+cleanup-failed" and report["counts"]["fail_alerts"] == 1
    assert report["failures"] == [{"stage": "down", "exit_code": 3}]
    assert report["cleanup"]["exit_code"] == 3
    # a successful down records done on the clean path
    zap_json.write_text(json.dumps(_zap_json(1)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="0",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 0
    assert _report_of(root, "zap-baseline")["cleanup"] == {
        "stage": "down",
        "result": "done",
        "exit_code": 0,
    }


def test_compose_verify_skips_without_daemon_and_refuses_busy_ports(scratch: Path) -> None:
    root = _dep5_root(scratch)
    env = _dep5_env(scratch, root, STUB_DOCKER_INFO_RC="1")
    done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" in done.stdout
    report = _report_of(root, "compose-verify")
    assert report["result"] == "skipped-no-daemon" and set(report["counts"]["stages"].values()) == {
        "skipped"
    }
    assert "compose" not in _calls(scratch)  # no compose command without a daemon
    # busy port: held by the scratch server on an ephemeral port of its own, refused before build/up
    with _scratch_http() as held:
        held_port = held.rsplit(":", 1)[1].rstrip("/")
        (scratch / "dep5-calls.log").write_text("", "utf-8")
        env = _dep5_env(scratch, root)
        env["EREV_COMPOSE_VERIFY_PORTS"] = f"{held_port} {_free_ports(1)[0]}"
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1 and done.stdout.splitlines()[-1].startswith(
        f"FAIL compose-verify: 127.0.0.1 port(s) in use: {held_port}"
    )
    report = _report_of(root, "compose-verify")
    assert report["result"] == "port-in-use" and report["counts"]["stages"]["ports"] == "fail"
    assert report["counts"]["stages"]["build"] == "not-run" and "compose" not in _calls(scratch)
    assert report["ports_overridden"] is True and report["ports"] == [
        f"127.0.0.1:{held_port}",
        report["ports"][1],
    ]
    # the override is test-only: refused outside EREV_ENV=test, and when malformed, before any
    # docker call
    for extra, reason in (
        ({"EREV_ENV": "dev"}, "test-only override outside EREV_ENV=test"),
        ({"EREV_COMPOSE_VERIFY_PORTS": "80 abc"}, "not one or two ports"),
        ({"EREV_COMPOSE_VERIFY_PORTS": "80"}, "port 80 outside 1024-65535"),
    ):
        (scratch / "dep5-calls.log").write_text("", "utf-8")
        env = _dep5_env(scratch, root)
        env.update(extra)
        if extra.get("EREV_ENV") == "dev":
            env.pop(
                "EREV_COMPOSE_VERIFY_ROOT"
            )  # the root override is refused under dev too; test the ports gate alone
            env["EREV_GATE_CONTEXT"] = str(root)
        done = _run_dep5("scripts/compose_verify.sh", root, env)
        assert (
            done.returncode == 1
            and f"FAIL compose-verify: EREV_COMPOSE_VERIFY_PORTS refused: {reason}" in done.stdout
        )
        assert _calls(scratch) == ""


def test_compose_verify_brings_up_smokes_and_tears_down(scratch: Path) -> None:
    root = _dep5_root(scratch)
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1] == "OK compose-verify"
    report = _report_of(root, "compose-verify")
    assert report["result"] == "verified" and report["kept_up"] is False
    assert report["counts"]["stages"] == {
        n: "pass"
        for n in ("daemon", "ports", "manifest", "build", "up", "ready", "smoke", "worker", "down")
    }
    # Rev 1.81 step (2a): the embedded manifest of the verified source sits at the build root before
    # the build (the Dockerfiles copy it), names this build, carries no image identity and no gate
    # evidence, and its retained copy and SHA-256 are in the report. Rev 1.150: the root is left
    # as it stood, so the retained copy is where the manifest is read after the run.
    report_dir = root / ".run" / "reports" / "compose-verify"
    assert report["manifest_copy"] == "release-manifest.embedded.json"
    embedded = (report_dir / "release-manifest.embedded.json").read_bytes()
    manifest = json.loads(embedded)
    assert manifest["build_sha"] == report["build_sha"]
    assert all(image == {"digest": None, "tag": None} for image in manifest["images"].values())
    assert {gate["result"] for gate in manifest["gate_results"].values()} == {"NOT_RUN"}
    assert report["manifest_sha256"] == hashlib.sha256(embedded).hexdigest()
    assert not (root / "release-manifest.json").exists()
    assert report["manifest_sha256"][:12] in done.stdout
    assert (report_dir / "gate-reports" / "release-manifest" / "report.json").is_file()
    assert "OK release-manifest" in (report_dir / "release-manifest.log").read_text("utf-8")
    # DEPLOY-PORT-FLAKE-1: the probe ran on this test's ephemeral ports under the generous budget
    assert report["ports_overridden"] is True and report["timeout_seconds"] == 120
    assert all(port not in ("127.0.0.1:8195", "127.0.0.1:5436") for port in report["ports"])
    assert report["csp_present"] is True and report["worker_health"] == "healthy"
    calls = _calls(scratch)
    compose_calls = [line for line in calls.splitlines() if line.startswith("docker compose")]
    assert all("-p erev-verify" in line for line in compose_calls) and compose_calls
    assert any(line.endswith("-p erev-verify build") for line in compose_calls)
    assert any(line.endswith("-p erev-verify up -d") for line in compose_calls)
    assert any(line.endswith("-p erev-verify down -v") for line in compose_calls)
    assert (
        f"-f {root}/deploy/compose.yaml --env-file {root}/deploy/compose.env.example"
        in compose_calls[0]
    )
    # the SPA without a CSP header fails the smoke stage, and the project still comes down
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    with _scratch_http(csp=False) as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert (
        done.returncode == 1
        and "FAIL compose-verify: GET" in done.stdout
        and "Content-Security-Policy" in done.stdout
    )
    assert any(line.endswith("-p erev-verify down -v") for line in _calls(scratch).splitlines())
    assert _report_of(root, "compose-verify")["counts"]["stages"]["smoke"] == "fail"
    # readiness never answers 200 within the (shortened) timeout: not-ready, torn down
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    with _scratch_http(ready=False) as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS="3",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1 and "did not answer 200 within 3s" in done.stdout
    assert any(line.endswith("-p erev-verify down -v") for line in _calls(scratch).splitlines())
    # an unhealthy worker fails the worker stage
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS="3",
            STUB_WORKER_HEALTH="starting",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1 and "the worker container is starting, not healthy" in done.stdout


def test_compose_verify_writes_the_embedded_manifest_before_the_build(scratch: Path) -> None:
    # Rev 1.81 (lane OPS; first run with a Docker daemon, 2026-09-29): in an execution context (a
    # clone) the git-ignored release-manifest.json does not exist and `compose build` failed at the
    # Dockerfiles' COPY. The script now writes the embedded manifest itself (step 2a) and a failure
    # there stops the run before any compose call.
    compose = (ROOT / "scripts" / "compose_verify.sh").read_text(encoding="utf-8")
    assert compose.index('scripts/release_manifest.py" --root "$ROOT"') < compose.index(
        "compose build >"
    )
    assert "--embedded" in compose and '--reports-dir "$REPORT_DIR/gate-reports"' in compose
    for dockerfile in ("api.Dockerfile", "worker.Dockerfile"):
        image = (ROOT / "deploy" / "docker" / dockerfile).read_text(encoding="utf-8")
        assert "COPY release-manifest.json /app/release-manifest.json" in image, dockerfile
    assert "release-manifest.json" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    root = _dep5_root(scratch)
    # a stale manifest of another build at the root is replaced, never embedded
    (root / "release-manifest.json").write_text(
        json.dumps({"build_sha": "0" * 40, "images": {"api": {"tag": "x", "digest": "y"}}}), "utf-8"
    )
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(root, "compose-verify")
    retained = root / ".run" / "reports" / "compose-verify" / "release-manifest.embedded.json"
    manifest = json.loads(retained.read_text("utf-8"))
    assert manifest["build_sha"] == report["build_sha"] != "0" * 40
    assert report["counts"]["stages"]["manifest"] == "pass"
    # the manifest cannot be written (its path is a directory): manifest-failed, nothing built
    (root / "release-manifest.json").unlink()
    (root / "release-manifest.json").mkdir()
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    done = _run_dep5("scripts/compose_verify.sh", root, _dep5_env(scratch, root))
    assert done.returncode == 1 and done.stdout.splitlines()[-1].startswith(
        "FAIL compose-verify: the embedded release manifest could not be written"
    )
    report = _report_of(root, "compose-verify")
    assert report["result"] == "manifest-failed" and report["manifest_sha256"] is None
    assert report["counts"]["stages"]["manifest"] == "fail"
    assert report["counts"]["stages"]["ports"] == "pass"
    assert report["counts"]["stages"]["build"] == "not-run"
    assert report["failures"][0]["stage"] == "manifest" and report["cleanup"] is None
    assert "compose" not in _calls(scratch)  # no build, no up and therefore no down
    # a directory is not this script's to set aside or to remove: it is left as it is
    assert (root / "release-manifest.json").is_dir() and report["manifest_root"] is None


def _own_manifest() -> bytes:
    """A manifest of the checkout's own making (`make release-manifest`): another build, with
    image identities - what a development process of that checkout reads at startup."""
    document = {"build_sha": "0" * 40, "images": {"api": {"tag": "x", "digest": "sha256:y"}}}
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def test_compose_verify_leaves_no_manifest_where_none_stood(scratch: Path) -> None:
    """DG-MK-compose-verify rev 1.150 (item 5 of supervisor ruling R-108 (b)): step (2a) writes
    the embedded manifest where the build reads it, and the script removes it when it ends - a
    verified run, a run that fails after the step, a run kept up for a caller. Fail-first: the
    file stayed at the build root, where the checkout's next development process read it."""
    root = _dep5_root(scratch)
    seen = scratch / "manifest-at-build.json"
    report_dir = root / ".run" / "reports" / "compose-verify"
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_MANIFEST_AT_BUILD=str(seen),
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(root, "compose-verify")
    assert not (root / "release-manifest.json").exists()
    assert report["manifest_root"] == "removed"
    # the build read this run's manifest, whose retained copy is the evidence
    assert seen.read_bytes() == (report_dir / "release-manifest.embedded.json").read_bytes()
    assert not (report_dir / "release-manifest.root-before.json").exists()
    # a run that fails after the step
    done = _run_dep5(
        "scripts/compose_verify.sh",
        root,
        _dep5_env(scratch, root, STUB_MANIFEST_AT_BUILD=str(seen), STUB_COMPOSE_BUILD_RC="1"),
    )
    assert done.returncode == 1 and "docker compose build failed" in done.stdout
    report = _report_of(root, "compose-verify")
    assert report["result"] == "build-failed" and report["manifest_root"] == "removed"
    assert seen.is_file() and not (root / "release-manifest.json").exists()
    # kept up for a caller: the project stays, the manifest does not
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            EREV_COMPOSE_VERIFY_KEEP_UP="1",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(root, "compose-verify")
    assert report["kept_up"] is True and report["manifest_root"] == "removed"
    assert not (root / "release-manifest.json").exists()


def test_compose_verify_puts_back_the_manifest_that_stood_at_the_build_root(scratch: Path) -> None:
    """DG-MK-compose-verify rev 1.150 (item 5 of supervisor ruling R-108 (b)): a manifest that
    stood at the build root - the checkout's own - is there again, byte for byte, when the script
    ends, on a verified run and on a failed one; the build read the run's embedded manifest, not
    that file. A copy that a killed run left next to the report is put back before the next run
    writes. Fail-first: the embedded manifest replaced the checkout's file for good."""
    root = _dep5_root(scratch)
    own = _own_manifest()
    (root / "release-manifest.json").write_bytes(own)
    seen = scratch / "manifest-at-build.json"
    report_dir = root / ".run" / "reports" / "compose-verify"
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_MANIFEST_AT_BUILD=str(seen),
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(root, "compose-verify")
    assert (root / "release-manifest.json").read_bytes() == own
    assert report["manifest_root"] == "restored"
    embedded = (report_dir / "release-manifest.embedded.json").read_bytes()
    assert seen.read_bytes() == embedded != own
    assert json.loads(embedded)["build_sha"] == report["build_sha"]
    assert not (report_dir / "release-manifest.root-before.json").exists()
    # a failed run (the stack never answers readyz) puts it back as well
    env = _dep5_env(
        scratch,
        root,
        EREV_COMPOSE_VERIFY_READYZ_URL="http://127.0.0.1:9/api/v1/readyz",
        EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS="1",
    )
    done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 1 and "did not answer 200 within 1s" in done.stdout
    assert _report_of(root, "compose-verify")["manifest_root"] == "restored"
    assert (root / "release-manifest.json").read_bytes() == own
    # a killed run left its embedded manifest at the root and the checkout's file next to the
    # report: the next run puts the checkout's file back first, and leaves it there at its end
    (report_dir / "release-manifest.root-before.json").write_bytes(own)
    (root / "release-manifest.json").write_bytes(
        (report_dir / "release-manifest.embedded.json").read_bytes()
    )
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "release-manifest.json").read_bytes() == own
    assert not (report_dir / "release-manifest.root-before.json").exists()
    # ... unless the checkout wrote a new manifest since: that one stands, the old copy is dropped
    newer = own.replace(b'"x"', b'"newer"')
    assert newer != own
    (report_dir / "release-manifest.root-before.json").write_bytes(own)
    (root / "release-manifest.json").write_bytes(newer)
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (root / "release-manifest.json").read_bytes() == newer
    assert not (report_dir / "release-manifest.root-before.json").exists()


def test_zap_baseline_leaves_the_build_root_as_it_stood(scratch: Path) -> None:
    """DG-MK-zap-baseline rev 1.150: the bring-up is compose_verify.sh's, which puts the build
    root back when it returns - before the scan starts - so the checkout's own manifest is at
    the root while ZAP runs and after the down, and with none there, none is left."""
    root = _dep5_root(scratch)
    own = _own_manifest()
    (root / "release-manifest.json").write_bytes(own)
    zap_json = scratch / "zap.json"
    zap_json.write_text(json.dumps(_zap_json(0)), "utf-8")
    at_build, at_scan = scratch / "manifest-at-build.json", scratch / "manifest-at-scan.json"
    for with_own in (True, False):
        if not with_own:
            (root / "release-manifest.json").unlink()
        with _scratch_http() as base:
            env = _dep5_env(
                scratch,
                root,
                EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
                EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
                STUB_ZAP_JSON=str(zap_json),
                STUB_MANIFEST_AT_BUILD=str(at_build),
                STUB_MANIFEST_AT_SCAN=str(at_scan),
            )
            done = _run_dep5("scripts/zap_baseline.sh", root, env)
        assert done.returncode == 0, done.stdout + done.stderr
        assert done.stdout.splitlines()[-1] == "OK zap-baseline"
        embedded = (
            root
            / ".run"
            / "reports"
            / "zap-baseline"
            / "compose-verify"
            / "release-manifest.embedded.json"
        ).read_bytes()
        assert at_build.read_bytes() == embedded != own
        if with_own:
            assert at_scan.read_bytes() == own
            assert (root / "release-manifest.json").read_bytes() == own
        else:
            assert Path(f"{at_scan}.absent").exists() and not at_scan.exists()
            assert not (root / "release-manifest.json").exists()


def test_compose_verify_readiness_is_reached_on_the_first_poll(scratch: Path) -> None:
    # DEPLOY-PORT-FLAKE-1, second cause (F-ADM): the stub answers readyz at once, so the script's
    # first poll succeeds and the wall-clock budget never decides a happy path. Structurally, the
    # readiness loop tries BEFORE its first sleep; at run time the stub saw at least one readyz
    # request, the stage passed, and the seconds to ready are far below the 120 s test budget (a
    # strict "exactly one request" would itself be load-sensitive: a starved server thread can push
    # the first request past its 5 s timeout, which is the very window this budget absorbs).
    compose = (ROOT / "scripts" / "compose_verify.sh").read_text(encoding="utf-8")
    ready_block = compose.split("# (5) readiness within the timeout.", 1)[1].split(
        "STAGES_PASSED=", 1
    )[0]
    assert ready_block.index("urllib.request.urlopen(url, timeout=5)") < ready_block.index(
        "time.sleep(2)"
    )
    root = _dep5_root(scratch)
    hits: dict[str, int] = {}
    with _scratch_http(hits=hits) as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
        )
        assert env["EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS"] == "120"
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    report = _report_of(root, "compose-verify")
    assert hits.get("readyz", 0) >= 1 and report["counts"]["stages"]["ready"] == "pass"
    assert report["counts"]["ready_seconds"] is not None and report["counts"]["ready_seconds"] <= 30
    assert report["timeout_seconds"] == 120


def test_compose_verify_keep_up_contract(scratch: Path) -> None:
    # EREV_COMPOSE_VERIFY_KEEP_UP=1: steps 2 to 6 run, no `down -v`, the keep-up line is printed,
    # the report records kept_up and the down stage skipped; EREV_COMPOSE_VERIFY_REPORT_DIR
    # relocates the report.
    root = _dep5_root(scratch)
    report_dir = root / ".run" / "reports" / "caller" / "compose-verify"
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            EREV_COMPOSE_VERIFY_KEEP_UP="1",
            EREV_COMPOSE_VERIFY_REPORT_DIR=str(report_dir),
        )
        done = _run_dep5("scripts/compose_verify.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "compose-verify: project erev-verify left up for the caller (keep-up)" in done.stdout
    assert not any(line.endswith("down -v") for line in _calls(scratch).splitlines())
    report = json.loads((report_dir / "report.json").read_text("utf-8"))
    assert report["kept_up"] is True and report["counts"]["stages"]["down"] == "skipped"
    assert not (root / ".run" / "reports" / "compose-verify").exists()


def test_zap_baseline_reuses_the_bring_up_and_owns_the_down(scratch: Path) -> None:
    root = _dep5_root(scratch)
    zap_json = scratch / "zap.json"
    zap_json.write_text(json.dumps(_zap_json(0, 1, 1, 2)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="2",  # WARN alerts only
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines()[-1] == "OK zap-baseline"
    report = _report_of(root, "zap-baseline")
    assert report["result"] == "clean" and report["zap_exit_code"] == 2
    assert report["counts"]["alerts_by_risk"] == {
        "informational": 1,
        "low": 2,
        "medium": 1,
        "high": 0,
        "fail": 0,
    }
    assert report["counts"]["stages"] == {
        n: "pass" for n in ("daemon", "bring-up", "zap", "down", "counts")
    }
    assert report["image_digest"] == "ghcr.io/zaproxy/zaproxy@sha256:stubdigest"
    calls = _calls(scratch).splitlines()
    # the bring-up came from compose_verify.sh (its build/up calls) under keep-up; exactly one
    # down, by zap
    assert sum(line.endswith("-p erev-verify build") for line in calls) == 1
    assert sum(line.endswith("-p erev-verify up -d") for line in calls) == 1
    assert sum(line.endswith("-p erev-verify down -v") for line in calls) == 1
    run_line = next(line for line in calls if line.startswith("docker run"))
    assert run_line == (
        f"docker run --rm -v {root}/.run/reports/zap-baseline:/zap/wrk "
        "ghcr.io/zaproxy/zaproxy:stable "
        "zap-baseline.py -t http://host.docker.internal:8195/ -J zap.json -r zap.html"
    )
    sub_report = json.loads(
        (root / ".run" / "reports" / "zap-baseline" / "compose-verify" / "report.json").read_text(
            "utf-8"
        )
    )
    assert sub_report["kept_up"] is True and sub_report["result"] == "verified"
    assert (root / ".run" / "reports" / "zap-baseline" / "zap.html").exists()
    # FAIL alerts: exit 1, result fail-alerts, still torn down exactly once
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    zap_json.write_text(json.dumps(_zap_json(3, 3)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="1",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 1 and done.stdout.splitlines()[-1].startswith(
        "FAIL zap-baseline: zap-baseline.py reported FAIL alerts"
    )
    report = _report_of(root, "zap-baseline")
    assert (
        report["result"] == "fail-alerts"
        and report["counts"]["alerts_by_risk"]["high"] == 2
        and report["counts"]["fail_alerts"] == 1
    )
    assert (
        sum(line.endswith("-p erev-verify down -v") for line in _calls(scratch).splitlines()) == 1
    )
    # no daemon: skipped, nothing brought up
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    done = _run_dep5(
        "scripts/zap_baseline.sh", root, _dep5_env(scratch, root, STUB_DOCKER_INFO_RC="1")
    )
    assert (
        done.returncode == 0
        and "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" in done.stdout
    )
    assert _report_of(root, "zap-baseline")["result"] == "skipped-no-daemon"
    assert "compose" not in _calls(scratch) and "docker run" not in _calls(scratch)
    # a bring-up failure (compose build fails inside compose_verify.sh) is reported; it started
    # nothing, so nothing is taken down (ZAP-DOWN-OWNERSHIP-1, the test below)
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    done = _run_dep5(
        "scripts/zap_baseline.sh",
        root,
        _dep5_env(scratch, root, STUB_COMPOSE_BUILD_RC="1", STUB_ZAP_JSON=str(zap_json)),
    )
    assert (
        done.returncode == 1
        and "FAIL zap-baseline: compose_verify.sh failed to bring project erev-verify up"
        in done.stdout
    )
    # the sub-run's verdict travels in the FAIL line (attributable from the line alone)
    assert "(compose-verify result: build-failed;" in done.stdout
    assert "docker run" not in _calls(scratch)


def _downs(scratch: Path) -> int:
    return sum(line.endswith("-p erev-verify down -v") for line in _calls(scratch).splitlines())


KEPT_UP = "left up for the caller (keep-up)"


def test_zap_baseline_reads_the_line_its_bring_up_prints() -> None:
    """Item ZAP-DOWN-OWNERSHIP-1: one line in three places - ``compose_verify.sh`` prints it,
    ``zap_baseline.sh`` reads it, and the row of the dev guide names it (DG-MK-zap-baseline rev
    1.235)."""
    zap = (ROOT / "scripts" / "zap_baseline.sh").read_text("utf-8")
    compose = (ROOT / "scripts" / "compose_verify.sh").read_text("utf-8")
    row = next(
        line
        for line in (ROOT / "docs" / "dev-guide.md").read_text("utf-8").splitlines()
        if line.startswith("| DG-MK-zap-baseline |")
    )
    assert f'KEPT_UP_LINE="{KEPT_UP}"' in zap and f'project $PROJECT {KEPT_UP}"' in compose
    assert 'grep -q "$KEPT_UP_LINE" "$REPORT_DIR/compose-verify.log"' in zap
    assert f"`{KEPT_UP}`" in row and "Rev 1.235 (item ZAP-DOWN-OWNERSHIP-1)" in row


def test_zap_baseline_takes_down_only_the_project_it_brought_up(scratch: Path) -> None:
    """Item ZAP-DOWN-OWNERSHIP-1 (dev-guide DG-MK-zap-baseline rev 1.235; the supervisor's ruling
    of 2026-10-01 and word of 2026-10-02). The exit trap ran ``down -v`` on every path after the
    bring-up was called - also after one that had stopped at the port check, where the two ports
    are held by ANOTHER checkout's project ``erev-verify``: the down would have removed that
    project with its volumes. The down is this script's only when the bring-up of the run
    printed that it left the project up for the caller. Both ways, with the stand-in docker:
    nothing is taken down after a held port, a failed build, or a bring-up that said nothing;
    the project is taken down once after an ``up`` that failed and after one that came up and
    was not ready."""
    root = _dep5_root(scratch)
    log = root / ".run" / "reports" / "zap-baseline" / "compose-verify.log"
    # a held port: the bring-up stops at its probe, and no compose command is sent at all
    with _scratch_http() as held:
        held_port = held.rsplit(":", 1)[1].rstrip("/")
        env = _dep5_env(scratch, root)
        env["EREV_COMPOSE_VERIFY_PORTS"] = f"{held_port} {_free_ports(1)[0]}"
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
        assert "compose" not in _calls(scratch), "a project this run did not bring up is taken down"
        assert done.returncode == 1, done.stdout + done.stderr
        assert done.stdout.splitlines()[-1].startswith(
            "FAIL zap-baseline: compose_verify.sh failed to bring project erev-verify up "
            "(compose-verify result: port-in-use; it started nothing, so nothing is taken down: "
            "a project erev-verify on the daemon is not this run's;"
        )
        report = _report_of(root, "zap-baseline")
        assert report["result"] == "bring-up-failed" and report["cleanup"] is None
        assert report["counts"]["stages"] == {
            "daemon": "pass",
            "bring-up": "fail",
            "zap": "not-run",
            "down": "not-run",
            "counts": "not-run",
        }
        # what an earlier bring-up said is not this run's: its log - here one that says a project
        # was left up, and that this run could not write over - is removed before the call
        log.unlink()
        log.write_text(f"compose-verify: project erev-verify {KEPT_UP}\n", "utf-8")
        log.chmod(0o444)
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
        assert "compose" not in _calls(scratch), "the earlier run's line is read as this run's"
        assert "(compose-verify result: port-in-use; it started nothing, so" in done.stdout
    # a build that fails: an image build starts no container, network or volume
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    done = _run_dep5(
        "scripts/zap_baseline.sh", root, _dep5_env(scratch, root, STUB_COMPOSE_BUILD_RC="1")
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "(compose-verify result: build-failed; it started nothing, so" in done.stdout
    assert _downs(scratch) == 0 and _report_of(root, "zap-baseline")["cleanup"] is None

    # the other way. `up` itself fails: it was begun, what it started is this run's
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    done = _run_dep5(
        "scripts/zap_baseline.sh", root, _dep5_env(scratch, root, STUB_COMPOSE_UP_RC="1")
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert (
        "(compose-verify result: up-failed; it left the project up, and this run takes it down;"
        in done.stdout
    )
    assert _downs(scratch) == 1
    assert _report_of(root, "zap-baseline")["cleanup"] == {
        "stage": "down",
        "result": "done",
        "exit_code": 0,
    }
    # the project came up and was not ready within the budget: taken down once as well
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    with _scratch_http(ready=False) as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS="2",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "(compose-verify result: not-ready; it left the project up, and this" in done.stdout
    assert _downs(scratch) == 1

    # that run's log says a project was left up. A run that never calls the bring-up - the script
    # it would call is not there - reads no log at all
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    absent = scratch / "bin" / "compose-verify-absent"
    done = _run_dep5(
        "scripts/zap_baseline.sh",
        root,
        _dep5_env(scratch, root, EREV_COMPOSE_VERIFY_BIN=str(absent)),
    )
    assert done.returncode == 1 and done.stdout.splitlines()[-1] == (
        "FAIL zap-baseline: scripts/compose_verify.sh is not in this tree (DEP-5)"
    )
    assert KEPT_UP in log.read_text("utf-8") and _calls(scratch).splitlines() == ["docker info"]
    # a bring-up that says nothing - here a stand-in that only fails - left nothing up, and what
    # the run before it said (it had left a project up, and its report says not-ready) is not
    # read as this run's
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    silent = _stub_binary(scratch, "compose-verify-silent", "#!/usr/bin/env bash\nexit 1\n")
    done = _run_dep5(
        "scripts/zap_baseline.sh",
        root,
        _dep5_env(scratch, root, EREV_COMPOSE_VERIFY_BIN=str(silent)),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "(compose-verify result: unknown; it started nothing, so" in done.stdout
    assert _calls(scratch).splitlines() == ["docker info"]
    # nor is anything taken down after a bring-up that ends well and has not said the line
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    quiet = _stub_binary(scratch, "compose-verify-quiet", "#!/usr/bin/env bash\nexit 0\n")
    done = _run_dep5(
        "scripts/zap_baseline.sh",
        root,
        _dep5_env(scratch, root, EREV_COMPOSE_VERIFY_BIN=str(quiet)),
    )
    assert done.returncode == 1 and done.stdout.splitlines()[-1] == (
        "FAIL zap-baseline: compose_verify.sh did not honour the keep-up contract"
    )
    assert _report_of(root, "zap-baseline")["result"] == "bring-up-not-kept-up"
    assert _calls(scratch).splitlines() == ["docker info"]
    # an earlier run's log that cannot be removed - its directory is read-only - stops the run
    # before the bring-up is called: the line in it would be read as this run's
    (scratch / "dep5-calls.log").write_text("", "utf-8")
    log.write_text(f"compose-verify: project erev-verify {KEPT_UP}\n", "utf-8")
    log.chmod(0o444)
    log.parent.chmod(0o555)
    try:
        done = _run_dep5("scripts/zap_baseline.sh", root, _dep5_env(scratch, root))
    finally:
        log.parent.chmod(0o755)
        log.chmod(0o644)
    assert _calls(scratch).splitlines() == ["docker info"], done.stdout + done.stderr
    assert done.returncode == 1 and done.stdout.splitlines()[-1] == (
        "FAIL zap-baseline: the log and the report an earlier bring-up left in zap-baseline "
        "could not be removed"
    )
    assert _report_of(root, "zap-baseline")["result"] == "stale-bring-up"


def test_zap_baseline_takes_its_project_down_when_a_signal_ends_the_run(scratch: Path) -> None:
    """Item ZAP-DOWN-OWNERSHIP-1, the interrupted run. ``compose_verify.sh`` writes its report
    only when it ends by itself; ended by a signal it prints from its exit trap that it left the
    project up, and that line is what this script reads - a rule that read the report would
    leave the run's own project up after a Ctrl-C. A signal ends this script through its exit
    trap once the command in the foreground has ended: the line is there when the trap looks,
    and a bring-up the signal did not reach runs to its end first. Both with SIGTERM, which no
    launcher leaves ignored: to the run's whole process group while the bring-up waits for
    readiness, and to the script's own process alone."""
    root = _dep5_root(scratch)
    report_dir = root / ".run" / "reports" / "zap-baseline"

    def ended_by_sigterm(*, whole_group: bool, readiness_budget: str) -> int:
        (scratch / "dep5-calls.log").write_text("", "utf-8")
        polled = threading.Event()
        with _scratch_http(ready=False, polled=polled) as base:
            env = _dep5_env(
                scratch,
                root,
                EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
                EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
                EREV_COMPOSE_VERIFY_TIMEOUT_SECONDS=readiness_budget,
            )
            process = subprocess.Popen(
                ["bash", str(ROOT / "scripts" / "zap_baseline.sh")],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,  # a process group of the run's own
            )
            try:
                # the bring-up is past its `up` and in its readiness wait
                assert polled.wait(timeout=300), "the bring-up never asked for readiness"
                if whole_group:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.send_signal(signal.SIGTERM)
                process.communicate(timeout=300)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
        return process.returncode

    # the whole group, as a terminal's Ctrl-C reaches it: the bring-up ends in its exit trap,
    # says the line and writes no report; this script then takes the project down, once
    assert ended_by_sigterm(whole_group=True, readiness_budget="120") == 143
    assert _downs(scratch) == 1
    assert KEPT_UP in (report_dir / "compose-verify.log").read_text("utf-8")
    assert not (report_dir / "compose-verify" / "report.json").exists()
    # this script alone: the bring-up runs to its end - not ready within its budget, a report of
    # its own - and only then does the signal end the run, with the project taken down, once
    assert ended_by_sigterm(whole_group=False, readiness_budget="3") == 143
    assert _downs(scratch) == 1
    sub_report = json.loads((report_dir / "compose-verify" / "report.json").read_text("utf-8"))
    assert sub_report["result"] == "not-ready" and sub_report["counts"]["stages"]["up"] == "pass"


MASTER_KEY_VARIABLES = (
    "EREV_COMPOSE_ENCRYPTION_KEY",
    "EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY",
    "EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY",
)


def _assert_generated_keys(keys: tuple[str, ...]) -> None:
    """Three different keys of the CFG-26 form that the production startup rule accepts (05 CFG-26
    rev 1.53: at least 16 distinct byte values), and none of the placeholders the example file
    shipped before."""
    assert len(keys) == 3 and len(set(keys)) == 3, "three different keys"
    for key in keys:
        assert re.fullmatch(r"[0-9a-f]{64}", key), "64 lowercase hexadecimal characters"
        assert len(set(bytes.fromhex(key))) >= 16
        assert not re.fullmatch(r"0{63}[1-9]", key)


def _written_by(done: subprocess.CompletedProcess[str], root: Path) -> str:
    written = done.stdout + done.stderr
    for path in (root / ".run").rglob("*"):
        if path.is_file():
            written += path.read_text("utf-8", errors="replace")
    return written


def test_compose_verify_generates_the_master_keys_of_the_run(scratch: Path) -> None:
    """DG-MK-compose-verify step (2b), rev 1.97 (05 CFG-26 rev 1.53; R-34 SD-6): the example file
    ships no master key, so the run generates three, hands every compose call the same three, and
    writes them nowhere; keys in the caller's environment are used as they are."""
    root = _dep5_root(scratch)

    def run(**extra: str) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, ...]]]:
        with _scratch_http() as base:
            env = _dep5_env(
                scratch,
                root,
                EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
                EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
                **extra,
            )
            done = _run_dep5("scripts/compose_verify.sh", root, env)
        return done, _keys_seen(scratch)

    done, seen = run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(seen) >= 4, "build, up, ps and down at least"
    assert len(set(seen)) == 1, "every compose call of the run is handed the same keys"
    first = seen[0]
    _assert_generated_keys(first)
    assert _report_of(root, "compose-verify")["master_keys"] == "generated"
    # Written nowhere: not in the output, not in any file under the run directory.
    written = _written_by(done, root)
    assert all(key not in written for key in first)

    # Another run, other keys.
    done, seen = run()
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_generated_keys(seen[0])
    assert not set(seen[0]) & set(first)

    # Keys the caller's environment carries are used as they are (zap-baseline's bring-up).
    given = ("1f" * 16 + "e0" * 16, "a9" * 32, "5c" * 32)
    done, seen = run(**dict(zip(MASTER_KEY_VARIABLES, given, strict=True)))
    assert done.returncode == 0, done.stdout + done.stderr
    assert set(seen) == {given}
    assert _report_of(root, "compose-verify")["master_keys"] == "inherited"
    # One given, two generated: the given one is kept.
    done, seen = run(EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY=given[1])
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(set(seen)) == 1 and seen[0][1] == given[1] and len(set(seen[0])) == 3
    assert _report_of(root, "compose-verify")["master_keys"] == "mixed"
    # The header names the step.
    text = (ROOT / "scripts" / "compose_verify.sh").read_text("utf-8")
    assert "(2b) generate the run's three CFG-26 master keys" in text


def test_zap_baseline_hands_its_down_the_keys_of_the_bring_up(scratch: Path) -> None:
    """DG-MK-zap-baseline, rev 1.97: the keys are generated before the bring-up, so the bring-up
    (compose_verify.sh, which inherits them) and this script's own ``down -v`` interpolate the
    same values."""
    root = _dep5_root(scratch)
    zap_json = scratch / "zap.json"
    zap_json.write_text(json.dumps(_zap_json(0, 1)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="2",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    calls = [line for line in _calls(scratch).splitlines() if line.startswith("docker compose")]
    seen = _keys_seen(scratch)
    assert len(seen) == len(calls) and calls[-1].endswith("-p erev-verify down -v")
    assert len(set(seen)) == 1, "the bring-up and the down see the same keys"
    _assert_generated_keys(seen[0])
    sub_report = json.loads(
        (root / ".run" / "reports" / "zap-baseline" / "compose-verify" / "report.json").read_text(
            "utf-8"
        )
    )
    assert sub_report["master_keys"] == "inherited"
    written = _written_by(done, root)
    assert all(key not in written for key in seen[0])


DATABASE_PASSWORD_VARIABLES = (
    "EREV_COMPOSE_POSTGRES_PASSWORD",
    "EREV_COMPOSE_OWNER_PASSWORD",
    "EREV_COMPOSE_APP_PASSWORD",
)


def _assert_generated_passwords(passwords: tuple[str, ...]) -> None:
    """Three different passwords of 32 URL-safe characters (``secrets.token_urlsafe(24)``:
    ``deploy/compose.yaml`` places two of them in the database URLs), none a placeholder the
    role-init script refuses (05 DPL-10 rev 1.53)."""
    assert len(passwords) == 3 and len(set(passwords)) == 3, "three different passwords"
    for password in passwords:
        assert re.fullmatch(r"[A-Za-z0-9_-]{32}", password), "32 URL-safe characters"
        assert not password.startswith("change-me")


def test_compose_verify_generates_the_database_passwords_of_the_run(scratch: Path) -> None:
    """DG-MK-compose-verify step (2b), rev 1.97 (05 DPL-10, DPL-16 rev 1.53; ruling R-53 (6)): the
    role-init script refuses the example file's ``change-me-…`` passwords, so the run generates
    three, hands every compose call the same three, and writes them nowhere; passwords in the
    caller's environment are used as they are."""
    root = _dep5_root(scratch)
    # Why the run cannot use the example's values: the repository's example ships placeholders.
    example = (ROOT / "deploy" / "compose.env.example").read_text("utf-8")
    shipped = dict(re.findall(r"(?m)^(EREV_COMPOSE_\w+_PASSWORD)=(.*)$", example))
    assert all(shipped[name].startswith("change-me-") for name in DATABASE_PASSWORD_VARIABLES)

    def run(**extra: str) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, ...]]]:
        with _scratch_http() as base:
            env = _dep5_env(
                scratch,
                root,
                EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
                EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
                **extra,
            )
            done = _run_dep5("scripts/compose_verify.sh", root, env)
        return done, _passwords_seen(scratch)

    done, seen = run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(seen) >= 4, "build, up, ps and down at least"
    assert len(set(seen)) == 1, "every compose call of the run is handed the same passwords"
    first = seen[0]
    _assert_generated_passwords(first)
    assert _report_of(root, "compose-verify")["database_passwords"] == "generated"
    written = _written_by(done, root)
    assert all(password not in written for password in first)

    done, seen = run()
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_generated_passwords(seen[0])
    assert not set(seen[0]) & set(first), "another run, other passwords"

    given = ("superuser-Given_000001", "owner-Given_0000000002", "app-Given_00000000003")
    done, seen = run(**dict(zip(DATABASE_PASSWORD_VARIABLES, given, strict=True)))
    assert done.returncode == 0, done.stdout + done.stderr
    assert set(seen) == {given}
    assert _report_of(root, "compose-verify")["database_passwords"] == "inherited"
    done, seen = run(EREV_COMPOSE_OWNER_PASSWORD=given[1])
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(set(seen)) == 1 and seen[0][1] == given[1] and len(set(seen[0])) == 3
    assert _report_of(root, "compose-verify")["database_passwords"] == "mixed"
    # The master keys of the same run are reported on their own.
    assert _report_of(root, "compose-verify")["master_keys"] == "generated"
    text = (ROOT / "scripts" / "compose_verify.sh").read_text("utf-8")
    assert "the run's three database passwords" in text


def test_zap_baseline_hands_its_down_the_passwords_of_the_bring_up(scratch: Path) -> None:
    """DG-MK-zap-baseline, rev 1.97 (ruling R-53 (6)): the database passwords are generated before
    the bring-up, so ``compose_verify.sh`` inherits them and this script's own ``down -v``
    interpolates the same values."""
    root = _dep5_root(scratch)
    zap_json = scratch / "zap.json"
    zap_json.write_text(json.dumps(_zap_json(0, 1)), "utf-8")
    with _scratch_http() as base:
        env = _dep5_env(
            scratch,
            root,
            EREV_COMPOSE_VERIFY_READYZ_URL=f"{base}/api/v1/readyz",
            EREV_COMPOSE_VERIFY_ROOT_URL=f"{base}/",
            STUB_ZAP_JSON=str(zap_json),
            STUB_ZAP_RC="2",
        )
        done = _run_dep5("scripts/zap_baseline.sh", root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    calls = [line for line in _calls(scratch).splitlines() if line.startswith("docker compose")]
    seen = _passwords_seen(scratch)
    assert len(seen) == len(calls) and calls[-1].endswith("-p erev-verify down -v")
    assert len(set(seen)) == 1, "the bring-up and the down see the same passwords"
    _assert_generated_passwords(seen[0])
    sub_report = json.loads(
        (root / ".run" / "reports" / "zap-baseline" / "compose-verify" / "report.json").read_text(
            "utf-8"
        )
    )
    assert sub_report["database_passwords"] == "inherited"
    written = _written_by(done, root)
    assert all(password not in written for password in seen[0])
