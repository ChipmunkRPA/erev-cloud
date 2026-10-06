"""Contract figures at the cut of ``as_of`` (CTR-ASOF-KPI-1, CTR-OBL-PERF-ENTITY-SCOPE-1,
CTR-TODATE-AWAITING-1, EXPLAIN-BALANCE-LINKS-1; 04 API-C-10, API-S-Context, API-S-Contract,
API-S-Obligation, API-S-ContractBalance, API-S-ScheduleLine and §16.11, rev 1.132, and API-C-10,
the balance entries' ``links`` and §16.11 rev 1.174; 03 REQ-REC-021, REQ-PLT-030; ENGINE_SPEC
S04-R-02, S04-R-14, S04-R-15; ENGINE_SPEC_B S09-R-45; PRD WLD-K-01, WLD-K-04, WLD-K-08, WLD-X-01
to WLD-X-03, WLD-X-14; supervisor rulings R-76, R-79 (f), R-85 and R-114 (f)).

A contract version stores its measures at its effective date d_v. The reads serve the to-date
measures at the end of the period that contains ``as_of``, not later than the version's horizon,
from the period nodes of the version's trace. Two oracles stand outside that reader:

- the figures the PRD documents for its key contracts (WLD-X-02, WLD-X-03, WLD-X-14) and the
  arithmetic of their rules (ALG-01 daily series, output percent, units delivered, the JET-14
  release);
- the ledger: the revenue the computation posted through the period of the cut (T-SL-04 lines of
  the ``REVENUE`` role), which no read of this module writes.

Worlds, built with the product's commands at the frozen clock 2026-09-12T12:00:00Z, the periods
FY2026-P01 to P09 open:

- K-01 ``SF-ORD-10001`` (``support.worlds.k01_pellworth``): O1 118,800.00 recognised daily over
  2026; O2 16,200.00 by output percent, 40% on 31 January and 100% on 27 February; invoices of
  120,000.00 (1 January) and 15,000.00 (27 February). Its latest event, and so d_v, is 27 February.
- ``NS-SO-DE-6001`` in the K-11 world (``support.factories.k11_world``): 200 gateway units for
  90,000.00 EUR recognised on delivery, with 900.00 payable to the customer, promised on 15 June.
- K-04 ``SF-ORD-UK-2001`` (``support.worlds.k04_saltmarsh``): contracted by AVM-UK in GBP, O1
  58,285.71 performed by AVM-US from 1 April 2026, read by a person whose role covers AVM-UK only.
- K-08 ``SF-ORD-10003`` (``support.worlds.k08_ulvane``): 800,000 API calls for 80,000.00 over
  2026, measured by usage, activated at its inception: its version is dated 1 January, nine open
  periods back, and no usage is reported.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract_version_balance, period, subledger_line
from erev_api.enums import ContractEventType
from erev_api.events.payloads import DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    GATEWAY,
    K11_CHART,
    K11World,
    Workspace,
    appended,
    booked_contract,
    computed,
    k11_world,
)
from support.principals import Actor, colleague
from support.reference import fields, get, holding, post, slug
from support.worlds import AVM_UK, AVM_US, K01, K08, k01_pellworth, k04_saltmarsh, k08_ulvane

CONTRACTS = "/api/v1/contracts"
OBLIGATIONS = "/api/v1/obligations"
EXPLAIN = "/api/v1/explain"
CLOCK_AT = "2026-09-12T12:00:00Z"
CENT = Decimal("0.01")
PRICE = Decimal("135000.00")
O1_ALLOCATED = Decimal("118800.00")  # PRD WLD-X-01
O2_ALLOCATED = Decimal("16200.00")
JANUARY = date(2026, 1, 31)
FEBRUARY = date(2026, 2, 28)
AUGUST = date(2026, 8, 31)
SEPTEMBER = date(2026, 9, 30)  # the end of the last open period: the version's horizon
# (the ``as_of`` sent or None for today, 12 September; the cut it answers at; that period's key)
CUTS = [
    (None, SEPTEMBER, "FY2026-P09"),
    ("2026-08-31", AUGUST, "FY2026-P08"),
    ("2026-08-10", AUGUST, "FY2026-P08"),  # inside a period: its end
    ("2026-02-10", FEBRUARY, "FY2026-P02"),  # before d_v, inside its period
    ("2026-01-31", JANUARY, "FY2026-P01"),  # a look-back before O2 was complete
    ("2026-12-31", SEPTEMBER, "FY2026-P09"),  # beyond the horizon: the horizon
]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def money(amount: Decimal | str, currency: str = "USD") -> dict[str, str]:
    return {"amount": f"{Decimal(amount):.2f}", "currency": currency}


# --- the oracles ---------------------------------------------------------------------------------


def daily(allocated: Decimal, start: date, days: int, through: date) -> Decimal:
    """POLICIES ALG-01: a DAILY series of ``allocated`` over ``days`` from ``start``, the
    cumulative amount through ``through`` rounded once (PRD WLD-X-02: 118,800 × 273 ÷ 365)."""
    elapsed = min(max((through - start).days + 1, 0), days)
    return (allocated * elapsed / days).quantize(CENT, rounding=ROUND_HALF_UP)


def k01_o1(through: date) -> Decimal:
    return daily(O1_ALLOCATED, date(2026, 1, 1), 365, through)


def k01_o2(through: date) -> Decimal:
    """Output percent: 40% recorded on 31 January, 100% on 27 February."""
    if through >= date(2026, 2, 27):
        return O2_ALLOCATED
    return O2_ALLOCATED * Decimal("0.4") if through >= JANUARY else Decimal(0)


def k01_billed(through: date) -> tuple[Decimal, Decimal]:
    """(O1, O2): INV-US-1001 120,000.00 on 1 January, INV-US-1044 15,000.00 on 27 February."""
    return (
        Decimal("120000.00") if through >= date(2026, 1, 1) else Decimal(0),
        Decimal("15000.00") if through >= date(2026, 2, 27) else Decimal(0),
    )


def posted_revenue(
    place: Workspace, contract_id: Any, through: date, obligation_id: Any = None
) -> Decimal:
    """The ledger: the contract's posted ``REVENUE`` in the periods ending on or before
    ``through``, credits positive (T-SL-04 ``amount_txn`` is signed, debit positive)."""
    statement = (
        select(func.coalesce(func.sum(subledger_line.c.amount_txn), 0))
        .select_from(
            subledger_line.join(
                period,
                (period.c.tenant_id == subledger_line.c.tenant_id)
                & (period.c.id == subledger_line.c.period_id),
            )
        )
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.book_code == "ASC606",
            subledger_line.c.account_role == "REVENUE",
            period.c.end_date <= through,
        )
    )
    if obligation_id is not None:
        statement = statement.where(subledger_line.c.obligation_id == obligation_id)
    return -Decimal(place.scalar(statement))


# --- reads ---------------------------------------------------------------------------------------


def shown(app: FastAPI, actor: Actor, path: str, as_of: str | None = None) -> Any:
    response = get(app, path, actor, {} if as_of is None else {"as_of": as_of})
    assert response.status_code == 200, (path, as_of, response.text)
    return response.json()


def obligations_of(
    app: FastAPI, actor: Actor, contract_id: Any, as_of: str | None = None
) -> dict[str, dict[str, Any]]:
    listed = shown(app, actor, f"{CONTRACTS}/{contract_id}/obligations", as_of)
    return {item["obligation_key"]: item for item in listed["items"]}


def step(contract: Mapping[str, Any], name: str) -> dict[str, Any]:
    (found,) = [item for item in contract["steps"] if item["step"] == name]
    return dict(found)


def close_to(text: str | None, expected: Decimal) -> bool:
    """A Decimal ratio of the API against the exact quotient, to twelve places."""
    return text is not None and abs(Decimal(text) - expected) < Decimal("1e-12")


def identity(item: Mapping[str, Any]) -> bool:
    """03 REQ-REC-021: allocated = recognized to date + scheduled + awaiting trigger."""
    return Decimal(item["current"]["allocated_amount"]["amount"]) == (
        Decimal(item["to_date"]["revenue"]["amount"])
        + Decimal(item["scheduled"]["amount"])
        + Decimal(item["awaiting_trigger"]["amount"])
    )


# --- K-01: a time-based and an event-driven obligation -------------------------------------------


@pytest.mark.parametrize(("as_of", "cut", "key"), CUTS, ids=[str(item[0]) for item in CUTS])
def test_contract_and_obligation_figures_are_those_of_the_cut(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    as_of: str | None,
    cut: date,
    key: str,
) -> None:
    """The header, the list row, the obligations and the balances answer at the end of the period
    that contains ``as_of``, capped at the horizon; the version reads answer the version."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    o1, o2 = k01_o1(cut), k01_o2(cut)
    billed_o1, billed_o2 = k01_billed(cut)
    revenue, billed = o1 + o2, billed_o1 + billed_o2
    measured = {"period_key": key, "end_date": cut.isoformat()}

    # The ledger agrees with the oracle before any read is asserted against either.
    assert posted_revenue(world.place, contract_id, cut) == revenue

    contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", as_of)
    kpis = contract["kpis"]
    assert (
        kpis["transaction_price"],
        kpis["revenue_to_date"],
        kpis["billed_to_date"],
        # ENGINE_SPEC_B S09-R-45: time places O1's remainder in later periods, so it is
        # scheduled; O2 is measured by recorded progress, so what it has not earned at the cut
        # awaits its trigger — in the look-back of January, 60% of it (rev 1.174).
        kpis["scheduled"],
        kpis["awaiting_trigger"],
        # The remainder at the cut decides (04 API-C-10 rev 1.213; item RPT-RPO-ROLLFWD-1;
        # supervisor ruling R-121 (g)): O2, satisfied at d_v, is in the RPO of the January
        # look-back with the 60% it had not earned then, as the RPO report states it there.
        # (Until that ruling this test held that it stays outside the RPO in a look-back too.)
        kpis["rpo"],
    ) == (
        money(PRICE),
        money(revenue),
        money(billed),
        money(O1_ALLOCATED - o1),
        money(O2_ALLOCATED - o2),
        money(O1_ALLOCATED - o1 + O2_ALLOCATED - o2),
    )
    assert contract["kpis_ratios"]["pending_trigger_count"] == (0 if o2 == O2_ALLOCATED else 1)
    assert close_to(contract["kpis_ratios"]["recognized"], revenue / PRICE)
    assert close_to(contract["kpis_ratios"]["billed"], billed / PRICE)
    assert close_to(step(contract, "RECOGNITION")["detail"]["recognized_ratio"], revenue / PRICE)
    (balance,) = kpis["balances"]
    assert (
        balance["entity"]["code"],
        balance["contract_liability"],
        balance["contract_asset"],
        balance["unbilled_receivable"],
    ) == (AVM_US, money(billed - revenue), money("0.00"), money("0.00"))
    context = contract["context"]
    assert (context["as_of"], context["computed_at"], context["measured_period"]) == (
        as_of or "2026-09-12",
        CLOCK_AT,
        measured,
    )

    # GET /contracts: the row carries the same figures, without the balances.
    rows = shown(app, maya, CONTRACTS, as_of)["items"]
    (row,) = [item for item in rows if item["id"] == contract_id]
    assert row["kpis"] == {name: value for name, value in kpis.items() if name != "balances"}
    assert (row["kpis_ratios"], row["context"]) == (contract["kpis_ratios"], context)

    # The obligations: O1 by elapsed days, O2 by its recorded progress.
    items = obligations_of(app, maya, contract_id, as_of)
    first, second = items["O1"], items["O2"]
    assert all(identity(item) for item in (first, second))
    assert (
        first["to_date"]["revenue"],
        first["to_date"]["billed"],
        first["remaining"]["allocation"],
        first["remaining"]["billing"],
        first["scheduled"],
        first["awaiting_trigger"],
        first["position"],
        first["satisfaction_status"],
    ) == (
        money(o1),
        money(billed_o1),
        money(O1_ALLOCATED - o1),
        money("0.00"),
        money(O1_ALLOCATED - o1),
        money("0.00"),
        {"label": "CONTRACT_LIABILITY", "amount": money(billed_o1 - o1)},
        "PARTIALLY_SATISFIED",
    )
    elapsed = Decimal((cut - date(2026, 1, 1)).days + 1)
    assert close_to(first["to_date"]["progress_ratio"], elapsed / 365)
    assert close_to(first["ratios"]["recognized"], o1 / O1_ALLOCATED)
    assert close_to(first["ratios"]["scheduled"], (O1_ALLOCATED - o1) / O1_ALLOCATED)
    assert posted_revenue(world.place, contract_id, cut, first["id"]) == o1
    assert (
        second["to_date"]["revenue"],
        second["to_date"]["billed"],
        second["remaining"]["allocation"],
        # ENGINE_SPEC_B S10-R-05: the plan of 15,000.00 less the billing at the cut.
        second["remaining"]["billing"],
        second["scheduled"],
        second["awaiting_trigger"],
        second["position"],
        second["satisfaction_status"],
    ) == (
        money(o2),
        money(billed_o2),
        money(O2_ALLOCATED - o2),
        money(Decimal("15000.00") - billed_o2),
        money("0.00"),
        money(O2_ALLOCATED - o2),
        {"label": "CONTRACT_ASSET", "amount": money(o2 - billed_o2)},
        "SATISFIED" if o2 == O2_ALLOCATED else "PARTIALLY_SATISFIED",
    )
    assert Decimal(second["to_date"]["progress_ratio"]) == o2 / O2_ALLOCATED
    assert close_to(second["ratios"]["awaiting_trigger"], (O2_ALLOCATED - o2) / O2_ALLOCATED)
    assert Decimal(second["ratios"]["scheduled"]) == 0
    for item in (first, second):
        assert item["context"]["measured_period"] == measured
        assert item["context"]["computed_at"] == CLOCK_AT
        version_path = f"{EXPLAIN}/obligation_version/{item['obligation_version_id']}"
        assert (
            item["links"]["explain_revenue_to_date"],
            item["links"]["explain_billed_to_date"],
        ) == (f"{version_path}/revenue_cum?period={key}", f"{version_path}/billed_cum?period={key}")
        single = shown(app, maya, f"{OBLIGATIONS}/{item['id']}", as_of)
        assert single == item

    # GET /contracts/{id}/balances: the same balance; the functional members only at the
    # version's latest period, because the engine publishes no functional node per period.
    (row,) = shown(app, maya, f"{CONTRACTS}/{contract_id}/balances", as_of)["items"]
    assert (row["contract_liability"], row["net_position"], row["context"]["measured_period"]) == (
        money(billed - revenue),
        money(billed - revenue),  # D-12: billed less revenue
        measured,
    )
    functional = row["functional"]
    if cut == SEPTEMBER:
        assert functional["contract_liability"] == money(billed - revenue)
        assert functional["contract_asset"] == money("0.00")
        assert functional["net_position"] is None  # T-CON-09 keeps no functional net position
    else:
        assert set(functional.values()) == {None}

    # The version reads answer the version as stored, at d_v (27 February), whatever ``as_of``.
    number = context["version_no"]
    version = shown(app, maya, f"{CONTRACTS}/{contract_id}/versions/{number}", as_of)
    at_d_v = k01_o1(date(2026, 2, 27))
    assert at_d_v == Decimal("18877.81")
    assert version["revenue_to_date"] == money(at_d_v + O2_ALLOCATED)
    stored = {item["obligation_key"]: item for item in version["obligations"]}
    assert stored["O1"]["to_date"]["revenue"] == money(at_d_v)
    assert stored["O1"]["context"]["measured_period"] is None
    assert stored["O1"]["links"]["explain_revenue_to_date"].endswith("/revenue_cum")
    listed = shown(app, maya, f"{OBLIGATIONS}/{first['id']}/versions")["items"]
    assert {item["to_date"]["revenue"]["amount"] for item in listed} >= {f"{at_d_v:.2f}"}
    assert {item["context"]["measured_period"] for item in listed} == {None}


