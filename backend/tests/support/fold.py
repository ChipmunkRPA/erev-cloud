"""Inception and boundary folds over stages 01 to 08 (ENGINE_SPEC §0.3 ``fold_book``; CV-10, CV-11).

``fold_inception`` runs stage 01 once and stages 02 to 05 for one book of the bundle, with that
book's policies and account mapping, every entity calendar of the bundle and each horizon at the
calendar's last period (CV-13). ``fold_book`` and ``fold_trace`` run stages 02 to 08 through the
book loop (``s13_books.run_books``), which applies the boundary events of Table 0.3-A in ENG-06
order through ``BOUNDARY_HANDLERS`` with the stage 04 price function bound (ENB-13, END-7). No
database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle
from erev_engine.enums import BookCode
from erev_engine.stages import (
    STAGES,
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s13_books import run_books
from erev_engine.stages.state import AllocatedState, BookContext, PolicyResolver
from erev_engine.trace import Trace, TraceBuilder

__all__ = ["FOLD_STAGES", "book_context", "fold_book", "fold_inception", "fold_trace"]

# Stages 02 to 08 of ``STAGES``: the inception fold and the boundary fold.
FOLD_STAGES = tuple(spec for spec in STAGES if spec.stage <= "08")


def book_context(bundle: InputBundle, book_code: str) -> BookContext:
    """The ``BookContext`` of ``book_code``; a book the bundle lacks raises ``ValueError``."""
    book = next((item for item in bundle.books if item.book_code == book_code), None)
    if book is None:
        raise ValueError(f"the bundle keeps no book {book_code!r}")
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=bundle.currencies,
        txn_currency=bundle.group.transaction_currency,
        entities={entity.code: entity for entity in bundle.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in bundle.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=bundle.trigger,
        tenant_preset=bundle.tenant_preset,
    )


def fold_inception(
    bundle: InputBundle, book_code: str, tb: TraceBuilder | None = None
) -> AllocatedState:
    """Stages 01 to 05 at the group inception for ``book_code`` (ENGINE_SPEC §0.3; CV-10).

    Every ``CONTRACT_BOOKED`` of every member enters the fold whatever its effective date. Stage 01
    writes its book-independent nodes to its own builder, as ``compute`` does; stages 02 to 05
    write to ``tb`` when it is given.
    """
    ctx = book_context(bundle, book_code)
    builder = TraceBuilder(engine_version=ENGINE_VERSION) if tb is None else tb
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(ctx, cb, builder, deposits=False)
    pob = s03_pob_builder.run(ctx, identified, builder)
    identified = s02_contract_identification.run_deposits(ctx, identified, pob, builder)
    pob = dataclasses.replace(pob, identified=identified)  # the book loop's fold order (D-91)
    priced = s04_transaction_price.run(ctx, pob, builder)
    return s05_allocation.run(ctx, priced, builder)


def fold_trace(bundle: InputBundle, book_code: str) -> tuple[AllocatedState, Trace]:
    """The state after stages 02 to 08 for ``book_code`` and the book's trace (CV-10, CV-11)."""
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    for result in run_books(cb, FOLD_STAGES):
        if result.book == book_code:
            if not isinstance(result.state, AllocatedState):
                raise TypeError(f"the {book_code} book produced no AllocatedState")
            return result.state, result.trace
    raise ValueError(f"the bundle keeps no enabled book {book_code!r}")


def fold_book(bundle: InputBundle, book_code: str) -> AllocatedState:
    """The state after stages 02 to 08 for ``book_code`` (ENGINE_SPEC §0.3 ``fold_book``)."""
    state, _ = fold_trace(bundle, book_code)
    return state
