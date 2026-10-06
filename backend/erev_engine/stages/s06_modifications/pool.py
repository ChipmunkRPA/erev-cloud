"""Stage 06 pool and apportionment (ENGINE_SPEC S06-R-12, S06-R-13; ALG-04 §2.5.5).

POL-103 ``REMAINING_TP``: Pool = Σ over the existing D and N obligations of (A_p − R_p) + Σ ΔC_m −
ΔC_sat + ΔVC, in minor units. s_p = ``largest_remainder(Pool, w, keys)[p]``; an existing obligation
takes A′_p = R_p + s_p and X′_p = R_p + (Pool ÷ 10^μ) × w_p ÷ Σw, an added one A′_p = s_p and
X′_p = (Pool ÷ 10^μ) × w_p ÷ Σw (D-76 decision 10: the exact segment share). Nodes
``mod_pool@<event key>:<contract>:-`` and ``mod_share@<event key>:<ob>:-`` (formula
``mod.pool.remaining_tp.v1``). Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine import money
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import contract_subject_key
from erev_engine.stages.state import BookContext, EventView
from erev_engine.trace import TraceBuilder

__all__ = [
    "BY_LINE_FORMULA",
    "REMAINING_TP_FORMULA",
    "LineMember",
    "Member",
    "Pool",
    "Share",
    "apportion",
    "attribute",
    "emit",
    "preview",
]

REMAINING_TP_FORMULA: Final = "mod.pool.remaining_tp.v1"
BY_LINE_FORMULA: Final = "mod.pool.by_line.v1"
SEPARATOR: Final = "|"


@dataclass(frozen=True, slots=True)
class Member:
    """An existing D or N obligation in the pool: A_p and R_p, minor units."""

    subject_key: str
    allocation: int
    revenue: int


@dataclass(frozen=True, slots=True)
class Pool:
    """The S06-R-12 pool of one modification, minor units."""

    contract_key: str
    members: tuple[Member, ...]  # subject-key order
    consideration: int  # Σ ΔC_m
    satisfied: int  # ΔC_sat (S06-R-09)
    vc_delta: int  # ΔVC

    @property
    def posted(self) -> int:
        remaining = sum(member.allocation - member.revenue for member in self.members)
        return remaining + self.consideration - self.satisfied + self.vc_delta


@dataclass(frozen=True, slots=True)
class Share:
    """s_p with its exact counterpart and node (S06-R-13)."""

    subject_key: str
    posted: int  # minor units
    exact: Fraction  # (Pool ÷ 10^μ) × w_p ÷ Σw
    node_id: str


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    pool: Pool,
    minor_unit: int,
    extra: Mapping[str, str] | None = None,
) -> str:
    """``mod_pool@<event key>:<contract>:-``; ``extra`` params record evidence the formula does
    not read, for example the unpriced change orders behind ΔVC (S06-R-20)."""
    params = {
        **(extra or {}),
        "allocations": SEPARATOR.join(str(member.allocation) for member in pool.members),
        "as_of": ev.effective_date.isoformat(),
        "consideration": str(pool.consideration),
        "keys": SEPARATOR.join(member.subject_key for member in pool.members),
        "revenue": SEPARATOR.join(str(member.revenue) for member in pool.members),
        "role": "pool",
        "satisfied": str(pool.satisfied),
        "vc_delta": str(pool.vc_delta),
    }
    return tb.node(
        measure=f"mod_pool@{ev.event_key}",
        subject_key=contract_subject_key(pool.contract_key),
        period_key=None,
        value=pool.posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=REMAINING_TP_FORMULA,
        inputs=[],
        params=params,
        narrative_key=REMAINING_TP_FORMULA.rsplit(".v", 1)[0],
    )


def preview(
    pool: Pool, weights: Sequence[tuple[str, Fraction]], minor_unit: int
) -> Mapping[str, tuple[int, Fraction]]:
    """(s_p, exact share) per key without emitting nodes, for the S06-R-22 check before emission."""
    keys = [key for key, _ in weights]
    values = [value for _, value in weights]
    total_weight = sum(values, Fraction(0))
    if total_weight == 0:
        return {key: (0, Fraction(0)) for key in keys}
    posted = money.largest_remainder(pool.posted, values, keys)
    scale = Fraction(pool.posted, 10**minor_unit)
    return {
        key: (amount, scale * value / total_weight)
        for key, value, amount in zip(keys, values, posted, strict=True)
    }


def apportion(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    pool: Pool,
    pool_node: str,
    weights: Sequence[tuple[str, Fraction]],
    minor_unit: int,
) -> Mapping[str, Share]:
    """s_p and the exact share of every weighted obligation, with ``mod_share`` nodes.

    Σw = 0 with a zero pool gives zero shares; a non-zero pool over zero weights is satisfied
    performance (S06-R-12), which the caller settles before apportioning.
    """
    keys = [key for key, _ in weights]
    values = [value for _, value in weights]
    total_weight = sum(values, Fraction(0))
    if total_weight == 0:
        posted = [0] * len(keys)
    else:
        posted = money.largest_remainder(pool.posted, values, keys)
    params = {
        "as_of": ev.effective_date.isoformat(),
        "keys": SEPARATOR.join(keys),
        "role": "share",
        "weights": SEPARATOR.join(rational_param(value) for value in values),
    }
    shares: dict[str, Share] = {}
    scale = 10**minor_unit
    for key, value, amount in zip(keys, values, posted, strict=True):
        exact = (
            Fraction(0)
            if total_weight == 0
            else Fraction(pool.posted, scale) * value / total_weight
        )
        node_id = tb.node(
            measure=f"mod_share@{ev.event_key}",
            subject_key=key,
            period_key=None,
            value=amount,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=REMAINING_TP_FORMULA,
            inputs=[pool_node],
            params={**params, "key": key},
            exact=exact,
            narrative_key=REMAINING_TP_FORMULA.rsplit(".v", 1)[0],
        )
        shares[key] = Share(key, amount, exact, node_id)
    return shares


@dataclass(frozen=True, slots=True)
class LineMember:
    """An obligation under POL-103 ``ATTRIBUTE_BY_LINE``: A_p, R_p and Σ ΔC_m of its lines."""

    subject_key: str
    allocation: int
    revenue: int
    consideration: int

    @property
    def posted(self) -> int:
        return self.allocation - self.revenue + self.consideration


def attribute(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    contract_key: str,
    members: Sequence[LineMember],
    minor_unit: int,
) -> Mapping[str, Share]:
    """POL-103 ``ATTRIBUTE_BY_LINE``: Pool_p = (A_p − R_p) + Σ ΔC_m of its lines, no apportionment.

    Nodes ``mod_pool@<event key>:<contract>:-`` and ``mod_share@<event key>:<ob>:-`` (formula
    ``mod.pool.by_line.v1``); the share of an obligation is its own pool.
    """

    def params(items: Sequence[LineMember]) -> dict[str, str]:
        return {
            "allocations": SEPARATOR.join(str(item.allocation) for item in items),
            "as_of": ev.effective_date.isoformat(),
            "consideration": SEPARATOR.join(str(item.consideration) for item in items),
            "keys": SEPARATOR.join(item.subject_key for item in items),
            "revenue": SEPARATOR.join(str(item.revenue) for item in items),
        }

    tb.node(
        measure=f"mod_pool@{ev.event_key}",
        subject_key=contract_subject_key(contract_key),
        period_key=None,
        value=sum(item.posted for item in members),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=BY_LINE_FORMULA,
        inputs=[],
        params=params(members),
        narrative_key=BY_LINE_FORMULA.rsplit(".v", 1)[0],
    )
    shares: dict[str, Share] = {}
    for item in members:
        node_id = tb.node(
            measure=f"mod_share@{ev.event_key}",
            subject_key=item.subject_key,
            period_key=None,
            value=item.posted,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=BY_LINE_FORMULA,
            inputs=[],
            params=params([item]),
            narrative_key=BY_LINE_FORMULA.rsplit(".v", 1)[0],
        )
        shares[item.subject_key] = Share(
            item.subject_key, item.posted, Fraction(item.posted, 10**minor_unit), node_id
        )
    return shares
