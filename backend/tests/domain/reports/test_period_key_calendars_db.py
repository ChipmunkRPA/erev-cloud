"""Entities of more than one fiscal calendar are refused a period named by key, and a report whose
columns are period keys (item RPT-PERIOD-KEY-CALENDARS-1; 04 T-RPT-01 rule 6 rev 1.264; PRD ERR-97
rev 1.180; the supervisor's rulings of 2026-10-02). PostgreSQL-bound, through
``POST /report-runs`` and ``POST /report-runs/{id}/rerun``.

World: PRD WLD-K-01 (``support.worlds.k01_pellworth``: AVM-US on a January calendar,
``SF-ORD-10001`` through September 2026) and beside it AVM-AP on an April calendar, with the same
contract booked under ``AP-ORD-0001``, activated on 1 January 2026 and computed, and AVM-CA on
AVM-US's calendar with no contract. On the January calendar September 2026 is FY2026-P09; on the
April calendar it is FY2027-P06, and FY2026-P09 is December 2025.

PRODUCT DEFECT of the release-blocker class, measured through the product on 2026-10-01: a
builder reads a period named by key in each entity's own calendar, and the framework admitted any
entities with any key. At ``FY2026-P09`` the RPO over both entities was 29,944.11 — AVM-US's
September beside AVM-AP's December 2025, with two as-of dates in its control totals — where the
two entities' September is 76,088.22; the contract balance roll-forward and the disaggregation
left AVM-AP's September out; the waterfall of FY2026-P07 to FY2026-P12 set AVM-AP's January to
March 2026 into the columns of October to December. Each of those requests is refused here. So is
a run without a key of the two definitions whose columns are period keys, measured on 2026-10-02:
the waterfall stated each calendar's fiscal year beside the other, 24 month columns, and the
disaggregation September 2026 twice, as ``period:FY2026-P09`` and ``period:FY2027-P06``.

The oracle stands outside the rule: an entity's own September is the run of that entity alone at
its own key, and a run that names no key reads each entity at its own period holding the run's
date — the two sums agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity, report_run
from erev_api.domain.reports import catalogue, framework
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.factories import booked_contract, computed, open_periods
from support.http import HttpResponse
from support.reference import CALENDARS, entity, get, post, slug
from support.worlds import AVM_US, K01, REPORT_RUNS, ReportWorld
from support.worlds import report_run as run_of

AP: Final = "AVM-AP"  # the April calendar
CA: Final = "AVM-CA"  # AVM-US's calendar; no contract
AP_CONTRACT: Final = "AP-ORD-0001"
# September 2026 on the January calendar; December 2025 on the April calendar.
JAN_SEPTEMBER: Final = "FY2026-P09"
APR_SEPTEMBER: Final = "FY2027-P06"  # September 2026 on the April calendar
BOOK: Final = {"book": "ASC606"}
BOTH: Final = [AP, AVM_US]
# PRD WLD-K-01 at 30 September 2026: what is left of O1. AVM-AP's copy has no progress on O2, so
# its 16,200.00 still waits for its trigger.
US_SEPTEMBER: Final = Decimal("29944.11")
AP_SEPTEMBER: Final = US_SEPTEMBER + Decimal("16200.00")
REFUSAL: Final = {
    "field": "parameters.entity_codes",
    "rule_id": "CALENDARS_DIFFER",
    "message": (
        "The entities of this run keep different fiscal calendars, so a period key can name "
        "different months for them. Run the report for entities of one calendar."
    ),
}
# The registered definitions that take a period by key as the rule was built. The witness reads
# its list from the catalogue, so a definition registered later is asked too; these stay in it.
KEYED_ON_2026_10_02: Final = frozenset(
    {
        "book_bridge",
        "contract_balance_rollforward",
        "contract_balances",
        "contract_cost_rollforward",
        "disaggregation",
        "intercompany_pairs",
        "je_population",
        "late_entry_report",
        "manual_adjustment_register",
        "out_of_period_register",
        "revenue_from_opening_liability",
        "revenue_from_prior_period_obligations",
        "revenue_waterfall",
        "rpo",
        "rpo_rollforward",
        "scope_exclusion_register",
    }
)
# The four requests measured on 2026-10-01, with what each answered then.
MEASURED: Final[tuple[tuple[str, str, Mapping[str, Any]], ...]] = (
    (
        "the RPO: 29,944.11 for two entities whose September is 76,088.22",
        "rpo",
        {"entity_codes": BOTH, **BOOK, "period_key": JAN_SEPTEMBER},
    ),
    (
        "the RPO of every entity in scope: the same figure",
        "rpo",
        {**BOOK, "period_key": JAN_SEPTEMBER},
    ),
    (
        "the roll-forward: AVM-AP's asset 79,091.51 to 88,855.89 left out",
        "contract_balance_rollforward",
        {
            "entity_codes": BOTH,
            **BOOK,
            "from_period_key": JAN_SEPTEMBER,
            "to_period_key": JAN_SEPTEMBER,
        },
    ),
    (
        "the disaggregation: 9,764.38 of the month's 19,528.76",
        "disaggregation",
        {
            "entity_codes": BOTH,
            **BOOK,
            "from_period_key": JAN_SEPTEMBER,
            "to_period_key": JAN_SEPTEMBER,
        },
    ),
    (
        "the waterfall: AVM-AP's January to March in the columns of October to December",
        "revenue_waterfall",
        {
            "entity_codes": BOTH,
            **BOOK,
            "row_dimension": "OBLIGATION",
            "from_period_key": "FY2026-P07",
            "to_period_key": "FY2026-P12",
        },
    ),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ReportWorld:
    """WLD-K-01 with AVM-AP on an April calendar and AVM-CA on AVM-US's."""
    world = worlds.k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    created = post(
        app, CALENDARS, maya, {"code": "APRIL", "name": "April year", "fiscal_year_start_month": 4}
    )
    assert created.status_code == 201, created.text
    april = str(created.json()["id"])
    for year in (2026, 2027):
        generated = post(app, f"{CALENDARS}/{april}/generate-year", maya, {"fiscal_year": year})
        assert generated.status_code == 200, generated.text
    entity(app, maya, code=AP, calendar_id=april)
    # Every period from the calendar's first to September 2026, so that none lacks a state.
    keys = [f"FY2026-P{month:02d}" for month in range(1, 13)]
    keys += [f"FY2027-P{month:02d}" for month in range(1, 7)]
    open_periods(app, maya, entity_code=AP, keys=keys)
    customer = world.contracts[K01].contract["customer_id"]
    body = {
        **worlds.k01_body(UUID(str(customer))),
        "external_id": AP_CONTRACT,
        "contracting_entity_code": AP,
    }
    booked = booked_contract(world.place, body, activate=True)
    computed(world.place, UUID(str(booked.combination_group["id"])))
    january = world.place.scalar(
        select(legal_entity.c.calendar_id).where(legal_entity.c.code == AVM_US)
    )
    entity(app, maya, code=CA, calendar_id=str(january))
    return world


