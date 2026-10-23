"""RPT-30 ``scope_exclusion_register`` Scope exclusion register (SCREENS_B §5.6.2 RPT-30; 04
T-CON-08, T-CON-11, T-CON-19, E-77; ENGINE_SPEC S03-R-11, S04-R-03; POLICIES PT-09; PRD §2.10 BR-06,
RB-06; 03 REQ-RPT-023, REQ-CON-016; BUILD_SPEC RPS-11).

One row per obligation version whose ``scope_flag`` is not ``IN_SCOPE_606`` in the latest contract
version of each combination group effective on or before the end of ``period_key`` (default: the
context period) — the ``latest_contract_status`` selection — for the run's entities and book. Rows
are ordered by contract and obligation; ``row_key`` ``obligation:<external id>:<key>``.

- ``out_of_scope_amount`` is the amount the version keeps out of Topic 606, in the contract's
  transaction currency: the allocation of a ``LEASE_842`` obligation, which stays an allocation
  target and whose allocation the transaction price excludes (PT-09; S03-R-11); for any other
  flag the contract version's ``out_of_scope_amount`` when the version holds one routed-out line,
  and an empty cell when it holds several (T-CON-11 carries no amount per excluded line; the
  total is never apportioned).
- ``judgement_no`` and ``rationale`` come from the judgement record on the obligation — the
  latest one that is neither rejected nor superseded — and are empty without one.
- ``effective_date`` is the listed obligation version's.

Control totals ``row_count``, ``out_of_scope_amount_total`` per currency and the ``as_of`` date
(per entity calendar the end of the period; the first entity's in the totals). ``currency_view``
``transaction`` is served; another view only when every row's currency is its entity's functional
currency, else refused by name. Reporting adds separately labelled equivalents at the report-period
closing rate; these amounts are not carrying balances. Saved runs retain amount, judgement and rate
inputs for reconstruction. A ``period_lock_id`` source is refused by name, as every register
does; an explicit historical run whose cutoff precedes the last change of a judgement record it
would show is refused by name (REGISTER-CUTOFF-1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    contract,
    contract_version,
    judgement_record,
    obligation_version,
    tenant,
)
from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, contract_history
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.builders.out_of_period_register import refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import JudgementStatus, ScopeFlag
from erev_api.explain import store as trace_store
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork
from erev_engine.canonical import canonical_bytes
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.trace import Trace

CODE: Final = "scope_exclusion_register"
EVIDENCE: Final = "scope_exclusion_inputs_v1"
ROW_KEY_PREFIX: Final = "obligation:"  # RPT-30: row_key `obligation:<external id>:<key>`
DEFAULT_CURRENCY_VIEW: Final = "transaction"
IN_SCOPE: Final = ScopeFlag.IN_SCOPE_606.value
LEASE: Final = ScopeFlag.LEASE_842.value  # S03-R-11: stays an allocation target (PT-09)
SUBJECT_TYPE: Final = "obligation"  # T-CON-19 subject of a line's scope judgement
# A record that is no judgement of its line any more: rejected, superseded, or — a discarded
# draft (E-57 ``VOIDED``; 04 rev 1.242) — never one.
CLOSED: Final = (
    JudgementStatus.REJECTED.value,
    JudgementStatus.SUPERSEDED.value,
    JudgementStatus.VOIDED.value,
)
FUNCTIONAL_ONLY: Final = (
    "The functional currency view is available when every routed-out line is in its entity's "
    "functional currency; choose the transaction view."
)
HISTORY_UNAVAILABLE: Final = (
    "The scope exclusion register cannot state judgement {judgement_no} as of {cutoff}: the "
    "record last changed at {updated_at}, after the cutoff, and T-CON-19 keeps no history of its "
    "status (not reconstructed). Run the register at a later known_at or current."
)
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("scope_flag", "Scope", "code"),
    Column("currency", "Currency", "code"),
    Column("out_of_scope_amount", "Out-of-scope amount", "money"),
    Column("judgement_no", "Judgement", "code"),
    Column("rationale", "Rationale", "text"),
    Column("effective_date", "Effective date", "date"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One routed-out obligation version with its amount and judgement — the input of
    ``dataset_rows``."""

    contract_external_id: str
    obligation_key: str
    product_code: str
    scope_flag: str
    currency: str
    functional_currency: str
    out_of_scope_amount: Decimal | None
    judgement_no: str | None
    rationale: str | None
    effective_date: date
    combined_components: tuple[str, ...] = ()
    combination_judgements: tuple[str, ...] = ()
    combination_rationales: tuple[str, ...] = ()
    combination_evidence_status: str | None = None


