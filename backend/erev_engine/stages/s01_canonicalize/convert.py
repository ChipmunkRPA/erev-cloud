"""Stage 01 conversion: decimals, literals, bundle order, subject keys and contract terms.

ENGINE_SPEC §1.5 S01-R-11 converts payload decimals to ``Fraction`` once and refuses a decimal in
exponent form or a non-finite decimal anywhere in the bundle (DG-KRN-MONEY-05); literals are checked
against ``erev_engine.enums``. The §0.4 tuple order is asserted (CV-45). Subject keys follow CV-21,
and contract terms come from the booking payload (S01-R-20). Private to stage 01; stage packages use
the names re-exported by ``s01_canonicalize``. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Final

from erev_engine import guards
from erev_engine.bundle import ContractInput, EventInput, InputBundle, SspEntryInput
from erev_engine.enums import (
    AccountRole,
    BookCode,
    ComputationTrigger,
    ContractEventType,
    Distinctness,
    JudgementTopic,
    LicenceNature,
    ObligationKind,
    PeriodState,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    RuleSetKind,
    SatisfactionPattern,
    ScopeFlag,
    SspMethod,
    SspQuantityUnit,
    SspValueBasis,
    WarrantyType,
)
from erev_engine.money import to_fraction
from erev_engine.stages.state import EventView
from erev_engine.trace import SourceRef

__all__ = [
    "BOOK_ORDER",
    "TERM_EVENT_TYPES",
    "assert_bundle_order",
    "canonical_header",
    "check_decimals",
    "check_literals",
    "check_selected_quantity_unit",
    "check_series_quantity_units",
    "contract_entity_subject_key",
    "contract_subject_key",
    "convert_payload",
    "encode_key",
    "event_view",
    "group_entity_subject_key",
    "member_in_force",
    "obligation_subject_key",
    "payload_bool",
    "payload_date",
    "payload_fraction",
    "payload_text",
]

# CV-21: characters percent-encoded inside every subject-key component.
# RCP-11 book order, which is the E-02 order.
BOOK_ORDER: Final = MappingProxyType({code.value: index for index, code in enumerate(BookCode)})
TENANT_PRESETS: Final = frozenset({"DEFAULT", "LEGACY_PARITY"})
# S01-R-20: the events whose payload carries contract terms.
TERM_EVENT_TYPES: Final = frozenset({"CONTRACT_BOOKED", "CONTRACT_AMENDED"})


def _values(enum: Iterable[Any]) -> frozenset[str]:
    return frozenset(str(member.value) for member in enum)


_TRIGGERS: Final = _values(ComputationTrigger) | {"DRY_RUN"}


# --- Subject keys (CV-21) ------------------------------------------------------------------------


# The percent-escapes of a subject-key component, in application order (``%`` first): the ONE
# CV-21 table every index, ledger, pin and node-id lookup keys on (D-98 candidate 76;
# ENG-COST-ENC-1) — stage 14 ``encode_component`` and ``EstimatePins.of_contract`` resolve here.
KEY_ESCAPES: Final = (("%", "%25"), ("/", "%2F"), ("@", "%40"), ("#", "%23"), (":", "%3A"))


def encode_key(component: str) -> str:
    """A subject-key component with ``%``, ``/``, ``@``, ``#`` and ``:`` percent-encoded (CV-21)."""
    if not isinstance(component, str) or not component:
        raise ValueError("a subject-key component is a non-empty string (CV-21)")
    for character, escape in KEY_ESCAPES:
        component = component.replace(character, escape)
    return component


def contract_key_from_subject(subject: str) -> str:
    """Recover the raw contract id from a CV-21 contract/member/obligation subject.

    Structural separators are removed before decoding, and percent is decoded last so
    literal escape-like characters in the identifier are not decoded twice.
    """
    component = subject.split("/", 1)[0].split("@", 1)[0].split("#", 1)[0]
    if not component:
        raise ValueError("a contract subject must have a non-empty contract component")
    for character, escape in reversed(KEY_ESCAPES):
        component = component.replace(escape, character)
    return component


def contract_subject_key(contract_key: str) -> str:
    """The subject key of a contract: its encoded external id."""
    return encode_key(contract_key)


