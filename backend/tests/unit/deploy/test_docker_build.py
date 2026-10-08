"""``scripts/docker_build.sh`` contract (dev-guide §4.5 DG-MK-docker-build, DG-MK-00g, DG-MK-00h,
DG-FORBID-07; 05 DPL-05, REL-01, REL-03; BUILD_SPEC DEP-5 docker-build part).

The script runs against a stand-in ``docker`` binary and a scratch repository root: no image is
built, no daemon is needed, and the worktree's own manifest and reports are never touched. The
stand-in records every invocation, can mutate the exported context or the source between builds,
answers the manifest read-back with the manifest the context held (or a chosen file) and the
hardening probe with chosen findings, so the immutable-context, attestation and hardening rules
are exercised before any real container run. The manifest step runs a stand-in generator (the
test-only ``EREV_DOCKER_BUILD_MANIFEST_SCRIPT``) except where a test asks for the real
``scripts/release_manifest.py``. The Makefile target is covered by ``test_makefile_targets``.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from support.release_manifest import commit, git, scratch_repo

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "docker_build.sh"
IMAGES = ("api", "worker", "web")

DOCKER_STUB = """#!/usr/bin/env bash
# docker stand-in: `info` answers per STUB_DOCKER_INFO_RC; `build` records its arguments, may
# mutate the context (STUB_MUTATE_CONTEXT=1) or the source root (STUB_MUTATE_SOURCE=1) and exits
# per STUB_DOCKER_BUILD_RC and keeps the manifest its context held; `image inspect` prints a
# deterministic id for the tag; `run` answers the manifest read-back with the SHA-256 of that kept
# manifest (or of STUB_MANIFEST_FILE) and the hardening probe (`--user 0`) with STUB_PROBE_<NAME>,
# by default no finding.
echo "$*" >>"$STUB_CALLS"
case "$1" in
  info)
    # Concurrent checkout modelled at the daemon probe (Codex build-source binding probe): HEAD of
    # the scratch repository moves to STUB_FLIP_TO after the script captured BUILD_SHA.
    if [[ -n "${STUB_FLIP_TO:-}" && ! -f "$STUB_CALLS.flipped" ]]; then
      git -C "$EREV_DOCKER_BUILD_ROOT" checkout -q "$STUB_FLIP_TO" && touch "$STUB_CALLS.flipped"
    fi
    exit "${STUB_DOCKER_INFO_RC:-0}" ;;
  build)
    for context in "$@"; do :; done  # the last argument (bash 3.2 has no negative offsets)
    prev=""; tag=""
    for arg in "$@"; do if [[ "$prev" == "-t" ]]; then tag="$arg"; fi; prev="$arg"; done
    name="${tag#erev-}"; name="${name%%:*}"
    cp "$context/README.md" "$STUB_CALLS.readme-$name" 2>/dev/null || true
    cp "$context/release-manifest.json" "$STUB_CALLS.manifest-$name" 2>/dev/null || true
    if [[ "$name" == "web" && -n "${STUB_FLIP_BACK:-}" ]]; then
      git -C "$EREV_DOCKER_BUILD_ROOT" checkout -q "$STUB_FLIP_BACK"
    fi
    if [[ "${STUB_MUTATE_CONTEXT:-}" == "1" && -d "$context" ]]; then
      echo "mutated" >>"$context/README.md"
    fi
    if [[ "${STUB_MUTATE_SOURCE:-}" == "1" ]]; then
      echo "mutated" >>"$EREV_DOCKER_BUILD_ROOT/README.md"
    fi
    exit "${STUB_DOCKER_BUILD_RC:-0}" ;;
  image)
    for tag in "$@"; do :; done
    printf 'sha256:%s\\n' "$(printf '%s' "$tag" | shasum -a 256 | cut -c1-64)"
    exit 0 ;;
  run)
    tag=""; entrypoint=""; probe=""; prev=""; last=""
    for arg in "$@"; do
      if [[ "$prev" == "--entrypoint" ]]; then entrypoint="$arg"; fi
      if [[ "$arg" == erev-*:* ]]; then tag="$arg"; fi
      if [[ "$arg" == "--user" ]]; then probe="1"; fi
      prev="$arg"; last="$arg"
    done
    name="${tag#erev-}"; name="${name%%:*}"
    if [[ -n "$probe" ]]; then
      if [[ "$last" == "-" ]]; then cat >/dev/null; fi  # the program on standard input
      if chosen="$(printenv "STUB_PROBE_$(printf '%s' "$name" | tr 'a-z' 'A-Z')")"; then
        printf '%s' "$chosen"
      elif [[ "$entrypoint" != "find" ]]; then
        printf '{"pip": [], "setuid": []}'
      fi
      exit "${STUB_PROBE_RC:-0}"
    fi
    shasum -a 256 "${STUB_MANIFEST_FILE:-$STUB_CALLS.manifest-$name}" | cut -c1-64 | tr -d '\\n'
    exit 0 ;;
  push|login) echo "forbidden: $1" >&2; exit 99 ;;
  *) exit 0 ;;
