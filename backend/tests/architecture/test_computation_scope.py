"""DG-ARC-16: the computation of a combination group chooses its own scope, and SYSTEM is a closed
door (05 RCP-18 and TXN-10, rev 1.82; dev-guide DG-KRN-DB-05, DG-KRN-UOW-05; supervisor rulings
R-95, R-98 (3) and R-103 (b) conditions (1) and (2)).

A computation is reader-independent: its bundle is read and its outputs are written under the
tenant's scope by SYSTEM, whoever asked for it and whatever scope an import narrowed the
transaction to. That is a property of the computation's own functions, not of their callers, and
this test holds it by reading the source:

1. ``bundles.build`` and ``bundles.index`` run their reads inside ``system_entity_scope``;
   ``compute_job.compute_group``, ``computation.persist`` and ``computation.recompute`` run their
   bodies inside ``UnitOfWork.as_system()``.
2. The blocks are a closed door. ``db.session.system_entity_scope`` is the one block that widens
   a transaction's entity scope — the approvals kernel's and, through ``every_entity_scope``, the
   close gates' as well as the computation's and, since dev-guide rev 1.195, the Home's three
   figure panels and, since rev 1.227, the explainer of a report cell (DG-KRN-DB-05; the
   supervisor's rulings of 2026-10-01) and, since rev 1.218, the window rows a command holds
   before it takes a ledger chain head and the period pin of an appender that computes nothing
   (``period_ends.hold_windows``, ``period_ends.refuse_appends_a_lock_met``; finding F4, ruling
   R-122 (j)) and, since rev 1.273, the flags and the amount ``activation.submit_activation``
   states of its contract before it hands them to ``approvals.submit`` (item ACT-FLAGS-1; ruling
   R-64 (1)) and, since rev 1.276, the two digests of what a close run read (item
   CLO-RATE-AFTER-RUN-1) and, since rev 1.295 (item READ-SCOPE-BY-PERMISSION-1: a guarded
   transaction runs under the scope of its route's own permission), the statements of the
   approvals kernel on a request's own row — its insert and read-back, its lock through a
   subject, its void — the basis and the content a modification's and an estimate version's
   submission re-derive of their group, the Home's count of the requests waiting for the
   caller, and (item PREVIEW-INLINE-SCOPE-1) the stored schedule and the postings of its own
   contract that a dry run summarised in its caller's transaction states — and ``system_user``
   the one that re-issues its user,
   for ``as_system`` alone. Every call site of the four is listed here once, by function with
   its reason, and so is every construction of a SYSTEM principal (``system_principal``); a new
   one fails until it is listed.
3. No module reaches past the door: the private readers of ``bundles`` and the private writers
   ``computation._persist``, ``compute_job._compute`` and ``compute_job._refused`` are called
   from their own modules only. And one reader is as wide as its caller and no wider: the window
   read ``period_ends.window_held`` (dev-guide rev 1.245) is named from ``computation`` alone —
   by attribute or by import — so that a second caller, such as an appender that computes
   nothing (supervisor ruling R-122 (j)), fails here until its scope is decided. The appender's
   check as built (item PIN-WINDOW-APPENDER-1) does not name it: the two functions of (2) open
   the tenant's scope themselves and read the rows through the module's private
   ``_window_rows_held``.
4. SYSTEM unlocks nothing. Nothing in the call tree of the computation reads the principal's
   permissions, roles or entity scope, branches on its kind, or calls an authorisation helper.
   The reads that copy the actor into an audit event are listed with their reason. The window
   read of a computation, ``period_ends._window_rows_held`` (item CLO-GATE-RUN-1), is not among
   them since rev 1.245: it reads under the computation's scope and hands no context to any
   block, and the computation's call tree no longer reaches ``every_entity_scope``.

The defect it guards against: WLD-K-04 (contracted by AVM-UK, one obligation performed by AVM-US)
was QUARANTINED on CV-12 when a Revenue Accountant of AVM-UK recorded an invoice, because bundle
assembly read ``legal_entity`` under the caller's entity scope; a combination group of two
contracting entities computed, for a caller of one of them, as if the other member did not exist.
"""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from typing import Final

from support.architecture import Finding, callee, iter_files, module_name, read, report

