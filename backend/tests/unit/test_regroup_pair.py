"""Submitted and applied transfer pairs must carry matching book-specific evidence."""

from copy import deepcopy
from datetime import date

import pytest

from erev_api.domain.contracts.regroup_pair import require_consistent
from erev_api.problems import Problem


def pair():
    rows = []
    evidence = {
        "ASC606": {
            "effective_date": "2026-09-16",
            "obligations": {
                "O1": {
                    "allocation_minor": 10000,
                    "recognized_minor": 2500,
                    "remaining_minor": 7500,
                    "remaining_quantity": "0.75",
                    "service_start_date": "2026-01-01",
                    "service_end_date": "2026-12-31",
                }
            },
        }
    }
    for kind, action, sign, contract in (
        ("REMOVE_OBLIGATION", "REMOVE", "-", "source"),
        ("ADD_OBLIGATION", "ADD", "", "target"),
    ):
        line = {
            "obligation_key": "O1",
            "action": action,
            "quantity_delta": sign + "0.75",
            "consideration_delta": {"amount": sign + "75", "currency": "USD"},
            "start_date": "2026-09-16",
            "end_date": "2026-12-31",
            "product_code": "P1",
        }
        rows.append(
            {
                "regroup_id": "pair-1",
                "kind": kind,
                "contract_id": contract,
                "effective_date": date(2026, 9, 16),
                "currency": "USD",
                "lines": [line],
                "questionnaire": {
                    "regroup_book_lines": {"ASC606": [deepcopy(line)]},
                    "regroup_source_basis": deepcopy(evidence),
                },
            }
        )
    return rows


def test_complete_pair_is_read_only_and_order_independent():
    rows = pair()
    original = deepcopy(rows)
    require_consistent(rows, primary_book="ASC606")
    require_consistent(rows[::-1], primary_book="ASC606")
    assert rows == original


@pytest.mark.parametrize(
    "change",
    [
        "missing_side",
        "same_contract",
        "date",
        "book",
        "amount",
        "quantity",
        "term",
        "primary_line",
        "source_basis",
        "both_sides",
    ],
)
def test_inconsistent_pair_is_refused_before_application(change):
    rows = pair()
    target = rows[1]
    line = target["questionnaire"]["regroup_book_lines"]["ASC606"][0]
    if change == "missing_side":
        rows.pop()
    elif change == "same_contract":
        target["contract_id"] = rows[0]["contract_id"]
    elif change == "date":
        target["effective_date"] = date(2026, 9, 17)
    elif change == "book":
        target["questionnaire"]["regroup_book_lines"] = {}
    elif change == "amount":
        line["consideration_delta"]["amount"] = "74"
    elif change == "quantity":
        line["quantity_delta"] = "1"
    elif change == "term":
        line["end_date"] = "2027-12-31"
    elif change == "primary_line":
        target["lines"][0]["consideration_delta"]["amount"] = "76"
    elif change == "source_basis":
        target["questionnaire"]["regroup_source_basis"]["ASC606"]["obligations"]["O1"][
            "remaining_minor"
        ] = 7400
    else:
        for row in rows:
            amount = "-74" if row["kind"] == "REMOVE_OBLIGATION" else "74"
            row["lines"][0]["consideration_delta"]["amount"] = amount
            row["questionnaire"]["regroup_book_lines"]["ASC606"][0]["consideration_delta"][
                "amount"
            ] = amount
    with pytest.raises(Problem, match="invalid-transition"):
        require_consistent(rows, primary_book="ASC606")


def test_ordinary_and_legacy_pairs_keep_their_existing_workflows():
    require_consistent([{"regroup_id": None}], primary_book="ASC606")
    rows = pair()
    for row in rows:
        row["questionnaire"] = {}
    require_consistent(rows, primary_book="ASC606")


def test_classification_edits_preserve_server_transfer_evidence():
    from erev_api.domain.contracts.regroup_pair import preserve_evidence

    row = pair()[0]
    row["questionnaire"]["regroup_target_input_sha256"] = "a" * 64
    values = {"questionnaire": {"O1": {"remaining_distinct": True}}}
    preserve_evidence(row, values)
    assert values["questionnaire"]["O1"] == {"remaining_distinct": True}
    assert (
        values["questionnaire"]["regroup_source_basis"]
        == row["questionnaire"]["regroup_source_basis"]
    )
    assert values["questionnaire"]["regroup_target_input_sha256"] == "a" * 64
    with pytest.raises(Problem, match="server-managed"):
        preserve_evidence(row, {"questionnaire": {"regroup_source_basis": {}}})


def test_pair_requires_matching_target_input_digest():
    rows = pair()
    rows[0]["questionnaire"]["regroup_target_input_sha256"] = "a" * 64
    with pytest.raises(Problem):
        require_consistent(rows, primary_book="ASC606")
    rows[1]["questionnaire"]["regroup_target_input_sha256"] = "a" * 64
    require_consistent(rows, primary_book="ASC606")
