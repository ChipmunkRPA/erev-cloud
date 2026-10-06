"""A report run under a role held for named entities (supervisor ruling R-63 (e) and the ruling on
SECFIX-SCOPE item 1; 03 REQ-PLT-012; 04 T-PLT-10; ENGINE_SPEC_B S15-R-03; SCREENS_B RPT-03).

WLD-K-04 (``worlds.k04_saltmarsh``): AVM-UK contracts ``SF-ORD-UK-2001`` and AVM-US performs O1,
so AVM-US's performance relieves AVM-UK's contract liability through the intercompany account.
The roles for named entities are granted through the product — ``POST /role-assignments`` with
entity codes, requested by Marcus (Tenant Admin) and approved by Grace, a second Tenant Admin
(PRD J-22.1) — where the proofs before this item wrote the rows directly. Grace's own role is a
row of the test world (``support.reference.assign``).
"""

from __future__ import annotations

from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import role
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, post
from support.worlds import AVM_UK, AVM_US, REPORT_RUNS, report_run
from tests.domain.contracts.test_reader_independence import INVOICE, recorded

ROLLFORWARD = "contract_balance_rollforward"
ASSIGNMENTS = "/api/v1/role-assignments"
JUNE = "FY2026-P06"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def second_admin(world: worlds.ReportWorld, clock: FrozenClock) -> Actor:
    """Grace, Tenant Admin for all entities: the approver of Marcus's access requests."""
    grace = colleague(world.tenant_id, "grace")
    assign(grace, "tenant_admin")
    return enrolled(world.app, clock, grace)


def scoped(
    world: worlds.ReportWorld,
    clock: FrozenClock,
    approver: Actor,
    name: str,
    *grants: tuple[str, str],
) -> Actor:
    """A member holding each (role, entity code) of ``grants``: Marcus requests, ``approver``
    approves (PRD J-22.1, J-22.2)."""
    someone = colleague(world.tenant_id, name)
    for role_code, entity_code in grants:
        role_id = world.place.scalar(select(role.c.id).where(role.c.code == role_code))
        granted = post(
            world.app,
            ASSIGNMENTS,
            world.marcus,
            {
                "membership_id": str(someone.membership_id),
                "role_id": str(role_id),
                "is_all_entities": False,
                "entity_codes": [entity_code],
            },
        )
        assert granted.status_code == 201, granted.text
        assert granted.json()["status"] == "REQUESTED", granted.text
        approved = approve(world.app, granted.json()["approval_request_id"], approver)
        assert approved.status_code == 200, approved.text
    return enrolled(world.app, clock, someone)


def ranged(period_key: str, entity: str) -> dict[str, Any]:
    return {
        "entity_codes": [entity],
        "book": "ASC606",
        "from_period_key": period_key,
        "to_period_key": period_key,
    }


def section_1(rows: list[dict[str, Any]]) -> dict[str, str]:
    """RPT-03 section 1: the contract liability by line code, the lines at zero left out."""
    return {
        str(row["line_code"]): str(row["contract_liability"]["amount"])
        for row in rows
        if row["line_code"] and row["contract_liability"]["amount"] != "0.00"
    }


def refused(world: worlds.ReportWorld, actor: Actor, entity: str) -> list[tuple[str, str]]:
    started = post(
        world.app,
        REPORT_RUNS,
        actor,
        {"report_code": ROLLFORWARD, "parameters": ranged(JUNE, entity), "output_format": "JSON"},
    )
    assert started.status_code == 422, started.text
    return [(error["field"], error["message"]) for error in started.json()["errors"]]


