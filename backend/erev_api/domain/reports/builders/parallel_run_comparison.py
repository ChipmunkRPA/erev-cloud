"""RPT-42 report pipeline adapter with retained-input reruns and current authorization."""

from typing import Final
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.reports import parallel_inputs
from erev_api.domain.reports.builders import RETAINED, ReportParams
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "parallel_run_comparison"
BINDING: Final = "parallel_comparison_inputs"


def require_access(uow: UnitOfWork, params: ReportParams) -> None:
    actor = uow.principal if params.requester is None else params.requester.principal
    scope = actor.permission_scopes.get("report.run")
    if (
        actor.tenant_id != uow.principal.tenant_id
        or "report.run" not in actor.permissions
        or not scope
        or not params.entity_ids
        or (scope != "*" and not set(params.entity_ids) <= scope)
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
        raise Problem("validation-failed", "Invalid parallel comparison parameters.")
    try:
        migration_id = UUID(str(params.parameters["migration_id"]))
        scope = parallel_inputs.context(
            tenant_id=uow.principal.tenant_id,
            migration_id=migration_id,
            entity_ids=params.entity_ids,
            known_at=params.known_at,
        )
        selection = {
            key: params.parameters.get(key) for key in ("from_period_key", "to_period_key")
        }
        if params.binding is None:
            facts = parallel_inputs.capture(
                uow,
                migration_id=migration_id,
                entity_ids=params.entity_ids,
                known_at=params.known_at,
                from_period_key=selection["from_period_key"],
                to_period_key=selection["to_period_key"],
                requester=None if params.requester is None else params.requester.principal,
            )
            digest = sha256_hex(facts)
        else:
            binding = params.binding
            if (
                binding.strategy != RETAINED
                or binding.report_version != 1
                or binding.cutoff != params.known_at
                or binding.evidence[BINDING + "_selection"] != selection
            ):
                raise ValueError("binding")
            facts = binding.evidence[BINDING]
            digest = binding.evidence[BINDING + "_sha256"]
        comparison = parallel_inputs.rebuild(facts, expected_sha256=digest, scope=scope)
    except (KeyError, TypeError, ValueError) as error:
        raise Problem(
            "validation-failed", "The parallel comparison source binding is invalid."
        ) from error
    if params.sources is not None:
        params.sources.record_cutoff(params.known_at)
        params.sources.record_evidence(BINDING, facts)
        params.sources.record_evidence(BINDING + "_sha256", digest)
        params.sources.record_evidence(BINDING + "_selection", selection)
    return comparison.data
