"""The account mapping a group's bundle carries (04 T-REF-15; 05 RCP-15 rev 1.168; dev-guide
DG-CMD-04 rev 1.217; item MAP-RULE-FOREIGN-1, supervisor ruling of 2026-10-01).

A rule of the published mapping version that names a product, or an entity, the bundle does not
hold can match none of the group's lines, and is left out of the bundle. Handed over without its
condition — as it was before this item — it stood for every product, or every entity, at its
stored specificity, and took the account away from the rule that was written for the line.

World, through the product's commands: Maya (Revenue Accountant, SSP Analyst), Priya (SSP Approver)
and Marcus (Controller, Tenant Admin); US01 and DE01 (both USD) with FY2026-P01 to P09 open;
LICENCE-X and SUPPORT-Y, satisfied at a point in time on delivery (TPL-PIT), and SERVICES-X,
satisfied over time by output percent (TPL-PCT), under SSP-MAIN 2026. A contract books X1-LICENCE
for 60,000.00 and X2-SERVICES for 40,000.00 on 02 Jan 2026 and is activated. Each later event is
appended to the stream and the group is computed by the product's computation command
(``compute_job.compute_group``) — how an event reaches the stream, directly or through an
approval, is not the subject here. This is contract X of answer key POS-CHK-012, on which the
defect was measured: its tenant maps REVENUE to 4020 for LICENCE-X, to 4010 for SERVICES-X and to
4010 for SUPPORT-Y — a product no line of X names — and the licence's 60,000.00 was posted to
4010.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_computation, subledger_line
from erev_api.db.tables import gl_account as account
from erev_api.domain.contracts import bundles, compute_job, release_prepare
from erev_api.enums import ComputationStatus, ContractEventType
from erev_api.events.payloads import DeliveryRecordedV1, EventPayload, ProgressRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.bundle import BookInput, InputBundle
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support.db import TestDatabase
from support.factories import (
    Workspace,
    appended,
    approved_ssp_version,
    booked_contract,
    customer_id,
    engine,
    open_periods,
    point_entry,
    product_with_template,
    published_template,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import (
    assign,
    entity,
    gl_account,
    holding,
    mapping_published,
    put,
)
from support.worlds import TPL_PROD_PIT

US01: Final = "US01"
DE01: Final = "DE01"
LICENCE: Final = "LICENCE-X"
SERVICES: Final = "SERVICES-X"
SUPPORT: Final = "SUPPORT-Y"
JANUARY: Final = "2026-01-01T00:00:00Z"
TPL_PCT: Final = {
    "distinctness": "distinct",
    "satisfaction_pattern": "OVER_TIME",
    "over_time_criterion": "OT_C",
    "recognition_method": "OUTPUT_PERCENT",
}
# (code, name, account type, normal balance) of the accounts the worlds map.
CHART: Final = (
    ("1100", "Accounts receivable", "ASSET", "D"),
    ("1105", "Unbilled receivable", "ASSET", "D"),
    ("1200", "Contract asset", "ASSET", "D"),
    ("2100", "Contract liability", "LIABILITY", "C"),
    ("2190", "Contract liability - DE01", "LIABILITY", "C"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C"),
    ("4020", "Revenue - licences and royalties", "REVENUE", "C"),
)
BALANCE_ROLES: Final = (
    ("ACCOUNTS_RECEIVABLE", "1100"),
    ("UNBILLED_RECEIVABLE", "1105"),
    ("CONTRACT_ASSET", "1200"),
    ("CONTRACT_LIABILITY", "2100"),
)
Rule = Mapping[str, Any]
Rules = Callable[[Mapping[str, str], Mapping[str, str], Mapping[str, str]], Sequence[Rule]]


@dataclass(frozen=True, slots=True)
class World:
    place: Workspace
    buyer: UUID


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _people(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Actor, Actor, Actor]:
    maya_member = member(keyring, clock, name="maya")
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    found: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        found[name] = enrolled(app, clock, someone)
    return maya, found["priya"], found["marcus"]


def _balance_rules(accounts: Mapping[str, str]) -> list[Rule]:
    return [{"account_role": role, "gl_account_id": accounts[code]} for role, code in BALANCE_ROLES]


def _revenue_rules(
    accounts: Mapping[str, str], products: Mapping[str, str], codes: Mapping[str, str]
) -> list[Rule]:
    """One REVENUE rule per product: product code → account code."""
    return [
        {
            "account_role": "REVENUE",
            "gl_account_id": accounts[code],
            "product_id": products[product],
        }
        for product, code in codes.items()
    ]


def product_rules(
    accounts: Mapping[str, str], products: Mapping[str, str], entities: Mapping[str, str]
) -> list[Rule]:
    """The mapping of answer key POS-CHK-012: the licence has an account of its own."""
    revenue = {LICENCE: "4020", SERVICES: "4010", SUPPORT: "4010"}
    return [*_balance_rules(accounts), *_revenue_rules(accounts, products, revenue)]


def services_rules(
    accounts: Mapping[str, str], products: Mapping[str, str], entities: Mapping[str, str]
) -> list[Rule]:
    """The same shape with the services on the account of their own."""
    revenue = {LICENCE: "4010", SERVICES: "4020", SUPPORT: "4010"}
    return [*_balance_rules(accounts), *_revenue_rules(accounts, products, revenue)]


def entity_rules(
    accounts: Mapping[str, str], products: Mapping[str, str], entities: Mapping[str, str]
) -> list[Rule]:
    """A contract liability account of its own for DE01; every other entity takes 2100."""
    return [
        *_balance_rules(accounts),
        {
            "account_role": "CONTRACT_LIABILITY",
            "gl_account_id": accounts["2190"],
            "entity_id": entities[DE01],
        },
        {"account_role": "REVENUE", "gl_account_id": accounts["4010"]},
    ]


def built(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, rules: Rules
) -> World:
    maya, priya, marcus = _people(app, keyring, clock)
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD"]})
    assert enabled.status_code == 200, enabled.text
    calendar_id, us01 = world_calendar(app, maya, entity_code=US01)
    de01 = entity(app, maya, code=DE01, calendar_id=calendar_id, time_zone="Europe/Berlin")
    open_periods(
        app, maya, entity_code=DE01, keys=[f"FY2026-P{month:02d}" for month in range(1, 10)]
    )
    buyer = customer_id(app, maya, code="CUST-1", name="Pellworth Logistics Inc. (Demo)")
    products: dict[str, str] = {}
    for template_code, outputs, members in (
        (
            "TPL-PIT",
            TPL_PROD_PIT,
            ((LICENCE, "Software licence", "60000.00"), (SUPPORT, "Support plan", "5000.00")),
        ),
        ("TPL-PCT", TPL_PCT, ((SERVICES, "Implementation services", "40000.00"),)),
    ):
        for code, name, _ in members:
            products[code] = product_with_template(
                app, maya, code=code, name=name, revenue_category="SERVICES"
            )
        first, _, price = members[0]
        template = published_template(
            app,
            maya,
            marcus,
            code=template_code,
            outputs=outputs,
            case_line={
                "obligation_key": "POB-01",
                "product_code": first,
                "quantity": "1",
                "total_price": price,
            },
        )
        for code, _, _ in members:
            set_default_template(app, maya, products[code], template["template_id"])
    approved_ssp_version(
        app,
        maya,
        [priya],
        ssp_book(app, maya, code="SSP-MAIN"),
        label="2026",
        effective_from="2026-01-01",
        entries=[
            point_entry(LICENCE, "60000.00"),
            point_entry(SERVICES, "40000.00"),
            point_entry(SUPPORT, "5000.00"),
        ],
    )
    accounts = {
        code: gl_account(app, maya, code=code, name=name, account_type=kind, normal_balance=normal)
        for code, name, kind, normal in CHART
    }
    mapping_published(
        app,
        maya,
        marcus,
        name="MAP-2026-01",
        effective_from=JANUARY,
        rules=rules(accounts, products, {US01: str(us01), DE01: str(de01["id"])}),
    )
    stamp_test_release()
    return World(place=workspace(app, clock, keyring, files, maya), buyer=buyer)


def booked(world: World, external_id: str, entity_code: str = US01) -> UUID:
    """The contract for the licence and the services, booked on 02 Jan 2026 and activated."""
    made = booked_contract(
        world.place,
        {
            "external_id": external_id,
            "customer_id": str(world.buyer),
            "contracting_entity_code": entity_code,
            "transaction_currency": "USD",
            "inception_date": "2026-01-02",
            "lines": [
                {
                    "obligation_key": key,
                    "product_code": code,
                    "quantity": "1",
                    "total_price": {"amount": price, "currency": "USD"},
                }
                for key, code, price in (
                    ("X1-LICENCE", LICENCE, "60000.00"),
                    ("X2-SERVICES", SERVICES, "40000.00"),
                )
            ],
        },
        activate=True,
    )
    return UUID(str(made.contract["id"]))


def recorded(
    place: Workspace, contract_id: UUID, kind: ContractEventType, day: date, payload: EventPayload
) -> None:
    """One event appended after the contract's head, and the group computed by the product's
    computation command."""
    head = place.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    appended(
        place,
        contract_id,
        int(head),
        [EventIn(event_type=kind, effective_date=day, payload=payload)],
    )
    with place.uow() as uow:
        outcome = compute_job.compute_group(uow, group_of(place, contract_id))
        uow.commit()
    assert outcome.status is ComputationStatus.SUCCEEDED, outcome


def delivered(world: World, external_id: str, entity_code: str = US01) -> UUID:
    """``booked`` with the licence delivered on 15 Jan 2026: revenue of 60,000.00."""
    contract_id = booked(world, external_id, entity_code)
    recorded(
        world.place,
        contract_id,
        ContractEventType.DELIVERY_RECORDED,
        date(2026, 1, 15),
        DeliveryRecordedV1(obligation_key="X1-LICENCE", quantity="1", trigger="CONTROL_TRANSFER"),
    )
    return contract_id


def progressed(place: Workspace, contract_id: UUID, ratio: str, day: date) -> None:
    """The services at ``ratio`` of their output on ``day``."""
    recorded(
        place,
        contract_id,
        ContractEventType.PROGRESS_RECORDED,
        day,
        ProgressRecordedV1(
            obligation_key="X2-SERVICES", cumulative_progress_ratio=ratio, measure="OUTPUT_PERCENT"
        ),
    )


def posted(place: Workspace, contract_id: UUID, role: str) -> dict[str, Decimal]:
    """GL account code → the contract's posted amount of ``role``, debits positive (T-SL-04)."""
    joined = subledger_line.join(
        account,
        and_(
            account.c.tenant_id == subledger_line.c.tenant_id,
            account.c.id == subledger_line.c.gl_account_id,
        ),
    )
    rows = place.rows(
        select(account.c.code, func.sum(subledger_line.c.amount_txn).label("amount"))
        .select_from(joined)
        .where(subledger_line.c.contract_id == contract_id, subledger_line.c.account_role == role)
        .group_by(account.c.code)
    )
    return {str(row["code"]): Decimal(row["amount"]) for row in rows}


