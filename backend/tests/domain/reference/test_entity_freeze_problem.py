"""ERR-MAP-1 (D-98 candidate 141; 04 §15.2 rev 1.71; DG-KRN-ERR-02 rev 1.61): DB-05
``tg_legal_entity__frozen`` (CTR-3 migration 0040 ``ENTITY_FROZEN_BODY``) refuses a change of
``functional_currency`` / ``time_zone`` once a subledger line of the entity exists — P0001
"EREV-REF-001: functional_currency and time_zone of entity <code> of erev.legal_entity are frozen: a
subledger line of the entity exists". The API answers it BY NAME through ``problems.from_db_error``:
409 ``immutable-record``, ``code`` EREV-REF-001, rule ``ENTITY_FROZEN``, the trigger's message as
the detail — never ``http.unhandled_error`` 500 (F-RPS measured the 500 on
``PATCH /api/v1/entities/{id}`` in integrated batch #6, request
01a0c4ab-de21-7de3-ac5a-f3e4d2274005). Nothing is saved. The route witness was handed over by
F-RPS (drafted in its scratch, never committed) and is authored here by P5, the slice owner.
World: ``support.worlds.k01_pellworth`` — the AVM-US entity carries K01's postings; a report run
makes the prerequisite explicit. DB-bound, NOT RUN on l12.
"""

from __future__ import annotations

from typing import Any, Final

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.reference import ENTITIES, get, patch, put
from support.worlds import ReportWorld, k01_pellworth
from support.worlds import report_run as run_report

AVM_US: Final = "AVM-US"
BALANCES: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": "FY2026-P09"}
TENANT_CURRENCIES: Final = "/api/v1/tenant-currencies"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ReportWorld:
    return k01_pellworth(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _prerequisite(condition: bool, what: str) -> None:
    if not condition:
        raise RuntimeError(f"prerequisite not met (not the binding under test): {what}")


def _frozen_fields(world: ReportWorld) -> dict[str, Any]:
    (row,) = world.place.rows(
        select(
            legal_entity.c.functional_currency, legal_entity.c.time_zone, legal_entity.c.row_version
        ).where(legal_entity.c.id == world.entity_id)
    )
    return dict(row)


@pytest.mark.parametrize(
    ("field", "value"),
    [("time_zone", "Europe/London"), ("functional_currency", "EUR")],
    ids=["time-zone", "functional-currency"],
)
def test_the_entity_time_zone_freeze_refuses_by_name_once_postings_exist(
    world: ReportWorld, field: str, value: str
) -> None:
    """A PATCH changing a frozen attribute of an entity with postings is 409 ``immutable-record``
    with ``code`` EREV-REF-001, rule ``ENTITY_FROZEN`` and a detail naming the entity and the frozen
    fields; the row is unchanged (fields and ``row_version``). Before ERR-MAP-1 the same PATCH was a
    500. The refusing control is the DB-05 trigger, untouched."""
    _, rows = run_report(world, "contract_balances", BALANCES)
    _prerequisite(bool(rows), "a non-empty original (the entity has postings)")
    if field == "functional_currency":
        enabled = put(
            world.app, TENANT_CURRENCIES, world.marcus, {"currency_codes": ["USD", value]}
        )
        _prerequisite(enabled.status_code == 200, f"{value} enabled for the tenant: {enabled.text}")
    shown = get(world.app, f"{ENTITIES}/{world.entity_id}", world.maya)
    _prerequisite(shown.status_code == 200 and "etag" in shown.headers, shown.text)
    _prerequisite(shown.json()[field] != value, f"a different {field} to move to")
    before = _frozen_fields(world)
    changed = patch(
        world.app,
        f"{ENTITIES}/{world.entity_id}",
        world.maya,
        {field: value},
        if_match=shown.headers["etag"],
    )
    assert changed.status_code == 409, changed.text  # a named refusal, never a 500
    body = changed.json()
    assert body["type"].endswith("/immutable-record") and body["code"] == "EREV-REF-001", body
    assert [error["rule_id"] for error in body["errors"]] == ["ENTITY_FROZEN"], body
    assert body["detail"] and AVM_US in body["detail"], body  # the entity …
    assert "functional_currency" in body["detail"] and "time_zone" in body["detail"]  # … its fields
    assert _frozen_fields(world) == before  # nothing saved: fields and row_version unchanged
    unchanged = get(world.app, f"{ENTITIES}/{world.entity_id}", world.maya).json()
    assert unchanged[field] == shown.json()[field]
