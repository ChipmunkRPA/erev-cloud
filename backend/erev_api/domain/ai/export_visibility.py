"""SQL authorization for retained call-export runs and their asynchronous jobs."""

from typing import Final

from sqlalchemy import ColumnElement, and_, false, or_

from erev_api.auth.entity_scope import holds_all
from erev_api.auth.principal import Principal
from erev_api.db.tables import report_run
from erev_api.enums import PrincipalKind

CODE: Final = "ai_call_log_export"


def source_permission(principal: Principal) -> str | None:
    """The current source grant, independent of accounting-report run permissions."""
    if "settings.manage" in principal.permissions and holds_all(principal, "settings.manage"):
        return "settings.manage"
    if "ai.use" in principal.permissions and principal.permission_scopes.get("ai.use"):
        return "ai.use"
    return None


def protected() -> ColumnElement[bool]:
    """Missing bindings on the reserved report code must never use ordinary report access."""
    return or_(report_run.c.report_code == CODE, report_run.c.ai_export_access.is_not(None))


def readable(principal: Principal) -> ColumnElement[bool]:
    """Current export/source grants plus the immutable requester and maximum scope."""
    if (
        principal.kind not in {PrincipalKind.USER, PrincipalKind.API_CLIENT}
        or principal.id is None
        or "report.export" not in principal.permissions
        or not principal.permission_scopes.get("report.export")
    ):
        return false()
    administrator = "settings.manage" in principal.permissions and holds_all(
        principal, "settings.manage"
    )
    own_reader = "ai.use" in principal.permissions and bool(
        principal.permission_scopes.get("ai.use")
    )
    scopes = []
    if administrator or own_reader:
        scopes.append("OWN")
    if administrator and holds_all(principal, "report.export"):
        scopes.append("TENANT")
    if not scopes:
        return false()
    binding = report_run.c.ai_export_access
    return and_(
        report_run.c.tenant_id == principal.tenant_id,
        report_run.c.created_by == principal.id,
        report_run.c.created_by_kind == principal.kind.value,
        binding["version"].astext == "1",
        binding["tenant_id"].astext == str(principal.tenant_id),
        binding["actor_id"].astext == str(principal.id),
        binding["actor_kind"].astext == principal.kind.value,
        binding["scope"].astext.in_(scopes),
    )
