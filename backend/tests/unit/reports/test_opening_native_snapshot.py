import hashlib
import json
from datetime import date
from io import BytesIO
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_native_snapshot as reader
from erev_api.problems import Problem


def setup(monkeypatch, snapshot=None):
    row = NS(version_id=UUID(int=1), entity_code="US", currency="USD")
    period = NS(key="P01", end=date(2026, 1, 31))
    book = {"book_code": "ASC606", "contract_version": {"subject_key": "GROUP"}}
    if snapshot is not None:
        book["disclosure_rollforwards"] = snapshot
    content = json.dumps({"input_sha256": "input", "books": [book]}).encode()
    digest = hashlib.sha256(content).hexdigest()
    version = {"contract_computation_id": UUID(int=2), "output_sha256": digest}
    evidence = {
        "output_file_id": UUID(int=3),
        "input_sha256": "input",
        "output_sha256": digest,
        "output_file_sha256": digest,
    }
    pending = iter([version, evidence])
    session = NS(
        execute=lambda statement: NS(mappings=lambda: NS(one_or_none=lambda: next(pending)))
    )
    monkeypatch.setattr(reader, "open_file", lambda *a, **k: ({"sha256": digest}, BytesIO(content)))
    return NS(session=session, files=None, keyring=None), row, period, evidence, digest


def snapshot():
    return {
        "entity": "US",
        "period_key": "P01",
        "closing_date": "2026-01-31",
        "view": "TRANSACTION",
        "currency": "USD",
        "minor_unit": 2,
        "unit": "GROUP@US",
        "opening_basis": "RESTATED",
    }


def test_verified_original_snapshot_and_legacy_absence(monkeypatch):
    uow, row, period, evidence, digest = setup(monkeypatch, [snapshot()])
    result = reader.read(uow, row, period, "ASC606")
    assert result["version"] == str(row.version_id)
    assert result["output_sha256"] == digest
    uow, row, period, _, _ = setup(monkeypatch)
    assert reader.read(uow, row, period, "ASC606") is None


def test_snapshot_refuses_mismatched_hash_and_duplicate_view(monkeypatch):
    uow, row, period, evidence, _ = setup(monkeypatch, [snapshot()])
    evidence["output_file_sha256"] = "bad"
    with pytest.raises(Problem):
        reader.read(uow, row, period, "ASC606")
    uow, row, period, _, _ = setup(monkeypatch, [snapshot(), snapshot()])
    with pytest.raises(Problem):
        reader.read(uow, row, period, "ASC606")


def test_old_report_bindings_do_not_gain_native_evidence():
    from erev_api.domain.reports.builders import SourceCollector
    from erev_api.domain.reports.opening_relief_frozen import NATIVE_KEY, Reader

    collector = SourceCollector()
    old = Reader(NS(), NS(binding=NS(evidence={}), sources=collector))
    assert old.native is False and collector.evidence == {}
    live = Reader(NS(), NS(binding=None, sources=collector))
    assert live.native is True and collector.evidence[NATIVE_KEY] is True


@pytest.mark.parametrize("amount", ["0", "1"])
def test_frozen_source_accepts_only_proven_zero_rows_omitted_by_lock(amount):
    from decimal import Decimal

    from erev_api.domain.reports.opening_relief_frozen import FrozenSources, Reader

    row = NS(contract_id=UUID(int=1), entity_id=UUID(int=2), external_id="SETTLED")
    original = NS(version_id=UUID(int=3), value=lambda name: Decimal(amount))
    locked = NS(lock_id=UUID(int=4), rows={})
    reader = Reader(NS())
    reader.cache[(locked.lock_id, row.entity_id, "ASC606")] = FrozenSources(
        {row.contract_id: original}, {"source": "authenticated"}
    )
    if amount == "0":
        found, facts = reader.read(row=row, previous=NS(), locked=locked, book="ASC606")
        assert found is original
        assert facts["version"] == str(original.version_id)
    else:
        with pytest.raises(Problem, match="validation-failed"):
            reader.read(row=row, previous=NS(), locked=locked, book="ASC606")
