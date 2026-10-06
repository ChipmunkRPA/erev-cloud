"""frps3c-1 DB acceptance cases (design §2.1 / §10.1 / §10.4 / §10.6; Codex fa64924e D1 / D4;
-0550 / -0645 §3: authored as EXECUTABLE cases here, NOT RUN in the lane — the lane database is
absent; the integrated batch measures).

Each case: a NON-EMPTY original `contract_balances` run; a CURRENT input changed afterwards; the
bound rerun equal to the original through the REAL builder (the retained inputs, never today's
rows); a separately requested current run that shows the change; and, where the pattern calls for
it, a named refusal or a CTL-029 mismatch.

Domain limits (stated, not worked around): `contract.customer_id` is NOT NULL and a customer's
`name` is required, so the NULL-customer / NULL-name semantics have no DB witness (they are pinned
at unit level); period definitions have no edit route — the calendar witness GROWS the calendar with
`POST /calendars/{id}/generate-year`; no API route re-associates a contract's customer AND
`contract.customer_id` is outside the contract table's IM-S allow-list (`db/transitions.py`; the
trigger refuses it in every status), so the association change has no DB witness — D1 is carried by
the missing-association refusal below and the 3c-1 unit pins. A planted (incomplete / malformed)
binding is a synthetic SUCCEEDED copy of the original inserted under the tenant context (the frps3b
pattern): 0065's transition trigger refuses a `source_binding` change on a finished row, for the
owner too. No owner-connection probe here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, legal_entity, period, report_run
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import SourceBinding
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select, text
from support.db import TestDatabase
from support.reference import CALENDARS, get, patch, post
from support.worlds import (
    AVM_US,
    JOBS,
    K01,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    run_now,
)
from support.worlds import (
    report_run as run_report,
)

CODE: Final = "contract_balances"
BOOK: Final = "ASC606"
BALANCES: Final = {"entity_codes": [AVM_US], "book": BOOK, "period_key": "FY2026-P09"}
CONTRACTS: Final = "/api/v1/contracts"
CUSTOMERS: Final = "/api/v1/customers"
GROWN_YEAR: Final = 2028  # world_calendar generates 2026 and 2027; DB-05 wants an adjoining year
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


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


def _binding(world: ReportWorld, run_id: str) -> SourceBinding:
    stored = world.place.scalar(
        select(report_run.c.source_binding).where(report_run.c.id == UUID(run_id))
    )
    binding = SourceBinding.from_stored(stored)
    _prerequisite(binding is not None, "the live run persisted a source binding")
    assert binding is not None
    return binding


def _keyed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def _settled(world: ReportWorld, job_id: UUID) -> dict[str, Any]:
    """The worker's attempts until the job settles (RV-14: a refused build ends FAILED after the
    second of REPORT_RUN_RETRY's attempts); returns API-S-Job."""
    state = run_now(world, job_id)
    if state["state"] not in ("SUCCEEDED", "FAILED"):
        context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
            session.execute(_FETCHED, {"id": task_id})
        run_job(job_id, world.tenant_id, attempt=2, runtime=world.runtime)
        shown = get(world.app, f"{JOBS}/{job_id}", world.maya)
        _prerequisite(shown.status_code == 200, shown.text)
        state = dict(shown.json())
    assert state["state"] in ("SUCCEEDED", "FAILED"), state
    return state


def _rerun(world: ReportWorld, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], Any]:
    """``POST /report-runs/{id}/rerun`` settled SUCCEEDED; returns (API-S-ReportRun, rows, job)."""
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    _prerequisite(started.status_code == 202, f"rerun accepted: {started.text}")
    new_id = started.headers[REPORT_RUN_ID_HEADER]
    finished = _settled(world, UUID(str(started.json()["id"])))
    _prerequisite(finished["state"] == "SUCCEEDED", f"rerun job: {finished}")
    shown = get(world.app, f"{REPORT_RUNS}/{new_id}", world.maya)
    listed = get(world.app, f"{REPORT_RUNS}/{new_id}/data", world.maya, {"limit": "200"})
    _prerequisite(shown.status_code == 200 and listed.status_code == 200, "rerun read back")
    return dict(shown.json()), list(listed.json()["items"]), finished


