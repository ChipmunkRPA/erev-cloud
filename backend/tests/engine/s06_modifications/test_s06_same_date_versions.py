"""D-92 (1)/(1a): same-date estimate versions recorded before the amendment join the modification.

ENGINE_SPEC S06-R-15 and S06-R-17 rev 1.7 (the pre-boundary state — C_before, the pool and the
S06-R-11 weights — is measured WITHOUT a same-date ``ESTIMATE_CHANGED`` version the amendment's
lines change or the class D / class N re-measurement reads; the version applies AT the boundary);
ENGINE_SPEC_B S09-R-04 exception and S09-R-35 cause clause (rev 1.9); S01-R-18 (the pin index
carries the position at which a version applies). The D18 world of ``test_s06_catch_up`` with the
EAC version recorded BEFORE the amendment (the answer-key chronology of MOD-CHK-042-D18) must give
the BUILD_SPEC ``test_chk_042_mixed_d18_default`` figures: f = 0.5, weights 62,500 : 30,000, shares
47,297.30 / 22,702.70, C′_B 30,918.92, catch-up 918.92. The (1a) membership limits are tested on
``pins.build`` directly: an unrelated same-date estimate keeps S09-R-04's ordering, and with two
same-day amendments a version belongs to the first amendment after it. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EstimateVersionInput, EventInput, ModificationInput
from erev_engine.money import cumulative_posted
from erev_engine.stages.s01_canonicalize import pins
from erev_engine.trace import TraceBuilder
from support import bundles
from support.recognition import estimate_version
from test_s06_catch_up import apply, cost, eac, estimate_event, with_eac
from test_s06_prospective import (
    CONTRACT,
    INCEPTION,
    amended,
    booked,
    bundle,
    checked,
    delivered,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    product,
    ssp_version,
    usd,
)

MIXED_DATE = date(2026, 6, 15)


def chk_042_version_before_amendment() -> tuple[object, EventInput]:
    """The CHK-042 world with EAC v2 (75,000.00) recorded at stream 6 and the amendment at 7,
    both effective on the modification date (the MOD-CHK-042-D18 chronology)."""
    scope = mod_line("B", "CHANGE", "SKU-SCOPE", "1", "20000.00")
    modification = modification_input("MOD-42", MIXED_DATE, [scope], kind="QUANTITY_CHANGE")
    # The element names its obligation (T-CON-12 ``obligation_id``), as the answer keys do; the
    # ``with_eac`` patch below is the L1-2-Q-51 segment naming stage 06 reads.
    first, updated = (
        dataclasses.replace(eac("EAC-B", number, effective, total), obligation_key="B")
        for number, effective, total in ((1, INCEPTION, "60000.00"), (2, MIXED_DATE, "75000.00"))
    )
    lines = [
        bundles.booking_line("A", product_code="SKU-A", total_price="40000.00"),
        bundles.booking_line(
            "B", product_code="SKU-B", total_price="60000.00", end=date(2027, 6, 30)
        ),
        bundles.booking_line("C", product_code="SKU-C", total_price="20000.00"),
    ]
    version_event = estimate_event(6, updated)
    value = bundle(
        booked(INCEPTION, *lines),
        estimate_event(3, first),
        delivered(4, "A", "1", date(2026, 3, 31)),
        cost(5, "B", "30000.00", date(2026, 5, 31)),
        version_event,  # EAC +15,000.00 effective at d, recorded BEFORE the amendment
        amended(7, modification, {"B": "CUMULATIVE_CATCH_UP", "C": "PROSPECTIVE"}),
        products=[
            product("SKU-A", "TPL-UNITS"),
            product("SKU-B", "TPL-C2C"),
            product("SKU-C", "TPL-UNITS"),
            product("SKU-SCOPE", "TPL-UNITS"),
        ],
        ssp=[
            ssp_version(
                1,
                [
                    point_entry("SSP-US@v1", "SKU-A", "50000.00"),
                    point_entry("SSP-US@v1", "SKU-B", "75000.00"),
                    point_entry("SSP-US@v1", "SKU-C", "25000.00"),
                ],
                date(2025, 1, 1),
                date(2026, 5, 31),
            ),
            ssp_version(
                2,
                [
                    point_entry("SSP-US@v2", "SKU-C", "30000.00"),
                    point_entry("SSP-US@v2", "SKU-SCOPE", "25000.00"),
                ],
                date(2026, 6, 1),
            ),
        ],
        inception=INCEPTION,
        months=24,
        modifications=[modification],
        estimate_versions=[first, updated],
    )
    return with_eac(fold(value), "B", "EAC-B"), version_event


def test_d92_same_date_eac_before_the_amendment_is_the_modifications_estimate() -> None:
    """D-92 (1): the D18 figures do not depend on the same-date send order."""
    folded, _ = chk_042_version_before_amendment()
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "120000.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    # The pre-boundary state is measured without the version: f = 30,000 ÷ 60,000, pool 70,000.00.
    assert nodes[f"mod_pool@{ev.event_key}:K-01:-"].value == "70000.00"
    weight_b = nodes[f"mod_weight@{ev.event_key}:K-01/B:-"]
    assert (weight_b.value, weight_b.params["progress"]) == ("62500", "1/2")
    assert nodes[f"mod_weight@{ev.event_key}:K-01/C:-"].value == "30000"
    shares = {key: nodes[f"mod_share@{ev.event_key}:K-01/{key}:-"].value for key in ("B", "C")}
    assert shares == {"B": "47297.30", "C": "22702.70"}
    b = obligation(after, "B").segments[-1]
    assert (b.basis, b.a_posted) == ("INCEPTION", usd("77297.30"))
    assert b.x_exact == 30000 + Fraction(70000 * 62500, 92500)
    # The version applies AT the boundary: post-change recognition uses EAC 75,000 (f = 0.4).
    assert cumulative_posted(b.x_exact, b.a_posted, Fraction(30000, 75000), 2) == usd("30918.92")
    catch_up = nodes[f"catch_up@{ev.event_key}:K-01/B:-"]
    assert (catch_up.value, catch_up.params["exact_before"]) == ("918.92", "30000")
    assert obligation(after, "C").segments[-1].a_posted == usd("22702.70")


def test_d92_pin_index_defers_the_member_version_to_the_amendment() -> None:
    """S01-R-18 with the D-92 exception: the member version applies at the amendment's position,
    so a read strictly before the amendment sees EAC v1 and a read at or after it sees v2."""
    folded, version_event = chk_042_version_before_amendment()
    st, ev = folded.state, folded.amended
    key = f"{CONTRACT}/EAC-B"
    before = st.estimates.pin(key, ev.effective_date, before=ev)
    assert before is not None and before.version_no == 1
    at_boundary = st.estimates.pin(key, ev.effective_date)  # every applied version, end of stream
    assert at_boundary is not None and at_boundary.version_no == 2
    (pin,) = [pin for pin in st.estimates.pins[key] if pin.version.version_no == 2]
    assert pin.event_order_key[1] == version_event.record_seq  # the applying event is unchanged
    assert pin.applies() == ev.order_key


# --- (1a) membership limits on the pin index ----------------------------------------------------

D = date(2026, 6, 15)


def _version(
    element: str,
    number: int,
    *,
    obligation_key: str | None,
    kind: str = "EAC",
    target: str = "OBLIGATION",
    targets: tuple[str, ...] = (),
) -> EstimateVersionInput:
    version = estimate_version(
        f"{CONTRACT}/{element}", kind, number, D, obligation_key=obligation_key
    )
    return dataclasses.replace(
        version,
        allocation_target=target,
        target_obligation_keys=targets,
        expected_total_amount=Decimal("100.00") if kind == "EAC" else None,
        constrained_amount=None if kind == "EAC" else Decimal("10.00"),
    )


def _contract(*modifications: ModificationInput):
    return dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), modifications=tuple(modifications)
    )


def _amendment(stream: int, modification: ModificationInput, key: str) -> EventInput:
    return amended(stream, modification, {key: "CUMULATIVE_CATCH_UP"})


def _booking() -> EventInput:
    return booked(
        INCEPTION,
        bundles.booking_line("B", product_code="SKU-B", total_price="60000.00"),
        bundles.booking_line("X", product_code="SKU-X", total_price="10000.00"),
    )


def _index(events: list[EventInput], versions: list[EstimateVersionInput], contract):
    built, findings = pins.build(
        tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        tuple(versions),
        contracts=(contract,),
    )
    assert findings == ()
    return built


def _applies(index, element: str) -> tuple[tuple[date, int, str], ...]:
    return tuple(pin.applies() for pin in index.pins[f"{CONTRACT}/{element}"])


def test_d92_1a_unrelated_same_date_estimate_keeps_the_ordering() -> None:
    """A same-date version of an estimate the amendment neither changes nor re-measures applies at
    its own event (S09-R-04 ordering); the amended obligation's version defers."""
    modification = modification_input(
        "MOD-B", D, [mod_line("B", "CHANGE", "SKU-B", "0", "5000.00")], kind="PRICE_CHANGE"
    )
    eac_b, eac_x = (
        _version("EAC-B", 1, obligation_key="B"),
        _version("EAC-X", 1, obligation_key="X"),
    )
    events = [
        _booking(),
        estimate_event(3, eac_b),
        estimate_event(4, eac_x),
        _amendment(5, modification, "B"),
    ]
    index = _index(events, [eac_b, eac_x], _contract(modification))
    amendment_key = (D, 5, f"{CONTRACT}/EV-000005")
    assert _applies(index, "EAC-B") == (amendment_key,)  # member: B is amended
    assert _applies(index, "EAC-X") == ((D, 4, f"{CONTRACT}/EV-000004"),)  # unrelated: own event


