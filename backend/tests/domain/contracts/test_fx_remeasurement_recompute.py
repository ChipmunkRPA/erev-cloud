"""A posted foreign-currency remeasurement survives the next computation (ENG-FXREM-RATEPIN-1;
ENGINE_SPEC_B S14-R-04, S14-R-28 and S14-INV-02, S14-INV-08 rev 1.50; 03 REQ-FX-006; 04 T-SL-04
``ck_subledger_line__fx``; 05 RCP-05; D-88 L7-6-Q-1; lane P7 record §4.26).

The database half of ``tests/engine/s14_posting/test_s14_fx_rate_references.py``. Maya (Revenue
Accountant, SSP Analyst) prepares, Priya (SSP Approver) approves the price list and Marcus
(Controller, SSP Approver, Tenant Admin; MFA) enables GBP and approves the templates, the mapping
and the rate sets. AVM-UK keeps GBP books (Europe/London, FY2026-P01 to P09 open); the contract
``NS-SO-UK-7001`` is in USD: 200 sensor gateways at USD 450.00 (TPL-PROD-UNITS, point in time per
unit). USD to GBP: spot 0.8000 (1 July 2026) and 0.8400 (20 August); average 0.8100 and closing
0.8200 for July. The frozen clock reads 2026-09-12T12:00:00Z.

- 10 July: 120 units delivered, revenue USD 54,000.00 at the July average, GBP 43,740.00 (an asset
  layer, POL-162); the July closing rate carries it at 44,280.00.
- 20 August: the invoice of USD 54,000.00 settles the layer at spot, 45,360.00 against 44,280.00:
  JET-10a settlement Dr CONTRACT_LIABILITY 1,080.00 / Cr FX_GAIN_LOSS 1,080.00, no transaction
  amount, posted by the command's computation under the group subject ``<group>@<entity>``.
- 1 September: a fact without an accounting effect is recorded and the group computes again.

Until revision 0124 the ledger stored no subject key and answered ``<contract>@<entity>`` for the
posted settlement (``bundles._posted``, decision L3-1-Q-32), so before rev 1.50 the third
computation reversed the 1,080.00 under a role key without a target — a foreign-currency line
without a rate reference, refused at persistence with "converts USD to GBP, but the output carries
no pinned rate" — and posted it again under the group subject. The volume seed failed exactly
there (``volume._recompute_all``). Rev 1.50 matched a posted remeasurement by its entry kind. The
ledger now stores the subject of every line a product command writes (04 T-SL-04 ``subject_key``
rev 1.282; item ENG-COST-READBACK-1), the read-back answers the stored ``<group>@<entity>`` (05
RCP-05 rev 1.202) and the match is gone (ENGINE_SPEC_B S14-R-04 rev 1.165).

The second test is the line that does reverse posted amounts (S14-R-28): an invoice dated before
the July period end arrives late, the replay holds no asset layer and therefore no remeasurement
target, and the posted settlement is taken back at the rate stamped on it — a rate of a version
that was superseded in the meantime, which the bundle no longer pins (``rate_refs``).

The third test is the settlement stored WITHOUT a subject key — a line a test builder writes
through the door: it answers ``<group>@<entity>`` all the same (the remeasurement clause of the
read-back for a line without a key), so the next computations post nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    close_run,
    combination_group,
    contract_computation,
    fx_rate,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.close import gates, period_end
from erev_api.domain.contracts import computation
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support import close_runs
from support.db import TestDatabase
from support.factories import (
    GATEWAY,
    GATEWAY_CASE,
    K11_CHART,
    TPL_PROD_UNITS,
    Workspace,
    activated_contract,
    approved_ssp_version,
    booked_contract,
    computed,
    customer_id,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.ledger_door import keyless
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, holding, post, put
from support.worlds import approved_manual_events

ENTITY = "AVM-UK"
CONTRACT = "NS-SO-UK-7001"
BOOK = "ASC606"
FX = "FX_REMEASUREMENT"
RATE_SETS = "/api/v1/fx-rate-sets"
VERSIONS = "/api/v1/fx-rate-set-versions"
USD_GBP = {"base_currency": "USD", "quote_currency": "GBP"}
# The K-11 chart and the account of the JET-10 gain or loss.
CHART = (*K11_CHART, ("7200", "Foreign exchange gain or loss", "EXPENSE", "D", "FX_GAIN_LOSS"))


@dataclass(frozen=True, slots=True)
class World:
    place: Workspace
    customer_id: UUID
    maya: Actor
    priya: Actor
    marcus: Actor
    closing_set_id: str

    @property
    def app(self) -> FastAPI:
        return self.place.app


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _rate_set(app: FastAPI, author: Actor, rate_type: str) -> str:
    """One MANUAL rate set ``AVM-UK-<TYPE>`` (04 T-REF-10); returns its id."""
    created = post(
        app,
        RATE_SETS,
        author,
        {
            "code": f"AVM-UK-{rate_type.upper()}",
            "name": f"USD to GBP {rate_type}",
            "rate_type": rate_type,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _published_version(
    app: FastAPI,
    author: Actor,
    approver: Actor,
    set_id: str,
    rates: list[dict[str, Any]],
    *,
    coverage: tuple[str, str] = ("2026-07-01", "2026-09-30"),
) -> None:
    """The next version of a rate set over ``coverage``, submitted by the author and approved by
    the controller (04 T-REF-11, T-REF-12; SM-04)."""
    draft = post(
        app,
        f"{RATE_SETS}/{set_id}/versions",
        author,
        {"coverage_from": coverage[0], "coverage_to": coverage[1], "rates": rates},
    )
    assert draft.status_code == 201, draft.text
    submitted = post(
        app,
        f"{VERSIONS}/{draft.json()['id']}/submit",
        author,
        {"comment": "Treasury rates"},
        if_match=f'"r{draft.json()["row_version"]}"',
    )
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["pending_approval_request_id"], approver)
    assert approved.status_code == 200, approved.text


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> World:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        # Priya is a Revenue Reviewer too: she approves the deliveries Maya records (CTR-6)
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "ssp_approver", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "GBP"]})
    assert enabled.status_code == 200, enabled.text
    world_calendar(
        app, maya, entity_code=ENTITY, functional_currency="GBP", time_zone="Europe/London"
    )
    buyer = customer_id(app, maya, code="C-71", name="Tarnbrook Instruments Ltd (Demo)")
    gateway = product_with_template(
        app, maya, code=GATEWAY, name="Sensor gateway unit", revenue_category="PRODUCT"
    )
    units = published_template(
        app, maya, marcus, code="TPL-PROD-UNITS", outputs=TPL_PROD_UNITS, case_line=GATEWAY_CASE
    )
    set_default_template(app, maya, gateway, units["template_id"])
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        ssp_book(app, maya, code="UK-LIST-USD", currency="USD"),
        label="2026",
        effective_from="2026-01-01",
        entries=[range_entry(GATEWAY, "405.00", "450.00", "495.00", currency="USD")],
    )
    published_mapping(app, maya, marcus, chart=CHART)
    _published_version(
        app,
        maya,
        marcus,
        _rate_set(app, maya, "spot"),
        [
            {**USD_GBP, "rate": "0.800000", "effective_date": "2026-07-01"},
            {**USD_GBP, "rate": "0.840000", "effective_date": "2026-08-20"},
        ],
    )
    _published_version(
        app,
        maya,
        marcus,
        _rate_set(app, maya, "average"),
        [
            {**USD_GBP, "rate": "0.810000", "period_key": "FY2026-P07"},
            {**USD_GBP, "rate": "0.830000", "period_key": "FY2026-P08"},
            {**USD_GBP, "rate": "0.835000", "period_key": "FY2026-P09"},
        ],
    )
    closing_set_id = _rate_set(app, maya, "closing")
    _published_version(
        app,
        maya,
        marcus,
        closing_set_id,
        [
            {**USD_GBP, "rate": "0.820000", "period_key": "FY2026-P07"},
            {**USD_GBP, "rate": "0.850000", "period_key": "FY2026-P08"},
            {**USD_GBP, "rate": "0.860000", "period_key": "FY2026-P09"},
        ],
    )
    stamp_test_release()
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), maya)
    return World(
        place=place,
        customer_id=buyer,
        maya=maya,
        priya=approvers["priya"],
        marcus=marcus,
        closing_set_id=closing_set_id,
    )


def _recorded(world: World, contract_id: UUID, head: int, event: dict[str, Any]) -> dict[str, Any]:
    """``POST /contracts/{id}/events`` after stream head ``head``; the 201 body."""
    response = post(
        world.app,
        f"/api/v1/contracts/{contract_id}/events",
        world.place.author,
        {"events": [event]},
        if_match=f'"s{head}"',
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    assert body["computation"]["status"] == "SUCCEEDED", body["computation"]
    return body


def _fx_lines(world: World, contract_id: UUID) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """(role, transaction amount, functional amount, stamped rate) of the contract's ASC606
    ``FX_REMEASUREMENT`` lines; the stamp is read through ``fx_rate_id``."""
    rows = world.place.rows(
        select(
            subledger_line.c.account_role,
            subledger_line.c.amount_txn,
            subledger_line.c.amount_functional,
            fx_rate.c.rate,
        )
        .select_from(
            subledger_line.join(
                fx_rate,
                and_(
                    fx_rate.c.tenant_id == subledger_line.c.tenant_id,
                    fx_rate.c.id == subledger_line.c.fx_rate_id,
                ),
            )
        )
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.book_code == BOOK,
            subledger_line.c.entry_kind == FX,
        )
        .order_by(subledger_line.c.account_role)
    )
    return [
        (
            str(row["account_role"]),
            Decimal(row["amount_txn"]),
            Decimal(row["amount_functional"]),
            Decimal(row["rate"]),
        )
        for row in rows
    ]


def _unstamped_foreign_lines(world: World, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(func.count())
            .select_from(subledger_line)
            .where(
                subledger_line.c.contract_id == contract_id,
                subledger_line.c.txn_currency != subledger_line.c.functional_currency,
                subledger_line.c.fx_rate_id.is_(None),
            )
        )
    )


def _line_count(world: World, contract_id: UUID) -> int:
    return int(
        world.place.scalar(
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.contract_id == contract_id)
        )
    )


def _group_subject(world: World, group_id: UUID) -> str:
    """``<group>@<entity>``: the one subject every JET-10 part of the group posts under in
    AVM-UK (ENGINE_SPEC_B Table 14-A)."""
    code = world.place.scalar(
        select(combination_group.c.code).where(combination_group.c.id == group_id)
    )
    return group_entity_subject_key(str(code), ENTITY)


def delivered(world: World) -> tuple[UUID, UUID]:
    """``NS-SO-UK-7001`` booked and activated, 120 units delivered on 10 July 2026 and computed:
    revenue USD 54,000.00 / GBP 43,740.00 at the July average. Returns (contract id, group id);
    the stream head is 3."""
    body = {
        "external_id": CONTRACT,
        "customer_id": str(world.customer_id),
        "contracting_entity_code": ENTITY,
        "transaction_currency": "USD",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": GATEWAY,
                "quantity": "200",
                "total_price": {"amount": "90000.00", "currency": "USD"},
            }
        ],
    }
    booked = activated_contract(world.place, booked_contract(world.place, body, activate=False))
    contract_id = UUID(str(booked.contract["id"]))
    assert str(booked.combination_group["code"]) != CONTRACT  # the two subjects differ
    # BUILD_SPEC CTR-6: Maya's delivery waits for another user; Priya approves it, and the
    # approval appends it and computes.
    recorded = approved_manual_events(
        world.place,
        world.priya,
        contract_id,
        {
            "event_type": "DELIVERY_RECORDED",
            "effective_date": "2026-07-10",
            "payload": {"obligation_key": "O1", "quantity": "120", "trigger": "DELIVERY"},
        },
        evidence_file_ids=[],
    )
    assert recorded["computation"]["status"] == "SUCCEEDED", recorded["computation"]
    assert _fx_lines(world, contract_id) == []
    return contract_id, UUID(str(booked.combination_group["id"]))


def _invoice(number: str, on: str, amount: str) -> dict[str, Any]:
    return {
        "event_type": "BILLING_RECORDED",
        "effective_date": on,
        "payload": {
            "invoice_number": number,
            "line_external_id": f"{number}-1",
            "obligation_key": "O1",
            "amount": {"amount": amount, "currency": "USD"},
            "issue_date": on,
        },
    }


def test_eng_fxrem_ratepin_1_a_posted_settlement_survives_the_next_computations(
    world: World,
) -> None:
    contract_id, group_id = delivered(world)
    _recorded(world, contract_id, 3, _invoice("INV-UK-7001", "2026-08-20", "54000.00"))
    # JET-10a settlement: USD 54,000.00 at spot 0.8400 = 45,360.00 against the July closing
    # carrying 44,280.00; the stamp is the rate with the latest effective date (D-88 L7-6-Q-1).
    settlement = [
        ("CONTRACT_LIABILITY", Decimal("0"), Decimal("1080.00"), Decimal("0.84")),
        ("FX_GAIN_LOSS", Decimal("0"), Decimal("-1080.00"), Decimal("0.84")),
    ]
    assert _fx_lines(world, contract_id) == settlement
    posted_lines = _line_count(world, contract_id)

    # The next computation reads the settlement back under its stored subject <group>@<entity>
    # (RCP-05 rev 1.202): it persists, reverses nothing and posts nothing (S14-INV-02); before rev
    # 1.50 it was refused.
    _recorded(
        world,
        contract_id,
        4,
        {
            "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
            "effective_date": "2026-09-01",
            "payload": {"description": "Customer asked for a review"},
        },
    )
    assert _fx_lines(world, contract_id) == settlement
    assert _line_count(world, contract_id) == posted_lines

    # The volume seed's frame: one more recompute of the group (``volume._recompute_all``).
    with world.place.uow() as uow:
        computation.recompute(uow, group_id)
        uow.commit()
    bundle, output, _ = computed(world.place, group_id)
    assert {item.subject_key for item in bundle.posted if item.entry_kind == FX} == {
        _group_subject(world, group_id)
    }
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _fx_lines(world, contract_id) == settlement
    assert _line_count(world, contract_id) == posted_lines
    assert _unstamped_foreign_lines(world, contract_id) == 0
    statuses = world.place.rows(
        select(contract_computation.c.status, func.count().label("computations"))
        .where(contract_computation.c.combination_group_id == group_id)
        .group_by(contract_computation.c.status)
    )
    assert [str(row["status"]) for row in statuses] == ["SUCCEEDED"]
    postings = world.place.scalar(
        select(func.count(func.distinct(subledger_line.c.subledger_posting_id)))
        .select_from(
            subledger_line.join(
                subledger_posting,
                and_(
                    subledger_posting.c.tenant_id == subledger_line.c.tenant_id,
                    subledger_posting.c.id == subledger_line.c.subledger_posting_id,
                ),
            )
        )
        .where(subledger_line.c.contract_id == contract_id, subledger_line.c.entry_kind == FX)
    )
    assert postings == 1  # the settlement posted once, by the billing's computation


def test_a_reversal_of_a_posted_settlement_takes_the_rate_stamped_on_it(world: World) -> None:
    """S14-R-28 on the ledger. The invoice of 20 August for USD 27,000.00 settles half the July
    asset layer: 27,000.00 × (0.8400 − 0.8200) = 540.00. The other half stays open over the August
    period end, so the role target also names the August closing rate and the one stamp of the
    line is that rate, 0.8500 of closing version 1 (the latest effective date, D-88 L7-6-Q-1).
    Treasury then republishes the August closing rate as version 2 (0.8550), and an invoice dated
    5 July for USD 54,000.00 arrives late. The replay starts with a liability layer at the 1 July
    spot, the July revenue relieves it (43,200.00, not 43,740.00), no asset layer ever exists and
    the remeasurement target is gone: the computation takes the posted 540.00 back. That line
    converts nothing itself; it names the rate stamped on the line it reverses — closing version
    1, which the bundle no longer pins — and persists with that stamp."""
    contract_id, group_id = delivered(world)
    _recorded(world, contract_id, 3, _invoice("INV-UK-7001", "2026-08-20", "27000.00"))
    settlement = [
        ("CONTRACT_LIABILITY", Decimal("0"), Decimal("540.00"), Decimal("0.85")),
        ("FX_GAIN_LOSS", Decimal("0"), Decimal("-540.00"), Decimal("0.85")),
    ]
    assert _fx_lines(world, contract_id) == settlement

    _published_version(
        world.app,
        world.maya,
        world.marcus,
        world.closing_set_id,
        [{**USD_GBP, "rate": "0.855000", "period_key": "FY2026-P08"}],
        coverage=("2026-08-01", "2026-08-31"),
    )
    _recorded(world, contract_id, 4, _invoice("INV-UK-7000", "2026-07-05", "54000.00"))

    bundle, output, _ = computed(world.place, group_id)
    pinned = {rate.rate_key for rate in bundle.fx_rates}
    version_1 = ("AVM-UK-CLOSING@v1/closing/USD/GBP/2026-08-31", "AVM-UK-CLOSING@v1")
    assert version_1[0] not in pinned
    assert "AVM-UK-CLOSING@v2/closing/USD/GBP/2026-08-31" in pinned
    fx_posted = [item for item in bundle.posted if item.entry_kind == FX]
    assert {item.rate_refs for item in fx_posted} == {(version_1,)}
    assert [intent for book in output.books for intent in book.posting_intents] == []
    # The posted settlement and its reversal, each stamped 0.8500 (version 1); the ledger nets to
    # nil per role.
    reversal = [(role, txn, -functional, rate) for role, txn, functional, rate in settlement]
    assert sorted(_fx_lines(world, contract_id)) == sorted([*settlement, *reversal])
    assert _unstamped_foreign_lines(world, contract_id) == 0
    revenue = world.place.rows(
        select(subledger_line.c.amount_txn, subledger_line.c.amount_functional).where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.book_code == BOOK,
            subledger_line.c.account_role == "REVENUE",
        )
    )
    # July revenue: 43,740.00 at the average, then the late invoice's carry of 540.00 back to the
    # historical 43,200.00 (credit negative; no transaction amount moves).
    assert sorted(
        (Decimal(row["amount_txn"]), Decimal(row["amount_functional"])) for row in revenue
    ) == [
        (Decimal("-54000.00"), Decimal("-43740.00")),
        (Decimal("0.00"), Decimal("540.00")),
    ]


def test_a_settlement_stored_without_a_subject_key_answers_the_group_subject(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04 T-SL-04 ``subject_key`` is nullable: a line a test builder writes through the door
    stores no key and is read back in the spelling of decision L3-1-Q-32 — with one clause for
    the remeasurement, which every JET-10 part posts under ``<group>@<entity>`` (Table 14-A): an
    ``FX_REMEASUREMENT`` line without a key answers that subject of the bundle group, where rev
    1.50 put it by its entry kind (05 RCP-05 rev 1.202). The settlement of the first test, every
    line written without a key: the next computations find it under the group subject, reverse
    nothing and post nothing. Without the clause the line would answer ``<contract>@<entity>``, a
    role key without a target, and the computation would be refused as before rev 1.50."""
    keyless(monkeypatch)
    contract_id, group_id = delivered(world)
    assert _group_subject(world, group_id) != f"{CONTRACT}@{ENTITY}"
    _recorded(world, contract_id, 3, _invoice("INV-UK-7001", "2026-08-20", "54000.00"))
    settlement = [
        ("CONTRACT_LIABILITY", Decimal("0"), Decimal("1080.00"), Decimal("0.84")),
        ("FX_GAIN_LOSS", Decimal("0"), Decimal("-1080.00"), Decimal("0.84")),
    ]
    assert _fx_lines(world, contract_id) == settlement
    stored = world.place.rows(
        select(subledger_line.c.subject_key)
        .where(subledger_line.c.contract_id == contract_id)
        .distinct()
    )
    assert [row["subject_key"] for row in stored] == [None]
    posted_lines = _line_count(world, contract_id)

    _recorded(
        world,
        contract_id,
        4,
        {
            "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
            "effective_date": "2026-09-01",
            "payload": {"description": "Customer asked for a review"},
        },
    )
    bundle, output, _ = computed(world.place, group_id)
    assert {item.subject_key for item in bundle.posted if item.entry_kind == FX} == {
        _group_subject(world, group_id)
    }
    assert [intent for book in output.books for intent in book.posting_intents] == []
    assert _fx_lines(world, contract_id) == settlement
    assert _line_count(world, contract_id) == posted_lines
    assert _unstamped_foreign_lines(world, contract_id) == 0


