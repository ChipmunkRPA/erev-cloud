"""Partial disclosure excludes only dated targeted VC, with fixed consideration retained."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from erev_api.domain.reports import rpo_quotas, variance_rpo
from erev_api.domain.reports.builders import rpo
from erev_api.problems import Problem
from erev_engine import compute
from support import allocation_worlds as worlds


@pytest.mark.parametrize("target_amount, expected_cap", [("200", "200"), ("-50", "0")])
def test_real_engine_targeted_changes_keep_fixed_consideration(
    target_amount: str,
    expected_cap: str,
) -> None:
    targeted = worlds.element("100", keys=["A"])
    base = worlds.untargeted_element("0")
    bundle = worlds.with_changes(
        worlds.targeted_world(estimates=[targeted, base]),
        [
            worlds.later_version(targeted, 2, date(2026, 2, 1), target_amount),
            worlds.later_version(base, 2, date(2026, 3, 1), "100"),
        ],
        memo_on=date(2026, 3, 31),
        policies={"rpo.exemption_vc_wholly_unsatisfied": "APPLY"},
    )
    output = compute(bundle)
    book = output.books[0]
    from erev_api.domain.reports import rpo_estimate_changes

    events = frozenset(
        event.event_key
        for event in bundle.events
        if event.event_type == "ESTIMATE_CHANGED" and event.effective_date > date(2026, 1, 1)
    )
    changes = rpo_estimate_changes.allocations(book.trace, events)
    assert changes is not None
    assert sum(changes.values()) == Decimal(target_amount)
    assert rpo_estimate_changes.allocations(book.trace, events | {"absent"}) is None
    share = next(
        node
        for node in book.trace.nodes
        if node.measure.startswith("tp_share@") and Decimal(node.value) != 0
    )
    incomplete = replace(
        book.trace, nodes=tuple(node for node in book.trace.nodes if node != share)
    )
    assert rpo_estimate_changes.allocations(incomplete, events) is None
    eligibility = {
        item.version_key: item.allocation_target == "OBLIGATIONS"
        and item.parameters.get("allocation_criteria_evidence") not in (None, "")
        for item in bundle.estimate_versions
    }
    history = rpo_quotas.history(
        book.trace,
        inception={item.external_id: item.inception_date for item in bundle.contracts},
        targeted=eligibility,
    )
    points = history["K-01/A"]
    assert rpo_quotas.cap(points, date(2026, 1, 31)) == Decimal("100")
    assert rpo_quotas.cap(points, date(2026, 2, 28)) == Decimal(expected_cap)
    assert rpo_quotas.cap(points, date(2026, 3, 31)) == Decimal(expected_cap)
    entity = bundle.entities[0]
    period = next(item for item in entity.periods if item.end_date == date(2026, 3, 31))
    result = variance_rpo.project(
        bundle, book, entity_code=entity.code, period_key=period.period_key, functional=False
    )
    gross = (
        sum(
            Decimal(str(item.columns["scheduled_amount"]))
            + Decimal(str(item.columns["awaiting_trigger_amount"]))
            for item in book.obligation_versions
        )
        / 100
    )
    assert sum(result.values()) == gross - Decimal(expected_cap)
    if target_amount == "200":
        assert sum(result.values()) == 200  # fixed 100 + untargeted 100 remains
    with pytest.raises(Problem, match="retained estimate version"):
        rpo_quotas.history(
            book.trace,
            inception={item.external_id: item.inception_date for item in bundle.contracts},
            targeted={},
        )


def test_partial_exemption_apportions_bands_and_releases_after_performance() -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, oid, cid, eid = (uuid4() for _ in range(4))
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal("150"),
        False,
    )
    day = date(2026, 1, 31)
    at = ObligationAt(
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal(0),
        Decimal("150"),
        "UNSATISFIED",
        None,
        None,
    )
    version = rpo._Version(vid, uuid4(), 1, True, date(2026, 1, 1), frozenset())
    store = rpo.Store(
        {version.group_id: (version,)},
        {vid: (ob,)},
        {cid: (version,)},
        {(vid, day): {oid: at}},
        {vid: {"C/O": (rpo_quotas.Point(date(2026, 1, 1), Decimal(100), "quota"),)}},
    )
    (row,) = rpo.rows_at(
        store, as_of={eid: day}, bands=(12, 24), applied={eid: frozenset({"POL-200"})}
    )
    assert (row.total, row.excluded, row.partial_exemption) == (
        Decimal(50),
        Decimal(100),
        "POL-200",
    )
    assert sum(row.placed) == sum(item[2] for item in row.contributors) == row.total
    assert row.placed == (Decimal(0), Decimal(0), Decimal(50))
    store.cuts[(vid, day)] = {
        oid: replace(
            at, revenue=Decimal(1), awaiting=Decimal(149), satisfaction_status="PARTIALLY_SATISFIED"
        )
    }
    (row,) = rpo.rows_at(
        store, as_of={eid: day}, bands=(12, 24), applied={eid: frozenset({"POL-200"})}
    )
    assert (row.total, row.excluded) == (Decimal(149), Decimal(0))

    # Beginning performance releases the exclusion separately from revenue.
    end = date(2026, 2, 28)
    store.cuts[(vid, end)] = store.cuts[(vid, day)]
    store.cuts[(vid, day)] = {oid: at}
    (movement,) = rpo.rollforward_lines(
        store, ranges={eid: (day, end)}, applied={eid: frozenset({"POL-200"})}
    )
    assert movement.lines["OPENING"] == 50
    assert movement.lines["EXEMPTIONS"] == 100
    (detail,) = movement.exemption_changes
    assert detail["opening_rule"] == "POL-200"
    assert detail["closing_rule"] is None
    assert Decimal(detail["opening_excluded"]) == 100
    assert Decimal(detail["closing_excluded"]) == 0
    assert movement.lines["REVENUE"] == -1
    assert movement.lines["CLOSING"] == 149
    assert movement.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize(
    "original_end, revised_end, exempt",
    [
        (date(2026, 12, 31), date(2027, 12, 31), True),
        (date(2027, 12, 31), date(2026, 12, 31), False),
        (date(2027, 1, 1), date(2027, 6, 30), False),
    ],
)
def test_original_duration_survives_contract_term_changes(
    original_end: date, revised_end: date, exempt: bool
) -> None:
    from erev_api.domain.reports import rpo_duration
    from erev_engine.bundle import ModificationInput
    from support import bundles

    bundle = worlds.native(
        {**worlds.line("A", "PROD-A", "100"), "end_date": original_end},
        entries=[worlds.entry("PROD-A", point="100")],
        activated=True,
        overrides={
            worlds.TOLERANCE: "NOT_ENFORCED",
            "rpo.exemption_original_duration_one_year": "APPLY",
        },
    )
    amendment = {
        "obligation_key": "A",
        "action": "CHANGE",
        "product_code": "PROD-A",
        "quantity_delta": Decimal(0),
        "consideration_delta": Decimal(0),
        "end_date": revised_end,
    }
    effective = date(2026, 6, 1)
    modification = ModificationInput(
        modification_key="TERM",
        effective_date=effective,
        kind="CHANGE_SCOPE",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(amendment,),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    changed = bundles.event(
        worlds.CONTRACT,
        3,
        "CONTRACT_AMENDED",
        effective,
        {
            "modification_id": "TERM",
            "treatments": {"A": "PROSPECTIVE"},
            "lines": [amendment],
            "ssp_basis": {},
        },
        obligation_keys=["A"],
    )
    bundle = replace(
        bundle,
        contracts=(replace(bundle.contracts[0], modifications=(modification,)),),
        events=(*bundle.events, changed),
    )
    bundle = worlds.with_changes(
        bundle, (), policies={"rpo.exemption_original_duration_one_year": "APPLY"}
    )
    output = compute(bundle)
    book = output.books[0]
    assert book.obligation_versions[0].columns["end_date"] == revised_end
    assert rpo_duration.original_ends(bundle, "ASC606")[worlds.CONTRACT] == original_end
    result = variance_rpo.project(
        bundle,
        book,
        entity_code=bundle.entities[0].code,
        period_key="FY2026-P06",
        functional=False,
    )
    assert sum(result.values()) == (0 if exempt else 100)


@pytest.mark.parametrize(
    "opening_method,closing_method,elected,expected",
    [
        ("POINT_IN_TIME", rpo.RIGHT_TO_INVOICE, True, (100, -100, 0)),
        (rpo.RIGHT_TO_INVOICE, "POINT_IN_TIME", True, (0, 100, 100)),
        ("POINT_IN_TIME", rpo.RIGHT_TO_INVOICE, False, (100, 0, 100)),
        (rpo.RIGHT_TO_INVOICE, rpo.RIGHT_TO_INVOICE, True, None),
    ],
)
def test_rollforward_exemption_changes_preserve_both_endpoints(
    opening_method: str, closing_method: str, elected: bool, expected: tuple[int, int, int] | None
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, next_vid, oid, cid, eid, gid = (uuid4() for _ in range(6))
    before, end = date(2026, 1, 31), date(2026, 2, 28)
    first = rpo._Version(vid, gid, 1, True, date(2026, 1, 1), frozenset())
    second = rpo._Version(next_vid, gid, 2, True, date(2026, 2, 1), frozenset({"CONTRACT_AMENDED"}))
    old = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        opening_method,
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal(100),
        False,
    )
    new = replace(old, version_id=next_vid, recognition_method=closing_method)
    at = ObligationAt(*(Decimal(0) for _ in range(7)), Decimal(100), "UNSATISFIED", None, None)
    store = rpo.Store(
        {gid: (first, second)},
        {vid: (old,), next_vid: (new,)},
        {cid: (first, second)},
        {
            (version.id, day): {oid: at}
            for version in (first, second)
            for day in (before, second.effective, end)
        },
    )
    applied = {eid: frozenset({"POL-198"}) if elected else frozenset()}
    movements = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied=applied)
    if expected is None:
        assert movements == ()
        return
    (movement,) = movements
    assert tuple(movement.lines[key] for key in ("OPENING", "EXEMPTIONS", "CLOSING")) == expected
    assert movement.lines["UNEXPLAINED"] == 0
    if elected and opening_method != closing_method:
        (detail,) = movement.exemption_changes
        assert detail["obligation"] == "O"
        assert detail["currency"] == "USD"
        assert Decimal(detail["movement"]) == movement.lines["EXEMPTIONS"]
        assert Decimal(detail["opening_excluded"]) - Decimal(detail["closing_excluded"]) == Decimal(
            detail["movement"]
        )
        assert {detail["opening_rule"], detail["closing_rule"]} == {None, "POL-198"}
    for day, key in ((before, "OPENING"), (end, "CLOSING")):
        rows = rpo.rows_at(store, as_of={eid: day}, bands=(12, 24), applied=applied)
        assert sum(row.total for row in rows if row.exemption is None) == movement.lines[key]


@pytest.mark.parametrize(
    "mixed,realised,usage_delta",
    [
        (False, False, 0),
        (False, True, 0),
        (True, False, 0),
        (True, True, 0),
        (True, True, 30),
        (True, True, -20),
    ],
)
@pytest.mark.parametrize("restated,revenue", [(40, 40), (40, 50), (45, 50), (40, 0)])
def test_terminal_cancellation_removes_remaining_rpo_not_recognized_revenue(
    restated: int, revenue: int, realised: bool, mixed: bool, usage_delta: int
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, next_vid, oid, cid, eid, gid = (uuid4() for _ in range(6))
    before, end = date(2026, 1, 31), date(2026, 2, 28)
    first = rpo._Version(vid, gid, 1, True, date(2026, 1, 1), frozenset())
    second = rpo._Version(next_vid, gid, 2, True, end, frozenset({"CONTRACT_TERMINATED"}))
    old = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal(100),
        False,
    )
    cancelled = replace(old, version_id=next_vid, cancelled=True)
    at = ObligationAt(
        Decimal(40),
        *(Decimal(0) for _ in range(6)),
        Decimal(60),
        "PARTIALLY_SATISFIED",
        None,
        None,
    )
    if realised:
        at = replace(
            at,
            realised=Decimal(100),
            realised_stored=Decimal(100),
            realised_traced=True,
            realised_through=Decimal(100),
        )
    store = rpo.Store(
        {gid: (first, second)},
        {vid: (old,), next_vid: (cancelled,)},
        {cid: (first, second)},
        {
            (vid, before): {oid: at},
            (vid, end): {oid: at},
            (next_vid, before): {oid: replace(at, revenue=Decimal(restated))},
            (next_vid, end): {oid: replace(at, revenue=Decimal(revenue), awaiting=Decimal(0))},
        },
    )
    if mixed:
        from erev_api.domain.reports.rpo_boundary_changes import Change

        second = replace(
            second,
            causes=second.causes | {"CONTRACT_AMENDED", "ESTIMATE_CHANGED"},
            modification_events=frozenset({"mod"}),
            cancellation_events=frozenset({"cancel"}),
            estimate_events=frozenset({"estimate"}),
            estimate_dates=(("estimate", date(2026, 2, 10)),),
        )
        store = replace(store, versions={gid: (first, second)}, chains={cid: (first, second)})
        opening_fixed = Decimal(0 if realised else 100)
        store.estimate_allocations[next_vid] = {"C/O": Decimal(20)}
        store.boundaries[next_vid] = {
            "C/O": (
                Change(
                    date(2026, 2, 1),
                    "mod",
                    "CONTRACT_AMENDED",
                    Decimal(30),
                    record_seq=1,
                    before=opening_fixed,
                    after=opening_fixed + 30,
                ),
                Change(
                    end,
                    "cancel",
                    "CONTRACT_TERMINATED",
                    -(opening_fixed + 50),
                    record_seq=3,
                    before=opening_fixed + 50,
                    after=Decimal(0),
                ),
            )
        }
        (legacy,) = rpo.rollforward_lines(
            replace(store, classify_cancelled_changes=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy.lines["UNEXPLAINED"] != 0
        valid = store.boundaries[next_vid]
        changed = valid["C/O"]
        store.boundaries[next_vid] = {
            "C/O": (*changed[:-1], replace(changed[-1], before=opening_fixed + 51))
        }
        (unmatched,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
        assert unmatched.lines["UNEXPLAINED"] != 0
        assert unmatched.lines["MODIFICATIONS"] == 0
        store.boundaries[next_vid] = valid
    if realised and mixed:
        second = replace(second, causes=second.causes | {"USAGE_REPORTED"})
        store = replace(store, versions={gid: (first, second)}, chains={cid: (first, second)})
        store.cuts[next_vid, end] = {
            oid: replace(store.cuts[next_vid, end][oid], realised=Decimal(100 + usage_delta))
        }
        (legacy_usage,) = rpo.rollforward_lines(
            replace(store, classify_cancelled_usage=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy_usage.lines["UNEXPLAINED"] != 0
        evidenced = store.cuts[next_vid, end]
        store.cuts[next_vid, end] = {oid: replace(evidenced[oid], realised_traced=False)}
        (missing_realization,) = rpo.rollforward_lines(
            store, ranges={eid: (before, end)}, applied={}
        )
        assert missing_realization.lines["UNEXPLAINED"] != 0
        store.cuts[next_vid, end] = evidenced
    else:
        usage_delta = 0
    (movement,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert movement.lines["OPENING"] == 60
    assert movement.lines["CANCELLATIONS"] == -(100 + (50 if mixed else 0) + usage_delta - revenue)
    assert movement.lines["MODIFICATIONS"] == (30 if mixed else 0)
    assert movement.lines["VC_ESTIMATE_CHANGES"] == (20 if mixed else 0) + usage_delta
    assert movement.lines["REVENUE"] == -(revenue - restated)
    assert movement.lines["LATE_EVENTS"] == -(restated - 40)
    assert movement.lines["CLOSING"] == movement.lines["UNEXPLAINED"] == 0
    if realised and mixed:
        retained_id = uuid4()
        retained = replace(
            second, id=retained_id, version_no=3, causes=frozenset({"USAGE_REPORTED"})
        )
        correction = Decimal(10)
        retained_points = {
            (retained_id, day): points
            for (source, day), points in store.cuts.items()
            if source == next_vid
        }
        retained_points[retained_id, end] = {
            oid: replace(
                store.cuts[next_vid, end][oid],
                realised=Decimal(110 + usage_delta),
                revenue=Decimal(revenue) + correction,
            )
        }
        chain = (first, second, retained)
        continued = replace(
            store,
            versions={gid: chain},
            chains={cid: chain},
            obligations={
                **store.obligations,
                retained_id: (replace(cancelled, version_id=retained_id),),
            },
            cuts={**store.cuts, **retained_points},
        )
        (updated,) = rpo.rollforward_lines(continued, ranges={eid: (before, end)}, applied={})
        expected = dict(movement.lines)
        expected["VC_ESTIMATE_CHANGES"] += correction
        expected["REVENUE"] -= correction
        assert updated.lines == expected


@pytest.mark.parametrize("eligibility", [False, True])
@pytest.mark.parametrize("realized_fees", [False, True])
@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize("start_after_cancellation", [False, True])
def test_reentry_uses_remaining_balance_and_segment_revenue(
    repeated: bool, start_after_cancellation: bool, realized_fees: bool, eligibility: bool
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    oid, cid, eid, gid = (uuid4() for _ in range(4))
    end = date(2026, 2, 28)
    before = date(2026, 2, 15) if start_after_cancellation else date(2026, 1, 31)
    # Revenue changes while excluded (45 -> 50, and 60 -> 70) enter only
    # through the remaining balance; they are not new in-scope revenue.
    states = [
        (date(2026, 1, 1), False, 40),
        (date(2026, 2, 10), True, 45),
        (date(2026, 2, 20), False, 50),
    ]
    if repeated:
        states += [(date(2026, 2, 23), True, 60), (date(2026, 2, 25), False, 70)]
    versions = []
    obligations = {}
    cuts = {}
    final_revenue = 80 if repeated else 60
    days = {before, end, *(day for day, _, _ in states)}
    for index, (effective, cancelled, _entry_revenue) in enumerate(states):
        vid = uuid4()
        version = rpo._Version(
            vid,
            gid,
            index + 1,
            not cancelled if eligibility else True,
            effective,
            frozenset(
                {"COLLECTIBILITY_ASSESSED" if cancelled else "CONTRACT_CRITERIA_MET"}
                if eligibility
                else {"CONTRACT_TERMINATED" if cancelled else "CONTRACT_ACTIVATED"}
            ),
            entries=((cid, effective),) if eligibility and not cancelled else (),
            eligibility_exits=((cid, effective),) if eligibility and cancelled else (),
        )
        versions.append(version)
        ob = rpo._Ob(
            oid,
            vid,
            oid,
            cid,
            "C",
            "O",
            "Service",
            None,
            None,
            None,
            eid,
            "E",
            "USD",
            "POINT_IN_TIME",
            date(2028, 12, 31),
            date(2026, 1, 1),
            Decimal(100),
            cancelled and not eligibility,
        )
        obligations[vid] = (ob,)
        for day in days:
            revenue = 40
            for event_day, _, amount in states[: index + 1]:
                if day >= event_day:
                    revenue = amount
            if index == len(states) - 1 and day == end:
                revenue = final_revenue
            cuts[vid, day] = {
                oid: ObligationAt(
                    Decimal(revenue),
                    *(Decimal(0) for _ in range(6)),
                    Decimal(0 if cancelled else 100 - revenue),
                    "PARTIALLY_SATISFIED",
                    None,
                    None,
                )
            }
    final_fee = 20 + (len(states) - 1) * 5 + 10
    if realized_fees:
        for index, version in enumerate(versions):
            stored_fee = final_fee if index == len(states) - 1 else 20 + index * 5
            obligations[version.id] = tuple(
                replace(ob, allocated=Decimal(100 + stored_fee)) for ob in obligations[version.id]
            )
            for day in days:
                fee = 20
                for event_index, (event_day, _, _) in enumerate(states[: index + 1]):
                    if day >= event_day:
                        fee = 20 + event_index * 5
                if index == len(states) - 1 and day == end:
                    fee = final_fee
                point = cuts[version.id, day][oid]
                cuts[version.id, day] = {
                    oid: replace(
                        point,
                        awaiting=point.awaiting + (0 if states[index][1] else fee),
                        fixed_allocation=Decimal(100),
                        realised=Decimal(fee),
                        realised_stored=Decimal(stored_fee),
                        realised_traced=True,
                    )
                }
    if eligibility and not realized_fees:
        cuts = {
            key: {oid: replace(point[oid], fixed_allocation=Decimal(100), realised_traced=True)}
            for key, point in cuts.items()
        }
    chain = tuple(versions)
    store = rpo.Store({gid: chain}, obligations, {cid: chain}, cuts)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["OPENING"] == (
        0 if start_after_cancellation else 60 + (20 if realized_fees else 0)
    )
    expected_exits = (0 if start_after_cancellation else -55 - (25 if realized_fees else 0)) + (
        -40 - (35 if realized_fees else 0) if repeated else 0
    )
    expected_entries = (80 if repeated else 50) + ((70 if repeated else 30) if realized_fees else 0)
    assert result.lines["CANCELLATIONS"] == (0 if eligibility else expected_exits)
    assert result.lines["NEW_CONTRACTS"] == (0 if eligibility else expected_entries)
    assert result.lines["ELIGIBILITY_CHANGES"] == (
        expected_entries + expected_exits if eligibility else 0
    )
    assert result.lines["REVENUE"] == (
        (0 if start_after_cancellation else -5) + (-20 if repeated else -10)
    )
    assert result.lines["LATE_EVENTS"] == 0
    assert result.lines["CLOSING"] == 100 - final_revenue + (final_fee if realized_fees else 0)
    assert result.lines["VC_ESTIMATE_CHANGES"] == (
        (0 if start_after_cancellation else 5) + (5 if repeated else 0) + 10 if realized_fees else 0
    )
    assert result.lines["UNEXPLAINED"] == 0

    if eligibility and start_after_cancellation and not repeated:
        # A first-ever criteria admission has no earlier included segment and is
        # still a new contract, even if a not-a-contract version already exists.
        first_chain = chain[1:]
        (first_admission,) = rpo.rollforward_lines(
            replace(store, versions={gid: first_chain}, chains={cid: first_chain}),
            ranges={eid: (before, end)},
            applied={},
        )
        assert first_admission.lines["ELIGIBILITY_CHANGES"] == 0
        assert first_admission.lines["NEW_CONTRACTS"] > 0
    if eligibility:
        (legacy,) = rpo.rollforward_lines(
            replace(store, classify_eligibility_changes=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy.lines["ELIGIBILITY_CHANGES"] == 0
        assert legacy.lines != result.lines
    elif realized_fees:
        (legacy,) = rpo.rollforward_lines(
            replace(store, classify_usage_reentry=False),
            ranges={eid: (before, end)},
            applied={},
        )
        # The old classification could balance while admitting too little RPO
        # and overstating in-scope fee changes. Check the individual lines.
        assert legacy.lines["NEW_CONTRACTS"] != result.lines["NEW_CONTRACTS"]
        assert legacy.lines["VC_ESTIMATE_CHANGES"] != result.lines["VC_ESTIMATE_CHANGES"]


@pytest.mark.parametrize(
    "closing,estimate,modification", [(150, 20, 30), (100, 20, -20), (90, -20, 10)]
)
@pytest.mark.parametrize("added", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_mixed_modification_and_estimate_uses_retained_event_shares(
    closing: int, estimate: int, modification: int, added: bool, mixed: bool
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, next_vid, oid, cid, eid, gid = (uuid4() for _ in range(6))
    before, end = date(2026, 1, 31), date(2026, 2, 28)
    first = rpo._Version(vid, gid, 1, True, date(2026, 1, 1), frozenset())
    second = rpo._Version(
        next_vid,
        gid,
        2,
        True,
        end,
        frozenset({"CONTRACT_AMENDED", "ESTIMATE_CHANGED"} if mixed else {"CONTRACT_AMENDED"}),
    )
    old = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal(100),
        False,
    )
    new = replace(old, version_id=next_vid, allocated=Decimal(closing))
    at = ObligationAt(
        *(Decimal(0) for _ in range(7)),
        Decimal(100),
        "UNSATISFIED",
        None,
        None,
    )
    store = rpo.Store(
        {gid: (first, second)},
        {vid: () if added else (old,), next_vid: (new,)},
        {cid: (first, second)},
        {
            (vid, before): {oid: at},
            (vid, end): {oid: at},
            (next_vid, before): {oid: at},
            (next_vid, end): {oid: replace(at, awaiting=Decimal(closing))},
        },
    )
    if added:
        (legacy,) = rpo.rollforward_lines(
            replace(store, classify_added_obligations=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy.lines["NEW_CONTRACTS"] == closing
        assert legacy.lines["MODIFICATIONS"] == 0
    (unknown,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    opening = 0 if added else 100
    delta = closing - opening
    assert unknown.lines["NEW_CONTRACTS"] == 0
    assert unknown.lines["OPENING"] == opening
    assert unknown.lines["CLOSING"] == closing
    assert unknown.lines["UNEXPLAINED"] == (delta if mixed else 0)
    assert unknown.lines["MODIFICATIONS"] == (0 if mixed else delta)
    assert unknown.lines["VC_ESTIMATE_CHANGES"] == 0
    store.estimate_allocations[next_vid] = {"C/O": Decimal(estimate)}
    (known,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert known.lines["NEW_CONTRACTS"] == 0
    assert known.lines["VC_ESTIMATE_CHANGES"] == (estimate if mixed else 0)
    assert known.lines["MODIFICATIONS"] == (
        (modification + (100 if added else 0)) if mixed else delta
    )
    assert known.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize(
    "with_modification,later_amount,added,same_day,cross_effect,across_periods",
    [
        (False, "200", False, False, False, False),
        (False, "-50", False, False, False, False),
        (True, "200", False, False, False, False),
        (True, "80", False, False, False, False),
        (True, "200", True, False, False, False),
        (True, "80", True, False, False, False),
        (True, "200", False, True, False, False),
        (True, "80", False, True, False, False),
        (True, "200", False, False, True, False),
        (True, "200", False, False, True, True),
    ],
)
def test_first_entry_separates_later_original_estimate_events(
    later_amount: str,
    with_modification: bool,
    added: bool,
    same_day: bool,
    cross_effect: bool,
    across_periods: bool,
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt
    from erev_api.domain.reports.rpo_estimate_changes import allocations

    targeted = worlds.element("100", keys=["A"])
    base = worlds.targeted_world(estimates=[targeted])
    original = compute(base).books[0]
    modification = Decimal(0)
    if with_modification:
        from support import cpc_worlds

        concession = cpc_worlds.concession("-20", date(2026, 2, 1), key="A")
        concession = replace(
            concession,
            modification_key="K-01/MOD-1",
            status="APPLIED",
            price_change_amount=None,
            questionnaire={},
            chosen_treatments={"A": "PROSPECTIVE", "B": "PROSPECTIVE"},
            treatment_summary="PROSPECTIVE",
            lines=tuple({**line, "product_code": "PROD-A"} for line in concession.lines),
        )
        base = replace(
            base,
            contracts=tuple(replace(c, modifications=(concession,)) for c in base.contracts),
            events=tuple(
                cpc_worlds.amended(list(base.events), concession, concession.chosen_treatments)
            ),
        )
        modification = Decimal(-20)
        if added:
            addition = replace(
                concession,
                modification_key="K-01/MOD-2",
                kind="ADD_OBLIGATION",
                chosen_treatments={"A": "PROSPECTIVE", "B": "PROSPECTIVE", "C": "PROSPECTIVE"},
                lines=(
                    {
                        "obligation_key": "C",
                        "action": "ADD",
                        "product_code": "PROD-B",
                        "quantity_delta": Decimal(1),
                        "consideration_delta": Decimal(40),
                        "start_date": date(2026, 2, 1),
                        "end_date": date(2026, 12, 31),
                    },
                ),
            )
            base = replace(
                base,
                contracts=tuple(
                    replace(c, modifications=(*c.modifications, addition)) for c in base.contracts
                ),
                events=tuple(
                    cpc_worlds.amended(list(base.events), addition, addition.chosen_treatments)
                ),
            )
            modification += 40
    bundle = worlds.with_changes(
        base,
        [worlds.later_version(targeted, 2, date(2026, 2, 15), later_amount)],
        memo_on=date(2026, 2, 28),
    )
    book = compute(bundle).books[0]
    vid, cid, eid, gid = (uuid4() for _ in range(4))
    entry, before, end = (
        date(2026, 1, 1),
        date(2025, 12, 31),
        date(2026, 3, 31) if across_periods else date(2026, 2, 28),
    )
    estimates = tuple(
        (event.event_key, event.effective_date)
        for event in bundle.events
        if event.event_type == "ESTIMATE_CHANGED"
    )
    version = rpo._Version(
        vid,
        gid,
        1,
        True,
        entry,
        frozenset({"CONTRACT_ACTIVATED", "ESTIMATE_CHANGED"}),
        entries=((cid, entry),),
        estimate_events=frozenset(key for key, _ in estimates),
        estimate_dates=estimates,
        modification_events=frozenset(
            event.event_key for event in bundle.events if event.event_type == "CONTRACT_AMENDED"
        ),
    )
    if with_modification:
        version = replace(version, causes=version.causes | {"CONTRACT_AMENDED"})
    obligations = []
    cuts = {}
    for output in book.obligation_versions:
        columns = output.columns
        oid = uuid4()
        allocated = Decimal(str(columns["allocated_amount"])) / 100
        ob = rpo._Ob(
            oid,
            vid,
            oid,
            cid,
            "K-01",
            str(columns["obligation_key"]),
            "Service",
            None,
            None,
            None,
            eid,
            "E",
            "USD",
            "POINT_IN_TIME",
            date(2028, 12, 31),
            entry,
            allocated,
            False,
        )
        obligations.append(ob)
        at = ObligationAt(*(Decimal(0) for _ in range(7)), allocated, "UNSATISFIED", None, None)
        for day in (before, entry, end):
            cuts.setdefault((vid, day), {})[oid] = at
    store = rpo.Store({gid: (version,)}, {vid: tuple(obligations)}, {cid: (version,)}, cuts)
    from erev_api.domain.reports.rpo_boundary_changes import history

    store.boundaries[vid] = history(book.trace)
    if added:
        from erev_api.domain.reports.rpo_boundary_changes import complete

        assert complete(store.boundaries[vid], "K-01/C", version.modification_events)
        # Zero before-value alone is not evidence of an obligation's absence.
        without_creation = {
            subject: tuple(replace(change, created=False) for change in changes)
            for subject, changes in store.boundaries[vid].items()
        }
        assert not complete(without_creation, "K-01/C", version.modification_events)
        created_event = next(
            change.event for change in store.boundaries[vid]["K-01/C"] if change.created
        )
        missing_prior = {
            subject: tuple(change for change in changes if change.event == created_event)
            for subject, changes in store.boundaries[vid].items()
        }
        assert not complete(missing_prior, "K-01/C", version.modification_events)
        creation = next(change for change in store.boundaries[vid]["K-01/C"] if change.created)
        assert creation.record_seq is not None
        later_boundary = replace(
            creation, event="missing-later", record_seq=creation.record_seq + 1
        )
        missing_later = {**store.boundaries[vid], "another-subject": (later_boundary,)}
        assert not complete(
            missing_later, "K-01/C", version.modification_events | {"missing-later"}
        )
    if with_modification:
        from erev_engine.trace import reevaluate

        replayed = reevaluate(book.trace)
        for node in book.trace.nodes:
            if node.measure.startswith("fixed_boundary_"):
                assert replayed[node.id] == node.value
        boundary = next(
            node for node in book.trace.nodes if node.measure.startswith("fixed_boundary_change@")
        )
        broken = replace(
            book.trace,
            nodes=tuple(
                replace(node, value="999.00") if node.id == boundary.id else node
                for node in book.trace.nodes
            ),
        )
        with pytest.raises(Problem, match="boundary allocation evidence"):
            history(broken)
        assert (
            sum(item.amount for items in store.boundaries[vid].values() for item in items)
            == modification
        )
    for event, day in estimates:
        if day > entry:
            shares = allocations(book.trace, frozenset({event}))
            assert shares is not None
            store.estimate_event_allocations[vid, event] = shares
    (movement,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    initial = sum(
        Decimal(str(row.columns["allocated_amount"])) / 100 for row in original.obligation_versions
    )
    final = sum(ob.allocated for ob in obligations)
    assert movement.lines["NEW_CONTRACTS"] == initial
    assert movement.lines["VC_ESTIMATE_CHANGES"] == final - initial - modification
    assert movement.lines["MODIFICATIONS"] == modification
    assert movement.lines["CLOSING"] == final
    assert movement.lines["UNEXPLAINED"] == 0

    # Read January from its original allocation, not the latest February amount.
    for period_key, expected in (("FY2026-P01", initial), ("FY2026-P02", final)):
        result = variance_rpo.project(
            bundle,
            book,
            entity_code=bundle.entities[0].code,
            period_key=period_key,
            functional=False,
        )
        assert sum(result.values()) == expected
    nodes = {node.id: node for node in book.trace.nodes}
    january = date(2026, 1, 31)
    for ob in obligations:
        subject = f"{ob.external_id}/{ob.obligation_key}"
        for day, period_key in ((january, "FY2026-P01"), (end, "FY2026-P02")):
            amount = Decimal(nodes[f"fixed_allocation:{subject}:{period_key}"].value)
            cuts.setdefault((vid, day), {})[ob.row_id] = replace(
                cuts[vid, end][ob.row_id],
                fixed_allocation=amount,
                awaiting=amount,
            )
    (january_row,) = rpo.rollforward_lines(store, ranges={eid: (before, january)}, applied={})
    assert january_row.lines["NEW_CONTRACTS"] == january_row.lines["CLOSING"] == initial
    assert january_row.lines["VC_ESTIMATE_CHANGES"] == january_row.lines["UNEXPLAINED"] == 0
    (february_row,) = rpo.rollforward_lines(store, ranges={eid: (january, end)}, applied={})
    assert february_row.lines["OPENING"] == initial
    assert february_row.lines["NEW_CONTRACTS"] == 0
    assert february_row.lines["VC_ESTIMATE_CHANGES"] == final - initial - modification
    assert february_row.lines["MODIFICATIONS"] == modification
    assert february_row.lines["CLOSING"] == final
    assert february_row.lines["UNEXPLAINED"] == 0

    if with_modification and not added:
        # The original cancellation boundary must reproduce every earlier movement.
        termination = replace(
            concession,
            modification_key="K-01/TERM",
            kind="TERMINATION",
            chosen_treatments={},
            treatment_summary=None,
            effective_date=date(2026, 2, 15 if same_day else 28),
            lines=tuple(
                {
                    "obligation_key": key,
                    "action": "REMOVE",
                    "product_code": f"PROD-{key}",
                    "quantity_delta": Decimal(0),
                    "consideration_delta": Decimal(0 if same_day else -20),
                }
                for key in ("A", "B")
            ),
        )
        terminated = replace(
            bundle,
            contracts=tuple(
                replace(c, modifications=(*c.modifications, termination)) for c in bundle.contracts
            ),
            events=tuple(
                cpc_worlds.then(
                    list(bundle.events),
                    "CONTRACT_TERMINATED",
                    termination.effective_date,
                    {
                        "modification_id": termination.modification_key,
                        "termination_kind": "FULL",
                        "refund_amount": Decimal(0 if same_day else 40),
                    },
                    modification_key=termination.modification_key,
                )
            ),
        )
        split_termination = later_amount == "200" and not same_day
        if split_termination:
            first_termination = replace(
                termination,
                modification_key="K-01/TERM-A",
                effective_date=date(2026, 2, 20),
                lines=termination.lines[:1],
                chosen_treatments={"B": "PROSPECTIVE"} if cross_effect else {},
            )
            last_termination = replace(
                termination,
                lines=termination.lines[1:],
                effective_date=date(2026, 3, 28) if across_periods else termination.effective_date,
            )
            events = cpc_worlds.then(
                list(bundle.events),
                "CONTRACT_TERMINATED",
                first_termination.effective_date,
                {
                    "modification_id": first_termination.modification_key,
                    "termination_kind": "PARTIAL",
                    "obligation_keys": ["A"],
                    "refund_amount": Decimal(20),
                },
                modification_key=first_termination.modification_key,
            )
            events = cpc_worlds.then(
                events,
                "CONTRACT_TERMINATED",
                last_termination.effective_date,
                {
                    "modification_id": last_termination.modification_key,
                    "termination_kind": "FULL",
                    "refund_amount": Decimal(20),
                },
                modification_key=last_termination.modification_key,
            )
            terminated = replace(
                terminated,
                events=tuple(events),
                contracts=tuple(
                    replace(
                        c,
                        modifications=tuple(
                            sorted(
                                (*c.modifications, first_termination, last_termination),
                                key=lambda m: m.modification_key,
                            )
                        ),
                    )
                    for c in bundle.contracts
                ),
            )
        termination_event = terminated.events[-1]
        terminated = replace(
            terminated,
            events=tuple(
                sorted(
                    terminated.events,
                    key=lambda event: (event.effective_date, event.record_seq, event.event_key),
                )
            ),
        )
        from erev_engine.bundle import MappingRuleInput

        terminated = replace(
            terminated,
            books=tuple(
                replace(
                    b,
                    account_mapping=replace(
                        b.account_mapping,
                        rules=tuple(
                            sorted(
                                (
                                    *b.account_mapping.rules,
                                    MappingRuleInput(
                                        "REFUND_LIABILITY",
                                        None,
                                        None,
                                        None,
                                        None,
                                        None,
                                        "2110",
                                        {},
                                        0,
                                        0,
                                    ),
                                ),
                                key=lambda rule: (
                                    rule.account_role,
                                    rule.clearing_purpose or "",
                                    rule.account_code,
                                ),
                            )
                        ),
                    ),
                )
                for b in terminated.books
            ),
        )
        terminated_output = compute(terminated)
        terminated_book = terminated_output.books[0]
        if across_periods:
            target_values = {node.id: Decimal(node.value) for node in terminated_book.trace.nodes}
            prefix = "posting_target:K-01/B/NETTING_RECLASS/"
            # Cumulative reclass retains February's CA 20 and March's UR 280 separately.
            assert target_values[prefix + "CONTRACT_ASSET:FY2026-P02"] == 20
            assert target_values[prefix + "CONTRACT_ASSET:FY2026-P03"] == 20
            assert target_values[prefix + "UNBILLED_RECEIVABLE:FY2026-P03"] == 280
            assert target_values[prefix + "CONTRACT_LIABILITY:FY2026-P03"] == -300
            from decimal import localcontext

            from erev_engine.money import DECIMAL_CONTEXT
            from support import intent_totals

            with localcontext(DECIMAL_CONTEXT):
                closed = intent_totals.close_pass(
                    terminated, [terminated_output], "NETTING_RECLASS"
                )
            actual_lines = sorted(
                (
                    intent.entry_kind,
                    line.account_role,
                    line.amount_txn if line.side == "D" else -line.amount_txn,
                )
                for intent in closed.books[0].posting_intents
                if intent.subject_key == "K-01/B" and intent.posting_period_key == "FY2026-P03"
                for line in intent.lines
            )
            assert actual_lines == [
                ("NETTING_RECLASS", "CONTRACT_LIABILITY", -28000),
                ("NETTING_RECLASS", "UNBILLED_RECEIVABLE", 28000),
                ("NETTING_RECLASS_REVERSAL", "CONTRACT_ASSET", -2000),
                ("NETTING_RECLASS_REVERSAL", "CONTRACT_LIABILITY", 2000),
            ]
        later_events = frozenset(event for event, day in estimates if day > entry)
        cancelled_version = replace(
            version,
            causes=frozenset({"CONTRACT_AMENDED", "ESTIMATE_CHANGED", "CONTRACT_TERMINATED"}),
            entries=(),
            estimate_events=later_events,
            cancellation_events=frozenset(
                event.event_key
                for event in terminated.events
                if event.event_type == "CONTRACT_TERMINATED"
            ),
            estimate_order=tuple(
                (event.event_key, event.record_seq)
                for event in terminated.events
                if event.event_key in later_events
            ),
        )
        store.boundaries[vid] = history(terminated_book.trace)
        if cross_effect:
            cross_changes = [
                item
                for changes in store.boundaries[vid].values()
                for item in changes
                if item.kind == "CONTRACT_TERMINATED"
                and item.cancelled_on != item.day
                and item.amount != 0
            ]
            assert len(cross_changes) == 1
            assert cross_changes[0].amount > 0
        shares = allocations(terminated_book.trace, later_events)
        assert shares is not None
        store.estimate_allocations[vid] = shares
        separated = []
        for original_ob in original.obligation_versions:
            subject = original_ob.subject_key
            opening_amount = Decimal(str(original_ob.columns["allocated_amount"])) / 100
            change = rpo._cancelled_changes(store, cancelled_version, subject, opening_amount)
            assert change is not None
            if split_termination:
                assert (
                    rpo._cancelled_changes(
                        replace(store, classify_separate_cancellations=False),
                        cancelled_version,
                        subject,
                        opening_amount,
                    )
                    is None
                )
            if split_termination:
                original_history = store.boundaries[vid]
                for remove_evidence in (False, True):
                    changed = tuple(
                        replace(item, cancellation_stated=False)
                        if remove_evidence
                        else replace(item, amount=Decimal(1))
                        if item.event in cancelled_version.cancellation_events
                        and item.cancelled_on != item.day
                        else item
                        for item in original_history[subject]
                    )
                    store.boundaries[vid] = {**original_history, subject: changed}
                    assert (
                        rpo._cancelled_changes(store, cancelled_version, subject, opening_amount)
                        is None
                    )
                store.boundaries[vid] = original_history
            if same_day:
                assert (
                    rpo._cancelled_changes(
                        replace(store, same_day_cancelled_changes=False),
                        cancelled_version,
                        subject,
                        opening_amount,
                    )
                    is None
                )
                assert (
                    rpo._cancelled_changes(
                        store,
                        replace(cancelled_version, estimate_order=()),
                        subject,
                        opening_amount,
                    )
                    is None
                )
                assert (
                    rpo._cancelled_changes(
                        store,
                        replace(
                            cancelled_version,
                            estimate_order=tuple(
                                (event, termination_event.record_seq + 1) for event in later_events
                            ),
                        ),
                        subject,
                        opening_amount,
                    )
                    is None
                )
            separated.append(change)
            assert (
                rpo._cancelled_changes(store, cancelled_version, subject, opening_amount + 1)
                is None
            )
        assert sum(item[0] for item in separated) == modification
        assert sum(item[1] for item in separated) == final - initial - modification

        # A first retained computation may already contain its later termination.
        # Historical cuts and monthly movements must still use the original dates.
        from erev_api.domain.contracts import to_date

        first_cancelled = replace(cancelled_version, entries=version.entries)
        cancelled_obs = tuple(replace(ob, cancelled=True) for ob in obligations)
        starts = {
            (period.period_key, period.end_date): (period.start_date,)
            for entity in terminated.entities
            for period in entity.periods
        }
        dated_nodes = to_date.nodes_of(terminated_book.trace.nodes, starts=starts)
        retained_rows = []
        for ob, output in zip(cancelled_obs, terminated_book.obligation_versions, strict=True):
            columns = output.columns
            row = {
                **columns,
                "id": ob.row_id,
                "contract_id": cid,
                "trace_nodes": output.trace_nodes,
            }
            for name in (
                "revenue_cum",
                "billed_cum",
                "scheduled_amount",
                "awaiting_trigger_amount",
            ):
                row[name] = Decimal(str(columns[name])) / 100
            row["progress_ratio"] = Decimal(columns["progress_ratio"].numerator) / Decimal(
                columns["progress_ratio"].denominator
            )
            retained_rows.append(row)
        cancelled_cuts = {
            (vid, day): to_date.version_at(
                {"version_no": "FIRST_CANCELLED"},
                retained_rows,
                nodes=dated_nodes,
                external_ids={cid: "K-01"},
                as_of=day,
            ).obligations
            for day in (before, entry, january, date(2026, 2, 28), end)
        }
        cancelled_store = replace(
            store,
            versions={gid: (first_cancelled,)},
            obligations={vid: cancelled_obs},
            chains={cid: (first_cancelled,)},
            cuts=cancelled_cuts,
        )
        if split_termination:
            prior_id = uuid4()
            prior_version = replace(version, id=prior_id, version_no=1)
            later_version = replace(cancelled_version, effective=end, version_no=2)
            prior_obs = tuple(
                replace(
                    ob,
                    version_id=prior_id,
                    cancelled=False,
                    allocated=cancelled_cuts[vid, january][ob.row_id].fixed_allocation,
                )
                for ob in cancelled_obs
            )
            prior_points = {
                ob.row_id: replace(
                    cancelled_cuts[vid, january][ob.row_id], satisfaction_status="UNSATISFIED"
                )
                for ob in prior_obs
            }
            later_store = replace(
                cancelled_store,
                versions={gid: (prior_version, later_version)},
                chains={cid: (prior_version, later_version)},
                obligations={prior_id: prior_obs, vid: cancelled_obs},
                cuts={
                    **cancelled_cuts,
                    **{(prior_id, day): prior_points for day in (before, entry, january, end)},
                },
            )
            (later_result,) = rpo.rollforward_lines(
                later_store, ranges={eid: (january, end)}, applied={}
            )
            assert later_result.lines["OPENING"] == initial
            assert later_result.lines["MODIFICATIONS"] == modification
            assert later_result.lines["VC_ESTIMATE_CHANGES"] == final - initial - modification
            assert later_result.lines["CANCELLATIONS"] == -40
            assert later_result.lines["REVENUE"] == -(final - 40)
            assert later_result.lines["CLOSING"] == later_result.lines["UNEXPLAINED"] == 0
            pending_version = replace(later_version, effective=date(2026, 2, 1))
            pending_store = replace(
                later_store,
                versions={gid: (prior_version, pending_version)},
                chains={cid: (prior_version, pending_version)},
            )
            (pending_result,) = rpo.rollforward_lines(
                pending_store,
                ranges={eid: (january, end)},
                applied={},
            )
            assert pending_result.lines == later_result.lines
            (old_result,) = rpo.rollforward_lines(
                replace(later_store, classify_separate_cancellations=False),
                ranges={eid: (january, end)},
                applied={},
            )
            assert old_result.lines["UNEXPLAINED"] != 0
            if cross_effect:
                (legacy_cross,) = rpo.rollforward_lines(
                    replace(later_store, classify_cancellation_cross_changes=False),
                    ranges={eid: (january, end)},
                    applied={},
                )
                assert legacy_cross.lines["UNEXPLAINED"] != 0
        if across_periods:
            intermediate = date(2026, 2, 28)
            partial_version = replace(later_version, effective=intermediate)
            partial_store = replace(
                later_store,
                versions={gid: (prior_version, partial_version)},
                chains={cid: (prior_version, partial_version)},
                cuts={**later_store.cuts, (prior_id, intermediate): prior_points},
            )
            (mixed_partial,) = rpo.rollforward_lines(
                partial_store, ranges={eid: (january, intermediate)}, applied={}
            )
            assert mixed_partial.lines["OPENING"] == initial
            assert mixed_partial.lines["NEW_CONTRACTS"] == 0
            assert mixed_partial.lines["MODIFICATIONS"] == modification
            assert mixed_partial.lines["VC_ESTIMATE_CHANGES"] == final - initial - modification
            assert mixed_partial.lines["CANCELLATIONS"] == -20
            assert mixed_partial.lines["REVENUE"] == 0
            assert mixed_partial.lines["CLOSING"] == final - 20
            assert mixed_partial.lines["UNEXPLAINED"] == 0
            (legacy_mixed,) = rpo.rollforward_lines(
                replace(partial_store, classify_mixed_continuing_changes=False),
                ranges={eid: (january, intermediate)},
                applied={},
            )
            assert legacy_mixed.lines["UNEXPLAINED"] != 0
            subject = "K-01/B"
            assert rpo._continuing_changes(
                partial_store, partial_version, subject, Decimal(210), intermediate
            ) == (Decimal(40), Decimal(0))
            assert (
                rpo._continuing_changes(
                    partial_store, partial_version, subject, Decimal(211), intermediate
                )
                is None
            )
            for incomplete in (
                replace(partial_store, estimate_allocations={}),
                replace(
                    partial_store,
                    boundaries={
                        vid: {
                            subject: tuple(
                                item
                                for item in partial_store.boundaries[vid][subject]
                                if item.kind != "CONTRACT_AMENDED"
                            )
                        }
                    },
                ),
            ):
                assert (
                    rpo._continuing_changes(
                        incomplete, partial_version, subject, Decimal(210), intermediate
                    )
                    is None
                )
            assert (
                rpo._continuing_changes(
                    partial_store,
                    replace(partial_version, estimate_dates=()),
                    subject,
                    Decimal(210),
                    intermediate,
                )
                is None
            )

        historical = variance_rpo.project(
            terminated,
            terminated_book,
            entity_code=terminated.entities[0].code,
            period_key="FY2026-P01",
            functional=False,
        )
        assert sum(historical.values()) == initial
        historical_rows = rpo.rows_at(
            cancelled_store, as_of={eid: january}, bands=rpo.DEFAULT_BANDS, applied={}
        )
        assert sum(row.total for row in historical_rows) == initial
        assert not rpo.rows_at(
            cancelled_store, as_of={eid: end}, bands=rpo.DEFAULT_BANDS, applied={}
        )
        for start, finish, opening, new, closing in (
            (before, january, 0, initial, initial),
            (before, end, 0, initial, 0),
            (january, end, initial, 0, 0),
        ):
            (result,) = rpo.rollforward_lines(
                cancelled_store, ranges={eid: (start, finish)}, applied={}
            )
            assert result.lines["OPENING"] == opening
            assert result.lines["NEW_CONTRACTS"] == new
            assert result.lines["CLOSING"] == closing
            assert result.lines["MODIFICATIONS"] == (modification if finish == end else 0)
            assert result.lines["VC_ESTIMATE_CHANGES"] == (
                final - initial - modification if finish == end else 0
            )
            if finish == end:
                refund = Decimal(0 if same_day else 40)
                assert result.lines["CANCELLATIONS"] == -refund
                assert result.lines["REVENUE"] == -(final - refund)
            assert result.lines["UNEXPLAINED"] == 0

        if across_periods:
            intermediate = date(2026, 2, 28)
            for start, expected_open, expected_new in ((before, 0, initial), (january, initial, 0)):
                (partial_row,) = rpo.rollforward_lines(
                    cancelled_store, ranges={eid: (start, intermediate)}, applied={}
                )
                assert partial_row.lines["OPENING"] == expected_open
                assert partial_row.lines["NEW_CONTRACTS"] == expected_new
                assert partial_row.lines["MODIFICATIONS"] == modification
                assert partial_row.lines["VC_ESTIMATE_CHANGES"] == final - initial - modification
                assert partial_row.lines["CANCELLATIONS"] == -20
                assert partial_row.lines["REVENUE"] == 0
                assert partial_row.lines["CLOSING"] == final - 20
                assert partial_row.lines["UNEXPLAINED"] == 0
                (legacy_partial,) = rpo.rollforward_lines(
                    replace(cancelled_store, classify_continuing_cancellations=False),
                    ranges={eid: (start, intermediate)},
                    applied={},
                )
                assert legacy_partial.lines != partial_row.lines
            (march,) = rpo.rollforward_lines(
                cancelled_store, ranges={eid: (intermediate, end)}, applied={}
            )
            assert march.lines["OPENING"] == final - 20
            assert march.lines["CANCELLATIONS"] == -20
            assert march.lines["REVENUE"] == -(final - 40)
            assert all(
                march.lines[key] == 0
                for key in (
                    "NEW_CONTRACTS",
                    "MODIFICATIONS",
                    "VC_ESTIMATE_CHANGES",
                    "CLOSING",
                    "UNEXPLAINED",
                )
            )
            subject = "K-01/B"
            original_history = cancelled_store.boundaries[vid]
            missing_state = replace(
                cancelled_store,
                boundaries={
                    vid: {
                        **original_history,
                        subject: tuple(
                            replace(item, cancellation_stated=False)
                            for item in original_history[subject]
                        ),
                    }
                },
            )
            assert (
                rpo._continuing_cancellations(
                    missing_state, first_cancelled, subject, january, intermediate
                )
                is None
            )

        # A later retained memo must not erase or duplicate that first cancellation.
        later_id = uuid4()
        retained = replace(
            first_cancelled,
            id=later_id,
            version_no=2,
            effective=end,
            entries=(),
            causes=frozenset({"MEMO_ADDED"}),
            modification_events=frozenset(),
            estimate_events=frozenset(),
            cancellation_events=frozenset(),
        )
        later_obs = tuple(replace(ob, version_id=later_id) for ob in cancelled_obs)
        continued = replace(
            cancelled_store,
            versions={gid: (first_cancelled, retained)},
            chains={cid: (first_cancelled, retained)},
            obligations={vid: cancelled_obs, later_id: later_obs},
            cuts={
                **cancelled_cuts,
                **{(later_id, day): points for (source, day), points in cancelled_cuts.items()},
            },
            boundaries={**cancelled_store.boundaries, later_id: cancelled_store.boundaries[vid]},
        )
        (continued_row,) = rpo.rollforward_lines(continued, ranges={eid: (before, end)}, applied={})
        (original_row,) = rpo.rollforward_lines(
            cancelled_store, ranges={eid: (before, end)}, applied={}
        )
        assert continued_row.lines == original_row.lines

        (continued_month,) = rpo.rollforward_lines(
            continued, ranges={eid: (january, end)}, applied={}
        )
        (original_month,) = rpo.rollforward_lines(
            cancelled_store, ranges={eid: (january, end)}, applied={}
        )
        assert continued_month.lines == original_month.lines

        # A retained version before the original termination must not erase the
        # original pre-termination amounts or settle the cancellation prematurely.
        if not same_day:
            intermediate_version = replace(retained, effective=date(2026, 2, 1))
            intervening = replace(
                continued,
                versions={gid: (first_cancelled, intermediate_version)},
                chains={cid: (first_cancelled, intermediate_version)},
            )
            for start in (before, january):
                (intervening_row,) = rpo.rollforward_lines(
                    intervening, ranges={eid: (start, end)}, applied={}
                )
                (unchanged_row,) = rpo.rollforward_lines(
                    cancelled_store, ranges={eid: (start, end)}, applied={}
                )
                assert intervening_row.lines == unchanged_row.lines
                (legacy_intervening,) = rpo.rollforward_lines(
                    replace(intervening, classify_pretermination_versions=False),
                    ranges={eid: (start, end)},
                    applied={},
                )
                assert legacy_intervening.lines != unchanged_row.lines

        (legacy_month,) = rpo.rollforward_lines(
            replace(continued, classify_cancelled_chains=False),
            ranges={eid: (january, end)},
            applied={},
        )
        assert legacy_month.lines != original_month.lines

        # Re-entry admits only the new remainder; pre-cancellation revenue is not
        # recognized a second time and the prior termination remains on its own line.
        reopened = replace(
            retained, causes=frozenset({"CONTRACT_ACTIVATED"}), entries=((cid, end),)
        )
        reopened_cuts = dict(continued.cuts)
        reopened_obs = []
        for ob in later_obs:
            amount = cancelled_cuts[vid, end][ob.row_id].revenue + Decimal(30)
            reopened_obs.append(replace(ob, cancelled=False, allocated=amount))
        for day in (before, entry, january, end):
            reopened_cuts[later_id, day] = {
                ob.row_id: replace(
                    cancelled_cuts[vid, day][ob.row_id],
                    fixed_allocation=ob.allocated,
                    awaiting=Decimal(30),
                    satisfaction_status="PARTIALLY_SATISFIED",
                )
                for ob in reopened_obs
            }
        reentry_store = replace(
            continued,
            versions={gid: (first_cancelled, reopened)},
            chains={cid: (first_cancelled, reopened)},
            obligations={vid: cancelled_obs, later_id: tuple(reopened_obs)},
            cuts=reopened_cuts,
        )
        for start in (before, january):
            (reentered,) = rpo.rollforward_lines(
                reentry_store, ranges={eid: (start, end)}, applied={}
            )
            (prior,) = rpo.rollforward_lines(
                cancelled_store, ranges={eid: (start, end)}, applied={}
            )
            expected = dict(prior.lines)
            expected["NEW_CONTRACTS"] += 60
            expected["CLOSING"] = Decimal(60)
            assert reentered.lines == expected


@pytest.mark.parametrize("first_entry", [False, True])
@pytest.mark.parametrize("realized", [80, 150])
@pytest.mark.parametrize("revenue", [0, 100])
def test_one_computation_separates_realized_fees_from_cancellation(
    first_entry: bool, realized: int, revenue: int
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt
    from erev_api.domain.reports.rpo_boundary_changes import Change

    vid, oid, cid, eid, gid = (uuid4() for _ in range(5))
    entry, january, end = date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 28)
    before = date(2025, 12, 31) if first_entry else january
    version = rpo._Version(
        vid,
        gid,
        1,
        True,
        entry,
        frozenset(
            {
                "CONTRACT_ACTIVATED",
                "CONTRACT_AMENDED",
                "ESTIMATE_CHANGED",
                "USAGE_REPORTED",
                "CONTRACT_TERMINATED",
            }
        ),
        entries=((cid, entry),),
        modification_events=frozenset({"mod"}),
        estimate_events=frozenset({"estimate"}),
        estimate_dates=(("estimate", date(2026, 2, 10)),),
        cancellation_events=frozenset({"cancel"}),
    )
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        end,
        entry,
        Decimal(250 + realized),
        True,
    )
    empty = ObligationAt(
        *(Decimal(0) for _ in range(8)),
        "CANCELLED",
        None,
        None,
        realised_traced=True,
        fixed_allocation=Decimal(200),
    )
    opening = replace(
        empty,
        revenue=Decimal(40),
        awaiting=Decimal(260),
        realised=Decimal(100),
        realised_stored=Decimal(realized),
    )
    closing = replace(
        empty,
        revenue=Decimal(revenue),
        fixed_allocation=Decimal(revenue),
        realised=Decimal(realized),
        realised_stored=Decimal(realized),
    )
    store = rpo.Store(
        {gid: (version,)},
        {vid: (ob,)},
        {cid: (version,)},
        {
            (vid, date(2025, 12, 31)): {oid: empty},
            (vid, entry): {oid: opening},
            (vid, january): {oid: opening},
            (vid, end): {oid: closing},
        },
        boundaries={
            vid: {
                "C/O": (
                    Change(
                        date(2026, 2, 1),
                        "mod",
                        "CONTRACT_AMENDED",
                        Decimal(30),
                        record_seq=2,
                        before=Decimal(200),
                        after=Decimal(230),
                    ),
                    Change(
                        end,
                        "cancel",
                        "CONTRACT_TERMINATED",
                        Decimal(-250),
                        record_seq=4,
                        before=Decimal(250),
                        after=Decimal(0),
                        cancelled_on=end,
                    ),
                )
            }
        },
        estimate_allocations={vid: {"C/O": Decimal(20)}},
        estimate_event_allocations={(vid, "estimate"): {"C/O": Decimal(20)}},
    )
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["OPENING"] == (0 if first_entry else 260)
    assert result.lines["NEW_CONTRACTS"] == (200 if first_entry else 0)
    assert result.lines["MODIFICATIONS"] == 30
    assert result.lines["VC_ESTIMATE_CHANGES"] == 20 + realized - (0 if first_entry else 100)
    assert result.lines["REVENUE"] == -revenue + (0 if first_entry else 40)
    assert result.lines["CANCELLATIONS"] == -(250 + realized - revenue)
    assert result.lines["CLOSING"] == result.lines["UNEXPLAINED"] == 0
    (legacy,) = rpo.rollforward_lines(
        replace(store, classify_batch_cancelled_usage=False),
        ranges={eid: (before, end)},
        applied={},
    )
    assert legacy.lines != result.lines

    for fee_correction in (Decimal(-10), Decimal(10)):
        retained_id = uuid4()
        retained = replace(
            version,
            id=retained_id,
            version_no=2,
            effective=end,
            causes=frozenset({"USAGE_REPORTED"}),
            entries=(),
            modification_events=frozenset(),
            estimate_events=frozenset(),
            cancellation_events=frozenset(),
        )
        retained_ob = replace(ob, version_id=retained_id)
        retained_cuts = {(retained_id, day): points for (source, day), points in store.cuts.items()}
        retained_cuts[retained_id, end] = {
            oid: replace(
                closing,
                realised=closing.realised + fee_correction,
                revenue=closing.revenue + fee_correction,
            )
        }
        continued = replace(
            store,
            versions={gid: (version, retained)},
            chains={cid: (version, retained)},
            obligations={vid: (ob,), retained_id: (retained_ob,)},
            cuts={**store.cuts, **retained_cuts},
            boundaries={**store.boundaries, retained_id: store.boundaries[vid]},
        )
        (updated,) = rpo.rollforward_lines(continued, ranges={eid: (before, end)}, applied={})
        expected = dict(result.lines)
        expected["VC_ESTIMATE_CHANGES"] += fee_correction
        expected["REVENUE"] -= fee_correction
        assert updated.lines == expected
        (legacy_chain,) = rpo.rollforward_lines(
            replace(continued, classify_cancelled_usage_chains=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy_chain.lines != expected
        continued.cuts[retained_id, end] = {
            oid: replace(retained_cuts[retained_id, end][oid], realised_traced=False)
        }
        (missing,) = rpo.rollforward_lines(continued, ranges={eid: (before, end)}, applied={})
        assert missing.lines != expected

    for intermediate in (False, True):
        reopened_id = uuid4()
        reopened = replace(
            version,
            id=reopened_id,
            version_no=3,
            effective=end,
            causes=frozenset({"CONTRACT_ACTIVATED"}),
            entries=((cid, end),),
            modification_events=frozenset(),
            estimate_events=frozenset(),
            cancellation_events=frozenset(),
        )
        fee_correction = Decimal(10 if intermediate else 0)
        new_fee = Decimal(realized) + fee_correction + 10
        new_revenue = Decimal(revenue) + fee_correction + 20
        remainder = Decimal(80) + new_fee - new_revenue
        reopened_ob = replace(
            ob, version_id=reopened_id, cancelled=False, allocated=Decimal(80) + new_fee
        )
        reopened_cuts = {(reopened_id, day): points for (source, day), points in store.cuts.items()}
        reopened_cuts[reopened_id, end] = {
            oid: replace(
                closing,
                fixed_allocation=Decimal(80),
                realised=new_fee,
                revenue=new_revenue,
                awaiting=remainder,
                satisfaction_status="PARTIALLY_SATISFIED",
            )
        }
        chain = (version, reopened)
        chain_obligations = {**store.obligations, reopened_id: (reopened_ob,)}
        chain_cuts = {**store.cuts, **reopened_cuts}
        chain_boundaries = dict(store.boundaries)
        if intermediate:
            memo_id = uuid4()
            memo = replace(
                reopened, id=memo_id, version_no=2, entries=(), causes=frozenset({"USAGE_REPORTED"})
            )
            chain = (version, memo, reopened)
            chain_obligations[memo_id] = (replace(ob, version_id=memo_id),)
            chain_cuts.update(
                {(memo_id, day): points for (source, day), points in store.cuts.items()}
            )
            chain_cuts[memo_id, end] = {
                oid: replace(
                    closing,
                    realised=Decimal(realized) + fee_correction,
                    revenue=Decimal(revenue) + fee_correction,
                )
            }
            chain_boundaries[memo_id] = store.boundaries[vid]
        reentry_store = replace(
            store,
            versions={gid: chain},
            chains={cid: chain},
            obligations=chain_obligations,
            cuts=chain_cuts,
            boundaries=chain_boundaries,
        )
        (reentered,) = rpo.rollforward_lines(reentry_store, ranges={eid: (before, end)}, applied={})
        expected = dict(result.lines)
        expected["NEW_CONTRACTS"] += remainder
        expected["CLOSING"] = remainder
        expected["VC_ESTIMATE_CHANGES"] += fee_correction
        expected["REVENUE"] -= fee_correction
        assert reentered.lines == expected
        (legacy_reentry,) = rpo.rollforward_lines(
            replace(reentry_store, classify_batch_usage_reentry=False),
            ranges={eid: (before, end)},
            applied={},
        )
        assert legacy_reentry.lines != expected


@pytest.mark.parametrize("refund", [0, 40])
@pytest.mark.parametrize("amended", [False, True])
@pytest.mark.parametrize("estimated", [False, True])
def test_original_same_day_activation_and_cancellation_keeps_movements(
    refund: int, amended: bool, estimated: bool
) -> None:
    from erev_api.domain.contracts import to_date
    from erev_api.domain.reports.rpo_boundary_changes import history
    from erev_engine.bundle import MappingRuleInput
    from support import cpc_worlds

    entry, before, end = date(2026, 1, 1), date(2025, 12, 31), date(2026, 1, 31)
    initial_estimate = worlds.element("100", keys=["A"])
    base = worlds.targeted_world(estimates=[initial_estimate] if estimated else [])
    initial = 300 if estimated else 100
    if amended:
        modification = replace(
            cpc_worlds.concession("-20", entry, key="A"),
            modification_key="K-01/MOD-1",
            status="APPLIED",
            price_change_amount=None,
            questionnaire={},
            chosen_treatments={"A": "PROSPECTIVE", "B": "PROSPECTIVE"},
            treatment_summary="PROSPECTIVE",
            lines=(
                {
                    "obligation_key": "A",
                    "action": "CHANGE",
                    "product_code": "PROD-A",
                    "quantity_delta": Decimal(0),
                    "consideration_delta": Decimal(-20),
                },
            ),
        )
        base = replace(
            base,
            contracts=tuple(replace(c, modifications=(modification,)) for c in base.contracts),
            events=tuple(
                cpc_worlds.amended(list(base.events), modification, modification.chosen_treatments)
            ),
        )
    if estimated:
        base = worlds.with_changes(base, [worlds.later_version(initial_estimate, 2, entry, "200")])
    termination = replace(
        cpc_worlds.concession("0", entry, key="A"),
        modification_key="K-01/TERM",
        kind="TERMINATION",
        status="APPLIED",
        price_change_amount=None,
        questionnaire={},
        chosen_treatments={},
        treatment_summary=None,
        lines=tuple(
            {
                "obligation_key": key,
                "action": "REMOVE",
                "product_code": f"PROD-{key}",
                "quantity_delta": Decimal(0),
                "consideration_delta": Decimal(-refund) / 2,
            }
            for key in ("A", "B")
        ),
    )
    bundle = replace(
        base,
        contracts=tuple(
            replace(c, modifications=(*c.modifications, termination)) for c in base.contracts
        ),
        events=tuple(
            cpc_worlds.then(
                list(base.events),
                "CONTRACT_TERMINATED",
                entry,
                {
                    "modification_id": termination.modification_key,
                    "termination_kind": "FULL",
                    "refund_amount": Decimal(refund),
                },
                modification_key=termination.modification_key,
            )
        ),
        books=tuple(
            replace(
                b,
                account_mapping=replace(
                    b.account_mapping,
                    rules=tuple(
                        sorted(
                            (
                                *b.account_mapping.rules,
                                MappingRuleInput(
                                    "REFUND_LIABILITY",
                                    None,
                                    None,
                                    None,
                                    None,
                                    None,
                                    "2110",
                                    {},
                                    0,
                                    0,
                                ),
                            ),
                            key=lambda rule: (
                                rule.account_role,
                                rule.clearing_purpose or "",
                                rule.account_code,
                            ),
                        )
                    ),
                ),
            )
            for b in base.books
        ),
    )
    book = compute(bundle).books[0]
    vid, cid, eid, gid = (uuid4() for _ in range(4))
    version = rpo._Version(
        vid,
        gid,
        1,
        True,
        entry,
        frozenset(event.event_type for event in bundle.events),
        entries=((cid, entry),),
        entry_order=(
            (
                cid,
                next(e.record_seq for e in bundle.events if e.event_type == "CONTRACT_ACTIVATED"),
            ),
        ),
        estimate_events=frozenset(
            e.event_key for e in bundle.events if e.event_type == "ESTIMATE_CHANGED"
        ),
        estimate_dates=tuple(
            (e.event_key, e.effective_date)
            for e in bundle.events
            if e.event_type == "ESTIMATE_CHANGED"
        ),
        estimate_order=tuple(
            (e.event_key, e.record_seq) for e in bundle.events if e.event_type == "ESTIMATE_CHANGED"
        ),
        modification_events=frozenset(
            e.event_key for e in bundle.events if e.event_type == "CONTRACT_AMENDED"
        ),
    )
    obligations, rows = [], []
    for output in book.obligation_versions:
        columns = output.columns
        oid = uuid4()
        assert columns["satisfaction_status"] == "CANCELLED"
        obligations.append(
            rpo._Ob(
                oid,
                vid,
                oid,
                cid,
                "K-01",
                str(columns["obligation_key"]),
                "Service",
                None,
                None,
                None,
                eid,
                "E",
                "USD",
                "POINT_IN_TIME",
                end,
                entry,
                Decimal(str(columns["allocated_amount"])) / 100,
                True,
            )
        )
        row = {**columns, "id": oid, "contract_id": cid, "trace_nodes": output.trace_nodes}
        for field in ("revenue_cum", "billed_cum", "scheduled_amount", "awaiting_trigger_amount"):
            row[field] = Decimal(str(columns[field])) / 100
        ratio = columns["progress_ratio"]
        row["progress_ratio"] = Decimal(ratio.numerator) / Decimal(ratio.denominator)
        rows.append(row)
    nodes = to_date.nodes_of(
        book.trace.nodes,
        starts={
            (p.period_key, p.end_date): (p.start_date,) for e in bundle.entities for p in e.periods
        },
    )
    store = rpo.Store(
        {gid: (version,)},
        {vid: tuple(obligations)},
        {cid: (version,)},
        {
            (vid, day): to_date.version_at(
                {"version_no": "SAME_DAY"}, rows, nodes=nodes, external_ids={cid: "K-01"}, as_of=day
            ).obligations
            for day in (before, entry, end)
        },
        boundaries={vid: history(book.trace)},
    )
    from erev_api.domain.reports.rpo_estimate_changes import at_inception

    for event in version.estimate_events:
        assert at_inception(book.trace, event)
        store.inception_estimate_events.add((vid, event))
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["NEW_CONTRACTS"] == initial
    assert result.lines["REVENUE"] == -(initial - (20 if amended else 0) - refund)
    assert result.lines["MODIFICATIONS"] == (-20 if amended else 0)
    assert result.lines["VC_ESTIMATE_CHANGES"] == 0
    if estimated:
        for unsupported in (
            replace(store, classify_same_day_entry_estimates=False),
            replace(store, inception_estimate_events=set()),
        ):
            (old_estimate,) = rpo.rollforward_lines(
                unsupported, ranges={eid: (before, end)}, applied={}
            )
            assert old_estimate.lines["NEW_CONTRACTS"] == 0
    if amended:
        for unsupported in (
            replace(store, classify_same_day_entry_modifications=False),
            replace(
                store,
                versions={gid: (replace(version, entry_order=((cid, 9999),)),)},
                chains={cid: (replace(version, entry_order=((cid, 9999),)),)},
            ),
            replace(
                store,
                versions={gid: (replace(version, entry_order=()),)},
                chains={cid: (replace(version, entry_order=()),)},
            ),
        ):
            (old_entry,) = rpo.rollforward_lines(
                unsupported, ranges={eid: (before, end)}, applied={}
            )
            assert old_entry.lines["NEW_CONTRACTS"] == 0
    assert result.lines["CANCELLATIONS"] == -refund
    assert result.lines["OPENING"] == result.lines["CLOSING"] == result.lines["UNEXPLAINED"] == 0
    assert not rpo.rows_at(store, as_of={eid: end}, bands=rpo.DEFAULT_BANDS, applied={})
    (legacy,) = rpo.rollforward_lines(
        replace(store, classify_same_day_entry_cancellation=False),
        ranges={eid: (before, end)},
        applied={},
    )
    assert legacy.lines["NEW_CONTRACTS"] == 0
    # Later retained versions must not suppress original same-day gross movements.
    for reenter in (False, True):
        later_id = uuid4()
        later = replace(
            version,
            id=later_id,
            version_no=2,
            effective=end,
            causes=frozenset({"CONTRACT_ACTIVATED" if reenter else "MEMO_ADDED"}),
            entries=((cid, end),) if reenter else (),
        )
        later_obligations = tuple(
            replace(
                ob,
                version_id=later_id,
                cancelled=not reenter,
                allocated=store.cuts[vid, end][ob.row_id].revenue + Decimal(30)
                if reenter
                else ob.allocated,
            )
            for ob in obligations
        )
        later_cuts = {
            (later_id, day): {
                ob.row_id: replace(
                    store.cuts[vid, day][ob.row_id],
                    fixed_allocation=ob.allocated,
                    awaiting=Decimal(30),
                    satisfaction_status="PARTIALLY_SATISFIED",
                )
                if reenter
                else store.cuts[vid, day][ob.row_id]
                for ob in later_obligations
            }
            for day in (before, entry, end)
        }
        chained = replace(
            store,
            versions={gid: (version, later)},
            chains={cid: (version, later)},
            obligations={vid: tuple(obligations), later_id: later_obligations},
            cuts={**store.cuts, **later_cuts},
            boundaries={**store.boundaries, later_id: store.boundaries[vid]},
        )
        (chained_result,) = rpo.rollforward_lines(chained, ranges={eid: (before, end)}, applied={})
        expected = {**result.lines}
        if reenter:
            expected["NEW_CONTRACTS"] += 60
            expected["CLOSING"] = Decimal(60)
        assert chained_result.lines == expected
        (old_chain,) = rpo.rollforward_lines(
            replace(chained, classify_same_day_entry_chains=False),
            ranges={eid: (before, end)},
            applied={},
        )
        if not reenter or refund:
            assert old_chain.lines["NEW_CONTRACTS"] != expected["NEW_CONTRACTS"]
        (missing_boundary,) = rpo.rollforward_lines(
            replace(chained, boundaries={}),
            ranges={eid: (before, end)},
            applied={},
        )
        if not reenter or refund:
            assert missing_boundary.lines["NEW_CONTRACTS"] != expected["NEW_CONTRACTS"]
    exempt = replace(
        store,
        obligations={
            vid: tuple(replace(ob, recognition_method="RIGHT_TO_INVOICE") for ob in obligations)
        },
    )
    assert not rpo.rollforward_lines(
        exempt, ranges={eid: (before, end)}, applied={eid: frozenset({"POL-198"})}
    )


@pytest.mark.parametrize("realized", [80, 150])
@pytest.mark.parametrize("revenue", [0, 100])
@pytest.mark.parametrize("amended", [False, True])
def test_same_day_entry_usage_and_termination_preserve_gross_movements(
    realized: int, revenue: int, amended: bool
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt
    from erev_api.domain.reports.rpo_boundary_changes import Change

    vid, oid, cid, eid, gid = (uuid4() for _ in range(5))
    entry, before, end = date(2026, 1, 1), date(2025, 12, 31), date(2026, 1, 31)
    version = rpo._Version(
        vid,
        gid,
        1,
        True,
        entry,
        frozenset({"CONTRACT_ACTIVATED", "USAGE_REPORTED", "CONTRACT_TERMINATED"}),
        entries=((cid, entry),),
        entry_order=((cid, 1),),
        cancellation_events=frozenset({"cancel"}),
    )
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Service",
        None,
        None,
        None,
        eid,
        "E",
        "USD",
        "POINT_IN_TIME",
        end,
        entry,
        Decimal(100 + realized),
        True,
    )
    empty = ObligationAt(
        *(Decimal(0) for _ in range(8)),
        "CANCELLED",
        None,
        None,
        realised_traced=True,
        fixed_allocation=Decimal(100),
    )
    closing = replace(
        empty,
        revenue=Decimal(revenue),
        realised=Decimal(realized),
        realised_stored=Decimal(realized),
        fixed_allocation=Decimal(revenue),
    )
    store = rpo.Store(
        {gid: (version,)},
        {vid: (ob,)},
        {cid: (version,)},
        {(vid, before): {oid: empty}, (vid, entry): {oid: closing}, (vid, end): {oid: closing}},
        boundaries={
            vid: {
                "C/O": (
                    Change(
                        entry,
                        "cancel",
                        "CONTRACT_TERMINATED",
                        Decimal(-100),
                        record_seq=3,
                        before=Decimal(100),
                        after=Decimal(0),
                        cancelled_on=entry,
                    ),
                )
            }
        },
    )
    if amended:
        version = replace(
            version,
            causes=version.causes | {"CONTRACT_AMENDED"},
            modification_events=frozenset({"mod"}),
        )
        store.versions[gid] = store.chains[cid] = (version,)
        terminal = store.boundaries[vid]["C/O"][0]
        store.boundaries[vid] = {
            "C/O": (
                Change(
                    entry,
                    "mod",
                    "CONTRACT_AMENDED",
                    Decimal(30),
                    record_seq=2,
                    before=Decimal(100),
                    after=Decimal(130),
                ),
                replace(terminal, before=Decimal(130), amount=Decimal(-130)),
            )
        }
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["NEW_CONTRACTS"] == 100
    assert result.lines["VC_ESTIMATE_CHANGES"] == realized
    assert result.lines["CANCELLATIONS"] == -(100 + (30 if amended else 0) + realized - revenue)
    assert result.lines["REVENUE"] == -revenue
    assert result.lines["MODIFICATIONS"] == (30 if amended else 0)
    assert result.lines["OPENING"] == result.lines["CLOSING"] == result.lines["UNEXPLAINED"] == 0
    for unsupported in (
        replace(store, classify_same_day_entry_usage=False),
        replace(store, classify_batch_cancelled_usage=False),
        replace(
            store,
            cuts={
                **store.cuts,
                (vid, end): {
                    oid: replace(closing, realised_traced=False),
                },
            },
        ),
    ):
        (legacy,) = rpo.rollforward_lines(unsupported, ranges={eid: (before, end)}, applied={})
        assert legacy.lines["NEW_CONTRACTS"] == 0

    # A later retained usage correction changes VC and cancellation equally,
    # without erasing or repeating the first admission or amendment.
    later_id = uuid4()
    later = replace(
        version,
        id=later_id,
        version_no=2,
        effective=end,
        causes=frozenset({"USAGE_REPORTED"}),
        entries=(),
        modification_events=frozenset(),
    )
    correction = replace(
        closing, realised=Decimal(realized + 10), realised_stored=Decimal(realized + 10)
    )
    retained = replace(
        store,
        versions={gid: (version, later)},
        chains={cid: (version, later)},
        obligations={vid: (ob,), later_id: (replace(ob, version_id=later_id),)},
        boundaries={**store.boundaries, later_id: store.boundaries[vid]},
        cuts={
            **store.cuts,
            **{
                (later_id, day): {oid: empty if day == before else correction}
                for day in (before, entry, end)
            },
        },
    )
    (corrected,) = rpo.rollforward_lines(retained, ranges={eid: (before, end)}, applied={})
    expected = dict(result.lines)
    expected["VC_ESTIMATE_CHANGES"] += 10
    expected["CANCELLATIONS"] -= 10
    assert corrected.lines == expected
