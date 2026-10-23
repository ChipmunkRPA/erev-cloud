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

New native APPLIED traces supply event-position transaction-price changes and per-obligation
catch-ups. Their hashes and formulas are verified and their node identities retained. Several
modifications in one application version can therefore be read independently. Older traces
without event-price evidence retain the version-delta fallback and shared-catch-up refusal.

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
currency, else the run refuses by name (RPT-07 pattern). Reporting view uses that same
admission and adds separately labelled equivalents at the modification effective-period average,
retaining original values and empty measures. The optional spot_equivalent basis admits foreign
contracts using pinned effective-date spot rates to functional currency before reporting
translation. These equivalents are not posted FX amounts.
A row whose key column cannot be supplied, or two rows of one key, refuse by name
(``ModificationRegisterRefusal``).
The as-locked surface (``period_lock_id``) is CLO-8b's; a lock source here refuses by name.

F-RPS's registry entry ``SNAPSHOT_DATASETS["MODIFICATION_REGISTER"]`` wraps ``dataset_rows`` /
``control_totals`` into the EDS-6 encoding; this module provides the rows and totals only.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_subject_key
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
    tenant,
)
from erev_api.domain.contracts import bundles, modifications
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import (
    modification_event_amounts,
    modification_functional,
    reporting_currency,
    tie_outs,
)
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_history import date_range
from erev_api.domain.reports.builders.out_of_period_register import event_key, refuse_locked_source
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalDecisionKind, ModificationStatus
from erev_api.explain.store import load_trace
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

CODE: Final = "modification_register"
EVIDENCE: Final = "modification_inputs_v1"
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
    "Functional and reporting views are available when every modification is in its entity's "
    "functional currency; choose the transaction view or explicitly select spot equivalents."
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
    tp_components: Mapping[str, Decimal] | None = None
    functional_calculation: Mapping[str, Mapping[str, Any]] | None = None


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
    is in its entity's functional currency; reporting uses the same admission before translation."""
    if view not in {"transaction", "functional", "reporting"}:
        raise tie_outs.invalid(
            "currency_view", "Choose Transaction, Functional or Reporting currency."
        )
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


def applied_price_change(
    version: Mapping[str, Any],
    predecessors: Mapping[UUID, Mapping[str, Any]],
    *,
    modification_no: str,
) -> Decimal:
    """Compare an application with its own same-book/group/currency predecessor."""
    previous_id = version["previous_version_id"]
    if previous_id is None:
        return Decimal(str(version["transaction_price"]))
    previous = predecessors.get(UUID(str(previous_id)))
    if (
        previous is None
        or any(
            previous[key] != version[key]
            for key in ("combination_group_id", "book_code", "transaction_currency")
        )
        or previous["known_at"] > version["known_at"]
    ):
        raise ModificationRegisterRefusal(
            "tp_change",
            f"The register cannot attribute the transaction-price change of {modification_no}: "
            "its original predecessor version is unavailable or has another scope. "
            "The prior transaction price cannot be assumed to be zero.",
        )
    return Decimal(str(version["transaction_price"])) - Decimal(str(previous["transaction_price"]))


