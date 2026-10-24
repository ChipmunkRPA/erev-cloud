"""Prospective split basis uses dated SSP and preserves original posted revenue."""

from dataclasses import replace
from datetime import date
from fractions import Fraction

import pytest
from support import bundles

from erev_engine.combination_split import prepare
from tests.engine.s06_modifications.test_s06_prospective import ex_09_a, point_entry


def combined():
    value = ex_09_a()
    first = replace(value.contracts[0], modifications=())
    second = replace(first, external_id="SPLIT-B")
    original = next(e for e in value.events if e.event_type == "CONTRACT_BOOKED")
    line = {**original.payload["lines"][0], "product_code": "SKU-SEATS"}
    events = (
        original,
        bundles.event(
            second.external_id,
            1,
            "CONTRACT_BOOKED",
            original.effective_date,
            {**original.payload, "lines": [line]},
            obligation_keys=["POB-01"],
        ),
    )
    events = (
        *events,
        *(
            bundles.event(
                c.external_id, 2, "CONTRACT_ACTIVATED", original.effective_date, {"checklist": {}}
            )
            for c in (first, second)
        ),
    )
    v1, v2 = value.ssp_versions
    v1 = replace(v1, entries=(*v1.entries, point_entry(v1.version_key, "SKU-SEATS", "120000")))
    v2 = replace(
        v2,
        entries=tuple(
            point_entry(v2.version_key, "SKU-SEATS", "155000")
            if e.product_code == "SKU-SEATS"
            else e
            for e in v2.entries
        ),
    )
    return replace(
        value,
        evidence_revision=48,
        group=replace(
            value.group,
            member_contract_keys=tuple(sorted((first.external_id, second.external_id))),
            criterion="25_9_A",
        ),
        contracts=tuple(sorted((first, second), key=lambda c: c.external_id)),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(v1, v2),
    )


def test_split_uses_effective_remaining_ssp_preserving_original_income():
    value = combined()
    targets = {c.external_id: c.external_id for c in value.contracts}
    digest = value.sha256()
    result = prepare(
        value, book_code="ASC606", destinations=targets, effective_date=date(2026, 9, 16)
    )
    a, b = result.members
    assert a.remaining_ssp == b.remaining_ssp
    assert abs(a.remaining_after_minor - b.remaining_after_minor) <= 1
    assert (a.recognized_minor, b.recognized_minor) == (11_309_589, 5_654_795)
    assert (a.remaining_after_minor, b.remaining_after_minor) == (15_517_808, 15_517_808)
    assert a.remaining_before_minor != b.remaining_before_minor
    assert sum(m.remaining_after_minor for m in result.members) == result.unrecognized_minor
    assert sum(m.recognized_minor for m in result.members) == result.recognized_minor
    assert all(
        sum(v for _, v in m.obligation_shares) == m.remaining_after_minor for m in result.members
    )
    assert all(m.original[0].remaining_ssp_sources for m in result.members)
    assert value.sha256() == digest == result.input_sha256
    assert (
        prepare(
            value,
            book_code="ASC606",
            destinations=dict(reversed(list(targets.items()))),
            effective_date=date(2026, 9, 16),
        )
        == result
    )


@pytest.mark.parametrize("targets", [{}, {"SPLIT-B": "new"}])
def test_split_refuses_omitting_original_members(targets):
    with pytest.raises(ValueError, match="every original"):
        prepare(
            combined(), book_code="ASC606", destinations=targets, effective_date=date(2026, 9, 16)
        )


