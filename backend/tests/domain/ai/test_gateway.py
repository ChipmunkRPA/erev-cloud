"""A narrative gateway attempt composes real admission, retrieval and persistence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from erev_api.adapters.ai.provider import FakeProvider
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, role_assignment
from erev_api.domain.ai.access import AIAccessRefused
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.gateway import AiGateway, NarrativeSource
from erev_api.domain.ai.ports import AIRequest, AIResponse, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.retrieval import retrieve_narrative
from erev_api.domain.ai.settings import AISettingsRefused
from erev_api.enums import RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobContext
from sqlalchemy import select, text, update
from support.reference import assign
from support.rows import publish_registry_version
from tests.api.test_explain_api import World, k01_computed, september_line
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world
from tests.domain.ai.test_narrative_retrieval import context_for


def test_admitted_call_failure_kill_switch_and_exhaustion(
    world: World, clock: FrozenClock, keyring: KeyRing, tmp_path: Path
) -> None:
    k01_computed(world)
    line = september_line(world)
    assign(world.maya.member, "viewer")

    def next_context() -> JobContext:
        original = context_for(world.maya.member, clock)
        return JobContext(
            job_id=original.job_id,
            tenant_id=original.tenant_id,
            kind=original.kind,
            principal=original.principal,
            runtime=replace(
                original.runtime, keyring=keyring, files=LocalFileStore(tmp_path / "files")
            ),
        )

    context = next_context()
    switch = {"disabled": False}
    state: dict[str, str | int] = {"mode": "success", "calls": 0, "factories": 0}

    def counts() -> tuple[int, int]:
        return int(state["calls"]), int(state["factories"])

    fake = FakeProvider(tmp_path / "fixtures")

    class Provider:
        def complete(self, request: AIRequest) -> AIResponse:
            state["calls"] = int(state["calls"]) + 1
            with budget_guard(context.principal.db_context) as competing:
                assert competing is None
            with tenant_session(context.principal.db_context, read_only=True) as session:
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                            "AND state = 'idle in transaction'"
                        )
                    )
                    == 0
                )
            if state["mode"] == "timeout":
                raise ProviderError("AI_TIMEOUT", retryable=True)
            if state["mode"] == "disable":
                switch["disabled"] = True
            if state["mode"] == "revoke":
                with tenant_session(context.principal.db_context) as session:
                    session.execute(
                        update(role_assignment)
                        .where(
                            role_assignment.c.membership_id == world.maya.member.membership_id,
                            role_assignment.c.revoked_at.is_(None),
                        )
                        .values(revoked_at=clock.now(), revoked_by_kind="SYSTEM")
                    )
            return fake.complete(request)

    def factory() -> Provider:
        state["factories"] = int(state["factories"]) + 1
        return Provider()

    gateway = AiGateway(
        provider="fake", provider_factory=factory, platform_kill_switch=lambda: switch["disabled"]
    )
    source = NarrativeSource("schedule_line", line["id"], "amount")
    with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
        gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert counts() == (0, 0)
    with tenant_session(context.principal.db_context) as session:
        publish_registry_version(
            session,
            tenant_id=context.tenant_id,
            category=RegistryCategory.AI,
            values={
                "ai.enabled": True,
                "ai.model": "fixture-model",
                "ai.monthly_token_budget": 90,
                "ai.send_contract_text": False,
                "ai.redact_contact_details": True,
            },
            at=clock.now(),
        )
    prepared = retrieve_narrative(
        context,
        object_type="schedule_line",
        object_id=line["id"],
        measure="amount",
        model="fixture-model",
        max_tokens=1000,
    ).prepared
    root = json.loads(prepared.request.messages[0]["content"])["facts"]["root_node_id"]
    directory = tmp_path / "fixtures" / "explain-narrative" / "v1"
    directory.mkdir(parents=True)
    (directory / f"{prepared.request.input_sha256}.json").write_text(
        json.dumps(
            {
                "text": json.dumps(
                    {"narrative": f"Revenue USD {line['amount']}.", "node_ids": [root]}
                ),
                "input_tokens": 20,
                "output_tokens": 10,
                "latency_ms": 0,
                "stop_reason": "end_turn",
            }
        )
    )
    with budget_guard(context.principal.db_context):
        with pytest.raises(AIBudgetRefused, match="AI_BUDGET_BUSY"):
            gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert counts() == (0, 0)
    proposal = gateway.run_narrative_attempt(context, source, max_tokens=1000)
    completed_context = context
    assert gateway.run_narrative_attempt(context, source, max_tokens=1000) == proposal
    assert counts() == (1, 1)
    context = next_context()
    state["mode"] = "timeout"
    with pytest.raises(ProviderError) as error:
        gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert error.value.retryable and error.value.code == "AI_TIMEOUT"
    context = next_context()
    state["mode"] = "disable"
    with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
        gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert counts() == (3, 3)
    switch["disabled"] = False
    context = next_context()
    state["mode"] = "revoke"
    with pytest.raises(AIAccessRefused, match="AI_PERMISSION_DENIED"):
        gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert counts() == (4, 4)
    assign(world.maya.member, "viewer")
    with pytest.raises(AIBudgetRefused, match="AI_BUDGET_EXHAUSTED"):
        gateway.run_narrative_attempt(context, source, max_tokens=1000)
    assert counts() == (4, 4)
    switch["disabled"] = True
    assert gateway.run_narrative_attempt(completed_context, source, max_tokens=1000) == proposal
    assert counts() == (4, 4)
    with pytest.raises(PreparationRefused, match="AI_JOB_INPUT_CHANGED"):
        gateway.run_narrative_attempt(completed_context, source, max_tokens=1001)
    with tenant_session(context.principal.db_context, read_only=True) as session:
        proposals = list(session.execute(select(ai_proposal)).mappings())
        assert len(proposals) == 1 and proposals[0]["id"] == proposal
        assert proposals[0]["status"] == "proposed"
        assert proposals[0]["job_id"] == completed_context.job_id
        logs = list(session.execute(select(ai_model_log)).mappings())
        assert len(logs) == 4
        assert {row["outcome"] for row in logs} == {"SUCCESS", "TIMEOUT", "ERROR"}
        assert sum(row["input_tokens"] + row["output_tokens"] for row in logs) == 90
