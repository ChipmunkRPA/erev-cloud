"""Stage 05 relative-SSP allocation and the immaterial-promise merge.

ENGINE_SPEC S05-R-10 (relative SSP and largest remainder, CV-34), S05-R-13 (posting on every path),
§5.5 S05-INV-01 to S05-INV-03, finding ``TOTAL_SSP_ZERO`` (POL-077), formulas
``alloc.relative_ssp.v1`` and ``alloc.largest_remainder.v1``, trace nodes ``total_ssp:<group>:-``,
``allocation_weight:<ob>:-``, ``original_allocated_exact:<ob>:-`` and
``original_allocated_amount:<ob>:-``; S03-R-13 merge step (POL-020). Private to stage 05. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine import money
from erev_engine.bundle import SspEntryInput, SspRangeInput
from erev_engine.enums import ObligationKind
from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages.s03_pob_builder import PobDraft
from erev_engine.stages.s05_allocation import points
from erev_engine.stages.state import BookContext, Quota, SspResolution
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["RELATIVE", "REMAINDER", "Resolved", "apportion", "emit", "merge_immaterial"]

RELATIVE: Final = "alloc.relative_ssp.v1"
REMAINDER: Final = "alloc.largest_remainder.v1"
MERGE_RULE: Final = "S03-R-13"
# 606-10-25-16B: the relief never applies to options, and a VC line or a routed-out lease component
# is no host of an immaterial promise.
_NOT_HOSTS: Final = frozenset({ObligationKind.MATERIAL_RIGHT, ObligationKind.VC_LINE})


@dataclass(frozen=True, slots=True)
class SnapshotSource:
    """The resolved SSP entry, its POL-079 conversion and the band row a line's snapshot values
    derive from (S05-R-05, S05-R-06): the canonical sources of the snapshot nodes."""

    entry: SspEntryInput
    factor: Fraction  # 1 without a conversion
    rate_source: SourceRef | None  # the ``fx_rate`` source of the conversion
    row: SspRangeInput | None  # the band row of a range entry, None for LEGACY_RANGE / points


@dataclass(frozen=True, slots=True)
class Resolved:
    """An obligation with its SSP snapshot, the sources of its selected SSP and its merges."""

    draft: PobDraft
    ssp: SspResolution
    sources: tuple[SourceRef, ...]
    revenue_account: str | None  # the SSP entry's revenue account (REQ-SSP-014)
    merged: tuple[str, ...]  # subject keys merged into it by S03-R-13
    # The canonical inputs behind the T-CON-11 SSP snapshot columns (lane ENG-T1F; Codex T1F-R1):
    # None for a merged obligation (S03-R-13 sums over parts) or an unresolved bypass.
    source: SnapshotSource | None = None


def apportion(
    total_minor: int, minor_unit: int, weights: Sequence[Fraction], keys: Sequence[str]
) -> tuple[Quota, ...]:
    """S05-R-10: a_p = ``largest_remainder(T, w, keys)[p]``; x_p = (T ÷ 10^μ) × w_p ÷ Σw (CV-34).

    Asserts S05-INV-01 (Σ a_p = T), S05-INV-02 (|x_p × 10^μ − a_p| < 1) and S05-INV-03 (weight 0
    gives 0) and raises ``EngineError("ENGINE_INVARIANT_VIOLATED")`` on failure (CV-46). Σw = 0 is
    the caller's ``TOTAL_SSP_ZERO``; a negative weight raises ``NEGATIVE_WEIGHT``.
    """
    # Through the module attribute, so the CTL-012 test can corrupt the apportionment.
    posted = money.largest_remainder(total_minor, list(weights), list(keys))
    scale: int = 10**minor_unit
    total_weight = sum(weights, Fraction(0))
    exact = [Fraction(total_minor, scale) * weight / total_weight for weight in weights]
    if sum(posted) != total_minor:
        raise _invariant("S05-INV-01", "posted allocations do not sum to the allocation basis")
    for key, weight, x_p, a_p in zip(keys, weights, exact, posted, strict=True):
        if not abs(x_p * scale - a_p) < 1:
            raise _invariant("S05-INV-02", "a posted allocation is a minor unit from exact", key)
        if weight == 0 and (a_p != 0 or x_p != 0):
            raise _invariant("S05-INV-03", "an obligation with weight 0 is allocated", key)
    return tuple(Quota(x_p, a_p) for x_p, a_p in zip(exact, posted, strict=True))


def merge_immaterial(items: Sequence[Resolved]) -> list[Resolved]:
    """S03-R-13: merge each candidate whose SSP share of its contract is below its threshold.

    Candidates carry ``immaterial_threshold_pct`` from stage 03 (POL-020 ``APPLY_RELIEF``). The
    share is the selected SSP over Σ selected SSP of the contract's obligations before any merge.
    The host is the bundle parent when it is a host obligation of the contract, else the host with
    the largest selected SSP, ties by ascending key; hosts exclude options, VC lines, routed-out
    lease components and merging candidates. The host keeps its key, template and measure; Q, P and
    the SSP values sum, start is the earliest and end the latest date. A candidate without a host
    stays its own obligation.
    """
    by_contract: dict[str, list[Resolved]] = {}
    for item in items:
        by_contract.setdefault(item.draft.contract_key, []).append(item)
    result: list[Resolved] = []
    for contract_key in sorted(by_contract):
        members = sorted(by_contract[contract_key], key=lambda item: item.draft.subject_key)
        total = sum((item.ssp.selected for item in members), Fraction(0))
        candidates = [item for item in members if total > 0 and _below(item, total)]
        moving = {item.draft.subject_key for item in candidates}
        hosts = {
            item.draft.obligation_key: item
            for item in members
            if item.draft.subject_key not in moving
            and item.draft.obligation_kind not in _NOT_HOSTS
            and not item.draft.routed_out
        }
        joined: dict[str, list[Resolved]] = {}
        standalone: list[Resolved] = []
        for candidate in candidates:
            host = _host(candidate, hosts)
            if host is None:
                standalone.append(candidate)
            else:
                joined.setdefault(host, []).append(candidate)
        for item in members:
            key = item.draft.obligation_key
            if item.draft.subject_key in moving:
                continue
            result.append(_merge(item, joined[key]) if key in joined else item)
        result.extend(standalone)
    return sorted(result, key=lambda item: item.draft.subject_key)


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    group: str,
    basis_node: str,
    weights: Sequence[Fraction],
    keys: Sequence[str],
    quotas: Sequence[Quota],
    *,
    sources: Sequence[str] | None = None,
    path: str = "relative",
) -> None:
    """The §5.5 allocation nodes of the relative path (CV-50).

    ``basis_node`` is the pool apportioned: ``tp_allocation_basis``, or ``allocation_remainder``
    after targeted VC. On the exceptions path (S05-R-13) ``sources`` names the node of each exact
    amount x_p, which is the weight, and ``path`` is ``exceptions``; otherwise the weights are the
    ``original_ssp_selected`` nodes.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    total_weight = sum(weights, Fraction(0))
    selected = (
        [f"original_ssp_selected:{key}:-" for key in keys] if sources is None else list(sources)
    )
    total_id = tb.node(
        measure="total_ssp",
        subject_key=group,
        period_key=None,
        value=total_weight,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=RELATIVE,
        inputs=selected,
        params={"path": path, "role": "total"} if path != "relative" else {"role": "total"},
        narrative_key="alloc.relative_ssp",
    )
    joined_keys = ",".join(keys)
    weight_ids: list[str] = []
    for index, (key, weight, quota) in enumerate(zip(keys, weights, quotas, strict=True)):
        weight_id = tb.node(
            measure="allocation_weight",
            subject_key=key,
            period_key=None,
            value=weight / total_weight,
            currency=None,
            minor_unit=None,
            formula_id=RELATIVE,
            inputs=[selected[index], total_id],
            params={"role": "weight"},
            narrative_key="alloc.relative_ssp",
        )
        weight_ids.append(weight_id)
        tb.node(
            measure="original_allocated_exact",
            subject_key=key,
            period_key=None,
            value=quota.x_exact,
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id=RELATIVE,
            # w_p and Σw rather than the weight node: its 18-place encoding would re-evaluate
            # x_p at fewer places (DG-AK-54; L4-3-Q-1).
            inputs=[basis_node, selected[index], total_id],
            params={"role": "exact"},
            narrative_key="alloc.relative_ssp",
        )
    # largest_remainder(T, w, keys)[index] apportions over w_p, not the weight nodes: their 18-place
    # encoding breaks ALG-01 ties on the fractional remainder, so a re-evaluation would give the
    # cent to another key (S05-R-10; DG-AK-54; L4-3-Q-9). The weight nodes stay inputs for lineage.
    for index, (key, weight, quota) in enumerate(zip(keys, weights, quotas, strict=True)):
        tb.node(
            measure="original_allocated_amount",
            subject_key=key,
            period_key=None,
            value=quota.a_posted,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=REMAINDER,
            inputs=[basis_node, *weight_ids, *selected],
            params={"index": str(index), "keys": joined_keys, "weight": format_exact(weight)},
            exact=quota.x_exact,
            narrative_key="alloc.largest_remainder",
        )


