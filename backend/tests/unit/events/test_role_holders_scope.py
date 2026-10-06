"""Every notification addressed by role states the scope of its event (item
NOTIFY-ROLE-HOLDERS-SCOPE-1; the supervisor's ruling of 2026-10-01; PRD §5.4 NTF-06, NTF-07,
NTF-09 to NTF-12; 05 NTR-02 rev 1.180).

CPU only. ``events.notifications.role_holders`` takes the event's scope — an entity, or None for
an event of the whole workspace — as a keyword every caller must give. The nine calls are read
from the source, as ``tests/unit/test_sandbox_periods.py`` reads the replayed lock: no world
reaches a lock or a reopen inside a sandbox today (05 SNP-2b; the first lock of a replay is
refused by its gates), so for the two calls of ``domain.platform.sandbox_periods`` this module is
the only witness; the other seven have database witnesses in
``tests/domain/platform/test_notification_scope_db.py``,
``tests/domain/journals/test_export_failure_recipients.py`` and, for the ninth (item
CLO-RATE-AFTER-RUN-1, register index 272: the finding of a rate changed after a lock tells the
role holders of the finding's entity), ``tests/domain/close/test_rate_changed_after_lock.py``.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.events import notifications
from sqlalchemy.dialects import postgresql

PACKAGE = Path(notifications.__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
ENTITY = UUID(int=0xE1)
# module → the scope each of its calls passes, in source order
SCOPES = {
    "audit/verify.py": ["None"],  # NTF-09: the chain is the workspace's
    "domain/close/commands.py": ["scope.entity_id", "scope.entity_id"],  # NTF-07, NTF-06
    "domain/close/monitors.py": ["finding.entity_id"],  # NTF-11
    "domain/close/rate_changes.py": ["entity_id"],  # NTF-11: the entity of the closed period
    "domain/journals/export.py": ["UUID(str(batch['entity_id']))"],  # NTF-10
    "domain/platform/sandbox_periods.py": ["scope.entity_id", "scope.entity_id"],  # the replay
    "domain/platform/support_grants.py": ["None"],  # NTF-12: an operator's access is every entity's
}


class _Session:
    """Records the statement ``role_holders`` reads and answers no row."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def scalars(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return iter(())


def _scope_of(path: Path) -> list[str]:
    """The ``entity_id`` argument of every ``role_holders(...)`` call in a module, in order."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name != "role_holders":
            continue
        scopes = [
            ast.unparse(keyword.value) for keyword in node.keywords if keyword.arg == "entity_id"
        ]
        found.append((node.lineno, scopes[0] if scopes else "<no entity_id>"))
    return [scope for _, scope in sorted(found)]


def test_every_call_states_the_scope_of_its_event() -> None:
    calls = {
        str(path.relative_to(PACKAGE)): _scope_of(path)
        for path in sorted(PACKAGE.rglob("*.py"))
        if path.name != "notifications.py"
    }
    assert {name: scopes for name, scopes in calls.items() if scopes} == SCOPES


def test_the_scope_is_a_keyword_no_call_can_leave_out() -> None:
    session = _Session()
    with pytest.raises(TypeError):
        notifications.role_holders(session, role_codes=["controller"], at=NOW)  # type: ignore[call-arg,arg-type]
    assert session.statements == []


def test_an_entitys_event_is_covered_by_all_entities_or_by_its_name() -> None:
    session = _Session()
    notifications.role_holders(
        session,  # type: ignore[arg-type]
        role_codes=["controller", "auditor"],
        entity_id=ENTITY,
        at=NOW,
    )
    (statement,) = session.statements
    assert "role_assignment.is_all_entities IS true OR" in statement
    assert "= ANY (erev.role_assignment.entity_ids)" in statement


def test_the_workspaces_event_is_covered_by_all_entities_alone() -> None:
    session = _Session()
    notifications.role_holders(
        session,  # type: ignore[arg-type]
        role_codes=["tenant_admin"],
        entity_id=None,
        at=NOW,
    )
    (statement,) = session.statements
    assert "role_assignment.is_all_entities IS true" in statement
    assert "entity_ids" not in statement
