"""Recovery verification: the pure parts of ``erev_api.controls.recovery`` (05 OPR-11 steps (3),
(4) and (6), OPR-12, OPR-17, SAR-31; RB-04 to RB-06; production readiness audit DEP-F).

``anchor_requests`` and ``compare_expected`` decide whether a restored database still carries every
chain head, file and key a backup-time document recorded; ``check_file`` decides the status of one
``file_object`` row against a file store. The database parts run in
``backend/tests/pg/test_recovery_verify.py``.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.controls import recovery
from erev_api.controls.recovery import Anchor
from erev_api.enums import FilePurpose
from erev_api.files.store import LocalFileStore, encryption_context, sidecar_key, storage_key

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
HMAC_A = "a" * 64
HMAC_B = "b" * 64
SEAL_1 = "1" * 64
SEAL_2 = "2" * 64


def _document(
    *,
    security_seq: int = 3,
    security_hmac: str = HMAC_A,
    head_seq: int = 12,
    head_hmac: str = HMAC_B,
    ledger_seq: int = 2,
    ledger_seal: str = SEAL_2,
    files: list[dict[str, Any]] | None = None,
    keys: list[dict[str, Any]] | None = None,
    key_available: bool = True,
) -> dict[str, Any]:
    return {
        "schema": recovery.DOCUMENT_SCHEMA,
        "result": "PASS",
        "failures": [],
        "security_chain": {
            "result": "PASS",
            "last_chain_seq": security_seq,
            "last_hmac": security_hmac,
            "hmac_key_id": "security-hmac:1",
            "head_key_id": "security-hmac:1",
            "current_key_id": "security-hmac:1",
            "required_key_ids": ["security-hmac:1"],
            "key_available": key_available,
        },
        "tenants": [
            {
                "tenant_id": str(TENANT),
                "code": "acme",
                "head": {"last_chain_seq": head_seq, "last_hmac": head_hmac},
                "ledger_chains": [
                    {
                        "book_code": "ASC606",
                        "last_chain_seq": ledger_seq,
                        "last_seal_sha256": ledger_seal,
                    }
                ],
                "files": {
                    "entries": files
                    if files is not None
                    else [
                        {
                            "storage_key": f"{TENANT}/ATTACHMENT/{'c' * 64}",
                            "sha256": "c" * 64,
                            "status": recovery.FILE_OK,
                        }
                    ]
                },
                "audit_hmac_keys": keys
                if keys is not None
                else [{"key_id": f"audit-hmac:{TENANT}:1", "available": True}],
            }
        ],
        "key_versions": {
            "security_hmac": [{"key_id": "security-hmac:1", "available": key_available}],
            "audit_hmac": [],
            "kek": [{"key_id": "kek:1", "available": True}],
        },
    }


def _anchors(document: dict[str, Any]) -> dict[Anchor, str | None]:
    """The anchors a database identical to ``document`` would resolve."""
    security = document["security_chain"]
    tenant = document["tenants"][0]
    book = tenant["ledger_chains"][0]
    return {
        Anchor("security", "", "", security["last_chain_seq"]): security["last_hmac"],
        Anchor("audit", str(TENANT), "", tenant["head"]["last_chain_seq"]): tenant["head"][
            "last_hmac"
        ],
        Anchor("ledger", str(TENANT), "ASC606", book["last_chain_seq"]): book["last_seal_sha256"],
    }


def test_anchor_requests_name_every_recorded_head() -> None:
    expected = _document()
    assert recovery.anchor_requests(expected) == [
        Anchor("security", "", "", 3),
        Anchor("audit", str(TENANT), "", 12),
        Anchor("ledger", str(TENANT), "ASC606", 2),
    ]
    # Empty chains record no anchor: nothing to find again.
    empty = _document(security_seq=0, head_seq=0, ledger_seq=0)
    assert recovery.anchor_requests(empty) == []


def test_compare_expected_passes_when_the_restore_carries_every_head() -> None:
    expected = _document()
    assert recovery.compare_expected(expected, expected, _anchors(expected)) == []


def test_compare_expected_tolerates_chains_that_grew_after_the_digest() -> None:
    # The digests are written before the dump, so the restored chains may be longer (OPR-11 (4)):
    # the row at each recorded head must still carry the recorded hash.
    expected = _document(security_seq=3, head_seq=12, ledger_seq=2)
    actual = _document(
        security_seq=5,
        security_hmac="e" * 64,
        head_seq=15,
        head_hmac="f" * 64,
        ledger_seq=3,
        ledger_seal="3" * 64,
    )
    assert recovery.compare_expected(expected, actual, _anchors(expected)) == []


def test_compare_expected_reports_shorter_or_rewritten_chains() -> None:
    expected = _document()
    shorter = _document(security_seq=2, head_seq=11, ledger_seq=1)
    findings = recovery.compare_expected(expected, shorter, _anchors(expected))
    assert findings == [
        "security chain: restored head 2 is before the backup-time head 3",
        "acme: restored audit head 11 is before the backup-time head 12",
        "acme: restored ledger chain ASC606 head 1 is before the backup-time head 2",
    ]
    rewritten = {
        Anchor("security", "", "", 3): "0" * 64,
        Anchor("audit", str(TENANT), "", 12): None,  # the event is gone
        Anchor("ledger", str(TENANT), "ASC606", 2): "9" * 64,
    }
    findings = recovery.compare_expected(expected, expected, rewritten)
    assert findings == [
        "security chain: the event at backup-time head 3 does not carry the recorded hmac",
        "acme: the audit event at backup-time head 12 does not carry the recorded hmac",
        "acme: the seal at backup-time head 2 of ASC606 does not carry the recorded seal_sha256",
    ]


def test_compare_expected_reports_missing_tenants_books_files_and_keys() -> None:
    expected = _document()
    key = f"{TENANT}/ATTACHMENT/{'c' * 64}"
    actual = _document(
        files=[{"storage_key": key, "sha256": "d" * 64, "status": recovery.FILE_OK}],
        keys=[{"key_id": f"audit-hmac:{TENANT}:1", "available": False}],
        key_available=False,
    )
    actual["tenants"][0]["ledger_chains"] = []
    findings = recovery.compare_expected(expected, actual, _anchors(expected))
    assert findings == [
        "acme: ledger chain ASC606 is missing after the restore",
        f"acme: file {key} hashes differently after the restore",
        f"acme: audit HMAC key audit-hmac:{TENANT}:1 recorded at backup time is missing or not "
        "served after the restore",
        "security HMAC key security-hmac:1 is not served after the restore",
    ]

    # P6-R2 population: a tenant only on one side is a finding either way.
    gone = _document()
    gone["tenants"][0]["tenant_id"] = str(OTHER)
    assert recovery.compare_expected(expected, gone, _anchors(expected)) == [
        f"acme: tenant {OTHER} is in the restored database but absent from the backup-time "
        "document",
        f"acme: tenant {TENANT} is missing from the restored database",
    ]
    # P6-R5: a KEK recorded at backup time must open every envelope after the restore.
    kek_lost = _document()
    kek_lost["key_versions"]["kek"] = [{"key_id": "kek:1", "available": False}]
    assert recovery.compare_expected(expected, kek_lost, _anchors(expected)) == [
        "kek kek:1 recorded at backup time does not open every envelope after the restore"
    ]
    legacy_expected = _document()
    legacy_expected["key_versions"]["kek"] = ["kek:1", "kek:2"]
    assert recovery.compare_expected(legacy_expected, expected, _anchors(expected)) == [
        "kek kek:2 recorded at backup time does not open every envelope after the restore"
    ]

    missing_file = _document(files=[])
    shredded_file = _document(
        files=[{"storage_key": key, "sha256": "c" * 64, "status": recovery.FILE_SHREDDED}]
    )
    assert recovery.compare_expected(expected, missing_file, _anchors(expected)) == [
        f"acme: file {key} recorded at backup time is missing"
    ]
    assert recovery.compare_expected(expected, shredded_file, _anchors(expected)) == [
        f"acme: file {key} verified at backup time is now shredded"
    ]
    # A file that already failed at backup time is not re-required after the restore.
    failed_before = _document(
        files=[{"storage_key": key, "sha256": "c" * 64, "status": recovery.FILE_MISSING_SIDECAR}]
    )
    assert recovery.compare_expected(failed_before, missing_file, _anchors(expected)) == []
    # P6-R6: an erasure recorded at backup time must survive the restore in every direction.
    shredded_before = _document(
        files=[{"storage_key": key, "sha256": "c" * 64, "status": recovery.FILE_SHREDDED}]
    )
    assert recovery.compare_expected(shredded_before, shredded_file, _anchors(expected)) == []
    assert recovery.compare_expected(shredded_before, expected, _anchors(expected)) == [
        f"acme: file {key} recorded shredded at backup time is readable after the restore"
    ]
    assert recovery.compare_expected(shredded_before, missing_file, _anchors(expected)) == [
        f"acme: file {key} recorded shredded at backup time is missing after the restore (its "
        "erasure record is gone)"
    ]
    incomplete = _document(
        files=[
            {
                "storage_key": key,
                "sha256": "c" * 64,
                "status": recovery.FILE_SHREDDED_SIDECAR_PRESENT,
            }
        ]
    )
    assert recovery.compare_expected(shredded_before, incomplete, _anchors(expected)) == [
        f"acme: file {key} recorded shredded at backup time is now shredded_sidecar_present"
    ]


def test_previous_heads_of_reads_the_recorded_heads() -> None:
    assert recovery.previous_heads_of(_document()) == {
        str(TENANT): {"last_chain_seq": 12, "last_hmac": HMAC_B}
    }
    assert recovery.previous_heads_of({"tenants": [{"tenant_id": str(TENANT), "head": None}]}) == {}


def _row(
    key: str, purpose: FilePurpose, sha256: str, size: int, *, shredded: bool = False
) -> dict[str, Any]:
    return {
        "id": UUID(int=7),
        "tenant_id": TENANT,
        "storage_key": key,
        "purpose": purpose.value,
        "sha256": sha256,
        "size_bytes": size,
        "shredded_at": "2026-09-19T00:00:00Z" if shredded else None,
    }


@pytest.fixture
def store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


def test_check_file_plaintext_purposes_hash_as_stored(
    store: LocalFileStore, keyring: KeyRing
) -> None:
    payload = b'{"digest": true}\n'
    sha256 = hashlib.sha256(payload).hexdigest()
    key = storage_key(TENANT, FilePurpose.AUDIT_DIGEST, sha256)
    store.put(key, io.BytesIO(payload))
    row = _row(key, FilePurpose.AUDIT_DIGEST, sha256, len(payload))
    assert recovery.check_file(row, files=store, keyring=keyring) == (recovery.FILE_OK, None)
    assert recovery.check_file(
        _row(key, FilePurpose.AUDIT_DIGEST, "0" * 64, len(payload)), files=store, keyring=keyring
    ) == (recovery.FILE_SHA256_MISMATCH, None)
    assert recovery.check_file(
        _row(key, FilePurpose.AUDIT_DIGEST, sha256, len(payload) + 1), files=store, keyring=keyring
    ) == (recovery.FILE_SIZE_MISMATCH, None)
    assert recovery.check_file(
        _row(key + "0", FilePurpose.AUDIT_DIGEST, sha256, len(payload)),
        files=store,
        keyring=keyring,
    ) == (recovery.FILE_MISSING_OBJECT, None)


def test_check_file_encrypted_purposes_decrypt_under_their_sidecar(
    store: LocalFileStore, keyring: KeyRing
) -> None:
    plaintext = b"attachment bytes"
    sha256 = hashlib.sha256(plaintext).hexdigest()
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, sha256)
    context = encryption_context(TENANT, key)
    dek, sidecar = keyring.new_file_key(context=context)
    store.put(sidecar_key(key), io.BytesIO(sidecar))
    store.put(key, io.BytesIO(keyring.seal_file(dek, plaintext, context=context)))
    row = _row(key, FilePurpose.ATTACHMENT, sha256, len(plaintext))

    status, kek_id = recovery.check_file(row, files=store, keyring=keyring)
    assert (status, kek_id) == (recovery.FILE_OK, keyring.envelope_key_id(sidecar))

    # The stored bytes are ciphertext: the plaintext hash is what must come back (SPEC-Q-158).
    wrong_hash = _row(key, FilePurpose.ATTACHMENT, "0" * 64, len(plaintext))
    assert (
        recovery.check_file(wrong_hash, files=store, keyring=keyring)[0]
        == recovery.FILE_SHA256_MISMATCH
    )

    # A shredded row passes only while its sidecar is gone (05 PRV-07, OPR-10).
    shredded = _row(key, FilePurpose.ATTACHMENT, sha256, len(plaintext), shredded=True)
    assert recovery.check_file(shredded, files=store, keyring=keyring) == (
        recovery.FILE_SHREDDED_SIDECAR_PRESENT,
        None,
    )
    Path(store._path(sidecar_key(key))).unlink()  # the shred deleted the sidecar
    assert recovery.check_file(shredded, files=store, keyring=keyring) == (
        recovery.FILE_SHREDDED,
        None,
    )
    assert recovery.check_file(row, files=store, keyring=keyring) == (
        recovery.FILE_MISSING_SIDECAR,
        None,
    )

    # A sidecar wrapped under another master key cannot be opened: the restore lacks the right .env.
    other = KeyRing(_ForeignProvider())
    store.put(sidecar_key(key), io.BytesIO(other.new_file_key(context=context)[1]))
    status, kek_id = recovery.check_file(row, files=store, keyring=keyring)
    assert status == recovery.FILE_UNDECRYPTABLE
    assert kek_id == "kek:1"


class _ForeignProvider:
    """A key provider deriving from another master key: what a restore under the wrong .env sees."""

    def __init__(self) -> None:
        from erev_api.adapters.keys.provider import LocalKeyProvider
        from erev_api.adapters.secrets.store import EnvSecretStore
        from erev_api.config import get_settings
        from pydantic import SecretStr

        settings = get_settings().model_copy(update={"encryption_key": SecretStr("f" * 64)})
        self._inner = LocalKeyProvider(EnvSecretStore(settings))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _VersionedStore(LocalFileStore):
    """A store with the P2/P8 lifecycle inventory; ``report`` is what it says about any key."""

    def __init__(self, root: Path, report: Any) -> None:
        super().__init__(root)
        self.report = report

    def sidecar_versions(self, key: str) -> Any:
        if isinstance(self.report, Exception):
            raise self.report
        return self.report


def _shredded_row(root: Path) -> dict[str, Any]:
    key = storage_key(TENANT, FilePurpose.ATTACHMENT, "c" * 64)
    (root / Path(key).parent).mkdir(parents=True, exist_ok=True)
    return {"storage_key": key, "shredded_at": "2026-09-19T10:00:00+00:00"}


def test_r6_residual_erasure_requires_an_explicit_complete_inventory(tmp_path: Path) -> None:
    # An empty inventory is invalid, not "all generations gone": every generation class and the
    # retained-copy/completion state must be present before the verifier says anything.
    row = _shredded_row(tmp_path)
    state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, {}))
    assert state["scope"] == recovery.ERASURE_VERSIONED_INVALID
    assert state["all_generations_gone"] is None
    assert state["versions"]["error"].startswith("incomplete inventory: live count missing")
    for missing in ("live", "noncurrent", "soft_deleted", "retained_copies"):
        partial = {n: 0 for n in recovery.INVENTORY_COUNTS if n != missing}
        partial["completion"] = "complete"
        state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, partial))
        assert state["all_generations_gone"] is None
        assert f"{missing} count missing" in state["versions"]["error"]
    no_completion = {n: 0 for n in recovery.INVENTORY_COUNTS}
    state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, no_completion))
    assert state["all_generations_gone"] is None
    assert "completion state missing" in state["versions"]["error"]
    # Wrong types never count as zero.
    for bad in (None, "0", True, -1, 0.0):
        state = recovery.erasure_state(
            row,
            files=_VersionedStore(
                tmp_path, {**no_completion, "live": bad, "completion": "complete"}
            ),
        )
        assert state["all_generations_gone"] is None, bad
    # A complete inventory answers.
    gone = {**no_completion, "completion": "complete"}
    state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, gone))
    assert state["scope"] == recovery.ERASURE_VERSIONED
    assert state["all_generations_gone"] is True and "error" not in state["versions"]
    for held in (
        {**gone, "noncurrent": 1},
        {**gone, "soft_deleted": 1},
        {**gone, "retained_copies": 1},
        {**gone, "completion": "pending"},
        {**gone, "completion": "retained"},
    ):
        state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, held))
        assert state["all_generations_gone"] is False, held
    # An inventory failure is reported, never masked as absence.
    state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, RuntimeError("boom")))
    assert state["scope"] == recovery.ERASURE_VERSIONED_INVALID
    assert state["all_generations_gone"] is None
    assert "inventory unavailable" in state["versions"]["error"]
    # The local store has no inventory at all: scope says so, and nothing is claimed.
    state = recovery.erasure_state(row, files=LocalFileStore(tmp_path))
    assert state["scope"] == recovery.ERASURE_LOCAL_LIVE and state["versions"] is None
    assert state["all_generations_gone"] is None


def test_r2_residual_compare_expected_reports_omitted_heads_and_untyped_keys() -> None:
    expected = _document()
    actual = _document()
    del expected["tenants"][0]["head"]
    findings = recovery.compare_expected(expected, actual, _anchors(_document()))
    assert findings == ["acme: the backup-time document records no audit head for the tenant"]
    untyped = _document()
    untyped["tenants"][0]["audit_hmac_keys"] = [{}]
    untyped["key_versions"]["security_hmac"] = [{"available": True}]
    untyped["key_versions"]["kek"] = [{}]
    assert recovery.compare_expected(untyped, actual, _anchors(untyped)) == [
        "acme: the backup-time document has an untyped audit key entry",
        "the backup-time document has an untyped security key entry",
        "the backup-time document has an untyped kek entry",
    ]


class _Head:
    def __init__(self, key_id: str) -> None:
        self.key_id = key_id


class _PinnedKeyRing:
    """A key ring with lane P2's ``current_security_key_id`` (the deployment pin)."""

    def __init__(self, pin: str) -> None:
        self.pin = pin

    def current_security_key_id(self) -> str:
        return self.pin


