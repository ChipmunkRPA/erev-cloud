"""RPT-03 ``contract_balance_rollforward`` Contract balance rollforward (SCREENS_B §5.6.1 RPT-03;
ENGINE_SPEC_B §15.2.2 S15-R-03 to S15-R-07, EX-15-B; S10-R-08; POLICIES POL-004, POL-126; 03
REQ-RPT-006; CTL-030; BUILD_SPEC RPS-3; supervisor ruling R-72).

Per member contract and contracting entity over the range:

- ``OPENING`` and ``CLOSING`` are the presented balances at the end of the period before the range
  and at the end of the range (``tie_outs.balances_at``);
- the path of S15-R-02 walks the flows of the control role in date order. The flows are the
  ``CONTRACT_LIABILITY`` subledger lines of the range, except the JET-06 netting kinds, and the
  billing that posts no line (R-72 (a)): under ``billing.posting = ERP`` an invoice or a credit
  memo is ingested, never posted, so the role holds no line of it. The billing of a period is the
  delta of the engine's stored node ``billed_unconditional_cum`` of the contract and entity
  (S10-R-08; ``tie_outs.billed_through``) less the ``BILLING`` and ``CREDIT_MEMO`` lines already
  on the role; where that is not zero and the role holds no such line in the period, the period's
  billing documents enter the path at their effective dates — the kept ``BILLING_RECORDED`` lines
  of S10-R-07 (``erev_engine.billing_identity``) and the ``CREDIT_MEMO_RECORDED`` events, without
  voided events and voided contracts. Nothing is plugged: a difference between the documents and
  the delta stays unexplained. On one date a document enters before the lines ([J]: a line carries
  the amount of its computation and is dated by it; the document's date is the invoice's);
- a credit settles the unbilled receivable, then the contract asset, and the rest enters the
  liability as a new layer; a debit consumes the layers first in first out (POL-126
  ``FIFO_WITHIN_CONTRACT``) and the rest is an asset. Each flow is shown under the line of its
  family (SCREENS_B RPT-03 "kind → line"; R-72 (c)): ``BILLINGS`` = billing less credit memos;
  the two revenue lines = revenue relief, the contracting side of an intercompany pair included,
  net of negative revenue — relief of the opening layer is ``REVENUE_FROM_OPENING``, of later
  layers ``REVENUE_FROM_PERIOD_BILLINGS``, and relief beyond the layers is revenue in excess of
  billing, shown on the contract asset row ``REVENUE_FROM_PERIOD_BILLINGS``; every other movement
  of the role (a deposit transfer, noncash consideration, financing interest, the refund
  liability and its release, the receivable contra) is ``RECLASSIFICATIONS``;
- the difference between the path and the presented closing of the unbilled receivable and the
  contract asset is ``RECLASSIFICATIONS`` between the two captions; a difference in their sum, and
  any liability difference, is ``OTHER`` (unexplained; REQ-RPT-006);
- ``FX_REMEASUREMENT`` is 0 in the transaction view. New runs classify authenticated
  period-end acquired opening balances as ``BUSINESS_COMBINATIONS``. Their original
  input/output identities and balance nodes are retained for reruns; older bindings
  keep their original interpretation.

The functional view reads dated engine balance targets and posted functional control flows.
Billing is valued from retained historical layer creation/settlement amounts and, in ENGINE
posting mode, must equal posted functional billing. Settlement FX is moved before its billing
flow with an equal offset to period-end FX on historical report bindings. New reports use
actual retained EVENT deltas instead of both synthetic timing movements. Event sequences keep
settlement before its invoice and relief before revenue. Layer identities and verified traces
are retained for reruns. Liability FX uses verified creation and remeasurement identities:
opening layers remain in the range-opening bucket, new billing layers keep their own keys,
and relief FX
precedes revenue while closing FX follows it. New close-pass TIME lines use their actual
retained target/prior/paid decomposition, with recursive historical line dependencies and
original layer creation dates bound into reruns. Asset sources bypass liability layers; mixed
control targets retain each source role. Historical passes without source evidence retain the
legacy path; command attribution without complete evidence refuses. Layer
totals must match posted period FX. Credit-memo reliefs use their original ordered
transaction portions and pinned spot rate, cumulatively rounded to the memo total.
Their billed amounts include this same spot conversion; the historical-to-spot
difference enters the specific liability layers immediately before the memo.
For a combined-member memo, an independently sourced bridge reconciles original
layer owners with the engine's member presentation. Endpoint carrying and memo
issuer/source transfers are bound as evidence, conserve the original group, and
are shown as RECLASSIFICATIONS rather than unexplained OTHER.

The reporting view translates monthly functional paths using the engine's S12-R-18 helper:
opening at the preceding closing rate, flows at each posting period's average rate, closing
at that period's closing rate. Monthly paths keep the original range's opening-layer identity.
TRANSLATION and ROUNDING are separate lines; rates and versions are retained, and locked
endpoints select rates at their frozen cutoff. GL and balance comparisons stay functional.
Unexplained functional OTHER remains a failure even if translated amounts round to zero.

Section 1 "Rollforward" gives one row per line code (``<line>:<ISO>`` when several currencies);
section 2 "By contract" one row per contract for ``balance_role``. Tie-outs:
``TO_ROLLFORWARD_BALANCES`` passes when every ``OTHER`` cell is 0 (opening plus activity equals
closing, S15-R-07); ``TO_BALANCES_EQ_ROLLFORWARD`` compares the contract balances at the range end
with the ``CLOSING`` line; ``TO_ROLLFORWARD_EQ_GL`` is ``NOT_APPLICABLE`` without a trial balance.

R-RC-1 (L6-3-Q-21): the ``CONTRACT_BALANCE_ROLLFORWARD`` reconciliation with
``unexplained_other_amount`` moves with CLO-16.

The two ends (ENGINE_SPEC_B S15-R-20 rev 1.168; ruling R-72 (b); item
RPT-ROLLFWD-LOCKED-CLOSING-1): an end of a period that is locked at the run's cutoff is the
lock's — the opening where the period before the range is, the closing where its last period is
(``reports.locked_ends``) —, so a range of locked months and the period after it foot after a
contract is activated late: its lines are movements of the period they are posted in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from erev_engine import billing_identity
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract_event, fx_layer_movement, subledger_line, subledger_posting
from erev_api.domain.close import pass_evidence
from erev_api.domain.reports import (
    functional_balances,
    locked_ends,
    reporting_rollforward,
    rollforward_gl,
    tie_outs,
)
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import (
    ROLLFORWARD_BALANCES,
    ZERO,
    BalanceRow,
    EntityRef,
    PeriodRef,
    TracedBalances,
    add,
)
from erev_api.enums import ContractEventType
from erev_api.explain import store as trace_store
from erev_api.registry.resolve import setting
from erev_api.uow import UnitOfWork

CODE: Final = "contract_balance_rollforward"
LIABILITY: Final = "contract_liability"
ASSET: Final = "contract_asset"
UNBILLED: Final = "unbilled_receivable"
LINES: Final = (
    "OPENING",
    "BILLINGS",
    "REVENUE_FROM_OPENING",
    "REVENUE_FROM_PERIOD_BILLINGS",
    "RECLASSIFICATIONS",
    "FX_REMEASUREMENT",
    "BUSINESS_COMBINATIONS",
    "OTHER",
    "CLOSING",
)
LABELS: Final[Mapping[str, str]] = {
    "OPENING": "Opening balance",
    "BILLINGS": "Billings",
    "REVENUE_FROM_OPENING": "Revenue recognized from the opening balance",
    "REVENUE_FROM_PERIOD_BILLINGS": "Revenue recognized from billings of the period",
    "RECLASSIFICATIONS": "Reclassifications",
    "FX_REMEASUREMENT": "FX remeasurement",
    "BUSINESS_COMBINATIONS": "Business combinations",
    "OTHER": "Other",
    "TRANSLATION": "Reporting currency translation",
    "ROUNDING": "Translation rounding",
    "CLOSING": "Closing balance",
}
BALANCE_ROLES: Final[Mapping[str, str]] = {
    "CONTRACT_LIABILITY": LIABILITY,
    "CONTRACT_ASSET": ASSET,
    "UNBILLED_RECEIVABLE": UNBILLED,
}
NETTING_KINDS: Final = frozenset({"NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"})
REVENUE_KIND: Final = "REVENUE_RECOGNITION"
LIABILITY_ROLE: Final = "CONTRACT_LIABILITY"
# The families of the flows of the role and the line each is shown under (SCREENS_B RPT-03
# "kind → line"; supervisor ruling R-72 (c)). A subledger line's family follows its entry kind
# (04 E-29; ENGINE_SPEC_B Table 14-A): JET-03 invoices and credit memos are billing; revenue
# relief and its reversal — the contracting side of an intercompany pair included (S12-R-03) —
# are revenue; every other movement of the role is a reclassification.
BILLING: Final = "BILLING"
REVENUE: Final = "REVENUE"
RECLASSIFICATION: Final = "RECLASSIFICATION"
FX: Final = "FX"
FAMILIES: Final[Mapping[str, str]] = {
    "BILLING": BILLING,
    "CREDIT_MEMO": BILLING,
    REVENUE_KIND: REVENUE,
    "INTERCOMPANY": REVENUE,
}
REVENUE_KINDS: Final = frozenset(kind for kind, family in FAMILIES.items() if family == REVENUE)
BILLING_KINDS: Final = frozenset(kind for kind, family in FAMILIES.items() if family == BILLING)
# The line of a family's movement, for the side that has no layer rule of its own.
FAMILY_LINES: Final[Mapping[str, str]] = {
    BILLING: "BILLINGS",
    REVENUE: "REVENUE_FROM_PERIOD_BILLINGS",
    RECLASSIFICATION: "RECLASSIFICATIONS",
    FX: "FX_REMEASUREMENT",
    "ACQUISITION": "BUSINESS_COMBINATIONS",
}
# A contract's billing stream (04 E-03): the documents and what voids them.
DOCUMENT_TYPES: Final = (
    ContractEventType.BILLING_RECORDED.value,
    ContractEventType.CREDIT_MEMO_RECORDED.value,
)
STREAM_TYPES: Final = (
    *DOCUMENT_TYPES,
    ContractEventType.EVENT_VOIDED.value,
    ContractEventType.CONTRACT_VOIDED.value,
)
FUNCTIONAL_ONLY: Final = (
    "The functional and reporting views show contracts in the entity's functional currency only."
)
type Lines = dict[str, dict[str, Decimal]]


@dataclass(frozen=True, slots=True)
class Flow:
    """One flow of the control role: signed amount (debit positive), whether it is revenue
    relief, and its family (``BILLING``, ``REVENUE``, ``RECLASSIFICATION``). Without a family the
    flow is read by its sign: a credit is billing, a debit revenue relief or another decrease."""

    amount: Decimal
    is_revenue: bool
    kind: str = ""
    layer_key: str | None = None
    liability_fx: tuple[tuple[str | None, Decimal], ...] = ()
    asset_fx: bool = False
    acquisition_balances: tuple[tuple[str, Decimal], ...] = ()
    # Explicit original signed changes; distinct from legacy positive carrying balances.
    acquisition_changes: tuple[tuple[str, Decimal], ...] = ()
    acquisition_includes_prior: bool = False


def family_of(flow: Flow) -> str:
    """The family a flow is shown under (``FAMILY_LINES``)."""
    if flow.kind:
        return flow.kind
    if flow.amount < 0:
        return BILLING
    return REVENUE if flow.is_revenue else RECLASSIFICATION


def line_flow(entry_kind: str, amount: Decimal) -> Flow:
    """The flow of a ``CONTRACT_LIABILITY`` subledger line of ``entry_kind`` (04 E-29)."""
    family = FAMILIES.get(entry_kind, RECLASSIFICATION)
    return Flow(amount, family == REVENUE, family)


def document_flow(signed_billing: Decimal) -> Flow:
    """The flow of a billing document that posts no line: an invoice (positive) credits the role,
    a credit memo (negative) debits it."""
    return Flow(-signed_billing, False, BILLING)


@dataclass(frozen=True, slots=True)
class ContractRollforward:
    contract_id: UUID
    external_id: str
    customer_name: str | None
    entity_id: UUID
    entity_code: str
    currency: str
    lines: Mapping[str, Mapping[str, Decimal]]
    period_lines: Mapping[UUID, Lines] = field(default_factory=dict)
    group_members: tuple[ContractRollforward, ...] = ()


def path(
    opening: Mapping[str, Decimal],
    flows: Sequence[Flow],
    closing: Mapping[str, Decimal],
    *,
    opening_relief: dict[int, Decimal] | None = None,
) -> Lines:
    """The S15-R-02 lines of one contract and entity (module docstring; ENGINE_SPEC_B EX-15-B)."""
    lines: Lines = {line: dict.fromkeys(ROLLFORWARD_BALANCES, ZERO) for line in LINES}
    for balance in ROLLFORWARD_BALANCES:
        lines["OPENING"][balance] = opening.get(balance, ZERO)
        lines["CLOSING"][balance] = closing.get(balance, ZERO)
    # A retained negative FX adjustment can restore an original opening source
    # whose carrying balance is zero. Keep its empty bucket; positive FX still
    # cannot overdraw it, and unknown named layers remain invalid.
    layers: list[list[Any]] = [["OPENING", max(ZERO, opening.get(LIABILITY, ZERO)), None]]
    asset = {UNBILLED: opening.get(UNBILLED, ZERO), ASSET: opening.get(ASSET, ZERO)}
    for flow_index, flow in enumerate(flows):
        family = family_of(flow)
        label = FAMILY_LINES[family]
        if family == "ACQUISITION":
            if flow.acquisition_changes:
                from ..acquisition_path import apply

                apply(flow, layers, asset, lines[label])
                continue
            amounts = dict(flow.acquisition_balances)
            if set(amounts) != set(ROLLFORWARD_BALANCES) or any(v < 0 for v in amounts.values()):
                raise tie_outs.invalid("currency_view", "Invalid original acquisition balances.")
            for role, amount in amounts.items():
                lines[label][role] += amount
                if role == LIABILITY:
                    layers.append(["NEW", amount, flow.layer_key])
                else:
                    asset[role] += amount
            continue
        if family == FX:
            if flow.asset_fx:
                if flow.liability_fx:
                    raise tie_outs.invalid("currency_view", "FX flow has conflicting source roles.")
                role = UNBILLED if asset[UNBILLED] else ASSET
                asset[role] += flow.amount
                lines[label][role] += flow.amount
                continue
            if flow.liability_fx:
                if sum((amount for _, amount in flow.liability_fx), ZERO) != flow.amount:
                    raise tie_outs.invalid(
                        "currency_view", "Layer FX differs from its posted total."
                    )
                for key, amount in flow.liability_fx:
                    matches = [
                        layer
                        for layer in layers
                        if layer[2] == key
                        and (layer[0] == "OPENING" if key is None else layer[0] == "NEW")
                    ]
                    if len(matches) != 1 or matches[0][1] < amount:
                        raise tie_outs.invalid(
                            "currency_view", "FX has no matching open liability layer."
                        )
                    matches[0][1] -= amount
                    lines[label][LIABILITY] -= amount
                continue
            live = [layer for layer in layers if layer[1] > 0]
            if live:
                if len(live) > 1:
                    raise tie_outs.invalid(
                        "currency_view",
                        "FX on multiple liability layers requires layer-specific attribution.",
                    )
                if live[0][1] < flow.amount:
                    raise tie_outs.invalid(
                        "currency_view", "FX movement exceeds the liability carrying amount."
                    )
                live[0][1] -= flow.amount
                lines[label][LIABILITY] -= flow.amount
                continue
            role = UNBILLED if asset[UNBILLED] else ASSET
            asset[role] += flow.amount
            lines[label][role] += flow.amount
            continue
        if flow.amount < 0:
            left = -flow.amount
            for role in (UNBILLED, ASSET):
                take = min(asset[role], left)
                asset[role] -= take
                left -= take
                lines[label][role] -= take
            if left > 0:
                layers.append(["NEW", left, flow.layer_key])
                lines[label][LIABILITY] += left
            continue
        need = flow.amount
        for layer in layers:
            if need <= 0:
                break
            take = min(layer[1], need)
            if take <= 0:
                continue
            layer[1] -= take
            need -= take
            relieved = family == REVENUE and layer[0] == "OPENING"
            if relieved and opening_relief is not None:
                opening_relief[flow_index] = opening_relief.get(flow_index, ZERO) + take
            lines["REVENUE_FROM_OPENING" if relieved else label][LIABILITY] -= take
        if need > 0:
            asset[ASSET] += need
            lines[label][ASSET] += need
    computed = sum((Decimal(layer[1]) for layer in layers), ZERO)
    lines["OTHER"][LIABILITY] = closing.get(LIABILITY, ZERO) - computed
    unexplained = (closing.get(UNBILLED, ZERO) + closing.get(ASSET, ZERO)) - (
        asset[UNBILLED] + asset[ASSET]
    )
    lines["RECLASSIFICATIONS"][UNBILLED] += closing.get(UNBILLED, ZERO) - asset[UNBILLED]
    lines["RECLASSIFICATIONS"][ASSET] += closing.get(ASSET, ZERO) - asset[ASSET] - unexplained
    lines["OTHER"][ASSET] = unexplained
    return lines


def ranges(
    session: Session, params: ReportParams
) -> tuple[tuple[EntityRef, ...], dict[UUID, tuple[PeriodRef, ...]], dict[UUID, PeriodRef | None]]:
    """The run's entities, each entity's range and the period before its range."""
    found = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found, params=params)
    periods: dict[UUID, tuple[PeriodRef, ...]] = {}
    before: dict[UUID, PeriodRef | None] = {}
    for item in found:
        calendar = found_calendars[item.id]
        periods[item.id] = tie_outs.range_of(params, calendar, item)
        before[item.id] = calendar.before(periods[item.id][0]) if periods[item.id] else None
    return found, periods, before


def rollforwards(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    before: Mapping[UUID, PeriodRef | None],
    known_at: datetime,
    cutoff: datetime,
    params: ReportParams,
    contract_id: UUID | None = None,
    documents: bool = True,
    functional: bool = False,
    period_detail: bool = False,
    locked: tie_outs.LockedEnds | None = None,
    uow: UnitOfWork | None = None,
) -> tuple[ContractRollforward, ...]:
    """The rollforward of every member contract and entity with a balance at either end.
    ``documents`` False leaves the billing that posts no line out of the path: a caller that reads
    the ``CLOSING`` line alone (``contract_balances``, CTL-030) needs no flow of it. ``locked``
    are the build's locked period ends (S15-R-20 rev 1.168): both ends are read through them."""
    closing_at: dict[UUID, PeriodRef | None] = {
        entity_id: (items[-1] if items else None) for entity_id, items in periods.items()
    }
    traces: dict[UUID, TracedBalances] = {}
    opening_rows = tie_outs.balances_at(
        session,
        uow=uow,
        entity_ids=entity_ids,
        book_code=book_code,
        period_keys=before,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        traces=traces,
        locked_ends=locked,
    )
    closing_rows = tie_outs.balances_at(
        session,
        uow=uow,
        entity_ids=entity_ids,
        book_code=book_code,
        period_keys=closing_at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        traces=traces,
        locked_ends=locked,
    )
    transaction_ends = {
        (row.contract_id, row.entity_id): row for row in (*opening_rows, *closing_rows)
    }
    acquisitions: dict[tuple[UUID, UUID], list[Entry]] = {}
    native_groups: dict[UUID, Any] = {}
    if documents and uow is not None:
        from ..acquisition_flows import read as acquisition_flows

        acquisitions = acquisition_flows(
            uow,
            params,
            transaction_ends,
            periods,
            book_code,
            functional=functional,
            groups=native_groups,
        )
    if documents and uow is not None:
        from ..split_groups import read as split_groups

        split_groups(
            uow,
            params,
            transaction_ends,
            periods,
            book_code,
            functional=functional,
            groups=native_groups,
        )
    group_keys = frozenset(key for group in native_groups.values() for key in group.keys)
    transaction_ends = {key: row for key, row in transaction_ends.items() if key not in group_keys}
    if functional:
        entities = tie_outs.entities(session, entity_ids, params=params)
        opening_rows = functional_balances.read(
            session,
            params,
            opening_rows,
            entities=entities,
            periods=before,
            book_code=book_code,
            locked=locked,
            measures=ROLLFORWARD_BALANCES,
        )
        closing_rows = functional_balances.read(
            session,
            params,
            closing_rows,
            entities=entities,
            periods=closing_at,
            book_code=book_code,
            locked=locked,
            measures=ROLLFORWARD_BALANCES,
        )
    monthly: dict[tuple[UUID, UUID], dict[tuple[UUID, UUID], BalanceRow]] = {}
    if period_detail:
        # Read each intermediate endpoint once. Prefix paths retain the original range's
        # opening-layer identity, so later months do not relabel new billings as opening.
        for entity_id, selected_periods in periods.items():
            for period in selected_periods:
                if period == selected_periods[-1]:
                    rows = tuple(row for row in closing_rows if row.entity_id == entity_id)
                else:
                    rows = tie_outs.balances_at(
                        session,
                        uow=uow,
                        entity_ids=(entity_id,),
                        book_code=book_code,
                        period_keys={entity_id: period},
                        cutoff=cutoff,
                        params=params,
                        contract_id=contract_id,
                        locked_ends=locked,
                    )
                    if functional:
                        rows = functional_balances.read(
                            session,
                            params,
                            rows,
                            entities=entities,
                            periods={entity_id: period},
                            book_code=book_code,
                            locked=locked,
                            measures=ROLLFORWARD_BALANCES,
                        )
                monthly[(entity_id, period.id)] = {
                    (row.contract_id, row.entity_id): row for row in rows
                }
    ends: dict[tuple[UUID, UUID], list[BalanceRow | None]] = {}
    for row in opening_rows:
        ends.setdefault((row.contract_id, row.entity_id), [None, None])[0] = row
    for row in closing_rows:
        ends.setdefault((row.contract_id, row.entity_id), [None, None])[1] = row
    posted = _lines(
        session,
        entity_ids,
        book_code,
        periods,
        known_at,
        contract_id,
        params=params,
        functional=functional,
    )
    posted = {key: entries for key, entries in posted.items() if key not in group_keys}
    member_transfers: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    opening_relief: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    liability_relief: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    asset_transfers: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    billing_assets: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    booked_billing: dict[tuple[UUID, UUID], list[Entry]] = {}
    if functional and documents:
        # Read billing at its source date in either posting mode. ENGINE totals
        # must match their posted functional amounts before substituting the path.
        for key, entries in posted.items():
            booked_billing[key] = [entry for entry in entries if entry.entry_kind in BILLING_KINDS]
            posted[key] = [entry for entry in entries if entry.entry_kind not in BILLING_KINDS]
    unposted: dict[tuple[UUID, UUID], list[Entry]] = {}
    if documents:
        described_rows = transaction_ends
        unposted = _billing(
            session,
            rows={key: row for key, row in described_rows.items() if row is not None},
            posted=posted,
            periods=periods,
            before=before,
            traces=traces,
            cutoff=cutoff,
            params=params,
            locked=locked,
        )
    if functional and documents:
        unposted = _functional_documents(
            session,
            unposted,
            transaction_ends,
            params,
            posted,
            periods,
            member_transfers=member_transfers,
            asset_transfers=asset_transfers,
            billing_assets=billing_assets,
        )
        for key, entries in booked_billing.items():
            for period_id in {entry.period_id for entry in entries}:
                booked = sum(
                    (entry.flow.amount for entry in entries if entry.period_id == period_id), ZERO
                )
                sourced = sum(
                    (
                        entry.flow.amount
                        for entry in unposted.get(key, ())
                        if entry.period_id == period_id and entry.flow.kind == BILLING
                    ),
                    ZERO,
                )
                if booked != sourced:
                    raise tie_outs.invalid(
                        "currency_view",
                        "Dated billing layers differ from posted functional billing.",
                    )
    if functional and documents:
        if uow is not None and params.requester is not None:
            uow = UnitOfWork(
                ctx=params.requester,
                session=uow.session,
                clock=uow.clock,
                keyring=uow.keyring,
                files=uow.files,
            )
        handled = (
            _retained_time_fx(uow, posted, transaction_ends, periods, params) if uow else set()
        )
        event_sources = False
        if uow and (params.binding is None or "event_posted_fx_v1" in params.binding.evidence):
            _retained_event_fx(uow, posted, unposted, transaction_ends, periods, params)
            event_sources = True
        _liability_fx(
            session,
            posted,
            transaction_ends,
            periods,
            params,
            handled=handled,
            event_sources=event_sources,
        )
    if (
        functional
        and documents
        and (
            params.binding is None
            or any(
                key in params.binding.evidence
                for key in (
                    "combined_liability_bridge_v3",
                    "combined_liability_bridge_v4",
                    "combined_liability_bridge_v5",
                    "combined_liability_bridge_v6",
                )
            )
        )
    ):
        from ..revenue_layer_transfers import read as revenue_transfers

        revenue_sources, opening_relief, liability_relief, revenue_asset_transfers = (
            revenue_transfers(session, params, transaction_ends, periods, posted, uow=uow)
        )
        for transfer_key, amount in revenue_asset_transfers.items():
            asset_transfers[transfer_key] = asset_transfers.get(transfer_key, ZERO) + amount
        for transfer_key, amount in revenue_sources.items():
            member_transfers[transfer_key] = member_transfers.get(transfer_key, ZERO) + amount
    found: list[ContractRollforward] = []
    for (contract_key, entity_id), (opening, closing) in ends.items():
        if (contract_key, entity_id) in group_keys:
            continue
        described = closing if closing is not None else opening
        assert described is not None
        key = (contract_key, entity_id)
        entries = acquisition_entries(
            [*posted.get(key, ()), *unposted.get(key, ())], acquisitions.get(key, ())
        )
        lines = path(
            _values(opening),
            [entry.flow for entry in entries] if documents else [],
            _values(closing),
        )
        found.append(
            ContractRollforward(
                contract_id=contract_key,
                external_id=described.external_id,
                customer_name=described.customer_name,
                entity_id=entity_id,
                entity_code=described.entity_code,
                currency=described.currency,
                lines=lines,
                period_lines=(
                    period_paths(
                        _values(opening),
                        entries,
                        [
                            (period, _values(monthly[(entity_id, period.id)].get(key)))
                            for period in periods[entity_id]
                        ],
                    )
                    if period_detail
                    else {}
                ),
            )
        )
    if (
        functional
        and documents
        and (
            params.binding is None
            or any(
                key in params.binding.evidence
                for key in (
                    "combined_liability_bridge_v1",
                    "combined_liability_bridge_v2",
                    "combined_liability_bridge_v3",
                    "combined_liability_bridge_v4",
                    "combined_liability_bridge_v5",
                    "combined_liability_bridge_v6",
                )
            )
        )
    ):
        from ..combined_liability_bridge import apply

        found = list(
            apply(
                session,
                params,
                found,
                opening=[r for r in opening_rows if (r.contract_id, r.entity_id) not in group_keys],
                closing=[r for r in closing_rows if (r.contract_id, r.entity_id) not in group_keys],
                before=before,
                periods=periods,
                monthly=monthly,
                transfers=member_transfers,
                opening_relief=opening_relief,
                liability_relief=liability_relief,
                foreign_members=frozenset(
                    (row.contract_id, row.entity_id)
                    for row in (*opening_rows, *closing_rows)
                    if (row.contract_id, row.entity_id) in transaction_ends
                    and transaction_ends[(row.contract_id, row.entity_id)].currency != row.currency
                ),
            )
        )
    if (
        functional
        and documents
        and (
            asset_transfers
            or (billing_assets and params.binding is None)
            or (
                params.binding is not None
                and any(
                    key in params.binding.evidence
                    for key in (
                        "combined_asset_bridge_v1",
                        "combined_asset_bridge_v2",
                        "combined_asset_bridge_v3",
                    )
                )
            )
        )
    ):
        from ..combined_asset_bridge import apply as asset_bridge

        found = list(
            asset_bridge(
                session,
                params,
                found,
                opening=[r for r in opening_rows if (r.contract_id, r.entity_id) not in group_keys],
                closing=[r for r in closing_rows if (r.contract_id, r.entity_id) not in group_keys],
                before=before,
                periods=periods,
                monthly=monthly,
                transfers=asset_transfers,
                billing_assets=billing_assets,
            )
        )
    if native_groups:
        from ..acquisition_groups import project as group_project

        found.extend(
            group_project(group, opening=opening_rows, closing=closing_rows, monthly=monthly)
            for group in native_groups.values()
        )
    return tuple(sorted(found, key=lambda item: (item.external_id, item.entity_code)))


