"""DIN-12 amendment basis — the ACTUAL applied chain (Codex 0444 §1, ACKed by team-lead).

The unit witnesses of ``test_integration_sync_unit.py`` read a fake session over a prebuilt
projection, and ``test_same_id_amendment_basis_is_the_booked_order_not_the_candidate`` reads a
never-computed DRAFT. Neither shows the chain team-lead's ruling on Codex 0339 §1 is about: the
basis is the parent's CURRENT GOVERNED line state — the head projection's ``obligation_version``
rows. This module drives that chain through the REAL commands and routes:

    1. book and ACTIVATE the parent (``booked_contract`` → ``activated_contract``: the activation
       computes and persists the group);
    2. link it to an ACTIVE Salesforce connection as order ``SF-ORD-K02-P`` (``POST /external-ids``,
       04 1.81 API-R-45) so the adapter finds it the way it finds a synced parent;
    3. append a row-less legacy amendment — a legacy-template ``CONTRACT_AMENDED`` with no
       T-CON-06 row (the DIN-6 / L5-1-Q-27 shape): +1 / +20.00 on the one line;
    4. probe: an incoming amendment BEFORE the recompute is refused ``BASIS_STALE`` by name — no
       candidate rows, no draft;
    5. the recompute FAILS CLOSED by name: this world holds the DEFAULT preset, and a legacy
       template is folded on the parity route only — ENGINE_SPEC S06-R-30 fixes its progress basis
       through POL-107 ``LEGACY_BY_TEMPLATE``, the ``LEGACY_PARITY`` value of a policy POLICIES
       §0.6 marks FIX (not configurable; the 606 / IFRS presets hold ``POB_MEASURE``), and the
       legacy upload itself refuses outside POL-100 ``USER_SELECTED_TEMPLATE`` (L5-1-Q-28: "no
       legacy treatment applies outside the parity route"). Nothing is persisted, so the basis
       stays ``BASIS_STALE`` and the adapter still drafts nothing — it never diffs against a
       head the engine could not compute;
    6. on a second parent ``SF-ORD-K02-N`` of the same connection, incoming A0 (3 / 120.00) → the
       adapter's DRAFT modification with CHANGE +1 / +20.00, APPLIED through classify → preview
       (the job) → submit → approve: ``modifications._approved`` appends ``CONTRACT_AMENDED`` and
       recomputes the group (``computation.recompute`` persists) — the basis reads 3 / 120.00
       with no explicit recompute;
    7. incoming A1 (4 / 150.00) → CHANGE +1 / +30.00 against THAT state, not +2 / +50.00 against
       the booking; APPLIED the same way — the basis reads 4 / 150.00;
    8. incoming A2 (5 / 170.00) → CHANGE +1 / +20.00 — not +2 / +50.00 against 3 / 120.00 and
       not +3 / +70.00 against the booking.

World: PRD WLD-K-02 (``support.factories.k02_world`` — AVM-US, customer C-02, AVM-SEAT-MO with a
published template and an approved SSP version), the world the contract command tests activate,
compute and modify in. The amounts follow team-lead's chain (2 / 100 → 3 / 120 → 4 / 150 → 5 / 170)
so that a stale or inception basis produces a different delta at every step.

Lane FIX-A (2026-09-29; first database run): the module was written NOT RUN and chained a legacy
amendment and native amendments on ONE contract of this DEFAULT-preset world, expecting the engine
to fold the legacy template there. No documented policy set folds both on one contract (the native
application fails closed on the parity options, S06-R-06; the template on the default one,
S06-R-30), so step 5 now asserts the documented refusal and the applied chain runs on a second
parent with native amendments. The expectation step 5 had — the head projection CARRYING a
row-less legacy amendment is what the adapter reads — is witnessed where a legacy amendment can
exist, on the parity route: ``test_parity_route_basis_carries_a_row_less_legacy_amendment`` (the
``LEGACY_PARITY`` world of ``support.legacy_replay``, golden step 10 through the real legacy
upload). What no test asserts any more, because no documented policy set computes it: a NATIVE
amendment applied after a LEGACY one on the same contract. A ``LEGACY_PARITY`` tenant cannot
activate a natively booked (synced) parent either — PRODUCT_UNMAPPED under POL-100
``USER_SELECTED_TEMPLATE`` (measured) — so the two halves have no common world.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.crm import salesforce
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_event,
    integration_connection,
    job,
    modification,
    source_order,
)
from erev_api.domain.integrations import ports
from erev_api.domain.integrations import sync as sync_module
from erev_api.enums import ContractEventType, ModificationTreatment, SourceObjectType, SourceSystem
from erev_api.events.payloads import ContractAmendedV1, ModificationLineV1, MoneyIn, SspBasisV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_engine.errors import EngineError
from fastapi import FastAPI
from sqlalchemy import select, text
from support import golden_streams
from support.adapter_secrets import tenant_ref
from support.db import TestDatabase
from support.factories import (
    SEAT_MONTH,
    K02World,
    activated_contract,
    appended,
    booked_contract,
    computed,
    k02_world,
    seat_body,
    seat_line,
)
from support.http import asgi_client
from support.legacy_replay import LegacyWorld, committed, legacy_world, replayed
from support.reference import approve, assign, get, patch, post

INTEGRATIONS = "/api/v1/integrations"
MODIFICATIONS = "/api/v1/modifications"
JOBS = "/api/v1/jobs"
MOCK_BASE = f"{mocks.MOCKS_PREFIX}{sf_mock.PREFIX}"
# The connection's credential reference names a secret of the workspace's own namespace of the
# secret store (``tenant_ref``; 05 KEY-09 rev 1.47). No test of this module reads the secret:
# the run's job is never run (``_connection``).
SECRET_NAME = "sf-client-secret"
PARENT_ORDER = "SF-ORD-K02-P"  # the parent's external id, also its Salesforce order id
LINE = "SF-OI-P-1"  # the one booked line: its Salesforce line id IS the obligation key
NATIVE_ORDER = "SF-ORD-K02-N"  # the second parent: the chain of APPLIED (native) amendments
NATIVE_LINE = "SF-OI-N-1"
# A legacy amendment names a modification key that is NO T-CON-06 row (D-98 140 Q-3).
LEGACY_KEY = uuid5(NAMESPACE_URL, "erev:legacy-amendment:SF-ORD-K02-P:1")
_TASK_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@pytest.fixture
def k02(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
) -> Iterator[K02World]:
    world = k02_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # modification.approve (PRD §2.5)
    assign(world.marcus.member, "integration_admin")  # integration.manage; Marcus is MFA-enrolled
    salesforce.register()
    previous = sync_module._HOOKS.get("http")
    sync_module.register_http_client_factory(lambda base_url: asgi_client(app))
    try:
        yield world
    finally:
        sync_module.register_http_client_factory(previous)


# --- the real commands and routes -----------------------------------------------------------------


def _connection(world: K02World) -> tuple[dict[str, Any], UUID]:
    """An ACTIVE inbound Salesforce connection (POST + PATCH status) and a QUEUED INBOUND_POLL run
    of it (``POST /sync``, 202): the run row the applied objects' ``sync_run_id`` names. Its job is
    never run here — the objects are applied directly through ``apply_object``."""
    body = {
        "code": "sf-avm",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "base_url": MOCK_BASE,
        "config": {"default_performing_entity": "AVM-US"},
        "secret_ref": tenant_ref(world.place.tenant_id, SECRET_NAME),
    }
    created = post(world.app, INTEGRATIONS, world.marcus, body)
    assert created.status_code == 201, created.text
    activated = patch(
        world.app,
        f"{INTEGRATIONS}/{created.json()['id']}",
        world.marcus,
        {"status": "ACTIVE"},
        if_match='"r1"',
    )
    assert activated.status_code == 200, activated.text
    accepted = post(
        world.app,
        f"{INTEGRATIONS}/{created.json()['id']}/sync",
        world.marcus,
        {"kind": "INBOUND_POLL"},
    )
    assert accepted.status_code == 202, accepted.text
    return dict(activated.json()), UUID(accepted.headers["X-Erev-Sync-Run-Id"])


def _parent(world: K02World, *, order: str = PARENT_ORDER, line: str = LINE) -> dict[str, Any]:
    """The parent booked through ``book_contract`` with the Salesforce line id as its obligation
    key (2 / 100.00 over 2026), then ACTIVATED through ``activation.activate`` (computed and
    persisted at activation)."""
    body = seat_body(
        world.customer_id,
        external_id=order,
        inception="2026-01-01",
        lines=[seat_line(line, seats="2", price="100.00", start="2026-01-01", end="2026-12-31")],
    )
    booked = booked_contract(world.place, body, activate=False)
    activated_contract(world.place, booked)
    return _contract(world, UUID(str(booked.contract["id"])))


def _contract(world: K02World, contract_id: UUID) -> dict[str, Any]:
    [row] = world.place.rows(select(contract).where(contract.c.id == contract_id))
    return row


def _link(world: K02World, connection: dict[str, Any], parent: dict[str, Any]) -> None:
    """``POST /external-ids``: the parent IS the Salesforce order of its external id under the
    connection (masterdata.maintain; 04 1.81 API-R-45)."""
    linked = post(
        world.app,
        "/api/v1/external-ids",
        world.place.author,
        {
            "integration_connection_id": connection["id"],
            "object_type": "contract",
            "internal_id": str(parent["id"]),
            "external_id": str(parent["external_id"]),
        },
    )
    assert linked.status_code == 201, linked.text


def _legacy_amendment(world: K02World, parent: dict[str, Any]) -> None:
    """The APPLIED row-less legacy amendment: a legacy-template ``CONTRACT_AMENDED`` appended to the
    stream with NO ``modification`` row (DIN-6 / L5-1-Q-27; ``ContractAmendedV1`` as
    ``imports/legacy_v1/modification.py`` builds it) — CHANGE +1 / +20.00 on the one line."""
    appended(
        world.place,
        UUID(str(parent["id"])),
        int(parent["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.CONTRACT_AMENDED,
                effective_date=date(2026, 6, 1),
                payload=ContractAmendedV1(
                    modification_id=LEGACY_KEY,
                    treatments={LINE: ModificationTreatment.LEGACY_PROSPECTIVE},
                    lines=(
                        ModificationLineV1(
                            obligation_key=LINE,
                            action="CHANGE",
                            quantity_delta="1",
                            consideration_delta=MoneyIn(amount="20.00", currency="USD"),
                        ),
                    ),
                    ssp_basis={LINE: SspBasisV1()},
                ),
                obligation_keys=(LINE,),
            )
        ],
    )


def _basis(world: K02World, contract_id: UUID) -> sync_module.ParentBasis:
    parent = _contract(world, contract_id)
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return sync_module._parent_basis(session, parent)


def _state(found: sync_module.ParentBasis) -> dict[str, tuple[Decimal, Decimal]]:
    return {key: (line["quantity"], line["total_price"]) for key, line in found.lines.items()}


def _amendment(
    external_id: str,
    *,
    quantity: str,
    total: str,
    effective: str,
    parent: str = PARENT_ORDER,
    line: str = LINE,
) -> ports.SourceObject:
    """A Salesforce amendment order of the parent (``Parent_Order__c``), one line on the parent's
    Salesforce line id; no ServiceDate / EndDate (an unsent date is no date change)."""
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version="1",
        version_order=1,
        payload={
            "Id": external_id,
            "OrderNumber": external_id,
            "Status": "Activated",
            "EffectiveDate": effective,
            "AccountId": "C-02",  # resolves to the K-02 customer by code
            "CurrencyIsoCode": "USD",
            "Parent_Order__c": parent,
            "Amendment_Reason__c": "Upsell",
            "OrderItems": {
                "records": [
                    {
                        "Id": line,
                        "ProductCode": SEAT_MONTH,
                        "Quantity": quantity,
                        "TotalPrice": total,
                    }
                ]
            },
        },
    )


def _apply(
    world: K02World,
    runtime: JobRuntime,
    connection: dict[str, Any],
    run_id: UUID,
    obj: ports.SourceObject,
) -> sync_module.Counts:
    """``apply_object`` under the sync principal in one committed unit of work (the SYNC_RUN job's
    step for one object): receive → store → normalise → ingest / route."""
    principal = sync_module.sync_principal(world.place.tenant_id)
    with system_unit_of_work(
        runtime, principal, request_id=f"tests-chain-{obj.external_id}"
    ) as uow:
        [row] = world.place.rows(
            select(integration_connection).where(
                integration_connection.c.id == UUID(connection["id"])
            )
        )
        adapter = sync_module.adapter_for(row, tenant_code="avm", client=asgi_client(world.app))
        counts = sync_module.Counts()
        loaded: list[tuple[str, str, str, Decimal]] = []
        applied = sync_module.apply_object(
            uow,
            adapter,
            row,
            obj,
            notified_versions=("1",),
            sync_run_id=run_id,
            counts=counts,
            loaded=loaded,
        )
        uow.commit()
    assert applied is True, counts.failures
    return counts


def _modifications(world: K02World, contract_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(modification)
        .where(modification.c.contract_id == contract_id)
        .order_by(modification.c.modification_no)
    )


def _work(world: K02World, job_id: UUID, runtime: JobRuntime) -> None:
    """The worker fetches the job's task and runs it."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    run_job(job_id, world.place.tenant_id, attempt=1, runtime=runtime)


