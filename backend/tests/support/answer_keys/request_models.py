"""Request-model conversion for the WorkspaceAdapter (record §14.2 "following slices (1)"; DG-AK-41;
dev-guide §9.5.3 to §9.5.5).

An answer key writes money as a string in the contract's transaction currency, names estimates,
modifications and judgements by handle, and books ``CONTRACT_ACTIVATED`` with an empty payload;
the API takes ``MoneyIn`` mappings, ids, and a checklist the activation command builds itself.
This module converts one direction only, key → API request model, and validates the result with
the API's own pydantic models, so the conversion is proven without a database:

- ``convert_payload``: a §16.3 event payload → the ``PAYLOADS`` model of its event type (money
  strings → ``MoneyIn`` in the contract currency, recursively through nested models; ``estimate`` +
  ``version_no`` → ``estimate_version_id`` / ``previous_estimate_version_id``; ``modification`` and
  ``judgement`` handles → ids) through an ``IdResolver``;
- ``booking_request``: ``contracts[]`` → ``ContractBookedV1`` (customer by code and name, lines with
  ``unit_price`` as a decimal string, money through the same rule);
- the world's reference requests (``CalendarIn``, ``EntityIn``, ``GlAccountIn``, ``CustomerIn``,
  ``ProductIn``, ``AccountMappingRuleIn``, ``SspBookIn`` / ``SspBookVersionIn`` / ``SspEntriesIn``,
  ``PolicyIn`` grouped by registry category, ``TenantProvisionRequest``);
- ``adapt``: a ``workspace_adapter.Call`` → the keyword arguments of its domain handler (one set
  per handler invocation), which ``real_invoker`` binds; ``bind_check`` proves each set binds to
  the handler's real signature.

Ids the platform assigns (customers, products, templates, calendars, entities, period states,
contracts, groups, obligations, estimates and their versions, judgements, approval
requests, mapping, SSP, rule-set and FX versions, roles, memberships) come from the
``IdResolver``; ``MockResolver`` answers deterministic UUID5 values (a test fixture) and
``ledger_resolver.LedgerResolver`` reads them from the committed results (record §17, RES-1).
Record §18 converts the contract-scoped and remaining world families (judgements, estimates
including the estimate lifecycle route, rule sets, FX rate sets); the three
values the key schema does not carry are refused by name (``SCHEMA_GAPS``, rule FOLL-3, Q-11).
A key's policy overrides have no request model (register index 308): release 1.0 offers no
policy override, the plan has no step for one (``platform_plan._contract_configuration``), and a
call that named the override commands would be refused as any handler without a conversion.
Nothing here touches a database.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import io
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any, Final, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from erev_api import enums as erev_enums
from erev_api.domain.platform.provisioning import TenantProvisionRequest
from erev_api.domain.platform.users import RoleGrant
from erev_api.enums import (
    BookCode,
    ContractEventType,
    Distinctness,
    FilePurpose,
    JournalRunGrain,
    JournalRunMode,
    JudgementTopic,
    RegistryCategory,
    RegistryScope,
    RuleSetKind,
    SspMethod,
)
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, PAYLOADS, ContractBookedV1
from erev_api.money import MoneyIn
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.presets import PRESET_CATEGORY, legacy_parity_values
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn
from erev_api.schemas.accounts import GlAccountIn
from erev_api.schemas.calendars import CalendarIn
from erev_api.schemas.close_runs import CloseRunCreateIn
from erev_api.schemas.contracts import DistinctReviewIn, SubmitActivationIn
from erev_api.schemas.currencies import (
    FxRateIn,
    FxRateSetIn,
    FxRateSetVersionCommandIn,
    FxRateSetVersionIn,
    TenantCurrenciesIn,
)
from erev_api.schemas.customers import CustomerIn
from erev_api.schemas.entities import EntityBookIn, EntityIn
from erev_api.schemas.estimates import (
    EstimateCreateIn,
    EstimateVersionCreateIn,
    EstimateVersionSubmitIn,
    EstimateVersionUpdateIn,
    ScenarioIn,
)
from erev_api.schemas.events import EventAppendIn, EventAppendItemIn
from erev_api.schemas.journals import JournalRunCreateIn
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn
from erev_api.schemas.periods import PeriodOpenIn
from erev_api.schemas.pob_templates import PobTemplateVersionIn
from erev_api.schemas.products import ProductIn
from erev_api.schemas.ssp_books import (
    SspBookIn,
    SspBookVersionIn,
    SspEntriesIn,
    SspEntryIn,
    SspRangeIn,
)
from pydantic import BaseModel
from support.answer_keys.models import (
    AnswerKey,
    Contract,
    Entity,
    Estimate,
    EstimateVersion,
    EventItem,
    FxRateSet,
    GlAccount,
    Judgement,
    PobTemplate,
    Product,
    Rule,
    RuleExampleCase,
    SspBook,
    SspBookVersion,
    World,
)
from support.answer_keys.platform_plan import (
    DISTINCT_BOUND,
    DISTINCT_RATIONALE,
    JOURNAL,
    PRESET_HANDLER,
    STEP1_BOUND,
    STEP1_HANDLE,
    H,
    constraint_judgement,
    constraint_of,
    plan_templates,
    step1_judgement,
    tenant_code,
    tenant_display_name,
)
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.runners import KEY_PRINCIPAL_AGENT
from support.answer_keys.workspace_adapter import Call, decimal_str

__all__ = [
    "EVIDENCE_GAP",
    "PRESET_HANDLER",
    "SCHEMA_GAPS",
    "IdResolver",
    "MockResolver",
    "adapt",
    "bind_check",
    "booking_request",
    "convert_payload",
    "estimate_request",
    "estimate_version_request",
    "event_append",
    "example_case_kwargs",
    "fx_rate_set_request",
    "fx_version_request",
    "handler_of",
    "judgement_request",
    "rule_kwargs",
]

PERSONA_DOMAIN: Final = "answer-keys.local"
# Rule ACT-1 role requirements per actor (dev-guide DG-AK-41 rev 1.38; D-98 candidate 107): the
# approver holds the controller role only — there is no ``approver`` platform role (T-PLT-09 has
# ten system roles) and none is created; the operator is the provisioning operator, checked like
# every other actor for the ``tenant_admin`` grant provisioning gives it (04 §14.3 item 2).
ROLE_CODES: Final[Mapping[str, tuple[str, ...]]] = {
    "ak-preparer": ("revenue_accountant",),
    "ak-approver": ("controller",),
    "ak-ssp-analyst": ("ssp_analyst",),  # D-98 candidate 107a: the only role with ssp.create
    "ak-ssp-approver": ("ssp_approver",),  # the only role with ssp.approve
    "operator": ("tenant_admin",),
}
# Record §18 rule FOLL-3: required API values the key schema (dev-guide §9.5.3, §9.5.4) does not
# carry. ``adapt`` refuses each by name; the question is returned as Q-11, never decided here.
SCHEMA_GAPS: Final[Mapping[str, str]] = {
    H["judgement"]: (
        "JudgementCreateIn.rationale is required; §9.5.4 judgements carry conclusion and "
        "questionnaire only"
    ),
    H["fx_set"]: (
        "FxRateSetIn.name is required; §9.5.3 fx_rate_sets carry code, rate_type and rates only"
    ),
    H["rule_set_submit"]: (
        "submit_rule_set_version needs a TESTED version; run_rule_set_version_tests needs "
        "example cases that §9.5.3 rule_sets do not carry"
    ),
}
# BUILD_SPEC CTR-6 (03 REQ-DAT-014; 04 §16.3 ``evidence_file_ids``), rule FOLL-3 again: a manual
# progress, milestone, cost or acceptance event is refused without an evidence file, and the key
# schema states none. It is a gap of such an ITEM, not of the handler — an integration's event
# and a manual delivery or return convert — so it is not a ``SCHEMA_GAPS`` key.
EVIDENCE_GAP: Final = (
    "EventAppendIn.evidence_file_ids is required for a manual progress, milestone, cost or "
    "acceptance event (REQ-DAT-014); §9.5.3 timeline items carry no evidence document"
)
# The manual event types whose request carries evidence (04 §16.3; ``domain.contracts.events``).
_EVIDENCE_TYPES: Final = frozenset({"PROGRESS_RECORDED", "MILESTONE_ACHIEVED", "COST_INCURRED"})
_ACTIVATION_TYPES: Final = frozenset({"CONTRACT_BOOKED", "CONTRACT_ACTIVATED"})
# CONV-2 / API-R-30: emitted by the estimate lifecycle command, never appended directly.
_LIFECYCLE_TYPES: Final = frozenset({"ESTIMATE_CHANGED"})


def _ignore_version(_: int) -> None:
    """``check_version`` for commands the runner drives without an ``If-Match`` header."""


# --- id resolution --------------------------------------------------------------------------------


class IdResolver(Protocol):
    def customer_id(self, code: str) -> UUID: ...
    def product_id(self, code: str) -> UUID: ...
    def template_id(self, code: str) -> UUID: ...
    def template_version_id(self, code: str) -> UUID: ...
    def gl_account_id(self, code: str) -> UUID: ...
    def calendar_id(self, entity_code: str) -> UUID: ...
    def entity_id(self, code: str) -> UUID: ...
    def period_state_id(self, entity: str, book: str, period_key: str) -> UUID: ...
    def contract_id(self, external_id: str) -> UUID: ...
    def group_id(self, external_id: str) -> UUID: ...
    def estimate_version_id(self, contract: str, element_code: str, version_no: int) -> UUID: ...
    def modification_id(self, contract: str, reference: str) -> UUID: ...
    def judgement_id(self, contract: str, handle: str) -> UUID: ...
    def pending_approval_id(self) -> UUID: ...
    def impact_preview_sha256(self, approval_request_id: UUID) -> str | None: ...
    def subject_sha256(self) -> str: ...
    def pending_approvals(self) -> tuple[tuple[UUID, str], ...]: ...
    def mapping_version_id(self) -> UUID: ...
    def ssp_book_id(self, code: str) -> UUID: ...
    def ssp_version_id(self, code: str, version_no: int) -> UUID: ...
    def ssp_study_id(self, code: str, version_no: int) -> UUID: ...
    def estimate_evidence_id(self, contract: str, element_code: str, version_no: int) -> UUID: ...
    def policy_version_id(self, scope: str, code: str, category: str) -> UUID: ...
    def role_id(self, code: str) -> UUID: ...
    def membership_id(self, persona: str) -> UUID: ...
    def invitation_token(self, persona: str) -> str: ...
    def obligation_id(self, contract: str, obligation_key: str) -> UUID: ...
    def estimate_id(self, contract: str, element_code: str) -> UUID: ...
    def rule_set_id(self, code: str) -> UUID: ...
    def rule_set_version_id(self, code: str) -> UUID: ...
    def fx_set_id(self, code: str) -> UUID: ...
    def fx_version_id(self, code: str) -> UUID: ...


class MockResolver:
    """Deterministic UUID5 ids per (kind, key); a call log for the tests."""

    def __init__(self, key_id: str) -> None:
        self.namespace = uuid5(NAMESPACE_URL, f"erev://answer-keys/{key_id}")
        self.asked: list[tuple[str, str]] = []

    def _id(self, kind: str, *parts: object) -> UUID:
        key = "/".join(str(part) for part in parts)
        self.asked.append((kind, key))
        return uuid5(self.namespace, f"{kind}:{key}")

    def customer_id(self, code: str) -> UUID:
        return self._id("customer", code)

    def product_id(self, code: str) -> UUID:
        return self._id("product", code)

    def template_id(self, code: str) -> UUID:
        return self._id("template", code)

    def template_version_id(self, code: str) -> UUID:
        return self._id("template_version", code)

    def gl_account_id(self, code: str) -> UUID:
        return self._id("gl_account", code)

    def calendar_id(self, entity_code: str) -> UUID:
        return self._id("calendar", entity_code)

    def entity_id(self, code: str) -> UUID:
        return self._id("entity", code)

    def period_state_id(self, entity: str, book: str, period_key: str) -> UUID:
        return self._id("period_state", entity, book, period_key)

    def contract_id(self, external_id: str) -> UUID:
        return self._id("contract", external_id)

    def group_id(self, external_id: str) -> UUID:
        return self._id("group", external_id)

    def estimate_version_id(self, contract: str, element_code: str, version_no: int) -> UUID:
        return self._id("estimate_version", contract, element_code, version_no)

    def modification_id(self, contract: str, reference: str) -> UUID:
        return self._id("modification", contract, reference)

    def judgement_id(self, contract: str, handle: str) -> UUID:
        return self._id("judgement", contract, handle)

    def pending_approval_id(self) -> UUID:
        return self._id("approval", "pending")

    def subject_sha256(self) -> str:
        return "0" * 64

    def pending_approvals(self) -> tuple[tuple[UUID, str], ...]:
        return ((self.pending_approval_id(), self.subject_sha256()),)

    def impact_preview_sha256(self, approval_request_id: UUID) -> str | None:
        return None  # no request exists on the mock platform, so none shows a preview

    def mapping_version_id(self) -> UUID:
        return self._id("mapping_version", "current")

    def ssp_book_id(self, code: str) -> UUID:
        return self._id("ssp_book", code)

    def ssp_version_id(self, code: str, version_no: int) -> UUID:
        return self._id("ssp_version", code, version_no)

    def ssp_study_id(self, code: str, version_no: int) -> UUID:
        return self._id("ssp_study", code, version_no)

    def estimate_evidence_id(self, contract: str, element_code: str, version_no: int) -> UUID:
        return self._id("estimate_evidence", contract, element_code, version_no)

    def policy_version_id(self, scope: str, code: str, category: str) -> UUID:
        return self._id("policy_version", scope, code, category)

    def role_id(self, code: str) -> UUID:
        return self._id("role", code)

    def membership_id(self, persona: str) -> UUID:
        return self._id("membership", persona)

    def invitation_token(self, persona: str) -> str:
        """A well-formed token (43 URL-safe characters, T-PLT-07) per persona; nothing reads it."""
        digest = hashlib.sha256(self._id("invitation", persona).bytes).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def obligation_id(self, contract: str, obligation_key: str) -> UUID:
        return self._id("obligation", contract, obligation_key)

    def estimate_id(self, contract: str, element_code: str) -> UUID:
        return self._id("estimate", contract, element_code)

    def rule_set_id(self, code: str) -> UUID:
        return self._id("rule_set", code)

    def rule_set_version_id(self, code: str) -> UUID:
        return self._id("rule_set_version", code)

    def fx_set_id(self, code: str) -> UUID:
        return self._id("fx_set", code)

    def fx_version_id(self, code: str) -> UUID:
        return self._id("fx_version", code)


# --- money and nested-model conversion ------------------------------------------------------------


def _unwrap(annotation: Any) -> tuple[Any, ...]:
    """The concrete types inside Optional / Union / Annotated annotations."""
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _unwrap(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType):
        found: list[Any] = []
        for arg in typing.get_args(annotation):
            found.extend(_unwrap(arg))
        return tuple(found)
    return (annotation,)


def _is_money(annotation: Any) -> bool:
    return any(candidate is MoneyIn for candidate in _unwrap(annotation))


def _model(annotation: Any) -> type[BaseModel] | None:
    for candidate in _unwrap(annotation):
        if (
            inspect.isclass(candidate)
            and issubclass(candidate, BaseModel)
            and candidate is not MoneyIn
        ):
            return candidate
    return None


def _item_model(annotation: Any) -> type[BaseModel] | None:
    for candidate in _unwrap(annotation):
        if typing.get_origin(candidate) in (tuple, list, Sequence):
            args = typing.get_args(candidate)
            if args:
                return _model(args[0])
    return None


def convert_fields(
    model: type[BaseModel], data: Mapping[str, Any], currency: str
) -> dict[str, Any]:
    """Money strings → ``MoneyIn`` mappings in ``currency`` wherever ``model`` types the field as
    money, recursively through nested models and sequences of models; other values pass through."""
    out: dict[str, Any] = {}
    for name, value in data.items():
        info = model.model_fields.get(name)
        annotation = info.annotation if info is not None else None
        if annotation is None or value is None:
            out[name] = value
        elif _is_money(annotation) and isinstance(value, str):
            out[name] = {"amount": value, "currency": currency}
        elif (item := _item_model(annotation)) is not None and isinstance(value, list | tuple):
            out[name] = [
                convert_fields(item, dict(entry), currency) if isinstance(entry, Mapping) else entry
                for entry in value
            ]
        elif (nested := _model(annotation)) is not None and isinstance(value, Mapping):
            out[name] = convert_fields(nested, dict(value), currency)
        else:
            out[name] = value
    return out


def convert_payload(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    currency: str,
    contract: str,
    resolver: IdResolver,
) -> BaseModel:
    """The validated API payload of one key event (§9.5.5 handles resolved; money in
    ``currency``)."""
    kind = ContractEventType(event_type)
    model = PAYLOADS[(kind, LATEST_SCHEMA_VERSION[kind])]  # the append path requires the latest
    data = dict(payload)
    if "estimate" in data:
        element = str(data.pop("estimate"))
        version_no = int(data.pop("version_no", 1))
        data["estimate_version_id"] = resolver.estimate_version_id(contract, element, version_no)
        if version_no > 1 and "previous_estimate_version_id" in model.model_fields:
            data["previous_estimate_version_id"] = resolver.estimate_version_id(
                contract, element, version_no - 1
            )
    if "modification" in data:
        data["modification_id"] = resolver.modification_id(contract, str(data.pop("modification")))
    if "judgement" in data:
        data["judgement_record_id"] = resolver.judgement_id(contract, str(data.pop("judgement")))
    return model.model_validate(convert_fields(model, data, currency))


def event_append(item: EventItem, contract: Contract, resolver: IdResolver) -> EventAppendIn:
    """API-S-EventAppend for one timeline event (never a booking or activation item)."""
    if item.event_type in _ACTIVATION_TYPES:
        raise ValueError(f"{item.event_type} is booked or activated through its own command")
    if item.event_type in _LIFECYCLE_TYPES:
        raise ValueError(
            f"{item.event_type} is emitted by its lifecycle command (API-R-30; rule CONV-2), never "
            "appended through record_events"
        )
    payload = convert_payload(
        item.event_type,
        item.payload,
        currency=contract.transaction_currency,
        contract=contract.external_id,
        resolver=resolver,
    )
    return EventAppendIn(
        events=[
            EventAppendItemIn(
                event_type=ContractEventType(item.event_type),
                effective_date=item.effective_date,  # type: ignore[arg-type]
                payload=payload.model_dump(mode="json", exclude_none=True),
            )
        ]
    )


# --- booking ------------------------------------------------------------------------------------


def booking_request(contract: Contract, world: World, resolver: IdResolver) -> ContractBookedV1:
    """``ContractBookedV1`` from ``contracts[]``: customer by code and name (``CustomerRefV1``),
    lines with ``unit_price`` as a decimal string, money in the transaction currency."""
    customer = next((item for item in world.customers if item.code == contract.customer), None)
    body: dict[str, Any] = {
        "external_id": contract.external_id,
        "customer": {
            "code": contract.customer,
            "name": customer.name if customer is not None else contract.customer,
        },
        "contracting_entity_code": contract.contracting_entity,
        "transaction_currency": contract.transaction_currency,
        "inception_date": contract.inception_date,
        # 04 table 15.4-I SOURCE_REFERENCE (IMP-100): the order reference an activation asks
        # for. A key states none; the runner names the contract by its own external id.
        "document_ref": contract.external_id,
        "lines": [],
    }
    for name in ("signature_date", "payment_terms", "region", "channel", "contract_type"):
        value = getattr(contract, name)
        if value is not None:
            body[name] = value
    if contract.has_commercial_substance is not None:
        body["has_commercial_substance"] = contract.has_commercial_substance
    if contract.termination is not None:
        body["termination"] = contract.termination.model_dump(exclude_none=True)
    if contract.scope_605_35:
        body["scope_605_35"] = True
    if contract.renewal_of is not None:
        body["renewal_of_contract_id"] = resolver.contract_id(contract.renewal_of)
    if contract.payment_schedule:
        body["payment_schedule"] = [point.model_dump() for point in contract.payment_schedule]
    if contract.noncash_consideration:
        body["noncash_consideration"] = [
            item.model_dump(exclude_none=True) for item in contract.noncash_consideration
        ]
    if contract.consideration_payable:
        body["consideration_payable"] = [
            item.model_dump(exclude_none=True) for item in contract.consideration_payable
        ]
    for line in contract.lines:
        entry = line.model_dump(exclude_none=True)
        if line.unit_price is not None:  # CONV-4: DecimalStr from either admitted encoding
            entry["unit_price"] = decimal_str(
                line.unit_price, contract.transaction_currency, field="unit_price"
            )
        body["lines"].append(entry)
    return ContractBookedV1.model_validate(
        convert_fields(ContractBookedV1, body, contract.transaction_currency)
    )


# --- world requests -------------------------------------------------------------------------------


def provision_request(key: AnswerKey) -> TenantProvisionRequest:
    return TenantProvisionRequest(
        code=tenant_code(key.id),  # the kernel's [J] rule (DG-KRN-TEN-03), never truncated past it
        display_name=tenant_display_name(key.id, key.title),
        reporting_currency=key.world.tenant.reporting_currency,
        is_demo=False,
        admin_email=f"ak-admin@{PERSONA_DOMAIN}",
    )


def calendar_in(entity: Entity) -> CalendarIn:
    return CalendarIn(
        code=f"CAL-{entity.code}"[:32],
        name=f"Calendar {entity.code}",
        pattern=entity.calendar.pattern,  # type: ignore[arg-type]
        fiscal_year_start_month=entity.calendar.fiscal_year_start_month,
        week_end_day=None
        if entity.calendar.week_end_day is None
        else int(entity.calendar.week_end_day),
        year_end_anchor=entity.calendar.year_end_anchor,  # type: ignore[arg-type]
    )


def entity_in(entity: Entity, resolver: IdResolver, first_period_key: str) -> EntityIn:
    return EntityIn(
        code=entity.code,
        name=entity.name,
        functional_currency=entity.functional_currency,
        time_zone=entity.time_zone,
        calendar_id=resolver.calendar_id(entity.code),
        first_period_key=first_period_key,
    )


def gl_account_in(account: GlAccount) -> GlAccountIn:
    debit = account.account_type in ("ASSET", "EXPENSE")
    return GlAccountIn(
        code=account.code,
        name=account.name,
        account_type=account.account_type,  # type: ignore[arg-type]
        normal_balance="D" if debit else "C",  # type: ignore[arg-type]
    )


TEMPLATE_CASE_SUBJECT: Final = (
    "pob_template_version"  # T-REF-27 subject_type (templates.SUBJECT_TYPE)
)
CASE_OBLIGATION_KEY: Final = "O1"


def template_case_facts(world: World, template: PobTemplate, product: Product) -> dict[str, Any]:
    """The one example case a template version is tested over before its submit (DB-03,
    REQ-POL-003):
    a booking of one line of a world product that uses the template, at the world's first period,
    in the tenant's reporting currency — test-side scaffolding in the case shape the kernel
    validates (`templates.case_errors`), never an original input or expected value of the key.
    An over-time template's line carries a one-year service period, as the kernel's own fixtures
    do (`support.factories.SUPPORT_CASE`)."""
    booking_date = f"{world.periods.from_}-01"
    line: dict[str, Any] = {
        "product_code": product.code,
        "obligation_key": CASE_OBLIGATION_KEY,
        "quantity": "1",
        "total_price": "100.00",
    }
    if template.satisfaction_pattern == "OVER_TIME":
        start = date.fromisoformat(booking_date)
        line["start_date"] = booking_date
        line["end_date"] = (start.replace(year=start.year + 1) - timedelta(days=1)).isoformat()
    return {
        "booking_date": booking_date,
        "currency": world.tenant.reporting_currency,
        "lines": [line],
    }


def case_product(world: World, template: PobTemplate) -> Product | None:
    """The world product a template version's example case books: one that names the template;
    for a parity template of the plan (``plan_templates``), which no key product names, one whose
    own template is of the same obligation kind and distinctness — the line stage 03 would give
    that parity template (S03-R-18) — else the world's first product."""
    named = next((item for item in world.products if item.pob_template == template.code), None)
    if named is not None or any(item.code == template.code for item in world.pob_templates):
        return named
    own = {item.code: item for item in world.pob_templates}
    alike = next(
        (
            item
            for item in world.products
            if item.pob_template in own
            and (own[item.pob_template].obligation_kind, own[item.pob_template].distinctness)
            == (template.obligation_kind, template.distinctness)
        ),
        None,
    )
    return alike or next(iter(world.products), None)


