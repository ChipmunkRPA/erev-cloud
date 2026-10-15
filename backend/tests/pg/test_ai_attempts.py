"""Attempt metadata and AUD-FACT evidence commit together without model text."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_call_intent, ai_model_log, audit_event, job
from erev_api.domain.ai.attempts import AttemptEvidenceRefused, record_attempt, record_intent
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.ai.preparation import prepare_request
from erev_api.domain.ai.templates import load_template
from erev_api.enums import PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.principals import member

pytestmark = pytest.mark.pg
SOURCE_TEXT = "Sensitive contract paragraph never retained in a model log"
RESPONSE_TEXT = "Sensitive provider answer never retained in a model log"


def request(model: str = "configured-model") -> AIRequest:
    return prepare_request(
        template=load_template("contract-review", 1),
        model=model,
        max_tokens=1000,
        inputs={},
        contract_text=SOURCE_TEXT,
        send_contract_text=True,
    )


def response() -> AIResponse:
    return AIResponse(
        RESPONSE_TEXT,
        sha256(RESPONSE_TEXT.encode()).hexdigest(),
        123,
        45,
        7,
        "resolved-model-version",
        "end_turn",
    )


@pytest.fixture
def world(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, tmp_path: Path
) -> tuple[Principal, JobRuntime]:
    actor = member(keyring, clock)
    principal = replace(
        system_principal(actor.tenant_id),
        kind=PrincipalKind.USER,
        id=actor.user_id,
        membership_id=actor.membership_id,
        permissions=frozenset({"ai.use"}),
    )
    return principal, JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(tmp_path))


def test_attempt_and_audit_metadata_commit_without_text(
    world: tuple[Principal, JobRuntime],
) -> None:
    principal, runtime = world
    prepared, received = request(), response()
    with system_unit_of_work(runtime, principal, request_id="ai-attempt-test") as uow:
        log_id = record_attempt(
            uow, request=prepared, response=received, provider="fake", outcome="SUCCESS"
        )
        uow.commit()
    with tenant_session(principal.db_context, read_only=True) as session:
        row = (
            session.execute(select(ai_model_log).where(ai_model_log.c.id == log_id))
            .mappings()
            .one()
        )
        assert row["created_by"] == principal.id and row["created_by_kind"] == "USER"
        assert row["model_id"] == "configured-model"
        assert row["parameters"]["response_model"] == "resolved-model-version"
        assert row["input_sha256"] == prepared.input_sha256
        assert row["response_sha256"] == received.response_sha256
        assert (row["input_tokens"], row["output_tokens"], row["latency_ms"]) == (123, 45, 7)
        event = (
            session.execute(
                select(audit_event).where(audit_event.c.action == "ai_model_log.record")
            )
            .mappings()
            .one()
        )
        assert event["object_id"] is None
        assert event["detail"]["ids"] == [str(log_id)]
        assert event["actor_id"] == principal.id
        serialized = json.dumps([dict(row), dict(event)], default=str)
        assert SOURCE_TEXT not in serialized and RESPONSE_TEXT not in serialized


def test_rollback_keeps_neither_log_nor_audit(world: tuple[Principal, JobRuntime]) -> None:
    principal, runtime = world
    with pytest.raises(RuntimeError, match="rollback witness"):
        with system_unit_of_work(runtime, principal, request_id="ai-attempt-rollback") as uow:
            record_attempt(
                uow, request=request(), response=response(), provider="fake", outcome="SUCCESS"
            )
            raise RuntimeError("rollback witness")
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.execute(select(func.count()).select_from(ai_model_log)).scalar_one() == 0
        assert (
            session.execute(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "ai_model_log.record")
            ).scalar_one()
            == 0
        )


def test_budget_and_invalid_output_evidence_preserve_known_usage(
    world: tuple[Principal, JobRuntime],
) -> None:
    principal, runtime = world
    with system_unit_of_work(runtime, principal, request_id="ai-attempt-failure") as uow:
        denied = record_attempt(
            uow,
            request=request(),
            provider="fake",
            outcome="BUDGET_EXCEEDED",
            failure="budget_exhausted",
        )
        failed = record_attempt(
            uow,
            request=request(),
            response=response(),
            provider="fake",
            outcome="ERROR",
            failure="invalid_output",
        )
        uow.commit()
    with tenant_session(principal.db_context, read_only=True) as session:
        rows = {row["id"]: row for row in session.execute(select(ai_model_log)).mappings()}
        assert rows[denied]["input_tokens"] == 0 and rows[denied]["response_sha256"] is None
        assert rows[denied]["error_detail"] == "budget_exhausted"
        assert rows[failed]["input_tokens"] == 123 and rows[failed]["output_tokens"] == 45


def test_invalid_evidence_cannot_write_partial_rows(world: tuple[Principal, JobRuntime]) -> None:
    principal, runtime = world
    prepared, received = request(), response()
    with system_unit_of_work(runtime, principal, request_id="ai-attempt-invalid") as uow:
        for modified, returned in (
            (replace(prepared, input_sha256="0" * 64), received),
            (
                replace(prepared, parameters=dict(prepared.parameters) | {"prompt": SOURCE_TEXT}),
                received,
            ),
            (prepared, replace(received, response_sha256="0" * 64)),
            (prepared, replace(received, input_tokens=True)),
            (prepared, replace(received, model=RESPONSE_TEXT)),
        ):
            with pytest.raises(AttemptEvidenceRefused):
                record_attempt(
                    uow, request=modified, response=returned, provider="fake", outcome="SUCCESS"
                )
        assert uow.session.execute(select(func.count()).select_from(ai_model_log)).scalar_one() == 0
        assert uow.drain_audit_events() == []


def test_system_principal_cannot_substitute_for_human_evidence(
    world: tuple[Principal, JobRuntime],
) -> None:
    principal, runtime = world
    with system_unit_of_work(
        runtime, system_principal(principal.tenant_id), request_id="ai-attempt-system"
    ) as uow:
        with pytest.raises(AttemptEvidenceRefused, match="AI_ATTEMPT_USER_REQUIRED"):
            record_attempt(
                uow, request=request(), response=response(), provider="fake", outcome="SUCCESS"
            )
        assert uow.drain_audit_events() == []


def test_success_and_failure_evidence_cannot_be_mixed(world: tuple[Principal, JobRuntime]) -> None:
    principal, runtime = world
    with system_unit_of_work(runtime, principal, request_id="ai-attempt-outcome") as uow:
        with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_ATTEMPT_OUTCOME"):
            record_attempt(
                uow,
                request=request(),
                response=response(),
                provider="fake",
                outcome="SUCCESS",
                failure="provider_error",
            )
        with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_ATTEMPT_RESPONSE"):
            record_attempt(
                uow,
                request=request(),
                response=response(),
                provider="fake",
                outcome="DISABLED",
                failure="disabled",
            )
        with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_ATTEMPT_RESPONSE"):
            record_attempt(uow, request=request(), provider="fake", outcome="SUCCESS")
        assert uow.drain_audit_events() == []


def test_intent_commit_unknown_outcome_binding_and_attempt_limit(
    world: tuple[Principal, JobRuntime],
) -> None:
    principal, runtime = world
    job_id = new_id()
    with tenant_session(principal.db_context) as session:
        session.execute(
            insert(job).values(
                tenant_id=principal.tenant_id,
                id=job_id,
                kind="AI_TASK",
                queue="ai",
                params={},
                state="RUNNING",
                created_by=principal.id,
                created_by_kind="USER",
                updated_by_kind="USER",
                updated_by=principal.id,
            )
        )
    prepared = request()
    source = "b" * 64
    # A rolled-back start leaves neither evidence nor an audit fact.
    with system_unit_of_work(runtime, principal, request_id="intent-rollback") as uow:
        record_intent(uow, request=prepared, provider="fake", job_id=job_id, source_sha256=source)
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(audit_event.c.action == "ai_call_intent.record")
            )
            == 0
        )
    for number in range(1, 4):
        with system_unit_of_work(runtime, principal, request_id=f"intent-{number}") as uow:
            intent_id = record_intent(
                uow, request=prepared, provider="fake", job_id=job_id, source_sha256=source
            )
            uow.commit()
        # Simulate a worker disappearing after start, before any known outcome.
        with pytest.raises(AttemptEvidenceRefused, match="AI_OUTCOME_UNKNOWN"):
            with system_unit_of_work(runtime, principal, request_id="unknown-outcome") as uow:
                record_intent(
                    uow, request=prepared, provider="fake", job_id=job_id, source_sha256=source
                )
        for changes in (
            {"provider": "anthropic"},
            {"request": request("changed")},
            {"intent_id": new_id()},
            {"outcome": "DISABLED", "failure": "disabled", "response": None},
        ):
            with pytest.raises(AttemptEvidenceRefused):
                with system_unit_of_work(runtime, principal, request_id="mismatch") as uow:
                    arguments: dict[str, Any] = dict(
                        request=prepared,
                        provider="fake",
                        outcome="SUCCESS",
                        response=response(),
                        intent_id=intent_id,
                    )
                    arguments.update(changes)
                    record_attempt(uow, **arguments)
        with pytest.raises(AttemptEvidenceRefused, match="AI_INTENT_MISMATCH"):
            with system_unit_of_work(
                runtime, replace(principal, id=new_id()), request_id="wrong-human"
            ) as uow:
                record_attempt(
                    uow,
                    request=prepared,
                    provider="fake",
                    outcome="ERROR",
                    failure="provider_error",
                    intent_id=intent_id,
                )
        with tenant_session(principal.db_context, read_only=True) as session:
            assert session.scalar(select(func.count()).select_from(ai_model_log)) == number - 1
        with system_unit_of_work(runtime, principal, request_id="outcome") as uow:
            record_attempt(
                uow,
                request=prepared,
                provider="fake",
                outcome="ERROR",
                failure="provider_error",
                intent_id=intent_id,
            )
            uow.commit()
        with pytest.raises(AttemptEvidenceRefused, match="AI_INTENT_ALREADY_RECORDED"):
            with system_unit_of_work(runtime, principal, request_id="duplicate-outcome") as uow:
                record_attempt(
                    uow,
                    request=prepared,
                    provider="fake",
                    outcome="ERROR",
                    failure="provider_error",
                    intent_id=intent_id,
                )
        with pytest.raises(AttemptEvidenceRefused, match="AI_JOB_INPUT_CHANGED"):
            with system_unit_of_work(runtime, principal, request_id="changed-source") as uow:
                record_intent(
                    uow, request=prepared, provider="fake", job_id=job_id, source_sha256="c" * 64
                )
    with pytest.raises(AttemptEvidenceRefused, match="AI_ATTEMPTS_EXHAUSTED"):
        with system_unit_of_work(runtime, principal, request_id="exhausted") as uow:
            record_intent(
                uow, request=prepared, provider="fake", job_id=job_id, source_sha256=source
            )
    with tenant_session(principal.db_context, read_only=True) as session:
        intents = (
            session.execute(select(ai_call_intent).order_by(ai_call_intent.c.attempt_no))
            .mappings()
            .all()
        )
        assert [row["attempt_no"] for row in intents] == [1, 2, 3]
        events = (
            session.execute(
                select(audit_event).where(audit_event.c.action == "ai_call_intent.record")
            )
            .mappings()
            .all()
        )
        assert len(events) == 3
        assert {event["detail"]["ids"][0] for event in events} == {
            str(row["id"]) for row in intents
        }
        assert all(event["object_id"] is None for event in events)
        retained = json.dumps(
            [dict(row) for row in intents] + [dict(event) for event in events], default=str
        )
        assert SOURCE_TEXT not in retained and RESPONSE_TEXT not in retained
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"state": "QUEUED"},
        {"kind": "AUDIT_CHAIN_VERIFY"},
        {"created_by_kind": "SYSTEM", "created_by": None},
        {"created_by": new_id()},
    ],
)
def test_intent_refuses_unowned_or_nonrunning_ai_job(
    world: tuple[Principal, JobRuntime],
    change: dict[str, Any],
) -> None:
    principal, runtime = world
    job_id = new_id()
    values = dict(
        tenant_id=principal.tenant_id,
        id=job_id,
        kind="AI_TASK",
        queue="ai",
        params={},
        state="RUNNING",
        created_by=principal.id,
        created_by_kind="USER",
        updated_by_kind="SYSTEM",
    )
    with tenant_session(principal.db_context) as session:
        session.execute(insert(job).values(**(values | change)))
    with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_JOB_BINDING"):
        with system_unit_of_work(runtime, principal, request_id="invalid-intent-job") as uow:
            record_intent(
                uow, request=request(), provider="fake", job_id=job_id, source_sha256="b" * 64
            )
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(ai_call_intent)) == 0


@pytest.mark.parametrize(
    "classification",
    [
        {"provider_failure_code": "raw provider diagnostic"},
        {"provider_failure_code": "AI_TIMEOUT"},
        {"provider_failure_code": "AI_AUTHENTICATION", "provider_retryable": True},
        {"provider_retryable": True},
        {"provider_failure_code": "AI_PROVIDER_ERROR", "provider_retryable": "yes"},
    ],
)
def test_provider_failure_classification_refuses_untrusted_metadata(
    world: tuple[Principal, JobRuntime],
    classification: dict[str, Any],
) -> None:
    principal, runtime = world
    with pytest.raises(AttemptEvidenceRefused, match="AI_INVALID_PROVIDER_FAILURE"):
        with system_unit_of_work(
            runtime, principal, request_id="bad-failure-classification"
        ) as uow:
            record_attempt(
                uow,
                request=request(),
                provider="fake",
                outcome="ERROR",
                failure="provider_error",
                **classification,
            )
    with tenant_session(principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 0