def _apply_modification(
    world: K02World, runtime: JobRuntime, clock: FrozenClock, modification_id: str
) -> None:
    """The real CTR-17 chain for the adapter's DRAFT: classify (the preparer confirms the
    provisional kind through the engine's proposal), preview (the job), submit, approve by priya —
    ``modifications._approved`` appends ``CONTRACT_AMENDED`` and recomputes the group."""
    author = world.place.author
    classified = post(world.app, f"{MODIFICATIONS}/{modification_id}/classify", author, {})
    assert classified.status_code == 200, classified.text
    queued = post(world.app, f"{MODIFICATIONS}/{modification_id}/preview", author, {})
    assert queued.status_code == 202, queued.text
    _work(world, UUID(queued.json()["id"]), runtime)
    finished = get(world.app, f"{JOBS}/{queued.json()['id']}", author).json()
    assert finished["state"] == "SUCCEEDED", finished
    sent = post(
        world.app,
        f"{MODIFICATIONS}/{modification_id}/submit",
        author,
        {"comment": "Approve the Salesforce amendment."},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED", sent.text
    clock.advance(timedelta(minutes=1))
    decided = approve(world.app, str(sent.json()["approval_request_id"]), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text


def _change(row: dict[str, Any]) -> tuple[str, str, Decimal, Decimal]:
    [line] = row["lines"]
    return (
        str(line["obligation_key"]),
        str(line["action"]),
        Decimal(str(line["quantity_delta"])),
        Decimal(str(line["consideration_delta"]["amount"])),
    )


# --- the witness ----------------------------------------------------------------------------------


def test_applied_chain_basis_follows_legacy_then_native_amendments(
    k02: K02World, runtime: JobRuntime, clock: FrozenClock
) -> None:
    """ACTIVE parent → row-less legacy amendment → the stale guard holds while the head cannot be
    computed (the legacy template is folded on the parity route only); ACTIVE parent → successive
    APPLIED amendments: the basis read by the adapter is the head projection at every step."""
    connection, run_id = _connection(k02)
    parent = _parent(k02)
    parent_id = UUID(str(parent["id"]))
    group_id = UUID(str(parent["combination_group_id"]))
    assert parent["status"] == "ACTIVE" and parent["latest_computation_id"] is not None
    assert int(parent["head_stream_version"]) == 2  # CONTRACT_BOOKED, CONTRACT_ACTIVATED
    _link(k02, connection, parent)
    inception = _basis(k02, parent_id)
    assert inception.refused is None and inception.unkeyed == ()
    assert _state(inception) == {LINE: (Decimal("2"), Decimal("100.00"))}

    # 3. the row-less legacy amendment (+1 / +20.00): head 3, no modification row
    _legacy_amendment(k02, parent)
    amended = _contract(k02, parent_id)
    assert int(amended["head_stream_version"]) == 3
    assert _modifications(k02, parent_id) == []  # row-less: the event alone carries it
    [dirty] = k02.place.rows(
        select(combination_group.c.dirty_since).where(combination_group.c.id == group_id)
    )
    assert (
        dirty["dirty_since"] is not None
        or amended["latest_computation_id"] == parent["latest_computation_id"]
    )

    # 4. the probe BEFORE the recompute: refused BASIS_STALE by name, no candidate rows, no draft
    probe = _apply(
        k02,
        runtime,
        connection,
        run_id,
        _amendment(f"{PARENT_ORDER}-A0", quantity="4", total="150.00", effective="2026-07-01"),
    )
    [refusal] = probe.failures
    assert refusal["step"] == "amendment" and refusal["rule_id"] == "BASIS_STALE"
    assert refusal["error"].startswith("The parent contract's latest computation does not cover")
    # F-ADM-ROUTE-DETAIL-1: the record names the REFUSED amendment; the parent's id and the heads
    # travel nested under ``detail`` — each id in its own place.
    assert refusal["external_id"] == f"{PARENT_ORDER}-A0" and refusal["external_version"] == "1"
    assert refusal["detail"]["external_id"] == PARENT_ORDER
    assert refusal["detail"]["stream_head"] == 3 and refusal["detail"]["computed_head"] in (2, None)
    assert probe.candidates == 0 and probe.modifications_drafted == 0
    assert (
        k02.place.rows(
            select(source_order).where(source_order.c.external_order_id == f"{PARENT_ORDER}-A0")
        )
        == []
    )
    assert _modifications(k02, parent_id) == []

    # 5. the recompute fails closed by name: outside the parity route no legacy template is
    # folded (ENGINE_SPEC S06-R-30; POLICIES POL-107 — DEFAULT presets hold POB_MEASURE)
    with pytest.raises(EngineError) as unfolded:
        computed(k02.place, group_id)
    assert unfolded.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert (
        unfolded.value.detail["rule"],
        unfolded.value.detail["policy"],
        unfolded.value.detail["option"],
    ) == ("S06-R-30", "mod.catch_up_progress_basis", "POB_MEASURE")
    held = _contract(k02, parent_id)
    assert held["latest_computation_id"] == parent["latest_computation_id"]  # nothing persisted
    stale = _basis(k02, parent_id)
    assert stale.refused == "BASIS_STALE" and _state(stale) == {}
    again = _apply(
        k02,
        runtime,
        connection,
        run_id,
        _amendment(f"{PARENT_ORDER}-A1", quantity="4", total="150.00", effective="2026-08-01"),
    )
    [still] = again.failures
    assert (still["step"], still["rule_id"]) == ("amendment", "BASIS_STALE")
    assert still["detail"]["stream_head"] == 3 and still["detail"]["computed_head"] in (2, None)
    assert again.candidates == 0 and again.modifications_drafted == 0
    assert _modifications(k02, parent_id) == []  # never diffed against the head it cannot read

    # 6. the APPLIED chain on a second parent: incoming A0 (3 / 120.00) → CHANGE +1 / +20.00
    native = _parent(k02, order=NATIVE_ORDER, line=NATIVE_LINE)
    native_id = UUID(str(native["id"]))
    assert native["status"] == "ACTIVE" and int(native["head_stream_version"]) == 2
    _link(k02, connection, native)
    assert _state(_basis(k02, native_id)) == {NATIVE_LINE: (Decimal("2"), Decimal("100.00"))}

    def incoming(name: str, quantity: str, total: str, effective: str) -> sync_module.Counts:
        return _apply(
            k02,
            runtime,
            connection,
            run_id,
            _amendment(
                f"{NATIVE_ORDER}-{name}",
                quantity=quantity,
                total=total,
                effective=effective,
                parent=NATIVE_ORDER,
                line=NATIVE_LINE,
            ),
        )

    zeroth = incoming("A0", "3", "120.00", "2026-06-01")
    assert zeroth.failures == [] and zeroth.candidates == 1 and zeroth.modifications_drafted == 1
    [draft_a0] = _modifications(k02, native_id)
    assert _change(draft_a0) == (NATIVE_LINE, "CHANGE", Decimal("1"), Decimal("20.00"))
    _apply_modification(k02, runtime, clock, str(draft_a0["id"]))
    after_a0 = _basis(k02, native_id)  # no explicit recompute: the approval persisted one
    assert after_a0.refused is None, after_a0.detail
    assert _state(after_a0) == {NATIVE_LINE: (Decimal("3"), Decimal("120.00"))}
    computed_a0 = _contract(k02, native_id)
    assert computed_a0["latest_computation_id"] != native["latest_computation_id"]

    # 7. incoming A1 (4 / 150.00): the adapter's DRAFT modification diffs the head projection
    first = incoming("A1", "4", "150.00", "2026-08-01")
    assert first.failures == [] and first.candidates == 1 and first.modifications_drafted == 1
    [_, draft_a1] = _modifications(k02, native_id)
    assert draft_a1["status"] == "DRAFT" and draft_a1["reference"] == f"{NATIVE_ORDER}-A1:1"
    assert draft_a1["questionnaire"]["kind_provisional"] is True
    assert draft_a1["questionnaire"]["parent_order_external_id"] == NATIVE_ORDER
    assert _change(draft_a1) == (
        NATIVE_LINE,
        "CHANGE",
        Decimal("1"),
        Decimal("30.00"),
    )  # not +2 / +50

    # A1 APPLIED through the real chain; the approval's recompute is the new head
    _apply_modification(k02, runtime, clock, str(draft_a1["id"]))
    [_, applied_a1] = _modifications(k02, native_id)
    assert applied_a1["status"] == "APPLIED" and applied_a1["applied_event_id"] is not None
    events = k02.place.rows(
        select(contract_event.c.event_type)
        .where(contract_event.c.contract_id == native_id)
        .order_by(contract_event.c.stream_version)
    )
    assert [event["event_type"] for event in events] == [
        "CONTRACT_BOOKED",
        "CONTRACT_ACTIVATED",
        "CONTRACT_AMENDED",  # A0, naming its T-CON-06 row
        "CONTRACT_AMENDED",  # A1, naming its T-CON-06 row
    ]
    applied = _contract(k02, native_id)
    assert int(applied["head_stream_version"]) == 4
    assert applied["latest_computation_id"] != computed_a0["latest_computation_id"]
    after_a1 = _basis(k02, native_id)  # no explicit recompute: the approval persisted one
    assert after_a1.refused is None, after_a1.detail
    assert _state(after_a1) == {NATIVE_LINE: (Decimal("4"), Decimal("150.00"))}

    # 8. the next incoming amendment (5 / 170.00) diffs against THAT state: +1 / +20.00
    second = incoming("A2", "5", "170.00", "2026-09-01")
    assert second.failures == [] and second.modifications_drafted == 1
    [_, _, draft_a2] = _modifications(k02, native_id)
    assert draft_a2["status"] == "DRAFT" and draft_a2["reference"] == f"{NATIVE_ORDER}-A2:1"
    assert _change(draft_a2) == (NATIVE_LINE, "CHANGE", Decimal("1"), Decimal("20.00"))
    # neither +2 / +50.00 (the 3 / 120.00 state) nor +3 / +70.00 (the booking) — the basis moved
    # with every applied amendment.


@pytest.fixture
def legacy(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> LegacyWorld:
    return legacy_world(app, keyring, clock, files)


def _legacy_contract(world: LegacyWorld, name: str) -> dict[str, Any]:
    (found,) = world.imports.rows(select(contract).where(contract.c.external_id == name))
    return found


def _legacy_basis(world: LegacyWorld, parent: dict[str, Any]) -> sync_module.ParentBasis:
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return sync_module._parent_basis(session, parent)


def test_parity_route_basis_carries_a_row_less_legacy_amendment(legacy: LegacyWorld) -> None:
    """The legacy half of team-lead's ruling on Codex 0339 §1, on the ONLY route a legacy amendment
    exists (ENGINE_SPEC S06-R-30; POL-100 / POL-107 ``LEGACY_PARITY``): the ``LEGACY_PARITY`` world
    replays golden steps 01 to 09, then step 10 — the legacy contract-modification upload in mode
    ``prospective`` — appends a ROW-LESS ``CONTRACT_AMENDED`` to ``Contract 1`` (treatments
    ``LEGACY_PROSPECTIVE``; line ``POB #1`` CHANGE −5 / −500.00; no T-CON-06 row: DIN-6 /
    L5-1-Q-27) under the import approval, whose commit recomputes the group. The adapter's basis
    (``sync._parent_basis``) reads the head projection at both points: 5 / 500.00 before, and
    0 / 0.00 after — the stated price after modifications, not the booking's 5 / 500.00 — with
    the untouched lines unchanged. In the first test this expectation read "3 / 120.00 after the
    legacy +1 / +20.00" on a DEFAULT-preset contract, where the engine refuses the template."""
    replayed(legacy, "09")
    before = _legacy_contract(legacy, "Contract 1")
    assert before["status"] == "ACTIVE" and before["latest_computation_id"] is not None
    head_before = int(before["head_stream_version"])
    inception = _legacy_basis(legacy, before)
    assert inception.refused is None and inception.unkeyed == ()
    assert _state(inception)["POB #1"] == (Decimal("5"), Decimal("500.00"))

    (step,) = [item for item in golden_streams.steps("10") if item.number == "10"]
    assert (step.template_code, step.mode) == ("legacy_contract_modification", "prospective")
    assert step.date_input is not None
    done = committed(
        legacy,
        step.workbook.name,
        step.workbook.read_bytes(),
        step.template_code,
        {"effective_date": step.date_input.isoformat(), "mode": step.mode},
    )
    amended = _legacy_contract(legacy, "Contract 1")
    assert int(amended["head_stream_version"]) == head_before + 1
    (event,) = legacy.imports.rows(
        select(contract_event).where(
            contract_event.c.import_upload_id == UUID(done["id"]),
            contract_event.c.event_type == "CONTRACT_AMENDED",
        )
    )
    assert event["contract_id"] == amended["id"]
    assert event["payload"]["treatments"]["POB #1"] == "LEGACY_PROSPECTIVE"
    (line,) = event["payload"]["lines"]
    assert (
        line["obligation_key"],
        line["action"],
        line["quantity_delta"],
        Decimal(line["consideration_delta"]["amount"]),
    ) == ("POB #1", "CHANGE", "-5", Decimal("-500"))
    assert (
        legacy.imports.rows(select(modification).where(modification.c.contract_id == amended["id"]))
        == []
    )  # row-less: the event alone carries the amendment

    # the import's commit computed the head: the basis is the projection CARRYING the amendment
    assert amended["latest_computation_id"] != before["latest_computation_id"]
    after = _legacy_basis(legacy, amended)
    assert after.refused is None, after.detail
    assert after.unkeyed == ()
    assert _state(after)["POB #1"] == (Decimal("0"), Decimal("0.00"))  # 5 − 5 / 500.00 − 500.00
    untouched = ("POB #2", "POB #3", "POB #4")
    assert {key: _state(after)[key] for key in untouched} == {
        key: _state(inception)[key] for key in untouched
    }
    assert _state(after)["POB #2"] == (Decimal("2"), Decimal("400.00"))
