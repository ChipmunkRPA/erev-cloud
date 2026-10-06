"""Stage 09 attribution of the 606-10-25-7 deposit revenue and the STEP1_MET netting.

ENGINE_SPEC S02-R-04 and §2.5 (rev 1.6), ENGINE_SPEC_B S14-R-25 (rev 1.7); D-91 gaps (iv), (v).
Stage 02 recognises a nonrefundable deposit as revenue per contract (``deposit_to_revenue_cum``,
``DepositRelease`` records on ``SpecialistTargets``); stage 09 holds the allocated state, so it
attributes each contract's recognitions to the contract's ``IN_SCOPE_606`` obligations with
``largest_remainder`` over the posted inception allocation A_p, else the resolved SSP, else the
stated prices, else ``TOTAL_WEIGHT_ZERO`` (fail closed). Each share is node
``deposit_revenue_share:<obligation>:<period>`` (formula ``step1.deposit_revenue_share.v1``; inputs
the stage 02 recognition nodes dated on or before the period end; params ``keys``, ``weights``,
``key``, ``basis``, ``index``); the recognitions at dated points give the sibling
``deposit_revenue_time_share`` node, the ``CLOSE_RELEASE`` share stage 14 posts as ``TIME``. Stage
14 cites the share nodes for the JET-01b 25-7 revenue part and the STEP1_MET netting of S02-R-04
cites them for max(C_p(d) − R25_p, 0), so no forward reference from stage 09 to a stage 14 node
exists (DG-ENG-07). Private to stage 09; the package exports ``deposit_attributions`` and
``deposit_share``. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import largest_remainder, round_half_up
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    DepositRelease,
    ObligationState,
    Target,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "BASES",
    "NET_FORMULA",
    "NETTED_MEASURE",
    "SHARE_FORMULA",
    "SHARE_MEASURE",
    "TIME_SHARE_MEASURE",
    "Attribution",
    "attributions",
    "emit",
    "share",
    "share_node_id",
    "weights",
]

SHARE_FORMULA: Final = "step1.deposit_revenue_share.v1"
NET_FORMULA: Final = "rec.step1_net.v1"
SHARE_MEASURE: Final = "deposit_revenue_share"
TIME_SHARE_MEASURE: Final = "deposit_revenue_time_share"
NETTED_MEASURE: Final = "step1_netted_target"
BASES: Final = ("ALLOCATION", "SSP", "STATED_PRICE")
_IN_SCOPE: Final = "IN_SCOPE_606"


@dataclass(frozen=True, slots=True)
class Attribution:
    """The S14-R-25 attribution of one contract's 25-7 revenue over its in-scope obligations."""

    contract_key: str
    entity: str  # contracting entity (C-04)
    keys: tuple[str, ...]  # obligation subject keys, sorted
    weights: tuple[Fraction, ...]  # one per key, Σ > 0
    basis: str  # BASES literal
    releases: tuple[DepositRelease, ...]  # ascending ENG-06 order

    def index(self, subject_key: str) -> int:
        return self.keys.index(subject_key)


def weights(
    contract_key: str, members: Sequence[ObligationState]
) -> tuple[tuple[Fraction, ...], str]:
    """The attribution weights of ``members`` and their basis (S14-R-25): the posted inception
    allocation A_p; when Σ A_p = 0 the resolved SSP; when that sums to 0 the stated prices;
    otherwise ``TOTAL_WEIGHT_ZERO`` (fail closed). A basis with a negative weight is skipped."""
    candidates = (
        ("ALLOCATION", [Fraction(ob.original_allocation.a_posted) for ob in members]),
        ("SSP", [Fraction(ob.resolved_ssp) for ob in members]),
        ("STATED_PRICE", [Fraction(ob.stated_price) for ob in members]),
    )
    for basis, found in candidates:
        if not found or any(weight < 0 for weight in found):
            continue
        if sum(found, Fraction(0)) > 0:
            return tuple(found), basis
    raise EngineError(
        "TOTAL_WEIGHT_ZERO",
        "no attribution basis for the 606-10-25-7 revenue of the contract (S14-R-25)",
        subject_key=contract_key,
        detail={"rule": "S14-R-25", "stage": "09", "bases": "|".join(BASES)},
    )


