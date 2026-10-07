"""Contract commands (dev-guide §6.1 DG-CMD-01 to DG-CMD-09, DG-CMD-11; 04 T-CON-01, T-CON-03,
T-CON-04, T-CON-10, §16.1 API-S-ContractCreate and the replace-draft command, §16.3; PRD SM-02; 03
REQ-CON-001, REQ-CON-002, REQ-DAT-017; BUILD_SPEC CTR-1, CTR-4).

``book_contract`` establishes a contract in ``DRAFT`` (SM-02 none → DRAFT) in one unit of work:

1. Authorize: a principal other than SYSTEM needs ``contract.create`` for the contracting entity
   (``require_for_entity``). [J] L3-1-Q-18: SYSTEM books on behalf of an approved import or
   migration, whose approval carries the permission.
2. Validate, collecting every finding (422 ``validation-failed``): the external id is new
   (REQ-DAT-017); the customer id exists, or ``customer {code, name}`` names an existing customer or
   one to create (API-S-ContractCreate); the contracting and performing entities exist; the
   transaction currency is enabled for the workspace; every line names an existing product; every
   money member is in the contract currency (REQ-CON-019); a renewal names a visible contract.
3. Allocate ``CON-nnnnnn``; insert the singleton group ``CG-<contract_no>`` (``APPLIED``) and the
   contract (``DRAFT``, head 0).
4. Append ``CONTRACT_BOOKED`` at stream version 1 through ``events.stream.append_events``, which
   raises the head, marks the group dirty and audits the event. [J] L3-1-Q-15: the stored payload
   names the resolved ``customer_id`` and no ``customer`` object.
5. Insert the current membership row (``valid_from_known_at`` = the event's ``recorded_at``) and one
   obligation per line with the id the event names (``ux_obligation__key``), then audit the group
   (AUD-CMD) and the contract, membership and obligations (AUD-FACT).

``create_contract`` (``POST /contracts``) books and computes the provisional version;
``replace_draft`` (``POST /contracts/{id}/replace-draft``) voids the booking of a DRAFT contract as
the SYSTEM principal, appends the caller's new booking and recomputes. Both answer API-S-Contract.
[J] L3-1-Q-36: the provisional computation runs in a savepoint of the command's transaction; an
``EngineError`` rolls the computation back and keeps the draft (fact capture, DG-CMD-09), and since
CTR-9 the refused computation is stored with its exception item (``compute_job.compute_group``).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from sqlalchemy import insert, select, update

from erev_api import numbering
from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import system_principal
from erev_api.db import new_id
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    combination_group,
    combination_group_member,
    contract,
    customer,
    legal_entity,
    obligation,
    product,
    tenant_currency,
)
from erev_api.domain.contracts import computation, compute_job, queries, repo
from erev_api.domain.reference.commands import create_customer
from erev_api.domain.reference.products import required_attribute_errors
from erev_api.enums import (
    CombinationStatus,
    ComputationStatus,
    ComputationTrigger,
    ContractEventType,
    ContractStatus,
    PrincipalKind,
    SourceSystem,
)
from erev_api.events import step1
from erev_api.events.payloads import ContractBookedV1, EventVoidedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.money import MoneyIn
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import ContractCreateIn, ContractOut
from erev_api.schemas.customers import CustomerIn
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

CREATE_PERMISSION: Final = "contract.create"
CONTRACT_SERIES: Final = "CONTRACT"
GROUP_PREFIX: Final = "CG-"
CONTRACT_OBJECT: Final = "contract"
GROUP_OBJECT: Final = "combination_group"
MEMBER_OBJECT: Final = "combination_group_member"
OBLIGATION_OBJECT: Final = "obligation"
BOOK_ACTION: Final = "contract.book"
REPLACE_ACTION: Final = "contract.replace_draft"
GROUP_CREATE_ACTION: Final = "combination_group.create"
MEMBER_CREATE_ACTION: Final = "combination_group_member.create"
OBLIGATION_CREATE_ACTION: Final = "obligation.create"
RULE_EXTERNAL_ID: Final = "REQ-DAT-017"
RULE_CONTRACT: Final = "T-CON-01"
RULE_ENTITY: Final = "T-REF-01"
RULE_CURRENCY: Final = "T-REF-09"
RULE_CUSTOMER: Final = "T-REF-19"
RULE_PRODUCT: Final = "T-REF-20"
RULE_SINGLE_CURRENCY: Final = "REQ-CON-019"
RULE_ACTIVATION: Final = "REQ-CON-005"
EXTERNAL_ID_TAKEN: Final = "A contract with this external id exists."
ENTITY_UNKNOWN: Final = "No legal entity has this code."
CURRENCY_DISABLED: Final = "Enable this currency for the workspace first."
CUSTOMER_UNKNOWN: Final = "No customer has this id."
PRODUCT_UNKNOWN: Final = "No product has this code."
CONTRACT_UNKNOWN: Final = "No contract has this id."
CONTRACT_CURRENCY: Final = "Use the contract currency."
EXTERNAL_ID_FIXED: Final = "Keep the contract's external id when replacing its draft."
ENTITY_FIXED: Final = "Keep the contracting entity when replacing a draft."
TRANSACTION_CURRENCY_FIXED: Final = "Keep the transaction currency when replacing a draft."
ACTIVATION_LATER: Final = "Save the draft first, then submit it for activation."
NOT_DRAFT: Final = "Only a draft contract can be replaced."
# PRD ERR-07.
STALE_CONTRACT: Final = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)
REPLACED_COMMENT: Final = "Booking replaced by a corrected draft (replace-draft)."
# Supervisor ruling R-102 (c) (04 §16.1 rev 1.150): a Step 1 judgement is made on the booking it
# judges, so the assessments of a replaced booking are voided with it.
ASSESSMENT_REPLACED_COMMENT: Final = (
    "Step 1 assessment of a booking replaced by a corrected draft (replace-draft)."
)
VOID_REASON: Final = "DATA_CORRECTION"

type Origin = Literal["API", "UI", "IMPORT", "ADAPTER", "SYSTEM", "MIGRATION"]


@dataclass(frozen=True, slots=True)
class BookedContract:
    contract: Mapping[str, Any]
    combination_group: Mapping[str, Any]
    member: Mapping[str, Any]
    obligations: tuple[Mapping[str, Any], ...]
    event: Mapping[str, Any]


def _stamps(uow: UnitOfWork, *, modified: bool = True) -> dict[str, Any]:
    principal = uow.principal
    values: dict[str, Any] = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    if modified:
        values |= {
            "updated_at": uow.now,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
        }
    return values


def _source(uow: UnitOfWork) -> SourceSystem:
    """[J] E-38 of a booking without a named channel: ``API`` for an API client, otherwise
    ``MANUAL_UI`` (as accounts and customers, L1-1-Q-8)."""
    if uow.principal.kind is PrincipalKind.API_CLIENT:
        return SourceSystem.API
    return SourceSystem.MANUAL_UI


def _origin(uow: UnitOfWork) -> Origin:
    """E-40 origin of a route command: ``API`` for an API client, otherwise ``UI``."""
    return "API" if uow.principal.kind is PrincipalKind.API_CLIENT else "UI"


def _error(field: str, rule_id: str, message: str) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _entity_ids(session: Session, codes: set[str]) -> dict[str, UUID]:
    statement = select(legal_entity.c.code, legal_entity.c.id).where(legal_entity.c.code.in_(codes))
    return {str(code): UUID(str(value)) for code, value in session.execute(statement)}


def _money_errors(field: str, value: MoneyIn | None, currency: str) -> list[ProblemError]:
    if value is None or value.currency == currency:
        return []
    return [_error(field, RULE_SINGLE_CURRENCY, CONTRACT_CURRENCY)]


def _currency_errors(body: ContractBookedV1) -> list[ProblemError]:
    currency = body.transaction_currency
    errors: list[ProblemError] = []
    for index, line in enumerate(body.lines):
        errors += _money_errors(f"lines.{index}.total_price", line.total_price, currency)
        errors += _money_errors(
            f"lines.{index}.out_of_scope_amount", line.out_of_scope_amount, currency
        )
    for index, point in enumerate(body.payment_schedule):
        errors += _money_errors(f"payment_schedule.{index}.amount", point.amount, currency)
    for index, payable in enumerate(body.consideration_payable):
        prefix = f"consideration_payable.{index}"
        errors += _money_errors(f"{prefix}.amount", payable.amount, currency)
        errors += _money_errors(
            f"{prefix}.distinct_good_fair_value", payable.distinct_good_fair_value, currency
        )
        errors += _money_errors(
            f"{prefix}.committed_purchases", payable.committed_purchases, currency
        )
    return errors


def _customer_id(
    session: Session, body: ContractBookedV1, errors: list[ProblemError]
) -> UUID | None:
    """The existing customer's id; None when ``customer`` names one to create."""
    if body.customer_id is not None:
        found = session.execute(
            select(customer.c.id).where(customer.c.id == body.customer_id)
        ).scalar_one_or_none()
        if found is None:
            errors.append(_error("customer_id", RULE_CUSTOMER, CUSTOMER_UNKNOWN))
        return body.customer_id
    assert body.customer is not None  # ContractBookedV1 requires one of the two members
    found = session.execute(
        select(customer.c.id).where(customer.c.code == body.customer.code)
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def _validate(
    uow: UnitOfWork, body: ContractBookedV1, *, replacing: Mapping[str, Any] | None = None
) -> tuple[UUID, UUID | None, dict[str, UUID], dict[str, UUID]]:
    """The findings of a booking; ``replacing`` is the contract whose draft the booking replaces,
    which keeps its external id, contracting entity and transaction currency (L3-1-Q-42)."""
    session = uow.session
    errors: list[ProblemError] = []
    if replacing is None:
        if repo.contract_by_external_id(session, body.external_id) is not None:
            errors.append(_error("external_id", RULE_EXTERNAL_ID, EXTERNAL_ID_TAKEN))
    elif body.external_id != replacing["external_id"]:
        errors.append(_error("external_id", RULE_CONTRACT, EXTERNAL_ID_FIXED))
    customer_id = _customer_id(session, body, errors)
    # The contracting entity is the caller's to write and is read under the caller's scope. A
    # line names its performing entity by code, and a caller is not refused a command because its
    # group reaches an entity outside the caller's scope (05 RCP-18 rev 1.82; supervisor ruling
    # R-95): that reference alone is resolved under the tenant's scope.
    own = _entity_ids(session, {body.contracting_entity_code})
    entity_id = own.get(body.contracting_entity_code)
    performing = {line.performing_entity_code for line in body.lines if line.performing_entity_code}
    with system_entity_scope(session):
        entities = {**_entity_ids(session, performing), **own}
    if entity_id is None:
        errors.append(_error("contracting_entity_code", RULE_ENTITY, ENTITY_UNKNOWN))
    elif (
        uow.principal.kind is not PrincipalKind.SYSTEM
        or CREATE_PERMISSION in uow.principal.permission_scopes
    ):
        # A SYSTEM principal that carries a scope for the permission acts on behalf of someone and
        # is held to it (an import runs within its uploader's entity scope, ruling R-29); a plain
        # SYSTEM job holds no permission and acts under its own authority.
        require_for_entity(uow.ctx, CREATE_PERMISSION, entity_id)
    if replacing is not None:
        if entity_id is not None and entity_id != replacing["contracting_entity_id"]:
            errors.append(_error("contracting_entity_code", RULE_CONTRACT, ENTITY_FIXED))
        if body.transaction_currency != str(replacing["transaction_currency"]).strip():
            errors.append(_error("transaction_currency", RULE_CONTRACT, TRANSACTION_CURRENCY_FIXED))
    enabled = session.execute(
        select(tenant_currency.c.currency_code).where(
            tenant_currency.c.currency_code == body.transaction_currency,
            tenant_currency.c.is_enabled.is_(True),
        )
    ).first()
    if enabled is None:
        errors.append(_error("transaction_currency", RULE_CURRENCY, CURRENCY_DISABLED))
    product_codes = {line.product_code for line in body.lines}
    products = {
        str(code): UUID(str(value))
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(product_codes))
        )
    }
    for index, line in enumerate(body.lines):
        if line.product_code not in products:
            errors.append(_error(f"lines.{index}.product_code", RULE_PRODUCT, PRODUCT_UNKNOWN))
        if line.performing_entity_code and line.performing_entity_code not in entities:
            errors.append(
                _error(f"lines.{index}.performing_entity_code", RULE_ENTITY, ENTITY_UNKNOWN)
            )
    errors += required_attribute_errors(session, product_codes, at=body.inception_date)
    errors += _currency_errors(body)
    if body.renewal_of_contract_id is not None:
        renewal = select(contract.c.id).where(contract.c.id == body.renewal_of_contract_id)
        if session.execute(renewal).first() is None:
            errors.append(_error("renewal_of_contract_id", RULE_CONTRACT, CONTRACT_UNKNOWN))
    if errors or entity_id is None:
        raise Problem("validation-failed", errors=errors)
    return entity_id, customer_id, products, entities