def amount_of(
    scope_flag: str, *, allocated_amount: Decimal, version_amount: Decimal, version_lines: int
) -> Decimal | None:
    """``out_of_scope_amount`` of one routed-out obligation version (module docstring). Pure."""
    if scope_flag == LEASE:
        return allocated_amount
    return version_amount if version_lines == 1 else None


def latest_judgement(records: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The latest judgement record of one obligation that is neither rejected nor superseded
    nor discarded. Pure."""
    open_records = [row for row in records if support.text(row["status"]) not in CLOSED]
    return max(open_records, key=lambda row: str(row["judgement_no"]), default=None)


def check_view(view: str, found: Iterable[Source]) -> None:
    """``transaction`` always; another view only when every row is in its entity's functional
    currency, else refused by name."""
    if view not in {"transaction", "functional", "reporting"}:
        raise tie_outs.invalid("currency_view", "Unsupported scope-exclusion currency view.")
    if view != DEFAULT_CURRENCY_VIEW and any(
        item.currency != item.functional_currency for item in found
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def dataset_rows(found: Iterable[Source]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in contract and obligation order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    totals: dict[str, Decimal] = {}
    ordered = sorted(found, key=lambda item: (item.contract_external_id, item.obligation_key))
    for item in ordered:
        amount = None
        if item.out_of_scope_amount is not None:
            amount = tie_outs.money(item.out_of_scope_amount, item.currency)
            tie_outs.add(totals, item.currency, item.out_of_scope_amount)
        rows.append(
            {
                "row_key": f"{ROW_KEY_PREFIX}{item.contract_external_id}:{item.obligation_key}",
                "contract_external_id": item.contract_external_id,
                "obligation_key": item.obligation_key,
                "product_code": item.product_code,
                "scope_flag": item.scope_flag,
                "currency": item.currency,
                "out_of_scope_amount": amount,
                "judgement_no": item.judgement_no,
                "rationale": item.rationale,
                "effective_date": item.effective_date,
            }
        )
        if item.combination_evidence_status is not None:
            rows[-1].update(
                combined_components="; ".join(item.combined_components),
                combination_judgements="; ".join(item.combination_judgements),
                combination_rationales="\n".join(item.combination_rationales),
                combination_evidence_status=item.combination_evidence_status,
            )
    if any("combination_evidence_status" in row for row in rows):
        for row in rows:
            for key in (
                "combined_components",
                "combination_judgements",
                "combination_rationales",
                "combination_evidence_status",
            ):
                row.setdefault(key, None)
    return rows, {
        "row_count": len(rows),
        "out_of_scope_amount_total": tie_outs.by_currency(totals),
    }


def period_ends(session: Session, params: ReportParams) -> dict[date, list[tie_outs.EntityRef]]:
    """The end of ``period_key`` (else of the period holding the run's as-of date) per entity
    calendar: end date → the entities that close on it, in entity-code order."""
    found = tie_outs.entities(session, params.entity_ids, params=params)
    calendars = tie_outs.calendars(session, found, params=params)
    ends: dict[date, list[tie_outs.EntityRef]] = {}
    for entity in found:
        period = tie_outs.period_of(params, calendars[entity.id], entity)
        ends.setdefault(period.end, []).append(entity)
    return ends


def _judgements(
    session: Session, params: ReportParams, obligation_ids: Sequence[UUID], *, cutoff: datetime
) -> dict[UUID, Mapping[str, Any]]:
    if not obligation_ids:
        return {}
    statement = select(judgement_record).where(
        judgement_record.c.subject_type == SUBJECT_TYPE,
        judgement_record.c.subject_id.in_(list(obligation_ids)),
        judgement_record.c.created_at <= cutoff,
    )
    by_obligation: dict[UUID, list[Mapping[str, Any]]] = {}
    for row in session.execute(statement).mappings():
        by_obligation.setdefault(UUID(str(row["subject_id"])), []).append(dict(row))
    found: dict[UUID, Mapping[str, Any]] = {}
    for obligation_id, records in by_obligation.items():
        moved = support.changed_after(records, cutoff=cutoff, historical=params.historical)
        if moved is not None:
            raise tie_outs.invalid(
                "known_at",
                HISTORY_UNAVAILABLE.format(
                    judgement_no=moved["judgement_no"],
                    cutoff=cutoff.isoformat(),
                    updated_at=moved["updated_at"].isoformat(),
                ),
            )
        latest = latest_judgement(records)
        if latest is not None:
            found[obligation_id] = latest
    return found


def combination_evidence(
    trace: Trace | None, subject_key: str
) -> tuple[tuple[str, ...], tuple[str, ...], str] | None:
    """Read retained calculation evidence, never infer combined membership from live judgements."""
    if trace is None:
        return None
    node = next((node for node in trace.nodes if node.id == f"stated_price:{subject_key}:-"), None)
    if node is None or "lessor_judgement_keys" not in node.params:
        return None
    judgements = tuple(node.params["lessor_judgement_keys"].split(","))
    encoded = node.params.get("lessor_component_keys")
    if encoded is None:
        return (), judgements, "Legacy trace lacks structured component membership"
    components = json.loads(encoded)
    if not isinstance(components, list) or not all(isinstance(key, str) for key in components):
        raise ValueError("Invalid retained lessor component membership")
    return tuple(components), judgements, "Retained calculation evidence"


def sources(uow: UnitOfWork, params: ReportParams, *, book_code: str) -> tuple[list[Source], date]:
    """The routed-out obligation versions at each entity's period end; and the as-of date of the
    control totals (the first entity's period end; the run's day without entities)."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    ends = period_ends(session, params)
    rows: list[tuple[dict[str, Any], tie_outs.EntityRef]] = []
    for end, entities in sorted(ends.items()):
        by_id = {entity.id: entity for entity in entities}
        for row in contract_history.population(
            session,
            params,
            book_code=book_code,
            where=[
                *contract_history.latest_where(session, params, book_code=book_code, as_of=end),
                obligation_version.c.scope_flag != IN_SCOPE,
                obligation_version.c.contracting_entity_id.in_(sorted(by_id, key=str)),
            ],
        ):
            rows.append((row, by_id[UUID(str(row["contracting_entity_id"]))]))
    version_ids = sorted({UUID(str(row["contract_version_id"])) for row, _ in rows}, key=str)
    tie_outs.record_members(params, "scope_contract_versions", version_ids)
    amounts: dict[UUID, Decimal] = {}
    if version_ids:
        amounts = {
            UUID(str(version_id)): Decimal(amount)
            for version_id, amount in session.execute(
                select(contract_version.c.id, contract_version.c.out_of_scope_amount).where(
                    contract_version.c.id.in_(version_ids)
                )
            )
        }
    lines: dict[UUID, int] = {}
    for row, _ in rows:
        version_id = UUID(str(row["contract_version_id"]))
        lines[version_id] = lines.get(version_id, 0) + 1
    judgements = _judgements(
        session, params, [UUID(str(row["obligation_id"])) for row, _ in rows], cutoff=cutoff
    )
    traces = {version_id: trace_store.load_trace(session, version_id) for version_id in version_ids}
    found: list[Source] = []
    for row, entity in rows:
        version_id = UUID(str(row["contract_version_id"]))
        judgement = judgements.get(UUID(str(row["obligation_id"])))
        combined = combination_evidence(
            traces[version_id],
            obligation_subject_key(str(row["contract_external_id"]), str(row["obligation_key"])),
        )
        rationales: tuple[str, ...] = ()
        if combined is not None:
            # Reviewed content is immutable even after supersession. Select the exact records
            # named by the retained computation, not a more recent assessment of the host.
            evidence = session.execute(
                select(judgement_record.c.judgement_no, judgement_record.c.rationale).where(
                    judgement_record.c.contract_id == row["contract_id"],
                    judgement_record.c.judgement_no.in_(combined[1]),
                    judgement_record.c.reviewed_at <= row["version_known_at"],
                )
            ).all()
            by_number = {str(number): str(rationale) for number, rationale in evidence}
            if set(by_number) != set(combined[1]):
                raise ValueError("Retained lessor judgement evidence is unavailable")
            rationales = tuple(f"{number}: {by_number[number]}" for number in combined[1])
        found.append(
            Source(
                contract_external_id=str(row["contract_external_id"]),
                obligation_key=str(row["obligation_key"]),
                product_code=str(row["product_code"]),
                scope_flag=str(support.text(row["scope_flag"])),
                currency=str(row["txn_currency"]).strip(),
                functional_currency=entity.functional_currency,
                out_of_scope_amount=amount_of(
                    str(support.text(row["scope_flag"])),
                    allocated_amount=Decimal(row["allocated_amount"]),
                    version_amount=amounts[version_id],
                    version_lines=lines[version_id],
                ),
                judgement_no=None if judgement is None else str(judgement["judgement_no"]),
                rationale=None if judgement is None else str(judgement["rationale"]),
                effective_date=row["effective_date"],
                combined_components=() if combined is None else combined[0],
                combination_judgements=() if combined is None else combined[1],
                combination_rationales=rationales,
                combination_evidence_status=None if combined is None else combined[2],
            )
        )
    # ``period_ends`` inserts in entity-code order: its first key is the first entity's end
    return found, next(iter(ends), params.known_at.date())


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    check_view(view, ())
    selection = {key: params.parameters.get(key) for key in ("book", "period_key")}
    if params.binding is not None:
        retained = tie_outs.bound_evidence(params, EVIDENCE)
        if retained["tenant_id"] != str(uow.principal.tenant_id) or set(retained["entity_ids"]) != {
            str(entity_id) for entity_id in params.entity_ids
        }:
            raise Problem("forbidden", "Retained scope inputs exceed report scope.")
        if retained["currency_view"] != view or retained["selection"] != selection:
            raise tie_outs.invalid(
                "currency_view", "Retained inputs use another currency or filter selection."
            )
        return data_from_inputs(retained)
    session = uow.session
    found, as_of = sources(uow, params, book_code=tie_outs.book_of(session, params))
    check_view(view, found)
    target: str | None = None
    translations: dict[str, tuple[UUID, reporting_currency.Translation]] = {}
    if view == "reporting":
        target = str(
            session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == uow.principal.tenant_id)
            ).scalar_one()
        ).strip()
        entities = tie_outs.entities(session, params.entity_ids)
        by_id = {entity.id: entity for entity in entities}
        calendars = tie_outs.calendars(session, entities)
        owners = {
            str(external): UUID(str(entity_id))
            for external, entity_id in session.execute(
                select(contract.c.external_id, contract.c.contracting_entity_id).where(
                    contract.c.tenant_id == uow.principal.tenant_id,
                    contract.c.contracting_entity_id.in_(params.entity_ids),
                    contract.c.external_id.in_({item.contract_external_id for item in found}),
                )
            ).all()
        }
        rates: dict[UUID, reporting_currency.Translation] = {}
        for item in found:
            if item.out_of_scope_amount is None:
                continue
            entity_id = owners[item.contract_external_id]
            entity = by_id[entity_id]
            if entity_id not in rates:
                period = tie_outs.period_of(params, calendars[entity_id], entity)
                rates[entity_id] = reporting_currency.rates_for_period(
                    session,
                    params,
                    tenant_id=uow.principal.tenant_id,
                    entities=(entity,),
                    periods={entity_id: period},
                    rate_type="closing",
                    target_currency=target,
                    evidence_key=f"scope_closing_v1:{entity_id}:{period.key}",
                )
            translations[item.contract_external_id] = (entity_id, rates[entity_id])
    retained = json.loads(
        canonical_bytes(
            {
                "tenant_id": uow.principal.tenant_id,
                "entity_ids": params.entity_ids,
                "currency_view": view,
                "selection": selection,
                "as_of": as_of,
                "sources": [asdict(item) for item in found],
                "reporting_currency": target,
                "translations": [
                    {
                        "contract_external_id": key,
                        "entity_id": entity_id,
                        "currency": rate.currency,
                        "rates": {str(k): v for k, v in rate.rates.items()},
                    }
                    for key, (entity_id, rate) in translations.items()
                ],
            }
        )
    )
    tie_outs.record_evidence(params, EVIDENCE, retained)
    return data_from_inputs(retained)