def period_paths(
    opening: Mapping[str, Decimal],
    entries: Sequence[Entry],
    endpoints: Sequence[tuple[PeriodRef, Mapping[str, Decimal]]],
) -> dict[UUID, Lines]:
    """Monthly deltas of the cumulative path, preserving range-opening provenance."""
    wanted = {period.id for period, _ in endpoints}
    if any(entry.period_id not in wanted for entry in entries):
        raise tie_outs.invalid("currency_view", "A reporting flow lacks its posting period.")
    previous = path(opening, (), opening)
    admitted: set[UUID] = set()
    output = {}
    for period, closing in endpoints:
        admitted.add(period.id)
        current = path(opening, [e.flow for e in entries if e.period_id in admitted], closing)
        output[period.id] = {
            line: {
                balance: (
                    previous["CLOSING"][balance]
                    if line == "OPENING"
                    else current[line][balance]
                    if line == "CLOSING"
                    else current[line][balance] - previous[line][balance]
                )
                for balance in ROLLFORWARD_BALANCES
            }
            for line in LINES
        }
        previous = current
    return output


def _values(row: BalanceRow | None) -> dict[str, Decimal]:
    if row is None:
        return dict.fromkeys(ROLLFORWARD_BALANCES, ZERO)
    return {balance: row.value(balance) for balance in ROLLFORWARD_BALANCES}


