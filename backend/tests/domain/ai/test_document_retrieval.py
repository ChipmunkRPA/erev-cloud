"""Encrypted document input is read as the current human before isolated parsing."""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, audit_event, job, role_assignment, tenant
from erev_api.domain.ai.access import AIAccessRefused, AICancelled
from erev_api.domain.ai.document_retrieval import RetrievedExtraction, retrieve_document
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.settings import AISettingsRefused
from erev_api.enums import FilePurpose, RegistryCategory
from erev_api.files.store import store_file
from erev_api.jobs.context import JobContext
from erev_api.problems import Problem
from sqlalchemy import func, select, update
from support.principals import colleague
from support.reference import assign
from support.rows import publish_registry_version
from tests.api.test_explain_api import World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401
from tests.domain.ai.test_narrative_retrieval import context_for


def test_document_admission_rechecks_and_no_provider_evidence(
    world: World, clock: FrozenClock, keyring: KeyRing
) -> None:
    pdf = (
        Path(__file__).parents[2] / "fixtures/ai/documents/Kinsley-Marrow-Order-Form-2026-10.pdf"
    ).read_bytes()
    with world.place.uow() as uow:
        source = store_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(pdf),
            original_filename="contract.pdf",
            media_type="application/pdf",
        )
        uow.commit()
    base = context_for(world.maya.member, clock)

    def with_runtime(context: JobContext) -> JobContext:
        return JobContext(
            job_id=context.job_id,
            tenant_id=context.tenant_id,
            kind=context.kind,
            principal=context.principal,
            runtime=replace(context.runtime, keyring=keyring, files=world.app.state.file_store),
        )

    context = with_runtime(base)
    calls: list[bytes] = []
    mode = {"value": "normal"}
    text = "Customer Acme; contact buyer@example.com; twelve months."

    def parser(data: bytes, *, send_contract_text: bool) -> tuple[str, ...]:
        assert send_contract_text and data == pdf
        calls.append(data)
        # Changes committed during parsing must be observed by fresh admission afterward.
        with tenant_session(world.place.principal.db_context) as session:
            if mode["value"] == "disable":
                session.execute(
                    update(tenant)
                    .where(tenant.c.id == world.place.tenant_id)
                    .values(
                        ai_disabled_at=clock.now(),
                        ai_disabled_by=world.maya.member.user_id,
                        ai_disabled_by_kind="USER",
                    )
                )
            if mode["value"] == "revoke":
                session.execute(
                    update(role_assignment)
                    .where(role_assignment.c.membership_id == world.maya.member.membership_id)
                    .values(
                        revoked_at=clock.now(),
                        revoked_by=world.maya.member.user_id,
                        revoked_by_kind="USER",
                    )
                )
        return (text,)

    def retrieve(ctx: JobContext = context, **extra: Any) -> RetrievedExtraction:
        return retrieve_document(
            ctx,
            file_id=source["id"],
            allowed_paths=frozenset({"customer"}),
            max_tokens=1024,
            extract_pages=parser,
            platform_kill_switch=lambda: False,
            **extra,
        )

    def settings(send: bool) -> None:
        clock.advance(timedelta(seconds=1))
        with tenant_session(world.place.principal.db_context) as session:
            publish_registry_version(
                session,
                tenant_id=world.place.tenant_id,
                category=RegistryCategory.AI,
                values={"ai.enabled": True, "ai.send_contract_text": send},
                at=clock.now(),
            )

    with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
        retrieve()
    settings(False)
    with pytest.raises(PreparationRefused, match="AI_TEXT_DISABLED"):
        retrieve()
    assert calls == []
    settings(True)
    with pytest.raises(PreparationRefused, match="AI_INPUT_CHANGED"):
        retrieve(expected_file_sha256="0" * 64)
    other = colleague(world.place.tenant_id, "document_outsider")
    assign(other, "viewer")
    with pytest.raises(Problem) as denied:
        retrieve(with_runtime(context_for(other, clock)))
    assert denied.value.slug == "not-found"
    assert calls == []
    result = retrieve(expected_file_sha256=str(source["sha256"]))
    assert result.source_sha256 == source["sha256"]
    assert result.principal.id == world.maya.member.user_id
    assert result.pages == (text,) and result.prepared.document_id == UUID(str(source["id"]))
    assert "buyer@example.com" not in repr(result.prepared.request.messages)
    mode["value"] = "disable"
    with pytest.raises(AISettingsRefused, match="AI_DISABLED"):
        retrieve()
    with tenant_session(world.place.principal.db_context) as session:
        session.execute(
            update(tenant)
            .where(tenant.c.id == world.place.tenant_id)
            .values(ai_disabled_at=None, ai_disabled_by=None, ai_disabled_by_kind=None)
        )
        session.execute(
            update(job).where(job.c.id == context.job_id).values(cancel_requested_at=clock.now())
        )
    with pytest.raises(AICancelled, match="AI_CANCELLED"):
        retrieve()
    assert len(calls) == 2
    mode["value"] = "revoke"
    with pytest.raises(AIAccessRefused, match="AI_PERMISSION_DENIED"):
        retrieve(with_runtime(context_for(world.maya.member, clock)))
    assert len(calls) == 3
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert session.scalar(select(func.count()).select_from(ai_model_log)) == 0
        assert session.scalar(select(func.count()).select_from(ai_proposal)) == 0
        downloads = list(
            session.execute(
                select(audit_event).where(
                    audit_event.c.action == "file.download", audit_event.c.object_id == source["id"]
                )
            ).mappings()
        )
        assert len(downloads) == 3
        assert all(
            row["actor_kind"] == "USER" and row["actor_id"] == world.maya.member.user_id
            for row in downloads
        )
