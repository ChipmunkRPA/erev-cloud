"""Fixed allocation evidence immediately before an original accepted boundary.

This query does not transfer obligations or authorize regrouping. It measures the fixed
component in original event order; callers must handle other consideration components and
preserve the source's recognized revenue when constructing a target's future service.
"""

from dataclasses import dataclass
from datetime import date
from decimal import localcontext
from fractions import Fraction

from erev_engine import ENGINE_VERSION, fold_book, money
from erev_engine.bundle import InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.stages import s01_canonicalize, s13_books
from erev_engine.stages.s06_modifications import segments
from erev_engine.trace import TraceBuilder


@dataclass(frozen=True, slots=True)
class FixedBoundaryBasis:
    input_sha256: str
    book_code: str
    currency: str
    contract_key: str
    obligation_key: str
    boundary_event_key: str
    effective_date: date
    allocation_exact: Fraction
    recognized_exact: Fraction
    remaining_exact: Fraction
    allocation_minor: int
    recognized_minor: int
    remaining_minor: int
    remaining_quantity: Fraction


def fixed_boundary_basis(
    bundle: InputBundle,
    *,
    book_code: str,
    event_key: str,
    contract_key: str,
    obligation_keys: tuple[str, ...],
) -> tuple[FixedBoundaryBasis, ...]:
    """Query selected original obligations without using latest-version remainder columns.

    Monetary integers are transaction-currency minor units. Exact fractions are retained
    separately: a transfer must not introduce a second rounding of recognized income.
    Same-day deliveries, estimates and modifications follow their original event positions.
    """
    if not obligation_keys or len(set(obligation_keys)) != len(obligation_keys):
        raise ValueError("Select a nonempty, unique boundary obligation population")
    books = [book for book in bundle.books if book.book_code == book_code]
    if len(books) != 1:
        raise ValueError("The boundary book must exist exactly once in the original input")
    with localcontext(money.DECIMAL_CONTEXT):
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        canonical = s01_canonicalize.run(bundle, trace)
        context = s13_books.book_context(canonical, books[0])
        state = fold_book(context, canonical, trace, before_boundary_event=event_key)
        event = next(item for item in state.events if item.event_key == event_key)
        obligations = {
            ob.obligation_key: ob for ob in state.obligations if ob.contract_key == contract_key
        }
        if not set(obligation_keys) <= obligations.keys():
            raise ValueError("Every selected obligation must exist before the original boundary")
        digest = sha256_hex(bundle)
        result = []
        for key in sorted(obligation_keys):
            ob = obligations[key]
            if ob.scope_flag != "IN_SCOPE_606":
                raise ValueError("Boundary allocation evidence requires in-scope obligations")
            segment = segments.in_force(state, ob, event)
            if segment is None:
                raise ValueError("The selected obligation has no fixed allocation at the boundary")
            measured = segments.measure(context, state, ob, segment, event)
            result.append(
                FixedBoundaryBasis(
                    input_sha256=digest,
                    book_code=book_code,
                    currency=context.txn_currency,
                    contract_key=contract_key,
                    obligation_key=key,
                    boundary_event_key=event_key,
                    effective_date=event.effective_date,
                    allocation_exact=segment.x_exact,
                    recognized_exact=measured.exact,
                    remaining_exact=segment.x_exact - measured.exact,
                    allocation_minor=segment.a_posted,
                    recognized_minor=measured.posted,
                    remaining_minor=segment.a_posted - measured.posted,
                    remaining_quantity=measured.remaining_quantity,
                )
            )
        return tuple(result)
