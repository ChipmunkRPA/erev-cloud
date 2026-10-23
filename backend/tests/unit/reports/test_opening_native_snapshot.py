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
