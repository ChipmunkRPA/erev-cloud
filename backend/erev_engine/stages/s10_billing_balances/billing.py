"""Stage 10 billing attribution and billed measures (ENGINE_SPEC_B §10.2.1, §10.2.2; ENC-11).

Billing is attributed per document (S10-R-01). A line with ``obligation_key`` goes to that
obligation. The unreferenced lines of one document are summed to T, and |T| is apportioned once by
``largest_remainder`` with the sign applied after apportioning (POLICIES ALG-02 step 3; CHK-003c).
The weights are the attribution of the credited invoice for a credit memo that names one; otherwise
the posted allocations at the document date of the contract's non-VC obligations of the header's
contracting entity, then their resolved SSPs when those sum to 0. ``billed_cum`` is attributed
invoice lines with S10-R-06 unconditional date by the date less attributed credit memos effective
by the date; in ERP mode and for noncancellable lines the unconditional date is the effective date,
and billing while ``NOT_A_CONTRACT`` still counts (S10-R-03, S10-R-04; D-89 L7-6-Q-9). The
apportioned part is node ``billed_attributed_cum``. ``billed_unconditional_cum`` per contract and
contracting entity counts the lines whose right is unconditional by the period end, except those
recorded while the contract was ``NOT_A_CONTRACT`` (S10-R-04, S10-R-08). ``remaining_billing`` is
the billing plan of the segment in force less the billing since its boundary (S10-R-05;
ENGINE_SPEC Table 0.9-A; L2-4-Q-9). Every node comes from a registered formula (DG-KRN-EXP-04).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final, Protocol

from erev_engine import dates, money
from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s10_billing_balances import classification
from erev_engine.stages.s10_billing_balances.classification import (
    CREDIT_MEMO,
    INVOICE,
    Document,
    Line,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    ObligationState,
    OrderKey,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ATTRIBUTION_FORMULA",
    "REMAINING_BILLING_FORMULA",
    "UNCONDITIONAL_FORMULA",
    "Attribution",
    "BalanceMeasures",
    "Billed",
    "BillingDocumentOut",
    "attribute",
    "is_vc_line",
    "measure",
    "periods",
    "posted_allocation",
    "unconditional_attributed",
    "version_date",
]

ATTRIBUTION_FORMULA: Final = "bil.attribution.v1"
BILLED_AMOUNT_FORMULA: Final = "bil.billed_amount.v1"
REMAINING_BILLING_FORMULA: Final = "bil.remaining_billing.v1"
UNCONDITIONAL_FORMULA: Final = "bil.unconditional_date.v1"
_SEPARATOR: Final = "|"


@dataclass(frozen=True, slots=True)
class Attribution:
    """The attribution of one document to obligations, magnitudes as recorded (S10-R-01)."""

    document: Document
    direct: Mapping[str, int]  # referenced lines by obligation subject key
    shares: Mapping[str, int]  # apportioned unreferenced total by subject key
    unreferenced: int  # T, minor units
    keys: tuple[str, ...]  # apportionment keys (subject keys), sorted
    weights: tuple[Fraction, ...]
    basis: str  # CREDITED_INVOICE | ALLOCATION | RESOLVED_SSP | NONE

    @property
    def sign(self) -> int:
        """+1 for an invoice, −1 for a credit memo (S10-R-03)."""
        return -1 if self.document.kind == CREDIT_MEMO else 1

    def signed(self) -> dict[str, int]:
        """Signed attributed amounts by obligation subject key."""
        out: dict[str, int] = {}
        for mapping in (self.direct, self.shares):
            for subject_key, amount in mapping.items():
                out[subject_key] = out.get(subject_key, 0) + self.sign * amount
        return out


@dataclass(frozen=True, slots=True)
class BillingDocumentOut:
    """One invoice or credit memo: its lines with unconditional dates and its attribution."""

    document_key: str  # event key of the first line
    contract_key: str
    kind: str  # INVOICE | CREDIT_MEMO
    number: str
    effective_date: date
    lines: tuple[Line, ...]
    attribution: Mapping[str, int]  # obligation subject key -> signed minor units (S10-INV-04)


@dataclass(frozen=True, slots=True)
class BalanceMeasures:
    """Stage 10 T-CON-11 values of one obligation at the version date (§10.1)."""

    subject_key: str
    as_of: date  # d_v (04 T-CON-11 effective_date)
    billed_cum: int
    billed_amount: int  # activity: billing of the lines first included (CV-64)
    remaining_billing: int
    remaining_billing_exact: Fraction  # exact billing plan − billing since the boundary
    trace_nodes: Mapping[str, str]  # measure -> node id
    # S10-R-12 (ENC-12): billed_cum − revenue_cum; exact values for the parity runner (DG-PAR-05).
    position_obligation: int = 0
    position_obligation_exact: Fraction = Fraction(0)
    position_contract_entity: int = 0
    position_contract_entity_exact: Fraction = Fraction(0)
    netting_reclass_amount: int = 0  # ENC-14: attribution of the reclass of the version's period
    netting_reclass_amount_exact: Fraction = Fraction(0)
    netting_reclass_role: str | None = None  # CONTRACT_ASSET | UNBILLED_RECEIVABLE when non-zero
    # D-87 L4-3-Q-24 (b): an agent obligation's billing net of credit memos to d_v; None otherwise.
    gross_amount_memo: int | None = None


@dataclass(frozen=True, slots=True)
class Billed:
    """Billing targets, documents, receipts on contract keys and obligation measures."""

    targets: tuple[Target, ...]  # billed_cum, billed_attributed_cum, billed_unconditional_cum
    documents: tuple[BillingDocumentOut, ...]
    paid_cum: Mapping[tuple[str, str], int]  # (contract@entity, period key) -> minor units
    measures: Mapping[str, BalanceMeasures]
    attributions: tuple[Attribution, ...] = ()  # per document, ENG-06 order (B_p of S10-R-20)


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def version_date(st: AllocatedState) -> date:
    """d_v: the latest effective date the version includes (04 T-CON-11 ``effective_date``)."""
    latest = max((ev.effective_date for ev in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def _segment_at(ob: ObligationState, d: date) -> AllocationSegment | None:
    """The ``FIXED`` segment in force at ``d`` by effective date (CV-60)."""
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component == "FIXED" and seg.effective_date <= d:
            found = seg
    return found


def posted_allocation(ob: ObligationState, d: date) -> int:
    """A_p of the ``FIXED`` segment in force at ``d``, 0 before the first (L2-4-Q-12)."""
    seg = _segment_at(ob, d)
    return 0 if seg is None else seg.a_posted


def _is_vc_line(ob: ObligationState) -> bool:
    return ob.is_vc_line or str(ob.obligation_kind) == "VC_LINE"


def is_vc_line(ob: ObligationState) -> bool:
    """A parity ``VC_LINE`` obligation, which takes no attribution weight (DEV-057)."""
    return _is_vc_line(ob)


def _obligation_of(st: AllocatedState, contract_key: str, obligation_key: str) -> ObligationState:
    for ob in st.obligations:
        if ob.contract_key == contract_key and ob.obligation_key == obligation_key:
            return ob
    raise _invariant(
        "a billing line names an obligation absent from the contract",
        contract_key,
        rule="S10-R-01",
        obligation_key=obligation_key,
    )


def attribute(
    st: AllocatedState,
    contract: ContractView,
    document: Document,
    lines: Sequence[Line],
    invoices: Mapping[tuple[str, str], Mapping[str, int]],
) -> Attribution:
    """``attribute_document`` of §10.2.1 over ``lines`` of ``document`` (S10-R-01)."""
    direct: dict[str, int] = {}
    for line in lines:
        if line.obligation_key is not None:
            ob = _obligation_of(st, document.contract_key, line.obligation_key)
            direct[ob.subject_key] = direct.get(ob.subject_key, 0) + line.amount
    total = sum(line.amount for line in lines if line.obligation_key is None)
    if total == 0:
        return Attribution(
            document, MappingProxyType(direct), MappingProxyType({}), 0, (), (), "NONE"
        )
    base = None
    credited = document.credited_invoice_number
    if document.kind == CREDIT_MEMO and credited is not None:
        base = invoices.get((document.contract_key, credited))
    keys: list[str]
    weights: list[Fraction]
    if base is not None and any(amount != 0 for amount in base.values()):
        keys = sorted(key for key, amount in base.items() if amount != 0)
        weights = [Fraction(abs(base[key])) for key in keys]
        basis = "CREDITED_INVOICE"
    else:
        entity = contract.header.contracting_entity_code
        candidates = sorted(
            (
                ob
                for ob in st.obligations
                if ob.contract_key == document.contract_key
                and ob.contracting_entity == entity
                and not _is_vc_line(ob)
            ),
            key=lambda ob: ob.subject_key,
        )
        keys = [ob.subject_key for ob in candidates]
        weights = []
        for ob in candidates:
            seg = _segment_at(ob, document.effective_date)
            weights.append(Fraction(0 if seg is None else seg.a_posted))
        basis = "ALLOCATION"
        if sum(weights, Fraction(0)) == 0:
            weights = [ob.resolved_ssp for ob in candidates]
            basis = "RESOLVED_SSP"
    if not keys or sum(weights, Fraction(0)) <= 0:
        raise _invariant(
            "unreferenced billing has no obligation to attribute to",
            document.contract_key,
            rule="S10-R-01",
            event_key=document.key,
        )
    shares = money.largest_remainder(total, weights, keys)  # |T|; the sign applies after
    return Attribution(
        document,
        MappingProxyType(direct),
        MappingProxyType(dict(zip(keys, shares, strict=True))),
        total,
        tuple(keys),
        tuple(weights),
        basis,
    )


def _restricted(st: AllocatedState, attribution: Attribution, lines: Sequence[Line]) -> Attribution:
    """The attribution of a subset of a document's lines over the same keys and weights."""
    if len(lines) == len(attribution.document.lines):
        return attribution
    direct: dict[str, int] = {}
    for line in lines:
        if line.obligation_key is not None:
            ob = _obligation_of(st, attribution.document.contract_key, line.obligation_key)
            direct[ob.subject_key] = direct.get(ob.subject_key, 0) + line.amount
    total = sum(line.amount for line in lines if line.obligation_key is None)
    shares: dict[str, int] = {}
    if total != 0:
        apportioned = money.largest_remainder(total, attribution.weights, attribution.keys)
        shares = dict(zip(attribution.keys, apportioned, strict=True))
    return Attribution(
        attribution.document,
        MappingProxyType(direct),
        MappingProxyType(shares),
        total,
        attribution.keys,
        attribution.weights,
        attribution.basis,
    )