def application_setup(measure="TIME_ELAPSED", group_collision=False):
    from types import MappingProxyType

    from erev_engine import ENGINE_VERSION, fold_book
    from erev_engine.stages import s01_canonicalize, s02_contract_identification, s13_books
    from erev_engine.stages.state import EventView
    from erev_engine.trace import SourceRef, TraceBuilder

    value = combined()
    if group_collision:
        value = replace(value, group=replace(value.group, group_key=value.contracts[0].external_id))
    day = date(2026, 9, 16)
    if measure == "UNITS_DELIVERED":
        delivery = bundles.event(
            value.contracts[0].external_id,
            3,
            "DELIVERY_RECORDED",
            date(2026, 9, 1),
            {"obligation_key": "POB-01", "quantity": "0.25", "trigger": "DELIVERY"},
            obligation_keys=["POB-01"],
        )
        value = replace(
            value,
            pob_template_versions=tuple(
                replace(t, recognition_method=measure) for t in value.pob_template_versions
            ),
            events=tuple(
                sorted(
                    (*value.events, delivery),
                    key=lambda e: (e.effective_date, e.record_seq, e.event_key),
                )
            ),
        )
    trace = TraceBuilder(engine_version=ENGINE_VERSION)
    canonical = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = s13_books.book_context(canonical, value.books[0])
    state = fold_book(ctx, canonical, trace, boundary_cutoff=day)
    identified = s02_contract_identification.run(
        ctx, canonical, TraceBuilder(engine_version=ENGINE_VERSION), deposits=False
    )
    plan = prepare(
        value,
        book_code="ASC606",
        destinations={c.external_id: c.external_id for c in value.contracts},
        effective_date=day,
    )
    event = EventView(
        event_key="SPLIT-1",
        contract_key=value.contracts[0].external_id,
        event_type="COMBINATION_CHANGED",
        effective_date=day,
        record_seq=100,
        recorded_at=value.known_at,
        obligation_subject_keys=(),
        payload=MappingProxyType({}),
        is_new=True,
        source=SourceRef("source_record", "SPLIT-1"),
    )
    state = replace(state, events=(*state.events, event))
    return value, ctx, state, identified, plan, event, trace


@pytest.mark.parametrize("group_collision", [False, True])
def test_native_split_installs_future_segments_without_rewriting_history(group_collision):
    from support.recognition import targets_by_period

    from erev_engine.combination_split_apply import install
    from erev_engine.stages import s09_recognition
    from erev_engine.trace import reevaluate

    _, ctx, state, identified, plan, event, trace = application_setup(
        group_collision=group_collision
    )
    result = install(ctx, state, event, plan, identified, trace)
    for old, new, member in zip(state.obligations, result.obligations, plan.members, strict=True):
        assert new.segments[:-1] == old.segments
        assert new.segments[-1].base_revenue_posted == member.recognized_minor
        assert new.segments[-1].a_posted == member.recognized_minor + member.remaining_after_minor
        assert new.stated_price == old.stated_price
        assert new.segments[-1].remaining_billing_plan == old.segments[-1].remaining_billing_plan
    assert result.refund_components == state.refund_components
    recognition = s09_recognition.run(ctx, result, trace)
    _, base_ctx, base_state, _, _, _, base_trace = application_setup()
    baseline = s09_recognition.run(base_ctx, base_state, base_trace)
    for ob in result.obligations:
        before_periods = targets_by_period(baseline, ob.subject_key)
        after_periods = targets_by_period(recognition, ob.subject_key)
        assert {p: a for p, a in after_periods.items() if p <= "FY2026-P08"} == {
            p: a for p, a in before_periods.items() if p <= "FY2026-P08"
        }
    assert (
        sum(
            targets_by_period(recognition, ob.subject_key)["FY2027-P12"]
            for ob in result.obligations
        )
        == 48_000_000
    )
    assert (
        sum(
            targets_by_period(recognition, ob.subject_key)["FY2026-P08"]
            for ob in result.obligations
        )
        > 0
    )
    rendered = trace.build(root_measures={})
    assert reevaluate(rendered) == {n.id: n.value for n in rendered.nodes}


def test_native_split_rejects_stale_or_invented_member_allocation():
    from erev_engine.combination_split_apply import install

    _, ctx, state, identified, plan, event, trace = application_setup()
    altered = replace(
        plan,
        members=(
            replace(
                plan.members[0], remaining_after_minor=plan.members[0].remaining_after_minor + 1
            ),
            *plan.members[1:],
        ),
    )
    with pytest.raises(ValueError, match="member allocation"):
        install(ctx, state, event, altered, identified, trace)


