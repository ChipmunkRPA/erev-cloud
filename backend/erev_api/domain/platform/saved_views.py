"""Saved grid views and favourites (04 API-R-16, T-PLT-37; SCREENS SCR-IA-07, SCR-IA-08; REQ-UX-009,
REQ-UX-017; BUILD_SPEC PLF-21).

Every view belongs to the caller's membership. The list holds the caller's views and the views other
members share; only the owner changes or deletes a view, and another member's view is 404
``not-found``. A name is unique per membership and screen code (``ux_saved_view__name``). A
favourite carries ``config {target, path, label}`` (SCR-IA-08). Saved views are AUD-OPS: no audit
event.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, delete, insert, or_, select, update
from sqlalchemy.orm import Session

from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import saved_view
from erev_api.domain.platform import provisioning, users
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.uow import UnitOfWork

NO_MEMBERSHIP: Final = "Only a workspace member has saved views."
NAME_TAKEN: Final = "You already have a view with this name on this screen."
FAVOURITE_CONFIG: Final = (
    "A favourite needs a target (contract, report or saved_view), a path starting with / and a "
    "label."
)
VALUE_REQUIRED: Final = "Send a value or leave the member out."
RULE_SAVED_VIEW: Final = "T-PLT-37"
RULE_FAVOURITE: Final = "SCR-IA-08"
FAVOURITE_TARGETS: Final = frozenset({"contract", "report", "saved_view"})
EDITABLE: Final = ("name", "config", "is_shared", "is_favourite")
SAVED_VIEW_COLUMNS: Final = (
    saved_view.c.id,
    saved_view.c.membership_id,
    saved_view.c.screen_code,
    saved_view.c.name,
    saved_view.c.config,
    saved_view.c.is_shared,
    saved_view.c.is_favourite,
    saved_view.c.created_at,
    saved_view.c.updated_at,
    saved_view.c.row_version,
)


def _membership_id(principal: Principal) -> UUID:
    if principal.membership_id is None:
        raise Problem("forbidden", NO_MEMBERSHIP)
    return principal.membership_id


def list_saved_views[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the caller's views and the shared views; ``page`` applies the list parameters."""
    membership_id = _membership_id(ctx.principal)
    statement = select(*SAVED_VIEW_COLUMNS).where(
        or_(saved_view.c.membership_id == membership_id, saved_view.c.is_shared.is_(True))
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, statement)


def _read(session: Session, view_id: UUID) -> Mapping[str, Any]:
    row = session.execute(select(*SAVED_VIEW_COLUMNS).where(saved_view.c.id == view_id)).mappings()
    return MappingProxyType(dict(row.one()))


def _validate(
    session: Session,
    *,
    membership_id: UUID,
    screen_code: str,
    name: str,
    config: Mapping[str, Any],
    is_favourite: bool,
    exclude_id: UUID | None = None,
) -> str:
    """The trimmed name, or 422 with every finding: name length and uniqueness, favourite config."""
    errors: list[ProblemError] = []
    label = name.strip()
    if len(label) not in provisioning.LABEL_LENGTH:
        errors.append(
            ProblemError(field="name", rule_id=RULE_SAVED_VIEW, message=users.NAME_LENGTH)
        )
    else:
        taken = select(saved_view.c.id).where(
            saved_view.c.membership_id == membership_id,
            saved_view.c.screen_code == screen_code,
            saved_view.c.name == label,
        )
        if exclude_id is not None:
            taken = taken.where(saved_view.c.id != exclude_id)
        if session.execute(taken.limit(1)).first() is not None:
            errors.append(ProblemError(field="name", rule_id=RULE_SAVED_VIEW, message=NAME_TAKEN))
    if is_favourite:
        target, path, text = config.get("target"), config.get("path"), config.get("label")
        if not (
            target in FAVOURITE_TARGETS
            and isinstance(path, str)
            and path.startswith("/")
            and isinstance(text, str)
            and text.strip()
        ):
            errors.append(
                ProblemError(field="config", rule_id=RULE_FAVOURITE, message=FAVOURITE_CONFIG)
            )
    if errors:
        raise Problem("validation-failed", errors=errors)
    return label


def create_saved_view(
    uow: UnitOfWork,
    *,
    screen_code: str,
    name: str,
    config: Mapping[str, Any],
    is_shared: bool,
    is_favourite: bool,
) -> Mapping[str, Any]:
    """Save a view or a favourite of the caller's membership."""
    principal = uow.principal
    membership_id = _membership_id(principal)
    label = _validate(
        uow.session,
        membership_id=membership_id,
        screen_code=screen_code,
        name=name,
        config=config,
        is_favourite=is_favourite,
    )
    view_id = new_id()
    uow.session.execute(
        insert(saved_view).values(
            tenant_id=principal.tenant_id,
            id=view_id,
            membership_id=membership_id,
            screen_code=screen_code,
            name=label,
            config=dict(config),
            is_shared=is_shared,
            is_favourite=is_favourite,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    return _read(uow.session, view_id)


def _lock_own(uow: UnitOfWork, view_id: UUID) -> Mapping[str, Any]:
    membership_id = _membership_id(uow.principal)
    row = (
        uow.session.execute(
            select(*SAVED_VIEW_COLUMNS)
            .where(saved_view.c.id == view_id, saved_view.c.membership_id == membership_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def update_saved_view(
    uow: UnitOfWork, view_id: UUID, changes: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Change the name, config, sharing or favourite flag of one of the caller's views."""
    current = _lock_own(uow, view_id)
    missing = [key for key in EDITABLE if key in changes and changes[key] is None]
    if missing:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field=key, rule_id=RULE_SAVED_VIEW, message=VALUE_REQUIRED)
                for key in missing
            ],
        )
    merged = {key: changes[key] if key in changes else current[key] for key in EDITABLE}
    label = _validate(
        uow.session,
        membership_id=current["membership_id"],
        screen_code=current["screen_code"],
        name=str(merged["name"]),
        config=merged["config"],
        is_favourite=bool(merged["is_favourite"]),
        exclude_id=view_id,
    )
    values = {**merged, "name": label}
    changed = {key: value for key, value in values.items() if value != current[key]}
    if changed:
        principal = uow.principal
        uow.session.execute(
            update(saved_view)
            .where(saved_view.c.id == view_id)
            .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
        )
    return _read(uow.session, view_id)


def delete_saved_view(uow: UnitOfWork, view_id: UUID) -> None:
    """Delete one of the caller's views (T-PLT-37 allows DELETE)."""
    _lock_own(uow, view_id)
    uow.session.execute(delete(saved_view).where(saved_view.c.id == view_id))
