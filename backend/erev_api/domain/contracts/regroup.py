"""Move draft lines or prepare a retained transfer between existing active contracts.

Two unposted drafts are regrouped from inception and recomputed immediately. After posting,
two existing ACTIVE contracts may prepare a pair of DRAFT modifications for ordinary fixed
service in the same entity and functional/transaction currency. Both sides require modification
permission, classification and preview; one spanning approval applies both sides atomically.
Source book-specific remaining consideration and target inputs are retained and checked again
before submission/application. Unsupported consideration, progress, currency and destination
cases refuse before pair creation. New targets remain available only for unposted draft moves.
The effective date is today in the contracting entity's timezone. Source and target groups and
contracts are locked together before validating or writing the command.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, insert, select
from sqlalchemy.orm import Session

from erev_api import numbering
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import new_id, transitions
from erev_api.db.locking import lock_groups_then_contracts
from erev_api.db.tables import (
    contract_version,
    legal_entity,
    modification,
    obligation_version,
    subledger_line,
)
from erev_api.domain.contracts import bundles, commands, computation, holds, queries, repo
from erev_api.domain.contracts import modifications as mods
from erev_api.domain.contracts.activation import engine_problem
from erev_api.enums import ComputationTrigger, ContractStatus, ModificationKind, ModificationStatus
from erev_api.events.payloads import ContractBookedV1, ContractLineV1
from erev_api.events.stream import append_events
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.modifications import RegroupIn, RegroupOut
from erev_api.uow import UnitOfWork
from erev_engine import money
from erev_engine.boundary_basis import FixedBoundaryBasis, fixed_boundary_basis
from erev_engine.errors import EngineError

__all__ = ["regroup"]

# 04 §16.1 rev 1.263 (item REGROUP-PERMISSION-PRD-1; PRD ACT-04 rev 1.179; API-R-28): in release 1.0
# the command moves obligations between two drafts — draft editing, so it asks what booking and
# replacing a draft ask, for the entity of each contract. The two T-CON-06 rows it writes are the
# trace of the move, written by a caller who may hold no ``modification.create``. The after-posting
# road, when it is rebuilt, asks what a modification asks.
PERMISSION: Final = commands.CREATE_PERMISSION
REGROUP_ACTION: Final = "contract.regroup"
RULE_TARGET: Final = "REQ-CON-012"
KEYS_UNKNOWN: Final = "{external_id} has no obligation {key}."
TARGET_SAME: Final = "The target is the source contract; choose another contract."
TARGET_MISMATCH: Final = (
    "The target contract must share the source's contracting entity and transaction currency."
)
TARGET_STATUS: Final = "Only a draft or active contract can receive regrouped obligations."
NOTHING_MOVES: Final = "Name at least one obligation to move."
# D-98 140-A6 REGROUP-R2 / R3 / R4: refused by name before any effect.
TARGET_KEY_COLLISION: Final = (
    "{external_id} already has obligation {key}; a regrouped obligation keeps its key, so choose "
    "another target or another obligation."
)
REMAINING_BASIS_MISSING: Final = (
    "{external_id} has no computed obligation version of {key} in the {book} book at the record "
    "cutoff; compute the contract before regrouping a posted obligation."
)
TERMS_MISSING: Final = (
    "{external_id} books no line {key}; a regrouped obligation needs its booked terms."
)
# 04 §16.1 rev 1.234 (item REGROUP-BEFORE-POSTING-1): the at-once case is for two drafts.
AT_ONCE_ACTIVE: Final = (
    "{external_id} is active and has posted nothing yet. A regroup is applied at once only "
    "between two drafts: change {external_id} with a modification, which is approved."
)
AT_ONCE_OTHER: Final = (
    "{external_id} is {status}. A regroup is applied at once only between two drafts."
)
# Posted moves outside the supported existing-ACTIVE pair remain refused.
AFTER_POSTING: Final = (
    "{external_id} has posted. A retained transfer requires two existing active contracts "
    "with supported fixed service; moves involving a draft or a new target are unavailable."
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _failed(field: str, rule_id: str, message: str) -> Problem:
    return Problem(
        "validation-failed", errors=[ProblemError(field=field, rule_id=rule_id, message=message)]
    )


def _posted(session: Session, contract_ids: Sequence[UUID]) -> bool:
    """Whether any T-SL-04 line of the contracts has posted (the S06-R-27 case switch)."""
    found = session.execute(
        select(subledger_line.c.id)
        .where(subledger_line.c.contract_id.in_(list(contract_ids)))
        .limit(1)
    ).first()
    return found is not None


def _refused(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=message)],
    )


def _refuse_at_once(row: Mapping[str, Any]) -> None:
    """While no line has posted the pair is applied without a request, so both contracts are
    drafts (04 §16.1 rev 1.234): 409 ``invalid-transition`` naming a contract that is not."""
    status = _text(row["status"])
    if status == ContractStatus.DRAFT.value:
        return
    copy = AT_ONCE_ACTIVE if status == ContractStatus.ACTIVE.value else AT_ONCE_OTHER
    raise _refused(
        copy.format(external_id=row["external_id"], status=status.replace("_", " ").lower())
    )


def _refuse_after_posting(session: Session, row: Mapping[str, Any]) -> None:
    """Refuse posted contracts in unsupported destination/status combinations."""
    if _posted(session, [_uuid(row["id"])]):
        raise _refused(AFTER_POSTING.format(external_id=row["external_id"]))


def _booking_lines(session: Session, contract_id: UUID) -> dict[str, Mapping[str, Any]]:
    """The latest ``CONTRACT_BOOKED`` lines of the contract by obligation key (S01-R-20)."""
    booking = None
    for event in repo.stream(session, contract_id):
        if _text(event["event_type"]) == "CONTRACT_BOOKED":
            booking = event
    if booking is None:
        return {}
    lines = booking["payload"].get("lines") or ()
    return {str(line["obligation_key"]): line for line in lines if isinstance(line, Mapping)}


def _remaining(
    session: Session,
    source: Mapping[str, Any],
    keys: Sequence[str],
    *,
    book_code: str,
    cutoff: datetime,
) -> dict[str, Decimal]:
    """The moved remaining consideration per obligation after posting (S06-R-27; D-98 140-A6 / A9
    REGROUP-R3): the latest obligation version of ``book_code`` in the source's CURRENT combination
    group whose contract version was known by ``cutoff`` — versions are per group and book, so an
    old singleton-group version never outranks the joined group's; a key without one is refused by
    name, never the booked price."""
    contract_id = _uuid(source["id"])
    group_id = _uuid(source["combination_group_id"])
    tenant = obligation_version.c.tenant_id
    rows = session.execute(
        select(obligation_version.c.obligation_key, obligation_version.c.remaining_allocation)
        .select_from(
            obligation_version.join(
                contract_version,
                and_(
                    contract_version.c.tenant_id == tenant,
                    contract_version.c.id == obligation_version.c.contract_version_id,
                ),
            )
        )
        .where(
            obligation_version.c.contract_id == contract_id,
            obligation_version.c.combination_group_id == group_id,
            obligation_version.c.book_code == book_code,
            obligation_version.c.obligation_key.in_(list(keys)),
            contract_version.c.known_at <= cutoff,
        )
        .order_by(obligation_version.c.version_no.desc())
    ).all()
    found: dict[str, Decimal] = {}
    for key, remaining in rows:
        found.setdefault(str(key), Decimal(str(remaining)))
    missing = [key for key in keys if key not in found]
    if missing:
        raise _failed(
            "obligation_keys",
            RULE_TARGET,
            REMAINING_BASIS_MISSING.format(
                external_id=source["external_id"], key=missing[0], book=book_code
            ),
        )
    return found


def _insert_row(
    uow: UnitOfWork,
    *,
    current: Mapping[str, Any],
    kind: ModificationKind,
    lines: Sequence[Mapping[str, Any]],
    effective_date: Any,
    regroup_id: UUID,
    comment: str,
    status: ModificationStatus,
    questionnaire: Mapping[str, Any] | None = None,
) -> UUID:
    principal = uow.principal
    modification_id = new_id()
    uow.session.execute(
        insert(modification).values(
            tenant_id=principal.tenant_id,
            id=modification_id,
            modification_no=numbering.next_number(uow, mods.SERIES),
            contract_id=_uuid(current["id"]),
            contracting_entity_id=_uuid(current["contracting_entity_id"]),
            effective_date=effective_date,
            kind=kind.value,
            status=status.value,
            lines=[dict(line) for line in lines],
            questionnaire=dict(questionnaire or {}),
            currency=str(current["transaction_currency"]).strip(),
            proposed_treatments={},
            chosen_treatments={},
            ssp_basis={},
            rationale=comment,
            regroup_id=regroup_id,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    return modification_id


def _signed_text(value: Decimal, sign: int) -> str:
    """``value * sign`` as the plain decimal text 04 API-C-06 states for a quantity or an amount,
    as every other writer of a modification line writes it: never an exponent — ``str`` writes
    ``5E-7`` for 0.0000005, which the line's own payload model refuses (measured: stored by a
    regroup of two drafts) — and a zero without a sign."""
    signed = value * sign
    return format(signed if signed else abs(signed), "f")


def missing_terms(booking: Mapping[str, Mapping[str, Any]], keys: Sequence[str]) -> list[str]:
    """The moved keys the source's latest booking does not carry (REGROUP-R4). Pure."""
    return [key for key in keys if key not in booking]