def test_d92_1a_contract_level_vc_belongs_to_the_amendment_that_reallocates_it() -> None:
    """A CONTRACT-target VC version (the S06-R-12 includable ΔVC) is re-allocated by the pool, so it
    defers to the amendment; an INCREMENTS element (realised amounts) never does."""
    modification = modification_input(
        "MOD-B", D, [mod_line("B", "CHANGE", "SKU-B", "0", "5000.00")], kind="PRICE_CHANGE"
    )
    bonus = _version(
        "VC-BONUS", 1, obligation_key=None, kind="VARIABLE_CONSIDERATION", target="CONTRACT"
    )
    usage = _version(
        "VC-USAGE", 1, obligation_key=None, kind="VARIABLE_CONSIDERATION", target="INCREMENTS"
    )
    events = [
        _booking(),
        estimate_event(3, bonus),
        estimate_event(4, usage),
        _amendment(5, modification, "B"),
    ]
    index = _index(events, [bonus, usage], _contract(modification))
    assert _applies(index, "VC-BONUS") == ((D, 5, f"{CONTRACT}/EV-000005"),)
    assert _applies(index, "VC-USAGE") == ((D, 4, f"{CONTRACT}/EV-000004"),)


def test_d92_1a_two_same_day_amendments_take_the_first_one_after_the_version() -> None:
    """With two amendments on d, a version belongs to the first amendment after it in record_seq,
    never to an earlier one; a version recorded after both keeps today's reading."""
    first = modification_input(
        "MOD-1", D, [mod_line("B", "CHANGE", "SKU-B", "0", "1000.00")], kind="PRICE_CHANGE"
    )
    second = modification_input(
        "MOD-2", D, [mod_line("B", "CHANGE", "SKU-B", "0", "2000.00")], kind="PRICE_CHANGE"
    )
    v1, v2, v3 = (_version("EAC-B", number, obligation_key="B") for number in (1, 2, 3))
    events = [
        _booking(),
        estimate_event(3, v1),
        _amendment(4, first, "B"),
        estimate_event(5, v2),
        _amendment(6, second, "B"),
        estimate_event(7, v3),
    ]
    index = _index(events, [v1, v2, v3], _contract(first, second))
    assert _applies(index, "EAC-B") == (
        (D, 4, f"{CONTRACT}/EV-000004"),  # v1: the first amendment after it
        (D, 6, f"{CONTRACT}/EV-000006"),  # v2: the second, never the earlier one
        (D, 7, f"{CONTRACT}/EV-000007"),  # v3: after both, its own event
    )


