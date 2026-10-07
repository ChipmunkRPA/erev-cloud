"""Judgement, estimate change, scope exclusion and loss provision registers (SCREENS_B §5.6.1
RPT-31, §5.6.2 RPT-28 to RPT-30; PRD J-06-AC-2, J-07-AC-2, J-10-AC-3, WLD-X-10 to WLD-X-12,
WLD-X-16, §2.10 BR-06; 03 REQ-RPT-023, REQ-LOS-003, REQ-CON-016; BUILD_SPEC RPS-11).

Worlds, each built through the product's commands; every report runs through ``POST
/report-runs`` and its ``REPORT_RUN`` job; the frozen clock starts at 2026-09-12T12:00:00Z.

- K-06 of ``tests/domain/contracts/test_estimates.py`` (PRD WLD-K-06): ``NS-SO-DE-5002`` with
  ``REBATE-DR-01`` version 1, the two shipments, then version 2 approved by Priya (J-07).
- ``support.worlds.k03_castellan`` with ``k03_change_order`` (J-06) and ``k03_september`` (J-10):
  ``PRJ-CB-2026-01`` through WLD-X-10, WLD-X-11 and WLD-X-12.
- ``support.worlds.br06_lease`` (PRD §2.10 BR-06): a lease component routed to ASC 842.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_version, legal_entity
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.reference import approve, get, post
from support.worlds import (
    AVM_US,
    BONUS_CB_01,
    BR06_EXTERNAL_ID,
    K03_CONSTRAINT_CONCLUSION,
    K03_EXTERNAL_ID,
    ROBOT_LEASE,
    SEPTEMBER_2026,
    Br06World,
    K03World,
    ReportWorld,
    br06_lease,
    judgement_submitted,
    k03_castellan,
    k03_change_order,
    k03_revenue,
    k03_september,
    report_run,
)
from tests.domain.contracts.test_estimates import (
    ESTIMATES,
    K06_CONTRACT,
    REBATE,
    VERSIONS,
    _k06_with_v1,
    _submitted,
    _v2_body,
    k06_world,
)

STEP: Final = timedelta(seconds=20)
CENT: Final = Decimal("0.01")
D = Decimal


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def k03(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K03World:
    return k03_castellan(app, keyring, clock, files)


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # a row key occurs once
    return found


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def historical(
    world: ReportWorld, code: str, parameters: Mapping[str, Any], *, known_at: datetime
) -> Any:
    """The builder of ``code`` called in a unit of work for an explicit historical read as of
    ``known_at``: the way a REGISTER-CUTOFF-1 refusal is read."""
    with world.place.uow() as uow:
        return framework.BUILDERS[code](
            uow,
            ReportParams(
                report_code=code,
                report_version=1,
                parameters=dict(parameters),
                entity_ids=(world.entity_id,),
                known_at=known_at,
                historical=True,
            ),
        )


# --- RPT-29 -----------------------------------------------------------------------------------


@pytest.mark.slow
def test_estimate_change_listing_k06(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD J-07-AC-2: element ``REBATE-DR-01``; version 1 → 2; the rebate expected 0.00 before
    and 5,750.00 after; effect (5,750.00); preparer Maya; approver Priya."""
    world = k06_world(app, keyring, clock, files)
    place = world.place
    maya = place.author
    k06 = _k06_with_v1(world)
    clock.advance(STEP)
    v2 = post(app, f"{ESTIMATES}/{k06.estimate_id}/versions", maya, _v2_body())  # J-07.2
    assert v2.status_code == 201, v2.text
    v2_id = str(v2.json()["id"])
    request_id = _submitted(world, v2_id)
    clock.advance(STEP)
    decided = approve(app, request_id, world.priya)  # J-07.4
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    shown = get(app, f"{VERSIONS}/{v2_id}", maya).json()
    (entity,) = place.rows(select(legal_entity.c.id).where(legal_entity.c.code == "AVM-DE"))
    report = ReportWorld(
        place=place,
        priya=world.priya,
        marcus=world.marcus,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        entity_id=UUID(str(entity["id"])),
        contracts=MappingProxyType({}),
    )
    clock.advance(STEP)
    parameters = {
        "entity_codes": ["AVM-DE"],
        "book": "ASC606",
        "from_date": "2026-07-01",
        "to_date": "2026-09-30",
    }
    run, rows = report_run(report, "estimate_change_listing", parameters)
    assert run["status"] == "SUCCEEDED"
    assert run["parameters"]["currency_view"] == "transaction"
    found = keyed(rows)
    assert list(found) == [
        f"estimate:{K06_CONTRACT}:{REBATE}:1",
        f"estimate:{K06_CONTRACT}:{REBATE}:2",
    ]
    changed = found[f"estimate:{K06_CONTRACT}:{REBATE}:2"]
    assert (changed["element_code"], changed["estimate_kind"], changed["method"]) == (
        REBATE,
        "VARIABLE_CONSIDERATION",
        "MOST_LIKELY_AMOUNT",
    )
    assert (changed["contract_external_id"], changed["obligation_key"]) == (K06_CONTRACT, None)
    assert (changed["version_pair"], changed["effective_date"]) == ("v1 → v2", "2026-09-30")
    # the rebate expected (the constrained amount of the element): 0.00 before, 5,750.00 after
    assert (changed["measure_label"], changed["currency"]) == ("Constrained amount", "EUR")
    assert (changed["before_value"], changed["after_value"]) == ("0.00", "5750.00")
    assert changed["pnl_effect"] == {"amount": "-5750.00", "currency": "EUR"}  # effect (5,750.00)
    assert changed["preparer"] == shown["created_by"]["display_name"]  # Maya, the world's author
    assert changed["approver"] == "Priya" == shown["approver"]["display_name"]
    assert changed["approved_at"] == shown["approved_at"]
    # J-07.2's evidence (WLD-F-24): a version is submitted with its evidence attached (04 §16.14
    # rev 1.241, item EST-EVIDENCE-AT-SUBMIT-1), so each version of this world counts its one file
    assert (changed["no_change_attestation"], changed["attachment_count"]) == (False, 1)
    # WLD-X-16: the effect is the change of cumulative revenue the version caused
    versions = place.rows(
        select(contract_version.c.revenue_cum, contract_version.c.transaction_price)
        .where(contract_version.c.combination_group_id == k06.group_id)
        .order_by(contract_version.c.version_no)
    )
    assert (D(versions[-2]["revenue_cum"]), D(versions[-1]["revenue_cum"])) == (
        D("57500.00"),
        D("51750.00"),
    )
    first = found[f"estimate:{K06_CONTRACT}:{REBATE}:1"]
    assert (first["version_pair"], first["before_value"], first["after_value"]) == (
        "v1",
        None,
        "0.00",
    )
    assert first["pnl_effect"] == {"amount": "0.00", "currency": "EUR"}
    assert (first["approver"], first["attachment_count"]) == ("Priya", 1)
    assert run["control_totals"] == {
        "row_count": 2,
        "pnl_effect_total": {"EUR": "-5750.00"},
        "from_date": "2026-07-01",
        "to_date": "2026-09-30",
    }

    # the filters; the functional view of an entity whose functional currency is the contract's
    _, before = report_run(
        report, "estimate_change_listing", {**parameters, "to_date": "2026-09-29"}
    )
    assert [row["row_key"] for row in before] == [f"estimate:{K06_CONTRACT}:{REBATE}:1"]
    _, other = report_run(
        report, "estimate_change_listing", {**parameters, "estimate_kind": ["EAC"]}
    )
    assert other == []
    _, functional = report_run(
        report, "estimate_change_listing", {**parameters, "currency_view": "functional"}
    )
    assert functional == rows


