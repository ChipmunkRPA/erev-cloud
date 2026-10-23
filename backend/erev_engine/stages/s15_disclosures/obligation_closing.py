"""Capture original closing eligibility and sources; never allocate the group liability."""

from typing import Any

from erev_engine.bundle import PeriodInput
from erev_engine.stages.state import AllocatedState, BookContext

from .rollforward import BalanceInputs, _entered


def capture(
    ctx: BookContext,
    st: AllocatedState,
    records: BalanceInputs,
    entity: str,
    period: PeriodInput,
    *,
    functional: bool,
) -> dict[str, Any]:
    def unavailable(reason: str) -> dict[str, Any]:
        return {"status": "UNAVAILABLE", "reason": reason}

    own = [ob for ob in st.obligations if ob.contracting_entity == entity]
    if any(
        ob.performing_entity != entity
        or ob.principal_agent.value != "PRINCIPAL"
        or ob.opening is not None
        for ob in own
    ):
        return unavailable("Original principal, same-entity sources are required.")
    subjects = {ob.subject_key for ob in own}
    billed = dict.fromkeys(subjects, 0)
    revenue = dict.fromkeys(subjects, 0)
    sources: dict[str, set[str]] = {subject: set() for subject in subjects}
    documents: dict[tuple[str, str], int] = {}
    for flow in records.flows:
        when = _entered(flow)
        if flow.entity != entity or when is None or when > period.end_date:
            continue
        if flow.kind in {"BILLING", "CREDIT_MEMO"}:
            shares = records.attribution.get(flow.source_key, {})
            sign = 1 if flow.kind == "BILLING" else -1
            if not shares or sum(shares.values()) != sign * flow.amount:
                return unavailable("Billing lacks complete original document attribution.")
            for subject, amount in shares.items():
                key = (flow.source_key, subject)
                if subject not in subjects or key in documents:
                    return unavailable("Billing attribution has duplicate or unknown sources.")
                documents[key] = amount
                billed[subject] += amount
                sources[subject].add(flow.source_key)
        elif flow.kind in {"REVENUE", "NEGATIVE_REVENUE"}:
            if flow.subject_key not in subjects:
                return unavailable("Revenue has an unknown obligation source.")
            revenue[flow.subject_key] += flow.amount * (1 if flow.kind == "REVENUE" else -1)
            sources[flow.subject_key].add(flow.source_key)
    if functional:
        fx = records.fx
        if fx is None:
            return unavailable("Original functional sources are unavailable.")
        original = {}
        for item in fx.billing_attribution_sources:
            if item.entity != entity or item.period_key > period.period_key:
                continue
            key = (item.source_key, item.subject_key)
            if key in original:
                return unavailable("Functional billing has duplicate sources.")
            original[key] = item
        if set(original) != set(documents):
            return unavailable("Functional billing population differs from original documents.")
        billed = dict.fromkeys(subjects, 0)
        for key, amount in documents.items():
            item = original[key]
            if item.amount_txn != amount:
                return unavailable(
                    "Functional billing differs from original transaction quantities."
                )
            billed[item.subject_key] += item.amount_functional
            sources[item.subject_key].add(item.node_id)
        for subject in subjects:
            targets = [
                target
                for target in fx.functional_targets
                if target.entity == entity
                and target.subject_key == subject
                and target.measure == "revenue_cum"
                and target.period_key <= period.period_key
            ]
            if not targets:
                if revenue[subject] != 0:
                    return unavailable("Functional revenue is missing original sources.")
                continue
            latest = max(targets, key=lambda target: target.period_key)
            if (
                sum(target.period_key == latest.period_key for target in targets) != 1
                or latest.amount_txn != revenue[subject]
                or latest.txn_currency != ctx.txn_currency
                or latest.functional_currency != ctx.entities[entity].functional_currency
            ):
                return unavailable("Functional revenue does not reconcile to original quantities.")
            revenue[subject] = latest.amount_functional
            sources[subject].add(f"revenue_functional:{subject}:{latest.period_key}")
    return {
        "status": "AVAILABLE",
        "basis": "OBLIGATION_ELIGIBILITY_BEFORE_GROUP_CAP",
        "obligations": {
            subject: {
                "billed": billed[subject],
                "revenue": revenue[subject],
                "liability": max(0, billed[subject] - revenue[subject]),
                "sources": sorted(sources[subject]),
            }
            for subject in sorted(subjects)
        },
    }
