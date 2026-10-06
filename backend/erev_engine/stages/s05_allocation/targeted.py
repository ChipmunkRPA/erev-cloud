"""Stage 05 targeted variable consideration and negative allocation.

ENGINE_SPEC §5.4 S05-R-14 (POL-044; 606-10-32-39 to 32-41) and S05-R-15 (606-10-32-44); findings
``VC_TARGET_TOLERANCE_EXCEEDED`` and ``VC_ALLOCATION_NEGATIVE``; formula ``alloc.targeted_vc.v1``;
trace nodes ``targeted_vc_allocated@<estimate key>:<ob>:-`` (the element's share of a target) and
``allocation_remainder:<group>:-`` (the allocation basis less targeted VC, S05-R-10). Private to
stage 05. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import (
    encode_key,
    judgement_names_element,
    judgement_names_subject,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s05_allocation import relative
from erev_engine.stages.s05_allocation.relative import Resolved
from erev_engine.stages.state import BookContext, Finding, Quota, TpBuildUp, VcElementView
from erev_engine.trace import TraceBuilder

__all__ = [
    "EVIDENCE",
    "FORMULA",
    "TARGETED",
    "Element",
    "Pool",
    "apportion",
    "emit",
    "emit_remainder",
    "evidenced",
    "negative",
    "remainder",
    "select",
    "share_node",
    "tolerance",
    "totals",
]

FORMULA: Final = "alloc.targeted_vc.v1"
TARGETED: Final = "OBLIGATIONS"  # T-CON-12 allocation_target (REQ-ALC-005)
EVIDENCE: Final = "allocation_criteria_evidence"  # T-CON-12 32-40(a) and (b) attestation
TOLERANCE_POLICY: Final = "vc.targeted_allocation_tolerance"  # POL-044
NOT_ENFORCED: Final = "NOT_ENFORCED"
OVERRIDE: Final = "pol_044_override"  # Table 0.4-A OTHER outcome
STAGE: Final = 5
SEPARATOR: Final = "|"
_NARRATIVE: Final = FORMULA.rsplit(".v", 1)[0]
_PORTFOLIO_PREFIX: Final = "PORTFOLIO:"
_DECIMAL: Final = re.compile(r"[0-9]+(?:\.[0-9]+)?")


@dataclass(frozen=True, slots=True)
class Element:
    """A targeted element (S05-R-14): its build-up view and the subject keys of its targets."""

    view: VcElementView
    contract_key: str | None  # the element's contract; None for a portfolio element
    keys: tuple[str, ...]  # target subject keys, ascending


@dataclass(frozen=True, slots=True)
class Pool:
    """The quota of one targeted element on each of its targets."""

    element: Element
    quotas: tuple[Quota, ...]  # in ``element.keys`` order

    def share(self, key: str) -> Quota | None:
        keys = self.element.keys
        return self.quotas[keys.index(key)] if key in keys else None


def select(
    identified: IdentifiedState, tp: TpBuildUp, items: Sequence[Resolved]
) -> tuple[Element, ...]:
    """S05-R-14: the elements of ``tp`` with ``allocation_target = OBLIGATIONS`` whose pinned
    version carries a non-empty ``allocation_criteria_evidence`` parameter, with their targets.

    A target is an obligation of the element's contract (of any member for a portfolio element)
    whose key, or the key of a line merged into it (S03-R-05, S03-R-13), is a target key. An element
    naming no obligation of the group raises ``ValueError`` (CV-45). Every other element stays in
    the basis apportioned by relative SSP.
    """
    versions = {
        version.version_key: version for version in identified.canonical.bundle.estimate_versions
    }
    found: list[Element] = []
    for view in tp.elements:
        if view.allocation_target != TARGETED:
            continue
        version = versions.get(view.version_key)
        if version is None or not evidenced(version):
            continue
        contract_key = (
            None
            if view.estimate_key.startswith(_PORTFOLIO_PREFIX)
            else view.estimate_key.split("/", 1)[0]
        )
        names = set(view.obligation_keys)
        keys = sorted(
            item.draft.subject_key
            for item in items
            if (contract_key is None or item.draft.contract_key == contract_key)
            and (
                item.draft.obligation_key in names
                or any(member.obligation_key in names for member in item.draft.members)
            )
        )
        if not keys:
            raise ValueError(
                f"{view.estimate_key}: the targeted element names no obligation of the group"
            )
        found.append(Element(view, contract_key, tuple(keys)))
    return tuple(found)


def apportion(
    ctx: BookContext,
    elements: Sequence[Element],
    weights: Mapping[str, Fraction],
    group_key: str,
    findings: list[Finding] | None,
) -> tuple[Pool, ...] | None:
    """K of each element by relative SSP within its targets (S05-R-14; CV-34).

    a = ``largest_remainder(K, w, keys)`` and x = (K ÷ 10^μ) × w ÷ Σw, with K the element's posted
    constrained amount. Targets whose SSPs are all 0 yield ``TOTAL_SSP_ZERO`` (``ERROR``); without
    a findings list it raises. ``None`` when a finding blocks.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    pools: list[Pool] = []
    blocked = False
    for element in elements:
        targets = [weights[key] for key in element.keys]
        if sum(targets, Fraction(0)) == 0:
            detail = {
                "estimate_key": element.view.estimate_key,
                "obligation_count": str(len(targets)),
                "rule": "S05-R-14",
            }
            finding = Finding("TOTAL_SSP_ZERO", "ERROR", encode_key(group_key), detail, STAGE, None)
            if findings is None:
                raise EngineError(
                    finding.code,
                    "every target of a targeted element has SSP 0",
                    subject_key=finding.subject_key,
                    detail=detail,
                )
            findings.append(finding)
            blocked = True
            continue
        quotas = relative.apportion(element.view.amount.posted, minor_unit, targets, element.keys)
        pools.append(Pool(element, quotas))
    return None if blocked else tuple(pools)


