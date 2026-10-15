"""Real trace proposals commit with attempt/audit evidence, without accounting writes."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, audit_event, contract_version
from erev_api.db.transitions import apply as real_apply
from erev_api.domain.ai import expiry, queries
from erev_api.domain.ai.commands import reject_proposal
from erev_api.domain.ai.ports import AIResponse
from erev_api.domain.ai.proposals import ProposalEvidenceRefused, record_narrative
from erev_api.domain.ai.retrieval import retrieve_narrative
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from sqlalchemy import func, select
from support.principals import member
from support.reference import assign
from tests.api.test_explain_api import World, k01_computed, september_line
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world
from tests.domain.ai.test_narrative_retrieval import context_for


def test_proposal_attempt_audit_and_rollback(
    world: World,
    clock: FrozenClock,
    keyring: KeyRing,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    k01_computed(world)
    line = september_line(world)
    assign(world.maya.member, "viewer")
    retrieved = retrieve_narrative(
        context_for(world.maya.member, clock),
        object_type="schedule_line",
        object_id=line["id"],
        measure="amount",
        model="fixture-model",
        max_tokens=1000,
    )
    prepared = retrieved.prepared
    root = json.loads(prepared.request.messages[0]["content"])["facts"]["root_node_id"]

    def response(amount: str) -> AIResponse:
        raw = json.dumps({"narrative": f"Revenue USD {amount}.", "node_ids": [root]})
        return AIResponse(
            raw, sha256(raw.encode()).hexdigest(), 20, 10, 1, "fixture-model", "end_turn"
        )

    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(tmp_path))
    with tenant_session(retrieved.principal.db_context, read_only=True) as session:
        versions_before = session.scalar(select(func.count()).select_from(contract_version))
    with system_unit_of_work(runtime, retrieved.principal, request_id="ai-proposal-success") as uow:
        proposed = record_narrative(
            uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
        )
        uow.commit()
    with system_unit_of_work(runtime, retrieved.principal, request_id="ai-proposal-failure") as uow:
        # A forged caller-side value mapping cannot make an unsupported figure valid.
        altered = replace(prepared, values={root: Decimal("999999999")})
        failed = record_narrative(
            uow, prepared=altered, response=response("999999999"), provider="fake"
        )
        uow.commit()
    with pytest.raises(RuntimeError, match="rollback"):
        with system_unit_of_work(
            runtime, retrieved.principal, request_id="ai-proposal-rollback"
        ) as uow:
            record_narrative(
                uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
            )
            raise RuntimeError("rollback")
    with system_unit_of_work(
        runtime, retrieved.principal, request_id="ai-proposal-mismatch"
    ) as uow:
        altered = replace(prepared, request=replace(prepared.request, input_sha256="0" * 64))
        with pytest.raises(ProposalEvidenceRefused, match="AI_TRACE_EVIDENCE_MISMATCH"):
            record_narrative(
                uow, prepared=altered, response=response(str(line["amount"])), provider="fake"
            )
        tampered = replace(
            prepared,
            request=replace(
                prepared.request, system=prepared.request.system + " Changed after hashing."
            ),
        )
        with pytest.raises(ProposalEvidenceRefused, match="AI_TRACE_EVIDENCE_MISMATCH"):
            record_narrative(
                uow, prepared=tampered, response=response(str(line["amount"])), provider="fake"
            )
        assert uow.drain_audit_events() == []
    overbroad = replace(
        retrieved.principal, permission_scopes={"ai.use": frozenset(), "contract.read": "*"}
    )
    with system_unit_of_work(runtime, overbroad, request_id="ai-proposal-scope") as uow:
        with pytest.raises(ProposalEvidenceRefused, match="AI_PROPOSAL_SCOPE_REQUIRED"):
            record_narrative(
                uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
            )
        assert uow.drain_audit_events() == []
    with tenant_session(retrieved.principal.db_context, read_only=True) as session:
        proposals = {row["id"]: row for row in session.execute(select(ai_proposal)).mappings()}
        assert set(proposals) == {proposed, failed}
        success = proposals[proposed]
        assert success["status"] == "proposed" and success["kind"] == "NUMBER_EXPLANATION"
        assert (
            success["subject_type"] == "calc_trace"
            and success["subject_id"] == line["calc_trace_id"]
        )
        assert success["citations"] == [
            {"ref_type": "record", "ref_id": str(line["calc_trace_id"]), "node_id": root}
        ]
        assert (success["expires_at"] - success["created_at"]).days == 30
        assert success["accepted_by"] is None and success["accepted_command"] is None
        assert proposals[failed]["status"] == "failed"
        assert proposals[failed]["content"] == {} and proposals[failed]["citations"] == []
        assert proposals[failed]["problem"] == {"code": "AI_UNTRACED_FIGURE"}
        logs = {row["id"]: row for row in session.execute(select(ai_model_log)).mappings()}
        assert len(logs) == 2
        assert logs[success["ai_model_log_id"]]["outcome"] == "SUCCESS"
        rejected_log = logs[proposals[failed]["ai_model_log_id"]]
        assert rejected_log["outcome"] == "ERROR" and rejected_log["input_tokens"] == 20
        events = list(
            session.execute(
                select(audit_event).where(audit_event.c.action == "ai_proposal.create")
            ).mappings()
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "ai_model_log.record")
            )
            == 2
        )
        assert len(events) == 2
        assert {row["object_id"] for row in events} == {proposed, failed}
        assert all(
            row["actor_kind"] == "USER" and row["actor_id"] == retrieved.principal.id
            for row in events
        )
        assert all("contract_id" in row["detail"] for row in events)
        assert "Revenue USD" not in json.dumps([dict(row) for row in events], default=str)
        assert session.scalar(select(func.count()).select_from(contract_version)) == versions_before

    # Expiry preserves immutable evidence and never revives failed/rejected proposals.
    with system_unit_of_work(runtime, retrieved.principal, request_id="expiry-fixtures") as uow:
        second = record_narrative(
            uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
        )
        rejected = record_narrative(
            uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
        )
        reject_proposal(uow, rejected, reason="Not needed", check_version=lambda _version: None)
        uow.commit()
    clock.advance(timedelta(days=29))
    with system_unit_of_work(runtime, retrieved.principal, request_id="expiry-future") as uow:
        future = record_narrative(
            uow, prepared=prepared, response=response(str(line["amount"])), provider="fake"
        )
        uow.commit()
    assert expiry.expire_due(runtime) == 0
    clock.advance(timedelta(days=1))
    other_tenant = member(keyring, clock, name="expiry_other")
    assert expiry.expire_tenant(runtime, other_tenant.tenant_id) == 0
    # Another transaction owns a review lock; the sweep progresses without taking it.
    with tenant_session(retrieved.principal.db_context) as session:
        session.execute(
            select(ai_proposal.c.id)
            .where(ai_proposal.c.id.in_([proposed, second]))
            .with_for_update()
        )
        assert expiry.expire_due(runtime) == 0

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        real_apply(*args, **kwargs)
        raise RuntimeError("expiry interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(expiry, "apply", interrupted)
        with pytest.raises(RuntimeError, match="expiry interrupted"):
            expiry.expire_due(runtime)
    with tenant_session(retrieved.principal.db_context, read_only=True) as session:
        assert (
            session.scalar(select(ai_proposal.c.status).where(ai_proposal.c.id == proposed))
            == "proposed"
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "ai_proposal.expire")
            )
            == 0
        )
    monkeypatch.setattr(expiry, "BATCH_SIZE", 1)
    assert expiry.expire_due(runtime) == 2
    assert expiry.expire_due(runtime) == 0
    with tenant_session(retrieved.principal.db_context, read_only=True) as session:
        rows = {row["id"]: row for row in session.execute(select(ai_proposal)).mappings()}
        assert rows[proposed]["status"] == rows[second]["status"] == "expired"
        assert rows[failed]["status"] == "failed"
        assert rows[rejected]["status"] == "rejected"
        assert rows[future]["status"] == "proposed"
        assert rows[proposed]["row_version"] == success["row_version"] + 1
        for field in ("content", "citations", "ai_model_log_id", "expires_at", "created_at"):
            assert rows[proposed][field] == success[field]
        events = list(
            session.execute(
                select(audit_event).where(audit_event.c.action == "ai_proposal.expire")
            ).mappings()
        )
        assert {event["object_id"] for event in events} == {proposed, second}
        assert len(events) == 2 and all(event["actor_kind"] == "SYSTEM" for event in events)
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 5
        assert session.scalar(select(func.count()).select_from(contract_version)) == versions_before

    retained = queries.proposal(retrieved.principal, proposed)
    assert retained.status == "expired" and retained.content == success["content"]
