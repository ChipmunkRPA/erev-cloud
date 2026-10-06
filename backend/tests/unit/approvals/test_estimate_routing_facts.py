"""The routing facts of an estimate version as a pure function (PRD §2.5 ``ESTIMATE_VERSION``: "If
absolute P&L impact ≥ USD 50,000.00: 2: Controller"; 04 §16.10 rev 1.104; supervisor ruling R-41
(7) on the lane's independent review: the requirement enters the subject specification, so the
floor protects it).

The P&L impact of a version is the catch-up of its submission's dry run, in the contract currency.
``estimates.routing_facts`` turns it into the request's amount — the absolute impact in the
entity's functional currency — and the second-step flag, measured in USD. The database-bound
witness of the second step is ``tests/domain/contracts/test_estimates.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from erev_api.approvals import subjects
from erev_api.domain.contracts import estimates
from erev_api.enums import ApprovalSubjectType

FLAG = frozenset({subjects.ESTIMATE_PL_IMPACT_FLAG})
ONE = Decimal(1)


def _facts(
    catch_up: str,
    *,
    functional: str = "USD",
    to_functional: Decimal | None = ONE,
    to_threshold: Decimal | None = ONE,
) -> tuple[tuple[Decimal, str] | None, frozenset[str]]:
    """The facts of a version alone in its group: the group's catch-up is the contract's."""
    return estimates.routing_facts(
        Decimal(catch_up),
        functional_currency=functional,
        to_functional=to_functional,
        to_threshold=to_threshold,
        group_impact=abs(Decimal(catch_up)),
    )


def test_threshold_is_the_absolute_impact_of_usd_50_000() -> None:
    assert estimates.PL_IMPACT_THRESHOLD == Decimal("50000.00")
    assert estimates.THRESHOLD_CURRENCY == "USD"
    assert _facts("49999.99") == ((Decimal("49999.99"), "USD"), frozenset())
    assert _facts("50000.00") == ((Decimal("50000.00"), "USD"), FLAG)
    # Absolute: a downward revision of the same size takes the Controller's step too.
    assert _facts("-50000.00") == ((Decimal("50000.00"), "USD"), FLAG)
    assert _facts("-49999.99") == ((Decimal("49999.99"), "USD"), frozenset())
    assert _facts("0") == ((Decimal("0.00"), "USD"), frozenset())


def test_threshold_is_measured_in_usd_and_the_amount_in_the_functional_currency() -> None:
    """A EUR contract of a EUR entity: the amount stays EUR; the threshold reads the USD value."""
    amount, flags = _facts(
        "46000.00", functional="EUR", to_functional=ONE, to_threshold=Decimal("1.10")
    )
    assert (amount, flags) == ((Decimal("46000.00"), "EUR"), FLAG)  # USD 50,600.00
    amount, flags = _facts(
        "45000.00", functional="EUR", to_functional=ONE, to_threshold=Decimal("1.10")
    )
    assert (amount, flags) == ((Decimal("45000.00"), "EUR"), frozenset())  # USD 49,500.00
    # A JPY functional currency has no minor unit: the amount is rounded half up to whole yen.
    amount, _ = _facts(
        "100.00", functional="JPY", to_functional=Decimal("150.456"), to_threshold=ONE
    )
    assert amount == (Decimal("15046"), "JPY")


def test_missing_rate_fails_closed() -> None:
    """Without the rate to USD the threshold cannot be measured: the Controller's step applies.
    Without the rate to the functional currency the request states no amount."""
    assert _facts("100.00", to_threshold=None) == ((Decimal("100.00"), "USD"), FLAG)
    assert _facts("100.00", to_functional=None) == (None, frozenset())
    assert _facts("0.00", to_threshold=None) == ((Decimal("0.00"), "USD"), frozenset())


@dataclass(frozen=True)
class _Version:
    subject_key: str
    columns: dict[str, object]


@dataclass(frozen=True)
class _Book:
    book_code: str
    obligation_versions: tuple[_Version, ...]


def _book(code: str, *catch_ups: tuple[str, object]) -> _Book:
    return _Book(code, tuple(_Version(key, {"catch_up_amount": value}) for key, value in catch_ups))


def test_group_catch_up_sums_the_group_in_the_primary_book() -> None:
    """Supervisor ruling R-66 (4): the P&L impact of an estimate version sums every member
    contract of the combination group; it is measured in the tenant's primary book, else in every
    book the dry run produced with the largest absolute amount taken; no book, no figure."""
    measure = estimates.group_catch_up
    asc = _book("ASC606", ("K-1/O1", -3_000_000), ("K-1/O2", 1_000_000), ("K-2/O1", -4_000_000))
    ifrs = _book("IFRS15", ("K-1/O1", 9_000_000))
    # Every obligation of every member, summed, in absolute value: the primary book when it is
    # there.
    assert measure([asc], 2, "ASC606") == Decimal("60000.00")
    assert measure([asc, ifrs], 2, "ASC606") == Decimal("60000.00")
    assert measure([asc, ifrs], 2, "IFRS15") == Decimal("90000.00")
    # An entity that does not keep the primary book: the largest of its books.
    assert measure([asc, ifrs], 2, "LOCAL") == Decimal("90000.00")
    assert measure([asc], 2, "LOCAL") == Decimal("60000.00")
    # Amounts as the engine states them: minor units, exact fractions or decimal text; no amount.
    mixed = _book("ASC606", ("K-1/O1", Fraction(5, 2)), ("K-1/O2", "1.25"), ("K-1/O3", None))
    assert measure([mixed], 2, "ASC606") == Decimal("3.75")
    assert measure([_book("ASC606")], 2, "ASC606") == Decimal(0)
    # No book at all: no figure.
    assert measure([], 2, "ASC606") is None


def test_group_impact_is_the_measure_and_its_absence_fails_closed() -> None:
    def facts(own: str, group: Decimal | None) -> tuple[tuple[Decimal, str] | None, frozenset[str]]:
        return estimates.routing_facts(
            Decimal(own),
            functional_currency="USD",
            to_functional=ONE,
            to_threshold=ONE,
            group_impact=group,
        )

    # The group's figure is the impact, whatever the summary of the element's own contract says.
    assert facts("0.00", Decimal("80000.00")) == ((Decimal("80000.00"), "USD"), FLAG)
    assert facts("-1000.00", Decimal("49999.99")) == ((Decimal("49999.99"), "USD"), frozenset())
    assert facts("-60000.00", Decimal("50000.00")) == ((Decimal("50000.00"), "USD"), FLAG)
    # No book yields a figure: the threshold cannot be measured, so the Controller's step applies
    # even where the summary reads 0.00 (the fail-open path the second review traced).
    assert facts("0.00", None) == ((Decimal("0.00"), "USD"), FLAG)
    assert facts("0.00", Decimal(0)) == ((Decimal("0.00"), "USD"), frozenset())


def test_specification_carries_the_second_step() -> None:
    spec = subjects.SUBJECTS[ApprovalSubjectType.ESTIMATE_VERSION]
    assert spec.second_step_flags == FLAG
    assert spec.second_step_role == "controller"
    assert spec.required_permission == "estimate.approve"
