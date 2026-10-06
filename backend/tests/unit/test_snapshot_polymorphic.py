"""Polymorphic subject columns of copied datasets (ruling D-98 candidate 34; T-PLT-30, judgement
records, rule test cases): a PENDING or unsupported subject type refuses the export, a REGENERATED
subject keeps the row with ``subject_id`` nulled, a copied subject is kept as is. No database."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_export as sx

DATA_MODEL = Path(__file__).resolve().parents[3] / "docs/04-DATA_MODEL.md"


def _u(n: int) -> UUID:
    return UUID(int=n)


# --- ruling D-98 candidate 34: polymorphic subjects of judgement_record and rule_test_case --------


def _check_literals(table: str) -> set[str]:
    text = DATA_MODEL.read_text(encoding="utf-8")
    section = re.split(r"\n### T-[A-Z]+-\d+ `" + table + "`", text)[1].split("\n### ", 1)[0]
    match = re.search(r"`subject_type`[^\n]*CHECK \(subject_type IN \(([^)]*)\)", section)
    assert match is not None, table
    return set(re.findall(r"'([a-z_]+)'", match.group(1)))


@pytest.mark.parametrize("table", ["file_attachment", "judgement_record", "rule_test_case"])
def test_polymorphic_subject_literals_equal_the_04_checks(table: str) -> None:
    assert set(sx.POLYMORPHIC_SUBJECTS[table]) == _check_literals(table)
    assert all(literal == target for literal, target in sx.POLYMORPHIC_SUBJECTS[table].items())
    assert sx.ATTACHMENT_SUBJECTS == sx.POLYMORPHIC_SUBJECTS["file_attachment"]


def test_judgement_records_follow_their_subject_class(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copied subject → kept as is; REGENERATED subject → kept with subject_id nulled (REBUILD_STEPS
    says it stays NULL); PENDING or unsupported subject type → refused until the table lands."""
    contract = {"id": _u(1), "subject_type": "contract", "subject_id": _u(101)}
    product = {"id": _u(2), "subject_type": "product", "subject_id": _u(102)}
    kept = sx.filter_polymorphic("judgement_record", [contract, product])
    assert kept == (contract, product)  # copied subjects, kept as is (SBX-03 judgement records)
    # modification landed with CTR-17 (D-98 140); a PENDING entry stands in for product here.
    monkeypatch.setattr(
        sx,
        "PENDING",
        {
            **sx.PENDING,
            "product": sd.PendingTable(
                "product", sd.SnapshotClass.COPIED, sd.Category.FACT, "TEST", "stand-in"
            ),
        },
    )
    with pytest.raises(ValueError, match="product is PENDING"):
        sx.filter_polymorphic("judgement_record", [{**contract, "subject_type": "product"}])
    monkeypatch.undo()
    # migration_batch landed with main 065e7f65 as a COPIED subject: kept as is, like a contract
    batch = {**contract, "subject_type": "migration_batch"}
    assert sx.filter_polymorphic("judgement_record", [batch]) == (batch,)
    with pytest.raises(ValueError, match="unsupported judgement_record subject type"):
        sx.filter_polymorphic("judgement_record", [{**contract, "subject_type": "invoice"}])
    with pytest.raises(TypeError, match="subject_id is a UUID"):
        sx.filter_polymorphic("judgement_record", [{**contract, "subject_id": "x"}])
    with pytest.raises(ValueError, match="no polymorphic subject"):
        sx.filter_polymorphic("customer", [contract])


def test_regenerated_polymorphic_subjects_are_nulled_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recon = {
        "id": _u(3),
        "file_object_id": _u(33),
        "subject_type": "reconciliation",
        "subject_id": _u(301),
    }
    # a REGENERATED subject: attachment excluded (R3)
    assert sx.filter_polymorphic("file_attachment", [recon]) == ()
    # today the 04 checks give judgement records and rule test cases only COPIED or PENDING subjects
    # (the ruling's example exception_item is not a judgement_record literal), so the row-nulling
    # branch is dormant by construction; pinned here, proved below with a widened literal map
    for table in ("judgement_record", "rule_test_case"):
        for target in sx.POLYMORPHIC_SUBJECTS[table].values():
            assert (
                target in sd.PENDING or sd.RULES[target].snapshot_class is sd.SnapshotClass.COPIED
            )
    widened = {
        **sx.POLYMORPHIC_SUBJECTS,
        "judgement_record": {
            **sx.POLYMORPHIC_SUBJECTS["judgement_record"],
            "exception_item": "exception_item",
        },
    }
    monkeypatch.setattr(sx, "POLYMORPHIC_SUBJECTS", widened)
    exception = {"id": _u(4), "subject_type": "exception_item", "subject_id": _u(401)}
    assert sx.filter_polymorphic("judgement_record", [exception]) == (
        {**exception, "subject_id": None},
    )
    assert sd.REBUILD_STEPS[("judgement_record", "subject_id")] is None
    assert sd.REBUILD_STEPS[("rule_test_case", "subject_id")] is None
    assert ("judgement_record", "subject_id") in sd.POLYMORPHIC_SUBJECT_COLUMNS
    versions = [{"id": _u(5), "subject_type": "rule_set_version", "subject_id": _u(501)}]
    assert sx.filter_polymorphic("rule_test_case", versions) == tuple(versions)
    with pytest.raises(ValueError, match="lacks subject_type"):
        sx.filter_polymorphic("rule_test_case", [{"id": _u(6)}])
