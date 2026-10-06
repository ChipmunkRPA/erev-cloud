"""MAIN DEFECT 4 (SOP-7 batch #8, WALK-DB-1): a naive ``effective_from`` on an account-mapping
version used to pass the schema (``datetime | None``) and reach the audit canonicaliser, which
requires an aware datetime (erev_engine/canonical.py) — HTTP 500 on a schema-valid input. The 04
SC-V column is ``timestamptz``; the schemas now take ``AwareDatetime | None`` and refuse a naive
value with 422, like ``PobTemplateVersionIn`` and ``MappingProfileIn``. CPU witness: request
validation only."""

from __future__ import annotations

import pytest
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingUpdateIn
from pydantic import ValidationError

NAIVE = ("2026-01-01", "2026-01-01T00:00:00")
AWARE = ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00", "2026-01-01T04:00:00-04:00")


@pytest.mark.parametrize("value", NAIVE)
def test_create_refuses_a_naive_effective_from(value: str) -> None:
    with pytest.raises(ValidationError) as refused:
        AccountMappingIn.model_validate({"name": "AVM-MAP-2026-01", "effective_from": value})
    assert refused.value.errors()[0]["loc"] == ("effective_from",)


@pytest.mark.parametrize("value", NAIVE)
def test_update_refuses_a_naive_effective_from(value: str) -> None:
    with pytest.raises(ValidationError) as refused:
        AccountMappingUpdateIn.model_validate({"effective_from": value})
    assert refused.value.errors()[0]["loc"] == ("effective_from",)


@pytest.mark.parametrize("value", AWARE)
def test_aware_effective_from_is_accepted(value: str) -> None:
    created = AccountMappingIn.model_validate({"name": "AVM-MAP-2026-01", "effective_from": value})
    updated = AccountMappingUpdateIn.model_validate({"effective_from": value})
    assert created.effective_from is not None and created.effective_from.tzinfo is not None
    assert updated.effective_from is not None and updated.effective_from.utcoffset() is not None


def test_absent_effective_from_stays_optional() -> None:
    assert AccountMappingIn.model_validate({"name": "AVM-MAP-2026-01"}).effective_from is None
    assert AccountMappingUpdateIn.model_validate({}).effective_from is None
