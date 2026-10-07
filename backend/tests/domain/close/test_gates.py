"""CLO-4 close blockers and gate evaluation (04 §16.8 API-S-Period ``blockers``, API-S-PeriodCockpit
``derived_blockers``; T-CLS-02, T-CLS-03; E-60, E-122; PRD §5.3 BR-CLS-01, J-13.1, WLD-B-01 to
WLD-B-06; SCREENS_B §1.1; 03 REQ-CLS-008, REQ-CLS-009, REQ-POL-008, REQ-DAT-010; BUILD_SPEC CLO-4,
header XR-12).

World: ``support.close_world``. Maya (Revenue Accountant) keeps AVM-US on a January calendar with
FY2026-P01 to P09 open, and ``wld_b`` writes the WLD-B shape as rows: three pending requests, two
open ``PROGRESS_OVER_DELIVERY`` items, one open ``journal_export`` hold, one open
``VC_REASSESSMENT_MISSING`` item, and no journal run or reconciliation. Maya's units of work
evaluate the gates (``support.factories.Workspace``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.tables import (
    approval_request,
    close_checklist_item,
    close_checklist_template,
    exception_item,
    file_object,
    gl_account,
    import_upload,
    integration_connection,
    judgement_record,
    legal_entity,
    period_lock,
    period_state,
    period_state_transition,
    reconciliation,
    sync_run,
)
from erev_api.domain.close import gates, monitors, queries
from erev_api.enums import ApprovalRequestStatus, ChecklistStatus, FilePurpose, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support import reconciliations as recon
from support.close_world import (
    BOOK,
    CloseWorld,
    actor_with_role,
    close_world,
    contract_of,
    earlier_periods_closed,
    identity_duplicates,
    other_entity,
    requested_journal_run,
    run_journal_job,
    sealed_activity,
    submitted_judgement,
    system_session,
    wld_b,
)
from support.db import TestDatabase
from support.principals import carrying, colleague, enrolled
from support.reference import get, periods, post
from support.rows import (
    CloseParts,
    approval_request_values,
    exception_item_values,
    file_object_values,
    gl_account_values,
    import_upload_values,
    integration_connection_values,
    period_lock_values,
    period_state_transition_values,
    reconciliation_values,
)

PERIODS = "/api/v1/periods"
EXCEPTIONS = "/api/v1/exceptions"
TOTAL_COUNT = "X-Erev-Total-Count"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _evaluated(world: CloseWorld) -> dict[str, gates.GateResult]:
    with world.place.uow() as uow:
        results = gates.evaluate_gates(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    assert [result.gate_check_code for result in results] == list(gates.GATE_CHECK_CODES)
    for result in results:
        if result.gate_check_code in gates.NEVER_WAIVABLE:
            continue
        assert result.members is not None, result.gate_check_code
        if result.count is not None:
            assert len(result.members) == result.count, result.gate_check_code
            assert len(set(result.members)) == result.count, result.gate_check_code
    return {result.gate_check_code: result for result in results}


def _outcome(result: gates.GateResult) -> tuple[str, int | None]:
    return result.status.value, result.count


@pytest.mark.parametrize("findings_named", [True, False], ids=["named", "import-level"])
def test_cockpit_blocker_counts(world: CloseWorld, findings_named: bool) -> None:
    wld_b(world, findings_named=findings_named)
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id)
        assert scope is not None
        counts = gates.blocker_counts(uow.session, scope)
        derived = gates.derived_counts(uow.session, scope, known_at=uow.now)
        requests = gates.pending_request_counts(uow.session, scope)
    # Import-level WLD-B-04 items are CONTROL_TOTALS_MISMATCH on a FAILED upload: they count as ONE
    # interface failure (per upload) and not as open exceptions (gates.py module docstring;
    # ``_open_exceptions`` excludes the code) — the named case keeps three open exceptions.
    expected = {
        "exceptions_open": 3 if findings_named else 1,
        "holds_open": 1,
        "unmapped_products": 0,
        "judgements_unreviewed": 1,
        "approvals_pending": 3,
        "interface_failures": 0 if findings_named else 1,
        "jobs_failed": 0,
        "groups_dirty": 0,
        "batches_unexported": 0,
        "batches_unacknowledged": 0,
        "reconciliations_unsigned": 0,
        "manual_adjustments_pending": 0,
    }
    assert counts == expected
    assert derived == {"JOURNAL_RUN_NOT_CALCULATED": 1, "RECONCILIATIONS_NOT_GENERATED": 2}
    # D-90a QA-L9-7: the WLD-B JUDGEMENT_RECORD and MANUAL_ADJUSTMENT requests, in that fixed order.
    assert list(requests.items()) == [("JUDGEMENT_RECORD", 1), ("MANUAL_ADJUSTMENT", 1)]

    # API-S-Period and API-S-PeriodCockpit answer the same counts (SCREENS_B §1.1 BLK-10, BLK-13).
    shown = get(world.app, f"{PERIODS}/{world.state_id}", world.maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["blockers"] == expected
    # ... and a row of the list answers no counts (04 §16.8 rev 1.199): the single read above
    # and the cockpit below do
    listed = periods(world.app, world.maya, entity="AVM-US")
    (row,) = [item for item in listed if item["id"] == str(world.state_id)]
    assert row["blockers"] is None
    cockpit = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", world.maya)
    assert cockpit.status_code == 200, cockpit.text
    assert cockpit.json()["derived_blockers"] == [
        {"code": "JOURNAL_RUN_NOT_CALCULATED", "count": 1},
        {"code": "RECONCILIATIONS_NOT_GENERATED", "count": 2},
    ]
    # SCREENS_B §1.1 KPI "Reconciliations reviewed 0 of 2" (L7-2-Q-12).
    assert cockpit.json()["kpis"]["reconciliations_reviewed"] == {"reviewed": 0, "required": 2}
    # [J] D-88 L7-2-Q-1 figure (1): the EXCEPTIONS_CLEARED gate counts exceptions_open (3 named;
    # 1 at import level, where the WLD-B-04 items are interface failures — batch #4 / #5 on main),
    # and
    # BLK-02 (exceptions_open less the BLK-03 VC_REASSESSMENT_MISSING items) shows 2 named, 0 at
    # import level.
    assert _outcome(_evaluated(world)["EXCEPTIONS_CLEARED"]) == (
        "FAILED",
        expected["exceptions_open"],
    )
    vc = get(
        world.app,
        EXCEPTIONS,
        world.maya,
        {
            "code": "VC_REASSESSMENT_MISSING",
            "entity": "AVM-US",
            "period": "FY2026-P09",
            "status": ["OPEN", "IN_PROGRESS"],
            "limit": 1,
            "count": "true",
        },
    )
    assert vc.status_code == 200, vc.text
    assert expected["exceptions_open"] - int(vc.headers[TOTAL_COUNT]) == (
        2 if findings_named else 0
    )
    # Figure (2): an INFO item and an item of another period change nothing, with or without an
    # entity.
    earliest = UUID(str(periods(world.app, world.maya, entity="AVM-US")[0]["period"]["id"]))
    with system_session(world) as session:
        for named in ({"entity_id": world.entity_id}, {}):
            for values in (
                {"severity": "INFO", "code": "COMBINATION_SUGGESTED"},
                {"period_id": earliest},
            ):
                session.execute(
                    insert(exception_item).values(
                        **exception_item_values(world.tenant_id, **named, **values)
                    )
                )
    again = get(world.app, f"{PERIODS}/{world.state_id}", world.maya)
    assert again.json()["blockers"]["exceptions_open"] == expected["exceptions_open"]


def test_exception_scope_cases(world: CloseWorld) -> None:
    """[J] D-88 L7-2-Q-1: cases (a), (b), (b2) and (c) for AVM-US and for a second entity."""
    with system_session(world) as session:
        uk = other_entity(session, world)
        us_contract, _, us_group = contract_of(session, world)
        uk_contract, _, uk_group = contract_of(session, world, uk)
        for values in (
            {"entity_id": world.entity_id},  # (a) AVM-US
            {"contract_id": us_contract},  # (b) AVM-US
            {"combination_group_id": us_group},  # (b2) AVM-US
            {"entity_id": uk},  # (a) AVM-UK
            {"contract_id": uk_contract},  # (b) AVM-UK
            {"combination_group_id": uk_group},  # (b2) AVM-UK
            {},  # (c) every entity
            {"code": "PRODUCT_UNMAPPED"},  # (c) every entity, also unmapped_products
            {"code": "CONTROL_TOTALS_MISMATCH"},  # interface failures only
        ):
            session.execute(
                insert(exception_item).values(**exception_item_values(world.tenant_id, **values))
            )
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id)
        assert scope is not None
        us_counts = gates.blocker_counts(uow.session, scope)
        uk_counts = gates.blocker_counts(
            uow.session, replace(scope, entity_id=uk, entity_code="AVM-UK")
        )
    assert (us_counts["exceptions_open"], us_counts["unmapped_products"]) == (5, 1)
    assert (uk_counts["exceptions_open"], uk_counts["unmapped_products"]) == (5, 1)


@pytest.mark.control("CTL-016")
def test_ctl_016_gate_results_name_failing_gates(world: CloseWorld) -> None:
    wld_b(world)
    results = _evaluated(world)
    assert _outcome(results["APPROVALS_CLEARED"]) == ("FAILED", 3)
    assert _outcome(results["EXCEPTIONS_CLEARED"]) == ("FAILED", 3)
    assert _outcome(results["HOLDS_REVIEWED"]) == ("FAILED", 1)
    assert _outcome(results["JUDGEMENTS_REVIEWED"]) == ("FAILED", 1)
    assert _outcome(results["JE_BALANCED"]) == ("FAILED", 1)
    assert _outcome(results["RECONCILIATIONS_GENERATED"]) == ("FAILED", 2)
    assert _outcome(results["INTERFACES_COMPLETE"]) == ("PASSED", 0)
    # SCREENS_B §1.1 failure details name each failing gate (ERR-14 gate list items).
    assert results["APPROVALS_CLEARED"].detail == "Pending approvals: 3"
    assert results["EXCEPTIONS_CLEARED"].detail == "Open exceptions: 3"
    assert results["HOLDS_REVIEWED"].detail == "Open holds: 1"
    assert results["JUDGEMENTS_REVIEWED"].detail == "Judgements not reviewed: 1"
    assert results["JE_BALANCED"].detail == "Journal run not calculated"
    assert results["RECONCILIATIONS_GENERATED"].detail == (
        "Reconciliation not generated: Billing to subledger; "
        "Reconciliation not generated: Subledger to GL"
    )
    assert results["INTERFACES_COMPLETE"].detail is None

    # The results are stored on the period's checklist items, one per system gate.
    stored = world.place.rows(
        select(
            close_checklist_template.c.gate_check_code,
            close_checklist_item.c.status,
            close_checklist_item.c.result,
        )
        .join(
            close_checklist_template,
            close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
        )
        .where(close_checklist_item.c.period_id == world.period_id)
        .order_by(close_checklist_template.c.sequence)
    )
    assert [row["gate_check_code"] for row in stored] == list(gates.GATE_CHECK_CODES)
    by_code = {row["gate_check_code"]: row for row in stored}
    assert (
        by_code["APPROVALS_CLEARED"]["status"],
        by_code["APPROVALS_CLEARED"]["result"]["count"],
    ) == (
        "FAILED",
        3,
    )
    assert by_code["INTERFACES_COMPLETE"]["status"] == "PASSED"
    # A second evaluation with nothing changed writes nothing (evaluated_at stays).
    first = by_code["APPROVALS_CLEARED"]["result"]["evaluated_at"]
    _evaluated(world)
    (after,) = world.place.rows(
        select(close_checklist_item.c.result)
        .join(
            close_checklist_template,
            close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
        )
        .where(
            close_checklist_item.c.period_id == world.period_id,
            close_checklist_template.c.gate_check_code == "APPROVALS_CLEARED",
        )
    )
    assert after["result"]["evaluated_at"] == first


def _approvals_pending(world: CloseWorld, *state_ids: UUID) -> tuple[int, ...]:
    """``blockers.approvals_pending`` of each period state, as the gate's one statement counts."""
    counted = []
    with system_session(world) as session:
        for state_id in state_ids:
            scope = gates.period_scope(session, state_id)
            assert scope is not None
            counted.append(gates.blocker_counts(session, scope)["approvals_pending"])
    return tuple(counted)