def obligation_subject_key(contract_key: str, obligation_key: str) -> str:
    """``<contract external_id>/<obligation_key>``, each component encoded (CV-21)."""
    return f"{encode_key(contract_key)}/{encode_key(obligation_key)}"


def judgement_names_subject(
    subject_key: str, contract_key: str, obligation_keys: Iterable[str] = ()
) -> bool:
    """A T-CON-19 record's subject is the contract, or one of the element's obligations (D-93
    (3); Table 0.4-A ``CONSTRAINT`` / ``OTHER``: the record may sit on the contract or on the
    element's obligation), in the raw or the CV-21 encoded form."""
    subjects = {contract_key, contract_subject_key(contract_key)}
    for obligation_key in obligation_keys:
        subjects.add(f"{contract_key}/{obligation_key}")
        subjects.add(obligation_subject_key(contract_key, obligation_key))
    return subject_key in subjects


def judgement_names_element(outcome_key: object, estimate_key: str, element_code: str) -> bool:
    """A T-CON-19 outcome ``estimate_key`` names the element: the §0.4 qualified key
    ``<contract external_id>/<element_code>`` (CV-21 encoded, as the engine carries it) or the raw
    T-CON-12 element code (D-93 (3); dev-guide §9.5.4). The raw code is compared with the element's
    own ``element_code``, never with a component split off the encoded key: TY-06 admits ``/``,
    ``#`` and ``:`` in a code, which the qualified key encodes (Codex C1B-ENCODED-JUDGEMENT)."""
    if not isinstance(outcome_key, str):
        return False
    return outcome_key == estimate_key or outcome_key == element_code


def contract_entity_subject_key(contract_key: str, entity_code: str) -> str:
    """``<contract external_id>@<entity code>``, each component encoded (CV-21)."""
    return f"{encode_key(contract_key)}@{encode_key(entity_code)}"


def group_entity_subject_key(group_code: str, entity_code: str) -> str:
    """``<group code>@<entity code>``, each component encoded (CV-21; D-90d L9-RUN-Q-3)."""
    return f"{encode_key(group_code)}@{encode_key(entity_code)}"


# --- Decimals (S01-R-11; DG-KRN-MONEY-05) --------------------------------------------------------


def _exact(value: Decimal, path: str) -> Fraction:
    # A finite decimal converts exactly; a positive exponent only arises from exponent notation
    # ("1E+2") or normalisation, which bundle assembly never produces (DG-KRN-MONEY-05).
    if not value.is_finite():
        raise ValueError(f"{path} holds a non-finite decimal (S01-R-11)")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        raise ValueError(f"{path} holds a decimal in exponent form {value} (S01-R-11)")
    return to_fraction(value)


def check_decimals(bundle: InputBundle) -> None:
    """``ValueError`` when any ``Decimal`` of the bundle is non-finite or in exponent form."""
    pending: list[tuple[object, str]] = [(bundle, "$")]
    seen: set[int] = set()
    while pending:
        item, path = pending.pop()
        if isinstance(item, Decimal):
            _exact(item, path)
            continue
        if item is None or isinstance(item, str | bytes | int | Fraction | date):
            continue
        if id(item) in seen:
            continue
        seen.add(id(item))
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            pending.extend(
                (getattr(item, field.name), f"{path}.{field.name}")
                for field in dataclasses.fields(item)
            )
        elif isinstance(item, Mapping):
            pending.extend((member, f"{path}[{key!r}]") for key, member in item.items())
        elif isinstance(item, list | tuple | set | frozenset):
            pending.extend((member, f"{path}[{index}]") for index, member in enumerate(item))


def convert_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    """A read-only copy of ``payload`` with every ``Decimal`` as ``Fraction`` (CV-30)."""
    converted = _convert(payload, "payload")
    if not isinstance(converted, Mapping):
        raise TypeError("an event payload is an object")
    return converted


def _convert(value: object, path: str) -> object:
    if isinstance(value, Decimal):
        return _exact(value, path)
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _convert(member, f"{path}[{key!r}]") for key, member in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_convert(member, f"{path}[{index}]") for index, member in enumerate(value))
    return value


