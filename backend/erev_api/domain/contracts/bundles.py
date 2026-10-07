"""Engine input bundle assembly (05 §3.8 RCP-15, RCP-16; dev-guide §6.1 DG-CMD-04, §5.15
DG-KRN-REG-02, DG-KRN-REG-03; ENGINE_SPEC §0.4; BUILD_SPEC CTR-2).

``build`` loads, for one combination group, everything ``erev_engine.compute`` reads, in the
natural-key order stage 01 asserts (S01-R-02):

- the members at ``known_at`` (T-CON-04), their header projections and the events of every member
  stream with ``recorded_at <= known_at`` in ENG-06 order, plus the command's pending events after
  the heads. Payload handles are resolved to natural keys: money objects ``{amount, currency}``
  become their amount strings, ``obligation_ids`` become obligation keys, and the
  ``changes.ssp_book_version_id`` of ``LINE_ATTRIBUTES_CHANGED`` becomes the approved SSP version's
  key (``<book>@v<n>``; BUILD_SPEC CTR-15);
- the products the member lines name, with their components and default templates — from the
  pin of the group's latest SUCCEEDED computation when it records them, else from the product row
  (``ProductPins``; 04 T-CON-07 ``pinned_refs.products``; DG-KRN-REG-02 rev 1.93); the
  PUBLISHED and SUPERSEDED template versions; the APPROVED SSP book versions (CTL-011); the
  PUBLISHED account mapping version in force, with the rules of it that name no product and no
  entity or one the bundle holds (``_account_mapping``; 05 RCP-15 rev 1.168); the published FX
  rates between the group's currencies;
- the entities of the members and of their performing lines, each with the periods of its
  calendar from the group's inception period on and the period states per book; an earlier period
  is carried only when every book the entity keeps has a state for it, so a period before a kept
  book's first period (04 T-REF-03) is handed over only from the group's inception on (ENGINE_SPEC
  §0.4 ``EntityInput.periods``, CV-12, CV-13; 05 RCP-03, RCP-15);
- per book kept by one of those entities, every accounting parameter resolved through
  ``registry.resolve`` (DG-KRN-REG-03): pin K at the GROUP scope, reused from the previous version's
  ``pinned_policies`` when one exists (DG-KRN-REG-02) — for the first version of a group in a
  book, from the latest version of a member's former group (``former_pinned_policies``: the
  first computation after an approved combination keeps the pin of the member with the earliest
  inception date, then external id; item PIN-K-COMBINATION-1) — pin P per entity period, and the
  level P values of each line's product and template at the OBLIGATION scope, pinned with the
  product. Approved contract-pinned overrides are loaded at their own scope as of the
  cutoff, with obligation > contract > product precedence. Shadowed product defaults remain
  in PRODUCT-scope metadata for pinning; scoped pins are never promoted to GROUP.
  At the CONTRACT scope
  (level C), POL-210 ``onboarding.method`` of a contract a D-31 mode (a) migration opened
  (``onboarding_pins``; 05 RCP-15 rev 1.36);
- the stream heads of the group's previous SUCCEEDED computation.

- the posted cumulative amounts of the members' sealed subledger lines (RCP-05; CTR-3).

[J] L5-1-Q-27 (BUILD_SPEC DIN-6): T-CON-06 ``modification`` is CTR-17 (post-rc, R-RC-1), so a
member's ``modifications`` are projected from its ``CONTRACT_AMENDED`` events whose treatments are
one legacy template (S01-R-09): the key is the payload ``modification_id``, ``template_mode`` the
E-24 mode of the treatment, ``kind`` ``VC_CHANGE`` for ``pob_price_change``, else
``ADD_OBLIGATION`` when a line adds and ``QUANTITY_CHANGE`` otherwise, status ``APPLIED``,
``lines`` and ``chosen_treatments`` the payload's, and ``ssp_basis`` the payload's with version ids
as version keys. Other amendments project nothing.

``index`` maps the natural keys of a built bundle back to row ids for ``computation.persist``, and
``pinned_refs`` gives the T-CON-07 member. [J] L3-1-Q-21: rule sets are not loaded yet (their loader
arrives with a later item), so that tuple is empty; RCP-16 batch loading is left to the compute
job. Since CTR-12 the bundle carries the estimate versions named by the included and pending
``ESTIMATE_CHANGED`` events of member contracts (T-CON-12, T-CON-13; ENGINE_SPEC §0.4, S01-R-18),
and each such event names its version key. Since CLO-12 the payload of an included or pending
``MANUAL_ADJUSTMENT_APPLIED`` carries its approved T-SL-05 adjustment in natural keys
(``adjustment_payloads``; decision L1-3-Q-14; ENGINE_SPEC_B S09-R-38 to R-41, S14-R-09a): the
stored payload holds ``manual_adjustment_id`` alone (04 §16.3) and the bundle has no adjustment
rows.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    BundleComponentInput,
    ContractInput,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    FxRateInput,
    GroupInput,
    InputBundle,
    JudgementInput,
    MappingRuleInput,
    ModificationInput,
    NoncashInput,
    OutputBundle,
    PayableInput,
    PaymentPointInput,
    PeriodInput,
    PostedAmountInput,
    ProductInput,
    ResolvedPolicyInput,
)
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.money import decimal_to_minor
from erev_engine.stages.s01_canonicalize import (
    contract_subject_key,
    group_entity_subject_key,
    obligation_subject_key,
)
from erev_engine.trace import SourceRef
from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    account_mapping_version,
    book,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    customer,
    entity_book,
    estimate,
    estimate_version,
    fiscal_calendar,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    judgement_record,
    legal_entity,
    manual_adjustment,
    modification,
    obligation,
    obligation_version,
    period,
    period_state,
    pob_template,
    pob_template_version,
    product,
    registry_version,
    related_party_group,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.contracts import policy_inputs, repo
from erev_api.domain.journals.subledger import POSTING_CLASSES
from erev_api.domain.policies import templates
from erev_api.domain.policies.templates import CONVENTION_POLICY, engine_policy_value
from erev_api.domain.reference import mapping
from erev_api.domain.reference import products as product_rules
from erev_api.domain.ssp import resolution
from erev_api.enums import (
    BookCode,
    ComputationStatus,
    ComputationTrigger,
    ConfigStatus,
    ContractEventType,
    JudgementStatus,
    SubledgerEntryKind,
)
from erev_api.events.payloads import LATEST_SCHEMA_VERSION, payload_json
from erev_api.events.stream import EventIn
from erev_api.periods import POSTABLE_STATES
from erev_api.registry import resolve as registry
from erev_api.registry.policies import POLICY_PARAMETERS

__all__ = [
    "PRODUCT_PINS",
    "BundleIndex",
    "ProductPins",
    "build",
    "entity_codes",
    "estimate_version_input",
    "former_groups",
    "former_pinned_policies",
    "index",
    "onboarding_pins",
    "pinned_refs",
    "posted_subject",
    "product_pins",
]

FORMAT_VERSION: Final = 1
BOOK_ORDER: Final = (BookCode.ASC606.value, BookCode.IFRS15.value, BookCode.LEGACY.value)
LEGACY_BOOK: Final = BookCode.LEGACY.value
# The states a line posts into (04 DB-07; ``erev_api.periods.POSTABLE_STATES``).
POSTABLE: Final = frozenset(state.value for state in POSTABLE_STATES)
TERM_EVENTS: Final = frozenset({"CONTRACT_BOOKED", "CONTRACT_AMENDED"})
NO_MAPPING_KEY: Final = "NO-MAPPING@v0"
ATTRIBUTES_EVENT: Final = "LINE_ATTRIBUTES_CHANGED"
ZERO_SHA256: Final = "0" * 64
_IN_FORCE: Final = (ConfigStatus.PUBLISHED.value, ConfigStatus.SUPERSEDED.value)
# the T-PLT-32 levels whose resolved rows carry a registry version id as their source reference
_VERSION_LEVELS: Final = frozenset(level for _, level in registry.VERSION_LEVELS)
# 04 T-REF-11: a rate set version runs DRAFT → SUBMITTED → APPROVED → SUPERSEDED and a rate resolves
# from APPROVED versions (ENGINE_SPEC_B §12.2.1 "pinned APPROVED versions"); it is never PUBLISHED
# (L6-5, CTR-20 K-04 FX_RATE_MISSING).
_FX_IN_FORCE: Final = (ConfigStatus.APPROVED.value, ConfigStatus.SUPERSEDED.value)
AMENDED_EVENT: Final = "CONTRACT_AMENDED"
# [J] L5-1-Q-27: E-23 legacy template treatment -> E-24 template mode (S01-R-09; ALG-04 §2.5.7).
TEMPLATE_MODES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "LEGACY_PROSPECTIVE": "prospective",
        "LEGACY_RETROSPECTIVE": "retrospective",
        "LEGACY_POB_VC": "pob_price_change",
    }
)
PRICE_CHANGE_MODE: Final = "pob_price_change"
# The event kinds that name a T-CON-06 row (04 §16.3 payloads: ``modification_id`` (R)).
_MODIFICATION_EVENTS: Final = frozenset({"CONTRACT_AMENDED", "CONTRACT_TERMINATED", "REGROUPED"})
NATIVE_CURRENCY_MISMATCH: Final = (
    "modification {key}: line {line} states its consideration in {found}, the modification is in "
    "{expected} (D-98 140-A6 NATIVE-MONEY-1: a native line is never retagged)"
)
NATIVE_MEMBER_CURRENCY_MISMATCH: Final = (
    "modification {key}: {member} is stated in {found}, the modification is in {expected} "
    "(D-98 140-A9 INPUT-1: every monetary member is validated at the adapter, never retagged)"
)
NATIVE_AND_LEGACY: Final = (
    "{event}: a legacy-template CONTRACT_AMENDED names the platform modification {key} "
    "(D-98 140 Q-3: a legacy amendment never also has a native T-CON-06 row)"
)


def _template_treatment(event_type: str, payload: Any) -> str | None:
    """The one legacy template treatment of a ``CONTRACT_AMENDED`` payload, else None."""
    if event_type != AMENDED_EVENT or not isinstance(payload, Mapping):
        return None
    treatments = payload.get("treatments")
    if not isinstance(treatments, Mapping) or not treatments:
        return None
    kinds = {str(value) for value in treatments.values()}
    return next(iter(kinds)) if len(kinds) == 1 and kinds <= set(TEMPLATE_MODES) else None


def _modification_key(event_type: str, payload: Any) -> str | None:
    """The projected modification key of a legacy template ``CONTRACT_AMENDED`` (L5-1-Q-27)."""
    if _template_treatment(event_type, payload) is None:
        return None
    return str(payload.get("modification_id"))


def _event_modification_key(
    event_type: str, payload: Any, native_ids: frozenset[str], *, event: str
) -> str | None:
    """The modification key an event carries: the legacy projection's key (L5-1-Q-27), else the
    id of the native T-CON-06 row the payload names (CTR-17; the engine matches
    ``payload.modification_id`` — stage 06 ``_modification_input``, stage 13
    ``_amendment_proposal``). A legacy template that names a native row is refused by name
    (D-98 140 Q-3)."""
    named = payload.get("modification_id") if isinstance(payload, Mapping) else None
    key = None if named is None else str(named)
    legacy = _modification_key(event_type, payload)
    if legacy is not None:
        if legacy in native_ids:
            raise ValueError(NATIVE_AND_LEGACY.format(event=event, key=legacy))
        return legacy
    if event_type in _MODIFICATION_EVENTS and key is not None and key in native_ids:
        return key
    return None


class NativeCurrencyMismatch(ValueError):
    """A native T-CON-06 monetary member stated in another currency than the modification's (D-98
    140-A9 / A12 INPUT-1): the adapter refuses by name; the API boundary translates THIS error (and
    only this one) into a named field refusal — never retagged, never a blanket ValueError → 422."""

    def __init__(self, member: str, message: str) -> None:
        self.member = member
        super().__init__(message)


def native_money(value: Any, *, currency: str, key: Any, member: str) -> Decimal | None:
    """D-98 140-A9 INPUT-1: one monetary member of a native T-CON-06 row as the engine's scalar —
    an API-S-Money object is validated against the modification's currency (a mismatch refuses by
    name, never retagged) and stripped to its amount; a bare decimal is kept; None stays None."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        found = str(value.get("currency") or currency).strip()
        if found != currency:
            raise NativeCurrencyMismatch(
                member,
                NATIVE_MEMBER_CURRENCY_MISMATCH.format(
                    key=key, member=member, found=found, expected=currency
                ),
            )
        return Decimal(str(value.get("amount")))
    return Decimal(str(value))


def _native_input(
    row: Mapping[str, Any],
    judgement_keys: Mapping[UUID, str],
    ssp_version_keys: Mapping[str, str],
) -> ModificationInput:
    """A platform-created T-CON-06 row as the engine's modification object (CTR-17). The key is
    the row id (what every event payload names); ``ssp_basis`` follows the legacy projection's
    shape; the optional consideration lists convert as the booking's do."""
    basis = row.get("ssp_basis") or {}
    ssp_basis = {
        str(key): {
            "is_override": "true" if item.get("is_override") else "false",
            "justification": str(item.get("justification") or ""),
            "ssp_version_key": ssp_version_keys.get(str(item.get("ssp_book_version_id")), ""),
        }
        for key, item in sorted(basis.items())
        if isinstance(item, Mapping)
    }
    noncash = row.get("noncash_consideration")
    payable = row.get("consideration_payable")
    judgement = row.get("judgement_record_id")
    # D-98 140-A6 NATIVE-MONEY-1: the row's lines carry API-S-Money objects; the engine reads the
    # scalar amount (ENGINE_SPEC §0.4, ``payload_fraction``), so the governed adapter validates the
    # currency against the modification's and normalises through ``engine_payload`` — exact values
    # preserved, the scalar contract untouched.
    currency = str(row["currency"]).strip()
    native_key = row.get("modification_no") or row["id"]
    lines: list[Mapping[str, Any]] = []
    for line in row.get("lines") or ():
        if not isinstance(line, Mapping):
            continue
        delta = line.get("consideration_delta")
        if isinstance(delta, Mapping):
            found = str(delta.get("currency") or currency).strip()
            if found != currency:
                raise NativeCurrencyMismatch(
                    f"lines[{line.get('obligation_key')}].consideration_delta",
                    NATIVE_CURRENCY_MISMATCH.format(
                        key=row.get("modification_no") or row["id"],
                        line=line.get("obligation_key"),
                        found=found,
                        expected=currency,
                    ),
                )
        lines.append(engine_payload(dict(line)))
    return ModificationInput(
        modification_key=str(row["id"]),
        effective_date=_day(row["effective_date"]),
        kind=str(row["kind"]),
        template_mode=None if row.get("template_mode") is None else str(row["template_mode"]),
        status=str(row["status"]),
        reference=None if row.get("reference") is None else str(row["reference"]),
        questionnaire=dict(row.get("questionnaire") or {}),
        lines=tuple(lines),
        price_change_amount=native_money(
            row.get("price_change_amount"),
            currency=currency,
            key=native_key,
            member="price_change_amount",
        ),
        noncash_consideration=None
        if noncash is None
        else tuple(
            NoncashInput(
                units=Decimal(str(item["units"])),
                fair_value_per_unit=native_money(
                    item["fair_value_per_unit"],
                    currency=currency,
                    key=native_key,
                    member=f"noncash[{i}].fair_value_per_unit",
                )
                or Decimal(0),
                measurement_date=_day(item["measurement_date"]),
                variability=str(item["variability"]),
                asset_type=item.get("asset_type"),
            )
            for i, item in enumerate(noncash)
        ),
        consideration_payable=None
        if payable is None
        else tuple(
            PayableInput(
                amount=native_money(
                    item["amount"], currency=currency, key=native_key, member=f"payable[{i}].amount"
                )
                or Decimal(0),
                promise_date=_day(item["promise_date"]),
                related_obligation_keys=tuple(item.get("related_obligation_keys") or ()),
                distinct_good_fair_value=native_money(
                    item.get("distinct_good_fair_value"),
                    currency=currency,
                    key=native_key,
                    member=f"payable[{i}].distinct_good_fair_value",
                ),
                committed_purchases=native_money(
                    item.get("committed_purchases"),
                    currency=currency,
                    key=native_key,
                    member=f"payable[{i}].committed_purchases",
                ),
                share_based=bool(item.get("share_based", False)),
            )
            for i, item in enumerate(payable)
        ),
        scope_605_35=row.get("scope_605_35"),
        currency=currency,
        proposed_treatments={
            str(key): str(value)
            for key, value in sorted((row.get("proposed_treatments") or {}).items())
        },
        chosen_treatments={
            str(key): str(value)
            for key, value in sorted((row.get("chosen_treatments") or {}).items())
        },
        treatment_summary=None
        if row.get("treatment_summary") is None
        else str(row["treatment_summary"]),
        ssp_basis=ssp_basis,
        judgement_key=None if judgement is None else judgement_keys.get(UUID(str(judgement))),
        content_sha256=None if row.get("content_sha256") is None else str(row["content_sha256"]),
    )