def test_the_periods_own_lock_request_is_no_pending_approval_of_it(world: CloseWorld) -> None:
    """Item CLO-LOCK-REQUEST-OWN-GATE-1 (04 §16.8 ``blockers`` rev 1.311; PRD BR-CLS-01 rev 1.205):
    ``approvals_pending`` leaves out the ``PENDING`` ``PERIOD_LOCK`` request whose subject is the
    period state asked, and no other request. Request by request, as rows, read for September
    2026 in soft close and for August, which the fixture's lock closed:

    - September's lock request: left out of September's count, counted in August's;
    - a ``PERIOD_LOCK`` request on August — on a closed period, its permanent-lock request: left
      out of August's count, counted in September's, as the request of another period state is;
    - a reopen request of August: counted in both — a reopen request is a pending approval of
      every period of the entity, its own included (04 §14.1: while it waits for its approvers
      no ``closing`` period of the entity moves to ``closed``);
    - the waiver request of September's own ``APPROVALS_CLEARED`` item, which names no entity:
      counted in August's and, since rev 1.318, left out of September's — the request that asks
      to waive the count is no part of it (item CLO-APPROVALS-WAIVER-OWN-REQUEST-1, witnessed
      below).

    The gate, the period reads and the cockpit say each period's count.

    Fail-first (on 9ec07ed02): a period counted its own lock request — September 1 with its
    request alone, where the cockpit then called the lock unavailable."""
    earlier_periods_closed(world)
    shown = {
        item["period"]["period_key"]: item
        for item in periods(world.app, world.maya, entity="AVM-US")
    }
    september, august = world.state_id, UUID(str(shown["FY2026-P08"]["id"]))
    started = post(
        world.app,
        f"{PERIODS}/{september}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["FY2026-P09"]["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    states = {
        item["period"]["period_key"]: item["state"]
        for item in periods(world.app, world.maya, entity="AVM-US")
    }
    assert (states["FY2026-P09"], states["FY2026-P08"]) == ("closing", "closed")
    assert _outcome(_evaluated(world)["APPROVALS_CLEARED"]) == ("PASSED", 0)
    (gate_item,) = world.place.rows(
        select(close_checklist_item.c.id)
        .join(
            close_checklist_template,
            close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
        )
        .where(
            close_checklist_item.c.period_id == world.period_id,
            close_checklist_template.c.gate_check_code == "APPROVALS_CLEARED",
        )
    )

    def pending(subject_type: str, subject_id: UUID, *, names_entity: bool = True) -> None:
        with system_session(world) as session:
            session.execute(
                insert(approval_request).values(
                    **approval_request_values(
                        world.tenant_id,
                        entity_id=world.entity_id if names_entity else None,
                        subject_type=subject_type,
                        subject_id=subject_id,
                        summary=f"{subject_type} of {subject_id}",
                    )
                )
            )

    assert _approvals_pending(world, september, august) == (0, 0)
    pending("PERIOD_LOCK", september)
    assert _approvals_pending(world, september, august) == (0, 1)
    pending("PERIOD_LOCK", august)
    assert _approvals_pending(world, september, august) == (1, 1)
    pending("PERIOD_REOPEN", august)
    assert _approvals_pending(world, september, august) == (2, 2)
    pending("EXCEPTION_WAIVER", UUID(str(gate_item["id"])), names_entity=False)
    assert _approvals_pending(world, september, august) == (2, 3)

    result = _evaluated(world)["APPROVALS_CLEARED"]
    assert (_outcome(result), result.detail) == (("FAILED", 2), "Pending approvals: 2")
    for state_id, counted in ((september, 2), (august, 3)):
        read = get(world.app, f"{PERIODS}/{state_id}", world.maya)
        assert read.status_code == 200, read.text
        assert read.json()["blockers"]["approvals_pending"] == counted
    cockpit = get(world.app, f"{PERIODS}/{september}/cockpit", world.maya)
    assert cockpit.status_code == 200, cockpit.text
    assert cockpit.json()["period"]["blockers"]["approvals_pending"] == 2


def test_the_approvals_gates_own_waiver_request_is_no_pending_approval_of_its_period(
    world: CloseWorld,
) -> None:
    """Item CLO-APPROVALS-WAIVER-OWN-REQUEST-1 (04 §16.8 ``blockers`` rev 1.318; PRD BR-CLS-01 rev
    1.206): ``approvals_pending`` leaves out the ``PENDING`` ``EXCEPTION_WAIVER`` request whose
    subject is the period's own ``APPROVALS_CLEARED`` item, and no other waiver request — by the
    type, the subject and the item's gate. Request by request, as rows that name no entity, read
    for September 2026 in soft close and for August:

    - the waiver request of September's ``APPROVALS_CLEARED`` item: left out of September's
      count; counted in August's — for August it is another period's;
    - the waiver request of September's ``EXCEPTIONS_CLEARED`` item, another gate's: counted in
      both;
    - the waiver request of an exception item of the entity — the same type on a subject that
      is no checklist item: counted in both.

    The gate says September's count and its sentence: what a waiver of the gate would state.

    Fail-first (on 6e04bc69d): September counted the waiver request of its own approvals gate —
    1 with that request alone — so a waiver changed the count it asked to waive."""
    earlier_periods_closed(world)
    shown = {
        item["period"]["period_key"]: item
        for item in periods(world.app, world.maya, entity="AVM-US")
    }
    september, august = world.state_id, UUID(str(shown["FY2026-P08"]["id"]))
    started = post(
        world.app,
        f"{PERIODS}/{september}/start-close",
        world.maya,
        {"comment": "September close in progress"},
        if_match=f'"r{shown["FY2026-P09"]["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    assert _outcome(_evaluated(world)["APPROVALS_CLEARED"]) == ("PASSED", 0)
    items = {
        row["gate_check_code"]: UUID(str(row["id"]))
        for row in world.place.rows(
            select(close_checklist_template.c.gate_check_code, close_checklist_item.c.id)
            .join(
                close_checklist_template,
                close_checklist_template.c.id == close_checklist_item.c.close_checklist_template_id,
            )
            .where(
                close_checklist_item.c.period_id == world.period_id,
                close_checklist_template.c.gate_check_code.in_(
                    ("APPROVALS_CLEARED", "EXCEPTIONS_CLEARED")
                ),
            )
        )
    }
    finding = exception_item_values(world.tenant_id, entity_id=world.entity_id)
    with system_session(world) as session:
        session.execute(insert(exception_item).values(**finding))

    def waiver_asked(subject_id: UUID) -> None:
        with system_session(world) as session:
            session.execute(
                insert(approval_request).values(
                    **approval_request_values(
                        world.tenant_id,
                        subject_type="EXCEPTION_WAIVER",
                        subject_id=subject_id,
                        summary=f"Waive {subject_id}",
                    )
                )
            )

    assert _approvals_pending(world, september, august) == (0, 0)
    waiver_asked(items["APPROVALS_CLEARED"])
    assert _approvals_pending(world, september, august) == (0, 1)
    waiver_asked(items["EXCEPTIONS_CLEARED"])
    assert _approvals_pending(world, september, august) == (1, 2)
    waiver_asked(UUID(str(finding["id"])))
    assert _approvals_pending(world, september, august) == (2, 3)

    result = _evaluated(world)["APPROVALS_CLEARED"]
    assert (_outcome(result), result.detail) == (("FAILED", 2), "Pending approvals: 2")


@pytest.mark.control("CTL-002")
def test_ctl_002_failed_interface_run_fails_gate(world: CloseWorld) -> None:
    assert _outcome(_evaluated(world)["INTERFACES_COMPLETE"]) == ("PASSED", 0)
    with system_session(world) as session:
        stored_file = file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
        session.execute(insert(file_object).values(**stored_file))
        upload = import_upload_values(world.tenant_id, file_object_id=stored_file["id"])
        session.execute(insert(import_upload).values(**upload))
        for status in ("VALIDATING", "VALIDATED", "DIFFING", "DIFF_READY", "SUBMITTED", "APPROVED"):
            session.execute(
                update(import_upload)
                .where(import_upload.c.id == upload["id"])
                .values(status=status, updated_by_kind="SYSTEM")
            )
        session.execute(
            update(import_upload)
            .where(import_upload.c.id == upload["id"])
            .values(status="COMMITTING", updated_by_kind="SYSTEM")
        )
        session.execute(
            update(import_upload)
            .where(import_upload.c.id == upload["id"])
            .values(status="FAILED", updated_by_kind="SYSTEM")
        )
        mismatch = exception_item_values(
            world.tenant_id,
            source="IMPORT",
            code="CONTROL_TOTALS_MISMATCH",
            title="Control totals do not match",
            import_upload_id=upload["id"],
        )
        session.execute(insert(exception_item).values(**mismatch))
    results = _evaluated(world)
    failed = results["INTERFACES_COMPLETE"]
    assert _outcome(failed) == ("FAILED", 1)
    assert failed.detail == "Interface batch not complete: File imports (1 runs)"
    # [J] D-88 L7-2-Q-1 figure (3): the mismatch item names no entity, contract or group, and it
    # counts only in interface_failures.
    assert _outcome(results["EXCEPTIONS_CLEARED"]) == ("PASSED", 0)
    blockers = get(world.app, f"{PERIODS}/{world.state_id}", world.maya).json()["blockers"]
    assert (blockers["exceptions_open"], blockers["interface_failures"]) == (0, 1)
    # Dismissing the mismatch item clears the gate.
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == mismatch["id"])
            .values(status="DISMISSED", resolution="Superseded.", updated_by_kind="SYSTEM")
        )
    assert _outcome(_evaluated(world)["INTERFACES_COMPLETE"]) == ("PASSED", 0)


