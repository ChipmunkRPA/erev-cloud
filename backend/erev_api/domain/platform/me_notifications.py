"""The caller's notifications and notification preferences (04 API-R-03, §16.12, T-PLT-24,
T-PLT-25; PRD §5.4 NTF-R2; SCREENS SCR-IA-06 bindings; SCREENS_B SF-15 notification preferences).

Every read and command acts on the caller's own membership in the active tenant. A principal
without a membership (an API client) is refused with 403 ``forbidden``, and another member's
notification is 404 ``not-found``. Notifications and preferences are AUD-OPS, so no audit event is
written.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import notification, notification_preference
from erev_api.db.transitions import apply
from erev_api.enums import NotificationKind
from erev_api.events.notifications import EMAIL_DEFAULTS, MANDATORY_KINDS
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.uow import UnitOfWork

NO_MEMBERSHIP: Final = "Only a workspace member has notifications."
# SCREENS_B SF-15: the tooltip of the CHAIN_VERIFICATION_FAILED switches (NTF-R2).
MANDATORY_MESSAGE: Final = "Audit chain failures are always sent in the app and by email."
DUPLICATE_MESSAGE: Final = "Send each notification kind once."
RULE_MANDATORY: Final = "NTF-R2"
RULE_ITEMS: Final = "API-R-03"
NOTIFICATION_COLUMNS: Final = (
    notification.c.id,
    notification.c.kind,
    notification.c.subject_type,
    notification.c.subject_id,
    notification.c.title,
    notification.c.body,
    notification.c.link_path,
    notification.c.read_at,
    notification.c.created_at,
)


def _membership_id(principal: Principal) -> UUID:
    if principal.membership_id is None:
        raise Problem("forbidden", NO_MEMBERSHIP)
    return principal.membership_id


def list_notifications[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the caller's notifications; ``page`` applies the list parameters (DG-LST)."""
    membership_id = _membership_id(ctx.principal)
    statement = select(*NOTIFICATION_COLUMNS).where(
        notification.c.recipient_membership_id == membership_id
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, statement)


def mark_read(uow: UnitOfWork, notification_id: UUID) -> Mapping[str, Any]:
    """Set ``read_at`` once; a notification already read is returned unchanged."""
    membership_id = _membership_id(uow.principal)
    row = (
        uow.session.execute(
            select(*NOTIFICATION_COLUMNS)
            .where(
                notification.c.id == notification_id,
                notification.c.recipient_membership_id == membership_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if row["read_at"] is not None:
        return MappingProxyType(dict(row))
    updated = apply(
        uow.session,
        "notification",
        notification_id,
        to_status=None,
        set_values={"read_at": uow.now},
    )
    return MappingProxyType({column.name: updated[column.name] for column in NOTIFICATION_COLUMNS})


def read_all(uow: UnitOfWork, *, before: datetime) -> int:
    """04 §16.12: mark read the caller's unread notifications created at or before ``before``."""
    membership_id = _membership_id(uow.principal)
    marked = uow.session.execute(
        update(notification)
        .where(
            notification.c.recipient_membership_id == membership_id,
            notification.c.read_at.is_(None),
            notification.c.created_at <= before,
        )
        .values(read_at=uow.now)
        .returning(notification.c.id)
    ).all()
    return len(marked)


def preferences(session: Session, membership_id: UUID) -> list[Mapping[str, Any]]:
    """One entry per E-69 kind in 04 order; a kind without a stored row shows the defaults."""
    stored = {
        NotificationKind(row.kind): (bool(row.in_app), bool(row.email))
        for row in session.execute(
            select(
                notification_preference.c.kind,
                notification_preference.c.in_app,
                notification_preference.c.email,
            ).where(notification_preference.c.membership_id == membership_id)
        )
    }
    entries: list[Mapping[str, Any]] = []
    for kind in NotificationKind:
        in_app, email = stored.get(kind, (True, EMAIL_DEFAULTS[kind]))
        entries.append(MappingProxyType({"kind": kind.value, "in_app": in_app, "email": email}))
    return entries


def get_preferences(ctx: RequestContext) -> list[Mapping[str, Any]]:
    membership_id = _membership_id(ctx.principal)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return preferences(session, membership_id)


def put_preferences(
    uow: UnitOfWork, items: Sequence[tuple[NotificationKind, bool, bool]]
) -> list[Mapping[str, Any]]:
    """Store (kind, in_app, email) entries and return every preference.

    Each kind may appear once, and ``CHAIN_VERIFICATION_FAILED`` cannot be turned off in the app or
    by email (NTF-R2): both give 422 ``validation-failed`` with one error per offending field
    before anything is written.
    """
    membership_id = _membership_id(uow.principal)
    errors: list[ProblemError] = []
    seen: set[NotificationKind] = set()
    for index, (kind, in_app, email) in enumerate(items):
        if kind in seen:
            errors.append(
                ProblemError(
                    field=f"items[{index}].kind", rule_id=RULE_ITEMS, message=DUPLICATE_MESSAGE
                )
            )
        seen.add(kind)
        if kind in MANDATORY_KINDS:
            errors += [
                ProblemError(
                    field=f"items[{index}].{name}",
                    rule_id=RULE_MANDATORY,
                    message=MANDATORY_MESSAGE,
                )
                for name, value in (("in_app", in_app), ("email", email))
                if not value
            ]
    if errors:
        raise Problem("validation-failed", errors=errors)
    principal = uow.principal
    for kind, in_app, email in items:
        statement = insert(notification_preference).values(
            tenant_id=principal.tenant_id,
            id=new_id(),
            membership_id=membership_id,
            kind=NotificationKind(kind).value,
            in_app=in_app,
            email=email,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
        excluded = statement.excluded
        uow.session.execute(
            statement.on_conflict_do_update(
                index_elements=["tenant_id", "membership_id", "kind"],
                set_={
                    "in_app": excluded.in_app,
                    "email": excluded.email,
                    "updated_at": excluded.updated_at,
                    "updated_by": excluded.updated_by,
                    "updated_by_kind": excluded.updated_by_kind,
                },
            )
        )
    return preferences(uow.session, membership_id)
