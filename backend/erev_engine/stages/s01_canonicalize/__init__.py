"""Stage 01 engine part: canonicalisation, voids, quantity ledger and estimate pins.

ENGINE_SPEC §1.5 to §1.7 (S01-R-11 to S01-R-20, S01-INV-01 to S01-INV-04); §0.3 Table 0.3-A;
CV-20 to CV-22 and CV-40 to CV-46. ``run`` turns the ``InputBundle`` into the book-independent
``CanonicalBundle`` that every book folds (§0.3). S01-R-01 to S01-R-10 are the platform part (DIN;
BS-D-16). The subject-key helpers and the term readers are exported for later stages; the
submodules are private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import usage
from erev_engine.bundle import InputBundle
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import classify, convert, ledger, pins, voids
from erev_engine.stages.s01_canonicalize.convert import (
    check_selected_quantity_unit,
    contract_entity_subject_key,
    contract_subject_key,
    encode_key,
    group_entity_subject_key,
    judgement_names_element,
    judgement_names_subject,
    member_in_force,
    obligation_subject_key,
    payload_bool,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.state import (
    CanonicalBundle,
    ContractView,
    EventView,
    Finding,
    GroupView,
    LedgerPoint,
    PostedIndex,
    QuantityLedger,
    RateIndex,
    RuleSetIndex,
    SspIndex,
    TemplateIndex,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "booking_lines",
    "check_selected_quantity_unit",
    "contract_entity_subject_key",
    "contract_subject_key",
    "encode_key",
    "group_entity_subject_key",
    "judgement_names_element",
    "judgement_names_subject",
    "member_in_force",
    "obligation_subject_key",
    "payload_bool",
    "payload_date",
    "payload_fraction",
    "payload_text",
    "run",
    "scope_605_35_at",
]

# Payload members of boundary events that add obligations (04 §16.3).
_ADDED_LINE_MEMBERS: Final = MappingProxyType(
    {"CONTRACT_AMENDED": "lines", "MATERIAL_RIGHT_EXERCISED": "new_lines"}
)
# S03-R-18: under the parity preset a line of stratification VC takes LEGACY-VC (kind VC_LINE).
_PARITY_PRESET: Final = "LEGACY_PARITY"
_VC_STRATIFICATION: Final = "VC"


def _vc_lines(
    bundle: InputBundle, contracts: Mapping[str, ContractView], boundary: Sequence[EventView]
) -> frozenset[str]:
    """The parity VC-line subjects (S03-R-18) of the booking and of the boundary events that add
    lines, which the ``REFUND_EXCEEDS_BILLED`` re-check leaves out (04 table 15.4-A #25; DEV-022).
    Empty outside the parity preset, where no VC line exists (DEVIATIONS §3, DEV-077)."""
    if bundle.tenant_preset != _PARITY_PRESET:
        return frozenset()
    found: list[tuple[str, Mapping[str, object]]] = [
        (contract_key, line)
        for contract_key, view in contracts.items()
        for line in booking_lines(view)
    ]
    for view in boundary:
        member = _ADDED_LINE_MEMBERS.get(view.event_type)
        lines = () if member is None else view.payload.get(member, ())
        if isinstance(lines, tuple):
            found.extend((view.contract_key, line) for line in lines if isinstance(line, Mapping))
    return frozenset(
        obligation_subject_key(contract_key, key)
        for contract_key, line in found
        if payload_text(line, "stratification") == _VC_STRATIFICATION
        and (key := payload_text(line, "obligation_key")) is not None
    )


def run(bundle: InputBundle, tb: TraceBuilder) -> CanonicalBundle:
    """The canonical view of ``bundle`` for every book (ENGINE_SPEC §1.5).

    A malformed bundle (unknown literal, unsorted tuple, exponent decimal, event after ``known_at``,
    event of a non-member, invalid void) raises ``ValueError`` (CV-45). Stage findings are returned
    in CV-43 order; ``compute`` raises CV-15 for any ``ERROR``. A failed stage invariant raises
    ``EngineError("ENGINE_INVARIANT_VIOLATED")`` (CV-46).
    """
    convert.check_literals(bundle)
    convert.check_series_quantity_units(bundle)
    convert.assert_bundle_order(bundle)
    convert.check_decimals(bundle)
    members = frozenset(bundle.group.member_contract_keys)
    for event in bundle.events:
        if event.recorded_at > bundle.known_at:
            raise ValueError(f"{event.event_key} was recorded after known_at (RCP-15)")
        if event.contract_key not in members:
            raise ValueError(f"{event.event_key} belongs to a non-member contract (CV-10)")
    included = voids.resolve(bundle.events)
    heads = MappingProxyType(dict(bundle.group.previous_stream_heads))
    events = tuple(convert.event_view(event, heads) for event in included)
    classes = classify.classify(events)
    contracts = _contract_views(bundle, classes.bookings)

    findings: list[Finding] = []
    for view in events:  # S01-R-15
        inception = contracts[view.contract_key].header.inception_date
        if view.effective_date < inception:
            detail = {"event_key": view.event_key, "inception_date": inception.isoformat()}
            subject = contract_subject_key(view.contract_key)
            findings.append(
                Finding("EVENT_BEFORE_INCEPTION", "ERROR", subject, detail, 1, view.event_key)
            )
        if view.event_type == "BILLING_RECORDED":  # S01-R-15a (D-97 (28)): both members required
            missing = [
                member
                for member in ("invoice_number", "line_external_id")
                if view.payload.get(member) in (None, "")
            ]
            if missing:
                detail = {
                    "event_key": view.event_key,
                    "missing": "|".join(missing),
                    "rule": "S01-R-15a",  # 04 table 15.4-B: the required rule member (C6-D97-R1)
                }
                subject = contract_subject_key(view.contract_key)
                findings.append(
                    Finding("BILLING_IDENTITY_MISSING", "ERROR", subject, detail, 1, view.event_key)
                )
    booked = _booked_quantities(contracts)
    changed = classify.quantity_changed(classes.boundary, dict(_by_contract(contracts, booked)))
    vc_lines = _vc_lines(bundle, contracts, classes.boundary)
    right_to_invoice = _right_to_invoice_subjects(bundle, contracts)
    built = ledger.build(classes.measure, booked, changed, vc_lines, right_to_invoice)
    estimates, pin_findings = pins.build(
        included,
        bundle.estimate_versions,
        contracts=bundle.contracts,
        inception_date=bundle.group.inception_date,
    )
    findings.extend(built.findings)
    findings.extend(pin_findings)
    ledger.emit_trace(tb, built, _obligation_subjects(booked, built, classes.boundary))
    ordered = tuple(sorted(findings, key=Finding.sort_key))
    _assert_invariants(events, classes, built.ledger, ordered, vc_lines)

    return CanonicalBundle(
        bundle=bundle,
        currencies=bundle.currencies,
        group=GroupView(
            group=bundle.group,
            products=_by_code(bundle.group.products, lambda product: product.code),
            portfolios=MappingProxyType(
                {p.code: p.member_contract_keys for p in bundle.group.portfolios}
            ),
            previous_stream_heads=heads,
        ),
        contracts=contracts,
        events=events,
        boundary_events=classes.boundary,
        measure_events=classes.measure,
        ledger=built.ledger,
        templates=TemplateIndex(_grouped(bundle.pob_template_versions, lambda t: t.template_code)),
        rule_sets=RuleSetIndex(_grouped(bundle.rule_set_versions, lambda r: r.kind)),
        ssp_books=SspIndex(_grouped(bundle.ssp_versions, lambda v: v.ssp_book_code)),
        estimates=estimates,
        fx=RateIndex(bundle.fx_rates),
        posted=PostedIndex(bundle.posted),
        books=_by_code(bundle.books, lambda book: book.book_code),
        entities=_by_code(bundle.entities, lambda entity: entity.code),
        findings=ordered,
    )


def booking_lines(view: ContractView) -> tuple[Mapping[str, object], ...]:
    """The booking lines (API-S-ContractLine) of a member contract; empty when voided (S01-R-13)."""
    lines = view.booking.get("lines", ())
    if not isinstance(lines, tuple):
        raise ValueError(f"{view.header.external_id}: booking member lines is not an array")
    for line in lines:
        if not isinstance(line, Mapping) or payload_text(line, "obligation_key") is None:
            raise ValueError(f"{view.header.external_id}: a booking line has no obligation_key")
    return tuple(line for line in lines if isinstance(line, Mapping))


def scope_605_35_at(cb: CanonicalBundle, contract_key: str, at: date) -> bool:
    """``scope_605_35`` in force at ``at``: the latest booking or ``CONTRACT_AMENDED`` payload
    carrying the member, else the header projection (S01-R-20; ENGINE_SPEC_B S11-R-15)."""
    value = member_in_force(cb.events, contract_key, "scope_605_35", at)
    if value is None:
        return cb.contracts[contract_key].header.scope_605_35
    if not isinstance(value, bool):
        raise ValueError(f"{contract_key}: payload member scope_605_35 is not a boolean")
    return value


def _contract_views(
    bundle: InputBundle, bookings: Mapping[str, EventView]
) -> Mapping[str, ContractView]:
    views: dict[str, ContractView] = {}
    for header in bundle.contracts:
        booking = bookings.get(header.external_id)
        payload: Mapping[str, object] = MappingProxyType({}) if booking is None else booking.payload
        views[header.external_id] = ContractView(
            header=convert.canonical_header(header, payload),
            booking=payload,
            status_in_book=MappingProxyType({}),
        )
    return MappingProxyType(views)


def _right_to_invoice_subjects(
    bundle: InputBundle, contracts: Mapping[str, ContractView]
) -> frozenset[str]:
    """D-87 L6-5-Q-16 (ENC-6): the booking lines S01-R-17 over-delivery does not apply to — rate
    lines whose resolution is unambiguously ``RIGHT_TO_INVOICE`` before any book stage runs
    (``erev_engine.usage.right_to_invoice_lines``: the product's default template version
    effective at the contract inception, no ``POB_ASSIGNMENT`` rule set in force, not the parity
    preset, and no book's level-O POL-091 ``recognition.measure_of_progress`` override moving the
    obligation to another method — ENC6-R2). Any other line is checked as today (fail closed,
    visible)."""
    overrides = [
        (policy.subject_key, policy.value)
        for book in bundle.books
        for policy in book.policies
        if policy.code == usage.MEASURE_POLICY and policy.level == "O"
    ]
    return usage.right_to_invoice_lines(
        tenant_preset=bundle.tenant_preset,
        products={product.code: product for product in bundle.group.products},
        templates=bundle.pob_template_versions,
        rule_sets=bundle.rule_set_versions,
        bookings={
            contract_key: (view.header.inception_date, tuple(booking_lines(view)))
            for contract_key, view in contracts.items()
        },
        subject_key=obligation_subject_key,
        measure_overrides=overrides,
    )


def _booked_quantities(contracts: Mapping[str, ContractView]) -> Mapping[str, Fraction]:
    booked: dict[str, Fraction] = {}
    for contract_key, view in contracts.items():
        for line in booking_lines(view):
            obligation = payload_text(line, "obligation_key")
            quantity = payload_fraction(line, "quantity")
            if obligation is None or quantity is None:
                raise ValueError(f"{contract_key}: a booking line lacks obligation_key or quantity")
            subject = obligation_subject_key(contract_key, obligation)
            if subject in booked:
                raise ValueError(f"{subject} is booked twice (04 §16.1)")
            booked[subject] = quantity
    return MappingProxyType(dict(sorted(booked.items())))


def _by_contract(
    contracts: Mapping[str, ContractView], booked: Mapping[str, Fraction]
) -> Iterable[tuple[str, tuple[str, ...]]]:
    for contract_key in contracts:
        prefix = f"{contract_subject_key(contract_key)}/"
        yield contract_key, tuple(subject for subject in booked if subject.startswith(prefix))


def _obligation_subjects(
    booked: Mapping[str, Fraction],
    built: ledger.LedgerBuild,
    boundary: Sequence[EventView],
) -> frozenset[str]:
    subjects = set(booked) | set(built.movements)
    for event in boundary:
        member = _ADDED_LINE_MEMBERS.get(event.event_type)
        rows = event.payload.get(member) if member is not None else None
        for row in rows if isinstance(rows, tuple) else ():
            if isinstance(row, Mapping):
                key = payload_text(row, "obligation_key")
                if key is not None:
                    subjects.add(obligation_subject_key(event.contract_key, key))
    return frozenset(subjects)


def _by_code[T](items: Iterable[T], key: Callable[[T], str]) -> Mapping[str, T]:
    return MappingProxyType({key(item): item for item in items})


def _grouped[T](items: Iterable[T], key: Callable[[T], str]) -> Mapping[str, tuple[T, ...]]:
    grouped: dict[str, list[T]] = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return MappingProxyType({code: tuple(members) for code, members in sorted(grouped.items())})


def _check_streams(
    quantities: QuantityLedger, contract_subjects: Iterable[str], vc_lines: frozenset[str]
) -> None:
    """S01-INV-03 for the contract subject: after each of its steps, the billing of every subject of
    the contract covers the credits of every subject (S01-R-16 "over the whole stream"). After each
    step of an obligation, its referenced billing plus ``ledger.referenced_cover`` covers its
    credits (D-87 L6-5-Q-15). Parity VC lines stay out, as in ``ledger.build`` (04 table 15.4-A
    #25; DEV-022)."""
    for contract in sorted(contract_subjects):
        members = [
            (step.order_key, subject, step.point)
            for subject, steps in quantities.steps.items()
            if (subject == contract or subject.startswith(f"{contract}/"))
            and subject not in vc_lines
            for step in steps
        ]
        latest: dict[str, LedgerPoint] = {}
        for _, subject, point in sorted(members, key=lambda member: member[0]):
            latest[subject] = point
            if subject != contract:
                cover = ledger.referenced_cover(latest, contract, subject, vc_lines)
                if point.credited_cum > point.billed_cum + cover:
                    raise _invariant(
                        "S01-INV-03", "a ledger point is negative", subject_key=subject
                    )
                continue
            billed = sum((item.billed_cum for item in latest.values()), Fraction(0))
            credited = sum((item.credited_cum for item in latest.values()), Fraction(0))
            if billed < credited:
                raise _invariant("S01-INV-03", "a ledger point is negative", subject_key=contract)


def _invariant(invariant: str, message: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, detail={"invariant": invariant, **detail}
    )


def _assert_invariants(
    events: Sequence[EventView],
    classes: classify.Classification,
    quantities: QuantityLedger,
    findings: Sequence[Finding],
    vc_lines: frozenset[str] = frozenset(),
) -> None:
    """S01-INV-01 to S01-INV-03 (CV-46); S01-INV-04 holds by construction of ``EstimatePins``.
    [J] A parity VC line may be credited beyond its billing, because ``REFUND_EXCEEDS_BILLED``
    covers non-VC billing only (04 table 15.4-A #25; DEV-022; L6-2-Q-4): its points keep
    ``credited_cum ≥ 0`` without ``billed_cum ≥ credited_cum``."""
    for previous, current in zip(events, events[1:], strict=False):
        if previous.order_key >= current.order_key:
            raise _invariant("S01-INV-01", "events out of order", event_key=current.event_key)
    if any(event.event_type == "EVENT_VOIDED" for event in events):
        raise _invariant("S01-INV-01", "a void remains among the events")
    parts = [*classes.boundary, *classes.measure, *classes.bookings.values()]
    part_keys = [event.event_key for event in parts]
    if len(part_keys) != len(set(part_keys)) or set(part_keys) != {e.event_key for e in events}:
        raise _invariant("S01-INV-02", "classification is not a partition of the events")
    if any(finding.severity == "ERROR" for finding in findings):
        return
    contract_subjects = {contract_subject_key(event.contract_key) for event in events}
    for subject, steps in quantities.steps.items():
        for step in steps:
            point = step.point
            # The contract subject holds unreferenced credits, which draw on the whole stream of
            # the contract (S01-R-16, S10-R-03; L4-3-Q-11): its billed amount may stay below them.
            # So may a parity VC line (docstring), and an obligation whose referenced credits draw
            # on unreferenced billing, which ``_check_streams`` checks (D-87 L6-5-Q-15).
            billed = point.credited_cum
            if not (
                point.delivered_cum >= point.returned_cum >= 0 and billed >= point.credited_cum >= 0
            ):
                raise _invariant("S01-INV-03", "a ledger point is negative", subject_key=subject)
    _check_streams(quantities, contract_subjects, vc_lines)
