"""Policy overrides and SSP overrides (04 T-CON-23, §15.3 API-R-13 and API-R-29, §16.2
``request-ssp-override``, §16.3 ``LINE_ATTRIBUTES_CHANGED``, §16.5 API-S-PolicyOverride and
API-S-PolicyResolution; POLICIES §0.5, §0.6; dev-guide DG-KRN-REG-01, DG-KRN-REG-06; 05 RCP-17; PRD
§2.5, BR-SSP-03; 03 REQ-SSP-006, REQ-POL-004; CTL-010; BUILD_SPEC CTR-15).

Policy overrides run in ``support.factories.k11_world``: Maya (Revenue Accountant:
``contract.create``, ``config.read``) prepares and Marcus (Controller: ``contract.approve``; MFA)
approves. SSP overrides run in ``support.factories.k02_world``: Maya requests and Priya (SSP
Approver: ``ssp.approve``; MFA) approves ``US-LIST 2026-H2``. [J] L4-2-Q-1: the obligation-level
resolution uses POL-051 ``returns.model`` (levels P, C, O), because POL-052
``returns.reversal_rate`` allows level T only.

The October 7 continuation enables public authoring for POL-122 and POL-047. These tests
exercise public creation, validation, approval and real calculation for both. Unsupported
parameters retain their named refusal after access checks. Historical generic lifecycle cases
continue to seed drafts directly to exercise resolution and approval behavior.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import subjects
from erev_api.approvals.preview import read_preview
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_delegation,
    approval_request,
    audit_event,
    combination_group,
    contract,
    contract_event,
    contract_version,
    obligation,
    obligation_version,
    policy_override,
)
from erev_api.domain.contracts import bundles, policy_inputs
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1, DeliveryRecordedV1, MoneyIn
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.db import TestDatabase
from support.factories import (
    K11_CHART,
    SEAT_MONTH,
    K02World,
    K11World,
    Workspace,
    activated_contract,
    appended,
    approved_ssp_version,
    booked_contract,
    computed,
    delivered_k11,
    drafted_override,
    k02_body,
    k02_seat_month_body,
    k02_world,
    k11_body,
    k11_world,
    range_entry,
)
from support.http import HttpResponse
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assert_approval_hidden, assign, fields, get, post, slug
from support.rows import (
    approval_delegation_values,
    insert_contract_rows,
    insert_policy_override,
    insert_role_assignment,
)
from support.worlds import judgement_submitted

POLICY_OVERRIDES = "/api/v1/policy-overrides"
RESOLVE = "/api/v1/policies/resolve"
OBLIGATIONS = "/api/v1/obligations"
SSP_BOOKS = "/api/v1/ssp-books"
ATTRIBUTES_CHANGED = "LINE_ATTRIBUTES_CHANGED"
RATIONALE = "Returns are expected under this reseller agreement."
JUSTIFICATION = "Negotiated under the second-half list; the order form cites it."
# PRD ERR-102: the refusal's rule id and its two sentences — this one, then what decides the
# parameter instead (POLICIES §0.5 table 0.5-A), spelled out here and not read from the product.
NOT_OFFERED_RULE = "POLICY_OVERRIDE_NOT_OFFERED"
NOT_OFFERED = "Policy overrides for a contract or an obligation are not offered in this release."
BY_THE_PRODUCT = "It is set on the product or on its obligation template."
BY_THE_REGISTRY = "It is set in the policy registry for the workspace."
BY_A_RECORD = "The method of the element's estimate version decides it."
BY_THE_DEFAULT = "The framework's default applies to every contract in this release."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _obligation_id(world: K11World | K02World, contract_id: UUID, key: str) -> UUID:
    statement = select(obligation.c.id).where(
        obligation.c.contract_id == contract_id, obligation.c.obligation_key == key
    )
    return UUID(str(world.place.scalar(statement)))


def _override(contract_id: UUID, policy_key: str, value: Any, **extra: str) -> dict[str, Any]:
    return {
        "contract_id": str(contract_id),
        "policy_key": policy_key,
        "value": value,
        "rationale": RATIONALE,
        **extra,
    }


def _refused(response: HttpResponse, decided_by: str) -> None:
    """The one refusal of a creation (04 T-CON-23 "Not offered in release 1.0"; PRD ERR-102): 422
    ``policy-level-not-allowed`` with one error — field ``policy_key``, rule id
    ``POLICY_OVERRIDE_NOT_OFFERED`` — whose message is the problem's detail as well: that policy
    overrides are not offered in this release, and ``decided_by``."""
    assert response.status_code == 422, response.text
    assert slug(response) == "policy-level-not-allowed", response.text
    assert fields(response) == [("policy_key", NOT_OFFERED_RULE)], response.text
    body = response.json()
    said = f"{NOT_OFFERED} {decided_by}"
    assert (body["detail"], body["errors"][0]["message"]) == (said, said)
    assert "Location" not in response.headers


def _stored(place: Workspace) -> tuple[int, int, int]:
    """(policy overrides, approval requests of the subject, audit events) the workspace holds."""
    requests = (
        select(func.count())
        .select_from(approval_request)
        .where(approval_request.c.subject_type == "POLICY_OVERRIDE")
    )
    return (
        int(place.scalar(select(func.count()).select_from(policy_override))),
        int(place.scalar(requests)),
        int(place.scalar(select(func.count()).select_from(audit_event))),
    )


def _attribute_events(world: K02World, contract_id: UUID) -> list[dict[str, object]]:
    return world.place.rows(
        select(contract_event).where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == ATTRIBUTES_CHANGED,
        )
    )


def _k02_computed(world: K02World) -> tuple[UUID, UUID, UUID]:
    """K-02 booked, activated and computed under US-LIST 2026-H1: (contract, group, O1) ids."""
    booked = booked_contract(world.place, k02_seat_month_body(world.customer_id), activate=False)
    booked = activated_contract(world.place, booked)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    contract_id = booked.contract["id"]
    return contract_id, group_id, _obligation_id(world, contract_id, "O1")


def _second_half(world: K02World) -> str:
    """US-LIST 2026-H2 effective 1 Oct 2026, AVM-SEAT-MO 95.00 / 105.00 / 115.00 USD, approved."""
    return approved_ssp_version(
        world.app,
        world.place.author,
        [world.priya, world.marcus],
        world.book_id,
        label="2026-H2",
        effective_from="2026-10-01",
        entries=[range_entry(SEAT_MONTH, "95.00", "105.00", "115.00", value_basis="AMOUNT")],
    )


def test_policy_override_unsupported_creation_is_refused_by_name(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 T-CON-23 "Not offered in release 1.0" (rev 1.322; PRD ERR-102; POLICIES §0.5 rule 5):
    no computation reads a policy override, so ``POST /policy-overrides`` refuses every creation
    by one rule and says what decides the parameter instead. Maya holds ``contract.create`` and
    reads the K-11 contract; until this revision her first request was stored as a DRAFT (201).
    Nothing is stored now: no override, no approval request, no audit event."""
    world = k11_world(app, keyring, clock, files)
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    contract_id = booked.contract["id"]
    maya = world.place.author
    before = _stored(world.place)
    assert before[:2] == (0, 0)
    asked: tuple[tuple[str, Any, dict[str, str], str], ...] = (
        # The creation the product stored until this revision: POL-051 for obligation O1.
        ("returns.model", "EXPECTED_RETURNS", {"obligation_key": "O1"}, BY_THE_PRODUCT),
        ("returns.model", "EXPECTED_RETURNS", {}, BY_THE_PRODUCT),
        # One parameter of each kind of POLICIES §0.5 table 0.5-A: a record of the contract,
        # another level the parameter lists, the framework's default.
        ("vc.estimation_method", "EXPECTED_VALUE", {}, BY_A_RECORD),
        ("step1.term_with_termination_rights", "STATED_TERM", {}, BY_THE_REGISTRY),
        ("concession.allocation_basis", "INCEPTION_BASIS", {}, BY_THE_DEFAULT),
        # POL-240 lists level P as well, where the engine does not read it (register index 309).
        ("usage.tier_minimum_method", "ESTIMATE_MEASUREMENT_PERIOD_TP", {}, BY_THE_DEFAULT),
        # A parameter that lists neither level is told the catalogue: POL-021 allows T, E and P.
        (
            "pob.shipping_as_fulfilment",
            "FALSE",
            {},
            "It can be set only at workspace, legal entity or product level.",
        ),
    )
    for policy_key, value, extra, decided_by in asked:
        answered = post(
            app, POLICY_OVERRIDES, maya, _override(contract_id, policy_key, value, **extra)
        )
        _refused(answered, decided_by)
    assert _stored(world.place) == before
    # The reads keep their answer: the contract has no override.
    listed = get(app, POLICY_OVERRIDES, maya, {"contract": str(contract_id)})
    assert (listed.status_code, listed.json()["items"]) == (200, [])