def test_p2_p6_security_key_inventory_uses_the_global_helper_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rows at versions 1 and 3 under pin 5: the required set is {1, 3, 5}, the head is 3.
    calls: list[tuple[Any, Any]] = []

    def helper(bind: Any, keyring: Any, *, tenant_id: Any = None) -> list[str]:
        calls.append((bind, tenant_id))
        return ["security-hmac:1", "security-hmac:3", keyring.current_security_key_id()]

    monkeypatch.setattr(recovery, "required_security_key_ids", helper)
    monkeypatch.setattr(recovery, "chain_head", lambda bind: _Head("security-hmac:3"))
    required, current, head = recovery.security_key_inventory(
        "session", _PinnedKeyRing("security-hmac:5")
    )  # type: ignore[arg-type]
    assert required == ["security-hmac:1", "security-hmac:3", "security-hmac:5"]
    assert current == "security-hmac:5" and head == "security-hmac:3"
    assert calls == [("session", None)]  # the GLOBAL chain, never one tenant
    # A pin the helper did not list (defensive) is still required, as is the head's key.
    monkeypatch.setattr(
        recovery, "required_security_key_ids", lambda b, k, **_: ["security-hmac:1"]
    )
    required, current, head = recovery.security_key_inventory(
        "session", _PinnedKeyRing("security-hmac:5")
    )  # type: ignore[arg-type]
    assert required == ["security-hmac:1", "security-hmac:3", "security-hmac:5"]


