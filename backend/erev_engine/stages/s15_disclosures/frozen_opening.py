"""Apply authenticated original openings without changing monetary posting targets."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace

from erev_engine.bundle import DisclosureOpeningInput
from erev_engine.stages.state import AllocatedState, BookContext

from .new_contract_opening import zero_contracts
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
        or not _has_source(item.source)
    ):
        raise ValueError("Frozen disclosure opening identity or balances differ")
    policy = ctx.policies.value(
        "rollforward.opening_liability_consumption", entity=row.entity, period=row.period_key
    )
    obligations = dict(item.obligations)
    encoded_zero = item.source.get("zero_opening_contracts_json")
    if encoded_zero is not None:
        try:
            claimed = json.loads(encoded_zero)
        except ValueError as error:
            raise ValueError("Invalid zero opening contract evidence") from error
        proven = zero_contracts(
            [contract.header for contract in st.contracts], st.events, item.opening_date
        )
        if (
            not isinstance(claimed, list)
            or not claimed
            or any(not isinstance(key, str) for key in claimed)
            or not set(claimed) <= proven
        ):
            raise ValueError("Zero opening contracts lack post-opening inception evidence")
        from erev_engine.stages.s01_canonicalize import encode_key

        prefixes = {encode_key(key) + "/" for key in claimed}
        for ob in st.obligations:
            if ob.contracting_entity == row.entity and any(
                ob.subject_key.startswith(prefix) for prefix in prefixes
            ):
                if ob.opening is not None or obligations.get(ob.subject_key, 0) != 0:
                    raise ValueError("New contract carries an existing opening balance")
                obligations[ob.subject_key] = 0
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


def _has_source(source: Mapping[str, str]) -> bool:
    encoded = source.get("sources_json")
    if encoded is None:
        return bool(source.get("output_sha256")) and not source.get("source_set_sha256")
    if hashlib.sha256(encoded.encode()).hexdigest() != source.get("source_set_sha256"):
        return False
    try:
        sources = json.loads(encoded)
    except (ValueError, TypeError):
        return False
    if not isinstance(sources, list) or len(sources) < 2:
        return False
    versions = set()
    for item in sources:
        if (
            not isinstance(item, dict)
            or any(
                not isinstance(item.get(key), str) or not item[key]
                for key in ("lock_id", "version", "output_sha256", "source_binding_sha256")
            )
            or item["lock_id"] != source.get("lock_id")
        ):
            return False
        versions.add(item["version"])
    return len(versions) == len(sources) and not source.get("output_sha256")