def _sync_run(
    session: Any,
    world: CloseWorld,
    connection_id: UUID,
    status: str,
    *,
    kind: str = "INBOUND_POLL",
    checkpoint: dict[str, Any] | None = None,
) -> UUID:
    """One finished T-INT-02 run of the connection, recorded as the sync job and the probe record
    theirs (``created_at`` is the database clock, so a later insert is a later run)."""
    run_id = new_id()
    session.execute(
        insert(sync_run).values(
            tenant_id=world.tenant_id,
            id=run_id,
            integration_connection_id=connection_id,
            kind=kind,
            status=status,
            checkpoint_before={} if checkpoint is None else checkpoint,
            created_by_kind="SYSTEM",
            updated_by_kind="SYSTEM",
        )
    )
    return run_id


def _run_item(session: Any, world: CloseWorld, run_id: UUID, *, code: str) -> UUID:
    """One OPEN failure item of the run in the exception queue (``exception_item.sync_run_id``)."""
    item = exception_item_values(
        world.tenant_id,
        source="SYNC",
        code=code,
        title="Interface run failure",
        sync_run_id=run_id,
        dedupe_key=f"SYNC:{code}:{run_id}",
    )
    session.execute(insert(exception_item).values(**item))
    return UUID(str(item["id"]))


def _interfaces(world: CloseWorld) -> tuple[str, int | None, str | None]:
    result = _evaluated(world)["INTERFACES_COMPLETE"]
    return result.status.value, result.count, result.detail


