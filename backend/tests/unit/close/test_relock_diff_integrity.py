"""Re-lock comparisons must verify both retained and newly frozen source bytes."""

from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from erev_api.domain.close import relock_diff
from erev_api.domain.close.snapshots import DatasetFile

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

CONTENT = b"entity_code,contract_external_id,contract_asset\nUS,C-1,10.00\n"
LOCK = UUID(int=1)
FILE = UUID(int=2)
KIND = "CONTRACT_BALANCES"


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize("fault", [None, "hash", "count", "changed_bytes"])
def test_lock_sides_verify_snapshot_evidence(
    monkeypatch: pytest.MonkeyPatch, side: str, fault: str | None
) -> None:
    digest = hashlib.sha256(CONTENT).hexdigest()
    stored_hash = "0" * 64 if fault == "hash" else digest
    row_count = 2 if fault == "count" else 1
    content = CONTENT.replace(b"10.00", b"90.00") if fault == "changed_bytes" else CONTENT
    stream = io.BytesIO(content)
    opener = MagicMock(return_value=({}, stream))
    monkeypatch.setattr(relock_diff, "open_file", opener)
    mock_uow = MagicMock()
    lock_result, rows_result = MagicMock(), MagicMock()
    lock_result.mappings.return_value.one_or_none.return_value = {
        "snapshot_manifest_sha256": "a" * 64,
        "certification": [],
    }
    rows_result.mappings.return_value.all.return_value = [
        {
            "snapshot_kind": KIND,
            "file_id": FILE,
            "file_sha256": stored_hash,
            "row_count": row_count,
        }
    ]
    mock_uow.session.execute.side_effect = [lock_result, rows_result]
    uow = cast("UnitOfWork", mock_uow)

    def read() -> relock_diff.LockSide:
        if side == "previous":
            return relock_diff.previous_side(uow, LOCK)
        return relock_diff.current_side(
            uow,
            lock_id=LOCK,
            manifest_sha256="a" * 64,
            certification=[],
            datasets=[DatasetFile(KIND, FILE, stored_hash, row_count, {})],
        )

    if fault is None:
        result = read()
        assert result.datasets[KIND].content == CONTENT
        assert result.datasets[KIND].file_sha256 == digest
        assert result.datasets[KIND].row_count == 1
    else:
        with pytest.raises(relock_diff.RelockDiffRefusal) as caught:
            read()
        assert caught.value.kind == KIND
        assert caught.value.code == (
            "RELOCK_DIFF_ROW_COUNT_MISMATCH" if fault == "count" else "RELOCK_DIFF_HASH_MISMATCH"
        )
    opener.assert_called_once_with(uow.session, FILE, files=uow.files, keyring=uow.keyring)
    assert stream.closed
