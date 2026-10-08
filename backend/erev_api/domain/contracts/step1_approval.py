"""The live basis and posting-window locks for dated Step 1 approvals."""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.money import minor_to_decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    approval_request,
    contract,
    event_submission,
    judgement_record,
    legal_entity,
    period,
    period_state,
)
from erev_api.domain.close.posting_guard import posts_into_restricted_period
from erev_api.enums import BookCode, FilePurpose
from erev_api.events import step1
from erev_api.events.payloads import CollectibilityAssessedV1, payload_json
from erev_api.events.stream import EventIn
from erev_api.files.store import store_file
from erev_api.money import money_out
from erev_api.periods import POSTABLE_STATES, auto_approval_barred

if TYPE_CHECKING:
    from erev_api.approvals.engine import ImpactPreview
    from erev_api.uow import UnitOfWork


def calculation_sha256(bundle: InputBundle, contract_key: str, head: int) -> str:
    """Bind all calculation inputs without treating the draft event's read time as a change.

    CV-25 already excludes the bundle cutoff. Pending events have synthetic recorded_at
    values set to that cutoff by the bundle builder. Normalize only those timestamps;
    retain their effective dates, order, payloads and every stored event timestamp.
    This is an approval comparison, never a replacement for the engine's input hash.
    """
    return replace(
        bundle,
        events=tuple(
            replace(event, recorded_at=datetime(1970, 1, 1, tzinfo=UTC))
            if event.contract_key == contract_key and event.stream_version > head
            else event
            for event in bundle.events
        ),
    ).sha256()


def posting_lines(output: OutputBundle) -> list[dict[str, Any]]:
    """Show every proposed ledger line without aggregating away books or entities."""

    def amount(value: int, currency: str) -> dict[str, Any]:
        return money_out(
            minor_to_decimal(value, ISO_4217[currency].minor_unit), currency, ISO_4217
        ).model_dump(mode="json")

    return [
        {
            "book": intent.book_code,
            "entity": intent.entity,
            "posting_period": intent.posting_period_key,
            "origin_period": intent.origin_period_key,
            "entry_kind": intent.entry_kind,
            "subject": intent.subject_key,
            "side": "Debit" if line.side == "D" else "Credit",
            "account": line.account_code,
            "account_role": line.account_role,
            "transaction_amount": amount(line.amount_txn, line.txn_currency),
            "functional_amount": amount(line.amount_functional, line.functional_currency),
            "counterparty_entity": line.counterparty_entity,
        }
        for book in output.books
        for intent in book.posting_intents
        for line in intent.lines
    ]


def retain_preview(
    uow: UnitOfWork, preview: ImpactPreview, bundle: InputBundle, current: Mapping[str, Any]
) -> ImpactPreview:
    document = {
        "before": dict(preview.before),
        "after": dict(preview.after),
        "provenance": {
            "comparison_version": 1,
            "calculation_sha256": calculation_sha256(
                bundle, str(current["external_id"]), int(current["head_stream_version"])
            ),
            "input_sha256": bundle.sha256(),
            "engine_version": bundle.engine_version,
        },
    }
    stored = store_file(
        uow,
        purpose=FilePurpose.IMPACT_PREVIEW,
        stream=io.BytesIO(canonical_bytes(document)),
        original_filename=None,
        media_type="application/json",
    )
    return type(preview)(
        before=preview.before,
        after=preview.after,
        retained_file_id=UUID(str(stored["id"])),
        retained_sha256=str(stored["sha256"]),
    )


def assert_calculation(
    uow: UnitOfWork, request_id: UUID, bundle: InputBundle, current: Mapping[str, Any]
) -> None:
    from erev_api.approvals.engine import StaleBasis
    from erev_api.approvals.preview import read_preview

    row = uow.session.execute(
        select(
            approval_request.c.impact_preview_file_id, approval_request.c.impact_preview_sha256
        ).where(approval_request.c.id == request_id)
    ).one()
    if row.impact_preview_file_id is None:
        raise StaleBasis()
    document = read_preview(
        uow.session, row.impact_preview_file_id, files=uow.files, keyring=uow.keyring
    )
    provenance = document.get("provenance", {})
    if (
        sha256_hex(document) != row.impact_preview_sha256
        or provenance.get("comparison_version") != 1
        or provenance.get("calculation_sha256")
        != calculation_sha256(
            bundle, str(current["external_id"]), int(current["head_stream_version"])
        )
    ):
        raise StaleBasis()


