"""dev-guide DG-KRN-DB-13 (rev 1.293; 04 T-PLT-02 rev 1.315; D-80 on SPEC-Q-182 (c); item
IDENTITY-BEFORE-ACCEPTANCE-READERS-1): what a workspace is shown of the person behind a
membership is ONE rule, and every statement that reads the person of a membership takes it.

``app_user`` is the directory of every workspace's people (RLS-NONE-U): a statement that joins a
membership to its person can read the name and the last sign-in a person has elsewhere. D-80
rule 5 withholds both until an invitation of a person who already had an identity is accepted —
and the rule was read by API-S-User alone. Measured through the routes before this rule: the
summary of a role request, ``GET /role-assignments``, the label of an audit event and an access
review each named a person the workspace had only invited, and the review gave that person's
last sign-in in another workspace. Whoever may invite an address learnt the name behind it.

The rule lives in ``erev_api.domain.platform.users``: ``IDENTITY_WITHHELD``, ``SHOWN_NAME``
(``SHOWN_DISPLAY_NAME`` is the same, labelled), ``SHOWN_LAST_LOGIN`` and ``shown_name``. This test
reads every function of ``backend/erev_api`` outside that module and finds those that read
``app_user.display_name`` or ``app_user.last_login_at`` themselves — a column of the table or of
an alias of it, by attribute or by subscript, and a SELECT of the whole row. Such a reader is in
one of two closed lists, with the reason no withheld identity reaches it, or the test fails:

- ``OF_A_MEMBERSHIP``: the function also names ``tenant_membership``. It reads the person of a
  membership past the rule, so the reason says why the rule is not owed there: the person's own
  page, a member the statement admits only while ACTIVE, or a record that names who acted —
  the rule goes by the membership's status since rev 1.294 (item
  IDENTITY-WITHHELD-BY-STATUS-1), so "has been ACTIVE" is no reason any more;
- ``BY_USER_ID``: the function names no membership. It reads a person by an id a row carries:
  someone who acted in the workspace, the person who is signing in, an operator.

A new reader takes the rule or states its reason here; an entry that no longer reads is removed.
Not seen: SQL text, a column reached through a name the scan cannot follow (a table handed in as
an argument), and a user id that a caller took from a membership before it calls a ``BY_USER_ID``
reader — the one such caller today, the owner of a close checklist item, has no writer.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from support.architecture import ROOT

APPLICATION: Final = ROOT / "backend" / "erev_api"
MIGRATIONS: Final = "db/migrations/"
# The rule's module: the two columns are read here, in the expressions every other reader takes.
RULE: Final = "domain/platform/users.py"
TABLE: Final = "app_user"
MEMBERSHIP: Final = "tenant_membership"
COLUMNS: Final = frozenset({"display_name", "last_login_at"})
ALIASES: Final = frozenset({"alias", "aliased"})
# What a reader takes instead of the columns.
TAKES: Final = frozenset(
    {"SHOWN_NAME", "SHOWN_DISPLAY_NAME", "SHOWN_LAST_LOGIN", "shown_name", "member_select"}
)
# ``<module path under erev_api>:<function>`` → why the person of the membership it reads is never
# one whose identity is withheld.
OF_A_MEMBERSHIP: Final = {
    "auth/invitations.py:find_invitation": (
        "the invitation's own page, read with the invitation's token: the invited person reads "
        "their own name, and who invited them by that person's user id"
    ),
    "domain/platform/me.py:me": "API-S-Me: the signed-in person's own identity",
    "domain/reports/builders/sod_conflict_report.py:_delegated": (
        "the delegator of a delegation RPT-25 counts at as_of, named as the person who GAVE "
        "it: the record of a delegation given while the workspace read that name, kept on "
        "the name by the supervisor's ruling on item IDENTITY-WITHHELD-BY-STATUS-1 — the "
        "delegation's own row follows the rule (`delegation_outs`)"
    ),
    "domain/platform/sandboxes.py:sandbox_actor": (
        "the requester of a period replay, by user id, after the statement that requires their "
        "ACTIVE membership of the sandbox"
    ),
    "events/notifications.py:notify": (
        "the members a notification is addressed to: ACTIVE, by the statement's own condition"
    ),
}
# ``<module>:<function>`` → whose user id it reads.
BY_USER_ID: Final = {
    "approvals/engine.py:_display_name": (
        "the preparer of a request, in the message to its approvers: a person who acted here"
    ),
    "auth/sessions.py:authenticate": "the person whose session it is",
    "auth/sessions.py:sign_in": "the person who signs in",
    "auth/sessions.py:sign_in_external": "the person who signs in through an identity provider",
    "domain/close/commands.py:_display_name": (
        "the requester and the approvers of a reopen, in its message: people who acted here"
    ),
    "domain/contracts/queries.py:_actor_names": "the actors of a contract's events",
    "domain/platform/actors.py:named": (
        "API-S-Actor of the principal a row is stamped with: someone who acted here"
    ),
    "domain/platform/approval_queries.py:display_names": (
        "the people a caller names by user id — the preparer and the deciders of a request, a "
        "delegation's creator and revoker, the stamps of a row: people who acted here"
    ),
    "domain/platform/audit_labels.py:_user": (
        "the label of an `app_user` object: only the erasure writes such an event, and the name "
        "is the one it wrote (05 PRV-07 a)"
    ),
    "domain/platform/privacy.py:_lock_user": "the erasure locks and reads the person it erases",
    "domain/platform/support_grants.py:_operator": (
        "the operator a support grant names by email: a platform identity, no member"
    ),
    "domain/reports/builders/late_entry_report.py:_names": "who appended the late entries",
}
# The readers of a membership's person that take the rule, by name: each is one the workspace
# reads about a member who may not have accepted yet.
TAKERS: Final = frozenset(
    {
        "domain/platform/actors.py:member",
        "domain/platform/approval_delegations.py:delegation_outs",
        "domain/platform/access_reviews.py:campaign_outs",
        "domain/platform/access_reviews.py:item_outs",
        "domain/platform/access_reviews.py:snapshot_memberships",
        "domain/platform/audit_labels.py:_member",
        "domain/platform/roles.py:assignment_select",
        "domain/platform/roles.py:requested_assignment_out",
        "domain/platform/sod.py:_member",
        "domain/platform/sod.py:exception_select",
        "domain/reports/builders/sod_conflict_report.py:conflicts",
        "domain/reports/builders/user_access_listing.py:members",
    }
)


def _sources(tree: ast.AST) -> set[str]:
    """The names the table goes by in a module: its own, and what an alias of it is bound to."""
    found = {TABLE}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        of_table = (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in ALIASES
            and _is_table(call.func.value, found)
        ) or (
            isinstance(call.func, ast.Name)
            and call.func.id in ALIASES
            and bool(call.args)
            and _is_table(call.args[0], found)
        )
        if of_table:
            found |= {target.id for target in node.targets if isinstance(target, ast.Name)}
    return found


def _is_table(node: ast.AST, sources: set[str]) -> bool:
    """``app_user``, a name an alias of it is bound to, or ``<module>.app_user``."""
    if isinstance(node, ast.Name):
        return node.id in sources
    return isinstance(node, ast.Attribute) and node.attr == TABLE


def _reads(node: ast.AST, sources: set[str]) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Attribute) and inner.attr in COLUMNS:
            columns = inner.value  # <table>.c.<column>
        elif (
            isinstance(inner, ast.Subscript)
            and isinstance(inner.slice, ast.Constant)
            and inner.slice.value in COLUMNS
        ):
            columns = inner.value  # <table>.c["<column>"]
        elif isinstance(inner, ast.Call) and _whole_row(inner, sources):
            return True
        else:
            continue
        if (
            isinstance(columns, ast.Attribute)
            and columns.attr in {"c", "columns"}
            and _is_table(columns.value, sources)
        ):
            return True
    return False


def _whole_row(call: ast.Call, sources: set[str]) -> bool:
    """``select(app_user, ...)`` or ``app_user.select()``: every column of the row."""
    if isinstance(call.func, ast.Name) and call.func.id == "select":
        return any(_is_table(argument, sources) for argument in call.args)
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "select"
        and _is_table(call.func.value, sources)
    )


def _names(node: ast.AST, wanted: frozenset[str]) -> bool:
    return any(
        (isinstance(inner, ast.Name) and inner.id in wanted)
        or (isinstance(inner, ast.Attribute) and inner.attr in wanted)
        for inner in ast.walk(node)
    )


def _functions(tree: ast.Module) -> list[tuple[str, list[ast.stmt]]]:
    """(name, body) of every top-level function and method — a nested function counts with the
    one that holds it — and ``<module>`` for the statements outside them."""
    found: list[tuple[str, list[ast.stmt]]] = []
    outside: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.append((node.name, [node]))
        elif isinstance(node, ast.ClassDef):
            found.extend(
                (f"{node.name}.{inner.name}", [inner])
                for inner in node.body
                if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef)
            )
        else:
            outside.append(node)
    return [*found, ("<module>", outside)]


def identity_readers(root: Path = APPLICATION) -> dict[str, bool]:
    """``<module>:<function>`` of every function outside the rule's module that reads a person's
    name or last sign-in itself → whether it names a membership too."""
    found: dict[str, bool] = {}
    for path in sorted(root.rglob("*.py")):
        module = path.relative_to(root).as_posix()
        if module.startswith(MIGRATIONS) or module == RULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        sources = _sources(tree)
        for name, body in _functions(tree):
            holder = ast.Module(body=body, type_ignores=[])
            if _reads(holder, sources):
                found[f"{module}:{name}"] = _names(holder, frozenset({MEMBERSHIP}))
    return found


def rule_takers(root: Path = APPLICATION) -> set[str]:
    """``<module>:<function>`` of every function outside the rule's module that takes the rule."""
    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        module = path.relative_to(root).as_posix()
        if module.startswith(MIGRATIONS) or module == RULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, body in _functions(tree):
            if _names(ast.Module(body=body, type_ignores=[]), TAKES):
                found.add(f"{module}:{name}")
    return found


