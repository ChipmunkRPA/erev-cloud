"""Stage 14 entries, keys, dimensions and accounts (ENGINE_SPEC_B §14.2.3, §14.2.4; END-6).

Private to stage 14 (DG-ENG-07). ``group_into_entries`` turns the role deltas into posting intents:

- S14-R-12: one entry per (book, entity, posting period, origin period, entry kind, posting class,
  subject, reason code); lines debit first, then by role, clearing purpose and counterparty; the
  intents sort by ``entry_key``, so ``entry_no`` is the 1-based position (T-SL-04);
- S14-R-10, S14-INV-01: each part balances per class and period in both currencies and posted
  amounts balanced when sealed, so every entry balances; a line side follows its transaction
  amount, else its functional amount, and a delta whose two amounts differ in sign posts a
  transaction line and a functional line of the same role (S14-INV-09);
- S14-R-11: the engine never emits ``ROUNDING``;
- S14-R-13, S14-INV-05: dimensions ``contract`` (combination group), ``contract_key``,
  ``obligation_key`` where the subject is an obligation, ``product`` or ``revenue_category``, the
  obligation's dimensions and the resolved rule's defaults; counterparty exactly on intercompany
  roles, ``clearing_purpose`` exactly on ``BILLING_CLEARING``, never a reserved role;
- S14-R-13a: every line carries ``source_event_keys``, the first-included events of the delta's
  subject's member contracts in ENG-06 order (the ``new_events`` binding of stage 13) — or, when
  those contracts had none, the group's first-included events (a combination group is one
  allocation unit; D-98 102b) — while ``source_event_key`` stays ``None``: a cumulative delta
  aggregates events (L2-5-Q-36) and the set is its lineage, not an apportionment (D-98 95);
- S14-R-14: a missing account yields ``ACCOUNT_MAPPING_MISSING`` and no intent;
- S14-R-15: ``entry_key`` and ``line_key`` are ``canonical.sha256_hex`` of the named members; the
  functional line of an opposed delta adds ``currency_leg``.

Foreign-currency lines publish the rate references behind their amounts in ``line_rates``
(S14-R-28; REQ-FX-006; L2-5-Q-35), and one that names none is refused here, before persistence
(S14-INV-08). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import IntentLine, PostingIntent
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.stages.s12_fx_entities import RateRef
from erev_engine.stages.s14_posting.accounts import Resolution, emit, missing, resolve
from erev_engine.stages.s14_posting.assign import RoleDelta, subject_contracts
from erev_engine.stages.s14_posting.targets import RoleKey
from erev_engine.stages.s14_posting.templates import (
    INTERCOMPANY_ROLES,
    RESERVED_ROLES,
    TEMPLATE_REASONS,
)
from erev_engine.stages.state import AllocatedState, BookContext, Finding, ObligationState
from erev_engine.trace import TraceBuilder

REVENUE_ROLE: Final = "REVENUE"  # E-01 (S15-R-15 tags on REVENUE lines)

__all__ = ["Entries", "entry_key", "group_into_entries", "line_key", "lineage_keys"]

ROUNDING = "ROUNDING"
# S14-R-15: the line-key member ``currency_leg`` of the functional line of an opposed delta.
FUNCTIONAL_LEG: Final = "FUNCTIONAL"


@dataclass(frozen=True, slots=True)
class Entries:
    """The posting intents of one book and the members ``PostingIntent`` does not carry."""

    intents: tuple[PostingIntent, ...]  # ascending entry key (S14-R-12)
    effective_dates: Mapping[str, date]  # entry key -> effective date (L2-5-Q-31)
    line_rates: Mapping[str, tuple[RateRef, ...]]  # line key -> pinned rates (L2-5-Q-35)
    findings: tuple[Finding, ...]  # CV-43 order


def entry_key(delta: RoleDelta) -> str:
    """S14-R-15: SHA-256 of the entry members of a delta."""
    return sha256_hex(
        {
            "book_code": delta.key.book_code,
            "entity": delta.key.entity,
            "entry_kind": delta.key.entry_kind,
            "origin_period_key": delta.origin_period_key,
            "posting_class": delta.posting_class,
            "posting_period_key": delta.posting_period_key,
            "reason_code": delta.reason_code,
            "subject_key": delta.key.subject_key,
        }
    )


def line_key(delta: RoleDelta, *, functional_leg: bool = False) -> str:
    """S14-R-15: SHA-256 of the line members of a delta (DG §5.17). A reason-variant line
    (S14-R-27) adds its Table 14-A ``reason_code``, because the untagged line of the same role,
    period, origin, class and subject may sit in another entry of the posting. The functional line
    of an opposed delta (S14-R-10; ``functional_leg``) adds ``currency_leg``, because its
    transaction line keeps the delta's own key. Every other line keeps the ten-member object, so
    the EX-14-A vector stands."""
    members: dict[str, object] = {
        "account_role": delta.key.account_role,
        "book_code": delta.key.book_code,
        "clearing_purpose": delta.key.clearing_purpose,
        "counterparty_entity": delta.key.counterparty_entity,
        "entity": delta.key.entity,
        "entry_kind": delta.key.entry_kind,
        "origin_period_key": delta.origin_period_key,
        "posting_class": delta.posting_class,
        "posting_period_key": delta.posting_period_key,
        "subject_key": delta.key.subject_key,
    }
    if delta.reason_code in TEMPLATE_REASONS:
        members["reason_code"] = delta.reason_code
    if functional_leg:
        members["currency_leg"] = FUNCTIONAL_LEG
    return sha256_hex(members)


def _invariant(message: str, delta: RoleDelta, invariant: str, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=delta.key.subject_key,
        detail={
            **detail,
            "entry_kind": delta.key.entry_kind,
            "invariant": invariant,
            "posting_period_key": delta.posting_period_key,
        },
    )


def _check_roles(delta: RoleDelta) -> None:
    """S14-INV-05 and S14-R-11 over one line."""
    key = delta.key
    if key.account_role in RESERVED_ROLES or key.account_role == ROUNDING:
        raise _invariant("the engine emits a reserved or rounding role", delta, "S14-INV-05")
    if (key.account_role == "BILLING_CLEARING") != (key.clearing_purpose is not None):
        raise _invariant(
            "clearing_purpose belongs exactly on BILLING_CLEARING", delta, "S14-INV-05"
        )
    if (key.account_role in INTERCOMPANY_ROLES) != (key.counterparty_entity is not None):
        raise _invariant(
            "a counterparty belongs exactly on intercompany roles", delta, "S14-INV-05"
        )


def _check_rates(delta: RoleDelta) -> None:
    """S14-INV-08: a line whose transaction currency is not its functional currency names at least
    one rate reference (S14-R-28; REQ-FX-006; 04 T-SL-04 ``ck_subledger_line__fx``)."""
    if delta.txn_currency != delta.functional_currency and not delta.rates:
        raise _invariant(
            "a foreign-currency line names no rate reference",
            delta,
            "S14-INV-08",
            account_role=delta.key.account_role,
            amount_functional=str(delta.amount_functional),
            amount_txn=str(delta.amount_txn),
            functional_currency=delta.functional_currency,
            origin_period_key=delta.origin_period_key or "",
            txn_currency=delta.txn_currency,
        )


def _legs(delta: RoleDelta) -> tuple[tuple[int, int, bool], ...]:
    """S14-R-10: the (transaction amount, functional amount, functional leg) of each line of a
    delta. The two amounts of a role delta are derived independently (S14-R-04), so with every
    rate positive they can still differ in sign; such a delta posts a transaction line and a
    functional line, which carry its two signed totals unchanged (no rate is used and no gain or
    loss line arises). Every other delta posts one line."""
    txn, functional = delta.amount_txn, delta.amount_functional
    if txn and functional and (txn > 0) != (functional > 0):
        return ((txn, 0, False), (0, functional, True))
    return ((txn, functional, False),)


def _side(amount_txn: int, amount_functional: int) -> str:
    """The side of a line: that of its transaction amount, else of its functional amount. The
    non-zero amounts of a line share one side (S14-INV-09; ``_legs``)."""
    return "D" if (amount_txn or amount_functional) > 0 else "C"


def _dimensions(
    st: AllocatedState,
    obligation: ObligationState | None,
    key: RoleKey,
    resolution: Resolution,
) -> Mapping[str, str]:
    """JET rule R3 dimensions of a line (S14-R-13); a ``REVENUE`` line of an obligation also
    carries its S15-R-15 disaggregation tags (``ObligationState.dimensions``; EDS-4). A tag that
    shares a code with an R3 dimension (``revenue_category``) is the selected value: the tags are
    the configured source (``state.disaggregation_tags``), so the R3 default does not overwrite it
    (Codex C4-R1)."""
    dims = {**resolution.default_dimensions}
    tags: Mapping[str, str] = {}
    if obligation is not None and key.account_role == REVENUE_ROLE:
        tags = obligation.dimensions
        dims.update(tags)
    dims["contract"] = st.group_code
    if obligation is not None:
        dims["contract_key"] = obligation.contract_key
        dims["obligation_key"] = obligation.obligation_key
        if obligation.product_code is not None:
            dims["product"] = obligation.product_code
        if obligation.revenue_category is not None and "revenue_category" not in tags:
            dims["revenue_category"] = obligation.revenue_category
    else:
        contracts = subject_contracts(st, key.subject_key)
        if len(contracts) == 1:
            dims["contract_key"] = contracts[0]
        product, category = _contract_scope(st, key.subject_key)
        if product is not None:
            dims["product"] = product
        if category is not None:
            dims["revenue_category"] = category
    return MappingProxyType(dict(sorted(dims.items())))


def lineage_keys(
    members: Collection[str], new_events: Sequence[tuple[str, str]]
) -> tuple[str, ...]:
    """S14-R-13a: the first-included events of the subject's member contracts in the ENG-06 order
    of ``new_events``; when those contracts had none, the group's first-included events (every
    member, same order) — a combination group is one allocation unit, so another member's event
    legitimately moves this subject's targets (D-98 candidate 102b). Empty only when nothing was
    first included at all (a trigger-only recomputation) or when the caller bound no events."""
    own = tuple(event_key for contract, event_key in new_events if contract in members)
    if own:
        return own
    return tuple(event_key for _, event_key in new_events)


def _source_events(
    st: AllocatedState, subject_key: str, new_events: Sequence[tuple[str, str]]
) -> tuple[str, ...]:
    """``lineage_keys`` over the subject's member contracts (``subject_contracts``)."""
    return lineage_keys(set(subject_contracts(st, subject_key)), new_events)