def event_view(event: EventInput, stream_heads: Mapping[str, int]) -> EventView:
    """The stage view of an included event (§0.11): payload decimals as ``Fraction``."""
    return EventView(
        event_key=event.event_key,
        contract_key=event.contract_key,
        event_type=event.event_type,
        effective_date=event.effective_date,
        record_seq=event.record_seq,
        recorded_at=event.recorded_at,
        obligation_subject_keys=tuple(
            obligation_subject_key(event.contract_key, key) for key in event.obligation_keys
        ),
        payload=convert_payload(event.payload),
        is_new=event.stream_version > stream_heads.get(event.contract_key, 0),
        source=SourceRef("contract_event", event.event_key),
    )


# --- Literals (S01-R-11; CV-45) ------------------------------------------------------------------


def _require(value: object, allowed: frozenset[str], name: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} holds an unknown literal {value!r} (S01-R-11)")


def _require_optional(value: object, allowed: frozenset[str], name: str) -> None:
    if value is not None:
        _require(value, allowed, name)


def check_literals(bundle: InputBundle) -> None:
    """``ValueError`` naming the first literal absent from its ``erev_engine.enums`` class."""
    books, states = _values(BookCode), _values(PeriodState)
    _require(bundle.trigger, _TRIGGERS, "trigger")
    _require(bundle.tenant_preset, TENANT_PRESETS, "tenant_preset")
    for book in bundle.books:
        _require(book.book_code, books, "books.book_code")
    for entity in bundle.entities:
        for period in entity.periods:
            for book_code, state in period.states:
                _require(book_code, books, f"period {period.period_key} book")
                _require(state, states, f"period {period.period_key} state")
    for product in bundle.group.products:
        _require(product.principal_agent, _values(PrincipalAgent), f"product {product.code}")
        _require(product.distinctness_default, _values(Distinctness), f"product {product.code}")
    for contract in bundle.contracts:
        for judgement in contract.judgements:
            _require(judgement.topic, _values(JudgementTopic), judgement.judgement_key)
            _require_optional(judgement.book_code, books, judgement.judgement_key)
    for event in bundle.events:
        _require(event.event_type, _values(ContractEventType), event.event_key)
        lines = event.payload.get("lines") if event.event_type in TERM_EVENT_TYPES else None
        for line in lines if isinstance(lines, list | tuple) else ():
            if isinstance(line, Mapping):
                _require_optional(line.get("scope_flag"), _values(ScopeFlag), event.event_key)
    _check_reference_literals(bundle)
    for amount in bundle.posted:
        _require(amount.account_role, _values(AccountRole), "posted.account_role")


def _check_reference_literals(bundle: InputBundle) -> None:
    for template in bundle.pob_template_versions:
        name = template.version_key
        _require(template.obligation_kind, _values(ObligationKind), name)
        _require(template.distinctness, _values(Distinctness), name)
        _require(template.satisfaction_pattern, _values(SatisfactionPattern), name)
        _require(template.recognition_method, _values(RecognitionMethod), name)
        _require_optional(template.ratable_convention, _values(RatableConvention), name)
        _require(template.principal_agent, _values(PrincipalAgent), name)
        _require(template.warranty_type, _values(WarrantyType), name)
        _require(template.licence_nature, _values(LicenceNature), name)
    for rule_set in bundle.rule_set_versions:
        _require(rule_set.kind, _values(RuleSetKind), rule_set.version_key)
    for version in bundle.ssp_versions:
        for entry in version.entries:
            _require(entry.method, _values(SspMethod), entry.entry_key)
            _require(entry.value_basis, _values(SspValueBasis), entry.entry_key)
            _require_optional(entry.quantity_unit, _values(SspQuantityUnit), entry.entry_key)
            _require(entry.distinctness, _values(Distinctness), entry.entry_key)


