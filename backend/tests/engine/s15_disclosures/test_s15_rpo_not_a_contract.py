"""RPO of a Step 1 failure (ENGINE_SPEC_B S15-R-08, S15-R-12 rev 1.7; D-91 gaps (v), (vii); ENA-2b).

The obligations of a contract whose status in the book is ``NOT_A_CONTRACT`` at d_v contribute
nothing to RPO or to any rollforward line (606-10-50-13: a Step 1 failure has no remaining
performance obligations); a contract whose status turns recognising inside the period enters on the
``NEW_CONTRACTS`` line; after a 25-7 release the RPO of an obligation nets the revenue attributed to
it (S14-R-25). The A21 baseline was MEASURED from the actual report on the base engine 9467de0
before the exclusion was built (``.run/l9/d91-gaps-d1/baseline-rpo.jsonl``): the T1 world reported
``contract_version.rpo_amount`` 120,000 minor, the stage 15 row included at 120,000, and the
FY2026-P02 rollforward opening and closing 120,000 (UNEXPLAINED 0); T10 reported 60,000 with
opening 120,000, REVENUE −60,000. No database (DG-TST-18).
"""

from __future__ import annotations

from datetime import date

import erev_engine
from erev_engine.stages import STAGES, s01_canonicalize, s13_books
from erev_engine.stages.s15_disclosures import DisclosureState
from erev_engine.trace import TraceBuilder
from support import step1_worlds as w

BASELINE_RPO = (
    120000  # measured on 9467de0 for T1, T2, T3 and T7 (A21; not inferred from the price)
)