@pytest.mark.slow
def test_estimate_change_listing_k03(k03: K03World, clock: FrozenClock) -> None:
    """PRD J-06-AC-2: EAC 700,000.00 → 820,000.00 and bonus 0.00 → 200,000.00, each approved by
    Priya, with the effect shown; WLD-X-12: EAC 820,000.00 → 850,000.00, effect (29,169.29).

    Supervisor ruling R-41 (7) (PRD §2.5 ``ESTIMATE_VERSION`` "If absolute P&L impact ≥ USD
    50,000.00: 2: Controller"; 04 rev 1.104): the two versions of J-06 apply as requests of their
    own with effects of (87,804.88) and 102,439.02, so each takes the Controller's second step and
    the listing names both approvers, Priya then Marcus. Version 3, (29,169.29), stays Priya's."""
    world = k03.report
    k03_change_order(k03, clock)  # J-06
    after_change_order = k03_revenue(world.place, k03.group_id)
    k03_september(k03, clock)  # J-10
    clock.advance(STEP)
    run, rows = report_run(
        world, "estimate_change_listing", {"entity_codes": [AVM_US], "book": "ASC606"}
    )
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    eac, bonus = f"estimate:{K03_EXTERNAL_ID}:EAC", f"estimate:{K03_EXTERNAL_ID}:{BONUS_CB_01}"
    assert list(found) == [f"{bonus}:1", f"{bonus}:2", f"{eac}:1", f"{eac}:2", f"{eac}:3"]

    eac_v2 = found[f"{eac}:2"]
    assert (eac_v2["estimate_kind"], eac_v2["method"], eac_v2["obligation_key"]) == (
        "EAC",
        "COST_BUILDUP",
        "O1",
    )
    assert (eac_v2["version_pair"], eac_v2["effective_date"]) == ("v1 → v2", "2026-09-10")
    assert (eac_v2["measure_label"], eac_v2["currency"]) == ("Expected total", "USD")
    assert (eac_v2["before_value"], eac_v2["after_value"]) == ("700000.00", "820000.00")
    assert eac_v2["approver"] == "Priya, Marcus"
    bonus_v2 = found[f"{bonus}:2"]
    assert (bonus_v2["estimate_kind"], bonus_v2["method"], bonus_v2["obligation_key"]) == (
        "VARIABLE_CONSIDERATION",
        "MOST_LIKELY_AMOUNT",
        None,
    )
    assert (bonus_v2["measure_label"], bonus_v2["version_pair"]) == (
        "Constrained amount",
        "v1 → v2",
    )
    assert (bonus_v2["before_value"], bonus_v2["after_value"]) == ("0.00", "200000.00")
    assert bonus_v2["approver"] == "Priya, Marcus"

    # the effect shown: the catch-up each version caused when it was applied. EAC version 2 moved
    # progress from 420,000 / 700,000 to 420,000 / 820,000 of 1,000,000.00; bonus version 2 then
    # raised the price to 1,200,000.00 at that progress.
    progress = D(420000) / D(820000)
    after_eac = cents(progress * D(1000000))
    after_bonus = cents(progress * D(1200000))
    assert eac_v2["pnl_effect"] == usd(str(after_eac - D("600000.00")))
    assert bonus_v2["pnl_effect"] == usd(str(after_bonus - after_eac))
    # with the change order's own step they are the catch-up of WLD-X-10: 91,463.41
    assert after_change_order == D("691463.41")
    assert (
        D(eac_v2["pnl_effect"]["amount"])
        + D(bonus_v2["pnl_effect"]["amount"])
        + (after_change_order - after_bonus)
    ) == D("91463.41")
    eac_v3 = found[f"{eac}:3"]  # WLD-X-12; SCREENS_B RPT-29 sample
    assert (eac_v3["version_pair"], eac_v3["effective_date"]) == ("v2 → v3", "2026-09-30")
    assert (eac_v3["before_value"], eac_v3["after_value"]) == ("820000.00", "850000.00")
    assert eac_v3["pnl_effect"] == usd("-29169.29")
    assert eac_v3["approver"] == "Priya"
    # the first versions: no predecessor, no catch-up
    for key, value in ((f"{eac}:1", "700000.00"), (f"{bonus}:1", "0.00")):
        row = found[key]
        assert (row["version_pair"], row["before_value"], row["after_value"]) == ("v1", None, value)
        assert (row["pnl_effect"], row["effective_date"]) == (usd("0.00"), "2026-02-01")
    total = sum(D(row["pnl_effect"]["amount"]) for row in rows)
    assert run["control_totals"] == {
        "row_count": 5,
        "pnl_effect_total": {"USD": str(total)},
        "from_date": "2026-01-01",  # the context fiscal year to the end of the context period
        "to_date": "2026-09-30",
    }
    for row in rows:
        assert "maya" in row["preparer"].lower() and row["approved_at"].endswith("Z")

    _, estimates = report_run(
        world,
        "estimate_change_listing",
        {"entity_codes": [AVM_US], "book": "ASC606", "estimate_kind": ["EAC"]},
    )
    assert [row["row_key"] for row in estimates] == [f"{eac}:1", f"{eac}:2", f"{eac}:3"]


