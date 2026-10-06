"""05 TXN-03 rev 1.121 and CFG-29 (dev-guide DG-KRN-DB-01 and DG-AK-60 rev 1.165; supervisor
rulings R-116 (h) and R-119 (d)): a transaction that is idle by design — a dataset freeze's caller
while the freeze's reader works, a held reader while its caller writes — sets its own
``idle_in_transaction_session_timeout``; every connection keeps the 60 s of its connect options.
Every caller of ``snapshots.freeze_datasets`` sets it through ``freeze.allow_idle``.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import erev_api
from erev_api.config import settings_override
from erev_api.db import session as db_session
from erev_api.domain.close import freeze
from sqlalchemy.dialects import postgresql

ROOT = Path(erev_api.__file__).parent
# the functions of erev_api that freeze a period's datasets, by module
FREEZE_CALLERS = {
    "domain/close/close_runs.py": "_dataset_freeze",
    "domain/close/commands.py": "_period_lock_approved",
    "domain/platform/sandbox_periods.py": "_lock",
}


class _Session:
    """Records the statements a helper executes, compiled for PostgreSQL, with their values."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, parameters: Any = None) -> None:
        compiled = str(statement.compile(dialect=postgresql.dialect()))
        self.calls.append((compiled, dict(parameters or {})))


def test_txn_03_the_idle_bound_is_set_for_the_transaction_alone_from_the_setting() -> None:
    """One statement: ``set_config(..., true)`` — the transaction's own value, gone at its end, so
    the pooled connection goes back with the 60 s of its options — carrying the setting in
    milliseconds as a bound value, never as SQL text."""
    session = _Session()
    with settings_override(dataset_freeze_idle_seconds=120):
        db_session.allow_idle_in_transaction(session)  # type: ignore[arg-type]
    ((statement, values),) = session.calls
    assert statement == (
        "SELECT set_config('idle_in_transaction_session_timeout', %(idle_timeout)s, true)"
    )
    assert values == {"idle_timeout": "120000"}
    # the freeze's function is that statement, for the session it is handed
    frozen = _Session()
    with settings_override(dataset_freeze_idle_seconds=120):
        freeze.allow_idle(frozen)  # type: ignore[arg-type]
    assert frozen.calls == session.calls


def test_txn_03_the_connections_own_bound_stays_sixty_seconds() -> None:
    """The helper widens one transaction; the bound every connection starts with is unchanged."""
    options = db_session.connect_options("api").split(" -c ")
    assert "idle_in_transaction_session_timeout=60000" in options
    assert [option for option in options if option.startswith("idle_in_transaction")] == [
        "idle_in_transaction_session_timeout=60000"
    ]


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _calls(function: ast.AST) -> list[tuple[tuple[int, int], str]]:
    """The dotted names ``function`` calls, with their source positions."""
    found = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name is not None:
                found.append(((node.lineno, node.col_offset), name))
    return sorted(found)


def test_txn_03_every_caller_of_the_dataset_freeze_sets_the_idle_bound_first() -> None:
    """Supervisor ruling R-119 (d) (05 TXN-03 rev 1.121; dev-guide DG-AK-60 rev 1.165): one function
    sets the bound for every caller of ``snapshots.freeze_datasets``. Read from the source of the
    package: each function that calls ``freeze_datasets`` calls ``freeze.allow_idle`` before it,
    and the callers are the three the documents name — a fourth joins this list with its call.
    Fail-first: the close run's DATASET_FREEZE step and the sandbox period replay froze under the
    connection's 60 s; a dataset that took longer to produce ended their transaction."""
    callers: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("db/migrations/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = _calls(node)
            frozen = [at for at, name in calls if name.split(".")[-1] == "freeze_datasets"]
            if not frozen:
                continue
            callers[relative] = node.name
            bound = [at for at, name in calls if name == "freeze.allow_idle"]
            assert bound and min(bound) < min(frozen), (relative, node.name)
    assert callers == FREEZE_CALLERS