def check_series_quantity_units(bundle: InputBundle) -> None:
    """D-97 (3) (04 T-REF-30 E-125; ENGINE_SPEC S06-R-11 series row): a ``PER_INCREMENT`` SSP
    entry declares ``quantity_unit`` — ``ValueError`` (CV-45) when it is absent — no other basis
    carries one (the unit is meaningful for ``PER_INCREMENT`` only), and all dated entries of one
    product in one SSP book agree on it; the unit is never inferred from a quantity."""
    declared: dict[tuple[str, str], tuple[str, str]] = {}
    for version in bundle.ssp_versions:
        for entry in version.entries:
            _check_entry_quantity_unit(entry)
            if entry.quantity_unit is None:
                continue
            key = (version.ssp_book_code, entry.product_code)
            seen = declared.setdefault(key, (entry.quantity_unit, entry.entry_key))
            if seen[0] != entry.quantity_unit:
                raise ValueError(
                    f"{entry.entry_key}: quantity_unit {entry.quantity_unit} disagrees with "
                    f"{seen[1]} ({seen[0]}) for product {entry.product_code!r} in SSP book "
                    f"{version.ssp_book_code!r} (T-REF-30, D-97 (3); CV-45)"
                )


def _check_entry_quantity_unit(entry: SspEntryInput) -> None:
    per_increment = entry.value_basis == SspValueBasis.PER_INCREMENT
    if per_increment and entry.quantity_unit is None:
        raise ValueError(
            f"{entry.entry_key}: a PER_INCREMENT SSP entry declares quantity_unit "
            "(SERVICE_UNITS or INCREMENTS; T-REF-30, D-97 (3); CV-45)"
        )
    if not per_increment and entry.quantity_unit is not None:
        raise ValueError(
            f"{entry.entry_key}: quantity_unit {entry.quantity_unit} is meaningful for a "
            f"PER_INCREMENT entry only, not {entry.value_basis} (T-REF-30, D-97 (3); CV-45)"
        )


def check_selected_quantity_unit(bundle: InputBundle, book_code: str, entry: SspEntryInput) -> None:
    """D-97 (3) at selection: the selected dated entry carries its own declaration (never a later
    one) and every entry of its product in its SSP book agrees with it — ``ValueError`` (CV-45)
    otherwise, so a disagreement never reprices an obligation."""
    _check_entry_quantity_unit(entry)
    for version in bundle.ssp_versions:
        if version.ssp_book_code != book_code:
            continue
        for other in version.entries:
            if other.product_code != entry.product_code or other.quantity_unit is None:
                continue
            if entry.quantity_unit is not None and other.quantity_unit != entry.quantity_unit:
                raise ValueError(
                    f"{entry.entry_key}: the selected entry's quantity_unit {entry.quantity_unit} "
                    f"disagrees with {other.entry_key} ({other.quantity_unit}) in SSP book "
                    f"{book_code!r} (T-REF-30, D-97 (3); CV-45)"
                )


# --- Bundle order (ENGINE_SPEC §0.4; CV-45) ------------------------------------------------------


def _sorted[T](
    items: Sequence[T], key: Callable[[T], Any], name: str, *, unique: bool = True
) -> None:
    guards.assert_sorted(items, key=key, name=name, unique=unique)


def _itself(value: str) -> str:
    return value


def _pair(value: tuple[str, str]) -> tuple[str, str]:
    return value