def test_documented_figures_of_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD WLD-X-02 and WLD-X-03: O1 cumulative 79,091.51 and 88,855.89; contract liability
    39,708.49 at 31 August and 29,944.11 at 30 September (billed 135,000.00 less cumulative revenue
    95,291.51 and 105,055.89). Before this item every read answered 35,077.81, the version's figure
    at 27 February, beside the September balance."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    for as_of, revenue, liability, cumulative in (
        ("2026-08-31", "95291.51", "39708.49", "79091.51"),
        ("2026-09-30", "105055.89", "29944.11", "88855.89"),
    ):
        contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", as_of)
        (balance,) = contract["kpis"]["balances"]
        items = obligations_of(app, maya, contract_id, as_of)
        assert (
            contract["kpis"]["revenue_to_date"],
            balance["contract_liability"],
            items["O1"]["to_date"]["revenue"],
        ) == (money(revenue), money(liability), money(cumulative))


def test_before_the_first_period_nothing_is_measured(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """An ``as_of`` before the first period the version measures answers zero revenue, billing and
    balances, names no measured period, and its Explain links name the version's nodes."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", "2025-12-15")
    kpis = contract["kpis"]
    assert (
        kpis["revenue_to_date"],
        kpis["billed_to_date"],
        # each obligation's whole allocation, in the part its pattern places it (rev 1.174)
        kpis["scheduled"],
        kpis["awaiting_trigger"],
        kpis["transaction_price"],
    ) == (money("0.00"), money("0.00"), money(O1_ALLOCATED), money(O2_ALLOCATED), money(PRICE))
    (balance,) = kpis["balances"]
    assert {balance[name]["amount"] for name in ("contract_liability", "contract_asset")} == {
        "0.00"
    }
    assert contract["context"]["measured_period"] is None
    for item in obligations_of(app, maya, contract_id, "2025-12-15").values():
        assert identity(item)
        assert (
            item["to_date"]["revenue"]["amount"],
            item["to_date"]["billed"]["amount"],
            Decimal(item["to_date"]["progress_ratio"]),
            item["satisfaction_status"],
            item["position"]["label"],
            item["context"]["measured_period"],
        ) == ("0.00", "0.00", Decimal(0), "UNSATISFIED", "NONE", None)
        assert item["links"]["explain_revenue_to_date"].endswith("/revenue_cum")
        # 04 §16.11: the figure is 0 and no node holds it.
        refused = get(
            app,
            f"{EXPLAIN}/obligation/{item['id']}/revenue_to_date",
            maya,
            {"as_of": "2025-12-15"},
        )
        assert (refused.status_code, slug(refused)) == (404, "not-found"), refused.text


def test_schedule_lines_read_recognized_from_the_ledger(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 API-S-ScheduleLine rev 1.132 (R-76 (b), R-79 (f)): a REVENUE line is RECOGNIZED when the
    ledger holds a REVENUE line of its contract, obligation and period. The computation posted
    January to September; no posting names a schedule line, which the state used to read."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    assert world.place.scalar(
        select(func.count())
        .select_from(subledger_line)
        .where(
            subledger_line.c.contract_id == contract_id,
            subledger_line.c.schedule_line_id.is_not(None),
        )
    ) == (0)
    posted = [f"FY2026-P{month:02d}" for month in range(1, 10)]
    later = [f"FY2026-P{month:02d}" for month in range(10, 13)]
    for path, params in (
        (f"{CONTRACTS}/{contract_id}/schedule", {"limit": "500"}),
        ("/api/v1/schedule-lines", {"contract": contract_id, "limit": "500"}),
    ):
        listed = get(app, path, maya, params)
        assert listed.status_code == 200, listed.text
        states: dict[str, dict[str, str]] = {"O1": {}, "O2": {}}
        for item in listed.json()["items"]:
            assert item["schedule_kind"] == "REVENUE"
            states[item["obligation_key"]][item["period"]["period_key"]] = item["state"]
        assert states["O1"] == {
            **dict.fromkeys(posted, "RECOGNIZED"),
            **dict.fromkeys(later, "SCHEDULED"),
        }
        # O2 has a line where an amount exists: the 40% of January and the rest in February.
        assert states["O2"] == {"FY2026-P01": "RECOGNIZED", "FY2026-P02": "RECOGNIZED"}


def test_explain_of_an_obligation_names_the_node_of_the_cut(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """04 §16.11 rev 1.132: the Explain of an obligation's to-date measure is the figure the
    obligation read serves; ``verify`` recomputes the same node; the links of the read resolve."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    items = obligations_of(app, maya, contract_id, "2026-08-31")
    first = items["O1"]
    august = {"as_of": "2026-08-31"}
    explained = get(app, f"{EXPLAIN}/obligation/{first['id']}/revenue_to_date", maya, august)
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert (
        body["root_node_id"],
        body["value"],
        body["object"]["period_key"],
        body["context"]["measured_period"],
        body["context"]["computed_at"],
    ) == (
        "revenue_cum:SF-ORD-10001/O1:FY2026-P08",
        money("79091.51"),  # PRD WLD-X-02
        "FY2026-P08",
        {"period_key": "FY2026-P08", "end_date": "2026-08-31"},
        CLOCK_AT,
    )
    verified = post(
        app,
        f"{EXPLAIN}/obligation/{first['id']}/revenue_to_date/verify?as_of=2026-08-31",
        maya,
        {},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json() == {
        "recomputed_value": "79091.51",
        "stored_value": "79091.51",
        "matches": True,
    }
    billed = get(app, f"{EXPLAIN}/obligation/{first['id']}/billed_to_date", maya, august)
    assert billed.status_code == 200, billed.text
    assert (billed.json()["root_node_id"], billed.json()["value"]) == (
        "billed_cum:SF-ORD-10001/O1:FY2026-P08",
        money("120000.00"),
    )
    # The version's own node stays what the version object type answers without a period.
    stored = get(
        app, f"{EXPLAIN}/obligation_version/{first['obligation_version_id']}/revenue_cum", maya
    )
    assert stored.status_code == 200, stored.text
    assert (stored.json()["root_node_id"], stored.json()["value"]) == (
        "revenue_cum:SF-ORD-10001/O1:-",
        money("18877.81"),
    )
    # The links of every obligation read resolve to the figure beside them.
    for item in items.values():
        for link, member in (
            ("explain_revenue_to_date", "revenue"),
            ("explain_billed_to_date", "billed"),
        ):
            path, _, query = item["links"][link].partition("?")
            name, _, value = query.partition("=")
            linked = get(app, path, maya, {name: value})
            assert linked.status_code == 200, (item["links"][link], linked.text)
            assert linked.json()["value"] == item["to_date"][member]


# --- the balances name their explanation ---------------------------------------------------------


def explain_links(body: Any) -> Iterator[tuple[str, str]]:
    """Every (member name, address) of a ``links`` object's ``explain…`` members, anywhere in a
    response; a null link names nothing."""
    if isinstance(body, list):
        for item in body:
            yield from explain_links(item)
    elif isinstance(body, dict):
        for name, value in body.items():
            if name == "links" and isinstance(value, dict):
                for member, address in value.items():
                    if member.startswith("explain") and address is not None:
                        yield member, str(address)
            else:
                yield from explain_links(value)


def followed(app: FastAPI, actor: Actor, address: str) -> Any:
    """The explanation a link names: the address as sent, its query string included."""
    path, _, query = address.partition("?")
    params = dict(pair.split("=", 1) for pair in query.split("&")) if query else {}
    response = get(app, path, actor, params)
    assert response.status_code == 200, (address, response.text)
    return response.json()


@pytest.mark.parametrize(
    ("as_of", "cut", "key"),
    [(None, SEPTEMBER, "FY2026-P09"), ("2026-08-31", AUGUST, "FY2026-P08")],
    ids=["today", "2026-08-31"],
)
def test_the_balances_of_a_contract_name_their_explanation(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    as_of: str | None,
    cut: date,
    key: str,
) -> None:
    """EXPLAIN-BALANCE-LINKS-1 (04 API-S-Contract ``kpis.balances[]``, API-S-ContractBalance and
    §16.11, rev 1.174). The explanation of a balance is addressed by the id of its T-CON-09 row,
    and the balance entries carry that address with the period of the cut: followed as sent, each
    of the three answers the figure the entry shows, at that period (PRD WLD-X-03: 39,708.49 at 31
    August, 29,944.11 at 30 September). Before this item no response carried the row's id, so the
    workbench sent the contract version's and the route answered 404."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    (stored,) = world.place.rows(select(contract_version_balance.c.id))
    liability = sum(k01_billed(cut)) - k01_o1(cut) - k01_o2(cut)
    assert liability == Decimal("29944.11" if cut == SEPTEMBER else "39708.49")

    contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", as_of)
    (balance,) = contract["kpis"]["balances"]
    base = f"{EXPLAIN}/contract_version_balance/{stored['id']}"
    assert balance["links"] == {
        f"explain_{name}": f"{base}/{name}?period={key}"
        for name in ("contract_liability", "contract_asset", "unbilled_receivable")
    }
    for name, amount in (
        ("contract_liability", liability),
        ("contract_asset", Decimal(0)),
        ("unbilled_receivable", Decimal(0)),
    ):
        explained = followed(app, maya, balance["links"][f"explain_{name}"])
        assert explained["value"] == balance[name] == money(amount), name
        assert (explained["object"]["measure"], explained["object"]["period_key"]) == (name, key)
    (row,) = shown(app, maya, f"{CONTRACTS}/{contract_id}/balances", as_of)["items"]
    assert row["links"] == balance["links"]

    # The version read answers the version as stored: its links name no period and explain the
    # stored figure, the node of the version's latest period.
    number = contract["context"]["version_no"]
    version = shown(app, maya, f"{CONTRACTS}/{contract_id}/versions/{number}", as_of)
    (kept,) = version["balances"]
    assert kept["links"]["explain_contract_liability"] == f"{base}/contract_liability"
    latest = followed(app, maya, kept["links"]["explain_contract_liability"])
    assert latest["value"] == kept["contract_liability"] == money("29944.11")
    assert latest["object"]["period_key"] == "FY2026-P09"

    # What the workbench sent: the contract version's id is not a balance row's.
    wrong = get(
        app,
        f"{EXPLAIN}/contract_version_balance/{contract['context']['contract_version_id']}"
        "/contract_liability",
        maya,
        {"period": key},
    )
    assert (wrong.status_code, slug(wrong)) == (404, "not-found"), wrong.text


def test_before_the_first_period_a_balance_names_no_explanation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """The balances of a cut before the first period the version measures are 0 and no node holds
    them: the entry's links are null, as its measured period is."""
    world = k01_pellworth(app, keyring, clock, files)
    contract_id = str(world.contracts[K01].contract["id"])
    contract = shown(app, world.maya, f"{CONTRACTS}/{contract_id}", "2025-12-15")
    (balance,) = contract["kpis"]["balances"]
    assert set(balance["links"].values()) == {None}
    (row,) = shown(app, world.maya, f"{CONTRACTS}/{contract_id}/balances", "2025-12-15")["items"]
    assert set(row["links"].values()) == {None}


@pytest.mark.parametrize("as_of", [None, "2026-08-31", "2026-01-31", "2025-12-15"])
def test_every_explain_link_a_contract_read_sends_resolves(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    as_of: str | None,
) -> None:
    """The guard of EXPLAIN-BALANCE-LINKS-1: every ``links.explain…`` address the contract reads
    send — the header, the list row, the obligations, the balances, the version, the schedule —
    is followed as sent and answers 200, at today's cut, at two look-backs and before the first
    period. An address a screen has to build from an id no response carries is not a link; this
    test fails for a link that names a subject the Explain route does not find."""
    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    base = f"{CONTRACTS}/{contract_id}"
    contract = shown(app, maya, base, as_of)
    number = contract["context"]["version_no"]
    sent: dict[str, set[str]] = {}
    for path in (
        base,
        CONTRACTS,
        f"{base}/obligations",
        f"{base}/balances",
        f"{base}/versions/{number}",
        f"{base}/schedule",
    ):
        for member, address in explain_links(shown(app, maya, path, as_of)):
            sent.setdefault(member, set()).add(address)
    # the members the reads carry today; a new one joins the guard by being sent
    expected = {
        "explain",  # API-S-ScheduleLine
        "explain_transaction_price",
        "explain_revenue_to_date",
        "explain_billed_to_date",
        "explain_allocated_amount",
        # at a cut before the first period only the version read's entry names them
        "explain_contract_liability",
        "explain_contract_asset",
        "explain_unbilled_receivable",
    }
    if as_of == "2025-12-15":
        expected.remove("explain")  # the schedule read answers no line before the first period
    assert set(sent) >= expected, sorted(set(sent))
    for addresses in sent.values():
        for address in sorted(addresses):
            followed(app, maya, address)


# --- K-08: a usage obligation dated back nine open periods ---------------------------------------

USAGE_PRICE = Decimal("80000.00")
# (the ``as_of`` sent or None for today; the cut it answers at; that period's key, None before
# the first period the version measures)
USAGE_CUTS = [
    (None, SEPTEMBER, "FY2026-P09"),
    ("2026-06-30", date(2026, 6, 30), "FY2026-P06"),
    ("2026-01-01", JANUARY, "FY2026-P01"),  # d_v itself: the end of its period
    ("2026-12-31", SEPTEMBER, "FY2026-P09"),  # beyond the horizon: the horizon
    ("2025-12-31", date(2025, 12, 31), None),  # before the first period: nothing is recognised
]


def remainder_of(item: Mapping[str, Any]) -> Decimal:
    """The scheduled and the awaiting-trigger amount of a read together: the remainder, which the
    classification of it does not move."""
    return Decimal(item["scheduled"]["amount"]) + Decimal(item["awaiting_trigger"]["amount"])


@pytest.mark.parametrize(
    ("as_of", "cut", "key"), USAGE_CUTS, ids=[str(item[0]) for item in USAGE_CUTS]
)
def test_revenue_since_the_version_leaves_the_scheduled_fee_of_a_usage_obligation(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    as_of: str | None,
    cut: date,
    key: str | None,
) -> None:
    """ENG-USAGE-FIXED-SCHEDULE-1 (ENGINE_SPEC_B S09-R-45 rev 1.126; 04 API-C-10 rev 1.178;
    supervisor ruling R-116 (a)), on the world of CTR-TODATE-AWAITING-1 (browser-QA finding Q-55;
    supervisor ruling R-114 (f)): the stated consideration of a usage obligation is recognised as
    time elapses and no event moves it, so the engine calls its remainder scheduled. K-08's
    version is dated 1 January and holds 219.18 recognised, 79,780.82 scheduled and nothing
    awaiting trigger; through September the computation posts 59,835.62. At a cut the revenue
    since the version date leaves the scheduled amount, and at a cut before the version's date it
    returns to it, as the version's own trace says: the three add up to the allocation and none is
    below zero.

    The classification moved with that revision and no total did. Until then the engine called
    the remainder awaiting trigger, and this test — named
    ``test_revenue_since_the_version_leaves_what_awaited_a_trigger`` — held 0.00 scheduled beside
    it and one obligation pending its trigger. The revenue, the remainder and the RPO of every cut
    are the figures it held."""
    world = k08_ulvane(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K08].contract["id"])
    revenue = daily(USAGE_PRICE, date(2026, 1, 1), 365, cut)
    remainder = USAGE_PRICE - revenue
    measured = None if key is None else {"period_key": key, "end_date": cut.isoformat()}
    if cut == SEPTEMBER:
        assert (revenue, remainder) == (Decimal("59835.62"), Decimal("20164.38"))

    # The ledger agrees with the oracle before any read is asserted against either.
    assert posted_revenue(world.place, contract_id, cut) == revenue

    contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", as_of)
    kpis = contract["kpis"]
    assert (
        kpis["transaction_price"],
        kpis["revenue_to_date"],
        kpis["scheduled"],
        kpis["awaiting_trigger"],
        kpis["rpo"],
    ) == (money(USAGE_PRICE), money(revenue), money(remainder), money("0.00"), money(remainder))
    assert remainder_of(kpis) == remainder  # the total of the two parts did not move
    assert all(Decimal(kpis[name]["amount"]) >= 0 for name in kpis if name != "balances")
    assert contract["kpis_ratios"]["pending_trigger_count"] == 0
    assert close_to(contract["kpis_ratios"]["recognized"], revenue / USAGE_PRICE)
    assert contract["context"]["measured_period"] == measured
    (row,) = shown(app, maya, CONTRACTS, as_of)["items"]
    assert row["kpis"] == {name: value for name, value in kpis.items() if name != "balances"}
    assert row["kpis_ratios"] == contract["kpis_ratios"]

    (item,) = obligations_of(app, maya, contract_id, as_of).values()
    assert identity(item)
    assert (
        item["current"]["allocated_amount"],
        item["to_date"]["revenue"],
        item["remaining"]["allocation"],
        item["scheduled"],
        item["awaiting_trigger"],
        item["context"]["measured_period"],
    ) == (
        money(USAGE_PRICE),
        money(revenue),
        money(remainder),
        money(remainder),
        money("0.00"),
        measured,
    )
    assert remainder_of(item) == remainder  # the total of the two parts did not move
    assert Decimal(item["ratios"]["awaiting_trigger"]) == 0
    assert close_to(item["ratios"]["scheduled"], remainder / USAGE_PRICE)
    assert close_to(item["ratios"]["recognized"], revenue / USAGE_PRICE)
    assert shown(app, maya, f"{OBLIGATIONS}/{item['id']}", as_of) == item
    if key is not None:
        assert posted_revenue(world.place, contract_id, cut, item["id"]) == revenue

    # The version reads answer the version as stored, at d_v (1 January), whatever ``as_of``: its
    # revenue and its remainder are the figures of before, and the remainder is scheduled.
    number = contract["context"]["version_no"]
    version = shown(app, maya, f"{CONTRACTS}/{contract_id}/versions/{number}", as_of)
    assert (version["revenue_to_date"], version["scheduled"], version["awaiting_trigger"]) == (
        money("219.18"),
        money("79780.82"),
        money("0.00"),
    )
    (stored,) = version["obligations"]
    assert (stored["to_date"]["revenue"], stored["scheduled"], stored["awaiting_trigger"]) == (
        money("219.18"),
        money("79780.82"),
        money("0.00"),
    )
    assert remainder_of(version) == remainder_of(stored) == Decimal("79780.82")


# --- consideration payable to the customer -------------------------------------------------------

GATEWAYS = Decimal("90000.00")  # 200 sensor gateway units at 450.00 EUR
PAYABLE = Decimal("900.00")
# The K-11 chart with the accounts a JET-14 entry reaches (ENGINE_SPEC S04-R-15).
PAYABLE_CHART = (
    *K11_CHART,
    ("1300", "Customer incentive asset", "ASSET", "D", "CUSTOMER_INCENTIVE_ASSET"),
    ("2400", "Consideration payable to customers", "LIABILITY", "C", "CONSIDERATION_PAYABLE"),
)


def delivery(quantity: str, day: date) -> EventIn:
    return EventIn(
        event_type=ContractEventType.DELIVERY_RECORDED,
        effective_date=day,
        payload=DeliveryRecordedV1(obligation_key="O1", quantity=quantity, trigger="DELIVERY"),
    )


def payable_contract(world: K11World) -> str:
    """200 gateway units for 90,000.00 EUR from 1 January 2026, recognised as units are
    delivered: 120 on 10 March and 30 on 20 July. 900.00 is payable to the customer, promised on
    15 June, after the first delivery."""
    body = {
        "external_id": "NS-SO-DE-6001",
        "customer_id": str(world.customer_id),
        "contracting_entity_code": "AVM-DE",
        "transaction_currency": "EUR",
        "inception_date": "2026-01-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": GATEWAY,
                "quantity": "200",
                "total_price": money(GATEWAYS, "EUR"),
            }
        ],
        "consideration_payable": [{"amount": money(PAYABLE, "EUR"), "promise_date": "2026-06-15"}],
    }
    booked = booked_contract(world.place, body, activate=True)
    contract_id = UUID(str(booked.contract["id"]))
    events = [delivery("120", date(2026, 3, 10)), delivery("30", date(2026, 7, 20))]
    appended(world.place, contract_id, 2, events)
    computed(world.place, UUID(str(booked.combination_group["id"])))
    return str(contract_id)


