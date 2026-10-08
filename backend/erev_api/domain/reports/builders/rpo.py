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
original expected duration, from inception to its latest obligation end date, is 12 months or less;
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
[J] L6-3-Q-27 (POL-199, POL-200): persisted versions hold no royalty or targeted VC amount per
obligation, so ``APPLY`` excludes nothing; fixed consideration is never excluded (50-14B).
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
from erev_api.domain.reports import cuts, elections, tie_outs
from erev_api.domain.reports.builders import ReportParams, filter_problem
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, EntityRef, add
from erev_api.enums import BookCode
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
FUNCTIONAL_ONLY: Final = (
    "The functional and reporting views show contracts in the entity's functional currency only."
)
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
        return self.cuts[ob.version_id, day][ob.row_id]

    def durations(self, version: _Version) -> dict[UUID, date]:
        """Each contract's latest obligation end date (inception without end dates)."""
        ends: dict[UUID, date] = {}
        for ob in self.obligations.get(version.id, ()):
            end = ob.end_date or ob.inception
            ends[ob.contract_id] = max(ends.get(ob.contract_id, ob.inception), end)
        return ends


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
    entered: dict[UUID, tuple[UUID, date]] = {}  # entry event → (its contract, its date)
    if event_ids:
        for found in session.execute(
            select(
                contract_event.c.id,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.contract_id,
                contract_event.c.payload["book"].as_string().label("admitted_book"),
            ).where(contract_event.c.id.in_(event_ids))
        ).mappings():
            kind = str(getattr(found["event_type"], "value", found["event_type"]))
            events[UUID(str(found["id"]))] = (kind, found["effective_date"])
            if kind in ENTRY_EVENTS and (
                kind != CRITERIA_MET or found["admitted_book"] == book_code
            ):
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
        ]
        previous = versions.get(group_id, [])
        effective = max(
            (day for _, day in causes), default=previous[-1].effective if previous else date.min
        )
        if previous:
            effective = max(effective, previous[-1].effective)
        entries: dict[UUID, date] = {}
        for item in row["cause_event_ids"] or ():
            found_entry = entered.get(UUID(str(item)))
            if found_entry is not None:
                contract_id, day = found_entry
                entries[contract_id] = min(entries.get(contract_id, day), day)
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
    return Store(
        versions={key: tuple(value) for key, value in versions.items()},
        obligations={key: tuple(value) for key, value in obligations.items()},
        chains=chains_of(versions, obligations, _memberships(session, obligations, cutoff)),
    )


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
    if "POL-197" in applied and ends.get(ob.contract_id, ob.inception) <= add_months(
        ob.inception, 12
    ):
        return "POL-197"
    if "POL-198" in applied and ob.recognition_method == RIGHT_TO_INVOICE:
        return "POL-198"
    return None


def measure(session: Session, store: Store, days: Mapping[UUID, Collection[date]]) -> None:
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
    scheduled = cuts.scheduled_after(
        ob.lines,
        at,
        day,
        contract=ob.external_id,
        obligation=ob.obligation_key,
        sources=ob.line_nodes,
    )
    for line_id, end, amount in scheduled:
        index = band_index(end, bounds)
        placed[index] += amount
        total += amount
        is_current = end <= current_bound
        if is_current:
            current += amount
        contributors.append(("schedule_line", line_id, amount, index, is_current))
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
                if ob.contract_id != contract_id or as_of.get(ob.entity_id) != day or ob.cancelled:
                    continue
                total, placed, current, contributors = rpo_of(ob, day, bands, store.at(ob, day))
                if total == 0:
                    continue
                remaining = (
                    0 if ob.end_date is None else max(month_ends_between(day, ob.end_date), 0)
                )
                found.append(
                    ObligationRpo(
                        ob=ob,
                        as_of=day,
                        total=total,
                        placed=placed,
                        current=current,
                        contributors=contributors,
                        exemption=_exemption(ob, applied.get(ob.entity_id, frozenset()), ends),
                        remaining_months=remaining,
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
        )
        for key, value in totals.items()
    ]
    return tuple(sorted(found, key=lambda item: (item.external_id, item.currency)))


