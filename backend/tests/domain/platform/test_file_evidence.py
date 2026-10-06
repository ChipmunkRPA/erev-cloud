"""Evidence files are not shredded while their record stands (security finding SC-6; supervisor
rulings R-30, R-49 and R-86; 05 PRV-06, PRV-07 b; 04 T-PLT-29, table 15.4-B
``FILE_EVIDENCE_HELD`` and ``FILE_SHRED_APPROVAL_REQUIRED``, E-08 ``EVIDENCE_SHRED``, API-R-12;
runbook RB-14; PRD §2.5; 03 REQ-DAT-001, REQ-CLS-010, REQ-PLT-011).

The reviewer's two proofs (``sec-close/test_poc_import_source_shred.py`` and
``test_poc_snapshot_shred.py``) inverted: Tess, a Tenant Admin who holds ``settings.manage`` and no
finance permission, is REFUSED by reference when she shreds the source of a submitted or committed
import, or a frozen dataset of a period lock — with a ``DENIED`` audit event that names the record
— next to the positive controls in which the same command succeeds on a file no standing record
holds. The import still answers once a source is gone, and the next period still locks.

An uploaded document that a record rests on is erased only through a second person (R-49 (a),
R-86 (b), (c)): the source of a committed import, the source file of a signed reconciliation, the
legacy database of a migration whose capture is relied on, the SSP study of a submitted version,
the attachment of a submitted manual adjustment at or above its threshold. Tess requests, a
Controller whose own scope covers the record's entities approves, and the approval shreds as the
system on her behalf — never Tess herself, never a reviewer, never a Controller of another
entity; nothing changes while the request is pending or when it is rejected. Every refusal of
``file.shred`` is on the audit log as ``DENIED`` (R-86 (f)).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import transitions
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    combination_group,
    engine_release,
    file_attachment,
    file_object,
    gl_account,
    job,
    journal_batch,
    journal_run,
    legal_entity,
    lock_snapshot,
    manual_adjustment,
    migration_batch,
    period_lock,
    reconciliation,
    ssp_book,
    ssp_book_version,
)
from erev_api.domain.close import commands as close_commands
from erev_api.domain.platform import evidence_shred, file_evidence, privacy, setup
from erev_api.enums import FilePurpose, JobKind
from erev_api.files.store import LocalFileStore, store_file
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session
from support.close_world import (
    CloseWorld,
    close_run_succeeded,
    close_world,
    contract_of,
    earlier_periods_closed,
    other_entity,
    record_run_calculation,
    reviewed_reconciliations,
    run_journal_job,
    system_session,
)
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    ImportWorld,
    J03World,
    computed,
    import_world,
    imported,
    j03_world,
    run_import_job,
    stamp_test_release,
)
from support.http import HttpResponse, call
from support.principals import Actor, colleague, cookie_headers, enrolled
from support.reference import PERIODS, approve, assign, get, periods, post, reject, slug
from support.rows import (
    JournalParts,
    JournalRows,
    approval_request_values,
    engine_release_values,
    file_object_values,
    gl_account_values,
    insert_journal_rows,
    manual_adjustment_values,
    migration_batch_values,
    reconciliation_values,
)

FILES = "/api/v1/files"
RULE = "FILE_EVIDENCE_HELD"
APPROVAL_RULE = "FILE_SHRED_APPROVAL_REQUIRED"
APPROVALS = "/api/v1/approvals"
REASON = "DSR-2026-0917: erase the person's data in this document"
KEPT = "It is kept while that record stands and cannot be shredded."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def tenant_admin(app: FastAPI, clock: FrozenClock, tenant_id: UUID) -> Actor:
    """Tess: a Tenant Admin (``settings.manage``, MFA) without a finance permission."""
    someone = colleague(tenant_id, "tess")
    assign(someone, "tenant_admin")
    return enrolled(app, clock, someone)


def shred(app: FastAPI, actor: Actor, file_id: Any) -> HttpResponse:
    return post(app, f"{FILES}/{file_id}/shred", actor, {"reason": REASON})


def rows_of(tenant_id: UUID, statement: Any) -> list[Mapping[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def assert_held(
    refused: HttpResponse, tenant_id: UUID, file_id: Any, record: str, *, rule: str = RULE
) -> str:
    """409 by reference, the file untouched, and the refusal on the audit log as DENIED. A hold
    an approval lifts answers ``FILE_SHRED_APPROVAL_REQUIRED`` and names the approved path (R-49
    (a), R-86); every other evidence file ``FILE_EVIDENCE_HELD``."""
    refused_as(refused, 409, "invalid-transition")
    (error,) = refused.json()["errors"]
    assert (error["field"], error["rule_id"]) == ("status", rule), error
    message = str(error["message"])
    if rule == APPROVAL_RULE:
        assert message == file_evidence.APPROVAL_MESSAGE.format(record=record), message
    else:
        assert message.startswith(f"This file is {record}. {KEPT}"), message
    (stored,) = rows_of(
        tenant_id, select(file_object.c.shredded_at).where(file_object.c.id == UUID(str(file_id)))
    )
    assert stored["shredded_at"] is None
    denied = rows_of(
        tenant_id,
        select(audit_event.c.action, audit_event.c.detail).where(
            audit_event.c.object_id == UUID(str(file_id)), audit_event.c.outcome == "DENIED"
        ),
    )
    assert denied, "the refusal is the recorded outcome of the request"
    last = denied[-1]
    assert last["action"] == "file_object.shred"
    assert (last["detail"]["rule_id"], last["detail"]["record"]) == (rule, record)
    assert last["detail"]["reason"] == REASON
    return message


# --- the source of an import (R-30, R-49 (a), (c)) --------------------------------------------


def customers_csv(code: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("code", "name", "segment", "country_code"))
    writer.writerow((code, "Harbourline Freight Ltd (Demo)", "Logistics", "PT"))
    return buffer.getvalue().encode("utf-8")


def job_of(world: ImportWorld, import_id: str, kind: str) -> UUID:
    found = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == UUID(import_id), job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    return UUID(str(found[-1]["id"]))


def shown(world: ImportWorld, import_id: str) -> dict[str, Any]:
    response = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor)
    assert response.status_code == 200, response.text
    return dict(response.json())


def submitted(world: ImportWorld, name: str, code: str) -> tuple[str, str, str]:
    """A ``customers`` upload validated, diffed and submitted: (import id, source file id,
    approval request id)."""
    import_id, validated = imported(world, name, customers_csv(code), "customers")
    assert validated["status"] == "VALIDATED", validated
    run_import_job(world, job_of(world, import_id, "IMPORT_DIFF"))
    response = post(
        world.app, f"{IMPORTS_PATH}/{import_id}/submit", world.actor, {"comment": "customers"}
    )
    assert response.status_code == 200, response.text
    return import_id, str(validated["file"]["id"]), str(response.json()["approval_request_id"])


def test_sc6_the_source_of_a_submitted_or_committed_import_is_not_shredded(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = import_world(app, keyring, clock, files)
    priya_member = colleague(world.tenant_id, "priya")
    assign(priya_member, "revenue_reviewer")
    priya = enrolled(app, clock, priya_member)
    tess = tenant_admin(app, clock, world.tenant_id)

    # --- a SUBMITTED import holds its source; the erasure path is "rejected or withdrawn first".
    import_id, file_id, request_id = submitted(world, "crm-customers.csv", "C-901")
    number = shown(world, import_id)["import_no"]
    pending = assert_held(
        shred(app, tess, file_id),
        world.tenant_id,
        file_id,
        f"the source of import {number}, which is submitted for approval or being committed",
    )
    assert pending.endswith(file_evidence.WITHDRAW_FIRST), pending

    # --- COMMITTED: REQ-DAT-001 "the original file and its SHA-256 are kept".
    assert approve(app, request_id, priya).status_code == 200
    run_import_job(world, job_of(world, import_id, "IMPORT_COMMIT"))
    assert shown(world, import_id)["status"] == "COMMITTED"
    assert_held(
        shred(app, tess, file_id),
        world.tenant_id,
        file_id,
        f"the source of committed import {number}",
        rule=APPROVAL_RULE,
    )
    assert get(app, f"{FILES}/{file_id}/content", world.actor).status_code == 200
    assert shown(world, import_id)["status"] == "COMMITTED"

    # --- Positive control 1: a rejected import no longer holds its source.
    rejected_id, rejected_file, rejected_request = submitted(world, "crm-second.csv", "C-902")
    assert reject(app, rejected_request, priya, "Not this quarter").status_code == 200
    assert shown(world, rejected_id)["status"] == "REJECTED"
    done = shred(app, tess, rejected_file)
    assert done.status_code == 200 and done.json()["shredded_at"] is not None, done.text

    # --- Positive control 2: an upload that never reached SUBMITTED, a CSV v2 file whose header
    # match reads the source. After the shred the import still answers (R-49 (c)): its state and
    # rows shown, the file's content gone.
    draft_id, validated = imported(world, "crm-third.csv", customers_csv("C-903"), "customers")
    draft_file = str(validated["file"]["id"])
    assert validated["status"] == "VALIDATED" and validated["header_match"], validated
    gone = shred(app, tess, draft_file)
    assert gone.status_code == 200 and gone.json()["shredded_at"] is not None, gone.text
    content = get(app, f"{FILES}/{draft_file}/content", world.actor)
    assert content.status_code == 404, content.text
    assert [error["rule_id"] for error in content.json()["errors"]] == ["FILE_SHREDDED"]
    after = shown(world, draft_id)
    assert (after["status"], after["file"]["id"], after["header_match"]) == (
        "VALIDATED",
        draft_file,
        [],
    )
    assert after["file"]["sha256"] == validated["file"]["sha256"]
    rows = get(app, f"{IMPORTS_PATH}/{draft_id}/rows", world.actor)
    assert rows.status_code == 200 and len(rows.json()["items"]) == 1, rows.text
    report = get(app, f"{IMPORTS_PATH}/{draft_id}/error-report", world.actor)
    assert report.status_code == 200, report.text


# --- a frozen dataset of a period lock (R-30, R-49 (b)) ----------------------------------------


def _state(world: CloseWorld, key: str) -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == key
    ]
    return dict(found)


def _acknowledged_run(
    session: Session, world: CloseWorld, period_id: UUID, *, je_seq: int
) -> JournalRows:
    """``support.close_world.acknowledged_run_for`` with a chosen JE sequence, so two periods of
    one entity each get their fixture run."""
    now = world.place.clock.now()
    calendar_id = session.execute(
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == world.entity_id)
    ).scalar_one()
    account = gl_account_values(world.tenant_id)
    session.execute(insert(gl_account).values(**account))
    release = engine_release_values()
    session.execute(insert(engine_release).values(**release))
    parts = JournalParts(
        calendar_id=UUID(str(calendar_id)),
        entity_id=world.entity_id,
        period_id=period_id,
        account_id=UUID(str(account["id"])),
        release_id=UUID(str(release["id"])),
    )
    rows = insert_journal_rows(session, world.tenant_id, parts=parts, je_seqs=(je_seq,))
    for state, stamps in (
        ("approved", {"approved_at": now}),
        ("exported", {"exported_at": now}),
        ("acknowledged", {"acknowledged_at": now}),
    ):
        session.execute(
            update(journal_run)
            .where(journal_run.c.id == rows.run["id"])
            .values(state=state, **stamps)
        )
    for state, stamps in (
        ("approved", {}),
        ("exported", {"exported_at": now, "attempt_count": 1}),
        ("acknowledged", {"acknowledged_at": now}),
    ):
        session.execute(
            update(journal_batch)
            .where(journal_batch.c.id == rows.batch["id"])
            .values(state=state, **stamps)
        )
    return rows


def _lock(world: CloseWorld, key: str, approver: Actor, *, je_seq: int) -> HttpResponse:
    """Soft-close ``key``, make its automatic gates pass, request the lock (Maya), decide it."""
    current = _state(world, key)
    started = post(
        world.app,
        f"{PERIODS}/{current['id']}/start-close",
        world.maya,
        {"comment": f"{key} close in progress"},
        if_match=f'"r{current["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    period_id = UUID(str(current["period"]["id"]))
    with system_session(world) as session:
        rows = _acknowledged_run(session, world, period_id, je_seq=je_seq)
        reviewed_reconciliations(session, world, period_id)
        close_run_succeeded(session, world, period_id)
    record_run_calculation(world, rows)
    with world.place.uow() as requester:
        requested = close_commands.request_lock(
            requester,
            state_id=UUID(str(current["id"])),
            body=PeriodLockRequestIn(certification_comment=f"{key} close complete"),
            check_version=lambda actual: None,
        )
        requester.commit()
    return approve(world.app, str(requested.approval_request_id), approver)


def test_sc6_a_frozen_dataset_of_a_period_lock_is_not_shredded(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = close_world(app, keyring, clock, files)
    stamp_test_release()
    cora_member = colleague(world.tenant_id, "cora")
    assign(cora_member, "controller")
    cora = enrolled(app, clock, cora_member)
    tess = tenant_admin(app, clock, world.tenant_id)
    with world.place.uow() as fixture:  # a tenant past its setup
        setup.evaluate_setup_completion(fixture)
        fixture.commit()

    # PRD WLD-P-02 / BR-CLS-08 (supervisor ruling R-6): January to August are closed before
    # September is brought to its lock — fixture state.
    earlier_periods_closed(world, before="FY2026-P09")
    # September is locked through the real approval: twelve frozen datasets (04 T-CLS-05).
    decided = _lock(world, "FY2026-P09", cora, je_seq=1)
    assert decided.status_code == 200, decided.text
    assert _state(world, "FY2026-P09")["state"] == "closed"
    frozen = rows_of(
        world.tenant_id,
        select(lock_snapshot.c.snapshot_kind, lock_snapshot.c.file_id, file_object.c.purpose)
        .select_from(
            lock_snapshot.join(file_object, file_object.c.id == lock_snapshot.c.file_id).join(
                period_lock, period_lock.c.id == lock_snapshot.c.period_lock_id
            )
        )
        .where(period_lock.c.period_id == world.period_id, period_lock.c.kind == "LOCK")
        .order_by(lock_snapshot.c.snapshot_kind),
    )
    assert len(frozen) == 12
    assert {str(row["purpose"]) for row in frozen} == {"SNAPSHOT_DATASET"}  # crypto-shreddable

    # Every dataset of the CLOSED period is refused by reference; none is touched.
    for row in frozen:
        assert_held(
            shred(app, tess, row["file_id"]),
            world.tenant_id,
            row["file_id"],
            "a frozen dataset of a period lock",
        )
    # ... and still read by its readers: a lock dataset is read with ``report.run`` for the
    # lock's entity (04 T-PLT-29 Read access), which the Controller holds. Tess, who may shred
    # and holds no finance permission, is not among them (security review S2; ruling R-48 (c)).
    readable = get(app, f"{FILES}/{frozen[0]['file_id']}/content", cora)
    assert readable.status_code == 200, readable.text
    hidden = get(app, f"{FILES}/{frozen[0]['file_id']}/content", tess)
    assert hidden.status_code == 404, hidden.text

    # The September lock opened October and deferred its re-marking (supervisor ruling R-101
    # (a)), and the period a lock opened is locked only after that job has succeeded (R-106 (a)).
    # Fixture state: the job runs as the worker runs it, and what it marks is recomputed.
    (deferred,) = rows_of(
        world.tenant_id,
        select(job.c.id).where(
            job.c.kind == JobKind.PERIOD_OPEN_REDIRTY.value,
            job.c.subject_id == UUID(str(_state(world, "FY2026-P10")["id"])),
        ),
    )
    remarked = run_journal_job(world, UUID(str(deferred["id"])))
    assert str(remarked["state"]) == "SUCCEEDED", remarked
    for marked in rows_of(
        world.tenant_id,
        select(combination_group.c.id).where(combination_group.c.dirty_since.is_not(None)),
    ):
        computed(world.place, UUID(str(marked["id"])))

    # The next period still locks: no dataset identity was burnt by a shred (D-98 145).
    assert _state(world, "FY2026-P10")["state"] == "open"
    following = _lock(world, "FY2026-P10", cora, je_seq=2)
    assert following.status_code == 200, following.text
    assert _state(world, "FY2026-P10")["state"] == "closed"

    # Positive control: a file of the same purpose that no lock references is shredded.
    with world.place.uow() as uow:
        loose = store_file(
            uow,
            purpose=FilePurpose.SNAPSHOT_DATASET,
            stream=io.BytesIO(f"line_code,amount\nLOOSE-{uuid4()},1.00\n".encode()),
            original_filename="loose-dataset.csv",
            media_type="text/csv",
        )
        uow.commit()
    done = shred(app, tess, loose["id"])
    assert done.status_code == 200 and done.json()["shredded_at"] is not None, done.text


# --- the lookup reads over every entity ---------------------------------------------------------


def test_sc6_a_record_of_another_entity_holds_its_file_too(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``approval_request`` is entity-scoped (RLS-TE): a session restricted to AVM-US does not see
    the request of AVM-UK that references a preview file, and ``holding`` finds it all the same —
    the refusal never depends on the caller's entity scope."""
    world = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    with system_session(world) as session:
        uk = other_entity(session, world)
        preview = file_object_values(tenant_id, purpose=FilePurpose.IMPACT_PREVIEW)
        session.execute(insert(file_object).values(**preview))
        request = approval_request_values(
            tenant_id, entity_id=uk, impact_preview_file_id=preview["id"]
        )
        session.execute(insert(approval_request).values(**request))
    file_id = UUID(str(preview["id"]))
    restricted = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(world.entity_id,))
    with tenant_session(restricted, read_only=True) as session:
        assert file_evidence.holding_in(session, file_id) is None
    hold = file_evidence.holding(tenant_id, file_id)
    assert hold is not None
    assert (hold.reference.table, hold.reference.column) == (
        "approval_request",
        "impact_preview_file_id",
    )
    assert hold.record == "the impact preview of an approval request"
    assert file_evidence.holding(tenant_id, uuid4()) is None