def test_contract_period_override_close_pass_posts_liability_fx_once(
    world: World,
) -> None:
    from support.factories import drafted_override

    booked = activated_contract(
        world.place,
        booked_contract(
            world.place,
            {
                "external_id": CONTRACT,
                "customer_id": str(world.customer_id),
                "contracting_entity_code": ENTITY,
                "transaction_currency": "USD",
                "inception_date": "2026-07-01",
                "lines": [
                    {
                        "obligation_key": "O1",
                        "product_code": GATEWAY,
                        "quantity": "200",
                        "total_price": {"amount": "90000.00", "currency": "USD"},
                    }
                ],
            },
            activate=False,
        ),
    )
    contract_id, group_id = booked.contract["id"], booked.combination_group["id"]
    _recorded(world, contract_id, 2, _invoice("ADV-1", "2026-07-01", "90000.00"))
    assert _fx_lines(world, contract_id) == []
    # Seed the still-disabled public authoring path; approval and calculation are real commands.
    identifier = drafted_override(
        world.place, contract_id, "fx.cl_historical_layering", "DISABLED_REMEASURE_AS_MONETARY"
    )
    sent = post(world.app, f"/api/v1/policy-overrides/{identifier}/submit", world.maya, {})
    assert sent.status_code == 200, sent.text
    decision = approve(world.app, str(sent.json()["approval_request_id"]), world.marcus)
    assert decision.status_code == 200, decision.text
    computed(world.place, group_id)
    # COMMAND leaves period-end TIME journals to the real close pass.
    assert _fx_lines(world, contract_id) == []
    run_id, _ = close_runs.started(
        world.app, world.marcus, entity_code=ENTITY, period_key="FY2026-P09"
    )

    def post_fx() -> period_end.PassResult:
        with world.place.uow() as uow:
            row = (
                uow.session.execute(select(close_run).where(close_run.c.id == UUID(run_id)))
                .mappings()
                .one()
            )
            scope = gates.scope_of_period(uow.session, row["entity_id"], BOOK, row["period_id"])
            assert scope is not None
            result = period_end.post_pass(
                uow,
                close_run_id=UUID(run_id),
                close_run_no=row["close_run_no"],
                scope=scope,
                pass_name=period_end.FX_REMEASUREMENT,
            )
            uow.commit()
            return result

    posted = post_fx()
    assert (posted.postings, posted.lines, posted.groups_skipped) == (1, 2, 0)
    expected = [
        ("CONTRACT_LIABILITY", Decimal("0"), Decimal("-5400.00"), Decimal("0.86")),
        ("FX_GAIN_LOSS", Decimal("0"), Decimal("5400.00"), Decimal("0.86")),
    ]
    assert _fx_lines(world, contract_id) == expected
    count = _line_count(world, contract_id)
    assert post_fx().postings == 0
    computed(world.place, group_id)
    assert post_fx().postings == 0
    assert _fx_lines(world, contract_id) == expected
    assert _line_count(world, contract_id) == count
    assert _unstamped_foreign_lines(world, contract_id) == 0
