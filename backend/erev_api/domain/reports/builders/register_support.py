"""Reads the registers and listings of RPS-9 to RPS-12 share (SCREENS_B §5.6.2, §5.6.4, §5.6.5; 04
T-PLT-17, T-PLT-18, T-PLT-20; ENGINE_SPEC_B S15-R-24 strategy ``open``; BUILD_SPEC RPS-9 to RPS-12).

- ``date_range`` and ``instants``: the inclusive ``from_date`` .. ``to_date`` of a run with the
  context defaults of SCREENS_B §5.6, and the same range as UTC instants ``[start, end)``. A
  register's date range filters instants (approved, submitted, recorded, changed) that DS-FMT-17
  shows in UTC, so a day is the UTC day.
- ``as_of_instant`` and ``instant``: the ``as_of`` of the access reports (RPT-24, RPT-25: the given
  instant, else the run's ``known_at``; never later than it) and an instant parameter as given.
- ``requests_in_scope``: the requests a register of the run's entities states — those whose every
  entity is among the run's, and the tenant-level ones (supervisor rulings R-28, R-121 (c)).
- ``requests``: T-PLT-17 approval requests as they stood at the record cutoff, each with its
  T-PLT-20 decisions by the cutoff in decision order. T-PLT-17 is IM-S and its two terminal
  transitions are timestamped (``decided_at``, ``voided_at``), so the status at a cutoff is derived
  — ``PENDING`` before either instant — never refused and never the later value.
- ``changed_after``: REGISTER-CUTOFF-1 (ENGINE_SPEC_B S15-R-20c) for a table without row history:
  on an explicit historical read a row whose last change follows the cutoff cannot be stated as of
  the cutoff; the builder refuses it by name. A live run never refuses.
- labels: ``version_label`` (``legacy_version_label`` or ``v<n>``; SCREENS_B RPT-19),
  ``actor_names`` (display names; ``System`` for the SYSTEM principal) and ``rate_text`` (an exact
  unit rate with at least the currency's minor-unit decimals, never rounded; DS-FMT-25 machine
  value of a DS-FMT-13 cell).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Uuid, and_, literal, or_, select, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    legal_entity,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_history import default_dates
from erev_api.enums import ApprovalDecisionKind, ApprovalRequestStatus

START_AFTER_END: Final = "Start date must be on or before end date."
AS_OF_FUTURE: Final = "Enter a time that is not in the future."  # SCREENS_B RPT-24, RPT-25
PENDING: Final = ApprovalRequestStatus.PENDING.value
APPROVED: Final = ApprovalRequestStatus.APPROVED.value
APPROVING: Final = (ApprovalDecisionKind.APPROVE.value, ApprovalDecisionKind.AUTO_APPROVE.value)
JOINER: Final = ", "  # SCREENS_B "users joined with ', '"


def text(value: object) -> str | None:
    """The literal of an enum or text column value; None stays None."""
    return None if value is None else str(getattr(value, "value", value))


def uuid_of(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


# --- date ranges --------------------------------------------------------------------------------


def day(params: ReportParams, key: str) -> date | None:
    value = params.parameters.get(key)
    return None if value is None else date.fromisoformat(str(value))


def date_range(
    session: Session, params: ReportParams, *, year: bool = True, today: bool = False
) -> tuple[date, date]:
    """``from_date`` and ``to_date`` with the context defaults of SCREENS_B §5.6: the first day of
    the context fiscal year (``year``; else of the context period) and the end of the context
    period, or the run's day with ``today`` — the context being the period that holds the run's
    as-of date for the first entity of the run with such a period (``contract_history``'s rule); a
    defaulted start never follows a given end. 422 for a given start after its end."""
    given_from, given_to = day(params, "from_date"), day(params, "to_date")
    if given_from is not None and given_to is not None:
        if given_from > given_to:
            raise tie_outs.invalid("from_date", START_AFTER_END)
        return given_from, given_to
    first, last = default_dates(session, params, year=year)
    if today:
        last = params.known_at.astimezone(UTC).date()
    end = last if given_to is None else given_to
    start = min(first, end) if given_from is None else given_from
    if start > end:
        raise tie_outs.invalid("from_date", START_AFTER_END)
    return start, end


def instants(first: date, last: date) -> tuple[datetime, datetime]:
    """``[start, end)`` in UTC of the inclusive days ``first`` .. ``last``."""
    return (
        datetime.combine(first, time.min, tzinfo=UTC),
        datetime.combine(last + timedelta(days=1), time.min, tzinfo=UTC),
    )


def within(moment: datetime | None, bounds: tuple[datetime, datetime]) -> bool:
    """``moment`` lies in ``[start, end)``; None never does."""
    return moment is not None and bounds[0] <= moment < bounds[1]


def instant(params: ReportParams, key: str) -> datetime | None:
    """The RFC 3339 instant parameter ``key`` (validated at creation, T-RPT-01 rule 1); None when
    absent."""
    value = params.parameters.get(key)
    return None if value is None else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def as_of_instant(params: ReportParams) -> datetime:
    """``as_of`` of an access report (SCREENS_B RPT-24, RPT-25 "default now"): the given instant,
    else the run's ``known_at``; 422 for an instant after ``known_at``."""
    found = instant(params, "as_of")
    if found is None:
        return params.known_at
    if found > params.known_at:
        raise tie_outs.invalid("as_of", AS_OF_FUTURE)
    return found.astimezone(UTC)


# --- REGISTER-CUTOFF-1 --------------------------------------------------------------------------


def changed_after(
    rows: Iterable[Mapping[str, Any]], *, cutoff: datetime, historical: bool
) -> Mapping[str, Any] | None:
    """The first row whose ``updated_at`` follows the cutoff of an explicit historical read, else
    None; a live run (record basis) inspects nothing. Pure."""
    if not historical:
        return None
    for row in rows:
        if row["updated_at"] > cutoff:
            return row
    return None


# --- labels -------------------------------------------------------------------------------------


def version_label(legacy_version_label: object, version_no: object) -> str:
    """``legacy_version_label``, else ``v<n>`` (SCREENS_B RPT-19 ``version_label``)."""
    return f"v{int(str(version_no))}" if legacy_version_label is None else str(legacy_version_label)


def version_name(book_code: object, legacy_version_label: object, version_no: object) -> str:
    """``<book code> <version label>``: one SSP book version named outside its book's rows, as PRD
    §2.6 names them (``US-LIST 2026-H1``)."""
    return f"{book_code} {version_label(legacy_version_label, version_no)}"


def rate_text(value: Decimal | None, currency: str) -> str | None:
    """An exact unit value as text with at least the currency's minor-unit decimals and no
    trailing zeros beyond them; never rounded (the DS-FMT-13 cell's machine value, DS-FMT-25)."""
    if value is None:
        return None
    shown = format(Decimal(value), "f")
    whole, _, fraction = shown.partition(".")
    fraction = fraction.rstrip("0").ljust(tie_outs.minor_unit(currency), "0")
    if whole in ("-0", "") and not fraction.strip("0"):
        whole = "0"
    return f"{whole}.{fraction}" if fraction else whole


def ratio_text(value: Decimal | None) -> str | None:
    """An exact ratio at full precision without trailing zeros and without a negative zero."""
    if value is None:
        return None
    number = Decimal(value)
    if number == 0:
        return "0"
    shown = format(number, "f")
    return shown.rstrip("0").rstrip(".") if "." in shown else shown


def actor_names(actors: Sequence[tuple[UUID | None, str]], names: Mapping[UUID, str]) -> list[str]:
    """The display name of each (id, kind) in order; the SYSTEM principal reads ``System``."""
    return [
        str(approval_queries.actor(user_id, kind, names)["display_name"])
        for user_id, kind in actors
    ]


def joined(values: Sequence[str]) -> str | None:
    """Names joined with ", "; None for none (an empty cell, never an empty string)."""
    return JOINER.join(values) if values else None


# --- approvals ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Decision:
    """One T-PLT-20 decision with its step (T-PLT-18)."""

    id: UUID
    decision: str  # E-07
    approver_id: UUID | None
    approver_kind: str
    on_behalf_of_id: UUID | None
    step_no: int
    step_name: str
    decided_at: datetime
    comment: str | None
    subject_content_sha256: str
    auto_rule_id: UUID | None
    auto_rule_set_version_id: UUID | None

    @property
    def approving(self) -> bool:
        return self.decision in APPROVING


@dataclass(frozen=True, slots=True)
class Request:
    """One T-PLT-17 request as it stood at the record cutoff, with its decisions by the cutoff."""

    id: UUID
    request_no: str
    subject_type: str  # E-08
    subject_id: UUID
    status: str  # E-05 at the cutoff
    summary: str
    entity_id: UUID | None
    amount_functional: Decimal | None
    amount_currency: str | None
    flags: tuple[str, ...]
    preparer_id: UUID | None
    preparer_kind: str
    submitted_at: datetime
    decided_at: datetime | None  # the terminal decision, when by the cutoff
    comment: str | None
    subject_content_sha256: str
    decisions: tuple[Decision, ...]

    @property
    def preparer(self) -> tuple[UUID | None, str]:
        return self.preparer_id, self.preparer_kind

    @property
    def approvers(self) -> tuple[tuple[UUID | None, str], ...]:
        """The APPROVE and AUTO_APPROVE deciders in decision order."""
        return tuple(
            (item.approver_id, item.approver_kind) for item in self.decisions if item.approving
        )

    @property
    def approved_at(self) -> datetime | None:
        """The instant the request became APPROVED, when it was by the cutoff."""
        return self.decided_at if self.status == APPROVED else None

    def user_ids(self) -> list[UUID | None]:
        found: list[UUID | None] = [self.preparer_id]
        for item in self.decisions:
            found += [item.approver_id, item.on_behalf_of_id]
        return found


def status_at(row: Mapping[str, Any], cutoff: datetime) -> tuple[str, datetime | None]:
    """(E-05 status, terminal decision instant) of a request row as of ``cutoff``: the stored
    status once its ``decided_at`` or ``voided_at`` is by the cutoff, ``PENDING`` before. Pure."""
    decided, voided = row["decided_at"], row["voided_at"]
    if decided is not None and decided <= cutoff:
        return str(text(row["status"])), decided
    if voided is not None and voided <= cutoff:
        return str(text(row["status"])), None
    if decided is None and voided is None:
        return str(text(row["status"])), None
    return PENDING, None


def _names_every_entity(session: Session, entity_ids: Sequence[UUID], cutoff: datetime) -> bool:
    """Whether ``entity_ids`` are every legal entity the workspace had at ``cutoff`` — and it had
    one. The build reads under the tenant's scope, so the entities read here are all of them; an
    entity created after the cutoff does not count, so a rerun states what the run stated."""
    known = {
        UUID(str(value))
        for value in session.execute(
            select(legal_entity.c.id).where(legal_entity.c.created_at <= cutoff)
        ).scalars()
    }
    return bool(known) and known <= set(entity_ids)


def requests_in_scope(
    session: Session, params: ReportParams, *, cutoff: datetime
) -> ColumnElement[bool]:
    """The approval requests a register of the run's entities states (supervisor rulings R-28 and
    R-121 (c); 04 T-PLT-17 rev 1.104; 03 REQ-PLT-012): a request whose EVERY entity is among the
    run's — the one of ``entity_id``, each of ``entity_ids`` — and a tenant-level request, which
    names none. A request that spans every entity (``is_all_entities``) is stated only by a run
    that names every legal entity the workspace had at its cutoff.

    A register row is the content of a request — its summary, amount, flags and comments — and
    content is for a reader who covers every entity of the request (the approvals kernel's
    ``SubjectEntities.covered_by``). A run is read only within its reader's scope, so the run's
    entities stand for the reader's. Measured before item SCOPE-WORKSPACE-LISTS-1: the builders
    took a null ``entity_id`` for "tenant-wide", and since rev 1.104 a request of several
    entities or of all entities has one — a register of one entity stated the requests of the
    others."""
    ids = sorted(params.entity_ids, key=str)
    if _names_every_entity(session, ids, cutoff):
        return true()
    return and_(
        approval_request.c.is_all_entities.is_(False),
        or_(approval_request.c.entity_id.is_(None), approval_request.c.entity_id.in_(ids)),
        approval_request.c.entity_ids.contained_by(literal(ids, ARRAY(Uuid()))),
    )


def requests(
    session: Session, *, cutoff: datetime, where: Sequence[ColumnElement[bool]]
) -> list[Request]:
    """The requests matching ``where`` submitted by ``cutoff``, in (submitted, request number)
    order, each as it stood at the cutoff with its decisions by the cutoff."""
    rows = [
        dict(row)
        for row in session.execute(
            select(approval_request)
            .where(approval_request.c.submitted_at <= cutoff, *where)
            .order_by(approval_request.c.submitted_at, approval_request.c.request_no)
        ).mappings()
    ]
    if not rows:
        return []
    ids = [UUID(str(row["id"])) for row in rows]
    decisions: dict[UUID, list[Decision]] = {}
    statement = (
        select(
            approval_decision,
            approval_step.c.step_no.label("step_no"),
            approval_step.c.name.label("step_name"),
        )
        .select_from(
            approval_decision.join(
                approval_step,
                and_(
                    approval_step.c.tenant_id == approval_decision.c.tenant_id,
                    approval_step.c.id == approval_decision.c.approval_step_id,
                ),
            )
        )
        .where(
            approval_decision.c.approval_request_id.in_(ids),
            approval_decision.c.decided_at <= cutoff,
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    )
    for row in session.execute(statement).mappings():
        decisions.setdefault(UUID(str(row["approval_request_id"])), []).append(
            Decision(
                id=UUID(str(row["id"])),
                decision=str(text(row["decision"])),
                approver_id=uuid_of(row["approver_id"]),
                approver_kind=str(text(row["approver_kind"])),
                on_behalf_of_id=uuid_of(row["on_behalf_of_id"]),
                step_no=int(row["step_no"]),
                step_name=str(row["step_name"]),
                decided_at=row["decided_at"],
                comment=None if row["comment"] in (None, "") else str(row["comment"]),
                subject_content_sha256=str(row["subject_content_sha256"]),
                auto_rule_id=uuid_of(row["auto_rule_id"]),
                auto_rule_set_version_id=uuid_of(row["auto_rule_set_version_id"]),
            )
        )
    found: list[Request] = []
    for stored in rows:
        request_id = UUID(str(stored["id"]))
        status, decided_at = status_at(stored, cutoff)
        currency = stored["amount_currency"]
        found.append(
            Request(
                id=request_id,
                request_no=str(stored["request_no"]),
                subject_type=str(text(stored["subject_type"])),
                subject_id=UUID(str(stored["subject_id"])),
                status=status,
                summary=str(stored["summary"]),
                entity_id=uuid_of(stored["entity_id"]),
                amount_functional=(
                    None
                    if stored["amount_functional"] is None
                    else Decimal(stored["amount_functional"])
                ),
                amount_currency=None if currency is None else str(currency).strip(),
                flags=tuple(str(flag) for flag in stored["flags"] or ()),
                preparer_id=uuid_of(stored["preparer_id"]),
                preparer_kind=str(text(stored["preparer_kind"])),
                submitted_at=stored["submitted_at"],
                decided_at=decided_at,
                comment=None if stored["comment"] in (None, "") else str(stored["comment"]),
                subject_content_sha256=str(stored["subject_content_sha256"]),
                decisions=tuple(decisions.get(request_id, ())),
            )
        )
    return found


def requests_by_id(
    session: Session, ids: Iterable[UUID], *, cutoff: datetime
) -> dict[UUID, Request]:
    wanted = sorted({value for value in ids}, key=str)
    if not wanted:
        return {}
    found = requests(session, cutoff=cutoff, where=[approval_request.c.id.in_(wanted)])
    return {item.id: item for item in found}


def requests_of_subjects(
    session: Session, subject_type: str, subject_ids: Iterable[UUID], *, cutoff: datetime
) -> dict[UUID, list[Request]]:
    """Every request of each subject by the cutoff, in submission order."""
    wanted = sorted({value for value in subject_ids}, key=str)
    if not wanted:
        return {}
    found: dict[UUID, list[Request]] = {}
    for item in requests(
        session,
        cutoff=cutoff,
        where=[
            approval_request.c.subject_type == subject_type,
            approval_request.c.subject_id.in_(wanted),
        ],
    ):
        found.setdefault(item.subject_id, []).append(item)
    return found


def names_of(
    session: Session, found: Iterable[Request], extra: Iterable[UUID | None] = ()
) -> dict[UUID, str]:
    """Display names of every preparer, approver and delegator of ``found`` and of ``extra``."""
    ids: list[UUID | None] = list(extra)
    for item in found:
        ids += item.user_ids()
    return approval_queries.display_names(session, ids)


__all__ = [
    "APPROVED",
    "APPROVING",
    "AS_OF_FUTURE",
    "PENDING",
    "START_AFTER_END",
    "Decision",
    "Request",
    "actor_names",
    "as_of_instant",
    "changed_after",
    "date_range",
    "day",
    "instant",
    "instants",
    "joined",
    "names_of",
    "rate_text",
    "ratio_text",
    "requests",
    "requests_by_id",
    "requests_of_subjects",
    "status_at",
    "text",
    "uuid_of",
    "version_label",
    "version_name",
    "within",
]