# --- the approved shred of an evidence file (R-49 (a), R-86 (b), (c)) ---------------------------

PDF = b"%PDF-1.4\n% evidence tests\n"


def committed(world: ImportWorld, approver: Actor, name: str, code: str) -> tuple[str, str]:
    """A ``customers`` upload committed: (import id, source file id)."""
    import_id, file_id, request_id = submitted(world, name, code)
    assert approve(world.app, request_id, approver).status_code == 200
    run_import_job(world, job_of(world, import_id, "IMPORT_COMMIT"))
    assert shown(world, import_id)["status"] == "COMMITTED"
    return import_id, file_id


def request_shred(app: FastAPI, actor: Actor, file_id: Any, reason: str = REASON) -> HttpResponse:
    return post(app, f"{FILES}/{file_id}/request-shred", actor, {"reason": reason})


def refused_as(response: HttpResponse, status: int, problem: str) -> None:
    """The status first, then the problem's slug: an answer that is no refusal (a 200 has no
    problem body) fails on its status, with its text, not inside ``slug``."""
    assert response.status_code == status, response.text
    assert slug(response) == problem, response.text


def requested(app: FastAPI, actor: Actor, file_id: Any) -> str:
    """The id of the pending ``EVIDENCE_SHRED`` request a request opens."""
    response = request_shred(app, actor, file_id)
    assert response.status_code == 200, response.text
    return str(response.json()["approval_request_id"])


