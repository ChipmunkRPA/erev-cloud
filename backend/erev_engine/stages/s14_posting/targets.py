"""Stage 14 part targets, role lines and role targets (ENGINE_SPEC_B §14.2.1, §14.2.2; END-4, 5).

Private to stage 14 (DG-ENG-07). A part target is a signed cumulative amount per (book, owner
entity, subject, part) and period end, in the transaction currency with its functional amount from
stage 12 (S14-R-01). The parts built so far:

- the revenue relief of an obligation (S10-R-09: ``revenue_cum`` plus concession components) posts
  through ``JET-02 principal``, ``JET-02 agent``, or ``JET-13 contracting`` when stage 12 published
  a pair for the obligation; JET-04a, JET-05a, JET-05b and JET-08 expiry have no target of their
  own, so a price change settled through future pricing lowers the relief (S14-R-02) and an
  expiry or a prepaid-credit lapse raises it with cause ``NORMAL`` (S14-R-03). The target keeps
  its cumulative amount by E-28 cause;
- ``JET-13 performing`` from the stage 12 pairs, in the performing entity's calendar (S12-R-17);
- ``JET-04b`` per refund-liability component, the unclaimed-property part included (S09-R-28), less
  the concession amounts that ``JET-05c`` created;
- ``JET-10a`` to ``JET-10d`` from the stage 12 remeasurement targets;
- ``JET-06 reclass`` from the stage 10 attributions: the cumulative sum of the period attributions,
  so that its period target is the attribution of the period (S14-R-07);
- ``JET-03 invoice`` from the unconditional billing and tax of ``ENGINE`` mode (POL-004);
- ``JET-15`` in the ``LEGACY`` book from the stage 13 fold ``pre_standard_revenue_cum`` (S13-R-08);
- ``JET-12`` per loss unit from the stage 11 required provision ``loss_provision_required``
  (S11-R-14), the whole amount ``TIME`` of the ``CLOSE_RELEASE`` pass (Table 14-A; D-92 (3)).

A functional amount comes from stage 12; at rate 1 the transaction amount is the functional amount,
and a foreign-currency part without its stage 12 amount fails closed. Every part target also
carries its ``TIME`` share (RCP-07; L2-5-Q-29) and the node inputs whose signed sum is its amount.

``role_lines`` derives the signed role amounts of a part: the debit roles take +amount and the
credit roles −amount, a split side apportions with ``largest_remainder`` (S14-R-01, S14-R-10), and
a negative economic effect therefore swaps the sides with non-negative line amounts (R4; POLICIES
§0.9). ``role_targets`` sums the role lines of every part per role key and period end, carrying
each part's latest target forward through the horizon, and emits one ``posting_target`` node per
role key and period (§14.6). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.enums import PrincipalAgent
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import format_money, largest_remainder, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key, encode_key
from erev_engine.stages.s09_recognition import (
    DEPOSIT_SHARE_MEASURE,
    DEPOSIT_TIME_SHARE_MEASURE,
    deposit_share_weights,
)
from erev_engine.stages.s12_fx_entities import FxState, FxTarget, IcPair, RateRef
from erev_engine.stages.s14_posting.amount_classes import AMOUNT_CLASSES, TIME
from erev_engine.stages.s14_posting.templates import (
    BY_SUBJECT,
    INTERCOMPANY_ROLES,
    JET_PARTS,
    ONE,
    JetPart,
    Side,
)
from erev_engine.stages.state import BookContext, ObligationState, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "COMPONENT_KINDS",
    "DEPOSIT_PART_MEASURES",
    "DEPOSIT_REVENUE_MEASURE",
    "DEPOSIT_REVENUE_PART",
    "FX_ENTRY_KIND",
    "NodeInput",
    "PartInputs",
    "PartTarget",
    "RoleKey",
    "RoleLine",
    "RoleTarget",
    "RoleVariant",
    "UNTAGGED",
    "encode_component",
    "part_targets",
    "role_lines",
    "role_targets",
]

RELIEF_MEASURE: Final = "revenue_relief_cum"
RELIEF_BY_CAUSE_MEASURE: Final = "revenue_relief"
REFUND_LIABILITY_MEASURE: Final = "refund_liability"
CONCESSION_MEASURE: Final = "concession_created_cum"
RECLASS_MEASURE: Final = "netting_reclass_amount"
INVOICE_MEASURE: Final = "billed_unconditional_cum"
INVOICE_TAX_MEASURE: Final = "sales_tax_billed_cum"
RECEIVABLE_CONTRA_MEASURE: Final = "receivable_contra"  # S10-R-18 (JET-04c)
PRE_STANDARD_MEASURE: Final = "pre_standard_revenue_cum"  # ENGINE_SPEC_B §13.5 (END-8)
FINANCING_MEASURE: Final = "financing_interest_cum"  # EMOD-18 (ENGINE_SPEC S04-R-12, S04-R-13)
RETURN_ASSET_MEASURE: Final = "return_asset"  # §10.2.5
RETURN_DERECOGNISED_MEASURE: Final = "return_asset_derecognised_cum"  # S10-R-16
LOSS_PROVISION_MEASURE: Final = "loss_provision_required"  # §11.5 (S11-R-14; JET-12; D-92 (3))
UNTAGGED: Final = (
    "UNTAGGED"  # the variant of the shares without a template reason (S14-R-27; §14.6)
)
# The JET-11 part of each stage 04 financing cause: the schedule kind or the part id (L4-3-Q-18).
_FINANCING_PARTS: Final[Mapping[str, str]] = MappingProxyType(
    {"DEFERRED": "JET-11a", "JET-11a": "JET-11a", "ADVANCE": "JET-11b", "JET-11b": "JET-11b"}
)
# The JET-01b part of each stage 02 cumulative deposit measure (S02-R-08; Table 14-A). The 25-7
# revenue measure is bound since END-4b (D-91 gaps (x)): stage 13 reads this one constant too.
DEPOSIT_REVENUE_MEASURE: Final = "deposit_to_revenue_cum"
# The stage 12 functional target of the dated (TIME) 25-7 releases at their own conversion
# (S12-R-20, S14-R-05; D1-R04): the sixth EMOD-12 measure, not a part of its own.
DEPOSIT_REVENUE_TIME_MEASURE: Final = "deposit_to_revenue_time_cum"
DEPOSIT_REVENUE_PART: Final = "JET-01b 25-7 revenue"
_DEPOSIT_PARTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "deposit_received_cum": "JET-01b receipt",
        "deposit_to_contract_liability_cum": "JET-01b criteria met",
        "deposit_refunded_cum": "JET-01b refund",
        DEPOSIT_REVENUE_MEASURE: DEPOSIT_REVENUE_PART,
    }
)
DEPOSIT_PART_MEASURES: Final = frozenset(_DEPOSIT_PARTS)
# The EMOD-22 measures behind the JET-14 parts (S04-R-14 to S04-R-17; ENGINE_SPEC_B S10-R-26;
# Table 14-A; D-91): the stage 04 payable and ordinary release, the stage 10 share-based reduction
# and the composed release the parts must sum to (S14-R-11).
CPC_PAYABLE_MEASURE: Final = "consideration_payable"
CPC_ORDINARY_MEASURE: Final = "incentive_release_ordinary_cum"
CPC_SHARE_BASED_MEASURE: Final = "share_based_reduction_cum"
CPC_RELEASE_MEASURE: Final = "incentive_release_cum"
_CPC_MEASURES: Final = frozenset(
    {CPC_PAYABLE_MEASURE, CPC_ORDINARY_MEASURE, CPC_SHARE_BASED_MEASURE, CPC_RELEASE_MEASURE}
)
WARRANTY_MEASURE: Final = "warranty_accrual_cum"  # EMOD-21 (S04-R-19; JET-16 accrual)
# The JET-17 part of each stage 04 EMOD-23 cumulative measure (S04-R-18; Table 14-A).
_NONCASH_PARTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "noncash_asset_recognised_cum": "JET-17 unconditional",
        "noncash_received_cum": "JET-17 receipt",
    }
)
_LEGACY_BOOK: Final = "LEGACY"
# ENGINE_SPEC_B §10.2.4 refund-liability components.
COMPONENT_KINDS: Final = frozenset(
    {"RETURN", "VARIABLE_CONSIDERATION", "TERMINATION", "CONCESSION", "UNCLAIMED_PROPERTY"}
)
RECLASS_ROLES: Final = ("UNBILLED_RECEIVABLE", "CONTRACT_ASSET")
FX_ENTRY_KIND: Final = "FX_REMEASUREMENT"  # its role targets carry functional amounts only
_REMEASUREMENT_PARTS: Final = frozenset({"JET-10a", "JET-10a′", "JET-10b", "JET-10c", "JET-10d"})
_PERIOD_END_PARTS: Final = frozenset({"JET-10a", "JET-10a′", "JET-10b", "JET-10d"})
_REMEASURED: Final = frozenset({"ASSET_LAYER_REMEASURED", "LIABILITY_LAYER_REMEASURED"})
_AP_SUPPLIER: Final = "BILLING_CLEARING:AP_SUPPLIER"
# A node input and its sign in the target's sum: 1, -1, or 0 for a node cited without adding it.
NodeInput = tuple[str | SourceRef, int]


def encode_component(component: str) -> str:
    """CV-21 percent-encoding of one key component (``%``, ``/``, ``@``, ``#``, ``:``): stage 01's
    ``encode_key`` (one table for every lookup; ENG-COST-ENC-1)."""
    return encode_key(component)


@dataclass(frozen=True, slots=True)
class PartInputs:
    """The cumulative producer targets stage 14 reads from stages 09 to 11 (L2-5-Q-24, L2-5-Q-29).

    ``relief``: ``revenue_relief_cum`` per obligation, contracting entity and period end (S10-R-09).
    ``relief_by_cause``: ``revenue_relief`` period amounts per obligation and E-28 cause (§9.2.10),
    in the contracting entity's calendar. ``refund_liabilities``: ``refund_liability`` balances per
    subject, component kind (``cause``) and period end (§10.2.4). ``concessions``:
    ``concession_created_cum`` per obligation and period end (JET-05c). ``released_at_close``: the
    obligations whose ``NORMAL`` revenue is released at close (T-ENG-02 ``is_released_at_close``).
    ``reclass``: ``netting_reclass_amount`` per obligation and period end with the reclass role as
    ``cause`` (§10.2.7). ``invoices`` and ``invoice_tax``: cumulative unconditional billing and tax
    per obligation under ``billing.posting = ENGINE`` (JET-03). ``pre_standard``: the ``LEGACY``
    book's ``pre_standard_revenue_cum`` per obligation, contracting entity and period end (JET-15;
    ENGINE_SPEC_B S13-R-08; END-8). ``financing``: the stage 04 ``financing_interest_cum`` per
    ``<contract>@<entity>`` and period end, with the schedule kind as ``cause`` (JET-11a, JET-11b;
    S10-R-10; L4-3-Q-30). ``return_assets``: the stage 10 ``return_asset`` and
    ``return_asset_derecognised_cum`` per obligation and period end (JET-07c, JET-07d; S10-R-16).
    """

    relief: tuple[Target, ...] = ()
    relief_by_cause: tuple[Target, ...] = ()
    refund_liabilities: tuple[Target, ...] = ()
    concessions: tuple[Target, ...] = ()
    released_at_close: tuple[str, ...] = ()
    reclass: tuple[Target, ...] = ()
    invoices: tuple[Target, ...] = ()
    invoice_tax: tuple[Target, ...] = ()
    # ENGINE mode receivable contra per <contract>@<entity> and period end (S10-R-18; JET-04c).
    receivable_contra: tuple[Target, ...] = ()
    pre_standard: tuple[Target, ...] = ()
    financing: tuple[Target, ...] = ()
    return_assets: tuple[Target, ...] = ()
    # The stage 02 EMOD-12 cumulative deposit measures per <contract>@<entity> and period end
    # (S02-R-08; JET-01b receipt, criteria met, refund and 25-7 revenue; L4-1-Q-15; D-91).
    deposits: tuple[Target, ...] = ()
    # The stage 09 ``deposit_revenue_share`` and ``deposit_revenue_time_share`` targets per
    # obligation and contracting period end: the S14-R-25 attribution the JET-01b 25-7 revenue
    # part posts per obligation, its time share the CLOSE_RELEASE amount (D-91 gaps (iii), (iv)).
    deposit_revenue: tuple[Target, ...] = ()
    # The stage 04 EMOD-22 ``consideration_payable``, ``incentive_release_cum`` and
    # ``share_based_reduction_cum`` per <contract>@<entity> and period end (S04-R-14 to S04-R-17;
    # JET-14 promised, release and share-based; lane L5-5).
    customer_consideration: tuple[Target, ...] = ()
    # The stage 04 EMOD-21 ``warranty_accrual_cum`` per product obligation and period end of the
    # performing entity (S04-R-19; JET-16 accrual; lane L5-5).
    warranties: tuple[Target, ...] = ()
    # The stage 04 EMOD-23 ``noncash_asset_recognised_cum`` and ``noncash_received_cum`` per
    # <contract>@<entity> and period end (S04-R-18; JET-17 unconditional and receipt; lane L5-5).
    noncash: tuple[Target, ...] = ()
    # The stage 11 cost asset measures per asset and period end, with the E-83 cost kind (OBTAIN
    # or FULFILL) as ``cause`` (S11-R-01 to S11-R-13; JET-09a to JET-09f; lane L5-5).
    cost_assets: tuple[Target, ...] = ()
    # The stage 10 ``supplier_share_cum`` S_t per agent obligation, contracting entity and period
    # end, the JET-02 agent supplier weight (D-87 L4-3-Q-24 (e)).
    agent_supplier: tuple[Target, ...] = ()
    # The stage 11 ``loss_provision_required`` per loss unit and period end of the contracting
    # entity: the provision balance S11-R-14 requires, whose period movement JET-12 posts (Table
    # 14-A; POLICIES JET-12; D-92 (3); lane ENG-C7).
    loss_provisions: tuple[Target, ...] = ()


@dataclass(frozen=True, slots=True)
class PartTarget:
    """A signed cumulative part target at a period end (S14-R-01)."""

    book_code: str
    entity: str  # owner entity (Table 14-A)
    subject_key: str
    part: str  # JET_PARTS key
    component: str | None  # refund-liability component, remeasured balance role or reclass role
    period_key: str  # of the owner entity's calendar
    txn_currency: str
    amount_txn: int  # signed, debit positive on the part's debit roles
    functional_currency: str
    amount_functional: int
    counterparty_entity: str | None  # intercompany parts only
    by_cause: tuple[tuple[str, int], ...]  # cumulative transaction amount by E-28 cause, sorted
    rates: tuple[RateRef, ...]  # pinned rates behind the functional amount (REQ-FX-006)
    node_ids: tuple[str, ...]  # producer and stage 12 nodes of the amounts
    time_txn: int = 0  # the TIME share of the cumulative amounts (RCP-07; L2-5-Q-29)
    time_functional: int = 0
    # Σ sign × input = the amount in the node currency (functional for JET-10 parts).
    value_inputs: tuple[NodeInput, ...] = ()
    # Per role label of a split side whose shares are component amounts (JET-03 net and tax).
    split_inputs: tuple[tuple[str, tuple[NodeInput, ...]], ...] = ()
    weights: tuple[tuple[str, Fraction], ...] = ()  # split side weights by role label

    @property
    def key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.book_code,
            self.entity,
            self.subject_key,
            self.part,
            self.component or "",
            self.period_key,
        )


@dataclass(frozen=True, slots=True)
class RoleLine:
    """A signed role amount of a part (debit positive, C-02)."""

    account_role: str
    clearing_purpose: str | None
    counterparty_entity: str | None
    signed_txn: int
    signed_functional: int

    @property
    def side(self) -> str:
        """``D`` or ``C``: the sign of the transaction amount, else of the functional one (R4)."""
        return "D" if (self.signed_txn or self.signed_functional) > 0 else "C"

    @property
    def amount_txn(self) -> int:
        return abs(self.signed_txn)

    @property
    def amount_functional(self) -> int:
        return abs(self.signed_functional)

    @property
    def label(self) -> str:
        """``<role>`` or ``BILLING_CLEARING:<purpose>`` (the override key of T-REF-15)."""
        if self.clearing_purpose is None:
            return self.account_role
        return f"{self.account_role}:{self.clearing_purpose}"


@dataclass(frozen=True, slots=True)
class RoleKey:
    """The posted grain of ``PostedAmountInput`` (§14.2.2; OQ-B-19)."""

    book_code: str
    entity: str
    subject_key: str
    entry_kind: str  # E-29
    account_role: str  # E-01
    clearing_purpose: str | None
    counterparty_entity: str | None

    def sort_key(self) -> tuple[str, str, str, str, str, str, str]:
        """CV-23 order of role keys."""
        return (
            self.book_code,
            self.entity,
            self.subject_key,
            self.entry_kind,
            self.account_role,
            self.clearing_purpose or "",
            self.counterparty_entity or "",
        )

    @property
    def node_subject(self) -> str:
        """``<subject>/<entry kind>/<role>[%3A<purpose>]`` (§14.6, components CV-21 encoded)."""
        role = self.account_role
        if self.clearing_purpose is not None:
            role = f"{role}{encode_component(':')}{self.clearing_purpose}"
        return f"{self.subject_key}/{self.entry_kind}/{role}"


@dataclass(frozen=True, slots=True)
class RoleVariant:
    """One reason variant of a role target (S14-R-27): the cumulative shares of the parts whose
    Table 14-A row stamps ``reason`` on their lines, or, for ``reason`` None, of every other part
    (the ``UNTAGGED`` remainder), with the variant's own ``posting_target`` node (§14.6)."""

    reason: str | None  # TERMINATION_ACCELERATION | CLAWBACK | None
    amount_txn: int
    amount_functional: int
    time_txn: int
    time_functional: int
    node_id: str

    @property
    def label(self) -> str:
        return UNTAGGED if self.reason is None else self.reason