# --- RPT-31 -----------------------------------------------------------------------------------


@pytest.mark.slow
def test_loss_provision_register_k03(k03: K03World, clock: FrozenClock) -> None:
    """PRD J-10-AC-3; REQ-LOS-003: ``PRJ-CB-2026-01`` with EAC version 3, expected consideration
    1,350,000.00 and provision balance 0.00 (SCREENS_B RPT-31)."""
    world = k03.report
    k03_change_order(k03, clock)
    k03_september(k03, clock)
    clock.advance(STEP)
    run, rows = report_run(
        world,
        "loss_provision_register",
        {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026},
    )
    assert run["status"] == "SUCCEEDED"
    row = keyed(rows)[f"contract:{K03_EXTERNAL_ID}"]
    assert (row["contract_external_id"], row["eac_version_no"]) == (K03_EXTERNAL_ID, 3)
    assert row["expected_consideration"] == usd("1350000.00")
    assert row["provision_balance"] == usd("0.00")
    # the loss test of J-10.3: estimated costs 850,000.00 are below the transaction price
    assert (row["expected_total_costs"], row["expected_margin"]) == (
        usd("850000.00"),
        usd("500000.00"),
    )
    assert (row["costs_to_date"], row["revenue_to_date"]) == (
        usd("502000.00"),
        usd("797294.12"),  # WLD-X-12
    )