def policy_effective_from(kw: Mapping[str, Any]) -> datetime:
    """The plan's policy effective instant (the first period start in every entity zone, from
    ``_Assembler.policy_effective_from``), carried as the step's ``effective_from`` text."""
    text = kw.get("effective_from")
    if not isinstance(text, str) or not text:
        raise NotProvisioned(
            "policy version: the plan step carries no effective_from (04 §16.5 rule 3)",
            H["policy"],
        )
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def mapping_effective_from(kw: Mapping[str, Any]) -> datetime:
    """The account mapping's effective instant — the plan's first period start, the instant its
    policy versions take effect — carried as the creation step's ``effective_from`` text. The
    version is dated at creation because its submit refuses one without a date
    (``mapping.EFFECTIVE_REQUIRED``) and DB-04 freezes the date at submission."""
    text = kw.get("effective_from")
    if not isinstance(text, str) or not text:
        raise NotProvisioned(
            "account mapping: the plan step carries no effective_from (required before "
            "submission; DB-04)",
            H["mapping"],
        )
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def no_row_precondition(row_version: int) -> None:
    """`update_product`'s ``check_version``: the runner is the plan's only writer, so it names no
    ``If-Match`` precondition (the API layer's concern); the current row version is accepted."""
    return None


def product_in(product: Product, resolver: IdResolver) -> ProductIn:
    # The default template is bound after the template is PUBLISHED ([J], T-REF-20): the
    # `product_template` step (`update_product`) sets it; creation names none.
    data: dict[str, Any] = {"code": product.code, "name": product.name}
    for name in (
        "sku_number",
        "product_family",
        "revenue_category",
        "principal_agent",
        "distinctness_default",
        "is_bundle",
        "assurance_cost_per_unit",
    ):
        value = getattr(product, name)
        if value is not None:
            data[name] = value
    # D-83 ruling 1: the answer-key runner resolves a key product that omits ``principal_agent``
    # as PRINCIPAL — the keys' figures assume gross revenue. The product's own default stays
    # NOT_ASSESSED (04 T-REF-20), which the engine refuses to compute (S03-R-09): the first dry
    # run of an activation stopped on PRINCIPAL_AGENT_NOT_ASSESSED. A product states its initial
    # conclusion at creation (REQ-REF-012), so the runner states the ruling's there.
    data.setdefault("principal_agent", KEY_PRINCIPAL_AGENT)
    return ProductIn.model_validate(data)


