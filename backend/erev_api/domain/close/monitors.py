"""CLO-5 data-quality monitors: the DB-bound producer (BUILD_SPEC CLO-5; 03 REQ-CLS-019; 04 §15.4
table 15.4-E, T-IMP-05, T-PLT-31, T-REF-24 to T-REF-26; PRD NTF-11; SCREENS_B §1.1 :368).

``run_monitors`` is the close-monitor entry point the close gates rely on. For one entity, book and
period it assembles the input records of the six monitors from the tables that hold them, evaluates
them through the pure ``monitor_rules`` (F-CLO preparation, Codex-reviewed), records one exception
item per finding through ``imports.exceptions.raise_exception_item`` (source ``DATA_QUALITY``; the
T-IMP-05 ``dedupe_key`` ``DATA_QUALITY:<code>:<subject>`` keeps one open item per rule and subject,
so a re-run counts the open item again and creates nothing), notifies the Revenue Accountants of a
new item (NTF-11; supervisor ruling Q-5: the owner when set, else the tenant's Revenue Accountants)
and returns the ``DATA_QUALITY_CLEAR`` gate result from the open ``BLOCKING`` items of the period.
A run also settles the open items of its entity and period that no evaluated book of the entity
finds any more — RESOLVED by the system (``_settle_gone``; 04 T-IMP-05 rev 1.185 "A monitor
finding that is gone"; supervisor ruling R-111 (j), item DQ-RESOLVE-1) — before it reads the gate.
``commands.run_period_monitors`` runs it before ``start-close`` and ``request-lock`` evaluate (the
SYSTEM principal, its own unit of work), the scheduled sweep runs it daily (05 SCH-10), and the
close run's ``EXCEPTION_CHECK`` step (CLO-19) calls the same function. It does not run on a GET:
every run writes one ``close.run_monitors`` audit event, and a read appends none (security finding
SC-8; supervisor ruling R-32).

Sources (record ``docs/reviews/loop/prod/F-CLO-prep.md`` §16.1):

- ``DQ_DUPLICATE_INVOICE``: ``source_invoice`` rows of the entity (``legal_entity_code``), keyed by
  ``(source_system, external_invoice_id, external_version)`` with the ruling Q-8 identity tuple
  (customer, invoice number, total amount, issue date);
- ``DQ_REVENUE_WITHOUT_BILLING``: ``subledger_line`` of the entity and book up to the period end,
  the first ``REVENUE_RECOGNITION`` date against the first ``BILLING`` date per obligation (a
  contract-level billing line covers every obligation of the contract);
- ``DQ_NEGATIVE_LIABILITY_LAYER``: current-version T-CON-18 movements through the period end,
  grouped by the originating layer. Either transaction or functional carrying below zero raises
  one finding. Positive layers cannot offset a negative layer; remeasurement changes only the
  functional carrying. Versions created before T-CON-18 persistence have no layer coverage;
- ``DQ_RECOGNITION_AFTER_POB_END``: revenue ``schedule_line`` rows of the period on the current
  version whose ``obligation_version.end_date`` precedes the period start;
- ``DQ_INACTIVE_CONTRACT``: ``ACTIVE`` contracts of the entity with the latest
  ``contract_event.effective_date``;
- ``FX_RATE_MISSING``: each transaction currency of the entity's ``ACTIVE`` contracts other than
  the functional currency needs an in-force ``closing`` rate at the period end
  (``fx.EFFECTIVE_RATES``, the rule ``fx.rate`` applies).

Thresholds are the T-PLT-31 settings resolved for the entity and book; severities are the table
defaults unless a ``PUBLISHED`` ``DATA_QUALITY`` rule keyed by the monitor code overrides them
(``DQ-SYSTEM`` first, so a tenant's own set wins). Business dates are the period's (API-C-07); the
clock is ``uow.now``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from sqlalchemy import ColumnElement, Select, Text, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.db.tables import (
    contract,
    contract_event,
    contract_version,
    fx_layer_movement,
    legal_entity,
    obligation_version,
    period_state,
    rule,
    rule_set,
    rule_set_version,
    schedule,
    schedule_line,
    source_invoice,
    subledger_line,
)
from erev_api.domain.close import gates, monitor_rules
from erev_api.domain.imports.exceptions import (
    RaisedItem,
    open_keys,
    raise_exception_item,
    settle_gone,
    standing_waiver,
)
from erev_api.domain.reference.fx import EFFECTIVE_RATES
from erev_api.domain.reports import tie_outs
from erev_api.enums import (
    BookCode,
    ConfigStatus,
    ContractStatus,
    ExceptionSource,
    NotificationKind,
    RateType,
    RuleSetKind,
    SubledgerEntryKind,
)
from erev_api.events.notifications import notify, role_holders
from erev_api.problems import Problem
from erev_api.registry.resolve import resolve

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

RUN_ACTION: Final = "close.run_monitors"  # BUILD_SPEC CLO-5 "the command close.run_monitors"
STATE_OBJECT: Final = "period_state"
EXCEPTION_OBJECT: Final = "exception_item"
REVENUE_ACCOUNTANT: Final = "revenue_accountant"  # T-PLT-09 role code; ruling Q-5
DQ_SYSTEM: Final = "DQ-SYSTEM"  # 04 §14.3 rev 1.21 seeded rule set
SEVERITY_CAUSE: Final = "DATA_QUALITY rule re-evaluation"  # D-98 58 history entry cause
OBLIGATION_SUBJECT: Final = "obligation"
REVENUE_SCHEDULE: Final = "REVENUE"
# 04 T-IMP-05 rev 1.185: the resolution of an item whose finding is gone.
GONE: Final = (
    "No longer found by the data-quality monitors for {period_key} (books evaluated: {books})."
)
# A book in one of these states is not evaluated and keeps the period's open items (table 15.4-E).
LOCKED_STATES: Final = frozenset({"closed", "permanently_locked"})


@dataclass(frozen=True, slots=True)
class MonitorRun:
    """What one monitor run established for a period."""

    scope: gates.PeriodScope
    outcome: monitor_rules.MonitorOutcome
    raised: tuple[RaisedItem, ...]
    open_blocking: int
    gate: gates.GateResult
    # The items whose approved waiver still covers a finding of this run: nothing was raised for
    # them (04 T-IMP-05 rev 1.106; supervisor ruling R-62 (c)).
    waived: tuple[UUID, ...] = ()
    # The open items this run settled because no evaluated book of the entity finds them any more,
    # and the number it would have settled but kept because another book of the entity has locked
    # the period (04 T-IMP-05 rev 1.185).
    settled: tuple[UUID, ...] = ()
    kept_for_locked_book: int = 0

    @property
    def created(self) -> int:
        return sum(1 for item in self.raised if item.created)

    @property
    def seen_again(self) -> int:
        return sum(1 for item in self.raised if not item.created)

    @property
    def severity_changed(self) -> int:
        """Existing items whose current effective severity changed on this run (D-98 58)."""
        return sum(1 for item in self.raised if item.severity_changed)


# --- settings and overrides ----------------------------------------------------------------------


def settings_of(
    session: Session, scope: gates.PeriodScope, *, known_at: datetime
) -> dict[str, int]:
    """The T-PLT-31 thresholds of the entity and book (``monitor_rules.SETTING_RANGES`` applies)."""
    values: dict[str, int] = {}
    for key in (monitor_rules.REVENUE_WITHOUT_BILLING_DAYS, monitor_rules.INACTIVE_CONTRACT_DAYS):
        resolved = resolve(
            session,
            key,
            book_code=BookCode(scope.book_code),
            entity_id=scope.entity_id,
            known_at=known_at,
        )
        values[key] = int(resolved.value)
    return values


def overrides_of(session: Session, *, at: datetime) -> dict[str, str]:
    """``outputs.severity`` of every ``PUBLISHED`` ``DATA_QUALITY`` rule keyed by a monitor code,
    from the highest published version of each set in force at ``at``; ``DQ-SYSTEM`` first so a
    tenant's own set overrides the seed."""
    on = at.date()
    rows = session.execute(
        select(rule_set.c.code, rule_set_version.c.version_no, rule.c.rule_key, rule.c.outputs)
        .select_from(
            rule_set.join(
                rule_set_version,
                and_(
                    rule_set_version.c.tenant_id == rule_set.c.tenant_id,
                    rule_set_version.c.rule_set_id == rule_set.c.id,
                ),
            ).join(
                rule,
                and_(
                    rule.c.tenant_id == rule_set_version.c.tenant_id,
                    rule.c.rule_set_version_id == rule_set_version.c.id,
                ),
            )
        )
        .where(
            rule_set.c.kind == RuleSetKind.DATA_QUALITY.value,
            rule_set_version.c.status == ConfigStatus.PUBLISHED.value,
            or_(
                rule_set_version.c.effective_from.is_(None),
                rule_set_version.c.effective_from <= on,
            ),
            or_(rule_set_version.c.effective_to.is_(None), rule_set_version.c.effective_to >= on),
            rule.c.rule_key.in_(sorted(monitor_rules.CODES)),
        )
        .order_by(rule_set.c.code, rule_set_version.c.version_no, rule.c.rule_key)
    ).tuples()
    found = [
        (str(code), int(version_no), str(key), outputs) for code, version_no, key, outputs in rows
    ]
    latest: dict[str, int] = {}
    for code, version_no, _, _ in found:
        latest[code] = max(latest.get(code, 0), version_no)
    overrides: dict[str, str] = {}
    for set_code in sorted(latest, key=lambda code: (code != DQ_SYSTEM, code)):
        for code, version_no, key, outputs in found:
            if code != set_code or version_no != latest[set_code]:
                continue
            severity = outputs.get("severity") if isinstance(outputs, Mapping) else None
            if isinstance(severity, str):
                overrides[key] = severity
    return overrides


