"""frps3c-2 DB witnesses for the bound subledger-line memberships (design §2.2 / §8 row 3c-2 /
§10.6; Codex production-20260921-1004 §1 R1 / R2 on 259b7db1): authored as EXECUTABLE cases, NOT
RUN in the lane — the lane database is absent; the integrated batch measures.

(a) a binding WITHOUT the membership kind (a pre-3c-2 ADAPTER binding, planted as a synthetic
SUCCEEDED copy) is refused by NAME on rerun; a binding with an explicit EMPTY membership is
admitted — the read finds nothing, nothing is missing, and the different figures show as a
CTL-029 mismatch, never a refusal (R1: absent versus empty); (b) a bound line id the read does
not return refuses the rerun by NAME with that identity (D4); (c) the opening-liability run's
membership is frozen NON-EMPTY and the bound rerun reproduces rows and membership exactly (R2:
the recorded population is the summed population). Planted bindings are synthetic SUCCEEDED
copies inserted under the tenant context (0065's transition trigger refuses a `source_binding`
change on a finished row; RLS-T is FORCED for the owner) — no owner probe.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import control_execution, job, report_run
from erev_api.domain.reports.builders import SourceBinding
from erev_api.files.store import LocalFileStore
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, text
from support.db import TestDatabase
from support.reference import get, post
from support.worlds import (
    AVM_US,
    JOBS,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    run_now,
)
from support.worlds import (
    report_run as run_report,
)

ROLLFORWARD: Final = "contract_balance_rollforward"
OPENING: Final = "revenue_from_opening_liability"
BOOK: Final = "ASC606"
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": BOOK,
    "from_period_key": "FY2026-P09",
    "to_period_key": "FY2026-P09",
}
MEMBERS: Final = "subledger_line"
# the rollforward movement columns fed by the subledger-line flows (rollforward COLUMNS)
MOVEMENTS: Final = ("billings", "revenue_from_opening", "revenue_from_period_billings")
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
    """The worker's attempts until the job settles (RV-14); returns API-S-Job."""
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
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    _prerequisite(started.status_code == 202, f"rerun accepted: {started.text}")
    finished = _settled(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "FAILED", finished  # refused by the bound read, before any figure
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


# --- (a) R1: absent versus empty ------------------------------------------------------------------


def test_a_binding_without_the_membership_kind_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    """A pre-3c-2 ADAPTER binding — `members` without `subledger_line` — refuses the same-source
    rerun by NAME (`members.subledger_line`), never a silent read that finds nothing."""
    original, rows = run_report(world, ROLLFORWARD, SEPTEMBER)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    _prerequisite(
        bool(stored["members"].get(MEMBERS)), "the live run captured a non-empty membership"
    )
    stored["members"].pop(MEMBERS)
    finished = _refused_rerun(world, _planted_copy(world, original, stored))
    assert f"members.{MEMBERS}" in str(finished["problem"]["detail"])


def test_a_captured_empty_membership_is_admitted_and_shows_as_a_ctl_029_mismatch(
    world: ReportWorld,
) -> None:
    """An explicit EMPTY membership is a captured population: the bound read finds nothing, nothing
    is missing, the rerun SUCCEEDS — and its movement-free rows differ from the original, which
    CTL-029 records as an OUTPUT mismatch (hash flag False); the control totals stay equal because
    they are the opening / closing balances of the bound versions (never completed from today's
    rows)."""
    original, rows = run_report(world, ROLLFORWARD, SEPTEMBER)
    _prerequisite(bool(rows), "a non-empty original")
    _prerequisite(
        any(row.get(name) not in ("0.00", None) for row in rows for name in MOVEMENTS),
        "the original carries a non-zero movement",
    )
    stored = _binding(world, str(original["id"])).to_stored()
    stored["members"][MEMBERS] = []
    planted = _planted_copy(world, original, stored)
    rerun, rerun_rows, finished = _rerun(world, planted)
    assert _binding(world, str(rerun["id"])).member_ids(MEMBERS) == ()
    # Codex 1035 C1: the planted parent carries the original's REAL output identity, so CTL-029
    # compares and records the mismatch — FAIL, population 1, one exception on the HASH flag
    # (False) — never NOT_APPLICABLE / ORIGINAL_WITHOUT_OUTPUT. The totals flag is TRUE by design
    # (batch #6 return, root cause from source): the rollforward's control totals are the OPENING /
    # CLOSING balances `rollforwards()` reads through `tie_outs.balances_at` over the BOUND
    # versions (contract_balance_rollforward.py:204–:217); the empty membership empties only the
    # movement lines between them, so the bytes differ while the totals are equal.
    assert finished["result"]["output_sha256_equal"] is False
    assert rerun["output"]["sha256"] != original["output"]["sha256"]
    (fact,) = world.place.rows(
        select(control_execution).where(
            control_execution.c.control_id == "CTL-029",
            control_execution.c.run_ref_type == "REPORT_RUN",
            control_execution.c.run_ref_id == UUID(str(rerun["id"])),
        )
    )
    result = getattr(fact["result"], "value", fact["result"])
    assert (str(result), fact["population_count"], fact["exception_count"]) == ("FAIL", 1, 1)
    assert fact["detail"]["output_sha256_equal"] is False and "reason" not in fact["detail"]
    assert fact["detail"]["control_totals_equal"] is True  # opening / closing: bound versions
    assert fact["detail"]["original"]["control_totals"] == original["control_totals"]
    assert fact["detail"]["rerun"]["control_totals"] == original["control_totals"]
    assert fact["detail"]["original"]["output_sha256"] == original["output"]["sha256"]


# --- (b) D4: a bound line the read does not return ---------------------------------------------


def test_a_bound_line_the_read_does_not_return_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    original, rows = run_report(world, ROLLFORWARD, SEPTEMBER)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    phantom = str(uuid4())
    stored["members"][MEMBERS] = sorted([*stored["members"][MEMBERS], phantom])
    finished = _refused_rerun(world, _planted_copy(world, original, stored))
    detail = str(finished["problem"]["detail"])
    assert f"members.{MEMBERS}" in detail and phantom in detail


# --- (c) R2: the opening-liability membership is the summed population ----------------------------


def test_the_opening_liability_membership_is_frozen_non_empty_and_reproduced_on_rerun(
    world: ReportWorld,
) -> None:
    """The ids recorded and the amounts summed come from one statement: the live run's membership
    is non-empty; the bound rerun re-reads exactly those lines, reproduces every row and records
    the same membership (CTL-029 equal on hash and totals)."""
    original, rows = run_report(world, OPENING, SEPTEMBER)
    _prerequisite(bool(rows), "a non-empty original")
    members = _binding(world, str(original["id"])).member_ids(MEMBERS)
    assert members  # the summed population was captured, not left absent
    rerun, rerun_rows, finished = _rerun(world, str(original["id"]))
    assert _keyed(rerun_rows) == _keyed(rows)
    assert _binding(world, str(rerun["id"])).member_ids(MEMBERS) == members
    assert finished["result"]["output_sha256_equal"] is True
    assert finished["result"]["control_totals_equal"] is True


# --- ruling R-72 (a): the billing events are bound members (ENGINE_SPEC_B S15-R-03a) --------------

EVENTS: Final = "contract_event"
JANUARY: Final = {**SEPTEMBER, "from_period_key": "FY2026-P01", "to_period_key": "FY2026-P01"}


def _liability(rows: list[dict[str, Any]], line: str) -> str:
    return str(_keyed(rows)[line]["contract_liability"]["amount"])


def test_the_billing_events_are_bound_members_and_reproduced_on_rerun(world: ReportWorld) -> None:
    """S15-R-03a with S15-R-24: a rollforward whose period holds billing that posted no line
    records the billing events it read as ``members.contract_event`` — K-01's two invoices, the
    stream S10-R-07 identifies the kept lines over — and the bound rerun re-reads exactly those,
    reproduces every row and records the same membership (CTL-029 equal on hash and totals). A
    period without such billing records the captured EMPTY membership, never an absent kind."""
    original, rows = run_report(world, ROLLFORWARD, JANUARY)
    _prerequisite(_liability(rows, "BILLINGS") == "120000.00", "January states INV-US-1001")
    events = _binding(world, str(original["id"])).member_ids(EVENTS)
    assert len(events) == 2  # INV-US-1001 and INV-US-1044
    rerun, rerun_rows, finished = _rerun(world, str(original["id"]))
    assert _keyed(rerun_rows) == _keyed(rows)
    assert _binding(world, str(rerun["id"])).member_ids(EVENTS) == events
    assert finished["result"]["output_sha256_equal"] is True
    assert finished["result"]["control_totals_equal"] is True
    september, _ = run_report(world, ROLLFORWARD, SEPTEMBER)
    stored = _binding(world, str(september["id"])).to_stored()
    assert stored["members"][EVENTS] == []  # no billing to explain in September


def test_a_binding_without_the_billing_events_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    """A binding recorded before ruling R-72 — ``members`` without ``contract_event`` — refuses the
    same-source rerun by NAME (``members.contract_event``): the rerun never reads today's events
    in their place and never states the billing as unexplained (R1: absent versus empty)."""
    original, rows = run_report(world, ROLLFORWARD, JANUARY)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    _prerequisite(bool(stored["members"].get(EVENTS)), "the live run captured the billing events")
    stored["members"].pop(EVENTS)
    finished = _refused_rerun(world, _planted_copy(world, original, stored))
    assert f"members.{EVENTS}" in str(finished["problem"]["detail"])


def test_a_bound_billing_event_the_read_does_not_return_refuses_the_rerun_by_name(
    world: ReportWorld,
) -> None:
    """D4 for the billing events: a bound event id the read does not return refuses the rerun by
    NAME with that identity."""
    original, rows = run_report(world, ROLLFORWARD, JANUARY)
    _prerequisite(bool(rows), "a non-empty original")
    stored = _binding(world, str(original["id"])).to_stored()
    phantom = str(uuid4())
    stored["members"][EVENTS] = sorted([*stored["members"][EVENTS], phantom])
    finished = _refused_rerun(world, _planted_copy(world, original, stored))
    detail = str(finished["problem"]["detail"])
    assert f"members.{EVENTS}" in detail and phantom in detail
