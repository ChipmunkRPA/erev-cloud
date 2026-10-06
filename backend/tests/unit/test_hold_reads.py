"""The member ``holds`` of API-S-Contract and API-S-Obligation (item HOLD-RELEASE-READ-1; the
supervisor's order of 2026-10-02; 04 §16.1, §16.2 rev 1.299): its shape as 04 states it, and
``release_refusal`` — what ``release-hold`` would answer for an open hold. No database: the
database witnesses are in ``tests/domain/contracts/test_holds.py``."""

from __future__ import annotations

import re
from pathlib import Path

from erev_api.domain.contracts import holds
from erev_api.enums import ContractStatus
from erev_api.schemas.contracts import ContractOut, HoldOut, ObligationOut

CONTRACT = "0199c1f0-0000-7000-8000-000000000001"


def test_hold_release_read_1_the_member_is_the_one_04_states() -> None:
    """04 §16.2 states the member of API-S-Obligation as a brace list and §16.1 says
    API-S-Contract ``holds`` has the same shape: the model's members ARE that list, in its
    order, and both answers carry the one model."""
    text = (Path(__file__).resolve().parents[3] / "docs" / "04-DATA_MODEL.md").read_text(
        encoding="utf-8"
    )
    (row,) = [
        line for line in text.splitlines() if line.startswith("| `holds` | array | — | `{id,")
    ]
    stated = re.search(r"`\{([a-z_, ]+)\}`", row)
    assert stated is not None, row
    assert stated.group(1).split(", ") == list(HoldOut.model_fields)
    assert ContractOut.model_fields["holds"].annotation == list[HoldOut]
    assert ObligationOut.model_fields["holds"].annotation == list[HoldOut]


def test_hold_release_read_1_the_refusal_is_the_commands_in_its_order() -> None:
    """``release_refusal`` answers what ``release_hold`` would, in the command's own order: a
    voided or terminated contract takes no hold command, whatever the hold; else the hold of a
    judgement record that waits for its review — or, a ``NOT_A_CONTRACT`` record, for its
    assessment — names what releases it; every other open hold is released by hand."""
    manual = {"hold_source": "MANUAL", "contract_id": CONTRACT, "reason": "Invoice dispute."}
    waiting = {
        "hold_source": "SYSTEM",
        "contract_id": CONTRACT,
        "reason": holds.judgement_hold_reason("J-7", "COLLECTIBILITY"),
    }
    step1 = {**waiting, "reason": holds.judgement_hold_reason("J-1", "NOT_A_CONTRACT")}
    submitted = [("J-7", "COLLECTIBILITY", "SUBMITTED"), ("J-1", "NOT_A_CONTRACT", "REVIEWED")]
    by_review = "This hold is released by the review of judgement record J-7."
    by_assessment = (
        "This hold is released when the Step 1 assessment that cites judgement record J-1 is "
        "recorded."
    )

    for status in ContractStatus:
        closed = status in (ContractStatus.VOIDED, ContractStatus.TERMINATED)
        no_command = "A voided or terminated contract takes no hold." if closed else None
        assert holds.release_refusal(status, manual, submitted) == no_command, status
        assert holds.release_refusal(status.value, waiting, submitted) == (
            no_command or by_review
        ), status
        assert holds.release_refusal(status, step1, submitted) == (no_command or by_assessment)

    # a record that is back with its author, or superseded, refuses nothing; a manual hold
    # whose reason reads like a record's is no record's hold
    for record_status in ("DRAFT", "REJECTED", "SUPERSEDED", "VOIDED"):
        records = [("J-7", "COLLECTIBILITY", record_status)]
        assert holds.release_refusal("ACTIVE", waiting, records) is None, record_status
    assert holds.release_refusal("ACTIVE", {**waiting, "hold_source": "MANUAL"}, submitted) is None
    assert holds.release_refusal("ACTIVE", waiting, []) is None
