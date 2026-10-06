"""CLO-12 summarisation of manual adjustment lines as pure rules (ENGINE_SPEC_B S14-R-18 and
S14-R-19 rev 1.63; 04 T-SL-08; BUILD_SPEC CLO-12). CPU-only: ``summarise.grouping_key``,
``summarise.summarise`` and ``summarise.plan_entries`` over detail lines.

A line of entry kind ``MANUAL_ADJUSTMENT`` nets only with the lines of its own adjustment, so the
adjustment has a journal entry of its own with ``je_type = manual`` that names it; the keys of
every other kind are as they were."""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

import pytest
from erev_api.domain.journals import summarise
from erev_api.domain.journals.summarise import DetailLine
from erev_api.enums import JeType, JournalRunGrain

LIABILITY: Final = UUID("00000000-0000-4000-8000-00000000f001")
REVENUE: Final = UUID("00000000-0000-4000-8000-00000000f002")
CONTRACT: Final = UUID("00000000-0000-4000-8000-00000000d001")
OBLIGATION: Final = UUID("00000000-0000-4000-8000-00000000b001")
FIRST: Final = UUID("00000000-0000-4000-8000-00000000a001")
SECOND: Final = UUID("00000000-0000-4000-8000-00000000a002")
ACCOUNTS: Final = {LIABILITY: ("2400", "CONTRACT_LIABILITY"), REVENUE: ("4000", "REVENUE")}
GRAINS: Final = tuple(JournalRunGrain)
DEFAULT: Final = JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS
MANUAL: Final = "MANUAL_ADJUSTMENT"
CODES: Final = frozenset({"product"})


def _line(
    seq: int,
    account: UUID,
    amount: str,
    *,
    adjustment: UUID | None = None,
    entry_kind: str = "REVENUE_RECOGNITION",
    posting_kind: str = "ENGINE_COMPUTE",
) -> DetailLine:
    code, role = ACCOUNTS[account]
    return DetailLine(
        id=UUID(int=seq),
        book_code="ASC606",
        sign=1,
        chain_seq=seq,
        posting_kind=posting_kind,
        entry_kind=entry_kind,
        account_role=role,
        gl_account_id=account,
        gl_account_code=code,
        dimensions={"product": "P-100"},
        txn_currency="USD",
        amount_txn=Decimal(amount),
        functional_currency="USD",
        amount_functional=Decimal(amount),
        contract_id=CONTRACT,
        obligation_id=OBLIGATION,
        legacy_key="K-01|O1",
        manual_adjustment_id=adjustment,
    )


def _manual(seq: int, account: UUID, amount: str, adjustment: UUID | None) -> DetailLine:
    """A line of the adjustment's own posting; ``None`` is a line stage 14 posted."""
    kind = "ENGINE_COMPUTE" if adjustment is None else MANUAL
    return _line(seq, account, amount, adjustment=adjustment, entry_kind=MANUAL, posting_kind=kind)


def _entries(
    lines: list[DetailLine], grain: JournalRunGrain
) -> list[tuple[str, UUID | None, list[tuple[str, Decimal]]]]:
    """(je type, adjustment, [(account code, net amount)]) of each planned entry."""
    batches = summarise.plan_batches(lines, grain=grain, dimension_codes=CODES)
    assert [currency for currency, _, _ in batches] == ["USD"]
    return [
        (
            plan.je_type.value,
            plan.manual_adjustment_id,
            [(line.gl_account_code, line.net_txn) for line in plan.lines],
        )
        for plan in batches[0][2]
    ]


AUTOMATED: Final = [
    _line(1, LIABILITY, "9764.38"),
    _line(2, REVENUE, "-9764.38"),
]


@pytest.mark.parametrize("grain", GRAINS, ids=[grain.value for grain in GRAINS])
def test_s14_r19_manual_lines_are_an_entry_of_their_own(grain: JournalRunGrain) -> None:
    """The adjustment debits revenue and credits the contract liability — the accounts and the
    dimensions of the automated entry — and neither line nets with it."""
    lines = [
        *AUTOMATED,
        _manual(3, REVENUE, "150.00", FIRST),
        _manual(4, LIABILITY, "-150.00", FIRST),
    ]
    assert _entries(lines, grain) == [
        (
            JeType.MANUAL.value,
            FIRST,
            [("2400", Decimal("-150.00")), ("4000", Decimal("150.00"))],
        ),
        (
            JeType.AUTOMATED.value,
            None,
            [("2400", Decimal("9764.38")), ("4000", Decimal("-9764.38"))],
        ),
    ]


def test_s14_r19_one_manual_entry_per_adjustment() -> None:
    """Two adjustments on the same accounts give two entries; two lines of one adjustment on one
    account net to one line (S14-R-18)."""
    lines = [
        *AUTOMATED,
        _manual(3, REVENUE, "150.00", FIRST),
        _manual(4, LIABILITY, "-100.00", FIRST),
        _manual(5, LIABILITY, "-50.00", FIRST),
        _manual(6, REVENUE, "-40.00", SECOND),
        _manual(7, LIABILITY, "40.00", SECOND),
    ]
    assert _entries(lines, DEFAULT) == [
        (JeType.MANUAL.value, FIRST, [("2400", Decimal("-150.00")), ("4000", Decimal("150.00"))]),
        (JeType.MANUAL.value, SECOND, [("2400", Decimal("40.00")), ("4000", Decimal("-40.00"))]),
        (
            JeType.AUTOMATED.value,
            None,
            [("2400", Decimal("9764.38")), ("4000", Decimal("-9764.38"))],
        ),
    ]


def test_s14_r19_engine_posted_manual_lines_name_no_adjustment() -> None:
    """Lines of kind MANUAL_ADJUSTMENT that stage 14 posted (the reversal of a voided adjustment)
    carry no adjustment: they are a manual entry of their own, apart from the adjustment's."""
    lines = [
        _manual(1, REVENUE, "150.00", FIRST),
        _manual(2, LIABILITY, "-150.00", FIRST),
        _manual(3, REVENUE, "-150.00", None),
        _manual(4, LIABILITY, "150.00", None),
    ]
    assert _entries(lines, DEFAULT) == [
        (JeType.MANUAL.value, FIRST, [("2400", Decimal("-150.00")), ("4000", Decimal("150.00"))]),
        (JeType.MANUAL.value, None, [("2400", Decimal("150.00")), ("4000", Decimal("-150.00"))]),
    ]


def test_s14_r18_manual_key_ends_with_kind_and_adjustment() -> None:
    automated = _line(1, REVENUE, "-9764.38")
    manual = _manual(2, REVENUE, "150.00", FIRST)
    for grain in GRAINS:
        base = summarise.grouping_key(automated, grain, CODES)
        assert summarise.grouping_key(manual, grain, CODES) == (*base, MANUAL, str(FIRST))
        assert summarise.grouping_key(_manual(3, REVENUE, "1.00", None), grain, CODES) == (
            *base,
            MANUAL,
            "",
        )
    # The keys of the other kinds are those of table 14.3.2, member for member.
    assert [len(summarise.grouping_key(automated, grain, CODES)) for grain in GRAINS] == [
        {
            JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS: 6,
            JournalRunGrain.CONTRACT_ACCOUNT_DIMENSIONS: 7,
            JournalRunGrain.LEGACY_CONTRACT_POB: 5,
        }[grain]
        for grain in GRAINS
    ]