def _periods(ctx: BookContext, st: AllocatedState, entity_code: str) -> tuple[PeriodInput, ...]:
    """Periods of the contracting entity from the group's inception period through its horizon."""
    entity = ctx.entities.get(entity_code)
    horizon_key = ctx.horizon.get(entity_code)
    if entity is None or horizon_key is None:
        raise _invariant(
            "the contracting entity has no calendar or horizon", entity_code, rule="CV-13"
        )
    ordered = tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))
    horizon = next((period for period in ordered if period.period_key == horizon_key), None)
    if horizon is None:
        raise _invariant(
            "the horizon period is absent from the calendar", entity_code, rule="CV-13"
        )
    first = dates.period_of(entity, st.inception_date)
    return tuple(
        period
        for period in ordered
        if period.start_date >= first.start_date and period.end_date <= horizon.end_date
    )


def periods(ctx: BookContext, st: AllocatedState, entity_code: str) -> tuple[PeriodInput, ...]:
    """The period ends stage 10 measures for a contracting entity: inception through horizon."""
    return _periods(ctx, st, entity_code)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def _counted(lines: Sequence[Line], t: date) -> list[Line]:
    """The lines ``billed_cum`` counts at ``t``: a credit memo by its ENG-06 position, an invoice
    line from its S10-R-06 unconditional date; ``in_position`` is not applied (S10-R-03, S10-R-04;
    D-89 L7-6-Q-9)."""
    return [
        line
        for line in lines
        if (line.kind == CREDIT_MEMO and line.event.effective_date <= t)
        or (line.unconditional_date is not None and line.unconditional_date <= t)
    ]