def test_policy_override_withdraw_1_the_refusal_comes_before_any_validation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """What the creation validated until rev 1.322 is answered by the one rule: the parameter key
    (422 ``validation-failed`` under T-PLT-31), the level (``POLICY_LEVEL_NOT_ALLOWED``), the
    obligation key (T-CON-10), the value's schema (``POLICY_VALUE_INVALID``) and the judgement
    record of a ``JDG`` parameter (T-CON-23) — none of them is asked any more."""
    world = k11_world(app, keyring, clock, files)
    booked = booked_contract(world.place, k11_body(world.customer_id), activate=False)
    contract_id = booked.contract["id"]
    maya = world.place.author
    before = _stored(world.place)
    asked: tuple[tuple[str, str, dict[str, str], str], ...] = (
        # A key the registry does not hold.
        (
            "returns.no_such_parameter",
            "ANYTHING",
            {},
            "The policy registry holds no parameter of this key.",
        ),
        # A level the parameter does not list: POL-052 allows T only (L4-2-Q-1).
        (
            "returns.reversal_rate",
            "AVERAGE_CARRYING_RATE",
            {"obligation_key": "O1"},
            "It can be set only at workspace level.",
        ),
        # An obligation key the contract does not hold.
        ("returns.model", "EXPECTED_RETURNS", {"obligation_key": "O9"}, BY_THE_PRODUCT),
        # A value outside the parameter's schema.
        ("returns.model", "SOMETIMES", {}, BY_THE_PRODUCT),
        # POL-030 ``pob.principal_or_agent``: approval code JDG, and no judgement record named.
        ("pob.principal_or_agent", "AGENT", {"obligation_key": "O1"}, BY_THE_PRODUCT),
    )
    for policy_key, value, extra, decided_by in asked:
        answered = post(
            app, POLICY_OVERRIDES, maya, _override(contract_id, policy_key, value, **extra)
        )
        _refused(answered, decided_by)
    assert _stored(world.place) == before


