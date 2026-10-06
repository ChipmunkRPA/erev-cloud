"""F-RPS-ACT2-PERSONA-R1 (record §36; D-98 candidate 107a; dev-guide DG-AK-41 rev 1.42): every
planned operation of the five platform keys is performed by a persona whose platform role actually
carries the operation's grant in the provisioned permission catalogue (``DEFAULT_ROLES``, PRD
§5.6) — checked on CPU through the ACT-2 step registry, with the approval subjects bound as the
runner binds them (RES-2). Author and approver are different personas per operation family; the
old composition (SSP work as the revenue accountant, SSP approval and journal runs as the
controller) is refused by name; no persona receives a grant the catalogue does not carry.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal
from erev_api.enums import PrincipalKind
from support.answer_keys import workspace_adapter
from support.answer_keys.ledger_resolver import SUBMIT_HANDLERS
from support.answer_keys.platform_plan import (
    APPROVER,
    ESTIMATE_MARKER,
    INTEGRATION,
    INTEGRATION_SCOPES,
    OPERATOR,
    PLATFORM_KEY_IDS,
    PREPARER,
    H,
    Step,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import ROLE_CODES
from support.answer_keys.step_permissions import check, required_permissions
from support.answer_keys.workspace_adapter import Call, LedgerEntry

SSP_ANALYST: Final = "ak-ssp-analyst"
SSP_APPROVER: Final = "ak-ssp-approver"
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/persona-r1/tenant")
# The CHECKPOINT runs the adapter starts are the job collaborator's, not the plan step's actor.
JOB_ACTOR: Final = MappingProxyType(
    {
        H["journal_create"]: PREPARER,
        H["journal_submit"]: PREPARER,
        H["report_create"]: APPROVER,
        H["report_run"]: APPROVER,
    }
)
SSP_AUTHORING: Final = frozenset(
    {
        H["ssp_book"],
        H["ssp_version"],
        H["ssp_entries"],
        H["ssp_study"],
        H["ssp_study_attach"],
        H["ssp_submit"],
    }
)
INVITED: Final = (PREPARER, APPROVER, SSP_ANALYST, SSP_APPROVER)


def _grants(actor: str) -> frozenset[str]:
    if actor == INTEGRATION:
        # BUILD_SPEC CTR-6: the world's API client holds scopes, not roles (PRD ACT-10).
        return frozenset(INTEGRATION_SCOPES)
    return frozenset[str]().union(*(DEFAULT_ROLES[code] for code in ROLE_CODES[actor]))


def _principal(actor: str, roles: tuple[str, ...]) -> Principal:
    permissions = frozenset[str]().union(*(DEFAULT_ROLES[code] for code in roles))
    return Principal(
        kind=PrincipalKind.USER,
        id=uuid5(TENANT, actor),
        tenant_id=TENANT,
        membership_id=uuid5(TENANT, f"{actor}-m"),
        display_name=actor,
        roles=tuple(sorted(roles)),
        permissions=permissions,
        permission_scopes={code: "*" for code in permissions},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def _operations(key_id: str):  # noqa: ANN202
    """(step, acting persona, required codes) for every persona-attributed operation of a plan,
    binding each decision to the latest committed submission as the runner does (RES-2)."""
    ledger: list[LedgerEntry] = []
    for step in plan(load_platform_key(key_id)).steps:
        if not step.handler.startswith("erev_api."):
            continue
        actor = JOB_ACTOR.get(step.handler, step.actor)
        call = Call(step.handler, actor, {}, step)
        if actor == "system":
            ledger.append(LedgerEntry(call, actor, None, None, None, None))
            continue
        yield step, actor, required_permissions(call, ledger)
        if step.handler in SUBMIT_HANDLERS:
            ledger.append(LedgerEntry(call, actor, None, None, None, None))


def test_every_planned_operation_is_performed_by_a_persona_holding_its_grant() -> None:
    """The five plans, end to end: each operation's persona holds one of the codes the API
    requires; a violation names the key, step and persona."""
    counted = 0
    for key_id in PLATFORM_KEY_IDS:
        for step, actor, required in _operations(key_id):
            counted += 1
            assert not required or required & _grants(actor), (
                key_id,
                step.phase,
                step.subject,
                actor,
                sorted(required),
                sorted(_grants(actor)),
            )
    assert counted >= 400  # the five plans' persona-attributed operations


def test_personas_map_to_the_roles_that_carry_their_grants() -> None:
    """D-98 candidate 107a: one platform role per persona, each a catalogue role; the SSP personas
    hold the only roles that carry ``ssp.create`` / ``ssp.approve``; the preparer holds the only
    role carrying ``journal.run``."""
    assert ROLE_CODES == {
        PREPARER: ("revenue_accountant",),
        APPROVER: ("controller",),
        SSP_ANALYST: ("ssp_analyst",),
        SSP_APPROVER: ("ssp_approver",),
        OPERATOR: ("tenant_admin",),
    }
    assert all(code in DEFAULT_ROLES for codes in ROLE_CODES.values() for code in codes)
    assert [r for r, p in DEFAULT_ROLES.items() if "ssp.create" in p] == ["ssp_analyst"]
    assert [r for r, p in DEFAULT_ROLES.items() if "ssp.approve" in p] == ["ssp_approver"]
    assert [r for r, p in DEFAULT_ROLES.items() if "journal.run" in p] == ["revenue_accountant"]
    assert "report.run" in DEFAULT_ROLES["controller"]
    assert workspace_adapter.JOURNAL_PERSONA == PREPARER
    assert workspace_adapter.REPORT_PERSONA == APPROVER


def test_author_and_approver_are_different_personas_per_operation_family() -> None:
    """The persona that creates or submits never approves: SSP authoring — the study of a version
    included (REQ-SSP-008) — is the analyst's and its approval a decision of the SSP approver,
    taken right after the submission it decides; configuration lifecycles are authored by the
    preparer and decided by the approver; the PERSONAS phase invites all four with exactly their
    catalogue roles, and everyone accepts the invitation they were sent before they act.

    The study's two commands also carry the evidence of an estimate version (04 §16.14 rev
    1.241): a step of them that is not of an SSP book is the preparer's and carries the plan's
    marker, which is what tells the two uses apart."""
    for key_id in PLATFORM_KEY_IDS:
        steps = plan(load_platform_key(key_id)).steps
        shared = [s for s in steps if s.handler in SSP_AUTHORING]
        ssp_authoring = [s for s in shared if s.subject.startswith("ssp_book ")]
        evidence = [s for s in shared if s not in ssp_authoring]
        assert {s.handler for s in evidence} <= {
            H["estimate_evidence"],
            H["estimate_evidence_attach"],
        }
        assert all(ESTIMATE_MARKER in s.detail and s.actor == PREPARER for s in evidence), key_id
        decisions = [s for s in steps if s.handler == H["decide"]]
        ssp_approvals = [s for s in decisions if s.subject.startswith("ssp_book ")]
        assert ssp_authoring and ssp_approvals, key_id
        assert {s.actor for s in ssp_authoring} == {SSP_ANALYST}, key_id
        assert {s.actor for s in ssp_approvals} == {SSP_APPROVER}, key_id
        for approval in ssp_approvals:
            before = steps[steps.index(approval) - 1]
            assert (before.handler, before.subject) == (H["ssp_submit"], approval.subject), key_id
        submits = [s for s in steps if s.handler in SUBMIT_HANDLERS - {H["ssp_submit"]}]
        assert {s.actor for s in submits} == {PREPARER}, key_id
        assert {s.actor for s in decisions if s not in ssp_approvals} == {APPROVER}, key_id
        # 04 T-PLT-07, DB-10: the operator accepts before the first invite, each persona right
        # after its own, and nobody accepts for another.
        personas = [s for s in steps if s.phase == "PERSONAS"]
        accepts = [(s.actor, s.subject) for s in personas if s.handler == H["accept"]]
        assert accepts == [(who, who) for who in (OPERATOR, *INVITED)], key_id
        assert (personas[0].handler, personas[0].actor) == (H["accept"], OPERATOR), key_id
        for index, step in enumerate(personas):
            if step.handler == H["invite"]:
                accepted = personas[index + 1]
                assert (accepted.handler, accepted.actor) == (H["accept"], step.subject), key_id
        invites = {s.subject: s.detail["roles"] for s in steps if s.handler == H["invite"]}
        assert invites == {
            PREPARER: "revenue_accountant",
            APPROVER: "controller",
            SSP_ANALYST: "ssp_analyst",
            SSP_APPROVER: "ssp_approver",
        }, key_id
        # The invite is the grant path (AUTO-BOOTSTRAP approves at submission); no second request.
        assert [s for s in steps if s.handler == H["assign_role"]] == [], key_id


def test_the_old_composition_is_refused_by_name() -> None:
    """The composition Codex measured (packet 1354): SSP authoring as the revenue accountant, SSP
    approval as the controller, journal runs as the controller — each refused by ACT-2 naming the
    missing grant, with the real plan steps and catalogue-derived principals."""
    steps = plan(load_platform_key(PLATFORM_KEY_IDS[1])).steps  # DLT: SSP book and journal runs
    book = next(s for s in steps if s.handler == H["ssp_book"])
    submit = next(s for s in steps if s.handler == H["ssp_submit"])
    approve = steps[steps.index(submit) + 1]  # the decision of that submission (RES-2)
    assert (approve.handler, approve.actor) == (H["decide"], SSP_APPROVER)
    submitted = [
        LedgerEntry(
            Call(submit.handler, SSP_ANALYST, {}, submit), SSP_ANALYST, None, None, None, None
        )
    ]
    journal = next(s for s in steps if s.handler == H["journal_create"])
    accountant = _principal("ak-preparer", ("revenue_accountant",))
    controller = _principal("ak-approver", ("controller",))
    with pytest.raises(NotProvisioned, match="lacks permission ssp.create for step 'ssp_book "):
        check(Call(book.handler, "ak-preparer", {}, book), accountant, [])
    with pytest.raises(NotProvisioned, match="lacks permission ssp.approve for step 'ssp_book "):
        check(Call(approve.handler, "ak-approver", {}, approve), controller, submitted)
    with pytest.raises(NotProvisioned, match="lacks permission journal.run for step "):
        step = Step("CHECKPOINT", "ak-approver", journal.handler, journal.subject)
        check(Call(journal.handler, "ak-approver", {}, step), controller, [])
    analyst = _principal(SSP_ANALYST, ("ssp_analyst",))
    ssp_approver = _principal(SSP_APPROVER, ("ssp_approver",))
    check(Call(book.handler, SSP_ANALYST, {}, book), analyst, [])
    check(Call(approve.handler, SSP_APPROVER, {}, approve), ssp_approver, submitted)
    check(Call(journal.handler, PREPARER, {}, journal), accountant, [])


def test_persona_bootstrap_requests_each_grant_once() -> None:
    """The PERSONAS phase grants every (persona, role) exactly once, through the invite: the
    operator holds `tenant_admin` and setup is incomplete, so rule AUTO-BOOTSTRAP approves each
    invited role at submission (04 §14.3 items 2–3; BR-PLT-02) and the `role_assignment` row is
    active. A second request for the same grant is refused by the kernel's validator as already
    held (`roles.assign_role`, 422 `validation-failed`) — the keys-platform stage on main c9110467
    failed all five keys there. Every plan step is a kernel call the database platform runs."""
    from collections import Counter

    from support.answer_keys.request_models import ROLE_CODES

    for key_id in PLATFORM_KEY_IDS:
        grants: Counter[tuple[str, str]] = Counter()
        for step in plan(load_platform_key(key_id)).steps:
            if step.phase != "PERSONAS":
                continue
            if step.handler == H["invite"]:
                for code in step.detail["roles"].split(","):
                    grants[(step.subject, code)] += 1
            elif step.handler == H["assign_role"]:
                for persona in step.subject.split(","):
                    for code in ROLE_CODES[persona]:
                        grants[(persona, code)] += 1
        assert grants, key_id
        assert {pair for pair, n in grants.items() if n != 1} == set(), (key_id, grants)
        assert {persona for persona, _ in grants} == {PREPARER, APPROVER, SSP_ANALYST, SSP_APPROVER}