def _baseline_ref(ob: ObligationState, amount: int, mu: int) -> SourceRef:
    """The source of an opening baseline's billing: the ``OPENING_BALANCE_ESTABLISHED`` event of
    the obligation with the baseline ``billed_cum`` (the payload value, or the S07-R-08 fair-value
    share) as the cited value, so the ``billed_cum`` sum re-evaluates (DG-ENG-04, P14)."""
    event_key = None if ob.opening is None else ob.opening.get("event_key")
    if not isinstance(event_key, str):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "an opening baseline names no OPENING_BALANCE_ESTABLISHED event",
            subject_key=ob.subject_key,
            detail={"rule": "S07-R-05"},
        )
    detail = {"member": "opening_billed_cum", "value": money.format_money(amount, mu)}
    return SourceRef("contract_event", event_key, detail)


_RECOMPUTE: Final = "RECOMPUTE_FROM_INCEPTION"  # POL-210 (ENGINE_SPEC S07-R-06)


def _kept(line: Line, floor: date, recompute: bool) -> bool:
    """Whether a counted line stays beside the baseline: dated after the cutover, or an ``ENGINE``
    line under ``RECOMPUTE_FROM_INCEPTION`` (recomputed, not replaced: its difference to the
    imported ``billed_cum`` is the S07-R-07 billing difference; S10-R-03 rev 1.16)."""
    return _dated_after(line, floor) or (recompute and line.mode == classification.ENGINE)


class _Documented(Protocol):
    """A billing document as the predicate below reads it (``Document``, ``BillingDocumentOut``)."""

    @property
    def contract_key(self) -> str: ...

    @property
    def lines(self) -> Sequence[Line]: ...