def test_approved_override_resolves_at_obligation_level(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The kept code on a row the product no longer creates (04 T-CON-23 "What stays" and "The
    premise"): the fixture writes Maya's DRAFT override of ``returns.model`` for O1; the product's
    own submit and approval follow, and ``GET /policies/resolve`` answers the approved row as the
    value in force — the one reader that would tell a value the books do not use."""
    world = k11_world(app, keyring, clock, files)
    maya = world.place.author
    booked = delivered_k11(world)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    dirty = select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    assert world.place.scalar(dirty) is None
    contract_id = booked.contract["id"]
    scope = {"key": "returns.model", "contract": str(contract_id), "obligation": "O1"}

    override_id = drafted_override(
        world.place,
        contract_id,
        "returns.model",
        "EXPECTED_RETURNS",
        obligation_key="O1",
        rationale=RATIONALE,
    )
    drafted = get(app, f"{POLICY_OVERRIDES}/{override_id}", maya)
    assert drafted.status_code == 200, drafted.text
    draft = drafted.json()
    assert (draft["id"], draft["level"], draft["obligation_key"], draft["status"]) == (
        str(override_id),
        "OBLIGATION",
        "O1",
        "DRAFT",
    )
    before = get(app, RESOLVE, maya, scope).json()
    assert (before["level"], before["source"]["type"]) == ("FRAMEWORK_DEFAULT", "framework_default")

    submitted = post(app, f"{POLICY_OVERRIDES}/{draft['id']}/submit", maya, {"comment": "Ready"})
    assert submitted.status_code == 200, submitted.text
    request_id = submitted.json()["approval_request_id"]
    assert (submitted.json()["status"], request_id is not None) == ("SUBMITTED", True)
    approved = approve(app, str(request_id), world.marcus)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text

    shown = get(app, f"{POLICY_OVERRIDES}/{draft['id']}", maya).json()
    assert (shown["status"], shown["approved_at"]) == ("APPROVED", "2026-09-12T12:00:00Z")
    resolved = get(app, RESOLVE, maya, scope)
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert (body["value"], body["level"], body["source"]) == (
        "EXPECTED_RETURNS",
        "OBLIGATION",
        {"type": "policy_override", "id": draft["id"]},
    )
    assert body["chain"] == [{"level": "OBLIGATION", "found": True, "source_id": draft["id"]}]
    # O2 holds no override: the chain passes the obligation and contract levels to the default.
    other = get(app, RESOLVE, maya, {**scope, "obligation": "O2"}).json()
    assert (other["level"], [link["level"] for link in other["chain"]]) == (
        "FRAMEWORK_DEFAULT",
        ["OBLIGATION", "CONTRACT", "FRAMEWORK_DEFAULT"],
    )
    # 05 RCP-17: approval marks the group dirty.
    assert world.place.scalar(dirty) == clock.now()
    listed = get(app, POLICY_OVERRIDES, maya, {"contract": str(contract_id)})
    assert [item["id"] for item in listed.json()["items"]] == [draft["id"]]


def test_ssp_override_request(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_world(app, keyring, clock, files)
    maya = world.place.author
    contract_id, group_id, o1 = _k02_computed(world)
    second_half = _second_half(world)
    draft = post(
        app,
        f"{SSP_BOOKS}/{world.book_id}/versions",
        maya,
        {
            "legacy_version_label": "2027-H1",
            "effective_from_date": "2027-01-01",
            "methodology_label": "List-price study",
        },
    )
    assert draft.status_code == 201, draft.text
    path = f"{OBLIGATIONS}/{o1}/request-ssp-override"

    refused = post(
        app, path, maya, {"ssp_book_version_id": draft.json()["id"], "justification": JUSTIFICATION}
    )
    assert (refused.status_code, fields(refused)) == (422, [("ssp_book_version_id", "REQ-SSP-006")])
    requested = post(
        app, path, maya, {"ssp_book_version_id": second_half, "justification": JUSTIFICATION}
    )
    assert requested.status_code == 200, requested.text
    assert set(requested.json()) == {"approval_request_id"}
    request_id = str(requested.json()["approval_request_id"])
    assert _attribute_events(world, contract_id) == []

    approved = approve(app, request_id, world.priya)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    (event,) = _attribute_events(world, contract_id)
    assert (event["origin"], event["created_by_kind"], event["approval_request_id"]) == (
        "SYSTEM",
        "SYSTEM",
        UUID(request_id),
    )
    payload = event["payload"]
    assert isinstance(payload, dict)
    assert payload["obligation_key"] == "O1"
    assert (payload["changes"]["ssp_book_version_id"], payload["changes"]["justification"]) == (
        second_half,
        JUSTIFICATION,
    )

    computed(world.place, group_id)
    shown = get(app, f"{OBLIGATIONS}/{o1}", maya)
    assert shown.status_code == 200, shown.text
    ssp = shown.json()["ssp"]
    assert (ssp["book_version_id"], ssp["version_label"], ssp["override_approval_request_id"]) == (
        second_half,
        "2026-H2",
        request_id,
    )


def _pins(world: K02World, obligation_id: UUID) -> list[str]:
    """``subjects.obligation_ssp_pins`` as the approval kernel reads it (the tenant's scope)."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return subjects.obligation_ssp_pins(session, obligation_id)


def _shown_pin(world: K02World, obligation_id: UUID) -> str:
    shown = get(world.app, f"{OBLIGATIONS}/{obligation_id}", world.place.author)
    assert shown.status_code == 200, shown.text
    return str(shown.json()["ssp"]["book_version_id"])


def _numbers(world: K02World, obligation_id: UUID) -> dict[UUID, list[int]]:
    """Combination group → the version numbers the obligation has in it, ascending."""
    rows = world.place.rows(
        select(obligation_version.c.combination_group_id, obligation_version.c.version_no)
        .where(obligation_version.c.obligation_id == obligation_id)
        .order_by(obligation_version.c.version_no)
    )
    found: dict[UUID, list[int]] = {}
    for row in rows:
        found.setdefault(UUID(str(row["combination_group_id"])), []).append(int(row["version_no"]))
    return found


def _override_requested(world: K02World, obligation_id: UUID, version_id: str) -> str:
    requested = post(
        world.app,
        f"{OBLIGATIONS}/{obligation_id}/request-ssp-override",
        world.place.author,
        {"ssp_book_version_id": version_id, "justification": JUSTIFICATION},
    )
    assert requested.status_code == 200, requested.text
    return str(requested.json()["approval_request_id"])


def _stored_before(world: K02World, request_id: str) -> Any:
    """``before`` of the IMPACT_PREVIEW document the request stores and hashes (04 §16.10)."""
    with world.place.uow() as uow:
        file_id = uow.session.execute(
            select(approval_request.c.impact_preview_file_id).where(
                approval_request.c.id == UUID(request_id)
            )
        ).scalar_one()
        document = read_preview(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    return document["before"]


def test_mod_ssp_pin_chain_1_an_override_reads_the_pin_of_the_latest_computation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item MOD-SSP-PIN-CHAIN-1 (supervisor ruling of 2026-10-01 on lane F-RPS-REG's finding
    S-3; a PRODUCT DEFECT of record and of staleness, measured before the fix). The pin an SSP
    override reads as the state before was taken from the obligation's versions with the highest
    ``version_no`` — a number that counts within one combination group. K-02 is computed four
    times on its own and then combined: the combined group starts at version 1, so the group the
    contract had left outranked it. Measured: with O1 priced from 2026-H2 in the combined group,
    the reader still answered 2026-H1; a request made while that pin was computed stayed fresh
    and was approved; and the next request stored 2026-H1 as its ``before`` and its event
    recorded a change from H1 to H1. Now the reader takes the versions of the obligation's
    latest computation: it answers what ``GET /obligations/{id}`` shows, a pending request goes
    stale when the pin under it is computed anew, and the record says H2 to H1."""
    world = k02_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    maya = world.place.author
    contract_id, own_group, o1 = _k02_computed(world)
    first_half, second_half = str(world.version_id), _second_half(world)

    def head() -> int:
        return int(
            world.place.scalar(
                select(contract.c.head_stream_version).where(contract.c.id == contract_id)
            )
        )

    # Two more computations of K-02 on its own: the obligation's fourth version in that group.
    for number in (1, 2):
        billed = EventIn(
            event_type=ContractEventType.BILLING_RECORDED,
            effective_date=date(2026, 9, number),
            payload=BillingRecordedV1(
                invoice_number=f"INV-PIN-{number}",
                line_external_id="1",
                obligation_key="O1",
                amount=MoneyIn(amount="1000.00", currency="USD"),
                issue_date=date(2026, 9, number),
            ),
            obligation_keys=("O1",),
        )
        appended(world.place, contract_id, head(), [billed])
        computed(world.place, own_group)
    assert _numbers(world, o1) == {own_group: [1, 2, 3, 4]}
    assert _pins(world, o1) == [first_half]

    # A second contract of the customer, and the two combined (606-10-25-9(a)).
    other = activated_contract(
        world.place,
        booked_contract(
            world.place,
            {**k02_body(world.customer_id), "external_id": "SF-ORD-10002-B"},
            activate=False,
        ),
    )
    computed(world.place, other.combination_group["id"])
    grouped = post(
        app,
        "/api/v1/combination-groups",
        maya,
        {
            "contract_ids": [str(contract_id), str(other.contract["id"])],
            "criterion": "606-10-25-9(a)",
            "rationale": "Negotiated as a package with Marrowby.",
        },
    )
    assert grouped.status_code == 201, grouped.text
    combined = UUID(str(grouped.json()["id"]))
    routed = post(
        app, f"/api/v1/combination-groups/{combined}/submit", maya, {"comment": "Combine."}
    )
    assert routed.status_code == 200, routed.text
    clock.advance(timedelta(minutes=1))
    assert approve(app, routed.json()["approval_request_id"], world.priya).status_code == 200
    assert _numbers(world, o1) == {own_group: [1, 2, 3, 4], combined: [1]}
    assert (_pins(world, o1), _shown_pin(world, o1)) == ([first_half], first_half)

    # O1 priced from 2026-H2: approved, the event appended, the combined group not yet computed.
    to_second = _override_requested(world, o1, second_half)
    clock.advance(timedelta(minutes=1))
    assert approve(app, to_second, world.priya).status_code == 200
    # A request made before that computation says, rightly, that the obligation stands at H1.
    waiting = _override_requested(world, o1, first_half)
    assert _stored_before(world, waiting) == {"ssp_book_version_ids": [first_half]}

    computed(world.place, combined)
    # The condition of the defect: the group the contract left holds the higher number.
    assert _numbers(world, o1) == {own_group: [1, 2, 3, 4], combined: [1, 2]}
    assert (_pins(world, o1), _shown_pin(world, o1)) == ([second_half], second_half)
    # The pin under the waiting request was computed anew: its decision is stale, not taken.
    clock.advance(timedelta(minutes=1))
    stale = approve(app, waiting, world.priya)
    assert (stale.status_code, slug(stale)) == (409, "stale-approval"), stale.text
    assert len(_attribute_events(world, contract_id)) == 1

    # The request made now states what was there, and its event records H2 to H1.
    back = _override_requested(world, o1, first_half)
    assert _stored_before(world, back) == {"ssp_book_version_ids": [second_half]}
    clock.advance(timedelta(minutes=1))
    assert approve(app, back, world.priya).status_code == 200
    events = sorted(_attribute_events(world, contract_id), key=lambda row: row["stream_version"])
    assert [event["payload"]["diff"]["ssp_book_version_id"] for event in events] == [
        {"before": [first_half], "after": second_half},
        {"before": [second_half], "after": first_half},
    ]
    # The group is not computed again here. The engine re-allocates a group from inception for a
    # corrected pin only while every obligation holds its inception segment (ENGINE_SPEC
    # S06-R-26), so a second pin change of one group is quarantined at its computation — the
    # lane's finding beside this item, measured and reported; the record above is written at
    # the approval.


def test_mod_ssp_pin_chain_1_within_a_group_the_highest_number_is_the_latest_computation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Item MOD-SSP-PIN-CHAIN-1, the second step of ``subjects.obligation_latest_computation``.
    ``known_at`` picks the group; it does not order one group's versions. A version's
    ``known_at`` is the record time of the latest event its computation read, and a group
    computes the events of its present members: K-02 and a second contract are combined, the
    second contract receives the group's latest event, and then leaves. The group's next
    computation — K-02 alone — reads fewer events and is stamped EARLIER than the one before
    it. The computation that last held the obligation is that one, the group's highest
    number, not the one with the latest ``known_at``."""
    world = k02_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    maya = world.place.author
    contract_id, own_group, o1 = _k02_computed(world)
    other = activated_contract(
        world.place,
        booked_contract(
            world.place,
            {**k02_body(world.customer_id), "external_id": "SF-ORD-10002-B"},
            activate=False,
        ),
    )
    other_id = UUID(str(other.contract["id"]))
    computed(world.place, other.combination_group["id"])
    grouped = post(
        app,
        "/api/v1/combination-groups",
        maya,
        {
            "contract_ids": [str(contract_id), str(other_id)],
            "criterion": "606-10-25-9(a)",
            "rationale": "Negotiated as a package with Marrowby.",
        },
    )
    assert grouped.status_code == 201, grouped.text
    combined = UUID(str(grouped.json()["id"]))
    routed = post(
        app, f"/api/v1/combination-groups/{combined}/submit", maya, {"comment": "Combine."}
    )
    assert routed.status_code == 200, routed.text
    clock.advance(timedelta(minutes=1))
    assert approve(app, routed.json()["approval_request_id"], world.priya).status_code == 200

    # The other member receives the group's latest event, and the group is computed with it.
    billed = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 9, 1),
        payload=BillingRecordedV1(
            invoice_number="INV-PIN-B",
            line_external_id="1",
            obligation_key="O1",
            amount=MoneyIn(amount="1000.00", currency="USD"),
            issue_date=date(2026, 9, 1),
        ),
        obligation_keys=("O1",),
    )
    head = int(
        world.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == other_id))
    )
    appended(world.place, other_id, head, [billed])
    computed(world.place, combined)
    # ... and leaves: the group is computed again for K-02 alone.
    leaving = post(
        app,
        f"/api/v1/combination-groups/{combined}/submit",
        maya,
        {
            "leave_contract_ids": [str(other_id)],
            "reason_code": "DATA_CORRECTION",
            "comment": "SF-ORD-10002-B was combined with the wrong order.",
        },
    )
    assert leaving.status_code == 200, leaving.text
    clock.advance(timedelta(minutes=1))
    assert approve(app, leaving.json()["approval_request_id"], world.priya).status_code == 200

    rows = world.place.rows(
        select(
            contract_version.c.version_no,
            contract_version.c.known_at,
            contract_version.c.contract_computation_id,
        )
        .join(
            obligation_version,
            obligation_version.c.contract_version_id == contract_version.c.id,
        )
        .where(
            obligation_version.c.obligation_id == o1,
            obligation_version.c.combination_group_id == combined,
        )
        .order_by(contract_version.c.version_no)
    )
    assert [int(row["version_no"]) for row in rows] == [1, 2, 3]
    stamped = [row["known_at"] for row in rows]
    # The condition: the group's last computation is stamped before the one it follows.
    assert stamped[2] < stamped[1] and stamped[1] == max(stamped)
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        latest = subjects.obligation_latest_computation(session, o1)
    assert latest == UUID(str(rows[2]["contract_computation_id"]))
    first_half = str(world.version_id)
    assert (_pins(world, o1), _shown_pin(world, o1)) == ([first_half], first_half)


