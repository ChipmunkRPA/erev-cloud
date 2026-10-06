"""frps3b — CUTOFF-R1 consumed-source binding at the REAL boundaries (record §44; 04 T-RPT-02
``source_binding`` rev 1.55; ENGINE_SPEC_B S15-R-24; Codex 2131 / design note 20b9a42f…).
DB-bound: written for the lane's ``erev_rv_l17_test`` and recorded **not run — databases not
provisioned**; it runs in an admitted database stage (the integrated batch's ``ci`` stage collects
this directory). A result exists only when that execution retains it.

The STORED original output (``GET /report-runs/{id}/data``), the actual rerun (``POST
/report-runs/{id}/rerun`` → worker → data) and the REGISTERED explain route (``GET
/explain/report-runs/{id}/cell``; RPO and revenue_waterfall are the registered explainers) are
compared on row keys, version ids and amounts — amounts alone are insufficient:

(a) deferred computation below the cutoff: an event admitted before the stamp is computed AFTER
    the original run, so the new version's ``known_at`` (the greatest event ``recorded_at``) is
    still below the fixed cutoff — a fresh "latest" query at the same cutoff would select it; the
    bound rerun and the explanation do not;
(b) a later eligible version (event and computation after the run) on the record basis;
(c) a customer-segment A → B edit after an RPO CUSTOMER_SEGMENT run: the saved row key stays
    ``customer_segment:A`` in the rerun and the explanation, ``customer_segment:B`` is refused as
    a row the original did not hold, and a separately requested current run shows B;
(d) a live run without a binding (created before the revision) is refused by name on rerun (409)
    and on explanation (404); authorization on every route is unchanged (403 without
    ``report.run``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_version, engine_release, report_run
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import SourceBinding
from erev_api.domain.reports.outputs import utc_text
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.money import MoneyIn
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.api_clients import access_approver
from support.db import TestDatabase
from support.factories import appended, computed
from support.principals import colleague, sign_in, step_up, workspace
from support.reference import approve, get, patch, post
from support.rows import report_run_values
from support.worlds import (
    AVM_US,
    K01,
    REPORT_RUN_ID_HEADER,
    REPORT_RUNS,
    ReportWorld,
    k01_pellworth,
    recalculated_journal,
    resigned,
    run_now,
)
from support.worlds import (
    journal_run as run_journal,
)
from support.worlds import (
    report_run as run_report,
)

RPO: Final = "rpo"
WATERFALL: Final = "revenue_waterfall"
BOOK: Final = "ASC606"
RPO_BY_SEGMENT: Final = {
    "entity_codes": [AVM_US],
    "book": BOOK,
    "period_key": "FY2026-P09",
    "row_dimension": "CUSTOMER_SEGMENT",
}
RPO_BY_CONTRACT: Final = {**RPO_BY_SEGMENT, "row_dimension": "CONTRACT"}
WATERFALL_PARAMS: Final = {
    "entity_codes": [AVM_US],
    "book": BOOK,
    "from_period_key": "FY2026-P01",
    "to_period_key": "FY2026-P09",
}
CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"


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


def _stream_head(world: ReportWorld, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _versions(world: ReportWorld, group_id: UUID) -> list[dict[str, Any]]:
    return world.place.rows(
        select(contract_version.c.id, contract_version.c.version_no, contract_version.c.known_at)
        .where(
            contract_version.c.combination_group_id == group_id,
            contract_version.c.book_code == BOOK,
        )
        .order_by(contract_version.c.version_no)
    )


def _billing(day: date, invoice: str) -> EventIn:
    return EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=day,
        payload=BillingRecordedV1(
            invoice_number=invoice,
            line_external_id=f"{invoice}-1",
            obligation_key="O1",
            amount=MoneyIn(amount="5000.00", currency="USD"),
            issue_date=day,
        ),
    )


def _rerun(world: ReportWorld, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    _prerequisite(started.status_code == 202, f"rerun accepted: {started.text}")
    new_id = started.headers[REPORT_RUN_ID_HEADER]
    finished = run_now(world, UUID(str(started.json()["id"])))
    _prerequisite(finished["state"] == "SUCCEEDED", f"rerun job: {finished}")
    shown = get(world.app, f"{REPORT_RUNS}/{new_id}", world.maya)
    listed = get(world.app, f"{REPORT_RUNS}/{new_id}/data", world.maya, {"limit": "200"})
    _prerequisite(shown.status_code == 200 and listed.status_code == 200, "rerun read back")
    return dict(shown.json()), list(listed.json()["items"])


def _cell(world: ReportWorld, run_id: str, row_key: str, column_key: str) -> Any:
    return get(
        world.app,
        CELL.format(run_id=run_id),
        world.maya,
        {"row_key": row_key, "column_key": column_key},
    )


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


def _money(cell: Any) -> str:
    return str(cell["amount"]) if isinstance(cell, dict) else str(cell)


# --- (a) deferred computation below the cutoff ----------------------------------------------------


def test_a_deferred_computation_below_the_cutoff_does_not_enter_a_bound_rerun_or_explanation(
    world: ReportWorld, clock: FrozenClock
) -> None:
    booked = world.contracts[K01]
    contract_id, group_id = (
        UUID(str(booked.contract["id"])),
        UUID(str(booked.combination_group["id"])),
    )
    # An event ADMITTED now (recorded at the server clock), not yet computed.
    appended(
        world.place,
        contract_id,
        _stream_head(world, contract_id),
        [_billing(date(2026, 9, 15), "INV-US-1098")],
    )
    stamp = world.place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime)
    clock.set(stamp + timedelta(seconds=1))  # the record-time clock: the stamp is admissible
    world = resigned(world)  # the jump (+ days) would end every session at the 12-hour limit
    before = _versions(world, group_id)
    original, rows = run_report(world, RPO, {**RPO_BY_CONTRACT, "known_at": utc_text(stamp)})
    binding = _binding(world, str(original["id"]))
    _prerequisite(binding.cutoff == stamp, "the historical basis kept the stamp as the cutoff")
    # Codex 2216 (A) / 2245 (a): the STORED cutoff is the exact server stamp to the microsecond —
    # the stored text carries the fraction and the restored instant equals the stamp exactly.
    _prerequisite(stamp.microsecond != 0, "a fractional server stamp (the witness needs one)")
    stored_cutoff = world.place.scalar(
        select(report_run.c.source_binding["cutoff"].astext).where(
            report_run.c.id == UUID(str(original["id"]))
        )
    )
    assert stored_cutoff == utc_text(stamp) and stored_cutoff.endswith("Z")
    assert f".{stamp.microsecond:06d}" in stored_cutoff
    assert binding.cutoff == stamp and binding.cutoff.microsecond == stamp.microsecond
    assert binding.cutoff != stamp.replace(microsecond=0)  # never the truncated boundary
    _prerequisite(
        set(binding.version_ids(BOOK)) == {UUID(str(v["id"])) for v in before},
        "bound versions = the versions consumed",
    )
    row_key = f"contract:{K01}"
    original_total = _money(_keyed(rows)[row_key]["total"])
    original_cell = _cell(world, str(original["id"]), row_key, "total")
    _prerequisite(original_cell.status_code == 200, original_cell.text)
    # The deferred computation: a higher version whose known_at is the admitted event's recorded_at
    # — BELOW the stamp — so a fresh "latest" query at the same cutoff would select it.
    computed(world.place, group_id)
    after = _versions(world, group_id)
    _prerequisite(
        len(after) == len(before) + 1 and after[-1]["known_at"] <= stamp,
        "deferred version below the cutoff",
    )
    with world.place.uow() as uow:
        fresh = set(
            uow.session.execute(
                tie_outs.latest_versions(uow.session, book_code=BOOK, cutoff=stamp)
            ).scalars()
        )
    assert UUID(str(after[-1]["id"])) in fresh  # the witness: today's latest differs from the bound
    assert UUID(str(after[-1]["id"])) not in binding.version_ids(BOOK)
    rerun, rerun_rows = _rerun(world, str(original["id"]))
    assert rerun["sources"]["bound"] is True and _binding(world, str(rerun["id"])) == binding
    assert _keyed(rerun_rows).keys() == _keyed(rows).keys()
    assert _money(_keyed(rerun_rows)[row_key]["total"]) == original_total
    assert rerun["control_totals"] == original["control_totals"]
    explained = _cell(world, str(original["id"]), row_key, "total")
    assert explained.status_code == 200, explained.text
    assert explained.json()["value"] == original_cell.json()["value"]
    assert {c["id"] for c in explained.json()["contributors"]["items"]} == {
        c["id"] for c in original_cell.json()["contributors"]["items"]
    }


# --- (b) a later eligible version, record basis, revenue_waterfall --------------------------------


def test_a_later_eligible_version_does_not_enter_a_bound_waterfall_rerun_or_explanation(
    world: ReportWorld,
) -> None:
    booked = world.contracts[K01]
    contract_id, group_id = (
        UUID(str(booked.contract["id"])),
        UUID(str(booked.combination_group["id"])),
    )
    original, rows = run_report(world, WATERFALL, WATERFALL_PARAMS)  # record basis
    binding = _binding(world, str(original["id"]))
    row_key = f"contract:{K01}"
    _prerequisite(row_key in _keyed(rows), "the waterfall holds the contract row")
    original_cell = _cell(world, str(original["id"]), row_key, "total")
    _prerequisite(original_cell.status_code == 200, original_cell.text)
    appended(
        world.place,
        contract_id,
        _stream_head(world, contract_id),
        [_billing(date(2026, 9, 16), "INV-US-1099")],
    )
    computed(world.place, group_id)
    later = _versions(world, group_id)[-1]
    assert UUID(str(later["id"])) not in binding.version_ids(BOOK)
    rerun, rerun_rows = _rerun(world, str(original["id"]))
    assert _binding(world, str(rerun["id"])) == binding
    assert _keyed(rerun_rows) == _keyed(rows)  # rows, keys and amounts as saved
    assert rerun["control_totals"] == original["control_totals"]
    explained = _cell(world, str(original["id"]), row_key, "total")
    assert explained.status_code == 200 and explained.json() == original_cell.json()
    # A separately requested CURRENT run may use the new population.
    current, _ = run_report(world, WATERFALL, WATERFALL_PARAMS)
    assert UUID(str(later["id"])) in _binding(world, str(current["id"])).version_ids(BOOK)


# --- (c) customer segment A → B, RPO CUSTOMER_SEGMENT ---------------------------------------------


def test_a_customer_segment_change_does_not_move_a_bound_rpo_row_or_its_explanation(
    world: ReportWorld,
) -> None:
    booked = world.contracts[K01]
    contract_shown = get(world.app, f"/api/v1/contracts/{booked.contract['id']}", world.maya)
    _prerequisite(contract_shown.status_code == 200, contract_shown.text)
    customer_id = str(contract_shown.json()["customer"]["id"])  # API-S-Contract customer ref
    shown = get(world.app, f"/api/v1/customers/{customer_id}", world.maya)
    _prerequisite(shown.status_code == 200, shown.text)
    segment_a = shown.json().get("segment") or ""
    original, rows = run_report(world, RPO, RPO_BY_SEGMENT)
    binding = _binding(world, str(original["id"]))
    key_a = f"customer_segment:{segment_a}"
    _prerequisite(key_a in _keyed(rows), f"the original holds {key_a}")
    original_cell = _cell(world, str(original["id"]), key_a, "total")
    _prerequisite(original_cell.status_code == 200, original_cell.text)
    # The admitted metadata-only change: segment A → B (versions, inputs, cutoff, totals unchanged).
    segment_b = "Enterprise-B" if segment_a != "Enterprise-B" else "Enterprise-C"
    changed = patch(
        world.app,
        f"/api/v1/customers/{customer_id}",
        world.maya,
        {"segment": segment_b, "name": "Renamed Customer (after the run)"},  # 2154 (1): name too
        if_match=shown.headers.get("etag"),
    )
    _prerequisite(changed.status_code == 200, changed.text)
    rerun, rerun_rows = _rerun(world, str(original["id"]))
    assert _binding(world, str(rerun["id"])) == binding
    assert _keyed(rerun_rows) == _keyed(rows)  # row A retained, no row B, customer_name as bound
    assert rerun["control_totals"] == original["control_totals"]
    explained_a = _cell(world, str(original["id"]), key_a, "total")
    assert explained_a.status_code == 200 and explained_a.json() == original_cell.json()
    refused_b = _cell(world, str(original["id"]), f"customer_segment:{segment_b}", "total")
    assert refused_b.status_code == 422, refused_b.text  # a row the original did not hold
    assert f"customer_segment:{segment_b}" in refused_b.text
    current, current_rows = run_report(world, RPO, RPO_BY_SEGMENT)  # a current run uses B
    assert f"customer_segment:{segment_b}" in _keyed(current_rows)
    assert key_a not in _keyed(current_rows)


# --- (d) legacy runs and authorization ------------------------------------------------------------


def test_an_unbound_live_run_is_refused_by_name_on_rerun_and_explanation(
    world: ReportWorld,
) -> None:
    release_id = world.place.scalar(select(engine_release.c.id).limit(1))
    values = report_run_values(
        world.tenant_id,
        engine_release_id=release_id,
        report_code=RPO,
        parameters={
            **RPO_BY_CONTRACT,
            "known_at": "2026-09-12T12:00:00Z",
            "known_at_basis": "historical",
        },
        entity_ids=[world.entity_id],
        book_code=BOOK,
        status="SUCCEEDED",
        row_count=0,
        control_totals={},
        tie_out_results=[],
        ledger_heads={},
        source_binding=None,  # created before source binding
    )
    with world.place.uow() as uow:
        uow.session.execute(insert(report_run).values(**values))
        uow.commit()
    run_id = str(values["id"])
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    # Codex 2315 (2): the FULL lifecycle / qualification shape of API-S-ReportRun `sources`.
    assert shown.status_code == 200 and shown.json()["sources"] == {
        "bound": False,
        "kind": framework.KIND_LEGACY,
        "strategy": "adapter",
        "cutoff": None,
        "versions": 0,
        "labels": 0,
        "members": 0,
        "rows": 0,
        "open": list(framework.SOURCE_CONTRACTS[RPO].open),
    }
    rerun = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    assert rerun.status_code == 409, rerun.text
    assert "created before source binding" in rerun.text
    explained = _cell(world, run_id, f"contract:{K01}", "total")
    assert explained.status_code == 404, explained.text
    assert "created before source binding" in explained.text
    # Authorization is unchanged on every route: an AUTHENTICATED colleague without a role (no
    # report.run grant) is refused 403 before any binding check (Codex 2315 (3): a signed-in
    # workspace actor, so the refusal is the permission denial, not an authentication failure).
    member = colleague(world.tenant_id, "nobody")
    nobody = workspace(world.app, member, sign_in(world.app, member.email))
    for response in (
        get(world.app, f"{REPORT_RUNS}/{run_id}", nobody),
        post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", nobody, {}),
        get(world.app, CELL.format(run_id=run_id), nobody, {"row_key": "x", "column_key": "total"}),
    ):
        assert response.status_code == 403, response.text


# --- (e) the non-version case: api_client_inventory (Codex 2202) ----------------------------------


def test_a_retained_inputs_rerun_rebuilds_from_evidence_while_a_current_run_reflects_the_change(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """``api_client_inventory`` reads CURRENT client fields and drops revoked clients by default;
    no contract version or label binds it. Its contract is ``retained_inputs`` (Codex 2225): the
    live build records the consumed rows, entity codes and creator names as evidence and a
    same-source rerun REBUILDS through the same logic from that evidence (no live read), so the
    output and hash are reproduced by computation; a separately requested current run re-reads
    the live rows — the admitted revoke removes the row there, not from the rebuild. Setup (Codex
    2301 F3B-TEST-SETUP-R1): the client is managed by Marcus — Tenant Admin, `api_client.manage`,
    with a fresh MFA step-up (BR-PLT-06) — with a catalogued non-approval scope; the report itself
    runs as the report actor; the revoke carries its required reason (SB-R-05). The client's
    scopes are an access grant (supervisor ruling R-38 (iii)): Ada, a second Tenant Admin,
    approves the grant before the first run, because only a client in force is revoked."""
    clock.advance(timedelta(seconds=60))  # a NEW TOTP step: the enrolment's step is not replayed
    manager = step_up(world.app, clock, world.marcus)
    created = post(
        world.app,
        "/api/v1/api-clients",
        manager,
        {"name": "Binding witness", "scopes": ["contract.read"], "is_all_entities": True},
    )
    _prerequisite(created.status_code in (200, 201), f"client created: {created.text}")
    ada = access_approver(world.app, clock, world.marcus.member, "ada")
    granted = approve(world.app, str(created.json()["approval_request_id"]), ada)
    _prerequisite(granted.status_code == 200, f"grant approved: {granted.text}")
    client_id = str(created.json()["id"])
    original, rows = run_report(world, "api_client_inventory", {})
    binding = _binding(world, str(original["id"]))
    _prerequisite(
        binding.strategy == "retained_inputs", "the inventory's contract is retained_inputs"
    )
    _prerequisite("api_client_inventory" in binding.evidence, "the consumed rows were retained")
    _prerequisite(any(r["client_id"] == created.json()["client_id"] for r in rows), "row present")
    assert original["sources"]["kind"] == "retained"
    revoked = post(
        world.app,
        f"/api/v1/api-clients/{client_id}/revoke",
        manager,
        {"reason": "Retired after the source-binding witness run."},
    )
    _prerequisite(revoked.status_code in (200, 202), f"revoke admitted: {revoked.text}")
    rerun, rerun_rows = _rerun(world, str(original["id"]))
    assert rerun["output"]["sha256"] == original["output"]["sha256"]  # rebuilt from the evidence
    assert _keyed(rerun_rows) == _keyed(rows)  # the revoked client is still a row of the rebuild
    assert rerun["control_totals"] == original["control_totals"]
    current, current_rows = run_report(world, "api_client_inventory", {})  # the current view
    assert all(r["client_id"] != created.json()["client_id"] for r in current_rows)
    assert (
        current["control_totals"]["client_count"] == original["control_totals"]["client_count"] - 1
    )


def test_a_calculation_change_shows_as_a_ctl_029_mismatch_on_a_retained_inputs_rerun(
    world: ReportWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 2225 / 2242: the same-source rerun is COMPUTED from the retained inputs, never copied
    from the saved output — so a changed calculation (here the row-key function the builder calls)
    produces a different rebuilt hash and CTL-029 records an output mismatch (totals equal); the
    original's evidence stays as it was."""
    from erev_api.domain.reports.builders import api_client_inventory

    # Codex 2315 (1): this world seeds no API client — an admissible one is created here (Marcus,
    # `api_client.manage`, fresh MFA step-up; scope `contract.read`) before the original run.
    clock.advance(timedelta(seconds=60))  # a NEW TOTP step: the enrolment's step is not replayed
    manager = step_up(world.app, clock, world.marcus)
    created = post(
        world.app,
        "/api/v1/api-clients",
        manager,
        {"name": "Calculation witness", "scopes": ["contract.read"], "is_all_entities": True},
    )
    _prerequisite(created.status_code in (200, 201), f"client created: {created.text}")
    original, rows = run_report(world, "api_client_inventory", {})
    _prerequisite(
        any(r["client_id"] == created.json()["client_id"] for r in rows), "the seeded client rows"
    )
    genuine = api_client_inventory.row_key
    monkeypatch.setattr(api_client_inventory, "row_key", lambda name: genuine(name) + ":v2")
    started = post(world.app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    _prerequisite(started.status_code == 202, f"rerun accepted: {started.text}")
    finished = run_now(world, UUID(str(started.json()["id"])))
    _prerequisite(finished["state"] == "SUCCEEDED", f"rerun job: {finished}")
    assert finished["result"]["output_sha256_equal"] is False  # rebuilt, not copied
    assert finished["result"]["control_totals_equal"] is True
    rerun = get(world.app, f"{REPORT_RUNS}/{started.headers[REPORT_RUN_ID_HEADER]}", world.maya)
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["output"]["sha256"] != original["output"]["sha256"]
    listed = get(
        world.app, f"{REPORT_RUNS}/{rerun.json()['id']}/data", world.maya, {"limit": "200"}
    )
    assert all(str(row["row_key"]).endswith(":v2") for row in listed.json()["items"])
    assert (
        _binding(world, str(rerun.json()["id"])).evidence
        == _binding(world, str(original["id"])).evidence
    )  # the retained inputs themselves are unchanged and copied


# --- (f) lifecycle: a FAILED original reruns as a NEW evaluation, never a reproduction ------------


def test_a_failed_original_without_capture_reruns_as_a_new_evaluation(
    world: ReportWorld, clock: FrozenClock
) -> None:
    """Codex 2318 (F3B-TEST-FAILED-CUTOFF-R1): the FAILED original's cutoff is chosen from THIS
    fixture's own evidence — the server clock after the world's computations, so every version the
    world persisted is eligible (their ``known_at`` is a DB-08 server stamp the FrozenClock cannot
    backdate) — and written to BOTH the authoritative ``known_at`` column and the parameter; the
    rerun (a new evaluation) applies exactly that cutoff and captures the eligible versions."""
    booked = world.contracts[K01]
    group_id = UUID(str(booked.combination_group["id"]))
    stamp = world.place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime)
    eligible = {UUID(str(v["id"])) for v in _versions(world, group_id) if v["known_at"] <= stamp}
    _prerequisite(bool(eligible), "an eligible version at the chosen cutoff (fixture evidence)")
    clock.set(stamp + timedelta(seconds=1))  # the record-time clock: the stamp is admissible
    world = resigned(world)  # the jump (+ days) would end every session at the 12-hour limit
    release_id = world.place.scalar(select(engine_release.c.id).limit(1))
    values = report_run_values(
        world.tenant_id,
        engine_release_id=release_id,
        report_code=RPO,
        parameters={
            **RPO_BY_CONTRACT,
            "known_at": utc_text(stamp),  # the parameter …
            "known_at_basis": "historical",
        },
        known_at=stamp,  # … and the authoritative column, synchronised (never the factory default)
        entity_ids=[world.entity_id],
        book_code=BOOK,
        status="FAILED",
        # a complete API-S-Problem as `run_failed` stores one (API-S-ReportRun `problem` is
        # ProblemOut: `instance` is required — batch #4 read this row with a 500 without it)
        problem={
            "type": "about:blank",
            "title": "failed before capture",
            "status": 500,
            "detail": "The build failed before its sources were captured.",
            "instance": "urn:erev:request:00000000-0000-7000-8000-000000000f01",
            "code": None,
            "errors": [],
        },
        source_binding=None,
    )
    with world.place.uow() as uow:
        uow.session.execute(insert(report_run).values(**values))
        uow.commit()
    run_id = str(values["id"])
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["sources"]["kind"] == "failed_without_capture"
    rerun, rerun_rows = _rerun(world, str(run_id))  # admitted: a new evaluation (CTL-029 N/A)
    assert rerun["sources"]["bound"] is True and rerun["sources"]["kind"] == "bound"
    captured = _binding(world, str(rerun["id"]))
    assert captured.cutoff == stamp  # the synchronised cutoff is what the new evaluation applied
    assert eligible <= set(captured.version_ids(BOOK))  # captured by the new evaluation: non-empty


