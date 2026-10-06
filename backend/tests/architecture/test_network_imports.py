"""DG-ARC-12: network libraries only in adapters and test support (REQ-SEC-008; DG-TST-15;
BUILD_SPEC FND-13).

The scan covers ``backend/``: the application packages and the tests.
"""

from __future__ import annotations

import ast
from typing import Final

import pytest
from support.architecture import Finding, Import, imports, iter_files, read, report

RULE: Final = "DG-ARC-12"
PY: Final = frozenset({".py"})
NETWORK_MODULES: Final = ("httpx", "anthropic", "smtplib", "socket", "urllib.request")
SCOPE: Final = ("backend/erev_api", "backend/erev_engine", "backend/tests")
ALLOWED_PREFIXES: Final = ("backend/erev_api/adapters/", "backend/tests/support/")
ALLOWLIST: Final = {
    "backend/tests/unit/test_socket_guard.py": "proves the DG-TST-15 socket guard",
}


def _network_module(item: Import) -> str | None:
    for candidate in (item.module, *(f"{item.module}.{name}" for name in item.names)):
        for module in NETWORK_MODULES:
            if candidate == module or candidate.startswith(module + "."):
                return module
    return None


def check_network_imports(path: str, source: str) -> list[Finding]:
    if path.startswith(ALLOWED_PREFIXES) or path in ALLOWLIST:
        return []
    return [
        Finding(path, item.line, RULE, f"imports {module} outside adapters")
        for item in imports(path, ast.parse(source, filename=path))
        if (module := _network_module(item)) is not None
    ]


def test_dg_arc_12_network_import_outside_adapters() -> None:
    findings = check_network_imports("backend/erev_api/domain/x.py", "import httpx\n")
    assert [(finding.line, finding.rule) for finding in findings] == [(1, RULE)], report(findings)
    assert check_network_imports("backend/erev_api/adapters/gl/netsuite.py", "import httpx\n") == []

    repository = [
        finding
        for path in iter_files(*SCOPE, suffixes=PY)
        for finding in check_network_imports(path, read(path))
    ]
    assert repository == [], report(repository)


@pytest.mark.parametrize(
    ("path", "source", "expected"),
    [
        ("backend/erev_api/api/v1/x.py", "from anthropic import Anthropic\n", 1),
        ("backend/erev_api/domain/x.py", "import smtplib\n", 1),
        ("backend/erev_api/domain/x.py", "import socket\n", 1),
        ("backend/erev_api/domain/x.py", "import urllib.request\n", 1),
        ("backend/erev_api/domain/x.py", "from urllib import request\n", 1),
        ("backend/erev_api/domain/x.py", "from urllib.request import urlopen\n", 1),
        ("backend/erev_engine/x.py", "import httpx._transports\n", 1),
        ("backend/tests/api/x.py", "import httpx\n", 1),
        ("backend/erev_api/config.py", "from urllib.parse import urlsplit\n", 0),
        ("backend/erev_api/domain/x.py", "import socketserver\n", 0),
        ("backend/tests/support/http.py", "import httpx\n", 0),
        ("backend/erev_api/adapters/email/smtp.py", "import smtplib\n", 0),
    ],
)
def test_network_import_rules(path: str, source: str, expected: int) -> None:
    findings = check_network_imports(path, source)
    assert len(findings) == expected, report(findings)
