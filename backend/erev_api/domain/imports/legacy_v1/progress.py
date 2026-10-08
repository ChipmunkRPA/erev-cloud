"""Legacy v1 template ``legacy_progress_tracking`` (ENGINE_SPEC S01-R-03, S01-R-07, S01-R-08; 04
T-IMP-01 ``aggregation_rule = SUM_BY_KEY``, §17.4 LM-TPL-PROG, table 15.4-A; PRD J-01.10, IMP-04,
IMP-20 to IMP-25; DEVIATIONS DEV-010, DEV-012, DEV-020, DEV-021, "Aggregated finding rows"; 03
REQ-REC-024, REQ-REC-025, REQ-TP-009; BUILD_SPEC DIN-5).

Rows sum by key (``Contract Unique Name``, ``POB Unique ID``, ``SKU Name``) before validation,
whatever their memos; the version memo of a key is the last non-blank value in worksheet order
(S01-R-07). Validation marks the later rows of a key ``AGGREGATED`` (``validate.aggregated``) and
adds:

- per row, ``PROGRESS_MEMO_BLANK`` (WARNING) for each blank memo cell; the row is processed
  (IMP-04);
- per aggregated key, on its lowest row: ``CONTRACT_NOT_FOUND`` (IMP-20), ``POB_NOT_FOUND``
  (IMP-21) when the obligation or its product differ from the booking, ``PROGRESS_OVER_DELIVERY``
  when the net delivery exceeds the remaining quantity and ``RETURN_EXCEEDS_DELIVERED`` when a
  return exceeds the delivered quantity (IMP-22, IMP-24), ``PROGRESS_OVER_BILLING`` when non-VC
  billing exceeds the remaining billing plan and ``REFUND_EXCEEDS_BILLED`` when a non-VC credit
  exceeds the billed amount (IMP-23, IMP-25). A finding on a key of several rows names every
  contributing row, ascending ("Rows 2, 3."; DEVIATIONS OQ-D11).

A plan is one contract. Its events follow S01-R-08 per aggregated key in ascending business-key
order: net delivery q > 0 → ``DELIVERY_RECORDED``, q < 0 → ``RETURN_RECORDED``; net billing b > 0 →
``BILLING_RECORDED`` with the synthetic number ``<import_upload id>:<contract>:<POB>`` and, at
commit, a synthetic ``source_invoice``; b < 0 → ``CREDIT_MEMO_RECORDED`` with the same number;
pre-standard amount p ≠ 0 → ``PRE_STANDARD_REVENUE_RECORDED`` (signed); a non-blank memo →
``MEMO_UPDATED``. Every event takes the upload parameter ``effective_date`` and the S01-R-03 import
key of its aggregated key and ordinal. The group is computed once per contract (T-IMP-01 "one
computation per contract").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import contract, legal_entity, source_invoice, source_invoice_line
from erev_api.domain.contracts import compute_job, repo
from erev_api.domain.imports import findings
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
)
from erev_api.domain.imports.legacy_v1 import headers, progress_amounts
from erev_api.domain.integrations.normalise import import_event_key
from erev_api.enums import ContractEventType, ContractStatus, SourceObjectType, SourceSystem
from erev_api.events.payloads import (
    BillingRecordedV1,
    CreditMemoRecordedV1,
    DeliveryRecordedV1,
    MemoUpdatedV1,
    PreStandardRevenueRecordedV1,
    ReturnRecordedV1,
)
from erev_api.events.stream import EventIn, append_events
from erev_api.money import MoneyIn, money_out
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["CODE", "ROW_RULES", "TEMPLATE", "Aggregate", "aggregates", "cross_findings"]

CODE: Final = "legacy_progress_tracking"
VC_STRATIFICATION: Final = "VC"
SYNTHETIC_INVOICE: Final = "{upload}:{contract}:{pob}"  # S01-R-08
EFFECTIVE_PARAMETER: Final = "effective_date"
BOOKED: Final = ContractEventType.CONTRACT_BOOKED.value
AMENDED: Final = ContractEventType.CONTRACT_AMENDED.value
ADD_LINE: Final = "ADD"
# PRD IMP copy.
MEMO_BLANK: Final = "{column} is blank. The row was processed and the previous memo was kept."
NOT_FOUND: Final = "Contract {contract} does not exist in this workspace."
POB_NOT_FOUND: Final = "Obligation {pob} does not exist on contract {contract}."
OVER_DELIVERY: Final = (
    "{contract}, obligation {pob} ({product}): requested {requested}, remaining {remaining}."
)
OVER_BILLING: Final = (
    "{contract}, obligation {pob} ({product}): billing {requested} exceeds the remaining billing "
    "plan {remaining}."
)
RETURN_EXCEEDS: Final = (
    "Return of {requested} units exceeds the {remaining} units delivered on {contract}, obligation "
    "{pob} ({product})."
)
REFUND_EXCEEDS: Final = (
    "Credit of {requested} exceeds the {remaining} billed on {contract}, obligation {pob} "
    "({product})."
)


@dataclass(slots=True)
class Aggregate:
    """The rows of one key summed (S01-R-07)."""

    contract: str
    obligation_key: str
    product_code: str
    delivery: Decimal = Decimal(0)
    billing: Decimal = Decimal(0)
    pre_standard: Decimal = Decimal(0)
    memos: dict[str, str] = field(default_factory=dict)
    rows: list[int] = field(default_factory=list)

    @property
    def business_key(self) -> str:
        return f"{self.contract} / {self.obligation_key} / {self.product_code}"


def aggregates(
    rows: Sequence[tuple[int, Mapping[str, Any]]],
) -> dict[tuple[str, str, str], Aggregate]:
    """The aggregated keys of the rows in worksheet order of first appearance."""
    found: dict[tuple[str, str, str], Aggregate] = {}
    for number, values in sorted(rows, key=lambda item: item[0]):
        key = (
            headers.text(values, columns.CONTRACT) or "",
            headers.text(values, columns.POB) or "",
            headers.text(values, columns.SKU) or "",
        )
        item = found.setdefault(key, Aggregate(*key))
        item.delivery += headers.number(values, columns.DELIVERY) or Decimal(0)
        item.billing += headers.number(values, columns.BILLING) or Decimal(0)
        item.pre_standard += headers.number(values, columns.PRE_STANDARD) or Decimal(0)
        item.memos.update(headers.memos(values))  # the last non-blank memo wins
        item.rows.append(number)
    return found


# --- rules ----------------------------------------------------------------------------------------


def _memo_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    return [
        headers.RowFinding(
            "PROGRESS_MEMO_BLANK", "WARNING", MEMO_BLANK.format(column=column), column
        )
        for column, _ in columns.MEMOS
        if typed.get(column) is None or str(typed.get(column)).strip() == ""
    ]


ROW_RULES: Final = (_memo_rule,)


@dataclass(slots=True)
class _Ledger:
    """Booked lines and cumulative totals of one contract (S01-R-16, S01-R-17)."""

    currency: str
    lines: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    delivered: dict[str, Decimal] = field(default_factory=dict)
    returned: dict[str, Decimal] = field(default_factory=dict)
    billed: dict[str, Decimal] = field(default_factory=dict)
    credited: dict[str, Decimal] = field(default_factory=dict)


def _money_value(payload: Mapping[str, Any], name: str) -> Decimal:
    value = payload.get(name)
    if isinstance(value, Mapping):
        value = value.get("amount")
    return Decimal(0) if value is None else Decimal(str(value))


def _amended(line: Mapping[str, Any] | None, change: Mapping[str, Any]) -> dict[str, Any]:
    """The line in force after one ``CONTRACT_AMENDED`` line (L6-2 GPA-5). The remaining quantity
    and billing plan are those of the terms in force, not of the booking (ENGINE_SPEC Table 0.8-A
    ``PROGRESS_OVER_DELIVERY``, S06-R-08 RQ_p = Q_p − q_p + ΔQ_p, §6.5 Plan_i; DEVIATIONS §5 #22,
    #23): ``quantity`` gains ``quantity_delta`` and ``total_price`` gains ``consideration_delta``.
    An ``ADD`` line starts from zero with its own product and stratification (DEV-018)."""
    if line is None or change.get("action") == ADD_LINE:
        base: dict[str, Any] = {
            "obligation_key": change["obligation_key"],
            "product_code": change.get("product_code"),
            "stratification": change.get("stratification"),
        }
        quantity, price = Decimal(0), Decimal(0)
    else:
        base = dict(line)
        quantity, price = Decimal(str(line["quantity"])), _money_value(line, "total_price")
    base["quantity"] = format(quantity + Decimal(str(change.get("quantity_delta") or 0)), "f")
    base["total_price"] = {
        "amount": format(price + _money_value(change, "consideration_delta"), "f")
    }
    return base


def _ledger(session: Session, contract_row: Mapping[str, Any]) -> _Ledger:
    stream = repo.stream(session, UUID(str(contract_row["id"])))
    voided = {row["supersedes_event_id"] for row in stream if row["supersedes_event_id"]}
    ledger = _Ledger(currency=str(contract_row["transaction_currency"]).strip())
    for row in stream:
        if row["id"] in voided:
            continue
        kind = str(getattr(row["event_type"], "value", row["event_type"]))
        payload = row["payload"] or {}
        key = str(payload.get("obligation_key") or "")
        if kind == BOOKED:
            ledger.lines = {str(line["obligation_key"]): line for line in payload.get("lines", ())}
        elif kind == AMENDED:
            for change in payload.get("lines", ()):
                changed = str(change["obligation_key"])
                ledger.lines[changed] = _amended(ledger.lines.get(changed), change)
        elif kind == ContractEventType.DELIVERY_RECORDED.value:
            ledger.delivered[key] = ledger.delivered.get(key, Decimal(0)) + Decimal(
                str(payload["quantity"])
            )
        elif kind == ContractEventType.RETURN_RECORDED.value:
            ledger.returned[key] = ledger.returned.get(key, Decimal(0)) + Decimal(
                str(payload["quantity"])
            )
        elif kind == ContractEventType.BILLING_RECORDED.value:
            ledger.billed[key] = ledger.billed.get(key, Decimal(0)) + _money_value(
                payload, "amount"
            )
        elif kind == ContractEventType.CREDIT_MEMO_RECORDED.value:
            ledger.credited[key] = ledger.credited.get(key, Decimal(0)) + _money_value(
                payload, "amount"
            )
    return ledger


def _quantity(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _amount(value: Decimal, currency: str) -> str:
    return money_out(value, currency, ISO_4217).amount


def _located(message: str, rows: Sequence[int]) -> str:
    return findings.every_row(message, rows)  # OQ-D11 (BUILD_SPEC DIN-7)


def _bounds(item: Aggregate, ledger: _Ledger) -> list[headers.RowFinding]:
    line = ledger.lines[item.obligation_key]
    names = {"contract": item.contract, "pob": item.obligation_key, "product": item.product_code}
    key = item.obligation_key
    delivered = ledger.delivered.get(key, Decimal(0)) - ledger.returned.get(key, Decimal(0))
    found: list[headers.RowFinding] = []
    if item.delivery > 0:
        remaining = Decimal(str(line["quantity"])) - delivered
        if item.delivery > remaining:
            message = OVER_DELIVERY.format(
                requested=_quantity(item.delivery), remaining=_quantity(remaining), **names
            )
            found.append(
                headers.RowFinding("PROGRESS_OVER_DELIVERY", "ERROR", message, columns.DELIVERY)
            )
    elif item.delivery < 0 and -item.delivery > delivered:
        message = RETURN_EXCEEDS.format(
            requested=_quantity(-item.delivery), remaining=_quantity(delivered), **names
        )
        found.append(
            headers.RowFinding("RETURN_EXCEEDS_DELIVERED", "ERROR", message, columns.DELIVERY)
        )
    if line.get("stratification") == VC_STRATIFICATION:
        return found
    currency = ledger.currency
    billed = ledger.billed.get(key, Decimal(0)) - ledger.credited.get(key, Decimal(0))
    if item.billing > 0:
        remaining = _money_value(line, "total_price") - billed
        if item.billing > remaining:
            message = OVER_BILLING.format(
                requested=_amount(item.billing, currency),
                remaining=_amount(remaining, currency),
                **names,
            )
            found.append(
                headers.RowFinding("PROGRESS_OVER_BILLING", "ERROR", message, columns.BILLING)
            )
    elif item.billing < 0 and -item.billing > billed:
        message = REFUND_EXCEEDS.format(
            requested=_amount(-item.billing, currency), remaining=_amount(billed, currency), **names
        )
        found.append(headers.RowFinding("REFUND_EXCEEDS_BILLED", "ERROR", message, columns.BILLING))
    return found


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[headers.RowFinding]]:
    """The aggregated-key findings of the module docstring, on each key's lowest row."""
    del known_at, parameters
    items = aggregates(rows)
    names = sorted({item.contract for item in items.values()})
    contracts = {
        str(row["external_id"]): dict(row)
        for row in session.execute(select(contract).where(contract.c.external_id.in_(names)))
        .mappings()
        .all()
    }
    ledgers: dict[str, _Ledger] = {}
    found: dict[int, list[headers.RowFinding]] = {}
    for item in items.values():
        lowest = item.rows[0]
        current = contracts.get(item.contract)
        if current is None:
            message = _located(NOT_FOUND.format(contract=item.contract), item.rows)
            found.setdefault(lowest, []).append(
                headers.RowFinding("CONTRACT_NOT_FOUND", "ERROR", message, columns.CONTRACT)
            )
            continue
        ledger = ledgers.get(item.contract)
        if ledger is None:
            ledger = ledgers[item.contract] = _ledger(session, current)
        line = ledger.lines.get(item.obligation_key)
        if line is None or str(line.get("product_code")) != item.product_code:
            message = _located(
                POB_NOT_FOUND.format(pob=item.obligation_key, contract=item.contract), item.rows
            )
            found.setdefault(lowest, []).append(
                headers.RowFinding("POB_NOT_FOUND", "ERROR", message, columns.POB)
            )
            continue
        for finding in _bounds(item, ledger):
            found.setdefault(lowest, []).append(
                headers.RowFinding(
                    finding.code,
                    finding.severity,
                    _located(finding.message, item.rows),
                    finding.column,
                )
            )
    return found


# --- plans and apply ------------------------------------------------------------------------------


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per contract in ascending contract order; AGGREGATED rows join their key."""
    grouped: dict[str, list[CsvRow]] = {}
    for row in rows:
        grouped.setdefault(headers.text(row.normalized, columns.CONTRACT) or "", []).append(row)
    return [Plan(key=name, rows=tuple(grouped[name]), body={}) for name in sorted(grouped)]


def _money(value: Decimal, currency: str) -> MoneyIn:
    return MoneyIn(amount=format(value, "f"), currency=currency)


def _store_invoice(
    uow: UnitOfWork,
    context: ApplyContext,
    current: Mapping[str, Any],
    item: Aggregate,
    number: str,
    record_id: UUID,
    effective: date,
) -> UUID:
    """The synthetic ``source_invoice`` of a key's billing or credit (S01-R-08). The document and
    its line store the SIGNED amount — 04 T-SRC-04 ``total_amount`` "Signed: credit memos
    negative", T-SRC-05 ``amount`` "Signed" — while the ``CREDIT_MEMO_RECORDED`` event keeps the
    positive Money of 04 §16.3 (item LEGACY-CM-SIGN-1). The caller stores no document for a zero
    billing (T-SRC-04: one synthetic invoice per aggregated row with non-zero billing)."""
    session = uow.session
    principal = uow.principal
    created = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    entity_code = session.execute(
        select(legal_entity.c.code).where(legal_entity.c.id == current["contracting_entity_id"])
    ).scalar_one()
    currency = str(current["transaction_currency"]).strip()
    invoice_id = new_id()
    session.execute(
        insert(source_invoice).values(
            tenant_id=principal.tenant_id,
            id=invoice_id,
            source_record_id=record_id,
            source_system=SourceSystem.LEGACY_TEMPLATE_V1.value,
            external_invoice_id=number,
            external_version="1",
            invoice_number=number,
            document_kind="INVOICE" if item.billing > 0 else "CREDIT_MEMO",
            issue_date=effective,
            customer_id=current["customer_id"],
            legal_entity_code=str(entity_code),
            currency=currency,
            total_amount=item.billing,
            custom_attributes={},
            **created,
        )
    )
    line_id = new_id()
    session.execute(
        insert(source_invoice_line).values(
            tenant_id=principal.tenant_id,
            id=line_id,
            source_invoice_id=invoice_id,
            line_external_id=number,
            contract_ref=item.contract,
            obligation_ref=item.obligation_key,
            product_code=item.product_code,
            amount=item.billing,
            tax_lines=[],
            custom_attributes={},
            **created,
        )
    )
    audit_writer.record_facts(
        uow,
        action="source_invoice.create",
        object_type="source_invoice",
        ids=[invoice_id],
        detail={"import_upload_id": str(context.import_upload_id), "synthetic": True},
    )
    audit_writer.record_facts(
        uow, action="source_invoice_line.create", object_type="source_invoice_line", ids=[line_id]
    )
    return invoice_id


def _events(
    uow: UnitOfWork,
    context: ApplyContext,
    current: Mapping[str, Any],
    item: Aggregate,
    record_id: UUID | None,
    effective: date,
) -> list[tuple[EventIn, int]]:
    currency = str(current["transaction_currency"]).strip()
    key = item.obligation_key
    number = SYNTHETIC_INVOICE.format(
        upload=context.import_upload_id, contract=item.contract, pob=key
    )
    payloads: list[tuple[ContractEventType, Any]] = []
    if item.delivery > 0:
        payloads.append(
            (
                ContractEventType.DELIVERY_RECORDED,
                DeliveryRecordedV1(
                    obligation_key=key, quantity=_quantity(item.delivery), trigger="DELIVERY"
                ),
            )
        )
    elif item.delivery < 0:
        payloads.append(
            (
                ContractEventType.RETURN_RECORDED,
                ReturnRecordedV1(obligation_key=key, quantity=_quantity(-item.delivery)),
            )
        )
    if item.billing != 0:
        invoice_id = (
            None
            if context.dry_run or record_id is None
            else _store_invoice(uow, context, current, item, number, record_id, effective)
        )
        if item.billing > 0:
            payloads.append(
                (
                    ContractEventType.BILLING_RECORDED,
                    BillingRecordedV1(
                        invoice_number=number,
                        line_external_id=number,
                        obligation_key=key,
                        amount=_money(item.billing, currency),
                        issue_date=effective,
                        source_invoice_id=None if invoice_id is None else str(invoice_id),
                    ),
                )
            )
        else:
            payloads.append(
                (
                    ContractEventType.CREDIT_MEMO_RECORDED,
                    CreditMemoRecordedV1(
                        credit_memo_number=number,
                        obligation_key=key,
                        amount=_money(-item.billing, currency),
                        issue_date=effective,
                    ),
                )
            )
    if item.pre_standard != 0:
        payloads.append(
            (
                ContractEventType.PRE_STANDARD_REVENUE_RECORDED,
                PreStandardRevenueRecordedV1(
                    obligation_key=key, amount=_money(item.pre_standard, currency)
                ),
            )
        )
    if item.memos:
        payloads.append(
            (
                ContractEventType.MEMO_UPDATED,
                # CV-47 (a): the presence set = the non-blank memo cells (never a null)
                MemoUpdatedV1(
                    obligation_key=key,
                    named=tuple(sorted(item.memos)),
                    **item.memos,
                ),
            )
        )
    return [
        (
            EventIn(
                event_type=event_type,
                effective_date=effective,
                payload=payload,
                obligation_keys=(key,),
                idempotency_key=import_event_key(
                    file_sha256=context.file_sha256,
                    template_code=context.template_code,
                    template_version=context.template_version,
                    business_key=item.business_key,
                    ordinal=ordinal,
                ),
                import_upload_id=context.import_upload_id,
                source_record_id=record_id,
            ),
            ordinal,
        )
        for ordinal, (event_type, payload) in enumerate(payloads, start=1)
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """The S01-R-08 events of one contract, then its computation (module docstring)."""
    session = uow.session
    found = repo.contract_by_external_id(session, plan.key)
    if found is None:
        raise Problem("validation-failed", NOT_FOUND.format(contract=plan.key))
    if str(getattr(found["status"], "value", found["status"])) == ContractStatus.VOIDED.value:
        raise Problem("invalid-transition", NOT_FOUND.format(contract=plan.key))
    contract_id = UUID(str(found["id"]))
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    effective = date.fromisoformat(str(context.parameters[EFFECTIVE_PARAMETER]))
    items = aggregates([(row.row_number, row.normalized) for row in plan.rows])
    by_number = {row.row_number: row for row in plan.rows}
    events: list[EventIn] = []
    owners: list[Aggregate] = []
    for business_key in sorted(items, key=lambda value: " / ".join(value)):
        item = items[business_key]
        record_id = context.record_ids.get(by_number[item.rows[0]].id)
        for event, _ in _events(uow, context, current, item, record_id, effective):
            events.append(event)
            owners.append(item)
    applied = Applied()
    head = int(current["head_stream_version"])
    group_id = UUID(str(current["combination_group_id"]))
    if events:
        rows = append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=head,
            events=events,
            origin="IMPORT",
        )
        by_key: dict[str, list[tuple[str, UUID]]] = {}
        for row, item in zip(rows, owners, strict=True):
            target = ("contract_event", UUID(str(row["id"])))
            applied.targets.append(target)
            by_key.setdefault(item.business_key, []).append(target)
        for item in items.values():
            for number in item.rows:
                applied.row_targets[by_number[number].id] = list(by_key.get(item.business_key, []))
        compute_job.compute_group(uow, group_id)
    else:
        for plan_row in plan.rows:
            applied.row_targets[plan_row.id] = []
    applied.contracts.append((plan.key, contract_id, group_id, head))
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PROGRESS_ROW,
    target_type="contract_event",
    key_column=columns.CONTRACT,
    columns=(),
    plans=plans,
    apply=apply,
    source_system=SourceSystem.LEGACY_TEMPLATE_V1,
    computes=True,
    reconcile_amounts=progress_amounts.reconcile_amounts,
)
