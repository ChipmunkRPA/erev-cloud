"""Legacy v1 template ``legacy_contract_setup`` (ENGINE_SPEC S01-R-03, S01-R-06, S03-R-18; 04
T-IMP-01, §17.4 LM-TPL-SETUP, T-REF-19 legacy note, T-CON-02, T-SRC-02, T-SRC-03; PRD J-01.8,
J-01.9, BR-DAT-06, WLD-X-26, IMP-13, IMP-16, IMP-34; POLICIES POL-213, POL-214; DEVIATIONS DEV-032;
03 REQ-DAT-017, REQ-ALC-010, REQ-TP-016; BUILD_SPEC DIN-4, BS3-D-23).

Rows group by ``Contract Unique Name`` across the whole file, never per batch (DEV-032). One plan
per contract:

1. customer ``LEGACY-<contract>`` with ``source_system = LEGACY_TEMPLATE_V1``, created when absent
   (T-REF-19 legacy note; [J] its name is the code);
2. a new contract is booked: ``CONTRACT_BOOKED`` (origin ``IMPORT``, the S01-R-03 import key of the
   contract, the upload and the first row's source record) at ``inception_date`` = the minimum
   ``Current Period``, header entity = ``Selling Entity`` of the first row, currency = the tenant
   reporting currency, ``document_ref = import:<import_no>:<file name>`` (BS3-D-23), and one line
   per row (LM-TPL-SETUP; account overrides ``CONTRACT_LIABILITY`` from the deferred revenue
   account, ``CONTRACT_ASSET`` and ``UNBILLED_RECEIVABLE`` from the unbilled account);
3. a DRAFT contract receives the new lines through ``replace_draft``, so allocation runs at
   activation over every line (DEV-032; TC-setup-11);
4. a row of stratification ``VC`` is a line of the booking, which S03-R-18 gives ``LEGACY-VC``
   (kind ``VC_LINE``), plus the contract-level VC element ``<contract>/VC-<obligation key>``
   (``ENTERED_AMOUNT``, version 1, ``allocation_target = CONTRACT``; POL-213). [J] L5-1-Q-15: the
   element is written through ``vc_element_writer``, the port to BUILD_SPEC CTR-12 (L5-2); since
   the L5 merge its default is ``store_vc_element`` (L5-1-Q-35);
5. at commit, per row a ``contract_source_link`` (``BOOKING``, the booking event) and the
   ``source_order`` and ``source_order_line`` rows; then, unless the upload parameter
   ``activate_on_approval`` is ``false`` ([J] L5-1-Q-16), the BS3-D-23 records and the activation
   (BR-DAT-06): one ``POB_DISTINCT_OVERRIDE`` judgement per obligation from its template flag, and
   per enabled book a ``COLLECTIBILITY`` judgement with ``COLLECTIBILITY_ASSESSED {is_probable:
   true}``, prepared by the import principal on behalf of the uploader and reviewed by the approver
   in the commit transaction; ``activation.activate`` then evaluates the checklist and computes. A
   contract whose checklist fails stays DRAFT with one exception item (L5-1-Q-17).

Validation adds ``SETUP_QUANTITY_ZERO`` and ``DATE_RANGE_INVERTED`` per row, and across the file
``SETUP_CONTRACT_EXISTS`` for the rows of a contract that is not DRAFT (REQ-DAT-017; TC-setup-22)
and, without the ``LEGACY_PARITY`` preset, ``VC_TARGET_INVALID`` for a ``VC`` row (REQ-TP-016).
BUILD_SPEC DIN-7 adds, naming every contributing row (DEVIATIONS OQ-D11):

- ``SETUP_DUPLICATE_POB`` on each row of a (contract, POB) key repeated in the file (IMP-12;
  DEV-014; TC-setup-14);
- ``SSP_KEY_NOT_FOUND`` on a row whose (SKU, stratification, version) key has no row in an
  approved ``LEGACY-SKU-SSP`` version, at column ``SKU Name`` (IMP-09; DEV-034; TC-setup-20);
- ``TOTAL_SSP_ZERO`` on each row of a contract whose total SSP is 0 whatever the stated prices
  (IMP-14; DEV-028; POL-077; TC-setup-18). [J] L6-1-Q-3: a line's SSP is 0 whatever its price when
  it is a ``VC`` row (S03-R-18 ``VC_LINE``) or its entry's unit midpoint L × (1 − d) is 0; the
  file's rows and the lines already booked on a DRAFT contract count. Any other total is left to
  the engine's ``TOTAL_SSP_ZERO`` at activation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects as approval_subjects
from erev_api.approvals.subjects import judgement_record_content
from erev_api.audit import writer as audit_writer
from erev_api.db import new_id, transitions
from erev_api.db.tables import (
    contract,
    contract_source_link,
    customer,
    estimate,
    estimate_version,
    judgement_record,
    product,
    source_order,
    source_order_line,
)
from erev_api.domain.contracts import activation, repo
from erev_api.domain.contracts.commands import book_contract, provisional_compute, replace_draft
from erev_api.domain.imports import findings
from erev_api.domain.imports import legacy_templates as columns
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    ContractChange,
    CsvRow,
    CsvTemplate,
    Performed,
    Plan,
)
from erev_api.domain.imports.exceptions import raise_exception_item, severity_of
from erev_api.domain.imports.legacy_v1 import headers, setup_amounts
from erev_api.domain.imports.legacy_v1.sku_ssp import (
    SspKey,
    approved_midpoints,
    key_text,
    reporting_currency,
    ssp_key,
)
from erev_api.domain.integrations.normalise import import_event_key
from erev_api.domain.policies import judgements
from erev_api.domain.reference.commands import create_customer
from erev_api.domain.ssp import resolution
from erev_api.enums import (
    ApprovalSubjectType,
    ContractEventType,
    ContractStatus,
    Distinctness,
    ExceptionSource,
    JudgementStatus,
    JudgementTopic,
    SourceObjectType,
    SourceSystem,
)
from erev_api.events.payloads import CollectibilityAssessedV1, EstimateChangedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem
from erev_api.registry import presets
from erev_api.schemas.contracts import ContractCreateIn
from erev_api.schemas.customers import CustomerIn
from erev_api.schemas.judgements import JudgementCreateIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "ACTIVATE_PARAMETER",
    "CODE",
    "ROW_RULES",
    "TEMPLATE",
    "VcElement",
    "cross_findings",
    "pending_vc_element",
    "store_vc_element",
    "write_vc_element",
]

CODE: Final = "legacy_contract_setup"
CUSTOMER_PREFIX: Final = "LEGACY-"  # T-REF-19 legacy note
VC_STRATIFICATION: Final = "VC"  # S01-R-06, S03-R-18
VC_ELEMENT: Final = "VC-{obligation_key}"
DOCUMENT_REF: Final = "import:{import_no}:{filename}"  # BS3-D-23
ACTIVATE_PARAMETER: Final = "activate_on_approval"  # [J] L5-1-Q-16
LINK_ROLE: Final = "BOOKING"  # T-CON-02
LINK_ACTION: Final = "contract_source_link.create"
ORDER_ACTION: Final = "source_order.create"
ORDER_LINE_ACTION: Final = "source_order_line.create"
JUDGEMENT_OBJECT: Final = "judgement_record"
CHECKLIST_FAILED: Final = "activation-checklist-failed"
# BS3-D-23 wording.
COLLECTIBILITY_CONCLUSION: Final = "Collectibility probable: legacy template import {import_no}"
DISTINCT_CONCLUSIONS: Final[Mapping[str, str]] = {
    Distinctness.DISTINCT.value: (
        "{key} ({product}) is a distinct performance obligation: legacy template import "
        "{import_no}."
    ),
    Distinctness.NONDISTINCT.value: (
        "{key} ({product}) is not distinct: legacy template import {import_no}."
    ),
}
RECORD_RATIONALE: Final = (
    "Recorded by legacy template import {import_no} and reviewed through its approval "
    "(BUILD_SPEC BS3-D-23)."
)
VC_RATIONALE: Final = (
    "Legacy VC stratification row imported as a contract-level VC element (POL-213)."
)
# PRD IMP-09, IMP-12, IMP-13, IMP-14, IMP-16, IMP-18, IMP-34.
SSP_NOT_FOUND: Final = "No approved SSP for {key}."
DUPLICATE_POB: Final = "Contract {contract} has obligation {pob} more than once in this file."
TOTAL_ZERO: Final = (
    "Contract {contract} has a total SSP of 0, so its transaction price cannot be allocated."
)
RANGE_INVERTED: Final = "{end_column} ({end}) is before {start_column} ({start})."
QUANTITY_ZERO: Final = "Original POB Total Qty must not be 0."
CONTRACT_EXISTS: Final = (
    "Contract {contract} already exists. Change it through a Contract Modification upload or the "
    "modification workflow."
)
VC_TARGET: Final = "A price change cannot target VC element {element}. Target an obligation."


@dataclass(frozen=True, slots=True)
class VcElement:
    """S01-R-06: the contract-level VC element of a legacy ``VC`` row, as BUILD_SPEC CTR-12 stores
    it (04 T-CON-12, T-CON-13). [J] L5-1-Q-15: amounts are magnitudes and a negative row price is a
    ``DECREASE`` element (04 B3-D16)."""

    contract_id: UUID
    contract_external_id: str
    element_code: str  # VC-<obligation key>
    obligation_key: str
    direction: str  # INCREASE | DECREASE
    constrained_amount: Decimal  # |row price|, version 1
    currency: str
    effective_date: date
    estimate_kind: str = "VARIABLE_CONSIDERATION"
    method: str = "ENTERED_AMOUNT"
    allocation_target: str = "CONTRACT"
    version_no: int = 1
    rationale: str = VC_RATIONALE

    @property
    def estimate_key(self) -> str:
        """``<contract>/VC-<obligation key>``, the estimate key of S01-R-06."""
        return f"{self.contract_external_id}/{self.element_code}"


type VcElementWriter = Callable[..., UUID | None]  # (uow, element, *, context) -> version id


def pending_vc_element(
    uow: UnitOfWork, element: VcElement, *, context: ApplyContext
) -> UUID | None:
    """The port before CTR-12 integrated (D-81): the element is not stored and the VC line stays a
    ``VC_LINE`` obligation. Tests that fake the writer replace ``vc_element_writer`` instead."""
    del uow, element, context
    return None


def store_vc_element(uow: UnitOfWork, element: VcElement, *, context: ApplyContext) -> UUID:
    """The CTR-12 port since the L5 merge (L5-1-Q-15, L5-1-Q-35; S01-R-06, S01-R-18): the element
    of a legacy ``VC`` row written under the import's approval request and upload, its
    ``ESTIMATE_CHANGED`` with origin ``IMPORT`` (``write_vc_element``). A dry run stores the same
    rows inside its savepoint (IPL-07)."""
    return write_vc_element(
        uow,
        element,
        origin="IMPORT",
        approval_request_id=context.approval_request_id,
        import_upload_id=context.import_upload_id,
    )


def write_vc_element(
    uow: UnitOfWork,
    element: VcElement,
    *,
    origin: Literal["IMPORT", "MIGRATION"],
    approval_request_id: UUID | None = None,
    import_upload_id: UUID | None = None,
) -> UUID:
    """The contract-level VC element of a legacy ``VC`` row (S01-R-06, S01-R-18; POL-213), shared
    by the legacy template import (``store_vc_element``, origin ``IMPORT``) and the D-31 mode (a)
    opening-balance import's dry run (``migration.capture``, origin ``MIGRATION``; S07-R-11).

    The T-CON-12 element ``VC-<obligation key>`` of the contract is created when absent (IM-A: an
    existing element keeps its method and direction). A T-CON-13 version numbered after the
    element's latest carries the magnitude (B3-D16), moves DRAFT → SUBMITTED → APPROVED under
    ``approval_request_id`` and supersedes the element's APPROVED version (E-12). Then
    ``ESTIMATE_CHANGED`` (the caller's ``origin``) is appended at the element's effective date and
    recorded in ``applied_event_ids``, so the computation prices the contract with the element."""
    session = uow.session
    principal = uow.principal
    created = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    stamps = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    found = session.execute(
        select(estimate.c.id).where(
            estimate.c.contract_id == element.contract_id,
            estimate.c.element_code == element.element_code,
        )
    ).scalar_one_or_none()
    if found is None:
        estimate_id = new_id()
        values: dict[str, Any] = {
            "contract_id": element.contract_id,
            "estimate_kind": element.estimate_kind,
            "element_code": element.element_code,
            "direction": element.direction,
            "method": element.method,
            "allocation_target": element.allocation_target,
        }
        session.execute(
            insert(estimate).values(
                tenant_id=principal.tenant_id, id=estimate_id, **created, **values
            )
        )
        uow.audit(
            action="estimate.create",
            object_type="estimate",
            object_id=estimate_id,
            object_version="1",
            after={**values, "contract_id": str(element.contract_id)},
            comment=element.rationale,
            contract_id=element.contract_id,
        )
    else:
        estimate_id = UUID(str(found))
    number = 1 + int(
        session.execute(
            select(func.coalesce(func.max(estimate_version.c.version_no), 0)).where(
                estimate_version.c.estimate_id == estimate_id
            )
        ).scalar_one()
    )
    approved = [
        UUID(str(row["id"]))
        for row in session.execute(
            select(estimate_version.c.id, estimate_version.c.status).where(
                estimate_version.c.estimate_id == estimate_id
            )
        ).mappings()
        if str(getattr(row["status"], "value", row["status"])) == "APPROVED"
    ]
    previous = approved[0] if approved else None
    version_id = new_id()
    content = {
        "estimate_key": element.estimate_key,
        "version_no": number,
        "effective_date": element.effective_date.isoformat(),
        "direction": element.direction,
        "constrained_amount": format(element.constrained_amount, "f"),
        "currency": element.currency,
    }
    session.execute(
        insert(estimate_version).values(
            tenant_id=principal.tenant_id,
            id=version_id,
            estimate_id=estimate_id,
            version_no=number,
            status="DRAFT",
            effective_date=element.effective_date,
            constrained_amount=element.constrained_amount,
            currency=element.currency,
            rationale=element.rationale,
            content_sha256=sha256_hex(content),
            supersedes_version_id=previous,
            **created,
            **stamps,
        )
    )
    uow.audit(
        action="estimate_version.create",
        object_type="estimate_version",
        object_id=version_id,
        object_version="1",
        after={**content, "estimate_id": str(estimate_id), "status": "DRAFT"},
        comment=element.rationale,
        contract_id=element.contract_id,
    )
    for earlier in approved:
        transitions.apply(
            session,
            "estimate_version",
            earlier,
            to_status="SUPERSEDED",
            expected_status="APPROVED",
            set_values=stamps,
        )
    transitions.apply(
        session,
        "estimate_version",
        version_id,
        to_status="SUBMITTED",
        expected_status="DRAFT",
        set_values=stamps,
    )
    transitions.apply(
        session,
        "estimate_version",
        version_id,
        to_status="APPROVED",
        expected_status="SUBMITTED",
        set_values={"approval_request_id": approval_request_id, **stamps},
    )
    current = repo.get_contract(session, element.contract_id)
    (appended,) = append_events(
        uow,
        contract_id=element.contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.ESTIMATE_CHANGED,
                effective_date=element.effective_date,
                payload=EstimateChangedV1(
                    estimate_version_id=version_id, previous_estimate_version_id=previous
                ),
                estimate_version_id=version_id,
                approval_request_id=approval_request_id,
                import_upload_id=import_upload_id,
            )
        ],
        origin=origin,
    )
    transitions.apply(
        session,
        "estimate_version",
        version_id,
        to_status=None,
        expected_status="APPROVED",
        set_values={"applied_event_ids": [UUID(str(appended["id"]))], **stamps},
    )
    return version_id


vc_element_writer: VcElementWriter = store_vc_element


# --- row and file rules (04 table 15.4-A) ---------------------------------------------------------


def _quantity_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    quantity = typed.get(columns.QUANTITY)
    if isinstance(quantity, Decimal) and quantity == 0:
        return (
            headers.RowFinding("SETUP_QUANTITY_ZERO", "ERROR", QUANTITY_ZERO, columns.QUANTITY),
        )
    return ()


def _range_rule(typed: Mapping[str, Any]) -> Sequence[headers.RowFinding]:
    start = typed.get(columns.POB_START)
    end = typed.get(columns.POB_END)
    if isinstance(start, date) and isinstance(end, date) and end < start:
        message = RANGE_INVERTED.format(
            end_column=columns.POB_END,
            end=end.isoformat(),
            start_column=columns.POB_START,
            start=start.isoformat(),
        )
        return (headers.RowFinding("DATE_RANGE_INVERTED", "ERROR", message, columns.POB_END),)
    return ()


ROW_RULES: Final = (_quantity_rule, _range_rule)


def _zero_ssp(values: Mapping[str, Any], midpoints: Mapping[SspKey, Decimal | None]) -> bool:
    """[J] L6-1-Q-3: the line's SSP is 0 whatever its stated price."""
    if headers.text(values, columns.STRATIFICATION) == VC_STRATIFICATION:
        return True
    return midpoints.get(ssp_key(values), Decimal(1)) == 0


def _booked_lines(session: Session, contract_id: UUID) -> list[dict[str, Any]]:
    """The lines of a DRAFT contract's latest booking, as setup row values."""
    events = repo.stream(session, contract_id)
    if not events:
        return []
    payload = dict(_latest_booking(session, contract_id)["payload"] or {})
    return [
        {
            columns.SKU: line.get("product_code"),
            columns.STRATIFICATION: line.get("stratification"),
            columns.SSP_VERSION: line.get("ssp_version_label"),
        }
        for line in payload.get("lines", ())
    ]


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[headers.RowFinding]]:
    """``SETUP_CONTRACT_EXISTS`` for rows of a contract that is not DRAFT (IMP-16), without the
    parity preset ``VC_TARGET_INVALID`` for ``VC`` rows (IMP-34), and the DIN-7 findings of the
    module docstring (IMP-09, IMP-12, IMP-14)."""
    del parameters
    ordered = sorted(rows, key=lambda item: item[0])
    names = sorted({headers.text(values, columns.CONTRACT) or "" for _, values in ordered})
    stored = {
        str(external_id): (UUID(str(contract_id)), str(getattr(status, "value", status)))
        for external_id, contract_id, status in session.execute(
            select(contract.c.external_id, contract.c.id, contract.c.status).where(
                contract.c.external_id.in_(names)
            )
        )
    }
    parity = resolution.tenant_preset(session, known_at=known_at) == presets.LEGACY_PARITY
    midpoints = approved_midpoints(session)
    obligations: dict[tuple[str, str], list[int]] = {}
    contracts: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for number, values in ordered:
        name = headers.text(values, columns.CONTRACT) or ""
        pob = headers.text(values, columns.POB) or ""
        obligations.setdefault((name, pob), []).append(number)
        contracts.setdefault(name, []).append((number, values))
    found: dict[int, list[headers.RowFinding]] = {}

    def add(number: int, code: str, message: str, column: str) -> None:
        found.setdefault(number, []).append(headers.RowFinding(code, "ERROR", message, column))

    for number, values in ordered:
        name = headers.text(values, columns.CONTRACT) or ""
        pob = headers.text(values, columns.POB) or ""
        current = stored.get(name)
        if current is not None and current[1] != ContractStatus.DRAFT.value:
            add(
                number,
                "SETUP_CONTRACT_EXISTS",
                CONTRACT_EXISTS.format(contract=name),
                columns.CONTRACT,
            )
        if not parity and headers.text(values, columns.STRATIFICATION) == VC_STRATIFICATION:
            element = f"{name}/{VC_ELEMENT.format(obligation_key=pob)}"
            add(
                number,
                "VC_TARGET_INVALID",
                VC_TARGET.format(element=element),
                columns.STRATIFICATION,
            )
        members = obligations[(name, pob)]
        if len(members) > 1:
            message = findings.every_row(DUPLICATE_POB.format(contract=name, pob=pob), members)
            add(number, "SETUP_DUPLICATE_POB", message, columns.POB)
        key = ssp_key(values)
        if key not in midpoints:
            add(number, "SSP_KEY_NOT_FOUND", SSP_NOT_FOUND.format(key=key_text(key)), columns.SKU)
    for name, contract_rows in contracts.items():
        current = stored.get(name)
        booked = (
            _booked_lines(session, current[0])
            if current is not None and current[1] == ContractStatus.DRAFT.value
            else []
        )
        lines = [row_values for _, row_values in contract_rows] + booked
        if not all(_zero_ssp(line, midpoints) for line in lines):
            continue
        numbers = [row_number for row_number, _ in contract_rows]
        message = findings.every_row(TOTAL_ZERO.format(contract=name), numbers)
        for number in numbers:
            add(number, "TOTAL_SSP_ZERO", message, columns.CONTRACT)
    return found


