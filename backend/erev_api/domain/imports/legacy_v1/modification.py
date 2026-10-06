"""Legacy v1 template ``legacy_contract_modification`` (ENGINE_SPEC S01-R-03, S01-R-09, §6.5
S06-R-28 to S06-R-31; 04 T-IMP-01, §3.4 E-23 to E-25, §16.3 ``CONTRACT_AMENDED``, §17.4 LM-TPL-MOD,
T-CON-02, table 15.4-A; PRD IMP-09, IMP-18, IMP-20, IMP-21, IMP-27 to IMP-30, IMP-33, IMP-34;
POLICIES POL-100, ALG-04 §2.5.7; DEVIATIONS DEV-018, DEV-053; 03 REQ-DAT-002, REQ-DAT-003;
BUILD_SPEC DIN-6).

The upload carries ``effective_date`` and ``mode`` (E-24 ``prospective``, ``retrospective``,
``pob_price_change``), which ``POST /imports`` requires (T-IMP-01 ``required_parameters``). Rows
group by ``Contract Unique Name`` into one plan per contract, and each row is one T-CON-06 line:
``obligation_key`` = POB Unique ID, ``product_code`` = SKU Name, ``start_date`` and ``end_date`` =
Mod Start Date and Mod End Date, ``stratification``, ``consideration_delta`` = Mod Billing,
``quantity_delta`` = Mod Qty, ``selling_entity_code``, ``account_codes`` (``CONTRACT_LIABILITY``
from the deferred revenue account, ``CONTRACT_ASSET`` and ``UNBILLED_RECEIVABLE`` from the unbilled
account), ``ssp_version_label`` and the memos. A row for an unknown obligation key is ``ADD`` when
the mode is not ``pob_price_change``, Mod Qty > 0, Mod Billing ≥ 0, every attribute is present and
the SSP key resolves (DEV-018); every other row names a stored obligation and is ``CHANGE``.

[J] L5-1-Q-27: BUILD_SPEC CTR-17 builds the T-CON-06 ``modification`` object, which R-RC-1 moves
post-rc, so the upload stores no ``modification`` row. The import approval approves the
modification, as BR-DAT-06 makes it the activation approval of a setup upload. The apply appends
``CONTRACT_AMENDED`` (origin ``IMPORT``, the import request, the S01-R-03 import key of the
contract) whose payload ``modification_id`` names the upload's modification of the contract
(``uuid5(<import upload id>, <contract>)``; the payload member only — the T-CON-05 column stays
NULL since 0068's FK links T-CON-06 rows and a legacy amendment has none: Q-3 composed with
140-A3 R2, 04 rev 1.80), whose ``treatments`` give the template treatment of
the mode to every obligation of the contract and every added line (S06-R-28; DEV-053), whose
``lines`` are the rows and whose ``ssp_basis`` names per line the approved ``LEGACY-SKU-SSP``
version of its label. The engine bundle projects the modification the event applies
(``domain.contracts.bundles``). The obligations of
``ADD`` lines are inserted after the event (``obligation.created_by_event_id``), each row's source
record is linked with role ``AMENDMENT`` at commit (T-CON-02), and the group is computed once per
contract.

[J] L5-1-Q-28: under POL-100 ``ENGINE_PROPOSES_PREPARER_CONFIRMS`` the upload is proposal input for
DRAFT modifications classified through stage 06 (S01-R-09), which is CTR-17 (R-RC-1). The plan is
refused (``IMPORT_PROCESSING_FAILED`` in the dry run, FAILED at commit), so no legacy treatment
applies outside the parity route.

Validation adds per row ``MOD_SIGN_MISMATCH`` and ``DATE_RANGE_INVERTED``, and across the file
``CONTRACT_NOT_FOUND``, ``POB_NOT_FOUND``, ``MOD_DUPLICATE_KEY``, ``MOD_POB_SKU_MISMATCH``,
``MOD_ATTRIBUTE_CONFLICT``, ``SSP_KEY_NOT_FOUND`` (when the three SSP key cells are given and the
row is not a VC row) and, for ``pob_price_change``, ``VC_QUANTITY_NOT_ALLOWED`` and
``VC_TARGET_INVALID``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID, uuid5

from erev_engine.currencies import ISO_4217
from sqlalchemy import and_, insert, select
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import THRESHOLD_CURRENCY
from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import (
    contract,
    contract_source_link,
    legal_entity,
    obligation,
    product,
)
from erev_api.domain.contracts import activation, compute_job, modifications, repo
from erev_api.domain.imports import findings
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import (
    UNEVALUATED,
    Applied,
    ApplyContext,
    ContractChange,
    CsvRow,
    CsvTemplate,
    Performed,
    Plan,
)
from erev_api.domain.imports.legacy_v1 import headers
from erev_api.domain.imports.legacy_v1.sku_ssp import BOOK_CODE
from erev_api.domain.integrations.normalise import import_event_key
from erev_api.domain.ssp import resolution
from erev_api.enums import (
    ApprovalSubjectType,
    BookCode,
    ComputationStatus,
    ContractEventType,
    ContractStatus,
    ModificationTreatment,
    SourceObjectType,
    SourceSystem,
)
from erev_api.events.payloads import ContractAmendedV1, ModificationLineV1, SspBasisV1
from erev_api.events.stream import EventIn, append_events
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.registry import resolve as registry

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "CODE",
    "ROW_RULES",
    "TEMPLATE",
    "TREATMENTS",
    "Catalogue",
    "StoredLine",
    "catalogue",
    "cross_findings",
    "stored_lines",
]

CODE: Final = "legacy_contract_modification"
MODE_PARAMETER: Final = "mode"
EFFECTIVE_PARAMETER: Final = "effective_date"
PRICE_CHANGE: Final = "pob_price_change"  # E-24
VC_STRATIFICATION: Final = "VC"  # S01-R-06
ROUTE_POLICY: Final = "mod.route_selection"  # POL-100
TEMPLATE_ROUTE: Final = "USER_SELECTED_TEMPLATE"
ADD: Final = "ADD"
CHANGE: Final = "CHANGE"
LINK_ROLE: Final = "AMENDMENT"  # T-CON-02
LINK_ACTION: Final = "contract_source_link.create"
MODIFIABLE: Final = frozenset({ContractStatus.ACTIVE.value, ContractStatus.COMPLETED.value})
# S01-R-09 under POL-100 USER_SELECTED_TEMPLATE: E-24 template mode -> E-23 treatment (ALG-04).
TREATMENTS: Final[Mapping[str, ModificationTreatment]] = MappingProxyType(
    {
        "prospective": ModificationTreatment.LEGACY_PROSPECTIVE,
        "retrospective": ModificationTreatment.LEGACY_RETROSPECTIVE,
        PRICE_CHANGE: ModificationTreatment.LEGACY_POB_VC,
    }
)
# DEV-018: the attributes an add-POB row carries.
ATTRIBUTES: Final = (
    columns.MOD_START,
    columns.MOD_END,
    columns.STRATIFICATION,
    columns.SELLING_ENTITY,
    columns.DEFERRED_ACCOUNT,
    columns.UNBILLED_ACCOUNT,
    columns.SSP_VERSION,
)
# PRD IMP copy.
NOT_FOUND: Final = "Contract {contract} does not exist in this workspace."
POB_NOT_FOUND: Final = "Obligation {pob} does not exist on contract {contract}."
DUPLICATE_KEY: Final = (
    "{contract}, obligation {pob} ({product}) appears more than once in this modification file."
)
SIGN_MISMATCH: Final = "Mod Qty ({quantity}) and Mod Billing ({amount}) have opposite signs."
SKU_MISMATCH: Final = "Obligation {pob} on {contract} is {stored}, not {found}."
ATTRIBUTE_CONFLICT: Final = (
    "{column} ({found}) differs from the stored value ({stored}). Change accounts, entity or "
    "stratification through a change event."
)
SSP_NOT_FOUND: Final = "No approved SSP for {key}."
VC_QUANTITY: Final = "A price change row must have Mod Qty 0. Found {quantity}."
VC_TARGET: Final = "A price change cannot target VC element {element}. Target an obligation."
RANGE_INVERTED: Final = "{end_column} ({end}) is before {start_column} ({start})."
# [J] L5-1-Q-28.
NATIVE_ROUTE: Final = (
    "Contract {contract}: POL-100 does not select USER_SELECTED_TEMPLATE, so this upload is "
    "proposal input for draft modifications, which this release does not build. Change the "
    "contract through the modification workflow."
)
NOT_MODIFIABLE: Final = (
    "Contract {contract} is {status}. A Contract Modification upload changes active contracts."
)


def _quantity(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


# --- row rules (04 table 15.4-A) ------------------------------------------------------------------


def _sign_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    quantity = typed.get(columns.MOD_QTY)
    billing = typed.get(columns.MOD_BILLING)
    if isinstance(quantity, Decimal) and isinstance(billing, Decimal) and quantity * billing < 0:
        message = SIGN_MISMATCH.format(quantity=_quantity(quantity), amount=format(billing, "f"))
        return (headers.RowFinding("MOD_SIGN_MISMATCH", "ERROR", message, columns.MOD_QTY),)
    return ()


def _range_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    start = typed.get(columns.MOD_START)
    end = typed.get(columns.MOD_END)
    if isinstance(start, date) and isinstance(end, date) and end < start:
        message = RANGE_INVERTED.format(
            end_column=columns.MOD_END,
            end=end.isoformat(),
            start_column=columns.MOD_START,
            start=start.isoformat(),
        )
        return (headers.RowFinding("DATE_RANGE_INVERTED", "ERROR", message, columns.MOD_END),)
    return ()


ROW_RULES: Final = (_sign_rule, _range_rule)


# --- stored state ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredLine:
    """The attributes of an obligation line in force (S01-R-20)."""

    product_code: str
    stratification: str | None
    entity_code: str | None
    accounts: Mapping[str, str]
    ssp_version_label: str | None


def _kind(row: Mapping[str, Any]) -> str:
    return str(getattr(row["event_type"], "value", row["event_type"]))


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def stored_lines(session: Session, contract_id: UUID) -> dict[str, StoredLine]:
    """The lines of the latest booking, then the ``ADD`` lines of the amendments; voided events are
    left out."""
    events = repo.stream(session, contract_id)
    voided = {row["supersedes_event_id"] for row in events if row["supersedes_event_id"]}
    found: dict[str, StoredLine] = {}
    for row in events:
        if row["id"] in voided:
            continue
        payload = row["payload"] or {}
        kind = _kind(row)
        if kind == ContractEventType.CONTRACT_BOOKED.value:
            found = {
                str(line["obligation_key"]): StoredLine(
                    product_code=str(line["product_code"]),
                    stratification=_text(line.get("stratification")),
                    entity_code=_text(line.get("performing_entity_code")),
                    accounts=dict(line.get("account_overrides") or {}),
                    ssp_version_label=_text(line.get("ssp_version_label")),
                )
                for line in payload.get("lines", ())
            }
        elif kind == ContractEventType.CONTRACT_AMENDED.value:
            for line in payload.get("lines", ()):
                if line.get("action") != ADD:
                    continue
                found[str(line["obligation_key"])] = StoredLine(
                    product_code=str(line.get("product_code")),
                    stratification=_text(line.get("stratification")),
                    entity_code=_text(line.get("selling_entity_code")),
                    accounts=dict(line.get("account_codes") or {}),
                    ssp_version_label=_text(line.get("ssp_version_label")),
                )
    return found


@dataclass(frozen=True, slots=True)
class Catalogue:
    """The approved ``LEGACY-SKU-SSP`` versions: the (label, SKU, stratification) keys and the
    version id of each label (S01-R-05)."""

    keys: frozenset[tuple[str, str, str]]
    version_ids: Mapping[str, UUID]


def catalogue(session: Session) -> Catalogue:
    versions, rows, _ = resolution.approved_versions(session)
    keys: set[tuple[str, str, str]] = set()
    ids: dict[str, UUID] = {}
    for version in versions:
        if version.ssp_book_code != BOOK_CODE or version.legacy_version_label is None:
            continue
        label = str(version.legacy_version_label)
        ids[label] = UUID(str(rows[version.version_key]["id"]))
        keys.update((label, entry.product_code, entry.stratification) for entry in version.entries)
    return Catalogue(frozenset(keys), MappingProxyType(ids))


def _adds(mode: str, values: Mapping[str, Any], resolves: bool) -> bool:
    """DEV-018: an add-POB row."""
    quantity = headers.number(values, columns.MOD_QTY)
    billing = headers.number(values, columns.MOD_BILLING)
    return (
        mode != PRICE_CHANGE
        and quantity is not None
        and quantity > 0
        and billing is not None
        and billing >= 0
        and all(headers.text(values, name) is not None for name in ATTRIBUTES)
        and resolves
    )


def _key(values: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        headers.text(values, columns.CONTRACT) or "",
        headers.text(values, columns.POB) or "",
        headers.text(values, columns.SKU) or "",
    )


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[headers.RowFinding]]:
    """The cross-row and cross-file findings of the module docstring, per row."""
    del known_at
    mode = str(parameters.get(MODE_PARAMETER) or "")
    ordered = sorted(rows, key=lambda item: item[0])
    names = sorted({_key(values)[0] for _, values in ordered})
    contracts = {
        str(row["external_id"]): dict(row)
        for row in session.execute(select(contract).where(contract.c.external_id.in_(names)))
        .mappings()
        .all()
    }
    keyed: dict[tuple[str, str, str], list[int]] = {}
    for number, values in ordered:
        keyed.setdefault(_key(values), []).append(number)
    ssp = catalogue(session)
    ledgers: dict[str, dict[str, StoredLine]] = {}
    found: dict[int, list[headers.RowFinding]] = {}

    def add(number: int, code: str, message: str, column: str) -> None:
        found.setdefault(number, []).append(headers.RowFinding(code, "ERROR", message, column))

    for number, values in ordered:
        key = _key(values)
        name, pob, sku = key
        if len(keyed[key]) > 1:
            # Every contributing row carries the finding and names every row (OQ-D11; DIN-8).
            add(
                number,
                "MOD_DUPLICATE_KEY",
                findings.every_row(
                    DUPLICATE_KEY.format(contract=name, pob=pob, product=sku), keyed[key]
                ),
                columns.POB,
            )
        current = contracts.get(name)
        if current is None:
            add(number, "CONTRACT_NOT_FOUND", NOT_FOUND.format(contract=name), columns.CONTRACT)
            continue
        lines = ledgers.get(name)
        if lines is None:
            lines = ledgers[name] = stored_lines(session, UUID(str(current["id"])))
        label = headers.text(values, columns.SSP_VERSION)
        stratification = headers.text(values, columns.STRATIFICATION)
        given = label is not None and stratification is not None
        resolves = given and (str(label), sku, str(stratification)) in ssp.keys
        if given and stratification != VC_STRATIFICATION and not resolves:
            add(
                number,
                "SSP_KEY_NOT_FOUND",
                SSP_NOT_FOUND.format(key=f"{sku} / {stratification} / {label}"),
                columns.SSP_VERSION,
            )
        line = lines.get(pob)
        if line is None:
            if not _adds(mode, values, resolves):
                add(
                    number,
                    "POB_NOT_FOUND",
                    POB_NOT_FOUND.format(pob=pob, contract=name),
                    columns.POB,
                )
            continue
        if line.product_code != sku:
            add(
                number,
                "MOD_POB_SKU_MISMATCH",
                SKU_MISMATCH.format(pob=pob, contract=name, stored=line.product_code, found=sku),
                columns.SKU,
            )
        for column, stored in (
            (columns.STRATIFICATION, line.stratification),
            (columns.SELLING_ENTITY, line.entity_code),
            (columns.DEFERRED_ACCOUNT, line.accounts.get("CONTRACT_LIABILITY")),
            (columns.UNBILLED_ACCOUNT, line.accounts.get("UNBILLED_RECEIVABLE")),
        ):
            value = headers.text(values, column)
            if value is not None and stored is not None and value != stored:
                add(
                    number,
                    "MOD_ATTRIBUTE_CONFLICT",
                    ATTRIBUTE_CONFLICT.format(column=column, found=value, stored=stored),
                    column,
                )
        if mode == PRICE_CHANGE:
            quantity = headers.number(values, columns.MOD_QTY) or Decimal(0)
            if quantity != 0:
                add(
                    number,
                    "VC_QUANTITY_NOT_ALLOWED",
                    VC_QUANTITY.format(quantity=_quantity(quantity)),
                    columns.MOD_QTY,
                )
            if line.stratification == VC_STRATIFICATION:
                add(
                    number,
                    "VC_TARGET_INVALID",
                    VC_TARGET.format(element=f"{name}/VC-{pob}"),
                    columns.POB,
                )
    return found


# --- plans and apply ------------------------------------------------------------------------------


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per contract in ascending contract order."""
    grouped: dict[str, list[CsvRow]] = {}
    for row in rows:
        grouped.setdefault(headers.text(row.normalized, columns.CONTRACT) or "", []).append(row)
    return [Plan(key=name, rows=tuple(grouped[name]), body={}) for name in sorted(grouped)]