def data_from_inputs(retained: Mapping[str, Any]) -> ReportData:
    found = []
    for record in retained["sources"]:
        values = dict(record)
        values["effective_date"] = date.fromisoformat(values["effective_date"])
        values["out_of_scope_amount"] = (
            None
            if values["out_of_scope_amount"] is None
            else Decimal(values["out_of_scope_amount"])
        )
        found.append(Source(**values))
    view = retained["currency_view"]
    check_view(view, found)
    rows, totals = dataset_rows(found)
    columns: tuple[Column, ...] = COLUMNS
    if any(item.combination_evidence_status is not None for item in found):
        columns += (
            Column("combined_components", "Combined original components", "text"),
            Column("combination_judgements", "Combination assessments", "text"),
            Column("combination_rationales", "Combination rationales", "text"),
            Column("combination_evidence_status", "Combination evidence basis", "text"),
        )
    if view == "reporting":
        target = retained["reporting_currency"]
        translations = {
            item["contract_external_id"]: (
                UUID(item["entity_id"]),
                reporting_currency.Translation(
                    item["currency"], {UUID(key): value for key, value in item["rates"].items()}
                ),
            )
            for item in retained["translations"]
        }
        equivalents: dict[str, Decimal] = {}
        for row in rows:
            row["reporting_currency"] = target
            row["reporting_basis"] = (
                "Equivalent at report-period closing rate; not a carrying balance"
            )
            row["out_of_scope_reporting"] = None
            if row["out_of_scope_amount"] is not None:
                entity_id, rate = translations[row["contract_external_id"]]
                if (
                    rate.currency != target
                    or rate.rates[entity_id]["base_currency"] != row["currency"]
                ):
                    raise tie_outs.invalid(
                        "currency_view", "Reporting translation requires functional amounts."
                    )
                amount = rate.amount(entity_id, Decimal(row["out_of_scope_amount"]["amount"]))
                row["out_of_scope_reporting"] = tie_outs.money(amount, target)
                tie_outs.add(equivalents, target, amount)
        totals["out_of_scope_reporting_total"] = tie_outs.by_currency(equivalents)
        totals["reporting_currency"] = target
        totals["translation_basis"] = "report_period_closing_equivalent"
        columns = columns + (
            Column("reporting_currency", "Reporting currency", "code"),
            Column("out_of_scope_reporting", "Out-of-scope reporting equivalent", "money"),
            Column("reporting_basis", "Reporting conversion basis", "text"),
        )
    totals["as_of"] = retained["as_of"]
    return ReportData(columns=columns, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "DEFAULT_CURRENCY_VIEW",
    "Source",
    "amount_of",
    "build",
    "check_view",
    "dataset_rows",
    "latest_judgement",
    "period_ends",
    "sources",
]