def _native_modifications(
    session: Session,
    stored: Sequence[Mapping[str, Any]],
    pending: Sequence[EventIn],
    pending_rows: Sequence[Mapping[str, Any]],
    *,
    external_ids: Mapping[UUID, str],
    ssp_version_keys: Mapping[str, str],
) -> tuple[dict[str, tuple[ModificationInput, ...]], frozenset[str], dict[UUID, dict[str, Any]]]:
    """Per member, the platform-created T-CON-06 rows the bundle carries (CTR-17; D-98 140 Q-3):
    the rows the stored and pending modification events name (native treatments; a legacy
    template keeps its L5-1-Q-27 projection) and ``pending_rows`` — a draft the platform
    classifies or previews, carried without an event so stage 13 proposes for it
    (``_pending_proposals``, S06-R-01). Returns the inputs per external id and the native row
    ids."""
    ids, legacy_named = named_modification_ids(stored, pending)
    rows: dict[UUID, dict[str, Any]] = {UUID(str(row["id"])): dict(row) for row in pending_rows}
    # D-98 140-A5 Q3: every named id is resolved before the native / legacy decision — a legacy
    # template that names an EXISTING T-CON-06 row joins the native set here, so ``_events``
    # refuses it by name (NATIVE_AND_LEGACY) instead of projecting over the row; a legacy id that
    # names no row keeps its L5-1-Q-27 projection.
    wanted = sorted((ids | legacy_named) - set(rows))
    if wanted:
        for stored_row in (
            session.execute(select(modification).where(modification.c.id.in_(wanted)))
            .mappings()
            .all()
        ):
            rows[UUID(str(stored_row["id"]))] = dict(stored_row)
    judgement_ids = sorted(
        {
            UUID(str(row["judgement_record_id"]))
            for row in rows.values()
            if row.get("judgement_record_id") is not None
        }
    )
    judgement_keys: dict[UUID, str] = {}
    if judgement_ids:
        for record_id, number in session.execute(
            select(judgement_record.c.id, judgement_record.c.judgement_no).where(
                judgement_record.c.id.in_(judgement_ids)
            )
        ):
            judgement_keys[UUID(str(record_id))] = str(number)
    found: dict[str, list[ModificationInput]] = {}
    for row in rows.values():
        contract_id = UUID(str(row["contract_id"]))
        if contract_id not in external_ids:
            continue  # a row of a contract outside this group names no member
        found.setdefault(external_ids[contract_id], []).append(
            _native_input(row, judgement_keys, ssp_version_keys)
        )
    return (
        {
            key: tuple(sorted(items, key=lambda item: item.modification_key))
            for key, items in found.items()
        },
        frozenset(str(key) for key in rows),
        rows,
    )


def named_modification_ids(
    stored: Sequence[Mapping[str, Any]], pending: Sequence[EventIn]
) -> tuple[frozenset[UUID], frozenset[UUID]]:
    """The modification ids the stored and pending modification events name, split into the ids
    of native treatments (a T-CON-06 row is expected) and the ids of legacy template treatments
    (an L5-1-Q-27 projection unless a row of that id exists; D-98 140-A5 Q3). Pure."""
    native: set[UUID] = set()
    legacy: set[UUID] = set()
    for row in stored:
        event_type = str(row["event_type"])
        payload = row["payload"]
        if event_type not in _MODIFICATION_EVENTS or not isinstance(payload, Mapping):
            continue
        named = payload.get("modification_id")
        if named is None:
            continue
        target = legacy if _template_treatment(event_type, payload) is not None else native
        target.add(UUID(str(named)))
    for event in pending:
        event_type = event.event_type.value
        if event_type not in _MODIFICATION_EVENTS:
            continue
        payload = payload_json(event.payload)
        named = payload.get("modification_id")
        if named is None:
            continue
        target = legacy if _template_treatment(event_type, payload) is not None else native
        target.add(UUID(str(named)))
    return frozenset(native), frozenset(legacy)


def pending_lines(
    pending_rows: Sequence[Mapping[str, Any]],
    external_ids: Mapping[UUID, str],
    *,
    applied: Collection[str],
) -> list[tuple[str, Mapping[str, Any]]]:
    """The lines of the pending T-CON-06 rows no pending event applies, keyed by the member's
    external id — the dependencies (products, performing entities, obligation policies) a
    classification's bundle collects without an applying event (D-98 140-A5 DOMAIN-R2). A row
    whose candidate event is pending contributes through that event's ``lines``. Pure."""
    found: list[tuple[str, Mapping[str, Any]]] = []
    for row in pending_rows:
        if str(row["id"]) in applied:
            continue
        contract_key = external_ids.get(UUID(str(row["contract_id"])))
        if contract_key is None:
            continue
        for line in row.get("lines") or ():
            if isinstance(line, Mapping):
                found.append((contract_key, line))
    return found


def _pending_applied(pending: Sequence[EventIn]) -> frozenset[str]:
    """The modification ids the pending events apply (their payload ``modification_id``)."""
    found: set[str] = set()
    for event in pending:
        if event.event_type.value not in _MODIFICATION_EVENTS:
            continue
        named = payload_json(event.payload).get("modification_id")
        if named is not None:
            found.add(str(named))
    return frozenset(found)


def fx_rate_inputs(
    session: Session, currencies: Iterable[str], known_at: datetime | None
) -> tuple[FxRateInput, ...]:
    """The pinned FX rate rows of ``currencies`` in force at ``known_at`` — the rows a bundle of
    these currencies carries (``_fx_rates``); CTR-17 retains the modification preview's rate basis
    from them (04 §16.14 ``fx_basis``). None reads every committed version now in force,
    for controls whose decision must not miss a publication that overtook their transaction."""
    return _fx_rates(session, currencies, known_at)


def _payload_lines(payload: Mapping[str, object]) -> list[Mapping[str, Any]]:
    members = payload.get("lines")
    if not isinstance(members, list | tuple):
        return []
    return [line for line in members if isinstance(line, Mapping)]


def _apply_regroups(
    events: Sequence[EventInput], rows: Mapping[UUID, Mapping[str, Any]]
) -> tuple[EventInput, ...]:
    """S06-R-27 before posting (CTR-17): a regroup applied without an approval request (the pair of
    T-CON-06 rows the command applied at once because nothing had posted) moves the named lines out
    of the source's ``CONTRACT_BOOKED`` payload and into the target's, so stage 06's
    ``before_posting`` sees the obligations absent from the source and booked in the target from
    its inception (no boundary). Each side is applied from its own stream (D-98 140-A6 REGROUP-R1):
    the source group's bundle sees the ``OUT`` event and removes the lines; the target group's
    bundle sees the ``IN`` event and adds the lines — from the source's booking when the source is
    a member of the same bundle, else from the ``IN`` event's own ``lines`` (04 §16.3), so two
    groups are never merged. A regroup pair that went through approval (after posting) changes
    nothing here: its paired events are the modification of both contracts."""
    by_regroup: dict[str, dict[str, EventInput]] = {}
    for event in events:
        if event.event_type != "REGROUPED":
            continue
        direction = event.payload.get("direction")
        regroup_id = event.payload.get("regroup_id")
        if direction not in ("OUT", "IN") or regroup_id is None:
            continue
        by_regroup.setdefault(str(regroup_id), {})[str(direction)] = event
    moves: list[tuple[str | None, str | None, tuple[str, ...], list[Mapping[str, Any]]]] = []
    for sides in by_regroup.values():
        seen = sides.get("OUT") or sides.get("IN")
        if seen is None:
            continue
        named = seen.payload.get("modification_id")
        row = None if named is None else rows.get(UUID(str(named)))
        if row is None or row.get("approval_request_id") is not None:
            continue  # after posting: the events are the modification (S06-R-27)
        named_keys = seen.payload.get("obligation_keys")
        keys = tuple(
            str(key) for key in (named_keys if isinstance(named_keys, list | tuple) else ())
        )
        out_event, in_event = sides.get("OUT"), sides.get("IN")
        evidence = _payload_lines(in_event.payload) if in_event is not None else []
        moves.append(
            (
                None if out_event is None else out_event.contract_key,
                None if in_event is None else in_event.contract_key,
                keys,
                evidence,
            )
        )
    if not moves:
        return tuple(events)
    changed = list(events)

    def _booking_index(contract_key: str | None) -> int | None:
        if contract_key is None:
            return None
        return next(
            (
                i
                for i, e in enumerate(changed)
                if e.contract_key == contract_key and e.event_type == "CONTRACT_BOOKED"
            ),
            None,
        )

    for source, target, keys, evidence in moves:
        wanted = set(keys)
        source_index = _booking_index(source)
        target_index = _booking_index(target)
        moved: list[Mapping[str, Any]] = []
        if source_index is not None:
            source_event = changed[source_index]
            source_lines = _payload_lines(source_event.payload)
            moved = [line for line in source_lines if str(line.get("obligation_key")) in wanted]
            kept = [line for line in source_lines if str(line.get("obligation_key")) not in wanted]
            changed[source_index] = dataclasses.replace(
                source_event,
                payload={**source_event.payload, "lines": kept},
                obligation_keys=tuple(k for k in source_event.obligation_keys if k not in wanted),
            )
        if target_index is None:
            continue
        if not moved:
            # the source sits in another group: the IN event's own lines are the evidence
            moved = [line for line in evidence if str(line.get("obligation_key")) in wanted]
        if not moved:
            continue  # the target was booked with the lines already (a new contract)
        target_event = changed[target_index]
        target_lines = _payload_lines(target_event.payload)
        present = {str(line.get("obligation_key")) for line in target_lines}
        added = [line for line in moved if str(line.get("obligation_key")) not in present]
        changed[target_index] = dataclasses.replace(
            target_event,
            payload={**target_event.payload, "lines": [*target_lines, *added]},
            obligation_keys=(
                *target_event.obligation_keys,
                *(k for k in keys if k not in target_event.obligation_keys),
            ),
        )
    return tuple(changed)


def _merged_modifications(
    legacy: Sequence[ModificationInput], native: Sequence[ModificationInput]
) -> tuple[ModificationInput, ...]:
    """The member's modifications: the legacy projections and the native rows, one key each."""
    merged = sorted((*legacy, *native), key=lambda item: item.modification_key)
    keys = [item.modification_key for item in merged]
    if len(set(keys)) != len(keys):
        duplicate = next(key for key in keys if keys.count(key) > 1)
        raise ValueError(NATIVE_AND_LEGACY.format(event="bundle", key=duplicate))
    return tuple(merged)


def _modifications(
    events: Sequence[EventInput],
    *,
    ssp_version_keys: Mapping[str, str],
    currencies: Mapping[str, str],
) -> dict[str, tuple[ModificationInput, ...]]:
    """Per member, the modifications its legacy template amendments apply (module docstring)."""
    found: dict[str, list[ModificationInput]] = {}
    for event in events:
        treatment = _template_treatment(event.event_type, event.payload)
        if treatment is None or event.modification_key is None:
            continue
        payload = event.payload
        members = payload.get("lines")
        lines = tuple(
            dict(line)
            for line in (members if isinstance(members, list | tuple) else ())
            if isinstance(line, Mapping)
        )
        treatments = payload.get("treatments")
        chosen = treatments if isinstance(treatments, Mapping) else {}
        mode = TEMPLATE_MODES[treatment]
        if mode == PRICE_CHANGE_MODE:
            kind = "VC_CHANGE"
        elif any(line.get("action") == "ADD" for line in lines):
            kind = "ADD_OBLIGATION"
        else:
            kind = "QUANTITY_CHANGE"
        basis = payload.get("ssp_basis")
        ssp_basis = {
            str(key): {
                "is_override": "true" if item.get("is_override") else "false",
                "justification": str(item.get("justification") or ""),
                "ssp_version_key": ssp_version_keys.get(str(item.get("ssp_book_version_id")), ""),
            }
            for key, item in sorted((basis if isinstance(basis, Mapping) else {}).items())
            if isinstance(item, Mapping)
        }
        found.setdefault(event.contract_key, []).append(
            ModificationInput(
                modification_key=event.modification_key,
                effective_date=event.effective_date,
                kind=kind,
                template_mode=mode,
                status="APPLIED",
                reference=None,
                questionnaire={},
                lines=lines,
                price_change_amount=None,
                noncash_consideration=None,
                consideration_payable=None,
                scope_605_35=None,
                currency=currencies[event.contract_key],
                proposed_treatments={},
                chosen_treatments={str(key): str(value) for key, value in sorted(chosen.items())},
                treatment_summary=treatment,
                ssp_basis=ssp_basis,
                judgement_key=None,
                content_sha256=event.payload_sha256,
            )
        )
    return {
        key: tuple(sorted(items, key=lambda item: item.modification_key))
        for key, items in found.items()
    }


def _event_key(contract_key: str, stream_version: int) -> str:
    """CV-22 global event key ``<encoded external_id>/EV-<6 digits>``."""
    return f"{contract_subject_key(contract_key)}/EV-{stream_version:06d}"


def _flat_values(values: Mapping[str, Any]) -> dict[str, str]:
    """Level P values as the text members of ``ProductInput`` (``templates`` convention)."""
    flat: dict[str, str] = {}
    for code, value in sorted(values.items()):
        converted = engine_policy_value(value)
        if isinstance(converted, str):
            flat[str(code)] = converted
        elif isinstance(converted, Mapping):
            flat[str(code)] = ",".join(converted.values())
        else:
            flat[str(code)] = ",".join(converted)
    return flat


def _contract_pinned(values: Mapping[str, Any]) -> dict[str, Any]:
    """The contract-pinned (pin K) members of level P values; pin P values stay PERIOD-scoped."""
    return {
        str(code): value
        for code, value in values.items()
        if code in POLICY_PARAMETERS and POLICY_PARAMETERS[code].pin == "K"
    }


