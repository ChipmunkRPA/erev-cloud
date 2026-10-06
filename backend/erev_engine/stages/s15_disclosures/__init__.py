"""Stage 15: close projections and disclosures, engine part (ENGINE_SPEC_B §15.1; EDS-1 to EDS-3).

``run(ctx, st, tb, *, recognition, posted, balances, fx)`` consumes the stage 14 ``PostingState``
and publishes the ``DisclosureState`` of one book at the version date d_v:

- per obligation the remaining performance obligation, its practical-expedient exemptions and its
  time bands; the T-CON-08 ``rpo_amount``; the 50-15 narrative dataset (§15.2.3 S15-R-08 to
  S15-R-11; S15-INV-02; formulas ``disc.rpo.v1``, ``disc.rpo_band.v1``, ``disc.rpo_exemption.v1``);
- the revenue waterfall measures (§15.2.1 S15-R-01, S15-R-02);
- per contracting entity, the RPO rollforward of its period holding d_v (§15.2.3 S15-R-12).
  ``rollforward`` measures any other period;
- per contracting entity, the contract balances rollforward of its period holding d_v in the
  transaction view, and in the functional view when the functional currency differs (§15.2.2
  S15-R-03 to S15-R-07; REQ-FX-007). ``rollforward_balances`` measures any other period or view.

``PostingState`` does not carry the stage 09 schedules and measures, so the book loop binds the
stage 09 state as ``recognition`` (L3-2-Q-26). It also binds the posted amounts as ``posted``,
which the waterfall adds to the stage 14 intents (L3-2-Q-31), and the stage 10 and stage 12 states
as ``balances`` and ``fx``, which the contract balances rollforward reads (L4-3-Q-3). Without both,
``balance_rollforwards`` is empty. Revenue from obligations satisfied in prior periods (§15.2.4
S15-R-13, S15-R-14; EDS-4) is ``prior_period``: the stage 08 ``decompose_prior_period`` targets per
obligation and period through each performing entity's horizon and their contract-entity sums
(``disc.prior_period_sum.v1``), read from ``allocated`` and the posted origins. Disaggregation
(§15.2.5 S15-R-15, S15-R-16; S15-INV-03) is ``disaggregation``: the period's ``REVENUE`` lines of
the consumed intents grouped by the dimension values stage 14 wrote on them, tied to the revenue
journal total. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities import FxState
from erev_engine.stages.s15_disclosures import disaggregation, prior_period, rpo, waterfall
from erev_engine.stages.s15_disclosures import rollforward as balances_rollforward
from erev_engine.stages.s15_disclosures.disaggregation import Disaggregation, DisaggregationRow
from erev_engine.stages.s15_disclosures.prior_period import PriorPeriod
from erev_engine.stages.s15_disclosures.rollforward import (
    BALANCE_LINES,
    BALANCES,
    FUNCTIONAL,
    MEMO_CAUSES,
    TRANSACTION,
    VIEWS,
    BalanceInputs,
    BalanceRollforward,
    balance_inputs,
    rollforward_balances,
)
from erev_engine.stages.s15_disclosures.rpo import (
    ROLLFORWARD_LINES,
    STATUS_25_5,
    Exemption,
    RollforwardRow,
    RpoRollforward,
    RpoRow,
    rollforward,
)
from erev_engine.stages.s15_disclosures.waterfall import Waterfall, WaterfallRow
from erev_engine.stages.state import AllocatedState, BookContext, Finding, PostedIndex
from erev_engine.trace import TraceBuilder

__all__ = [
    "BALANCES",
    "BALANCE_LINES",
    "FORMULA_IDS",
    "FUNCTIONAL",
    "MEMO_CAUSES",
    "POLICY_KEYS",
    "ROLLFORWARD_LINES",
    "TRANSACTION",
    "VIEWS",
    "BalanceInputs",
    "BalanceRollforward",
    "Disaggregation",
    "DisaggregationRow",
    "DisclosureState",
    "Exemption",
    "NarrativeDataset",
    "PriorPeriod",
    "RollforwardRow",
    "RpoRollforward",
    "STATUS_25_5",
    "RpoRow",
    "Waterfall",
    "WaterfallRow",
    "balance_inputs",
    "rollforward",
    "rollforward_balances",
    "run",
]

# Table 13-A row 15 (ENGINE_SPEC_B §13.2.2; s13_books.memo.STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "disclosure.interim_revenue_pack",
    "disclosure.nonpublic_contract_balances_relief",
    "disclosure.nonpublic_cost_relief",
    "disclosure.nonpublic_disaggregation_relief",
    "disclosure.nonpublic_expedient_relief",
    "disclosure.nonpublic_judgements_relief",
    "disclosure.nonpublic_rpo_relief",
    "disclosure.prior_period_pob_revenue_basis",
    "entity.reporting_type",
    "rollforward.opening_liability_consumption",
    "rpo.exemption_original_duration_one_year",
    "rpo.exemption_right_to_invoice",
    "rpo.exemption_royalty_vc",
    "rpo.exemption_vc_wholly_unsatisfied",
    "rpo.time_bands",
)
FORMULA_IDS: Final[tuple[str, ...]] = (
    "disc.prior_period_sum.v1",
    "disc.rpo.v1",
    "disc.rpo_band.v1",
    "disc.rpo_exemption.v1",
)


@dataclass(frozen=True, slots=True)
class NarrativeDataset:
    """S15-R-11: the 50-15 narrative inputs of one group in one book (REQ-TP-003)."""

    group_key: str
    vc_excluded_amount: int  # T-CON-08 ``vc_excluded_amount``: constrained-out VC, minor units
    exempt: tuple[Exemption, ...]  # every exempt amount, (obligation, POL id) order


@dataclass(frozen=True, slots=True)
class DisclosureState:
    """Stage 15 output (ENGINE_SPEC_B §15.1), members built so far."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    as_of: date  # d_v, the version date
    rpo: tuple[RpoRow, ...]  # per obligation with stage 09 measures, subject key order
    rpo_amount: int  # T-CON-08: gross Σ RPO of the included obligations (S15-R-08 rev 1.26)
    rpo_after_exemptions: int  # net: gross − Σ exempt (S15-R-09; the S15-INV-08 closing; D-98 91a)
    narrative: NarrativeDataset  # S15-R-11
    waterfall: Waterfall  # S15-R-01, S15-R-02 (EDS-2)
    rpo_rollforwards: tuple[RpoRollforward, ...]  # S15-R-12 per contracting entity, entity order
    trace_nodes: Mapping[str, str]  # "rpo_amount" -> the group node id
    findings: tuple[Finding, ...] = ()  # stage 15 raises no finding codes (§15.4)
    # S15-R-03 per contracting entity, entity order: TRANSACTION, then FUNCTIONAL when it differs
    balance_rollforwards: tuple[BalanceRollforward, ...] = ()
    # S15-R-13, S15-R-14 (EDS-4): revenue from obligations satisfied in prior periods, per
    # obligation and period through each entity's horizon, and the contract-entity sums
    prior_period: PriorPeriod = PriorPeriod((), ())
    # S15-R-15, S15-R-16, S15-INV-03 (EDS-4): the period's REVENUE lines by dimension value
    disaggregation: Disaggregation = Disaggregation((), MappingProxyType({}), ())