def _in_version(store: Store, version: _Version | None, obligation_id: UUID) -> _Ob | None:
    if version is None or not version.included:
        return None
    for ob in store.obligations.get(version.id, ()):
        if ob.obligation_id == obligation_id and not ob.cancelled:
            return ob
    return None


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
            ends = store.durations(version)
            break
    if described is None or _exemption(described, applied, ends) is not None:
        return
    lines = dict.fromkeys(ROLLFORWARD_LINES, ZERO)
    opening = _in_version(store, opening_version, obligation_id)
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
    previous_obligation = opening
    previous = (
        ZERO if opening is None else opening.allocated - store.at(opening, before).realised_stored
    )
    realised_opening = ZERO if opening is None else store.at(opening, before).realised
    for version in moved:
        current = _in_version(store, version, obligation_id)
        allocated = (
            ZERO if current is None else current.allocated - store.at(current, end).realised_stored
        )
        if current is not None and previous_obligation is None:
            # Fees realized by completed periods before admission enter with the contract;
            # later realization is independently identified variable consideration.
            entry_realised = (
                store.at(current, version.effective).realised_through
                if store.at(current, end).realised_traced
                else ZERO
            )
            lines["NEW_CONTRACTS"] += entry_realised
            lines["VC_ESTIMATE_CHANGES"] -= entry_realised
        elif current is None and previous_obligation is not None:
            removed = (
                store.at(previous_obligation, version.effective).realised
                if store.at(previous_obligation, end).realised_traced
                else ZERO
            )
            lines["CANCELLATIONS"] -= removed
            lines["VC_ESTIMATE_CHANGES"] += removed
        delta = allocated - previous
        if delta:
            if previous_obligation is None:
                line: str | None = "NEW_CONTRACTS"
            else:
                causes = {CAUSE_LINES[kind] for kind in version.causes if kind in CAUSE_LINES}
                # One version may include several events. Without a per-cause allocation
                # breakdown, competing cause lines cannot be assigned by alphabetic order.
                line = next(iter(causes)) if len(causes) == 1 else None
            if line is not None:
                lines[line] += delta
        previous = allocated
        previous_obligation = current
    closing = _in_version(store, closing_version, obligation_id)
    realised_closing = ZERO if closing is None else store.at(closing, end).realised
    lines["VC_ESTIMATE_CHANGES"] += realised_closing - realised_opening
    if closing is not None:
        at_end = store.at(closing, end)
        restated = store.at(closing, before).revenue  # to the day before, as the closing knows it
        lines["REVENUE"] = -(at_end.revenue - restated)
        if opening is not None:
            # S15-R-12 late events: what the closing version recognises for the time before the
            # range and the opening did not state (module docstring)
            lines["LATE_EVENTS"] = -(restated - store.at(opening, before).revenue)
        lines["CLOSING"] = rpo_of(closing, end, DEFAULT_BANDS, at_end)[0]
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
        },
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


def _run(session: Session, params: ReportParams) -> _Run:
    book_code = tie_outs.book_of(session, params)
    found_entities = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found_entities, params=params)
    as_of: dict[UUID, date] = {}
    starts: dict[UUID, date] = {}
    for entity in found_entities:
        at = tie_outs.period_of(params, found_calendars[entity.id], entity)
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
    )
    found = rows_at(store, as_of=as_of, bands=bands, applied=applied)
    functional = {entity.id: entity.functional_currency for entity in found_entities}
    view = str(params.parameters.get("currency_view") or "transaction")
    if view != "transaction" and any(
        item.ob.currency != functional[item.ob.entity_id] for item in found
    ):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)
    return _Run(book_code, found_entities, as_of, starts, bands, store, applied, found)


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
    run = _run(session, params)
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
        if item.exemption is None:
            continue
        label, description = labels[item.exemption]
        exempt_key = f"{item.ob.external_id}:{item.ob.obligation_key}:{item.exemption}"
        rows.append(
            {
                "row_key": f"exempt:{exempt_key}",
                "section": 2,
                "contract_external_id": item.ob.external_id,
                "obligation_key": item.ob.obligation_key,
                "expedient": item.exemption,
                "expedient_label": label,
                "nature": item.ob.product_name,
                "remaining_duration_months": item.remaining_months,
                "excluded_amount": tie_outs.money(item.total, item.ob.currency),
                "excluded_descriptor": description,
                "currency": item.ob.currency,
            }
        )
        add(excluded, item.ob.currency, item.total)
    notes: list[dict[str, Any]] = []
    for entity in run.entities:
        if entity.id in omitted:
            notes.append(
                {"entity_code": entity.code, **elected[entity.id].note(elections.RPO_RELIEF, 1)}
            )
            notes.append(
                {"entity_code": entity.code, **elected[entity.id].note(elections.RPO_RELIEF, 2)}
            )
        elif not any(item.exemption for item in run.found if item.ob.entity_id == entity.id):
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
    days = sorted({day.isoformat() for day in run.as_of.values()})
    columns = (
        Column("section", "Section", "integer"),
        Column("contract_external_id", "Contract", "code"),
        Column("customer_name", "Customer", "text"),
        Column("entity_code", "Entity", "code"),
        Column("currency", "Currency", "code"),
        Column(TOTAL, "Total", "money"),
        *(Column(band.key, _band_label(band), "money") for band in bands),
        Column(CURRENT, "Current", "money"),
        Column(NONCURRENT, "Noncurrent", "money"),
        Column("obligation_key", "Obligation", "code"),
        Column("expedient", "Expedient", "code"),
        Column("expedient_label", "Expedient name", "text"),
        Column("nature", "Nature of goods or services", "text"),
        Column("remaining_duration_months", "Remaining duration (months)", "integer"),
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
        },
        tie_out_results=(tie_outs.compared(tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO, expected, actual),),
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
            if (
                kind == "schedule_line"
                and run.store.at(item.ob, item.as_of).fixed_schedule is not None
            ):
                measure = to_date.FIXED_SCHEDULE
            contributors.append(
                {
                    "object_type": kind,
                    "id": object_id,
                    "measure": measure,
                    "value": tie_outs.money(amount, currency),
                    "href": f"/api/v1/explain/{kind}/{object_id}/{measure}",
                }
            )
    return tie_outs.money(value, currency), contributors