def _below(item: Resolved, total: Fraction) -> bool:
    # A residual candidate has SSP 0 until S05-R-12 measures R, so its share is not a materiality
    # test.
    threshold = item.draft.immaterial_threshold_pct
    return (
        threshold is not None
        and not item.ssp.residual_candidate
        and item.ssp.selected / total < threshold
    )


def _host(candidate: Resolved, hosts: dict[str, Resolved]) -> str | None:
    parent = candidate.draft.bundle_parent_obligation_key
    if parent is not None and parent in hosts:
        return parent
    ranked = sorted(hosts.values(), key=lambda item: (-item.ssp.selected, item.draft.subject_key))
    return ranked[0].draft.obligation_key if ranked else None


def _merge(host: Resolved, others: Sequence[Resolved]) -> Resolved:
    draft = host.draft
    members = list(draft.members)
    for other in others:
        members.extend(
            dataclasses.replace(member, rule=MERGE_RULE) for member in other.draft.members
        )
    everyone = (draft, *(other.draft for other in others))
    quantity = sum((d.quantity for d in everyone), Fraction(0))
    price = sum((d.stated_price for d in everyone), Fraction(0))
    merged = dataclasses.replace(
        draft,
        quantity=quantity,
        stated_price=price,
        original_quantity=quantity,
        original_stated_price=price,
        start_date=min((d.start_date for d in everyone if d.start_date is not None), default=None),
        end_date=max((d.end_date for d in everyone if d.end_date is not None), default=None),
        members=tuple(sorted(members, key=lambda member: member.subject_key)),
        price_basis="MERGED",
        split=None,
    )
    return Resolved(
        draft=merged,
        ssp=points.combine([host.ssp, *(other.ssp for other in others)]),
        sources=host.sources + tuple(source for other in others for source in other.sources),
        revenue_account=host.revenue_account,
        merged=host.merged + tuple(other.draft.subject_key for other in others),
    )


def _invariant(invariant: str, message: str, subject_key: str | None = None) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=subject_key,
        detail={"invariant": invariant},
    )