# --- (g) a journal-run cancellation cannot move a bound tie-out (Codex 2154 (2)) ----------------


def test_a_later_journal_run_cancellation_does_not_move_a_bound_waterfall_tie_out(
    world: ReportWorld,
) -> None:
    """The revenue tie-out's journal-run membership is bound: cancelling an included run after the
    original changes a CURRENT run's expected side, not the bound rerun's ``tie_out_results``."""
    journal = run_journal(world)  # a non-zero revenue journal for FY2026-P09
    original, rows = run_report(world, WATERFALL, WATERFALL_PARAMS)
    binding = _binding(world, str(original["id"]))
    _prerequisite(str(journal["id"]) in binding.member_ids("journal_run"), "the run is a member")
    (tie,) = original["tie_out_results"]
    recalculated_journal(world, journal)  # cancels the draft run (and calculates again)
    rerun, _ = _rerun(world, str(original["id"]))
    assert rerun["tie_out_results"] == original["tie_out_results"]  # bound membership
    assert _binding(world, str(rerun["id"])).member_ids("journal_run") == binding.member_ids(
        "journal_run"
    )
    current, _ = run_report(world, WATERFALL, WATERFALL_PARAMS)  # a current run: new membership
    assert str(journal["id"]) not in _binding(world, str(current["id"])).member_ids("journal_run")
    assert tie["code"] == current["tie_out_results"][0]["code"]


