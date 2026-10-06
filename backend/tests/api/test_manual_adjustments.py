"""API-R-37 Manual adjustments: the request contract (04 §15.3 API-R-37, §16.14 "API-R-37 shapes",
API-C-06; PRD §5.5 ERR-35; BUILD_SPEC CLO-12).

The commands, their approvals and their accounting are witnessed in
``tests/domain/journals/test_adjustments.py``; this module pins what the route refuses before any
command runs. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.main import create_app
from fastapi import FastAPI
from support.db import TestDatabase
from support.principals import member
from support.reference import fields, get, holding, post, slug

ADJUSTMENTS: Final = "/api/v1/manual-adjustments"
CONTRACT: Final = str(UUID(int=7))
OBLIGATION: Final = str(UUID(int=8))
PERIOD: Final = str(UUID(int=9))
ACCOUNT: Final = str(UUID(int=10))
RULE: Final = "API-C-06"
MONEY_MESSAGE: Final = 'Send money amounts as decimal strings, for example "1250.00".'


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _body(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": kind,
        "contract_id": CONTRACT,
        "effective_date": "2026-09-12",
        "reason_code": "DATA_CORRECTION",
        "memo": "Customer accepted phase 2 on 12 Sep 2026",
        "payload": payload,
    }


def _override(amount: object) -> dict[str, Any]:
    periods = [{"period_id": PERIOD, "amount": amount}]
    return _body("SCHEDULE_OVERRIDE", {"obligation_id": OBLIGATION, "periods": periods})


def _line(amount: object) -> dict[str, Any]:
    return {"account_role": "REVENUE", "gl_account_id": ACCOUNT, "amount_txn": amount}


def test_money_as_string_only(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """BUILD_SPEC CLO-12 / 04 API-C-06: money is an API-S-Money object whose amount is a decimal
    string. A JSON number in ``payload.periods[].amount`` returns 422 ``validation-failed`` with
    ``rule_id`` ``API-C-06`` — sent in place of the object or as the object's amount — and so does
    every other money member of a payload; nothing is stored."""
    maya = holding(app, member(keyring, clock), "revenue_accountant")
    usd = {"amount": "2400.00", "currency": "USD"}

    bare = post(app, ADJUSTMENTS, maya, _override(2400.00))
    assert (bare.status_code, slug(bare)) == (422, "validation-failed"), bare.text
    assert fields(bare) == [("payload.periods.0.amount", RULE)]
    assert bare.json()["errors"][0]["message"] == MONEY_MESSAGE
    integer = post(app, ADJUSTMENTS, maya, _override(2400))
    assert (integer.status_code, fields(integer)) == (422, [("payload.periods.0.amount", RULE)])
    inner = post(app, ADJUSTMENTS, maya, _override({"amount": 2400.00, "currency": "USD"}))
    assert (inner.status_code, slug(inner)) == (422, "validation-failed"), inner.text
    assert fields(inner) == [("payload.periods.0.amount.amount", RULE)]

    release = _body("MANUAL_RELEASE", {"obligation_id": OBLIGATION, "amount": 2400.00})
    refused = post(app, ADJUSTMENTS, maya, release)
    assert (refused.status_code, fields(refused)) == (422, [("payload.amount", RULE)])
    ratio = _body("MANUAL_DEFER", {"obligation_id": OBLIGATION, "ratio": 0.5})
    refused = post(app, ADJUSTMENTS, maya, ratio)
    assert (refused.status_code, fields(refused)) == (422, [("payload.ratio", RULE)])
    journal = _body("MANUAL_JOURNAL", {"lines": [_line(usd), _line(-2400.00)]})
    refused = post(app, ADJUSTMENTS, maya, journal)
    assert (refused.status_code, fields(refused)) == (
        422,
        [("payload.lines.1.amount_txn", RULE)],
    )

    listed = get(app, ADJUSTMENTS, maya)
    assert (listed.status_code, listed.json()["items"]) == (200, []), listed.text
