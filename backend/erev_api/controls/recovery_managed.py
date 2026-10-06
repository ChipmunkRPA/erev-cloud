"""MANAGED recovery provider KRN-RCV (ruling D-95; 05 OPR-08, OPR-11, OPR-12, OPR-16; runbook RB-04,
RB-06; Codex privilege note of 2026-09-19).

Hosted production recovers through Cloud SQL's automated backups and point-in-time recovery, which
are control-plane operations authorised by IAM rather than a customer ``pg_dump`` identity. A
managed backup is therefore evidenced by a **record**, not by a dump the application can hash: the
record binds the backup (project, source instance, backup id or PITR instant, operation status,
start and end, engine, schema and release identity) to the restore (a fresh isolated instance,
its operation status and times), to the external state the database does not contain (file object
generations, key-version references, digest objects) and to the verifier's document on the clone
(tenant inventory, audit, security and ledger anchors, result). ``validate_managed_record`` is the
acceptance contract; ``build_managed_record`` assembles one from the parts a drill collects.
``MockManagedProvider`` stands in for Cloud SQL in tests: it answers backup runs and restores from
fixtures, so the refusals (pending or failed backup, wrong instance, non-isolated destination,
missing bindings, drifted generations or keys, invented database hashes, any bypass or partial
dump) are proven offline. Nothing here calls a cloud API; live provider behaviour, all-tenant
restore completeness and recovery timings are established only by an authorised disposable Cloud
SQL drill (Codex note, "Verification still owed").
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from erev_api.controls import recovery_preflight as pf
from erev_api.controls.recovery_preflight import DOCUMENT_SCHEMA, MANAGED, _parse_instant

MANAGED_RECORD_SCHEMA: Final = "erev-managed-restore-record/1"
SUCCESSFUL: Final = "SUCCESSFUL"
BACKUP_KINDS: Final = ("AUTOMATED", "ON_DEMAND", "PITR")
# Cloud SQL BackupRun statuses that mean the bytes exist and are complete.
COMPLETE_STATUSES: Final = frozenset({SUCCESSFUL})
_RESOURCE: Final = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
MANAGED_BYTES_NOTE: Final = (
    "provider-managed database bytes are not accessible to the application; no SHA-256 of them "
    "is recorded or invented (D-95); the record hashes the retained evidence bytes only"
)


@dataclass(frozen=True, slots=True)
class ManagedBackup:
    """One Cloud SQL backup run or PITR instant, bound to its project and source instance (a
    backup id is unique only within an instance)."""

    project: str
    instance: str
    kind: str  # AUTOMATED, ON_DEMAND or PITR
    backup_id: str | None  # null for PITR
    pitr_instant: str | None  # RFC 3339; null for a backup run
    operation_status: str
    started_at: str | None
    finished_at: str | None
    database_version: str  # e.g. POSTGRES_17
    engine_version: str
    schema_revision: str
    release_build_sha: str

    def restore_point(self) -> str | None:
        """The PITR instant, else the backup's end (the snapshot is complete then); never a
        manifest or record instant."""
        return self.pitr_instant if self.kind == "PITR" else self.finished_at


@dataclass(frozen=True, slots=True)
class ManagedRestore:
    """The restore into a fresh isolated instance of the restore-test project."""

    project: str
    instance: str
    fresh_instance: bool
    operation_status: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class ExternalState:
    """What the database does not hold and a database restore does not prove (D-95): the file
    object generations pinned at backup time and observed after the restore, the key versions
    referenced, and the digest objects of the write-once bucket."""

    files_bucket: str
    pinned_generations_sha256: str  # SHA-256 of the sorted generation listing pinned at backup
    restored_generations_sha256: str  # the same listing observed against the restored view
    key_version_references: Sequence[str]  # KMS / Secret Manager version names the data needs
    key_versions_available: Sequence[str]  # the ones the provider served during verification
    digest_objects: Sequence[str]  # bucket objects of the SAR-31 digests used as anchors
    shred_tombstones: int  # tombstones/erasure records carried by the restored view


@dataclass(frozen=True, slots=True)
class Assurances:
    """Fail-closed statements the drill asserts; any relaxation is a refusal."""

    rls_forced: bool = True
    bypass_used: bool = False
    partial_dump: bool = False
    policies_relaxed: bool = False
    impersonation_used: bool = False


class ManagedEvidenceError(ValueError):
    """The baseline or the clone's verification document is not consistent evidence (review
    df43dd9 H2): the record is not built from it."""


def security_evidence_errors(document: Mapping[str, Any], *, label: str) -> list[str]:
    """Why a verify document's security-key evidence is not consistent: the inventory grammar, the
    head and the pin as members of the required set, and the head not above the pin (the
    relationships the native drill checks through ``validate_expected_document``)."""
    security = document.get("security_chain") if isinstance(document, Mapping) else None
    if not isinstance(security, Mapping):
        return [f"{label} has no security_chain"]
    errors = [f"{label}: {e}" for e in pf.security_inventory_errors(security)]
    if errors:
        return errors
    head = pf.security_key_version(security["head_key_id"])
    pin = pf.security_key_version(security["current_key_id"])
    if head > pin:
        errors.append(
            f"{label}: the chain head {security['head_key_id']} is above the pin "
            f"{security['current_key_id']}"
        )
    # Whether every required id was SERVED is a drill outcome (a genuine provider denial), judged
    # by the validator from the retained evidence, never a reason to refuse building the record.
    return errors


def _canonical(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _security_summary(document: Mapping[str, Any]) -> dict[str, Any]:
    """The five security-key summaries of a verify document, derived from its bytes (H3)."""
    security = document.get("security_chain") or {}
    return {
        "key_ids": sorted(
            (str(k) for k in security.get("required_key_ids") or []), key=_version_or_zero
        ),
        "pin": security.get("current_key_id"),
        "head": security.get("head_key_id"),
        "served": sorted(
            str(k.get("key_id"))
            for k in (document.get("key_versions") or {}).get("security_hmac") or []
            if isinstance(k, Mapping) and k.get("available") is True
        ),
    }


def verifier_projection(verification: Mapping[str, Any]) -> dict[str, Any]:
    """Everything the record presents as evidence about the clone, derived from the verifier
    document's bytes: result, schema, findings, expected-anchor result, tenant inventory, tenant
    head sequences and the security head. The constructor projects with it and the validator
    re-derives with it from the retained document (review 779847e: a projected summary is never
    trusted on its own)."""
    tenants = verification.get("tenants") or []
    return {
        "result": verification.get("result"),
        "schema": verification.get("schema"),
        "findings": [str(f) for f in verification.get("failures") or []],
        "expected_result": (verification.get("expected") or {}).get("result"),
        "tenant_inventory": [
            {"tenant_id": t.get("tenant_id"), "code": t.get("code")}
            for t in tenants
            if isinstance(t, Mapping)
        ],
        "tenant_heads": {
            str(t.get("tenant_id")): (t.get("head") or {}).get("last_chain_seq")
            for t in tenants
            if isinstance(t, Mapping)
        },
        "security_head": (verification.get("security_chain") or {}).get("last_chain_seq"),
    }


@dataclass(frozen=True, slots=True)
class ManagedRestoreRecord:
    """The OPR-12 restore-test record of a MANAGED drill (D-95 adjustment 3). The record retains
    the full backup-time baseline and the clone's verification document (``evidence``), hashed;
    every security-key summary is derived from those bytes and revalidated against them by
    ``validate_managed_record`` (review df43dd9 H3)."""

    backup: ManagedBackup
    restore: ManagedRestore
    external: ExternalState
    verification: Mapping[str, Any]  # the erev verify document produced on the clone
    measured_at: str
    assurances: Assurances = field(default_factory=Assurances)
    managed_bytes_sha256: str | None = None  # must stay None
    baseline: Mapping[str, Any] | None = None  # the backup-time erev verify document (source-bound)

    def __post_init__(self) -> None:
        # H2: the head/pin/required relationships are validated BEFORE projection; an inconsistent
        # baseline or verification document never becomes a record.
        errors = security_evidence_errors(self.verification, label="verification document")
        if self.baseline is not None:
            errors += security_evidence_errors(self.baseline, label="baseline document")
        if errors:
            raise ManagedEvidenceError("; ".join(errors))

    def document(self) -> dict[str, Any]:
        verification_bytes = _canonical(self.verification)
        baseline_bytes = None if self.baseline is None else _canonical(self.baseline)
        projection = verifier_projection(self.verification)
        restore_point = self.backup.restore_point()
        measured = _parse_instant(self.measured_at)
        point = _parse_instant(restore_point)
        age = None if measured is None or point is None else int((measured - point).total_seconds())
        restore_seconds = _seconds(self.restore.started_at, self.restore.finished_at)
        return {
            "schema": MANAGED_RECORD_SCHEMA,
            "provider": MANAGED,
            "backup": {
                "project": self.backup.project,
                "instance": self.backup.instance,
                "kind": self.backup.kind,
                "backup_id": self.backup.backup_id,
                "pitr_instant": self.backup.pitr_instant,
                "operation_status": self.backup.operation_status,
                "started_at": self.backup.started_at,
                "finished_at": self.backup.finished_at,
                "database_version": self.backup.database_version,
                "engine_version": self.backup.engine_version,
                "schema_revision": self.backup.schema_revision,
                "release_build_sha": self.backup.release_build_sha,
            },
            "restore": {
                "project": self.restore.project,
                "instance": self.restore.instance,
                "fresh_instance": self.restore.fresh_instance,
                "operation_status": self.restore.operation_status,
                "started_at": self.restore.started_at,
                "finished_at": self.restore.finished_at,
                "restore_duration_seconds": restore_seconds,
            },
            "recovery_interval": {
                "restore_point": restore_point,
                "restore_point_basis": "pitr_instant"
                if self.backup.kind == "PITR"
                else "backup finished_at",
                "measured_at": self.measured_at,
                "recovery_age_seconds": age,
            },
            "external_state": {
                "files_bucket": self.external.files_bucket,
                "pinned_generations_sha256": self.external.pinned_generations_sha256,
                "restored_generations_sha256": self.external.restored_generations_sha256,
                "key_version_references": sorted(self.external.key_version_references),
                "key_versions_available": sorted(self.external.key_versions_available),
                "digest_objects": sorted(self.external.digest_objects),
                "shred_tombstones": self.external.shred_tombstones,
            },
            "tenant_inventory": projection["tenant_inventory"],
            "audit_anchors": {
                "security_head": projection["security_head"],
                # P2/P6 integration: the global security-key set the source-bound baseline named
                # and the pin it was taken under, next to what the verifier saw on the clone; all
                # derived from the retained evidence bytes below (H3).
                "baseline_security_key_ids": (
                    [] if self.baseline is None else _security_summary(self.baseline)["key_ids"]
                ),
                "baseline_security_pin": (
                    None if self.baseline is None else _security_summary(self.baseline)["pin"]
                ),
                "baseline_security_head": (
                    None if self.baseline is None else _security_summary(self.baseline)["head"]
                ),
                "baseline_sha256": (
                    None if baseline_bytes is None else hashlib.sha256(baseline_bytes).hexdigest()
                ),
                "restored_security_key_ids": _security_summary(self.verification)["key_ids"],
                "restored_security_pin": _security_summary(self.verification)["pin"],
                "restored_security_head": _security_summary(self.verification)["head"],
                "security_keys_served": _security_summary(self.verification)["served"],
                "tenant_heads": projection["tenant_heads"],
                "expected_result": projection["expected_result"],
            },
            "verification": {
                "result": projection["result"],
                "findings": projection["findings"],
                "document_sha256": hashlib.sha256(verification_bytes).hexdigest(),
                "schema": projection["schema"],
            },
            "evidence": {
                # The full documents the summaries are derived from; the validator recomputes the
                # hashes and the summaries from these bytes (H3). Key ids only, never material.
                "baseline": None if self.baseline is None else dict(self.baseline),
                "verification": dict(self.verification),
            },
            "assurances": {
                "rls_forced": self.assurances.rls_forced,
                "bypass_used": self.assurances.bypass_used,
                "partial_dump": self.assurances.partial_dump,
                "policies_relaxed": self.assurances.policies_relaxed,
                "impersonation_used": self.assurances.impersonation_used,
            },
            "managed_bytes_sha256": self.managed_bytes_sha256,
            "managed_bytes_note": MANAGED_BYTES_NOTE,
        }


def _version_or_zero(key_id: Any) -> int:
    try:
        return pf.security_key_version(key_id)
    except pf.PreflightError:
        return 0


def _names_security_version(name: Any, version: int) -> bool:
    """Whether a provider version name (``…security-hmac…/<n>`` or ``…/versions/<n>``) names the
    numbered security HMAC version."""
    text = str(name or "")
    if "security-hmac" not in text:
        return False
    tail = text.rsplit("/", 1)[-1]
    return tail.isdigit() and int(tail) == version


def _seconds(start: str | None, end: str | None) -> int | None:
    first, last = _parse_instant(start), _parse_instant(end)
    if first is None or last is None:
        return None
    return int((last - first).total_seconds())


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _section(document: Mapping[str, Any], name: str) -> dict[str, Any]:
    """The named object of ``document`` as a dict, or an empty dict when absent or not an object."""
    value = document.get(name)
    return dict(value) if isinstance(value, Mapping) else {}


def validate_managed_record(document: Mapping[str, Any]) -> list[str]:
    """Every reason a managed restore-test record is not acceptable evidence (D-95 adjustment 3;
    Codex acceptance cases). An empty list is acceptance."""
    errors: list[str] = []
    if document.get("schema") != MANAGED_RECORD_SCHEMA:
        errors.append(f"record schema is not {MANAGED_RECORD_SCHEMA}")
    if document.get("provider") != MANAGED:
        errors.append("record provider is not MANAGED")
    backup = _section(document, "backup")
    restore = _section(document, "restore")
    external = _section(document, "external_state")
    verification = _section(document, "verification")
    anchors = _section(document, "audit_anchors")
    assurances = _section(document, "assurances")
    interval = _section(document, "recovery_interval")
    # Backup binding: a backup id means nothing without its project and instance.
    for name in ("project", "instance", "database_version", "engine_version", "schema_revision"):
        if _missing(backup.get(name)):
            errors.append(f"backup.{name} is missing")
    if _missing(backup.get("release_build_sha")):
        errors.append("backup.release_build_sha is missing")
    kind = backup.get("kind")
    if kind not in BACKUP_KINDS:
        errors.append("backup.kind is not AUTOMATED, ON_DEMAND or PITR")
    elif kind == "PITR":
        if _parse_instant(backup.get("pitr_instant")) is None:
            errors.append("backup.pitr_instant is missing for a PITR restore")
    elif _missing(backup.get("backup_id")):
        errors.append("backup.backup_id is missing")
    if backup.get("operation_status") not in COMPLETE_STATUSES:
        errors.append(
            f"backup.operation_status is {backup.get('operation_status')!r}, not SUCCESSFUL: a "
            "pending or failed backup is not a restore point"
        )
    if kind != "PITR" and (
        _parse_instant(backup.get("started_at")) is None
        or _parse_instant(backup.get("finished_at")) is None
    ):
        errors.append("backup.started_at and finished_at are missing")
    # Restore: a fresh isolated instance, completed.
    for name in ("project", "instance"):
        if _missing(restore.get(name)):
            errors.append(f"restore.{name} is missing")
    if restore.get("fresh_instance") is not True:
        errors.append(
            "restore.fresh_instance is not true: production data is never restored in place"
        )
    if restore.get("instance") and restore.get("instance") == backup.get("instance"):
        errors.append(
            "restore.instance equals the source instance: the destination is not isolated"
        )
    if restore.get("project") and restore.get("project") == backup.get("project"):
        errors.append(
            "restore.project equals the source project: the restore test runs in a separate "
            "project (OPR-12)"
        )
    if restore.get("operation_status") not in COMPLETE_STATUSES:
        errors.append(
            f"restore.operation_status is {restore.get('operation_status')!r}, not SUCCESSFUL"
        )
    if (
        _parse_instant(restore.get("started_at")) is None
        or _parse_instant(restore.get("finished_at")) is None
    ):
        errors.append("restore.started_at and finished_at are missing")
    # Recovery interval: the restore point is the PITR instant or the backup's end, never a record
    # or manifest instant.
    expected_point = backup.get("pitr_instant") if kind == "PITR" else backup.get("finished_at")
    if _parse_instant(interval.get("restore_point")) is None:
        errors.append("recovery_interval.restore_point is missing")
    elif interval.get("restore_point") != expected_point:
        errors.append(
            "recovery_interval.restore_point is not the PITR instant or the backup's finished_at"
        )
    age = interval.get("recovery_age_seconds")
    if not isinstance(age, int) or isinstance(age, bool) or age < 0:
        errors.append("recovery_interval.recovery_age_seconds is missing or negative")
    # External state: the database restore proves none of it.
    if _missing(external.get("files_bucket")):
        errors.append("external_state.files_bucket is missing")
    pinned, restored = (
        external.get("pinned_generations_sha256"),
        external.get("restored_generations_sha256"),
    )
    if not (isinstance(pinned, str) and re.fullmatch(r"[0-9a-f]{64}", pinned)):
        errors.append("external_state.pinned_generations_sha256 is missing")
    elif pinned != restored:
        errors.append(
            "external_state file generations after the restore differ from the ones pinned at "
            "backup time"
        )
    references = set(external.get("key_version_references") or [])
    available = set(external.get("key_versions_available") or [])
    if not references:
        errors.append("external_state.key_version_references is empty")
    missing_keys = sorted(references - available)
    if missing_keys:
        errors.append(f"key versions referenced but not served: {', '.join(missing_keys)}")
    # P2/P6 integration control 4: the required security-key set is DERIVED from the source-bound
    # baseline (every key id its global chain named plus its pin) and the verifier's own inventory
    # on the clone; a self-declared reference list that is merely a subset of a self-declared
    # available list proves nothing. Each required version must be referenced, served by the
    # provider AND opened by the restore verifier's identity.
    # H3: the summaries are bound to the retained evidence. The validator recomputes the hashes of
    # the retained documents and re-derives every security-key summary from their bytes; a summary
    # that differs from its evidence is refused, and the required set below is derived from the
    # retained documents, never from the summaries.
    evidence = _section(document, "evidence")
    retained_verification = evidence.get("verification")
    retained_baseline = evidence.get("baseline")
    if not isinstance(retained_verification, Mapping):
        errors.append("evidence.verification (the retained verify document) is missing")
        retained_verification = {}
    if not isinstance(retained_baseline, Mapping):
        errors.append("evidence.baseline (the retained backup-time document) is missing")
        retained_baseline = {}
    else:
        recorded = anchors.get("baseline_sha256")
        if recorded != hashlib.sha256(_canonical(retained_baseline)).hexdigest():
            errors.append("audit_anchors.baseline_sha256 does not match the retained baseline")
    if (
        retained_verification
        and verification.get("document_sha256")
        != hashlib.sha256(_canonical(retained_verification)).hexdigest()
    ):
        errors.append("verification.document_sha256 does not match the retained verify document")
    for label, retained in (
        ("verification document", retained_verification),
        ("baseline document", retained_baseline),
    ):
        if retained:
            errors.extend(security_evidence_errors(retained, label=label))
    derived_baseline = _security_summary(retained_baseline) if retained_baseline else None
    derived_restored = _security_summary(retained_verification) if retained_verification else None
    summary_checks = []
    if derived_baseline is not None:
        summary_checks += [
            ("baseline_security_key_ids", derived_baseline["key_ids"]),
            ("baseline_security_pin", derived_baseline["pin"]),
            ("baseline_security_head", derived_baseline["head"]),
        ]
    if derived_restored is not None:
        summary_checks += [
            ("restored_security_key_ids", derived_restored["key_ids"]),
            ("restored_security_pin", derived_restored["pin"]),
            ("restored_security_head", derived_restored["head"]),
            ("security_keys_served", derived_restored["served"]),
        ]
    for name, derived in summary_checks:
        recorded_value = anchors.get(name)
        if isinstance(derived, list):
            recorded_value = sorted(map(str, recorded_value or []), key=_version_or_zero)
        if recorded_value != derived:
            errors.append(f"audit_anchors.{name} does not match the retained evidence")
    baseline_ids = derived_baseline["key_ids"] if derived_baseline else []
    baseline_pin = derived_baseline["pin"] if derived_baseline else None
    restored_ids = derived_restored["key_ids"] if derived_restored else []
    restored_pin = derived_restored["pin"] if derived_restored else None
    served_by_verifier = set(derived_restored["served"]) if derived_restored else set()
    if not baseline_ids or _missing(baseline_pin):
        errors.append(
            "the retained baseline names no security key ids or pin: the required security-key "
            "set cannot be derived from the source-bound baseline"
        )
    required_ids = sorted(
        {*baseline_ids, *restored_ids}
        | ({str(baseline_pin)} if not _missing(baseline_pin) else set())
        | ({str(restored_pin)} if not _missing(restored_pin) else set()),
        key=_version_or_zero,
    )
    for key_id in required_ids:
        try:
            version = pf.security_key_version(key_id)
        except pf.PreflightError:
            errors.append(f"security key id {key_id!r} is not a security-hmac:<n> key id")
            continue
        referenced = any(_names_security_version(name, version) for name in references)
        provided = any(_names_security_version(name, version) for name in available)
        if not referenced:
            errors.append(
                f"security HMAC key {key_id} required by the baseline or the clone is not among "
                "external_state.key_version_references"
            )
        if not provided:
            errors.append(
                f"security HMAC key {key_id} required by the baseline or the clone was not "
                "served by the provider"
            )
        if key_id not in served_by_verifier:
            errors.append(
                f"security HMAC key {key_id} required by the baseline or the clone was not "
                "opened by the restore verifier"
            )
    if not external.get("digest_objects"):
        errors.append("external_state.digest_objects is empty: no independent audit anchors")
    # Verification on the clone (review 779847e): acceptance is derived from the RETAINED verifier
    # document, and every projected summary the record presents (result, schema, findings,
    # expected-anchor result, tenant inventory, tenant heads, security head) must equal what the
    # retained bytes say; an editable summary can never turn a failed verifier into a pass.
    view = verifier_projection(retained_verification) if retained_verification else None
    if view is None:
        errors.append("verification cannot be judged: no retained verify document")
    else:
        if view["schema"] != DOCUMENT_SCHEMA:
            errors.append("verification document is not an erev verify document")
        if view["result"] != "PASS":
            errors.append(f"verification result is {view['result']!r}, not PASS")
        if view["expected_result"] != "PASS":
            errors.append(
                "audit anchors: the backup-time expected document did not anchor (or is absent)"
            )
        if not view["tenant_inventory"]:
            errors.append("tenant_inventory is empty")
        projected = {
            "verification.result": (verification.get("result"), view["result"]),
            "verification.schema": (verification.get("schema"), view["schema"]),
            "verification.findings": (
                [str(f) for f in verification.get("findings") or []],
                view["findings"],
            ),
            "audit_anchors.expected_result": (
                anchors.get("expected_result"),
                view["expected_result"],
            ),
            "audit_anchors.security_head": (
                anchors.get("security_head"),
                view["security_head"],
            ),
            "audit_anchors.tenant_heads": (
                {str(k): v for k, v in (anchors.get("tenant_heads") or {}).items()}
                if isinstance(anchors.get("tenant_heads"), Mapping)
                else anchors.get("tenant_heads"),
                view["tenant_heads"],
            ),
            "tenant_inventory": (
                [
                    {"tenant_id": t.get("tenant_id"), "code": t.get("code")}
                    for t in document.get("tenant_inventory") or []
                    if isinstance(t, Mapping)
                ]
                if isinstance(document.get("tenant_inventory"), list)
                else document.get("tenant_inventory"),
                view["tenant_inventory"],
            ),
        }
        for name, (recorded_value, derived) in projected.items():
            if recorded_value != derived:
                errors.append(f"{name} does not match the retained verify document")
    # Assurances: no bypass, no partial dump, no relaxed policy, RLS forced.
    if assurances.get("rls_forced") is not True:
        errors.append("assurances.rls_forced is not true")
    for name in ("bypass_used", "partial_dump", "policies_relaxed", "impersonation_used"):
        if assurances.get(name) is not False:
            errors.append(f"assurances.{name} is not false")
    if document.get("managed_bytes_sha256") is not None:
        errors.append(
            "managed_bytes_sha256 is set: a hash of provider-managed bytes cannot be taken"
        )
    return errors


class MockManagedProvider:
    """A Cloud SQL stand-in for tests: backup runs, restores and external listings come from
    fixtures; nothing is called."""

    def __init__(
        self,
        *,
        backups: Sequence[ManagedBackup],
        restores: Mapping[str, ManagedRestore],
        listings: Mapping[str, Sequence[tuple[str, int]]],
    ) -> None:
        self._backups = {(b.project, b.instance, b.backup_id or b.pitr_instant): b for b in backups}
        self._restores = dict(restores)
        self._listings = {name: list(items) for name, items in listings.items()}

    def backup(self, project: str, instance: str, reference: str) -> ManagedBackup | None:
        """The backup run ``reference`` of ``instance`` in ``project``; None when unknown, and
        also None for the same id on another instance (ids are unique per instance only)."""
        return self._backups.get((project, instance, reference))

    def restore(self, target_instance: str) -> ManagedRestore | None:
        return self._restores.get(target_instance)

    def generations_sha256(self, view: str) -> str:
        """SHA-256 of the sorted (object, generation) listing of a bucket view."""
        listing = sorted(self._listings.get(view, []))
        return hashlib.sha256(json.dumps(listing).encode("ascii")).hexdigest()


def build_managed_record(
    *,
    provider: MockManagedProvider,
    project: str,
    instance: str,
    reference: str,
    target_instance: str,
    files_bucket: str,
    pinned_view: str,
    restored_view: str,
    key_version_references: Sequence[str],
    key_versions_available: Sequence[str],
    digest_objects: Sequence[str],
    shred_tombstones: int,
    verification: Mapping[str, Any],
    measured_at: datetime,
    assurances: Assurances | None = None,
    baseline: Mapping[str, Any] | None = None,
) -> ManagedRestoreRecord:
    """Assemble the record of one managed drill from what the provider and the verifier report;
    unknown backups or restores are recorded as such (and then refused by validation)."""
    backup = provider.backup(project, instance, reference)
    if backup is None:
        backup = ManagedBackup(
            project=project,
            instance=instance,
            kind="AUTOMATED",
            backup_id=reference,
            pitr_instant=None,
            operation_status="UNKNOWN",
            started_at=None,
            finished_at=None,
            database_version="",
            engine_version="",
            schema_revision="",
            release_build_sha="",
        )
    restore = provider.restore(target_instance) or ManagedRestore(
        project="",
        instance=target_instance,
        fresh_instance=False,
        operation_status="UNKNOWN",
        started_at=None,
        finished_at=None,
    )
    external = ExternalState(
        files_bucket=files_bucket,
        pinned_generations_sha256=provider.generations_sha256(pinned_view),
        restored_generations_sha256=provider.generations_sha256(restored_view),
        key_version_references=tuple(key_version_references),
        key_versions_available=tuple(key_versions_available),
        digest_objects=tuple(digest_objects),
        shred_tombstones=shred_tombstones,
    )
    return ManagedRestoreRecord(
        backup=backup,
        restore=restore,
        external=external,
        verification=dict(verification),
        measured_at=measured_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        assurances=assurances or Assurances(),
        baseline=None if baseline is None else dict(baseline),
    )
