"""Golden reclass attribution under POL-121 ``CUMULATIVE_SSP_DELIVERED`` (ENC-14).

Legacy 02 §7.3 TC-delivery-02, 04, 07 and 09 (GT-05, GT-09), legacy 06 §7.3 TC-JE-01 and legacy 03
§7.3 TC-19 (probe P-17; DEV-057). Contracts 1 and 2 of the legacy UAT (legacy 02 §5.3, §5.7) are
built as ``AllocatedState`` against the documented contract (D-81 integration after merge): X =
contract price × extended SSP ÷ total SSP, posted allocations by largest remainder (ALG-01
§2.1.2), measure ``UNITS_DELIVERED`` with each line's unit SSP, under the ``LEGACY_PARITY`` preset.
Upload rows become delivery and billing events on the upload date (04 LM-TPL-PROG-01 to 09). Exact
values are compared at the six places of the legacy figures: the contract position is
``position_contract_entity`` at the version date, and each reclass the exact quota of the
``netting_reclass_amount`` node at ``-`` (Table 0.9-A; DG-PAR-05 ``uar_reclass_field``). The dates
of the TC-delivery-09 events (E20, E20b) are not recorded in the legacy text; the tests use 31
January and 28 February 2023.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.money import format_exact, largest_remainder
from erev_engine.stages import s09_recognition, s10_billing_balances
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import (
    AllocationSegment,
    EventView,
    ObligationState,
    SegmentCause,
)
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support.bundles import entity
from support.recognition import (
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

PARITY = book_context(entity(start=date(2023, 1, 1), months=12), preset="LEGACY_PARITY")
SETUP, TERM_END = date(2023, 1, 1), date(2023, 12, 31)
STEP_04, STEP_06, STEP_07 = date(2023, 1, 31), date(2023, 3, 31), date(2023, 4, 30)
GROUP_AT_ENTITY = "CG-1@US01"
# (contract price, ((POB, quantity, extended SSP), ...)): legacy 02 §5.3, §5.7.
CONTRACTS: Mapping[str, tuple[int, tuple[tuple[str, str, int], ...]]] = {
    "Contract 1": (
        1300,
        (
            ("POB #1", "5", 500),
            ("POB #2", "2", 368),
            ("POB #3", "1", 150),
            ("POB #4", "1000", 1000),
        ),
    ),
    "Contract 2": (
        900,
        (("POB #1", "8", 612), ("POB #2", "3", 408), ("POB #3", "1", 150), ("VC #1", "1", 0)),
    ),
}
Row = tuple[date, str, str, str]  # (upload date, POB, Current Delivery, Current Billing)
CONTRACT_1_STEP_04: tuple[Row, ...] = (
    (STEP_04, "POB #1", "2", "100"),
    (STEP_04, "POB #2", "1", "100"),
    (STEP_04, "POB #3", "0.5", "100"),
)
CONTRACT_2: tuple[Row, ...] = (
    (STEP_04, "POB #1", "1", "0"),
    (STEP_06, "POB #3", "0.4", "0"),
    (STEP_07, "POB #1", "0", "20"),
)


def _events(contract_key: str, rows: Sequence[Row]) -> list[EventView]:
    """Upload rows as delivery and billing events (version 1 is ``CONTRACT_BOOKED``)."""
    events: list[EventView] = []
    for upload, key, delivery, billing in rows:
        if Decimal(delivery) > 0:
            payload = {"obligation_key": key, "quantity": Decimal(delivery), "trigger": "DELIVERY"}
            events.append(
                event_view(
                    contract_key,
                    len(events) + 2,
                    "DELIVERY_RECORDED",
                    upload,
                    payload,
                    obligation_keys=[key],
                )
            )
        if Decimal(billing) > 0:
            invoice = {
                "invoice_number": f"INV-{upload.isoformat()}",
                "line_external_id": key,
                "obligation_key": key,
                "amount": Decimal(billing),
                "issue_date": upload,
            }
            events.append(
                event_view(
                    contract_key,
                    len(events) + 2,
                    "BILLING_RECORDED",
                    upload,
                    invoice,
                    obligation_keys=[key],
                )
            )
    return events


def _units(
    contract_key: str, key: str, segments: Sequence[AllocationSegment], *, kind: str = "STANDARD"
) -> ObligationState:
    return obligation(
        key,
        segments,
        contract_key=contract_key,
        method="UNITS_DELIVERED",
        convention=None,
        start=SETUP,
        quantity=segments[0].totals.quantity,
        kind=kind,
    )


def _units_segment(
    x_exact: Fraction, a_posted: int, quantity: str, unit_ssp: Fraction
) -> AllocationSegment:
    seg = segment(
        x_exact,
        a_posted,
        start=SETUP,
        end=TERM_END,
        quantity=Fraction(Decimal(quantity)),
        measure="UNITS_DELIVERED",
    )
    return dataclasses.replace(seg, unit_ssp=unit_ssp)


def _inception(contract_key: str) -> list[ObligationState]:
    price, lines = CONTRACTS[contract_key]
    total = sum(ssp for _, _, ssp in lines)
    posted = largest_remainder(
        price * 100, [Fraction(ssp) for _, _, ssp in lines], [key for key, _, _ in lines]
    )
    return [
        _units(
            contract_key,
            key,
            [
                _units_segment(
                    Fraction(price * ssp, total),
                    a_posted,
                    quantity,
                    Fraction(ssp) / Fraction(quantity),
                )
            ],
        )
        for (key, quantity, ssp), a_posted in zip(lines, posted, strict=True)
    ]


def _run(
    contract_key: str, rows: Sequence[Row], obligations: Sequence[ObligationState] | None = None
) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one golden contract (its own group); boundary events are faked."""
    obligations = _inception(contract_key) if obligations is None else obligations
    boundaries = {
        seg.event_key: seg.effective_date
        for ob in obligations
        for seg in ob.segments
        if seg.event_key is not None
    }
    amended = [
        event_view(
            contract_key,
            int(key.rsplit("-", 1)[1]),
            "CONTRACT_AMENDED",
            when,
            {"modification_id": f"MOD-{when.isoformat()}"},
        )
        for key, when in sorted(boundaries.items())
    ]
    st = allocated_state(
        obligations,
        events=[*_events(contract_key, rows), *amended],
        inception=SETUP,
        statuses=((SETUP, "ACTIVE"),),
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, PARITY, st)
    recognition = s09_recognition.run(PARITY, st, tb)
    state = s10_billing_balances.run(PARITY, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _six(value: Fraction) -> Decimal:
    """An exact value at the six places of the legacy figures (legacy 02 §3.13)."""
    return Decimal(format_exact(value, 6))


def _position(state: BalanceState, contract_key: str) -> Decimal:
    """``position_contract_entity`` exact at the version date (legacy POSC)."""
    measures = state.obligation_measures[f"{contract_key}/POB #1"]
    return _six(measures.position_contract_entity_exact)


def _reclass(state: BalanceState, contract_key: str) -> dict[str, Decimal]:
    """``netting_reclass_amount`` exact at the version date per POB (legacy RECL)."""
    prefix = f"{contract_key}/"
    return {
        key.removeprefix(prefix): _six(measures.netting_reclass_amount_exact)
        for key, measures in state.obligation_measures.items()
        if key.startswith(prefix)
    }


def test_tc_delivery_02_contract2_reclass() -> None:
    state, trace = _run("Contract 2", CONTRACT_2[:1])
    assert _position(state, "Contract 2") == Decimal("-58.846154")
    assert _reclass(state, "Contract 2") == {
        "POB #1": Decimal("58.846154"),
        "POB #2": Decimal("0"),
        "POB #3": Decimal("0"),
        "VC #1": Decimal("0"),
    }
    first = state.obligation_measures["Contract 2/POB #1"]
    assert (first.netting_reclass_amount, first.netting_reclass_role) == (
        usd("58.85"),
        "CONTRACT_ASSET",
    )
    node_id = first.trace_nodes["netting_reclass_amount"]
    assert node_id == "netting_reclass_amount:Contract 2/POB #1:-"
    node = next(item for item in trace.nodes if item.id == node_id)
    # The residue is exact 58.846153… less posted 58.85 (Table 0.9-A; DG-KRN-EXP-03).
    assert (node.value, node.rounding_residue) == ("58.85", "-0.003846153846153846")


def test_tc_delivery_04_contract2_reclass() -> None:
    state, _ = _run("Contract 2", CONTRACT_2[:2])
    assert _position(state, "Contract 2") == Decimal("-105.000000")
    reclass = _reclass(state, "Contract 2")
    assert (reclass["POB #1"], reclass["POB #3"]) == (Decimal("58.846154"), Decimal("46.153846"))
    assert (reclass["POB #2"], reclass["VC #1"]) == (Decimal("0"), Decimal("0"))


def test_tc_delivery_07_billing_against_asset() -> None:
    state, _ = _run("Contract 2", CONTRACT_2)
    assert _position(state, "Contract 2") == Decimal("-85.000000")
    reclass = _reclass(state, "Contract 2")
    assert (reclass["POB #1"], reclass["POB #3"]) == (Decimal("47.637363"), Decimal("37.362637"))
    # Posted: 85.00 over cumulative SSP delivered 76.5 and 60 (legacy JE Dr 21002 20.00 / Cr 15002
    # 20.00 is the reversal of 105.00 less the new 85.00).
    april = {
        item.subject_key: item.amount
        for item in state.netting_reclass
        if item.period_key == "FY2023-P04"
    }
    assert (april["Contract 2/POB #1"], april["Contract 2/POB #3"]) == (usd("47.64"), usd("37.36"))


def test_tc_delivery_09_reclass_key_ssp_delivered() -> None:
    event_1: tuple[Row, ...] = (
        (date(2023, 1, 31), "POB #1", "5", "0"),
        (date(2023, 1, 31), "POB #3", "0", "400"),
    )
    first, _ = _run("Contract 1", event_1)
    assert _position(first, "Contract 1") == Decimal("77.898910")
    assert set(_reclass(first, "Contract 1").values()) == {Decimal("0")}
    assert not first.reclass_entries
    second, trace = _run("Contract 1", (*event_1, (date(2023, 2, 28), "POB #2", "2", "0")))
    assert _position(second, "Contract 1") == Decimal("-159.167493")
    assert _reclass(second, "Contract 1") == {
        "POB #1": Decimal("91.686344"),
        "POB #2": Decimal("67.481149"),
        "POB #3": Decimal("0"),  # billed but not delivered: no SSP delivered
        "POB #4": Decimal("0"),
    }
    node = next(
        item for item in trace.nodes if item.id == "netting_reclass_amount:Contract 1/POB #1:-"
    )
    assert (node.params["basis"], node.params["weights"]) == ("ssp_delivered", "500|368|0|0")


def test_tc_je_01_january_reclass_attribution() -> None:
    contract_2, _ = _run("Contract 2", CONTRACT_2[:1])
    january = {
        item.subject_key: item
        for item in contract_2.netting_reclass
        if item.period_key == "FY2023-P01"
    }
    pob_1 = "Contract 2/POB #1"
    assert january[pob_1].amount == usd("58.85")
    # Units delivered beside other non-zero allocations are a conditional right (ALG-03 table
    # 2.4-A). The preset maps CONTRACT_ASSET and UNBILLED_RECEIVABLE to the POB's Unbilled A/R
    # account 15002, the account of the TC-JE-01 line (POLICIES §6.3; DEV-074; L2-4-Q-28).
    assert (january[pob_1].receivable, january[pob_1].asset, january[pob_1].role) == (
        0,
        usd("58.85"),
        "CONTRACT_ASSET",
    )
    assert {key: item.amount for key, item in january.items() if key != pob_1} == {
        "Contract 2/POB #2": 0,
        "Contract 2/POB #3": 0,
        "Contract 2/VC #1": 0,
    }
    entries = sorted(
        (
            entry.kind,
            entry.subject_key,
            entry.debit_role,
            entry.credit_role,
            entry.amount,
            entry.posting_date,
        )
        for entry in contract_2.reclass_entries
        if entry.period_key == "FY2023-P01"
    )
    assert entries == [
        ("NETTING_RECLASS", pob_1, "CONTRACT_ASSET", "CONTRACT_LIABILITY", usd("58.85"), STEP_04),
        (
            "NETTING_RECLASS_REVERSAL",
            pob_1,
            "CONTRACT_LIABILITY",
            "CONTRACT_ASSET",
            usd("58.85"),
            date(2023, 2, 1),
        ),
    ]
    contract_1, _ = _run("Contract 1", CONTRACT_1_STEP_04)
    net = next(
        target.value
        for target in contract_1.positions
        if (target.subject_key, target.period_key) == (GROUP_AT_ENTITY, "FY2023-P01")
    )
    assert net == usd("4.31")  # a liability: nothing to reclassify
    assert (
        sum(item.amount for item in contract_1.netting_reclass if item.period_key == "FY2023-P01")
        == 0
    )
    assert not contract_1.reclass_entries


def test_tc_prospective_19_one_reclass_policy() -> None:
    contract_key, boundary = "Contract P17", date(2023, 1, 20)
    event_key = f"{contract_key}/EV-000099"
    goods = _units_segment(Fraction(380), usd("380.00"), "2", Fraction(180))
    priced_vc = _units_segment(Fraction(0), 0, "2", Fraction(10))  # a VC SKU with a list price

    def prospective(seg: AllocationSegment, revenue: str) -> AllocationSegment:
        """A 25-13(a) boundary after one unit of each line: the remaining unit at the same rate."""
        after = segment(
            seg.x_exact,
            seg.a_posted,
            start=boundary,
            end=TERM_END,
            basis="PROSPECTIVE",
            cause=SegmentCause.MODIFICATION,
            event_key=event_key,
            base_revenue_posted=usd(revenue),
            base_revenue_exact=Fraction(Decimal(revenue)),
            quantity=Fraction(1),
            base_delivered=Fraction(1),
            measure="UNITS_DELIVERED",
        )
        return dataclasses.replace(after, unit_ssp=seg.unit_ssp)

    rows: tuple[Row, ...] = (
        (date(2023, 1, 10), "POB #1", "1", "0"),
        (date(2023, 1, 10), "VC #1", "1", "0"),
    )
    delivery_path = [
        _units(contract_key, "POB #1", [goods]),
        _units(contract_key, "VC #1", [priced_vc], kind="VC_LINE"),
    ]
    modification_path = [
        _units(contract_key, "POB #1", [goods, prospective(goods, "190.00")]),
        _units(contract_key, "VC #1", [priced_vc, prospective(priced_vc, "0")], kind="VC_LINE"),
    ]
    for obligations in (delivery_path, modification_path):
        state, _ = _run(contract_key, rows, obligations)
        net = next(
            target.value
            for target in state.positions
            if (target.subject_key, target.period_key) == (GROUP_AT_ENTITY, "FY2023-P01")
        )
        assert net == usd("-190.00")
        january = {
            item.subject_key: item.amount
            for item in state.netting_reclass
            if item.period_key == "FY2023-P01"
        }
        # One position function: the VC line takes no share and the total reclass is 190.00.
        assert january == {f"{contract_key}/POB #1": usd("190.00"), f"{contract_key}/VC #1": 0}
        posted = [
            entry
            for entry in state.reclass_entries
            if entry.period_key == "FY2023-P01" and entry.kind == "NETTING_RECLASS"
        ]
        assert sum(entry.amount for entry in posted) == usd("190.00")
