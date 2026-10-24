"""Transaction opening relief follows the retained combination group's control path."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_api.domain.reports import (
    locked_ends,
    opening_consumption_policy,
    opening_relief_pob,
    opening_relief_frozen,
    opening_agent_sources,
    tie_outs,
)
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.opening_relief_currency import finish
from erev_api.domain.reports.outputs import ReportData
from erev_api.domain.reports.revenue_attribution import Attribution, for_control
from erev_api.uow import UnitOfWork
from erev_engine.money import DECIMAL_CONTEXT

KEY = "opening_relief_transaction_v1"
ZERO = Decimal(0)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    with localcontext(DECIMAL_CONTEXT):
        return _build(uow, params)


def _build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book = tie_outs.book_of(session, params)
    entities, periods, before = rollforward.ranges(session, params)
    use_pob = params.binding is None or opening_relief_pob.KEY in params.binding.evidence
    policies = (
        opening_consumption_policy.by_entity(session, params, entities, book) if use_pob else {}
    )
    pob_evidence: dict[str, Any] = {}
    cutoff = tie_outs.cutoff_for(session, params)
    locked = locked_ends.Reader(
        uow,
        params,
        book_code=book,
        cutoff=cutoff,
        entity_codes={entity.id: entity.code for entity in entities},
    )
    traces: dict[UUID, tie_outs.TracedBalances] = {}

    def balances(at: Mapping[UUID, tie_outs.PeriodRef | None]) -> tuple[tie_outs.BalanceRow, ...]:
        return tie_outs.balances_at(
            session,
            entity_ids=params.entity_ids,
            book_code=book,
            period_keys=at,
            cutoff=cutoff,
            params=params,
            traces=traces,
            locked_ends=locked,
        )

    opening = balances(before)
    closing = balances({key: (items[-1] if items else None) for key, items in periods.items()})
    selected = {(row.contract_id, row.entity_id): row for row in (*opening, *closing)}
    posted = rollforward._lines(
        session,
        params.entity_ids,
        book,
        periods,
        params.known_at,
        None,
        params=params,
        functional=False,
    )
    documents = rollforward._billing(
        session,
        rows=selected,
        posted=posted,
        periods=periods,
        before=before,
        traces=traces,
        cutoff=cutoff,
        params=params,
        locked=locked,
    )
    # A version identifies the original computation's combination membership;
    # never substitute today's group table for the selected report version.
    groups: dict[tuple[UUID, UUID, str], list[tuple[UUID, UUID]]] = defaultdict(list)
    for member, row in selected.items():
        groups[(row.version_id, row.entity_id, row.currency)].append(member)
    open_rows = {(row.contract_id, row.entity_id): row for row in opening}
    close_rows = {(row.contract_id, row.entity_id): row for row in closing}
    contracts: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    membership: dict[str, list[str]] = {}
    signed_key = "transaction_opening_posted_v1"
    signed_evidence: dict[str, Any] = {}
    paid_members: set[UUID] = set()
    source_cache: dict[UUID, Attribution] = {}
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
    frozen_sources = opening_relief_frozen.Reader(source_uow, params)
    use_agent_sources = (
        params.binding is None or opening_agent_sources.KEY in params.binding.evidence
    )
    agent_evidence: dict[str, Any] = {}
    for (version, entity, currency), members in groups.items():
        first = {
            name: sum((open_rows[key].value(name) for key in members if key in open_rows), ZERO)
            for name in tie_outs.ROLLFORWARD_BALANCES
        }
        last = {
            name: sum((close_rows[key].value(name) for key in members if key in close_rows), ZERO)
            for name in tie_outs.ROLLFORWARD_BALANCES
        }
        entries = sorted(
            (
                (key, entry)
                for key in members
                for entry in (*posted.get(key, ()), *documents.get(key, ()))
            ),
            key=lambda pair: (pair[1].order, selected[pair[0]].external_id),
        )
        has_reversal = any(entry.flow.is_revenue and entry.flow.amount < 0 for _, entry in entries)
        attribution: dict[int, Decimal] = {}
        path = rollforward.path(
            first, [entry.flow for _, entry in entries], last, opening_relief=attribution
        )
        if any(path["OTHER"][name] != 0 for name in tie_outs.ROLLFORWARD_BALANCES):
            raise tie_outs.invalid(
                "currency_view", "Transaction opening relief requires a reconciled group path."
            )
        if has_reversal:
            # Reproduce all revenue in the group from original signed sources,
            # including the paid history that the reversal removes.
            attribution = {}
            member_ids = {member[0] for member in members}
            for index, (_, entry) in enumerate(entries):
                if not entry.flow.is_revenue:
                    continue
                if entry.line_id is None or entry.entry_kind not in {
                    "REVENUE_RECOGNITION",
                    "INTERCOMPANY",
                }:
                    raise tie_outs.invalid(
                        "currency_view", "Reversal requires original posted revenue sources."
                    )
                try:
                    revenue_id, result = for_control(
                        source_uow, entry.line_id, view="transaction", cache=source_cache
                    )
                except ValueError as error:
                    raise tie_outs.invalid("currency_view", str(error)) from error
                if result.delta.amount != -entry.flow.amount:
                    raise tie_outs.invalid(
                        "currency_view", "Transaction revenue differs from its retained sources."
                    )
                dates = {(owner, layer): created for owner, layer, created in result.layer_dates}
                released = ZERO
                for part in result.delta.movements:
                    if part.contract_id not in member_ids or part.movement_kind not in {
                        "LIABILITY_LAYER_CONSUMED",
                        "LIABILITY_LAYER_CREATED",
                        "ASSET_LAYER_CREATED",
                        "ASSET_LAYER_SETTLED",
                    }:
                        raise tie_outs.invalid(
                            "currency_view",
                            "Reversal source kind or original member ownership is unsupported.",
                        )
                    if part.movement_kind != "LIABILITY_LAYER_CONSUMED":
                        continue
                    created = dates.get((part.contract_id, part.layer_key))
                    if created is None:
                        raise tie_outs.invalid(
                            "currency_view", "Reversal lacks its original layer creation date."
                        )
                    if created < periods[entity][0].start:
                        released -= Decimal(part.amount.numerator) / Decimal(
                            part.amount.denominator
                        )
                attribution[index] = released
                paid_members.update((revenue_id, *result.paid_line_ids))
                paid_members.update(item[0] for item in result.components)
                signed_evidence[str(entry.line_id)] = {
                    "revenue_line_id": str(revenue_id),
                    **(
                        {"gross_control_line_id": str(result.gross_control_id)}
                        if result.gross_control_id is not None
                        else {}
                    ),
                    **(
                        {"counterpart_role": result.components[0][1]}
                        if len(result.components) == 1
                        else {}
                    ),
                    **(
                        {
                            "agent_components": [
                                [str(identity), role, txn, functional]
                                for identity, role, txn, functional in result.components
                            ]
                        }
                        if result.components
                        else {}
                    ),
                    "opening_relief": str(released),
                    "paid_line_ids": list(map(str, result.paid_line_ids)),
                    "source_ids": list(map(str, result.delta.source_ids)),
                    "evidence": [[str(identity), digest] for identity, digest in result.evidence],
                    "layer_dates": [
                        [str(owner), layer, created.isoformat()]
                        for owner, layer, created in result.layer_dates
                    ],
                }
        agent_results = {}
        if use_agent_sources and policies.get(str(entity)) == "FIFO_WITHIN_POB":
            for member in members:
                agent_result = opening_agent_sources.read(
                    source_uow,
                    selected[member],
                    [entry for owner, entry in entries if owner == member],
                    periods[entity][0].start,
                    first["contract_liability"],
                )
                if agent_result is not None:
                    agent_results[member] = agent_result
                    paid_members.update(agent_result.paid_lines)
                    agent_evidence[f"{version}:{entity}:{member[0]}"] = agent_result.evidence
        recognized: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        relief: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        for index, (member, entry) in enumerate(entries):
            if entry.flow.is_revenue:
                recognized[member] += entry.flow.amount
                relief[member] += attribution.get(index, ZERO)
        for member, agent_result in agent_results.items():
            recognized[member] = sum(
                (entry.flow.amount for entry in agent_result.entries if entry.flow.is_revenue), ZERO
            )
        group_identity = f"{version}:{entity}:{currency}"
        membership[group_identity] = sorted(str(member[0]) for member in members)
        if policies.get(str(entity)) == "FIFO_WITHIN_POB":
            previous = before.get(entity)
            frozen = None if previous is None else locked.at(entity, previous)
            consumed = -(
                path["REVENUE_FROM_OPENING"]["contract_liability"]
                + path["REVENUE_FROM_PERIOD_BILLINGS"]["contract_liability"]
            )
            member_facts: dict[str, Any] = {}
            for member in members:
                frozen_row = None
                frozen_facts = None
                if frozen is not None and previous is not None:
                    frozen_row, frozen_facts = frozen_sources.read(
                        row=selected[member],
                        previous=previous,
                        locked=frozen,
                        book=book,
                    )
                pob_amount, facts = opening_relief_pob.calculate(
                    session,
                    selected[member],
                    previous,
                    agent_results[member].entries
                    if member in agent_results
                    else [entry for owner, entry in entries if owner == member],
                    first["contract_liability"],
                    consumed,
                    opening_row=frozen_row,
                    opening_absent=frozen is not None and frozen_row is None,
                    agent_eligible=agent_results[member].eligible
                    if member in agent_results
                    else None,
                    agent_evidence=agent_results[member].evidence
                    if member in agent_results
                    else None,
                )
                if frozen_facts is not None:
                    facts["frozen_opening"] = frozen_facts
                relief[member] = pob_amount
                member_facts[str(member[0])] = facts
            if len(members) == 1:
                pob_evidence[group_identity] = member_facts[str(members[0][0])]
            else:
                # The group cap does not establish a unique member split. Present it once,
                # with the complete member set, rather than inventing individual relief.
                amount = opening_relief_pob.group_total(
                    list(relief[member] for member in members),
                    opening=first["contract_liability"],
                    consumed=consumed,
                )
                for facts in member_facts.values():
                    facts["eligible_relief_capped_by_group"] = facts.pop("relief")
                pob_evidence[group_identity] = {
                    "presentation": "GROUP_TOTAL",
                    "members": member_facts,
                    "opening_cap": str(first["contract_liability"]),
                    "consumption_cap": str(consumed),
                    "relief": str(amount),
                }
                names = sorted(selected[member].external_id for member in members)
                recognized_total = sum((recognized[member] for member in members), ZERO)
                contracts.append(
                    {
                        "_opening_source": {
                            "entity_id": str(entity),
                            "contracts": sorted(str(member[0]) for member in members),
                            "group_key": group_identity,
                        },
                        "row_key": f"combined:{group_identity}",
                        "section": 2,
                        "summary": "Combined contracts (group total): "
                        + "; ".join(names)
                        + ". Member relief is not allocated.",
                        "contract_external_id": None,
                        "customer_name": None,
                        "entity_code": selected[members[0]].entity_code,
                        "currency": currency,
                        "opening_contract_liability": tie_outs.money(
                            first["contract_liability"], currency
                        ),
                        "revenue_recognized": tie_outs.money(recognized_total, currency),
                        "revenue_from_opening": tie_outs.money(amount, currency),
                    }
                )
                group = totals.setdefault(currency, {})
                for name, value in (
                    ("opening", first["contract_liability"]),
                    ("revenue", recognized_total),
                    ("relief", amount),
                ):
                    tie_outs.add(group, name, value)
                continue
        for member in members:
            row = selected[member]
            amount = open_rows[member].value("contract_liability") if member in open_rows else ZERO
            if amount == 0 and recognized[member] == 0 and relief[member] == 0:
                continue
            contracts.append(
                {
                    "_opening_source": {
                        "entity_id": str(entity),
                        "contracts": [str(row.contract_id)],
                        "group_key": group_identity,
                    },
                    "row_key": f"contract:{row.external_id}:{row.entity_code}",
                    "section": 2,
                    "contract_external_id": row.external_id,
                    "customer_name": row.customer_name,
                    "entity_code": row.entity_code,
                    "currency": currency,
                    "opening_contract_liability": tie_outs.money(amount, currency),
                    "revenue_recognized": tie_outs.money(recognized[member], currency),
                    "revenue_from_opening": tie_outs.money(relief[member], currency),
                }
            )
            group = totals.setdefault(currency, {})
            for name, value in (
                ("opening", amount),
                ("revenue", recognized[member]),
                ("relief", relief[member]),
            ):
                tie_outs.add(group, name, value)
    if (
        params.binding is not None
        and params.binding.evidence["opening_relief_groups_v1"] != membership
    ):
        raise tie_outs.invalid(
            "currency_view", "Opening-relief member population differs from retained evidence."
        )
    if params.binding is None or signed_key in params.binding.evidence:
        if params.binding is not None and params.binding.evidence[signed_key] != signed_evidence:
            raise tie_outs.invalid(
                "currency_view", "Transaction reversal sources differ from retained evidence."
            )
        tie_outs.require_members(params, "transaction_revenue_paid_line", paid_members)
        tie_outs.record_members(params, "transaction_revenue_paid_line", paid_members)
        tie_outs.record_evidence(params, signed_key, signed_evidence)
    if use_pob:
        if (
            params.binding is not None
            and params.binding.evidence[opening_relief_pob.KEY] != pob_evidence
        ):
            raise tie_outs.invalid(
                "currency_view", "Per-obligation relief differs from retained evidence."
            )
        tie_outs.record_evidence(params, opening_relief_pob.KEY, pob_evidence)
    if use_agent_sources:
        if (
            params.binding is not None
            and params.binding.evidence[opening_agent_sources.KEY] != agent_evidence
        ):
            raise tie_outs.invalid(
                "currency_view", "Agent net opening sources differ from retained evidence."
            )
        tie_outs.record_evidence(params, opening_agent_sources.KEY, agent_evidence)
    tie_outs.record_evidence(params, "opening_relief_groups_v1", membership)
    contracts.sort(key=lambda row: row["row_key"])
    return finish(
        uow,
        params,
        contracts=contracts,
        totals=totals,
        entities=entities,
        periods=periods,
        book=book,
        view="transaction",
        rates=[],
        source_key=KEY,
        legacy_contract_footnote=not signed_evidence
        and all(len(members) == 1 for members in groups.values()),
        signed_reversals=bool(signed_evidence),
        per_obligation="FIFO_WITHIN_POB" in policies.values(),
    )
