"""Functional POB disclosure from original openings and selected-range posted control revenue."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_api.domain.reports import opening_relief_frozen, opening_relief_pob, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.uow import UnitOfWork

KEY = "opening_relief_functional_pob_v1"
ZERO = Decimal(0)


def rows(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    book: str,
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    before: Mapping[UUID, tie_outs.PeriodRef | None],
    locked: tie_outs.LockedEnds,
    items: Sequence[rollforward.ContractRollforward],
    policies: Mapping[str, str],
    reporting_slices: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], set[tuple[UUID, UUID]]]:
    evidence_key = KEY if reporting_slices is None else "opening_relief_reporting_pob_v1"
    cutoff = tie_outs.cutoff_for(uow.session, params)
    selected = tie_outs.balances_at(
        uow.session,
        entity_ids=params.entity_ids,
        book_code=book,
        period_keys={key: (value[-1] if value else None) for key, value in periods.items()},
        cutoff=cutoff,
        params=params,
    )
    sources = {(row.contract_id, row.entity_id): row for row in selected}
    posted = rollforward._lines(
        uow.session,
        params.entity_ids,
        book,
        periods,
        params.known_at,
        None,
        params=params,
        functional=True,
    )
    groups: dict[tuple[UUID, UUID, str], list[rollforward.ContractRollforward]] = defaultdict(list)
    for item in items:
        if policies.get(str(item.entity_id)) != "FIFO_WITHIN_POB":
            continue
        source = sources.get((item.contract_id, item.entity_id))
        if source is None:
            raise tie_outs.invalid("currency_view", "Functional POB source version is missing.")
        groups[(source.version_id, item.entity_id, item.currency)].append(item)
    frozen_sources = opening_relief_frozen.Reader(uow)
    result = []
    excluded: set[tuple[UUID, UUID]] = set()
    evidence: dict[str, Any] = {}
    for (version, entity, currency), members in groups.items():
        group_key = f"{version}:{entity}:{currency}"
        opening = sum((item.lines["OPENING"][rollforward.LIABILITY] for item in members), ZERO)
        consumed = -sum(
            (
                item.lines[line][rollforward.LIABILITY]
                for item in members
                for line in ("REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS")
            ),
            ZERO,
        )
        recognized = ZERO
        eligible = []
        facts = {}
        previous = before.get(entity)
        frozen = None if previous is None else locked.at(entity, previous)
        for item in members:
            key = (item.contract_id, item.entity_id)
            source = sources[key]
            entries = posted.get(key, ())
            member_revenue = sum(
                (entry.flow.amount for entry in entries if entry.flow.is_revenue), ZERO
            )
            path_revenue = sum(
                (
                    values[rollforward.ASSET]
                    + values[rollforward.UNBILLED]
                    - values[rollforward.LIABILITY]
                    for code, values in item.lines.items()
                    if code in {"REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS"}
                ),
                ZERO,
            )
            if member_revenue != path_revenue:
                raise tie_outs.invalid(
                    "currency_view", "Functional posted revenue differs from its balance path."
                )
            original = None
            frozen_facts = None
            if frozen is not None and previous is not None:
                original, frozen_facts = frozen_sources.read(
                    row=source,
                    previous=previous,
                    locked=frozen,
                    book=book,
                )
            amount, detail = opening_relief_pob.calculate(
                uow.session,
                source,
                previous,
                entries,
                opening,
                consumed,
                opening_row=original,
                opening_absent=frozen is not None and original is None,
                functional_currency=currency,
            )
            if frozen_facts is not None:
                detail["frozen_opening"] = frozen_facts
            detail["currency_view"] = "functional"
            detail["currency"] = currency
            detail["transaction_currency"] = source.currency
            detail["eligible_relief_capped_by_group"] = detail.pop("relief")
            facts[str(item.contract_id)] = detail
            recognized += member_revenue
            eligible.append(amount)
            excluded.add(key)
        amount = opening_relief_pob.group_total(eligible, opening=opening, consumed=consumed)
        evidence[group_key] = {
            "members": facts,
            "opening": str(opening),
            "recognized": str(recognized),
            "consumed": str(consumed),
            "relief": str(amount),
        }
        if reporting_slices is not None:
            from .opening_relief_periods import deltas

            period_amounts = deltas(
                periods=[p.id for p in periods[entity]],
                opening=opening,
                obligations={
                    subject: Decimal(detail.get("opening_billing", "0"))
                    - Decimal(detail.get("opening_revenue", "0"))
                    for member in facts.values()
                    for subject, detail in member["obligations"].items()
                },
                entries=[
                    entry
                    for item in members
                    for entry in posted.get((item.contract_id, entity), ())
                ],
                consumption={
                    p.id: -sum(
                        (
                            item.period_lines[p.id][line][rollforward.LIABILITY]
                            for item in members
                            for line in ("REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS")
                        ),
                        ZERO,
                    )
                    for p in periods[entity]
                },
                expected=amount,
            )
            evidence[group_key]["period_relief"] = {
                p.key: str(period_amounts[p.id]) for p in periods[entity]
            }
            reporting_slices[group_key] = {
                "members": [(item.contract_id, entity) for item in members],
                "entity": entity,
                "periods": period_amounts,
                "currency": currency,
                "row_key": f"combined:{group_key}"
                if len(members) > 1
                else f"contract:{members[0].external_id}:{members[0].entity_code}",
            }
        if opening == recognized == amount == 0 and (
            reporting_slices is None or not any(period_amounts.values())
        ):
            continue
        combined = len(members) > 1
        first = members[0]
        result.append(
            {
                "row_key": f"combined:{group_key}"
                if combined
                else f"contract:{first.external_id}:{first.entity_code}",
                "section": 2,
                "summary": (
                    "Combined contracts (group total): "
                    + "; ".join(sorted(item.external_id for item in members))
                    + ". Member relief is not allocated."
                )
                if combined
                else None,
                "contract_external_id": None if combined else first.external_id,
                "customer_name": None if combined else first.customer_name,
                "entity_code": first.entity_code,
                "currency": currency,
                "opening_contract_liability": tie_outs.money(opening, currency),
                "revenue_recognized": tie_outs.money(recognized, currency),
                "revenue_from_opening": tie_outs.money(amount, currency),
            }
        )
    if params.binding is not None and params.binding.evidence[evidence_key] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Functional POB sources differ from retained evidence."
        )
    tie_outs.record_evidence(params, evidence_key, evidence)
    return result, excluded
