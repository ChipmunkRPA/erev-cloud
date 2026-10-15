"""Human draft acceptance is atomic, permissioned, replay-safe and never posts revenue."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.ai_provenance import accepted_draft_proposals
from erev_api.clock import FrozenClock
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    ai_proposal,
    audit_event,
    contract,
    customer,
    file_attachment,
    file_object,
    subledger_line,
)
from erev_api.domain.ai import acceptance
from erev_api.enums import FilePurpose
from erev_api.files.store import put_file
from erev_api.problems import Problem
from erev_api.schemas.ai import AIExtractionDraftIn
from sqlalchemy import func, insert, select, update
from support.http import call
from support.principals import colleague, cookie_headers
from support.reference import holding
from support.rows import RowContext, ai_proposal_row
from tests.api.test_ai_extractions import source_file
from tests.api.test_explain_api import PLATFORM, World
from tests.api.test_explain_api import app as app  # noqa: F401
from tests.api.test_explain_api import world as world  # noqa: F401


def test_acceptance_is_atomic_and_replay_rechecks_source(
    world: World, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = world.maya
    source = source_file(world)
    with world.place.uow() as uow:
        name = uow.session.scalar(select(customer.c.name).where(customer.c.id == world.customer_id))
        text_file = put_file(
            uow,
            purpose=FilePurpose.AI_DOCUMENT_TEXT,
            stream=io.BytesIO(json.dumps({"pages": ["Synthetic retained evidence"]}).encode()),
            original_filename=None,
            media_type="application/json",
        )
        row = ai_proposal_row(RowContext(world.place.tenant_id, actor.member.user_id), uow.session)
        row.update(
            kind="CONTRACT_EXTRACTION",
            file_object_id=source,
            document_text_file_id=text_file.row["id"],
            content=[
                {"path": "customer_name", "value": name},
                {"path": "lines.0", "value": {"product_code": PLATFORM, "amount": "120.00"}},
            ],
            created_at=clock.now(),
            expires_at=clock.now() + timedelta(days=30),
        )
        uow.session.execute(insert(ai_proposal).values(**row))
        uow.commit()
    proposal_id = row["id"]
    path = f"/api/v1/ai/proposals/{proposal_id}/accept"
    body: dict[str, Any] = {
        "command": "contract.create_draft",
        "entity_code": "AVM-US",
        "field_decisions": [
            {"path": "customer_name", "decision": "ACCEPT"},
            {"path": "lines.0", "decision": "ACCEPT"},
        ],
        "header_bindings": {"customer_name": "customer"},
        "line_bindings": {"lines.0": "O1"},
        "draft": {
            "external_id": "AI-DRAFT-001",
            "customer_id": str(world.customer_id),
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-01-01",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": PLATFORM,
                    "quantity": "1",
                    "total_price": {"amount": "120.00", "currency": "USD"},
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                }
            ],
        },
    }
    headers = cookie_headers(actor.token, actor.csrf_token)
    detail = call(world.app, "GET", path.removesuffix("/accept"), headers=headers)
    assert detail.status_code == 200, detail.text
    etag = detail.headers["ETag"]
    missing_etag = call(world.app, "POST", path, json=body, headers=headers)
    assert missing_etag.status_code == 428, missing_etag.text
    viewer = holding(world.app, colleague(world.place.tenant_id, "no_create"), "viewer")
    denied_headers = cookie_headers(viewer.token, viewer.csrf_token) | {"If-Match": etag}
    denied = call(world.app, "POST", path, json=body, headers=denied_headers)
    assert denied.status_code == 403, denied.text
    mismatched = deepcopy(body)
    mismatched["draft"]["lines"][0]["total_price"]["amount"] = "121.00"
    refused = call(
        world.app,
        "POST",
        path,
        json=mismatched,
        headers=cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag},
    )
    assert refused.status_code == 422, refused.text
    rejected = deepcopy(body)
    rejected["field_decisions"] = [
        {"path": path, "decision": "REJECT", "reason": "Reviewer excludes this field"}
        for path in ("customer_name", "lines.0")
    ]
    rejected["header_bindings"] = {}
    rejected["line_bindings"] = {}
    empty = call(
        world.app,
        "POST",
        path,
        json=rejected,
        headers=cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag},
    )
    assert empty.status_code == 422, empty.text
    assert "AI_REVIEW_EMPTY_ACCEPTANCE" in empty.text
    parsed = AIExtractionDraftIn.model_validate(body)
    with pytest.raises(Problem) as expired:
        with replace(world.place, clock=FrozenClock(row["expires_at"])).uow() as uow:
            acceptance.accept_draft(uow, proposal_id, parsed, check_version=lambda _: None)
    assert expired.value.slug == "invalid-transition"

    def fail_transition(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected transition failure")

    with monkeypatch.context() as patch:
        patch.setattr(acceptance, "apply", fail_transition)
        with pytest.raises(RuntimeError, match="injected transition failure"):
            with world.place.uow() as uow:
                acceptance.accept_draft(uow, proposal_id, parsed, check_version=lambda _: None)
                uow.commit()
    with tenant_session(world.place.principal.db_context, read_only=True) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(file_attachment)
                .where(file_attachment.c.file_object_id == source)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(contract)
                .where(contract.c.external_id == "AI-DRAFT-001")
            )
            == 0
        )
        assert (
            session.scalar(select(ai_proposal.c.status).where(ai_proposal.c.id == proposal_id))
            == "proposed"
        )
    request_headers = [
        cookie_headers(actor.token, actor.csrf_token) | {"If-Match": etag} for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(call, world.app, "POST", path, json=body, headers=h)
            for h in request_headers
        ]
        responses = [future.result(timeout=30) for future in futures]
    assert sorted(response.status_code for response in responses) == [201, 412], [
        r.text for r in responses
    ]
    accepted = next(response for response in responses if response.status_code == 201)
    winning_headers = request_headers[responses.index(accepted)]
    contract_id = UUID(accepted.json()["contract_id"])
    assert accepted.headers["Location"] == f"/api/v1/contracts/{contract_id}"
    replay = call(world.app, "POST", path, json=body, headers=winning_headers)
    assert replay.status_code == 201 and replay.json() == accepted.json(), replay.text
    with tenant_session(world.place.principal.db_context) as session:
        saved = (
            session.execute(select(ai_proposal).where(ai_proposal.c.id == proposal_id))
            .mappings()
            .one()
        )
        assert saved["status"] == "accepted" and saved["accepted_object_id"] == contract_id
        assert saved["accepted_by"] == actor.member.user_id and saved["row_version"] == 2
        assert len(saved["field_decisions"]) == 2
        created = (
            session.execute(select(contract).where(contract.c.id == contract_id)).mappings().one()
        )
        assert created["status"] == "DRAFT" and created["created_by"] == actor.member.user_id
        assert (
            session.scalar(
                select(func.count())
                .select_from(subledger_line)
                .where(subledger_line.c.contract_id == contract_id)
            )
            == 0
        )
        attached = (
            session.execute(
                select(file_attachment).where(file_attachment.c.file_object_id == source)
            )
            .mappings()
            .one()
        )
        assert attached["subject_type"] == "contract" and attached["subject_id"] == contract_id
        assert len(accepted_draft_proposals(session, contract_id)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(audit_event)
                .where(
                    audit_event.c.action == "ai_proposal.accept",
                    audit_event.c.object_id == proposal_id,
                )
            )
            == 1
        )
        session.execute(
            update(file_object)
            .where(file_object.c.id == source)
            .values(
                shredded_at=clock.now(),
                shredded_by=actor.member.user_id,
                shredded_by_kind="USER",
                shred_reason="fixture unavailable source",
            )
        )
    unavailable = call(world.app, "POST", path, json=body, headers=winning_headers)
    assert unavailable.status_code == 404, unavailable.text
