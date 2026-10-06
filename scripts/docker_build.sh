#!/usr/bin/env bash
# make docker-build (docs/dev-guide.md §4.5 DG-MK-docker-build; §4.1 DG-MK-00g, DG-MK-00h; §10.3
# DG-FORBID-07; 05 §8.1 DPL-01, DPL-02, DPL-05; §7.8 REL-01, REL-03; BUILD_SPEC DEP-5, SOP-2).
#   (0) capture the build sha, the dirty state and the start time, then, in a git repository,
#       write the embedded release manifest (scripts/release_manifest.py --embedded: the pre-build
#       manifest the api and worker images carry, no image identities inside it; STRICT=1 adds
#       --strict) to .run/reports/docker-build/release-manifest.embedded.json - under the run
#       directory and nowhere else. release-manifest.json at the repository root is neither read
#       nor written, so the working tree is as it was when the target ends (05 DPL-05 rev 1.53,
#       ruling R-53 (4): the target's manifest step used to leave the file at the root, and the
#       checkout's next development process refused to start once the schema revision moved). A
#       manifest step that exits non-zero fails the run before any docker call;
#   (1) without a Docker daemon write {"result": "skipped-no-daemon"}, print
#       "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable" and exit 0;
#   (1a) refuse when there is no git repository, or when the embedded manifest is absent, names
#        another build than the captured one or carries image identities: the api and worker
#        images copy the manifest into /app and a production process refuses to start without it
#        (REL-03);
#   (1b) export ONE immutable build context with `git archive <captured build sha>` (never the
#        mutable HEAD name) into a scratch directory under .run/tmp and copy the embedded manifest
#        into it as release-manifest.json (the file under the run directory is the only copy
#        outside the context and the only bytes validated, embedded and attested); record the tree
#        sha of the captured commit, the context's content hash and the manifest's SHA-256;
#   (2) build deploy/docker/api.Dockerfile, worker.Dockerfile and web.Dockerfile FROM THAT CONTEXT
#       with the tags erev-api:<first 12 characters of the build sha>, erev-worker:<…>,
#       erev-web:<…>; NO_CACHE=1 adds --no-cache; the context hash is verified before every build
#       and after the last one, and HEAD and the dirty state are sampled again at the end: a change
#       fails the run, which is then never labelled clean;
#   (3) read /app/release-manifest.json back from the api and worker images and require its SHA-256
#       to equal the embedded manifest's;
#   (3a) probe every image as uid 0 without a network (05 SAR-33, DPL-01 to DPL-05 rev 1.53, ruling
#        R-37 (b)): no pip and no ensurepip for either interpreter of the api and worker images,
#        none in the web image, and no regular file with a setuid or setgid bit in any of the
#        three; a finding fails the run (stage "hardening");
#       then record images: {api, worker, web}: {tag, digest, manifest_sha256, hardened} with the
#       local image id from `docker image inspect --format '{{.Id}}'` (never pushed, so no registry
#       digest, D-47) in .run/reports/docker-build/report.json, the post-build attestation that
#       binds build_sha, tree_sha, context_sha256, manifest_sha256 and the image ids.
# The script never pushes an image or logs in to a registry (DG-FORBID-07). The final line is
# "OK docker-build" or "FAIL docker-build: <reason>" (DG-MK-00a).
# Test-only overrides (backend/tests/unit/deploy/test_docker_build.py): EREV_DOCKER_BIN names the
# docker binary and EREV_DOCKER_BUILD_ROOT a scratch repository root; EREV_RUN_DIR as in proc.sh;
# EREV_DOCKER_BUILD_MANIFEST_SCRIPT names a stand-in for scripts/release_manifest.py and is
# honoured under EREV_ENV=test only (elsewhere the run is refused before the manifest step: the
# manifest a release image carries is never a caller's choice).
set -uo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${EREV_DOCKER_BUILD_ROOT:-$SCRIPT_ROOT}"
RUN_DIR="${EREV_RUN_DIR:-.run}"
[[ "$RUN_DIR" == /* ]] || RUN_DIR="$ROOT/$RUN_DIR"
PY="$SCRIPT_ROOT/backend/.venv/bin/python"
DOCKER="${EREV_DOCKER_BIN:-docker}"
COMMAND="${EREV_DOCKER_BUILD_COMMAND:-make docker-build}"
NO_CACHE="${NO_CACHE:-}"
STRICT="${STRICT:-}"
TARGET="docker-build"
REPORT_DIR="$RUN_DIR/reports/$TARGET"
# The embedded manifest of this run: written here by step (0), copied into the context by (1b).
MANIFEST_COPY="$REPORT_DIR/release-manifest.embedded.json"
MANIFEST_LOG="$REPORT_DIR/release-manifest.log"
GENERATOR="$SCRIPT_ROOT/scripts/release_manifest.py"
GENERATOR_REJECTED=""
if [[ -n "${EREV_DOCKER_BUILD_MANIFEST_SCRIPT:-}" ]]; then
  if [[ "${EREV_ENV:-}" == "test" ]]; then GENERATOR="$EREV_DOCKER_BUILD_MANIFEST_SCRIPT"; else GENERATOR_REJECTED="1"; fi
fi
IMAGES="api worker web"
# Images whose runtime stage carries the manifest (DPL-01, DPL-02); web serves the SPA only.
MANIFEST_IMAGES="api worker"

IMG_TAGS=""
IMG_DIGESTS=""
IMG_MANIFESTS=""
IMG_HARDENED=""
MANIFEST_SHA=""
MANIFEST_SHA256=""
TREE_SHA=""
CONTEXT_SHA256=""
HEAD_AFTER=""
DIRTY_AFTER=""
FAIL_STAGE=""
FAIL_IMAGE=""
FAIL_EXIT=""
CTX=""

utc_now() {
  "$PY" -c 'import datetime as d; print(d.datetime.now(d.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'
}

file_sha256() {
  "$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
}

# Content hash of a directory: sorted relative paths and file bytes (symlinks by their target text).
tree_sha256() {
  "$PY" - "$1" <<'PY'
import hashlib
import os
import sys

root = sys.argv[1]
digest = hashlib.sha256()
for dirpath, dirnames, filenames in os.walk(root):
    dirnames.sort()
    for name in sorted(filenames):
        path = os.path.join(dirpath, name)
        relative = os.path.relpath(path, root).encode()
        digest.update(relative + b"\0")
        if os.path.islink(path):
            digest.update(b"link:" + os.readlink(path).encode() + b"\0")
        else:
            with open(path, "rb") as handle:
                digest.update(hashlib.sha256(handle.read()).digest() + b"\0")
print(digest.hexdigest())
PY
}

sample_dirty() {
  if [[ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]]; then echo "true"; else echo "false"; fi
}

# write_report <exit code> <result>: the DG-MK-00g report plus the attestation facts, all passed
# through the environment so no value is interpolated into code.
write_report() {
  mkdir -p "$REPORT_DIR"
  REPORT_TARGET="$TARGET" REPORT_COMMAND="$COMMAND" REPORT_BUILD_SHA="$BUILD_SHA" \
    REPORT_DIRTY="$DIRTY" REPORT_STARTED="$STARTED_AT" REPORT_FINISHED="$(utc_now)" \
    REPORT_EXIT="$1" REPORT_RESULT="$2" REPORT_IMAGES="$IMAGES" REPORT_TAGS="$IMG_TAGS" \
    REPORT_DIGESTS="$IMG_DIGESTS" REPORT_IMAGE_MANIFESTS="$IMG_MANIFESTS" \
    REPORT_HARDENED="$IMG_HARDENED" \
    REPORT_MANIFEST_SHA="$MANIFEST_SHA" REPORT_MANIFEST_SHA256="$MANIFEST_SHA256" \
    REPORT_MANIFEST_COPY="$MANIFEST_COPY" REPORT_TREE_SHA="$TREE_SHA" \
    REPORT_CONTEXT_SHA256="$CONTEXT_SHA256" REPORT_HEAD_AFTER="$HEAD_AFTER" \
    REPORT_DIRTY_AFTER="$DIRTY_AFTER" REPORT_NO_CACHE="$NO_CACHE" \
    REPORT_FAIL_STAGE="$FAIL_STAGE" REPORT_FAIL_IMAGE="$FAIL_IMAGE" REPORT_FAIL_EXIT="$FAIL_EXIT" \
    "$PY" - "$REPORT_DIR/report.json" <<'PY'
import json
import os
import sys

env = os.environ


def pairs(value):
    found = {}
    for token in value.split():
        name, _, rest = token.partition("=")
        found[name] = None if rest in ("", "-") else rest
    return found


def text(value):
    return value or None


tags, digests, manifests, hardened = (
    pairs(env["REPORT_TAGS"]),
    pairs(env["REPORT_DIGESTS"]),
    pairs(env["REPORT_IMAGE_MANIFESTS"]),
    pairs(env["REPORT_HARDENED"]),
)
images = {
    name: {
        "tag": tags.get(name),
        "digest": digests.get(name),
        "manifest_sha256": manifests.get(name),
        # Step (3a): true after a clean probe, false after a finding, null when not probed.
        "hardened": {"true": True, "false": False}.get(hardened.get(name) or ""),
    }
    for name in env["REPORT_IMAGES"].split()
}
failures = []
if env["REPORT_FAIL_STAGE"]:
    failure = {"stage": env["REPORT_FAIL_STAGE"], "exit_code": int(env["REPORT_FAIL_EXIT"] or 1)}
    if env["REPORT_FAIL_IMAGE"]:
        failure = {"stage": failure["stage"], "image": env["REPORT_FAIL_IMAGE"], "exit_code": failure["exit_code"]}
    failures.append(failure)
dirty = env["REPORT_DIRTY"] == "true"
dirty_after = None if env["REPORT_DIRTY_AFTER"] == "" else env["REPORT_DIRTY_AFTER"] == "true"
head_after = text(env["REPORT_HEAD_AFTER"])
built = env["REPORT_RESULT"] == "built"
clean_source = built and not dirty and dirty_after is False and head_after == env["REPORT_BUILD_SHA"]
report = {
    "target": env["REPORT_TARGET"],
    "command": env["REPORT_COMMAND"],
    "build_sha": env["REPORT_BUILD_SHA"],
    "worktree_dirty": dirty,
    "started_at": env["REPORT_STARTED"],
    "finished_at": env["REPORT_FINISHED"],
    "exit_code": int(env["REPORT_EXIT"]),
    "result": env["REPORT_RESULT"],
    "counts": {
        "images": sum(1 for image in images.values() if image["digest"]),
        "no_cache": env["REPORT_NO_CACHE"] == "1",
    },
    "failures": failures,
    "images": images,
    # Attestation: the immutable source context and the exact embedded manifest these ids bind to.
    "tree_sha": text(env["REPORT_TREE_SHA"]),
    "context_sha256": text(env["REPORT_CONTEXT_SHA256"]),
    "manifest_build_sha": text(env["REPORT_MANIFEST_SHA"]),
    "manifest_sha256": text(env["REPORT_MANIFEST_SHA256"]),
    "manifest_copy": text(env["REPORT_MANIFEST_COPY"]) if env["REPORT_MANIFEST_SHA256"] else None,
    "head_after": head_after,
    "worktree_dirty_after": dirty_after,
    "clean_source": clean_source,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY
}

cleanup() {
  [[ -n "$CTX" && -d "$CTX" ]] && rm -rf "$CTX"
}
trap cleanup EXIT

fail() {
  HEAD_AFTER="${HEAD_AFTER:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)}"
  DIRTY_AFTER="${DIRTY_AFTER:-$(sample_dirty)}"
  write_report 1 "failed"
  echo "FAIL $TARGET: $1"
  exit 1
}

# probe_python <tag>: the hardening probe of an image that carries the interpreter (step 3a).
# The program is read from standard input; it prints one JSON object {"pip": [...], "setuid": [...]}.
probe_python() {
  "$DOCKER" run --rm -i --user 0 --network none --entrypoint /app/.venv/bin/python "$1" - <<'PROBE'
import importlib.util
import json
import os
import stat
import sys


def pip_modules(find=importlib.util.find_spec):
    """pip or ensurepip importable by this interpreter (ensurepip could install pip again)."""
    return [
        f"module {name} importable by {sys.executable}"
        for name in ("pip", "ensurepip")
        if find(name) is not None
    ]


def pip_files(prefixes):
    """The pip launchers and the pip entries of site-packages under each interpreter prefix."""
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    found = []
    for prefix in prefixes:
        for directory, wanted in (
            (os.path.join(prefix, "bin"), lambda name: name == "pip" or name.startswith("pip3")),
            (
                os.path.join(prefix, "lib", version, "site-packages"),
                lambda name: name == "pip" or name.startswith("pip-"),
            ),
        ):
            if os.path.isdir(directory):
                found += [
                    os.path.join(directory, name)
                    for name in sorted(os.listdir(directory))
                    if wanted(name)
                ]
    return found


def setuid_files(root):
    """Every regular file under root, on root's own file system, with a setuid or setgid bit."""
    device = os.lstat(root).st_dev
    found = []
    for directory, names, files in os.walk(root):
        names[:] = [n for n in names if os.lstat(os.path.join(directory, n)).st_dev == device]
        for name in files:
            path = os.path.join(directory, name)
            try:
                mode = os.lstat(path).st_mode
            except OSError:
                continue
            if stat.S_ISREG(mode) and mode & (stat.S_ISUID | stat.S_ISGID):
                found.append(path)
    return sorted(found)


if __name__ == "__main__":
    prefixes = list(dict.fromkeys((sys.prefix, sys.base_prefix)))
    verdict = {"pip": pip_modules() + pip_files(prefixes), "setuid": setuid_files("/")}
    json.dump(verdict, sys.stdout)
PROBE
}

# probe_files <tag>: the same two classes in an image without an interpreter, one path per line.
probe_files() {
  "$DOCKER" run --rm --user 0 --network none --entrypoint find "$1" / -xdev \
    \( -type f -perm /6000 -o -name pip -o -name 'pip3*' -o -name ensurepip \) -print </dev/null
}

# probe_verdict <json|lines>: reads a probe's output; prints "OK" or what was found.
probe_verdict() {
  "$PY" -c '
import json, os, sys

kind, raw = sys.argv[1], sys.stdin.read()
if kind == "json":
    try:
        found = json.loads(raw)
        pip, setuid = list(found["pip"]), list(found["setuid"])
    except (ValueError, KeyError, TypeError):
        print("the probe printed no verdict")
        sys.exit(0)
else:
    lines = [line for line in raw.splitlines() if line.strip()]
    named = lambda path: os.path.basename(path) in ("pip", "ensurepip") or os.path.basename(path).startswith("pip3")
    pip, setuid = [l for l in lines if named(l)], [l for l in lines if not named(l)]

def some(paths):
    return ", ".join(paths[:4]) + (f" (and {len(paths) - 4} more)" if len(paths) > 4 else "")

parts = [f"{label}: {some(paths)}" for label, paths in (("pip", pip), ("setuid or setgid", setuid)) if paths]
print("; ".join(parts) if parts else "OK")
' "$1"
}

BUILD_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
[[ "$BUILD_SHA" =~ ^[0-9a-f]{40}$ ]] || BUILD_SHA="nogit"
DIRTY="$(sample_dirty)"
STARTED_AT="$(utc_now)"

# (0) The embedded manifest of this build, written under the run directory (05 DPL-05 rev 1.53,
# ruling R-53 (4)): nothing is read from or written to the repository root. A retained copy of an
# earlier run is removed first, so it is never taken for this run's.
if [[ -n "$GENERATOR_REJECTED" ]]; then
  FAIL_STAGE="manifest"
  fail "EREV_DOCKER_BUILD_MANIFEST_SCRIPT is a test-only override (EREV_ENV=test); unset it"
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR/tmp"
rm -f "$MANIFEST_COPY"
if [[ "$BUILD_SHA" != "nogit" ]]; then
  STRICT_FLAG=""
  [[ "$STRICT" == "1" ]] && STRICT_FLAG="--strict"
  # shellcheck disable=SC2086
  "$PY" "$GENERATOR" --root "$ROOT" --reports-dir "$RUN_DIR/reports" --embedded --out "$MANIFEST_COPY" \
    --command "$COMMAND (embedded manifest)" $STRICT_FLAG >"$MANIFEST_LOG" 2>&1
  rc=$?
  if [[ $rc -ne 0 ]]; then
    tail -n 20 "$MANIFEST_LOG"
    FAIL_STAGE="manifest"
    FAIL_EXIT="$rc"
    fail "the manifest step failed (exit $rc; see $TARGET/$(basename "$MANIFEST_LOG"))"
  fi
fi

# (1) DG-MK-docker-build: no daemon, no build; the supervisor verifies later.
if ! "$DOCKER" info >/dev/null 2>&1; then
  write_report 0 "skipped-no-daemon"
  echo "SUPERVISOR VERIFICATION NEEDED: Docker daemon unavailable"
  echo "OK $TARGET"
  exit 0
fi

# (1a) REL-03: a repository to export from, and a manifest that describes this build. Validation,
# the context and the attestation all use the one file step (0) wrote, so the validated and the
# embedded bytes cannot differ (a change in between fails the read-back of step 3).
if [[ "$BUILD_SHA" == "nogit" ]]; then
  FAIL_STAGE="source"
  fail "no git repository at the build root; an immutable context needs HEAD"
fi
if [[ ! -f "$MANIFEST_COPY" ]]; then
  FAIL_STAGE="manifest"
  fail "the manifest step wrote no embedded manifest (see $TARGET/$(basename "$MANIFEST_LOG"))"
fi
MANIFEST_SHA="$("$PY" -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d.get("build_sha") or "")' "$MANIFEST_COPY" 2>/dev/null || true)"
if [[ "$MANIFEST_SHA" != "$BUILD_SHA" ]]; then
  FAIL_STAGE="manifest"
  fail "the embedded manifest names build ${MANIFEST_SHA:0:12} but the captured build is ${BUILD_SHA:0:12}; HEAD moved while the manifest was written, run the target again"
fi
# The embedded manifest never carries image identities (acyclic: the attestation binds them).
if ! "$PY" -c 'import json, sys; d = json.load(open(sys.argv[1])); sys.exit(0 if all(v.get("tag") is None and v.get("digest") is None for v in d.get("images", {}).values()) else 1)' "$MANIFEST_COPY"; then
  FAIL_STAGE="manifest"
  fail "the embedded manifest carries image identities; the manifest step must write the pre-build manifest"
fi
MANIFEST_SHA256="$(file_sha256 "$MANIFEST_COPY")"

# (1b) One immutable context: the CAPTURED commit exported by git archive (a HEAD that moves
# meanwhile changes nothing here and is caught by the endpoint check), plus the embedded manifest.
CTX="$(mktemp -d "$RUN_DIR/tmp/docker-context-${BUILD_SHA:0:12}-XXXXXX")" || { FAIL_STAGE="context"; fail "cannot create the build context directory"; }
if ! (git -C "$ROOT" archive --format=tar "$BUILD_SHA" | tar -x -C "$CTX"); then
  FAIL_STAGE="context"
  fail "git archive ${BUILD_SHA:0:12} failed"
fi
cp "$MANIFEST_COPY" "$CTX/release-manifest.json" || { FAIL_STAGE="context"; fail "cannot copy the embedded manifest into the context"; }
TREE_SHA="$(git -C "$ROOT" rev-parse "${BUILD_SHA}^{tree}")"
CONTEXT_SHA256="$(tree_sha256 "$CTX")"
echo "$TARGET: context $CTX tree $TREE_SHA manifest sha256 $MANIFEST_SHA256"

# (2) Build every image from the exported context; verify the context before each build.
NO_CACHE_FLAG=""
[[ "$NO_CACHE" == "1" ]] && NO_CACHE_FLAG="--no-cache"
for name in $IMAGES; do
  if [[ "$(tree_sha256 "$CTX")" != "$CONTEXT_SHA256" ]]; then
    FAIL_STAGE="context"
    FAIL_IMAGE="$name"
    fail "build context changed before the $name build; the run is not a clean release"
  fi
  tag="erev-$name:${BUILD_SHA:0:12}"
  IMG_TAGS="$IMG_TAGS $name=$tag"
  log="$REPORT_DIR/$name.log"
  echo "== $TARGET: $name -> $tag (log $log) =="
  # shellcheck disable=SC2086
  "$DOCKER" build $NO_CACHE_FLAG -f "$CTX/deploy/docker/$name.Dockerfile" -t "$tag" "$CTX" >"$log" 2>&1
  rc=$?
  if [[ $rc -ne 0 ]]; then
    tail -n 20 "$log"
    FAIL_STAGE="build"
    FAIL_IMAGE="$name"
    FAIL_EXIT="$rc"
    fail "docker build $name failed (exit $rc)"
  fi
  digest="$("$DOCKER" image inspect --format '{{.Id}}' "$tag" 2>>"$log")"
  rc=$?
  if [[ $rc -ne 0 || -z "$digest" ]]; then
    FAIL_STAGE="inspect"
    FAIL_IMAGE="$name"
    FAIL_EXIT="$rc"
    fail "docker image inspect $tag failed (exit $rc)"
  fi
  IMG_DIGESTS="$IMG_DIGESTS $name=$digest"
  echo "$TARGET: $tag $digest"
done

# Source and context unchanged for the whole run, else the release is not clean.
if [[ "$(tree_sha256 "$CTX")" != "$CONTEXT_SHA256" ]]; then
  FAIL_STAGE="context"
  fail "build context changed during the builds; the run is not a clean release"
fi
HEAD_AFTER="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
DIRTY_AFTER="$(sample_dirty)"
if [[ "$HEAD_AFTER" != "$BUILD_SHA" || "$DIRTY_AFTER" != "$DIRTY" ]]; then
  FAIL_STAGE="source"
  fail "source changed during the builds (HEAD ${HEAD_AFTER:0:12}, dirty $DIRTY_AFTER); the run is not a clean release"
fi

# (3) Attestation: the manifest inside each Python image is byte-identical to the embedded copy.
for name in $MANIFEST_IMAGES; do
  tag="erev-$name:${BUILD_SHA:0:12}"
  inside="$("$DOCKER" run --rm --entrypoint /app/.venv/bin/python "$tag" -c 'import hashlib, sys; sys.stdout.write(hashlib.sha256(open("/app/release-manifest.json", "rb").read()).hexdigest())' 2>>"$REPORT_DIR/$name.log")"
  rc=$?
  if [[ $rc -ne 0 || "$inside" != "$MANIFEST_SHA256" ]]; then
    FAIL_STAGE="attestation"
    FAIL_IMAGE="$name"
    FAIL_EXIT="$rc"
    fail "the manifest inside $tag (${inside:0:12}) is not the embedded manifest (${MANIFEST_SHA256:0:12})"
  fi
  IMG_MANIFESTS="$IMG_MANIFESTS $name=$inside"
done
IMG_MANIFESTS="$IMG_MANIFESTS web=-"

# (3a) Hardening (05 SAR-33; ruling R-37 (b)): no pip and no setuid or setgid file in any image.
for name in $IMAGES; do
  tag="erev-$name:${BUILD_SHA:0:12}"
  if [[ " $MANIFEST_IMAGES " == *" $name "* ]]; then
    found="$(probe_python "$tag" 2>>"$REPORT_DIR/$name.log")"; rc=$?; kind="json"
  else
    found="$(probe_files "$tag" 2>>"$REPORT_DIR/$name.log")"; rc=$?; kind="lines"
  fi
  if [[ $rc -ne 0 ]]; then
    IMG_HARDENED="$IMG_HARDENED $name=false"
    FAIL_STAGE="hardening"
    FAIL_IMAGE="$name"
    FAIL_EXIT="$rc"
    fail "the hardening probe of $tag failed (exit $rc)"
  fi
  verdict="$(printf '%s' "$found" | probe_verdict "$kind")"
  if [[ "$verdict" != "OK" ]]; then
    IMG_HARDENED="$IMG_HARDENED $name=false"
    FAIL_STAGE="hardening"
    FAIL_IMAGE="$name"
    FAIL_EXIT="1"
    fail "$tag is not hardened (05 SAR-33): ${verdict:-the probe printed no verdict}"
  fi
  IMG_HARDENED="$IMG_HARDENED $name=true"
done

write_report 0 "built"
echo "$TARGET: attestation $REPORT_DIR/report.json (embedded manifest copy $MANIFEST_COPY)"
echo "OK $TARGET"
