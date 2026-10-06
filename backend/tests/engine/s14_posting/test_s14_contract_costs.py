"""JET-09 contract-cost part targets from the stage 11 cost measures (ENGINE_SPEC_B S11-R-01 to
S11-R-13, Table 14-A rows JET-09a to JET-09f; POLICIES §2.3 CHK-130; lane L5-5, cluster "cost").

Stage 11 publishes ``cost_capitalised``, ``cost_amortised_cum``, ``cost_impaired_cum``,
``cost_impairment_reversed_cum``, ``cost_accelerated_cum``, ``cost_clawback_cum`` and
``carrying_amount`` per cost asset, and the JET-09 templates and amount classes exist, but
``PartInputs`` had no field for them, so a capitalised commission posted no asset, clearing or
amortisation line (COST-S8-CONTRACT-COSTS-EX1, -EX2, JE-CHK-130). No database.
"""

from __future__ import annotations

import pytest
from erev_engine.enums import BookCode
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.s14_posting.targets import part_targets, role_lines
from erev_engine.stages.s14_posting.templates import JET_PARTS
from erev_engine.stages.state import Target
from support import bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

ENTITY = bundles.ENTITY_CODE
OBTAIN = f"{CONTRACT_KEY}/EV-000004"
FULFIL = f"{CONTRACT_KEY}/EV-000005"


def _target(measure: str, subject: str, kind: str, period: str, amount: str) -> Target:
    node = f"{measure}:{subject}:{period}"
    return Target(BookCode.ASC606, ENTITY, subject, measure, period, kind, usd(amount), None, node)


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


def _parts(inputs: PartInputs) -> dict[tuple[str, str, str | None], tuple[int, int]]:
    ctx = book_context(bundles.entity(months=3), book_code="ASC606", currency="USD")
    return {
        (p.part, p.subject_key, p.component): (p.amount_txn, p.time_txn)
        for p in part_targets(ctx, _state(), inputs)
        if p.period_key == "FY2026-P01"
    }


def test_jet_09_capitalisation_and_amortisation_per_cost_kind() -> None:
    # JE-CHK-130: commission 10,000.00 (obtain) and set-up 140,000.00 (fulfil) capitalised on
    # 1 January 2026; January amortisation 119.05 and 1,666.67; carrying 9,880.95 and 138,333.33.
    costs = (
        _target("cost_capitalised", OBTAIN, "OBTAIN", "FY2026-P01", "10000.00"),
        _target("cost_amortised_cum", OBTAIN, "OBTAIN", "FY2026-P01", "119.05"),
        _target("carrying_amount", OBTAIN, "OBTAIN", "FY2026-P01", "9880.95"),
        _target("cost_capitalised", FULFIL, "FULFILL", "FY2026-P01", "140000.00"),
        _target("cost_amortised_cum", FULFIL, "FULFILL", "FY2026-P01", "1666.67"),
        _target("cost_impaired_cum", FULFIL, "FULFILL", "FY2026-P01", "0.00"),
    )
    assert _parts(PartInputs(cost_assets=costs)) == {
        ("JET-09a", OBTAIN, None): (usd("10000.00"), 0),
        ("JET-09b", OBTAIN, "COST_TO_OBTAIN_ASSET"): (usd("119.05"), 0),
        ("JET-09a′", FULFIL, None): (usd("140000.00"), 0),
        ("JET-09b", FULFIL, "COST_TO_FULFILL_ASSET"): (usd("1666.67"), 0),
        ("JET-09c", FULFIL, "COST_TO_FULFILL_ASSET"): (0, 0),
    }
    # The asset role nets at role grain: Dr asset 9,880.95 after the amortisation credit.
    assert [
        (line.account_role, line.signed_txn)
        for line in role_lines(
            JET_PARTS["JET-09b"], usd("119.05"), usd("119.05"), subject_role="COST_TO_OBTAIN_ASSET"
        )
    ] == [("CONTRACT_COST_AMORTIZATION", usd("119.05")), ("COST_TO_OBTAIN_ASSET", -usd("119.05"))]


def test_a_cost_target_without_its_cost_kind_is_refused() -> None:
    wrong = (_target("cost_capitalised", OBTAIN, "RETURN", "FY2026-P01", "1.00"),)
    with pytest.raises(ValueError, match="E-83"):
        _parts(PartInputs(cost_assets=wrong))
