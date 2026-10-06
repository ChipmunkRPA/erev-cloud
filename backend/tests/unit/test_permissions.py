"""Permission catalogue and default roles (dev-guide §5.4; 04 T-PLT-09, T-PLT-11; PRD §5.6; FND-7).

docs/02-PRD.md and docs/04-DATA_MODEL.md are read read-only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from erev_api.auth.permissions import CATALOGUE, DEFAULT_ROLES, spec

ROOT = Path(__file__).resolve().parents[3]
PRD = ROOT / "docs" / "02-PRD.md"
DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"

# docs/02-PRD.md §5.6 column abbreviations; DD is a custom seeded role, not a default role.
PRD_COLUMNS = {
    "RA": "revenue_accountant",
    "RR": "revenue_reviewer",
    "CO": "controller",
    "SA": "ssp_analyst",
    "SP": "ssp_approver",
    "IA": "integration_admin",
    "TA": "tenant_admin",
    "AU": "auditor",
    "VW": "viewer",
    "SV": "service_account",
}
_CODE = re.compile(r"`([a-z_]+(?:\.[a-z_]+)+)`")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def prd_default_role_grants() -> dict[str, frozenset[str]]:
    section = _between(PRD.read_text(encoding="utf-8"), "### 5.6 Permissions per action", "| Id |")
    lines = section.splitlines()
    header_index = next(i for i, line in enumerate(lines) if line.startswith("| Permission |"))
    columns = _cells(lines[header_index])[1:]
    grants: dict[str, set[str]] = {column: set() for column in columns}
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = _cells(line)
        codes = set(_CODE.findall(cells[0]))
        assert codes, line
        for column, cell in zip(columns, cells[1:], strict=True):
            if cell == "●":
                grants[column] |= codes
            elif cell:
                named = set(_CODE.findall(cell))
                assert named and named <= codes, line
                grants[column] |= named
    return {PRD_COLUMNS[column]: frozenset(grants[column]) for column in PRD_COLUMNS}


def t_plt_09_default_codes() -> list[str]:
    section = _between(
        DATA_MODEL.read_text(encoding="utf-8"), "### T-PLT-09 `role`", "### T-PLT-10"
    )
    row = next(line for line in section.splitlines() if line.startswith("| `code` |"))
    return re.findall(r"`([a-z_]+)`", row.split("Default codes:", 1)[1])


def test_default_roles_follow_prd_5_6() -> None:
    assert list(DEFAULT_ROLES) == t_plt_09_default_codes()
    assert {role: len(grants) for role, grants in DEFAULT_ROLES.items()} == {
        "revenue_accountant": 24,
        "revenue_reviewer": 19,
        "controller": 26,
        "ssp_analyst": 5,
        "ssp_approver": 5,
        "integration_admin": 10,
        "tenant_admin": 10,
        "auditor": 7,
        "viewer": 6,
        "service_account": 5,
    }
    assert dict(DEFAULT_ROLES) == prd_default_role_grants()
    codes = {permission.code for permission in CATALOGUE}
    for grants in DEFAULT_ROLES.values():
        assert grants <= codes


def test_default_roles_t_plt_11_constraints() -> None:
    by_code = {permission.code: permission for permission in CATALOGUE}
    reads = {code for code in by_code if code.endswith(".read")}
    access_admin = {code for code, permission in by_code.items() if permission.is_access_admin}
    assert DEFAULT_ROLES["tenant_admin"] <= access_admin | reads | {"audit.read", "settings.manage"}
    assert DEFAULT_ROLES["auditor"] <= reads | {
        "report.run",
        "report.export",
        "evidence.export",
        "audit.read",
    }
    assert not [code for code in DEFAULT_ROLES["service_account"] if by_code[code].is_approval]


def test_spec_unknown_code_raises() -> None:
    with pytest.raises(KeyError):
        spec("contract.explode")
    assert spec("period.lock").requires_mfa is True
    assert spec("contract.read").requires_mfa is False


def test_catalogue_and_roles_are_immutable() -> None:
    assert len({permission.code for permission in CATALOGUE}) == len(CATALOGUE) == 52
    with pytest.raises(TypeError):
        DEFAULT_ROLES["probe"] = frozenset()  # type: ignore[index]
