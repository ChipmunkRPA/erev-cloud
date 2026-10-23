"""Transaction POL-126 disclosure from attributed opening billing and posted POB revenue."""

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import obligation_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry
from erev_api.explain import store
from erev_engine.stages.s01_canonicalize import obligation_subject_key

KEY = "opening_relief_pob_v1"
ZERO = Decimal(0)


def calculate(
    session: Session,
    row: tie_outs.BalanceRow,
    previous: tie_outs.PeriodRef | None,
    entries: Sequence[Entry],
    opening: Decimal,
    consumed: Decimal,
    *,
    opening_row: tie_outs.BalanceRow | None = None,
    opening_absent: bool = False,
) -> tuple[Decimal, dict[str, Any]]:
    """Eligibility for one member, using the selected version and selected posting range.

    Locked openings must supply the authenticated lock-time source row, or proven absence.
    A range is evaluated once, never as a sum of monthly opening-consumption disclosures.
    """
    obligations = (
        session.execute(
            select(obligation_version).where(
                obligation_version.c.contract_version_id == row.version_id,
                obligation_version.c.contract_id == row.contract_id,
                obligation_version.c.contracting_entity_id == row.entity_id,
            )
        )
        .mappings()
        .all()
    )
    if not obligations or any(
        item["performing_entity_id"] != row.entity_id or str(item["principal_agent"]) != "PRINCIPAL"
        for item in obligations
    ):
        raise tie_outs.invalid(
            "currency_view",
            "Per-obligation opening relief requires principal obligations performed by the "
            "contracting entity; cross-entity and agent attribution remain unsupported.",
        )
    subjects = {
        obligation_subject_key(row.external_id, item["obligation_key"]) for item in obligations
    }
    source = opening_row or row
    opening_subjects = subjects
    if opening_absent:
        opening_subjects = set()
    elif source.version_id != row.version_id:
        prior_obligations = (
            session.execute(
                select(obligation_version).where(
                    obligation_version.c.contract_version_id == source.version_id,
                    obligation_version.c.contract_id == row.contract_id,
                    obligation_version.c.contracting_entity_id == row.entity_id,
                )
            )
            .mappings()
            .all()
        )
        if not prior_obligations or any(
            item["performing_entity_id"] != row.entity_id
            or str(item["principal_agent"]) != "PRINCIPAL"
            for item in prior_obligations
        ):
            raise tie_outs.invalid(
                "currency_view", "The original opening obligations need special attribution."
            )
        opening_subjects = {
            obligation_subject_key(row.external_id, item["obligation_key"])
            for item in prior_obligations
        }
    trace = store.load_trace(session, source.version_id)
    if trace is None:
        raise tie_outs.invalid("currency_view", "Per-obligation opening relief requires a trace.")
    nodes = {node.id: node for node in trace.nodes}
    recognized: dict[str, Decimal] = defaultdict(Decimal)
    posted: list[str] = []
    for entry in entries:
        if not entry.flow.is_revenue:
            continue
        if entry.subject_key not in subjects | opening_subjects or entry.line_id is None:
            raise tie_outs.invalid(
                "currency_view", "Posted relief does not identify a retained obligation."
            )
        recognized[entry.subject_key] += entry.flow.amount
        posted.append(str(entry.line_id))
    facts: dict[str, Any] = {}
    formula = ZERO
    for subject in sorted(subjects | opening_subjects):
        billed = revenue = ZERO
        inputs: list[str] = []
        if previous is not None and subject in opening_subjects:
            for measure in ("billed_cum", "revenue_cum"):
                identity = f"{measure}:{subject}:{previous.key}"
                node = nodes.get(identity)
                if node is None:
                    raise tie_outs.invalid(
                        "currency_view",
                        f"Per-obligation opening relief lacks {identity}; recompute the contract.",
                    )
                if node.currency != row.currency:
                    raise tie_outs.invalid("currency_view", "Opening POB currency differs.")
                inputs.append(identity)
                if measure == "billed_cum":
                    billed = Decimal(node.value)
                else:
                    revenue = Decimal(node.value)
        liability = max(ZERO, billed - revenue)
        contribution = min(liability, max(ZERO, recognized[subject]))
        formula += contribution
        facts[subject] = {
            "opening_nodes": inputs,
            "opening_billing": str(billed),
            "opening_revenue": str(revenue),
            "posted_revenue": str(recognized[subject]),
            "eligible_relief": str(contribution),
        }
    result = min(max(ZERO, opening), max(ZERO, consumed), formula)
    return result, {
        "version": str(row.version_id),
        "opening_period": None if previous is None else previous.key,
        "posted_lines": sorted(posted),
        "obligations": facts,
        "opening_cap": str(opening),
        "consumption_cap": str(consumed),
        "relief": str(result),
    }


def group_total(eligible: Sequence[Decimal], *, opening: Decimal, consumed: Decimal) -> Decimal:
    """Apply the group cap once; it provides no authority to allocate member relief."""
    return min(max(ZERO, opening), max(ZERO, consumed), sum(eligible, ZERO))
