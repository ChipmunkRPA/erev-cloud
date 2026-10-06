"""Shared frozen stage state (ENGINE_SPEC §0.8, §0.11; ENGINE_SPEC_B §0.5, §0.6; EKC-6).

Stage 01 builds ``CanonicalBundle``; stages 02 to 08 fold an ``AllocatedState`` per book; stages 09
to 15 consume it (Table 0.11-A). Field names equal 04 columns where a column exists. Members whose
content a stage owns and no document expands (payload views, lookup indexes) are typed as mappings
or tuples of bundle inputs; the stage that builds them adds its lookups. Every class is a frozen
dataclass with slots. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates, guards
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    ContractInput,
    EntityInput,
    EstimateVersionInput,
    FxRateInput,
    GroupInput,
    InputBundle,
    MaterialRightInput,
    PostedAmountInput,
    ProductInput,
    ProposalOut,
    ResolvedPolicyInput,
    RuleSetInput,
    SspVersionInput,
    TemplateInput,
    TimeTrigger,
)
from erev_engine.canonical import canonical_bytes
from erev_engine.currencies import CurrencyTable
from erev_engine.enums import (
    BookCode,
    Distinctness,
    LicenceNature,
    ObligationKind,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    ScheduleKind,
    ScheduleLineType,
    ScopeFlag,
    WarrantyType,
)
from erev_engine.errors import EngineError
from erev_engine.trace import SourceRef

__all__ = [
    "DISAGGREGATION_DERIVED",
    "TIMING_OF_TRANSFER",
    "disaggregation_tags",
    "BILLING_BASIS_POLICY",
    "BILLING_MODE_ENGINE",
    "BILLING_MODE_ERP",
    "BILLING_POSTING_POLICY",
    "POLICY_SCOPES",
    "AccountMappingView",
    "AllocatedState",
    "AllocationSegment",
    "BookContext",
    "CanonicalBundle",
    "ContractView",
    "DepositRelease",
    "EntityView",
    "EstimatePin",
    "EstimatePins",
    "EventView",
    "Finding",
    "GroupView",
    "LedgerPoint",
    "LedgerStep",
    "MaterialRightTerms",
    "ObligationState",
    "OpeningBalanceView",
    "PolicyResolver",
    "PostedIndex",
    "ProgressBase",
    "ProgressTotals",
    "QuantityLedger",
    "CONCESSION_EMBEDDED",
    "CONCESSION_SEPARATE",
    "ConcessionAddition",
    "ConcessionQuota",
    "Quota",
    "Quota1",
    "RateIndex",
    "ReturnPath",
    "ReturnPin",
    "RuleSetIndex",
    "ScheduleLineOut",
    "SegmentCause",
    "SpecialistTargets",
    "SspIndex",
    "SspResolution",
    "Target",
    "TemplateIndex",
    "TpBuildUp",
    "TpView",
    "VcElementView",
    "billing_mode_at",
    "malformed_estimate_key",
]

# Views that are the bundle inputs themselves.
EntityView = EntityInput  # functional currency, time zone, calendar periods and period states
AccountMappingView = AccountMappingInput  # T-REF-15 PUBLISHED version pinned for the computation
OpeningBalanceView = Mapping[str, object]  # OPENING_BALANCE_ESTABLISHED payload values (POL-210)

POLICY_SCOPES: Final = ("GROUP", "CONTRACT", "OBLIGATION", "ENTITY", "PERIOD")

OrderKey = tuple[date, int, str]  # ENG-06: (effective_date, record_seq, event_key)


# --- Policies and book context (CV-17; ENGINE_SPEC_B §0.5) ---------------------------------------


@dataclass(frozen=True, slots=True)
class PolicyResolver:
    """Policy reads of one book over ``BookInput.policies`` (CV-17; EMOD-03).

    Pin ``K`` codes resolve to the most specific scope present: OBLIGATION, CONTRACT, ENTITY, then
    GROUP. Pin ``P`` codes resolve only through the PERIOD scope ``<entity code>@<period_key>``.
    The orchestrator resolved every value (DG-KRN-REG-03), so an absent value is a bundle-assembly
    error and raises ``ValueError`` (CV-17, CV-45).
    """

    policies: tuple[ResolvedPolicyInput, ...]  # (code, scope, subject_key)
    _index: Mapping[tuple[str, str, str], ResolvedPolicyInput] = field(
        init=False, repr=False, compare=False
    )
    _pins: Mapping[str, str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        guards.assert_sorted(
            self.policies, key=lambda p: (p.code, p.scope, p.subject_key), name="policies"
        )
        index: dict[tuple[str, str, str], ResolvedPolicyInput] = {}
        pins: dict[str, str] = {}
        for policy in self.policies:
            code = policy.code
            if policy.scope not in POLICY_SCOPES:
                raise ValueError(f"policy {code} has unknown scope {policy.scope!r}")
            if policy.pin not in ("K", "P"):
                raise ValueError(f"policy {code} has unknown pin {policy.pin!r}")
            if (policy.pin == "P") != (policy.scope == "PERIOD"):
                raise ValueError(f"policy {code}: pin P values and only they use the PERIOD scope")
            if (policy.scope == "GROUP") != (policy.subject_key == ""):
                raise ValueError(f"policy {code}: only the GROUP scope has an empty subject key")
            if pins.setdefault(code, policy.pin) != policy.pin:
                raise ValueError(f"policy {code} mixes pins K and P")
            index[(code, policy.scope, policy.subject_key)] = policy
        object.__setattr__(self, "_index", index)
        object.__setattr__(self, "_pins", pins)

    def resolved(
        self,
        code: str,
        *,
        contract: str | None = None,
        obligation: str | None = None,
        entity: str | None = None,
        period: str | None = None,
    ) -> ResolvedPolicyInput:
        """The ``ResolvedPolicyInput`` of the most specific scope present for ``code``."""
        pin = self._pins.get(code)
        if pin is None:
            raise ValueError(f"policy {code} is absent from the bundle (CV-17)")
        if pin == "P":
            if entity is None or period is None:
                raise ValueError(f"policy {code} is period-scoped: pass entity and period")
            candidates = [("PERIOD", f"{entity}@{period}")]
        else:
            scopes = (("OBLIGATION", obligation), ("CONTRACT", contract), ("ENTITY", entity))
            candidates = [(scope, key) for scope, key in scopes if key is not None]
            candidates.append(("GROUP", ""))
        for scope, subject_key in candidates:
            found = self._index.get((code, scope, subject_key))
            if found is not None:
                return found
        raise ValueError(f"policy {code} has no value for the requested scope (CV-17)")

    def value(
        self,
        code: str,
        *,
        contract: str | None = None,
        obligation: str | None = None,
        entity: str | None = None,
        period: str | None = None,
    ) -> str | tuple[str, ...] | Mapping[str, str]:
        """The resolved literal(s) of ``code`` (CV-17)."""
        return self.resolved(
            code, contract=contract, obligation=obligation, entity=entity, period=period
        ).value

    def all(self) -> tuple[ResolvedPolicyInput, ...]:
        """Every resolved value, in bundle order (stage keys, ENGINE_SPEC_B S13-R-04)."""
        return self.policies

    def require(self, codes: Iterable[str]) -> None:
        """``ValueError`` naming every declared code absent from the bundle (CV-17)."""
        missing = sorted(set(codes) - set(self._pins))
        if missing:
            raise ValueError(f"policies declared by a stage are absent: {', '.join(missing)}")

    def has(self, code: str, *, entity: str | None = None, period: str | None = None) -> bool:
        """Whether the bundle holds any resolved value of ``code``; with ``entity`` and ``period``,
        whether it holds the value of that entity period. A period-pinned parameter without a
        framework default has a value only in the periods a version holds it for (the
        orchestrator resolves each period at its own instant; ENGINE_SPEC_B S10-R-06)."""
        if entity is None and period is None:
            return code in self._pins
        if entity is None or period is None:
            raise ValueError(f"policy {code}: pass entity and period together")
        return (code, "PERIOD", f"{entity}@{period}") in self._index


@dataclass(frozen=True, slots=True)
class BookContext:
    book_code: BookCode  # E-02
    framework: BookCode  # ASC606 | IFRS15 | LEGACY
    currencies: CurrencyTable  # minor units per ISO code
    txn_currency: str  # single currency per group (D-75, 03 Q3)
    entities: Mapping[str, EntityView]  # entity code -> view
    horizon: Mapping[str, str]  # entity code -> horizon period key (CV-13)
    policies: PolicyResolver
    mapping: AccountMappingView
    trigger: str  # E-87 literal, or "DRY_RUN" (05 §3.2)
    tenant_preset: str  # "DEFAULT" | "LEGACY_PARITY"


# --- Billing mode (POLICIES §1 POL-004, POL-123; ENGINE_SPEC_B S10-R-06; D-91) -------------------

BILLING_POSTING_POLICY: Final = "billing.posting"  # POL-004
BILLING_BASIS_POLICY: Final = "balance.position_invoice_basis"  # POL-123
BILLING_MODE_ERP: Final = "ERP"
BILLING_MODE_ENGINE: Final = "ENGINE"
_BILLING_MODE_OF_POSTING: Final[Mapping[str, str]] = MappingProxyType(
    {"ERP": BILLING_MODE_ERP, "ENGINE": BILLING_MODE_ENGINE}
)
_BILLING_MODE_OF_BASIS: Final[Mapping[str, str]] = MappingProxyType(
    {"ERP_POSTED_INVOICES": BILLING_MODE_ERP, "UNCONDITIONAL_INVOICES_ONLY": BILLING_MODE_ENGINE}
)


def billing_mode_at(policies: PolicyResolver, entity: EntityView, on: date) -> str:
    """``ERP`` or ``ENGINE`` for ``entity`` at ``on``: the one POL-123-else-POL-004 resolution.

    The resolved POL-123 basis at the entity's period of the date when the bundle holds a POL-123
    value for that period, else the mode derived from POL-004 at that period (pin ``P``; POLICIES
    §1). POL-123 has no framework default, so a period before its first version has no POL-123
    value and reads POL-004, whatever later periods hold (item PINP-PERIOD-VALUE-1). Stage 10
    dates every line by it (ENGINE_SPEC_B S10-R-06, §10.2.2) and stage 09 counts units billed by
    it (S09-R-23a); D-91 "One identity rule, one home" places the resolution here, beside the
    resolver, so both stages read one function (D-88 L7-5-Q-3 forbids stage 10 helper imports,
    not a shared stage-neutral function). An unknown literal raises ``ENGINE_INVARIANT_VIOLATED``.
    """
    period_key = dates.period_of(entity, on).period_key
    code, modes = (
        (BILLING_BASIS_POLICY, _BILLING_MODE_OF_BASIS)
        if policies.has(BILLING_BASIS_POLICY, entity=entity.code, period=period_key)
        else (BILLING_POSTING_POLICY, _BILLING_MODE_OF_POSTING)
    )
    value = policies.value(code, entity=entity.code, period=period_key)
    if not isinstance(value, str) or value not in modes:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the billing mode is unknown",
            subject_key=entity.code,
            detail={"rule": "S10-R-06", "policy": code},
        )
    return modes[value]


# --- Stage 01 products (ENGINE_SPEC §0.11, §1) ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventView:
    event_key: str
    contract_key: str
    event_type: str  # E-03
    effective_date: date
    record_seq: int
    recorded_at: datetime
    obligation_subject_keys: tuple[str, ...]
    payload: Mapping[str, object]  # decimals converted to Fraction (CV-30)
    is_new: bool  # stream_version > previous_stream_heads[contract_key]
    source: SourceRef  # ref_type "contract_event", ref_id = event_key

    @property
    def order_key(self) -> OrderKey:
        """ENG-06 order (CV-20)."""
        return (self.effective_date, self.record_seq, self.event_key)


@dataclass(frozen=True, slots=True)
class LedgerPoint:
    """Cumulative quantities of one subject after a measure event (S01-R-16)."""

    delivered_cum: Fraction
    returned_cum: Fraction
    costs_cum: Fraction
    hours_cum: Fraction
    output_ratio: Fraction
    milestone_weight_cum: Fraction
    usage_quantity_cum: Fraction
    billed_cum: Fraction
    credited_cum: Fraction
    paid_cum: Fraction
    last_event_key: str | None

    @classmethod
    def zero(cls) -> LedgerPoint:
        """The point before any measure event."""
        nothing = Fraction(0)
        return cls(*(nothing,) * 10, last_event_key=None)


@dataclass(frozen=True, slots=True)
class LedgerStep:
    order_key: OrderKey  # of the measure event
    point: LedgerPoint  # after the event


@dataclass(frozen=True, slots=True)
class QuantityLedger:
    """Cumulative quantities per subject key after each measure event (S01-R-16)."""

    steps: Mapping[str, tuple[LedgerStep, ...]]  # subject key -> ascending by order key

    def __post_init__(self) -> None:
        for subject_key, steps in self.steps.items():
            guards.assert_sorted(steps, key=lambda step: step.order_key, name=subject_key)

    def at(
        self, subject_key: str, *, before: EventView | None = None, on: date | None = None
    ) -> LedgerPoint:
        """The point after every measure event that precedes ``before`` in ENG-06 order, or whose
        effective date is on or before ``on``; the latest point when neither is given."""
        if before is not None and on is not None:
            raise ValueError("pass before or on, not both")
        steps = self.steps.get(subject_key, ())
        if before is not None:
            count = bisect.bisect_left(steps, before.order_key, key=lambda step: step.order_key)
        elif on is not None:
            count = bisect.bisect_right(steps, on, key=lambda step: step.order_key[0])
        else:
            count = len(steps)
        return steps[count - 1].point if count else LedgerPoint.zero()


@dataclass(frozen=True, slots=True)
class EstimatePin:
    version: EstimateVersionInput
    event_order_key: OrderKey  # of the ESTIMATE_CHANGED event that applied the version
    # D-92 (1)/(1a): the ENG-06 position at which the version applies: the same-date
    # ``CONTRACT_AMENDED`` it belongs to when the amendment's lines change or its re-measurement
    # reads the estimate (ENGINE_SPEC S06-R-15, S06-R-17; ENGINE_SPEC_B S09-R-04); else its event.
    applies_order_key: OrderKey | None = None
    # S01-R-18, S04-R-01: the applying event is effective on or before the group inception and no
    # amendment takes the version (D-92), so the version is in force at inception and belongs to
    # the inception measurement at whatever record position its event stands among the boundary
    # events of that date; its amount was promised before every such boundary (S08-R-05).
    at_inception: bool = False

    def applies(self) -> OrderKey:
        """The position the pin counts from: ``applies_order_key`` or the applying event's."""
        return self.event_order_key if self.applies_order_key is None else self.applies_order_key


