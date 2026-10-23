"""Default entry uses the resolved obligation policy independently in each book."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from support.bundles import book, minimal_contract

from erev_api.domain.contracts import material_right_defaults as defaults
from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.stages.s01_canonicalize import obligation_subject_key


@pytest.mark.parametrize("second", ["ENTERED_AMOUNT", "RENEWAL_ALTERNATIVE"])
def test_book_defaults_resolve_product_scope_and_refuse_ambiguous_choice(monkeypatch, second):
    def with_method(code, method):
        base = book(code)
        pin = ResolvedPolicyInput(
            "material_right.ssp_method",
            "OBLIGATION",
            obligation_subject_key("K-01", "O1"),
            method,
            "P",
            "PRODUCT-ORIGINAL",
            "K",
        )
        return replace(
            base,
            policies=tuple(
                sorted((*base.policies, pin), key=lambda p: (p.code, p.scope, p.subject_key))
            ),
        )

    bundle = replace(
        minimal_contract(),
        books=(with_method("ASC606", "ENTERED_AMOUNT"), with_method("IFRS15", second)),
    )
    monkeypatch.setattr(
        defaults.obligations,
        "obligation_row",
        lambda *a: {
            "obligation_key": "O1",
            "contract": {"external_id": "K-01", "combination_group_id": uuid4()},
        },
    )
    monkeypatch.setattr(defaults.bundles, "build", lambda *a: bundle)
    answer = defaults.read(None, uuid4(), known_at=datetime(2026, 10, 23, tzinfo=UTC))
    assert answer.method == ("ENTERED_AMOUNT" if second == "ENTERED_AMOUNT" else None)
    assert [b.method for b in answer.books] == ["ENTERED_AMOUNT", second]
    assert all(b.level == "P" and b.source == "PRODUCT-ORIGINAL" for b in answer.books)