@pytest.mark.control("CTL-010")
def test_ctl_010_ssp_override_needs_other_approver(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_world(app, keyring, clock, files)
    contract_id, group_id, o1 = _k02_computed(world)
    second_half = _second_half(world)
    rosa_member = colleague(world.place.tenant_id, "rosa")
    assign(rosa_member, "revenue_accountant")
    assign(rosa_member, "ssp_approver")
    rosa = enrolled(app, clock, rosa_member)

    requested = post(
        app,
        f"{OBLIGATIONS}/{o1}/request-ssp-override",
        rosa,
        {"ssp_book_version_id": second_half, "justification": JUSTIFICATION},
    )
    assert requested.status_code == 200, requested.text
    refused = approve(app, str(requested.json()["approval_request_id"]), rosa)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text

    assert _attribute_events(world, contract_id) == []
    computed(world.place, group_id)
    ssp = get(app, f"{OBLIGATIONS}/{o1}", world.place.author).json()["ssp"]
    assert (ssp["book_version_id"], ssp["version_label"], ssp["override_approval_request_id"]) == (
        world.version_id,
        "2026-H1",
        None,
    )


def test_policy_override_request_is_scoped_to_the_contracting_entity(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """Security review SN-4 (supervisor ruling R-25; 04 §16.10 rev 1.104 "Entity scope of a
    request"; REQ-PLT-012): the ``POLICY_OVERRIDE`` request names the contracting entity of the
    override's contract. One tenant, entities E_in and E_out with one contract each; Tomas
    (Revenue Accountant, all entities) prepares an override on the E_out contract. Rob
    (``contract.approve`` for E_in, no role on E_out) and Rita (``contract.approve`` for E_in and a
    read-only role on E_out — she approved it before the fix) neither read, list nor decide the
    request; Olga (``contract.approve`` for E_out) approves it."""
    owner = member(keyring, clock, name="tomas")
    tenant_id = owner.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=owner.membership_id,
            role_code="revenue_accountant",
        )
        inside = insert_contract_rows(session, tenant_id)
        outside = insert_contract_rows(session, tenant_id)
    e_in, e_out = inside.entity_id, outside.entity_id

    def scoped(name: str, *grants: tuple[str, UUID]) -> Actor:
        someone = colleague(tenant_id, name)
        for role_code, entity_id in grants:
            assign(someone, role_code, entity_ids=[entity_id])
        return enrolled(app, clock, someone)

    tomas = enrolled(app, clock, owner)
    rob = scoped("rob", ("revenue_reviewer", e_in))
    rita = scoped("rita", ("revenue_reviewer", e_in), ("viewer", e_out))
    olga = scoped("olga", ("revenue_reviewer", e_out))

    # Release 1.0 creates no override (04 T-CON-23 rev 1.322): the DRAFT row is the fixture's,
    # written as Tomas's, and the request is made by the product's own submit.
    with tenant_session(context) as session:
        override_id = str(
            insert_policy_override(
                session, tenant_id, contract_id=outside.contract_id, created_by=owner.user_id
            )
        )
    submitted = post(app, f"{POLICY_OVERRIDES}/{override_id}/submit", tomas, {"comment": "x"})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    shown = get(app, f"/api/v1/approvals/{request_id}", tomas)
    assert shown.status_code == 200, shown.text
    assert shown.json()["entity"]["id"] == str(e_out)

    assert_approval_hidden(app, request_id, rob, reader=tomas)
    assert_approval_hidden(app, request_id, rita, reader=tomas)
    pending = get(app, f"{POLICY_OVERRIDES}/{override_id}", tomas)
    assert (pending.json()["status"], pending.json()["approved_at"]) == ("SUBMITTED", None)

    # Positive control: contract.approve for the contracting entity decides it.
    detail = get(app, f"/api/v1/approvals/{request_id}", olga)
    assert detail.status_code == 200 and detail.json()["can_decide"] is True, detail.text
    approved = approve(app, request_id, olga)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert get(app, f"{POLICY_OVERRIDES}/{override_id}", tomas).json()["status"] == "APPROVED"


def test_policy_override_withdraw_1_the_404_and_the_403_come_first(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> None:
    """The positive controls of the refusal (04 T-CON-23 "Not offered in release 1.0", rev
    1.322): what answered a creation before its own rule still answers before it, and none of
    these answers carries the rule id. One tenant, entities E_in and E_out with one contract each.
    Tomas (Revenue Accountant, all entities) is refused by name on the E_out contract — the
    control that the others are not the refusal in another dress. An id that names no contract
    answers him 404; a body the schema refuses, the schema's own 422. Una holds
    ``contract.create`` for E_in alone, so her transaction does not read the E_out contract
    (04 API-C-03 rev 1.319): 404. Vic, a Viewer of E_out, holds no ``contract.create``: 403 at
    the route. Nothing is stored by any of them."""
    owner = member(keyring, clock, name="tomas")
    tenant_id = owner.tenant_id
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=owner.membership_id,
            role_code="revenue_accountant",
        )
        inside = insert_contract_rows(session, tenant_id)
        outside = insert_contract_rows(session, tenant_id)

    def scoped(name: str, role_code: str, entity_id: UUID) -> Actor:
        someone = colleague(tenant_id, name)
        assign(someone, role_code, entity_ids=[entity_id])
        return enrolled(app, clock, someone)

    tomas = enrolled(app, clock, owner)
    una = scoped("una", "revenue_accountant", inside.entity_id)
    vic = scoped("vic", "viewer", outside.entity_id)
    body = _override(outside.contract_id, "returns.model", "EXPECTED_RETURNS")

    def rule_ids(response: HttpResponse) -> list[str | None]:
        return [error.get("rule_id") for error in response.json().get("errors") or []]

    _refused(post(app, POLICY_OVERRIDES, tomas, body), BY_THE_PRODUCT)

    unknown = post(app, POLICY_OVERRIDES, tomas, {**body, "contract_id": str(uuid4())})
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text
    unseen = post(app, POLICY_OVERRIDES, una, body)
    assert (unseen.status_code, slug(unseen)) == (404, "not-found"), unseen.text
    denied = post(app, POLICY_OVERRIDES, vic, body)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    without = {key: value for key, value in body.items() if key != "rationale"}
    shapeless = post(app, POLICY_OVERRIDES, tomas, without)
    assert (shapeless.status_code, slug(shapeless)) == (422, "validation-failed"), shapeless.text
    assert [error["field"] for error in shapeless.json()["errors"]] == ["rationale"]
    for answered in (unknown, unseen, denied, shapeless):
        assert NOT_OFFERED_RULE not in rule_ids(answered), answered.text
        assert NOT_OFFERED not in answered.text

    # The enabled authoring path must preserve the same entity and permission boundary.
    supported = _override(
        outside.contract_id,
        "sfc.discount_rate_basis",
        {"basis": "CUSTOMER_CREDIT_RATE", "annual_rate": "0.06"},
    )
    assert post(app, POLICY_OVERRIDES, una, supported).status_code == 404
    assert post(app, POLICY_OVERRIDES, vic, supported).status_code == 403
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(select(func.count()).select_from(policy_override)).scalar_one()
    assert stored == 0


def test_approved_right_override_changes_computed_balances(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A real approval moves earned, unbilled amounts from assets to receivables."""
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    group_id = booked.combination_group["id"]
    contract_id = booked.contract["id"]
    _, before, _ = computed(world.place, group_id)
    created = post(
        app,
        POLICY_OVERRIDES,
        world.place.author,
        _override(
            contract_id, "balance.right_to_consideration", "UNCONDITIONAL", obligation_key="O1"
        ),
    )
    assert created.status_code == 201, created.text
    override_id = UUID(created.json()["id"])
    with world.place.uow() as uow:
        draft_bundle = bundles.build(uow.session, group_id, uow.now)
    assert not any(
        row.source_ref == str(override_id) for book in draft_bundle.books for row in book.policies
    )
    submitted = post(app, f"{POLICY_OVERRIDES}/{override_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert approved.status_code == 200, approved.text
    with world.place.uow() as uow:
        assert (
            policy_inputs.approved_rows(
                uow.session, [contract_id], clock.now() - timedelta(microseconds=1)
            )
            == []
        )
    bundle, after, _ = computed(world.place, group_id)
    for book in bundle.books:
        rows = [row for row in book.policies if row.source_ref == str(override_id)]
        assert len(rows) == 1
        assert (rows[0].scope, rows[0].level, rows[0].value) == ("OBLIGATION", "O", "UNCONDITIONAL")
    for first, second in zip(before.books, after.books, strict=True):
        before_balances = {
            (row.subject_key, row.period_key): {
                key: Decimal(str(value))
                for key, value in row.columns.items()
                if key
                in {"unbilled_receivable_txn", "contract_asset_txn", "contract_liability_txn"}
            }
            for row in first.balances
        }
        changed = False
        for row in second.balances:
            old = before_balances[(row.subject_key, row.period_key)]
            new = {key: Decimal(str(value)) for key, value in row.columns.items() if key in old}
            if new["unbilled_receivable_txn"] != old["unbilled_receivable_txn"]:
                changed = True
                assert new["unbilled_receivable_txn"] > old["unbilled_receivable_txn"]
                assert new["contract_asset_txn"] < old["contract_asset_txn"]
                assert new["contract_liability_txn"] == old["contract_liability_txn"]
                assert new["unbilled_receivable_txn"] + new["contract_asset_txn"] == (
                    old["unbilled_receivable_txn"] + old["contract_asset_txn"]
                )
        assert changed

    # A scoped pin must never be promoted to GROUP on the next computation.
    repeated_bundle, repeated, _ = computed(world.place, group_id)
    assert [book.balances for book in repeated.books] == [book.balances for book in after.books]
    assert not any(
        row.code == "balance.right_to_consideration" and row.scope == "GROUP"
        for book in repeated_bundle.books
        for row in book.policies
    )
    created = post(
        app,
        POLICY_OVERRIDES,
        world.place.author,
        _override(
            contract_id, "balance.right_to_consideration", "CONDITIONAL", obligation_key="O1"
        ),
    )
    assert created.status_code == 201, created.text
    successor = UUID(created.json()["id"])
    submitted = post(app, f"{POLICY_OVERRIDES}/{successor}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert approved.status_code == 200, approved.text
    # Both approvals share the frozen timestamp; the current approval wins deterministically.
    restored_bundle, restored, _ = computed(world.place, group_id)
    assert [book.balances for book in restored.books] == [book.balances for book in before.books]
    assert not any(
        row.source_ref == str(override_id)
        for book in restored_bundle.books
        for row in book.policies
    )
    shown = get(
        app,
        RESOLVE,
        world.place.author,
        {"key": "balance.right_to_consideration", "contract": str(contract_id), "obligation": "O1"},
    )
    assert shown.json()["source"]["id"] == str(successor)

    assert (
        get(app, f"{POLICY_OVERRIDES}/{override_id}", world.place.author).json()["status"]
        == "SUPERSEDED"
    )


@pytest.mark.parametrize("system_authored", [False, True])
def test_policy_draft_author_cannot_approve_when_someone_else_submits(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, system_authored: bool
) -> None:
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        override_id = insert_policy_override(
            session,
            world.place.tenant_id,
            contract_id=booked.contract["id"],
            obligation_key="O1",
            created_by=None if system_authored else world.marcus.member.user_id,
            policy_key="balance.right_to_consideration",
            value="UNCONDITIONAL",
        )
    if system_authored:
        system = system_principal(
            world.place.tenant_id, on_behalf_of_id=world.marcus.member.user_id
        )
        with world.place.uow(system) as uow:
            uow.audit(
                action="policy_override.create",
                object_type="policy_override",
                object_id=override_id,
                after={"value": "UNCONDITIONAL"},
                contract_id=booked.contract["id"],
            )
            uow.commit()
    submitted = post(app, f"{POLICY_OVERRIDES}/{override_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    request_id = str(submitted.json()["approval_request_id"])
    detail = get(app, f"/api/v1/approvals/{request_id}", world.marcus)
    assert detail.status_code == 200, detail.text
    assert detail.json()["can_decide"] is False
    refused = approve(app, request_id, world.marcus)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert "authored this draft" in refused.json()["detail"]
    assert (
        get(app, f"{POLICY_OVERRIDES}/{override_id}", world.place.author).json()["status"]
        == "SUBMITTED"
    )
    # A delegate cannot use the author's approval authority to bypass the same exclusion.
    delegate_member = colleague(world.place.tenant_id, "policy-author-delegate")
    assign(delegate_member, "revenue_accountant")
    delegate = enrolled(app, clock, delegate_member)
    with tenant_session(context) as session:
        values = approval_delegation_values(
            world.place.tenant_id,
            delegator_membership_id=world.marcus.member.membership_id,
            delegate_membership_id=delegate_member.membership_id,
            valid_from=clock.now() - timedelta(days=1),
            valid_to=clock.now() + timedelta(days=1),
        )
        values["permissions"] = ["contract.approve"]
        session.execute(insert(approval_delegation).values(**values))
    delegated = approve(app, request_id, delegate)
    assert (delegated.status_code, slug(delegated)) == (403, "self-approval"), delegated.text
    reviewer = colleague(world.place.tenant_id, "independent-policy-reviewer")
    assign(reviewer, "controller")
    independent = enrolled(app, clock, reviewer)
    accepted = approve(app, request_id, independent)
    assert accepted.status_code == 200, accepted.text


def test_supported_override_validation_is_atomic(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    contract_id = booked.contract["id"]
    rate = {"basis": "CUSTOMER_CREDIT_RATE", "annual_rate": "0.06"}
    invalid = [
        _override(contract_id, "balance.right_to_consideration", "UNCONDITIONAL"),
        _override(contract_id, "balance.right_to_consideration", "INVALID", obligation_key="O1"),
        _override(
            contract_id, "balance.right_to_consideration", "UNCONDITIONAL", obligation_key="O9"
        ),
        _override(contract_id, "sfc.discount_rate_basis", rate, obligation_key="O1"),
        _override(contract_id, "sfc.discount_rate_basis", {"basis": "CUSTOMER_CREDIT_RATE"}),
        _override(contract_id, "sfc.discount_rate_basis", {**rate, "annual_rate": "NaN"}),
        _override(contract_id, "sfc.discount_rate_basis", {**rate, "annual_rate": 0.06}),
        _override(contract_id, "sfc.discount_rate_basis", {**rate, "annual_rate": "-12"}),
        _override(
            contract_id,
            "sfc.discount_rate_basis",
            {**rate, "annual_rate": "-1", "compounding": "ANNUAL"},
        ),
        {**_override(contract_id, "sfc.discount_rate_basis", rate), "rationale": "  "},
        _override(contract_id, "sfc.discount_rate_basis", rate, judgement_record_id=str(uuid4())),
    ]
    before = _stored(world.place)
    for body in invalid:
        response = post(app, POLICY_OVERRIDES, world.place.author, body)
        assert response.status_code == 422, response.text
        assert response.json()["errors"], response.text
    assert _stored(world.place) == before


def test_approved_financing_rate_reaches_contract_calculation_input(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    rate = {"basis": "CUSTOMER_CREDIT_RATE", "annual_rate": "0.06", "compounding": "MONTHLY"}
    created = post(
        app,
        POLICY_OVERRIDES,
        world.place.author,
        _override(booked.contract["id"], "sfc.discount_rate_basis", rate),
    )
    assert created.status_code == 201, created.text
    assert (created.json()["level"], created.json()["status"]) == ("CONTRACT", "DRAFT")
    override_id = created.json()["id"]
    submitted = post(app, f"{POLICY_OVERRIDES}/{override_id}/submit", world.place.author, {})
    assert submitted.status_code == 200, submitted.text
    accepted = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert accepted.status_code == 200, accepted.text
    bundle, _, _ = computed(world.place, booked.combination_group["id"])
    for book in bundle.books:
        [found] = [
            p
            for p in book.policies
            if p.code == "sfc.discount_rate_basis" and p.scope == "CONTRACT"
        ]
        assert (found.value, found.level, found.source_ref) == (rate, "C", override_id)


def test_financing_override_changes_real_deferred_payment_calculation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k11_world(
        app,
        keyring,
        clock,
        files,
        chart=(
            *K11_CHART,
            ("7100", "Interest income", "REVENUE", "C", "INTEREST_INCOME"),
        ),
    )
    body = k11_body(world.customer_id)
    body["lines"] = [body["lines"][0]]
    body["lines"][0]["start_date"] = "2026-09-12"
    body["payment_schedule"] = [
        {"date": "2027-10-01", "amount": {"amount": "90000.00", "currency": "EUR"}}
    ]
    booked = booked_contract(world.place, body, activate=False)
    contract_id = booked.contract["id"]

    def rate(annual: str, judgement_id: str | None = None) -> str:
        created = post(
            app,
            POLICY_OVERRIDES,
            world.place.author,
            _override(
                contract_id,
                "sfc.discount_rate_basis",
                {"basis": "CUSTOMER_CREDIT_RATE", "annual_rate": annual, "compounding": "MONTHLY"},
                rationale="Record or correct the inception rate from the contract evidence.",
                **({"judgement_record_id": judgement_id} if judgement_id else {}),
            ),
        )
        assert created.status_code == 201, created.text
        identifier = str(created.json()["id"])
        sent = post(app, f"{POLICY_OVERRIDES}/{identifier}/submit", world.place.author, {})
        assert sent.status_code == 200, sent.text
        approved = approve(app, str(sent.json()["approval_request_id"]), world.marcus)
        assert approved.status_code == 200, approved.text
        return identifier

    rate("0")
    judgement = judgement_submitted(
        app,
        world.place.author,
        {
            "topic": "SFC_ASSESSMENT",
            "subject_type": "contract",
            "subject_id": str(contract_id),
            "conclusion": "The deferred payment includes a significant financing component.",
            "rationale": "Payment follows transfer by more than a year; no exception applies.",
            "questionnaire": {"obligation_key": "", "significant": True, "exception_32_17": "NONE"},
        },
    )
    reviewed = approve(app, str(judgement["approval_request_id"]), world.marcus)
    assert reviewed.status_code == 200, reviewed.text
    activated_contract(world.place, booked, compute=False)
    appended(
        world.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=date(2026, 9, 12),
                payload=DeliveryRecordedV1(obligation_key="O1", quantity="200", trigger="DELIVERY"),
            )
        ],
    )
    _, undiscounted, _ = computed(world.place, booked.combination_group["id"])
    override_id = rate("0.06", str(judgement["id"]))
    bundle, discounted, _ = computed(world.place, booked.combination_group["id"])
    for before, after in zip(undiscounted.books, discounted.books, strict=True):
        assert before.contract_version is not None and after.contract_version is not None
        assert before.contract_version.columns["transaction_price"] == 9_000_000
        assert 0 < after.contract_version.columns["transaction_price"] < 9_000_000
    assert any(p.source_ref == override_id for book in bundle.books for p in book.policies)


def test_period_override_bundle_retains_entity_default_and_framework_force(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    # Authoring remains disabled until the FX layer reader uses the contract scope.
    world = k11_world(app, keyring, clock, files)
    booked = delivered_k11(world)
    code = "fx.cl_historical_layering"
    identifier = drafted_override(
        world.place, booked.contract["id"], code, "DISABLED_REMEASURE_AS_MONETARY"
    )
    sent = post(app, f"{POLICY_OVERRIDES}/{identifier}/submit", world.place.author, {})
    assert sent.status_code == 200, sent.text
    approved = approve(app, str(sent.json()["approval_request_id"]), world.marcus)
    assert approved.status_code == 200, approved.text
    bundle, result, _ = computed(world.place, booked.combination_group["id"])
    for output in result.books:
        assert output.contract_version is not None
        pinned = output.contract_version.columns["pinned_policies"]
        assert pinned[code]["source_id"] != str(identifier)
    for book in bundle.books:
        scoped = [p for p in book.policies if p.code == code and p.scope == "CONTRACT_PERIOD"]
        defaults = [p for p in book.policies if p.code == code and p.scope == "PERIOD"]
        assert defaults and all(p.value == "ENABLED" for p in defaults)
        if book.book_code == "ASC606":
            assert scoped and all(p.source_ref == str(identifier) for p in scoped)
            assert all(p.pin == "P" and p.level == "C" for p in scoped)
        else:
            assert not scoped
    refused = post(
        app,
        POLICY_OVERRIDES,
        world.place.author,
        _override(booked.contract["id"], code, "DISABLED_REMEASURE_AS_MONETARY"),
    )
    assert refused.status_code == 422, refused.text
    assert any(e["rule_id"] == NOT_OFFERED_RULE for e in refused.json()["errors"])