@dataclass(frozen=True, slots=True)
class EstimatePins:
    """Approved estimate versions by element key (S01-R-18)."""

    pins: Mapping[str, tuple[EstimatePin, ...]]  # estimate key -> ascending by event order key

    def pin(
        self, estimate_key: str, at: date, before: EventView | None = None
    ) -> EstimateVersionInput | None:
        """The version with the greatest ``effective_date`` on or before ``at`` (ties: greater
        ``version_no``) among versions that apply before ``before`` (S01-R-18): at their own
        ``ESTIMATE_CHANGED`` event, or at the same-date amendment D-92 (1)/(1a) assigns them to. A
        version in force at inception (``EstimatePin.at_inception``) applies before every
        position: its event is no boundary (S04-R-01, S08-R-01)."""
        candidates = [
            pin.version
            for pin in self.pins.get(estimate_key, ())
            if pin.version.effective_date <= at
            and (before is None or pin.at_inception or pin.applies() < before.order_key)
        ]
        return max(
            candidates,
            key=lambda version: (version.effective_date, version.version_no),
            default=None,
        )

    def replaced_by(self, estimate_key: str, ev: EventView) -> EstimateVersionInput | None:
        """The version in force of ``estimate_key`` when ``ev`` applied its own: as ``pin`` at the
        event's date, every version counted from its own position — the ``v_old`` of the
        event's pin node (S08-R-01). A version in force at inception counts from its event here,
        so the first version of an element replaces none."""
        candidates = [
            pin.version
            for pin in self.pins.get(estimate_key, ())
            if pin.version.effective_date <= ev.effective_date and pin.applies() < ev.order_key
        ]
        return max(
            candidates,
            key=lambda version: (version.effective_date, version.version_no),
            default=None,
        )

    def of_contract(self, contract_key: str) -> tuple[str, ...]:
        """The element keys of ``contract_key`` in the index, ascending (CV-21 lookups; D-98
        candidate 76). The index is keyed by the CV-21 encoded element key
        ``<encoded external id>/<encoded element code>``, so the contract's elements are exactly
        the keys under its encoded prefix — never a raw-string prefix of the unencoded external id,
        which misses every contract whose id carries ``%``, ``/``, ``@``, ``#`` or ``:``
        (ENG-COST-ENC-1: ``C-COST/2`` lost its approved renewal).

        Malformedness is a property of an entry's own structure, never of the requested prefix
        (ENG-COST-LOOKUP-R1): raw ``C/2`` encodes to ``C%2F2`` and raw ``C%2F2`` to ``C%252F2``, so
        ``C%2F2/EAC`` under the raw prefix ``C%2F2/`` is the first contract's valid key and is not
        selected for the second. An entry that is not ``<head>/<element>`` — a second separator, an
        empty part, an unencoded ``@``, ``#`` or ``:`` (``:`` only as the ``PORTFOLIO:`` marker),
        an escape other than the five of CV-21 — is refused by name (``ENGINE_INVARIANT_VIOLATED``,
        rule CV-21) wherever it lies in the index, never skipped: a malformed pin key is a corrupt
        bundle, not another contract's data."""
        # Imported at call time: stage 01 imports this module (the registry cycle of L2-5-Q-37).
        from erev_engine.stages.s01_canonicalize.convert import encode_key

        encoded = f"{encode_key(contract_key)}/"
        found: list[str] = []
        for key in sorted(self.pins):
            reason = malformed_estimate_key(key)
            if reason is not None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    f"an estimate index key is not a CV-21 element key: {reason}",
                    subject_key=encode_key(contract_key),
                    detail={
                        "rule": "CV-21",
                        "estimate_key": key,
                        "contract_key": contract_key,
                        "reason": reason,
                    },
                )
            if key.startswith(encoded):
                found.append(key)
        return tuple(found)