@pytest.mark.control("CTL-002")
def test_ctl_002_failed_sync_runs_hold_the_gate_until_cleared(world: CloseWorld) -> None:
    """CLO-GATE-SYNC-1 (supervisor rulings R-45 (d) and R-56 (a); CTL-002; BR-INT-03; REQ-DAT-010;
    SCREENS_B BLK-07): the interface gate counts, for the period's entity, the sync runs that
    ended FAILED or CONTROL_TOTAL_MISMATCH. A run stops counting when a later run of the same
    connection and kind SUCCEEDED over the same window (a poll from the same checkpoint; a sweep
    or a chart sync that ran to completion; never a webhook batch, an export or a trial-balance
    pull), or when it has failure items in the exception queue and none is still open. Until this
    item the gate read failed file imports only, so a period locked over a control-total mismatch
    of a connection."""
    passed = ("PASSED", 0, None)
    assert _interfaces(world) == passed
    with system_session(world) as session:
        uk = other_entity(session, world)
        shared = integration_connection_values(world.tenant_id, name="Salesforce (orders)")
        foreign = integration_connection_values(
            world.tenant_id, name="Stripe (UK)", adapter="STRIPE", entity_ids=[uk]
        )
        session.execute(insert(integration_connection).values(**shared))
        session.execute(insert(integration_connection).values(**foreign))
        connection_id, foreign_id = UUID(str(shared["id"])), UUID(str(foreign["id"]))
        # Runs that never hold the gate: a succeeded poll, a run still in progress, a failed
        # connection test (no batch, no control totals) and a failed run of a connection that
        # serves another entity only.
        _sync_run(session, world, connection_id, "SUCCEEDED", checkpoint={"replay_id": 5})
        _sync_run(session, world, connection_id, "RUNNING", checkpoint={"replay_id": 6})
        _sync_run(session, world, connection_id, "FAILED", kind="TEST_CONNECTION")
        _sync_run(session, world, foreign_id, "FAILED", checkpoint={"cursor": "evt_1"})
    assert _interfaces(world) == passed

    # A control-total mismatch (BR-INT-03) holds the gate, named by its connection.
    with system_session(world) as session:
        mismatch_run = _sync_run(
            session, world, connection_id, "CONTROL_TOTAL_MISMATCH", checkpoint={"replay_id": 10}
        )
        mismatch_item = _run_item(session, world, mismatch_run, code="CONTROL_TOTALS_MISMATCH")
    one = ("FAILED", 1, "Interface batch not complete: Salesforce (orders) (1 runs)")
    assert _interfaces(world) == one
    blockers = get(world.app, f"{PERIODS}/{world.state_id}", world.maya).json()["blockers"]
    assert (blockers["exceptions_open"], blockers["interface_failures"]) == (0, 1)

    # A failed poll without any failure item is cleared only by a later run over its window.
    with system_session(world) as session:
        failed_run = _sync_run(
            session, world, connection_id, "FAILED", checkpoint={"replay_id": 20}
        )
    two = ("FAILED", 2, "Interface batch not complete: Salesforce (orders) (2 runs)")
    assert _interfaces(world) == two
    with system_session(world) as session:
        # Not the same window, not the same kind, not succeeded, another connection: no clearing.
        _sync_run(session, world, connection_id, "SUCCEEDED", checkpoint={"replay_id": 21})
        _sync_run(
            session,
            world,
            connection_id,
            "SUCCEEDED",
            kind="RECONCILIATION_SWEEP",
            checkpoint={"replay_id": 20},
        )
        _sync_run(session, world, connection_id, "RUNNING", checkpoint={"replay_id": 20})
        _sync_run(session, world, foreign_id, "SUCCEEDED", checkpoint={"replay_id": 20})
    assert _interfaces(world) == two
    with system_session(world) as session:
        _sync_run(session, world, connection_id, "SUCCEEDED", checkpoint={"replay_id": 20})
    assert _interfaces(world) == one
    assert failed_run != mismatch_run

    # A sweep and a chart sync read the whole set: a later run of the kind clears the failed one,
    # whatever its checkpoint; a trial-balance pull has no window and no later pull clears it.
    with system_session(world) as session:
        _sync_run(
            session,
            world,
            connection_id,
            "FAILED",
            kind="RECONCILIATION_SWEEP",
            checkpoint={"replay_id": 30},
        )
        _sync_run(session, world, connection_id, "FAILED", kind="COA_SYNC")
        pull = _sync_run(session, world, connection_id, "FAILED", kind="TRIAL_BALANCE_PULL")
    assert _interfaces(world)[:2] == ("FAILED", 4)
    with system_session(world) as session:
        _sync_run(
            session,
            world,
            connection_id,
            "SUCCEEDED",
            kind="RECONCILIATION_SWEEP",
            checkpoint={"replay_id": 44},
        )
        _sync_run(session, world, connection_id, "SUCCEEDED", kind="COA_SYNC")
        _sync_run(session, world, connection_id, "SUCCEEDED", kind="TRIAL_BALANCE_PULL")
    assert _interfaces(world) == two  # the mismatch and the pull
    with system_session(world) as session:
        pull_item = _run_item(session, world, pull, code="ACCOUNT_MAPPING_MISSING")
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == pull_item)
            .values(status="RESOLVED", resolution="Account mapped.", updated_by_kind="SYSTEM")
        )
    assert _interfaces(world) == one

    # A webhook batch moves no checkpoint: a later batch never clears it, its failure items do.
    with system_session(world) as session:
        webhook_run = _sync_run(
            session, world, connection_id, "FAILED", kind="WEBHOOK_BATCH", checkpoint={}
        )
        _sync_run(session, world, connection_id, "SUCCEEDED", kind="WEBHOOK_BATCH", checkpoint={})
    assert _interfaces(world) == two
    with system_session(world) as session:
        first = _run_item(session, world, webhook_run, code="PRODUCT_UNMAPPED")
        second = _run_item(session, world, webhook_run, code="STALE_SOURCE_VERSION")
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == first)
            .values(status="RESOLVED", resolution="Product mapped.", updated_by_kind="SYSTEM")
        )
    assert _interfaces(world)[:2] == ("FAILED", 2)  # one of its two items is still open
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == second)
            .values(status="IN_PROGRESS", updated_by_kind="SYSTEM")
        )
    assert _interfaces(world)[:2] == ("FAILED", 2)  # IN_PROGRESS is still open
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == second)
            .values(status="DISMISSED", resolution="Superseded.", updated_by_kind="SYSTEM")
        )
    assert _interfaces(world) == one

    # A failed file import counts beside the run, and both are named.
    with system_session(world) as session:
        stored_file = file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
        session.execute(insert(file_object).values(**stored_file))
        upload = import_upload_values(world.tenant_id, file_object_id=stored_file["id"])
        session.execute(insert(import_upload).values(**upload))
        for status in (
            "VALIDATING",
            "VALIDATED",
            "DIFFING",
            "DIFF_READY",
            "SUBMITTED",
            "APPROVED",
            "COMMITTING",
            "FAILED",
        ):
            session.execute(
                update(import_upload)
                .where(import_upload.c.id == upload["id"])
                .values(status=status, updated_by_kind="SYSTEM")
            )
        import_item = exception_item_values(
            world.tenant_id,
            source="IMPORT",
            code="CONTROL_TOTALS_MISMATCH",
            title="Control totals do not match",
            import_upload_id=upload["id"],
        )
        session.execute(insert(exception_item).values(**import_item))
    assert _interfaces(world) == (
        "FAILED",
        2,
        "Interface batch not complete: Salesforce (orders), File imports (2 runs)",
    )
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == import_item["id"])
            .values(status="DISMISSED", resolution="Superseded.", updated_by_kind="SYSTEM")
        )
    assert _interfaces(world) == one

    # The mismatch is waived through its approval (E-44 WAIVED): the gate passes.
    with system_session(world) as session:
        waiver = approval_request_values(
            world.tenant_id,
            subject_type="EXCEPTION_WAIVER",
            subject_id=mismatch_item,
            preparer_id=world.maya.member.user_id,
            summary="Waive the control-total mismatch",
        )
        session.execute(insert(approval_request).values(**waiver))
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == mismatch_item)
            .values(
                status="WAIVED",
                waiver_approval_request_id=waiver["id"],
                resolution="Accepted by the controller.",
                updated_by_kind="SYSTEM",
            )
        )
    assert _interfaces(world) == passed
    blockers = get(world.app, f"{PERIODS}/{world.state_id}", world.maya).json()["blockers"]
    assert blockers["interface_failures"] == 0