# On one date a billing document enters the path before the subledger lines (module docstring).
DOCUMENT_RANK: Final = 0
LINE_RANK: Final = 1


@dataclass(frozen=True, slots=True)
class Entry:
    """A flow in its place on the path: ``order`` = (effective date, rank, the source's own
    order); ``period_id`` and ``entry_kind`` are a subledger line's (None for a document)."""

    order: tuple[Any, ...]
    flow: Flow
    period_id: UUID | None = None
    entry_kind: str | None = None
    line_id: UUID | None = None
    posting_kind: str | None = None
    subject_key: str | None = None


def acquisition_entries(activity: Sequence[Entry], acquisitions: Sequence[Entry]) -> list[Entry]:
    """Keep original sources without counting cutover-covered activity a second time."""
    covered = [entry.order[0] for entry in acquisitions if entry.flow.acquisition_includes_prior]
    selected = list(activity)
    if covered:
        cutover = max(covered)
        selected = [entry for entry in selected if entry.order[0] > cutover]
    return sorted([*selected, *acquisitions], key=lambda entry: entry.order)


def _lines(
    session: Session,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    known_at: datetime,
    contract_id: UUID | None,
    *,
    params: ReportParams,
    functional: bool = False,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    """The subledger lines of the role over the range, per contract and entity. S15-R-24 /
    frps3c-2: the line ids consumed are recorded as ``members.subledger_line`` on a live build; a
    bound run reads exactly those ids WITHIN today's scope predicates (tenant / book / entity /
    period stay; the ids restrict, never replace) and refuses by name a bound id the read did not
    return (D4)."""
    period_ids = sorted({item.id for items in periods.values() for item in items}, key=str)
    if not entity_ids or not period_ids:
        # R1: an empty range is a CAPTURED empty membership (recorded), never an absent kind
        tie_outs.require_members(params, "subledger_line", ())
        tie_outs.record_members(params, "subledger_line", ())
        return {}
    statement = (
        select(
            subledger_line.c.id,
            subledger_line.c.contract_id,
            subledger_line.c.entity_id,
            subledger_line.c.period_id,
            subledger_line.c.effective_date,
            subledger_line.c.period_end_date,
            subledger_line.c.recorded_at,
            subledger_line.c.entry_no,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
            subledger_line.c.entry_kind,
            subledger_line.c.subject_key,
            subledger_posting.c.posting_kind,
        )
        .select_from(
            subledger_line.join(
                subledger_posting, subledger_posting.c.id == subledger_line.c.subledger_posting_id
            )
        )
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.account_role == LIABILITY_ROLE,
            subledger_line.c.entity_id.in_(list(entity_ids)),
            subledger_line.c.period_id.in_(period_ids),
            tie_outs.line_recorded_by(params, known_at),
            subledger_line.c.entry_kind.not_in(sorted(NETTING_KINDS)),
            *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
        )
    )
    if contract_id is not None:
        statement = statement.where(subledger_line.c.contract_id == contract_id)
    statement = statement.order_by(
        subledger_line.c.effective_date,
        subledger_line.c.period_end_date,
        subledger_line.c.recorded_at,
        subledger_line.c.entry_no,
        subledger_line.c.id,
    )
    found: dict[tuple[UUID, UUID], list[Entry]] = {}
    consumed: list[UUID] = []
    for row in session.execute(statement).mappings():
        if row["contract_id"] is None:
            continue
        consumed.append(UUID(str(row["id"])))
        key = (UUID(str(row["contract_id"])), UUID(str(row["entity_id"])))
        entry_kind = str(getattr(row["entry_kind"], "value", row["entry_kind"]))
        found.setdefault(key, []).append(
            Entry(
                order=(
                    row["effective_date"],
                    LINE_RANK,
                    row["period_end_date"],
                    row["recorded_at"],
                    int(row["entry_no"]),
                    str(row["id"]),
                ),
                flow=(
                    Flow(Decimal(row["amount_functional"]), False, FX)
                    if functional and entry_kind == "FX_REMEASUREMENT"
                    else line_flow(
                        entry_kind,
                        Decimal(row["amount_functional" if functional else "amount_txn"]),
                    )
                ),
                period_id=UUID(str(row["period_id"])),
                entry_kind=entry_kind,
                line_id=UUID(str(row["id"])),
                posting_kind=str(row["posting_kind"]),
                subject_key=row["subject_key"],
            )
        )
    tie_outs.require_members(params, "subledger_line", consumed)
    tie_outs.record_members(params, "subledger_line", consumed)
    return found