_PORTFOLIO_MARKER: Final = "PORTFOLIO:"
_KEY_ESCAPE_CODES: Final = frozenset({"%25", "%2F", "%40", "%23", "%3A"})


def malformed_estimate_key(key: str) -> str | None:
    """Why ``key`` is not a CV-21 estimate element key, or None when it is one (S01-R-18; D-98
    candidate 76). The form is ``<head>/<element>``: exactly one ``/``, both parts non-empty, no
    unencoded ``@`` or ``#``, ``:`` only as the head's ``PORTFOLIO:`` marker, and every ``%`` one of
    the five CV-21 escapes in their canonical uppercase form (compared case-sensitively;
    ENG-COST-LOOKUP-R1a). Structure only: which contract the head names is not a question here."""
    parts = key.split("/")
    if len(parts) != 2:
        return "the key is not <head>/<element> (one separator)"
    head, element = parts
    if not head or not element:
        return "an empty component"
    body = head[len(_PORTFOLIO_MARKER) :] if head.startswith(_PORTFOLIO_MARKER) else head
    for component in (body, element):
        if any(character in component for character in "@#:"):
            return "an unencoded separator in a component"
        index = component.find("%")
        while index != -1:
            # Case-sensitive: CV-21 encoding is canonical uppercase; a lowercase token in a
            # stored key is malformed, never normalised into acceptance (ENG-COST-LOOKUP-R1a).
            if component[index : index + 3] not in _KEY_ESCAPE_CODES:
                return "an escape other than %25 %2F %40 %23 %3A"
            index = component.find("%", index + 3)
    return None


