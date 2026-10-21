"""RPT-06 ``rpo`` Remaining performance obligations, and the RPO rollforward lines of RPT-07
(SCREENS_B §5.6.1 RPT-06, RPT-07, §0.5 RV-12; 04 §16.9 API-S-RpoReportData; ENGINE_SPEC_B §15.2.3
S15-R-08 to S15-R-12, EX-15-A; POLICIES POL-193, POL-197 to POL-201; D-76; 03 REQ-RPT-009,
REQ-RPT-010, REQ-RPT-025; CTL-027, CTL-030; BUILD_SPEC RPS-4).

**Version at a date.** Each group's versions of the book recorded by the cutoff (``tie_outs``), in
version order, carry the latest effective date of their causing events (carried forward for a
version caused by no event). The version at date d is the last one effective on or before d, so a
later-dated event does not change an earlier RPO.

**Entry at activation** (ENGINE_SPEC_B S15-R-12 rev 1.161, "groups activated in the period"; item
RPT-RPO-ROLLFWD-1; supervisor ruling R-121 (g)). A contract enters the disclosures on the day
it becomes a contract: the first included version of its chain counts from the effective date of
the ``CONTRACT_ACTIVATED``, ``CONTRACT_CRITERIA_MET`` (for the book it admits) or
``OPENING_BALANCE_ESTABLISHED`` event of that contract among the version's causes
(``ENTRY_EVENTS``), not from the latest of its causing events. A computation takes in every event
recorded so far, so a first version is often caused by the activation and by measurements dated
after it — a progress report, an invoice — which change no allocation. Dated by the last of
them, the contract was missing from the RPO of every date in between, and the period of that
last event showed the whole allocation as new beside revenue of earlier periods that nothing
explained. Every figure of the version is read at the date asked for (below), so the earlier
entry states the remainder of that date. Later versions are dated as before.

**The versions of a contract** (item RPT-FORMER-GROUP-VERSIONS-1; 04 T-CON-04; ENGINE_SPEC S02-R-09,
S02-R-10). A version counts for a member contract only while that contract is a member of the
version's group: a contract is read along its own chain — the versions of each group it has been a
member of that were recorded during that membership, in the order of the memberships — and the
version at date d is the last one of the chain effective on or before d (effective dates carried
forward along the chain). A contract computed in its own group and combined later is therefore read
from its former group up to the combined group's first version and from the combined group after
it, never from both; the last version of a group it has left is history. Before, the versions were
read group by group: after an approved combination each member's obligations were stated twice
(RPO, the rollforward's ``NEW_CONTRACTS`` and ``REVENUE``) and the lock's ``RPO`` dataset was
refused for a duplicate row key.

**RPO of an obligation at d** (S15-R-08, S15-INV-02; rev 1.127, item RPT-ASOF-FIGURES-1,
supervisor ruling R-116 (c)): for an obligation that is not cancelled, of a version whose status
enters the disclosures, its remainder at d — the allocated constrained transaction price less
revenue to d — as the reader of the contract reads states it at the cut of d
(``reports.cuts.obligations_at``; 04 API-C-10): the scheduled part plus the awaiting-trigger part.
The version's stored ``awaiting_trigger_amount`` is the amount at the version's own date; added to
the schedule lines after d it stated again whatever was recognised since. ``measure`` reads the
obligations of a run at its dates. **Bands** (POL-201, S15-R-10): upper bounds add_months(d, b),
the last band open; the scheduled part is placed by the period ends of the version's later
schedule lines (``reports.cuts.scheduled_after``), the awaiting part by the obligation's end date
or in the first band. ``current`` is the part placed within 12 months after d; ``noncurrent`` the
rest.

**Exemptions** (S15-R-09), resolved for the contracting entity at ``known_at``, so a DRAFT registry
version is not in force (CTL-027): POL-197 ``APPLY`` exempts every obligation of a contract whose
original inception segments end before the first anniversary (inclusive service dates).
Original terms come from verified retained computation input, including templates and voids;
subsequent extensions or shortening do not replace them. Terms are retained for reruns/cells;
POL-198 ``APPLY`` exempts ``RIGHT_TO_INVOICE`` obligations. An exempt obligation leaves section 1
and is listed in section 2 with the expedient, the nature (product name), the remaining months
(month ends after d through the end date), the excluded amount and its description (50-15).

**Rollforward lines** (S15-R-12): per obligation, opening = the RPO at the day before the range by
the version at that day; each version effective in the range adds its allocation change on the line
of its cause (activation of a group without an included version: ``NEW_CONTRACTS``;
``CONTRACT_AMENDED``, material-right events and ``COMBINATION_CHANGED``: ``MODIFICATIONS``;
``ESTIMATE_CHANGED`` and ``USAGE_REPORTED`` (including royalty statements):
``VC_ESTIMATE_CHANGES``; ``CONTRACT_TERMINATED``: ``CANCELLATIONS``);
``REVENUE`` = −(revenue to the range end − revenue to the day before) by the closing version, both
read at their cuts; closing = the RPO at the range end; ``UNEXPLAINED`` = closing − opening −
movements (V9). Dated realization traces separate fee allocation from the fixed version
allocation: fees enter variable consideration when realized, with pre-entry realized fees
included in entry and exited fees removed on cancellation. Mixed legacy/dated evidence is
refused because a missing historical component cannot be interpreted as zero. Fixed-allocation
changes with competing event classes remain unexplained pending full cause decomposition.

``LATE_EVENTS`` (S15-R-12 "late events: revenue changes with an origin period before the period";
rev 1.161; item RPT-RPO-ROLLFWD-1) = −(revenue to the day before the range by the CLOSING version
− revenue to that day by the OPENING version): what a version that became effective in the range
recognises for the time before it, which the opening did not state. The revenue line reads both
of its ends from the closing version, so without this line that amount stood in no line and was
"Unexplained": a progress report of a locked period, posted in the range with that period as its
origin. The line is zero when one version is read at both ends. It names the amount by the
versions' dates, not by the ledger: where the earlier period was still open when the event
arrived, the revenue is posted in that period and this report still shows it as a late event of
the range (the limitation SCREENS_B RPT-07 states; a reader of the ledger's posting and origin
periods is a separate item).

[J] L6-3-Q-26 (API-S-RpoReportData): ``GET /report-runs/{id}/data`` is the framework's API-S-List of
rows, so the as-of date and the ordered bands are the control totals ``as_of`` and ``bands``;
section 1 rows carry one money field per band key (the explain ``column_key``), and section 2 rows
carry ``section`` 2 (RPT-R-09) instead of an ``exemptions`` member.
POL-200 reads dated targeted-VC allocations and later allocated deltas from retained traces,
with immutable estimate versions identifying evidenced targeted changes. Only wholly unsatisfied
obligations with no revenue qualify. Net bands and contributors retain currency precision; partial
exclusions are listed separately and their movement is the ``EXEMPTIONS`` rollforward line.
POL-199's quota is zero under the engine's royalty realization model; fixed consideration remains.
[J] L6-3-Q-28 (POL-193 ``ELECT``): a JSON (on-screen) run omits the entity's section 1 and 2 rows
with the RV-12 note; file outputs, which need ``report.export``, keep the dataset.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.dates import add_months, month_ends_between
from erev_engine.formulas import rpo_bands
from erev_engine.stages.s01_canonicalize import contract_subject_key, obligation_subject_key
from erev_engine.stages.s02_contract_identification.status import STATUS_ORDINAL
from erev_engine.trace import SourceRef, Trace
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    customer,
    legal_entity,
    obligation_version,
    product,
    schedule,
    schedule_line,
)
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import (
    cuts,
    elections,
    rpo_boundary_changes,
    rpo_currency,
    rpo_duration,
    rpo_estimate_changes,
    rpo_quotas,
    tie_outs,
)
from erev_api.domain.reports.builders import ReportParams, filter_problem
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, EntityRef, add
from erev_api.enums import BookCode
from erev_api.explain import store as trace_store
from erev_api.problems import Problem
from erev_api.registry.resolve import resolve
from erev_api.uow import UnitOfWork

CODE: Final = "rpo"
TIME_BANDS: Final = "rpo.time_bands"
DEFAULT_BANDS: Final = (12, 24)
CURRENT_MONTHS: Final = 12
APPLY: Final = "APPLY"
RIGHT_TO_INVOICE: Final = "RIGHT_TO_INVOICE"
CANCELLED: Final = "CANCELLED"
TOTAL: Final = "total"
CURRENT: Final = "current"
NONCURRENT: Final = "noncurrent"
TOTAL_PREFIX: Final = "TOTAL:"
# (POL id, registry code, expedient label, description of the excluded consideration).
EXPEDIENTS: Final = (
    (
        "POL-197",
        "rpo.exemption_original_duration_one_year",
        "Original expected duration of one year or less",
        "consideration of a contract with an original expected duration of one year or less "
        "(606-10-50-14(a))",
    ),
    (
        "POL-198",
        "rpo.exemption_right_to_invoice",
        "Right to invoice",
        "consideration the entity has a right to invoice for performance completed to date "
        "(606-10-50-14(b))",
    ),
    (
        "POL-199",
        "rpo.exemption_royalty_vc",
        "Sales- or usage-based royalty",
        "sales- or usage-based royalty consideration of a licence (606-10-50-14A(a))",
    ),
    (
        "POL-200",
        "rpo.exemption_vc_wholly_unsatisfied",
        "Variable consideration allocated to a wholly unsatisfied obligation",
        "variable consideration allocated entirely to a wholly unsatisfied performance "
        "obligation (606-10-50-14A(b))",
    ),
)
DIMENSIONS: Final[Mapping[str, str]] = {
    "CONTRACT": "contract",
    "ENTITY": "entity",
    "PRODUCT_FAMILY": "product_family",
    "CUSTOMER_SEGMENT": "customer_segment",
}
# In report order; ``LATE_EVENTS`` stands where the engine's own rollforward has it (ENGINE_SPEC_B
# S15-R-12; ``erev_engine.stages.s15_disclosures.rpo.ROLLFORWARD_LINES``).
ROLLFORWARD_LINES: Final = (
    "OPENING",
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "EXEMPTIONS",
    "ELIGIBILITY_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "FX",
    "UNEXPLAINED",
    "CLOSING",
)
MOVEMENTS: Final = (
    "NEW_CONTRACTS",
    "MODIFICATIONS",
    "VC_ESTIMATE_CHANGES",
    "EXEMPTIONS",
    "ELIGIBILITY_CHANGES",
    "LATE_EVENTS",
    "REVENUE",
    "CANCELLATIONS",
    "FX",
)
# The events at whose effective date a contract enters the disclosures (module docstring "Entry
# at activation"); the criteria-met event counts for the book its payload names.
ENTRY_EVENTS: Final = tie_outs.ENTRY_EVENTS
CRITERIA_MET: Final = tie_outs.CRITERIA_MET
CAUSE_LINES: Final[Mapping[str, str]] = {
    "CONTRACT_AMENDED": "MODIFICATIONS",
    "MATERIAL_RIGHT_EXERCISED": "MODIFICATIONS",
    "MATERIAL_RIGHT_EXPIRED": "MODIFICATIONS",
    "COMBINATION_CHANGED": "MODIFICATIONS",
    "ESTIMATE_CHANGED": "VC_ESTIMATE_CHANGES",
    "USAGE_REPORTED": "VC_ESTIMATE_CHANGES",
    "CONTRACT_TERMINATED": "CANCELLATIONS",
}
NO_EXEMPTIONS: Final = "No contracts are excluded. {entity} applies no RPO practical expedient."
MIXED_BANDS: Final = "Choose one set of time bands for the entities of the run."

UNKNOWN_CELL: Final = "The run holds no cell {row_key} / {column_key}."


@dataclass(frozen=True, slots=True)
class Band:
    index: int
    key: str
    from_month: int
    to_month: int | None

    def out(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "key": self.key,
            "from_month": self.from_month,
            "to_month": self.to_month,
        }


def bands_of(time_bands: Sequence[int]) -> tuple[Band, ...]:
    """API-S-RpoReportData ``bands`` of ``time_bands`` [b1, …, bn] (04 §16.9)."""
    bounds = sorted({int(item) for item in time_bands})
    found = [Band(0, f"within_{bounds[0]}_months", 1, bounds[0])]
    for index in range(1, len(bounds)):
        found.append(
            Band(
                index,
                f"months_{bounds[index - 1] + 1}_to_{bounds[index]}",
                bounds[index - 1] + 1,
                bounds[index],
            )
        )
    found.append(Band(len(bounds), f"after_{bounds[-1]}_months", bounds[-1] + 1, None))
    return tuple(found)


def band_index(end: date, bounds: Sequence[date]) -> int:
    """The band whose (previous bound, bound] holds ``end``; past the last bound, the open band."""
    for index, bound in enumerate(bounds):
        if end <= bound:
            return index
    return len(bounds)


@dataclass(frozen=True, slots=True)
class _Version:
    id: UUID
    group_id: UUID
    version_no: int
    included: bool
    effective: date
    causes: frozenset[str]
    known_at: datetime | None = None
    # (contract, the effective date of its earliest ``ENTRY_EVENTS`` cause of this version)
    entries: tuple[tuple[UUID, date], ...] = ()
    estimate_events: frozenset[str] = frozenset()
    estimate_dates: tuple[tuple[str, date], ...] = ()
    modification_events: frozenset[str] = frozenset()
    cancellation_events: frozenset[str] = frozenset()
    estimate_order: tuple[tuple[str, int], ...] = ()
    entry_order: tuple[tuple[UUID, int], ...] = ()
    eligibility_exits: tuple[tuple[UUID, date], ...] = ()
    cause_events: frozenset[str] = frozenset()
    dated_slice: bool = False


@dataclass(slots=True)
class _Ob:
    row_id: UUID
    version_id: UUID
    obligation_id: UUID
    contract_id: UUID
    external_id: str
    obligation_key: str
    product_name: str
    product_family: str | None
    customer_name: str | None
    customer_segment: str | None
    entity_id: UUID
    entity_code: str
    currency: str
    recognition_method: str
    end_date: date | None
    inception: date
    allocated: Decimal
    cancelled: bool
    lines: list[tuple[UUID, date, Decimal]] = field(default_factory=list)
    line_nodes: dict[UUID, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObligationRpo:
    ob: _Ob
    as_of: date
    total: Decimal
    placed: tuple[Decimal, ...]
    current: Decimal
    contributors: tuple[
        tuple[str, UUID, Decimal, int, bool], ...
    ]  # (type, id, amount, band, current)
    exemption: str | None
    remaining_months: int
    excluded: Decimal = ZERO
    partial_exemption: str | None = None


@dataclass(frozen=True, slots=True)
class Store:
    """The versions, obligation versions and schedule lines of a run's population."""

    versions: Mapping[UUID, tuple[_Version, ...]]  # group → version order
    obligations: Mapping[UUID, tuple[_Ob, ...]]  # version → obligations of the run's entities
    # contract → the versions it is read from, in order (module docstring "The versions of a
    # contract"); the effective dates are carried forward along the chain
    chains: Mapping[UUID, tuple[_Version, ...]] = field(default_factory=dict)
    # (version, date) → obligation-version row → the obligation at that date (``measure``)
    cuts: dict[tuple[UUID, date], Mapping[UUID, to_date.ObligationAt]] = field(default_factory=dict)

    classify_added_obligations: bool = field(default=True, kw_only=True)
    classify_cancelled_changes: bool = field(default=True, kw_only=True)
    same_day_cancelled_changes: bool = field(default=True, kw_only=True)
    classify_cancelled_chains: bool = field(default=True, kw_only=True)
    classify_cancelled_usage: bool = field(default=True, kw_only=True)
    classify_batch_cancelled_usage: bool = field(default=True, kw_only=True)
    classify_cancelled_usage_chains: bool = field(default=True, kw_only=True)
    classify_usage_reentry: bool = field(default=True, kw_only=True)
    classify_batch_usage_reentry: bool = field(default=True, kw_only=True)
    classify_same_day_entry_cancellation: bool = field(default=True, kw_only=True)
    classify_separate_cancellations: bool = field(default=True, kw_only=True)
    classify_cancellation_cross_changes: bool = field(default=True, kw_only=True)
    classify_continuing_cancellations: bool = field(default=True, kw_only=True)
    classify_mixed_continuing_changes: bool = field(default=True, kw_only=True)
    classify_same_day_entry_chains: bool = field(default=True, kw_only=True)
    classify_pretermination_versions: bool = field(default=True, kw_only=True)
    classify_same_day_entry_modifications: bool = field(default=True, kw_only=True)
    classify_same_day_entry_estimates: bool = field(default=True, kw_only=True)
    classify_same_day_entry_usage: bool = field(default=True, kw_only=True)
    classify_eligibility_changes: bool = field(default=True, kw_only=True)
    classify_mixed_eligibility: bool = field(default=True, kw_only=True)
    inception_estimate_events: set[tuple[UUID, str]] = field(default_factory=set, kw_only=True)
    quotas: dict[UUID, Mapping[str, tuple[rpo_quotas.Point, ...]]] = field(default_factory=dict)
    boundaries: dict[UUID, Mapping[str, tuple[rpo_boundary_changes.Change, ...]]] = field(
        default_factory=dict
    )
    original_ends: dict[UUID, Mapping[str, date]] = field(default_factory=dict)

    estimate_allocations: dict[UUID, Mapping[str, Decimal]] = field(default_factory=dict)
    estimate_event_allocations: dict[tuple[UUID, str], Mapping[str, Decimal]] = field(
        default_factory=dict
    )

    def version_at(self, contract_id: UUID, day: date) -> _Version | None:
        """The version a contract is read from at ``day``: the last one of its chain effective
        on or before ``day``."""
        found = None
        for version in self.chains.get(contract_id, ()):
            if version.effective <= day:
                found = version
        return found

    def at(self, ob: _Ob, day: date) -> to_date.ObligationAt:
        """The obligation of a version at ``day``; a run measures the dates it states first."""
        point = self.cuts[ob.version_id, day][ob.row_id]
        terminal = self.cancellation(ob)
        if ob.cancelled and terminal is not None and day < terminal.day:
            status = (
                "SATISFIED"
                if point.progress_ratio == 1
                else (
                    "UNSATISFIED"
                    if point.revenue == 0 and point.progress_ratio == 0
                    else "PARTIALLY_SATISFIED"
                )
            )
            return dataclasses.replace(point, satisfaction_status=status)
        return point

    def cancellation(self, ob: _Ob) -> rpo_boundary_changes.Change | None:
        subject = obligation_subject_key(ob.external_id, ob.obligation_key)
        return rpo_boundary_changes.cancellation(
            self.boundaries.get(ob.version_id, {}).get(subject, ())
        )

    def visible(self, ob: _Ob, day: date) -> _Ob | None:
        if not ob.cancelled:
            return ob
        terminal = self.cancellation(ob)
        if terminal is None or day >= terminal.day:
            return None
        return dataclasses.replace(ob, end_date=terminal.prior_end)

    def durations(self, version: _Version) -> dict[UUID, date]:
        """Original inception-segment endpoints from verified retained computations."""
        original = self.original_ends.get(version.id, {})
        return {
            ob.contract_id: original[ob.external_id]
            for ob in self.obligations.get(version.id, ())
            if ob.external_id in original
        }


