"""An import needs its source (supervisor ruling R-98 (1) on the independent review of merge
4ac6c1d1; 04 rev 1.147 §16.6, table 15.4-B ``FILE_SHREDDED``; 05 rev 1.86 IPL-08, IPL-10, PRV-07 b;
dev-guide rev 1.130 DG-KRN-DB-08; PRD IMP-50; 03 REQ-DAT-001).

A source was held from its submission on, and neither the submission nor the commit read whether
the file had been shredded: Tess, a Tenant Admin, shredded the source of an upload that was ready
to submit, the uploader submitted it, and the import was approved and committed without its
original file. The submission and the commit now lock the source's ``file_object`` row and refuse
a shredded source by name; ``file.shred`` takes the same row lock first, so the two are
serialised on it.

World ``support.factories.import_world``: a Revenue Accountant uploads ``customers`` files; Priya
is a Revenue Reviewer; Tess holds ``settings.manage`` and no finance permission.
"""

from __future__ import annotations

import csv
import io
import threading
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_request,
    customer,
    exception_item,
    file_object,
    import_upload,
    job,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, update
from support.db import TestDatabase
from support.factories import IMPORTS_PATH, ImportWorld, import_world, imported, run_import_job
from support.http import HttpResponse
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, get, post, slug

FILES = "/api/v1/files"
REASON = "DSR-2026-0917: erase the person's data in this document"
RULE = "FILE_SHREDDED"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ImportWorld:
    return import_world(app, keyring, clock, files)


def customers_csv(code: str) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("code", "name", "segment", "country_code"))
    writer.writerow((code, "Harbourline Freight Ltd (Demo)", "Logistics", "PT"))
    return buffer.getvalue().encode("utf-8")


def tenant_admin(world: ImportWorld) -> Actor:
    """Tess: a Tenant Admin (``settings.manage``, MFA) without a finance permission."""
    someone = colleague(world.tenant_id, "tess")
    assign(someone, "tenant_admin")
    return enrolled(world.app, world.clock, someone)


def reviewer(world: ImportWorld) -> Actor:
    someone = colleague(world.tenant_id, "priya")
    assign(someone, "revenue_reviewer")
    return enrolled(world.app, world.clock, someone)


def job_of(world: ImportWorld, import_id: str, kind: str) -> UUID:
    found = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == UUID(import_id), job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    return UUID(str(found[-1]["id"]))


def diffed(world: ImportWorld, name: str, code: str) -> tuple[str, dict[str, Any]]:
    """A ``customers`` upload validated and diffed: (import id, the file of API-S-Import)."""
    import_id, validated = imported(world, name, customers_csv(code), "customers")
    assert validated["status"] == "VALIDATED", validated
    run_import_job(world, job_of(world, import_id, "IMPORT_DIFF"))
    assert status_of(world, import_id) == "DIFF_READY"
    return import_id, dict(validated["file"])


def status_of(world: ImportWorld, import_id: str) -> str:
    return str(
        world.scalar(select(import_upload.c.status).where(import_upload.c.id == UUID(import_id)))
    )


def submit(world: ImportWorld, import_id: str) -> HttpResponse:
    return post(
        world.app, f"{IMPORTS_PATH}/{import_id}/submit", world.actor, {"comment": "customers"}
    )


def requests_of(world: ImportWorld, import_id: str) -> list[dict[str, Any]]:
    return world.rows(
        select(approval_request.c.id).where(approval_request.c.subject_id == UUID(import_id))
    )


def customers(world: ImportWorld, code: str) -> list[dict[str, Any]]:
    return world.rows(select(customer.c.id).where(customer.c.code == code))


def assert_refused_by_name(refused: HttpResponse, name: str, on: str) -> None:
    """409 by name, with the copy of PRD IMP-50."""
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "invalid-transition", refused.text
    message = f"The content of {name} was shredded on {on}. Its SHA-256 remains as evidence."
    assert refused.json()["detail"] == message
    assert [(error["rule_id"], error["message"]) for error in refused.json()["errors"]] == [
        (RULE, message)
    ]


def test_r98_an_import_whose_source_was_shredded_is_not_submitted(
    world: ImportWorld, clock: FrozenClock
) -> None:
    """The reviewer's scenario inverted: the source of a DIFF_READY upload is shredded by one
    administrator (no record holds it yet, so the shred succeeds) — and the upload can then not
    be submitted: 409 by name, the import stays DIFF_READY, no approval request exists. It can
    be cancelled. Positive control: the same file under another customer code, not shredded, is
    submitted, approved and committed."""
    app = world.app
    tess, priya = tenant_admin(world), reviewer(world)
    import_id, source = diffed(world, "crm-customers.csv", "C-901")

    gone = post(app, f"{FILES}/{source['id']}/shred", tess, {"reason": REASON})
    assert gone.status_code == 200 and gone.json()["shredded_at"] is not None, gone.text

    refused = submit(world, import_id)
    assert_refused_by_name(refused, "crm-customers.csv", clock.now().date().isoformat())
    assert status_of(world, import_id) == "DIFF_READY"
    assert requests_of(world, import_id) == []
    assert customers(world, "C-901") == []
    cancelled = post(app, f"{IMPORTS_PATH}/{import_id}/cancel", world.actor, {})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"

    # Positive control: a source that was not shredded.
    kept_id, _ = diffed(world, "crm-second.csv", "C-902")
    submitted = submit(world, kept_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), priya)
    assert decided.status_code == 200, decided.text
    run_import_job(world, job_of(world, kept_id, "IMPORT_COMMIT"))
    assert status_of(world, kept_id) == "COMMITTED"
    assert len(customers(world, "C-902")) == 1


