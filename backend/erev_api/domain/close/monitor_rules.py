"""CLO-5 data-quality monitors as pure rules (04 §15.4 table 15.4-E; REQ-CLS-019; T-PLT-31
``close.dq_revenue_without_billing_days`` and ``close.dq_inactive_contract_days``; T-IMP-05
``dedupe_key``; E-43 severity mapping; T-REF-24 to T-REF-26 ``DATA_QUALITY`` rule sets).

The DB-bound producer of CLO-5 (``close/monitors.py::run_monitors``, run by the close run's
``EXCEPTION_CHECK`` step and the cockpit refresh) assembles the input records of one entity, book
and period and calls ``evaluate``; it then upserts one ``exception_item`` per finding by
``dedupe_key`` (source ``DATA_QUALITY``) and stores the ``DATA_QUALITY_CLEAR`` gate result. Nothing
here reads a session or the clock: the period bounds and the thresholds are parameters.

Duplicate invoices follow the supervisor's ruling Q-8 (F-CLO preparation record §11): the same
(``source_system``, ``external_invoice_id``, ``external_version``) recorded twice, or distinct
external ids with one (customer, invoice number, amount, issue date); a later version of one
external id is a correction path. The spec owner confirms the wording at the CLO-5 build.

Severity: the table's default, or the ``outputs.severity`` of a published tenant ``DATA_QUALITY``
rule whose ``rule_key`` is the monitor code (``severity_of``); ``ERROR`` maps to ``BLOCKING`` and
``WARNING`` to ``WARNING`` (E-43). Only ``BLOCKING`` findings count against the lock gate
(REQ-CLS-019 "error results block lock"). "More than N days" is strictly greater than N.

``tests/unit/close/test_monitor_rules.py`` is the contract (F-CLO preparation record
``docs/reviews/loop/prod/F-CLO-prep.md`` §4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal
from uuid import UUID

from erev_api.domain.close import gates
from erev_api.enums import ExceptionSeverity, ExceptionSource

Severity = Literal["ERROR", "WARNING"]

REVENUE_WITHOUT_BILLING_DAYS: Final = "close.dq_revenue_without_billing_days"  # T-PLT-31
INACTIVE_CONTRACT_DAYS: Final = "close.dq_inactive_contract_days"
DEFAULT_SETTINGS: Final[Mapping[str, int]] = {
    REVENUE_WITHOUT_BILLING_DAYS: 60,
    INACTIVE_CONTRACT_DAYS: 90,
}
# T-PLT-31 value ranges: "integer 1-365" and "integer 1-730" (F-CLO-R3: enforced here as well as by
# the settings adapter, so an out-of-range supplied value never reaches a predicate).
SETTING_RANGES: Final[Mapping[str, tuple[int, int]]] = {
    REVENUE_WITHOUT_BILLING_DAYS: (1, 365),
    INACTIVE_CONTRACT_DAYS: (1, 730),
}
DATA_QUALITY_DETAIL: Final = gates.DATA_QUALITY_DETAIL  # SCREENS_B §1.1 :368; owned by gates.py
SOURCE: Final = ExceptionSource.DATA_QUALITY.value


@dataclass(frozen=True, slots=True)
class MonitorSpec:
    code: str
    default_severity: Severity
    setting_key: str | None
    description: str


# Table 15.4-E in its order.
MONITORS: Final[tuple[MonitorSpec, ...]] = (
    MonitorSpec(
        "DQ_DUPLICATE_INVOICE",
        "ERROR",
        None,
        "Two source invoices with the same external invoice id from one source system (Q-8: the "
        "same external id and version twice, or distinct external ids with one identity tuple)",
    ),
    MonitorSpec(
        "DQ_REVENUE_WITHOUT_BILLING",
        "WARNING",
        REVENUE_WITHOUT_BILLING_DAYS,
        "Revenue recognised without billing for more than the configured days",
    ),
    MonitorSpec(
        "DQ_NEGATIVE_LIABILITY_LAYER",
        "ERROR",
        None,
        "A contract-liability layer (T-CON-18) has a negative open balance",
    ),
    MonitorSpec(
        "DQ_RECOGNITION_AFTER_POB_END",
        "WARNING",
        None,
        "Revenue recognised in a period that starts after the POB end date",
    ),
    MonitorSpec(
        "DQ_INACTIVE_CONTRACT",
        "WARNING",
        INACTIVE_CONTRACT_DAYS,
        "Active contract without any event for more than the configured days",
    ),
    MonitorSpec("FX_RATE_MISSING", "ERROR", None, "A required FX rate is absent"),
)
_ORDER: Final[Mapping[str, int]] = {spec.code: index for index, spec in enumerate(MONITORS)}
DEFAULT_SEVERITIES: Final[Mapping[str, Severity]] = {
    spec.code: spec.default_severity for spec in MONITORS
}
CODES: Final[frozenset[str]] = frozenset(_ORDER)


# --- input records ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceInvoiceRef:
    """One T-SRC-04 row: the ``(source_system, external_invoice_id, external_version)`` key of
    ``ux_source_invoice``, the row id and, when known, the identity tuple of the supervisor's ruling
    Q-8 (customer, invoice number, amount, issue date). A later ``external_version`` of one external
    id is a version or correction path, never a duplicate."""

    source_system: str
    external_invoice_id: str
    external_version: str  # T-SRC-04 text; a later version is a correction path (Q-8)
    row_id: UUID
    customer_ref: str | None = None
    invoice_number: str | None = None
    amount: Decimal | None = None
    issue_date: date | None = None

    def identity(self) -> tuple[str, str, Decimal, date] | None:
        """The Q-8 identity tuple, or None while any member is unknown."""
        if (
            self.customer_ref is None
            or self.invoice_number is None
            or self.amount is None
            or self.issue_date is None
        ):
            return None
        return (self.customer_ref, self.invoice_number, self.amount, self.issue_date)


@dataclass(frozen=True, slots=True)
class UnbilledRevenueRef:
    """An obligation with recognised revenue: the first recognition date and the first billing
    date."""

    contract_id: UUID
    obligation_id: UUID | None  # None: contract-level revenue lines
    first_recognition_date: date
    first_billing_date: date | None


@dataclass(frozen=True, slots=True)
class LiabilityLayerRef:
    """A T-CON-18 ``CONTRACT_LIABILITY`` layer with its open balance at the period end."""

    contract_id: UUID
    layer_key: str
    open_balance: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class RecognitionRef:
    """Revenue recognised for an obligation in the period."""

    contract_id: UUID
    obligation_id: UUID
    obligation_end_date: date
    period_start: date
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ContractActivityRef:
    """A contract with its status and the date of its latest event."""

    contract_id: UUID
    is_active: bool
    last_event_date: date | None


@dataclass(frozen=True, slots=True)
class FxRequirementRef:
    """A rate the period needs: transaction to functional currency at ``rate_date``."""

    contract_id: UUID
    txn_currency: str
    functional_currency: str
    rate_date: date
    rate_present: bool


@dataclass(frozen=True, slots=True)
class MonitorInputs:
    invoices: Sequence[SourceInvoiceRef] = ()
    unbilled: Sequence[UnbilledRevenueRef] = ()
    layers: Sequence[LiabilityLayerRef] = ()
    recognitions: Sequence[RecognitionRef] = ()
    contracts: Sequence[ContractActivityRef] = ()
    fx: Sequence[FxRequirementRef] = ()


# --- findings -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonitorFinding:
    code: str
    severity: ExceptionSeverity
    subject: str
    message: str
    entity_id: UUID
    period_id: UUID
    contract_id: UUID | None = None
    obligation_id: UUID | None = None

    @property
    def dedupe_key(self) -> str:
        """T-IMP-05 rev 1.22 (supervisor ruling D-98 57): ``<source>:<code>:<entity>:<period>:
        <subject>`` — the identity carries the affected scope, so a recurrence in another entity or
        period is a distinct unresolved item and never an occurrence bump on the first. The subject
        already names the contract or obligation where the monitor is contract-scoped."""
        return f"{SOURCE}:{self.code}:{self.entity_id}:{self.period_id}:{self.subject}"


@dataclass(frozen=True, slots=True)
class MonitorOutcome:
    findings: tuple[MonitorFinding, ...] = field(default=())

    @property
    def blocking(self) -> int:
        return sum(1 for f in self.findings if f.severity is ExceptionSeverity.BLOCKING)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity is ExceptionSeverity.WARNING)

    def dedupe_keys(self) -> frozenset[str]:
        return frozenset(f.dedupe_key for f in self.findings)


def exception_severity(severity: Severity) -> ExceptionSeverity:
    """E-43: ``ERROR`` → ``BLOCKING``, ``WARNING`` → ``WARNING``."""
    return ExceptionSeverity.BLOCKING if severity == "ERROR" else ExceptionSeverity.WARNING


def severity_of(code: str, overrides: Mapping[str, str]) -> Severity:
    """The monitor's severity: a published tenant rule's ``outputs.severity`` (T-REF-26, keyed by
    the monitor code) or the table default. ``KeyError`` for an unknown code; ``ValueError`` for
    a value outside ``ERROR`` and ``WARNING``."""
    default = DEFAULT_SEVERITIES[code]
    value = overrides.get(code)
    if value is None:
        return default
    if value == "ERROR":
        return "ERROR"
    if value == "WARNING":
        return "WARNING"
    raise ValueError(f"DATA_QUALITY rule {code}: severity {value!r} is not ERROR or WARNING")


def _threshold(settings: Mapping[str, int], key: str) -> int:
    """The T-PLT-31 day count of ``key``, enforced locally to the catalogue range (F-CLO-R3): an
    integer within ``SETTING_RANGES[key]``; ``ValueError`` names the key otherwise."""
    value = settings.get(key, DEFAULT_SETTINGS[key])
    low, high = SETTING_RANGES[key]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{key} must be an integer number of days from {low} to {high}")
    return value


def evaluate(
    inputs: MonitorInputs,
    *,
    period_start: date,
    period_end: date,
    entity_id: UUID,
    period_id: UUID,
    settings: Mapping[str, int] | None = None,
    overrides: Mapping[str, str] | None = None,
) -> MonitorOutcome:
    """Every finding of the six monitors for one entity and period (the affected scope every finding
    carries, D-98 57), ordered by table position and subject; deterministic for equal inputs
    (``test_monitor_rerun_is_idempotent``)."""
    if period_end < period_start:
        raise ValueError("period_end precedes period_start")
    thresholds = settings or {}
    severities = overrides or {}
    without_billing_days = _threshold(thresholds, REVENUE_WITHOUT_BILLING_DAYS)
    inactive_days = _threshold(thresholds, INACTIVE_CONTRACT_DAYS)

    raw: list[tuple[str, str, str, UUID | None, UUID | None]] = []

    # Q-8 rule 1: one (source system, external id, version) recorded more than once.
    rows_by_key: dict[tuple[str, str, str], set[UUID]] = {}
    dates_by_key: dict[tuple[str, str, str], set[date]] = {}
    # Q-8 rule 2: distinct external ids sharing one (customer, invoice number, amount, date).
    ids_by_identity: dict[tuple[str, str, Decimal, date], set[str]] = {}
    for invoice in inputs.invoices:
        key = (invoice.source_system, invoice.external_invoice_id, invoice.external_version)
        rows_by_key.setdefault(key, set()).add(invoice.row_id)
        if invoice.issue_date is not None:
            dates_by_key.setdefault(key, set()).add(invoice.issue_date)
        identity = invoice.identity()
        if identity is not None:
            ids_by_identity.setdefault(identity, set()).add(invoice.external_invoice_id)

    def concerns_this_period(concerned: date | None) -> bool:
        """SCH10-PERIOD-SCOPE-1 (Codex production-20260922-0505 §1 as corrected by 0511 / 0522;
        supervisor ruling 2026-09-22; 04 15.4-E rev 1.82): a duplicate is attributed to the period
        of its EARLIEST dated participating invoice and to every LATER evaluated period while
        unresolved (the D-98 57 recurrence), never to a period that ends before that date — data
        of September is not January's blocker, while an open August whose own invoice takes part in
        an August + September duplicate is gated (the gate is preventive, REQ-CLS-019). A wholly
        undated set cannot be attributed and keeps surfacing in every evaluated period (a stated
        limitation, pinned by its witness)."""
        return concerned is None or concerned <= period_end

    for (system, external_id, version), rows in rows_by_key.items():
        if len(rows) > 1 and concerns_this_period(
            min(dates_by_key.get((system, external_id, version), ()), default=None)
        ):
            raw.append(
                (
                    "DQ_DUPLICATE_INVOICE",
                    f"{system}:{external_id}:{version}",
                    f"Source invoice {external_id} version {version} from {system} appears "
                    f"{len(rows)} times.",
                    None,
                    None,
                )
            )
    for (customer, number, amount, issued), external_ids in ids_by_identity.items():
        if len(external_ids) > 1 and concerns_this_period(issued):
            listed = ", ".join(sorted(external_ids))
            raw.append(
                (
                    "DQ_DUPLICATE_INVOICE",
                    f"{customer}:{number}:{amount}:{issued.isoformat()}",
                    f"Invoices {listed} share customer {customer}, invoice number {number}, amount "
                    f"{amount} and date {issued.isoformat()}.",
                    None,
                    None,
                )
            )

    for unbilled in inputs.unbilled:
        if unbilled.first_billing_date is not None:
            continue
        days = (period_end - unbilled.first_recognition_date).days
        if days > without_billing_days:
            raw.append(
                (
                    "DQ_REVENUE_WITHOUT_BILLING",
                    str(unbilled.obligation_id or unbilled.contract_id),
                    f"Revenue recognised since {unbilled.first_recognition_date.isoformat()} "
                    f"without billing for {days} days (limit {without_billing_days}).",
                    unbilled.contract_id,
                    unbilled.obligation_id,
                )
            )

    for layer in inputs.layers:
        if layer.open_balance < 0:
            raw.append(
                (
                    "DQ_NEGATIVE_LIABILITY_LAYER",
                    layer.layer_key,
                    f"Contract liability layer {layer.layer_key} has a negative open balance of "
                    f"{layer.open_balance} {layer.currency}.",
                    layer.contract_id,
                    None,
                )
            )

    for recognition in inputs.recognitions:
        if recognition.amount != 0 and recognition.period_start > recognition.obligation_end_date:
            raw.append(
                (
                    "DQ_RECOGNITION_AFTER_POB_END",
                    f"{recognition.obligation_id}:{recognition.period_start.isoformat()}",
                    f"Revenue of {recognition.amount} recognised in the period starting "
                    f"{recognition.period_start.isoformat()}, after the obligation end date "
                    f"{recognition.obligation_end_date.isoformat()}.",
                    recognition.contract_id,
                    recognition.obligation_id,
                )
            )

    for contract in inputs.contracts:
        if not contract.is_active:
            continue
        if contract.last_event_date is None:
            message = "Active contract without any event."
        else:
            days = (period_end - contract.last_event_date).days
            if days <= inactive_days:
                continue
            message = f"Active contract without any event for {days} days (limit {inactive_days})."
        raw.append(
            ("DQ_INACTIVE_CONTRACT", str(contract.contract_id), message, contract.contract_id, None)
        )

    for need in inputs.fx:
        if need.txn_currency != need.functional_currency and not need.rate_present:
            raw.append(
                (
                    "FX_RATE_MISSING",
                    f"{need.txn_currency}:{need.functional_currency}:{need.rate_date.isoformat()}",
                    f"No rate from {need.txn_currency} to {need.functional_currency} for "
                    f"{need.rate_date.isoformat()}.",
                    need.contract_id,
                    None,
                )
            )

    # One finding per (code, subject): the first record supplied names the item when several
    # records share a dedupe subject (for example two contracts missing the same closing rate).
    first: dict[tuple[str, str], tuple[str, str, str, UUID | None, UUID | None]] = {}
    for row in raw:
        first.setdefault((row[0], row[1]), row)
    findings = tuple(
        MonitorFinding(
            code=code,
            severity=exception_severity(severity_of(code, severities)),
            subject=subject,
            message=message,
            entity_id=entity_id,
            period_id=period_id,
            contract_id=contract_id,
            obligation_id=obligation_id,
        )
        for code, subject, message, contract_id, obligation_id in sorted(
            first.values(), key=lambda row: (_ORDER[row[0]], row[1])
        )
    )
    return MonitorOutcome(findings)


def data_quality_gate(open_blocking: int, *, at: datetime) -> gates.GateResult:
    """``gates.data_quality_gate``: the ``DATA_QUALITY_CLEAR`` gate from the count of open
    ``BLOCKING`` ``DATA_QUALITY`` items of the period (kept here for the CLO-5 callers)."""
    return gates.data_quality_gate(open_blocking, at=at)
