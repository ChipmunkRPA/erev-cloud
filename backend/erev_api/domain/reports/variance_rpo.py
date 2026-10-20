"""RPO at a replay's selected period end, through the shared dated trace reader.

The transient row adapter uses local UUID keys only to call ``to_date.version_at``;
it creates no database rows or version history. The calculation is the same dated
scheduled/awaiting remainder used by the RPO report, with the report's status and
duration/right-to-invoice exclusions. Partial targeted-VC exemptions use dated
allocation/share traces and retained estimate inputs; fixed consideration remains.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.dates import add_months
from erev_engine.money import format_exact, minor_to_decimal
from erev_engine.stages.s01_canonicalize.convert import (
    contract_key_from_subject,
    obligation_subject_key,
)
from erev_engine.stages.state import PolicyResolver

from erev_api.domain.contracts import to_date
from erev_api.domain.reports import rpo_quotas, tie_outs
from erev_api.problems import Problem

from .variance_measures import MeasureKey


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance RPO: {detail}")


def project(
    bundle: InputBundle,
    book: BookOutput,
    *,
    entity_code: str,
    period_key: str,
    functional: bool,
) -> dict[MeasureKey, Fraction]:
    """Disclosed RPO from dated output traces; no live registry or contract lookup."""
    entity = next(item for item in bundle.entities if item.code == entity_code)
    at = next(item.end_date for item in entity.periods if item.period_key == period_key)
    policies = PolicyResolver(
        next(b for b in bundle.books if b.book_code == book.book_code).policies
    )
    contracts = {item.external_id: item for item in bundle.contracts}
    statuses = dict(book.status_in_book)
    if len(statuses) != len(book.status_in_book):
        raise _refuse("contract status identities are duplicated.")
    ends = {key: header.inception_date for key, header in contracts.items()}
    rows: list[dict[str, Any]] = []
    external_ids = {}
    ids = {}
    for item in book.obligation_versions:
        contract = contract_key_from_subject(item.subject_key)
        header = contracts.get(contract)
        if header is None:
            raise _refuse("an obligation names a contract outside the input bundle.")
        columns = item.columns
        if columns.get("contracting_entity_code") != header.contracting_entity_code:
            raise _refuse("an obligation's contracting entity differs from its contract.")
        end = columns.get("end_date") or header.inception_date
        if not isinstance(end, date):
            raise _refuse("an obligation has an invalid end date.")
        ends[contract] = max(ends[contract], end)
        if columns.get("contracting_entity_code") != entity_code:
            continue
        if contract not in statuses:
            raise _refuse("the output omits a contract's book status.")
        if statuses[contract] not in tie_outs.INCLUDED_STATUSES:
            continue
        if columns.get("satisfaction_status") == "CANCELLED":
            continue
        entries = [
            event.effective_date
            for event in bundle.events
            if event.contract_key == contract
            and event.event_type in tie_outs.ENTRY_EVENTS
            and (
                event.event_type != tie_outs.CRITERIA_MET
                or event.payload.get("book") == book.book_code
            )
        ]
        if not entries:
            raise _refuse("an included contract has no retained disclosure-entry event.")
        if min(entries) > at:
            continue
        currency = str(columns.get("txn_currency", ""))
        if currency != header.transaction_currency or currency not in bundle.currencies:
            raise _refuse("an obligation has an inconsistent currency.")
        minor = bundle.currencies[currency].minor_unit
        contract_id = uuid5(NAMESPACE_URL, f"erev:variance:contract:{contract}")
        row_id = uuid5(NAMESPACE_URL, f"erev:variance:obligation:{item.subject_key}")
        if row_id in ids:
            raise _refuse("obligation identities are duplicated.")
        ids[row_id] = (contract, currency)
        external_ids[contract_id] = contract
        row: dict[str, Any] = {
            "id": row_id,
            "contract_id": contract_id,
            "obligation_key": columns.get("obligation_key"),
            "effective_date": columns.get("effective_date"),
            "satisfaction_status": columns.get("satisfaction_status"),
            "txn_currency": currency,
            "trace_nodes": item.trace_nodes,
            "recognition_method": columns.get("recognition_method"),
        }
        for name in ("revenue_cum", "billed_cum", "scheduled_amount", "awaiting_trigger_amount"):
            value = columns.get(name)
            if type(value) is not int:
                raise _refuse(f"{name} is missing or is not integer minor units.")
            row[name] = minor_to_decimal(value, minor)
        ratio = columns.get("progress_ratio")
        if isinstance(ratio, bool) or not isinstance(ratio, Fraction | Decimal | int):
            raise _refuse("the obligation's progress measure is absent.")
        row["progress_ratio"] = Decimal(format_exact(ratio))
        rows.append(row)
    if not rows:
        return {}
    starts: dict[tuple[str, date], set[date]] = defaultdict(set)
    for calendar in bundle.entities:
        for period in calendar.periods:
            starts[(period.period_key, period.end_date)].add(period.start_date)
    nodes = to_date.nodes_of(
        book.trace.nodes, starts={key: tuple(sorted(values)) for key, values in starts.items()}
    )
    measured = to_date.version_at(
        {"version_no": "DRY_RUN"}, rows, nodes=nodes, external_ids=external_ids, as_of=at
    )
    quota_history = rpo_quotas.history(
        book.trace,
        inception={key: header.inception_date for key, header in contracts.items()},
        targeted={
            item.version_key: item.allocation_target == "OBLIGATIONS"
            and item.parameters.get("allocation_criteria_evidence") not in (None, "")
            for item in bundle.estimate_versions
        },
    )
    result: dict[MeasureKey, Fraction] = {}
    for row in rows:
        contract, currency = ids[row["id"]]

        def applied(code: str) -> bool:
            value = policies.value(code, entity=entity_code, period=period_key)
            if not isinstance(value, str) or value not in {"APPLY", "DO_NOT_APPLY"}:
                raise _refuse(f"{code} has an invalid resolved value.")
            return value == "APPLY"

        if applied("rpo.exemption_original_duration_one_year") and ends[contract] <= add_months(
            contracts[contract].inception_date, 12
        ):
            continue
        if (
            applied("rpo.exemption_right_to_invoice")
            and row["recognition_method"] == "RIGHT_TO_INVOICE"
        ):
            continue
        if functional and currency != entity.functional_currency:
            raise _refuse("foreign-currency RPO has no supported functional valuation basis.")
        point = measured.obligations[row["id"]]
        remaining = point.scheduled + point.awaiting
        if (
            applied("rpo.exemption_vc_wholly_unsatisfied")
            and point.satisfaction_status == "UNSATISFIED"
            and point.revenue == 0
        ):
            quota = rpo_quotas.cap(
                quota_history.get(obligation_subject_key(contract, str(row["obligation_key"])), ()),
                at,
            )
            remaining -= min(max(remaining, Decimal(0)), quota)
        # Royalties are realized as reported; POL-199 has no unrecognized quota to remove.
        key = MeasureKey(contract, currency, "RPO")
        result[key] = result.get(key, Fraction(0)) + Fraction(remaining)
    return result