def load(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    cutoff: datetime,
    params: ReportParams | None = None,
) -> Store:
    """The version history, obligations and schedule lines of ``book_code`` recorded by ``cutoff``.
    With ``params`` (S15-R-24): under a bound run only the bound version ids and the bound
    customer-segment / product-family labels; for a live build the consumed versions and labels
    are recorded into ``params.sources``."""
    # Keep each computation and its original dated targets. Administrative holds
    # affect recognition evidence, but their review date is not the business date
    # of a collectibility reassessment carried by the same computation.
    hold_dates_key = "rpo_operational_hold_dates_v1"
    business_dates = (
        params is None or params.binding is None or hold_dates_key in params.binding.evidence
    )
    if business_dates and params is not None and params.sources is not None:
        params.sources.record_evidence(hold_dates_key, True)
    version_where = (
        []
        if params is None
        else tie_outs.bound_version_where(params, contract_version.c.id, book_code)
    )
    rows = [
        dict(row)
        for row in session.execute(
            select(
                contract_version.c.id,
                contract_version.c.combination_group_id,
                contract_version.c.version_no,
                contract_version.c.status_in_book,
                contract_version.c.cause_event_ids,
                contract_version.c.known_at,
            )
            .where(
                contract_version.c.book_code == book_code,
                contract_version.c.known_at <= cutoff,
                *version_where,
            )
            .order_by(contract_version.c.combination_group_id, contract_version.c.version_no)
        ).mappings()
    ]
    if params is not None:
        tie_outs.record_consumed_versions(params, book_code, (UUID(str(row["id"])) for row in rows))
    event_ids = sorted(
        {UUID(str(item)) for row in rows for item in row["cause_event_ids"] or ()}, key=str
    )
    events: dict[UUID, tuple[str, date]] = {}
    estimate_keys: dict[UUID, str] = {}
    estimate_order: dict[UUID, int] = {}
    boundary_keys: dict[UUID, str] = {}
    cancellation_keys: dict[UUID, str] = {}
    entry_sequences: dict[UUID, int] = {}
    eligibility_exits: dict[UUID, tuple[UUID, date]] = {}
    status_events: dict[str, tuple[UUID, str, date, int]] = {}
    event_keys: dict[UUID, str] = {}
    entered: dict[UUID, tuple[UUID, date]] = {}  # entry event → (its contract, its date)
    if event_ids:
        for found in session.execute(
            select(
                contract_event.c.id,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.contract_id,
                contract_event.c.stream_version,
                contract_event.c.record_seq,
                contract.c.external_id,
                contract_event.c.payload["book"].as_string().label("admitted_book"),
                contract_event.c.payload["is_probable"].as_boolean().label("is_probable"),
            )
            .join(contract, contract.c.id == contract_event.c.contract_id)
            .where(contract_event.c.id.in_(event_ids))
        ).mappings():
            kind = str(getattr(found["event_type"], "value", found["event_type"]))
            events[UUID(str(found["id"]))] = (kind, found["effective_date"])
            natural_key = (
                f"{contract_subject_key(str(found['external_id']))}/"
                f"EV-{int(found['stream_version']):06d}"
            )
            event_keys[UUID(str(found["id"]))] = natural_key
            status_events[natural_key] = (
                UUID(str(found["contract_id"])),
                kind,
                found["effective_date"],
                int(found["record_seq"]),
            )
            if (
                kind == "COLLECTIBILITY_ASSESSED"
                and found["admitted_book"] == book_code
                and found["is_probable"] is False
            ):
                eligibility_exits[UUID(str(found["id"]))] = (
                    UUID(str(found["contract_id"])),
                    found["effective_date"],
                )
            if kind == "ESTIMATE_CHANGED":
                estimate_order[UUID(str(found["id"]))] = int(found["record_seq"])
                estimate_keys[UUID(str(found["id"]))] = (
                    f"{contract_subject_key(str(found['external_id']))}/"
                    f"EV-{int(found['stream_version']):06d}"
                )
            if CAUSE_LINES.get(kind) == "MODIFICATIONS":
                boundary_keys[UUID(str(found["id"]))] = (
                    f"{contract_subject_key(str(found['external_id']))}/"
                    f"EV-{int(found['stream_version']):06d}"
                )
            if CAUSE_LINES.get(kind) == "CANCELLATIONS":
                cancellation_keys[UUID(str(found["id"]))] = (
                    f"{contract_subject_key(str(found['external_id']))}/"
                    f"EV-{int(found['stream_version']):06d}"
                )
            if kind in ENTRY_EVENTS and (
                kind != CRITERIA_MET or found["admitted_book"] == book_code
            ):
                entry_sequences[UUID(str(found["id"]))] = int(found["record_seq"])
                entered[UUID(str(found["id"]))] = (
                    UUID(str(found["contract_id"])),
                    found["effective_date"],
                )
    versions: dict[UUID, list[_Version]] = {}
    for row in rows:
        group_id = UUID(str(row["combination_group_id"]))
        causes = [
            events[UUID(str(item))]
            for item in row["cause_event_ids"] or ()
            if UUID(str(item)) in events
            and not (
                business_dates and events[UUID(str(item))][0] in {"HOLD_APPLIED", "HOLD_RELEASED"}
            )
        ]
        previous = versions.get(group_id, [])
        effective = max(
            (day for _, day in causes), default=previous[-1].effective if previous else date.min
        )
        if previous:
            effective = max(effective, previous[-1].effective)
        entries: dict[UUID, date] = {}
        orders: dict[UUID, tuple[date, int]] = {}
        for item in row["cause_event_ids"] or ():
            found_entry = entered.get(UUID(str(item)))
            if found_entry is not None:
                contract_id, day = found_entry
                entries[contract_id] = min(entries.get(contract_id, day), day)
                ordered = (day, entry_sequences[UUID(str(item))])
                orders[contract_id] = min(orders.get(contract_id, ordered), ordered)
        versions.setdefault(group_id, []).append(
            _Version(
                id=UUID(str(row["id"])),
                group_id=group_id,
                version_no=int(row["version_no"]),
                included=str(row["status_in_book"]) in tie_outs.INCLUDED_STATUSES,
                effective=effective,
                causes=frozenset(kind for kind, _ in causes),
                known_at=row["known_at"],
                entries=tuple(sorted(entries.items(), key=lambda pair: str(pair[0]))),
                entry_order=tuple(
                    (cid, value[1])
                    for cid, value in sorted(orders.items(), key=lambda pair: str(pair[0]))
                ),
                cause_events=frozenset(
                    event_keys[UUID(str(item))]
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in event_keys
                ),
                eligibility_exits=tuple(
                    eligibility_exits[UUID(str(item))]
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in eligibility_exits
                ),
                estimate_events=frozenset(
                    estimate_keys[UUID(str(item))]
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in estimate_keys
                ),
                modification_events=frozenset(
                    boundary_keys[UUID(str(item))]
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in boundary_keys
                ),
                cancellation_events=frozenset(
                    cancellation_keys[UUID(str(item))]
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in cancellation_keys
                ),
                estimate_order=tuple(
                    (estimate_keys[UUID(str(item))], estimate_order[UUID(str(item))])
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in estimate_keys
                ),
                estimate_dates=tuple(
                    (estimate_keys[UUID(str(item))], events[UUID(str(item))][1])
                    for item in row["cause_event_ids"] or ()
                    if UUID(str(item)) in estimate_keys
                ),
            )
        )
    version_ids = [UUID(str(row["id"])) for row in rows]
    obligations: dict[UUID, list[_Ob]] = {}
    by_row: dict[tuple[UUID, UUID], _Ob] = {}
    if version_ids and entity_ids:
        statement = (
            select(
                obligation_version.c.id,
                obligation_version.c.contract_version_id,
                obligation_version.c.obligation_id,
                obligation_version.c.contract_id,
                obligation_version.c.obligation_key,
                obligation_version.c.recognition_method,
                obligation_version.c.end_date,
                obligation_version.c.allocated_amount,
                obligation_version.c.satisfaction_status,
                obligation_version.c.txn_currency,
                obligation_version.c.contracting_entity_id,
                contract.c.external_id,
                contract.c.inception_date,
                customer.c.id.label("customer_id"),
                customer.c.name.label("customer_name"),
                customer.c.segment.label("customer_segment"),
                product.c.id.label("product_id"),
                product.c.name.label("product_name"),
                product.c.product_family,
                legal_entity.c.code.label("entity_code"),
            )
            .select_from(
                obligation_version.join(
                    contract,
                    and_(
                        contract.c.tenant_id == obligation_version.c.tenant_id,
                        contract.c.id == obligation_version.c.contract_id,
                    ),
                )
                .outerjoin(
                    customer,
                    and_(
                        customer.c.tenant_id == contract.c.tenant_id,
                        customer.c.id == contract.c.customer_id,
                    ),
                )
                .join(
                    product,
                    and_(
                        product.c.tenant_id == obligation_version.c.tenant_id,
                        product.c.id == obligation_version.c.product_id,
                    ),
                )
                .join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == obligation_version.c.tenant_id,
                        legal_entity.c.id == obligation_version.c.contracting_entity_id,
                    ),
                )
            )
            .where(
                obligation_version.c.contract_version_id.in_(version_ids),
                obligation_version.c.contracting_entity_id.in_(list(entity_ids)),
            )
            .order_by(contract.c.external_id, obligation_version.c.obligation_key)
        )
        for found in session.execute(statement).mappings():
            ob = _Ob(
                row_id=UUID(str(found["id"])),
                version_id=UUID(str(found["contract_version_id"])),
                obligation_id=UUID(str(found["obligation_id"])),
                contract_id=UUID(str(found["contract_id"])),
                external_id=str(found["external_id"]),
                obligation_key=str(found["obligation_key"]),
                product_name=str(
                    _label(params, "product_name", found["product_id"], found["product_name"])
                ),
                product_family=_label(
                    params, "product_family", found["product_id"], found["product_family"]
                ),
                customer_name=_label(
                    params, "customer_name", found["customer_id"], found["customer_name"]
                ),
                customer_segment=_label(
                    params, "customer_segment", found["customer_id"], found["customer_segment"]
                ),
                entity_id=UUID(str(found["contracting_entity_id"])),
                entity_code=_entity_code(
                    params, UUID(str(found["contracting_entity_id"])), str(found["entity_code"])
                ),
                currency=str(found["txn_currency"]).strip(),
                recognition_method=str(found["recognition_method"]),
                end_date=found["end_date"],
                inception=found["inception_date"],
                allocated=Decimal(found["allocated_amount"]),
                cancelled=str(found["satisfaction_status"]) == CANCELLED,
            )
            obligations.setdefault(ob.version_id, []).append(ob)
            by_row[(ob.version_id, ob.obligation_id)] = ob
    if by_row:
        lines = (
            select(
                schedule_line.c.id,
                schedule_line.c.contract_version_id,
                schedule_line.c.subject_id,
                schedule_line.c.period_end_date,
                schedule_line.c.amount,
                schedule_line.c.trace_node_id,
            )
            .select_from(
                schedule_line.join(
                    schedule,
                    and_(
                        schedule.c.tenant_id == schedule_line.c.tenant_id,
                        schedule.c.id == schedule_line.c.schedule_id,
                    ),
                )
            )
            .where(
                schedule_line.c.contract_version_id.in_(
                    sorted({key[0] for key in by_row}, key=str)
                ),
                schedule_line.c.subject_type == "obligation",
                schedule.c.schedule_kind == tie_outs.REVENUE,
            )
        )
        for found in session.execute(
            lines.order_by(schedule_line.c.period_end_date, schedule_line.c.id)
        ).mappings():
            ob_found = by_row.get(
                (UUID(str(found["contract_version_id"])), UUID(str(found["subject_id"])))
            )
            if ob_found is not None:
                ob_found.line_nodes[UUID(str(found["id"]))] = str(found["trace_node_id"])
                ob_found.lines.append(
                    (UUID(str(found["id"])), found["period_end_date"], Decimal(found["amount"]))
                )
    chains = chains_of(versions, obligations, _memberships(session, obligations, cutoff))
    timeline_key = "rpo_initial_eligibility_timeline_v1"
    timelines = params is None or params.binding is None or timeline_key in params.binding.evidence
    mixed_key = "rpo_initial_monetary_timeline_v1"
    mixed_timeline = (
        params is None or params.binding is None or mixed_key in params.binding.evidence
    )
    if timelines:
        if mixed_timeline and params is not None and params.sources is not None:
            params.sources.record_evidence(mixed_key, True)
        if params is not None and params.sources is not None:
            params.sources.record_evidence(timeline_key, True)
        retained_traces: dict[UUID, Trace | None] = {}
        for cid, chain in chains.items():
            first = chain[0]
            if not {"CONTRACT_CRITERIA_MET", "COLLECTIBILITY_ASSESSED"} <= first.causes:
                continue
            if first.id not in retained_traces:
                retained_traces[first.id] = trace_store.load_trace(session, first.id)
            trace = retained_traces[first.id]
            if trace is None:
                continue
            expanded = initial_eligibility_timeline(
                first, cid, trace, status_events, mixed=mixed_timeline
            )
            if expanded is not None:
                chains[cid] = (*expanded, *chain[1:])
    return Store(
        versions={key: tuple(value) for key, value in versions.items()},
        obligations={key: tuple(value) for key, value in obligations.items()},
        chains=chains,
    )


