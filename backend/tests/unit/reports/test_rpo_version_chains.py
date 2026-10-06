"""The versions a contract is read from (item RPT-FORMER-GROUP-VERSIONS-1; ``rpo.chains_of``;
04 T-CON-04; ENGINE_SPEC S02-R-09, S02-R-10; ENGINE_SPEC_B S15-R-08, S15-R-12, S15-R-24).

Two orders of one customer, each computed in its own group and then combined by the approved
command (PRD WLD-K-09 ``SF-ORD-10417`` 108,000.00 over 1,096 days and ``SF-ORD-10418`` 48,000.00
over 365 days, both from 01 Sep 2026; combined on 12 Sep 2026, re-allocated 117,000.00 and
39,000.00). Before, the versions were read group by group, and a former group keeps its last
version: RPO stated each member twice — 218,841.25 and 79,849.31 at 30 Sep 2026 — and the
rollforward ``NEW_CONTRACTS`` 312,000.00 for 156,000.00 of contracts, measured through the
product.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from erev_api.domain.contracts.to_date import ObligationAt
from erev_api.domain.reports.builders import rpo
from erev_api.domain.reports.builders.rpo import Membership, Store, _Ob, _Version

ENTITY = UUID(int=1)
FIRST, SECOND = UUID(int=11), UUID(int=12)  # the contracts
OWN_FIRST, OWN_SECOND, COMBINED = UUID(int=21), UUID(int=22), UUID(int=23)  # the groups
FIRST_O1, SECOND_O1 = UUID(int=31), UUID(int=32)  # the obligations
BOOKED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
JOINED = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
LEFT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
AUGUST_31, SEPTEMBER_30, OCTOBER_31 = date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31)
SEPTEMBER_5 = date(2026, 9, 5)
RANGE = {ENTITY: (AUGUST_31, SEPTEMBER_30)}
NOTHING_APPLIED: dict[UUID, frozenset[str]] = {}


def version(
    number: int, group: UUID, no: int, effective: date, known: datetime, *causes: str
) -> _Version:
    return _Version(
        id=UUID(int=100 + number),
        group_id=group,
        version_no=no,
        included=True,
        effective=effective,
        causes=frozenset(causes),
        known_at=known,
    )


def obligation(
    of: _Version,
    contract: UUID,
    obligation_id: UUID,
    external_id: str,
    allocated: str,
    *,
    september: str,
    end: date,
) -> _Ob:
    """One ratable obligation: the revenue of September 2026 and the rest at its end date."""
    rest = Decimal(allocated) - Decimal(september)
    return _Ob(
        row_id=UUID(int=of.id.int * 1000 + obligation_id.int),
        version_id=of.id,
        obligation_id=obligation_id,
        contract_id=contract,
        external_id=external_id,
        obligation_key="O1",
        product_name="Seats, monthly",
        product_family=None,
        customer_name="Orrin Vale Architects LLP (Demo)",
        customer_segment=None,
        entity_id=ENTITY,
        entity_code="AVM-US",
        currency="USD",
        recognition_method="TIME_ELAPSED",
        end_date=end,
        inception=date(2026, 9, 1),
        allocated=Decimal(allocated),
        cancelled=False,
        lines=[
            (
                UUID(int=of.id.int * 1000 + obligation_id.int + 500),
                SEPTEMBER_30,
                Decimal(september),
            ),
            (UUID(int=of.id.int * 1000 + obligation_id.int + 501), end, rest),
        ],
    )


# each order in its own group: 108,000.00 × 30 / 1,096 = 2,956.20; 48,000.00 × 30 / 365 = 3,945.21
OWN_1 = version(1, OWN_FIRST, 1, date(2026, 9, 1), BOOKED, "CONTRACT_BOOKED", "CONTRACT_ACTIVATED")
OWN_2 = version(2, OWN_SECOND, 1, date(2026, 9, 1), BOOKED, "CONTRACT_BOOKED", "CONTRACT_ACTIVATED")
# the combined group, allocated 3 : 1: 117,000.00 × 30 / 1,096 = 3,202.55; 39,000.00 × 30 / 365 =
# 3,205.48
JOINT = version(3, COMBINED, 1, date(2026, 9, 12), JOINED, "COMBINATION_CHANGED")
VERSIONS = {OWN_FIRST: (OWN_1,), OWN_SECOND: (OWN_2,), COMBINED: (JOINT,)}
OBLIGATIONS = {
    OWN_1.id: (
        obligation(
            OWN_1,
            FIRST,
            FIRST_O1,
            "SF-ORD-10417",
            "108000.00",
            september="2956.20",
            end=date(2029, 8, 31),
        ),
    ),
    OWN_2.id: (
        obligation(
            OWN_2,
            SECOND,
            SECOND_O1,
            "SF-ORD-10418",
            "48000.00",
            september="3945.21",
            end=date(2027, 8, 31),
        ),
    ),
    JOINT.id: (
        obligation(
            JOINT,
            FIRST,
            FIRST_O1,
            "SF-ORD-10417",
            "117000.00",
            september="3202.55",
            end=date(2029, 8, 31),
        ),
        obligation(
            JOINT,
            SECOND,
            SECOND_O1,
            "SF-ORD-10418",
            "39000.00",
            september="3205.48",
            end=date(2027, 8, 31),
        ),
    ),
}
MEMBERSHIPS = (
    Membership(FIRST, OWN_FIRST, BOOKED, JOINED),
    Membership(SECOND, OWN_SECOND, BOOKED, JOINED),
    Membership(FIRST, COMBINED, JOINED, None),
    Membership(SECOND, COMBINED, JOINED, None),
)


def at(ob: _Ob, day: date) -> ObligationAt:
    """The obligation at ``day`` as a run reads it (S15-R-08 rev 1.127; ``rpo.measure``). In this
    fixture the schedule lines are the obligation's revenue by period: recognised to ``day``, the
    later lines scheduled, nothing awaiting a trigger."""
    revenue = sum((amount for _, end, amount in ob.lines if end <= day), Decimal(0))
    return ObligationAt(
        revenue=revenue,
        billed=Decimal(0),
        progress_ratio=Decimal(0),
        delta=Decimal(0),
        billed_delta=Decimal(0),
        shift=Decimal(0),
        scheduled=ob.allocated - revenue,
        awaiting=Decimal(0),
        satisfaction_status="PARTIALLY_SATISFIED",
        measured=None,
        billed_measured=None,
    )


def store(memberships: tuple[Membership, ...] = MEMBERSHIPS) -> Store:
    return Store(
        versions=VERSIONS,
        obligations=OBLIGATIONS,
        chains=rpo.chains_of(VERSIONS, OBLIGATIONS, memberships),
        cuts={
            (version_id, day): {ob.row_id: at(ob, day) for ob in found}
            for version_id, found in OBLIGATIONS.items()
            for day in (AUGUST_31, SEPTEMBER_5, SEPTEMBER_30, OCTOBER_31)
        },
    )


def totals(found: tuple[rpo.ObligationRpo, ...]) -> dict[str, Decimal]:
    return {item.ob.external_id: item.total for item in found}


def lines(found: tuple[rpo.ContractLines, ...]) -> dict[str, dict[str, Decimal]]:
    return {
        item.external_id: {code: amount for code, amount in item.lines.items() if amount}
        for item in found
    }


def test_a_contract_is_read_along_its_own_chain_of_groups() -> None:
    """Its own group while it was the member, then the combined group: one chain per contract."""
    chains = rpo.chains_of(VERSIONS, OBLIGATIONS, MEMBERSHIPS)
    assert {key: [item.id for item in chain] for key, chain in chains.items()} == {
        FIRST: [OWN_1.id, JOINT.id],
        SECOND: [OWN_2.id, JOINT.id],
    }


def test_rpo_states_a_combined_member_once() -> None:
    """S15-R-08 at 30 Sep 2026: allocated less revenue to date, by the combined group's version —
    117,000.00 − 3,202.55 and 39,000.00 − 3,205.48. Read group by group it was 218,841.25 and
    79,849.31: the former group's 105,043.80 and 44,054.79 on top."""
    found = rpo.rows_at(
        store(), as_of={ENTITY: SEPTEMBER_30}, bands=rpo.DEFAULT_BANDS, applied=NOTHING_APPLIED
    )
    assert totals(found) == {
        "SF-ORD-10417": Decimal("113797.45"),
        "SF-ORD-10418": Decimal("35794.52"),
    }
    assert len(found) == 2  # one row per obligation: the lock's RPO dataset has one row key each