def _contract_scope(st: AllocatedState, subject_key: str) -> tuple[str | None, str | None]:
    """The product and revenue category of a line whose subject is not an obligation: those every
    obligation of its one member contract shares, else None (JET rule R3; S14-R-13; L5-5-Q-8)."""
    contracts = subject_contracts(st, subject_key)
    if len(contracts) != 1:
        return None, None
    members = [ob for ob in st.obligations if ob.contract_key == contracts[0]]
    products = {ob.product_code for ob in members}
    categories = {ob.revenue_category for ob in members}
    return (
        next(iter(products)) if len(products) == 1 else None,
        next(iter(categories)) if len(categories) == 1 else None,
    )


def group_into_entries(
    ctx: BookContext,
    st: AllocatedState,
    deltas: Sequence[RoleDelta],
    tb: TraceBuilder,
    *,
    new_events: Sequence[tuple[str, str]] = (),
) -> Entries:
    """The balanced posting intents of one book (S14-R-10 to S14-R-15)."""
    obligations = {ob.subject_key: ob for ob in st.obligations}
    lineage: dict[str, tuple[str, ...]] = {}
    groups: dict[tuple[str, ...], list[RoleDelta]] = {}
    for delta in deltas:
        members = (
            delta.key.book_code,
            delta.key.entity,
            delta.posting_period_key,
            delta.origin_period_key or "",
            delta.key.entry_kind,
            delta.posting_class,
            delta.key.subject_key,
            delta.reason_code or "",
        )
        groups.setdefault(members, []).append(delta)
    intents: list[PostingIntent] = []
    effective: dict[str, date] = {}
    rates: dict[str, tuple[RateRef, ...]] = {}
    findings: list[Finding] = []
    for group in sorted(groups):
        items = groups[group]
        first = items[0]
        for delta in items:
            _check_roles(delta)
            _check_rates(delta)
        if sum(d.amount_txn for d in items) or sum(d.amount_functional for d in items):
            raise _invariant(
                "an entry does not balance",
                first,
                "S14-INV-01",
                amount_functional=str(sum(d.amount_functional for d in items)),
                amount_txn=str(sum(d.amount_txn for d in items)),
                origin_period_key=first.origin_period_key or "",
            )
        lines: list[IntentLine] = []
        for delta in items:
            obligation = obligations.get(delta.key.subject_key)
            scope = (
                (None, None)
                if obligation is not None
                else _contract_scope(st, delta.key.subject_key)
            )
            resolution = resolve(ctx, obligation, delta.key, subject_scope=scope)
            if resolution is None:
                findings.append(missing(ctx, st, obligation, delta.key))
                continue
            subject = delta.key.subject_key
            if subject not in lineage:
                lineage[subject] = _source_events(st, subject, new_events)
            dimensions = _dimensions(st, obligation, delta.key, resolution)
            for amount_txn, amount_functional, functional_leg in _legs(delta):
                key = line_key(delta, functional_leg=functional_leg)
                emit(ctx, tb, resolution, key, delta.posting_period_key)
                lines.append(
                    IntentLine(
                        line_key=key,
                        side=_side(amount_txn, amount_functional),
                        account_role=delta.key.account_role,
                        clearing_purpose=delta.key.clearing_purpose,
                        counterparty_entity=delta.key.counterparty_entity,
                        account_code=resolution.account_code,
                        amount_txn=abs(amount_txn),
                        amount_functional=abs(amount_functional),
                        txn_currency=delta.txn_currency,
                        functional_currency=delta.functional_currency,
                        dimensions=dimensions,
                        source_event_key=None,  # a cumulative delta aggregates events (L2-5-Q-36)
                        trace_node_id=delta.target_node_id,
                        source_event_keys=lineage[subject],  # S14-R-13a
                    )
                )
                if delta.txn_currency != delta.functional_currency:
                    rates[key] = delta.rates  # both lines of an opposed delta (S14-R-28)
        lines.sort(
            key=lambda line: (
                0 if line.side == "D" else 1,
                line.account_role,
                line.clearing_purpose or "",
                line.counterparty_entity or "",
            )
        )
        key = entry_key(first)
        intents.append(
            PostingIntent(
                entry_key=key,
                book_code=first.key.book_code,
                entity=first.key.entity,
                posting_period_key=first.posting_period_key,
                origin_period_key=first.origin_period_key,
                entry_kind=first.key.entry_kind,
                posting_class=first.posting_class,
                subject_key=first.key.subject_key,
                reason_code=first.reason_code,
                lines=tuple(lines),
            )
        )
        effective[key] = first.effective_date
    if findings:
        return Entries((), MappingProxyType({}), MappingProxyType({}), _sorted(findings))
    intents.sort(key=lambda intent: intent.entry_key)
    return Entries(
        tuple(intents),
        MappingProxyType(dict(sorted(effective.items()))),
        MappingProxyType(dict(sorted(rates.items()))),
        (),
    )


def _sorted(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    unique = {(f.sort_key()): f for f in findings}
    return tuple(unique[key] for key in sorted(unique))