class _ProbeKeyRing:
    """Serves every security key except the versions in ``denied`` (a provider denial)."""

    def __init__(self, *denied: str) -> None:
        self.denied = set(denied)
        self.asked: list[str] = []

    def security_event_key(self, key_id: str) -> bytes:
        self.asked.append(key_id)
        if key_id in self.denied:
            raise LookupError(f"{key_id} is not served")
        return b"k" * 32


def test_p2_p6_probe_security_keys_names_missing_historical_and_current_separately() -> None:
    required = ["security-hmac:1", "security-hmac:3", "security-hmac:5"]
    keys, failures = recovery.probe_security_keys(
        required,
        current_key="security-hmac:5",
        head_key="security-hmac:3",
        keyring=_ProbeKeyRing(),  # type: ignore[arg-type]
    )
    assert [k["key_id"] for k in keys] == required and all(k["available"] for k in keys)
    assert [k["key_id"] for k in keys if k["head"]] == ["security-hmac:3"]
    assert [k["key_id"] for k in keys if k["current"]] == ["security-hmac:5"]
    assert failures == []
    # Every id is probed individually; a denial of historical 3 or of current 5 is its own failure.
    ring = _ProbeKeyRing("security-hmac:3")
    keys, failures = recovery.probe_security_keys(
        required,
        current_key="security-hmac:5",
        head_key="security-hmac:3",
        keyring=ring,  # type: ignore[arg-type]
    )
    assert ring.asked == required
    assert [k["available"] for k in keys] == [True, False, True]
    assert failures == [
        "security HMAC key security-hmac:3 required by the security chain or the current pin is "
        "not served by the key provider"
    ]
    _, failures = recovery.probe_security_keys(
        required,
        current_key="security-hmac:5",
        head_key="security-hmac:3",
        keyring=_ProbeKeyRing("security-hmac:5"),  # type: ignore[arg-type]
    )
    assert failures == [
        "security HMAC key security-hmac:5 required by the security chain or the current pin is "
        "not served by the key provider"
    ]
    # A head above the pin is a stale writer and fails closed even when every key is served.
    _, failures = recovery.probe_security_keys(
        ["security-hmac:1", "security-hmac:3"],
        current_key="security-hmac:1",
        head_key="security-hmac:3",
        keyring=_ProbeKeyRing(),  # type: ignore[arg-type]
    )
    assert failures == [
        "the security chain head is signed under security-hmac:3 but the process pin is "
        "security-hmac:1: a stale pin may not append (KEY-03)"
    ]