# --- input collectors ----------------------------------------------------------------------------


def _current_version(
    contract_id: ColumnElement[Any], version_id: ColumnElement[Any], book_code: str
) -> ColumnElement[bool]:
    """Whether a row of ``contract_id`` in contract version ``version_id`` is of the version the
    contract is read from now (04 T-CON-04 reading rule; ``tie_outs.read_from``; item
    RPT-FORMER-GROUP-READERS-1, supervisor ruling R-117 (a)). The condition was "no later version
    of the same group and book": a group every contract has left keeps its last version, which
    stayed current for ever beside the combined group's (measured: two liability layers and two
    recognitions for each member of a combined group)."""
    return tie_outs.read_from(
        contract_id, version_id, book_code=book_code, cutoff=None, statuses=None
    )


def canonical_amount(total: Decimal | None, currency: str | None) -> Decimal | None:
    """The Q-8 identity amount as canonical money text: quantized to the currency's ISO 4217 minor
    unit — half-up, as ``erev_engine.money`` rounds; two places when the currency is unknown — so
    the T-IMP-05 dedupe key does not depend on the T-SRC-04 column scale (NUMERIC(24, 4) reads
    ``1200.0000``; the key carries ``1200.00``; integrated batch #4 on main c9110467). Stage 10
    billing admission needs exact minor units anyway; the quantization only names an off-minor
    source amount consistently."""
    if total is None:
        return None
    spec = ISO_4217.get(str(currency or ""))
    places = 2 if spec is None else int(spec.minor_unit)
    return Decimal(total).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _invoices(session: Session, scope: gates.PeriodScope) -> list[monitor_rules.SourceInvoiceRef]:
    rows = session.execute(
        select(
            source_invoice.c.id,
            source_invoice.c.source_system,
            source_invoice.c.external_invoice_id,
            source_invoice.c.external_version,
            source_invoice.c.customer_external_id,
            source_invoice.c.customer_id,
            source_invoice.c.invoice_number,
            source_invoice.c.total_amount,
            source_invoice.c.currency,
            source_invoice.c.issue_date,
        )
        .where(source_invoice.c.legal_entity_code == scope.entity_code)
        .order_by(source_invoice.c.issue_date, source_invoice.c.id)
    ).tuples()
    refs: list[monitor_rules.SourceInvoiceRef] = []
    for (
        row_id,
        system,
        external_id,
        version,
        customer_ref,
        customer_id,
        number,
        total,
        currency,
        issued,
    ) in rows:
        customer = (
            str(customer_ref)
            if customer_ref is not None
            else (None if customer_id is None else str(customer_id))
        )
        refs.append(
            monitor_rules.SourceInvoiceRef(
                source_system=str(getattr(system, "value", system)),
                external_invoice_id=str(external_id),
                external_version=str(version),
                row_id=UUID(str(row_id)),
                customer_ref=customer,
                invoice_number=None if number is None else str(number),
                amount=canonical_amount(total, currency),
                issue_date=issued,
            )
        )
    return refs


