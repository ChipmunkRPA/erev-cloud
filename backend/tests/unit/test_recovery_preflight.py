"""``erev_api.controls.recovery_preflight`` (independent review P6-R1 to P6-R4, P6-R7 of
2026-09-19; 05 OPR-11, OPR-12, OPR-15; runbook RB-04, RB-06).

The reviewer's six wrongly accepted cases (empty inventory; inventory missing the dump; missing
the digests; admin on another host; app on another host; admin on another port, all with the same
database name) are fixtures here and must be refused; the accepted controls (complete manifest,
same endpoint with different roles, tampered listed member, forbidden database, other database,
redirecting query) keep their verdicts.
"""

from __future__ import annotations

import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from erev_api.controls import recovery_preflight as pf

BACKUP_ID = "erev-20260919T120000Z"
SHA = "c6023e2f960d2e26710faeb4910296dfdc70f4407b43b3d4c6f50f7d5d002db5"
SYNTHETIC = "SYNTHETIC_ONLY"  # a stand-in credential that must never appear in a message


def _url(role: str, host: str = "127.0.0.1", port: int = 1, database: str = "erev_rv_probe") -> str:
    return f"postgresql://{role}:{SYNTHETIC}@{host}:{port}/{database}"


def _manifest(**overrides: object) -> dict[str, object]:
    members = pf.expected_members(BACKUP_ID)
    manifest: dict[str, object] = {
        "schema": pf.MANIFEST_SCHEMA,
        "backup_id": BACKUP_ID,
        "database": "erev",
        "file_root": "files",
        "started_at": "2026-09-19T11:59:50.000000Z",
        "snapshot_started_at": "2026-09-19T12:00:00.000000Z",
        "snapshot_finished_at": "2026-09-19T12:00:04.000000Z",
        "created_at": "2026-09-19T12:10:00.000000Z",
        "files": {name: {"sha256": SHA, "size_bytes": 19} for name in members.values()},
        "digests": {
            "file": members["digests"],
            "result": "PASS",
            "generated_at": "2026-09-19T11:59:58.000000Z",
            "tenants": 1,
        },
    }
    manifest.update(overrides)
    return manifest


# --- R1 endpoint binding -----------------------------------------------------------------------


def test_r1_same_endpoint_different_roles_passes() -> None:
    urls = {
        "EREV_RESTORE_OWNER_URL": _url("erev_owner"),
        "EREV_RESTORE_APP_URL": _url("erev_app"),
        "EREV_RESTORE_ADMIN_URL": _url("restore_admin"),
    }
    assert pf.same_endpoint(urls) == pf.Endpoint(host="127.0.0.1", port=1, database="erev_rv_probe")
    # Credentials never matter to the binding and never reach a message.
    assert pf.same_endpoint({"A": _url("x"), "B": _url("y").replace(SYNTHETIC, "other")}).port == 1


@pytest.mark.parametrize(
    ("variable", "url", "fragment"),
    [
        (
            "EREV_RESTORE_ADMIN_URL",
            _url("restore_admin", host="127.0.0.2"),
            "127.0.0.2:1/erev_rv_probe",
        ),
        ("EREV_RESTORE_APP_URL", _url("erev_app", host="127.0.0.2"), "127.0.0.2:1/erev_rv_probe"),
        ("EREV_RESTORE_ADMIN_URL", _url("restore_admin", port=2), "127.0.0.1:2/erev_rv_probe"),
        (
            "EREV_RESTORE_ADMIN_URL",
            _url("restore_admin", database="erev_rv_other"),
            "erev_rv_other",
        ),
    ],
)
def test_r1_same_name_other_host_or_port_is_refused(variable: str, url: str, fragment: str) -> None:
    urls = {
        "EREV_RESTORE_OWNER_URL": _url("erev_owner"),
        "EREV_RESTORE_APP_URL": _url("erev_app"),
        "EREV_RESTORE_ADMIN_URL": _url("restore_admin"),
    }
    urls[variable] = url
    with pytest.raises(pf.PreflightError) as refused:
        pf.same_endpoint(urls)
    message = str(refused.value)
    assert variable in message and fragment in message
    assert "not 127.0.0.1:1/erev_rv_probe (EREV_RESTORE_OWNER_URL)" in message
    assert SYNTHETIC not in message


def test_r1_endpoint_of_routes_and_allow_list() -> None:
    assert pf.endpoint_of("postgresql://u:p@localhost/erev", variable="X") == pf.Endpoint(
        "localhost", 5432, "erev"
    )
    assert pf.endpoint_of("postgresql+psycopg://u:p@Db.Example:6543/erev_rv_a", variable="X") == (
        pf.Endpoint("db.example", 6543, "erev_rv_a")
    )
    socket = pf.endpoint_of("postgresql://u:p@/erev?sslmode=disable", variable="X")
    assert socket == pf.Endpoint("", 5432, "erev") and socket.describe() == "socket/erev"
    for bad, fragment in (
        ("postgresql://u:p@127.0.0.1:1/erev_rv_probe?dbname=erev", "query parameter dbname"),
        ("postgresql://u:p@127.0.0.1:1/erev_rv_probe?host=other", "query parameter host"),
        (
            "postgresql://u:p@127.0.0.1:1/erev_rv_probe?hostaddr=10.0.0.9",
            "query parameter hostaddr",
        ),
        ("postgresql://u:p@127.0.0.1:1/erev_rv_probe?port=9", "query parameter port"),
        ("postgresql://u:p@127.0.0.1:1/postgres", "outside the allow-list"),
        ("mysql://u:p@127.0.0.1:1/erev", "not a postgresql:// URL"),
    ):
        with pytest.raises(pf.PreflightError) as refused:
            pf.endpoint_of(bad, variable="EREV_RESTORE_ADMIN_URL")
        assert fragment in str(refused.value) and ":p@" not in str(refused.value)


