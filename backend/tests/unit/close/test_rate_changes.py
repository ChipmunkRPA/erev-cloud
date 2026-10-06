"""A rate changed after a lock, without a database (item CLO-RATE-AFTER-RUN-1, second part; the
supervisor's rulings of 2026-10-02 08:56 and 11:08; 04 T-REF-11 "A rate changed after a lock" rev
1.291; PRD IMP-144): the statements of ``close.rate_changes`` and its message as rules. The
database witnesses are ``tests/domain/close/test_rate_changed_after_lock.py``.

- What a version changes is THE admission of a rate, read twice in one statement: with the
  version and as if it did not exist, with no time bound.
- The period states are read ``FOR SHARE`` in the governed order, ``future`` rows left alone.
- A version that changes nothing costs one statement and holds no row.
- The message names the period, the version, the first rate and the roads the states leave.
- The approval of a version fails while no hook is registered; the reference commands register it;
  a version is decided by a person, never by a rule.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import routing, subjects
from erev_api.domain.close import rate_changes
from erev_api.domain.contracts import bundles
from erev_api.domain.reference import commands as reference_commands
from erev_api.enums import ApprovalSubjectType
from sqlalchemy.dialects import postgresql

VERSION = UUID(int=7)
REQUEST = UUID(int=8)
CUTOFF = datetime(2026, 9, 3, 14, 0, tzinfo=UTC)
PUBLISHED = " AND erev.fx_rate_set_version.published_at <= %(published_at_1)s"
PUBLISHED_LATER = " AND later_version.published_at <= %(published_at_2)s"


def _sql(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


# --- the admission, whenever published and without a version -------------------------------------


def test_without_a_cutoff_the_admission_drops_its_two_time_conditions_and_nothing_else() -> None:
    """``fx_rates_in_force(None)``: every APPROVED or SUPERSEDED version counts, as candidate and
    as the higher version that answers instead. Word for word the bounded statement less the two
    ``published_at`` conditions."""
    bounded = _sql(bundles.fx_rates_in_force(CUTOFF))
    assert bounded.count(".published_at <= ") == 2
    assert PUBLISHED in bounded and PUBLISHED_LATER in bounded
    unbounded = _sql(bundles.fx_rates_in_force(None))
    assert "published_at" not in unbounded
    assert unbounded == bounded.replace(PUBLISHED, "").replace(PUBLISHED_LATER, "")


def test_without_a_version_the_admission_leaves_it_out_as_candidate_and_as_superseder() -> None:
    """``without``: the same rows as if the version did not exist — two conditions, one on the
    version a rate comes from and one on the higher version that would answer instead."""
    unbounded = _sql(bundles.fx_rates_in_force(None))
    without = _sql(bundles.fx_rates_in_force(None, without=VERSION))
    candidate = " AND erev.fx_rate_set_version.id != %(id_1)s::UUID"
    superseder = " AND later_version.id != %(id_2)s::UUID"
    assert candidate in without and superseder in without
    assert without.replace(candidate, "").replace(superseder, "") == unbounded
    compiled = bundles.fx_rates_in_force(None, without=VERSION).compile(
        dialect=postgresql.dialect()
    )
    assert [compiled.params["id_1"], compiled.params["id_2"]] == [VERSION, VERSION]


def test_what_a_version_changes_is_the_admission_with_it_against_the_admission_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One statement, both sides through ``bundles.fx_rates_in_force`` with no time bound — the
    side without the version is what was in force before its approval — narrowed to the version's
    set, full-joined on set, pair and date, where the two values are distinct: a rate that
    differs, one that appears and one that disappears."""
    calls: list[tuple[Any, Any]] = []
    admission = bundles.fx_rates_in_force

    def spied(known_at: Any, *, without: Any = None) -> Any:
        calls.append((known_at, without))
        return admission(known_at, without=without)

    monkeypatch.setattr(bundles, "fx_rates_in_force", spied)
    text = _sql(rate_changes.changes_statement(VERSION))
    assert calls == [(None, None), (None, VERSION)]
    assert text.count("AS rates_after") == 1 and text.count("AS rates_before") == 1
    assert ") AS rates_after FULL OUTER JOIN (" in text
    assert text.endswith(
        ") AS rates_before ON rates_before.code = rates_after.code"
        " AND rates_before.base_currency = rates_after.base_currency"
        " AND rates_before.quote_currency = rates_after.quote_currency"
        " AND rates_before.effective_date = rates_after.effective_date"
        " WHERE rates_before.rate IS DISTINCT FROM rates_after.rate"
    )
    of_the_set = (
        "erev.fx_rate_set.id = (SELECT approved_version.fx_rate_set_id"
        " FROM erev.fx_rate_set_version AS approved_version WHERE approved_version.id = "
    )
    assert text.count(of_the_set) == 2  # each side reads the version's set alone