def engine_lines_through(
    documents: Iterable[_Documented], contract_key: str, cutover: date
) -> bool:
    """Whether the ledger holds ``ENGINE``-mode lines of the contract dated on or before the cutover
    on the S10-R-03 date (a credit memo by its position, an invoice line by its unconditional date).
    Under ``RECOMPUTE_FROM_INCEPTION`` they are recomputed, not replaced, and the baseline
    ``billed_cum`` is not counted beside them — in ``billed_cum``, in B_u (S10-R-08) and in the
    stage 13 opening flow (S12-R-03); their excess over the imported ``billed_cum`` is the S07-R-07
    billing difference stage 14 posts once (rev 1.16). One predicate for stages 10, 13 and 14."""
    return any(
        line.mode == classification.ENGINE and not _dated_after(line, cutover)
        for document in documents
        if document.contract_key == contract_key
        for line in document.lines
    )


def _baseline_cutover(
    st: AllocatedState, contract_key: str, entity: str
) -> tuple[date | None, bool]:
    """(the one cutover date, whether the method is RECOMPUTE) of the stage 07 opening baselines
    of the contract's obligations at the entity, when every one of them carries a baseline with
    that date and method (S14-R-26 condition); (None, False) otherwise."""
    found: set[tuple[date, str]] = set()
    for ob in st.obligations:
        if ob.contract_key != contract_key or ob.contracting_entity != entity:
            continue
        baseline = baseline_of(ob)
        if baseline is None:
            return None, False
        found.add((baseline.cutover_date, baseline.method))
    if len(found) != 1:
        return None, False
    ((cutover, method),) = found
    return cutover, method == _RECOMPUTE


def _dated_after(line: Line, floor: date) -> bool:
    """Whether a counted line is dated after ``floor`` on the date ``_counted`` reads (S10-R-03
    rev 1.11: lines on or before an opening-baseline cutover are the ERP's, not the ledger's)."""
    if line.kind == CREDIT_MEMO:
        return line.event.effective_date > floor
    return line.unconditional_date is not None and line.unconditional_date > floor