def _retained_time_fx(
    uow: UnitOfWork,
    posted: dict[tuple[UUID, UUID], list[Entry]],
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    params: ReportParams,
) -> set[tuple[UUID, UUID, UUID]]:
    """Place actual close-pass TIME deltas on their retained member layers."""
    mixed = params.binding is None or "control_posted_fx_v2" in params.binding.evidence
    evidence_key = "control_posted_fx_v2" if mixed else "liability_posted_fx_v1"
    if params.binding is not None and evidence_key not in params.binding.evidence:
        return set()  # Preserve the explicitly retained historical report path.
    owners = {row.external_id: row.contract_id for row in rows.values()}
    handled: set[tuple[UUID, UUID, UUID]] = set()
    facts: dict[str, Any] = {}
    additions: dict[tuple[UUID, UUID], list[Entry]] = {}
    for key, entries in list(posted.items()):
        for entry in tuple(entries):
            if entry.posting_kind != "FX_REMEASUREMENT" or entry.line_id is None:
                continue
            document = pass_evidence.read_for_line(uow, entry.line_id)
            if document is None:
                continue
            # Preserve the earlier source-binding contract on historical reruns.
            if not mixed and not any(
                item["columns"]["movement_kind"] == "LIABILITY_LAYER_REMEASURED"
                for item in document["book_output"]["fx_layer_movements"]
            ):
                continue
            try:
                result = pass_evidence.liability_attribution(uow, entry.line_id, owners=owners)
            except ValueError as error:
                raise tie_outs.invalid("currency_view", str(error)) from error
            if result is None or result.amount != entry.flow.amount:
                raise tie_outs.invalid(
                    "currency_view", "Retained FX delta differs from the posted flow."
                )
            period = next(item for item in periods[key[1]] if item.id == entry.period_id)
            beginning = periods[key[1]][0].start
            groups: dict[tuple[UUID, date, str], dict[str | None, Decimal]] = {}
            for movement in result.movements:
                if not movement.closing or movement.created_on is None:
                    raise tie_outs.invalid(
                        "currency_view", "Close TIME attribution lacks dated layer evidence."
                    )
                owner_key = (movement.contract_id, key[1])
                if owner_key not in rows:
                    raise tie_outs.invalid(
                        "currency_view", "FX source owner is outside the report population."
                    )
                day = max(period.start, min(period.end, movement.effective_date))
                layer = None if movement.created_on < beginning else movement.layer_key
                parts = groups.setdefault((movement.contract_id, day, movement.balance_role), {})
                parts[layer] = parts.get(layer, ZERO) + movement.amount
                handled.add((*owner_key, period.id))
            handled.add((*key, period.id))
            for (owner, day, role), parts in groups.items():
                additions.setdefault((owner, key[1]), []).append(
                    Entry(
                        order=(day, LINE_RANK, period.end, params.known_at, 0, str(entry.line_id)),
                        flow=Flow(
                            sum(parts.values(), ZERO),
                            False,
                            FX,
                            liability_fx=tuple(parts.items()) if role == LIABILITY_ROLE else (),
                            asset_fx=role == "CONTRACT_ASSET",
                        ),
                        period_id=period.id,
                        entry_kind="FX_REMEASUREMENT",
                    )
                )
            entries.remove(entry)
            facts[str(entry.line_id)] = {
                "delta": result.node_id,
                "paid_line_ids": [str(identity) for identity in result.paid_line_ids],
                "evidence": [[str(identity), digest] for identity, digest in result.evidence],
            }
    for key, entries in additions.items():
        posted.setdefault(key, []).extend(_net_time_fx(entries))
    if params.binding is not None and params.binding.evidence[evidence_key] != facts:
        raise tie_outs.invalid(
            "currency_view", "Retained FX source attribution differs from the report binding."
        )
    tie_outs.record_evidence(params, evidence_key, facts)
    return handled


def _retained_event_fx(
    uow: UnitOfWork,
    posted: dict[tuple[UUID, UUID], list[Entry]],
    documents: dict[tuple[UUID, UUID], list[Entry]],
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    params: ReportParams,
) -> None:
    """Replace synthetic settlement timing with signed, actually posted EVENT sources.

    Net original and correcting postings by source before walking the path. An
    invoice's retained event sequence places its FX immediately before billing;
    relief FX precedes revenue. Late carries stay inside their posting period.
    """
    from erev_api.domain.journals.subledger import POSTING_CLASSES

    owners = {row.external_id: row.contract_id for row in rows.values()}
    facts: dict[str, Any] = {}
    grouped: dict[tuple[Any, ...], dict[str | None, Decimal]] = {}
    for key, entries in posted.items():
        for entry in tuple(entries):
            if (
                entry.entry_kind != "FX_REMEASUREMENT"
                or entry.line_id is None
                or POSTING_CLASSES.get(entry.posting_kind or "") != "EVENT"
            ):
                continue
            try:
                result = pass_evidence.liability_attribution(uow, entry.line_id, owners=owners)
            except ValueError as error:
                raise tie_outs.invalid("currency_view", str(error)) from error
            if result is None or result.amount != entry.flow.amount:
                raise tie_outs.invalid(
                    "currency_view", "Posted EVENT FX lacks matching source evidence."
                )
            period = next(item for item in periods[key[1]] if item.id == entry.period_id)
            beginning = periods[key[1]][0].start
            for movement in result.movements:
                owner_key = (movement.contract_id, key[1])
                if movement.closing or movement.created_on is None or owner_key not in rows:
                    raise tie_outs.invalid(
                        "currency_view", "EVENT FX lacks dated authorized sources."
                    )
                day = max(period.start, min(period.end, movement.effective_date))
                order: tuple[Any, ...]
                if movement.event_type in DOCUMENT_TYPES and movement.record_seq is not None:
                    order = (day, DOCUMENT_RANK, movement.record_seq, "", 0)
                else:
                    order = (
                        day,
                        LINE_RANK,
                        period.end,
                        datetime.min.replace(tzinfo=params.known_at.tzinfo),
                        0,
                        movement.source_key or "event-fx",
                    )
                group = (*owner_key, period.id, order, movement.balance_role)
                parts = grouped.setdefault(group, {})
                layer = None if movement.created_on < beginning else movement.layer_key
                parts[layer] = parts.get(layer, ZERO) + movement.amount
            entries.remove(entry)
            facts[str(entry.line_id)] = {
                "delta": result.node_id,
                "paid_line_ids": [str(identity) for identity in result.paid_line_ids],
                "evidence": [[str(identity), digest] for identity, digest in result.evidence],
            }
    # These are presentation-only movements from the old path, not journal lines.
    # Actual EVENT sources above replace both sides of that timing relocation.
    for entries in posted.values():
        entries[:] = [entry for entry in entries if entry.order[-1] != "settlement-timing"]
    for entries in documents.values():
        entries[:] = [entry for entry in entries if entry.flow.kind != FX]
    for (owner, entity, period_id, order, role), parts in grouped.items():
        parts = {layer: amount for layer, amount in parts.items() if amount}
        if not parts:
            continue
        posted.setdefault((owner, entity), []).append(
            Entry(
                order=order,
                flow=Flow(
                    sum(parts.values(), ZERO),
                    False,
                    FX,
                    liability_fx=tuple(parts.items()) if role == LIABILITY_ROLE else (),
                    asset_fx=role == "CONTRACT_ASSET",
                ),
                period_id=period_id,
                entry_kind="FX_REMEASUREMENT",
            )
        )
    if params.binding is not None and params.binding.evidence["event_posted_fx_v1"] != facts:
        raise tie_outs.invalid("currency_view", "EVENT FX sources differ from the report binding.")
    tie_outs.record_evidence(params, "event_posted_fx_v1", facts)