def test_data_quality_warning_holds_no_lock(world: CloseWorld) -> None:
    """Supervisor ruling R-57; 04 Table 15.4-E rev 1.106 ("`ERROR` results block lock"); 03
    REQ-CLS-019. A WARNING finding of the monitors — an inactive contract here — stays in the
    exception queue and counts neither in EXCEPTIONS_CLEARED nor in ``blockers.exceptions_open``;
    a BLOCKING finding counts in both gates, and a WARNING item of any other source still holds
    the exceptions gate (D-88 L7-2-Q-1). Until this ruling every open WARNING item held the gate,
    the monitors' own included, so an ordinary period locked only through a gate waiver."""
    with system_session(world) as session:
        contract_of(
            session,
            world,
            status="ACTIVE",
            event_effective_date=date(2026, 6, 1),
        )
    with world.place.uow() as uow:
        run = monitors.run_monitors(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    assert (run.created, run.open_blocking) == (1, 0)
    with system_session(world) as session:
        ((code, severity, status),) = session.execute(
            select(exception_item.c.code, exception_item.c.severity, exception_item.c.status)
        ).all()
    assert (code, str(severity), str(status)) == ("DQ_INACTIVE_CONTRACT", "WARNING", "OPEN")
    results = _evaluated(world)
    assert _outcome(results["EXCEPTIONS_CLEARED"]) == ("PASSED", 0)
    assert _outcome(results["DATA_QUALITY_CLEAR"]) == ("PASSED", 0)
    blockers = get(world.app, f"{PERIODS}/{world.state_id}", world.maya).json()["blockers"]
    assert blockers["exceptions_open"] == 0

    # A WARNING item of another source holds the exceptions gate as before.
    with system_session(world) as session:
        other = exception_item_values(
            world.tenant_id,
            source="IMPORT",
            code="STALE_SOURCE_VERSION",
            severity="WARNING",
            title="Stale source version",
            entity_id=world.entity_id,
        )
        session.execute(insert(exception_item).values(**other))
    assert _outcome(_evaluated(world)["EXCEPTIONS_CLEARED"]) == ("FAILED", 1)
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == other["id"])
            .values(status="DISMISSED", resolution="Superseded.", updated_by_kind="SYSTEM")
        )

    # A BLOCKING data-quality finding (a duplicate invoice) holds both gates.
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    with world.place.uow() as uow:
        monitors.run_monitors(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    results = _evaluated(world)
    assert _outcome(results["DATA_QUALITY_CLEAR"]) == ("FAILED", 1)
    assert _outcome(results["EXCEPTIONS_CLEARED"]) == ("FAILED", 1)


@pytest.mark.control("CTL-049")
def test_ctl_049_unreviewed_judgement_fails_gate(world: CloseWorld) -> None:
    with system_session(world) as session:
        contract_id, _, _ = contract_of(session, world)
        judgement_id = submitted_judgement(session, world, contract_id)
    assert _outcome(_evaluated(world)["JUDGEMENTS_REVIEWED"]) == ("FAILED", 1)
    reviewer = colleague(world.tenant_id, "priya")
    with system_session(world) as session:
        session.execute(
            update(judgement_record)
            .where(judgement_record.c.id == judgement_id)
            .values(
                status="REVIEWED",
                reviewer_id=reviewer.user_id,
                reviewed_at=world.place.clock.now(),
                updated_by_kind="SYSTEM",
            )
        )
    assert _outcome(_evaluated(world)["JUDGEMENTS_REVIEWED"]) == ("PASSED", 0)


def test_gates_pass_with_balanced_covering_run(world: CloseWorld) -> None:
    """BUILD_SPEC CLO-10 acceptance, re-run with the real signal: the period's one non-cancelled
    run balances (a REVENUE credit and an UNBILLED_RECEIVABLE debit of 250.00 in one sealed
    posting) and covers the schedule line carrying the period's activity, so ``JE_BALANCED`` and
    ``JE_COMPLETE`` are PASSED with count 0; both results are stored on
    ``close_checklist_item.result`` and ``control_execution_id`` stays null until SOP builds
    T-PLT-39 (header XR-12)."""
    with system_session(world) as session:
        revenue = gl_account_values(world.tenant_id, code="5001")
        unbilled = gl_account_values(world.tenant_id, code="1201")
        session.execute(insert(gl_account).values(**revenue))
        session.execute(insert(gl_account).values(**unbilled))
        sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=date(2026, 9, 30),
            amounts=[Decimal("-250.00"), Decimal("250.00")],
            with_schedule_line=True,
            schedule_amount=Decimal("250.00"),
            line_overrides=[
                {},
                {
                    "gl_account_id": unbilled["id"],
                    "account_role": "UNBILLED_RECEIVABLE",
                    "schedule_line_id": None,
                },
            ],
        )
    job_id, _ = requested_journal_run(world)
    assert str(run_journal_job(world, job_id)["state"]) == "SUCCEEDED"
    results = _evaluated(world)
    assert _outcome(results["JE_BALANCED"]) == ("PASSED", 0)
    assert _outcome(results["JE_COMPLETE"]) == ("PASSED", 0)
    assert results["JE_COMPLETE"].detail is None
    with system_session(world) as session:
        stored = {
            str(row["gate_check_code"]): (row["result"], row["control_execution_id"])
            for row in session.execute(
                select(
                    close_checklist_template.c.gate_check_code,
                    close_checklist_item.c.result,
                    close_checklist_item.c.control_execution_id,
                )
                .select_from(
                    close_checklist_item.join(
                        close_checklist_template,
                        close_checklist_template.c.id
                        == close_checklist_item.c.close_checklist_template_id,
                    )
                )
                .where(
                    close_checklist_item.c.entity_id == world.entity_id,
                    close_checklist_item.c.period_id == world.period_id,
                )
            ).mappings()
        }
    for code in ("JE_BALANCED", "JE_COMPLETE"):
        result, execution = stored[code]
        assert (result["count"], result["detail"], execution) == (0, None, None), code