def group_of(place: Workspace, contract_id: UUID) -> UUID:
    found = place.scalar(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    )
    return UUID(str(found))


def asc606(bundle: InputBundle) -> BookInput:
    return next(item for item in bundle.books if item.book_code == "ASC606")


def rules_of(bundle: InputBundle, role: str) -> list[tuple[str, str, str, int]]:
    """(entity code, product code, account code, specificity) of the bundle's ``role`` rules; a
    rule without an entity or a product states ``""``."""
    return sorted(
        (rule.entity_code or "", rule.product_code or "", rule.account_code, rule.specificity)
        for rule in asc606(bundle).account_mapping.rules
        if rule.account_role == role
    )


def bundle_now(place: Workspace, contract_id: UUID) -> InputBundle:
    with place.uow() as uow:
        return bundles.build(uow.session, group_of(place, contract_id), uow.now)


class _Every(dict[UUID, str]):
    """The ids of a bundle's entities or products as the builder read them before this item: an
    id the bundle does not hold is found too, and answers no code."""

    def __contains__(self, key: object) -> bool:
        return True

    def __missing__(self, key: UUID) -> None:
        return None


def as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    """The builder as it stood before this item: every rule of the version is handed over, a rule
    of another product or entity without that condition."""
    real = bundles._account_mapping
    monkeypatch.setattr(
        bundles,
        "_account_mapping",
        lambda session, known_at, entities, products: real(
            session, known_at, _Every(entities), _Every(products)
        ),
    )


