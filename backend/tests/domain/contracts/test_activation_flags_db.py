"""The routing flags and the amount of a contract activation (PRD §2.5 rows ``CONTRACT_ACTIVATION``
rev 1.194; 04 T-PLT-17, T-CON-01, §16.3, §16.10 rev 1.287; dev-guide DG-KRN-APR-01 rev 1.273; 03
REQ-CON-006; control CTL-005; item ACT-FLAGS-1, a release blocker — the supervisor's rulings of
2026-10-02 on lane SECFIX-ACT's measurement and this lane's pre-build line; supervisor ruling
R-66 (4)).

THE DEFECT, as lane SECFIX-ACT measured it on main 84bc44e3: under the published rule
``AUTO-CON-01`` an integration's contract with an estimated element of variable consideration,
and one with a material right, were activated with no person's decision — an activation derived
four flags only, and its two thresholds compared the booking's total with the bare numbers
100,000.00 and 1,000,000.00 whatever the currency.

World: ``support.factories.seat_world`` (AVM-US, USD) as ``tests/domain/contracts/
test_activation.py`` builds it, the rule ``AUTO-CON-01`` published, and the API client
``svc-salesforce``, which books its contracts through the adapter path, records Step 1 itself
and submits — no event of a stream is a person's. The seat product is KNOWN to the workspace: a
fixture contract of it is active. Marcus (Controller; MFA) reviews the judgement records. The
computations run ``erev_engine.compute``, except where a test hands the command a dry run of its
own (``_dry_run``), which says so.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine as approvals_engine
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    contract,
    estimate,
    product,
    role,
)
from erev_api.domain.contracts import activation, computation
from erev_api.domain.contracts.commands import book_contract
from erev_api.enums import ApprovalSubjectType, SourceSystem
from erev_api.events.payloads import ContractBookedV1
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.contracts import SubmitActivationIn
from erev_engine.bundle import InputBundle, OutputBundle
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import (
    AVM_US_CHART,
    SEAT_MO,
    SeatWorld,
    approved_ssp_version,
    booked_contract,
    customer_id,
    point_entry,
    product_with_template,
    published_template,
    range_entry,
    seat_body,
    seat_line,
    seat_world,
    set_default_template,
)
from support.http import call
from support.principals import colleague, enrolled
from support.reference import approve, assign, calendar, entity, get, post, put, reject
from support.rows import estimate_values
from support.worlds import estimate_version_ready
from tests.domain.contracts.test_activation import (
    APPROVAL_HEADER,
    CONTRACTS,
    REVIEW_RATIONALE,
    SUGGESTIONS,
    _api_client,
    _bearer,
    _decisions,
    _header,
    _publish_auto_approval,
    _requests,
    _salesforce_token,
    _step1,
    _step1_by_integration,
    _steps,
)

STATED = {"acceptance_clause": False, "side_letter": False}
NEW_SEAT = "AVM-SEAT-NEW"
OPTION = "AVM-EXP-CREDIT"
REBATE_LINE = "AVM-REBATE-LINE"
TPL_PIT = {
    "distinctness": "distinct",
    "satisfaction_pattern": "POINT_IN_TIME",
    "over_time_criterion": "NOT_APPLICABLE",
    "recognition_method": "POINT_IN_TIME",
}
REBATE = {
    "estimate_kind": "VARIABLE_CONSIDERATION",
    "element_code": "REBATE-01",
    "vc_element_type": "REBATE",
    "method": "MOST_LIKELY_AMOUNT",
}
AUTO = "AUTO_APPROVE"
# The seat world's chart with the two accounts that consideration payable to a customer reaches
# (JET-14, ENGINE_SPEC S04-R-15): without them the dry run of such a booking is refused, and the
# case would show a refusal where it is to show a flag.
PAYABLE_CHART = (
    *AVM_US_CHART,
    ("1300", "Customer incentive asset", "ASSET", "D", "CUSTOMER_INCENTIVE_ASSET"),
    ("2450", "Consideration payable to customers", "LIABILITY", "C", "CONSIDERATION_PAYABLE"),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def seats(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> SeatWorld:
    return seat_world(app, keyring, clock, files, chart=PAYABLE_CHART)


@dataclass(frozen=True, slots=True)
class _Sales:
    """``svc-salesforce`` in a seat world under the published rule ``AUTO-CON-01``."""

    world: SeatWorld
    client_id: UUID
    token: str
    rule: tuple[UUID, UUID]  # the rule set version and the rule that approves

    def booked(self, external_id: str, lines: list[dict[str, Any]], **members: Any) -> UUID:
        """A draft the integration books through the adapter path: USD, inception 1 September
        2026, customer C-09, with the members given beside its lines."""
        body = {
            **seat_body(
                self.world.customers["C-09"],
                external_id=external_id,
                inception="2026-09-01",
                lines=lines,
            ),
            **members,
        }
        with self.world.place.uow(_api_client(self.world, self.client_id)) as uow:
            found = book_contract(
                uow,
                body=ContractBookedV1.model_validate(body),
                origin="ADAPTER",
                source_system=SourceSystem.SALESFORCE,
            )
            uow.commit()
        return UUID(str(found.contract["id"]))

    def assessed(self, contract_id: UUID) -> int:
        """Step 1 as the integration records it; the new head."""
        return _step1_by_integration(self.world, self.token, contract_id, 1)

    def submitted(self, contract_id: UUID, head: int) -> Any:
        return call(
            self.world.app,
            "POST",
            f"{CONTRACTS}/{contract_id}/submit-activation",
            json={},
            headers=_bearer(self.token, head),
        )

    def answer(self, contract_id: UUID, head: int) -> tuple[Any, ...]:
        """What a submission ends in: the request's status, its flags and who decided it — or
        the refusal, by status, code and sentence."""
        sent = self.submitted(contract_id, head)
        if sent.status_code != 200:
            refusal = sent.json()
            return ("REFUSED", sent.status_code, refusal.get("code"), refusal.get("detail"))
        (request,) = _requests(self.world, contract_id)
        decided = [kind for kind, _, _, _ in _decisions(self.world, str(request["id"]))]
        return (str(request["status"]), list(request["flags"]), decided)


def _known(world: SeatWorld, *codes: str) -> None:
    """Each product is known to the workspace: a fixture contract that holds a line of it is
    ACTIVE (``booked_contract``: booked and activated, no request). It belongs to a customer of
    its own, so no combination is suggested with a contract of a test."""
    maya = world.place.author
    buyer = customer_id(world.app, maya, code="C-77", name="Known Products GmbH (Demo)")
    lines = [
        seat_line(
            f"K{number}",
            seats="1",
            price="2400.00",
            start="2026-01-01",
            end="2026-12-31",
            product_code=code,
        )
        for number, code in enumerate(codes, start=1)
    ]
    body = seat_body(buyer, external_id="SF-ORD-10001", inception="2026-01-01", lines=lines)
    booked_contract(world.place, body, activate=True)


def _sales(world: SeatWorld, *known: str) -> _Sales:
    assign(world.priya.member, "revenue_reviewer")
    rule = _publish_auto_approval(world)
    client_id, token = _salesforce_token(world)
    _known(world, SEAT_MO, *known)
    return _Sales(world=world, client_id=client_id, token=token, rule=rule)


def _seat(
    key: str = "O1", *, price: str = "30000.00", product_code: str = SEAT_MO
) -> dict[str, Any]:
    return seat_line(
        key,
        seats="12",
        price=price,
        start="2026-09-01",
        end="2027-08-31",
        product_code=product_code,
    )


def _more_products(world: SeatWorld) -> None:
    """People's configuration beside the seat: a second seat product on the seat's template, a
    customer option whose template is of the kind MATERIAL_RIGHT, a rebate line whose template is
    of the kind VC_LINE, and US-LIST 2026-H2 with a price for each."""
    maya, marcus = world.place.author, world.marcus
    daily = world.place.scalar(
        select(product.c.default_pob_template_id).where(product.c.code == SEAT_MO)
    )
    second = product_with_template(
        world.app, maya, code=NEW_SEAT, name="Platform seat, new", revenue_category="SUBSCRIPTION"
    )
    set_default_template(world.app, maya, second, str(daily))
    for code, template, kind, category, price in (
        (OPTION, "TPL-OPTION", "MATERIAL_RIGHT", "MATERIAL_RIGHT", "1200.00"),
        (REBATE_LINE, "TPL-VC-LINE", "VC_LINE", "SUBSCRIPTION", "1200.00"),
    ):
        made = product_with_template(
            world.app, maya, code=code, name=f"Product {code}", revenue_category=category
        )
        published = published_template(
            world.app,
            maya,
            marcus,
            code=template,
            outputs={"obligation_kind": kind, **TPL_PIT},
            case_line={
                "obligation_key": "O2",
                "product_code": code,
                "quantity": "1",
                "total_price": price,
            },
        )
        set_default_template(world.app, maya, made, published["template_id"])
    approved_ssp_version(
        world.app,
        maya,
        [world.priya],
        world.book_id,
        label="2026-H2",
        effective_from="2026-07-01",
        entries=[
            range_entry(SEAT_MO, "2160.00", "2400.00", "2640.00", value_basis="AMOUNT"),
            range_entry(NEW_SEAT, "2160.00", "2400.00", "2640.00", value_basis="AMOUNT"),
            point_entry(OPTION, "1200.00"),
            point_entry(REBATE_LINE, "1200.00"),
        ],
    )


def _option_line() -> dict[str, Any]:
    return {
        "obligation_key": "O2",
        "product_code": OPTION,
        "quantity": "1",
        "total_price": {"amount": "1200.00", "currency": "USD"},
    }


def _distinct_reviewed(world: SeatWorld, contract_id: UUID, key: str) -> None:
    """People review the option's distinctness — a judgement record with an approval of its own,
    which appends nothing to the stream."""
    review = post(
        world.app,
        f"{CONTRACTS}/{contract_id}/obligations/{key}/distinct-review",
        world.place.author,
        {"distinctness": "distinct", "rationale": REVIEW_RATIONALE},
    )
    assert review.status_code == 201, review.text
    decided = approve(world.app, review.json()["approval_request_id"], world.marcus)
    assert decided.status_code == 200, decided.text


def _facts(world: SeatWorld, contract_id: UUID) -> tuple[list[str], tuple[Decimal, str] | None]:
    """The routing facts the record states of a contract with no dry run at hand, read under the
    tenant's scope as the approvals kernel reads a subject's registered functions."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        stated = activation.routing_facts(session, contract_id, None)
    return sorted(stated.flags), stated.amount