def assert_bundle_order(bundle: InputBundle) -> None:
    """``ValueError`` when a bundle tuple departs from its §0.4 natural-key order (CV-45)."""
    _sorted(bundle.books, lambda book: BOOK_ORDER[book.book_code], "books")
    for book in bundle.books:
        _sorted(book.entity_codes, _itself, f"{book.book_code} entity_codes")
        _sorted(book.policies, lambda p: (p.code, p.scope, p.subject_key), "policies")
        _sorted(
            book.account_mapping.rules,
            lambda r: (
                r.account_role,
                r.clearing_purpose or "",
                -r.specificity,
                -r.priority,
                r.account_code,
            ),
            "account_mapping.rules",
            unique=False,
        )
    _sorted(bundle.entities, lambda entity: entity.code, "entities")
    for entity in bundle.entities:
        _sorted(entity.periods, lambda period: period.start_date, f"{entity.code} periods")
        for period in entity.periods:
            _sorted(period.states, lambda state: state[0], f"{period.period_key} states")
    _assert_group_order(bundle)
    _sorted(bundle.contracts, lambda contract: contract.external_id, "contracts")
    if tuple(c.external_id for c in bundle.contracts) != bundle.group.member_contract_keys:
        raise ValueError("contracts must be exactly the group's member contracts (CV-10)")
    for contract in bundle.contracts:
        name = contract.external_id
        _sorted(contract.judgements, lambda j: j.judgement_key, f"{name} judgements")
        _sorted(contract.material_rights, lambda m: m.obligation_key, f"{name} material_rights")
        _sorted(contract.modifications, lambda m: m.modification_key, f"{name} modifications")
        _sorted(contract.payment_schedule, lambda point: point.date, f"{name} payment_schedule")
    _sorted(bundle.events, lambda e: (e.effective_date, e.record_seq, e.event_key), "events")
    _assert_reference_order(bundle)
    _sorted(bundle.estimate_versions, lambda v: (v.estimate_key, v.version_no), "estimates")
    _sorted(
        bundle.fx_rates,
        lambda r: (r.rate_type, r.base_currency, r.quote_currency, r.effective_date, r.version_key),
        "fx_rates",
    )
    _sorted(
        bundle.posted,
        lambda p: (
            p.book_code,
            p.entity_code,
            p.subject_key,
            p.entry_kind,
            p.account_role,
            p.clearing_purpose or "",
            p.period_key,
            p.origin_period_key or "",
            p.posting_class,
        ),
        "posted",
        unique=False,
    )
    for amount in bundle.posted:
        # S14-R-28: the distinct rate references of the summed lines, in (rate key, version key)
        # order (05 RCP-05).
        _sorted(amount.rate_refs, _pair, "posted rate_refs")


def _assert_group_order(bundle: InputBundle) -> None:
    group = bundle.group
    _sorted(group.member_contract_keys, _itself, "member_contract_keys")
    _sorted(group.previous_stream_heads, lambda head: head[0], "previous_stream_heads")
    _sorted(group.products, lambda product: product.code, "products")
    for product in group.products:
        _sorted(
            product.components,
            lambda c: (c.sequence, c.component_product_code),
            f"{product.code} components",
        )
    _sorted(group.portfolios, lambda portfolio: portfolio.code, "portfolios")
    for portfolio in group.portfolios:
        _sorted(portfolio.member_contract_keys, _itself, f"{portfolio.code} members")


def _assert_reference_order(bundle: InputBundle) -> None:
    _sorted(bundle.ssp_versions, lambda v: (v.ssp_book_code, v.version_no), "ssp_versions")
    for version in bundle.ssp_versions:
        _sorted(
            version.entries,
            lambda e: (
                e.product_code,
                e.stratification,
                e.region or "",
                e.channel or "",
                e.segment or "",
                e.deal_size_band or "",
                e.term_band or "",
                e.currency,
            ),
            f"{version.version_key} entries",
        )
        for entry in version.entries:
            _sorted(
                entry.ranges,
                lambda r: (r.band_dimension, r.band_from is not None, r.band_from or Decimal(0)),
                f"{entry.entry_key} ranges",
            )
    _sorted(bundle.pob_template_versions, lambda t: (t.template_code, t.version_no), "templates")
    _sorted(bundle.rule_set_versions, lambda r: (r.rule_set_code, r.version_no), "rule_sets")
    for rule_set in bundle.rule_set_versions:
        _sorted(
            rule_set.rules,
            lambda rule: (-rule.specificity, -rule.priority, rule.rule_key),
            f"{rule_set.version_key} rules",
        )


# --- Payload readers -----------------------------------------------------------------------------


def payload_fraction(payload: Mapping[str, object], name: str) -> Fraction | None:
    """An exact payload number; ``None`` when absent. Strings must be plain decimals."""
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Fraction | int | str | Decimal):
        raise ValueError(f"payload member {name} is not a number")
    if isinstance(value, Decimal):
        return _exact(value, name)
    return to_fraction(value)


def payload_text(payload: Mapping[str, object], name: str) -> str | None:
    value = payload.get(name)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"payload member {name} is not a string")
    return value


def payload_bool(payload: Mapping[str, object], name: str) -> bool | None:
    """A payload boolean; the strings ``"true"`` and ``"false"`` are accepted."""
    value = payload.get(name)
    if value is None or isinstance(value, bool):
        return value
    if value in ("true", "false"):
        return value == "true"
    raise ValueError(f"payload member {name} is not a boolean")