def approval_sent_by(
    app: FastAPI, request_id: str, outsider: Actor, *, reader: Actor
) -> HttpResponse:
    """The approve command as ``outsider`` sends it, with the hashes ``reader`` — who can read the
    request — sees. ``approve`` reads the request as the approver first, which a person the
    request is not shown to cannot do."""
    detail = get(app, f"{APPROVALS}/{request_id}", reader)
    assert detail.status_code == 200, detail.text
    return post(
        app,
        f"{APPROVALS}/{request_id}/approve",
        outsider,
        {
            "subject_content_sha256": detail.json()["subject"]["content_sha256"],
            "impact_preview_sha256": detail.json()["impact_preview"]["sha256"],
            "comment": "OK",
        },
    )


def controller(app: FastAPI, clock: FrozenClock, tenant_id: UUID, name: str, **scope: Any) -> Actor:
    someone = colleague(tenant_id, name)
    assign(someone, "controller", **scope)
    return enrolled(app, clock, someone)


def file_state(tenant_id: UUID, file_id: Any) -> Mapping[str, Any]:
    (stored_row,) = rows_of(
        tenant_id,
        select(
            file_object.c.shredded_at,
            file_object.c.shredded_by,
            file_object.c.shredded_by_kind,
            file_object.c.shred_reason,
        ).where(file_object.c.id == UUID(str(file_id))),
    )
    return stored_row


