"""Invitation lookup failures (04 T-PLT-07 rev 1.38, E-79 ``INVITATION_LOOKUP_FAILED``; D-98
candidate 20 from the P4c SOP-7 audit; BUILD_SPEC WEB-13).

DB-free: the token well-formedness rule, the failure classification of a membership row and the
refusal type that carries the reason to the recorder. The recorder itself and the route behaviour
are covered by ``tests/api/test_invitations.py`` against a lane database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from erev_api.auth import invitations
from erev_api.enums import AuditOutcome, MembershipStatus, SecurityEventKind, UserStatus
from erev_api.problems import Problem

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
WELL_FORMED = "A" * 43


def test_well_formed_token_is_43_url_safe_characters() -> None:
    assert invitations.well_formed_token(WELL_FORMED)
    assert invitations.well_formed_token("abcDEF0123456789-_" + "x" * 25)
    assert not invitations.well_formed_token("")
    assert not invitations.well_formed_token("A" * 42)
    assert not invitations.well_formed_token("A" * 44)
    assert not invitations.well_formed_token("A" * 42 + "=")
    assert not invitations.well_formed_token("A" * 42 + " ")
    assert not invitations.well_formed_token("A" * 42 + "é")


@pytest.mark.parametrize(
    ("status", "expires_at", "user_status", "reason"),
    [
        (MembershipStatus.INVITED, NOW + timedelta(days=1), UserStatus.ACTIVE, None),
        (MembershipStatus.INVITED, NOW, UserStatus.ACTIVE, "expired"),
        (MembershipStatus.INVITED, NOW - timedelta(seconds=1), UserStatus.ACTIVE, "expired"),
        (MembershipStatus.ACTIVE, NOW + timedelta(days=1), UserStatus.ACTIVE, "used"),
        (MembershipStatus.SUSPENDED, NOW + timedelta(days=1), UserStatus.ACTIVE, "used"),
        (MembershipStatus.REMOVED, NOW - timedelta(days=1), UserStatus.ACTIVE, "used"),
        (MembershipStatus.INVITED, NOW + timedelta(days=1), UserStatus.DISABLED, "inactive"),
        (MembershipStatus.INVITED, NOW + timedelta(days=1), None, None),
    ],
)
def test_failure_reason_of_a_matching_membership(
    status: MembershipStatus,
    expires_at: datetime,
    user_status: UserStatus | None,
    reason: str | None,
) -> None:
    assert (
        invitations.failure_reason(
            membership_status=status, expires_at=expires_at, user_status=user_status, now=NOW
        )
        == reason
    )


def test_refusal_is_a_not_found_problem_that_names_its_reason() -> None:
    refusal = invitations.InvitationRefused("expired")
    assert isinstance(refusal, Problem)
    assert refusal.slug == "not-found"
    assert refusal.reason == "expired"
    with pytest.raises(ValueError):
        invitations.InvitationRefused("guessed")  # type: ignore[arg-type]


def test_failure_event_fields_are_anonymous_and_name_the_reason_and_route() -> None:
    fields = invitations.failure_event_fields("malformed", route="lookup")
    assert fields == {
        "kind": SecurityEventKind.INVITATION_LOOKUP_FAILED,
        "outcome": AuditOutcome.FAILED,
        "user_id": None,
        "detail": {"reason": "malformed", "route": "lookup"},
    }
    assert invitations.failure_event_fields("used", route="accept")["detail"] == {
        "reason": "used",
        "route": "accept",
    }
    assert invitations.FAILURE_REASONS == ("malformed", "unknown", "expired", "used", "inactive")
