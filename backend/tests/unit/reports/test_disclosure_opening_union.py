"""Whole original groups can be joined; historic amounts cannot be split."""

import copy
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from erev_api.domain.contracts.disclosure_openings import complete_openings
from erev_api.problems import Problem
from erev_engine.stages.s15_disclosures.frozen_opening import _has_source


def snapshot(version, names, amount):
    return (
        {
            "version": version,
            "output_sha256": version * 64,
            "views": [
                {
                    "view": view,
                    "currency": currency,
                    "minor_unit": 2,
                    "lines": {"CONTRACT_LIABILITY": {"CLOSING": amount}},
                    "obligation_closing": {
                        "status": "AVAILABLE",
                        "obligations": {name + "/P": {"liability": amount} for name in names},
                    },
                }
                for view, currency in [("TRANSACTION", "GBP"), ("FUNCTIONAL", "USD")]
            ],
        },
        {"lock_id": "lock", "source_binding_sha256": "b" * 64},
    )


def assemble(snapshots, names=None):
    return complete_openings(
        snapshots,
        names or {"A", "B"},
        {name: NS(values={"contract_liability": Decimal("40")}) for name in ("A", "B")},
        book_code="ASC606",
        entity="UK",
        period_key="2026-10",
        opening_date=date(2026, 9, 30),
    )


def test_union_preserves_original_sources_and_unallocated_eligibility():
    originals = [snapshot("a", ["A"], 4000), snapshot("c", ["B"], 4000)]
    result = assemble(originals)
    assert len(result) == 2
    for row in result:
        assert row.balances == {"CONTRACT_LIABILITY": 8000}
        assert row.obligations == {"A/P": 4000, "B/P": 4000}
        assert "output_sha256" not in row.source
        assert {x["version"] for x in json.loads(row.source["sources_json"])} == {"a", "c"}
        assert _has_source(row.source)
        assert not _has_source({**row.source, "sources_json": "[]"})
    assert result == assemble(list(reversed(originals)))


@pytest.mark.parametrize(
    "originals",
    [
        [snapshot("a", ["A"], 4000)],
        [snapshot("a", ["A", "B"], 8000), snapshot("c", ["B"], 4000)],
        [snapshot("a", ["A", "C"], 4000), snapshot("c", ["B"], 4000)],
    ],
)
def test_missing_overlapping_or_split_groups_do_not_invent_openings(originals):
    assert assemble(originals) == []


def test_union_rejects_currency_mismatch_and_checks_each_original_lock_total():
    originals = [snapshot("a", ["A"], 4000), snapshot("c", ["B"], 4000)]
    changed = copy.deepcopy(originals)
    changed[1][0]["views"][1]["currency"] = "EUR"
    assert [row.view for row in assemble(changed)] == ["TRANSACTION"]
    originals[0][0]["views"][0]["lines"]["CONTRACT_LIABILITY"]["CLOSING"] += 1
    originals[1][0]["views"][0]["lines"]["CONTRACT_LIABILITY"]["CLOSING"] -= 1
    with pytest.raises(Problem, match="validation-failed"):
        assemble(originals)


def test_unchanged_group_retains_single_original_proof():
    result = assemble([snapshot("a", ["A", "B"], 8000)])
    assert result[0].source == {
        "lock_id": "lock",
        "version": "a",
        "output_sha256": "a" * 64,
        "source_binding_sha256": "b" * 64,
    }


def test_new_member_zero_requires_explicit_proof_and_preserves_old_balance():
    original = snapshot("a", ["A"], 4000)
    rows = complete_openings(
        [original],
        {"A", "B"},
        {"A": NS(values={"contract_liability": Decimal("40")})},
        book_code="ASC606",
        entity="UK",
        period_key="2026-10",
        opening_date=date(2026, 9, 30),
        zero_names={"B"},
    )
    assert len(rows) == 2
    assert rows[0].balances == {"CONTRACT_LIABILITY": 4000}
    assert rows[0].obligations == {"A/P": 4000}
    assert json.loads(rows[0].source["zero_opening_contracts_json"]) == ["B"]
    assert assemble([original]) == []


def test_original_contract_keys_are_compared_using_canonical_encoding():
    from erev_engine.stages.s01_canonicalize import obligation_subject_key

    original = snapshot("a", ["unused"], 4000)
    name = "A/B%customer"
    for view in original[0]["views"]:
        view["obligation_closing"]["obligations"] = {
            obligation_subject_key(name, "P"): {"liability": 4000}
        }
    rows = complete_openings(
        [original],
        {name},
        {name: NS(values={"contract_liability": Decimal("40")})},
        book_code="ASC606",
        entity="UK",
        period_key="2026-10",
        opening_date=date(2026, 9, 30),
    )
    assert len(rows) == 2


def test_zero_inception_proof_refuses_old_or_backdated_or_missing_bookings():
    from erev_engine.stages.s15_disclosures.new_contract_opening import zero_contracts

    contract = NS(external_id="B", inception_date=date(2026, 10, 1))
    booking = NS(contract_key="B", event_type="CONTRACT_BOOKED", effective_date=date(2026, 10, 1))
    before = date(2026, 9, 30)
    assert zero_contracts([contract], [booking], before) == {"B"}
    assert zero_contracts([contract], [], before) == set()
    assert zero_contracts([contract], [booking, booking], before) == set()
    backdated = NS(contract_key="B", event_type="BILLING_RECORDED", effective_date=before)
    assert zero_contracts([contract], [booking, backdated], before) == set()
    acquired = NS(
        contract_key="B", event_type="OPENING_BALANCE_ESTABLISHED", effective_date=date(2026, 10, 1)
    )
    assert zero_contracts([contract], [booking, acquired], before) == set()
    contract.inception_date = before
    assert zero_contracts([contract], [booking], before) == set()
