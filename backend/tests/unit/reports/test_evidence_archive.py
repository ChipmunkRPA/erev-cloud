"""The pack byte/integrity boundary; not a CTL-041 complete-pack claim."""

import hashlib
import io
import json
import stat
import zipfile
from uuid import UUID

import pytest
from erev_api.domain.reports import evidence_archive as packs
from erev_engine.canonical import canonical_bytes

FILES = [
    packs.PackFile("certification.json", b'{"status":"closed"}'),
    packs.PackFile("reports/rpo.csv", b"row_key,amount\ncontract:A,100.00\n", UUID(int=1)),
    packs.PackFile("audit/chain_digest.json", b"{}"),
]


def zipped(
    entries: list[tuple[str, bytes]], *, link: bool = False, compressed: bool = False
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in entries:
            info = zipfile.ZipInfo(path)
            info.create_system = 3
            info.external_attr = ((stat.S_IFLNK if link else stat.S_IFREG) | 0o600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
            archive.writestr(info, content)
    return output.getvalue()


def test_export_is_reproducible_and_every_payload_hash_is_independently_verifiable() -> None:
    result = packs.build(FILES)
    assert packs.build(list(reversed(FILES))) == result
    assert hashlib.sha256(result.manifest_bytes).hexdigest() == result.manifest_sha256
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.read("manifest.json") == result.manifest_bytes
        document = json.loads(archive.read("manifest.json"))
        assert {row["path"] for row in document["files"]} == {file.path for file in FILES}
        for row in document["files"]:
            payload = archive.read(row["path"])
            assert row["bytes"] == len(payload)
            assert row["sha256"] == hashlib.sha256(payload).hexdigest()
        linked = next(row for row in document["files"] if row["path"] == "reports/rpo.csv")
        assert linked["report_run_id"] == str(UUID(int=1))
    assert packs.verify(result.content, expected_manifest_sha256=result.manifest_sha256) == document
    changed = result.manifest_document()
    changed["files"].clear()
    assert result.manifest_document() == document


@pytest.mark.parametrize("change", ["byte", "missing", "extra", "manifest", "wrong-trusted-hash"])
def test_changed_missing_and_unlisted_evidence_is_refused(change: str) -> None:
    result = packs.build(FILES)
    entries = [(file.path, file.content) for file in FILES]
    manifest = result.manifest_bytes
    trusted = result.manifest_sha256
    if change == "byte":
        entries[1] = (entries[1][0], entries[1][1].replace(b"100.00", b"900.00"))
    elif change == "missing":
        entries.pop()
    elif change == "extra":
        entries.append(("unlisted.txt", b"not in manifest"))
    elif change == "manifest":
        manifest = manifest.replace(b"reports/rpo.csv", b"reports/xxx.csv")
    else:
        trusted = "0" * 64
    content = zipped([*entries, ("manifest.json", manifest)])
    with pytest.raises(packs.InvalidArchive):
        packs.verify(content, expected_manifest_sha256=trusted)


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../outside",
        "/absolute",
        "a/../b",
        "a/./b",
        "a//b",
        "a/",
        "a\\b",
        "C:relative",
        "C:/absolute",
        "a\x00b",
        "a\nb",
        "a\x7fb",
        "a./b",
        "a /b",
        "e\u0301.txt",
        "\ud800",
        "a" * 1025,
    ],
)
def test_unsafe_noncanonical_paths_cannot_be_built(path: str) -> None:
    with pytest.raises(packs.InvalidArchive):
        packs.build([packs.PackFile(path, b"x")])


@pytest.mark.parametrize(
    "paths",
    [
        ["same", "same"],
        ["Case", "case"],
        ["manifest.json"],
        ["MANIFEST.JSON"],
        ["folder", "folder/file"],
        ["folder/file", "folder"],
    ],
)
def test_duplicate_reserved_and_file_directory_collisions_are_refused(paths: list[str]) -> None:
    with pytest.raises(packs.InvalidArchive):
        packs.build([packs.PackFile(path, b"x") for path in paths])


@pytest.mark.parametrize("paths", [["x", "x"], ["X", "x"], ["a", "a/b"], ["../x"]])
def test_verifier_checks_archive_paths_before_trusting_manifest(paths: list[str]) -> None:
    entries = [(path, b"x") for path in paths]
    if paths == ["x", "x"]:
        with pytest.warns(UserWarning, match="Duplicate name"):
            content = zipped(entries)
    else:
        content = zipped(entries)
    with pytest.raises(packs.InvalidArchive):
        packs.verify(content, expected_manifest_sha256="0" * 64)


def test_symlinks_and_compressed_payload_over_budget_are_refused() -> None:
    for content in (
        zipped([("link", b"target")], link=True),
        zipped([("large", b"a" * 10000)], compressed=True),
    ):
        with pytest.raises(packs.InvalidArchive):
            packs.verify(content, expected_manifest_sha256="0" * 64, max_payload_bytes=20)
    with pytest.raises(packs.InvalidArchive):
        packs.build(FILES, max_payload_bytes=1)


@pytest.mark.parametrize(
    "mutation", ["boolean-size", "duplicate", "self", "bad-id", "noncanonical"]
)
def test_even_trusted_manifest_must_have_valid_unambiguous_metadata(mutation: str) -> None:
    result = packs.build(FILES)
    document = result.manifest_document()
    if mutation == "boolean-size":
        document["files"][0]["bytes"] = True
    elif mutation == "duplicate":
        document["files"].append(document["files"][0])
    elif mutation == "self":
        document["files"][0]["path"] = "manifest.json"
    elif mutation == "bad-id":
        document["files"][0]["report_run_id"] = "not-a-uuid"
    manifest = canonical_bytes(document)
    if mutation == "noncanonical":
        manifest = json.dumps(document, indent=2).encode()
    content = zipped([*((file.path, file.content) for file in FILES), ("manifest.json", manifest)])
    with pytest.raises(packs.InvalidArchive):
        packs.verify(content, expected_manifest_sha256=hashlib.sha256(manifest).hexdigest())


def test_bad_zip_and_empty_payload_pack() -> None:
    with pytest.raises(packs.InvalidArchive):
        packs.verify(b"not a ZIP", expected_manifest_sha256="0" * 64)
    result = packs.build([])
    assert packs.verify(result.content, expected_manifest_sha256=result.manifest_sha256) == {
        "files": []
    }


@pytest.mark.parametrize("path", ["CON", "aux.json", "LPT1.csv", "a/<bad>", "a/q?", "a/x*"])
def test_paths_survive_portable_extraction(path: str) -> None:
    with pytest.raises(packs.InvalidArchive):
        packs.build([packs.PackFile(path, b"data")])


def test_crc_damage_and_rehashed_forgery_are_refused() -> None:
    original = packs.build(FILES)
    damaged = original.content.replace(b"100.00", b"900.00", 1)
    forged = packs.build(
        [
            packs.PackFile(
                file.path, file.content.replace(b"100.00", b"900.00"), file.report_run_id
            )
            for file in FILES
        ]
    )
    for content in (damaged, forged.content):
        with pytest.raises(packs.InvalidArchive):
            packs.verify(content, expected_manifest_sha256=original.manifest_sha256)


def test_duplicate_json_keys_are_not_a_canonical_manifest() -> None:
    manifest = b'{"files":[],"files":[]}'
    with pytest.raises(packs.InvalidArchive):
        packs.verify(
            zipped([("manifest.json", manifest)]),
            expected_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        )
