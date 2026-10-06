"""CTR-17 regrouping: ``POST /contracts/{id}/regroup`` (04 API-R-28, §16.1; 03 REQ-CON-012;
ENGINE_SPEC S06-R-27; BUILD_SPEC CTR-17; D-98 140 Q-4).

In release 1.0 the command is taken between two DRAFT contracts and for nothing else (04 §16.1 rev
1.234; 03 REQ-CON-012 rev 1.136; supervisor's rulings of 2026-10-01). The cases are decided from
the contracts' status and from persisted postings (the engine reads none, CV-14):

- **Before any line of either contract has posted, between two DRAFT contracts** — the moved
  obligations are treated as booked in the target contract from its inception: the command creates
  the pair of T-CON-06 rows (``REMOVE_OBLIGATION`` on the source, ``ADD_OBLIGATION`` on the target,
  one ``regroup_id``), applies them at once (no approval request: nothing has posted and nothing
  can — a draft posts nothing, REQ-CON-002), appends the paired ``REGROUPED`` events (``OUT`` /
  ``IN``, each naming its row), inserts the target's obligation rows
  (``regrouped_from_obligation_id``) and recomputes both groups. Bundle assembly moves the booking
  lines (``bundles._apply_regroups``), so stage 06's ``before_posting`` sees the obligations absent
  from the source and booked in the target from inception (no boundary).
- **No posted line, and the source or the target is not a DRAFT** — refused before anything is
  written (04 §16.1 rev 1.234; ENGINE_SPEC S06-R-27 rev 1.148; item REGROUP-BEFORE-POSTING-1). A
  contract that is not a draft posts as soon as it has something to recognise: measured, an
  obligation in service since January moved from a draft into an ACTIVE contract that had posted
  nothing yet was recognised at once — 18 lines, 35,901.37 — with no activation and no
  modification approval (REQ-CON-012: "through an approved command").
- **After posting** — refused before anything is written, by the same ruling (item
  REGROUP-AFTER-POSTING-AMOUNT-1): an obligation is moved between contracts that have posted by a
  modification of each, each with its own approval. THE ROAD BELOW IS WITHDRAWN FROM 1.0 UNTIL IT
  IS REBUILT and is reached by no route; its code stays for the rebuild. As built, the same pair is
  created as DRAFT modifications (``REMOVE`` lines with ΔC = −(moved remaining consideration) on
  the source, ``ADD`` lines with +ΔC on the target) and returned as ``{modification_ids}``; the
  preparer classifies and previews each, ``submit`` routes ONE spanning ``MODIFICATION`` request
  over the pair, and its approval appends both ``REGROUPED`` events or neither
  (``modifications._approved``). Measured end to end before the ruling: ``_remaining`` reads the
  latest obligation version's remaining allocation, which is not the remainder at the regroup's
  date (95,868.49 of 96,000.00 with 35,901.37 posted), and an ``ADD`` row classified a separate
  contract books the obligation with its original service dates, so the new contract's activation
  recognised service the source had recognised already (69,254.93 posted against 35,901.37).

A regroup to a new contract (``target_contract_id`` absent) books the target as a DRAFT of the same
customer, entity and currency from the moved booking lines — from a DRAFT source, like every
regroup of release 1.0 (after posting the ADD lines would double the booking).
The pair is dated the contracting entity's current date (05 TZ-03; ``holds.entity_date``).
The command asks ``contract.create`` for the contracting entity of the source and of an existing
target (04 §16.1 rev 1.263; PRD ACT-04; item REGROUP-PERMISSION-PRD-1).
Locks: ``lock_groups_then_contracts`` over source and target (DG-KRN-DB-08; D-98 101a / 101c).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.errors import EngineError
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
# Item REGROUP-AFTER-POSTING-AMOUNT-1: the after-posting road is withdrawn from release 1.0.
AFTER_POSTING: Final = (
    "{external_id} has posted. After a posting an obligation is moved between contracts by a "
    "modification of each: a removal on the one and an addition on the other, each with its own "
    "approval."
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
    """A line of the contract has posted: 409 ``invalid-transition`` naming it (04 §16.1 rev
    1.234 (c)). The DRAFT pair this command created there is withdrawn from release 1.0 until
    its amount and its dates are rebuilt (module docstring)."""
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
            questionnaire={},
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
        if posted:
            amount = amounts[key]
        else:
            price = source.get("total_price") or {}
            amount = Decimal(str(price.get("amount", "0")))
        lines.append(
            {
                "obligation_key": key,
                "action": action,
                "product_code": source.get("product_code"),
                "quantity_delta": _signed_text(Decimal(str(source.get("quantity", "0"))), sign),
                "consideration_delta": {"amount": _signed_text(amount, sign), "currency": currency},
                "start_date": source.get("start_date"),
                "end_date": source.get("end_date"),
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
    # Release 1.0 takes two drafts and nothing else (04 §16.1 rev 1.234). The source is judged
    # here, before a new target is booked; the target after its own checks, so that a refusal
    # names no contract the caller may not see.
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
        _refuse_after_posting(session, target)
        _refuse_at_once(target)
    # From here ``posted`` is false: the after-posting branches below are the withdrawn road.
    currency = str(source["transaction_currency"]).strip()
    amounts = (
        _remaining(
            session,
            source,
            keys,
            book_code=queries.primary_book(session),
            cutoff=bundles.record_cutoff(session, uow.now),
        )
        if posted
        else {}
    )
    # 05 TZ-03: the contracting entity's current date (source and target share the entity), not
    # the UTC date of ``uow.now``.
    effective = holds.entity_date(session, source, uow.now)
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
        ),
        effective_date=effective,
        regroup_id=regroup_id,
        comment=body.comment,
        status=status,
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
        ),
        effective_date=effective,
        regroup_id=regroup_id,
        comment=body.comment,
        status=status,
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