def _insert_group(
    uow: UnitOfWork, body: ContractBookedV1, contract_no: str
) -> tuple[UUID, dict[str, Any]]:
    """The singleton group of a booking and the ``after`` of its audit event, which
    ``book_contract`` writes once the contract has its id (the event names its contract)."""
    group_id = new_id()
    values = {
        "code": f"{GROUP_PREFIX}{contract_no}",
        "is_singleton": True,
        "status": CombinationStatus.APPLIED.value,
        "transaction_currency": body.transaction_currency,
        "inception_date": body.inception_date,
    }
    uow.session.execute(
        insert(combination_group).values(
            tenant_id=uow.principal.tenant_id, id=group_id, **values, **_stamps(uow)
        )
    )
    return group_id, {**values, "inception_date": body.inception_date.isoformat()}


def _insert_contract(
    uow: UnitOfWork,
    body: ContractBookedV1,
    *,
    contract_no: str,
    customer_id: UUID,
    entity_id: UUID,
    group_id: UUID,
    source_system: SourceSystem,
) -> UUID:
    contract_id = new_id()
    termination = body.termination
    uow.session.execute(
        insert(contract).values(
            tenant_id=uow.principal.tenant_id,
            id=contract_id,
            contract_no=contract_no,
            external_id=body.external_id,
            customer_id=customer_id,
            contracting_entity_id=entity_id,
            transaction_currency=body.transaction_currency,
            inception_date=body.inception_date,
            status=ContractStatus.DRAFT.value,
            combination_group_id=group_id,
            head_stream_version=0,
            signature_date=body.signature_date,
            document_ref=body.document_ref,
            payment_terms=body.payment_terms,
            termination_party=None if termination is None else termination.party,
            termination_has_penalty=None if termination is None else termination.has_penalty,
            termination_notice_days=None if termination is None else termination.notice_days,
            acceptance_clause=body.acceptance_clause,
            side_letter=body.side_letter,
            has_commercial_substance=body.has_commercial_substance,
            region=body.region,
            channel=body.channel,
            contract_type=body.contract_type,
            memo_1=body.memo_1,
            memo_2=body.memo_2,
            memo_3=body.memo_3,
            custom_attributes=dict(body.custom_attributes or {}),
            renewal_of_contract_id=body.renewal_of_contract_id,
            scope_605_35=body.scope_605_35,
            source_system=source_system.value,
            **_stamps(uow),
        )
    )
    return contract_id


