"""Foreign-currency consideration payable: JET-14 promised and JET-10d (L6-5; FX-CHK-084-C).

Stage 14 posts JET-14 promised per ``<contract>@<entity>`` from the stage 04
``consideration_payable`` target and S14-R-01 takes its functional amount from stage 12, but the
book loop bound no
consideration-payable flow, so a EUR promise of a USD entity raised ``ENGINE_INVARIANT_VIOLATED``
"stage 12 publishes no functional amount for a foreign-currency part target" and the payable was
never remeasured (POLICIES CHK-084 (c); ENGINE_SPEC_B S12-R-19, S12-R-21, EX-12-B). The book loop
now binds each promise at its promise date; stage 12 creates the payable layer at spot, publishes
the JET-14 functional amount and remeasures the open payable at the closing rate. These tests run
the answer-key world without a database.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import erev_engine
import erev_engine.stages.s14_posting.targets as s14_targets
import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import FxRateInput, InputBundle, MappingRuleInput, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.stages import s12_fx_entities, s13_books
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.s12_fx_entities import FxFlows, FxState, MonetaryFlow
from erev_engine.stages.s12_fx_entities import balances as s12_balances
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.state import AllocatedState, BookContext, RateIndex, Target
from erev_engine.trace import TraceBuilder, reevaluate
from support import bundles, cpc_worlds, intent_totals
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import (
    _build_checkpoint_bundles,
    assert_checkpoints,
    run_engine,
)
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

FX_084_C = "FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED"
SUBJECT = "C-FX-084-C@US01"
PAYABLE, INCENTIVE, GAIN_LOSS = "CONSIDERATION_PAYABLE", "CUSTOMER_INCENTIVE_ASSET", "FX_GAIN_LOSS"
ENTITY = bundles.ENTITY_CODE
RELEASE_SUBJECT = f"{CONTRACT_KEY}@{ENTITY}"
RATE_SET = "EURUSD-PUBLISHED@v1"


@dataclass(frozen=True, slots=True)
class _FxSource:
    """The consumed state as stage 12 reads it (L2-5-Q-10), with the Table 14-A producer targets
    stage 12 reads for the JET-14 release (D-91 amending D-88 L7-6-Q-6)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs = PartInputs()


def _bundle() -> tuple[InputBundle, str]:
    loaded = load(ANSWER_KEY_ROOT / "fx" / f"{FX_084_C}.yaml")
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    (bundle,) = checkpoint.bundles
    return cast(InputBundle, bundle), checkpoint.book


def _lines(output: OutputBundle, book_code: str, kind: str) -> list[tuple[str, str, int, int]]:
    """(class, role, signed txn, signed functional) of the book's FY2026-P06 ``kind`` intents."""
    (book,) = [item for item in output.books if item.book_code == book_code]
    return sorted(
        (
            intent.posting_class,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
            line.amount_functional if line.side == "D" else -line.amount_functional,
        )
        for intent in book.posting_intents
        if intent.entry_kind == kind and intent.posting_period_key == "FY2026-P06"
        for line in intent.lines
    )


def _captured(
    monkeypatch: pytest.MonkeyPatch, bundle: InputBundle, book: str
) -> tuple[BookContext, CostLossState]:
    captured: list[tuple[BookContext, CostLossState]] = []
    original: Callable[[BookContext, CostLossState], s13_books.CostsView] = s13_books.costs_view

    def capture(ctx: BookContext, st: CostLossState) -> s13_books.CostsView:
        captured.append((ctx, st))
        return original(ctx, st)

    monkeypatch.setattr(s13_books, "costs_view", capture)
    erev_engine.compute(bundle)
    return next(item for item in captured if str(item[0].book_code) == book)


