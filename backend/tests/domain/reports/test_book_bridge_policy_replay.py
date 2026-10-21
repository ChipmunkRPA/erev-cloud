"""Book-policy replay against a real dual-book shipping election computation."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from erev_api.domain.reports import book_bridge_replay as replay
from erev_api.domain.reports.builders import SourceCollector
from erev_api.domain.reports.builders import book_bridge as bridge
from erev_api.domain.reports.computation_sources import VerifiedComputation
from erev_engine import compute, upgrade
from support import bundles
from tests.engine.s03_pob_builder import test_s03_elections as worlds


def shipping():
    return worlds.bundle(
        worlds.booked(
            worlds.line("POB-01", "HW", price="1000.00"),
            worlds.line("SHIP-1", "FREIGHT", price="50.00"),
        ),
        bundles.event("K-01", 2, "CONTRACT_ACTIVATED", date(2026, 1, 1), {"checklist": {}}),
        bundles.event(
            "K-01",
            3,
            "DELIVERY_RECORDED",
            date(2026, 1, 15),
            {"obligation_key": "POB-01", "quantity": Decimal(1), "trigger": "CONTROL_TRANSFER"},
            obligation_keys=["POB-01"],
        ),
        products=[worlds.product("HW"), worlds.product("FREIGHT", "TPL-SHIP")],
        templates=[worlds.template(), worlds.template("TPL-SHIP", obligation_kind="SHIPPING")],
        ssp=[worlds.points(HW="1000.00", FREIGHT="50.00")],
        books=worlds.BOTH_BOOKS,
    )


def prepared_world(basis, *, periods=("FY2026-P01",), view="transaction", currency="USD"):
    name = basis.contracts[0].external_id
    original = compute(basis)
    source = VerifiedComputation(
        UUID(int=1),
        UUID(int=2),
        UUID(int=3),
        basis,
        upgrade.output_mapping(original),
        original.sha256(),
        {},
        None,
    )
    collector = SourceCollector()
    retained = {"currency_view": view, "display_currency": currency, "sources": []}
    collector.evidence[bridge.EVIDENCE] = retained
    prepared = replay.Prepared(
        collector,
        (source,),
        basis.entities[0].code,
        UUID(int=4),
        periods,
        UUID(int=5),
        (UUID(int=4),),
    )
    endpoints = {code: replay.project(prepared, basis, original, code) for code in bridge.BOOKS}
    retained["sources"] = [
        {
            "contract_external_id": name,
            "currency": currency,
            "asc606": {
                measure: str(endpoints["ASC606"].get((name, measure), 0))
                for measure in bridge.MEASURES
            },
            "ifrs15": {
                measure: str(endpoints["IFRS15"].get((name, measure), 0))
                for measure in bridge.MEASURES
            },
            "step1_differs": False,
            "impairment_reversed": False,
            "fx_attribution_unavailable": view != "transaction"
            and basis.contracts[0].transaction_currency != basis.entities[0].functional_currency,
        }
    ]
    return prepared


def prepared_shipping():
    prepared = prepared_world(shipping())
    row = prepared.collector.evidence[bridge.EVIDENCE]["sources"][0]
    assert Decimal(row["asc606"]["REVENUE"]) == Decimal("1050")
    assert Decimal(row["ifrs15"]["REVENUE"]) == Decimal("1000")
    return prepared


def test_shipping_election_is_quantified_by_real_policy_replay():
    prepared = prepared_shipping()
    calls = []

    def engine(bundle):
        calls.append(bundle)
        return compute(bundle)

    calculated = replay.calculate(prepared, engine=engine)
    assert len(calls) > 1
    effects = calculated.retained["sources"][0]["driver_effects"]
    assert Decimal(effects["REVENUE"]["FRAMEWORK_ELECTIONS"]) == Decimal("50")
    assert Decimal(effects["REVENUE"]["OTHER"]) == 0
    rows, _, tie = bridge.dataset_rows(bridge._restore_sources(calculated.retained["sources"]))
    driver = next(row for row in rows if row["row_key"] == "driver:FRAMEWORK_ELECTIONS:REVENUE")
    assert driver["effect"] == {"currency": "USD", "amount": "50.00"}
    assert tie["result"] == "PASS"
    assert calculated.executions[0]["steps"]


def test_original_hash_and_endpoint_mismatch_never_get_causal_labels():
    prepared = prepared_shipping()
    corrupt = replace(prepared, sources=(replace(prepared.sources[0], output_sha256="0" * 64),))
    assert not replay.calculate(corrupt, engine=compute).executions
    prepared.collector.evidence[bridge.EVIDENCE]["sources"][0]["asc606"]["REVENUE"] = "1051"
    result = replay.calculate(prepared, engine=compute)
    assert not result.executions
    assert "driver_effects" not in result.retained["sources"][0]


def test_offsetting_policy_effects_remain_visible_when_books_net_to_zero():
    item = bridge.Compared(
        "OFFSET",
        "USD",
        driver_effects={
            "REVENUE": {"FRAMEWORK_ELECTIONS": Decimal("50"), "LICENCE_RENEWALS": Decimal("-50")},
        },
    )
    rows, _, tie = bridge.dataset_rows([item])
    indexed = {row["row_key"]: row for row in rows}
    assert indexed["measure:REVENUE"]["difference"]["amount"] == "0.00"
    assert indexed["driver:FRAMEWORK_ELECTIONS:REVENUE"]["effect"]["amount"] == "50.00"
    assert indexed["driver:LICENCE_RENEWALS:REVENUE"]["effect"]["amount"] == "-50.00"
    assert indexed["contract:OFFSET:REVENUE"]["driver_code"] == "MULTIPLE"
    assert tie["result"] == "PASS"


def test_quantified_effect_is_not_hidden_by_a_separate_residual():
    item = bridge.Compared(
        "RESIDUAL",
        "USD",
        {"REVENUE": Decimal("60")},
        driver_effects={"REVENUE": {"FRAMEWORK_ELECTIONS": Decimal("50"), "OTHER": Decimal("10")}},
    )
    rows, _, tie = bridge.dataset_rows([item])
    indexed = {row["row_key"]: row for row in rows}
    assert indexed["driver:FRAMEWORK_ELECTIONS:REVENUE"]["effect"]["amount"] == "50.00"
    assert indexed["driver:OTHER:REVENUE"]["effect"]["amount"] == "10.00"
    assert tie["result"] == "PASS"


def test_unavailable_counterfactual_preserves_the_residual():
    from erev_engine.errors import EngineError

    prepared = prepared_shipping()

    def unsupported(bundle):
        if bundle.trigger == "DRY_RUN":
            raise EngineError("TEST_UNSUPPORTED_PHASE", "counterfactual unavailable")
        return compute(bundle)

    result = replay.calculate(prepared, engine=unsupported)
    effects = result.retained["sources"][0]["driver_effects"]["REVENUE"]
    assert Decimal(effects["OTHER"]) == Decimal("50")
    assert not any(Decimal(value) for key, value in effects.items() if key != "OTHER")
    assert result.executions[0]["steps"][-1]["status"] == "UNAVAILABLE"
    _, _, tie = bridge.dataset_rows(bridge._restore_sources(result.retained["sources"]))
    assert tie["result"] == "PASS"


def renewal_world(kind="RENEWAL"):
    from tests.engine.s06_modifications import test_s06_prospective as modifications

    modification = modifications.modification_input(
        "RENEW",
        date(2026, 6, 1),
        [
            modifications.mod_line(
                "L2",
                "ADD",
                "IP",
                "1",
                "900",
                start=date(2027, 1, 1),
                end=date(2027, 12, 31),
            )
        ],
        kind=kind,
    )
    return worlds.bundle(
        worlds.booked(worlds.line("L1", "IP", price="1000")),
        bundles.event("K-01", 2, "CONTRACT_ACTIVATED", date(2026, 1, 1), {"checklist": {}}),
        bundles.event(
            "K-01",
            3,
            "DELIVERY_RECORDED",
            date(2026, 1, 1),
            {"obligation_key": "L1", "quantity": Decimal(1), "trigger": "CONTROL_TRANSFER"},
            obligation_keys=["L1"],
        ),
        modifications.amended(4, modification, {"L2": "PROSPECTIVE"}),
        bundles.event(
            "K-01",
            5,
            "DELIVERY_RECORDED",
            date(2026, 6, 1),
            {"obligation_key": "L2", "quantity": Decimal(1), "trigger": "CONTROL_TRANSFER"},
            obligation_keys=["L2"],
        ),
        products=[worlds.product("IP", "TPL-IP")],
        templates=[
            worlds.template("TPL-IP", obligation_kind="LICENCE", licence_nature="FUNCTIONAL")
        ],
        ssp=[worlds.points(IP="1000")],
        books=worlds.BOTH_BOOKS,
        contracts=[replace(worlds.header(), modifications=(modification,))],
    )


def advance_fx_world():
    from support import cpc_worlds as cpc
    from support import step1_worlds as step1

    name = "C-FX"
    basis = step1.world(
        bundles.contract(name, inception=date(2026, 1, 1), currency="EUR"),
        [
            bundles.event(
                name,
                1,
                "CONTRACT_BOOKED",
                date(2026, 1, 1),
                {
                    "lines": [
                        bundles.booking_line(
                            "O1",
                            product_code="GOODS",
                            quantity="1",
                            total_price="1000",
                            start=date(2026, 1, 1),
                            end=date(2026, 12, 31),
                        )
                    ]
                },
            ),
            bundles.event(name, 2, "CONTRACT_ACTIVATED", date(2026, 1, 1), {"checklist": {}}),
            bundles.event(
                name,
                3,
                "BILLING_RECORDED",
                date(2026, 1, 10),
                {
                    "invoice_number": "INV1",
                    "line_external_id": "INV1-1",
                    "obligation_key": "O1",
                    "amount": Decimal("1000"),
                    "issue_date": date(2026, 1, 10),
                },
            ),
        ],
        products=[cpc.product("GOODS", "TPL-PIT")],
        templates=[step1.PIT],
        ssp=[cpc.ssp_book({"GOODS": "1000"}, "EUR")],
        months=2,
        books=worlds.BOTH_BOOKS,
    )
    return replace(
        basis,
        books=tuple(
            replace(
                book,
                policies=tuple(
                    replace(policy, value="DISABLED_REMEASURE_AS_MONETARY")
                    if book.book_code == "ASC606" and policy.code == "fx.cl_historical_layering"
                    else policy
                    for policy in book.policies
                ),
            )
            for book in basis.books
        ),
    )


def test_licence_renewal_guard_survives_modification_and_is_attributed():
    for kind in ("RENEWAL", "EARLY_RENEWAL"):
        basis = renewal_world(kind)
        output = compute(basis)
        recognition = {
            book.book_code: [
                intent.posting_period_key
                for intent in book.posting_intents
                if intent.subject_key == "K-01/L2" and intent.entry_kind == "REVENUE_RECOGNITION"
            ]
            for book in output.books
        }
        assert recognition == {"ASC606": ["FY2027-P01"], "IFRS15": ["FY2026-P06"]}
        prepared = prepared_world(basis, periods=("FY2026-P06",))
        result = replay.calculate(prepared, engine=compute)
        record = result.retained["sources"][0]
        assert Decimal(record["asc606"]["REVENUE"]) == 0
        assert Decimal(record["ifrs15"]["REVENUE"]) == 900
        assert Decimal(record["driver_effects"]["REVENUE"]["LICENCE_RENEWALS"]) == -900
        assert Decimal(record["driver_effects"]["REVENUE"]["OTHER"]) == 0
        _, _, tie = bridge.dataset_rows(bridge._restore_sources([record]))
        assert tie["result"] == "PASS"


def test_advance_fx_difference_is_quantified_only_in_functional_money():
    basis = advance_fx_world()
    functional = replay.calculate(prepared_world(basis, view="functional"), engine=compute)
    record = functional.retained["sources"][0]
    assert Decimal(record["asc606"]["CONTRACT_LIABILITY"]) == 1120
    assert Decimal(record["ifrs15"]["CONTRACT_LIABILITY"]) == 1100
    effects = record["driver_effects"]["CONTRACT_LIABILITY"]
    assert Decimal(effects["ADVANCE_CONSIDERATION_FX"]) == 20
    assert Decimal(effects["OTHER"]) == 0
    transaction = replay.calculate(prepared_world(basis, currency="EUR"), engine=compute)
    txn = transaction.retained["sources"][0]
    assert Decimal(txn["asc606"]["CONTRACT_LIABILITY"]) == 1000
    assert Decimal(txn["ifrs15"]["CONTRACT_LIABILITY"]) == 1000
    assert all(
        Decimal(value) == 0 for value in txn["driver_effects"]["CONTRACT_LIABILITY"].values()
    )
    _, _, tie = bridge.dataset_rows(bridge._restore_sources([record]))
    assert tie["result"] == "PASS"
