"""Stage 11: contract costs and loss contracts (ENGINE_SPEC_B §11; BUILD_SPEC ENC-15, ENC-16).

``run`` gates every ``COST_INCURRED`` cost to obtain or to fulfil a contract (§11.2.1, §11.2.2;
S11-R-01 to S11-R-05) and amortises each capitalised asset by segments (§11.2.3; S11-R-06,
S11-R-07). The assets of one contract share a period loop in which renewal changes, commission
clawbacks and termination acceleration start segments (§11.2.6; S11-R-12, S11-R-13) before the
assets that share their related obligations are tested at every period end within the horizon,
reversing impairments in a book under POL-144 ``REQUIRED_CAPPED`` (§11.2.4, §11.2.5; S11-R-08 to
S11-R-11b). The loss test runs per contract at the POL-150 unit (§11.2.7; S11-R-14 to S11-R-17). It
publishes the T-CON-15 specs, the T-CON-16 and T-CON-17 values with their cumulative targets, the
costs expensed with their reason, the ``COST_AMORTIZATION`` and ``LOSS_PROVISION_RELEASE`` schedule
lines and the findings. ``CostLossState.balances`` carries the stage 10 output unchanged for stages
12 to 15, and ``allocated`` the consumed state (§0.4). Submodules are private to the stage
(DG-ENG-07). ``POLICY_KEYS`` and ``FORMULA_IDS`` feed the ``STAGES`` entry (ENGINE_SPEC §0.10;
Table 13-A row 11). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s11_costs_loss import balances, capitalise, impair, loss
from erev_engine.stages.s11_costs_loss.amortise import CostSegment
from erev_engine.stages.s11_costs_loss.capitalise import CostAssetSpec, ExpensedCost
from erev_engine.stages.s11_costs_loss.impair import CostAssetMeasures
from erev_engine.stages.s11_costs_loss.loss import LossMeasures
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    Finding,
    ScheduleLineOut,
    Target,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "POLICY_KEYS",
    "CostAssetMeasures",
    "CostAssetSpec",
    "CostLossState",
    "CostSegment",
    "ExpensedCost",
    "LossMeasures",
    "run",
]

# ENGINE_SPEC_B Table 13-A row 11 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "costs.amortisation_pattern",
    "costs.amortisation_period",
    "costs.commensurate_ratio",
    "costs.fulfilment_capitalisation",
    "costs.impairment_reversal",
    "costs.obtain_expedient",
    "costs.termination_acceleration",
    "loss.consideration_basis",
    "loss.cost_basis",
    "loss.scope",
    "loss.unit",
    "recognition.time_convention",
)
# The registered formulas stage 11 emits (§11.5), sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "cost.accelerate.v1",
    "cost.amortise.proportional.v1",
    "cost.amortise.straight_line.v1",
    "cost.capitalise.v1",
    "cost.carrying.v1",
    "cost.clawback.v1",
    "cost.expense_reason.v1",
    "cost.impair.ifrs_reversal.v1",
    "cost.impair.us.v1",
    "cost.member_sum.v1",
    "cost.recoverable.v1",
    "loss.expected_margin.v1",
    "loss.movement.v1",
    "loss.required_provision.v1",
    "loss.tp_unconstrained.v1",
)


@dataclass(frozen=True, slots=True)
class CostLossState:
    """Stage 11 output (ENGINE_SPEC_B §11.1)."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    balances: BalanceState  # stage 10 output (revenue, positions, presentation) for stages 12 to 15
    cost_assets: tuple[Target, ...]  # per asset and period: capitalised, amortised, impaired,
    # reversed, clawed back, accelerated, carrying (§11.5 measures)
    cost_asset_specs: tuple[CostAssetSpec, ...]  # T-CON-15, sorted by asset key
    # (asset key, period key) -> T-CON-16 values
    cost_asset_measures: Mapping[tuple[str, str], CostAssetMeasures]
    expensed_costs: tuple[ExpensedCost, ...]  # ENG-06 order
    schedule_lines: tuple[ScheduleLineOut, ...]  # COST_AMORTIZATION, then LOSS_PROVISION_RELEASE
    findings: tuple[Finding, ...]  # CV-43 order
    # per loss unit and period: tp_unconstrained_credit_adjusted, expected_margin,
    # loss_provision_required, provision_movement (§11.5 measures; JET-12)
    loss_provisions: tuple[Target, ...] = ()
    # (loss unit key, period key) -> T-CON-17 values
    loss_measures: Mapping[tuple[str, str], LossMeasures] = MappingProxyType({})
    # T-CON-09 ``cost_asset_carrying`` and ``loss_provision`` per member "<contract>@<entity>" and
    # period with their nodes (DG-KRN-EXP-01; D-97 (8); ``balances.member_sums``).
    member_sums: tuple[Target, ...] = ()


def run(ctx: BookContext, st: BalanceState, tb: TraceBuilder) -> CostLossState:
    """Contract cost assets and loss provisions of one book (§11.2)."""
    allocated = st.allocated
    gated = capitalise.gate(ctx, allocated, tb)
    by_contract: dict[str, list[CostAssetSpec]] = {}
    for spec in gated.specs:
        by_contract.setdefault(spec.contract_key, []).append(spec)
    targets: list[Target] = []
    lines: list[ScheduleLineOut] = []
    findings: list[Finding] = list(gated.findings)
    measures: dict[tuple[str, str], CostAssetMeasures] = {}
    for key in sorted(by_contract):
        measured = impair.measure(ctx, st, by_contract[key], gated.capitalised_nodes, tb)
        targets.extend(measured.targets)
        lines.extend(measured.lines)
        findings.extend(measured.findings)
        measures.update(measured.measures)
    losses = loss.measure(ctx, st, tb)
    member_of = {
        spec.asset_key: contract_entity_subject_key(spec.contract_key, spec.entity)
        for spec in gated.specs
    }
    member_of.update(
        {
            item.unit_key: contract_entity_subject_key(item.contract_key, item.entity)
            for item in losses.measures.values()
        }
    )
    sums = balances.member_sums(
        ctx,
        st.member_balances,
        carrying={
            key: (item.carrying_amount, item.trace_nodes["carrying_amount"])
            for key, item in measures.items()
        },
        provisions={
            key: (item.provision_balance, item.trace_nodes["loss_provision_required"])
            for key, item in losses.measures.items()
        },
        member_of=member_of,
        tb=tb,
    )
    return CostLossState(
        allocated=allocated,
        balances=st,
        cost_assets=tuple(targets),
        cost_asset_specs=gated.specs,
        cost_asset_measures=MappingProxyType(measures),
        expensed_costs=gated.expensed,
        schedule_lines=tuple(lines) + losses.lines,
        findings=tuple(sorted([*findings, *losses.findings], key=lambda item: item.sort_key())),
        loss_provisions=losses.targets,
        loss_measures=losses.measures,
        member_sums=sums,
    )
