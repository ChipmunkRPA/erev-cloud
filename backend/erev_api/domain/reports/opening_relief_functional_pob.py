"""Functional POB disclosure from original openings and selected-range posted control revenue."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from erev_api.domain.reports import (
    opening_agent_sources,
    opening_relief_frozen,
    opening_relief_pob,
    tie_outs,
)
from erev_api.domain.reports import (
    opening_relief_availability as availability,
)
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
    from .opening_intercompany import Reader as IntercompanyReader

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
    intercompany_reader = IntercompanyReader(source_uow, params, "functional")
    frozen_sources = opening_relief_frozen.Reader(source_uow, params)
    agent_key = opening_agent_sources.key_for(
        None if params.binding is None else params.binding.evidence
    )
    use_agent_sources = params.binding is None or agent_key != opening_agent_sources.LEGACY_KEY
    from .opening_agent_postings import read as net_postings

    all_net = (
        net_postings(source_uow, params, book, periods, view="functional")
        if use_agent_sources
        else {}
    )
    agent_evidence: dict[str, Any] = {}
    paid_members: set[UUID] = set()
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
        # A net-zero range can hide positive relief followed by reversal at another FX rate.
        # Reporting may omit POB openings only when every period has no positive consumption.
        zero_consumption_safe = reporting_slices is None or all(
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
        )
        group_entries: list[rollforward.Entry] = []
        source_eligibility: dict[str, list[rollforward.Entry]] = {}
        recognized = ZERO
        eligible = []
        facts = {}
        previous = before.get(entity)
        frozen = None if previous is None else locked.at(entity, previous)
        for item in members:
            key = (item.contract_id, item.entity_id)
            source = sources[key]
            entries: Sequence[rollforward.Entry] = posted.get(key, ())
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
            agent_result = (
                opening_agent_sources.read(
                    source_uow,
                    source,
                    list(entries),
                    periods[entity][0].start,
                    opening,
                    view="functional",
                    net_entries=all_net.get(key, []),
                    allow_unresolved=availability.enabled(params),
                    allow_historical_owners=opening_agent_sources.historical_enabled(params),
                    allow_contracting_revenue=opening_agent_sources.contracting_enabled(params),
                    allowed_source_contracts={member.contract_id for member in members}
                    if agent_key == opening_agent_sources.KEY
                    else None,
                    classify_opening=agent_key != opening_agent_sources.KEY
                    or not (zero_consumption_safe and consumed <= ZERO),
                )
                if use_agent_sources
                else None
            )
            if agent_result is not None:
                entries = agent_result.entries
                member_revenue = sum(
                    (entry.flow.amount for entry in entries if entry.flow.is_revenue), ZERO
                )
                paid_members.update(agent_result.paid_lines)
                agent_evidence[f"{version}:{entity}:{item.contract_id}"] = agent_result.evidence
                for subject in agent_result.eligible:
                    source_eligibility[subject] = [
                        entry
                        for entry in agent_result.opening_entries
                        if entry.subject_key == subject
                    ]
            group_entries.extend(entries)
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
                intercompany_reader=intercompany_reader,
                opening_absent=frozen is not None and original is None,
                functional_currency=currency,
                allow_zero_consumption=zero_consumption_safe,
                agent_eligible=agent_result.eligible if agent_result is not None else None,
                agent_evidence=agent_result.evidence if agent_result is not None else None,
                agent_unresolved=agent_result.unresolved if agent_result is not None else None,
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
        availability.mask_facts(evidence[group_key])
        uncertain = availability.unresolved(evidence[group_key])
        if reporting_slices is not None:
            from .opening_relief_periods import deltas

            period_amounts = (
                {p.id: ZERO for p in periods[entity]}
                if uncertain
                else deltas(
                    periods=[p.id for p in periods[entity]],
                    opening=opening,
                    obligations={
                        subject: Decimal(detail.get("opening_billing", "0"))
                        - Decimal(detail.get("opening_revenue", "0"))
                        for member in facts.values()
                        for subject, detail in member["obligations"].items()
                    },
                    entries=group_entries,
                    source_eligibility=source_eligibility,
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
            )
            evidence[group_key]["period_relief"] = {
                p.key: None if uncertain else str(period_amounts[p.id]) for p in periods[entity]
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
            if source_eligibility:
                net_periods = {
                    p.id: sum(
                        (
                            entry.flow.amount
                            for entry in group_entries
                            if entry.flow.is_revenue and entry.period_id == p.id
                        ),
                        ZERO,
                    )
                    for p in periods[entity]
                }
                evidence[group_key]["period_net_revenue"] = {
                    p.key: str(net_periods[p.id]) for p in periods[entity]
                }
                reporting_slices[group_key]["net_revenue"] = net_periods
        if opening == recognized == amount == 0 and (
            reporting_slices is None or not any(period_amounts.values())
        ):
            continue
        combined = len(members) > 1
        first = members[0]
        result.append(
            {
                **({"_opening_unavailable": uncertain} if uncertain else {}),
                "_opening_source": {
                    "entity_id": str(entity),
                    "contracts": sorted(str(item.contract_id) for item in members),
                    "group_key": group_key,
                },
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
    if use_agent_sources:
        if params.binding is not None and params.binding.evidence[agent_key] != agent_evidence:
            raise tie_outs.invalid(
                "currency_view", "Agent net functional sources differ from retained evidence."
            )
        tie_outs.record_evidence(params, agent_key, agent_evidence)
        tie_outs.require_members(params, "agent_net_paid_line", paid_members)
        tie_outs.record_members(params, "agent_net_paid_line", paid_members)
    if params.binding is not None and params.binding.evidence[evidence_key] != evidence:
        raise tie_outs.invalid(
            "currency_view", "Functional POB sources differ from retained evidence."
        )
    tie_outs.record_evidence(params, evidence_key, evidence)
    intercompany_reader.retain()
    return result, excluded