# --- plans ----------------------------------------------------------------------------------------


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per contract over the whole file, in worksheet order of first appearance."""
    grouped: dict[str, list[CsvRow]] = {}
    for row in rows:
        grouped.setdefault(headers.text(row.normalized, columns.CONTRACT) or "", []).append(row)
    return [Plan(key=name, rows=tuple(members), body={}) for name, members in grouped.items()]


def _customer(uow: UnitOfWork, name: str) -> UUID:
    code = f"{CUSTOMER_PREFIX}{name}"
    found = uow.session.execute(select(customer.c.id).where(customer.c.code == code)).first()
    if found is not None:
        return UUID(str(found[0]))
    created = create_customer(
        uow, body=CustomerIn(code=code, name=code), source_system=SourceSystem.LEGACY_TEMPLATE_V1
    )
    return created.id


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


def _line(values: Mapping[str, Any], currency: str) -> dict[str, Any]:
    """The API-S-ContractLine members of one setup row (LM-TPL-SETUP-02 to 16)."""
    start = headers.day(values, columns.POB_START)
    end = headers.day(values, columns.POB_END)
    line: dict[str, Any] = {
        "obligation_key": headers.text(values, columns.POB),
        "product_code": headers.text(values, columns.SKU),
        "stratification": headers.text(values, columns.STRATIFICATION),
        "quantity": format(headers.number(values, columns.QUANTITY) or Decimal(0), "f"),
        "total_price": {
            "amount": format(headers.number(values, columns.PRICE) or Decimal(0), "f"),
            "currency": currency,
        },
        "start_date": None if start is None else start.isoformat(),
        "end_date": None if end is None else end.isoformat(),
        "performing_entity_code": headers.text(values, columns.SELLING_ENTITY),
        "ssp_version_label": headers.text(values, columns.SSP_VERSION),
        "account_overrides": _accounts(values),
        **headers.memos(values),
    }
    return line


def _inception(rows: Sequence[CsvRow]) -> date:
    days = [headers.day(row.normalized, columns.CURRENT_PERIOD) for row in rows]
    return min(value for value in days if value is not None)


def _latest_booking(session: Session, contract_id: UUID) -> Mapping[str, Any]:
    events = repo.stream(session, contract_id)
    voided = {row["supersedes_event_id"] for row in events if row["supersedes_event_id"]}
    bookings = [
        row
        for row in events
        if str(getattr(row["event_type"], "value", row["event_type"]))
        == ContractEventType.CONTRACT_BOOKED.value
        and row["id"] not in voided
    ]
    return bookings[-1]


def _key(context: ApplyContext, name: str) -> str:
    return import_event_key(
        file_sha256=context.file_sha256,
        template_code=context.template_code,
        template_version=context.template_version,
        business_key=name,
        ordinal=1,
    )


def _admit_booking(
    consumed: approvals.ConsumedBasis | None, name: str, existing: Mapping[str, Any] | None
) -> None:
    """DG-KRN-APR-05 rev 1.51 (Codex 0342 R1): a plan is booked against the APPROVED basis of its
    key, never against whatever draft is visible now. With a consumed composition, the key must
    have a basis entry (the approval covered it), an approved head must still be the head of the
    draft the plan replaces, and an approved ABSENCE must still hold — a contract that appeared for
    the key between the approval and this plan is refused ``StaleBasis`` (the whole job rolls back);
    the tenant-unique ``contract.external_id`` excludes a creation between this check and the
    insert. Without a composition (the diff's dry run) nothing is enforced here."""
    if consumed is None:
        return
    if name not in consumed.bases:
        raise approvals.StaleBasis()  # the approval did not cover this key
    approved = consumed.bases[name]
    if approved is None:
        if existing is not None:
            raise approvals.StaleBasis()  # approved absent; a contract appeared in between
        return
    if existing is None or int(existing["head_stream_version"]) != approved:
        raise approvals.StaleBasis()  # approved head no longer the head (or the draft is gone)


def _book(
    uow: UnitOfWork, plan: Plan, context: ApplyContext, currency: str, customer_id: UUID
) -> tuple[UUID, UUID, UUID, int | None]:
    """(contract id, group id, booking event id, head before) of the plan's booking."""
    session = uow.session
    name = plan.key
    first = plan.rows[0]
    lines = [_line(row.normalized, currency) for row in plan.rows]
    existing = repo.contract_by_external_id(session, name)
    _admit_booking(context.consumed, name, existing)
    record_id = context.record_ids.get(first.id)
    if existing is None:
        body = ContractCreateIn.model_validate(
            {
                "external_id": name,
                "customer_id": str(customer_id),
                "contracting_entity_code": headers.text(first.normalized, columns.SELLING_ENTITY),
                "transaction_currency": currency,
                "inception_date": _inception(plan.rows).isoformat(),
                "document_ref": DOCUMENT_REF.format(
                    import_no=context.import_no, filename=context.original_filename or ""
                ),
                "lines": lines,
            }
        )
        booked = book_contract(
            uow,
            body=body.booking(),
            origin="IMPORT",
            source_system=SourceSystem.LEGACY_TEMPLATE_V1,
            idempotency_key=_key(context, name),
            import_upload_id=context.import_upload_id,
            source_record_id=record_id,
        )
        contract_id = UUID(str(booked.contract["id"]))
        group_id = UUID(str(booked.combination_group["id"]))
        if context.dry_run:
            provisional_compute(uow, group_id)
        return contract_id, group_id, UUID(str(booked.event["id"])), None
    if str(getattr(existing["status"], "value", existing["status"])) != ContractStatus.DRAFT.value:
        raise Problem("validation-failed", CONTRACT_EXISTS.format(contract=name))
    contract_id = UUID(str(existing["id"]))
    # The approved head (== the locked draft's head, _admit_booking above) is the expected head of
    # the replace — never a re-read the job did not approve.
    head = int(existing["head_stream_version"])
    booking = dict(_latest_booking(session, contract_id)["payload"] or {})
    inception = min(date.fromisoformat(str(booking["inception_date"])), _inception(plan.rows))
    body = ContractCreateIn.model_validate(
        {
            **booking,
            "inception_date": inception.isoformat(),
            "lines": [*booking["lines"], *lines],
        }
    )
    replace_draft(
        uow,
        contract_id=contract_id,
        expected_stream_version=head,
        body=body,
        origin="IMPORT",
        idempotency_key=_key(context, name),
        import_upload_id=context.import_upload_id,
        source_record_id=record_id,
    )
    return (
        contract_id,
        UUID(str(existing["combination_group_id"])),
        UUID(str(_latest_booking(session, contract_id)["id"])),
        head,
    )


def _vc_elements(
    uow: UnitOfWork, plan: Plan, context: ApplyContext, contract_id: UUID, currency: str
) -> list[tuple[str, UUID]]:
    """S01-R-06: one element per ``VC`` row, through the CTR-12 port."""
    inception = _inception(plan.rows)
    targets: list[tuple[str, UUID]] = []
    for row in plan.rows:
        if headers.text(row.normalized, columns.STRATIFICATION) != VC_STRATIFICATION:
            continue
        key = headers.text(row.normalized, columns.POB) or ""
        price = headers.number(row.normalized, columns.PRICE) or Decimal(0)
        element = VcElement(
            contract_id=contract_id,
            contract_external_id=plan.key,
            element_code=VC_ELEMENT.format(obligation_key=key),
            obligation_key=key,
            direction="DECREASE" if price < 0 else "INCREASE",
            constrained_amount=abs(price),
            currency=currency,
            effective_date=inception,
        )
        existed = uow.session.execute(
            select(estimate.c.id).where(
                estimate.c.contract_id == contract_id,
                estimate.c.element_code == element.element_code,
            )
        ).scalar_one_or_none()
        version_id = vc_element_writer(uow, element, context=context)
        if version_id is not None and existed is None:
            estimate_id = uow.session.execute(
                select(estimate_version.c.estimate_id).where(estimate_version.c.id == version_id)
            ).scalar_one()
            targets.append(("estimate", UUID(str(estimate_id))))
    return targets


# --- commit-only records ------------------------------------------------------------------------


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _links(
    uow: UnitOfWork, plan: Plan, context: ApplyContext, contract_id: UUID, event_id: UUID
) -> None:
    """T-CON-02: one ``BOOKING`` link per row's source record."""
    tenant_id = uow.principal.tenant_id
    rows = [
        {
            "tenant_id": tenant_id,
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


def _source_order(
    uow: UnitOfWork,
    plan: Plan,
    context: ApplyContext,
    customer_id: UUID,
    currency: str,
) -> None:
    """T-SRC-02 and T-SRC-03: the order of the contract's rows of this file (LM-TPL-SETUP-01 to
    16). [J] ``external_version`` is the upload id, so a later file for a draft contract adds an
    order."""
    first = plan.rows[0]
    record_id = context.record_ids.get(first.id)
    if record_id is None:
        return
    session = uow.session
    tenant_id = uow.principal.tenant_id
    order_id = new_id()
    session.execute(
        insert(source_order).values(
            tenant_id=tenant_id,
            id=order_id,
            source_record_id=record_id,
            source_system=SourceSystem.LEGACY_TEMPLATE_V1.value,
            external_order_id=plan.key,
            external_version=str(context.import_upload_id),
            order_number=plan.key,
            order_date=_inception(plan.rows),
            customer_external_id=f"{CUSTOMER_PREFIX}{plan.key}",
            customer_id=customer_id,
            legal_entity_code=headers.text(first.normalized, columns.SELLING_ENTITY),
            transaction_currency=currency,
            grouping_values={},
            document_ref=DOCUMENT_REF.format(
                import_no=context.import_no, filename=context.original_filename or ""
            ),
            custom_attributes={},
            **_created(uow),
        )
    )
    codes = sorted({headers.text(row.normalized, columns.SKU) or "" for row in plan.rows})
    products = {
        str(code): UUID(str(value))
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(codes))
        )
    }
    lines: list[dict[str, Any]] = []
    for number, row in enumerate(plan.rows, start=1):
        values = row.normalized
        code = headers.text(values, columns.SKU) or ""
        entity = headers.text(values, columns.SELLING_ENTITY)
        lines.append(
            {
                "tenant_id": tenant_id,
                "id": new_id(),
                "source_order_id": order_id,
                "line_external_id": headers.text(values, columns.POB),
                "line_no": number,
                "product_code": code,
                "product_id": products.get(code),
                "stratification": headers.text(values, columns.STRATIFICATION),
                "quantity": headers.number(values, columns.QUANTITY),
                "total_price": headers.number(values, columns.PRICE),
                "start_date": headers.day(values, columns.POB_START),
                "end_date": headers.day(values, columns.POB_END),
                "selling_entity_code": entity,
                "performing_entity_code": entity,
                "ssp_version_label": headers.text(values, columns.SSP_VERSION),
                "account_codes": _accounts(values) or {},
                "effective_date": headers.day(values, columns.CURRENT_PERIOD),
                "memo_1": headers.text(values, "Memo 1"),
                "memo_2": headers.text(values, "Memo 2"),
                "memo_3": headers.text(values, "Memo 3"),
                "custom_attributes": {},
                **_created(uow),
            }
        )
    session.execute(insert(source_order_line), lines)
    audit_writer.record_facts(uow, action=ORDER_ACTION, object_type="source_order", ids=[order_id])
    audit_writer.record_facts(
        uow,
        action=ORDER_LINE_ACTION,
        object_type="source_order_line",
        ids=[line["id"] for line in lines],
        detail={"source_order_id": str(order_id)},
    )


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _review(uow: UnitOfWork, judgement_id: UUID, context: ApplyContext) -> None:
    """DRAFT → SUBMITTED → REVIEWED in the commit transaction, reviewed by the import's approver
    (BS3-D-23; DB-10: the preparer is the import principal)."""
    session = uow.session
    content = judgement_record_content(session, judgement_id)
    record = transitions.apply(
        session,
        JUDGEMENT_OBJECT,
        judgement_id,
        to_status=JudgementStatus.SUBMITTED.value,
        expected_status=JudgementStatus.DRAFT.value,
        set_values={"content_sha256": sha256_hex(content), **_stamps(uow)},
    )
    uow.audit(
        action=f"{JUDGEMENT_OBJECT}.{JudgementStatus.SUBMITTED.value.lower()}",
        object_type=JUDGEMENT_OBJECT,
        object_id=judgement_id,
        before={"status": JudgementStatus.DRAFT.value},
        after={"status": JudgementStatus.SUBMITTED.value},
        approval_request_id=context.approval_request_id,
        contract_ids=judgements.record_contracts(record),
    )
    # The approver who answered for the review by ordinal (R-98 (9) as refined, rev 1.198).
    reviewer_id = context.approver_of(ApprovalSubjectType.JUDGEMENT_RECORD)
    record = transitions.apply(
        session,
        JUDGEMENT_OBJECT,
        judgement_id,
        to_status=JudgementStatus.REVIEWED.value,
        expected_status=JudgementStatus.SUBMITTED.value,
        set_values={
            "reviewer_id": reviewer_id,
            "reviewed_at": uow.now,
            "approval_request_id": context.approval_request_id,
            **_stamps(uow),
        },
    )
    uow.audit(
        action=f"{JUDGEMENT_OBJECT}.{JudgementStatus.REVIEWED.value.lower()}",
        object_type=JUDGEMENT_OBJECT,
        object_id=judgement_id,
        before={"status": JudgementStatus.SUBMITTED.value},
        after={
            "status": JudgementStatus.REVIEWED.value,
            "reviewer_id": None if reviewer_id is None else str(reviewer_id),
        },
        approval_request_id=context.approval_request_id,
        contract_ids=judgements.record_contracts(record),
    )


def _prepare_records(uow: UnitOfWork, contract_id: UUID, context: ApplyContext) -> None:
    """BS3-D-23: the distinct reviews of the obligations without one and, per enabled book, the
    collectibility record and ``COLLECTIBILITY_ASSESSED``."""
    session = uow.session
    current = repo.get_contract(session, contract_id)
    obligations = repo.obligations(session, contract_id)
    reviewed = {
        UUID(str(value))
        for value in session.execute(
            select(judgement_record.c.subject_id).where(
                judgement_record.c.contract_id == contract_id,
                judgement_record.c.topic == JudgementTopic.POB_DISTINCT_OVERRIDE.value,
                judgement_record.c.status == JudgementStatus.REVIEWED.value,
            )
        ).scalars()
    }
    product_ids = sorted({UUID(str(row["product_id"])) for row in obligations})
    flags = {
        UUID(str(value)): (str(code), str(getattr(flag, "value", flag)))
        for value, code, flag in session.execute(
            select(product.c.id, product.c.code, product.c.distinctness_default).where(
                product.c.id.in_(product_ids)
            )
        )
    }
    rationale = RECORD_RATIONALE.format(import_no=context.import_no)
    for row in obligations:
        if UUID(str(row["id"])) in reviewed:
            continue
        code, flag = flags[UUID(str(row["product_id"]))]
        if flag not in DISTINCT_CONCLUSIONS:
            continue
        key = str(row["obligation_key"])
        created = judgements.create_judgement(
            uow,
            body=JudgementCreateIn(
                topic=JudgementTopic.POB_DISTINCT_OVERRIDE,
                subject_type="obligation",
                subject_id=UUID(str(row["id"])),
                contract_id=contract_id,
                conclusion=DISTINCT_CONCLUSIONS[flag].format(
                    key=key, product=code, import_no=context.import_no
                ),
                rationale=rationale,
                questionnaire={"obligation_key": key, "distinctness": flag},
            ),
        )
        _review(uow, created.id, context)
    assessed: list[EventIn] = []
    for book_code in activation.enabled_books(session, UUID(str(current["contracting_entity_id"]))):
        created = judgements.create_judgement(
            uow,
            body=JudgementCreateIn(
                topic=JudgementTopic.COLLECTIBILITY,
                subject_type="contract",
                subject_id=contract_id,
                contract_id=contract_id,
                book=book_code,
                conclusion=COLLECTIBILITY_CONCLUSION.format(import_no=context.import_no),
                rationale=rationale,
                questionnaire={},
            ),
        )
        _review(uow, created.id, context)
        assessed.append(
            EventIn(
                event_type=ContractEventType.COLLECTIBILITY_ASSESSED,
                effective_date=current["inception_date"],
                payload=CollectibilityAssessedV1(
                    book=book_code, is_probable=True, judgement_record_id=created.id
                ),
                approval_request_id=context.approval_request_id,
                import_upload_id=context.import_upload_id,
            )
        )
    if assessed:
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=int(current["head_stream_version"]),
            events=assessed,
            origin="IMPORT",
        )


