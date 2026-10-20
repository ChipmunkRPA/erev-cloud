"""Item cutoffs preserve the difference between requesting and completing revocation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_access_reviews import item_at
from erev_api.problems import Problem

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def row(**changes: object) -> dict:
    return {
        "id": UUID(int=1),
        "membership_id": UUID(int=2),
        "user_email_snapshot": "review@example.test",
        "roles_snapshot": [],
        "last_login_at": None,
        "decision": "REVOKED",
        "reviewer_id": UUID(int=3),
        "created_at": NOW - timedelta(days=1),
        "decided_at": NOW,
        "comment": "Remove access.",
        "revocation_completed_at": NOW + timedelta(seconds=5),
        **changes,
    }


def test_cutoffs_hide_later_reviewers_comments_and_revocation() -> None:
    for offset, expected in (
        (-1, "PENDING"),
        (0, "REVOKE_REQUESTED"),
        (4, "REVOKE_REQUESTED"),
        (5, "REVOKED"),
    ):
        item = item_at(row(), NOW + timedelta(seconds=offset))
        assert item["decision"] == expected
        assert (item["reviewer_id"] is None) == (expected == "PENDING")
        assert (item["comment"] is None) == (expected == "PENDING")
        assert (item["revocation_completed_at"] is not None) == (expected == "REVOKED")


@pytest.mark.parametrize(
    "changes",
    [
        {"revocation_completed_at": None},
        {"revocation_completed_at": NOW - timedelta(seconds=1)},
        {"decision": "CERTIFIED"},
        {"reviewer_id": None},
        {"decided_at": NOW - timedelta(days=2)},
        {"decision": "PENDING", "decided_at": None},
    ],
)
def test_inconsistent_current_state_is_not_used_as_historical_evidence(changes: dict) -> None:
    with pytest.raises(Problem):
        item_at(row(**changes), NOW)