def engine_payload(value: Any) -> Any:
    """A stored payload with money objects as their amount strings (ENGINE_SPEC §0.4)."""
    if isinstance(value, Mapping):
        if set(value) == {"amount", "currency"} and isinstance(value.get("amount"), str):
            return value["amount"]
        return {str(key): engine_payload(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [engine_payload(item) for item in value]
    return value


def _override_keys(payload: Mapping[str, Any], version_keys: Mapping[str, str]) -> Any:
    """``CONTRACT_AMENDED`` with ``ssp_version_key`` beside the ``ssp_book_version_id`` of every
    approved override of its ``ssp_basis`` (``is_override`` true): the member stage 06 prices the
    obligation's weight from (01-DECISIONS D-18; ENGINE_SPEC S06-R-11; item
    MOD-SSP-OVERRIDE-PREVIEW-1). The projections of ``_native_input`` and ``_modifications`` map
    the same id; a classification default (``is_override`` false) is not read by the engine and
    stays as stored, as does an id without an approved version."""
    basis = payload.get("ssp_basis")
    if not isinstance(basis, Mapping):
        return payload
    keyed = {
        key: {**entry, "ssp_version_key": version_keys[str(entry.get("ssp_book_version_id"))]}
        for key, entry in basis.items()
        if isinstance(entry, Mapping)
        and entry.get("is_override")
        and str(entry.get("ssp_book_version_id")) in version_keys
    }
    return {**payload, "ssp_basis": {**basis, **keyed}} if keyed else payload


def _ssp_pin_key(event_type: str, payload: Any, version_keys: Mapping[str, str]) -> Any:
    """The SSP versions a payload names by id, under the keys the engine reads:
    ``LINE_ATTRIBUTES_CHANGED`` with ``changes.ssp_book_version_id`` as the key of the approved
    SSP version it names (S06-R-26; CTR-15), ``CONTRACT_AMENDED`` as ``_override_keys`` gives it;
    an id without an approved version stays as it is."""
    if event_type == AMENDED_EVENT and isinstance(payload, Mapping):
        return _override_keys(payload, version_keys)
    if event_type != ATTRIBUTES_EVENT or not isinstance(payload, Mapping):
        return payload
    changes = payload.get("changes")
    if not isinstance(changes, Mapping) or changes.get("ssp_book_version_id") is None:
        return payload
    key = version_keys.get(str(changes["ssp_book_version_id"]))
    if key is None:
        return payload
    return {**payload, "changes": {**changes, "ssp_book_version_id": key}}


def _members(session: Session, group_id: UUID, known_at: datetime) -> list[dict[str, Any]]:
    member = combination_group_member
    statement = (
        select(contract)
        .select_from(
            member.join(
                contract,
                and_(
                    contract.c.tenant_id == member.c.tenant_id,
                    contract.c.id == member.c.contract_id,
                ),
            )
        )
        .where(
            member.c.combination_group_id == group_id,
            member.c.valid_from_known_at <= known_at,
            or_(member.c.valid_to_known_at.is_(None), member.c.valid_to_known_at > known_at),
        )
        .order_by(contract.c.external_id)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _stored_events(
    session: Session, contract_ids: Sequence[UUID], known_at: datetime
) -> list[dict[str, Any]]:
    statement = (
        select(contract_event)
        .where(
            contract_event.c.contract_id.in_(contract_ids), contract_event.c.recorded_at <= known_at
        )
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _obligations(session: Session, contract_ids: Sequence[UUID]) -> list[dict[str, Any]]:
    statement = select(obligation).where(obligation.c.contract_id.in_(contract_ids))
    return [dict(row) for row in session.execute(statement).mappings()]


def _hold_handle(event_type: str, payload: Any, by_id: Mapping[UUID, str]) -> Any:
    """[J] L4-1-Q-22 (BUILD_SPEC CTR-10): ``HOLD_RELEASED.hold_id`` names ``contract_hold.id``,
    which equals the id of the hold's ``HOLD_APPLIED``; the engine reads its event key (S09-R-42;
    L1-3-Q-15)."""
    if event_type != ContractEventType.HOLD_RELEASED.value or not isinstance(payload, Mapping):
        return payload
    try:
        key = by_id.get(UUID(str(payload.get("hold_id"))))
    except ValueError:
        return payload
    return payload if key is None else {**payload, "hold_id": key}


ADJUSTMENT_EVENT: Final = ContractEventType.MANUAL_ADJUSTMENT_APPLIED.value
# 04 E-93 kinds whose payload carries lines (ENGINE_SPEC_B S09-R-41, S14-R-09a).
JOURNAL_KINDS: Final = frozenset({"MANUAL_JOURNAL", "ACCOUNT_RECLASS"})


def _amount_text(value: Any) -> str | None:
    """The amount string of a stored money member: API-S-Money ``{amount, currency}`` or a plain
    decimal string (the engine reads plain decimals, ENGINE_SPEC §0.4)."""
    if isinstance(value, Mapping):
        value = value.get("amount")
    return None if value is None else str(value)


def adjustment_members(
    row: Mapping[str, Any],
    *,
    entity_code: str,
    period_key: str,
    period_keys: Mapping[str, str],
    obligation_keys: Mapping[UUID, str],
) -> dict[str, Any]:
    """The engine payload members of one T-SL-05 row (decision L1-3-Q-14): ``kind``,
    ``book_code``, ``entity_code``, ``period_key`` (the adjustment period P), ``obligation_key``
    when the row names an obligation, and the kind payload with handles as natural keys —
    ``amount`` | ``ratio`` | ``remaining`` (S09-R-38, S09-R-39), ``periods`` [{``period_key``,
    ``amount``}] (S09-R-40), or ``lines`` [{``account_role``, ``amount_txn``}] (S14-R-09a: one
    amount a line, the contract being in its entity's functional currency). A period id the
    calendar does not hold stays out, so the engine refuses the adjustment by name instead of
    guessing."""
    stored = row["payload"] if isinstance(row["payload"], Mapping) else {}
    kind = _text_of(row["kind"])
    members: dict[str, Any] = {
        "kind": kind,
        "book_code": _text_of(row["book_code"]),
        "entity_code": entity_code,
        "period_key": period_key,
    }
    obligation_id = row["obligation_id"]
    if obligation_id is not None and UUID(str(obligation_id)) in obligation_keys:
        members["obligation_key"] = obligation_keys[UUID(str(obligation_id))]
    if kind in JOURNAL_KINDS:
        members["lines"] = [
            {
                "account_role": str(line.get("account_role")),
                "amount_txn": _amount_text(line.get("amount_txn")),
            }
            for line in stored.get("lines") or ()
        ]
    elif kind == "SCHEDULE_OVERRIDE":
        members["periods"] = [
            {
                "period_key": period_keys.get(str(item.get("period_id"))),
                "amount": _amount_text(item.get("amount")),
            }
            for item in stored.get("periods") or ()
        ]
    else:
        for basis in ("amount", "ratio"):
            if stored.get(basis) is not None:
                members[basis] = _amount_text(stored[basis])
        if stored.get("remaining") is True:
            members["remaining"] = True
    return members


def adjustment_payloads(
    session: Session,
    stored: Sequence[Mapping[str, Any]],
    pending: Sequence[EventIn],
    *,
    obligation_keys: Mapping[UUID, str],
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Per adjustment id (text) named by an included or pending ``MANUAL_ADJUSTMENT_APPLIED``: the
    adjustment number — the event's ``manual_adjustment_key`` — and its engine payload members.
    An id without a visible row resolves to nothing; the engine then refuses the event."""
    ids = {
        UUID(str(row["manual_adjustment_id"]))
        for row in stored
        if row["manual_adjustment_id"] is not None
        and _text_of(row["event_type"]) == ADJUSTMENT_EVENT
    }
    ids |= {
        event.manual_adjustment_id
        for event in pending
        if event.manual_adjustment_id is not None
        and event.event_type is ContractEventType.MANUAL_ADJUSTMENT_APPLIED
    }
    if not ids:
        return {}
    rows = [
        dict(row)
        for row in session.execute(
            select(
                manual_adjustment,
                legal_entity.c.code.label("entity_code"),
                period.c.period_key,
            )
            .select_from(
                manual_adjustment.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == manual_adjustment.c.tenant_id,
                        legal_entity.c.id == manual_adjustment.c.entity_id,
                    ),
                ).join(
                    period,
                    and_(
                        period.c.tenant_id == manual_adjustment.c.tenant_id,
                        period.c.id == manual_adjustment.c.period_id,
                    ),
                )
            )
            .where(manual_adjustment.c.id.in_(sorted(ids)))
        ).mappings()
    ]
    listed: set[UUID] = set()
    for row in rows:
        payload = row["payload"] if isinstance(row["payload"], Mapping) else {}
        for item in payload.get("periods") or ():
            try:
                listed.add(UUID(str(item.get("period_id"))))
            except (AttributeError, ValueError):
                continue
    period_keys = (
        {
            str(period_id): str(key)
            for period_id, key in session.execute(
                select(period.c.id, period.c.period_key).where(period.c.id.in_(sorted(listed)))
            )
        }
        if listed
        else {}
    )
    return {
        str(row["id"]): (
            str(row["adjustment_no"]),
            adjustment_members(
                row,
                entity_code=str(row["entity_code"]),
                period_key=str(row["period_key"]),
                period_keys=period_keys,
                obligation_keys=obligation_keys,
            ),
        )
        for row in rows
    }


def _adjustment_payload(
    event_type: str,
    payload: Any,
    adjustment_id: Any,
    adjustments: Mapping[str, tuple[str, Mapping[str, Any]]],
) -> tuple[Any, str | None]:
    """The engine payload and ``manual_adjustment_key`` of an event: a
    ``MANUAL_ADJUSTMENT_APPLIED`` gains the members of its T-SL-05 row; every other event is
    unchanged."""
    if event_type != ADJUSTMENT_EVENT or adjustment_id is None:
        return payload, None
    found = adjustments.get(str(adjustment_id))
    if found is None or not isinstance(payload, Mapping):
        return payload, None
    return {**payload, **found[1]}, found[0]


def _events(
    rows: Sequence[Mapping[str, Any]],
    pending: Sequence[EventIn],
    *,
    contracts: Mapping[UUID, Mapping[str, Any]],
    obligation_keys: Mapping[UUID, str],
    known_at: datetime,
    pending_contract_id: UUID | None,
    ssp_version_keys: Mapping[str, str] | None = None,
    estimate_version_keys: Mapping[str, str] | None = None,
    native_modification_ids: frozenset[str] = frozenset(),
    adjustments: Mapping[str, tuple[str, Mapping[str, Any]]] | None = None,
) -> tuple[EventInput, ...]:
    version_keys = ssp_version_keys or {}
    estimate_keys = estimate_version_keys or {}
    resolved = adjustments or {}
    keys = {
        (UUID(str(row["contract_id"])), int(row["stream_version"])): _event_key(
            str(contracts[UUID(str(row["contract_id"]))]["external_id"]), int(row["stream_version"])
        )
        for row in rows
    }
    by_id = {
        UUID(str(row["id"])): keys[(UUID(str(row["contract_id"])), int(row["stream_version"]))]
        for row in rows
    }
    found: list[EventInput] = []
    for row in rows:
        contract_row = contracts[UUID(str(row["contract_id"]))]
        external_id = str(contract_row["external_id"])
        supersedes = row["supersedes_event_id"]
        event_type = str(row["event_type"])
        stored_payload, adjustment_key = _adjustment_payload(
            event_type,
            engine_payload(row["payload"]),
            # only a MANUAL_ADJUSTMENT_APPLIED row names an adjustment (04 T-CON-05)
            row["manual_adjustment_id"] if event_type == ADJUSTMENT_EVENT else None,
            resolved,
        )
        found.append(
            EventInput(
                event_key=keys[(UUID(str(row["contract_id"])), int(row["stream_version"]))],
                contract_key=external_id,
                stream_version=int(row["stream_version"]),
                event_type=str(row["event_type"]),
                schema_version=int(row["schema_version"]),
                effective_date=row["effective_date"],
                recorded_at=row["recorded_at"],
                record_seq=int(row["record_seq"]),
                origin=str(row["origin"]),
                is_manual=bool(row["is_manual"]),
                obligation_keys=tuple(
                    obligation_keys[UUID(str(value))] for value in row["obligation_ids"] or ()
                ),
                payload=_ssp_pin_key(
                    str(row["event_type"]),
                    _hold_handle(str(row["event_type"]), stored_payload, by_id),
                    version_keys,
                ),
                payload_sha256=str(row["payload_sha256"]),
                idempotency_key=row["idempotency_key"],
                supersedes_event_key=None
                if supersedes is None
                else by_id.get(UUID(str(supersedes))),
                modification_key=_event_modification_key(
                    str(row["event_type"]),
                    row["payload"],
                    native_modification_ids,
                    event=_event_key(
                        str(contracts[UUID(str(row["contract_id"]))]["external_id"]),
                        int(row["stream_version"]),
                    ),
                ),
                estimate_version_key=None
                if row["estimate_version_id"] is None
                else estimate_keys.get(str(row["estimate_version_id"])),
                manual_adjustment_key=adjustment_key,
            )
        )
    if pending:
        if pending_contract_id is None:
            raise ValueError("pending events need the contract they are appended to")
        target = contracts[pending_contract_id]
        external_id = str(target["external_id"])
        head = int(target["head_stream_version"])
        next_seq = max((int(row["record_seq"]) for row in rows), default=0) + 1
        for offset, event in enumerate(pending, start=1):
            pending_payload, pending_key = _adjustment_payload(
                event.event_type.value,
                engine_payload(payload_json(event.payload)),
                event.manual_adjustment_id,
                resolved,
            )
            payload = _ssp_pin_key(
                event.event_type.value,
                _hold_handle(event.event_type.value, pending_payload, by_id),
                version_keys,
            )
            found.append(
                EventInput(
                    event_key=_event_key(external_id, head + offset),
                    contract_key=external_id,
                    stream_version=head + offset,
                    event_type=event.event_type.value,
                    # the version ``stream`` appends at (stream.py; D-98 cand. 127, Codex 0533 F2)
                    schema_version=LATEST_SCHEMA_VERSION[event.event_type],
                    effective_date=event.effective_date,
                    recorded_at=known_at,
                    record_seq=next_seq + offset - 1,
                    origin="API",
                    is_manual=event.is_manual,
                    obligation_keys=tuple(event.obligation_keys),
                    payload=payload,
                    payload_sha256=sha256_hex(payload_json(event.payload)),
                    idempotency_key=event.idempotency_key,
                    supersedes_event_key=None
                    if event.supersedes_event_id is None
                    else by_id.get(event.supersedes_event_id),
                    modification_key=_event_modification_key(
                        event.event_type.value,
                        payload,
                        native_modification_ids,
                        event=_event_key(external_id, head + offset),
                    ),
                    estimate_version_key=None
                    if event.estimate_version_id is None
                    else estimate_keys.get(str(event.estimate_version_id)),
                    manual_adjustment_key=pending_key,
                )
            )
    return tuple(sorted(found, key=lambda e: (e.effective_date, e.record_seq, e.event_key)))


def _text_of(value: Any) -> str:
    return str(getattr(value, "value", value))


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def estimate_version_input(
    version: Mapping[str, Any],
    element: Mapping[str, Any],
    *,
    contract_key: str,
    obligation_keys: Mapping[UUID, str],
    version_keys: Mapping[str, str],
    status: str | None = None,
) -> EstimateVersionInput:
    """A T-CON-13 row and its T-CON-12 element as the engine's ``EstimateVersionInput`` (§0.4).

    The estimate key is ``<contract external_id>/<element code>`` and the version key
    ``<estimate key>@v<version_no>``, as the answer-key runner builds them; ``status`` overrides the
    stored status of a dry-run version. The element's T-CON-12 ``direction`` (B3-D16) travels on
    the input and the amounts stay the stored magnitudes; the engine applies the sign
    (ENC-VC-direction; this replaces the L5 ``_vc_sign`` workaround, L5-1-Q-35, L5-2-Q-9, which
    signed the amounts of a ``DECREASE`` element of a non-reducing type and could not carry an
    ``INCREASE`` on a reducing type). [J] L5-2-Q-5: a scenario table in which an outcome carries no
    probability is not passed, so the version carries its stored amounts (S04-R-05).
    """
    element_code = str(element["element_code"])
    estimate_key = obligation_subject_key(contract_key, element_code)
    version_no = int(version["version_no"])
    scenarios = [item for item in version["scenarios"] or () if isinstance(item, Mapping)]
    weighted = bool(scenarios) and all(item.get("probability") is not None for item in scenarios)
    obligation_id = element["obligation_id"]
    supersedes = version["supersedes_version_id"]
    targets = [UUID(str(value)) for value in element["target_obligation_ids"] or ()]
    return EstimateVersionInput(
        estimate_key=estimate_key,
        estimate_kind=_text_of(element["estimate_kind"]),
        element_code=element_code,
        method=_text_of(element["method"]),
        vc_element_type=None
        if element["vc_element_type"] is None
        else str(element["vc_element_type"]),
        direction=_text_of(element["direction"]),
        allocation_target=str(element["allocation_target"]),
        target_obligation_keys=tuple(
            sorted(obligation_keys[target] for target in targets if target in obligation_keys)
        ),
        obligation_key=None
        if obligation_id is None
        else obligation_keys.get(UUID(str(obligation_id))),
        version_key=f"{estimate_key}@v{version_no}",
        version_no=version_no,
        status=_text_of(version["status"]) if status is None else status,
        effective_date=version["effective_date"],
        scenarios=tuple(
            {
                "amount": Decimal(str(item["amount"])),
                "probability": Decimal(str(item["probability"])),
            }
            for item in scenarios
        )
        if weighted
        else (),
        parameters=dict(sorted(dict(version["parameters"] or {}).items())),
        unconstrained_amount=_optional_decimal(version["unconstrained_amount"]),
        most_conservative_amount=_optional_decimal(version["most_conservative_amount"]),
        constrained_amount=_optional_decimal(version["constrained_amount"]),
        rate=_optional_decimal(version["rate"]),
        expected_total_amount=_optional_decimal(version["expected_total_amount"]),
        expected_quantity=_optional_decimal(version["expected_quantity"]),
        amortization_months=None
        if version["amortization_months"] is None
        else int(version["amortization_months"]),
        currency=None if version["currency"] is None else str(version["currency"]).strip(),
        supersedes_version_key=None if supersedes is None else version_keys.get(str(supersedes)),
        judgement_key=None,
        content_sha256=str(version["content_sha256"] or "").strip(),
    )


def _estimate_versions(
    session: Session,
    stored: Sequence[Mapping[str, Any]],
    pending: Sequence[EventIn],
    *,
    contracts: Mapping[UUID, Mapping[str, Any]],
    obligation_keys: Mapping[UUID, str],
) -> tuple[tuple[EstimateVersionInput, ...], dict[str, str]]:
    """The versions the included and pending ``ESTIMATE_CHANGED`` events name, in bundle order
    (estimate key, version number), and their keys by version id (S01-R-18)."""
    ids = {
        UUID(str(row["estimate_version_id"]))
        for row in stored
        if row["estimate_version_id"] is not None
        and _text_of(row["event_type"]) == ContractEventType.ESTIMATE_CHANGED.value
    }
    ids |= {
        event.estimate_version_id
        for event in pending
        if event.estimate_version_id is not None
        and event.event_type is ContractEventType.ESTIMATE_CHANGED
    }
    if not ids:
        return (), {}
    versions = [
        dict(row)
        for row in session.execute(
            select(estimate_version).where(estimate_version.c.id.in_(sorted(ids)))
        ).mappings()
    ]
    elements = {
        UUID(str(row["id"])): dict(row)
        for row in session.execute(
            select(estimate).where(
                estimate.c.id.in_(sorted({UUID(str(row["estimate_id"])) for row in versions}))
            )
        ).mappings()
    }
    members: list[tuple[Mapping[str, Any], Mapping[str, Any], str]] = []
    for row in versions:
        element = elements.get(UUID(str(row["estimate_id"])))
        contract_id = None if element is None else element["contract_id"]
        if element is None or contract_id is None or UUID(str(contract_id)) not in contracts:
            continue  # [J] portfolio-scoped versions apply through CTR-13
        members.append((row, element, str(contracts[UUID(str(contract_id))]["external_id"])))
    keys = {
        str(row["id"]): (
            f"{obligation_subject_key(external_id, str(element['element_code']))}"
            f"@v{int(row['version_no'])}"
        )
        for row, element, external_id in members
    }
    inputs = [
        estimate_version_input(
            row,
            element,
            contract_key=external_id,
            obligation_keys=obligation_keys,
            version_keys=keys,
        )
        for row, element, external_id in members
    ]
    return tuple(sorted(inputs, key=lambda item: (item.estimate_key, item.version_no))), keys


def _term_payload(events: Sequence[EventInput], contract_key: str) -> Mapping[str, Any]:
    """The latest ``CONTRACT_BOOKED`` payload of a contract (S01-R-20)."""
    found: Mapping[str, Any] = {}
    for event in events:
        if event.contract_key == contract_key and event.event_type == "CONTRACT_BOOKED":
            found = event.payload
    return found


def _lines(events: Sequence[EventInput]) -> list[tuple[str, Mapping[str, Any]]]:
    found: list[tuple[str, Mapping[str, Any]]] = []
    for event in events:
        members = event.payload.get("lines") if event.event_type in TERM_EVENTS else None
        for line in members if isinstance(members, list | tuple) else ():
            if isinstance(line, Mapping):
                found.append((event.contract_key, line))
    return found


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _header(
    row: Mapping[str, Any],
    *,
    customer_codes: Mapping[UUID, str],
    group_codes: Mapping[UUID, str | None],
    entity_codes: Mapping[UUID, str],
    renewal_keys: Mapping[UUID, str],
    booking: Mapping[str, Any],
    judgements: tuple[JudgementInput, ...] = (),
    modifications: tuple[ModificationInput, ...] = (),
) -> ContractInput:
    customer_id = UUID(str(row["customer_id"]))
    renewal = row["renewal_of_contract_id"]
    schedule = booking.get("payment_schedule") or ()
    noncash = booking.get("noncash_consideration") or ()
    payable = booking.get("consideration_payable") or ()
    return ContractInput(
        external_id=str(row["external_id"]),
        customer_code=customer_codes[customer_id],
        related_party_group=group_codes.get(customer_id),
        contracting_entity_code=entity_codes[UUID(str(row["contracting_entity_id"]))],
        transaction_currency=str(row["transaction_currency"]).strip(),
        inception_date=row["inception_date"],
        signature_date=row["signature_date"],
        document_ref=row["document_ref"],
        termination_party=row["termination_party"],
        termination_has_penalty=row["termination_has_penalty"],
        termination_notice_days=row["termination_notice_days"],
        has_commercial_substance=bool(row["has_commercial_substance"]),
        region=row["region"],
        channel=row["channel"],
        contract_type=row["contract_type"],
        renewal_of_contract_key=None if renewal is None else renewal_keys.get(UUID(str(renewal))),
        judgements=judgements,
        material_rights=(),
        modifications=modifications,
        noncash_consideration=tuple(
            NoncashInput(
                units=Decimal(str(item["units"])),
                fair_value_per_unit=Decimal(str(item["fair_value_per_unit"])),
                measurement_date=_day(item["measurement_date"]),
                variability=str(item["variability"]),
                asset_type=item.get("asset_type"),
            )
            for item in noncash
        ),
        consideration_payable=tuple(
            PayableInput(
                amount=Decimal(str(item["amount"])),
                promise_date=_day(item["promise_date"]),
                related_obligation_keys=tuple(item.get("related_obligation_keys") or ()),
                distinct_good_fair_value=_decimal(item.get("distinct_good_fair_value")),
                committed_purchases=_decimal(item.get("committed_purchases")),
                share_based=bool(item.get("share_based", False)),
            )
            for item in payable
        ),
        payment_schedule=tuple(
            PaymentPointInput(date=_day(item["date"]), amount=Decimal(str(item["amount"])))
            for item in schedule
        ),
        scope_605_35=bool(row["scope_605_35"]),
    )


def _render(value: Any) -> str | None:
    """A questionnaire member as ``JudgementInput.outcome`` renders it (04 T-CON-19)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | Decimal):
        return str(value)
    return None


def _judgements(
    session: Session,
    external_ids: Mapping[UUID, str],
    obligation_keys: Mapping[UUID, str],
    known_at: datetime,
) -> dict[UUID, tuple[JudgementInput, ...]]:
    """The judgement records of the members reviewed by ``known_at`` (CTR-7; ENGINE_SPEC Table
    0.4-A). A record superseded later still governed at ``known_at``; of several on one topic the
    engine takes the greatest ``judgement_key``, the series number. The subject is the contract's
    external id, or the obligation subject key of an obligation record."""
    if not external_ids:
        return {}
    statement = (
        select(judgement_record)
        .where(
            judgement_record.c.contract_id.in_(sorted(external_ids)),
            judgement_record.c.status.in_(
                [JudgementStatus.REVIEWED.value, JudgementStatus.SUPERSEDED.value]
            ),
            judgement_record.c.reviewed_at <= known_at,
        )
        .order_by(judgement_record.c.judgement_no)
    )
    found: dict[UUID, list[JudgementInput]] = {}
    for row in session.execute(statement).mappings():
        contract_id = UUID(str(row["contract_id"]))
        external_id = external_ids[contract_id]
        subject_key = external_id
        if str(row["subject_type"]) == "obligation":
            key = obligation_keys.get(UUID(str(row["subject_id"])))
            if key is not None:
                subject_key = obligation_subject_key(external_id, key)
        outcome = {
            str(name): rendered
            for name, value in sorted(dict(row["questionnaire"] or {}).items())
            if (rendered := _render(value)) is not None
        }
        book_code = row["book_code"]
        found.setdefault(contract_id, []).append(
            JudgementInput(
                judgement_key=str(row["judgement_no"]),
                topic=str(getattr(row["topic"], "value", row["topic"])),
                subject_key=subject_key,
                book_code=None
                if book_code is None
                else str(getattr(book_code, "value", book_code)),
                outcome=outcome,
            )
        )
    return {contract_id: tuple(items) for contract_id, items in found.items()}


# --- product pins (04 T-CON-07 ``pinned_refs.products`` rev 1.110; DG-KRN-REG-02 rev 1.93) -------
#
# Security ruling R-21 (finding SN-7). A product is a master-data row without versions, so what a
# computation pins is the value: the ``ProductInput`` it was computed with and the level-P values
# of the product's obligations. ``product_pin_members`` derives the member from the computed
# bundle; ``ProductPins`` reads it back for the next bundle of the group.

PRODUCT_PINS: Final = "products"
OBLIGATION_POLICIES: Final = "obligation_policies"
# E-17 statuses in which nothing of a contract posts (ENGINE_SPEC S02-R-02): its products are read
# from T-REF-20, so that a repaired product still reaches a draft (REQ-REF-014).
_UNPINNED_STATUSES: Final = frozenset({"DRAFT", "PENDING_REVIEW"})
_PRODUCT_MEMBERS: Final = (
    "sku_number",
    "product_family",
    "revenue_category",
    "default_template_code",
    "principal_agent",
    "distinctness_default",
    "unit_of_measure",
    "is_bundle",
    "is_franchisor_preopening_service",
)


def _pin_text(value: Decimal | date | None) -> str | None:
    """An exact decimal or a date as the text ``pinned_product`` reads back unchanged."""
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def product_pin(item: ProductInput, policies: Mapping[str, Any] | None) -> dict[str, Any]:
    """One product of ``pinned_refs.products``: the ``ProductInput`` members as computed and,
    when a line of the product was computed, the level-P values of its obligations."""
    pin: dict[str, Any] = {name: getattr(item, name) for name in _PRODUCT_MEMBERS}
    pin["policy_values"] = dict(sorted(item.policy_values.items()))
    pin["assurance_cost_per_unit"] = _pin_text(item.assurance_cost_per_unit)
    pin["components"] = [
        {
            "component_product_code": component.component_product_code,
            "quantity_per_bundle": _pin_text(component.quantity_per_bundle),
            "split_basis": component.split_basis,
            "split_ratio": _pin_text(component.split_ratio),
            "sequence": component.sequence,
            "valid_from": _pin_text(component.valid_from),
            "valid_to": _pin_text(component.valid_to),
        }
        for component in item.components
    ]
    if policies is not None:
        pin[OBLIGATION_POLICIES] = {code: dict(policies[code]) for code in sorted(policies)}
    return pin


def pinned_product(code: str, pin: Mapping[str, Any]) -> ProductInput:
    """The ``ProductInput`` a computation recorded (``product_pin``), member for member."""
    cost = pin["assurance_cost_per_unit"]
    return ProductInput(
        code=code,
        sku_number=pin["sku_number"],
        product_family=pin["product_family"],
        revenue_category=pin["revenue_category"],
        default_template_code=pin["default_template_code"],
        principal_agent=str(pin["principal_agent"]),
        distinctness_default=str(pin["distinctness_default"]),
        unit_of_measure=str(pin["unit_of_measure"]),
        is_bundle=bool(pin["is_bundle"]),
        policy_values={str(key): str(value) for key, value in pin["policy_values"].items()},
        assurance_cost_per_unit=None if cost is None else Decimal(str(cost)),
        components=tuple(
            BundleComponentInput(
                component_product_code=str(component["component_product_code"]),
                quantity_per_bundle=Decimal(str(component["quantity_per_bundle"])),
                split_basis=str(component["split_basis"]),
                split_ratio=(
                    None
                    if component["split_ratio"] is None
                    else Decimal(str(component["split_ratio"]))
                ),
                sequence=int(component["sequence"]),
                valid_from=date.fromisoformat(str(component["valid_from"])),
                valid_to=(
                    None
                    if component["valid_to"] is None
                    else date.fromisoformat(str(component["valid_to"]))
                ),
            )
            for component in pin["components"]
        ),
        is_franchisor_preopening_service=bool(pin["is_franchisor_preopening_service"]),
    )


def _latest_pins(session: Session, group_id: UUID) -> Mapping[str, Any] | None:
    """``pinned_refs.products`` of the group's latest SUCCEEDED computation; None when the group
    has none. A computation that recorded no product answers an empty mapping."""
    refs = session.execute(
        select(contract_computation.c.pinned_refs)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == ComputationStatus.SUCCEEDED.value,
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    ).first()
    if refs is None:
        return None
    found = (refs[0] or {}).get(PRODUCT_PINS)
    return found if isinstance(found, Mapping) else {}


def former_groups(
    session: Session, group_id: UUID, members: Sequence[Mapping[str, Any]]
) -> list[UUID]:
    """The groups the members of ``group_id`` belonged to before (T-CON-04 history), each once:
    the member with the earliest inception date, then external id, first, and within a member
    its most recent former group first — the one order of the pins a group inherits."""
    ordered = sorted(members, key=lambda row: (row["inception_date"], str(row["external_id"])))
    order = {UUID(str(row["id"])): position for position, row in enumerate(ordered)}
    former = session.execute(
        select(
            combination_group_member.c.contract_id,
            combination_group_member.c.combination_group_id,
        )
        .where(
            combination_group_member.c.contract_id.in_(sorted(order)),
            combination_group_member.c.combination_group_id != group_id,
            combination_group_member.c.valid_to_known_at.is_not(None),
        )
        .order_by(
            combination_group_member.c.valid_to_known_at.desc(),
            combination_group_member.c.combination_group_id,
        )
    ).all()
    found: list[UUID] = []
    # ``sorted`` is stable: within a member the most recent former group stays first.
    for row in sorted(former, key=lambda row: order[UUID(str(row.contract_id))]):
        former_id = UUID(str(row.combination_group_id))
        if former_id not in found:
            found.append(former_id)
    return found


class ProductPins:
    """The product pins in force for one group (DG-KRN-REG-02 rev 1.93; 05 RCP-15 rev 1.49).

    ``get`` answers the pin of a product code: that of the group's latest SUCCEEDED computation,
    else — for a product the group has not recorded, as in its first computation after an
    approved combination or uncombination — that of a member's former group, the member with the
    earliest inception date, then external id, first, and its most recent former group first.
    None means the product is not pinned: the builder reads its T-REF-20 row. The former groups
    are read once, and only when a product is missing from the group's own pins."""

    def __init__(
        self, session: Session, group_id: UUID, members: Sequence[Mapping[str, Any]]
    ) -> None:
        self._session = session
        self._group_id = group_id
        self._members = members
        self._own: Mapping[str, Any] = _latest_pins(session, group_id) or {}
        self._former: dict[str, Any] | None = None

    def get(self, code: str) -> Mapping[str, Any] | None:
        pin = self._own.get(code)
        if pin is None:
            pin = self._from_former_groups().get(code)
        return pin if isinstance(pin, Mapping) else None

    def _from_former_groups(self) -> Mapping[str, Any]:
        if self._former is not None:
            return self._former
        found: dict[str, Any] = {}
        for group_id in former_groups(self._session, self._group_id, self._members):
            for code, pin in (_latest_pins(self._session, group_id) or {}).items():
                found.setdefault(str(code), pin)
        self._former = found
        return found


def product_pins(
    session: Session, group_id: UUID, members: Sequence[Mapping[str, Any]]
) -> ProductPins:
    """``ProductPins`` of the group whose members at the bundle's ``known_at`` are ``members``."""
    return ProductPins(session, group_id, members)


def _carried_products(
    bundle: InputBundle, contract_keys: Collection[str]
) -> tuple[set[str], list[tuple[str, Mapping[str, Any]]]]:
    """The product codes the contracts of ``contract_keys`` carry in ``bundle`` — on a line, or
    through a bundle a line names — and every line of the bundle."""
    lines = _lines(bundle.events)
    by_code = {item.code: item for item in bundle.group.products}
    pending = {
        str(line.get("product_code"))
        for contract_key, line in lines
        if contract_key in contract_keys
    }
    carried: set[str] = set()
    while pending:
        code = pending.pop()
        item = by_code.get(code)
        if item is None or code in carried:
            continue
        carried.add(code)
        pending |= {component.component_product_code for component in item.components}
    return carried, lines


def product_pin_members(bundle: InputBundle, output: OutputBundle) -> dict[str, Any]:
    """04 T-CON-07 ``pinned_refs.products`` of the computation of ``bundle`` whose result is
    ``output``: every product carried by a member contract that is past DRAFT in a book, as the
    bundle holds it, with the level-P values of its obligations where a line of it was computed.
    Derived from the bundle alone, so the pin is what was computed (DG-KRN-REG-02 rev 1.93)."""
    past_draft = {
        contract_key
        for book_output in output.books
        for contract_key, status in book_output.status_in_book
        if status not in _UNPINNED_STATUSES
    }
    if not past_draft:
        return {}
    carried, lines = _carried_products(bundle, past_draft)
    by_subject: dict[str, dict[str, Any]] = {}
    for book_input in bundle.books:
        for policy in book_input.policies:
            # Level P only: a level-O row is the obligation's own (the SSP read-back of
            # ``recorded_ssp_versions``), never a value of its product.
            if policy.scope == "OBLIGATION" and policy.level == "P":
                by_subject.setdefault(policy.subject_key, {})[policy.code] = {
                    "value": _json_value(policy.value),
                    "source": policy.source_ref,
                }
    # The level-P values of a product are those of each of its lines (``_policies`` merges the
    # product and its template, never the line): the line with the smallest subject key names them.
    policies: dict[str, Mapping[str, Any]] = {}
    for subject_key, code in sorted(
        (
            obligation_subject_key(contract_key, str(line.get("obligation_key"))),
            str(line.get("product_code")),
        )
        for contract_key, line in lines
    ):
        policies.setdefault(code, by_subject.get(subject_key, {}))
    for book_input in bundle.books:
        for policy in book_input.policies:
            if policy.scope == "PRODUCT" and policy.level == "P":
                policies[policy.subject_key] = {
                    **policies.get(policy.subject_key, {}),
                    policy.code: {"value": _json_value(policy.value), "source": policy.source_ref},
                }
    by_code = {item.code: item for item in bundle.group.products}
    return {code: product_pin(by_code[code], policies.get(code)) for code in sorted(carried)}


def _json_value(value: Any) -> Any:
    """A ``ResolvedPolicyInput.value`` as JSON: a tuple as a list, an object with sorted keys;
    ``_stored_value`` reads both back."""
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return value


def _products(
    session: Session, codes: Iterable[str], *, at: date, pins: ProductPins | None = None
) -> tuple[tuple[ProductInput, ...], dict[str, Mapping[str, Any]]]:
    """The products of ``codes`` and their components, with default template codes. A product
    ``pins`` records is the pinned one, with the components pinned with it (04 T-CON-07
    ``pinned_refs.products``); every other product is its T-REF-20 row. The rows are returned for
    every product that still has one, pinned or not."""
    found: dict[str, ProductInput] = {}
    rows_by_code: dict[str, Mapping[str, Any]] = {}
    pending = set(codes)
    while pending:
        statement = (
            select(product, pob_template.c.code.label("template_code"))
            .select_from(
                product.outerjoin(
                    pob_template,
                    and_(
                        pob_template.c.tenant_id == product.c.tenant_id,
                        pob_template.c.id == product.c.default_pob_template_id,
                    ),
                )
            )
            .where(product.c.code.in_(sorted(pending)))
        )
        wanted, pending = pending, set()
        live = {str(row["code"]): row for row in session.execute(statement).mappings()}
        for code in sorted(wanted):
            pin = None if pins is None else pins.get(code)
            row = live.get(code)
            if pin is not None:
                found[code] = pinned_product(code, pin)
            elif row is not None:
                found[code] = ProductInput(
                    code=code,
                    sku_number=row["sku_number"],
                    product_family=row["product_family"],
                    revenue_category=row["revenue_category"],
                    default_template_code=row["template_code"],
                    principal_agent=str(row["principal_agent"]),
                    distinctness_default=str(row["distinctness_default"]),
                    unit_of_measure=str(row["unit_of_measure"]),
                    is_bundle=bool(row["is_bundle"]),
                    policy_values=_flat_values(row["policy_values"]),
                    assurance_cost_per_unit=row["assurance_cost_per_unit"],
                    components=product_rules.bundle_components(session, row["id"], at=at),
                    is_franchisor_preopening_service=bool(row["is_franchisor_preopening_service"]),
                )
            else:
                continue
            if row is not None:
                rows_by_code[code] = dict(row)
            pending |= {c.component_product_code for c in found[code].components} - set(found)
    return tuple(found[code] for code in sorted(found)), rows_by_code


def _stated_from(session: Session, entity_ids: Sequence[UUID]) -> dict[UUID, date]:
    """Per entity, the start of the first period from which every book it keeps has a state: the
    latest first-period start among its enabled books (04 T-REF-03; ``period_state`` rows exist from
    a book's first period on, T-REF-06). An entity that keeps no enabled book has no entry."""
    joined = entity_book.join(
        book,
        and_(book.c.tenant_id == entity_book.c.tenant_id, book.c.code == entity_book.c.book_code),
    ).join(
        period,
        and_(
            period.c.tenant_id == entity_book.c.tenant_id,
            period.c.id == entity_book.c.first_period_id,
        ),
    )
    rows = session.execute(
        select(entity_book.c.entity_id, func.max(period.c.start_date))
        .select_from(joined)
        .where(
            entity_book.c.entity_id.in_(entity_ids),
            entity_book.c.is_enabled.is_(True),
            book.c.is_enabled.is_(True),
        )
        .group_by(entity_book.c.entity_id)
    )
    return {UUID(str(entity_id)): start for entity_id, start in rows}


def handed_states(
    found: Iterable[tuple[str, str]], primary_book: str | None
) -> tuple[tuple[str, str], ...]:
    """The (book, state) pairs of one period as the engine is handed them, in book order (05
    RCP-15 rev 1.94; supervisor rulings R-112 (e) and R-114 (d)). The LEGACY book has no close of
    its own and follows the primary book's (04 T-REF-06 and DB-07 rev 1.155): where the primary
    book's state is not postable and the LEGACY row's is, the LEGACY state handed is the
    primary's. The DB-07 guard refuses a LEGACY line there; handed the primary's state, the engine
    assigns the amount to the first later period postable in both books (ENGINE_SPEC S08-R-08).
    Every other state is handed as stored. Pure."""
    by_book = dict(found)
    followed = None if primary_book is None else by_book.get(primary_book)
    if (
        primary_book != LEGACY_BOOK
        and by_book.get(LEGACY_BOOK) in POSTABLE
        and followed is not None
        and followed not in POSTABLE
    ):
        by_book[LEGACY_BOOK] = followed
    return tuple(sorted(by_book.items()))


def _entities(
    session: Session, entity_ids: Iterable[UUID], inception: date
) -> tuple[tuple[EntityInput, ...], dict[str, Mapping[str, Any]]]:
    """The entities with the periods the fold needs (05 RCP-15): the calendar from the period
    containing ``inception``, the group's inception date, on (ENGINE_SPEC §0.4, CV-12; 05 RCP-03),
    preceded by the earlier periods for which every book the entity keeps has a state. A period
    before the inception that precedes a kept book's first period carries no state for that book
    (04 T-REF-03), and the engine refuses a period it is handed without one (CV-13), so it is not
    loaded. The LEGACY book's states are handed as ``handed_states`` decides (RCP-15 rev 1.94)."""
    wanted = sorted(set(entity_ids))
    stated_from = _stated_from(session, wanted)
    primary_book = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    primary_code = None if primary_book is None else str(primary_book)
    joined = legal_entity.join(
        fiscal_calendar,
        and_(
            fiscal_calendar.c.tenant_id == legal_entity.c.tenant_id,
            fiscal_calendar.c.id == legal_entity.c.calendar_id,
        ),
    )
    rows = [
        dict(row)
        for row in session.execute(
            select(legal_entity, fiscal_calendar.c.pattern.label("calendar_pattern"))
            .select_from(joined)
            .where(legal_entity.c.id.in_(wanted))
            .order_by(legal_entity.c.code)
        ).mappings()
    ]
    states: dict[tuple[UUID, UUID], list[tuple[str, str]]] = {}
    for entity_id, book_code, period_id, state in session.execute(
        select(
            period_state.c.entity_id,
            period_state.c.book_code,
            period_state.c.period_id,
            period_state.c.state,
        ).where(period_state.c.entity_id.in_(wanted))
    ):
        states.setdefault((UUID(str(entity_id)), UUID(str(period_id))), []).append(
            (str(book_code), str(state))
        )
    found: list[EntityInput] = []
    for row in rows:
        entity_id = UUID(str(row["id"]))
        loaded = select(period).where(period.c.calendar_id == row["calendar_id"])
        if entity_id in stated_from:
            loaded = loaded.where(
                or_(
                    period.c.end_date >= inception,
                    period.c.start_date >= stated_from[entity_id],
                )
            )
        periods = session.execute(loaded.order_by(period.c.start_date)).mappings()
        found.append(
            EntityInput(
                code=str(row["code"]),
                functional_currency=str(row["functional_currency"]).strip(),
                time_zone=str(row["time_zone"]),
                calendar_pattern=str(row["calendar_pattern"]),
                periods=tuple(
                    PeriodInput(
                        period_key=str(item["period_key"]),
                        fiscal_year=int(item["fiscal_year"]),
                        period_no=int(item["period_no"]),
                        start_date=item["start_date"],
                        end_date=item["end_date"],
                        states=handed_states(
                            states.get((entity_id, UUID(str(item["id"]))), ()), primary_code
                        ),
                    )
                    for item in periods
                ),
            )
        )
    return tuple(found), {str(row["code"]): row for row in rows}


def _rule_in_bundle(
    rule: Mapping[str, Any], entity_codes: Mapping[UUID, str], product_codes: Mapping[UUID, str]
) -> bool:
    """Whether a T-REF-15 rule can match a line of the group: the entity it names, when it names
    one, is an entity of the bundle, and the product it names a product of the bundle."""
    return (rule["entity_id"] is None or UUID(str(rule["entity_id"])) in entity_codes) and (
        rule["product_id"] is None or UUID(str(rule["product_id"])) in product_codes
    )


def _account_mapping(
    session: Session,
    known_at: datetime,
    entity_codes: Mapping[UUID, str],
    product_codes: Mapping[UUID, str],
) -> AccountMappingInput:
    """The PUBLISHED mapping version in force and the rules of it that can match a line of the
    group (04 T-REF-14, T-REF-15; 05 RCP-15 rev 1.168; item MAP-RULE-FOREIGN-1, supervisor ruling of
    2026-10-01). ``entity_codes`` and ``product_codes`` are the entities and the products the
    bundle holds, by id. A rule written for a product or for an entity the bundle does not hold is
    left out. The engine knows a rule's product and entity by their codes (ENGINE_SPEC S14-R-14),
    and a rule handed over without the condition it was written with stands for every product, or
    every entity, at its stored specificity: it took the account from the rule written for the
    line. The version key and the content hash stay those of the whole version."""
    found = mapping.published_version_at(session, known_at)
    if found is None:
        return AccountMappingInput(NO_MAPPING_KEY, ZERO_SHA256, ())
    version = session.execute(
        select(
            account_mapping_version.c.name,
            account_mapping_version.c.version_no,
            account_mapping_version.c.content_sha256,
        ).where(account_mapping_version.c.id == found["id"])
    ).one()
    rules = [
        MappingRuleInput(
            account_role=str(rule["account_role"]),
            clearing_purpose=None
            if rule["clearing_purpose"] is None
            else str(rule["clearing_purpose"]),
            entity_code=None
            if rule["entity_id"] is None
            else entity_codes[UUID(str(rule["entity_id"]))],
            book_code=None if rule["book_code"] is None else str(rule["book_code"]),
            product_code=None
            if rule["product_id"] is None
            else product_codes[UUID(str(rule["product_id"]))],
            revenue_category=rule["revenue_category"],
            account_code=str(rule["gl_account_code"]),
            default_dimensions={
                str(k): str(v) for k, v in sorted(dict(rule["default_dimensions"]).items())
            },
            priority=int(rule["priority"]),
            specificity=int(rule["specificity"]),
        )
        for rule in mapping.rule_rows(session, found["id"])
        if _rule_in_bundle(rule, entity_codes, product_codes)
    ]
    rules.sort(
        key=lambda r: (
            r.account_role,
            r.clearing_purpose or "",
            -r.specificity,
            -r.priority,
            r.account_code,
        )
    )
    return AccountMappingInput(
        mapping_version_key(str(version.name), int(version.version_no)),
        version.content_sha256 or ZERO_SHA256,
        tuple(rules),
    )


def mapping_version_key(name: str, version_no: int) -> str:
    return f"{name}@v{version_no}"


def fx_version_key(code: str, version_no: int) -> str:
    return f"{code}@v{version_no}"


def _fx_rates(
    session: Session, currencies: Iterable[str], known_at: datetime | None
) -> tuple[FxRateInput, ...]:
    return tuple(rate for rate, _ in _fx_rate_rows(session, currencies, known_at))


def fx_rate_ids(session: Session, bundle: InputBundle) -> Mapping[str, tuple[UUID, UUID, Decimal]]:
    """D-88 L7-6-Q-1: per rate key of ``bundle``, (``fx_rate.id``, ``fx_rate_set_version.id``,
    rate) from the ``_fx_rates`` rows the build read (the bundle's currencies at ``known_at``)."""
    keys = {rate.rate_key for rate in bundle.fx_rates}
    return MappingProxyType(
        {
            rate.rate_key: ids
            for rate, ids in _fx_rate_rows(session, bundle.currencies, bundle.known_at)
            if rate.rate_key in keys
        }
    )


def _fx_rate_key(
    code: object, version_no: object, rate_type: object, base: object, quote: object, on: date
) -> tuple[str, str]:
    """(``rate_key``, ``version_key``): the natural keys of a rate row (REQ-FX-006)."""
    version_key = fx_version_key(str(code), int(str(version_no)))
    return (
        f"{version_key}/{rate_type}/{str(base).strip()}/{str(quote).strip()}/{on.isoformat()}",
        version_key,
    )


def posted_rate_rows(
    session: Session, contract_ids: Collection[UUID]
) -> Mapping[str, tuple[str, date, tuple[UUID, UUID, Decimal]]]:
    """ENGINE_SPEC_B S14-R-28: per rate key, (version key, effective date, (``fx_rate.id``,
    ``fx_rate_set_version.id``, rate)) of every rate row stamped on a sealed line of the member
    contracts — whatever its version's status today, because a line keeps the rate it was posted
    with when a later version supersedes it. ``_posted`` names them as ``rate_refs``, and
    ``computation._post_book`` stamps a line that reverses posted amounts from them."""
    if not contract_ids:
        return MappingProxyType({})
    stamped = (
        select(subledger_line.c.fx_rate_id)
        .where(
            subledger_line.c.contract_id.in_(sorted(contract_ids)),
            subledger_line.c.fx_rate_id.is_not(None),
        )
        .distinct()
    )
    rows = session.execute(
        select(
            fx_rate.c.id,
            fx_rate_set_version.c.id,
            fx_rate_set.c.code,
            fx_rate_set_version.c.version_no,
            fx_rate.c.rate_type,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            fx_rate.c.rate,
        )
        .select_from(
            fx_rate.join(
                fx_rate_set_version,
                and_(
                    fx_rate_set_version.c.tenant_id == fx_rate.c.tenant_id,
                    fx_rate_set_version.c.id == fx_rate.c.fx_rate_set_version_id,
                ),
            ).join(
                fx_rate_set,
                and_(
                    fx_rate_set.c.tenant_id == fx_rate_set_version.c.tenant_id,
                    fx_rate_set.c.id == fx_rate_set_version.c.fx_rate_set_id,
                ),
            )
        )
        .where(fx_rate.c.id.in_(stamped))
    )
    found: dict[str, tuple[str, date, tuple[UUID, UUID, Decimal]]] = {}
    for rate_id, version_id, code, no, rate_type, base, quote, effective, rate in rows:
        rate_key, version_key = _fx_rate_key(code, no, rate_type, base, quote, effective)
        found[rate_key] = (
            version_key,
            effective,
            (UUID(str(rate_id)), UUID(str(version_id)), Decimal(rate)),
        )
    return MappingProxyType(dict(sorted(found.items())))


def fx_rates_in_force(known_at: datetime | None, *, without: UUID | None = None) -> Select[Any]:
    """The rate rows in force at ``known_at`` — THE admission of a rate into a bundle, as a
    statement: one function for every reader. ``_fx_rate_rows`` reads a bundle's rates through it
    (the rows of the bundle's currencies), ``close.run_inputs`` digests through it what a close
    run's passes could read, and ``close.rate_changes`` states through it what the approval of a
    version changes (item CLO-RATE-AFTER-RUN-1; 04 T-CLS-01 "What a run read" and T-REF-11 "A rate
    changed after a lock", rev 1.291) — a reader with an admission of its own would drift from
    what a pass reads.

    D-87 L6-5-Q-23: only the versions in force at ``known_at``. A version counts when it is
    APPROVED or SUPERSEDED and published by ``known_at``; for each (set, rate type, pair, date or
    period) the highest such version whose coverage contains the date answers, so a version
    superseded by a version published by ``known_at`` is left out, and S12-R-01 keeps failing
    closed.

    ``known_at`` None: whenever a version was published — every APPROVED or SUPERSEDED version
    the statement can see counts. A control that asks what is in force NOW reads so: a version's
    ``published_at`` is the instant its approval BEGAN, on the application clock, and a reader
    whose transaction began before that instant, or whose clock is behind it, would not admit a
    version that is committed and in force for every later reader.

    ``without``: the same rows as if that version did not exist — it neither answers nor
    supersedes. The rows with a version against the rows without it are what its approval
    changes."""

    def counts(version: Any) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [version.c.status.in_(_FX_IN_FORCE)]
        if known_at is not None:
            conditions.append(version.c.published_at <= known_at)
        if without is not None:
            conditions.append(version.c.id != without)
        return conditions

    joined = (
        fx_rate.join(
            fx_rate_set_version,
            and_(
                fx_rate_set_version.c.tenant_id == fx_rate.c.tenant_id,
                fx_rate_set_version.c.id == fx_rate.c.fx_rate_set_version_id,
            ),
        )
        .join(
            fx_rate_set,
            and_(
                fx_rate_set.c.tenant_id == fx_rate_set_version.c.tenant_id,
                fx_rate_set.c.id == fx_rate_set_version.c.fx_rate_set_id,
            ),
        )
        .outerjoin(
            period,
            and_(period.c.tenant_id == fx_rate.c.tenant_id, period.c.id == fx_rate.c.period_id),
        )
    )
    later = fx_rate_set_version.alias("later_version")
    superseded = exists().where(
        later.c.tenant_id == fx_rate_set_version.c.tenant_id,
        later.c.fx_rate_set_id == fx_rate_set_version.c.fx_rate_set_id,
        *counts(later),
        later.c.version_no > fx_rate_set_version.c.version_no,
        later.c.coverage_from <= fx_rate.c.effective_date,
        later.c.coverage_to >= fx_rate.c.effective_date,
    )
    return (
        select(
            fx_rate.c.id,
            fx_rate_set_version.c.id.label("fx_rate_set_version_id"),
            fx_rate_set.c.code,
            fx_rate_set_version.c.version_no,
            fx_rate.c.rate_type,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            period.c.period_key,
            fx_rate.c.rate,
        )
        .select_from(joined)
        .where(
            *counts(fx_rate_set_version),
            fx_rate_set_version.c.coverage_from <= fx_rate.c.effective_date,
            fx_rate_set_version.c.coverage_to >= fx_rate.c.effective_date,
            ~superseded,
        )
    )


def _fx_rate_rows(
    session: Session, currencies: Iterable[str], known_at: datetime | None
) -> tuple[tuple[FxRateInput, tuple[UUID, UUID, Decimal]], ...]:
    codes = sorted(set(currencies))
    if len(codes) < 2:
        return ()
    rows = session.execute(
        fx_rates_in_force(known_at).where(
            fx_rate.c.base_currency.in_(codes), fx_rate.c.quote_currency.in_(codes)
        )
    )
    found: list[tuple[FxRateInput, tuple[UUID, UUID, Decimal]]] = []
    for rate_id, version_id, code, no, rate_type, base, quote, effective, period_key, rate in rows:
        rate_key, version_key = _fx_rate_key(code, no, rate_type, base, quote, effective)
        pinned = FxRateInput(
            rate_key=rate_key,
            version_key=version_key,
            rate_type=str(rate_type),
            base_currency=str(base).strip(),
            quote_currency=str(quote).strip(),
            effective_date=effective,
            period_key=None if period_key is None else str(period_key),
            rate=Decimal(rate),
        )
        found.append((pinned, (UUID(str(rate_id)), UUID(str(version_id)), Decimal(rate))))
    return tuple(
        sorted(
            found,
            key=lambda item: (
                item[0].rate_type,
                item[0].base_currency,
                item[0].quote_currency,
                item[0].effective_date,
                item[0].version_key,
            ),
        )
    )


def previous_version(session: Session, group_id: UUID, book_code: str) -> dict[str, Any] | None:
    """The latest contract version of the group in the book."""
    row = (
        session.execute(
            select(contract_version)
            .where(
                contract_version.c.combination_group_id == group_id,
                contract_version.c.book_code == book_code,
            )
            .order_by(contract_version.c.version_no.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def former_pinned_policies(
    session: Session, group_id: UUID, book_code: str, members: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    """Pin K of a group's FIRST version in a book (DG-KRN-REG-02; item PIN-K-COMBINATION-1,
    supervisor ruling R-112 (i)): the ``pinned_policies`` of the latest version, in the book, of
    the first former group of its members that has one (``former_groups``) — after an approved
    combination, those of the member with the earliest inception date, then external id. None
    when no member was computed in the book before: every parameter then resolves at this
    computation, as does any parameter the inherited pin does not hold (``_policies``)."""
    for former_id in former_groups(session, group_id, members):
        previous = previous_version(session, former_id, book_code)
        if previous is not None:
            pinned: Mapping[str, Any] = previous["pinned_policies"]
            return pinned
    return None


SSP_VERSION_BASIS: Final = "ssp.version_basis"  # POL-070: T, override O; pin K
RECORDED_VERSION: Final = "recorded"  # ENGINE_SPEC S05-R-03: the member of a read-back value
RECORDED_SOURCE: Final = "RECORDED"  # the source reference of a read-back row
SSP_WEIGHTS: Final = "ssp_weights"  # 04 T-CON-07 ``pinned_refs`` member (``ssp_weight_members``)
_WEIGHT_MEASURE: Final = "mod_weight@"  # ENGINE_SPEC S06-R-11: the measure before its event key
# The ``ssp_entry`` members of a weight that price an obligation which existed before the event:
# its remaining units and the units added to it. ``added`` (an obligation the event adds) is the
# obligation's own pricing; ``corrected`` and ``inception`` belong to a correction (S06-R-26).
_WEIGHED_PARTS: Final = ("remaining", "added:")
ACTIVATED_EVENT: Final = ContractEventType.CONTRACT_ACTIVATED.value


def _activation_gates(stored: Sequence[Mapping[str, Any]]) -> dict[UUID, int]:
    """Per contract, the stream version of its first ``CONTRACT_ACTIVATED``: the gate behind which
    its computations are no longer provisional (ENGINE_SPEC S02-R-02). A contract still ``DRAFT``
    has none."""
    found: dict[UUID, int] = {}
    for row in stored:
        if str(row["event_type"]) == ACTIVATED_EVENT:
            contract_id, version = UUID(str(row["contract_id"])), int(row["stream_version"])
            found[contract_id] = min(found.get(contract_id, version), version)
    return found


def _behind_the_gate(
    session: Session,
    version: Mapping[str, Any],
    contract_ids: Collection[UUID],
    gates: Mapping[UUID, int],
) -> tuple[set[UUID], Mapping[str, Any]]:
    """The contracts of ``contract_ids`` that the computation behind the contract version
    ``version`` computed with their activation included, and that computation's ``pinned_refs``.
    The computation of a contract still ``DRAFT`` is provisional and posts nothing (ENGINE_SPEC
    S02-R-02): it records no pricing to read back, so the SSP version in force reaches a draft
    until it is activated — as a repaired product does (REQ-REF-014; ``product_pin_members``)."""
    row = session.execute(
        select(contract_computation.c.stream_heads, contract_computation.c.pinned_refs).where(
            contract_computation.c.id == version["contract_computation_id"]
        )
    ).one()
    heads = dict(row.stream_heads or {})
    past = {
        contract_id
        for contract_id in contract_ids
        if contract_id in gates and int(heads.get(str(contract_id), 0)) >= gates[contract_id]
    }
    return past, dict(row.pinned_refs or {})


def _version_naming(stored: Sequence[Mapping[str, Any]]) -> dict[tuple[UUID, str], int]:
    """Per (contract, obligation key), the stream version of the first stored
    ``LINE_ATTRIBUTES_CHANGED`` that names an SSP version, by id (an approved ``SSP_OVERRIDE``) or
    by label: the correction of the version an obligation was priced from (S06-R-26)."""
    found: dict[tuple[UUID, str], int] = {}
    for row in stored:
        payload = row["payload"]
        if str(row["event_type"]) != ATTRIBUTES_EVENT or not isinstance(payload, Mapping):
            continue
        changes = payload.get("changes")
        if not isinstance(changes, Mapping) or (
            changes.get("ssp_book_version_id") is None and changes.get("ssp_version_label") is None
        ):
            continue
        key = (UUID(str(row["contract_id"])), str(payload.get("obligation_key")))
        version = int(row["stream_version"])
        found[key] = min(found.get(key, version), version)
    return found


def _priced_from(
    session: Session, contract_version_id: UUID, contract_ids: Collection[UUID]
) -> dict[tuple[UUID, str], UUID | None]:
    """``ssp_book_version_id`` of the obligations of ``contract_ids`` at one contract version."""
    version = obligation_version
    return {
        (UUID(str(row.contract_id)), str(row.obligation_key)): row.ssp_book_version_id
        for row in session.execute(
            select(
                version.c.contract_id, version.c.obligation_key, version.c.ssp_book_version_id
            ).where(
                version.c.contract_version_id == contract_version_id,
                version.c.contract_id.in_(sorted(contract_ids)),
            )
        )
    }


def _priced_before(
    session: Session,
    contract_id: UUID,
    obligation_key: str,
    book_code: str,
    *,
    gate: int,
    stream_version: int,
) -> UUID | None:
    """``ssp_book_version_id`` of the obligation at its latest version, in any group, whose
    computation ended behind the contract's activation (``gate``) and below ``stream_version`` of
    its stream: the version it was priced from before the event of that stream version."""
    version, computed = obligation_version, contract_computation
    joined = version.join(
        contract_version,
        and_(
            contract_version.c.tenant_id == version.c.tenant_id,
            contract_version.c.id == version.c.contract_version_id,
        ),
    ).join(
        computed,
        and_(
            computed.c.tenant_id == contract_version.c.tenant_id,
            computed.c.id == contract_version.c.contract_computation_id,
        ),
    )
    found: UUID | None = session.execute(
        select(version.c.ssp_book_version_id)
        .select_from(joined)
        .where(
            version.c.contract_id == contract_id,
            version.c.obligation_key == obligation_key,
            version.c.book_code == book_code,
            computed.c.stream_heads[str(contract_id)].as_integer() >= gate,
            computed.c.stream_heads[str(contract_id)].as_integer() < stream_version,
        )
        .order_by(contract_version.c.known_at.desc(), contract_version.c.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    return found


def _former_groups_of(
    session: Session, group_id: UUID, contract_ids: Collection[UUID]
) -> dict[UUID, list[UUID]]:
    """Per contract, the groups it belonged to before ``group_id``, the most recent first."""
    member = combination_group_member
    found: dict[UUID, list[UUID]] = {}
    for row in session.execute(
        select(member.c.contract_id, member.c.combination_group_id)
        .where(
            member.c.contract_id.in_(sorted(contract_ids)),
            member.c.combination_group_id != group_id,
            member.c.valid_to_known_at.is_not(None),
        )
        .order_by(member.c.valid_to_known_at.desc(), member.c.combination_group_id)
    ):
        groups = found.setdefault(UUID(str(row.contract_id)), [])
        former_id = UUID(str(row.combination_group_id))
        if former_id not in groups:
            groups.append(former_id)
    return found


def _recorded_weights(
    book_code: str,
    sources: Sequence[tuple[Collection[UUID], Mapping[str, Any]]],
    external_ids: Mapping[UUID, str],
    stored: Sequence[Mapping[str, Any]],
    obligations: Sequence[Mapping[str, Any]],
    version_keys: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """Per obligation subject key, the members ``recorded@<event key>`` of its read-back value:
    ``pinned_refs.ssp_weights`` of the book (``ssp_weight_members``) in ``sources`` — each the
    contracts a computation speaks for with its ``pinned_refs``, an earlier source winning —
    under the keys of the bundle being built. A record whose event or version the bundle does not
    hold is left out."""
    subjects = {
        str(row["id"]): (
            UUID(str(row["contract_id"])),
            obligation_subject_key(
                external_ids[UUID(str(row["contract_id"]))], str(row["obligation_key"])
            ),
        )
        for row in obligations
    }
    event_keys = {
        str(row["id"]): _event_key(
            external_ids[UUID(str(row["contract_id"]))], int(row["stream_version"])
        )
        for row in stored
    }
    found: dict[str, dict[str, str]] = {}
    for contract_ids, refs in sources:
        by_event = (refs.get(SSP_WEIGHTS) or {}).get(book_code) or {}
        for event_id, by_obligation in by_event.items():
            event_key = event_keys.get(str(event_id))
            for obligation_id, weighed_from in by_obligation.items():
                subject = subjects.get(str(obligation_id))
                version_key = version_keys.get(str(weighed_from))
                if event_key is None or version_key is None or subject is None:
                    continue
                if subject[0] in contract_ids:
                    member = f"{RECORDED_VERSION}@{event_key}"
                    found.setdefault(subject[1], {}).setdefault(member, version_key)
    return found


def recorded_ssp_versions(
    session: Session,
    group_id: UUID,
    book_code: str,
    previous: Mapping[str, Any] | None,
    members: Sequence[Mapping[str, Any]],
    stored: Sequence[Mapping[str, Any]],
    obligations: Sequence[Mapping[str, Any]],
    version_keys: Mapping[str, str],
) -> dict[str, dict[str, str]]:
    """The SSP read-back of one book (05 RCP-15; ENGINE_SPEC S05-R-03, S06-R-11; POLICIES POL-070;
    item PIN-READBACK-1, supervisor ruling R-116 (d)): per obligation subject key, the read-back
    value — ``recorded``, the key of the SSP book version the obligation's own pricing was made
    from, and ``recorded@<event key>``, that of its weight in each modification event.

    The own pricing is the version recorded on the obligation (04 T-CON-11
    ``ssp_book_version_id``) at the latest version of the group in the book, and the weights are
    those its computation recorded (04 T-CON-07 ``pinned_refs.ssp_weights``). A member the group
    has not computed yet — after an approved combination, or a contract that joined — is read at
    the latest version of its most recent former group that has one, so the record follows the
    obligation, not the group. Only a computation that included the contract's activation is
    read (``_behind_the_gate``): what was computed for a contract still ``DRAFT`` is provisional.
    An obligation whose stream holds a ``LINE_ATTRIBUTES_CHANGED`` that names a version is read
    BEFORE the first such event: the event corrects the pricing at its own place in the stream
    (S06-R-26), and the corrected version must not price the inception a second time. A pricing
    without a record, or whose version is no longer among the approved ones, has no member and
    selects by date as a first pricing does."""
    external_ids = {UUID(str(row["id"])): str(row["external_id"]) for row in members}
    gates = _activation_gates(stored)
    found: dict[tuple[UUID, str], UUID | None] = {}
    sources: list[tuple[Collection[UUID], Mapping[str, Any]]] = []
    computed_here: set[UUID] = set()
    if previous is not None:
        priced = _priced_from(session, UUID(str(previous["id"])), external_ids)
        computed_here = {contract_id for contract_id, _ in priced}
        past, refs = _behind_the_gate(session, previous, computed_here, gates)
        found.update({key: value for key, value in priced.items() if key[0] in past})
        sources.append((past, refs))
    missing = [contract_id for contract_id in external_ids if contract_id not in computed_here]
    if missing:
        for contract_id, former_ids in _former_groups_of(session, group_id, missing).items():
            for former_id in former_ids:
                former = previous_version(session, former_id, book_code)
                if former is not None:
                    past, refs = _behind_the_gate(session, former, [contract_id], gates)
                    if past:
                        found.update(_priced_from(session, UUID(str(former["id"])), past))
                        sources.append((past, refs))
                    break
    for (contract_id, obligation_key), stream_version in _version_naming(stored).items():
        if (contract_id, obligation_key) in found:
            found[(contract_id, obligation_key)] = _priced_before(
                session,
                contract_id,
                obligation_key,
                book_code,
                gate=gates[contract_id],
                stream_version=stream_version,
            )
    recorded: dict[str, dict[str, str]] = {}
    for (contract_id, obligation_key), version_id in found.items():
        version_key = None if version_id is None else version_keys.get(str(version_id))
        if version_key is not None:
            subject_key = obligation_subject_key(external_ids[contract_id], obligation_key)
            recorded.setdefault(subject_key, {})[RECORDED_VERSION] = version_key
    weights = _recorded_weights(book_code, sources, external_ids, stored, obligations, version_keys)
    for subject_key, weighed in weights.items():
        recorded.setdefault(subject_key, {}).update(weighed)
    return recorded


def ssp_weight_members(
    bundle: InputBundle, found: BundleIndex, output: OutputBundle
) -> dict[str, dict[str, dict[str, str]]]:
    """04 T-CON-07 ``pinned_refs.ssp_weights`` of the computation of ``bundle`` whose result is
    ``output``: per book, modification event id and obligation id, the id of the SSP book version
    the obligation's weight in that event was priced from (ENGINE_SPEC S06-R-11) — read from the
    ``ssp_entry`` sources of the event's ``mod_weight@<event key>`` nodes, so the record is what
    was computed. Only an obligation that existed before the event has one: an obligation the
    event adds is priced for itself, and T-CON-11 records that version. A weight priced from no
    entry, or from entries of more than one version, has none and is selected by date again.
    ``recorded_ssp_versions`` hands the record to the next computation of the event, so a version
    approved afterwards does not weigh an applied modification a second time."""
    version_keys = {
        entry.entry_key: version.version_key
        for version in bundle.ssp_versions
        for entry in version.entries
    }
    event_ids = {
        event.event_key: found.events.get((event.contract_key, event.stream_version))
        for event in bundle.events
    }
    record: dict[str, dict[str, dict[str, str]]] = {}
    for book_output in output.books:
        by_event: dict[str, dict[str, str]] = {}
        for node in book_output.trace.nodes:
            if not node.measure.startswith(_WEIGHT_MEASURE):
                continue
            event_id = event_ids.get(node.measure.removeprefix(_WEIGHT_MEASURE))
            row = found.obligations.get(node.id[len(node.measure) + 1 : -len(":-")])
            priced_from = {
                version_keys.get(source.ref_id)
                for source in node.inputs
                if isinstance(source, SourceRef)
                and source.ref_type == "ssp_entry"
                and source.detail.get("member", "").startswith(_WEIGHED_PARTS)
            }
            if event_id is None or row is None or len(priced_from) != 1:
                continue
            (version_key,) = priced_from
            if version_key is not None:
                by_event.setdefault(str(event_id), {})[str(row["id"])] = str(
                    found.ssp_versions[version_key]
                )
        if by_event:
            record[book_output.book_code] = {
                event_id: dict(sorted(by_obligation.items()))
                for event_id, by_obligation in sorted(by_event.items())
            }
    return record


def _previous_heads(
    session: Session, group_id: UUID, external_ids: Mapping[UUID, str]
) -> tuple[tuple[str, int], ...]:
    heads = session.execute(
        select(contract_computation.c.stream_heads)
        .where(
            contract_computation.c.combination_group_id == group_id,
            contract_computation.c.status == ComputationStatus.SUCCEEDED.value,
        )
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if heads is None:
        return ()
    return tuple(
        sorted(
            (external_ids[UUID(str(contract_id))], int(version))
            for contract_id, version in dict(heads).items()
            if UUID(str(contract_id)) in external_ids
        )
    )


def _policy(
    code: str, scope: str, subject_key: str, value: Any, level: str, source: str, pin: str
) -> ResolvedPolicyInput:
    return ResolvedPolicyInput(code, scope, subject_key, value, level, source, pin)


def _stored_value(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in sorted(value.items())}
    return value


ONBOARDING_METHOD: Final = "onboarding.method"  # POL-210
OPENING_BALANCES_AT_CUTOVER: Final = "OPENING_BALANCES_AT_CUTOVER"
LEGACY_MIGRATION: Final = "LEGACY_MIGRATION"  # E-03 opening-balance reason of D-31 mode (a)


def onboarding_pins(events: Sequence[EventInput]) -> dict[str, str]:
    """05 RCP-15 rev 1.36 (DG-KRN-REG-03; FLMG-ONBOARDING-METHOD-PIN-1): the contracts a D-31 mode
    (a) migration opened — those whose OWN stream carries ``OPENING_BALANCE_ESTABLISHED`` with
    reason ``LEGACY_MIGRATION`` (ENGINE_SPEC S07-R-11) — by external id, each with the key of that
    event as its source reference. POL-210 names their method itself ("legacy database import per
    D-31: mode (a) ``OPENING_BALANCES_AT_CUTOVER``") and ENGINE_SPEC §7.1 its level ("pinned from
    the import batch onto the contract, level C"); the registry has no level for an import batch
    and answers the framework default ``RECOMPUTE_FROM_INCEPTION``, under which the imported
    balances are ignored (WLD-F-15 Contract 1: revenue 0.00 instead of PRD WLD-X-27's 295.69).
    Only the immutable event is read — never the ``migration_batch`` row — so a replay that
    includes the event resolves the same value."""
    found: dict[str, str] = {}
    for event in events:
        if (
            event.event_type == ContractEventType.OPENING_BALANCE_ESTABLISHED.value
            and event.payload.get("reason") == LEGACY_MIGRATION
        ):
            found.setdefault(event.contract_key, event.event_key)
    return found


def period_end_instant(end_date: date, time_zone: str) -> datetime:
    """The last instant of a period that ends on ``end_date`` in the entity's time zone: one
    microsecond before the next local midnight, in UTC."""
    midnight = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=ZoneInfo(time_zone))
    return midnight.astimezone(UTC) - timedelta(microseconds=1)


def _period_rows(
    code: str,
    *,
    book_code: str,
    entities: Sequence[EntityInput],
    entity_ids: Mapping[str, UUID],
    versions: Sequence[Mapping[str, Any]],
    known_at: datetime,
) -> list[ResolvedPolicyInput]:
    """05 RCP-15 (item PINP-PERIOD-VALUE-1): the PERIOD rows of a period-pinned parameter, one per
    entity and period. A period's row carries the value in force FOR ITS ENTITY at the earlier of
    ``known_at`` and the period's last instant in the entity's time zone, among the versions
    published at or before ``known_at`` (``versions``; POLICIES §0.5 rule 3). A value that takes
    effect at a later date therefore never reaches a period that ended before it, and an entity's
    own version answers for that entity's periods only. A period for which no version holds a
    value and the framework has no default carries no row."""
    spec = POLICY_PARAMETERS[code]
    rows: list[ResolvedPolicyInput] = []
    for entity in entities:
        answers: dict[datetime, registry.ResolvedValue] = {}
        for item in entity.periods:
            at = min(known_at, period_end_instant(item.end_date, entity.time_zone))
            found = answers.get(at)
            if found is None:
                found = answers[at] = registry.resolve_among(
                    versions,
                    code,
                    book_code=BookCode(book_code),
                    entity_id=entity_ids.get(entity.code),
                    at=at,
                )
            if found.value is None:
                continue
            source = spec.source_ref if found.source_id is None else str(found.source_id)
            rows.append(
                _policy(
                    code,
                    "PERIOD",
                    f"{entity.code}@{item.period_key}",
                    engine_policy_value(found.value),
                    found.level,
                    source,
                    "P",
                )
            )
    return rows


def _policies(
    session: Session,
    *,
    book_code: str,
    entity_id: UUID | None,
    entities: Sequence[EntityInput],
    known_at: datetime,
    pinned: Mapping[str, Any] | None,
    lines: Sequence[tuple[str, Mapping[str, Any]]],
    product_rows: Mapping[str, Mapping[str, Any]],
    template_values: Mapping[str, Mapping[str, Any]],
    onboarding: Mapping[str, str] | None = None,
    pins: ProductPins | None = None,
    recorded: Mapping[str, Mapping[str, str]] | None = None,
    entity_ids: Mapping[str, UUID] | None = None,
    known: Sequence[Mapping[str, Any]] | None = None,
    overrides: Sequence[ResolvedPolicyInput] = (),
) -> tuple[ResolvedPolicyInput, ...]:
    """The resolved parameters of one book. ``entity_id`` is the entity a contract-pinned
    parameter is first resolved for (the member with the earliest inception); ``entity_ids`` maps
    every entity of the bundle to its row, and ``known`` are the registry versions known at
    ``known_at`` (``registry.known_versions``), read once per bundle for the period rows."""
    resolved: list[ResolvedPolicyInput] = []
    if known is None and entities:
        known = registry.known_versions(session, known_at=known_at)
    for code, spec in sorted(POLICY_PARAMETERS.items()):
        if spec.pin == "P":
            resolved.extend(
                _period_rows(
                    code,
                    book_code=book_code,
                    entities=entities,
                    entity_ids=entity_ids or {},
                    versions=known or (),
                    known_at=known_at,
                )
            )
            continue
        if (
            spec.pin == "K"
            and pinned is not None
            and code in pinned
            and pinned[code]["level"] in {"B", "E", "T", "DEFAULT"}
        ):
            stored = pinned[code]
            resolved.append(
                _policy(
                    code,
                    "GROUP",
                    "",
                    _stored_value(stored["value"]),
                    str(stored["level"]),
                    str(stored["source_id"]),
                    "K",
                )
            )
            continue
        found = registry.resolve(
            session, code, book_code=BookCode(book_code), entity_id=entity_id, known_at=known_at
        )
        if found.value is None:
            continue
        value = engine_policy_value(found.value)
        source = spec.source_ref if found.source_id is None else str(found.source_id)
        resolved.append(_policy(code, "GROUP", "", value, found.level, source, "K"))
    # 05 RCP-15 rev 1.36: the import-batch level of POL-210, at contract scope, beside the GROUP row
    for contract_key, event_key in sorted((onboarding or {}).items()):
        resolved.append(
            _policy(
                ONBOARDING_METHOD,
                "CONTRACT",
                contract_key,
                OPENING_BALANCES_AT_CUTOVER,
                "C",
                event_key,
                "K",
            )
        )
    # 05 RCP-15 (item PIN-READBACK-1): the versions each obligation was priced from, at
    # OBLIGATION scope and level O, beside the GROUP row of POL-070 (ENGINE_SPEC S05-R-03).
    for subject_key, versions in sorted((recorded or {}).items()):
        resolved.append(
            _policy(
                SSP_VERSION_BASIS,
                "OBLIGATION",
                subject_key,
                dict(sorted(versions.items())),
                "O",
                RECORDED_SOURCE,
                "K",
            )
        )
    for contract_key, line in lines:
        product_code = str(line.get("product_code"))
        pin = None if pins is None else pins.get(product_code)
        if pin is not None and pin.get(OBLIGATION_POLICIES) is not None:
            # DG-KRN-REG-02 rev 1.93: the level-P values the product's obligations were first
            # computed with, not those its row and template hold today.
            subject_key = obligation_subject_key(contract_key, str(line.get("obligation_key")))
            resolved.extend(
                _policy(
                    str(code),
                    "OBLIGATION",
                    subject_key,
                    _stored_value(item["value"]),
                    "P",
                    str(item["source"]),
                    "K",
                )
                for code, item in sorted(pin[OBLIGATION_POLICIES].items())
            )
            continue
        row = product_rows.get(product_code)
        if row is None:
            continue
        template = template_values.get(product_code, {})
        merged = {
            **_contract_pinned(dict(row["policy_values"])),
            **_contract_pinned(dict(template.get("policy_values") or {})),
        }
        convention = template.get("ratable_convention")
        if convention is not None:
            merged.setdefault(CONVENTION_POLICY, str(convention))
        subject_key = obligation_subject_key(contract_key, str(line.get("obligation_key")))
        source = str(template.get("version_key") or product_code)
        resolved.extend(
            _policy(code, "OBLIGATION", subject_key, engine_policy_value(value), "P", source, "K")
            for code, value in sorted(merged.items())
        )
    # Preserve shadowed product defaults in the bundle so product pinning cannot turn
    # one member's exception into a missing default for another member in a later run.
    overridden = {(item.code, item.scope, item.subject_key) for item in overrides}
    products_by_subject = {
        obligation_subject_key(contract_key, str(line["obligation_key"])): str(line["product_code"])
        for contract_key, line in lines
    }
    preserved = [
        _policy(
            item.code,
            "PRODUCT",
            products_by_subject[item.subject_key],
            item.value,
            "P",
            item.source_ref,
            "K",
        )
        for item in resolved
        if item.scope == "OBLIGATION"
        and item.level == "P"
        and (item.code, item.scope, item.subject_key) in overridden
    ]
    resolved.extend(preserved)
    resolved.extend(overrides)
    unique: dict[tuple[str, str, str], ResolvedPolicyInput] = {}
    for item in resolved:
        unique[(item.code, item.scope, item.subject_key)] = item
    return tuple(unique[key] for key in sorted(unique))


def _template_values(
    session: Session,
    product_inputs: Sequence[ProductInput],
    *,
    at: date,
    known_at: datetime,
) -> dict[str, Mapping[str, Any]]:
    """Per product, the default template version in force at ``at`` (S03-R-02 step 2)."""
    found: dict[str, Mapping[str, Any]] = {}
    for item in product_inputs:
        if item.default_template_code is None:
            continue
        version = templates.resolve_template_version(
            session, item.default_template_code, at=at, known_at=known_at
        )
        if version is None:
            continue
        found[item.code] = {
            "version_key": version.version_key,
            "policy_values": dict(version.policy_values),
            "ratable_convention": version.ratable_convention,
        }
    return found


def entity_codes(session: Session, group_ids: Collection[UUID]) -> list[str]:
    """The codes of the entities a bundle of ``group_ids`` names, without building one: the
    contracting entities of the groups' current members and the entities that the lines of
    their booking and amendment events name as performing — the rule of ``_assemble``. They are
    read from the stream: the rows of the last computation can be older than it. For a caller
    that holds a group's window rows before it posts, or in place of a computation
    (``period_ends.hold_windows``; dev-guide DG-KRN-DB-08 (1c) rev 1.218); the caller chooses the
    scope the read runs under."""
    member = combination_group_member
    members = select(member.c.contract_id).where(
        member.c.combination_group_id.in_(sorted(set(group_ids))),
        member.c.valid_to_known_at.is_(None),
    )
    codes = {
        str(code)
        for code in session.execute(
            select(legal_entity.c.code)
            .select_from(
                contract.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == contract.c.tenant_id,
                        legal_entity.c.id == contract.c.contracting_entity_id,
                    ),
                )
            )
            .where(contract.c.id.in_(members))
        ).scalars()
    }
    stated = session.execute(
        select(contract_event.c.payload["lines"]).where(
            contract_event.c.contract_id.in_(members),
            contract_event.c.event_type.in_(sorted(TERM_EVENTS)),
        )
    ).scalars()
    for lines in stated:
        for line in lines if isinstance(lines, list) else ():
            if isinstance(line, Mapping):
                named = line.get("performing_entity_code") or line.get("selling_entity_code")
                if named:
                    codes.add(str(named))
    return sorted(codes)


def marked_trigger(
    asked: ComputationTrigger | str,
    group: Mapping[str, Any],
    events: Iterable[EventInput],
    previous_heads: Iterable[tuple[str, int]],
) -> str:
    """The trigger a bundle is built under (05 RCP-17 rev 1.206; 04 T-CON-03 ``dirty_trigger``
    rev 1.297; item FX-REPUBLISH-DIRTY-1): the one its caller asks for — except that a bundle
    asked under ``COMMAND`` which first-includes no event, no member event beyond the stream
    heads of the group's latest computation, takes the trigger the group's mark carries.

    A mark set by the approval of an FX rate set version carries ``FX_REPUBLISH``
    (``close.rate_reach``). Whoever then computes the group without bringing an event — the
    close run's ``RECOMPUTE_DIRTY``, a job, a command's recompute — stores the computation
    under it, so that a difference posted behind a lock has a non-event trigger and an empty
    lineage, the proof the out-of-period register asks (ENGINE_SPEC_B S15-R-18b). A computation
    that brings an event stays ``COMMAND``: its lines carry the event (S14-R-13a). Stage 14
    posts alike under both (S14-R-05)."""
    code = str(asked.value if isinstance(asked, ComputationTrigger) else asked)
    carried = group.get("dirty_trigger")
    if code != ComputationTrigger.COMMAND.value or carried is None:
        return code
    heads = dict(previous_heads)
    if any(event.stream_version > heads.get(event.contract_key, 0) for event in events):
        return code
    return str(getattr(carried, "value", carried))


def record_cutoff(session: Session, known_at: datetime) -> datetime:
    """The record-time cutoff of a computation at ``known_at``: the later of ``known_at`` and the
    transaction timestamp.

    [J] L3-1-Q-25: DB-08 stamps ``recorded_at``, and memberships follow it, from the server clock,
    while ``known_at`` comes from the application clock (DG-KRN-TIME-06). The later instant keeps
    every row committed before the transaction and every row it inserted, and stage 01 then finds
    no event recorded after ``known_at`` (RCP-15).
    """
    started = session.execute(select(func.transaction_timestamp())).scalar_one()
    if not isinstance(started, datetime):
        raise TypeError("transaction_timestamp() returned no timestamp")
    return max(known_at, started)


def build(
    session: Session,
    group_id: UUID,
    known_at: datetime,
    pending_events: Sequence[EventIn] = (),
    trigger: ComputationTrigger | str = ComputationTrigger.COMMAND,
    *,
    pending_contract_id: UUID | None = None,
    cutoff: datetime | None = None,
    pending_modifications: Sequence[Mapping[str, Any]] = (),
) -> InputBundle:
    """The engine input bundle of one combination group at ``known_at`` (RCP-15; DG-CMD-04).

    ``pending_modifications`` (CTR-17): T-CON-06 rows carried beside the stored ones — a draft
    the platform classifies (no event; stage 13 proposes for it) or previews (with its candidate
    ``CONTRACT_AMENDED`` in ``pending_events``).

    404 ``not-found`` when the group is not visible. ``pending_events`` are appended to
    ``pending_contract_id`` after its head, recorded at the cutoff. The bundle's ``known_at`` is
    ``record_cutoff(session, known_at)``, or ``cutoff`` when a caller names one.

    The bundle is read under the tenant's scope whoever calls and whatever scope the transaction
    was narrowed to (05 RCP-18 rev 1.82, TXN-10; supervisor rulings R-95 and R-98 (3)): the
    members of another entity, the performing entity's calendar, its period states and its posted
    lines belong to the group's computation and to its dry run alike.
    """
    with system_entity_scope(session):
        return _assemble(
            session,
            group_id,
            known_at,
            pending_events,
            trigger,
            pending_contract_id=pending_contract_id,
            cutoff=cutoff,
            pending_modifications=pending_modifications,
        )


def _assemble(
    session: Session,
    group_id: UUID,
    known_at: datetime,
    pending_events: Sequence[EventIn],
    trigger: ComputationTrigger | str,
    *,
    pending_contract_id: UUID | None,
    cutoff: datetime | None,
    pending_modifications: Sequence[Mapping[str, Any]],
) -> InputBundle:
    """``build`` inside the tenant's scope."""
    known_at = record_cutoff(session, known_at) if cutoff is None else cutoff
    group = repo.get_group(session, group_id)
    members = _members(session, group_id, known_at)
    if not members:
        raise ValueError(f"combination group {group_id} has no members at {known_at.isoformat()}")
    contracts = {UUID(str(row["id"])): row for row in members}
    if pending_events and pending_contract_id is None and len(members) == 1:
        pending_contract_id = next(iter(contracts))
    contract_ids = sorted(contracts)
    external_ids = {contract_id: str(row["external_id"]) for contract_id, row in contracts.items()}
    stored = _stored_events(session, contract_ids, known_at)
    obligation_rows = _obligations(session, contract_ids)
    obligation_keys = {UUID(str(row["id"])): str(row["obligation_key"]) for row in obligation_rows}
    ssp_versions, ssp_rows, _ = resolution.approved_versions(session)
    ssp_version_keys = {str(row["id"]): key for key, row in ssp_rows.items()}
    estimate_versions, estimate_keys = _estimate_versions(
        session, stored, pending_events, contracts=contracts, obligation_keys=obligation_keys
    )
    native, native_ids, native_rows = _native_modifications(
        session,
        stored,
        pending_events,
        pending_modifications,
        external_ids=external_ids,
        ssp_version_keys=ssp_version_keys,
    )
    events = _events(
        stored,
        pending_events,
        contracts=contracts,
        obligation_keys=obligation_keys,
        known_at=known_at,
        pending_contract_id=pending_contract_id,
        ssp_version_keys=ssp_version_keys,
        estimate_version_keys=estimate_keys,
        native_modification_ids=native_ids,
        adjustments=adjustment_payloads(
            session, stored, pending_events, obligation_keys=obligation_keys
        ),
    )
    events = _apply_regroups(events, native_rows)
    customer_rows = session.execute(
        select(customer.c.id, customer.c.code, related_party_group.c.code.label("group_code"))
        .select_from(
            customer.outerjoin(
                related_party_group,
                and_(
                    related_party_group.c.tenant_id == customer.c.tenant_id,
                    related_party_group.c.id == customer.c.related_party_group_id,
                ),
            )
        )
        .where(customer.c.id.in_(sorted({UUID(str(row["customer_id"])) for row in members})))
    ).all()
    customer_codes = {UUID(str(row.id)): str(row.code) for row in customer_rows}
    group_codes = {UUID(str(row.id)): row.group_code for row in customer_rows}
    lines = _lines(events) + pending_lines(
        pending_modifications, external_ids, applied=_pending_applied(pending_events)
    )
    # A modification line names its entity as ``selling_entity_code`` (T-CON-06; L5-1-Q-27).
    performing = {
        str(line.get("performing_entity_code") or line.get("selling_entity_code"))
        for _, line in lines
        if line.get("performing_entity_code") or line.get("selling_entity_code")
    }
    entity_ids = {UUID(str(row["contracting_entity_id"])) for row in members}
    if performing:
        entity_ids |= {
            UUID(str(entity_id))
            for (entity_id,) in session.execute(
                select(legal_entity.c.id).where(legal_entity.c.code.in_(sorted(performing)))
            )
        }
    inception = min(row["inception_date"] for row in members)
    entities, entity_rows = _entities(session, entity_ids, min(inception, group["inception_date"]))
    entity_codes = {UUID(str(row["id"])): code for code, row in entity_rows.items()}
    renewal_ids = {
        UUID(str(row["renewal_of_contract_id"])) for row in members if row["renewal_of_contract_id"]
    }
    renewal_keys = (
        {
            UUID(str(row_id)): str(external_id)
            for row_id, external_id in session.execute(
                select(contract.c.id, contract.c.external_id).where(
                    contract.c.id.in_(sorted(renewal_ids))
                )
            )
        }
        if renewal_ids
        else {}
    )
    reviewed = _judgements(session, external_ids, obligation_keys, known_at)
    amended = _modifications(
        events,
        ssp_version_keys=ssp_version_keys,
        currencies={
            str(row["external_id"]): str(row["transaction_currency"]).strip() for row in members
        },
    )
    headers = tuple(
        _header(
            contracts[contract_id],
            customer_codes=customer_codes,
            group_codes=group_codes,
            entity_codes=entity_codes,
            renewal_keys=renewal_keys,
            booking=_term_payload(events, external_ids[contract_id]),
            judgements=reviewed.get(contract_id, ()),
            modifications=_merged_modifications(
                amended.get(external_ids[contract_id], ()),
                native.get(external_ids[contract_id], ()),
            ),
        )
        for contract_id in sorted(contracts, key=lambda value: external_ids[value])
    )
    pins = product_pins(session, group_id, members)
    products, product_rows = _products(
        session, {str(line.get("product_code")) for _, line in lines}, at=inception, pins=pins
    )
    product_codes = {UUID(str(row["id"])): code for code, row in product_rows.items()}
    template_versions = templates.template_inputs(session, known_at=known_at)
    template_values = _template_values(session, products, at=inception, known_at=known_at)
    account_mapping = _account_mapping(session, known_at, entity_codes, product_codes)
    primary_entity = UUID(
        str(
            min(members, key=lambda row: (row["inception_date"], row["external_id"]))[
                "contracting_entity_id"
            ]
        )
    )
    kept: dict[str, set[str]] = {}
    for entity_id, book_code in session.execute(
        select(entity_book.c.entity_id, entity_book.c.book_code).where(
            entity_book.c.entity_id.in_(sorted(entity_ids)), entity_book.c.is_enabled.is_(True)
        )
    ):
        code = entity_codes.get(UUID(str(entity_id)))
        if code is not None:
            kept.setdefault(str(book_code), set()).add(code)
    book_rows = {
        str(row.code): row
        for row in session.execute(
            select(book.c.code, book.c.is_primary).where(book.c.is_enabled.is_(True))
        )
    }
    books: list[BookInput] = []
    onboarding = onboarding_pins(events)
    known_versions = registry.known_versions(session, known_at=known_at)
    override_rows = policy_inputs.approved_rows(session, contract_ids, known_at)
    for book_code in BOOK_ORDER:
        if book_code not in book_rows or not kept.get(book_code):
            continue
        previous = previous_version(session, group_id, book_code)
        policies = _policies(
            session,
            book_code=book_code,
            entity_id=primary_entity,
            entities=entities,
            entity_ids={code: UUID(str(row["id"])) for code, row in entity_rows.items()},
            known=known_versions,
            overrides=(
                *policy_inputs.scoped_inputs(
                    override_rows,
                    book_code=book_code,
                    contracts=external_ids,
                    obligations=obligation_rows,
                    lines=lines,
                ),
                *policy_inputs.period_scoped_inputs(
                    override_rows,
                    book_code=book_code,
                    contracts={
                        UUID(str(member["id"])): (
                            str(member["external_id"]),
                            entity_codes[UUID(str(member["contracting_entity_id"]))],
                        )
                        for member in members
                    },
                    period_cutoffs=[
                        (
                            entity.code,
                            item.period_key,
                            period_end_instant(item.end_date, entity.time_zone),
                        )
                        for entity in entities
                        for item in entity.periods
                    ],
                    known_at=known_at,
                ),
            ),
            known_at=known_at,
            pinned=(
                former_pinned_policies(session, group_id, book_code, members)
                if previous is None
                else previous["pinned_policies"]
            ),
            lines=lines,
            product_rows=product_rows,
            template_values=template_values,
            onboarding=onboarding,
            pins=pins,
            recorded=recorded_ssp_versions(
                session,
                group_id,
                book_code,
                previous,
                members,
                stored,
                obligation_rows,
                ssp_version_keys,
            ),
        )
        books.append(
            BookInput(
                book_code=book_code,
                is_primary=bool(book_rows[book_code].is_primary),
                entity_codes=tuple(sorted(kept[book_code])),
                policies=policies,
                account_mapping=account_mapping,
            )
        )
    currency = str(group["transaction_currency"]).strip()
    currency_codes = {currency, *(entity.functional_currency for entity in entities)}
    previous_heads = _previous_heads(session, group_id, external_ids)
    return InputBundle(
        format_version=FORMAT_VERSION,
        engine_version=ENGINE_VERSION,
        trigger=marked_trigger(trigger, group, events, previous_heads),
        known_at=known_at,
        tenant_preset=resolution.tenant_preset(session, known_at=known_at),
        currencies={code: ISO_4217[code] for code in sorted(currency_codes)},
        books=tuple(books),
        entities=entities,
        group=GroupInput(
            group_key=str(group["code"]),
            transaction_currency=currency,
            inception_date=group["inception_date"],
            member_contract_keys=tuple(sorted(external_ids.values())),
            criterion=group["criterion"],
            previous_stream_heads=previous_heads,
            products=products,
            portfolios=(),
        ),
        contracts=headers,
        events=events,
        ssp_versions=ssp_versions,
        pob_template_versions=template_versions,
        rule_set_versions=(),
        estimate_versions=estimate_versions,
        fx_rates=_fx_rates(session, currency_codes, known_at),
        posted=_posted(session, contracts, obligation_keys, group_code=str(group["code"])),
    )


def posted_subject(
    stored_key: str | None,
    *,
    external_id: str,
    obligation_key: str | None,
    entry_kind: str,
    entity_code: str,
    group_code: str,
) -> str:
    """The subject of a posted line for 05 RCP-05 (rev 1.202; 04 T-SL-04 rev 1.282; supervisor
    ruling R-11 as amended): its stored ``subject_key`` — the subject the engine posted under, so
    a posted amount answers the role key it was posted for (ENGINE_SPEC_B S14-R-04 rev 1.165,
    S14-INV-02). Every line a product command writes stores one (``journals.subledger.post``).

    A line without a key — a line a test builder wrote — answers what it answered before the key
    was stored. An ``FX_REMEASUREMENT`` line answers ``<group>@<entity>`` of ``group_code``, the
    bundle's group, whatever else it names: every JET-10 part posts under that one subject (Table
    14-A), and until rev 1.165 stage 14 put such an amount there by its entry kind. Any other line
    answers the spelling of decision [J] L3-1-Q-32, which stands for such lines alone: a line of
    an obligation its obligation subject key, any other ``<contract subject key>@<entity code>``.
    """
    if stored_key is not None:
        return stored_key
    if entry_kind == SubledgerEntryKind.FX_REMEASUREMENT.value:
        return group_entity_subject_key(group_code, entity_code)
    if obligation_key is not None:
        return obligation_subject_key(external_id, obligation_key)
    return f"{contract_subject_key(external_id)}@{entity_code}"


def _posted(
    session: Session,
    contracts: Mapping[UUID, Mapping[str, Any]],
    obligation_keys: Mapping[UUID, str],
    *,
    group_code: str,
) -> tuple[PostedAmountInput, ...]:
    """RCP-05: per (book, entity, subject, entry kind, role, posting period, origin period, posting
    class, reason code), the signed sums of the members' sealed lines in integer minor units, in
    bundle order, each with the distinct rate references stamped on its lines (``rate_refs``;
    ENGINE_SPEC_B S14-R-28; rev 1.41). The subject is ``posted_subject`` of the line: its stored
    key, and for a line without one the spelling of L3-1-Q-32 with ``group_code``, the bundle's
    group, for a remeasurement line. ``origin_period_key`` is None for a line posted in its own
    period.
    """
    if not contracts:
        return ()
    line = subledger_line
    tenant = line.c.tenant_id
    origin = period.alias("posted_origin_period")
    counterparty = legal_entity.alias("posted_counterparty")
    grouping = (
        line.c.book_code,
        legal_entity.c.code,
        line.c.contract_id,
        line.c.obligation_id,
        line.c.subject_key,
        line.c.entry_kind,
        line.c.account_role,
        line.c.clearing_purpose,
        counterparty.c.code,
        period.c.period_key,
        origin.c.period_key,
        subledger_posting.c.posting_kind,
        line.c.txn_currency,
        line.c.functional_currency,
        line.c.reason_code,
        line.c.fx_rate_id,
    )
    statement = (
        select(
            *grouping,
            func.sum(line.c.amount_txn).label("amount_txn"),
            func.sum(line.c.amount_functional).label("amount_functional"),
        )
        .select_from(
            line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == tenant,
                    subledger_posting.c.id == line.c.subledger_posting_id,
                ),
            )
            .join(
                legal_entity,
                and_(legal_entity.c.tenant_id == tenant, legal_entity.c.id == line.c.entity_id),
            )
            .join(period, and_(period.c.tenant_id == tenant, period.c.id == line.c.period_id))
            .outerjoin(
                origin, and_(origin.c.tenant_id == tenant, origin.c.id == line.c.origin_period_id)
            )
            .outerjoin(
                counterparty,
                and_(
                    counterparty.c.tenant_id == tenant,
                    counterparty.c.id == line.c.counterparty_entity_id,
                ),
            )
        )
        .where(line.c.contract_id.in_(sorted(contracts)))
        .group_by(*grouping)
    )
    rate_rows = posted_rate_rows(session, contracts)
    rate_keys = {ids[0]: (rate_key, version) for rate_key, (version, _, ids) in rate_rows.items()}
    totals: dict[tuple[str, ...], list[int]] = {}
    refs: dict[tuple[str, ...], set[tuple[str, str]]] = {}
    for row in session.execute(statement):
        (
            book_code,
            entity_code,
            contract_id,
            obligation_id,
            stored_key,
            entry_kind,
            account_role,
            clearing_purpose,
            counterparty_code,
            period_key,
            origin_period_key,
            posting_kind,
            txn_currency,
            functional_currency,
            reason_code,
            rate_id,
            amount_txn,
            amount_functional,
        ) = tuple(row)
        subject_key = posted_subject(
            None if stored_key is None else str(stored_key),
            external_id=str(contracts[UUID(str(contract_id))]["external_id"]),
            obligation_key=(
                None if obligation_id is None else obligation_keys[UUID(str(obligation_id))]
            ),
            entry_kind=str(entry_kind),
            entity_code=str(entity_code),
            group_code=group_code,
        )
        txn = str(txn_currency).strip()
        functional = str(functional_currency).strip()
        key = (
            str(book_code),
            str(entity_code),
            subject_key,
            str(entry_kind),
            str(account_role),
            str(clearing_purpose or ""),
            str(period_key),
            str(origin_period_key or ""),
            POSTING_CLASSES[str(posting_kind)],
            str(counterparty_code or ""),
            txn,
            functional,
            str(reason_code or ""),
        )
        sums = totals.setdefault(key, [0, 0])
        sums[0] += decimal_to_minor(Decimal(amount_txn), ISO_4217[txn].minor_unit)
        sums[1] += decimal_to_minor(Decimal(amount_functional), ISO_4217[functional].minor_unit)
        if rate_id is not None:
            refs.setdefault(key, set()).add(rate_keys[UUID(str(rate_id))])
    return tuple(
        PostedAmountInput(
            book_code=key[0],
            entity_code=key[1],
            subject_key=key[2],
            entry_kind=key[3],
            account_role=key[4],
            clearing_purpose=key[5] or None,
            counterparty_entity_code=key[9] or None,
            period_key=key[6],
            origin_period_key=key[7] or None,
            posting_class=key[8],
            txn_currency=key[10],
            functional_currency=key[11],
            amount_txn=sums[0],
            amount_functional=sums[1],
            reason_code=key[12] or None,
            rate_refs=tuple(sorted(refs.get(key, ()))),
        )
        for key, sums in sorted(totals.items())
    )


# --- natural keys to rows (DG-ENG-02: the orchestrator maps keys to ids when persisting) ---------


@dataclass(frozen=True, slots=True)
class BundleIndex:
    """Row ids of a built bundle's natural keys."""

    group: Mapping[str, Any]
    contracts: Mapping[str, Mapping[str, Any]]  # external id -> contract row
    obligations: Mapping[str, Mapping[str, Any]]  # obligation subject key -> obligation row
    entities: Mapping[str, Mapping[str, Any]]  # entity code -> legal_entity row
    periods: Mapping[tuple[str, str], tuple[UUID, date]]  # (entity code, period key) -> (id, end)
    products: Mapping[str, UUID]
    templates: Mapping[str, UUID]  # template version key -> id
    ssp_versions: Mapping[str, UUID]
    ssp_entries: Mapping[str, UUID]
    account_mapping_version_id: UUID | None
    fx_versions: Mapping[str, UUID]
    events: Mapping[tuple[str, int], UUID]  # (external id, stream version) -> event id


def index(session: Session, bundle: InputBundle) -> BundleIndex:
    """The rows behind ``bundle``'s natural keys, read in the caller's session under the tenant's
    scope, as the bundle was (05 TXN-10)."""
    with system_entity_scope(session):
        return _index(session, bundle)


def _index(session: Session, bundle: InputBundle) -> BundleIndex:
    group = dict(
        session.execute(
            select(combination_group).where(combination_group.c.code == bundle.group.group_key)
        )
        .mappings()
        .one()
    )
    contract_rows = {
        str(row["external_id"]): dict(row)
        for row in session.execute(
            select(contract).where(contract.c.external_id.in_(bundle.group.member_contract_keys))
        ).mappings()
    }
    by_id = {UUID(str(row["id"])): key for key, row in contract_rows.items()}
    obligations = {
        obligation_subject_key(
            by_id[UUID(str(row["contract_id"]))], str(row["obligation_key"])
        ): dict(row)
        for row in session.execute(
            select(obligation).where(obligation.c.contract_id.in_(sorted(by_id)))
        ).mappings()
    }
    entity_rows = {
        str(row["code"]): dict(row)
        for row in session.execute(
            select(legal_entity).where(legal_entity.c.code.in_([e.code for e in bundle.entities]))
        ).mappings()
    }
    periods: dict[tuple[str, str], tuple[UUID, date]] = {}
    for code, row in entity_rows.items():
        for period_id, period_key, end_date in session.execute(
            select(period.c.id, period.c.period_key, period.c.end_date).where(
                period.c.calendar_id == row["calendar_id"]
            )
        ):
            periods[(code, str(period_key))] = (UUID(str(period_id)), end_date)
    products = {
        str(code): UUID(str(product_id))
        for product_id, code in session.execute(
            select(product.c.id, product.c.code).where(
                product.c.code.in_([p.code for p in bundle.group.products])
            )
        )
    }
    template_ids = {
        f"{code}@v{version_no}": UUID(str(version_id))
        for version_id, code, version_no in session.execute(
            select(
                pob_template_version.c.id, pob_template.c.code, pob_template_version.c.version_no
            ).select_from(
                pob_template_version.join(
                    pob_template,
                    and_(
                        pob_template.c.tenant_id == pob_template_version.c.tenant_id,
                        pob_template.c.id == pob_template_version.c.pob_template_id,
                    ),
                )
            )
        )
    }
    _, by_key, entry_ids = resolution.approved_versions(session)
    ssp_ids = {key: UUID(str(row["id"])) for key, row in by_key.items()}
    mapping_id = mapping_version_id(session, bundle)
    fx_ids = {
        fx_version_key(str(code), int(no)): UUID(str(version_id))
        for version_id, code, no in session.execute(
            select(
                fx_rate_set_version.c.id, fx_rate_set.c.code, fx_rate_set_version.c.version_no
            ).select_from(
                fx_rate_set_version.join(
                    fx_rate_set,
                    and_(
                        fx_rate_set.c.tenant_id == fx_rate_set_version.c.tenant_id,
                        fx_rate_set.c.id == fx_rate_set_version.c.fx_rate_set_id,
                    ),
                )
            )
        )
    }
    events = {
        (by_id[UUID(str(contract_id))], int(version)): UUID(str(event_id))
        for event_id, contract_id, version in session.execute(
            select(
                contract_event.c.id, contract_event.c.contract_id, contract_event.c.stream_version
            ).where(contract_event.c.contract_id.in_(sorted(by_id)))
        )
    }
    return BundleIndex(
        group=group,
        contracts=contract_rows,
        obligations=obligations,
        entities=entity_rows,
        periods=periods,
        products=products,
        templates=template_ids,
        ssp_versions=ssp_ids,
        ssp_entries=dict(entry_ids),
        account_mapping_version_id=mapping_id,
        fx_versions=fx_ids,
        events=events,
    )


def mapping_version_id(session: Session, bundle: InputBundle) -> UUID | None:
    keys = {book_input.account_mapping.version_key for book_input in bundle.books} - {
        NO_MAPPING_KEY
    }
    if not keys:
        return None
    for version_id, name, version_no in session.execute(
        select(
            account_mapping_version.c.id,
            account_mapping_version.c.name,
            account_mapping_version.c.version_no,
        )
    ):
        if mapping_version_key(str(name), int(version_no)) in keys:
            return UUID(str(version_id))
    return None


def pinned_refs(
    session: Session,
    bundle: InputBundle,
    found: BundleIndex,
    output: OutputBundle | None = None,
) -> dict[str, Any]:
    """T-CON-07 ``pinned_refs`` of a computation over ``bundle`` (REQ-REF-015; RCP-15). With the
    ``output`` of a computation that succeeded, the member ``products`` records the products it
    pins (``product_pin_members``; 04 rev 1.110), and ``ssp_weights`` — present when the
    computation weighed a modification — the version each weight was priced from
    (``ssp_weight_members``). ``registry_version_ids`` names the registry versions in force at the
    bundle's ``known_at`` and every version a resolved row of the bundle came from: a period's
    row may carry a version that was superseded before ``known_at``, and a contract-pinned row the
    version of the contract's first computation (item PINP-PERIOD-VALUE-1)."""
    in_force = {
        str(value)
        for (value,) in session.execute(
            select(registry_version.c.id).where(
                registry_version.c.status.in_(_IN_FORCE),
                registry_version.c.published_at <= bundle.known_at,
                or_(
                    registry_version.c.effective_from.is_(None),
                    registry_version.c.effective_from <= bundle.known_at,
                ),
                or_(
                    registry_version.c.effective_to.is_(None),
                    registry_version.c.effective_to > bundle.known_at,
                ),
            )
        )
    }
    row_versions = {
        policy.source_ref
        for book_input in bundle.books
        for policy in book_input.policies
        if policy.level in _VERSION_LEVELS
    }
    registry_ids = sorted(in_force | row_versions)
    calendars = sorted({str(found.entities[e.code]["calendar_id"]) for e in bundle.entities})
    fx_keys = {rate.version_key for rate in bundle.fx_rates}
    estimate_event_ids = sorted(
        found.events[(event.contract_key, event.stream_version)]
        for event in bundle.events
        if event.event_type == ContractEventType.ESTIMATE_CHANGED.value
        and (event.contract_key, event.stream_version) in found.events
    )
    estimate_ids = (
        sorted(
            {
                str(value)
                for (value,) in session.execute(
                    select(contract_event.c.estimate_version_id).where(
                        contract_event.c.id.in_(estimate_event_ids),
                        contract_event.c.estimate_version_id.is_not(None),
                    )
                )
            }
        )
        if estimate_event_ids
        else []
    )
    mapping_id = found.account_mapping_version_id
    weights = {} if output is None else ssp_weight_members(bundle, found, output)
    return {
        "ssp_book_version_ids": sorted(
            str(found.ssp_versions[v.version_key]) for v in bundle.ssp_versions
        ),
        "registry_version_ids": registry_ids,
        "rule_set_version_ids": [],
        "pob_template_version_ids": sorted(
            str(found.templates[t.version_key]) for t in bundle.pob_template_versions
        ),
        "account_mapping_version_id": None if mapping_id is None else str(mapping_id),
        "fx_rate_set_version_ids": sorted(str(found.fx_versions[key]) for key in fx_keys),
        "calendar_ids": calendars,
        "estimate_version_ids": estimate_ids,
        **({} if output is None else {PRODUCT_PINS: product_pin_members(bundle, output)}),
        **({SSP_WEIGHTS: weights} if weights else {}),
    }
