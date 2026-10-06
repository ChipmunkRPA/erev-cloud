"""CLO-15 chunking as pure rules (ENGINE_SPEC_B S14-R-21; 05 ADP-11; 04 T-SL-07; BUILD_SPEC
CLO-15). CPU-only: ``summarise.chunk_entries`` and ``summarise.split_entry`` over planned entries,
and the sandbox branch of ``summarise.gl_target``. The calculation that writes the chunks is
witnessed in ``tests/domain/journals/test_chunking.py``."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final, cast
from uuid import UUID

import pytest
from erev_api.domain.journals import ports, summarise
from erev_api.domain.journals.summarise import DetailLine, EntryPlan
from erev_api.enums import GlAdapter, JournalRunGrain

LIABILITY: Final = UUID("00000000-0000-4000-8000-00000000f001")
HARDWARE: Final = UUID("00000000-0000-4000-8000-00000000f002")
SERVICE: Final = UUID("00000000-0000-4000-8000-00000000f003")
ACCOUNTS: Final = {
    LIABILITY: ("21001", "CONTRACT_LIABILITY"),
    HARDWARE: ("5001", "REVENUE"),
    SERVICE: ("5002", "REVENUE"),
}
FIRST: Final = UUID("00000000-0000-4000-8000-00000000d001")
SECOND: Final = UUID("00000000-0000-4000-8000-00000000d002")
THIRD: Final = UUID("00000000-0000-4000-8000-00000000d003")
CODES: Final = frozenset({"product"})
DEFAULT: Final = JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS


def _line(seq: int, contract: UUID, account: UUID, amount: str, **over: Any) -> DetailLine:
    code, role = ACCOUNTS[account]
    values: dict[str, Any] = {
        "id": UUID(int=seq),
        "book_code": "ASC606",
        "sign": 1,
        "chain_seq": seq,
        "posting_kind": "ENGINE_COMPUTE",
        "entry_kind": "REVENUE_RECOGNITION",
        "account_role": role,
        "gl_account_id": account,
        "gl_account_code": code,
        "dimensions": {"product": "P-100"},
        "txn_currency": "USD",
        "amount_txn": Decimal(amount),
        "functional_currency": "USD",
        "amount_functional": Decimal(amount),
        "contract_id": contract,
        "obligation_id": None,
        "legacy_key": None,
    }
    values.update(over)
    return DetailLine(**values)


def _pair(seq: int, contract: UUID, revenue: UUID, amount: str) -> list[DetailLine]:
    """Dr contract liability / Cr revenue of one contract."""
    return [
        _line(seq, contract, LIABILITY, amount),
        _line(seq + 1, contract, revenue, f"-{amount}"),
    ]


def _planned(lines: list[DetailLine]) -> tuple[list[EntryPlan], dict[UUID, DetailLine]]:
    [(currency, _, plans)] = summarise.plan_batches(lines, grain=DEFAULT, dimension_codes=CODES)
    assert currency == "USD"
    return plans, {line.id: line for line in lines}


def _shape(chunks: list[list[EntryPlan]]) -> list[list[list[tuple[str, Decimal]]]]:
    """Per chunk, per entry: (account code, net transaction amount) of each line."""
    return [
        [[(line.gl_account_code, line.net_txn) for line in plan.lines] for plan in chunk]
        for chunk in chunks
    ]


def test_s14_r21_an_entry_larger_than_the_limit_is_split_by_contract() -> None:
    """With a limit of two lines, the entry Dr 21001 150.00 / Cr 5001 100.00 / Cr 5002 50.00 of
    two contracts becomes one entry per contract — each balancing in both currencies — in two
    chunks; nothing is split across a chunk boundary."""
    lines = [*_pair(1, FIRST, HARDWARE, "100.00"), *_pair(3, SECOND, SERVICE, "50.00")]
    plans, details = _planned(lines)
    assert _shape([plans]) == [
        [[("21001", Decimal("150.00")), ("5001", Decimal("-100.00")), ("5002", Decimal("-50.00"))]]
    ]
    chunks = summarise.chunk_entries(plans, 2, details=details, dimension_codes=CODES)
    assert _shape(chunks) == [
        [[("21001", Decimal("100.00")), ("5001", Decimal("-100.00"))]],
        [[("21001", Decimal("50.00")), ("5002", Decimal("-50.00"))]],
    ]
    for chunk in chunks:
        written = [line for plan in chunk for line in plan.lines]
        assert sum(line.net_txn for line in written) == 0
        assert sum(line.net_functional for line in written) == 0
        assert {line.grain for line in written} == {JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS}
        assert {plan.entry_kind for plan in chunk} == {"REVENUE_RECOGNITION"}
    # every detail line is in exactly one written line
    seen = [
        line_id
        for chunk in chunks
        for plan in chunk
        for line in plan.lines
        for line_id in line.line_ids
    ]
    assert sorted(seen) == sorted(details)


def test_s14_r21_a_line_of_a_split_entry_is_traced_at_the_grain_it_was_summarised_at() -> None:
    """04 T-SL-06 drill-back rev 1.288 (item SUBLEDGER-LINE-JOURNAL-RUN-1 — PRODUCT DEFECT of the
    drill, measured through the product on 2026-10-02): a journal line carries the grouping hash
    of the grain it was summarised at — the run's, or ``CONTRACT_ACCOUNT_DIMENSIONS`` for a line
    of an entry split by contract. ``summarise.lines_of_group`` finds a journal line's detail
    lines at either. Hashed at the run's grain alone, as the drill hashed, no detail line
    matched a line of a split entry: its drill answered an empty list."""
    lines = [*_pair(1, FIRST, HARDWARE, "100.00"), *_pair(3, SECOND, SERVICE, "50.00")]
    plans, details = _planned(lines)
    [whole] = plans

    def traced(sha256: str) -> list[UUID]:
        found = summarise.lines_of_group(lines, sha256, grain=DEFAULT, dimension_codes=CODES)
        return sorted(item.id for item in found)

    def at_the_runs_grain(sha256: str) -> list[UUID]:
        return [
            item.id
            for item in lines
            if summarise.grouping_sha256(summarise.grouping_key(item, DEFAULT, CODES)) == sha256
        ]

    # the entry whole: three lines at the run's grain, each traced to what it summarizes
    assert [len(line.line_ids) for line in whole.lines] == [2, 1, 1]
    for line in whole.lines:
        assert (
            traced(line.sha256) == sorted(line.line_ids) == sorted(at_the_runs_grain(line.sha256))
        )
    # the entry split by contract: four lines at the split grain, one detail line each
    parts = summarise.split_entry(whole, 2, details=details, dimension_codes=CODES)
    written = [line for part in parts for line in part.lines]
    assert [len(line.line_ids) for line in written] == [1, 1, 1, 1]
    for line in written:
        assert traced(line.sha256) == list(line.line_ids)
        assert at_the_runs_grain(line.sha256) == []  # what the drill answered until rev 1.288
    # the four are a partition of the entry's detail lines
    assert sorted(line_id for line in written for line_id in traced(line.sha256)) == sorted(details)
    # the grains a line of a run can have: its run's and the split grain, once
    split = JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS
    assert summarise.SPLIT_GRAIN is split
    assert summarise.line_grains(DEFAULT) == (DEFAULT, split)
    assert summarise.line_grains(split) == (split,)
    assert summarise.line_grains(JournalRunGrain.LEGACY_CONTRACT_POB) == (
        JournalRunGrain.LEGACY_CONTRACT_POB,
        split,
    )


def test_adp_11_whole_entries_fill_a_chunk_and_no_limit_is_one_chunk() -> None:
    """Whole entries are taken in order until the limit would be exceeded (ADP-11): three
    contracts of two lines each under a limit of five give chunks of two entries and one; a limit
    the entry fits keeps it whole; no limit (``CSV``) keeps one chunk."""
    lines = [
        *_pair(1, FIRST, HARDWARE, "100.00"),
        *_pair(3, SECOND, SERVICE, "50.00"),
        *_pair(5, THIRD, HARDWARE, "25.00"),
    ]
    plans, details = _planned(lines)
    assert [len(plan.lines) for plan in plans] == [3]
    assert summarise.chunk_entries(plans, None, details=details, dimension_codes=CODES) == [plans]
    assert summarise.chunk_entries(plans, 3, details=details, dimension_codes=CODES) == [plans]
    assert summarise.chunk_entries([], 2, details={}, dimension_codes=CODES) == []
    assert summarise.chunk_entries([], None, details={}, dimension_codes=CODES) == []
    split = summarise.split_entry(plans[0], 2, details=details, dimension_codes=CODES)
    assert [len(plan.lines) for plan in split] == [2, 2, 2]
    packed = summarise.chunk_entries(split, 5, details=details, dimension_codes=CODES)
    assert [[len(plan.lines) for plan in chunk] for chunk in packed] == [[2, 2], [2]]
    # a run at the contract grain holds the same entry in six lines: it is split the same way
    [(_, _, by_contract)] = summarise.plan_batches(
        lines, grain=JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS, dimension_codes=CODES
    )
    assert [len(plan.lines) for plan in by_contract] == [6]
    again = summarise.chunk_entries(by_contract, 4, details=details, dimension_codes=CODES)
    assert [[len(plan.lines) for plan in chunk] for chunk in again] == [[2, 2], [2]]


def test_s14_r21_an_entry_no_chunk_can_hold_is_refused_by_name() -> None:
    """A contract's own part that still exceeds the limit cannot be split further while it
    balances: the calculation is refused by name, never exported out of balance."""
    lines = [
        _line(1, FIRST, LIABILITY, "150.00"),
        _line(2, FIRST, HARDWARE, "-100.00"),
        _line(3, FIRST, SERVICE, "-50.00"),
    ]
    plans, details = _planned(lines)
    with pytest.raises(summarise.ChunkingRefused) as refused:
        summarise.chunk_entries(plans, 2, details=details, dimension_codes=CODES)
    assert str(refused.value) == (
        "A journal entry of 3 lines cannot be split into chunks of at most 2 lines: the part of "
        f"contract {FIRST} alone has 3 lines."
    )


def test_adp_11_defaults_and_the_sandbox_target() -> None:
    """ADP-11: NetSuite 500, QuickBooks Online 250, CSV unlimited; a sandbox never takes an ERP
    adapter (DB-15) — ``gl_target`` answers ``CSV`` there without reading a connection."""
    assert dict(ports.DEFAULT_MAX_LINES) == {
        GlAdapter.CSV: None,
        GlAdapter.NETSUITE: 500,
        GlAdapter.QUICKBOOKS_ONLINE: 250,
    }
    target = summarise.gl_target(
        cast(Any, None), entity_id=UUID(int=1), entity_code="AVM-US", sandbox=True
    )
    assert (target.adapter, target.connection_id, target.max_lines) == (GlAdapter.CSV, None, None)
    assert set(summarise.GL_CONNECTION_ADAPTERS.values()) == set(GlAdapter)
