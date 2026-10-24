"""Transaction POL-126 disclosure from attributed opening billing and posted POB revenue."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract_event, obligation, obligation_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry
from erev_api.explain import store
from erev_engine.stages.s01_canonicalize import obligation_subject_key

from .opening_intercompany import Reader as IntercompanyReader

KEY = "opening_relief_pob_v1"
ZERO = Decimal(0)


def _new_after_opening(
    session: Session,
    row: tie_outs.BalanceRow,
    previous: tie_outs.PeriodRef | None,
    missing: set[str],
) -> dict[str, dict[str, str]]:
    """Prove new ADD identities from the selected version and their immutable creating event.

    A regrouped/replaced obligation can inherit history and is deliberately not a new opening.
    """
    if not missing or previous is None or getattr(previous, "end", None) is None:
        return {}
    rows = (
        session.execute(
            select(
                obligation.c.obligation_key,
                contract_event.c.id.label("event_id"),
                contract_event.c.effective_date,
                contract_event.c.payload,
            )
            .select_from(
                obligation_version.join(
                    obligation,
                    (obligation.c.id == obligation_version.c.obligation_id)
                    & (obligation.c.tenant_id == obligation_version.c.tenant_id),
                ).join(
                    contract_event,
                    (contract_event.c.id == obligation.c.created_by_event_id)
                    & (contract_event.c.tenant_id == obligation.c.tenant_id),
                )
            )
            .where(
                obligation_version.c.contract_version_id == row.version_id,
                obligation.c.contract_id == row.contract_id,
                contract_event.c.contract_id == row.contract_id,
                contract_event.c.event_type == "CONTRACT_AMENDED",
                contract_event.c.effective_date > previous.end,
                obligation.c.parent_obligation_id.is_(None),
                obligation.c.regrouped_from_obligation_id.is_(None),
            )
        )
        .mappings()
        .all()
    )
    found = {}
    for item in rows:
        key = item["obligation_key"]
        subject = obligation_subject_key(row.external_id, key)
        if subject not in missing or not any(
            line.get("action") == "ADD" and line.get("obligation_key") == key
            for line in item["payload"].get("lines", [])
        ):
            continue
        found[subject] = {
            "basis": "CREATED_AFTER_OPENING",
            "event_id": str(item["event_id"]),
            "effective_date": item["effective_date"].isoformat(),
        }
    return found


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
    functional_currency: str | None = None,
    allow_zero_consumption: bool = True,
    agent_eligible: Mapping[str, Decimal] | None = None,
    agent_evidence: Mapping[str, Any] | None = None,
    agent_unresolved: set[str] | None = None,
    intercompany_reader: IntercompanyReader | None = None,
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
    special = any(
        item["performing_entity_id"] != row.entity_id or str(item["principal_agent"]) != "PRINCIPAL"
        for item in obligations
    )
    intercompany = (
        intercompany_reader.read(row, obligations, entries)
        if intercompany_reader is not None
        else {}
    )
    supported_special = all(
        (
            item["performing_entity_id"] == row.entity_id
            or obligation_subject_key(row.external_id, item["obligation_key"]) in intercompany
        )
        and (
            str(item["principal_agent"]) == "PRINCIPAL"
            or (
                str(item["principal_agent"]) == "AGENT"
                and agent_eligible is not None
                and obligation_subject_key(row.external_id, item["obligation_key"])
                in agent_eligible
            )
        )
        for item in obligations
    )
    zero_special_consumption = allow_zero_consumption and consumed <= 0 and special
    # A reconciled zero group opening cannot contribute opening relief in any
    # currency. Preserve the established principal transaction evidence shape.
    zero_group_opening = opening <= 0 and (functional_currency is not None or special)
    zero_cap = zero_group_opening or zero_special_consumption
    if not obligations or (not zero_cap and special and not supported_special):
        raise tie_outs.invalid(
            "currency_view",
            "Per-obligation opening relief requires same-entity principal obligations or "
            "verified agent net or intercompany control sources; "
            "other special attribution remains unsupported.",
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
        original_intercompany = (
            intercompany_reader.read(source, prior_obligations, [])
            if intercompany_reader is not None
            else {}
        )
        if not prior_obligations or (
            not zero_cap
            and any(
                (
                    item["performing_entity_id"] != row.entity_id
                    and obligation_subject_key(row.external_id, item["obligation_key"])
                    not in original_intercompany
                )
                or (
                    str(item["principal_agent"]) != "PRINCIPAL"
                    and (
                        str(item["principal_agent"]) != "AGENT"
                        or agent_eligible is None
                        or obligation_subject_key(row.external_id, item["obligation_key"])
                        not in agent_eligible
                    )
                )
                for item in prior_obligations
            )
        ):
            raise tie_outs.invalid(
                "currency_view", "The original opening obligations need special attribution."
            )
        opening_subjects = {
            obligation_subject_key(row.external_id, item["obligation_key"])
            for item in prior_obligations
        }
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
    if zero_cap:
        return ZERO, {
            "version": str(row.version_id),
            "opening_period": None if previous is None else previous.key,
            "posted_lines": sorted(posted),
            "obligations": {
                subject: {
                    "posted_revenue": str(value),
                    **(
                        {"agent_net_sources": agent_evidence[subject]}
                        if agent_evidence is not None and subject in agent_evidence
                        else {}
                    ),
                }
                for subject, value in sorted(recognized.items())
            },
            "opening_cap": str(opening),
            "consumption_cap": str(consumed),
            "relief": "0",
            "basis": "ZERO_GROUP_OPENING" if zero_group_opening else "ZERO_CONSUMPTION",
        }
    trace = store.load_trace(session, source.version_id)
    if trace is None:
        raise tie_outs.invalid("currency_view", "Per-obligation opening relief requires a trace.")
    nodes = {node.id: node for node in trace.nodes}
    missing = {
        subject
        for subject in opening_subjects
        if previous is not None
        and any(
            f"{measure}:{subject}:{previous.key}" not in nodes
            for measure in ("billed_cum", "revenue_cum")
        )
    }
    new = _new_after_opening(session, source, previous, missing)
    for subject in new:
        assert previous is not None
        for measure in ("billed_cum", "revenue_cum"):
            node = nodes.get(f"{measure}:{subject}:{previous.key}")
            if node is not None and (node.currency != row.currency or Decimal(node.value) != ZERO):
                raise tie_outs.invalid(
                    "currency_view", "New obligation has conflicting opening evidence."
                )
    opening_subjects = opening_subjects - set(new)
    facts: dict[str, Any] = {}
    formula = ZERO
    unresolved_subjects: list[str] = []
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
        if (
            functional_currency is not None
            and functional_currency != row.currency
            and previous is not None
            and subject in opening_subjects
        ):
            from .opening_pob_functional_nodes import read as functional_opening

            billed, revenue, functional_inputs = functional_opening(
                nodes,
                subject=subject,
                period=previous,
                txn_currency=row.currency,
                currency=functional_currency,
                billed=billed,
                revenue=revenue,
            )
            inputs.extend(functional_inputs)
        liability = max(ZERO, billed - revenue)
        contribution = min(liability, max(ZERO, recognized[subject]))
        if agent_eligible is not None and subject in agent_eligible:
            contribution = min(contribution, max(ZERO, agent_eligible[subject]))
        uncertain = (
            subject in (agent_unresolved or set())
            and liability > ZERO
            and (recognized[subject] > ZERO or not allow_zero_consumption)
        )
        if uncertain:
            unresolved_subjects.append(subject)
        formula += contribution
        facts[subject] = {
            "opening_nodes": inputs,
            "opening_billing": str(billed),
            "opening_revenue": str(revenue),
            "posted_revenue": str(recognized[subject]),
            **({"intercompany_sources": intercompany[subject]} if subject in intercompany else {}),
            "eligible_relief": None if uncertain else str(contribution),
            **({"opening_absence": new[subject]} if subject in new else {}),
            **(
                {"agent_net_sources": agent_evidence[subject]}
                if agent_evidence is not None and subject in agent_evidence
                else {}
            ),
        }
    result = min(max(ZERO, opening), max(ZERO, consumed), formula)
    return result, {
        "version": str(row.version_id),
        "opening_period": None if previous is None else previous.key,
        "posted_lines": sorted(posted),
        "obligations": facts,
        "opening_cap": str(opening),
        "consumption_cap": str(consumed),
        "relief": None if unresolved_subjects else str(result),
        **({"unresolved_subjects": unresolved_subjects} if unresolved_subjects else {}),
    }


def group_total(eligible: Sequence[Decimal], *, opening: Decimal, consumed: Decimal) -> Decimal:
    """Apply the group cap once; it provides no authority to allocate member relief."""
    return min(max(ZERO, opening), max(ZERO, consumed), sum(eligible, ZERO))
