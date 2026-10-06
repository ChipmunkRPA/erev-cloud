"""dev-guide DG-KRN-APR-09 (04 T-PLT-21; PRD BR-PLT-07 rev 1.118; supervisor ruling R-111 (4)): a
delegation ends — it does not lie dormant — when its delegator loses the permission or the
membership, and when its delegate is removed (item SBX-COPY-OPEN-INVITATION-1: a removed person
is invited again on the same membership).

The end is stamped by ``erev_api.approvals.delegations.end_unsupported`` (or its session-level
core), which every command that changes what a member holds calls: after a change that takes
access away, before one that gives access. A command that forgets it leaves a delegation that the
engine no longer honours and that returns with the delegator's next grant. This test finds those
commands by what they write — a role assignment, the permissions of a role, a membership — and
fails for a function that neither calls the sweep nor is listed here with the reason it need not.
"""

from __future__ import annotations

import ast
from pathlib import Path

from support.architecture import ROOT

APPLICATION = ROOT / "backend" / "erev_api"
MIGRATIONS = APPLICATION / "db" / "migrations"
# What a member holds: the assignments, what a role carries, and the membership itself.
ACCESS_TABLES = frozenset({"role_assignment", "role_permission", "tenant_membership"})
WRITES = frozenset({"insert", "update", "delete"})
SWEEPS = frozenset({"end_unsupported", "end_unsupported_rows"})
# ``<module path under erev_api>:<function>`` → why the write changes no delegation's support.
EXEMPT = {
    "auth/sessions.py:_mark_opened": (
        "stamps last_opened_at on the member's own row: no status and no grant changes"
    ),
    "domain/platform/memberships.py:accept_invitation": (
        "INVITED becomes ACTIVE: a member who was never active gave no delegation, a delegation "
        "is given only by a session of an ACTIVE member, and what a member removed and invited "
        "again had given, or had been given, ended with the removal"
    ),
    "domain/platform/provisioning.py:grant_bootstrap_admin": (
        "the first administrator's grant of a workspace being created (provisioning, a sandbox "
        "reset): the workspace holds no delegation yet"
    ),
    "domain/platform/provisioning.py:provision_tenant": (
        "inserts the first membership of a workspace being created: no delegation exists"
    ),
    "domain/platform/provisioning.py:seed_workspace": (
        "the system roles of a workspace being created: no member holds one yet"
    ),
    "domain/platform/users.py:invite_user": (
        "inserts the membership of a new invitation: its roles are granted through the approval "
        "of ROLE_ASSIGNMENT requests, which runs the sweep; a removed membership invited again "
        "is written by `_set_status`, which sweeps before and after"
    ),
}


def _table_of(call: ast.Call) -> str | None:
    """``insert(<table>)``, ``update(<table>)`` or ``delete(<table>)`` of an access table."""
    if not (isinstance(call.func, ast.Name) and call.func.id in WRITES and call.args):
        return None
    target = call.args[0]
    return target.id if isinstance(target, ast.Name) and target.id in ACCESS_TABLES else None


def _called(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return call.func.id if isinstance(call.func, ast.Name) else None


def access_writers(root: Path = APPLICATION) -> dict[str, bool]:
    """``<module>:<function>`` of every function that writes an access table → whether it calls
    the sweep itself. A nested function counts with the function that holds it."""
    found: dict[str, bool] = {}
    for path in sorted(root.rglob("*.py")):
        if MIGRATIONS in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = [inner for inner in ast.walk(node) if isinstance(inner, ast.Call)]
            if not any(_table_of(call) for call in calls):
                continue
            ref = f"{path.relative_to(root).as_posix()}:{node.name}"
            found[ref] = any(_called(call) in SWEEPS for call in calls)
    return found


def test_dg_krn_apr_09_every_writer_of_access_ends_what_it_leaves_unsupported() -> None:
    writers = access_writers()
    assert len(writers) >= 9, writers
    unhooked = {ref for ref, hooked in writers.items() if not hooked}
    assert unhooked == set(EXEMPT), {
        "writes access without the sweep and without a stated reason": sorted(
            unhooked - set(EXEMPT)
        ),
        "listed as exempt and no longer a writer without the sweep": sorted(set(EXEMPT) - unhooked),
    }
    # The commands that take access away or give it, by name: each runs the sweep.
    hooked = {ref for ref, calls_sweep in writers.items() if calls_sweep}
    assert hooked >= {
        "approvals/subjects.py:_apply_role_assignment",
        "approvals/subjects.py:_apply_role_change",
        "domain/platform/privacy.py:_remove_membership_in_tenant",
        "domain/platform/roles.py:revoke_role_assignment",
        "domain/platform/users.py:_set_status",
        "domain/platform/users.py:remove_membership",
    }, sorted(hooked)


def test_the_scan_sees_a_writer_without_the_sweep(tmp_path: Path) -> None:
    """The check can fail: a function that revokes a role assignment and calls nothing is found
    as unhooked, and one that calls the sweep as hooked."""
    module = tmp_path / "domain" / "platform"
    module.mkdir(parents=True)
    (module / "example.py").write_text(
        "def forgets(uow):\n"
        "    uow.session.execute(update(role_assignment).values(revoked_at=uow.now))\n"
        "\n"
        "def remembers(uow):\n"
        "    uow.session.execute(delete(role_permission))\n"
        "    delegations.end_unsupported(uow, cause='x')\n"
        "\n"
        "def reads(uow):\n"
        "    uow.session.execute(select(role_assignment))\n",
        encoding="utf-8",
    )
    assert access_writers(tmp_path) == {
        "domain/platform/example.py:forgets": False,
        "domain/platform/example.py:remembers": True,
    }