def started(world: ReportWorld, code: str, parameters: Mapping[str, Any]) -> HttpResponse:
    body = {"report_code": code, "parameters": dict(parameters), "output_format": "JSON"}
    return post(world.app, REPORT_RUNS, world.maya, body)


def refused(response: HttpResponse, what: str) -> None:
    """422 ``validation-failed`` with the one error of PRD ERR-97, its sentence the detail too."""
    assert response.status_code == 422, (what, response.text)
    problem = response.json()
    assert slug(response) == "validation-failed", what
    assert problem["detail"] == REFUSAL["message"], what
    assert [{name: error[name] for name in REFUSAL} for error in problem["errors"]] == [REFUSAL], (
        what
    )


def stored_runs(world: ReportWorld) -> int:
    return int(world.place.scalar(select(func.count()).select_from(report_run)))


def total(rows: list[dict[str, Any]]) -> Decimal:
    (row,) = [row for row in rows if row["row_key"] == "TOTAL:USD"]
    return Decimal(row["total"]["amount"])


def keyed_requests() -> list[tuple[str, str, dict[str, Any]]]:
    """Every registered definition that takes a period by key, with each of its key parameters
    alone. A definition that names one entity at most (``book_bridge``) is asked for every entity
    in scope — the only way it meets two calendars."""
    requests: list[tuple[str, str, dict[str, Any]]] = []
    for definition in catalogue.DEFINITIONS:
        properties = definition.parameters_schema["properties"]
        keys = sorted(key for key in properties if key.endswith("period_key"))
        if not keys or definition.code not in framework.BUILDERS:
            continue
        named = {} if properties["entity_codes"].get("maxItems") == 1 else {"entity_codes": BOTH}
        requests += [(definition.code, key, {**named, key: JAN_SEPTEMBER}) for key in keys]
    return requests