def _activate(uow: UnitOfWork, plan: Plan, context: ApplyContext, contract_id: UUID) -> None:
    """BR-DAT-06: the import approval is the activation approval; a failing checklist keeps the
    contract DRAFT with one exception item (L5-1-Q-17)."""
    session = uow.session
    savepoint = session.begin_nested()
    try:
        activation.activate(
            uow,
            contract_id=contract_id,
            approval_request_id=context.approval_request_id,
            on_behalf_of=context.uploader_id,
            consumed=context.consumed,  # the import approval's basis, consumed fresh at commit
            # the lines of a failing checklist become the message of the item below, which the
            # members of the contract's entity read: they are written for them
            stored_lines=True,
        )
    except Problem as problem:
        savepoint.rollback()
        if problem.slug != CHECKLIST_FAILED or not problem.errors:
            raise
        first = problem.errors[0]
        current = repo.get_contract(session, contract_id)
        raise_exception_item(
            uow,
            source=ExceptionSource.IMPORT,
            code=str(first.rule_id),
            severity=severity_of("ERROR"),
            message=" ".join(str(item.message) for item in problem.errors),
            dedupe=f"{ExceptionSource.IMPORT.value}:{first.rule_id}:{context.import_upload_id}:"
            f"{contract_id}",
            business_key=plan.key,
            import_upload_id=context.import_upload_id,
            contract_id=contract_id,
            combination_group_id=UUID(str(current["combination_group_id"])),
            # EXC-IMPORT-SCOPE-1 (04 T-IMP-05 rev 1.218): the entity of the contract it names
            entity_id=UUID(str(current["contracting_entity_id"])),
        )
        return
    savepoint.commit()


