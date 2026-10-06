"""Build-spec header XR-08; 05 §10 SBX-08 rev 1.116; BUILD_SPEC SNP-4 (03 REQ-PLT-022; CTL-043):
every command a sandbox may not run calls the production guard exactly once.

``domain.platform.guards.ensure_production`` is the one place that refuses a sandbox and audits the
attempt. ``RESTRICTED`` lists the handler of every restricted command with the guard function it
calls — the guard itself, or one of the three integration wrappers, each of which calls the
guard once. The list is closed in both directions: a listed handler that stops calling its guard
fails, and so does a function that calls a guard without being listed, so a new restricted command
is added here with the route that serves it.

XR-08 names "export, posting and conversion". Export and posting are one command here, ``POST
/journal-runs/{id}/export``, with the retry of a failed batch, which exports again (``POST
/journal-batches/{id}/retry``, BUILD_SPEC CLO-14), and its hand-over, which exports it as a file
(``POST /journal-batches/{id}/hand-over``, 05 SBX-08 rev 1.98): the adapters post what they
export. Conversion of a sandbox into a production tenant has no command at all (SBX-08; ``PATCH
/tenant`` refuses ``kind`` in every tenant, 409 ``tenant-kind-immutable``), which
``test_no_command_converts_a_workspace`` pins.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import erev_api

ROOT: Final = Path(erev_api.__file__).parent
GUARD: Final = "ensure_production"
GUARD_MODULE: Final = "domain/platform/guards.py"
# The integration refusals keep their own messages and audit details; each calls the guard once.
# So does the refusal of a shred of a file a sandbox shares, which asks the file's storage key
# first: what a sandbox stored itself is its own (05 SBX-08 rev 1.164).
WRAPPERS: Final = {
    ("domain/integrations/commands.py", "refuse_inbound_in_sandbox"),
    ("domain/integrations/commands.py", "refuse_activation_in_sandbox"),
    ("domain/integrations/commands.py", "refuse_probe_in_sandbox"),
    ("domain/platform/privacy.py", "refuse_shared_in_sandbox"),
}
# (module, handler) → (the guard function it calls once, the route it serves and how).
RESTRICTED: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("domain/journals/export.py", "export_run"): (
        GUARD,
        "journal_runs_export: api/v1/journal_runs.py calls export.export_run(",
    ),
    ("domain/journals/export.py", "retry_batch"): (
        GUARD,
        "journal_batches_retry: api/v1/journal_runs.py calls export.retry_batch(",
    ),
    # 05 SBX-08 rev 1.98 (item JRN-FAILED-CANCEL-1): the hand-over exports a batch as its file
    ("domain/journals/failed_exits.py", "hand_over_batch"): (
        GUARD,
        "journal_batches_hand_over: api/v1/journal_runs.py calls failed_exits.hand_over_batch(",
    ),
    ("domain/platform/webhook_endpoints.py", "create_endpoint"): (
        GUARD,
        "webhook_endpoints_create: api/v1/webhooks.py calls webhook_endpoints.create_endpoint(",
    ),
    ("domain/platform/webhook_endpoints.py", "update_endpoint"): (
        GUARD,
        "webhook_endpoints_update: api/v1/webhooks.py calls webhook_endpoints.update_endpoint(",
    ),
    ("domain/integrations/commands.py", "create_connection"): (
        "refuse_inbound_in_sandbox",
        "integrations_create: api/v1/integrations.py calls commands.create_connection(",
    ),
    ("domain/integrations/commands.py", "update_connection"): (
        "refuse_activation_in_sandbox",
        "integrations_update: api/v1/integrations.py calls commands.update_connection(",
    ),
    # 05 SBX-08 rev 1.116 (item SBX-PROBE-1): a sandbox reaches no external system, a probe included
    ("domain/integrations/commands.py", "test_connection"): (
        "refuse_probe_in_sandbox",
        "integrations_test: api/v1/integrations.py calls commands.test_connection(",
    ),
    ("domain/integrations/commands.py", "request_sync"): (
        "refuse_inbound_in_sandbox",
        "integrations_sync: api/v1/integrations.py calls commands.request_sync(",
    ),
    ("domain/integrations/commands.py", "receive_webhook"): (
        "refuse_inbound_in_sandbox",
        "webhooks_receive: api/v1/integrations.py calls commands.receive_webhook(",
    ),
    # 05 SBX-08 rev 1.164 (item FILE-SHRED-SCOPE-1): a sandbox destroys nothing it shares — a
    # copy's file rows carry the storage keys of their source — and what it stored is its own
    ("domain/platform/privacy.py", "shred_file"): (
        "refuse_shared_in_sandbox",
        "files_shred: api/v1/files.py calls privacy.shred_file(",
    ),
    ("domain/platform/evidence_shred.py", "request_shred"): (
        "refuse_shared_in_sandbox",
        "files_request_shred: api/v1/files.py calls evidence_shred.request_shred(",
    ),
    ("domain/platform/evidence_shred.py", "_approved"): (
        "refuse_shared_in_sandbox",
        "the approval of an EVIDENCE_SHRED request: domain/platform/evidence_shred.py calls "
        "subjects.SubjectLifecycle(on_approved=_approved",
    ),
    ("domain/integrations/sync.py", "request_record_reprocess"): (
        "refuse_inbound_in_sandbox",
        "the SYNC exception reprocessor: domain/integrations/sync.py calls "
        "exception_queue.REPROCESSORS[ExceptionSource.SYNC] = request_record_reprocess",
    ),
}
GUARD_NAMES: Final = frozenset({GUARD} | {name for _, name in WRAPPERS})
SLUG: Final = "sandbox-restricted"
# module → constructions of the problem outside the guard: 05 SBX-02, only a production tenant is
# the source of a snapshot (no DENIED event; the request and the job each say it).
SOURCE_RULE_REFUSALS: Final = {
    "domain/platform/snapshots.py": 2,
    "domain/platform/snapshot_job.py": 1,
}


def _callee(node: ast.Call) -> str | None:
    """The bare name a call is made through: ``f(…)`` or ``module.f(…)``."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def guard_calls(source: str) -> dict[str, dict[str, int]]:
    """function name → {guard function → number of call sites} for the module-level functions of
    ``source`` that call a guard function at all."""
    found: dict[str, dict[str, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        counts: dict[str, int] = {}
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and (name := _callee(inner)) in GUARD_NAMES:
                counts[str(name)] = counts.get(str(name), 0) + 1
        if counts:
            found[node.name] = counts
    return found


def _all_guard_calls() -> dict[tuple[str, str], dict[str, int]]:
    found: dict[tuple[str, str], dict[str, int]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == GUARD_MODULE or relative.startswith("db/migrations/"):
            continue
        for function, counts in guard_calls(path.read_text(encoding="utf-8")).items():
            found[(relative, function)] = counts
    return found


def test_export_posting_conversion_handlers_guarded() -> None:
    calls = _all_guard_calls()
    expected: dict[tuple[str, str], dict[str, int]] = {
        handler: {callee: 1} for handler, (callee, _) in RESTRICTED.items()
    }
    expected.update({wrapper: {GUARD: 1} for wrapper in WRAPPERS})
    missing = {key: want for key, want in expected.items() if calls.get(key) != want}
    assert not missing, (
        "a restricted command must call its production guard exactly once (XR-08): "
        f"{ {key: calls.get(key) for key in missing} } instead of {missing}"
    )
    unlisted = sorted(set(calls) - set(expected))
    assert not unlisted, f"guard callers that RESTRICTED does not list: {unlisted}"
    # Each listed handler is what its route (or registry) really reaches.
    for (_, function), (_, served_by) in RESTRICTED.items():
        _, _, where = served_by.partition(": ")
        module, _, call = where.partition(" calls ")
        source = (ROOT / module).read_text(encoding="utf-8")
        assert call and call in source, f"{function}: {module} no longer holds {call!r}"


def test_the_guard_refuses_and_audits_in_one_place() -> None:
    """The guard module is the only one that turns a sandbox into a ``DENIED`` event plus a 403:
    it calls ``audit_writer.record_now`` with ``AuditOutcome.DENIED`` and raises the slug, and
    ``record_now`` comes before the ``raise``."""
    source = (ROOT / GUARD_MODULE).read_text(encoding="utf-8")
    tree = ast.parse(source)
    [guard] = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == GUARD
    ]
    recorded = [
        node.lineno
        for node in ast.walk(guard)
        if isinstance(node, ast.Call) and _callee(node) == "record_now"
    ]
    raised = [node.lineno for node in ast.walk(guard) if isinstance(node, ast.Raise)]
    assert len(recorded) == 1 and len(raised) == 1 and recorded[0] < raised[0]
    assert "AuditOutcome.DENIED" in (ast.get_source_segment(source, guard) or "")


def slug_refusals(source: str) -> int:
    """The number of ``Problem("sandbox-restricted", …)`` constructions in ``source``."""
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and _callee(node) == "Problem"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == SLUG
    )


def test_no_handler_refuses_a_sandbox_by_itself() -> None:
    """A command that answers ``sandbox-restricted`` does it through the guard, so that the
    refusal is audited in one way. The only other constructions of the problem are SBX-02's
    source rule — a sandbox is not copied — in the snapshot request, the restore request and the
    export job, which refuse without a ``DENIED`` event by design. A handler that grows a copy of
    the guard (a merge of a lane that predates it) is named here."""
    found = {}
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative == GUARD_MODULE or relative.startswith("db/migrations/"):
            continue
        count = slug_refusals(path.read_text(encoding="utf-8"))
        if count:
            found[relative] = count
    assert found == SOURCE_RULE_REFUSALS, found
    copy = """
def retry(uow):
    if uow.ctx.tenant_kind is TenantKind.SANDBOX:
        audit_writer.record_now(uow.ctx, outcome=AuditOutcome.DENIED)
        raise Problem("sandbox-restricted", DETAIL)
    raise Problem("invalid-transition", DETAIL)
"""
    assert slug_refusals(copy) == 1


def test_no_command_converts_a_workspace() -> None:
    """SBX-08: conversion to production does not exist. No statement of the application assigns
    ``tenant.kind`` on an UPDATE: the two kinds are written only where a tenant row is inserted
    (provisioning, the sandbox load and the empty sandbox), and ``PATCH /tenant`` answers 409
    ``tenant-kind-immutable`` to a request that names ``kind`` before anything else."""
    settings = (ROOT / "domain/platform/tenant_settings.py").read_text(encoding="utf-8")
    refusal = settings.index('raise Problem("tenant-kind-immutable"')
    assert "kind_requested" in settings[:refusal]
    assert refusal < settings.index("update(tenant)"), "the refusal must precede the UPDATE"
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("db/migrations/"):
            continue
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            # update(tenant)….values(kind=…): a keyword ``kind`` on a ``values`` call whose
            # receiver chain starts at ``update(tenant)``.
            if not (isinstance(node, ast.Call) and _callee(node) == "values"):
                continue
            if not any(keyword.arg == "kind" for keyword in node.keywords):
                continue
            chain = ast.get_source_segment(source, node) or ""
            if chain.lstrip().startswith(("update(tenant)", "update(tenant_table)")):
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == [], offenders


def test_the_counter_names_each_defect_shape() -> None:
    """The guard of the guard: a handler that does not call it, one that calls it twice and one
    that calls it through an attribute are each counted as they are."""
    source = """
def unguarded(uow):
    return uow.session

def once(uow):
    guards.ensure_production(uow, action="a", object_type="t", object_id=None)

def twice(uow):
    if uow.flag:
        ensure_production(uow, action="a", object_type="t", object_id=None)
    guards.ensure_production(uow, action="a", object_type="t", object_id=None)

def wrapped(uow):
    refuse_inbound_in_sandbox(uow, action="a", object_type="t", object_id=None, detail={})
"""
    assert guard_calls(source) == {
        "once": {"ensure_production": 1},
        "twice": {"ensure_production": 2},
        "wrapped": {"refuse_inbound_in_sandbox": 1},
    }
