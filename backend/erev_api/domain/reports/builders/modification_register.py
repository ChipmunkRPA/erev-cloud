"""RPT-14 ``modification_register`` Modification register — the governed ``MODIFICATION_REGISTER``
dataset (SCREENS_B §5.6.2 RPT-14 rev 1.23; ENGINE_SPEC_B §15.2.7 S15-R-20a / S15-R-20c; 04
T-CON-06, T-CLS-05; 03 REQ-MOD-014; PRD SM-03 "register row"; CTL-007 evidence; BUILD_SPEC CTR-17
slice 1 (D-98 140 Q-8 option A, 140-A1) and RPS-8; design note
``docs/reviews/loop/prod/F-CTR-CTR17-DESIGN-NOTE.md`` §10; lane F-CTR).

One row per (T-CON-06 modification, ``lines[].obligation_key``) of the modifications whose
contracting entity is in scope, whose ``effective_date`` lies in the range and whose ``status`` is
in the run's ``status`` set (default "Applied", "Approved"), read as of the run's ``known_at``
(D-98 96: rows recorded by the cutoff). The frozen-dataset shape of S15-R-20a: the key code columns
``contract_external_id``, ``modification_no``, ``obligation_key`` first (F-CLO's ``KeySpec``), then
the code and measure columns, then the display attributes. ``currency`` is on every row; the two
declared measures ``tp_change`` and ``catch_up_amount`` are typed API-S-Money cells in that currency
(never bare decimals); an optional cell is empty (None), never 0; the dataset carries no TOTAL row —
the totals per currency are control totals.

Measure sources by status (S15-R-20c): ``APPLIED`` reads the run's book — the application version
is bound deterministically: the contract version of the group the applied event's OWNER contract
belonged to when the event was recorded (T-CON-04 membership by ``recorded_at``) whose
``cause_event_ids`` holds the event and whose ``known_at`` is by the cutoff; ``tp_change`` is its
``transaction_price`` minus its predecessor's, ``catch_up_amount`` its obligation version of the
modification's contract and the line's key (``last_modification_id`` is null for every native
computation and plays no part); two candidates, or a version whose cause set holds several
modification events (a shared catch-up), refuse by name — never an arbitrary first match, a split
or a substituted zero (D-98 140-A10 / A11); ``APPROVED`` / ``SUBMITTED`` read the stored impact
preview (``impact_preview_sha256`` is the provenance); ``DRAFT``, ``REJECTED`` and ``VOIDED`` carry
empty measures. ``currency_view``
``transaction`` is served; ``functional`` only when every row's currency is its entity's functional
currency, else the run refuses by name (RPT-07 pattern) — no FX conversion here. A row whose key
column cannot be supplied, or two rows of one key, refuse by name (``ModificationRegisterRefusal``).
The as-locked surface (``period_lock_id``) is CLO-8b's; a lock source here refuses by name.

F-RPS's registry entry ``SNAPSHOT_DATASETS["MODIFICATION_REGISTER"]`` wraps ``dataset_rows`` /
``control_totals`` into the EDS-6 encoding; this module provides the rows and totals only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    approval_decision,
    approval_request,
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    judgement_record,
    legal_entity,
    modification,
    obligation_version,
)
from erev_api.domain.contracts import modifications
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_history import date_range
from erev_api.domain.reports.builders.out_of_period_register import event_key, refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalDecisionKind, ModificationStatus
from erev_api.uow import UnitOfWork

CODE: Final = "modification_register"
KEY_COLUMNS: Final = ("contract_external_id", "modification_no", "obligation_key")  # S15-R-20c
MEASURES: Final = ("tp_change", "catch_up_amount")  # the declared measures (D-98 87)
DEFAULT_CURRENCY_VIEW: Final = "transaction"  # SCREENS_B RPT-14 rev 1.23 "transaction served"
STATUS_DEFAULT: Final = ("APPLIED", "APPROVED")  # SCREENS_B RPT-14 `status` default
QUESTIONS: Final = (
    "added_goods_distinct",
    "priced_at_ssp",
    "remaining_goods_distinct_from_transferred",
)
FUNCTIONAL_ONLY: Final = (
    "The functional currency view is available when every modification is in its entity's "
    "functional currency; choose the transaction view."
)
# D-98 140-A8 REGISTER-CUTOFF-1: T-CON-06 keeps no row history — status, effective date or any
# authored member — so an explicit historical read whose cutoff precedes a row's last change cannot
# state that row as of the cutoff. A13 / Codex 2043: the copy names the members that can have moved
# (the row carries only ``updated_at``; which one moved is not knowable and is not asserted).
# D-98 140-A10 / A11 REGISTER-CATCHUP-1: attribution refusals by name.
APPLICATION_AMBIGUOUS: Final = (
    "The register cannot attribute modification {modification_no}: {count} contract versions of "
    "the {book} book in its application group hold its applied event; the application version is "
    "not determinable."
)
CATCH_UP_SHARED: Final = (
    "The register cannot attribute the catch-up of modification {modification_no}: its application "
    "version was caused by {count} modification events together, and a shared catch-up is never "
    "split among them."
)
MODIFICATION_EVENT_TYPES: Final = frozenset(
    {"CONTRACT_AMENDED", "CONTRACT_TERMINATED", "REGROUPED"}
)
HISTORY_UNAVAILABLE: Final = (
    "The modification register cannot state {modification_no} as of {cutoff}: the row last "
    "changed at {updated_at} — its status, effective date or another authored member moved after "
    "the cutoff and T-CON-06 keeps no row history, so the population as of {cutoff} is "
    "unavailable (not reconstructed, not narrowed). Run the register at a later known_at or "
    "current."
)
STATUS_HISTORY_UNAVAILABLE: Final = HISTORY_UNAVAILABLE  # the A8 name, kept
# E-25 labels (SCREENS_B RPT-14 "Kind").
KIND_LABELS: Final[Mapping[str, str]] = {
    "ADD_OBLIGATION": "Add obligation",
    "REMOVE_OBLIGATION": "Remove obligation",
    "QUANTITY_CHANGE": "Quantity change",
    "PRICE_CHANGE": "Price change",
    "TERM_CHANGE": "Term change",
    "UPGRADE": "Upgrade",
    "DOWNGRADE": "Downgrade",
    "CO_TERM": "Co-term",
    "RENEWAL": "Renewal",
    "EARLY_RENEWAL": "Early renewal",
    "CANCELLATION": "Cancellation",
    "TERMINATION": "Termination",
    "VC_CHANGE": "VC change",
    "OTHER": "Other",
}
# E-23 labels (SCREENS_B RPT-14 "Proposed treatment" / "Chosen treatment").
TREATMENT_LABELS: Final[Mapping[str, str]] = {
    "SEPARATE_CONTRACT": "Separate contract",
    "PROSPECTIVE": "Prospective",
    "CUMULATIVE_CATCH_UP": "Cumulative catch-up",
    "MIXED": "Mixed",
    "LEGACY_PROSPECTIVE": "Legacy prospective",
    "LEGACY_RETROSPECTIVE": "Legacy retrospective",
    "LEGACY_POB_VC": "Legacy obligation price change",
}
# S15-R-20c: key code columns first, then code and measure columns, then attributes.
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("modification_no", "Modification", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("kind", "Kind", "code"),
    Column("effective_date", "Effective date", "date"),
    Column("created_at", "Entered", "timestamp"),
    Column("status", "Status", "code"),
    Column("proposed_treatment", "Proposed treatment", "code"),
    Column("chosen_treatment", "Chosen treatment", "code"),
    Column("treatment_override", "Override", "boolean"),
    Column("judgement_no", "Judgement", "code"),
    Column("added_goods_distinct", "Added goods distinct", "boolean"),
    Column("priced_at_ssp", "Priced at SSP", "boolean"),
    Column("remaining_goods_distinct_from_transferred", "Remaining goods distinct", "boolean"),
    Column("currency", "Currency", "code"),
    Column("tp_change", "Transaction price change", "money"),
    Column("catch_up_amount", "Catch-up", "money"),
    Column("approval_request_no", "Approval request", "code"),
    Column("approved_at", "Approved", "timestamp"),
    Column("impact_preview_sha256", "Preview", "code"),
    Column("applied_event_key", "Applied event", "code"),
    Column("reference", "Reference", "text"),
    Column("kind_label", "Kind (label)", "text"),
    Column("proposed_treatment_label", "Proposed treatment (label)", "text"),
    Column("chosen_treatment_label", "Chosen treatment (label)", "text"),
    Column("preparer", "Preparer", "text"),
    Column("approvers", "Approver", "text"),
)
# SCREENS_B RPT-14 grid field → dataset column (a dotted questionnaire field is its last segment).
GRID_FIELDS: Final[Mapping[str, str]] = {
    "modification_no": "modification_no",
    "reference": "reference",
    "contract_external_id": "contract_external_id",
    "kind": "kind",
    "effective_date": "effective_date",
    "created_at": "created_at",
    "questionnaire.added_goods_distinct": "added_goods_distinct",
    "questionnaire.priced_at_ssp": "priced_at_ssp",
    "questionnaire.remaining_goods_distinct_from_transferred": (
        "remaining_goods_distinct_from_transferred"
    ),
    "obligation_key": "obligation_key",
    "proposed_treatment": "proposed_treatment",
    "chosen_treatment": "chosen_treatment",
    "status": "status",
    "preparer": "preparer",
    "approvers": "approvers",
    "approved_at": "approved_at",
    "currency": "currency",
    "tp_change": "tp_change",
    "catch_up_amount": "catch_up_amount",
}


class ModificationRegisterRefusal(RuntimeError):
    """A governed key column cannot be supplied, or a key occurs twice: refused by name
    (S15-R-20a / S15-R-20c), never a proxy, a default or a dropped row."""

    def __init__(self, column: str, detail: str) -> None:
        self.column = column
        self.detail = detail
        super().__init__(f"{CODE}: {column}: {detail}")


@dataclass(frozen=True, slots=True)
class Source:
    """One modification as the register reads it — the T-CON-06 members the rows copy and the
    measures already resolved per obligation key (None = an empty cell)."""

    modification_no: str
    reference: str | None
    contract_external_id: str
    entity_code: str
    functional_currency: str
    kind: str
    effective_date: date
    created_at: datetime
    status: str
    proposed_treatments: Mapping[str, str]
    chosen_treatments: Mapping[str, str]
    judgement_no: str | None
    questionnaire: Mapping[str, Any]
    obligation_keys: tuple[str, ...]  # lines[].obligation_key in line order
    currency: str
    tp_change: Decimal | None
    catch_up: Mapping[str, Decimal] | None  # per obligation key; None = no measure source
    approval_request_no: str | None
    approved_at: datetime | None
    impact_preview_sha256: str | None
    applied_event_key: str | None
    preparer: str
    approvers: str | None


def applied_event_reference(owner: tuple[str, int] | None) -> str | None:
    """REGISTER-EVENT-1: ``event:<owner external id>:<stream version>`` of the applied event —
    the OWNER contract's id (the new contract for a separate-contract booking), CV-21-encoded; None
    until APPLIED. The row key keeps the original contract. Pure."""
    return None if owner is None else event_key(owner[0], owner[1])


def historical_status_refusal(
    rows: Iterable[Mapping[str, Any]], *, cutoff: datetime, historical: bool
) -> str | None:
    """REGISTER-CUTOFF-1: the refusal copy for an explicit historical read whose cutoff precedes a
    row's last change (T-CON-06 keeps no row history — status, effective date or any authored
    member), else None; every row in scope recorded by the cutoff is inspected, so a later edit to a
    row outside the selected range refuses too (named unavailable history, never a narrowed output —
    Codex 2043). A live run (record basis) never refuses here. Pure."""
    if not historical:
        return None
    for row in rows:
        if row["updated_at"] > cutoff:
            return HISTORY_UNAVAILABLE.format(
                modification_no=row["modification_no"],
                cutoff=cutoff.isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
    return None


def population_filter(
    candidates: Iterable[Mapping[str, Any]],
    *,
    from_date: date,
    to_date: date,
    statuses: Iterable[str],
) -> list[dict[str, Any]]:
    """The run's rows among the inspected candidates: effective date in range and status in the
    run's set — applied AFTER the historical inspection (REGISTER-CUTOFF-1; D-98 140-A13). Pure."""
    wanted = {str(status) for status in statuses}
    return [
        dict(row)
        for row in candidates
        if from_date <= row["effective_date"] <= to_date and _text(row["status"]) in wanted
    ]


