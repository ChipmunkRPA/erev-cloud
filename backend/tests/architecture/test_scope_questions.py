"""DG-KRN-APR-06 (rev 1.295): the census of the questions that read further than a route (04
§16.10 rev 1.319 "The request's row is the kernel's"; 03 REQ-PLT-012 rev 1.146; item
READ-SCOPE-BY-PERMISSION-1, register index 301; the supervisor's ruling of 2026-10-03, 10:02Z).

A guarded transaction reads and writes under the scope of the permission that admitted it
(``tests/architecture/test_route_scope.py``). The approvals kernel and its kin ask another
question — whether the caller READS what she asks about, for every entity of it — and the answer
can be yes where the route's own permission covers one of those entities and not the rest: a
Revenue Accountant of one contracting entity who is a Viewer of the other submits a modification
of a contract grouped across the two. A statement that follows such an answer in the same
transaction and reads or writes a row of the entity the route does not cover runs behind the row
policy of the route's permission; measured before the item's fixes, the insert of a request was
refused by the policy's check and a stored preview was called stale that was not.

So every call site of those questions is listed here once, by function, with what becomes of
the statements that follow it. A new call site fails until it is read and listed.

- ``KERNEL``: the request's own row — looked for, inserted, read back, locked, closed — under
  the tenant's scope since rev 1.319, inside the kernel's function that the site calls.
- ``BEFORE``: the site's function opened the tenant's scope for what follows before the item.
- ``NOW``: the item put what follows under the tenant's scope, in the site's function.
- ``NONE``: not concerned, with the reason in its first word — ``pure`` (nothing follows that
  reads a row under the entity policy), ``own`` (what follows is the subject's own row, of the
  entity the route's permission found it under), ``workspace`` (the tables that follow carry
  no entity policy), ``union`` (the route has no permission guard and keeps the union of the
  caller's roles), ``defers`` (a job computes, as SYSTEM), ``job`` (an import job, narrowed to
  its uploader's bounds for the template's write permission), ``predicate`` (a condition of a
  read: it admits no row the statement's own scope hides).

What the list can hold and what it cannot. It holds the call sites: the walker finds every call
by the function it resolves to, through each module's imports. It ties ``BEFORE`` and ``NOW``
to the door of DG-KRN-DB-05 (``test_computation_scope.DOOR``), ``KERNEL`` to the kernel's
functions that open the scope there, and ``defers`` to a deferred job after the question. It
cannot hold that a reason is true: ``own`` and ``workspace`` were read, function by function,
and the witnesses of ``tests/api/test_read_scope_by_permission.py`` run the commands a member
of the first paragraph meets.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final

from support.architecture import imports, iter_files, module_name, read
from tests.architecture.test_computation_scope import DOOR, EVERY_SCOPE, SYSTEM_SCOPE

ENGINE: Final = "erev_api.approvals.engine"
READERS: Final = "erev_api.approvals.readers"
QUERIES: Final = "erev_api.domain.platform.approval_queries"
FILE_ACCESS: Final = "erev_api.domain.platform.file_access"
IMPORT_SCOPE: Final = "erev_api.domain.imports.scope"
NOTIFICATIONS: Final = "erev_api.events.notifications"
# The questions, by the function that answers: the kernel's and its kin's. ``engine.withdraw``
# is held by ``test_withdraw_through_subject.py``.
QUESTIONS: Final = frozenset(
    {
        # the kernel's question, and who asks it of a preparer, a delegate and a reader
        f"{READERS}.read_in_full",
        f"{ENGINE}.own_scope_covers",
        f"{ENGINE}.refuse_outside_scope",
        f"{ENGINE}.require_preparer_scope",
        f"{ENGINE}.require_preview_scope",
        f"{ENGINE}.require_contract_preview_scope",
        f"{ENGINE}.find_authority",
        f"{ENGINE}.visible_to",
        # the kernel's commands that ask it, or stand behind a command that did
        f"{ENGINE}.submit",
        f"{ENGINE}.void_if_stale",
        f"{ENGINE}.void_subject",
        # its statements over ``approval_request``
        f"{QUERIES}._own_scope_covers",
        f"{QUERIES}.visible",
        f"{QUERIES}.content_visible",
        f"{QUERIES}.content_readable",
        f"{QUERIES}.decidable",
        # a stored preview, the summary of a dry run, a request's document
        f"{FILE_ACCESS}.request_content_visible",
        f"{FILE_ACCESS}.stored_preview_readable",
        f"{FILE_ACCESS}.preview_summary_readable",
        # an import: who reads an upload, and what its uploader may write
        f"{IMPORT_SCOPE}.visible",
        f"{IMPORT_SCOPE}.require_visible",
        f"{IMPORT_SCOPE}.uploader_bounds",
        f"{IMPORT_SCOPE}.require_covered",
        # who is told and who waits: the same question over every membership
        f"{NOTIFICATIONS}.entity_scope_covering",
        f"{NOTIFICATIONS}.permission_holders_covering",
    }
)
KERNEL: Final = "KERNEL"
BEFORE: Final = "BEFORE"
NOW: Final = "NOW"
NONE: Final = "NONE"
REASONS: Final = frozenset({"pure", "own", "workspace", "union", "defers", "job", "predicate"})
# The kernel's functions that hold a request's row under the tenant's scope (the door).
KERNEL_FUNCTIONS: Final = frozenset({"submit", "withdraw", "void_if_stale", "void_subject"})


@dataclass(frozen=True, slots=True)
class Site:
    calls: frozenset[str]  # the questions the function asks, by their short name
    then: str  # KERNEL, BEFORE, NOW or NONE
    why: str
    door: tuple[str, str] | None = None  # who opens the tenant's scope, when not the function


def site(calls: str, then: str, why: str, *, door: tuple[str, str] | None = None) -> Site:
    return Site(frozenset(calls.split()), then, why, door)


_ENGINE: Final = "backend/erev_api/approvals/engine.py"
_SUBJECTS: Final = "backend/erev_api/approvals/subjects.py"
_QUERIES: Final = "backend/erev_api/domain/platform/approval_queries.py"
_FILES: Final = "backend/erev_api/domain/platform/file_access.py"
_CLOSE: Final = "backend/erev_api/domain/close/commands.py"
_ESTIMATES: Final = "backend/erev_api/domain/contracts/estimates.py"
_EVENTS: Final = "backend/erev_api/domain/contracts/events.py"
_MODIFICATIONS: Final = "backend/erev_api/domain/contracts/modifications.py"
_COMMIT: Final = "backend/erev_api/domain/imports/commit.py"
_EXCEPTIONS: Final = "backend/erev_api/domain/imports/exceptions.py"
_IMPORT_QUERIES: Final = "backend/erev_api/domain/imports/queries.py"
_ADJUSTMENTS: Final = "backend/erev_api/domain/journals/adjustments.py"
_JOURNALS: Final = "backend/erev_api/domain/journals/commands.py"
_SOD: Final = "backend/erev_api/domain/platform/sod.py"
_USERS: Final = "backend/erev_api/domain/platform/users.py"
_OVERRIDES: Final = "backend/erev_api/domain/policies/overrides.py"
_REFERENCE: Final = "backend/erev_api/domain/reference/commands.py"
_NOTIFY: Final = "backend/erev_api/events/notifications.py"

ROW: Final = "the request's row: found, inserted and read back by engine.submit"
ONE_ENTITY: Final = (
    "own: the subject is of one entity, the one the route's permission found it under"
)
TENANT_LEVEL: Final = "workspace: a tenant-level subject and the workspace's own tables"
APPROVALS_ROUTE: Final = (
    "union: the approvals routes carry no permission guard, and the union of the caller's "
    "roles holds every entity the question admits"
)
PREDICATE: Final = "predicate: a condition over approval_request, asked on the approvals routes"

CENSUS: Final = {
    # --- the kernel -------------------------------------------------------------------------------
    (_ENGINE, "own_scope_covers"): site("read_in_full", NONE, "pure: the question itself"),
    (_ENGINE, "refuse_outside_scope"): site(
        "own_scope_covers", NONE, "pure: the refusal by name and its DENIED event (audit)"
    ),
    (_ENGINE, "require_preparer_scope"): site(
        "refuse_outside_scope", NONE, "pure: the question for a stored subject; see its callers"
    ),
    (_ENGINE, "require_preview_scope"): site(
        "refuse_outside_scope", NONE, "pure: the question for a stored subject; see its callers"
    ),
    (_ENGINE, "require_contract_preview_scope"): site(
        "refuse_outside_scope", NONE, "pure: the question for a contract; see its caller"
    ),
    (_ENGINE, "submit"): site(
        "refuse_outside_scope",
        KERNEL,
        "the second look for a pending request, the insert, the auto-approval and the read-back",
    ),
    (_ENGINE, "find_authority"): site(
        "own_scope_covers", NONE, "pure: own grants first, then the delegations (workspace)"
    ),
    (_ENGINE, "can_decide"): site("find_authority", NONE, APPROVALS_ROUTE),
    (_ENGINE, "decide"): site(
        "find_authority",
        BEFORE,
        "the hooks of a decision; its lock and its rows under the union of an approvals route",
        door=(_ENGINE, "_apply_decision"),
    ),
    (_ENGINE, "visible_to"): site("own_scope_covers", NONE, "pure: the reading rule of a request"),
    (_ENGINE, "_require_visible"): site("visible_to", NONE, APPROVALS_ROUTE),
    (_ENGINE, "_eligible_memberships"): site(
        "permission_holders_covering", NONE, "workspace: memberships, roles and assignments"
    ),
    (_ENGINE, "_preparer_summary"): site(
        "read_in_full", NONE, "workspace: the preparer's grants; it chooses a text"
    ),
    (_SUBJECTS, "_void_stale_assignment_requests"): site(
        "void_if_stale", KERNEL, "inside a decision's hook, itself at the door"
    ),
    (_SUBJECTS, "_void_stale_exception_requests"): site(
        "void_if_stale", KERNEL, "inside a decision's hook, itself at the door"
    ),
    # --- the kernel's statements over approval_request ------------------------------------------
    (_QUERIES, "visible"): site("_own_scope_covers", NONE, PREDICATE),
    (_QUERIES, "content_visible"): site("_own_scope_covers", NONE, PREDICATE),
    (_QUERIES, "_assigned"): site("_own_scope_covers", NONE, PREDICATE),
    (_QUERIES, "content_readable"): site("content_visible", NONE, PREDICATE),
    (_QUERIES, "shown"): site("content_visible", NONE, PREDICATE),
    (_QUERIES, "_custom_clauses"): site("decidable", NONE, APPROVALS_ROUTE),
    ("backend/erev_api/domain/reports/dashboard.py", "_pending_approvals"): site(
        "decidable",
        NOW,
        "the Home's count of the requests that wait for the caller, as the inbox counts them",
        door=("backend/erev_api/domain/reports/dashboard.py", "home"),
    ),
    (_QUERIES, "list_approvals"): site("visible", NONE, APPROVALS_ROUTE),
    (_QUERIES, "get_approval"): site("visible", NONE, APPROVALS_ROUTE),
    (_QUERIES, "approval_outs"): site("content_readable", NONE, APPROVALS_ROUTE),
    # --- documents, previews, summaries ----------------------------------------------------------
    (_FILES, "request_content_visible"): site(
        "content_readable", NONE, "predicate: one statement over approval_request, the files' own"
    ),
    (_FILES, "_through_request"): site(
        "request_content_visible", NONE, "union: the file routes carry no permission guard"
    ),
    (_FILES, "_through_modification"): site(
        "stored_preview_readable", NONE, "union: the file routes carry no permission guard"
    ),
    (_FILES, "_through_adjustment"): site(
        "stored_preview_readable", NONE, "union: the file routes carry no permission guard"
    ),
    (_FILES, "preview_summary_readable"): site(
        "stored_preview_readable", NONE, "pure: the same question for the summary of a dry run"
    ),
    ("backend/erev_api/domain/platform/jobs.py", "_answered"): site(
        "preview_summary_readable", NONE, "union: the job routes carry no permission guard"
    ),
    ("backend/erev_api/domain/platform/attachments.py", "preview_refusal"): site(
        "request_content_visible", NONE, "workspace: the attachment and its file"
    ),
    (_MODIFICATIONS, "preview_answered"): site(
        "stored_preview_readable", NONE, "workspace: the stored document, a file of the workspace"
    ),
    (_ADJUSTMENTS, "adjustment_outs"): site(
        "stored_preview_readable", NONE, "workspace: it withholds or names a file id"
    ),
    # --- a preview: the question, then a job ----------------------------------------------------
    (_MODIFICATIONS, "request_preview"): site(
        "require_preview_scope", NONE, "defers: the dry run is the job's"
    ),
    (_ESTIMATES, "request_preview"): site(
        "require_preview_scope", NONE, "defers: the dry run is the job's"
    ),
    (_ADJUSTMENTS, "preview"): site(
        "require_preview_scope", NONE, "defers: the dry run is the job's"
    ),
    (_EVENTS, "request_preview"): site(
        "require_contract_preview_scope", NONE, "defers: the dry run is the job's"
    ),
    # --- a submission: contracts and what is recorded on them --------------------------------
    (_MODIFICATIONS, "submit"): site(
        "require_preparer_scope submit",
        NOW,
        "the content the row keeps the hash of; the basis of the stored preview "
        "(_stored_preview); " + ROW,
    ),
    (_MODIFICATIONS, "update_modification"): site(
        "void_if_stale",
        KERNEL,
        "the request of a modification names its contract's entity, or several: the look "
        "between is the route's own",
    ),
    (_ESTIMATES, "submit_version"): site(
        "submit", NOW, "the content the row keeps the hash of; " + ROW
    ),
    ("backend/erev_api/domain/contracts/activation.py", "submit_activation"): site(
        "submit",
        BEFORE,
        "the flags and the amount the request states (ACT-FLAGS-1); the bundle at the door; " + ROW,
    ),
    ("backend/erev_api/domain/contracts/void.py", "request_void"): site(
        "submit", KERNEL, "a member of a combined group is refused: one entity; " + ROW
    ),
    ("backend/erev_api/domain/contracts/combination.py", "submit_group"): site(
        "submit",
        KERNEL,
        "every contract of the proposal is read and locked under the route's scope first: "
        "404 otherwise; " + ROW,
    ),
    (_EVENTS, "_submit"): site(
        "submit", KERNEL, "the preparer is held to the one contract she records on; " + ROW
    ),
    (_EVENTS, "request_void"): site(
        "submit", KERNEL, "the preparer is held to the one contract she records on; " + ROW
    ),
    (_OVERRIDES, "submit_override"): site(
        "submit", KERNEL, "the override's own row, a row of the workspace; " + ROW
    ),
    (_OVERRIDES, "request_ssp_override"): site(
        "submit", KERNEL, "the obligation and its pins, rows of the workspace; " + ROW
    ),
    ("backend/erev_api/domain/policies/judgements.py", "submit_judgement"): site(
        "submit", KERNEL, "the record's own row; the hold it applies computes at the door; " + ROW
    ),
    (_ADJUSTMENTS, "_routed"): site(
        "submit", KERNEL, "the adjustment's submit and deferral routes keep the union; " + ROW
    ),
    (_ADJUSTMENTS, "request_defer_past_lock"): site(
        "void_subject", KERNEL, "the pending request it replaces is closed by the kernel"
    ),
    # --- a submission: one entity, or none -----------------------------------------------------
    (_CLOSE, "request_lock"): site("submit", KERNEL, ONE_ENTITY),
    (_CLOSE, "request_permanent_lock"): site("submit", KERNEL, ONE_ENTITY),
    (_CLOSE, "request_reopen"): site("submit", KERNEL, ONE_ENTITY),
    (_CLOSE, "waive_checklist_item"): site("submit", KERNEL, ONE_ENTITY),
    (_JOURNALS, "submit_run"): site("submit", KERNEL, ONE_ENTITY),
    (_JOURNALS, "cancel_run"): site("void_subject", KERNEL, ONE_ENTITY),
    ("backend/erev_api/domain/ssp/publication.py", "submit_ssp_book_version"): site(
        "submit", KERNEL, "workspace: the SSP tables carry no entity policy; " + ROW
    ),
    ("backend/erev_api/domain/policies/lifecycle.py", "submit"): site(
        "submit",
        KERNEL,
        "the version's own row; an account mapping version that ends another entity's rules "
        "names that entity alone (R-64 (2)): " + ROW,
    ),
    (_REFERENCE, "submit_fx_rate_set_version"): site("submit", KERNEL, TENANT_LEVEL),
    (_REFERENCE, "propose_principal_agent_change"): site("submit", KERNEL, TENANT_LEVEL),
    (_REFERENCE, "propose_policy_values_change"): site("submit", KERNEL, TENANT_LEVEL),
    ("backend/erev_api/domain/migration/commands.py", "import_batch"): site(
        "submit", KERNEL, TENANT_LEVEL
    ),
    ("backend/erev_api/domain/platform/roles.py", "_request_change"): site(
        "submit", KERNEL, TENANT_LEVEL
    ),
    (_SOD, "create_sod_rule_version"): site("submit", KERNEL, TENANT_LEVEL),
    (_SOD, "request_sod_exception"): site("submit", KERNEL, TENANT_LEVEL),
    (_SOD, "end_for_invitation"): site(
        "void_if_stale", KERNEL, "workspace: the exceptions of a membership"
    ),
    (_USERS, "request_role_assignment"): site(
        "submit", KERNEL, "workspace: memberships and assignments; the request names the grant's"
    ),
    (_USERS, "_void_stale_role_requests"): site(
        "void_if_stale", BEFORE, "the role requests a removed membership left pending"
    ),
    ("backend/erev_api/domain/platform/support_grants.py", "request_support_grant"): site(
        "submit", KERNEL, "workspace: a grant for every entity names none on its row"
    ),
    ("backend/erev_api/auth/api_clients.py", "create_api_client"): site(
        "submit", KERNEL, "workspace: the client and its grants"
    ),
    ("backend/erev_api/domain/platform/evidence_shred.py", "request_shred"): site(
        "submit",
        KERNEL,
        "the route's permission was asked for every entity of the records that hold the file",
    ),
    # --- imports and the exception queue -----------------------------------------------------
    (_COMMIT, "submit_import"): site(
        "require_visible uploader_bounds require_covered submit",
        KERNEL,
        "the upload is a row of the workspace; its request names the entities of the "
        "template's write permission, not of import.upload: " + ROW,
    ),
    (_COMMIT, "commit_upload"): site(
        "uploader_bounds require_covered", NONE, "job: narrowed to the uploader's bounds"
    ),
    ("backend/erev_api/domain/imports/diff.py", "compute_diff"): site(
        "uploader_bounds", NONE, "job: narrowed to the uploader's bounds"
    ),
    ("backend/erev_api/domain/imports/validate.py", "validate_upload"): site(
        "uploader_bounds", NONE, "job: narrowed to the uploader's bounds"
    ),
    ("backend/erev_api/domain/imports/commands.py", "cancel_import"): site(
        "require_visible", NONE, "workspace: the upload and its rows"
    ),
    (_IMPORT_QUERIES, "_upload"): site(
        "require_visible", NONE, "workspace: the upload and its rows"
    ),
    (_IMPORT_QUERIES, "imports_statement"): site(
        "visible", NONE, "predicate: over import_upload, a table of the workspace"
    ),
    (_EXCEPTIONS, "readable"): site(
        "visible", NONE, "predicate: beside the row policy of exception_item"
    ),
    (_EXCEPTIONS, "asking"): site(
        "own_scope_covers", NONE, "pure: which waivers the page offers; no statement follows"
    ),
    (_EXCEPTIONS, "request_waiver"): site(
        "submit",
        KERNEL,
        "a waiver names the item's entity, which exception.resolve was asked for, or several "
        "or every entity, and such a request names none on its row",
    ),
    # --- who is told ------------------------------------------------------------------------------
    (_NOTIFY, "permission_holders_covering"): site(
        "entity_scope_covering", NONE, "workspace: memberships, roles and assignments"
    ),
    (_NOTIFY, "permission_holders"): site(
        "entity_scope_covering", NONE, "workspace: memberships, roles and assignments"
    ),
}


def _bound(path: str, tree: ast.AST) -> dict[str, str]:
    """Local name → what an import binds it to: a module, or ``module.name``."""
    bound: dict[str, str] = {}
    for item in imports(path, tree):
        if not item.names:
            alias = item.asnames[0]
            if alias is not None:
                bound[alias] = item.module
            continue
        for name, alias in zip(item.names, item.asnames, strict=True):
            bound[alias or name] = f"{item.module}.{name}"
    return bound


def _owners(tree: ast.AST) -> dict[int, str]:
    """Every node inside a function → the top-level function, or the method, that holds it."""
    inside: dict[int, str] = {}
    for node in ast.iter_child_nodes(tree):
        functions: list[tuple[str, ast.AST]] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            functions += [
                (f"{node.name}.{item.name}", item)
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        for name, function in functions:
            for child in ast.walk(function):
                inside[id(child)] = name
    return inside


def _target(node: ast.Call, module: str, bound: dict[str, str]) -> str | None:
    """The function a call resolves to: an imported name, a function of the module itself, or
    an attribute of an imported module."""
    callee = node.func
    if isinstance(callee, ast.Name):
        return bound.get(callee.id, f"{module}.{callee.id}")
    if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
        base = bound.get(callee.value.id)
        return None if base is None else f"{base}.{callee.attr}"
    return None


def asked() -> dict[tuple[str, str], dict[str, list[int]]]:
    """Every call of a question in the product: (file, function) → question → its lines."""
    found: dict[tuple[str, str], dict[str, list[int]]] = {}
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        tree = ast.parse(read(path), filename=path)
        module, bound, owners = module_name(path), _bound(path, tree), _owners(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _target(node, module, bound)
            if target not in QUESTIONS:
                continue
            where = (path, owners.get(id(node), "<module>"))
            name = str(target).rsplit(".", 1)[1]
            found.setdefault(where, {}).setdefault(name, []).append(node.lineno)
    return found


def test_every_call_of_a_question_that_reads_further_than_a_route_is_listed() -> None:
    found = asked()
    assert {where: frozenset(calls) for where, calls in found.items()} == {
        where: listed.calls for where, listed in CENSUS.items()
    }
    # the walker follows the imports: the two modules that take ``submit`` by another name
    assert "submit" in found[(_COMMIT, "submit_import")]
    assert len(found) > 70, len(found)  # 84 functions and 90 calls when the census was taken


def test_what_follows_a_question_is_held_where_the_list_says() -> None:
    door = set(DOOR[SYSTEM_SCOPE]) | set(DOOR[EVERY_SCOPE])
    found = asked()
    for (path, name), listed in CENSUS.items():
        where = f"{path}::{name}"
        assert listed.then in (KERNEL, BEFORE, NOW, NONE), where
        if listed.then == NONE:
            assert listed.why.split(":", 1)[0] in REASONS, where
        if listed.then in (BEFORE, NOW):
            # the function itself opens the tenant's scope, at the door — or the one it names
            assert (listed.door or (path, name)) in door, where
        else:
            assert listed.door is None, where
        if listed.then == KERNEL:
            # ... or it stands on a function of the kernel that does
            assert listed.calls & KERNEL_FUNCTIONS or name in KERNEL_FUNCTIONS, where
        if listed.why.startswith("defers"):
            source = ast.parse(read(path), filename=path)
            function = next(
                node
                for node in ast.walk(source)
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            question = min(line for lines in found[(path, name)].values() for line in lines)
            deferred = [
                node.lineno
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "defer"
            ]
            assert deferred and min(deferred) > question, where
    for name in sorted(KERNEL_FUNCTIONS):
        assert (_ENGINE, name) in door, name


# Item PREVIEW-INLINE-SCOPE-1 (04 API-S-ImpactSummary rev 1.319; found by this census): the reads
# of a contract's stored schedule and of its postings that a REQUEST states — (file, the reader,
# the functions that may call it). A schedule line and a subledger line are rows of the entity
# that performs; each call below stands inside ``system_entity_scope``, so the preview a request
# stores and the amount it routes on are the same whoever submits (R-64 (1)). The kernel reads
# ``posted_basis`` for the content under the scope it holds already (``contract_void_content``),
# and the void's hook under the hooks' (``_approved``).
STATED_READS: Final = {
    ("backend/erev_api/domain/contracts/events.py", "_before_revenue"): {"impact_summary"},
    ("backend/erev_api/domain/journals/adjustments.py", "_stored_revenue"): {"_measure"},
    ("backend/erev_api/domain/contracts/void.py", "posted_basis"): {"request_void", "_approved"},
}
UNDER_THE_HOOKS: Final = {("backend/erev_api/domain/contracts/void.py", "_approved")}


def _inside_the_scope(function: ast.AST, reader: str) -> list[bool]:
    """For every call of ``reader`` in ``function``: whether it stands, by the source, inside a
    ``with system_entity_scope(...)`` block."""
    wide: set[int] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.With) and any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == SYSTEM_SCOPE
            for item in node.items
        ):
            wide |= {id(child) for child in ast.walk(node)}
    return [
        id(node) in wide
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == reader
    ]


def test_what_a_request_states_of_its_contract_is_read_under_the_tenants_scope() -> None:
    for (path, reader), callers in STATED_READS.items():
        tree = ast.parse(read(path), filename=path)
        owners = _owners(tree)
        calling = {
            owners.get(id(node), "<module>")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == reader
        }
        assert calling == callers, (path, reader)
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in callers:
                continue
            placed = _inside_the_scope(node, reader)
            assert placed, (path, node.name)
            if (path, node.name) in UNDER_THE_HOOKS:
                continue  # ``engine._apply_decision`` holds the scope around the hook
            assert all(placed), (path, node.name, reader)