@dataclass(frozen=True, slots=True)
class GroupView:
    """``GroupInput`` with products and portfolios as mappings by code (§0.11)."""

    group: GroupInput
    products: Mapping[str, ProductInput]
    portfolios: Mapping[str, tuple[str, ...]]  # portfolio code -> member contract keys
    previous_stream_heads: Mapping[str, int]  # contract key -> stream version


@dataclass(frozen=True, slots=True)
class ContractView:
    """Header, booking payload and per-book status of a member contract (§0.11; stage 02)."""

    header: ContractInput  # judgements, material rights and modifications included
    booking: Mapping[str, object]  # CONTRACT_BOOKED payload, decimals as Fraction (CV-30)
    status_in_book: Mapping[str, tuple[tuple[date, str], ...]]  # book -> ascending (date, E-17)


@dataclass(frozen=True, slots=True)
class TemplateIndex:
    versions: Mapping[str, tuple[TemplateInput, ...]]  # template code -> ascending version_no


@dataclass(frozen=True, slots=True)
class RuleSetIndex:
    versions: Mapping[str, tuple[RuleSetInput, ...]]  # E-55 kind -> (rule_set_code, version_no)


@dataclass(frozen=True, slots=True)
class SspIndex:
    versions: Mapping[str, tuple[SspVersionInput, ...]]  # SSP book code -> ascending version_no


