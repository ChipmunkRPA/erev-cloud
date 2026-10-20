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
