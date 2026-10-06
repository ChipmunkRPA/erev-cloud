"""The usage period of a report (04 §16.3 "The usage period of a report" and table 15.4-B
``USAGE_PERIOD_NOT_ENDED``, rev 1.320; PRD BR-REC-01, IMP-148; dev-guide DG-KRN-EVT-02 rev 1.296;
item USAGE-REPORT-PERIOD-ENDED-1).

Pure. ``events.usage_period_refusal`` is the rule — a usage report states usage that has occurred,
so its usage period ends on or before the report's date, the event's effective date — and
``events._period_finding`` its finding for an event as every channel hands it to
``events.check_bounds``. The database witnesses, through the route, the approval and the reports,
are in ``tests/domain/contracts/test_usage_report_period.py`` and
``tests/domain/reports/test_usage_report_figures_db.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from erev_api.domain.contracts import events
from erev_api.enums import ContractEventType
from erev_api.events.stream import EventIn
from erev_api.schemas.events import EventAppendItemIn

NEW_YORK = "America/New_York"
AUGUST_1 = date(2026, 8, 1)
AUGUST_24 = date(2026, 8, 24)
AUGUST_31 = date(2026, 8, 31)
SENTENCE = (
    "The usage period 01 Aug 2026 to 31 Aug 2026 ends after the report's date, 24 Aug 2026. A "
    "usage report states usage that has occurred: end the period on or before 24 Aug 2026."
)


def _usage(start: date, end: date, *, royalty: bool | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "obligation_key": "O1",
        "usage_period_start": start.isoformat(),
        "usage_period_end": end.isoformat(),
        "metric": "API_CALL",
        "quantity": "50000",
        "rated_amount": {"amount": "5000.00", "currency": "USD"},
    }
    if royalty is not None:
        payload["is_royalty_statement"] = royalty
    return payload


def _event(item: EventAppendItemIn, *, time_zone: str = NEW_YORK) -> EventIn:
    """The event as the route, a submission, a preview and an import row build it."""
    [event] = events.to_events([item], time_zone=time_zone, is_manual=False)
    return event


def _report(effective: date, start: date, end: date, *, royalty: bool | None = None) -> EventIn:
    return _event(
        EventAppendItemIn(
            event_type=ContractEventType.USAGE_REPORTED,
            effective_date=effective,
            payload=_usage(start, end, royalty=royalty),
        )
    )


def test_a_period_that_ends_after_the_reports_date_is_refused_by_name() -> None:
    """The report of the measurement on main: 1 to 31 August, dated 24 August. The finding stands
    at the payload's ``usage_period_end`` of the event's place in the request, under the rule id
    of table 15.4-B, with the sentence of PRD IMP-148 and its dates as copy prints them."""
    assert events.usage_period_refusal(AUGUST_1, AUGUST_31, AUGUST_24) == SENTENCE

    finding = events._period_finding(3, _report(AUGUST_24, AUGUST_1, AUGUST_31))

    assert finding is not None
    assert (finding.field, finding.rule_id, finding.message) == (
        "events.3.payload.usage_period_end",
        "USAGE_PERIOD_NOT_ENDED",
        SENTENCE,
    )


@pytest.mark.parametrize(
    "end",
    [AUGUST_24, date(2026, 8, 23), AUGUST_1],
    ids=["the report's date", "the day before", "one day"],
)
def test_a_period_that_has_ended_by_the_reports_date_passes(end: date) -> None:
    """Equal dates are accepted — the engine realises a fee at ``usage_period_end <= d_v`` — and
    so is every earlier end: a report dated after its period's end is taken as before."""
    assert events.usage_period_refusal(AUGUST_1, end, AUGUST_24) is None
    assert events._period_finding(0, _report(AUGUST_24, AUGUST_1, end)) is None


def test_the_day_after_the_reports_date_is_refused() -> None:
    """The bound is the date itself: a period that ends one day after the report's date is one
    that has not ended."""
    message = events.usage_period_refusal(AUGUST_1, date(2026, 8, 25), AUGUST_24)

    assert message is not None
    assert message.startswith("The usage period 01 Aug 2026 to 25 Aug 2026 ends after")
    assert events._period_finding(0, _report(AUGUST_24, AUGUST_1, date(2026, 8, 25))) is not None


@pytest.mark.parametrize("royalty", [True, False])
def test_a_royalty_statement_is_held_alike(royalty: bool) -> None:
    """One payload serves the usage report and the royalty statement (``is_royalty_statement``):
    the same finding with the same sentence, and the same pass for a period that has ended."""
    finding = events._period_finding(0, _report(AUGUST_24, AUGUST_1, AUGUST_31, royalty=royalty))

    assert finding is not None
    assert (finding.rule_id, finding.message) == ("USAGE_PERIOD_NOT_ENDED", SENTENCE)
    ended = _report(AUGUST_24, AUGUST_1, AUGUST_24, royalty=royalty)
    assert events._period_finding(0, ended) is None


def test_an_instant_is_held_in_the_contracting_entitys_date() -> None:
    """``effective_at`` becomes the date in the contracting entity's zone once (TZ-03), and that
    date is the report's: 25 August 01:30 UTC is 24 August in New York, where a period to 25
    August has not ended, and 25 August in London, where it has."""
    item = EventAppendItemIn(
        event_type=ContractEventType.USAGE_REPORTED,
        effective_at=datetime(2026, 8, 25, 1, 30, tzinfo=UTC),
        payload=_usage(AUGUST_1, date(2026, 8, 25)),
    )

    in_new_york = _event(item)
    in_london = _event(item, time_zone="Europe/London")

    assert (in_new_york.effective_date, in_london.effective_date) == (AUGUST_24, date(2026, 8, 25))
    finding = events._period_finding(0, in_new_york)
    assert finding is not None
    assert finding.message == (
        "The usage period 01 Aug 2026 to 25 Aug 2026 ends after the report's date, 24 Aug 2026. "
        "A usage report states usage that has occurred: end the period on or before 24 Aug 2026."
    )
    assert events._period_finding(0, in_london) is None


def test_no_other_event_type_is_held_to_it() -> None:
    """A usage period is a member of ``USAGE_REPORTED`` alone: a delivery has no finding of the
    kind, whatever its date."""
    delivery = _event(
        EventAppendItemIn(
            event_type=ContractEventType.DELIVERY_RECORDED,
            effective_date=AUGUST_24,
            payload={"obligation_key": "O1", "quantity": "10", "trigger": "DELIVERY"},
        )
    )

    assert events._period_finding(0, delivery) is None