@dataclass(frozen=True, slots=True)
class RateIndex:
    rates: tuple[FxRateInput, ...]  # bundle order


@dataclass(frozen=True, slots=True)
class PostedIndex:
    amounts: tuple[PostedAmountInput, ...]  # bundle order


@dataclass(frozen=True, slots=True)
class Finding:
    """A stage finding (CV-40); ``stage`` and ``event_key`` only order findings (CV-43)."""

    code: str  # 04 §15.4 literal
    severity: str  # ERROR | WARNING | INFO
    subject_key: str | None
    detail: Mapping[str, str]  # no personal data (DG-ENG-06)
    stage: int
    event_key: str | None

    def sort_key(self) -> tuple[int, str, str, str, bytes]:
        """CV-43: (stage, code, subject key, event key, canonical JSON of detail)."""
        return (
            self.stage,
            self.code,
            self.subject_key or "",
            self.event_key or "",
            canonical_bytes(self.detail),
        )


@dataclass(frozen=True, slots=True)
class CanonicalBundle:
    """Stage 01 output, book-independent (§0.11)."""

    bundle: InputBundle  # the original, for hashing and source references
    currencies: CurrencyTable
    group: GroupView
    contracts: Mapping[str, ContractView]  # external_id -> view
    events: tuple[EventView, ...]  # after voids (S01-R-12), ENG-06 order
    boundary_events: tuple[EventView, ...]  # Table 0.3-A types, first CONTRACT_BOOKED excluded
    measure_events: tuple[EventView, ...]  # every other included event
    ledger: QuantityLedger
    templates: TemplateIndex
    rule_sets: RuleSetIndex
    ssp_books: SspIndex
    estimates: EstimatePins
    fx: RateIndex
    posted: PostedIndex
    books: Mapping[str, BookInput]
    entities: Mapping[str, EntityView]
    findings: tuple[Finding, ...]


# --- Allocation state (ENGINE_SPEC §0.11, §4.1, §5.1; ENGINE_SPEC_B §0.5) ------------------------


@dataclass(frozen=True, slots=True)
class Quota:
    """CV-34: exact allocation X and posted allocation A (minor units)."""

    x_exact: Fraction
    a_posted: int


# The revenue basis a concession producer stamps on its refund quota (ENGINE_SPEC_B S10-R-26;
# D-91 C606-03 as ruled on L9-ENG-B3-Q-1): EMBEDDED when the producer applied the concession to
# the obligation's recognition segment, so the stage 09 ``revenue_cum`` node already carries it;
# SEPARATE when the concession posts a reduction the revenue node does not carry.
CONCESSION_EMBEDDED: Final = "EMBEDDED"
CONCESSION_SEPARATE: Final = "SEPARATE"


@dataclass(frozen=True, slots=True)
class ConcessionQuota(Quota):
    """A ``CONCESSION`` refund quota (S06-R-09, D-88 L7-5-Q-4 (iii)) with the producer-derived
    revenue basis the share-based numerator reads (S10-R-26): ``EMBEDDED`` or ``SEPARATE``."""

    revenue_basis: str


@dataclass(frozen=True, slots=True)
class ConcessionAddition:
    """One accepted addition to an obligation's ``CONCESSION`` refund quota, as its producer
    computed it (the dated source subledger the share-based numerator reads; ENGINE_SPEC_B
    S10-R-26; D-91 L9-ENG-B3-Q-1). ``exact`` and ``posted`` are the producer's signed exact share
    and its separately allocated posted minor units (never re-rounded): stage 06 −receiver.exact /
    −receiver.posted (S06-R-09 under CREDIT_OR_REFUND), stage 08 −share.exact / −share.delta (D-88
    L7-5-Q-4 (iii)). Per (obligation, producing event): Σ exact = quota.x_exact and Σ posted =
    quota.a_posted; a zero-posted, negative-exact entry is legitimate deferred targeted-cent
    history. The aggregate refund component, its trace node and JET-05c are unchanged."""

    subject_key: str  # the receiving obligation
    event_key: str  # the producing CONTRACT_AMENDED or ESTIMATE_CHANGED event
    effective_date: date
    order_key: OrderKey  # ENG-06 position of the producing event (same-day ordering)
    exact: Fraction  # currency units, the concession as a positive amount
    posted: int  # minor units, as allocated by the producer
    producer: str  # "06" | "08"
    revenue_basis: str  # CONCESSION_EMBEDDED | CONCESSION_SEPARATE, as the producer stamped it


@dataclass(frozen=True, slots=True)
class Quota1:
    """A transaction price component: exact value and posted minor units (§4.1)."""

    exact: Fraction
    posted: int


class SegmentCause(StrEnum):
    INCEPTION = "INCEPTION"
    MODIFICATION = "MODIFICATION"
    TP_CHANGE = "TP_CHANGE"
    ESTIMATE_CHANGE = "ESTIMATE_CHANGE"
    MATERIAL_RIGHT_EXERCISE = "MATERIAL_RIGHT_EXERCISE"
    TERMINATION = "TERMINATION"
    OPENING_BALANCE = "OPENING_BALANCE"


