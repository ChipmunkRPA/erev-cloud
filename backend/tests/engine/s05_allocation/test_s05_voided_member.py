"""D-98 78 (S05-R-10 rev 1.17 provisional; S01-R-13; S14-R-08): a member whose contract is VOIDED
computes end to end with every target 0.

F-CTR found that every request-void reaching the dry run was refused with ``TOTAL_SSP_ZERO``:
S01-R-13 removes every other event of the voided contract, stage 03 yields no obligation, and
stage 05 skipped allocation only for a routed-out member, so the voided member fell through to
``allocate`` over zero keys. The fix takes the general form of the D-88 guard (D-98 78 addendum):
the skip needs no obligation AND a zero allocation basis, whatever ``routed_out`` holds — the
voided member (no line at all) is its second instance; it is keyed neither on routed-out lines nor
on the void status. A non-voided member keeps its refusal (``PRODUCT_UNMAPPED`` here for the
unmapped product; ``TOTAL_SSP_ZERO`` for a zero-SSP member in
``test_s05_exceptions.test_l8_d_every_line_excluded_allocates_nothing``, and for T ≠ 0 with no
obligation in ``test_s05_allocation.test_d98_78_no_obligation_with_nonzero_basis_still_raises_
total_ssp_zero``). Fail-first: the three voided rows fail on the a07e03ef engine with
``TOTAL_SSP_ZERO``; the control passes before and after.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import erev_engine
import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import BookInput, ContractInput, EventInput, InputBundle, PostedAmountInput
from erev_engine.errors import EngineError
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
LINE_END = date(2026, 12, 31)
POB = f"{CONTRACT}/POB-01"


def _booking(price: str = "1200.00") -> EventInput:
    line = bundles.booking_line(
        "POB-01", quantity="1", total_price=price, start=INCEPTION, end=LINE_END
    )
    return bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def _event(stream: int, event_type: str, on: date, payload: Mapping[str, object]) -> EventInput:
    obligation = payload.get("obligation_key")
    keys = [obligation] if isinstance(obligation, str) else []
    return bundles.event(CONTRACT, stream, event_type, on, payload, obligation_keys=keys)


def _activated(stream: int) -> EventInput:
    return _event(stream, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})


def _voided(stream: int, on: date) -> EventInput:
    return _event(stream, "CONTRACT_VOIDED", on, {"reason_code": "DUPLICATE", "comment": "x"})


def _delivery(stream: int, on: date) -> EventInput:
    payload = {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "DELIVERY"}
    return _event(stream, "DELIVERY_RECORDED", on, payload)


def _with_policies(book: BookInput, overrides: Mapping[str, str]) -> BookInput:
    policies = tuple(
        dataclasses.replace(policy, value=overrides[policy.code])
        if policy.code in overrides and policy.scope == "GROUP"
        else policy
        for policy in book.policies
    )
    return dataclasses.replace(book, policies=policies)


def _bundle(
    *events: EventInput,
    contracts: Iterable[ContractInput] | None = None,
    posted: tuple[PostedAmountInput, ...] = (),
) -> InputBundle:
    """The stage 02 test world (``test_s02_rules.bundle``) with a ``posted`` history."""
    calendar = bundles.entity(start=INCEPTION, months=24, books=("ASC606",))
    headers = tuple(contracts or (bundles.contract(CONTRACT, inception=INCEPTION),))
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(_with_policies(bundles.book("ASC606", preset="DEFAULT", entity=calendar), {}),),
        entities=(calendar,),
        group=bundles.group(headers, products=(bundles.product(),)),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=posted,
    )


BEFORE_DELIVERY = (_booking(), _activated(2), _voided(3, date(2026, 2, 1)))
AFTER_DELIVERY = (
    _booking(),
    _activated(2),
    _delivery(3, date(2026, 2, 1)),
    _voided(4, date(2026, 3, 1)),
)


@pytest.mark.parametrize(
    "events",
    [
        pytest.param(BEFORE_DELIVERY, id="before_delivery"),
        pytest.param(AFTER_DELIVERY, id="after_delivery"),
    ],
)
def test_d98_78_voided_member_computes_with_every_target_zero(
    events: tuple[EventInput, ...],
) -> None:
    """The compute succeeds; the member is VOIDED in the book; no obligation version, no balance
    and no posting intent exists (nothing was posted, so nothing is reversed); no diagnostic."""
    output = erev_engine.compute(_bundle(*events))
    assert output.diagnostics == ()
    (book,) = output.books
    assert book.status_in_book == ((CONTRACT, "VOIDED"),)
    assert book.contract_version is not None
    assert book.contract_version.columns["status_in_book"] == "VOIDED"
    assert book.obligation_versions == ()
    assert book.posting_intents == ()
    population = _monetary_columns(book)
    assert population, (
        "no monetary balance column inspected (C6-VOID-T1: the check must not be vacuous)"
    )
    nonzero = [item for item in population if item[3] not in (0, "0", "0.00")]
    assert not nonzero, f"{len(population)} monetary balance columns inspected; nonzero: {nonzero}"


def _monetary_columns(book: object) -> list[tuple[str, str, str, object]]:
    """(subject, period, column, value) of every monetary T-CON-09 balance column — the
    ``<role>_txn`` / ``<role>_functional`` entries of ``BalanceOut.columns`` (C6-VOID-T1: the
    amounts live in ``columns``, not as attributes)."""
    return [
        (balance.subject_key, balance.period_key, key, value)
        for balance in book.balances  # type: ignore[attr-defined]
        for key, value in balance.columns.items()
        if key.endswith(("_txn", "_functional"))
    ]


def test_d98_78_voided_member_reverses_what_was_posted() -> None:
    """With a posted history (the JET-02 entry of January: Cr REVENUE 1,200.00 / Dr
    UNBILLED_RECEIVABLE 1,200.00 on POB-01), the voided member's targets are 0, so stage 14's
    reversal path runs (S01-R-13 "stage 14 reverses everything posted"): one entry with Dr REVENUE
    1,200.00 / Cr UNBILLED_RECEIVABLE 1,200.00, every line carrying ``reason_code`` VOID (S14-R-08)
    because the book loop binds the newly voided member into stage 14 (D-98 80; before it the
    reversal carried ``None``)."""
    revenue_credit = PostedAmountInput(
        "ASC606",
        "US01",
        POB,
        "REVENUE_RECOGNITION",
        "REVENUE",
        None,
        None,
        "FY2026-P01",
        None,
        "EVENT",
        "USD",
        "USD",
        -120_000,
        -120_000,
    )
    receivable_debit = dataclasses.replace(
        revenue_credit,
        account_role="UNBILLED_RECEIVABLE",
        amount_txn=120_000,
        amount_functional=120_000,
    )
    posted = (revenue_credit, receivable_debit)  # the balanced JET-02 entry once posted
    output = erev_engine.compute(_bundle(*AFTER_DELIVERY, posted=posted))
    assert output.diagnostics == ()
    (book,) = output.books
    assert book.status_in_book == ((CONTRACT, "VOIDED"),)
    assert book.obligation_versions == ()
    lines = sorted(
        (line.account_role, line.side, line.amount_txn)
        for intent in book.posting_intents
        for line in intent.lines
    )
    assert lines == [("REVENUE", "D", 120_000), ("UNBILLED_RECEIVABLE", "C", 120_000)], lines
    assert [intent.reason_code for intent in book.posting_intents] == ["VOID"]  # S14-R-08


def test_d98_78_non_voided_member_keeps_its_refusal() -> None:
    """The same world without the void is refused as before — by stage 03 (``PRODUCT_UNMAPPED``:
    the product has no SSP mapping), before allocation is reached; the operative stage 05 guard
    skips allocation only when there is no obligation AND the allocation basis is 0, and this
    world has its obligation, so the guard does not apply to it. ``TOTAL_SSP_ZERO`` for a zero-SSP
    member is pinned by
    ``test_s05_exceptions.test_l8_d_every_line_excluded_allocates_nothing`` and for T ≠ 0 with no
    obligation by ``test_s05_allocation.test_d98_78_no_obligation_with_nonzero_basis_still_raises_
    total_ssp_zero``."""
    with pytest.raises(EngineError) as raised:
        erev_engine.compute(_bundle(_booking(), _activated(2)))
    assert raised.value.code == "PRODUCT_UNMAPPED"


def test_d98_80_book_loop_binds_new_voids_into_stage_14() -> None:
    """The ``voided`` keyword the book loop binds (S14-R-08; D-98 80): the member contracts whose
    NEW events include a ``CONTRACT_VOIDED``. With no previous stream head every event is new, so
    the voided contract is bound; with the head at or past the void's stream version the void is
    old (its reversal was produced by an earlier computation) and nothing is bound; a world without
    a void binds nothing."""
    from erev_engine.stages import s01_canonicalize, s13_books
    from erev_engine.trace import TraceBuilder

    def canonical(bundle: InputBundle):  # noqa: ANN202 - CanonicalBundle
        return s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))

    new_void = _bundle(*AFTER_DELIVERY)
    assert s13_books.voided_members(canonical(new_void)) == (CONTRACT,)
    old_void = dataclasses.replace(
        new_void, group=dataclasses.replace(new_void.group, previous_stream_heads=((CONTRACT, 4),))
    )
    assert s13_books.voided_members(canonical(old_void)) == ()
    assert s13_books.voided_members(canonical(_bundle(_booking(), _activated(2)))) == ()