# --- (h) implementation contract: a binding this release cannot read refuses by name ------------


def test_a_binding_this_release_cannot_read_refuses_rerun_and_explanation_by_name(
    world: ReportWorld,
) -> None:
    original, _ = run_report(world, RPO, RPO_BY_CONTRACT)
    stored = world.place.scalar(
        select(report_run.c.source_binding).where(report_run.c.id == UUID(str(original["id"])))
    )
    release_id = world.place.scalar(select(engine_release.c.id).limit(1))
    values = report_run_values(
        world.tenant_id,
        engine_release_id=release_id,
        report_code=RPO,
        parameters=dict(original["parameters"]),
        entity_ids=[world.entity_id],
        book_code=BOOK,
        status="SUCCEEDED",
        row_count=original["row_count"],
        control_totals=dict(original["control_totals"]),
        tie_out_results=[],
        ledger_heads={},
        source_binding={**dict(stored), "binding_version": 99},  # a form this release cannot read
    )
    with world.place.uow() as uow:
        uow.session.execute(insert(report_run).values(**values))
        uow.commit()
    run_id = str(values["id"])
    rerun = post(world.app, f"{REPORT_RUNS}/{run_id}/rerun", world.maya, {})
    assert rerun.status_code == 409 and "cannot read" in rerun.text, rerun.text
    explained = _cell(world, run_id, f"contract:{K01}", "total")
    assert explained.status_code == 404 and "cannot read" in explained.text, explained.text
