"""frps3c-1 — configuration evidence for every adapter + the balance family's consumed customer
association / names (Codex design review fa64924e D1; design §2.1, §10.1, §10.4). FAIL-FIRST:
written before the code; the first run must fail on the missing names (`tie_outs.CONFIGURATION`,
`record_configuration`, `customer_of`, `BOUND_INPUT_MISSING`, the `params=` keyword of
`entities` / `calendars`)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import ADAPTER, ReportParams, SourceBinding, SourceCollector
from erev_api.problems import Problem

K = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
US01 = uuid5(NAMESPACE_URL, "erev://tests/entity/US01")
GB01 = uuid5(NAMESPACE_URL, "erev://tests/entity/GB01")
CAL = uuid5(NAMESPACE_URL, "erev://tests/calendar/fy")
P09 = uuid5(NAMESPACE_URL, "erev://tests/period/2026-09")
K01 = uuid5(NAMESPACE_URL, "erev://tests/contract/K01")
K02 = uuid5(NAMESPACE_URL, "erev://tests/contract/K02")
CUST = uuid5(NAMESPACE_URL, "erev://tests/customer/pellworth")


def _params(**over: Any) -> ReportParams:
    base: dict[str, Any] = {
        "report_code": "contract_balances",
        "report_version": 1,
        "parameters": {},
        "entity_ids": (US01,),
        "known_at": K,
        "book_code": "ASC606",
    }
    base.update(over)
    return ReportParams(**base)


class _NoQueries:
    def execute(self, statement: Any) -> Any:
        raise AssertionError(f"live query under a bound run: {str(statement)[:60]}")


class _Rows:
    """``execute(...).mappings()`` yields the fixed rows; counts the queries."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.executed = 0

    def execute(self, statement: Any) -> Any:
        self.executed += 1
        return SimpleNamespace(mappings=lambda: iter(self.rows), scalar_one=lambda: self.rows[0])


ENTITY_ROWS = [
    {
        "id": US01,
        "code": "US01",
        "calendar_id": CAL,
        "functional_currency": "USD ",
        "time_zone": "America/New_York",
    },
    {
        "id": GB01,
        "code": "GB01",
        "calendar_id": CAL,
        "functional_currency": "GBP",
        "time_zone": "Europe/London",
    },
]
PERIOD_ROWS = [
    {
        "id": P09,
        "calendar_id": CAL,
        "period_key": "FY2026-P09",
        "name": "Sep 2026",
        "fiscal_year": 2026,
        "period_no": 9,
        "quarter_no": 3,
        "start_date": date(2026, 9, 1),
        "end_date": date(2026, 9, 30),
    }
]
CONFIGURATION = {
    "entities": {
        str(US01): {
            "code": "US01",
            "calendar_id": str(CAL),
            "functional_currency": "USD",
            "time_zone": "America/New_York",
        },
    },
    "periods": {
        str(CAL): [
            {
                "id": str(P09),
                "key": "FY2026-P09",
                "name": "Sep 2026",
                "fiscal_year": 2026,
                "period_no": 9,
                "quarter_no": 3,
                "start": "2026-09-01",
                "end": "2026-09-30",
            }
        ]
    },
    "book_code": "ASC606",
}
BOUND = SourceBinding(
    cutoff=K,
    versions={"ASC606": ()},
    labels={tie_outs.CUSTOMER_NAME: {str(CUST): "Pellworth Ltd"}},
    row_keys=frozenset(),
    evidence={
        tie_outs.CONFIGURATION: CONFIGURATION,
        tie_outs.CUSTOMER_ASSOCIATION: {str(K01): str(CUST), str(K02): None},
    },
)


def test_a_live_build_records_the_consumed_entities_and_calendars_as_configuration_evidence() -> (
    None
):
    collector = SourceCollector()
    params = _params(entity_ids=(US01, GB01), sources=collector)
    found = tie_outs.entities(_Rows(ENTITY_ROWS), (US01, GB01), params=params)  # type: ignore[arg-type]
    assert sorted(item.code for item in found) == ["GB01", "US01"]  # the DB orders by code
    calendars = tie_outs.calendars(_Rows(PERIOD_ROWS), found, params=params)  # type: ignore[arg-type]
    assert calendars[US01].periods[0].key == "FY2026-P09"
    stored = collector.evidence[tie_outs.CONFIGURATION]
    assert set(stored["entities"]) == {str(US01), str(GB01)}
    assert stored["entities"][str(US01)]["functional_currency"] == "USD"  # stripped, as EntityRef
    assert stored["periods"][str(CAL)][0]["start"] == "2026-09-01"  # ISO dates, JSON-safe
    # the book: a run WITHOUT a book parameter reads the tenant's primary book — recorded too
    assert "book_code" not in stored  # book_of records it only when it read the default