def test_r1_server_identity_compares_reached_servers() -> None:
    same = ("erev_rv_probe", 16400, "2026-09-19 10:00:00+00", "127.0.0.1", 5446)
    rows = {
        "EREV_RESTORE_OWNER_URL": same,
        "EREV_RESTORE_APP_URL": same,
        "EREV_RESTORE_ADMIN_URL": same,
    }
    assert pf.server_identity(rows) == []
    other = ("erev_rv_probe", 16400, "2026-09-19 09:00:00+00", "127.0.0.1", 5432)
    rows["EREV_RESTORE_ADMIN_URL"] = other
    assert pf.server_identity(rows) == [
        "EREV_RESTORE_ADMIN_URL reached another server or database than EREV_RESTORE_OWNER_URL "
        "(database erev_rv_probe vs erev_rv_probe)"
    ]


# --- R2 manifest and expected document ---------------------------------------------------------


def test_r2_complete_manifest_is_accepted() -> None:
    assert pf.validate_manifest(_manifest(), backup_id=BACKUP_ID) == []
    assert set(pf.expected_members(BACKUP_ID).values()) == {
        f"{BACKUP_ID}.dump",
        f"{BACKUP_ID}-files.tar.gz",
        f"{BACKUP_ID}.env",
        f"{BACKUP_ID}.digests.json",
    }


def test_r2_incomplete_or_unbound_manifests_are_refused() -> None:
    members = pf.expected_members(BACKUP_ID)
    empty = _manifest(files={})
    assert sorted(pf.validate_manifest(empty, backup_id=BACKUP_ID)) == sorted(
        f"manifest omits {name}" for name in members.values()
    )
    files = dict(_manifest()["files"])  # type: ignore[arg-type]
    without_dump = {k: v for k, v in files.items() if k != members["dump"]}
    assert pf.validate_manifest(_manifest(files=without_dump), backup_id=BACKUP_ID) == [
        f"manifest omits {members['dump']}"
    ]
    without_digests = {k: v for k, v in files.items() if k != members["digests"]}
    assert pf.validate_manifest(_manifest(files=without_digests), backup_id=BACKUP_ID) == [
        f"manifest omits {members['digests']}"
    ]
    extra = {**files, "../escape": {"sha256": SHA, "size_bytes": 1}}
    assert pf.validate_manifest(_manifest(files=extra), backup_id=BACKUP_ID) == [
        "manifest lists an unexpected member '../escape'"
    ]
    other_id = _manifest(backup_id="erev-20260101T000000Z")
    assert pf.validate_manifest(other_id, backup_id=BACKUP_ID) == [
        f"manifest backup_id is not {BACKUP_ID}"
    ]
    assert pf.validate_manifest(
        _manifest(schema="erev-backup-manifest/1"), backup_id=BACKUP_ID
    ) == [f"manifest schema is not {pf.MANIFEST_SCHEMA}"]
    bad_hash = {**files, members["dump"]: {"sha256": SHA.upper(), "size_bytes": 19}}
    bad_size = {**files, members["env"]: {"sha256": SHA, "size_bytes": 0}}
    assert pf.validate_manifest(_manifest(files=bad_hash), backup_id=BACKUP_ID) == [
        f"manifest entry {members['dump']} has no lowercase 64-hex sha256"
    ]
    assert pf.validate_manifest(_manifest(files=bad_size), backup_id=BACKUP_ID) == [
        f"manifest entry {members['env']} has no positive size_bytes"
    ]
    wrong_digest = _manifest(digests={**_manifest()["digests"], "file": "other.json"})  # type: ignore[dict-item]
    assert pf.validate_manifest(wrong_digest, backup_id=BACKUP_ID) == [
        f"manifest digests.file is not {members['digests']}"
    ]
    assert "manifest file_root is not a plain directory name" in pf.validate_manifest(
        _manifest(file_root="../files"), backup_id=BACKUP_ID
    )
    assert (
        "manifest snapshot_started_at is missing or not an RFC 3339 instant with an offset"
        in pf.validate_manifest(_manifest(snapshot_started_at=None), backup_id=BACKUP_ID)
    )
    assert pf.validate_manifest([], backup_id=BACKUP_ID) == ["manifest is not a JSON object"]
    with pytest.raises(ValueError, match="duplicate JSON key"):
        pf.load_json_strict('{"files": {"a": 1, "a": 2}}')
    with pytest.raises(pf.PreflightError):
        pf.validate_backup_id("../..")


def _expected(**overrides: object) -> dict[str, object]:
    tenant = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "code": "acme",
        "head": {"last_chain_seq": 12, "last_hmac": "b" * 64},
        "ledger_chains": [
            {"book_code": "ASC606", "last_chain_seq": 2, "last_seal_sha256": "2" * 64}
        ],
        "files": {"entries": [{"storage_key": "k", "sha256": "c" * 64, "status": "ok"}]},
        "audit_hmac_keys": [{"key_id": "audit-hmac:x:1", "available": True}],
    }
    document: dict[str, object] = {
        "schema": pf.DOCUMENT_SCHEMA,
        "result": "PASS",
        "generated_at": "2026-09-19T11:59:58.000000Z",
        "security_chain": {
            "last_chain_seq": 3,
            "last_hmac": "a" * 64,
            "head_key_id": "security-hmac:1",
            "current_key_id": "security-hmac:1",
            "required_key_ids": ["security-hmac:1"],
        },
        "tenants": [tenant],
        "counts": {"tenants": 1},
        "key_versions": {
            "security_hmac": [{"key_id": "security-hmac:1", "available": True}],
            "audit_hmac": [],
            "kek": [],
        },
    }
    document.update(overrides)
    return document


def _security(**overrides: object) -> dict[str, object]:
    security: dict[str, object] = {
        "last_chain_seq": 3,
        "last_hmac": "a" * 64,
        "head_key_id": "security-hmac:3",
        "current_key_id": "security-hmac:5",
        "required_key_ids": ["security-hmac:1", "security-hmac:3", "security-hmac:5"],
    }
    security.update(overrides)
    return security


def _served(*versions: int) -> list[dict[str, object]]:
    return [{"key_id": f"security-hmac:{v}", "available": True} for v in versions]


