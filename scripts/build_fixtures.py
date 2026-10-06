#!/usr/bin/env python3
"""Legacy fixture builder (docs/dev-guide.md DG-PAR-02, DG-MK-fixtures, DG-LAY-09, DG-LAY-11;
BUILD_SPEC FND-17).

The plan comes from the golden documents only:
  1. UAT workbooks: `docs/legacy/golden/NN-<slug>/step.json` (`file`, `file_sha256`) for steps 01
     to 14, read from `legacy-harness/erev_copy/<file>`, else from the legacy repository
     (`~/dev/erev-legacy/<file>`), and copied to `legacy_uat/NN-<slug>/<basename>`;
  2. probe inputs: the files named by `docs/legacy/golden/probes/*/probe.json` `sequence` that are
     not UAT workbooks, read from `legacy-harness/out/probes/inputs/` and copied to
     `legacy_probes/`. The documents record no hash for them, so the committed bytes are the
     reference once built;
  3. the shipped database, read from `legacy-harness/fixtures/ASC606.shipped.db`, verified against
     `docs/legacy/golden/manifest.json` `shipped_db_sha256` and copied to
     `legacy_db/ASC606-shipped-step04.db`. SQLite is a file format here: bytes are copied, never
     opened (D-40a).

`backend/tests/fixtures/manifest.json` lists `{path, sha256, bytes, source}` per file, sorted by
path; `path` is relative to the fixtures directory and `source` is the stable provenance (the
legacy repository path `legacy:<file>` for UAT workbooks, the harness path otherwise).

The builder copies bytes only, never imports legacy code and writes only below the fixtures
directory. It refuses to overwrite a fixture with different bytes and, when a source is missing
and the fixture is absent, exits 1 with `BLOCKED: legacy fixture <path> unavailable`. Findings are
collected first, so a failing run writes nothing. `--check` verifies the manifest against the plan
and every file's SHA-256 and size, and writes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = ROOT / "docs" / "legacy" / "golden"
DEFAULT_HARNESS = ROOT / "legacy-harness"
DEFAULT_LEGACY = Path.home() / "dev" / "erev-legacy"
DEFAULT_FIXTURES = ROOT / "backend" / "tests" / "fixtures"

MANIFEST = "manifest.json"
FIXTURE_DIRS = ("legacy_uat", "legacy_probes", "legacy_db")
DB_FIXTURE = "legacy_db/ASC606-shipped-step04.db"
DB_SOURCE = "fixtures/ASC606.shipped.db"
PROBE_INPUTS = "out/probes/inputs"
STEP_DIR = re.compile(r"^(?:0[1-9]|1[0-4])-[a-z0-9-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ENTRY_KEYS = frozenset({"path", "sha256", "bytes", "source"})
MAX_BYTES = 5 * 1024 * 1024  # DG-GIT-04


class PlanError(Exception):
    """The golden documents do not describe a usable fixture plan."""


@dataclass(frozen=True, slots=True)
class Planned:
    path: str  # relative to the fixtures directory
    candidates: tuple[Path, ...]  # source files, in order of preference
    source: str  # provenance recorded in the manifest
    expected_sha256: str | None  # from the golden documents; None for probe inputs
    authority: str  # the document that fixes the expected hash


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read {_display(path)}: {exc}") from exc


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan(golden: Path, harness: Path, legacy: Path) -> list[Planned]:
    """The 18 fixtures of DG-PAR-02, derived from the golden documents."""
    planned: list[Planned] = []
    uat_basenames: set[str] = set()
    step_dirs = sorted(p for p in golden.iterdir() if p.is_dir() and STEP_DIR.match(p.name))
    for step_dir in step_dirs:
        step = _load_json(step_dir / "step.json")
        if not isinstance(step, dict):
            raise PlanError(f"{_display(step_dir / 'step.json')} is not an object")
        file, digest = step.get("file"), step.get("file_sha256")
        if not isinstance(file, str) or not isinstance(digest, str) or not SHA256.match(digest):
            raise PlanError(f"{_display(step_dir / 'step.json')} lacks file and file_sha256")
        basename = Path(file).name
        uat_basenames.add(basename)
        planned.append(
            Planned(
                path=f"legacy_uat/{step_dir.name}/{basename}",
                candidates=(harness / "erev_copy" / file, legacy / file),
                source=f"legacy:{file}",
                expected_sha256=digest,
                authority=_display(step_dir / "step.json"),
            )
        )

    probe_basenames: list[str] = []
    for probe_file in sorted((golden / "probes").glob("*/probe.json")):
        probe = _load_json(probe_file)
        sequence = probe.get("sequence") if isinstance(probe, dict) else None
        if not isinstance(sequence, list):
            raise PlanError(f"{_display(probe_file)} lacks sequence")
        for item in sequence:
            file = item.get("file") if isinstance(item, dict) else None
            if isinstance(file, str) and file not in uat_basenames | set(probe_basenames):
                probe_basenames.append(file)
    for basename in probe_basenames:
        planned.append(
            Planned(
                path=f"legacy_probes/{basename}",
                candidates=(harness / PROBE_INPUTS / basename,),
                source=f"legacy-harness/{PROBE_INPUTS}/{basename}",
                expected_sha256=None,
                authority="committed fixture",
            )
        )

    manifest = _load_json(golden / MANIFEST)
    shipped = manifest.get("shipped_db_sha256") if isinstance(manifest, dict) else None
    if not isinstance(shipped, str) or not SHA256.match(shipped):
        raise PlanError(f"{_display(golden / MANIFEST)} lacks shipped_db_sha256")
    planned.append(
        Planned(
            path=DB_FIXTURE,
            candidates=(harness / DB_SOURCE,),
            source=f"legacy-harness/{DB_SOURCE}",
            expected_sha256=shipped,
            authority=_display(golden / MANIFEST),
        )
    )
    return sorted(planned, key=lambda p: p.path)


def _read_manifest(fixtures: Path) -> dict[str, dict[str, object]] | None:
    path = fixtures / MANIFEST
    if not path.is_file():
        return None
    data = _load_json(path)
    if not isinstance(data, list) or not all(
        isinstance(e, dict) and set(e) == ENTRY_KEYS and isinstance(e["path"], str) for e in data
    ):
        raise PlanError(f"{_display(path)} is not a list of {{path, sha256, bytes, source}}")
    return {str(e["path"]): e for e in data}


def _manifest_text(entries: list[dict[str, object]]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False) + "\n"


def build(planned: Sequence[Planned], fixtures: Path) -> int:
    committed = _read_manifest(fixtures) or {}
    findings: list[str] = []
    writes: list[tuple[Path, bytes]] = []
    entries: list[dict[str, object]] = []
    for item in planned:
        target = fixtures / item.path
        source = next((c for c in item.candidates if c.is_file()), None)
        if source is None:
            if not target.is_file():
                findings.append(f"BLOCKED: legacy fixture {_display(target)} unavailable")
                continue
            # No source on this machine: keep the committed fixture while its hash still holds.
            data = target.read_bytes()
            recorded = committed.get(item.path, {}).get("sha256")
            expected = item.expected_sha256 or recorded
            if expected is None or _sha256(data) != expected:
                findings.append(
                    f"FAIL fixture {_display(target)}: source unavailable and sha256 unverified"
                )
                continue
        else:
            with source.open("rb") as handle:
                data = handle.read()
            digest = _sha256(data)
            if item.expected_sha256 is not None and digest != item.expected_sha256:
                findings.append(
                    f"FAIL source {_display(source)}: sha256 {digest} differs from "
                    f"{item.expected_sha256} ({item.authority})"
                )
                continue
            if target.is_file():
                if target.read_bytes() != data:
                    findings.append(
                        f"FAIL fixture {_display(target)}: refusing to overwrite a committed "
                        "fixture with different bytes"
                    )
                    continue
            else:
                writes.append((target, data))
        if len(data) > MAX_BYTES:
            findings.append(f"FAIL fixture {_display(target)}: {len(data)} bytes exceeds 5 MiB")
            continue
        entries.append(
            {"path": item.path, "sha256": _sha256(data), "bytes": len(data), "source": item.source}
        )

    if findings:
        for finding in findings:
            print(finding)
        return 1
    for target, data in writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = fixtures / MANIFEST
    text = _manifest_text(entries)
    if not manifest.is_file() or manifest.read_text(encoding="utf-8") != text:
        manifest.write_text(text, encoding="utf-8")
    print(f"fixtures: {len(entries)} files, {len(writes)} written")
    return 0


def check(planned: Sequence[Planned], fixtures: Path) -> int:
    committed = _read_manifest(fixtures)
    if committed is None:
        print(f"FAIL {_display(fixtures / MANIFEST)} missing; run make fixtures")
        return 1
    findings: list[str] = []
    expected_paths = {item.path: item for item in planned}
    for path in sorted(set(expected_paths) - set(committed)):
        findings.append(f"FAIL fixture {_display(fixtures / path)}: absent from the manifest")
    for path in sorted(set(committed) - set(expected_paths)):
        findings.append(f"FAIL fixture {_display(fixtures / path)}: not in the golden plan")
    for path, entry in sorted(committed.items()):
        target = fixtures / path
        item = expected_paths.get(path)
        if item is not None and item.expected_sha256 not in (None, entry["sha256"]):
            findings.append(
                f"FAIL fixture {_display(target)}: manifest sha256 differs from {item.authority}"
            )
        if not target.is_file():
            findings.append(f"FAIL fixture {_display(target)}: missing")
            continue
        data = target.read_bytes()
        if _sha256(data) != entry["sha256"] or len(data) != entry["bytes"]:
            findings.append(
                f"FAIL fixture {_display(target)}: sha256 or size differs from manifest"
            )
    listed = {(fixtures / path).resolve() for path in committed}
    for directory in FIXTURE_DIRS:
        for file in sorted((fixtures / directory).rglob("*")):
            if file.is_file() and file.resolve() not in listed:
                findings.append(f"FAIL fixture {_display(file)}: not listed in the manifest")
    for finding in findings:
        print(finding)
    if findings:
        return 1
    print(f"fixtures: {len(committed)} files verified")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    sys.dont_write_bytecode = True  # never leave __pycache__ beside the inputs (DG-PAR-02)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify hashes only; write nothing")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--harness", type=Path, default=DEFAULT_HARNESS)
    parser.add_argument("--legacy", type=Path, default=DEFAULT_LEGACY)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    args = parser.parse_args(argv)
    try:
        planned = plan(args.golden, args.harness, args.legacy)
        return check(planned, args.fixtures) if args.check else build(planned, args.fixtures)
    except PlanError as exc:
        print(f"FAIL {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