@dataclass(frozen=True, slots=True)
class RoleTarget:
    """The cumulative signed target of a role key through a period end (S14-R-04)."""

    key: RoleKey
    period_key: str
    txn_currency: str
    functional_currency: str
    amount_txn: int
    amount_functional: int
    time_txn: int  # the TIME share (RCP-07)
    time_functional: int
    passes: tuple[str, ...]  # E-31 close-run passes of its TIME amounts (S14-R-05)
    rates: tuple[RateRef, ...]
    node_id: str  # posting_target node (§14.6)
    # S14-R-27: the reason variants, untagged first, when a part with a template reason shares the
    # role key; () for every other role key. The variants' amounts sum to the target's.
    variants: tuple[RoleVariant, ...] = ()


def _receivable_contra(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-04c`` per ``<contract>@<entity>``: the stage 10 receivable contra of ``ENGINE`` mode
    (S10-R-18; Table 14-A; POLICIES JET-04c, CHK-138; L4-3-Q-19, L5-3-Q-12)."""
    out: list[PartTarget] = []
    for target in inputs.receivable_contra:
        _require(target, RECEIVABLE_CONTRA_MEASURE, ctx)
        out.append(_plain(ctx, target, "JET-04c", None, target.value, ((target.node_id, 1),)))
    return out


def part_targets(ctx: BookContext, st: FxState, inputs: PartInputs) -> tuple[PartTarget, ...]:
    """The part targets of one book (S14-R-01 to S14-R-03, S14-R-07), sorted by key."""
    inputs = _within_horizon(ctx, inputs)
    found = [
        *_relief(ctx, st, inputs),
        *_performing(ctx, st.ic_pairs, frozenset(inputs.released_at_close)),
        *_refund_liabilities(ctx, inputs, st),
        *_receivable_contra(ctx, inputs),
        *_financing(ctx, inputs),
        *_return_assets(ctx, inputs),
        *_remeasurement(ctx, st),
        *_reclass(ctx, st, inputs),
        *_invoices(ctx, st, inputs),
        *_pre_standard(ctx, inputs),
        *_deposits(ctx, inputs, st),
        *_customer_consideration(ctx, inputs, st),
        *_warranties(ctx, inputs),
        *_noncash(ctx, inputs),
        *_cost_assets(ctx, inputs),
        *_loss_provisions(ctx, inputs, st),
    ]
    keys = [target.key for target in found]
    if len(set(keys)) != len(keys):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "two part targets share a book, owner entity, subject, part and period",
            detail={"rule": "S14-R-01"},
        )
    return tuple(sorted(found, key=lambda target: target.key))


_COST_PARTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "cost_capitalised": "JET-09a",
        "cost_amortised_cum": "JET-09b",
        "cost_impaired_cum": "JET-09c",
        "cost_impairment_reversed_cum": "JET-09d",
        "cost_accelerated_cum": "JET-09e",
        "cost_clawback_cum": "JET-09f",
    }
)
_COST_ASSET_ROLES: Final[Mapping[str, str]] = MappingProxyType(
    {"OBTAIN": "COST_TO_OBTAIN_ASSET", "FULFILL": "COST_TO_FULFILL_ASSET"}
)


def _cost_assets(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-09a`` to ``JET-09f`` per cost asset from the stage 11 measures (Table 14-A; S11-R-01
    to S11-R-13; lane L5-5).

    The E-83 cost kind (``cause``) selects ``JET-09a`` or ``JET-09a′`` and the asset role of the
    ``BY_SUBJECT`` sides. ``carrying_amount`` produces no part. Compute posts the amounts as EVENT
    deltas, as it posts relief (L3-2-Q-15; L5-5-Q-15).
    """
    out: list[PartTarget] = []
    for target in inputs.cost_assets:
        part = _COST_PARTS.get(target.measure)
        if part is None:
            continue
        _require(target, target.measure, ctx)
        role = _COST_ASSET_ROLES.get(str(target.cause))
        if role is None:
            raise ValueError(
                f"cost asset {target.subject_key}: cause {target.cause!r} names no E-83 cost kind"
            )
        component: str | None = role
        if part == "JET-09a":
            part = "JET-09a′" if target.cause == "FULFILL" else part
            component = None
        out.append(_plain(ctx, target, part, component, target.value, ((target.node_id, 1),)))
    return out


def _loss_provisions(
    ctx: BookContext, inputs: PartInputs, st: FxState | None = None
) -> list[PartTarget]:
    """``JET-12`` per loss unit from the stage 11 required provision (Table 14-A; S11-R-14;
    D-92 (3)).

    The cumulative target is the provision balance required at the period end, so the S14-R-04
    period delta is the movement required(t) − required(t − 1) of S11-R-14: an increase debits
    ``LOSS_EXPENSE`` and credits ``LOSS_PROVISION``, a release the reverse (POLICIES JET-12). The
    whole amount is ``TIME`` (05 RCP-07 rev 1.2; Table 14-A), so the ``CLOSE_RELEASE`` pass posts it
    for open periods and a compute posts it only as a closed-period carry (RCP-08(a); S14-R-05).
    Stage 11 measures only the units in the book's loss scope (S11-R-15), so a contract outside
    the POL-151 scope binds no target here.

    A foreign-currency part takes the stage 12 functional amount of its measure when stage 12
    publishes one for the loss unit and period (``loss_provision_required``; S14-R-01), as every
    other part does; without one it fails closed (L3-2-Q-14), because §12 names no loss-provision
    flow today (G12 AD-31: monetary or non-monetary item, remeasurement rate). A same-currency
    part converts at rate 1.
    """
    functional = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure == LOSS_PROVISION_MEASURE
        }
    )
    out: list[PartTarget] = []
    for target in inputs.loss_provisions:
        _require(target, LOSS_PROVISION_MEASURE, ctx)
        fx = functional.get((target.entity, target.subject_key, target.period_key))
        out.append(
            _plain(
                ctx, target, "JET-12", None, target.value, ((target.node_id, 1),), time=True, fx=fx
            )
        )
    return out