def compute_approved(
    uow: UnitOfWork, expected: InputBundle, *, contract_key: str, previous_head: int
) -> None:
    """Apply this reviewed calculation in the approval transaction, never in a later job.

    Compare the actual persisted-event bundle with the validated pending-event bundle.
    Only append metadata changes: SYSTEM attribution, recorded time and the global record
    sequence assigned by the stream. Keep the actual order and every accounting input.
    The engine receives the unmodified actual bundle, preserving normal computation hashes.
    """
    from erev_api.approvals.engine import StaleBasis
    from erev_api.domain.contracts import computation
    from erev_api.domain.contracts.compute_job import compute_group
    from erev_api.enums import ComputationStatus
    from erev_api.problems import Problem

    proposed = {
        event.event_key: event
        for event in expected.events
        if event.contract_key == contract_key and event.stream_version > previous_head
    }
    run = computation.default_engine()

    def checked(actual: InputBundle) -> OutputBundle:
        normalized = []
        for event in actual.events:
            draft = proposed.get(event.event_key)
            if draft is not None:
                if event.origin != "SYSTEM":
                    raise StaleBasis()
                event = replace(
                    event,
                    origin=draft.origin,
                    recorded_at=draft.recorded_at,
                    record_seq=draft.record_seq,
                )
            normalized.append(event)
        compared = replace(actual, trigger=expected.trigger, events=tuple(normalized))
        if compared.sha256() != expected.sha256():
            raise StaleBasis()
        return run(actual)

    group_id = uow.session.execute(
        select(contract.c.combination_group_id).where(contract.c.external_id == contract_key)
    ).scalar_one()
    outcome = compute_group(uow, group_id, engine=checked)
    if outcome.status != ComputationStatus.SUCCEEDED:
        raise Problem(
            "invalid-transition",
            "The reviewed assessment could not be computed. No approval or assessment was "
            "applied. Resolve the calculation issue and retry the decision.",
        )


def _members(session: Session, contract_id: UUID) -> list[Mapping[str, Any]]:
    group_id = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    ).scalar_one()
    return [
        dict(row)
        for row in session.execute(
            select(contract)
            .where(contract.c.combination_group_id == group_id)
            .order_by(contract.c.id)
        ).mappings()
    ]


def _periods(
    session: Session,
    members: list[Mapping[str, Any]],
    *,
    lock: bool,
    extra_entity_codes: Sequence[str] = (),
) -> list[Mapping[str, Any]]:
    entities = {row["contracting_entity_id"] for row in members}
    if extra_entity_codes:
        entities.update(
            session.scalars(
                select(legal_entity.c.id).where(legal_entity.c.code.in_(extra_entity_codes))
            )
        )
    statement = (
        select(period_state)
        .where(period_state.c.entity_id.in_(entities))
        .order_by(period_state.c.entity_id, period_state.c.book_code, period_state.c.period_id)
    )
    if lock:
        statement = statement.with_for_update(read=True, nowait=True)
    return [dict(row) for row in session.execute(statement).mappings()]


def lock_basis(session: Session, contract_id: UUID, *, known_at: datetime) -> bool:
    """Hold the group's book, judgement and period basis; report restricted posting windows.

    Periods are locked even when currently closed/open, preventing a concurrent state
    transition from changing the direct-append decision. NOWAIT avoids a close/group
    lock cycle; the command's existing database-error path supplies a retryable conflict.
    """
    with system_entity_scope(session):
        from erev_api.domain.contracts import bundles

        step1.lock_books(session)
        members = _members(session, contract_id)
        session.execute(
            select(judgement_record.c.id)
            .where(judgement_record.c.contract_id.in_([row["id"] for row in members]))
            .order_by(judgement_record.c.id)
            .with_for_update(read=True, nowait=True)
        ).all()
        # The engine also reads performing entities named by the group's lines. Their
        # periods must be locked even when no contract in the group is owned by them.
        scope = bundles.build(
            session, UUID(str(members[0]["combination_group_id"])), known_at, trigger="DRY_RUN"
        )
        periods = _periods(
            session,
            members,
            lock=True,
            extra_entity_codes=[entity.code for entity in scope.entities],
        )
        enabled = {
            entity_id: set(step1.enabled_books(session, entity_id))
            for entity_id in {row["entity_id"] for row in periods}
        }
        return any(
            str(row["state"]) in POSTABLE_STATES
            and str(row["book_code"]) in enabled[row["entity_id"]]
            and auto_approval_barred(
                session,
                entity_id=row["entity_id"],
                book_code=BookCode(row["book_code"]),
                period_id=row["period_id"],
            )
            for row in periods
        )


