"""A period end that is locked at the run's cutoff is the lock's: ``reports.locked_ends`` without
a database (ENGINE_SPEC_B S15-R-20 rev 1.168; 04 §16.9 rev 1.313; item
RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's rulings of 2026-10-02).

The rows of a lock's ``CONTRACT_BALANCES`` dataset are read as balances by contract, their three
roll-forward balances are compared per currency with the closing control totals of the same
lock's ``CONTRACT_BALANCE_ROLLFORWARD`` dataset, and a ``LOCK`` record is read by a run only
where it froze its datasets by the run's cutoff. A ``LOCK`` record without a manifest froze
nothing — the product never writes one; the shared test fixture
``support.close_world.periods_closed_before`` does — and is read from the versions. The refusals
by name are witnessed here over a stand-in session: the product leaves no lock without its
datasets to witness them on. The database witness is
``tests/domain/reports/test_rollforward_locked_ends_db.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports import locked, locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceBinding, contract_balances
from erev_api.domain.reports.outputs import ROW_KEY
from erev_api.problems import Problem

FROZEN = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
LATER = FROZEN + timedelta(minutes=5)
MANIFEST = "ab" * 32
ENTITY, LOCK = UUID(int=1), UUID(int=7)
FEBRUARY = tie_outs.PeriodRef(
    id=UUID(int=2),
    key="FY2026-P02",
    name="Feb 2026",
    fiscal_year=2026,
    period_no=2,
    quarter_no=1,
    start=date(2026, 2, 1),
    end=date(2026, 2, 28),
)
HEADER = (
    f"{ROW_KEY},contract_external_id,customer_name,entity_code,currency,"
    "contract_liability,contract_asset,unbilled_receivable\n"
)
CONTENT = (HEADER + "contract:C-1:AVM-US,C-1,Pellworth,AVM-US,USD,100.00,5.00,\n").encode()
AGREEING = {
    "closing_contract_liability": {"USD": "100.00"},
    "closing_contract_asset": {"USD": "5.00"},
}


def _row(contract: str, currency: str = "USD", **measures: str) -> dict[str, str]:
    return {
        ROW_KEY: f"contract:{contract}:AVM-US",
        "contract_external_id": contract,
        "customer_name": "Pellworth",
        "entity_code": "AVM-US",
        "currency": currency,
        **measures,
    }


# --- the rows and the comparison ------------------------------------------------------------------


def test_the_rows_of_a_dataset_are_balances_by_contract() -> None:
    """Every column that is not an identity or a label is a money measure; an empty cell is 0."""
    rows = locked_ends.rows_of(
        [
            _row("C-1", contract_liability="39708.49", contract_asset="", loss_provision="0.00"),
            _row("C-2", currency="EUR", unbilled_receivable="-12.30"),
        ]
    )
    assert set(rows) == {"C-1", "C-2"}
    assert rows["C-1"].currency == "USD"
    assert rows["C-1"].values == {
        "contract_liability": Decimal("39708.49"),
        "contract_asset": Decimal("0"),
        "loss_provision": Decimal("0.00"),
    }
    assert rows["C-2"].currency == "EUR"
    assert rows["C-2"].values == {"unbilled_receivable": Decimal("-12.30")}


def test_the_checked_balances_are_measures_of_the_dataset() -> None:
    """The three balances compared are the roll-forward's own, and each is a money column of
    ``contract_balances`` — the dataset the rows are read from."""
    assert locked_ends.CHECKED is tie_outs.ROLLFORWARD_BALANCES
    measures = {name for name, _ in contract_balances.MEASURE_COLUMNS}
    assert set(locked_ends.CHECKED) <= measures
    assert not measures & locked_ends.NOT_A_MEASURE


@pytest.mark.parametrize(
    ("rows", "said"),
    [
        ([_row("C-1", contract_liability="12,5")], "column contract_liability holds '12,5'"),
        ([_row("", contract_liability="1.00")], "no contract_external_id"),
        ([_row("C-1"), _row("C-1")], "contract C-1 is stated twice"),
    ],
)
def test_a_dataset_that_cannot_be_read_as_balances_says_why(
    rows: list[dict[str, str]], said: str
) -> None:
    with pytest.raises(ValueError, match=said):
        locked_ends.rows_of(rows)


def test_the_three_balances_are_compared_with_the_closing_totals_per_currency() -> None:
    rows = locked_ends.rows_of(
        [
            _row("C-1", contract_liability="100.00", contract_asset="5.00"),
            _row("C-2", contract_liability="20.00", accounts_receivable="999.00"),
            _row("C-3", currency="EUR", unbilled_receivable="7.00"),
        ]
    )
    agreeing = {
        "closing_contract_liability": {"USD": "120.00"},
        "closing_contract_asset": {"USD": "5.00", "EUR": "0.00"},
        "closing_unbilled_receivable": {"EUR": "7.00"},
        "opening_contract_liability": {"USD": "1.00"},  # not compared: the closing alone
    }
    assert locked_ends.differences(rows, agreeing) == []
    apart = dict(agreeing) | {
        "closing_contract_liability": {"USD": "119.99"},
        "closing_unbilled_receivable": {},
    }
    assert locked_ends.differences(rows, apart) == [
        ("contract_liability", "USD", Decimal("120.00"), Decimal("119.99")),
        ("unbilled_receivable", "EUR", Decimal("7.00"), Decimal("0")),
    ]
    # a total the rows do not hold is a difference too
    assert locked_ends.differences({}, {"closing_contract_asset": {"GBP": "3.00"}}) == [
        ("contract_asset", "GBP", Decimal("0"), Decimal("3.00"))
    ]


def test_a_lock_record_is_read_where_it_froze_its_datasets_by_the_runs_cutoff() -> None:
    """The supervisor's ruling of 2026-10-02: a ``LOCK`` record without a manifest froze nothing
    and is read from the versions — the record only a test fixture writes. A run as of an
    instant before the lock's cutoff reads the versions too. The two cutoffs can be equal — an
    application clock ahead of the server's gives a run started after the lock the lock's own
    instant — and a run that finds the record at its cutoff reads it."""
    assert locked_ends.stands(MANIFEST, FROZEN, LATER)
    assert locked_ends.stands(MANIFEST, FROZEN, FROZEN)  # the tie: the record is there, so read
    assert not locked_ends.stands(None, FROZEN, LATER)  # froze nothing
    assert not locked_ends.stands(None, FROZEN, FROZEN)
    assert not locked_ends.stands(MANIFEST, FROZEN, FROZEN - timedelta(microseconds=1))
    assert not locked_ends.stands(MANIFEST, None, LATER)


# --- the reader over a stand-in session -----------------------------------------------------------


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def one_or_none(self) -> Any:
        return self._row

    def first(self) -> Any:
        return self._row

    def mappings(self) -> _Result:
        return self


class _Session:
    """Answers the reader's statements in the order it issues them."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)

    def execute(self, statement: Any) -> _Result:
        return _Result(self.answers.pop(0))