# --- RPT-28 -----------------------------------------------------------------------------------


@pytest.mark.slow
def test_judgement_register_status_filter(k03: K03World, clock: FrozenClock) -> None:
    """SF-05 BLK-06: ``p.status=SUBMITTED`` lists only the records that wait for review."""
    world = k03.report
    app, maya = world.app, world.maya
    order = k03_change_order(k03, clock)  # the CONSTRAINT record of J-06.1, reviewed by Priya
    clock.advance(STEP)
    waiting = judgement_submitted(  # PRD J-14.1
        app,
        maya,
        {
            "topic": "ESTIMATE_VS_ERROR",
            "subject_type": "contract",
            "subject_id": str(k03.contract_id),
            "conclusion": "Error: the cost existed and was known at period end.",
            "rationale": "The job-cost report of 29 Sep 2026 lists the omitted cost.",
            "codification_refs": ["250-10-45-23"],
            "book": "ASC606",
        },
    )
    drafted = post(
        app,
        "/api/v1/judgements",
        maya,
        {
            "topic": "OTHER",
            "subject_type": "estimate_version",
            "subject_id": order.bonus_v2_id,
            "contract_id": str(k03.contract_id),
            "conclusion": "The completion bonus is a single performance bonus.",
            "rationale": "One milestone decides the whole amount.",
        },
    )
    assert drafted.status_code == 201, drafted.text
    clock.advance(STEP)

    parameters = {"entity_codes": [AVM_US], "book": "ASC606"}
    run, rows = report_run(world, "judgement_register", {**parameters, "status": ["SUBMITTED"]})
    assert run["status"] == "SUCCEEDED"
    (row,) = rows
    assert row["row_key"] == f"judgement:{waiting['judgement_no']}"
    assert (row["judgement_no"], row["topic"], row["status"]) == (
        waiting["judgement_no"],
        "ESTIMATE_VS_ERROR",
        "SUBMITTED",
    )
    assert (row["subject_type"], row["subject_label"], row["contract_external_id"]) == (
        "contract",
        K03_EXTERNAL_ID,
        K03_EXTERNAL_ID,
    )
    assert (row["book"], row["codification_refs"]) == ("ASC606", ["250-10-45-23"])
    assert row["conclusion"] == "Error: the cost existed and was known at period end."
    assert "maya" in row["created_by"].lower()
    assert (row["reviewer"], row["reviewed_at"], row["supersedes_no"]) == (None, None, None)
    assert run["control_totals"] == {
        "row_count": 1,
        "record_count": 1,  # head R28-READS: the records of the run in all (SCREENS_B RPT-28)
        "from_date": "2026-01-01",
        "to_date": "2026-09-12",
    }

    # every record: the two reviewed ones with their reviewer — the CONSTRAINT record bonus
    # version 1 of the world was submitted with (04 §16.14 rev 1.241), a record of that version,
    # and the one of J-06 — the waiting one and the draft
    _, every = report_run(world, "judgement_register", parameters)
    found = keyed(every)
    assert list(found) == sorted(found) and len(found) == 4
    initial = every[0]
    assert (initial["topic"], initial["status"], initial["reviewer"]) == (
        "CONSTRAINT",
        "REVIEWED",
        "Priya",
    )
    assert (initial["subject_type"], initial["subject_label"]) == (
        "estimate_version",
        f"{BONUS_CB_01} v1",
    )
    reviewed = found[f"judgement:{order.judgement['judgement_no']}"]
    assert (reviewed["topic"], reviewed["status"], reviewed["reviewer"]) == (
        "CONSTRAINT",
        "REVIEWED",
        "Priya",
    )
    assert reviewed["conclusion"] == K03_CONSTRAINT_CONCLUSION
    assert reviewed["reviewed_at"] == order.judgement["reviewed_at"]
    assert (reviewed["book"], reviewed["codification_refs"]) == (
        None,  # every book
        ["606-10-32-11", "606-10-32-12"],
    )
    draft = found[f"judgement:{drafted.json()['judgement_no']}"]
    assert (draft["status"], draft["subject_type"], draft["subject_label"]) == (
        "DRAFT",
        "estimate_version",
        f"{BONUS_CB_01} v2",
    )
    _, by_topic = report_run(world, "judgement_register", {**parameters, "topic": ["CONSTRAINT"]})
    assert by_topic == [initial, reviewed]
    _, unreviewed = report_run(
        world, "judgement_register", {**parameters, "status": ["DRAFT", "SUBMITTED"]}
    )
    assert [item["status"] for item in unreviewed] == ["SUBMITTED", "DRAFT"]
    # a record of another book is outside the run's book; a range before the records is empty
    _, ifrs = report_run(world, "judgement_register", {"entity_codes": [AVM_US], "book": "IFRS15"})
    assert {item["row_key"] for item in ifrs} == {
        initial["row_key"],
        reviewed["row_key"],
        draft["row_key"],
    }
    _, earlier = report_run(
        world,
        "judgement_register",
        {**parameters, "from_date": "2026-01-01", "to_date": "2026-09-11"},
    )
    assert earlier == []

    # REGISTER-CUTOFF-1: T-CON-19 keeps no status history, so an explicit historical read between
    # the CONSTRAINT record's submission and its review is refused by name; as of the present
    # nothing changed afterwards and the read is served
    reviewed_at = datetime.fromisoformat(order.judgement["reviewed_at"])
    with pytest.raises(Problem) as refused:
        historical(
            world,
            "judgement_register",
            {"book": "ASC606"},
            known_at=reviewed_at - timedelta(seconds=1),
        )
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at"
    assert order.judgement["judgement_no"] in error.message
    assert "keeps no history of its status" in error.message
    served = historical(world, "judgement_register", {"book": "ASC606"}, known_at=clock.now())
    assert [item["judgement_no"] for item in served.rows] == sorted(
        item["judgement_no"] for item in every
    )