def test_a_rule_written_for_a_product_outside_the_group_does_not_take_its_revenue(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The licence's revenue goes to the account its own rule names. SUPPORT-Y is no product of the
    contract: its rule, handed to the engine without its product, stood for every product at the
    specificity of a product rule, and of two such rules the smaller account code won (4010)."""
    world = built(app, keyring, clock, files, product_rules)
    contract_id = delivered(world, "C-X")

    assert posted(world.place, contract_id, "REVENUE") == {"4020": Decimal("-60000.00")}
    # The bundle holds the rules of the group's own products, each with its product.
    assert rules_of(bundle_now(world.place, contract_id), "REVENUE") == [
        ("", LICENCE, "4020", 2),
        ("", SERVICES, "4010", 2),
    ]


def test_a_rule_written_for_another_entity_does_not_take_the_contract_liability(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """A contract of US01 takes the tenant's contract liability account. DE01's rule, handed over
    without its entity, stood for every entity at the specificity of an entity rule and beat the
    rule without an entity. A contract of DE01 keeps DE01's account: the rule is left out only of
    a bundle that does not hold its entity."""
    world = built(app, keyring, clock, files, entity_rules)
    american = delivered(world, "C-US")
    german = delivered(world, "C-DE", DE01)

    assert posted(world.place, american, "CONTRACT_LIABILITY") == {"2100": Decimal("60000.00")}
    assert posted(world.place, german, "CONTRACT_LIABILITY") == {"2190": Decimal("60000.00")}
    assert rules_of(bundle_now(world.place, american), "CONTRACT_LIABILITY") == [
        ("", "", "2100", 0)
    ]
    assert rules_of(bundle_now(world.place, german), "CONTRACT_LIABILITY") == [
        ("", "", "2100", 0),
        (DE01, "", "2190", 8),
    ]


def test_the_bundle_of_one_state_differs_by_the_foreign_rule_alone_and_is_found_drifted(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a computation stored before this item names. Of one state of one group, the bundle as
    it was built before and the bundle built now differ by the foreign rule and by nothing else,
    so their CV-25 hashes differ: the release preparation's decision calls a head that names the
    earlier hash drifted and hands the group to a recomputation (05 REL-06)."""
    world = built(app, keyring, clock, files, product_rules)
    place = world.place
    contract_id = delivered(world, "C-X")
    group_id = group_of(place, contract_id)
    head = place.scalar(
        select(contract_computation.c.id)
        .where(contract_computation.c.combination_group_id == group_id)
        .order_by(contract_computation.c.created_at.desc(), contract_computation.c.id.desc())
        .limit(1)
    )

    with place.uow() as uow:
        now = bundles.build(uow.session, group_id, uow.now)
        with monkeypatch.context() as earlier:
            as_before(earlier)
            was = bundles.build(uow.session, group_id, uow.now)

    assert rules_of(was, "REVENUE") == [
        ("", "", "4010", 2),  # SUPPORT-Y's rule without its product
        ("", LICENCE, "4020", 2),
        ("", SERVICES, "4010", 2),
    ]
    assert rules_of(now, "REVENUE") == [("", LICENCE, "4020", 2), ("", SERVICES, "4010", 2)]
    assert dataclasses.replace(was, books=now.books) == now
    assert was.sha256() != now.sha256()
    decision = release_prepare.backfill_decision(
        release_prepare.HeadFacts(group_id, UUID(str(head)), False, was.sha256(), {}),
        now,
        engine(),
    )
    assert (decision.kind, decision.recompute) == ("INPUT_DRIFTED", True)


def test_what_was_posted_before_stays_and_what_is_posted_now_takes_its_own_account(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ledger of a group that was computed while the bundle still carried the foreign rule. Half
    of the services' revenue was posted to 4010, the account of SUPPORT-Y's rule. The computation
    of the other half reads the bundle built now and posts it to 4020, the account of the
    services' own rule. It moves nothing that was posted: a change of what the mapping answers
    never reposts history (ENGINE_SPEC_B S14-R-09), and an account reclassification moves it."""
    world = built(app, keyring, clock, files, services_rules)
    place = world.place
    with monkeypatch.context() as earlier:
        as_before(earlier)
        contract_id = booked(world, "C-X")
        progressed(place, contract_id, "0.5", date(2026, 1, 31))
    assert posted(place, contract_id, "REVENUE") == {"4010": Decimal("-20000.00")}

    progressed(place, contract_id, "1", date(2026, 2, 28))

    assert posted(place, contract_id, "REVENUE") == {
        "4010": Decimal("-20000.00"),
        "4020": Decimal("-20000.00"),
    }
