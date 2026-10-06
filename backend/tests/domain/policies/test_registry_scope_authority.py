"""Who authors and who decides a registry version (PRD BR-UX-06 rev 1.203; 04 §15.3 API-R-13 and
§16.10 rev 1.309; dev-guide DG-KRN-AUTH-04 and DG-KRN-APR-07 rev 1.289; the supervisor's ruling
of 2026-10-02 on lane F-SNP's measurement; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1) — and, for
the version of an entity, what a route answers since 04 API-C-03 rev 1.319 (PRD BR-UX-06 rev
1.207; item READ-SCOPE-BY-PERMISSION-1, register index 301).

A version at TENANT scope answers for every entity that states no value of its own, and one at
BOOK scope — which no entity owns either — for every entity that keeps the book, ahead of the
entity's own value (the book level is read before the entity level). Such a version is the
workspace's: authored by a member whose ``config.author`` covers all entities and decided by
one whose ``config.approve`` does, whatever its category. A version at ENTITY scope is its
entity's: the author's permission covers that entity — not another entity beside a role that
merely reads this one — and so does the decider's. Since rev 1.319 a command's transaction runs
under the scope of the permission that admitted it, so a command on the version of an entity
its caller's ``config.author`` does not name answers as for a version that does not exist; the
refusal by name is the answer for a version of the workspace.

The cast. Maya holds Revenue Accountant and Marcus Controller for all entities (the ``policies``
fixture). Ella holds Revenue Accountant and Carl Controller for AVM-DE alone. Vera holds Revenue
Accountant for AVM-DE and Viewer for AVM-US: she reads AVM-US and her ``config.author`` does not
name it. The frozen clock reads 2026-09-12T12:00Z.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.approvals import engine, subjects
from erev_api.db.tables import approval_request, audit_event, registry_version
from erev_api.enums import ApprovalSubjectType, AuditOutcome
from sqlalchemy import func, select
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled
from support.reference import assign, calendar, entity, fields, patch, slug
from support.subjects import install
from tests.domain.policies.test_registry_versions import (
    APPROVALS,
    POLICIES,
    World,
    created,
    pass_tests,
    shown,
    submitted,
    work,
)

if TYPE_CHECKING:
    from conftest import Policies

OCTOBER = "2026-10-01T00:00:00Z"
CLOSE_TENANT: Mapping[str, Any] = {
    "category": "CLOSE",
    "scope": "TENANT",
    "values": {"close.late_entry_window_days": 7},
}
ACCOUNTING_TENANT: Mapping[str, Any] = {
    "category": "ACCOUNTING_POLICY",
    "scope": "TENANT",
    "values": {"returns.reversal_rate": "CURRENT_REMAINING_RATE"},
    "effective_from": OCTOBER,
}
BOOK_VERSION: Mapping[str, Any] = {
    "category": "ACCOUNTING_POLICY",
    "scope": "BOOK",
    "book": "ASC606",
    "values": {"loss.scope": "ALL_CONTRACTS_WITH_EAC"},
    "effective_from": OCTOBER,
}
INTEGRATION_TENANT: Mapping[str, Any] = {
    "category": "INTEGRATION",
    "scope": "TENANT",
    "values": {"data.quarantine_failed_rows": True},
}
RULE = "T-PLT-10"
# What a caller the scope does not cover is told about a version of the workspace: 403 by name —
# the words the member reads, so they are spelled out here and not read from the product. The
# sentence of an entity's version reaches no member through a route since 04 API-C-03 rev 1.319
# (the third witness); its words are held where the command's own statement is, in
# tests/unit/policies/test_registry_authority.py.
WORKSPACE_SENTENCE = (
    "A tenant or book policy version applies to every entity. Your own access covers named "
    "entities only; a member whose access covers all entities must author it."
)
REFUSED_WORKSPACE = (403, "forbidden", WORKSPACE_SENTENCE, [(None, RULE)])
# ... and what its DENIED event states beside the action, the version and the actor.
WORKSPACE_DENIAL = {"permission": "config.author", "rule_id": RULE, "scope": "*"}


@pytest.fixture
def world(policies: Policies) -> World:
    calendar_id = calendar(policies.app, policies.maya, years=(2026, 2027))
    us = entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    de = entity(
        policies.app,
        policies.maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    return World(policies=policies, us_id=UUID(str(us["id"])), de_id=UUID(str(de["id"])))


def scoped(world: World, name: str, *grants: tuple[str, Sequence[UUID]]) -> Actor:
    """A member who holds each role of ``grants`` for the entities named beside it, signed in
    with a verified second factor."""
    someone = colleague(world.tenant_id, name)
    for role_code, entity_ids in grants:
        assign(someone, role_code, entity_ids=entity_ids)
    return enrolled(world.policies.app, world.policies.clock, someone)


def entity_version(code: str) -> dict[str, Any]:
    return {
        "category": "PRACTICAL_EXPEDIENT",
        "scope": "ENTITY",
        "entity_code": code,
        "values": {"sfc.one_year_expedient": "DO_NOT_APPLY"},
        "effective_from": OCTOBER,
    }


def answered(response: HttpResponse) -> tuple[int, str | None]:
    """The status of an answer and, when it is a problem, its slug."""
    return response.status_code, slug(response) if "type" in response.json() else None


def told(
    response: HttpResponse,
) -> tuple[int, str | None, Any, list[tuple[str | None, str | None]]]:
    """What a refusal tells its caller: status, slug, the sentence and the rule. An answer
    that is no problem — the command was admitted — is told by its status alone."""
    if "type" not in response.json():
        return response.status_code, None, None, []
    return response.status_code, slug(response), response.json()["detail"], fields(response)


def denials(world: World) -> list[tuple[str, str | None, UUID | None, dict[str, Any]]]:
    """(action, version id, actor, detail) of the ``DENIED`` audit events of registry versions,
    in chain order."""
    rows = world.policies.rows(
        select(
            audit_event.c.action,
            audit_event.c.object_id,
            audit_event.c.actor_id,
            audit_event.c.detail,
        )
        .where(
            audit_event.c.object_type == "registry_version",
            audit_event.c.outcome == AuditOutcome.DENIED,
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [
        (
            str(row["action"]),
            None if row["object_id"] is None else str(row["object_id"]),
            row["actor_id"],
            dict(row["detail"]),
        )
        for row in rows
    ]


def versions(world: World) -> int:
    """How many registry versions the workspace holds."""
    counted = select(func.count().label("n")).select_from(registry_version)
    return int(world.policies.rows(counted)[0]["n"])


def frozen(world: World, request_id: str) -> dict[str, Any]:
    """The entities a request froze at its submission (T-PLT-17)."""
    [row] = world.policies.rows(
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
            approval_request.c.status,
        ).where(approval_request.c.id == UUID(request_id))
    )
    return {**row, "entity_ids": list(row["entity_ids"] or [])}


def approve_as(world: World, request_id: str, approver: Actor, reader: Actor) -> HttpResponse:
    """``approver`` sends the approval with the hashes ``reader`` is shown — so that an approver
    who cannot read the request is answered for the request and not for a missing hash."""
    policies = world.policies
    detail = policies.get(f"{APPROVALS}/{request_id}", reader)
    assert detail.status_code == 200, detail.text
    preview = detail.json()["impact_preview"]
    return policies.post(
        f"{APPROVALS}/{request_id}/approve",
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": None if preview is None else preview["sha256"],
            "comment": "Reviewed the values",
        },
        actor=approver,
    )


def test_policy_tenant_scope_1_a_workspace_version_is_authored_for_all_entities(
    world: World,
) -> None:
    """Ella's ``config.author`` names AVM-DE alone. A TENANT version — of a settings category and
    of an accounting one — a BOOK version and the legacy-parity preset of the workspace are not
    hers to create: 403 by name, nothing is stored, and each attempt is one ``DENIED`` event of
    the creation that states the scope asked and no entity. On Maya's draft of a TENANT version
    every other lifecycle command answers her the same — change, test, submit, withdraw, publish
    — after the version is found and before its state is told: a stale ``If-Match``, a version
    that is not submitted and one that is not approved are all answered 403, never 412 or 409;
    the version is untouched; each attempt is recorded under the version. An id that names no
    version answers the 404 it answered and records nothing.

    Fail-first: Ella created, changed, tested and submitted a TENANT version of a settings
    category and of an accounting policy, and a BOOK version; lane F-SNP measured the five
    settings categories."""
    policies = world.policies
    ella = scoped(world, "ella", ("revenue_accountant", [world.de_id]))
    her = ella.member.user_id
    before = versions(world)

    for body in (CLOSE_TENANT, ACCOUNTING_TENANT, BOOK_VERSION):
        assert told(policies.post(POLICIES, body, actor=ella)) == REFUSED_WORKSPACE, body
    preset = policies.post(f"{POLICIES}/presets/legacy-parity", {"scope": "TENANT"}, actor=ella)
    assert told(preset) == REFUSED_WORKSPACE
    assert versions(world) == before
    assert denials(world) == [("registry_version.create", None, her, WORKSPACE_DENIAL)] * 4

    draft = created(world, **INTEGRATION_TENANT)  # Maya's
    version_id = str(draft["id"])
    path = f"{POLICIES}/{version_id}"
    attempts: tuple[tuple[str, Callable[[], HttpResponse]], ...] = (
        (
            "registry_version.update",
            lambda: patch(
                policies.app,
                path,
                ella,
                {"values": {"data.quarantine_failed_rows": False}},
                if_match='"r999"',
            ),
        ),
        ("registry_version.test_requested", lambda: policies.post(f"{path}/test", {}, actor=ella)),
        (
            "registry_version.submitted",
            lambda: policies.post(f"{path}/submit", {"comment": "Ready"}, actor=ella),
        ),
        (
            "registry_version.withdrawn",
            lambda: policies.post(f"{path}/withdraw", {"comment": "Mine"}, actor=ella),
        ),
        ("registry_version.published", lambda: policies.post(f"{path}/publish", {}, actor=ella)),
    )
    for action, attempt in attempts:
        assert told(attempt()) == REFUSED_WORKSPACE, action
    assert denials(world)[4:] == [
        (action, version_id, her, WORKSPACE_DENIAL) for action, _ in attempts
    ]
    current = shown(world, version_id)
    assert (current["status"], current["row_version"], current["values"]) == (
        draft["status"],
        draft["row_version"],
        draft["values"],
    )

    nobody = f"{POLICIES}/{UUID(int=0)}"
    unknown = policies.post(f"{nobody}/submit", {"comment": "Ready"}, actor=ella)
    assert answered(unknown) == (404, "not-found"), unknown.text
    assert len(denials(world)) == 9

    # Positive control: Maya, whose permission covers all entities, takes her draft on.
    changed = patch(
        policies.app,
        path,
        policies.maya,
        {"values": {"data.quarantine_failed_rows": False}},
        if_match=f'"r{draft["row_version"]}"',
    )
    assert changed.status_code == 200, changed.text
    pass_tests(world, version_id)
    assert submitted(world, version_id)["status"] == "SUBMITTED"
    assert len(denials(world)) == 9


def test_policy_tenant_scope_1_the_request_of_a_workspace_version_spans_every_entity(
    world: World,
) -> None:
    """Carl's ``config.approve`` names AVM-DE alone. The request of a TENANT version and of a BOOK
    version names every entity, so it is not his: not listed for him, 404 on its read and on his
    approval, exactly as an id that names none — and the version stays SUBMITTED. Marcus, the
    Controller of all entities, reads it as a request of every entity that names none, approves
    it, and the version is PUBLISHED.

    Fail-first: the request named no entity at all — a tenant-level subject — and Carl read and
    approved it; the version was PUBLISHED for the workspace."""
    policies = world.policies
    carl = scoped(world, "carl", ("controller", [world.de_id]))
    for body in (CLOSE_TENANT, BOOK_VERSION):
        version = created(world, **body)
        pass_tests(world, version["id"])
        request_id = str(submitted(world, version["id"])["approval_request_id"])
        assert frozen(world, request_id) == {
            "entity_id": None,
            "entity_ids": [],
            "is_all_entities": True,
            "status": "PENDING",
        }, body

        seen = policies.get(f"{APPROVALS}/{request_id}", carl)
        assert answered(seen) == (404, "not-found"), body
        listed = policies.get(APPROVALS, carl)
        assert listed.status_code == 200, listed.text
        assert request_id not in [item["id"] for item in listed.json()["items"]], body
        decided = approve_as(world, request_id, carl, policies.marcus)
        assert answered(decided) == (404, "not-found"), body
        assert shown(world, version["id"])["status"] == "SUBMITTED"
        assert frozen(world, request_id)["status"] == "PENDING"

        detail = policies.get(f"{APPROVALS}/{request_id}", policies.marcus).json()
        assert (detail["all_entities"], detail["entity"], detail["entities"]) == (True, None, [])
        approved = policies.approve(request_id)
        assert approved.status_code == 200, approved.text
        assert shown(world, version["id"])["status"] == "PUBLISHED", body


def test_policy_tenant_scope_1_an_entity_version_is_authored_for_its_entity(world: World) -> None:
    """An ENTITY version is its entity's. Vera's ``config.author`` names AVM-DE; a second role
    lets her read AVM-US. A command runs under the scope of the permission that admitted it (04
    API-C-03 rev 1.319), so hers does not read AVM-US at all, and she is answered for AVM-US's
    version as Ella is, whose roles name AVM-DE alone: at the creation the code names no entity
    — the 422 it answered her, the same findings, nothing stored; on Maya's draft for AVM-US,
    which Vera reads and Ella does not, her change, her test request and her submission answer
    404, exactly as an id that names no version does. Nothing is recorded — a 404 and a 422
    confirm nothing, in the trail either — and the draft is untouched.

    Positive control: AVM-DE's version is Vera's to create, change, test and submit; its request
    names AVM-DE, Carl — Controller of AVM-DE alone — approves it, and it is PUBLISHED.

    A STALE EXPECTATION turned at the join of register index 301 (the supervisor's ruling of
    2026-10-03): until rev 1.319 the command read AVM-US through her second role and refused her
    403 by name, four ``DENIED`` events in all. That refusal stays the command's own statement
    (``registry_versions.require_authority``); no route reaches it for an entity's version, and
    ``tests/unit/policies/test_registry_authority.py`` holds it as a pure function.

    Fail-first (index 291): Vera created, changed, tested and submitted AVM-US's version — the
    permission was asked for any entity and the entity was read by her session."""
    policies = world.policies
    de, us = world.de_id, world.us_id
    vera = scoped(world, "vera", ("revenue_accountant", [de]), ("viewer", [us]))
    ella = scoped(world, "ella", ("revenue_accountant", [de]))
    carl = scoped(world, "carl", ("controller", [de]))
    before = versions(world)

    unnamed = policies.post(POLICIES, entity_version("AVM-US"), actor=vera)
    unread = policies.post(POLICIES, entity_version("AVM-US"), actor=ella)
    assert told(unread)[:2] == (422, "validation-failed"), unread.text
    assert fields(unread) == [("entity_code", "T-REF-01")]
    assert told(unnamed) == told(unread), unnamed.text
    assert versions(world) == before
    assert denials(world) == []

    draft = created(world, **entity_version("AVM-US"))  # Maya's
    version_id = str(draft["id"])
    path = f"{POLICIES}/{version_id}"
    nobody = f"{POLICIES}/{UUID(int=0)}"
    # What is left of the difference between the two members: the read. The draft is Vera's to
    # read — her ``config.read`` names AVM-US — and it is not Ella's.
    assert policies.get(path, vera).status_code == 200
    assert answered(policies.get(path, ella)) == (404, "not-found")
    attempts: tuple[tuple[str, Callable[[Actor, str], HttpResponse]], ...] = (
        (
            "registry_version.update",
            lambda actor, target: patch(
                policies.app,
                target,
                actor,
                {"values": {"sfc.one_year_expedient": "APPLY"}},
                if_match=f'"r{draft["row_version"]}"',
            ),
        ),
        (
            "registry_version.test_requested",
            lambda actor, target: policies.post(f"{target}/test", {}, actor=actor),
        ),
        (
            "registry_version.submitted",
            lambda actor, target: policies.post(
                f"{target}/submit", {"comment": "Ready"}, actor=actor
            ),
        ),
    )
    for action, attempt in attempts:
        hers = told(attempt(vera, path))
        assert hers[:2] == (404, "not-found"), action
        assert hers == told(attempt(ella, path)) == told(attempt(vera, nobody)), action
    assert denials(world) == []
    assert shown(world, version_id)["row_version"] == draft["row_version"]

    made = policies.post(POLICIES, entity_version("AVM-DE"), actor=vera)
    assert made.status_code == 201, made.text
    own = f"{POLICIES}/{made.json()['id']}"
    changed = patch(
        policies.app,
        own,
        vera,
        {"values": {"sfc.one_year_expedient": "DO_NOT_APPLY"}},
        if_match=f'"r{made.json()["row_version"]}"',
    )
    assert changed.status_code == 200, changed.text
    asked = policies.post(f"{own}/test", {}, actor=vera)
    assert asked.status_code == 202, asked.text
    assert work(world, str(asked.json()["id"]))["state"] == "SUCCEEDED"
    sent = policies.post(f"{own}/submit", {"comment": "Ready"}, actor=vera)
    assert sent.status_code == 200, sent.text
    request_id = str(sent.json()["approval_request_id"])
    assert frozen(world, request_id) == {
        "entity_id": de,
        "entity_ids": [],
        "is_all_entities": False,
        "status": "PENDING",
    }
    approved = policies.approve(request_id, approver=carl)
    assert approved.status_code == 200, approved.text
    assert shown(world, str(made.json()["id"]))["status"] == "PUBLISHED"
    assert denials(world) == []


def test_policy_tenant_scope_1_a_request_that_froze_no_entity_is_voided_at_its_decision(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request of a TENANT version submitted before rev 1.309 froze no entity. Nothing rewrites
    it (D-99); the kernel reads what the subject states again at the decision (R-41 (2)), finds
    every entity where the request froze none, and voids the request as stale — 409, nothing
    decided — whoever tries, also the Controller of one entity whom the stored row still lets
    read it. The version leaves SUBMITTED; a member whose ``config.author`` covers all entities
    changes it, which reopens it, and tests and submits it again under the rule.

    Fail-first: the approval of the Controller of AVM-DE alone published the version."""
    carl = scoped(world, "carl", ("controller", [world.de_id]))
    spec = engine.spec_for(ApprovalSubjectType.REGISTRY_VERSION)
    with monkeypatch.context() as as_before:
        # the subject as it stated itself until rev 1.309: a tenant-level one
        install(as_before, replace(spec, entity_id=subjects._tenant_level, entities=None))
        version = created(world, **CLOSE_TENANT)
        pass_tests(world, version["id"])
        request_id = str(submitted(world, version["id"])["approval_request_id"])
    assert frozen(world, request_id) == {
        "entity_id": None,
        "entity_ids": [],
        "is_all_entities": False,
        "status": "PENDING",
    }

    decided = approve_as(world, request_id, carl, carl)
    assert answered(decided) == (409, "stale-approval"), decided.text
    assert frozen(world, request_id)["status"] == "VOIDED"
    assert shown(world, version["id"])["status"] == "WITHDRAWN"