def request_status(tenant_id: UUID, request_id: Any) -> str:
    (request,) = rows_of(
        tenant_id,
        select(approval_request.c.status).where(approval_request.c.id == UUID(str(request_id))),
    )
    return str(request["status"])


def bound_to(tenant_id: UUID, request_id: Any) -> tuple[UUID | None, list[UUID], bool]:
    """The legal entities the request froze (04 T-PLT-17 rev 1.104): ``entity_id`` for exactly
    one, ``entity_ids`` for several, ``is_all_entities`` for a request that spans every entity."""
    (request,) = rows_of(
        tenant_id,
        select(
            approval_request.c.entity_id,
            approval_request.c.entity_ids,
            approval_request.c.is_all_entities,
        ).where(approval_request.c.id == UUID(str(request_id))),
    )
    return request["entity_id"], sorted(request["entity_ids"]), bool(request["is_all_entities"])


def decisions(tenant_id: UUID, request_id: Any) -> list[Mapping[str, Any]]:
    return rows_of(
        tenant_id,
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(str(request_id))
        ),
    )


def shred_events(tenant_id: UUID, file_id: Any) -> list[Mapping[str, Any]]:
    return rows_of(
        tenant_id,
        select(
            audit_event.c.actor_kind,
            audit_event.c.on_behalf_of_id,
            audit_event.c.approval_request_id,
            audit_event.c.detail,
        ).where(
            audit_event.c.object_id == UUID(str(file_id)),
            audit_event.c.action == "file_object.shred",
            audit_event.c.outcome != "DENIED",
        ),
    )


def test_sc6_the_source_of_a_committed_import_is_shredded_only_through_an_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = import_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    priya_member = colleague(tenant_id, "priya")
    assign(priya_member, "revenue_reviewer")
    priya = enrolled(app, clock, priya_member)
    tess = tenant_admin(app, clock, tenant_id)
    cora = controller(app, clock, tenant_id, "cora")
    import_id, file_id = committed(world, priya, "crm-customers.csv", "C-911")
    number = shown(world, import_id)["import_no"]
    record = f"the source of committed import {number}"

    # One person does not shred it; the refusal names the way.
    assert_held(shred(app, tess, file_id), tenant_id, file_id, record, rule=APPROVAL_RULE)

    # The request: a reason that names the erasure request, a pending approval, nothing changed.
    short = request_shred(app, tess, file_id, reason="clean-up")
    refused_as(short, 422, "validation-failed")
    opened = request_shred(app, tess, file_id)
    assert opened.status_code == 200, opened.text
    request_id = opened.json()["approval_request_id"]
    assert opened.json()["file"]["id"] == file_id
    assert opened.json()["file"]["shredded_at"] is None
    assert request_status(tenant_id, request_id) == "PENDING"
    assert file_state(tenant_id, file_id)["shredded_at"] is None
    assert get(app, f"{FILES}/{file_id}/content", world.actor).status_code == 200
    again = request_shred(app, tess, file_id)
    assert again.status_code == 409, again.text
    detail = get(app, f"{APPROVALS}/{request_id}", cora)
    assert detail.status_code == 200, detail.text
    subject = detail.json()["subject"]
    assert (subject["type"], subject["id"]) == ("EVIDENCE_SHRED", file_id)
    (step,) = detail.json()["steps"]
    assert step["required_permission"] == "config.approve"

    # Who cannot decide it: the requester (no ``config.approve``: the privacy side never holds
    # the finance side's permission), and a reviewer who approves imports but is no Controller —
    # she holds no permission of the request's step, so she does not see it (04 API-R-09) and her
    # decision is answered as for an unknown id (04 §16.10: a decision answers 404 exactly where
    # the read does).
    refused = approve(app, request_id, tess)
    refused_as(refused, 403, "forbidden")
    hidden = get(app, f"{APPROVALS}/{request_id}", priya)
    refused_as(hidden, 404, "not-found")
    unseen = approval_sent_by(app, request_id, priya, reader=cora)
    refused_as(unseen, 404, "not-found")
    assert request_status(tenant_id, request_id) == "PENDING"
    assert decisions(tenant_id, request_id) == []
    assert file_state(tenant_id, file_id)["shredded_at"] is None

    # A Controller of every entity approves: the system shreds on the requester's behalf.
    decided = approve(app, request_id, cora)
    assert decided.status_code == 200, decided.text
    assert request_status(tenant_id, request_id) == "APPROVED"
    state = file_state(tenant_id, file_id)
    assert state["shredded_at"] is not None
    assert (state["shredded_by"], str(state["shredded_by_kind"]), state["shred_reason"]) == (
        None,
        "SYSTEM",
        REASON,
    )
    (event,) = shred_events(tenant_id, file_id)
    assert str(event["actor_kind"]) == "SYSTEM"
    assert event["on_behalf_of_id"] == tess.member.user_id
    assert str(event["approval_request_id"]) == request_id
    assert event["detail"]["lifted_holds"] == [record]
    content = get(app, f"{FILES}/{file_id}/content", world.actor)
    assert content.status_code == 404, content.text
    assert [error["rule_id"] for error in content.json()["errors"]] == ["FILE_SHREDDED"]
    after = shown(world, import_id)
    assert (after["status"], after["file"]["id"], after["header_match"]) == (
        "COMMITTED",
        file_id,
        [],
    )
    rows = get(app, f"{IMPORTS_PATH}/{import_id}/rows", world.actor)
    assert rows.status_code == 200 and len(rows.json()["items"]) == 1, rows.text
    # A shredded file takes no second request.
    spent = request_shred(app, tess, file_id)
    refused_as(spent, 409, "invalid-transition")
    assert [error["rule_id"] for error in spent.json()["errors"]] == ["FILE_SHREDDED"]

    # A rejection leaves the file as it is, and the decision is the record.
    other_id, other_file = committed(world, priya, "crm-second.csv", "C-912")
    second_request = requested(app, tess, other_file)
    assert reject(app, second_request, cora, "Not covered by the request").status_code == 200
    assert request_status(tenant_id, second_request) == "REJECTED"
    assert file_state(tenant_id, other_file)["shredded_at"] is None
    assert shown(world, other_id)["status"] == "COMMITTED"

    # The request is for a file a record holds: an upload nothing holds is shredded directly.
    draft_id, validated = imported(world, "crm-third.csv", customers_csv("C-913"), "customers")
    loose = request_shred(app, tess, validated["file"]["id"])
    refused_as(loose, 409, "invalid-transition")
    (error,) = loose.json()["errors"]
    assert (error["rule_id"], error["message"]) == ("PRV-07", evidence_shred.NOT_HELD)
    assert shown(world, draft_id)["status"] == "VALIDATED"

    # ... and a file a record holds WITHOUT override takes no request either (R-49 (b)).
    pending_id, pending_file, _request = submitted(world, "crm-fourth.csv", "C-914")
    blocked = request_shred(app, tess, pending_file)
    refused_as(blocked, 409, "invalid-transition")
    assert [error["rule_id"] for error in blocked.json()["errors"]] == [RULE]
    assert shown(world, pending_id)["status"] == "SUBMITTED"


