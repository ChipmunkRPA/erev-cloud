"""MANAGED recovery provider record and mock (ruling D-95; 05 OPR-08, OPR-11, OPR-12; Codex
privilege note of 2026-09-19 "Verification still owed": offline mocks prove provider selection,
refusal of pending/failed/wrong-instance backups, destination isolation, complete manifest
requirements, mismatched generations/keys/digests, and no fallback to partial dumps or relaxed
RLS; they cannot prove Cloud SQL privilege grants, restore completeness or timings)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from erev_api.controls import recovery_managed as rm
from erev_api.controls import recovery_preflight as pf

PROJECT = "erev-prod-project"
DRILL_PROJECT = "erev-restore-test-project"
INSTANCE = "erev-prod"
CLONE = "erev-prod-restore-20260919"
BACKUP_ID = "1758300000000"
TENANT_ID = "11111111-1111-4111-8111-111111111111"


SECURITY_IDS = ["security-hmac:1", "security-hmac:3", "security-hmac:5"]


def _verification(
    result: str = "PASS",
    expected: str = "PASS",
    served: list[str] | None = None,
    required: list[str] | None = None,
    pin: str = "security-hmac:5",
) -> dict[str, Any]:
    required_ids = SECURITY_IDS if required is None else required
    served_ids = required_ids if served is None else served
    return {
        "schema": pf.DOCUMENT_SCHEMA,
        "result": result,
        "failures": [] if result == "PASS" else ["acme: audit chain FAIL at sequence 3"],
        "security_chain": {
            "last_chain_seq": 300,
            "head_key_id": "security-hmac:3",
            "current_key_id": pin,
            "required_key_ids": required_ids,
        },
        "key_versions": {
            "security_hmac": [
                {"key_id": key_id, "available": key_id in served_ids} for key_id in required_ids
            ]
        },
        "tenants": [{"tenant_id": TENANT_ID, "code": "acme", "head": {"last_chain_seq": 9294}}],
        "expected": {"result": expected, "anchors": 11},
    }


def _baseline(required: list[str] | None = None, pin: str = "security-hmac:5") -> dict[str, Any]:
    return {
        "schema": pf.DOCUMENT_SCHEMA,
        "result": "PASS",
        "security_chain": {
            "last_chain_seq": 298,
            "head_key_id": "security-hmac:3",
            "current_key_id": pin,
            "required_key_ids": SECURITY_IDS if required is None else required,
        },
    }


def _provider(**backup_overrides: Any) -> rm.MockManagedProvider:
    good = rm.ManagedBackup(
        project=PROJECT,
        instance=INSTANCE,
        kind="AUTOMATED",
        backup_id=BACKUP_ID,
        pitr_instant=None,
        operation_status="SUCCESSFUL",
        started_at="2026-09-19T02:00:00Z",
        finished_at="2026-09-19T02:04:00Z",
        database_version="POSTGRES_17",
        engine_version="0.2.0",
        schema_revision="0054",
        release_build_sha="d96c728",
    )
    backups = [replace(good, **backup_overrides)]
    restores = {
        CLONE: rm.ManagedRestore(
            project=DRILL_PROJECT,
            instance=CLONE,
            fresh_instance=True,
            operation_status="SUCCESSFUL",
            started_at="2026-09-19T12:00:00Z",
            finished_at="2026-09-19T12:09:30Z",
        )
    }
    listing = [("t/ATTACHMENT/obj", 1700000001), ("t/ATTACHMENT/obj.dek", 1700000002)]
    listings = {"pinned": listing, "restored": list(listing), "drifted": listing[:1]}
    return rm.MockManagedProvider(backups=backups, restores=restores, listings=listings)


def _record(provider: rm.MockManagedProvider | None = None, **overrides: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "provider": provider or _provider(),
        "project": PROJECT,
        "instance": INSTANCE,
        "reference": BACKUP_ID,
        "target_instance": CLONE,
        "files_bucket": "erev-files-production",
        "pinned_view": "pinned",
        "restored_view": "restored",
        "key_version_references": [
            "erev-app-kek/1",
            "erev-audit-hmac-acme/1",
            "erev-security-hmac/1",
            "erev-security-hmac/3",
            "erev-security-hmac/5",
        ],
        "key_versions_available": [
            "erev-app-kek/1",
            "erev-audit-hmac-acme/1",
            "erev-security-hmac/1",
            "erev-security-hmac/3",
            "erev-security-hmac/5",
        ],
        "digest_objects": ["acme/2026-09-19/chain_digest.json"],
        "shred_tombstones": 0,
        "verification": _verification(),
        "baseline": _baseline(),
        "measured_at": datetime(2026, 9, 19, 12, 30, tzinfo=UTC),
    }
    parameters.update(overrides)
    return rm.build_managed_record(**parameters).document()


def test_d95_complete_managed_record_is_accepted() -> None:
    document = _record()
    assert rm.validate_managed_record(document) == []
    assert document["schema"] == rm.MANAGED_RECORD_SCHEMA and document["provider"] == "MANAGED"
    assert document["backup"]["backup_id"] == BACKUP_ID and document["backup"]["project"] == PROJECT
    assert document["restore"]["fresh_instance"] is True
    assert document["restore"]["restore_duration_seconds"] == 570
    # The restore point is the backup's completion, never the record instant; the recovery age
    # counts from it.
    assert document["recovery_interval"]["restore_point"] == "2026-09-19T02:04:00Z"
    assert document["recovery_interval"]["restore_point_basis"] == "backup finished_at"
    assert document["recovery_interval"]["recovery_age_seconds"] == 10 * 3600 + 26 * 60
    assert document["tenant_inventory"] == [{"tenant_id": TENANT_ID, "code": "acme"}]
    assert document["audit_anchors"]["tenant_heads"] == {TENANT_ID: 9294}
    assert document["managed_bytes_sha256"] is None
    assert "no SHA-256 of them is recorded or invented" in document["managed_bytes_note"]
    assert len(document["verification"]["document_sha256"]) == 64  # our retained evidence bytes


def test_d95_pitr_restore_point_is_the_instant() -> None:
    provider = _provider(
        kind="PITR",
        backup_id=None,
        pitr_instant="2026-09-19T11:45:00Z",
        started_at=None,
        finished_at=None,
    )
    document = _record(provider, reference="2026-09-19T11:45:00Z")
    assert rm.validate_managed_record(document) == []
    assert document["recovery_interval"]["restore_point"] == "2026-09-19T11:45:00Z"
    assert document["recovery_interval"]["restore_point_basis"] == "pitr_instant"
    assert document["recovery_interval"]["recovery_age_seconds"] == 45 * 60


def test_d95_pending_failed_and_wrong_instance_backups_are_refused() -> None:
    pending = rm.validate_managed_record(_record(_provider(operation_status="PENDING")))
    assert any("not SUCCESSFUL: a pending or failed backup" in e for e in pending)
    failed = rm.validate_managed_record(_record(_provider(operation_status="FAILED")))
    assert any("not SUCCESSFUL" in e for e in failed)
    # The same backup id on another instance is another backup: unknown → refused.
    wrong_instance = _record(instance="erev-staging")
    errors = rm.validate_managed_record(wrong_instance)
    assert (
        "backup.operation_status is 'UNKNOWN', not SUCCESSFUL: a pending or failed backup is not "
        "a restore point" in errors
    )
    assert "backup.database_version is missing" in errors


def test_d95_destination_must_be_a_fresh_isolated_instance() -> None:
    provider = _provider()
    provider_same = rm.MockManagedProvider(
        backups=[provider.backup(PROJECT, INSTANCE, BACKUP_ID)],  # type: ignore[list-item]
        restores={
            INSTANCE: rm.ManagedRestore(
                project=PROJECT,
                instance=INSTANCE,
                fresh_instance=False,
                operation_status="SUCCESSFUL",
                started_at="2026-09-19T12:00:00Z",
                finished_at="2026-09-19T12:09:30Z",
            )
        },
        listings={"pinned": [("a", 1)], "restored": [("a", 1)]},
    )
    errors = rm.validate_managed_record(_record(provider_same, target_instance=INSTANCE))
    assert (
        "restore.fresh_instance is not true: production data is never restored in place" in errors
    )
    assert "restore.instance equals the source instance: the destination is not isolated" in errors
    assert any("restore.project equals the source project" in e for e in errors)
    unknown_target = rm.validate_managed_record(_record(target_instance="erev-nowhere"))
    assert any("restore.operation_status is 'UNKNOWN'" in e for e in unknown_target)


def test_d95_external_state_generations_keys_and_anchors_must_hold() -> None:
    drifted = rm.validate_managed_record(_record(restored_view="drifted"))
    assert drifted == [
        "external_state file generations after the restore differ from the ones pinned at "
        "backup time"
    ]
    key_lost = rm.validate_managed_record(
        _record(
            key_versions_available=[
                "erev-app-kek/1",
                "erev-security-hmac/1",
                "erev-security-hmac/3",
                "erev-security-hmac/5",
            ]
        )
    )
    assert key_lost == ["key versions referenced but not served: erev-audit-hmac-acme/1"]
    no_digests = rm.validate_managed_record(_record(digest_objects=[]))
    assert no_digests == ["external_state.digest_objects is empty: no independent audit anchors"]
    unanchored = rm.validate_managed_record(_record(verification=_verification(expected="FAIL")))
    assert unanchored == [
        "audit anchors: the backup-time expected document did not anchor (or is absent)"
    ]
    failed_verify = rm.validate_managed_record(_record(verification=_verification(result="FAIL")))
    assert "verification result is 'FAIL', not PASS" in failed_verify


def test_d95_no_bypass_partial_dump_or_invented_hash() -> None:
    relaxed = _record(
        assurances=rm.Assurances(rls_forced=False, bypass_used=True, partial_dump=True)
    )
    errors = rm.validate_managed_record(relaxed)
    assert "assurances.rls_forced is not true" in errors
    assert "assurances.bypass_used is not false" in errors
    assert "assurances.partial_dump is not false" in errors
    invented = _record()
    invented["managed_bytes_sha256"] = "0" * 64
    assert rm.validate_managed_record(invented) == [
        "managed_bytes_sha256 is set: a hash of provider-managed bytes cannot be taken"
    ]
    # A record whose restore point was replaced by the record instant is refused (R7 for MANAGED).
    shifted = _record()
    shifted["recovery_interval"]["restore_point"] = shifted["recovery_interval"]["measured_at"]
    assert rm.validate_managed_record(shifted) == [
        "recovery_interval.restore_point is not the PITR instant or the backup's finished_at"
    ]
    # An empty object is not a record.
    assert len(rm.validate_managed_record({})) >= 10


def test_p2_p6_managed_record_derives_the_security_key_set_from_the_baseline() -> None:
    # Integration control 4: rows at 1 and 3 under pin 5 ⇒ {1, 3, 5} derived from the source-bound
    # baseline and the clone's inventory; each version must be referenced, served by the provider
    # and opened by the restore verifier. A self-declared subset proves nothing.
    assert rm.validate_managed_record(_record()) == []
    document = _record()
    anchors = document["audit_anchors"]
    assert anchors["baseline_security_key_ids"] == SECURITY_IDS
    assert anchors["baseline_security_pin"] == "security-hmac:5"
    assert anchors["restored_security_key_ids"] == SECURITY_IDS
    assert anchors["security_keys_served"] == SECURITY_IDS
    # Missing historical 3: the provider did not serve it and the verifier could not open it.
    missing_3 = rm.validate_managed_record(
        _record(
            verification=_verification(served=["security-hmac:1", "security-hmac:5"]),
            key_versions_available=[
                "erev-app-kek/1",
                "erev-audit-hmac-acme/1",
                "erev-security-hmac/1",
                "erev-security-hmac/5",
            ],
        )
    )
    assert missing_3 == [
        "key versions referenced but not served: erev-security-hmac/3",
        "security HMAC key security-hmac:3 required by the baseline or the clone was not served "
        "by the provider",
        "security HMAC key security-hmac:3 required by the baseline or the clone was not opened "
        "by the restore verifier",
    ]
    # Missing current 5: the pin itself is unserved.
    missing_5 = rm.validate_managed_record(
        _record(
            verification=_verification(served=["security-hmac:1", "security-hmac:3"]),
            key_versions_available=[
                "erev-app-kek/1",
                "erev-audit-hmac-acme/1",
                "erev-security-hmac/1",
                "erev-security-hmac/3",
            ],
        )
    )
    assert missing_5 == [
        "key versions referenced but not served: erev-security-hmac/5",
        "security HMAC key security-hmac:5 required by the baseline or the clone was not served "
        "by the provider",
        "security HMAC key security-hmac:5 required by the baseline or the clone was not opened "
        "by the restore verifier",
    ]
    # A caller that omits version 3 from its reference and available lists (a self-consistent
    # subset) while the clone's verification still names {1, 3, 5} is refused, because the
    # baseline and the clone named it.
    subset = rm.validate_managed_record(
        _record(
            key_version_references=[
                "erev-app-kek/1",
                "erev-audit-hmac-acme/1",
                "erev-security-hmac/1",
                "erev-security-hmac/5",
            ],
            key_versions_available=[
                "erev-app-kek/1",
                "erev-audit-hmac-acme/1",
                "erev-security-hmac/1",
                "erev-security-hmac/5",
            ],
        )
    )
    assert subset == [
        "security HMAC key security-hmac:3 required by the baseline or the clone is not among "
        "external_state.key_version_references",
        "security HMAC key security-hmac:3 required by the baseline or the clone was not served "
        "by the provider",
    ]
    # H2: a verification document whose required set {1, 5} omits its own head 3 is inconsistent
    # evidence and never becomes a record (the constructor refuses before projection).
    with pytest.raises(rm.ManagedEvidenceError, match="head_key_id is not in required_key_ids"):
        _record(
            verification=_verification(
                required=["security-hmac:1", "security-hmac:5"],
                served=["security-hmac:1", "security-hmac:5"],
            )
        )
    # No baseline, no derivation: refused.
    assert "evidence.baseline (the retained backup-time document) is missing" in (
        rm.validate_managed_record(_record(baseline=None))
    )
    # The genuine provider denial of every version is a clear failure, not a silent pass.
    denied = rm.validate_managed_record(
        _record(
            verification=_verification(served=[]),
            key_versions_available=["erev-app-kek/1", "erev-audit-hmac-acme/1"],
        )
    )
    assert sum("was not opened by the restore verifier" in e for e in denied) == 3


def test_df43dd9_h2_inconsistent_baseline_is_refused_before_projection() -> None:
    # The complete baseline with its required set shortened to {1, 5} while head 3 / current 5
    # stay: the constructor refuses (head outside the required set), and a record whose RETAINED
    # baseline carries that inconsistency is refused by the validator as well.
    with pytest.raises(rm.ManagedEvidenceError, match="baseline document: .*head_key_id"):
        _record(baseline=_baseline(required=["security-hmac:1", "security-hmac:5"]))
    with pytest.raises(
        rm.ManagedEvidenceError, match="chain head security-hmac:3 is above the pin"
    ):
        _record(
            baseline=_baseline(
                pin="security-hmac:1", required=["security-hmac:1", "security-hmac:3"]
            )
        )
    record = _record()
    record["evidence"]["baseline"]["security_chain"]["required_key_ids"] = [
        "security-hmac:1",
        "security-hmac:5",
    ]
    errors = rm.validate_managed_record(record)
    assert any(
        "baseline document: expected document security_chain.head_key_id is not in required_key_ids"
        in e
        for e in errors
    )
    assert "audit_anchors.baseline_sha256 does not match the retained baseline" in errors


def test_df43dd9_h3_summaries_are_bound_to_the_retained_evidence() -> None:
    # From a valid {1, 3, 5} record, altering only the five summaries to omit version 3 (while the
    # retained documents and the verifier hash stay) is refused: every summary is re-derived from
    # the retained bytes.
    record = _record()
    assert rm.validate_managed_record(record) == []
    assert record["evidence"]["verification"]["security_chain"]["required_key_ids"] == SECURITY_IDS
    tampered = json.loads(json.dumps(record))
    shortened = ["security-hmac:1", "security-hmac:5"]
    tampered["audit_anchors"]["baseline_security_key_ids"] = shortened
    tampered["audit_anchors"]["restored_security_key_ids"] = shortened
    tampered["audit_anchors"]["security_keys_served"] = shortened
    tampered["external_state"]["key_version_references"] = [
        r
        for r in tampered["external_state"]["key_version_references"]
        if not r.endswith("security-hmac/3")
    ]
    tampered["external_state"]["key_versions_available"] = [
        r
        for r in tampered["external_state"]["key_versions_available"]
        if not r.endswith("security-hmac/3")
    ]
    assert tampered["verification"]["document_sha256"] == record["verification"]["document_sha256"]
    errors = rm.validate_managed_record(tampered)
    assert "audit_anchors.baseline_security_key_ids does not match the retained evidence" in errors
    assert "audit_anchors.restored_security_key_ids does not match the retained evidence" in errors
    assert "audit_anchors.security_keys_served does not match the retained evidence" in errors
    assert (
        "security HMAC key security-hmac:3 required by the baseline or the clone is not among "
        "external_state.key_version_references"
    ) in errors
    assert (
        "security HMAC key security-hmac:3 required by the baseline or the clone was not served "
        "by the provider"
    ) in errors
    # Altering the retained verification itself breaks the hash binding.
    altered = json.loads(json.dumps(record))
    altered["evidence"]["verification"]["security_chain"]["required_key_ids"] = shortened
    errors = rm.validate_managed_record(altered)
    assert "verification.document_sha256 does not match the retained verify document" in errors
    # Dropping the retained evidence is refused, not silently accepted.
    hollow = json.loads(json.dumps(record))
    del hollow["evidence"]
    errors = rm.validate_managed_record(hollow)
    assert "evidence.verification (the retained verify document) is missing" in errors
    assert "evidence.baseline (the retained backup-time document) is missing" in errors
    # The record carries the derived head relationship for both documents.
    assert record["audit_anchors"]["baseline_security_head"] == "security-hmac:3"
    assert record["audit_anchors"]["restored_security_head"] == "security-hmac:3"
    assert (
        record["audit_anchors"]["baseline_sha256"]
        == hashlib.sha256(
            json.dumps(
                record["evidence"]["baseline"], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )


def test_779847e_acceptance_is_derived_from_the_retained_verifier() -> None:
    # Codex PRODUCTION-P6-MANAGED-RESULT-BINDING-779847e: a failed retained verifier stays failed
    # whatever the editable summary says, and every projected summary must equal the retained
    # bytes (findings, tenant identities, head sequences, security head, inventory, schema).
    coherent = _record()
    assert rm.validate_managed_record(coherent) == []
    # (1) retained result FAIL; summary edited to PASS.
    failed = _record(verification=_verification(result="FAIL"))
    assert "verification result is 'FAIL', not PASS" in rm.validate_managed_record(failed)
    forged = json.loads(json.dumps(failed))
    forged["verification"]["result"] = "PASS"
    errors = rm.validate_managed_record(forged)
    assert "verification result is 'FAIL', not PASS" in errors
    assert "verification.result does not match the retained verify document" in errors
    # (2) expected-anchor FAIL; summary edited to PASS.
    unanchored = _record(verification=_verification(expected="FAIL"))
    forged = json.loads(json.dumps(unanchored))
    forged["audit_anchors"]["expected_result"] = "PASS"
    errors = rm.validate_managed_record(forged)
    assert (
        "audit anchors: the backup-time expected document did not anchor (or is absent)" in errors
    )
    assert "audit_anchors.expected_result does not match the retained verify document" in errors
    # (3) unsupported retained schema; summary edited to the supported one.
    other = _verification()
    other["schema"] = "erev-something-else/9"
    odd = _record(verification=other)
    forged = json.loads(json.dumps(odd))
    forged["verification"]["schema"] = pf.DOCUMENT_SCHEMA
    errors = rm.validate_managed_record(forged)
    assert "verification document is not an erev verify document" in errors
    assert "verification.schema does not match the retained verify document" in errors
    # (4) a different outer tenant inventory.
    forged = json.loads(json.dumps(coherent))
    forged["tenant_inventory"] = [
        {"tenant_id": "22222222-2222-4222-8222-222222222222", "code": "zeta"}
    ]
    assert (
        "tenant_inventory does not match the retained verify document"
        in rm.validate_managed_record(forged)
    )
    # (5) a tenant head sequence changed in the summary only.
    forged = json.loads(json.dumps(coherent))
    forged["audit_anchors"]["tenant_heads"][TENANT_ID] = 999
    assert (
        "audit_anchors.tenant_heads does not match the retained verify document"
        in rm.validate_managed_record(forged)
    )
    # (6) the security head changed in the summary only.
    forged = json.loads(json.dumps(coherent))
    forged["audit_anchors"]["security_head"] = 999
    assert (
        "audit_anchors.security_head does not match the retained verify document"
        in rm.validate_managed_record(forged)
    )
    # Findings cannot be emptied in the summary either.
    forged = json.loads(json.dumps(failed))
    forged["verification"]["findings"] = []
    assert (
        "verification.findings does not match the retained verify document"
        in rm.validate_managed_record(forged)
    )
    # The retained document decides: dropping it leaves nothing to judge.
    forged = json.loads(json.dumps(coherent))
    forged["evidence"]["verification"] = None
    errors = rm.validate_managed_record(forged)
    assert "verification cannot be judged: no retained verify document" in errors
