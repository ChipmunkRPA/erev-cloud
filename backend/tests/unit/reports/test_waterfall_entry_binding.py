"""Entry dates are retained per contract and applied in the performing entity's calendar."""

from dataclasses import replace
from datetime import date
from typing import cast
from uuid import uuid4

import pytest
from erev_api.domain.reports.builders.revenue_waterfall import ENTRY_EVIDENCE, _entered_rows
from erev_api.problems import Problem
from sqlalchemy.orm import Session
from tests.unit.reports.test_source_binding_members import BOUND, US01, K, _params


class NoReads:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("A retained entry must not read live events or versions")


def test_entry_cutoff_uses_each_performing_calendar_and_preserves_legacy_population() -> None:
    contract, other = uuid4(), uuid4()
    rows = [
        {"contract_id": contract, "performing_entity_id": US01},
        {"contract_id": contract, "performing_entity_id": other},
    ]
    ends = {US01: date(2026, 3, 31), other: date(2026, 4, 1)}
    bound = replace(
        BOUND,
        evidence={
            ENTRY_EVIDENCE: {
                str(contract): {"entry_date": "2026-04-01", "contract_version_id": str(uuid4())}
            }
        },
    )
    session = cast(Session, NoReads())
    assert _entered_rows(session, _params(binding=bound), rows, "ASC606", K, ends) == rows[1:]
    assert _entered_rows(session, _params(binding=BOUND), rows, "ASC606", K, ends) == rows
    with pytest.raises(Problem):
        _entered_rows(
            session,
            _params(binding=replace(bound, evidence={ENTRY_EVIDENCE: {}})),
            rows,
            "ASC606",
            K,
            ends,
        )