def _accounts(values: Mapping[str, Any]) -> dict[str, str] | None:
    deferred = headers.text(values, columns.DEFERRED_ACCOUNT)
    unbilled = headers.text(values, columns.UNBILLED_ACCOUNT)
    found: dict[str, str] = {}
    if deferred is not None:
        found["CONTRACT_LIABILITY"] = deferred
    if unbilled is not None:
        found["CONTRACT_ASSET"] = unbilled
        found["UNBILLED_RECEIVABLE"] = unbilled
    return found or None


def _line(
    values: Mapping[str, Any], currency: str, action: Literal["ADD", "CHANGE"]
) -> ModificationLineV1:
    """The T-CON-06 line of one row (LM-TPL-MOD-02 to 15)."""
    billing = headers.number(values, columns.MOD_BILLING) or Decimal(0)
    return ModificationLineV1(
        obligation_key=headers.text(values, columns.POB) or "",
        action=action,
        product_code=headers.text(values, columns.SKU),
        quantity_delta=_quantity(headers.number(values, columns.MOD_QTY) or Decimal(0)),
        consideration_delta=MoneyIn(amount=format(billing, "f"), currency=currency),
        start_date=headers.day(values, columns.MOD_START),
        end_date=headers.day(values, columns.MOD_END),
        stratification=headers.text(values, columns.STRATIFICATION),
        selling_entity_code=headers.text(values, columns.SELLING_ENTITY),
        account_codes=_accounts(values),
        ssp_version_label=headers.text(values, columns.SSP_VERSION),
        **headers.memos(values),
    )