def attributions(st: AllocatedState) -> Mapping[str, Attribution]:
    """Per contract with at least one 25-7 recognition: its attribution (S14-R-25; D-91 (iv))."""
    releases: dict[str, list[DepositRelease]] = {}
    for release in st.specialist_targets.deposit_releases:
        releases.setdefault(release.contract_key, []).append(release)
    found: dict[str, Attribution] = {}
    for contract_key in sorted(releases):
        ordered = tuple(sorted(releases[contract_key], key=lambda item: item.order_key))
        members = sorted(
            (
                ob
                for ob in st.obligations
                if ob.contract_key == contract_key and str(ob.scope_flag) == _IN_SCOPE
            ),
            key=lambda ob: ob.subject_key,
        )
        weighted, basis = weights(contract_key, members)
        entity = ordered[0].entity
        if any(ob.contracting_entity != entity for ob in members):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the 25-7 revenue and its obligations belong to one contracting entity",
                subject_key=f"{contract_key}@{entity}",
                detail={"rule": "S14-R-25", "stage": "09"},
            )
        found[contract_key] = Attribution(
            contract_key=contract_key,
            entity=entity,
            keys=tuple(ob.subject_key for ob in members),
            weights=weighted,
            basis=basis,
            releases=ordered,
        )
    return MappingProxyType(found)


def share(
    attribution: Attribution,
    subject_key: str,
    d: date,
    minor_unit: int,
    *,
    timed: bool | None = None,
    position: Position | None = None,
) -> tuple[int, tuple[str, ...]]:
    """(share in minor units, the recognition nodes it sums) of ``subject_key`` at the end of ``d``,
    or at ``position`` within ``d``: the recognitions dated on or before ``d`` (all, or the dated
    points when ``timed``), summed, rounded (CV-35) and apportioned by ``largest_remainder``."""
    selected = [
        item
        for item in attribution.releases
        if item.effective_date <= d
        and (timed is None or item.timed == timed)
        and (position is None or item.effective_date < d or position.admits(item.order_key))
    ]
    total = round_half_up(sum((item.amount for item in selected), Fraction(0)), minor_unit)
    nodes = tuple(item.node_id for item in selected)
    if total == 0:
        return 0, nodes
    index = attribution.index(subject_key)
    return (
        largest_remainder(total, list(attribution.weights), list(attribution.keys))[index],
        nodes,
    )


def share_node_id(subject_key: str, period_key: str | None, *, timed: bool = False) -> str:
    """The id of the share node stage 14 and the S02-R-04 netting cite (CV-50)."""
    measure = TIME_SHARE_MEASURE if timed else SHARE_MEASURE
    return f"{measure}:{subject_key}:{'-' if period_key is None else period_key}"


def emit(
    tb: TraceBuilder,
    ctx: BookContext,
    attribution: Attribution,
    ob: ObligationState,
    period_key: str | None,
    d: date,
) -> tuple[Target, ...]:
    """The share and time-share nodes of ``ob`` at ``d`` (a period end, or the version date with
    ``period_key`` None), as targets of the contracting entity (§2.5 rev 1.6)."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    index = attribution.index(ob.subject_key)
    out: list[Target] = []
    for measure, timed in ((SHARE_MEASURE, None), (TIME_SHARE_MEASURE, True)):
        value, inputs = share(attribution, ob.subject_key, d, minor_unit, timed=timed)
        node_id = tb.node(
            measure=measure,
            subject_key=ob.subject_key,
            period_key=period_key,
            value=value,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=SHARE_FORMULA,
            inputs=list(inputs),
            params={
                "as_of": d.isoformat(),
                "basis": attribution.basis,
                "index": str(index),
                "key": ob.subject_key,
                "keys": "|".join(attribution.keys),
                "minor_unit": str(minor_unit),
                "weights": "|".join(rational_param(weight) for weight in attribution.weights),
            },
            narrative_key=SHARE_FORMULA.rsplit(".v", 1)[0],
        )
        if period_key is not None:
            out.append(
                Target(
                    book_code=ctx.book_code,
                    entity=attribution.entity,
                    subject_key=ob.subject_key,
                    measure=measure,
                    period_key=period_key,
                    cause=None,
                    value=value,
                    exact=None,
                    node_id=node_id,
                )
            )
    return tuple(out)