# --- the flags of the record ---------------------------------------------------------------------


ELEMENT_CASE = "an estimated element of variable consideration"
OPTION_CASE = "a customer option, a material right"


def _cases() -> dict[str, tuple[list[dict[str, Any]], dict[str, Any], list[str]]]:
    """One contract a source of a flag — its lines, the members of its booking beside them and
    the one flag it carries: a seat contract of 30,000.00 USD that states both terms false unless
    its case says otherwise, on products the workspace knows."""
    payable = {
        "amount": {"amount": "1000.00", "currency": "USD"},
        "promise_date": "2026-09-01",
    }
    noncash = {
        "units": "10",
        "fair_value_per_unit": "50.00",
        "measurement_date": "2026-09-01",
        "variability": "FORM",
    }
    return {
        "neither term is stated": ([_seat()], {}, ["TERMS_NOT_STATED"]),
        "one term is not stated": ([_seat()], {"acceptance_clause": False}, ["TERMS_NOT_STATED"]),
        "a side letter": (
            [_seat()],
            {"acceptance_clause": False, "side_letter": True},
            ["SIDE_LETTER"],
        ),
        "an acceptance clause": (
            [_seat()],
            {"acceptance_clause": True, "side_letter": False},
            ["NON_STANDARD_TERMS"],
        ),
        "termination for convenience": (
            [_seat()],
            {**STATED, "termination": {"party": "CUSTOMER"}},
            ["NON_STANDARD_TERMS"],
        ),
        "a product no activated contract holds": (
            [_seat(product_code=NEW_SEAT)],
            STATED,
            ["NEW_SKU"],
        ),
        "consideration payable to the customer": (
            [_seat()],
            {**STATED, "consideration_payable": [payable]},
            ["NON_STANDARD_TERMS"],
        ),
        "noncash consideration": (
            [_seat()],
            {**STATED, "noncash_consideration": [noncash]},
            ["NON_STANDARD_TERMS"],
        ),
        "a line with its own accounts": (
            [{**_seat(), "account_overrides": {"CONTRACT_LIABILITY": "2400"}}],
            STATED,
            ["NON_STANDARD_TERMS"],
        ),
        ELEMENT_CASE: ([_seat()], STATED, ["VARIABLE_CONSIDERATION"]),
        OPTION_CASE: ([_seat(), _option_line()], STATED, ["MATERIAL_RIGHT"]),
    }