def _within_horizon(ctx: BookContext, inputs: PartInputs) -> PartInputs:
    """The producer targets at or before their entity's horizon (C-05; S14-R-04; lane L5-5).

    Stage 09 projects deterministic relief to the term end, while stage 12 publishes functional
    amounts and stage 14 derives role targets only through the horizon (S12-R-13, S14-R-04), so a
    target after the horizon never reaches a role target and needs no functional amount. A target
    whose period or entity the context does not know is kept, so ``_require`` and the calendar
    checks still refuse it (CV-45).
    """
    changes: dict[str, tuple[object, ...]] = {}
    for member in dataclasses.fields(inputs):
        values = getattr(inputs, member.name)
        kept = tuple(item for item in values if not _after_horizon(ctx, item))
        if len(kept) != len(values):
            changes[member.name] = kept
    return dataclasses.replace(inputs, **changes) if changes else inputs  # type: ignore[arg-type]


def _after_horizon(ctx: BookContext, item: object) -> bool:
    if not isinstance(item, Target) or item.entity not in ctx.entities:
        return False
    horizon = ctx.horizon.get(item.entity)
    position = _positions(ctx, item.entity)
    if horizon is None or horizon not in position or item.period_key not in position:
        return False
    return position[item.period_key] > position[horizon]


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=subject_key,
        detail={**detail, "rule": "S14-R-01"},
    )


def _functional(
    ctx: BookContext, target: Target, amount: int, fx: FxTarget | None
) -> tuple[int, tuple[RateRef, ...], tuple[str, ...]]:
    """The stage 12 functional amount of a part amount, or the amount itself at rate 1."""
    if fx is not None:
        if fx.amount_txn != amount:
            raise _invariant(
                "stage 12 converts another transaction amount than the part target",
                target.subject_key,
                part_amount=str(amount),
                period_key=target.period_key,
                stage_12_amount=str(fx.amount_txn),
            )
        return fx.amount_functional, fx.rates, (fx.node_id,)
    if ctx.entities[target.entity].functional_currency == ctx.txn_currency or amount == 0:
        return amount, (), ()
    raise _invariant(
        "stage 12 publishes no functional amount for a foreign-currency part target",
        target.subject_key,
        measure=target.measure,
        period_key=target.period_key,
    )


def _time_share(time_txn: int, amount_txn: int, amount_functional: int) -> int:
    """The functional TIME share: proportional to the transaction split, rounded half up."""
    if time_txn == amount_txn:
        return amount_functional
    if time_txn == 0 or amount_txn == 0:
        return 0
    return round_half_up(Fraction(time_txn * amount_functional, amount_txn), 0)


def _require(target: Target, measure: str, ctx: BookContext) -> None:
    if target.measure != measure or target.book_code != ctx.book_code:
        raise ValueError(
            f"a part input of measure {target.measure!r} in book {target.book_code} is not "
            f"{measure!r} of {ctx.book_code} (CV-45)"
        )
    if target.entity not in ctx.entities:
        raise ValueError(f"a part input names the entity {target.entity!r}, absent (CV-45)")


def _relief_part(ob: ObligationState, paired: bool) -> str:
    if paired:
        return "JET-13 contracting"  # POL-170 PERFORMING_ENTITY with another performing entity
    if ob.principal_agent == PrincipalAgent.AGENT:
        return "JET-02 agent"
    return "JET-02 principal"