def _label(table: Mapping[str, str], code: str | None) -> str | None:
    return None if code is None else table.get(code, code)


def _answer(questionnaire: Mapping[str, Any], key: str, question: str) -> bool | None:
    """The questionnaire answer of ``question`` for obligation ``key``: a per-obligation object
    (``questionnaire[key][question]``) wins over a contract-level answer; unanswered → None."""
    scoped = questionnaire.get(key)
    if isinstance(scoped, Mapping) and question in scoped:
        value = scoped.get(question)
    else:
        value = questionnaire.get(question)
    return None if value is None else bool(value)


def _money(amount: Decimal | None, currency: str) -> dict[str, str] | None:
    return None if amount is None else tie_outs.money(amount, currency)


def dataset_rows(sources: Iterable[Source]) -> list[dict[str, Any]]:
    """The register rows: one per (modification, obligation key) in row-key order (S15-R-20c);
    ``row_key`` ``modification:<modification no>:<obligation key>``. Pure: CPU-testable."""
    rows: list[dict[str, Any]] = []
    for item in sources:
        for key in item.obligation_keys:
            proposed = item.proposed_treatments.get(key)
            chosen = item.chosen_treatments.get(key)
            catch_up = None if item.catch_up is None else item.catch_up.get(key)
            rows.append(
                {
                    "row_key": f"modification:{item.modification_no}:{key}",
                    "contract_external_id": item.contract_external_id,
                    "modification_no": item.modification_no,
                    "obligation_key": key,
                    "kind": item.kind,
                    "effective_date": item.effective_date,
                    "created_at": item.created_at,
                    "status": item.status,
                    "proposed_treatment": proposed,
                    "chosen_treatment": chosen,
                    "treatment_override": (
                        None if proposed is None and chosen is None else proposed != chosen
                    ),
                    "judgement_no": item.judgement_no,
                    **{
                        question: _answer(item.questionnaire, key, question)
                        for question in QUESTIONS
                    },
                    "currency": item.currency,
                    "tp_change": _money(item.tp_change, item.currency),
                    "catch_up_amount": _money(catch_up, item.currency),
                    "approval_request_no": item.approval_request_no,
                    "approved_at": item.approved_at,
                    "impact_preview_sha256": item.impact_preview_sha256,
                    "applied_event_key": item.applied_event_key,
                    "reference": item.reference,
                    "kind_label": _label(KIND_LABELS, item.kind),
                    "proposed_treatment_label": _label(TREATMENT_LABELS, proposed),
                    "chosen_treatment_label": _label(TREATMENT_LABELS, chosen),
                    "preparer": item.preparer,
                    "approvers": item.approvers,
                }
            )
    rows.sort(key=lambda row: tuple(str(row[column]) for column in KEY_COLUMNS))
    return rows


