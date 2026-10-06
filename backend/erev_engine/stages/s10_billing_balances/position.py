"""Stage 10 net position and obligation positions (ENGINE_SPEC_B §10.2.3; ENC-12).

The unit is (combination group, contracting entity, book) (S10-R-11; POL-120): performing entities
hold no balances and groups never net. At each period end NP = B_u + DT + NC + IE − II − R_ctl − RC
− RL (S10-R-09; S10-INV-05), the balance of the ``CONTRACT_LIABILITY`` control role built from
targets: B_u is the unconditional billing of the member contracts (S10-R-08); DT, NC and the JET-11
accretion are the ``specialist_targets`` of stages 02 and 04 (S10-R-10); R_ctl is the stage 09
posted revenue target of every obligation of the entity plus the concessions created by JET-05c,
which reduce revenue without touching the control role; RC is the receivable contra (ENC-13); RL is
the JET-04b flow of the refund-liability components: the open balance of a component JET-04b
creates, and minus the consumed amount of a concession, which JET-05c created (L2-4-Q-13). Return
assets never enter NP (S10-R-17). ``position_obligation`` keeps its legacy definition ``billed_cum
− revenue_cum``, with the exact value for the parity runner, and ``position_contract_entity`` sums
it per contract and contracting entity at the version date (S10-R-12; REQ-ENT-002). Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.enums import PrincipalAgent
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    group_entity_subject_key,
)
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import billing, classification
from erev_engine.stages.s10_billing_balances.billing import BalanceMeasures, Billed
from erev_engine.stages.s10_billing_balances.refund_liability import CONCESSION, Refunds
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "DEPOSIT_MEASURE",
    "EXPENSE_CAUSE",
    "FINANCING_MEASURE",
    "INCOME_CAUSE",
    "NET_POSITION_FORMULA",
    "NONCASH_MEASURE",
    "OBLIGATION_FORMULA",
    "PositionComponents",
    "Positions",
    "latest_target",
    "measure",
    "obligation_positions",
    "series",
]

NET_POSITION_FORMULA: Final = "pos.net_position.v1"
OBLIGATION_FORMULA: Final = "pos.obligation.v1"
DEPOSIT_MEASURE: Final = "deposit_to_contract_liability_cum"  # EMOD-12 (ENGINE_SPEC S02-R-08)
NONCASH_MEASURE: Final = "noncash_asset_recognised_cum"  # EMOD-23 (S04-R-18; JET-17)
FINANCING_MEASURE: Final = "financing_interest_cum"  # EMOD-18 (S04-R-12, S04-R-13)
INCOME_CAUSE: Final = "JET-11a"  # deferred payment: Dr CONTRACT_LIABILITY / Cr INTEREST_INCOME
EXPENSE_CAUSE: Final = "JET-11b"  # advance payment: Dr INTEREST_EXPENSE / Cr CONTRACT_LIABILITY
_DEFERRED_KIND: Final = "DEFERRED"  # the stage 04 schedule kind of JET-11a (S04-R-12)
_ADVANCE_KIND: Final = "ADVANCE"  # the stage 04 schedule kind of JET-11b (S04-R-13)
_BILLED_UNCONDITIONAL: Final = "billed_unconditional_cum"


@dataclass(frozen=True, slots=True)
class PositionComponents:
    """NP and its components per (group, contracting entity) and period end (§10.2.3)."""

    subject_key: str  # "<group>@<entity>"
    entity: str
    period_key: str
    as_of: date
    net_position: int  # NP, minor units
    billed_unconditional: int  # B_u
    revenue_relief: int  # R_ctl
    deposit_transferred: int  # DT
    noncash_unconditional: int  # NC
    interest_expense: int  # IE
    interest_income: int  # II
    receivable_contra: int  # RC
    refund_liability: int  # RL: the JET-04b control-role flows (L2-4-Q-13)
    node_id: str


@dataclass(frozen=True, slots=True)
class Positions:
    """Net positions of one book (§10.1 ``positions``)."""

    targets: tuple[Target, ...]  # net_position per "<group>@<entity>" and period key
    components: Mapping[tuple[str, str], PositionComponents]  # (entity, period key)
    relief: Mapping[tuple[str, str], int]  # (obligation, period key) -> revenue_relief (S10-R-09)


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


class _Terms:
    """The signed inputs of one ``net_position`` node and the S10-INV-05 components they add to."""

    def __init__(self) -> None:
        self.items: list[tuple[str | SourceRef, int, int]] = []  # (input, sign, value)
        self.parts = dict.fromkeys(("b_u", "dt", "nc", "ie", "ii", "r_ctl", "rc", "rl"), 0)

    def add(self, ref: str | SourceRef, sign: int, value: int, part: str, signed: int) -> None:
        """Cite ``ref`` with ``sign``; ``signed`` is its contribution to component ``part``."""
        self.items.append((ref, sign, value))
        self.parts[part] += signed

    @property
    def value(self) -> int:
        return sum(sign * amount for _, sign, amount in self.items)

    @property
    def identity(self) -> int:
        """B_u + DT + NC + IE − II − R_ctl − RC − RL (S10-INV-05)."""
        p = self.parts
        positive = p["b_u"] + p["dt"] + p["nc"] + p["ie"]
        return positive - p["ii"] - p["r_ctl"] - p["rc"] - p["rl"]


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def series(
    ctx: BookContext, targets: Iterable[Target]
) -> dict[tuple[str, str], tuple[tuple[date, Target], ...]]:
    """Targets by (measure, subject key), ascending by the end date of their owner's period."""
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    grouped: dict[tuple[str, str], list[tuple[date, Target]]] = {}
    for target in targets:
        end = ends.get((target.entity, target.period_key))
        if end is None:
            raise _invariant(
                "a target names a period absent from its entity's calendar",
                target.subject_key,
                rule="CV-12",
                period_key=target.period_key,
            )
        grouped.setdefault((target.measure, target.subject_key), []).append((end, target))
    return {key: tuple(sorted(items, key=lambda item: item[0])) for key, items in grouped.items()}