class _Emitter:
    """Trace nodes and targets of the billing measures of one book (§10.5)."""

    def __init__(
        self,
        ctx: BookContext,
        tb: TraceBuilder,
        attributions: Sequence[Attribution],
        st: AllocatedState,
    ):
        self.ctx = ctx
        self.tb = tb
        self.st = st
        self.mu = classification.minor_unit(ctx)
        self.attributions = attributions
        self.share_nodes: dict[tuple[str, str], str] = {}
        self.restricted_nodes: dict[tuple[str, str], str] = {}  # (measure, subject key) -> node
        for attribution in attributions:
            self._shares(attribution)

    def _restricted_share(self, restricted: Attribution, counted: Sequence[Line], key: str) -> str:
        """``billed_attributed@<document>@<latest unconditional date>``: the share of ``key`` in the
        counted unreferenced lines of a document whose other lines are memo-only (D-89 L7-6-Q-9).
        The latest unconditional date of the counted lines names the subset."""
        document = restricted.document
        latest = max(line.unconditional_date or document.effective_date for line in counted)
        measure = f"billed_attributed@{document.key}@{latest.isoformat()}"
        found = self.restricted_nodes.get((measure, key))
        if found is not None:
            return found
        signed_total = restricted.sign * restricted.unreferenced
        detail = {
            "member": "unreferenced_total",
            "value": money.format_money(signed_total, self.mu),
        }
        node_id = self.tb.node(
            measure=measure,
            subject_key=key,
            period_key=None,
            value=restricted.sign * restricted.shares[key],
            currency=self.ctx.txn_currency,
            minor_unit=self.mu,
            formula_id=ATTRIBUTION_FORMULA,
            inputs=[SourceRef("contract_event", document.key, detail)],
            params={
                "key": key,
                "keys": _SEPARATOR.join(restricted.keys),
                "mode": "apportion",
                "weights": _SEPARATOR.join(rational_param(weight) for weight in restricted.weights),
            },
            narrative_key=_narrative(ATTRIBUTION_FORMULA),
        )
        self.restricted_nodes[(measure, key)] = node_id
        return node_id

    def _shares(self, attribution: Attribution) -> None:
        signed_total = attribution.sign * attribution.unreferenced
        if signed_total == 0:
            return
        detail = {
            "member": "unreferenced_total",
            "value": money.format_money(signed_total, self.mu),
        }
        params = {
            "keys": _SEPARATOR.join(attribution.keys),
            "mode": "apportion",
            "weights": _SEPARATOR.join(rational_param(weight) for weight in attribution.weights),
        }
        for subject_key in attribution.keys:
            self.share_nodes[(attribution.document.key, subject_key)] = self.tb.node(
                measure=f"billed_attributed@{attribution.document.key}",
                subject_key=subject_key,
                period_key=None,
                value=attribution.sign * attribution.shares[subject_key],
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=ATTRIBUTION_FORMULA,
                inputs=[SourceRef("contract_event", attribution.document.key, detail)],
                params={**params, "key": subject_key},
                narrative_key=_narrative(ATTRIBUTION_FORMULA),
            )

    def _engine_lines_through(self, contract_key: str, cutover: date) -> bool:
        """``engine_lines_through`` over the attributed documents (S10-R-03 rev 1.16)."""
        return engine_lines_through(
            (attribution.document for attribution in self.attributions), contract_key, cutover
        )

    def billed(
        self, ob: ObligationState, t: date, period_key: str | None
    ) -> tuple[str, int, str | None, int]:
        """(``billed_cum`` node, value, ``billed_attributed_cum`` node or None, its value) at t.

        From the cutover date of the obligation's stage 07 opening baseline, the baseline
        ``billed_cum`` (the ERP's cumulative billing; the fair-value share under S07-R-08 IFRS15)
        replaces the ledger's lines dated on or before the cutover and is cited through the
        baseline node (S10-R-03 rev 1.11; ENGINE_SPEC S07-R-05; ENB-9).
        """
        inputs: list[str | SourceRef] = []
        direct = 0
        share_ids: list[str] = []
        shared = 0
        baseline = baseline_of(ob)
        floor: date | None = None
        recompute = baseline is not None and baseline.method == _RECOMPUTE
        if baseline is not None and t >= baseline.cutover_date:
            floor = baseline.cutover_date
            if not (recompute and self._engine_lines_through(ob.contract_key, floor)):
                inputs.append(_baseline_ref(ob, baseline.billed_cum, self.mu))
                direct += baseline.billed_cum
        for attribution in self.attributions:
            document = attribution.document
            if document.effective_date > t:
                continue
            counted = _counted(document.lines, t)
            if floor is not None:
                counted = [line for line in counted if _kept(line, floor, recompute)]
            if not counted:
                continue
            if document.contract_key == ob.contract_key:
                for line in counted:
                    if line.obligation_key != ob.obligation_key:
                        continue
                    amount = attribution.sign * line.amount
                    detail = {"member": "amount", "value": money.format_money(amount, self.mu)}
                    inputs.append(SourceRef("contract_event", line.event.event_key, detail))
                    direct += amount
            if len(counted) == len(document.lines):
                share_id = self.share_nodes.get((document.key, ob.subject_key))
                if share_id is not None:
                    share_ids.append(share_id)
                    shared += attribution.sign * attribution.shares[ob.subject_key]
                continue
            restricted = _restricted(self.st, attribution, counted)
            if ob.subject_key in restricted.shares:
                share_ids.append(self._restricted_share(restricted, counted, ob.subject_key))
                shared += attribution.sign * restricted.shares[ob.subject_key]
        attributed_id: str | None = None
        as_of = {"as_of": t.isoformat(), "mode": "sum"}
        if share_ids:
            attributed_id = self.tb.node(
                measure="billed_attributed_cum",
                subject_key=ob.subject_key,
                period_key=period_key,
                value=shared,
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=ATTRIBUTION_FORMULA,
                inputs=share_ids,
                params=as_of,
                narrative_key=_narrative(ATTRIBUTION_FORMULA),
            )
            inputs.append(attributed_id)
        node_id = self.tb.node(
            measure="billed_cum",
            subject_key=ob.subject_key,
            period_key=period_key,
            value=direct + shared,
            currency=self.ctx.txn_currency,
            minor_unit=self.mu,
            formula_id=ATTRIBUTION_FORMULA,
            inputs=inputs,
            params=as_of,
            narrative_key=_narrative(ATTRIBUTION_FORMULA),
        )
        return node_id, direct + shared, attributed_id, shared

    def unconditional(
        self,
        st: AllocatedState,
        contract_key: str,
        entity: str,
        t: date,
        period_key: str,
        entities: Mapping[str, str],
    ) -> tuple[str, int]:
        """``billed_unconditional_cum:<contract>@<entity>:<period>`` (S10-R-04, S10-R-08).

        From the cutover date of the contract's stage 07 opening baselines (every obligation of the
        contract at this entity carrying one with the same cutover), B_u counts their baseline
        ``billed_cum`` in place of the lines dated on or before the cutover (S10-R-03 rev 1.11;
        ENGINE_SPEC S07-R-05): the ERP's cutover billing is the opening net position.
        """
        inputs: list[str | SourceRef] = []
        total = 0
        floor, recompute = _baseline_cutover(st, contract_key, entity)
        if (
            floor is not None
            and t >= floor
            and not (recompute and self._engine_lines_through(contract_key, floor))
        ):
            for ob in st.obligations:
                if ob.contract_key == contract_key and ob.contracting_entity == entity:
                    baseline = baseline_of(ob)
                    if baseline is not None:
                        inputs.append(_baseline_ref(ob, baseline.billed_cum, self.mu))
                        total += baseline.billed_cum
        else:
            floor = None
        for attribution in self.attributions:
            document = attribution.document
            if document.contract_key != contract_key or document.effective_date > t:
                continue
            counted = [
                line
                for line in document.lines
                if line.in_position
                and (
                    line.kind == CREDIT_MEMO
                    or (line.unconditional_date is not None and line.unconditional_date <= t)
                )
                and (floor is None or _kept(line, floor, recompute))
            ]
            if not counted:
                continue
            restricted = _restricted(st, attribution, counted)
            amount = sum(
                value
                for subject_key, value in restricted.signed().items()
                if entities[subject_key] == entity
            )
            if amount == 0:
                continue
            detail = {
                "member": "unconditional_billing",
                "value": money.format_money(amount, self.mu),
            }
            inputs.append(SourceRef("contract_event", document.key, detail))
            total += amount
        node_id = self.tb.node(
            measure="billed_unconditional_cum",
            subject_key=contract_entity_subject_key(contract_key, entity),
            period_key=period_key,
            value=total,
            currency=self.ctx.txn_currency,
            minor_unit=self.mu,
            formula_id=UNCONDITIONAL_FORMULA,
            inputs=inputs,
            params={"as_of": t.isoformat()},
            narrative_key=_narrative(UNCONDITIONAL_FORMULA),
        )
        return node_id, total

    def unconditional_obligation(
        self, st: AllocatedState, ob: ObligationState, t: date, period_key: str
    ) -> tuple[tuple[str, int], tuple[str, int]]:
        """(node, value) of ``billed_unconditional_cum`` and ``sales_tax_billed_cum`` of one
        obligation at t, the JET-03 invoice inputs (Table 14-A; S10-R-02, S10-R-06 to S10-R-08).

        Billing is the obligation's attribution of the unconditional lines of its contract's
        documents less credit memos, as ``unconditional`` sums it per contract. The tax of a
        referenced line goes to its obligation; the tax of the unreferenced lines of a document is
        apportioned once over the document's keys and weights (L5-5-Q-9).
        """
        billing_inputs: list[str | SourceRef] = []
        tax_inputs: list[str | SourceRef] = []
        billed = taxed = 0
        for attribution in self.attributions:
            document = attribution.document
            if document.contract_key != ob.contract_key or document.effective_date > t:
                continue
            counted = [
                line
                for line in document.lines
                if line.in_position
                and (
                    line.kind == CREDIT_MEMO
                    or (line.unconditional_date is not None and line.unconditional_date <= t)
                )
            ]
            if not counted:
                continue
            amount = _restricted(st, attribution, counted).signed().get(ob.subject_key, 0)
            tax = attribution.sign * _obligation_tax(attribution, counted, ob)
            if amount != 0:
                detail = {
                    "member": "unconditional_billing",
                    "value": money.format_money(amount, self.mu),
                }
                billing_inputs.append(SourceRef("contract_event", document.key, detail))
                billed += amount
            if tax != 0:
                detail = {"member": "tax", "value": money.format_money(tax, self.mu)}
                tax_inputs.append(SourceRef("contract_event", document.key, detail))
                taxed += tax
        found: list[tuple[str, int]] = []
        for measure_name, value, inputs in (
            ("billed_unconditional_cum", billed, billing_inputs),
            ("sales_tax_billed_cum", taxed, tax_inputs),
        ):
            node_id = self.tb.node(
                measure=measure_name,
                subject_key=ob.subject_key,
                period_key=period_key,
                value=value,
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=UNCONDITIONAL_FORMULA,
                inputs=inputs,
                params={"as_of": t.isoformat()},
                narrative_key=_narrative(UNCONDITIONAL_FORMULA),
            )
            found.append((node_id, value))
        return found[0], found[1]