def test_unit_split_keeps_delivered_units_at_the_boundary():
    from support.recognition import targets_by_period

    from erev_engine.combination_split_apply import install
    from erev_engine.stages import s09_recognition
    from erev_engine.trace import reevaluate

    _, ctx, state, identified, plan, event, trace = application_setup("UNITS_DELIVERED")
    result = install(ctx, state, event, plan, identified, trace)
    recognition = s09_recognition.run(ctx, result, trace)
    assert plan.recognized_minor == 8_000_000
    assert (
        sum(
            targets_by_period(recognition, ob.subject_key)["FY2026-P09"]
            for ob in result.obligations
        )
        == plan.recognized_minor
    )
    assert result.obligations[0].segments[-1].totals.quantity == Fraction(3, 4)
    rendered = trace.build(root_measures={})
    assert reevaluate(rendered) == {n.id: n.value for n in rendered.nodes}


@pytest.mark.parametrize("group_collision", [False, True])
def test_full_native_computation_applies_split_boundary_and_replays_trace(group_collision):
    from erev_engine import compute
    from erev_engine.trace import reevaluate

    source = combined()
    source = replace(source, evidence_revision=49)
    if group_collision:
        source = replace(
            source, group=replace(source.group, group_key=source.contracts[0].external_id)
        )
    event = bundles.event(
        source.contracts[0].external_id,
        3,
        "COMBINATION_CHANGED",
        date(2026, 9, 16),
        {
            "action": "LEAVE",
            "combination_group_id": source.group.group_key,
            "prospective_split_destinations": {
                c.external_id: c.external_id for c in source.contracts
            },
        },
    )
    value = replace(source, events=(*source.events, event))
    result = compute(value).books[0]
    assert [o.columns["allocated_amount"] for o in result.obligation_versions] == [
        26_827_397,
        21_172_603,
    ]
    assert sum(o.columns["allocated_amount"] for o in result.obligation_versions) == 48_000_000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    nodes = {n.id: n for n in result.trace.nodes}
    for row in result.balances:
        for measure in ("contract_liability", "contract_asset", "unbilled_receivable"):
            assert (
                Fraction(nodes[row.trace_nodes[measure]].value) * 100
                == row.columns[f"{measure}_txn"]
            )
    if group_collision:
        for measure in ("contract_liability", "contract_asset", "unbilled_receivable"):
            group_nodes = [n for n in result.trace.nodes if n.measure == f"group_{measure}"]
            assert group_nodes
            for node in group_nodes:
                assert Fraction(node.value) * 100 == sum(
                    row.columns[f"{measure}_txn"]
                    for row in result.balances
                    if row.period_key == node.id.rsplit(":", 1)[1]
                )
    with pytest.raises(ValueError, match="revision 49"):
        compute(replace(value, evidence_revision=48))


