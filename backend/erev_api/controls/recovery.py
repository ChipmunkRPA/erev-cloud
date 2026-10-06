"""Recovery verification KRN-RCV (05 §7.3 OPR-11 steps (3), (4) and (6), OPR-12, OPR-15, OPR-17,
SAR-31; §7.7 RB-04 to RB-06; REQ-OPS-013; production readiness audit DEP-F, package 4).

``verify_all_tenants`` is what ``erev verify --all-tenants`` runs against one database, one file
store and one key ring, live or restored into an isolated ``erev_rv_*`` clone:

- the global ``security_event`` chain, each tenant's ``audit_event`` chain anchored to its head and
  to its latest earlier PASS digest (D-80), and each book's ledger seal chain (DB-06);
- each tenant's latest SAR-31 digest against the chain: the event at the digest's sequence still
  carries the digest's HMAC, and the number of events appended since it (the gap of OPR-11 (4));
- the file store: every ``file_object`` row has its object, encrypted purposes decrypt under their
  sidecar and hash back to ``sha256``, and a shredded row has no sidecar left;
- the key versions in use (tenant audit HMAC ids, the security HMAC id, KEK ids of sidecars and
  envelopes) and whether the running key provider serves each one (OPR-17).

The document it returns is what ``make backup`` writes next to the dump (the backup-time digests)
and what ``make restore-verify`` reads back through ``anchor_requests``, ``resolve_anchors`` and
``compare_expected``: every recorded chain head must still be present in the restored chains with
the same hash (a chain may have grown between the digest and the dump), every recorded file must
verify again and every recorded key must be served. ``record_restore_applied`` is OPR-11 step (6):
the ``platform.restore_applied`` event of every ACTIVE tenant after a cutover, naming the restore
instant, the backup, the previous head and the new head. Nothing here restores anything: a restore
is ``pg_restore`` into a clone (RB-04), never in place (REQ-PLT-024).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import func, select

from erev_api.audit.verify import ChainVerificationResult, rfc3339, verify_tenant_chain_anchored
from erev_api.audit.writer import record_facts
from erev_api.auth import recovery_reads
from erev_api.auth.mfa import secret_context as mfa_secret_context
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.auth.security_events import chain_head, required_security_key_ids
from erev_api.controls.ledger_chain_registry import verify_ledger_chain
from erev_api.controls.recovery_preflight import DOCUMENT_SCHEMA, security_key_version
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables import (
    audit_chain_head,
    audit_chain_verification,
    audit_event,
    file_object,
    ledger_chain_head,
    subledger_posting_seal,
    tenant,
    webhook_endpoint,
)
from erev_api.enums import ControlResult, FilePurpose, TenantKind, TenantStatus
from erev_api.events.webhooks import secret_context as webhook_secret_context
from erev_api.files import policy
from erev_api.files.store import (
    content_tenant,
    encryption_context,
    shred_marker_key,
    sidecar_key,
)
from erev_api.uow import unit_of_work

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.clock import Clock
    from erev_api.files.store import FileStore

RESTORE_APPLIED_ACTION: Final = "platform.restore_applied"  # 05 OPR-11 (6)
RESTORE_APPLIED_OBJECT: Final = "tenant"
CHUNK_BYTES: Final = 1024 * 1024
# File statuses; anything but OK and SHREDDED is a failure.
FILE_OK: Final = "ok"
FILE_SHREDDED: Final = "shredded"
FILE_MISSING_OBJECT: Final = "missing_object"
FILE_MISSING_SIDECAR: Final = "missing_sidecar"
FILE_SHREDDED_SIDECAR_PRESENT: Final = "shredded_sidecar_present"
FILE_UNDECRYPTABLE: Final = "undecryptable"
# The row names the object of a workspace that is neither its own nor its sandbox's source (05
# SBX-03 rev 1.196): a fault of the stored data, told apart from a key that does not open.
FILE_FOREIGN_KEY: Final = "foreign_storage_key"
FILE_SHA256_MISMATCH: Final = "sha256_mismatch"
FILE_SIZE_MISMATCH: Final = "size_mismatch"
FILE_GOOD_STATUSES: Final = frozenset({FILE_OK, FILE_SHREDDED})
# Erasure evidence a store can report per sidecar (P2/P8 lifecycle interface, review P6-R6); the
# local store reports live absence only.
ERASURE_LOCAL_LIVE: Final = "local-live-absence"
ERASURE_VERSIONED: Final = "versioned-store-inventory"
ERASURE_VERSIONED_INVALID: Final = "versioned-store-inventory-invalid"
INVENTORY_COUNTS: Final = ("live", "noncurrent", "soft_deleted", "retained_copies")
INVENTORY_COMPLETIONS: Final = ("complete", "pending", "retained")


@dataclass(frozen=True, slots=True)
class _Tenant:
    id: UUID
    code: str
    status: str
    audit_hmac_key_id: str
    # The workspace a sandbox was copied from: its copied files lie under that workspace's keys.
    source_tenant_id: UUID | None = None


@dataclass(frozen=True, slots=True, order=True)
class Anchor:
    """One recorded chain head to find again in a restored database (``compare_expected``)."""

    kind: str  # "security", "audit" or "ledger"
    tenant_id: str  # "" for the security chain
    book_code: str  # "" unless kind == "ledger"
    chain_seq: int


def _chain_document(result: ChainVerificationResult) -> dict[str, Any]:
    return {
        "result": result.result.value,
        "from_chain_seq": result.from_chain_seq,
        "to_chain_seq": result.to_chain_seq,
        "events_checked": result.events_checked,
        "first_failure_seq": result.first_failure_seq,
        "reason": None if result.failure_detail is None else result.failure_detail.get("reason"),
    }


def _rfc3339_or_none(moment: datetime | None) -> str | None:
    return None if moment is None else rfc3339(moment)


def _later(first: datetime | None, second: datetime | None) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _tenants(*, keyring: KeyRing, request_id: str) -> list[_Tenant]:
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as session:
        rows = session.execute(
            select(
                tenant.c.id,
                tenant.c.code,
                tenant.c.status,
                tenant.c.audit_hmac_key_id,
                tenant.c.source_tenant_id,
            ).order_by(tenant.c.code)
        ).all()
    return [
        _Tenant(
            row.id,
            str(row.code),
            str(row.status),
            str(row.audit_hmac_key_id),
            None if row.source_tenant_id is None else UUID(str(row.source_tenant_id)),
        )
        for row in rows
    ]


def security_key_inventory(session: Any, keyring: KeyRing) -> tuple[list[str], str, str]:
    """``(required key ids, current pin id, chain head key id)`` of the GLOBAL T-PLT-06 chain (P2/P6
    integration; 05 OPR-11, RB-05).

    Lane P2's contract: ``required_security_key_ids(bind, keyring)`` is every distinct
    ``security-hmac:<n>`` the rows name (legacy NULL → ``security-hmac:1``) plus
    ``keyring.current_security_key_id()`` (the deployment pin
    ``EREV_SECURITY_HMAC_SECRET_VERSION``), sorted by version; ``chain_head(session).key_id`` is
    the key of the head row. Rows at versions
    1 and 3 under pin 5 give {1, 3, 5}: a restored deployment must serve every one of them. The
    contract is a hard import (supervisor ruling of 2026-09-19): a tree without it fails to import
    this module, never skips or assumes a version.
    """
    required = [str(key_id) for key_id in required_security_key_ids(session, keyring)]
    current = str(keyring.current_security_key_id())
    head_key = str(chain_head(session).key_id)
    if current not in required:
        required.append(current)
    if head_key not in required:
        required.append(head_key)
    return sorted(set(required), key=security_key_version), current, head_key


def probe_security_keys(
    required: Sequence[str], *, current_key: str, head_key: str, keyring: KeyRing
) -> tuple[list[dict[str, Any]], list[str]]:
    """Each required security key id probed individually through the key provider (ids and
    availability only; the material is discarded), plus the failures: an unserved required id,
    and a head signed above the process pin (a stale pin may not append, KEY-03)."""
    keys = [
        {
            "key_id": key_id,
            "available": _key_available(lambda k=key_id: keyring.security_event_key(k)),
            "current": key_id == current_key,
            "head": key_id == head_key,
        }
        for key_id in required
    ]
    failures = [
        f"security HMAC key {entry['key_id']} required by the security chain or the current pin "
        "is not served by the key provider"
        for entry in keys
        if not entry["available"]
    ]
    if security_key_version(head_key) > security_key_version(current_key):
        failures.append(
            f"the security chain head is signed under {head_key} but the process pin is "
            f"{current_key}: a stale pin may not append (KEY-03)"
        )
    return keys, failures


def _key_available(probe: Any) -> bool:
    try:
        probe()
    except Exception:  # noqa: BLE001 - any provider error means the key is not served
        return False
    return True


def _sha256_of(stream: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK_BYTES):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def check_file(
    row: Mapping[str, Any],
    *,
    files: FileStore,
    keyring: KeyRing,
    source_tenant_id: UUID | None = None,
) -> tuple[str, str | None]:
    """The status of one ``file_object`` row against the store and the KEK id of its sidecar.

    Encrypted purposes decrypt under their sidecar and must hash back to ``sha256`` with
    ``size_bytes`` bytes; other purposes hash as stored. A shredded row passes only when its
    sidecar is gone (05 PRV-07); its object is not read.

    ``source_tenant_id`` is the workspace the row's sandbox was copied from, None for a
    production workspace (05 SBX-03 rev 1.196; item SBX-FILE-READ-1). A copied row lies under
    its source's key and is read as the product reads it (``files.store.content_tenant``): the
    associated data names the source, and a file the source has shredded — the marker stands,
    the copy's own row was never stamped — is ``shredded``, as its read answers. A row that
    names the object of any other workspace is ``foreign_storage_key``. For a row under its
    own key nothing changes: an unmarked row without its sidecar stays ``missing_sidecar``.
    """
    key = str(row["storage_key"])
    purpose = FilePurpose(str(row["purpose"]))
    encrypted = purpose in policy.ENCRYPTED_PURPOSES
    kek_id: str | None = None
    tenant_id = UUID(str(row["tenant_id"]))
    stored_by = content_tenant(tenant_id, key, source_tenant_id=source_tenant_id)
    if stored_by is None:
        return FILE_FOREIGN_KEY, None
    if row["shredded_at"] is not None:
        if encrypted and files.exists(sidecar_key(key)):
            return FILE_SHREDDED_SIDECAR_PRESENT, None
        return FILE_SHREDDED, None
    if encrypted and stored_by != tenant_id and files.exists(shred_marker_key(key)):
        return FILE_SHREDDED, None
    if not files.exists(key):
        return FILE_MISSING_OBJECT, None
    if not encrypted:
        with files.open(key) as stored:
            sha256, size = _sha256_of(stored)
    else:
        if not files.exists(sidecar_key(key)):
            return FILE_MISSING_SIDECAR, None
        context = encryption_context(stored_by, key)
        try:
            with files.open(sidecar_key(key)) as stored_key:
                sidecar = stored_key.read()
            kek_id = keyring.envelope_key_id(sidecar)
            dek = keyring.file_key(sidecar, context=context)
            with files.open(key) as stored:
                plaintext = keyring.open_file(dek, stored.read(), context=context)
        except Exception:  # noqa: BLE001 - InvalidTag, a foreign KEK or a malformed sidecar
            return FILE_UNDECRYPTABLE, kek_id
        sha256, size = hashlib.sha256(plaintext).hexdigest(), len(plaintext)
    if sha256 != str(row["sha256"]):
        return FILE_SHA256_MISMATCH, kek_id
    if size != int(row["size_bytes"]):
        return FILE_SIZE_MISMATCH, kek_id
    return FILE_OK, kek_id


def erasure_state(row: Mapping[str, Any], *, files: FileStore) -> dict[str, Any]:
    """What the store can say about a shredded row's sidecar (05 PRV-07, OPR-10; review P6-R6).

    The local store answers only whether a live sidecar exists; a versioned store implementing
    ``sidecar_versions(key)`` (the P2/P8 lifecycle interface) reports live, noncurrent and
    soft-deleted generations and retained copies. Local absence supports local access denial; it
    never stands in for hosted irreversibility, which ``scope`` names.
    """
    key = sidecar_key(str(row["storage_key"]))
    live_present = files.exists(key)
    inventory = getattr(files, "sidecar_versions", None)
    versions: dict[str, Any] | None = None
    scope = ERASURE_LOCAL_LIVE
    if callable(inventory):
        scope = ERASURE_VERSIONED
        try:
            versions = dict(inventory(key))
        except Exception:  # noqa: BLE001 - an inventory error is reported, never masked
            versions = {"error": "inventory unavailable"}
    complete: bool | None = None
    if versions is not None:
        # R6 residual: an inventory counts only when it is explicit and complete (every generation
        # class and the retained-copy/completion state); an absent field is never read as zero, so
        # an empty inventory is invalid, not "all generations gone".
        problems = inventory_problems(versions)
        label = "incomplete inventory"
        if not problems:
            # Review ef8d8d3 residual 1: metadata that contradicts what the store answers about
            # the live sidecar is inconsistent, never "gone".
            label = "inconsistent inventory"
            if int(versions["live"]) == 0 and live_present:
                problems.append("inventory reports no live generation but the live sidecar exists")
            elif int(versions["live"]) > 0 and not live_present:
                problems.append("inventory reports a live generation but no live sidecar exists")
        if problems:
            versions = {"error": f"{label}: " + "; ".join(problems), **versions}
            scope = ERASURE_VERSIONED_INVALID
        else:
            complete = (
                all(int(versions[name]) == 0 for name in INVENTORY_COUNTS)
                and versions["completion"] == "complete"
            )
    return {
        "shredded_at": None if row["shredded_at"] is None else str(row["shredded_at"]),
        "live_sidecar_present": live_present,
        "scope": scope,
        "versions": versions,
        "all_generations_gone": complete,
    }


def inventory_problems(versions: Mapping[str, Any]) -> list[str]:
    """Why a versioned store's sidecar inventory is not complete. The P2/P8 lifecycle interface is
    ``sidecar_versions(key) -> {live, noncurrent, soft_deleted, retained_copies: int >= 0,
    completion: "complete" | "pending" | "retained"}``; every field is required."""
    problems = []
    if "error" in versions:
        problems.append(str(versions["error"]))
    for name in INVENTORY_COUNTS:
        value = versions.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"{name} count missing")
    if versions.get("completion") not in INVENTORY_COMPLETIONS:
        problems.append("completion state missing")
    return problems


def _digest_file(files: FileStore, rows: Sequence[Mapping[str, Any]], file_id: UUID | None) -> Any:
    if file_id is None:
        return None
    row = next((r for r in rows if r["id"] == file_id), None)
    if row is None or row["shredded_at"] is not None or not files.exists(str(row["storage_key"])):
        return {"present": False}
    try:
        with files.open(str(row["storage_key"])) as stored:
            document = json.loads(stored.read().decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return {"present": True, "parsed": False}
    return {"present": True, "parsed": True, "document": document}


def _verify_tenant(
    workspace: _Tenant, *, keyring: KeyRing, files: FileStore, check_files: bool
) -> tuple[dict[str, Any], list[str]]:
    ctx = DbContext(tenant_id=workspace.id, user_id=None, entity_scope="*")
    failures: list[str] = []
    with tenant_session(ctx, read_only=True) as session:
        chain = verify_tenant_chain_anchored(session, tenant_id=workspace.id, keyring=keyring)
        head = session.execute(
            select(
                audit_chain_head.c.last_chain_seq,
                audit_chain_head.c.last_hmac,
                audit_chain_head.c.last_occurred_at,
            ).where(audit_chain_head.c.tenant_id == workspace.id)
        ).one_or_none()
        digest_row = session.execute(
            select(
                audit_chain_verification.c.to_chain_seq,
                audit_chain_verification.c.digest_last_hmac,
                audit_chain_verification.c.digest_file_id,
                audit_chain_verification.c.finished_at,
            )
            .where(
                audit_chain_verification.c.tenant_id == workspace.id,
                audit_chain_verification.c.result == ControlResult.PASS.value,
            )
            .order_by(
                audit_chain_verification.c.finished_at.desc(),
                audit_chain_verification.c.to_chain_seq.desc(),
                audit_chain_verification.c.id.desc(),
            )
            .limit(1)
        ).one_or_none()
        digest_event_hmac = None
        if digest_row is not None:
            digest_event_hmac = session.execute(
                select(audit_event.c.hmac).where(
                    audit_event.c.tenant_id == workspace.id,
                    audit_event.c.chain_seq == int(digest_row.to_chain_seq),
                )
            ).scalar_one_or_none()
        used_key_ids = sorted(
            str(key_id)
            for key_id in session.execute(
                select(audit_event.c.hmac_key_id)
                .distinct()
                .where(audit_event.c.tenant_id == workspace.id)
            ).scalars()
        )
        books = [
            str(code)
            for code in session.execute(
                select(ledger_chain_head.c.book_code)
                .where(ledger_chain_head.c.tenant_id == workspace.id)
                .order_by(ledger_chain_head.c.book_code)
            ).scalars()
        ]
        ledgers = [verify_ledger_chain(session, book_code=code) for code in books]
        seal_counts = {
            str(code): int(count)
            for code, count in session.execute(
                select(subledger_posting_seal.c.book_code, func.count())
                .where(subledger_posting_seal.c.tenant_id == workspace.id)
                .group_by(subledger_posting_seal.c.book_code)
            )
        }
        webhook_rows = [
            dict(mapping)
            for mapping in session.execute(
                select(
                    webhook_endpoint.c.id,
                    webhook_endpoint.c.secret_ciphertext,
                    webhook_endpoint.c.secret_key_id,
                ).where(webhook_endpoint.c.tenant_id == workspace.id)
            ).mappings()
        ]
        file_rows: list[Mapping[str, Any]] = [
            dict(mapping)
            for mapping in session.execute(
                select(file_object)
                .where(file_object.c.tenant_id == workspace.id)
                .order_by(file_object.c.storage_key)
            ).mappings()
        ]

    if chain.result is not ControlResult.PASS:
        failures.append(
            f"{workspace.code}: audit chain {chain.result.value} at sequence "
            f"{chain.first_failure_seq}: {_chain_document(chain)['reason']}"
        )
    head_seq = None if head is None else int(head.last_chain_seq)
    digest: dict[str, Any] | None = None
    gap: int | None = None
    if digest_row is not None:
        digest_seq = int(digest_row.to_chain_seq)
        last_hmac = (
            None if digest_row.digest_last_hmac is None else str(digest_row.digest_last_hmac)
        )
        matches = digest_event_hmac is not None and str(digest_event_hmac) == last_hmac
        gap = None if head_seq is None else head_seq - digest_seq
        digest = {
            "last_chain_seq": digest_seq,
            "last_hmac": last_hmac,
            "verified_at": rfc3339(digest_row.finished_at),
            "file_id": None
            if digest_row.digest_file_id is None
            else str(digest_row.digest_file_id),
            "event_matches": matches,
        }
        if not matches:
            failures.append(
                f"{workspace.code}: the event at digest sequence {digest_seq} no longer carries "
                "the digest hmac"
            )
        if check_files:
            digest_file = _digest_file(files, file_rows, digest_row.digest_file_id)
            if digest_file is not None:
                document = digest_file.get("document") or {}
                digest_file["matches_row"] = bool(document) and (
                    document.get("last_hmac") == last_hmac
                    and int(document.get("last_chain_seq") or -1) == digest_seq
                )
                digest_file.pop("document", None)
                digest["file"] = digest_file
                if digest_file.get("present") and not digest_file["matches_row"]:
                    failures.append(
                        f"{workspace.code}: the stored digest file does not match the "
                        "verification row"
                    )

    ledger_documents = []
    for verification in ledgers:
        ledger_documents.append(
            {
                "book_code": verification.book_code,
                "result": verification.result.value,
                "seals_checked": verification.seals_checked,
                "last_chain_seq": seal_counts.get(verification.book_code, 0),
                "last_seal_sha256": verification.last_seal_sha256,
                "first_failure_seq": verification.first_failure_seq,
                "reason": None
                if verification.failure_detail is None
                else verification.failure_detail.get("reason"),
            }
        )
        if verification.result is not ControlResult.PASS:
            failures.append(
                f"{workspace.code}: ledger chain {verification.book_code} FAIL at seal "
                f"{verification.first_failure_seq}: {ledger_documents[-1]['reason']}"
            )

    key_ids = sorted(set(used_key_ids) | {workspace.audit_hmac_key_id})
    keys = [
        {
            "key_id": key_id,
            "current": key_id == workspace.audit_hmac_key_id,
            "in_use": key_id in used_key_ids,
            "available": _key_available(lambda key_id=key_id: keyring.tenant_audit_key(key_id)),
        }
        for key_id in key_ids
    ]
    for entry in keys:
        if not entry["available"]:
            failures.append(
                f"{workspace.code}: audit HMAC key {entry['key_id']} is not served by the key "
                "provider"
            )

    # P6-R5: every webhook secret is opened under its KEK; an id that is only listed proves
    # nothing, an envelope that opens does.
    envelopes: list[dict[str, Any]] = []
    for hook in webhook_rows:
        probe = _probe_envelope(
            keyring,
            bytes(hook["secret_ciphertext"]),
            webhook_secret_context(workspace.id, UUID(str(hook["id"]))),
            recorded_key_id=str(hook["secret_key_id"]),
        )
        envelopes.append({"kind": "webhook", "row_id": str(hook["id"]), **probe})
        if not probe["opened"]:
            failures.append(
                f"{workspace.code}: webhook endpoint {hook['id']} secret does not open under "
                f"{probe['key_id']}"
            )

    entries: list[dict[str, Any]] = []
    counts = {
        "checked": 0,
        "ok": 0,
        "shredded": 0,
        "failed": 0,
    }
    if check_files:
        for row in file_rows:
            status, kek_id = check_file(
                row, files=files, keyring=keyring, source_tenant_id=workspace.source_tenant_id
            )
            counts["checked"] += 1
            if status == FILE_OK:
                counts["ok"] += 1
            elif status == FILE_SHREDDED:
                counts["shredded"] += 1
            else:
                counts["failed"] += 1
                failures.append(f"{workspace.code}: file {row['storage_key']} {status}")
            file_entry: dict[str, Any] = {
                "file_id": str(row["id"]),
                "storage_key": str(row["storage_key"]),
                "purpose": str(row["purpose"]),
                "sha256": str(row["sha256"]),
                "size_bytes": int(row["size_bytes"]),
                "encrypted": FilePurpose(str(row["purpose"])) in policy.ENCRYPTED_PURPOSES,
                "kek_id": kek_id,
                "status": status,
            }
            if row["shredded_at"] is not None:
                file_entry["erasure"] = erasure_state(row, files=files)
            entries.append(file_entry)

    document = {
        "tenant_id": str(workspace.id),
        "code": workspace.code,
        "status": workspace.status,
        "audit_chain": _chain_document(chain),
        # R2 residual: a tenant without a chain head row records an explicit empty head (sequence
        # 0, no hash) so the baseline is complete; an omitted head is refused by the drill.
        "head": {"last_chain_seq": 0, "last_hmac": None, "last_occurred_at": None}
        if head is None
        else {
            "last_chain_seq": head_seq,
            "last_hmac": None if head.last_hmac is None else str(head.last_hmac),
            "last_occurred_at": _rfc3339_or_none(head.last_occurred_at),
        },
        "digest": digest,
        "gap_events": gap,
        "ledger_chains": ledger_documents,
        "audit_hmac_keys": keys,
        "envelopes": envelopes,
        "kek_ids": sorted(
            {str(e["key_id"]) for e in envelopes} | {e["kek_id"] for e in entries if e["kek_id"]}
        ),
        "files": {**counts, "entries": entries},
    }
    return document, failures


def _probe_envelope(
    keyring: KeyRing, blob: bytes, context: Mapping[str, str], *, recorded_key_id: str
) -> dict[str, Any]:
    """Open one SAR-07 envelope and discard the plaintext: proof that its KEK is served."""
    key_id = recorded_key_id
    try:
        key_id = keyring.envelope_key_id(blob)
        keyring.decrypt(blob, context=context)
    except Exception:  # noqa: BLE001 - a wrong or absent KEK, a foreign context or a malformed blob
        return {"key_id": key_id, "recorded_key_id": recorded_key_id, "opened": False}
    return {"key_id": key_id, "recorded_key_id": recorded_key_id, "opened": True}


def kek_inventory(
    tenant_documents: Sequence[Mapping[str, Any]], mfa_probes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Per KEK id: how many sidecars, webhook secrets and MFA seeds reference it and how many of
    them opened; ``available`` only when every reference opened (review P6-R5)."""
    table: dict[str, dict[str, int]] = {}

    def bucket(key_id: str) -> dict[str, int]:
        return table.setdefault(
            key_id,
            {
                "sidecars": 0,
                "sidecars_opened": 0,
                "webhooks": 0,
                "webhooks_opened": 0,
                "mfa": 0,
                "mfa_opened": 0,
            },
        )

    for document in tenant_documents:
        for entry in document["files"]["entries"]:
            if not entry.get("encrypted") or entry["status"] == FILE_SHREDDED:
                continue
            counts = bucket(str(entry.get("kek_id") or "unknown"))
            counts["sidecars"] += 1
            if entry["status"] == FILE_OK:
                counts["sidecars_opened"] += 1
        for probe in document.get("envelopes", []):
            counts = bucket(str(probe["key_id"]))
            counts["webhooks"] += 1
            counts["webhooks_opened"] += int(bool(probe["opened"]))
    for probe in mfa_probes:
        counts = bucket(str(probe["key_id"]))
        counts["mfa"] += 1
        counts["mfa_opened"] += int(bool(probe["opened"]))
    inventory = []
    for key_id in sorted(table):
        counts = table[key_id]
        references = counts["sidecars"] + counts["webhooks"] + counts["mfa"]
        opened = counts["sidecars_opened"] + counts["webhooks_opened"] + counts["mfa_opened"]
        inventory.append(
            {
                "key_id": key_id,
                **counts,
                "references": references,
                "opened": opened,
                "available": references > 0 and opened == references,
            }
        )
    return inventory