def test_gates_fail_closed_before_producers(world: CloseWorld, clock: FrozenClock) -> None:
    results = _evaluated(world)
    # CLO-10: the real signal — without a run the completeness assertion fails closed by name,
    # as JE_BALANCED does (BUILD_SPEC CLO-10 acceptance, re-run with the real signal).
    assert (results["JE_COMPLETE"].status, results["JE_COMPLETE"].detail) == (
        ChecklistStatus.FAILED,
        "Journal run not calculated",
    )
    assert results["JE_COMPLETE"].count == 1
    # CLO-5: the real signal — no open BLOCKING DATA_QUALITY item, so the gate passes with count 0.
    assert _outcome(results["DATA_QUALITY_CLEAR"]) == ("PASSED", 0)
    assert results["DATA_QUALITY_CLEAR"].detail is None
    # T-SL-07 and T-CLS-06 are empty and a journal run is required (header XR-12).
    assert _outcome(results["BATCHES_ACKNOWLEDGED"]) == ("FAILED", 1)
    assert results["BATCHES_ACKNOWLEDGED"].detail == "Journal run not calculated"
    assert _outcome(results["RECONCILIATIONS_GENERATED"]) == ("FAILED", 2)
    assert _outcome(results["JE_BALANCED"]) == ("FAILED", 1)
    assert (results["CONTROLLER_CERTIFIED"].status, results["CONTROLLER_CERTIFIED"].detail) == (
        ChecklistStatus.FAILED,
        "Awaiting Controller certification at lock",
    )
    passed = {code for code, result in results.items() if result.status is ChecklistStatus.PASSED}
    assert passed == {
        "INTERFACES_COMPLETE",
        "APPROVALS_CLEARED",
        "EXCEPTIONS_CLEARED",
        "HOLDS_REVIEWED",
        "JUDGEMENTS_REVIEWED",
        "DATA_QUALITY_CLEAR",
        "NO_DIRTY_GROUPS",
        "MANUAL_ADJUSTMENTS_CLEARED",
    }
    # CLO-5 acceptance: one reachable BLOCKING data-quality finding fails the gate with 1 — the
    # admitted duplicate invoice (ruling Q-8 rule 2). A negative contract liability is not
    # representable on contract_version_balance (04 T-CON-09 CHECK), see test_monitors.
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    with world.place.uow() as uow:
        monitors.run_monitors(uow, world.entity_id, BOOK, world.period_id)
        uow.commit()
    failed = _evaluated(world)["DATA_QUALITY_CLEAR"]
    assert (_outcome(failed), failed.detail) == (("FAILED", 1), "Data-quality errors: 1")
    # Generated but not reviewed reconciliations still fail the gate, and count as generated.
    with system_session(world) as session:
        for kind in ("BILLING_TO_SUBLEDGER", "SUBLEDGER_TO_GL"):
            session.execute(
                insert(reconciliation).values(
                    **reconciliation_values(
                        world.tenant_id,
                        entity_id=world.entity_id,
                        period_id=world.period_id,
                        kind=kind,
                    )
                )
            )
    again = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert _outcome(again) == ("FAILED", 2)
    assert again.detail == (
        "Reconciliation not reviewed: Billing to subledger; "
        "Reconciliation not reviewed: Subledger to GL"
    )
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id)
        assert scope is not None
        derived = gates.derived_counts(uow.session, scope, known_at=uow.now)
    assert derived["RECONCILIATIONS_NOT_GENERATED"] == 0

    # CLO-16 and CLO-17 (BUILD_SPEC re-runs with the real signal; supervisor ruling R-54 (b), (f)):
    # a required kind counts while its CURRENT reconciliation — the latest generated — is missing
    # or not reviewed. The reconciliations the product generates replace the fixture rows above.
    place = world.place
    runtime = JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files)
    maya = enrolled(world.app, clock, world.maya.member)
    # From here Maya and the world work with the verified session: with a factor, her earlier
    # one owes the challenge (REQ-PLT-005).
    world = carrying(world, maya=maya)
    priya = actor_with_role(world.app, clock, world.tenant_id, "revenue_reviewer", name="priya")
    billing = "Reconciliation not reviewed: Billing to subledger"
    both = f"{billing}; Reconciliation not reviewed: Subledger to GL"
    # Subledger to GL: generated without a source, compared with an uploaded trial balance, then
    # prepared and reviewed. AVM-US has posted nothing, so no account is subledger-controlled and
    # the file's row is not compared.
    ledger = recon.generated(
        world.app,
        maya,
        runtime,
        entity_code="AVM-US",
        period_key="FY2026-P09",
        kind=recon.SUBLEDGER_TO_GL,
    )
    unattached = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert (_outcome(unattached), unattached.detail) == (("FAILED", 2), both)
    file_id = recon.uploaded(
        world.app,
        maya,
        "avm-us-tb-2026-09.csv",
        recon.trial_balance_csv([("2100", "USD", "0.00")]),
    )
    compared = recon.attached(world.app, maya, runtime, ledger["id"], {"file_id": file_id})
    assert (compared["status"], compared["variance_count"], compared["totals"]) == ("DRAFT", 0, [])
    assert recon.prepare(world.app, maya, ledger["id"]).status_code == 200
    assert recon.sign(world.app, priya, ledger["id"]).status_code == 200
    # CLO-16: with Subledger to GL reviewed, the gate counts 1 until a BILLING_TO_SUBLEDGER
    # reconciliation exists and is reviewed or auto-certified.
    waiting = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert (_outcome(waiting), waiting.detail) == (("FAILED", 1), billing)
    # The billing reconciliation itemises the two A-1001 documents above (2,400.00, no billing
    # event): a draft still counts, and so does a prepared one.
    generated = recon.generated(
        world.app, maya, runtime, entity_code="AVM-US", period_key="FY2026-P09"
    )
    assert (generated["status"], generated["variance_count"]) == ("DRAFT", 1)
    drafted = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert (_outcome(drafted), drafted.detail) == (("FAILED", 1), billing)
    (difference,) = recon.items_of(world.app, maya, generated["id"])
    assert (difference["item_kind"], difference["difference"]["amount"]) == (
        "UNMATCHED_SOURCE",
        "2400.00",
    )
    explained = recon.explain(
        world.app, maya, difference, "Duplicate documents of A-1001; the second one is credited."
    )
    assert explained.status_code == 200, explained.text
    assert recon.prepare(world.app, maya, generated["id"]).status_code == 200
    prepared = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert (_outcome(prepared), prepared.detail) == (("FAILED", 1), billing)
    assert recon.sign(world.app, priya, generated["id"]).status_code == 200
    # CLO-17: the gate counts 0 once both required kinds exist and are reviewed or auto-certified.
    reviewed = _evaluated(world)["RECONCILIATIONS_GENERATED"]
    assert (_outcome(reviewed), reviewed.detail) == (("PASSED", 0), None)
    # The cockpit counts read the same current rows: the fixture's draft rows are replaced, so
    # nothing is unsigned and both required kinds are reviewed.
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id)
        assert scope is not None
        assert gates.blocker_counts(uow.session, scope)["reconciliations_unsigned"] == 0
        assert gates.reconciliations_reviewed(uow.session, scope, known_at=uow.now) == {
            "reviewed": 2,
            "required": 2,
        }

    # A future period has no checklist yet: nothing is stored for FY2026-P10.
    (october,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P10"
    ]
    with world.place.uow() as uow:
        gates.evaluate_gates(uow, world.entity_id, BOOK, UUID(str(october["period"]["id"])))
        uow.commit()
    assert (
        world.place.rows(
            select(close_checklist_item.c.id).where(
                close_checklist_item.c.period_id == UUID(str(october["period"]["id"]))
            )
        )
        == []
    )