def _obligation_tax(attribution: Attribution, lines: Sequence[Line], ob: ObligationState) -> int:
    """The magnitude of the tax of ``lines`` that one obligation carries (L5-5-Q-9)."""
    direct = sum(line.tax_amount for line in lines if line.obligation_key == ob.obligation_key)
    unreferenced = sum(line.tax_amount for line in lines if line.obligation_key is None)
    if unreferenced == 0 or ob.subject_key not in attribution.keys:
        return direct
    shares = money.largest_remainder(unreferenced, attribution.weights, attribution.keys)
    return direct + dict(zip(attribution.keys, shares, strict=True))[ob.subject_key]


def _boundary_key(st: AllocatedState, ob: ObligationState, seg: AllocationSegment) -> OrderKey:
    for ev in st.events:
        if ev.event_key == seg.event_key:
            return ev.order_key
    raise _invariant("the boundary event of a segment is absent", ob.subject_key, rule="CV-60")


def _billed_before(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment | None,
    attributions: Sequence[Attribution],
) -> int:
    """Billing attributed to ``ob`` strictly before the boundary of a PROSPECTIVE segment: the lines
    whose ``unconditional_source`` (a credit memo's own event) precedes the boundary, unreferenced
    shares over the counted lines (D-89 L7-6-Q-9)."""
    if seg is None or seg.basis != "PROSPECTIVE" or seg.event_key is None:
        return 0
    if seg.cause == SegmentCause.OPENING_BALANCE:
        # S07-R-05 (S10-R-03 rev 1.11): the ERP's cumulative billing at the cutover IS the billing
        # before the boundary; it replaces the ledger's lines dated on or before the cutover, as
        # ``billed`` does, so they are never counted beside it (C5-R1).
        baseline = baseline_of(ob)
        if baseline is not None:
            return baseline.billed_cum
    boundary = _boundary_key(st, ob, seg)
    total = 0
    for attribution in attributions:
        counted = [
            line
            for line in attribution.document.lines
            if line.unconditional_source is not None
            and line.unconditional_source.order_key < boundary
        ]
        if counted:
            total += _restricted(st, attribution, counted).signed().get(ob.subject_key, 0)
    return total