def test_before_the_combined_group_is_effective_the_former_group_is_read() -> None:
    """A date before the combination took effect is the state before it: each order in its own
    group, the allocation as booked (the day's RPO: nothing recognized by 05 Sep 2026)."""
    found = rpo.rows_at(
        store(), as_of={ENTITY: SEPTEMBER_5}, bands=rpo.DEFAULT_BANDS, applied=NOTHING_APPLIED
    )
    assert totals(found) == {
        "SF-ORD-10417": Decimal("108000.00"),
        "SF-ORD-10418": Decimal("48000.00"),
    }


def test_the_rollforward_shows_the_combination_as_a_modification_of_each_member() -> None:
    """S15-R-12 for September 2026: each order is a new contract at its booked price and the
    combination re-allocates 9,000.00 from one member to the other under ``MODIFICATIONS``
    (cause ``COMBINATION_CHANGED``); revenue is the closing version's; nothing is unexplained.
    ``NEW_CONTRACTS`` 156,000.00 in all — read group by group it was 312,000.00."""
    found = lines(rpo.rollforward_lines(store(), ranges=RANGE, applied=NOTHING_APPLIED))
    assert found == {
        "SF-ORD-10417": {
            "NEW_CONTRACTS": Decimal("108000.00"),
            "MODIFICATIONS": Decimal("9000.00"),
            "REVENUE": Decimal("-3202.55"),
            "CLOSING": Decimal("113797.45"),
        },
        "SF-ORD-10418": {
            "NEW_CONTRACTS": Decimal("48000.00"),
            "MODIFICATIONS": Decimal("-9000.00"),
            "REVENUE": Decimal("-3205.48"),
            "CLOSING": Decimal("35794.52"),
        },
    }
    assert sum(item["NEW_CONTRACTS"] for item in found.values()) == Decimal("156000.00")
    assert sum(item["MODIFICATIONS"] for item in found.values()) == Decimal("0.00")


