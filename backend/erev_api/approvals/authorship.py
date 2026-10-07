"""People who authored stored drafts, independently of who submitted them.

The creator is durable on the subject row. Content edits and SYSTEM writes on behalf of an
uploader are attributed by successful, immutable audit events; lifecycle/preview actions do not
make someone an author. The approval kernel reads these exclusions under tenant SYSTEM scope and
applies them to both the deciding user and the person represented by a delegation.
"""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from erev_api.db.tables import audit_event
from erev_api.enums import AuditOutcome, PrincipalKind

AUTHOR_DETAIL = "You authored this draft, so another user must approve it."


def draft_authors(
    table: Table, *, edit_actions: tuple[str, ...] = ()
) -> Callable[[Session, UUID], frozenset[UUID]]:
    """Build the exclusion reader for a stored draft and its content-writing actions."""

    def read(session: Session, subject_id: UUID) -> frozenset[UUID]:
        row = session.execute(
            select(table.c.created_by, table.c.created_by_kind).where(table.c.id == subject_id)
        ).one_or_none()
        people: set[UUID] = set()
        if (
            row is not None
            and row.created_by is not None
            and row.created_by_kind == PrincipalKind.USER
        ):
            people.add(UUID(str(row.created_by)))
        # Imports may create drafts as SYSTEM on behalf of their uploader. Preserve that
        # authorship as well as editors; lifecycle stamps cannot recover it after submission.
        actors = session.execute(
            select(audit_event.c.actor_id, audit_event.c.actor_kind, audit_event.c.on_behalf_of_id)
            .distinct()
            .where(
                audit_event.c.object_type == table.name,
                audit_event.c.object_id == subject_id,
                audit_event.c.action.in_((f"{table.name}.create", *edit_actions)),
                audit_event.c.outcome == AuditOutcome.SUCCESS.value,
            )
        )
        for actor in actors:
            if actor.actor_id is not None and actor.actor_kind == PrincipalKind.USER:
                people.add(UUID(str(actor.actor_id)))
            if actor.on_behalf_of_id is not None:
                people.add(UUID(str(actor.on_behalf_of_id)))
        return frozenset(people)

    return read