class _RowAdapter:
    """A synthetic bind: answers P2's DISTINCT hmac_key_id query with rows and the chain-head
    query with one head row; no engine, no connection (Codex's adapter pattern)."""

    def __init__(self, key_ids: list[str | None], head: tuple[str, str | None, int]) -> None:
        self.key_ids = key_ids
        self.head = head
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Any:
        text = str(statement)
        self.statements.append(text)
        adapter = self

        class _Result:
            def scalars(self) -> list[str | None]:
                assert (
                    "DISTINCT" in text
                    and "tenant_id" not in text.split("WHERE")[-1]
                    or "WHERE" not in text
                )
                return list(adapter.key_ids)

            def mappings(self) -> Any:
                hmac, key_id, form = adapter.head

                class _Mappings:
                    def one_or_none(self) -> dict[str, Any]:
                        return {"hmac": hmac, "hmac_key_id": key_id, "canonical_version": form}

                return _Mappings()

        return _Result()


def test_p2_p6_combined_inventory_composes_with_the_real_p2_helper() -> None:
    # Combined-source control: rows at NULL (legacy 1), 3, 1 and a duplicate 3 under pin 5, head 3
    # ⇒ {1, 3, 5}, current 5, head 3; the GLOBAL query carries no tenant predicate.
    bind = _RowAdapter(
        [None, "security-hmac:3", "security-hmac:1", "security-hmac:3"],
        ("f" * 64, "security-hmac:3", 2),
    )
    required, current, head = recovery.security_key_inventory(
        bind, _PinnedKeyRing("security-hmac:5")
    )  # type: ignore[arg-type]
    assert required == ["security-hmac:1", "security-hmac:3", "security-hmac:5"]
    assert current == "security-hmac:5" and head == "security-hmac:3"
    assert any("DISTINCT" in s for s in bind.statements)
    assert not any("tenant_id =" in s for s in bind.statements)
    # Missing historical 3 and missing current 5 fail independently through the probe.
    for denied in ("security-hmac:3", "security-hmac:5"):
        _, failures = recovery.probe_security_keys(
            required,
            current_key=current,
            head_key=head,
            keyring=_ProbeKeyRing(denied),  # type: ignore[arg-type]
        )
        assert failures == [
            f"security HMAC key {denied} required by the security chain or the current pin is "
            "not served by the key provider"
        ]