def test_the_period_after_the_combination_opens_at_the_combined_closing() -> None:
    """October 2026: opening = the closing of September by the same version; no movement but
    revenue (none in the fixture's October), so closing = opening."""
    found = lines(
        rpo.rollforward_lines(
            store(), ranges={ENTITY: (SEPTEMBER_30, OCTOBER_31)}, applied=NOTHING_APPLIED
        )
    )
    assert found == {
        "SF-ORD-10417": {"OPENING": Decimal("113797.45"), "CLOSING": Decimal("113797.45")},
        "SF-ORD-10418": {"OPENING": Decimal("35794.52"), "CLOSING": Decimal("35794.52")},
    }


def test_a_membership_that_ended_after_the_cutoff_is_still_open_for_the_run() -> None:
    """A run whose cutoff precedes the combination knows neither the combined group's version nor
    the end of the first membership: the loader passes the membership as open and the versions
    recorded by the cutoff — the former group alone."""
    early_versions = {OWN_FIRST: (OWN_1,), OWN_SECOND: (OWN_2,)}
    early_obligations = {OWN_1.id: OBLIGATIONS[OWN_1.id], OWN_2.id: OBLIGATIONS[OWN_2.id]}
    early = (
        Membership(FIRST, OWN_FIRST, BOOKED, None),
        Membership(SECOND, OWN_SECOND, BOOKED, None),
    )
    chains = rpo.chains_of(early_versions, early_obligations, early)
    assert {key: [item.id for item in chain] for key, chain in chains.items()} == {
        FIRST: [OWN_1.id],
        SECOND: [OWN_2.id],
    }


def test_an_uncombined_contract_returns_to_its_own_group() -> None:
    """Uncombining (an approved error correction) ends the membership in the combined group and
    opens one in the contract's own group again; that group's later version follows the combined
    one in the chain, and its earlier version stays where it was."""
    back = version(4, OWN_SECOND, 2, date(2026, 10, 20), LEFT, "COMBINATION_CHANGED")
    alone = version(5, COMBINED, 2, date(2026, 10, 20), LEFT, "COMBINATION_CHANGED")
    versions = {OWN_FIRST: (OWN_1,), OWN_SECOND: (OWN_2, back), COMBINED: (JOINT, alone)}
    obligations = {
        **OBLIGATIONS,
        back.id: (
            obligation(
                back,
                SECOND,
                SECOND_O1,
                "SF-ORD-10418",
                "48000.00",
                september="3945.21",
                end=date(2027, 8, 31),
            ),
        ),
        alone.id: (
            obligation(
                alone,
                FIRST,
                FIRST_O1,
                "SF-ORD-10417",
                "108000.00",
                september="2956.20",
                end=date(2029, 8, 31),
            ),
        ),
    }
    memberships = (
        Membership(FIRST, OWN_FIRST, BOOKED, JOINED),
        Membership(SECOND, OWN_SECOND, BOOKED, JOINED),
        Membership(FIRST, COMBINED, JOINED, None),
        Membership(SECOND, COMBINED, JOINED, LEFT),
        Membership(SECOND, OWN_SECOND, LEFT, None),
    )
    chains = rpo.chains_of(versions, obligations, memberships)
    assert {key: [item.id for item in chain] for key, chain in chains.items()} == {
        FIRST: [OWN_1.id, JOINT.id, alone.id],
        SECOND: [OWN_2.id, JOINT.id, back.id],
    }


