"""Authorized call-evidence dataset for the queued CSV/XLSX export integration.

Read using the caller's current context, never a worker's unrestricted system principal.
No public export route or retained-file authorization is implied by this builder.
"""

from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from pydantic import BaseModel, ConfigDict

from erev_api.auth.entity_scope import holds_all
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log
from erev_api.domain.ai.queries import model_log_statement
from erev_api.domain.platform import actors
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.ai import AIModelLogOut

if TYPE_CHECKING:
    from erev_api.domain.reports.builders import ReportParams
    from erev_api.uow import UnitOfWork


COLUMNS: Final = (
    Column("id", "Call id", "code"),
    Column("created_at", "Called", "timestamp"),
    Column("created_by", "User", "actor"),
    Column("provider", "Provider", "text"),
    Column("model_id", "Model", "text"),
    Column("prompt_template_id", "Template", "text"),
    Column("prompt_template_version", "Template version", "text"),
    Column("outcome", "Outcome", "code"),
    Column("usage_known", "Usage known", "boolean"),
    Column("input_tokens", "Input tokens", "integer", empty_text="Unknown"),
    Column("output_tokens", "Output tokens", "integer", empty_text="Unknown"),
    Column("latency_ms", "Latency (ms)", "integer"),
    Column("input_sha256", "Input SHA-256", "code"),
    Column("response_sha256", "Response SHA-256", "code"),
    Column("parameters", "Parameters", "text"),
    Column("error_detail", "Error", "text"),
)


class ExportAccess(BaseModel):
    """Server-captured identity and maximum disclosure scope, retained with the queued export."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    tenant_id: UUID
    actor_id: UUID
    actor_kind: Literal["USER", "API_CLIENT"]
    scope: Literal["OWN", "TENANT"]


def _identity(ctx: RequestContext) -> None:
    if (
        ctx.principal.kind not in {PrincipalKind.USER, PrincipalKind.API_CLIENT}
        or ctx.principal.id is None
    ):
        raise Problem("forbidden", "Call export requires the current caller's identity.")


def _administrator(ctx: RequestContext) -> bool:
    return "settings.manage" in ctx.principal.permissions and holds_all(
        ctx.principal, "settings.manage"
    )


def _own_reader(ctx: RequestContext) -> bool:
    return "ai.use" in ctx.principal.permissions and bool(
        ctx.principal.permission_scopes.get("ai.use")
    )


def capture_access(ctx: RequestContext) -> ExportAccess:
    """Capture on submission, never from client-selected actor/scope fields."""
    _identity(ctx)
    principal = ctx.principal
    if not _administrator(ctx) and not _own_reader(ctx):
        raise Problem("forbidden")
    _require_export_permission(ctx, workspace_wide=_administrator(ctx))
    assert principal.id is not None
    return ExportAccess(
        tenant_id=principal.tenant_id,
        actor_id=principal.id,
        actor_kind="USER" if principal.kind is PrincipalKind.USER else "API_CLIENT",
        scope="TENANT" if _administrator(ctx) else "OWN",
    )


def _require_export_permission(ctx: RequestContext, *, workspace_wide: bool) -> None:
    principal = ctx.principal
    if (
        "report.export" not in principal.permissions
        or not principal.permission_scopes.get("report.export")
        or (workspace_wide and not holds_all(principal, "report.export"))
    ):
        raise Problem("forbidden", "Call export permission is required for the requested scope.")


def require_access(ctx: RequestContext, access: ExportAccess) -> None:
    """Recheck on build, replay and every stored-output read, before selecting any content."""
    _identity(ctx)
    principal = ctx.principal
    if (
        principal.tenant_id != access.tenant_id
        or principal.id != access.actor_id
        or principal.kind.value != access.actor_kind
    ):
        raise Problem("not-found")
    if not _administrator(ctx) and (access.scope == "TENANT" or not _own_reader(ctx)):
        raise Problem("forbidden")
    _require_export_permission(ctx, workspace_wide=access.scope == "TENANT")


def dataset(ctx: RequestContext, access: ExportAccess) -> ReportData:
    """One statement snapshot, newest first, with the same owner/tenant visibility as the API.

    Unknown counters are empty values, with an explicit usage-known column. Control totals
    distinguish known counters from unknown call count; they never assert complete usage.
    The standard writers supply spreadsheet-formula escaping and output run stamps.
    """
    require_access(ctx, access)
    statement = model_log_statement(ctx).order_by(
        ai_model_log.c.created_at.desc(), ai_model_log.c.id.desc()
    )
    if access.scope == "OWN":
        # A later administrator grant must not widen the original export request.
        statement = statement.where(
            ai_model_log.c.created_by == access.actor_id,
            ai_model_log.c.created_by_kind == access.actor_kind,
        )
    rows: list[dict[str, Any]] = []
    unknown = input_tokens = output_tokens = 0
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        for record in session.execute(statement).mappings():
            value = dict(record)
            value["created_by"] = actors.actor(
                record["created_by"], record["created_by_kind"], record["creator"]
            )
            # Explicit API schema strips storage-only fields and preserves its evidence contract.
            evidence = AIModelLogOut.model_validate(value)
            row = evidence.model_dump()
            row["id"] = str(evidence.id)
            row["row_key"] = "ai-call:" + str(evidence.id)
            row["parameters"] = canonical_bytes(evidence.parameters).decode("utf-8")
            if evidence.usage_known:
                input_tokens += evidence.input_tokens
                output_tokens += evidence.output_tokens
            else:
                unknown += 1
                row["input_tokens"] = row["output_tokens"] = None
            rows.append(row)
    return ReportData(
        columns=COLUMNS,
        rows=tuple(rows),
        control_totals={
            "row_count": len(rows),
            "unknown_usage_calls": unknown,
            "known_input_tokens": input_tokens,
            "known_output_tokens": output_tokens,
        },
    )


def build(uow: "UnitOfWork", params: "ReportParams") -> ReportData:
    """Registered report builder; the worker must supply its reauthorized requester context."""
    if params.requester is None or params.access_binding is None:
        raise Problem("forbidden", "Call export requires a reauthorized requester.")
    return dataset(params.requester, ExportAccess.model_validate(params.access_binding))