def _unbilled(session: Session, scope: gates.PeriodScope) -> list[monitor_rules.UnbilledRevenueRef]:
    conditions = (
        subledger_line.c.entity_id == scope.entity_id,
        subledger_line.c.book_code == scope.book_code,
        subledger_line.c.effective_date <= scope.end_date,
    )

    def firsts(kind: SubledgerEntryKind) -> list[tuple[UUID, UUID | None, date]]:
        rows = session.execute(
            select(
                subledger_line.c.contract_id,
                subledger_line.c.obligation_id,
                func.min(subledger_line.c.effective_date),
            )
            .where(*conditions, subledger_line.c.entry_kind == kind.value)
            .group_by(subledger_line.c.contract_id, subledger_line.c.obligation_id)
            .order_by(subledger_line.c.contract_id, subledger_line.c.obligation_id)
        ).tuples()
        return [
            (
                UUID(str(contract_id)),
                None if obligation_id is None else UUID(str(obligation_id)),
                first,
            )
            for contract_id, obligation_id, first in rows
        ]

    billed = {
        (contract_id, obligation_id): first
        for contract_id, obligation_id, first in firsts(SubledgerEntryKind.BILLING)
    }
    refs: list[monitor_rules.UnbilledRevenueRef] = []
    for contract_id, obligation_id, first_revenue in firsts(SubledgerEntryKind.REVENUE_RECOGNITION):
        candidates = [
            found
            for found in (billed.get((contract_id, obligation_id)), billed.get((contract_id, None)))
            if found is not None
        ]
        refs.append(
            monitor_rules.UnbilledRevenueRef(
                contract_id=contract_id,
                obligation_id=obligation_id,
                first_recognition_date=first_revenue,
                first_billing_date=min(candidates) if candidates else None,
            )
        )
    return refs