def test_dg_krn_db_13_the_person_of_a_membership_is_read_through_the_rule() -> None:
    readers = identity_readers()
    of_a_membership = {ref for ref, names_membership in readers.items() if names_membership}
    by_user_id = set(readers) - of_a_membership
    assert of_a_membership == set(OF_A_MEMBERSHIP), {
        "reads the name or the last sign-in of a membership's person past the rule "
        "(take users.SHOWN_NAME, users.SHOWN_LAST_LOGIN or users.shown_name)": sorted(
            of_a_membership - set(OF_A_MEMBERSHIP)
        ),
        "listed and no longer such a reader": sorted(set(OF_A_MEMBERSHIP) - of_a_membership),
    }
    assert by_user_id == set(BY_USER_ID), {
        "reads a person's name or last sign-in by an id, without a stated reason": sorted(
            by_user_id - set(BY_USER_ID)
        ),
        "listed and no longer such a reader": sorted(set(BY_USER_ID) - by_user_id),
    }
    assert not set(OF_A_MEMBERSHIP) & set(BY_USER_ID)
    # The readers the workspace asks about a member who may not have accepted yet, by name.
    takers = rule_takers()
    assert takers >= TAKERS, sorted(TAKERS - takers)
    # And the rule's module holds the rule: the summary of a role request reads the name there.
    rule = ast.parse((APPLICATION / RULE).read_text(encoding="utf-8"))
    defined = {
        target.id
        for node in rule.body
        if isinstance(node, ast.Assign | ast.AnnAssign)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    } | {node.name for node in rule.body if isinstance(node, ast.FunctionDef)}
    assert defined >= TAKES | {"IDENTITY_WITHHELD", "request_role_assignment"}
    [request] = [
        node
        for node in rule.body
        if isinstance(node, ast.FunctionDef) and node.name == "request_role_assignment"
    ]
    assert _names(request, frozenset({"shown_name"}))
    assert "member_name" not in {argument.arg for argument in request.args.kwonlyargs}


