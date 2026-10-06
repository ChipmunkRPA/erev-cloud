"""DG-ARC-08 for the file-read registry: it is complete and equals its document (04 T-PLT-29
"Read access", T-PLT-30 "Subjects"; 03 REQ-PLT-012, REQ-PLT-035; security review 2026-09-29 S2,
ruling R-48 (c)).

A file is read through a record that owns it. ``file_access.FILE_READ_ACCESS`` names the owners of
every purpose; these tests keep the registry whole as the schema grows — a new file purpose, a new
column that holds a file id or a new attachment subject fails here until someone says who reads it
— and keep the table of 04 T-PLT-29 word for word what the code enforces.
"""

from __future__ import annotations

import re
from typing import get_args

from erev_api.auth.permissions import CATALOGUE
from erev_api.db.tables import file_object
from erev_api.domain.platform import file_access, file_evidence
from erev_api.domain.platform.file_access import (
    ATTACHMENT_SUBJECTS,
    FILE_READ_ACCESS,
    FileOwner,
)
from erev_api.enums import FilePurpose
from erev_api.files import policy
from erev_api.schemas.files import SubjectType
from support.architecture import ROOT

DATA_MODEL = ROOT / "docs" / "04-DATA_MODEL.md"
READ_ACCESS_HEADING = "**Read access (authoritative"
READ_ACCESS_HEADER = "| Purpose | Owner | Read by | Entity |"
SUBJECTS_HEADING = "**Subjects (authoritative"
SUBJECTS_HEADER = "| Subject type | Attach with | Read with | Entity |"
# A column whose name ends like a file reference and is none: a mapping profile is not a file.
NOT_A_FILE = frozenset({"import_upload.mapping_profile_id"})
PERMISSIONS = frozenset(permission.code for permission in CATALOGUE)


def schema_file_columns() -> set[str]:
    """``<table>.<column>`` of every column of the schema that holds a ``file_object`` id."""
    found: set[str] = set()
    for table in file_object.metadata.tables.values():
        if table.name == file_object.name:
            continue
        for column in table.columns:
            if column.name == "file_object_id" or column.name.endswith("file_id"):
                found.add(f"{table.name}.{column.name}")
    return found - NOT_A_FILE


def owners() -> list[FileOwner]:
    return [owner for access in FILE_READ_ACCESS.values() for owner in access.owners]


def test_dg_arc_08_every_file_purpose_names_its_readers() -> None:
    assert set(FILE_READ_ACCESS) == set(FilePurpose)
    # An upload is read back by its uploader: exactly the purposes POST /files accepts.
    assert {purpose for purpose, access in FILE_READ_ACCESS.items() if access.uploader} == set(
        policy.UPLOADABLE_PURPOSES
    )


def test_dg_arc_08_every_column_that_holds_a_file_has_an_owner_rule() -> None:
    columns = schema_file_columns()
    assert len(columns) >= 25
    # Every column that holds a file id is an owner of the registry but one: T-PLT-49 names the
    # uploaders of a file — the table the "uploader" rows read — and owns no file.
    assert columns - file_access.file_owners() == {file_access.UPLOAD_REF}
    # The registry names real columns: a renamed column cannot leave a rule behind.
    for owner in owners():
        assert owner.column in owner.table.c, owner.ref


def test_dg_arc_08_owner_rules_are_well_formed() -> None:
    for owner in owners():
        assert owner.permissions <= PERMISSIONS, owner.ref
        # audit.read opens audit artefacts only: chain digests and control exception lists.
        if "audit.read" in owner.permissions:
            assert owner.ref in {
                "audit_chain_verification.digest_file_id",
                "control_execution.exceptions_file_id",
            }, owner.ref
    # One purpose, one place: no owner is listed under two purposes except the attachment link,
    # which carries both attachable purposes.
    seen: dict[str, set[FilePurpose]] = {}
    for purpose, access in FILE_READ_ACCESS.items():
        for owner in access.owners:
            seen.setdefault(owner.ref, set()).add(purpose)
    assert {ref: purposes for ref, purposes in seen.items() if len(purposes) > 1} == {
        "file_attachment.file_object_id": {FilePurpose.ATTACHMENT, FilePurpose.SSP_STUDY}
    }


def test_dg_arc_08_every_attachment_subject_type_is_registered() -> None:
    """04 T-PLT-30 ``ck_file_attachment__subject_type`` = the API's ``SubjectType`` = the registry
    (ATT-SUBJECTS-1: attachments accept every subject type the documents name)."""
    declared = set(get_args(SubjectType))
    assert set(ATTACHMENT_SUBJECTS) == declared
    text = DATA_MODEL.read_text(encoding="utf-8")
    check = re.search(r"CHECK \(subject_type IN \(([^)]*)\)\)", text)
    assert check is not None
    assert {name.strip("' ") for name in check.group(1).split(",")} == declared
    for name, subject in ATTACHMENT_SUBJECTS.items():
        assert subject.write and subject.write <= PERMISSIONS, name
        if subject.read is None:
            # Read by a rule of its own: only the approval request, by its readers.
            assert (name, subject.visible is not None) == ("approval_request", True)
            continue
        assert subject.read and subject.read <= PERMISSIONS, name
        assert "audit.read" not in subject.read, name


def documented_rows(heading: str, header: str) -> list[tuple[str, str, str, str]]:
    """The rows of the four-column table under ``heading`` in 04, cells stripped of their code
    marks."""
    lines = DATA_MODEL.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(heading))
    top = next(index for index in range(start, start + 6) if lines[index].strip() == header)
    rows: list[tuple[str, str, str, str]] = []
    for line in lines[top + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip().replace("`", "") for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 4, line
        rows.append((cells[0], cells[1], cells[2], cells[3]))
    return rows


def test_dg_arc_08_the_04_read_access_table_equals_the_registry() -> None:
    documented = documented_rows(READ_ACCESS_HEADING, READ_ACCESS_HEADER)
    assert documented == file_access.read_access_rows()


def test_dg_arc_08_the_04_subjects_table_equals_the_registry() -> None:
    documented = documented_rows(SUBJECTS_HEADING, SUBJECTS_HEADER)
    assert documented == file_access.attachment_subject_rows()


def test_dg_krn_file_07_a_destructive_command_asks_every_record_for_its_entities() -> None:
    """04 T-PLT-29 "Shred scope": the scope question of a command that destroys a file reads
    every owner of the registry once, and an owner with a rule of its own says how its records
    are found. A refusal by reference names a record of the evidence registry; every evidence
    reference is an owner, so no refusal names a record the question did not ask about."""
    asked = [owner.ref for owner in file_access.every_owner()]
    assert sorted(asked) == sorted(file_access.file_owners())
    evidence = {f"{reference.table}.{reference.column}" for reference in file_evidence.EVIDENCE}
    assert evidence <= set(asked), evidence - set(asked)
    for owner in owners():
        assert (owner.grant is None) == (owner.referenced is None), owner.ref
