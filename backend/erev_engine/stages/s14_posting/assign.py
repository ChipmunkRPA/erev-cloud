"""Stage 14 posting classes, posted amounts and role deltas (ENGINE_SPEC_B §14.2.2; END-5).

Private to stage 14 (DG-ENG-07). ``derive_deltas`` compares the cumulative role targets with the
posted amounts of the bundle (RCP-05, RCP-06):

- S14-R-04: ``period_target(rk, p, classes)`` is the cumulative target through the end of p less
  that through the end of p − 1; ``PostedTotals.by_origin`` sums the posted amounts whose origin
  period (else posting period) is p and whose posting class is in the set (``POSTING_CLASSES``);
  a posted amount answers the role key of the subject stored on its ledger lines (04 T-SL-04
  ``subject_key``), except under the one regrouping rule: an amount stored under the group-level
  subject of another combination group — ``<group>@<entity>``, alone or with further components
  — answers the same subject under the current group (``regrouped_subject_key``);
- S14-R-05: compute triggers post ``EVENT`` amounts of open periods and every amount of closed
  periods; ``CLOSE_RELEASE`` posts the ``TIME`` amounts of open periods for the role keys of its
  pass (L2-5-Q-28);
- S14-R-06: a closed-period amount posts where ``s08_estimates_late_events.assign_posting_period``
  places it, with its origin and ``reason_code = LATE_EVENT``; a future period posts nothing;
- S14-R-07: netting reclasses of locked periods are never carried or re-reversed, and the reversal
  target of t is the negation of the reclass posted for t − 1 (posted before, or in this compute),
  naming the rate references of the reclass it negates (S14-R-28);
- S14-R-08: a subject of a contract with a new void carries ``reason_code = VOID`` (L2-5-Q-30);
- S02-R-02: subjects of ``DRAFT`` contracts keep their targets and post nothing;
- S14-R-26 (rev 1.14; ENB-9): a role key whose subject carries a stage 07 opening baseline emits
  no delta for a period ending on or before the cutover (the ERP holds the baseline, so it is
  deemed posted, ENGINE_SPEC S07-R-05) and the first later period measures from it; under
  ``RECOMPUTE_FROM_INCEPTION`` the cutover period posts the S07-R-07 difference (the role target
  less the imported role amount ``onboarding.imported_role_amounts`` derives, less what that
  period already posted) once, dated the cutover, ``reason_code = ONBOARDING_DIFFERENCE``.
- S14-R-27: in a postable period of a subject without a new void, a role key shared by a part
  with a Table 14-A ``reason_code`` (JET-09e ``TERMINATION_ACCELERATION``, JET-09f ``CLAWBACK``)
  posts one delta per reason variant — the variant's movement less the posted amounts carrying
  that reason (untagged: the lines without one) — when every posted line of the origin is
  attributable; a carry, a void or an unattributable line (``LATE_EVENT``, ``VOID``, another
  reason) keeps the single pooled delta of the role key (D-98 candidate 19).
- S14-R-28 (rev 1.50): a delta names the rate references of its role target; one whose target
  supplies none only reverses posted amounts and names the references stamped on them
  (``PostedAmountInput.rate_refs``; ``PostedTotals.rates_at``).

Every delta has a ``posting_delta`` node (§14.6). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.money import format_money
from erev_engine.stages.s12_fx_entities import RateRef
from erev_engine.stages.s14_posting import onboarding
from erev_engine.stages.s14_posting.amount_classes import EVENT, TIME
from erev_engine.stages.s14_posting.targets import (
    COMPONENT_KINDS,
    FX_ENTRY_KIND,
    UNTAGGED,
    RoleKey,
    RoleTarget,
    RoleVariant,
    encode_component,
)
from erev_engine.stages.s14_posting.templates import CLOSE_RUN_PASSES, TEMPLATE_REASONS
from erev_engine.stages.state import AllocatedState, BookContext, PostedIndex
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "COMPUTE_TRIGGERS",
    "LATE_EVENT",
    "POSTING_CLASSES",
    "VOID",
    "PostedTotals",
    "RoleDelta",
    "classes_posted_by",
    "derive_deltas",
    "posting_class",
    "regrouped_subject_key",
    "subject_contracts",
]

LATE_EVENT: Final = "LATE_EVENT"
VOID: Final = "VOID"
CLOSE_RELEASE: Final = "CLOSE_RELEASE"
RECLASS: Final = "NETTING_RECLASS"
REVERSAL: Final = "NETTING_RECLASS_REVERSAL"
_CLOSED: Final = frozenset({"closed", "permanently_locked"})
_BOTH: Final = (EVENT, TIME)

# 04 E-31 posting kind -> posting class (S14-R-04; 05 RCP-05).
POSTING_CLASSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "ENGINE_COMPUTE": EVENT,
        "MANUAL_ADJUSTMENT": EVENT,
        "VOID_REVERSAL": EVENT,
        "CLOSE_RELEASE": TIME,
        "FX_REMEASUREMENT": TIME,
        "NETTING_RECLASS": TIME,
    }
)
# E-87 triggers that post EVENT amounts of open periods and all amounts of closed ones (RCP-08).
COMPUTE_TRIGGERS: Final = frozenset(
    {
        "COMMAND",
        "REPLAY_VERIFY",
        "RESTATE",
        "UPGRADE_VALIDATE",
        "FX_REPUBLISH",
        "POLICY_RERUN",
        "MIGRATION",
        "DRY_RUN",
    }
)


def posting_class(posting_kind: str) -> str:
    """The posting class of a posted line of E-31 ``posting_kind`` (S14-R-04)."""
    found = POSTING_CLASSES.get(posting_kind)
    if found is None:
        raise ValueError(f"unknown posting kind {posting_kind!r} (E-31)")
    return found


def classes_posted_by(trigger: str, pass_name: str | None) -> tuple[str, ...]:
    """The posting classes a computation posts for open periods (S14-R-05; RCP-08)."""
    if trigger in COMPUTE_TRIGGERS:
        if pass_name is not None:
            raise ValueError(f"trigger {trigger} runs no close-run pass (S14-R-05)")
        return (EVENT,)
    if trigger == CLOSE_RELEASE:
        if pass_name not in CLOSE_RUN_PASSES:
            raise ValueError(f"a CLOSE_RELEASE computation names its pass, not {pass_name!r}")
        return (TIME,)
    raise ValueError(f"unknown computation trigger {trigger!r} (E-87)")


def regrouped_subject_key(subject_key: str, group_code: str, members: Collection[str]) -> str:
    """The regrouping rule of S14-R-04 (supervisor rulings R-11 as amended and R-44 (b)).

    A group-level subject begins with the combination group: ``<group>@<entity>``, alone (the FX
    remeasurement subject of a JET-10 part, Table 14-A) or followed by further components (a
    refund-liability component ``<group>@<entity>/<kind>/<source>``, §10.2.4; any later family).
    ``posted`` holds the sealed lines of the current group's member contracts (05 RCP-05), so a
    group-level subject in it that names another group was stored while a member belonged to that
    group. It answers the same subject under the current group: ``group_code`` in place of the
    stored group, every other component unchanged. The amounts of the members then sum under one
    key and a combination posts only the difference to its target.

    Every other subject is returned unchanged: one whose first component is a member contract
    (``members``, CV-21 encoded: ``<contract>@<entity>``), and one without a leading
    ``<component>@`` (an obligation, a cost asset, a loss unit, ``<contract>#…``)."""
    head, at, rest = subject_key.partition("@")
    if not at or "/" in head or "#" in head:
        return subject_key
    current = encode_component(group_code)
    if head == current or head in members:
        return subject_key
    return f"{current}@{rest}"


@dataclass(frozen=True, slots=True)
class PostedTotals:
    """The bundle's posted amounts of one book by role key, origin period and class (RCP-05), with
    the share of each Table 14-A reason and the origins no variant can be attributed (S14-R-27)."""

    amounts: Mapping[tuple[RoleKey, str, str], tuple[int, int]]  # (txn, functional), debit +
    currencies: Mapping[RoleKey, tuple[str, str]]  # (txn currency, functional currency)
    # (key, origin, class, template reason) -> the part of ``amounts`` whose lines carry it.
    tagged: Mapping[tuple[RoleKey, str, str, str], tuple[int, int]] = MappingProxyType({})
    # (key, origin, class) with a line carrying LATE_EVENT, VOID or another non-template reason.
    unattributable: frozenset[tuple[RoleKey, str, str]] = frozenset()
    # (key, origin, class) -> the rate references stamped on the posted lines (S14-R-28).
    rates: Mapping[tuple[RoleKey, str, str], tuple[RateRef, ...]] = MappingProxyType({})

    @classmethod
    def of(
        cls,
        ctx: BookContext,
        index: PostedIndex,
        *,
        group_code: str | None = None,
        contracts: Collection[str] = (),
    ) -> PostedTotals:
        """The posted amounts of ``ctx``'s book by the role key of their stored subject.
        ``group_code`` and ``contracts`` are the combination group of the computation and its
        member contracts, for the regrouping rule of S14-R-04 (``regrouped_subject_key``)."""
        amounts: dict[tuple[RoleKey, str, str], tuple[int, int]] = {}
        currencies: dict[RoleKey, tuple[str, str]] = {}
        tagged: dict[tuple[RoleKey, str, str, str], tuple[int, int]] = {}
        unattributable: set[tuple[RoleKey, str, str]] = set()
        rates: dict[tuple[RoleKey, str, str], set[RateRef]] = {}
        book = str(ctx.book_code)
        members = frozenset(encode_component(contract) for contract in contracts)
        for item in index.amounts:
            if item.book_code != book:
                continue
            if item.posting_class not in _BOTH:
                raise ValueError(f"posted class {item.posting_class!r} is not EVENT or TIME")
            subject_key = item.subject_key
            if group_code is not None:
                subject_key = regrouped_subject_key(subject_key, group_code, members)
            key = RoleKey(
                item.book_code,
                item.entity_code,
                subject_key,
                item.entry_kind,
                item.account_role,
                item.clearing_purpose,
                item.counterparty_entity_code,
            )
            pair = (item.txn_currency, item.functional_currency)
            if currencies.setdefault(key, pair) != pair:
                raise ValueError(f"posted amounts of {key.node_subject} mix currencies (CV-45)")
            origin = item.origin_period_key or item.period_key
            txn, functional = amounts.get((key, origin, item.posting_class), (0, 0))
            amounts[(key, origin, item.posting_class)] = (
                txn + item.amount_txn,
                functional + item.amount_functional,
            )
            if item.rate_refs:
                rates.setdefault((key, origin, item.posting_class), set()).update(
                    RateRef(rate_key, version_key) for rate_key, version_key in item.rate_refs
                )
            reason = item.reason_code
            if reason is None:
                continue
            if reason in TEMPLATE_REASONS:
                tag = (key, origin, item.posting_class, reason)
                txn, functional = tagged.get(tag, (0, 0))
                tagged[tag] = (txn + item.amount_txn, functional + item.amount_functional)
            else:
                unattributable.add((key, origin, item.posting_class))
        return cls(
            MappingProxyType(amounts),
            MappingProxyType(currencies),
            MappingProxyType(tagged),
            frozenset(unattributable),
            MappingProxyType({found: _ordered(refs) for found, refs in rates.items()}),
        )

    def by_origin(self, key: RoleKey, period_key: str, classes: Iterable[str]) -> tuple[int, int]:
        """Σ posted (txn, functional) with origin ``period_key`` and a class in ``classes``."""
        txn = functional = 0
        for name in classes:
            posted_txn, posted_functional = self.amounts.get((key, period_key, name), (0, 0))
            txn += posted_txn
            functional += posted_functional
        return txn, functional

    def by_reason(
        self, key: RoleKey, period_key: str, classes: Iterable[str], reason: str
    ) -> tuple[int, int]:
        """Σ posted (txn, functional) of ``by_origin`` whose lines carry the template ``reason``."""
        txn = functional = 0
        for name in classes:
            posted_txn, posted_functional = self.tagged.get((key, period_key, name, reason), (0, 0))
            txn += posted_txn
            functional += posted_functional
        return txn, functional

    def reasons_at(self, key: RoleKey, period_key: str, classes: Iterable[str]) -> set[str]:
        """The template reasons posted lines of ``by_origin`` carry (S14-R-27)."""
        names = set(classes)
        return {
            reason
            for (found, origin, name, reason) in self.tagged
            if found == key and origin == period_key and name in names
        }

    def attributable(self, key: RoleKey, period_key: str, classes: Iterable[str]) -> bool:
        """S14-R-27: no posted line of ``by_origin`` carries a non-template reason."""
        return not any((key, period_key, name) in self.unattributable for name in classes)

    def rates_at(
        self, key: RoleKey, period_keys: Iterable[str], classes: Iterable[str]
    ) -> tuple[RateRef, ...]:
        """S14-R-28: the rate references stamped on the posted lines of ``by_origin`` over
        ``period_keys`` and ``classes``, sorted; empty when the lines carry none."""
        names = tuple(classes)
        found: set[RateRef] = set()
        for period_key in period_keys:
            for name in names:
                found.update(self.rates.get((key, period_key, name), ()))
        return _ordered(found)


@dataclass(frozen=True, slots=True)
class RoleDelta:
    """A role delta to post: target movement less posted by origin (S14-R-04 to S14-R-08)."""

    key: RoleKey
    posting_period_key: str
    origin_period_key: str | None  # set only for closed-period carries (S14-INV-03)
    posting_class: str  # EVENT | TIME
    # LATE_EVENT or VOID with an origin; VOID, a Table 14-A reason (S14-R-27) or None otherwise.
    reason_code: str | None
    effective_date: date  # L2-5-Q-31
    txn_currency: str
    functional_currency: str
    amount_txn: int  # signed, debit positive
    amount_functional: int
    rates: tuple[RateRef, ...]
    target_node_id: str  # posting_target node of the origin or posting period
    node_id: str  # posting_delta node


def subject_contracts(st: AllocatedState, subject_key: str) -> tuple[str, ...]:
    """The member contracts of a subject: its obligation's, its contract's, the owning member of a
    stage 10 refund component (D-90d L9-RUN-Q-4), else every member."""
    for ob in st.obligations:
        if ob.subject_key == subject_key:
            return (ob.contract_key,)
    head = subject_key.split("#", 1)[0]
    for view in st.contracts:
        encoded = encode_component(view.header.external_id)
        if head.startswith(f"{encoded}@") or head.startswith(f"{encoded}/"):
            return (view.header.external_id,)
    owner = _component_contract(st, subject_key)
    if owner is not None:
        return (owner,)
    return tuple(sorted(view.header.external_id for view in st.contracts))


def _component_contract(st: AllocatedState, subject_key: str) -> str | None:
    """The member a stage 10 refund component key ``<group>@<entity>/<KIND>/<source>`` names
    through its source (§10.2.4; D-90d L9-RUN-Q-4): the obligation subject key of a ``RETURN``
    component, the ``<event key>/<obligation subject key>`` of a ``CONCESSION``, the event key of
    a ``TERMINATION`` or the estimate key of a ``VARIABLE_CONSIDERATION`` component, every head
    CV-21 encoded as ``refund_liability._key`` writes it. ``None`` when the key has another form
    or names no member (the caller falls back to every member)."""
    prefix = f"{encode_component(st.group_code)}@"
    if not subject_key.startswith(prefix):
        return None
    parts = subject_key[len(prefix) :].split("/", 2)
    if len(parts) != 3 or parts[1] not in COMPONENT_KINDS:
        return None
    source = parts[2]
    for ob in st.obligations:
        if source == ob.subject_key or source.endswith(f"/{ob.subject_key}"):
            return ob.contract_key
    for view in st.contracts:
        if source.startswith(f"{encode_component(view.header.external_id)}/"):
            return view.header.external_id
    return None


def _drafts(ctx: BookContext, st: AllocatedState, subjects: Iterable[str]) -> frozenset[str]:
    """S02-R-02: subjects all of whose contracts are ``DRAFT`` in the book."""
    book = str(ctx.book_code)
    status = {
        view.header.external_id: history[-1][1]
        for view in st.contracts
        if (history := view.status_in_book.get(book))
    }
    found = set()
    for subject in subjects:
        contracts = subject_contracts(st, subject)
        if contracts and all(status.get(contract) == "DRAFT" for contract in contracts):
            found.add(subject)
    return frozenset(found)


def derive_deltas(
    ctx: BookContext,
    st: AllocatedState,
    targets: Sequence[RoleTarget],
    posted: PostedTotals,
    tb: TraceBuilder,
    *,
    pass_name: str | None,
    voided: Collection[str],
    imported: Mapping[RoleKey, onboarding.Imported] | None = None,
    openings: Mapping[str, onboarding.Opening] | None = None,
) -> tuple[RoleDelta, ...]:
    """The role deltas of one book (§14.2.2), in role-key order, reversals last (S14-R-07).

    ``imported``: the imported role amounts at the cutover period of the RECOMPUTE openings
    (``onboarding.imported_role_amounts``), read by the S07-R-07 difference (S14-R-26).
    ``openings``: the openings the walker resolves subjects against (``onboarding.openings(st)``
    when None; a synthetic map is a test seam for owner-resolution fixtures).
    """
    classes = classes_posted_by(str(ctx.trigger), pass_name)
    by_key: dict[RoleKey, dict[str, RoleTarget]] = {}
    for target in targets:
        by_key.setdefault(target.key, {})[target.period_key] = target
    keys = set(by_key) | set(posted.currencies)
    subjects = {key.subject_key for key in keys}
    drafts = _drafts(ctx, st, subjects)
    void = {s for s in subjects if set(subject_contracts(st, s)) & set(voided)}
    walker = _Walker(
        ctx,
        tb,
        posted,
        classes,
        pass_name,
        openings=onboarding.openings(st) if openings is None else openings,
        imported=MappingProxyType(dict(imported or {})),
    )
    out: list[RoleDelta] = []
    ordinary = [key for key in keys if key.entry_kind != REVERSAL and key.subject_key not in drafts]
    for key in sorted(ordinary, key=RoleKey.sort_key):
        out.extend(walker.deltas(key, by_key.get(key, {}), key.subject_key in void))
    reclass = [key for key in ordinary if key.entry_kind == RECLASS]
    reversals = walker.reversal_targets(reclass, by_key, out)
    waiting = {key for key in keys if key.entry_kind == REVERSAL and key.subject_key not in drafts}
    for key in sorted(waiting | set(reversals), key=RoleKey.sort_key):
        out.extend(walker.deltas(key, reversals.get(key, {}), key.subject_key in void))
    return tuple(out)


@dataclass
class _Walker:
    """Walks the periods of a role key through the horizon (the pseudocode of §14.2.2)."""

    ctx: BookContext
    tb: TraceBuilder
    posted: PostedTotals
    classes: tuple[str, ...]
    pass_name: str | None
    openings: Mapping[str, onboarding.Opening] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )
    imported: Mapping[RoleKey, onboarding.Imported] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )
    zero_nodes: dict[tuple[RoleKey, str, str], str] = dataclasses.field(default_factory=dict)

    def periods(self, key: RoleKey) -> list[dates.PeriodLike]:
        calendar = self.ctx.entities.get(key.entity)
        if calendar is None:
            raise ValueError(f"role key names the entity {key.entity!r}, absent (CV-45)")
        horizon = self.ctx.horizon[key.entity]
        ordered = sorted(calendar.periods, key=lambda p: (p.start_date, p.end_date))
        end = next(p.end_date for p in ordered if p.period_key == horizon)
        return [period for period in ordered if period.start_date <= end]

    def currencies(self, key: RoleKey, targets: Mapping[str, RoleTarget]) -> tuple[str, str]:
        for target in targets.values():
            return (target.txn_currency, target.functional_currency)
        found = self.posted.currencies.get(key)
        if found is None:
            raise ValueError(f"role key {key.node_subject} has neither target nor posted amount")
        return found

    def deltas(
        self, key: RoleKey, targets: Mapping[str, RoleTarget], void: bool
    ) -> list[RoleDelta]:
        book = str(self.ctx.book_code)
        passes = {name for target in targets.values() for name in target.passes}
        if not targets:  # posted only: the pass follows the entry kind
            passes = {_default_pass(key.entry_kind)}
        out: list[RoleDelta] = []
        previous: RoleTarget | None = None
        # ALG-09 step 5 (S12-R-13): the remeasurements of locked periods are not reposted. A
        # closed period carries only the EVENT share of an FX_REMEASUREMENT role key, and the
        # FX_REMEASUREMENT pass posts the cumulative TIME difference of the locked run into the
        # first later open period, untagged (LATE-POL-181; L6-5).
        fx = key.entry_kind == FX_ENTRY_KIND
        anchor: RoleTarget | None = None  # the target before the current run of locked periods
        locked: list[str] = []
        for period in self.periods(key):
            state = dates.period_state(period, book)
            if state == "future":
                break
            current = targets.get(period.period_key, previous)
            opening = onboarding.resolve(self.openings, key.subject_key, key.entity)
            if opening is not None:
                recompute = opening.method == onboarding.RECOMPUTE
                in_cutover = period.start_date <= opening.cutover <= period.end_date
                if recompute and in_cutover and str(self.ctx.trigger) != CLOSE_RELEASE:
                    # S07-R-07: the cutover period posts the onboarding difference once.
                    delta = self.difference(key, targets, period, current, opening, void)
                    if delta is not None:
                        out.append(delta)
                if period.end_date <= opening.cutover or (recompute and in_cutover):
                    # S14-R-26: the period's target is the opening baseline the ERP already
                    # holds (RECOMPUTE: plus the difference just posted); nothing else posts and
                    # the next period measures its movement from it (S07-R-05).
                    previous = current
                    locked = []
                    continue
            if state in _CLOSED:
                carried = key.entry_kind not in (RECLASS, REVERSAL)
                if fx:
                    anchor = previous if not locked else anchor
                    locked.append(period.period_key)
                if carried and str(self.ctx.trigger) != CLOSE_RELEASE:
                    basis = EVENT if fx else "ALL"
                    out.extend(
                        self.delta(key, targets, period, current, previous, basis, void, carry=fx)
                    )
            elif state in dates.POSTABLE_STATES:
                for name in self.classes:
                    if name == TIME and self.pass_name not in passes:
                        continue
                    if name == TIME and locked:
                        out.extend(
                            self.delta(
                                key, targets, period, current, anchor, name, void, locked=locked
                            )
                        )
                    else:
                        out.extend(self.delta(key, targets, period, current, previous, name, void))
                locked = []
            else:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "the period carries an unknown E-04 state",
                    subject_key=key.subject_key,
                    detail={"rule": "CV-45", "period_key": period.period_key, "state": state},
                )
            previous = current
        return out

    def delta(
        self,
        key: RoleKey,
        targets: Mapping[str, RoleTarget],
        period: dates.PeriodLike,
        current: RoleTarget | None,
        previous: RoleTarget | None,
        basis: str,
        void: bool,
        *,
        carry: bool = False,
        locked: Sequence[str] = (),
    ) -> list[RoleDelta]:
        """The deltas of ``key`` for ``period`` and ``basis``: one pooled delta, or one per reason
        variant (S14-R-27). ``carry``: a closed-period carry of the ``basis`` share with its
        origin. ``locked``: the locked periods since ``previous``, whose posted amounts of the
        class count as paid."""
        classes = _BOTH if basis == "ALL" else (basis,)
        now, before = _amounts(current, basis), _amounts(previous, basis)
        paid = self.posted.by_origin(key, period.period_key, classes)
        for locked_key in locked:
            earlier = self.posted.by_origin(key, locked_key, classes)
            paid = (paid[0] + earlier[0], paid[1] + earlier[1])
        amount = (now[0] - before[0] - paid[0], now[1] - before[1] - paid[1])
        if amount == (0, 0):
            return []
        # S14-R-28: the references of the posted amounts the delta is measured against, named by
        # a delta whose role target supplies none.
        reversed_rates = self.posted.rates_at(key, (period.period_key, *locked), classes)
        if basis == "ALL" or carry:
            # Imported at call time: stage 08 imports stage 01, whose classifier reads the stage
            # registry, and the registry imports this stage (L2-5-Q-37).
            from erev_engine.stages.s08_estimates_late_events import assign_posting_period

            assignment = assign_posting_period(self.ctx, key.entity, period.end_date)
            if assignment.posting_period_key is None:
                return []  # no later open period in the bundle (S08-R-08)
            placed = _Placement(
                assignment.posting_period_key,
                period.period_key,
                EVENT,
                VOID if void else assignment.reason_code,
                period.end_date,
            )
            return [
                self._emit(
                    key,
                    targets,
                    period,
                    current,
                    previous,
                    basis,
                    paid,
                    amount,
                    placed,
                    reversed_rates=reversed_rates,
                )
            ]
        effective = period.start_date if key.entry_kind == REVERSAL else period.end_date
        placed = _Placement(period.period_key, None, basis, VOID if void else None, effective)
        reasons = _variant_reasons(current, previous) | self.posted.reasons_at(
            key, period.period_key, classes
        )
        pooled = (
            not reasons
            or void
            or bool(locked)
            or not self.posted.attributable(key, period.period_key, classes)
        )
        if pooled:
            return [
                self._emit(
                    key,
                    targets,
                    period,
                    current,
                    previous,
                    basis,
                    paid,
                    amount,
                    placed,
                    reversed_rates=reversed_rates,
                )
            ]
        # S14-R-27: one delta per variant; the untagged variant takes the untagged posted lines.
        out: list[RoleDelta] = []
        summed = (0, 0)
        tagged_paid = (0, 0)
        for reason in reasons:
            if reason is None:
                continue
            found = self.posted.by_reason(key, period.period_key, classes, reason)
            tagged_paid = (tagged_paid[0] + found[0], tagged_paid[1] + found[1])
        for reason in sorted(reasons, key=lambda r: (r is not None, r or "")):
            if reason is None:
                variant_paid = (paid[0] - tagged_paid[0], paid[1] - tagged_paid[1])
            else:
                variant_paid = self.posted.by_reason(key, period.period_key, classes, reason)
            v_now = _variant_amounts(current, reason, basis)
            v_before = _variant_amounts(previous, reason, basis)
            variant_amount = (
                v_now[0] - v_before[0] - variant_paid[0],
                v_now[1] - v_before[1] - variant_paid[1],
            )
            summed = (summed[0] + variant_amount[0], summed[1] + variant_amount[1])
            if variant_amount == (0, 0):
                continue
            tagged_placement = dataclasses.replace(placed, reason=reason)
            out.append(
                self._emit(
                    key,
                    targets,
                    period,
                    current,
                    previous,
                    basis,
                    variant_paid,
                    variant_amount,
                    tagged_placement,
                    split=True,
                    reversed_rates=reversed_rates,
                )
            )
        if summed != amount:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the reason variant deltas do not sum to the role key's delta",
                subject_key=key.subject_key,
                detail={
                    "rule": "S14-R-27",
                    "period_key": period.period_key,
                    "amount_txn": str(amount[0]),
                    "variants_txn": str(summed[0]),
                },
            )
        return out

    def _emit(
        self,
        key: RoleKey,
        targets: Mapping[str, RoleTarget],
        period: dates.PeriodLike,
        current: RoleTarget | None,
        previous: RoleTarget | None,
        basis: str,
        paid: tuple[int, int],
        amount: tuple[int, int],
        placed: _Placement,
        *,
        split: bool = False,
        reversed_rates: tuple[RateRef, ...] = (),
    ) -> RoleDelta:
        """The ``posting_delta`` node and ``RoleDelta`` of one pooled delta of the role key, or,
        with ``split``, of the reason variant ``placed.reason`` (None: untagged; S14-R-27).
        ``reversed_rates``: the rate references of the posted amounts the delta is measured
        against, which it names when its role target supplies none (S14-R-28)."""
        txn_currency, functional_currency = self.currencies(key, targets)
        rates = () if current is None else current.rates
        from_posted = not rates and bool(reversed_rates)
        if from_posted:
            rates = reversed_rates
        fx = key.entry_kind == FX_ENTRY_KIND
        currency = functional_currency if fx else txn_currency
        mu = self.ctx.currencies[currency].minor_unit
        reason = placed.reason
        subject = key.node_subject
        if split:
            subject = f"{key.node_subject}/{UNTAGGED if reason is None else reason}"
        if not split:
            target_node = self.target_node(key, period.period_key, current)
            previous_node = None if previous is None else previous.node_id
            time_now = (
                0 if current is None else (current.time_functional if fx else current.time_txn)
            )
            time_before = 0
            if previous is not None:
                time_before = previous.time_functional if fx else previous.time_txn
        else:
            target_node = self.variant_node(key, period.period_key, current, reason, subject)
            found = _variant_of(previous, reason)
            if previous is None:
                previous_node = None
            elif found is not None:
                previous_node = found.node_id
            elif reason is None and not previous.variants:
                previous_node = previous.node_id  # every earlier share was untagged
            else:
                previous_node = None  # the variant did not exist: before = 0
            now_v = _variant_amounts(current, reason, TIME)
            before_v = _variant_amounts(previous, reason, TIME) if previous_node else (0, 0)
            time_now = now_v[1] if fx else now_v[0]
            time_before = before_v[1] if fx else before_v[0]
        inputs: list[str | SourceRef] = [target_node]
        if previous_node is not None:
            inputs.append(previous_node)
        ref_id = f"posted/{key.book_code}/{key.entity}/{subject}/{period.period_key}/{basis}"
        detail = {"value": format_money(paid[1] if fx else paid[0], mu)}
        if from_posted:
            # D-88 L7-6-Q-1: the full list of a line's rates stays in its trace.
            detail["rate_keys"] = "|".join(ref.rate_key for ref in rates)
        inputs.append(SourceRef("source_record", ref_id, detail))
        node_subject = f"{subject}/{placed.posting_class}" + (
            "" if placed.origin is None else f"/{placed.origin}"
        )
        node_id = self.tb.node(
            measure="posting_delta",
            subject_key=node_subject,
            period_key=placed.posting,
            value=amount[1] if fx else amount[0],
            currency=currency,
            minor_unit=mu,
            formula_id="post.delta.v1",
            inputs=inputs,
            params={
                "class": basis,
                "previous": "true" if previous_node is not None else "false",
                "time": str(time_now),
                "time_previous": str(time_before),
            },
            narrative_key="post.delta",
        )
        return RoleDelta(
            key=key,
            posting_period_key=placed.posting,
            origin_period_key=placed.origin,
            posting_class=placed.posting_class,
            reason_code=placed.reason,
            effective_date=placed.effective,
            txn_currency=txn_currency,
            functional_currency=functional_currency,
            amount_txn=amount[0],
            amount_functional=amount[1],
            rates=rates,
            target_node_id=target_node,
            node_id=node_id,
        )

    def difference(
        self,
        key: RoleKey,
        targets: Mapping[str, RoleTarget],
        period: dates.PeriodLike,
        current: RoleTarget | None,
        opening: onboarding.Opening,
        void: bool,
    ) -> RoleDelta | None:
        """The S07-R-07 onboarding difference of a role key at its cutover period: the recomputed
        shares of the eligible parts less the imported role amount less what the period already
        posted (both classes), dated the cutover, ``reason_code = ONBOARDING_DIFFERENCE``, class
        EVENT; a closed cutover period posts it in the RCP-04 period with the cutover period as
        origin. Only an ``ELIGIBLE`` key (``onboarding.Imported``) has a difference: a deemed-posted
        or refused key returns None, and eligibility is never inferred from key presence (S14-R-26
        rev 1.15; C5-PH2-R1)."""
        state = self.imported.get(key)
        if state is None or state.status != onboarding.ELIGIBLE:
            return None
        now = state.recomputed
        imported = state.imported
        paid = self.posted.by_origin(key, period.period_key, _BOTH)
        amount = (now[0] - imported[0] - paid[0], now[1] - imported[1] - paid[1])
        if amount == (0, 0):
            return None
        book = str(self.ctx.book_code)
        if dates.period_state(period, book) in _CLOSED:
            from erev_engine.stages.s08_estimates_late_events import assign_posting_period

            assignment = assign_posting_period(self.ctx, key.entity, opening.cutover)
            if assignment.posting_period_key is None:
                return None  # no later open period in the bundle (S08-R-08)
            posting, origin = assignment.posting_period_key, period.period_key
        else:
            posting, origin = period.period_key, None
        txn_currency, functional_currency = self.currencies(key, targets)
        mu = self.ctx.currencies[txn_currency].minor_unit
        target_node = self.target_node(key, period.period_key, current)
        # post.delta.v1 takes the target and one deducted source: the imported role amount the
        # ERP holds plus what the cutover period already posted (params show both).
        ref_id = (
            f"imported/{key.book_code}/{key.entity}/{key.node_subject}/{period.period_key}"
            f"@{opening.event_key}"
        )
        inputs: list[str | SourceRef] = [
            target_node,
            SourceRef("source_record", ref_id, {"value": format_money(imported[0] + paid[0], mu)}),
        ]
        node_id = self.tb.node(
            measure="posting_delta",
            subject_key=f"{key.node_subject}/{onboarding.REASON}",
            period_key=posting,
            value=amount[0],
            currency=txn_currency,
            minor_unit=mu,
            formula_id="post.delta.v1",
            inputs=inputs,
            params={
                "class": EVENT,
                "cutover_date": opening.cutover.isoformat(),
                "imported": str(imported[0]),
                "owner": opening.owner,
                "posted": str(paid[0]),
                "previous": "false",
                "reason": onboarding.REASON,
                "time": "0",
                "time_previous": "0",
            },
            narrative_key="post.delta",
        )
        return RoleDelta(
            key=key,
            posting_period_key=posting,
            origin_period_key=origin,
            posting_class=EVENT,
            reason_code=VOID if void else onboarding.REASON,
            effective_date=opening.cutover,
            txn_currency=txn_currency,
            functional_currency=functional_currency,
            amount_txn=amount[0],
            amount_functional=amount[1],
            rates=(() if current is None else current.rates)
            or self.posted.rates_at(key, (period.period_key,), _BOTH),
            target_node_id=target_node,
            node_id=node_id,
        )

    def variant_node(
        self,
        key: RoleKey,
        period_key: str,
        current: RoleTarget | None,
        reason: str | None,
        subject: str,
    ) -> str:
        """The variant's ``posting_target`` node, or a zero node when the target has no such
        variant (a reason only posted lines carry; S14-R-27)."""
        found = _variant_of(current, reason)
        if found is not None:
            return found.node_id
        if current is not None and reason is None and not current.variants:
            return current.node_id  # every share is untagged: the role target is the variant
        return self.zero_node(key, period_key, subject)

    def target_node(self, key: RoleKey, period_key: str, current: RoleTarget | None) -> str:
        """The posting_target node of the period, or a zero node for a posted-only role key."""
        if current is not None:
            return current.node_id
        return self.zero_node(key, period_key, key.node_subject)

    def zero_node(self, key: RoleKey, period_key: str, subject: str) -> str:
        """A zero ``posting_target`` node under ``subject`` (a posted-only role key or variant)."""
        found = self.zero_nodes.get((key, period_key, subject))
        if found is None:
            txn_currency, functional_currency = self.currencies(key, {})
            currency = functional_currency if key.entry_kind == FX_ENTRY_KIND else txn_currency
            found = self.tb.node(
                measure="posting_target",
                subject_key=subject,
                period_key=period_key,
                value=0,
                currency=currency,
                minor_unit=self.ctx.currencies[currency].minor_unit,
                formula_id="post.role_target.v1",
                inputs=[],
                params={"amount_functional": "0", "signs": "", "time": "0"},
                narrative_key="post.role_target",
            )
            self.zero_nodes[(key, period_key, subject)] = found
        return found

    def reversal_targets(
        self,
        reclass: Iterable[RoleKey],
        by_key: Mapping[RoleKey, Mapping[str, RoleTarget]],
        deltas: Sequence[RoleDelta],
    ) -> dict[RoleKey, dict[str, RoleTarget]]:
        """S14-R-07: the reversal of t negates the reclass posted for t − 1 (ALG-02 step 5). Its
        amount is that reclass's, so it names the rate references of what it negates: the posted
        reclass lines and the reclass delta of this compute; where the posted lines carry none,
        those of the reclass role target of t − 1, the carrying at its closing rate (S12-R-09;
        S14-R-28)."""
        emitted = {
            (delta.key, delta.posting_period_key): delta
            for delta in deltas
            if delta.key.entry_kind == RECLASS and delta.origin_period_key is None
        }
        out: dict[RoleKey, dict[str, RoleTarget]] = {}
        for key in sorted(reclass, key=RoleKey.sort_key):
            reversal = dataclasses.replace(key, entry_kind=REVERSAL)
            txn_currency, functional_currency = self.currencies(key, by_key.get(key, {}))
            mu = self.ctx.currencies[txn_currency].minor_unit
            periods = self.periods(key)
            running_txn = running_functional = 0
            previous_node: str | None = None
            for prior, period in zip(periods, periods[1:], strict=False):
                paid = self.posted.by_origin(key, prior.period_key, _BOTH)
                delta = emitted.get((key, prior.period_key))
                negated = set(self.posted.rates_at(key, (prior.period_key,), _BOTH))
                if delta is not None:
                    negated.update(delta.rates)
                target = by_key.get(key, {}).get(prior.period_key)
                if not negated and target is not None:
                    negated.update(target.rates)
                txn = -(paid[0] + (0 if delta is None else delta.amount_txn))
                functional = -(paid[1] + (0 if delta is None else delta.amount_functional))
                if previous_node is None and txn == 0 and functional == 0:
                    continue
                running_txn += txn
                running_functional += functional
                inputs: list[str | SourceRef] = []
                signs: list[str] = []
                if previous_node is not None:
                    inputs.append(previous_node)
                    signs.append("1")
                ref_id = (
                    f"posted/{key.book_code}/{key.entity}/{key.node_subject}/{prior.period_key}"
                )
                detail = {"value": format_money(paid[0], mu)}
                inputs.append(SourceRef("source_record", ref_id, detail))
                signs.append("-1")
                if delta is not None:
                    inputs.append(delta.node_id)
                    signs.append("-1")
                node_id = self.tb.node(
                    measure="posting_target",
                    subject_key=reversal.node_subject,
                    period_key=period.period_key,
                    value=running_txn,
                    currency=txn_currency,
                    minor_unit=mu,
                    formula_id="post.role_target.v1",
                    inputs=inputs,
                    params={
                        "amount_functional": str(running_functional),
                        "signs": "|".join(signs),
                        "time": str(running_txn),
                    },
                    narrative_key="post.role_target",
                )
                out.setdefault(reversal, {})[period.period_key] = RoleTarget(
                    key=reversal,
                    period_key=period.period_key,
                    txn_currency=txn_currency,
                    functional_currency=functional_currency,
                    amount_txn=running_txn,
                    amount_functional=running_functional,
                    time_txn=running_txn,
                    time_functional=running_functional,
                    passes=(RECLASS,),
                    rates=_ordered(negated),
                    node_id=node_id,
                )
                previous_node = node_id
        return out


