"""The platform runner after BUILD_SPEC CTR-6 (supervisor ruling of 2026-10-01 on lane SECFIX-CLO's
addendum; 04 §16.3 "Manual events"; PRD BR-REC-01, ACT-10; dev-guide DG-AK-41).

The product no longer appends a delivery, progress, milestone, usage, cost or return event that
a signed-in person records: the request waits for another user's approval. So a timeline event the
key does not mark manual — every recorded event of the five platform keys — is what the key says
it is, an integrated source's event, and is sent by an API client of the world
(``ak-integration``), which the product appends directly with ``is_manual`` false. An item marked
manual is the preparer's request and takes the approver's decision, which appends it. No database:
plans, conversions and principals, with fakes.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES, Grants
from erev_api.domain.contracts import events as contract_events
from erev_api.enums import PrincipalKind
from support.answer_keys.database_platform import LedgerPrincipals
from support.answer_keys.db_personas import integration_principal, principal_map
from support.answer_keys.loader import LoadedKey
from support.answer_keys.models import EventItem
from support.answer_keys.platform_plan import (
    APPROVER,
    INTEGRATION,
    INTEGRATION_SCOPES,
    MANUAL_EVENT_TYPES,
    OPERATOR,
    PLATFORM_KEY_IDS,
    PREPARER,
    STEP1_EVENT,
    STEP1_HANDLE,
    SYSTEM,
    H,
    Step,
    load_platform_key,
    plan,
    waits_for_approval,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import (
    EVIDENCE_GAP,
    ROLE_CODES,
    SCHEMA_GAPS,
    MockResolver,
    adapt,
    bind_check,
)
from support.answer_keys.step_permissions import check, required_permissions
from support.answer_keys.workspace_adapter import (
    ROUTE_APPROVAL,
    ROUTE_DIRECT,
    Call,
    LedgerEntry,
    WorkspaceAdapter,
    _principal_for,
)

POS_012 = PLATFORM_KEY_IDS[0]
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/ctr-6/tenant")
CLIENT = uuid5(NAMESPACE_URL, "erev://answer-keys/ctr-6/client")
NOW = datetime(2026, 1, 2, 17, tzinfo=UTC)


def _marked_manual(loaded: LoadedKey, seq: int) -> LoadedKey:
    """``loaded`` with timeline item ``seq`` marked manual — a key no corpus file states (0 of 254
    mark an item manual), built here to witness the road such an item takes."""
    timeline = [
        item.model_copy(update={"is_manual": True}) if item.seq == seq else item
        for item in loaded.key.timeline
    ]
    return replace(loaded, key=loaded.key.model_copy(update={"timeline": timeline}))


def _seq_of(loaded: LoadedKey, event_type: str) -> int:
    return next(
        item.seq
        for item in loaded.key.timeline
        if isinstance(item, EventItem)
        and item.event_type == event_type
        and item.expect_problem is None
    )


def test_ctr_6_every_recorded_event_of_the_five_keys_is_the_api_clients() -> None:
    """No item of the five keys is marked manual, so every ``record_events`` step of a key's
    timeline is the world's API client's: the PERSONAS phase creates it through the product's
    command with exactly the scopes its steps need, the operator holds the grant to create it,
    and each recorded step captures ``known_at`` at its own commit (the append is direct). The
    one event a person records is the runner's own Step 1 assessment before an activation
    (DG-AK-41 layer 4), which is none of the types that wait for a second person."""
    assert MANUAL_EVENT_TYPES == {member.value for member in contract_events.MANUAL_TYPES}
    recorded_types: set[str] = set()
    for key_id in PLATFORM_KEY_IDS:
        loaded = load_platform_key(key_id)
        steps = plan(loaded).steps
        (client,) = [step for step in steps if step.handler == H["api_client"]]
        assert (client.phase, client.actor, client.subject, dict(client.detail)) == (
            "PERSONAS",
            OPERATOR,
            INTEGRATION,
            {"scopes": "contract.read,event.record"},
        ), key_id
        events = {item.seq: item for item in loaded.key.timeline if isinstance(item, EventItem)}
        assert not any(item.is_manual for item in events.values()), key_id
        appends = [step for step in steps if step.handler == H["record_events"]]
        recorded = [step for step in appends if step.phase == "TIMELINE"]
        assert recorded and {step.actor for step in recorded} == {INTEGRATION}, key_id
        assessed = [step for step in appends if step.phase != "TIMELINE"]
        assert {(step.phase, step.actor, step.detail.get("step1")) for step in assessed} == {
            ("CONTRACTS", PREPARER, STEP1_HANDLE)
        }, key_id
        assert all(
            step.captures_known_at == (events[step.seq or -1].expect_problem is None)
            for step in recorded
        ), key_id
        recorded_types |= {events[step.seq or -1].event_type for step in recorded}
        # nothing of the timeline waits for a decision on an event: the decisions left are the
        # activations', the estimate changes' and the commands'
        assert not any(waits_for_approval(item) for item in events.values()), key_id
        for step in recorded:
            call = Call(step.handler, step.actor, {}, step)
            assert required_permissions(call, []) <= frozenset(INTEGRATION_SCOPES), key_id
    # the keys do record manual event types — which is why a persona can no longer send them; a
    # usage report is one of them since 04 rev 1.238 (item EVT-USAGE-MANUAL-1)
    assert recorded_types & MANUAL_EVENT_TYPES == {
        "DELIVERY_RECORDED",
        "PROGRESS_RECORDED",
        "USAGE_REPORTED",
    }
    assert STEP1_EVENT not in MANUAL_EVENT_TYPES  # a person's assessment is appended directly
    assert INTEGRATION not in ROLE_CODES  # a client holds scopes, never a role
    assert "api_client.manage" in DEFAULT_ROLES[ROLE_CODES[OPERATOR][0]]
    assert "event.record" in INTEGRATION_SCOPES


def test_ctr_6_an_item_marked_manual_is_the_preparers_request_and_the_approvers_decision() -> None:
    """A delivery marked manual: the preparer's ``record_events`` appends nothing and captures no
    ``known_at``; the approver's decision appends it and captures it; the computation follows.
    A billing marked manual is still appended directly (its E-03 approval is none): the preparer
    sends it and no decision is planned. One ``known_at`` per item either way."""
    loaded = load_platform_key(POS_012)
    delivery, billing = _seq_of(loaded, "DELIVERY_RECORDED"), _seq_of(loaded, "BILLING_RECORDED")
    before = plan(loaded)

    manual = _marked_manual(loaded, delivery)
    steps = [
        step for step in plan(manual).steps if step.phase == "TIMELINE" and step.seq == delivery
    ]
    assert [
        (step.actor, step.handler.rsplit(".", 1)[1], step.captures_known_at) for step in steps
    ] == [
        (PREPARER, "record_events", False),
        (APPROVER, "decide", True),
        (SYSTEM, "compute_group", False),
    ]
    assert steps[0].detail["is_manual"] == "true"
    assert plan(manual).known_at_captures == before.known_at_captures
    adapter = WorkspaceAdapter(manual)
    call = adapter.plan_call(steps[0])
    assert call is not None and (call.actor, call.kwargs["route"]) == (PREPARER, ROUTE_APPROVAL)
    # the same step of the key as it stands: the client's, direct
    direct = WorkspaceAdapter(loaded).plan_call(
        next(
            step
            for step in before.steps
            if step.handler == H["record_events"] and step.seq == delivery
        )
    )
    assert direct is not None and (direct.actor, direct.kwargs["route"]) == (
        INTEGRATION,
        ROUTE_DIRECT,
    )

    billed = _marked_manual(loaded, billing)
    steps = [
        step for step in plan(billed).steps if step.phase == "TIMELINE" and step.seq == billing
    ]
    assert [
        (step.actor, step.handler.rsplit(".", 1)[1], step.captures_known_at) for step in steps
    ] == [(PREPARER, "record_events", True), (SYSTEM, "compute_group", False)]
    call = WorkspaceAdapter(billed).plan_call(steps[0])
    assert call is not None and call.kwargs["route"] == ROUTE_DIRECT


def test_ctr_6_a_person_mapped_as_the_integration_is_refused_by_name() -> None:
    """Rule ACT-1 for the client: the principal mapped for ``ak-integration`` is an API client —
    a person's principal there would turn every recorded event into a request that waits. ACT-2
    then holds the client to its scopes like any other actor."""
    loaded = load_platform_key(POS_012)
    step = next(  # a key item's append; the runner's assessment before it is the preparer's
        step
        for step in plan(loaded).steps
        if step.handler == H["record_events"] and step.phase == "TIMELINE"
    )
    call = WorkspaceAdapter(loaded).plan_call(step)
    assert call is not None and call.actor == INTEGRATION
    maya = SimpleNamespace(
        user_id=uuid5(TENANT, "maya"), tenant_id=TENANT, membership_id=uuid5(TENANT, "maya-m")
    )
    marcus = SimpleNamespace(
        user_id=uuid5(TENANT, "marcus"), tenant_id=TENANT, membership_id=uuid5(TENANT, "marcus-m")
    )
    without = principal_map(maya, marcus, verified_at=NOW)
    assert INTEGRATION not in without
    with pytest.raises(NotProvisioned, match="no principal mapped for actor 'ak-integration'"):
        _principal_for(call, without)
    person = {**without, INTEGRATION: without[PREPARER]}
    with pytest.raises(NotProvisioned, match="'ak-integration' is not an API client"):
        _principal_for(call, person)

    principals = principal_map(maya, marcus, integration=CLIENT, verified_at=NOW)
    client = _principal_for(call, principals)
    assert client is principals[INTEGRATION] and client == integration_principal(TENANT, CLIENT)
    assert (client.kind, client.id, client.tenant_id, client.membership_id, client.roles) == (
        PrincipalKind.API_CLIENT,
        CLIENT,
        TENANT,
        None,
        (),
    )
    assert client.permissions == frozenset(INTEGRATION_SCOPES) and client.mfa_verified_at is None
    check(call, client, [])  # holds `event.record`
    narrowed = replace(client, permissions=frozenset({"contract.read"}))
    with pytest.raises(NotProvisioned, match="'ak-integration' lacks permission event.record"):
        check(call, narrowed, [])


def test_ctr_6_the_database_platform_reads_the_api_client_from_the_committed_ledger() -> None:
    """Like a persona, the client exists for the runner only once its creating step committed:
    ``LedgerPrincipals`` names it from the committed ``create_api_client`` result with the grants
    the API gives a token of its scopes — never a default, and absent without the reader."""

    def entry(handler: str, subject: str, result: object) -> LedgerEntry:
        call = Call(handler, OPERATOR, {}, Step("PERSONAS", OPERATOR, handler, subject))
        return LedgerEntry(call, OPERATOR, None, None, None, result)

    asked: list[tuple[UUID, tuple[str, ...]]] = []

    def client_grants_of(client_id: UUID, scopes: object) -> Grants:
        held = tuple(str(code) for code in scopes)  # type: ignore[attr-defined]
        asked.append((client_id, held))
        return Grants((), frozenset(held), {code: "*" for code in held}, "*")

    def never(_: UUID) -> Grants:
        raise AssertionError("no membership is read for the client")

    ledger: list[LedgerEntry] = []
    principals = LedgerPrincipals(
        ledger,
        grants_of=never,
        user_of=lambda _: (TENANT, "unused"),
        now=lambda: NOW,
        client_grants_of=client_grants_of,
    )
    assert INTEGRATION not in set(principals)
    ledger.append(
        entry(
            H["provision"],
            "tenant",
            SimpleNamespace(tenant={"id": TENANT}, admin_membership_id=None),
        )
    )
    with pytest.raises(KeyError):
        principals[INTEGRATION]
    created = SimpleNamespace(
        client={"id": CLIENT, "name": INTEGRATION, "scopes": list(INTEGRATION_SCOPES)},
        client_secret="shown-once",
    )
    ledger.append(entry(H["api_client"], INTEGRATION, created))
    assert INTEGRATION in set(principals) and len(principals) == 1
    client = principals[INTEGRATION]
    assert (client.kind, client.id, client.tenant_id, client.display_name) == (
        PrincipalKind.API_CLIENT,
        CLIENT,
        TENANT,
        INTEGRATION,
    )
    assert client.permissions == frozenset(INTEGRATION_SCOPES) and client.roles == ()
    assert client.membership_id is None and client.mfa_verified_at is None
    assert asked == [(CLIENT, INTEGRATION_SCOPES)]
    # without the reader of the client's grants the client is absent, never defaulted
    blind = LedgerPrincipals(
        ledger, grants_of=never, user_of=lambda _: (TENANT, "unused"), now=lambda: NOW
    )
    assert INTEGRATION not in set(blind)
    with pytest.raises(KeyError):
        blind[INTEGRATION]


def test_ctr_6_the_conversions_of_the_client_and_of_a_manual_item() -> None:
    """``adapt``: the client's creation binds to ``create_api_client``; an integration's event and
    a manual delivery convert to the route's body; a manual progress event is refused by name —
    the product asks an evidence file of it (REQ-DAT-014) and the key schema states none. The gap
    is the item's, not the handler's: ``SCHEMA_GAPS`` keeps its three handlers."""
    loaded = load_platform_key(POS_012)
    resolver = MockResolver(POS_012)
    steps = plan(loaded).steps
    adapter = WorkspaceAdapter(loaded)
    created = adapter.plan_call(next(step for step in steps if step.handler == H["api_client"]))
    assert created is not None and created.actor == OPERATOR
    kwargs = adapt(created, loaded.key, resolver)
    assert kwargs == [
        {"name": INTEGRATION, "scopes": list(INTEGRATION_SCOPES), "auto_approval": True}
    ]
    bind_check(created, kwargs)

    assert H["record_events"] not in SCHEMA_GAPS and len(SCHEMA_GAPS) == 3
    for event_type, refused in (("DELIVERY_RECORDED", False), ("PROGRESS_RECORDED", True)):
        seq = _seq_of(loaded, event_type)
        for marked in (loaded, _marked_manual(loaded, seq)):
            step = next(
                step
                for step in plan(marked).steps
                if step.handler == H["record_events"] and step.seq == seq
            )
            call = WorkspaceAdapter(marked).plan_call(step)
            assert call is not None
            if refused and marked is not loaded:
                with pytest.raises(NotProvisioned) as caught:
                    adapt(call, marked.key, resolver)
                assert EVIDENCE_GAP in str(caught.value) and "rule FOLL-3" in str(caught.value)
                continue
            converted = adapt(call, marked.key, resolver)
            bind_check(call, converted)
            assert [item.event_type.value for item in converted[0]["body"].events] == [event_type]
