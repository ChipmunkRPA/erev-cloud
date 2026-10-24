"""Original acquisition-period carrying balances, retained with report inputs.

Cutovers are period ends. Their admitted opening-balance method establishes a new
balance, not an invoice or current-period revenue. Read its original computation
input and output together; never infer the increase from an unexplained residual.
"""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract_event
from erev_api.domain.reports import acquisition_evidence, acquisition_native, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.uow import UnitOfWork
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import PolicyResolver

KEY = "acquisition_rollforward_sources_v1"
FAMILY = "ACQUISITION"
RECOMPUTED_KEY = "acquisition_recomputed_sources_v1"
NATIVE_KEY = "acquisition_native_cutover_sources_v1"


def read(
    uow: UnitOfWork,
    params: ReportParams,
    rows: Mapping[tuple[UUID, UUID], tie_outs.BalanceRow],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    book: str,
    *,
    functional: bool,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    if params.binding is not None and KEY not in params.binding.evidence:
        return {}  # Historical runs retain their original interpretation.
    allow_recomputed = params.binding is None or bool(params.binding.evidence.get(RECOMPUTED_KEY))
    allow_native = params.binding is None or bool(params.binding.evidence.get(NATIVE_KEY))
    admitted_methods = {"OPENING_BALANCES_AT_CUTOVER"}
    if allow_recomputed:
        admitted_methods.add("RECOMPUTE_FROM_INCEPTION")
    candidates = set(
        uow.session.execute(
            select(contract_event.c.contract_id).where(
                contract_event.c.contract_id.in_([key[0] for key in rows]),
                contract_event.c.event_type == "OPENING_BALANCE_ESTABLISHED",
                contract_event.c.payload["reason"].astext == "BUSINESS_COMBINATION",
            )
        ).scalars()
    )
    captured: dict[str, Any] = {}
    result: dict[tuple[UUID, UUID], list[Entry]] = {}
    cached = {}
    for key, row in rows.items():
        if row.contract_id not in candidates:
            continue
        selected_periods = periods.get(row.entity_id, ())
        if not selected_periods:
            continue
        if row.version_id not in cached:
            cached[row.version_id] = acquisition_evidence.load(uow, row.version_id, book)
        bundle, output, source = cached[row.version_id]
        original_book = next(b for b in bundle.books if b.book_code == book)
        voided = {e.supersedes_event_key for e in bundle.events if e.event_type == "EVENT_VOIDED"}
        method = PolicyResolver(original_book.policies).resolved(
            "onboarding.method", contract=row.external_id
        )
        if method.value not in admitted_methods:
            continue
        openings = [
            event
            for event in bundle.events
            if event.contract_key == row.external_id
            and event.event_key not in voided
            and event.event_type == "OPENING_BALANCE_ESTABLISHED"
            and event.payload.get("reason") == "BUSINESS_COMBINATION"
        ]
        if not openings:
            continue
        if len(openings) != 1:
            raise tie_outs.invalid("currency_view", "Acquisition opening source is ambiguous.")
        event = openings[0]
        cutover = date.fromisoformat(str(event.payload["cutover_date"]))
        period = next((p for p in selected_periods if p.start <= cutover <= p.end), None)
        if period is None:
            continue
        if cutover != period.end:
            raise tie_outs.invalid("currency_view", "Acquisition cutover must be a period end.")
        if any(c.contracting_entity_code != row.entity_code for c in bundle.contracts) or any(
            p.principal_agent != "PRINCIPAL" for p in bundle.group.products
        ):
            raise tie_outs.invalid(
                "currency_view",
                "Acquired agent or cross-entity sources require explicit attribution.",
            )
        # No ordinary member's prior business may be mislabeled an acquisition.
        acquired_members = {
            e.contract_key
            for e in bundle.events
            if e.event_type == "OPENING_BALANCE_ESTABLISHED"
            and e.event_key not in voided
            and e.payload.get("reason") == "BUSINESS_COMBINATION"
            and e.payload.get("cutover_date") == cutover.isoformat()
        }
        if acquired_members != set(bundle.group.member_contract_keys) or any(
            PolicyResolver(original_book.policies)
            .resolved("onboarding.method", contract=member)
            .value
            not in admitted_methods
            for member in acquired_members
        ):
            raise tie_outs.invalid(
                "currency_view",
                "Mixed acquired and existing group members require explicit attribution.",
            )
        original_output = next(b for b in output["books"] if b["book_code"] == book)
        nodes = {n["id"]: n for n in original_output["trace"]["nodes"]}
        prefix = f"opening_revenue_cum@{event.event_key}:"
        if not any(identity.startswith(prefix) for identity in nodes):
            raise tie_outs.invalid(
                "currency_view", "Acquisition opening was not admitted by the original computation."
            )
        subject = contract_entity_subject_key(row.external_id, row.entity_code)
        entity = next(e for e in bundle.entities if e.code == row.entity_code)
        foreign = functional and entity.functional_currency != row.currency
        currency = entity.functional_currency if functional else row.currency
        identities = [
            f"{role}{'_functional' if foreign else ''}:{subject}:{period.key}"
            for role in tie_outs.ROLLFORWARD_BALANCES
        ]
        native = None
        if (
            allow_native
            and method.value == "RECOMPUTE_FROM_INCEPTION"
            and not any(identity in nodes for identity in identities)
        ):
            native = acquisition_native.single_member_cutover(
                bundle,
                output,
                member=row.external_id,
                book=book,
                entity=row.entity_code,
                period=period,
                functional=functional,
            )
        if (
            native is None
            and allow_native
            and foreign
            and not any(identity in nodes for identity in identities)
            and method.value == "RECOMPUTE_FROM_INCEPTION"
        ):
            from .acquisition_complete import read as complete_balances

            complete = complete_balances(
                bundle,
                output,
                member=row.external_id,
                entity=row.entity_code,
                book=book,
                period=period,
                event_key=event.event_key,
            )
            if complete is not None:
                _, observation = complete
                fn = observation["functional"]
                scale = Decimal(10) ** -fn["minor_unit"]
                values = {
                    role: Decimal(fn["amounts"][role]) * scale
                    for role in tie_outs.ROLLFORWARD_BALANCES
                }
                native = (
                    values,
                    {
                        "basis": observation["basis"],
                        "currency": fn["currency"],
                        "period_key": observation["period_key"],
                        "event_key": event.event_key,
                        "nodes": sorted(
                            fn["nodes"][role] for role in tie_outs.ROLLFORWARD_BALANCES
                        ),
                        "amounts": {role: str(value) for role, value in values.items()},
                    },
                )
        amounts: dict[str, Decimal] = {}
        inputs = []
        if native is not None:
            amounts, snapshot = native
            if snapshot["currency"] != currency:
                raise tie_outs.invalid("currency_view", "Acquisition native currency differs.")
            inputs = snapshot["nodes"]
        else:
            for role, identity in zip(tie_outs.ROLLFORWARD_BALANCES, identities, strict=True):
                node = nodes.get(identity)
                if node is None or node["currency"] != currency:
                    raise tie_outs.invalid(
                        "currency_view", "Acquisition lacks original cutover balance evidence."
                    )
                amount = Decimal(node["value"])
                if not amount.is_finite() or amount < 0:
                    raise tie_outs.invalid(
                        "currency_view", "Acquisition carrying balance is invalid."
                    )
                amounts[role] = amount
                inputs.append(identity)
        identity = f"{row.version_id}:{row.contract_id}:{row.entity_id}:{period.key}"
        captured[identity] = {
            "event_key": event.event_key,
            "input_sha256": source["input_sha256"],
            "output_sha256": source["output_sha256"],
            "currency": currency,
            "nodes": inputs,
            "amounts": {k: str(v) for k, v in amounts.items()},
        }
        if native is not None:
            captured[identity]["native_cutover"] = native[1]
        result[key] = [
            Entry(
                (cutover, -1, event.event_key),
                Flow(
                    Decimal(0),
                    False,
                    FAMILY,
                    acquisition_balances=tuple(sorted(amounts.items())),
                    acquisition_includes_prior=method.value == "RECOMPUTE_FROM_INCEPTION",
                ),
                period_id=period.id,
            )
        ]
    if params.binding is not None and params.binding.evidence[KEY] != captured:
        raise tie_outs.invalid("currency_view", "Retained acquisition sources differ.")
    tie_outs.record_evidence(params, KEY, captured)
    if allow_recomputed:
        tie_outs.record_evidence(params, RECOMPUTED_KEY, True)
    if allow_native:
        tie_outs.record_evidence(params, NATIVE_KEY, True)
    return result
