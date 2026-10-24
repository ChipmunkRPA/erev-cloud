"""Missing ordinary cutover balances read from authenticated native snapshots."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract_event
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import PolicyResolver

from . import acquisition_evidence, acquisition_native, tie_outs
from .builders import ReportParams

KEY = "acquisition_cutover_balances_v1"


def read(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    row: Mapping[str, Any],
    entity: str,
    period: tie_outs.PeriodRef,
    book: str,
    traced: tie_outs.TracedBalances,
) -> dict[str, Decimal] | None:
    if params.binding is not None and not params.binding.evidence.get(KEY):
        return None
    tie_outs.record_evidence(params, KEY, True)
    member = str(row["external_id"])
    subject = contract_entity_subject_key(member, entity)
    if any(
        any(key == period.key for key, _ in traced.nodes.get(f"{role}:{subject}", ()))
        for role in tie_outs.ROLLFORWARD_BALANCES
    ):
        return None
    candidate = uow.session.execute(
        select(contract_event.c.id)
        .where(
            contract_event.c.contract_id == row["contract_id"],
            contract_event.c.event_type == "OPENING_BALANCE_ESTABLISHED",
            contract_event.c.payload["reason"].astext == "BUSINESS_COMBINATION",
            contract_event.c.payload["cutover_date"].astext <= period.end.isoformat(),
        )
        .limit(1)
    ).first()
    if candidate is None:
        return None
    version = UUID(str(row["contract_version_id"]))
    bundle, output, source = acquisition_evidence.load(uow, version, book)
    voided = {
        event.supersedes_event_key for event in bundle.events if event.event_type == "EVENT_VOIDED"
    }
    original_book = next(item for item in bundle.books if item.book_code == book)
    if (
        PolicyResolver(original_book.policies).resolved("onboarding.method", contract=member).value
        != "RECOMPUTE_FROM_INCEPTION"
    ):
        return None
    openings = [
        event
        for event in bundle.events
        if event.event_key not in voided
        and event.contract_key == member
        and event.event_type == "OPENING_BALANCE_ESTABLISHED"
        and event.payload.get("reason") == "BUSINESS_COMBINATION"
        and str(event.payload.get("cutover_date")) <= period.end.isoformat()
    ]
    if not openings:
        return None
    if len(openings) != 1:
        raise tie_outs.invalid("currency_view", "Acquisition balance source is ambiguous.")
    cutover = date.fromisoformat(str(openings[0].payload["cutover_date"]))
    original_entity = next(item for item in bundle.entities if item.code == entity)
    anchor = next((item for item in original_entity.periods if item.end_date == cutover), None)
    if anchor is None:
        raise tie_outs.invalid("currency_view", "Acquisition cutover period is unavailable.")
    # Preserve the ordinary last-observation rule after cutover, but never carry a
    # pre-acquisition zero over the new original observation. A later ordinary
    # measurement wins; the retained snapshot states its actual measurement date.
    if any(
        any(
            anchor.period_key <= key <= period.key
            for key, _ in traced.nodes.get(f"{role}:{subject}", ())
        )
        for role in tie_outs.ROLLFORWARD_BALANCES
    ):
        return None
    source_period = replace(
        period, key=anchor.period_key, start=anchor.start_date, end=anchor.end_date
    )
    native = acquisition_native.single_member_cutover(
        bundle,
        output,
        member=member,
        book=book,
        entity=entity,
        period=source_period,
        functional=False,
        include_current=True,
    )
    if native is None:
        raise tie_outs.invalid(
            "currency_view", f"{member}: original acquisition cutover balance is unavailable."
        )
    amounts, snapshot = native
    if snapshot["currency"] != str(row["txn_currency"]).strip():
        raise tie_outs.invalid("currency_view", "Acquisition balance currency differs.")
    captured = {
        "input_sha256": source["input_sha256"],
        "output_sha256": source["output_sha256"],
        "snapshot": snapshot,
        "requested_period_key": period.key,
        "amounts": {key: str(value) for key, value in amounts.items()},
    }
    identity = f"{KEY}:{version}:{row['contract_id']}:{row['entity_id']}:{period.key}"
    if params.binding is not None and params.binding.evidence.get(identity) != captured:
        raise tie_outs.invalid("currency_view", "Retained acquisition balance sources differ.")
    tie_outs.record_evidence(params, identity, captured)
    return amounts