def test_a_period_named_by_key_is_refused_for_entities_of_two_calendars(
    world: ReportWorld,
) -> None:
    """04 T-RPT-01 rule 6 (PRD ERR-97). The four requests measured on 2026-10-01 answer the
    refusal where each stated one entity's September beside the other's December; so does every
    registered definition that takes a period by key, for each of its key parameters alone; so
    does, without a key, every definition whose columns are period keys — the set the framework
    reads from the builders, today the waterfall and the disaggregation. Nothing is stored: no
    run, so no job.

    Fail-first: every request answered 202 — the failure lists them — and its job stated the
    mixed figures."""
    before = stored_runs(world)
    requests = keyed_requests()
    assert {code for code, _, _ in requests} >= KEYED_ON_2026_10_02
    assert {key for _, key, _ in requests} == {
        "period_key",
        "from_period_key",
        "to_period_key",
        "origin_period_key",
    }
    columns = sorted(framework.PERIOD_KEY_COLUMNS)
    assert {"revenue_waterfall", "disaggregation"} <= set(columns)
    cases = [
        *MEASURED,
        *((f"{code} by {key}", code, parameters) for code, key, parameters in requests),
        *((f"{code} without a key", code, {"entity_codes": BOTH, **BOOK}) for code in columns),
        *((f"{code} of every entity in scope, without a key", code, BOOK) for code in columns),
    ]
    answered = [(what, started(world, code, parameters)) for what, code, parameters in cases]
    assert [what for what, response in answered if response.status_code != 422] == []
    for what, response in answered:
        refused(response, what)
    assert stored_runs(world) == before


def test_what_the_rule_leaves_alone(world: ReportWorld) -> None:
    """The rule's edge. A run that names NO period by key reads each entity at its own period
    holding the run's date: over both calendars the RPO is the two entities' September, with one
    as-of date. A period named by key is answered for one entity, in that entity's calendar, and
    for entities of one calendar.

    Not a fail-first witness: these answers are the same before and after the rule."""
    run, rows = run_of(
        world, "rpo", {"entity_codes": [AVM_US], **BOOK, "period_key": JAN_SEPTEMBER}
    )
    assert total(rows) == US_SEPTEMBER
    assert run["control_totals"]["as_of"] == "2026-09-30"
    run, rows = run_of(world, "rpo", {"entity_codes": [AP], **BOOK, "period_key": APR_SEPTEMBER})
    assert total(rows) == AP_SEPTEMBER
    assert run["control_totals"]["as_of"] == "2026-09-30"
    # No key, two calendars: each entity's own September.
    run, rows = run_of(world, "rpo", {"entity_codes": BOTH, **BOOK})
    assert total(rows) == US_SEPTEMBER + AP_SEPTEMBER == Decimal("76088.22")
    assert run["control_totals"]["as_of"] == "2026-09-30"
    assert {
        row["entity_code"]: Decimal(row["total"]["amount"])
        for row in rows
        if row["entity_code"] is not None
    } == {AVM_US: US_SEPTEMBER, AP: AP_SEPTEMBER}
    assert "period_key" not in run["parameters"]
    # A key, two entities, one calendar.
    run, rows = run_of(
        world, "rpo", {"entity_codes": [AVM_US, CA], **BOOK, "period_key": JAN_SEPTEMBER}
    )
    assert total(rows) == US_SEPTEMBER
    assert {item["code"] for item in run["entity_scope"]} == {AVM_US, CA}


def test_a_run_stored_before_the_rule_is_read_and_not_run_again(
    world: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``POST /report-runs/{id}/rerun`` copies the stored run and resolves nothing, so the rule
    is asked there as well. An entity's calendar does not change after creation (T-REF-01), so
    the run that meets it is one stored before the rule: it is made here with the check taken
    away, and holds the figure measured then. It stays readable; its rerun is refused and stores
    nothing.

    Fail-first: the rerun answered 202 and stated the same figure again."""
    with monkeypatch.context() as before_the_rule:
        before_the_rule.setattr(framework, "_calendar_errors", lambda *_: [], raising=False)
        run, rows = run_of(
            world, "rpo", {"entity_codes": BOTH, **BOOK, "period_key": JAN_SEPTEMBER}
        )
    assert total(rows) == US_SEPTEMBER
    assert run["control_totals"]["as_of"] == ["2025-12-31", "2026-09-30"]
    stored = stored_runs(world)
    again = post(world.app, f"{REPORT_RUNS}/{run['id']}/rerun", world.maya, {})
    refused(again, "the rerun of a run stored before the rule")
    assert stored_runs(world) == stored
    shown = get(world.app, f"{REPORT_RUNS}/{run['id']}", world.maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["status"] == "SUCCEEDED"
    data = get(world.app, f"{REPORT_RUNS}/{run['id']}/data", world.maya, {"limit": "200"})
    assert data.status_code == 200, data.text
    assert total(list(data.json()["items"])) == US_SEPTEMBER
