"""The channel refund bound is the engine's cover rule (D-98 103; 05 §3.9; 04 §16.3
``CREDIT_MEMO_RECORDED`` note). ``check_bounds`` — behind the API append, the preview and the
CSV v2 import — is exercised here directly on the K-11 world for the parity VC scope (Codex
BOUND-R2; the engine's ``test_s01_vc_line_credit`` Contract 4 shape: a signed VC-stratified
booking line, non-VC billing, a VC credit with zero VC billing) with and without the effective
``LEGACY_PARITY`` preset. The pending events carry the billing, so the DRAFT booking is the whole
stored stream.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.contracts import repo
from erev_api.enums import ContractEventType, RegistryCategory, RegistryScope
from erev_api.events.payloads import BillingRecordedV1, CreditMemoRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.registry import presets
from fastapi import FastAPI
from support.db import TestDatabase
from support.factories import K11World, booked_contract, k11_body, k11_world
from support.rows import publish_registry_version

REFUSED = ["REFUND_EXCEEDS_BILLED"]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def k11(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    return k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _publish_parity(world: K11World) -> None:
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=world.place.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            values=presets.legacy_parity_values(scope=RegistryScope.TENANT, book_code=None),
            preset_code=presets.LEGACY_PARITY,
        )


def _contract_4_shape(world: K11World, external_id: str) -> UUID:
    body: dict[str, Any] = {**k11_body(world.customer_id), "external_id": external_id}
    body["lines"] = [
        *body["lines"],
        {
            "obligation_key": "VC1",
            "product_code": "AVM-SUP-12",
            "stratification": "VC",
            "quantity": "1",
            "total_price": {"amount": "-200.00", "currency": "EUR"},
        },
    ]
    booked = booked_contract(world.place, body, activate=False)
    return UUID(str(booked.contract["id"]))


def _billing(key: str | None, amount: str) -> EventIn:
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 9, 5),
        payload=BillingRecordedV1(
            invoice_number=f"INV-{key or 'X'}-{amount}",
            line_external_id="1",
            obligation_key=key,
            amount=MoneyIn(amount=amount, currency="EUR"),
            issue_date=date(2026, 9, 5),
        ),
        obligation_keys=() if key is None else (key,),
    )


def _credit(key: str | None, amount: str) -> EventIn:
    return EventIn(
        event_type=ContractEventType.CREDIT_MEMO_RECORDED,
        effective_date=date(2026, 9, 12),
        payload=CreditMemoRecordedV1(
            credit_memo_number=f"CM-{key or 'X'}-{amount}",
            obligation_key=key,
            amount=MoneyIn(amount=amount, currency="EUR"),
            issue_date=date(2026, 9, 12),
        ),
        obligation_keys=() if key is None else (key,),
    )


def _refusals(world: K11World, contract_id: UUID, events: list[EventIn]) -> list[str]:
    with world.place.uow() as uow:
        current = repo.get_contract(uow.session, contract_id)
        try:
            contract_events.check_bounds(uow.session, current, events, known_at=uow.now)
        except Problem as problem:
            return [str(error.rule_id) for error in problem.errors]
    return []


def test_d98_103_parity_vc_credit_is_out_of_scope_and_stream_excludes_vc(k11: K11World) -> None:
    """Under the effective ``LEGACY_PARITY`` preset (Codex BOUND-R2; the engine's
    ``test_s01_r16_vc_line_credit_is_not_checked``): 200.00 billed on O1, nothing on VC1 — a
    100.00 credit on VC1 passes unchecked; an unreferenced 200.00 credit passes because the stream
    holds the non-VC 200.00 only (the VC credit stays out of it) and 200.01 is refused; a non-VC
    credit above its cover is still refused."""
    _publish_parity(k11)
    contract_id = _contract_4_shape(k11, "NS-SO-DE-5013")
    billed = [_billing("O1", "200.00"), _credit("VC1", "100.00")]
    assert _refusals(k11, contract_id, billed) == []
    assert _refusals(k11, contract_id, [*billed, _credit(None, "200.00")]) == []
    assert _refusals(k11, contract_id, [*billed, _credit(None, "200.01")]) == REFUSED
    assert _refusals(k11, contract_id, [*billed, _credit("O1", "200.01")]) == REFUSED


def test_d98_103_referenced_cover_is_drawn_in_stream_order(k11: K11World) -> None:
    """D-87 L6-5-Q-15 as the engine's ``test_l7_5_referenced_credit_*`` state it: referenced
    billing first, then the unreferenced remainder (80.00 + 20.00 covers 100.00, not 100.01); a
    second obligation may draw only on the cover the first left (300.00 unreferenced, 200.00 drawn
    by O1, so O2 is covered for 100.00 and refused for 100.01)."""
    contract_id = _contract_4_shape(k11, "NS-SO-DE-5015")
    split = [_billing("O1", "80.00"), _billing(None, "20.00")]
    assert _refusals(k11, contract_id, [*split, _credit("O1", "100.00")]) == []
    assert _refusals(k11, contract_id, [*split, _credit("O1", "100.01")]) == REFUSED
    shared = [_billing(None, "300.00"), _credit("O1", "200.00")]
    assert _refusals(k11, contract_id, [*shared, _credit("O2", "100.00")]) == []
    assert _refusals(k11, contract_id, [*shared, _credit("O2", "100.01")]) == REFUSED


def test_d98_103_vc_stratification_outside_the_parity_preset_is_checked(k11: K11World) -> None:
    """Outside ``LEGACY_PARITY`` no VC exception exists (S03-R-18 gives stratification VC the
    parity template only; the engine's
    ``test_s01_r16_vc_stratification_outside_the_parity_preset_is_checked``): the same 100.00
    credit on VC1 with nothing billed there is refused, and the VC line's billing counts in the
    stream an unreferenced credit draws on."""
    contract_id = _contract_4_shape(k11, "NS-SO-DE-5014")
    billed = [_billing("O1", "200.00")]
    assert _refusals(k11, contract_id, [*billed, _credit("VC1", "100.00")]) == REFUSED
    vc_billed = [*billed, _billing("VC1", "50.00")]
    assert _refusals(k11, contract_id, [*vc_billed, _credit(None, "250.00")]) == []
    assert _refusals(k11, contract_id, [*vc_billed, _credit(None, "250.01")]) == REFUSED