RULE: Final = "DG-ARC-16"
PY: Final = frozenset({".py"})
PACKAGE: Final = "erev_api"
BUNDLES: Final = "backend/erev_api/domain/contracts/bundles.py"
COMPUTATION: Final = "backend/erev_api/domain/contracts/computation.py"
COMPUTE_JOB: Final = "backend/erev_api/domain/contracts/compute_job.py"
SESSION: Final = "backend/erev_api/db/session.py"
UOW: Final = "backend/erev_api/uow.py"
APPROVALS: Final = "backend/erev_api/approvals/engine.py"
SYSTEM_SCOPE: Final = "system_entity_scope"
EVERY_SCOPE: Final = "every_entity_scope"
SYSTEM_USER: Final = "system_user"
AS_SYSTEM: Final = "as_system"
SYSTEM_PRINCIPAL: Final = "system_principal"
# (file, function) → the manager its body runs inside.
SCOPED: Final = {
    (BUNDLES, "build"): SYSTEM_SCOPE,
    (BUNDLES, "index"): SYSTEM_SCOPE,
    (COMPUTATION, "persist"): AS_SYSTEM,
    (COMPUTATION, "recompute"): AS_SYSTEM,
    (COMPUTE_JOB, "compute_group"): AS_SYSTEM,
}
# The approvals kernel reads what a SUBJECT states and runs its hooks under the tenant's SYSTEM
# scope, so that routing, the hash a decider recomputes and what a decision puts in force do not
# depend on who submits or decides (supervisor ruling R-64 (1); DG-KRN-APR-01, -02).
SUBJECT: Final = "what the subject of a request states, whoever asks (R-64 (1))"
HOOKS: Final = "an approval hook recomputes, reverses and posts for every entity (R-64 (1))"
# 04 §16.10 rev 1.319: once the kernel's own question has admitted the caller — or a subject's
# command has authorised it for the subject — the request's row is found, locked, closed and
# read back whatever the scope of the caller's route (the supervisor's ruling of 2026-10-03).
REQUEST: Final = "a request's own row, for a caller the kernel's question admitted"
# 04 API-S-ImpactSummary rev 1.319 (item PREVIEW-INLINE-SCOPE-1; R-64 (1)): a schedule line and a
# subledger line are rows of the entity that PERFORMS, and a dry run summarised in its caller's
# transaction read them under the caller's scope — the preview a request stores, and the amount
# it routes on, were less for a preparer of the contracting entity alone.
STATED: Final = "what a request states of its contract, as a preview job reads it (R-64 (1))"
# The door: who may call each block — (file, function) → why.
DOOR: Final = {
    AS_SYSTEM: {
        (COMPUTATION, "persist"): "the outputs of a computation are written for every entity",
        (COMPUTATION, "recompute"): "a decision command computes: bundle, engine, persist",
        (COMPUTE_JOB, "compute_group"): "unit of work B and the job compute; refusals stored",
    },
    SYSTEM_USER: {
        (UOW, "UnitOfWork.as_system"): "the computation's statements are attributed to SYSTEM",
    },
    EVERY_SCOPE: {
        (
            "backend/erev_api/domain/close/gates.py",
            "evaluate_gates",
        ): "a close gate counts rows of every entity (R-42 (d))",
        (
            "backend/erev_api/domain/reports/dashboard.py",
            "home",
        ): "the Home's three figure panels, read as the reports' jobs read them, and the count "
        "of the requests waiting for the caller, as the inbox counts them: sums, no row",
        (
            "backend/erev_api/domain/reports/framework.py",
            "explain_cell",
        ): "a report cell, explained as the run's job read it: named within reach, summed beyond",
        (
            "backend/erev_api/domain/reference/commands.py",
            "_sync_calendar_states",
        ): "a fiscal year's period states are written for every entity on the calendar: a count",
    },
    SYSTEM_SCOPE: {
        (SESSION, "every_entity_scope"): "the same block for a caller that holds its context",
        (APPROVALS, "route_submission"): SUBJECT,
        (APPROVALS, "submit"): SUBJECT,
        (APPROVALS, "preparer_scope"): SUBJECT,
        (APPROVALS, "contract_scope"): SUBJECT,
        (APPROVALS, "current_entities"): SUBJECT,
        (APPROVALS, "current_content_sha256"): SUBJECT,
        (APPROVALS, "_excluded_deciders"): SUBJECT,
        (APPROVALS, "_refused_deciders"): SUBJECT,
        (APPROVALS, "_apply_decision"): HOOKS,
        (APPROVALS, "_void"): HOOKS,
        (APPROVALS, "withdraw"): REQUEST,
        (APPROVALS, "void_if_stale"): REQUEST,
        (APPROVALS, "void_subject"): REQUEST,
        (
            "backend/erev_api/domain/contracts/modifications.py",
            "_stored_preview",
        ): "the basis of a stored preview, re-derived as the job that retained it read it",
        (
            "backend/erev_api/domain/contracts/modifications.py",
            "submit",
        ): "the content a modification's row keeps the hash of, whoever submits (R-64 (1))",
        (
            "backend/erev_api/domain/contracts/estimates.py",
            "submit_version",
        ): "the content an estimate version's row keeps the hash of, whoever submits (R-64 (1))",
        (UOW, "UnitOfWork.as_system"): "the computation's own transaction settings",
        (BUNDLES, "build"): "a bundle holds every member, entity, period state and posted line",
        (BUNDLES, "index"): "the rows behind the bundle's keys, read as the bundle was",
        (
            "backend/erev_api/domain/contracts/queries.py",
            "_entity_refs",
        ): "id, code and name of an obligation's performing entity (R-85 (d))",
        (
            "backend/erev_api/domain/contracts/commands.py",
            "_validate",
        ): "the performing entity a booked line names by code (R-95)",
        (
            "backend/erev_api/domain/imports/commit.py",
            "_answering_approvers",
        ): "who answered for each approval an import commit performs (R-98 (9), R-109)",
        (
            "backend/erev_api/domain/close/queries.py",
            "with_close",
        ): "the blocker counts of a period are the same for every reader (R-42 (d), R-121 (i))",
        (
            "backend/erev_api/domain/platform/setup.py",
            "open_period_exists",
        ): "the open period of BR-PLT-02 is the tenant's, whoever's command evaluates setup",
        # 04 §16.7 rev 1.245 (register index 182; the supervisor's rulings of 2026-10-02).
        (
            "backend/erev_api/domain/journals/queries.py",
            "counterparties",
        ): "id, code and name of a journal line's intercompany counterparty (R-85 (d))",
        (
            "backend/erev_api/domain/journals/export.py",
            "chunk_of",
        ): "a batch's lines and their references: the batch as it leaves, for job and download",
        (
            "backend/erev_api/domain/contracts/period_ends.py",
            "hold_windows",
        ): "the window rows a transaction shares with a lock decision, whoever asks (F4)",
        (
            "backend/erev_api/domain/contracts/period_ends.py",
            "refuse_appends_a_lock_met",
        ): "the period pin of an appender that computes nothing, whoever asks (R-122 (j))",
        (
            "backend/erev_api/domain/close/run_inputs.py",
            "read",
        ): "what a close run read is the same for the step that records it and for the gate",
        (
            "backend/erev_api/domain/ssp/resolution.py",
            "resolve",
        ): "the entity each SSP book names, read as a bundle reads it (SSP-ENTITY-SCOPE-1)",
        (
            "backend/erev_api/domain/platform/users.py",
            "_void_stale_role_requests",
        ): "the role requests a removed membership left pending, whoever invites (R-64 (1))",
        (
            "backend/erev_api/domain/contracts/activation.py",
            "submit_activation",
        ): "the flags and amount an activation's request states, whoever submits (R-64 (1))",
        # Item PREVIEW-INLINE-SCOPE-1 (dev-guide rev 1.295; found by the census of index 301): what
        # a request states of its contract's stored schedule and postings, whoever submits.
        (
            "backend/erev_api/domain/contracts/events.py",
            "impact_summary",
        ): STATED + ": the revenue its contract's stored schedule holds, by period",
        (
            "backend/erev_api/domain/contracts/void.py",
            "request_void",
        ): STATED + ": the posted lines of the contract a void reverses",
        (
            "backend/erev_api/domain/journals/adjustments.py",
            "_measure",
        ): STATED + ": the stored revenue an adjustment's amount is measured against",
        (
            "backend/erev_api/domain/policies/lifecycle.py",
            "has_legal_entity",
        ): "whether the workspace has a legal entity yet is the tenant's fact (PRD ERR-75): no row",
    },
}
# Every construction of a SYSTEM principal — (file, function) → why. A unit of work built on one
# has no permissions; where it shares a decider's session, the session keeps the decider's scope.
JOB: Final = "a job, a sweep or a scheduler tick: its own transaction, no person behind it"
HOOK: Final = "an approval's effect, stamped SYSTEM inside the decider's transaction"
SYSTEM_BUILDERS: Final = {
    (UOW, "UnitOfWork.as_system"): "the computation of a group (this rule)",
    ("backend/erev_api/jobs/registry.py", "run_job"): JOB,
    ("backend/erev_api/jobs/registry.py", "_fail_queued"): JOB,
    ("backend/erev_api/jobs/registry.py", "fail_attempt"): JOB,
    ("backend/erev_api/jobs/registry.py", "retry_stranded"): JOB,
    # 05 JOB-07 rev 1.165: the open JOB_FAILED item of a kind and record is settled after the
    # job that ran to its end, in a unit of work of its own.
    ("backend/erev_api/jobs/registry.py", "_settle_failed_item"): JOB,
    ("backend/erev_api/controls/recovery.py", "record_restore_applied"): JOB,
    ("backend/erev_api/domain/close/data_quality_sweep.py", "run"): JOB,
    ("backend/erev_api/domain/integrations/sweeps.py", "run"): JOB,
    ("backend/erev_api/domain/reference/period_auto_open.py", "run"): JOB,
    ("backend/erev_api/domain/platform/support_grants.py", "expire_due"): JOB,
    # 05 SCH-16 rev 1.171: the sweep that completes a decided shred, one unit of work per file.
    ("backend/erev_api/domain/platform/shred_completion.py", "run"): JOB,
    ("backend/erev_api/domain/platform/sandboxes.py", "load_sandbox"): JOB,
    ("backend/erev_api/domain/demo/seed.py", "_record_complete"): JOB,
    ("backend/erev_api/domain/imports/diff.py", "import_principal"): (
        "an import job on behalf of its uploader, narrowed to the uploader's scope"
    ),
    ("backend/erev_api/domain/integrations/sync.py", "sync_principal"): (
        "an adapter sync job on behalf of who started it"
    ),
    ("backend/erev_api/domain/migration/capture.py", "migration_principal"): (
        "a migration capture job on behalf of who started it"
    ),
    ("backend/erev_api/api/v1/integrations.py", "receive_webhook"): (
        "an inbound webhook: authenticated by its signature, no person behind it"
    ),
    ("backend/erev_api/domain/close/freeze.py", "system_reads"): (
        "the read-only reader of a lock's coverage guard"
    ),
    ("backend/erev_api/domain/close/freeze.py", "system_unit"): (
        "the read-only unit of a lock's dataset producers, in a transaction of its own (R-94 (a))"
    ),
    ("backend/erev_api/api/v1/periods.py", "_materialised"): (
        "the checklist of a period brought up to date for its reader, stamped SYSTEM (R-32)"
    ),
    ("backend/erev_api/api/v1/periods.py", "_monitored"): (
        "the data-quality monitors before a period command, in a unit of work of their own"
    ),
    ("backend/erev_api/jobs/registry.py", "_defer_unless_pending"): JOB,
    ("backend/erev_api/domain/platform/sandboxes.py", "archive_failed_load"): JOB,
    ("backend/erev_api/domain/platform/sandbox_reset.py", "create_empty_sandbox"): (
        "the first records of a new sandbox, as that tenant's SYSTEM principal"
    ),
    ("backend/erev_api/domain/platform/sandbox_reset.py", "_source_context"): (
        "a sandbox load reads its snapshot as the source tenant's SYSTEM principal (05 SBX-04)"
    ),
    ("backend/erev_api/domain/platform/sandbox_reset.py", "reset_sandbox"): JOB,
    ("backend/erev_api/approvals/subjects.py", "_apply_event_submission"): HOOK,
    ("backend/erev_api/domain/contracts/activation.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/combination.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/commands.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/estimates.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/holds.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/modifications.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/contracts/void.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/journals/adjustments.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/policies/overrides.py", "_system_unit"): HOOK,
    ("backend/erev_api/domain/platform/evidence_shred.py", "_approved"): HOOK,
}
# A private writer or reader → the one module that may name it.
PRIVATE: Final = {
    ("computation", "_persist"): COMPUTATION,
    ("compute_job", "_compute"): COMPUTE_JOB,
    ("compute_job", "_refused"): COMPUTE_JOB,
}
# A reader that widens nothing itself → the modules that may name it. The window read holds the
# state rows of every entity of a bundle only because the computation that asks runs under the
# tenant's scope (``computation._persist`` requires it); under a caller's scope it would hold the
# rows that caller may see and no more (supervisor ruling R-42 (d); dev-guide rev 1.245).
CALLER_WIDE: Final = {
    ("period_ends", "window_held"): frozenset({COMPUTATION}),
}
# The call tree of the computation starts here (module, function).
STARTS: Final = (
    ("erev_api.domain.contracts.bundles", "build"),
    ("erev_api.domain.contracts.bundles", "index"),
    ("erev_api.domain.contracts.computation", "persist"),
    ("erev_api.domain.contracts.computation", "recompute"),
    ("erev_api.domain.contracts.compute_job", "_refused"),
    ("erev_api.domain.contracts.compute_job", "compute_group"),
)
# What a computation must never read of its principal: what it may do and where.
AUTHORITY: Final = frozenset(
    {
        "permissions",
        "permission_scopes",
        "entity_scope",
        "roles",
        "db_context",
        "membership_id",
        "auth_method",
        "mfa_verified_at",
        "support_grant_id",
        "session_id",
    }
)
AUTHORISATION_MODULES: Final = ("erev_api.auth.dependencies", "erev_api.auth.permissions")
SCOPE_SETTINGS: Final = ("app.entity_scope", "app.user_id", "entity_in_scope")
# Reads of the principal inside the tree that decide nothing — (module, function) → why.
RECORDS_THE_ACTOR: Final = {
    ("erev_api.audit.writer", "actor_of"): "copies the principal into the audit event's actor",
    ("erev_api.audit.writer", "principal_actor"): "the actor fields of a principal (T-PLT-19)",
    ("erev_api.audit.writer", "build_event"): "writes the actor's fields on the audit event",
    ("erev_api.uow", "UnitOfWork.as_system"): "names whom SYSTEM acts on behalf of",
    ("erev_api.db.session", "system_entity_scope"): "the block itself re-issues the scope",
    ("erev_api.db.session", "system_user"): "the block itself re-issues the user",
    ("erev_api.db.session", "require_tenant_scope"): "the writer's guard reads the setting",
}
# Functions the walk must reach, or it has stopped following the code (module, function).
ANCHORS: Final = (
    ("erev_api.domain.journals.subledger", "post"),
    ("erev_api.domain.imports.exceptions", "raise_exception_item"),
    ("erev_api.audit.writer", "actor_of"),
    ("erev_api.controls.evidence", "record_execution"),
    ("erev_api.numbering", "next_numbers"),
    ("erev_api.db.session", "system_entity_scope"),
)
MINIMUM_REACHED: Final = 150  # 201 functions in 29 modules when the rule was written


