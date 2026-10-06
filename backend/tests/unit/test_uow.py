"""Unit of work (dev-guide §5.18 DG-KRN-UOW-01 to 03; BUILD_SPEC FND-11).

The units of work run on the real ``erev_app`` engine of the test database; session events record
when SQLAlchemy commits or rolls back, so hook order is observed against the real commit.
"""

from __future__ import annotations

import dataclasses
import io
import json
import uuid
from datetime import timedelta

import pytest
from erev_api.auth.keyring import build_keyring
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import every_entity_scope, system_entity_scope
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import event, text
from support.db import TestDatabase


def _context(clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=system_principal(uuid.uuid4()),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="uow-test",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


def _record_transactions(uow: UnitOfWork, calls: list[str]) -> None:
    event.listen(uow.session, "after_commit", lambda _: calls.append("commit"))
    event.listen(uow.session, "after_rollback", lambda _: calls.append("rollback"))


def test_krn_uow_01_now_captured_once(
    committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock
) -> None:
    ctx = _context(clock)
    opened_at = clock.now()
    with unit_of_work(
        ctx,
        clock=clock,
        keyring=build_keyring(app_settings),
        files=LocalFileStore(app_settings.file_root),
    ) as uow:
        assert uow.now == opened_at
        clock.advance(timedelta(minutes=1))
        assert clock.now() == opened_at + timedelta(minutes=1)
        assert uow.now == opened_at
        assert uow.principal is ctx.principal
        # TXN-01: the transaction carries the principal's tenant context and the timeout.
        row = uow.session.execute(
            text(
                "SELECT current_setting('app.tenant_id'), current_setting('app.user_id'), "
                "current_setting('app.entity_scope'), current_setting('statement_timeout')"
            )
        ).one()
        assert tuple(row) == (str(ctx.principal.tenant_id), "", "*", "1min")
        uow.commit()


def test_krn_uow_02_hooks_run_in_order_after_commit(
    committed_db: TestDatabase,
    app_settings: Settings,
    clock: FrozenClock,
    log_stream: io.StringIO,
) -> None:
    calls: list[str] = []

    def h1() -> None:
        calls.append("h1")

    def h2() -> None:
        calls.append("h2")
        raise RuntimeError("hook failed")

    def h3() -> None:
        calls.append("h3")

    with unit_of_work(
        _context(clock),
        clock=clock,
        keyring=build_keyring(app_settings),
        files=LocalFileStore(app_settings.file_root),
    ) as uow:
        _record_transactions(uow, calls)
        uow.session.execute(text("SELECT 1"))
        for hook in (h1, h2, h3):
            uow.after_commit(hook)
        assert calls == []
        assert uow.commit() is None

    assert calls == ["commit", "h1", "h2", "h3"]
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    (failure,) = [line for line in lines if line["event"] == "uow.after_commit_failed"]
    assert failure["hook"].endswith(".h2")
    assert failure["level"] == "error"
    assert "RuntimeError: hook failed" in failure["exception"]


def test_krn_uow_03_double_commit_and_rollback(
    committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock
) -> None:
    keyring = build_keyring(app_settings)
    files = LocalFileStore(app_settings.file_root)

    committed_calls: list[str] = []
    with unit_of_work(_context(clock), clock=clock, keyring=keyring, files=files) as uow:
        _record_transactions(uow, committed_calls)
        uow.session.execute(text("SELECT 1"))
        uow.commit()
        with pytest.raises(RuntimeError, match="already committed"):
            uow.commit()
    assert committed_calls == ["commit"]

    calls: list[str] = []
    with unit_of_work(_context(clock), clock=clock, keyring=keyring, files=files) as uow:
        _record_transactions(uow, calls)
        uow.session.execute(text("SELECT 1"))
        uow.after_commit(lambda: calls.append("hook"))
    assert calls == ["rollback"]

    failed_calls: list[str] = []
    with pytest.raises(ValueError, match="command failed"):
        with unit_of_work(_context(clock), clock=clock, keyring=keyring, files=files) as uow:
            _record_transactions(uow, failed_calls)
            uow.session.execute(text("SELECT 1"))
            uow.after_commit(lambda: failed_calls.append("hook"))
            raise ValueError("command failed")
    assert "commit" not in failed_calls
    assert "hook" not in failed_calls
    assert failed_calls[0] == "rollback"


def test_krn_uow_02_before_commit_steps_and_a_commit_that_fails(
    committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock
) -> None:
    """DG-KRN-UOW-02 (1a), rev 1.266 (item JOB-STALL-COMMIT-RACE-1). A before-commit step runs
    inside ``commit()`` in registration order, before the database's commit; one registered
    after the commit is refused. A commit that fails - at a step, or at the audit chain, whose
    head a tenant without one cannot give - ends the transaction before the error leaves
    ``commit()``: a caller that takes the error and leaves its block normally commits nothing,
    where the session would commit the transaction it finds open, and no hook runs."""
    keyring = build_keyring(app_settings)
    files = LocalFileStore(app_settings.file_root)

    calls: list[str] = []
    with unit_of_work(_context(clock), clock=clock, keyring=keyring, files=files) as uow:
        _record_transactions(uow, calls)
        uow.session.execute(text("SELECT 1"))
        uow.before_commit(lambda: calls.append("step 1"))
        uow.before_commit(lambda: calls.append("step 2"))
        uow.after_commit(lambda: calls.append("hook"))
        uow.commit()
        with pytest.raises(RuntimeError, match="before_commit is too late"):
            uow.before_commit(lambda: None)
    assert calls == ["step 1", "step 2", "commit", "hook"]

    refused: list[str] = []

    def refuse() -> None:
        refused.append("step")
        raise LookupError("no row, no commit")

    with unit_of_work(_context(clock), clock=clock, keyring=keyring, files=files) as uow:
        _record_transactions(uow, refused)
        uow.session.execute(text("SELECT 1"))
        uow.before_commit(refuse)
        uow.before_commit(lambda: refused.append("a later step"))
        uow.after_commit(lambda: refused.append("hook"))
        with pytest.raises(LookupError, match="no row, no commit"):
            uow.commit()
        assert not uow.session.in_transaction()
    assert refused == ["step", "rollback"]

    unchained: list[str] = []
    ctx = _context(clock)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        _record_transactions(uow, unchained)
        uow.session.execute(text("SELECT 1"))
        uow.buffer_audit_event({"tenant_id": ctx.principal.tenant_id})
        uow.after_commit(lambda: unchained.append("hook"))
        with pytest.raises(Problem) as missing:
            uow.commit()
        assert missing.value.slug == "ledger-integrity"
        assert not uow.session.in_transaction()
    assert unchained == ["rollback"]


def _settings(uow: UnitOfWork) -> tuple[str, str]:
    row = uow.session.execute(
        text("SELECT current_setting('app.user_id'), current_setting('app.entity_scope')")
    ).one()
    return str(row[0]), str(row[1])


def test_krn_uow_05_as_system_names_whom_it_acts_for_and_restores_what_it_found(
    committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock
) -> None:
    """DG-KRN-UOW-05 (05 TXN-10; supervisor ruling R-95): inside ``as_system()`` the principal
    is SYSTEM without a permission, on behalf of the caller — of the caller's own on-behalf-of
    when the caller is SYSTEM already — and the transaction is SYSTEM's under the tenant's scope.
    It is re-entrant, and leaving it restores the principal and the two settings, also when its
    block raises."""
    tenant_id, user_id, entity_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    person: Principal = dataclasses.replace(
        system_principal(tenant_id),
        kind=PrincipalKind.USER,
        id=user_id,
        display_name="Una Lindqvist",
        roles=("revenue_accountant",),
        permissions=frozenset({"event.record"}),
        entity_scope=(entity_id,),
        auth_method="password",
    )
    cases = (
        (person, user_id, (str(user_id), str(entity_id))),
        (system_principal(tenant_id, on_behalf_of_id=user_id), user_id, ("", "*")),
        (system_principal(tenant_id), None, ("", "*")),
    )
    for principal, behalf, found in cases:
        ctx = dataclasses.replace(_context(clock), principal=principal)
        with unit_of_work(
            ctx,
            clock=clock,
            keyring=build_keyring(app_settings),
            files=LocalFileStore(app_settings.file_root),
        ) as uow:
            assert _settings(uow) == found
            with uow.as_system():
                acting = uow.principal
                assert (acting.kind, acting.id, acting.on_behalf_of_id, acting.tenant_id) == (
                    PrincipalKind.SYSTEM,
                    None,
                    behalf,
                    tenant_id,
                )
                assert (acting.permissions, acting.roles, acting.entity_scope) == (
                    frozenset(),
                    (),
                    "*",
                )
                assert _settings(uow) == ("", "*")
                with uow.as_system():
                    assert uow.principal is acting
                # leaving the inner block changed nothing: the outer one is still in force
                assert uow.principal is acting and _settings(uow) == ("", "*")
            assert uow.principal is principal and uow.ctx is ctx
            assert _settings(uow) == found
            with pytest.raises(RuntimeError, match="inside"), uow.as_system():
                raise RuntimeError("inside the manager")
            assert uow.principal is principal and uow.ctx is ctx
            assert _settings(uow) == found
            # One block widens the entity scope (``system_entity_scope``; the close gates' is the
            # same one): the computation's block nests inside it and around it, and whichever
            # ends first leaves the other's scope in force (DG-KRN-DB-05).
            db_context = principal.db_context
            with system_entity_scope(uow.session), every_entity_scope(uow.session, db_context):
                assert _settings(uow) == (found[0], "*")
                with uow.as_system():
                    assert _settings(uow) == ("", "*")
                # an approval hook's recompute ended: the hook still reads every entity, as its
                # decider
                assert uow.principal is principal and _settings(uow) == (found[0], "*")
            assert _settings(uow) == found
            with uow.as_system():
                with every_entity_scope(uow.session, db_context):
                    with system_entity_scope(uow.session):
                        assert _settings(uow) == ("", "*")
                    assert _settings(uow) == ("", "*")
                assert _settings(uow) == ("", "*")
            assert uow.principal is principal and _settings(uow) == found
