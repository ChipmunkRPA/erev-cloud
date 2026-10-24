"""Monthly exemption translation explains a movement hidden by net-zero endpoints."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from erev_api.domain.contracts.to_date import ObligationAt
from erev_api.domain.reports import reporting_currency, rpo_rollforward_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, rpo


@pytest.mark.parametrize("eligibility", [False, True])
@pytest.mark.parametrize("view", ["functional", "reporting"])
def test_exemption_round_trip_keeps_both_months_and_their_original_rates(
    monkeypatch, view, eligibility
) -> None:
    eid, cid, oid, gid, tenant_id = (uuid4() for _ in range(5))
    days = (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31))
    periods = tuple(
        tie_outs.PeriodRef(uuid4(), f"FY2026-P{n:02d}", str(n), 2026, n, 1, day.replace(day=1), day)
        for n, day in enumerate(days, 1)
    )
    versions = tuple(
        rpo._Version(
            uuid4(),
            gid,
            n,
            n != 2 if eligibility else True,
            day.replace(day=1),
            frozenset(
                {"COLLECTIBILITY_ASSESSED" if n == 2 else "CONTRACT_CRITERIA_MET"}
                if eligibility
                else {"CONTRACT_AMENDED"}
            ),
            entries=((cid, day.replace(day=1)),) if eligibility and n != 2 else (),
            eligibility_exits=((cid, day.replace(day=1)),) if eligibility and n == 2 else (),
        )
        for n, day in enumerate(days, 1)
    )
    obligations = {}
    cuts = {}
    for n, version in enumerate(versions):
        ob = rpo._Ob(
            oid,
            version.id,
            oid,
            cid,
            "C",
            "O",
            "Service",
            None,
            None,
            None,
            eid,
            "E",
            "EUR",
            "RIGHT_TO_INVOICE" if n == 1 and not eligibility else "POINT_IN_TIME",
            date(2028, 12, 31),
            date(2026, 1, 1),
            Decimal(100),
            False,
        )
        obligations[version.id] = (ob,)
        at = ObligationAt(
            *(Decimal(0) for _ in range(7)),
            Decimal(100),
            "UNSATISFIED",
            None,
            None,
            fixed_allocation=Decimal(100),
            realised_traced=True,
        )
        for day in (*days, *(v.effective for v in versions)):
            cuts[version.id, day] = {oid: at}
    store = rpo.Store({gid: versions}, obligations, {cid: versions}, cuts)
    applied = {eid: frozenset({"POL-198"})}
    (raw,) = rpo.rollforward_lines(store, ranges={eid: (days[0], days[2])}, applied=applied)
    assert raw.lines["EXEMPTIONS"] == 0
    assert raw.exemption_changes == ()
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "USD", "UTC")
    params = ReportParams("rpo_rollforward", 1, {"currency_view": view}, (eid,), datetime.now(UTC))
    session = SimpleNamespace(execute=lambda _: SimpleNamespace(scalar_one=lambda: tenant_id))
    uow = SimpleNamespace(session=session, principal=SimpleNamespace(tenant_id=tenant_id))

    def rates(session, params, *, entities, periods, rate_type="closing", **kwargs):
        period = periods[eid]
        if entities[0].functional_currency == "USD":
            return reporting_currency.Translation(
                "GBP",
                {
                    eid: {
                        "rate": "0.80" if rate_type == "average" else "0.70",
                        "base_currency": "USD",
                    }
                },
            )
        value = {1: "1.10", 2: "1.25", 3: "1.45"}[period.period_no]
        if rate_type == "average":
            value = {2: "1.20", 3: "1.40"}[period.period_no]
        return reporting_currency.Translation("USD", {eid: {"rate": value, "base_currency": "EUR"}})

    monkeypatch.setattr(reporting_currency, "rates_for_period", rates)
    items, _, unexplained, details, gaps = rpo_rollforward_currency.project(
        uow, params, store, (entity,), {eid: periods[1:]}, {eid: periods[0]}, applied
    )
    (shown,) = items
    assert not unexplained
    assert gaps == []
    reporting = view == "reporting"
    assert shown.lines["OPENING"] == (77 if reporting else 110)
    assert shown.lines["CLOSING"] == (Decimal("101.50") if reporting else 145)
    movement = "ELIGIBILITY_CHANGES" if eligibility else "EXEMPTIONS"
    assert shown.lines[movement] == (16 if reporting else 20)
    assert shown.lines["FX"] == (Decimal("8.50") if reporting else 15)
    assert shown.lines["ROUNDING"] == 0
    if eligibility:
        assert shown.lines["EXEMPTIONS"] == 0
        assert details == []
        return
    assert [
        (d["period"], Decimal(d["movement"]), Decimal(d["translated_movement"])) for d in details
    ] == [
        ("FY2026-P02", Decimal(-100), Decimal(-96 if reporting else -120)),
        ("FY2026-P03", Decimal(100), Decimal(112 if reporting else 140)),
    ]
    assert all(
        d["currency"] == "EUR" and d["translated_currency"] == ("GBP" if reporting else "USD")
        for d in details
    )
    assert sum(Decimal(d["translated_movement"]) for d in details) == shown.lines["EXEMPTIONS"]

    # Opposite source gaps must remain reviewable even when translated totals net to zero.
    actual_rollforward = rpo.rollforward_lines

    def with_gaps(*args, **kwargs):
        from dataclasses import replace

        (item,) = actual_rollforward(*args, **kwargs)
        at = kwargs["ranges"][eid][1]
        gap = Decimal(7 if at == days[1] else -6)
        return (replace(item, lines={**item.lines, "UNEXPLAINED": gap}),)

    monkeypatch.setattr(rpo, "rollforward_lines", with_gaps)
    items, _, unexplained, _, gaps = rpo_rollforward_currency.project(
        uow, params, store, (entity,), {eid: periods[1:]}, {eid: periods[0]}, applied
    )
    assert unexplained
    assert items[0].lines["UNEXPLAINED"] == 0
    assert [Decimal(d["movement"]) for d in gaps] == [7, -6]
    amount = Decimal("6.72" if reporting else "8.40")
    assert [Decimal(d["translated_movement"]) for d in gaps] == [amount, -amount]
    assert [d["period"] for d in gaps] == ["FY2026-P02", "FY2026-P03"]


def test_combined_partial_exemptions_keep_translated_rule_amounts_reconciled(monkeypatch):
    from erev_api.domain.reports import rpo_currency, rpo_quotas

    vid, oid, cid, eid, gid = (uuid4() for _ in range(5))
    day = date(2026, 1, 31)
    ob = rpo._Ob(
        oid,
        vid,
        oid,
        cid,
        "C",
        "O",
        "Licence",
        None,
        None,
        None,
        eid,
        "E",
        "EUR",
        "ROYALTY",
        date(2028, 12, 31),
        date(2026, 1, 1),
        Decimal(175),
        False,
    )
    point = ObligationAt(*(Decimal(0) for _ in range(7)), Decimal(175), "UNSATISFIED", None, None)
    version = rpo._Version(vid, gid, 1, True, date(2026, 1, 1), frozenset())
    store = rpo.Store(
        {gid: (version,)},
        {vid: (ob,)},
        {cid: (version,)},
        {(vid, day): {oid: point}},
        quotas={vid: {"C/O": (rpo_quotas.Point(day, Decimal(100), "quota"),)}},
        royalty_remaining={vid: {"C/O": {day: Decimal(50)}}},
    )
    (original,) = rpo.rows_at(
        store, as_of={eid: day}, bands=(12, 24), applied={eid: frozenset({"POL-199", "POL-200"})}
    )
    assert original.partial_exemptions == (("POL-199", Decimal(50)), ("POL-200", Decimal(100)))
    assert original.total == 25
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "USD", "UTC")
    period = tie_outs.PeriodRef(uuid4(), "FY2026-P01", "Jan", 2026, 1, 1, date(2026, 1, 1), day)
    rate = reporting_currency.Translation("USD", {eid: {"rate": "1.111", "base_currency": "EUR"}})
    monkeypatch.setattr(reporting_currency, "rates_for_period", lambda *args, **kwargs: rate)
    session = SimpleNamespace(execute=lambda *args: SimpleNamespace(scalar_one=lambda: uuid4()))
    params = ReportParams(
        report_code="rpo",
        report_version=1,
        parameters={"currency_view": "functional"},
        entity_ids=(eid,),
        known_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    (converted,), _ = rpo_currency.translate(session, params, [original], [entity], {eid: period})
    assert converted.excluded == Decimal("166.65")
    assert sum(amount for _, amount in converted.partial_exemptions) == converted.excluded
    assert converted.total == Decimal("27.78")


@pytest.mark.parametrize("saved", [None, False, True])
def test_zero_opening_needs_no_prior_rate_but_legacy_source_population_is_preserved(
    monkeypatch, saved
):
    from erev_api.domain.reports.builders import SourceBinding, SourceCollector

    eid = uuid4()
    prior = tie_outs.PeriodRef(
        uuid4(), "JAN", "Jan", 2026, 1, 1, date(2026, 1, 1), date(2026, 1, 31)
    )
    current = tie_outs.PeriodRef(
        uuid4(), "FEB", "Feb", 2026, 2, 1, date(2026, 2, 1), date(2026, 2, 28)
    )
    now = datetime.now(UTC)
    flag = "rpo_zero_opening_fx_v1"
    binding = (
        None
        if saved is None
        else SourceBinding(
            now,
            {},
            {},
            frozenset(),
            evidence={flag: True} if saved else {},
        )
    )
    sources = SourceCollector()
    params = ReportParams(
        "rpo_rollforward",
        1,
        {"currency_view": "functional"},
        (eid,),
        now,
        binding=binding,
        sources=sources,
    )
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "GBP", "UTC")
    uow = SimpleNamespace(session=None, principal=SimpleNamespace(tenant_id=uuid4()))
    monkeypatch.setattr(rpo, "rows_at", lambda *a, **k: ())
    monkeypatch.setattr(
        rpo,
        "rollforward_lines",
        lambda *a, **k: (
            rpo.ContractLines(
                "C", None, "E", "USD", dict.fromkeys(rpo.ROLLFORWARD_LINES, Decimal(0))
            ),
        ),
    )
    calls = []

    def rates(*args, periods, **kwargs):
        calls.append(periods[eid].key)
        return reporting_currency.Translation("GBP", {eid: {"rate": "0.8", "base_currency": "USD"}})

    monkeypatch.setattr(reporting_currency, "rates_for_period", rates)
    result, *_ = rpo_rollforward_currency.project(
        uow, params, None, (entity,), {eid: (current,)}, {eid: prior}, {}
    )
    assert ("JAN" in calls) is (saved is False)
    assert result[0].lines["FX"] == 0
    assert result[0].lines["ROUNDING"] == 0
