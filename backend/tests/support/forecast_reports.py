"""Five forecast sections read real computed scenario sources at one cutoff."""

from dataclasses import replace
from typing import Any

from erev_api.db.tables import contract, forecast_event_set
from erev_api.domain.reports import forecast_capture
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.forecast_exports import Identity, render
from erev_api.domain.reports.outputs import RunStamp
from erev_api.enums import TenantKind
from sqlalchemy import func, select


def exercise_capture(world: Any) -> None:
    with world.place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        entities = tuple(uow.session.scalars(select(contract.c.contracting_entity_id).distinct()))
        cutoff = max(uow.now, uow.session.scalar(select(func.clock_timestamp())))
        params = ReportParams(
            report_code="forecast_outputs",
            report_version=1,
            parameters={},
            entity_ids=entities,
            known_at=cutoff,
            book_code="ASC606",
            output_format="JSON",
        )
        result = forecast_capture.capture(
            uow,
            params,
            horizon=("FY2026-P06", "FY2026-P07"),
        )
        assert [s.key for s in result.sections] == [
            "revenue",
            "billing",
            "balances",
            "rpo",
            "journals",
        ]
        assert all(not section.data.tie_out_results for section in result.sections)
        assert result.sections[0].data.rows
        assert result.sections[2].data.rows
        assert result.sections[4].data.rows
        assert all(source.cutoff == cutoff for source in result.sources.values())
        balance_keys = [key for key in result.sources if key.startswith("balances:")]
        assert len(balance_keys) == 2 * len(entities)
        assert all("section" not in row for row in result.sections[3].data.rows)
        publication = (
            uow.session.execute(
                select(forecast_event_set).where(
                    forecast_event_set.c.code == "REPLAY_TXN",
                )
            )
            .mappings()
            .one()
        )
        identity = Identity(
            publication["production_scenario_id"],
            "Scenario capture",
            publication["id"],
            publication["name"],
            publication["version_no"],
            publication["content_sha256"],
        )
        stamp = RunStamp(
            "forecast_outputs",
            "Forecast outputs",
            1,
            "RPT-CAPTURE",
            {},
            result.entity_codes,
            result.book,
            None,
            "Scenario",
            "test",
            "test",
            "Scenario requester",
            cutoff,
            "",
        )
        exported = render(result, identity, stamp, format="JSON")
        assert exported.content == exported.dataset
        assert b'"source_evidence_sha256"' in exported.content
