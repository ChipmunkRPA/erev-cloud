"""Every foreign key to ``file_object`` is ruled on: the evidence of a standing record, or not
evidence by a stated reason (security finding SC-6; supervisor rulings R-30, R-49 and R-86; 05
PRV-06, PRV-07 b; 04 T-PLT-29).

``file.shred`` refuses by reference through ``erev_api.domain.platform.file_evidence``. The
foreign keys are read from the Alembic chain replayed offline (the DG-ARC-15 replay of
``test_orm_migration_type_agreement``), so a revision that gives a table a new reference to
``file_object`` fails here until the registry names the column or the not-evidence list does.
CPU only — never a database.
"""

from __future__ import annotations

import re

from erev_api.db import tables
from erev_api.domain.platform import file_evidence
from test_orm_migration_type_agreement import replay_chain

_FOREIGN_KEY = re.compile(
    r"ALTER TABLE (?:erev\.)?([a-z_][a-z0-9_]*)\s+ADD CONSTRAINT \S+\s+FOREIGN KEY \(([^)]*)\)\s+"
    r"REFERENCES (?:erev\.)?file_object\b",
    re.S,
)
_INLINE = re.compile(r"REFERENCES (?:erev\.)?file_object\b")


def file_object_foreign_keys() -> set[tuple[str, str]]:
    """(table, column) of every foreign key to ``file_object`` the chain creates."""
    found: set[tuple[str, str]] = set()
    for revision, statement in replay_chain().statements:
        matches = list(_FOREIGN_KEY.finditer(statement))
        # a reference written any other way (inline in CREATE TABLE) must not pass unseen
        assert len(matches) == len(_INLINE.findall(statement)), (revision, statement[:120])
        for match in matches:
            (column,) = [
                name.strip() for name in match.group(2).split(",") if name.strip() != "tenant_id"
            ]
            found.add((match.group(1), column))
    return found


def test_every_file_object_foreign_key_is_evidence_or_listed_as_not() -> None:
    registered = {(item.table, item.column) for item in file_evidence.EVIDENCE}
    listed = set(file_evidence.NOT_EVIDENCE)
    foreign_keys = file_object_foreign_keys()
    assert len(foreign_keys) >= 24, sorted(foreign_keys)
    assert not registered & listed, sorted(registered & listed)
    undecided = foreign_keys - registered - listed
    assert not undecided, (
        f"foreign keys to file_object without a ruling: {sorted(undecided)} — register each in "
        "file_evidence.EVIDENCE or name it in file_evidence.NOT_EVIDENCE with its reason"
    )
    stale = (registered | listed) - foreign_keys
    assert not stale, f"entries that name no foreign key to file_object: {sorted(stale)}"


def test_every_registry_entry_names_real_columns_and_a_record() -> None:
    for item in file_evidence.EVIDENCE:
        table = tables.metadata.tables[f"erev.{item.table}"]
        assert item.column in table.c, (item.table, item.column)
        if item.label is not None:
            assert item.label in table.c, (item.table, item.label)
        assert item.label is None or item.label_of is None, (item.table, item.column)
        labelled = item.label is not None or item.label_of is not None
        assert ("{label}" in item.record) == labelled, item.record
        for expression in (item.standing, item.label_of, item.entities):
            if expression is not None:
                assert str(expression(table)), (item.table, item.column)
        hold = file_evidence.Hold(item, "IMP-000001" if labelled else None)
        message = file_evidence.held_message(hold)
        assert message.startswith("This file is ") and "{" not in message, message
        # an approval lifts a hold; it does not also ask for a withdrawal first
        assert not (item.approval and item.advice), (item.table, item.column)
        rule = file_evidence.held_rule(hold)
        assert rule == (
            file_evidence.RULE_APPROVAL_REQUIRED
            if item.approval
            else file_evidence.RULE_EVIDENCE_HELD
        )
        assert message.endswith(
            "which a Controller approves." if item.approval else (item.advice or "shredded.")
        ), message
    for (table_name, column), reason in file_evidence.NOT_EVIDENCE.items():
        assert column in tables.metadata.tables[f"erev.{table_name}"].c, (table_name, column)
        assert reason.strip(), (table_name, column)


def test_the_ruled_evidence_is_registered() -> None:
    """Rulings R-30 and R-49: lock datasets, the source of a submitted or committed import,
    journal batch files, report outputs of a locked run, approval impact previews and audit
    digests — each by its column, the conditional ones with their condition."""
    by_column = {(item.table, item.column): item for item in file_evidence.EVIDENCE}
    for key in (
        ("lock_snapshot", "file_id"),
        ("journal_batch", "export_file_id"),
        ("journal_batch", "detail_file_id"),
        ("approval_request", "impact_preview_file_id"),
        ("audit_chain_verification", "digest_file_id"),
    ):
        assert by_column[key].standing is None, key
    assert by_column[("report_run", "output_file_id")].standing is not None
    sources = [
        item
        for item in file_evidence.EVIDENCE
        if (item.table, item.column) == ("import_upload", "file_object_id")
    ]
    table = tables.metadata.tables["erev.import_upload"]
    compiled = " ".join(
        str(item.standing(table).compile(compile_kwargs={"literal_binds": True}))
        for item in sources
        if item.standing is not None
    )
    assert len(sources) == 2 and all(item.standing is not None for item in sources)
    for status in ("SUBMITTED", "APPROVED", "COMMITTING", "COMMITTED"):
        assert f"'{status}'" in compiled, status
    for status in ("UPLOADED", "VALIDATED", "DIFF_READY", "REJECTED", "CANCELLED", "FAILED"):
        assert f"'{status}'" not in compiled, status
    assert [item.advice for item in sources] == [file_evidence.WITHDRAW_FIRST, None]
    assert [item.approval for item in sources] == [False, True]  # R-49 (a)


