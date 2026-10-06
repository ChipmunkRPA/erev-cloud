"""Every transaction of a job passes the attempt's door (05 JOB-06 rev 1.200; dev-guide
DG-KRN-JOB-04, DG-KRN-JOB-06 rev 1.266; PRD NTF-05 rev 1.191; item JOB-STALL-COMMIT-RACE-1).

An attempt keeps nothing once it has lost its job because the transactions it opens pass one
door: a unit of work takes the job's lock, is refused when the job is no longer the attempt's and
writes its heartbeat at its commit (``jobs.context.JobAttempt.enter``). A handler opens a unit of
work through its context or through ``system_unit_of_work`` with the context's runtime, and both
are that door. What a handler opens any other way - a tenant session, a platform scope, a copy
step - is found here by reading the source: it calls ``enlist`` as its first statement, or it
stands in the list below with what it rests on instead.

The scan reads the functions that are handed a job context or a job runtime, the two ways an
attempt reaches code, and the functions nested in them. The kernel itself (``jobs/``) is the rule
and is not scanned. A function that opens a transaction without being handed either is not seen.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import erev_api
import pytest
from erev_api.auth.principal import system_principal
from erev_api.domain.platform import sandboxes
from erev_api.enums import JobKind
from erev_api.jobs import registry
from erev_api.jobs.context import JobAttempt, JobContext, JobRuntime, unit_lock_key
from erev_api.jobs.sweeper import STRANDED_DETAIL
from erev_api.problems import Problem
from sqlalchemy import text
from support.clock import frozen_clock

# The package as it is imported: the scan reads the code the tests run.
PRODUCT: Final = Path(erev_api.__file__).resolve().parent
KERNEL: Final = "jobs/"
# What opens a transaction that can write. ``unit_of_work`` is the plain one of ``erev_api.uow``:
# called as a method it is the context's, which is the door.
OPENERS: Final = frozenset(
    {
        "tenant_session",
        "platform_session",
        "identity_session",
        "release_session",
        "copy_transaction",
        "unit_of_work",
    }
)
DOOR: Final = "enlist"

Opened = tuple[str, str]  # module path below the package, enclosing function

# The transactions that pass the door by themselves, by function: a new one is added here.
THROUGH_THE_DOOR: Final[dict[Opened, int]] = {
    ("domain/platform/sandbox_reset.py", "create_empty_sandbox"): 1,  # the empty successor
    ("domain/platform/sandboxes.py", "load_sandbox"): 2,  # the sandbox's tenant; the target
    ("domain/platform/sandboxes.py", "load_sandbox.copy_step"): 1,  # every copy step
}
# The transactions that do not, each with what it rests on instead.
WITHOUT_THE_DOOR: Final[dict[Opened, str]] = {
    ("domain/journals/export.py", "dispatch_batch"): (
        "the relay's topic handler reads the batch under its row lock and writes nothing there; "
        "a posting is recorded by a unit of work (05 ADP-31)"
    ),
    ("domain/platform/support_grants.py", "expire_due"): (
        "a periodic task of the worker reads the tenant directory: no job, no attempt (05 SCH-15)"
    ),
    ("domain/platform/shred_completion.py", "run"): (
        "a periodic task of the worker reads the tenant directory: no job, no attempt (05 SCH-16); "
        "what it writes, it writes in units of work, one per file (joined by the supervisor)"
    ),
    ("domain/platform/tenant_directory.py", "active_tenants"): (
        "the tenant directory of the worker's periodic tasks: no job, no attempt"
    ),
    ("events/outbox.py", "_claim"): (
        "a message is claimed under its own stamp, and a relay that lost the claim records "
        "nothing (05 ADP-32); delivery is at least once by design"
    ),
    ("events/outbox.py", "_record"): "written only while the message's claim stamp still holds",
    ("events/outbox.py", "_dispatch_email"): (
        "marks a notification's e-mail as sent, once, after the send the claim covers"
    ),
    ("events/webhooks.py", "_claim"): "a delivery is claimed under its own lease (05 NTR-12)",
    ("events/webhooks.py", "_attempt"): (
        "recorded only where the delivery's claim stamp still holds (SPEC-Q-216)"
    ),
}


def _callee(node: ast.expr) -> tuple[str, bool] | None:
    """(name, called as an attribute) of a call's function."""
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id, False
    if isinstance(node.func, ast.Attribute):
        return node.func.attr, True
    return None


