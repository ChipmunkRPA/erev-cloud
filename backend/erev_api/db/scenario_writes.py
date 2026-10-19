"""Scenario read-only gate, shared by HTTP commands and worker business transactions.

Resolve only the current sandbox's parent and its exact scenario pointer. The temporary
source context is restored before returning; no source business data is returned. A shared
lock on that pointer serializes admitted writes against the source archive command.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.session import DbContext, set_tenant_context, tenant_session
from erev_api.db.tables import scenario, tenant
from erev_api.problems import Problem, ProblemError


def require_writable(session: Session, context: DbContext, *, lock: bool = True) -> None:
    current = session.execute(
        select(tenant.c.kind, tenant.c.source_tenant_id).where(tenant.c.id == context.tenant_id)
    ).one_or_none()
    if current is None or current.kind != "sandbox" or current.source_tenant_id is None:
        return
    parent = DbContext(
        tenant_id=UUID(str(current.source_tenant_id)), user_id=context.user_id, entity_scope="*"
    )
    statement = select(scenario.c.status).where(
        scenario.c.tenant_id == parent.tenant_id, scenario.c.scenario_tenant_id == context.tenant_id
    )
    if lock:
        statement = statement.with_for_update(read=True)
    set_tenant_context(session, parent)
    try:
        status = session.execute(statement).scalar_one_or_none()
    finally:
        set_tenant_context(session, context)
    if status == "ARCHIVED":
        raise Problem(
            "invalid-transition",
            "This scenario is archived and read-only.",
            errors=[
                ProblemError(
                    field=None,
                    rule_id="SCENARIO_ARCHIVED",
                    message="Archived scenarios cannot be changed.",
                )
            ],
        )


def check_command(context: DbContext) -> None:
    """Check before replay; the business transaction checks again with a lock."""
    with tenant_session(context, read_only=True) as session:
        require_writable(session, context, lock=False)
