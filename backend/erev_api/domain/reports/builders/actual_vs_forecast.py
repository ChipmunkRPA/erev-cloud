"""RPT-40 report framework adapter, with current access and retained-fact rebuilding."""

from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.db.session import set_tenant_context
from erev_api.domain.reports import forecast_comparison_inputs as inputs
from erev_api.domain.reports.builders import RETAINED, ReportParams
from erev_api.domain.reports.builders.parallel_run_comparison import require_access as report_access
from erev_api.domain.reports.outputs import ReportData
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE = "actual_vs_forecast"
BINDING = "forecast_comparison_inputs"


def require_access(uow: UnitOfWork, params: ReportParams) -> None:
    report_access(uow, params)
    actor = uow.principal if params.requester is None else params.requester.principal
    if (
        uow.ctx.tenant_kind != TenantKind.SANDBOX
        or actor.kind != PrincipalKind.USER
        or "scenario.use" not in actor.permissions
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    require_access(uow, params)
    if (
        params.report_code != CODE
        or params.report_version != 1
        or params.period_lock_id is not None
        or params.filters
    ):
        raise Problem("validation-failed", "Invalid forecast comparison parameters.")
    try:
        run_id = UUID(str(params.parameters["forecast_run_id"]))
        selection = {
            "row_dimension": params.parameters.get("row_dimension", "CONTRACT"),
            "from_period_key": params.parameters.get("from_period_key"),
            "to_period_key": params.parameters.get("to_period_key"),
        }
        if selection["row_dimension"] not in ("CONTRACT", "REVENUE_CATEGORY"):
            raise ValueError("dimension")
        if params.binding is None:
            original = uow.ctx
            try:
                if params.requester is not None:
                    uow.ctx = params.requester
                    set_tenant_context(uow.session, uow.principal.db_context)
                captured = inputs.read(uow, run_id, **selection)
                facts = captured.evidence
                digest = sha256_hex(facts)
            finally:
                uow.ctx = original
                set_tenant_context(uow.session, original.principal.db_context)
        else:
            binding = params.binding
            if (
                binding.strategy != RETAINED
                or binding.report_version != 1
                or binding.cutoff != params.known_at
            ):
                raise ValueError("binding")
            facts = binding.evidence[BINDING]
            digest = binding.evidence[BINDING + "_sha256"]
        data = inputs.rebuild(
            facts,
            expected_sha256=digest,
            tenant_id=uow.principal.tenant_id,
            forecast_run_id=run_id,
            entity_ids=params.entity_ids,
            book_code=params.book_code,
            currency_view=params.parameters.get("currency_view", "transaction"),
            selection=selection,
            known_at=params.known_at,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise Problem(
            "validation-failed", "The forecast comparison source binding is invalid."
        ) from error
    if params.sources is not None:
        params.sources.record_cutoff(params.known_at)
        params.sources.record_evidence(BINDING, facts)
        params.sources.record_evidence(BINDING + "_sha256", digest)
    return data
