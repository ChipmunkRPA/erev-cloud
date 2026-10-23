"""Phased RPT-38 builder: authorize/read, compute without SQL, reauthorize/publish."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.reports.builders import ADAPTER, ReportParams
from erev_api.domain.reports.outputs import ReportData
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.domain.reports import variance_presentation, variance_sources
    from erev_api.domain.reports.variance_replay import Engine

CODE: Final = "variance_between_closes"
BINDING: Final = "close_variance_sources"


@dataclass(frozen=True)
class Prepared:
    pair: variance_sources.Pair
    identity: dict[str, Any]
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction"


@dataclass(frozen=True)
class Calculated:
    identity: dict[str, Any]
    presentation: variance_presentation.Presentation


def _invalid() -> Problem:
    return Problem("validation-failed", "The close variance source binding is invalid.")


def prepare(uow: UnitOfWork, params: ReportParams) -> Prepared:
    from erev_api.domain.reports import variance_sources

    view = params.parameters.get("currency_view", "transaction")
    if view not in ("transaction", "functional", "reporting"):
        raise Problem(
            "validation-failed",
            "Close variance supports transaction, functional or reporting currency.",
        )

    if (
        params.report_code != CODE
        or params.report_version != 1
        or params.period_lock_id
        or params.filters
    ):
        raise _invalid()
    try:
        before = UUID(str(params.parameters["from_period_lock_id"]))
        after = UUID(str(params.parameters["to_period_lock_id"]))
    except (KeyError, ValueError, TypeError) as error:
        raise _invalid() from error
    reader = (
        uow
        if params.requester is None
        else UnitOfWork(
            ctx=params.requester,
            session=uow.session,
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
        )
    )
    pair = variance_sources.read_pair(
        reader, from_period_lock_id=before, to_period_lock_id=after, entity_ids=params.entity_ids
    )
    if not set(pair.required_entity_ids) <= set(params.entity_ids):
        raise Problem("forbidden", "The report scope must include every source computation entity.")
    if params.book_code is not None and params.book_code != pair.earlier.frozen.scope.book_code:
        raise _invalid()
    if any(
        side.frozen.record["created_at"] > params.known_at for side in (pair.earlier, pair.later)
    ):
        raise Problem(
            "validation-failed", "The selected lock was not available at the report cutoff."
        )
    sides = []
    for side in (pair.earlier, pair.later):
        sides.append(
            {
                "lock_id": str(side.frozen.scope.lock_id),
                "snapshot_manifest_sha256": side.frozen.record["snapshot_manifest_sha256"],
                "contracts": {
                    name: str(identity)
                    for name, identity in sorted(side.contract_computations.items())
                },
                "computations": {
                    str(identity): {
                        "input_sha256": source.bundle.sha256(),
                        "output_sha256": source.output_sha256,
                        "known_at": source.bundle.known_at.isoformat(),
                        "engine_release_id": str(source.engine_release_id),
                        "group_id": str(source.group_id),
                    }
                    for identity, source in sorted(
                        side.computations.items(), key=lambda item: str(item[0])
                    )
                },
            }
        )
    identity = {
        "version": 1,
        "sides": sides,
        "required_entity_ids": [str(item) for item in pair.required_entity_ids],
    }
    if view != "transaction":
        identity["currency_view"] = view
    # New reports retain offset evidence; bound older reports keep their row population.
    if (
        params.binding is None
        or params.binding.evidence.get(BINDING, {}).get("offset_details") is True
    ):
        identity["offset_details"] = True
    if params.binding is not None and (
        params.binding.strategy != ADAPTER
        or params.binding.report_version != params.report_version
        or params.binding.evidence.get(BINDING) != identity
    ):
        raise _invalid()
    return Prepared(pair, identity, view)


def calculate(prepared: Prepared, *, engine: Engine) -> Calculated:
    from erev_api.domain.reports import variance_groups, variance_presentation

    replay = variance_groups.execute(
        prepared.pair, engine=engine, currency_view=prepared.currency_view
    )
    return Calculated(
        prepared.identity,
        variance_presentation.dataset(
            prepared.pair, replay, retain_offsets=prepared.identity.get("offset_details") is True
        ),
    )


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    result = params.execution_result
    if not isinstance(result, Calculated):
        raise Problem(
            "invalid-transition", "Close variance requires transaction-free worker execution."
        )
    current = prepare(uow, params)
    if current.identity != result.identity:
        raise _invalid()
    if params.sources is not None:
        params.sources.record_cutoff(params.known_at)
        params.sources.record_evidence(BINDING, current.identity)
        params.sources.record_evidence("close_variance_contributors", result.presentation.evidence)
        params.sources.record_evidence(
            "close_variance_evidence_sha256", sha256_hex(result.presentation.evidence)
        )
    return result.presentation.data


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    from erev_api.domain.reports import variance_cells

    return variance_cells.cell(session, params, row_key, column_key)
