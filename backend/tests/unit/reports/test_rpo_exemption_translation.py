"""Monthly exemption translation explains a movement hidden by net-zero endpoints."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from erev_api.domain.contracts.to_date import ObligationAt
from erev_api.domain.reports import reporting_currency, rpo_rollforward_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, rpo


@pytest.mark.parametrize("view", ["functional", "reporting"])
def test_exemption_round_trip_keeps_both_months_and_their_original_rates(monkeypatch, view) -> None:
    eid, cid, oid, gid, tenant_id = (uuid4() for _ in range(5))
    days = (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31))
    periods = tuple(
        tie_outs.PeriodRef(uuid4(), f"FY2026-P{n:02d}", str(n), 2026, n, 1, day.replace(day=1), day)
        for n, day in enumerate(days, 1)
    )
    versions = tuple(
        rpo._Version(uuid4(), gid, n, True, day.replace(day=1), frozenset({"CONTRACT_AMENDED"}))
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
            "RIGHT_TO_INVOICE" if n == 1 else "POINT_IN_TIME",
            date(2028, 12, 31),
            date(2026, 1, 1),
            Decimal(100),
            False,
        )
        obligations[version.id] = (ob,)
        at = ObligationAt(*(Decimal(0) for _ in range(7)), Decimal(100), "UNSATISFIED", None, None)
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
    assert shown.lines["EXEMPTIONS"] == (16 if reporting else 20)
    assert shown.lines["FX"] == (Decimal("8.50") if reporting else 15)
    assert shown.lines["ROUNDING"] == 0
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