def latest_target(items: Sequence[tuple[date, Target]], t: date) -> Target | None:
    """The cumulative target of the latest period ending on or before ``t``."""
    found: Target | None = None
    for end, target in items:
        if end > t:
            break
        found = target
    return found


def measure(
    ctx: BookContext,
    recognition: RecognitionState,
    billed: Billed,
    refunds: Refunds,
    tb: TraceBuilder,
    *,
    receivable_contra: Sequence[Target] = (),
    supplier: Mapping[str, Sequence[tuple[date, int, str | None]]] | None = None,
) -> Positions:
    """``net_position`` of §10.2.3 per (group, contracting entity) and period end (S10-R-09).

    ``supplier``: the S_t rows of the agent obligations, which the control role relieves beside R_t
    (D-87 L4-3-Q-24 (d)).
    """
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    revenue = series(ctx, recognition.revenue_targets)
    specialist = st.specialist_targets
    flows = series(ctx, (*specialist.deposit, *specialist.financing, *specialist.noncash))
    unconditional = {
        (target.subject_key, target.period_key): target
        for target in billed.targets
        if target.measure == _BILLED_UNCONDITIONAL
    }
    contra = series(ctx, receivable_contra)
    targets: list[Target] = []
    components: dict[tuple[str, str], PositionComponents] = {}
    relief: dict[tuple[str, str], int] = {}
    obligations = sorted(st.obligations, key=lambda ob: ob.subject_key)
    for entity in sorted({ob.contracting_entity for ob in obligations}):
        members = sorted({ob.contract_key for ob in obligations if ob.contracting_entity == entity})
        own = [ob for ob in obligations if ob.contracting_entity == entity]
        subject_key = group_entity_subject_key(st.group_code, entity)
        for period in billing.periods(ctx, st, entity):
            t = period.end_date
            terms = _Terms()
            for contract_key in members:
                at_entity = contract_entity_subject_key(contract_key, entity)
                billed_target = unconditional.get((at_entity, period.period_key))
                if billed_target is not None:
                    terms.add(
                        billed_target.node_id, 1, billed_target.value, "b_u", billed_target.value
                    )
                for name, part in ((DEPOSIT_MEASURE, "dt"), (NONCASH_MEASURE, "nc")):
                    found = latest_target(flows.get((name, at_entity), ()), t)
                    if found is not None:
                        terms.add(found.node_id, 1, found.value, part, found.value)
                interest = latest_target(flows.get((FINANCING_MEASURE, at_entity), ()), t)
                if interest is not None:
                    # Stage 04 names the schedule kind (S04-R-12, S04-R-13): ADVANCE is JET-11b
                    # and DEFERRED is JET-11a (L4-3-Q-18).
                    if interest.cause in (EXPENSE_CAUSE, _ADVANCE_KIND):
                        terms.add(interest.node_id, 1, interest.value, "ie", interest.value)
                    elif interest.cause in (INCOME_CAUSE, _DEFERRED_KIND):
                        terms.add(interest.node_id, -1, interest.value, "ii", interest.value)
                    else:
                        raise _invariant(
                            "a financing target names no JET-11 part",
                            at_entity,
                            rule="S10-R-10",
                            cause=str(interest.cause),
                        )
                rc_target = latest_target(contra.get(("receivable_contra", at_entity), ()), t)
                if rc_target is not None:
                    terms.add(rc_target.node_id, -1, rc_target.value, "rc", rc_target.value)
            for ob in own:
                found = latest_target(revenue.get(("revenue_cum", ob.subject_key), ()), t)
                value = 0 if found is None else found.value
                if found is not None:
                    terms.add(found.node_id, -1, value, "r_ctl", value)
                shared, shared_node = _supplier_at(supplier, ob.subject_key, t)
                if shared_node is not None:
                    terms.add(shared_node, -1, shared, "r_ctl", shared)
                relief[(ob.subject_key, period.period_key)] = (
                    value + shared + refunds.concession_total(ob.subject_key, t)
                )
            for component in refunds.components:
                if component.entity != entity:
                    continue
                if component.kind == CONCESSION:
                    ref = component.created_ref
                    if component.created_on is None or component.created_on > t or ref is None:
                        continue
                    amount = component.created_amount
                    terms.add(ref, -1, amount, "r_ctl", amount)
                    for item in component.consumed_by(t):
                        terms.add(item.node_id, 1, item.amount, "rl", -item.amount)
                    continue
                balance = refunds.balances.get((component.key, period.period_key))
                if balance is not None:
                    terms.add(balance.node_id, -1, balance.value, "rl", balance.value)
            value = terms.value
            if value != terms.identity:
                raise _invariant(
                    "NP = B_u + DT + NC + IE − II − R_ctl − RC − RL does not hold",
                    subject_key,
                    rule="S10-INV-05",
                    period_key=period.period_key,
                )
            node_id = tb.node(
                measure="net_position",
                subject_key=subject_key,
                period_key=period.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=NET_POSITION_FORMULA,
                inputs=[ref for ref, _, _ in terms.items],
                params={
                    "as_of": t.isoformat(),
                    "signs": "|".join("+" if sign > 0 else "-" for _, sign, _ in terms.items),
                },
                narrative_key=_narrative(NET_POSITION_FORMULA),
            )
            targets.append(
                Target(
                    ctx.book_code,
                    entity,
                    subject_key,
                    "net_position",
                    period.period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
            components[(entity, period.period_key)] = PositionComponents(
                subject_key=subject_key,
                entity=entity,
                period_key=period.period_key,
                as_of=t,
                net_position=value,
                billed_unconditional=terms.parts["b_u"],
                revenue_relief=terms.parts["r_ctl"],
                deposit_transferred=terms.parts["dt"],
                noncash_unconditional=terms.parts["nc"],
                interest_expense=terms.parts["ie"],
                interest_income=terms.parts["ii"],
                receivable_contra=terms.parts["rc"],
                refund_liability=terms.parts["rl"],
                node_id=node_id,
            )
    return Positions(
        targets=tuple(targets),
        components=MappingProxyType(components),
        relief=MappingProxyType(relief),
    )


def _supplier_at(
    supplier: Mapping[str, Sequence[tuple[date, int, str | None]]] | None,
    subject_key: str,
    t: date,
) -> tuple[int, str | None]:
    """S_t of the latest agent row ending on or before ``t``; (0, None) otherwise."""
    found: tuple[int, str | None] = (0, None)
    for end, value, node_id in (supplier or {}).get(subject_key, ()):
        if end > t:
            break
        found = (value, node_id)
    return found


def obligation_positions(
    ctx: BookContext,
    recognition: RecognitionState,
    billed: Billed,
    tb: TraceBuilder,
    version_relief: Callable[
        [ObligationState, date, tuple[int, Fraction, str | None]],
        tuple[int, Fraction, str | None] | None,
    ]
    | None = None,
) -> Mapping[str, BalanceMeasures]:
    """``position_obligation`` and ``position_contract_entity`` at the version date (S10-R-12).

    ``version_relief`` gives an agent obligation's relief max(G, R) at d_v, so its position is
    billed − (R + S); an agent obligation also publishes ``gross_amount_memo`` = its billing net of
    credit memos (D-87 L4-3-Q-24 (b), (d)).
    """
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    scale: int = 10**mu
    obligations = {ob.subject_key: ob for ob in st.obligations}
    out: dict[str, BalanceMeasures] = {}
    pairs: dict[tuple[str, str], list[str]] = {}
    for subject_key, measures in sorted(billed.measures.items()):
        ob = obligations[subject_key]
        inputs = [measures.trace_nodes["billed_cum"]]
        revenue = 0
        revenue_exact = Fraction(0)
        found = recognition.obligation_measures.get(subject_key)
        if found is not None:
            inputs.append(found.trace_nodes["revenue_cum"])
            revenue = found.revenue_cum
            revenue_exact = (
                Fraction(revenue, scale)
                if found.revenue_cum_exact is None
                else found.revenue_cum_exact
            )
        agent = (
            None
            if version_relief is None
            else version_relief(
                ob,
                measures.as_of,
                (revenue, revenue_exact, None if found is None else inputs[1]),
            )
        )
        if agent is not None:
            revenue, revenue_exact, relief_node = agent
            inputs = [measures.trace_nodes["billed_cum"], *([relief_node] if relief_node else [])]
        value = measures.billed_cum - revenue
        exact = Fraction(measures.billed_cum, scale) - revenue_exact
        node_id = tb.node(
            measure="position_obligation",
            subject_key=subject_key,
            period_key=None,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=OBLIGATION_FORMULA,
            inputs=inputs,
            params={"as_of": measures.as_of.isoformat(), "mode": "difference"},
            exact=exact,
            narrative_key=_narrative(OBLIGATION_FORMULA),
        )
        memo = ob.principal_agent == PrincipalAgent.AGENT and ob.gross_to_net is not None
        memo_node = {"gross_amount_memo": measures.trace_nodes["billed_cum"]} if memo else {}
        out[subject_key] = dataclasses.replace(
            measures,
            position_obligation=value,
            position_obligation_exact=exact,
            gross_amount_memo=measures.billed_cum if memo else measures.gross_amount_memo,
            trace_nodes=MappingProxyType(
                {**measures.trace_nodes, "position_obligation": node_id, **memo_node}
            ),
        )
        pairs.setdefault((ob.contract_key, ob.contracting_entity), []).append(subject_key)
    for (contract_key, entity), keys in sorted(pairs.items()):
        total = sum(out[key].position_obligation for key in keys)
        exact_total = sum((out[key].position_obligation_exact for key in keys), Fraction(0))
        node_id = tb.node(
            measure="position_contract_entity",
            subject_key=contract_entity_subject_key(contract_key, entity),
            period_key=None,
            value=total,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=OBLIGATION_FORMULA,
            inputs=[out[key].trace_nodes["position_obligation"] for key in keys],
            params={"as_of": out[keys[0]].as_of.isoformat(), "mode": "sum"},
            exact=exact_total,
            narrative_key=_narrative(OBLIGATION_FORMULA),
        )
        for key in keys:
            out[key] = dataclasses.replace(
                out[key],
                position_contract_entity=total,
                position_contract_entity_exact=exact_total,
                trace_nodes=MappingProxyType(
                    {**out[key].trace_nodes, "position_contract_entity": node_id}
                ),
            )
    return MappingProxyType(out)


_EMPTY_MEMBER_FORMULA: Final = "pos.split_ca_ur.v1"  # mode parts over no attribution: 0
_EMPTY_MEMBER_MEASURES: Final = ("contract_liability", "contract_asset", "unbilled_receivable")


def empty_member_balances(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder
) -> tuple[Target, ...]:
    """D-88 L7-5-Q-10 (3): the T-CON-09 member balance targets of a member contract with no
    obligation (every line excluded by S03-R-11), all zero, for each period end of its contracting
    entity (S10-R-23). ``accounts_receivable`` is added outside ``ENGINE`` mode, where S10-R-19
    publishes no receivable of its own. Contracts with obligations are unchanged."""
    mu = classification.minor_unit(ctx)
    with_obligations = {ob.contract_key for ob in st.obligations}
    out: list[Target] = []
    for contract in sorted(st.contracts, key=lambda view: view.header.external_id):
        contract_key = contract.header.external_id
        if contract_key in with_obligations:
            continue
        entity = contract.header.contracting_entity_code
        subject_key = contract_entity_subject_key(contract_key, entity)
        for period in billing.periods(ctx, st, entity):
            t = period.end_date
            measures = list(_EMPTY_MEMBER_MEASURES)
            if classification.mode_at(ctx, contract, t) != classification.ENGINE:
                measures.append("accounts_receivable")
            for measure_name in measures:
                node_id = tb.node(
                    measure=measure_name,
                    subject_key=subject_key,
                    period_key=period.period_key,
                    value=0,
                    currency=ctx.txn_currency,
                    minor_unit=mu,
                    formula_id=_EMPTY_MEMBER_FORMULA,
                    inputs=[],
                    params={"as_of": t.isoformat(), "keys": "", "mode": "parts", "parts": ""},
                    narrative_key=_narrative(_EMPTY_MEMBER_FORMULA),
                )
                out.append(
                    Target(
                        ctx.book_code,
                        entity,
                        subject_key,
                        measure_name,
                        period.period_key,
                        None,
                        0,
                        None,
                        node_id,
                    )
                )
    return tuple(out)