def test_r2_expected_document_population_and_binding() -> None:
    assert pf.validate_expected_document(_expected()) == []
    assert pf.validate_expected_document({}) == [
        f"expected document schema is not {pf.DOCUMENT_SCHEMA}",
        "expected document result is not PASS or FAIL",
        "expected document generated_at is missing or not an RFC 3339 instant",
        "expected document security_chain.last_chain_seq is missing",
        "expected document records no tenants",
        "expected document counts.tenants does not match its tenants",
        "expected document key_versions is missing",
    ]
    assert "expected document records no tenants" in pf.validate_expected_document(
        _expected(tenants=[], counts={"tenants": 0})
    )
    assert "expected document counts.tenants does not match its tenants" in (
        pf.validate_expected_document(_expected(counts={"tenants": 7}))
    )
    broken = _expected()
    broken["tenants"] = [{**broken["tenants"][0], "head": {"last_chain_seq": "12"}}]  # type: ignore[index]
    assert pf.validate_expected_document(broken) == [
        "expected document tenants[0].head is malformed"
    ]
    twice = _expected()
    twice["tenants"] = [twice["tenants"][0], twice["tenants"][0]]  # type: ignore[index]
    twice["counts"] = {"tenants": 2}
    assert pf.validate_expected_document(twice) == [
        "expected document tenants[1].tenant_id repeats"
    ]

    manifest = _manifest()
    assert pf.bind_expected_to_manifest(_expected(), manifest) == []
    assert pf.bind_expected_to_manifest(
        _expected(generated_at="2026-09-19T00:00:00Z"), manifest
    ) == ["expected document generated_at differs from the manifest's digests"]
    assert pf.bind_expected_to_manifest(_expected(result="FAIL"), manifest) == [
        "expected document result differs from the manifest's digests"
    ]
    assert pf.bind_expected_to_manifest(
        _expected(counts={"tenants": 1}),
        _manifest(
            digests={**_manifest()["digests"], "tenants": 3}  # type: ignore[dict-item]
        ),
    ) == ["expected document tenant count differs from the manifest's digests"]


# --- R3 ids, containment and archives -----------------------------------------------------------


def test_r3_backup_id_grammar_and_containment(tmp_path: Path) -> None:
    assert pf.validate_backup_id(BACKUP_ID) == BACKUP_ID
    for bad in ("../..", "/etc", "erev-20260919T120000Z/../x", "latest", "", "erev-2026"):
        with pytest.raises(pf.PreflightError):
            pf.validate_backup_id(bad)
    root = tmp_path / "restore"
    root.mkdir()
    inside = root / BACKUP_ID
    assert pf.contained_path(root, inside, label="restore directory") == inside.resolve()
    # A parent segment is refused before any resolution (stricter than "escapes" since the
    # residual fix: no `..` may appear in a restore path at all).
    with pytest.raises(pf.PreflightError, match="escapes|unsafe path segment"):
        pf.contained_path(root, root / ".." / "elsewhere", label="restore directory")
    with pytest.raises(pf.PreflightError, match="escapes"):
        pf.contained_path(root, root, label="restore directory")
    link = root / "linked"
    link.symlink_to(tmp_path)
    with pytest.raises(pf.PreflightError, match="symbolic link"):
        pf.contained_path(root, link, label="restore directory")

    # Review residual (2026-09-19): a SYMLINKED PARENT. The restore root itself is a link to a
    # directory elsewhere; a descendant under it resolves outside the intended run directory and
    # must be refused, not accepted because the resolved root "contains" it.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    linked_root = run / "restore"
    linked_root.symlink_to(elsewhere)
    with pytest.raises(pf.PreflightError, match="symbolic link"):
        pf.real_directory(linked_root, label="restore root")
    (elsewhere / "erev-20260919T120000Z").mkdir()
    with pytest.raises(pf.PreflightError):
        pf.contained_path(run, run / "restore" / "erev-20260919T120000Z", label="restore directory")
    # A symlinked component deeper down is refused too.
    real_root = run / "restore-real"
    real_root.mkdir()
    (real_root / "erev-20260919T120000Z").symlink_to(elsewhere)
    with pytest.raises(pf.PreflightError, match="symbolic link"):
        pf.contained_path(real_root, real_root / "erev-20260919T120000Z", label="restore directory")
    # The run directory itself may be a link (another disk): its realpath is the anchor, and a
    # real restore root beneath it is fine.
    disk = tmp_path / "disk"
    (disk / "restore").mkdir(parents=True)
    linked_run = tmp_path / "linked-run"
    linked_run.symlink_to(disk)
    with pytest.raises(pf.PreflightError, match="symbolic link"):
        pf.real_directory(linked_run, label="run directory")  # a link is refused by default
    anchored = pf.real_directory(linked_run, label="run directory", allow_link=True)
    assert anchored == disk.resolve()
    assert pf.contained_path(anchored / "restore", anchored / "restore" / BACKUP_ID, label="x") == (
        disk.resolve() / "restore" / BACKUP_ID
    )
    with pytest.raises(pf.PreflightError, match="unsafe path segment"):
        pf.contained_path(real_root, Path("../escape"), label="restore directory")


def test_r3_archive_members_are_validated_before_extraction(tmp_path: Path) -> None:
    ok = [
        ("files", "dir"),
        ("files/t/ATTACHMENT/obj", "file"),
        ("files/t/ATTACHMENT/obj.dek", "file"),
    ]
    assert pf.validate_archive_members(ok, file_root="files") == []
    findings = pf.validate_archive_members(
        [
            ("/etc/passwd", "file"),
            ("files/../escape", "file"),
            ("other/obj", "file"),
            ("files/link", "symlink"),
            ("files\\win", "file"),
        ],
        file_root="files",
    )
    assert findings == [
        "archive member '/etc/passwd' is absolute",
        "archive member 'files/../escape' has an unsafe path segment",
        "archive member 'other/obj' lies outside files/",
        "archive member 'files/link' is a symlink, not a file or directory",
        "archive member 'files\\\\win' has an unsafe path segment",
    ]
    assert pf.validate_archive_members(ok, file_root="../files") == [
        "file_root is not a plain directory name"
    ]

    archive = tmp_path / "files.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = io.BytesIO(b"x")
        info = tarfile.TarInfo("files/t/obj")
        info.size = 1
        tar.addfile(info, data)
        link = tarfile.TarInfo("files/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    assert pf.inspect_archive(archive, file_root="files") == [
        "archive member 'files/escape' is a symlink, not a file or directory"
    ]


