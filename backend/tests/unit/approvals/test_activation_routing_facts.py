"""The routing facts of a contract activation, the parts that need no database (PRD §2.5 rows
``CONTRACT_ACTIVATION`` rev 1.194; 04 T-PLT-17, §16.3, §16.10 rev 1.287; 05 ADP-16, ADP-17 rev
1.204; item ACT-FLAGS-1, the supervisor's rulings of 2026-10-02; supervisor ruling R-66 (4)).

- the two thresholds read ONE amount in ONE stated currency, and an amount that cannot be judged
  is treated as above (``activation.threshold_flags``);
- what a dry run states for the routing: the largest transaction price of its books and whether
  any holds a financing adjustment (``activation.measured_by``);
- what a booking states beside its header (``activation._booking_flags``);
- the two terms of a booking are stored only when they are stated, so a booking that states
  neither is stored — and hashed — as it was before the members existed
  (``payloads.payload_json``);
- what a source object states of a term (``ports.stated_term``);
- the threshold currency is defined in one place.

The database-bound witnesses are ``tests/domain/contracts/test_activation_flags_db.py``.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from erev_api.approvals import routing, subjects
from erev_api.domain.contracts import activation, estimates, modifications
from erev_api.domain.integrations import ports
from erev_api.domain.journals import adjustments
from erev_api.enums import ApprovalSubjectType
from erev_api.events import payloads
from erev_engine.canonical import sha256_hex
from erev_engine.stages.s01_canonicalize import obligation_subject_key

ROOT = Path(__file__).resolve().parents[4]
ABOVE = frozenset({"ABOVE_THRESHOLD"})
BOTH = frozenset({"ABOVE_THRESHOLD", "ABOVE_CONTROLLER_THRESHOLD"})
UNJUDGED = BOTH | {"RATE_NOT_PUBLISHED"}


def _judged(
    in_dollars: str | None, *, functional: tuple[str, str] | None = ("1.00", "USD")
) -> activation.Judged:
    return activation.Judged(
        amount=Decimal("1.00"),
        currency="GBP",
        functional=None if functional is None else (Decimal(functional[0]), functional[1]),
        in_threshold_currency=None if in_dollars is None else Decimal(in_dollars),
    )


def test_the_two_thresholds_are_dollar_amounts_and_inclusive() -> None:
    assert subjects.THRESHOLD_CURRENCY == "USD"
    assert subjects.ACTIVATION_THRESHOLD == Decimal("100000.00")
    assert subjects.CONTROLLER_THRESHOLD == Decimal("1000000.00")
    assert activation.threshold_flags(_judged("99999.99")) == frozenset()
    assert activation.threshold_flags(_judged("100000.00")) == ABOVE
    assert activation.threshold_flags(_judged("999999.99")) == ABOVE
    assert activation.threshold_flags(_judged("1000000.00")) == BOTH
    assert activation.threshold_flags(_judged("0.00")) == frozenset()


def test_an_amount_that_cannot_be_judged_is_treated_as_above() -> None:
    """The supervisor's rulings of 2026-10-02. No rate to the threshold currency: the amount
    cannot be judged, so both threshold flags stand with ``RATE_NOT_PUBLISHED`` — treated as
    above, never as below. No rate to the functional currency ALONE: the dollar amount is known
    and is judged by its value — a flag is a fact an approver reads —, and ``RATE_NOT_PUBLISHED``
    says that the request states no functional amount."""
    assert activation.threshold_flags(_judged(None)) == UNJUDGED
    assert activation.threshold_flags(_judged(None, functional=None)) == UNJUDGED
    only = frozenset({"RATE_NOT_PUBLISHED"})
    assert activation.threshold_flags(_judged("12.00", functional=None)) == only
    assert activation.threshold_flags(_judged("100000.00", functional=None)) == only | ABOVE
    assert activation.threshold_flags(_judged("1000000.00", functional=None)) == only | BOTH
    assert _judged(None).rate_missing and _judged("12.00", functional=None).rate_missing
    assert not _judged("12.00").rate_missing


def test_a_rate_that_is_not_published_takes_the_controllers_step_by_itself() -> None:
    """The supervisor's ruling of 2026-10-02 (point 4): a request without a functional amount is
    one no tenant's amount rule can read, so it must not pass such a rule unseen —
    ``RATE_NOT_PUBLISHED`` is a second-step flag of the subject, beside the Controller's
    threshold: the routing floor of a request that carries it alone has the second step, held by
    a Controller."""
    spec = subjects.spec_for(ApprovalSubjectType.CONTRACT_ACTIVATION)
    assert spec.second_step_flags == {"ABOVE_CONTROLLER_THRESHOLD", "RATE_NOT_PUBLISHED"}
    assert activation.RATE_NOT_PUBLISHED is subjects.RATE_NOT_PUBLISHED
    first = ("Approval", "contract.approve", 1, None)
    second = ("Second approval", "contract.approve", 1, "controller")
    assert routing.floor_items(spec, ["ABOVE_THRESHOLD", "NEW_SKU"]) == [first]
    assert routing.floor_items(spec, ["RATE_NOT_PUBLISHED"]) == [first, second]
    assert routing.floor_items(spec, ["ABOVE_CONTROLLER_THRESHOLD"]) == [first, second]


def _output(*books: dict[str, Any] | None, obligations: dict[str, str] | None = None) -> Any:
    """An output as ``measured_by`` reads it: a book a member (None: the LEGACY book, which holds
    no contract version), each with the obligation versions given — subject key to kind."""
    versions = [
        SimpleNamespace(subject_key=key, columns={"obligation_kind": kind})
        for key, kind in (obligations or {}).items()
    ]
    return SimpleNamespace(
        books=[
            SimpleNamespace(
                contract_version=None if columns is None else SimpleNamespace(columns=columns),
                obligation_versions=versions,
            )
            for columns in books
        ]
    )


def test_a_dry_run_states_its_largest_price_and_any_financing_adjustment() -> None:
    """``measured_by``: integer minor units, exact fractions and decimals are read alike; the
    LEGACY book holds no contract version and is passed over; the price is an absolute amount."""
    measured = activation.measured_by(
        _output(
            {"transaction_price": 3_000_000, "financing_adjustment_amount": 0},
            None,
            {"transaction_price": Fraction(70001, 2), "financing_adjustment_amount": Decimal("0")},
        ),
        "USD",
        "SF-ORD-1",
    )
    assert measured == activation.Measured(transaction_price=Decimal("35000.5"), financing=False)
    financed = activation.measured_by(
        _output({"transaction_price": -44_359_283, "financing_adjustment_amount": -5_640_717}),
        "USD",
        "SF-ORD-1",
    )
    assert financed == activation.Measured(transaction_price=Decimal("443592.83"), financing=True)
    # A currency without minor units: the engine's integer is the amount.
    assert activation.measured_by(_output({"transaction_price": 1_000_000}), "JPY", "X") == (
        activation.Measured(transaction_price=Decimal("1000000"), financing=False)
    )
    # No book with a contract version: nothing is measured, and the booking alone is judged.
    assert activation.measured_by(_output(None), "USD", "X") == activation.Measured(None, False)


def test_a_dry_run_states_the_kinds_of_the_contracts_own_obligations() -> None:
    """``measured_by``: the kind of the template the engine gave each line of THIS contract — a
    ``POB_ASSIGNMENT`` rule, or S03-R-18 of the parity preset, may give a line another template
    than its product's default, and only the computation says which. A sibling of a combined
    group states nothing of this contract, nor does a contract whose external id merely begins
    with this one's; an external id is compared as the engine encodes it (CV-21)."""
    output = _output(
        {"transaction_price": 100},
        obligations={
            "SF-ORD-1/O1": "STANDARD",
            "SF-ORD-1/O2": "MATERIAL_RIGHT",
            "SF-ORD-10/O1": "VC_LINE",
            "SF-ORD-2/O1": "SERVICE_WARRANTY",
            obligation_subject_key("ORD/7", "O1"): "VC_LINE",
        },
    )
    assert activation.measured_by(output, "USD", "SF-ORD-1").kinds == {
        "STANDARD",
        "MATERIAL_RIGHT",
    }
    assert activation.measured_by(output, "USD", "SF-ORD-10").kinds == {"VC_LINE"}
    assert activation.measured_by(output, "USD", "ORD/7").kinds == {"VC_LINE"}
    assert activation.measured_by(output, "USD", "ORD").kinds == frozenset()
    assert activation.measured_by(output, "USD", "SF-ORD-3").kinds == frozenset()
    # The LEGACY book states no kinds: it holds no contract version.
    assert activation.measured_by(
        _output(None, obligations={"SF-ORD-1/O1": "VC_LINE"}), "USD", "SF-ORD-1"
    ) == activation.Measured(None, False)