def _agent_weights(
    ob: ObligationState, relief: int = 0, supplier: int = 0
) -> tuple[tuple[str, Fraction], ...]:
    """The retained and supplier weights of an agent obligation (POL-030; L2-5-Q-32).

    D-87 L4-3-Q-24 (e): ``FIXED_FEE`` and ``SUPPLIER_COST`` weigh (R_t, S_t) = (relief − S_t, S_t)
    of the cumulative relief; nil relief takes the revenue side only. ``COMMISSION_RATE`` keeps
    (ρ, 1 − ρ). Stage 03 names the basis ``basis``; ``gross_to_net_basis`` is read too.
    """
    basis = ob.gross_to_net or {}
    name = basis.get("gross_to_net_basis") or basis.get("basis")
    if name in ("FIXED_FEE", "SUPPLIER_COST"):
        if supplier < 0 or supplier > relief:
            raise _invariant(
                "the supplier share lies outside [0, relief]",
                ob.subject_key,
                relief=str(relief),
                supplier=str(supplier),
            )
        if relief == 0:
            return (("REVENUE", Fraction(1)), (_AP_SUPPLIER, Fraction(0)))
        return (("REVENUE", Fraction(relief - supplier)), (_AP_SUPPLIER, Fraction(supplier)))
    if name != "COMMISSION_RATE" or "rate" not in basis:
        raise ValueError(
            f"agent obligation {ob.subject_key}: the supplier split needs gross_to_net_basis "
            "COMMISSION_RATE with a rate (L2-5-Q-32)"
        )
    rate = to_fraction(basis["rate"])
    if not 0 <= rate <= 1:
        raise ValueError(f"agent obligation {ob.subject_key}: the retained rate lies in [0, 1]")
    return (("REVENUE", rate), (_AP_SUPPLIER, 1 - rate))


def _relief(ctx: BookContext, st: FxState, inputs: PartInputs) -> list[PartTarget]:
    obligations = {ob.subject_key: ob for ob in st.allocated.obligations}
    counterparties = {pair.obligation: pair.performing_entity for pair in st.ic_pairs}
    released = frozenset(inputs.released_at_close)
    functional = {
        (fx.entity, fx.subject_key, fx.period_key): fx
        for fx in st.functional_targets
        if fx.measure == "revenue_cum"
    }
    causes: dict[tuple[str, str], list[Target]] = {}
    for item in inputs.relief_by_cause:
        _require(item, RELIEF_BY_CAUSE_MEASURE, ctx)
        if item.cause is None:
            raise ValueError(f"relief by cause of {item.subject_key} names no cause (§9.2.10)")
        causes.setdefault((item.entity, item.subject_key), []).append(item)
    supplier = {
        (item.entity, item.subject_key, item.period_key): item.value
        for item in inputs.agent_supplier
    }
    out: list[PartTarget] = []
    for target in inputs.relief:
        _require(target, RELIEF_MEASURE, ctx)
        ob = obligations.get(target.subject_key)
        if ob is None:
            raise ValueError(f"relief names the obligation {target.subject_key!r}, absent (CV-45)")
        if target.entity != ob.contracting_entity:
            raise _invariant(
                "revenue relief belongs to the contracting entity",
                target.subject_key,
                entity=target.entity,
            )
        fx = functional.get((target.entity, target.subject_key, target.period_key))
        amount_functional, rates, fx_nodes = _functional(ctx, target, target.value, fx)
        cited = tuple(
            item.node_id
            for item in inputs.concessions
            if (item.entity, item.subject_key, item.period_key)
            == (target.entity, target.subject_key, target.period_key)
        )
        position = _positions(ctx, target.entity)
        by_cause: dict[str, int] = {}
        for item in causes.get((target.entity, target.subject_key), ()):
            if position[item.period_key] <= position[target.period_key]:
                cause = item.cause or ""
                by_cause[cause] = by_cause.get(cause, 0) + item.value
        part = _relief_part(ob, target.subject_key in counterparties)
        time_txn = by_cause.get("NORMAL", 0) if target.subject_key in released else 0
        out.append(
            PartTarget(
                book_code=ctx.book_code,
                entity=target.entity,
                subject_key=target.subject_key,
                part=part,
                component=None,
                period_key=target.period_key,
                txn_currency=ctx.txn_currency,
                amount_txn=target.value,
                functional_currency=ctx.entities[target.entity].functional_currency,
                amount_functional=amount_functional,
                counterparty_entity=counterparties.get(target.subject_key),
                by_cause=tuple(sorted((c, v) for c, v in by_cause.items() if v != 0)),
                rates=rates,
                node_ids=(target.node_id, *cited, *fx_nodes),
                time_txn=time_txn,
                time_functional=_time_share(time_txn, target.value, amount_functional),
                # D-88 L7-5-Q-4 (1): relief = revenue_cum + the concessions created, citing both.
                value_inputs=((target.node_id, 1), *((node_id, 1) for node_id in cited)),
                weights=(
                    _agent_weights(
                        ob,
                        target.value,
                        supplier.get((target.entity, target.subject_key, target.period_key), 0),
                    )
                    if part == "JET-02 agent"
                    else ()
                ),
            )
        )
    return out


def _positions(ctx: BookContext, entity: str) -> Mapping[str, int]:
    return MappingProxyType(
        {period.period_key: index for index, period in enumerate(ctx.entities[entity].periods)}
    )


def _performing(
    ctx: BookContext, pairs: Sequence[IcPair], released: frozenset[str]
) -> list[PartTarget]:
    """``JET-13 performing``: cumulative pairs per performing period through its horizon."""
    groups: dict[tuple[str, str, str], list[IcPair]] = {}
    for pair in pairs:
        key = (pair.performing_entity, pair.obligation, pair.contracting_entity)
        groups.setdefault(key, []).append(pair)
    out: list[PartTarget] = []
    for (entity, obligation, contracting), items in sorted(groups.items()):
        calendar = ctx.entities[entity]
        position = _positions(ctx, entity)
        first = min(position[pair.performing_period_key] for pair in items)
        last = position[ctx.horizon[entity]]
        mu = ctx.currencies[items[0].txn_currency].minor_unit
        by_node: dict[str, list[IcPair]] = {}
        for pair in items:
            by_node.setdefault(pair.txn_node_id, []).append(pair)
        amount_txn = amount_functional = 0
        rates: set[RateRef] = set()
        nodes: list[str] = []
        for period in calendar.periods[first : last + 1]:
            through = position[period.period_key]
            for pair in items:
                if pair.performing_period_key == period.period_key:
                    amount_txn += pair.amount_txn
                    amount_functional += pair.amount_performing
                    rates.update(pair.performing_rates)
                    nodes += [pair.txn_node_id, pair.performing_node_id]
            values: list[NodeInput] = []
            for node_id, group in sorted(by_node.items()):
                included = [p for p in group if position[p.performing_period_key] <= through]
                if len(included) == len(group):
                    values.append((node_id, 1))
                elif included:  # a contracting-period node spans later performing periods
                    detail = {"value": format_money(sum(p.amount_txn for p in included), mu)}
                    ref_id = f"{node_id}#through={period.period_key}"
                    values.append((SourceRef("source_record", ref_id, detail), 1))
            cited = [(node, 0) for node in dict.fromkeys(nodes) if node not in by_node]
            out.append(
                PartTarget(
                    book_code=ctx.book_code,
                    entity=entity,
                    subject_key=obligation,
                    part="JET-13 performing",
                    component=None,
                    period_key=period.period_key,
                    txn_currency=items[0].txn_currency,
                    amount_txn=amount_txn,
                    functional_currency=items[0].performing_currency,
                    amount_functional=amount_functional,
                    counterparty_entity=contracting,
                    by_cause=(),
                    rates=tuple(sorted(rates, key=lambda ref: (ref.rate_key, ref.version_key))),
                    node_ids=tuple(nodes),
                    time_txn=amount_txn if obligation in released else 0,
                    time_functional=amount_functional if obligation in released else 0,
                    value_inputs=(*values, *cited),
                )
            )
    return out


def _refund_liabilities(
    ctx: BookContext, inputs: PartInputs, st: FxState | None = None
) -> list[PartTarget]:
    """``JET-04b`` per component less the JET-05c concessions; ``JET-05c`` per obligation.

    Stage 10 names each ``concession_created_cum`` target's component key as ``cause``; a
    ``CONCESSION`` JET-04b part nets the created amounts indexed by (entity, cause, period) where
    its subject is that cause (D-88 L7-5-Q-4 (2)). JET-05c parts stay per obligation.

    A foreign-currency JET-04b part takes the stage 12 functional amount of its component when no
    concession is netted out of it (S12-R-19, S12-R-20, S14-R-01; L6-5); a netted foreign part
    therefore still fails closed.
    """
    functional = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure == REFUND_LIABILITY_MEASURE
        }
    )
    created: dict[tuple[str, str, str], Target] = {}
    out: list[PartTarget] = []
    for target in inputs.concessions:
        _require(target, CONCESSION_MEASURE, ctx)
        if target.cause is None:
            raise ValueError(
                f"a concession of {target.subject_key} names no component as cause (§10.2.4)"
            )
        created[(target.entity, target.cause, target.period_key)] = target
        values: tuple[NodeInput, ...] = ((target.node_id, 1),)
        out.append(_plain(ctx, target, "JET-05c", None, target.value, values))
    for target in inputs.refund_liabilities:
        _require(target, REFUND_LIABILITY_MEASURE, ctx)
        if target.cause not in COMPONENT_KINDS:
            raise ValueError(f"unknown refund-liability component {target.cause!r} (§10.2.4)")
        amount = target.value
        values = ((target.node_id, 1),)
        concession = created.get((target.entity, target.subject_key, target.period_key))
        if target.cause == "CONCESSION" and concession is not None:
            amount -= concession.value  # created by JET-05c; JET-04b carries the consumption
            values += ((concession.node_id, -1),)
        fx = None
        if amount == target.value:
            fx = functional.get((target.entity, target.subject_key, target.period_key))
        out.append(_plain(ctx, target, "JET-04b", target.cause, amount, values, fx=fx))
    return out


