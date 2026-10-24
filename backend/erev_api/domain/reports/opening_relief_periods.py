"""Signed period deltas of POB eligibility against one original range opening."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from uuid import UUID

from . import opening_relief_pob, tie_outs
from .builders.contract_balance_rollforward import Entry

ZERO = Decimal(0)


def deltas(
    *,
    periods: Sequence[UUID],
    opening: Decimal,
    obligations: Mapping[str, Decimal],
    entries: Sequence[Entry],
    consumption: Mapping[UUID, Decimal],
    expected: Decimal,
    source_eligibility: Mapping[str, Sequence[Entry]] | None = None,
) -> dict[UUID, Decimal]:
    """Reversals reduce cumulative eligibility; new-period billings never reset the opening."""
    if len(set(periods)) != len(periods) or any(
        entry.flow.is_revenue and entry.period_id not in periods for entry in entries
    ):
        raise tie_outs.invalid("currency_view", "POB posting periods differ from the range.")
    source_eligibility = source_eligibility or {}
    if any(
        subject not in obligations
        or any(
            entry.period_id not in periods
            or entry.subject_key != subject
            or not entry.flow.is_revenue
            for entry in items
        )
        for subject, items in source_eligibility.items()
    ):
        raise tie_outs.invalid("currency_view", "Agent source eligibility differs from the range.")
    source_totals = dict.fromkeys(source_eligibility, ZERO)
    recognized = dict.fromkeys(obligations, ZERO)
    consumed = prior = ZERO
    result = {}
    for period in periods:
        for entry in entries:
            if entry.period_id == period and entry.flow.is_revenue:
                if entry.subject_key not in recognized:
                    raise tie_outs.invalid("currency_view", "Period revenue lacks a POB source.")
                recognized[entry.subject_key] += entry.flow.amount
        for subject, items in source_eligibility.items():
            source_totals[subject] += sum(
                (entry.flow.amount for entry in items if entry.period_id == period), ZERO
            )
        consumed += consumption[period]
        current = opening_relief_pob.group_total(
            [
                min(
                    max(ZERO, amount),
                    max(ZERO, recognized[key]),
                    max(ZERO, source_totals[key]) if key in source_totals else max(ZERO, amount),
                )
                for key, amount in obligations.items()
            ],
            opening=opening,
            consumed=consumed,
        )
        result[period] = current - prior
        prior = current
    if prior != expected:
        raise tie_outs.invalid(
            "currency_view", "Period POB relief does not reconcile to the range."
        )
    return result