def _net_time_fx(entries: Sequence[Entry]) -> tuple[Entry, ...]:
    """Apply same-day close adjustments together, preserving source role/layer.

    A later close may reverse all of an earlier remeasurement. Intermediate
    UUID ordering must not overdraw a layer that is settled in the final path.
    """
    groups: dict[tuple[UUID | None, date, bool], list[Entry]] = {}
    for entry in entries:
        groups.setdefault((entry.period_id, entry.order[0], entry.flow.asset_fx), []).append(entry)
    result = []
    for (_, _, asset), items in groups.items():
        parts: dict[str | None, Decimal] = {}
        for item in items:
            for key, amount in item.flow.liability_fx:
                parts[key] = parts.get(key, ZERO) + amount
        amount = sum((item.flow.amount for item in items), ZERO)
        parts = {key: value for key, value in parts.items() if value}
        if amount or parts:
            result.append(
                replace(
                    min(items, key=lambda item: item.order),
                    flow=Flow(amount, False, FX, liability_fx=tuple(parts.items()), asset_fx=asset),
                )
            )
    return tuple(result)


def _liability_fx(
    session: Session,
    posted: dict[tuple[UUID, UUID], list[Entry]],
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    params: ReportParams,
    *,
    handled: set[tuple[UUID, UUID, UUID]] | None = None,
    event_sources: bool = False,
) -> None:
    """Attach verified layer remeasurement to its posted control movement.

    Opening layers share the range-opening bucket. New layers retain their creation
    identity, so an FX change cannot change which billing later revenue relieves.
    Settlement FX is already placed at its billing event by _functional_documents.
    """
    consumed: list[UUID] = []
    for key, entries in posted.items():
        row = rows.get(key)
        if row is None or not periods[row.entity_id]:
            continue
        selected = tuple(
            session.execute(
                select(fx_layer_movement).where(
                    fx_layer_movement.c.contract_version_id == row.version_id,
                    fx_layer_movement.c.contract_id == row.contract_id,
                    fx_layer_movement.c.entity_id == row.entity_id,
                    fx_layer_movement.c.balance_role == LIABILITY_ROLE,
                    fx_layer_movement.c.movement_kind.in_(
                        ("LIABILITY_LAYER_CREATED", "LIABILITY_LAYER_REMEASURED")
                    ),
                )
            ).mappings()
        )
        billing_events = set(
            session.execute(
                select(contract_event.c.id).where(
                    contract_event.c.contract_id == row.contract_id,
                    contract_event.c.event_type.in_(DOCUMENT_TYPES),
                )
            ).scalars()
        )
        relevant = [
            item
            for item in selected
            if item["movement_kind"] == "LIABILITY_LAYER_REMEASURED"
            and item["source_event_id"] not in billing_events
        ]
        if not relevant:
            continue
        trace = trace_store.load_trace(session, row.version_id)
        if trace is None:
            raise tie_outs.invalid("currency_view", "Liability FX trace is unavailable.")
        nodes = {node.id: node for node in trace.nodes}
        currency = tie_outs.entities(session, (row.entity_id,), params=params)[
            0
        ].functional_currency
        created = {
            str(item["layer_key"]): item
            for item in selected
            if item["movement_kind"] == "LIABILITY_LAYER_CREATED"
        }
        beginning = periods[row.entity_id][0].start
        for period in periods[row.entity_id]:
            movements = [
                item
                for item in relevant
                if period.start <= item["effective_date"] <= period.end
                and not (
                    handled
                    and (*key, period.id) in handled
                    and nodes[str(item["trace_node_id"])].formula_id == "fx.remeasure.closing.v1"
                )
            ]
            if event_sources:
                movements = [
                    item
                    for item in movements
                    if nodes[str(item["trace_node_id"])].formula_id == "fx.remeasure.closing.v1"
                ]
            if not movements:
                continue
            fx_entries = [
                entry
                for entry in entries
                if entry.period_id == period.id
                and entry.flow.kind == FX
                and not entry.flow.liability_fx
                and not entry.flow.asset_fx
            ]
            amount = sum((entry.flow.amount for entry in fx_entries), ZERO)
            if -sum((Decimal(item["amount_functional"]) for item in movements), ZERO) != amount:
                raise tie_outs.invalid(
                    "currency_view", "Liability layer FX differs from posted period FX."
                )
            groups: dict[tuple[date, bool], dict[str | None, Decimal]] = {}
            for item in movements:
                creation = created.get(str(item["layer_key"]))
                if creation is None:
                    raise tie_outs.invalid(
                        "currency_view", "Liability FX layer has no creation source."
                    )
                for source in (creation, item):
                    node = nodes.get(str(source["trace_node_id"]))
                    if (
                        node is None
                        or node.currency != str(source["functional_currency"]).strip()
                        or Decimal(node.value) != Decimal(source["amount_functional"])
                        or str(source["txn_currency"]).strip() != row.currency
                        or str(source["functional_currency"]).strip() != currency
                    ):
                        raise tie_outs.invalid(
                            "currency_view", "Liability FX evidence differs from its trace."
                        )
                    consumed.append(UUID(str(source["id"])))
                identity = (
                    None if creation["effective_date"] < beginning else str(item["layer_key"])
                )
                closing = nodes[str(item["trace_node_id"])].formula_id == "fx.remeasure.closing.v1"
                parts = groups.setdefault((item["effective_date"], closing), {})
                parts[identity] = parts.get(identity, ZERO) - Decimal(item["amount_functional"])
            entries[:] = [entry for entry in entries if entry not in fx_entries]
            for (day, closing), parts in sorted(groups.items()):
                # Relief remeasurement precedes that day's revenue; closing FX follows it.
                recorded = (
                    params.known_at
                    if closing
                    else datetime.min.replace(tzinfo=params.known_at.tzinfo)
                )
                entries.append(
                    Entry(
                        order=(day, LINE_RANK, period.end, recorded, 0, "liability-layer-fx"),
                        flow=Flow(
                            sum(parts.values(), ZERO), False, FX, liability_fx=tuple(parts.items())
                        ),
                        period_id=period.id,
                        entry_kind="FX_REMEASUREMENT",
                    )
                )
    tie_outs.require_members(params, "liability_fx_layer", consumed)
    tie_outs.record_members(params, "liability_fx_layer", consumed)