def initial_eligibility_timeline(
    version: _Version,
    contract_id: UUID,
    trace: Trace,
    events: Mapping[str, tuple[UUID, str, date, int]],
    *,
    mixed: bool = False,
) -> tuple[_Version, ...] | None:
    """Read status slices of one original computation without inventing new computations."""
    money_kinds = {"CONTRACT_AMENDED", "ESTIMATE_CHANGED"}
    if version.version_no != 1 or not version.causes <= (
        {
            "CONTRACT_BOOKED",
            "CONTRACT_ACTIVATED",
            "CONTRACT_CRITERIA_MET",
            "COLLECTIBILITY_ASSESSED",
            "SIGNIFICANT_CHANGE_FLAGGED",
            "MEMO_ADDED",
        }
        | (money_kinds if mixed else set())
    ):
        return None
    points: list[tuple[date, int, str, str]] = []
    seen: set[str] = set()
    for node in trace.nodes:
        if not node.measure.startswith("status@"):
            continue
        key = node.measure.removeprefix("status@")
        event = events.get(key)
        if event is None:
            return None
        cid, kind, day, sequence = event
        if cid != contract_id:
            continue
        status = node.params.get("status")
        if (
            key in seen
            or node.formula_id != "step1.status.v1"
            or status not in {"DRAFT", "NOT_A_CONTRACT", "ACTIVE"}
            or node.value != str(STATUS_ORDINAL[status])
            or len(node.inputs) != 1
            or not isinstance(node.inputs[0], SourceRef)
            or node.inputs[0].ref_type != "contract_event"
            or node.inputs[0].ref_id != key
        ):
            return None
        seen.add(key)
        points.append((day, sequence, key, status))
    points.sort()
    if not points or (points[-1][3] == "ACTIVE") != version.included:
        return None
    result: list[_Version] = []
    included = False
    for day, sequence, key, status in points:
        now = status == "ACTIVE"
        if now == included:
            continue
        kind = events[key][1]
        if (now and kind not in ENTRY_EVENTS) or (not now and kind != "COLLECTIBILITY_ASSESSED"):
            return None
        result.append(
            dataclasses.replace(
                version,
                effective=day,
                included=now,
                causes=frozenset({kind}),
                entries=((contract_id, day),) if now else (),
                entry_order=((contract_id, sequence),) if now else (),
                eligibility_exits=() if now else ((contract_id, day),),
            )
        )
        included = now
    # One admission already has the ordinary first-entry behavior.
    if len(result) < 2:
        return None
    if not version.causes & money_kinds:
        return tuple(result)
    return _monetary_timeline(version, contract_id, trace, events, result)


def _monetary_timeline(
    version: _Version,
    contract_id: UUID,
    trace: Trace,
    events: Mapping[str, tuple[UUID, str, date, int]],
    statuses: Sequence[_Version],
) -> tuple[_Version, ...] | None:
    """Keep each monetary cause on its original date, using event-specific retained shares."""
    kinds = {"CONTRACT_AMENDED", "ESTIMATE_CHANGED"}
    if not version.cause_events or not version.cause_events <= events.keys():
        return None
    monetary = {
        key: events[key]
        for key in version.cause_events
        if events[key][0] == contract_id and events[key][1] in kinds
    }
    if {event[1] for event in monetary.values()} != version.causes & kinds:
        return None
    dated = {status.effective: status for status in statuses}
    if len(dated) != len(statuses):
        return None
    # A date-only fixed balance cannot separate a change after a same-day exit/entry.
    # Inception estimate pins belong to the initial allocation and are not later deltas.
    for key, (_, kind, day, sequence) in monetary.items():
        if day not in dated:
            continue
        status = dated[day]
        transitions = [
            events[cause]
            for cause in version.cause_events
            if (event := events[cause])[0] == contract_id
            and event[2] == day
            and event[1] in status.causes
        ]
        if len(transitions) != 1:
            return None
        if sequence > transitions[0][3] and not (
            day == statuses[0].effective
            and kind == "ESTIMATE_CHANGED"
            and rpo_estimate_changes.at_inception(trace, key)
        ):
            return None
    days = sorted(set(dated) | {event[2] for event in monetary.values()})
    result: list[_Version] = []
    for day in days:
        if day < statuses[0].effective:
            continue
        state = next(status for status in reversed(statuses) if status.effective <= day)
        transition = dated.get(day)
        own = {key: event for key, event in monetary.items() if event[2] == day}
        estimates = frozenset(key for key, event in own.items() if event[1] == "ESTIMATE_CHANGED")
        amendments = frozenset(key for key, event in own.items() if event[1] == "CONTRACT_AMENDED")
        result.append(
            dataclasses.replace(
                state,
                effective=day,
                dated_slice=True,
                causes=frozenset(event[1] for event in own.values())
                | (transition.causes if transition else frozenset()),
                entries=transition.entries if transition else (),
                entry_order=transition.entry_order if transition else (),
                eligibility_exits=transition.eligibility_exits if transition else (),
                estimate_events=estimates,
                estimate_dates=tuple((key, day) for key in sorted(estimates)),
                estimate_order=tuple((key, own[key][3]) for key in sorted(estimates)),
                modification_events=amendments,
                cause_events=frozenset(own),
            )
        )
    return tuple(result)


def _estimate_changes(store: Store, version: _Version) -> Mapping[str, Decimal] | None:
    if not version.dated_slice:
        return store.estimate_allocations.get(version.id)
    result: dict[str, Decimal] = {}
    for event in version.estimate_events:
        shares = store.estimate_event_allocations.get((version.id, event))
        if shares is None:
            return None
        for subject, amount in shares.items():
            result[subject] = result.get(subject, ZERO) + amount
    return result


@dataclass(frozen=True, slots=True)
class Membership:
    """A T-CON-04 row as a run reads it: the contract is a member of the group from ``valid_from``
    until ``valid_to`` in record time (None: still a member at the run's cutoff)."""

    contract_id: UUID
    group_id: UUID
    valid_from: datetime
    valid_to: datetime | None


def _memberships(
    session: Session, obligations: Mapping[UUID, Sequence[_Ob]], cutoff: datetime
) -> list[Membership]:
    """The memberships, recorded by ``cutoff``, of the contracts the run holds. A membership that
    ended after the cutoff is still open for the run. T-CON-04 is RLS-T: the read does not depend
    on the reader's entities."""
    contract_ids = sorted(
        {ob.contract_id for items in obligations.values() for ob in items}, key=str
    )
    if not contract_ids:
        return []
    member = combination_group_member
    found: list[Membership] = []
    for row in session.execute(
        select(
            member.c.contract_id,
            member.c.combination_group_id,
            member.c.valid_from_known_at,
            member.c.valid_to_known_at,
        ).where(member.c.contract_id.in_(contract_ids), member.c.valid_from_known_at <= cutoff)
    ).mappings():
        ended = row["valid_to_known_at"]
        found.append(
            Membership(
                contract_id=UUID(str(row["contract_id"])),
                group_id=UUID(str(row["combination_group_id"])),
                valid_from=row["valid_from_known_at"],
                valid_to=None if ended is None or ended > cutoff else ended,
            )
        )
    return found