def _financing(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-11a`` and ``JET-11b``: the cumulative accretion per contract and entity (S10-R-10).

    Compute posts the accretion as ``EVENT`` deltas, as it posts relief (L3-2-Q-15; L4-3-Q-30).
    """
    out: list[PartTarget] = []
    for target in inputs.financing:
        _require(target, FINANCING_MEASURE, ctx)
        part = _FINANCING_PARTS.get(target.cause or "")
        if part is None:
            raise ValueError(
                f"a financing target names no JET-11 part: {target.cause!r} (S10-R-10)"
            )
        out.append(_plain(ctx, target, part, None, target.value, ((target.node_id, 1),)))
    return out


def _deposits(ctx: BookContext, inputs: PartInputs, st: FxState | None = None) -> list[PartTarget]:
    """``JET-01b`` receipt, criteria met and refund per ``<contract>@<entity>``, and the 25-7
    revenue per obligation (S02-R-08; Table 14-A; S14-R-25; L4-1-Q-15; D-91 gaps (iv)).

    The receipt, transfer and refund parts take the stage 02 cumulative measures. The 25-7 revenue
    part posts per ``IN_SCOPE_606`` obligation: the stage 09 ``deposit_revenue_share`` target of
    the obligation and period is the amount, its ``deposit_revenue_time_share`` the ``TIME``
    share of the ``CLOSE_RELEASE`` pass, and the part cites the share node. The shares must sum
    to the contract's ``deposit_to_revenue_cum``; a non-zero recognition without its attribution
    fails closed (S14-R-25).

    A foreign-currency part takes the stage 12 functional amount of its measure: the deposit layers
    created at spot, or the portions consumed at spot (S12-R-19, S12-R-20, S14-R-01; L6-5); the
    functional 25-7 release is split over the obligations by the attribution weights (S14-R-10;
    D-91 (iv): [75,333, 37,667] of 113,000 for weights 2 : 1).
    """
    functional = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.measure, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure in _DEPOSIT_PARTS
        }
    )
    functional_time = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure == DEPOSIT_REVENUE_TIME_MEASURE
        }
    )
    shares = {
        (item.entity, item.subject_key, item.period_key): item
        for item in inputs.deposit_revenue
        if item.measure == DEPOSIT_SHARE_MEASURE
    }
    times = {
        (item.entity, item.subject_key, item.period_key): item
        for item in inputs.deposit_revenue
        if item.measure == DEPOSIT_TIME_SHARE_MEASURE
    }
    out: list[PartTarget] = []
    for target in inputs.deposits:
        part = _DEPOSIT_PARTS.get(target.measure)
        if part is None:
            continue
        _require(target, target.measure, ctx)
        fx = functional.get((target.entity, target.subject_key, target.measure, target.period_key))
        if target.measure == DEPOSIT_REVENUE_MEASURE:
            if st is None:
                raise _invariant(
                    "the 25-7 revenue part needs the allocated state",
                    target.subject_key,
                    period_key=target.period_key,
                )
            fx_time = functional_time.get((target.entity, target.subject_key, target.period_key))
            out.extend(_deposit_revenue(ctx, st, target, shares, times, fx, fx_time))
            continue
        out.append(_plain(ctx, target, part, None, target.value, ((target.node_id, 1),), fx=fx))
    return out


def _deposit_revenue(
    ctx: BookContext,
    st: FxState,
    target: Target,
    shares: Mapping[tuple[str, str, str], Target],
    times: Mapping[tuple[str, str, str], Target],
    fx: FxTarget | None,
    fx_time: FxTarget | None = None,
) -> list[PartTarget]:
    """The ``JET-01b 25-7 revenue`` parts of one contract target (S14-R-25; D-91 gaps (iv)).

    A foreign release takes the stage 12 functional amount of the contract's recognition, split
    over the obligations by the attribution weights (S14-R-10); its ``TIME`` share (the dated
    releases) takes the stage 12 amount of ``deposit_to_revenue_time_cum``, the dated releases at
    their own conversion (S12-R-20; D1-R04), split over the same weights, so a dated release at one
    spot and an event release at another keep their functional amounts (660 / 720, not 690 / 690).
    """
    members = sorted(
        (
            ob
            for ob in st.allocated.obligations
            if str(ob.scope_flag) == "IN_SCOPE_606"
            and contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
            == target.subject_key
        ),
        key=lambda ob: ob.subject_key,
    )
    found = [(ob, shares.get((target.entity, ob.subject_key, target.period_key))) for ob in members]
    if any(share is None for _, share in found):
        if target.value == 0:
            return []  # nothing recognised and nothing attributed: no part
        raise _invariant(
            "the 606-10-25-7 revenue of the contract has no stage 09 attribution",
            target.subject_key,
            period_key=target.period_key,
            rule_ref="S14-R-25",
        )
    attributed = [(ob, share) for ob, share in found if share is not None]
    if sum(share.value for _, share in attributed) != target.value:
        raise _invariant(
            "the 25-7 revenue shares do not sum to the contract's recognition",
            target.subject_key,
            period_key=target.period_key,
            rule_ref="S14-R-25",
        )
    functional_shares: Mapping[str, int]
    rates: tuple[RateRef, ...] = ()
    fx_nodes: tuple[str, ...] = ()
    if fx is not None:
        if fx.amount_txn != target.value:
            raise _invariant(
                "stage 12 converts another transaction amount than the 25-7 recognition",
                target.subject_key,
                period_key=target.period_key,
                stage_12_amount=str(fx.amount_txn),
            )
        keys = [ob.subject_key for ob, _ in attributed]
        weights, _basis = deposit_share_weights(
            members[0].contract_key, [ob for ob, _ in attributed]
        )
        split = (
            [0] * len(keys)
            if fx.amount_functional == 0
            else largest_remainder(fx.amount_functional, list(weights), keys)
        )
        functional_shares = dict(zip(keys, split, strict=True))
        rates, fx_nodes = fx.rates, (fx.node_id,)
        time_txn_total = sum(_time_txn(times, target, ob.subject_key) for ob, _ in attributed)
        if fx_time is None:
            if time_txn_total != 0:
                raise _invariant(
                    "stage 12 publishes no functional amount for the dated 25-7 releases",
                    target.subject_key,
                    period_key=target.period_key,
                    time_txn=str(time_txn_total),
                )
            time_split = [0] * len(keys)
        else:
            if fx_time.amount_txn != time_txn_total:
                raise _invariant(
                    "stage 12 converts another transaction amount than the dated 25-7 releases",
                    target.subject_key,
                    period_key=target.period_key,
                    stage_12_amount=str(fx_time.amount_txn),
                )
            time_split = (
                [0] * len(keys)
                if fx_time.amount_functional == 0
                else largest_remainder(fx_time.amount_functional, list(weights), keys)
            )
            rates = tuple(
                sorted(set(rates) | set(fx_time.rates), key=lambda r: (r.rate_key, r.version_key))
            )
            fx_nodes = (*fx_nodes, fx_time.node_id)
        time_functional_shares = dict(zip(keys, time_split, strict=True))
    else:
        for _ob, share in attributed:
            _functional(ctx, share, share.value, None)  # a foreign part without stage 12 fails
        functional_shares = {ob.subject_key: share.value for ob, share in attributed}
        time_functional_shares = {
            ob.subject_key: _time_txn(times, target, ob.subject_key) for ob, _ in attributed
        }
    out: list[PartTarget] = []
    for ob, share in attributed:
        time = times.get((target.entity, ob.subject_key, target.period_key))
        time_txn = 0 if time is None else time.value
        amount_functional = functional_shares[ob.subject_key]
        time_functional = time_functional_shares[ob.subject_key]
        if not 0 <= time_functional <= amount_functional:
            raise _invariant(
                "the functional TIME share of a 25-7 release exceeds its functional amount",
                ob.subject_key,
                period_key=target.period_key,
                time_functional=str(time_functional),
                amount_functional=str(amount_functional),
            )
        out.append(
            PartTarget(
                book_code=ctx.book_code,
                entity=target.entity,
                subject_key=ob.subject_key,
                part=DEPOSIT_REVENUE_PART,
                component=None,
                period_key=target.period_key,
                txn_currency=ctx.txn_currency,
                amount_txn=share.value,
                functional_currency=ctx.entities[target.entity].functional_currency,
                amount_functional=amount_functional,
                counterparty_entity=None,
                by_cause=(),
                rates=rates,
                node_ids=(
                    share.node_id,
                    *(() if time is None else (time.node_id,)),
                    *fx_nodes,
                ),
                time_txn=time_txn,
                time_functional=time_functional,
                value_inputs=((share.node_id, 1),),
            )
        )
    return out


def _time_txn(times: Mapping[tuple[str, str, str], Target], target: Target, key: str) -> int:
    """The ``deposit_revenue_time_share`` of ``key`` in the target's entity and period, else 0."""
    time = times.get((target.entity, key, target.period_key))
    return 0 if time is None else time.value


def _customer_consideration(
    ctx: BookContext, inputs: PartInputs, st: FxState | None = None
) -> list[PartTarget]:
    """``JET-14`` promised, release and share-based per ``<contract>@<entity>`` (S04-R-14 to
    S04-R-17; ENGINE_SPEC_B S10-R-26, S14-R-11; Table 14-A; POLICIES JET-14, CHK-133, PT-10
    CHK-120; D-91 C606-03).

    - promised (Dr ``CUSTOMER_INCENTIVE_ASSET`` / Cr ``CONSIDERATION_PAYABLE``): the cumulative
      ``consideration_payable`` Σ R of the non-share-based promises (the stage 04 payable node);
    - release (Dr ``REVENUE`` / Cr ``CUSTOMER_INCENTIVE_ASSET``): P = the posted stage 04
      ``incentive_release_ordinary_cum`` on its own, citing the ordinary node only;
    - share-based (Dr ``REVENUE`` / Cr ``BILLING_CLEARING`` ``EQUITY``): E = the posted stage 10
      ``share_based_reduction_cum``, the sum of the individually rounded element targets.

    P + E = T, the composed ``incentive_release_cum`` stage 10 publishes and the engine root nets
    from ``contract_version.revenue_cum``, with no residue (S14-R-11); ``customer_incentive_asset``
    = posted payable − P (S04-R-16). A set whose parts do not sum to T fails closed.

    The three targets do not separate a promise released in full after related revenue
    (S04-R-15), so it posts through promised and release, whose incentive-asset lines net to the
    after-revenue lines at role grain (L5-5-Q-7).

    A foreign-currency promised part takes the stage 12 functional amount of the payable layers
    created at spot (S12-R-19, S14-R-01; L6-5), and a foreign-currency release part the stage 12
    release at historical carrying, with no JET-10 line (POL-164; D-88 L7-6-Q-6). A foreign-currency
    share-based part still fails closed.
    """
    payables = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure == CPC_PAYABLE_MEASURE
        }
    )
    releases = (
        {}
        if st is None
        else {
            (fx.entity, fx.subject_key, fx.period_key): fx
            for fx in st.functional_targets
            if fx.measure == CPC_ORDINARY_MEASURE
        }
    )
    found: dict[tuple[str, str, str], dict[str, Target]] = {}
    for target in inputs.customer_consideration:
        if target.measure not in _CPC_MEASURES:
            continue
        _require(target, target.measure, ctx)
        key = (target.entity, target.subject_key, target.period_key)
        found.setdefault(key, {})[target.measure] = target
    out: list[PartTarget] = []
    for (entity, subject_key, period_key), items in sorted(found.items()):
        payable = items.get(CPC_PAYABLE_MEASURE)
        ordinary = items.get(CPC_ORDINARY_MEASURE)
        release = items.get(CPC_RELEASE_MEASURE)
        if payable is None or ordinary is None or release is None:
            raise ValueError(
                f"the consideration payable of {subject_key} at {period_key} lacks its payable, "
                "ordinary or release target (CV-45)"
            )
        share = items.get(CPC_SHARE_BASED_MEASURE)
        if ordinary.value + (0 if share is None else share.value) != release.value:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the JET-14 release and share-based parts do not sum to the composed release "
                "(S14-R-11)",
                subject_key=subject_key,
                detail={
                    "period_key": period_key,
                    "rule": "S14-R-11",
                    "ordinary": str(ordinary.value),
                    "share_based": "0" if share is None else str(share.value),
                    "release": str(release.value),
                },
            )
        out.append(
            _plain(
                ctx,
                payable,
                "JET-14 promised",
                None,
                payable.value,
                ((payable.node_id, 1),),
                fx=payables.get((entity, subject_key, period_key)),
            )
        )
        if share is not None:
            out.append(
                _plain(ctx, share, "JET-14 share-based", None, share.value, ((share.node_id, 1),))
            )
        out.append(
            _plain(
                ctx,
                ordinary,
                "JET-14 release",
                None,
                ordinary.value,
                ((ordinary.node_id, 1),),
                fx=releases.get((entity, subject_key, period_key)),
            )
        )
    return out


