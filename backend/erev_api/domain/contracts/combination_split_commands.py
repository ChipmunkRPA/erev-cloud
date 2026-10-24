"""Approve effective split events without discarding the original calculation history."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.approvals import engine as approvals
from erev_api.db import transitions
from erev_api.db.tables import contract, judgement_record
from erev_api.domain.contracts import combination as commands
from erev_api.domain.contracts import combination_split, repo
from erev_api.domain.contracts.compute_job import compute_group
from erev_api.domain.reports.computation_sources import read_for_report
from erev_api.enums import ApprovalSubjectType, ComputationStatus
from erev_api.events.payloads import CombinationChangedV1
from erev_api.problems import Problem
from erev_api.schemas.combinations import CombinationGroupDetailOut, CombinationGroupSubmitIn
from erev_api.uow import UnitOfWork
from erev_engine import compute
from erev_engine.bundle import InputBundle
from erev_engine.combination_split import prepare
from erev_engine.combination_split_balances import preview_input
from erev_engine.errors import EngineError


def _plans(
    bundle: InputBundle,
    effective_date: date,
    destinations: Mapping[str, str],
    *,
    event_key: str | None = None,
) -> dict[str, Any]:
    plans = {}
    for book in bundle.books:
        plan = prepare(
            bundle,
            book_code=book.book_code,
            effective_date=effective_date if event_key is None else None,
            event_key=event_key,
            destinations=destinations,
        )
        plans[book.book_code] = {
            "recognized_minor": plan.recognized_minor,
            "unrecognized_minor": plan.unrecognized_minor,
            "members": [
                {
                    "contract": m.contract_key,
                    "destination": m.destination,
                    "recognized_minor": m.recognized_minor,
                    "remaining_after_minor": m.remaining_after_minor,
                    "remaining_ssp": str(m.remaining_ssp),
                    "obligation_shares": dict(m.obligation_shares),
                }
                for m in plan.members
            ],
        }
    return plans


def submit(
    uow: UnitOfWork, group_id: UUID, body: CombinationGroupSubmitIn
) -> CombinationGroupDetailOut:
    assert body.split_effective_date is not None
    group = repo.read_group(uow.session, group_id)
    ids = list(
        uow.session.execute(
            select(contract.c.id).where(contract.c.combination_group_id == group_id)
        ).scalars()
    )

    def pending(groups: commands.GroupRows) -> None:
        if commands._proposal(uow.session, group_id, lock=True) is not None:
            raise Problem("invalid-transition", "Resolve the pending combination proposal first.")

    groups, rows = commands._visible_contracts(uow, ids, target=group_id, between=pending)
    group = groups[group_id]
    if str(group["status"]) != "APPLIED" or group["is_singleton"]:
        raise Problem(
            "invalid-transition", "Only an applied combination can be split prospectively."
        )
    if (
        not body.leave_contract_ids
        or not body.comment
        or not body.split_input_sha256
        or not body.split_output_sha256
    ):
        raise Problem(
            "validation-failed", "A split requires members, rationale and reviewed source hashes."
        )
    selected = combination_split.preview(
        uow, group_id, body.split_effective_date, body.leave_contract_ids, None
    )
    if (selected.input_sha256, selected.output_sha256) != (
        body.split_input_sha256,
        body.split_output_sha256,
    ):
        raise Problem(
            "precondition-failed", "The split preview is stale. Rebuild it before submitting."
        )
    if body.reason_code is not None:
        raise Problem(
            "validation-failed", "An effective split is not a retrospective data correction."
        )
    original = read_for_report(uow, selected.source_computation_id, permission="contract.read")
    if (original.bundle.evidence_revision or 0) < 54:
        raise Problem(
            "validation-failed", "Recompute with current split evidence before submitting."
        )
    destinations = {m.contract_key: m.destination for m in selected.members}
    try:
        plans = _plans(original.bundle, body.split_effective_date, destinations)
        # All active books must support the same approved event before a request exists.
        compute(
            preview_input(
                original.bundle, effective_date=body.split_effective_date, destinations=destinations
            )
        )
    except (ValueError, EngineError) as error:
        raise Problem("validation-failed", str(error)) from error
    saved = {
        "effective_date": body.split_effective_date.isoformat(),
        "destinations": destinations,
        "source_computation_id": str(selected.source_computation_id),
        "input_sha256": selected.input_sha256,
        "output_sha256": selected.output_sha256,
        "plans": plans,
    }
    record_id = commands._record_proposal(
        uow,
        group_id,
        action="LEAVE",
        contract_rows=rows,
        criterion=None,
        rationale=body.comment,
        extra={"prospective_split": saved},
    )
    commands._submit_record(uow, record_id)
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.COMBINATION_GROUP,
        subject_id=group_id,
        summary=f"Split {group['code']} effective {body.split_effective_date}",
        comment=body.comment,
        reason_code=None,
    )
    if commands._text(request["status"]) == "PENDING":
        transitions.apply(
            uow.session,
            commands.GROUP_OBJECT,
            group_id,
            to_status=None,
            set_values={"approval_request_id": UUID(str(request["id"])), **commands._stamps(uow)},
        )
    return commands.get_group(uow.session, group_id)


def apply(
    uow: UnitOfWork,
    system: UnitOfWork,
    group_id: UUID,
    record_id: UUID,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    saved = uow.session.execute(
        select(judgement_record.c.questionnaire).where(judgement_record.c.id == record_id)
    ).scalar_one()["prospective_split"]
    group = repo.read_group(uow.session, group_id)
    if (
        group["dirty_since"] is not None
        or str(group["head_computation_id"]) != saved["source_computation_id"]
    ):
        raise Problem(
            "precondition-failed", "The split source changed. Rebuild and resubmit its preview."
        )
    original = read_for_report(uow, group["head_computation_id"], permission="contract.read")
    if (original.bundle.sha256(), original.output_sha256) != (
        saved["input_sha256"],
        saved["output_sha256"],
    ):
        raise Problem(
            "precondition-failed", "The split source hashes differ from the approved evidence."
        )
    effective = date.fromisoformat(saved["effective_date"])
    owner = min(saved["destinations"])
    row = next(r for r in rows if r["external_id"] == owner)
    event = commands._change(
        system,
        row,
        CombinationChangedV1(
            combination_group_id=group_id,
            action="LEAVE",
            prospective_split_destinations=saved["destinations"],
        ),
        effective_date=effective,
    )
    commands._dirty(system, group_id)
    for audited in system.drain_audit_events():
        uow.buffer_audit_event(audited)
    # Keep the original envelope and history. The retained event, not an inception
    # correction of the membership table, determines period-end accounting groups.
    outcome = compute_group(uow, group_id)
    if outcome.status != ComputationStatus.SUCCEEDED:
        raise Problem(
            "validation-failed", "The split could not be recomputed; no change was applied."
        )
    head = repo.read_group(uow.session, group_id)["head_computation_id"]
    updated = read_for_report(uow, head, permission="contract.read")
    actual = next(
        e
        for e in updated.bundle.events
        if e.contract_key == owner and e.stream_version == event["stream_version"]
    )
    try:
        plans = _plans(updated.bundle, effective, saved["destinations"], event_key=actual.event_key)
    except (ValueError, EngineError) as error:
        raise Problem("precondition-failed", str(error)) from error
    if plans != saved["plans"]:
        raise Problem(
            "precondition-failed", "The applied split basis differs from the approved preview."
        )