def chains_of(
    versions: Mapping[UUID, Sequence[_Version]],
    obligations: Mapping[UUID, Sequence[_Ob]],
    memberships: Iterable[Membership],
) -> dict[UUID, tuple[_Version, ...]]:
    """Per contract, the versions it is read from (module docstring "The versions of a contract"):
    for each of its memberships in the order they began, the group's versions that hold an
    obligation of the contract and were recorded while it was a member; the effective dates are
    carried forward along the chain, as they are within a group. A contract none of whose versions
    falls in a membership — rows written outside the product's commands — is read from every
    version that holds it, in the order they were recorded.

    The first included version of a chain counts from the contract's entry (module docstring
    "Entry at activation"): the effective date of its ``ENTRY_EVENTS`` cause of that version,
    where the version has one and it is earlier than the latest of the version's causes — and
    never earlier than the version before it in the chain. Pure."""
    holding: dict[UUID, set[UUID]] = {}
    for version_id, items in obligations.items():
        for ob in items:
            holding.setdefault(ob.contract_id, set()).add(version_id)
    spans: dict[UUID, list[Membership]] = {}
    for membership in memberships:
        spans.setdefault(membership.contract_id, []).append(membership)
    chains: dict[UUID, tuple[_Version, ...]] = {}
    for contract_id in sorted(holding, key=str):
        held = holding[contract_id]
        chain = [
            version
            for span in sorted(spans.get(contract_id, ()), key=lambda item: item.valid_from)
            for version in versions.get(span.group_id, ())
            if version.id in held and _recorded_within(version, span)
        ]
        if not chain:
            chain = sorted(
                (
                    version
                    for group_versions in versions.values()
                    for version in group_versions
                    if version.id in held
                ),
                key=lambda item: (
                    item.known_at is not None,
                    item.known_at,
                    str(item.group_id),
                    item.version_no,
                ),
            )
        carried: list[_Version] = []
        entered = False
        for version in chain:
            effective = version.effective
            if version.included and not entered:
                entered = True
                effective = min(effective, dict(version.entries).get(contract_id, effective))
            if carried:
                effective = max(effective, carried[-1].effective)
            if effective == version.effective:
                carried.append(version)
            else:
                carried.append(dataclasses.replace(version, effective=effective))
        chains[contract_id] = tuple(carried)
    return chains


def _recorded_within(version: _Version, span: Membership) -> bool:
    if version.known_at is None:
        return True
    return span.valid_from <= version.known_at and (
        span.valid_to is None or version.known_at < span.valid_to
    )


def _entity_code(params: ReportParams | None, entity_id: UUID, live: str) -> str:
    """The contracting entity's code as the run consumed it (frps3c-1 `labels.entity_code`): the
    retained code under a binding, the live code recorded; the live code when no params (a read
    outside a report build)."""
    return live if params is None else tie_outs.entity_code_for(params, entity_id, live)


def _label(params: ReportParams | None, kind: str, key: object, live: object) -> str | None:
    """A grouping label as the run consumed it (S15-R-24): bound under a bound run, else live,
    recorded for the binding."""
    value = None if live is None else str(live)
    if params is None:
        return value
    return tie_outs.label_for(params, kind, key, value)


def applied_expedients(
    session: Session, entities: Iterable[EntityRef], *, book_code: str, known_at: datetime
) -> dict[UUID, frozenset[str]]:
    """The POL ids set to ``APPLY`` for each entity at ``known_at``."""
    book = BookCode(book_code)
    return {
        entity.id: frozenset(
            pol
            for pol, code, _, _ in EXPEDIENTS
            if resolve(session, code, book_code=book, entity_id=entity.id, known_at=known_at).value
            == APPLY
        )
        for entity in entities
    }


def _exemption(ob: _Ob, applied: frozenset[str], ends: Mapping[UUID, date]) -> str | None:
    if "POL-197" in applied:
        if ob.contract_id not in ends:
            raise Problem("validation-failed", "The original RPO contract term is unavailable.")
        if ends[ob.contract_id] < add_months(ob.inception, 12):
            return "POL-197"
    if "POL-198" in applied and ob.recognition_method == RIGHT_TO_INVOICE:
        return "POL-198"
    return None


def measure(
    session: Session,
    store: Store,
    days: Mapping[UUID, Collection[date]],
    *,
    applied: Mapping[UUID, frozenset[str]] | None = None,
    uow: UnitOfWork | None = None,
    book_code: str | None = None,
    permission: str = "report.run",
    params: ReportParams | None = None,
) -> None:
    """Read the obligations a run states at the dates it states them (module docstring "RPO of
    an obligation at d"): for every contract the version it is read from at each date of the run,
    measured at every one of those dates — the rollforward takes the revenue of the closing
    version at both ends of its range. ``days`` are the dates per entity."""
    every = sorted({day for found in days.values() for day in found})
    wanted: dict[UUID, set[date]] = {}
    for contract_id, chain in store.chains.items():
        moved = [
            candidate
            for candidate in chain
            if every and every[0] < candidate.effective <= every[-1]
        ]
        measured_days = {*every, *(candidate.effective for candidate in moved)}
        for candidate in moved:
            wanted.setdefault(candidate.id, set()).update(measured_days)
        for day in measured_days:
            version = store.version_at(contract_id, day)
            if version is not None:
                wanted.setdefault(version.id, set()).update(measured_days)
    store.cuts.update(cuts.obligations_at(session, wanted))
    for chain in store.versions.values():
        for version in chain:
            if version.id not in wanted or not (
                version.entries
                or (store.classify_mixed_eligibility and version.eligibility_exits)
                or any(
                    CAUSE_LINES.get(kind) in {"MODIFICATIONS", "CANCELLATIONS"}
                    for kind in version.causes
                )
            ):
                continue
            trace = trace_store.load_trace(session, version.id)
            if trace is not None:
                store.boundaries[version.id] = rpo_boundary_changes.history(trace)
                changes = rpo_estimate_changes.allocations(trace, version.estimate_events)
                if changes is not None:
                    store.estimate_allocations[version.id] = changes
                if version.entries:
                    for event in version.estimate_events:
                        if rpo_estimate_changes.at_inception(trace, event):
                            store.inception_estimate_events.add((version.id, event))
                        shares = rpo_estimate_changes.allocations(trace, frozenset({event}))
                        if shares is not None:
                            store.estimate_event_allocations[version.id, event] = shares
    if applied is not None and any("POL-197" in values for values in applied.values()):
        if book_code is None:
            raise Problem("validation-failed", "Original RPO terms require retained source access.")
        store.original_ends.update(
            rpo_duration.read(
                uow, tuple(wanted), book_code=book_code, permission=permission, params=params
            )
        )
    if applied is not None and any("POL-200" in values for values in applied.values()):
        targets = rpo_quotas.targeted_versions(session, tuple(store.chains))
        for version_id in wanted:
            trace = trace_store.load_trace(session, version_id)
            if trace is None:
                raise Problem(
                    "validation-failed", "RPO exemptions require the retained allocation trace."
                )
            store.quotas[version_id] = rpo_quotas.history(
                trace,
                inception={
                    ob.external_id: ob.inception for ob in store.obligations.get(version_id, ())
                },
                targeted=targets,
            )


def _partial_exclusion(
    store: Store, ob: _Ob, day: date, total: Decimal, applied: frozenset[str]
) -> Decimal:
    at = store.at(ob, day)
    if "POL-200" not in applied or at.satisfaction_status != "UNSATISFIED" or at.revenue != 0:
        return ZERO
    if ob.version_id not in store.quotas:
        raise Problem("validation-failed", "RPO targeted-VC quota evidence has not been loaded.")
    points = store.quotas[ob.version_id].get(
        obligation_subject_key(ob.external_id, ob.obligation_key), ()
    )
    return min(max(total, ZERO), rpo_quotas.cap(points, day))


def _net_figures(
    total: Decimal,
    placed: tuple[Decimal, ...],
    contributors: tuple[tuple[str, UUID, Decimal, int, bool], ...],
    *,
    excluded: Decimal,
    currency: str,
) -> tuple[Decimal, tuple[Decimal, ...], Decimal, tuple[tuple[str, UUID, Decimal, int, bool], ...]]:
    scale = 10 ** tie_outs.minor_unit(currency)
    net = total - excluded
    bands = rpo_bands(int(net * scale), [int(amount * scale) for amount in placed])
    reduced: list[tuple[str, UUID, Decimal, int, bool]] = []
    for index, amount in enumerate(bands):
        held = [item for item in contributors if item[3] == index]
        if not held:
            if amount:
                raise Problem("validation-failed", "RPO net band has no disclosure contributors.")
            continue
        shares = rpo_bands(amount, [int(item[2] * scale) for item in held])
        reduced.extend(
            (item[0], item[1], Decimal(share) / scale, index, item[4])
            for item, share in zip(held, shares, strict=True)
        )
    return (
        net,
        tuple(Decimal(value) / scale for value in bands),
        sum((item[2] for item in reduced if item[4]), ZERO),
        tuple(reduced),
    )


def rpo_of(
    ob: _Ob, day: date, bands: Sequence[int], at: to_date.ObligationAt
) -> tuple[Decimal, tuple[Decimal, ...], Decimal, tuple[tuple[str, UUID, Decimal, int, bool], ...]]:
    """(total, per band, current, contributors) of one obligation at ``day``: its remainder at
    that date (``at``, the obligation read at the cut of ``day``) — the scheduled part by the
    periods of the version's later schedule lines, the awaiting-trigger part by the obligation's
    end date."""
    bounds = [add_months(day, int(item)) for item in sorted(bands)]
    current_bound = add_months(day, CURRENT_MONTHS)
    placed = [ZERO] * (len(bounds) + 1)
    total = current = ZERO
    contributors: list[tuple[str, UUID, Decimal, int, bool]] = []
    projected = cuts.projected_after(at, day, contract=ob.external_id, obligation=ob.obligation_key)
    if projected is None:
        scheduled = [
            ("schedule_line", line_id, end, amount)
            for line_id, end, amount in cuts.scheduled_after(
                ob.lines,
                at,
                day,
                contract=ob.external_id,
                obligation=ob.obligation_key,
                sources=ob.line_nodes,
            )
        ]
    else:
        scheduled = [
            (f"{to_date.PERIOD_SCHEDULE}@{at.fixed_schedule_cut}@{key}", ob.row_id, end, amount)
            for key, end, amount in projected
        ]
    for kind, object_id, end, amount in scheduled:
        index = band_index(end, bounds)
        placed[index] += amount
        total += amount
        is_current = end <= current_bound
        if is_current:
            current += amount
        contributors.append((kind, object_id, amount, index, is_current))
    if at.awaiting:
        index = 0 if ob.end_date is None else band_index(ob.end_date, bounds)
        is_current = ob.end_date is None or ob.end_date <= current_bound
        placed[index] += at.awaiting
        total += at.awaiting
        if is_current:
            current += at.awaiting
        contributors.append(("obligation_version", ob.row_id, at.awaiting, index, is_current))
    return total, tuple(placed), current, tuple(contributors)


def rows_at(
    store: Store,
    *,
    as_of: Mapping[UUID, date],
    bands: Sequence[int],
    applied: Mapping[UUID, frozenset[str]],
) -> tuple[ObligationRpo, ...]:
    """Every obligation with RPO at its entity's as-of date, by the version at that date."""
    found: list[ObligationRpo] = []
    for contract_id in store.chains:
        for day in sorted(set(as_of.values())):
            version = store.version_at(contract_id, day)
            if version is None or not version.included:
                continue
            ends = store.durations(version)
            for ob in store.obligations.get(version.id, ()):
                if ob.contract_id != contract_id or as_of.get(ob.entity_id) != day:
                    continue
                visible = store.visible(ob, day)
                if visible is None:
                    continue
                ob = visible
                total, placed, current, contributors = rpo_of(ob, day, bands, store.at(ob, day))
                if total == 0:
                    continue
                remaining = (
                    0 if ob.end_date is None else max(month_ends_between(day, ob.end_date), 0)
                )
                exemption = _exemption(ob, applied.get(ob.entity_id, frozenset()), ends)
                excluded = (
                    ZERO
                    if exemption is not None
                    else _partial_exclusion(
                        store, ob, day, total, applied.get(ob.entity_id, frozenset())
                    )
                )
                if excluded:
                    total, placed, current, contributors = _net_figures(
                        total, placed, contributors, excluded=excluded, currency=ob.currency
                    )
                found.append(
                    ObligationRpo(
                        ob=ob,
                        as_of=day,
                        total=total,
                        placed=placed,
                        current=current,
                        contributors=contributors,
                        exemption=exemption,
                        remaining_months=remaining,
                        excluded=excluded,
                        partial_exemption="POL-200" if excluded else None,
                    )
                )
    return tuple(sorted(found, key=lambda item: (item.ob.external_id, item.ob.obligation_key)))


@dataclass(frozen=True, slots=True)
class ContractLines:
    external_id: str
    customer_name: str | None
    entity_code: str
    currency: str
    lines: Mapping[str, Decimal]
    exemption_changes: tuple[Mapping[str, Any], ...] = ()