def test_l6_5_foreign_promise_posts_jet_14_at_spot_and_remeasures_the_payable() -> None:
    """FX-CHK-084-C `june-close`: EUR 50,000.00 promised on 1 June at spot 1.1000 posts JET-14
    promised Dr CUSTOMER_INCENTIVE_ASSET / Cr CONSIDERATION_PAYABLE USD 55,000.00 at compute; the
    pass remeasures the open payable at the June closing 1.0900 (JET-10d gain 500.00). T-CON-09
    publishes the functional payable at the closing rate, 54,500.00 (S12-R-21), and the incentive
    asset at the promise-date spot, 55,000.00 (POL-164), so the key matches (D-87 L6-5-Q-18)."""
    bundle, book = _bundle()
    command = cast(OutputBundle, erev_engine.compute(bundle))
    assert _lines(command, book, PAYABLE) == [
        ("EVENT", PAYABLE, -5000000, -5500000),
        ("EVENT", INCENTIVE, 5000000, 5500000),
    ]
    with decimal.localcontext(DECIMAL_CONTEXT):
        remeasured = intent_totals.close_pass(bundle, [command], "FX_REMEASUREMENT")
    assert _lines(remeasured, book, "FX_REMEASUREMENT") == [
        ("TIME", PAYABLE, 0, 50000),
        ("TIME", GAIN_LOSS, 0, -50000),
    ]
    (output,) = [item for item in command.books if item.book_code == book]
    (june,) = [item for item in output.balances if item.period_key == "FY2026-P06"]
    assert june.subject_key == SUBJECT
    assert (
        june.columns["consideration_payable_txn"],
        june.columns["consideration_payable_functional"],
        june.columns["customer_incentive_asset_txn"],
        june.columns["customer_incentive_asset_functional"],
    ) == (5_000_000, 5_450_000, 5_000_000, 5_500_000)
    loaded = load(ANSWER_KEY_ROOT / "fx" / f"{FX_084_C}.yaml")
    assert_checkpoints(loaded, run_engine(loaded))


def test_l8_e_book_output_carries_the_line_rates() -> None:
    """D-88 L7-6-Q-1: BookOutput.line_rates copies PostingState.line_rates, sorted by line key: the
    two EUR JET-14 promised lines of the USD entity each carry the 1 June spot (REQ-FX-006)."""
    bundle, book = _bundle()
    command = cast(OutputBundle, erev_engine.compute(bundle))
    (output,) = [item for item in command.books if item.book_code == book]
    foreign = sorted(
        line.line_key
        for intent in output.posting_intents
        for line in intent.lines
        if line.txn_currency != line.functional_currency
    )
    assert [key for key, _ in output.line_rates] == foreign
    assert len(foreign) == 2
    spot = {refs for _, refs in output.line_rates}
    assert len(spot) == 1
    ((rate_key, version_key),) = spot.pop()
    (pinned,) = [rate for rate in bundle.fx_rates if rate.rate_key == rate_key]
    assert (pinned.rate_type, pinned.effective_date, pinned.version_key) == (
        "spot",
        date(2026, 6, 1),
        version_key,
    )
    """D-87 L6-5-Q-18: the functional incentive asset is the promised functional amount at spot
    less the released share at that historical carrying, never remeasured (POL-164). EUR 50,000.00
    promised at 1.1000 (USD 55,000.00) with EUR 10,000.00 released keeps USD 44,000.00; a whole
    release keeps 0, and a period without a promise keeps 0. D-88 L7-6-Q-6: the released share is
    the functional JET-14 release stage 12 publishes (``release_functional``)."""
    released = s12_balances.release_functional(5_500_000, 5_000_000, 1_000_000, 2)
    assert released == 1_100_000
    assert s12_balances._incentive_functional(5_500_000, 5_000_000, released) == 4_400_000
    whole = s12_balances.release_functional(5_500_000, 5_000_000, 5_000_000, 2)
    assert s12_balances._incentive_functional(5_500_000, 5_000_000, whole) == 0
    assert s12_balances.release_functional(5_500_000, 5_000_000, 0, 2) == 0
    assert s12_balances._incentive_functional(5_500_000, 5_000_000, 0) == 5_500_000
    assert s12_balances._incentive_functional(0, 0, 0) == 0
    # Cumulatively rounded share: 1/3 of 1.00 released at a carrying of 1.10 leaves 0.73.
    assert s12_balances.release_functional(110, 300, 100, 2) == 37
    assert s12_balances._incentive_functional(110, 300, 37) == 73


