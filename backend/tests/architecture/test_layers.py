"""DG-ARC-01: imports inside ``erev_api`` follow the DG-LAY-03 layer order (BUILD_SPEC FND-13).

Layers, highest first: the composition roots ``main``, ``worker`` and ``cli``; ``api``; ``domain``;
the kernel modules; ``erev_engine``. A module imports only from its own layer or a lower one.
``adapters`` implement kernel or domain protocols and are imported only by the roots and by the
adapter factories of ``ADAPTER_FACTORIES``. ``erev_engine`` imports nothing of ``erev_api``.
"""

from __future__ import annotations

import ast
from typing import Final

import pytest
from support.architecture import Finding, imports, iter_files, module_name, read, report

RULE: Final = "DG-ARC-01"
PY: Final = frozenset({".py"})
ROOTS: Final = frozenset({"main", "worker", "cli"})
KERNEL: Final = frozenset(
    {
        "uow",
        "db",
        "auth",
        "audit",
        "approvals",
        "idempotency",
        "problems",
        "money",
        "clock",
        "periods",
        "numbering",
        "events",
        "jobs",
        "files",
        "registry",
        "explain",
        "projections",
        "schemas",
        "logging",
        "controls",
        # Configuration and the platform StrEnums are kernel modules DG-LAY-03 does not list.
        "config",
        "enums",
        # The contact-member catalogue 04 §16.14 names erev_api.redaction (BUILD_SPEC DIN-2).
        "redaction",
        # 05 PRV-01 names erev_api.privacy.CLASSIFICATION (BUILD_SPEC SOP-5).
        "privacy",
    }
)
LAYER_HEADS: Final = ROOTS | KERNEL | {"api", "domain", "adapters"}
ALLOWED: Final[dict[str, frozenset[str]]] = {
    "root": frozenset({"root", "api", "domain", "kernel", "adapters", "engine"}),
    "api": frozenset({"api", "domain", "kernel", "engine"}),
    "domain": frozenset({"domain", "kernel", "engine"}),
    "kernel": frozenset({"kernel", "engine"}),
    "adapters": frozenset({"adapters", "domain", "kernel", "engine"}),
    "engine": frozenset({"engine"}),
}
# Kernel modules that construct adapters, with the binding signature that places the factory there.
ADAPTER_FACTORIES: Final = {
    "backend/erev_api/auth/keyring.py": "build_keyring selects the key provider (dev-guide §5.19)",
    "backend/erev_api/files/store.py": "build_file_store selects the file backend (05 CFG-05)",
}


# DG-KRN-DB-02 as amended by D-78: the only application modules that may import identity_session.
IDENTITY_SESSION_RULE: Final = "DG-KRN-DB-02"
IDENTITY_SESSION_IMPORTERS: Final = (
    "backend/erev_api/auth/",
    "backend/erev_api/api/v1/health.py",
    "backend/erev_api/db/lint.py",
)


def layer_of(module: str) -> str | None:
    """The layer of an ``erev_api`` or ``erev_engine`` module; None for any other package and
    ``"unclassified"`` for an ``erev_api`` module that belongs to no layer."""
    parts = module.split(".")
    if parts[0] == "erev_engine":
        return "engine"
    if parts[0] != "erev_api":
        return None
    if len(parts) == 1:
        return "kernel"
    head = parts[1]
    if head in ROOTS:
        return "root"
    if head in ("api", "domain", "adapters"):
        return head
    return "kernel" if head in KERNEL else "unclassified"


def check_layers(path: str, source: str) -> list[Finding]:
    importer = layer_of(module_name(path))
    if importer is None:
        return []
    if importer == "unclassified":
        return [Finding(path, 1, RULE, f"{module_name(path)} belongs to no DG-LAY-03 layer")]
    findings: list[Finding] = []
    for item in imports(path, ast.parse(source, filename=path)):
        if item.module == "erev_api" and item.names:
            # A layer name is a subpackage; any other name (``__version__``) is a package attribute.
            targets = [
                f"erev_api.{name}" if name in LAYER_HEADS else "erev_api" for name in item.names
            ]
        else:
            targets = [item.module]
        for target in targets:
            layer = layer_of(target)
            if layer is None or layer in ALLOWED[importer]:
                continue
            if layer == "adapters" and path in ADAPTER_FACTORIES:
                continue
            findings.append(
                Finding(path, item.line, RULE, f"{importer} module imports {layer} module {target}")
            )
    return findings


