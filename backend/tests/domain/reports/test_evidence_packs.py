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
from zipfile import ZipFile

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.domain.platform import audit_jobs  # noqa: F401 - register the actual audit worker
from erev_api.domain.reports import (
    evidence,  # noqa: F401 - register the actual pack worker
    evidence_archive,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from support.close_world import actor_with_role
from support.db import TestDatabase
from support.evidence_packs import retained_close_pack
from support.reference import get


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
    retained = retained_close_pack(app, keyring, clock, files, monkeypatch)
    world, pack = retained.world, retained.pack
    auditor = actor_with_role(app, clock, world.tenant_id, "auditor", name="hannah")
    path = f"/api/v1/evidence-packs/{pack['id']}"
    header = get(app, path, auditor)
    assert header.status_code == 200, header.text
    downloaded = get(app, f"{path}/download", auditor)
    assert downloaded.status_code == 200, downloaded.text
    # Catalogue output uses the same retained pack under current source authorization.
    from erev_api.domain.reports import evidence_catalogue, evidence_commands, evidence_sources
    from erev_api.problems import Problem

    principal = replace(
        world.place.principal,
        permissions=evidence_commands.PERMISSIONS,
        permission_scopes={permission: "*" for permission in evidence_commands.PERMISSIONS},
    )
    with world.place.uow(principal) as uow:
        source = evidence_sources.load_close(uow, pack["id"])
        bound = evidence_catalogue.bind(
            uow,
            pack["id"],
            request=source.request,
            entity_ids=(source.entity_id,),
            known_at=source.cutoff_known_at,
            output_format="ZIP",
        )
        output = evidence_catalogue.read(uow, bound)
        assert output.content == downloaded.content
        changed = bound.model_copy(update={"source_binding_sha256": "f" * 64})
        with pytest.raises(Problem):
            evidence_catalogue.read(uow, changed)
        uow.commit()
    denied = replace(principal, permissions=principal.permissions - {"evidence.export"})
    with world.place.uow(denied) as uow, pytest.raises(Problem) as refusal:
        evidence_catalogue.read(uow, bound)
    assert refusal.value.status == 403
    digest = header.json()["manifest_sha256"]
    manifest = evidence_archive.verify(downloaded.content, expected_manifest_sha256=digest)
    with ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert hashlib.sha256(archive.read("manifest.json")).hexdigest() == digest
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
        journals = json.loads(archive.read("journals/batch_register.json"))
        assert {run["id"] for run in journals["runs"]} == {retained.journal_run_id}
        assert journals["batches"]
        reconciliations = json.loads(archive.read("reconciliations/index.json"))
        assert set(reconciliations["reconciliation_ids"]) == retained.reviewed_ids
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