def template_version_in(template: PobTemplate) -> PobTemplateVersionIn:
    outputs = template.model_dump(exclude_none=True, exclude={"code"})
    return PobTemplateVersionIn.model_validate(outputs)


def mapping_rule_in(row: Any, resolver: IdResolver) -> AccountMappingRuleIn:
    data: dict[str, Any] = {
        "account_role": row.account_role,
        "gl_account_id": resolver.gl_account_id(row.account),
        "priority": row.priority or 0,
    }
    if row.clearing_purpose is not None:
        data["clearing_purpose"] = row.clearing_purpose
    if row.entity is not None:
        data["entity_id"] = resolver.entity_id(row.entity)
    if row.book_code is not None:
        data["book_code"] = row.book_code
    if row.product is not None:
        data["product_id"] = resolver.product_id(row.product)
    if row.revenue_category is not None:
        data["revenue_category"] = row.revenue_category
    return AccountMappingRuleIn.model_validate(data)


def ssp_book_in(book: SspBook) -> SspBookIn:
    return SspBookIn.model_validate(
        {
            "code": book.code,
            "name": f"SSP book {book.code}",
            "entity_code": book.entity,
            "currency": book.currency,
            "resolution_mode": book.resolution_mode,
        }
    )


def ssp_version_in(version: SspBookVersion) -> SspBookVersionIn:
    return SspBookVersionIn.model_validate(
        {
            "legacy_version_label": version.legacy_version_label,
            "effective_from_date": version.effective_from_date,
            "effective_to_date": version.effective_to_date,
            "methodology_label": version.methodology_label,
        }
    )