def _move_lines(
    booking: Mapping[str, Mapping[str, Any]],
    keys: Sequence[str],
    amounts: Mapping[str, Decimal],
    *,
    sign: int,
    action: str,
    currency: str,
    external_id: str,
    posted: bool,
    transfer_basis: Mapping[str, FixedBoundaryBasis] | None = None,
) -> list[dict[str, Any]]:
    """The REMOVE / ADD lines of the pair (S06-R-27; D-98 140-A6 REGROUP-R4): terms from the
    source's bound booking line — a key without one refuses by name; the consideration is the
    bound remaining allocation after posting (R3, ``amounts`` complete) or the booked total price
    before posting (the booking is the basis then)."""
    lines: list[dict[str, Any]] = []
    for key in keys:
        source = booking.get(key)
        if source is None:
            raise _failed(
                "obligation_keys",
                RULE_TARGET,
                TERMS_MISSING.format(external_id=external_id, key=key),
            )
        quantity = Decimal(str(source.get("quantity", "0")))
        start, end = source.get("start_date"), source.get("end_date")
        if posted:
            if transfer_basis is None or key not in transfer_basis:
                raise _failed("obligation_keys", RULE_TARGET, "A dated transfer basis is required.")
            basis = transfer_basis[key]
            if (
                basis.obligation_key != key
                or basis.currency != currency
                or basis.contract_key != external_id
            ):
                raise _failed("obligation_keys", RULE_TARGET, "Transfer basis identity differs.")
            if basis.remaining_minor < 0 or basis.remaining_quantity <= 0:
                raise _failed(
                    "obligation_keys",
                    RULE_TARGET,
                    "Transfer needs positive remaining service and nonnegative consideration.",
                )
            scaled = basis.remaining_quantity * 10**18
            if scaled.denominator != 1:
                raise _failed(
                    "obligation_keys",
                    RULE_TARGET,
                    "Remaining quantity exceeds supported exact precision.",
                )
            with localcontext(money.DECIMAL_CONTEXT):
                quantity = Decimal(scaled.numerator) / Decimal(10**18)
            amount = amounts[key]
            start = max(
                basis.effective_date, basis.service_start_date or basis.effective_date
            ).isoformat()
            end = None if basis.service_end_date is None else basis.service_end_date.isoformat()
        else:
            price = source.get("total_price") or {}
            amount = Decimal(str(price.get("amount", "0")))
        lines.append(
            {
                "obligation_key": key,
                "action": action,
                "product_code": source.get("product_code"),
                "quantity_delta": _signed_text(quantity, sign),
                "consideration_delta": {"amount": _signed_text(amount, sign), "currency": currency},
                "start_date": start,
                "end_date": end,
                "stratification": source.get("stratification"),
                "selling_entity_code": source.get("performing_entity_code"),
                "account_codes": source.get("account_overrides"),
                "ssp_version_label": source.get("ssp_version_label"),
            }
        )
    return lines


