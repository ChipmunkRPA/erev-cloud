"""Historical report figures exclude subsequent insertions while record figures include them."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from erev_api.db import new_id
from erev_api.domain.journals import subledger
from erev_api.domain.reports.builders import ReportParams, disaggregation
from erev_api.enums import SubledgerPostingKind
from sqlalchemy import func, select
from support.factories import K11World
from tests.domain.reports.test_historical_line_cutoff_db import _lines_of, _posted
from tests.domain.reports.test_historical_line_cutoff_db import app as app
from tests.domain.reports.test_historical_line_cutoff_db import world as world


def test_historical_disaggregation_retains_original_revenue(world: K11World) -> None:
    first, stored = _posted(world)
    stamp = world.place.scalar(select(func.clock_timestamp()))
    assert isinstance(stamp, datetime)
    params = ReportParams(
        report_code=disaggregation.CODE,
        report_version=1,
        parameters={"from_period_key": "FY2026-P01", "to_period_key": "FY2026-P09"},
        entity_ids=(world.entity_id,),
        known_at=stamp,
        book_code="ASC606",
        historical=True,
    )
    with world.place.uow() as uow:
        baseline = disaggregation.build(uow, params)
    totals = baseline.control_totals["revenue_total"]
    assert totals and all(Decimal(value) > 0 for value in totals.values())
    with world.place.uow() as uow:
        subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:report-after-cutoff",
            description="Later insertion with the same business clock and effective period",
            lines=[{**line, "id": new_id()} for line in _lines_of(world, first)],
            contract_computation_id=stored["id"],
        )
        uow.commit()
    with world.place.uow() as uow:
        historical = disaggregation.build(uow, params)
        record = disaggregation.build(uow, replace(params, historical=False))
    assert historical.rows == baseline.rows
    assert historical.control_totals == baseline.control_totals
    assert record.control_totals["revenue_total"] == {
        currency: f"{Decimal(value) * 2:.2f}" for currency, value in totals.items()
    }
    with world.place.uow() as uow:
        empty_scope = disaggregation.build(uow, replace(params, entity_ids=()))
    assert empty_scope.control_totals["revenue_total"] == {}


def test_historical_read_excludes_an_insert_committed_after_cutoff(
    world: K11World, request: pytest.FixtureRequest
) -> None:
    first, stored = _posted(world)
    copied = [{**line, "id": new_id()} for line in _lines_of(world, first)]
    with world.place.uow() as uow:
        later = subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:commit-after-cutoff",
            description="Inserted before the cutoff but committed afterward",
            lines=copied,
            contract_computation_id=stored["id"],
        )
        # Another transaction establishes the cutoff while this posting is still uncommitted.
        stamp = world.place.scalar(select(func.clock_timestamp()))
        assert isinstance(stamp, datetime)
        assert _lines_of(world, later.posting_id) == []
        uow.commit()
    with world.place.uow() as uow:
        visible = (
            uow.session.execute(
                subledger.line_statement(
                    uow.session, subledger.LineFilters(book="ASC606", known_at=stamp)
                )
            )
            .mappings()
            .all()
        )
    assert first in {line["subledger_posting_id"] for line in visible}
    # Only the missing commit-visibility assertion is expected to fail, never setup/preconditions.
    request.applymarker(
        pytest.mark.xfail(
            strict=True,
            reason="Insertion timestamp does not retain historical PostgreSQL commit visibility",
        )
    )
    assert later.posting_id not in {line["subledger_posting_id"] for line in visible}