def test_a_bound_read_returns_the_retained_configuration_without_a_query() -> None:
    params = _params(binding=BOUND)
    found = tie_outs.entities(_NoQueries(), (US01,), params=params)  # type: ignore[arg-type]
    (us01,) = found
    assert (us01.code, us01.calendar_id, us01.functional_currency, us01.time_zone) == (
        "US01",
        CAL,
        "USD",
        "America/New_York",
    )
    calendars = tie_outs.calendars(_NoQueries(), found, params=params)  # type: ignore[arg-type]
    period = calendars[US01].periods[0]
    assert (period.id, period.key, period.start, period.end) == (
        P09,
        "FY2026-P09",
        date(2026, 9, 1),
        date(2026, 9, 30),
    )


def test_a_bound_read_refuses_an_entity_or_calendar_the_binding_does_not_hold_by_name() -> None:
    params = _params(binding=BOUND)
    with pytest.raises(Problem) as missing:
        tie_outs.entities(_NoQueries(), (US01, GB01), params=params)  # type: ignore[arg-type]
    assert "configuration.entities" in str(missing.value.detail) and str(GB01) in str(
        missing.value.detail
    )
    other = replace(
        BOUND,
        evidence={**BOUND.evidence, tie_outs.CONFIGURATION: {**CONFIGURATION, "periods": {}}},
    )
    with pytest.raises(Problem) as no_calendar:
        tie_outs.calendars(
            _NoQueries(),  # type: ignore[arg-type]
            tie_outs.entities(_NoQueries(), (US01,), params=_params(binding=other)),  # type: ignore[arg-type]
            params=_params(binding=other),
        )
    assert "configuration.periods" in str(no_calendar.value.detail)
    # a binding with NO configuration kind at all: the existing incomplete-binding refusal, by name
    with pytest.raises(Problem) as absent:
        tie_outs.entities(
            _NoQueries(), (US01,), params=_params(binding=replace(BOUND, evidence={}))
        )  # type: ignore[arg-type]
    assert tie_outs.CONFIGURATION in str(absent.value.detail)


def test_book_of_records_the_primary_book_default_and_reads_it_back_bound() -> None:
    collector = SourceCollector()
    live = _params(book_code=None, parameters={}, sources=collector)

    class _Primary:
        def execute(self, statement: Any) -> Any:  # primary_book(session) reads the registry
            return SimpleNamespace(scalar_one=lambda: "ASC606", scalars=lambda: iter(["ASC606"]))

    # the given book wins without any read or record
    assert tie_outs.book_of(_NoQueries(), _params(book_code="IFRS15")) == "IFRS15"  # type: ignore[arg-type]
    bound = _params(book_code=None, parameters={}, binding=BOUND)
    assert tie_outs.book_of(_NoQueries(), bound) == "ASC606"  # type: ignore[arg-type]
    without = replace(
        BOUND, evidence={tie_outs.CONFIGURATION: {**CONFIGURATION, "book_code": None}}
    )
    with pytest.raises(Problem) as missing:
        tie_outs.book_of(_NoQueries(), _params(book_code=None, parameters={}, binding=without))  # type: ignore[arg-type]
    assert "configuration.book_code" in str(missing.value.detail)
    del live, _Primary  # the live default read needs the registry (DB-bound); not exercised here


