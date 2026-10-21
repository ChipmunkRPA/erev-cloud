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


def prepared_shipping():
    basis = shipping()
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
    retained = {"currency_view": "transaction", "display_currency": "USD", "sources": []}
    collector.evidence[bridge.EVIDENCE] = retained
    prepared = replay.Prepared(
        collector,
        (source,),
        basis.entities[0].code,
        UUID(int=4),
        ("FY2026-P01",),
        UUID(int=5),
        (UUID(int=4),),
    )
    endpoints = {code: replay.project(prepared, basis, original, code) for code in bridge.BOOKS}
    assert endpoints["ASC606"][("K-01", "REVENUE")] == Decimal("1050")
    assert endpoints["IFRS15"][("K-01", "REVENUE")] == Decimal("1000")
    retained["sources"] = [
        {
            "contract_external_id": "K-01",
            "currency": "USD",
            "asc606": {
                measure: str(endpoints["ASC606"].get(("K-01", measure), 0))
                for measure in bridge.MEASURES
            },
            "ifrs15": {
                measure: str(endpoints["IFRS15"].get(("K-01", measure), 0))
                for measure in bridge.MEASURES
            },
            "step1_differs": False,
            "impairment_reversed": False,
            "fx_attribution_unavailable": False,
        }
    ]
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