@dataclass(frozen=True, slots=True)
class ProgressBase:
    """Quantities at a PROSPECTIVE boundary (CV-62); zero for INCEPTION segments (CV-61)."""

    delivered_cum: Fraction
    costs_cum: Fraction
    hours_cum: Fraction
    boundary_date: date | None

    @classmethod
    def zero(cls) -> ProgressBase:
        return cls(Fraction(0), Fraction(0), Fraction(0), None)


@dataclass(frozen=True, slots=True)
class ProgressTotals:
    """Totals in force after a boundary: quantity, EAC element, term (ENGINE_SPEC_B §0.5)."""

    quantity: Fraction
    eac_element_code: str | None
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True, slots=True)
class AllocationSegment:
    """One allocation segment per boundary (CV-60 to CV-63)."""

    component: str  # "FIXED" | "PERIOD_VC" | "ROYALTY" (ENGINE_SPEC_B §9.2.1)
    effective_date: date
    event_key: str | None  # boundary event; None for inception
    cause: SegmentCause
    basis: str  # "INCEPTION" | "PROSPECTIVE"
    x_exact: Fraction  # X, currency units
    a_posted: int  # A, minor units
    base_revenue_posted: int  # R_k (PROSPECTIVE only, else 0)
    base_revenue_exact: Fraction  # b_k (CV-63)
    base_progress: ProgressBase
    totals: ProgressTotals
    progress_measure: str  # E-11 literal, "SSP_DELIVERED" or "UNITS_SINCE_BOUNDARY"
    unit_ssp: Fraction | None  # parity reclass key (DEV-075)
    remaining_ssp: Fraction
    remaining_billing_plan: Fraction
    estimate_pair: tuple[str | None, str | None]  # (v_old, v_new) for ESTIMATE_CHANGE, TP_CHANGE
    modification_boundary_no: int  # 25-13(a) boundaries through this segment (REQ-MOD-020)


@dataclass(frozen=True, slots=True)
class SspResolution:
    """Snapshot feeding the T-CON-11 ``ssp_*`` and ``original_ssp_*`` columns (§5.1)."""

    book_code: str
    version_key: str
    version_label: str | None
    entry_key: str
    method: str  # E-47
    rate_key: str | None  # POL-079 conversion rate, never re-converted (32-43)
    unit_list_price: Fraction | None
    midpoint_discount_ratio: Fraction | None
    range_ratio: Fraction | None
    low: Fraction | None  # extended (× Q)
    mid: Fraction | None
    high: Fraction | None
    selected: Fraction  # original_ssp_selected
    in_range: bool | None
    point_policy: str  # POL-071 or POL-072 literal applied, or "POINT"
    residual_candidate: bool
    value_basis: str | None = None  # E-49 of the entry (D-93 (4) series pricing basis)
    quantity_unit: str | None = None  # E-125 of the entry (D-97 (3), PER_INCREMENT only)


@dataclass(frozen=True, slots=True)
class MaterialRightTerms:
    """Option terms with the resolved option SSP (§0.11; S03-R-07)."""

    terms: MaterialRightInput
    option_ssp: Fraction


@dataclass(frozen=True, slots=True)
class VcElementView:
    estimate_key: str
    element_code: str  # T-CON-12 raw code; the §0.4 key encodes it (CV-21)
    version_key: str  # pinned version
    amount: Quota1
    allocation_target: str
    obligation_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TpBuildUp:
    """04 API-S-ContractVersion ``transaction_price_buildup``, exact and posted (§4.1)."""

    at: date
    before_event_key: str | None
    fixed: Quota1
    vc_constrained: Quota1
    vc_excluded: Quota1
    expected_returns: Quota1
    consideration_payable: Quota1
    financing_adjustment: Quota1
    noncash: Quota1
    sales_tax_excluded: Quota1
    out_of_scope: Quota1
    # fixed + vc_constrained + expected_returns + consideration_payable + financing_adjustment
    # + noncash (memo members excluded)
    total: Quota1
    allocation_basis: Quota1  # total − expected_returns − consideration_payable (S04-R-02)
    elements: tuple[VcElementView, ...]
    # Σ S04-R-06 realised amounts inside vc_constrained (PERIOD_VC and ROYALTY components,
    # ENGINE_SPEC_B S09-R-01); they are allocated entirely to their obligation, so the FIXED
    # allocations sum to allocation_basis − realised (S06-INV-01; ENC-6).
    realised: Quota1 = Quota1(Fraction(0), 0)


TpView = tuple[TpBuildUp, ...]  # unconstrained, credit-adjusted TP build-up by date (S04-R-21)


@dataclass(frozen=True, slots=True)
class ReturnPin:
    effective_date: date
    version_key: str
    expected_quantity: Fraction
    carrying_cost_per_unit: Fraction | None
    recovery_cost_per_unit: Fraction | None
    window_end_date: date | None
    # A portfolio pin without expected_quantity: E = rate × units transferred (S04-R-08; PT-06)
    rate: Fraction | None = None


@dataclass(frozen=True, slots=True)
class ReturnPath:
    """Expected-returns path of a returnable obligation published by stage 04 (S04-R-08b)."""

    estimate_key: str  # RETURN_RATE element
    pins: tuple[ReturnPin, ...]  # ascending effective_date
    r: tuple[tuple[date, Fraction], ...]  # x_exact ÷ Q of the segment in force at each date
    p_ref: Fraction  # billed unit price of transferred units, else the stated unit price
    policy: Mapping[str, str]  # resolved POL-051 to POL-053 values


