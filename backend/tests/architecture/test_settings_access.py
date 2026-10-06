"""DG-ARC-03: ``get_settings`` is used only by composition roots (DG-KRN-CFG-01; BUILD_SPEC FND-13).

Domain and kernel code receives settings through ``UnitOfWork`` or parameters. The scan covers
the application packages; tests configure settings through their own fixtures.
"""

from __future__ import annotations

import ast
from typing import Final

from support.architecture import Finding, imports, iter_files, read, report

RULE: Final = "DG-ARC-03"
PY: Final = frozenset({".py"})
COMPOSITION_ROOTS: Final = frozenset(
    {
        "backend/erev_api/main.py",
        "backend/erev_api/worker.py",
        "backend/erev_api/cli.py",
        "backend/erev_api/db/session.py",
        "backend/erev_api/logging.py",
        # The definition itself.
        "backend/erev_api/config.py",
    }
)
ADAPTER_FACTORIES: Final = "backend/erev_api/adapters/"


def check_settings_access(path: str, source: str) -> list[Finding]:
    if path in COMPOSITION_ROOTS or path.startswith(ADAPTER_FACTORIES):
        return []
    tree = ast.parse(source, filename=path)
    lines = {item.line for item in imports(path, tree) if "get_settings" in item.names}
    lines |= {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "get_settings"
    }
    return [
        Finding(path, line, RULE, "get_settings outside a composition root")
        for line in sorted(lines)
    ]


def test_dg_arc_03_get_settings_only_in_roots() -> None:
    imported = "from erev_api.config import get_settings\nsettings = get_settings()\n"
    findings = check_settings_access("backend/erev_api/domain/x.py", imported)
    assert [(finding.line, finding.rule) for finding in findings] == [(1, RULE)], report(findings)
    attribute = "from erev_api import config\nsettings = config.get_settings()\n"
    assert len(check_settings_access("backend/erev_api/db/x.py", attribute)) == 1
    for root in ("main.py", "cli.py", "db/session.py", "logging.py"):
        assert check_settings_access(f"backend/erev_api/{root}", imported) == [], root
    assert check_settings_access("backend/erev_api/adapters/email/factory.py", imported) == []

    repository = [
        finding
        for path in iter_files("backend/erev_api", "backend/erev_engine", suffixes=PY)
        for finding in check_settings_access(path, read(path))
    ]
    assert repository == [], report(repository)