def _consideration(
    released: str, share_based: str | None = None, period: str = "FY2026-P06"
) -> tuple[Target, ...]:
    """The EMOD-22 targets of EUR 50,000.00 promised: the stage 04 payable and ordinary release
    ``released`` in ``period`` and the stage 10 share-based and composed release (D-91)."""
    ordinary = usd(released)
    share = 0 if share_based is None else usd(share_based)
    values = [
        ("consideration_payable", "FY2026-P06", usd("50000.00")),
        ("incentive_release_ordinary_cum", period, ordinary),
    ]
    if share_based is not None:
        values.append(("share_based_reduction_cum", period, share))
    values.append(("incentive_release_cum", period, ordinary + share))
    return tuple(
        Target(
            BookCode.ASC606, ENTITY, RELEASE_SUBJECT, measure, period_key, None, amount, None,
            f"{measure}:{RELEASE_SUBJECT}:{period_key}",
        )
        for measure, period_key, amount in values
    )  # fmt: skip


def _release_run(
    consideration: tuple[Target, ...], currency: str = "EUR"
) -> tuple[BookContext, FxState]:
    """Stage 12 over a EUR 50,000.00 promise on 1 June at spot 1.1000 (June closing 1.0900) with
    the stage 04 customer consideration targets bound on the allocated state."""
    calendar = bundles.entity(months=6, books=("ASC606",))
    ctx = book_context(calendar, book_code="ASC606", currency=currency)
    ctx = dataclasses.replace(ctx, currencies=bundles.currencies("EUR", "USD"))
    promise = MonetaryFlow(
        PAYABLE, "INCREASE", ENTITY, RELEASE_SUBJECT, f"{RELEASE_SUBJECT}#PROMISE-1",
        f"{CONTRACT_KEY}/EV-000002", date(2026, 6, 1), 2, usd("50000.00"), "PROMISE",
    )  # fmt: skip
    rates = (
        FxRateInput(
            "EURUSD-SPOT-2026-06-01", RATE_SET, "spot", "EUR", "USD", date(2026, 6, 1), None,
            Decimal("1.1000"),
        ),
        FxRateInput(
            "EURUSD-CLOSING-FY2026-P06", RATE_SET, "closing", "EUR", "USD", date(2026, 6, 30),
            "FY2026-P06", Decimal("1.0900"),
        ),
    )  # fmt: skip
    allocated = allocated_state([])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    source = _FxSource(
        allocated,
        FxFlows((), monetary=(promise,)),
        PartInputs(customer_consideration=consideration),
    )
    state = s12_fx_entities.run(ctx, source, tb, rates=RateIndex(rates))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return ctx, state


def _released(state: FxState) -> list[tuple[str, str, int, int, list[str]]]:
    return [
        (
            t.subject_key,
            t.period_key,
            t.amount_txn,
            t.amount_functional,
            [r.rate_key for r in t.rates],
        )
        for t in state.functional_targets
        if t.measure == "incentive_release_ordinary_cum"
    ]


def test_l8_e_foreign_release_posts_jet_14_at_historical_carrying() -> None:
    """D-88 L7-6-Q-6: EUR 10,000.00 of 50,000.00 released from USD 55,000.00 publishes F_rel
    11,000.00 = cumulative_posted(55,000.00, 5,500,000, 1/5), with the promised rates and an
    ``fx.settlement.spot.v1`` SHARE node; stage 14 posts JET-14 release at that amount and T-CON-09
    keeps the incentive asset at 44,000.00, so GL and T-CON-09 tie. A whole release gives 55,000.00
    and 0, 1/3 of 1.10 gives 0.37 and 0.73, and a same-currency book publishes none."""
    consideration = _consideration("10000.00")
    ctx, state = _release_run(consideration)
    assert _released(state) == [
        (RELEASE_SUBJECT, "FY2026-P06", 1_000_000, 1_100_000, ["EURUSD-SPOT-2026-06-01"])
    ]
    (release,) = [
        t for t in state.functional_targets if t.measure == "incentive_release_ordinary_cum"
    ]
    assert release.node_id == f"fx_layer_settled:{RELEASE_SUBJECT}#JET-14 release:FY2026-P06"
    parts = {
        part.part: (part.amount_txn, part.amount_functional, [r.rate_key for r in part.rates])
        for part in s14_targets._customer_consideration(
            ctx, PartInputs(customer_consideration=consideration), state
        )
    }
    assert parts == {
        "JET-14 promised": (5_000_000, 5_500_000, ["EURUSD-SPOT-2026-06-01"]),
        "JET-14 release": (1_000_000, 1_100_000, ["EURUSD-SPOT-2026-06-01"]),
    }
    assert s12_balances._incentive_functional(5_500_000, 5_000_000, 1_100_000) == 4_400_000

    _ctx, whole = _release_run(_consideration("50000.00"))
    assert _released(whole)[0][3] == 5_500_000
    assert s12_balances._incentive_functional(5_500_000, 5_000_000, 5_500_000) == 0
    assert s12_balances.release_functional(110, 300, 100, 2) == 37
    assert s12_balances._incentive_functional(110, 300, 37) == 73

    _ctx, same = _release_run(consideration, currency="USD")
    assert _released(same) == []