def _reader(
    monkeypatch: pytest.MonkeyPatch,
    *answers: Any,
    dataset: bytes | Exception = CONTENT,
    binding: SourceBinding | None = None,
    cutoff: datetime = LATER,
) -> tuple[locked_ends.Reader, _Session]:
    def read(uow: Any, *, report_code: str, lock_id: UUID) -> locked.LockedDataset:
        assert report_code == "contract_balances"
        if isinstance(dataset, Exception):
            raise dataset
        return locked.LockedDataset(
            lock_id=lock_id,
            kind="CONTRACT_BALANCES",
            file_id=UUID(int=9),
            file_sha256="aa" * 32,
            row_count=1,
            control_totals={},
            content=dataset,
        )

    monkeypatch.setattr(locked, "locked_dataset", read)
    session = _Session(*answers)
    params = ReportParams(
        report_code="contract_balance_rollforward",
        report_version=1,
        parameters={},
        entity_ids=(ENTITY,),
        known_at=cutoff,
        binding=binding,
    )
    reader = locked_ends.Reader(
        SimpleNamespace(session=session),  # type: ignore[arg-type]
        params,
        book_code="ASC606",
        cutoff=cutoff,
        entity_codes={ENTITY: "AVM-US"},
    )
    return reader, session


def _standing(manifest: str | None = MANIFEST, frozen: datetime | None = FROZEN) -> Any:
    return SimpleNamespace(id=LOCK, cutoff_known_at=frozen, snapshot_manifest_sha256=manifest)


def _closing(totals: dict[str, Any]) -> dict[str, Any]:
    return {"file_sha256": "bb" * 32, "control_totals": totals}


def _refusal(refused: Problem) -> str:
    assert isinstance(refused, locked_ends.LockedEndRefused)
    assert refused.status == 422
    (error,) = refused.errors
    assert (error.rule_id, error.field) == ("S15-R-20", "balances[AVM-US@FY2026-P02]")
    assert error.message == refused.detail
    return error.message


def test_the_lock_is_read_and_what_the_run_records_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, session = _reader(monkeypatch, _standing(), _closing(AGREEING))
    end = reader.at(ENTITY, FEBRUARY)
    assert end is not None and (end.lock_id, end.frozen_at) == (LOCK, FROZEN)
    assert end.rows["C-1"].values["contract_liability"] == Decimal("100.00")
    assert locked_ends.recorded(end) == {
        "lock_id": str(LOCK),
        "frozen_at": FROZEN.isoformat(),
        "balances_sha256": "aa" * 32,
        "rollforward_sha256": "bb" * 32,
    }
    assert reader.at(ENTITY, FEBRUARY) is end and session.answers == []  # resolved once


@pytest.mark.parametrize(
    "found",
    [None, _standing(manifest=None), _standing(frozen=LATER + timedelta(seconds=1))],
    ids=["no lock stands", "a record without a manifest", "frozen after the run's cutoff"],
)
def test_an_end_that_is_not_the_locks_is_read_from_the_versions(
    monkeypatch: pytest.MonkeyPatch, found: Any
) -> None:
    reader, session = _reader(monkeypatch, found)
    assert reader.at(ENTITY, FEBRUARY) is None
    assert session.answers == []  # no dataset was asked for


