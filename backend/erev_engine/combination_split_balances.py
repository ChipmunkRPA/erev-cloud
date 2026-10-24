"""Dated destination balance calculation from retained combination history.

This query reuses original allocation segments, billing and receipt events. It does not
post, change membership, or provide a functional-currency carry-forward baseline.
"""

from dataclasses import dataclass, fields, replace
from datetime import date

from erev_engine import ENGINE_VERSION, fold_book
from erev_engine.bundle import InputBundle
from erev_engine.combination_membership import membership_at
from erev_engine.stages import s01_canonicalize, s09_recognition, s10_billing_balances, s13_books
from erev_engine.stages.state import Target
from erev_engine.trace import Trace, TraceBuilder


@dataclass(frozen=True, slots=True)
class DestinationBalance:
    destination: str
    member_contract_keys: tuple[str, ...]
    book_code: str
    currency: str
    as_of: date
    presentation: tuple[Target, ...]
    member_balances: tuple[Target, ...]
    member_sums: tuple[Target, ...]
    current_split: tuple[Target, ...]
    trace: Trace


def calculate(
    bundle: InputBundle, *, book_code: str, as_of: date
) -> tuple[DestinationBalance, ...]:
    """Measure each effective netting group at a common contracting-period end.

    Original earlier allocations stay intact. Recompute stage 09 and stage 10 for each
    destination using its original member events, rather than apportioning an already
    netted source group's displayed balance. Return transaction-currency measures only.
    This is the fixed-service split lane; specialist flows require separate continuation.
    """
    if (bundle.evidence_revision or 0) < 49 or book_code not in {"ASC606", "IFRS15"}:
        raise ValueError("Destination balances require native split evidence revision 49")
    canonical = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    books = [book for book in bundle.books if book.book_code == book_code]
    if len(books) != 1:
        raise ValueError("The balance book must exist exactly once")
    ctx = s13_books.book_context(canonical, books[0])
    membership = membership_at(
        bundle.group.group_key, canonical.contracts, canonical.events, effective_date=as_of
    )
    if not any(
        e.effective_date <= as_of and "prospective_split_destinations" in e.payload
        for e in canonical.boundary_events
    ):
        raise ValueError("Destination balances require an effective retained split")
    source_trace = TraceBuilder(engine_version=ENGINE_VERSION)
    original = fold_book(ctx, canonical, source_trace, boundary_cutoff=as_of)
    source_evidence = source_trace.build(root_measures={})
    results = []
    for destination in sorted(set(membership.values())):
        members = tuple(sorted(key for key, group in membership.items() if group == destination))
        trace = TraceBuilder(engine_version=ENGINE_VERSION)
        trace.merge_evidence(source_evidence)
        if any(f.severity == "ERROR" for f in original.findings):
            raise ValueError("Destination balance source has blocking calculation findings")
        if original.estimates.pins or original.return_paths or original.refund_components:
            raise ValueError(
                "Estimated or refund balances require separate destination continuation"
            )
        if any(
            getattr(original.specialist_targets, field.name)
            for field in fields(original.specialist_targets)
        ):
            raise ValueError("Specialist balances require separate destination continuation")
        obligations = tuple(o for o in original.obligations if o.contract_key in members)
        if not obligations or any(
            o.scope_flag != "IN_SCOPE_606"
            or o.principal_agent != "PRINCIPAL"
            or o.opening is not None
            or o.material_right is not None
            or o.combined_component_keys
            or o.performing_entity != o.contracting_entity
            or o.recognition_method not in {"TIME_ELAPSED", "UNITS_DELIVERED"}
            or any(s.component != "FIXED" for s in o.segments)
            for o in obligations
        ):
            raise ValueError("Destination balances require supported fixed-service obligations")
        periods = {}
        for entity in {o.contracting_entity for o in obligations}:
            ends = [p.period_key for p in ctx.entities[entity].periods if p.end_date == as_of]
            if len(ends) != 1:
                raise ValueError("Choose a common contracting-period end for destination balances")
            periods[entity] = ends[0]
        segment_events = {s.event_key for o in obligations for s in o.segments}
        scoped = replace(
            original,
            group_code=destination,
            contracts=tuple(c for c in original.contracts if c.header.external_id in members),
            obligations=obligations,
            events=tuple(
                e
                for e in original.events
                if (e.contract_key in members or e.event_key in segment_events)
                and e.effective_date <= as_of
            ),
            measure_events=tuple(
                e
                for e in original.measure_events
                if e.contract_key in members and e.effective_date <= as_of
            ),
        )
        recognized = s09_recognition.run(ctx, scoped, trace)
        balances = s10_billing_balances.run(ctx, recognized, trace)
        if any(f.severity == "ERROR" for f in (*recognized.findings, *balances.findings)):
            raise ValueError("Destination balance calculation has blocking findings")

        def selected(
            targets: tuple[Target, ...], period_keys: dict[str, str] = periods
        ) -> tuple[Target, ...]:
            return tuple(t for t in targets if period_keys.get(t.entity) == t.period_key)

        presentation = selected(balances.presentation)
        if not presentation:
            raise ValueError(
                "The requested balance date is outside the retained calculation horizon"
            )
        results.append(
            DestinationBalance(
                destination,
                members,
                book_code,
                ctx.txn_currency,
                as_of,
                presentation,
                selected(balances.member_balances),
                selected(balances.member_sums),
                selected(balances.current_split),
                trace.build(root_measures={}),
            )
        )
    return tuple(results)


def preview_input(
    bundle: InputBundle, *, effective_date: date, destinations: dict[str, str]
) -> InputBundle:
    """Add a nonpersistent candidate event to an authenticated current source bundle."""
    from erev_engine.bundle import EventInput
    from erev_engine.canonical import sha256_hex

    if (bundle.evidence_revision or 0) < 48:
        raise ValueError("Recompute the source with current evidence before balance preview")
    if not destinations:
        raise ValueError("Select an original population for split preview")
    owner = min(destinations)
    stream = (
        max((e.stream_version for e in bundle.events if e.contract_key == owner), default=0) + 1
    )
    payload: dict[str, object] = {
        "action": "LEAVE",
        "prospective_split_destinations": dict(sorted(destinations.items())),
    }
    event = EventInput(
        event_key=f"{owner}/EV-{stream:06d}",
        contract_key=owner,
        stream_version=stream,
        event_type="COMBINATION_CHANGED",
        schema_version=1,
        effective_date=effective_date,
        recorded_at=bundle.known_at,
        record_seq=max((e.record_seq for e in bundle.events), default=0) + 1,
        origin="SYSTEM",
        is_manual=False,
        obligation_keys=(),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        supersedes_event_key=None,
        modification_key=None,
        estimate_version_key=None,
        manual_adjustment_key=None,
    )
    return replace(
        bundle,
        evidence_revision=max(bundle.evidence_revision or 0, 49),
        trigger="DRY_RUN",
        events=tuple(
            sorted(
                (*bundle.events, event), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
            )
        ),
    )
