"""Public portfolio membership commands retain history and require current parent ETags."""

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.http import call
from support.principals import colleague, cookie_headers, member
from support.reference import approve, assign, entity, get, holding, post

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, contract, legal_entity, obligation, estimate_version
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def test_portfolio_membership_workflow(
    app: FastAPI, app_settings: Settings, keyring: KeyRing, clock: FrozenClock
) -> None:
    world = worlds.k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))
    maya = world.maya
    viewer = holding(app, colleague(maya.member.tenant_id, "portfolio-viewer"), "viewer")
    foreign = holding(app, member(keyring, clock), "revenue_accountant")
    identity = {"code": "SIMILAR-RETURNS", "name": "Similar return profiles"}
    assert post(app, "/api/v1/portfolios", viewer, identity).status_code == 403
    created = post(app, "/api/v1/portfolios", maya, identity)
    assert created.status_code == 201, created.text
    path = created.headers["location"]
    tag = created.headers["etag"]
    assert get(app, path, foreign).status_code == 404
    listed = get(app, "/api/v1/portfolios", viewer, {"count": "true"})
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Erev-Total-Count"] == "1"
    assert [row["code"] for row in listed.json()["items"]] == [identity["code"]]
    contract_id = str(world.contracts[worlds.K01].contract["id"])
    before_computation = world.place.scalar(
        select(contract.c.latest_computation_id).where(contract.c.id == UUID(contract_id))
    )
    other_entity = entity(
        app,
        world.marcus,
        code="PORTFOLIO-OTHER",
        calendar_id=str(world.place.scalar(select(legal_entity.c.calendar_id).limit(1))),
    )
    hidden = holding(
        app,
        colleague(maya.member.tenant_id, "portfolio-hidden"),
        "revenue_accountant",
        entity_ids=[UUID(other_entity["id"])],
    )
    payload = {"contract_id": contract_id, "rationale": "Same return terms and customer profile."}
    assert post(app, path + "/members", maya, payload).status_code == 428
    assert post(app, path + "/members", viewer, payload, if_match=tag).status_code == 403
    joined = post(app, path + "/members", maya, payload, if_match=tag)
    assert joined.status_code == 201, joined.text
    assert joined.headers["etag"] != tag
    assert post(app, path + "/members", maya, payload, if_match=tag).status_code == 412
    tag = joined.headers["etag"]
    assert get(app, path + "/members", hidden, {"count": "true"}).json()["items"] == []
    assert (
        get(app, path + "/members", hidden, {"count": "true"}).headers["X-Erev-Total-Count"] == "0"
    )
    assert post(app, path + "/members", hidden, payload, if_match=tag).status_code == 404
    assert (
        post(
            app,
            path + f"/members/{contract_id}/remove",
            hidden,
            {"rationale": "Hidden"},
            if_match=tag,
        ).status_code
        == 404
    )
    assert post(app, path + "/members", maya, payload, if_match=tag).status_code == 409
    members = get(app, path + "/members", viewer)
    assert members.status_code == 200, members.text
    assert [row["contract_id"] for row in members.json()["items"]] == [contract_id]
    clock.advance(timedelta(seconds=1))
    ended = post(
        app,
        path + f"/members/{contract_id}/remove",
        maya,
        {"rationale": "Customer terms changed."},
        if_match=tag,
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["valid_to_known_at"] is not None
    assert get(app, path + "/members", viewer).json()["items"] == []
    history = get(app, path + "/members", viewer, {"include_history": "true"})
    assert history.status_code == 200, history.text
    assert len(history.json()["items"]) == 1
    clock.advance(timedelta(seconds=1))
    rejoined = post(app, path + "/members", maya, payload, if_match=ended.headers["etag"])
    assert rejoined.status_code == 201, rejoined.text
    assert rejoined.json()["id"] != joined.json()["id"]
    assert (
        len(get(app, path + "/members", viewer, {"include_history": "true"}).json()["items"]) == 2
    )
    assert (
        world.place.scalar(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action.in_(["portfolio.member_join", "portfolio.member_leave"]))
        )
        == 3
    )
    assert (
        world.place.scalar(
            select(contract.c.latest_computation_id).where(
                contract.c.id == world.contracts[worlds.K01].contract["id"]
            )
        )
        == before_computation
    )

    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = rejoined.headers["etag"]
    updated = call(
        app, "PUT", path, json={**identity, "name": "Updated population"}, headers=headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Updated population"
    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = rejoined.headers["etag"]
    assert call(app, "PUT", path, json=identity, headers=headers).status_code == 412

    definition = {"element_code": "RETURNS", "estimate_kind": "RETURN_RATE", "method": "RATE"}
    current_tag = updated.headers["etag"]
    assert (
        post(app, path + "/estimates", viewer, definition, if_match=current_tag).status_code == 403
    )
    assert (
        post(app, path + "/estimates", hidden, definition, if_match=current_tag).status_code == 404
    )
    limited_member = colleague(maya.member.tenant_id, "portfolio-limited-writer")
    assign(limited_member, "viewer")
    limited = holding(
        app, limited_member, "revenue_accountant", entity_ids=[UUID(other_entity["id"])]
    )
    assert (
        post(app, path + "/estimates", limited, definition, if_match=current_tag).status_code == 404
    )
    defined = post(app, path + "/estimates", maya, definition, if_match=current_tag)
    assert defined.status_code == 201, defined.text
    assert defined.json()["portfolio_id"] == created.json()["id"]
    assert defined.json()["contract_id"] is None
    assert defined.json()["latest_version"] is None
    assert get(app, defined.headers["location"], viewer).json() == defined.json()
    assert get(app, defined.headers["location"], hidden).status_code == 404
    listed = get(app, path + "/estimates", viewer, {"count": "true"})
    assert listed.headers["X-Erev-Total-Count"] == "1"
    assert listed.json()["items"] == [defined.json()]
    assert get(app, path + "/estimates", hidden).status_code == 404
    assert post(app, path + "/estimates", maya, definition, if_match=current_tag).status_code == 412
    current_tag = get(app, path, maya).headers["etag"]
    assert post(app, path + "/estimates", maya, definition, if_match=current_tag).status_code == 422
    assert (
        post(
            app,
            path + "/estimates",
            maya,
            {**definition, "estimate_kind": "EAC"},
            if_match=current_tag,
        ).status_code
        == 422
    )
    clock.advance(timedelta(seconds=1))
    removed = post(
        app,
        path + f"/members/{contract_id}/remove",
        maya,
        {"rationale": "End membership"},
        if_match=current_tag,
    )
    assert removed.status_code == 200, removed.text
    # Removing the last current member cannot reveal shared evidence to an excluded entity.
    assert get(app, path + "/estimates", hidden).status_code == 404

    versions_path = defined.headers["location"] + "/versions"
    values = {
        "effective_date": "2026-09-01",
        "currency": "USD",
        "rate": "0.10",
        "parameters": {
            "carrying_cost_per_unit": "12.50",
            "recovery_cost_per_unit": "1.00",
            "window_end_date": "2026-12-31",
        },
        "rationale": "Observed returns for the shared population",
    }
    current_tag = get(app, path, maya).headers["etag"]
    assert post(app, versions_path, maya, values).status_code == 428
    assert post(app, versions_path, hidden, values, if_match=current_tag).status_code == 404
    assert (
        post(
            app, versions_path, maya, {**values, "currency": None}, if_match=current_tag
        ).status_code
        == 422
    )
    assert (
        post(app, versions_path, maya, {**values, "rate": "1.01"}, if_match=current_tag).status_code
        == 422
    )
    assert (
        post(
            app, versions_path, maya, {**values, "method": "ENTERED_AMOUNT"}, if_match=current_tag
        ).status_code
        == 422
    )
    version = post(app, versions_path, maya, values, if_match=current_tag)
    assert version.status_code == 201, version.text
    assert version.json()["status"] == "DRAFT"
    assert version.json()["version_no"] == 1
    version_path = version.headers["location"]
    assert get(app, version_path, viewer).json() == version.json()
    assert get(app, version_path, hidden).status_code == 404
    current_tag = get(app, path, maya).headers["etag"]
    assert post(app, versions_path, maya, values, if_match=current_tag).status_code == 409
    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = version.headers["etag"]
    edited = call(app, "PUT", version_path, json={**values, "rate": "0.15"}, headers=headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["rate"] == "0.15"
    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = version.headers["etag"]
    assert call(app, "PUT", version_path, json=values, headers=headers).status_code == 412
    discarded = post(app, version_path + "/discard", maya, {}, if_match=edited.headers["etag"])
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "VOIDED"
    headers = cookie_headers(maya.token, maya.csrf_token, key=True)
    headers["If-Match"] = discarded.headers["etag"]
    assert call(app, "PUT", version_path, json=values, headers=headers).status_code == 409
    current_tag = get(app, path, maya).headers["etag"]
    second = post(app, versions_path, maya, values, if_match=current_tag)
    assert second.status_code == 201, second.text
    assert second.json()["version_no"] == 2
    history = get(app, versions_path, viewer, {"count": "true"})
    assert history.headers["X-Erev-Total-Count"] == "2"
    assert [v["status"] for v in history.json()["items"]] == ["DRAFT", "VOIDED"]
    assert get(app, versions_path, hidden).status_code == 404
    assert (
        world.place.scalar(
            select(contract.c.latest_computation_id).where(contract.c.id == UUID(contract_id))
        )
        == before_computation
    )

    file_id = worlds.evidence_file(app, maya, "portfolio-returns.pdf")
    subject = {"subject_type": "estimate_version", "subject_id": second.json()["id"]}
    attached = post(app, "/api/v1/attachments", maya, {**subject, "file_object_id": file_id})
    assert attached.status_code == 201, attached.text
    visible_files = get(app, "/api/v1/attachments", viewer, subject)
    assert visible_files.status_code == 200, visible_files.text
    assert [f["id"] for f in visible_files.json()["items"]] == [attached.json()["id"]]
    hidden_files = get(app, "/api/v1/attachments", hidden, subject)
    assert hidden_files.status_code == 200, hidden_files.text
    assert hidden_files.json()["items"] == []
    assert get(app, f"/api/v1/files/{file_id}/content", hidden).status_code == 404
    assert get(app, f"/api/v1/files/{file_id}/content", viewer).status_code == 200
    own_file = worlds.evidence_file(app, hidden, "outside-population.pdf")
    assert (
        post(
            app, "/api/v1/attachments", hidden, {**subject, "file_object_id": own_file}
        ).status_code
        == 404
    )
    # Broader read access is not permission to attach for entities outside the write grant.
    limited_file = worlds.evidence_file(app, limited, "limited-write.pdf")
    assert (
        post(
            app, "/api/v1/attachments", limited, {**subject, "file_object_id": limited_file}
        ).status_code
        == 404
    )
    voided = post(
        app,
        f"/api/v1/attachments/{attached.json()['id']}/void",
        maya,
        {"reason": "Replaced supporting evidence"},
    )
    assert voided.status_code == 200, voided.text

    # Audit evidence remains linked to former members and carries actual version changes.
    changes = world.place.rows(
        select(audit_event)
        .where(
            audit_event.c.object_type == "estimate_version",
            audit_event.c.object_id == UUID(version.json()["id"]),
        )
        .order_by(audit_event.c.occurred_at, audit_event.c.action)
    )
    by_action = {event["action"]: event for event in changes}
    assert set(by_action) == {
        "estimate_version.create",
        "estimate_version.update",
        "estimate_version.discard",
    }
    update_event = by_action["estimate_version.update"]
    assert update_event["before"]["rate"] == version.json()["rate"]
    assert update_event["after"]["rate"] == "0.15"
    assert update_event["object_version"] == str(edited.json()["row_version"])
    assert update_event["detail"]["contract_id"] == contract_id
    assert by_action["estimate_version.discard"]["after"]["status"] == "VOIDED"

    # The owner-selected total-by-SSP basis is explicit and cannot mix with a member rate.
    current_tag = get(app, path, maya).headers["etag"]
    breakage = post(
        app,
        path + "/estimates",
        maya,
        {"element_code": "BREAKAGE", "estimate_kind": "BREAKAGE", "method": "RATE"},
        if_match=current_tag,
    )
    assert breakage.status_code == 201, breakage.text
    breakage_path = breakage.headers["location"] + "/versions"
    current_tag = get(app, path, maya).headers["etag"]
    total_values = {
        "effective_date": "2026-10-23",
        "currency": "USD",
        "rationale": "Shared total by SSP",
        "parameters": {},
    }
    assert post(app, breakage_path, maya, total_values, if_match=current_tag).status_code == 422
    total_values["parameters"] = {"portfolio_total_breakage_quantity": "12.000000000000000001"}
    assert (
        post(
            app, breakage_path, maya, {**total_values, "rate": "0.1"}, if_match=current_tag
        ).status_code
        == 422
    )
    saved_total = post(app, breakage_path, maya, total_values, if_match=current_tag)
    assert saved_total.status_code == 201, saved_total.text
    assert saved_total.json()["parameters"] == total_values["parameters"]

    preview_path = saved_total.headers["location"] + "/allocation-preview"
    assert get(app, preview_path, foreign).status_code == 404
    assert get(app, preview_path, hidden).status_code == 404
    # This ordinary subscription population has no redemption obligations. Never fabricate weights.
    preview_response = get(app, preview_path, maya)
    assert preview_response.status_code == 422, preview_response.text

    from erev_api.approvals import subjects
    from erev_api.db.session import DbContext, tenant_session

    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        before_basis = subjects.estimate_version_content(session, UUID(saved_total.json()["id"]))
        approval_entities = subjects.estimate_version_entities(
            session, UUID(saved_total.json()["id"])
        )
        original_entity = session.scalar(
            select(contract.c.contracting_entity_id).where(contract.c.id == UUID(contract_id))
        )
        assert approval_entities.ids == frozenset({original_entity})
        assert not approval_entities.all_entities
        assert not approval_entities.covered_by(frozenset({UUID(other_entity["id"])}))
    basis = before_basis["portfolio_basis"]
    assert basis["precedence"] == "SHARED_OVERRIDES_LOCAL"
    assert basis["breakage_allocation"] == "TOTAL_BY_SSP"
    assert {m["contract_id"] for m in basis["members"]} == {contract_id}
    assert basis["members"][0]["latest_computation_id"] == str(before_computation)
    current_tag = get(app, path, maya).headers["etag"]
    rejoined = post(app, path + "/members", maya, payload, if_match=current_tag)
    assert rejoined.status_code == 201, rejoined.text
    with tenant_session(context) as session:
        after_basis = subjects.estimate_version_content(session, UUID(saved_total.json()["id"]))
    assert after_basis != before_basis
    assert len(after_basis["portfolio_basis"]["memberships"]) == len(basis["memberships"]) + 1

    # Membership snapshots use the requested record cutoff, including removed/rejoined history.
    from erev_api.domain.contracts import bundles

    history = after_basis["portfolio_basis"]["memberships"]
    from datetime import datetime

    first_join = min(datetime.fromisoformat(m["valid_from_known_at"]) for m in history)
    removed = min(
        datetime.fromisoformat(m["valid_to_known_at"]) for m in history if m["valid_to_known_at"]
    )
    latest_join = max(datetime.fromisoformat(m["valid_from_known_at"]) for m in history)
    with tenant_session(context) as session:
        source = dict(
            session.execute(select(contract).where(contract.c.id == UUID(contract_id)))
            .mappings()
            .one()
        )
        population = {UUID(contract_id): source}
        assert (
            bundles.portfolio_inputs(session, population, first_join - timedelta(microseconds=1))
            == ()
        )
        first_snapshot = bundles.portfolio_inputs(session, population, first_join)
        assert len(first_snapshot) == 1
        assert first_snapshot[0].code == path.rsplit("/", 1)[-1]
        assert first_snapshot[0].member_contract_keys == (source["external_id"],)
        assert bundles.portfolio_inputs(session, population, removed) == ()
        assert bundles.portfolio_inputs(session, population, latest_join) == first_snapshot
        built = bundles.build(session, source["combination_group_id"], latest_join, [], "DRY_RUN")
        assert built.group.portfolios == first_snapshot

    # Shared targets bind the original obligations of every current member.
    target_key = world.place.scalar(
        select(obligation.c.obligation_key)
        .where(obligation.c.contract_id == UUID(contract_id))
        .limit(1)
    )
    current_tag = get(app, path, maya).headers["etag"]
    target_body = {
        "element_code": "TARGETED-RETURNS",
        "estimate_kind": "RETURN_RATE",
        "method": "RATE",
    }
    for invalid in [["MISSING-OBLIGATION"], [target_key, target_key]]:
        refused = post(
            app,
            path + "/estimates",
            maya,
            {**target_body, "target_obligation_keys": invalid},
            if_match=current_tag,
        )
        assert refused.status_code == 422, refused.text
        assert get(app, path, maya).headers["etag"] == current_tag
    targeted = post(
        app,
        path + "/estimates",
        maya,
        {**target_body, "target_obligation_keys": [target_key]},
        if_match=current_tag,
    )
    assert targeted.status_code == 201, targeted.text
    assert targeted.json()["target_obligation_keys"] == [target_key]
    assert targeted.json()["allocation_target"] == "OBLIGATIONS"
    assert get(app, targeted.headers["location"], maya).json() == targeted.json()

    preview_version = post(
        app,
        targeted.headers["location"] + "/versions",
        maya,
        values,
        if_match=get(app, path, maya).headers["etag"],
    )
    assert preview_version.status_code == 201, preview_version.text
    impact_path = preview_version.headers["location"] + "/impact-preview"
    assert get(app, impact_path, hidden).status_code == 404
    impact = get(app, impact_path, maya)
    assert impact.status_code == 200, impact.text
    assert impact.json()["basis"] == "SHARED_RETURN_DRY_RUN"
    assert len(impact.json()["groups"]) == 1
    assert impact.json()["groups"][0]["members"][0]["contract_id"] == contract_id
    assert impact.json()["groups"][0]["source_computation_id"] == str(before_computation)
    assert len(impact.json()["groups"][0]["input_sha256"]) == 64
    assert impact.json()["groups"][0]["members"][0]["revenue_by_period"]
    repeated = get(app, impact_path, maya).json()["groups"]
    assert repeated[0]["members"] == impact.json()["groups"][0]["members"]
    assert repeated[0]["catch_up_amount"] == impact.json()["groups"][0]["catch_up_amount"]
    after_preview = get(app, preview_version.headers["location"], maya).json()
    assert after_preview["status"] == "DRAFT"
    assert after_preview["applied_event_ids"] == []
    assert (
        world.place.scalar(
            select(contract.c.latest_computation_id).where(contract.c.id == UUID(contract_id))
        )
        == before_computation
    )

    retained_basis = after_preview["portfolio_application_basis"]
    assert retained_basis["portfolio_id"] == path.rsplit("/", 1)[-1]
    assert retained_basis["members"][0]["contract_id"] == contract_id
    assert retained_basis["members"][0]["obligation_keys"] == [target_key]
    clock.advance(timedelta(seconds=1))
    left = post(
        app,
        path + "/members/" + contract_id + "/remove",
        maya,
        {"rationale": "Retained application scope check"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert left.status_code == 200, left.text
    assert (
        get(app, preview_version.headers["location"], maya).json()["portfolio_application_basis"]
        == retained_basis
    )
    assert get(app, impact_path, maya).status_code == 422
    from erev_api.db import transitions
    from sqlalchemy import update
    from sqlalchemy.exc import DBAPIError
    from erev_api.domain.contracts import estimates as estimate_service

    saved_id = UUID(preview_version.json()["id"])
    with tenant_session(context) as session:
        saved_row = dict(
            session.execute(select(estimate_version).where(estimate_version.c.id == saved_id))
            .mappings()
            .one()
        )
        frozen_input = bundles.build(
            session,
            source["combination_group_id"],
            clock.now(),
            [estimate_service._changed_event(saved_row, None, None)],
            "DRY_RUN",
            pending_contract_id=UUID(contract_id),
        )
        shared_input = next(
            v
            for v in frozen_input.estimate_versions
            if v.version_key.endswith("TARGETED-RETURNS@v1")
        )
        assert shared_input.portfolio_member_contract_keys == (source["external_id"],)
        assert frozen_input.group.portfolios[0].member_contract_keys == (source["external_id"],)
        # The real database guard makes the saved application immutable on submission.
        with session.begin_nested() as status_savepoint:
            transitions.apply(
                session,
                "estimate_version",
                saved_id,
                to_status="SUBMITTED",
                expected_status="DRAFT",
                set_values={"content_sha256": "0" * 64},
            )
            with pytest.raises(DBAPIError, match="EREV-TRN-001"), session.begin_nested():
                session.execute(
                    update(estimate_version)
                    .where(estimate_version.c.id == saved_id)
                    .values(portfolio_application_basis={})
                )
            status_savepoint.rollback()

    # Restore membership, save the current basis, then exercise real public approval.
    joined = post(
        app,
        path + "/members",
        maya,
        {"contract_id": contract_id, "rationale": "Apply shared returns"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert joined.status_code == 201, joined.text
    version_path = preview_version.headers["location"]
    saved = call(
        app,
        "PUT",
        version_path,
        headers={
            **cookie_headers(maya.token, maya.csrf_token, key=True),
            "If-Match": get(app, version_path, maya).headers["etag"],
        },
        json=values,
    )
    assert saved.status_code == 200, saved.text
    missing = post(app, version_path + "/submit", maya, {}, if_match=saved.headers["etag"])
    assert missing.status_code == 422, missing.text
    evidence = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "subject_type": "estimate_version",
            "subject_id": str(saved_id),
            "file_object_id": file_id,
        },
    )
    assert evidence.status_code == 201, evidence.text
    submitted = post(
        app,
        version_path + "/submit",
        maya,
        {},
        if_match=get(app, version_path, maya).headers["etag"],
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    request_id = submitted.json()["approval_request_id"]
    assert approve(app, request_id, maya).status_code == 403
    approved = approve(app, request_id, world.marcus)
    assert approved.status_code == 200, approved.text
    applied = get(app, version_path, maya).json()
    assert applied["status"] == "APPROVED"
    assert len(applied["applied_event_ids"]) == 1
    assert (
        world.place.scalar(
            select(contract.c.latest_computation_id).where(contract.c.id == UUID(contract_id))
        )
        != before_computation
    )

    # A submitted follow-up can be withdrawn without changing the applied version.
    followup = post(
        app,
        targeted.headers["location"] + "/versions",
        maya,
        values,
        if_match=get(app, path, maya).headers["etag"],
    )
    assert followup.status_code == 201, followup.text
    follow_path = followup.headers["location"]
    attached = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "subject_type": "estimate_version",
            "subject_id": followup.json()["id"],
            "file_object_id": file_id,
        },
    )
    assert attached.status_code == 201, attached.text
    pending = post(
        app, follow_path + "/submit", maya, {}, if_match=get(app, follow_path, maya).headers["etag"]
    )
    assert pending.status_code == 200, pending.text
    withdrawn = post(app, follow_path + "/withdraw", maya, {}, if_match=pending.headers["etag"])
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "WITHDRAWN"
    assert withdrawn.json()["applied_event_ids"] == []
    assert get(app, version_path, maya).json()["status"] == "APPROVED"

    # Removing the final member does not silently alter its approved estimate. A new
    # independently approved version explicitly ends the scope from its effective date.
    clock.advance(timedelta(seconds=1))
    removed = post(
        app,
        path + "/members/" + contract_id + "/remove",
        maya,
        {"rationale": "End this shared return population"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert removed.status_code == 200, removed.text
    retirement = post(
        app,
        targeted.headers["location"] + "/versions",
        maya,
        {**values, "effective_date": "2026-10-01", "rationale": "Return to member estimates"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert retirement.status_code == 201, retirement.text
    retire_path = retirement.headers["location"]
    basis = retirement.json()["portfolio_application_basis"]
    assert basis["members"] == []
    assert [m["contract_id"] for m in basis["retired_members"]] == [contract_id]
    preview = get(app, retire_path + "/impact-preview", maya)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["members"][0]["contract_id"] == contract_id
    assert get(app, version_path, maya).json()["status"] == "APPROVED"
    attached = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "subject_type": "estimate_version",
            "subject_id": retirement.json()["id"],
            "file_object_id": file_id,
        },
    )
    assert attached.status_code == 201, attached.text
    submitted = post(
        app, retire_path + "/submit", maya, {}, if_match=get(app, retire_path, maya).headers["etag"]
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    retired = get(app, retire_path, maya).json()
    assert retired["status"] == "APPROVED"
    assert len(retired["applied_event_ids"]) == 1
    assert get(app, version_path, maya).json()["status"] == "SUPERSEDED"
    with tenant_session(context) as session:
        bundle = bundles.build(session, source["combination_group_id"], clock.now(), [], "DRY_RUN")
        ending = next(
            v
            for v in bundle.estimate_versions
            if v.version_no == retired["version_no"] and v.element_code == "TARGETED-RETURNS"
        )
        original = next(
            v
            for v in bundle.estimate_versions
            if v.version_no == 1 and v.element_code == "TARGETED-RETURNS"
        )
        assert ending.portfolio_member_contract_keys == ()
        assert original.portfolio_member_contract_keys == (source["external_id"],)
        assert ending.effective_date.isoformat() == "2026-10-01"

    # New members resolve the definition's common keys into their own original IDs,
    # without rewriting the definition or any historical version's saved bindings.
    from support.factories import booked_contract, computed

    clone_body = worlds.k01_body(source["customer_id"])
    clone_body["external_id"] = "NEW-SHARED-MEMBER"
    clone = booked_contract(world.place, clone_body, activate=True)
    computed(world.place, clone.combination_group["id"])
    new_id = str(clone.contract["id"])
    joined = post(
        app,
        path + "/members",
        maya,
        {"contract_id": new_id, "rationale": "New member with the same target keys"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert joined.status_code == 201, joined.text
    onboarding = post(
        app,
        targeted.headers["location"] + "/versions",
        maya,
        {**values, "effective_date": "2026-10-01"},
        if_match=get(app, path, maya).headers["etag"],
    )
    assert onboarding.status_code == 201, onboarding.text
    new_path = onboarding.headers["location"]
    binding = onboarding.json()["portfolio_application_basis"]["members"][0]
    assert binding["contract_id"] == new_id
    assert binding["obligation_keys"] == [target_key]
    assert set(binding["obligation_ids"]).isdisjoint(retained_basis["members"][0]["obligation_ids"])
    assert get(app, targeted.headers["location"], maya).json()["target_obligation_keys"] == [
        target_key
    ]
    assert get(app, version_path, maya).json()["portfolio_application_basis"] == retained_basis
    preview = get(app, new_path + "/impact-preview", maya)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["members"][0]["contract_id"] == new_id
    attached = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "subject_type": "estimate_version",
            "subject_id": onboarding.json()["id"],
            "file_object_id": file_id,
        },
    )
    assert attached.status_code == 201, attached.text
    submitted = post(
        app, new_path + "/submit", maya, {}, if_match=get(app, new_path, maya).headers["etag"]
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    assert len(get(app, new_path, maya).json()["applied_event_ids"]) == 1

    # A rate with no monetary amounts is independent of the version's denomination.
    # No GBP/USD rate is installed: both the preview and real application must work.
    from support.reference import put

    enabled = put(
        app, "/api/v1/tenant-currencies", world.marcus, {"currency_codes": ["USD", "GBP"]}
    )
    assert enabled.status_code == 200, enabled.text
    rate_only = post(
        app,
        targeted.headers["location"] + "/versions",
        maya,
        {
            **values,
            "currency": "GBP",
            "effective_date": "2026-10-01",
            "rate": "0.15",
            "parameters": {
                "carrying_cost_per_unit": "0",
                "recovery_cost_per_unit": "0",
                "window_end_date": "2026-12-31",
            },
        },
        if_match=get(app, path, maya).headers["etag"],
    )
    assert rate_only.status_code == 201, rate_only.text
    rate_path = rate_only.headers["location"]
    preview = get(app, rate_path + "/impact-preview", maya)
    assert preview.status_code == 200, preview.text
    assert preview.json()["groups"][0]["currency"] == "USD"
    attached = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "subject_type": "estimate_version",
            "subject_id": rate_only.json()["id"],
            "file_object_id": file_id,
        },
    )
    assert attached.status_code == 201, attached.text
    submitted = post(
        app, rate_path + "/submit", maya, {}, if_match=get(app, rate_path, maya).headers["etag"]
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    assert get(app, rate_path, maya).json()["status"] == "APPROVED"