LINE: dict[str, Any] = {"obligation_key": "O1", "product_code": "P", "quantity": "1"}


@pytest.mark.parametrize(
    ("booking", "flagged"),
    [
        ({"lines": [LINE]}, False),
        ({"lines": [{**LINE, "scope_flag": "IN_SCOPE_606", "account_overrides": None}]}, False),
        ({"lines": [{**LINE, "ssp_version_label": "2026-H1"}]}, False),
        ({"lines": [LINE], "consideration_payable": [], "noncash_consideration": []}, False),
        ({"lines": [LINE], "consideration_payable": [{"amount": {"amount": "1.00"}}]}, True),
        ({"lines": [LINE], "noncash_consideration": [{"units": "1"}]}, True),
        ({"lines": [{**LINE, "scope_flag": "LEASE_842"}]}, True),
        ({"lines": [{**LINE, "out_of_scope_amount": {"amount": "0.00", "currency": "USD"}}]}, True),
        ({"lines": [{**LINE, "ssp_override_justification": "Negotiated price"}]}, True),
        ({"lines": [{**LINE, "ssp_override_justification": "  "}]}, False),
        ({"lines": [{**LINE, "account_overrides": {"CONTRACT_LIABILITY": "2400"}}]}, True),
        ({"lines": [{**LINE, "account_overrides": {}}]}, False),
        ({"lines": [LINE, {**LINE, "obligation_key": "O2", "scope_flag": "GUARANTEE_460"}]}, True),
    ],
)
def test_what_a_booking_states_beside_its_header(booking: dict[str, Any], flagged: bool) -> None:
    expected = {"NON_STANDARD_TERMS"} if flagged else set()
    assert activation._booking_flags(booking) == expected


