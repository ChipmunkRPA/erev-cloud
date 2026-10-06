#!/usr/bin/env python3
"""Dependency licence gate (docs/dev-guide.md DG-MK-licence-check; REQ-SEC-010; 05 SAR-32).

Inventories, both read offline:
  - runtime Python packages: `uv export --project backend --no-dev --frozen --all-extras` (the
    `gcp` extra holds the hosted providers, 05 SAR-21), with metadata read from backend/.venv;
  - production npm packages: `npm --prefix frontend ls --omit=dev --all --json --long`, with their
    `license` fields.

A licence resolves from the first source that parses: the SPDX `License-Expression` (npm:
`license`), the `License` field, then the licence classifiers (several are alternatives). It must
satisfy the REQ-SEC-010 allow-list; LGPL-3.0 passes only for psycopg, psycopg-binary and
psycopg-pool while NOTICE names psycopg. A package whose metadata yields no licence needs an entry
{ecosystem, name, licence, source, reason} in scripts/licence_allowlist.toml.

Output lines are `<ecosystem>:<name>@<version> LICENCE <licence or missing>: <reason>`. Exit 1 on
any finding, an invalid allow-list, an entry naming no dependency, or a failing inventory command.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "scripts" / "licence_allowlist.toml"

ECOSYSTEMS = ("python", "npm")
# REQ-SEC-010: MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0 and OFL for fonts. MIT-0 grants the MIT
# permissions without the notice condition (SPEC-Q-61).
ALLOWED = frozenset(
    {
        "MIT",
        "MIT-0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "ISC",
        "PSF-2.0",
        "MPL-2.0",
        "OFL-1.1",
    }
)
LGPL = "LGPL-3.0"
# psycopg-pool is the psycopg project's connection pool (procrastinate needs it), under the same
# licence and covered by the same NOTICE entry.
LGPL_PACKAGES = frozenset({"psycopg", "psycopg-binary", "psycopg-pool"})

# Free-text `License` values that name one SPDX licence.
ALIASES = {
    "mit license": "MIT",
    "the mit license": "MIT",
    "isc license": "ISC",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "mpl 2.0": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    # defusedxml publishes `License: PSFL`; its LICENSE file is the PSF Licence Agreement v2.
    "psfl": "PSF-2.0",
}
# Classifiers that name one licence; "BSD License" and "Apache Software License" name a family
# without a version and resolve nothing.
CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: MIT No Attribution License (MIT-0)": "MIT-0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": LGPL,
    "License :: OSI Approved :: SIL Open Font License 1.1 (OFL-1.1)": "OFL-1.1",
}
MAX_LICENCE_FIELD = 100
# Free-text `License` values that name a licence family without a version ("BSD", "Apache") resolve
# nothing, like the family classifiers above, so the allow-list entry with the verified licence
# governs (pyasn1-modules publishes `License: BSD`).
LICENCE_FAMILIES = frozenset({"bsd", "apache", "gpl", "lgpl", "mpl"})
REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;]+)")
_TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z0-9][A-Za-z0-9.+:-]*)")
_ALLOW_KEYS = frozenset({"ecosystem", "name", "licence", "source", "reason"})

# A parsed SPDX expression: ("id", licence) or ("and" | "or", children).
Node = tuple[str, str] | tuple[str, tuple["Node", ...]]


@dataclass(frozen=True, slots=True)
class Package:
    ecosystem: str
    name: str
    version: str
    expression: str | None = None
    licence_text: str | None = None
    classifiers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AllowEntry:
    ecosystem: str
    name: str
    licence: str
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class Finding:
    package: Package
    licence: str
    reason: str

    def render(self) -> str:
        package = self.package
        return (
            f"{package.ecosystem}:{package.name}@{package.version} "
            f"LICENCE {self.licence}: {self.reason}"
        )


class AllowListError(ValueError):
    """The allow-list file is missing, unparsable or holds an invalid entry."""


class InventoryError(RuntimeError):
    """An inventory command failed or printed output that cannot be read."""


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _normalise_id(token: str) -> str:
    for suffix in ("-only", "-or-later", "+"):
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.index = 0

    def peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> str | None:
        token = self.peek()
        self.index += 1
        return token

    def _operator(self, word: str) -> bool:
        token = self.peek()
        return token is not None and token.upper() == word

    def expression(self) -> Node:
        children = [self.term()]
        while self._operator("OR"):
            self.take()
            children.append(self.term())
        return children[0] if len(children) == 1 else ("or", tuple(children))

    def term(self) -> Node:
        children = [self.factor()]
        while self._operator("AND"):
            self.take()
            children.append(self.factor())
        return children[0] if len(children) == 1 else ("and", tuple(children))

    def factor(self) -> Node:
        token = self.take()
        if token is None or token == ")" or token.upper() in {"AND", "OR", "WITH"}:
            raise ValueError("licence expected")
        if token == "(":
            node = self.expression()
            if self.take() != ")":
                raise ValueError("closing parenthesis expected")
            return node
        if self._operator("WITH"):
            self.take()
            exception = self.take()
            if exception is None or exception in {"(", ")"}:
                raise ValueError("exception expected")
        return ("id", _normalise_id(token))


def parse_expression(text: str) -> Node | None:
    """The SPDX expression tree of ``text``, or None when it does not parse."""
    text = ALIASES.get(text.strip().lower(), text).strip()
    tokens: list[str] = []
    index = 0
    while index < len(text):
        match = _TOKEN.match(text, index)
        if match is None:
            return None
        tokens.append(match.group(1))
        index = match.end()
        while index < len(text) and text[index].isspace():
            index += 1
    if not tokens:
        return None
    parser = _Parser(tokens)
    try:
        node = parser.expression()
    except ValueError:
        return None
    return node if parser.peek() is None else None


def render(node: Node) -> str:
    kind, value = node
    if isinstance(value, str):
        return value
    joiner = " AND " if kind == "and" else " OR "
    parts = [render(child) if child[0] == "id" else f"({render(child)})" for child in value]
    return joiner.join(parts)


def licence_ids(node: Node) -> set[str]:
    kind, value = node
    if isinstance(value, str):
        return {value}
    return set().union(*(licence_ids(child) for child in value))


def is_allowed(node: Node, name: str, *, notice_names_psycopg: bool) -> bool:
    kind, value = node
    if isinstance(value, str):
        if value in ALLOWED:
            return True
        return value == LGPL and name in LGPL_PACKAGES and notice_names_psycopg
    results = [
        is_allowed(child, name, notice_names_psycopg=notice_names_psycopg) for child in value
    ]
    return any(results) if kind == "or" else all(results)


def resolve(package: Package) -> Node | None:
    """The licence the package metadata declares, or None when the metadata yields none."""
    if package.expression:
        node = parse_expression(package.expression)
        if node is not None:
            return node
    text = package.licence_text
    if text and len(text) <= MAX_LICENCE_FIELD and "\n" not in text:
        node = parse_expression(text)
        if node is not None and not _names_family_only(node):
            return node
    named = [CLASSIFIERS[c] for c in package.classifiers if c in CLASSIFIERS]
    if not named:
        return None
    if len(named) == 1:
        return ("id", named[0])
    return ("or", tuple(("id", licence) for licence in named))


def _names_family_only(node: Node) -> bool:
    kind, value = node
    if isinstance(value, str):
        return value.lower() in LICENCE_FAMILIES
    return all(_names_family_only(child) for child in value)


def load_allowlist(path: Path) -> list[AllowEntry]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AllowListError(f"{path.name}: file not found") from error
    except tomllib.TOMLDecodeError as error:
        raise AllowListError(f"{path.name}: {error}") from error
    unknown = set(document) - {"package"}
    if unknown:
        raise AllowListError(f"{path.name}: unknown top-level keys {sorted(unknown)}")
    raw_entries = document.get("package", [])
    if not isinstance(raw_entries, list):
        raise AllowListError(f"{path.name}: 'package' must be an array of tables")
    entries: list[AllowEntry] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict) or set(raw) != _ALLOW_KEYS:
            raise AllowListError(
                f"{path.name}: entry {index} must have exactly {sorted(_ALLOW_KEYS)}"
            )
        if not all(isinstance(value, str) and value.strip() for value in raw.values()):
            raise AllowListError(f"{path.name}: entry {index} values must be non-empty strings")
        if raw["ecosystem"] not in ECOSYSTEMS:
            raise AllowListError(f"{path.name}: entry {index} ecosystem must be python or npm")
        if not raw["source"].startswith("https://"):
            raise AllowListError(f"{path.name}: entry {index} source must be an https URL")
        if parse_expression(raw["licence"]) is None:
            raise AllowListError(f"{path.name}: entry {index} licence is not an SPDX expression")
        name = canonical_name(raw["name"]) if raw["ecosystem"] == "python" else raw["name"]
        key = (raw["ecosystem"], name)
        if key in seen:
            raise AllowListError(f"{path.name}: entry {index} duplicates {name}")
        seen.add(key)
        entries.append(
            AllowEntry(raw["ecosystem"], name, raw["licence"], raw["source"], raw["reason"])
        )
    return entries


def check(
    packages: Sequence[Package], allowlist: Sequence[AllowEntry], notice_text: str
) -> tuple[list[Finding], list[str], int]:
    """(findings, allow-list errors, count of packages resolved through the allow-list)."""
    notice_names_psycopg = "psycopg" in notice_text.lower()
    entries = {(entry.ecosystem, entry.name): entry for entry in allowlist}
    findings: list[Finding] = []
    allow_listed = 0
    for package in packages:
        node = resolve(package)
        if node is None:
            entry = entries.get((package.ecosystem, package.name))
            if entry is None:
                findings.append(
                    Finding(package, "missing", "no licence metadata and no allow-list entry")
                )
                continue
            node = parse_expression(entry.licence)
            assert node is not None  # load_allowlist validated it
            allow_listed += 1
        if is_allowed(node, package.name, notice_names_psycopg=notice_names_psycopg):
            continue
        if LGPL in licence_ids(node) and package.name in LGPL_PACKAGES:
            reason = "LGPL-3.0 needs the psycopg entry in NOTICE"
        else:
            reason = "not on the REQ-SEC-010 allow-list"
        findings.append(Finding(package, render(node), reason))
    present = {(package.ecosystem, package.name) for package in packages}
    errors = [
        f"entry for {entry.ecosystem}:{entry.name} names no dependency"
        for entry in allowlist
        if (entry.ecosystem, entry.name) not in present
    ]
    return findings, errors, allow_listed


def _run(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command), capture_output=True, text=True, check=False, timeout=300
        )
    except FileNotFoundError as error:
        raise InventoryError(f"{command[0]} not found") from error
    if completed.returncode != 0:
        detail = (completed.stderr.strip().splitlines() or ["no output"])[-1]
        raise InventoryError(f"{' '.join(command[:3])} exited {completed.returncode}: {detail}")
    return completed.stdout


def python_packages(root: Path) -> list[Package]:
    backend = root / "backend"
    exported = _run(
        [
            "uv",
            "--offline",
            "export",
            "--project",
            str(backend),
            "--no-dev",
            "--frozen",
            "--all-extras",
            "--no-hashes",
            "--no-emit-project",
        ]
    )
    site_packages = [str(path) for path in sorted(backend.glob(".venv/lib/python*/site-packages"))]
    if not site_packages:
        raise InventoryError("backend/.venv has no site-packages; run make setup first")
    installed = {
        canonical_name(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions(path=site_packages)
    }
    packages: list[Package] = []
    for line in exported.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[0].isspace():
            continue
        match = REQUIREMENT.match(stripped)
        if match is None:
            raise InventoryError(f"uv export line not understood: {stripped[:60]}")
        name, version = canonical_name(match.group(1)), match.group(2)
        dist = installed.get(name)
        if dist is None:
            packages.append(Package("python", name, version))
            continue
        metadata = dist.metadata
        packages.append(
            Package(
                "python",
                name,
                version,
                expression=metadata.get("License-Expression"),
                licence_text=metadata.get("License"),
                classifiers=tuple(metadata.get_all("Classifier") or ()),
            )
        )
    return packages


def _npm_licence(node: dict[str, object]) -> str | None:
    licence = node.get("license")
    if isinstance(licence, str):
        return licence
    if isinstance(licence, dict) and isinstance(licence.get("type"), str):
        return str(licence["type"])
    legacy = node.get("licenses")
    if isinstance(legacy, list):
        types = [str(item["type"]) for item in legacy if isinstance(item, dict) and "type" in item]
        return " OR ".join(types) if types else None
    return None


def npm_packages(root: Path) -> list[Package]:
    output = _run(
        [
            "npm",
            "--prefix",
            str(root / "frontend"),
            "ls",
            "--omit=dev",
            "--all",
            "--json",
            "--long",
            "--offline",
        ]
    )
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise InventoryError(f"npm ls printed invalid JSON: {error}") from error
    found: dict[tuple[str, str], Package] = {}

    def walk(node: dict[str, object]) -> None:
        dependencies = node.get("dependencies")
        if not isinstance(dependencies, dict):
            return
        for name, child in dependencies.items():
            if not isinstance(child, dict) or child.get("missing"):
                raise InventoryError(f"npm dependency {name} is not installed")
            version = str(child.get("version", ""))
            found.setdefault(
                (name, version), Package("npm", name, version, expression=_npm_licence(child))
            )
            walk(child)

    walk(document)
    return [found[key] for key in sorted(found)]


def load_packages(path: Path) -> list[Package]:
    """A JSON package list that replaces both inventories (used by tests)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Package(
            item["ecosystem"],
            item["name"],
            item["version"],
            expression=item.get("expression"),
            licence_text=item.get("licence_text"),
            classifiers=tuple(item.get("classifiers", ())),
        )
        for item in raw
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--notice", type=Path, help="NOTICE file (default: <root>/NOTICE)")
    parser.add_argument("--packages", type=Path, help="JSON package list replacing the inventories")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        allowlist = load_allowlist(args.allowlist)
    except AllowListError as error:
        print(f"licence-check allow-list: {error}")
        return 1
    try:
        if args.packages is not None:
            packages = load_packages(args.packages)
        else:
            packages = python_packages(root) + npm_packages(root)
    except InventoryError as error:
        print(f"licence-check inventory: {error}")
        return 1
    notice = args.notice if args.notice is not None else root / "NOTICE"
    notice_text = notice.read_text(encoding="utf-8") if notice.is_file() else ""

    findings, errors, allow_listed = check(packages, allowlist, notice_text)
    for finding in findings:
        print(finding.render())
    for message in errors:
        print(f"{args.allowlist.name}: {message}")
    counts = {ecosystem: 0 for ecosystem in ECOSYSTEMS}
    for package in packages:
        counts[package.ecosystem] = counts.get(package.ecosystem, 0) + 1
    print(
        f"licence-check: {len(packages)} packages "
        f"({counts['python']} python, {counts['npm']} npm), {allow_listed} allow-listed, "
        f"{len(findings)} findings, {len(errors)} allow-list errors"
    )
    return 1 if findings or errors else 0


if __name__ == "__main__":
    sys.exit(main())