def _disclosure(value):
    output = erev_engine.compute(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=erev_engine.ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    (book,) = output.books
    return book, result.state


def test_not_a_contract_obligations_are_excluded_from_rpo_and_its_rollforward() -> None:
    """T1 at d_v 2026-02-15 (the receipt), NOT_A_CONTRACT: the base engine reported 120,000; the
    row is excluded (params ``excluded`` NOT_A_CONTRACT, ``included`` false) and every line of the
    FY2026-P02 rollforward is 0; the refundable T3 and the undelivered goods T7 alike."""
    for value in (w.time_world(), w.time_world(nonrefundable=False), w.pit_world(delivery=None)):
        book, state = _disclosure(value)
        assert book.contract_version is not None
        assert book.contract_version.columns["status_in_book"] == "NOT_A_CONTRACT"
        assert book.contract_version.columns["rpo_amount"] == 0 != BASELINE_RPO
        (row,) = state.rpo
        assert (row.included, row.total, row.after_exemptions, state.rpo_amount) == (False, 0, 0, 0)
        (rollforward,) = state.rpo_rollforwards
        assert rollforward.period_key == "FY2026-P02"
        assert set(rollforward.lines.values()) == {0}
        node = next(n for n in book.trace.nodes if n.id == row.trace_nodes["rpo_amount"])
        assert (node.params["included"], node.params["excluded"], node.value) == (
            "false",
            "NOT_A_CONTRACT",
            "0.00",
        )
        # T-CON-11 is untouched (D-91 gaps (vii)): the obligation still shows its full remainder.
        (version,) = book.obligation_versions
        assert (
            version.columns["revenue_cum"],
            version.columns["awaiting_trigger_amount"] + version.columns["scheduled_amount"],
        ) == (0, 120000)


def test_criteria_met_inside_the_period_enters_rpo_on_the_new_contracts_line() -> None:
    """T10: CONTRACT_CRITERIA_MET 2026-06-30 (d_v): the base reported opening 120,000 and REVENUE
    −60,000; now the opening (31 May, NOT_A_CONTRACT) is 0, the contract enters on NEW_CONTRACTS at
    120,000, REVENUE −60,000 (the STEP1_MET catch-up) and the closing 60,000 ties (V9)."""
    value = w.time_world(steps=[("C", date(2026, 6, 30), "")])
    book, state = _disclosure(value)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 60000
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2026-P06"
    lines = dict(rollforward.lines)
    assert (lines["OPENING"], lines["NEW_CONTRACTS"], lines["REVENUE"], lines["CLOSING"]) == (
        0,
        120000,
        -60000,
        60000,
    )
    assert lines["UNEXPLAINED"] == 0


def test_rpo_after_a_release_nets_the_revenue_attributed_to_the_obligation() -> None:
    """T9 at d_v 2027-01-15: the goods released under 25-7 (1,200.00) are SATISFIED, RPO 0; the
    rollforward of FY2027-P01 ties with the entry net of the attributed revenue (0) and no
    revenue line, UNEXPLAINED 0 (S15-INV-08 holds with the netted stage 09 target)."""
    value = w.pit_world(steps=[("C", date(2027, 1, 15), "")], months=13)
    book, state = _disclosure(value)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 0
    (row,) = state.rpo
    assert (row.included, row.total) == (False, 0)
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2027-P01"
    assert set(rollforward.lines.values()) == {0}
    # A partially recognised release (D-91 gaps (v), S14-R-25): the mixed world with the service
    # running to 30 June 2027, the 25-7(c) point on 30 September 2026 releasing 1,200.00 (800.00 to
    # the goods, 400.00 to the service) and the criteria met on 15 January 2027: the service is
    # PARTIALLY_SATISFIED at d_v (C = 400 × 12/18 = 266.67 below its 400.00 share, target 0), so
    # its RPO nets the attributed revenue (400.00 − 400.00, floored at 0) citing the share node,
    # and the FY2027-P01 rollforward ties at 0.
    mixed = w.mixed_world(
        months=18,
        service_end=date(2027, 6, 30),
        met_on=date(2026, 9, 30),
        steps=[("C", date(2027, 1, 15), "")],
    )
    book, state = _disclosure(mixed)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 0
    rows = {row.subject_key: row for row in state.rpo}
    service = rows[f"{w.CONTRACT}/{w.SERVICE}"]
    assert (service.included, service.total) == (True, 0)
    node = next(n for n in book.trace.nodes if n.id == service.trace_nodes["rpo_amount"])
    assert node.params["r25"] == "40000"
    assert node.inputs[-1] == f"deposit_revenue_share:{w.CONTRACT}/{w.SERVICE}:-"
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2027-P01" and set(rollforward.lines.values()) == {0}
    (version,) = [v for v in book.obligation_versions if v.subject_key == service.subject_key]
    assert (version.columns["satisfaction_status"], version.columns["revenue_cum"]) == (
        "PARTIALLY_SATISFIED",
        0,
    )


def test_wholly_excluded_contract_reports_no_rollforward_activity() -> None:
    """D1-R02 (A21): a 1,200.00 service booked 2026-02-05 inside FY2026-P02 that never passes Step
    1 contributes nothing to any rollforward line (no NEW_CONTRACTS / CANCELLATIONS pair); the
    control with CONTRACT_CRITERIA_MET at inception enters on NEW_CONTRACTS 120,000 with REVENUE
    −9,474 (MONTHLY_EVEN 3/38 of the 5 February to 31 December term) and ties. Figures: derive.py
    R02, R02_control."""
    book, state = _disclosure(w.time_world(inception=date(2026, 2, 5)))
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 0
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2026-P02"
    assert dict(rollforward.lines) == dict.fromkeys(rollforward.lines, 0)
    control, control_state = _disclosure(
        w.time_world(inception=date(2026, 2, 5), steps=[("C", date(2026, 2, 5), "")])
    )
    assert control.contract_version is not None
    (entered,) = control_state.rpo_rollforwards
    lines = dict(entered.lines)
    assert (lines["NEW_CONTRACTS"], lines["REVENUE"], lines["CANCELLATIONS"]) == (120000, -9474, 0)
    assert (lines["CLOSING"], lines["UNEXPLAINED"]) == (110526, 0)
    assert control.contract_version.columns["status_in_book"] == "ACTIVE"


def test_step1_failure_after_a_release_moves_the_netted_remainder() -> None:
    """D1-R03: receipts 400.00, the 25-7(c) point 2026-03-31 releases 400.00; CONTRACT_CRITERIA_MET
    2026-06-30 posts the netted STEP1_MET 200.00 (C 600.00 − R25 400.00), so the RPO at 30 June is
    600.00; a significant change and a not-probable reassessment on 2026-07-01 make the contract
    NOT_A_CONTRACT: the closing is 0 and the removal is measured on the R25-netted basis (−600.00,
    UNEXPLAINED 0), not −1,000.00 with UNEXPLAINED +400.00. Figures: derive.py R03."""
    value = w.time_world(
        paid="400.00",
        met_on=date(2026, 3, 31),
        steps=[
            ("C", date(2026, 6, 30), ""),
            ("S", date(2026, 7, 1), "credit event"),
            ("N", date(2026, 7, 1), ""),
        ],
    )
    book, state = _disclosure(value)
    assert book.contract_version is not None
    assert book.contract_version.columns["status_in_book"] == "NOT_A_CONTRACT"
    assert book.contract_version.columns["rpo_amount"] == 0
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2026-P07"
    lines = dict(rollforward.lines)
    assert (lines["OPENING"], lines["REVENUE"], lines["CLOSING"]) == (60000, 0, 0)
    assert (lines["CANCELLATIONS"], lines["UNEXPLAINED"]) == (-60000, 0)
    assert (
        sum(
            lines[code]
            for code in lines
            if code not in ("OPENING", "CLOSING", "UNEXPLAINED", "CANCELLATIONS")
        )
        == 0
    )
    (row,) = rollforward.rows
    assert dict(row.reasons) == {"CANCELLATIONS": "STATUS_25_5"}  # D-94 (4), Q-10


def test_entry_and_exit_inside_one_period_reconcile() -> None:
    """Secondary review item 1: goods 2 × 600.00 booked NOT_A_CONTRACT (received 15 Feb); criteria
    met 1 Jul; one unit delivered 10 Jul (revenue 600.00); significant change and not probable 20
    Jul return the contract to NOT_A_CONTRACT with the revenue preserved (S02-R-05). July: OPENING
    0, NEW_CONTRACTS 120,000 (the entry), REVENUE −60,000, CANCELLATIONS −60,000 (the remainder
    at the exit), CLOSING 0, UNEXPLAINED 0. Figures: derive.py ITEM1."""
    value = w.pit_world(
        delivery=None,
        quantity="2",
        steps=[
            ("C", date(2026, 7, 1), ""),
            ("D", date(2026, 7, 10), "1"),
            ("S", date(2026, 7, 20), "credit event"),
            ("N", date(2026, 7, 20), ""),
        ],
    )
    book, state = _disclosure(value)
    assert book.contract_version is not None
    assert book.contract_version.columns["status_in_book"] == "NOT_A_CONTRACT"
    assert book.contract_version.columns["rpo_amount"] == 0
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2026-P07"
    lines = dict(rollforward.lines)
    assert (
        lines["OPENING"],
        lines["NEW_CONTRACTS"],
        lines["REVENUE"],
        lines["CANCELLATIONS"],
        lines["CLOSING"],
        lines["UNEXPLAINED"],
    ) == (0, 120000, -60000, -60000, 0, 0)
    (row,) = rollforward.rows
    assert dict(row.reasons) == {"CANCELLATIONS": "STATUS_25_5"}  # D-94 (4), Q-10


def test_delayed_entry_inside_the_inception_period_enters_once() -> None:
    """Secondary review item 4: inception 1 Jan NOT_A_CONTRACT, 1,200.00 received 15 Jan, criteria
    met 31 Jan (CATCH_UP_AT_TRANSITION, C 1/12): January OPENING 0 (no status before inception),
    NEW_CONTRACTS 120,000 once (the entry, not the suppressed inception boundary), REVENUE
    −10,000, CLOSING 110,000, UNEXPLAINED 0. Figures: derive.py ITEM4."""
    value = w.time_world(paid_on=date(2026, 1, 15), steps=[("C", date(2026, 1, 31), "")])
    book, state = _disclosure(value)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 110000
    (rollforward,) = state.rpo_rollforwards
    assert rollforward.period_key == "FY2026-P01"
    lines = dict(rollforward.lines)
    assert (
        lines["OPENING"],
        lines["NEW_CONTRACTS"],
        lines["REVENUE"],
        lines["CLOSING"],
        lines["UNEXPLAINED"],
    ) == (0, 120000, -10000, 110000, 0)