def test_a_lock_that_names_a_manifest_and_holds_no_dataset_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = locked.LockedRefusal("Lock holds no CONTRACT_BALANCES dataset for contract_balances.")
    reader, _ = _reader(monkeypatch, _standing(), None, dataset=missing)
    with pytest.raises(locked_ends.LockedEndRefused) as refused:
        reader.at(ENTITY, FEBRUARY)
    said = _refusal(refused.value)
    assert said == locked_ends.NO_DATASET.format(
        lock=LOCK, period="FY2026-P02", kind="CONTRACT_BALANCES"
    )
    assert "not read from the contract versions in its place" in said

    reader, _ = _reader(monkeypatch, _standing(), None)  # the roll-forward dataset is missing
    with pytest.raises(locked_ends.LockedEndRefused) as refused:
        reader.at(ENTITY, FEBRUARY)
    assert _refusal(refused.value) == locked_ends.NO_DATASET.format(
        lock=LOCK, period="FY2026-P02", kind="CONTRACT_BALANCE_ROLLFORWARD"
    )


def test_a_file_that_fails_its_hash_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = locked.LockedRefusal(locked.HASH_MISMATCH.format(kind="CONTRACT_BALANCES", lock=LOCK))
    reader, _ = _reader(monkeypatch, _standing(), SimpleNamespace(id=UUID(int=3)), dataset=failed)
    with pytest.raises(locked_ends.LockedEndRefused) as refused:
        reader.at(ENTITY, FEBRUARY)
    said = _refusal(refused.value)
    assert said.startswith("The CONTRACT_BALANCES dataset of lock ")
    assert "cannot be read as frozen" in said and failed.detail in said


def test_two_datasets_of_one_lock_that_differ_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    apart = AGREEING | {"closing_contract_liability": {"USD": "99.00"}}
    reader, _ = _reader(monkeypatch, _standing(), _closing(apart))
    with pytest.raises(locked_ends.LockedEndRefused) as refused:
        reader.at(ENTITY, FEBRUARY)
    assert _refusal(refused.value) == locked_ends.DIFFER.format(
        lock=LOCK,
        period="FY2026-P02",
        balance="contract_liability",
        currency="USD",
        balances=Decimal("100.00"),
        rollforward=Decimal("99.00"),
    )


def test_a_row_of_a_contract_the_read_does_not_hold_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, _ = _reader(monkeypatch, _standing(), _closing(AGREEING))
    assert reader.at(ENTITY, FEBRUARY) is not None
    said = _refusal(reader.unknown(ENTITY, FEBRUARY, "C-1"))
    assert said == locked_ends.UNKNOWN_CONTRACT.format(
        lock=LOCK, period="FY2026-P02", contract="C-1"
    )


def _bound(evidence: dict[str, Any]) -> SourceBinding:
    return SourceBinding(
        cutoff=LATER, versions={}, labels={}, row_keys=frozenset(), evidence=evidence
    )


def test_a_bound_run_reads_what_it_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """S15-R-24: no lock is looked for again. A binding without the kind was recorded before the
    rule and reads the versions; an end recorded as not locked reads the versions; an end
    recorded with its lock reads that lock; an end the record does not hold is refused."""
    key = locked_ends.key_of(ENTITY, FEBRUARY)
    reader, session = _reader(monkeypatch, binding=_bound({}))
    assert reader.at(ENTITY, FEBRUARY) is None and session.answers == []

    reader, _ = _reader(monkeypatch, binding=_bound({"locked_ends": {key: None}}))
    assert reader.at(ENTITY, FEBRUARY) is None

    entry = {
        "lock_id": str(LOCK),
        "frozen_at": FROZEN.isoformat(),
        "balances_sha256": "aa" * 32,
        "rollforward_sha256": "bb" * 32,
    }
    reader, session = _reader(
        monkeypatch, _closing(AGREEING), binding=_bound({"locked_ends": {key: entry}})
    )
    end = reader.at(ENTITY, FEBRUARY)
    assert end is not None and end.lock_id == LOCK and session.answers == []

    reader, _ = _reader(monkeypatch, binding=_bound({"locked_ends": {}}))
    with pytest.raises(Problem, match="holds no locked_ends"):
        reader.at(ENTITY, FEBRUARY)

    moved = entry | {"rollforward_sha256": "cc" * 32}
    reader, _ = _reader(
        monkeypatch, _closing(AGREEING), binding=_bound({"locked_ends": {key: moved}})
    )
    with pytest.raises(locked_ends.LockedEndRefused) as refused:
        reader.at(ENTITY, FEBRUARY)
    assert _refusal(refused.value) == locked_ends.NOT_AS_RECORDED.format(
        kind="CONTRACT_BALANCE_ROLLFORWARD", lock=LOCK, period="FY2026-P02"
    )