def test_p2_p6_combined_writer_fence_refuses_a_stale_clone_pin() -> None:
    # Combined-source control: a restored chain headed under security-hmac:3 with the default
    # clone pin 1 is refused by P2's admission before any INSERT, naming both key ids; a matching
    # pin 3 and a forward pin 5 are admissible. The native drill decides the pin from the backup
    # evidence before any mutation (clone_security_pin), so this refusal is never reached there.
    from erev_api.auth import security_events as module
    from erev_api.controls import recovery_preflight as pf

    head = module.ChainHead("f" * 64, "security-hmac:3", 2)
    with pytest.raises(module.StaleSecurityKeyWriter) as info:
        module.assert_writer_admissible(head, writer_key_id="security-hmac:1", writer_form=2)
    assert "security-hmac:1" in str(info.value) and "security-hmac:3" in str(info.value)
    module.assert_writer_admissible(head, writer_key_id="security-hmac:3", writer_form=2)
    module.assert_writer_admissible(head, writer_key_id="security-hmac:5", writer_form=2)
    # The same rule, source-bound, before the destructive phases of the native drill.
    document = {
        "security_chain": {
            "last_chain_seq": 3,
            "last_hmac": "a" * 64,
            "head_key_id": "security-hmac:3",
            "current_key_id": "security-hmac:3",
            "required_key_ids": ["security-hmac:1", "security-hmac:3"],
        }
    }
    assert pf.clone_security_pin(document)["version"] == 3
    with pytest.raises(pf.PreflightError, match="behind the restored chain head security-hmac:3"):
        pf.clone_security_pin(document, override="1")


