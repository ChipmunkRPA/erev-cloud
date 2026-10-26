"""Foreign split layers conserve historical sources and both monetary totals."""

from collections import defaultdict
from datetime import date
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from erev_engine.split_fx_layers import OpenLayer, allocate
from erev_engine.stages.s12_fx_entities.rates import RateView


def layer(key, txn, fn, day=1):
    rate = RateView(
        Fraction(fn, txn), str(Fraction(fn, txn)), "spot", f"r-{key}", "v1", "USD", "EUR"
    )
    return OpenLayer(
        key,
        "original-collector",
        f"invoice-{key}",
        date(2026, 1, day),
        f"original-node-{key}",
        rate,
        txn,
        fn,
    )


def test_small_layers_do_not_duplicate_destination_rounding_or_lose_source_age():
    originals = (layer("early", 1, 2), layer("later", 1, 3, 2))
    shares = allocate(originals, {"A": 1, "B": 1}, effective_date=date(2026, 2, 1))
    assert len(shares) == 2
    assert {share.destination for share in shares} == {"A", "B"}
    assert sum(share.fn_carrying for share in shares) == 5
    assert {share.original for share in shares} == set(originals)
    assert {share.original.source_date for share in shares} == {date(2026, 1, 1), date(2026, 1, 2)}
    assert (
        allocate(tuple(reversed(originals)), {"B": 1, "A": 1}, effective_date=date(2026, 2, 1))
        == shares
    )


@settings(max_examples=80)
@given(
    st.lists(st.integers(min_value=1, max_value=10000), min_size=1, max_size=12),
    st.lists(st.integers(min_value=0, max_value=100), min_size=2, max_size=8).filter(any),
)
def test_allocations_reconcile_rows_columns_and_original_quotas(amounts, weights):
    from erev_engine.money import largest_remainder

    total = sum(amounts)
    names = [f"D-{i}" for i in range(len(weights))]
    targets = dict(
        zip(names, largest_remainder(total, [Fraction(w) for w in weights], names), strict=True)
    )
    originals = tuple(layer(f"L-{i}", amount, amount * 3 + 1) for i, amount in enumerate(amounts))
    shares = allocate(originals, targets, effective_date=date(2026, 2, 1))
    by_source = defaultdict(lambda: [0, 0])
    by_destination = defaultdict(int)
    cells = {(share.original.layer_key, share.destination): share.txn_open for share in shares}
    for share in shares:
        by_source[share.original.layer_key][0] += share.txn_open
        by_source[share.original.layer_key][1] += share.fn_carrying
        by_destination[share.destination] += share.txn_open
        assert share.txn_open > 0 and share.fn_carrying >= 0
    for original in originals:
        assert by_source[original.layer_key] == [original.txn_open, original.fn_carrying]
        for destination, target in targets.items():
            exact = Fraction(original.txn_open * target, total)
            actual = cells.get((original.layer_key, destination), 0)
            assert (
                exact.numerator // exact.denominator
                <= actual
                <= -(-exact.numerator // exact.denominator)
            )
    assert {name: by_destination[name] for name in names} == targets


def test_missing_gross_carrying_is_not_invented():
    with pytest.raises(ValueError, match="differ from the original remaining"):
        allocate((layer("net", 100, 90),), {"A": 150}, effective_date=date(2026, 2, 1))
