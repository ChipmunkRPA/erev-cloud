"""JET-16 accrual and JET-17 unconditional and receipt part targets (ENGINE_SPEC S04-R-18, S04-R-19;
ENGINE_SPEC_B Table 14-A rows "JET-16 accrual; claim release" and "JET-17 unconditional; receipt";
POLICIES JET-16 CHK-134, JET-17 CHK-135; lane L5-5, L4-3-Q-19).

Stage 04 publishes ``warranty_accrual_cum`` per product obligation (performing entity) and
``noncash_asset_recognised_cum`` per ``<contract>@<entity>``, and the templates and amount classes
of both parts exist, but ``PartInputs`` had no field for them, so an assurance warranty accrued
nothing and a noncash right posted no asset. The receipt part reads the new
``noncash_received_cum``, the carrying amount of the ``PAYMENT_RECEIVED`` lines with
``form = NONCASH`` (04 §16.3 rev 1.2). No database.
"""

from __future__ import annotations

from erev_engine.enums import BookCode
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import part_targets
from erev_engine.stages.state import Target
from support import bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

ENTITY = bundles.ENTITY_CODE
OBLIGATION = f"{CONTRACT_KEY}/L1-EQUIP"
SUBJECT = f"{CONTRACT_KEY}@{ENTITY}"


def _target(measure: str, subject: str, period: str, amount: str) -> Target:
    node = f"{measure}:{subject}:{period}"
    return Target(BookCode.ASC606, ENTITY, subject, measure, period, None, usd(amount), None, node)


def _state() -> FxState:
    return FxState(
        allocated=allocated_state([]),
        costs=None,  # type: ignore[arg-type]
        layer_movements=(),
        layer_balances=(),
        functional_targets=(),
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )


def _parts(inputs: PartInputs) -> dict[tuple[str, str, str], tuple[int, tuple[object, ...]]]:
    ctx = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    return {
        (p.part, p.subject_key, p.period_key): (p.amount_txn, p.value_inputs)
        for p in part_targets(ctx, _state(), inputs)
    }


def test_jet_16_accrual_from_the_warranty_accrual() -> None:
    # CHK-134: one unit transferred on 10 January at assurance_cost_per_unit 200.00.
    warranties = (
        _target("warranty_accrual_cum", OBLIGATION, "FY2026-P01", "200.00"),
        _target("warranty_accrual_cum", OBLIGATION, "FY2026-P02", "200.00"),
    )
    found = _parts(PartInputs(warranties=warranties))
    node = f"warranty_accrual_cum:{OBLIGATION}:FY2026-P01"
    assert found == {
        ("JET-16 accrual", OBLIGATION, "FY2026-P01"): (usd("200.00"), ((node, 1),)),
        ("JET-16 accrual", OBLIGATION, "FY2026-P02"): (
            usd("200.00"),
            ((f"warranty_accrual_cum:{OBLIGATION}:FY2026-P02", 1),),
        ),
    }


def test_jet_17_unconditional_and_receipt_from_the_noncash_measures() -> None:
    # CHK-135: four weeks completed in January (4,000.00); week 1 shares received at 1,000.00.
    noncash = (
        _target("noncash_asset_recognised_cum", SUBJECT, "FY2026-P01", "4000.00"),
        _target("noncash_received_cum", SUBJECT, "FY2026-P01", "1000.00"),
    )
    found = _parts(PartInputs(noncash=noncash))
    assert {key: amount for key, (amount, _) in found.items()} == {
        ("JET-17 unconditional", SUBJECT, "FY2026-P01"): usd("4000.00"),
        ("JET-17 receipt", SUBJECT, "FY2026-P01"): usd("1000.00"),
    }
    assert found[("JET-17 receipt", SUBJECT, "FY2026-P01")][1] == (
        (f"noncash_received_cum:{SUBJECT}:FY2026-P01", 1),
    )


def test_a_warranty_input_of_another_measure_is_refused() -> None:
    wrong = (_target("noncash_received_cum", OBLIGATION, "FY2026-P01", "1.00"),)
    try:
        _parts(PartInputs(warranties=wrong))
    except ValueError as error:
        assert "warranty_accrual_cum" in str(error)
    else:
        raise AssertionError("a warranty part input of another measure must raise (CV-45)")
