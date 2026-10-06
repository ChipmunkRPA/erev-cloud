"""D-93 (4) / D-97 (3): a series SSP entry declares what it prices (04 E-49 ``ssp_value_basis``)
and, priced per increment, what the line's quantity counts (E-125 ``quantity_unit``).

ENGINE_SPEC S06-R-11 rev 1.11 (class D series: "the d SSP of the remaining increments, priced from
the SSP entry's declared basis: ``PER_INCREMENT`` × the remaining increments in [d, e_p] × the
remaining quantity as T-REF-30 ``quantity_unit`` declares it — ``SERVICE_UNITS``: each unit spans
the term, so value × increments × ρ × quantity; ``INCREMENTS``: the quantity counts increments, so
value × ρ × quantity — a ``PER_INCREMENT`` entry without ``quantity_unit`` fails closed, CV-45;
``PER_BOOKED_TERM`` ÷ the increments of the term the entry prices × the remaining increments; an
entry annotated as pricing the remaining increments at d is taken as is"); 04 T-REF-30 rev 1.19;
POLICIES ALG-04 §2.5.4. The world is MOD-FS-03-CASEB's shape: a 12-month series subscription
120,000.00 (entry 132,000.00 for the booked term, or 11,000.00 per month) and, on 1 Jul 2026, added
seats 26,400.00 for six months (entry 33,000.00): the remaining six months weigh 66,000.00 against
33,000.00, so the 86,400.00 pool splits 2 : 1 (the key's 2 : 1), where the booked-term entry read
as the remaining-increments amount gave 4 : 1. The remaining increments are counted as the pinned
E-21 convention counts the term's periods (Codex PRODUCTION-C1B-SERIES-BASIS-77cc618 S1: one
denominator for the count and for ρ) and never inferred from the line's quantity (S2; D-97 (3)).
Every trace re-evaluates node for node (DG-ENG-04). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle
from erev_engine.stages.state import AllocatedState
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles
from test_s06_catch_up import apply
from test_s06_prospective import (
    CONTRACT,
    TEMPLATES,
    amended,
    booked,
    bundle,
    checked,
    fold,
    mod_line,
    modification_input,
    obligation,
    point_entry,
    product,
    ssp_version,
    template,
    usd,
)

START, END = date(2026, 1, 1), date(2026, 12, 31)
MOD_DATE = date(2026, 7, 1)
SUB, SEATS = "SKU-SUB", "SKU-SEATS"
D18_FORMULA = "mod.weights.d18.v1"
INCEPTION_FORMULA = "mod.weights.inception_all.v1"
SERVICE_UNITS, INCREMENTS = "SERVICE_UNITS", "INCREMENTS"


def series_world(
    basis: str | None,
    point: str,
    *,
    quantity_unit: str | None = None,
    start: date = START,
    convention: str = "MONTHLY_EVEN",
    unit: str = "month",
    quantity: str = "1",
    remove: str | None = None,
    mod_date: date = MOD_DATE,
    ssp_basis: str | None = None,
    seats_unit: str | None = None,
) -> InputBundle:
    """The FS-03B shape over a series template with ``unit`` increments under ``convention``:
    the subscription line (``quantity`` units, 120,000.00, [``start``, 31 Dec]) and, on
    ``mod_date``, added seats 26,400.00 (entry 33,000.00) plus, with ``remove``, a CHANGE line
    removing that many subscription units for no consideration. ``basis`` and ``quantity_unit``
    annotate the subscription's SSP entry (None leaves ``point_entry``'s explicit ``AMOUNT`` and no
    unit); ``seats_unit`` annotates the seats entry."""
    entry = point_entry("SSP-US@v1", SUB, point)
    if basis is not None:
        entry = dataclasses.replace(entry, value_basis=basis)
    if quantity_unit is not None:
        entry = dataclasses.replace(entry, quantity_unit=quantity_unit)
    seats_entry = point_entry("SSP-US@v1", SEATS, "33000.00")
    if seats_unit is not None:
        # A unit is meaningful for PER_INCREMENT only; the added obligation's entry is the d SSP
        # for ΔQ_m, ΔC_m and is never rescaled, so its basis does not change the figures.
        seats_entry = dataclasses.replace(
            seats_entry, value_basis="PER_INCREMENT", quantity_unit=seats_unit
        )
    lines = [mod_line("L3", "ADD", SEATS, "1", "26400.00", start=mod_date, end=END)]
    if remove is not None:
        lines.insert(0, mod_line("L1", "CHANGE", SUB, f"-{remove}", "0.00"))
    modification = modification_input(
        "MOD-B", mod_date, lines, kind="QUANTITY_CHANGE" if remove else "ADD_OBLIGATION"
    )
    overrides = {"recognition.time_convention": convention}
    if ssp_basis is not None:
        overrides["mod.ssp_basis"] = ssp_basis
    value = bundle(
        booked(
            START,
            bundles.booking_line(
                "L1",
                product_code=SUB,
                quantity=quantity,
                total_price="120000.00",
                start=start,
                end=END,
            ),
        ),
        amended(3, modification, {"L1": "PROSPECTIVE", "L3": "PROSPECTIVE"}),
        products=[product(SUB, "TPL-SUB"), product(SEATS, "TPL-SUB")],
        ssp=[ssp_version(1, [entry, seats_entry], date(2020, 1, 1))],
        inception=START,
        months=12,
        modifications=[modification],
        overrides=overrides,
    )
    series = template(
        "TPL-SUB",
        method="TIME_ELAPSED",
        pattern="OVER_TIME",
        convention=convention,
        distinctness="series",
        series_increment_unit=unit,
    )
    templates = tuple(sorted((*TEMPLATES, series), key=lambda t: t.template_code))
    return dataclasses.replace(value, pob_template_versions=templates)


def weighed(
    basis: str | None, point: str, *, pool: str | None = "86400.00", **world: object
) -> tuple[TraceNode, dict[str, str], AllocatedState]:
    """The subscription's ``mod_weight`` node, the two shares and the state after the event.

    ``pool`` is the expected ``mod_pool`` (60,000.00 unrecognised at 30 Jun + 26,400.00 for the
    Jan–Dec worlds); ``None`` skips it for worlds whose recognition through 30 Jun differs."""
    folded = fold(series_world(basis, point, **world))  # type: ignore[arg-type]
    ev = folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = apply(folded, "120000.00", tb)
    assert after.findings == ()
    nodes = checked(tb)
    weight = nodes[f"mod_weight@{ev.event_key}:{CONTRACT}/L1:-"]
    shares = {
        key: nodes[f"mod_share@{ev.event_key}:{CONTRACT}/{key}:-"].value for key in ("L1", "L3")
    }
    if pool is not None:
        assert nodes[f"mod_pool@{ev.event_key}:{CONTRACT}:-"].value == pool
        assert obligation(after, "L1").segments[-1].a_posted == usd("60000.00") + usd(shares["L1"])
    return weight, shares, after


def per_increment(point: str, **world: object) -> tuple[TraceNode, dict[str, str], AllocatedState]:
    """A ``PER_INCREMENT`` entry declaring ``SERVICE_UNITS`` (the default world reading)."""
    world.setdefault("quantity_unit", SERVICE_UNITS)
    return weighed("PER_INCREMENT", point, **world)


def weights_and_shares(basis: str | None, point: str) -> tuple[dict[str, object], dict[str, str]]:
    weight, shares, _ = per_increment(point) if basis == "PER_INCREMENT" else weighed(basis, point)
    assert weight.formula_id == D18_FORMULA
    return {"value": weight.value, "params": dict(weight.params)}, shares


# --- D-93 (4): the declared basis -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("basis", "point", "increments"),
    [("PER_BOOKED_TERM", "132000.00", "12"), ("PER_INCREMENT", "11000.00", "12")],
)
def test_d93_4_series_entry_priced_from_its_declared_basis(
    basis: str, point: str, increments: str
) -> None:
    weight, shares = weights_and_shares(basis, point)
    # Six of twelve months remain at the close of 30 Jun: 132,000 × 6 ÷ 12 = 11,000 × 6 = 66,000.
    assert weight["value"] == "66000"
    params = weight["params"]
    assert (params["series_basis"], params["series_increments"], params["remaining_scale"]) == (
        basis,
        increments,
        "1/2",
    )
    assert params["series_remaining_increments"] == "6"
    assert (params["measure"], params["convention"], params["progress_as_of"]) == (
        "TIME_ELAPSED",
        "MONTHLY_EVEN",
        "2026-06-30",
    )
    assert params.get("series_quantity_unit") == (
        SERVICE_UNITS if basis == "PER_INCREMENT" else None
    )
    assert shares == {
        "L1": "57600.00",
        "L3": "28800.00",
    }  # 86,400 × 66,000 ÷ 99,000; × 33,000 ÷ 99,000


def test_d93_4_explicit_amount_on_a_series_entry_is_taken_as_is() -> None:
    # An entry declared AMOUNT prices the remaining increments at d as is (CHK-043, EX-09-A):
    # 132,000 : 33,000. The engine only ever sees a declared basis: an omitted basis on a series
    # entry is refused by the answer-key loader (dev-guide §9.5.3 `ssp_books`; D-93 (4) fails
    # closed).
    weight, shares = weights_and_shares(None, "132000.00")
    assert weight["value"] == "132000"
    assert "series_basis" not in weight["params"]
    assert shares == {"L1": "69120.00", "L3": "17280.00"}


def test_d93_4_added_obligation_entry_is_never_rescaled() -> None:
    # The seats entry (33,000.00 for the added six-month obligation) is the d SSP for ΔQ_m, ΔC_m
    # (S06-R-11 class D new), whatever the basis annotated on the existing obligation's entry.
    _, shares = weights_and_shares("PER_BOOKED_TERM", "132000.00")
    assert Fraction(usd(shares["L1"]), usd(shares["L3"])) == 2


# --- Codex C1B-S1: the increments are counted as the convention counts the term -------------------


@pytest.mark.parametrize(
    ("convention", "increments", "rho"),
    [
        # MONTHLY_EVEN: 16/31 of January + 11 whole months = 357/31 periods; 171/31 elapsed by
        # 30 Jun; ρ = 186/357 = 62/119; remaining increments 357/31 × 62/119 = 6.
        ("MONTHLY_EVEN", "357/31", "62/119"),
        # MID_MONTH: January (day 16 > 15) is not counted; 11 periods, 5 complete; ρ = 6/11.
        ("MID_MONTH", "11", "6/11"),
    ],
)
def test_codex_s1_partial_first_month_counts_six_remaining_increments(
    convention: str, increments: str, rho: str
) -> None:
    # Term 16 Jan – 31 Dec 2026, PER_INCREMENT 11,000: six full July–December increments remain
    # under both conventions, so the weight is 66,000 — not 11,000 × 12 touched months × ρ
    # (68,773.11 / 72,000).
    weight, _, _ = per_increment(
        "11000.00", pool=None, start=date(2026, 1, 16), convention=convention
    )
    assert weight.formula_id == D18_FORMULA
    assert weight.value == "66000"
    params = weight.params
    assert (params["series_increments"], params["remaining_scale"]) == (increments, rho)
    assert (params["series_remaining_increments"], params["series_multiplier"]) == ("6", increments)
    assert params["convention"] == convention


@pytest.mark.parametrize("convention", ["MONTHLY_EVEN", "MID_MONTH"])
def test_codex_s1_partial_first_month_under_inception_all(convention: str) -> None:
    weight, _, _ = per_increment(
        "11000.00",
        pool=None,
        start=date(2026, 1, 16),
        convention=convention,
        ssp_basis="INCEPTION_ALL",
    )
    assert (weight.formula_id, weight.value) == (INCEPTION_FORMULA, "66000")
    assert weight.params["series_remaining_increments"] == "6"


def test_codex_s1_booked_term_entry_over_a_partial_term_scales_by_rho() -> None:
    # PER_BOOKED_TERM prices the term the entry prices (16 Jan – 31 Dec): 132,000 ÷ (357/31)
    # increments × 6 remaining = 132,000 × 62/119 = 8,184,000/119 (68,773.11) — the booked-term
    # reading, not the per-increment one.
    weight, _, _ = weighed("PER_BOOKED_TERM", "132000.00", pool=None, start=date(2026, 1, 16))
    assert Decimal(weight.value).quantize(Decimal("0.01")) == Decimal("68773.11")
    assert abs(Fraction(Decimal(weight.value)) - Fraction(8_184_000, 119)) < Fraction(1, 10**12)
    assert (weight.params["series_increments"], weight.params["series_multiplier"]) == (
        "357/31",
        "1",
    )


@pytest.mark.parametrize("convention", ["MONTHLY_EVEN", "MID_MONTH"])
def test_codex_s1_mid_month_modification_control(convention: str) -> None:
    # A 16 Jul amendment measured at the close of 15 Jul: a whole period of the term counts only
    # once complete under both conventions, so July counts as remaining (D-90b) — six of twelve
    # increments, 11,000 × 6 = 66,000.
    weight, _, _ = per_increment(
        "11000.00", pool=None, convention=convention, mod_date=date(2026, 7, 16)
    )
    assert weight.value == "66000"
    assert (
        weight.params["series_increments"],
        weight.params["series_remaining_increments"],
        weight.params["progress_as_of"],
    ) == ("12", "6", "2026-07-15")


def test_codex_s1_daily_increments_control() -> None:
    # A day-increment series under DAILY: 365 days, 181 elapsed by 30 Jun, 184 remain;
    # 400 per day × 184 = 73,600.
    weight, _, _ = per_increment("400.00", pool=None, convention="DAILY", unit="day")
    assert weight.value == "73600"
    assert (
        weight.params["series_increments"],
        weight.params["series_remaining_increments"],
        weight.params["remaining_scale"],
    ) == ("365", "184", "184/365")


# --- Codex C1B-S2 / D-97 (3): the quantity unit is declared, never inferred -----------------------


@pytest.mark.parametrize(
    ("remove", "remaining_quantity", "value"),
    [(None, "12", "7920"), ("10", "2", "1320"), ("11", "1", "660")],
)
def test_d97_3_service_units_removing_units_never_raises_the_weight(
    remove: str | None, remaining_quantity: str, value: str
) -> None:
    # Twelve units at PER_INCREMENT 110 over Jan–Dec, SERVICE_UNITS; the 1 Jul amendment removes
    # 0, 10 or 11 units for no consideration: 110 × remaining units × 12 increments × ρ 1/2 =
    # 7,920 / 1,320 / 660 — monotone in the removal, multiplier 12 whatever the remaining quantity.
    weight, _, _ = per_increment("110.00", quantity="12", remove=remove)
    assert weight.value == value
    assert (
        weight.params["remaining_quantity"],
        weight.params["series_multiplier"],
        weight.params["series_quantity_unit"],
    ) == (remaining_quantity, "12", SERVICE_UNITS)
    assert weight.params["removed"] == ("0" if remove is None else remove)


@pytest.mark.parametrize(
    ("remove", "remaining_quantity", "value"),
    [(None, "12", "660"), ("10", "2", "110"), ("11", "1", "55")],
)
def test_d97_3_increments_unit_prices_the_remaining_increments_of_the_quantity(
    remove: str | None, remaining_quantity: str, value: str
) -> None:
    # The same fixture declaring INCREMENTS (the quantity counts increments, seat-months): the
    # SSP at d is 110 × remaining quantity × ρ 1/2 = 660 / 110 / 55 (Codex C1B-S2's independent
    # figures), multiplier 1.
    weight, shares, _ = weighed(
        "PER_INCREMENT", "110.00", quantity_unit=INCREMENTS, quantity="12", remove=remove
    )
    assert weight.formula_id == D18_FORMULA
    assert weight.value == value
    assert (
        weight.params["remaining_quantity"],
        weight.params["series_multiplier"],
        weight.params["series_quantity_unit"],
    ) == (remaining_quantity, "1", INCREMENTS)
    if remove == "11":
        # 86,400 × 55 ÷ 33,055 and × 33,000 ÷ 33,055 (Codex: 143.76 / 86,256.24).
        assert shares == {"L1": "143.76", "L3": "86256.24"}


@pytest.mark.parametrize(("remove", "value"), [(None, "660"), ("10", "110"), ("11", "55")])
def test_d97_3_increments_unit_under_inception_all(remove: str | None, value: str) -> None:
    # The original conditional oracles 660 / 110 / 55 hold under INCEPTION_ALL too (D-97 (3)
    # acceptance): the inception entry's declaration prices the remaining increments.
    weight, _, _ = weighed(
        "PER_INCREMENT",
        "110.00",
        quantity_unit=INCREMENTS,
        quantity="12",
        remove=remove,
        ssp_basis="INCEPTION_ALL",
    )
    assert (weight.formula_id, weight.value) == (INCEPTION_FORMULA, value)
    assert (weight.params["series_quantity_unit"], weight.params["series_multiplier"]) == (
        INCREMENTS,
        "1",
    )


@pytest.mark.parametrize("basis", ["AMOUNT", "PER_BOOKED_TERM"])
def test_d97_3_quantity_unit_with_another_basis_is_refused(basis: str) -> None:
    # The unit is meaningful for a PER_INCREMENT entry only (D-97 (3) completion contract).
    with pytest.raises(ValueError, match="meaningful for a PER_INCREMENT entry only"):
        fold(series_world(basis, "132000.00", quantity_unit=SERVICE_UNITS))


def test_d97_3_hash_view_writes_the_quantity_unit_only_when_declared() -> None:
    # CV-25 compatibility path: an entry without a declaration hashes as before the member
    # existed (the member is absent from its hash view); a declared unit enters the bundle hash.
    undeclared = series_world(None, "132000.00")
    entry = next(e for e in undeclared.ssp_versions[0].entries if e.product_code == SUB)
    assert entry.quantity_unit is None
    assert "quantity_unit" not in entry.hash_view()
    assert "value_basis" in entry.hash_view()
    declared = series_world("PER_INCREMENT", "11000.00", quantity_unit=SERVICE_UNITS)
    chosen = next(e for e in declared.ssp_versions[0].entries if e.product_code == SUB)
    assert chosen.hash_view()["quantity_unit"] == SERVICE_UNITS
    assert undeclared.sha256() != declared.sha256()
    again = series_world("PER_INCREMENT", "11000.00", quantity_unit=SERVICE_UNITS)
    other = series_world("PER_INCREMENT", "11000.00", quantity_unit=INCREMENTS)
    assert declared.sha256() == again.sha256()
    assert declared.sha256() != other.sha256()


def test_d97_3_weights_are_monotone_in_the_removal_under_both_units() -> None:
    for quantity_unit, expected in (
        (SERVICE_UNITS, [7920, 7260, 3960, 1320, 660]),
        (INCREMENTS, [660, 605, 330, 110, 55]),
    ):
        values = [
            Fraction(
                weighed(
                    "PER_INCREMENT",
                    "110.00",
                    quantity_unit=quantity_unit,
                    quantity="12",
                    remove=remove,
                )[0].value
            )
            for remove in (None, "1", "6", "10", "11")
        ]
        assert values == sorted(values, reverse=True)
        assert values == [Fraction(item) for item in expected]


def test_d97_3_per_increment_entry_without_a_quantity_unit_fails_closed() -> None:
    # Stage 01 refuses the bundle (CV-45): the unit is never inferred from the quantity.
    with pytest.raises(ValueError, match="PER_INCREMENT SSP entry declares quantity_unit"):
        fold(series_world("PER_INCREMENT", "11000.00"))


def test_d97_3_entries_of_one_product_agree_on_the_quantity_unit() -> None:
    # A second entry of the same product in the same book declaring another unit is refused; a
    # unit on another product (the seats entry) is not a disagreement.
    fold(
        series_world(
            "PER_INCREMENT", "11000.00", quantity_unit=SERVICE_UNITS, seats_unit=INCREMENTS
        )
    )
    disagreeing = series_world("PER_INCREMENT", "11000.00", quantity_unit=SERVICE_UNITS)
    version = disagreeing.ssp_versions[0]
    first = version.entries[0] if version.entries[0].product_code == SUB else version.entries[1]
    other = dataclasses.replace(
        first,
        entry_key=first.entry_key.replace("//", "/EU/", 1),
        region="EU",
        quantity_unit=INCREMENTS,
    )
    entries = tuple(sorted((*version.entries, other), key=lambda e: e.entry_key))
    disagreeing = dataclasses.replace(
        disagreeing, ssp_versions=(dataclasses.replace(version, entries=entries),)
    )
    with pytest.raises(ValueError, match="quantity_unit INCREMENTS disagrees"):
        fold(disagreeing)
