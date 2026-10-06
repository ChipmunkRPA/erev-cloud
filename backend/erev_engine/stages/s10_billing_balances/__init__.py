"""Stage 10: billing and balances (ENGINE_SPEC_B §10; BUILD_SPEC ENC-11 to ENC-13).

``run`` attributes billing to obligations per document, counts unconditional billing per contract
and contracting entity, accrues receipts on the contract subject key and measures the obligations'
``billed_cum`` and ``remaining_billing`` (§10.2.1, §10.2.2; S10-R-01 to S10-R-08). It then measures
the refund-liability components and return assets (§10.2.4, §10.2.5; S10-R-13 to S10-R-17), the
receivable contra and accounts receivable in ``ENGINE`` mode (§10.2.6; S10-R-18, S10-R-19), the net
position per (group, contracting entity) and period end with ``position_obligation`` at the version
date (§10.2.3; S10-R-09 to S10-R-12), the presented contract liability, contract asset and unbilled
receivable with the netting reclass attribution, its JET-06 targets and the member-contract
balances (§10.2.7; S10-R-20 to S10-R-23), and the current parts (§10.2.8; S10-R-24, S10-R-25).
Last, it measures the share-based consideration payable from posted related revenue and composes
the JET-14 release (§10.1 ``customer_consideration``; S10-R-26; D-91 C606-03).
``BalanceState.allocated`` carries the consumed state unchanged and ``recognition`` the stage 09
output that stages 11 to 15 read (§0.4; L2-4-Q-7). Submodules are private to the stage
(DG-ENG-07). ``POLICY_KEYS`` and ``FORMULA_IDS`` feed the ``STAGES`` entry (ENGINE_SPEC §0.10;
Table 13-A row 10). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import (
    agent,
    billing,
    classification,
    current_split,
    customer_consideration,
    member_sums,
    position,
    reclass,
    refund_liability,
)
from erev_engine.stages.s10_billing_balances.billing import BalanceMeasures, BillingDocumentOut
from erev_engine.stages.s10_billing_balances.classification import Receipt
from erev_engine.stages.s10_billing_balances.position import PositionComponents
from erev_engine.stages.s10_billing_balances.reclass import ReclassAttribution, ReclassEntry
from erev_engine.stages.s10_billing_balances.refund_liability import RefundComponent
from erev_engine.stages.state import AllocatedState, BookContext, Finding, Target
from erev_engine.trace import TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "POLICY_KEYS",
    "BalanceMeasures",
    "BalanceState",
    "BillingDocumentOut",
    "PositionComponents",
    "Receipt",
    "ReclassAttribution",
    "ReclassEntry",
    "RefundComponent",
    "run",
]

# ENGINE_SPEC_B Table 13-A row 10 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "balance.credit_losses",
    "balance.current_noncurrent",
    "balance.deposit_liability",
    "balance.position_invoice_basis",
    "balance.refund_liability_presentation",
    "balance.right_to_consideration",
    "billing.posting",
    "concession.allocation_basis",
    "position.netting_unit",
    "position.reclass_attribution_key",
    "termination.refund_settlement",
    "tp.sales_tax_exclusion",
)
# The registered formulas stage 10 emits (§10.5), sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "bal.member_sum.v1",
    "bil.ar_balance.v1",
    "bil.attribution.v1",
    "bil.billed_amount.v1",
    "bil.remaining_billing.v1",
    "bil.unconditional_date.v1",
    "pos.accretion_attribution.v1",
    "pos.current_split.v1",
    "pos.net_position.v1",
    "pos.obligation.v1",
    "pos.receivable_contra.v1",
    "pos.reclass_attribution.cumulative_ssp_delivered.v1",
    "pos.reclass_attribution.no_measured_period.v1",
    "pos.reclass_attribution.pob_debit_positions.v1",
    "pos.split_ca_ur.v1",
    "returns.return_asset.v1",
    "rl.concession.v1",
    "rl.consumption.v1",
    "rl.return.v1",
    "rl.return.v2",
    "rl.termination.v1",
    "rl.unclaimed_property.v1",
    "rl.vc_target.v1",
    "tp.cpc_release.v1",
    "tp.cpc_share_based.v1",
)


@dataclass(frozen=True, slots=True)
class BalanceState:
    """Stage 10 output (ENGINE_SPEC_B §10.1), members built so far."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    recognition: RecognitionState  # stage 09 output: revenue targets for stages 11 to 15
    billing: tuple[Target, ...]  # billed_cum, billed_attributed_cum; billed_unconditional_cum
    documents: tuple[BillingDocumentOut, ...]  # per document: lines, unconditional dates
    receipts: tuple[Receipt, ...]  # PAYMENT_RECEIVED on the contract subject key
    paid_cum: Mapping[tuple[str, str], int]  # (contract@entity, period key) -> minor units
    obligation_measures: Mapping[str, BalanceMeasures]  # subject key -> T-CON-11 values
    findings: tuple[Finding, ...]  # CV-43 order
    accounts_receivable: tuple[Target, ...] = ()  # ENGINE mode only (S10-R-19; ENC-13)
    receivable_contra: tuple[Target, ...] = ()  # ENGINE mode only (S10-R-18; ENC-13)
    positions: tuple[Target, ...] = ()  # net_position per "<group>@<entity>" and period (ENC-12)
    position_components: Mapping[tuple[str, str], PositionComponents] = field(
        default_factory=lambda: MappingProxyType({})
    )  # (entity, period key) -> NP components (S10-INV-05)
    refund_components: tuple[RefundComponent, ...] = ()  # §10.2.4, sorted by component key
    refund_liabilities: tuple[Target, ...] = ()  # refund_liability per component and period
    concessions: tuple[Target, ...] = ()  # concession_created_cum per obligation (JET-05c)
    return_assets: tuple[Target, ...] = ()  # return_asset, return_asset_derecognised_cum
    presentation: tuple[Target, ...] = ()  # contract_liability, contract_asset, unbilled_receivable
    accretion_attributed: tuple[Target, ...] = ()  # accretion_attributed_cum (S10-R-20; ENC-13)
    right_classes: Mapping[tuple[str, str], str] = field(
        default_factory=lambda: MappingProxyType({})
    )  # (obligation, period key) -> CONDITIONAL | UNCONDITIONAL (S10-R-21)
    netting_reclass: tuple[ReclassAttribution, ...] = ()  # per obligation and period (ENC-14)
    reclass_entries: tuple[ReclassEntry, ...] = ()  # JET-06 reclass and reversal targets (S10-R-22)
    member_balances: tuple[Target, ...] = ()  # T-CON-09 per "<contract>@<entity>" (S10-R-23)
    # T-CON-09 member sums per "<contract>@<entity>" and period: refund_liability, return_asset,
    # deposit_liability, customer_incentive_asset, consideration_payable and (ENGINE mode)
    # accounts_receivable, each with its node (DG-KRN-EXP-01; D-97 (8); ``member_sums.py``).
    member_sums: tuple[Target, ...] = ()
    current_split: tuple[Target, ...] = ()  # current parts per "<group>@<entity>" (S10-R-24, 25)
    # agent_relief_cum max(G_t, R_t) and supplier_share_cum S_t per agent obligation and period end
    # (D-87 L4-3-Q-24 (c))
    agent_relief: tuple[Target, ...] = ()
    # EMOD-22 per <contract>@<entity> and period end: the stage 04 consideration_payable,
    # incentive_release_ordinary_cum and customer_incentive_asset rows plus the stage 10
    # share_based_reduction_element_cum, share_based_reduction_cum and incentive_release_cum rows
    # (§10.1; S10-R-26; D-91), read by stages 12, 13, 14 and the engine root.
    customer_consideration: tuple[Target, ...] = ()