def test_the_customer_association_is_retained_with_null_distinct_from_absent() -> None:
    """D1: contract → customer as consumed; a NULL customer is retained as null and rebuilt as
    "no customer"; a contract absent from the association refuses by name; a customer whose
    name is absent from the labels refuses by name (present-null = no name)."""
    bound = _params(binding=BOUND)
    assert tie_outs.customer_of(bound, K01, None) == CUST  # bound: the retained association
    assert tie_outs.customer_of(bound, K02, CUST) is None  # retained NULL, even if live says CUST
    with pytest.raises(Problem) as absent:
        tie_outs.customer_of(bound, uuid5(NAMESPACE_URL, "erev://tests/contract/K03"), CUST)
    assert tie_outs.CUSTOMER_ASSOCIATION in str(absent.value.detail)
    assert tie_outs.label_for(bound, tie_outs.CUSTOMER_NAME, CUST, "Renamed") == "Pellworth Ltd"
    with pytest.raises(Problem):
        tie_outs.label_for(
            bound, tie_outs.CUSTOMER_NAME, uuid5(NAMESPACE_URL, "erev://tests/customer/x"), "X"
        )
    # live: the association and the name are recorded as consumed
    collector = SourceCollector()
    live = _params(sources=collector)
    assert (
        tie_outs.customer_of(live, K01, CUST) == CUST
        and tie_outs.customer_of(live, K02, None) is None
    )
    assert collector.evidence[tie_outs.CUSTOMER_ASSOCIATION] == {
        str(K01): str(CUST),
        str(K02): None,
    }
    assert (
        tie_outs.label_for(live, tie_outs.CUSTOMER_NAME, CUST, "Pellworth Ltd") == "Pellworth Ltd"
    )
    assert collector.labels[tie_outs.CUSTOMER_NAME][str(CUST)] == "Pellworth Ltd"


def test_no_adapter_declares_configuration_open_and_the_balance_family_binds_customers() -> None:
    for code, contract in framework.SOURCE_CONTRACTS.items():
        if contract.strategy == ADAPTER:
            assert not any("consumed-configuration" in item for item in contract.open), code
            assert any("configuration" in item for item in contract.bound), code
    for code in (
        "contract_balances",
        "contract_balance_rollforward",
        "revenue_from_opening_liability",
    ):
        assert any(
            "customer association" in item for item in framework.SOURCE_CONTRACTS[code].bound
        ), code
    # the four binding-by-design adapters now declare NOTHING open
    for code in ("rpo", "rpo_rollforward", "revenue_waterfall", "contract_history"):
        assert framework.SOURCE_CONTRACTS[code].open == (), code


# --- Codex -0354 on 8ede60b7: R1 retained entity code by consumed id; R2 validated shapes ------


def test_a_bound_read_carries_the_retained_entity_code_not_the_supplied_current_code() -> None:
    """R1 (reader boundary): under a binding the code comes from `labels.entity_code` by entity id;
    a supplied current code that differs is never what the rows carry; a live build records the
    supplied code; a binding without the label refuses by name."""
    bound = _params(
        binding=replace(BOUND, labels={**BOUND.labels, tie_outs.ENTITY_CODE: {str(US01): "US01"}})
    )
    assert tie_outs.entity_code_for(bound, US01, "US01-RENAMED") == "US01"
    with pytest.raises(Problem) as missing:
        tie_outs.entity_code_for(bound, GB01, "GB01")
    assert tie_outs.ENTITY_CODE in str(missing.value.detail) and str(GB01) in str(
        missing.value.detail
    )
    collector = SourceCollector()
    assert tie_outs.entity_code_for(_params(sources=collector), US01, "US01") == "US01"
    assert collector.labels[tie_outs.ENTITY_CODE] == {str(US01): "US01"}