def remainder(tp: TpBuildUp, pools: Sequence[Pool]) -> int:
    """T of S05-R-10: ``allocation_basis.posted`` less the posted K of every targeted element."""
    return tp.allocation_basis.posted - sum(pool.element.view.amount.posted for pool in pools)


def totals(
    keys: Sequence[str], quotas: Sequence[Quota], pools: Sequence[Pool]
) -> tuple[Quota, ...]:
    """Each obligation's inception allocation: its share of T plus its targeted shares."""
    result: list[Quota] = []
    for key, quota in zip(keys, quotas, strict=True):
        shares = [share for pool in pools if (share := pool.share(key)) is not None]
        result.append(
            Quota(
                quota.x_exact + sum((share.x_exact for share in shares), Fraction(0)),
                quota.a_posted + sum(share.a_posted for share in shares),
            )
        )
    return tuple(result)


def negative(
    pools: Sequence[Pool], keys: Sequence[str], quotas: Sequence[Quota], findings: list[Finding]
) -> None:
    """S05-R-15: ``VC_ALLOCATION_NEGATIVE`` (``ERROR``) for a target whose total exact allocation
    is negative while its targeted shares are negative, so that targeted VC makes it negative."""
    for key, total in zip(keys, quotas, strict=True):
        shares = [
            (pool.element.view.estimate_key, share)
            for pool in pools
            if (share := pool.share(key)) is not None
        ]
        targeted = sum((share.x_exact for _, share in shares), Fraction(0))
        if shares and total.x_exact < 0 and targeted < 0:
            detail = {
                "allocated_exact": format_exact(total.x_exact),
                "estimate_keys": SEPARATOR.join(estimate for estimate, _ in shares),
                "rule": "S05-R-15",
            }
            findings.append(Finding("VC_ALLOCATION_NEGATIVE", "ERROR", key, detail, STAGE, None))


def tolerance(
    ctx: BookContext,
    identified: IdentifiedState,
    pools: Sequence[Pool],
    weights: Mapping[str, Fraction],
    basis_posted: int,
    findings: list[Finding],
) -> dict[tuple[str, str], dict[str, str]]:
    """The S05-R-14 test under POL-044; the trace params of each tested (element, target).

    r_p = the element's exact share of target p ÷ SSP_p and r_c = basis ÷ ΣSSP over every
    obligation. |r_p − r_c| > tolerance × |r_c| yields ``VC_TARGET_TOLERANCE_EXCEEDED`` (``ERROR``)
    unless a reviewed ``OTHER`` outcome ``pol_044_override = true`` names the element; the params
    record ``tolerance_exceeded`` in both cases. ``NOT_ENFORCED`` (parity) skips the test, and so
    does a target with SSP 0, which has no ratio.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    total_weight = sum(weights.values(), Fraction(0))
    tested: dict[tuple[str, str], dict[str, str]] = {}
    if total_weight == 0:
        return tested
    contract_ratio = Fraction(basis_posted, 10**minor_unit) / total_weight
    for pool in pools:
        view = pool.element.view
        for key, quota in zip(pool.element.keys, pool.quotas, strict=True):
            value = ctx.policies.value(
                TOLERANCE_POLICY, contract=pool.element.contract_key, obligation=key
            )
            if value == NOT_ENFORCED or weights[key] == 0:
                continue
            limit = _limit(value)
            ratio = quota.x_exact / weights[key]
            exceeded = abs(ratio - contract_ratio) > limit * abs(contract_ratio)
            params = {
                "contract_ratio": format_exact(contract_ratio),
                "ratio": format_exact(ratio),
                "tolerance": format_exact(limit),
                "tolerance_exceeded": "true" if exceeded else "false",
            }
            tested[(view.estimate_key, key)] = params
            if exceeded and not _overridden(ctx, identified, pool.element):
                detail = {
                    "contract_ratio": params["contract_ratio"],
                    "estimate_key": view.estimate_key,
                    "ratio": params["ratio"],
                    "rule": "S05-R-14",
                    "tolerance": params["tolerance"],
                }
                findings.append(
                    Finding("VC_TARGET_TOLERANCE_EXCEEDED", "ERROR", key, detail, STAGE, None)
                )
    return tested


def element_node(element: Element) -> str:
    """The stage 04 node of the element's constrained amount K (§4.4 per-element name)."""
    return f"vc_constrained:{element.view.estimate_key}:-"