def test_r98_an_approved_import_whose_source_is_gone_commits_nothing(
    world: ImportWorld, clock: FrozenClock
) -> None:
    """The backstop at the commit, for an upload submitted before the rule: its source row reads
    shredded when the commit job runs (a state ``file.shred`` no longer produces — the source of
    a submitted import is held — so the row is marked directly, as such a row would stand). The
    commit fails by name and writes nothing; no import is committed without its original file
    (REQ-DAT-001)."""
    priya = reviewer(world)
    import_id, source = diffed(world, "crm-customers.csv", "C-903")
    submitted = submit(world, import_id)
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), priya)
    assert decided.status_code == 200, decided.text
    assert status_of(world, import_id) == "APPROVED"

    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        session.execute(
            update(file_object)
            .where(file_object.c.id == UUID(str(source["id"])))
            .values(shredded_at=clock.now(), shredded_by_kind="SYSTEM", shred_reason=REASON)
        )

    run_import_job(world, job_of(world, import_id, "IMPORT_COMMIT"))
    assert status_of(world, import_id) == "FAILED"
    assert customers(world, "C-903") == []
    (item,) = world.rows(
        select(exception_item.c.code, exception_item.c.message).where(
            exception_item.c.import_upload_id == UUID(import_id)
        )
    )
    assert str(item["code"]) == "IMPORT_PROCESSING_FAILED"
    on = clock.now().date().isoformat()
    assert str(item["message"]).startswith(
        f"The content of crm-customers.csv was shredded on {on}. Its SHA-256 remains as "
        "evidence. The import could not be committed and nothing was committed. Reference: "
    ), item


def test_r98_a_shred_and_a_submission_are_serialised_on_the_file_row(
    world: ImportWorld, clock: FrozenClock
) -> None:
    """The race of the review: a shred interleaved with a submission did not see the uncommitted
    SUBMITTED, and the submission did not see the uncommitted shred. A holder session takes the
    source's row lock and marks the row shredded, as ``file.shred`` does, and stays open; the
    submission, in another connection, is observed WAITING in its own lock of that row — the
    statement it waits in is the ``FOR UPDATE`` of the ``file_object`` row, taken before it
    changes anything — and, once the holder commits, answers by name: nothing is submitted on a
    source that was shredded while the submission ran.

    Before the rule the submission waited behind the holder as well, but late and by accident —
    in the foreign-key check of its second ``UPDATE`` of the upload row, the status already
    moved — and then committed SUBMITTED on the shredded source; so the wait alone proves
    nothing, and the statement is named."""
    import_id, source = diffed(world, "crm-customers.csv", "C-904")
    file_id = UUID(str(source["id"]))
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = submit(world, import_id)
        except Exception as error:  # noqa: BLE001 — surfaced by the assertions below
            outcome["error"] = error

    with observing_checkouts() as backends:
        with tenant_session(context) as holder:
            holder_pid = backend_pid(holder)
            holder.execute(
                select(file_object.c.id).where(file_object.c.id == file_id).with_for_update()
            ).one()
            holder.execute(
                update(file_object)
                .where(file_object.c.id == file_id)
                .values(shredded_at=clock.now(), shredded_by_kind="SYSTEM", shred_reason=REASON)
            )
            request = threading.Thread(target=run, name="interleaved-submit")
            request.start()
            blocked_pid, blocked_in = await_lock_wait(
                holder,
                holder_pid=holder_pid,
                backends=backends,
                timeout=20.0,
                expect="from erev.file_object",
            )
            assert blocked_pid != holder_pid and request.is_alive(), (blocked_pid, blocked_in)
            assert "for update" in blocked_in.lower(), blocked_in
            # Nothing was submitted while the shred was in flight.
            assert status_of(world, import_id) == "DIFF_READY"
        # the holder's transaction committed on leaving the block: the row is shredded
    request.join(timeout=30)
    assert not request.is_alive() and "error" not in outcome, outcome
    assert_refused_by_name(outcome["result"], "crm-customers.csv", clock.now().date().isoformat())
    assert status_of(world, import_id) == "DIFF_READY"
    assert requests_of(world, import_id) == []
    shown = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor)
    assert shown.status_code == 200 and shown.json()["status"] == "DIFF_READY", shown.text
