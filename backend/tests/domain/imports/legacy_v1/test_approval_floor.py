"""An import commit never stands in for a stricter approval (supervisor ruling R-38 (ii); 04 rev
1.107 §16.6 template scope table and ``diff_summary.underlying_approvals``; 05 rev 1.46 IPL-07 to
IPL-09; PRD §2.5 rev 1.36 routing row ``IMPORT_COMMIT``; 03 REQ-PLT-013, REQ-PLT-016,
REQ-SSP-007, REQ-CON-006; controls CTL-005, CTL-010).

The commit of a legacy v1 upload performs approvals by itself: it approves the SSP book version,
activates the contracts, approves a modification. The dry run states them with the routing flags
the underlying subject gives the file's content; the decision that would approve the import is
refused — and nothing is approved — unless the approvers satisfy the underlying subject's own
steps; and such an upload is never auto-approved.

World ``support.legacy_replay.legacy_world``: Maya uploads; Priya is a Revenue Reviewer and an SSP
Approver; Marcus a Controller. Rex is a Revenue Reviewer only: ``import.approve`` without
``ssp.approve``. Jobs run as the worker runs them.

Item IMP-FLOOR-AMOUNT-1 and supervisor rulings R-96, R-98 (4), R-102 (f) and R-109 (04 rev 1.147
§16.6): the dry run states the approvals one by one — per approval the flags and the functional
amount a request of the underlying subject would carry (``instances``); the estimate version of a
setup row is the nil-impact case, evaluated without a flag; and a modification whose dry-run
computation did not succeed is not evaluated at all.
"""

from __future__ import annotations

import dataclasses
import io
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects as approval_subjects
from erev_api.approvals.engine import ROLE_REQUIRED_DETAIL
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    api_client,
    approval_decision,
    approval_request,
    approval_step,
    contract,
    contract_event,
    import_upload,
    job,
    role,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.contracts import computation
from erev_api.domain.imports import commit, scope, upload
from erev_api.domain.imports import diff as import_diff
from erev_api.enums import (
    ApprovalSubjectType,
    FilePurpose,
    PrincipalKind,
    RuleSetKind,
    TenantKind,
)
from erev_api.files.store import LocalFileStore, store_file
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.schemas.imports import ImportCreateIn, ImportOut, ImportSubmitIn
from erev_api.uow import UnitOfWork, unit_of_work
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support import golden_streams
from support.db import TestDatabase
from support.factories import (
    maya_principal,
    run_import_job,
    tenant_factory,
    tenant_id_of,
    workbook_bytes,
)
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
from support.reference import approve, assign, get, slug
from support.rows import (
    api_client_values,
    insert_active_membership,
    insert_role_assignment,
    publish_rule_set,
)

SSP_NAME = "SKU SSP Template.xlsx"
SETUP_NAME = "Contract Setup Template 1.1.2023.xlsx"
# Item ACT-FLAGS-1 (04 §16.10 rev 1.287; the supervisor's rulings of 2026-10-02 — STALE
# EXPECTATION: each list read ``MANUAL_ENTRY`` alone): what the activation of a contract of the
# setup file states. ``MANUAL_ENTRY`` since ruling R-38 (i): a person uploaded the file.
# ``NON_STANDARD_TERMS``: a setup's lines name their own accounts, by the template's own columns —
# every legacy setup's contract carries it. ``TERMS_NOT_STATED``: the legacy template states
# neither of the two terms of a booking (register index 261). ``NEW_SKU``: no activated contract
# of the workspace holds a line of its products. The activation is the import's, which no rule
# approves, so none of them routes anything here.
SETUP_FLAGS = ("MANUAL_ENTRY", "NEW_SKU", "NON_STANDARD_TERMS", "TERMS_NOT_STATED")
# Contract 2 holds a row of stratification ``VC``: variable consideration. Its amount moved with
# ruling R-66 (4), from 900.00 to 1,000.00: the larger of the booked consideration — 600.00 +
# 400.00 + 0.00 − 100.00, the ``VC`` row among the lines — and the transaction price of the
# draft's stored version, which the dry run computes before the row's element exists.
SETUP_VC_FLAGS = (*SETUP_FLAGS, "VARIABLE_CONSIDERATION")
SSP_ACT = "approves its SSP book version"
ACTIVATION_ACT = "activates its contracts"
MODIFICATION_ACT = "approves its contract modifications"
MODIFICATION = "legacy_contract_modification"


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


def rex(world: LegacyWorld, clock: FrozenClock) -> Actor:
    """A Revenue Reviewer for every entity, MFA enrolled: ``import.approve`` and no
    ``ssp.approve``."""
    someone = colleague(world.imports.tenant_id, "rex")
    assign(someone, "revenue_reviewer")
    return enrolled(world.app, clock, someone)


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


def underlying(world: LegacyWorld, import_id: str) -> Any:
    return shown(world.imports, import_id)["diff_summary"].get("underlying_approvals")


