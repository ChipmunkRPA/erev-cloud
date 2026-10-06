"""Report figures at an as-of date (ENGINE_SPEC_B S15-R-01, S15-R-08 and S15-R-12, rev 1.127; 04
API-C-10; item RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c)).

A contract version stores an obligation's revenue and the two parts of its remainder — scheduled
and awaiting trigger — at the version's effective date d_v. A computation recognises revenue past
d_v, through every open period, so a report that added the stored awaiting-trigger amount to the
revenue posted since stated the same amount twice: the remaining performance obligation of a
usage obligation dated nine periods back read 79,780.82 for a remainder of 20,164.38.

A report that states an obligation at a date reads it where the contract reads do
(``domain.contracts.to_date``): the period nodes of the version's trace, the same refusal by name
for a measure the trace cannot answer, the same rule for the part of the remainder a movement
leaves (04 API-C-10, the remainder at the cut). ``load`` reads the versions of a run once, for the
dates the run states: a report holds every version of its entities, so of each trace only the
period nodes a read at those dates reaches are kept (``to_date.load_nodes(..., days=...)``), and
the versions are read in portions. ``Versions.at`` and ``Versions.balance`` state an obligation
and a member's balances at one of those dates; ``obligations_at`` is the read for the versions
and dates of a run; ``scheduled_after`` holds the one rule the reports add:

- an obligation whose remainder at the date has a scheduled part states that part by period, as
  the ``REVENUE`` schedule lines of its version for the periods after the period it was read at,
  and those lines are that part — a version whose lines do not add up to it is refused by name;
- an obligation without a scheduled part states no scheduled amount: the later lines of its
  version are amounts it recognises by events or by a transfer still to come, and at the date
  they are inside its awaiting-trigger amount.

So at every date recognised to the date + scheduled + awaiting trigger is the obligation's
allocation (S15-R-02), and its remaining performance obligation is scheduled + awaiting trigger
(S15-R-08).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_version, obligation_version
from erev_api.domain.contracts import to_date
from erev_api.problems import Problem, ProblemError

__all__ = ["RULE", "ScheduleUnreadable", "Versions", "load", "obligations_at", "scheduled_after"]

RULE: Final = "S15-R-01"
ZERO: Final = Decimal(0)
NOT_LOADED: Final = "the versions were loaded for {loaded}, not for {day}"
SCHEDULE_DIFFERS: Final = (
    "Contract {contract}, obligation {obligation}: at {day} the scheduled amount read from the "
    "calculation trace of the contract version is {scheduled}, and the version's revenue schedule "
    "places {lines} in later periods. Nothing is reported in place of either."
)

# (schedule line id, the end of its period, its amount)
type Line = tuple[UUID, date, Decimal]


class ScheduleUnreadable(Problem):
    """ENGINE_SPEC_B S15-R-01 (rev 1.127): the scheduled part of an obligation's remainder at a
    date and the schedule lines of the later periods are one amount. A version in which they
    differ is refused by name — 422 ``validation-failed`` naming the contract, the obligation,
    the date and both amounts — and no report states one of them."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            "validation-failed",
            "1 field needs attention.",
            errors=[ProblemError(field=field, rule_id=RULE, message=message)],
        )


@dataclass(frozen=True, slots=True)
class Versions:
    """The contract versions of a run as the reader takes them: each version's number, every
    obligation version of it — the group's whole, since a version's figures are the group's —,
    the external id of each member contract the run's reader sees, and the period nodes of the
    version's trace that a read at one of ``days`` reaches. A read at another date is a mistake
    of the caller and raises ``ValueError``: the nodes it would need were not kept."""

    versions: Mapping[UUID, Mapping[str, Any]]
    obligations: Mapping[UUID, Sequence[Mapping[str, Any]]]
    external_ids: Mapping[UUID, str]
    nodes: Mapping[UUID, to_date.Nodes]
    days: frozenset[date] = frozenset()

    def _loaded(self, day: date) -> None:
        if day not in self.days:
            loaded = ", ".join(sorted(item.isoformat() for item in self.days)) or "no date"
            raise ValueError(NOT_LOADED.format(loaded=loaded, day=day))

    def at(self, version_id: UUID, day: date) -> Mapping[UUID, to_date.ObligationAt]:
        """Obligation-version row id → the obligation at the cut of ``day``.
        ``to_date.Unreadable`` when the version's trace cannot answer."""
        self._loaded(day)
        return to_date.version_at(
            self.versions[version_id],
            self.obligations[version_id],
            nodes=self.nodes.get(version_id, to_date.EMPTY),
            external_ids=self.external_ids,
            as_of=day,
        ).obligations

    def balance(self, row: Mapping[str, Any], day: date) -> to_date.BalanceAt:
        """The labelled balances of one T-CON-09 row — with its entity's code as ``entity_code``
        — at the cut of ``day`` (the versions were loaded with their balance nodes).
        ``to_date.Unreadable`` or ``tie_outs.BalanceUnreadable`` when the trace cannot answer."""
        self._loaded(day)
        version_id = UUID(str(row["contract_version_id"]))
        return to_date.balance_at(
            row,
            version=self.versions[version_id],
            nodes=self.nodes.get(version_id, to_date.EMPTY),
            external_id=self.external_ids[UUID(str(row["contract_id"]))],
            moved=ZERO,  # the net position is not a labelled balance (D-12); no report reads it
            as_of=day,
        )


