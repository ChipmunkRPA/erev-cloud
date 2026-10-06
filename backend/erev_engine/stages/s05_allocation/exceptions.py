"""Stage 05 discount exception and residual approach.

ENGINE_SPEC §5.4 S05-R-11 (POL-076; 606-10-32-36 to 32-38), S05-R-12 (POL-075; 606-10-32-34(c),
32-35, 32-38) and S05-R-13 (posting on the exceptions path); POLICIES POL-076 rev 1.2 test (c) and
§3.2; finding ``RESIDUAL_REJECTED``; proposals of kind ``DISCOUNT_EXCEPTION`` (CV-16); formulas
``alloc.discount_exception.v1`` and ``alloc.residual.v1``; trace nodes
``discount_exception@<bundle code>:<contract>:-``, ``discount_exception_share:<ob>:-`` and
``residual_ssp:<ob>:-``. Private to stage 05. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import ProductInput, ProposalOut
from erev_engine.enums import SspMethod
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import RawLine
from erev_engine.stages.s05_allocation.relative import Resolved, SnapshotSource
from erev_engine.stages.state import BookContext, Finding, SspResolution
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "DISCOUNT_FORMULA",
    "KIND",
    "RESIDUAL_FORMULA",
    "Bundle",
    "Residual",
    "Resolver",
    "applied",
    "bundles",
    "emit",
    "exact",
    "proposals",
    "residual",
]

# A silent SSP resolution of one line at the group inception (S05-R-02 to S05-R-07).
Resolver = Callable[
    [RawLine], tuple[SspResolution, tuple[SourceRef, ...], str | None, SnapshotSource] | None
]

DISCOUNT_FORMULA: Final = "alloc.discount_exception.v1"
RESIDUAL_FORMULA: Final = "alloc.residual.v1"
DISCOUNT_POLICY: Final = "alloc.discount_exception"  # POL-076
RESIDUAL_POLICY: Final = "ssp.residual_failure"  # POL-075
PROPOSE: Final = "PROPOSE_WITH_APPROVAL"
DISABLED: Final = "DISABLED"
RESIDUAL_OPTIONS: Final = frozenset({"REQUIRE_ESTIMATED_SSP", "BLOCK"})
DEFAULT_TOLERANCE: Final = "0.02"  # POL-076 parameter bundle_discount_tolerance_pp
APPROVAL: Final = "discount_exception_bundle"  # Table 0.4-A OTHER outcome
KIND: Final = "DISCOUNT_EXCEPTION"
STAGE: Final = 5
SEPARATOR: Final = "|"
_DECIMAL: Final = re.compile(r"[0-9]+(?:\.[0-9]+)?")


@dataclass(frozen=True, slots=True)
class Bundle:
    """A bundle product meeting S05-R-11 (a) to (c) over the obligations of one contract."""

    product_code: str
    contract_key: str
    members: tuple[str, ...]  # subject keys of the component obligations, ascending
    price: Fraction  # S_b: the regularly sold bundle price (an observable entry)
    source: SourceRef  # the bundle product's SSP entry
    component_ssp: Fraction  # S_B = Σ SSP of the component obligations
    d_bundle: Fraction  # d_B = S_B − S_b
    d_contract: Fraction  # d_C = Σ SSP − T, a residual candidate counted at R
    proposed_residual: Fraction | None  # R computed with the proposed exception
    tolerance: Fraction
    judgement_key: str | None  # the reviewed OTHER judgement that approves it; None: proposed


@dataclass(frozen=True, slots=True)
class Residual:
    """The residual candidate and R (S05-R-12)."""

    key: str  # subject key
    amount: Fraction


def bundles(
    ctx: BookContext,
    identified: IdentifiedState,
    items: Sequence[Resolved],
    remainder: Fraction,
    at: date,
    resolve: Resolver,
) -> tuple[Bundle, ...]:
    """Every bundle meeting S05-R-11 (a) to (c), by (contract, bundle product code).

    Under POL-076 ``PROPOSE_WITH_APPROVAL``, for each bundle product of the group whose components
    in force at ``at`` are all products of the contract's obligations: (a) every component
    obligation's SSP entry is ``observable``; (b) the bundle product has an ``observable`` entry,
    resolved at quantity 1, giving S_b; (c) with d_B = S_B − S_b and d_C = Σ SSP − T,
    |d_B − d_C| ÷ S_B ≤ ``bundle_discount_tolerance_pp`` (POLICIES POL-076 rev 1.2), and the bundle
    share is not negative. T is the basis less targeted VC; a single residual candidate outside the
    bundle enters Σ SSP at R = T − Σ SSP of the other obligations − S_b.
    """
    cb = identified.canonical
    candidates = [item for item in items if item.ssp.residual_candidate]
    found: list[Bundle] = []
    for contract_key in identified.member_contract_keys:
        option, limit = _discount_policy(ctx, contract_key)
        if option == DISABLED:
            continue
        own = [item for item in items if item.draft.contract_key == contract_key]
        for code in sorted(cb.group.products):
            product = cb.group.products[code]
            codes = _components(product, at)
            if not product.is_bundle or not codes:
                continue
            members = [item for item in own if item.draft.product_code in codes]
            if {item.draft.product_code for item in members} != codes:
                continue
            if any(item.ssp.method != SspMethod.OBSERVABLE for item in members):  # (a)
                continue
            priced = resolve(_bundle_line(members[0].draft.line, code))
            if priced is None or priced[0].method != SspMethod.OBSERVABLE:  # (b)
                continue
            member_keys = {item.draft.subject_key for item in members}
            component_ssp = sum((item.ssp.selected for item in members), Fraction(0))
            others = sum(
                (
                    item.ssp.selected
                    for item in items
                    if item.draft.subject_key not in member_keys and not item.ssp.residual_candidate
                ),
                Fraction(0),
            )
            price = priced[0].selected
            proposed: Fraction | None = None
            total_ssp = others + component_ssp
            share = remainder - others
            if len(candidates) == 1 and candidates[0].draft.subject_key not in member_keys:
                proposed = remainder - others - price
                total_ssp += proposed
                share = price
            d_bundle = component_ssp - price
            d_contract = total_ssp - remainder
            if component_ssp <= 0 or share < 0:
                continue
            if abs(d_bundle - d_contract) > limit * component_ssp:  # (c)
                continue
            found.append(
                Bundle(
                    product_code=code,
                    contract_key=contract_key,
                    members=tuple(sorted(member_keys)),
                    price=price,
                    source=priced[1][0],
                    component_ssp=component_ssp,
                    d_bundle=d_bundle,
                    d_contract=d_contract,
                    proposed_residual=proposed,
                    tolerance=limit,
                    judgement_key=_approval(ctx, identified, contract_key, code),
                )
            )
    return tuple(found)


def applied(found: Sequence[Bundle]) -> Bundle | None:
    """The first approved bundle: a reviewed ``OTHER`` outcome ``discount_exception_bundle``."""
    return next((bundle for bundle in found if bundle.judgement_key is not None), None)


def proposals(found: Sequence[Bundle]) -> tuple[ProposalOut, ...]:
    """One ``DISCOUNT_EXCEPTION`` proposal per bundle meeting (a) to (c) (CV-16)."""
    return tuple(
        ProposalOut(
            kind=KIND,
            subject_key=encode_key(bundle.contract_key),
            summary=None,
            treatments=MappingProxyType({}),
            detail=MappingProxyType(
                {
                    "approved": "false" if bundle.judgement_key is None else "true",
                    "bundle_price": format_exact(bundle.price),
                    "bundle_product_code": bundle.product_code,
                    "component_ssp": format_exact(bundle.component_ssp),
                    "d_bundle": format_exact(bundle.d_bundle),
                    "d_contract": format_exact(bundle.d_contract),
                    "judgement_key": bundle.judgement_key or "",
                    "obligations": SEPARATOR.join(bundle.members),
                    "tolerance": format_exact(bundle.tolerance),
                }
            ),
        )
        for bundle in found
    )


def _latest_status(identified: IdentifiedState, contract_key: str) -> str:
    """The contract's latest E-17 status in the book; ``DRAFT`` without a timeline segment."""
    segments = identified.timelines.get(contract_key, ())
    return segments[-1].status if segments else "DRAFT"