def _insert_obligations(
    uow: UnitOfWork,
    body: ContractBookedV1,
    *,
    contract_id: UUID,
    event: Mapping[str, Any],
    products: Mapping[str, UUID],
    existing: Mapping[UUID, int] | None = None,
) -> list[UUID]:
    """One obligation per line the event names a new id for; ``existing`` maps the ids already
    stored to their line sequence, and new lines follow the highest (replace-draft)."""
    known = dict(existing or {})
    ids = dict(
        zip((line.obligation_key for line in body.lines), event["obligation_ids"], strict=True)
    )
    sequence = max(known.values(), default=0)
    rows: list[dict[str, Any]] = []
    for line in body.lines:
        obligation_id = UUID(str(ids[line.obligation_key]))
        if obligation_id in known:
            continue
        sequence += 1
        # LM-CL-70: <Contract Unique Name> <POB Unique ID> <SKU Name>.
        legacy_key = f"{body.external_id} {line.obligation_key} {line.product_code}"
        rows.append(
            {
                "tenant_id": uow.principal.tenant_id,
                "id": obligation_id,
                "contract_id": contract_id,
                "obligation_key": line.obligation_key,
                "product_id": products[line.product_code],
                "legacy_record_key": legacy_key,
                "created_by_event_id": event["id"],
                "parent_obligation_id": (
                    None
                    if line.bundle_parent_obligation_key is None
                    else ids[line.bundle_parent_obligation_key]
                ),
                "regrouped_from_obligation_id": None,
                "line_sequence": sequence,
                **_stamps(uow, modified=False),
            }
        )
    if rows:
        uow.session.execute(insert(obligation), rows)
    return [row["id"] for row in rows]