def test_effective_dates_are_carried_forward_along_the_chain() -> None:
    """As within a group: a version never takes effect before the one it follows. A former group's
    version dated later than the combination holds the combined group's version back to its
    date, so the chain has one version at every date."""
    dated_later = version(6, OWN_FIRST, 2, date(2026, 12, 1), BOOKED, "CONTRACT_AMENDED")
    versions = {OWN_FIRST: (OWN_1, dated_later), OWN_SECOND: (OWN_2,), COMBINED: (JOINT,)}
    obligations = {
        **OBLIGATIONS,
        dated_later.id: (
            obligation(
                dated_later,
                FIRST,
                FIRST_O1,
                "SF-ORD-10417",
                "108000.00",
                september="2956.20",
                end=date(2029, 8, 31),
            ),
        ),
    }
    chains = rpo.chains_of(versions, obligations, MEMBERSHIPS)
    assert [(item.id, item.effective) for item in chains[FIRST]] == [
        (OWN_1.id, date(2026, 9, 1)),
        (dated_later.id, date(2026, 12, 1)),
        (JOINT.id, date(2026, 12, 1)),
    ]
    # the other member's chain keeps the version's own date
    assert [(item.id, item.effective) for item in chains[SECOND]] == [
        (OWN_2.id, date(2026, 9, 1)),
        (JOINT.id, date(2026, 9, 12)),
    ]


def test_rows_written_without_a_membership_are_read_as_recorded() -> None:
    """A contract none of whose versions falls in a membership (rows written outside the
    product's commands) is read from every version that holds it, in the order recorded — the
    reading before this item, kept for such rows alone."""
    chains = rpo.chains_of(VERSIONS, OBLIGATIONS, ())
    assert {key: [item.id for item in chain] for key, chain in chains.items()} == {
        FIRST: [OWN_1.id, JOINT.id],
        SECOND: [OWN_2.id, JOINT.id],
    }


# --- RPT-RPO-ROLLFWD-1: entry at activation, and the late-events line -----------------------------

SEPTEMBER_1, SEPTEMBER_27 = date(2026, 9, 1), date(2026, 9, 27)
ALONE = (Membership(FIRST, OWN_FIRST, BOOKED, None),)


def _own_chain(*versions: _Version) -> tuple[_Version, ...]:
    """The chain of ``SF-ORD-10417`` over ``versions`` of its own group, each holding its O1."""
    held = {item.id: OBLIGATIONS[OWN_1.id] for item in versions}
    return rpo.chains_of({OWN_FIRST: versions}, held, ALONE)[FIRST]


def test_a_contract_enters_at_its_activation_not_at_its_first_versions_last_event() -> None:
    """ENGINE_SPEC_B S15-R-12 rev 1.161 (item RPT-RPO-ROLLFWD-1; supervisor ruling R-121 (g)):
    the first version of ``SF-ORD-10417`` was caused by its booking and activation of 1 September
    and by a progress report of 27 September, computed together, so the latest of its causes is
    27 September. The contract is read from it from 1 September on — the day it was activated.

    Fail-first: the version counted from 27 September, so no RPO was stated for the contract at
    any date before it (K-01 through the product: no row at 31 January for a contract activated
    on 1 January, and the whole allocation "new" in February beside unexplained January
    revenue)."""
    first = dataclasses.replace(OWN_1, effective=SEPTEMBER_27, entries=((FIRST, SEPTEMBER_1),))
    (entered,) = _own_chain(first)
    assert (entered.id, entered.effective) == (first.id, SEPTEMBER_1)
    found = Store(
        versions={OWN_FIRST: (first,)},
        obligations={first.id: OBLIGATIONS[OWN_1.id]},
        chains={FIRST: (entered,)},
    )
    assert found.version_at(FIRST, AUGUST_31) is None
    at_entry = found.version_at(FIRST, SEPTEMBER_5)
    assert at_entry is not None and at_entry.id == first.id