@dataclass(frozen=True, slots=True)
class Target:
    """One cumulative target point (ENGINE_SPEC_B §0.6)."""

    book_code: BookCode
    entity: str  # C-04 owner entity
    subject_key: str
    measure: str  # for example "revenue_cum", "refund_liability", "cost_amortised_cum"
    period_key: str
    cause: str | None  # E-28 line type or driver for decomposed measures
    value: int  # minor units, signed (C-02)
    exact: Fraction | None
    node_id: str  # trace node (C-07)


@dataclass(frozen=True, slots=True)
class DepositRelease:
    """A 606-10-25-7 recognition stage 02 published (ENGINE_SPEC S02-R-07 rev 1.6; D-91).

    Stage 09 attributes the contract-level recognitions to the contract's in-scope obligations
    (ENGINE_SPEC_B S14-R-25) and nets the STEP1_MET catch-up against them (S02-R-04); ``timed``
    marks a recognition at a dated point without an event, the ``CLOSE_RELEASE`` ``TIME`` share.
    """

    contract_key: str
    entity: str  # contracting entity (C-04)
    reason: str  # EVENT_25_7_A | EVENT_25_7_B | EVENT_25_7_C
    effective_date: date
    order_key: OrderKey
    amount: Fraction  # exact, currency units
    node_id: str  # the stage 02 ``deposit_to_revenue@…`` node
    timed: bool


@dataclass(frozen=True, slots=True)
class SpecialistTargets:
    """EMOD-12, 18, 21, 22 and 23 cumulative targets per period (§0.11; Table 0.11-A)."""

    deposit: tuple[Target, ...]  # EMOD-12 (stage 02)
    financing: tuple[Target, ...]  # EMOD-18 (stage 04)
    warranty: tuple[Target, ...]  # EMOD-21 (stage 04)
    customer_consideration: tuple[Target, ...]  # EMOD-22 (stage 04)
    noncash: tuple[Target, ...]  # EMOD-23 (stage 04)
    # The dated 25-7 recognitions behind ``deposit_to_revenue_cum`` (S02-R-07 rev 1.6; D-91).
    deposit_releases: tuple[DepositRelease, ...] = ()


# ENGINE_SPEC_B §15.2.5 S15-R-15 (EDS-4): the disaggregation dimension values of an obligation,
# stamped on ``ObligationState.dimensions`` by stages 05 and 06 and written by stage 14 on its
# ``REVENUE`` lines. Attribute codes are the template's own (T-REF-23) plus these derived ones.
TIMING_OF_TRANSFER: Final = "timing_of_transfer"
DISAGGREGATION_DERIVED: Final = (
    "product_family",
    "revenue_category",
    "region",
    "channel",
    "contract_type",
    "performing_entity",
    TIMING_OF_TRANSFER,
)


def disaggregation_tags(
    canonical: CanonicalBundle,
    *,
    contract_key: str,
    template_version_key: str,
    product_code: str | None,
    performing_entity: str,
    satisfaction_pattern: str,
    revenue_category: str | None,
) -> Mapping[str, str]:
    """S15-R-15: the template ``disaggregation`` mapping (T-REF-23), product family and revenue
    category (T-REF-20), contract region, channel and contract type (T-CON-01), the performing
    entity and ``timing_of_transfer`` ∈ {POINT_IN_TIME, OVER_TIME} from the satisfaction pattern
    (E-19). Absent values are omitted; a template attribute of the same code as a derived one is
    kept (the template is the configured source). Sorted by code."""
    tags: dict[str, str] = {}
    if product_code is not None:
        product = canonical.group.products.get(product_code)
        if product is not None and product.product_family is not None:
            tags["product_family"] = product.product_family
    if revenue_category is not None:
        tags["revenue_category"] = revenue_category
    contract = canonical.contracts.get(contract_key)
    if contract is not None:
        header = contract.header
        for code, value in (
            ("region", header.region),
            ("channel", header.channel),
            ("contract_type", header.contract_type),
        ):
            if value is not None:
                tags[code] = str(value)
    for versions in canonical.templates.versions.values():
        for version in versions:
            if version.version_key == template_version_key:
                tags.update({str(k): str(v) for k, v in version.disaggregation.items()})
    tags["performing_entity"] = performing_entity
    tags[TIMING_OF_TRANSFER] = (
        "OVER_TIME" if str(satisfaction_pattern) == "OVER_TIME" else "POINT_IN_TIME"
    )
    return MappingProxyType(dict(sorted(tags.items())))