def _compiled(item: file_evidence.EvidenceReference) -> str:
    assert item.standing is not None
    table = tables.metadata.tables[f"erev.{item.table}"]
    return str(item.standing(table).compile(compile_kwargs={"literal_binds": True}))


def test_the_holds_an_approval_lifts_are_the_ruled_ones() -> None:
    """Rulings R-49 (a) and R-86 (b), (c): an approved ``EVIDENCE_SHRED`` request lifts the hold
    of a committed import on its source, of a signed reconciliation and of a migration whose
    capture is relied on on their source files, of a submitted SSP version on its study, of
    a submitted manual adjustment at or above the threshold on its attachment and — item
    EVT-EVIDENCE-1, 04 rev 1.268 — of an event submission that is submitted, approved or applied
    on the evidence attached to its request, and of a contract event on its attachment — and no
    other. Two foreign keys are not evidence: a sandbox manifest, and the record that a
    principal uploaded a file's bytes (T-PLT-49, revision 0103: it names the file and holds
    nothing against a shred); every other attachment stays erasable because no entry's
    condition names it."""
    lifted = [item for item in file_evidence.EVIDENCE if item.approval]
    assert [(item.table, item.column) for item in lifted] == [
        ("import_upload", "file_object_id"),
        ("reconciliation", "source_file_id"),
        ("migration_batch", "source_file_id"),
        ("file_attachment", "file_object_id"),
        ("file_attachment", "file_object_id"),
        ("file_attachment", "file_object_id"),
        ("file_attachment", "file_object_id"),
    ]
    assert all(item.standing is not None for item in lifted)
    assert set(file_evidence.NOT_EVIDENCE) == {
        ("file_upload", "file_object_id"),
        ("tenant_snapshot", "manifest_file_id"),
    }
    committed, reconciliation, migration, study, adjustment, request, event = (
        _compiled(item) for item in lifted
    )
    assert "'COMMITTED'" in committed
    # E-59: every status that carries a sign-off or a certification; DRAFT does not.
    for status in ("PREPARED", "AUTO_CERTIFIED", "REVIEWED", "CERTIFIED", "REOPENED"):
        assert f"'{status}'" in reconciliation, status
    assert "'DRAFT'" not in reconciliation
    # E-76: from the import that takes the capture to the promotion.
    for status in ("IMPORTING", "IMPORTED", "RECONCILED", "SUBMITTED", "PROMOTED"):
        assert f"'{status}'" in migration, status
    for status in ("UPLOADED", "PROFILING", "PROFILED", "FAILED", "CANCELLED"):
        assert f"'{status}'" not in migration, status
    # T-PLT-30: a live SSP_STUDY attachment of a version that has left DRAFT (E-12).
    assert "subject_type = 'ssp_book_version'" in study and "voided_at IS NULL" in study
    assert "purpose = 'SSP_STUDY'" in study
    assert "NOT IN ('DRAFT', 'REJECTED', 'WITHDRAWN')" in study
    # PRD §2.5: a live attachment of a submitted adjustment that needed one — its request carries
    # the flag the command sets from USD 10,000.00 (E-94; T-SL-05 ``approval_request_id``), which
    # ``amount_functional_abs`` says for USD entities only. A VOIDED adjustment counts when it was
    # applied: a discarded DRAFT is VOIDED too.
    assert "subject_type = 'manual_adjustment'" in adjustment
    assert "voided_at IS NULL" in adjustment
    assert "status IN ('SUBMITTED', 'APPROVED', 'POSTED')" in adjustment
    assert "status = 'VOIDED' AND erev.manual_adjustment.applied_event_id IS NOT NULL" in adjustment
    assert "approval_request.id = erev.manual_adjustment.approval_request_id" in adjustment
    assert "'ABOVE_THRESHOLD' = ANY (erev.approval_request.flags)" in adjustment
    assert "amount_functional_abs" not in adjustment
    for status in ("DRAFT", "REJECTED"):
        assert f"'{status}'" not in adjustment, status
    # 04 T-CON-24: a live attachment of the approval request of an event submission — any
    # subject type that stores one — while the submission stands. A rejected, withdrawn or voided
    # submission put nothing in force.
    assert "subject_type = 'approval_request'" in request and "voided_at IS NULL" in request
    assert "subject_type IN ('MANUAL_EVENT', 'STEP1_EVENT', 'ATTRIBUTE_CHANGE')" in request
    assert "status IN ('SUBMITTED', 'APPROVED', 'APPLIED')" in request
    for status in ("DRAFT", "REJECTED", "VOIDED", "WITHDRAWN"):
        assert f"'{status}'" not in request, status
    # T-PLT-30: a live attachment of a contract event, whichever road wrote it.
    assert "subject_type = 'contract_event'" in event and "voided_at IS NULL" in event
    # The entities an approval has to cover: the record's own, or every entity without one.
    assert [item.entities is not None for item in lifted] == [
        True,
        True,
        False,
        True,
        True,
        True,
        True,
    ]