def payload_date(payload: Mapping[str, object], name: str) -> date | None:
    """A payload date; an ISO ``YYYY-MM-DD`` string is accepted."""
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, datetime):
        raise ValueError(f"payload member {name} is a timestamp, not a date")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"payload member {name} is not a date")


# --- Contract terms (S01-R-20) -------------------------------------------------------------------


def canonical_header(header: ContractInput, booking: Mapping[str, object]) -> ContractInput:
    """The header with every term the booking payload carries taken from the payload (S01-R-20).

    The ``ContractInput`` projection serves only facts absent from the payload. The list members
    ``payment_schedule``, ``noncash_consideration`` and ``consideration_payable`` stay as projected;
    their value in force at a date is ``member_in_force`` over the payloads.
    """
    termination = booking.get("termination")
    party = header.termination_party
    has_penalty = header.termination_has_penalty
    notice_days = header.termination_notice_days
    if termination is not None:
        if not isinstance(termination, Mapping):
            raise ValueError("booking member termination is not an object")
        party = payload_text(termination, "party") if "party" in termination else party
        if "has_penalty" in termination:
            has_penalty = payload_bool(termination, "has_penalty")
        if "notice_days" in termination:
            notice = termination.get("notice_days")
            if notice is not None and (isinstance(notice, bool) or not isinstance(notice, int)):
                raise ValueError("booking member termination.notice_days is not an integer")
            notice_days = notice
    customer = booking.get("customer")
    customer_code = header.customer_code
    if isinstance(customer, Mapping) and customer.get("code") is not None:
        customer_code = _text(customer, "code", customer_code)
    return ContractInput(
        external_id=header.external_id,
        customer_code=customer_code,
        related_party_group=header.related_party_group,
        contracting_entity_code=_text(
            booking, "contracting_entity_code", header.contracting_entity_code
        ),
        transaction_currency=_text(booking, "transaction_currency", header.transaction_currency),
        inception_date=_day(booking, "inception_date", header.inception_date),
        signature_date=_optional(booking, "signature_date", header.signature_date, payload_date),
        document_ref=_optional(booking, "document_ref", header.document_ref, payload_text),
        termination_party=party,
        termination_has_penalty=has_penalty,
        termination_notice_days=notice_days,
        has_commercial_substance=_flag(
            booking, "has_commercial_substance", header.has_commercial_substance
        ),
        region=_optional(booking, "region", header.region, payload_text),
        channel=_optional(booking, "channel", header.channel, payload_text),
        contract_type=_optional(booking, "contract_type", header.contract_type, payload_text),
        renewal_of_contract_key=header.renewal_of_contract_key,
        judgements=header.judgements,
        material_rights=header.material_rights,
        modifications=header.modifications,
        noncash_consideration=header.noncash_consideration,
        consideration_payable=header.consideration_payable,
        payment_schedule=header.payment_schedule,
        scope_605_35=_flag(booking, "scope_605_35", header.scope_605_35),
    )


def _text(payload: Mapping[str, object], name: str, default: str) -> str:
    value = payload_text(payload, name)
    return default if value is None else value


def _day(payload: Mapping[str, object], name: str, default: date) -> date:
    value = payload_date(payload, name)
    return default if value is None else value


def _flag(payload: Mapping[str, object], name: str, default: bool) -> bool:
    value = payload_bool(payload, name)
    return default if value is None else value


def _optional[T](
    payload: Mapping[str, object],
    name: str,
    default: T | None,
    reader: Callable[[Mapping[str, object], str], T | None],
) -> T | None:
    return reader(payload, name) if name in payload else default


def member_in_force(
    events: Sequence[EventView], contract_key: str, member: str, at: date
) -> object | None:
    """The member of the latest ``CONTRACT_BOOKED`` or ``CONTRACT_AMENDED`` payload of the contract
    effective on or before ``at`` that carries it; ``None`` when none does (S01-R-20)."""
    found: object | None = None
    for event in events:
        if event.effective_date > at:
            break
        if (
            event.contract_key == contract_key
            and event.event_type in TERM_EVENT_TYPES
            and member in event.payload
        ):
            found = event.payload[member]
    return found
