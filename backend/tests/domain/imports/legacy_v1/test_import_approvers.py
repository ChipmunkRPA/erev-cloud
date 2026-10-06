"""Who approves an import whose commit performs an approval by itself (supervisor rulings R-92 and
R-98 on R-38 (ii); 04 §16.6, §16.10 rev 1.104; 05 IPL-09; PRD §2.5 routing row ``IMPORT_COMMIT``;
dev-guide DG-KRN-APR-02, DG-KRN-APR-07; 03 REQ-PLT-011 to REQ-PLT-013, REQ-PLT-019; controls
CTL-005, CTL-010).

The ``IMPORT_COMMIT`` request keeps its own step, and its approver also answers for the first
approver of every approval the commit performs: a person who holds ``import.approve`` and not the
underlying permission takes no step — neither approval nor rejection — is not waited for and is
not notified, and the refusal is on the audit record. What one step cannot hold becomes a further
step: the underlying subject's second step, and a step a routing rule of the workspace adds to
that subject. ONE further person answers for the second approver of every approval that takes
one. A delegation conveys ``import.approve``, never the underlying permission.

World ``support.legacy_replay.legacy_world``: Maya uploads; Priya is a Revenue Reviewer and an SSP
Approver; Marcus a Controller, an SSP Approver and a Tenant Admin. Jobs run as the worker runs
them. The refusals at the backstop and the two-step cases of the documented thresholds are in
``test_approval_floor.py``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_delegation,
    approval_request,
    approval_step,
    audit_event,
    contract,
    job,
    judgement_record,
    notification,
    role,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.contracts import computation
from erev_api.domain.imports import scope
from erev_api.enums import ApprovalSubjectType, RuleSetKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support import golden_streams
from support.db import TestDatabase
from support.factories import run_import_job, workbook_bytes
from support.legacy_replay import (
    SETUP_2023,
    SKU_SSP,
    LegacyWorld,
    committed,
    diffed,
    job_of,
    legacy_world,
    replayed,
    shown,
    submit,
    workbook_rows,
)
from support.principals import Actor, colleague, enrolled
from support.reference import APPROVALS, approve, assign, get, reject, slug
from support.rows import (
    approval_delegation_values,
    insert_approval_request,
    insert_approval_step,
    publish_rule_set,
)

SSP_NAME = "SKU SSP Template.xlsx"
SSP_ACT = "approves its SSP book version"
JUDGEMENT_ACT = "reviews the judgement records of its contracts"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


def person(world: LegacyWorld, clock: FrozenClock, name: str, *roles: str) -> Actor:
    """Another member of the workspace with ``roles`` for every entity, MFA enrolled."""
    someone = colleague(world.tenant_id, name)
    for code in roles:
        assign(someone, code)
    return enrolled(world.app, clock, someone)


def delegated(
    world: LegacyWorld, clock: FrozenClock, delegator: Actor, delegate: Actor, *permissions: str
) -> None:
    """A delegation of ``permissions`` in force now (T-PLT-21)."""
    values = approval_delegation_values(
        world.tenant_id,
        delegator_membership_id=delegator.member.membership_id,
        delegate_membership_id=delegate.member.membership_id,
        valid_from=clock.now() - timedelta(days=1),
        valid_to=clock.now() + timedelta(days=29),
    )
    values["permissions"] = list(permissions)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(insert(approval_delegation).values(**values))


def routing_rule(
    world: LegacyWorld,
    rule_key: str,
    subject: str,
    steps: list[Any],
    *,
    amount: tuple[str, str] | None = None,
) -> None:
    """A PUBLISHED ``APPROVAL_ROUTING`` rule of the workspace for ``subject`` — with a condition
    on the request's functional amount (operator, value) when ``amount`` is given."""
    conditions: list[dict[str, Any]] = [{"field": "subject.type", "op": "eq", "value": subject}]
    if amount is not None:
        conditions.append({"field": "amount.functional", "op": amount[0], "value": amount[1]})
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_rule_set(
            session,
            tenant_id=world.tenant_id,
            kind=RuleSetKind.APPROVAL_ROUTING,
            code=f"WS-{rule_key}",
            rules=[
                {
                    "rule_key": rule_key,
                    "conditions": conditions,
                    "outputs": {"steps": steps},
                }
            ],
        )