def share_node(estimate_key: str, subject_key: str) -> str:
    return f"targeted_vc_allocated@{encode_key(estimate_key)}:{subject_key}:-"


def emit_remainder(
    ctx: BookContext,
    tb: TraceBuilder,
    group: str,
    basis_node: str,
    pools: Sequence[Pool],
    value: int,
) -> str:
    """Node ``allocation_remainder:<group>:-``: the basis less every K (signed inputs)."""
    return tb.node(
        measure="allocation_remainder",
        subject_key=group,
        period_key=None,
        value=value,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=FORMULA,
        inputs=[basis_node, *(element_node(pool.element) for pool in pools)],
        params={"role": "remainder", "signs": ",".join(["+", *("-" for _ in pools)])},
        narrative_key=_NARRATIVE,
    )


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    pools: Sequence[Pool],
    tested: Mapping[tuple[str, str], Mapping[str, str]],
) -> None:
    """Nodes ``targeted_vc_allocated@<estimate key>:<ob>:-``: largest_remainder(K, SSP of the
    targets, keys)[index], posted with the exact share in the residue, and the tolerance params."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    for pool in pools:
        element = pool.element
        estimate_key = element.view.estimate_key
        selected = [f"original_ssp_selected:{key}:-" for key in element.keys]
        joined = SEPARATOR.join(element.keys)
        for index, (key, quota) in enumerate(zip(element.keys, pool.quotas, strict=True)):
            params = {
                "estimate_key": estimate_key,
                "index": str(index),
                "keys": joined,
                "role": "share",
                **tested.get((estimate_key, key), {}),
            }
            tb.node(
                measure=f"targeted_vc_allocated@{encode_key(estimate_key)}",
                subject_key=key,
                period_key=None,
                value=quota.a_posted,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=FORMULA,
                inputs=[element_node(element), *selected],
                params=params,
                exact=quota.x_exact,
                narrative_key=_NARRATIVE,
            )


def evidenced(version: EstimateVersionInput) -> bool:
    """The S05-R-14 evidence state of a version: ``allocation_criteria_evidence`` present and not
    the empty string. Shared with the stage 08 S08-R-04 evidence guard and the S05-R-14 quota
    history (D-91), so that both stages read one predicate."""
    value = version.parameters.get(EVIDENCE)
    return value is not None and value != ""


_evidenced = evidenced  # the name the D-91 frozen prototypes and probes call (rerun evidence)


def _limit(value: object) -> Fraction:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise ValueError(f"{TOLERANCE_POLICY} holds an unknown value {value!r} (CV-17)")
    limit = Fraction(value)
    if limit > 1:
        raise ValueError(f"{TOLERANCE_POLICY} lies outside [0, 1] (CV-17)")
    return limit


def _overridden(ctx: BookContext, identified: IdentifiedState, element: Element) -> bool:
    """A reviewed ``OTHER`` outcome ``pol_044_override = true`` naming the element (OQ-A-12).

    D-93 (3) (Table 0.4-A; 04 T-CON-19): the outcome ``estimate_key`` is the element code or the
    §0.4 qualified key, and the record may sit on the contract or on one of its obligations.
    """
    contracts = (
        identified.member_contract_keys if element.contract_key is None else (element.contract_key,)
    )
    for contract_key in contracts:
        header = identified.canonical.contracts[contract_key].header
        for record in header.judgements:
            if (
                record.topic == "OTHER"
                and judgement_names_subject(
                    record.subject_key, contract_key, element.view.obligation_keys
                )
                and record.book_code in (None, ctx.book_code)
                and judgement_names_element(
                    record.outcome.get("estimate_key"),
                    element.view.estimate_key,
                    element.view.element_code,
                )
                and record.outcome.get(OVERRIDE) == "true"
            ):
                return True
    return False
