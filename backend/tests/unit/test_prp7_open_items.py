"""The items the stateful machine's coverage note named (BUILD_SPEC PRP-7 note; T1 record
2026-09-22), each reproduced through the same in-memory platform the machine drives
(``support.platform_props``). An open item is pinned as a strict expected failure — here, because
DG-TST-09 forbids ``xfail`` on gate-marked (property) tests — and the pin is lifted by the change
that settles it (pin policy R-10a). Both items are settled: the module holds their witnesses and
no expected failure.

- ENG-S14R10-FX-SIGN-1 — CLOSED (supervisor ruling R-44 (a); ENGINE_SPEC_B S14-R-10, S14-INV-09).
  A redirected REVENUE_RECOGNITION delta whose transaction and functional amounts differ in sign
  was refused under decision L2-5-Q-34 (docs/reviews/loop/sprint/L2-5.md:261). It now posts as a
  transaction line and a functional line of the same role. The two former pins are the first two
  tests below, as passing witnesses of their own figures: rate kinds orders of magnitude apart,
  and Codex production-20260922-1508 §2's arithmetic at spot 1 / average 2. The market-rate
  witness is ``tests/engine/s14_posting/test_s14_fx_sign_witness.py``.
- CLO-LOCK-ORDER-1 (RULED: supervisor ruling R-6; PRD BR-CLS-08, ERR-65): the platform admitted a
  plain LOCK of a later period while an earlier one was postable; a later booking into the earlier
  period changes the locked period's opening while its snapshot is frozen, so the rollforward
  identity across that lock (P6) has no defined form. The ordinary lock is now chronological: the
  request and the decision are refused while an earlier period is ``open``, ``closing`` or
  ``reopened``. The machine's rule that periods close in calendar order is the product rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from erev_api.domain.close import gates, period_machine
from erev_api.enums import ChecklistStatus, PeriodState
from erev_engine.bundle import FxRateInput
from erev_engine.dates import month_end
from support import oracle, platform_props
from support.prop_worlds import INCEPTION, LineSpec, MeasureSpec, WorldSpec

MONTHS = 24
KEYS = [oracle.month_period_key(oracle.add_months(INCEPTION, n)) for n in range(MONTHS)]
ROLES = ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE")


def _rates(txn: str, fn: str, spot: str, averages: tuple[str, ...], closings: tuple[str, ...]):
    rows = []
    for n, key in enumerate(KEYS):
        start = oracle.add_months(INCEPTION, n)
        end = month_end(start)
        rows.append(
            FxRateInput(f"SPOT-{key}", "FX@v1", "spot", txn, fn, start, None, Decimal(spot))
        )
        average = Decimal(averages[n % len(averages)])
        closing = Decimal(closings[n % len(closings)])
        rows.append(FxRateInput(f"AVERAGE-{key}", "FX@v1", "average", txn, fn, end, key, average))
        rows.append(FxRateInput(f"CLOSING-{key}", "FX@v1", "closing", txn, fn, end, key, closing))
    return tuple(rows)


def _net(run: platform_props.CloseRun, period_key: str) -> int:
    """D-12: the entity's presented net position (liability − asset − unbilled), transaction."""
    rows = platform_props.balance_rows(run.primary())
    entity = run.bundle.entities[0].code
    total = 0
    for contract in platform_props.iter_contracts(run.bundle):
        columns = rows[(f"{contract}@{entity}", period_key)]
        total += platform_props.balance(columns, ROLES[0], False)
        total -= platform_props.balance(columns, ROLES[1], False)
        total -= platform_props.balance(columns, ROLES[2], False)
    return total


def _role_lines_net_credit(run: platform_props.CloseRun, period_key: str) -> int:
    total = 0
    for _, _, intent in platform_props.intents(run, platform_props.PRIMARY):
        if intent.posting_period_key != period_key:
            continue
        for line in intent.lines:
            if line.account_role in ROLES:
                total += line.amount_txn if line.side == "C" else -line.amount_txn
    for item in run.bundle.posted:
        if item.book_code == platform_props.PRIMARY and item.period_key == period_key:
            if item.account_role in ROLES:
                total -= item.amount_txn  # debit positive
    return total


