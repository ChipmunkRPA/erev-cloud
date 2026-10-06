"""Products, bundles and principal-or-agent changes (04 T-REF-20, T-REF-21, E-89, E-105, API-R-23;
03 REQ-REF-012, REQ-REF-013, REQ-REF-014; PRD §2.5 routing row ``PRINCIPAL_AGENT_CHANGE``, §2.6;
SCREENS §10; ENGINE_SPEC §3.3 S03-R-03; POLICIES §0.5; CTL-031; BUILD_SPEC RFD-9).

Pure rules and copy, and the reads later items consume; the reference commands create and change
products and their components. A product is deactivated, never deleted (IM-M). Its
``principal_agent`` changes only through an approved ``PRINCIPAL_AGENT_CHANGE`` request, whose
callbacks live in ``approvals.subjects`` (REQ-REF-012; CTL-031).

The code (04 §14.1 DB-05; item PRODUCT-CODE-FREEZE-1, supervisor ruling R-112 (i)). Contract
lines, the product pin of a computed contract and the engine's bundle name a product by its code,
while SSP entries and account mapping rules hold its id: a renamed product in use left the lines
of its contracts without an SSP entry, and their next computation failed with
``SSP_KEY_NOT_FOUND``. ``code_references`` names what holds a product — an obligation (a contract
line), an SSP entry, an account mapping rule — and the update command refuses a changed code while
one does; the database refuses the same update (DB-05).

Usability (REQ-REF-012). The attribute codes of registry parameter
``disclosure.mandatory_disaggregation_attributes`` must each carry a non-blank value in
``disaggregation`` before the product is usable; an inactive product is not usable.

Bundle components (T-REF-21; L2-1-Q-17). The rows sharing a ``valid_from`` form one component set.
A set replaces the earlier set from its ``valid_from``: a row's ``valid_to`` is the next later set's
``valid_from`` unless the row ends earlier. Within a set the split basis is one of
``relative_ssp`` and ``fixed_percentage``, and fixed percentages add up to 1 (REQ-REF-013).
``bundle_components`` returns the rows valid at a date in ``sequence`` order as the engine's
``BundleComponentInput`` (S03-R-03).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, TypedDict
from uuid import UUID

from erev_engine.bundle import BundleComponentInput
from sqlalchemy import Select, Table, and_, exists, literal, or_, select, union_all
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    account_mapping_rule,
    obligation,
    pob_template_version,
    product,
    product_bundle_component,
    ssp_entry,
)
from erev_api.enums import Distinctness, RegistryScope
from erev_api.problems import ProblemError
from erev_api.registry.resolve import PARAMETERS, setting
from erev_api.registry.versions import (
    POLICY_LEVEL_NOT_ALLOWED,
    POLICY_VALUE_INVALID,
    schema_errors,
)

RULE_PRODUCT: Final = "T-REF-20"
RULE_COMPONENT: Final = "T-REF-21"
RULE_PRINCIPAL_AGENT: Final = "REQ-REF-012"
RULE_POLICY_VALUES: Final = "REQ-POL-003"
# POLICIES §0.6 approval codes of a level-P parameter whose value, once the product exists, changes
# only through an approved request (04 API-R-23 rev 1.110; security ruling R-21, finding SN-7, and
# the supervisor's answer on its scope): every code. The request is one subject — the product's
# policy values, routed as configuration to ``config.approve`` — and a floor: it does not replace
# the estimate, override or judgement approval a value coded EST, OVR or JDG gets elsewhere.
APPROVAL_CODES_BY_REQUEST: Final = frozenset({"CFG", "EST", "OVR", "JDG", "FIX"})
RULE_BUNDLE: Final = "REQ-REF-013"
RULE_CODE_FROZEN: Final = "DB-05"
RULE_LEVEL_P_NOT_READ: Final = "POLICY_PRODUCT_LEVEL_NOT_READ"  # PRD ERR-103
MANDATORY_ATTRIBUTES: Final = "disclosure.mandatory_disaggregation_attributes"
PRINCIPAL_AGENT_POLICY: Final = "pob.principal_or_agent"  # POL-030
RELATIVE_SSP: Final = "relative_ssp"
FIXED_PERCENTAGE: Final = "fixed_percentage"
SPLIT_BASES: Final = (RELATIVE_SSP, FIXED_PERCENTAGE)

# [J] Copy the documents leave open; SCREENS §9.5 "Duplicate code" wording for the code.
CODE_TAKEN: Final = "Product code {code} is already used."
CODE_FROZEN: Final = (
    "The code cannot change: {holders} use this product. Create a new product for the new code."
)
# What names a product once it is in use, in the order the refusal lists them (DB-05), and
# whether a key of the table is led by the product. ``obligation`` has one
# (``ix_obligation__product``) and is probed for each product, however many lines name it; the
# other two have none, so a probe reads the tenant's rows of the table once for EACH product —
# they are read once for the whole set instead (``code_holders``).
_CODE_HOLDERS: Final = (
    ("contract lines", obligation, True),
    ("SSP entries", ssp_entry, False),
    ("account mapping rules", account_mapping_rule, False),
)
UNIT_REQUIRED: Final = "Enter the unit of measure."
TEMPLATE_UNKNOWN: Final = "Choose an obligation template with a published version."
ASSURANCE_NEGATIVE: Final = "Enter an assurance cost per unit of zero or more."
ATTRIBUTE_CODE: Final = "Name the disaggregation attribute."
ATTRIBUTE_VALUE: Final = "Enter a value for this disaggregation attribute."
POLICY_UNKNOWN: Final = "Use the code of a policy parameter."
POLICY_LEVEL: Final = "This parameter cannot be set on a product."
POLICY_FORCED: Final = "The framework fixes this value."
# PRD ERR-103 (rev 1.210; item PRODUCT-POLICY-VALUE-NOT-READ-1, register index 309): the two
# sentences of ``RULE_LEVEL_P_NOT_READ``, each with what applies instead. ``{key}`` is the
# parameter's code: a form that shows the sentence in a banner shows it without its field.
POLICY_NOT_READ_DEFAULT: Final = (
    "This release reads {key} from no product or template. The framework's default applies to "
    "every contract: leave it out, or state the default."
)
POLICY_NOT_READ_REGISTRY: Final = (
    "This release reads {key} from no product or template. The entity's or the workspace's "
    "value applies where the framework does not fix it: set it by a policy version."
)
# The level P values no computation of a contract reads, each with the sentence that refuses it
# (POLICIES §0.5 rule 1, rev 1.125; 04 T-REF-20 and T-REF-23, rev 1.323). Bundle assembly gives a
# product's and a template's value to the engine for an OBLIGATION (``contracts.bundles``), and
# the engine reads these three parameters for a CONTRACT — the readers named beside each pass no
# obligation — so a value stated here was stored, approved with its template version and taken
# by no rule. Under ``POLICY_NOT_READ_DEFAULT`` the framework's default may be stated: no other
# level sets the parameter in this release, so it is the value every contract takes. Under
# ``POLICY_NOT_READ_REGISTRY`` no value may: the registry's value is the one the reader meets.
# The witness is ``backend/tests/architecture/test_level_p_readers.py``: when a reader passes the
# obligation it turns red, and the parameter leaves this set.
LEVEL_P_NOT_READ: Final[Mapping[str, str]] = MappingProxyType(
    {
        # POL-240: stage 04 ``vc.elements`` and ``buildup.realised``, stage 05 ``original``
        "usage.tier_minimum_method": POLICY_NOT_READ_DEFAULT,
        # POL-029: stage 03 ``options._benefit_period``
        "upfront_fee.recognition_period": POLICY_NOT_READ_DEFAULT,
        # POL-021: stage 03 ``elections.shipping``
        "pob.shipping_as_fulfilment": POLICY_NOT_READ_REGISTRY,
    }
)
PRINCIPAL_AGENT_BY_APPROVAL: Final = (
    "Principal or agent changes need approval. Propose a principal or agent change instead."
)
PRINCIPAL_AGENT_UNCHANGED: Final = "The product already has this conclusion."
POLICY_VALUES_BY_APPROVAL: Final = (
    "Policy values of a product change only by approval. Propose a policy values change instead."
)
POLICY_VALUES_UNCHANGED: Final = "The product already has these policy values."
RATIONALE_REQUIRED: Final = "Enter the rationale for the change."
NOT_A_BUNDLE: Final = "Mark the product as a bundle before adding components."
BUNDLE_HAS_COMPONENTS: Final = "Remove the bundle components before clearing Bundle."
COMPONENT_UNKNOWN: Final = "Choose an existing product as the component."
COMPONENT_IS_BUNDLE: Final = "A component must be another product than the bundle."
QUANTITY_POSITIVE: Final = "Enter a quantity per bundle above zero."
RATIO_REQUIRED: Final = "Enter the split percentage of a fixed-percentage component."
RATIO_NOT_ALLOWED: Final = "A split percentage applies only to fixed percentages."
RATIO_RANGE: Final = "Enter a split percentage above 0% and at most 100%."
VALID_RANGE: Final = "Valid to must be after valid from."
COMPONENT_TWICE: Final = "This component already has a row valid from {valid_from}."
SEQUENCE_TWICE: Final = "Another component valid from {valid_from} uses sequence {sequence}."
MIXED_BASIS: Final = "The components valid from {valid_from} must share one split basis."
PERCENT_TOTAL: Final = (
    "The split percentages of the components valid from {valid_from} total {total}%. "
    "They must total 100%."
)
# SCREENS §10.4 drawer banner (REQ-REF-012).
UNUSABLE_BANNER: Final = "This product cannot be used on contracts until {attributes} are set."


class Usability(TypedDict):
    """``usability``: whether contracts may use the product, and the mandatory attributes missing
    from ``disaggregation`` in registry order (REQ-REF-012)."""

    usable: bool
    missing: list[str]


@dataclass(frozen=True, slots=True)
class ComponentDraft:
    """One T-REF-21 row of ``PUT /products/{id}/bundle-components`` with parsed decimals."""

    component_product_id: UUID
    quantity_per_bundle: Decimal
    split_basis: str
    split_ratio: Decimal | None
    sequence: int
    valid_from: date
    valid_to: date | None


def exact_text(value: Decimal | None) -> str | None:
    """API-C-06 ``erev.exact`` text: trailing zeros trimmed, no exponent."""
    if value is None:
        return None
    text = format(Decimal(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _error(field: str, message: str, rule_id: str = RULE_PRODUCT) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _held(position: int, table: Table, wanted: Sequence[UUID], *, keyed: bool) -> Select[Any]:
    """``(position, product id)`` for the products among ``wanted`` that a row of ``table``
    references. With a key led by the product each product is probed and the probe stops at the
    first row; without one the rows of the tenant are read once and the products named among them
    kept (a page of 200 products probed 1,200 SSP entries 200 times: 84,000 buffers, 44 ms)."""
    holder = literal(position).label("holder")
    if keyed:
        return select(holder, product.c.id).where(
            product.c.id.in_(wanted),
            exists().where(
                table.c.tenant_id == product.c.tenant_id, table.c.product_id == product.c.id
            ),
        )
    return select(holder, table.c.product_id).where(table.c.product_id.in_(wanted)).distinct()


def code_holders(session: Session, product_ids: Collection[UUID]) -> dict[UUID, list[str]]:
    """DB-05 for a set of products: what holds each of ``product_ids``, by name in the order the
    refusal lists them — ``contract lines``, ``SSP entries``, ``account mapping rules`` —, each
    when a row of that kind references the product; a product nothing references has no entry.
    One statement whatever the number of products (DG-LST-10), a branch for each holder
    (``_held``). This is THE predicate — the update command's refusal (``code_frozen_errors``)
    and the derived read-only ``ProductOut.code_frozen`` both read it, so the screen and the
    command agree; ``tg_product__code_frozen`` holds the same three references in the database."""
    if not product_ids:
        return {}
    wanted = sorted(set(product_ids), key=str)
    held = union_all(
        *(
            _held(position, table, wanted, keyed=keyed)
            for position, (_, table, keyed) in enumerate(_CODE_HOLDERS)
        )
    )
    found: dict[UUID, list[str]] = {}
    for position, product_id in sorted(session.execute(held).tuples()):
        found.setdefault(UUID(str(product_id)), []).append(_CODE_HOLDERS[position][0])
    return found


def code_references(session: Session, product_id: UUID) -> list[str]:
    """What holds the product, by name: ``contract lines``, ``SSP entries``, ``account mapping
    rules`` — each when a row of that kind references it (DB-05; ``code_holders``)."""
    return code_holders(session, [product_id]).get(product_id, [])


def code_frozen_errors(session: Session, product_id: UUID) -> list[ProblemError]:
    """422 on ``code`` with rule DB-05 for a product in use; none for an unused one."""
    holders = code_references(session, product_id)
    if not holders:
        return []
    named = holders[0] if len(holders) == 1 else ", ".join(holders[:-1]) + " and " + holders[-1]
    return [_error("code", CODE_FROZEN.format(holders=named), RULE_CODE_FROZEN)]


def assurance_cost_errors(value: Decimal | None) -> list[ProblemError]:
    """T-REF-20 ``CHECK (assurance_cost_per_unit IS NULL OR assurance_cost_per_unit >= 0)``."""
    if value is None or value >= 0:
        return []
    return [_error("assurance_cost_per_unit", ASSURANCE_NEGATIVE)]


def disaggregation_errors(values: Mapping[str, Any]) -> list[ProblemError]:
    """``disaggregation`` maps non-blank attribute codes to non-blank text values (T-REF-20)."""
    errors: list[ProblemError] = []
    for code in sorted(values):
        where = f"disaggregation.{code}"
        value = values[code]
        if not code.strip():
            errors.append(_error(where, ATTRIBUTE_CODE))
        elif not isinstance(value, str) or not value.strip():
            errors.append(_error(where, ATTRIBUTE_VALUE))
    return errors


def level_p_read(code: str, value: Any) -> bool:
    """Whether a computation of a contract takes ``value`` of parameter ``code`` stated at level
    P. Outside ``LEVEL_P_NOT_READ`` it does. Inside, the engine takes the parameter for a
    contract and never meets the value: the framework's default — one value for both frameworks,
    the value every contract takes — is admitted where the sentence says so, and nothing else."""
    sentence = LEVEL_P_NOT_READ.get(code)
    if sentence is None:
        return True
    return sentence == POLICY_NOT_READ_DEFAULT and value == PARAMETERS[code].default_asc606


def policy_values_errors(values: Mapping[str, Any]) -> list[ProblemError]:
    """Level P values (POLICIES §0.5 rule 1; DG-KRN-REG-06 applied to the product level): each code
    names a registry parameter allowed at ``PRODUCT`` and not fixed by both frameworks, a
    computation reads the value at that level (``level_p_read``; PRD ERR-103), and each value
    satisfies the parameter's value schema (L2-1-Q-16). One check for the four doors that store
    such values: ``POST /products``, ``PATCH /products/{id}``, the proposal of a product's policy
    values and the outputs of an obligation template version (``policies.templates``)."""
    errors: list[ProblemError] = []
    for code in sorted(values):
        where = f"policy_values.{code}"
        spec = PARAMETERS.get(code)
        if code == PRINCIPAL_AGENT_POLICY:
            # [J] POL-030 at level P is the product's conclusion, which changes only by approval.
            errors.append(_error(where, PRINCIPAL_AGENT_BY_APPROVAL, RULE_PRINCIPAL_AGENT))
        elif spec is None:
            errors.append(_error(where, POLICY_UNKNOWN, POLICY_VALUE_INVALID))
        elif RegistryScope.PRODUCT not in spec.allowed_levels:
            errors.append(_error(where, POLICY_LEVEL, POLICY_LEVEL_NOT_ALLOWED))
        elif spec.is_forced_asc606 and spec.is_forced_ifrs15:
            errors.append(_error(where, POLICY_FORCED, POLICY_VALUE_INVALID))
        elif not level_p_read(code, values[code]):
            sentence = LEVEL_P_NOT_READ[code].format(key=code)
            errors.append(_error(where, sentence, RULE_LEVEL_P_NOT_READ))
        elif messages := schema_errors(spec.value_schema, values[code], where):
            message = messages[0][:1].upper() + messages[0][1:] + "."
            errors.append(_error(where, message, POLICY_VALUE_INVALID))
    return errors


def changed_policy_values(current: Mapping[str, Any], proposed: Mapping[str, Any]) -> list[str]:
    """The keys two level-P maps differ in — added, removed or holding another value — sorted."""
    return sorted(
        code
        for code in {*current, *proposed}
        if code not in current or code not in proposed or current[code] != proposed[code]
    )


def policy_values_by_request(
    current: Mapping[str, Any], proposed: Mapping[str, Any]
) -> list[ProblemError]:
    """``PATCH /products/{id}`` (04 API-R-23 rev 1.110; REQ-POL-003): one error per key of
    ``proposed`` that differs from the stored map and whose parameter's approval code is in
    ``APPROVAL_CODES_BY_REQUEST`` — such a value changes through
    ``propose-policy-values-change``. A key that names no parameter is refused the same way."""
    errors: list[ProblemError] = []
    for code in changed_policy_values(current, proposed):
        spec = PARAMETERS.get(code)
        if spec is None or spec.approval_code in APPROVAL_CODES_BY_REQUEST:
            errors.append(
                _error(f"policy_values.{code}", POLICY_VALUES_BY_APPROVAL, RULE_POLICY_VALUES)
            )
    return errors


def mandatory_attributes(session: Session, *, known_at: datetime | None = None) -> list[str]:
    """The attribute codes of ``disclosure.mandatory_disaggregation_attributes`` for the session's
    tenant at ``known_at`` (by default the transaction timestamp; DG-KRN-REG-01)."""
    value = setting(session, MANDATORY_ATTRIBUTES, known_at=known_at)
    return [str(code) for code in value]


def series_product_ids(session: Session, product_ids: Collection[UUID]) -> set[UUID]:
    """D-97 (3a) / SSP-ADMISSION-R1: the products among ``product_ids`` whose default POB template
    (T-REF-22) has a version of ``series`` distinctness (T-REF-23). This is THE predicate — the SSP
    entry admission guard (``domain.ssp.commands.upsert_ssp_entries``) and the derived read-only
    ``ProductOut.requires_explicit_ssp_basis`` both read it, so the editor and the API agree; the
    stored ``distinctness_default`` plays no part (its consistency with the default template is the
    D-98 candidate PRODUCT-CLASS-CONSISTENCY)."""
    if not product_ids:
        return set()
    statement = (
        select(product.c.id)
        .select_from(
            product.join(
                pob_template_version,
                and_(
                    pob_template_version.c.tenant_id == product.c.tenant_id,
                    pob_template_version.c.pob_template_id == product.c.default_pob_template_id,
                ),
            )
        )
        .where(
            product.c.id.in_(sorted(set(product_ids), key=str)),
            pob_template_version.c.distinctness == Distinctness.SERIES.value,
        )
        .distinct()
    )
    return {UUID(str(row_id)) for row_id in session.execute(statement).scalars()}


def usability_of(
    *, is_active: bool, disaggregation: Mapping[str, Any], mandatory: Sequence[str]
) -> Usability:
    """The usability of a product row under the mandatory attribute codes."""
    missing = [
        code
        for code in mandatory
        if not isinstance(disaggregation.get(code), str) or not str(disaggregation[code]).strip()
    ]
    return {"usable": bool(is_active) and not missing, "missing": missing}


def usability(session: Session, product_id: UUID, *, known_at: datetime | None = None) -> Usability:
    """Whether the product may be used on contracts (REQ-REF-012; CTL-028 closes in RPS).

    ``LookupError`` for a product the session cannot see (XR-12).
    """
    row = session.execute(
        select(product.c.is_active, product.c.disaggregation).where(product.c.id == product_id)
    ).one_or_none()
    if row is None:
        raise LookupError(f"product {product_id} is not visible")
    return usability_of(
        is_active=bool(row.is_active),
        disaggregation=dict(row.disaggregation),
        mandatory=mandatory_attributes(session, known_at=known_at),
    )


def bundle_components(
    session: Session, product_id: UUID, *, at: date
) -> tuple[BundleComponentInput, ...]:
    """The components of bundle ``product_id`` valid at ``at``, in ``sequence`` order, as the
    engine's T-REF-21 input (``valid_from <= at < valid_to``; ENGINE_SPEC §3.3 S03-R-03)."""
    component = product.alias("component")
    rows = session.execute(
        select(
            component.c.code,
            product_bundle_component.c.quantity_per_bundle,
            product_bundle_component.c.split_basis,
            product_bundle_component.c.split_ratio,
            product_bundle_component.c.sequence,
            product_bundle_component.c.valid_from,
            product_bundle_component.c.valid_to,
        )
        .select_from(
            product_bundle_component.join(
                component,
                and_(
                    component.c.tenant_id == product_bundle_component.c.tenant_id,
                    component.c.id == product_bundle_component.c.component_product_id,
                ),
            )
        )
        .where(
            product_bundle_component.c.bundle_product_id == product_id,
            product_bundle_component.c.valid_from <= at,
            or_(
                product_bundle_component.c.valid_to.is_(None),
                product_bundle_component.c.valid_to > at,
            ),
        )
        .order_by(product_bundle_component.c.sequence, component.c.code)
    ).all()
    return tuple(
        BundleComponentInput(
            component_product_code=str(row.code),
            quantity_per_bundle=Decimal(row.quantity_per_bundle),
            split_basis=str(row.split_basis),
            split_ratio=None if row.split_ratio is None else Decimal(row.split_ratio),
            sequence=int(row.sequence),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )
        for row in rows
    )


