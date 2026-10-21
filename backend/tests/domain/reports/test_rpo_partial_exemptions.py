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


@pytest.mark.parametrize("realised", [False, True])
@pytest.mark.parametrize("restated,revenue", [(40, 40), (40, 50), (45, 50), (40, 0)])
def test_terminal_cancellation_removes_remaining_rpo_not_recognized_revenue(
    restated: int, revenue: int, realised: bool
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
    (movement,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert movement.lines["OPENING"] == 60
    assert movement.lines["CANCELLATIONS"] == -(100 - revenue)
    assert movement.lines["REVENUE"] == -(revenue - restated)
    assert movement.lines["LATE_EVENTS"] == -(restated - 40)
    assert movement.lines["CLOSING"] == movement.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize("repeated", [False, True])
@pytest.mark.parametrize("start_after_cancellation", [False, True])
def test_reentry_uses_remaining_balance_and_segment_revenue(
    repeated: bool, start_after_cancellation: bool
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
            True,
            effective,
            frozenset({"CONTRACT_TERMINATED" if cancelled else "CONTRACT_ACTIVATED"}),
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
            cancelled,
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
    chain = tuple(versions)
    store = rpo.Store({gid: chain}, obligations, {cid: chain}, cuts)
    (result,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert result.lines["OPENING"] == (0 if start_after_cancellation else 60)
    assert result.lines["CANCELLATIONS"] == (
        (0 if start_after_cancellation else -55) + (-40 if repeated else 0)
    )
    assert result.lines["NEW_CONTRACTS"] == (80 if repeated else 50)
    assert result.lines["REVENUE"] == (
        (0 if start_after_cancellation else -5) + (-20 if repeated else -10)
    )
    assert result.lines["LATE_EVENTS"] == 0
    assert result.lines["CLOSING"] == 100 - final_revenue
    assert result.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize(
    "closing,estimate,modification", [(150, 20, 30), (100, 20, -20), (90, -20, 10)]
)
def test_mixed_modification_and_estimate_uses_retained_event_shares(
    closing: int, estimate: int, modification: int
) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt

    vid, next_vid, oid, cid, eid, gid = (uuid4() for _ in range(6))
    before, end = date(2026, 1, 31), date(2026, 2, 28)
    first = rpo._Version(vid, gid, 1, True, date(2026, 1, 1), frozenset())
    second = rpo._Version(
        next_vid, gid, 2, True, end, frozenset({"CONTRACT_AMENDED", "ESTIMATE_CHANGED"})
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
        {vid: (old,), next_vid: (new,)},
        {cid: (first, second)},
        {
            (vid, before): {oid: at},
            (vid, end): {oid: at},
            (next_vid, before): {oid: at},
            (next_vid, end): {oid: replace(at, awaiting=Decimal(closing))},
        },
    )
    (unknown,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert unknown.lines["UNEXPLAINED"] == closing - 100
    assert unknown.lines["MODIFICATIONS"] == unknown.lines["VC_ESTIMATE_CHANGES"] == 0
    store.estimate_allocations[next_vid] = {"C/O": Decimal(estimate)}
    (known,) = rpo.rollforward_lines(store, ranges={eid: (before, end)}, applied={})
    assert known.lines["VC_ESTIMATE_CHANGES"] == estimate
    assert known.lines["MODIFICATIONS"] == modification
    assert known.lines["UNEXPLAINED"] == 0


@pytest.mark.parametrize("later_amount", ["200", "-50"])
def test_first_entry_separates_later_original_estimate_events(later_amount: str) -> None:
    from erev_api.domain.contracts.to_date import ObligationAt
    from erev_api.domain.reports.rpo_estimate_changes import allocations

    targeted = worlds.element("100", keys=["A"])
    base = worlds.targeted_world(estimates=[targeted])
    original = compute(base).books[0]
    bundle = worlds.with_changes(
        base,
        [worlds.later_version(targeted, 2, date(2026, 2, 1), later_amount)],
        memo_on=date(2026, 2, 28),
    )
    book = compute(bundle).books[0]
    vid, cid, eid, gid = (uuid4() for _ in range(4))
    entry, before, end = date(2026, 1, 1), date(2025, 12, 31), date(2026, 2, 28)
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
    )
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
    assert movement.lines["VC_ESTIMATE_CHANGES"] == final - initial
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
    assert february_row.lines["VC_ESTIMATE_CHANGES"] == final - initial
    assert february_row.lines["CLOSING"] == final
    assert february_row.lines["UNEXPLAINED"] == 0