def measure(
    ctx: BookContext, st: AllocatedState, classified: classification.Classified, tb: TraceBuilder
) -> Billed:
    """Attributions, billing targets and measures of every obligation of one book (§10.2.1)."""
    contracts = {view.header.external_id: view for view in st.contracts}
    attributions: list[Attribution] = []
    invoices: dict[tuple[str, str], dict[str, int]] = {}
    documents: list[BillingDocumentOut] = []
    for document in classified.documents:  # ENG-06 order of first lines
        attribution = attribute(
            st, contracts[document.contract_key], document, document.lines, invoices
        )
        signed = attribution.signed()
        if sum(signed.values()) != attribution.sign * sum(line.amount for line in document.lines):
            raise _invariant(
                "a document's attribution does not equal its amount",
                document.contract_key,
                rule="S10-INV-04",
                event_key=document.key,
            )
        if document.kind == INVOICE:
            base = invoices.setdefault((document.contract_key, document.number), {})
            for subject_key, amount in signed.items():
                base[subject_key] = base.get(subject_key, 0) + amount
        attributions.append(attribution)
        documents.append(
            BillingDocumentOut(
                document_key=document.key,
                contract_key=document.contract_key,
                kind=document.kind,
                number=document.number,
                effective_date=document.effective_date,
                lines=document.lines,
                attribution=MappingProxyType(dict(sorted(signed.items()))),
            )
        )
    emitter = _Emitter(ctx, tb, attributions, st)
    # Contracts with a line billed under ENGINE mode (S10-R-06): their obligations publish the
    # JET-03 inputs; ERP-mode contracts publish nothing new.
    engine_billed = {
        document.contract_key
        for document in classified.documents
        if any(line.mode == classification.ENGINE for line in document.lines)
    }
    mu = emitter.mu
    scale: int = 10**mu
    v = version_date(st)
    targets: list[Target] = []
    measures: dict[str, BalanceMeasures] = {}
    entities = {ob.subject_key: ob.contracting_entity for ob in st.obligations}
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        for period in _periods(ctx, st, ob.contracting_entity):
            node_id, value, attributed_id, shared = emitter.billed(
                ob, period.end_date, period.period_key
            )
            targets.append(
                Target(
                    ctx.book_code,
                    ob.contracting_entity,
                    ob.subject_key,
                    "billed_cum",
                    period.period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
            if attributed_id is not None:
                targets.append(
                    Target(
                        ctx.book_code,
                        ob.contracting_entity,
                        ob.subject_key,
                        "billed_attributed_cum",
                        period.period_key,
                        None,
                        shared,
                        None,
                        attributed_id,
                    )
                )
        if ob.contract_key in engine_billed:
            # JET-03 invoice inputs per obligation under ENGINE billing (Table 14-A; L4-3-Q-19;
            # lanes L5-3 and L5-5 at the L5 merge, the tax rule of L5-5-Q-9).
            for period in _periods(ctx, st, ob.contracting_entity):
                pair = emitter.unconditional_obligation(st, ob, period.end_date, period.period_key)
                for measure_name, (node_id, value) in zip(
                    ("billed_unconditional_cum", "sales_tax_billed_cum"), pair, strict=True
                ):
                    targets.append(
                        Target(
                            ctx.book_code,
                            ob.contracting_entity,
                            ob.subject_key,
                            measure_name,
                            period.period_key,
                            None,
                            value,
                            None,
                            node_id,
                        )
                    )
        billed_node, billed, _, _ = emitter.billed(ob, v, None)
        seg = _segment_at(ob, v)
        plan = Fraction(0) if seg is None else seg.remaining_billing_plan
        before = _billed_before(st, ob, seg, attributions)
        remaining = money.round_half_up(plan, mu) - (billed - before)
        exact = plan - Fraction(billed - before, scale)
        remaining_node = tb.node(
            measure="remaining_billing",
            subject_key=ob.subject_key,
            period_key=None,
            value=remaining,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=REMAINING_BILLING_FORMULA,
            inputs=[billed_node],
            params={
                "as_of": v.isoformat(),
                "billed_before": str(before),
                "plan": rational_param(plan),
            },
            exact=exact,
            narrative_key=_narrative(REMAINING_BILLING_FORMULA),
        )
        # D-89 L7-6-Q-9: the lines counted at d_v less those whose source the version holds already.
        new_amount = 0
        activity: list[SourceRef] = []
        for attribution in attributions:
            if attribution.document.effective_date > v:
                continue
            counted = _counted(attribution.document.lines, v)
            if not counted:
                continue
            old = [
                line
                for line in counted
                if line.unconditional_source is not None and not line.unconditional_source.is_new
            ]
            now = _restricted(st, attribution, counted).signed()
            before_new = _restricted(st, attribution, old).signed() if old else {}
            delta = now.get(ob.subject_key, 0) - before_new.get(ob.subject_key, 0)
            new_amount += delta
            if delta != 0:
                detail = {"role": "billed_amount", "value": money.format_money(delta, mu)}
                activity.append(SourceRef("contract_event", attribution.document.key, detail))
        # T-CON-11 ``billed_amount`` node (DG-KRN-EXP-01; D-97 (8)): the signed sum of each
        # document's effect on the obligation in this version (``bil.billed_amount.v1``).
        amount_node = tb.node(
            measure="billed_amount",
            subject_key=ob.subject_key,
            period_key=None,
            value=new_amount,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=BILLED_AMOUNT_FORMULA,
            inputs=list(activity),
            params={"as_of": v.isoformat()},
            narrative_key=_narrative(BILLED_AMOUNT_FORMULA),
        )
        measures[ob.subject_key] = BalanceMeasures(
            subject_key=ob.subject_key,
            as_of=v,
            billed_cum=billed,
            billed_amount=new_amount,
            remaining_billing=remaining,
            remaining_billing_exact=exact,
            trace_nodes=MappingProxyType(
                {
                    "billed_amount": amount_node,
                    "billed_cum": billed_node,
                    "remaining_billing": remaining_node,
                }
            ),
        )
    for contract_key in sorted(contracts):
        contract_entities = sorted(
            {ob.contracting_entity for ob in st.obligations if ob.contract_key == contract_key}
        )
        for entity in contract_entities:
            for period in _periods(ctx, st, entity):
                node_id, value = emitter.unconditional(
                    st, contract_key, entity, period.end_date, period.period_key, entities
                )
                targets.append(
                    Target(
                        ctx.book_code,
                        entity,
                        contract_entity_subject_key(contract_key, entity),
                        "billed_unconditional_cum",
                        period.period_key,
                        None,
                        value,
                        None,
                        node_id,
                    )
                )
    paid_cum: dict[tuple[str, str], int] = {}
    for contract_key, view in sorted(contracts.items()):
        entity = view.header.contracting_entity_code
        for period in _periods(ctx, st, entity):
            paid_cum[(contract_entity_subject_key(contract_key, entity), period.period_key)] = sum(
                receipt.amount
                for receipt in classified.receipts
                if receipt.contract_key == contract_key
                and receipt.event.effective_date <= period.end_date
            )
    return Billed(
        targets=tuple(targets),
        documents=tuple(documents),
        paid_cum=MappingProxyType(paid_cum),
        measures=MappingProxyType(measures),
        attributions=tuple(attributions),
    )


def unconditional_attributed(st: AllocatedState, billed: Billed, t: date) -> dict[str, int]:
    """B_p at ``t``: the signed billing attributed to each obligation from lines that enter the
    position and are unconditional by ``t``, credit memos included (S10-R-08, S10-R-20)."""
    out: dict[str, int] = {}
    for attribution in billed.attributions:
        document = attribution.document
        if document.effective_date > t:
            continue
        counted = [
            line
            for line in document.lines
            if line.in_position
            and (
                line.kind == CREDIT_MEMO
                or (line.unconditional_date is not None and line.unconditional_date <= t)
            )
        ]
        if not counted:
            continue
        for subject_key, value in _restricted(st, attribution, counted).signed().items():
            out[subject_key] = out.get(subject_key, 0) + value
    return out