def _late_revenue_lines(
    run: platform_props.CloseRun, subject_key: str
) -> list[tuple[str, str, int, int]]:
    """(side, role, transaction, functional) of the REVENUE_RECOGNITION entry of ``subject_key``
    that ``run`` redirects from locked January to February (S14-R-06), in entry order."""
    (found,) = [
        intent
        for _, _, intent in platform_props.intents(run, platform_props.PRIMARY)
        if intent.entry_kind == "REVENUE_RECOGNITION"
        and intent.subject_key == subject_key
        and (intent.posting_period_key, intent.origin_period_key, intent.reason_code)
        == ("FY2026-P02", "FY2026-P01", "LATE_EVENT")
    ]
    return [
        (line.side, line.account_role, line.amount_txn, line.amount_functional)
        for line in found.lines
    ]


def test_eng_s14r10_fx_sign_1_inconsistent_rate_kinds_post_the_two_lines() -> None:
    """JPY → CLF; spot 317.092384111085 every month against averages ≤ 1.06E-3 and closings
    ≤ 9.07E-6; K-1 PIT 7,781,346 delivered day 14; January closing then locked (its lines sealed);
    a late billing of 114 effective 26 January arriving afterwards and a second contract booked at
    the inception after the lock. The recompute redirects January's amounts to February; the
    CONTRACT_LIABILITY delta of K-1/POB-01 is −5,518,692 JPY and +361,485,316 minor units of CLF
    (T1 probe, 2026-09-22), and REVENUE the reverse: a transaction line and a functional line per
    role, each on the side of its own amount, balancing in each currency."""
    rates = _rates(
        "JPY",
        "CLF",
        "317.092384111085",
        (
            "3.9E-11",
            "1E-12",
            "4.3010E-8",
            "0.000731101142",
            "1E-12",
            "0.001064946205",
            "8.703E-9",
            "3.603E-9",
        ),
        ("1.55E-10", "0.000009068418", "1.649E-9"),
    )
    policies = {"fx.cl_layer_consumption": "PRO_RATA", "fx.unbilled_revenue_rate": "PERIOD_AVERAGE"}
    pit = LineSpec("POB-01", "PIT", 7781346, 689, 1, 0, 0)
    before = WorldSpec(
        "JPY", (("K-1", (pit,)),), (MeasureSpec("K-1", "POB-01", "DELIVERY", 14, 1),)
    )
    first = platform_props.close_run(
        platform_props.machine_bundle(
            before,
            period_states={"FY2026-P01": "closing"},
            months=MONTHS,
            functional_currency="CLF",
            fx_rates=rates,
            policies=policies,
        )
    )
    sealed = platform_props.sealed_through(first.outputs, KEYS, "FY2026-P01")
    after = WorldSpec(
        "JPY",
        (
            ("K-1", (pit,)),
            (
                "K-2",
                (
                    LineSpec("POB-01", "DAILY", 3628799, 122, 1, 0, 7),
                    LineSpec("POB-02", "DAILY", 161, 51, 1, 0, 1),
                    LineSpec("POB-03", "PIT", 100001, 881, 3, 0, 0),
                ),
            ),
        ),
        (
            MeasureSpec("K-1", "POB-01", "DELIVERY", 14, 1),
            MeasureSpec("K-1", "POB-01", "BILLING", 25, 114),
        ),
    )
    late = platform_props.close_run(
        platform_props.machine_bundle(
            after,
            period_states={"FY2026-P01": "closed"},
            posted=sealed,
            months=MONTHS,
            functional_currency="CLF",
            fx_rates=rates,
            policies=policies,
        )
    )
    assert _late_revenue_lines(late, "K-1/POB-01") == [
        ("D", "CONTRACT_LIABILITY", 0, 361485316),
        ("D", "REVENUE", 5518692, 0),
        ("C", "CONTRACT_LIABILITY", 5518692, 0),
        ("C", "REVENUE", 0, 361485316),
    ]