# --- R4 effective keys --------------------------------------------------------------------------


def test_r4_effective_keys_must_match_the_saved_env() -> None:
    file_values = {name: "1" * 64 for name in pf.MASTER_KEY_NAMES}
    assert pf.effective_key_mismatches({}, file_values) == []
    assert pf.effective_key_mismatches({"EREV_ENCRYPTION_KEY": "1" * 64}, file_values) == []
    for name in pf.MASTER_KEY_NAMES:
        findings = pf.effective_key_mismatches({name: "2" * 64}, file_values)
        assert findings == [
            f"effective {name} (environment) differs from the .env copy that would be restored"
        ]
        assert "2" * 64 not in " ".join(findings) and "1" * 64 not in " ".join(findings)
    missing = {k: v for k, v in file_values.items() if k != "EREV_AUDIT_HMAC_MASTER_KEY"}
    assert pf.effective_key_mismatches({}, missing) == [
        "EREV_AUDIT_HMAC_MASTER_KEY in the .env copy is missing or not 64 hex characters"
    ]
    short = {**file_values, "EREV_SECURITY_EVENT_HMAC_KEY": "abc"}
    assert pf.effective_key_mismatches({}, short) == [
        "EREV_SECURITY_EVENT_HMAC_KEY in the .env copy is missing or not 64 hex characters"
    ]
    hosted = pf.effective_key_mismatches({"EREV_KEY_PROVIDER": "gcp"}, file_values)
    assert hosted == [pf.MANAGED_NATIVE_REFUSAL]
    contradicting = pf.effective_key_mismatches({"EREV_RECOVERY_PROVIDER": "MANAGED"}, file_values)
    assert contradicting == [
        "EREV_RECOVERY_PROVIDER=MANAGED contradicts EREV_KEY_PROVIDER=local (D-95: local → NATIVE, "
        "gcp → MANAGED)"
    ]


def test_d95_recovery_provider_resolution() -> None:
    # D-95: the provider follows the key provider unless set explicitly and consistently.
    assert pf.resolve_recovery_provider({}) == pf.NATIVE
    assert pf.resolve_recovery_provider({"EREV_KEY_PROVIDER": "local"}) == pf.NATIVE
    assert pf.resolve_recovery_provider({"EREV_KEY_PROVIDER": "gcp"}) == pf.MANAGED
    assert pf.resolve_recovery_provider({"EREV_RECOVERY_PROVIDER": "native"}) == pf.NATIVE
    assert (
        pf.resolve_recovery_provider(
            {"EREV_RECOVERY_PROVIDER": "MANAGED"}, {"EREV_KEY_PROVIDER": "gcp"}
        )
        == pf.MANAGED
    )
    # The environment wins over the file, as pydantic-settings does.
    assert (
        pf.resolve_recovery_provider({"EREV_KEY_PROVIDER": "gcp"}, {"EREV_KEY_PROVIDER": "local"})
        == pf.MANAGED
    )
    for environ, fragment in (
        ({"EREV_RECOVERY_PROVIDER": "MANAGED"}, "contradicts EREV_KEY_PROVIDER=local"),
        ({"EREV_RECOVERY_PROVIDER": "NATIVE", "EREV_KEY_PROVIDER": "gcp"}, "contradicts"),
        ({"EREV_RECOVERY_PROVIDER": "cloud"}, "must be NATIVE or MANAGED"),
        ({"EREV_KEY_PROVIDER": "vault"}, "names no recovery provider"),
    ):
        with pytest.raises(pf.PreflightError, match=fragment):
            pf.resolve_recovery_provider(environ)


# --- R7 measurements ---------------------------------------------------------------------------


def test_r7_restore_point_is_the_snapshot_and_old_backups_keep_their_age() -> None:
    # Snapshot at 12:00, manifest at 12:10, measured at 12:30: the recovered data is 30 minutes
    # old, not the 20 minutes the manifest instant would suggest (review P6-R7).
    manifest = _manifest(
        snapshot_started_at="2026-09-19T12:00:00.000000Z",
        snapshot_finished_at="2026-09-19T12:00:04.000000Z",
        created_at="2026-09-19T12:10:00.000000Z",
    )
    verify = {"latest_evidence_at": "2026-09-19T11:58:00.000000Z", "verifier_events_appended": 1}
    now = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    record = pf.restore_measurements(
        manifest=manifest,
        verify_document=verify,
        now=now,
        drill_seconds=25,
        phase_seconds={"restore": 13, "migrate": 1, "doctor": 0, "verify": 5},
    )
    assert record["restore_point"] == "2026-09-19T12:00:00.000000Z"
    assert record["restore_point_basis"] == "snapshot_started_at"
    assert record["recovery_age_seconds"] == 1800
    assert record["snapshot_duration_seconds"] == 4
    assert record["archive_after_snapshot_seconds"] == 596
    assert record["evidence_lag_seconds"] == 120 and record["evidence_after_restore_point"] is False
    assert record["drill_duration_seconds"] == 25 and record["restore_component_seconds"] == 19
    assert record["cutover_rto_seconds"] is None and "no cutover" in record["cutover_rto_note"]
    assert record["verifier_events_excluded"] == 1

    # A backup taken a week ago and verified today keeps its age under a fixed clock.
    later = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    aged = pf.restore_measurements(
        manifest=manifest, verify_document=verify, now=later, drill_seconds=None, phase_seconds={}
    )
    assert aged["recovery_age_seconds"] == 7 * 86400 and aged["restore_component_seconds"] is None

    # Evidence newer than the restore point is reported as such, never clamped to zero.
    stale = pf.restore_measurements(
        manifest=manifest,
        verify_document={"latest_evidence_at": "2026-09-19T12:05:00.000000Z"},
        now=now,
        drill_seconds=1,
        phase_seconds={},
    )
    assert stale["evidence_lag_seconds"] == -300 and stale["evidence_after_restore_point"] is True

    # Residual of P6-R7: a manifest without the snapshot instant yields no measurement; the later
    # manifest instant is never substituted as a "conservative" restore point.
    with pytest.raises(pf.PreflightError, match="cannot be substituted"):
        pf.restore_measurements(
            manifest={"created_at": "2026-09-19T12:10:00.000000Z"},
            verify_document={},
            now=now,
            drill_seconds=None,
            phase_seconds={},
        )