def test_l8_e_release_without_amount_and_share_based_parts() -> None:
    """D-88 L7-6-Q-6 as amended by D-91: Rel = the posted ``incentive_release_ordinary_cum`` on its
    own, so EUR 10,000.00 of ordinary release beside a 5,000.00 share-based reduction (composed
    release 15,000.00) publishes F_rel 11,000.00, while the foreign share-based part still fails
    closed; Rel = 0 publishes nothing and JET-14 release keeps 0; a release with no promised
    functional amount in its period fails closed."""
    shared = _consideration("10000.00", "5000.00")
    ctx, state = _release_run(shared)
    assert _released(state) == [
        (RELEASE_SUBJECT, "FY2026-P06", 1_000_000, 1_100_000, ["EURUSD-SPOT-2026-06-01"])
    ]
    with pytest.raises(EngineError, match="no functional amount"):
        s14_targets._customer_consideration(ctx, PartInputs(customer_consideration=shared), state)

    nothing = _consideration("0.00")
    ctx, state = _release_run(nothing)
    assert _released(state) == []
    (release,) = [
        part
        for part in s14_targets._customer_consideration(
            ctx, PartInputs(customer_consideration=nothing), state
        )
        if part.part == "JET-14 release"
    ]
    assert (release.amount_txn, release.amount_functional) == (0, 0)

    with pytest.raises(EngineError, match="no promised functional amount"):
        _release_run(_consideration("10000.00", period="FY2026-P05"))