def _functional_documents(
    session: Session,
    entries: Mapping[tuple[UUID, UUID], list[Entry]],
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    params: ReportParams,
    posted: dict[tuple[UUID, UUID], list[Entry]],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    *,
    member_transfers: dict[tuple[UUID, UUID, UUID], Decimal],
    asset_transfers: dict[tuple[UUID, UUID, UUID], Decimal],
    billing_assets: dict[tuple[UUID, UUID, UUID], Decimal],
) -> dict[tuple[UUID, UUID], list[Entry]]:
    """ERP billing takes its actual historical layer carrying, never today's rate."""
    asset_sources = params.binding is None or "billing_asset_sources_v1" in params.binding.evidence
    result: dict[tuple[UUID, UUID], list[Entry]] = {}
    consumed: list[UUID] = []
    settlements: dict[tuple[UUID, UUID, UUID], Decimal] = {}
    for key, items in entries.items():
        row = rows[key]
        currency = tie_outs.entities(session, (row.entity_id,), params=params)[
            0
        ].functional_currency
        if row.currency == currency:
            result[key] = list(items)
            continue
        trace = trace_store.load_trace(session, row.version_id)
        if trace is None:
            raise tie_outs.invalid("currency_view", "Functional billing trace is unavailable.")
        nodes = {node.id: node for node in trace.nodes}
        translated = []
        for entry in items:
            event_id = UUID(str(entry.order[-1]))
            found = (
                session.execute(
                    select(fx_layer_movement).where(
                        fx_layer_movement.c.contract_version_id == row.version_id,
                        fx_layer_movement.c.contract_id.in_(
                            [
                                owner.contract_id
                                for owner in rows.values()
                                if owner.version_id == row.version_id
                                and owner.entity_id == row.entity_id
                            ]
                        ),
                        fx_layer_movement.c.entity_id == row.entity_id,
                        fx_layer_movement.c.source_event_id == event_id,
                        fx_layer_movement.c.balance_role.in_(
                            ("CONTRACT_LIABILITY", "CONTRACT_ASSET")
                        ),
                        fx_layer_movement.c.movement_kind.in_(
                            (
                                *(
                                    ("LIABILITY_LAYER_CREATED", "ASSET_LAYER_SETTLED")
                                    if entry.flow.amount < 0
                                    else ("LIABILITY_LAYER_CONSUMED", "ASSET_LAYER_CREATED")
                                ),
                                "ASSET_LAYER_REMEASURED",
                                "LIABILITY_LAYER_REMEASURED",
                            )
                        ),
                    )
                )
                .mappings()
                .all()
            )
            remeasured = [
                item for item in found if str(item["movement_kind"]).endswith("_REMEASURED")
            ]
            all_sources = found
            found = [
                item for item in found if not str(item["movement_kind"]).endswith("_REMEASURED")
            ]
            if (
                not found
                or any(
                    str(item["functional_currency"]).strip() != currency
                    or str(item["txn_currency"]).strip() != row.currency
                    for item in all_sources
                )
                or any(
                    item["trace_node_id"] not in nodes
                    or nodes[item["trace_node_id"]].currency != currency
                    or Decimal(nodes[item["trace_node_id"]].value)
                    != Decimal(item["amount_functional"])
                    for item in all_sources
                )
                or sum((Decimal(item["amount_txn"]) for item in found), ZERO)
                != abs(entry.flow.amount)
            ):
                raise tie_outs.invalid(
                    "currency_view",
                    f"Billing {event_id} has no matching functional layer evidence.",
                )
            consumed.extend(UUID(str(item["id"])) for item in all_sources)
            settlement = sum(
                (
                    Decimal(item["amount_functional"])
                    * (-1 if item["balance_role"] == "CONTRACT_LIABILITY" else 1)
                    for item in remeasured
                ),
                ZERO,
            )
            if settlement:
                if entry.period_id is None:
                    raise tie_outs.invalid(
                        "currency_view", "Billing settlement lacks its report period."
                    )
                settlement_key = (*key, entry.period_id)
                settlements[settlement_key] = settlements.get(settlement_key, ZERO) + settlement
                parts: dict[str | None, Decimal] = {}
                if all(item["balance_role"] == LIABILITY_ROLE for item in remeasured):
                    for item in remeasured:
                        creation = (
                            session.execute(
                                select(fx_layer_movement).where(
                                    fx_layer_movement.c.contract_version_id == row.version_id,
                                    fx_layer_movement.c.contract_id == row.contract_id,
                                    fx_layer_movement.c.entity_id == row.entity_id,
                                    fx_layer_movement.c.layer_key == item["layer_key"],
                                    fx_layer_movement.c.movement_kind == "LIABILITY_LAYER_CREATED",
                                )
                            )
                            .mappings()
                            .one_or_none()
                        )
                        node = (
                            None if creation is None else nodes.get(str(creation["trace_node_id"]))
                        )
                        if (
                            creation is None
                            or node is None
                            or node.currency != currency
                            or Decimal(node.value) != Decimal(creation["amount_functional"])
                        ):
                            raise tie_outs.invalid(
                                "currency_view",
                                "Settlement FX layer lacks verified creation evidence.",
                            )
                        consumed.append(UUID(str(creation["id"])))
                        identity = (
                            None
                            if creation["effective_date"] < periods[row.entity_id][0].start
                            else str(item["layer_key"])
                        )
                        parts[identity] = parts.get(identity, ZERO) - Decimal(
                            item["amount_functional"]
                        )
                translated.append(
                    replace(
                        entry,
                        order=(*entry.order, 0),
                        flow=Flow(settlement, False, FX, liability_fx=tuple(parts.items())),
                    )
                )
            memo_spot: dict[str, Decimal] = {}
            if entry.flow.amount > 0 and (
                params.binding is None or "event_posted_fx_v1" in params.binding.evidence
            ):
                from ..credit_memo_fx import parts as memo_parts

                memo_nodes = [
                    node
                    for node in trace.nodes
                    if node.formula_id == "fx.credit_memo_difference.v1"
                ]
                scales = {
                    child: (int(node.params["minor_unit"]), int(node.params["txn_minor_unit"]))
                    for node in memo_nodes
                    for child in node.inputs
                    if isinstance(child, str)
                }
                raw = []
                for item in found:
                    scale = scales.get(str(item["trace_node_id"]))
                    if scale is None:
                        continue
                    raw.append(
                        {
                            **item,
                            "contract_key": rows[
                                (UUID(str(item["contract_id"])), row.entity_id)
                            ].external_id,
                            "source_key": str(event_id),
                            "functional_currency": currency,
                            "effective_date": item["effective_date"].isoformat(),
                            "amount_functional": int(
                                Decimal(item["amount_functional"]).scaleb(scale[0])
                            ),
                            "amount_txn": int(Decimal(item["amount_txn"]).scaleb(scale[1])),
                        }
                    )
                try:
                    for part in memo_parts(trace, raw):
                        memo_spot[part.relief_node_id] = Decimal(part.spot_minor).scaleb(
                            -scales[part.relief_node_id][0]
                        )
                except (ValueError, KeyError) as error:
                    raise tie_outs.invalid("currency_view", str(error)) from error
            for index, item in enumerate(
                sorted(
                    found,
                    key=lambda item: (
                        item["movement_kind"] == "LIABILITY_LAYER_CREATED",
                        str(item["id"]),
                    ),
                )
            ):
                amount = memo_spot.get(
                    str(item["trace_node_id"]), Decimal(item["amount_functional"])
                )
                source_owner = UUID(str(item["contract_id"]))
                if asset_sources:
                    if entry.period_id is None:
                        raise tie_outs.invalid(
                            "currency_view", "Billing source lacks a report period."
                        )
                    billing_key = (row.contract_id, row.entity_id, entry.period_id)
                    billing_assets.setdefault(billing_key, ZERO)
                    if item["balance_role"] == "CONTRACT_ASSET":
                        signed = -amount if entry.flow.amount < 0 else amount
                        billing_assets[billing_key] += signed
                        if source_owner != row.contract_id:
                            for owner, sign in ((source_owner, 1), (row.contract_id, -1)):
                                asset_key = (owner, row.entity_id, entry.period_id)
                                asset_transfers[asset_key] = (
                                    asset_transfers.get(asset_key, ZERO) + sign * signed
                                )
                if str(item["trace_node_id"]) in memo_spot and source_owner != row.contract_id:
                    if entry.period_id is None:
                        raise tie_outs.invalid(
                            "currency_view", "Member memo lacks a posting period."
                        )
                    for owner, sign in ((source_owner, -1), (row.contract_id, 1)):
                        transfer_key = (owner, row.entity_id, entry.period_id)
                        member_transfers[transfer_key] = (
                            member_transfers.get(transfer_key, ZERO) + sign * amount
                        )
                translated.append(
                    replace(
                        entry,
                        order=(*entry.order, 1, index),
                        flow=Flow(
                            -amount if entry.flow.amount < 0 else amount,
                            False,
                            BILLING,
                            layer_key=str(item["layer_key"])
                            if item["movement_kind"] == "LIABILITY_LAYER_CREATED"
                            else None,
                        ),
                    )
                )
        result[key] = translated
    # Settlement FX belongs immediately before the invoice. Remove that same
    # amount from period-end posted FX, retaining its net movement exactly.
    for (contract_id, entity_id, period_id), settlement in settlements.items():
        key = (contract_id, entity_id)
        at = next(item for item in periods[entity_id] if item.id == period_id)
        posted.setdefault(key, []).append(
            Entry(
                order=(at.end, LINE_RANK, at.end, params.known_at, 0, "settlement-timing"),
                flow=Flow(-settlement, False, FX),
                period_id=period_id,
                entry_kind="FX_REMEASUREMENT",
            )
        )
    if asset_sources:
        evidence = {
            "asset_amounts": {
                ":".join(map(str, key)): str(value) for key, value in sorted(billing_assets.items())
            },
            "transfers": {
                ":".join(map(str, key)): str(value)
                for key, value in sorted(asset_transfers.items())
            },
        }
        if (
            params.binding is not None
            and params.binding.evidence["billing_asset_sources_v1"] != evidence
        ):
            raise tie_outs.invalid(
                "currency_view", "Billing asset sources differ from retained evidence."
            )
        tie_outs.record_evidence(params, "billing_asset_sources_v1", evidence)
    tie_outs.require_members(params, "functional_billing_layer", consumed)
    tie_outs.record_members(params, "functional_billing_layer", consumed)
    return result


@dataclass(frozen=True, slots=True)
class Document:
    """A billing document of a contract: the invoice line or credit memo the engine keeps
    (S10-R-07), its effective date, its place in the stream and its amount — positive for an
    invoice, negative for a credit memo — and the instant it was recorded at, which decides the
    period it enters the path in where an end is a lock's (``entered``; None: not stated, the
    document is taken as recorded before any lock)."""

    effective_date: date
    record_seq: int
    event_id: UUID
    amount: Decimal
    recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BillingSourceEvent:
    """A stored contract event read as ``billing_identity.BillingEvent`` (ENG-06 order)."""

    event_id: UUID
    contract_id: UUID
    event_type: str
    effective_date: date
    record_seq: int
    payload: Mapping[str, object]
    recorded_at: datetime | None = None

    @property
    def event_key(self) -> str:
        return str(self.event_id)

    @property
    def contract_key(self) -> str:
        return str(self.contract_id)

    @property
    def order_key(self) -> tuple[date, int, str]:
        return (self.effective_date, self.record_seq, str(self.event_id))


def kept_documents(events: Iterable[BillingSourceEvent], voided: Iterable[UUID]) -> list[Document]:
    """The billing documents of one contract's stream, in ENG-06 order: the kept
    ``BILLING_RECORDED`` lines of S10-R-07 (a status update of a line adds no billing) and the
    ``CREDIT_MEMO_RECORDED`` events, less the events ``voided`` names. Pure."""
    dropped = set(voided)
    stream = [event for event in events if event.event_id not in dropped]
    kept = {line.event_id for line in billing_identity.kept_lines(stream)}
    found: list[Document] = []
    for event in stream:
        if event.event_type == ContractEventType.BILLING_RECORDED.value:
            if event.event_id not in kept:
                continue
            sign = 1
        elif event.event_type == ContractEventType.CREDIT_MEMO_RECORDED.value:
            sign = -1
        else:
            continue
        found.append(
            Document(
                effective_date=event.effective_date,
                record_seq=event.record_seq,
                event_id=event.event_id,
                amount=sign * _payload_amount(event.payload),
                recorded_at=event.recorded_at,
            )
        )
    return found


def _payload_amount(payload: Mapping[str, object]) -> Decimal:
    money = payload.get("amount")
    if not isinstance(money, Mapping):
        raise ValueError("a billing event carries no amount")
    return Decimal(str(money["amount"]))


def unposted_periods(
    deltas: Sequence[tuple[PeriodRef, Decimal]], posted: Sequence[Entry]
) -> list[PeriodRef]:
    """The periods of the range whose billing posted no line, for one contract and entity (ruling
    R-72 (a)). ``deltas`` gives, per period, the delta of the engine's ``billed_unconditional_cum``;
    ``posted`` the role's subledger lines of the range. A period is named when that delta less the
    ``BILLING`` and ``CREDIT_MEMO`` lines of the period is not zero and the period holds no such
    line — with such lines the billing is on the role already. Pure."""
    found: list[PeriodRef] = []
    for item, delta in deltas:
        lines = [
            entry
            for entry in posted
            if entry.period_id == item.id and entry.entry_kind in BILLING_KINDS
        ]
        on_role = -sum((entry.flow.amount for entry in lines), ZERO)  # credit positive
        if not lines and delta - on_role != 0:
            found.append(item)
    return found


def document_entries(wanted: Sequence[PeriodRef], documents: Sequence[Document]) -> list[Entry]:
    """The documents dated in the ``wanted`` periods as flows of the path, each at its effective
    date and before the lines of that date. They enter as recorded: a difference from the engine's
    delta is never plugged, it stays unexplained. Pure."""
    return [
        Entry(
            order=(
                document.effective_date,
                DOCUMENT_RANK,
                document.record_seq,
                str(document.event_id),
            ),
            flow=document_flow(document.amount),
            period_id=next(
                item.id for item in wanted if item.start <= document.effective_date <= item.end
            ),
        )
        for document in documents
        if any(item.start <= document.effective_date <= item.end for item in wanted)
    ]