def _liability_layers(
    session: Session, scope: gates.PeriodScope
) -> list[monitor_rules.LiabilityLayerRef]:
    """Current-version layer balances through the close date, in both currencies.

    Consumption is subtracted from its originating layer. A remeasurement changes only the
    functional carrying amount; its transaction amount is the amount remeasured, not a new flow.
    """
    movement = fx_layer_movement.c
    created = movement.movement_kind == "LIABILITY_LAYER_CREATED"
    consumed = movement.movement_kind == "LIABILITY_LAYER_CONSUMED"
    rows = session.execute(
        select(
            movement.contract_id,
            movement.layer_key,
            movement.txn_currency,
            movement.functional_currency,
            func.sum(
                case((created, movement.amount_txn), (consumed, -movement.amount_txn), else_=0)
            ),
            func.sum(
                case((consumed, -movement.amount_functional), else_=movement.amount_functional)
            ),
        )
        .where(
            movement.entity_id == scope.entity_id,
            movement.book_code == scope.book_code,
            movement.balance_role == "CONTRACT_LIABILITY",
            movement.movement_kind.in_(
                [
                    "LIABILITY_LAYER_CREATED",
                    "LIABILITY_LAYER_CONSUMED",
                    "LIABILITY_LAYER_REMEASURED",
                ]
            ),
            movement.effective_date <= scope.end_date,
            _current_version(movement.contract_id, movement.contract_version_id, scope.book_code),
        )
        .group_by(
            movement.contract_id,
            movement.layer_key,
            movement.txn_currency,
            movement.functional_currency,
        )
        .order_by(movement.contract_id, movement.layer_key)
    ).tuples()
    result = []
    for contract_id, key, txn_currency, functional_currency, txn, functional in rows:
        # One finding per layer. Prefer the transaction deficit when both currencies are negative.
        use_functional = txn >= 0 and functional < 0
        result.append(
            monitor_rules.LiabilityLayerRef(
                contract_id=UUID(str(contract_id)),
                layer_key=str(key),
                open_balance=Decimal(functional if use_functional else txn),
                currency=str(functional_currency if use_functional else txn_currency).strip(),
            )
        )
    return result


