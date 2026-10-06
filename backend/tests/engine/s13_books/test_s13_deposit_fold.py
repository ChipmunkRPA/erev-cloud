"""The deposit fold after stage 03, the JET-01b 25-7 revenue posting and the STEP1_MET netting
(ENGINE_SPEC S02-R-04, S02-R-07 rev 1.6; ENGINE_SPEC_B Table 14-A, S14-R-05, S14-R-25 rev 1.7;
D-91 "Contract and obligation gaps" (iii), (iv), (v), (x); BUILD_SPEC ENA-2b, END-4b).

The 1.0-rc stage 13 guard (``test_s13_rc_guard.py``) fails closed on any 606-10-25-7 recognition;
END-4b replaces it with the real behaviour: stage 02 folds its deposit ledger once after stage 03
(``run_deposits``), the refined state replaces ``published["02"]``, stage 09 attributes the
recognition to the obligations and stage 14 posts Dr DEPOSIT_LIABILITY / Cr REVENUE per obligation
exactly once on replay. A recognition at an event posts at compute (EVENT); one at a dated point is
a TIME amount of the CLOSE_RELEASE pass, posted by the close run of its period or carried into the
first open period with origin when the period is closed (S14-R-05, S14-R-06), and a COMMAND compute
with the period open posts nothing (the A11 control). Figures: ``.run/l9/d91-gaps-d1/derive.py``.
No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import erev_engine
import pytest
from erev_engine.stages import STAGES, s01_canonicalize, s13_books
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.trace import TraceBuilder
from support import cpc_worlds as cpc
from support import intent_totals
from support import step1_worlds as w

RELEASE = (
    "FY2026-P12",
    "REVENUE_RECOGNITION",
    "TIME",
    "DEPOSIT_LIABILITY",
    "D",
    120000,
    120000,
    None,
)
REVENUE = ("FY2026-P12", "REVENUE_RECOGNITION", "TIME", "REVENUE", "C", 120000, 120000, None)


def test_deposit_fold_runs_after_stage_03_and_refines_the_published_state() -> None:
    """D-91 gaps (iii): stage 02 publishes no ledger before stage 03; after stage 03 the refined
    ``IdentifiedState`` is ``published["02"]`` and ``PobState.identified``, carrying the T1
    recognition the time test needs the classification for."""
    value = w.time_world()
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=erev_engine.ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    identified = result.states["02"]
    pob = result.states["03"]
    assert isinstance(identified, IdentifiedState) and isinstance(pob, PobState)
    assert pob.identified is identified
    assert [(r.reason, r.effective_date, r.event_key) for r in identified.recognitions] == [
        ("EVENT_25_7_A", date(2026, 12, 31), None)
    ]
    priced = result.states["04"]
    assert priced.pob.identified is identified  # type: ignore[attr-defined]  # stage 04 read it
    releases = priced.specialist_targets.deposit_releases  # type: ignore[attr-defined]
    assert [(r.reason, r.effective_date, r.timed, r.amount) for r in releases] == [
        ("EVENT_25_7_A", date(2026, 12, 31), True, 1200)
    ]
    # Every stage 02 deposit node exists once (CV-50) and the trace re-evaluates.
    ids = [node.id for node in result.trace.nodes]
    assert len(ids) == len(set(ids))
    assert cpc.trace_mismatches(result.trace) == []
    assert f"deposit_to_revenue@2026-12-31:{w.SUBJECT}:-" in ids
    assert f"deposit_to_revenue_time_cum:{w.SUBJECT}:FY2026-P12" in ids


def test_t1_release_is_a_close_release_time_amount_and_replays_once() -> None:
    """T1 (D-91 gaps (iii), (x)): a COMMAND compute with December open posts only the February
    receipt (the A11 control at the horizon); the CLOSE_RELEASE pass posts Dr DEPOSIT_LIABILITY /
    Cr REVENUE 1,200.00 in FY2026-P12 as TIME; a replay and a compute with both posted add
    nothing; the published balance is 0 at FY2026-P12 and the GL agrees after the pass."""
    value = w.time_world()
    command = erev_engine.compute(value)
    (book,) = command.books
    assert cpc.role_net(book, "REVENUE") == {}
    assert cpc.role_net(book, "DEPOSIT_LIABILITY", credit=True) == {"FY2026-P02": 120000}
    assert cpc.balance(book, "FY2026-P12", "deposit_liability_txn") == 0
    assert cpc.balance(book, "FY2026-P11", "deposit_liability_txn") == 120000
    release = w.release_pass(value, command)
    assert w.journal(release, "DEPOSIT_LIABILITY", "REVENUE") == [RELEASE, REVENUE]
    intent = next(i for i in release.posting_intents if i.entry_kind == "REVENUE_RECOGNITION")
    assert {item.dimensions.get("obligation_key") for item in intent.lines} == {w.SERVICE}
    assert cpc.trace_mismatches(release.trace) == []
    again = erev_engine.compute(value)
    assert again.sha256() == command.sha256()
    release_output = intent_totals.close_pass(value, [command], "CLOSE_RELEASE")
    posted = dataclasses.replace(value, posted=intent_totals.posted(command, release_output))
    (replayed,) = erev_engine.compute(posted).books
    assert replayed.posting_intents == ()
    assert w.release_pass(value, command, release_output).posting_intents == ()


def test_a11_control_a_command_compute_before_the_term_end_posts_no_release() -> None:
    """A11 (D-91 gaps (iii)): known_at 2026-06-30 with the later periods future: the time point
    2026-12-31 lies beyond the horizon, nothing is recognised and nothing posts."""
    states = {f"FY2026-P{month:02d}": "future" for month in range(7, 13)}
    value = w.time_world(states=states, known_at=datetime(2026, 6, 30, 23, tzinfo=UTC))
    (book,) = erev_engine.compute(value).books
    assert cpc.role_net(book, "REVENUE") == {}
    assert cpc.balance(book, "FY2026-P06", "deposit_liability_txn") == 120000
    assert cpc.node_values(book, "deposit_to_revenue_time_cum") == {
        f"deposit_to_revenue_time_cum:{w.SUBJECT}:FY2026-P0{m}": "0.00" for m in range(1, 7)
    }
    assert w.release_pass(value, erev_engine.compute(value)).posting_intents == ()


def test_closed_period_twin_posts_the_release_into_the_first_open_period_with_origin() -> None:
    """The closed-period-T twin (S14-R-05, S14-R-06): with FY2026-P12 closed and January 2027 open
    a COMMAND compute carries the December release into FY2027-P01 with origin FY2026-P12."""
    value = w.time_world(months=13, states={"FY2026-P12": "closed"})
    (book,) = erev_engine.compute(value).books
    lines = w.journal(book, "DEPOSIT_LIABILITY", "REVENUE")
    assert (
        "FY2027-P01",
        "REVENUE_RECOGNITION",
        "EVENT",
        "DEPOSIT_LIABILITY",
        "D",
        120000,
        120000,
        "FY2026-P12",
    ) in lines
    assert (
        "FY2027-P01",
        "REVENUE_RECOGNITION",
        "EVENT",
        "REVENUE",
        "C",
        120000,
        120000,
        "FY2026-P12",
    ) in lines
    assert cpc.role_net(book, "DEPOSIT_LIABILITY", credit=True) == {
        "FY2026-P02": 120000,
        "FY2027-P01": -120000,
    }


def test_t9_criteria_met_after_a_release_nets_the_step1_met_catch_up() -> None:
    """T9 (D-91 gaps (v)): goods delivered 2026-12-31 while NOT_A_CONTRACT release 1,200.00 at the
    delivery (EVENT); CONTRACT_CRITERIA_MET on 2027-01-15 under CATCH_UP_AT_TRANSITION posts
    STEP1_MET revenue of max(C_p − R25_p, 0) = 0, so total revenue is 120,000 minor with
    CONTRACT_LIABILITY 0 and DEPOSIT_LIABILITY 0; the netted chain cites the share node."""
    value = w.pit_world(steps=[("C", date(2027, 1, 15), "")], months=13)
    book = cpc.checked(value)
    assert cpc.role_net(book, "REVENUE", credit=True) == {"FY2026-P12": 120000}
    assert cpc.role_net(book, "CONTRACT_LIABILITY") == {}
    assert cpc.role_net(book, "DEPOSIT_LIABILITY", credit=True) == {
        "FY2026-P02": 120000,
        "FY2026-P12": -120000,
    }
    assert cpc.balance(book, "FY2027-P01", "deposit_liability_txn") == 0
    assert cpc.balance(book, "FY2027-P01", "contract_liability_txn") == 0
    (version,) = book.obligation_versions
    assert (version.columns["revenue_cum"], version.columns["satisfaction_status"]) == (
        0,
        "SATISFIED",
    )
    assert (
        book.contract_version is not None
        and book.contract_version.columns["status_in_book"] == "ACTIVE"
    )
    nodes = cpc.nodes(book)
    subject = f"{w.CONTRACT}/{w.GOODS}"
    share = nodes[f"deposit_revenue_share:{subject}:FY2027-P01"]
    assert (
        share.value,
        share.formula_id,
        share.params["basis"],
        share.params["keys"],
        share.params["weights"],
    ) == (
        "1200.00",
        "step1.deposit_revenue_share.v1",
        "ALLOCATION",
        subject,
        "120000",
    )
    assert share.inputs == (f"deposit_to_revenue@{w.CONTRACT}/EV-000005:{w.SUBJECT}:-",)
    netted = nodes[f"step1_netted_target:{subject}:FY2027-P01"]
    assert (netted.value, netted.formula_id, netted.params["r25"]) == (
        "0.00",
        "rec.step1_net.v1",
        "120000",
    )
    assert netted.inputs == (f"segment_target:{subject}:FY2027-P01", share.id)
    revenue = nodes[f"revenue_cum:{subject}:FY2027-P01"]
    assert (revenue.value, revenue.params["adjusted"], revenue.inputs) == (
        "0.00",
        "true",
        (netted.id,),
    )
    assert nodes[f"deposit_revenue_share:{subject}:-"].value == "1200.00"


def test_t9b_criteria_met_after_the_time_completion() -> None:
    """T9b: the time service released at 2026-12-31 (TIME) and CONTRACT_CRITERIA_MET on 2027-01-15:
    the CLOSE_RELEASE pass posts the December release, the transition transfers 0 and posts no
    STEP1_MET revenue; total revenue 120,000 minor, CONTRACT_LIABILITY 0, DEPOSIT_LIABILITY 0."""
    value = w.time_world(steps=[("C", date(2027, 1, 15), "")], months=13)
    command = erev_engine.compute(value)
    (book,) = command.books
    assert cpc.role_net(book, "REVENUE") == {} and cpc.role_net(book, "CONTRACT_LIABILITY") == {}
    release = w.release_pass(value, command)
    assert w.journal(release, "DEPOSIT_LIABILITY", "REVENUE") == [RELEASE, REVENUE]
    assert cpc.balance(book, "FY2027-P01", "contract_liability_txn") == 0
    assert cpc.balance(book, "FY2027-P01", "deposit_liability_txn") == 0
    (version,) = book.obligation_versions
    assert version.columns["revenue_cum"] == 0
    assert cpc.trace_mismatches(book.trace) == []


def test_t5_release_is_attributed_by_the_posted_inception_allocation() -> None:
    """T5 (D-91 gaps (iv); S14-R-25): goods 800.00 and a service 400.00 share the 1,200.00 release
    largest_remainder(120000, [80000, 40000]) = [80000, 40000], one part per obligation."""
    value = w.mixed_world()
    command = erev_engine.compute(value)
    release = w.release_pass(value, command)
    by_obligation = {
        item.dimensions["obligation_key"]: (item.side, item.amount_txn)
        for intent in release.posting_intents
        if intent.entry_kind == "REVENUE_RECOGNITION"
        for item in intent.lines
        if item.account_role == "REVENUE"
    }
    assert by_obligation == {w.GOODS: ("C", 80000), w.SERVICE: ("C", 40000)}
    assert cpc.trace_mismatches(release.trace) == []
    nodes = cpc.nodes(command.books[0])
    share = nodes[f"deposit_revenue_share:{w.CONTRACT}/{w.GOODS}:FY2026-P12"]
    assert (share.value, share.params["weights"], share.params["keys"]) == (
        "800.00",
        "80000|40000",
        f"{w.CONTRACT}/{w.GOODS}|{w.CONTRACT}/{w.SERVICE}",
    )


def test_r01_same_day_refund_precedes_the_term_end_release() -> None:
    """D1-R01 at compute level: receipts 1,200.00, a billing and a FULL termination (refund 200.00)
    both dated T = 2026-12-31. The GL carries one refund of 200.00 (Dr DEPOSIT_LIABILITY / Cr
    UNAPPLIED_CASH), route (b) revenue 1,000.00 as EVENT in FY2026-P12, deposit 0, and the
    CLOSE_RELEASE pass posts nothing more; the CONTRACT_CRITERIA_MET sibling posts the STEP1_MET
    catch-up 1,200.00 and no 25-7 revenue. Figures: derive.py R01, R01_sibling."""
    value = w.time_world(steps=[("I", w.END, "1200.00"), ("T", w.END, "200.00")])
    command = erev_engine.compute(value)
    (book,) = command.books
    assert cpc.role_net(book, "REVENUE") == {"FY2026-P12": -100000}
    assert cpc.role_net(book, "DEPOSIT_LIABILITY", credit=True) == {
        "FY2026-P02": 120000,
        "FY2026-P12": -120000,
    }
    assert cpc.role_net(book, "BILLING_CLEARING", "UNAPPLIED_CASH") == {
        "FY2026-P02": 120000,
        "FY2026-P12": -20000,
    }
    assert cpc.role_net(book, "REFUND_LIABILITY") == {}
    assert cpc.balance(book, "FY2026-P12", "deposit_liability_txn") == 0
    revenue = [line for line in w.journal(book, "REVENUE") if line[0] == "FY2026-P12"]
    assert revenue == [
        ("FY2026-P12", "REVENUE_RECOGNITION", "EVENT", "REVENUE", "C", 100000, 100000, None)
    ]
    assert cpc.trace_mismatches(book.trace) == []
    assert w.release_pass(value, command).posting_intents == ()
    sibling = w.time_world(steps=[("I", w.END, "1200.00"), ("C", w.END, "")])
    (met,) = erev_engine.compute(sibling).books
    assert cpc.role_net(met, "REVENUE") == {"FY2026-P12": -120000}
    assert cpc.balance(met, "FY2026-P12", "deposit_liability_txn") == 0
    # The invoice dated T enters billed_cum at the transition (S02-R-11) against the open
    # receivable; its contract-liability effect is a stage 10 matter outside this control.
    assert (
        cpc.node_values(met, "deposit_to_revenue_cum")[
            f"deposit_to_revenue_cum:{w.SUBJECT}:FY2026-P12"
        ]
        == "0.00"
    )
    assert (
        cpc.node_values(met, "deposit_to_contract_liability_cum")[
            f"deposit_to_contract_liability_cum:{w.SUBJECT}:FY2026-P12"
        ]
        == "1200.00"
    )


def test_r04_mixed_rate_releases_keep_their_own_conversion() -> None:
    """D1-R04 (S12-R-20, S14-R-05, S14-R-10): EUR 600.00 released at the dated 25-7(c) point at
    spot 1.1000 (TIME, USD 660.00) and EUR 600.00 released at the 20 January receipt at spot 1.2000
    (EVENT, USD 720.00), both in FY2026-P01. Each release keeps its own conversion: the COMMAND
    compute posts the EVENT 720.00 and the CLOSE_RELEASE pass the TIME 660.00 (total 1,380.00), not
    a proportional 690.00 / 690.00. Figures: derive.py R04."""
    value = w.eur_mixed_rates()
    command = erev_engine.compute(value)
    (book,) = command.books
    event = ("FY2026-P01", "REVENUE_RECOGNITION", "EVENT", "REVENUE", "C", 60000, 72000, None)
    assert w.journal(book, "REVENUE") == [event]
    assert (
        "FY2026-P01",
        "REVENUE_RECOGNITION",
        "EVENT",
        "DEPOSIT_LIABILITY",
        "D",
        60000,
        72000,
        None,
    ) in w.journal(book, "DEPOSIT_LIABILITY")
    release = w.release_pass(value, command)
    time = ("FY2026-P01", "REVENUE_RECOGNITION", "TIME", "REVENUE", "C", 60000, 66000, None)
    assert w.journal(release, "REVENUE") == [time]
    assert w.journal(release, "DEPOSIT_LIABILITY") == [
        ("FY2026-P01", "REVENUE_RECOGNITION", "TIME", "DEPOSIT_LIABILITY", "D", 60000, 66000, None)
    ]
    assert cpc.role_net(book, "FX_GAIN_LOSS") == {}
    assert cpc.trace_mismatches(release.trace) == []
    replayed = w.release_pass(
        value, command, intent_totals.close_pass(value, [command], "CLOSE_RELEASE")
    )
    assert replayed.posting_intents == ()


def test_item3_time_functional_target_across_periods_and_obligations() -> None:
    """Secondary review item 3: two goods (posted weights 2 : 1), EUR 600 released at the dated (c)
    point 12 Jan at 1.1000 (January TIME EUR [400, 200] / USD [440, 220]) and EUR 600 received and
    released 20 Feb at 1.2000 (February EVENT EUR [400, 200] / USD [480, 240]); no further TIME;
    cumulative USD [920, 460] = 1,380. With January closed the COMMAND compute carries the January
    TIME release into FY2026-P02 with origin FY2026-P01 at the January conversion; a replay posts
    nothing. Figures: derive.py ITEM3."""
    value = w.eur_mixed_rates(
        two_obligations=True, second_on=date(2026, 2, 20), states={"FY2026-P01": "closed"}
    )
    command = erev_engine.compute(value)
    (book,) = command.books
    kind, cls, role = "REVENUE_RECOGNITION", "EVENT", "REVENUE"
    assert w.journal(book, "REVENUE") == [
        ("FY2026-P02", kind, cls, role, "C", 20000, 22000, "FY2026-P01"),
        ("FY2026-P02", kind, cls, role, "C", 20000, 24000, None),
        ("FY2026-P02", kind, cls, role, "C", 40000, 44000, "FY2026-P01"),
        ("FY2026-P02", kind, cls, role, "C", 40000, 48000, None),
    ]
    debits = [
        line for line in w.journal(book, "DEPOSIT_LIABILITY") if line[1] == kind and line[4] == "D"
    ]
    assert debits == [
        ("FY2026-P02", kind, cls, "DEPOSIT_LIABILITY", "D", 20000, 22000, "FY2026-P01"),
        ("FY2026-P02", kind, cls, "DEPOSIT_LIABILITY", "D", 20000, 24000, None),
        ("FY2026-P02", kind, cls, "DEPOSIT_LIABILITY", "D", 40000, 44000, "FY2026-P01"),
        ("FY2026-P02", kind, cls, "DEPOSIT_LIABILITY", "D", 40000, 48000, None),
    ]
    assert cpc.balance(book, "FY2026-P02", "deposit_liability_txn") == 0
    assert cpc.trace_mismatches(book.trace) == []
    posted = dataclasses.replace(value, posted=intent_totals.posted(command))
    (replayed,) = erev_engine.compute(posted).books
    assert replayed.posting_intents == ()
    # Both periods open: the COMMAND compute posts the February EVENT at 1.2000 and the
    # CLOSE_RELEASE pass posts the January TIME at 1.1000 in FY2026-P01; February adds no TIME.
    open_value = w.eur_mixed_rates(two_obligations=True, second_on=date(2026, 2, 20))
    open_command = erev_engine.compute(open_value)
    (open_book,) = open_command.books
    assert w.journal(open_book, "REVENUE") == [
        ("FY2026-P02", kind, cls, role, "C", 20000, 24000, None),
        ("FY2026-P02", kind, cls, role, "C", 40000, 48000, None),
    ]
    release = w.release_pass(open_value, open_command)
    assert w.journal(release, "REVENUE") == [
        ("FY2026-P01", kind, "TIME", role, "C", 20000, 22000, None),
        ("FY2026-P01", kind, "TIME", role, "C", 40000, 44000, None),
    ]
    assert cpc.trace_mismatches(release.trace) == []


@pytest.mark.xfail(
    strict=True,
    reason="D-94 (5), Q-11: open G12 question; measured CONTRACT_LIABILITY 1,200.00 (D1 unchanged)",
)
def test_q11_invoice_dated_t_while_not_a_contract_observation() -> None:
    """D-94 (5) / Q-11 observation (fail-first, xfail strict): receipts 1,200.00 in February, a
    BILLING_RECORDED of 1,200.00 dated T = 2026-12-31 while NOT_A_CONTRACT and CONTRACT_CRITERIA_MET
    dated T. Measured on 94019c0: the deposit transfers (S02-R-08), the invoice enters
    ``billed_cum`` at the transition (S02-R-11), the STEP1_MET catch-up 1,200.00 posts, and the
    book shows CONTRACT_LIABILITY 1,200.00 (minor 120,000) against the open receivable while the
    receipt sits in the transferred deposit. The open accounting question for G12 is whether a
    billing raised while NOT_A_CONTRACT may create a receivable and a contract liability at all, or
    is memo-only until the transition (606-10-25-7, 25-8; 606-10-45-1); this test asserts the
    cash-applied shape (contract liability 0) and is expected to fail until the ruling."""
    value = w.time_world(steps=[("I", w.END, "1200.00"), ("C", w.END, "")])
    (book,) = erev_engine.compute(value).books
    assert cpc.role_net(book, "REVENUE") == {"FY2026-P12": -120000}
    assert cpc.balance(book, "FY2026-P12", "deposit_liability_txn") == 0
    assert cpc.balance(book, "FY2026-P12", "contract_liability_txn") == 0