def run(
    ctx: BookContext,
    st: object,
    tb: TraceBuilder,
    *,
    recognition: RecognitionState | None = None,
    posted: PostedIndex | None = None,
    balances: object = None,
    fx: object = None,
) -> DisclosureState:
    """RPO, exemptions, time bands, the narrative dataset, the waterfall, the RPO rollforward, the
    contract balances rollforward and the prior-period revenue of one book at d_v (§15.2.1 to
    §15.2.4)."""
    allocated = getattr(st, "allocated", None)
    if not isinstance(allocated, AllocatedState):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "stage 15 consumes a state that carries the allocated state",
            detail={"rule": "ENGINE_SPEC_B §0.4", "stage": "15"},
        )
    if not isinstance(recognition, RecognitionState):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "stage 15 reads the stage 09 schedules and obligation measures",
            subject_key=allocated.group_code,
            detail={"rule": "L3-2-Q-26", "stage": "15"},
        )
    intents = getattr(st, "posting_intents", ())
    if not isinstance(intents, tuple):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "stage 15 reads the posting intents of the consumed state as a tuple",
            subject_key=allocated.group_code,
            detail={"rule": "ENGINE_SPEC_B §0.4", "stage": "15"},
        )
    found = rpo.build(ctx, allocated, recognition, tb)
    prior = prior_period.build(ctx, allocated, recognition, posted, tb)
    tp = allocated.tp_history[-1] if allocated.tp_history else None
    exempt = tuple(item for row in found.rows for item in row.exemptions)
    entities = sorted(
        {
            ob.contracting_entity
            for ob in allocated.obligations
            if ob.subject_key in recognition.obligation_measures
        }
    )
    rollforwards = tuple(
        rpo.rollforward(
            ctx, allocated, recognition, entity, rpo.period_of(ctx, entity, found.as_of)
        )
        for entity in entities
    )
    balance_rows: list[BalanceRollforward] = []
    if isinstance(balances, BalanceState) and isinstance(fx, FxState):
        records = balances_rollforward.balance_inputs(ctx, balances, fx, intents, posted)
        for entity in entities:
            key = rpo.period_of(ctx, entity, found.as_of)
            balance_rows.append(
                balances_rollforward.rollforward_balances(ctx, allocated, records, entity, key)
            )
            if ctx.entities[entity].functional_currency != ctx.txn_currency:
                balance_rows.append(
                    balances_rollforward.rollforward_balances(
                        ctx, allocated, records, entity, key, view=FUNCTIONAL
                    )
                )
    return DisclosureState(
        allocated=allocated,
        as_of=found.as_of,
        rpo=found.rows,
        rpo_amount=found.total,
        rpo_after_exemptions=found.after_exemptions,
        narrative=NarrativeDataset(
            group_key=allocated.group_code,
            vc_excluded_amount=0 if tp is None else tp.vc_excluded.posted,
            exempt=exempt,
        ),
        waterfall=waterfall.build(ctx, allocated, recognition, intents, posted, found.as_of),
        rpo_rollforwards=rollforwards,
        trace_nodes=MappingProxyType({"rpo_amount": found.node_id}),
        balance_rollforwards=tuple(balance_rows),
        prior_period=prior,
        disaggregation=disaggregation.build(intents),
    )