def _booked_cases(sales: _Sales, numbers: str) -> dict[str, UUID]:
    """Each case of ``_cases`` booked by the integration, with the element of the element's case
    — a person adds it; an element writes no event. A draft that holds the new product is booked
    first and never submitted: a draft makes no product known."""
    world = sales.world
    sales.booked(f"SF-ORD-{numbers}00", [_seat(product_code=NEW_SEAT)], **STATED)
    found: dict[str, UUID] = {}
    for number, (name, (lines, members, _)) in enumerate(_cases().items(), start=1):
        found[name] = sales.booked(f"SF-ORD-{numbers}{number:02d}", lines, **members)
    element = post(
        world.app, f"{CONTRACTS}/{found[ELEMENT_CASE]}/estimates", world.place.author, REBATE
    )
    assert element.status_code == 201, element.text
    return found


def test_an_integrations_activation_waits_for_a_person_wherever_the_record_states_a_flag(
    seats: SeatWorld,
) -> None:
    """Every case of ``_cases``, submitted by the integration under the published rule. The three
    contracts of lane SECFIX-ACT's measurement are the control, the rebate element and the
    customer option: before the item each of the three was ACTIVE with flags [] by
    ``AUTO_APPROVE`` of SYSTEM. The control is submitted last and is still approved by the rule —
    so every other contract waits for its own reason and no other."""
    _more_products(seats)
    sales = _sales(seats, OPTION)
    booked = _booked_cases(sales, "105")
    _distinct_reviewed(seats, booked[OPTION_CASE], "O2")
    answers = {
        name: sales.answer(contract_id, sales.assessed(contract_id))
        for name, contract_id in booked.items()
    }
    control = sales.booked("SF-ORD-10599", [_seat()], **STATED)
    answers["control"] = sales.answer(control, sales.assessed(control))

    assert answers == {
        **{name: ("PENDING", flags, []) for name, (_, _, flags) in _cases().items()},
        "control": ("APPROVED", [], [AUTO]),
    }
    # The control was approved by the published rule and by nothing else.
    (request,) = _requests(seats, control)
    assert _decisions(seats, str(request["id"])) == [(AUTO, "SYSTEM", *sales.rule)]
    assert _header(seats, control)[0] == "ACTIVE"


def test_what_the_record_states_of_a_draft_with_no_dry_run_at_hand(seats: SeatWorld) -> None:
    """The subject's registered flags, on drafts the integration booked: every case of ``_cases``
    and two a dry run of this world would not compute — a line outside Topic 606 and a line that
    states an SSP justification —; each estimated element by its kind (E-09): five kinds estimate
    consideration, the exercise likelihood of an option is the built record of a material right,
    four state nothing of the price; and a line by the kind of its product's template."""
    _more_products(seats)
    sales = _sales(seats, OPTION, REBATE_LINE)
    booked = _booked_cases(sales, "104")
    outside = {
        **_seat(),
        "scope_flag": "LEASE_842",
        "out_of_scope_amount": {"amount": "1000.00", "currency": "USD"},
    }
    booked["a line outside Topic 606"] = sales.booked("SF-ORD-10490", [outside], **STATED)
    booked["a line with an SSP justification"] = sales.booked(
        "SF-ORD-10491",
        [{**_seat(), "ssp_override_justification": "Negotiated list price."}],
        **STATED,
    )
    assert {name: _facts(seats, contract_id)[0] for name, contract_id in booked.items()} == {
        **{name: flags for name, (_, _, flags) in _cases().items()},
        "a line outside Topic 606": ["NON_STANDARD_TERMS"],
        "a line with an SSP justification": ["NON_STANDARD_TERMS"],
    }
    kinds = {
        "VARIABLE_CONSIDERATION": ["VARIABLE_CONSIDERATION"],
        "RETURN_RATE": ["VARIABLE_CONSIDERATION"],
        "IMPLICIT_PRICE_CONCESSION": ["VARIABLE_CONSIDERATION"],
        "BREAKAGE": ["VARIABLE_CONSIDERATION"],
        "ROYALTY_ACCRUAL": ["VARIABLE_CONSIDERATION"],
        "EXERCISE_LIKELIHOOD": ["MATERIAL_RIGHT"],
        "EAC": [],
        "RENEWAL_EXPECTATION": [],
        "EXPECTED_PURCHASES": [],
        "SHARE_BASED_CONSIDERATION": [],
    }
    stated: dict[str, list[str]] = {}
    for number, kind in enumerate(kinds, start=1):
        contract_id = sales.booked(f"SF-ORD-106{number:02d}", [_seat()], **STATED)
        row = estimate_values(
            seats.place.tenant_id,
            contract_id=contract_id,
            estimate_kind=kind,
            vc_element_type="REBATE" if kind == "VARIABLE_CONSIDERATION" else None,
            direction="DECREASE" if kind == "IMPLICIT_PRICE_CONCESSION" else "INCREASE",
        )
        context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(context) as session:
            session.execute(insert(estimate).values(**row))
        stated[kind] = _facts(seats, contract_id)[0]
    assert stated == kinds

    plain = sales.booked("SF-ORD-10650", [_seat()], **STATED)
    rebate = sales.booked(
        "SF-ORD-10651", [_seat(), {**_option_line(), "product_code": REBATE_LINE}], **STATED
    )
    option = sales.booked("SF-ORD-10652", [_seat(), _option_line()], **STATED)
    assert {
        "a seat alone": _facts(seats, plain),
        "a line whose template is VC_LINE": _facts(seats, rebate),
        "a line whose template is MATERIAL_RIGHT": _facts(seats, option),
    } == {
        "a seat alone": ([], (Decimal("30000.00"), "USD")),
        "a line whose template is VC_LINE": (
            ["VARIABLE_CONSIDERATION"],
            (Decimal("31200.00"), "USD"),
        ),
        "a line whose template is MATERIAL_RIGHT": (
            ["MATERIAL_RIGHT"],
            (Decimal("31200.00"), "USD"),
        ),
    }