def test_only_the_first_included_version_of_a_chain_counts_from_the_entry() -> None:
    """The entry moves one date, the first included version's, and never before the version it
    follows: a booking recorded as a version of its own (not included) on 5 September keeps the
    contract out until then although the activation is dated 1 September; a later version keeps
    the date of its latest cause whatever entry event it names; an entry event of another
    contract of the group moves nothing; and a first version without an entry event among its
    causes keeps its date."""
    booked = dataclasses.replace(OWN_1, id=UUID(int=201), included=False, effective=SEPTEMBER_5)
    activated = dataclasses.replace(
        OWN_1, version_no=2, effective=SEPTEMBER_27, entries=((FIRST, SEPTEMBER_1),)
    )
    assert [item.effective for item in _own_chain(booked, activated)] == [SEPTEMBER_5, SEPTEMBER_5]

    first = dataclasses.replace(OWN_1, effective=SEPTEMBER_5)
    later = dataclasses.replace(
        OWN_1,
        id=UUID(int=202),
        version_no=2,
        effective=SEPTEMBER_27,
        entries=((FIRST, SEPTEMBER_1),),
    )
    assert [item.effective for item in _own_chain(first, later)] == [SEPTEMBER_5, SEPTEMBER_27]

    of_another = dataclasses.replace(
        OWN_1, effective=SEPTEMBER_27, entries=((SECOND, SEPTEMBER_1),)
    )
    assert [item.effective for item in _own_chain(of_another)] == [SEPTEMBER_27]

    without = dataclasses.replace(OWN_1, effective=SEPTEMBER_27)
    assert [item.effective for item in _own_chain(without)] == [SEPTEMBER_27]


def test_revenue_a_later_version_recognises_for_an_earlier_period_is_a_late_event() -> None:
    """S15-R-12 "late events" (rev 1.161; the row ``LATE_EVENTS``): the version at 31 August
    states no revenue of ``SF-ORD-10417`` to that day; a version effective on 5 September — a
    late progress report — states 2,956.20 of it for the time up to 31 August. For September the
    opening is the first version's, 108,000.00, the revenue line is the closing version's between
    its own two ends (nothing more in this fixture), and the 2,956.20 the opening did not know
    stand on the late-events line: nothing is unexplained.

    Fail-first: no line carried the amount and it showed as ``UNEXPLAINED`` −2,956.20 (K-01 with
    a locked January, through the product: −6,480.00 in February)."""
    before = dataclasses.replace(OWN_1, effective=date(2026, 8, 1))
    late = dataclasses.replace(OWN_1, id=UUID(int=203), version_no=2, effective=SEPTEMBER_5)
    as_known_later = obligation(
        late,
        FIRST,
        FIRST_O1,
        "SF-ORD-10417",
        "108000.00",
        september="2956.20",
        end=date(2029, 8, 31),
    )
    # the later version places the first amount in August, the period the event is dated in
    as_known_later.lines[0] = (as_known_later.lines[0][0], AUGUST_31, Decimal("2956.20"))
    unknown_yet = obligation(
        before,
        FIRST,
        FIRST_O1,
        "SF-ORD-10417",
        "108000.00",
        september="0.00",
        end=date(2029, 8, 31),
    )
    obligations = {before.id: (unknown_yet,), late.id: (as_known_later,)}
    versions = {OWN_FIRST: (before, late)}
    found = Store(
        versions=versions,
        obligations=obligations,
        chains=rpo.chains_of(versions, obligations, ALONE),
        cuts={
            (version_id, day): {ob.row_id: at(ob, day) for ob in held}
            for version_id, held in obligations.items()
            for day in (AUGUST_31, SEPTEMBER_30)
        },
    )
    assert lines(rpo.rollforward_lines(found, ranges=RANGE, applied=NOTHING_APPLIED)) == {
        "SF-ORD-10417": {
            "OPENING": Decimal("108000.00"),
            "LATE_EVENTS": Decimal("-2956.20"),
            "CLOSING": Decimal("105043.80"),
        }
    }
    assert rpo.ROLLFORWARD_LINES.index("LATE_EVENTS") == rpo.ROLLFORWARD_LINES.index("REVENUE") - 1
    assert "LATE_EVENTS" in rpo.MOVEMENTS
