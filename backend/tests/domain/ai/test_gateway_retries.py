"""Bounded AI retry waits follow committed evidence and re-enter admission."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from erev_api.adapters.ai.anthropic import AnthropicProvider
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_call_intent, ai_model_log, ai_proposal
from erev_api.domain.ai import jobs as ai_jobs
from erev_api.domain.ai.attempts import AttemptEvidenceRefused
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.gateway import AiGateway, NarrativeSource, source_sha256
from erev_api.domain.ai.ports import AIRequest, AIResponse, AIUsage, ProviderError
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
        ("unknown_usage", 1, None),
        ("resume_unknown_usage", 1, None),
        ("permanent", 1, "failed"),
        ("adapter_known", 1, "failed"),
        ("adapter_unknown", 1, "failed"),
        ("recover", 3, "proposed"),
        ("disabled", 1, None),
        ("crash", 1, None),
        ("lost_result", 1, None),
        ("resume_transient", 3, "failed"),
        ("resume_permanent", 1, "failed"),
        ("resume_exhausted", 3, "failed"),
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
    monkeypatch: pytest.MonkeyPatch,
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
            with tenant_session(context.principal.db_context, read_only=True) as session:
                starts = (
                    session.execute(
                        select(ai_call_intent).where(ai_call_intent.c.job_id == context.job_id)
                    )
                    .mappings()
                    .all()
                )
                assert len(starts) == len(observed) + 1
                assert all(row["input_sha256"] == request.input_sha256 for row in starts)
            observed.append(request)
            if mode in {"adapter_known", "adapter_unknown"}:
                client = MagicMock()
                client.__enter__.return_value = client
                client.messages.create.return_value = SimpleNamespace(
                    model=request.model,
                    stop_reason=None,
                    content=[],
                    usage=SimpleNamespace(
                        input_tokens=20 if mode == "adapter_known" else -1,
                        output_tokens=10,
                        cache_creation_input_tokens=4,
                        cache_read_input_tokens=6,
                    ),
                )
                return AnthropicProvider(lambda: client).complete(request)
            if mode == "crash":
                raise RuntimeError("simulated worker crash during provider call")
            if mode not in {"recover", "lost_result"} or (mode == "recover" and len(observed) < 3):
                raise ProviderError(
                    "AI_AUTHENTICATION"
                    if mode in {"permanent", "resume_permanent"}
                    else "AI_TIMEOUT",
                    retryable=True,
                    usage=None
                    if mode in {"unknown_usage", "resume_unknown_usage"}
                    else AIUsage(2, 1),
                )
            root = json.loads(request.messages[0]["content"])["facts"]["root_node_id"]
            answer = json.dumps({"narrative": f"Revenue USD {line['amount']}.", "node_ids": [root]})
            return AIResponse(
                answer, sha256(answer.encode()).hexdigest(), 20, 10, 0, request.model, "end_turn"
            )

    gateway = AiGateway(
        provider="anthropic" if mode.startswith("adapter_") else "fake",
        provider_factory=Provider,
        platform_kill_switch=lambda: disabled[0],
    )
    waits: list[timedelta] = []

    def wait(delay: timedelta) -> None:
        waits.append(delay)
        # Retry waits cannot retain the admission lease, and preceding logs are committed.
        with budget_guard(context.principal.db_context) as guard:
            assert guard is not None
        with tenant_session(context.principal.db_context, read_only=True) as session:
            assert session.scalar(select(func.count()).select_from(ai_model_log)) == len(observed)
        clock.advance(delay)
        if mode == "disabled":
            disabled[0] = True

    source = NarrativeSource("schedule_line", line["id"], "amount")
    if mode.startswith("resume_"):
        for _ in range(3 if mode == "resume_exhausted" else 1):
            with pytest.raises(ProviderError) as caught:
                gateway.run_narrative_attempt(context, source, max_tokens=1000)
            assert caught.value.usage == (None if mode == "resume_unknown_usage" else AIUsage(2, 1))
        # Reconstruct the gateway with no in-memory retry state, as a restarted worker does.
        gateway = AiGateway(
            provider="fake", provider_factory=Provider, platform_kill_switch=lambda: disabled[0]
        )
    if mode in {"crash", "lost_result"}:

        def lost_commit(*args: Any, **kwargs: Any) -> NoReturn:
            raise RuntimeError("simulated worker crash before result commit")

        with monkeypatch.context() as patch:
            if mode == "lost_result":
                patch.setattr("erev_api.domain.ai.gateway.record_narrative", lost_commit)
            with pytest.raises(RuntimeError, match="simulated worker crash"):
                gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
        gateway = AiGateway(
            provider="fake", provider_factory=Provider, platform_kill_switch=lambda: False
        )
        with pytest.raises(AttemptEvidenceRefused, match="AI_OUTCOME_UNKNOWN"):
            gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
        with tenant_session(context.principal.db_context, read_only=True) as session:
            assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 1
            assert session.scalar(select(func.count()).select_from(ai_model_log)) == 0
            assert session.scalar(select(func.count()).select_from(ai_proposal)) == 0
        peer = context_for(world.maya.member, clock)
        peer_context = JobContext(
            job_id=peer.job_id,
            tenant_id=peer.tenant_id,
            kind=peer.kind,
            principal=peer.principal,
            runtime=replace(peer.runtime, keyring=keyring, files=LocalFileStore(tmp_path)),
        )
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            gateway.run_narrative(peer_context, source, max_tokens=1000, wait=wait)
        assert len(observed) == 1 and waits == []
        return
    if mode in {"unknown_usage", "resume_unknown_usage"}:
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
        assert len(observed) == 1
        peer = context_for(world.maya.member, clock)
        peer_context = JobContext(
            job_id=peer.job_id,
            tenant_id=peer.tenant_id,
            kind=peer.kind,
            principal=peer.principal,
            runtime=replace(peer.runtime, keyring=keyring, files=LocalFileStore(tmp_path)),
        )
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
            gateway.run_narrative(peer_context, source, max_tokens=1000, wait=wait)
        assert len(observed) == 1
        with tenant_session(context.principal.db_context, read_only=True) as session:
            logs = session.execute(select(ai_model_log)).mappings().all()
            assert len(logs) == 1 and logs[0]["parameters"]["usage_evidence"] == "UNKNOWN"
            assert session.scalar(select(func.count()).select_from(ai_proposal)) == 0
        return
    if status is None:
        with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
            gateway.run_narrative(context, source, max_tokens=1000, wait=wait)
        proposal = None
    else:
        monkeypatch.setattr(ai_jobs, "_gateway", gateway)
        monkeypatch.setattr(ai_jobs, "_wait", wait)
        params = {
            "operation": "narrative",
            "object_type": source.object_type,
            "object_id": str(source.object_id),
            "measure": source.measure,
            "max_tokens": 1000,
        }
        outcome = ai_jobs.run(context, params)
        proposal = UUID(outcome.result["proposal_id"])
        assert ai_jobs.run(context, params).result == outcome.result
    if proposal is not None:
        assert gateway.run_narrative(context, source, max_tokens=1000, wait=wait) == proposal
    assert len(observed) == calls
    assert waits == (
        []
        if mode
        in {"permanent", "resume_permanent", "resume_exhausted", "adapter_known", "adapter_unknown"}
        else [timedelta(seconds=5)]
        if mode == "disabled"
        else [timedelta(seconds=5), timedelta(seconds=10)]
    )
    with tenant_session(context.principal.db_context, read_only=True) as session:
        logs = list(session.execute(select(ai_model_log).order_by(ai_model_log.c.id)).mappings())
        proposals = list(session.execute(select(ai_proposal)).mappings())
        assert len(logs) == calls
        intents = (
            session.execute(select(ai_call_intent).order_by(ai_call_intent.c.attempt_no))
            .mappings()
            .all()
        )
        assert [row["attempt_no"] for row in intents] == list(range(1, calls + 1))
        assert {row["intent_id"] for row in logs} == {row["id"] for row in intents}
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
                    "code": "AI_INVALID_RESPONSE"
                    if mode.startswith("adapter_")
                    else "AI_AUTHENTICATION"
                    if mode in {"permanent", "resume_permanent"}
                    else "AI_TIMEOUT"
                }
                assert all(item["response_sha256"] is None for item in logs)
            else:
                assert row["problem"] is None
                assert sum(item["input_tokens"] + item["output_tokens"] for item in logs) == 36

    if mode.startswith("adapter_"):
        with budget_guard(context.principal.db_context) as guard:
            assert guard is not None
            if mode == "adapter_known":
                assert guard.require_available(now=clock.now(), monthly_budget=1000).tokens == 40
                assert logs[0]["parameters"]["usage_evidence"] == "REPORTED"
            else:
                with pytest.raises(AIBudgetRefused, match="AI_BUDGET_USAGE_UNCERTAIN"):
                    guard.require_available(now=clock.now(), monthly_budget=1000)
                assert logs[0]["parameters"]["usage_evidence"] == "UNKNOWN"
        return

    if status == "failed":
        fresh = retrieve_narrative(
            context,
            object_type="schedule_line",
            object_id=line["id"],
            measure="amount",
            model="fixture-model",
            max_tokens=1000,
        )
        with system_unit_of_work(
            context.runtime, fresh.principal, request_id="wrong-job-intent"
        ) as uow:
            with pytest.raises(ProposalEvidenceRefused, match="AI_INVALID_INTENT_BINDING"):
                record_provider_failure(
                    uow,
                    prepared=fresh.prepared,
                    log_id=logs[-1]["id"],
                    provider="fake",
                    code=row["problem"]["code"],
                    job_id=new_id(),
                    job_source_sha256=source_sha256(source, 1000),
                )
            assert uow.drain_audit_events() == []
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
