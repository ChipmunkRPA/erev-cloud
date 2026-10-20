"""Admit and execute a fenced asynchronous deal preview under its human requester's grants."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db import new_id
from erev_api.db.tables import deal_preview
from erev_api.domain.ai.access import AIAccessRefused, job_requester
from erev_api.domain.forecast import deal_bundle
from erev_api.domain.forecast import deal_preview as previews
from erev_api.domain.reports import framework
from erev_api.enums import JobKind, PrincipalKind
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.problems import Problem
from erev_api.schemas.deal_previews import DealInputIn, DealPreviewRequestedOut
from erev_api.uow import UnitOfWork


def request(uow: UnitOfWork, proposal: DealInputIn) -> DealPreviewRequestedOut:
    if uow.principal.kind != PrincipalKind.USER:
        raise Problem("forbidden")
    deal_bundle.authorize(uow, proposal)
    identity = new_id()
    pending = uow.defer(
        JobKind.DEAL_PREVIEW,
        {"preview_id": str(identity), "input": proposal.model_dump(mode="json")},
        subject_type="deal_preview",
        subject_id=identity,
    )
    uow.audit(
        action="deal_preview.request",
        object_type="deal_preview",
        object_id=identity,
        after={"job_id": str(pending["id"]), "input": proposal.model_dump(mode="json")},
    )
    return DealPreviewRequestedOut(
        **framework._job_out(uow.session, pending["id"]).model_dump(), preview_id=identity
    )


def cancel_guard(uow: UnitOfWork, params: Mapping[str, Any], job_id: UUID) -> None:
    if uow.session.scalar(
        select(deal_preview.c.id).where(deal_preview.c.id == UUID(str(params["preview_id"])))
    ):
        raise Problem("invalid-transition", "The preview has already been retained.")


@task(JobKind.DEAL_PREVIEW, retry=RetryPolicy(max_attempts=1), cancel_guard=cancel_guard)
def run(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    identity = UUID(str(params["preview_id"]))
    proposal = DealInputIn.model_validate(params["input"])
    with jc.unit_of_work() as uow:
        try:
            actor = job_requester(jc, uow.session, kind=JobKind.DEAL_PREVIEW)
        except AIAccessRefused as exc:
            raise Problem("forbidden") from exc
    jc.heartbeat()
    if jc.cancel_requested():
        return JobOutcome(state="SUCCEEDED", result={"cancelled": True})
    with system_unit_of_work(jc.runtime, actor, request_id=f"job-{jc.job_id}-deal") as uow:
        row = previews.retain(uow, proposal, identity)
        jc.heartbeat()
        if jc.cancel_requested():
            return JobOutcome(state="SUCCEEDED", result={"cancelled": True})
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "preview_id": str(identity),
            "href": f"/api/v1/deal-previews/{identity}",
            "input_sha256": row["input_sha256"],
            "result_sha256": row["result_sha256"],
        },
    )
