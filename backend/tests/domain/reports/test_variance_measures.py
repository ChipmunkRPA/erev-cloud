"""Frozen monetary endpoint arithmetic, independent of the pending driver replay."""

import csv
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext
from io import StringIO
from uuid import uuid4

import pytest
from erev_api.domain.reports import locked, variance_measures
from erev_api.domain.reports.evidence_close import FrozenClose, FrozenReport
from erev_api.problems import Problem


def _source(*, later: bool = False) -> FrozenClose:
    scope = locked.LockScope(uuid4(), uuid4(), "AVM-US", "ASC606", uuid4(), "FY2026-P09")
    revenue, asset, rpo = (
        ("229852.94", "129852.94", "520147.06") if later else ("197294.12", "97294.12", "552705.88")
    )
    common = ["row_key", "entity_code", "contract_external_id", "currency"]
    datasets = {
        "WATERFALL": (
            common + ["obligation_key", "period_key", "recognised"],
            [["wf:1", "AVM-US", "PRJ-CB-2026-01", "USD", "O1", "FY2026-P09", revenue]],
        ),
        "CONTRACT_BALANCES": (
            common + ["contract_liability", "contract_asset", "unbilled_receivable"],
            [["bal:1", "AVM-US", "PRJ-CB-2026-01", "USD", "0.00", asset, "0.00"]],
        ),
        "RPO": (
            common + ["obligation_key", "section", "total"],
            [
                ["rpo:1", "AVM-US", "PRJ-CB-2026-01", "USD", "O1", "1", rpo],
                ["rpo:2", "AVM-US", "EXEMPT", "USD", "O2", "2", ""],
            ],
        ),
    }
    reports = []
    for kind, (headers, rows) in datasets.items():
        stream = StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)
        content = stream.getvalue().encode()
        dataset = locked.LockedDataset(
            scope.lock_id,
            kind,
            uuid4(),
            hashlib.sha256(content).hexdigest(),
            len(rows),
            {},
            content,
        )
        reports.append(FrozenReport(kind, uuid4(), None, dataset))
    return FrozenClose(
        scope,
        {"created_at": datetime(2026, 10, 1, tzinfo=UTC), "snapshot_manifest_sha256": "a" * 64},
        tuple(reports),
    )


def _pair() -> tuple[FrozenClose, FrozenClose]:
    first, second = _source(), _source(later=True)
    second = replace(
        second,
        scope=replace(first.scope, lock_id=second.scope.lock_id),
        record={**second.record, "created_at": first.record["created_at"] + timedelta(days=1)},
    )
    return first, second


def test_frozen_changes_are_exact_and_keep_source_identities() -> None:
    before, after = _pair()
    # Arithmetic must not depend on the application's Decimal context.
    with localcontext() as context:
        context.prec = 3
        result = variance_measures.compare(before, after)
    by_measure = {row["measure"]: row for row in result["rows"]}
    assert {key: row["change"] for key, row in by_measure.items()} == {
        "REVENUE": "32558.82",
        "CONTRACT_ASSET_AND_UNBILLED": "32558.82",
        "RPO": "-32558.82",
    }
    assert by_measure["REVENUE"]["earlier_value"] == "197294.12"
    assert by_measure["REVENUE"]["later_value"] == "229852.94"
    assert by_measure["REVENUE"]["earlier_source_rows"] == ["wf:1"]
    assert result["sources"][0]["period_lock_id"] == str(before.scope.lock_id)
    assert result["driver_attribution"] == "not_computed"
    assert all(row["contract_external_id"] != "EXEMPT" for row in result["rows"])


def _rewrite(source: FrozenClose, kind: str, old: bytes, new: bytes) -> FrozenClose:
    reports = []
    for report in source.reports:
        if report.dataset.kind == kind:
            content = report.dataset.content.replace(old, new)
            report = replace(
                report,
                dataset=replace(
                    report.dataset, content=content, file_sha256=hashlib.sha256(content).hexdigest()
                ),
            )
        reports.append(report)
    return replace(source, reports=tuple(reports))


def test_currency_changes_are_separate_removal_and_addition() -> None:
    before, after = _pair()
    after = _rewrite(after, "WATERFALL", b"USD", b"EUR")
    rows = [
        r for r in variance_measures.compare(before, after)["rows"] if r["measure"] == "REVENUE"
    ]
    assert [(r["currency"], r["change"]) for r in rows] == [
        ("EUR", "229852.94"),
        ("USD", "-197294.12"),
    ]


def test_identical_figures_have_no_changes() -> None:
    before, after = _pair()
    after = replace(
        after,
        reports=tuple(
            replace(report, dataset=replace(report.dataset, lock_id=after.scope.lock_id))
            for report in before.reports
        ),
    )
    result = variance_measures.compare(before, after)
    assert result["rows"] == result["totals"] == []


@pytest.mark.parametrize("fault", ["scope", "order", "kind", "missing", "hash", "blank", "period"])
def test_bad_sources_refuse(fault: str) -> None:
    before, after = _pair()
    if fault == "scope":
        after = replace(after, scope=replace(after.scope, entity_id=uuid4()))
    elif fault == "order":
        after = replace(after, record=before.record)
    elif fault == "kind":
        after = replace(after, scope=replace(after.scope, kind="PERMANENT_LOCK"))
    elif fault == "missing":
        after = replace(after, reports=after.reports[1:])
    elif fault == "hash":
        report = after.reports[0]
        after = replace(
            after,
            reports=(
                replace(report, dataset=replace(report.dataset, content=b"bad")),
                *after.reports[1:],
            ),
        )
    elif fault == "blank":
        after = _rewrite(after, "WATERFALL", b"229852.94", b"")
    else:
        after = _rewrite(after, "WATERFALL", b"FY2026-P09", b"FY2026-P10")
    with pytest.raises(Problem):
        variance_measures.compare(before, after)