def _ordered(refs: Iterable[RateRef]) -> tuple[RateRef, ...]:
    """Distinct rate references in (rate key, version key) order, as role targets hold them."""
    return tuple(sorted(set(refs), key=lambda ref: (ref.rate_key, ref.version_key)))


def _default_pass(entry_kind: str) -> str:
    if entry_kind in (RECLASS, REVERSAL):
        return RECLASS
    if entry_kind == FX_ENTRY_KIND:
        return FX_ENTRY_KIND
    return CLOSE_RELEASE


@dataclass(frozen=True, slots=True)
class _Placement:
    """Where a delta posts: period, origin, class, reason, effective date (S14-R-06, S14-R-08)."""

    posting: str
    origin: str | None
    posting_class: str
    reason: str | None
    effective: date


def _variant_of(target: RoleTarget | None, reason: str | None) -> RoleVariant | None:
    if target is None:
        return None
    for variant in target.variants:
        if variant.reason == reason:
            return variant
    return None


def _variant_reasons(*targets: RoleTarget | None) -> set[str | None]:
    """The reasons of the variants of ``targets`` (S14-R-27); empty when none has variants."""
    return {
        variant.reason for target in targets if target is not None for variant in target.variants
    }


def _variant_amounts(target: RoleTarget | None, reason: str | None, basis: str) -> tuple[int, int]:
    """The (txn, functional) amounts of the ``basis`` class of one variant: the variant's own when
    the target has variants, the whole target for the untagged variant of a target without any,
    and 0 for a variant the target does not carry."""
    if target is None:
        return (0, 0)
    found = _variant_of(target, reason)
    if found is None:
        if reason is None and not target.variants:
            return _amounts(target, basis)
        return (0, 0)
    if basis == TIME:
        return (found.time_txn, found.time_functional)
    if basis == EVENT:
        return (
            found.amount_txn - found.time_txn,
            found.amount_functional - found.time_functional,
        )
    return (found.amount_txn, found.amount_functional)


def _amounts(target: RoleTarget | None, basis: str) -> tuple[int, int]:
    if target is None:
        return (0, 0)
    if basis == TIME:
        return (target.time_txn, target.time_functional)
    if basis == EVENT:
        return (
            target.amount_txn - target.time_txn,
            target.amount_functional - target.time_functional,
        )
    return (target.amount_txn, target.amount_functional)
