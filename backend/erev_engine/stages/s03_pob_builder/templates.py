"""Stage 03 lines, drafts and template resolution (ENGINE_SPEC S03-R-01, S03-R-02, S03-R-04,
S03-R-18).

Private to stage 03. ``collect`` turns an API-S-ContractLine into a ``RawLine`` with the stage 02
truncation applied (S02-R-06). ``resolve`` chooses the POB template: under the parity preset the
seeded legacy templates by line (S03-R-18), otherwise the decision table, else the product default
(S03-R-02). It pins the template version and applies the template date rules (S03-R-01). The draft
dataclasses live here because the stage file map has no ``lines.py``; the package re-exports them.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import rules
from erev_engine.bundle import (
    ContractInput,
    MaterialRightInput,
    ProductInput,
    RuleSetInput,
    SspEntryInput,
    TemplateInput,
)
from erev_engine.dates import add_months
from erev_engine.enums import (
    Distinctness,
    LicenceNature,
    ObligationKind,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    ScopeFlag,
    WarrantyType,
)
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import (
    obligation_subject_key,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.state import BookContext, Finding

__all__ = [
    "PRICE_BUNDLE",
    "PRICE_LINE",
    "PRICE_MERGED",
    "PRICE_TERM",
    "BundleSplit",
    "MemberLine",
    "PobDraft",
    "RawLine",
    "collect",
    "decision",
    "effective_rule_sets",
    "line_facts",
    "resolve",
    "template_version",
]

# How a draft's stated price arose (trace formula choice, §3.4).
PRICE_LINE: Final = "LINE"  # total_price of the line
PRICE_TERM: Final = "ENFORCEABLE_TERM"  # S02-R-06 enforceable consideration
PRICE_BUNDLE: Final = "BUNDLE_SPLIT"  # S03-R-03
PRICE_MERGED: Final = "MERGED"  # S03-R-05, S03-R-14, S03-R-15

# S03-R-18: the seeded parity templates (T-MIG-01; REQ-MIG-006).
LEGACY_VC: Final = "LEGACY-VC"
LEGACY_MATERIAL_RIGHT: Final = "LEGACY-MATERIAL-RIGHT"
LEGACY_DISTINCT: Final = "LEGACY-DISTINCT"
LEGACY_NONDISTINCT: Final = "LEGACY-NONDISTINCT"
_PARITY_PRESET: Final = "LEGACY_PARITY"

EntryLookup = Callable[["RawLine"], SspEntryInput | None]

_MEMOS: Final = ("memo_1", "memo_2", "memo_3")
_START_FROM_LINE: Final = frozenset({"LINE_START", "LICENCE_START_OR_AVAILABLE"})
_START_UNKNOWN: Final = frozenset({"CONTROL_TRANSFER", "FIRST_USAGE"})


@dataclass(frozen=True, slots=True)
class BundleSplit:
    """S03-R-03: a bundle line price apportioned over its components (trace params)."""

    bundle_key: str  # obligation key of the bundle line
    bundle_price: Fraction
    split_basis: str  # "relative_ssp" | "fixed_percentage"
    keys: tuple[str, ...]  # component obligation keys, sequence order
    weights: tuple[Fraction, ...]


@dataclass(frozen=True, slots=True)
class MemberLine:
    """A booking line of an obligation: its own line or a merged line (S03-INV-01)."""

    subject_key: str
    obligation_key: str
    quantity: Fraction
    stated_price: Fraction
    rule: str  # "LINE", "S03-R-05", "S03-R-13", "S03-R-14" or "S03-R-15"
    weighted: bool  # False: price only, no quantity and SSP weight 0 (S03-R-14)
    line: RawLine  # the member's line, for its own SSP at stage 05 (S03-R-05 SSP weights are sums)


@dataclass(frozen=True, slots=True)
class RawLine:
    """A booking or added line before template resolution (S03-R-01)."""

    contract_key: str
    obligation_key: str
    product_code: str
    stratification: str | None
    quantity: Fraction
    stated_price: Fraction
    line_start_date: date | None
    line_end_date: date | None
    truncated_end_date: date | None  # S02-R-06
    pricing_date: date  # D-18: group inception, or the modification effective date
    template_date: date  # contract inception (booking lines) or the pricing date (added lines)
    performing_entity: str
    ssp_version_label: str | None
    account_overrides: Mapping[str, str]
    scope_flag: ScopeFlag
    out_of_scope_amount: Fraction | None
    bundle_parent_obligation_key: str | None
    bundle_product_code: str | None  # fact bundle_parent.code of an exploded component
    memos: Mapping[str, str]
    price_basis: str  # PRICE_LINE | PRICE_TERM | PRICE_BUNDLE
    split: BundleSplit | None

    @property
    def subject_key(self) -> str:
        return obligation_subject_key(self.contract_key, self.obligation_key)


@dataclass(frozen=True, slots=True)
class PobDraft:
    """Obligation terms without allocation (ENGINE_SPEC §3.1; §0.11 ``ObligationState`` terms)."""

    subject_key: str  # CV-21 "<contract>/<obligation_key>"
    contract_key: str
    obligation_key: str
    product_code: str
    sku_number: str | None
    stratification: str | None
    quantity: Fraction  # Q
    stated_price: Fraction  # P
    original_quantity: Fraction
    original_stated_price: Fraction
    start_date: date | None
    end_date: date | None
    pricing_date: date
    contracting_entity: str
    performing_entity: str
    ssp_version_label: str | None
    account_overrides: Mapping[str, str]
    scope_flag: ScopeFlag
    out_of_scope_amount: Fraction | None
    bundle_parent_obligation_key: str | None
    bundle_product_code: str | None
    memos: Mapping[str, str]
    template_code: str
    template_version_key: str  # pinned (POLICIES §0.5 rule 3)
    template_basis: str  # "RULE" | "PRODUCT_DEFAULT" | "LEGACY_PARITY"
    rule_key: str | None
    obligation_kind: ObligationKind
    distinctness: Distinctness
    series_increment_unit: str | None
    satisfaction_pattern: SatisfactionPattern
    over_time_criterion: str  # E-20
    recognition_method: RecognitionMethod
    ratable_convention: RatableConvention | None
    principal_agent: PrincipalAgent
    warranty_type: WarrantyType
    licence_nature: LicenceNature
    revenue_category: str | None
    is_vc_line: bool
    integrates_into_obligation_key: str | None  # S03-R-05 reviewed outcome
    members: tuple[MemberLine, ...]  # subject key; the draft's own line included
    price_basis: str
    split: BundleSplit | None
    line: RawLine  # the line after explosion and truncation (SSP reads, S03-R-14, S03-R-16)
    routed_out: bool  # S03-R-11: LEASE_842 allocation target (PT-09)
    repurchase_outcome: str | None  # S03-R-12: FINANCING | LEASE | RIGHT_OF_RETURN | SALE
    immaterial_threshold_pct: Fraction | None  # S03-R-13 candidate under POL-020 APPLY_RELIEF
    # S03-R-07 to S03-R-10 (ENA-4). Defaulted members, so drafts built before those rules keep their
    # terms: option record and SSP, agent gross-to-net basis, licence recognition start.
    material_right: MaterialRightInput | None = None  # S03-R-07 option record (T-CON-14)
    option_ssp: Fraction | None = None  # S03-R-07; None: stage 05 resolves the entry (S05-R-08)
    gross_amount_memo: Fraction | None = None  # S03-R-09 gross consideration P (REQ-POB-009)
    gross_to_net: Mapping[str, str] | None = None  # S03-R-09 agent basis, retained and supplier
    recognition_start_date: date | None = None  # S03-R-10 earliest revenue date (V5; POL-025)


def collect(
    st: IdentifiedState,
    contract_key: str,
    line: Mapping[str, object],
    *,
    pricing_date: date,
    template_date: date,
    truncations: Mapping[str, tuple[date, Fraction | None]],
) -> RawLine:
    """S03-R-01: one ``RawLine`` per API-S-ContractLine; S03-R-04 refuses quantity 0.

    A line without ``obligation_key``, ``product_code``, ``quantity`` or ``total_price`` raises
    ``ValueError`` (CV-45). Quantity 0 raises ``EngineError("ENGINE_INVARIANT_VIOLATED")``, because
    the import refuses it (``SETUP_QUANTITY_ZERO``).
    """
    header = st.canonical.contracts[contract_key].header
    key = payload_text(line, "obligation_key")
    product_code = payload_text(line, "product_code")
    quantity = payload_fraction(line, "quantity")
    price = payload_fraction(line, "total_price")
    if key is None or product_code is None or quantity is None or price is None:
        raise ValueError(
            f"{contract_key}: a line lacks obligation_key, product_code, quantity or total_price"
        )
    if quantity == 0:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a booking line has quantity 0",
            subject_key=obligation_subject_key(contract_key, key),
            detail={"rule": "S03-R-04"},
        )
    basis, truncated_end = PRICE_LINE, None
    truncated = truncations.get(key)
    if truncated is not None:
        truncated_end, consideration = truncated
        if consideration is not None:
            price, basis = consideration, PRICE_TERM
    memos = {name: text for name in _MEMOS if (text := payload_text(line, name)) is not None}
    return RawLine(
        contract_key=contract_key,
        obligation_key=key,
        product_code=product_code,
        stratification=payload_text(line, "stratification"),
        quantity=quantity,
        stated_price=price,
        line_start_date=payload_date(line, "start_date"),
        line_end_date=payload_date(line, "end_date"),
        truncated_end_date=truncated_end,
        pricing_date=pricing_date,
        template_date=template_date,
        performing_entity=payload_text(line, "performing_entity_code")
        or header.contracting_entity_code,
        ssp_version_label=payload_text(line, "ssp_version_label"),
        account_overrides=_text_mapping(line, "account_overrides", key),
        scope_flag=ScopeFlag(payload_text(line, "scope_flag") or ScopeFlag.IN_SCOPE_606),
        out_of_scope_amount=payload_fraction(line, "out_of_scope_amount"),
        bundle_parent_obligation_key=payload_text(line, "bundle_parent_obligation_key"),
        bundle_product_code=None,
        memos=MappingProxyType(memos),
        price_basis=basis,
        split=None,
    )


def resolve(
    ctx: BookContext,
    st: IdentifiedState,
    raw: RawLine,
    findings: MutableSequence[Finding],
    entry_of: EntryLookup,
) -> PobDraft | None:
    """S03-R-02 template resolution and the S03-R-01 date rules; ``None`` with ``PRODUCT_UNMAPPED``.

    Order: under the ``LEGACY_PARITY`` preset the S03-R-18 template by line; otherwise the
    ``POB_ASSIGNMENT`` decision table at the pricing date, else ``product.default_template_code``.
    An absent product, no template code or no template version effective at
    ``raw.template_date`` yields ``PRODUCT_UNMAPPED`` (``ERROR``; CTL-003). ``entry_of`` reads the
    line's SSP entry (S05-R-04) for the parity distinct flag.
    """
    cb = st.canonical
    header = cb.contracts[raw.contract_key].header
    product = cb.group.products.get(raw.product_code)
    if product is None:
        findings.append(_unmapped(raw, None))
        return None
    if ctx.tenant_preset == _PARITY_PRESET:
        choice: tuple[str, str | None, str] | None = (
            _legacy_template(raw, product, entry_of),
            None,
            "LEGACY_PARITY",
        )
    else:
        choice = _template_choice(st, raw, product, header)
    if choice is None:
        findings.append(_unmapped(raw, None))
        return None
    code, rule_key, basis = choice
    template = template_version(st, code, raw.template_date)
    if template is None:
        findings.append(_unmapped(raw, code))
        return None
    start, end = _dates(template, raw, header)
    kind = ObligationKind(template.obligation_kind)
    subject = raw.subject_key
    member = MemberLine(
        subject, raw.obligation_key, raw.quantity, raw.stated_price, "LINE", True, raw
    )
    return PobDraft(
        subject_key=subject,
        contract_key=raw.contract_key,
        obligation_key=raw.obligation_key,
        product_code=raw.product_code,
        sku_number=product.sku_number,
        stratification=raw.stratification,
        quantity=raw.quantity,
        stated_price=raw.stated_price,
        original_quantity=raw.quantity,
        original_stated_price=raw.stated_price,
        start_date=start,
        end_date=end,
        pricing_date=raw.pricing_date,
        contracting_entity=header.contracting_entity_code,
        performing_entity=raw.performing_entity,
        ssp_version_label=raw.ssp_version_label,
        account_overrides=MappingProxyType(
            dict(sorted({**template.account_role_overrides, **raw.account_overrides}.items()))
        ),
        scope_flag=raw.scope_flag,
        out_of_scope_amount=raw.out_of_scope_amount,
        bundle_parent_obligation_key=raw.bundle_parent_obligation_key,
        bundle_product_code=raw.bundle_product_code,
        memos=raw.memos,
        template_code=code,
        template_version_key=template.version_key,
        template_basis=basis,
        rule_key=rule_key,
        obligation_kind=kind,
        distinctness=Distinctness(template.distinctness),
        series_increment_unit=template.series_increment_unit,
        satisfaction_pattern=SatisfactionPattern(template.satisfaction_pattern),
        over_time_criterion=template.over_time_criterion,
        recognition_method=RecognitionMethod(template.recognition_method),
        ratable_convention=None
        if template.ratable_convention is None
        else RatableConvention(template.ratable_convention),
        principal_agent=PrincipalAgent(product.principal_agent),
        warranty_type=WarrantyType(template.warranty_type),
        licence_nature=LicenceNature(template.licence_nature),
        revenue_category=template.revenue_category or product.revenue_category,
        is_vc_line=kind == ObligationKind.VC_LINE,
        integrates_into_obligation_key=None,
        members=(member,),
        price_basis=raw.price_basis,
        split=raw.split,
        line=raw,
        routed_out=False,
        repurchase_outcome=None,
        immaterial_threshold_pct=None,
    )


def line_facts(
    raw: RawLine, product: ProductInput | None, header: ContractInput
) -> dict[str, object]:
    """The ``rules.FIELDS["POB_ASSIGNMENT"]`` facts of a line (T-REF-26; S03-R-02, S05-R-02).

    ``customer.segment`` and ``line.term_band`` are not bundle members (§0.4), so they are absent
    and fail every condition on them.
    """
    return {
        "product.code": raw.product_code,
        "product.product_family": None if product is None else product.product_family,
        "bundle_parent.code": raw.bundle_product_code,
        "contract.region": header.region,
        "contract.channel": header.channel,
        "customer.segment": None,
        "contract.contract_type": header.contract_type,
        "line.term_band": None,
        "contract.currency": header.transaction_currency,
        "effective_date": raw.pricing_date,
    }


def effective_rule_sets(versions: Sequence[RuleSetInput], at: date) -> list[RuleSetInput]:
    """Per rule set code, the greatest version with ``effective_from ≤ at < effective_to``."""
    latest: dict[str, RuleSetInput] = {}
    for version in versions:
        if version.effective_from <= at and (
            version.effective_to is None or at < version.effective_to
        ):
            current = latest.get(version.rule_set_code)
            if current is None or version.version_no > current.version_no:
                latest[version.rule_set_code] = version
    return [latest[code] for code in sorted(latest)]


def decision(
    st: IdentifiedState, kind: str, facts: Mapping[str, object], at: date, output: str
) -> tuple[str, str] | None:
    """``(output value, rule_key)`` of the best match over the effective rule sets of ``kind``.

    Greatest specificity, then greatest priority, then ascending ``rule_key``, then ascending rule
    set code (S03-R-02). A matching rule without the output raises ``ValueError`` (T-REF-26).
    """
    best: tuple[tuple[int, int, str, str], str, str] | None = None
    for rule_set in effective_rule_sets(st.canonical.rule_sets.versions.get(kind, ()), at):
        found = rules.match(rule_set, facts)
        if found is None:
            continue
        value = found.outputs.get(output)
        if not isinstance(value, str) or not value:
            raise ValueError(f"rule {found.rule_key} of {rule_set.version_key} has no {output}")
        rank = (-found.specificity, -found.priority, found.rule_key, rule_set.rule_set_code)
        if best is None or rank < best[0]:
            best = (rank, value, found.rule_key)
    return None if best is None else (best[1], best[2])


def template_version(st: IdentifiedState, code: str, at: date) -> TemplateInput | None:
    """The greatest version of ``code`` whose ``[effective_from, effective_to)`` holds ``at``."""
    eligible = [
        version
        for version in st.canonical.templates.versions.get(code, ())
        if version.effective_from <= at
        and (version.effective_to is None or at < version.effective_to)
    ]
    return max(eligible, key=lambda version: version.version_no, default=None)


def _legacy_template(raw: RawLine, product: ProductInput, entry_of: EntryLookup) -> str:
    """S03-R-18: stratification ``VC``; a product mapped to the material-right template; else the
    SSP entry's distinct flag, or the product's ``distinctness_default`` (LM-SSP-03) without one."""
    if raw.stratification == "VC":
        return LEGACY_VC
    if product.default_template_code == LEGACY_MATERIAL_RIGHT:
        return LEGACY_MATERIAL_RIGHT
    entry = entry_of(raw)
    flag = product.distinctness_default if entry is None else entry.distinctness
    return LEGACY_NONDISTINCT if flag == Distinctness.NONDISTINCT else LEGACY_DISTINCT


def _template_choice(
    st: IdentifiedState, raw: RawLine, product: ProductInput, header: ContractInput
) -> tuple[str, str | None, str] | None:
    facts = line_facts(raw, product, header)
    matched = decision(st, "POB_ASSIGNMENT", facts, raw.pricing_date, "pob_template_code")
    if matched is not None:
        return matched[0], matched[1], "RULE"
    if product.default_template_code is not None:
        return product.default_template_code, None, "PRODUCT_DEFAULT"
    return None


def _dates(
    template: TemplateInput, raw: RawLine, header: ContractInput
) -> tuple[date | None, date | None]:
    rule = template.start_date_rule
    start: date | None
    if rule in _START_FROM_LINE:
        start = raw.line_start_date  # LICENCE_START_OR_AVAILABLE: availability in S03-R-10
    elif rule == "BOOKING_DATE":
        start = header.inception_date
    elif rule in _START_UNKNOWN:
        start = None
    else:
        raise ValueError(f"{template.version_key}: unknown start_date_rule {rule!r}")
    rule = template.end_date_rule
    end: date | None
    if rule == "LINE_END":
        end = raw.line_end_date
    elif rule == "START_PLUS_TERM":
        if template.term_months is None:
            raise ValueError(f"{template.version_key}: START_PLUS_TERM needs term_months")
        end = None if start is None else add_months(start, template.term_months) - timedelta(1)
    elif rule == "NONE":
        end = None
    else:
        raise ValueError(f"{template.version_key}: unknown end_date_rule {rule!r}")
    if raw.truncated_end_date is not None:
        end = raw.truncated_end_date  # S02-R-06
    return start, end


def _text_mapping(line: Mapping[str, object], name: str, key: str) -> Mapping[str, str]:
    value = line.get(name)
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ValueError(f"{key}: line member {name} is not an object of strings")
    return MappingProxyType({str(k): str(v) for k, v in sorted(value.items())})


def _unmapped(raw: RawLine, template_code: str | None) -> Finding:
    detail = {"obligation_key": raw.obligation_key, "product_code": raw.product_code}
    if template_code is not None:
        detail["template_code"] = template_code
    return Finding("PRODUCT_UNMAPPED", "ERROR", raw.subject_key, detail, 3, None)