def _row_errors(
    index: int, draft: ComponentDraft, bundle_id: UUID, known: Collection[UUID]
) -> list[ProblemError]:
    where = f"components[{index}]"
    errors: list[ProblemError] = []
    if draft.component_product_id == bundle_id:
        errors.append(_error(f"{where}.component_product_id", COMPONENT_IS_BUNDLE, RULE_COMPONENT))
    elif draft.component_product_id not in known:
        errors.append(_error(f"{where}.component_product_id", COMPONENT_UNKNOWN, RULE_COMPONENT))
    if draft.quantity_per_bundle <= 0:
        errors.append(_error(f"{where}.quantity_per_bundle", QUANTITY_POSITIVE, RULE_COMPONENT))
    if draft.split_basis == FIXED_PERCENTAGE and draft.split_ratio is None:
        errors.append(_error(f"{where}.split_ratio", RATIO_REQUIRED, RULE_COMPONENT))
    elif draft.split_basis == RELATIVE_SSP and draft.split_ratio is not None:
        errors.append(_error(f"{where}.split_ratio", RATIO_NOT_ALLOWED, RULE_COMPONENT))
    elif draft.split_ratio is not None and not Decimal(0) < draft.split_ratio <= 1:
        errors.append(_error(f"{where}.split_ratio", RATIO_RANGE, RULE_COMPONENT))
    if draft.valid_to is not None and draft.valid_to <= draft.valid_from:
        errors.append(_error(f"{where}.valid_to", VALID_RANGE, RULE_COMPONENT))
    return errors