def book_contract(
    uow: UnitOfWork,
    *,
    body: ContractBookedV1,
    origin: Origin = "API",
    source_system: SourceSystem | None = None,
    idempotency_key: str | None = None,
    import_upload_id: UUID | None = None,
    source_record_id: UUID | None = None,
    sync_run_id: UUID | None = None,
) -> BookedContract:
    """Book ``body`` as a DRAFT contract with its singleton group, obligations and
    ``CONTRACT_BOOKED`` at stream version 1 (REQ-CON-001). An import commit names its upload and
    source record on the event (BUILD_SPEC DIN-3); an adapter sync names its source record and sync
    run (05 ADP-03; BUILD_SPEC DIN-12)."""
    entity_id, customer_id, products, _ = _validate(uow, body)
    if customer_id is None:
        assert body.customer is not None
        created = create_customer(
            uow, body=CustomerIn(code=body.customer.code, name=body.customer.name)
        )
        customer_id = created.id

    contract_no = numbering.next_number(uow, CONTRACT_SERIES)
    group_id, group_values = _insert_group(uow, body, contract_no)
    contract_id = _insert_contract(
        uow,
        body,
        contract_no=contract_no,
        customer_id=customer_id,
        entity_id=entity_id,
        group_id=group_id,
        source_system=source_system or _source(uow),
    )
    uow.audit(
        action=GROUP_CREATE_ACTION,
        object_type=GROUP_OBJECT,
        object_id=group_id,
        object_version="1",
        after=group_values,
        contract_id=contract_id,
    )
    booked = body.model_copy(update={"customer_id": customer_id, "customer": None})
    (event,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=0,
        events=[
            EventIn(
                event_type=ContractEventType.CONTRACT_BOOKED,
                effective_date=body.inception_date,
                payload=booked,
                obligation_keys=tuple(line.obligation_key for line in body.lines),
                idempotency_key=idempotency_key,
                import_upload_id=import_upload_id,
                source_record_id=source_record_id,
                sync_run_id=sync_run_id,
            )
        ],
        origin=origin,
    )

    member_id = new_id()
    uow.session.execute(
        insert(combination_group_member).values(
            tenant_id=uow.principal.tenant_id,
            id=member_id,
            combination_group_id=group_id,
            contract_id=contract_id,
            valid_from_known_at=event["recorded_at"],
            join_event_id=event["id"],
            **_stamps(uow, modified=False),
        )
    )
    obligation_ids = _insert_obligations(
        uow, body, contract_id=contract_id, event=event, products=products
    )
    audit_writer.record_facts(
        uow,
        action=BOOK_ACTION,
        object_type=CONTRACT_OBJECT,
        ids=[contract_id],
        detail={"contract_no": contract_no, "combination_group_id": str(group_id)},
        contract_id=contract_id,
    )
    audit_writer.record_facts(
        uow,
        action=MEMBER_CREATE_ACTION,
        object_type=MEMBER_OBJECT,
        ids=[member_id],
        contract_id=contract_id,
    )
    audit_writer.record_facts(
        uow,
        action=OBLIGATION_CREATE_ACTION,
        object_type=OBLIGATION_OBJECT,
        ids=obligation_ids,
        contract_id=contract_id,
    )
    session = uow.session
    return BookedContract(
        contract=repo.get_contract(session, contract_id),
        combination_group=repo.get_group(session, group_id),
        member=_member(session, member_id),
        obligations=tuple(repo.obligations(session, contract_id)),
        event=event,
    )