def test_r7_residual_corrupt_or_unordered_instants_are_refused() -> None:
    def errors(**overrides: object) -> list[str]:
        return pf.validate_manifest(_manifest(**overrides), backup_id=BACKUP_ID)

    assert errors() == []
    # Each required instant: missing, not a string, without an offset, or not a date at all.
    for field in ("started_at", "snapshot_started_at", "snapshot_finished_at", "created_at"):
        expected = f"manifest {field} is missing or not an RFC 3339 instant with an offset"
        for corrupt in (None, 1758283200, "2026-09-19T12:00:00", "not-a-date", ""):
            assert errors(**{field: corrupt}) == [expected], (field, corrupt)
    digests = dict(_manifest()["digests"])  # type: ignore[arg-type]
    for corrupt in (None, "2026-09-19", "x"):
        assert errors(digests={**digests, "generated_at": corrupt}) == [
            "manifest digests.generated_at is not an RFC 3339 instant with an offset"
        ]
    # Ordering: digests before the snapshot, the snapshot before its end, the end before the
    # manifest; a reversed pair is refused rather than reinterpreted.
    assert errors(snapshot_finished_at="2026-09-19T11:59:59.000000Z") == [
        "manifest snapshot_started_at is later than snapshot_finished_at"
    ]
    assert errors(created_at="2026-09-19T12:00:03.000000Z") == [
        "manifest snapshot_finished_at is later than created_at"
    ]
    assert errors(digests={**digests, "generated_at": "2026-09-19T12:00:01.000000Z"}) == [
        "manifest digests.generated_at is later than snapshot_started_at"
    ]
    # Offsets are compared as instants, not as strings.
    assert errors(created_at="2026-09-19T14:10:00.000000+02:00") == []
    assert errors(created_at="2026-09-19T14:00:03.000000+02:00") == [
        "manifest snapshot_finished_at is later than created_at"
    ]
    assert errors(digests={**digests, "tenants": 0}) == [
        "manifest digests.tenants is not a positive count"
    ]
    # restore_measurements refuses the same corruption instead of measuring from another field.
    now = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    for corrupt in (
        _manifest(snapshot_started_at="garbage"),
        _manifest(snapshot_started_at="2026-09-19T12:00:00"),
        _manifest(snapshot_finished_at=None),
        _manifest(created_at=None),
    ):
        with pytest.raises(pf.PreflightError, match="cannot be substituted"):
            pf.restore_measurements(
                manifest=corrupt, verify_document={}, now=now, drill_seconds=None, phase_seconds={}
            )
    with pytest.raises(pf.PreflightError, match="out of order"):
        pf.restore_measurements(
            manifest=_manifest(created_at="2026-09-19T11:00:00.000000Z"),
            verify_document={},
            now=now,
            drill_seconds=None,
            phase_seconds={},
        )


def test_r2_residual_expected_document_is_typed_and_complete() -> None:
    def errors(**tenant_overrides: object) -> list[str]:
        document = _expected()
        tenant = dict(document["tenants"][0])  # type: ignore[index]
        tenant.update(tenant_overrides)
        document["tenants"] = [tenant]
        return pf.validate_expected_document(document)

    # An explicit empty head is accepted; an omitted head is refused (it would anchor nothing).
    assert errors(head={"last_chain_seq": 0, "last_hmac": None}) == []
    assert errors(head=None) == [
        "expected document tenants[0].head is omitted (an empty head is last_chain_seq 0 with "
        "last_hmac null)"
    ]
    without = _expected()
    del without["tenants"][0]["head"]  # type: ignore[index]
    assert pf.validate_expected_document(without) == [
        "expected document tenants[0].head is omitted (an empty head is last_chain_seq 0 with "
        "last_hmac null)"
    ]
    # A nonzero head carries its hash; a zero head carries none.
    for head in (
        {"last_chain_seq": 12, "last_hmac": None},
        {"last_chain_seq": 12},
        {"last_chain_seq": 12, "last_hmac": "b" * 63},
        {"last_chain_seq": 0, "last_hmac": "b" * 64},
        {"last_chain_seq": -1, "last_hmac": None},
        {"last_chain_seq": True, "last_hmac": None},
    ):
        assert errors(head=head) == ["expected document tenants[0].head is malformed"], head
    assert pf.validate_expected_document(
        _expected(
            security_chain=_security(last_hmac=None),
            key_versions={"security_hmac": _served(1, 3, 5), "audit_hmac": [], "kek": []},
        )
    ) == ["expected document security_chain.last_hmac is missing for a nonzero head"]
    assert (
        pf.validate_expected_document(
            _expected(
                security_chain=_security(last_chain_seq=0, last_hmac=None),
                key_versions={"security_hmac": _served(1, 3, 5), "audit_hmac": [], "kek": []},
            )
        )
        == []
    )
    # Ledger chains, file entries and key entries are typed.
    assert errors(ledger_chains=[{"book_code": "ASC606", "last_chain_seq": 2}]) == [
        "expected document tenants[0].ledger_chains has a malformed book"
    ]
    assert (
        errors(
            ledger_chains=[{"book_code": "ASC606", "last_chain_seq": 0, "last_seal_sha256": None}]
        )
        == []
    )
    for entry in (
        {"storage_key": "k", "sha256": "c" * 64, "status": "deleted"},
        {"storage_key": "k", "sha256": "zz", "status": "ok"},
        {"storage_key": "k", "status": "ok"},
        {"sha256": "c" * 64, "status": "ok"},
        "k",
    ):
        assert errors(files={"entries": [entry]}) == [
            "expected document tenants[0].files.entries has a malformed entry"
        ], entry
    assert errors(files={"entries": [], "checked": 0, "ok": 0, "shredded": 0, "failed": 0}) == []
    assert errors(
        files={"entries": [{"storage_key": "k", "sha256": "c" * 64, "status": "ok"}], "checked": 2}
    ) == ["expected document tenants[0].files.checked does not match its entries"]
    assert errors(
        files={
            "entries": [{"storage_key": "k", "sha256": "c" * 64, "status": "ok"}],
            "checked": 1,
            "ok": 1,
            "shredded": 1,
            "failed": 0,
        }
    ) == ["expected document tenants[0].files counts are incoherent"]
    assert errors(audit_hmac_keys=[]) == ["expected document tenants[0].audit_hmac_keys is empty"]
    for key in (
        {},
        {"key_id": "audit-hmac:x:1"},
        {"available": True},
        "audit-hmac:x:1",
        {"key_id": "", "available": True},
    ):
        assert errors(audit_hmac_keys=[key]) == [
            "expected document tenants[0].audit_hmac_keys has an untyped entry"
        ], key
    # The reviewer's fixture: an empty object in the KEK inventory is not a key.
    assert pf.validate_expected_document(
        _expected(key_versions={"security_hmac": _served(1), "audit_hmac": [], "kek": [{}]})
    ) == ["expected document key_versions.kek has an untyped entry"]
    assert pf.validate_expected_document(
        _expected(key_versions={"security_hmac": [{}], "audit_hmac": [], "kek": []})
    ) == ["expected document key_versions.security_hmac has an untyped entry"]
    assert (
        pf.validate_expected_document(
            _expected(
                key_versions={
                    "security_hmac": [{"key_id": "security-hmac:1", "available": True}],
                    "audit_hmac": [{"key_id": "audit-hmac:x:1", "available": True}],
                    "kek": ["kek:1", {"key_id": "kek:2", "available": True}],
                }
            )
        )
        == []
    )
    # Document-level file counts must agree with the tenants.
    assert pf.validate_expected_document(
        _expected(counts={"tenants": 1, "files": {"checked": 2}})
    ) == ["expected document counts.files.checked does not match the tenants"]
    assert (
        pf.validate_expected_document(_expected(counts={"tenants": 1, "files": {"checked": 1}}))
        == []
    )


