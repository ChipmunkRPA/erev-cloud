"""Stage 06 satisfied performance and targeted concessions (ENGINE_SPEC S06-R-09, S06-R-10).

POL-104 ``RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS`` (606-10-32-42 to 32-44): ΔC_sat is the tagged
``price_change_amount``, else the consideration of price-only lines on class S obligations (ALG-04
§2.5.2). A pool over zero weights, for example when no obligation remains unsatisfied, is satisfied
performance as well (S06-R-12; DEV-054). ΔC_sat is apportioned over the class S obligations of the
contract by ``largest_remainder(ΔC_sat, original posted allocations, keys)``, or goes wholly to the
named obligation under POL-243 ``TARGETED_WHEN_32_40_ATTESTED`` with questionnaire
``pol_243_attested = true`` (S06-R-10). ``POOL_WITH_REMAINING`` (parity) leaves it in the pool.
Each receiver takes an ``INCEPTION`` segment with x′ = X_p + share exact and a′ = A_p + share, so
its catch-up equals the share. Node ``satisfied_share@<event key>:<ob>:-`` (formula
``mod.satisfied_performance.v1``). Under ``CREDIT_OR_REFUND`` stage 06 adds each receiver's negative
share to ``refund_components`` as the ``CONCESSION`` refund quota (D-87 L6-5-Q-10). Private to stage
06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine import money
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import payload_text
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import BookContext, EventView, ObligationState
from erev_engine.trace import TraceBuilder

__all__ = [
    "CONCESSION_POLICY",
    "FORMULA_ID",
    "POLICY_CODE",
    "POOL_WITH_REMAINING",
    "RECOGNISE",
    "Receiver",
    "apportion",
    "preview",
    "settlement",
    "target",
]

FORMULA_ID: Final = "mod.satisfied_performance.v1"
POLICY_CODE: Final = "mod.price_change_on_satisfied_performance"
CONCESSION_POLICY: Final = "concession.allocation_basis"
RECOGNISE: Final = "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS"
POOL_WITH_REMAINING: Final = "POOL_WITH_REMAINING"
TARGETED: Final = "TARGETED_WHEN_32_40_ATTESTED"
INCEPTION_BASIS: Final = "INCEPTION_BASIS"
CREDIT_OR_REFUND: Final = "CREDIT_OR_REFUND"
SETTLEMENTS: Final = frozenset({"FUTURE_PRICING", CREDIT_OR_REFUND})
SEPARATOR: Final = "|"


@dataclass(frozen=True, slots=True)
class Receiver:
    """The share of ΔC_sat one class S obligation receives (S06-R-09)."""

    subject_key: str
    posted: int  # minor units
    exact: Fraction  # ΔC_sat × w_p ÷ Σw, currency units
    node_id: str


def settlement(mod: ModificationView) -> str:
    """Questionnaire ``price_change_settlement`` (T-CON-06; D-76): ``FUTURE_PRICING`` by default."""
    value = payload_text(mod.questionnaire, "price_change_settlement")
    if value is None:
        return "FUTURE_PRICING"
    if value not in SETTLEMENTS:
        raise ValueError(f"{mod.modification_key}: unknown price_change_settlement {value!r}")
    return value


def target(ctx: BookContext, mod: ModificationView, named: Sequence[str]) -> str | None:
    """The obligation that receives the whole concession under POL-243, if any (S06-R-10)."""
    option = ctx.policies.value(CONCESSION_POLICY, contract=mod.contract_key)
    if option == INCEPTION_BASIS:
        return None
    if option != TARGETED:
        raise ValueError(f"{CONCESSION_POLICY} holds an unknown option {option!r} (CV-17)")
    attested = sorted({key for key in named if mod.answer(key, "pol_243_attested")})
    return attested[0] if len(attested) == 1 else None


def _members(
    receivers: Sequence[ObligationState], targeted: str | None
) -> tuple[list[str], list[Fraction]]:
    members = (
        list(receivers)
        if targeted is None
        else [ob for ob in receivers if ob.obligation_key == targeted]
    )
    keys = [ob.subject_key for ob in members]
    values = [Fraction(ob.original_allocation.a_posted) for ob in members]
    return keys, values


def preview(
    total: int, receivers: Sequence[ObligationState], targeted: str | None, minor_unit: int
) -> Mapping[str, tuple[int, Fraction]]:
    """(share, exact share) per receiver without emitting nodes (the S06-R-22 check)."""
    keys, values = _members(receivers, targeted)
    posted = money.largest_remainder(total, values, keys)
    weight_sum = sum(values, Fraction(0))
    scale = Fraction(total, 10**minor_unit)
    return {
        key: (amount, scale * value / weight_sum)
        for key, value, amount in zip(keys, values, posted, strict=True)
    }


def apportion(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    mod: ModificationView,
    total: int,
    receivers: Sequence[ObligationState],
    targeted: str | None,
    minor_unit: int,
) -> Mapping[str, Receiver]:
    """ΔC_sat over the receivers by original posted allocations, with ``satisfied_share`` nodes."""
    keys, values = _members(receivers, targeted)
    posted = money.largest_remainder(total, values, keys)
    weight_sum = sum(values, Fraction(0))
    params = {
        "as_of": ev.effective_date.isoformat(),
        "keys": SEPARATOR.join(keys),
        "mode": INCEPTION_BASIS if targeted is None else TARGETED,
        "settlement": settlement(mod),
        "total": str(total),
        "weights": SEPARATOR.join(rational_param(value) for value in values),
    }
    found: dict[str, Receiver] = {}
    for key, value, amount in zip(keys, values, posted, strict=True):
        exact = Fraction(total, 10**minor_unit) * value / weight_sum
        node_id = tb.node(
            measure=f"satisfied_share@{ev.event_key}",
            subject_key=key,
            period_key=None,
            value=amount,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=FORMULA_ID,
            inputs=[],
            params={**params, "key": key},
            exact=exact,
            narrative_key=FORMULA_ID.rsplit(".v", 1)[0],
        )
        found[key] = Receiver(key, amount, exact, node_id)
    return found
