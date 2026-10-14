"""Operational first-close evidence acceptance (RPS-16 / CTL-041).

Product commands generate the close run, journal and reconciliations. Prior periods are
closed as fixture state. The uploaded GL is a synthetic matching reference, not an independent
accounting oracle; this test proves evidence lineage, lifecycle and archive integrity.
"""

from __future__ import annotations

import hashlib
import io
import json
from copy import copy
from dataclasses import replace
from datetime import timedelta
from uuid import UUID
from zipfile import ZipFile

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import evidence_pack, gl_account, job, legal_entity, period_lock
from erev_api.domain.platform import audit_jobs  # noqa: F401 - register the actual audit worker
from erev_api.domain.reports import (
    evidence,  # noqa: F401 - register the actual pack worker
    evidence_archive,
    evidence_sources,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support import close_runs as runs
from support import reconciliations as recon
from support import worlds
from support.close_world import actor_with_role, periods_closed_before
from support.db import TestDatabase
from support.principals import enrolled
from support.reference import PERIODS, approve, assign, get, post


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.mark.control("CTL-041")
def test_ctl_041_close_pack_manifest(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = worlds.k01_pellworth(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    world = worlds.on_record_clock(world, clock)
    world = replace(
        world, place=replace(world.place, author=enrolled(app, clock, world.maya.member))
    )
    entity_id = world.place.scalar(select(legal_entity.c.id).where(legal_entity.c.code == "AVM-US"))
    periods_closed_before(world.place, app, world.maya, entity_id=entity_id, before="FY2026-P09")
    state = worlds.period_state(world, "AVM-US", "FY2026-P09")
    started = post(
        app,
        f"{PERIODS}/{state['id']}/start-close",
        world.maya,
        {"comment": "September evidence acceptance"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    close = runs.closed(world, monkeypatch, entity_code="AVM-US", period_key="FY2026-P09")
    assert close["status"] == "SUCCEEDED", close
    assert close["journal_run_id"] is not None
    world = runs.journal_posted(world, clock, close["journal_run_id"])

    reviewed_ids = set()
    for kind in (recon.BILLING, recon.SUBLEDGER_TO_GL):
        draft = recon.generated(
            app, world.maya, world.runtime, entity_code="AVM-US", period_key="FY2026-P09", kind=kind
        )
        if kind == recon.SUBLEDGER_TO_GL:
            # A matching synthetic GL upload exercises the source-file path; amounts are
            # not used as an oracle for the engine's accounting calculations.
            # The initial draft deliberately has no totals until a source is attached.
            # Read a zero-valued fixture once, then supply a matching synthetic reference.
            accounts = world.place.rows(select(gl_account.c.code).order_by(gl_account.c.code))
            initial_id = recon.uploaded(
                app,
                world.maya,
                "september-zero-reference.csv",
                recon.trial_balance_csv([(row["code"], "USD", "0.00") for row in accounts]),
            )
            comparison = recon.attached(
                app, world.maya, world.runtime, draft["id"], {"file_id": initial_id}
            )
            assert comparison["totals"], comparison
            assert all(row["subledger_amount"] is not None for row in comparison["totals"])
            reference = [
                (row["account_code"], row["currency"], row["subledger_amount"]["amount"])
                for row in comparison["totals"]
            ]
            draft = recon.generated(
                app,
                world.maya,
                world.runtime,
                entity_code="AVM-US",
                period_key="FY2026-P09",
                kind=kind,
            )
            source_id = recon.uploaded(
                app,
                world.maya,
                "september-test-trial-balance.csv",
                recon.trial_balance_csv(reference),
            )
            draft = recon.attached(
                app, world.maya, world.runtime, draft["id"], {"file_id": source_id}
            )
        assert draft["variance_count"] == 0, draft
        prepared = recon.prepare(app, world.maya, draft["id"])
        assert prepared.status_code == 200, prepared.text
        world = worlds.verified(world, clock, "priya")
        signed = recon.sign(app, world.priya, draft["id"])
        assert signed.status_code == 200, signed.text
        assert signed.json()["status"] == "REVIEWED"
        reviewed_ids.add(draft["id"])

    state = worlds.period_state(world, "AVM-US", "FY2026-P09")
    requested = post(
        app,
        f"{PERIODS}/{state['id']}/request-lock",
        world.maya,
        {"certification_comment": "September evidence acceptance complete"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    world = worlds.verified(world, clock, "marcus")
    approved = approve(app, requested.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    state = worlds.period_state(world, "AVM-US", "FY2026-P09")
    assert state["state"] == "closed"
    (lock,) = world.place.rows(
        select(period_lock)
        .where(
            period_lock.c.kind == "LOCK",
            period_lock.c.period_id == UUID(state["period"]["id"]),
        )
        .order_by(period_lock.c.created_at.desc())
        .limit(1)
    )
    assert all(gate["status"] != "WAIVED" for gate in lock["certification"])
    closed_run = runs.shown(app, world.maya, close["id"])
    assert runs.step(closed_run, "LOCK")["status"] == "SUCCEEDED"
    clock.set(lock["cutoff_known_at"] + timedelta(seconds=1))
    (preparation,) = world.place.rows(
        select(job).where(
            job.c.params["mode"].astext == "PREPARE_CLOSE",
            job.c.params["period_lock_id"].astext == str(lock["id"]),
        )
    )
    assert worlds.run_now(world, preparation["id"])["state"] == "SUCCEEDED"
    (pack,) = world.place.rows(select(evidence_pack))
    bound = evidence_sources.checked_row(pack)
    assert isinstance(bound, evidence_sources.QueuedCloseSources)
    for child in [bound.audit_verification_job_id, *[r.job_id for r in bound.supporting_reports]]:
        finished = worlds.run_now(world, child)
        assert finished["state"] == "SUCCEEDED", finished
    finished = worlds.run_now(world, pack["job_id"])
    assert finished["state"] == "SUCCEEDED", finished

    auditor = actor_with_role(app, clock, world.tenant_id, "auditor", name="hannah")
    path = f"/api/v1/evidence-packs/{pack['id']}"
    header = get(app, path, auditor)
    assert header.status_code == 200, header.text
    downloaded = get(app, f"{path}/download", auditor)
    assert downloaded.status_code == 200, downloaded.text
    digest = header.json()["manifest_sha256"]
    manifest = evidence_archive.verify(downloaded.content, expected_manifest_sha256=digest)
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert hashlib.sha256(archive.read("manifest.json")).hexdigest() == digest
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
        journals = json.loads(archive.read("journals/batch_register.json"))
        assert {run["id"] for run in journals["runs"]} == {close["journal_run_id"]}
        assert journals["batches"]
        reconciliations = json.loads(archive.read("reconciliations/index.json"))
        assert set(reconciliations["reconciliation_ids"]) == reviewed_ids
        assert reconciliations["count"] == 2
        paths = archive.namelist()
        for prefix in (
            "certification.json",
            "lock/snapshots.json",
            "journals/",
            "reconciliations/",
            "reports/contract_balance_rollforward.",
            "reports/rpo_rollforward.",
            "reports/rpo.",
            "reports/disaggregation.",
            "registers/",
            "registers/late_entries.",
            "registers/out_of_period.",
            "access/",
            "audit/chain_digest.json",
        ):
            assert any(path.startswith(prefix) for path in paths), prefix
        for target in ("manifest.json", "certification.json"):
            damaged = io.BytesIO()
            with ZipFile(damaged, "w") as changed:
                for item in archive.infolist():
                    content = archive.read(item.filename)
                    changed.writestr(
                        copy(item), content + b"!" if item.filename == target else content
                    )
            with pytest.raises(evidence_archive.InvalidArchive):
                evidence_archive.verify(damaged.getvalue(), expected_manifest_sha256=digest)