# --- 1 to 3: the managers and the door ------------------------------------------------------------


def _enclosing(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    """Every function of a module with its qualified name (``Class.method`` for a method)."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}.{item.name}", item


def _statements(function: ast.AST) -> list[ast.stmt]:
    """The body without its docstring."""
    body = list(getattr(function, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body


def _enters(statement: ast.stmt, manager: str) -> bool:
    return isinstance(statement, ast.With) and any(
        isinstance(item.context_expr, ast.Call) and callee(item.context_expr) == manager
        for item in statement.items
    )


def check_scoped(path: str, source: str) -> list[Finding]:
    """A computation function whose work does not run inside its manager. Statements that come
    before the ``with`` may only bind names from values in hand (no call reaches the database
    before the scope is entered)."""
    functions = dict(_enclosing(ast.parse(source, filename=path)))
    findings: list[Finding] = []
    for (file, name), manager in SCOPED.items():
        if file != path:
            continue
        function = functions.get(name)
        if function is None:
            findings.append(Finding(path, 1, RULE, f"{name} is gone; DG-ARC-16 names it"))
            continue
        body = _statements(function)
        entered = [index for index, statement in enumerate(body) if _enters(statement, manager)]
        if not entered or entered[0] != len(body) - 1:
            message = f"{name} does not end in one `with {manager}(...)` block that holds its work"
            findings.append(Finding(path, getattr(function, "lineno", 1), RULE, message))
            continue
        for statement in body[: entered[0]]:
            if not isinstance(statement, ast.Assign) or any(
                isinstance(node, ast.Call) and callee(node) != "default_engine"
                for node in ast.walk(statement)
            ):
                message = f"{name} does work before it enters `{manager}`"
                findings.append(Finding(path, statement.lineno, RULE, message))
    return findings


def check_door(path: str, source: str) -> list[Finding]:
    """A call of ``as_system``, of a block that changes a transaction's scope or user, or of
    ``system_principal`` from a function that the door does not list."""
    listed = DOOR
    findings: list[Finding] = []
    tree = ast.parse(source, filename=path)
    inside: dict[int, str] = {}
    for name, function in _enclosing(tree):
        for node in ast.walk(function):
            inside[id(node)] = name
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = callee(node)
        where = (path, inside.get(id(node), "<module>"))
        if name in listed and where not in listed[name]:
            message = (
                f"{where[1]} calls {name}: a transaction's scope and user change at the listed "
                "call sites only; list this one with its reason if it is one"
            )
            findings.append(Finding(path, node.lineno, RULE, message))
        if name == SYSTEM_PRINCIPAL and where not in SYSTEM_BUILDERS:
            message = (
                f"{where[1]} builds a SYSTEM principal: list it in SYSTEM_BUILDERS with its reason"
            )
            findings.append(Finding(path, node.lineno, RULE, message))
    return findings


def _caller_wide(path: str, owner: str, name: str, line: int) -> list[Finding]:
    """The finding for ``owner.name`` named in ``path`` when it is a reader as wide as its caller
    (``CALLER_WIDE``) and ``path`` is not one of its listed modules."""
    allowed = CALLER_WIDE.get((owner, name))
    if allowed is None or path in allowed:
        return []
    message = (
        f"names {owner}.{name} outside a computation: it reads under its caller's scope — decide "
        "that scope here, then list this module beside the computation's"
    )
    return [Finding(path, line, RULE, message)]


def check_private(path: str, source: str) -> list[Finding]:
    """A reach past the door: a private function of ``bundles`` or a private writer of the
    computation named from another module; and a reader as wide as its caller named — by
    attribute or by import — outside the modules listed for it."""
    findings: list[Finding] = []
    for node in ast.walk(ast.parse(source, filename=path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            owner = node.module.rsplit(".", 1)[-1]
            for alias in node.names:
                findings.extend(_caller_wide(path, owner, alias.name, node.lineno))
            continue
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        owner, name = node.value.id, node.attr
        findings.extend(_caller_wide(path, owner, name, node.lineno))
        if (
            owner == "bundles"
            and name.startswith("_")
            and not name.startswith("__")
            and path != BUNDLES
        ):
            message = f"reaches bundles.{name}; a bundle is assembled by bundles.build"
            findings.append(Finding(path, node.lineno, RULE, message))
        home = PRIVATE.get((owner, name))
        if home is not None and path != home:
            message = f"reaches {owner}.{name} past its wrapper; it writes as SYSTEM or not at all"
            findings.append(Finding(path, node.lineno, RULE, message))
    return findings


def unlisted(found: Iterable[tuple[str, str]], listed: Iterable[tuple[str, str]]) -> list[str]:
    """Listed call sites that no longer exist: the list states what is there, nothing more."""
    return sorted(f"{path}::{name}" for path, name in set(listed) - set(found))


def names(source: str, owner: str, name: str) -> bool:
    """Whether a module names ``owner.name`` — the attribute, or the name imported from a module
    called ``owner`` — as ``check_private`` reads it."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.rsplit(".", 1)[-1] == owner and any(a.name == name for a in node.names):
                return True
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) == (owner, name):
                return True
    return False