def rollforward_lines(
    store: Store,
    *,
    ranges: Mapping[UUID, tuple[date, date]],
    applied: Mapping[UUID, frozenset[str]],
) -> tuple[ContractLines, ...]:
    """S15-R-12 lines per contract over each entity's (day before the range, range end)."""
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for contract_id, versions in store.chains.items():
        for entity_id, (before, end) in ranges.items():
            opening_version = store.version_at(contract_id, before)
            closing_version = store.version_at(contract_id, end)
            moved = [item for item in versions if before < item.effective <= end]
            chain = [opening_version, *moved] if opening_version is not None else list(moved)
            if not chain:
                continue
            obligation_ids = {
                ob.obligation_id
                for version in chain
                for ob in store.obligations.get(version.id, ())
                if ob.entity_id == entity_id and ob.contract_id == contract_id
            }
            for obligation_id in sorted(obligation_ids, key=str):
                _obligation_lines(
                    store,
                    totals,
                    obligation_id=obligation_id,
                    opening_version=opening_version,
                    closing_version=closing_version,
                    moved=moved,
                    before=before,
                    end=end,
                    applied=applied.get(entity_id, frozenset()),
                )
    found = [
        ContractLines(
            external_id=key[0],
            customer_name=value["customer_name"],
            entity_code=value["entity_code"],
            currency=key[1],
            lines={line: value["lines"][line] for line in ROLLFORWARD_LINES},
            exemption_changes=tuple(value["exemption_changes"]),
        )
        for key, value in totals.items()
    ]
    return tuple(sorted(found, key=lambda item: (item.external_id, item.currency)))


def _in_version(
    store: Store, version: _Version | None, obligation_id: UUID, day: date | None = None
) -> _Ob | None:
    if version is None or not version.included:
        return None
    for ob in store.obligations.get(version.id, ()):
        if ob.obligation_id == obligation_id:
            return store.visible(ob, version.effective if day is None else day)
    return None


def _cancellation_boundary(
    store: Store, changes: Sequence[rpo_boundary_changes.Change], events: frozenset[str]
) -> tuple[rpo_boundary_changes.Change, Decimal] | None:
    terminal = [item for item in changes if item.event in events]
    cross = ZERO
    if len(events) > 1:
        if (
            not store.classify_separate_cancellations
            or {item.event for item in terminal} != events
            or len(terminal) != len(events)
            or not all(item.cancellation_stated for item in terminal)
        ):
            return None
        actual = rpo_boundary_changes.cancellation(tuple(terminal))
        if actual is None:
            return None
        for item in terminal:
            if item.event == actual.event or item.amount == 0:
                continue
            if (
                not store.classify_cancellation_cross_changes
                or item.day > actual.day
                or (
                    item.day == actual.day
                    and (
                        item.record_seq is None
                        or actual.record_seq is None
                        or (item.record_seq, item.event) >= (actual.record_seq, actual.event)
                    )
                )
            ):
                return None
            cross += item.amount
        terminal = [actual]
    if len(terminal) != 1 or terminal[0].before is None:
        return None
    return terminal[0], cross


def _continuing_cancellations(
    store: Store, version: _Version, subject: str, start: date, end: date
) -> Decimal | None:
    """Original termination effects while this obligation remains in disclosure."""
    if not store.classify_continuing_cancellations or not version.cancellation_events:
        return None
    changes = [
        item
        for item in store.boundaries.get(version.id, {}).get(subject, ())
        if item.event in version.cancellation_events
    ]
    if (
        len(changes) != len(version.cancellation_events)
        or {item.event for item in changes} != version.cancellation_events
        or not all(item.cancellation_stated for item in changes)
        or any(item.cancelled_on is not None for item in changes if start < item.day <= end)
    ):
        return None
    return sum((item.amount for item in changes if start < item.day <= end), ZERO)


def _continuing_changes(
    store: Store, version: _Version, subject: str, delta: Decimal, end: date
) -> tuple[Decimal, Decimal] | None:
    """Separate a retained version's competing causes using their original amounts."""
    if not store.classify_mixed_continuing_changes:
        return None
    if (
        any(CAUSE_LINES.get(kind) == "MODIFICATIONS" for kind in version.causes)
        and not version.modification_events
    ) or ("ESTIMATE_CHANGED" in version.causes and not version.estimate_events):
        return None
    cancellation = _continuing_cancellations(store, version, subject, date.min, end)
    if cancellation is None:
        return None
    history = store.boundaries.get(version.id, {})
    if version.modification_events and not rpo_boundary_changes.complete(
        history, subject, version.modification_events
    ):
        return None
    modifications = [
        item for item in history.get(subject, ()) if item.event in version.modification_events
    ]
    if any(item.day > end for item in modifications):
        return None
    estimate = ZERO
    if version.estimate_events:
        shares = _estimate_changes(store, version)
        dates = dict(version.estimate_dates)
        if shares is None or any(
            event not in dates or dates[event] > end for event in version.estimate_events
        ):
            return None
        estimate = shares.get(subject, ZERO)
    modified = sum((item.amount for item in modifications), ZERO)
    if modified + estimate + cancellation != delta:
        return None
    return modified, estimate


def _eligibility_changes(
    store: Store, version: _Version, subject: str, delta: Decimal
) -> tuple[Decimal, Decimal] | None:
    """Explain fixed changes before a retained eligibility exit from original evidence."""
    neutral = {"COLLECTIBILITY_ASSESSED", "SIGNIFICANT_CHANGE_FLAGGED", "MEMO_ADDED"}
    if version.causes <= neutral:
        return (ZERO, ZERO) if delta == ZERO else None
    if not store.classify_mixed_eligibility or not version.causes <= neutral | {
        "CONTRACT_AMENDED",
        "ESTIMATE_CHANGED",
        "USAGE_REPORTED",
    }:
        return None
    if ("CONTRACT_AMENDED" in version.causes and not version.modification_events) or (
        "ESTIMATE_CHANGED" in version.causes and not version.estimate_events
    ):
        return None
    history = store.boundaries.get(version.id, {})
    if version.modification_events and not rpo_boundary_changes.complete(
        history, subject, version.modification_events
    ):
        return None
    changes = [
        item for item in history.get(subject, ()) if item.event in version.modification_events
    ]
    if any(item.day > version.effective for item in changes):
        return None
    estimate = ZERO
    if version.estimate_events:
        dates = dict(version.estimate_dates)
        shares = _estimate_changes(store, version)
        if shares is None or any(
            event not in dates or dates[event] > version.effective
            for event in version.estimate_events
        ):
            return None
        estimate = shares.get(subject, ZERO)
    modified = sum((item.amount for item in changes), ZERO)
    return (modified, estimate) if modified + estimate == delta else None


def _cancelled_changes(
    store: Store, version: _Version, subject: str, opening: Decimal
) -> tuple[Decimal, Decimal] | None:
    if not store.classify_cancelled_changes or not version.cancellation_events:
        return None
    if (
        any(CAUSE_LINES.get(kind) == "MODIFICATIONS" for kind in version.causes)
        and not version.modification_events
    ) or ("ESTIMATE_CHANGED" in version.causes and not version.estimate_events):
        return None
    history = store.boundaries.get(version.id, {})
    changes = history.get(subject, ())
    boundary = _cancellation_boundary(store, changes, version.cancellation_events)
    if boundary is None:
        return None
    termination, cross = boundary
    if version.modification_events and not rpo_boundary_changes.complete(
        history, subject, version.modification_events
    ):
        return None
    modifications = [item for item in changes if item.event in version.modification_events]
    for item in modifications:
        if item.day > termination.day or (
            item.day == termination.day
            and (
                item.record_seq is None
                or termination.record_seq is None
                or (item.record_seq, item.event) >= (termination.record_seq, termination.event)
            )
        ):
            return None
    estimate = ZERO
    if version.estimate_events:
        shares = _estimate_changes(store, version)
        dates = dict(version.estimate_dates)
        if shares is None:
            return None
        order = dict(version.estimate_order)
        for event in version.estimate_events:
            day = dates.get(event)
            if day is None or day > termination.day:
                return None
            if day == termination.day and (
                not store.same_day_cancelled_changes
                or event not in order
                or termination.record_seq is None
                or (order[event], event) >= (termination.record_seq, termination.event)
            ):
                return None
        estimate = shares.get(subject, ZERO)
    modified = sum((item.amount for item in modifications), ZERO)
    if opening + modified + estimate + cross != termination.before:
        return None
    return modified, estimate


def _same_day_entry_modifications(
    store: Store, version: _Version, ob: _Ob
) -> frozenset[str] | None:
    """Original amendments strictly after admission and before same-day termination."""
    if not store.classify_same_day_entry_modifications or not version.modification_events:
        return None
    admission = dict(version.entry_order).get(ob.contract_id)
    terminal = store.cancellation(ob)
    if admission is None or terminal is None or terminal.record_seq is None:
        return None
    subject = obligation_subject_key(ob.external_id, ob.obligation_key)
    history = store.boundaries.get(version.id, {})
    if not rpo_boundary_changes.complete(history, subject, version.modification_events):
        return None
    changes = sorted(
        (item for item in history.get(subject, ()) if item.event in version.modification_events),
        key=lambda item: (item.record_seq or 0, item.event),
    )
    if not changes or any(
        item.day != terminal.day
        or item.record_seq is None
        or not admission < item.record_seq < terminal.record_seq
        or item.before is None
        or item.after is None
        for item in changes
    ):
        return None
    if any(left.after != right.before for left, right in zip(changes, changes[1:], strict=False)):
        return None
    if changes[-1].after != terminal.before:
        return None
    return frozenset(item.event for item in changes)