def _template_route(uow: UnitOfWork, entity_id: UUID) -> bool:
    """POL-100 ``USER_SELECTED_TEMPLATE`` in every book the contracting entity keeps."""
    books = activation.enabled_books(uow.session, entity_id)
    return bool(books) and all(
        str(
            registry.resolve(
                uow.session,
                ROUTE_POLICY,
                book_code=BookCode(book_code),
                entity_id=entity_id,
                known_at=uow.now,
            ).value
        )
        == TEMPLATE_ROUTE
        for book_code in books
    )


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _insert_added(
    uow: UnitOfWork,
    plan: Plan,
    contract_id: UUID,
    event: Mapping[str, Any],
    keys: Sequence[str],
    lines: Sequence[ModificationLineV1],
) -> None:
    """The obligations of the ``ADD`` lines, with the ids the event names (L3-1-Q-16)."""
    added = [line for line in lines if line.action == ADD]
    if not added:
        return
    session = uow.session
    ids = {key: UUID(str(value)) for key, value in zip(keys, event["obligation_ids"], strict=True)}
    existing = repo.obligations(session, contract_id)
    known = {UUID(str(row["id"])) for row in existing}
    sequence = max((int(row["line_sequence"]) for row in existing), default=0)
    codes = sorted({str(line.product_code) for line in added})
    products = {
        str(code): UUID(str(value))
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(codes))
        )
    }
    rows: list[dict[str, Any]] = []
    for line in added:
        obligation_id = ids[line.obligation_key]
        if obligation_id in known:
            continue
        product_id = products.get(str(line.product_code))
        if product_id is None:
            raise Problem(
                "validation-failed",
                f"Product {line.product_code} does not exist in this workspace.",
            )
        sequence += 1
        rows.append(
            {
                "tenant_id": uow.principal.tenant_id,
                "id": obligation_id,
                "contract_id": contract_id,
                "obligation_key": line.obligation_key,
                "product_id": product_id,
                # LM-CL-70: <Contract Unique Name> <POB Unique ID> <SKU Name>.
                "legacy_record_key": f"{plan.key} {line.obligation_key} {line.product_code}",
                "created_by_event_id": event["id"],
                "parent_obligation_id": None,
                "regrouped_from_obligation_id": None,
                "line_sequence": sequence,
                **_created(uow),
            }
        )
    if rows:
        session.execute(insert(obligation), rows)