def check_identity_session_importers(path: str, source: str) -> list[Finding]:
    if not path.startswith("backend/erev_api/"):
        return []
    if any(path == allowed or path.startswith(allowed) for allowed in IDENTITY_SESSION_IMPORTERS):
        return []
    return [
        Finding(
            path,
            item.line,
            IDENTITY_SESSION_RULE,
            "identity_session is imported outside auth/**, api/v1/health.py and db/lint.py",
        )
        for item in imports(path, ast.parse(source, filename=path))
        if item.module == "erev_api.db.session" and "identity_session" in item.names
    ]


# 05 REL-03: release_session serves only the startup release stamping (BUILD_SPEC PLF-20).
RELEASE_SESSION_RULE: Final = "REL-03"
RELEASE_SESSION_IMPORTERS: Final = ("backend/erev_api/controls/release.py",)


def check_release_session_importers(path: str, source: str) -> list[Finding]:
    if not path.startswith("backend/erev_api/") or path in RELEASE_SESSION_IMPORTERS:
        return []
    return [
        Finding(
            path,
            item.line,
            RELEASE_SESSION_RULE,
            "release_session is imported outside controls/release.py",
        )
        for item in imports(path, ast.parse(source, filename=path))
        if item.module == "erev_api.db.session" and "release_session" in item.names
    ]


def test_rel_03_release_session_importers() -> None:
    snippet = "from erev_api.db.session import release_session\n"
    findings = check_release_session_importers("backend/erev_api/domain/x.py", snippet)
    assert [(finding.line, finding.rule) for finding in findings] == [(1, RELEASE_SESSION_RULE)], (
        report(findings)
    )
    assert check_release_session_importers("backend/erev_api/controls/release.py", snippet) == []

    repository = [
        finding
        for path in iter_files("backend/erev_api", suffixes=PY)
        for finding in check_release_session_importers(path, read(path))
    ]
    assert repository == [], report(repository)


def test_dg_krn_db_02_identity_session_importers() -> None:
    snippet = "from erev_api.db.session import identity_session\n"
    findings = check_identity_session_importers("backend/erev_api/domain/x.py", snippet)
    assert [(finding.line, finding.rule) for finding in findings] == [(1, IDENTITY_SESSION_RULE)], (
        report(findings)
    )
    for path in (
        "backend/erev_api/auth/x.py",
        "backend/erev_api/api/v1/health.py",
        "backend/erev_api/db/lint.py",
    ):
        assert check_identity_session_importers(path, snippet) == [], path

    repository = [
        finding
        for path in iter_files("backend/erev_api", suffixes=PY)
        for finding in check_identity_session_importers(path, read(path))
    ]
    assert repository == [], report(repository)


def test_dg_arc_01_detects_upward_import() -> None:
    snippet = "from erev_api.api.router import api_router\n"
    findings = check_layers("backend/erev_api/domain/x.py", snippet)
    assert [(finding.line, finding.rule) for finding in findings] == [(1, RULE)], report(findings)

    repository = [
        finding
        for path in iter_files("backend/erev_api", "backend/erev_engine", suffixes=PY)
        for finding in check_layers(path, read(path))
    ]
    assert repository == [], report(repository)


@pytest.mark.parametrize(
    ("path", "source", "expected"),
    [
        ("backend/erev_api/db/x.py", "from erev_api.domain.contracts import commands\n", 1),
        ("backend/erev_api/domain/x.py", "from erev_api.adapters.secrets.store import X\n", 1),
        ("backend/erev_api/api/v1/x.py", "import erev_api.main\n", 1),
        ("backend/erev_api/uow.py", "from erev_api import api\n", 1),
        ("backend/erev_engine/x.py", "from erev_api.money import MoneyStr\n", 1),
        ("backend/erev_api/adapters/gl/x.py", "from erev_api.api.deps import command\n", 1),
        ("backend/erev_api/gadgets.py", "import json\n", 1),
        ("backend/erev_api/api/v1/x.py", "from ..deps import API_PREFIX\n", 0),
        ("backend/erev_api/api/v1/x.py", "from erev_api.domain.contracts import queries\n", 0),
        ("backend/erev_api/domain/x.py", "from erev_api import clock, uow\n", 0),
        ("backend/erev_api/cli.py", "from erev_api.adapters.keys.provider import Y\n", 0),
        ("backend/erev_api/auth/keyring.py", "from erev_api.adapters.keys.provider import Y\n", 0),
        ("backend/erev_api/adapters/gl/x.py", "from erev_api.domain.journals import queries\n", 0),
        ("backend/erev_api/db/x.py", "from erev_engine.canonical import sha256_hex\n", 0),
    ],
)
def test_layer_order(path: str, source: str, expected: int) -> None:
    findings = check_layers(path, source)
    assert len(findings) == expected, report(findings)
