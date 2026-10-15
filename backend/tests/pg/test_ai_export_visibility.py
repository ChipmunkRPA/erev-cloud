"""Retained export ownership applies to report and job reads, including audit readers."""

from dataclasses import replace
from uuid import UUID

import pytest
from alembic import command
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import job, report_run
from erev_api.domain.ai.log_export import capture_access
from erev_api.domain.platform.jobs import get_job
from erev_api.domain.reports.framework import run_row, runs_statement
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem
from sqlalchemy import exc, insert, select, text, update
from support.db import TestDatabase, alembic_config
from support.principals import colleague, member
from support.rows import RowContext, job_row, report_run_row
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_retained_exports_are_private_and_recheck_current_grants(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = member(keyring, clock)
    peer = colleague(owner.tenant_id, "export_auditor")
    permissions = {"ai.use", "settings.manage", "report.export", "report.run", "audit.read"}
    principal = replace(
        system_principal(owner.tenant_id),
        kind=PrincipalKind.USER,
        id=owner.user_id,
        permissions=frozenset(permissions),
        permission_scopes={code: "*" for code in permissions},
    )
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="retained-export-test",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    wide = capture_access(ctx)
    demoted = replace(principal, permissions=principal.permissions - {"settings.manage"})
    own = capture_access(replace(ctx, principal=demoted))
    rows = []
    with tenant_session(principal.db_context) as session:
        for access in (own, wide, None):
            context = RowContext(owner.tenant_id, owner.user_id)
            pending = job_row(context, session)
            pending.update(kind="REPORT_RUN", created_by=owner.user_id, created_by_kind="USER")
            session.execute(insert(job).values(**pending))
            run = report_run_row(context, session)
            # The existing inventory definition witnesses that the extra guard does not
            # replace ordinary report ACLs. Public call-export registration is separate.
            run.update(
                created_by=owner.user_id,
                created_by_kind="USER",
                job_id=pending["id"],
                ai_export_access=None if access is None else access.model_dump(mode="json"),
            )
            session.execute(insert(report_run).values(**run))
            rows.append(run)
    own_id, wide_id, ordinary_id = [row["id"] for row in rows]
    cases = [
        (principal, {own_id, wide_id, ordinary_id}),
        (demoted, {own_id, ordinary_id}),
        (replace(principal, id=peer.user_id), {ordinary_id}),
        (replace(principal, kind=PrincipalKind.API_CLIENT), {ordinary_id}),
        (replace(principal, permissions=principal.permissions - {"report.export"}), {ordinary_id}),
        (
            replace(principal, permissions=principal.permissions - {"settings.manage", "ai.use"}),
            {ordinary_id},
        ),
        (
            replace(
                principal,
                permission_scopes={**principal.permission_scopes, "report.export": frozenset()},
            ),
            {ordinary_id},
        ),
    ]
    for reader, expected in cases:
        with tenant_session(reader.db_context, read_only=True) as session:
            assert {
                row["id"] for row in session.execute(runs_statement(reader)).mappings()
            } == expected
            for row in rows:
                if row["id"] in expected:
                    assert run_row(session, reader, row["id"], "report.run")["id"] == row["id"]
                else:
                    for permission in ("report.run", "report.export"):
                        with pytest.raises(Problem) as refused:
                            run_row(session, reader, row["id"], permission)
                        assert refused.value.slug == "not-found"
        for row in rows:
            if row["id"] in expected:
                assert get_job(replace(ctx, principal=reader), row["job_id"]).id == row["job_id"]
            else:
                with pytest.raises(Problem) as refused:
                    get_job(replace(ctx, principal=reader), row["job_id"])
                assert refused.value.slug == "not-found"

    with tenant_session(principal.db_context) as session:
        for replacement in (None, {**own.model_dump(mode="json"), "scope": "TENANT"}):
            with (
                pytest.raises(exc.ProgrammingError, match="permission denied"),
                session.begin_nested(),
            ):
                session.execute(
                    update(report_run)
                    .where(report_run.c.id == own_id)
                    .values(ai_export_access=replacement)
                )
        for malformed in (
            {},
            {**own.model_dump(mode="json"), "actor_id": str(peer.user_id)},
            {**own.model_dump(mode="json"), "version": "1"},
            {**own.model_dump(mode="json"), "extra": True},
            {**own.model_dump(mode="json"), "scope": None},
        ):
            values = report_run_row(RowContext(owner.tenant_id, owner.user_id), session)
            values.update(
                created_by=owner.user_id, created_by_kind="USER", ai_export_access=malformed
            )
            with pytest.raises(exc.IntegrityError), session.begin_nested():
                session.execute(insert(report_run).values(**values))
        assert session.scalar(
            select(report_run.c.ai_export_access).where(report_run.c.id == own_id)
        ) == own.model_dump(mode="json")

    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.report_run NO FORCE ROW LEVEL SECURITY")
            message = _owner_failure(
                connection,
                update(report_run).where(report_run.c.id == own_id).values(ai_export_access=None),
            )
            assert message == "Call export requester binding is immutable"
        finally:
            transaction.rollback()

    with pytest.raises(exc.IntegrityError, match="ck_report_run__0157_empty"):
        command.downgrade(alembic_config(), "0156")
    with committed_db.owner_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM erev.alembic_version")) == "0157"
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(
            select(report_run.c.ai_export_access).where(report_run.c.id == UUID(str(own_id)))
        ) == own.model_dump(mode="json")

    # Revisions commit separately: removing the unused 0158 definition succeeded before
    # 0157 refused loss of the inventory bindings. Restore it for the direct FK guard probe.
    command.upgrade(alembic_config(), "head")
    # Unlike the inventory fixtures above, this row references the public export definition.
    with tenant_session(principal.db_context) as session:
        exported = report_run_row(RowContext(owner.tenant_id, owner.user_id), session)
        exported.update(
            report_code="ai_call_log_export",
            report_version=1,
            created_by=owner.user_id,
            created_by_kind="USER",
            ai_export_access=own.model_dump(mode="json"),
        )
        session.execute(insert(report_run).values(**exported))
    with pytest.raises(exc.IntegrityError, match="fk_report_run__report_definition"):
        command.downgrade(alembic_config(), "0157")
    with committed_db.owner_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM erev.alembic_version")) == "0158"
        assert (
            connection.scalar(
                text(
                    "SELECT tgenabled FROM pg_trigger "
                    "WHERE tgname = 'tg_report_definition__immutable'"
                )
            )
            == "O"
        )
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(
            select(report_run.c.ai_export_access).where(report_run.c.id == exported["id"])
        ) == own.model_dump(mode="json")

    # A refused older downgrade can already have removed newer disposable-history revisions.
    command.upgrade(alembic_config(), "head")