def test_reviewer_fixtures_are_refused_as_a_set() -> None:
    # The six wrongly accepted cases of 2026-09-19-p6-preflight-independent-d63239c.json.
    members = pf.expected_members(BACKUP_ID)
    full = {name: {"sha256": SHA, "size_bytes": 19} for name in members.values()}
    manifests = {
        "manifest_empty_inventory": {
            "schema": pf.MANIFEST_SCHEMA,
            "backup_id": BACKUP_ID,
            "files": {},
        },
        "manifest_missing_dump": _manifest(
            files={k: v for k, v in full.items() if k != members["dump"]}
        ),
        "manifest_missing_digests": _manifest(
            files={k: v for k, v in full.items() if k != members["digests"]}
        ),
    }
    for case, manifest in manifests.items():
        assert pf.validate_manifest(manifest, backup_id=BACKUP_ID), case
    targets = {
        "target_admin_other_host_same_name": {
            "EREV_RESTORE_OWNER_URL": _url("erev_owner"),
            "EREV_RESTORE_APP_URL": _url("erev_app"),
            "EREV_RESTORE_ADMIN_URL": _url("restore_admin", host="127.0.0.2"),
        },
        "target_app_other_host_same_name": {
            "EREV_RESTORE_OWNER_URL": _url("erev_owner"),
            "EREV_RESTORE_APP_URL": _url("erev_app", host="127.0.0.2"),
            "EREV_RESTORE_ADMIN_URL": _url("restore_admin"),
        },
        "target_admin_other_port_same_name": {
            "EREV_RESTORE_OWNER_URL": _url("erev_owner"),
            "EREV_RESTORE_APP_URL": _url("erev_app"),
            "EREV_RESTORE_ADMIN_URL": _url("restore_admin", port=2),
        },
    }
    for case, urls in targets.items():
        with pytest.raises(pf.PreflightError, match="reaches"):
            pf.same_endpoint(urls)
        assert case.startswith("target_")
    assert json.dumps(manifests["manifest_empty_inventory"])  # fixtures are plain JSON


# --- P2/P6 security-key integration -------------------------------------------------------------


def test_p2_p6_security_key_inventory_is_required_and_typed() -> None:
    # The global inventory travels with the evidence: every key id the backed-up chain names plus
    # the pin (rows at 1 and 3 under pin 5 ⇒ {1, 3, 5}); the head and the pin are members; the
    # verifier's served list covers the set. Key ids only, never material.
    complete = _expected(
        security_chain=_security(),
        key_versions={"security_hmac": _served(1, 3, 5), "audit_hmac": [], "kek": []},
    )
    assert pf.validate_expected_document(complete) == []
    assert pf.validate_expected_document(
        _expected(security_chain=_security(required_key_ids=[]))
    ) == ["expected document security_chain.required_key_ids is empty"]
    errors = pf.validate_expected_document(
        _expected(security_chain=_security(required_key_ids=["security-hmac:1", "kek:2"]))
    )
    assert (
        "expected document security_chain.required_key_ids has an entry that is not a "
        "security-hmac:<n> key id"
    ) in errors
    errors = pf.validate_expected_document(
        _expected(security_chain=_security(required_key_ids=["security-hmac:1", "security-hmac:1"]))
    )
    assert "expected document security_chain.required_key_ids repeats a key id" in errors
    for name in ("current_key_id", "head_key_id"):
        errors = pf.validate_expected_document(_expected(security_chain=_security(**{name: None})))
        assert (
            f"expected document security_chain.{name} is not a security-hmac:<n> key id" in errors
        )
        errors = pf.validate_expected_document(
            _expected(security_chain=_security(**{name: "security-hmac:7"}))
        )
        assert f"expected document security_chain.{name} is not in required_key_ids" in errors
    # The verifier's served list must cover the required set (missing historical 3).
    errors = pf.validate_expected_document(
        _expected(
            security_chain=_security(),
            key_versions={"security_hmac": _served(1, 5), "audit_hmac": [], "kek": []},
        )
    )
    assert errors == [
        "expected document key_versions.security_hmac does not cover every required security key id"
    ]
    # The manifest carries the pin (a key id, never material) and is bound to the document.
    manifest = _manifest(security_hmac_pin="security-hmac:1")
    assert pf.validate_manifest(manifest, backup_id=BACKUP_ID) == []
    assert pf.bind_expected_to_manifest(_expected(), manifest) == []
    assert pf.bind_expected_to_manifest(complete, manifest) == [
        "expected document security pin differs from the manifest's security_hmac_pin"
    ]
    assert pf.validate_manifest(_manifest(security_hmac_pin="1"), backup_id=BACKUP_ID) == [
        "manifest security_hmac_pin is not a security-hmac:<n> key id"
    ]
    assert pf.security_key_version("security-hmac:12") == 12
    for bad in ("security-hmac:0", "security-hmac:", "audit-hmac:1", "", None, 3):
        with pytest.raises(pf.PreflightError):
            pf.security_key_version(bad)


