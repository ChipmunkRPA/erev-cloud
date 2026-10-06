"""Delta posting and pre-standard revenue end to end: legacy 06 TC-JE-02, TC-JE-08 and TC-JE-10,
legacy 03 TC-14, legacy 04 TC-RM-12 and legacy 05 TC-pob-vc-13 (END-10).

ENGINE_SPEC_B §13.2.4 S13-R-09, S13-R-10; §14.3.4 S14-R-23; POLICIES JET-02, JET-06, JET-15, §6.3;
D-34; DEVIATIONS DEV-050, DEV-051; golden GT-07, GT-18. The golden streams are computed by the real
engine under ``LEGACY_PARITY`` with the books ``ASC606`` (primary) and ``LEGACY``, activated at
inception (L2-5-Q-38), with a ``NETTING_RECLASS`` close pass over the posted intents (RCP-08(b);
L3-2-Q-21). ``support.intent_totals`` sums the intents in the legacy grain: balance-sheet lines per
contract, revenue lines per obligation (POL-006 ``LEGACY_CONTRACT_POB``). A modification upload is
built as the golden replay builds one (S01-R-09): an approved modification and its
``CONTRACT_AMENDED``, repeating the stored attributes of the named obligation (LM-TPL-MOD).
Legacy 05 numbers its snapshots from 00, so its "step 04 (after 2.28)" is golden step 05
(L2-3-Q-35). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal

from erev_engine import compute
from erev_engine.bundle import InputBundle, ModificationInput
from erev_engine.canonical import sha256_hex
from erev_engine.money import decimal_to_minor
from support import golden_streams, intent_totals

DELTA = intent_totals.DELTA
GROSS = intent_totals.GROSS
JANUARY = (date(2023, 1, 1), date(2023, 1, 31))
YEAR = (date(2023, 1, 1), date(2023, 12, 31))


def usd(amount: str) -> int:
    return decimal_to_minor(Decimal(amount), 2)


def cr(amount: str) -> int:
    return -usd(amount)


TC_JE_02 = {
    ("Contract 1", None, "21001"): usd("141.69"),
    ("Contract 1", "POB #1", "5001"): cr("128.84"),
    ("Contract 1", "POB #2", "5002"): cr("52.53"),
    ("Contract 1", "POB #3", "5003"): usd("39.68"),
    ("Contract 2", None, "15002"): usd("58.85"),
    ("Contract 2", "POB #1", "5001"): cr("58.85"),
}


def golden(contract: str, step: str) -> InputBundle:
    stream = golden_streams.stream(contract, step)
    value = stream.input_bundle(preset="LEGACY_PARITY", books=intent_totals.BOOKS)
    return intent_totals.activated(value)


def booking_line(value: InputBundle, key: str) -> Mapping[str, object]:
    booked = next(event for event in value.events if event.event_type == "CONTRACT_BOOKED")
    members = booked.payload["lines"]
    assert isinstance(members, Sequence)
    return next(
        line for line in members if isinstance(line, Mapping) and line["obligation_key"] == key
    )


def template_line(value: InputBundle, key: str, quantity: str, billing: str) -> dict[str, object]:
    """A modification row on an existing obligation that repeats its stored attributes."""
    stored = booking_line(value, key)
    accounts = stored["account_overrides"]
    assert isinstance(accounts, Mapping)
    return {
        "obligation_key": key,
        "action": "CHANGE",
        "product_code": stored["product_code"],
        "quantity_delta": Decimal(quantity),
        "consideration_delta": Decimal(billing),
        "stratification": stored["stratification"],
        "selling_entity_code": stored["performing_entity_code"],
        "account_codes": dict(accounts),
        "ssp_version_label": stored["ssp_version_label"],
    }


def amended(
    value: InputBundle,
    key: str,
    effective: date,
    mode: str,
    lines: Sequence[Mapping[str, object]],
) -> InputBundle:
    """``value`` with one approved template modification and the ``CONTRACT_AMENDED`` applying it,
    the chosen treatment of the template for every obligation (S01-R-09)."""
    header = value.contracts[0]
    booked = next(event for event in value.events if event.event_type == "CONTRACT_BOOKED")
    booked_lines = booked.payload["lines"]
    assert isinstance(booked_lines, Sequence)
    keys = {str(line["obligation_key"]) for line in booked_lines if isinstance(line, Mapping)}
    treatment = golden_streams.TREATMENTS[mode]
    treatments = {name: treatment for name in sorted(keys)}
    modification = ModificationInput(
        modification_key=key,
        effective_date=effective,
        kind="VC_CHANGE" if mode == "pob_price_change" else "QUANTITY_CHANGE",
        template_mode=mode,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=tuple(lines),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments=treatments,
        treatment_summary=treatment,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    payload = {
        "modification_id": key,
        "treatments": treatments,
        "lines": list(lines),
        "ssp_basis": {},
    }
    head = max(event.stream_version for event in value.events) + 1
    event = dataclasses.replace(
        booked,
        event_key=f"{header.external_id}/EV-{head:06d}",
        stream_version=head,
        event_type="CONTRACT_AMENDED",
        effective_date=effective,
        recorded_at=max(event.recorded_at for event in value.events) + timedelta(seconds=1),
        record_seq=max(event.record_seq for event in value.events) + 1,
        obligation_keys=tuple(sorted({str(line["obligation_key"]) for line in lines})),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        idempotency_key=None,
        modification_key=key,
    )
    events = sorted(
        (*value.events, event),
        key=lambda item: (item.effective_date, item.record_seq, item.event_key),
    )
    header = dataclasses.replace(header, modifications=(*header.modifications, modification))
    return dataclasses.replace(value, contracts=(header,), events=tuple(events))


def with_head(value: InputBundle, head: int) -> InputBundle:
    """``value`` as a later computation: events through stream version ``head`` already included."""
    contract = value.contracts[0].external_id
    group = dataclasses.replace(value.group, previous_stream_heads=((contract, head),))
    return dataclasses.replace(value, group=group)


def test_tc_je_02_delta_january() -> None:
    computed = [
        *intent_totals.golden("Contract 1", "04"),
        *intent_totals.golden("Contract 2", "04"),
    ]
    found = intent_totals.totals(computed, view=DELTA, start=JANUARY[0], end=JANUARY[1])
    assert found == TC_JE_02
    assert sum(found.values()) == 0


def test_tc_je_08_full_year_gross_and_delta() -> None:
    computed = [
        *intent_totals.golden("Contract 1", "14"),
        *intent_totals.golden("Contract 3", "14"),
    ]
    gross = intent_totals.totals(computed, view=GROSS, start=YEAR[0], end=YEAR[1])
    delta = intent_totals.totals(computed, view=DELTA, start=YEAR[0], end=YEAR[1])
    pob_3 = ("Contract 3", "POB #3", "5003")
    # Gross: deferred debits C1 21001 +800.00 and C3 21001 +2,600.00 with no unbilled A/R lines, and
    # the revenue lines per obligation. C3 POB #5 is added by the step 13 exercise and takes its SKU
    # revenue account (L3-2-Q-24).
    assert {key: amount for key, amount in gross.items() if key != pob_3} == {
        ("Contract 1", None, "21001"): usd("800.00"),
        ("Contract 1", "POB #2", "5002"): cr("211.07"),
        ("Contract 1", "POB #3", "5003"): cr("86.03"),
        ("Contract 1", "POB #4", "5001"): cr("502.90"),
        ("Contract 3", None, "21001"): usd("2600.00"),
        ("Contract 3", "POB #1", "5001"): cr("678.02"),
        ("Contract 3", "POB #2", "5002"): cr("464.52"),
        ("Contract 3", "POB #5", "5003"): cr("1268.11"),
    }
    # C3 POB #3: the engine posts the largest-remainder allocation of the step 12 boundary, 189.35
    # against the legacy float 189.343962 printed as 189.34. GT-18 ties each POB's revenue to the
    # cumulative revenue within 0.01 (L3-2-Q-22).
    assert abs(gross[pob_3] - cr("189.34")) <= 1
    # Delta differences: C1 21001 +646.00, POB #2 −145.07, POB #3 +1.97; C3 21001 +2,400.00 and
    # POB #3 +10.66 within the same unit; the other lines equal the gross lines.
    assert {key: amount for key, amount in delta.items() if key != pob_3} == {
        ("Contract 1", None, "21001"): usd("646.00"),
        ("Contract 1", "POB #2", "5002"): cr("145.07"),
        ("Contract 1", "POB #3", "5003"): usd("1.97"),
        ("Contract 1", "POB #4", "5001"): cr("502.90"),
        ("Contract 3", None, "21001"): usd("2400.00"),
        ("Contract 3", "POB #1", "5001"): cr("678.02"),
        ("Contract 3", "POB #2", "5002"): cr("464.52"),
        ("Contract 3", "POB #5", "5003"): cr("1268.11"),
    }
    assert abs(delta[pob_3] - usd("10.66")) <= 1
    assert sum(gross.values()) == 0 and sum(delta.values()) == 0  # both views balance
    assert not any(account in ("15001", "15002") for _, _, account in gross)
    # Contracts 2 and 4 credit the VC pseudo-line (Current Billing −100) with nothing billed on it.
    # REFUND_EXCEEDS_BILLED covers non-VC billing only (04 table 15.4-A #25; DEV-022), so stage 01
    # accepts it (L6-2-Q-4, closing L3-2-Q-23), and VC #1 holds the legacy step 14 figures.
    for contract, billed in (("Contract 2", "-100.00"), ("Contract 4", "-200.00")):
        (asc606,) = [
            book for book in compute(golden(contract, "14")).books if book.book_code == "ASC606"
        ]
        (vc,) = [
            item for item in asc606.obligation_versions if item.subject_key == f"{contract}/VC %231"
        ]
        columns = {
            name: vc.columns[name]
            for name in ("billed_cum", "remaining_billing", "position_obligation")
        }
        assert columns == {
            "billed_cum": usd(billed),
            "remaining_billing": 0,
            "position_obligation": usd(billed),
        }
    # D-87 L6-2-Q-5: the TC-JE-08 journals of Contracts 2 and 4. Gross deferred debits C2 21002
    # +1,100.00 and C4 21002 +1,200.00 with no unbilled A/R lines, the six revenue lines, and the
    # delta differences C4 21002 +1,050.00 and POB #1 −329.69; the other delta lines equal gross.
    computed = [
        *intent_totals.golden("Contract 2", "14"),
        *intent_totals.golden("Contract 4", "14"),
    ]
    gross = intent_totals.totals(computed, view=GROSS, start=YEAR[0], end=YEAR[1])
    delta = intent_totals.totals(computed, view=DELTA, start=YEAR[0], end=YEAR[1])
    # C4 POB #3: TC-JE-08 prints −293.93, the legacy defect DEVIATIONS §4.1 corrects to −293.92
    # (bound A 293.92 below round(X) 293.93; the printed full-year report balances only by offset,
    # C4 revenue lines 1,200.01 against 1,200.00). Asserted to the cent like every other C2 and C4
    # figure, with no one-minor-unit tolerance (D-88 L7-5-Q-5).
    revenue = {
        ("Contract 2", "POB #1", "5001"): cr("573.20"),
        ("Contract 2", "POB #2", "5002"): cr("385.19"),
        ("Contract 2", "POB #3", "5003"): cr("141.61"),
        ("Contract 4", "POB #2", "5002"): cr("426.39"),
        ("Contract 4", "POB #3", "5003"): cr("293.92"),
    }
    assert gross == {
        ("Contract 2", None, "21002"): usd("1100.00"),
        ("Contract 4", None, "21002"): usd("1200.00"),
        ("Contract 4", "POB #1", "5001"): cr("479.69"),
        **revenue,
    }
    assert delta == {
        ("Contract 2", None, "21002"): usd("1100.00"),
        ("Contract 4", None, "21002"): usd("1050.00"),
        ("Contract 4", "POB #1", "5001"): cr("329.69"),
        **revenue,
    }
    assert sum(gross.values()) == 0 and sum(delta.values()) == 0


def test_tc_je_10_pob_vc_zero_modification_delta() -> None:
    base = golden("Contract 1", "04")
    changed = amended(
        base,
        "MOD-PV",
        date(2023, 1, 31),
        "pob_price_change",
        [template_line(base, "POB #1", "0", "0")],
    )
    command, reclass = intent_totals.computations(changed)
    (asc606,) = [book for book in command.output.books if book.book_code == "ASC606"]
    assert {v.columns["last_modification_key"] for v in asc606.obligation_versions} == {"MOD-PV"}
    computed = [command, reclass, *intent_totals.golden("Contract 2", "04")]
    found = intent_totals.totals(computed, view=DELTA, start=JANUARY[0], end=JANUARY[1])
    assert found == TC_JE_02  # the legacy defect gave 21001 −12.31, 5002 +13.47, 5003 +127.68


def with_pre_standard(value: InputBundle, amounts: Mapping[str, str]) -> InputBundle:
    """``value`` with its pre-standard revenue events re-keyed to ``amounts`` (obligation → amount),
    in stream order, so the stream keeps its versions."""
    events = list(value.events)
    positions = [
        i for i, event in enumerate(events) if event.event_type == "PRE_STANDARD_REVENUE_RECORDED"
    ]
    assert len(positions) == len(amounts)
    for position, (key, amount) in zip(positions, sorted(amounts.items()), strict=True):
        payload = {"obligation_key": key, "amount": Decimal(amount)}
        events[position] = dataclasses.replace(
            events[position],
            obligation_keys=(key,),
            payload=payload,
            payload_sha256=sha256_hex(payload),
        )
    return dataclasses.replace(value, events=tuple(events))


def test_tc_prospective_14_modification_reposts_no_pre_standard() -> None:
    # Probe P-08: the 31 January upload books pre-standard revenue 360.00 (POB #1, 5001) and 70.00
    # (POB #3, 5003); a prospective modification follows on 15 February (L3-2-Q-25).
    upload = with_pre_standard(golden("Contract 1", "04"), {"POB #1": "360.00", "POB #3": "70.00"})
    head = max(event.stream_version for event in upload.events)
    changed = amended(
        upload,
        "MOD-P08",
        date(2023, 2, 15),
        "prospective",
        [template_line(upload, "POB #1", "0", "0")],
    )
    computed = intent_totals.computations(changed)
    february = intent_totals.totals(
        computed, view=DELTA, start=date(2023, 2, 15), end=date(2023, 2, 15)
    )
    assert february == {}  # the legacy defect gave Dr 5001 360, Dr 5003 70 / Cr 21001 430
    assert intent_totals.totals(computed, start=date(2023, 2, 15), end=date(2023, 2, 15)) == {}
    command, _ = computed
    (legacy,) = [book for book in command.output.books if book.book_code == "LEGACY"]
    assert {intent.posting_period_key for intent in legacy.posting_intents} == {"FY2023-P01"}
    january = intent_totals.totals(computed, view=DELTA, start=JANUARY[0], end=JANUARY[1])
    assert january == {
        ("Contract 1", None, "21001"): cr("134.31"),  # 295.69 − 430.00
        ("Contract 1", "POB #1", "5001"): usd("231.16"),  # 360.00 − 128.84
        ("Contract 1", "POB #2", "5002"): cr("118.53"),
        ("Contract 1", "POB #3", "5003"): usd("21.68"),  # 70.00 − 48.32
    }
    # The modification version carries no pre-standard amount; the cumulative rolls (S13-R-10).
    version = compute(with_head(changed, head))
    (asc606,) = [book for book in version.books if book.book_code == "ASC606"]
    measures = {
        str(item.columns["obligation_key"]): (
            item.columns["pre_standard_revenue_amount"],
            item.columns["pre_standard_revenue_cum"],
        )
        for item in asc606.obligation_versions
    }
    assert measures == {
        "POB #1": (0, usd("360.00")),
        "POB #2": (0, 0),
        "POB #3": (0, usd("70.00")),
        "POB #4": (0, 0),
    }


def test_tc_rm_12_retro_zero_modification_delta() -> None:
    base = golden("Contract 1", "04")
    changed = amended(
        base,
        "MOD-RM12",
        date(2023, 2, 1),
        "retrospective",
        [template_line(base, "POB #2", "0", "0")],
    )
    window = {"start": date(2023, 1, 1), "end": date(2023, 2, 28)}
    found = intent_totals.totals(intent_totals.computations(changed), view=DELTA, **window)
    listed = [
        ("Contract 1", "POB #2", "5002"),
        ("Contract 1", "POB #3", "5003"),
        ("Contract 1", None, "21001"),
    ]
    assert {key: found[key] for key in listed} == {
        ("Contract 1", "POB #2", "5002"): cr("52.53"),
        ("Contract 1", "POB #3", "5003"): usd("39.68"),
        ("Contract 1", None, "21001"): usd("141.69"),
    }  # the legacy defect gave 5002 +13.47, 5003 +127.68, 21001 −12.31
    # The retrospective line adds no line: the window equals the stream without it.
    assert found == intent_totals.totals(
        intent_totals.golden("Contract 1", "04"), view=DELTA, **window
    )


def test_tc_pob_vc_13_periodic_measures_zero() -> None:
    base = golden("Contract 4", "05")
    head = max(event.stream_version for event in base.events)
    changed = amended(
        base,
        "MOD-VC13",
        date(2023, 3, 1),
        "pob_price_change",
        [template_line(base, "POB #2", "0", "50")],
    )
    window = {"start": date(2023, 2, 28), "end": date(2023, 3, 1)}
    found = intent_totals.totals(intent_totals.computations(changed), view=DELTA, **window)
    assert found == {
        ("Contract 4", None, "21002"): cr("38.71"),
        ("Contract 4", "POB #1", "5001"): usd("38.71"),
    }  # the legacy defect re-posted the carried 150.00: 21002 −188.71, 5001 +188.71
    version = compute(with_head(changed, head))
    (asc606,) = [book for book in version.books if book.book_code == "ASC606"]
    periodic = (
        "delivered_quantity",
        "revenue_amount",
        "ssp_delivered",
        "billed_amount",
        "pre_standard_revenue_amount",
        "catch_up_amount",
    )
    for item in asc606.obligation_versions:
        assert item.columns["effective_date"] == date(2023, 3, 1)
        assert tuple(item.columns[name] for name in periodic) == (0,) * len(periodic), (
            item.subject_key
        )
    pob_1 = next(
        item for item in asc606.obligation_versions if item.columns["obligation_key"] == "POB #1"
    )
    assert pob_1.columns["pre_standard_revenue_cum"] == usd("150.00")
