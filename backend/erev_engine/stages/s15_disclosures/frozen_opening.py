"""Apply authenticated original openings without changing monetary posting targets."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from erev_engine.bundle import DisclosureOpeningInput
from erev_engine.stages.state import AllocatedState, BookContext

from .rollforward import BALANCES, BalanceInputs, BalanceRollforward, rollforward_balances


def apply(
    ctx: BookContext,
    st: AllocatedState,
    records: BalanceInputs,
    row: BalanceRollforward,
    inputs: Sequence[DisclosureOpeningInput],
) -> BalanceRollforward:
    matched = [
        item
        for item in inputs
        if (item.book_code, item.entity, item.period_key, item.view)
        == (row.book_code, row.entity, row.period_key, row.view)
    ]
    if not matched:
        return row
    if len(matched) != 1:
        raise ValueError("Duplicate frozen disclosure opening")
    item = matched[0]
    if (
        item.currency != row.currency
        or item.opening_date != row.opening_date
        or set(item.balances) != set(BALANCES)
        or any(type(value) is not int for value in item.balances.values())
        or not item.source.get("lock_id")
        or not item.source.get("output_sha256")
    ):
        raise ValueError("Frozen disclosure opening identity or balances differ")
    policy = ctx.policies.value(
        "rollforward.opening_liability_consumption", entity=row.entity, period=row.period_key
    )
    obligations = dict(item.obligations)
    if policy == "FIFO_WITHIN_POB":
        from erev_engine.stages.s01_canonicalize import obligation_subject_key

        subjects = {ob.subject_key for ob in st.obligations if ob.contracting_entity == row.entity}
        for event in st.events:
            if event.event_type != "CONTRACT_AMENDED" or event.effective_date <= item.opening_date:
                continue
            lines = event.payload.get("lines", [])
            if not isinstance(lines, (tuple, list)):
                continue
            for line in lines:
                if not isinstance(line, Mapping):
                    continue
                key = line.get("obligation_key")
                if line.get("action") == "ADD" and isinstance(key, str):
                    subject = obligation_subject_key(event.contract_key, key)
                    if subject in subjects and subject not in obligations:
                        obligations[subject] = 0
    result = rollforward_balances(
        ctx,
        st,
        records,
        row.entity,
        row.period_key,
        view=row.view,
        opening=item.balances,
        opening_obligations=obligations if policy == "FIFO_WITHIN_POB" else None,
    )
    return replace(result, opening_source=item.source)