def _warranties(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-16 accrual`` per product obligation in its performing entity: the stage 04 cumulative
    ``warranty_accrual_cum`` (S04-R-19; Table 14-A; POLICIES JET-16, CHK-134). The claim release
    has no producer target yet (Table 14-A: ``COST_INCURRED`` with ``purpose = WARRANTY_CLAIM``)."""
    out: list[PartTarget] = []
    for target in inputs.warranties:
        _require(target, WARRANTY_MEASURE, ctx)
        out.append(
            _plain(ctx, target, "JET-16 accrual", None, target.value, ((target.node_id, 1),))
        )
    return out


def _noncash(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-17 unconditional`` and ``receipt`` per ``<contract>@<entity>`` (S04-R-18; Table 14-A;
    POLICIES JET-17, CHK-135): the stage 04 cumulative asset recognised, and the cumulative
    carrying amount of the noncash receipts (04 §16.3 ``PAYMENT_RECEIVED`` ``form = NONCASH``)."""
    out: list[PartTarget] = []
    for target in inputs.noncash:
        part = _NONCASH_PARTS.get(target.measure)
        if part is None:
            continue
        _require(target, target.measure, ctx)
        out.append(_plain(ctx, target, part, None, target.value, ((target.node_id, 1),)))
    return out


def _return_assets(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-07c`` and ``JET-07d`` per returnable obligation (S10-R-16; CHK-029, CHK-060).

    JET-07d carries the cumulative derecognition into inventory; JET-07c carries the rest against
    cost of revenue, so its cumulative target is the balance plus the derecognised amount.
    """
    found: dict[tuple[str, str, str], dict[str, Target]] = {}
    for target in inputs.return_assets:
        if target.measure not in (RETURN_ASSET_MEASURE, RETURN_DERECOGNISED_MEASURE):
            raise ValueError(f"a return-asset input of measure {target.measure!r} (CV-45)")
        _require(target, target.measure, ctx)
        key = (target.entity, target.subject_key, target.period_key)
        found.setdefault(key, {})[target.measure] = target
    out: list[PartTarget] = []
    for _key, items in sorted(found.items()):
        balance = items.get(RETURN_ASSET_MEASURE)
        derecognised = items.get(RETURN_DERECOGNISED_MEASURE)
        if balance is None or derecognised is None:
            raise ValueError(f"a return asset of {_key[1]} lacks its balance or derecognition")
        values: tuple[NodeInput, ...] = ((balance.node_id, 1), (derecognised.node_id, 1))
        amount = balance.value + derecognised.value
        out.append(_plain(ctx, balance, "JET-07c", None, amount, values))
        cited: tuple[NodeInput, ...] = ((derecognised.node_id, 1),)
        out.append(_plain(ctx, derecognised, "JET-07d", None, derecognised.value, cited))
    return out


def _plain(
    ctx: BookContext,
    target: Target,
    part: str,
    component: str | None,
    amount: int,
    values: tuple[NodeInput, ...],
    *,
    time: bool = False,
    weights: tuple[tuple[str, Fraction], ...] = (),
    split_inputs: tuple[tuple[str, tuple[NodeInput, ...]], ...] = (),
    fx: FxTarget | None = None,
) -> PartTarget:
    amount_functional, rates, fx_nodes = _functional(ctx, target, amount, fx)
    nodes = tuple(dict.fromkeys(ref for ref, _ in values if isinstance(ref, str)))
    return PartTarget(
        book_code=ctx.book_code,
        entity=target.entity,
        subject_key=target.subject_key,
        part=part,
        component=component,
        period_key=target.period_key,
        txn_currency=ctx.txn_currency,
        amount_txn=amount,
        functional_currency=ctx.entities[target.entity].functional_currency,
        amount_functional=amount_functional,
        counterparty_entity=None,
        by_cause=(),
        rates=rates,
        node_ids=(*nodes, *fx_nodes),
        time_txn=amount if time else 0,
        time_functional=amount_functional if time else 0,
        value_inputs=values,
        split_inputs=split_inputs,
        weights=weights,
    )


def _remeasurement(ctx: BookContext, st: FxState) -> list[PartTarget]:
    """``JET-10a`` to ``JET-10d``: cumulative differences per group@entity and balance role.

    The ``TIME`` share is the sum of the period-end remeasurements of the role (movement reason
    ``PERIOD_END``); settlement differences are ``EVENT`` (Table 14-A; L2-5-Q-29).
    """
    out: list[PartTarget] = []
    for fx in st.remeasurement_targets:
        if fx.part not in _REMEASUREMENT_PARTS or fx.balance_role is None:
            raise ValueError(f"a remeasurement target names the part {fx.part!r} (L2-5-Q-15)")
        time = 0
        if fx.part in _PERIOD_END_PARTS:
            end = ctx.entities[fx.entity].periods[_positions(ctx, fx.entity)[fx.period_key]]
            time = sum(
                movement.amount_functional
                for movement in st.layer_movements
                if movement.entity == fx.entity
                and movement.balance_role == fx.balance_role
                and movement.movement_kind in _REMEASURED
                and movement.reason == "PERIOD_END"
                and movement.effective_date <= end.end_date
            )
        out.append(
            PartTarget(
                book_code=fx.book_code,
                entity=fx.entity,
                subject_key=fx.subject_key.split("#", 1)[0],
                part=fx.part,
                component=fx.balance_role,
                period_key=fx.period_key,
                txn_currency=fx.txn_currency,
                amount_txn=fx.amount_txn,
                functional_currency=fx.functional_currency,
                amount_functional=fx.amount_functional,
                counterparty_entity=None,
                by_cause=(),
                rates=fx.rates,
                node_ids=(fx.node_id,),
                time_txn=0,
                time_functional=time,
                value_inputs=((fx.node_id, 1),),
            )
        )
    return out


def _reclass(ctx: BookContext, st: FxState, inputs: PartInputs) -> list[PartTarget]:
    """``JET-06 reclass``: the running sum of the period attributions per obligation and role."""
    obligations = {ob.subject_key: ob for ob in st.allocated.obligations}
    groups: dict[tuple[str, str, str], dict[str, Target]] = {}
    for target in inputs.reclass:
        _require(target, RECLASS_MEASURE, ctx)
        ob = obligations.get(target.subject_key)
        if ob is None or target.cause not in RECLASS_ROLES:
            raise ValueError(
                f"a reclass attribution of {target.subject_key!r} names no obligation of the group "
                f"or the role {target.cause!r} (§10.2.7)"
            )
        if target.entity != ob.contracting_entity:
            raise _invariant(
                "netting reclass belongs to the contracting entity",
                target.subject_key,
                entity=target.entity,
            )
        periods = groups.setdefault((target.entity, target.subject_key, target.cause), {})
        if target.period_key in periods:
            raise ValueError(f"two reclass attributions of {target.subject_key} in one period")
        periods[target.period_key] = target
    # S12-R-09: the cumulative functional amounts stage 12 publishes per obligation and role.
    functional = {
        (fx.entity, fx.subject_key, fx.period_key): fx
        for fx in st.functional_targets
        if fx.measure == RECLASS_MEASURE
    }
    out: list[PartTarget] = []
    for (entity, subject, role), periods in sorted(groups.items()):
        calendar = ctx.entities[entity]
        position = _positions(ctx, entity)
        first = min(position[key] for key in periods)
        last = position[ctx.horizon[entity]]
        running = 0
        values: list[NodeInput] = []
        weights = tuple((label, Fraction(1 if label == role else 0)) for label in RECLASS_ROLES)
        base = periods[min(periods, key=lambda key: position[key])]
        for period in calendar.periods[first : last + 1]:
            attribution = periods.get(period.period_key)
            if attribution is not None:
                running += attribution.value
                values.append((attribution.node_id, 1))
            carried = dataclasses.replace(base, period_key=period.period_key, value=running)
            part = _plain(
                ctx,
                carried,
                "JET-06 reclass",
                role,
                running,
                tuple(values),
                time=True,
                weights=weights,
                fx=functional.get((entity, f"{subject}#{role}", period.period_key)),
            )
            out.append(part)
    return out


def _invoices(ctx: BookContext, st: FxState, inputs: PartInputs) -> list[PartTarget]:
    """``JET-03 invoice``: Dr AR for billing and tax; Cr CL for billing, Cr tax for the tax."""
    if not inputs.invoices and not inputs.invoice_tax:
        return []
    obligations = {ob.subject_key: ob for ob in st.allocated.obligations}
    taxes: dict[tuple[str, str, str], Target] = {}
    for billed in inputs.invoice_tax:
        _require(billed, INVOICE_TAX_MEASURE, ctx)
        taxes[(billed.entity, billed.subject_key, billed.period_key)] = billed
    # S14-R-01: the stage 12 functional amount of billing plus tax per obligation (L6-5).
    functional = {
        (fx.entity, fx.subject_key, fx.period_key): fx
        for fx in st.functional_targets
        if fx.measure == INVOICE_MEASURE
    }
    out: list[PartTarget] = []
    for target in inputs.invoices:
        _require(target, INVOICE_MEASURE, ctx)
        ob = obligations.get(target.subject_key)
        if ob is None:
            raise ValueError(f"billing names the obligation {target.subject_key!r}, absent")
        mode = ctx.policies.value(
            "billing.posting",
            contract=ob.contract_key,
            entity=target.entity,
            period=target.period_key,
        )
        if mode != "ENGINE":
            raise ValueError(f"JET-03 billing inputs under billing.posting {mode!r} (POL-004)")
        tax_key = (target.entity, target.subject_key, target.period_key)
        tax = taxes.pop(tax_key) if tax_key in taxes else None
        tax_value = 0 if tax is None else tax.value
        if target.value * tax_value < 0:
            raise ValueError(f"billing and tax of {target.subject_key} differ in sign (JET-03)")
        net_inputs: tuple[NodeInput, ...] = ((target.node_id, 1),)
        tax_inputs: tuple[NodeInput, ...] = () if tax is None else ((tax.node_id, 1),)
        weights = (
            ("CONTRACT_LIABILITY", Fraction(abs(target.value) if target.value or tax_value else 1)),
            ("SALES_TAX_PAYABLE", Fraction(abs(tax_value))),
        )
        out.append(
            _plain(
                ctx,
                target,
                "JET-03 invoice",
                None,
                target.value + tax_value,
                (*net_inputs, *tax_inputs),
                weights=weights,
                split_inputs=(
                    ("CONTRACT_LIABILITY", net_inputs),
                    ("SALES_TAX_PAYABLE", tax_inputs),
                ),
                fx=functional.get((target.entity, target.subject_key, target.period_key)),
            )
        )
    if taxes:
        raise ValueError("sales tax billed without billing of its obligation and period (JET-03)")
    return out


def _pre_standard(ctx: BookContext, inputs: PartInputs) -> list[PartTarget]:
    """``JET-15``: cumulative pre-standard revenue per obligation in its contracting entity, posted
    only by the ``LEGACY`` book (POLICIES R6; ENGINE_SPEC_B S13-R-08)."""
    if not inputs.pre_standard:
        return []
    if str(ctx.book_code) != _LEGACY_BOOK:
        raise ValueError(f"JET-15 inputs in book {ctx.book_code} (POLICIES R6; S13-R-08)")
    out: list[PartTarget] = []
    for target in inputs.pre_standard:
        _require(target, PRE_STANDARD_MEASURE, ctx)
        out.append(_plain(ctx, target, "JET-15", None, target.value, ((target.node_id, 1),)))
    return out


def role_lines(
    part: JetPart,
    amount_txn: int,
    amount_functional: int,
    *,
    counterparty_entity: str | None = None,
    subject_role: str | None = None,
    weights: Mapping[str, Fraction] | None = None,
) -> tuple[RoleLine, ...]:
    """The signed role amounts of one part amount: debit roles +, credit roles − (S14-R-01; R4).

    ``subject_role`` selects the role of a ``BY_SUBJECT`` side; ``weights`` apportion a split side
    by role label with ``largest_remainder``, the functional amount weighted by the transaction
    split (S14-R-10). ``counterparty_entity`` tags the intercompany roles (R3).
    """
    if part.debit is None or part.credit is None:
        raise ValueError(f"part {part.part} posts no lines of its own (S14-R-02, S14-R-03)")
    lines = [
        *_side(part.debit, 1, amount_txn, amount_functional, subject_role, weights),
        *_side(part.credit, -1, amount_txn, amount_functional, subject_role, weights),
    ]
    out: list[RoleLine] = []
    for role, clearing_purpose, txn, functional in lines:
        counterparty = None
        if role in INTERCOMPANY_ROLES:
            if counterparty_entity is None:
                raise ValueError(f"{part.part}: an intercompany role needs its counterparty (R3)")
            counterparty = counterparty_entity
        out.append(RoleLine(role, clearing_purpose, counterparty, txn, functional))
    return tuple(out)


def _side(
    side: Side,
    sign: int,
    amount_txn: int,
    amount_functional: int,
    subject_role: str | None,
    weights: Mapping[str, Fraction] | None,
) -> list[tuple[str, str | None, int, int]]:
    if side.selection == ONE or side.selection == BY_SUBJECT:
        if side.selection == ONE:
            role = side.roles[0]
        else:
            chosen = [role for role in side.roles if role.account_role == subject_role]
            if len(chosen) != 1:
                raise ValueError(f"the subject role {subject_role!r} is not one of {side.labels}")
            role = chosen[0]
        return [
            (role.account_role, role.clearing_purpose, sign * amount_txn, sign * amount_functional)
        ]
    if weights is None or set(weights) != set(side.labels):
        raise ValueError(f"a split side needs one weight per role {side.labels} (S14-R-01)")
    keys = list(side.labels)
    shares = _apportion(amount_txn, [Fraction(weights[key]) for key in keys], keys)
    basis = [Fraction(abs(share)) for share in shares]
    if sum(basis) == 0:
        basis = [Fraction(weights[key]) for key in keys]
    functional = _apportion(amount_functional, basis, keys)
    return [
        (role.account_role, role.clearing_purpose, sign * share, sign * fn)
        for role, share, fn in zip(side.roles, shares, functional, strict=True)
    ]


def _apportion(total: int, weights: Sequence[Fraction], keys: Sequence[str]) -> list[int]:
    if total == 0:
        return [0] * len(keys)
    return largest_remainder(total, weights, keys)


# --- Role targets (§14.2.2) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Share:
    """One part's contribution to a role key at a period end."""

    part_key: tuple[str, str, str, str, str]  # the part target key without its period
    txn: int
    functional: int
    time_txn: int
    time_functional: int
    inputs: tuple[NodeInput, ...]  # signed for the role
    split: Mapping[str, str] | None  # post.role_target.v1 split params, None for a plain share
    passes: frozenset[str]
    rates: tuple[RateRef, ...]
    currencies: tuple[str, str]
    reason: str | None = None  # the part's Table 14-A reason_code (S14-R-27)


def _passes(part: str) -> frozenset[str]:
    return frozenset(
        cls.posting_pass
        for cls in AMOUNT_CLASSES.get(part, {}).values()
        if cls.amount_class == TIME and cls.posting_pass is not None
    )


def _signed(inputs: Iterable[NodeInput], sign: int) -> tuple[NodeInput, ...]:
    return tuple((ref, sign * s) for ref, s in inputs)


def _shares(part: PartTarget) -> list[tuple[RoleKey, _Share]]:
    spec = JET_PARTS[part.part]
    weights = dict(part.weights) or None
    lines = role_lines(
        spec,
        part.amount_txn,
        part.amount_functional,
        counterparty_entity=part.counterparty_entity,
        subject_role=part.component,
        weights=weights,
    )
    times = role_lines(
        spec,
        part.time_txn,
        part.time_functional,
        counterparty_entity=part.counterparty_entity,
        subject_role=part.component,
        weights=weights,
    )
    debit = spec.debit
    credit = spec.credit
    assert debit is not None and credit is not None and spec.entry_kind is not None
    nonzero = [label for label, weight in part.weights if weight != 0]
    split_inputs = dict(part.split_inputs)
    out: list[tuple[RoleKey, _Share]] = []
    for index, (line, time) in enumerate(zip(lines, times, strict=True)):
        on_debit = index < (1 if debit.selection != "SPLIT" else len(debit.roles))
        side = debit if on_debit else credit
        sign = 1 if on_debit else -1
        split: Mapping[str, str] | None = None
        if side.selection != "SPLIT":
            inputs = _signed(part.value_inputs, sign)
        elif line.label in split_inputs:
            inputs = _signed(split_inputs[line.label], sign)
        elif len(nonzero) == 1:
            if line.label != nonzero[0]:
                continue  # the share of a zero weight is 0
            inputs = _signed(part.value_inputs, sign)
        else:
            labels = list(side.labels)
            inputs = tuple(part.value_inputs)
            split = {
                "index": str(labels.index(line.label)),
                "keys": "|".join(labels),
                "side": str(sign),
                "weights": "|".join(rational_param(dict(part.weights)[key]) for key in labels),
            }
        if not inputs and not (line.signed_txn or line.signed_functional):
            continue  # an empty component of a split side (JET-03 without tax)
        key = RoleKey(
            str(part.book_code),
            part.entity,
            part.subject_key,
            spec.entry_kind,
            line.account_role,
            line.clearing_purpose,
            line.counterparty_entity,
        )
        share = _Share(
            part_key=part.key[:5],
            txn=line.signed_txn,
            functional=line.signed_functional,
            time_txn=time.signed_txn,
            time_functional=time.signed_functional,
            inputs=inputs,
            split=split,
            passes=_passes(part.part),
            rates=part.rates,
            currencies=(part.txn_currency, part.functional_currency),
            reason=spec.reason_code,
        )
        out.append((key, share))
    return out


def role_targets(
    ctx: BookContext, parts: Sequence[PartTarget], tb: TraceBuilder
) -> tuple[RoleTarget, ...]:
    """Cumulative role targets per role key and period end through the horizon (S14-R-04)."""
    shares: dict[RoleKey, dict[tuple[str, ...], list[tuple[int, _Share]]]] = {}
    for part in parts:
        position = _positions(ctx, part.entity)[part.period_key]
        for key, share in _shares(part):
            by_part = shares.setdefault(key, {})
            by_part.setdefault(share.part_key, []).append((position, share))
    out: list[RoleTarget] = []
    for key in sorted(shares, key=RoleKey.sort_key):
        by_part = shares[key]
        calendar = ctx.entities[key.entity]
        first = min(position for items in by_part.values() for position, _ in items)
        last = _positions(ctx, key.entity)[ctx.horizon[key.entity]]
        for index in range(first, last + 1):
            current = [
                max((item for item in items if item[0] <= index), key=lambda item: item[0])[1]
                for items in by_part.values()
                if any(position <= index for position, _ in items)
            ]
            period_key = calendar.periods[index].period_key
            out.append(_publish(ctx, tb, key, period_key, current))
    return tuple(out)


def _publish(
    ctx: BookContext, tb: TraceBuilder, key: RoleKey, period_key: str, current: Sequence[_Share]
) -> RoleTarget:
    currencies = {share.currencies for share in current}
    if len(currencies) != 1:
        raise _invariant("a role key combines currencies", key.subject_key, period_key=period_key)
    ((txn_currency, functional_currency),) = currencies
    splits = [share for share in current if share.split is not None]
    if splits and len(current) != 1:
        raise _invariant(
            "a split share combines with another part on one role key",
            key.subject_key,
            period_key=period_key,
        )
    fx = key.entry_kind == FX_ENTRY_KIND
    currency = functional_currency if fx else txn_currency
    node_id, amounts = _target_node(
        ctx, tb, key, period_key, current, key.node_subject, currency, fx, splits
    )
    variants: list[RoleVariant] = []
    if any(share.reason is not None for share in current):
        # S14-R-27: one node per reason variant, the untagged remainder first (§14.6).
        reasons = sorted(
            {share.reason for share in current}, key=lambda r: (r is not None, r or "")
        )
        for reason in reasons:
            shares = [share for share in current if share.reason == reason]
            subject = f"{key.node_subject}/{UNTAGGED if reason is None else reason}"
            variant_node, found = _target_node(
                ctx, tb, key, period_key, shares, subject, currency, fx, []
            )
            variants.append(RoleVariant(reason, *found, variant_node))
        summed = (
            sum(v.amount_txn for v in variants),
            sum(v.amount_functional for v in variants),
            sum(v.time_txn for v in variants),
            sum(v.time_functional for v in variants),
        )
        if summed != amounts:
            raise _invariant(
                "the reason variants do not sum to the role target (S14-R-27)",
                key.subject_key,
                period_key=period_key,
            )
    rates = {ref for share in current for ref in share.rates}
    return RoleTarget(
        key=key,
        period_key=period_key,
        txn_currency=txn_currency,
        functional_currency=functional_currency,
        amount_txn=amounts[0],
        amount_functional=amounts[1],
        time_txn=amounts[2],
        time_functional=amounts[3],
        passes=tuple(sorted({name for share in current for name in share.passes})),
        rates=tuple(sorted(rates, key=lambda ref: (ref.rate_key, ref.version_key))),
        node_id=node_id,
        variants=tuple(variants),
    )


def _target_node(
    ctx: BookContext,
    tb: TraceBuilder,
    key: RoleKey,
    period_key: str,
    shares: Sequence[_Share],
    subject: str,
    currency: str,
    fx: bool,
    splits: Sequence[_Share],
) -> tuple[str, tuple[int, int, int, int]]:
    """The ``posting_target`` node of ``shares`` under ``subject`` and their summed amounts
    (txn, functional, time txn, time functional)."""
    amount_txn = sum(share.txn for share in shares)
    amount_functional = sum(share.functional for share in shares)
    time_txn = sum(share.time_txn for share in shares)
    time_functional = sum(share.time_functional for share in shares)
    inputs = [ref for share in shares for ref, _ in share.inputs]
    params: dict[str, str] = {
        "amount_functional": str(amount_functional),
        "signs": "|".join(str(sign) for share in shares for _, sign in share.inputs),
        "time": str(time_functional if fx else time_txn),
    }
    if splits:
        params.update(splits[0].split or {})
    node_id = tb.node(
        measure="posting_target",
        subject_key=subject,
        period_key=period_key,
        value=amount_functional if fx else amount_txn,
        currency=currency,
        minor_unit=ctx.currencies[currency].minor_unit,
        formula_id="post.role_target.v1",
        inputs=inputs,
        params=params,
        narrative_key="post.role_target",
    )
    return node_id, (amount_txn, amount_functional, time_txn, time_functional)