def _refused_rerun(world: ReportWorld, run_id: str) -> dict[str, Any]:
    """The rerun is ACCEPTED (the binding is readable) and the worker refuses the bound read by
    name: the settled job is FAILED with the refusal as its problem."""
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    _prerequisite(started.status_code == 202, f"rerun accepted: {started.text}")
    finished = _settled(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "FAILED", finished  # the bound read refused BEFORE any figure
    return finished


def _planted_copy(world: ReportWorld, original: dict[str, Any], stored: dict[str, Any]) -> str:
    """A SUCCEEDED copy of the ORIGINAL RUN ROW carrying the planted ``stored`` binding (the frps3b
    pattern; Codex production-20260921-1035 C1): every stored column of the original is retained —
    ``output_sha256``, ``output_file_id``, ``manifest_file_id``, ``control_totals``, ``row_count``,
    ``tie_out_results``, ``ledger_heads`` — so a rerun of the copy compares against the original's
    REAL output identity (CTL-029 PASS / FAIL, never NOT_APPLICABLE ORIGINAL_WITHOUT_OUTPUT); only
    the id, the run number, the job link and the binding differ. A finished row's binding cannot be
    changed in place (0065's transition trigger): the planted form is a new row; returns its id."""
    (model,) = world.place.rows(
        select(report_run).where(report_run.c.id == UUID(str(original["id"])))
    )
    digest = hashlib.sha256(json.dumps(stored, sort_keys=True, default=str).encode()).hexdigest()
    row = {
        **model,
        "id": new_id(),
        "report_run_no": f"RPT-S{str(model['report_run_no'])[-5:]}{digest[:6]}",
        "job_id": None,
        "source_binding": stored,
    }
    with world.place.uow() as uow:
        uow.session.execute(insert(report_run).values(**row))
        uow.commit()
    return str(row["id"])


def _k01_customer_id(world: ReportWorld) -> str:
    booked = world.contracts[K01]
    shown = get(world.app, f"{CONTRACTS}/{booked.contract['id']}", world.maya)
    _prerequisite(shown.status_code == 200, shown.text)
    return str(shown.json()["customer"]["id"])  # API-S-Contract customer ref


# --- family 1: consumed configuration ------------------------------------------------------------


def test_the_retained_entity_row_is_frozen_by_design_and_equal_on_a_bound_rerun(
    world: ReportWorld,
) -> None:
    """DOMAIN LIMIT (batch #6 return, root cause from source): the retained entity fields are
    `code`, `calendar_id`, `functional_currency`, `time_zone` (tie_outs._ENTITY_FIELDS) — the API
    freezes code and calendar, and DB-05 `tg_legal_entity__frozen` (CTR-3 migration 0040:333–:346,
    EREV-REF-001) freezes functional_currency and time_zone once a subledger line of the entity
    exists. The k01 world has postings, so NO retained entity attribute can legitimately change
    after a run: the "changed current input" witness of design §10.6 cannot exist for this family
    here. The route's answer to that frozen change (a 409 problem carrying `EREV-REF-001` instead of
    the batch-#6 `http.unhandled_error` 500) is P5's kernel slice ERR-MAP-1 (D-98 141) and is
    witnessed there. What is witnessed here: the retained row equals the live row at the run, the
    bound rerun reproduces rows, totals and the retained evidence, and a current run re-records the
    same row."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    before = _binding(world, str(original["id"]))
    retained = before.evidence[tie_outs.CONFIGURATION]["entities"][str(world.entity_id)]
    live = world.place.rows(
        select(
            legal_entity.c.code,
            legal_entity.c.calendar_id,
            legal_entity.c.functional_currency,
            legal_entity.c.time_zone,
        ).where(legal_entity.c.id == world.entity_id)
    )[0]
    assert retained == {
        "code": live["code"],
        "calendar_id": str(live["calendar_id"]),
        "functional_currency": str(live["functional_currency"]).strip(),
        "time_zone": live["time_zone"],
    }
    rerun, rerun_rows, _ = _rerun(world, str(original["id"]))
    assert _keyed(rerun_rows) == _keyed(rows)
    assert rerun["control_totals"] == original["control_totals"]
    after = _binding(world, str(rerun["id"]))
    assert after.evidence[tie_outs.CONFIGURATION]["entities"][str(world.entity_id)] == retained
    current, _ = run_report(world, CODE, BALANCES)
    now = _binding(world, str(current["id"])).evidence[tie_outs.CONFIGURATION]["entities"]
    assert now[str(world.entity_id)] == retained  # frozen by design: the current row is the same


def test_a_calendar_that_grows_after_the_run_does_not_enter_a_bound_rerun(
    world: ReportWorld,
) -> None:
    """Period definitions have no edit route; `POST /calendars/{id}/generate-year` GROWS the
    calendar
    (DB-05: an adjoining year). The bound rerun reads the retained period list (same count and
    keys); a current run's binding records every period row it read, the new year included."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    binding = _binding(world, str(original["id"]))
    calendar_id = str(
        world.place.scalar(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        )
    )
    retained = binding.evidence[tie_outs.CONFIGURATION]["periods"][calendar_id]
    _prerequisite(
        all(int(item["fiscal_year"]) < GROWN_YEAR for item in retained),
        f"FY{GROWN_YEAR} not yet generated",
    )
    grown = post(
        world.app,
        f"{CALENDARS}/{calendar_id}/generate-year",
        world.maya,
        {"fiscal_year": GROWN_YEAR},
    )
    _prerequisite(grown.status_code == 200, f"calendar grown: {grown.text}")
    live_count = int(
        world.place.scalar(
            select(func.count())
            .select_from(period)
            .where(period.c.calendar_id == UUID(calendar_id))
        )
    )
    _prerequisite(live_count > len(retained), "the live calendar now holds more periods")
    rerun, rerun_rows, _ = _rerun(world, str(original["id"]))
    assert _keyed(rerun_rows) == _keyed(rows)
    after = _binding(world, str(rerun["id"])).evidence[tie_outs.CONFIGURATION]["periods"]
    assert after[calendar_id] == retained
    current, _ = run_report(world, CODE, BALANCES)
    now = _binding(world, str(current["id"])).evidence[tie_outs.CONFIGURATION]["periods"]
    assert len(now[calendar_id]) == live_count and len(now[calendar_id]) > len(retained)


# --- family 2b: the consumed customer names (D1) --------------------------------------------------


def test_a_customer_rename_after_the_run_does_not_move_a_bound_rerun(world: ReportWorld) -> None:
    """`PATCH /customers/{id}` renames K01's customer after the run: the bound rerun carries the
    bound name (`labels.customer_name`), never the live join; a current run shows the new name."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    customer_id = _k01_customer_id(world)
    bound, old_name = _binding(world, str(original["id"])).label(
        tie_outs.CUSTOMER_NAME, customer_id
    )
    _prerequisite(bound and old_name is not None, "the customer name is bound")
    row_key = next(key for key, row in _keyed(rows).items() if row.get("customer_name") == old_name)
    shown = get(world.app, f"{CUSTOMERS}/{customer_id}", world.maya)
    _prerequisite(shown.status_code == 200, shown.text)
    renamed = patch(
        world.app,
        f"{CUSTOMERS}/{customer_id}",
        world.maya,
        {"name": "Renamed After The Run"},
        if_match=shown.headers.get("etag"),
    )
    _prerequisite(renamed.status_code == 200, f"renamed: {renamed.text}")
    rerun, rerun_rows, _ = _rerun(world, str(original["id"]))
    assert _keyed(rerun_rows) == _keyed(rows)  # the bound name, never the live join
    assert _keyed(rerun_rows)[row_key]["customer_name"] == old_name
    current, current_rows = run_report(world, CODE, BALANCES)
    assert _keyed(current_rows)[row_key]["customer_name"] == "Renamed After The Run"
    assert _binding(world, str(current["id"])).label(tie_outs.CUSTOMER_NAME, customer_id) == (
        True,
        "Renamed After The Run",
    )


# --- D4: named refusals for an incomplete / malformed retained input ----------------------------


def test_a_binding_without_the_contracts_association_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    """The retained association is what a bound rerun reads (D1): a binding whose
    `evidence.customer_association` lacks K01 is refused by NAME with the contract id — never
    completed from today's `contract.customer_id`, never a later mismatch as the only detection."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    contract_id = str(world.contracts[K01].contract["id"])
    _prerequisite(
        contract_id in stored["evidence"][tie_outs.CUSTOMER_ASSOCIATION], "K01 is associated"
    )
    stored["evidence"][tie_outs.CUSTOMER_ASSOCIATION].pop(contract_id)
    planted = _planted_copy(world, original, stored)
    finished = _refused_rerun(world, planted)
    detail = str(finished["problem"]["detail"])
    assert tie_outs.CUSTOMER_ASSOCIATION in detail and contract_id in detail, detail


def test_a_malformed_configuration_container_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    """`evidence.configuration` present but not a mapping (Codex -0414 container shapes): the
    bound entity read refuses by name — never a raw TypeError, never a live read."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    stored["evidence"][tie_outs.CONFIGURATION] = 1  # a JSON-safe malformed container
    planted = _planted_copy(world, original, stored)
    finished = _refused_rerun(world, planted)
    assert f"{tie_outs.CONFIGURATION} (shape: not a mapping)" in str(finished["problem"]["detail"])


# --- CTL-029: a calculation change is detected on a same-source rerun -----------------------------


def test_a_calculation_change_shows_as_a_ctl_029_mismatch_on_a_bound_balances_rerun(
    world: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rerun is COMPUTED from the retained inputs and bound rows, never a replay: a changed
    calculation (here the customer-name helper the balance rows carry) gives a different rebuilt
    hash, CTL-029 records the output mismatch, and the retained evidence is unchanged.

    STALE TEST WORLD (supervisor ruling R-16, 2026-09-29; ENGINE_SPEC_B S15-R-07a): the changed
    helper used to be the consumed entity code. That code is a component of the engine's subject
    key of the member's balance nodes; a changed code found no node, and the rows were rebuilt
    from the version's latest stored figures — the silent fallback R-16 removes. Today such a read
    is refused by name (the next test), which is no CTL-029 comparison; the mismatch is therefore
    witnessed with a change the read still computes."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    genuine = tie_outs._customer_name

    def changed(params: Any, row: Mapping[str, Any]) -> str | None:
        name = genuine(params, row)
        return None if name is None else f"{name} V2"

    monkeypatch.setattr(tie_outs, "_customer_name", changed)
    rerun, rerun_rows, finished = _rerun(world, str(original["id"]))
    assert finished["result"]["output_sha256_equal"] is False  # rebuilt, not copied
    assert rerun["output"]["sha256"] != original["output"]["sha256"]
    names = [
        row["customer_name"]
        for key, row in _keyed(rerun_rows).items()
        if key.startswith("contract:")
    ]
    assert names and all(str(name).endswith(" V2") for name in names)
    assert _keyed(rerun_rows).keys() == _keyed(rows).keys()  # the same rows, another label
    assert (
        _binding(world, str(rerun["id"])).evidence == _binding(world, str(original["id"])).evidence
    )


def test_a_consumed_entity_code_that_misses_the_trace_refuses_the_rerun_by_name(
    world: ReportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENGINE_SPEC_B S15-R-07a (R-16): the consumed entity code is half of the subject key the
    member's balance nodes are read under. A code that is not the one the version was computed
    under finds no node, and the rerun is refused by name — contract, entity, contract version,
    period — instead of rebuilding its rows from the version's latest stored figures (what the
    test above did with this very change until R-16)."""
    original, rows = run_report(world, CODE, BALANCES)
    _prerequisite(bool(rows), "a non-empty original")
    genuine = tie_outs.entity_code_for

    def changed(params: Any, entity_id: UUID, live: str) -> str:
        return genuine(params, entity_id, live) + "-V2"

    monkeypatch.setattr(tie_outs, "entity_code_for", changed)
    finished = _refused_rerun(world, str(original["id"]))
    problem = finished["problem"]
    assert problem["type"].endswith("/validation-failed") and problem["status"] == 422
    (error,) = problem["errors"]
    assert (error["field"], error["rule_id"]) == (f"balances[{K01}@{AVM_US}-V2]", "S15-R-07a")
    for named in (f"Contract {K01}", f"entity {AVM_US}-V2", BALANCES["period_key"]):
        assert named in error["message"], named
