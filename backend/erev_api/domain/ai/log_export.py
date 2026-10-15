"""Authorized call-evidence dataset for the queued CSV/XLSX export integration.

Read using the caller's current context, never a worker's unrestricted system principal.
No public export route or retained-file authorization is implied by this builder.
"""

from typing import Any, Final

from erev_engine.canonical import canonical_bytes

from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log
from erev_api.domain.ai.queries import model_log_statement
from erev_api.domain.platform import actors
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.ai import AIModelLogOut

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


def dataset(ctx: RequestContext) -> ReportData:
    """One statement snapshot, newest first, with the same owner/tenant visibility as the API.

    Unknown counters are empty values, with an explicit usage-known column. Control totals
    distinguish known counters from unknown call count; they never assert complete usage.
    The standard writers supply spreadsheet-formula escaping and output run stamps.
    """
    if (
        ctx.principal.kind not in {PrincipalKind.USER, PrincipalKind.API_CLIENT}
        or ctx.principal.id is None
    ):
        raise Problem("forbidden", "Call export requires the current caller's identity.")
    statement = model_log_statement(ctx).order_by(
        ai_model_log.c.created_at.desc(), ai_model_log.c.id.desc()
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