def _activates(context: ApplyContext) -> bool:
    value = context.parameters.get(ACTIVATE_PARAMETER, True)
    return not (value is False or str(value).lower() == "false")


# --- apply ----------------------------------------------------------------------------------------


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """Book, or add lines to the draft of, one contract; at commit record its sources and activate
    it (S01-R-06; BS3-D-23; BR-DAT-06)."""
    currency = reporting_currency(uow)
    customer_id = _customer(uow, plan.key)
    contract_id, group_id, event_id, head = _book(uow, plan, context, currency, customer_id)
    vc_targets = _vc_elements(uow, plan, context, contract_id, currency)
    if not context.dry_run:
        _links(uow, plan, context, contract_id, event_id)
        _source_order(uow, plan, context, customer_id, currency)
        if _activates(context):
            _prepare_records(uow, contract_id, context)
            _activate(uow, plan, context, contract_id)
    applied = Applied()
    applied.targets.extend(vc_targets)
    applied.targets.append(("contract_event", event_id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("contract_event", event_id)]
    applied.contracts.append((plan.key, contract_id, group_id, head))
    return applied


def underlying(
    session: Session,
    plan: Plan,
    applied: Applied,
    context: ApplyContext,
    changes: Mapping[str, ContractChange],
) -> dict[ApprovalSubjectType, list[Performed]]:
    """Ruling R-38 (ii): what the commit of one contract's rows approves by itself, so that the
    import approval answers for it — each with the routing facts a request of its subject would
    carry on its own path (item IMP-FLOOR-AMOUNT-1).

    - ``CONTRACT_ACTIVATION`` unless the upload asks for no activation (BR-DAT-06), with the
      routing flags that subject states for the contract the dry run booked (PRD §2.5: a second
      step held by a Controller from USD 1,000,000.00) and the amount its request carries — the
      subject's registered functions (``activation.activation_flags``, ``activation_amount``;
      item ACT-FLAGS-1, 04 §16.10 rev 1.287). They judge the larger of the booked consideration
      and the price of the provisional version the dry run stored when it booked the plan
      (``_book``), read that version for a financing adjustment and for the kinds of the
      contract's obligations — a row of stratification ``VC`` computes under ``LEGACY-VC`` —,
      and convert at the spot rate in force for the inception date: the amount is stated in
      the functional currency also where the contract's currency is another, and is none only
      while that rate is not published. A setup's lines state their own accounts and name no
      source for the two terms
      of a booking, so its activation carries ``NON_STANDARD_TERMS`` where a row holds an
      account and ``TERMS_NOT_STATED`` always — by construction, and with no effect on an
      auto-approval, which an import that activates never is (R-38 (ii));
    - ``JUDGEMENT_RECORD`` with it (the BS3-D-23 records ``_prepare_records`` writes REVIEWED).
      Its flags are not evaluated from the file (None): a second step of that subject, if its
      specification gains one, counts as applying. Its request carries no amount;
    - ``ESTIMATE_VERSION`` when the contract has a ``VC`` row (S01-R-06: the element version is
      APPROVED under the import's request). Evaluated, with no flag and a nil amount
      (supervisor rulings R-96 and R-102 (f), on R-41 (7) and R-66 (4)): the routing facts of an
      estimate version are the P&L impact of a change of estimate, and the commit approves the
      element version on a DRAFT contract the same commit books, before ``_activate`` — or
      without activating it at all (``activate_on_approval`` false). Such a version recognises
      nothing; its weight reaches the approval through the activation, whose facts are stated
      above. The condition holds for every setup upload that reaches an approval: a row naming
      a contract that is not DRAFT is refused at validation (``SETUP_CONTRACT_EXISTS``, IMP-16;
      ``cross_findings``), so the only contract that exists before the commit and that a setup
      upload touches is a DRAFT it replaces."""
    del changes
    found: dict[ApprovalSubjectType, list[Performed]] = {}
    if _activates(context):
        spec = approval_subjects.spec_for(ApprovalSubjectType.CONTRACT_ACTIVATION)
        found[ApprovalSubjectType.CONTRACT_ACTIVATION] = [
            Performed(
                flags=frozenset(spec.flags(session, contract_id)),
                amount=spec.amount_functional(session, contract_id),
            )
            for _external_id, contract_id, _group_id, _head in applied.contracts
        ]
        found[ApprovalSubjectType.JUDGEMENT_RECORD] = [Performed(flags=None)]
    if any(
        headers.text(row.normalized, columns.STRATIFICATION) == VC_STRATIFICATION
        for row in plan.rows
    ):
        found[ApprovalSubjectType.ESTIMATE_VERSION] = [
            Performed(flags=frozenset(), amount=_nil_amount(session, contract_id))
            for _external_id, contract_id, _group_id, _head in applied.contracts
        ]
    return found


def _nil_amount(session: Session, contract_id: UUID) -> tuple[Decimal, str]:
    """A nil P&L impact in the functional currency of the contract's entity: what the request of
    an estimate version that recognises nothing would carry (R-96)."""
    _total, _currency, functional = approval_subjects.contract_activation_total(
        session, contract_id
    )
    return Decimal(0).scaleb(-ISO_4217[functional].minor_unit), functional


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.CONTRACT_SETUP_ROW,
    target_type="contract",
    key_column=columns.CONTRACT,
    columns=(),
    plans=plans,
    apply=apply,
    source_system=SourceSystem.LEGACY_TEMPLATE_V1,
    underlying=underlying,
    reconcile_amounts=setup_amounts.reconcile_amounts,
)