def test_balances_at_emits_the_retained_entity_code_and_customer_not_the_joined_current_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1 (builder boundary): `balances_at` under a binding — the row's identity carries the
    RETAINED entity code and customer name although the joined current row says otherwise; the
    trace lookup is not exercised (no period → no values), so no trace store is touched."""
    version_id = uuid5(NAMESPACE_URL, "erev://tests/version/1")
    row = {
        "contract_version_id": version_id,
        "contract_id": K01,
        "entity_id": US01,
        "txn_currency": "USD ",
        "external_id": "K-01",
        "customer_id": CUST,
        "customer_name": "Renamed Customer",  # the CURRENT join
        "entity_code": "US01-RENAMED",  # the CURRENT join
    }
    monkeypatch.setattr(tie_outs, "_balance_nodes", lambda session, version: {})
    binding = replace(
        BOUND,
        versions={"ASC606": (version_id,)},
        labels={**BOUND.labels, tie_outs.ENTITY_CODE: {str(US01): "US01"}},
    )
    (found,) = tie_outs.balances_at(
        _Rows([row]),  # type: ignore[arg-type]
        entity_ids=(US01,),
        book_code="ASC606",
        period_keys={US01: None},
        cutoff=K,
        params=_params(binding=binding),
    )
    assert (found.entity_code, found.customer_name, found.contract_id) == (
        "US01",
        "Pellworth Ltd",
        K01,
    )


def test_an_inner_missing_or_malformed_retained_field_refuses_by_name_with_identity() -> None:
    """R2: present entity without `time_zone`; a malformed calendar id; a period with a malformed
    date / a non-integer fiscal year — each a NAMED refusal carrying the identity and the key;
    the admitted NULL (`quarter_no`) and an EMPTY period list stay admitted."""
    without_tz = {
        **CONFIGURATION,
        "entities": {
            str(US01): {
                k: v for k, v in CONFIGURATION["entities"][str(US01)].items() if k != "time_zone"
            }
        },
    }
    with pytest.raises(Problem) as missing:
        tie_outs.entities(
            _NoQueries(),
            (US01,),
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: without_tz})),
        )  # type: ignore[arg-type]
    assert "configuration.entities.time_zone" in str(missing.value.detail) and str(US01) in str(
        missing.value.detail
    )
    bad_calendar = {
        **CONFIGURATION,
        "entities": {
            str(US01): {**CONFIGURATION["entities"][str(US01)], "calendar_id": "not-a-uuid"}
        },
    }
    with pytest.raises(Problem) as malformed:
        tie_outs.entities(
            _NoQueries(),
            (US01,),
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: bad_calendar})),
        )  # type: ignore[arg-type]
    assert "malformed" in str(malformed.value.detail) and str(US01) in str(malformed.value.detail)
    found = tie_outs.entities(_NoQueries(), (US01,), params=_params(binding=BOUND))  # type: ignore[arg-type]
    bad_period = {
        **CONFIGURATION,
        "periods": {str(CAL): [{**CONFIGURATION["periods"][str(CAL)][0], "start": "2026-13-40"}]},
    }
    with pytest.raises(Problem) as bad_date:
        tie_outs.calendars(
            _NoQueries(),
            found,
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: bad_period})),
        )  # type: ignore[arg-type]
    assert "configuration.periods (malformed" in str(bad_date.value.detail) and str(P09) in str(
        bad_date.value.detail
    )
    bad_year = {
        **CONFIGURATION,
        "periods": {str(CAL): [{**CONFIGURATION["periods"][str(CAL)][0], "fiscal_year": "twenty"}]},
    }
    with pytest.raises(Problem):
        tie_outs.calendars(
            _NoQueries(),
            found,
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: bad_year})),
        )  # type: ignore[arg-type]
    absent_key = {
        **CONFIGURATION,
        "periods": {
            str(CAL): [
                {k: v for k, v in CONFIGURATION["periods"][str(CAL)][0].items() if k != "name"}
            ]
        },
    }
    with pytest.raises(Problem) as no_name:
        tie_outs.calendars(
            _NoQueries(),
            found,
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: absent_key})),
        )  # type: ignore[arg-type]
    assert "configuration.periods.name" in str(no_name.value.detail)
    # admitted: a null quarter and an empty period list
    admitted = {
        **CONFIGURATION,
        "periods": {str(CAL): [{**CONFIGURATION["periods"][str(CAL)][0], "quarter_no": None}]},
    }
    calendars = tie_outs.calendars(
        _NoQueries(),
        found,
        params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: admitted})),
    )  # type: ignore[arg-type]
    assert calendars[US01].periods[0].quarter_no is None
    empty = {**CONFIGURATION, "periods": {str(CAL): []}}
    assert (
        tie_outs.calendars(
            _NoQueries(),
            found,
            params=_params(binding=replace(BOUND, evidence={tie_outs.CONFIGURATION: empty})),
        )[US01].periods
        == ()
    )  # type: ignore[arg-type]


def test_the_recorded_configuration_survives_a_serialized_round_trip_into_the_same_references() -> (
    None
):
    """R2 (typed round trip): live recording → `to_stored` → JSON text → `from_stored` → bound reads
    return EntityRef / PeriodRef equal to the live ones (UUIDs, dates and integers re-typed)."""
    collector = SourceCollector()
    live = _params(entity_ids=(US01, GB01), sources=collector)
    live_entities = tie_outs.entities(_Rows(ENTITY_ROWS), (US01, GB01), params=live)  # type: ignore[arg-type]
    live_calendars = tie_outs.calendars(_Rows(PERIOD_ROWS), live_entities, params=live)  # type: ignore[arg-type]
    collector.record_cutoff(K)  # a binding needs the cutoff the build applied
    stored = json.loads(json.dumps(collector.binding(row_keys=[]).to_stored()))
    binding = SourceBinding.from_stored(stored)
    assert binding is not None
    bound = _params(entity_ids=(US01, GB01), binding=binding)
    bound_entities = tie_outs.entities(_NoQueries(), (US01, GB01), params=bound)  # type: ignore[arg-type]
    # the stub ignores ORDER BY; the bound read orders by code — compare the references as sets
    assert set(bound_entities) == set(live_entities)
    assert tie_outs.calendars(_NoQueries(), bound_entities, params=bound) == live_calendars  # type: ignore[arg-type]
    assert isinstance(bound_entities[0].calendar_id, UUID)


def test_a_malformed_enclosing_container_refuses_by_name_before_any_conversion() -> None:
    """Codex -0414 (R2 container shapes): a JSON-safe malformed CONTAINER survives `from_stored`
    (it copies evidence); `configuration = 1`, `entities = 1`, `periods = 1`, a non-list calendar
    entry and a non-mapping period row each refuse by NAME with the container's identity — never a
    raw TypeError — through a serialized round trip; a null inner container is the admitted-empty
    case (nothing retained → the id-level refusal by name)."""

    def bound_with(configuration: Any) -> ReportParams:
        stored = json.loads(
            json.dumps(replace(BOUND, evidence={tie_outs.CONFIGURATION: configuration}).to_stored())
        )
        binding = SourceBinding.from_stored(stored)
        assert binding is not None
        return _params(binding=binding)

    with pytest.raises(Problem) as whole:
        tie_outs.entities(_NoQueries(), (US01,), params=bound_with(1))  # type: ignore[arg-type]
    assert "configuration (shape: not a mapping)" in str(whole.value.detail)
    with pytest.raises(Problem) as ents:
        tie_outs.entities(
            _NoQueries(),  # type: ignore[arg-type]
            (US01,),
            params=bound_with({**CONFIGURATION, "entities": 1}),
        )
    assert "configuration.entities (shape: not a mapping)" in str(ents.value.detail)
    found = tie_outs.entities(_NoQueries(), (US01,), params=bound_with(CONFIGURATION))  # type: ignore[arg-type]
    with pytest.raises(Problem) as pers:
        tie_outs.calendars(
            _NoQueries(),  # type: ignore[arg-type]
            found,
            params=bound_with({**CONFIGURATION, "periods": 1}),
        )
    assert "configuration.periods (shape: not a mapping)" in str(pers.value.detail)
    with pytest.raises(Problem) as entry:
        tie_outs.calendars(
            _NoQueries(),  # type: ignore[arg-type]
            found,
            params=bound_with({**CONFIGURATION, "periods": {str(CAL): 1}}),
        )
    assert "configuration.periods (list)" in str(entry.value.detail)
    assert str(CAL) in str(entry.value.detail)
    with pytest.raises(Problem) as row:
        tie_outs.calendars(
            _NoQueries(),  # type: ignore[arg-type]
            found,
            params=bound_with({**CONFIGURATION, "periods": {str(CAL): [1]}}),
        )
    assert "configuration.periods (row)" in str(row.value.detail)
    with pytest.raises(Problem) as none_entities:
        tie_outs.entities(
            _NoQueries(),  # type: ignore[arg-type]
            (US01,),
            params=bound_with({**CONFIGURATION, "entities": None}),
        )
    assert "configuration.entities" in str(none_entities.value.detail)
    assert str(US01) in str(none_entities.value.detail)
