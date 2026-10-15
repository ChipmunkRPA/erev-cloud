"""Attempt metadata and AUD-FACT evidence commit together without model text."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, system_principal
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, audit_event
from erev_api.domain.ai.attempts import AttemptEvidenceRefused, record_attempt
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.domain.ai.preparation import prepare_request
from erev_api.domain.ai.templates import load_template
from erev_api.enums import PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from sqlalchemy import func, select
from support.db import TestDatabase
from support.principals import member

pytestmark = pytest.mark.pg
SOURCE_TEXT = "Sensitive contract paragraph never retained in a model log"
RESPONSE_TEXT = "Sensitive provider answer never retained in a model log"


def request() -> AIRequest:
    return prepare_request(
        template=load_template("contract-review", 1),
        model="configured-model",
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
