"""Extraction calls commit evidence, reuse retained input and re-enter admission on retry."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    ai_call_intent,
    ai_model_log,
    ai_proposal,
    file_object,
    job,
    role_assignment,
)
from erev_api.domain.ai import extraction_gateway
from erev_api.domain.ai import jobs as ai_jobs
from erev_api.domain.ai.access import AIAccessRefused, AICancelled
from erev_api.domain.ai.attempts import AttemptEvidenceRefused
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.extraction_gateway import ExtractionGateway, ExtractionSource
from erev_api.domain.ai.extraction_proposals import record_extraction_failure
from erev_api.domain.ai.ports import AIRequest, AIResponse, AIUsage, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.settings import AISettingsRefused
from erev_api.enums import FilePurpose, RegistryCategory
from erev_api.files.store import store_file
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import run_job
from sqlalchemy import func, select, update
from support.rows import publish_registry_version
from tests.api.test_explain_api import World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401
from tests.domain.ai.test_narrative_retrieval import context_for


@pytest.mark.parametrize(
    "mode,calls,status",
    [
        ("success", 1, "proposed"),
        ("worker", 1, "proposed"),
        ("retry", 3, "proposed"),
        ("resume_wait", 3, "proposed"),
        ("exhausted", 3, "failed"),
        ("permanent", 1, "failed"),
        ("resume_failure", 1, "failed"),
        ("unknown_usage", 1, None),
        ("crash", 1, None),
        ("disable_response", 1, None),
        ("revoke_response", 1, None),
        ("cancel_before", 0, None),
        ("cancel_wait", 1, None),
        ("cancel_response", 1, "proposed"),
        ("budget", 0, None),
        ("text_off", 0, None),
        ("invalid_output", 1, "failed"),
        ("invalid_value", 1, "failed"),
        ("unknown_path", 0, None),
    ],
)
def test_extraction_admission_retries_and_recovery(
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    mode: str,
    calls: int,
    status: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = (
        Path(__file__).parents[2] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"
    ).read_bytes()
    with world.place.uow() as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(pdf),
            original_filename="contract.pdf",
            media_type="application/pdf",
        )
        publish_registry_version(
            uow.session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.send_contract_text": mode != "text_off",
                "ai.monthly_token_budget": 0 if mode == "budget" else 1000,
                "ai.model": "fixture-model",
            },
            at=clock.now(),
        )
        uow.commit()
    params = {
        "operation": "extraction",
        "file_id": str(stored["id"]),
        "file_sha256": str(stored["sha256"]),
        "allowed_paths": ["lines.0"],
        "max_tokens": 1024,
    }
    base = context_for(world.maya.member, clock, queued_params=params if mode == "worker" else None)
    context = JobContext(
        job_id=base.job_id,
        tenant_id=base.tenant_id,
        kind=base.kind,
        principal=base.principal,
        runtime=replace(base.runtime, files=world.app.state.file_store, keyring=keyring),
    )
    source = ExtractionSource(stored["id"], str(stored["sha256"]), frozenset({"lines.0"}))
    if mode == "unknown_path":
        source = replace(source, allowed_paths=frozenset({"submit_for_activation"}))
    parsed: list[bytes] = []
    observed: list[AIRequest] = []
    constructed: list[bool] = []
    disabled = [False]
    waits: list[timedelta] = []

    def cancel() -> None:
        with tenant_session(context.principal.db_context) as session:
            session.execute(
                update(job)
                .where(job.c.id == context.job_id)
                .values(cancel_requested_at=clock.now())
            )

    def parser(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
        assert send_contract_text and data == pdf
        parsed.append(data)
        return ("Contact buyer@example.com; product DEMO amount 120.00.",)

    class Provider:
        def __init__(self) -> None:
            constructed.append(True)

        def complete(self, request: AIRequest) -> AIResponse:
            with tenant_session(context.principal.db_context, read_only=True) as session:
                starts = (
                    session.execute(
                        select(ai_call_intent)
                        .where(ai_call_intent.c.job_id == context.job_id)
                        .order_by(ai_call_intent.c.attempt_no)
                    )
                    .mappings()
                    .all()
                )
                assert len(starts) == len(observed) + 1
                assert all(
                    row["file_object_id"] == source.file_id
                    and row["document_text_file_id"] is not None
                    for row in starts
                )
                assert len({row["document_text_file_id"] for row in starts}) == 1
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(file_object)
                        .where(file_object.c.purpose == "AI_DOCUMENT_TEXT")
                    )
                    == 1
                )
            with budget_guard(context.principal.db_context) as guard:
                assert guard is None
            observed.append(request)
            assert all(
                "buyer@example.com" not in message["content"] for message in request.messages
            )
            if mode == "crash":
                raise RuntimeError("worker lost during call")
            if mode == "disable_response":
                disabled[0] = True
            if mode == "revoke_response":
                with tenant_session(context.principal.db_context) as session:
                    session.execute(
                        update(role_assignment)
                        .where(role_assignment.c.membership_id == world.maya.member.membership_id)
                        .values(
                            revoked_at=clock.now(),
                            revoked_by=world.maya.member.user_id,
                            revoked_by_kind="USER",
                        )
                    )
            if mode == "cancel_response":
                cancel()
            if mode in {"permanent", "resume_failure"}:
                raise ProviderError("AI_PERMISSION", retryable=False, usage=AIUsage(4, 0))
            if mode in {"exhausted", "unknown_usage", "cancel_wait"} or (
                mode in {"retry", "resume_wait"} and len(observed) < 3
            ):
                raise ProviderError(
                    "AI_RATE_LIMIT",
                    retryable=True,
                    usage=None if mode == "unknown_usage" else AIUsage(4, 0),
                )
            incoming = json.loads(request.messages[0]["content"])
            page = json.loads(incoming["contract_text"])[0]["text"]
            start = page.index("120.00")
            raw = json.dumps(
                [
                    {
                        "path": "lines.0",
                        "value": {
                            "product_code": "DEMO",
                            "amount": 120.0 if mode == "invalid_value" else "120.00",
                        },
                        "confidence": 0.9,
                        "citation": {
                            "ref_type": "document",
                            "ref_id": str(source.file_id),
                            "page": 1,
                            "char_start": start,
                            "char_end": start + 6,
                        },
                    }
                ]
            )
            if mode == "invalid_output":
                raw = "[]"
            return AIResponse(
                raw, sha256(raw.encode()).hexdigest(), 30, 20, 1, request.model, "end_turn"
            )

    def gateway() -> ExtractionGateway:
        return ExtractionGateway(
            provider="fake",
            provider_factory=Provider,
            platform_kill_switch=lambda: disabled[0],
            extract_pages=parser,
        )

    def wait(delay: timedelta) -> None:
        waits.append(delay)
        with budget_guard(context.principal.db_context) as guard:
            assert guard is not None
        with tenant_session(context.principal.db_context, read_only=True) as session:
            assert session.scalar(select(func.count()).select_from(ai_model_log)) == len(observed)
        if mode == "resume_wait" and len(waits) == 1:
            clock.advance(timedelta(seconds=2))
            raise RuntimeError("worker lost during wait")
        clock.advance(delay)
        if mode == "cancel_wait":
            cancel()

    def run() -> UUID:
        return gateway().run_extraction(context, source, max_tokens=1024, wait=wait)

    if mode == "resume_wait":
        with pytest.raises(RuntimeError, match="worker lost during wait"):
            run()
    if mode == "resume_failure":
        original_failure = record_extraction_failure

        def interrupted_failure(*args: object, **kwargs: object) -> UUID:
            raise RuntimeError("worker lost before failed proposal")

        monkeypatch.setattr(extraction_gateway, "record_extraction_failure", interrupted_failure)
        with pytest.raises(RuntimeError, match="worker lost before failed proposal"):
            run()
        monkeypatch.setattr(extraction_gateway, "record_extraction_failure", original_failure)
    if mode == "cancel_before":
        cancel()
    errors: dict[str, type[Exception]] = {
        "unknown_usage": AIBudgetRefused,
        "crash": RuntimeError,
        "disable_response": AISettingsRefused,
        "revoke_response": AIAccessRefused,
        "cancel_before": AICancelled,
        "cancel_wait": AICancelled,
        "budget": AIBudgetRefused,
        "text_off": PreparationRefused,
        "unknown_path": PreparationRefused,
    }
    proposal_id = None
    if mode in errors:
        with pytest.raises(errors[mode]):
            run()
    elif mode == "worker":
        monkeypatch.setattr(ai_jobs, "_gateway", gateway())
        monkeypatch.setattr(ai_jobs, "_wait", wait)
        run_job(
            context.job_id,
            context.tenant_id,
            attempt=1,
            runtime=replace(context.runtime, attempt=None),
        )
        with tenant_session(context.principal.db_context, read_only=True) as session:
            finished = (
                session.execute(select(job).where(job.c.id == context.job_id)).mappings().one()
            )
            assert finished["state"] == "SUCCEEDED"
            proposal_id = UUID(finished["result"]["proposal_id"])
    else:
        proposal_id = run()
        disabled[0] = True
        assert run() == proposal_id  # completed replay never re-enters call admission
    if mode == "crash":
        with pytest.raises(AttemptEvidenceRefused, match="AI_OUTCOME_UNKNOWN"):
            run()
        cancel()
        with pytest.raises(AICancelled, match="AI_CANCELLED"):
            run()
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            with budget_guard(context.principal.db_context) as guard:
                assert guard is not None
                guard.require_available(now=clock.now(), monthly_budget=1000)
    if mode == "disable_response":
        with pytest.raises(AttemptEvidenceRefused, match="AI_RECOVERY_REQUIRED"):
            run()
    assert len(observed) == len(constructed) == calls
    assert len(parsed) == (1 if calls else 0)
    if calls > 1:
        assert all(request == observed[0] for request in observed)
    if mode in {"retry", "exhausted"}:
        assert waits == [timedelta(seconds=5), timedelta(seconds=10)]
    if mode == "resume_wait":
        assert waits == [timedelta(seconds=5), timedelta(seconds=3), timedelta(seconds=10)]
    with tenant_session(context.principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == calls
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == (
            0 if mode == "crash" else calls
        )
        rows = session.execute(select(ai_proposal)).mappings().all()
        if status is None:
            assert rows == []
        else:
            assert len(rows) == 1 and rows[0]["id"] == proposal_id and rows[0]["status"] == status
            assert rows[0]["file_object_id"] == source.file_id
            assert rows[0]["created_by"] == world.maya.member.user_id
            if mode == "invalid_value":
                assert rows[0]["content"] == []
                assert rows[0]["problem"] == {"code": "AI_INVALID_FIELD_VALUE"}
        if mode in {"disable_response", "revoke_response"}:
            log = session.execute(select(ai_model_log)).mappings().one()
            assert (log["input_tokens"], log["output_tokens"]) == (30, 20)
            assert log["error_detail"] == "invalid_output"