def _call_sites(
    sources: Mapping[str, str], names: frozenset[str]
) -> dict[str, set[tuple[str, str]]]:
    found: dict[str, set[tuple[str, str]]] = {name: set() for name in names}
    for path, source in sources.items():
        tree = ast.parse(source, filename=path)
        for function_name, function in _enclosing(tree):
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and callee(node) in names:
                    found[str(callee(node))].add((path, function_name))
    return found


# --- 4: the call tree -----------------------------------------------------------------------------


class Tree:
    """The functions of the package, by module, with what each module imports from the package."""

    def __init__(self, sources: Mapping[str, str]) -> None:
        self.paths: dict[str, str] = {}
        self.functions: dict[str, dict[str, ast.AST]] = {}
        self.aliases: dict[str, dict[str, tuple[str, str | None]]] = {}
        trees = {module_name(path): (path, ast.parse(source)) for path, source in sources.items()}
        for module, (path, tree) in trees.items():
            self.paths[module] = path
            self.functions[module] = dict(_enclosing(tree))
        for module, (_, tree) in trees.items():
            found: dict[str, tuple[str, str | None]] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    for alias in node.names:
                        target = f"{node.module}.{alias.name}"
                        found[alias.asname or alias.name] = (
                            (target, None) if target in trees else (node.module, alias.name)
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.asname:
                            found[alias.asname] = (alias.name, None)
            self.aliases[module] = found

    def resolve(self, module: str, call: ast.Call) -> tuple[str, str] | None:
        """The function a call names, when the source says which: a plain name defined or imported
        in the module, ``alias.function`` on an imported module, ``uow.method`` on the unit of
        work."""
        func = call.func
        aliases = self.aliases[module]
        if isinstance(func, ast.Name):
            if func.id in self.functions[module]:
                return module, func.id
            target, name = aliases.get(func.id, ("", None))
            if name is not None and name in self.functions.get(target, {}):
                return target, name
            return None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            target, name = aliases.get(func.value.id, ("", None))
            if target and name is None and func.attr in self.functions.get(target, {}):
                return target, func.attr
            method = f"UnitOfWork.{func.attr}"
            if func.value.id in ("uow", "self") and method in self.functions.get(
                "erev_api.uow", {}
            ):
                return "erev_api.uow", method
        return None

    def reached(self, starts: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        queue = deque(starts)
        while queue:
            key = queue.popleft()
            node = self.functions.get(key[0], {}).get(key[1])
            if key in seen or node is None:
                continue
            seen.add(key)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    found = self.resolve(key[0], sub)
                    if found is not None:
                        queue.append(found)
        return seen


def _names_a_principal(expression: ast.AST) -> bool:
    text = ast.unparse(expression)
    return "principal" in text or text in ("actor", "caller", "ctx", "uow.ctx", "self.ctx")


def check_authority(tree: Tree, starts: Iterable[tuple[str, str]]) -> list[Finding]:
    """A function of the computation's call tree that reads what its principal may do: a
    permission, a role, an entity scope, the kind as anything but a stamp, an authorisation
    helper, or the scope settings in SQL."""
    findings: list[Finding] = []
    for module, name in sorted(tree.reached(starts)):
        if (module, name) in RECORDS_THE_ACTOR:
            continue
        path = tree.paths[module]
        function = tree.functions[module][name]
        stamps = {
            id(node.value)
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and node.attr == "value"
        }
        for node in ast.walk(function):
            message = None
            if isinstance(node, ast.Attribute) and _names_a_principal(node.value):
                if node.attr in AUTHORITY:
                    message = f"{name} reads the principal's {node.attr}"
                elif node.attr == "kind" and id(node) not in stamps:
                    message = f"{name} branches on the principal's kind"
            elif isinstance(node, ast.Call):
                found = tree.resolve(module, node)
                if found is not None and found[0] in AUTHORISATION_MODULES:
                    message = f"{name} calls the authorisation helper {found[1]}"
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(setting in node.value for setting in SCOPE_SETTINGS):
                    message = f"{name} names a scope setting in SQL"
            if message is not None:
                findings.append(
                    Finding(
                        path,
                        getattr(node, "lineno", 1),
                        RULE,
                        f"{message}: a computation is the same for every principal",
                    )
                )
    return findings


# --- the repository -------------------------------------------------------------------------------


def _sources() -> dict[str, str]:
    return {path: read(path) for path in iter_files("backend/erev_api", suffixes=PY)}


def test_dg_arc_16_the_computation_chooses_its_own_scope() -> None:
    sources = _sources()
    findings = [
        finding
        for path, source in sources.items()
        for check in (check_scoped, check_door, check_private)
        for finding in check(path, source)
    ]
    assert findings == [], report(findings)
    # the lists state what is there: a listed call site that is gone is removed from its list
    sites = _call_sites(sources, frozenset({*DOOR, SYSTEM_PRINCIPAL}))
    for name, callers in DOOR.items():
        assert unlisted(sites[name], callers) == [], name
    assert unlisted(sites[SYSTEM_PRINCIPAL], SYSTEM_BUILDERS) == []
    # … and a reader as wide as its caller is named by exactly the modules listed for it
    for (owner, name), modules in CALLER_WIDE.items():
        naming = {path for path, source in sources.items() if names(source, owner, name)}
        assert naming == set(modules), f"{owner}.{name}"


def test_dg_arc_16_system_unlocks_nothing_in_the_call_tree_of_a_computation() -> None:
    tree = Tree(_sources())
    reached = tree.reached(STARTS)
    assert len(reached) >= MINIMUM_REACHED, len(reached)
    assert [anchor for anchor in ANCHORS if anchor not in reached] == []
    findings = check_authority(tree, STARTS)
    assert findings == [], report(findings)
    # the listed readers are in the tree and do read the principal
    assert [key for key in RECORDS_THE_ACTOR if key not in reached] == []


# --- the checks find what they are for ------------------------------------------------------------


def test_a_computation_function_outside_its_manager_is_found() -> None:
    unscoped = "def build(session, group_id):\n    return _assemble(session, group_id)\n"
    assert [finding.message for finding in check_scoped(BUNDLES, unscoped)] == [
        "build does not end in one `with system_entity_scope(...)` block that holds its work",
        "index is gone; DG-ARC-16 names it",
    ]
    early = (
        "def persist(uow, bundle, output):\n"
        "    found = bundles.index(uow.session, bundle)\n"
        "    with uow.as_system():\n"
        "        return _persist(uow, bundle, output, found)\n"
        "def recompute(uow, group_id):\n"
        "    with uow.as_system():\n"
        "        return 1\n"
    )
    assert [(finding.line, finding.message) for finding in check_scoped(COMPUTATION, early)] == [
        (2, "persist does work before it enters `as_system`")
    ]
    trailing = (
        "def compute_group(uow, group_id):\n"
        "    with uow.as_system():\n"
        "        outcome = _compute(uow, group_id)\n"
        "    return outcome\n"
    )
    assert [finding.message for finding in check_scoped(COMPUTE_JOB, trailing)] == [
        "compute_group does not end in one `with as_system(...)` block that holds its work"
    ]
    good = (
        "def compute_group(uow, group_id, engine=None):\n"
        '    """Docstring."""\n'
        "    with uow.as_system():\n"
        "        return _compute(uow, group_id)\n"
    )
    assert check_scoped(COMPUTE_JOB, good) == []


def test_a_caller_outside_the_door_is_found() -> None:
    hook = "def approve(uow):\n    with uow.as_system():\n        write(uow)\n"
    assert [finding.line for finding in check_door("backend/erev_api/approvals/x.py", hook)] == [2]
    wide = (
        "def rows(session):\n    with system_entity_scope(session):\n        return read(session)\n"
    )
    assert len(check_door("backend/erev_api/domain/reports/x.py", wide)) == 1
    for block in ("every_entity_scope(session, ctx)", "system_user(session)"):
        other = wide.replace("system_entity_scope(session)", block)
        assert len(check_door("backend/erev_api/domain/reports/x.py", other)) == 1, block
    # the listed function of a listed file passes; another function of the same file does not
    assert check_door(BUNDLES, wide.replace("def rows", "def build")) == []
    assert len(check_door(BUNDLES, wide)) == 1
    system = "def sweep(tenant_id):\n    return system_principal(tenant_id)\n"
    assert len(check_door("backend/erev_api/domain/close/new_job.py", system)) == 1
    assert check_door("backend/erev_api/jobs/registry.py", system.replace("sweep", "run_job")) == []
    reach = "def dry_run(session, group_id):\n    return bundles._members(session, group_id)\n"
    assert len(check_private("backend/erev_api/domain/contracts/events.py", reach)) == 1
    assert check_private(BUNDLES, reach) == []
    past = "def capture(uow, b, o):\n    return computation._persist(uow, b, o)\n"
    assert len(check_private("backend/erev_api/domain/migration/capture.py", past)) == 1
    assert unlisted({("a.py", "f")}, {("a.py", "f"), ("b.py", "g")}) == ["b.py::g"]


def test_a_second_caller_of_the_window_read_is_found() -> None:
    """DG-ARC-16 (3), dev-guide rev 1.245: ``period_ends.window_held`` is as wide as its caller.
    Named — by attribute or by import — in a module other than ``computation``, it is a finding
    that says what to decide; in ``computation``, and for the other names of its module, none."""
    periods = "backend/erev_api/domain/contracts/period_ends.py"
    appender = (
        "def commit(uow, bundle, group_id):\n"
        "    return period_ends.window_held(uow, bundle, group_id)\n"
    )
    (found,) = check_private("backend/erev_api/domain/imports/commit.py", appender)
    assert (found.line, found.message) == (
        2,
        "names period_ends.window_held outside a computation: it reads under its caller's scope "
        "— decide that scope here, then list this module beside the computation's",
    )
    assert check_private(COMPUTATION, appender) == []
    imported = "from erev_api.domain.contracts.period_ends import Held, window_held\n"
    events = "backend/erev_api/domain/contracts/events.py"
    assert [finding.line for finding in check_private(events, imported)] == [1]
    assert check_private(COMPUTATION, imported) == []
    other = "from erev_api.domain.contracts.period_ends import PASSES, engine_pass\n"
    assert check_private("backend/erev_api/domain/close/period_end.py", other) == []
    defined = "def window_held(uow, bundle, group_id):\n    return _window_rows_held(uow, [])\n"
    assert check_private(periods, defined) == []
    assert names(appender, "period_ends", "window_held")
    assert names(imported, "period_ends", "window_held")
    assert not names(other, "period_ends", "window_held") and not names(defined, "period_ends", "x")
    assert CALLER_WIDE == {("period_ends", "window_held"): frozenset({COMPUTATION})}


def test_a_read_of_the_principals_authority_in_the_call_tree_is_found() -> None:
    def tree_of(helper: str) -> Tree:
        return Tree(
            {
                "backend/erev_api/domain/contracts/compute_job.py": (
                    "from erev_api.domain.contracts import helper\n"
                    "def compute_group(uow, group_id):\n"
                    "    with uow.as_system():\n"
                    "        return helper.work(uow, group_id)\n"
                ),
                "backend/erev_api/domain/contracts/helper.py": helper,
                "backend/erev_api/auth/dependencies.py": (
                    "def require_for_entity(ctx, p, e):\n    pass\n"
                ),
            }
        )

    starts = [("erev_api.domain.contracts.compute_job", "compute_group")]
    stamp = (
        "def work(uow, group_id):\n"
        "    return {'by': uow.principal.id, 'kind': uow.principal.kind.value}\n"
    )
    assert check_authority(tree_of(stamp), starts) == []
    for helper, message in (
        (
            "def work(uow, group_id):\n    return 'x' in uow.principal.permissions\n",
            "work reads the principal's permissions",
        ),
        (
            "def work(uow, group_id):\n    return uow.principal.entity_scope == '*'\n",
            "work reads the principal's entity_scope",
        ),
        (
            "def work(uow, group_id):\n    return list(uow.principal.roles)\n",
            "work reads the principal's roles",
        ),
        (
            "def work(uow, group_id):\n    return uow.principal.kind is SYSTEM\n",
            "work branches on the principal's kind",
        ),
        (
            "from erev_api.auth.dependencies import require_for_entity\n"
            "def work(uow, group_id):\n    require_for_entity(uow.ctx, 'p', group_id)\n",
            "work calls the authorisation helper require_for_entity",
        ),
        (
            "def work(uow, group_id):\n"
            "    sql = \"SELECT current_setting('app.entity_scope')\"\n"
            "    return uow.session.execute(text(sql))\n",
            "work names a scope setting in SQL",
        ),
    ):
        found = check_authority(tree_of(helper), starts)
        assert [finding.message.split(":")[0] for finding in found] == [message], helper
    # a function the computation does not reach is not its concern
    unreached = stamp + "def other(uow):\n    return uow.principal.permissions\n"
    assert check_authority(tree_of(unreached), starts) == []