def instance(
    *flags: str,
    evaluated: bool = True,
    amount: str | None = None,
    amount_evaluated: bool = True,
    count: int = 1,
) -> dict[str, Any]:
    """One member of ``instances`` (04 §16.6 rev 1.147): the routing facts ``count`` approvals of
    one subject would carry as requests of their own; ``amount`` in USD, the functional currency
    of the world's entities."""
    return {
        "flags": sorted(flags),
        "evaluated": evaluated,
        "amount": None if amount is None else {"amount": amount, "currency": "USD"},
        "amount_evaluated": amount_evaluated,
        "count": count,
    }


def stated(
    *flags: str,
    evaluated: bool = True,
    amount: str | None = None,
    amount_evaluated: bool = True,
    count: int = 1,
) -> scope.UnderlyingInstance:
    """``instance`` as ``scope.approval_floor`` passes it on."""
    return scope.UnderlyingInstance(
        flags=frozenset(flags),
        evaluated=evaluated,
        amount=None if amount is None else (Decimal(amount), "USD"),
        amount_evaluated=amount_evaluated,
        count=count,
    )


def floor(world: LegacyWorld, import_id: str) -> tuple[scope.UnderlyingApproval, ...]:
    context = DbContext(tenant_id=world.imports.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return scope.approval_floor(session, UUID(import_id))


def submitted(world: LegacyWorld, import_id: str) -> str:
    response = submit(world.imports, import_id)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUBMITTED", response.text
    return str(response.json()["approval_request_id"])


def nothing_approved(world: LegacyWorld, import_id: str, request_id: str) -> None:
    """The refusal undid the decision: the import waits, the request is PENDING without a
    decision, and no commit job exists."""
    rows = world.imports.rows
    assert shown(world.imports, import_id)["status"] == "SUBMITTED"
    (request,) = rows(
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
    )
    assert str(request["status"]) == "PENDING"
    assert (
        rows(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == UUID(request_id)
            )
        )
        == []
    )
    assert (
        rows(
            select(job.c.id).where(
                job.c.subject_id == UUID(import_id), job.c.kind == "IMPORT_COMMIT"
            )
        )
        == []
    )


def steps(world: LegacyWorld, request_id: str) -> list[tuple[int, str, str | None, str]]:
    """The steps of a request: number, permission, the code of the role it names, status."""
    found = world.imports.rows(
        select(
            approval_step.c.step_no,
            approval_step.c.required_permission,
            role.c.code,
            approval_step.c.status,
        )
        .select_from(approval_step.outerjoin(role, role.c.id == approval_step.c.required_role_id))
        .where(approval_step.c.approval_request_id == UUID(request_id))
        .order_by(approval_step.c.step_no)
    )
    return [
        (
            int(row["step_no"]),
            str(row["required_permission"]),
            None if row["code"] is None else str(row["code"]),
            str(row["status"]),
        )
        for row in found
    ]