# --- RPT-30 -----------------------------------------------------------------------------------

LEASE_RATIONALE: Final = (
    "Pellworth directs the use of the identified robot for 36 months and obtains substantially "
    "all of its economic benefits (ASC 842-10-15-3)."
)


@pytest.mark.slow
def test_scope_exclusion_register(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """REQ-CON-016: a contract with a line routed out under the ASC 842 scope flag is listed with
    the flag, its out-of-scope amount and the rationale of its judgement."""
    br06: Br06World = br06_lease(app, keyring, clock, files)
    world = br06.report
    parameters = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026}
    clock.advance(STEP)
    run, rows = report_run(world, "scope_exclusion_register", parameters)
    assert run["status"] == "SUCCEEDED"
    assert run["parameters"]["currency_view"] == "transaction"
    (row,) = rows  # the in-scope service line is not listed
    assert row["row_key"] == f"obligation:{BR06_EXTERNAL_ID}:L1-LEASE"
    assert (row["contract_external_id"], row["obligation_key"], row["product_code"]) == (
        BR06_EXTERNAL_ID,
        "L1-LEASE",
        ROBOT_LEASE,
    )
    assert (row["scope_flag"], row["currency"]) == ("LEASE_842", "USD")
    # answer key ALC-BR-06: the lease allocation of 108,000.00 on SSP 90,000.00 of 120,000.00
    assert row["out_of_scope_amount"] == usd("81000.00")
    assert row["effective_date"] == "2026-01-01"
    assert (row["judgement_no"], row["rationale"]) == (None, None)  # no judgement recorded yet
    assert run["control_totals"] == {
        "row_count": 1,
        "out_of_scope_amount_total": {"USD": "81000.00"},
        "as_of": "2026-09-30",
    }

    judgement = judgement_submitted(
        app,
        world.maya,
        {
            "topic": "OTHER",
            "subject_type": "obligation",
            "subject_id": str(br06.lease_obligation_id),
            "conclusion": "The robot is an identified asset the customer controls: a lease.",
            "rationale": LEASE_RATIONALE,
            "codification_refs": ["842-10-15-3", "606-10-15-2"],
        },
    )
    clock.advance(STEP)
    reviewed = approve(app, str(judgement["approval_request_id"]), world.priya)
    assert (reviewed.status_code, reviewed.json()["status"]) == (200, "APPROVED"), reviewed.text
    clock.advance(STEP)
    _, documented = report_run(world, "scope_exclusion_register", parameters)
    (listed,) = documented
    assert (listed["scope_flag"], listed["judgement_no"], listed["rationale"]) == (
        "LEASE_842",
        judgement["judgement_no"],
        LEASE_RATIONALE,
    )
    assert listed["out_of_scope_amount"] == row["out_of_scope_amount"]
    # the register follows the judgement register's record
    _, judgements = report_run(
        world, "judgement_register", {"entity_codes": [AVM_US], "book": "ASC606"}
    )
    (record,) = judgements
    assert (record["judgement_no"], record["subject_type"], record["subject_label"]) == (
        judgement["judgement_no"],
        "obligation",
        f"{BR06_EXTERNAL_ID} L1-LEASE",
    )
    assert (record["status"], record["reviewer"]) == ("REVIEWED", "Priya")


