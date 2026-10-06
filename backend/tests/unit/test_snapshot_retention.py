"""The copy of the unset-retention refusal (BUILD_SPEC SNP-5; PRD ERR-77;
``domain.platform.snapshot_retention``): it says from when copies are possible. Pure: the wording
of the two forms. What the registry answers — a confirmed version ahead of ``known_at``, or
none — is witnessed in ``tests/domain/platform/test_snapshots.py`` and, through the failed job a
person reads, in ``tests/api/test_tenant_snapshots.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from erev_api.domain.platform import snapshot_retention as sr


def test_a_confirmed_policy_that_is_not_in_force_yet_names_its_instant() -> None:
    approved = datetime(2026, 9, 12, 16, 5, tzinfo=UTC)
    effective = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    assert sr.copy((approved, effective)) == (
        "Sandbox copies are possible from 15 Sep 2026 12:00 UTC: the snapshot retention policy "
        "approved on 12 Sep 2026 takes effect then."
    )
    # both instants are worded in UTC whatever offset they carry
    tokyo = timezone(timedelta(hours=9))
    assert sr.copy((approved.astimezone(tokyo), effective.astimezone(tokyo))) == sr.copy(
        (approved, effective)
    )
    # an approval late in the UTC day stays on its UTC date
    late = datetime(2026, 9, 12, 23, 59, tzinfo=UTC)
    assert "approved on 12 Sep 2026" in sr.copy((late, effective))


def test_no_confirmed_policy_says_who_sets_and_who_approves_it() -> None:
    assert sr.copy(None) == (
        "No snapshot retention policy is confirmed yet. A Tenant Admin sets the retention "
        "families and a second person approves them; sandbox copies are possible from the time "
        "the approved policy takes effect."
    )


def test_neither_form_names_a_screen_or_leaves_a_placeholder() -> None:
    """No screen sets the retention families yet (item SBX-RETENTION-UI-1), so the copy names no
    place in the product; and a formatted sentence holds no brace."""
    now = datetime(2026, 9, 12, 12, tzinfo=UTC)
    for text in (sr.copy(None), sr.copy((now, now + timedelta(days=3)))):
        assert "Settings" not in text and "Policies" not in text
        assert "{" not in text and "}" not in text


def test_the_refusal_is_named_and_carries_its_copy_twice() -> None:
    """412 ``precondition-failed`` with ``errors[].rule_id`` ``RETENTION_UNSET`` (PRD ERR-77, a
    convention row): the sentence is the problem's detail and the message of its one error."""
    for found in (
        None,
        (datetime(2026, 9, 12, 12, tzinfo=UTC), datetime(2026, 9, 15, 12, tzinfo=UTC)),
    ):
        problem = sr.refusal(found)
        assert (problem.slug, problem.status) == ("precondition-failed", 412)
        assert problem.detail == sr.copy(found)
        assert [(error.field, error.rule_id, error.message) for error in problem.errors] == [
            (None, "RETENTION_UNSET", sr.copy(found))
        ]