def residual(
    ctx: BookContext,
    items: Sequence[Resolved],
    remainder: Fraction,
    bundle: Bundle | None,
    findings: list[Finding],
    identified: IdentifiedState,
) -> Residual | None:
    """S05-R-12: R = T − Σ SSP of the other obligations, the obligations of an applied discount
    exception counted at their discounted allocation S_b.

    Checks: R > 0, and low ≤ R ≤ high when the candidate's entry has a range. A failure, or several
    candidates without an approved split, raises ``RESIDUAL_REJECTED`` (``ERROR``) under both
    POL-075 options. While the candidate's contract is latest ``DRAFT``, a range failure raises
    nothing and the candidate takes R (D-88 L7-5-Q-7; S03-R-09, S04-R-08a); R ≤ 0 and several
    candidates still raise. ``None`` without a candidate or when a finding blocks.
    """
    candidates = [item for item in items if item.ssp.residual_candidate]
    if not candidates:
        return None
    literals: dict[str, str] = {}
    for item in candidates:
        value = ctx.policies.value(
            RESIDUAL_POLICY, contract=item.draft.contract_key, obligation=item.draft.subject_key
        )
        if not isinstance(value, str) or value not in RESIDUAL_OPTIONS:
            raise ValueError(f"{RESIDUAL_POLICY} holds an unknown literal {value!r} (CV-17)")
        literals[item.draft.subject_key] = value
    if len(candidates) > 1:
        for item in candidates:
            key = item.draft.subject_key
            detail = {"policy": literals[key], "reason": "SEVERAL_CANDIDATES", "rule": "S05-R-12"}
            findings.append(Finding("RESIDUAL_REJECTED", "ERROR", key, detail, STAGE, None))
        return None
    (item,) = candidates
    key = item.draft.subject_key
    members = set() if bundle is None else set(bundle.members)
    others = sum(
        (
            other.ssp.selected
            for other in items
            if other.draft.subject_key != key and other.draft.subject_key not in members
        ),
        Fraction(0),
    )
    amount = remainder - others - (Fraction(0) if bundle is None else bundle.price)
    low, high = item.ssp.low, item.ssp.high
    outside = (low is not None and amount < low) or (high is not None and amount > high)
    if outside and amount > 0 and _latest_status(identified, item.draft.contract_key) == "DRAFT":
        outside = False  # D-88 L7-5-Q-7: a DRAFT contract takes R; activation still refuses it
    if amount <= 0 or outside:
        detail = {
            "high": "" if high is None else format_exact(high),
            "low": "" if low is None else format_exact(low),
            "policy": literals[key],
            "reason": "NOT_POSITIVE" if amount <= 0 else "OUTSIDE_RANGE",
            "residual": format_exact(amount),
            "rule": "S05-R-12",
        }
        findings.append(Finding("RESIDUAL_REJECTED", "ERROR", key, detail, STAGE, None))
        return None
    return Residual(key, amount)