def component_errors(
    drafts: Sequence[ComponentDraft], bundle_id: UUID, known: Collection[UUID]
) -> list[ProblemError]:
    """Row findings in row order, then set findings in ``valid_from`` order (T-REF-21;
    REQ-REF-013). ``known`` holds the ids of the visible products among the components."""
    errors: list[ProblemError] = []
    seen: set[tuple[UUID, date]] = set()
    sequences: set[tuple[date, int]] = set()
    for index, draft in enumerate(drafts):
        errors += _row_errors(index, draft, bundle_id, known)
        start = draft.valid_from.isoformat()
        if (draft.component_product_id, draft.valid_from) in seen:
            message = COMPONENT_TWICE.format(valid_from=start)
            errors.append(
                _error(f"components[{index}].component_product_id", message, RULE_COMPONENT)
            )
        elif (draft.valid_from, draft.sequence) in sequences:
            message = SEQUENCE_TWICE.format(valid_from=start, sequence=draft.sequence)
            errors.append(_error(f"components[{index}].sequence", message, RULE_COMPONENT))
        seen.add((draft.component_product_id, draft.valid_from))
        sequences.add((draft.valid_from, draft.sequence))
    for valid_from in sorted({draft.valid_from for draft in drafts}):
        members = [draft for draft in drafts if draft.valid_from == valid_from]
        bases = {draft.split_basis for draft in members}
        if len(bases) > 1:
            message = MIXED_BASIS.format(valid_from=valid_from.isoformat())
            errors.append(_error("components", message, RULE_BUNDLE))
        elif bases == {FIXED_PERCENTAGE}:
            ratios = [draft.split_ratio for draft in members if draft.split_ratio is not None]
            total = sum(ratios, Decimal(0))
            if len(ratios) == len(members) and total != 1:
                message = PERCENT_TOTAL.format(
                    valid_from=valid_from.isoformat(), total=exact_text(total * 100)
                )
                errors.append(_error("components", message, RULE_BUNDLE))
    return errors


def with_derived_valid_to(drafts: Sequence[ComponentDraft]) -> list[ComponentDraft]:
    """Each row ends at the next later set's ``valid_from`` unless it ends earlier (L2-1-Q-17)."""
    starts = sorted({draft.valid_from for draft in drafts})
    derived: list[ComponentDraft] = []
    for draft in drafts:
        later = [start for start in starts if start > draft.valid_from]
        next_start = later[0] if later else None
        ends = [value for value in (draft.valid_to, next_start) if value is not None]
        derived.append(replace(draft, valid_to=min(ends) if ends else None))
    return derived