def test_contract_revenue_is_net_of_the_release_of_the_cut(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """ENGINE_SPEC S04-R-02: a contract's revenue is the sum of its obligations' revenue, which
    is gross of consideration payable, less the cumulative JET-14 release. The promise of 15 June
    follows a delivery and is released in full at its date (S04-R-15): nothing through May,
    900.00 from June. The version, dated 20 July, holds the release of July; a read at May is net
    of May's release, none, and is again what the ledger holds through May."""
    world = k11_world(app, keyring, clock, files, chart=PAYABLE_CHART)
    maya = world.place.author
    contract_id = payable_contract(world)
    version = shown(app, maya, f"{CONTRACTS}/{contract_id}")["context"]["version_no"]
    stored = shown(app, maya, f"{CONTRACTS}/{contract_id}/versions/{version}")
    # the version at 20 July: 150 units less the release; its price is not this test's subject
    assert stored["revenue_to_date"] == money(GATEWAYS * 150 / 200 - PAYABLE, "EUR")
    price = stored["transaction_price_buildup"]["total"]
    for as_of, cut, units, release in (
        ("2026-02-28", FEBRUARY, 0, Decimal(0)),
        ("2026-05-31", date(2026, 5, 31), 120, Decimal(0)),
        ("2026-06-30", date(2026, 6, 30), 120, PAYABLE),
        ("2026-07-31", date(2026, 7, 31), 150, PAYABLE),
        (None, SEPTEMBER, 150, PAYABLE),
    ):
        gross = GATEWAYS * units / 200
        assert posted_revenue(world.place, contract_id, cut) == gross - release, as_of
        contract = shown(app, maya, f"{CONTRACTS}/{contract_id}", as_of)
        assert contract["kpis"]["revenue_to_date"] == money(gross - release, "EUR"), as_of
        assert contract["kpis"]["transaction_price"] == price
        (item,) = obligations_of(app, maya, contract_id, as_of).values()
        assert identity(item)
        assert (item["to_date"]["revenue"], item["current"]["allocated_amount"]) == (
            money(gross, "EUR"),
            money(GATEWAYS, "EUR"),
        ), as_of


# --- a reader whose entities exclude the performing entity ---------------------------------------


def test_obligations_name_their_performing_entity_to_every_reader_of_the_contract(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """CTR-OBL-PERF-ENTITY-SCOPE-1 (supervisor ruling R-85 (c), (d)): K-04 is contracted by AVM-UK
    and its O1 is performed by AVM-US. Una's role covers AVM-UK only. She reads the contract, so
    she reads its obligations whole, with the performing entity's reference; the figures are the
    ones a reader of every entity sees, O1's revenue at the cut included; nothing else of AVM-US
    is disclosed to her. Before this item both obligation routes answered 500."""
    world = k04_saltmarsh(app, keyring, clock, files)
    maya = world.report.maya
    una_member = colleague(world.report.tenant_id, "una")
    una = holding(app, una_member, "revenue_accountant", entity_ids=[world.uk_entity_id])

    entities = get(app, "/api/v1/entities", una)
    assert entities.status_code == 200, entities.text
    assert [item["code"] for item in entities.json()["items"]] == [AVM_UK]
    hidden = get(app, f"/api/v1/entities/{world.us_entity_id}", una)
    assert (hidden.status_code, slug(hidden)) == (404, "not-found"), hidden.text

    path = f"{CONTRACTS}/{world.contract_id}"
    whole = obligations_of(app, maya, world.contract_id)
    listed = get(app, f"{path}/obligations", una)
    assert listed.status_code == 200, listed.text
    scoped = {item["obligation_key"]: item for item in listed.json()["items"]}
    assert scoped == whole
    performing = scoped["O1"]["performing_entity"]
    assert (performing["id"], performing["code"]) == (str(world.us_entity_id), AVM_US)
    assert set(performing) == {"id", "code", "name"}
    assert scoped["O2"]["performing_entity"]["code"] == AVM_UK
    # PRD WLD-X-14: 58,285.71 over 365 days from 1 April; 183 days through 30 September.
    september = daily(Decimal("58285.71"), date(2026, 4, 1), 365, SEPTEMBER)
    assert september - daily(Decimal("58285.71"), date(2026, 4, 1), 365, AUGUST) == Decimal(
        "4790.61"
    )
    assert scoped["O1"]["to_date"]["revenue"] == money(september, "GBP")
    for key, item in whole.items():
        single = get(app, f"{OBLIGATIONS}/{item['id']}", una)
        assert single.status_code == 200, (key, single.text)
        assert single.json() == item

    # The header is the same for both readers: no figure depends on a calendar Una cannot read.
    for as_of in (None, "2026-06-30"):
        assert shown(app, una, path, as_of) == shown(app, maya, path, as_of)
    # The schedule lines and ledger lines of AVM-US stay RLS-TE: Una sees none of O1's.
    lines = get(app, f"{path}/schedule", una, {"limit": "500"})
    assert lines.status_code == 200, lines.text
    assert {item["entity"]["code"] for item in lines.json()["items"]} <= {AVM_UK}


# --- a trace that cannot answer ------------------------------------------------------------------


def test_a_measure_the_trace_cannot_answer_is_refused_by_name(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 API-C-10: the contract, obligation and balance reads refuse by name, with rule id
    API-C-10, and serve no stored figure; a list row carries ``kpis: null``. The
    engine traces every measure today, so the refusal is reached by reading the version as if its
    trace held none of the to-date nodes (a test double of the loader, nothing else)."""
    from erev_api.domain.contracts import to_date

    world = k01_pellworth(app, keyring, clock, files)
    maya = world.maya
    contract_id = str(world.contracts[K01].contract["id"])
    items = obligations_of(app, maya, contract_id)
    monkeypatch.setattr(to_date, "load_nodes", lambda session, version_ids, **members: {})

    refused = get(app, f"{CONTRACTS}/{contract_id}", maya)
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert fields(refused) == [("balances[SF-ORD-10001@]", "API-C-10")]
    (error,) = refused.json()["errors"]
    assert error["message"] == (
        "Contract SF-ORD-10001: the calculation trace of contract version "
        f"{items['O1']['context']['version_no']} holds no dated member-balance node of the "
        "contract, so the period its figures reach cannot be read. Nothing is answered from the "
        "version's stored figures."
    )
    for path in (f"{CONTRACTS}/{contract_id}/obligations", f"{OBLIGATIONS}/{items['O1']['id']}"):
        refused = get(app, path, maya)
        assert (refused.status_code, fields(refused)) == (
            422,
            [("balances[SF-ORD-10001@]", "API-C-10")],
        ), refused.text
    refused = get(app, f"{CONTRACTS}/{contract_id}/balances", maya)
    assert (refused.status_code, fields(refused)) == (
        422,
        [("balances[SF-ORD-10001@]", "API-C-10")],
    ), refused.text

    listed = get(app, CONTRACTS, maya)
    assert listed.status_code == 200, listed.text
    (row,) = [item for item in listed.json()["items"] if item["id"] == contract_id]
    assert row["kpis"] is None
    assert (row["kpis_ratios"]["recognized"], row["kpis_ratios"]["billed"]) == (None, None)
    assert row["context"]["measured_period"] is None
    # The version reads do not read the to-date nodes and answer as before.
    number = row["context"]["version_no"]
    version = get(app, f"{CONTRACTS}/{contract_id}/versions/{number}", maya)
    assert version.status_code == 200, version.text