@pytest.mark.slow
def test_a_reader_of_the_contracting_entity_sees_what_the_other_entity_performed(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ula is Revenue Accountant for AVM-UK alone. Her rollforward of AVM-UK for June 2026 is the
    one an all-entities reader gets: the opening liability 48,544.81 relieved by 4,790.61 — the
    month's performance of O1 by AVM-US, a line of AVM-UK's own books — closing 43,754.20, tie
    PASS. The scope of her role hides nothing of her entity. AVM-US she cannot name: the answer
    is the one for a code that names no entity."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    ula = scoped(world, clock, second_admin(world, clock), "ula", ("revenue_accountant", AVM_UK))
    expected = {"OPENING": "48544.81", "REVENUE_FROM_OPENING": "-4790.61", "CLOSING": "43754.20"}

    everyone, rows = report_run(world, ROLLFORWARD, ranged(JUNE, AVM_UK))
    assert section_1(rows) == expected
    hers, own_rows = report_run(world, ROLLFORWARD, ranged(JUNE, AVM_UK), actor=ula)
    assert section_1(own_rows) == expected
    assert hers["tie_out_results"] == everyone["tie_out_results"]
    assert [item["code"] for item in hers["entity_scope"]] == [AVM_UK]
    assert refused(world, ula, AVM_US) == refused(world, ula, "AVM-FR")


@pytest.mark.slow
def test_a_run_names_the_entities_its_permission_is_held_for(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A run's entities are those ``report.run`` is held for — not every entity some role of the
    caller covers. Ian is Tenant Admin for AVM-US, a role without ``report.run``, and Viewer for
    AVM-UK: his session sees both entities, a run for AVM-UK is his, and AVM-US answers as a
    code that names no entity."""
    world = worlds.k04_saltmarsh(app, keyring, clock, files).report
    grace = second_admin(world, clock)
    ian = scoped(world, clock, grace, "ian", ("tenant_admin", AVM_US), ("viewer", AVM_UK))
    run, _ = report_run(world, ROLLFORWARD, ranged(JUNE, AVM_UK), actor=ian)
    assert [item["code"] for item in run["entity_scope"]] == [AVM_UK]
    assert refused(world, ian, AVM_US) == refused(world, ian, "AVM-FR")


@pytest.mark.slow
def test_an_event_of_a_member_of_one_entity_computes_the_group_and_reads_as_everyone_reads_it(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ula is Revenue Accountant for AVM-UK alone, a grant of the product. She records an invoice
    of 100.00 GBP on ``SF-ORD-UK-2001`` (5 June 2026), whose obligation O1 AVM-US performs: 201 and
    the computation SUCCEEDED — it runs as SYSTEM on her behalf under the tenant's scope (05
    RCP-18; supervisor rulings R-95 and R-98 (3); lane QA-BE's CTR-COMPUTE-CALLER-SCOPE-1, whose
    own witnesses write the member's role as a row). Before that slice the group was QUARANTINED
    for a caller of one entity. Her June rollforward of AVM-UK is then the one a reader of all
    entities gets: the opening liability 48,544.81, the billing 100.00, the revenue from the
    opening liability 4,790.61, closing 43,854.20 = 48,544.81 + 100.00 − 4,790.61."""
    k04 = worlds.k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    ula = scoped(world, clock, second_admin(world, clock), "ula", ("revenue_accountant", AVM_UK))

    sent = recorded(app, ula, k04.contract_id, INVOICE)
    assert sent.status_code == 201, sent.text
    assert sent.json()["computation"]["status"] == "SUCCEEDED", sent.text

    expected = {
        "OPENING": "48544.81",
        "BILLINGS": "100.00",
        "REVENUE_FROM_OPENING": "-4790.61",
        "CLOSING": "43854.20",
    }
    everyone, rows = report_run(world, ROLLFORWARD, ranged(JUNE, AVM_UK))
    assert section_1(rows) == expected
    hers, own_rows = report_run(world, ROLLFORWARD, ranged(JUNE, AVM_UK), actor=ula)
    assert section_1(own_rows) == expected
    assert hers["tie_out_results"] == everyone["tie_out_results"]
    # opening plus activity is closing, and the balances at the range end are the closing line;
    # the tie to the ledger does not apply without a trial balance
    assert {item["code"]: item["result"] for item in hers["tie_out_results"]} == {
        "TO_ROLLFORWARD_BALANCES": "PASS",
        "TO_BALANCES_EQ_ROLLFORWARD": "PASS",
        "TO_ROLLFORWARD_EQ_GL": "NOT_APPLICABLE",
    }