# --- the two thresholds and the request's amount -------------------------------------------------


def _spot_rates(world: SeatWorld, rates: list[tuple[str, str, str, str]]) -> None:
    """A spot rate set with ``rates`` — (base, quote, day, rate) — covering 2026, approved by
    Marcus; the inverse of each entered pair is derived at its submission."""
    maya = world.place.author
    rate_set = post(
        world.app,
        "/api/v1/fx-rate-sets",
        maya,
        {"code": "AVM-RATES-SPOT", "name": "AVM-RATES spot", "rate_type": "spot"},
    )
    assert rate_set.status_code == 201, rate_set.text
    draft = post(
        world.app,
        f"/api/v1/fx-rate-sets/{rate_set.json()['id']}/versions",
        maya,
        {
            "coverage_from": "2026-01-01",
            "coverage_to": "2026-12-31",
            "rates": [
                {
                    "base_currency": base,
                    "quote_currency": quote,
                    "effective_date": day,
                    "rate": rate,
                }
                for base, quote, day, rate in rates
            ],
        },
    )
    assert draft.status_code == 201, draft.text
    sent = post(
        world.app,
        f"/api/v1/fx-rate-set-versions/{draft.json()['id']}/submit",
        maya,
        {"comment": "Spot rates"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert sent.status_code == 200, sent.text
    world.place.clock.advance(timedelta(minutes=1))
    decided = approve(world.app, sent.json()["pending_approval_request_id"], world.marcus)
    assert decided.status_code == 200, decided.text


def _draft(
    sales: _Sales, external_id: str, currency: str, price: str, *, entity_code: str = "AVM-US"
) -> UUID:
    """A draft of one seat line in ``currency``, both terms false, booked by the integration."""
    line = {**_seat(price=price), "total_price": {"amount": price, "currency": currency}}
    return sales.booked(
        external_id,
        [line],
        **STATED,
        transaction_currency=currency,
        contracting_entity_code=entity_code,
    )


def test_the_thresholds_read_dollars_at_the_spot_rate_in_force_for_the_inception_date(
    seats: SeatWorld,
) -> None:
    """PRD §2.5: "TP ≥ USD 100,000.00" and "≥ USD 1,000,000.00" are dollar amounts. Until the item
    the booking's total was compared with the bare numbers whatever the currency, and a request
    stated no amount when the contract's currency was not the entity's.

    AVM-US keeps dollars, AVM-UK pounds. The spot set states GBP to USD 1.280000 on 15 August —
    the latest rate on or before the inception date, 1 September, as the engine reads a spot rate
    — and 1.500000 on 2 September, which is not read; JPY to USD on 1 September; EUR to USD on 2
    September alone, after the inception date; nothing for CHF."""
    sales = _sales(seats)
    enabled = put(
        seats.app,
        "/api/v1/tenant-currencies",
        seats.marcus,
        {"currency_codes": ["USD", "GBP", "JPY", "EUR", "CHF"]},
    )
    assert enabled.status_code == 200, enabled.text
    london = calendar(seats.app, seats.place.author, code="UK-CAL", years=(2026,))
    entity(
        seats.app,
        seats.place.author,
        code="AVM-UK",
        calendar_id=london,
        functional_currency="GBP",
        time_zone="Europe/London",
    )
    _spot_rates(
        seats,
        [
            ("GBP", "USD", "2026-08-15", "1.280000"),
            ("GBP", "USD", "2026-09-02", "1.500000"),
            ("JPY", "USD", "2026-09-01", "0.006900"),
            ("EUR", "USD", "2026-09-02", "1.100000"),
        ],
    )
    unjudged = ["ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD", "RATE_NOT_PUBLISHED"]
    drafts = {
        # Below 100,000.00 pounds and above 100,000.00 dollars: flagged, and the amount stated.
        "GBP 90,000.00 under AVM-US": ("GBP", "90000.00", "AVM-US"),
        # The threshold is inclusive at the cent, after the conversion's rounding.
        "GBP 78,125.00 under AVM-US": ("GBP", "78125.00", "AVM-US"),
        "GBP 78,124.99 under AVM-US": ("GBP", "78124.99", "AVM-US"),
        # Above 1,000,000 yen and far below 1,000,000.00 dollars: no Controller's step.
        "JPY 2,000,000 under AVM-US": ("JPY", "2000000", "AVM-US"),
        # No rate: the amount cannot be judged, so it is treated as above, and nothing is stated.
        "CHF 5,000.00 under AVM-US": ("CHF", "5000.00", "AVM-US"),
        "EUR 5,000.00 under AVM-US": ("EUR", "5000.00", "AVM-US"),
        # An amount of zero needs no rate.
        "CHF 0.00 under AVM-US": ("CHF", "0.00", "AVM-US"),
        # The entity's own currency: the amount is the pounds, the thresholds read the dollars.
        "GBP 90,000.00 under AVM-UK": ("GBP", "90000.00", "AVM-UK"),
        # Dollars under the pound entity: the amount at the derived inverse, 1 / 1.28 = 0.78125.
        "USD 30,000.00 under AVM-UK": ("USD", "30000.00", "AVM-UK"),
        # The dollar amount is known and is judged by its value; the amount in pounds is not, so
        # the request states none and says so.
        "JPY 2,000,000 under AVM-UK": ("JPY", "2000000", "AVM-UK"),
    }
    found = {
        name: _facts(
            seats, _draft(sales, f"SF-ORD-107{number:02d}", currency, price, entity_code=code)
        )
        for number, (name, (currency, price, code)) in enumerate(drafts.items(), start=1)
    }
    assert found == {
        "GBP 90,000.00 under AVM-US": (["ABOVE_THRESHOLD"], (Decimal("115200.00"), "USD")),
        "GBP 78,125.00 under AVM-US": (["ABOVE_THRESHOLD"], (Decimal("100000.00"), "USD")),
        "GBP 78,124.99 under AVM-US": ([], (Decimal("99999.99"), "USD")),
        "JPY 2,000,000 under AVM-US": ([], (Decimal("13800.00"), "USD")),
        "CHF 5,000.00 under AVM-US": (unjudged, None),
        "EUR 5,000.00 under AVM-US": (unjudged, None),
        "CHF 0.00 under AVM-US": ([], (Decimal("0.00"), "USD")),
        "GBP 90,000.00 under AVM-UK": (["ABOVE_THRESHOLD"], (Decimal("90000.00"), "GBP")),
        "USD 30,000.00 under AVM-UK": ([], (Decimal("23437.50"), "GBP")),
        "JPY 2,000,000 under AVM-UK": (["RATE_NOT_PUBLISHED"], None),
    }
    # A request that states no functional amount is one no tenant's amount rule can read: the
    # flag alone takes the Controller's second step.
    unstated = seats.place.scalar(
        select(contract.c.id).where(contract.c.external_id == "SF-ORD-10710")
    )
    with seats.place.uow() as uow:
        routed = approvals_engine.route_submission(
            uow, ApprovalSubjectType.CONTRACT_ACTIVATION, unstated, auto_approval=False
        )
    controller = seats.place.scalar(select(role.c.id).where(role.c.code == "controller"))
    assert (routed.flags, routed.amount) == (["RATE_NOT_PUBLISHED"], None)
    assert [(step.permission, step.role_id) for step in routed.routed.steps] == [
        ("contract.approve", None),
        ("contract.approve", controller),
    ]
    # The subject registry states the same through the functions the domain registered: the
    # amount of an activation, and of a void request of the contract — the booked consideration.
    pounds = seats.place.scalar(
        select(contract.c.id).where(contract.c.external_id == "SF-ORD-10701")
    )
    context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        activated = subjects.spec_for(ApprovalSubjectType.CONTRACT_ACTIVATION)
        voided = subjects.spec_for(ApprovalSubjectType.CONTRACT_VOID)
        assert activated.amount_functional(session, pounds) == (Decimal("115200.00"), "USD")
        assert sorted(activated.flags(session, pounds)) == ["ABOVE_THRESHOLD"]
        assert voided.amount_functional(session, pounds) == (Decimal("115200.00"), "USD")


def _dry_run(
    *, price: str | None = None, financing: str | None = None, kind: str | None = None
) -> computation.Engine:
    """The engine's dry run with one statement of its output replaced: the transaction price or
    the financing adjustment of its contract versions, or the kind of its obligation versions.
    The routing reads the dry run's OUTPUT, so the witness states the output and leaves the
    engine's rules to the engine's own tests."""
    run = computation.default_engine()

    def stated(original: object, amount: str) -> object:
        if isinstance(original, int):
            return int(Decimal(amount) * 100)
        return Decimal(amount)

    def computed(bundle: InputBundle) -> OutputBundle:
        output = run(bundle)
        books = []
        for book in output.books:
            version = book.contract_version
            if version is not None:
                columns = dict(version.columns)
                if price is not None:
                    columns["transaction_price"] = stated(columns.get("transaction_price"), price)
                if financing is not None:
                    columns["financing_adjustment_amount"] = stated(
                        columns.get("financing_adjustment_amount"), financing
                    )
                version = dataclasses.replace(version, columns=columns)
            obligations = book.obligation_versions
            if kind is not None:
                obligations = tuple(
                    dataclasses.replace(item, columns={**item.columns, "obligation_kind": kind})
                    for item in obligations
                )
            books.append(
                dataclasses.replace(book, contract_version=version, obligation_versions=obligations)
            )
        return dataclasses.replace(output, books=tuple(books))

    return computed


def _submitted_with(sales: _Sales, contract_id: UUID, head: int, run: computation.Engine) -> None:
    """``submit_activation`` as the integration, with the dry run given."""
    with sales.world.place.uow(_api_client(sales.world, sales.client_id)) as uow:
        activation.submit_activation(
            uow,
            contract_id=contract_id,
            expected_stream_version=head,
            body=SubmitActivationIn(),
            engine=run,
        )
        uow.commit()


def _request(world: SeatWorld, contract_id: UUID) -> tuple[str, list[str], Decimal | None]:
    (request,) = _requests(world, contract_id)
    amount = request["amount_functional"]
    return (
        str(request["status"]),
        list(request["flags"]),
        None if amount is None else Decimal(amount),
    )


def test_the_larger_of_the_booking_and_the_dry_runs_price_is_judged_and_financing_is_flagged(
    seats: SeatWorld,
) -> None:
    """Supervisor ruling R-66 (4): "the activation thresholds read the larger of the booked
    consideration and the transaction price of the activation's dry run" — both orders of the
    two operands, and the financing adjustment, which no row of the record states."""
    sales = _sales(seats)
    lifted = sales.booked("SF-ORD-10801", [_seat()], **STATED)  # booked 30,000.00
    lowered = sales.booked("SF-ORD-10802", [_seat(price="120000.00")], **STATED)
    financed = sales.booked("SF-ORD-10803", [_seat()], **STATED)
    control = sales.booked("SF-ORD-10804", [_seat()], **STATED)

    _submitted_with(sales, lifted, sales.assessed(lifted), _dry_run(price="120000.00"))
    _submitted_with(sales, lowered, sales.assessed(lowered), _dry_run(price="30000.00"))
    _submitted_with(sales, financed, sales.assessed(financed), _dry_run(financing="-500.00"))
    _submitted_with(sales, control, sales.assessed(control), computation.default_engine())

    assert {
        "the dry run's price is the larger": _request(seats, lifted),
        "the booking is the larger": _request(seats, lowered),
        "a financing adjustment": _request(seats, financed),
        "control": _request(seats, control),
    } == {
        "the dry run's price is the larger": ("PENDING", ["ABOVE_THRESHOLD"], Decimal("120000.00")),
        "the booking is the larger": ("PENDING", ["ABOVE_THRESHOLD"], Decimal("120000.00")),
        "a financing adjustment": ("PENDING", ["NON_STANDARD_TERMS"], Decimal("30000.00")),
        "control": ("APPROVED", [], Decimal("30000.00")),
    }
    # At the Controller's threshold the dry run's price alone routes the second step.
    second = sales.booked("SF-ORD-10805", [_seat()], **STATED)
    _submitted_with(sales, second, sales.assessed(second), _dry_run(price="1000000.00"))
    (request,) = _requests(seats, second)
    assert list(request["flags"]) == ["ABOVE_CONTROLLER_THRESHOLD", "ABOVE_THRESHOLD"]
    assert [step[0] for step in _steps(seats, str(request["id"]))] == [1, 2]


def test_a_line_is_judged_by_the_kind_the_computation_gives_it(seats: SeatWorld) -> None:
    """The template a line computes under is the engine's choice: under the parity preset a row
    of stratification ``VC`` takes the template of the kind VC_LINE whatever its product's
    default (S03-R-18), and a ``POB_ASSIGNMENT`` rule may give a line another template — only
    the computation says which. So the command reads the kinds its dry run states for the
    contract's own obligations, beside the product's default template: a seat contract whose
    dry run states VC_LINE, or MATERIAL_RIGHT, for its line waits for a person with the flag,
    though the seat's template is of neither kind and the contract holds no estimated element.
    The dry run's output is given, as in the test above.

    A reader without a dry run reads the kinds of the group's stored version: of a draft Maya
    books with a seat and a customer option, the kinds of the two lines as computed.

    Fail-first (the kinds of the computation not read): both contracts were approved by the
    rule, flags []."""
    _more_products(seats)
    sales = _sales(seats, OPTION)
    by_kind = {}
    for number, kind in enumerate(("VC_LINE", "MATERIAL_RIGHT"), start=1):
        contract_id = sales.booked(f"SF-ORD-1082{number}", [_seat()], **STATED)
        _submitted_with(sales, contract_id, sales.assessed(contract_id), _dry_run(kind=kind))
        by_kind[kind] = _request(seats, contract_id)
    assert by_kind == {
        "VC_LINE": ("PENDING", ["VARIABLE_CONSIDERATION"], Decimal("30000.00")),
        "MATERIAL_RIGHT": ("PENDING", ["MATERIAL_RIGHT"], Decimal("30000.00")),
    }

    body = {
        **seat_body(
            seats.customers["C-02"],
            external_id="SF-ORD-10829",
            inception="2026-09-01",
            lines=[_seat(), _option_line()],
        ),
        **STATED,
    }
    created = post(seats.app, CONTRACTS, seats.place.author, body)
    assert created.status_code == 201, created.text
    context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        stored = activation.stored_measure(session, UUID(str(created.json()["id"])))
    assert stored is not None
    assert stored.kinds == {"STANDARD", "MATERIAL_RIGHT"}


def test_an_estimate_approved_on_a_draft_reaches_the_threshold_of_its_activation(
    seats: SeatWorld,
) -> None:
    """Supervisor ruling R-66 (4), the DRAFT case as lane SECFIX-ACT measured it on main a101c4c0
    (the review had inferred it): Maya books 36,000.00 and a bonus of 70,000.00 — an estimated
    element that raises the price — is approved while the contract is a draft. The version's own
    request states an amount of zero and takes one step: a version on a draft recognises
    nothing. The draft's price moves to 106,000.00. On main the activation's request then stated
    36,000.00 and no threshold flag, with 106,000.00 to be recognised. It states the larger of the
    two, 106,000.00, and carries ``ABOVE_THRESHOLD`` — the dry run's price is the engine's own
    here, no figure is given to it."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    line = seat_line("O1", seats="10", price="36000.00", start="2026-09-01", end="2029-08-31")
    created = post(
        seats.app,
        CONTRACTS,
        maya,
        {
            **seat_body(
                seats.customers["C-09"],
                external_id="SF-ORD-10851",
                inception="2026-09-01",
                lines=[line],
            ),
            **STATED,
        },
    )
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    element = post(
        seats.app,
        f"{CONTRACTS}/{contract_id}/estimates",
        maya,
        {
            "estimate_kind": "VARIABLE_CONSIDERATION",
            "element_code": "BONUS-01",
            "vc_element_type": "BONUS",
            "direction": "INCREASE",
            "method": "MOST_LIKELY_AMOUNT",
        },
    )
    assert element.status_code == 201, element.text
    version = post(
        seats.app,
        f"/api/v1/estimates/{element.json()['id']}/versions",
        maya,
        {
            "effective_date": "2026-09-01",
            "scenarios": [{"outcome": "The bonus is earned", "amount": "70000.00"}],
            "unconstrained_amount": "70000.00",
            "most_conservative_amount": "70000.00",
            "constrained_amount": "70000.00",
            "rationale": "Performance bonus, most likely amount.",
        },
    )
    assert version.status_code == 201, version.text
    version_id = str(version.json()["id"])
    estimate_version_ready(
        seats.app, maya, version_id, constraint_of="BONUS-01", reviewer=seats.marcus
    )
    sent = post(
        seats.app, f"/api/v1/estimate-versions/{version_id}/submit", maya, {"comment": "Review"}
    )
    assert sent.status_code == 200, sent.text
    weighed = seats.place.rows(
        select(approval_request.c.flags, approval_request.c.amount_functional).where(
            approval_request.c.id == UUID(str(sent.json()["approval_request_id"]))
        )
    )
    assert [(list(row["flags"]), Decimal(row["amount_functional"])) for row in weighed] == [
        ([], Decimal("0.00"))
    ]
    decided = approve(seats.app, str(sent.json()["approval_request_id"]), seats.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    # The draft is computed again with the version; a caller that holds no dry run — the
    # subject's registered functions — reads that stored version: the same amount, the same flag.
    context = DbContext(tenant_id=seats.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        registered = subjects.spec_for(ApprovalSubjectType.CONTRACT_ACTIVATION)
        assert registered.amount_functional(session, contract_id) == (Decimal("106000.00"), "USD")
        assert "ABOVE_THRESHOLD" in registered.flags(session, contract_id)

    head = _step1(seats.app, maya, seats.marcus, contract_id, _header(seats, contract_id)[1])
    submitted = post(
        seats.app,
        f"{CONTRACTS}/{contract_id}/submit-activation",
        maya,
        {},
        if_match=f'"s{head}"',
    )
    assert submitted.status_code == 200, submitted.text
    assert _request(seats, contract_id) == (
        "PENDING",
        ["ABOVE_THRESHOLD", "MANUAL_ENTRY", "NEW_SKU", "VARIABLE_CONSIDERATION"],
        Decimal("106000.00"),
    )


def test_what_a_request_states_does_not_depend_on_who_submits(
    seats: SeatWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (1); dev-guide DG-KRN-DB-05 rev 1.273. The command states the
    request's flags itself, and one of them asks about every other contract of the workspace.
    Here the seat product is known ONLY through an active contract of another entity, AVM-UK.
    Rosa is a Revenue Accountant of AVM-US alone and reads no contract of AVM-UK; Maya reads
    every entity. Rosa submits the activation of an AVM-US contract; it is rejected; Maya submits
    the same contract. Both requests state the same flags and amount — no ``NEW_SKU``: the facts
    are read under the tenant's scope — and the request Rosa reads names nothing of AVM-UK's
    contract."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    london = calendar(seats.app, maya, code="UK-CAL", years=(2026,))
    entity(
        seats.app,
        maya,
        code="AVM-UK",
        calendar_id=london,
        functional_currency="USD",
        time_zone="Europe/London",
    )
    other = booked_contract(
        seats.place,
        {
            **seat_body(
                seats.customers["C-02"],
                external_id="UK-ORD-20001",
                inception="2026-01-01",
                lines=[
                    seat_line(
                        "K1", seats="1", price="2400.00", start="2026-01-01", end="2026-12-31"
                    )
                ],
            ),
            "contracting_entity_code": "AVM-UK",
        },
        activate=True,
    )
    someone = colleague(maya.member.tenant_id, "rosa")
    assign(someone, "revenue_accountant", entity_ids=[seats.entity_id])
    rosa = enrolled(seats.app, clock, someone)

    created = post(
        seats.app,
        CONTRACTS,
        maya,
        {
            **seat_body(
                seats.customers["C-09"],
                external_id="SF-ORD-10861",
                inception="2026-09-01",
                lines=[_seat()],
            ),
            **STATED,
        },
    )
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)
    path = f"{CONTRACTS}/{contract_id}/submit-activation"

    by_rosa = post(seats.app, path, rosa, {}, if_match=f'"s{head}"')
    assert by_rosa.status_code == 200, by_rosa.text
    first = _request(seats, contract_id)
    shown = get(seats.app, f"/api/v1/approvals/{by_rosa.headers[APPROVAL_HEADER]}", rosa)
    assert shown.status_code == 200, shown.text
    assert "UK-ORD-20001" not in shown.text and str(other.contract["id"]) not in shown.text
    refused = reject(seats.app, by_rosa.headers[APPROVAL_HEADER], seats.priya, "Submit it again.")
    assert refused.status_code == 200, refused.text

    by_maya = post(seats.app, path, maya, {}, if_match=f'"s{head}"')
    assert by_maya.status_code == 200, by_maya.text
    stated = [
        (list(row["flags"]), Decimal(row["amount_functional"]))
        for row in _requests(seats, contract_id)
    ]
    assert first == ("PENDING", ["MANUAL_ENTRY"], Decimal("30000.00"))
    assert stated == [(["MANUAL_ENTRY"], Decimal("30000.00"))] * 2


def _terms(world: SeatWorld, contract_id: UUID) -> tuple[bool | None, bool | None]:
    (row,) = world.place.rows(
        select(contract.c.acceptance_clause, contract.c.side_letter).where(
            contract.c.id == contract_id
        )
    )
    return row["acceptance_clause"], row["side_letter"]


def test_a_replaced_draft_states_the_terms_of_its_latest_booking(seats: SeatWorld) -> None:
    """04 T-CON-01 rev 1.287: the two terms are header members of the booking, written with the
    header projection — at the booking and again when a draft is replaced. A draft that stated
    nothing and is replaced by a booking that states both false is a standard item; one that
    stated them and is replaced by a booking that does not, is not."""
    sales = _sales(seats)

    def replaced(contract_id: UUID, external_id: str, **members: Any) -> None:
        body = {
            **seat_body(
                seats.customers["C-09"],
                external_id=external_id,
                inception="2026-09-01",
                lines=[_seat()],
            ),
            **members,
        }
        answered = call(
            seats.app,
            "POST",
            f"{CONTRACTS}/{contract_id}/replace-draft",
            json=body,
            headers=_bearer(sales.token, 1),
        )
        assert answered.status_code == 200, answered.text

    silent = sales.booked("SF-ORD-10871", [_seat()])
    stated = sales.booked("SF-ORD-10872", [_seat()], **STATED)
    before = {
        "silent": (_terms(seats, silent), _facts(seats, silent)[0]),
        "stated": (_terms(seats, stated), _facts(seats, stated)[0]),
    }
    replaced(silent, "SF-ORD-10871", **STATED)
    replaced(stated, "SF-ORD-10872")
    after = {
        "silent": (_terms(seats, silent), _facts(seats, silent)[0]),
        "stated": (_terms(seats, stated), _facts(seats, stated)[0]),
    }
    assert (before, after) == (
        {
            "silent": ((None, None), ["TERMS_NOT_STATED"]),
            "stated": ((False, False), []),
        },
        {
            "silent": ((False, False), []),
            "stated": ((None, None), ["TERMS_NOT_STATED"]),
        },
    )


# --- a request routed before the item ------------------------------------------------------------


def test_a_request_routed_before_the_upgrade_is_decided_with_the_flags_it_was_routed_by(
    seats: SeatWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A request that is pending at the upgrade keeps its flags: a decision does not read a
    subject's flags again, and the request's content pins the contract's head, not its flags.

    "Before the upgrade" is the submission of the earlier release, reproduced where it differed:
    the contract's two terms are NULL — the migration writes no value — and the request is
    routed by the flags that release derived, here none beside ``MANUAL_ENTRY`` for a contract a
    person booked. The release under test would state ``NEW_SKU`` and ``TERMS_NOT_STATED`` of
    the same contract. The decision is this release's: approved, activated, flags as routed."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    created = post(
        seats.app,
        CONTRACTS,
        maya,
        seat_body(
            seats.customers["C-09"],
            external_id="SF-ORD-10901",
            inception="2026-09-01",
            lines=[_seat()],
        ),
    )
    assert created.status_code == 201, created.text
    contract_id = UUID(str(created.json()["id"]))
    terms = seats.place.rows(
        select(contract.c.acceptance_clause, contract.c.side_letter).where(
            contract.c.id == contract_id
        )
    )
    assert terms == [{"acceptance_clause": None, "side_letter": None}]
    head = _step1(seats.app, maya, seats.marcus, contract_id, 1)

    present = activation.routing_facts
    earlier = activation.RoutingFacts(
        flags=frozenset({"MANUAL_ENTRY"}), amount=(Decimal("30000.00"), "USD")
    )
    monkeypatch.setattr(activation, "routing_facts", lambda *_, **__: earlier)
    submitted = post(
        seats.app,
        f"{CONTRACTS}/{contract_id}/submit-activation",
        maya,
        {},
        if_match=f'"s{head}"',
    )
    assert submitted.status_code == 200, submitted.text
    monkeypatch.setattr(activation, "routing_facts", present)

    assert _request(seats, contract_id) == ("PENDING", ["MANUAL_ENTRY"], Decimal("30000.00"))
    assert _facts(seats, contract_id)[0] == ["MANUAL_ENTRY", "NEW_SKU", "TERMS_NOT_STATED"]
    decided = approve(seats.app, submitted.headers[APPROVAL_HEADER], seats.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    assert _request(seats, contract_id) == ("APPROVED", ["MANUAL_ENTRY"], Decimal("30000.00"))
    assert _header(seats, contract_id)[0] == "ACTIVE"
    decisions = seats.place.rows(
        select(approval_decision.c.decision).where(
            approval_decision.c.approval_request_id == UUID(submitted.headers[APPROVAL_HEADER])
        )
    )
    assert [str(row["decision"]) for row in decisions] == ["APPROVE"]


# --- a member of a combined group ----------------------------------------------------------------


def test_a_member_of_a_combined_group_is_judged_by_the_groups_price(seats: SeatWorld) -> None:
    """Ruling R-66 (4) for a combined group (ASC 606-10-25-9: one contract for the transaction
    price). A contract version is the combination group's, so the price of an activation's dry
    run is the GROUP's. Maya books two drafts of C-09, 60,000.00 and 70,000.00 — each below USD
    100,000.00 — and Marcus approves their combination before either is activated. Each member's
    activation states the group's 130,000.00 as its amount and carries ``ABOVE_THRESHOLD``: the
    first, whose sibling is still a draft, and the second after it."""
    maya = seats.place.author
    assign(seats.priya.member, "revenue_reviewer")
    members = {}
    for external_id, price in (("SF-ORD-11001", "60000.00"), ("SF-ORD-11002", "70000.00")):
        body = {
            **seat_body(
                seats.customers["C-09"],
                external_id=external_id,
                inception="2026-09-01",
                lines=[_seat(price=price)],
            ),
            **STATED,
        }
        created = post(seats.app, CONTRACTS, maya, body)
        assert created.status_code == 201, created.text
        members[external_id] = UUID(str(created.json()["id"]))
    alone = {name: _facts(seats, contract_id) for name, contract_id in members.items()}
    proposed = post(
        seats.app,
        "/api/v1/combination-groups",
        maya,
        {
            "contract_ids": [str(contract_id) for contract_id in members.values()],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    sent = post(seats.app, f"/api/v1/combination-groups/{proposed.json()['id']}/submit", maya, {})
    assert sent.status_code == 200, sent.text
    combined = approve(seats.app, sent.json()["approval_request_id"], seats.marcus)
    assert combined.status_code == 200, combined.text
    # The second booking raised a combination suggestion for the pair (S02-R-14); it stays open
    # after the pair was combined, and the checklist asks that none is: dismissed by its answer.
    listed = get(seats.app, SUGGESTIONS, maya, {"contract": str(members["SF-ORD-11001"])})
    assert listed.status_code == 200, listed.text
    for suggestion in listed.json()["items"]:
        dismissed = post(
            seats.app,
            f"{SUGGESTIONS}/{suggestion['id']}/dismiss",
            maya,
            {"rationale": "Combined by the approved combination group request."},
        )
        assert dismissed.status_code == 200, dismissed.text

    requests = {}
    for name, contract_id in members.items():
        head = _header(seats, contract_id)[1]
        head = _step1(seats.app, maya, seats.marcus, contract_id, head)
        submitted = post(
            seats.app,
            f"{CONTRACTS}/{contract_id}/submit-activation",
            maya,
            {},
            if_match=f'"s{head}"',
        )
        assert submitted.status_code == 200, submitted.text
        requests[name] = _request(seats, contract_id)
        decided = approve(seats.app, submitted.headers[APPROVAL_HEADER], seats.priya)
        assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
        assert _header(seats, contract_id)[0] == "ACTIVE"

    # Alone, before the combination, each is judged by its own booking: no threshold flag.
    assert alone == {
        "SF-ORD-11001": (["MANUAL_ENTRY", "NEW_SKU"], (Decimal("60000.00"), "USD")),
        "SF-ORD-11002": (["MANUAL_ENTRY", "NEW_SKU"], (Decimal("70000.00"), "USD")),
    }
    flags = ["ABOVE_THRESHOLD", "MANUAL_ENTRY", "NEW_SKU"]
    assert requests == {
        "SF-ORD-11001": ("PENDING", flags, Decimal("130000.00")),
        # The first member is ACTIVE now and holds a line of the product: no NEW_SKU.
        "SF-ORD-11002": ("PENDING", ["ABOVE_THRESHOLD", "MANUAL_ENTRY"], Decimal("130000.00")),
    }
