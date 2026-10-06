"""Stage 03 elections: immaterial promises, shipping, franchisor services and custodial service.

ENGINE_SPEC S03-R-13 to S03-R-16; POL-020, POL-021, POL-094, POL-202; POLICIES §6.2 rows 3, 4
and 14. Private to stage 03. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Final

from erev_engine.enums import (
    BookCode,
    Distinctness,
    ObligationKind,
    RecognitionMethod,
    SatisfactionPattern,
)
from erev_engine.money import to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import bundles
from erev_engine.stages.s03_pob_builder.distinct import merge
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext

__all__ = [
    "FRANCHISOR_OPTIONS",
    "custodial",
    "franchisor_distinct",
    "franchisor_option",
    "franchisor_single",
    "immaterial",
    "immaterial_threshold",
    "shipping",
]

DEFAULT_THRESHOLD: Final = Fraction(1, 100)  # POL-020 immaterial_threshold_pct default 0.01
MAXIMUM_THRESHOLD: Final = Fraction(5, 100)  # POL-020 maximum 0.05
FRANCHISOR_OPTIONS: Final = frozenset(
    {"NOT_ELECTED", "ELECT_DISTINCT_SERVICES", "ELECT_SINGLE_SERVICES_POB"}
)
# 606-10-25-16B: the relief never applies to options; a VC_LINE is no promise.
_NOT_PROMISES: Final = frozenset({ObligationKind.MATERIAL_RIGHT, ObligationKind.VC_LINE})
_NOT_HOSTS: Final = frozenset(
    {ObligationKind.MATERIAL_RIGHT, ObligationKind.SHIPPING, ObligationKind.VC_LINE}
)


def immaterial_threshold(ctx: BookContext, contract_key: str) -> Fraction | None:
    """POL-020: the relief threshold of a contract, or ``None`` under ``ASSESS_ALL``.

    The relief exists in the ASC606 book only (POLICIES §6.2 row 3). The value is the literal
    ``APPLY_RELIEF`` (threshold 0.01) or ``{option, immaterial_threshold_pct}``. Any other value, or
    a threshold outside (0, 0.05], raises ``ValueError`` (CV-45).
    """
    if ctx.framework != BookCode.ASC606:
        return None
    value = ctx.policies.value("pob.immaterial_promise_relief", contract=contract_key)
    threshold = DEFAULT_THRESHOLD
    if isinstance(value, str):
        option: str | None = value
    elif isinstance(value, Mapping):
        option = value.get("option")
        member = value.get("immaterial_threshold_pct")
        threshold = DEFAULT_THRESHOLD if member is None else to_fraction(member)
    else:
        raise ValueError("pob.immaterial_promise_relief holds one POL-020 option")
    if option == "ASSESS_ALL":
        return None
    if option != "APPLY_RELIEF" or not 0 < threshold <= MAXIMUM_THRESHOLD:
        raise ValueError("pob.immaterial_promise_relief is not a valid POL-020 value")
    return threshold


def immaterial(ctx: BookContext, obligations: Sequence[PobDraft]) -> list[PobDraft]:
    """S03-R-13: mark every non-option allocation target a candidate under ``APPLY_RELIEF``.

    The candidate carries the threshold; stage 05 merges it after SSP resolution when its SSP share
    of the contract total is below the threshold (S05 merge step, ENA-11).
    """
    thresholds: dict[str, Fraction | None] = {}
    marked: list[PobDraft] = []
    for obligation in obligations:
        key = obligation.contract_key
        if key not in thresholds:
            thresholds[key] = immaterial_threshold(ctx, key)
        eligible = obligation.obligation_kind not in _NOT_PROMISES and not obligation.routed_out
        threshold = thresholds[key] if eligible else None
        marked.append(dataclasses.replace(obligation, immaterial_threshold_pct=threshold))
    return marked


def shipping(ctx: BookContext, st: IdentifiedState, drafts: Sequence[PobDraft]) -> list[PobDraft]:
    """S03-R-14: under POL-021 ``TRUE`` a ``SHIPPING`` line joins its host's stated price.

    The host is the bundle parent when that parent is a product obligation of the contract, else
    the product obligation with the largest SSP (S05-R-06 point), ties by ascending key; its
    quantity, dates and SSP weights are unchanged. A shipping line without a host, and every
    shipping line under ``FALSE`` (IFRS15 forced), is its own obligation.
    """
    by_contract: dict[str, list[PobDraft]] = {}
    for draft in drafts:
        by_contract.setdefault(draft.contract_key, []).append(draft)
    result: list[PobDraft] = []
    for contract_key in sorted(by_contract):
        lines = sorted(by_contract[contract_key], key=lambda draft: draft.obligation_key)
        election = ctx.policies.value("pob.shipping_as_fulfilment", contract=contract_key)
        if election != "TRUE":
            result.extend(lines)
            continue
        hosts = {
            draft.obligation_key: draft
            for draft in lines
            if draft.obligation_kind not in _NOT_HOSTS and not draft.routed_out
        }
        standalone: list[PobDraft] = []
        for draft in lines:
            if draft.obligation_kind != ObligationKind.SHIPPING:
                if draft.obligation_key not in hosts:
                    standalone.append(draft)
                continue
            host = _host(ctx, st, draft, hosts)
            if host is None:
                standalone.append(draft)
            else:
                hosts[host] = merge(hosts[host], [draft], rule="S03-R-14", weighted=False)
        result.extend([*hosts.values(), *standalone])
    return result


def franchisor_option(ctx: BookContext, st: IdentifiedState, contract_key: str) -> str:
    """POL-202 for a contract; ``NOT_ELECTED`` in the IFRS15 book (POLICIES §6.2 row 14)."""
    if ctx.framework == BookCode.IFRS15:
        return "NOT_ELECTED"
    entity = st.canonical.contracts[contract_key].header.contracting_entity_code
    value = ctx.policies.value(
        "franchisor.preopening_expedient", contract=contract_key, entity=entity
    )
    if not isinstance(value, str) or value not in FRANCHISOR_OPTIONS:
        raise ValueError("franchisor.preopening_expedient is not a POL-202 option")
    return value


def franchisor_distinct(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft:
    """S03-R-15 ``ELECT_DISTINCT_SERVICES``: a pre-opening service line is a distinct obligation."""
    if not _preopening(st, draft):
        return draft
    if franchisor_option(ctx, st, draft.contract_key) != "ELECT_DISTINCT_SERVICES":
        return draft
    return _distinct(draft)


def franchisor_single(
    ctx: BookContext, st: IdentifiedState, drafts: Sequence[PobDraft]
) -> list[PobDraft]:
    """S03-R-15 ``ELECT_SINGLE_SERVICES_POB``: one services obligation per contract, keyed by the
    first pre-opening service line in key order."""
    result: list[PobDraft] = []
    services: dict[str, list[PobDraft]] = {}
    for draft in drafts:
        single = _preopening(st, draft) and (
            franchisor_option(ctx, st, draft.contract_key) == "ELECT_SINGLE_SERVICES_POB"
        )
        if single:
            services.setdefault(draft.contract_key, []).append(draft)
        else:
            result.append(draft)
    for contract_key in sorted(services):
        lines = sorted(services[contract_key], key=lambda draft: draft.obligation_key)
        result.append(merge(_distinct(lines[0]), lines[1:], rule="S03-R-15"))
    return result


def custodial(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft | None:
    """S03-R-16: a ``CUSTODIAL`` line is a ``TIME_ELAPSED`` obligation over its holding period
    under ``CREATE_WHEN_SSP_PROVIDED`` with a resolvable SSP entry; otherwise ``None``.

    A custodial obligation without start and end dates raises ``ValueError`` (CV-45).
    """
    if draft.obligation_kind != ObligationKind.CUSTODIAL:
        return draft
    policy = ctx.policies.value("bill_and_hold.custodial_pob", contract=draft.contract_key)
    if policy != "CREATE_WHEN_SSP_PROVIDED" or bundles.ssp_entry(ctx, st, draft.line) is None:
        return None
    if draft.start_date is None or draft.end_date is None:
        raise ValueError(f"{draft.subject_key}: a custodial obligation needs its holding period")
    return dataclasses.replace(
        draft,
        recognition_method=RecognitionMethod.TIME_ELAPSED,
        satisfaction_pattern=SatisfactionPattern.OVER_TIME,
    )


def _host(
    ctx: BookContext, st: IdentifiedState, line: PobDraft, hosts: Mapping[str, PobDraft]
) -> str | None:
    parent = line.bundle_parent_obligation_key
    if parent is not None and parent in hosts:
        return parent
    ranked: list[tuple[bool, Fraction, str]] = []
    for key in sorted(hosts):
        point = bundles.point_ssp(ctx, st, hosts[key].line)
        ranked.append((point is None, -(point or Fraction(0)), key))
    return min(ranked)[2] if ranked else None


def _preopening(st: IdentifiedState, draft: PobDraft) -> bool:
    product = st.canonical.group.products.get(draft.product_code)
    return product is not None and product.is_franchisor_preopening_service


def _distinct(draft: PobDraft) -> PobDraft:
    return dataclasses.replace(
        draft,
        distinctness=Distinctness.DISTINCT,
        series_increment_unit=None,
        integrates_into_obligation_key=None,
    )
