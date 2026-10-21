"""Transaction-view reconciliation must not net away opposite monthly source gaps."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from erev_api.domain.contracts.to_date import ObligationAt
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, SourceBinding, SourceCollector, rpo
from erev_api.domain.reports.builders import rpo_rollforward as report


def test_transaction_report_retains_offsetting_monthly_gaps_and_legacy_binding(monkeypatch):
    eid, cid, oid, gid = (uuid4() for _ in range(4))
    days = (date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31))
    periods = tuple(
        tie_outs.PeriodRef(uuid4(), f"FY2026-P{n:02d}", str(n), 2026, n, 1, day.replace(day=1), day)
        for n, day in enumerate(days, 1)
    )
    versions = tuple(
        rpo._Version(uuid4(), gid, n, True, day.replace(day=1), frozenset({"MEMO_ADDED"}))
        for n, day in enumerate(days, 1)
    )
    obligations, cuts = {}, {}
    for version, amount in zip(versions, (100, 110, 100), strict=True):
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
            "POINT_IN_TIME",
            date(2028, 12, 31),
            date(2026, 1, 1),
            Decimal(amount),
            False,
        )
        obligations[version.id] = (ob,)
        point = ObligationAt(
            *(Decimal(0) for _ in range(7)), Decimal(amount), "UNSATISFIED", None, None
        )
        for day in (*days, *(v.effective for v in versions)):
            cuts[version.id, day] = {oid: point}
    store = rpo.Store({gid: versions}, obligations, {cid: versions}, cuts)
    entity = tie_outs.EntityRef(eid, "E", uuid4(), "USD", "UTC")
    now = datetime.now(UTC)
    sources = SourceCollector()
    params = ReportParams(
        "rpo_rollforward", 1, {"currency_view": "transaction"}, (eid,), now, sources=sources
    )
    measured = []
    monkeypatch.setattr(tie_outs, "book_of", lambda *a, **kw: "ASC606")
    monkeypatch.setattr(tie_outs, "cutoff_for", lambda *a, **kw: now)
    monkeypatch.setattr(
        report.balances,
        "ranges",
        lambda *a, **kw: ((entity,), {eid: periods[1:]}, {eid: periods[0]}),
    )
    monkeypatch.setattr(rpo, "load", lambda *a, **kw: store)
    monkeypatch.setattr(rpo, "applied_expedients", lambda *a, **kw: {})
    monkeypatch.setattr(rpo, "measure", lambda session, store, dates, **kw: measured.append(dates))
    result = report.build(SimpleNamespace(session=object()), params)
    assert result.control_totals["source_unexplained"] is True
    assert result.tie_out_results[0]["result"] == tie_outs.FAIL
    assert result.tie_out_results[1]["result"] == tie_outs.PASS
    gaps = result.control_totals["unexplained_details"]
    assert [(g["period"], Decimal(g["movement"])) for g in gaps] == [
        ("FY2026-P02", Decimal(10)),
        ("FY2026-P03", Decimal(-10)),
    ]
    assert all(g["currency"] == g["translated_currency"] == "EUR" for g in gaps)
    assert all(g["movement"] == g["translated_movement"] for g in gaps)
    assert days[1] in measured[-1][eid]
    assert sources.evidence["rpo_eligibility_changes_v1"] is True
    assert "eligibility_changes" in {column.key for column in result.columns}
    assert any(row.get("line_code") == "ELIGIBILITY_CHANGES" for row in result.rows)
    assert sources.evidence["rpo_transaction_monthly_gaps_v1"] is True
    binding = SourceBinding(now, {}, {}, frozenset(), evidence=sources.evidence)
    rerun = report.build(
        SimpleNamespace(session=object()), replace(params, binding=binding, sources=None)
    )
    assert rerun == result
    legacy = report.build(
        SimpleNamespace(session=object()),
        replace(params, binding=replace(binding, evidence={}), sources=None),
    )
    assert "eligibility_changes" not in {column.key for column in legacy.columns}
    assert not any(row.get("line_code") == "ELIGIBILITY_CHANGES" for row in legacy.rows)
    assert legacy.tie_out_results[0]["result"] == tie_outs.PASS
    assert "unexplained_details" not in legacy.control_totals
    assert measured[-1][eid] == (days[0], days[2])

    supported_versions = tuple(replace(v, causes=frozenset({"CONTRACT_AMENDED"})) for v in versions)
    supported = replace(store, versions={gid: supported_versions}, chains={cid: supported_versions})
    monkeypatch.setattr(rpo, "load", lambda *a, **kw: supported)
    reconciled = report.build(SimpleNamespace(session=object()), params)
    assert reconciled.tie_out_results[0]["result"] == tie_outs.PASS
    assert reconciled.control_totals["source_unexplained"] is False
    assert reconciled.control_totals["unexplained_details"] == []

    exempt_obligations = {
        key: tuple(replace(ob, recognition_method="RIGHT_TO_INVOICE") for ob in obs)
        if key == versions[1].id
        else obs
        for key, obs in supported.obligations.items()
    }
    exemption_store = replace(supported, obligations=exempt_obligations)
    monkeypatch.setattr(rpo, "load", lambda *a, **kw: exemption_store)
    monkeypatch.setattr(rpo, "applied_expedients", lambda *a, **kw: {eid: frozenset({"POL-198"})})
    exempted = report.build(SimpleNamespace(session=object()), params)
    assert exempted.control_totals["exemption_changes"] == []
    monthly = exempted.control_totals["exemption_translation"]
    assert [(d["period"], Decimal(d["movement"])) for d in monthly] == [
        ("FY2026-P02", Decimal(-110)),
        ("FY2026-P03", Decimal(110)),
    ]
    assert all(d["currency"] == d["translated_currency"] == "EUR" for d in monthly)
    assert all(d["movement"] == d["translated_movement"] for d in monthly)
    assert exempted.tie_out_results[0]["result"] == tie_outs.PASS
    exemption_binding = SourceBinding(now, {}, {}, frozenset(), evidence=sources.evidence)
    assert (
        report.build(
            SimpleNamespace(session=object()),
            replace(params, binding=exemption_binding, sources=None),
        )
        == exempted
    )
    old_exemptions = report.build(
        SimpleNamespace(session=object()),
        replace(params, binding=replace(exemption_binding, evidence={}), sources=None),
    )
    assert "exemption_translation" not in old_exemptions.control_totals