def _handed(function: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> bool:
    """Whether the function is handed a job context or a job runtime: by the parameter's name
    (``jc``, ``runtime``) or by its annotation."""
    arguments = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    for argument in arguments:
        if argument.arg in ("jc", "runtime"):
            return True
        annotation = argument.annotation
        named = "" if annotation is None else (ast.get_source_segment(source, annotation) or "")
        if "JobContext" in named or "JobRuntime" in named:
            return True
    return False


def _passes_the_door(body: list[ast.stmt], session: str | None) -> bool:
    """Whether the block's first statement hands its session to ``enlist``."""
    first = body[0]
    if session is None or not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)):
        return False
    name = _callee(first.value)
    if name is None or name[0] != DOOR:
        return False
    return any(isinstance(arg, ast.Name) and arg.id == session for arg in first.value.args)


def opened(source: str) -> list[tuple[int, str, bool]]:
    """(line, enclosing function, passes the door) of every transaction that can write and that
    a function handed a job context or a job runtime opens without a unit of work's door."""
    found: list[tuple[int, str, bool]] = []

    def visit(node: ast.AST, owner: str | None, inside: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                name = child.name if owner is None else f"{owner}.{child.name}"
                visit(child, name, inside or _handed(child, source))
                continue
            if isinstance(child, ast.ClassDef):
                visit(child, child.name if owner is None else f"{owner}.{child.name}", inside)
                continue
            if isinstance(child, ast.With) and inside:
                for item in child.items:
                    call = item.context_expr
                    name = _callee(call)
                    if name is None or name[0] not in OPENERS:
                        continue
                    if name == ("unit_of_work", True):
                        continue
                    assert isinstance(call, ast.Call)
                    read_only = any(
                        keyword.arg == "read_only"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in call.keywords
                    )
                    if read_only:
                        continue
                    target = item.optional_vars
                    session = target.id if isinstance(target, ast.Name) else None
                    found.append(
                        (child.lineno, owner or "<module>", _passes_the_door(child.body, session))
                    )
            visit(child, owner, inside)

    visit(ast.parse(source), None, False)
    return found


def _modules() -> list[tuple[str, str]]:
    return [
        (path.relative_to(PRODUCT).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(PRODUCT.rglob("*.py"))
    ]


def test_dg_krn_job_04_a_transaction_of_a_job_passes_the_door_or_is_listed() -> None:
    through: Counter[Opened] = Counter()
    without: Counter[Opened] = Counter()
    for relative, source in _modules():
        if relative.startswith(KERNEL):
            continue
        for _, owner, door in opened(source):
            (through if door else without)[(relative, owner)] += 1
    assert dict(through) == THROUGH_THE_DOOR
    assert set(without) == set(WITHOUT_THE_DOOR), sorted(set(without) ^ set(WITHOUT_THE_DOOR))
    assert all(count == 1 for count in without.values()), without


def test_dg_krn_job_04_the_scan_tells_a_door_from_a_bare_transaction() -> None:
    """Every rule can fail."""
    bare = "def load(jc):\n    with tenant_session(ctx) as session:\n        session.execute(q)\n"
    through = bare.replace("        session.execute(q)", "        jc.enlist(session)")
    late = bare.replace("        session.execute(q)", "        f()\n        jc.enlist(session)")
    another = bare.replace("        session.execute(q)", "        jc.enlist(other)")
    read_only = bare.replace("tenant_session(ctx)", "tenant_session(ctx, read_only=True)")
    unit = bare.replace("tenant_session(ctx)", "jc.unit_of_work()")
    plain_unit = bare.replace("tenant_session(ctx)", "unit_of_work(ctx)")
    system = bare.replace("tenant_session(ctx)", "system_unit_of_work(jc.runtime, p)")
    request = bare.replace("def load(jc)", "def command(uow)")
    by_type = bare.replace("def load(jc)", "def load(context: JobContext)")
    by_runtime = bare.replace("def load(jc)", "def sweep(clock, *, runtime)")
    nested = "def load(jc):\n    def step():\n        with platform_session(s) as session:\n"
    nested += "            session.execute(q)\n    return step\n"
    passed = "def create(runtime, *, enlist):\n    with platform_session(s) as session:\n"
    passed += "        enlist(session)\n"
    assert opened(bare) == [(2, "load", False)]
    assert opened(through) == [(2, "load", True)]
    assert opened(late) == [(2, "load", False)]
    assert opened(another) == [(2, "load", False)]
    assert opened(read_only) == []
    assert opened(unit) == []
    assert opened(plain_unit) == [(2, "load", False)]
    assert opened(system) == []
    assert opened(request) == []
    assert opened(by_type) == [(2, "load", False)]
    assert opened(by_runtime) == [(2, "sweep", False)]
    assert opened(nested) == [(3, "load.step", False)]
    assert opened(passed) == [(2, "create", True)]


def test_dg_krn_job_04_an_attempt_and_a_context_with_a_job_row_are_the_registrys() -> None:
    """The door stands in the runtime the registry hands a handler. So an attempt is made in
    one place, where the registry runs a handler, and a context with a job row cannot be built
    without one: its heartbeat would be nobody's."""
    made: Counter[str] = Counter()
    for relative, source in _modules():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and _callee(node) == ("JobAttempt", False):
                made[relative] += 1
    assert dict(made) == {"jobs/registry.py": 1}

    tenant_id, job_id = UUID(int=1), UUID(int=2)
    runtime = JobRuntime(clock=frozen_clock(), keyring=None, files=None)

    def context(runtime: JobRuntime, *, persisted: bool) -> JobContext:
        return JobContext(
            job_id=job_id,
            tenant_id=tenant_id,
            kind=JobKind.REPORT_RUN,
            principal=system_principal(tenant_id),
            runtime=runtime,
            persisted=persisted,
        )

    with pytest.raises(RuntimeError, match="runs as an attempt"):
        context(runtime, persisted=True)
    inline = context(runtime, persisted=False)
    # No job row: no beat, no progress, no cancellation, and nothing to enlist in - none of
    # them opens a session.
    inline.heartbeat()
    inline.progress(1, 2)
    assert inline.cancel_requested() is False
    inline.enlist(_Refusing())


class _Refusing:
    """A session nothing may be sent to."""

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"a statement was sent: {statement}")


class _Recording:
    """A session that keeps the statements it is sent."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self.statements.append(statement)
        return None


def test_dg_krn_db_08_the_jobs_lock_is_a_read_a_copy_step_may_send() -> None:
    """A copy step of a sandbox load runs under a guard that admits reads, and inserts and
    updates of the copied tables, and nothing else (05 SBX-04). The job's lock is a SELECT of
    the lock function, which the guard admits as it is; written as text it would be refused,
    and the step with it."""
    job_id = UUID(int=7)
    session = _Recording()
    JobAttempt(job_id=job_id, tenant_id=UUID(int=1), task_id=None).hold(session)  # type: ignore[arg-type]
    (statement,) = session.statements
    sandboxes.check_copy_statement(statement)
    compiled = statement.compile(compile_kwargs={"literal_binds": True})
    assert str(compiled).startswith("SELECT pg_advisory_xact_lock_shared(hashtextextended(")
    assert unit_lock_key(job_id) == f"erev-job-unit:{job_id}"
    assert f"'{unit_lock_key(job_id)}', 0" in str(compiled)
    with pytest.raises(RuntimeError, match="SELECT, INSERT and UPDATE statements only"):
        sandboxes.check_copy_statement(text("SELECT pg_advisory_xact_lock_shared(1)"))


def test_ntf_05_the_body_of_a_stopped_job_says_what_was_not_kept() -> None:
    """PRD NTF-05 rev 1.191: a job the sweeper stopped after ten minutes without a heartbeat is
    told that it was stopped and what is not kept. Every other failure keeps "Nothing was
    committed." - and so does a job whose task never started it, which carries the same slug
    with another detail: no handler ran, so nothing was."""
    job_id = UUID(int=3)
    stalled = registry.failure_problem(Problem(registry.STALL_SLUG, registry.STALL_DETAIL), job_id)
    stranded = registry.failure_problem(Problem(registry.STALL_SLUG, STRANDED_DETAIL), job_id)
    other = registry.failure_problem(RuntimeError("boom"), job_id)
    assert registry.stopped_as_stalled(stalled)
    assert not registry.stopped_as_stalled(stranded)
    assert not registry.stopped_as_stalled(other)

    def body(problem: dict[str, Any]) -> str:
        reason = str(problem.get("detail") or problem["title"]).rstrip(".")
        return registry.job_failed_body(
            label="Import commit", step="attempt 1", reason=reason, problem=problem
        )

    assert body(stalled) == (
        "Import commit failed at attempt 1: no heartbeat for 10 minutes. The job was stopped; "
        "what it had not committed by then is not kept."
    )
    assert body(stranded) == (
        "Import commit failed at attempt 1: the worker task stopped before the job started. "
        "Nothing was committed."
    )
    assert body(other) == (
        "Import commit failed at attempt 1: The job stopped with an unexpected error. "
        "Nothing was committed."
    )