def _new_target(
    uow: UnitOfWork,
    source: Mapping[str, Any],
    booking: Mapping[str, Mapping[str, Any]],
    keys: Sequence[str],
) -> dict[str, Any]:
    """A DRAFT target booked from the moved lines (REQ-CON-012 "or to a new contract")."""
    code = str(
        uow.session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == source["contracting_entity_id"])
        ).scalar_one()
    )
    lines = tuple(
        ContractLineV1.model_validate({**booking[key], "obligation_key": key}) for key in keys
    )
    body = ContractBookedV1(
        external_id=f"{source['external_id']}-REGROUP-{uow.now.strftime('%Y%m%d%H%M%S')}",
        customer_id=_uuid(source["customer_id"]),
        contracting_entity_code=code,
        transaction_currency=str(source["transaction_currency"]).strip(),
        inception_date=min(
            (line.start_date for line in lines if line.start_date is not None),
            default=source["inception_date"],
        ),
        lines=lines,
    )
    booked = commands.book_contract(uow, body=body, origin=_origin(uow))
    return dict(booked.contract)


def _origin(uow: UnitOfWork) -> Any:
    return "UI" if uow.principal.kind.value == "USER" else "API"


def regroup(uow: UnitOfWork, *, contract_id: UUID, body: RegroupIn) -> RegroupOut:
    """``POST /contracts/{id}/regroup``: move ``obligation_keys`` to ``target_contract_id`` (or a
    new contract); 201 ``{modification_ids}`` (04 §16.1)."""
    session = uow.session
    keys = sorted({str(key) for key in body.obligation_keys})
    if not keys:
        raise _failed("obligation_keys", RULE_TARGET, NOTHING_MOVES)
    if body.target_contract_id is not None and body.target_contract_id == contract_id:
        raise _failed("target_contract_id", RULE_TARGET, TARGET_SAME)
    wanted = [contract_id] + ([body.target_contract_id] if body.target_contract_id else [])
    locked = lock_groups_then_contracts(session, wanted)
    source = locked[contract_id]
    require_for_entity(uow.ctx, PERMISSION, _uuid(source["contracting_entity_id"]))
    source_obligations = mods._source_obligations(session, contract_id)
    missing = [key for key in keys if key not in source_obligations]
    if missing:
        raise _failed(
            "obligation_keys",
            "T-CON-10",
            KEYS_UNKNOWN.format(external_id=source["external_id"], key=missing[0]),
        )
    posted = _posted(session, wanted)
    booking = _booking_lines(session, contract_id)
    # D-98 140-A9 REGROUP-R4: the moved terms are validated BEFORE either target branch and any
    # write (a new target's booking read them first).
    lacking = missing_terms(booking, keys)
    if lacking:
        raise _failed(
            "obligation_keys",
            RULE_TARGET,
            TERMS_MISSING.format(external_id=source["external_id"], key=lacking[0]),
        )
    retained_transfer = (
        posted
        and body.target_contract_id is not None
        and _text(source["status"]) == ContractStatus.ACTIVE.value
        and _text(locked[body.target_contract_id]["status"]) == ContractStatus.ACTIVE.value
    )
    if retained_transfer:
        require_for_entity(uow.ctx, mods.CREATE_PERMISSION, _uuid(source["contracting_entity_id"]))
    else:
        _refuse_after_posting(session, source)
        if not posted:
            _refuse_at_once(source)
    if body.target_contract_id is None:
        target = _new_target(uow, source, booking, keys)
        target_id = _uuid(target["id"])
        # the new contract already carries the moved lines: the IN row records the move, the
        # bundle move is a no-op for it
    else:
        target_id = body.target_contract_id
        target = locked[target_id]
        require_for_entity(uow.ctx, PERMISSION, _uuid(target["contracting_entity_id"]))
        if (
            target["contracting_entity_id"] != source["contracting_entity_id"]
            or str(target["transaction_currency"]).strip()
            != str(source["transaction_currency"]).strip()
        ):
            raise _failed("target_contract_id", RULE_TARGET, TARGET_MISMATCH)
        if _text(target["status"]) not in (ContractStatus.DRAFT.value, ContractStatus.ACTIVE.value):
            raise _failed("target_contract_id", RULE_TARGET, TARGET_STATUS)
        # D-98 140-A6 REGROUP-R2: a moved obligation keeps its key; a collision on the target is
        # refused before any insert or event
        collisions = sorted(set(keys) & set(mods._source_obligations(session, target_id)))
        if collisions:
            raise _failed(
                "obligation_keys",
                RULE_TARGET,
                TARGET_KEY_COLLISION.format(external_id=target["external_id"], key=collisions[0]),
            )
        if retained_transfer:
            require_for_entity(
                uow.ctx, mods.CREATE_PERMISSION, _uuid(target["contracting_entity_id"])
            )
            functional = session.scalar(
                select(legal_entity.c.functional_currency).where(
                    legal_entity.c.id == source["contracting_entity_id"]
                )
            )
            if str(functional).strip() != str(source["transaction_currency"]).strip():
                raise _failed(
                    "target_contract_id",
                    RULE_TARGET,
                    "Foreign-currency transfers require retained historical FX transfer treatment.",
                )
        else:
            _refuse_after_posting(session, target)
            _refuse_at_once(target)
    currency = str(source["transaction_currency"]).strip()
    # 05 TZ-03: use the contracting entity's current date, not the UTC date.
    effective = holds.entity_date(session, source, uow.now)
    transfer_basis: dict[str, FixedBoundaryBasis] = {}
    amounts: dict[str, Decimal] = {}
    book_lines: dict[str, dict[str, list[dict[str, Any]]]] = {"OUT": {}, "IN": {}}
    basis_evidence: dict[str, Any] = {}
    target_digest: str | None = None
    if posted:
        original = bundles.build(session, _uuid(source["combination_group_id"]), uow.now)
        if retained_transfer:
            target_basis = bundles.build(session, _uuid(target["combination_group_id"]), uow.now)
            target_digest = target_basis.sha256()
            target_header = next(
                c for c in target_basis.contracts if c.external_id == target["external_id"]
            )
            for book in target_basis.books:
                if target_header.contracting_entity_code not in book.entity_codes:
                    continue
                if book.book_code == "LEGACY":
                    raise _failed(
                        "target_contract_id",
                        RULE_TARGET,
                        "Legacy target transfer basis is unavailable.",
                    )
                try:
                    fixed_boundary_basis(
                        target_basis,
                        book_code=book.book_code,
                        effective_date=effective,
                        contract_key=str(target["external_id"]),
                        obligation_keys=tuple(sorted(mods._source_obligations(session, target_id))),
                        require_fixed_transfer=True,
                        require_remaining_service=False,
                    )
                except (ValueError, EngineError) as error:
                    raise _failed("target_contract_id", RULE_TARGET, str(error)) from error
        primary = queries.primary_book(session)
        source_header = next(
            c for c in original.contracts if c.external_id == source["external_id"]
        )
        for book in original.books:
            if source_header.contracting_entity_code not in book.entity_codes:
                continue
            if book.book_code == "LEGACY":
                raise _failed(
                    "obligation_keys",
                    RULE_TARGET,
                    "Legacy-book transfers need separate retained recognition evidence.",
                )
            try:
                measured = fixed_boundary_basis(
                    original,
                    book_code=book.book_code,
                    effective_date=effective,
                    contract_key=str(source["external_id"]),
                    obligation_keys=tuple(keys),
                    require_fixed_transfer=True,
                )
            except (ValueError, EngineError) as error:
                raise _failed("obligation_keys", RULE_TARGET, str(error)) from error
            basis = {item.obligation_key: item for item in measured}
            scale = 10 ** original.currencies[currency].minor_unit
            with localcontext(money.DECIMAL_CONTEXT):
                book_amounts = {
                    item.obligation_key: Decimal(item.remaining_minor) / Decimal(scale)
                    for item in measured
                }
            for direction, sign, action in (("OUT", -1, mods.REMOVE), ("IN", 1, mods.ADD)):
                book_lines[direction][book.book_code] = _move_lines(
                    booking,
                    keys,
                    book_amounts,
                    sign=sign,
                    action=action,
                    currency=currency,
                    external_id=str(source["external_id"]),
                    posted=True,
                    transfer_basis=basis,
                )
            from .regroup_freshness import snapshot

            basis_evidence[book.book_code] = snapshot(measured)
            if book.book_code == primary:
                transfer_basis, amounts = basis, book_amounts
        if not transfer_basis:
            raise _failed(
                "obligation_keys", RULE_TARGET, "The source lacks a primary-book transfer basis."
            )
    regroup_id = new_id()
    status = ModificationStatus.DRAFT if posted else ModificationStatus.APPLIED
    out_id = _insert_row(
        uow,
        current=source,
        kind=ModificationKind.REMOVE_OBLIGATION,
        lines=_move_lines(
            booking,
            keys,
            amounts,
            sign=-1,
            action=mods.REMOVE,
            currency=currency,
            external_id=str(source["external_id"]),
            posted=posted,
            transfer_basis=transfer_basis,
        ),
        effective_date=effective,
        regroup_id=regroup_id,
        comment=body.comment,
        status=status,
        questionnaire={
            "regroup_book_lines": book_lines["OUT"],
            "regroup_source_basis": basis_evidence,
            **({"regroup_target_input_sha256": target_digest} if target_digest else {}),
        }
        if posted
        else None,
    )
    in_id = _insert_row(
        uow,
        current=target,
        kind=ModificationKind.ADD_OBLIGATION,
        lines=_move_lines(
            booking,
            keys,
            amounts,
            sign=1,
            action=mods.ADD,
            currency=currency,
            external_id=str(source["external_id"]),
            posted=posted,
            transfer_basis=transfer_basis,
        ),
        effective_date=effective,
        regroup_id=regroup_id,
        comment=body.comment,
        status=status,
        questionnaire={
            "regroup_book_lines": book_lines["IN"],
            "regroup_source_basis": basis_evidence,
            **({"regroup_target_input_sha256": target_digest} if target_digest else {}),
        }
        if posted
        else None,
    )
    uow.audit(
        action=REGROUP_ACTION,
        object_type=mods.OBJECT,
        object_id=out_id,
        object_version="1",
        after={
            "regroup_id": str(regroup_id),
            "source_contract_id": str(contract_id),
            "target_contract_id": str(target_id),
            "obligation_keys": keys,
            "posted": posted,
            "modification_ids": [str(out_id), str(in_id)],
        },
        comment=body.comment,
        contract_ids=[contract_id, target_id],
    )
    if posted:
        return RegroupOut(modification_ids=[out_id, in_id])
    # Before posting: the pair applies now — REGROUPED OUT on the source, IN on the target.
    out_row = mods._row(session, out_id)
    in_row = mods._row(session, in_id)
    (out_event,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(source["head_stream_version"]),
        events=[mods._regrouped_event(out_row, in_row, approval_request_id=None)],
        origin=_origin(uow),
    )
    (in_event,) = append_events(
        uow,
        contract_id=target_id,
        expected_stream_version=int(target["head_stream_version"]),
        events=[
            mods._regrouped_event(
                in_row,
                out_row,
                approval_request_id=None,
                lines=[{**booking[key], "obligation_key": key} for key in keys],
            )
        ],
        origin=_origin(uow),
    )
    if body.target_contract_id is not None:
        mods._insert_created_obligations(
            uow,
            current=target,
            event=in_event,
            keys=keys,
            products={
                source_obligations[k]["product_code"]: _uuid(source_obligations[k]["product_id"])
                for k in keys
            },
            product_codes={k: str(source_obligations[k]["product_code"]) for k in keys},
            regrouped_from={k: _uuid(source_obligations[k]["id"]) for k in keys},
        )
    for row_id, event in ((out_id, out_event), (in_id, in_event)):
        transitions.apply(
            session,
            mods.OBJECT,
            row_id,
            to_status=None,
            expected_status=ModificationStatus.APPLIED.value,
            set_values={"applied_event_id": _uuid(event["id"]), **mods._bump(uow)},
        )
    groups = {_uuid(source["combination_group_id"]), _uuid(target["combination_group_id"])}
    for group_id in sorted(groups):
        try:
            computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
        except EngineError as error:
            raise engine_problem(error) from error
    return RegroupOut(modification_ids=[out_id, in_id])