def _recognitions(session: Session, scope: gates.PeriodScope) -> list[monitor_rules.RecognitionRef]:
    rows = session.execute(
        select(
            schedule_line.c.contract_id,
            schedule_line.c.subject_id,
            obligation_version.c.end_date,
            schedule_line.c.amount,
        )
        .select_from(
            schedule_line.join(
                schedule,
                and_(
                    schedule.c.tenant_id == schedule_line.c.tenant_id,
                    schedule.c.id == schedule_line.c.schedule_id,
                ),
            )
            .join(
                contract_version,
                and_(
                    contract_version.c.tenant_id == schedule_line.c.tenant_id,
                    contract_version.c.id == schedule_line.c.contract_version_id,
                ),
            )
            .join(
                obligation_version,
                and_(
                    obligation_version.c.tenant_id == schedule_line.c.tenant_id,
                    obligation_version.c.contract_version_id == schedule_line.c.contract_version_id,
                    obligation_version.c.obligation_id == schedule_line.c.subject_id,
                ),
            )
        )
        .where(
            schedule_line.c.entity_id == scope.entity_id,
            schedule_line.c.book_code == scope.book_code,
            schedule_line.c.period_id == scope.period_id,
            schedule_line.c.subject_type == OBLIGATION_SUBJECT,
            schedule_line.c.amount != 0,
            schedule.c.schedule_kind == REVENUE_SCHEDULE,
            obligation_version.c.end_date.is_not(None),
            _current_version(
                schedule_line.c.contract_id, schedule_line.c.contract_version_id, scope.book_code
            ),
        )
        .order_by(schedule_line.c.contract_id, schedule_line.c.subject_id, schedule_line.c.id)
    ).tuples()
    return [
        monitor_rules.RecognitionRef(
            contract_id=UUID(str(contract_id)),
            obligation_id=UUID(str(obligation_id)),
            obligation_end_date=end_date,
            period_start=scope.start_date,
            amount=Decimal(amount),
        )
        for contract_id, obligation_id, end_date, amount in rows
    ]


def _contracts(
    session: Session, scope: gates.PeriodScope
) -> list[monitor_rules.ContractActivityRef]:
    rows = session.execute(
        select(contract.c.id, func.max(contract_event.c.effective_date))
        .select_from(
            contract.outerjoin(
                contract_event,
                and_(
                    contract_event.c.tenant_id == contract.c.tenant_id,
                    contract_event.c.contract_id == contract.c.id,
                ),
            )
        )
        .where(
            contract.c.contracting_entity_id == scope.entity_id,
            contract.c.status == ContractStatus.ACTIVE.value,
        )
        .group_by(contract.c.id)
        .order_by(contract.c.id)
    ).tuples()
    return [
        monitor_rules.ContractActivityRef(
            contract_id=UUID(str(contract_id)), is_active=True, last_event_date=last
        )
        for contract_id, last in rows
    ]


def fx_requirement_query(entity_id: UUID, functional: str) -> Select[Any]:
    """One row per non-functional transaction currency of the entity's ACTIVE contracts with a
    representative contract id: the minimum of the id's TEXT form — PostgreSQL has no ``min(uuid)``
    (the ci stage of the integrated batch on main 0cb36c14 failed every ``run_monitors`` here)."""
    return (
        select(contract.c.transaction_currency, func.min(cast(contract.c.id, Text)))
        .where(
            contract.c.contracting_entity_id == entity_id,
            contract.c.status == ContractStatus.ACTIVE.value,
            contract.c.transaction_currency != functional,
        )
        .group_by(contract.c.transaction_currency)
        .order_by(contract.c.transaction_currency)
    )


def _fx(session: Session, scope: gates.PeriodScope) -> list[monitor_rules.FxRequirementRef]:
    functional = str(scope.functional_currency)
    if not functional:
        functional = str(
            session.execute(
                select(legal_entity.c.functional_currency).where(
                    legal_entity.c.id == scope.entity_id
                )
            ).scalar_one()
        )
    rows = session.execute(fx_requirement_query(scope.entity_id, functional)).tuples()
    refs: list[monitor_rules.FxRequirementRef] = []
    for currency, first_contract in rows:
        present = session.execute(
            select(func.count())
            .select_from(EFFECTIVE_RATES)
            .where(
                EFFECTIVE_RATES.c.resolution_rank == 1,
                EFFECTIVE_RATES.c.rate_type == RateType.CLOSING.value,
                EFFECTIVE_RATES.c.base_currency == str(currency),
                EFFECTIVE_RATES.c.quote_currency == functional,
                EFFECTIVE_RATES.c.effective_date == scope.end_date,
            )
        ).scalar_one()
        refs.append(
            monitor_rules.FxRequirementRef(
                contract_id=UUID(str(first_contract)),
                txn_currency=str(currency),
                functional_currency=functional,
                rate_date=scope.end_date,
                rate_present=int(present) > 0,
            )
        )
    return refs