def exact(
    items: Sequence[Resolved],
    remainder: Fraction,
    bundle: Bundle | None,
    found: Residual | None,
) -> tuple[Fraction, ...]:
    """S05-R-13 exact amounts x_p, in item order, summing exactly to T.

    The residual candidate takes R; the obligations of an applied bundle share B = T − Σ SSP of the
    others − R by relative SSP within the bundle; every other obligation takes its SSP.
    """
    members = set() if bundle is None else set(bundle.members)
    residual_key = None if found is None else found.key
    amount = Fraction(0) if found is None else found.amount
    others = sum(
        (
            item.ssp.selected
            for item in items
            if item.draft.subject_key not in members and item.draft.subject_key != residual_key
        ),
        Fraction(0),
    )
    share = remainder - others - amount
    result: list[Fraction] = []
    for item in items:
        key = item.draft.subject_key
        if key == residual_key:
            result.append(amount)
        elif bundle is not None and key in members:
            result.append(share * item.ssp.selected / bundle.component_ssp)
        else:
            result.append(item.ssp.selected)
    return tuple(result)


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    pool_node: str,
    items: Sequence[Resolved],
    remainder: Fraction,
    bundle: Bundle | None,
    found: Residual | None,
) -> tuple[str, ...]:
    """Nodes of the exceptions path; the node of each exact amount x_p, in item order.

    - ``discount_exception@<bundle code>:<contract>:-`` (mode ``remainder``: B = T − Σ SSP of the
      others; mode ``residual``: B = S_b, with R proposed = T − Σ SSP of the others − S_b in
      params).
    - ``discount_exception_share:<ob>:-``: B × SSP_p ÷ Σ SSP of the bundle.
    - ``residual_ssp:<ob>:-``: R = T − Σ of the other inputs.
    """
    members = set() if bundle is None else set(bundle.members)
    residual_key = None if found is None else found.key
    selected = {
        item.draft.subject_key: f"original_ssp_selected:{item.draft.subject_key}:-"
        for item in items
    }
    others = [key for key in selected if key not in members and key != residual_key]
    others_ssp = sum(
        (item.ssp.selected for item in items if item.draft.subject_key in others), Fraction(0)
    )
    sources = dict(selected)
    discount_id: str | None = None
    if bundle is not None:
        with_residual = found is not None
        inputs: list[str | SourceRef] = [pool_node, *(selected[key] for key in others)]
        params = {
            "bundle_price": format_exact(bundle.price),
            "bundle_product_code": bundle.product_code,
            "component_ssp": format_exact(bundle.component_ssp),
            "d_bundle": format_exact(bundle.d_bundle),
            "d_contract": format_exact(bundle.d_contract),
            "judgement_key": bundle.judgement_key or "",
            "members": SEPARATOR.join(bundle.members),
            "mode": "residual" if with_residual else "remainder",
            "signs": ",".join(["+", *("-" for _ in others)]),
            "tolerance": format_exact(bundle.tolerance),
        }
        if with_residual:
            inputs.append(bundle.source)
            params["proposed_residual"] = format_exact(remainder - others_ssp - bundle.price)
            params["value"] = format_exact(bundle.price)
            share = bundle.price
        else:
            share = remainder - others_ssp
        discount_id = tb.node(
            measure=f"discount_exception@{encode_key(bundle.product_code)}",
            subject_key=encode_key(bundle.contract_key),
            period_key=None,
            value=share,
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id=DISCOUNT_FORMULA,
            inputs=inputs,
            params=params,
            narrative_key=DISCOUNT_FORMULA.rsplit(".v", 1)[0],
        )
        weights = {item.draft.subject_key: item.ssp.selected for item in items}
        member_inputs = [selected[key] for key in bundle.members]
        for index, key in enumerate(bundle.members):
            sources[key] = tb.node(
                measure="discount_exception_share",
                subject_key=key,
                period_key=None,
                value=share * weights[key] / bundle.component_ssp,
                currency=ctx.txn_currency,
                minor_unit=None,
                formula_id=DISCOUNT_FORMULA,
                inputs=[discount_id, *member_inputs],
                params={"index": str(index), "role": "share"},
                narrative_key=DISCOUNT_FORMULA.rsplit(".v", 1)[0],
            )
    if found is not None:
        tail = [] if discount_id is None else [discount_id]
        residual_inputs: list[str | SourceRef] = [
            pool_node,
            *(selected[key] for key in others),
            *tail,
        ]
        low, high = _range(items, found.key)
        sources[found.key] = tb.node(
            measure="residual_ssp",
            subject_key=found.key,
            period_key=None,
            value=found.amount,
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id=RESIDUAL_FORMULA,
            inputs=residual_inputs,
            params={
                "high": high,
                "low": low,
                "signs": ",".join(["+", *("-" for _ in residual_inputs[1:])]),
            },
            narrative_key=RESIDUAL_FORMULA.rsplit(".v", 1)[0],
        )
    return tuple(sources[item.draft.subject_key] for item in items)