type End = tuple[PeriodRef | None, datetime | None]


def entered(documents: Sequence[Document], ends: Sequence[End]) -> list[list[Document]]:
    """Per period of a range, the documents that enter the path in it (ENGINE_SPEC_B S15-R-20 rev
    1.168; the supervisor's ruling of 2026-10-02). ``ends`` are the range's period ends in order,
    the end before the range first (None where the range starts at the first period), each with
    the cutoff of the lock it is read from (None where it is read from the versions).

    An end HOLDS a document dated on or before it — unless the end is a lock's and the document
    was recorded after that lock's cutoff: the lock's balances do not hold it. A document is a
    movement of the first period whose end holds it and whose opening end does not; so a
    document recorded after the lock of the period it is dated in enters in the first period
    whose end is not locked, or was locked after the document was recorded — as a line posted
    with an earlier origin does. Without a lock every document enters in the period it is dated
    in. One list per period of the range, in the documents' order. Pure."""

    def holds(end: End, document: Document) -> bool:
        period, frozen = end
        if period is None or document.effective_date > period.end:
            return False
        return frozen is None or document.recorded_at is None or document.recorded_at <= frozen

    found: list[list[Document]] = [[] for _ in ends[1:]]
    for document in documents:
        if holds(ends[0], document):
            continue  # in the opening already
        for index, end in enumerate(ends[1:]):
            if holds(end, document):
                found[index].append(document)
                break
    return found


def _billing(
    session: Session,
    *,
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    posted: Mapping[tuple[UUID, UUID], Sequence[Entry]],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    before: Mapping[UUID, PeriodRef | None],
    traces: Mapping[UUID, TracedBalances],
    cutoff: datetime,
    params: ReportParams,
    locked: tie_outs.LockedEnds | None = None,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    """The billing that posts no line, per contract and entity (``unposted_periods``,
    ``document_entries``). The engine's billed amount is read from the trace of the version the
    balances came from; the documents are the billing events of the contracts that need them,
    recorded by the cutoff. S15-R-24: the events consumed are recorded as
    ``members.contract_event`` on a live build and a bound run reads exactly those (an empty
    population is a captured empty membership).

    Where an end of an entity's range is a lock's (``locked``; S15-R-20 rev 1.168), a document
    enters in the period ``entered`` gives it, not in the period it is dated in: the engine's
    delta of a period is taken less the documents dated in it that enter elsewhere and plus
    those that enter in it from an earlier date, and a document keeps its own date in the order
    of the path, as a line posted with an earlier origin keeps its. For such an entity the
    streams read
    are those of the contracts with a period whose billing posted no line, as without a lock,
    and of the contracts with a billing event recorded after the earliest of the locks read —
    a document dated before the range can enter in it, and only such an event can move one."""
    wanted: dict[tuple[UUID, UUID], list[PeriodRef]] = {}
    moved: dict[tuple[UUID, UUID], tuple[list[End], list[tuple[PeriodRef, Decimal]]]] = {}
    frozen: dict[UUID, list[End]] = {}
    for entity_id, items in periods.items():
        if locked is None:
            continue
        ends: list[End] = []
        for item in (before.get(entity_id), *items):
            end = None if item is None else locked.at(entity_id, item)
            ends.append((item, None if end is None else end.frozen_at))
        if any(cutoff_of is not None for _, cutoff_of in ends):
            frozen[entity_id] = ends
    for key, row in rows.items():
        entity_id = key[1]
        traced = traces[row.version_id]
        earlier = before.get(entity_id)
        previous = tie_outs.billed_through(
            traced,
            external_id=row.external_id,
            entity_code=row.entity_code,
            period_key=None if earlier is None else earlier.key,
        )
        deltas: list[tuple[PeriodRef, Decimal]] = []
        for item in periods.get(entity_id, ()):
            current = tie_outs.billed_through(
                traced,
                external_id=row.external_id,
                entity_code=row.entity_code,
                period_key=item.key,
            )
            deltas.append((item, current - previous))
            previous = current
        if entity_id in frozen:
            moved[key] = (frozen[entity_id], deltas)
            continue
        found = unposted_periods(deltas, posted.get(key, ()))
        if found:
            wanted[key] = found
    # only the streams of the contracts with such a period are read — and, beside a lock's end,
    # of the contracts with a billing event recorded after the earliest lock read
    read = {key[0] for key in wanted}
    read |= {
        key[0]
        for key, (_, deltas) in moved.items()
        if unposted_periods(deltas, posted.get(key, ()))
    }
    others = sorted({key[0] for key in moved} - read, key=str)
    if others:
        earliest = min(at for ends in frozen.values() for _, at in ends if at is not None)
        read |= {
            UUID(str(found_id))
            for found_id in session.execute(
                select(contract_event.c.contract_id)
                .where(
                    contract_event.c.contract_id.in_(others),
                    contract_event.c.event_type.in_(STREAM_TYPES),
                    contract_event.c.recorded_at > earliest,
                    contract_event.c.recorded_at <= cutoff,
                )
                .distinct()
            ).scalars()
        }
    streams = _streams(session, sorted(read, key=str), cutoff=cutoff, params=params)
    entries = {key: document_entries(found, streams.get(key, ())) for key, found in wanted.items()}
    for key, (ends, deltas) in moved.items():
        if key[0] not in read:
            continue
        documents = streams.get(key, ())
        entering = entered(documents, ends)
        adjusted: list[tuple[PeriodRef, Decimal]] = []
        for (item, delta), here in zip(deltas, entering, strict=True):
            dated = sum(
                (d.amount for d in documents if item.start <= d.effective_date <= item.end), ZERO
            )
            adjusted.append((item, delta - dated + sum((d.amount for d in here), ZERO)))
        named = {item.id for item in unposted_periods(adjusted, posted.get(key, ()))}
        flows = [
            Entry(
                order=(
                    document.effective_date,
                    DOCUMENT_RANK,
                    document.record_seq,
                    str(document.event_id),
                ),
                flow=document_flow(document.amount),
                period_id=item.id,
            )
            for (item, _), here in zip(deltas, entering, strict=True)
            if item.id in named
            for document in here
        ]
        if flows:
            entries[key] = flows
    return entries


def _streams(
    session: Session, contract_ids: Sequence[UUID], *, cutoff: datetime, params: ReportParams
) -> dict[tuple[UUID, UUID], list[Document]]:
    """The billing documents of ``contract_ids``, per contract and contracting entity."""
    if not contract_ids:
        tie_outs.require_members(params, "contract_event", ())
        tie_outs.record_members(params, "contract_event", ())
        return {}
    rows = session.execute(
        select(
            contract_event.c.id,
            contract_event.c.contract_id,
            contract_event.c.contracting_entity_id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.record_seq,
            contract_event.c.payload,
            contract_event.c.supersedes_event_id,
            contract_event.c.recorded_at,
        )
        .where(
            contract_event.c.contract_id.in_(list(contract_ids)),
            contract_event.c.event_type.in_(STREAM_TYPES),
            contract_event.c.recorded_at <= cutoff,
            *tie_outs.bound_member_where(params, "contract_event", contract_event.c.id),
        )
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq, contract_event.c.id)
    ).mappings()
    consumed: list[UUID] = []
    events: dict[tuple[UUID, UUID], list[BillingSourceEvent]] = {}
    voided: dict[UUID, set[UUID]] = {}
    void_contracts: set[UUID] = set()
    for row in rows:
        consumed.append(UUID(str(row["id"])))
        contract_key = UUID(str(row["contract_id"]))
        event_type = str(getattr(row["event_type"], "value", row["event_type"]))
        if event_type == ContractEventType.EVENT_VOIDED.value:
            if row["supersedes_event_id"] is not None:
                voided.setdefault(contract_key, set()).add(UUID(str(row["supersedes_event_id"])))
            continue
        if event_type == ContractEventType.CONTRACT_VOIDED.value:
            void_contracts.add(contract_key)
            continue
        key = (contract_key, UUID(str(row["contracting_entity_id"])))
        events.setdefault(key, []).append(
            BillingSourceEvent(
                event_id=UUID(str(row["id"])),
                contract_id=contract_key,
                event_type=event_type,
                effective_date=row["effective_date"],
                record_seq=int(row["record_seq"]),
                payload=row["payload"],
                recorded_at=row["recorded_at"],
            )
        )
    tie_outs.require_members(params, "contract_event", consumed)
    tie_outs.record_members(params, "contract_event", consumed)
    return {
        key: kept_documents(found, voided.get(key[0], ()))
        for key, found in events.items()
        if key[0] not in void_contracts
    }


def _check_view(params: ReportParams, found: Sequence[EntityRef], items: Sequence[Any]) -> None:
    view = str(params.parameters.get("currency_view") or "transaction")
    functional = {entity.id: entity.functional_currency for entity in found}
    if view != "transaction" and any(item.currency != functional[item.entity_id] for item in items):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


COLUMNS: Final = (
    Column("section", "Section", "integer"),
    # D-98 85 (CLO-7c): the stable line code is the row's identity in the frozen dataset; the label
    # is a display attribute.
    Column("line_code", "Line code", "code"),
    Column("line_label", "Line", "text"),
    Column(LIABILITY, "Contract liability", "money"),
    Column(ASSET, "Contract asset", "money"),
    Column(UNBILLED, "Unbilled receivable", "money"),
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("currency", "Currency", "code"),
    Column("opening", "Opening", "money"),
    Column("billings", "Billings", "money"),
    Column("revenue_from_opening", "Revenue from opening", "money"),
    Column("revenue_from_period_billings", "Revenue from period billings", "money"),
    Column("reclassifications", "Reclassifications", "money"),
    Column("fx_remeasurement", "FX remeasurement", "money"),
    Column("business_combinations", "Business combinations", "money"),
    Column("other", "Other", "money"),
    Column("closing", "Closing", "money"),
)


OTHER_THRESHOLD: Final = "rollforward_other_threshold_v1"


