"""Fixed allocation evidence at an original or proposed boundary.

This query does not transfer obligations or authorize regrouping. It measures the fixed
component in original event order; callers must handle other consideration components and
preserve the source's recognized revenue when constructing a target's future service.
"""

from dataclasses import dataclass
from datetime import date
from decimal import localcontext
from fractions import Fraction
from types import MappingProxyType

from erev_engine import ENGINE_VERSION, fold_book, money
from erev_engine.bundle import InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.stages import s01_canonicalize, s13_books
from erev_engine.stages.s06_modifications import segments
from erev_engine.stages.state import EventView
from erev_engine.trace import SourceRef, TraceBuilder


@dataclass(frozen=True, slots=True)
class FixedBoundaryBasis:
    input_sha256: str
    book_code: str
    currency: str
    contract_key: str
    obligation_key: str
    boundary_event_key: str | None
    boundary_position: str
    effective_date: date
    allocation_exact: Fraction
    recognized_exact: Fraction
    remaining_exact: Fraction
    allocation_minor: int
    recognized_minor: int
    remaining_minor: int
    remaining_quantity: Fraction
    service_start_date: date | None
    service_end_date: date | None


def fixed_boundary_basis(
    bundle: InputBundle,
    *,
    book_code: str,
    event_key: str | None = None,
    effective_date: date | None = None,
    contract_key: str,
    obligation_keys: tuple[str, ...],
) -> tuple[FixedBoundaryBasis, ...]:
    """Query selected original obligations without using latest-version remainder columns.

    Monetary integers are transaction-currency minor units. Exact fractions are retained
    separately: a transfer must not introduce a second rounding of recognized income.
    Same-day deliveries, estimates and modifications follow their original event positions.
    Select an existing event to measure strictly before it, or a proposed effective date
    to measure after all retained events on that date. The latter creates no source event;
    it is a current-known-input query, not a historical knowledge snapshot.
    """
    if (event_key is None) == (effective_date is None):
        raise ValueError("Choose exactly one original event or proposed effective date")
    if not obligation_keys or len(set(obligation_keys)) != len(obligation_keys):
        raise ValueError("Select a nonempty, unique boundary obligation population")
    books = [book for book in bundle.books if book.book_code == book_code]
    if len(books) != 1:
        raise ValueError("The boundary book must exist exactly once in the original input")
    with localcontext(money.DECIMAL_CONTEXT):
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        canonical = s01_canonicalize.run(bundle, trace)
        context = s13_books.book_context(canonical, books[0])
        if event_key is not None:
            state = fold_book(context, canonical, trace, before_boundary_event=event_key)
            event = next(item for item in state.events if item.event_key == event_key)
            position = "BEFORE_RETAINED_EVENT"
        else:
            assert effective_date is not None
            state = fold_book(context, canonical, trace, boundary_cutoff=effective_date)
            # A newly authored command follows every already retained record on its
            # effective date. This marker is never appended to the input or persisted.
            event = EventView(
                event_key="query:fixed-boundary",
                contract_key=contract_key,
                event_type="REGROUPED",
                effective_date=effective_date,
                record_seq=max((e.record_seq for e in state.events), default=0) + 1,
                recorded_at=bundle.known_at,
                obligation_subject_keys=(),
                payload=MappingProxyType({}),
                is_new=False,
                source=SourceRef("source_record", "query:fixed-boundary"),
            )
            position = "AFTER_RETAINED_EVENTS_ON_DATE"
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
                    boundary_position=position,
                    effective_date=event.effective_date,
                    allocation_exact=segment.x_exact,
                    recognized_exact=measured.exact,
                    remaining_exact=segment.x_exact - measured.exact,
                    allocation_minor=segment.a_posted,
                    recognized_minor=measured.posted,
                    remaining_minor=segment.a_posted - measured.posted,
                    remaining_quantity=measured.remaining_quantity,
                    service_start_date=segment.totals.start_date,
                    service_end_date=segment.totals.end_date,
                )
            )
        return tuple(result)