def successive_split_bundle(*, same_day=False):
    value = combined()
    third = replace(value.contracts[1], external_id="SPLIT-C")
    extra = tuple(
        bundles.event(
            third.external_id,
            e.stream_version,
            e.event_type,
            e.effective_date,
            e.payload,
            obligation_keys=e.obligation_keys,
        )
        for e in value.events
        if e.contract_key == value.contracts[1].external_id
    )
    a, b = (c.external_id for c in value.contracts)
    c = third.external_id
    first = bundles.event(
        a,
        3,
        "COMBINATION_CHANGED",
        date(2026, 9, 16),
        {"action": "LEAVE", "prospective_split_destinations": {a: "LEFT", b: "REST", c: "REST"}},
        record_seq=100,
    )
    second = bundles.event(
        b,
        3,
        "COMBINATION_CHANGED",
        date(2026, 9, 16) if same_day else date(2026, 10, 16),
        {"action": "LEAVE", "prospective_split_destinations": {b: "REST", c: "NEW"}},
        record_seq=101,
    )
    value = replace(
        value,
        evidence_revision=49,
        contracts=(*value.contracts, third),
        group=replace(value.group, member_contract_keys=(a, b, c)),
        events=tuple(
            sorted(
                (*value.events, *extra, first, second),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
    )
    return value, first, second


@pytest.mark.parametrize("same_day", [False, True])
def test_successive_split_preserves_previously_separated_member(same_day):
    from erev_engine import ENGINE_VERSION, compute, fold_book
    from erev_engine.combination_membership import membership_at
    from erev_engine.stages import s01_canonicalize, s13_books
    from erev_engine.trace import TraceBuilder, reevaluate

    value, first, second = successive_split_bundle(same_day=same_day)
    canonical = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = s13_books.book_context(canonical, value.books[0])
    before = fold_book(
        ctx,
        canonical,
        TraceBuilder(engine_version=ENGINE_VERSION),
        before_boundary_event=second.event_key,
    )
    after = fold_book(
        ctx,
        canonical,
        TraceBuilder(engine_version=ENGINE_VERSION),
        boundary_cutoff=second.effective_date,
    )
    owner = first.contract_key
    assert [o for o in before.obligations if o.contract_key == owner] == [
        o for o in after.obligations if o.contract_key == owner
    ]
    assert all(len(o.segments) == (2 if o.contract_key == owner else 3) for o in after.obligations)
    prior = membership_at(
        value.group.group_key,
        canonical.contracts,
        canonical.events,
        before_event=(second.effective_date, second.record_seq, second.event_key),
    )
    assert prior == {owner: "LEFT", "SPLIT-B": "REST", "SPLIT-C": "REST"}
    final = membership_at(
        value.group.group_key,
        canonical.contracts,
        canonical.events,
        effective_date=second.effective_date,
    )
    assert final == {owner: "LEFT", "SPLIT-B": "REST", "SPLIT-C": "NEW"}
    plan = prepare(
        value,
        book_code="ASC606",
        event_key=second.event_key,
        destinations=second.payload["prospective_split_destinations"],
    )
    assert {m.contract_key for m in plan.members} == {"SPLIT-B", "SPLIT-C"}
    assert sum(m.remaining_after_minor for m in plan.members) == plan.unrecognized_minor
    output = compute(value).books[0]
    baseline = compute(replace(value, events=tuple(e for e in value.events if e != second))).books[
        0
    ]
    owner_versions = [
        o for o in output.obligation_versions if o.subject_key.startswith(owner + "/")
    ]
    prior_versions = [
        o for o in baseline.obligation_versions if o.subject_key.startswith(owner + "/")
    ]
    assert owner_versions and prior_versions
    assert [o.columns["allocated_amount"] for o in owner_versions] == [
        o.columns["allocated_amount"] for o in prior_versions
    ]

    def schedule_amounts(book):
        return [
            (row.period_key, row.amount, row.cumulative_amount)
            for row in book.schedules
            if row.subject_key.startswith(owner + "/") and row.schedule_kind == "REVENUE"
        ]

    assert schedule_amounts(output)
    assert schedule_amounts(output) == schedule_amounts(baseline)
    assert sum(o.columns["allocated_amount"] for o in output.obligation_versions) == 72_000_000
    assert reevaluate(output.trace) == {n.id: n.value for n in output.trace.nodes}


@pytest.mark.parametrize(
    "destinations, message",
    [
        ({"K-01": "LEFT", "SPLIT-B": "REST", "SPLIT-C": "NEW"}, "rejoin"),
        ({"SPLIT-B": "LEFT", "SPLIT-C": "NEW"}, "reuse"),
        ({"SPLIT-B": "NEW"}, "every original"),
    ],
)
def test_successive_split_refuses_cross_group_or_incomplete_population(destinations, message):
    value, _, second = successive_split_bundle()
    with pytest.raises(ValueError, match=message):
        prepare(value, book_code="ASC606", event_key=second.event_key, destinations=destinations)