def _member(session: Session, member_id: UUID) -> Mapping[str, Any]:
    statement = select(combination_group_member).where(combination_group_member.c.id == member_id)
    return dict(session.execute(statement).mappings().one())


# --- CTR-4: POST /contracts and replace-draft ---------------------------------------------------


def _refuse_activation_flag(body: ContractCreateIn) -> None:
    """[J] L3-1-Q-43: activation is CTR-9's command; the flag is refused rather than ignored."""
    if body.submit_for_activation:
        raise Problem(
            "validation-failed",
            errors=[_error("submit_for_activation", RULE_ACTIVATION, ACTIVATION_LATER)],
        )


def provisional_compute(
    uow: UnitOfWork, group_id: UUID, *, engine: computation.Engine | None = None
) -> Mapping[str, Any] | None:
    """The provisional version of a DRAFT group (API-S-ContractCreate; S02-R-02 posts nothing), or
    None when the engine refuses the bundle (L3-1-Q-36). [J] BUILD_SPEC CTR-9: the booking is a
    fact-capture command, so a refused computation is stored QUARANTINED or FAILED with its
    exception item through ``compute_job.compute_group`` (DG-CMD-09; REQ-REF-014; TC-setup-20)."""
    outcome = compute_job.compute_group(
        uow, group_id, trigger=ComputationTrigger.COMMAND, engine=engine
    )
    if outcome.status is ComputationStatus.SUCCEEDED:
        return outcome.computation
    return None