def security_head_seq(*, request_id: str) -> int:
    """The security chain head before this run appends anything (review P6-R7); read through the
    auth repository (DG-KRN-DB-02)."""
    return recovery_reads.security_head_seq(request_id=request_id)


def _security_chain(
    *, keyring: KeyRing, request_id: str, head_before_run: int
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    # The identity-scope reads live in erev_api.auth.recovery_reads (DG-KRN-DB-02); this module
    # receives a snapshot and judges it.
    snapshot = recovery_reads.security_chain_snapshot(
        keyring=keyring,
        request_id=request_id,
        head_before_run=head_before_run,
        inventory=security_key_inventory,
    )
    result = snapshot.result
    mfa_rows = snapshot.mfa_rows
    schema_revision = snapshot.schema_revision
    required_keys, current_key, head_key = (
        snapshot.required_keys,
        snapshot.current_key,
        snapshot.head_key,
    )
    # P2/P6 integration: every key the backed-up chain names and the current pin must be served;
    # a pin behind the chain head is a stale writer (KEY-03) and fails closed here as well.
    keys, key_failures = probe_security_keys(
        required_keys, current_key=current_key, head_key=head_key, keyring=keyring
    )
    available = all(bool(entry["available"]) for entry in keys)
    failures: list[str] = []
    if result.result is not ControlResult.PASS:
        failures.append(
            f"security chain FAIL at sequence {result.first_failure_seq}: "
            f"{_chain_document(result)['reason']}"
        )
    failures.extend(key_failures)
    # P6-R5: every MFA seed is opened under its KEK, disabled factors included (their history
    # must stay verifiable); the plaintext is discarded.
    mfa_probes: list[dict[str, Any]] = []
    for row in mfa_rows:
        probe = _probe_envelope(
            keyring,
            bytes(row["secret_ciphertext"]),
            mfa_secret_context(UUID(str(row["id"]))),
            recorded_key_id=str(row["secret_key_id"]),
        )
        mfa_probes.append(
            {
                "kind": "mfa",
                "row_id": str(row["id"]),
                "disabled": row["disabled_at"] is not None,
                **probe,
            }
        )
        if not probe["opened"]:
            failures.append(f"MFA factor {row['id']} seed does not open under {probe['key_id']}")
    head_seq = snapshot.head_seq
    document = {
        **_chain_document(result),
        "last_chain_seq": head_seq,
        "last_hmac": snapshot.head_hmac,
        "last_occurred_at": _rfc3339_or_none(snapshot.head_occurred_at),
        "head_before_run": head_before_run,
        "verifier_events_appended": max(0, head_seq - head_before_run),
        "recovered_last_occurred_at": _rfc3339_or_none(snapshot.recovered_latest),
        "hmac_key_id": head_key,
        "head_key_id": head_key,
        "current_key_id": current_key,
        "required_key_ids": required_keys,
        "keys": keys,
        "key_available": available,
        "schema_revision": schema_revision,
    }
    return document, failures, mfa_probes


def verify_all_tenants(
    *,
    keyring: KeyRing,
    files: FileStore,
    clock: Clock,
    request_id: str,
    database: str | None = None,
    engine_version: str | None = None,
    tenant_codes: Sequence[str] | None = None,
    check_files: bool = True,
) -> dict[str, Any]:
    """The verification document of OPR-11 step (3) over every tenant (or ``tenant_codes``).

    ``result`` is ``PASS`` only when every chain verifies, every digest still anchors, every file
    of every tenant verifies and every key in use is served. Reading the tenant directory writes
    one ``PLATFORM_SCOPE_USED`` security event, as ``erev doctor`` does.
    """
    started = clock.now()
    head_before_run = security_head_seq(request_id=request_id)
    tenants = _tenants(keyring=keyring, request_id=request_id)
    if tenant_codes is not None:
        wanted = set(tenant_codes)
        unknown = sorted(wanted - {t.code for t in tenants})
        if unknown:
            raise ValueError(f"unknown tenant codes: {', '.join(unknown)}")
        tenants = [t for t in tenants if t.code in wanted]
    failures: list[str] = []
    tenant_documents: list[dict[str, Any]] = []
    latest: datetime | None = None
    file_counts = {"checked": 0, "ok": 0, "shredded": 0, "failed": 0}
    for workspace in tenants:
        document, found = _verify_tenant(
            workspace, keyring=keyring, files=files, check_files=check_files
        )
        tenant_documents.append(document)
        failures.extend(found)
        for name in file_counts:
            file_counts[name] += int(document["files"][name])
        head = document["head"]
        if head is not None and head["last_occurred_at"] is not None:
            latest = _later(latest, datetime.fromisoformat(head["last_occurred_at"]))
    # The security chain last: the directory read above appended to it, which the recovered
    # freshness excludes (P6-R7).
    security, found, mfa_probes = _security_chain(
        keyring=keyring, request_id=request_id, head_before_run=head_before_run
    )
    failures.extend(found)
    schema_revision = security.pop("schema_revision")
    if security["recovered_last_occurred_at"] is not None:
        latest = _later(latest, datetime.fromisoformat(security["recovered_last_occurred_at"]))
    keks = kek_inventory(tenant_documents, mfa_probes)
    for kek in keks:
        if not kek["available"]:
            failures.append(
                f"kek {kek['key_id']}: {kek['references'] - kek['opened']} of {kek['references']} "
                "envelopes do not open"
            )
    audit_keys = sorted(
        {
            (document["tenant_id"], entry["key_id"], bool(entry["available"]))
            for document in tenant_documents
            for entry in document["audit_hmac_keys"]
        }
    )
    return {
        "schema": DOCUMENT_SCHEMA,
        "generated_at": rfc3339(started),
        "database": database,
        "engine_version": engine_version,
        "schema_revision": schema_revision,
        "result": (ControlResult.FAIL if failures else ControlResult.PASS).value,
        "failures": failures,
        "latest_evidence_at": _rfc3339_or_none(latest),
        "verifier_events_appended": security["verifier_events_appended"],
        "security_chain": security,
        "tenants": tenant_documents,
        "mfa_envelopes": mfa_probes,
        "key_versions": {
            "security_hmac": [
                {"key_id": entry["key_id"], "available": bool(entry["available"])}
                for entry in security["keys"]
            ],
            "audit_hmac": [
                {"tenant_id": tenant_id, "key_id": key_id, "available": available}
                for tenant_id, key_id, available in audit_keys
            ],
            "kek": keks,
        },
        "counts": {
            "tenants": len(tenant_documents),
            "tenants_failed": sum(
                1 for d in tenant_documents if d["audit_chain"]["result"] != "PASS"
            ),
            "ledger_chains": sum(len(d["ledger_chains"]) for d in tenant_documents),
            "files": file_counts,
            "failures": len(failures),
        },
    }


def anchor_requests(expected: Mapping[str, Any]) -> list[Anchor]:
    """Every chain head a backup-time document recorded, as anchors to find again."""
    anchors: list[Anchor] = []
    security = expected.get("security_chain") or {}
    seq = int(security.get("last_chain_seq") or 0)
    if seq > 0:
        anchors.append(Anchor("security", "", "", seq))
    for workspace in expected.get("tenants") or []:
        tenant_id = str(workspace["tenant_id"])
        head = workspace.get("head") or {}
        seq = int(head.get("last_chain_seq") or 0)
        if seq > 0:
            anchors.append(Anchor("audit", tenant_id, "", seq))
        for book in workspace.get("ledger_chains") or []:
            seq = int(book.get("last_chain_seq") or 0)
            if seq > 0:
                anchors.append(Anchor("ledger", tenant_id, str(book["book_code"]), seq))
    return anchors


def resolve_anchors(requests: Iterable[Anchor], *, request_id: str) -> dict[Anchor, str | None]:
    """The hash the database holds at each anchor's position, or None when the row is absent."""
    resolved: dict[Anchor, str | None] = {}
    by_tenant: dict[str, list[Anchor]] = {}
    for anchor in requests:
        if anchor.kind == "security":
            resolved[anchor] = recovery_reads.security_anchor(
                anchor.chain_seq, request_id=request_id
            )
        else:
            by_tenant.setdefault(anchor.tenant_id, []).append(anchor)
    for tenant_id, anchors in by_tenant.items():
        ctx = DbContext(tenant_id=UUID(tenant_id), user_id=None, entity_scope="*")
        with tenant_session(ctx, read_only=True) as session:
            for anchor in anchors:
                if anchor.kind == "audit":
                    found = session.execute(
                        select(audit_event.c.hmac).where(
                            audit_event.c.tenant_id == ctx.tenant_id,
                            audit_event.c.chain_seq == anchor.chain_seq,
                        )
                    ).scalar_one_or_none()
                else:
                    found = session.execute(
                        select(subledger_posting_seal.c.seal_sha256).where(
                            subledger_posting_seal.c.tenant_id == ctx.tenant_id,
                            subledger_posting_seal.c.book_code == anchor.book_code,
                            subledger_posting_seal.c.chain_seq == anchor.chain_seq,
                        )
                    ).scalar_one_or_none()
                resolved[anchor] = None if found is None else str(found)
    return resolved


def compare_expected(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    anchors: Mapping[Anchor, str | None],
) -> list[str]:
    """Findings when a restored database does not carry everything a backup-time document
    recorded. Pure: the anchors come from ``resolve_anchors``.

    A restored chain may be longer than the digest (events appended between the digest and the
    dump) but never shorter, and the row at each recorded head must carry the recorded hash.
    Every file recorded as verified must verify again with the same SHA-256, and every key
    recorded in use must be served.
    """
    findings: list[str] = []
    expected_security = expected.get("security_chain") or {}
    actual_security = actual.get("security_chain") or {}
    expected_seq = int(expected_security.get("last_chain_seq") or 0)
    if int(actual_security.get("last_chain_seq") or 0) < expected_seq:
        findings.append(
            f"security chain: restored head {actual_security.get('last_chain_seq')} is before "
            f"the backup-time head {expected_seq}"
        )
    elif expected_seq > 0:
        anchor = anchors.get(Anchor("security", "", "", expected_seq))
        if anchor != expected_security.get("last_hmac"):
            findings.append(
                f"security chain: the event at backup-time head {expected_seq} does not carry "
                "the recorded hmac"
            )
    actual_tenants = {str(t["tenant_id"]): t for t in actual.get("tenants") or []}
    expected_ids = {str(t["tenant_id"]) for t in expected.get("tenants") or [] if "tenant_id" in t}
    for tenant_id, restored in sorted(actual_tenants.items()):
        if tenant_id not in expected_ids:
            findings.append(
                f"{restored.get('code') or tenant_id}: tenant {tenant_id} is in the restored "
                "database but absent from the backup-time document"
            )
    for workspace in expected.get("tenants") or []:
        tenant_id = str(workspace["tenant_id"])
        code = str(workspace.get("code") or tenant_id)
        restored = actual_tenants.get(tenant_id)
        if restored is None:
            findings.append(f"{code}: tenant {tenant_id} is missing from the restored database")
            continue
        head = workspace.get("head")
        restored_head = restored.get("head") or {}
        if not isinstance(head, Mapping):
            # R2 residual: an omitted head is a finding, never a silently skipped anchor.
            findings.append(
                f"{code}: the backup-time document records no audit head for the tenant"
            )
            head = {}
        expected_seq = int(head.get("last_chain_seq") or 0)
        if int(restored_head.get("last_chain_seq") or 0) < expected_seq:
            findings.append(
                f"{code}: restored audit head {restored_head.get('last_chain_seq')} is before the "
                f"backup-time head {expected_seq}"
            )
        elif expected_seq > 0:
            anchor = anchors.get(Anchor("audit", tenant_id, "", expected_seq))
            if anchor != head.get("last_hmac"):
                findings.append(
                    f"{code}: the audit event at backup-time head {expected_seq} does not carry "
                    "the recorded hmac"
                )
        restored_books = {str(b["book_code"]): b for b in restored.get("ledger_chains") or []}
        for book in workspace.get("ledger_chains") or []:
            book_code = str(book["book_code"])
            expected_seq = int(book.get("last_chain_seq") or 0)
            restored_book = restored_books.get(book_code)
            if restored_book is None:
                findings.append(f"{code}: ledger chain {book_code} is missing after the restore")
                continue
            if int(restored_book.get("last_chain_seq") or 0) < expected_seq:
                findings.append(
                    f"{code}: restored ledger chain {book_code} head "
                    f"{restored_book.get('last_chain_seq')} is before the backup-time head "
                    f"{expected_seq}"
                )
            elif expected_seq > 0:
                anchor = anchors.get(Anchor("ledger", tenant_id, book_code, expected_seq))
                if anchor != book.get("last_seal_sha256"):
                    findings.append(
                        f"{code}: the seal at backup-time head {expected_seq} of {book_code} does "
                        "not carry the recorded seal_sha256"
                    )
        restored_files = {
            str(e["storage_key"]): e for e in (restored.get("files") or {}).get("entries") or []
        }
        for entry in (workspace.get("files") or {}).get("entries") or []:
            key = str(entry["storage_key"])
            restored_entry = restored_files.get(key)
            expected_status = entry.get("status")
            if expected_status == FILE_SHREDDED:
                # P6-R6: an erasure recorded at backup time must survive the restore.
                if restored_entry is None:
                    findings.append(
                        f"{code}: file {key} recorded shredded at backup time is missing after the "
                        "restore (its erasure record is gone)"
                    )
                elif restored_entry.get("status") == FILE_OK:
                    findings.append(
                        f"{code}: file {key} recorded shredded at backup time is readable after "
                        "the restore"
                    )
                elif restored_entry.get("status") != FILE_SHREDDED:
                    findings.append(
                        f"{code}: file {key} recorded shredded at backup time is now "
                        f"{restored_entry.get('status')}"
                    )
                continue
            if expected_status != FILE_OK:
                continue
            if restored_entry is None:
                findings.append(f"{code}: file {key} recorded at backup time is missing")
            elif restored_entry.get("status") != FILE_OK:
                status = restored_entry.get("status")
                findings.append(f"{code}: file {key} verified at backup time is now {status}")
            elif restored_entry.get("sha256") != entry.get("sha256"):
                findings.append(f"{code}: file {key} hashes differently after the restore")
        restored_keys = {
            str(k.get("key_id")): bool(k.get("available"))
            for k in restored.get("audit_hmac_keys") or []
            if isinstance(k, Mapping)
        }
        for key in workspace.get("audit_hmac_keys") or []:
            if not isinstance(key, Mapping) or not key.get("key_id"):
                findings.append(f"{code}: the backup-time document has an untyped audit key entry")
                continue
            key_id = str(key["key_id"])
            if not restored_keys.get(key_id, False):
                findings.append(
                    f"{code}: audit HMAC key {key_id} recorded at backup time is missing or not "
                    "served after the restore"
                )
    served = {
        str(k.get("key_id")): bool(k.get("available"))
        for k in actual.get("key_versions", {}).get("security_hmac") or []
        if isinstance(k, Mapping)
    }
    reported: set[str] = set()
    for key in expected.get("key_versions", {}).get("security_hmac") or []:
        if not isinstance(key, Mapping) or not key.get("key_id"):
            findings.append("the backup-time document has an untyped security key entry")
            continue
        if not served.get(str(key["key_id"]), False):
            reported.add(str(key["key_id"]))
            findings.append(f"security HMAC key {key['key_id']} is not served after the restore")
    # P2/P6 integration: every key id the backed-up global chain named, and the pin it was taken
    # under, must be served on the restored copy (rows at 1 and 3 under pin 5 need {1, 3, 5}).
    for key_id in expected_security.get("required_key_ids") or []:
        if str(key_id) in reported or served.get(str(key_id), False):
            continue
        reported.add(str(key_id))
        findings.append(
            f"security HMAC key {key_id} required by the backed-up chain is not served after "
            "the restore"
        )
    # P6-R5: every KEK the backup recorded must open its envelopes after the restore.
    actual_keks = {
        str(k.get("key_id")): bool(k.get("available"))
        for k in actual.get("key_versions", {}).get("kek") or []
        if isinstance(k, Mapping)
    }
    for recorded in expected.get("key_versions", {}).get("kek") or []:
        if isinstance(recorded, Mapping) and not recorded.get("key_id"):
            findings.append("the backup-time document has an untyped kek entry")
            continue
        key_id = str(recorded["key_id"]) if isinstance(recorded, Mapping) else str(recorded)
        if not actual_keks.get(key_id, False):
            findings.append(
                f"kek {key_id} recorded at backup time does not open every envelope after the "
                "restore"
            )
    return findings


def previous_heads_of(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Tenant id → the recorded ``head`` of a verification document (the "previous chain head
    from the digest" of OPR-11 step (6))."""
    heads: dict[str, dict[str, Any]] = {}
    for workspace in document.get("tenants") or []:
        head = workspace.get("head")
        if head is not None:
            heads[str(workspace["tenant_id"])] = {
                "last_chain_seq": head.get("last_chain_seq"),
                "last_hmac": head.get("last_hmac"),
            }
    return heads


def _head_of(tenant_id: UUID) -> dict[str, Any] | None:
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        row = session.execute(
            select(
                tenant.c.kind,
                audit_chain_head.c.last_chain_seq,
                audit_chain_head.c.last_hmac,
            )
            .select_from(tenant.join(audit_chain_head, audit_chain_head.c.tenant_id == tenant.c.id))
            .where(tenant.c.id == tenant_id)
        ).one_or_none()
    if row is None:
        return None
    return {
        "kind": str(row.kind),
        "last_chain_seq": int(row.last_chain_seq),
        "last_hmac": None if row.last_hmac is None else str(row.last_hmac),
    }


def record_restore_applied(
    *,
    keyring: KeyRing,
    files: FileStore,
    clock: Clock,
    request_id: str,
    restore_instant: datetime,
    backup_id: str,
    previous_heads: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """OPR-11 step (6): append ``platform.restore_applied`` to every ACTIVE tenant's audit log.

    The event names the restore instant, the backup, the previous chain head (from the digests
    document when given, else the head found before the append) and is itself the new head. It
    runs as the SYSTEM principal of each tenant; nothing else is written. Notifying Tenant Admins
    is the operator's runbook step (no notification kind exists for it, RB-04).
    """
    applied: list[dict[str, Any]] = []
    for workspace in _tenants(keyring=keyring, request_id=request_id):
        if workspace.status != TenantStatus.ACTIVE.value:
            continue
        before = _head_of(workspace.id)
        if before is None:
            continue
        recorded = (previous_heads or {}).get(str(workspace.id))
        previous = (
            {"last_chain_seq": before["last_chain_seq"], "last_hmac": before["last_hmac"]}
            if recorded is None
            else dict(recorded)
        )
        principal = system_principal(workspace.id)
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind(before["kind"]),
            request_id=request_id,
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=clock.now(),
            format_locale="en-US",
        )
        with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
            record_facts(
                uow,
                action=RESTORE_APPLIED_ACTION,
                object_type=RESTORE_APPLIED_OBJECT,
                ids=[workspace.id],
                detail={
                    "restore_instant": rfc3339(restore_instant),
                    "backup_id": backup_id,
                    "previous_head": previous,
                    "head_before_event": {
                        "last_chain_seq": before["last_chain_seq"],
                        "last_hmac": before["last_hmac"],
                    },
                },
            )
            uow.commit()
        after = _head_of(workspace.id) or {}
        applied.append(
            {
                "tenant_id": str(workspace.id),
                "code": workspace.code,
                "previous_head": previous,
                "new_head": {
                    "last_chain_seq": after.get("last_chain_seq"),
                    "last_hmac": after.get("last_hmac"),
                },
            }
        )
    return applied