@dataclass(frozen=True, slots=True)
class ObligationState:
    """Obligation terms and segments (ENGINE_SPEC_B §0.5 members, then the §0.11 additions)."""

    subject_key: str
    contract_key: str
    obligation_key: str
    obligation_kind: ObligationKind  # E-18
    distinctness: Distinctness  # E-105
    satisfaction_pattern: SatisfactionPattern  # E-19
    recognition_method: RecognitionMethod  # E-11
    ratable_convention: RatableConvention | None  # E-21
    principal_agent: PrincipalAgent  # E-89
    licence_nature: LicenceNature  # E-90
    scope_flag: ScopeFlag  # E-77
    start_date: date | None
    end_date: date | None
    recognition_start_date: date | None  # V5; POL-025 (S03-R-10)
    contracting_entity: str
    performing_entity: str
    quantity: Fraction  # Q after modifications
    resolved_ssp: Fraction
    revenue_category: str | None
    dimensions: Mapping[str, str]  # S15-R-15 disaggregation tags (``disaggregation_tags``)
    account_overrides: Mapping[str, str]  # role literal or "BILLING_CLEARING:<purpose>" -> account
    segments: tuple[AllocationSegment, ...]  # first cause INCEPTION or OPENING_BALANCE
    opening: OpeningBalanceView | None
    terminated_on: date | None
    template_version_key: str
    product_code: str | None
    sku_number: str | None
    stratification: str | None
    series_increment_unit: str | None
    over_time_criterion: str  # E-20
    warranty_type: WarrantyType  # E-91
    material_right: MaterialRightTerms | None
    ssp: SspResolution | None
    original_quantity: Fraction
    original_stated_price: Fraction
    stated_price: Fraction
    original_allocation: Quota
    original_total_contract_price: Fraction
    original_total_contract_ssp: Fraction
    is_vc_line: bool  # parity VC_LINE
    gross_to_net: Mapping[str, str] | None  # agent pass-through basis (§3.3)
    lineage_pre_modification: tuple[str, ...]  # POL-106
    assurance_cost_per_unit: Fraction | None
    last_modification_key: str | None
    # S08-R-04 routing weight fixed at inception: the selected SSP, or the residual R of the
    # residual candidate (S05-R-12); SSP changes after inception never re-weight (rev 1.6, D-91).
    inception_weight: Fraction
    # D-98 candidate 117 (CV-47 (b)): the node(s) whose exact values sum to the CURRENT
    # ``original_allocation`` — at inception the stage 05 ``original_allocated_exact:<ob>:-`` node
    # with the obligation's ``targeted_vc_allocated@<estimate>:<ob>:-`` shares (S05-R-10 totals),
    # after ``attributes.reallocate`` (S06-R-26) the repin's ``mod_share@<event>:<ob>:-`` share
    # alone. Empty where no producer is stamped (an obligation a boundary adds).
    original_allocation_nodes: tuple[str, ...] = ()
    # D-98 candidate 121 (CV-50): the ``<column>@<event>`` pair — (exact node id, amount node id) —
    # stamped at the write of ``original_allocation`` when the columns' producer is not the stage
    # 05 version-state node: the S05-R-10 sum pair under the booking event (targeted shares), the
    # repin's pair (S06-R-26), a created obligation's pair. None: the version-state nodes. The
    # assembler links by this identity and asserts the link holds the value; it never picks a node
    # by value.
    original_allocation_links: tuple[str, str] | None = None
    # D-98 candidates 123 / 124 (CV-50, rev 1.29): the producer identity, per snapshot column, when
    # it is not the stage 05 version-state node — the repin's / creating boundary's
    # ``<column>@<event>`` node for original_ssp_selected, original_unit_ssp,
    # original_total_contract_ssp, original_stated_price, original_total_contract_price and
    # allocation_weight. The assembler links by this identity and asserts the link holds.
    snapshot_producer_links: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class AllocatedState:
    """State after the boundary fold (ENGINE_SPEC_B §0.5 members, then the §0.11 additions)."""

    group_code: str
    inception_date: date
    contracts: tuple[ContractView, ...]
    obligations: tuple[ObligationState, ...]  # subject key
    events: tuple[EventView, ...]
    measure_events: tuple[EventView, ...]
    ledger: QuantityLedger
    return_paths: Mapping[str, ReturnPath]  # obligation subject key -> path
    estimates: EstimatePins
    tp_unconstrained: Mapping[str, TpView]  # contract key -> build-ups by date
    specialist_targets: SpecialistTargets
    proposals: tuple[ProposalOut, ...]
    time_triggers: tuple[TimeTrigger, ...]
    tp_history: tuple[TpBuildUp, ...]  # one per boundary (S04-R-01)
    targeted_vc_quotas: Mapping[str, Mapping[str, Quota]]  # estimate key -> obligation -> quota
    # estimate key -> obligation -> ((effective date, quota), ...) in ENG-06 order, the first entry
    # the inception quota: the targeted quota in force at any measured date (S05-R-14, S08-R-07;
    # ENGINE_SPEC_B S15-R-09; rev 1.6, D-91). ``targeted_vc_quotas`` holds the latest quota.
    targeted_vc_quota_history: Mapping[str, Mapping[str, tuple[tuple[date, Quota], ...]]]
    refund_components: Mapping[str, Quota]  # obligation subject key -> refund quota (S06-R-09)
    findings: tuple[Finding, ...]
    # The dated additions behind the CONCESSION refund quotas, in ENG-06 order (S10-R-26; D-91).
    concession_history: tuple[ConcessionAddition, ...] = ()


@dataclass(frozen=True, slots=True)
class ScheduleLineOut:
    """T-ENG-02 line without surrogate ids (ENGINE_SPEC_B §0.6)."""

    schedule_kind: ScheduleKind  # E-27
    subject_type: str  # "obligation" | "contract_cost_asset" | "contract"
    subject_key: str
    entity: str
    period_key: str
    line_type: ScheduleLineType  # E-28
    amount: int
    cumulative_amount: int
    cumulative_exact: Fraction
    quantity: Fraction | None
    is_released_at_close: bool
    trace_node_id: str
