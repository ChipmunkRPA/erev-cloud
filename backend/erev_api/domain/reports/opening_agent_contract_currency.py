"""Functional and reporting contract-FIFO agent disclosures."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_api.uow import UnitOfWork

from . import (
    opening_agent_contract as agent,
)
from . import (
    opening_agent_postings,
    opening_agent_sources,
    opening_source_membership,
    tie_outs,
)
from . import (
    opening_relief_availability as availability,
)
from .builders import ReportParams
from .builders import contract_balance_rollforward as rollforward

ZERO = Decimal(0)


def rows(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    book: str,
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    items: Sequence[rollforward.ContractRollforward],
    policies: Mapping[str, str],
    reporting_slices: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], set[tuple[UUID, UUID]]]:
    if not agent.enabled(params):
        return [], set()
    sources = {
        (row.contract_id, row.entity_id): row
        for row in tie_outs.balances_at(
            uow.session,
            entity_ids=params.entity_ids,
            book_code=book,
            period_keys={key: (value[-1] if value else None) for key, value in periods.items()},
            cutoff=tie_outs.cutoff_for(uow.session, params),
            params=params,
        )
    }
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
    source_uow = (
        uow
        if params.requester is None
        else UnitOfWork(
            ctx=params.requester,
            session=uow.session,
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
        )
    )
    net = opening_agent_postings.read(source_uow, params, book, periods, view="functional")
    groups: dict[tuple[UUID, UUID, str], list[rollforward.ContractRollforward]] = defaultdict(list)
    for item in items:
        if policies.get(str(item.entity_id)) != "FIFO_WITHIN_CONTRACT":
            continue
        source = sources.get((item.contract_id, item.entity_id))
        if source is None:
            raise tie_outs.invalid("currency_view", "Contract FIFO original version is missing.")
        groups[(source.version_id, item.entity_id, item.currency)].append(item)
    output = []
    excluded: set[tuple[UUID, UUID]] = set()
    evidence = {}
    paid: set[UUID] = set()
    for (version, entity, currency), members in groups.items():
        group_key = f"{version}:{entity}:{currency}"
        selected = [sources[item.contract_id, entity] for item in members]
        opening = sum((item.lines["OPENING"][rollforward.LIABILITY] for item in members), ZERO)
        consumed = -sum(
            (
                item.lines[line][rollforward.LIABILITY]
                for item in members
                for line in ("REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS")
            ),
            ZERO,
        )
        result = agent.calculate(
            source_uow,
            selected,
            posted,
            net,
            start=periods[entity][0].start,
            opening=opening,
            consumed=consumed,
            view="functional",
            allow_unresolved=availability.enabled(params),
            allow_historical_owners=opening_agent_sources.historical_enabled(params),
            allow_contracting_revenue=opening_agent_sources.contracting_enabled(params),
            allow_historical_principal=opening_source_membership.enabled(params),
            allow_zero_consumption=reporting_slices is None
            or all(
                sum(
                    (
                        item.period_lines[p.id][line][rollforward.LIABILITY]
                        for item in members
                        for line in ("REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS")
                    ),
                    ZERO,
                )
                >= ZERO
                for p in periods[entity]
            ),
        )
        if result is None:
            continue
        row = agent.row(selected, group_key, currency, opening, result)
        if reporting_slices is not None:
            relief, revenue = agent.period_slices(
                result,
                periods=periods[entity],
                opening=opening,
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
            )
            reporting_slices[group_key] = {
                "members": [(item.contract_id, entity) for item in members],
                "entity": entity,
                "periods": relief,
                "net_revenue": revenue,
                "currency": currency,
                "row_key": row["row_key"],
            }
        evidence[group_key] = result.evidence
        paid.update(result.paid)
        output.append(row)
        excluded.update((item.contract_id, entity) for item in members)
    agent.retain(params, evidence, paid)
    return output, excluded
