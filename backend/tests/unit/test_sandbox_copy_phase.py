"""The COPY PHASE of a sandbox load — the CPU guards of its compensating controls (05 SBX-04 rev
1.30; 04 §14.3 rev 1.85; supervisor engineering ruling of 2026-09-22 on the SNP-2 loader's batch-#8
returns). The phase runs under the provisioning platform scope, so these pin what that scope can
reach and what the phase does with it:

1. ``LOAD_ORDER`` carries no ``tenant`` table and a copy-phase transaction writes the COPIED
   datasets of ``LOAD_ORDER`` only — the tenant-creation capability the scope retains is unused by
   construction;
2. exactly five database guards yield to the scope (a sixth would widen what the copy can do);
3. a database guard's own refusal is re-raised by name, every other error propagates untouched.

The database witnesses — row-level security still refuses another tenant's row inside a copy-phase
transaction, and each transaction records its ``PLATFORM_SCOPE_USED`` event — are in
``tests/pg/test_sandbox_isolation.py``. No database here.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from erev_api.db import migration_ops
from erev_api.db import session as db_session
from erev_api.db.tables import metadata
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.problems import Problem
from sqlalchemy.orm import Session

SANDBOX = UUID("01a0c1a2-0000-7000-8000-000000000011")
REQUESTER = UUID("01a0c1a2-0000-7000-8000-000000000012")
VERSIONS = Path(migration_ops.__file__).resolve().parent / "migrations" / "versions"
GUARD_LINE = "EREV-CFG-002: a version of erev.sod_rule is inserted as DRAFT, not PUBLISHED"


class _Orig(Exception):
    """A driver error as psycopg raises it: a SQLSTATE and a primary message."""

    def __init__(self, sqlstate: str, message: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


def _db_error(sqlstate: str, message: str) -> sa.exc.DBAPIError:
    return sa.exc.DBAPIError("INSERT INTO erev.sod_rule", {}, _Orig(sqlstate, message))


def _table(name: str) -> sa.Table:
    return metadata.tables[f"erev.{name}"]


# --- control 1: the tables a copy-phase transaction writes ---------------------------------------


def test_load_order_carries_no_tenant_table() -> None:
    """The provisioning scope lifts the ``tenant`` INSERT policy (RLS-TN); ``LOAD_ORDER`` never
    names ``tenant`` (it is SHARED: created by the provision step, read in place), so the copy
    phase has no statement that could use it. Every table it does write is tenant-owned — it
    carries ``tenant_id``, the column every RLS-T / TE / TM policy keys on."""
    assert "tenant" not in sd.LOAD_ORDER
    assert sd.RULES["tenant"].snapshot_class is sd.SnapshotClass.SHARED
    copied = {
        name for name in sd.LOAD_ORDER if sd.RULES[name].snapshot_class is sd.SnapshotClass.COPIED
    }
    assert sb.COPY_PHASE_TABLES == copied
    assert "tenant" not in sb.COPY_PHASE_TABLES
    # the REPLAY_REFERENCE datasets belong to the period replay, which does not carry the scope
    assert set(sd.LOAD_ORDER) - sb.COPY_PHASE_TABLES == {
        "period_state",
        "period_state_transition",
        "period_lock",
    }
    for name in sorted(sb.COPY_PHASE_TABLES):
        assert "tenant_id" in _table(name).c, name
    # every row the phase finalizes or restores is a row it inserted
    assert set(sd.FINALIZATIONS) <= sb.COPY_PHASE_TABLES
    inv = sd.inventory()
    assert {d.name for d in inv.datasets if d.deferred} <= sb.COPY_PHASE_TABLES


def test_check_copy_statement_admits_reads_and_writes_of_the_copied_tables_only() -> None:
    """A copy-phase transaction reads, and inserts or updates rows of ``COPY_PHASE_TABLES``: a
    write to any other table — ``tenant`` above all — a DELETE, or a textual statement is refused
    before it reaches the database, as a defect (``RuntimeError``), never as a business refusal."""
    for name in ("sod_rule", "tenant_membership", "approval_request", "contract_event"):
        table = _table(name)
        sb.check_copy_statement(sa.insert(table).values(tenant_id=SANDBOX))
        sb.check_copy_statement(sa.update(table).where(table.c.tenant_id == SANDBOX))
        sb.check_copy_statement(sa.update(table).returning(*table.c))  # the DB-03 kernel's shape
    sb.check_copy_statement(sa.select(_table("approval_request")))
    sb.check_copy_statement(sa.select(_table("tenant")))  # reading is left to row-level security
    for name in ("tenant", "audit_chain_head", "security_event", "app_user", "job"):
        with pytest.raises(RuntimeError, match=f"copied LOAD_ORDER tables only, not '{name}'"):
            sb.check_copy_statement(sa.insert(_table(name)))
        with pytest.raises(RuntimeError, match=f"not '{name}'"):
            sb.check_copy_statement(sa.update(_table(name)))
    # a REPLAY_REFERENCE table is written by the period replay, never by the copy phase
    with pytest.raises(RuntimeError, match="not 'period_state'"):
        sb.check_copy_statement(sa.insert(_table("period_state")))
    with pytest.raises(RuntimeError, match="SELECT, INSERT and UPDATE statements only"):
        sb.check_copy_statement(sa.delete(_table("sod_rule")))
    with pytest.raises(RuntimeError, match="SELECT, INSERT and UPDATE statements only"):
        sb.check_copy_statement(sa.text("SELECT set_config('app.tenant_id', :t, true)"))
    # the table object itself must be the model's: a look-alike of another MetaData is refused
    other = sa.Table("sod_rule", sa.MetaData(schema="erev"), sa.Column("tenant_id", sa.Uuid()))
    with pytest.raises(RuntimeError, match="not 'sod_rule'"):
        sb.check_copy_statement(sa.insert(other))


# --- the scope and the guards that yield to it ----------------------------------------------------


def test_the_copy_phase_scope_is_the_provisioning_scope() -> None:
    assert sb.COPY_PHASE_SCOPE == "provisioning"
    assert sb.COPY_PHASE_SCOPE in db_session.PLATFORM_SCOPES


def test_exactly_five_guards_yield_to_the_provisioning_scope() -> None:
    """05 SBX-04 rev 1.30: "exactly five guards yield to the scope — the ``tenant`` INSERT policy,
    the DB-04 version guard, the DB-04 child guard and the two SSP bodies". Every place the schema
    reads ``app.platform_scope`` against ``'provisioning'`` is counted here, so a sixth yield —
    which would widen what a copy-phase transaction can do — fails this guard until the ruling's
    exposure analysis is redone."""
    reads = re.compile(
        r"current_setting\('app\.platform_scope', true\)\s*"
        r"(?:=|IS DISTINCT FROM)\s*'provisioning'"
    )
    found: dict[str, int] = {}
    for path in (Path(migration_ops.__file__), *sorted(VERSIONS.glob("*.py"))):
        count = len(reads.findall(path.read_text(encoding="utf-8")))
        if count:
            found[path.name] = count
    assert found == {
        # the RLS-TN INSERT policy, CONFIG_INSERT_GUARD and CONFIG_CHILD_BODY
        "migration_ops.py": 3,
        "0034_ssp_books.py": 1,  # the SSP range child body
        "0035_ssp_publication.py": 1,  # the SSP version body
    }
    assert "IS DISTINCT FROM 'provisioning'" in migration_ops.CONFIG_INSERT_GUARD
    assert "= 'provisioning'" in migration_ops.CONFIG_CHILD_BODY
    # the DB-04 guards yield on INSERT only: an UPDATE of a version past TESTED stays frozen,
    # which is why a copied self-reference is inserted with its row and never fixed up
    assert "TG_OP = 'INSERT'" in migration_ops.CONFIG_INSERT_GUARD
    assert "TG_OP = 'INSERT' AND current_setting" in migration_ops.CONFIG_CHILD_BODY
    policy = [
        statement
        for statement in migration_ops.rls_statements("tenant", "RLS-TN")
        if "provisioning" in statement
    ]
    assert len(policy) == 1 and "FOR INSERT" in policy[0]  # INSERT only: no read, no update


# --- control 4: a guard's refusal by name ---------------------------------------------------------


def test_guard_refusal_is_the_first_line_of_a_database_guards_own_refusal() -> None:
    """SQLSTATE P0001 with an ``EREV-…`` message (04 §14.1) is a guard's refusal; its first line
    is what the named refusal carries. Every other error — another SQLSTATE, a P0001 without the
    code, a Python error — is a defect and is never named."""
    assert sb.guard_refusal(_db_error("P0001", GUARD_LINE)) == GUARD_LINE
    context = GUARD_LINE + "\nCONTEXT:  PL/pgSQL function tg_config_version() line 21 at RAISE"
    assert sb.guard_refusal(_db_error("P0001", context)) == GUARD_LINE
    assert sb.guard_refusal(_db_error("P0001", "  EREV-APR-001: self-approval  ")) == (
        "EREV-APR-001: self-approval"
    )
    assert sb.guard_refusal(_db_error("P0001", "a plain RAISE EXCEPTION")) is None
    assert sb.guard_refusal(_db_error("P0001", "see EREV-CFG-002 for the rule")) is None
    assert sb.guard_refusal(_db_error("42501", "permission denied for table tenant")) is None
    assert sb.guard_refusal(_db_error("23503", "violates foreign key constraint")) is None
    assert sb.guard_refusal(_db_error("428C9", "cannot insert a non-DEFAULT value")) is None
    assert sb.guard_refusal(Problem("invalid-transition")) is None
    assert sb.guard_refusal(KeyError("sod_rule")) is None


def test_copy_refused_is_snapshot_not_loadable_with_the_guards_line_as_detail() -> None:
    refused = sb.copy_refused("the copy of sod_rule", GUARD_LINE)
    assert (refused.slug, refused.status) == ("precondition-failed", 412)
    assert refused.detail == GUARD_LINE  # 04 §14.3 rev 1.85: "the guard's first line as its detail"
    (error,) = refused.errors
    assert error.rule_id == sb.RULE_NOT_LOADABLE == "SNAPSHOT_NOT_LOADABLE"
    assert error.field == "tenant_snapshot_id"
    assert error.message == f"the copy of sod_rule was refused by a database guard: {GUARD_LINE}"


# --- one copy-phase transaction (the kernel factory replaced by a recording fake) ----------------


class _Recorder:
    def __init__(self, *, on_exit: BaseException | None = None) -> None:
        self.opened: list[dict[str, Any]] = []
        self.named: list[UUID] = []
        self.contexts: list[db_session.DbContext] = []
        self.session = Session()  # unbound: a statement that passed the guard has nowhere to go
        self.committed = False
        self.on_exit = on_exit

    @contextmanager
    def platform_session(self, scope: str, **kwargs: Any) -> Iterator[Session]:
        self.opened.append({"scope": scope, **kwargs})
        yield self.session
        if self.on_exit is not None:
            raise self.on_exit  # a deferred constraint, raised by the commit
        self.committed = True

    def name_platform_tenant(self, session: Session, tenant_id: UUID) -> None:
        assert session is self.session
        self.named.append(tenant_id)

    def set_tenant_context(self, session: Session, ctx: db_session.DbContext) -> None:
        assert session is self.session
        self.contexts.append(ctx)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    fake = _Recorder()
    _install(monkeypatch, fake)
    return fake


def _install(monkeypatch: pytest.MonkeyPatch, fake: _Recorder) -> None:
    monkeypatch.setattr(db_session, "platform_session", fake.platform_session)
    monkeypatch.setattr(db_session, "name_platform_tenant", fake.name_platform_tenant)
    monkeypatch.setattr(db_session, "set_tenant_context", fake.set_tenant_context)


def _transaction(step: str = "the copy of sod_rule") -> Any:
    return sb.copy_transaction(
        sandbox_tenant_id=SANDBOX,
        requested_by=REQUESTER,
        request_id="job-1-load-sod_rule",
        keyring=object(),  # type: ignore[arg-type]
        step=step,
    )


def test_copy_transaction_opens_the_scope_for_the_sandbox_and_the_requester(
    recorder: _Recorder,
) -> None:
    """One transaction: the provisioning platform scope, for the requester, under the step's
    request id — then the sandbox named for its ``PLATFORM_SCOPE_USED`` event and ONE tenant
    context, the sandbox's (TXN-08: a transaction never sets two)."""
    with _transaction() as session:
        assert session is recorder.session
    (opened,) = recorder.opened
    assert opened["scope"] == "provisioning"
    assert opened["actor_user_id"] == REQUESTER
    assert opened["request_id"] == "job-1-load-sod_rule"
    assert recorder.named == [SANDBOX]
    assert recorder.contexts == [
        db_session.DbContext(tenant_id=SANDBOX, user_id=None, entity_scope="*")
    ]
    assert recorder.committed