def ssp_study(code: str, version_no: int) -> bytes:
    """The study document the runner attaches to version ``version_no`` of SSP book ``code``
    (REQ-SSP-008: a version is submitted with its study). A key carries the standalone selling
    prices, not the study behind them, so this is the runner's own page — test-side, never an
    input or an expected value of a key (DG-AK-41): a one-object PDF naming the version, distinct
    per version so each has its own file."""
    title = f"SSP study for {code} version {version_no} (answer-key runner)"
    return (
        b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n"
        + f"2 0 obj << /Title ({title}) >> endobj\n".encode("ascii")
        + b"trailer << /Root 1 0 R /Info 2 0 R >>\n%%EOF\n"
    )


def estimate_evidence(contract: str, element_code: str, version_no: int) -> bytes:
    """The evidence document the runner attaches to version ``version_no`` of an estimated
    element before it is submitted (04 §16.14 rev 1.241, table 15.4-D: a variable-consideration,
    EAC or return-rate version is submitted with its evidence). A key carries the estimate,
    not the document behind it, so this is the runner's own page — test-side, never an input
    or an expected value of a key (DG-AK-41): a one-object PDF naming the version, distinct
    per version so each has its own file."""
    title = (
        f"Evidence of estimate {element_code} version {version_no} of contract {contract} "
        "(answer-key runner)"
    )
    return (
        b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n"
        + f"2 0 obj << /Title ({title}) >> endobj\n".encode("ascii")
        + b"trailer << /Root 1 0 R /Info 2 0 R >>\n%%EOF\n"
    )


def ssp_entries_in(version: SspBookVersion) -> SspEntriesIn:
    entries: list[SspEntryIn] = []
    for entry in version.entries:
        data: dict[str, Any] = {
            "product_code": entry.product,
            "stratification": entry.stratification or "",
            "currency": entry.currency,
            "method": entry.method,
            "distinctness": entry.distinctness,
        }
        # 04 T-REF-31: the server derives the one band of a ``legacy_range`` entry from its list
        # price, discount and range and refuses a client band, an empty list too — so a legacy
        # entry that states no band sends none. Bands a key does state go as stated.
        if entry.method != SspMethod.LEGACY_RANGE.value or entry.ranges:
            data["ranges"] = [
                SspRangeIn.model_validate(band.model_dump(exclude_none=True))
                for band in entry.ranges
            ]
        for name in (
            "region",
            "channel",
            "segment",
            "deal_size_band",
            "term_band",
            "value_basis",
            "unit_list_price",
            "midpoint_discount_ratio",
            "range_ratio",
            "cost_basis",
            "margin_ratio",
            "observable_point",
        ):
            value = getattr(entry, name)
            if value is not None:
                data[name] = value
        if entry.revenue_account is not None:
            data["revenue_account_code"] = entry.revenue_account
        entries.append(SspEntryIn.model_validate(data))
    return SspEntriesIn(entries=entries)


def schema_value(schema: Mapping[str, Any], value: Any) -> Any:
    """A key's value as the API takes it under ``schema``. A key carries numbers as strings and
    sequences as the loader's tuples; the product validates JSON against a parameter's own schema
    (``registry.versions`` for a policy value, ``reports.framework.schema_message`` for a report
    parameter: an array is a list, an integer an int), so a value whose schema says array or
    integer is sent as one — ``["12", "24"]`` as ``[12, 24]``. Everything else goes as the key
    states it, and the product's own validation answers for it."""
    kind = schema.get("type")
    if kind == "array" and isinstance(value, (list, tuple)):
        items: Mapping[str, Any] = schema.get("items") or {}
        return [schema_value(items, item) for item in value]
    if kind == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return value


def policy_groups(values: Mapping[str, Any]) -> dict[RegistryCategory, dict[str, Any]]:
    """The key's policy values grouped by their registry category (one ``PolicyIn`` each), each
    value in the JSON type its parameter declares (``schema_value``)."""
    groups: dict[RegistryCategory, dict[str, Any]] = {}
    for code, value in values.items():
        spec = POLICY_PARAMETERS.get(code)
        if spec is None:
            raise ValueError(f"policy key {code!r} is not in the registry (POLICIES §1)")
        groups.setdefault(spec.category, {})[code] = schema_value(spec.value_schema, value)
    return groups


# --- the adaptation -------------------------------------------------------------------------------


def handler_of(path: str) -> Callable[..., Any]:
    import importlib

    module_name, _, name = path.rpartition(".")
    found = getattr(importlib.import_module(module_name), name)
    if not callable(found):
        raise TypeError(f"{path} is not callable")
    return found  # type: ignore[no-any-return]


