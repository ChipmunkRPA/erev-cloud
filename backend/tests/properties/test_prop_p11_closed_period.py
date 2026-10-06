"""P11 closed-period immutability (dev-guide §9.7 row P11; BUILD_SPEC PRP-6; ENGINE_SPEC S08-R-08 to
S08-R-10; ENGINE_SPEC_B §14.2.2 S14-R-05, S14-R-06, §14.4 S14-INV-03; 04 DB-07; D-19).

Engine part in memory (``support.platform_props``, ``support.prop_worlds``): a generated world is
computed and closed as the platform closes it up to an arrival cut (the stream before the lock);
the intents posted to the first k periods — the journal runs the platform has booked when it
locks them — are sealed as ``posted`` (RCP-05; ``platform_props.sealed_through``) and those
periods are locked through ``PeriodInput.states`` (``closed``). The full stream then arrives over
the sealed amounts: every event the cut excluded is a late event of the periods it belongs to.
After the lock no line of a locked period changes — the recompute posts nothing into a locked
period (S14-R-05: every amount of a closed period posts where ``assign_posting_period`` places
it) — and every redirected line carries its origin period and ``reason_code = LATE_EVENT`` and
posts in the earliest postable period on or after its origin (S14-R-06; ``dates.
first_open_period_on_or_after``), which with a locked prefix is the first open period. A control
recompute of the same stream over the same sealed amounts with every period open shows that the
redirection moves amounts without changing them: per (subject, role, currency) the redirected
amounts equal the control's amounts in the locked periods.

The ``lock_period`` command part is DB-bound and has no domain command yet (CLO-6;
``platform_plan.LOCK_GAP``); it is NOT written here (DG-TST-07 keeps database tests under
``tests/pg/``) and is the open PRP-6 item once the command and the lane databases exist.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from erev_engine import compute
from erev_engine.bundle import PostingIntent
from hypothesis import given
from hypothesis import strategies as st
from support import platform_props, strategies
from support.prop_worlds import WorldSpec, bundle

pytestmark = pytest.mark.property

LATE_EVENT = "LATE_EVENT"


def _by_subject_role(
    entries: list[tuple[str, tuple[str, ...], PostingIntent]], periods: set[str]
) -> dict[tuple[str, str, str, str], int]:
    """Signed posted amounts (debit positive, transaction minor units) per (book, subject, role,
    currency) of the intents whose ORIGIN period (else posting period) is in ``periods``."""
    found: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for _, _, intent in entries:
        origin = intent.origin_period_key or intent.posting_period_key
        if origin not in periods:
            continue
        for line in intent.lines:
            key = (intent.book_code, intent.subject_key, line.account_role, line.txn_currency)
            found[key] += line.amount_txn if line.side == "D" else -line.amount_txn
    return {key: amount for key, amount in found.items() if amount}


@platform_props.platform_settings()
@given(spec=strategies.world_specs(), data=st.data())
def test_p11_locked_period_unchanged(spec: WorldSpec, data: st.DataObject) -> None:
    """PROP:P11: after a period is locked, no generated command sequence changes a line of that
    period; late events create lines in the first open period with the origin period set and
    ``reason_code`` ``LATE_EVENT``; the redirection preserves the amounts."""
    books = ("ASC606", "LEGACY")
    cut = data.draw(st.integers(0, len(spec.measures)))
    before = platform_props.close_run(bundle(spec, books=books, arrivals=cut))
    keys = platform_props.period_keys(before.bundle, before.bundle.entities[0].code)
    locked_count = data.draw(st.integers(1, min(len(keys) - 1, 30)))
    locked = set(keys[:locked_count])
    first_open = keys[locked_count]
    # the platform has booked the journal runs of the periods it locks; later periods' intents
    # are not journal runs yet and are recomputed
    sealed = platform_props.sealed_through(before.outputs, keys, keys[locked_count - 1])
    states = {period: "closed" for period in locked}
    after = platform_props.close_run(bundle(spec, books=books, period_states=states, posted=sealed))
    entries = platform_props.intents(after, *books)
    # (i) immutability: nothing posts into a locked period after the lock
    for _, _, intent in entries:
        assert intent.posting_period_key not in locked, (
            "a line posted into a locked period",
            intent.posting_period_key,
            intent.entry_kind,
            intent.subject_key,
        )
    # (ii) late lines: origin in a locked period → LATE_EVENT in the first open period (S14-R-06)
    redirected = [
        intent
        for _, _, intent in entries
        if intent.origin_period_key is not None and intent.origin_period_key in locked
    ]
    for intent in redirected:
        assert intent.reason_code == LATE_EVENT, (intent.entry_kind, intent.reason_code)
        assert intent.posting_period_key == first_open, (
            intent.origin_period_key,
            intent.posting_period_key,
            first_open,
        )
    # a line with an origin outside the locked set never carries the late reason
    for _, _, intent in entries:
        if intent.reason_code == LATE_EVENT:
            assert intent.origin_period_key in locked, (
                intent.origin_period_key,
                intent.posting_period_key,
            )
    # (iii) the redirection moves amounts, it does not change them: the same stream over the same
    # sealed amounts with every period open posts, in the locked periods, exactly what the locked
    # run redirected out of them
    control = compute(bundle(spec, books=books, posted=sealed))
    control_entries = [
        (after.bundle.group.group_key, tuple(after.bundle.group.member_contract_keys), intent)
        for book in control.books
        for intent in book.posting_intents
    ]
    assert _by_subject_role(entries, locked) == _by_subject_role(control_entries, locked)