def check_key_columns(rows: Sequence[Mapping[str, Any]]) -> None:
    """S15-R-20a shape statement: every row supplies the three key columns and the key occurs
    once; otherwise refuse by name."""
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        values = tuple(row.get(column) for column in KEY_COLUMNS)
        for column, value in zip(KEY_COLUMNS, values, strict=True):
            if value is None or str(value) == "":
                raise ModificationRegisterRefusal(
                    column, f"row {row.get('row_key')!r} supplies no {column}"
                )
        key = tuple(str(value) for value in values)
        if key in seen:
            raise ModificationRegisterRefusal(
                "obligation_key", f"the key {':'.join(key)} occurs twice"
            )
        seen.add((key[0], key[1], key[2]))


def control_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``row_count``, ``modification_count`` and per currency ``tp_change_total`` (one per
    modification, not per line) and ``catch_up_total`` (S15-R-20c)."""
    tp_totals: dict[str, Decimal] = {}
    catch_up_totals: dict[str, Decimal] = {}
    counted: set[str] = set()
    for row in rows:
        currency = str(row["currency"])
        tp_change = row.get("tp_change")
        if tp_change is not None and row["modification_no"] not in counted:
            counted.add(str(row["modification_no"]))
            tie_outs.add(tp_totals, currency, Decimal(str(tp_change["amount"])))
        catch_up = row.get("catch_up_amount")
        if catch_up is not None:
            tie_outs.add(catch_up_totals, currency, Decimal(str(catch_up["amount"])))
    return {
        "row_count": len(rows),
        "modification_count": len({str(row["modification_no"]) for row in rows}),
        "tp_change_total": tie_outs.by_currency(tp_totals),
        "catch_up_total": tie_outs.by_currency(catch_up_totals),
    }


def check_view(view: str, sources: Sequence[Source]) -> None:
    """``transaction`` (the served default) always; ``functional`` only when every modification
    is in its entity's functional currency, else refused by name (RPT-07 pattern)."""
    if view != DEFAULT_CURRENCY_VIEW and any(
        item.currency != item.functional_currency for item in sources
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _statuses(params: ReportParams) -> tuple[str, ...]:
    given = params.parameters.get("status")
    if not given:
        return STATUS_DEFAULT
    return tuple(_text(ModificationStatus(_text(item))) for item in given)


def _approvers(
    session: Session, request_ids: Sequence[UUID], *, cutoff: datetime
) -> tuple[dict[UUID, list[tuple[UUID | None, str]]], dict[UUID, datetime]]:
    """Per request: its APPROVE / AUTO_APPROVE deciders decided by ``cutoff`` in decision order and
    the last such decision's time (``approved_at``) — REGISTER-CUTOFF-1."""
    wanted = sorted(set(request_ids), key=str)
    deciders: dict[UUID, list[tuple[UUID | None, str]]] = {}
    approved_at: dict[UUID, datetime] = {}
    if not wanted:
        return deciders, approved_at
    statement = (
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decided_at,
        )
        .where(
            approval_decision.c.approval_request_id.in_(wanted),
            approval_decision.c.decision.in_(
                [ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value]
            ),
            approval_decision.c.decided_at <= cutoff,
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    )
    for request_id, approver_id, kind, decided_at in session.execute(statement):
        key = UUID(str(request_id))
        deciders.setdefault(key, []).append(
            (None if approver_id is None else UUID(str(approver_id)), _text(kind))
        )
        approved_at[key] = decided_at
    return deciders, approved_at


def bind_application_version(
    candidates: Iterable[Mapping[str, Any]], *, group_id: UUID, modification_no: str, book_code: str
) -> Mapping[str, Any] | None:
    """D-98 140-A11 REGISTER-CATCHUP-1: of the versions whose ``cause_event_ids`` hold the applied
    event, the one of the group the event's owner belonged to at application (a later approved JOIN
    re-includes the event in the new group's first version, so two versions can match); none → no
    measures yet (empty cells); more than one → refused by name, never an arbitrary first match.
    Pure."""
    matching = [c for c in candidates if UUID(str(c["combination_group_id"])) == group_id]
    if not matching:
        return None
    if len(matching) > 1:
        raise ModificationRegisterRefusal(
            "catch_up_amount",
            APPLICATION_AMBIGUOUS.format(
                modification_no=modification_no, count=len(matching), book=book_code
            ),
        )
    return matching[0]


def shared_catch_up(cause_event_types: Iterable[str]) -> int:
    """The number of modification-kind events among a version's causes (D-98 140-A10): more than
    one means the version's catch-up is shared and cannot be attributed to one modification.
    Pure."""
    return sum(1 for kind in cause_event_types if str(kind) in MODIFICATION_EVENT_TYPES)


def applied_catch_up(
    version_rows: Iterable[Mapping[str, Any]], *, contract_id: UUID, keys: Iterable[str]
) -> dict[str, Decimal]:
    """REGISTER-CATCHUP-1: the catch-up per line key from the obligation versions of THE contract
    version the applied event caused — the modification's contract and its line keys are the
    persisted provenance (``cause_event_ids``); ``last_modification_id`` is null for every native
    computation and is never used; a key without such an obligation version is absent (an empty
    cell), never a substituted zero. Pure."""
    wanted = set(keys)
    found: dict[str, Decimal] = {}
    for row in version_rows:
        key = str(row["obligation_key"])
        if key in wanted and UUID(str(row["contract_id"])) == contract_id and key not in found:
            found[key] = Decimal(str(row["catch_up_amount"]))
    return found


def _application_groups(session: Session, event_ids: Sequence[UUID]) -> dict[UUID, UUID]:
    """Per applied event: the combination group its OWNER contract belonged to when the event was
    recorded (T-CON-04 membership: ``valid_from_known_at <= recorded_at < valid_to_known_at``)."""
    found: dict[UUID, UUID] = {}
    if not event_ids:
        return found
    member = combination_group_member
    rows = session.execute(
        select(contract_event.c.id, member.c.combination_group_id)
        .select_from(
            contract_event.join(
                member,
                and_(
                    member.c.tenant_id == contract_event.c.tenant_id,
                    member.c.contract_id == contract_event.c.contract_id,
                    member.c.valid_from_known_at <= contract_event.c.recorded_at,
                    or_(
                        member.c.valid_to_known_at.is_(None),
                        member.c.valid_to_known_at > contract_event.c.recorded_at,
                    ),
                ),
            )
        )
        .where(contract_event.c.id.in_(list(event_ids)))
    ).all()
    for event_id, group_id in rows:
        found.setdefault(UUID(str(event_id)), UUID(str(group_id)))
    return found


def _applied_measures(
    session: Session,
    *,
    book_code: str,
    rows: Sequence[Mapping[str, Any]],
    cutoff: datetime,
) -> dict[UUID, tuple[Decimal | None, dict[str, Decimal]]]:
    """Per APPLIED modification: (``tp_change``, catch-up per obligation key) from the run's
    book as of ``cutoff`` — the application version bound deterministically
    (``bind_application_version``: the owner's group at application; ambiguity refused), its
    obligation versions of the modification's contract and line keys (REGISTER-CATCHUP-1), and a
    shared catch-up (several modification events in one version) refused by name (D-98 140-A10)."""
    events = {
        UUID(str(row["applied_event_id"])): UUID(str(row["id"]))
        for row in rows
        if row["applied_event_id"] is not None
    }
    by_id = {UUID(str(row["id"])): row for row in rows}
    found: dict[UUID, tuple[Decimal | None, dict[str, Decimal]]] = {}
    if not events:
        return found
    versions = [
        dict(row)
        for row in session.execute(
            select(
                contract_version.c.id,
                contract_version.c.combination_group_id,
                contract_version.c.transaction_price,
                contract_version.c.previous_version_id,
                contract_version.c.cause_event_ids,
            ).where(
                contract_version.c.book_code == book_code,
                contract_version.c.known_at <= cutoff,
                contract_version.c.cause_event_ids.overlap(sorted(events, key=str)),
            )
        ).mappings()
    ]
    groups = _application_groups(session, sorted(events, key=str))
    bound: dict[UUID, Mapping[str, Any]] = {}
    for event_id, modification_id in events.items():
        group_id = groups.get(event_id)
        if group_id is None:
            continue  # no membership at the event: no application version to read
        candidates = [
            v for v in versions if event_id in {UUID(str(c)) for c in (v["cause_event_ids"] or ())}
        ]
        version = bind_application_version(
            candidates,
            group_id=group_id,
            modification_no=str(by_id[modification_id]["modification_no"]),
            book_code=book_code,
        )
        if version is not None:
            bound[modification_id] = version
    if not bound:
        return found
    cause_ids = sorted(
        {UUID(str(c)) for v in bound.values() for c in (v["cause_event_ids"] or ())}, key=str
    )
    cause_types: dict[UUID, str] = {}
    for event_id, event_type in session.execute(
        select(contract_event.c.id, contract_event.c.event_type).where(
            contract_event.c.id.in_(cause_ids)
        )
    ):
        cause_types[UUID(str(event_id))] = str(getattr(event_type, "value", event_type))
    previous_ids = sorted(
        {
            UUID(str(v["previous_version_id"]))
            for v in bound.values()
            if v["previous_version_id"] is not None
        },
        key=str,
    )
    previous_prices: dict[UUID, Decimal] = {}
    if previous_ids:
        for version_id, price in session.execute(
            select(contract_version.c.id, contract_version.c.transaction_price).where(
                contract_version.c.id.in_(previous_ids)
            )
        ):
            previous_prices[UUID(str(version_id))] = Decimal(str(price))
    version_rows = [
        dict(row)
        for row in session.execute(
            select(
                obligation_version.c.contract_version_id,
                obligation_version.c.contract_id,
                obligation_version.c.obligation_key,
                obligation_version.c.catch_up_amount,
            ).where(
                obligation_version.c.contract_version_id.in_(
                    sorted({UUID(str(v["id"])) for v in bound.values()}, key=str)
                )
            )
        ).mappings()
    ]
    for modification_id, version in bound.items():
        source = by_id[modification_id]
        causes = [cause_types.get(UUID(str(c)), "") for c in (version["cause_event_ids"] or ())]
        if shared_catch_up(causes) > 1:
            raise ModificationRegisterRefusal(
                "catch_up_amount",
                CATCH_UP_SHARED.format(
                    modification_no=source["modification_no"], count=shared_catch_up(causes)
                ),
            )
        previous = version["previous_version_id"]
        before = (
            Decimal(0) if previous is None else previous_prices.get(UUID(str(previous)), Decimal(0))
        )
        keys = [
            str(line["obligation_key"])
            for line in (source["lines"] or ())
            if isinstance(line, Mapping) and line.get("obligation_key") is not None
        ]
        version_id = UUID(str(version["id"]))
        found[modification_id] = (
            Decimal(str(version["transaction_price"])) - before,
            applied_catch_up(
                (r for r in version_rows if UUID(str(r["contract_version_id"])) == version_id),
                contract_id=UUID(str(source["contract_id"])),
                keys=keys,
            ),
        )
    return found


def _preview_measures(
    uow: UnitOfWork, row: Mapping[str, Any]
) -> tuple[Decimal | None, dict[str, Decimal]] | None:
    """The stored impact preview's ``transaction_price_after − transaction_price_before`` and its
    ``catch_up_by_obligation`` (provenance ``impact_preview_sha256``); None without a preview."""
    if row["impact_preview_file_id"] is None:
        return None
    document = modifications.read_preview(
        uow.session, dict(row), files=uow.files, keyring=uow.keyring
    )
    if document is None:
        return None
    summary = document.get("summary") or {}
    before = Decimal(str(summary["transaction_price_before"]["amount"]))
    after = Decimal(str(summary["transaction_price_after"]["amount"]))
    catch_up = {
        str(item["obligation_key"]): Decimal(str(item["amount"]["amount"]))
        for item in summary.get("catch_up_by_obligation") or ()
    }
    return after - before, catch_up


def sources(
    uow: UnitOfWork,
    params: ReportParams,
    *,
    book_code: str,
    from_date: date,
    to_date: date,
    statuses: Sequence[str],
) -> list[Source]:
    """The modifications of the run with their measures resolved (module docstring)."""
    session = uow.session
    if not params.entity_ids:
        return []
    tenant = modification.c.tenant_id
    joined = modification.join(
        contract, and_(contract.c.tenant_id == tenant, contract.c.id == modification.c.contract_id)
    ).join(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == tenant,
            legal_entity.c.id == modification.c.contracting_entity_id,
        ),
    )
    statement = (
        select(
            modification,
            contract.c.external_id.label("contract_external_id"),
            legal_entity.c.code.label("entity_code"),
            legal_entity.c.functional_currency.label("functional_currency"),
        )
        .select_from(joined)
        .where(
            modification.c.contracting_entity_id.in_(list(params.entity_ids)),
            modification.c.created_at <= tie_outs.cutoff_for(session, params),
        )
        .order_by(contract.c.external_id, modification.c.modification_no)
    )
    if not params.historical:
        # a live run reads the CURRENT effective dates — the truth of the record basis
        statement = statement.where(
            modification.c.effective_date >= from_date, modification.c.effective_date <= to_date
        )
    named = params.parameters.get("contract_external_id")
    if named is not None:
        statement = statement.where(contract.c.external_id == str(named))
    candidates = [dict(row) for row in session.execute(statement).mappings()]
    cutoff = tie_outs.cutoff_for(session, params)
    # REGISTER-CUTOFF-1 (D-98 140-A10 / A11 / A13): on a historical run the potentially relevant
    # population — every row in scope recorded by the cutoff, BEFORE the mutable effective_date
    # and the current status can exclude it — is inspected for unavailable history: a row that
    # changed after the cutoff (a PATCHed date, a moved status) refuses by name; nothing is
    # inferred or silently dropped. The date and status filters apply afterwards.
    refusal = historical_status_refusal(candidates, cutoff=cutoff, historical=params.historical)
    if refusal is not None:
        raise tie_outs.invalid("known_at", refusal)
    rows = population_filter(candidates, from_date=from_date, to_date=to_date, statuses=statuses)
    if not rows:
        return []
    request_ids = [
        UUID(str(row["approval_request_id"])) for row in rows if row["approval_request_id"]
    ]
    deciders, approved_at = _approvers(session, request_ids, cutoff=cutoff)
    request_nos: dict[UUID, str] = {}
    if request_ids:
        for request_id, number in session.execute(
            select(approval_request.c.id, approval_request.c.request_no).where(
                approval_request.c.id.in_(sorted(set(request_ids), key=str))
            )
        ):
            request_nos[UUID(str(request_id))] = str(number)
    judgement_ids = sorted(
        {UUID(str(row["judgement_record_id"])) for row in rows if row["judgement_record_id"]},
        key=str,
    )
    judgement_nos: dict[UUID, str] = {}
    if judgement_ids:
        for record_id, number in session.execute(
            select(judgement_record.c.id, judgement_record.c.judgement_no).where(
                judgement_record.c.id.in_(judgement_ids)
            )
        ):
            judgement_nos[UUID(str(record_id))] = str(number)
    event_ids = sorted(
        {UUID(str(row["applied_event_id"])) for row in rows if row["applied_event_id"]}, key=str
    )
    # REGISTER-EVENT-1: the CV-21 identity is the event's OWNER contract's external id (the NEW
    # contract for a separate-contract booking); the row key keeps the original contract.
    event_owners: dict[UUID, tuple[str, int]] = {}
    if event_ids:
        owner = contract.alias("event_owner")
        for event_id, stream_version, external_id in session.execute(
            select(contract_event.c.id, contract_event.c.stream_version, owner.c.external_id)
            .select_from(
                contract_event.join(
                    owner,
                    and_(
                        owner.c.tenant_id == contract_event.c.tenant_id,
                        owner.c.id == contract_event.c.contract_id,
                    ),
                )
            )
            .where(contract_event.c.id.in_(event_ids))
        ):
            event_owners[UUID(str(event_id))] = (str(external_id), int(stream_version))
    applied = _applied_measures(session, book_code=book_code, rows=rows, cutoff=cutoff)
    names = approval_queries.display_names(
        session,
        [
            *(None if row["created_by"] is None else UUID(str(row["created_by"])) for row in rows),
            *(approver for found in deciders.values() for approver, _ in found),
        ],
    )
    out: list[Source] = []
    for row in rows:
        modification_id = UUID(str(row["id"]))
        status = _text(row["status"])
        request_id = (
            None if row["approval_request_id"] is None else UUID(str(row["approval_request_id"]))
        )
        tp_change: Decimal | None = None
        catch_up: dict[str, Decimal] | None = None
        if status == ModificationStatus.APPLIED.value and modification_id in applied:
            tp_change, catch_up = applied[modification_id]
        elif status in (ModificationStatus.APPROVED.value, ModificationStatus.SUBMITTED.value):
            measured = _preview_measures(uow, row)
            if measured is not None:
                tp_change, catch_up = measured
        applied_event_key = (
            None
            if row["applied_event_id"] is None
            else applied_event_reference(event_owners.get(UUID(str(row["applied_event_id"]))))
        )
        approvers = None
        if request_id is not None and deciders.get(request_id):
            approvers = ", ".join(
                str(approval_queries.actor(approver, kind, names)["display_name"])
                for approver, kind in deciders[request_id]
            )
        preparer = approval_queries.actor(
            None if row["created_by"] is None else UUID(str(row["created_by"])),
            _text(row["created_by_kind"]),
            names,
        )
        out.append(
            Source(
                modification_no=str(row["modification_no"]),
                reference=None if row["reference"] is None else str(row["reference"]),
                contract_external_id=str(row["contract_external_id"]),
                entity_code=str(row["entity_code"]),
                functional_currency=str(row["functional_currency"]).strip(),
                kind=_text(row["kind"]),
                effective_date=row["effective_date"],
                created_at=row["created_at"],
                status=status,
                proposed_treatments={
                    str(k): _text(v) for k, v in (row["proposed_treatments"] or {}).items()
                },
                chosen_treatments={
                    str(k): _text(v) for k, v in (row["chosen_treatments"] or {}).items()
                },
                judgement_no=(
                    None
                    if row["judgement_record_id"] is None
                    else judgement_nos.get(UUID(str(row["judgement_record_id"])))
                ),
                questionnaire=dict(row["questionnaire"] or {}),
                obligation_keys=tuple(
                    str(line["obligation_key"])
                    for line in (row["lines"] or ())
                    if isinstance(line, Mapping) and line.get("obligation_key") is not None
                ),
                currency=str(row["currency"]).strip(),
                tp_change=tp_change,
                catch_up=catch_up,
                approval_request_no=None if request_id is None else request_nos.get(request_id),
                approved_at=None if request_id is None else approved_at.get(request_id),
                impact_preview_sha256=(
                    None
                    if row["impact_preview_sha256"] is None
                    else str(row["impact_preview_sha256"])
                ),
                applied_event_key=applied_event_key,
                preparer=str(preparer["display_name"]),
                approvers=approvers,
            )
        )
    return out


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    from_date, to_date = date_range(session, params, year=True)
    found = sources(
        uow,
        params,
        book_code=book_code,
        from_date=from_date,
        to_date=to_date,
        statuses=_statuses(params),
    )
    check_view(str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW), found)
    rows = dataset_rows(found)
    check_key_columns(rows)
    totals = control_totals(rows)
    totals["from_date"] = from_date.isoformat()
    totals["to_date"] = to_date.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)
