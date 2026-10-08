"""Bind a platform sweep's test workload to the tenants owned by that scenario.

committed_db retains other scenarios' tenants, whose deliberately incomplete shreds
must not affect this scenario's exact retry and alert counts or use its file store.
The original eligibility predicate and all production completion paths remain active.
"""

from collections.abc import Collection
from uuid import UUID

import pytest
from erev_api.db.tables import file_object
from erev_api.domain.platform import shred_completion


def scope_shred_sweep(monkeypatch: pytest.MonkeyPatch, tenants: Collection[UUID]) -> None:
    owed = shred_completion._owed
    owned = tuple(tenants)
    monkeypatch.setattr(
        shred_completion,
        "_owed",
        lambda tenant_id, cutoff: owed(tenant_id, cutoff) & file_object.c.tenant_id.in_(owned),
    )
