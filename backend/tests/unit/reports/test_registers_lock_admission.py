"""CLO-8b: the modification and manual-adjustment registers admit the as-locked read like every
other dataset report (ENGINE_SPEC_B S15-R-19; 04 E-64 / T-RPT-02 rev 1.53; F-CLO record
§25.27).

CPU-only: the catalogue rows and the pure lock-scope reconciliation
(``locked.reconcile_selectors``); no database. The as-locked run path itself (frozen dataset,
by-name refusal when the lock holds no snapshot of the kind) is the framework's and is exercised
in ``tests/domain/reports/test_as_locked.py``.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from erev_api.domain.reports import locked
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.enums import SnapshotKind

LOCK: Final = UUID("00000000-0000-4000-8000-000000000c8b")
SCOPE: Final = locked.LockScope(
    lock_id=LOCK,
    entity_id=UUID("00000000-0000-4000-8000-00000000000a"),
    entity_code="AVM-US",
    book_code="ASC606",
    period_id=UUID("00000000-0000-4000-8000-000000000909"),
    period_key="FY2026-P09",
)
REGISTERS: Final = {
    "modification_register": SnapshotKind.MODIFICATION_REGISTER.value,
    "manual_adjustment_register": SnapshotKind.MANUAL_ADJUSTMENT_REGISTER.value,
}


@pytest.mark.parametrize("code", sorted(REGISTERS))
def test_register_row_admits_the_lock_and_names_its_frozen_source(code: str) -> None:
    definition = DEFINITIONS_BY_CODE[code]
    properties = definition.parameters_schema["properties"]
    assert properties["period_lock_id"] == {"type": "string", "format": "uuid"}
    assert "period_lock_id" in definition.ipe_logic["parameters"]
    assert "lock_snapshot" in definition.ipe_logic["source_tables"]
    phrase = f"lock_snapshot kind {REGISTERS[code]}"
    assert any(phrase in entry for entry in definition.ipe_logic["filters"])
    assert locked.snapshot_kind_of(code) == REGISTERS[code]


def test_modification_register_lock_scope_carries_no_date_or_status_filter() -> None:
    """The frozen MODIFICATION_REGISTER dataset is the lock's population (S15-R-20c): the run
    persists the lock's entity and book only — no date window, status or contract filter — and a
    caller's date window is refused by name, never applied to frozen rows."""
    properties = DEFINITIONS_BY_CODE["modification_register"].parameters_schema["properties"]
    kind = REGISTERS["modification_register"]
    parameters, errors = locked.reconcile_selectors({}, SCOPE, properties, kind=kind)
    assert errors == []
    assert parameters == {"period_lock_id": str(LOCK), "entity_codes": ["AVM-US"], "book": "ASC606"}
    given = {"from_date": "2026-09-01"}
    _, refused = locked.reconcile_selectors(given, SCOPE, properties, kind=kind)
    assert [error.field for error in refused] == ["parameters.from_date"]


def test_manual_adjustment_register_lock_scope_derives_the_period_range() -> None:
    properties = DEFINITIONS_BY_CODE["manual_adjustment_register"].parameters_schema["properties"]
    kind = REGISTERS["manual_adjustment_register"]
    parameters, errors = locked.reconcile_selectors({}, SCOPE, properties, kind=kind)
    assert errors == []
    assert parameters == {
        "period_lock_id": str(LOCK),
        "entity_codes": ["AVM-US"],
        "book": "ASC606",
        "from_period_key": "FY2026-P09",
        "to_period_key": "FY2026-P09",
    }