def _links(
    uow: UnitOfWork, plan: Plan, context: ApplyContext, contract_id: UUID, event_id: UUID
) -> None:
    """T-CON-02: one ``AMENDMENT`` link per row's source record."""
    rows = [
        {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "contract_id": contract_id,
            "source_record_id": context.record_ids[row.id],
            "link_role": LINK_ROLE,
            "contract_event_id": event_id,
            **_created(uow),
        }
        for row in plan.rows
        if row.id in context.record_ids
    ]
    if not rows:
        return
    uow.session.execute(insert(contract_source_link), rows)
    audit_writer.record_facts(
        uow,
        action=LINK_ACTION,
        object_type="contract_source_link",
        ids=[row["id"] for row in rows],
        detail={"link_role": LINK_ROLE},
        contract_id=contract_id,
    )


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``CONTRACT_AMENDED`` of one contract, then its computation (module docstring)."""
    session = uow.session
    found = repo.contract_by_external_id(session, plan.key)
    if found is None:
        raise Problem("validation-failed", NOT_FOUND.format(contract=plan.key))
    contract_id = UUID(str(found["id"]))
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    status = str(getattr(current["status"], "value", current["status"]))
    if status not in MODIFIABLE:
        raise Problem("invalid-transition", NOT_MODIFIABLE.format(contract=plan.key, status=status))
    if not _template_route(uow, UUID(str(current["contracting_entity_id"]))):
        raise Problem("validation-failed", NATIVE_ROUTE.format(contract=plan.key))
    mode = str(context.parameters[MODE_PARAMETER])
    treatment = TREATMENTS[mode]
    effective = date.fromisoformat(str(context.parameters[EFFECTIVE_PARAMETER]))
    currency = str(current["transaction_currency"]).strip()
    stored = set(stored_lines(session, contract_id)) | {
        str(row["obligation_key"]) for row in repo.obligations(session, contract_id)
    }
    lines: list[ModificationLineV1] = []
    for row in plan.rows:
        pob = headers.text(row.normalized, columns.POB) or ""
        if pob not in stored and mode == PRICE_CHANGE:
            raise Problem("validation-failed", POB_NOT_FOUND.format(pob=pob, contract=plan.key))
        lines.append(_line(row.normalized, currency, CHANGE if pob in stored else ADD))
    ssp = catalogue(session)
    keys = sorted(line.obligation_key for line in lines)
    payload = ContractAmendedV1(
        modification_id=uuid5(context.import_upload_id, plan.key),
        treatments={
            key: treatment for key in sorted(stored | {line.obligation_key for line in lines})
        },
        lines=tuple(lines),
        ssp_basis={
            line.obligation_key: SspBasisV1(
                ssp_book_version_id=None
                if line.ssp_version_label is None
                else ssp.version_ids.get(line.ssp_version_label)
            )
            for line in lines
        },
    )
    event = EventIn(
        event_type=ContractEventType.CONTRACT_AMENDED,
        effective_date=effective,
        payload=payload,
        obligation_keys=tuple(keys),
        # CTR-17 Q-3 / L5-1-Q-27 composed with D-98 140-A3 R2 (MAIN DEFECT 2, 2026-09-21,
        # (c)-QUALIFIED; 04 rev 1.80): the T-CON-05 column stays NULL — 0068's
        # fk_contract_event__modification links platform-created T-CON-06 rows only, and a legacy
        # amendment has none; its synthetic id lives in the payload (04 §16.3 (R)) and the bundle
        # projects it from there (bundles.named_modification_ids / _modifications).
        modification_id=None,
        approval_request_id=context.approval_request_id,
        idempotency_key=import_event_key(
            file_sha256=context.file_sha256,
            template_code=context.template_code,
            template_version=context.template_version,
            business_key=plan.key,
            ordinal=1,
        ),
        import_upload_id=context.import_upload_id,
        source_record_id=context.record_ids.get(plan.rows[0].id),
    )
    head = int(current["head_stream_version"])
    (appended,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=head,
        events=[event],
        origin="IMPORT",
    )
    event_id = UUID(str(appended["id"]))
    _insert_added(uow, plan, contract_id, appended, keys, lines)
    if not context.dry_run:
        _links(uow, plan, context, contract_id, event_id)
    group_id = UUID(str(current["combination_group_id"]))
    outcome = compute_job.compute_group(uow, group_id)
    # Supervisor ruling R-98 (4): a computation that ends QUARANTINED or FAILED is stored, not
    # raised, and leaves the version of before the amendment in place — the dry run then reads
    # "nothing changed". The plan says so, and nothing is evaluated on its figures.
    applied = Applied(computed=outcome.status is ComputationStatus.SUCCEEDED)
    target = ("contract_event", event_id)
    applied.targets.append(target)
    for row in plan.rows:
        applied.row_targets[row.id] = [target]
    applied.contracts.append((plan.key, contract_id, group_id, head))
    return applied


def underlying(
    session: Session,
    plan: Plan,
    applied: Applied,
    context: ApplyContext,
    changes: Mapping[str, ContractChange],
) -> dict[ApprovalSubjectType, list[Performed]]:
    """Ruling R-38 (ii): the import approval approves the modification (L5-1-Q-27), so it answers
    for a ``MODIFICATION`` approval — with the routing facts a request of that subject carries,
    which its own ``routing_facts`` reads from the figures of the contract (PRD §2.5; item
    IMP-FLOOR-AMOUNT-1), here the dry run's:

    - the second-step flags, |catch-up| ≥ USD 50,000.00 and |transaction price change| ≥ USD
      250,000.00. The upload stores no modification row and retains no FX basis, so a contract in
      another currency than the thresholds' is not evaluated (None: the second step counts as
      applying);
    - the amount, |transaction price change| in the functional currency of the contract's entity
      — stated when the contract currency IS that currency (rate 1), not evaluated otherwise.

    Supervisor ruling R-98 (4): nothing is evaluated unless the plan's computation SUCCEEDED. A
    computation that ended QUARANTINED or FAILED left the stored version untouched, so the
    figures would read "no change" for an amendment of any size."""
    del plan, context
    if not applied.computed:
        return {ApprovalSubjectType.MODIFICATION: [UNEVALUATED]}
    contract_ids = {key: contract_id for key, contract_id, _group, _head in applied.contracts}
    performed: list[Performed] = []
    for external_id, change in changes.items():
        flags: frozenset[str] | None = None
        if change.currency == THRESHOLD_CURRENCY:
            unit = {"rate": "1", "base": change.currency, "quote": change.currency}
            _amount, flags, _basis = modifications.routing_facts(
                {
                    "transaction_price_before": {
                        "amount": str(change.transaction_price_before),
                        "currency": change.currency,
                    },
                    "transaction_price_after": {
                        "amount": str(change.transaction_price_after),
                        "currency": change.currency,
                    },
                    "catch_up_total": {
                        "amount": str(change.catch_up_total),
                        "currency": change.currency,
                    },
                },
                currency=change.currency,
                functional_currency=change.currency,
                fx_basis={"to_functional": unit, "to_threshold": unit},
            )
        functional = _functional_currency(session, contract_ids[external_id])
        stated = change.currency == functional
        performed.append(
            Performed(
                flags=flags,
                amount=_price_change(change, functional) if stated else None,
                amount_evaluated=stated,
            )
        )
    return {ApprovalSubjectType.MODIFICATION: performed}


def _functional_currency(session: Session, contract_id: UUID) -> str:
    """The functional currency of the contract's contracting entity."""
    return str(
        session.execute(
            select(legal_entity.c.functional_currency)
            .select_from(
                contract.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == contract.c.tenant_id,
                        legal_entity.c.id == contract.c.contracting_entity_id,
                    ),
                )
            )
            .where(contract.c.id == contract_id)
        ).scalar_one()
    ).strip()


def _price_change(change: ContractChange, currency: str) -> tuple[Decimal, str]:
    """|TP after − TP before| at the minor unit of ``currency``, rounded half up — the amount of
    ``modifications.routing_facts`` at a transaction→functional rate of 1."""
    unit = Decimal(1).scaleb(-ISO_4217[currency].minor_unit)
    moved = abs(change.transaction_price_after - change.transaction_price_before)
    return moved.quantize(unit, rounding=ROUND_HALF_UP), currency


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.MODIFICATION_ROW,
    target_type="contract_event",
    key_column=columns.CONTRACT,
    columns=(),
    plans=plans,
    apply=apply,
    source_system=SourceSystem.LEGACY_TEMPLATE_V1,
    underlying=underlying,
    computes=True,
)