def _obligation_lines(
    store: Store,
    totals: dict[tuple[str, str], dict[str, Any]],
    *,
    obligation_id: UUID,
    opening_version: _Version | None,
    closing_version: _Version | None,
    moved: Sequence[_Version],
    before: date,
    end: date,
    applied: frozenset[str],
) -> None:
    described = None
    for version in (closing_version, *reversed(moved), opening_version):
        if version is None:
            continue
        described = next(
            (
                ob
                for ob in store.obligations.get(version.id, ())
                if ob.obligation_id == obligation_id
            ),
            None,
        )
        if described is not None:
            break
    if described is None:
        return
    same_day_entry = None
    same_day_modifications: frozenset[str] = frozenset()
    if (
        store.classify_same_day_entry_cancellation
        and opening_version is None
        and moved
        and (len(moved) == 1 or store.classify_same_day_entry_chains)
        and moved[0].included
        and {"CONTRACT_ACTIVATED", "CONTRACT_TERMINATED"} <= moved[0].causes
        and moved[0].causes
        <= (
            {"CONTRACT_BOOKED", "CONTRACT_ACTIVATED", "CONTRACT_TERMINATED", "MEMO_ADDED"}
            | ({"CONTRACT_AMENDED"} if store.classify_same_day_entry_modifications else set())
            | ({"ESTIMATE_CHANGED"} if store.classify_same_day_entry_estimates else set())
            | (
                {"USAGE_REPORTED"}
                if store.classify_same_day_entry_usage and store.classify_batch_cancelled_usage
                else set()
            )
        )
    ):
        version = moved[0]
        candidate = next(
            (
                ob
                for ob in store.obligations.get(version.id, ())
                if ob.obligation_id == obligation_id and ob.cancelled
            ),
            None,
        )
        if candidate is not None:
            terminal = store.cancellation(candidate)
            amendments = _same_day_entry_modifications(store, version, candidate)
            inception_estimates_valid = "ESTIMATE_CHANGED" not in version.causes or (
                bool(version.estimate_events)
                and all(
                    (version.id, event) in store.inception_estimate_events
                    and dict(version.estimate_dates).get(event) == version.effective
                    for event in version.estimate_events
                )
            )
            if (
                inception_estimates_valid
                and ("CONTRACT_AMENDED" not in version.causes or amendments is not None)
                and (
                    terminal is not None
                    and terminal.before is not None
                    and terminal.day == version.effective
                    and dict(version.entries).get(candidate.contract_id) == terminal.day
                    and store.at(candidate, end).realised_traced
                    and (
                        store.at(candidate, end).realised == 0
                        or (
                            store.classify_same_day_entry_usage
                            and store.classify_batch_cancelled_usage
                        )
                    )
                )
            ):
                same_day_entry = candidate
                same_day_modifications = amendments or frozenset()
    relevant = [
        (version, ob)
        for version in (opening_version, *moved, closing_version)
        if version is not None and (ob := _in_version(store, version, obligation_id)) is not None
    ]
    if same_day_entry is not None:
        relevant.append((moved[0], same_day_entry))
    # A closing exemption cannot erase a previously disclosed opening balance.
    # Preserve the old omission only when every retained version is fully exempt.
    if relevant and all(
        _exemption(ob, applied, store.durations(version)) is not None for version, ob in relevant
    ):
        return
    lines = dict.fromkeys(ROLLFORWARD_LINES, ZERO)
    opening = _in_version(store, opening_version, obligation_id, before)
    evidence = [
        store.at(ob, end).realised_traced
        for version in (opening_version, *moved)
        if (ob := _in_version(store, version, obligation_id)) is not None
    ]
    if any(evidence) and not all(evidence):
        raise to_date.Unreadable(
            f"obligations[{described.obligation_key}].{to_date.REALISED}",
            f"Contract {described.external_id}, obligation {described.obligation_key}: "
            "this rollforward mixes dated realization evidence with legacy versions that lack it. "
            "Historical realized allocation cannot be inferred from a missing series. "
            "Nothing is reported in its place.",
        )
    if opening is not None:
        lines["OPENING"] = rpo_of(opening, before, DEFAULT_BANDS, store.at(opening, before))[0]

    def fixed(ob: _Ob, day: date) -> Decimal:
        at = store.at(ob, day)
        value = (
            ob.allocated - at.realised_stored
            if at.fixed_allocation is None
            else at.fixed_allocation
        )
        # The general dated reader measures period ends. Internal lifecycle boundaries
        # must exclude later same-period allocation changes using their original amounts.
        if at.fixed_measured is not None:
            subject = obligation_subject_key(ob.external_id, ob.obligation_key)
            for sliced in store.chains.get(ob.contract_id, ()):
                if not (
                    sliced.id == ob.version_id
                    and sliced.dated_slice
                    and day < sliced.effective <= at.fixed_measured.end_date
                ):
                    continue
                history = store.boundaries.get(ob.version_id, {})
                if sliced.modification_events and not rpo_boundary_changes.complete(
                    history, subject, sliced.modification_events
                ):
                    raise to_date.Unreadable(
                        f"obligations[{ob.obligation_key}].fixed_allocation",
                        "Original amendment evidence is required at the eligibility boundary.",
                    )
                shares = _estimate_changes(store, sliced)
                if shares is None:
                    raise to_date.Unreadable(
                        f"obligations[{ob.obligation_key}].fixed_allocation",
                        "Original estimate shares are required at the eligibility boundary.",
                    )
                value -= shares.get(subject, ZERO) + sum(
                    (
                        change.amount
                        for change in history.get(subject, ())
                        if change.event in sliced.modification_events
                    ),
                    ZERO,
                )
        return value

    previous_obligation = opening
    previous_version = opening_version
    previous = ZERO if opening is None else fixed(opening, before)
    realised_opening = ZERO if opening is None else store.at(opening, before).realised
    terminal_cancellation: _Ob | None = None
    pending_cancellation: _Ob | None = None
    batch_cancelled_usage: _Ob | None = None
    batch_usage_cut = end
    segment_start = before
    segment_opening = ZERO if opening is None else store.at(opening, before).revenue
    segment_has_opening = opening is not None
    previously_included = False
    if opening_version is not None:
        for retained in store.chains.get(described.contract_id, ()):
            if retained == opening_version:
                break
            if retained.included and any(
                ob.obligation_id == obligation_id for ob in store.obligations.get(retained.id, ())
            ):
                previously_included = True
    outside_scope = bool(
        previously_included
        and store.classify_eligibility_changes
        and opening_version is not None
        and not opening_version.included
    )
    was_cancelled = (
        opening is None
        and opening_version is not None
        and any(
            ob.obligation_id == obligation_id and ob.cancelled
            for ob in store.obligations.get(opening_version.id, ())
        )
    )

    def recognition(ob: _Ob, until: date) -> Decimal:
        cumulative = store.at(ob, until).revenue
        restated = store.at(ob, segment_start).revenue
        lines["REVENUE"] -= cumulative - restated
        if segment_has_opening:
            lines["LATE_EVENTS"] -= restated - segment_opening
        return cumulative

    def cancelled_tail(start: int) -> _Ob | None:
        """Final realized source only when every subsequent version stays cancelled."""
        if not store.classify_cancelled_usage_chains:
            return None
        latest = None
        for retained in moved[start:]:
            if not retained.included:
                return None
            candidate = next(
                (
                    ob
                    for ob in store.obligations.get(retained.id, ())
                    if ob.obligation_id == obligation_id
                ),
                None,
            )
            if (
                candidate is None
                or not candidate.cancelled
                or store.visible(candidate, retained.effective) is not None
                or not store.at(candidate, end).realised_traced
            ):
                return None
            latest = candidate
        return latest

    def cancelled_segment(start: int, initial: _Ob | None = None) -> tuple[_Ob, date] | None:
        """Retained cancellation evidence up to the next disclosure re-entry."""
        if not store.classify_usage_reentry:
            return None
        if initial is not None and (
            not store.classify_batch_usage_reentry
            or not store.classify_batch_cancelled_usage
            or not store.classify_cancelled_usage_chains
            or not store.at(initial, end).realised_traced
        ):
            return None
        latest = initial
        for retained in moved[start:]:
            if not retained.included:
                return None
            candidate = next(
                (
                    ob
                    for ob in store.obligations.get(retained.id, ())
                    if ob.obligation_id == obligation_id
                ),
                None,
            )
            if candidate is None or not store.at(candidate, end).realised_traced:
                return None
            if store.visible(candidate, retained.effective) is not None:
                return None if latest is None else (latest, retained.effective)
            if not candidate.cancelled:
                return None
            latest = candidate
        return None if latest is None else (latest, end)

    def settle_batch_usage() -> None:
        nonlocal batch_cancelled_usage
        if batch_cancelled_usage is not None:
            realized = store.at(batch_cancelled_usage, batch_usage_cut).realised
            lines["VC_ESTIMATE_CHANGES"] += realized
            lines["CANCELLATIONS"] -= realized
            batch_cancelled_usage = None

    if opening is not None:
        terminal = store.cancellation(opening)
        if (
            terminal is not None
            and before < terminal.day <= end
            and (
                not moved
                or (store.classify_cancelled_chains and terminal.day <= moved[0].effective)
                or (store.classify_cancelled_chains and store.classify_pretermination_versions)
            )
            and terminal.before is not None
            and (
                (store.at(opening, end).realised == 0 and realised_opening == 0)
                or (
                    store.classify_batch_cancelled_usage
                    and (
                        not moved
                        or cancelled_tail(0) is not None
                        or cancelled_segment(0, opening) is not None
                    )
                    and store.at(opening, end).realised_traced
                    and store.at(opening, before).realised_traced
                )
            )
            and opening_version is not None
        ):
            subject = obligation_subject_key(opening.external_id, opening.obligation_key)
            mods = frozenset(
                item.event
                for item in store.boundaries.get(opening.version_id, {}).get(subject, ())
                if before < item.day <= terminal.day
                and CAUSE_LINES.get(item.kind) == "MODIFICATIONS"
            )
            estimates = frozenset(
                event
                for event, day in opening_version.estimate_dates
                if before < day <= terminal.day
            )
            if all(
                (opening.version_id, event) in store.estimate_event_allocations
                for event in estimates
            ):
                estimate_amount = sum(
                    (
                        store.estimate_event_allocations[opening.version_id, event].get(
                            subject, ZERO
                        )
                        for event in estimates
                    ),
                    ZERO,
                )
                scoped = dataclasses.replace(
                    opening_version,
                    modification_events=mods,
                    estimate_events=estimates,
                    cancellation_events=frozenset(
                        item.event
                        for item in store.boundaries.get(opening.version_id, {}).get(subject, ())
                        if before < item.day <= terminal.day and item.kind == "CONTRACT_TERMINATED"
                    )
                    if store.classify_cancellation_cross_changes
                    else frozenset({terminal.event}),
                    causes=frozenset(
                        {"CONTRACT_TERMINATED"}
                        | ({"CONTRACT_AMENDED"} if mods else set())
                        | ({"ESTIMATE_CHANGED"} if estimates else set())
                    ),
                )
                reader = dataclasses.replace(
                    store,
                    estimate_allocations={
                        **store.estimate_allocations,
                        opening.version_id: {subject: estimate_amount},
                    },
                )
                separated = _cancelled_changes(reader, scoped, subject, previous)
                if separated is not None:
                    lines["MODIFICATIONS"] += separated[0]
                    lines["VC_ESTIMATE_CHANGES"] += separated[1]
                    boundary = _cancellation_boundary(
                        reader,
                        store.boundaries[opening.version_id][subject],
                        scoped.cancellation_events,
                    )
                    assert boundary is not None
                    if (
                        store.classify_pretermination_versions
                        and moved
                        and moved[0].effective < terminal.day
                    ):
                        lines["CANCELLATIONS"] += boundary[1]
                        previous = terminal.before
                        pending_cancellation = opening
                    else:
                        lines["CANCELLATIONS"] += boundary[1] - terminal.before
                        terminal_cancellation = opening
                    if store.classify_batch_cancelled_usage:
                        batch_segment = cancelled_segment(0, opening)
                        if batch_segment is not None:
                            batch_cancelled_usage, batch_usage_cut = batch_segment
                        elif not moved:
                            batch_cancelled_usage = opening
                        elif cancelled_tail(0) is not None:
                            batch_cancelled_usage = cancelled_tail(0)
                    if pending_cancellation is None:
                        previous = ZERO
                        previous_obligation = None
                        was_cancelled = True

    for index, version in enumerate(moved):
        if pending_cancellation is not None and store.classify_pretermination_versions:
            terminal = store.cancellation(pending_cancellation)
            if terminal is not None and version.effective < terminal.day:
                # A newer computation can supersede a future cancellation. Carry
                # its pre-termination balance into the version delta, not zero.
                pending_cancellation = None
        if pending_cancellation is not None:
            terminal = store.cancellation(pending_cancellation)
            assert terminal is not None and terminal.before is not None
            # Settle the earlier computation's dated termination before a later
            # version can supersede its retained revenue or admit a new segment.
            lines["CANCELLATIONS"] -= terminal.before
            terminal_cancellation = pending_cancellation
            batch_segment = cancelled_segment(index, pending_cancellation)
            if batch_segment is not None:
                batch_cancelled_usage, batch_usage_cut = batch_segment
            elif store.classify_batch_cancelled_usage and cancelled_tail(index) is not None:
                batch_cancelled_usage = cancelled_tail(index)
            pending_cancellation = None
            previous = ZERO
            previous_obligation = None
            was_cancelled = True
        current = _in_version(store, version, obligation_id)
        if same_day_entry is not None and same_day_entry.version_id == version.id:
            current = same_day_entry
        if (
            store.classify_eligibility_changes
            and previous_obligation is not None
            and not version.included
            and version.eligibility_exits.count(
                (previous_obligation.contract_id, version.effective)
            )
            == 1
            and "COLLECTIBILITY_ASSESSED" in version.causes
        ):
            # The retained excluded computation still carries recognition through
            # the exit. Do not present loss of eligibility as a legal termination.
            exiting = next(
                (
                    ob
                    for ob in store.obligations.get(version.id, ())
                    if ob.obligation_id == obligation_id
                ),
                None,
            )
            if (
                exiting is not None
                and not exiting.cancelled
                and store.at(exiting, end).realised_traced
                and (
                    separated := _eligibility_changes(
                        store,
                        version,
                        obligation_subject_key(exiting.external_id, exiting.obligation_key),
                        fixed(exiting, version.effective) - previous,
                    )
                )
                is not None
            ):
                revenue = recognition(exiting, version.effective)
                realized = store.at(exiting, version.effective).realised
                modified, estimate = separated
                lines["MODIFICATIONS"] += modified
                lines["VC_ESTIMATE_CHANGES"] += estimate
                lines["ELIGIBILITY_CHANGES"] -= (
                    fixed(exiting, version.effective) + realized - revenue
                )
                lines["VC_ESTIMATE_CHANGES"] += realized
                outside_scope = True
                previous = ZERO
                previous_obligation = None
                previous_version = version
                continue
        eligibility_entry = bool(
            outside_scope
            and current is not None
            and "CONTRACT_CRITERIA_MET" in version.causes
            and any(cid == current.contract_id for cid, _ in version.entries)
        )
        entry_line = "ELIGIBILITY_CHANGES" if eligibility_entry else "NEW_CONTRACTS"
        # A new obligation in an already disclosed contract is a movement of that
        # contract. Its absent opening obligation does not make it a new contract.
        admission = previous_obligation is None and (
            not store.classify_added_obligations
            or previous_version is None
            or not previous_version.included
            or was_cancelled
            or (
                current is not None
                and any(contract_id == current.contract_id for contract_id, _ in version.entries)
            )
        )
        reentry = (
            current is not None
            and previous_obligation is None
            and (was_cancelled or eligibility_entry)
        )
        if current is not None:
            if terminal_cancellation is not None:
                settle_batch_usage()
                lines["CANCELLATIONS"] += recognition(terminal_cancellation, version.effective)
                terminal_cancellation = None
            if previous_obligation is None and (was_cancelled or eligibility_entry):
                # Re-entry admits the remaining balance, not revenue recognized
                # before this new disclosure segment (including while excluded).
                segment_start = version.effective
                segment_opening = store.at(current, segment_start).revenue
                segment_has_opening = True
                lines[entry_line] -= segment_opening
                was_cancelled = False
                outside_scope = False
        elif terminal_cancellation is not None:
            terminal_cancellation = next(
                (
                    ob
                    for ob in store.obligations.get(version.id, ())
                    if ob.obligation_id == obligation_id
                ),
                terminal_cancellation,
            )
        allocated = (
            ZERO
            if current is None
            else fixed(current, version.effective if version.dated_slice else end)
        )
        if (
            current is not None
            and current.cancelled
            and (admission or store.classify_pretermination_versions)
            and (store.classify_cancelled_chains or len(moved) == 1)
        ):
            terminal = store.cancellation(current)
            if (
                terminal is not None
                and terminal.day <= end
                and (
                    index + 1 == len(moved)
                    or terminal.day <= moved[index + 1].effective
                    or store.classify_pretermination_versions
                )
                and terminal.before is not None
                and (
                    (
                        store.at(current, end).realised == 0
                        and "USAGE_REPORTED" not in version.causes
                    )
                    or (
                        store.classify_batch_cancelled_usage
                        and (
                            len(moved) == 1
                            or cancelled_tail(index + 1) is not None
                            or cancelled_segment(index + 1, current) is not None
                        )
                        and store.at(current, end).realised_traced
                    )
                )
                and all(
                    (day, dict(version.estimate_order).get(event, 0), event)
                    < (terminal.day, terminal.record_seq or 0, terminal.event)
                    and (day != terminal.day or event in dict(version.estimate_order))
                    for event, day in version.estimate_dates
                    if day > version.effective
                )
                and all(
                    (item.day, item.record_seq or 0, item.event)
                    < (terminal.day, terminal.record_seq or 0, terminal.event)
                    for item in store.boundaries.get(version.id, {}).get(
                        obligation_subject_key(current.external_id, current.obligation_key), ()
                    )
                    if item.event in version.modification_events
                )
            ):
                allocated = terminal.before
                pending_cancellation = current
        if current is not None and admission:
            # Fees realized by completed periods before admission enter with the contract;
            # later realization is independently identified variable consideration.
            entry_realised = (
                store.at(current, version.effective).realised_through
                if store.at(current, end).realised_traced
                else ZERO
            )
            if reentry and store.classify_usage_reentry and store.at(current, end).realised_traced:
                entry_realised = store.at(current, version.effective).realised
            lines[entry_line] += entry_realised
            lines["VC_ESTIMATE_CHANGES"] -= entry_realised
            subject = obligation_subject_key(current.external_id, current.obligation_key)
            boundaries = store.boundaries.get(version.id, {}).get(subject, ())
            continuing = (
                _continuing_cancellations(store, version, subject, version.effective, end)
                if pending_cancellation is None and store.visible(current, end) is not None
                else None
            )
            if continuing is not None:
                lines["NEW_CONTRACTS"] -= continuing
                lines["CANCELLATIONS"] += continuing
            if pending_cancellation is current and store.classify_cancellation_cross_changes:
                boundary = _cancellation_boundary(store, boundaries, version.cancellation_events)
                if boundary is not None:
                    lines["NEW_CONTRACTS"] -= boundary[1]
                    lines["CANCELLATIONS"] += boundary[1]
            complete_boundaries = rpo_boundary_changes.complete(
                store.boundaries.get(version.id, {}), subject, version.modification_events
            )
            if complete_boundaries:
                modified = sum(
                    (
                        item.amount
                        for item in boundaries
                        if item.event in version.modification_events
                        and (
                            version.effective < item.day <= end
                            or (
                                same_day_entry is not None
                                and current.version_id == same_day_entry.version_id
                                and item.event in same_day_modifications
                            )
                        )
                        and CAUSE_LINES.get(item.kind) == "MODIFICATIONS"
                    ),
                    ZERO,
                )
                lines["NEW_CONTRACTS"] -= modified
                lines["MODIFICATIONS"] += modified
            later = [
                (event, day)
                for event, day in version.estimate_dates
                if day > version.effective
                and (store.at(current, end).fixed_allocation is None or day <= end)
            ]
            if (
                later
                and all(day <= end for _, day in later)
                and not any(
                    (
                        CAUSE_LINES.get(kind) == "CANCELLATIONS"
                        and pending_cancellation is not current
                        and continuing is None
                    )
                    or (CAUSE_LINES.get(kind) == "MODIFICATIONS" and not complete_boundaries)
                    for kind in version.causes
                )
                and all(
                    (version.id, event) in store.estimate_event_allocations for event, _ in later
                )
            ):
                # Inception estimates are part of entry. Later original estimate
                # shares are changes, even if first computed together with entry.
                subject = obligation_subject_key(current.external_id, current.obligation_key)
                change = sum(
                    (
                        store.estimate_event_allocations[version.id, event].get(subject, ZERO)
                        for event, _ in later
                    ),
                    ZERO,
                )
                lines["NEW_CONTRACTS"] -= change
                lines["VC_ESTIMATE_CHANGES"] += change
        cancelled_usage = None
        usage_segment = cancelled_segment(index) if current is None else None
        if (
            store.classify_cancelled_usage
            and current is None
            and previous_obligation is not None
            and (
                (
                    len(moved) == 1
                    and closing_version is not None
                    and closing_version.id == version.id
                )
                or cancelled_tail(index) is not None
                or usage_segment is not None
            )
            and "CONTRACT_TERMINATED" in version.causes
            and store.at(previous_obligation, end).realised_traced
        ):
            cancelled_usage = (
                (usage_segment[0] if usage_segment is not None else None)
                or cancelled_tail(index)
                or next(
                    (
                        ob
                        for ob in store.obligations.get(version.id, ())
                        if ob.obligation_id == obligation_id
                        and ob.cancelled
                        and store.at(ob, end).realised_traced
                    ),
                    None,
                )
            )
        if current is None and previous_obligation is not None:
            removed = (
                store.at(previous_obligation, version.effective).realised
                if store.at(previous_obligation, end).realised_traced
                else ZERO
            )
            if cancelled_usage is not None:
                # The terminating computation includes newly realized fees and
                # corrections absent from the previous version. Its full retained
                # realization is removed from RPO; the change remains a VC movement.
                until = end if usage_segment is None else usage_segment[1]
                removed = store.at(cancelled_usage, until).realised
            lines["CANCELLATIONS"] -= removed
            lines["VC_ESTIMATE_CHANGES"] += removed
        delta = allocated - previous
        if admission:
            line: str | None = entry_line
        else:
            realised_is_separate = current is not None and store.at(current, end).realised_traced
            causes = {
                CAUSE_LINES[kind]
                for kind in version.causes
                if kind in CAUSE_LINES and not (realised_is_separate and kind == "USAGE_REPORTED")
            }
            # Dated usage (including royalty statements) is already attributed below.
            # It cannot also make a fixed amendment ambiguous or explain an otherwise
            # unsupported fixed change. Competing remaining cause lines stay unexplained.
            line = next(iter(causes)) if len(causes) == 1 else None
            changes = _estimate_changes(store, version)
            if (
                causes == {"MODIFICATIONS", "VC_ESTIMATE_CHANGES"}
                and changes is not None
                and current is not None
                and ("USAGE_REPORTED" not in version.causes or realised_is_separate)
            ):
                estimate_change = changes.get(
                    obligation_subject_key(current.external_id, current.obligation_key), ZERO
                )
                lines["VC_ESTIMATE_CHANGES"] += estimate_change
                delta -= estimate_change
                line = "MODIFICATIONS"
            if (
                current is not None
                and previous_obligation is not None
                and store.visible(current, end) is not None
                and "CANCELLATIONS" in causes
                and len(causes) > 1
                and causes <= {"CANCELLATIONS", "MODIFICATIONS", "VC_ESTIMATE_CHANGES"}
                and ("USAGE_REPORTED" not in version.causes or realised_is_separate)
            ):
                separated = _continuing_changes(
                    store,
                    version,
                    obligation_subject_key(current.external_id, current.obligation_key),
                    delta,
                    end,
                )
                if separated is not None:
                    modified, estimate = separated
                    lines["MODIFICATIONS"] += modified
                    lines["VC_ESTIMATE_CHANGES"] += estimate
                    delta -= modified + estimate
                    line = "CANCELLATIONS"
            if (
                (
                    current is None
                    or (store.classify_pretermination_versions and pending_cancellation is current)
                )
                and previous_obligation is not None
                and "CANCELLATIONS" in causes
                and len(causes) > 1
                and causes <= {"CANCELLATIONS", "MODIFICATIONS", "VC_ESTIMATE_CHANGES"}
                and ("USAGE_REPORTED" not in version.causes or cancelled_usage is not None)
            ):
                separated = _cancelled_changes(
                    store,
                    version,
                    obligation_subject_key(
                        previous_obligation.external_id, previous_obligation.obligation_key
                    ),
                    previous,
                )
                if separated is not None:
                    modified, estimate = separated
                    lines["MODIFICATIONS"] += modified
                    lines["VC_ESTIMATE_CHANGES"] += estimate
                    delta -= modified + estimate
                    line = "CANCELLATIONS"
        if line is not None:
            lines[line] += delta
            if current is None and line == "CANCELLATIONS":
                was_cancelled = True
                # The terminating computation retains recognized revenue even
                # though this obligation no longer contributes remaining RPO.
                terminal_cancellation = next(
                    (
                        ob
                        for ob in store.obligations.get(version.id, ())
                        if ob.obligation_id == obligation_id
                    ),
                    None,
                )
        previous = allocated
        previous_obligation = current
        previous_version = version
    closing = _in_version(store, closing_version, obligation_id, end)
    if pending_cancellation is not None:
        terminal = store.cancellation(pending_cancellation)
        assert terminal is not None and terminal.before is not None
        lines["CANCELLATIONS"] -= terminal.before
        terminal_cancellation = pending_cancellation
        batch_segment = cancelled_segment(len(moved), pending_cancellation)
        if batch_segment is not None:
            batch_cancelled_usage, batch_usage_cut = batch_segment
        elif store.classify_batch_cancelled_usage and len(moved) == 1:
            batch_cancelled_usage = pending_cancellation
            batch_usage_cut = end
    if opening is not None and closing is not None and not moved:
        open_fixed = store.at(opening, before).fixed_allocation
        close_fixed = store.at(closing, end).fixed_allocation
        if open_fixed is not None and close_fixed is not None and opening_version is not None:
            events = [event for event, day in opening_version.estimate_dates if before < day <= end]
            if (events or store.boundaries.get(closing.version_id)) and all(
                (closing.version_id, event) in store.estimate_event_allocations for event in events
            ):
                subject = obligation_subject_key(closing.external_id, closing.obligation_key)
                change = sum(
                    (
                        store.estimate_event_allocations[closing.version_id, event].get(
                            subject, ZERO
                        )
                        for event in events
                    ),
                    ZERO,
                )
                modifications = sum(
                    (
                        item.amount
                        for item in store.boundaries.get(closing.version_id, {}).get(subject, ())
                        if before < item.day <= end
                        and CAUSE_LINES.get(item.kind) == "MODIFICATIONS"
                    ),
                    ZERO,
                )
                continuing = _continuing_cancellations(store, opening_version, subject, before, end)
                cancelled = continuing if continuing is not None else ZERO
                if change + modifications + cancelled == close_fixed - open_fixed:
                    lines["CANCELLATIONS"] += cancelled
                    lines["VC_ESTIMATE_CHANGES"] += change
                    lines["MODIFICATIONS"] += modifications
    settle_batch_usage()
    realised_closing = ZERO if closing is None else store.at(closing, end).realised
    lines["VC_ESTIMATE_CHANGES"] += realised_closing - realised_opening
    if closing is not None:
        at_end = store.at(closing, end)
        recognition(closing, end)
        lines["CLOSING"] = rpo_of(closing, end, DEFAULT_BANDS, at_end)[0]
    elif terminal_cancellation is not None:
        lines["CANCELLATIONS"] += recognition(terminal_cancellation, end)

    def excluded(ob: _Ob | None, version: _Version | None, day: date, total: Decimal) -> Decimal:
        if ob is None or version is None:
            return ZERO
        if _exemption(ob, applied, store.durations(version)) is not None:
            return total
        return _partial_exclusion(store, ob, day, total, applied)

    opening_excluded = excluded(opening, opening_version, before, lines["OPENING"])
    closing_excluded = excluded(closing, closing_version, end, lines["CLOSING"])
    lines["OPENING"] -= opening_excluded
    lines["CLOSING"] -= closing_excluded
    lines["EXEMPTIONS"] = opening_excluded - closing_excluded
    lines["UNEXPLAINED"] = (
        lines["CLOSING"] - lines["OPENING"] - sum((lines[code] for code in MOVEMENTS), ZERO)
    )
    key = (described.external_id, described.currency)
    into = totals.setdefault(
        key,
        {
            "customer_name": described.customer_name,
            "entity_code": described.entity_code,
            "lines": dict.fromkeys(ROLLFORWARD_LINES, ZERO),
            "exemption_changes": [],
        },
    )
    if opening_excluded or closing_excluded:

        def exemption_code(ob: _Ob | None, version: _Version | None, amount: Decimal) -> str | None:
            if ob is None or version is None or not amount:
                return None
            return _exemption(ob, applied, store.durations(version)) or "POL-200"

        into["exemption_changes"].append(
            {
                "contract": described.external_id,
                "obligation": described.obligation_key,
                "entity": described.entity_code,
                "currency": described.currency,
                "opening_date": before.isoformat(),
                "closing_date": end.isoformat(),
                "opening_rule": exemption_code(opening, opening_version, opening_excluded),
                "closing_rule": exemption_code(closing, closing_version, closing_excluded),
                "opening_excluded": str(opening_excluded),
                "closing_excluded": str(closing_excluded),
                "movement": str(lines["EXEMPTIONS"]),
            }
        )
    for code in ROLLFORWARD_LINES:
        into["lines"][code] += lines[code]