def create_contract(
    uow: UnitOfWork, *, body: ContractCreateIn, engine: computation.Engine | None = None
) -> ContractOut:
    """``POST /contracts``: book ``body`` as a DRAFT contract (REQ-CON-001) and compute its
    provisional version; no subledger line while DRAFT (REQ-CON-002)."""
    _refuse_activation_flag(body)
    booked = book_contract(uow, body=body.booking(), origin=_origin(uow))
    provisional_compute(uow, UUID(str(booked.combination_group["id"])), engine=engine)
    return queries.contract_out(uow.session, UUID(str(booked.contract["id"])), now=uow.now)


def _event_type(value: object) -> str:
    return str(getattr(value, "value", value))


def _latest_booking(session: Session, contract_id: UUID) -> Mapping[str, Any]:
    """The latest ``CONTRACT_BOOKED`` of the stream that no ``EVENT_VOIDED`` names."""
    events = repo.stream(session, contract_id)
    voided = {event["supersedes_event_id"] for event in events if event["supersedes_event_id"]}
    bookings = [
        event
        for event in events
        if _event_type(event["event_type"]) == ContractEventType.CONTRACT_BOOKED.value
        and event["id"] not in voided
    ]
    return bookings[-1]


def _system_unit(uow: UnitOfWork) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, stamped with the caller's instant."""
    ctx = dataclasses.replace(uow.ctx, principal=system_principal(uow.principal.tenant_id))
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _follow_inception(uow: UnitOfWork, group_id: UUID, inception: date) -> None:
    """A singleton group's inception date follows its contract's booking (T-CON-03)."""
    principal = uow.principal
    uow.session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == principal.tenant_id,
            combination_group.c.id == group_id,
            combination_group.c.is_singleton.is_(True),
            combination_group.c.inception_date != inception,
        )
        .values(
            inception_date=inception,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=combination_group.c.row_version + 1,
        )
    )


