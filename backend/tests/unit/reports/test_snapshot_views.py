from dataclasses import replace
from uuid import uuid4

import pytest

from erev_api.domain.reports import locked, snapshot_views
from erev_engine.stages.s15_disclosures import snapshots as engine


def encoded(view: str, amount: str) -> engine.Encoded:
    return engine.encode(
        engine.Dataset(
            "CONTRACT_BALANCES",
            tuple(engine.Column(h, "text") for h in ("row_key", "currency", "contract_liability")),
            ({"row_key": "contract:A", "currency": "USD", "contract_liability": amount},)
            if amount
            else (),
        ),
        {"currency_view": view, "total": amount},
    )


def test_bundle_selects_one_authenticated_basis_including_empty_and_legacy() -> None:
    variants = {
        view: encoded(view, amount)
        for view, amount in zip(snapshot_views.VIEWS, ("100.00", "110.00", ""), strict=True)
    }
    packed = snapshot_views.pack(variants)
    dataset = locked.LockedDataset(
        uuid4(),
        packed.kind,
        uuid4(),
        packed.file_sha256,
        packed.row_count,
        packed.control_totals,
        packed.content,
    )
    assert locked.verify(dataset) == dataset
    assert packed.row_count == 5  # two data rows, three authenticated metadata rows
    for view in snapshot_views.VIEWS:
        data = locked.report_data(dataset, view)
        assert data.control_totals == variants[view].control_totals
        assert len(data.rows) == variants[view].row_count
        content, digest = locked.export_csv(dataset, {}, view)
        assert (content, digest) == (variants[view].content, variants[view].file_sha256)
    assert locked.report_data(dataset).rows[0]["contract_liability"] == "100.00"
    legacy = variants["transaction"]
    old = replace(
        dataset,
        content=legacy.content,
        file_sha256=legacy.file_sha256,
        row_count=legacy.row_count,
        control_totals=legacy.control_totals,
    )
    assert locked.report_data(old).rows[0]["contract_liability"] == "100.00"
    with pytest.raises(locked.LockedRefusal, match="no retained dataset"):
        locked.report_data(old, "functional")
    with pytest.raises(locked.LockedRefusal, match="hash"):
        locked.verify(replace(dataset, content=dataset.content.replace(b"110.00", b"120.00")))


def test_missing_currency_metadata_is_refused_even_when_other_basis_requested() -> None:
    packed = snapshot_views.pack({v: encoded(v, "1.00") for v in snapshot_views.VIEWS})
    malformed = b"\n".join(
        line for line in packed.content.split(b"\n") if not line.startswith(b"currency:reporting,")
    )
    with pytest.raises(ValueError, match="missing or incomplete"):
        snapshot_views.select(malformed, "transaction")


def test_relock_reports_alternate_currency_changes_without_mixing_default_amounts() -> None:
    from erev_api.domain.close.relock_diff import DatasetSide, diff_dataset

    def variant(view: str, amount: str) -> engine.Encoded:
        return engine.encode(
            engine.Dataset(
                "CONTRACT_BALANCES",
                tuple(
                    engine.Column(h, "text")
                    for h in (
                        "row_key",
                        "entity_code",
                        "contract_external_id",
                        "currency",
                        "contract_liability",
                    )
                ),
                (
                    {
                        "row_key": "contract:A",
                        "entity_code": "US",
                        "contract_external_id": "A",
                        "currency": "USD",
                        "contract_liability": amount,
                    },
                ),
            )
        )

    old = snapshot_views.pack({v: variant(v, "100.00") for v in snapshot_views.VIEWS})
    new = snapshot_views.pack(
        {v: variant(v, "110.00" if v == "reporting" else "100.00") for v in snapshot_views.VIEWS}
    )
    result = diff_dataset(
        "CONTRACT_BALANCES",
        DatasetSide(old.kind, old.file_sha256, old.row_count, old.content),
        DatasetSide(new.kind, new.file_sha256, new.row_count, new.content),
    )
    assert result["totals"]["measure_changes"] == 0
    assert result["currency_views"]["functional"]["comparison"]["changed"] is False
    changed = result["currency_views"]["reporting"]["comparison"]["changed_rows"]
    assert changed[0]["columns"]["contract_liability"]["delta"] == "10.00"