# --- the rpo report -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Run:
    book_code: str
    entities: tuple[EntityRef, ...]
    as_of: Mapping[UUID, date]
    period_starts: Mapping[UUID, date]
    bands: tuple[int, ...]
    store: Store
    applied: Mapping[UUID, frozenset[str]]
    found: tuple[ObligationRpo, ...]
    source_found: tuple[ObligationRpo, ...] = ()
    translation_rates: tuple[Mapping[str, Any], ...] = ()


def _run(session: Session, params: ReportParams, uow: UnitOfWork | None = None) -> _Run:
    book_code = tie_outs.book_of(session, params)
    found_entities = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found_entities, params=params)
    as_of: dict[UUID, date] = {}
    starts: dict[UUID, date] = {}
    periods: dict[UUID, tie_outs.PeriodRef] = {}
    for entity in found_entities:
        at = tie_outs.period_of(params, found_calendars[entity.id], entity)
        periods[entity.id] = at
        as_of[entity.id] = at.end
        starts[entity.id] = at.start
    given = params.parameters.get("time_bands")
    resolved: set[tuple[int, ...]] = set()
    for entity in found_entities:
        value = given
        if value is None:
            value = resolve(
                session,
                TIME_BANDS,
                book_code=BookCode(book_code),
                entity_id=entity.id,
                known_at=params.known_at,
            ).value
        resolved.add(tuple(sorted(int(item) for item in (value or DEFAULT_BANDS))))
    if len(resolved) > 1:
        raise tie_outs.invalid("time_bands", MIXED_BANDS)
    bands = next(iter(resolved)) if resolved else DEFAULT_BANDS
    cutoff = tie_outs.cutoff_for(session, params)
    store = load(
        session, entity_ids=params.entity_ids, book_code=book_code, cutoff=cutoff, params=params
    )
    applied = applied_expedients(
        session, found_entities, book_code=book_code, known_at=params.known_at
    )
    # the as-of date, and the day before its period for the rollforward the tie-out reads
    measure(
        session,
        store,
        {
            entity_id: (starts[entity_id] - timedelta(days=1), day)
            for entity_id, day in as_of.items()
        },
        applied=applied,
        uow=uow,
        book_code=book_code,
        params=params,
    )
    found = rows_at(store, as_of=as_of, bands=bands, applied=applied)
    converted, rates = rpo_currency.translate(session, params, found, found_entities, periods)
    return _Run(
        book_code,
        found_entities,
        as_of,
        starts,
        bands,
        store,
        applied,
        converted,
        found,
        rates,
    )


