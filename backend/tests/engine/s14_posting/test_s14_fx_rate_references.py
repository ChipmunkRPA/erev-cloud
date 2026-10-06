"""Rate references of foreign-currency lines and the posted remeasurement subject
(ENG-FXREM-RATEPIN-1; supervisor rulings R-11, R-12 and R-44 (b); ENGINE_SPEC_B S14-R-04 rev 1.165,
S14-R-28 and S14-INV-08 rev 1.50; S14-R-07, S12-R-02, S12-R-09; ENGINE_SPEC §0.4 rev 1.43
``PostedAmountInput.rate_refs``; 05 RCP-05 rev 1.202; 03 REQ-FX-006; 04 T-SL-04 ``subject_key`` rev
1.282 and ``ck_subledger_line__fx``; D-88 L7-6-Q-1; L2-5-Q-35).

The world is one USD contract of a GBP-functional entity built from public events
(``support.prop_worlds``): ten units of a point-in-time line of USD 1,000.00, delivered on 10
January 2026 and invoiced in full on 20 February. Rates USD to GBP: spot 0.8000 (1 January) and
0.8400 (20 February); average 0.8100 and closing 0.8200 for January.

- January: revenue 1,000.00 at the average is GBP 810.00, an asset layer (POL-162). The period end
  remeasures it to the closing rate, 820.00 (JET-10a, Dr CONTRACT_LIABILITY 10.00 / Cr FX_GAIN_LOSS
  10.00, the ``FX_REMEASUREMENT`` pass), and JET-06 presents 1,000.00 / 820.00.
- February: the reclass is reversed at 820.00, and the invoice settles the layer at spot, 840.00
  against 820.00 (JET-10a settlement, Dr CONTRACT_LIABILITY 20.00 / Cr FX_GAIN_LOSS 20.00, compute).

What failed (lane P7 record §4.26, the sixth volume-seed measurement). The ledger stored no
subject key, so the platform read a posted line without an obligation back as
``<contract>@<entity>`` (``erev_api.domain.contracts.bundles._posted``, decision L3-1-Q-32), while
stage 14 posts every JET-10 part under ``<group>@<entity>`` (Table 14-A). The next computation of
the same events therefore saw the posted remeasurement under a role key without a target and
reversed it — a foreign-currency line with no rate reference, which the ledger refuses — and
posted the cumulative remeasurement again. The in-memory platform kept the engine's subject keys,
so no suite without a database saw it.

The repair (ruling R-11 as amended; item ENG-COST-READBACK-1): the ledger stores the engine's
subject key on every line a product command writes and the read-back returns it (04 T-SL-04
``subject_key``), so a posted amount answers the role key it was posted for; the database half
is ``tests/domain/contracts/test_fx_remeasurement_recompute.py``. What stays in
the engine is the explicit regrouping rule of S14-R-04: there is one FX subject per group and
entity, so the remeasurements a contract posted while it belonged to another combination group —
stored under that group's key — attach to the current group's key and only the difference posts.

Two more producers of a foreign-currency line without a rate, both closed by S14-R-28: the JET-06
reversal of every foreign-currency contract, and any delta that only reverses posted amounts (a
void, a part that no longer arises after an earlier-dated event) — it converts nothing itself, so
it names the rates stamped on the posted lines it reverses.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

import pytest
from erev_engine import compute
from erev_engine.bundle import (
    BookOutput,
    FxRateInput,
    InputBundle,
    IntentLine,
    OutputBundle,
    PostedAmountInput,
    PostingIntent,
)
from erev_engine.errors import EngineError
from erev_engine.money import DECIMAL_CONTEXT
from support import intent_totals, platform_props
from support.prop_worlds import LineSpec, MeasureSpec, WorldSpec

BOOK = "ASC606"
ENTITY = "US01"
GROUP_SUBJECT = "CG-PROP@US01"  # <group>@<entity>, the JET-10 subject (Table 14-A)
OBLIGATION = "K-1/POB-01"
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
KEYS = (P01, P02, P03)
FX = "FX_REMEASUREMENT"
RECLASS, REVERSAL = "NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"
CL, GAIN_LOSS, UNBILLED = "CONTRACT_LIABILITY", "FX_GAIN_LOSS", "UNBILLED_RECEIVABLE"
RATE_SET = "FX@v1"
AVERAGE_P01 = "USDGBP-AVERAGE-FY2026-P01"
CLOSING_P01 = "USDGBP-CLOSING-FY2026-P01"
SPOT_FEB_20 = "USDGBP-SPOT-2026-02-20"

LINE = LineSpec("POB-01", "PIT", 100000, 10000, 10, 0, 0)  # 10 units, USD 1,000.00
DELIVERY = MeasureSpec("K-1", "POB-01", "DELIVERY", 9, 10)  # 10 January
BILLING = MeasureSpec("K-1", "POB-01", "BILLING", 50, 100000)  # 20 February
JANUARY = {P01: "closing", P02: "future", P03: "future"}
FEBRUARY = {P01: "closed", P02: "closing", P03: "future"}

# (period, entry kind, class, subject, side, role, transaction minor units, functional minor units)
Row = tuple[str, str, str, str, str, str, int, int]


def _rate(kind: str, on: date, period: str | None, value: str) -> FxRateInput:
    key = f"USDGBP-{kind.upper()}-{period or on.isoformat()}"
    return FxRateInput(key, RATE_SET, kind, "USD", "GBP", on, period, Decimal(value))


RATES = (
    _rate("spot", date(2026, 1, 1), None, "0.8000"),
    _rate("spot", date(2026, 2, 20), None, "0.8400"),
    _rate("average", date(2026, 1, 31), P01, "0.8100"),
    _rate("average", date(2026, 2, 28), P02, "0.8300"),
    _rate("average", date(2026, 3, 31), P03, "0.8350"),
    _rate("closing", date(2026, 1, 31), P01, "0.8200"),
    _rate("closing", date(2026, 2, 28), P02, "0.8500"),
    _rate("closing", date(2026, 3, 31), P03, "0.8600"),
)


def _world(
    measures: Sequence[MeasureSpec],
    states: Mapping[str, str],
    *,
    posted: Sequence[PostedAmountInput] = (),
    voids: Sequence[tuple[int, date]] = (),
    contracts: Sequence[str] = ("K-1",),
    group: str | None = None,
) -> InputBundle:
    """The bundle of ``contracts`` in one combination group: ``CG-PROP``, or ``group``."""
    bundle = platform_props.machine_bundle(
        WorldSpec("USD", tuple((contract, (LINE,)) for contract in contracts), tuple(measures)),
        voids=voids,
        period_states=states,
        posted=posted,
        books=(BOOK,),
        months=len(KEYS),
        functional_currency="GBP",
        fx_rates=RATES,
    )
    if group is None:
        return bundle
    return dataclasses.replace(bundle, group=dataclasses.replace(bundle.group, group_key=group))


def _pass(bundle: InputBundle, name: str) -> OutputBundle:
    """One close-run pass over ``bundle.posted`` alone (RCP-08(b))."""
    with decimal.localcontext(DECIMAL_CONTEXT):
        return intent_totals.close_pass(bundle, [], name)


def _book(output: OutputBundle) -> BookOutput:
    (book,) = output.books
    return book


def _intents(*outputs: OutputBundle) -> list[PostingIntent]:
    return [intent for output in outputs for intent in _book(output).posting_intents]


def _rows(*outputs: OutputBundle, kinds: Sequence[str] = ()) -> list[Row]:
    return sorted(
        (
            intent.posting_period_key,
            intent.entry_kind,
            intent.posting_class,
            intent.subject_key,
            line.side,
            line.account_role,
            line.amount_txn,
            line.amount_functional,
        )
        for intent in _intents(*outputs)
        if not kinds or intent.entry_kind in kinds
        for line in intent.lines
    )


def _rate_keys(output: OutputBundle, line: IntentLine) -> tuple[str, ...]:
    return tuple(rate_key for rate_key, _ in dict(_book(output).line_rates).get(line.line_key, ()))


def _stamp(rate_keys: Sequence[str]) -> str:
    """The one reference the platform stamps on the line: the latest effective date, ties to the
    greatest rate key (D-88 L7-6-Q-1; ``computation._rate_stamp``)."""
    dated = {rate.rate_key: rate.effective_date for rate in RATES}
    return max(rate_keys, key=lambda key: (dated[key], key))


def _ledger_read_back(*outputs: OutputBundle) -> tuple[PostedAmountInput, ...]:
    """RCP-05 as the platform answers it from T-SL-04 (``bundles._posted``; 04 rev 1.282): each
    posted amount under the subject key stored on its lines, which is the engine's, with the one
    rate stamped on each summed line as its ``rate_refs`` (``computation._rate_stamp``)."""
    versions = {rate.rate_key: rate.version_key for rate in RATES}
    stamps: dict[tuple[str, ...], set[tuple[str, str]]] = {}
    for output in outputs:
        book = _book(output)
        rates = dict(book.line_rates)
        for intent in book.posting_intents:
            for line in intent.lines:
                refs = rates.get(line.line_key, ())
                if not refs:
                    continue
                stamp = _stamp([rate_key for rate_key, _ in refs])
                grain = (
                    book.book_code,
                    intent.entity,
                    intent.subject_key,
                    intent.entry_kind,
                    line.account_role,
                    line.clearing_purpose or "",
                    intent.posting_period_key,
                    intent.origin_period_key or "",
                    intent.posting_class,
                )
                stamps.setdefault(grain, set()).add((stamp, versions[stamp]))
    return tuple(
        dataclasses.replace(item, rate_refs=tuple(sorted(stamps.get(_posted_order(item), ()))))
        for item in intent_totals.posted(*outputs)
    )


def _posted_order(item: PostedAmountInput) -> tuple[str, ...]:
    """The bundle order of ``posted`` (``s01_canonicalize.convert.assert_bundle_order``)."""
    return (
        item.book_code,
        item.entity_code,
        item.subject_key,
        item.entry_kind,
        item.account_role,
        item.clearing_purpose or "",
        item.period_key,
        item.origin_period_key or "",
        item.posting_class,
    )


def _january() -> platform_props.CloseRun:
    return platform_props.close_run(_world([DELIVERY], JANUARY))


def _february() -> platform_props.CloseRun:
    sealed = platform_props.sealed_through(_january().outputs, KEYS, P01)
    return platform_props.close_run(_world([DELIVERY, BILLING], FEBRUARY, posted=sealed))


def test_the_world_posts_both_remeasurements_under_the_group_subject() -> None:
    """The guard of the world: the January ``FX_REMEASUREMENT`` pass posts the period-end JET-10a
    10.00 and the February compute the settlement JET-10a 20.00, both functional-only and both
    under ``<group>@<entity>`` (Table 14-A), each naming the rates that produced it."""
    january, february = _january(), _february()
    assert _rows(*january.outputs, kinds=(FX,)) == [
        (P01, FX, "TIME", GROUP_SUBJECT, "C", GAIN_LOSS, 0, 1000),
        (P01, FX, "TIME", GROUP_SUBJECT, "D", CL, 0, 1000),
    ]
    assert _rows(*february.outputs, kinds=(FX,)) == [
        (P02, FX, "EVENT", GROUP_SUBJECT, "C", GAIN_LOSS, 0, 2000),
        (P02, FX, "EVENT", GROUP_SUBJECT, "D", CL, 0, 2000),
    ]
    period_end = next(i for i in _intents(*january.outputs) if i.entry_kind == FX)
    for line in period_end.lines:
        assert _rate_keys(january.passes[0], line) == (CLOSING_P01,)
    settlement = next(i for i in _intents(february.command) if i.entry_kind == FX)
    for line in settlement.lines:
        assert _rate_keys(february.command, line) == (CLOSING_P01, SPOT_FEB_20)
        assert _stamp(_rate_keys(february.command, line)) == SPOT_FEB_20


def test_eng_fxrem_ratepin_1_a_compute_over_the_ledger_read_back_posts_nothing() -> None:
    """S14-INV-02 over the ledger's own answer: the February events computed again over the lines
    posted so far, read back as the platform reads them, post nothing. The read-back answers the
    settlement under the stored ``<group>@<entity>`` key with the one rate stamped on its lines;
    before 04 rev 1.282 it answered ``<contract>@<entity>``, and the settlement was reversed
    without a rate reference (the line the ledger refused) and posted a second time."""
    january, february = _january(), _february()
    read_back = _ledger_read_back(*january.outputs, february.command)
    remeasurements = [item for item in read_back if item.entry_kind == FX]
    assert {item.subject_key for item in remeasurements} == {GROUP_SUBJECT}
    assert {item.rate_refs for item in remeasurements if item.posting_class == "EVENT"} == {
        ((SPOT_FEB_20, RATE_SET),)
    }
    again = compute(_world([DELIVERY, BILLING], FEBRUARY, posted=read_back))
    assert _intents(again) == []


def test_eng_fxrem_ratepin_1_the_fx_pass_does_not_repost_a_posted_remeasurement() -> None:
    """The close-run half: the February ``FX_REMEASUREMENT`` pass over the ledger read-back holds
    no entry, because the January period-end 10.00 is posted and the layer is settled before the
    February period end (S12-R-13: a locked period's remeasurement is never reposted)."""
    january, february = _january(), _february()
    read_back = _ledger_read_back(*january.outputs, february.command)
    remeasured = _pass(_world([DELIVERY, BILLING], FEBRUARY, posted=read_back), FX)
    assert _rows(remeasured, kinds=(FX,)) == []


def _singletons_closed_for_january() -> tuple[PostedAmountInput, ...]:
    """K-1 and K-2, each a combination group of its own (``CG-K1``, ``CG-K2``), delivered in
    January and closed for it: each group's period-end JET-10a 10.00 is posted under its own
    ``<group>@<entity>`` key, which is what the ledger stores."""
    sealed = []
    for contract, group in (("K-1", "CG-K1"), ("K-2", "CG-K2")):
        delivery = dataclasses.replace(DELIVERY, contract=contract)
        run = platform_props.close_run(
            _world([delivery], JANUARY, contracts=(contract,), group=group)
        )
        assert _rows(*run.outputs, kinds=(FX,)) == [
            (P01, FX, "TIME", f"{group}@{ENTITY}", "C", GAIN_LOSS, 0, 1000),
            (P01, FX, "TIME", f"{group}@{ENTITY}", "D", CL, 0, 1000),
        ]
        sealed.append(platform_props.sealed_through(run.outputs, KEYS, P01))
    return platform_props.merge_sealed(*sealed)


def test_s14_r_04_regrouping_posted_remeasurements_attach_to_the_current_group() -> None:
    """The regrouping rule of S14-R-04 (rev 1.165; rulings R-11 and R-44 (b)) for the FX subject.
    K-1 and K-2 are combined into ``CG-PROP`` after January was closed while each was its own
    group. Their posted remeasurements are stored under ``CG-K1@US01`` and ``CG-K2@US01``; there
    is one FX subject per group and entity, so both answer ``CG-PROP@US01``: the combined group
    reverses neither and its February pass posts February's own remeasurement only, 2 × 1,000.00
    × (0.8500 − 0.8200) = 60.00. The stored keys alone would reverse 10.00 under each former
    group's key and post 80.00 under the new one — the same 60.00 through three entries."""
    sealed = _singletons_closed_for_january()
    assert {item.subject_key for item in sealed if item.entry_kind == FX} == {
        f"CG-K1@{ENTITY}",
        f"CG-K2@{ENTITY}",
    }
    deliveries = [DELIVERY, dataclasses.replace(DELIVERY, contract="K-2")]
    combined = platform_props.close_run(
        _world(deliveries, FEBRUARY, posted=sealed, contracts=("K-1", "K-2"))
    )
    assert _rows(*combined.outputs, kinds=(FX,)) == [
        (P02, FX, "TIME", GROUP_SUBJECT, "C", GAIN_LOSS, 0, 6000),
        (P02, FX, "TIME", GROUP_SUBJECT, "D", CL, 0, 6000),
    ]
    # Every other posted amount answers the role key of its stored subject: the obligations keep
    # theirs through the combination, so revenue posts nothing and each reclass is reversed once.
    assert {i.subject_key for i in _intents(*combined.outputs) if i.entry_kind != FX} == {
        "K-1/POB-01",
        "K-2/POB-01",
    }
    assert _rows(*combined.outputs, kinds=("REVENUE_RECOGNITION",)) == []


def test_s14_r_04_regrouping_with_the_period_still_open_posts_nothing() -> None:
    """The same combination while January is still open: the combined target of January, 20.00,
    is what the two former groups have posted, so nothing is reversed and nothing posts."""
    sealed = _singletons_closed_for_january()
    deliveries = [DELIVERY, dataclasses.replace(DELIVERY, contract="K-2")]
    combined = platform_props.close_run(
        _world(deliveries, JANUARY, posted=sealed, contracts=("K-1", "K-2"))
    )
    assert _intents(*combined.outputs) == []


def test_the_jet_06_reversal_names_the_rates_of_the_reclass_it_negates() -> None:
    """S14-R-28: the February reversal is the negation of the January reclass (S14-R-07), whose
    functional amount is the asset carrying at the January closing rate (S12-R-09), so it names
    that reclass's rate references and its stamp is the January closing rate. Before rev 1.50 the
    reversal named none (12 such lines in FX-CHK-081)."""
    january, february = _january(), _february()
    reclass_pass, reversal_pass = january.passes[-1], february.passes[-1]
    assert _rows(reclass_pass, kinds=(RECLASS, REVERSAL)) == [
        (P01, RECLASS, "TIME", OBLIGATION, "C", CL, 100000, 82000),
        (P01, RECLASS, "TIME", OBLIGATION, "D", UNBILLED, 100000, 82000),
    ]
    assert _rows(reversal_pass, kinds=(RECLASS, REVERSAL)) == [
        (P02, REVERSAL, "TIME", OBLIGATION, "C", UNBILLED, 100000, 82000),
        (P02, REVERSAL, "TIME", OBLIGATION, "D", CL, 100000, 82000),
    ]
    reclass = next(i for i in _intents(reclass_pass) if i.entry_kind == RECLASS)
    reversal = next(i for i in _intents(reversal_pass) if i.entry_kind == REVERSAL)
    negated = {_rate_keys(reclass_pass, line) for line in reclass.lines}
    assert negated == {(CLOSING_P01,)}
    for line in reversal.lines:
        assert _rate_keys(reversal_pass, line) == (CLOSING_P01,)
        assert _stamp(_rate_keys(reversal_pass, line)) == CLOSING_P01


def test_every_foreign_currency_line_names_a_pinned_rate() -> None:
    """S14-INV-08 over both checkpoints: every line (all are USD lines of a GBP entity) names at
    least one rate reference and every reference is a pinned row of the bundle (REQ-FX-006)."""
    pinned = {(rate.rate_key, rate.version_key) for rate in RATES}
    seen = 0
    for run in (_january(), _february()):
        for output in run.outputs:
            rates = dict(_book(output).line_rates)
            for intent in _book(output).posting_intents:
                for line in intent.lines:
                    assert (line.txn_currency, line.functional_currency) == ("USD", "GBP")
                    refs = rates.get(line.line_key, ())
                    assert refs and set(refs) <= pinned, (intent.entry_kind, line.account_role)
                    seen += 1
    assert seen == 10  # January 2 + 2 + 2, February 2 + 2


def test_a_void_names_the_rates_of_the_posted_lines_it_reverses() -> None:
    """S14-R-28, a delta that only reverses posted amounts: the delivery is voided on 5 February
    after its January revenue was posted and January locked. The relief target is nil and no
    conversion of the computation stands behind the role key, so the carried reversal of the
    posted 1,000.00 / 810.00 names the rate stamped on the posted lines, the January average
    (``PostedAmountInput.rate_refs``). Before rev 1.50 the line named no rate and the ledger's
    ``ck_subledger_line__fx`` refused the posting."""
    sealed = platform_props.sealed_through(_january().outputs, KEYS, P01)
    revenue = [item for item in sealed if item.entry_kind == "REVENUE_RECOGNITION"]
    assert {item.rate_refs for item in revenue} == {((AVERAGE_P01, RATE_SET),)}
    states = {P01: "closed", P02: "open", P03: "future"}
    voided = compute(_world([DELIVERY], states, posted=sealed, voids=[(0, date(2026, 2, 5))]))
    assert _rows(voided) == [
        (P02, "REVENUE_RECOGNITION", "EVENT", OBLIGATION, "C", CL, 100000, 81000),
        (P02, "REVENUE_RECOGNITION", "EVENT", OBLIGATION, "D", "REVENUE", 100000, 81000),
    ]
    (reversal,) = _intents(voided)
    assert reversal.origin_period_key == P01
    for line in reversal.lines:
        assert _rate_keys(voided, line) == (AVERAGE_P01,)


def test_a_late_billing_reverses_a_locked_reclass_at_its_posted_rate() -> None:
    """S14-R-28 with S14-R-07 (the stateful machine's case): January is locked with its reclass
    posted at the January closing carrying, 1,000.00 / 820.00; an invoice dated 20 January then
    arrives. The replay relieves the January revenue from the invoice's liability layer at spot
    0.8000, so no asset stands at the January period end: the January reclass target and the
    JET-10a remeasurement are gone. February still reverses the reclass ACTUALLY posted, and the
    ``FX_REMEASUREMENT`` pass takes back the posted 10.00 (S12-R-13) — both name the January
    closing rate stamped on the posted lines; the revenue carry (810.00 to 800.00, no transaction
    amount) names the spot rate of its layer."""
    sealed = platform_props.sealed_through(_january().outputs, KEYS, P01)
    late = dataclasses.replace(BILLING, day=19)  # 20 January
    run = platform_props.close_run(_world([DELIVERY, late], FEBRUARY, posted=sealed))
    assert _rows(*run.outputs) == [
        (P02, FX, "TIME", GROUP_SUBJECT, "C", CL, 0, 1000),
        (P02, FX, "TIME", GROUP_SUBJECT, "D", GAIN_LOSS, 0, 1000),
        (P02, REVERSAL, "TIME", OBLIGATION, "C", UNBILLED, 100000, 82000),
        (P02, REVERSAL, "TIME", OBLIGATION, "D", CL, 100000, 82000),
        (P02, "REVENUE_RECOGNITION", "EVENT", OBLIGATION, "C", CL, 0, 1000),
        (P02, "REVENUE_RECOGNITION", "EVENT", OBLIGATION, "D", "REVENUE", 0, 1000),
    ]
    named = {
        (intent.entry_kind, _rate_keys(output, line))
        for output in run.outputs
        for intent in _book(output).posting_intents
        for line in intent.lines
    }
    assert named == {
        (FX, (CLOSING_P01,)),
        (REVERSAL, (CLOSING_P01,)),
        ("REVENUE_RECOGNITION", ("USDGBP-SPOT-2026-01-01",)),
    }


def test_s14_inv_08_a_foreign_currency_line_without_a_rate_reference_is_refused() -> None:
    """S14-INV-08: the void of the posted delivery again, but the posted amounts carry no rate
    reference (a read-back that does not supply ``rate_refs``). The engine then holds no rate for
    the reversal and refuses it by name before any intent is returned, instead of emitting a line
    the ledger's ``ck_subledger_line__fx`` would refuse."""
    sealed = tuple(
        dataclasses.replace(item, rate_refs=())
        for item in platform_props.sealed_through(_january().outputs, KEYS, P01)
    )
    states = {P01: "closed", P02: "open", P03: "future"}
    voided = _world([DELIVERY], states, posted=sealed, voids=[(0, date(2026, 2, 5))])
    with pytest.raises(EngineError) as refused:
        compute(voided)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.subject_key == OBLIGATION
    assert dict(refused.value.detail) == {
        "account_role": CL,
        "amount_functional": "-81000",
        "amount_txn": "-100000",
        "entry_kind": "REVENUE_RECOGNITION",
        "functional_currency": "GBP",
        "invariant": "S14-INV-08",
        "origin_period_key": P01,
        "posting_period_key": P02,
        "txn_currency": "USD",
    }


def test_posted_rate_references_are_ordered_in_the_bundle() -> None:
    """CV-45 for ``PostedAmountInput.rate_refs`` (ENGINE_SPEC §0.4 rev 1.43): the distinct
    references of a posted amount come in (rate key, version key) order; anything else is a
    malformed bundle."""
    sealed = list(platform_props.sealed_through(_january().outputs, KEYS, P01))
    sealed[0] = dataclasses.replace(
        sealed[0], rate_refs=((CLOSING_P01, RATE_SET), (AVERAGE_P01, RATE_SET))
    )
    with pytest.raises(ValueError, match="posted rate_refs is not sorted by its key"):
        compute(_world([DELIVERY], FEBRUARY, posted=sealed))