def test_aging_relock_distinguishes_bucket_migration_from_total_change() -> None:
    from erev_api.domain.close.relock_diff import DatasetSide, diff_dataset
    from erev_api.domain.reports import snapshots
    from erev_api.domain.reports.builders.balance_aging import COLUMNS
    from erev_api.domain.reports.outputs import ReportData

    def variant(older: bool) -> engine.Encoded:
        row = {
            "row_key": "contract:A:CONTRACT_LIABILITY",
            "entity_code": "US",
            "contract_external_id": "A",
            "customer_name": "Customer A",
            "balance_role": "Contract liability",
            "currency": "USD",
            **{
                column.key: {"amount": "0.00", "currency": "USD"}
                for column in COLUMNS
                if column.kind == "money"
            },
        }
        row["total"] = {"amount": "100.00", "currency": "USD"}
        row["bucket_31_90" if older else "bucket_0_30"] = row["total"]
        return snapshots.encode_report(
            "BALANCE_AGING",
            ReportData(columns=COLUMNS, rows=(row,), control_totals={}),
            drop_presentation_totals=True,
        )

    old, new = variant(False), variant(True)
    result = diff_dataset(
        "BALANCE_AGING",
        DatasetSide(old.kind, old.file_sha256, old.row_count, old.content),
        DatasetSide(new.kind, new.file_sha256, new.row_count, new.content),
    )
    changed = result["changed_rows"][0]["columns"]
    assert changed["bucket_0_30"]["delta"] == "-100.00"
    assert changed["bucket_31_90"]["delta"] == "100.00"
    assert "total" not in changed


def test_cost_snapshot_retains_all_currency_and_asset_variants():
    variants = {}
    for index, key in enumerate(snapshot_views.COST_VIEWS):
        asset = key.startswith("asset:")
        headers = ["row_key", "currency", "cost_kind", "line_code", "amount"]
        if asset:
            headers += ["asset_key", "contract_external_id"]
        row = {
            "row_key": "original",
            "currency": "USD",
            "cost_kind": "OBTAIN",
            "line_code": "CLOSING",
            "amount": str(index),
        }
        if asset:
            row.update(asset_key="C/EV-1", contract_external_id="C")
        variants[key] = engine.encode(
            engine.Dataset(
                "COST_ROLLFORWARD", tuple(engine.Column(h, "text") for h in headers), (row,)
            ),
            {"currency_view": key.split(":")[-1], "closing": str(index)},
        )
    packed = snapshot_views.pack(variants)
    dataset = locked.LockedDataset(
        uuid4(),
        packed.kind,
        uuid4(),
        packed.file_sha256,
        packed.row_count,
        packed.control_totals,
        packed.content,
    )
    locked.verify(dataset)
    for key, original in variants.items():
        view = key.split(":")[-1]
        granularity = "asset" if key.startswith("asset:") else "category"
        data = locked.report_data(dataset, view, granularity)
        assert data.control_totals["granularity"] == granularity
        assert data.control_totals["closing"] == original.control_totals["closing"]
        assert ("asset_key" in data.rows[0]) == (granularity == "asset")
        assert locked.export_csv(dataset, {}, view, granularity) == (
            original.content,
            original.file_sha256,
        )
    incomplete = b"\n".join(
        line
        for line in packed.content.split(b"\n")
        if not line.startswith(b"currency:asset:reporting,")
    )
    with pytest.raises(ValueError, match="missing or incomplete"):
        snapshot_views.select(incomplete, "transaction")
    legacy = variants["transaction"]
    with pytest.raises(locked.LockedRefusal):
        locked.report_data(replace(dataset, content=legacy.content), "transaction", "asset")


def test_cost_relock_detects_asset_transfer_with_unchanged_category() -> None:
    from erev_api.domain.close.relock_diff import DatasetSide, diff_dataset

    def bundle(changed: bool) -> engine.Encoded:
        variants = {}
        for view in snapshot_views.COST_VIEWS:
            asset = view.startswith("asset:")
            amounts = ("4.00", "6.00") if changed else ("5.00", "5.00")
            rows = tuple(
                {
                    "row_key": str(index),
                    "entity_code": "US",
                    "cost_kind": "OBTAIN",
                    "line_code": "CLOSING",
                    "amount": amount,
                    **({"asset_key": f"A{index}"} if asset else {}),
                }
                for index, amount in enumerate(amounts if asset else ("10.00",))
            )
            variants[view] = engine.encode(
                engine.Dataset(
                    "COST_ROLLFORWARD", tuple(engine.Column(h, "text") for h in rows[0]), rows
                ),
                {"currency_view": view.split(":")[-1]},
            )
        return snapshot_views.pack(variants)

    old, new = bundle(False), bundle(True)
    result = diff_dataset(
        "COST_ROLLFORWARD",
        *(DatasetSide(x.kind, x.file_sha256, x.row_count, x.content) for x in (old, new)),
    )
    assert result["totals"]["measure_changes"] == 0
    for view in snapshot_views.VIEWS:
        comparison = result["asset_views"][view]["comparison"]
        assert comparison["totals"]["measure_changes"] == 2
        assert "asset_key" in comparison["key_columns"]