def test_p2_p6_compare_expected_requires_every_backed_up_security_key() -> None:
    expected = _document()
    expected["security_chain"].update(
        {
            "head_key_id": "security-hmac:3",
            "current_key_id": "security-hmac:5",
            "required_key_ids": ["security-hmac:1", "security-hmac:3", "security-hmac:5"],
        }
    )
    expected["key_versions"]["security_hmac"] = [
        {"key_id": f"security-hmac:{v}", "available": True} for v in (1, 3, 5)
    ]
    served_all = _document()
    served_all["key_versions"]["security_hmac"] = [
        {"key_id": f"security-hmac:{v}", "available": True} for v in (1, 3, 5)
    ]
    assert recovery.compare_expected(expected, served_all, _anchors(expected)) == []
    # Missing historical 3 and missing current 5 are each named, once.
    missing_3 = _document()
    missing_3["key_versions"]["security_hmac"] = [
        {"key_id": "security-hmac:1", "available": True},
        {"key_id": "security-hmac:3", "available": False},
        {"key_id": "security-hmac:5", "available": True},
    ]
    assert recovery.compare_expected(expected, missing_3, _anchors(expected)) == [
        "security HMAC key security-hmac:3 is not served after the restore"
    ]
    missing_5 = _document()
    missing_5["key_versions"]["security_hmac"] = [
        {"key_id": "security-hmac:1", "available": True},
        {"key_id": "security-hmac:3", "available": True},
    ]
    assert recovery.compare_expected(expected, missing_5, _anchors(expected)) == [
        "security HMAC key security-hmac:5 is not served after the restore"
    ]
    # A required id the backup-time key_versions list omitted is still required.
    sparse = _document()
    sparse["security_chain"]["required_key_ids"] = ["security-hmac:1", "security-hmac:3"]
    assert recovery.compare_expected(sparse, missing_5, _anchors(sparse)) == []
    assert recovery.compare_expected(sparse, _document(), _anchors(sparse)) == [
        "security HMAC key security-hmac:3 required by the backed-up chain is not served after "
        "the restore"
    ]