def test_the_span_is_one_row_over_the_changes() -> None:
    text = _sql(rate_changes.span_statement(VERSION))
    assert text.startswith(
        "SELECT min(changed.effective_date) AS min_1, max(changed.effective_date) AS max_1,"
        " count(*) AS count_1 FROM ("
    )
    assert text.endswith(") AS changed")


# --- the period states ----------------------------------------------------------------------------


def test_the_states_are_read_for_share_in_the_governed_order_and_future_rows_are_left() -> None:
    """dev-guide DG-KRN-DB-08 (1c): one statement, period start then state id, ``FOR SHARE`` of
    the state rows alone. A ``future`` row is not taken: a lock decision takes the next period's
    ``future`` row ``NOWAIT`` and would be refused by an approval in flight."""
    statement = rate_changes.states_statement(date(2026, 8, 31))
    text = _sql(statement)
    assert text.endswith(
        " WHERE erev.period_state.period_end_date >= %(period_end_date_1)s"
        " AND erev.period_state.state != %(state_1)s"
        " ORDER BY erev.period.start_date, erev.period_state.id"
        " FOR SHARE OF period_state"
    )
    params = statement.compile(dialect=postgresql.dialect()).params
    assert (params["period_end_date_1"], params["state_1"]) == (date(2026, 8, 31), "future")
    assert "NOWAIT" not in text and "SKIP LOCKED" not in text  # a decision in flight is waited for


class _Session:
    """A session that answers the span and records what it is asked."""

    def __init__(self, span: tuple[Any, Any, int]) -> None:
        self.span = span
        self.statements: list[str] = []

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.statements.append(_sql(statement))
        span = self.span
        return type("R", (), {"one": lambda self: span, "all": lambda self: []})()


class _Uow:
    def __init__(self, session: _Session) -> None:
        self.session = session


def test_a_version_that_changes_nothing_costs_one_statement_and_holds_no_row() -> None:
    session = _Session((None, None, 0))
    assert rate_changes.approved(_Uow(session), VERSION, REQUEST) == ()  # type: ignore[arg-type]
    (only,) = session.statements
    assert only.startswith("SELECT min(changed.effective_date)") and "FOR SHARE" not in only


def test_a_version_that_changes_a_rate_reads_the_states_from_the_first_changed_date() -> None:
    """With no state that is closed in the span, nothing more is read: the common case of a
    version that brings the rates of a period still open."""
    session = _Session((date(2026, 9, 1), date(2026, 9, 30), 60))
    assert rate_changes.approved(_Uow(session), VERSION, REQUEST) == ()  # type: ignore[arg-type]
    span, states = session.statements
    assert span.startswith("SELECT min(changed.effective_date)")
    assert states.endswith("FOR SHARE OF period_state")


# --- the message ----------------------------------------------------------------------------------


def _change(
    before: str | None, after: str | None, *, on: date = date(2026, 8, 31), base: str = "EUR"
) -> rate_changes.RateChange:
    return rate_changes.RateChange(
        set_code="AVM-RATES-CLOSING",
        rate_type="closing",
        base_currency=base,
        quote_currency="USD",
        effective_date=on,
        before=None if before is None else Decimal(before),
        after=None if after is None else Decimal(after),
    )


def _message(changes: list[rate_changes.RateChange], **named: Any) -> str:
    members: dict[str, Any] = {
        "period_key": "FY2026-P08",
        "state": "closed",
        "later": [],
        "entity_code": "AVM-US",
        "book_code": "ASC606",
        "version_no": 2,
        "posting_period_key": "FY2026-P09",
    }
    return rate_changes.message(changes=changes, **{**members, **named})


POSTED = (
    " The difference is not computed here. What remains of it to post goes to FY2026-P09. The "
    "contracts the changed rates reach are recalculated by the next close run of their "
    "contracting entity or by the next change to them: what the rates change in the amounts of "
    "their events is posted with the closed period of each event as origin period, and the "
    "out-of-period register lists it as Fx republish or with the event that carried it. The close "
    "run of FY2026-P09 posts what remains of a period-end remeasurement as an amount of that "
    "period, without an origin period. Where nothing remains nothing is posted: a closing rate of "
    "a period that is followed by another closed period moves an amount between the two for a "
    "balance open through both."
)


def test_the_message_names_the_period_the_version_the_rate_and_where_the_difference_posts() -> None:
    assert _message([_change("1.105000000000", "1.115000000000")]) == (
        "FY2026-P08 is closed for AVM-US in book ASC606. The approval of version 2 of rate set "
        "AVM-RATES-CLOSING changed 1 exchange rate dated in it: EUR/USD closing rate of "
        "2026-08-31 from 1.105 to 1.115. Reopen the period to restate it, or request a waiver "
        "to accept the difference." + POSTED
    )