def _dimension_key(item: ObligationRpo, dimension: str) -> tuple[str, dict[str, Any]]:
    ob = item.ob
    if dimension == "ENTITY":
        return f"entity:{ob.entity_code}", {"entity_code": ob.entity_code}
    if dimension == "PRODUCT_FAMILY":
        return f"product_family:{ob.product_family or ''}", {}
    if dimension == "CUSTOMER_SEGMENT":
        return f"customer_segment:{ob.customer_segment or ''}", {}
    return f"contract:{ob.external_id}", {
        "contract_external_id": ob.external_id,
        "customer_name": ob.customer_name,
        "entity_code": ob.entity_code,
    }


def _grouped(found: Sequence[ObligationRpo], dimension: str) -> dict[str, list[ObligationRpo]]:
    groups: dict[str, list[ObligationRpo]] = {}
    for item in found:
        if item.exemption is None:
            key = f"{_dimension_key(item, dimension)[0]}:{item.ob.currency}"
            groups.setdefault(key, []).append(item)
    currencies = {item.ob.currency for items in groups.values() for item in items}
    if len(currencies) <= 1:
        return {key.rsplit(":", 1)[0]: items for key, items in groups.items()}
    return groups


def _figures(
    items: Sequence[ObligationRpo], bands: Sequence[Band], currency: str
) -> dict[str, Any]:
    total = sum((item.total for item in items), ZERO)
    current = sum((item.current for item in items), ZERO)
    values: dict[str, Any] = {
        "currency": currency,
        TOTAL: tie_outs.money(total, currency),
        CURRENT: tie_outs.money(current, currency),
        NONCURRENT: tie_outs.money(total - current, currency),
    }
    for band in bands:
        values[band.key] = tie_outs.money(
            sum((item.placed[band.index] for item in items), ZERO), currency
        )
    return values


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    run = _run(session, params, uow)
    bands = bands_of(run.bands)
    dimension = str(params.parameters.get("row_dimension") or "CONTRACT")
    elected = {
        entity.id: elections.entity_elections(
            session, entity_id=entity.id, book_code=run.book_code, known_at=params.known_at
        )
        for entity in run.entities
    }
    omitted = {
        entity_id for entity_id, found in elected.items() if found.is_elected(elections.RPO_RELIEF)
    }
    hidden = omitted if params.output_format == "JSON" else set()
    visible = tuple(item for item in run.found if item.ob.entity_id not in hidden)
    rows: list[dict[str, Any]] = []
    totals: dict[str, list[ObligationRpo]] = {}
    for key, items in _grouped(visible, dimension).items():
        rows.append(
            {
                "row_key": key,
                "section": 1,
                "contract_external_id": None,
                "customer_name": None,
                "entity_code": None,
                **_dimension_key(items[0], dimension)[1],
                **_figures(items, bands, items[0].ob.currency),
            }
        )
        totals.setdefault(items[0].ob.currency, []).extend(items)
    for currency, items in sorted(totals.items()):
        rows.append(
            {
                "row_key": f"{TOTAL_PREFIX}{currency}",
                "section": 1,
                "contract_external_id": None,
                "customer_name": None,
                "entity_code": None,
                **_figures(items, bands, currency),
            }
        )
    labels = {pol: (label, description) for pol, _, label, description in EXPEDIENTS}
    excluded: dict[str, Decimal] = {}
    for item in visible:
        policy = item.exemption or item.partial_exemption
        if policy is None:
            continue
        excluded_amount = item.total if item.exemption else item.excluded
        label, description = labels[policy]
        exempt_key = f"{item.ob.external_id}:{item.ob.obligation_key}:{policy}"
        rows.append(
            {
                "row_key": f"exempt:{exempt_key}",
                "section": 2,
                "contract_external_id": item.ob.external_id,
                "obligation_key": item.ob.obligation_key,
                "expedient": policy,
                "expedient_label": label,
                "nature": item.ob.product_name,
                "remaining_duration_months": item.remaining_months,
                **(
                    {
                        "original_inception_date": item.ob.inception,
                        "original_contract_end_date": run.store.original_ends[item.ob.version_id][
                            item.ob.external_id
                        ],
                    }
                    if policy == "POL-197"
                    else {}
                ),
                "excluded_amount": tie_outs.money(excluded_amount, item.ob.currency),
                "excluded_descriptor": description,
                "currency": item.ob.currency,
            }
        )
        add(excluded, item.ob.currency, excluded_amount)
    notes: list[dict[str, Any]] = []
    for entity in run.entities:
        if entity.id in omitted:
            notes.append(
                {"entity_code": entity.code, **elected[entity.id].note(elections.RPO_RELIEF, 1)}
            )
            notes.append(
                {"entity_code": entity.code, **elected[entity.id].note(elections.RPO_RELIEF, 2)}
            )
        elif not any(
            item.exemption or item.partial_exemption
            for item in run.found
            if item.ob.entity_id == entity.id
        ):
            notes.append(
                {
                    "entity_code": entity.code,
                    "section": 2,
                    "note": NO_EXEMPTIONS.format(entity=entity.code),
                }
            )
    actual: dict[str, Decimal] = {}
    for item in run.found:
        if item.exemption is None:
            add(actual, item.ob.currency, item.total)
    ranges = {
        entity.id: (run.period_starts[entity.id] - timedelta(days=1), run.as_of[entity.id])
        for entity in run.entities
    }
    expected: dict[str, Decimal] = {}
    for contract_lines in rollforward_lines(run.store, ranges=ranges, applied=run.applied):
        add(expected, contract_lines.currency, contract_lines.lines["CLOSING"])
    source_actual: dict[str, Decimal] = {}
    for item in run.source_found:
        if item.exemption is None:
            add(source_actual, item.ob.currency, item.total)
    check = tie_outs.compared(tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO, expected, source_actual)
    converted = params.parameters.get("currency_view", "transaction") != "transaction"
    if converted:
        check["details"] = [
            {"currency_basis": "transaction", "translation_basis": "as_of_closing_rate"}
        ]
    days = sorted({day.isoformat() for day in run.as_of.values()})
    columns = (
        Column("section", "Section", "integer"),
        Column("contract_external_id", "Contract", "code"),
        Column("customer_name", "Customer", "text"),
        Column("entity_code", "Entity", "code"),
        Column("currency", "Currency", "code"),
        Column(TOTAL, "Total (as-of FX)" if converted else "Total", "money"),
        *(Column(band.key, _band_label(band), "money") for band in bands),
        Column(CURRENT, "Current", "money"),
        Column(NONCURRENT, "Noncurrent", "money"),
        Column("obligation_key", "Obligation", "code"),
        Column("expedient", "Expedient", "code"),
        Column("expedient_label", "Expedient name", "text"),
        Column("nature", "Nature of goods or services", "text"),
        Column("remaining_duration_months", "Remaining duration (months)", "integer"),
        Column("original_inception_date", "Original inception date", "date"),
        Column("original_contract_end_date", "Original contract end date", "date"),
        Column("excluded_amount", "Excluded amount", "money"),
        Column("excluded_descriptor", "Excluded consideration", "text"),
    )
    keys = {column.key for column in columns}
    shaped = tuple(
        {"row_key": row["row_key"], **{name: value for name, value in row.items() if name in keys}}
        for row in rows
    )
    return ReportData(
        columns=columns,
        rows=shaped,
        control_totals={
            "as_of": days[0] if len(days) == 1 else days,
            "bands": [band.out() for band in bands],
            "total": tie_outs.by_currency(actual),
            "excluded_total": tie_outs.by_currency(excluded),
            "notes": notes,
            "currency_view": str(params.parameters.get("currency_view") or "transaction"),
            "translation_basis": "as_of_closing_rate" if converted else "transaction",
            "tie_out_currency_basis": "transaction",
            "translation_rates": list(run.translation_rates),
        },
        tie_out_results=(check,),
    )


def _band_label(band: Band) -> str:
    """DS-CH-03 labels: "Within 12 months", "13 to 24 months", "After 24 months"."""
    if band.index == 0:
        return f"Within {band.to_month} months"
    if band.to_month is None:
        return f"After {band.from_month - 1} months"
    return f"{band.from_month} to {band.to_month} months"


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """The value and contributors of one section 1 cell: ``total``, ``current``, ``noncurrent`` or
    a band key (04 §16.9)."""
    run = _run(session, params)
    bands = bands_of(run.bands)
    dimension = str(params.parameters.get("row_dimension") or "CONTRACT")
    if row_key.startswith(TOTAL_PREFIX):
        currency = row_key[len(TOTAL_PREFIX) :]
        items = [
            item for item in run.found if item.exemption is None and item.ob.currency == currency
        ]
    else:
        items = _grouped(run.found, dimension).get(row_key, [])
    band = next((found for found in bands if found.key == column_key), None)
    if not items or (column_key not in (TOTAL, CURRENT, NONCURRENT) and band is None):
        raise filter_problem("row_key", UNKNOWN_CELL.format(row_key=row_key, column_key=column_key))
    currency = items[0].ob.currency
    value = ZERO
    contributors: list[dict[str, Any]] = []
    for item in items:
        for kind, object_id, amount, index, is_current in item.contributors:
            chosen = (
                column_key == TOTAL
                or (column_key == CURRENT and is_current)
                or (column_key == NONCURRENT and not is_current)
                or (band is not None and band.index == index)
            )
            if not chosen:
                continue
            value += amount
            measure = "amount" if kind == "schedule_line" else "awaiting_trigger_amount"
            if kind.startswith(to_date.PERIOD_SCHEDULE + "@"):
                measure, kind = kind, "obligation_version"
            if (
                kind == "schedule_line"
                and run.store.at(item.ob, item.as_of).fixed_schedule is not None
            ):
                measure = to_date.FIXED_SCHEDULE
                fixed_cut = run.store.at(item.ob, item.as_of).fixed_schedule_cut
                if fixed_cut is not None:
                    measure += "@" + fixed_cut.isoformat()
            contributors.append(
                {
                    "object_type": kind,
                    "id": object_id,
                    "measure": measure,
                    "value": tie_outs.money(amount, currency),
                    "href": f"/api/v1/explain/{kind}/{object_id}/{measure}"
                    + (
                        f"?as_of={item.as_of}"
                        if measure.startswith(to_date.PERIOD_SCHEDULE + "@")
                        else ""
                    ),
                }
            )
    if params.parameters.get("currency_view", "transaction") != "transaction":
        for contributor in contributors:
            contributor["details"] = [
                "RPO translated at retained as-of closing rates; rounding is apportioned.",
                "The linked source retains its original transaction-currency value.",
            ]
    return tie_outs.money(value, currency), contributors
