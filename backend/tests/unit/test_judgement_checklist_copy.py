"""The copy of the activation checklist's line for a rejected judgement record (item
JDG-REJECTED-EXIT-1; the supervisor's rulings of 2026-10-02; 04 table 15.4-I
``JUDGEMENT_RECORD_REJECTED``). No database: the database witnesses are in
``tests/domain/policies/test_judgements.py``."""

from __future__ import annotations

from pathlib import Path

from erev_api.domain.contracts import activation
from erev_api.domain.policies import judgements


def test_jdg_rejected_exit_1_the_checklist_copy_is_the_prd_row_imp_145() -> None:
    """The line ``JUDGEMENT_RECORDS`` shows for a rejected record IS PRD §5.5 IMP-145, under the
    code of 04 table 15.4-I (a placeholder ``<two words>`` is the template field
    ``{two_words}``); IMP-104 keeps its copy for a record that waits."""
    prd = (Path(__file__).resolve().parents[3] / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (row,) = [line for line in prd.splitlines() if line.startswith("| IMP-145 |")]
    cells = [cell.strip() for cell in row.strip().strip("|").split(" | ")]
    assert cells[:3] == ["IMP-145", "`JUDGEMENT_RECORD_REJECTED`", "ERROR"]
    assert cells[3].strip('"') == activation.JUDGEMENT_REJECTED_MESSAGE.format(
        judgement_no="<judgement no>", topic="<topic>"
    )
    # IMP-104's row names the same value "<topic label>"; its copy is the template's all the same.
    (waiting,) = [line for line in prd.splitlines() if line.startswith("| IMP-104 |")]
    assert activation.JUDGEMENT_MESSAGE.format(topic="<topic label>") in waiting


def test_jdg_rejected_exit_1_the_second_preparers_refusal_has_its_road_where_there_is_one() -> None:
    """The 403 of a second preparer's edit gains "and discard this one" only for a record the
    discard takes: a draft or a rejected record that is not the proposal of a combination
    group. Who may act is answered before the record's state, so the sentence follows the
    state: a record in review or reviewed keeps the sentence without that half."""
    row = {"status": "DRAFT", "topic": "CONTRACT_TERM", "subject_type": "contract"}
    assert judgements._discard_refusal(row) is None
    assert judgements._discard_refusal({**row, "status": "REJECTED"}) is None
    for status in ("SUBMITTED", "REVIEWED", "SUPERSEDED", "VOIDED"):
        assert judgements._discard_refusal({**row, "status": status}) == (
            "Only a draft or rejected judgement record can be discarded."
        )
    proposal = {"status": "DRAFT", "topic": "COMBINATION", "subject_type": "combination_group"}
    assert judgements._discard_refusal(proposal) == (
        "This record is the proposal of a combination group. It is decided with its group."
    )
    assert judgements._discard_refusal({**proposal, "status": "REJECTED"}) == (
        "This record is the proposal of a combination group. It is decided with its group."
    )
    assert judgements.NOT_THE_CREATOR_DISCARD == (
        judgements.NOT_THE_CREATOR.removesuffix(".") + " and discard this one."
    )