def replace_draft(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: ContractCreateIn,
    engine: computation.Engine | None = None,
    origin: Origin | None = None,
    idempotency_key: str | None = None,
    import_upload_id: UUID | None = None,
    source_record_id: UUID | None = None,
    sync_run_id: UUID | None = None,
) -> ContractOut:
    """``POST /contracts/{id}/replace-draft`` (04 §16.1; SCREENS R-18): while the contract is
    DRAFT, in one transaction the SYSTEM principal appends ``EVENT_VOIDED`` (reason
    ``DATA_CORRECTION``) for the earlier ``CONTRACT_BOOKED``, the caller's new booking is appended
    and the provisional version recomputed. No approval is routed because nothing has posted
    (REQ-CON-002). An import names its origin, key, upload and source record on the new booking
    (BUILD_SPEC DIN-4: a setup file adds lines to a draft).

    Supervisor ruling R-102 (c) (04 §16.1 rev 1.150; item STEP1-DRAFT-REPLACE-1): the same SYSTEM
    append voids every standing ``COLLECTIBILITY_ASSESSED`` of the draft — a Step 1 judgement is
    made on the booking it judges, and a replaced draft (another customer, another price) kept a
    reviewed assessment that still satisfied the checklist and, for a draft an integration wrote,
    the auto-approval rule. A DRAFT header has no activation event, so no book status is replayed.
    The judgement records stay as they are; ``events._step1_errors`` refuses to cite them again."""
    session = uow.session
    # DG-KRN-DB-08 rev 1.36 (D-98 candidate 101a): group row first, then the contract row; every
    # check below runs under both locks.
    group_id, current = repo.lock_group_then_contract(session, contract_id)
    require_for_entity(uow.ctx, CREATE_PERMISSION, current["contracting_entity_id"])
    head = int(current["head_stream_version"])
    if expected_stream_version != head:
        raise Problem("precondition-failed", STALE_CONTRACT)
    if current["status"] != ContractStatus.DRAFT.value:
        # REQ-CON-007 (BUILD_SPEC CTR-10; CTL-006): the refusal is audited as DENIED.
        audit_writer.record_denied(
            uow.ctx,
            action=REPLACE_ACTION,
            object_type=CONTRACT_OBJECT,
            object_id=contract_id,
            permission=CREATE_PERMISSION,
            detail={"rule_id": "REQ-CON-007", "status": str(current["status"])},
            keyring=uow.keyring,
            contract_id=contract_id,
        )
        raise Problem("invalid-transition", NOT_DRAFT)
    _refuse_activation_flag(body)
    booking = body.booking()
    _, customer_id, products, _ = _validate(uow, booking, replacing=current)
    earlier = _latest_booking(session, contract_id)
    if customer_id is None:
        assert booking.customer is not None
        customer_id = create_customer(
            uow, body=CustomerIn(code=booking.customer.code, name=booking.customer.name)
        ).id
    system = _system_unit(uow)
    # Ruling R-102 (c): the assessments of the booking that is replaced, in stream order.
    assessed = [item for item in step1.read(session, contract_id).assessments if item.event_id]
    void, *_ = append_events(
        system,
        contract_id=contract_id,
        expected_stream_version=head,
        events=[
            EventIn(
                event_type=ContractEventType.EVENT_VOIDED,
                effective_date=earlier["effective_date"],
                payload=EventVoidedV1(reason_code=VOID_REASON, comment=REPLACED_COMMENT),
                supersedes_event_id=earlier["id"],
            ),
            *(
                EventIn(
                    event_type=ContractEventType.EVENT_VOIDED,
                    effective_date=item.effective_date,
                    payload=EventVoidedV1(
                        reason_code=VOID_REASON, comment=ASSESSMENT_REPLACED_COMMENT
                    ),
                    supersedes_event_id=item.event_id,
                )
                for item in assessed
            ),
        ],
        origin="SYSTEM",
    )
    booking_head = head + 1 + len(assessed)  # the head the new booking is appended at
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    replacement = booking.model_copy(update={"customer_id": customer_id, "customer": None})
    (booked,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=booking_head,
        events=[
            EventIn(
                event_type=ContractEventType.CONTRACT_BOOKED,
                effective_date=booking.inception_date,
                payload=replacement,
                obligation_keys=tuple(line.obligation_key for line in booking.lines),
                idempotency_key=idempotency_key,
                import_upload_id=import_upload_id,
                source_record_id=source_record_id,
                sync_run_id=sync_run_id,
            )
        ],
        origin=origin or _origin(uow),
    )
    _follow_inception(uow, group_id, booking.inception_date)
    existing = {
        UUID(str(row["id"])): int(row["line_sequence"])
        for row in repo.obligations(session, contract_id)
    }
    added = _insert_obligations(
        uow,
        replacement,
        contract_id=contract_id,
        event=booked,
        products=products,
        existing=existing,
    )
    uow.audit(
        action=REPLACE_ACTION,
        object_type=CONTRACT_OBJECT,
        object_id=contract_id,
        object_version=str(booking_head + 1),
        detail={
            "voided_event_id": str(void["id"]),
            "booking_event_id": str(booked["id"]),
            "voided_assessment_event_ids": [str(item.event_id) for item in assessed],
        },
        contract_id=contract_id,
    )
    if added:
        audit_writer.record_facts(
            uow,
            action=OBLIGATION_CREATE_ACTION,
            object_type=OBLIGATION_OBJECT,
            ids=added,
            contract_id=contract_id,
        )
    provisional_compute(uow, group_id, engine=engine)
    return queries.contract_out(session, contract_id, now=uow.now)


__all__: Sequence[str] = (
    "BookedContract",
    "Origin",
    "book_contract",
    "create_contract",
    "provisional_compute",
    "replace_draft",
)