def test_d92_1a_a_version_on_another_date_or_contract_never_defers() -> None:
    earlier = date(2026, 6, 14)
    modification = modification_input(
        "MOD-B", D, [mod_line("B", "CHANGE", "SKU-B", "0", "5000.00")], kind="PRICE_CHANGE"
    )
    version = dataclasses.replace(_version("EAC-B", 1, obligation_key="B"), effective_date=earlier)
    event = bundles.event(
        CONTRACT, 3, "ESTIMATE_CHANGED", earlier, {"estimate_version_id": version.version_key}
    )
    index = _index(
        [_booking(), event, _amendment(5, modification, "B")], [version], _contract(modification)
    )
    assert _applies(index, "EAC-B") == ((earlier, 3, f"{CONTRACT}/EV-000003"),)


def test_a_version_in_force_at_inception_is_marked_unless_an_amendment_takes_it() -> None:
    """S01-R-18 beside D-92 (1)/(1a) (item ENG-INCEPTION-ESTIMATE-1). A version whose
    ``ESTIMATE_CHANGED`` is dated at the group inception is in force at inception: its pin is
    marked, and ``EstimatePins.pin`` admits it before every position. D-92 keeps its precedence:
    a same-date amendment recorded after the version that takes it applies the version, and the
    pin is not marked. A version dated after the inception is never marked, and a caller that
    passes no inception date marks none."""
    modification = modification_input(
        "MOD-B", INCEPTION, [mod_line("B", "CHANGE", "SKU-B", "0", "5000.00")], kind="PRICE_CHANGE"
    )

    def dated(version: EstimateVersionInput, effective: date) -> EstimateVersionInput:
        return dataclasses.replace(version, effective_date=effective)

    def changed(stream: int, version: EstimateVersionInput) -> EventInput:
        payload = {"estimate_version_id": version.version_key}
        return bundles.event(CONTRACT, stream, "ESTIMATE_CHANGED", version.effective_date, payload)

    bonus_1, bonus_2 = (
        dated(
            _version(
                "VC-BONUS",
                number,
                obligation_key=None,
                kind="VARIABLE_CONSIDERATION",
                target="CONTRACT",
            ),
            INCEPTION,
        )
        for number in (1, 2)
    )
    usage = dated(
        _version(
            "VC-USAGE", 1, obligation_key=None, kind="VARIABLE_CONSIDERATION", target="INCREMENTS"
        ),
        INCEPTION,
    )
    later = _version(
        "VC-LATER", 1, obligation_key=None, kind="VARIABLE_CONSIDERATION", target="CONTRACT"
    )
    events = [
        _booking(),
        changed(3, bonus_1),  # the amendment of the same date, recorded after it, takes it (D-92)
        changed(4, usage),  # realised amounts: never a member of an amendment
        _amendment(5, modification, "B"),
        changed(6, bonus_2),  # recorded after the amendment
        changed(7, later),  # effective after the inception
    ]
    versions = [bonus_1, bonus_2, usage, later]
    ordered = tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key)))
    built, findings = pins.build(
        ordered, tuple(versions), contracts=(_contract(modification),), inception_date=INCEPTION
    )
    assert findings == ()
    marks = {
        (pin.version.element_code, pin.version.version_no): (pin.at_inception, pin.applies())
        for element in built.pins.values()
        for pin in element
    }
    assert marks == {
        ("VC-BONUS", 1): (False, (INCEPTION, 5, f"{CONTRACT}/EV-000005")),
        ("VC-BONUS", 2): (True, (INCEPTION, 6, f"{CONTRACT}/EV-000006")),
        ("VC-USAGE", 1): (True, (INCEPTION, 4, f"{CONTRACT}/EV-000004")),
        ("VC-LATER", 1): (False, (D, 7, f"{CONTRACT}/EV-000007")),
    }
    unmarked = _index(events, versions, _contract(modification))
    assert not any(pin.at_inception for element in unmarked.pins.values() for pin in element)