def adapt(
    call: Call, key: AnswerKey, resolver: IdResolver, streams: object | None = None
) -> list[dict[str, Any]]:
    """The keyword arguments (without ``uow``) of each handler invocation one call makes; a value
    the key schema does not carry (``SCHEMA_GAPS``) raises ``NotProvisioned`` by name, and so does
    a statement of the runner's own that the key's expected values do not imply
    (``platform_plan.STEP1_BOUND``, ``DISTINCT_BOUND``; dev-guide DG-AK-41). Stateless (WSA-1):
    the expected stream version and the mapping-rule index come from the call the adapter built;
    ``streams`` is accepted and ignored for compatibility."""
    world = key.world
    handler = call.handler
    kw = call.kwargs
    if handler == H["provision"]:
        return [{"request": provision_request(key)}]
    if handler == H["invite"]:
        persona = call.step.subject
        return [
            {
                "email": f"{persona}@{PERSONA_DOMAIN}",
                "display_name": persona,
                "roles": [
                    RoleGrant(role_id=resolver.role_id(code), is_all_entities=True, entity_codes=())
                    for code in ROLE_CODES.get(persona, ())
                ],
            }
        ]
    if handler == H["accept"]:
        # The invited user follows the link of the invitation they were sent (04 T-PLT-07): the
        # token is read back from that message, never generated. The password, the request facts
        # and the runtime are the invoker's (``workspace_adapter.real_invoker``).
        return [{"token": resolver.invitation_token(call.step.subject)}]
    if handler == H["api_client"]:
        # CTR-6: the world's API client, created through the product's command. Its scopes are
        # an access grant (supervisor ruling R-38 (iii); 04 T-PLT-15 rev 1.168), and the command
        # is handed its caller's reading of the setup state (``auto_approval``; dev-guide
        # DG-KRN-APR-08): the plan requests the client before any period is open, so the
        # completion conditions cannot hold and rule AUTO-BOOTSTRAP decides, as for the invites.
        return [
            {
                "name": str(kw["name"]),
                "scopes": [str(code) for code in kw["scopes"]],
                "auto_approval": True,
            }
        ]
    if handler == H["assign_role"]:
        return [
            {
                "membership_id": resolver.membership_id(persona),
                "role_id": resolver.role_id(code),
                "is_all_entities": True,
                "entity_codes": (),
            }
            for persona in call.step.subject.split(",")  # the invited personas, never the operator
            for code in ROLE_CODES[persona]
        ]
    if handler == H["currencies"]:
        return [{"body": TenantCurrenciesIn(currency_codes=list(world.currencies))}]  # type: ignore[arg-type]
    first_period = _first_period_key(world)
    if handler in (
        H["calendar"],
        H["fiscal_year"],
        H["entity"],
        H["entity_book"],
        H["open_period"],
    ):
        code = str(kw["entity_code"])
        entity = next(item for item in world.entities if item.code == code)
        if handler == H["calendar"]:
            return [{"body": calendar_in(entity)}]
        if handler == H["fiscal_year"]:
            return [
                {"calendar_id": resolver.calendar_id(code), "fiscal_year": int(kw["fiscal_year"])}
            ]
        if handler == H["entity"]:
            return [{"body": entity_in(entity, resolver, first_period)}]
        if handler == H["entity_book"]:
            return [
                {
                    "entity_id": resolver.entity_id(code),
                    "code": BookCode(str(kw["book"])),  # CONV-1: the enum, never its string
                    "body": EntityBookIn(is_enabled=True, first_period_key=first_period),
                }
            ]
        return [
            {
                "state_id": resolver.period_state_id(code, str(kw["book"]), period_key),
                "body": PeriodOpenIn(),
                "check_version": _ignore_version,
            }
            for period_key in _period_keys(world, entity)
        ]
    if handler == H["gl_account"]:
        account = next(item for item in world.gl_accounts if item.code == kw["code"])
        return [{"body": gl_account_in(account)}]
    if handler == H["mapping"]:
        return [
            {
                "body": AccountMappingIn(
                    name="Answer-key account mapping", effective_from=mapping_effective_from(kw)
                )
            }
        ]
    if handler == H["mapping_rule"]:
        row = world.account_mapping[int(kw["rule_index"])]
        return [
            {"version_id": resolver.mapping_version_id(), "body": mapping_rule_in(row, resolver)}
        ]
    if handler == H["mapping_test"]:
        return [{"version_id": resolver.mapping_version_id()}]
    if handler == H["mapping_submit"]:
        return [{"version_id": resolver.mapping_version_id(), "comment": None}]
    if handler == H["mapping_publish"]:
        return [{"version_id": resolver.mapping_version_id()}]
    if handler == H["customer"]:
        customer = next(item for item in world.customers if item.code == kw["code"])
        return [{"body": CustomerIn(code=customer.code, name=customer.name)}]
    if handler == H["template"]:
        return [{"code": str(kw["code"]), "name": str(kw["code"]), "description": None}]
    if handler == H["template_version"]:
        template = next(item for item in plan_templates(world) if item.code == kw["code"])
        return [
            {
                "template_id": resolver.template_id(template.code),
                "changes": template_version_in(template).model_dump(exclude_none=True),
                "effective_from": None,
                "source_version_id": None,
            }
        ]
    if handler == H["template_case"] and call.step.subject.startswith("pob_template "):
        template = next(item for item in plan_templates(world) if item.code == kw["code"])
        product = case_product(world, template)
        if product is None:
            where = f"{call.step.phase} {call.step.subject}"
            raise NotProvisioned(
                f"{where}: no product of the world uses template {template.code!r}, so no example "
                "case can name one (DB-03; REQ-POL-003)",
                handler,
            )
        return [
            {
                "subject_type": TEMPLATE_CASE_SUBJECT,
                "subject_id": resolver.template_version_id(template.code),
                "name": f"{product.code} booking",
                "facts": template_case_facts(world, template, product),
                "expected_output": {"drafts": [{"obligation_key": CASE_OBLIGATION_KEY}]},
            }
        ]
    if handler == H["template_test"]:
        return [{"version_id": resolver.template_version_id(str(kw["code"]))}]
    if handler == H["template_submit"]:
        return [{"version_id": resolver.template_version_id(str(kw["code"])), "comment": None}]
    if handler == H["template_publish"]:
        return [{"version_id": resolver.template_version_id(str(kw["code"]))}]
    if handler == H["product"]:
        product = next(item for item in world.products if item.code == kw["code"])
        return [{"body": product_in(product, resolver)}]
    if handler == H["product_template"]:
        product = next(item for item in world.products if item.code == kw["code"])
        return [
            {
                "product_id": resolver.product_id(product.code),
                "changes": {"default_pob_template_id": resolver.template_id(product.pob_template)},
                "check_version": no_row_precondition,
            }
        ]
    if handler in (H["estimate_evidence"], H["estimate_evidence_attach"]) and kw.get("evidence"):
        # 04 §16.14 rev 1.241: the evidence of an estimate version — the SSP study's two
        # commands, told apart by the call (``workspace_adapter``: the step's marker).
        contract_key, element = str(kw["contract"]), str(kw["element_code"])
        version_no = int(kw["version_no"])
        if handler == H["estimate_evidence"]:
            name = f"estimate-evidence-{contract_key}-{element}-v{version_no}.pdf"
            return [
                {
                    "purpose": FilePurpose.ATTACHMENT.value,
                    "stream": io.BytesIO(estimate_evidence(contract_key, element, version_no)),
                    "original_filename": name.lower(),
                    "media_type": "application/pdf",
                }
            ]
        return [
            {
                "file_object_id": resolver.estimate_evidence_id(contract_key, element, version_no),
                "subject_type": "estimate_version",
                "subject_id": resolver.estimate_version_id(contract_key, element, version_no),
                "description": None,
            }
        ]
    if handler in (
        H["ssp_book"],
        H["ssp_version"],
        H["ssp_entries"],
        H["ssp_study"],
        H["ssp_study_attach"],
        H["ssp_submit"],
    ):
        book = next(item for item in world.ssp_books if item.code == kw["code"])
        version_no = int(kw["version"])
        version = book.versions[version_no - 1]
        if handler == H["ssp_book"]:
            return [{"body": ssp_book_in(book)}]
        if handler == H["ssp_version"]:
            return [{"book_id": resolver.ssp_book_id(book.code), "body": ssp_version_in(version)}]
        if handler == H["ssp_entries"]:
            return [
                {
                    "version_id": resolver.ssp_version_id(book.code, version_no),
                    "body": ssp_entries_in(version),
                }
            ]
        if handler == H["ssp_study"]:
            return [
                {
                    "purpose": FilePurpose.SSP_STUDY.value,
                    "stream": io.BytesIO(ssp_study(book.code, version_no)),
                    "original_filename": f"ssp-study-{book.code}-v{version_no}.pdf".lower(),
                    "media_type": "application/pdf",
                }
            ]
        if handler == H["ssp_study_attach"]:
            return [
                {
                    "file_object_id": resolver.ssp_study_id(book.code, version_no),
                    "subject_type": "ssp_book_version",
                    "subject_id": resolver.ssp_version_id(book.code, version_no),
                    "description": None,
                }
            ]
        # The submission; its approval is a decision of the SSP approver (``decide``), which
        # publishes the version through the engine's own hook.
        return [
            {
                "version_id": resolver.ssp_version_id(book.code, version_no),
                "comment": None,
                "check_version": _ignore_version,
            }
        ]
    if handler == PRESET_HANDLER or kw.get("preset"):
        preset = str(kw.get("preset", ""))
        if preset != "LEGACY_PARITY":
            raise NotProvisioned(f"tenant preset {preset!r} has no lifecycle here (rule CONV-3)")
        if handler == PRESET_HANDLER:  # creation: on a fresh ledger there is no version to resolve
            return [{"scope": RegistryScope.TENANT, "entity_code": None, "book_code": None}]
        # test / submit / publish name exactly the version the committed creation returned (RES-3)
        version_id = resolver.policy_version_id("TENANT", "preset", preset)
        if handler == H["policy_effective"]:
            changes: dict[str, Any] = {"effective_from": policy_effective_from(kw)}
            overlay = policy_groups(dict(kw.get("values") or {}))
            if overlay:
                # ONE version: the preset's values overlaid by the key's tenant values of the
                # preset's category (``platform_plan.preset_overlay``), each in its JSON type.
                (category,) = overlay  # the plan hands over the preset's category alone
                if category is not PRESET_CATEGORY:
                    raise NotProvisioned(
                        f"tenant preset {preset!r}: values of {category.value} are not the "
                        "preset version's (rule CONV-3)"
                    )
                changes["values"] = {
                    **legacy_parity_values(scope=RegistryScope.TENANT, book_code=None),
                    **overlay[category],
                }
            return [
                {
                    "version_id": version_id,
                    "changes": changes,
                    "check_version": no_row_precondition,
                }
            ]
        if handler == H["policy_test"]:
            return [{"version_id": version_id, "run_simulation": False}]
        if handler == H["policy_submit"]:
            return [{"version_id": version_id, "comment": None}]
        if handler == H["policy_publish"]:
            return [{"version_id": version_id}]
    if handler in (H["policy"], H["policy_test"], H["policy_submit"], H["policy_publish"]):
        scope, code = str(kw["scope"]), str(kw["scope_code"])
        groups = policy_groups(dict(kw["values"]))
        if handler == H["policy"]:
            return [
                {
                    "category": category,
                    "scope": RegistryScope(scope),  # CONV-1: the enum, never its string
                    "entity_code": code if scope == "ENTITY" else None,
                    "book_code": BookCode(code) if scope == "BOOK" else None,
                    "values": values,
                    # 04 §16.5 rule 3: the first period start, a future period start at setup
                    "effective_from": policy_effective_from(kw),
                }
                for category, values in groups.items()
            ]
        if handler == H["policy_test"]:
            return [
                {
                    "version_id": resolver.policy_version_id(scope, code, category.value),
                    "run_simulation": False,
                }
                for category in groups
            ]
        if handler == H["policy_submit"]:
            return [
                {
                    "version_id": resolver.policy_version_id(scope, code, category.value),
                    "comment": None,
                }
                for category in groups
            ]
        return [
            {"version_id": resolver.policy_version_id(scope, code, category.value)}
            for category in groups
        ]
    if handler == H["decide"]:
        # READ-3: one decision per pending request of the latest submission, each bound to its
        # own (approval request id, subject hash) pair (RES-2).
        return [
            {
                "approval_request_id": request_id,
                "decision": "APPROVE",
                "subject_content_sha256": digest,
                # REQ-PLT-015: the digest of the preview the request shows, when it has one
                "impact_preview_sha256": resolver.impact_preview_sha256(request_id),
                "comment": None,
                "reason_code": None,
            }
            for request_id, digest in resolver.pending_approvals()
        ]
    if handler == H["book"]:
        contract = next(item for item in key.contracts if item.external_id == kw["contract"])
        return [{"body": booking_request(contract, world, resolver), "origin": "UI"}]
    if handler == H["submit_activation"]:
        contract_key = str(kw["contract"])
        return [
            {
                "contract_id": resolver.contract_id(contract_key),
                "expected_stream_version": int(kw["expected_stream_version"]),
                "body": SubmitActivationIn(),
            }
        ]
    if handler == H["record_events"] and kw.get("step1"):
        # The runner's own Step 1 assessment (``platform_plan._activation_prerequisites``): each
        # event cites the runner's reviewed record of the contract.
        contract_key = str(kw["contract"])
        record_id = resolver.judgement_id(contract_key, str(kw["step1"]))
        return [
            {
                "contract_id": resolver.contract_id(contract_key),
                "expected_stream_version": int(kw["expected_stream_version"]),
                "body": EventAppendIn(
                    events=[
                        EventAppendItemIn(
                            event_type=ContractEventType(event["event_type"]),
                            effective_date=event["effective_date"],
                            payload={**event["payload"], "judgement_record_id": str(record_id)},
                        )
                        for event in kw["events"]
                    ]
                ),
            }
        ]
    if handler == H["record_events"]:
        contract_key = str(kw["contract"])
        contract = next(item for item in key.contracts if item.external_id == contract_key)
        item = next(
            entry
            for entry in key.timeline
            if isinstance(entry, EventItem) and entry.seq == call.step.seq
        )
        if item.event_type in _LIFECYCLE_TYPES:
            raise NotProvisioned(
                f"seq {item.seq} {item.event_type}: API-R-30 forbids record_events; the estimate "
                "lifecycle route (FOLL-2: submit_version → decide) emits it (rule CONV-2)",
                handler,
            )
        if item.is_manual and (
            item.event_type in _EVIDENCE_TYPES
            or (
                item.event_type == "DELIVERY_RECORDED"
                and str(item.payload.get("trigger")) == "ACCEPTANCE"
            )
        ):
            raise NotProvisioned(
                f"seq {item.seq} {item.event_type}: {EVIDENCE_GAP} (rule FOLL-3, Q-11)",
                handler,
            )
        return [
            {
                "contract_id": resolver.contract_id(contract_key),
                "expected_stream_version": int(kw["expected_stream_version"]),
                "body": event_append(item, contract, resolver),
            }
        ]
    if handler == H["close_run"]:
        # AK-CLOSE-RUN-STEP-1: API-S-CloseRunCreate for the entity, book and period the plan names.
        return [
            {
                "body": CloseRunCreateIn(
                    entity_code=str(kw["entity"]),
                    book=BookCode(str(kw["book"])),  # CONV-1: the enum, never its string
                    period_key=str(kw["period_key"]),
                )
            }
        ]
    if handler == H["journal_create"] and call.step.phase == JOURNAL:
        # AK-JOURNAL-RUN-PLAN-1: API-S-JournalRunCreate for the block's entity, period, mode and
        # grain, in the key's primary book — the book the oracle's journals are of
        # (``platform_runner.journal_lines``). No cutoff: the command takes the clock of the step.
        primary = next(str(book) for book in key.books if str(book) != BookCode.LEGACY.value)
        return [
            {
                "body": JournalRunCreateIn(
                    entity_code=str(kw["entity"]),
                    book=BookCode(primary),  # CONV-1: the enums, never their strings
                    period_key=str(kw["period_key"]),
                    mode=JournalRunMode(str(kw["mode"])),
                    grain=JournalRunGrain(str(kw["grain"])),
                )
            }
        ]
    if handler == H["compute"]:
        return [{"group_id": resolver.group_id(str(kw["contract"]))}]
    where = f"{call.step.phase} {call.step.subject}"
    if handler == H["distinct_review"]:
        contract_key, obligation_key = str(kw["contract"]), str(kw["obligation_key"])
        distinctness = Distinctness(str(kw["distinctness"]))
        if distinctness is not Distinctness.DISTINCT:
            # DG-AK-41, the bound: the runner confirms a distinct conclusion and nothing else.
            # The review of a nondistinct obligation names the obligation it integrates into
            # (422 otherwise), and a key's line does not: refused by name, never guessed.
            raise NotProvisioned(
                f"{where} obligation {obligation_key!r}: {DISTINCT_BOUND}", handler
            )
        return [
            {
                "contract_id": resolver.contract_id(contract_key),
                "obligation_key": obligation_key,
                "body": DistinctReviewIn(distinctness=distinctness, rationale=DISTINCT_RATIONALE),
            }
        ]
    if handler in (H["judgement"], H["judgement_submit"]):
        contract_key, handle = str(kw["contract"]), str(kw["handle"])
        if handler == H["judgement_submit"]:
            return [
                {
                    "judgement_id": resolver.judgement_id(contract_key, handle),
                    "body": JudgementSubmitIn(),
                }
            ]
        contract = _contract(key, contract_key)
        judgement = next((j for j in contract.judgements or () if j.handle == handle), None)
        if judgement is None and handle == STEP1_HANDLE:
            if contract.has_commercial_substance is False:
                # DG-AK-41, the bound: the default statement is of a contract that is one.
                raise NotProvisioned(f"{where}: {STEP1_BOUND}", handler)
            judgement = step1_judgement()  # the runner's own record: the key states none
        named = constraint_of(handle)
        if judgement is None and named is not None:
            # The runner's own CONSTRAINT record of an estimate version: the key states none.
            # Its subject is the version, as the product's screen sends it — a record of a
            # contract would hold the active contract until its review (REQ-POL-010).
            element, number = named
            return [
                {
                    "body": judgement_request(
                        constraint_judgement(element, number),
                        resolver.contract_id(contract_key),
                        resolver.estimate_version_id(contract_key, element, number),
                        subject_type="estimate_version",
                    )
                }
            ]
        if judgement is None:
            raise NotProvisioned(f"{where}: judgement {handle!r} not in the key", handler)
        if judgement.rationale is None:  # FOLL-3 / Q-11: the optional member is absent
            raise NotProvisioned(
                f"{where} judgement {handle!r}: {SCHEMA_GAPS[handler]} (rule FOLL-3, Q-11)",
                handler,
            )
        contract_id = resolver.contract_id(contract_key)
        subject_id = (
            resolver.obligation_id(contract_key, judgement.subject_obligation_key)
            if judgement.subject_obligation_key
            else contract_id
        )
        return [
            {
                "body": judgement_request(
                    judgement,
                    contract_id,
                    subject_id,
                    commercial_substance=contract.has_commercial_substance is not False,
                )
            }
        ]
    if handler in (
        H["estimate"],
        H["estimate_version"],
        H["estimate_version_update"],
        H["estimate_submit"],
    ):
        contract_key, element = str(kw["contract"]), str(kw["element_code"])
        contract = _contract(key, contract_key)
        estimate = next((e for e in contract.estimates or () if e.element_code == element), None)
        if estimate is None:
            raise NotProvisioned(f"{where}: estimate {element!r} not in the key", handler)
        if handler == H["estimate"]:
            return [
                {
                    "contract_id": resolver.contract_id(contract_key),
                    "body": estimate_request(estimate),
                }
            ]
        version_no = int(kw["version_no"])
        version = next((v for v in estimate.versions if v.version_no == version_no), None)
        if version is None:
            raise NotProvisioned(
                f"{where}: estimate {element!r} has no version {version_no}", handler
            )
        if handler == H["estimate_version"]:
            # 04 §16.14 rev 1.241: a variable-consideration version names the CONSTRAINT
            # record of its element (PRD ERR-94) — at its creation when the key states the
            # record, which was reviewed after the booking.
            record = kw.get("constraint_handle")
            return [
                {
                    "estimate_id": resolver.estimate_id(contract_key, element),
                    "body": estimate_version_request(
                        version,
                        judgement_record_id=None
                        if record is None
                        else resolver.judgement_id(contract_key, str(record)),
                    ),
                }
            ]
        version_id = resolver.estimate_version_id(contract_key, element, version_no)
        if handler == H["estimate_version_update"]:
            # The runner's own record was prepared on the version: the DRAFT now names it.
            record = kw.get("constraint_handle")
            if record is None:
                raise NotProvisioned(f"{where}: the step names no CONSTRAINT record", handler)
            body = EstimateVersionUpdateIn(
                judgement_record_id=resolver.judgement_id(contract_key, str(record))
            )
            return [{"version_id": version_id, "body": body}]
        return [{"version_id": version_id, "body": EstimateVersionSubmitIn()}]
    if handler in (
        H["rule_set"],
        H["rule_set_version"],
        H["rule"],
        H["rule_case"],
        H["rule_tests"],
        H["rule_set_submit"],
        H["rule_set_publish"],
    ):
        code = str(kw["code"])
        rule_set = next((r for r in world.rule_sets if r.code == code), None)
        if rule_set is None:
            raise NotProvisioned(f"{where}: rule_set {code!r} not in the key", handler)
        if handler == H["rule_set"]:
            return [
                {
                    "code": code,
                    "kind": RuleSetKind(rule_set.kind),  # CONV-1: the enum, never its string
                    "name": None,
                    "description": None,
                }
            ]
        if handler == H["rule_set_version"]:
            return [
                {
                    "rule_set_id": resolver.rule_set_id(code),
                    "effective_from": None,
                    "source_version_id": None,
                }
            ]
        version_id = resolver.rule_set_version_id(code)
        if handler == H["rule"]:
            index = int(kw["rule_index"])
            if not 0 <= index < len(rule_set.rules):
                raise NotProvisioned(f"{where}: rule_set {code!r} has no rule {index}", handler)
            return [{"version_id": version_id, **rule_kwargs(rule_set.rules[index])}]
        cases = rule_set.example_cases or ()
        if handler == H["rule_case"]:
            index = int(kw["case_index"])
            if not 0 <= index < len(cases):
                raise NotProvisioned(f"{where}: rule_set {code!r} has no case {index}", handler)
            return [example_case_kwargs(cases[index], version_id)]
        if handler == H["rule_tests"]:
            return [{"version_id": version_id}]
        if handler == H["rule_set_submit"]:
            if not cases:  # FOLL-3 / Q-11: TESTED needs the optional example cases
                raise NotProvisioned(
                    f"{where} rule_set {code!r}: {SCHEMA_GAPS[handler]} (rule FOLL-3, Q-11)",
                    handler,
                )
            return [{"version_id": version_id, "comment": None}]
        return [{"version_id": version_id}]
    if handler in (H["fx_set"], H["fx_version"], H["fx_submit"]):
        code = str(kw["code"])
        rate_set = next((r for r in world.fx_rate_sets if r.code == code), None)
        if rate_set is None:
            raise NotProvisioned(f"{where}: fx_rate_set {code!r} not in the key", handler)
        if handler == H["fx_set"]:
            if rate_set.name is None:  # FOLL-3 / Q-11: the optional member is absent
                raise NotProvisioned(
                    f"{where} fx_rate_set {code!r}: {SCHEMA_GAPS[handler]} (rule FOLL-3, Q-11)",
                    handler,
                )
            return [{"body": fx_rate_set_request(rate_set)}]
        if handler == H["fx_version"]:
            return [{"set_id": resolver.fx_set_id(code), "body": fx_version_request(rate_set)}]
        return [
            {
                "version_id": resolver.fx_version_id(code),
                "body": FxRateSetVersionCommandIn(),
                "check_version": _ignore_version,
            }
        ]
    raise NotProvisioned(f"{where}: no request-model conversion", handler)