CONTRACT_HEADERS = (
    "external_id",
    "customer_id",
    "contracting_entity_code",
    "transaction_currency",
    "inception_date",
    "document_ref",
    "lines.obligation_key",
    "lines.product_code",
    "lines.quantity",
    "lines.total_price.amount",
    "lines.total_price.currency",
    "lines.start_date",
    "lines.end_date",
    "lines.performing_entity_code",
)


def contracts_csv(customer_id: UUID, external_id: str, contracting: str = "AVM-US") -> bytes:
    """PRD WLD-F-20 as a CSV v2 ``contracts`` file: contracted by ``contracting``, O2 performed
    by AVM-UK."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CONTRACT_HEADERS)
    header = [external_id, str(customer_id), contracting, "USD", "2026-09-01", external_id]
    writer.writerow(
        [*header, "O1", "AVM-PLAT-100", "1", "96000.00", "USD", "2026-09-01", "2027-08-31", ""]
    )
    writer.writerow([*header, "O2", "AVM-IMPL-PLUS", "1", "24000.00", "USD", "", "", "AVM-UK"])
    return buffer.getvalue().encode("utf-8")


def test_sc6_the_shred_request_is_decided_by_a_controller_of_the_records_entities(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """R-49 (a) with R-25 / R-41: the request is bound to every entity the import names
    (``named_entity_ids``) — to every entity for an import that names none — and the approvals
    kernel holds everyone to that set (04 §16.10 "Entity scope of a request"): the requester's
    own scope covers it, the request is read only inside it, and the decider's ``config.approve``
    and Controller role cover every entity of it. A requester who is also a Controller does not
    approve her own request."""
    j03: J03World = j03_world(app, keyring, clock, files)
    tenant_id = j03.place.tenant_id
    maya = ImportWorld(
        app=app,
        actor=j03.place.author,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
        clock=clock,
    )
    assign(j03.priya.member, "revenue_reviewer")  # every entity; MFA enrolled
    # Dana is a Tenant Admin AND a Controller of every entity: she may request, not decide.
    dana_member = colleague(tenant_id, "dana")
    assign(dana_member, "tenant_admin")
    assign(dana_member, "controller")
    dana = enrolled(app, clock, dana_member)
    cody = controller(app, clock, tenant_id, "cody", entity_ids=[j03.uk_entity_id])
    # Una administers AVM-UK only.
    una_member = colleague(tenant_id, "una")
    assign(una_member, "tenant_admin", entity_ids=[j03.uk_entity_id])
    una = enrolled(app, clock, una_member)

    # An import that names AVM-US and AVM-UK: a contract of each (04 T-IMP-02 rev 1.256 — the
    # entity that performs a line is no named entity, which is how one contract named both).
    of_uk = contracts_csv(j03.customer_id, "UK-ORD-30001", contracting="AVM-UK")
    import_id, validated = imported(
        maya,
        "sf-ord-30001.csv",
        contracts_csv(j03.customer_id, "SF-ORD-30001") + of_uk.split(b"\n", 1)[1],
        "contracts",
    )
    assert validated["status"] == "VALIDATED", validated
    run_import_job(maya, job_of(maya, import_id, "IMPORT_DIFF"))
    submitted_import = post(app, f"{IMPORTS_PATH}/{import_id}/submit", maya.actor, {"comment": "x"})
    assert submitted_import.status_code == 200, submitted_import.text
    request = str(submitted_import.json()["approval_request_id"])
    assert approve(app, request, j03.priya).status_code == 200
    run_import_job(maya, job_of(maya, import_id, "IMPORT_COMMIT"))
    assert shown(maya, import_id)["status"] == "COMMITTED"
    file_id = validated["file"]["id"]

    # The requester's own scope covers every entity of the records (R-64 (6)): an administrator
    # of AVM-UK alone opens no request for a file that a record of AVM-US holds too.
    outside = request_shred(app, una, file_id)
    refused_as(outside, 403, "forbidden")
    assert outside.json()["detail"] == approvals_engine.OUTSIDE_SCOPE_DETAIL

    request_id = requested(app, dana, file_id)
    assert bound_to(tenant_id, request_id) == (
        None,
        sorted([j03.entity_id, j03.uk_entity_id]),
        False,
    )
    own = approve(app, request_id, dana)  # REQ-PLT-011
    refused_as(own, 403, "self-approval")
    # A Controller of AVM-UK only reads the request — it names an entity of his — and does not
    # decide it: one authority covers every entity the request names.
    assert get(app, f"{APPROVALS}/{request_id}", cody).status_code == 200
    partial = approve(app, request_id, cody)
    refused_as(partial, 403, "forbidden")
    assert partial.json()["detail"] == approvals_engine.EVERY_ENTITY_DETAIL
    assert request_status(tenant_id, request_id) == "PENDING"
    assert file_state(tenant_id, file_id)["shredded_at"] is None
    assert decisions(tenant_id, request_id) == []
    decided = approve(app, request_id, j03.marcus)  # Controller of every entity
    assert decided.status_code == 200, decided.text
    assert file_state(tenant_id, file_id)["shredded_at"] is not None

    # An import that names no entity needs a decider for every entity.
    customers_id, customers = imported(
        maya, "crm-customers.csv", customers_csv("C-921"), "customers"
    )
    run_import_job(maya, job_of(maya, customers_id, "IMPORT_DIFF"))
    sent = post(app, f"{IMPORTS_PATH}/{customers_id}/submit", maya.actor, {"comment": "x"})
    assert approve(app, str(sent.json()["approval_request_id"]), j03.priya).status_code == 200
    run_import_job(maya, job_of(maya, customers_id, "IMPORT_COMMIT"))
    unbound = request_shred(app, una, customers["file"]["id"])
    refused_as(unbound, 403, "forbidden")
    tenant_level = requested(app, dana, customers["file"]["id"])
    assert bound_to(tenant_id, tenant_level) == (None, [], True)
    # A request that spans every entity is read and decided under scope "*" only: to a
    # Controller of one entity it is an unknown id.
    assert get(app, f"{APPROVALS}/{tenant_level}", cody).status_code == 404
    narrow = approval_sent_by(app, tenant_level, cody, reader=j03.marcus)
    refused_as(narrow, 404, "not-found")
    wide = approve(app, tenant_level, j03.marcus)
    assert wide.status_code == 200, wide.text
    assert file_state(tenant_id, customers["file"]["id"])["shredded_at"] is not None


# --- the other documents a record rests on (R-86 (b), (c)) ---------------------------------------


def stored(world: CloseWorld, purpose: FilePurpose, name: str) -> UUID:
    """A stored file of ``purpose`` — object and wrapped key — so that a shred acts on it. The
    content is of a type the purpose admits (05 UPL-02) and unique, as a content identity is."""
    mark = f"{name} {uuid4()}".encode()
    content, filename, media_type = {
        FilePurpose.IMPORT_SOURCE: (
            b"account,amount\n" + mark + b",1.00\n",
            f"{name}.csv",
            "text/csv",
        ),
        FilePurpose.LEGACY_DATABASE: (
            b"SQLite format 3\x00" + mark,
            name,
            "application/vnd.sqlite3",
        ),
    }.get(purpose, (PDF + b"% " + mark + b"\n", f"{name}.pdf", "application/pdf"))
    with world.place.uow() as uow:
        row = store_file(
            uow,
            purpose=purpose,
            stream=io.BytesIO(content),
            original_filename=filename,
            media_type=media_type,
        )
        uow.commit()
    return UUID(str(row["id"]))


def attach(
    session: Session, tenant_id: UUID, file_id: UUID, subject_type: str, subject: Any
) -> UUID:
    """A live T-PLT-30 attachment of ``file_id`` to a subject row."""
    row = {
        "tenant_id": tenant_id,
        "id": uuid4(),
        "file_object_id": file_id,
        "subject_type": subject_type,
        "subject_id": UUID(str(subject)),
        "created_by_kind": "SYSTEM",
    }
    session.execute(insert(file_attachment).values(**row))
    return UUID(str(row["id"]))


def released_by_approval(
    app: FastAPI,
    tess: Actor,
    tenant_id: UUID,
    file_id: UUID,
    record: str,
    *,
    entity_id: UUID | None,
    refused: Actor | None,
    approver: Actor,
) -> None:
    """One administrator is refused by the rule that names the approved path; the request is
    bound to the record's entity — to every entity for a record without one (``entity_id``
    None); a Controller whose scope does not reach it neither reads nor decides the request (404,
    as for an unknown id), and the approval of one whose scope covers it shreds the file."""
    assert_held(shred(app, tess, file_id), tenant_id, file_id, record, rule=APPROVAL_RULE)
    request_id = requested(app, tess, file_id)
    assert bound_to(tenant_id, request_id) == (entity_id, [], entity_id is None)
    if refused is not None:
        assert get(app, f"{APPROVALS}/{request_id}", refused).status_code == 404
        outside = approval_sent_by(app, request_id, refused, reader=approver)
        refused_as(outside, 404, "not-found")
        assert file_state(tenant_id, file_id)["shredded_at"] is None
    decided = approve(app, request_id, approver)
    assert decided.status_code == 200, decided.text
    assert file_state(tenant_id, file_id)["shredded_at"] is not None
    (event,) = shred_events(tenant_id, file_id)
    assert str(event["approval_request_id"]) == request_id
    assert event["detail"]["lifted_holds"] == [record]


def shredded_directly(app: FastAPI, tess: Actor, file_id: UUID) -> None:
    done = shred(app, tess, file_id)
    assert done.status_code == 200 and done.json()["shredded_at"] is not None, done.text


def test_sc6_the_documents_a_record_rests_on_are_released_only_by_an_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ruling R-86 (b), (c). The source file of a reconciliation, the legacy database of a
    migration and the attachment of a manual adjustment are shredded by one administrator while
    no record rests on them — a DRAFT reconciliation, a PROFILED batch, an adjustment whose
    request needed no attachment, a draft, a discarded draft — and only through the approval of
    a Controller of the record's entity once one does: signed, captured, submitted with the
    attachment its request needed. (The SSP study is the next test: the product submits its
    version.)

    An adjustment "needed" its attachment when its request carries ``ABOVE_THRESHOLD``: the
    command compares the amount in USD at the spot rate of the effective date (PRD §2.5), so
    the stored functional amount says it for USD entities only. ``support-below`` is such a row:
    9,000.00 in its functional currency, with the flag. The product's own path — create,
    attach, submit, withdraw — is witnessed in ``tests/domain/journals/test_adjustments.py``."""
    world = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    tess = tenant_admin(app, clock, tenant_id)
    cora = controller(app, clock, tenant_id, "cora")  # every entity
    with system_session(world) as session:
        uk = other_entity(session, world)
    cody = controller(app, clock, tenant_id, "cody", entity_ids=[uk])  # AVM-UK only
    ursula = controller(app, clock, tenant_id, "ursula", entity_ids=[world.entity_id])  # AVM-US
    names = ("tb-signed", "tb-draft", "db-captured", "db-profiled")
    names += ("support-large", "support-small", "support-draft")
    names += ("support-below", "support-discarded")
    purposes = {
        "tb": FilePurpose.IMPORT_SOURCE,
        "db": FilePurpose.LEGACY_DATABASE,
        "support": FilePurpose.ATTACHMENT,
    }
    file_of = {name: stored(world, purposes[name.split("-")[0]], name) for name in names}
    now = world.place.clock.now()
    stamps = {"updated_at": now, "updated_by": None, "updated_by_kind": "SYSTEM"}
    with system_session(world) as session:
        # a reconciliation of AVM-US that has been signed, and one still DRAFT
        recon = {
            name: reconciliation_values(
                tenant_id,
                entity_id=world.entity_id,
                period_id=world.period_id,
                source_file_id=file_of[name],
            )
            for name in ("tb-signed", "tb-draft")
        }
        for row in recon.values():
            session.execute(insert(reconciliation).values(**row))
        transitions.apply(
            session,
            "reconciliation",
            UUID(str(recon["tb-signed"]["id"])),
            to_status="PREPARED",
            expected_status="DRAFT",
            set_values=dict(stamps),
        )
        # a migration whose capture is relied on (IMPORTED), and one only profiled
        batch = {
            "db-captured": migration_batch_values(
                tenant_id, source_file_id=file_of["db-captured"], status="IMPORTED"
            ),
            "db-profiled": migration_batch_values(
                tenant_id, source_file_id=file_of["db-profiled"], status="PROFILED"
            ),
        }
        for row in batch.values():
            session.execute(insert(migration_batch).values(**row))
        # manual adjustments of AVM-US, each with the request it stands under (T-SL-05
        # ``approval_request_id``): the amount, the request's flags, the status it ends in
        contract_id, _event_id, _group_id = contract_of(session, world)
        cases: dict[str, tuple[str, list[str] | None, str]] = {
            "support-large": ("10000.00", ["ABOVE_THRESHOLD"], "SUBMITTED"),
            "support-small": ("9999.99", [], "SUBMITTED"),
            "support-draft": ("25000.00", None, "DRAFT"),  # never submitted: no request
            "support-below": ("9000.00", ["ABOVE_THRESHOLD"], "SUBMITTED"),
            "support-discarded": ("25000.00", ["ABOVE_THRESHOLD"], "VOIDED"),  # a withdrawn draft
        }
        adjustment: dict[str, dict[str, Any]] = {}
        for name, (amount, flags, status) in cases.items():
            row = manual_adjustment_values(
                tenant_id,
                contract_id=contract_id,
                entity_id=world.entity_id,
                period_id=world.period_id,
                amount_functional_abs=Decimal(amount),
            )
            if flags is not None:
                request = approval_request_values(
                    tenant_id,
                    subject_type="MANUAL_ADJUSTMENT",
                    subject_id=row["id"],
                    entity_id=world.entity_id,
                    flags=flags,
                )
                session.execute(insert(approval_request).values(**request))
                row["approval_request_id"] = request["id"]
            adjustment[name] = row
            session.execute(insert(manual_adjustment).values(**row))
            attach(session, tenant_id, file_of[name], "manual_adjustment", row["id"])
            if status != "DRAFT":
                transitions.apply(
                    session,
                    "manual_adjustment",
                    UUID(str(row["id"])),
                    to_status=status,
                    expected_status="DRAFT",
                    set_values=dict(stamps),
                )

    # No record rests on these: one administrator erases them, as 05 PRV-07 (b) has it.
    erasable = ("tb-draft", "db-profiled", "support-small", "support-draft", "support-discarded")
    for name in erasable:
        assert file_evidence.holds(tenant_id, file_of[name]) == (), name
        shredded_directly(app, tess, file_of[name])

    # The request is bound to the record's own entity, or to every entity without one.
    released_by_approval(
        app,
        tess,
        tenant_id,
        file_of["tb-signed"],
        f"the source file of reconciliation {recon['tb-signed']['reconciliation_no']}, which has "
        "been signed",
        entity_id=world.entity_id,
        refused=cody,
        approver=ursula,
    )
    released_by_approval(
        app,
        tess,
        tenant_id,
        file_of["db-captured"],
        f"the legacy database of migration {batch['db-captured']['migration_no']}, whose capture "
        "is relied on",
        entity_id=None,
        refused=ursula,  # a batch has no entity: a Controller of one entity does not cover it
        approver=cora,
    )
    for name in ("support-large", "support-below"):
        released_by_approval(
            app,
            tess,
            tenant_id,
            file_of[name],
            f"the supporting attachment of manual adjustment "
            f"{adjustment[name]['adjustment_no']}, which has been submitted",
            entity_id=world.entity_id,
            refused=cody,
            approver=ursula,
        )