def requires_review(
    session: Session,
    contract_id: UUID,
    events: Sequence[EventIn],
    output: OutputBundle,
) -> bool:
    """Check all batch dates and every computed posting destination under held period locks."""
    with system_entity_scope(session):
        members = _members(session, contract_id)
        entities = sorted({row["contracting_entity_id"] for row in members})
        for entity_id in entities:
            for book in step1.enabled_books(session, entity_id):
                for effective in sorted({event.effective_date for event in events}):
                    if posts_into_restricted_period(
                        session,
                        entity_id=entity_id,
                        book_code=book,
                        effective_date=effective,
                    ):
                        return True
        targets = {
            (intent.entity, intent.book_code, intent.posting_period_key)
            for book in output.books
            for intent in book.posting_intents
        }
        for entity_code, book_code, period_key in sorted(targets):
            entity = session.execute(
                select(legal_entity.c.id, legal_entity.c.calendar_id).where(
                    legal_entity.c.code == entity_code,
                )
            ).one()
            period_id = session.execute(
                select(period.c.id).where(
                    period.c.calendar_id == entity.calendar_id,
                    period.c.period_key == period_key,
                )
            ).scalar_one()
            if auto_approval_barred(
                session,
                entity_id=entity.id,
                book_code=BookCode(book_code),
                period_id=period_id,
            ):
                return True
    return False


def same_effective_day(
    session: Session, contract_id: UUID, submitted_at: datetime, now: datetime
) -> bool:
    """A current-day system release cannot move to an unreviewed date while waiting."""
    with system_entity_scope(session):
        from erev_api.domain.contracts import bundles

        members = _members(session, contract_id)
        scope = bundles.build(
            session, UUID(str(members[0]["combination_group_id"])), now, trigger="DRY_RUN"
        )
        zones = [entity.time_zone for entity in scope.entities]
        return all(
            submitted_at.astimezone(ZoneInfo(zone)).date() == now.astimezone(ZoneInfo(zone)).date()
            for zone in zones
        )


def reviewed_dates(session: Session, events: Sequence[EventIn]) -> list[dict[str, Any]]:
    """Human-readable event dates and cited conclusions in the immutable review preview."""
    result: list[dict[str, Any]] = []
    for event in events:
        item = {
            "event_type": event.event_type.value,
            "effective_date": event.effective_date.isoformat(),
            **payload_json(event.payload),
        }
        if isinstance(event.payload, CollectibilityAssessedV1):
            record = session.execute(
                select(
                    judgement_record.c.judgement_no,
                    judgement_record.c.conclusion,
                    judgement_record.c.reviewed_at,
                ).where(judgement_record.c.id == UUID(str(event.payload.judgement_record_id)))
            ).one()
            item.update(
                judgement_no=record.judgement_no,
                conclusion=record.conclusion,
                reviewed_at=record.reviewed_at.isoformat(),
            )
        result.append(item)
    return result


def content(session: Session, submission_id: UUID) -> Mapping[str, Any]:
    """Bind original inputs to the group stream, book choices and reviewed judgement basis."""
    from erev_api.approvals.subjects import event_submission_content, judgement_record_content

    result = dict(event_submission_content(session, submission_id))
    contract_id = session.execute(
        select(event_submission.c.contract_id).where(event_submission.c.id == submission_id)
    ).scalar_one()
    with system_entity_scope(session):
        members = _members(session, contract_id)
        result["step1_basis"] = {
            "contracts": [
                {
                    "id": str(row["id"]),
                    "group_id": str(row["combination_group_id"]),
                    "head": int(row["head_stream_version"]),
                    "status": str(row["status"]),
                    "books": step1.enabled_books(session, row["contracting_entity_id"]),
                }
                for row in members
            ],
            "judgements": [
                {
                    "id": str(row["id"]),
                    "status": str(row["status"]),
                    "reviewer_id": None if row["reviewer_id"] is None else str(row["reviewer_id"]),
                    "reviewed_at": None
                    if row["reviewed_at"] is None
                    else row["reviewed_at"].isoformat(),
                    "content": judgement_record_content(session, row["id"]),
                }
                for row in session.execute(
                    select(judgement_record)
                    .where(judgement_record.c.contract_id.in_([member["id"] for member in members]))
                    .order_by(judgement_record.c.id)
                ).mappings()
            ],
            "periods": [
                {
                    "id": str(row["id"]),
                    "state": str(row["state"]),
                    "lock_id": None
                    if row["current_lock_id"] is None
                    else str(row["current_lock_id"]),
                }
                for row in _periods(session, members, lock=False)
            ],
        }
    return result