def _contract(key: AnswerKey, external_id: str) -> Contract:
    found = next((item for item in key.contracts if item.external_id == external_id), None)
    if found is None:
        raise NotProvisioned(f"contract {external_id!r} not in the key")
    return found


# --- record §18: the contract-scoped and remaining world families ---------------------------------


def judgement_request(
    judgement: Judgement,
    contract_id: UUID,
    subject_id: UUID,
    rationale: str | None = None,
    *,
    commercial_substance: bool = True,
    subject_type: str | None = None,
) -> JudgementCreateIn:
    """``JudgementCreateIn`` from a §9.5.4 judgement: the subject is the named obligation, else
    the contract — or of the type ``subject_type`` names, for a record of the runner's own;
    ``book`` is the enum of ``book_code``; ``rationale`` is the key's optional member
    (dev-guide rev 1.26) or the value a test supplies; neither → refused by name (FOLL-3, Q-11).
    A record that serves Step 1 — topic COLLECTIBILITY or NOT_A_CONTRACT — is sent for review
    with the five criteria of 606-10-25-1 (04 T-CON-19 rev 1.150; supervisor rulings R-113 (f),
    R-115 (f)). The keys state none, so the request supplies what the key's facts imply: (a) to
    (c) Yes — the key's contract is one —, (d) the contract's ``has_commercial_substance``
    (``commercial_substance``), (e) by the topic."""
    text = rationale if rationale is not None else judgement.rationale
    if text is None:
        raise NotProvisioned(
            f"judgement {judgement.handle!r}: {SCHEMA_GAPS[H['judgement']]} (rule FOLL-3, Q-11)",
            H["judgement"],
        )
    return JudgementCreateIn(
        topic=JudgementTopic(judgement.topic),
        subject_type=subject_type
        or ("obligation" if judgement.subject_obligation_key else "contract"),
        subject_id=subject_id,
        contract_id=contract_id,
        book=None if judgement.book_code is None else BookCode(judgement.book_code),
        conclusion=judgement.conclusion,
        rationale=text,
        questionnaire=_step1_answers(judgement, commercial_substance=commercial_substance),
    )