def test_business_days_after_period_end() -> None:
    from datetime import date

    # 30 Sep 2026 is a Wednesday; three business days later is Monday 5 Oct 2026.
    assert gates.business_days_after(date(2026, 9, 30), 3) == date(2026, 10, 5)
    assert gates.business_days_after(date(2026, 9, 30), 0) == date(2026, 9, 30)


def _lock(world: CloseWorld, period_key: str, created_at: datetime) -> None:
    """AVM-US ``period_key`` open → closing → closed for ASC606 with a lock created at
    ``created_at``, each change with its transition row. No period can be locked in the rc (CLO-6 is
    post-rc), so the rows are written directly ([J] D-88 L7-2-Q-8)."""
    (state,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == period_key
    ]
    state_id = UUID(str(state["id"]))
    period_id = UUID(str(state["period"]["id"]))
    with system_session(world) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
        ).scalar_one()
        request = approval_request_values(world.tenant_id, status=ApprovalRequestStatus.APPROVED)
        session.execute(insert(approval_request).values(**request))
        for from_state, to_state in (("open", "closing"), ("closing", "closed")):
            transition = period_state_transition_values(
                world.tenant_id,
                period_state_id=state_id,
                entity_id=world.entity_id,
                period_id=period_id,
                from_state=from_state,
                to_state=to_state,
            )
            moved = {"state": to_state, "updated_by_kind": PrincipalKind.SYSTEM.value}
            if to_state == "closed":
                parts = CloseParts(
                    calendar_id=UUID(str(calendar_id)),
                    entity_id=world.entity_id,
                    period_id=period_id,
                    period_state_transition_id=transition["id"],
                    approval_request_id=request["id"],
                    file_id=request["id"],
                )
                lock = period_lock_values(world.tenant_id, parts=parts, created_at=created_at)
                session.execute(insert(period_lock).values(**lock))
                transition = {
                    **transition,
                    "approval_request_id": request["id"],
                    "period_lock_id": lock["id"],
                }
                moved["current_lock_id"] = lock["id"]
            session.execute(insert(period_state_transition).values(**transition))
            session.execute(
                update(period_state).where(period_state.c.id == state_id).values(**moved)
            )