def first_approval_stands(world: LegacyWorld, import_id: str, request_id: str) -> None:
    """Supervisor ruling R-92: after the first of two approvals the import still waits — the
    request is PENDING at its second step with one decision, and no commit job exists."""
    rows = world.imports.rows
    assert shown(world.imports, import_id)["status"] == "SUBMITTED"
    (request,) = rows(
        select(approval_request.c.status, approval_request.c.current_step_no).where(
            approval_request.c.id == UUID(request_id)
        )
    )
    assert (str(request["status"]), int(request["current_step_no"])) == ("PENDING", 2)
    decided = rows(
        select(approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert [str(row["decision"]) for row in decided] == ["APPROVE"]
    assert (
        rows(
            select(job.c.id).where(
                job.c.subject_id == UUID(import_id), job.c.kind == "IMPORT_COMMIT"
            )
        )
        == []
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
def test_r38_an_approver_without_the_underlying_permission_is_refused(
    legacy: LegacyWorld, clock: FrozenClock
) -> None:
    """The commit of a SKU SSP upload approves the book version (S01-R-05), so its approval needs
    ``ssp.approve`` — REQ-SSP-007: "an SSP Approver other than the preparer". Rex holds
    ``import.approve`` only: refused by name, nothing approved. Priya holds both: approved, and
    the commit approves the version."""
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    # The dry run states what the commit performs; the book has no entity (R-41 (5)).
    # Item IMP-FLOOR-AMOUNT-1: one approval, whose own request carries no amount.
    assert underlying(legacy, import_id) == [
        {
            "subject_type": "SSP_BOOK_VERSION",
            "flags": [],
            "evaluated": True,
            "instances": [instance()],
        }
    ]
    assert floor(legacy, import_id) == (
        scope.UnderlyingApproval(
            subject_type=ApprovalSubjectType.SSP_BOOK_VERSION,
            permission="ssp.approve",
            min_approvers=1,
            entity_ids=frozenset(),
            flags=frozenset(),
            evaluated=True,
            second_step=False,
            second_step_role=None,
            instances=(stated(),),
        ),
    )
    request_id = submitted(legacy, import_id)

    refused = approve(legacy.app, request_id, rex(legacy, clock))
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_PERMISSION.format(
        act=SSP_ACT, permission="ssp.approve"
    )
    nothing_approved(legacy, import_id, request_id)
    assert versions(legacy) == []

    # Positive control: an approver who holds the import's and the underlying permission.
    decided = approve(legacy.app, request_id, legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"
    assert versions(legacy) == [("2023-01-01", "APPROVED")]


@pytest.mark.control("CTL-010")
def test_r38_a_second_step_of_the_underlying_subject_is_never_approved_short(
    legacy: LegacyWorld,
) -> None:
    """REQ-SSP-007 / PRD §2.5: a version that moves an entry's mid value by more than 10 % needs a
    second ``ssp.approve``. An import that carries such a version states the flag and is not
    approved by one person; a version that moves it by exactly 10 % is.

    Supervisor ruling R-92 moved the expectation of the first approval (STALE EXPECTATION: it
    answered 403 ``FLOOR_SECOND_STEP`` from the backstop, and such an import could then not be
    approved at all): the request is routed with the underlying subject's second step, so the
    first approval answers 200 and leaves it PENDING with nothing approved, the first approver
    cannot take the second step, and a second SSP Approver decides the request."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")

    above_id = diffed(legacy.imports, "SKU SSP 2024 above.xlsx", ssp_file(120), "legacy_sku_ssp")
    assert underlying(legacy, above_id) == [
        {
            "subject_type": "SSP_BOOK_VERSION",
            "flags": ["ABOVE_THRESHOLD"],
            "evaluated": True,
            "instances": [instance("ABOVE_THRESHOLD")],
        }
    ]
    (item,) = floor(legacy, above_id)
    assert (item.second_step, item.second_step_role, item.permission) == (True, None, "ssp.approve")
    request_id = submitted(legacy, above_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None, "ACTIVE"),
        (2, "ssp.approve", None, "WAITING"),
    ]
    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    first_approval_stands(legacy, above_id, request_id)
    assert versions(legacy) == [("2023-01-01", "APPROVED")]
    again = approve(legacy.app, request_id, legacy.priya)
    assert (again.status_code, slug(again)) == (409, "approver-already-decided"), again.text
    first_approval_stands(legacy, above_id, request_id)

    # Positive control: at the threshold, not above it, one SSP approver decides.
    at_id = diffed(
        legacy.imports, "SKU SSP 2025 at.xlsx", ssp_file(110, "2025-01-01"), "legacy_sku_ssp"
    )
    assert underlying(legacy, at_id) == [
        {
            "subject_type": "SSP_BOOK_VERSION",
            "flags": [],
            "evaluated": True,
            "instances": [instance()],
        }
    ]
    decided = approve(legacy.app, submitted(legacy, at_id), legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(at_id), "IMPORT_COMMIT"))
    assert versions(legacy) == [("2023-01-01", "APPROVED"), ("2025-01-01", "APPROVED")]

    # The second SSP Approver decides the flagged import (R-92): Marcus holds ``ssp.approve``.
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    assert shown(legacy.imports, above_id)["status"] == "APPROVED"


@pytest.mark.control("CTL-005")
def test_r38_a_contract_setup_states_what_its_commit_performs(legacy: LegacyWorld) -> None:
    """The commit of a setup upload activates its contracts (BR-DAT-06), reviews their judgement
    records and approves the estimate version of a ``VC`` row (S01-R-06); the dry run evaluates the
    activation's routing flags on the contracts it booked. An upload that asks for no activation
    performs only the estimate approval. The floor names the entities of the file.

    Item IMP-FLOOR-AMOUNT-1: it states them one by one, with the amount each would carry as a
    request of its own — an activation the larger of the booked consideration of its contract
    and the price of its stored version (ruling R-66 (4), item ACT-FLAGS-1; WLD-F-02: Contract 1
    500.00 + 400.00 + 400.00 + 0.00; Contract 2 booked 600.00 + 400.00 + 0.00 − 100.00 and
    priced 1,000.00, ``SETUP_VC_FLAGS``), a judgement review none.

    Supervisor rulings R-96 and R-102 (f) moved the estimate version's expectation, in both
    halves (STALE EXPECTATION: it read ``evaluated`` false): the commit approves the VC element
    version on a DRAFT contract it has just booked — activated by the same commit or, without
    ``activate_on_approval``, not at all — so the version recognises nothing: evaluated, no flag,
    a nil amount. A setup row naming a contract that is not DRAFT never reaches an approval
    (``test_tc_setup_22_existing_contract_rejected_with_pointer`` of
    ``test_contract_setup.py``)."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(legacy.imports, SETUP_NAME, SETUP_2023.read_bytes(), "legacy_contract_setup")
    # ``MANUAL_ENTRY``: Maya uploaded the file, so the contracts its commit books are a person's
    # content (supervisor ruling R-38 (i): authorship, not the submitting principal, makes an
    # activation system-originated) — the flag joined the expectation when the two lanes met.
    # The other flags, and Contract 2's amount: item ACT-FLAGS-1 (``SETUP_FLAGS``).
    assert underlying(legacy, import_id) == [
        {
            "subject_type": "CONTRACT_ACTIVATION",
            "flags": list(SETUP_VC_FLAGS),
            "evaluated": True,
            "instances": [
                instance(*SETUP_FLAGS, amount="1300.00"),
                instance(*SETUP_VC_FLAGS, amount="1000.00"),
            ],
        },
        # Evaluated, no flag (supervisor rulings R-96 and R-102 (f)): the VC element version is
        # approved on the DRAFT contract the commit has just booked, so ``PL_IMPACT_GE_50K`` —
        # the Controller's second step of an estimate version since ruling R-41 (7) — cannot
        # apply (R-66 (4)). A setup row naming a contract that is not DRAFT never reaches an
        # approval: ``test_tc_setup_22_existing_contract_rejected_with_pointer`` of
        # ``test_contract_setup.py``.
        {
            "subject_type": "ESTIMATE_VERSION",
            "flags": [],
            "evaluated": True,
            "instances": [instance(amount="0.00")],
        },
        {
            "subject_type": "JUDGEMENT_RECORD",
            "flags": [],
            "evaluated": False,
            "instances": [instance(evaluated=False, count=2)],
        },
    ]
    found = floor(legacy, import_id)
    assert [(item.subject_type.value, item.permission, item.second_step) for item in found] == [
        ("CONTRACT_ACTIVATION", "contract.approve", False),
        ("JUDGEMENT_RECORD", "judgement.review", False),
        ("ESTIMATE_VERSION", "estimate.approve", False),
    ]
    assert {item.entity_ids for item in found} == {frozenset(legacy.entity_ids.values())}
    # The floor passes the statement on, amounts as decimals (``scope.UnderlyingInstance``).
    assert [item.instances for item in found] == [
        (stated(*SETUP_FLAGS, amount="1300.00"), stated(*SETUP_VC_FLAGS, amount="1000.00")),
        (stated(evaluated=False, count=2),),
        (stated(amount="0.00"),),
    ]

    # No activation asked for (L5-1-Q-16): the contracts stay DRAFT and take their own activation
    # approval; the estimate version of the VC row is approved by the commit all the same.
    drafts_id = diffed(
        legacy.imports,
        "Contract Setup drafts.xlsx",
        setup_file(500),
        "legacy_contract_setup",
        {"activate_on_approval": False},
    )
    assert underlying(legacy, drafts_id) == [
        {
            "subject_type": "ESTIMATE_VERSION",
            "flags": [],
            "evaluated": True,
            "instances": [instance(amount="0.00")],
        }
    ]
    assert [item.subject_type.value for item in floor(legacy, drafts_id)] == ["ESTIMATE_VERSION"]


@pytest.mark.control("CTL-005")
def test_r38_an_activation_at_the_controller_threshold_is_never_approved_short(
    legacy: LegacyWorld,
) -> None:
    """PRD §2.5 ``CONTRACT_ACTIVATION``: from USD 1,000,000.00 a second step held by a Controller.
    A setup upload whose contract reaches it states the flags, and the import is not approved by
    the Revenue Reviewer alone; the file as delivered (1,300.00) is.

    Supervisor ruling R-92 moved the expectation of the first approval (STALE EXPECTATION: it
    answered 403 ``FLOOR_SECOND_STEP`` from the backstop): the request carries the activation's
    second step with the Controller role, so the Revenue Reviewer's approval answers 200 and
    leaves it PENDING with no contract booked, she cannot take the second step, and the
    Controller decides the request."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    import_id = diffed(
        legacy.imports, "Contract Setup large.xlsx", setup_file(1_000_000), "legacy_contract_setup"
    )
    activation = next(
        item
        for item in underlying(legacy, import_id)
        if item["subject_type"] == "CONTRACT_ACTIVATION"
    )
    # One contract reaches the threshold (1,000,000.00 + 400.00 + 400.00 + 0.00) and one does
    # not: each activation is stated with its own flags and amount (item IMP-FLOOR-AMOUNT-1).
    # ``MANUAL_ENTRY`` beside the two thresholds: a person uploaded the file (ruling R-38 (i)).
    # The other flags, and Contract 2's amount: item ACT-FLAGS-1 (``SETUP_FLAGS``).
    assert activation == {
        "subject_type": "CONTRACT_ACTIVATION",
        "flags": sorted({"ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD", *SETUP_VC_FLAGS}),
        "evaluated": True,
        "instances": [
            instance(
                "ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD", *SETUP_FLAGS, amount="1000800.00"
            ),
            instance(*SETUP_VC_FLAGS, amount="1000.00"),
        ],
    }
    first = floor(legacy, import_id)[0]
    assert (first.permission, first.second_step, first.second_step_role) == (
        "contract.approve",
        True,
        "controller",
    )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [
        (1, "import.approve", None, "ACTIVE"),
        (2, "contract.approve", "controller", "WAITING"),
    ]
    first = approve(legacy.app, request_id, legacy.priya)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PENDING"
    first_approval_stands(legacy, import_id, request_id)
    assert legacy.imports.rows(select(contract.c.id)) == []
    # The second step names the Controller role, which the Revenue Reviewer does not hold.
    again = approve(legacy.app, request_id, legacy.priya)
    assert (again.status_code, slug(again)) == (403, "forbidden"), again.text
    assert again.json()["detail"] == ROLE_REQUIRED_DETAIL.format(role="Controller")
    first_approval_stands(legacy, import_id, request_id)
    assert legacy.imports.rows(select(contract.c.id)) == []

    # The Controller decides the second step (R-92), and the commit books and activates.
    second = approve(legacy.app, request_id, legacy.marcus)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "APPROVED"
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert shown(legacy.imports, import_id)["status"] == "COMMITTED"
    booked = legacy.imports.rows(select(contract.c.status).order_by(contract.c.external_id))
    assert booked and {str(row["status"]) for row in booked} == {"ACTIVE"}


@pytest.mark.control("CTL-010")
def test_r38_the_backstop_refuses_a_request_routed_without_the_underlying_second_step(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backstop of R-38 (ii) holds where the routing did not carry the step — a request
    routed before ruling R-92, or a floor that failed to reach the routing. With the further
    steps and the per-decision check of the ``IMPORT_COMMIT`` subject switched off, the request
    has its own step only, and the decision that would approve the import is refused by name with
    nothing approved: the two refusals this module asserted at the first approval before the
    ruling moved that expectation."""
    lifecycle = approval_subjects.LIFECYCLES[ApprovalSubjectType.IMPORT_COMMIT]
    monkeypatch.setitem(
        approval_subjects.LIFECYCLES,
        ApprovalSubjectType.IMPORT_COMMIT,
        dataclasses.replace(lifecycle, floor=lambda *_: (), deciders=lambda *_: {}),
    )
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")

    above_id = diffed(legacy.imports, "SKU SSP 2024 above.xlsx", ssp_file(120), "legacy_sku_ssp")
    request_id = submitted(legacy, above_id)
    assert steps(legacy, request_id) == [(1, "import.approve", None, "ACTIVE")]
    refused = approve(legacy.app, request_id, legacy.priya)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_SECOND_STEP.format(act=SSP_ACT, holder="")
    nothing_approved(legacy, above_id, request_id)
    assert versions(legacy) == [("2023-01-01", "APPROVED")]

    import_id = diffed(
        legacy.imports, "Contract Setup large.xlsx", setup_file(1_000_000), "legacy_contract_setup"
    )
    request_id = submitted(legacy, import_id)
    assert steps(legacy, request_id) == [(1, "import.approve", None, "ACTIVE")]
    refused = approve(legacy.app, request_id, legacy.priya)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_SECOND_STEP.format(
        act=ACTIVATION_ACT, holder=" by a Controller"
    )
    nothing_approved(legacy, import_id, request_id)
    assert legacy.imports.rows(select(contract.c.id)) == []


def amended(world: LegacyWorld, import_id: str) -> list[dict[str, Any]]:
    return world.imports.rows(
        select(contract_event.c.id).where(
            contract_event.c.import_upload_id == UUID(import_id),
            contract_event.c.event_type == "CONTRACT_AMENDED",
        )
    )


@pytest.mark.control("CTL-010")
def test_r98_a_modification_whose_dry_run_computation_did_not_succeed_is_not_evaluated(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R-98 (4). A computation that fails or is quarantined is stored, not raised, and leaves the
    earlier version in place: the dry run of a legacy modification then read "nothing changed"
    and stated ``MODIFICATION``, no flag, evaluated — so one holder of ``modification.approve``
    approved an amendment of any size and the Controller's step never applied. The golden step
    08 file (Contract 2, POB #1, +400.00), with an engine that fails: the approval is stated
    unevaluated, its second step counts as applying, and one Revenue Reviewer does not approve
    the import. Positive control: the same rows with the engine at work are evaluated — no flag,
    and the amount of the request is the change of the transaction price the diff shows."""
    replayed(legacy, "07")
    (step,) = [item for item in golden_streams.steps("08") if item.number == "08"]
    parameters = {"effective_date": "2023-05-15", "mode": "retrospective"}

    def failing(bundle: Any) -> Any:
        raise RuntimeError("the engine is down")

    with monkeypatch.context() as patched:
        patched.setattr(computation, "default_engine", lambda: failing)
        failed_id = diffed(
            legacy.imports, step.workbook.name, step.workbook.read_bytes(), MODIFICATION, parameters
        )
    (entry,) = underlying(legacy, failed_id)
    assert entry["evaluated"] is False, entry
    assert entry == {
        "subject_type": "MODIFICATION",
        "flags": [],
        "evaluated": False,
        "instances": [instance(evaluated=False, amount_evaluated=False)],
    }
    (item,) = floor(legacy, failed_id)
    assert (item.permission, item.second_step, item.second_step_role) == (
        "modification.approve",
        True,
        "controller",
    )
    assert item.instances == (stated(evaluated=False, amount_evaluated=False),)
    request_id = submitted(legacy, failed_id)
    attempt = approve(legacy.app, request_id, legacy.priya)
    if attempt.status_code == 200:
        # A request routed with the underlying subject's second step (supervisor ruling R-92,
        # lane SECFIX-APR): her approval is the first of two and decides nothing by itself.
        assert attempt.json()["status"] == "PENDING", attempt.text
    else:
        # The backstop at the decision: refused by name, the decision undone.
        assert (attempt.status_code, slug(attempt)) == (403, "forbidden"), attempt.text
        assert attempt.json()["detail"] == scope.FLOOR_SECOND_STEP.format(
            act=MODIFICATION_ACT, holder=" by a Controller"
        )
    rows = legacy.imports.rows
    assert shown(legacy.imports, failed_id)["status"] == "SUBMITTED"
    (request,) = rows(
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
    )
    assert str(request["status"]) == "PENDING"
    assert (
        rows(
            select(job.c.id).where(
                job.c.subject_id == UUID(failed_id), job.c.kind == "IMPORT_COMMIT"
            )
        )
        == []
    )
    assert amended(legacy, failed_id) == []

    # Positive control: the same rows in a file of other bytes, the engine at work.
    headers, data = workbook_rows(step.workbook)
    computed_id = diffed(
        legacy.imports,
        "Contract Modification step 08 again.xlsx",
        workbook_bytes("Contract Modification", headers, data),
        MODIFICATION,
        parameters,
    )
    listed = get(legacy.app, f"/api/v1/imports/{computed_id}/diff", legacy.maya)
    assert listed.status_code == 200, listed.text
    (price,) = [
        item
        for item in listed.json()["items"]
        if item["measure"] == "transaction_price" and item["contract_external_id"] == "Contract 2"
    ]
    moved = abs(Decimal(price["after"]) - Decimal(price["before"]))
    assert moved > 0, price
    assert underlying(legacy, computed_id) == [
        {
            "subject_type": "MODIFICATION",
            "flags": [],
            "evaluated": True,
            "instances": [instance(amount=f"{moved:.2f}")],
        }
    ]
    (evaluated,) = floor(legacy, computed_id)
    assert (evaluated.second_step, evaluated.instances) == (
        False,
        (stated(amount=f"{moved:.2f}"),),
    )

    # PRD §2.5: from a change of the transaction price of USD 250,000.00, or a catch-up of USD
    # 50,000.00, a second step held by a Controller. The same row priced at 300,000.00 states
    # the flags its figures meet and the amount, and the second step applies.
    billing = headers.index("Mod Billing")
    large_id = diffed(
        legacy.imports,
        "Contract Modification step 08 large.xlsx",
        workbook_bytes(
            "Contract Modification",
            headers,
            [[*row[:billing], 300_000, *row[billing + 1 :]] for row in data],
        ),
        MODIFICATION,
        parameters,
    )
    items = get(legacy.app, f"/api/v1/imports/{large_id}/diff", legacy.maya).json()["items"]
    of_contract = [item for item in items if item["contract_external_id"] == "Contract 2"]
    (price,) = [item for item in of_contract if item["measure"] == "transaction_price"]
    moved = abs(Decimal(price["after"]) - Decimal(price["before"]))
    catch_up = sum(
        (
            Decimal(item["after"]) - Decimal(item["before"])
            for item in of_contract
            if item["measure"] == "revenue_cum"
        ),
        Decimal(0),
    )
    assert moved >= Decimal("250000.00"), price
    flags = ["TP_CHANGE_GE_250K"]
    if abs(catch_up) >= Decimal("50000.00"):
        flags.insert(0, "CATCH_UP_GE_50K")
    assert underlying(legacy, large_id) == [
        {
            "subject_type": "MODIFICATION",
            "flags": flags,
            "evaluated": True,
            "instances": [instance(*flags, amount=f"{moved:.2f}")],
        }
    ]
    (flagged,) = floor(legacy, large_id)
    assert (flagged.second_step, flagged.second_step_role) == (True, "controller")


@pytest.mark.control("CTL-005")
def test_r38_a_plan_the_dry_run_could_not_apply_leaves_its_approvals_unevaluated(
    legacy: LegacyWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan the command services refuse in the dry run books nothing to read flags or an
    amount from, while the commit would still perform its approvals: every approval the
    template can perform is stated once, unevaluated, for that plan — beside what the plans
    that applied state. With Contract 2 of the setup file refused: the activations are one
    unevaluated and one of 1,300.00, the floor's second step counts as applying, and the import
    still reaches DIFF_READY with the refusal as a finding."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    emitter_of = import_diff.emitter_of
    template = emitter_of("legacy_contract_setup")
    assert template is not None

    def refusing(uow: Any, plan: Any, *, context: Any) -> Any:
        if plan.key == "Contract 2":
            raise Problem("validation-failed", "Contract 2 cannot be booked today.")
        return template.apply(uow, plan, context=context)

    def patched(code: str) -> Any:
        found = emitter_of(code)
        return dataclasses.replace(found, apply=refusing) if found is template else found

    with monkeypatch.context() as patch:
        patch.setattr(import_diff, "emitter_of", patched)
        import_id = diffed(
            legacy.imports, SETUP_NAME, SETUP_2023.read_bytes(), "legacy_contract_setup"
        )
    unstated = instance(evaluated=False, amount_evaluated=False)
    assert underlying(legacy, import_id) == [
        {
            "subject_type": "CONTRACT_ACTIVATION",
            "flags": list(SETUP_FLAGS),  # item ACT-FLAGS-1: Contract 1 as ``SETUP_FLAGS`` says
            "evaluated": False,
            "instances": [unstated, instance(*SETUP_FLAGS, amount="1300.00")],
        },
        {
            "subject_type": "ESTIMATE_VERSION",
            "flags": [],
            "evaluated": False,
            "instances": [unstated],
        },
        {
            "subject_type": "JUDGEMENT_RECORD",
            "flags": [],
            "evaluated": False,
            "instances": [unstated, instance(evaluated=False)],
        },
    ]
    first = floor(legacy, import_id)[0]
    assert (first.subject_type.value, first.second_step, first.second_step_role) == (
        "CONTRACT_ACTIVATION",
        True,
        "controller",
    )
    summary = shown(legacy.imports, import_id)["diff_summary"]
    assert (summary["contracts_affected"], summary["contracts_created"]) == (1, 1)


@pytest.mark.control("CTL-010")
def test_r38_an_upload_the_dry_run_did_not_state_answers_for_every_approval(
    legacy: LegacyWorld,
) -> None:
    """An upload whose dry run did not state what the commit performs — one diffed before the
    statement existed — answers for every approval its template can perform, unevaluated: the
    second step counts as applying and the amount as the strictest outcome. Such an upload is
    not approved by one SSP Approver, and the backstop refuses a request no person approved at
    all (``FLOOR_PERSON``)."""
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    context = DbContext(tenant_id=legacy.imports.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        summary = dict(
            session.execute(
                select(import_upload.c.diff_summary).where(import_upload.c.id == UUID(import_id))
            ).scalar_one()
        )
        del summary[scope.UNDERLYING_MEMBER]
        session.execute(
            update(import_upload)
            .where(import_upload.c.id == UUID(import_id))
            .values(diff_summary=summary)
        )
    assert underlying(legacy, import_id) is None
    (item,) = floor(legacy, import_id)
    assert (item.subject_type.value, item.evaluated, item.second_step, item.instances) == (
        "SSP_BOOK_VERSION",
        False,
        True,
        (stated(evaluated=False, amount_evaluated=False),),
    )

    request_id = submitted(legacy, import_id)
    with tenant_session(context, read_only=True) as session:
        with pytest.raises(Problem) as nobody:
            scope.require_floor_met(
                session, UUID(import_id), UUID(request_id), at=legacy.imports.clock.now()
            )
    assert (nobody.value.slug, nobody.value.detail) == (
        "forbidden",
        scope.FLOOR_PERSON.format(act=SSP_ACT),
    )
    attempt = approve(legacy.app, request_id, legacy.priya)
    if attempt.status_code == 200:
        # routed with the underlying second step (ruling R-92, lane SECFIX-APR)
        assert attempt.json()["status"] == "PENDING", attempt.text
    else:
        assert (attempt.status_code, slug(attempt)) == (403, "forbidden"), attempt.text
        assert attempt.json()["detail"] == scope.FLOOR_SECOND_STEP.format(act=SSP_ACT, holder="")
    assert shown(legacy.imports, import_id)["status"] == "SUBMITTED"
    assert versions(legacy) == []


def _unit(world: LegacyWorld, principal: Principal) -> Iterator[UnitOfWork]:
    imports = world.imports
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-import-floor-api-client",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=imports.clock.now(),
        format_locale="en-US",
    )
    runtime = imports.runtime
    assert runtime.keyring is not None and runtime.files is not None
    with unit_of_work(
        ctx, clock=imports.clock, keyring=runtime.keyring, files=runtime.files
    ) as uow:
        yield uow


unit = contextmanager(_unit)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CUSTOMERS_CSV = (
    b"code,name,segment,country_code\nC-501,Harbourline Freight Ltd (Demo),Logistics,PT\n"
)


def service(legacy: LegacyWorld, *held: str) -> Principal:
    """The API client ``svc-salesforce`` for every entity, holding ``import.upload``,
    ``contract.read`` and ``held`` — in its stored scopes, which an import is held to (R-29), and
    as the principal of its requests — with PRD §2.5 ``AUTO-IMP-01`` published for the tenant."""
    imports = legacy.imports
    permissions = frozenset({"import.upload", "contract.read", *held})
    context = DbContext(tenant_id=imports.tenant_id, user_id=None, entity_scope="*")
    client = api_client_values(imports.tenant_id, name="svc-salesforce", scopes=sorted(permissions))
    with tenant_session(context) as session:
        session.execute(insert(api_client).values(**client))
        publish_rule_set(
            session,
            tenant_id=imports.tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="AVM-AUTO-APPROVAL",
            rules=[
                {
                    "rule_key": "AUTO-IMP-01",
                    "conditions": [
                        {"field": "subject.type", "op": "eq", "value": "IMPORT_COMMIT"},
                        {"field": "source.channel", "op": "eq", "value": "API_CLIENT"},
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    return dataclasses.replace(
        maya_principal(imports.actor.member),
        kind=PrincipalKind.API_CLIENT,
        id=UUID(str(client["id"])),
        membership_id=None,
        display_name="svc-salesforce",
        roles=(),
        permissions=permissions,
        permission_scopes=MappingProxyType(dict.fromkeys(permissions, "*")),
    )


def client_submitted(
    legacy: LegacyWorld,
    client: Principal,
    name: str,
    content: bytes,
    template_code: str,
    media_type: str = XLSX,
) -> ImportOut:
    """The client stores and uploads a file, the worker validates and dry-runs it and the client
    submits it; the answer of the submit."""
    imports = legacy.imports
    with unit(legacy, client) as uow:
        stored = store_file(
            uow,
            purpose=FilePurpose.IMPORT_SOURCE,
            stream=io.BytesIO(content),
            original_filename=name,
            media_type=media_type,
        )
        created = upload.create_import(
            uow, body=ImportCreateIn(file_id=stored["id"], template_code=template_code)
        )
        uow.commit()
    run_import_job(imports, created.job.id)
    run_import_job(imports, job_of(imports, created.import_id, "IMPORT_DIFF"))
    with unit(legacy, client) as uow:
        out = commit.submit_import(uow, import_id=created.import_id, body=ImportSubmitIn())
        uow.commit()
    return out


def decisions(legacy: LegacyWorld, out: ImportOut) -> list[str]:
    found = legacy.imports.rows(
        select(approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == out.approval_request_id
        )
    )
    return [str(row["decision"]) for row in found]


def test_r38_an_upload_whose_commit_performs_an_approval_is_never_auto_approved(
    legacy: LegacyWorld,
) -> None:
    """PRD §2.5 ``AUTO-IMP-01`` (API client, control totals match, zero ERROR findings) stays for
    uploads that write transactional data or DRAFT objects. A SKU SSP upload of the same client
    under the same published rule waits for a person: its commit approves an SSP version."""
    out = client_submitted(
        legacy, service(legacy), "svc-salesforce-ssp.xlsx", SKU_SSP.read_bytes(), "legacy_sku_ssp"
    )
    assert out.status == "SUBMITTED"
    assert out.approval_request_id is not None
    assert decisions(legacy, out) == []
    (row,) = legacy.imports.rows(select(import_upload.c.status).where(import_upload.c.id == out.id))
    assert str(row["status"]) == "SUBMITTED"
    assert versions(legacy) == []


@pytest.mark.control("CTL-005")
def test_r38_a_contract_setup_of_an_api_client_is_never_auto_approved(
    legacy: LegacyWorld,
) -> None:
    """The same for a Contract Setup upload: its commit activates the contracts (BR-DAT-06;
    REQ-CON-006), so the published rule does not approve it although the client may create
    contracts for every entity — no decision, no commit job, no contract. Positive control: the
    rule is in force for this client — its customers upload, which puts nothing in force, is
    auto-approved."""
    committed(legacy, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    client = service(legacy, "contract.create", "masterdata.maintain")
    out = client_submitted(
        legacy,
        client,
        "svc-salesforce-setup.xlsx",
        SETUP_2023.read_bytes(),
        "legacy_contract_setup",
    )
    assert out.status == "SUBMITTED"
    assert out.approval_request_id is not None
    assert [item["subject_type"] for item in underlying(legacy, str(out.id))] == [
        "CONTRACT_ACTIVATION",
        "ESTIMATE_VERSION",
        "JUDGEMENT_RECORD",
    ]
    nothing_approved(legacy, str(out.id), str(out.approval_request_id))
    assert legacy.imports.rows(select(contract.c.id)) == []

    control = client_submitted(
        legacy, client, "svc-salesforce-customers.csv", CUSTOMERS_CSV, "customers", "text/csv"
    )
    assert control.status == "APPROVED"
    assert decisions(legacy, control) == ["AUTO_APPROVE"]


def elsewhere(keyring: KeyRing, clock: FrozenClock, someone: Actor, role_code: str) -> UUID:
    """Another workspace in which ``someone`` is an ACTIVE member holding ``role_code`` for every
    entity. ``tenant_membership`` is RLS-TM (04 §2.3): the person's own session reads the
    memberships of both workspaces."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        membership_id = insert_active_membership(
            session, tenant_id=tenant_id, user_id=someone.member.user_id
        )
        insert_role_assignment(
            session, tenant_id=tenant_id, membership_id=membership_id, role_code=role_code
        )
    return tenant_id


@pytest.mark.control("CTL-010")
def test_r38_the_approvers_grants_are_read_in_the_workspace_of_the_import(
    legacy: LegacyWorld, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The backstop reads the approvers' grants in the workspace of the import, in the approver's
    own session — which reads that person's memberships of other workspaces too. Rex holds
    ``ssp.approve`` only in another workspace: refused here by name, nothing approved. Priya is a
    Controller in another workspace besides her roles here: her approval stands and the commit
    approves the version."""
    someone = rex(legacy, clock)
    elsewhere(keyring, clock, someone, "ssp_approver")
    elsewhere(keyring, clock, legacy.priya, "controller")
    import_id = diffed(legacy.imports, SSP_NAME, SKU_SSP.read_bytes(), "legacy_sku_ssp")
    request_id = submitted(legacy, import_id)

    refused = approve(legacy.app, request_id, someone)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == scope.FLOOR_PERMISSION.format(
        act=SSP_ACT, permission="ssp.approve"
    )
    nothing_approved(legacy, import_id, request_id)

    decided = approve(legacy.app, request_id, legacy.priya)
    assert decided.status_code == 200, decided.text
    run_import_job(legacy.imports, job_of(legacy.imports, UUID(import_id), "IMPORT_COMMIT"))
    assert versions(legacy) == [("2023-01-01", "APPROVED")]