def test_eng_s14r10_fx_sign_1_codex_1508_arithmetic_posts_the_two_lines() -> None:
    """JPY → USD, spot 1 / average 2 / closing 1.5 every month. K-1: a point-in-time line 110 JPY,
    SSP 11 × 11 units; 10 units delivered in January → revenue 100 unbilled at the average
    (functional 200.00); January closing then locked, its lines sealed. Then, late in January: a
    billing of 50 (a liability layer at spot 1) and one more unit — revenue 110 = 50 relieved at
    spot 1 + 60 unbilled at average 2 = 170.00. The redirected February delta of
    CONTRACT_LIABILITY is +10 JPY and −30.00 USD (Codex's own figures at average 3: +10 / −70.00;
    T1 probe, 2026-09-22), and REVENUE the reverse: a transaction line and a functional line per
    role."""
    rates = _rates("JPY", "USD", "1", ("2",), ("1.5",))
    policies = {"fx.cl_layer_consumption": "FIFO", "fx.unbilled_revenue_rate": "PERIOD_AVERAGE"}
    pit = LineSpec("POB-01", "PIT", 110, 11, 11, 0, 0)
    delivered = MeasureSpec("K-1", "POB-01", "DELIVERY", 10, 10)
    first = platform_props.close_run(
        platform_props.machine_bundle(
            WorldSpec("JPY", (("K-1", (pit,)),), (delivered,)),
            period_states={"FY2026-P01": "closing"},
            months=MONTHS,
            functional_currency="USD",
            fx_rates=rates,
            policies=policies,
        )
    )
    sealed = platform_props.sealed_through(first.outputs, KEYS, "FY2026-P01")
    late = platform_props.close_run(
        platform_props.machine_bundle(
            WorldSpec(
                "JPY",
                (("K-1", (pit,)),),
                (
                    delivered,
                    MeasureSpec("K-1", "POB-01", "BILLING", 20, 50),
                    MeasureSpec("K-1", "POB-01", "DELIVERY", 21, 1),
                ),
            ),
            period_states={"FY2026-P01": "closed"},
            posted=sealed,
            months=MONTHS,
            functional_currency="USD",
            fx_rates=rates,
            policies=policies,
        )
    )
    assert _late_revenue_lines(late, "K-1/POB-01") == [
        ("D", "CONTRACT_LIABILITY", 10, 0),
        ("D", "REVENUE", 0, 3000),
        ("C", "CONTRACT_LIABILITY", 0, 3000),
        ("C", "REVENUE", 10, 0),
    ]


def _all_gates_passed(at: datetime) -> tuple[gates.GateResult, ...]:
    """The gate results of a period ready for its lock request: every gate passed, the
    controller's certification still to come (it is the lock decision itself)."""
    return tuple(
        gates.GateResult(code, ChecklistStatus.FAILED, None, gates.CERTIFICATION_DETAIL, at)
        if code == gates.CONTROLLER_CERTIFIED
        else gates.GateResult(code, ChecklistStatus.PASSED, 0, None, at)
        for code in gates.GATE_CHECK_CODES
    )