def test_l6_5_payable_flows_follow_the_promises_in_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each non-share-based promise of the booking list binds at its promise date for R of
    S04-R-14 (a second promise of EUR 1,000.00 with a distinct good at fair value 400.00 binds
    600.00 on 15 June), the flows sum to the stage 04 payable, and a same-currency book binds
    none."""
    bundle, book = _bundle()
    events = []
    for event in bundle.events:
        if event.event_type == "CONTRACT_BOOKED":
            listed = cast(list[dict[str, object]], event.payload["consideration_payable"])
            first = listed[0]
            money = type(first["amount"])
            on = date(2026, 6, 15)
            second = {
                **first,
                "amount": money("1000.00"),
                "promise_date": on if isinstance(first["promise_date"], date) else on.isoformat(),
                "distinct_good_fair_value": money("400.00"),
            }
            payload = {**event.payload, "consideration_payable": [first, second]}
            event = dataclasses.replace(event, payload=payload, payload_sha256=sha256_hex(payload))
        events.append(event)
    bundle = dataclasses.replace(bundle, events=tuple(events))
    ctx, st = _captured(monkeypatch, bundle, book)
    flows = s13_books._payable_flows(ctx, st.allocated)
    booked = next(item for item in st.allocated.events if item.event_type == "CONTRACT_BOOKED")
    assert [
        (
            flow.role,
            flow.direction,
            flow.entity,
            flow.subject_key,
            flow.component_key,
            flow.source_key,
            flow.effective_date,
            flow.amount,
            flow.reason,
            flow.control,
        )
        for flow in flows
    ] == [
        (
            PAYABLE, "INCREASE", "US01", SUBJECT, f"{SUBJECT}#PROMISE-1", booked.event_key,
            date(2026, 6, 1), 5000000, "PROMISE", None,
        ),
        (
            PAYABLE, "INCREASE", "US01", SUBJECT, f"{SUBJECT}#PROMISE-2", booked.event_key,
            date(2026, 6, 15), 60000, "PROMISE", None,
        ),
    ]  # fmt: skip
    (payable,) = [
        item
        for item in st.allocated.specialist_targets.customer_consideration
        if item.measure == "consideration_payable" and item.period_key == "FY2026-P06"
    ]
    assert payable.value == sum(flow.amount for flow in flows) == 5060000
    same = dataclasses.replace(ctx, txn_currency="USD")
    assert s13_books._payable_flows(same, st.allocated) == ()


def _fx_share_based_world() -> InputBundle:
    """FX-CHK-084-C (EUR contract in the USD-functional US01) plus a share-based promise of EUR
    10,000.00 measured by an element F 10,000.00 / E 500,000.00, with 100,000 units delivered and
    invoiced on 30 June 2026 (would-be reduction 2,000.00 EUR)."""
    bundle, _book = _bundle()
    (header,) = bundle.contracts
    key = f"{header.external_id}/SBC-FX"
    promise = dataclasses.replace(
        header.consideration_payable[0],
        amount=Decimal("10000.00"),
        committed_purchases=None,
        share_based=True,
    )
    header = dataclasses.replace(
        header, consideration_payable=(*header.consideration_payable, promise)
    )
    version = cpc_worlds.sbc_version(
        1,
        date(2026, 6, 1),
        True,
        "500000.00",
        key=key,
        element="SBC-FX",
        fair="10000.00",
        grant="2026-06-01",
        currency="EUR",
    )
    last = max(event.stream_version for event in bundle.events)
    contract = header.external_id
    events = [
        *bundle.events,
        bundles.event(
            contract,
            last + 1,
            "ESTIMATE_CHANGED",
            date(2026, 6, 1),
            {"estimate_version_id": version.version_key},
        ),
        bundles.event(
            contract,
            last + 2,
            "DELIVERY_RECORDED",
            date(2026, 6, 30),
            {"obligation_key": "L1-SUPPLY", "quantity": Decimal("100000"), "trigger": "DELIVERY"},
            obligation_keys=["L1-SUPPLY"],
        ),
        bundles.event(
            contract,
            last + 3,
            "BILLING_RECORDED",
            date(2026, 6, 30),
            {
                "invoice_number": "INV-FX-1",
                "line_external_id": "INV-FX-1-1",
                "obligation_key": "L1-SUPPLY",
                "amount": Decimal("100000.00"),
                "issue_date": date(2026, 6, 30),
            },
            obligation_keys=["L1-SUPPLY"],
        ),
    ]
    (book,) = bundle.books
    mapping = book.account_mapping
    rules = mapping.rules
    if not any(
        r.account_role == "BILLING_CLEARING" and r.clearing_purpose == "EQUITY" for r in rules
    ):
        rules = tuple(
            sorted(
                (
                    *rules,
                    MappingRuleInput(
                        "BILLING_CLEARING", "EQUITY", None, None, None, None, "3100", {}, 0, 0
                    ),
                ),
                key=lambda r: (r.account_role, r.clearing_purpose or "", r.account_code),
            )
        )
    book = dataclasses.replace(book, account_mapping=dataclasses.replace(mapping, rules=rules))
    return dataclasses.replace(
        bundle,
        contracts=(header,),
        group=dataclasses.replace(bundle.group, member_contract_keys=(contract,)),
        books=(book,),
        events=tuple(events),
        estimate_versions=(*bundle.estimate_versions, version),
        known_at=datetime(2026, 6, 30, 23, tzinfo=UTC),
    )


def test_foreign_share_based_part_fails_closed_under_revenue_driver() -> None:
    """D-91 (7), D-88 L7-6-Q-6: a foreign-currency share-based part has no stage 12 functional
    amount, so the FX-CHK-084-C world with a share-based element (would-be 2,000.00 EUR) fails
    closed in stage 14 through ``compute``."""
    with pytest.raises(EngineError) as raised:
        erev_engine.compute(_fx_share_based_world())
    error = raised.value
    assert error.code == "ENGINE_INVARIANT_VIOLATED"
    assert "stage 12 publishes no functional amount for a foreign-currency part target" in str(
        error.message
    )
    assert error.detail.get("measure") == "share_based_reduction_cum"