def _range(items: Sequence[Resolved], key: str) -> tuple[str, str]:
    item = next(item for item in items if item.draft.subject_key == key)
    low, high = item.ssp.low, item.ssp.high
    return ("" if low is None else format_exact(low), "" if high is None else format_exact(high))


def _discount_policy(ctx: BookContext, contract_key: str) -> tuple[str, Fraction]:
    """POL-076: the option and ``bundle_discount_tolerance_pp`` (default 0.02) (CV-17)."""
    value = ctx.policies.value(DISCOUNT_POLICY, contract=contract_key)
    tolerance = DEFAULT_TOLERANCE
    if isinstance(value, str):
        option = value
    elif isinstance(value, Mapping):
        option = value.get("option", "")
        tolerance = value.get("bundle_discount_tolerance_pp", DEFAULT_TOLERANCE)
    else:
        raise ValueError(f"{DISCOUNT_POLICY} holds an unknown value shape (CV-17)")
    if option not in (DISABLED, PROPOSE) or not _DECIMAL.fullmatch(tolerance):
        raise ValueError(f"{DISCOUNT_POLICY} holds an unknown value {value!r} (CV-17)")
    return option, Fraction(tolerance)


def _components(product: ProductInput, at: date) -> frozenset[str]:
    return frozenset(
        component.component_product_code
        for component in product.components
        if component.valid_from <= at and (component.valid_to is None or at <= component.valid_to)
    )


def _bundle_line(line: RawLine, product_code: str) -> RawLine:
    """The bundle product priced as one unit on the contract (S05-R-11 (b))."""
    return dataclasses.replace(
        line,
        product_code=product_code,
        stratification=None,
        quantity=Fraction(1),
        stated_price=Fraction(0),
        bundle_parent_obligation_key=None,
        bundle_product_code=None,
        split=None,
    )


def _approval(
    ctx: BookContext, identified: IdentifiedState, contract_key: str, product_code: str
) -> str | None:
    """The greatest ``judgement_key`` of a reviewed ``OTHER`` record of the contract whose outcome
    ``discount_exception_bundle`` names the bundle product (OQ-A-17)."""
    header = identified.canonical.contracts[contract_key].header
    subjects = {contract_key, encode_key(contract_key)}
    keys = [
        record.judgement_key
        for record in header.judgements
        if record.topic == "OTHER"
        and record.subject_key in subjects
        and record.book_code in (None, ctx.book_code)
        and record.outcome.get(APPROVAL) == product_code
    ]
    return max(keys, default=None)