def _applied_measures(
    session: Session,
    *,
    book_code: str,
    rows: Sequence[Mapping[str, Any]],
    cutoff: datetime,
    params: ReportParams | None = None,
    components: dict[UUID, Mapping[str, Decimal]] | None = None,
    functional: dict[UUID, dict[str, dict[str, Any]]] | None = None,
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
                contract_version.c.calc_trace_id,
                contract_version.c.book_code,
                contract_version.c.transaction_currency,
                contract_version.c.known_at,
                contract_version.c.previous_version_id,
                contract_version.c.cause_event_ids,
            ).where(
                contract_version.c.book_code == book_code,
                contract_version.c.known_at <= cutoff,
                *tie_outs.version_commit_where(params, cutoff),
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
    if params is not None:
        tie_outs.record_members(
            params, "modification_application_versions", (v["id"] for v in bound.values())
        )
        tie_outs.record_evidence(
            params,
            "modification_application_versions_v1",
            json.loads(canonical_bytes({str(key): dict(value) for key, value in bound.items()})),
        )
    cause_ids = sorted(
        {UUID(str(c)) for v in bound.values() for c in (v["cause_event_ids"] or ())}, key=str
    )
    cause_types: dict[UUID, str] = {}
    event_keys: dict[UUID, str] = {}
    for event_id, event_type, external_id, stream_version in session.execute(
        select(
            contract_event.c.id,
            contract_event.c.event_type,
            contract.c.external_id,
            contract_event.c.stream_version,
        )
        .join(
            contract,
            and_(
                contract.c.id == contract_event.c.contract_id,
                contract.c.tenant_id == contract_event.c.tenant_id,
            ),
        )
        .where(contract_event.c.id.in_(cause_ids))
    ):
        cause_types[UUID(str(event_id))] = str(getattr(event_type, "value", event_type))
        event_keys[UUID(str(event_id))] = (
            f"{contract_subject_key(str(external_id))}/EV-{stream_version:06d}"
        )
    previous_ids = sorted(
        {
            UUID(str(v["previous_version_id"]))
            for v in bound.values()
            if v["previous_version_id"] is not None
        },
        key=str,
    )
    predecessors: dict[UUID, Mapping[str, Any]] = {}
    if previous_ids:
        predecessors = {
            UUID(str(row["id"])): dict(row)
            for row in session.execute(
                select(
                    contract_version.c.id,
                    contract_version.c.transaction_price,
                    contract_version.c.combination_group_id,
                    contract_version.c.book_code,
                    contract_version.c.transaction_currency,
                    contract_version.c.known_at,
                ).where(
                    contract_version.c.id.in_(previous_ids),
                    contract_version.c.known_at <= cutoff,
                    *tie_outs.version_commit_where(params, cutoff),
                )
            ).mappings()
        }
        if params is not None:
            tie_outs.record_members(params, "modification_predecessor_versions", predecessors)
            tie_outs.record_evidence(
                params,
                "modification_predecessor_versions_v1",
                json.loads(
                    canonical_bytes({str(key): dict(value) for key, value in predecessors.items()})
                ),
            )
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
    trace_cache = {}
    for modification_id, version in bound.items():
        source = by_id[modification_id]
        version_id = UUID(str(version["id"]))
        keys = [
            str(line["obligation_key"])
            for line in (source["lines"] or ())
            if isinstance(line, Mapping) and line.get("obligation_key") is not None
        ]
        event_key_ = event_keys.get(UUID(str(source["applied_event_id"])))
        try:
            if version_id not in trace_cache:
                trace_cache[version_id] = load_trace(session, version_id)
            trace = trace_cache[version_id]
            measured = (
                None
                if trace is None or event_key_ is None
                else modification_event_amounts.read(
                    trace,
                    event_key=event_key_,
                    contract_key=str(source["contract_external_id"]),
                    obligation_keys=keys,
                    currency=str(source["currency"]).strip(),
                )
            )
        except (ValueError, EngineError) as error:
            raise ModificationRegisterRefusal("catch_up_amount", str(error)) from error
        if measured is not None:
            if components is not None and measured.components is not None:
                components[modification_id] = measured.components
            found[modification_id] = (measured.tp_change, measured.catch_up)
            if functional is not None:
                assert trace is not None and event_key_ is not None
                from erev_engine.stages.s01_canonicalize import obligation_subject_key

                calculated = {}
                for key in keys:
                    try:
                        original = modification_functional.read(
                            trace,
                            event_key=event_key_,
                            subject=obligation_subject_key(
                                str(source["contract_external_id"]), key
                            ),
                            entity=str(source["entity_code"]),
                            transaction_currency=str(source["currency"]).strip(),
                            functional_currency=str(source["functional_currency"]).strip(),
                        )
                    except (ValueError, EngineError) as error:
                        raise ModificationRegisterRefusal("catch_up_amount", str(error)) from error
                    if original is not None:
                        calculated[key] = asdict(original)
                functional[modification_id] = calculated
            if params is not None:
                tie_outs.record_members(
                    params, "modification_event_traces", [version["calc_trace_id"]]
                )
                assert trace is not None
                tie_outs.record_evidence(
                    params,
                    f"modification_event_amounts_v1:{modification_id}",
                    {
                        "version_id": str(version_id),
                        "trace_id": str(version["calc_trace_id"]),
                        "trace_sha256": trace.sha256(),
                        "event_key": event_key_,
                        "node_ids": list(measured.node_ids),
                    },
                )
            continue
        causes = [cause_types.get(UUID(str(c)), "") for c in (version["cause_event_ids"] or ())]
        if shared_catch_up(causes) > 1:
            raise ModificationRegisterRefusal(
                "catch_up_amount",
                CATCH_UP_SHARED.format(
                    modification_no=source["modification_no"], count=shared_catch_up(causes)
                ),
            )
        keys = [
            str(line["obligation_key"])
            for line in (source["lines"] or ())
            if isinstance(line, Mapping) and line.get("obligation_key") is not None
        ]
        version_id = UUID(str(version["id"]))
        found[modification_id] = (
            applied_price_change(
                version, predecessors, modification_no=str(source["modification_no"])
            ),
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
    tie_outs.record_members(params, "modifications", (row["id"] for row in rows))
    tie_outs.record_members(
        params,
        "modification_preview_files",
        (
            row["impact_preview_file_id"]
            for row in rows
            if row["impact_preview_file_id"] is not None
        ),
    )
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
    component_values: dict[UUID, Mapping[str, Decimal]] = {}
    functional_values: dict[UUID, dict[str, dict[str, Any]]] = {}
    applied = _applied_measures(
        session,
        book_code=book_code,
        rows=rows,
        cutoff=cutoff,
        params=params,
        components=component_values,
        functional=functional_values,
    )
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
                tp_components=component_values.get(modification_id),
                functional_calculation=functional_values.get(modification_id),
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


def reporting_rows(
    found: Sequence[Source],
    target: str,
    translations: Mapping[str, tuple[UUID, reporting_currency.Translation]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Add analytical reporting equivalents; retain the original amounts and nulls."""
    check_view("reporting", found)
    rows = dataset_rows(found)
    converted: list[dict[str, Any]] = []
    for row in rows:
        translated = {**row, "currency": target}
        for field in ("tp_change", "catch_up_amount"):
            value = row[field]
            if value is None:
                translated[field] = None
            else:
                entity_id, rate = translations[str(row["modification_no"])]
                if (
                    rate.currency != target
                    or rate.rates[entity_id]["base_currency"] != row["currency"]
                ):
                    raise tie_outs.invalid(
                        "currency_view", "Reporting translation requires functional amounts."
                    )
                translated[field] = tie_outs.money(
                    rate.amount(entity_id, Decimal(value["amount"])), target
                )
        row["reporting_currency"] = target
        row["tp_change_reporting"] = translated["tp_change"]
        row["catch_up_reporting"] = translated["catch_up_amount"]
        row["reporting_basis"] = "Equivalent at modification effective-period average"
        converted.append(translated)
    totals = control_totals(rows)
    equivalents = control_totals(converted)
    totals["tp_change_reporting_total"] = equivalents["tp_change_total"]
    totals["catch_up_reporting_total"] = equivalents["catch_up_total"]
    totals["reporting_currency"] = target
    totals["translation_basis"] = "modification_effective_period_average"
    return rows, totals


def functional_equivalents(
    found: Sequence[Source],
    facts: Mapping[str, Mapping[str, Any]],
) -> list[Source]:
    """Explicit analytical spot equivalents, never historical-layer posted catch-ups."""
    result = []
    for item in found:
        has_amount = item.tp_change is not None or bool(item.catch_up)
        if not has_amount:
            result.append(replace(item, currency=item.functional_currency))
            continue
        fact = facts.get(item.modification_no)
        try:
            if fact is None:
                raise ValueError("missing spot basis")
            rate = Decimal(str(fact["rate"]))
            if (
                fact["base"] != item.currency
                or fact["quote"] != item.functional_currency
                or fact["on"] != item.effective_date.isoformat()
                or fact["rate_type"] != "spot"
                or not rate.is_finite()
                or rate <= 0
            ):
                raise ValueError("inconsistent spot basis")
            if item.currency == item.functional_currency:
                if rate != 1:
                    raise ValueError("nonidentity equal-currency rate")
            elif not fact.get("rate_key") or not fact.get("version_key"):
                raise ValueError("missing pinned rate identity")
            # Reuse the same exact decimal-to-minor-unit conversion as other reports.
            identity = UUID(int=0)
            conversion = reporting_currency.Translation(
                item.functional_currency, {identity: {"rate": str(rate)}}
            )
            result.append(
                replace(
                    item,
                    currency=item.functional_currency,
                    tp_change=None
                    if item.tp_change is None
                    else conversion.amount(identity, item.tp_change),
                    catch_up=None
                    if item.catch_up is None
                    else {
                        key: conversion.amount(identity, amount)
                        for key, amount in item.catch_up.items()
                    },
                )
            )
        except (KeyError, ValueError, ArithmeticError) as error:
            raise tie_outs.invalid(
                "currency_basis", "Retained modification spot evidence is inconsistent."
            ) from error
    return result


def equivalent_rows(
    found: Sequence[Source],
    functional: Sequence[Source],
    view: str,
    target: str | None,
    translations: Mapping[str, tuple[UUID, reporting_currency.Translation]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = dataset_rows(found)
    converted = dataset_rows(functional)
    totals = control_totals(rows)
    functional_totals = control_totals(converted)
    totals["tp_change_functional_equivalent_total"] = functional_totals["tp_change_total"]
    totals["catch_up_functional_equivalent_total"] = functional_totals["catch_up_total"]
    if view == "reporting":
        assert target is not None
        translated, reporting_totals = reporting_rows(functional, target, translations)
        for name in ("tp_change_reporting_total", "catch_up_reporting_total", "reporting_currency"):
            totals[name] = reporting_totals[name]
    else:
        translated = converted
    for row, func, report in zip(rows, converted, translated, strict=True):
        row["functional_currency"] = func["currency"]
        row["tp_change_functional_equivalent"] = func["tp_change"]
        row["catch_up_functional_equivalent"] = func["catch_up_amount"]
        row["conversion_basis"] = "Effective-date spot equivalent; not actual posted FX attribution"
        if view == "reporting":
            for name in ("reporting_currency", "tp_change_reporting", "catch_up_reporting"):
                row[name] = report[name]
            row["reporting_basis"] = (
                "Effective-date spot to functional, then effective-period average to reporting"
            )
    totals["translation_basis"] = "analytical_spot_equivalent_not_posted"
    return rows, totals


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    check_view(view, ())
    basis = str(params.parameters.get("currency_basis") or "source")
    if basis not in {"source", "spot_equivalent"} or (
        basis == "spot_equivalent" and view == "transaction"
    ):
        raise tie_outs.invalid(
            "currency_basis",
            "Choose source amounts, or spot equivalents with Functional or Reporting currency.",
        )
    selection = {
        key: params.parameters.get(key)
        for key in (
            "book",
            "from_date",
            "to_date",
            "status",
            "contract_external_id",
        )
    }
    if params.binding is not None:
        retained = tie_outs.bound_evidence(params, EVIDENCE)
        if retained["tenant_id"] != str(uow.principal.tenant_id) or set(retained["entity_ids"]) != {
            str(entity_id) for entity_id in params.entity_ids
        }:
            raise Problem("forbidden", "Retained modification inputs exceed report scope.")
        if (
            retained["currency_view"] != view
            or retained["selection"] != selection
            or retained.get("currency_basis", "source") != basis
        ):
            raise tie_outs.invalid(
                "currency_view", "Retained inputs use another currency or filter selection."
            )
        return data_from_inputs(retained)
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
    if basis == "source":
        check_view(view, found)
    spot_facts: dict[str, dict[str, Any]] = {}
    if basis == "spot_equivalent":
        currencies = {
            currency for item in found for currency in (item.currency, item.functional_currency)
        }
        cutoff = tie_outs.cutoff_for(session, params)
        fx = bundles.fx_rate_inputs(session, currencies, cutoff)
        for item in found:
            if item.tp_change is None and not item.catch_up:
                continue
            fact = modifications.spot_basis(
                fx, base=item.currency, quote=item.functional_currency, on=item.effective_date
            )
            if fact.get("rate") is None:
                raise tie_outs.invalid(
                    "currency_basis",
                    "An approved spot rate is required for "
                    f"{item.currency}/{item.functional_currency} "
                    f"on or before {item.effective_date}.",
                )
            spot_facts[item.modification_no] = {
                **fact,
                "on": item.effective_date.isoformat(),
                "known_at": cutoff.isoformat(),
            }
        tie_outs.record_evidence(params, "modification_spot_equivalents_v1", spot_facts)
    target: str | None = None
    translations: dict[str, tuple[UUID, reporting_currency.Translation]] = {}
    if view == "reporting":
        target = str(
            session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == uow.principal.tenant_id)
            ).scalar_one()
        ).strip()
        entities = tie_outs.entities(session, params.entity_ids)
        by_code = {entity.code: entity for entity in entities}
        calendars = tie_outs.calendars(session, entities)
        rates: dict[tuple[UUID, str], reporting_currency.Translation] = {}
        for item in found:
            if item.tp_change is None and not item.catch_up:
                continue
            entity = by_code[item.entity_code]
            at = calendars[entity.id].holding(item.effective_date)
            if at is None:
                raise tie_outs.invalid(
                    "currency_view", "The modification effective date has no calendar period."
                )
            key = (entity.id, at.key)
            if key not in rates:
                rates[key] = reporting_currency.rates_for_period(
                    session,
                    params,
                    tenant_id=uow.principal.tenant_id,
                    entities=(entity,),
                    periods={entity.id: at},
                    rate_type="average",
                    target_currency=target,
                    evidence_key=f"modification_average_v1:{entity.id}:{at.key}",
                )
            translations[item.modification_no] = (entity.id, rates[key])
    retained = json.loads(
        canonical_bytes(
            {
                "tenant_id": uow.principal.tenant_id,
                "entity_ids": params.entity_ids,
                "selection": selection,
                "currency_view": view,
                "book": book_code,
                "from_date": from_date,
                "to_date": to_date,
                "sources": [asdict(item) for item in found],
                "tp_component_breakdown": True,
                "functional_calculation_columns": True,
                "currency_basis": basis,
                "spot_equivalents": spot_facts,
                "reporting_currency": target,
                "translations": [
                    {
                        "modification_no": key,
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
    found: list[Source] = []
    for record in retained["sources"]:
        values = dict(record)
        values["effective_date"] = date.fromisoformat(values["effective_date"])
        for key in ("created_at", "approved_at"):
            values[key] = (
                None
                if values[key] is None
                else datetime.fromisoformat(values[key].replace("Z", "+00:00"))
            )
        values["tp_change"] = None if values["tp_change"] is None else Decimal(values["tp_change"])
        values["catch_up"] = (
            None
            if values["catch_up"] is None
            else {key: Decimal(value) for key, value in values["catch_up"].items()}
        )
        if values.get("tp_components") is not None:
            values["tp_components"] = {k: Decimal(v) for k, v in values["tp_components"].items()}
        values["obligation_keys"] = tuple(values["obligation_keys"])
        found.append(Source(**values))
    view = retained["currency_view"]
    basis = retained.get("currency_basis", "source")
    functional = (
        functional_equivalents(found, retained["spot_equivalents"])
        if basis == "spot_equivalent"
        else found
    )
    check_view(view, functional)
    columns: tuple[Column, ...] = COLUMNS
    translations: dict[str, tuple[UUID, reporting_currency.Translation]] = {}
    if view == "reporting":
        translations = {
            item["modification_no"]: (
                UUID(item["entity_id"]),
                reporting_currency.Translation(
                    item["currency"], {UUID(key): value for key, value in item["rates"].items()}
                ),
            )
            for item in retained["translations"]
        }
        rows, totals = reporting_rows(functional, retained["reporting_currency"], translations)
        columns = COLUMNS + (
            Column("reporting_currency", "Reporting currency", "code"),
            Column("tp_change_reporting", "TP change, reporting equivalent", "money"),
            Column("catch_up_reporting", "Catch-up, reporting equivalent", "money"),
            Column("reporting_basis", "Reporting conversion basis", "text"),
        )
    else:
        rows = dataset_rows(found)
        totals = control_totals(rows)
    if basis == "spot_equivalent":
        rows, totals = equivalent_rows(
            found, functional, view, retained["reporting_currency"], translations
        )
        for row in rows:
            fact = retained["spot_equivalents"].get(str(row["modification_no"]))
            row["functional_spot_rate"] = None if fact is None else fact["rate"]
            row["functional_spot_rate_key"] = None if fact is None else fact.get("rate_key")
        columns += (
            Column("functional_spot_rate", "Functional spot rate", "decimal"),
            Column("functional_spot_rate_key", "Functional spot rate reference", "text"),
            Column("functional_currency", "Functional currency", "code"),
            Column(
                "tp_change_functional_equivalent", "TP change, functional spot equivalent", "money"
            ),
            Column(
                "catch_up_functional_equivalent", "Catch-up, functional spot equivalent", "money"
            ),
            Column("conversion_basis", "Conversion basis", "text"),
        )
    if retained.get("tp_component_breakdown"):
        labels = (
            "Fixed consideration",
            "Constrained variable consideration",
            "Expected returns",
            "Consideration payable",
            "Financing adjustment",
            "Noncash consideration",
            "Posting rounding",
        )
        columns += tuple(
            Column("tp_" + key, label + " change (original currency)", "money")
            for key, label in zip(modification_event_amounts.COMPONENTS, labels, strict=True)
        )
        by_modification = {item.modification_no: item for item in found}
        component_totals: dict[str, dict[str, Decimal]] = {}
        counted: set[str] = set()
        for row in rows:
            item = by_modification[str(row["modification_no"])]
            for key in modification_event_amounts.COMPONENTS:
                amount = None if item.tp_components is None else item.tp_components.get(key)
                row["tp_" + key] = _money(amount, item.currency)
                if amount is not None and item.modification_no not in counted:
                    tie_outs.add(component_totals.setdefault(key, {}), item.currency, amount)
            counted.add(item.modification_no)
        for key in modification_event_amounts.COMPONENTS:
            totals["tp_" + key + "_total"] = tie_outs.by_currency(component_totals.get(key, {}))
        totals["tp_component_basis"] = (
            "Original event-position TP components; empty when unavailable"
        )
    if retained.get("functional_calculation_columns"):
        columns += (
            Column(
                "catch_up_functional_calculation",
                "Catch-up, original functional calculation",
                "money",
            ),
            Column("catch_up_functional_period", "Functional calculation period", "code"),
            Column("catch_up_functional_basis", "Functional calculation basis", "text"),
        )
        by_modification = {item.modification_no: item for item in found}
        for row in rows:
            item = by_modification[str(row["modification_no"])]
            fact = (item.functional_calculation or {}).get(str(row["obligation_key"]))
            row["catch_up_functional_calculation"] = (
                None
                if fact is None
                else _money(Decimal(str(fact["amount"])), str(fact["currency"]))
            )
            row["catch_up_functional_period"] = None if fact is None else fact["period_key"]
            row["catch_up_functional_basis"] = (
                "Unavailable: requires exclusive original event-to-period evidence"
                if fact is None
                else (
                    "Original functional layers; exclusive event-period calculation, "
                    "not journal delta"
                )
            )
    check_key_columns(rows)
    totals["from_date"] = retained["from_date"]
    totals["to_date"] = retained["to_date"]
    return ReportData(columns=columns, rows=tuple(rows), control_totals=totals)