esac
"""

GENERATOR_STUB = """# scripts/release_manifest.py stand-in: logs its arguments and writes to --out
# what STUB_MANIFEST names: "ok" the embedded manifest of the root's HEAD, "stale" one of another
# build, "images" one that carries image identities, "absent" nothing; "fail" exits 1 as a refused
# --strict run does.
import json
import os
import subprocess
import sys

args = sys.argv[1:]
with open(os.environ["STUB_CALLS"] + ".generator", "a", encoding="utf-8") as log:
    log.write(" ".join(args) + "\\n")
mode = os.environ.get("STUB_MANIFEST", "ok")
if mode == "fail":
    print("stand-in: ci FAIL (exit 1)", file=sys.stderr)
    sys.exit(1)
if mode == "absent":
    sys.exit(0)
root, out = args[args.index("--root") + 1], args[args.index("--out") + 1]
head = subprocess.run(
    ["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
).stdout.strip()
build = "f" * 40 if mode == "stale" else head
images = {
    name: (
        {"tag": f"erev-{name}:{build[:12]}", "digest": "sha256:" + "0" * 64}
        if mode == "images"
        else {"tag": None, "digest": None}
    )
    for name in ("api", "worker", "web")
}
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as handle:
    document = {"build_sha": build, "engine_version": "0.0.0", "images": images}
    handle.write(json.dumps(document, indent=2, sort_keys=True) + "\\n")
"""


@pytest.fixture
def scratch() -> Iterator[Path]:
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        yield Path(directory)


def _stub(scratch: Path) -> Path:
    binary = scratch / "bin" / "docker"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(DOCKER_STUB, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def _repo(scratch: Path) -> tuple[Path, str]:
    files = {
        f"deploy/docker/{name}.Dockerfile": f"FROM scratch AS runtime\n# {name}\n"
        for name in IMAGES
    }
    files["README.md"] = "scratch\n"
    files[".gitignore"] = "release-manifest.json\n"  # as the repository's own (DG-LAY-08)
    repo = scratch_repo(scratch / "repo", files=files)
    return repo, git(repo, "rev-parse", "HEAD")


def _generator(scratch: Path) -> Path:
    script = scratch / "bin" / "manifest.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(GENERATOR_STUB, encoding="utf-8")
    return script


def _embedded(scratch: Path) -> Path:
    """Where the script writes the embedded manifest: under the run directory, nowhere else."""
    return scratch / "run" / "reports" / "docker-build" / "release-manifest.embedded.json"


def _run(
    scratch: Path, repo: Path, *, real_generator: bool = False, **values: str
) -> subprocess.CompletedProcess[str]:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "STUB_", "NO_CACHE", "STRICT", "VALIDATION_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(prefixes)}
    env.pop("EREV_VALIDATION_LEVEL_RAW", None)
    env.pop("EREV_DOCKER_BUILD_MANIFEST_SCRIPT", None)
    calls = scratch / "calls.log"
    for old in scratch.glob("calls.log*"):
        old.unlink()
    env |= {
        "EREV_ENV": "test",
        "EREV_DOCKER_BIN": str(_stub(scratch)),
        "EREV_DOCKER_BUILD_ROOT": str(repo),
        "EREV_RUN_DIR": str(scratch / "run"),
        "EREV_DOCKER_BUILD_COMMAND": "make docker-build",
        "STUB_CALLS": str(calls),
    }
    if not real_generator:
        env["EREV_DOCKER_BUILD_MANIFEST_SCRIPT"] = str(_generator(scratch))
    env |= values
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _calls(scratch: Path) -> list[str]:
    path = scratch / "calls.log"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def _builds(scratch: Path) -> list[list[str]]:
    return [call.split() for call in _calls(scratch) if call.startswith("build ")]


def _generator_calls(scratch: Path) -> list[list[str]]:
    path = scratch / "calls.log.generator"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [line.split(" ") for line in lines]


def _ignored_and_untracked(repo: Path) -> str:
    return git(repo, "status", "--porcelain", "--ignored")


def _report(scratch: Path) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(
        (scratch / "run" / "reports" / "docker-build" / "report.json").read_text("utf-8")
    )
    return report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_script_parses_and_never_pushes() -> None:
    # DEP-5 test_docker_and_compose_rules (docker-build part): syntax, no push or login.
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
    text = SCRIPT.read_text(encoding="utf-8")
    assert "docker push" not in text and "docker login" not in text
    assert "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" in text
    assert "skipped-no-daemon" in text
    assert "image inspect" in text and "{{.Id}}" in text
    assert "git archive" in text, "one immutable context exported from HEAD"


def test_no_daemon_writes_skipped_report(scratch: Path) -> None:
    # DG-MK-docker-build step (1): without a daemon the report says so and the target exits 0.
    repo, head = _repo(scratch)
    result = _run(scratch, repo, STUB_DOCKER_INFO_RC="1")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" in lines
    assert lines[-1] == "OK docker-build"
    report = _report(scratch)
    assert report["result"] == "skipped-no-daemon"
    assert report["target"] == "docker-build" and report["exit_code"] == 0
    assert report["build_sha"] == head and report["worktree_dirty"] is False
    assert report["clean_source"] is False, "nothing was built"
    assert [call for call in _calls(scratch) if not call.startswith("info")] == []


def test_builds_three_images_from_one_exported_context(scratch: Path) -> None:
    # Steps (1b) to (3): one `git archive HEAD` context holding the manifest, three builds from it
    # tagged with the first 12 characters of the build sha, image ids and the attestation.
    repo, head = _repo(scratch)
    manifest = _embedded(scratch)
    result = _run(scratch, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "OK docker-build"
    # Step (0): one manifest step, for this root, embedded, written under the run directory.
    (generated,) = _generator_calls(scratch)
    assert generated[generated.index("--root") + 1] == str(repo)
    assert generated[generated.index("--out") + 1] == str(manifest)
    assert generated[generated.index("--reports-dir") + 1] == str(scratch / "run" / "reports")
    assert "--embedded" in generated and "--strict" not in generated
    assert json.loads(manifest.read_text("utf-8"))["build_sha"] == head
    builds = _builds(scratch)
    contexts = {build[-1] for build in builds}
    assert len(contexts) == 1, "every image builds from the same context"
    (context,) = contexts
    assert context != "." and context.startswith(str(scratch / "run" / "tmp" / "docker-context-"))
    assert not Path(context).exists(), "the scratch context is removed afterwards"
    assert [(b[b.index("-f") + 1], b[b.index("-t") + 1]) for b in builds] == [
        (f"{context}/deploy/docker/{name}.Dockerfile", f"erev-{name}:{head[:12]}")
        for name in IMAGES
    ]
    assert all("--no-cache" not in build and "--pull" not in build for build in builds)
    inspects = [call for call in _calls(scratch) if call.startswith("image inspect")]
    assert len(inspects) == 3 and all("--format {{.Id}}" in call for call in inspects)
    runs = [call.split() for call in _calls(scratch) if call.startswith("run ")]
    readbacks = [run for run in runs if "--user" not in run]
    assert [run[run.index("--entrypoint") + 2] for run in readbacks] == [
        f"erev-api:{head[:12]}",
        f"erev-worker:{head[:12]}",
    ], "the manifest is read back from the two Python images only"
    # Step (3a): every image is probed as uid 0 without a network, after the read-back.
    probes = [run for run in runs if "--user" in run]
    assert runs == readbacks + probes
    assert [[arg for arg in run if arg.startswith("erev-")] for run in probes] == [
        [f"erev-{name}:{head[:12]}"] for name in IMAGES
    ]
    for run in probes:
        assert run[run.index("--user") + 1] == "0" and run[run.index("--network") + 1] == "none"
        assert "--rm" in run
    assert [run[run.index("--entrypoint") + 1] for run in probes] == [
        "/app/.venv/bin/python",
        "/app/.venv/bin/python",
        "find",
    ]
    assert not any(call.startswith(("push", "login")) for call in _calls(scratch))

    report = _report(scratch)
    assert report["target"] == "docker-build"
    assert report["command"] == "make docker-build"
    assert report["build_sha"] == head and report["worktree_dirty"] is False
    assert report["exit_code"] == 0 and report["failures"] == []
    assert report["result"] == "built"
    assert report["counts"]["images"] == 3
    assert report["manifest_build_sha"] == head
    # The attestation binds the immutable context and the exact embedded manifest to the ids.
    assert report["tree_sha"] == git(repo, "rev-parse", "HEAD^{tree}")
    assert len(report["context_sha256"]) == 64
    assert report["manifest_sha256"] == _sha256(manifest)
    copy = Path(report["manifest_copy"])
    assert copy == manifest
    for name in ("api", "worker"):
        kept = scratch / f"calls.log.manifest-{name}"
        assert kept.read_bytes() == manifest.read_bytes(), "the context held the embedded manifest"
    assert report["head_after"] == head and report["worktree_dirty_after"] is False
    assert report["clean_source"] is True
    for name in IMAGES:
        image = report["images"][name]
        assert image["tag"] == f"erev-{name}:{head[:12]}"
        assert image["digest"].startswith("sha256:") and len(image["digest"]) == 71
        expected = _sha256(manifest) if name != "web" else None
        assert image["manifest_sha256"] == expected, name
        assert image["hardened"] is True, name
    assert report["images"]["api"]["digest"] != report["images"]["web"]["digest"]

    # NO_CACHE=1 adds --no-cache to every build (the fresh-build evidence of the sprint records).
    fresh = _run(scratch, repo, NO_CACHE="1")
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr
    builds = _builds(scratch)
    assert len(builds) == 3 and all("--no-cache" in build for build in builds)
    assert _report(scratch)["counts"]["no_cache"] is True


def test_missing_stale_or_image_bearing_manifest_fails_before_building(scratch: Path) -> None:
    # REL-03: an image without a manifest cannot start in production, a manifest of another build
    # would stamp the wrong release, and an embedded manifest never carries image identities
    # (acyclic attestation), so the build refuses all three before `docker build`.
    # Rev 1.97 (R-53 (4)): the script writes the manifest itself, so each case is what its manifest
    # step left behind (the stand-in generator) rather than a file an operator forgot to write.
    repo, head = _repo(scratch)
    missing = _run(scratch, repo, STUB_MANIFEST="absent")
    assert missing.returncode == 1, missing.stdout + missing.stderr
    assert missing.stdout.splitlines()[-1] == (
        "FAIL docker-build: the manifest step wrote no embedded manifest "
        "(see docker-build/release-manifest.log)"
    )
    assert _builds(scratch) == []
    report = _report(scratch)
    assert report["exit_code"] == 1 and report["failures"][0]["stage"] == "manifest"
    assert report["clean_source"] is False

    stale = _run(scratch, repo, STUB_MANIFEST="stale")
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert stale.stdout.splitlines()[-1] == (
        f"FAIL docker-build: the embedded manifest names build ffffffffffff but the captured "
        f"build is {head[:12]}; HEAD moved while the manifest was written, run the target again"
    )
    assert _builds(scratch) == []
    assert _report(scratch)["failures"][0]["stage"] == "manifest"

    bearing = _run(scratch, repo, STUB_MANIFEST="images")
    assert bearing.returncode == 1, bearing.stdout + bearing.stderr
    assert "carries image identities" in bearing.stdout.splitlines()[-1]
    assert _builds(scratch) == []
    assert _report(scratch)["failures"][0]["stage"] == "manifest"

    # An earlier run's embedded manifest is never taken for this run's.
    assert _run(scratch, repo).returncode == 0
    assert _embedded(scratch).is_file()
    again = _run(scratch, repo, STUB_MANIFEST="absent")
    assert again.returncode == 1 and "wrote no embedded manifest" in again.stdout.splitlines()[-1]
    assert not _embedded(scratch).exists()


def test_a_failed_manifest_step_fails_before_any_docker_call(scratch: Path) -> None:
    # Step (0): `STRICT=1` reaches the generator as --strict, and a generator that exits non-zero
    # (a gate that is not PASS under --strict) fails the run with its last lines, before `docker
    # info`; without STRICT the flag is absent (the main build test).
    repo, _ = _repo(scratch)
    result = _run(scratch, repo, STRICT="1", STUB_MANIFEST="fail")
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[-1] == (
        "FAIL docker-build: the manifest step failed (exit 1; "
        "see docker-build/release-manifest.log)"
    )
    assert "stand-in: ci FAIL (exit 1)" in lines, "the generator's own words are shown"
    (generated,) = _generator_calls(scratch)
    assert "--strict" in generated and "--embedded" in generated
    assert _calls(scratch) == [], "no docker call at all"
    report = _report(scratch)
    assert report["failures"] == [{"stage": "manifest", "exit_code": 1}]
    assert report["result"] == "failed" and report["clean_source"] is False


def test_the_generator_stand_in_is_test_only(scratch: Path) -> None:
    # EREV_DOCKER_BUILD_MANIFEST_SCRIPT would let a caller choose the manifest a release image
    # carries: honoured under EREV_ENV=test only, refused before the manifest step and any docker
    # call elsewhere.
    repo, _ = _repo(scratch)
    for environment in ("dev", "production", ""):
        result = _run(scratch, repo, EREV_ENV=environment)
        assert result.returncode == 1, (environment, result.stdout + result.stderr)
        assert result.stdout.splitlines()[-1] == (
            "FAIL docker-build: EREV_DOCKER_BUILD_MANIFEST_SCRIPT is a test-only override "
            "(EREV_ENV=test); unset it"
        )
        assert _generator_calls(scratch) == [] and _calls(scratch) == []
        assert _report(scratch)["failures"] == [{"stage": "manifest", "exit_code": 1}]


def test_the_working_tree_is_left_as_it_was(scratch: Path) -> None:
    # Ruling R-53 (4) (05 DPL-05 rev 1.53): with the REAL generator the target writes the embedded
    # manifest under the run directory and nowhere in the checkout. `git status --ignored` lists
    # nothing afterwards — release-manifest.json is git-ignored, so a plain status could not see it
    # — and no file of that name exists under the root. Before, the manifest step left the file at
    # the repository root, where the next development process read it.
    repo, head = _repo(scratch)
    assert _ignored_and_untracked(repo) == ""
    result = _run(scratch, repo, real_generator=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _ignored_and_untracked(repo) == "", "nothing new in the checkout, ignored or not"
    assert not list(repo.rglob("release-manifest*.json"))
    manifest = json.loads(_embedded(scratch).read_text("utf-8"))
    assert manifest["build_sha"] == head
    assert all(image == {"digest": None, "tag": None} for image in manifest["images"].values())
    report = _report(scratch)
    assert (report["result"], report["clean_source"]) == ("built", True)
    assert report["manifest_sha256"] == _sha256(_embedded(scratch))
    # The generator's own report names the file under the run directory as the manifest it wrote.
    own = json.loads(
        (scratch / "run" / "reports" / "release-manifest" / "report.json").read_text("utf-8")
    )
    assert own["embedded"] is True and own["manifest"] == str(_embedded(scratch))
    assert own["command"] == "make docker-build (embedded manifest)"
    log = scratch / "run" / "reports" / "docker-build" / "release-manifest.log"
    assert "OK release-manifest" in log.read_text("utf-8")


def test_a_root_manifest_is_neither_read_nor_replaced(scratch: Path) -> None:
    # A release-manifest.json at the repository root (`make release-manifest`, or the compose path
    # of the runbook) is not this target's: a stale one naming another build and carrying image
    # identities — both refusals when it was the input — changes nothing, and its bytes stay.
    repo, head = _repo(scratch)
    theirs = repo / "release-manifest.json"
    theirs.write_text(
        json.dumps({"build_sha": "0" * 40, "images": {"api": {"tag": "x", "digest": "y"}}}) + "\n",
        encoding="utf-8",
    )
    before = theirs.read_bytes()
    result = _run(scratch, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert theirs.read_bytes() == before
    report = _report(scratch)
    assert report["manifest_build_sha"] == head and report["clean_source"] is True
    assert (scratch / "calls.log.manifest-api").read_bytes() == _embedded(scratch).read_bytes()
    assert (scratch / "calls.log.manifest-api").read_bytes() != before


def test_no_repository_fails_closed(scratch: Path) -> None:
    plain = scratch / "plain"
    plain.mkdir()
    env = {"GIT_CEILING_DIRECTORIES": str(scratch)}
    result = _run(scratch, plain, **env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no git repository" in result.stdout.splitlines()[-1]
    assert _builds(scratch) == []
    assert _report(scratch)["failures"][0]["stage"] == "source"
    assert _generator_calls(scratch) == [], "no manifest is written for a root without a build"


def test_failed_build_is_reported(scratch: Path) -> None:
    repo, head = _repo(scratch)
    result = _run(scratch, repo, STUB_DOCKER_BUILD_RC="7")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "FAIL docker-build: docker build api failed (exit 7)"
    report = _report(scratch)
    assert report["exit_code"] == 1 and report["result"] == "failed"
    assert report["failures"] == [{"stage": "build", "image": "api", "exit_code": 7}]
    assert report["images"]["api"]["tag"] == f"erev-api:{head[:12]}"
    assert report["images"]["api"]["digest"] is None
    assert report["clean_source"] is False
    assert len(_builds(scratch)) == 1


def test_context_mutation_between_builds_is_rejected(scratch: Path) -> None:
    # PRV-2: the exported context is hashed before every build; a change (the stand-in edits the
    # context during the api build) fails the run before the worker build and never labels it clean.
    repo, _ = _repo(scratch)
    result = _run(scratch, repo, STUB_MUTATE_CONTEXT="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        "FAIL docker-build: build context changed before the worker build; "
        "the run is not a clean release"
    )
    assert len(_builds(scratch)) == 1
    report = _report(scratch)
    assert report["failures"] == [{"stage": "context", "image": "worker", "exit_code": 1}]
    assert report["clean_source"] is False


def test_source_mutation_during_builds_is_rejected(scratch: Path) -> None:
    # PRV-2: the images come from `git archive HEAD`, so an edit of the worktree during the builds
    # never enters them, but the run is not a clean release: the dirty state changed.
    repo, head = _repo(scratch)
    result = _run(scratch, repo, STUB_MUTATE_SOURCE="1")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith(
        "FAIL docker-build: source changed during the builds"
    )
    assert len(_builds(scratch)) == 3, "the builds themselves consumed the unchanged context"
    report = _report(scratch)
    assert report["failures"] == [{"stage": "source", "exit_code": 1}]
    assert report["worktree_dirty"] is False and report["worktree_dirty_after"] is True
    assert report["head_after"] == head
    assert report["clean_source"] is False
    assert all(report["images"][name]["digest"] for name in IMAGES), "ids recorded, run not clean"


def test_dirty_worktree_builds_from_head_but_is_not_clean(scratch: Path) -> None:
    repo, _ = _repo(scratch)
    (repo / "README.md").write_text("edited before the build\n", encoding="utf-8")
    result = _run(scratch, repo)
    assert result.returncode == 0, result.stdout + result.stderr
    report = _report(scratch)
    assert report["result"] == "built"
    assert report["worktree_dirty"] is True and report["worktree_dirty_after"] is True
    assert report["clean_source"] is False, "a dirty worktree never labels a clean release"


def test_manifest_inside_image_must_be_the_embedded_manifest(scratch: Path) -> None:
    # Step (3): the manifest read back from the api and worker images is byte-identical to the
    # embedded copy; the stand-in answers with another file, so the attestation fails.
    repo, _ = _repo(scratch)
    other = scratch / "other-manifest.json"
    other.write_text('{"build_sha": "not the embedded bytes"}\n', encoding="utf-8")
    result = _run(scratch, repo, STUB_MANIFEST_FILE=str(other))
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith(
        "FAIL docker-build: the manifest inside erev-api:"
    )
    assert "is not the embedded manifest" in result.stdout.splitlines()[-1]
    report = _report(scratch)
    assert report["failures"] == [{"stage": "attestation", "image": "api", "exit_code": 0}]
    assert report["clean_source"] is False
    assert report["images"]["api"]["manifest_sha256"] is None


def _second_commit(repo: Path, head_a: str) -> tuple[str, str, str]:
    """Commit B with other source on a side branch; HEAD back at A. Returns (B, tree A, tree B)."""
    git(repo, "checkout", "-q", "-b", "other")
    head_b = commit(repo, {"README.md": "source-B\n"}, "B")
    git(repo, "checkout", "-q", "main")
    assert git(repo, "rev-parse", "HEAD") == head_a
    tree_a = git(repo, "rev-parse", f"{head_a}^{{tree}}")
    tree_b = git(repo, "rev-parse", f"{head_b}^{{tree}}")
    assert tree_a != tree_b
    return head_b, tree_a, tree_b


def _readmes(scratch: Path) -> dict[str, str]:
    return {
        name: (scratch / f"calls.log.readme-{name}").read_text(encoding="utf-8") for name in IMAGES
    }


def test_transient_head_movement_still_builds_the_captured_commit(scratch: Path) -> None:
    # Codex build-source binding (04891a4): HEAD moves A → B right after BUILD_SHA is captured and
    # back to A after the last build. The context, the tree and the attestation must all be A's:
    # the archive and the tree are resolved from the captured commit, never from the HEAD name.
    repo, head_a = _repo(scratch)
    head_b, tree_a, _ = _second_commit(repo, head_a)
    result = _run(scratch, repo, STUB_FLIP_TO=head_b, STUB_FLIP_BACK=head_a)
    assert result.returncode == 0, result.stdout + result.stderr
    report = _report(scratch)
    assert (report["result"], report["clean_source"]) == ("built", True)
    assert report["build_sha"] == head_a and report["head_after"] == head_a
    assert report["tree_sha"] == tree_a, "the tree of the captured commit, not of the moved HEAD"
    assert _readmes(scratch) == {name: "scratch\n" for name in IMAGES}, "every build saw A"
    assert git(repo, "rev-parse", "HEAD") == head_a


def test_persistent_head_movement_is_refused(scratch: Path) -> None:
    # A → B that stays: the context is still A's (captured commit), and the endpoint check refuses
    # the run because HEAD no longer names the build; nothing is labelled clean.
    repo, head_a = _repo(scratch)
    head_b, tree_a, _ = _second_commit(repo, head_a)
    result = _run(scratch, repo, STUB_FLIP_TO=head_b)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1].startswith(
        "FAIL docker-build: source changed during the builds"
    )
    report = _report(scratch)
    assert report["failures"] == [{"stage": "source", "exit_code": 1}]
    assert report["clean_source"] is False
    assert (report["build_sha"], report["head_after"]) == (head_a, head_b)
    assert report["tree_sha"] == tree_a
    assert _readmes(scratch) == {name: "scratch\n" for name in IMAGES}
    git(repo, "checkout", "-q", "main")


def test_manifest_is_written_once_under_the_run_directory() -> None:
    # Rev 1.97 (R-53 (4)): one manifest step writes the embedded manifest to the retained copy under
    # the run directory; that file feeds the validation, the context and the attestation. There is
    # no live file at the repository root any more, so nothing reads or writes one (before: the
    # root file was read exactly once into this copy).
    text = SCRIPT.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert 'MANIFEST_COPY="$REPORT_DIR/release-manifest.embedded.json"' in body
    assert body.count('--out "$MANIFEST_COPY"') == 1 and body.count('"$GENERATOR"') == 1
    assert body.count("--embedded") == 1
    assert "$ROOT/release-manifest.json" not in body and '"$MANIFEST"' not in body
    assert "release-manifest EMBEDDED=1" not in body, (
        "no make call: the script is the manifest step"
    )
    copies = [line.strip() for line in body.splitlines() if "release-manifest.json" in line]
    assert [line for line in copies if line.startswith("cp ")] == [
        'cp "$MANIFEST_COPY" "$CTX/release-manifest.json" || { FAIL_STAGE="context"; '
        'fail "cannot copy the embedded manifest into the context"; }'
    ], copies
    assert body.index('--out "$MANIFEST_COPY"') < body.index('"$DOCKER" info')
    assert body.index('"$DOCKER" info') < body.index(
        'cp "$MANIFEST_COPY" "$CTX/release-manifest.json"'
    )
    assert 'git -C "$ROOT" archive --format=tar "$BUILD_SHA"' in body
    assert 'git -C "$ROOT" rev-parse "${BUILD_SHA}^{tree}"' in body
    assert "archive --format=tar HEAD" not in body and "HEAD^{tree}" not in body


def test_an_image_with_pip_or_a_setuid_file_fails_the_build(scratch: Path) -> None:
    # Step (3a) (ruling R-37 (b); 05 SAR-33, DPL-01 to DPL-05): the probe's findings fail the run,
    # name the image and what was found, and the image is recorded as not hardened. The three
    # images are probed in order, so the first finding stops the run.
    repo, head = _repo(scratch)
    findings = json.dumps(
        {
            "pip": ["/usr/local/bin/pip3", "/usr/local/lib/python3.12/site-packages/pip"],
            "setuid": ["/usr/bin/su"],
        }
    )
    result = _run(scratch, repo, STUB_PROBE_WORKER=findings)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        f"FAIL docker-build: erev-worker:{head[:12]} is not hardened (05 SAR-33): "
        "pip: /usr/local/bin/pip3, /usr/local/lib/python3.12/site-packages/pip; "
        "setuid or setgid: /usr/bin/su"
    )
    report = _report(scratch)
    assert report["failures"] == [{"stage": "hardening", "image": "worker", "exit_code": 1}]
    assert report["result"] == "failed" and report["clean_source"] is False
    assert [report["images"][name]["hardened"] for name in IMAGES] == [True, False, None]
    assert all(report["images"][name]["digest"] for name in IMAGES), "ids recorded, run not clean"

    # The web image has no interpreter: `find` lists the paths, one per line.
    result = _run(scratch, repo, STUB_PROBE_WEB="/bin/bbsuid\n/usr/bin/pip\n")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        f"FAIL docker-build: erev-web:{head[:12]} is not hardened (05 SAR-33): "
        "pip: /usr/bin/pip; setuid or setgid: /bin/bbsuid"
    )
    report = _report(scratch)
    assert report["failures"] == [{"stage": "hardening", "image": "web", "exit_code": 1}]
    assert [report["images"][name]["hardened"] for name in IMAGES] == [True, True, False]

    # A probe that cannot run, or prints no verdict, is a failure, never a pass.
    result = _run(scratch, repo, STUB_PROBE_RC="125")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        f"FAIL docker-build: the hardening probe of erev-api:{head[:12]} failed (exit 125)"
    )
    assert _report(scratch)["failures"] == [
        {"stage": "hardening", "image": "api", "exit_code": 125}
    ]
    result = _run(scratch, repo, STUB_PROBE_API="Traceback (most recent call last):")
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == (
        f"FAIL docker-build: erev-api:{head[:12]} is not hardened (05 SAR-33): "
        "the probe printed no verdict"
    )
    assert _report(scratch)["images"]["api"]["hardened"] is False


def test_the_probe_program_reads_both_interpreters_and_the_whole_root_filesystem() -> None:
    # The program the api and worker images read from standard input, taken from the script and run
    # here function by function: importable pip or ensurepip, the pip entries of each interpreter's
    # site-packages and launcher directory, and every regular file with a setuid or setgid bit under
    # a root (one file system; a setgid directory is not a finding).
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("<<'PROBE'\n") + len("<<'PROBE'\n")
    program = text[start : text.index("\nPROBE\n", start)]
    namespace: dict[str, Any] = {"__name__": "probe"}
    exec(compile(program, "image-probe", "exec"), namespace)  # noqa: S102 - the repository's own text
    base = ROOT / ".run" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        root = Path(directory)
        (root / "usr" / "bin").mkdir(parents=True)
        plain, setuid, setgid = (root / "usr" / "bin" / n for n in ("plain", "su", "wall"))
        for file in (plain, setuid, setgid):
            file.write_text("x", encoding="utf-8")
        plain.chmod(0o755)
        setuid.chmod(0o4755)
        # macOS clears setgid for an inherited group the caller does not belong to
        # (for example wheel under /private/tmp). Give our fixture the caller's group.
        os.chown(setgid, -1, os.getgid())
        setgid.chmod(0o2755)
        shared = root / "usr" / "shared"
        shared.mkdir()
        os.chown(shared, -1, os.getgid())
        shared.chmod(0o2775)
        assert stat.S_IMODE(setuid.stat().st_mode) == 0o4755
        assert stat.S_IMODE(setgid.stat().st_mode) == 0o2755
        assert stat.S_IMODE(shared.stat().st_mode) == 0o2775
        (root / "usr" / "bin" / "link").symlink_to(setuid)
        assert namespace["setuid_files"](str(root)) == sorted([str(setuid), str(setgid)])

        prefix = root / "prefix"
        version = f"python{sys.version_info.major}.{sys.version_info.minor}"
        packages = prefix / "lib" / version / "site-packages"
        (packages / "pip").mkdir(parents=True)
        (packages / "pip-25.0.1.dist-info").mkdir()
        (packages / "pipdeptree").mkdir()  # another distribution, not a finding
        (prefix / "bin").mkdir()
        for name in ("pip", "pip3", "pip3.12", "python3", "pipx"):
            (prefix / "bin" / name).write_text("x", encoding="utf-8")
        assert namespace["pip_files"]([str(prefix), str(root / "absent")]) == [
            str(prefix / "bin" / "pip"),
            str(prefix / "bin" / "pip3"),
            str(prefix / "bin" / "pip3.12"),
            str(packages / "pip"),
            str(packages / "pip-25.0.1.dist-info"),
        ]

    def only_ensurepip(name: str) -> object | None:
        return object() if name == "ensurepip" else None

    assert namespace["pip_modules"](lambda name: None) == []
    assert namespace["pip_modules"](only_ensurepip) == [
        f"module ensurepip importable by {sys.executable}"
    ]
    assert namespace["pip_modules"](lambda name: object()) == [
        f"module pip importable by {sys.executable}",
        f"module ensurepip importable by {sys.executable}",
    ]
