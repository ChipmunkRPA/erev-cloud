"""Workspace settings of the active tenant (04 API-R-04 ``GET, PATCH /tenant``, T-PLT-01, DB-05,
API-C-08; PRD ERR-26; SCREENS_B SF-23 data bindings; BUILD_SPEC PLF-21).

``update_tenant`` changes ``display_name`` and ``default_locale`` of the locked row under the
``If-Match`` precondition. A request naming ``kind`` is refused with 409 ``tenant-kind-immutable``
before anything is written; DB-05 guards the column as well. A change is AUD-CMD: one
``tenant.update`` event with the changed columns before and after (SPEC-Q-186).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.db.session import tenant_session
from erev_api.db.tables import tenant
from erev_api.domain.platform import provisioning, sandboxes, users
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import RequestContext
    from erev_api.uow import UnitOfWork

OBJECT_TYPE: Final = "tenant"
UPDATE_ACTION: Final = "tenant.update"
RULE_TENANT: Final = "T-PLT-01"
# PRD ERR-26.
KIND_IMMUTABLE: Final = "A workspace's type is fixed when it is created."
LOCALE_MESSAGE: Final = "Use a BCP 47 language tag such as en-US."
VALUE_REQUIRED: Final = "Send a value or leave the member out."
LOCALE_TAG: Final = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
# The T-PLT-01 row as API-S-Tenant serves it; the HMAC key identifier stays internal.
TENANT_COLUMNS: Final = (
    tenant.c.id,
    tenant.c.code,
    tenant.c.kind,
    tenant.c.status,
    tenant.c.display_name,
    tenant.c.reporting_currency,
    tenant.c.source_tenant_id,
    tenant.c.source_known_at,
    tenant.c.is_demo,
    tenant.c.industry_cluster,
    tenant.c.default_locale,
    tenant.c.setup_completed_at,
    tenant.c.ai_disabled_at,
    tenant.c.ai_disabled_by,
    tenant.c.ai_disabled_by_kind,
    tenant.c.created_at,
    tenant.c.created_by,
    tenant.c.created_by_kind,
    tenant.c.updated_at,
    tenant.c.updated_by,
    tenant.c.updated_by_kind,
    tenant.c.row_version,
)


def _row(session: Session, tenant_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    statement = select(*TENANT_COLUMNS).where(tenant.c.id == tenant_id)
    if lock:
        statement = statement.with_for_update()
    row = dict(session.execute(statement).mappings().one())
    # 04 §16.14 rev 1.125: a loaded sandbox's facts, read from its own summary event
    row["sandbox_load"] = sandboxes.sandbox_load_of(session, row)
    return MappingProxyType(row)


def get_tenant(ctx: RequestContext) -> Mapping[str, Any]:
    """The active tenant's row."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return _row(session, ctx.principal.tenant_id)


def update_tenant(
    uow: UnitOfWork,
    *,
    changes: Mapping[str, Any],
    kind_requested: bool,
    check_version: Callable[[int], None],
) -> Mapping[str, Any]:
    """``PATCH /tenant``: apply ``display_name`` and ``default_locale`` from ``changes``;
    ``check_version`` applies the ``If-Match`` precondition to the locked row."""
    tenant_id = uow.principal.tenant_id
    session = uow.session
    current = _row(session, tenant_id, lock=True)
    check_version(int(current["row_version"]))
    if kind_requested:
        raise Problem("tenant-kind-immutable", KIND_IMMUTABLE)
    errors: list[ProblemError] = []
    values: dict[str, Any] = {}
    if "display_name" in changes:
        name = changes["display_name"]
        label = name.strip() if isinstance(name, str) else ""
        if name is None:
            errors.append(
                ProblemError(field="display_name", rule_id=RULE_TENANT, message=VALUE_REQUIRED)
            )
        elif len(label) not in provisioning.LABEL_LENGTH:
            errors.append(
                ProblemError(field="display_name", rule_id=RULE_TENANT, message=users.NAME_LENGTH)
            )
        values["display_name"] = label
    if "default_locale" in changes:
        locale = changes["default_locale"]
        if not isinstance(locale, str) or LOCALE_TAG.fullmatch(locale) is None:
            errors.append(
                ProblemError(field="default_locale", rule_id=RULE_TENANT, message=LOCALE_MESSAGE)
            )
        values["default_locale"] = locale
    if errors:
        raise Problem("validation-failed", errors=errors)
    changed = {key: value for key, value in values.items() if value != current[key]}
    if not changed:
        return current
    principal = uow.principal
    session.execute(
        update(tenant)
        .where(tenant.c.id == tenant_id)
        .values(**changed, updated_by=principal.id, updated_by_kind=principal.kind.value)
    )
    uow.audit(
        action=UPDATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=tenant_id,
        before={key: current[key] for key in changed},
        after=changed,
    )
    return _row(session, tenant_id)