def test_the_message_counts_the_other_rates_and_names_a_rate_that_appears_or_disappears() -> None:
    several = [
        _change(None, "1.2", on=date(2026, 8, 3)),
        _change("1.1", None, on=date(2026, 8, 4)),
        _change("110", "112.5", on=date(2026, 8, 5), base="JPY"),
    ]
    text = _message(several)
    assert (
        "changed 3 exchange rates dated in it: EUR/USD closing rate of 2026-08-03, 1.2 where "
        "there was none, and 2 more. " in text
    )
    assert "EUR/USD closing rate of 2026-08-04, none where it was 1.1" in _message(several[1:])
    assert "JPY/USD closing rate of 2026-08-05 from 110 to 112.5." in _message(several[2:])
    with pytest.raises(ValueError, match="without a changed rate"):
        _message([])
    with pytest.raises(ValueError, match="neither with nor without"):
        _message([_change(None, None)])


def test_the_roads_are_the_ones_the_states_leave() -> None:
    """PRD BR-CLS-05: a period is not reopened while a later period of its entity and book is
    closed or permanently locked, and a permanent lock is never reopened."""
    closed, permanent = "closed", "permanently_locked"
    assert rate_changes.roads(closed, []) == rate_changes.REOPEN_OR_ACCEPT
    assert rate_changes.roads(closed, [closed, closed]) == rate_changes.LATER_FIRST_OR_ACCEPT
    assert rate_changes.roads(closed, [closed, permanent]) == rate_changes.ACCEPT_ONLY
    assert rate_changes.roads(permanent, []) == rate_changes.ACCEPT_ONLY
    text = _message([_change("1.1", "1.2")], state=permanent, posting_period_key=None)
    assert text.startswith("FY2026-P08 is permanently locked for AVM-US in book ASC606. ")
    assert text.endswith(
        " The period cannot be reopened. Request a waiver to accept the difference."
        + POSTED.replace("FY2026-P09", "the next period to open")
    )
    later = _message([_change("1.1", "1.2")], later=[closed])
    assert (
        " To restate it, reopen the later closed periods first and then this one; or request a "
        "waiver to accept the difference. " in later
    )


# --- the hook of the approval ---------------------------------------------------------------------


def test_the_reference_commands_register_the_hook() -> None:
    """Every version is submitted through ``reference.commands``: a process that can decide a
    version has loaded them, and with them the hook."""
    assert reference_commands.rate_changes is rate_changes
    assert rate_changes.approved in subjects.FX_RATE_VERSION_APPROVED
    before = list(subjects.FX_RATE_VERSION_APPROVED)
    subjects.register_fx_rate_version_approved(rate_changes.approved)
    assert before == subjects.FX_RATE_VERSION_APPROVED  # registering again changes nothing


def test_a_rate_set_version_is_no_subject_of_an_automatic_approval() -> None:
    """dev-guide DG-KRN-DB-08 (1a): the hook takes the period states after the approval's own rows
    and before any series. ``approvals.submit`` takes the ``APPROVAL`` series before it runs the
    hook of a submission that a rule approves, so the hook's place rests on a version being
    decided by a person, in ``decide``."""
    kind = ApprovalSubjectType.FX_RATE_SET_VERSION
    assert kind not in routing.AUTO_APPROVABLE and kind not in routing.SEEDED_RULE_SETS


class _Approving:
    """The session of an approval: the version is SUBMITTED, and the update is accepted."""

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        return type("R", (), {"scalar_one_or_none": lambda self: "SUBMITTED"})()


class _Decision:
    def __init__(self) -> None:
        self.session = _Approving()
        self.now = CUTOFF
        self.principal = type("P", (), {"id": UUID(int=3), "kind": type("K", (), {"value": "U"})})
        self.audited: list[Any] = []

    def audit(self, **event: Any) -> None:
        self.audited.append(event)


def test_a_version_is_not_approved_while_no_hook_is_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XR-12: a version that changes a rate of a closed period is never in force without its
    finding, so a decision in a process that registered no hook rolls back."""
    monkeypatch.setattr(subjects, "FX_RATE_VERSION_APPROVED", [])
    with pytest.raises(LookupError, match="no registered hook"):
        subjects._approve_fx_rate_set_version(_Decision(), VERSION, REQUEST)  # type: ignore[arg-type]
    called: list[tuple[UUID, UUID]] = []
    monkeypatch.setattr(
        subjects,
        "FX_RATE_VERSION_APPROVED",
        [lambda uow, version_id, request_id: called.append((version_id, request_id))],
    )
    decision = _Decision()
    subjects._approve_fx_rate_set_version(decision, VERSION, REQUEST)  # type: ignore[arg-type]
    assert called == [(VERSION, REQUEST)]
    assert [event["action"] for event in decision.audited] == ["fx_rate_set_version.approve"]
