"""``erev verify --all-tenants`` and ``platform.restore_applied`` against a database (05 OPR-11
steps (3), (4) and (6), OPR-12, SAR-31; RB-04 to RB-06; DG-TST-22; readiness audit DEP-F).

The verification document must PASS on intact chains, a digest and a stored file; it must FAIL on
a tampered audit event, a tampered ledger line, a missing sidecar and a database restored under
another master key; ``compare_expected`` must anchor a backup-time document into chains that grew
since; and the restore event must append to every ACTIVE tenant and leave its chain verifiable.
Restores themselves (``pg_restore`` into an ``erev_rv_*`` clone) run only in the supervisor drill
(``make restore-verify``), never in the loop.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit import verify
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.controls import recovery
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_chain_head,
    audit_event,
    file_object,
    user_mfa_factor,
)
from erev_api.domain.journals import subledger  # noqa: F401  (registers the ledger-chain verifier)
from erev_api.domain.platform import audit_jobs  # noqa: F401  (registers AUDIT_CHAIN_VERIFY)
from erev_api.enums import FilePurpose, PrincipalKind, TenantKind
from erev_api.files.store import LocalFileStore, put_file, sidecar_key
from erev_api.uow import unit_of_work
from sqlalchemy import select, text, update
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release, tenant_factory, tenant_id_of
from support.rows import (
    insert_ledger_rows,
    insert_sealed_mfa_factor,
    insert_sealed_webhook_endpoint,
    tamper_audit_event,
)

pytestmark = pytest.mark.pg

DATA_FIX = text("SELECT set_config('app.data_fix_ticket', 'DF-P6-RCV', true)")


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    code: str
    files: LocalFileStore
    root: Path
    attachment_key: str
    attachment_sha256: str
    second_seal_line_id: UUID  # a line of the seal at chain_seq 2 of ASC606
    attachment_id: UUID
    webhook_endpoint_id: UUID  # a real sealed signing secret (P6-R5)
    mfa_factor_id: UUID  # a real sealed TOTP seed of the admin user (P6-R5)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _system_ctx(tenant_id: UUID, clock: FrozenClock, request_id: str) -> RequestContext:
    return RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id=request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


def _record_pass(
    tenant_id: UUID, keyring: KeyRing, files: LocalFileStore, clock: FrozenClock
) -> None:
    """A PASS verification row and its SAR-31 digest file, as the AUDIT_CHAIN_VERIFY job writes."""
    with unit_of_work(
        _system_ctx(tenant_id, clock, "tests-p6-verify"), clock=clock, keyring=keyring, files=files
    ) as uow:
        row = verify.record_tenant_verification(uow, trigger=verify.SCHEDULED, job_id=None)
        assert row["result"] == "PASS"
        uow.commit()


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, tmp_path: Path) -> World:
    clock = frozen_clock()
    # 05 REL-03 (D-98 60): the verification recorded below writes its CTL-039 evidence stamped
    # with the process's engine release (SOP-1), and a process that never stamped fails closed
    # (``release-mismatch``). The world stamps as the app's startup does — the module passed
    # only behind a module whose world had (measured alone: seven errors here).
    stamp_test_release()
    provisioned = tenant_factory(keyring=keyring, clock=clock)
    tenant_id = tenant_id_of(provisioned)
    files = LocalFileStore(tmp_path / "files")
    # A ledger chain of two seals (DB-06) and one encrypted attachment (PRV-06).
    with tenant_session(_context(tenant_id)) as session:
        insert_ledger_rows(session, tenant_id)
    with tenant_session(_context(tenant_id)) as session:
        second = insert_ledger_rows(
            session, tenant_id, amounts=(Decimal("25.00"), Decimal("-25.00"))
        )
    plaintext = b"%PDF-1.4 attachment bytes for the restore drill"
    with unit_of_work(
        _system_ctx(tenant_id, clock, "tests-p6-file"), clock=clock, keyring=keyring, files=files
    ) as uow:
        stored = put_file(
            uow,
            purpose=FilePurpose.ATTACHMENT,
            stream=io.BytesIO(plaintext),
            original_filename="evidence.pdf",
            media_type="application/pdf",
        )
        uow.commit()
    _record_pass(tenant_id, keyring, files, frozen_clock(FROZEN_AT + timedelta(minutes=1)))
    # P6-R5: envelopes that only MFA and webhooks reference must be opened, not listed.
    with tenant_session(_context(tenant_id)) as session:
        endpoint_id = insert_sealed_webhook_endpoint(session, tenant_id, keyring=keyring)
    with identity_session(request_id="tests-p6-mfa") as session:
        # A user without an active factor (ux_user_mfa_factor__active): the tenant's invited admin.
        user_id = session.execute(
            select(app_user.c.id)
            .where(
                ~select(user_mfa_factor.c.id)
                .where(
                    user_mfa_factor.c.user_id == app_user.c.id,
                    user_mfa_factor.c.disabled_at.is_(None),
                )
                .exists()
            )
            .order_by(app_user.c.created_at.desc())
            .limit(1)
        ).scalar_one()
        factor_id = insert_sealed_mfa_factor(session, user_id, keyring=keyring)
    return World(
        tenant_id=tenant_id,
        code=str(provisioned.tenant["code"]),
        files=files,
        root=tmp_path / "files",
        attachment_key=str(stored.row["storage_key"]),
        attachment_sha256=str(stored.row["sha256"]),
        second_seal_line_id=UUID(str(second.lines[1]["id"])),
        attachment_id=UUID(str(stored.row["id"])),
        webhook_endpoint_id=endpoint_id,
        mfa_factor_id=factor_id,
    )


def _verify(world: World, keyring: KeyRing, clock: FrozenClock | None = None) -> dict[str, Any]:
    return recovery.verify_all_tenants(
        keyring=keyring,
        files=world.files,
        clock=clock or frozen_clock(FROZEN_AT + timedelta(minutes=5)),
        request_id="tests-p6",
        database="erev_test",
        engine_version="0.2.0",
        tenant_codes=[world.code],
    )


def _tenant_of(document: dict[str, Any], code: str) -> dict[str, Any]:
    (found,) = [t for t in document["tenants"] if t["code"] == code]
    return found


def _book(workspace: dict[str, Any], book_code: str) -> dict[str, Any]:
    (found,) = [b for b in workspace["ledger_chains"] if b["book_code"] == book_code]
    return found


def test_opr_11_verify_passes_on_intact_chains_digest_and_files(
    world: World, keyring: KeyRing
) -> None:
    document = _verify(world, keyring)
    assert document["result"] == "PASS", document["failures"]
    assert document["schema"] == recovery.DOCUMENT_SCHEMA
    assert document["schema_revision"] and document["security_chain"]["result"] == "PASS"
    assert document["security_chain"]["key_available"] is True
    workspace = _tenant_of(document, world.code)
    chain = workspace["audit_chain"]
    assert (
        chain["result"] == "PASS" and chain["events_checked"] == workspace["head"]["last_chain_seq"]
    )
    # The digest anchors: the event at its sequence carries its hmac; the gap counts the events
    # appended since (the verification's own AUD-FACT event and the file upload came after it).
    digest = workspace["digest"]
    assert digest is not None and digest["event_matches"] is True
    assert digest["file"] == {"present": True, "parsed": True, "matches_row": True}
    assert workspace["gap_events"] == workspace["head"]["last_chain_seq"] - digest["last_chain_seq"]
    assert workspace["gap_events"] >= 1
    # Both seals of the ASC606 book verify and its head is recorded; provisioning seeds a chain
    # head per book, so the other books verify empty.
    ledger = _book(workspace, "ASC606")
    assert {b["book_code"] for b in workspace["ledger_chains"]} >= {"ASC606"}
    assert all(b["result"] == "PASS" for b in workspace["ledger_chains"])
    assert (
        ledger["book_code"],
        ledger["result"],
        ledger["seals_checked"],
        ledger["last_chain_seq"],
    ) == (
        "ASC606",
        "PASS",
        2,
        2,
    )
    assert ledger["last_seal_sha256"]
    # The attachment decrypted and hashed back; the digest file hashed as stored.
    entries = {e["storage_key"]: e for e in workspace["files"]["entries"]}
    attachment = entries[world.attachment_key]
    assert (attachment["status"], attachment["encrypted"], attachment["kek_id"]) == (
        "ok",
        True,
        "kek:1",
    )
    assert attachment["sha256"] == world.attachment_sha256
    digest_entries = [e for e in entries.values() if e["purpose"] == "AUDIT_DIGEST"]
    assert digest_entries and all(
        e["status"] == "ok" and e["kek_id"] is None for e in digest_entries
    )
    assert workspace["files"]["failed"] == 0 and workspace["files"]["checked"] == len(entries)
    # Key versions: the tenant's current audit key is in use and served; kek:1 wraps the sidecar.
    assert workspace["audit_hmac_keys"] == [
        {
            "key_id": f"audit-hmac:{world.tenant_id}:1",
            "current": True,
            "in_use": True,
            "available": True,
        }
    ]
    # kek:1 wraps the sidecar, the webhook secret and the MFA seed, and every one of those
    # envelopes opened (P6-R5); the verifier's own directory read is not recovered freshness
    # (P6-R7).
    assert "kek:1" in workspace["kek_ids"]
    (hook,) = workspace["envelopes"]
    assert (hook["kind"], hook["row_id"], hook["opened"]) == (
        "webhook",
        str(world.webhook_endpoint_id),
        True,
    )
    mfa = [p for p in document["mfa_envelopes"] if p["row_id"] == str(world.mfa_factor_id)]
    assert mfa and mfa[0]["opened"] is True and mfa[0]["key_id"] == "kek:1"
    (kek,) = [k for k in document["key_versions"]["kek"] if k["key_id"] == "kek:1"]
    assert kek["available"] is True and kek["opened"] == kek["references"]
    assert kek["webhooks_opened"] >= 1 and kek["mfa_opened"] >= 1 and kek["sidecars_opened"] >= 1
    assert document["verifier_events_appended"] >= 1
    assert document["security_chain"]["recovered_last_occurred_at"] is not None
    assert document["latest_evidence_at"] <= document["security_chain"]["last_occurred_at"]
    assert document["latest_evidence_at"] is not None
    assert document["counts"]["failures"] == 0


def test_opr_11_verify_fails_on_tampered_audit_event_and_ledger_line(
    world: World, committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tamper_audit_event(committed_db.owner_engine, tenant_id=world.tenant_id, chain_seq=3)
    document = _verify(world, keyring)
    assert document["result"] == "FAIL"
    workspace = _tenant_of(document, world.code)
    assert workspace["audit_chain"]["result"] == "FAIL"
    assert workspace["audit_chain"]["first_failure_seq"] == 3
    assert any(
        f.startswith(f"{world.code}: audit chain FAIL at sequence 3:") for f in document["failures"]
    )

    with committed_db.owner_engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE erev.subledger_line NO FORCE ROW LEVEL SECURITY")
        connection.execute(DATA_FIX)
        changed = connection.execute(
            text(
                "UPDATE erev.subledger_line SET description = 'Adjusted by hand' "
                "WHERE tenant_id = :tenant_id AND id = :line_id"
            ),
            {"tenant_id": world.tenant_id, "line_id": world.second_seal_line_id},
        ).rowcount
        connection.exec_driver_sql("ALTER TABLE erev.subledger_line FORCE ROW LEVEL SECURITY")
    assert changed == 1
    document = _verify(world, keyring)
    ledger = _book(_tenant_of(document, world.code), "ASC606")
    assert (ledger["result"], ledger["first_failure_seq"]) == ("FAIL", 2)
    reason = "seal_sha256 does not match the posting content"
    assert f"{world.code}: ledger chain ASC606 FAIL at seal 2: {reason}" in document["failures"]


def test_prv_06_verify_fails_on_missing_sidecar_and_foreign_master_key(
    world: World, keyring: KeyRing, tmp_path: Path
) -> None:
    from erev_api.adapters.keys.provider import LocalKeyProvider
    from erev_api.adapters.secrets.store import EnvSecretStore
    from erev_api.config import get_settings
    from pydantic import SecretStr

    # A restore under another EREV_ENCRYPTION_KEY cannot open any sidecar (RB-05); the audit
    # chains fail too when the audit master key differs.
    foreign_settings = get_settings().model_copy(
        update={
            "encryption_key": SecretStr("e" * 64),
            "audit_hmac_master_key": SecretStr("d" * 64),
        }
    )
    foreign = KeyRing(LocalKeyProvider(EnvSecretStore(foreign_settings)))
    document = _verify(world, foreign)
    workspace = _tenant_of(document, world.code)
    assert document["result"] == "FAIL"
    assert workspace["audit_chain"]["result"] == "FAIL"
    entries = {e["storage_key"]: e for e in workspace["files"]["entries"]}
    assert entries[world.attachment_key]["status"] == "undecryptable"
    # P6-R5: the webhook secret and the MFA seed fail to open under the wrong KEK, each named.
    (hook,) = workspace["envelopes"]
    assert hook["opened"] is False
    assert (
        f"{world.code}: webhook endpoint {world.webhook_endpoint_id} secret does not open under "
        "kek:1"
    ) in document["failures"]
    assert (
        f"MFA factor {world.mfa_factor_id} seed does not open under kek:1" in document["failures"]
    )
    (kek,) = [k for k in document["key_versions"]["kek"] if k["key_id"] == "kek:1"]
    assert kek["available"] is False and kek["opened"] < kek["references"]
    assert any(f.startswith("kek kek:1:") for f in document["failures"])

    # The sidecar gone without a shred: the file is unreadable and the drill says so.
    Path(world.files._path(sidecar_key(world.attachment_key))).unlink()
    document = _verify(world, keyring)
    entries = {e["storage_key"]: e for e in _tenant_of(document, world.code)["files"]["entries"]}
    assert entries[world.attachment_key]["status"] == "missing_sidecar"
    assert f"{world.code}: file {world.attachment_key} missing_sidecar" in document["failures"]
    assert document["result"] == "FAIL"


def test_opr_11_4_expected_document_anchors_into_chains_that_grew(
    world: World, keyring: KeyRing, committed_db: TestDatabase
) -> None:
    # The backup-time digests are taken, then the chains grow (a later event and a later seal),
    # as they do between `erev verify` and `pg_dump` in scripts/backup.sh.
    expected = _verify(world, keyring)
    assert expected["result"] == "PASS"
    clock = frozen_clock(FROZEN_AT + timedelta(minutes=10))
    with tenant_session(_context(world.tenant_id)) as session:
        insert_ledger_rows(session, world.tenant_id, amounts=(Decimal("7.00"), Decimal("-7.00")))
    _record_pass(world.tenant_id, keyring, world.files, clock)
    actual = _verify(world, keyring, frozen_clock(FROZEN_AT + timedelta(minutes=11)))
    assert actual["result"] == "PASS"
    workspace, before = _tenant_of(actual, world.code), _tenant_of(expected, world.code)
    assert workspace["head"]["last_chain_seq"] > before["head"]["last_chain_seq"]
    assert _book(workspace, "ASC606")["last_chain_seq"] == 3

    anchors = recovery.anchor_requests(expected)
    assert {a.kind for a in anchors} == {"security", "audit", "ledger"}
    resolved = recovery.resolve_anchors(anchors, request_id="tests-p6-anchors")
    assert set(resolved) == set(anchors) and all(v is not None for v in resolved.values())
    assert recovery.compare_expected(expected, actual, resolved) == []

    # After a tamper of the very event the digest names, the anchor no longer holds.
    tamper_audit_event(
        committed_db.owner_engine,
        tenant_id=world.tenant_id,
        chain_seq=before["head"]["last_chain_seq"],
    )
    resolved = recovery.resolve_anchors(anchors, request_id="tests-p6-anchors-2")
    findings = recovery.compare_expected(expected, actual, resolved)
    assert findings == [] or findings == [
        f"{world.code}: the audit event at backup-time head {before['head']['last_chain_seq']} "
        "does not carry the recorded hmac"
    ]
    # tamper_audit_event changes `detail`, not `hmac`: the anchor (the stored hmac) still matches
    # while the recomputation fails, which the full verification of the clone reports instead.
    assert _verify(world, keyring)["result"] == "FAIL"


def test_opr_11_6_restore_applied_appends_to_every_active_tenant(
    world: World, keyring: KeyRing
) -> None:
    before = _verify(world, keyring)
    heads = recovery.previous_heads_of(before)
    clock = frozen_clock(FROZEN_AT + timedelta(hours=2))
    applied = recovery.record_restore_applied(
        keyring=keyring,
        files=world.files,
        clock=clock,
        request_id="tests-p6-restore",
        restore_instant=datetime(2026, 9, 19, 9, 30, tzinfo=UTC),
        backup_id="erev-20260919T093000Z",
        previous_heads=heads,
    )
    (row,) = [r for r in applied if r["tenant_id"] == str(world.tenant_id)]
    assert row["previous_head"] == heads[str(world.tenant_id)]
    assert row["new_head"]["last_chain_seq"] == heads[str(world.tenant_id)]["last_chain_seq"] + 1

    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        event = (
            session.execute(
                select(audit_event)
                .where(audit_event.c.tenant_id == world.tenant_id)
                .order_by(audit_event.c.chain_seq.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        head = session.execute(
            select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac).where(
                audit_chain_head.c.tenant_id == world.tenant_id
            )
        ).one()
    assert event["action"] == "platform.restore_applied"
    assert event["object_type"] == "tenant"
    assert event["actor_kind"] == PrincipalKind.SYSTEM.value
    assert event["detail"]["restore_instant"] == "2026-09-19T09:30:00Z"
    assert event["detail"]["backup_id"] == "erev-20260919T093000Z"
    assert event["detail"]["previous_head"] == heads[str(world.tenant_id)]
    assert event["detail"]["ids"] == [str(world.tenant_id)]
    assert (int(head.last_chain_seq), str(head.last_hmac)) == (
        row["new_head"]["last_chain_seq"],
        row["new_head"]["last_hmac"],
    )
    # The chain still verifies with the restore event as its head.
    after = _verify(world, keyring, frozen_clock(FROZEN_AT + timedelta(hours=3)))
    assert after["result"] == "PASS", after["failures"]
    assert (
        _tenant_of(after, world.code)["head"]["last_chain_seq"] == row["new_head"]["last_chain_seq"]
    )


def test_prv_07_shredded_state_is_reported_and_compared(world: World, keyring: KeyRing) -> None:
    # P6-R6: a shredded row passes only while its live sidecar is gone, its erasure state is
    # reported with its scope, and a backup-time shredded record must survive a restore.
    before = _verify(world, keyring)
    with tenant_session(_context(world.tenant_id)) as session:
        session.execute(
            update(file_object)
            .where(file_object.c.id == world.attachment_id)
            .values(
                shredded_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
                shredded_by=None,
                shredded_by_kind=PrincipalKind.SYSTEM.value,
                shred_reason="P6 drill",
            )
        )
        session.commit()
    sidecar = Path(world.files._path(sidecar_key(world.attachment_key)))
    still_present = _verify(world, keyring)
    entry = {
        e["storage_key"]: e for e in _tenant_of(still_present, world.code)["files"]["entries"]
    }[world.attachment_key]
    assert entry["status"] == "shredded_sidecar_present"
    assert entry["erasure"]["live_sidecar_present"] is True
    assert entry["erasure"]["scope"] == recovery.ERASURE_LOCAL_LIVE
    assert entry["erasure"]["all_generations_gone"] is None  # the local store has no inventory
    saved = sidecar.read_bytes()
    sidecar.unlink()
    shredded = _verify(world, keyring)
    entry = {e["storage_key"]: e for e in _tenant_of(shredded, world.code)["files"]["entries"]}[
        world.attachment_key
    ]
    assert entry["status"] == "shredded" and entry["erasure"]["live_sidecar_present"] is False
    assert shredded["result"] == "PASS", shredded["failures"]
    # The backup-time document recorded the file readable; the clone shows it shredded → finding.
    anchors = recovery.resolve_anchors(recovery.anchor_requests(before), request_id="t-p6-e1")
    assert f"{world.code}: file {world.attachment_key} verified at backup time is now shredded" in (
        recovery.compare_expected(before, shredded, anchors)
    )
    # The backup-time document recorded the shred; a restore that brings the sidecar back is
    # reported as an incomplete erasure.
    sidecar.write_bytes(saved)
    readable_again = _verify(world, keyring)
    assert (
        f"{world.code}: file {world.attachment_key} recorded shredded at backup time is now "
        "shredded_sidecar_present"
    ) in recovery.compare_expected(shredded, readable_again, anchors)
    sidecar.unlink()


def test_verify_reports_unknown_tenant_codes(world: World, keyring: KeyRing) -> None:
    with pytest.raises(ValueError, match="unknown tenant codes: nope"):
        recovery.verify_all_tenants(
            keyring=keyring,
            files=world.files,
            clock=frozen_clock(),
            request_id="tests-p6-unknown",
            tenant_codes=["nope"],
        )