def test_clo_lock_order_1_a_later_period_is_not_locked_first() -> None:
    """CLO-LOCK-ORDER-1 as ruled (supervisor ruling R-6; PRD BR-CLS-08 / ERR-65). Part 1, the
    refusal: March in soft close with every gate passed is not submitted for lock, and not locked,
    while January is postable — 409 ``earlier-period-open`` with the ERR-65 copy — and is accepted
    once no earlier period is. The database witnesses of the same rule are
    ``tests/domain/close/test_lock.py::test_br_cls_08_*``.

    Part 2, what the refusal prevents, in the figures of the former strict-xfail pin (T1 probe,
    2026-09-22). JPY: K-1 (a PIT and two DAILY lines) and K-2 booked at the inception; January
    closing; a K-2 delivery on day 61 (March); March LOCKED while January and February stay
    postable — its lines sealed and its presented net position snapshotted; then K-3 booked at
    the inception. February's presented position (the identity's opening) is recomputed with K-3
    while March's snapshot predates it, and K-3's March amounts are redirected to April, so
    closing − opening ≠ billings + the engine's March lines: P6 has no defined identity across an
    out-of-order lock. The in-memory platform builds that state directly; the product no longer
    reaches it."""
    at = datetime(2026, 4, 5, 12, tzinfo=UTC)
    ctx = period_machine.Context(period_key="FY2026-P03", entity_code="E-1", book_code="ASC606")
    comment = "March 2026 close complete"
    refused = period_machine.decide(
        PeriodState.CLOSING,
        period_machine.Command.REQUEST_LOCK,
        period_machine.Guards(
            comment=comment, gate_results=_all_gates_passed(at), earlier_postable_period="Jan 2026"
        ),
        ctx=ctx,
    )
    assert isinstance(refused, period_machine.Refusal)
    assert (refused.slug, refused.rule_id, refused.problem().status) == (
        "earlier-period-open",
        "BR-CLS-08",
        409,
    )
    assert refused.detail == (
        "Lock Jan 2026 first. An earlier period of E-1 in book ASC606 is not closed."
    )
    accepted = period_machine.decide(
        PeriodState.CLOSING,
        period_machine.Command.REQUEST_LOCK,
        period_machine.Guards(comment=comment, gate_results=_all_gates_passed(at)),
        ctx=ctx,
    )
    assert isinstance(accepted, period_machine.Accepted)

    k1 = (
        LineSpec("POB-01", "PIT", 668, 2700, 1, 0, 0),
        LineSpec("POB-02", "DAILY", 2835081, 380, 1, 0, 6),
        LineSpec("POB-03", "DAILY", 8849, 2375, 1, 0, 7),
    )
    k2 = (
        LineSpec("POB-01", "DAILY", 429, 35233, 1, 0, 14),
        LineSpec("POB-02", "PIT", 8072, 330234, 2, 0, 0),
        LineSpec("POB-03", "PIT", 111, 9107, 1, 0, 0),
    )
    k3 = (
        LineSpec("POB-01", "PIT", 77971, 3704, 4, 0, 0),
        LineSpec("POB-02", "DAILY", 3062, 1911, 1, 0, 16),
        LineSpec("POB-03", "DAILY", 34, 16693, 1, 0, 7),
    )
    delivery = MeasureSpec("K-2", "POB-02", "DELIVERY", 61, 1)
    locking = platform_props.close_run(
        platform_props.machine_bundle(
            WorldSpec("JPY", (("K-1", k1), ("K-2", k2)), (delivery,)),
            period_states={"FY2026-P01": "closing"},
            months=MONTHS,
        )
    )
    sealed = platform_props.sealed_through(locking.outputs, KEYS, "FY2026-P03")
    march_snapshot = _net(locking, "FY2026-P03")
    later = platform_props.close_run(
        platform_props.machine_bundle(
            WorldSpec("JPY", (("K-1", k1), ("K-2", k2), ("K-3", k3)), (delivery,)),
            period_states={"FY2026-P01": "closing", "FY2026-P03": "closed"},
            posted=sealed,
            months=MONTHS,
        )
    )
    opening = _net(later, "FY2026-P02")
    lines = _role_lines_net_credit(later, "FY2026-P03")
    assert isinstance(march_snapshot, int) and isinstance(opening, int)
    # The identity P6 states for a period locked in order; across the out-of-order lock it fails.
    assert march_snapshot - opening != 0 + lines, (
        "P6 across an out-of-order lock",
        {
            "opening": opening,
            "closing": march_snapshot,
            "billed": 0,
            "role lines net credit": lines,
        },
    )