def test_ef8d8d3_residual_contradictory_inventory_is_inconsistent(tmp_path: Path) -> None:
    # A zero, complete inventory while the live sidecar exists is contradictory metadata: never
    # "gone"; the valid empty-genesis control (no sidecar, zero inventory) still answers true.
    row = _shredded_row(tmp_path)
    gone = {**{n: 0 for n in recovery.INVENTORY_COUNTS}, "completion": "complete"}
    key = sidecar_key(str(row["storage_key"]))
    store = _VersionedStore(tmp_path, gone)
    assert recovery.erasure_state(row, files=store)["all_generations_gone"] is True
    Path(store._path(key)).parent.mkdir(parents=True, exist_ok=True)
    Path(store._path(key)).write_bytes(b"still here")
    state = recovery.erasure_state(row, files=store)
    assert state["live_sidecar_present"] is True
    assert state["scope"] == recovery.ERASURE_VERSIONED_INVALID
    assert state["all_generations_gone"] is None
    assert "no live generation but the live sidecar exists" in state["versions"]["error"]
    # The mirror image: a live generation claimed while no sidecar exists.
    Path(store._path(key)).unlink()
    state = recovery.erasure_state(row, files=_VersionedStore(tmp_path, {**gone, "live": 1}))
    assert state["all_generations_gone"] is None
    assert "a live generation but no live sidecar exists" in state["versions"]["error"]