def _booking(**members: Any) -> payloads.ContractBookedV1:
    return payloads.ContractBookedV1.model_validate(
        {
            "external_id": "SF-ORD-1",
            "customer_id": "01a0fbde-303f-7c80-9ffd-223a84a8e61b",
            "contracting_entity_code": "AVM-US",
            "transaction_currency": "USD",
            "inception_date": "2026-09-01",
            "lines": [{**LINE, "total_price": {"amount": "30000.00", "currency": "USD"}}],
            **members,
        }
    )


def test_a_booking_that_states_neither_term_is_stored_as_before() -> None:
    """04 §16.3 rev 1.287: ``acceptance_clause`` and ``side_letter`` are absent from the stored
    payload while they are not stated, so every booking that exists, and every booking of a
    source that does not know the two members, keeps its bytes and its hash."""
    silent = payloads.payload_json(_booking())
    assert "acceptance_clause" not in silent and "side_letter" not in silent
    # Every other optional member is stored as null, as it always was.
    assert silent["signature_date"] is None and silent["termination"] is None
    stated = payloads.payload_json(_booking(acceptance_clause=False, side_letter=True))
    assert (stated["acceptance_clause"], stated["side_letter"]) == (False, True)
    assert {key: value for key, value in stated.items() if key in silent} == silent
    assert sha256_hex(stated) != sha256_hex(silent)
    # One stated, one not: the stated one is stored, the other stays absent.
    half = payloads.payload_json(_booking(side_letter=False))
    assert half["side_letter"] is False and "acceptance_clause" not in half
    # A stored payload reads back as it was written: absent is "not stated".
    again = payloads.ContractBookedV1.model_validate(silent)
    assert (again.acceptance_clause, again.side_letter) == (None, None)
    assert payloads.payload_json(payloads.ContractBookedV1.model_validate(stated)) == stated


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        (" False ", False),
        ("TRUE", True),
    ],
)
def test_what_a_source_states_of_a_term(value: object, expected: bool | None) -> None:
    assert ports.stated_term(value, "side_letter") is expected


@pytest.mark.parametrize("value", ["yes", "0", 1, 0, "no", "n/a", ["true"]])
def test_a_term_spelled_another_way_is_refused_not_presumed(value: object) -> None:
    with pytest.raises(ports.Permanent, match="side_letter is neither true nor false"):
        ports.stated_term(value, "side_letter")


def test_the_threshold_currency_is_stated_in_one_place() -> None:
    """The supervisor's ruling of 2026-10-02: USD is a stated constant "in ONE place that every
    reader goes through". No module of the product but the subject registry assigns
    ``THRESHOLD_CURRENCY``; the readers hold the registry's own object."""
    assigned: list[str] = []
    for path in sorted((ROOT / "backend" / "erev_api").rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            if any(isinstance(t, ast.Name) and t.id == "THRESHOLD_CURRENCY" for t in targets):
                assigned.append(path.relative_to(ROOT).as_posix())
    assert assigned == ["backend/erev_api/approvals/subjects.py"]
    for reader in (activation, estimates, modifications, adjustments):
        assert reader.THRESHOLD_CURRENCY is subjects.THRESHOLD_CURRENCY
