from dataclasses import replace
from datetime import date
from fractions import Fraction
from uuid import uuid4

import pytest
from erev_api.domain.reports import locked, snapshot_views, variance_reporting
from erev_api.domain.reports.evidence_close import FrozenClose, FrozenReport
from erev_api.problems import Problem
from erev_engine.stages.s15_disclosures import snapshots as engine


def source(*, missing_balance_rate: bool = False, conflict: bool = False) -> FrozenClose:
    scope = locked.LockScope(uuid4(), uuid4(), "US", "ASC606", uuid4(), "P1")
    common = {
        "base_currency": "USD",
        "quote_currency": "EUR",
        "period_key": "P1",
        "period_end": "2026-01-31",
        "rate_cutoff": "2026-02-01T00:00:00+00:00",
    }
    closing = {
        **common,
        "rate_type": "closing",
        "rate": "0.9",
        "rate_id": str(uuid4()),
        "version_id": str(uuid4()),
    }
    average = {
        **common,
        "rate_type": "average",
        "rate": "0.8",
        "rate_id": str(uuid4()),
        "version_id": str(uuid4()),
    }
    reports = []
    for kind in ("WATERFALL", "CONTRACT_BALANCES", "RPO"):
        rates = [average, closing] if kind == "WATERFALL" else [closing]
        if missing_balance_rate and kind == "CONTRACT_BALANCES":
            rates = []
        if conflict and kind == "RPO":
            rates = [{**closing, "rate": "0.7"}]
        data = engine.Dataset(kind, (engine.Column("row_key", "text"),), ())
        variants = {
            view: engine.encode(data, {"reporting_currency": "EUR", "translation_rates": rates})
            for view in snapshot_views.VIEWS
        }
        packed = snapshot_views.pack(variants)
        dataset = locked.LockedDataset(
            scope.lock_id,
            kind,
            uuid4(),
            packed.file_sha256,
            packed.row_count,
            packed.control_totals,
            packed.content,
        )
        reports.append(FrozenReport(kind, uuid4(), None, dataset))
    return FrozenClose(scope, {}, tuple(reports))


def test_reporting_basis_binds_verified_snapshot_rates() -> None:
    frozen = source()
    basis = variance_reporting.from_close(
        frozen, functional_currency="USD", period_end=date(2026, 1, 31)
    )
    assert basis.amount(Fraction("10.01"), revenue=True) == Fraction("8.01")
    assert basis.amount(Fraction("10.01")) == Fraction("9.01")
    assert (
        basis.evidence_sha256
        == variance_reporting.from_close(
            frozen, functional_currency="USD", period_end=date(2026, 1, 31)
        ).evidence_sha256
    )
    report = frozen.reports[0]
    bad = replace(
        report,
        dataset=replace(report.dataset, content=report.dataset.content.replace(b"0.8", b"0.7")),
    )
    with pytest.raises(locked.LockedRefusal, match="hash"):
        variance_reporting.from_close(
            replace(frozen, reports=(bad, *frozen.reports[1:])),
            functional_currency="USD",
            period_end=date(2026, 1, 31),
        )


@pytest.mark.parametrize(
    "options,message",
    [({"missing_balance_rate": True}, "own retained closing"), ({"conflict": True}, "disagree")],
)
def test_rates_cannot_be_borrowed_from_another_dataset_or_silently_overridden(
    options: dict[str, bool], message: str
) -> None:
    with pytest.raises(Problem, match=message):
        variance_reporting.from_close(
            source(**options), functional_currency="USD", period_end=date(2026, 1, 31)
        )