STEP1_TOPICS: Final = frozenset({"COLLECTIBILITY", "NOT_A_CONTRACT"})


def _step1_answers(judgement: Judgement, *, commercial_substance: bool) -> dict[str, Any] | None:
    """The key's questionnaire, with ``criteria`` for a Step 1 topic that states none."""
    stated = None if judgement.questionnaire is None else dict(judgement.questionnaire)
    if judgement.topic not in STEP1_TOPICS or "criteria" in (stated or {}):
        return stated
    criteria = {
        "a": "YES",
        "b": "YES",
        "c": "YES",
        "d": "YES" if commercial_substance else "NO",
        "e": "YES" if judgement.topic == "COLLECTIBILITY" else "NO",
    }
    return {**(stated or {}), "criteria": criteria}


def example_case_kwargs(case: RuleExampleCase, version_id: UUID) -> dict[str, Any]:
    """``commands.create_config_test_case`` keywords for a rev 1.26 example case of a rule-set
    version: subject ``rule_set_version``, the case's ``input`` as the facts."""
    facts, expected = case.input, case.expected_output
    if not isinstance(facts, Mapping) or not isinstance(expected, Mapping):
        raise NotProvisioned(
            f"example case {case.name!r}: input and expected_output are mappings (T-REF-27)",
            H["rule_case"],
        )
    return {
        "subject_type": "rule_set_version",
        "subject_id": version_id,
        "name": case.name,
        "facts": dict(facts),
        "expected_output": dict(expected),
    }


