"""Unit of work KRN-UOW (docs/dev-guide.md §5.18; 05 TXN-01).

Every command runs inside one ``unit_of_work``: a tenant transaction opened with the principal's
context, one captured ``now``, the process keyring and file store, buffered audit events and
after-commit hooks. ``commit()`` flushes, runs the before-commit steps a job's unit of work
registers, appends the buffered audit events to the tenant chain, commits and then runs the hooks
(DG-KRN-UOW-02 steps (1) to (4)). Leaving the block without committing rolls back and discards
the buffer and the hooks.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.audit import chain as audit_chain
from erev_api.audit import writer as audit_writer
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import Clock
from erev_api.controls.evidence import ControlRefusal
from erev_api.db.session import system_entity_scope, system_user, tenant_session
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import FileStore
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import from_db_error

_LOGGER: Final = "erev_api.uow"

register_logger_fields(_LOGGER, ("hook",))


def _hook_name(fn: Callable[[], None]) -> str:
    return getattr(fn, "__qualname__", None) or repr(fn)


class UnitOfWork:
    ctx: RequestContext
    session: Session
    clock: Clock
    now: datetime
    keyring: KeyRing
    files: FileStore

    def __init__(
        self,
        *,
        ctx: RequestContext,
        session: Session,
        clock: Clock,
        keyring: KeyRing,
        files: FileStore,
    ) -> None:
        self.ctx = ctx
        self.session = session
        self.clock = clock
        # Captured once; every timestamp the command writes uses it (DG-KRN-UOW-01).
        self.now = clock.now()
        self.keyring = keyring
        self.files = files
        self._audit_events: list[Mapping[str, Any]] = []
        self._before_commit: list[Callable[[], None]] = []
        self._hooks: list[Callable[[], None]] = []
        self._committed = False
        self._as_system = False

    @property
    def principal(self) -> Principal:
        return self.ctx.principal

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def audit_events(self) -> tuple[Mapping[str, Any], ...]:
        """The events buffered for the commit, in buffer order."""
        return tuple(self._audit_events)

    def audit(self, **kwargs: Any) -> None:
        """``audit.writer.record(self, **kwargs)`` (DG-KRN-AUD-01)."""
        audit_writer.record(self, **kwargs)

    def defer(self, kind: JobKind, params: Mapping[str, Any], **kwargs: Any) -> Mapping[str, Any]:
        """``jobs.registry.defer(self, kind, params, **kwargs)`` (DG-KRN-JOB-02)."""
        # Imported here: the registry's job context builds units of work.
        from erev_api.jobs import registry

        return registry.defer(self, kind, params, **kwargs)

    def defer_single(
        self, kind: JobKind, params: Mapping[str, Any], **kwargs: Any
    ) -> tuple[UUID, bool]:
        """``jobs.registry.defer_single(self, kind, params, **kwargs)``: the pending job of the
        kind and False, or the job deferred now and True (DG-KRN-AUD-07)."""
        from erev_api.jobs import registry

        return registry.defer_single(self, kind, params, **kwargs)

    def buffer_audit_event(self, event: Mapping[str, Any]) -> None:
        if self._committed:
            raise RuntimeError("unit of work already committed; audit events are too late")
        self._audit_events.append(event)

    def drain_audit_events(self) -> list[Mapping[str, Any]]:
        events, self._audit_events = self._audit_events, []
        return events

    def after_commit(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` after a successful commit, in registration order (DG-KRN-UOW-02 (4))."""
        if self._committed:
            raise RuntimeError("unit of work already committed; after_commit is too late")
        self._hooks.append(fn)

    def before_commit(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` inside ``commit()``, after the flush and before the audit chain's lock, in
        registration order (DG-KRN-UOW-02 (1a), rev 1.266): the last statements the unit of work
        sends before it takes the chain head. A ``fn`` that raises ends the commit there, as a
        failure at the chain head does, and nothing of the unit of work is committed
        (``commit``). The one caller is a job's unit of work, which writes its heartbeat on
        the job's row (``jobs.context.JobAttempt.enter``)."""
        if self._committed:
            raise RuntimeError("unit of work already committed; before_commit is too late")
        self._before_commit.append(fn)

    def commit(self) -> None:
        """Flush, run the before-commit steps, append the audit events, commit, then run the
        hooks; a second call raises (DG-KRN-UOW-02, UOW-03). A commit that fails after the
        flush - at a step, at the chain, at the database's commit - keeps nothing, whatever
        its caller does with the error: the transaction is rolled back before the error
        leaves this method, because the session commits an open transaction when its block
        is left without an error (``db.session``)."""
        if self._committed:
            raise RuntimeError("unit of work already committed")
        self._committed = True
        self.session.flush()
        try:
            for step in self._before_commit:
                step()
            # The audit chain head is the last lock of the transaction (DG-KRN-DB-08).
            audit_chain.flush(self)
            self.session.commit()
        except BaseException as exc:
            self.discard()
            if isinstance(exc, DBAPIError):
                problem = from_db_error(exc)
                if problem is not None:
                    raise problem from exc
            raise
        hooks, self._hooks = self._hooks, []
        for fn in hooks:
            try:
                fn()
            except Exception:
                # The commit stands; the job sweeper recovers lost deferrals (DG-KRN-JOB-06).
                get_logger(_LOGGER).exception("uow.after_commit_failed", hook=_hook_name(fn))

    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """DG-KRN-UOW-03 (rev 1.40; D-98 candidate 101d, Codex CONTEXT-R1): a nested transaction for
        writes the unit of work may have to undo WITHOUT ending it. On an exception the savepoint is
        rolled back and the audit events and hooks buffered inside it are dropped; the session keeps
        its tenant context (the app engine clears ``erev.context`` only on a transaction rollback,
        DG-KRN-DB-04) and every lock taken before the savepoint; the exception propagates. On
        success the savepoint is released and the writes stay part of the transaction."""
        events, hooks = len(self._audit_events), len(self._hooks)
        nested = self.session.begin_nested()
        try:
            yield
        except BaseException:
            nested.rollback()
            del self._audit_events[events:]
            del self._hooks[hooks:]
            raise
        nested.commit()

    @contextmanager
    def as_system(self) -> Iterator[None]:
        """DG-KRN-UOW-05 (05 TXN-10; supervisor ruling R-95): run the block as the SYSTEM
        principal on behalf of this unit of work's principal, under the tenant's scope.

        The computation of a combination group runs inside the transaction that asked for it and
        is reader-independent: what the engine reads and what the orchestrator writes do not
        depend on the entities the caller may see, nor on a scope an import narrowed. Inside the
        block ``principal`` is ``system_principal(tenant, on_behalf_of_id=…)`` — on behalf of the
        caller, or of the caller's own on-behalf-of when the caller is SYSTEM already — so rows are
        stamped SYSTEM and audit events carry ``on_behalf_of_id``, as a job's do; the transaction
        runs under ``system_entity_scope`` — the one block that widens the entity scope, the
        approvals kernel's and the close gates' too — and under ``system_user``, which this
        manager alone takes. Leaving the block restores the principal and the two settings,
        also when it raises. Re-entrant: inside itself it does nothing. Enter it before a
        savepoint whose rollback the block must survive.
        """
        if self._as_system:
            yield
            return
        caller = self.ctx
        principal = caller.principal
        behalf = (
            principal.on_behalf_of_id if principal.kind is PrincipalKind.SYSTEM else principal.id
        )
        acting = system_principal(principal.tenant_id, on_behalf_of_id=behalf)
        self._as_system = True
        self.ctx = dataclasses.replace(caller, principal=acting)
        try:
            with system_entity_scope(self.session), system_user(self.session):
                yield
        finally:
            self.ctx = caller
            self._as_system = False

    def discard(self) -> None:
        """Roll back and drop the buffered events and hooks of an uncommitted unit of work."""
        self._audit_events.clear()
        self._before_commit.clear()
        self._hooks.clear()
        self.session.rollback()


@contextmanager
def unit_of_work(
    ctx: RequestContext,
    *,
    clock: Clock,
    keyring: KeyRing,
    files: FileStore,
    statement_timeout_ms: int = 60_000,
) -> Iterator[UnitOfWork]:
    """A tenant transaction for ``ctx.principal`` with ``now`` captured once (DG-KRN-UOW-01)."""
    try:
        with tenant_session(
            ctx.principal.db_context, statement_timeout_ms=statement_timeout_ms
        ) as session:
            uow = UnitOfWork(ctx=ctx, session=session, clock=clock, keyring=keyring, files=files)
            try:
                yield uow
            finally:
                if not uow.committed:
                    uow.discard()
    except ControlRefusal as refused:
        if uow.committed:
            raise RuntimeError("a control refusal must precede commit") from refused
        # Exit the original session first: no business write or lock survives into this
        # independent evidence transaction. A failure to retain evidence is not hidden.
        if not refused.retained:
            with unit_of_work(
                ctx,
                clock=clock,
                keyring=keyring,
                files=files,
                statement_timeout_ms=statement_timeout_ms,
            ) as evidence_uow:
                refused.retain(evidence_uow)
                evidence_uow.commit()
            refused.retained = True
        raise
