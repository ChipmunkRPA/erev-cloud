"""05 PRV-07 b refusal rules of ``file.shred`` (BUILD_SPEC SOP-5; 04 table 15.4-B). CPU only: the
predicates decide before any write; the command itself is exercised by
``backend/tests/domain/platform/test_privacy_commands.py`` against a database (NOT RUN until lane
P1's FILES-SHRED-1 chain lands)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from erev_api.domain.platform import file_evidence
from erev_api.domain.platform.privacy import (
    PLAINTEXT_PURPOSE_MESSAGE,
    RULE_PLAINTEXT_PURPOSE,
    RULE_RETENTION_ACTIVE,
    RULE_SHREDDED,
    SHRED_ACTION,
    retention_active,
    shred_refusal,
    shred_supported,
)
from erev_api.enums import FilePurpose
from erev_api.files import policy
from erev_api.privacy.classification import CLASSIFICATION, Retention

TODAY = date(2026, 9, 21)


def row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "purpose": FilePurpose.ATTACHMENT.value,
        "legal_hold": False,
        "retention_until": None,
        "shredded_at": None,
    }
    return {**base, **overrides}


def test_retention_active_reads_hold_and_future_retention() -> None:
    assert not retention_active(row(), TODAY)
    assert retention_active(row(legal_hold=True), TODAY)
    assert retention_active(row(retention_until=TODAY + timedelta(days=1)), TODAY)
    assert not retention_active(row(retention_until=TODAY), TODAY), "ending today is not active"
    assert not retention_active(row(retention_until=TODAY - timedelta(days=1)), TODAY)
    assert retention_active(row(legal_hold=True, retention_until=TODAY - timedelta(days=1)), TODAY)


@pytest.mark.parametrize("purpose", list(FilePurpose))
def test_shred_supported_is_exactly_the_encrypted_purposes(purpose: FilePurpose) -> None:
    assert shred_supported(purpose) is (purpose in policy.ENCRYPTED_PURPOSES)


def test_encrypted_purposes_are_the_five_of_bs1_d_21() -> None:
    assert policy.ENCRYPTED_PURPOSES == {
        FilePurpose.IMPORT_SOURCE,
        FilePurpose.ATTACHMENT,
        FilePurpose.SSP_STUDY,
        FilePurpose.LEGACY_DATABASE,
        FilePurpose.SNAPSHOT_DATASET,
    }


def test_shred_refusal_order_and_rule_ids() -> None:
    assert shred_refusal(row(), TODAY) is None
    shredded = shred_refusal(
        row(shredded_at=datetime(2026, 9, 1), legal_hold=True, purpose="REPORT_OUTPUT"), TODAY
    )
    assert shredded is not None and shredded.slug == "invalid-transition"
    assert [error.rule_id for error in shredded.errors] == [RULE_SHREDDED]
    held = shred_refusal(row(legal_hold=True, purpose="REPORT_OUTPUT"), TODAY)
    assert held is not None and [error.rule_id for error in held.errors] == [RULE_RETENTION_ACTIVE]
    future = shred_refusal(row(retention_until=TODAY + timedelta(days=365)), TODAY)
    assert future is not None and [e.rule_id for e in future.errors] == [RULE_RETENTION_ACTIVE]
    plaintext = shred_refusal(row(purpose=FilePurpose.REPORT_OUTPUT.value), TODAY)
    assert plaintext is not None and plaintext.slug == "invalid-transition"
    assert [error.rule_id for error in plaintext.errors] == [RULE_PLAINTEXT_PURPOSE]
    assert plaintext.errors[0].message == PLAINTEXT_PURPOSE_MESSAGE
    assert RULE_SHREDDED == "FILE_SHREDDED" and RULE_RETENTION_ACTIVE == "FILE_RETENTION_ACTIVE"
    assert RULE_PLAINTEXT_PURPOSE == "PRV-06" and SHRED_ACTION == "file_object.shred"


def test_shred_refusal_by_reference_follows_retention_and_precedes_the_purpose() -> None:
    """Rulings R-30 and R-49 (04 table 15.4-B ``FILE_EVIDENCE_HELD``): a file a standing record
    holds is refused by reference — after the row's own states (already shredded, legal hold or
    retention), before the plaintext-purpose block, and whatever the retention columns say."""
    lock = file_evidence.Hold(file_evidence.EVIDENCE[0], None)
    held = shred_refusal(row(purpose=FilePurpose.SNAPSHOT_DATASET.value), TODAY, held=lock)
    assert held is not None and held.slug == "invalid-transition"
    (error,) = held.errors
    assert (error.field, error.rule_id) == ("status", "FILE_EVIDENCE_HELD")
    assert error.message == (
        "This file is a frozen dataset of a period lock. "
        "It is kept while that record stands and cannot be shredded."
    )
    plaintext = shred_refusal(row(purpose=FilePurpose.JOURNAL_EXPORT.value), TODAY, held=lock)
    assert plaintext is not None and [e.rule_id for e in plaintext.errors] == ["FILE_EVIDENCE_HELD"]
    retained = shred_refusal(row(legal_hold=True), TODAY, held=lock)
    assert retained is not None and [e.rule_id for e in retained.errors] == [RULE_RETENTION_ACTIVE]
    shredded = shred_refusal(row(shredded_at=datetime(2026, 9, 1)), TODAY, held=lock)
    assert shredded is not None and [e.rule_id for e in shredded.errors] == [RULE_SHREDDED]
    pending = next(
        item
        for item in file_evidence.EVIDENCE
        if (item.table, item.column) == ("import_upload", "file_object_id") and item.advice
    )
    assert file_evidence.held_message(file_evidence.Hold(pending, "IMP-000007")) == (
        "This file is the source of import IMP-000007, which is submitted for approval or being "
        "committed. It is kept while that record stands and cannot be shredded. "
        "Have the import rejected, or its approval request withdrawn, first."
    )


def test_shred_columns_match_the_catalogue_file_retention_family() -> None:
    """The four columns the command sets once are catalogued on T-PLT-29 under FILE_RETENTION."""
    for column in ("shredded_at", "shredded_by", "shredded_by_kind", "shred_reason"):
        entry = CLASSIFICATION[("file_object", column)]
        assert entry.retention is Retention.FILE_RETENTION, column


def test_a_hold_an_approval_lifts_names_the_request_and_yields_to_one_without_override() -> None:
    """Rulings R-49 (a) and R-86 (04 table 15.4-B ``FILE_SHRED_APPROVAL_REQUIRED``; PRD IMP-129):
    the source of a committed import, the source file of a signed reconciliation, a migration's
    legacy database, an SSP study, a manual adjustment's attachment and — item EVT-EVIDENCE-1 —
    the evidence of an event submission and of a recorded event are refused by the rule that
    names the approved path; a record that holds the same file without override is the one a
    refusal names."""
    lifted = [item for item in file_evidence.EVIDENCE if item.approval]
    assert [file_evidence.Hold(item, "X-1").record for item in lifted] == [
        "the source of committed import X-1",
        "the source file of reconciliation X-1, which has been signed",
        "the legacy database of migration X-1, whose capture is relied on",
        "the SSP study of SSP book X-1, which has been submitted",
        "the supporting attachment of manual adjustment X-1, which has been submitted",
        "the evidence of approval request X-1, whose events wait for approval or are recorded",
        "the evidence of an event recorded on contract X-1",
    ]
    committed = file_evidence.Hold(lifted[0], "IMP-000007")
    refusal = shred_refusal(row(purpose=FilePurpose.IMPORT_SOURCE.value), TODAY, held=committed)
    assert refusal is not None and refusal.slug == "invalid-transition"
    (error,) = refusal.errors
    assert (error.field, error.rule_id) == ("status", "FILE_SHRED_APPROVAL_REQUIRED")
    assert error.message == (
        "This file is the source of committed import IMP-000007. It is kept while that record "
        "stands; to erase it, request its shredding, which a Controller approves."
    )
    lock = file_evidence.Hold(file_evidence.EVIDENCE[0], None)
    assert file_evidence.first_refusing([committed, lock]) is lock
    assert file_evidence.first_refusing([committed]) is committed
    assert file_evidence.first_refusing([]) is None