def test_loss_tests_persist_periods_and_eac_lineage(k03: K03World, clock: FrozenClock) -> None:
    from erev_api.db.tables import estimate_version, loss_provision_eac, loss_provision_version
    from erev_api.domain.contracts import bundles
    from erev_engine import compute
    from erev_engine.money import minor_to_decimal

    k03_change_order(k03, clock)
    k03_september(k03, clock)
    with k03.report.place.uow() as uow:
        latest = uow.session.execute(
            select(contract_version.c.id)
            .where(
                contract_version.c.combination_group_id == k03.group_id,
                contract_version.c.book_code == "ASC606",
            )
            .order_by(contract_version.c.version_no.desc())
            .limit(1)
        ).scalar_one()
        rows = (
            uow.session.execute(
                select(loss_provision_version)
                .where(
                    loss_provision_version.c.contract_version_id == latest,
                )
                .order_by(loss_provision_version.c.as_of)
            )
            .mappings()
            .all()
        )
        assert len(rows) > 1 and len({row["period_key"] for row in rows}) == len(rows)
        august = next(row for row in rows if row["as_of"].isoformat() == "2026-08-31")
        assert august["expected_consideration"] == Decimal("1200000")
        september = next(row for row in rows if row["period_key"] == SEPTEMBER_2026)
        assert september["contract_id"] == k03.contract_id
        assert september["in_scope"] is True
        # Storage is checked against the complete engine output, not a substituted calculation.
        bundle = bundles.build(uow.session, k03.group_id, uow.now)
        book = next(item for item in compute(bundle).books if item.book_code == "ASC606")
        emitted = next(
            item for item in book.loss_provision_versions if item.period_key == SEPTEMBER_2026
        )
        for name in (
            "expected_consideration",
            "expected_total_costs",
            "costs_to_date",
            "revenue_to_date",
            "expected_margin",
            "provision_balance",
            "provision_movement",
        ):
            assert september[name] == minor_to_decimal(int(str(emitted.columns[name])), 2)
        assert september["expected_consideration"] == Decimal("1350000")
        assert september["expected_margin"] == Decimal("500000")
        assert september["expected_total_costs"] == Decimal("850000")
        assert september["costs_to_date"] == Decimal("502000")
        assert september["revenue_to_date"] == Decimal("797294.12")
        assert september["trace_nodes"]
        sources = uow.session.execute(
            select(estimate_version.c.id, estimate_version.c.version_no)
            .join(
                loss_provision_eac,
                estimate_version.c.id == loss_provision_eac.c.estimate_version_id,
            )
            .where(loss_provision_eac.c.loss_provision_version_id == september["id"])
        ).all()
        assert sources == [(september["eac_estimate_version_id"], 3)]