def test_sbx_03_the_verifier_reads_a_copied_row_under_its_sources_key(
    store: LocalFileStore, keyring: KeyRing
) -> None:
    """05 SBX-03 rev 1.196 (item SBX-FILE-READ-1): a sandbox copy's row lies under its source's
    key, sealed with the source's id in the associated data. Told the source, the verifier opens
    it and says ``ok`` (measured before: ``undecryptable`` for every copied file, so
    ``erev verify --all-tenants`` failed for every sandbox that carried one); once the source
    has shredded the file — the marker stands, the copy's row was never stamped — it says
    ``shredded``, as the copy's read answers. Without a source, or with another one, the row
    names a foreign object: ``foreign_storage_key``, a failing status of its own, told apart
    from a key that does not open. A row under its OWN key is read as before."""
    from erev_api.files.store import shred_marker_key

    source = UUID("22222222-2222-4222-8222-222222222222")
    plaintext = b"attachment bytes"
    sha256 = hashlib.sha256(plaintext).hexdigest()
    key = storage_key(source, FilePurpose.ATTACHMENT, sha256)
    context = encryption_context(source, key)
    dek, sidecar = keyring.new_file_key(context=context)
    store.put(sidecar_key(key), io.BytesIO(sidecar))
    store.put(key, io.BytesIO(keyring.seal_file(dek, plaintext, context=context)))
    copied = _row(key, FilePurpose.ATTACHMENT, sha256, len(plaintext))  # the row is TENANT's

    assert recovery.check_file(copied, files=store, keyring=keyring, source_tenant_id=source) == (
        recovery.FILE_OK,
        keyring.envelope_key_id(sidecar),
    )
    for not_the_source in (None, UUID(int=9)):
        assert recovery.check_file(
            copied, files=store, keyring=keyring, source_tenant_id=not_the_source
        ) == (recovery.FILE_FOREIGN_KEY, None)
    assert recovery.FILE_FOREIGN_KEY not in recovery.FILE_GOOD_STATUSES
    from erev_api.controls import recovery_preflight

    assert recovery.FILE_FOREIGN_KEY in recovery_preflight.FILE_STATUSES

    # The source shreds the file: its marker is written and its sidecar goes.
    store.put(shred_marker_key(key), io.BytesIO(b"erev shred marker\n"))
    Path(store._path(sidecar_key(key))).unlink()
    assert recovery.check_file(copied, files=store, keyring=keyring, source_tenant_id=source) == (
        recovery.FILE_SHREDDED,
        None,
    )
    # The same state under a row's OWN key is a finding, as before: the row was never stamped.
    own_row = {**copied, "tenant_id": source}
    assert recovery.check_file(own_row, files=store, keyring=keyring) == (
        recovery.FILE_MISSING_SIDECAR,
        None,
    )