def other_explanations(
    items: Sequence[ContractRollforward],
    totals: Mapping[str, Lines],
    ratio: Decimal,
    *,
    book: str,
    ending_periods: Mapping[UUID, str],
) -> list[dict[str, str]]:
    """Preserve signed, currency-specific exceptions, including contracts that offset in total."""
    flagged: list[dict[str, str]] = []
    populations = [("", "", "", currency, lines) for currency, lines in sorted(totals.items())] + [
        (
            item.external_id,
            item.entity_code,
            ending_periods.get(item.entity_id, ""),
            item.currency,
            item.lines,
        )
        for item in items
    ]
    for contract_key, entity, period_key, currency, lines in populations:
        for role in ROLLFORWARD_BALANCES:
            other, closing = lines["OTHER"][role], lines["CLOSING"][role]
            if abs(Fraction(other)) > Fraction(ratio) * abs(Fraction(closing)):
                flagged.append(
                    {
                        "contract": contract_key,
                        "entity": entity,
                        "period": period_key,
                        "book": book,
                        "currency": currency,
                        "role": role,
                        "other": str(other),
                        "closing": str(closing),
                    }
                )
    return flagged


def _other_control(
    session: Session,
    params: ReportParams,
    items: Sequence[ContractRollforward],
    totals: Mapping[str, Lines],
    *,
    book: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
) -> dict[str, Any]:
    if params.binding is not None:
        if OTHER_THRESHOLD not in params.binding.evidence:
            return {}  # Historical reports did not retain this setting; never read today's value.
        raw = str(params.binding.evidence[OTHER_THRESHOLD])
    else:
        raw = str(
            setting(session, "close.rollforward_other_threshold_ratio", known_at=params.known_at)
        )
        tie_outs.record_evidence(params, OTHER_THRESHOLD, raw)
    ratio = Decimal(raw)
    if not ratio.is_finite() or ratio < 0:
        raise ValueError("Rollforward Other threshold must be a finite nonnegative ratio")
    return {
        "other_explanation": {
            "threshold_ratio": raw,
            "items": other_explanations(
                items,
                totals,
                ratio,
                book=book,
                ending_periods={key: values[-1].key for key, values in periods.items() if values},
            ),
        }
    }


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, before = ranges(session, params)
    contract_id = tie_outs.contract_named(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    ends = locked_ends.Reader(
        uow,
        params,
        book_code=book_code,
        cutoff=cutoff,
        entity_codes={item.id: item.code for item in found},
    )
    view = str(params.parameters.get("currency_view") or "transaction")
    items = rollforwards(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        periods=periods,
        before=before,
        known_at=params.known_at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        functional=view in {"functional", "reporting"},
        period_detail=view == "reporting",
        locked=ends,
        uow=uow,
    )
    _check_view(params, found, items)
    functional_items = items
    rate_evidence: list[dict[str, Any]] = []
    from .. import acquisition_groups

    group_presentation = any(item.group_members for item in items)
    line_codes: tuple[str, ...] = (
        (*LINES[:-1], *acquisition_groups.EXTRA_LINES, "CLOSING") if group_presentation else LINES
    )
    if view == "reporting":
        items, rate_evidence = reporting_rollforward.project(
            session,
            params,
            tenant_id=uow.principal.tenant_id,
            entities=found,
            periods=periods,
            before=before,
            items=items,
            locked=ends,
        )
        line_codes = (*line_codes[:-1], *reporting_rollforward.EXTRA_LINES, "CLOSING")
    role = BALANCE_ROLES[str(params.parameters.get("balance_role") or "CONTRACT_LIABILITY")]
    totals: dict[str, Lines] = {}
    for item in items:
        into = totals.setdefault(
            item.currency, {line: dict.fromkeys(ROLLFORWARD_BALANCES, ZERO) for line in line_codes}
        )
        for line in line_codes:
            for balance in ROLLFORWARD_BALANCES:
                into[line][balance] += item.lines.get(line, {}).get(balance, ZERO)
    rows: list[dict[str, Any]] = []
    mixed = len(totals) > 1
    for currency, lines in sorted(totals.items()):
        for line in line_codes:
            rows.append(
                {
                    "row_key": f"{line}:{currency}" if mixed else line,
                    "section": 1,
                    "line_code": line,
                    "line_label": {**LABELS, **acquisition_groups.LABELS}[line],
                    # 04 T-CLS-05 dataset identity (D-98 85): a line row is identified by its
                    # line code and currency; the contract column is stated EMPTY, never left
                    # out — the lock freeze reads every key column by name (S15-R-18).
                    "contract_external_id": None,
                    "currency": currency,
                    **{
                        balance: tie_outs.money(lines[line][balance], currency)
                        for balance in ROLLFORWARD_BALANCES
                    },
                }
            )
    for item in items:
        rows.append(
            {
                "row_key": f"contract:{item.external_id}:{item.entity_code}",
                "section": 2,
                # a by-contract row is identified by its contract and currency: no line code
                "line_code": None,
                "contract_external_id": item.external_id,
                "customer_name": item.customer_name,
                "currency": item.currency,
                **(
                    {
                        "attribution_scope": "Group movements; members have endpoint balances only",
                        "group_members": ", ".join(m.external_id for m in item.group_members),
                    }
                    if item.group_members
                    else {}
                ),
                **{
                    line.lower(): tie_outs.money(
                        item.lines.get(line, {}).get(role, ZERO), item.currency
                    )
                    for line in line_codes
                },
            }
        )
        for member in item.group_members:
            rows.append(
                {
                    "row_key": f"member-endpoints:{member.external_id}:{member.entity_code}",
                    "section": 3,
                    "line_code": None,
                    "contract_external_id": member.external_id,
                    "customer_name": member.customer_name,
                    "currency": member.currency,
                    "attribution_scope": "Member endpoints; movements shown in the group row",
                    "group_members": item.external_id,
                    **{
                        line.lower(): tie_outs.money(member.lines[line][role], member.currency)
                        if line in {"OPENING", "CLOSING"}
                        else None
                        for line in line_codes
                    },
                }
            )
    control: dict[str, Any] = _other_control(
        session, params, items, totals, book=book_code, periods=periods
    )
    for balance in ROLLFORWARD_BALANCES:
        control[f"opening_{balance}"] = tie_outs.by_currency(
            {code: lines["OPENING"][balance] for code, lines in totals.items()}
        )
        control[f"closing_{balance}"] = tie_outs.by_currency(
            {code: lines["CLOSING"][balance] for code, lines in totals.items()}
        )
    closing_balances = tie_outs.balances_at(
        session,
        uow=uow,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys={key: (value[-1] if value else None) for key, value in periods.items()},
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        locked_ends=ends,
    )
    if view in {"functional", "reporting"}:
        closing_balances = functional_balances.read(
            session,
            params,
            closing_balances,
            entities=found,
            periods={key: (value[-1] if value else None) for key, value in periods.items()},
            book_code=book_code,
            locked=ends,
            measures=ROLLFORWARD_BALANCES,
        )
    movement_check = balances_tie(totals, functional_items)
    balance_check = balances_equal_tie(closing_balances, functional_items)
    gl_check = rollforward_gl.build(
        session,
        params,
        entities=found,
        periods=periods,
        items=functional_items,
        book_code=book_code,
        contract_id=contract_id,
    )
    columns: tuple[Column, ...] = COLUMNS
    if view == "reporting":
        columns = (
            *COLUMNS[:-1],
            Column("translation", "Reporting currency translation", "money"),
            Column("rounding", "Translation rounding", "money"),
            COLUMNS[-1],
        )
        control["translation_rates"] = rate_evidence
        control["tie_out_currency_basis"] = "functional for balance and GL comparisons"
        for check in (balance_check, gl_check):
            check.setdefault("details", []).append(
                {"reason": "Compared in functional currency before reporting translation."}
            )
        if any(
            month["OTHER"][balance] != 0
            for item in functional_items
            for month in item.period_lines.values()
            for balance in ROLLFORWARD_BALANCES
        ):
            movement_check["result"] = tie_outs.FAIL
            movement_check.setdefault("details", []).append(
                {"reason": "Functional period movements contain unexplained OTHER."}
            )
    if group_presentation:
        columns = (
            *columns,
            Column("attribution_scope", "Attribution scope", "text"),
            Column("group_members", "Group members", "text"),
            *(
                Column(code.lower(), acquisition_groups.LABELS[code], "money")
                for code in acquisition_groups.EXTRA_LINES
            ),
        )
        control["group_movement_presentation"] = (
            "Group movements; member endpoints are informational and excluded from totals. "
            "Monthly opening revenue and asset settlements keep their original classification."
        )
    from ..acquisition_cells import retain as retain_acquisition_cells

    retain_acquisition_cells(params, items, rows, role, rate_evidence)
    from ..split_cells import retain as retain_split_cells

    retain_split_cells(params, items, rows, role, rate_evidence)
    return ReportData(
        columns=columns,
        rows=tuple(rows),
        control_totals=control,
        tie_out_results=(movement_check, balance_check, gl_check),
    )


def balances_tie(
    totals: Mapping[str, Lines], items: Sequence[ContractRollforward] = ()
) -> dict[str, Any]:
    """``TO_ROLLFORWARD_BALANCES``: opening plus explained activity equals closing, per currency
    over the three balances; any non-zero ``OTHER`` fails (S15-R-07)."""
    expected: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    unexplained = False
    for currency, lines in totals.items():
        for balance in ROLLFORWARD_BALANCES:
            add(expected, currency, lines["CLOSING"][balance])
            explained = sum(
                (lines[line][balance] for line in lines if line not in ("OTHER", "CLOSING")), ZERO
            )
            add(actual, currency, explained)
            unexplained = unexplained or lines["OTHER"][balance] != 0
    result = tie_outs.compared(tie_outs.TO_ROLLFORWARD_BALANCES, expected, actual)
    if unexplained:
        result["result"] = tie_outs.FAIL
    if any(item.lines["OTHER"][balance] != 0 for item in items for balance in ROLLFORWARD_BALANCES):
        result["result"] = tie_outs.FAIL
        result.setdefault("details", []).append(
            {"reason": "Individual contract movements contain unexplained OTHER."}
        )
    return result


def balances_equal_tie(
    closing: Sequence[BalanceRow], items: Sequence[ContractRollforward]
) -> dict[str, Any]:
    """``TO_BALANCES_EQ_ROLLFORWARD``: Σ contract liability, contract asset and unbilled receivable
    at the range end equals Σ the ``CLOSING`` line (CTL-030)."""
    expected: dict[str, Decimal] = {}
    for row in closing:
        add(expected, row.currency, sum((row.value(b) for b in ROLLFORWARD_BALANCES), ZERO))
    actual: dict[str, Decimal] = {}
    for item in items:
        add(
            actual,
            item.currency,
            sum((item.lines["CLOSING"][b] for b in ROLLFORWARD_BALANCES), ZERO),
        )
    return tie_outs.compared(tie_outs.TO_BALANCES_EQ_ROLLFORWARD, expected, actual)