def load(
    session: Session,
    version_ids: Collection[UUID],
    days: Collection[date],
    *,
    balances: bool = False,
) -> Versions:
    """What the reader needs of ``version_ids`` to state them at ``days``: the versions, their
    obligation versions, the member contracts' external ids and the period nodes those dates
    reach (with the member-balance nodes when ``balances``)."""
    wanted = sorted(set(version_ids), key=str)
    loaded = frozenset(days)
    if not wanted:
        return Versions({}, {}, {}, {}, loaded)
    versions = {
        UUID(str(row["id"])): dict(row)
        for row in session.execute(
            select(contract_version.c.id, contract_version.c.version_no).where(
                contract_version.c.id.in_(wanted)
            )
        ).mappings()
    }
    rows: dict[UUID, list[dict[str, Any]]] = {version_id: [] for version_id in wanted}
    statement = (
        select(obligation_version)
        .where(obligation_version.c.contract_version_id.in_(wanted))
        .order_by(obligation_version.c.contract_version_id, obligation_version.c.id)
    )
    for row in session.execute(statement).mappings():
        rows[UUID(str(row["contract_version_id"]))].append(dict(row))
    contract_ids = sorted({row["contract_id"] for found in rows.values() for row in found}, key=str)
    external_ids: dict[UUID, str] = {}
    if contract_ids:
        # A member contract of an entity outside the reader's scope is not in this answer; the
        # reader then finds the obligation's subject in a bound node (04 API-C-10, R-85 (c)).
        named = select(contract.c.id, contract.c.external_id).where(contract.c.id.in_(contract_ids))
        external_ids = {
            UUID(str(row["id"])): str(row["external_id"])
            for row in session.execute(named).mappings()
        }
    return Versions(
        versions=versions,
        obligations=rows,
        external_ids=external_ids,
        nodes=to_date.load_nodes(session, wanted, balances=balances, days=loaded),
        days=loaded,
    )


def obligations_at(
    session: Session, wanted: Mapping[UUID, Collection[date]]
) -> dict[tuple[UUID, date], Mapping[UUID, to_date.ObligationAt]]:
    """Each obligation of the contract versions of ``wanted`` at each of the version's dates:
    (version id, date) → obligation-version row id → the obligation at the cut of that date.
    ``to_date.Unreadable`` when a trace cannot answer."""
    found = load(
        session,
        [version_id for version_id, days in wanted.items() if days],
        {day for days in wanted.values() for day in days},
    )
    return {
        (version_id, day): found.at(version_id, day)
        for version_id in found.versions
        for day in sorted(set(wanted[version_id]))
    }


def scheduled_after(
    lines: Sequence[Line],
    at: to_date.ObligationAt,
    day: date,
    *,
    contract: str,
    obligation: str,
) -> tuple[Line, ...]:
    """The schedule lines that state the scheduled part of an obligation's remainder at ``day``:
    the lines of the periods ending after the cut when the remainder has a scheduled part, none
    otherwise (module docstring). The cut is the end of the period the obligation was read at
    (``at.measured``; 04 API-C-10) — the period that holds ``day`` in the obligation's own
    periods, so a date inside a period counts that period as read, and not later than the
    version's horizon, so a date beyond the last period a version measures answers at that
    period and the lines between the two are still scheduled. Before the first period the version
    measures the cut is ``day`` itself. ``lines`` are every ``REVENUE`` line of the obligation in
    its version.
    ``ScheduleUnreadable`` when the later lines do not add up to the scheduled part."""
    if at.scheduled == 0:
        return ()
    cut = day if at.measured is None else at.measured.end_date
    later = tuple(line for line in lines if line[1] > cut)
    placed = sum((amount for _, _, amount in later), ZERO)
    if placed != at.scheduled:
        message = SCHEDULE_DIFFERS.format(
            contract=contract, obligation=obligation, day=cut, scheduled=at.scheduled, lines=placed
        )
        raise ScheduleUnreadable(f"obligations[{obligation}].scheduled_amount", message)
    return later
