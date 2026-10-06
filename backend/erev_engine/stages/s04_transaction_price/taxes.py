"""Stage 04 sales taxes collected from customers.

ENGINE_SPEC S04-R-20; 606-10-32-2, 32-2A; POLICIES POL-045 (pin P), §6.2 row 5, JET-03 (CHK-023);
04 §16.3 ``BILLING_RECORDED.tax_amount`` and ``tax_lines`` (rev 1.2). The invoice lines are the
S10-R-07 kept lines of the kernel helper ``erev_engine.billing_identity`` (ENGINE_SPEC_B S10-R-07
"the same identity governs every consumer"; D-91 C606-05h). Private to stage 04. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import billing_identity, dates
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import payload_fraction, payload_text
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.state import BookContext, EventView, Quota1
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ASSESS_EACH_TAX",
    "EXCLUDE_ALL_IN_SCOPE",
    "FORMULA",
    "POLICY",
    "Tax",
    "collected_tax",
    "emit",
    "excluded",
]

POLICY: Final = "tp.sales_tax_exclusion"  # POL-045, pin P
EXCLUDE_ALL_IN_SCOPE: Final = "EXCLUDE_ALL_IN_SCOPE"
ASSESS_EACH_TAX: Final = "ASSESS_EACH_TAX"
FORMULA: Final = "tp.tax_excluded.v1"
PRINCIPAL: Final = "PRINCIPAL"
_OPTIONS: Final = frozenset({EXCLUDE_ALL_IN_SCOPE, ASSESS_EACH_TAX})


@dataclass(frozen=True, slots=True)
class Tax:
    """Tax of one included invoice line, excluded from the transaction price (S04-R-20)."""

    event: EventView
    amount: Fraction
    treatment: str  # resolved POL-045 literal
    principal_amount: Fraction  # tax lines flagged PRINCIPAL; stored evidence in 1.0 (OQ-A-14)


def excluded(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    *,
    contract_key: str | None = None,
) -> tuple[Tax, ...]:
    """Taxes of included ``BILLING_RECORDED`` lines dated on or before ``at`` and before ``before``.

    ``EXCLUDE_ALL_IN_SCOPE`` (ASC606): invoice tax never enters the price. ``ASSESS_EACH_TAX``
    (IFRS15, forced): every tax line is treated as collected on behalf of a third party and
    excluded until a tax-type principal mapping exists (OQ-A-14); a ``tax_lines`` member flagged
    ``PRINCIPAL`` is kept as evidence and is still excluded (L2-2-Q-9). ``tax_lines`` govern over
    ``tax_amount`` when present. The lines are the S10-R-07 kept lines of the kernel helper
    (``billing_identity.kept_lines`` over the ENG-06 measure events preceding ``before``, classified
    before the member and date filters; D-91 C606-05h): the identity is (contract key,
    ``invoice_number``, ``line_external_id``), so identical identifiers on two member contracts are
    two lines and a line of another contract never counts; a repeat whose ``is_cancellable`` is not
    true (``false``, ``"false"`` or absent, the 04 default) is a status update and adds no tax,
    whatever ``tax_amount`` it carries (stage 04 validates nothing; stage 10 owns
    ``INVOICE_STATUS_UPDATE_MISMATCH``); a repeat flagged cancellable is another line (D-91 C606-01
    (2)). The policy is read in the invoice's period for the contracting entity; a literal outside
    POL-045 raises ``ValueError`` (CV-17).
    """
    cb = st.identified.canonical
    members = set(st.identified.member_contract_keys) if contract_key is None else {contract_key}
    found: list[Tax] = []
    for event in billing_identity.kept_lines(cb.measure_events, before=before):
        if event.contract_key not in members or event.effective_date > at:
            continue
        amount, principal = _tax(event)
        if amount == 0:
            continue
        entity = cb.contracts[event.contract_key].header.contracting_entity_code
        period = dates.period_of(ctx.entities[entity], event.effective_date).period_key
        treatment = ctx.policies.value(POLICY, entity=entity, period=period)
        if not isinstance(treatment, str) or treatment not in _OPTIONS:
            raise ValueError(f"{POLICY} holds an unknown literal {treatment!r} (CV-17)")
        found.append(Tax(event, amount, treatment, principal))
    return tuple(found)


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject_key: str,
    quota: Quota1,
    taxes: Sequence[Tax],
) -> str:
    """Node ``sales_tax_excluded_amount`` (§4.4; ``tp.tax_excluded.v1``); its id."""
    inputs: list[str | SourceRef] = [
        SourceRef("contract_event", tax.event.event_key, {"value": format_exact(tax.amount)})
        for tax in taxes
    ]
    params = {
        "signs": ",".join("+" for _ in taxes),
        "treatment": ",".join(sorted({tax.treatment for tax in taxes})),
    }
    return tb.node(
        measure=measure_name,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=FORMULA,
        inputs=inputs,
        params=params,
        exact=quota.exact,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )


def _tax(event: EventView) -> tuple[Fraction, Fraction]:
    """(tax amount, amount of lines flagged ``PRINCIPAL``) of one billing line."""
    lines = event.payload.get("tax_lines")
    if isinstance(lines, list | tuple) and lines:
        total = principal = Fraction(0)
        for item in lines:
            if not isinstance(item, Mapping):
                raise ValueError(f"{event.event_key}: a tax line is not an object (§16.3)")
            amount = payload_fraction(item, "amount")
            if amount is None:
                raise ValueError(f"{event.event_key}: a tax line needs amount (§16.3)")
            total += amount
            if payload_text(item, "principal_or_agent") == PRINCIPAL:
                principal += amount
        return total, principal
    return payload_fraction(event.payload, "tax_amount") or Fraction(0), Fraction(0)


def collected_tax(events: Sequence[EventView], members: Collection[str], at: date) -> Fraction:
    """S04-R-20 memo amount at ``at``: Σ tax of the ``BILLING_RECORDED`` lines of the member
    contracts dated on or before ``at``, the lines being the kernel's S10-R-07 kept lines over
    ``events`` (``billing_identity.kept_lines``: identity at contract scope, a status update adds
    nothing, a repeat flagged cancellable is another line; D-91 C606-05h), as ``excluded`` sums
    them. Both POL-045 options exclude every tax line, so no policy is read (the version at d_v;
    lane L5-5)."""
    total = Fraction(0)
    for event in billing_identity.kept_lines(events):
        if event.contract_key not in members or event.effective_date > at:
            continue
        total += _tax(event)[0]
    return total