def test_copy_transaction_refuses_a_write_outside_the_copied_tables(recorder: _Recorder) -> None:
    """Inside the block every statement of the session passes ``check_copy_statement``: an INSERT
    into ``tenant`` is refused before any connection is asked for. After the block the guard is
    gone — the scope's own ``PLATFORM_SCOPE_USED`` insert, which follows, is not the phase's."""
    tenant = _table("tenant")
    with pytest.raises(RuntimeError, match="not 'tenant'"):
        with _transaction() as session:
            session.execute(sa.insert(tenant).values(id=SANDBOX))
    assert not recorder.committed
    with _transaction() as session:
        with pytest.raises(sa.exc.UnboundExecutionError):  # admitted by the guard, no bind here
            session.execute(sa.insert(_table("sod_rule")).values(tenant_id=SANDBOX))
    with pytest.raises(sa.exc.UnboundExecutionError):  # the guard was removed with the block
        recorder.session.execute(sa.insert(tenant).values(id=SANDBOX))


def test_copy_transaction_names_a_guards_refusal_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, recorder: _Recorder
) -> None:
    """A P0001 ``EREV-…`` refusal of a statement becomes ``SNAPSHOT_NOT_LOADABLE`` with the guard's
    first line, chained to the database error; a ``Problem`` raised inside passes unchanged; any
    other database or Python error propagates as the defect it is."""
    guard = _db_error("P0001", GUARD_LINE)
    with pytest.raises(Problem) as refused:
        with _transaction():
            raise guard
    assert refused.value.slug == "precondition-failed" and refused.value.detail == GUARD_LINE
    assert refused.value.errors[0].rule_id == sb.RULE_NOT_LOADABLE
    assert "the copy of sod_rule" in refused.value.errors[0].message
    assert refused.value.__cause__ is guard
    assert not recorder.committed

    original = Problem("invalid-transition", "injected refusal")
    with pytest.raises(Problem) as passed:
        with _transaction():
            raise original
    assert passed.value is original

    for defect in (
        _db_error("42501", "permission denied for table role_assignment"),
        _db_error("23503", "violates foreign key constraint"),
        _db_error("P0001", "a RAISE without a code"),
    ):
        with pytest.raises(sa.exc.DBAPIError) as propagated:
            with _transaction():
                raise defect
        assert propagated.value is defect
    with pytest.raises(KeyError):
        with _transaction():
            raise KeyError("sod_rule")

    # a deferred constraint raises at the commit, after the block: named all the same
    at_commit = _Recorder(on_exit=_db_error("P0001", "EREV-PER-001: no transition row"))
    _install(monkeypatch, at_commit)
    with pytest.raises(Problem) as late:
        with _transaction("the fixup of the deferred references"):
            pass
    assert late.value.detail == "EREV-PER-001: no transition row"
    assert "the fixup of the deferred references" in late.value.errors[0].message