def collect_inputs(session: Session, scope: gates.PeriodScope) -> monitor_rules.MonitorInputs:
    """The input records of the six monitors for the period (module docstring)."""
    return monitor_rules.MonitorInputs(
        invoices=_invoices(session, scope),
        unbilled=_unbilled(session, scope),
        layers=_liability_layers(session, scope),
        recognitions=_recognitions(session, scope),
        contracts=_contracts(session, scope),
        fx=_fx(session, scope),
    )


# --- the run -------------------------------------------------------------------------------------


def _notify_created(
    uow: UnitOfWork,
    findings: Sequence[monitor_rules.MonitorFinding],
    raised: Sequence[RaisedItem],
) -> None:
    """NTF-11 for each item created now: the owner when set (never at creation), else the Revenue
    Accountants whose role covers the finding's entity (ruling Q-5; 05 NTR-02 rev 1.180: a
    Revenue Accountant of another entity alone is not told)."""
    recipients: dict[UUID, list[UUID]] = {}
    for finding, item in zip(findings, raised, strict=True):
        if not item.created:
            continue
        if finding.entity_id not in recipients:
            recipients[finding.entity_id] = role_holders(
                uow.session,
                role_codes=[REVENUE_ACCOUNTANT],
                entity_id=finding.entity_id,
                at=uow.now,
            )
        notify(
            uow,
            recipient_membership_ids=recipients[finding.entity_id],
            kind=NotificationKind.EXCEPTION_ASSIGNED,
            title=f"Exception: {finding.code}",  # PRD NTF-11
            body=finding.message,
            link_path=subjects.EXCEPTION_LINK.format(item_id=item.id),
            subject_type=EXCEPTION_OBJECT,
            subject_id=item.id,
        )


def _evaluate(uow: UnitOfWork, scope: gates.PeriodScope) -> monitor_rules.MonitorOutcome:
    """The findings of the six monitors for one entity, book and period, from the facts as they
    are now and the thresholds and severities in force at the run's instant."""
    session = uow.session
    return monitor_rules.evaluate(
        collect_inputs(session, scope),
        period_start=scope.start_date,
        period_end=scope.end_date,
        entity_id=scope.entity_id,
        period_id=scope.period_id,
        settings=settings_of(session, scope, known_at=uow.now),
        overrides=overrides_of(session, at=uow.now),
    )


def _settle_gone(
    uow: UnitOfWork, scope: gates.PeriodScope, outcome: monitor_rules.MonitorOutcome
) -> tuple[tuple[UUID, ...], int]:
    """Settle the open ``DATA_QUALITY`` items of the run's entity and period whose finding is gone
    (04 T-IMP-05 rev 1.185 "A monitor finding that is gone"; supervisor ruling R-111 (j), item
    DQ-RESOLVE-1): (the ids settled, the number kept for a locked book).

    An item's key carries entity and period and no book, while a run evaluates one book — three
    monitors read rows of the book and two thresholds resolve per book. A finding is therefore gone
    only when NO book of the entity makes it: when this run has an open item its own findings do
    not name, it evaluates the entity's other books whose state for the period is evaluated, here,
    and settles what none of them finds. While another book's state is ``closed`` or
    ``permanently_locked`` nothing of the period is settled — that book is not evaluated and keeps
    the period's open items; a ``future`` state holds no finding and does not count."""
    session = uow.session
    found = set(outcome.dedupe_keys())
    open_items = open_keys(
        session,
        source=ExceptionSource.DATA_QUALITY,
        entity_id=scope.entity_id,
        period_id=scope.period_id,
    )
    gone = [(item_id, key) for item_id, key in open_items if key not in found]
    if not gone:
        return (), 0
    others = session.execute(
        select(period_state.c.book_code, period_state.c.state)
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.period_id == scope.period_id,
            period_state.c.book_code != scope.book_code,
        )
        .order_by(period_state.c.book_code)
    ).all()
    states = {str(getattr(row.book_code, "value", row.book_code)): str(row.state) for row in others}
    if any(state in LOCKED_STATES for state in states.values()):
        return (), len(gone)
    books = [str(scope.book_code)]
    for book, state in states.items():
        if state not in gates.EVALUATED_STATES:
            continue
        other = gates.scope_of_period(session, scope.entity_id, book, scope.period_id)
        if other is None:
            continue
        found |= _evaluate(uow, other).dedupe_keys()
        books.append(book)
    resolution = GONE.format(period_key=scope.period_key, books=", ".join(sorted(books)))
    settled = settle_gone(
        uow, [item_id for item_id, key in gone if key not in found], resolution=resolution
    )
    return settled, 0