def run(ctx: BookContext, st: RecognitionState, tb: TraceBuilder) -> BalanceState:
    """Billing, refund liabilities, receivables, positions and presentation of one book (§10.2)."""
    allocated = st.allocated
    classified = classification.classify(ctx, allocated)
    billed = billing.measure(ctx, allocated, classified, tb)
    refunds = refund_liability.measure(ctx, st, billed, tb)
    contra = reclass.receivable_contra(ctx, st, billed, tb)
    relief = agent.measure(ctx, st, billed, tb)
    positions = position.measure(
        ctx, st, billed, refunds, tb, receivable_contra=contra, supplier=relief.supplier
    )
    measures = position.obligation_positions(
        ctx,
        st,
        billed,
        tb,
        version_relief=lambda ob, as_of, revenue: agent.version_relief(
            ctx, billed, tb, relief, ob, as_of, revenue
        ),
    )
    presentation = reclass.present(ctx, st, billed, positions, tb)
    # S10-R-26 runs last: it reads the stage 09 revenue targets and the JET-05c concessions.
    listed = allocated.specialist_targets.customer_consideration
    consideration = customer_consideration.measure(
        ctx, st, refunds.components, refunds.concessions, listed, tb
    )
    members = (
        *presentation.members,
        *position.empty_member_balances(ctx, allocated, tb),  # D-88 L7-5-Q-10 (3)
    )
    receivables = reclass.accounts_receivable(ctx, st, billed, classified.receipts, tb)
    return BalanceState(
        allocated=allocated,
        recognition=st,
        billing=billed.targets,
        documents=billed.documents,
        receipts=classified.receipts,
        paid_cum=billed.paid_cum,
        obligation_measures=reclass.version_measures(measures, presentation),
        findings=tuple(
            sorted(
                (*classified.findings, *consideration.findings),
                key=lambda finding: finding.sort_key(),
            )
        ),
        accounts_receivable=receivables,
        receivable_contra=contra,
        positions=positions.targets,
        position_components=positions.components,
        refund_components=refunds.components,
        refund_liabilities=refunds.refund_liabilities,
        concessions=refunds.concessions,
        return_assets=refunds.return_assets,
        presentation=presentation.targets,
        accretion_attributed=presentation.accretion,
        right_classes=presentation.rights,
        netting_reclass=presentation.reclass,
        reclass_entries=presentation.entries,
        member_balances=members,
        member_sums=member_sums.measure(
            ctx,
            allocated,
            members,
            refund_liabilities=refunds.refund_liabilities,
            return_assets=refunds.return_assets,
            receivables=receivables,
            component_contracts={c.key: c.contract_key for c in refunds.components},
            tb=tb,
        ),
        current_split=current_split.measure(ctx, st, presentation, tb),
        agent_relief=relief.targets,
        customer_consideration=(*listed, *consideration.targets),
    )