def test_days_to_close_in_entity_time_zone(world: CloseWorld) -> None:
    """[J] D-88 L7-2-Q-8: days = the date of the current lock's created_at in the entity's time zone
    (AVM-US: America/New_York) minus the period end date; a period not closed has no days."""
    # 2026-08-05T02:00:00Z is 2026-08-04 22:00 in New York: 4 days, where the UTC date gives 5.
    _lock(world, "FY2026-P07", datetime(2026, 8, 5, 2, 0, tzinfo=UTC))
    _lock(world, "FY2026-P08", datetime(2026, 9, 4, 16, 0, tzinfo=UTC))
    cockpit = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", world.maya)
    assert cockpit.status_code == 200, cockpit.text
    assert cockpit.json()["kpis"]["days_to_close_last_three"] == [
        {"period_key": "FY2026-P07", "days": 4},
        {"period_key": "FY2026-P08", "days": 4},
        {"period_key": "FY2026-P09", "days": None},
    ]
    # CLO-6 figure: FY2026-P09 (end 2026-09-30) locked 2026-10-06 local gives 6.
    _lock(world, "FY2026-P09", datetime(2026, 10, 6, 14, 0, tzinfo=UTC))
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, world.state_id)
        assert scope is not None
        shown = queries.days_to_close(uow.session, scope)
    assert shown == [
        {"period_key": "FY2026-P07", "days": 4},
        {"period_key": "FY2026-P08", "days": 4},
        {"period_key": "FY2026-P09", "days": 6},
    ]