def test_the_scan_sees_a_reader_past_the_rule(tmp_path: Path) -> None:
    """The check can fail: a function that joins a membership to the person's name is found as a
    reader of a membership's person — by the column, through an alias, by subscript and by the
    whole row — one that reads by user id as that, and one that takes the rule as neither."""
    module = tmp_path / "domain" / "platform"
    module.mkdir(parents=True)
    (module / "example.py").write_text(
        "person = app_user.alias('person')\n"
        "\n"
        "def names_the_member(session, membership_id):\n"
        "    joined = tenant_membership.join(app_user)\n"
        "    return session.execute(select(app_user.c.display_name).select_from(joined))\n"
        "\n"
        "def through_an_alias(session):\n"
        "    return select(person.c.last_login_at).join(tenant_membership)\n"
        "\n"
        "def by_subscript(session):\n"
        "    return select(tables.app_user.c['display_name']).join(tables.tenant_membership)\n"
        "\n"
        "def the_whole_row(session, user_id):\n"
        "    return session.execute(select(app_user).where(app_user.c.id == user_id))\n"
        "\n"
        "def by_user_id(session, user_id):\n"
        "    return select(app_user.c.display_name).where(app_user.c.id == user_id)\n"
        "\n"
        "def takes_the_rule(session):\n"
        "    joined = tenant_membership.join(app_user)\n"
        "    return select(users.SHOWN_NAME, app_user.c.email).select_from(joined)\n"
        "\n"
        "def another_name(session):\n"
        "    return select(tenant.c.display_name, tenant_membership.c.id)\n",
        encoding="utf-8",
    )
    assert identity_readers(tmp_path) == {
        "domain/platform/example.py:names_the_member": True,
        "domain/platform/example.py:through_an_alias": True,
        "domain/platform/example.py:by_subscript": True,
        "domain/platform/example.py:the_whole_row": False,
        "domain/platform/example.py:by_user_id": False,
    }
    assert rule_takers(tmp_path) == {"domain/platform/example.py:takes_the_rule"}
