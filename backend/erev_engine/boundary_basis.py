"""Fixed allocation evidence at an original or proposed boundary.

This query does not transfer obligations or authorize regrouping. It measures the fixed
component in original event order; callers must handle other consideration components and
preserve the source's recognized revenue when constructing a target's future service.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import localcontext
from fractions import Fraction
from types import MappingProxyType

from erev_engine import ENGINE_VERSION, fold_book, money
from erev_engine.bundle import InputBundle
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s13_books
from erev_engine.stages.s06_modifications import segments, weights
from erev_engine.stages.state import EventView, Finding
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
    remaining_ssp: Fraction | None = None
    remaining_ssp_sources: tuple[SourceRef, ...] = ()
    retained_minor: int = 0
    recognized_total_minor: int | None = None


def fixed_boundary_basis(
    bundle: InputBundle,
    *,
    book_code: str,
    event_key: str | None = None,
    effective_date: date | None = None,
    contract_key: str,
    obligation_keys: tuple[str, ...] | None,
    require_fixed_transfer: bool = False,
    require_remaining_service: bool = True,
    resolve_remaining_ssp: bool = False,
    separation: bool = False,
) -> tuple[FixedBoundaryBasis, ...]:
    """Query selected original obligations without using latest-version remainder columns.

    Monetary integers are transaction-currency minor units. Exact fractions are retained
    separately: a transfer must not introduce a second rounding of recognized income.
    Same-day deliveries, estimates and modifications follow their original event positions.
    Select an existing event to measure strictly before it, or a proposed effective date
    to measure after all retained events on that date. The latter creates no source event;
    it is a current-known-input query, not a historical knowledge snapshot.
    ``obligation_keys=None`` selects every original obligation of the named contract.
    ``resolve_remaining_ssp`` resolves dated remaining-service weights and source references
    using the native prospective-allocation rules, rather than a saved inception weight.
    Transfer preparation opts into fixed-component eligibility checks. A receiving contract's
    existing obligations may be fully performed; only the source must retain movable service.
    Analytical queries remain available for other obligations; their fixed component alone
    does not authorize transferring consideration, progress, FX, or balances.
    """
    if (event_key is None) == (effective_date is None):
        raise ValueError("Choose exactly one original event or proposed effective date")
    if obligation_keys is not None and (
        not obligation_keys or len(set(obligation_keys)) != len(obligation_keys)
    ):
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
        if require_fixed_transfer:
            if any(finding.severity == "ERROR" for finding in state.findings):
                raise ValueError("Transfer basis has blocking calculation findings")
            if any(
                header.noncash_consideration
                or header.consideration_payable
                or header.payment_schedule
                or header.scope_605_35
                for header in bundle.contracts
            ) or any(
                item.event_type in {"COST_INCURRED", "COLLECTIBILITY_ASSESSED"}
                for item in bundle.events
            ):
                raise ValueError(
                    "Specialist consideration and cost balances need separate transfer treatment"
                )
            if bundle.estimate_versions:
                raise ValueError(
                    "Transfer of estimated consideration requires retained member treatment"
                )
        obligations = {
            ob.obligation_key: ob for ob in state.obligations if ob.contract_key == contract_key
        }
        if not obligations:
            raise ValueError("The boundary contract has no original obligations")
        if obligation_keys is None:
            obligation_keys = tuple(sorted(obligations))
        if not set(obligation_keys) <= obligations.keys():
            raise ValueError("Every selected obligation must exist before the original boundary")
        identified = (
            s02_contract_identification.run(
                context, canonical, TraceBuilder(engine_version=ENGINE_VERSION), deposits=False
            )
            if resolve_remaining_ssp
            else None
        )
        digest = bundle.sha256()
        result = []
        for key in sorted(obligation_keys):
            ob = obligations[key]
            if ob.scope_flag != "IN_SCOPE_606":
                raise ValueError("Boundary allocation evidence requires in-scope obligations")
            if require_fixed_transfer:
                if ob.combined_component_keys:
                    raise ValueError("Combined obligations require member-level transfer treatment")
                if ob.opening is not None:
                    raise ValueError(
                        "Acquired obligations require retained opening transfer treatment"
                    )
                if ob.material_right is not None or ob.is_vc_line:
                    raise ValueError(
                        "Material rights and variable consideration need separate transfer bases"
                    )
                if (
                    ob.principal_agent != "PRINCIPAL"
                    or ob.performing_entity != ob.contracting_entity
                ):
                    raise ValueError(
                        "Agent and cross-entity obligations need separate transfer bases"
                    )
                if ob.recognition_method not in {"TIME_ELAPSED", "UNITS_DELIVERED"}:
                    raise ValueError(
                        "This recognition method requires its own transfer progress basis"
                    )
                if any(segment.component != "FIXED" for segment in ob.segments):
                    raise ValueError(
                        "A fixed transfer basis cannot omit other consideration components"
                    )
                if ob.terminated_on is not None and ob.terminated_on <= event.effective_date:
                    raise ValueError(
                        "Terminated obligations have no transferable remaining service"
                    )
            segment = segments.in_force(state, ob, event)
            if segment is None:
                raise ValueError("The selected obligation has no fixed allocation at the boundary")
            if separation:
                from erev_engine.separation import measure, remaining_weight, retained
                from erev_engine.stages.s09_recognition import target_at_position

                measured = measure(context, state, ob, segment, event)
            else:
                measured = segments.measure(context, state, ob, segment, event)
            if require_fixed_transfer and (
                segment.a_posted - measured.posted < 0
                or (
                    require_remaining_service
                    and (
                        measured.remaining_quantity <= 0
                        or (
                            segment.totals.end_date is not None
                            and segment.totals.end_date < event.effective_date
                        )
                    )
                )
            ):
                raise ValueError("The obligation has no transferable remaining service")
            remaining_ssp = None
            ssp_sources: tuple[SourceRef, ...] = ()
            if identified is not None:
                if measured.progress == 1:
                    remaining_ssp = Fraction(0)
                else:
                    findings: list[Finding] = []
                    weight = (
                        remaining_weight(context, state, identified, ob, measured, event, findings)
                        if separation
                        else weights.existing(
                            context,
                            identified,
                            ob,
                            measured,
                            (),
                            event,
                            None,
                            findings,
                            state=state,
                        )
                    )
                    if weight is None or any(f.severity == "ERROR" for f in findings):
                        raise ValueError("Remaining service lacks a valid effective-date SSP")
                    remaining_ssp = weight.value
                    ssp_sources = weight.sources
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
                    remaining_ssp=remaining_ssp,
                    remaining_ssp_sources=ssp_sources,
                    retained_minor=(
                        retained(context, state, ob, measured, event) if separation else 0
                    ),
                    recognized_total_minor=(
                        target_at_position(
                            context,
                            state,
                            ob,
                            event.effective_date - timedelta(days=1)
                            if segment.progress_measure == "TIME_ELAPSED"
                            or (
                                ob.recognition_method in {"USAGE", "ROYALTY"}
                                and ob.satisfaction_pattern == "OVER_TIME"
                            )
                            else event.effective_date,
                            event=event,
                            inclusive=False,
                        ).value
                        if separation
                        else None
                    ),
                )
            )
        return tuple(result)