def estimate_request(estimate: Estimate) -> EstimateCreateIn:
    """``EstimateCreateIn`` from a §9.5.4 estimate element; ``allocation_target`` keeps the API's
    default (``CONTRACT``) when the key does not name it."""
    body: dict[str, Any] = {
        "estimate_kind": estimate.estimate_kind,
        "element_code": estimate.element_code,
        "obligation_key": estimate.obligation_key,
        "vc_element_type": estimate.vc_element_type,
        "direction": estimate.direction,
        "method": estimate.method,
        "target_obligation_keys": list(estimate.target_obligation_keys or ()),
        "allocation_criteria_evidence": estimate.allocation_criteria_evidence,
    }
    if estimate.allocation_target is not None:
        body["allocation_target"] = estimate.allocation_target
    return EstimateCreateIn.model_validate(body)


def estimate_version_request(
    version: EstimateVersion, *, judgement_record_id: UUID | None = None
) -> EstimateVersionCreateIn:
    """``EstimateVersionCreateIn`` from a §9.5.4 estimate version: the key's amounts as decimal
    strings, scenarios and parameters as given; ``method`` is not sent (locked to the element's,
    IMP-71); ``currency`` None defaults to the contract's. ``judgement_record_id`` is the
    CONSTRAINT record a variable-consideration version names (04 §16.14 rev 1.241) — the
    runner's workflow, not a member of the key."""
    return EstimateVersionCreateIn(
        effective_date=date.fromisoformat(version.effective_date),
        scenarios=[
            ScenarioIn(outcome=item.outcome, amount=item.amount, probability=item.probability)
            for item in version.scenarios or ()
        ],
        parameters=dict(version.parameters or {}),
        unconstrained_amount=version.unconstrained_amount,
        most_conservative_amount=version.most_conservative_amount,
        constrained_amount=version.constrained_amount,
        rate=version.rate,
        expected_total_amount=version.expected_total_amount,
        expected_quantity=version.expected_quantity,
        amortization_months=version.amortization_months,
        currency=version.currency,
        rationale=version.rationale,
        judgement_record_id=judgement_record_id,
    )


def rule_kwargs(rule: Rule) -> dict[str, Any]:
    """``commands.upsert_rule`` keywords (without ``version_id``) from a §9.5.3 rule; conditions
    must be a sequence of mappings and outputs a mapping (T-REF-26), else refused by name."""
    conditions, outputs = rule.conditions, rule.outputs
    if not isinstance(conditions, list | tuple) or not all(
        isinstance(item, Mapping) for item in conditions
    ):
        raise NotProvisioned(
            f"rule {rule.rule_key!r}: conditions are not a sequence of mappings (T-REF-26)",
            H["rule"],
        )
    if not isinstance(outputs, Mapping):
        raise NotProvisioned(
            f"rule {rule.rule_key!r}: outputs are not a mapping (T-REF-26)", H["rule"]
        )
    return {
        "rule_key": rule.rule_key,
        "priority": int(rule.priority),
        "conditions": [dict(item) for item in conditions],
        "outputs": dict(outputs),
        "description": None,
    }


def fx_rate_set_request(rate_set: FxRateSet, name: str | None = None) -> FxRateSetIn:
    """``FxRateSetIn`` from a §9.5.3 FX rate set; ``source`` keeps the API default ``MANUAL``.
    ``name`` is the key's optional member (dev-guide rev 1.26) or the value a test supplies;
    neither → refused by name (FOLL-3, Q-11)."""
    label = name if name is not None else rate_set.name
    if label is None:
        raise NotProvisioned(
            f"fx_rate_set {rate_set.code!r}: {SCHEMA_GAPS[H['fx_set']]} (rule FOLL-3, Q-11)",
            H["fx_set"],
        )
    return FxRateSetIn(code=rate_set.code, name=label, rate_type=rate_set.rate_type)


def fx_version_request(rate_set: FxRateSet) -> FxRateSetVersionIn:
    """``FxRateSetVersionIn`` from the set's rates; coverage is the span of their effective dates
    (rule FOLL-4)."""
    dates = [date.fromisoformat(rate.effective_date) for rate in rate_set.rates]
    if not dates:
        raise NotProvisioned(
            f"fx_rate_set {rate_set.code!r}: no rates, no coverage (rule FOLL-4)", H["fx_version"]
        )
    return FxRateSetVersionIn(
        coverage_from=min(dates),
        coverage_to=max(dates),
        rates=[
            FxRateIn(
                base_currency=rate.base_currency,
                quote_currency=rate.quote_currency,
                rate=rate.rate,
                effective_date=date.fromisoformat(rate.effective_date),
                period_key=rate.period_key,
            )
            for rate in rate_set.rates
        ],
    )


def _first_period_key(world: World) -> str:
    entity = world.entities[0]
    return _period_keys(world, entity)[0]


def _period_keys(world: World, entity: Entity) -> list[str]:
    """``FY<year>-P<nn>`` for every month of ``world.periods`` under a MONTHLY calendar starting
    in January; other calendars are the database resolver's (they need the generated periods)."""
    if entity.calendar.pattern != "MONTHLY" or entity.calendar.fiscal_year_start_month != 1:
        raise NotProvisioned(
            f"period keys of {entity.code}: calendar {entity.calendar.pattern} starting month "
            f"{entity.calendar.fiscal_year_start_month} needs the generated periods"
        )
    start_year, start_month = (int(part) for part in world.periods.from_.split("-"))
    end_year, end_month = (int(part) for part in world.periods.to.split("-"))
    keys: list[str] = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        keys.append(f"FY{year}-P{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return keys


def bind_check(call: Call, kwargs_list: Sequence[Mapping[str, Any]]) -> None:
    """Every keyword set binds to the handler's real signature (``uow`` first, the provisioning
    request for ``provision_tenant``, or the invoker's password, facts and runtime beside the
    token for ``accept_invitation``); raises ``TypeError`` when it does not."""
    handler = handler_of(call.handler)
    signature = inspect.signature(handler)
    hints = {name: parameter.annotation for name, parameter in signature.parameters.items()}
    for kwargs in kwargs_list:
        if call.handler == H["provision"]:
            signature.bind(kwargs["request"], actor=None, clock=None, keyring=None)
        elif call.handler == H["accept"]:
            signature.bind(
                **kwargs,
                password=None,
                facts=None,
                keyring=None,
                clock=None,
                files=None,
                previous_token=None,
            )
        else:
            signature.bind(None, **kwargs)
        _check_enums(hints, kwargs)


def _enum_types(annotation: Any) -> tuple[list[type[Enum]], bool]:
    """The ``Enum`` classes an annotation names (a type, or the string form the handlers keep under
    ``from __future__ import annotations``, resolved against ``erev_api.enums``), and whether
    None is allowed."""
    if isinstance(annotation, str):
        names = [
            part.strip() for part in annotation.replace("Optional[", "").replace("]", "").split("|")
        ]
        optional = "None" in names
        found = [
            candidate
            for candidate in (getattr(erev_enums, name, None) for name in names if name != "None")
            if inspect.isclass(candidate) and issubclass(candidate, Enum)
        ]
        return found, optional
    parts = _unwrap(annotation)
    found = [
        candidate
        for candidate in parts
        if inspect.isclass(candidate) and issubclass(candidate, Enum)
    ]
    return found, type(None) in parts


def _check_enums(hints: Mapping[str, Any], kwargs: Mapping[str, Any]) -> None:
    """CONV-1: a parameter annotated with an ``Enum`` type receives an instance of it (None only
    where the annotation allows None); a matching string never passes."""
    for name, value in kwargs.items():
        annotation = hints.get(name)
        if annotation is None or annotation is inspect.Parameter.empty:
            continue
        enums, optional = _enum_types(annotation)
        if not enums:
            continue
        if value is None and optional:
            continue
        if not any(isinstance(value, enum) for enum in enums):
            names = " | ".join(enum.__name__ for enum in enums)
            raise TypeError(f"{name}: expected {names}, got {type(value).__name__} {value!r}")