def run_monitors(uow: UnitOfWork, entity_id: UUID, book_code: str, period_id: UUID) -> MonitorRun:
    """Evaluate the six monitors for the period, record the findings as exception items (one open
    item per rule and subject; re-runs count the open item again), notify new items and return the
    ``DATA_QUALITY_CLEAR`` gate result. A finding whose latest item was waived by an approved
    request, and whose code, severity and message are unchanged, stands waived: nothing is raised
    for it (``exceptions.standing_waiver``; supervisor ruling R-62 (c)). An open item of the entity
    and period that no evaluated book of the entity finds any more is settled — RESOLVED by the
    system — before the gate is read (``_settle_gone``; 04 T-IMP-05 rev 1.185). 404 ``not-found``
    for an unknown period state; a period that is not ``open``, ``closing`` or ``reopened`` is not
    evaluated and keeps its open items."""
    session = uow.session
    scope = gates.scope_of_period(session, entity_id, book_code, period_id)
    if scope is None:
        raise Problem("not-found")
    if scope.state not in gates.EVALUATED_STATES:
        open_blocking = gates.data_quality_blocking(session, scope)
        return MonitorRun(
            scope=scope,
            outcome=monitor_rules.MonitorOutcome(),
            raised=(),
            open_blocking=open_blocking,
            gate=gates.data_quality_gate(open_blocking, at=uow.now),
        )
    outcome = _evaluate(uow, scope)
    raised_findings: list[monitor_rules.MonitorFinding] = []
    raised_items: list[RaisedItem] = []
    waived: list[UUID] = []
    for finding in outcome.findings:
        covered = standing_waiver(
            uow,
            finding.dedupe_key,
            code=finding.code,
            severity=finding.severity,
            message=finding.message,
        )
        if covered is not None:
            waived.append(covered)
            continue
        raised_findings.append(finding)
        raised_items.append(
            raise_exception_item(
                uow,
                source=ExceptionSource.DATA_QUALITY,
                code=finding.code,
                severity=finding.severity,
                message=finding.message,
                dedupe=finding.dedupe_key,
                severity_cause=SEVERITY_CAUSE,
                business_key=finding.subject,
                contract_id=finding.contract_id,
                obligation_id=finding.obligation_id,
                entity_id=scope.entity_id,
                period_id=scope.period_id,
            )
        )
    raised = tuple(raised_items)
    _notify_created(uow, raised_findings, raised)
    settled, kept = _settle_gone(uow, scope, outcome)  # before the gate reads the open items
    open_blocking = gates.data_quality_blocking(session, scope)
    gate = gates.data_quality_gate(open_blocking, at=uow.now)
    run = MonitorRun(
        scope=scope,
        outcome=outcome,
        raised=raised,
        open_blocking=open_blocking,
        gate=gate,
        waived=tuple(waived),
        settled=settled,
        kept_for_locked_book=kept,
    )
    uow.audit(
        action=RUN_ACTION,
        object_type=STATE_OBJECT,
        object_id=scope.state_id,
        object_version=str(scope.row_version),
        after={
            "entity_id": str(scope.entity_id),
            "book_code": scope.book_code,
            "period_id": str(scope.period_id),
            "findings": len(outcome.findings),
            "blocking": outcome.blocking,
            "warnings": outcome.warnings,
            "created": run.created,
            "seen_again": run.seen_again,
            "waived": len(run.waived),
            "settled": len(run.settled),
            "kept_for_locked_book": run.kept_for_locked_book,
            "severity_changed": run.severity_changed,
            "open_blocking": open_blocking,
            "gate": gate.status.value,
        },
    )
    return run


def summary(run: MonitorRun) -> Mapping[str, Any]:
    """Counts for a close-run step summary (CLO-19 ``EXCEPTION_CHECK``)."""
    return {
        "findings": len(run.outcome.findings),
        "blocking": run.outcome.blocking,
        "warnings": run.outcome.warnings,
        "created": run.created,
        "seen_again": run.seen_again,
        "waived": len(run.waived),
        "settled": len(run.settled),
        "severity_changed": run.severity_changed,
        "open_blocking": run.open_blocking,
    }
