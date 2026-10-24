"""Effective reassessment needs the state before one original boundary, not a day end."""

from dataclasses import replace
from datetime import date
from decimal import localcontext

import pytest
from support import golden_streams

from erev_engine import ENGINE_VERSION, fold_book, money
from erev_engine.stages import s01_canonicalize, s13_books
from erev_engine.trace import TraceBuilder


def fold(bundle, **kwargs):
    with localcontext(money.DECIMAL_CONTEXT):
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        cb = s01_canonicalize.run(bundle, trace)
        ctx = s13_books.book_context(cb, next(b for b in bundle.books if b.book_code == "ASC606"))
        return fold_book(ctx, cb, trace, **kwargs)


def test_original_same_day_boundary_order_preserves_prior_allocation():
    original = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    first, second = [e for e in original.events if e.event_type == "CONTRACT_AMENDED"]
    # Two separately accepted changes on the same day still have distinct record positions.
    moved = replace(
        original,
        events=tuple(
            replace(e, effective_date=first.effective_date) if e == second else e
            for e in original.events
        ),
        contracts=tuple(
            replace(
                c,
                modifications=tuple(
                    replace(m, effective_date=first.effective_date)
                    if m.effective_date == second.effective_date
                    else m
                    for m in c.modifications
                ),
            )
            for c in original.contracts
        ),
    )
    before_first = fold(moved, before_boundary_event=first.event_key)
    before_second = fold(moved, before_boundary_event=second.event_key)
    before_day = fold(moved, boundary_cutoff=date(2023, 5, 14))
    after_day = fold(moved, boundary_cutoff=first.effective_date)
    assert before_first.obligations == before_day.obligations
    assert before_first.obligations[0].quantity == 8
    assert before_second.obligations[0].quantity == 10
    assert before_second.obligations[0].segments[-1].event_key == first.event_key
    assert after_day.obligations[0].segments[-1].event_key == second.event_key
    assert before_second.obligations[0].segments == after_day.obligations[0].segments[:-1]
    assert moved.events[-1].event_key == second.event_key  # original input stays intact


@pytest.mark.parametrize(
    "kwargs",
    [
        {"before_boundary_event": "unknown"},
        {"before_boundary_event": "Contract 2/EV-000003"},  # delivery is not an allocation boundary
        {"before_boundary_event": "Contract 2/EV-000009", "boundary_cutoff": date(2023, 5, 15)},
    ],
)
def test_boundary_position_requires_one_retained_boundary(kwargs):
    bundle = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    with pytest.raises(ValueError):
        fold(bundle, **kwargs)