def ssp_file(price: int, label: str = "2024-01-01") -> bytes:
    """The first two WLD-F-01 rows under another version label, Hardware 1 listed at ``price``
    (100 in the 2023 version, so its mid value moves by ``price`` − 100 per cent)."""
    headers, rows = workbook_rows(SKU_SSP)
    version, listed = headers.index("SSP Version"), headers.index("SKU Unit List Price")
    later = [[*row[:version], label, *row[version + 1 :]] for row in rows[:2]]
    later[0][listed] = price
    return workbook_bytes("SKU Setup", headers, later)


def setup_file(price: int) -> bytes:
    """WLD-F-02 with the first obligation of Contract 1 priced at ``price`` (500 in the file)."""
    headers, rows = workbook_rows(SETUP_2023)
    amount = headers.index("Original POB Total Selling Price")
    changed = [list(row) for row in rows]
    changed[0][amount] = price
    return workbook_bytes("Contract Setup", headers, changed)


def submitted(world: LegacyWorld, import_id: str) -> str:
    response = submit(world.imports, import_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUBMITTED", response.text
    return str(response.json()["approval_request_id"])


def steps(world: LegacyWorld, request_id: str) -> list[tuple[int, str, str | None]]:
    """The steps of a request: number, permission and the code of the role it names."""
    found = world.imports.rows(
        select(approval_step.c.step_no, approval_step.c.required_permission, role.c.code)
        .select_from(approval_step.outerjoin(role, role.c.id == approval_step.c.required_role_id))
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return [
        (
            int(row["step_no"]),
            str(row["required_permission"]),
            None if row["code"] is None else str(row["code"]),
        )
        for row in found
    ]


def can_decide(world: LegacyWorld, request_id: str, someone: Actor) -> bool:
    shown_to = get(world.app, f"{APPROVALS}/{request_id}", someone)
    assert shown_to.status_code == 200, shown_to.text
    return bool(shown_to.json()["can_decide"])


def waiting_for(world: LegacyWorld, someone: Actor) -> set[str]:
    """``GET /approvals?assigned_to_me=true``: the requests waiting for ``someone``."""
    listed = get(world.app, APPROVALS, someone, {"assigned_to_me": "true"})
    assert listed.status_code == 200, listed.text
    return {str(item["id"]) for item in listed.json()["items"]}


def decisions(world: LegacyWorld, request_id: str) -> list[tuple[str, UUID, UUID | None]]:
    found = world.imports.rows(
        select(
            approval_decision.c.decision,
            approval_decision.c.approver_id,
            approval_decision.c.on_behalf_of_id,
        )
        .where(approval_decision.c.approval_request_id == UUID(request_id))
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    )
    return [(str(row["decision"]), row["approver_id"], row["on_behalf_of_id"]) for row in found]


def status(world: LegacyWorld, request_id: str) -> tuple[str, int]:
    (request,) = world.imports.rows(
        select(approval_request.c.status, approval_request.c.current_step_no).where(
            approval_request.c.id == UUID(request_id)
        )
    )
    return str(request["status"]), int(request["current_step_no"])


def denied(world: LegacyWorld, request_id: str) -> list[tuple[str, UUID, dict[str, Any]]]:
    """The ``DENIED`` audit events of a request: action, actor and detail, in chain order."""
    found = world.imports.rows(
        select(audit_event.c.action, audit_event.c.actor_id, audit_event.c.detail)
        .where(
            audit_event.c.object_type == "approval_request",
            audit_event.c.object_id == UUID(request_id),
            audit_event.c.outcome == "DENIED",
        )
        .order_by(audit_event.c.chain_seq)
    )
    return [(str(row["action"]), row["actor_id"], dict(row["detail"])) for row in found]


def notified(world: LegacyWorld, request_id: str) -> set[UUID]:
    """The memberships told that the request needs their approval (NTF-01)."""
    found = world.imports.rows(
        select(notification.c.recipient_membership_id).where(
            notification.c.kind == "APPROVAL_ASSIGNED",
            notification.c.subject_id == UUID(request_id),
        )
    )
    return {row["recipient_membership_id"] for row in found}


def commit_jobs(world: LegacyWorld, import_id: str) -> list[Any]:
    return world.imports.rows(
        select(job.c.id).where(job.c.subject_id == UUID(import_id), job.c.kind == "IMPORT_COMMIT")
    )


def versions(world: LegacyWorld) -> list[tuple[str, str]]:
    found = world.imports.rows(
        select(ssp_book_version.c.legacy_version_label, ssp_book_version.c.status)
        .join(ssp_book, ssp_book.c.id == ssp_book_version.c.ssp_book_id)
        .where(ssp_book.c.code == "LEGACY-SKU-SSP")
        .order_by(ssp_book_version.c.version_no)
    )
    return [(str(row["legacy_version_label"]), str(row["status"])) for row in found]


@pytest.mark.control("CTL-010")
def test_r92_an_approver_without_the_underlying_permission_takes_no_step_and_is_not_waited_for(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """R-92: the requirement is checked at EACH decision and ``can_decide`` asks the same. Rex is a
    Revenue Reviewer — ``import.approve`` without ``ssp.approve`` — and the commit of a SKU SSP
    upload approves the book version: the request does not wait for him, he is not notified, and
    neither his approval nor his rejection is taken; both refusals name the permission and are
    recorded as ``DENIED`` (R-98). Priya holds both permissions: the request waits for her, and
    she approves it alone.

    Fail-first: without the per-decision check Rex is listed and notified, and his rejection ends
    the request (the backstop stands at the approving decision only)."""
    rex = person(legacy, clock, "rex", "revenue_reviewer")
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [(1, "import.approve", None)]

    assert can_decide(legacy, request_id, rex) is False
    assert request_id not in waiting_for(legacy, rex)
    assert can_decide(legacy, request_id, legacy.priya) is True
    assert request_id in waiting_for(legacy, legacy.priya)
    assert notified(legacy, request_id) == {legacy.priya.member.membership_id}

    wanted = scope.FLOOR_PERMISSION.format(act=SSP_ACT, permission="ssp.approve")
    refused = approve(legacy.app, request_id, rex)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == wanted
    rejected = reject(legacy.app, request_id, rex, "Not the rates we agreed.")
    assert (rejected.status_code, slug(rejected)) == (403, "forbidden"), rejected.text
    assert rejected.json()["detail"] == wanted
    assert status(legacy, request_id) == ("PENDING", 1)
    assert decisions(legacy, request_id) == []
    assert shown(legacy.imports, import_id)["status"] == "SUBMITTED"
    fact = {
        "permission": "ssp.approve",
        "rule_id": "IPL-09",
        "subject_type": "IMPORT_COMMIT",
        "subject_id": import_id,
        "underlying_subject_type": "SSP_BOOK_VERSION",
        "approval": 1,
        "role": None,
    }
    assert denied(legacy, request_id) == [
        ("approval_request.approve", rex.member.user_id, fact),
        ("approval_request.reject", rex.member.user_id, fact),
    ]

    # Positive control: one person with both permissions approves the unflagged import alone.
    decided = approve(legacy.app, request_id, legacy.priya)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    assert denied(legacy, request_id)[2:] == []
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert versions(legacy) == [("2023-01-01", "APPROVED")]


@pytest.mark.control("CTL-010")
def test_r92_a_delegation_conveys_the_imports_permission_and_not_the_underlying_one(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """R-92 "personally", through a delegate: Priya delegates her approval permissions. Dana holds
    nothing of her own — the delegation gives her ``import.approve``, and naming ``ssp.approve``
    in it as well changes nothing: the person who decides holds the underlying permission in
    their own right. She cannot decide, is not waited for, and her approval is refused by name.
    Sam is an SSP Approver in his own right and has ``import.approve`` from the same delegator:
    the request waits for him and he approves it alone, on Priya's behalf.

    Fail-first: a check that read the delegator's grants, or none, would take Dana's approval."""
    dana = person(legacy, clock, "dana")
    sam = person(legacy, clock, "sam", "ssp_approver")
    delegated(legacy, clock, legacy.priya, dana, "import.approve", "ssp.approve")
    delegated(legacy, clock, legacy.priya, sam, "import.approve")
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    request_id = submitted(legacy, import_id)

    assert can_decide(legacy, request_id, dana) is False
    assert request_id not in waiting_for(legacy, dana)
    refused = approve(legacy.app, request_id, dana)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_PERMISSION.format(
        act=SSP_ACT, permission="ssp.approve"
    )
    assert decisions(legacy, request_id) == []
    assert notified(legacy, request_id) == {
        legacy.priya.member.membership_id,
        sam.member.membership_id,
    }

    assert can_decide(legacy, request_id, sam) is True
    assert request_id in waiting_for(legacy, sam)
    decided = approve(legacy.app, request_id, sam)
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"
    assert decisions(legacy, request_id) == [
        ("APPROVE", sam.member.user_id, legacy.priya.member.user_id)
    ]
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert versions(legacy) == [("2023-01-01", "APPROVED")]


@pytest.mark.control("CTL-010")
def test_r98_a_routing_rule_of_the_workspace_on_the_underlying_subject_reaches_the_import(
    legacy: LegacyWorld,
) -> None:
    """R-98: the underlying subject is routed as a request of its own would be, rules included.
    The workspace publishes a rule that gives every SSP book version a second step — a
    Controller's sign-off under ``config.approve``. An unflagged SKU SSP import, which one SSP
    Approver approved alone before, now carries that step: Priya's approval leaves it PENDING with
    nothing approved, and the Controller decides it.

    Fail-first: a floor read from the subject's specification alone gives the request one step
    and Priya's approval commits the version."""
    routing_rule(
        legacy,
        "ROUTE-SSP-SIGN-OFF",
        "SSP_BOOK_VERSION",
        [
            {"name": "SSP review", "permission": "ssp.approve", "min_approvers": 1},
            {
                "name": "Finance sign-off",
                "permission": "config.approve",
                "min_approvers": 1,
                "role": "controller",
            },
        ],
    )
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None),
        (2, "config.approve", "controller"),
    ]

    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    assert status(legacy, request_id) == ("PENDING", 2)
    assert commit_jobs(legacy, import_id) == []
    assert versions(legacy) == []

    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert versions(legacy) == [("2023-01-01", "APPROVED")]


SIGN_OFF_STEPS: list[Any] = [
    {"name": "Contract review", "permission": "contract.approve", "min_approvers": 1},
    {
        "name": "Finance sign-off",
        "permission": "contract.approve",
        "min_approvers": 1,
        "role": "controller",
    },
]


@pytest.mark.control("CTL-005")
@pytest.mark.parametrize(
    ("at_least", "routed"),
    [
        # The activations of WLD-F-02 state 1,300.00 and 1,000.00: Contract 1's own request takes
        # the rule and Contract 2's does not. (Item ACT-FLAGS-1 with ruling R-66 (4) moved the
        # WORLD: Contract 2, booked 900.00, states the 1,000.00 of its stored version's price,
        # so the rule stands at 1,200.00 where it stood at 1,000.00 — between the two again.)
        ("1200.00", [(1, "import.approve", None), (2, "contract.approve", "controller")]),
        # Positive control: neither request reaches the amount, and one person approves.
        ("2000.00", [(1, "import.approve", None)]),
    ],
)
def test_r109_a_routing_rule_on_the_underlying_amount_reaches_the_import(
    legacy: LegacyWorld, at_least: str, routed: list[tuple[int, str, str | None]]
) -> None:
    """Item IMP-FLOOR-AMOUNT-1, the reader (supervisor ruling R-109 (d)): each approval the commit
    performs is routed with the functional amount its own request would carry. The workspace gives
    every contract activation from a functional amount a Controller's sign-off. A Contract Setup
    upload whose activations state 1,000.00 and 1,300.00 takes that step when the amount is
    1,200.00 — one of its activations would — and Priya's approval leaves it PENDING with nothing
    booked; Marcus, a Controller, decides it. At 2,000.00 the same upload keeps its one step.

    Fail-first: a reader that routes without the amount gives the request one step in both
    cases, and Priya's approval alone commits contracts a rule of the workspace sends to a
    Controller."""
    routing_rule(
        legacy, "ROUTE-ACT-AMOUNT", "CONTRACT_ACTIVATION", SIGN_OFF_STEPS, amount=("gte", at_least)
    )
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(
        legacy.imports, "Contract Setup.xlsx", SETUP_2023.read_bytes(), "legacy_contract_setup"
    )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == routed

    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    if len(routed) == 1:
        assert first.json()["status"] == "APPROVED"
        return
    assert first.json()["status"] == "PENDING"
    assert status(legacy, request_id) == ("PENDING", 2)
    assert commit_jobs(legacy, import_id) == []
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"


@pytest.mark.control("CTL-005")
def test_r92_one_second_person_answers_for_every_underlying_second_approver(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """R-92, never more people than the direct path: a Contract Setup upload at the Controller
    threshold takes the activation's second step (``contract.approve``, a Controller), and a rule
    of the workspace gives every judgement record a second reviewer under ``ssp.approve``. The
    request gains ONE further step — the activation's, the first approval in template order that
    takes a second approver — and its approver answers for both: Cora, a Controller without
    ``ssp.approve``, meets the step and is refused by name for the judgement records' second
    approver, recorded as ``DENIED``; Marcus, a Controller and an SSP Approver, decides.

    Fail-first: without the per-decision check Cora's approval approves the import — the step's
    permission and role are hers."""
    cora = person(legacy, clock, "cora", "controller")
    routing_rule(
        legacy,
        "ROUTE-JDG-SECOND",
        "JUDGEMENT_RECORD",
        [
            {"name": "Judgement review", "permission": "judgement.review", "min_approvers": 1},
            {"name": "SSP sign-off", "permission": "ssp.approve", "min_approvers": 1},
        ],
    )
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(
        legacy.imports, "Contract Setup large.xlsx", setup_file(1_000_000), "legacy_contract_setup"
    )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None),
        (2, "contract.approve", "controller"),
    ]

    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    assert status(legacy, request_id) == ("PENDING", 2)

    assert can_decide(legacy, request_id, cora) is False
    assert request_id not in waiting_for(legacy, cora)
    refused = approve(legacy.app, request_id, cora)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_LATER_PERMISSION.format(
        act=JUDGEMENT_ACT, nth="second", permission="ssp.approve"
    )
    assert status(legacy, request_id) == ("PENDING", 2)
    assert [item[0] for item in decisions(legacy, request_id)] == ["APPROVE"]
    assert denied(legacy, request_id) == [
        (
            "approval_request.approve",
            cora.member.user_id,
            {
                "permission": "ssp.approve",
                "rule_id": "IPL-09",
                "subject_type": "IMPORT_COMMIT",
                "subject_id": import_id,
                "underlying_subject_type": "JUDGEMENT_RECORD",
                "approval": 2,
                "role": None,
            },
        )
    ]
    assert commit_jobs(legacy, import_id) == []
    assert legacy.imports.rows(select(contract.c.id)) == []

    assert can_decide(legacy, request_id, legacy.marcus) is True
    assert request_id in waiting_for(legacy, legacy.marcus)
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"


ACTIVATION_ACT = "activates its contracts"


@pytest.mark.control("CTL-005")
def test_r109_every_instance_is_asked_for_and_none_is_reduced_to_the_longest(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """The reader of item IMP-FLOOR-AMOUNT-1, reading 1 (ruling R-109 (d) as answered on
    2026-10-01): every approval the commit performs is routed by itself, and two lists of one
    length are both asked for. Two rules of the workspace route a contract activation by its
    amount — from 500.00 a Tenant Admin's second approval, from 1,000.00 a Controller's — and
    the setup file, with the first obligation of Contract 1 priced at 100.00, states one
    activation of 900.00 and one of 1,000.00, so each activation's own request takes two
    approvers, with a different role. (Item ACT-FLAGS-1 with ruling R-66 (4) moved the WORLD,
    not an expectation: an activation states the larger of the booked consideration and the
    price of the contract's stored version, so Contract 2 of WLD-F-02 — booked 900.00, priced
    1,000.00 — reaches the Controller's rule, and the file as delivered, 1,300.00 and 1,000.00,
    would give both contracts the same role.) The import takes ONE further step, and its
    approver answers for both second approvers: Tara, a Tenant Admin who approves contracts, is
    refused by name for the Controller the larger contract asks; Marcus, Controller and Tenant
    Admin, decides.

    Fail-first: a reader that keeps the longest list — the first of two equal ones — drops the
    other contract's role, and Tara's approval approves the import."""
    tara = person(legacy, clock, "tara", "tenant_admin", "revenue_reviewer")
    for rule_key, at_least, role_code in (
        ("ROUTE-ACT-1-CONTROLLER", "1000.00", "controller"),
        ("ROUTE-ACT-2-ADMIN", "500.00", "tenant_admin"),
    ):
        routing_rule(
            legacy,
            rule_key,
            "CONTRACT_ACTIVATION",
            [
                {"name": "Contract review", "permission": "contract.approve", "min_approvers": 1},
                {
                    "name": "Sign-off",
                    "permission": "contract.approve",
                    "min_approvers": 1,
                    "role": role_code,
                },
            ],
            amount=("gte", at_least),
        )
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(
        legacy.imports, "Contract Setup.xlsx", setup_file(100), "legacy_contract_setup"
    )
    request_id = submitted(legacy, import_id)
    # the further step carries the role of the first list that takes a second approver: the
    # 900.00 contract's, which only the rule from 500.00 reaches
    assert steps(legacy, request_id) == [
        (1, "import.approve", None),
        (2, "contract.approve", "tenant_admin"),
    ]
    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"

    assert can_decide(legacy, request_id, tara) is False
    assert request_id not in waiting_for(legacy, tara)
    refused = approve(legacy.app, request_id, tara)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_ROLE.format(
        act=ACTIVATION_ACT, nth="second", role="Controller"
    )
    assert status(legacy, request_id) == ("PENDING", 2)
    assert commit_jobs(legacy, import_id) == []

    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"


def _review(name: str) -> dict[str, Any]:
    return {"name": name, "permission": "modification.approve", "min_approvers": 1}


@pytest.mark.control("CTL-010")
def test_r109_an_unevaluated_amount_takes_every_rule_that_could_win(
    legacy: LegacyWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader of item IMP-FLOOR-AMOUNT-1, reading 2 (ruling R-109 (d) as answered on
    2026-10-01): an amount the dry run could not state counts as the strictest outcome — every
    rule that could route the request for SOME amount is asked for. The workspace routes a
    modification of up to 999,999.99 through one review and one of 1,000,000.00 or more through
    three; the rule for the small amounts ranks first. The golden step 08 file is diffed while
    the engine is down, so its modification is stated unevaluated — flags and amount. The
    import takes the three approvers of the rule a large amount would reach, with the
    Controller of the subject's own second step among them.

    Fail-first: a reader that takes every condition on the amount as met picks the best-ranked
    rule — the one for small amounts — and the request has two approvals to give instead of
    three; so has a reader that routes without the amount."""
    cora = person(legacy, clock, "cora", "controller")
    routing_rule(
        legacy,
        "ROUTE-MOD-1-SMALL",
        "MODIFICATION",
        [_review("Modification review")],
        amount=("lte", "999999.99"),
    )
    routing_rule(
        legacy,
        "ROUTE-MOD-2-LARGE",
        "MODIFICATION",
        [_review("Modification review"), _review("Second review"), _review("Third review")],
        amount=("gte", "1000000.00"),
    )
    replayed(legacy, "07")
    (step,) = [item for item in golden_streams.steps("08") if item.number == "08"]

    def failing(bundle: Any) -> Any:
        raise RuntimeError("the engine is down")

    with monkeypatch.context() as patched:
        patched.setattr(computation, "default_engine", lambda: failing)
        import_id = diffed(
            legacy.imports,
            step.workbook.name,
            step.workbook.read_bytes(),
            "legacy_contract_modification",
            {"effective_date": "2023-05-15", "mode": "retrospective"},
        )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None),
        (2, "modification.approve", "controller"),
        (3, "modification.approve", None),
    ]
    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert status(legacy, request_id) == ("PENDING", 2)
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert status(legacy, request_id) == ("PENDING", 3)
    third = approve(legacy.app, request_id, cora)
    assert third.status_code == 200, third.text
    assert third.json()["status"] == "APPROVED"


def reviewers(world: LegacyWorld) -> set[UUID | None]:
    """The reviewers the commit named on the judgement records it reviewed."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return {
            row.reviewer_id
            for row in session.execute(
                select(judgement_record.c.reviewer_id).where(
                    judgement_record.c.status == "REVIEWED"
                )
            )
        }


@pytest.mark.control("CTL-005")
def test_r98_each_act_names_the_approver_who_answered_for_it(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """Ruling R-98 (9) as refined (04 §16.10 rev 1.198): an act the commit performs names the
    approver who answered for it by ordinal, not whoever decided the request's last step. A
    Contract Setup upload at the Controller threshold takes two approvers — the activation's
    second step — while its judgement records take one reviewer. Priya gives the first approval
    and answers for the review: ``judgement.review`` was asked of her then. Marcus gives the
    second and answers for the activation's Controller step. The commit names Priya as the
    reviewer of the judgement records.

    Fail-first: the commit named the request's last approver — Marcus, of whom the review's
    permission was never asked."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(
        legacy.imports, "Contract Setup large.xlsx", setup_file(1_000_000), "legacy_contract_setup"
    )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None),
        (2, "contract.approve", "controller"),
    ]
    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    clock.advance(timedelta(seconds=30))  # Marcus decides later: he is the last approver
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"
    assert reviewers(legacy) == {legacy.priya.member.user_id}


def test_r92_a_request_whose_upload_is_gone_is_decided_by_nobody(legacy: LegacyWorld) -> None:
    """``can_decide`` answers false, never an error (04 §16.10; ruling R-64 (7) (c)), and the
    subject's own check of its deciders keeps to that: an ``IMPORT_COMMIT`` request whose upload
    row does not exist — a row the product never writes — is shown and listed without a failure,
    waits for nobody, and its approval answers 404 like an unknown id."""
    context = DbContext(tenant_id=legacy.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        request_id = insert_approval_request(
            session,
            tenant_id=legacy.tenant_id,
            subject_type=ApprovalSubjectType.IMPORT_COMMIT.value,
            subject_id=new_id(),
        )
        insert_approval_step(
            session,
            tenant_id=legacy.tenant_id,
            approval_request_id=request_id,
            required_permission="import.approve",
        )
    assert can_decide(legacy, str(request_id), legacy.priya) is False
    assert str(request_id) not in waiting_for(legacy, legacy.priya)
    refused = approve(legacy.app, str(request_id), legacy.priya)
    assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text
    assert status(legacy, str(request_id)) == ("PENDING", 1)
    assert decisions(legacy, str(request_id)) == []