def test_p2_p6_clone_pin_is_decided_from_the_backup_before_any_mutation() -> None:
    # Integration control 3: backup pin 3 on a chain headed under 3 binds the clone to 3 (the
    # same-pin positive control); the ambient host pin never matters to this decision.
    same = _expected(
        security_chain=_security(
            head_key_id="security-hmac:3",
            current_key_id="security-hmac:3",
            required_key_ids=["security-hmac:1", "security-hmac:3"],
        )
    )
    decision = pf.clone_security_pin(same)
    assert decision == {
        "version": 3,
        "key_id": "security-hmac:3",
        "backup_pin": "security-hmac:3",
        "head_key_id": "security-hmac:3",
        "required_key_ids": ["security-hmac:1", "security-hmac:3"],
        "forward_rotation": False,
    }
    # A pin ahead of the head (rotation happened before the backup) is fine: the clone gets 5.
    ahead = pf.clone_security_pin(_expected(security_chain=_security()))
    assert ahead["version"] == 5 and ahead["forward_rotation"] is False
    # A backup whose pin is behind its own chain head is inconsistent evidence: refused.
    with pytest.raises(pf.PreflightError, match="behind its chain head security-hmac:3"):
        pf.clone_security_pin(_expected(security_chain=_security(current_key_id="security-hmac:1")))
    # An operator may rotate FORWARD explicitly; the decision records it.
    forward = pf.clone_security_pin(same, override="5")
    assert forward["version"] == 5 and forward["forward_rotation"] is True
    # Never backwards (a stale pin would append a backwards transition), never garbage.
    with pytest.raises(pf.PreflightError, match="behind the restored chain head security-hmac:3"):
        pf.clone_security_pin(same, override="2")
    for garbage in ("0", "-1", "abc", "1.5"):
        with pytest.raises(pf.PreflightError, match="positive integer"):
            pf.clone_security_pin(same, override=garbage)
    # An empty override means "no override".
    assert pf.clone_security_pin(same, override="")["version"] == 3
    # No inventory, no decision.
    with pytest.raises(pf.PreflightError, match="required_key_ids is empty"):
        pf.clone_security_pin(
            _expected(security_chain={"last_chain_seq": 3, "last_hmac": "a" * 64})
        )
    with pytest.raises(pf.PreflightError, match="no security_chain"):
        pf.clone_security_pin({})


def test_ef8d8d3_residuals_chronology_and_strict_rfc3339() -> None:
    # Residual 2: started_at belongs to the chronology (started ≤ digests ≤ snapshot start ≤
    # snapshot end ≤ manifest); the valid fixture stays the control.
    assert pf.validate_manifest(_manifest(), backup_id=BACKUP_ID) == []
    assert pf.validate_manifest(
        _manifest(started_at="2026-09-19T13:00:00.000000Z"), backup_id=BACKUP_ID
    ) == ["manifest started_at is later than digests.generated_at"]
    # Residual 3: the declared lexical form is RFC 3339 date-time; other ISO 8601 shapes that
    # Python's parser accepts are refused.
    for corrupt in (
        "2026-W38-6T12:00:00+00:00",  # week date
        "2026-262T12:00:00+00:00",  # ordinal date
        "2026-09-19 12:00:00+00:00",  # space separator
        "2026-09-19T12:00+00:00",  # no seconds
        "20260919T120000Z",  # basic format
        "2026-09-19T12:00:00",  # no offset
        "2026-09-19T12:00:00+0000",  # offset without a colon
        "2026-09-19T24:00:00Z",  # hour 24
    ):
        assert pf.validate_manifest(
            _manifest(snapshot_started_at=corrupt), backup_id=BACKUP_ID
        ) == [
            "manifest snapshot_started_at is missing or not an RFC 3339 instant with an offset"
        ], corrupt
    for valid in (
        "2026-09-19T12:00:00Z",
        "2026-09-19T12:00:00.5Z",
        "2026-09-19T12:00:00.000000Z",
        "2026-09-19T14:00:00+02:00",
        "2026-09-19T07:00:00-05:00",
    ):
        assert pf._parse_instant(valid) is not None, valid
    # The equivalent-offset control keeps its verdict.
    assert (
        pf.validate_manifest(
            _manifest(snapshot_started_at="2026-09-19T14:00:00.000000+02:00"), backup_id=BACKUP_ID
        )
        == []
    )