def test_sc6_the_study_of_a_submitted_ssp_version_is_released_only_by_an_approval(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ruling R-86 (c): the study is a condition of a version's submission
    (``ssp-study-required``). The study of US-LIST 2026-H1 — uploaded, attached, submitted and
    approved through the product — is refused to one administrator and shredded by the approval
    of a Controller of every entity (the book has none of its own); the study of a version that
    is still DRAFT is shredded directly."""
    j03: J03World = j03_world(app, keyring, clock, files)
    tenant_id = j03.place.tenant_id
    maya = j03.place.author
    tess = tenant_admin(app, clock, tenant_id)
    cody = controller(app, clock, tenant_id, "cody", entity_ids=[j03.uk_entity_id])
    (study,) = rows_of(
        tenant_id,
        select(file_attachment.c.file_object_id).where(
            file_attachment.c.subject_type == "ssp_book_version",
            file_attachment.c.subject_id == UUID(j03.version_id),
            file_attachment.c.voided_at.is_(None),
        ),
    )
    (version,) = rows_of(
        tenant_id,
        select(ssp_book.c.code, ssp_book.c.entity_id, ssp_book_version.c.version_no)
        .join(ssp_book_version, ssp_book_version.c.ssp_book_id == ssp_book.c.id)
        .where(ssp_book_version.c.id == UUID(j03.version_id)),
    )
    assert (version["code"], version["entity_id"]) == ("US-LIST", None)

    # A second version of the book, still DRAFT, with a study of its own.
    drafted = post(
        app,
        f"/api/v1/ssp-books/{j03.book_id}/versions",
        maya,
        {
            "legacy_version_label": "2026-H2",
            "effective_from_date": "2026-07-01",
            "methodology_label": "List-price study",
        },
    )
    assert drafted.status_code == 201, drafted.text
    uploaded = call(
        app,
        "POST",
        FILES,
        data={"purpose": "SSP_STUDY"},
        files={"file": ("study-h2.pdf", PDF + b"% 2026-H2\n", "application/pdf")},
        headers=cookie_headers(maya.token, maya.csrf_token),
    )
    assert uploaded.status_code == 201, uploaded.text
    attached = post(
        app,
        "/api/v1/attachments",
        maya,
        {
            "file_object_id": uploaded.json()["id"],
            "subject_type": "ssp_book_version",
            "subject_id": drafted.json()["id"],
        },
    )
    assert attached.status_code == 201, attached.text
    assert file_evidence.holds(tenant_id, UUID(uploaded.json()["id"])) == ()
    shredded_directly(app, tess, UUID(uploaded.json()["id"]))

    study_id = UUID(str(study["file_object_id"]))
    released_by_approval(
        app,
        tess,
        tenant_id,
        study_id,
        f"the SSP study of SSP book US-LIST version {version['version_no']}, which has been "
        "submitted",
        entity_id=None,  # a book without an entity
        refused=cody,
        approver=j03.marcus,
    )


def test_sc6_an_approval_lifts_the_holds_it_names_and_no_other(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The approval certifies a proposal that names the records holding the file. A record that
    comes to hold the file after the request — here a second signed reconciliation on the same
    extract — refuses the decision by name; so does a legal hold set since (the content is
    stale); and a record that holds the file without override refuses the request itself."""
    world = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    tess = tenant_admin(app, clock, tenant_id)
    cora = controller(app, clock, tenant_id, "cora")
    now = world.place.clock.now()
    stamps = {"updated_at": now, "updated_by": None, "updated_by_kind": "SYSTEM"}

    def signed(file_id: UUID) -> Mapping[str, Any]:
        row = reconciliation_values(
            tenant_id, entity_id=world.entity_id, period_id=world.period_id, source_file_id=file_id
        )
        with system_session(world) as session:
            session.execute(insert(reconciliation).values(**row))
            transitions.apply(
                session,
                "reconciliation",
                UUID(str(row["id"])),
                to_status="PREPARED",
                expected_status="DRAFT",
                set_values=dict(stamps),
            )
        return row

    # --- a second record comes to hold the file between the request and the decision
    extract = stored(world, FilePurpose.IMPORT_SOURCE, "trial-balance")
    first = signed(extract)
    request_id = requested(app, tess, extract)
    second = signed(extract)
    assert len(file_evidence.holds(tenant_id, extract)) == 2
    changed = approve(app, request_id, cora)
    refused_as(changed, 409, "invalid-transition")
    (error,) = changed.json()["errors"]
    assert (error["rule_id"], error["message"]) == ("PRV-07", evidence_shred.HOLDS_CHANGED)
    assert request_status(tenant_id, request_id) == "PENDING"
    assert decisions(tenant_id, request_id) == []
    assert file_state(tenant_id, extract)["shredded_at"] is None
    # the repair: reject, request again — the new proposal names both records — and approve
    assert reject(app, request_id, cora, "Another reconciliation rests on it").status_code == 200
    again = requested(app, tess, extract)
    assert approve(app, again, cora).status_code == 200
    (event,) = shred_events(tenant_id, extract)
    assert sorted(event["detail"]["lifted_holds"]) == sorted(
        f"the source file of reconciliation {row['reconciliation_no']}, which has been signed"
        for row in (first, second)
    )

    # --- a legal hold set since the request: the file's own refusals stand at the decision
    held = stored(world, FilePurpose.IMPORT_SOURCE, "billing-extract")
    signed(held)
    on_hold = requested(app, tess, held)
    with system_session(world) as session:
        session.execute(update(file_object).where(file_object.c.id == held).values(legal_hold=True))
    refused = approve(app, on_hold, cora)
    assert refused.status_code == 409, refused.text
    assert file_state(tenant_id, held)["shredded_at"] is None

    # --- a record that holds the file without override: no request (R-49 (b))
    both = stored(world, FilePurpose.IMPORT_SOURCE, "extract-and-preview")
    signed(both)
    with system_session(world) as session:
        pinned = approval_request_values(
            tenant_id, entity_id=world.entity_id, impact_preview_file_id=both
        )
        session.execute(insert(approval_request).values(**pinned))
    blocked = request_shred(app, tess, both)
    refused_as(blocked, 409, "invalid-transition")
    assert [error["rule_id"] for error in blocked.json()["errors"]] == [RULE]
    assert_held(
        shred(app, tess, both), tenant_id, both, "the impact preview of an approval request"
    )


def test_sc6_every_refusal_of_file_shred_is_audited_as_denied(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Ruling R-86 (f): one rule for every refusal of a destructive command. Beside the evidence
    refusals, ``file.shred`` refused because the file is under a legal hold or retention, already
    shredded, or stored in plaintext is on the audit log as ``DENIED`` with its rule, the file's
    SHA-256 and the requester's reason."""
    world = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    tess = tenant_admin(app, clock, tenant_id)

    def denied(file_id: UUID) -> list[str]:
        return [
            str(row["detail"]["rule_id"])
            for row in rows_of(
                tenant_id,
                select(audit_event.c.detail, audit_event.c.chain_seq)
                .where(
                    audit_event.c.object_id == file_id,
                    audit_event.c.action == "file_object.shred",
                    audit_event.c.outcome == "DENIED",
                )
                .order_by(audit_event.c.chain_seq),
            )
        ]

    def refused_by(file_id: UUID, rule: str) -> None:
        response = shred(app, tess, file_id)
        refused_as(response, 409, "invalid-transition")
        assert [error["rule_id"] for error in response.json()["errors"]] == [rule]

    # legal hold, then retention, then — once both are lifted — shredded, then shredded again
    document = stored(world, FilePurpose.ATTACHMENT, "personal")
    with system_session(world) as session:
        session.execute(
            update(file_object).where(file_object.c.id == document).values(legal_hold=True)
        )
    refused_by(document, privacy.RULE_RETENTION_ACTIVE)
    later = world.place.clock.now().date() + timedelta(days=30)
    with system_session(world) as session:
        session.execute(
            update(file_object)
            .where(file_object.c.id == document)
            .values(legal_hold=False, retention_until=later)
        )
    refused_by(document, privacy.RULE_RETENTION_ACTIVE)
    with system_session(world) as session:
        session.execute(
            update(file_object).where(file_object.c.id == document).values(retention_until=None)
        )
    shredded_directly(app, tess, document)
    refused_by(document, privacy.RULE_SHREDDED)
    assert denied(document) == [
        privacy.RULE_RETENTION_ACTIVE,
        privacy.RULE_RETENTION_ACTIVE,
        privacy.RULE_SHREDDED,
    ]

    # a plaintext purpose that no record references
    with system_session(world) as session:
        plain = file_object_values(tenant_id, purpose=FilePurpose.AI_PROMPT_LOG)
        session.execute(insert(file_object).values(**plain))
    plain_id = UUID(str(plain["id"]))
    refused_by(plain_id, privacy.RULE_PLAINTEXT_PURPOSE)
    assert denied(plain_id) == [privacy.RULE_PLAINTEXT_PURPOSE]
    (event,) = rows_of(
        tenant_id,
        select(audit_event.c.detail).where(
            audit_event.c.object_id == plain_id, audit_event.c.outcome == "DENIED"
        ),
    )
    assert event["detail"] == {
        "permission": "settings.manage",
        "rule_id": privacy.RULE_PLAINTEXT_PURPOSE,
        "sha256": plain["sha256"],
        "purpose": "AI_PROMPT_LOG",
        "reason": REASON,
    }
