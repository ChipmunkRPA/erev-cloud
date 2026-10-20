"""Resolve a proposed deal through ordinary booking/bundle rules without retaining a contract."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from erev_engine.bundle import InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.dates import add_months
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import legal_entity
from erev_api.domain.contracts import bundles, commands
from erev_api.events.payloads import ContractBookedV1, ContractLineV1, CustomerRefV1, payload_json
from erev_api.problems import Problem
from erev_api.schemas.deal_previews import DealInputIn
from erev_api.uow import UnitOfWork


class _Captured(Exception):
    """Internal sentinel: successful assembly must still roll back its scratch booking."""

    def __init__(self, bundle: InputBundle, index: bundles.BundleIndex) -> None:
        self.bundle = bundle
        self.index = index


def booking(proposal: DealInputIn, preview_id: UUID) -> ContractBookedV1:
    """Stable natural keys keep repeated previews of the same retained request reproducible."""
    lines = []
    for index, line in enumerate(proposal.lines, start=1):
        try:
            end = (
                None
                if line.term_months is None
                else add_months(proposal.start_date, line.term_months) - timedelta(days=1)
            )
        except (ValueError, OverflowError) as exc:
            raise Problem(
                "validation-failed", "The proposed term exceeds supported dates."
            ) from exc
        lines.append(
            ContractLineV1(
                obligation_key=f"L{index}",
                product_code=line.product_code,
                quantity=line.quantity,
                total_price=line.price,
                start_date=proposal.start_date,
                end_date=end,
                performing_entity_code=line.performing_entity_code,
            )
        )
    return ContractBookedV1(
        external_id=f"DEAL-{preview_id}",
        customer_id=proposal.customer_id,
        customer=(
            None
            if proposal.customer_name is None
            else CustomerRefV1(code=f"DEAL-{preview_id}", name=proposal.customer_name)
        ),
        contracting_entity_code=proposal.entity_code,
        transaction_currency=proposal.lines[0].price.currency,
        inception_date=proposal.start_date,
        lines=tuple(lines),
    )


def resolve(
    uow: UnitOfWork, proposal: DealInputIn, preview_id: UUID
) -> tuple[InputBundle, bundles.BundleIndex]:
    """Authorize the entity before internal assembly, then roll back rows and audit buffers.

    The snapshot returned by ``bundles.build`` contains resolved natural keys and configuration
    values, not references to the temporary rows. It remains usable after rollback. No compute
    persistence/file/job helpers run inside this scratch transaction.
    """
    authorize(uow, proposal)
    body = booking(proposal, preview_id)
    # Enter system context before the savepoint so rollback cannot invalidate its restoration.
    with uow.as_system():
        try:
            with uow.savepoint():
                booked = commands.book_contract(uow, body=body, origin="SYSTEM")
                bundle = bundles.build(
                    uow.session,
                    UUID(str(booked.combination_group["id"])),
                    uow.now,
                    trigger="DRY_RUN",
                )
                # These are synthetic proposal events, not retained ledger events. Remove the
                # rolled-back customer's surrogate and global sequence from their evidence.
                if len(bundle.events) != 1 or bundle.events[0].event_type != "CONTRACT_BOOKED":
                    raise Problem("validation-failed", "A proposed deal must contain one booking.")
                payload = payload_json(body)
                event = replace(
                    bundle.events[0],
                    record_seq=1,
                    payload=bundles.engine_payload(payload),
                    payload_sha256=sha256_hex(payload),
                )
                raise _Captured(
                    replace(bundle, events=(event,)), bundles.index(uow.session, bundle)
                )
        except _Captured as captured:
            return captured.bundle, captured.index


def authorize(uow: UnitOfWork, proposal: DealInputIn) -> None:
    entity = uow.session.execute(
        select(legal_entity.c.id, legal_entity.c.functional_currency).where(
            legal_entity.c.code == proposal.entity_code,
            legal_entity.c.tenant_id == uow.principal.tenant_id,
            legal_entity.c.is_active.is_(True),
        )
    ).one_or_none()
    if entity is None:
        raise Problem("not-found", "The proposed contracting entity is unavailable.")
    require_for_entity(uow.ctx, "scenario.use", entity.id)
    if proposal.lines[0].price.currency != entity.functional_currency.strip():
        raise Problem("validation-failed", "Deal prices must use the entity's functional currency.")


def build(uow: UnitOfWork, proposal: DealInputIn, preview_id: UUID) -> InputBundle:
    return resolve(uow, proposal, preview_id)[0]