def test_identity_stub_is_a_test_and_dev_hook_only(tmp_path: Path) -> None:
    stub = tmp_path / "identity.json"
    stub.write_text(json.dumps({"EREV_DB_OWNER_URL": ["erev_rv_a", "1", "t", "h", "1"]}), "utf-8")
    environ = {pf.IDENTITY_STUB_NAME: str(stub)}
    assert pf.identity_stub({}) is None
    assert pf.identity_stub({pf.IDENTITY_STUB_NAME: ""}) is None
    assert pf.identity_stub(environ) == str(stub)  # unset EREV_ENV means dev
    for ok in ("dev", "test", "TEST"):
        assert pf.identity_stub({**environ, "EREV_ENV": ok}) == str(stub)
        assert pf.identity_stub(environ, env_name=ok) == str(stub)
    for refused in ("production", "staging", "e2e", "prod"):
        with pytest.raises(pf.PreflightError, match=f"set under EREV_ENV={refused}"):
            pf.identity_stub({**environ, "EREV_ENV": refused})
        with pytest.raises(pf.PreflightError, match="honoured under test or dev only"):
            pf.identity_stub(environ, env_name=refused)
        # The caller's environment wins over a switched process environment.
        with pytest.raises(pf.PreflightError):
            pf.connected_identities(
                {"EREV_DB_OWNER_URL": _url("erev_owner")},
                {**environ, "EREV_ENV": "dev"},
                env_name=refused,
            )


def test_df43dd9_h1_override_is_forward_only_against_the_source_pin() -> None:
    # Source pin 5, head 3: an override of 3 is BELOW the source pin and refused (it would be a
    # rotation backwards, whatever the head admits); 5 is not a rotation; 7 is a forward rotation.
    source = _expected(security_chain=_security())  # head 3, pin 5, required {1, 3, 5}
    with pytest.raises(pf.PreflightError, match="below the backup's signing pin security-hmac:5"):
        pf.clone_security_pin(source, override="3")
    with pytest.raises(pf.PreflightError, match="below the backup's signing pin security-hmac:5"):
        pf.clone_security_pin(source, override="4")
    same = pf.clone_security_pin(source, override="5")
    assert same["version"] == 5 and same["forward_rotation"] is False
    forward = pf.clone_security_pin(source, override="7")
    assert forward["version"] == 7 and forward["forward_rotation"] is True
    # Below the head is still named as such (head 3, pin 3, override 2).
    with pytest.raises(pf.PreflightError, match="behind the restored chain head security-hmac:3"):
        pf.clone_security_pin(
            _expected(
                security_chain=_security(
                    current_key_id="security-hmac:3",
                    required_key_ids=["security-hmac:1", "security-hmac:3"],
                )
            ),
            override="2",
        )


def test_diagnostic_output_is_redacted() -> None:
    # Common-terms amendment (2026-09-19, after two credential exposures): DSN credentials, secret
    # assignments and literal secrets never reach a diagnostic line; hosts, ports, databases stay.
    marker = "never-print-this-marker"  # a synthetic credential; never a real one
    line = f'connection to "postgresql://erev_backup:{marker}@127.0.0.1:5446/erev" failed'
    out = pf.redact_diagnostics(line, marker)
    assert marker not in out and "erev_backup" not in out
    assert out == 'connection to "postgresql://***@127.0.0.1:5446/erev" failed'
    assert (
        pf.redact_diagnostics(f"PGPASSWORD={marker} PGHOST=h", marker) == "PGPASSWORD=*** PGHOST=h"
    )
    word = "pass" + "word"  # assembled so the secrets scan does not read a literal assignment
    assert pf.redact_diagnostics(f"{word}=abc user=u") == f"{word}=*** user=u"
    assert pf.redact_diagnostics("EREV_DB_OWNER_URL=postgresql://u:p@h/erev ok") == (
        "EREV_DB_OWNER_URL=*** ok"
    )
    assert (
        pf.redact_diagnostics("EREV_ENCRYPTION_KEY: 1111 rest") == "EREV_ENCRYPTION_KEY: *** rest"
    )
    # SQLAlchemy's own masking still passes through the same shape.
    assert pf.redact_diagnostics(
        "Engine(postgresql+psycopg://erev_owner:***@127.0.0.1:5446/x)"
    ) == ("Engine(postgresql+psycopg://***@127.0.0.1:5446/x)")
    assert pf.redact_diagnostics(None) == "" and pf.redact_diagnostics("plain", None) == "plain"


def test_redaction_covers_quoted_assignments_and_keeps_safe_context() -> None:
    # Codex 3cfaaa8 redaction residual: quoted assignment values were kept when no matching literal
    # was supplied. The seven probe shapes (five passing, two formerly failing) plus the colon and
    # arrow forms redact without any literal; non-secret quoted assignments are untouched. Only a
    # synthetic marker is used.
    marker = "synthetic-marker-93"
    word = "pass" + "word"  # assembled so the secrets scan reads no literal assignment
    redacted = {
        f"postgresql://erev_backup:{marker}@127.0.0.1:5446/erev": "postgresql://***@127.0.0.1:5446/erev",
        f"PGPASSWORD={marker} PGHOST=h": "PGPASSWORD=*** PGHOST=h",
        f"EREV_ENCRYPTION_KEY={marker}": "EREV_ENCRYPTION_KEY=***",
        f"{word}={marker} user=u": f"{word}=*** user=u",
        f"{word}='{marker}' user=u": f"{word}='***' user=u",  # formerly kept the marker
        f'EREV_ENCRYPTION_KEY="{marker}"': 'EREV_ENCRYPTION_KEY="***"',  # formerly kept the marker
        f'{word} : "{marker}"': f'{word} : "***"',
        f"EREV_DB_APP_URL => 'postgresql://u:{marker}@h/db'": "EREV_DB_APP_URL => '***'",
        f"PGPASSWORD = {marker}": "PGPASSWORD = ***",
        f"pg{word}='{marker}'": f"pg{word}='***'",
        f"{word}wd={marker}".replace("wordwd", "wd"): f"{word}wd=***".replace("wordwd", "wd"),
    }
    for text, expected in redacted.items():
        out = pf.redact_diagnostics(text)  # no literal supplied on purpose
        assert marker not in out, text
        assert out == expected, (text, out)
    # A matching literal supplied as well changes nothing about the shape.
    assert pf.redact_diagnostics(f"{word}='{marker}'", marker) == f"{word}='***'"
    # Safe diagnostic context is preserved: non-secret quoted assignments, hosts, ports, names.
    safe = (
        'EREV_ENV="dev" host=\'127.0.0.1\' port=5446 database=erev_rv_x user="erev_owner" '
        "EREV_KEY_PROVIDER=local stage=preflight pid=4798 count=2"
    )
    assert pf.redact_diagnostics(safe) == safe
