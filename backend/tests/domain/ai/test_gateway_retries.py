"""Bounded AI retry waits follow committed evidence and re-enter admission."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal
from erev_api.domain.ai.budget import budget_guard
from erev_api.domain.ai.gateway import AiGateway, NarrativeSource
from erev_api.domain.ai.ports import AIRequest, AIResponse, ProviderError
from erev_api.domain.ai.proposals import ProposalEvidenceRefused, record_provider_failure
from erev_api.domain.ai.retrieval import retrieve_narrative
from erev_api.domain.ai.settings import AISettingsRefused
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext, system_unit_of_work
from sqlalchemy import func, select
from support.reference import assign
from support.rows import publish_registry_version
from tests.api.test_explain_api import World, k01_computed, september_line
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world
from tests.domain.ai.test_narrative_retrieval import context_for


@pytest.mark.parametrize(
    "mode,calls,status",
    [
        ("transient", 3, "failed"),
        ("permanent", 1, "failed"),
        ("recover", 3, "proposed"),
        ("disabled", 1, None),
    ],
)
def test_retry_evidence_and_terminal_outcome(
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    tmp_path: Path,
    mode: str,
    calls: int,
    status: str | None,
) -> None:
    k01_computed(world)
    line = september_line(world)
    assign(world.maya.member, "viewer")
    original = context_for(world.maya.member, clock)
    context = JobContext(
        job_id=original.job_id,
        tenant_id=original.tenant_id,
        kind=original.kind,
        principal=original.principal,
        runtime=replace(original.runtime, keyring=keyring, files=LocalFileStore(tmp_path)),
    )
    with tenant_session(context.principal.db_context) as session:
        publish_registry_version(
            session,
            tenant_id=context.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.model": "fixture-model",
                "ai.monthly_token_budget": 1000,
                "ai.send_contract_text": False,
                "ai.redact_contact_details": True,
            },
            at=clock.now(),
        )
    observed: list[AIRequest] = []
    disabled = [False]

    class Provider:
        def complete(self, request: AIRequest) -> AIResponse:
            observed.append(request)
            if mode != "recover" or len(observed) < 3:
                raise ProviderError(
                    "AI_AUTHENTICATION" if mode == "permanent" else "AI_TIMEOUT",
                    retryable=True,
                )
            root = json.loads(request.messages[0]["content"])["facts"]["root_node_id"]
            answer = json.dumps({"narrative": f"Revenue USD {line['amount']}.", "node_ids": [root]})
            return AIResponse(
                answer, sha256(answer.encode()).hexdigest(), 20, 10, 0, request.model, "end_turn"
            )

    gateway = AiGateway(
        provider="fake", provider_factory=Provider, platform_kill_switch=lambda: disabled[0]
    )
    waits: list[timedelta] = []

    def wait(delay: timedelta) -> None:
        waits.append(delay)
        # Retry waits cannot retain the admission lease, and preceding logs are committed.
        with budget_guard(context.principal.db_context) as guard:
            assert guard is not None
        with tenant_session(context.principal.db_context, read_only=True) as session:
            assert session.scalar(select(func.count()).select_from(ai_model_log)) == len(observed)
        if mode == "disabled":
            disabled[0] = True

    source = NarrativeSource("schedule_line", line["id"], "amount")
    if status is None:
        with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
            gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
        proposal = None
    else:
        proposal = gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
    if proposal is not None:
        assert gateway.run_narrative(context, source, max_tokens=1000, wait=wait) == proposal
    assert len(observed) == calls
    assert waits == (
        []
        if mode == "permanent"
        else [timedelta(seconds=5)]
        if mode == "disabled"
        else [timedelta(seconds=5), timedelta(seconds=10)]
    )
    with tenant_session(context.principal.db_context, read_only=True) as session:
        logs = list(session.execute(select(ai_model_log).order_by(ai_model_log.c.id)).mappings())
        proposals = list(session.execute(select(ai_proposal)).mappings())
        assert len(logs) == calls
        if status is None:
            assert proposals == []
        else:
            assert len(proposals) == 1 and proposals[0]["id"] == proposal
            row = proposals[0]
            assert row["status"] == status
            assert row["ai_model_log_id"] == logs[-1]["id"]
            if status == "failed":
                assert row["content"] == {} and row["citations"] == []
                assert row["problem"] == {
                    "code": "AI_AUTHENTICATION" if mode == "permanent" else "AI_TIMEOUT"
                }
                assert all(item["response_sha256"] is None for item in logs)
            else:
                assert row["problem"] is None
                assert sum(item["input_tokens"] + item["output_tokens"] for item in logs) == 30

    if mode == "recover":
        fresh = retrieve_narrative(
            context,
            object_type="schedule_line",
            object_id=line["id"],
            measure="amount",
            model="fixture-model",
            max_tokens=1000,
        )
        with system_unit_of_work(
            context.runtime, fresh.principal, request_id="ai-wrong-evidence"
        ) as uow:
            with pytest.raises(ProposalEvidenceRefused, match="AI_ATTEMPT_EVIDENCE_MISMATCH"):
                record_provider_failure(
                    uow,
                    prepared=fresh.prepared,
                    log_id=logs[-1]["id"],
                    provider="fake",
                    code="AI_TIMEOUT",
                )
            assert uow.drain_audit_events() == []
