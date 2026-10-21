"""Historical report figures exclude subsequent insertions while record figures include them."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from erev_api.db import new_id
from erev_api.domain.journals import commit_evidence, subledger
from erev_api.domain.reports.builders import (
    ReportParams,
    SourceCollector,
    bbr_sources,
    disaggregation,
    extract_subledger_lines,
)
from erev_api.domain.reports.catalogue import (
    COMMIT_VISIBILITY_REPORTS,
    DEFINITIONS_BY_CODE,
    RETAINED_COMMIT_REPORTS,
)
from erev_api.enums import SubledgerPostingKind
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
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


def test_historical_read_excludes_an_insert_committed_after_cutoff(world: K11World) -> None:
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
    assert later.posting_id not in {line["subledger_posting_id"] for line in visible}
    with world.place.uow() as uow:
        committed = uow.session.execute(
            text(
                "SELECT committed_server_at FROM erev.subledger_posting_commit "
                "WHERE subledger_posting_id = :posting"
            ),
            {"posting": later.posting_id},
        ).scalar_one()
        assert committed > stamp
        assert (
            uow.session.scalar(
                text("SELECT erev.subledger_commit_time(:posting)"),
                {"posting": later.posting_id},
            )
            == committed
        )
    with pytest.raises(DBAPIError, match="EREV-IMM-001"):
        with world.place.uow() as uow:
            uow.session.execute(
                text(
                    "UPDATE erev.subledger_posting_commit "
                    "SET committed_server_at = :stamp WHERE subledger_posting_id = :posting"
                ),
                {"stamp": stamp, "posting": later.posting_id},
            )


def test_unarchived_commit_is_readable_and_only_database_time_can_be_retained(
    world: K11World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commit_evidence, "retain_after_commit", lambda *args: None)
    posting, _ = _posted(world)
    with world.place.uow() as uow:
        stamp = uow.session.scalar(
            text("SELECT erev.subledger_commit_time(:posting)"), {"posting": posting}
        )
        assert isinstance(stamp, datetime)
        assert (
            uow.session.scalar(
                text(
                    "SELECT committed_server_at FROM erev.subledger_posting_commit "
                    "WHERE subledger_posting_id = :posting"
                ),
                {"posting": posting},
            )
            is None
        )
    assert world.place.scalar(select(func.erev.subledger_commit_time(posting))) == stamp
    with pytest.raises(DBAPIError, match="EREV-HIS-001"):
        with world.place.uow() as uow:
            uow.session.execute(
                text(
                    "UPDATE erev.subledger_posting_commit "
                    "SET committed_server_at = clock_timestamp() "
                    "WHERE subledger_posting_id = :posting"
                ),
                {"posting": posting},
            )
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(
                text("SELECT erev.capture_subledger_commit(:posting)"), {"posting": posting}
            )
            == stamp
        )
        uow.commit()
    with world.place.uow() as uow:
        assert (
            uow.session.scalar(
                text(
                    "SELECT committed_server_at FROM erev.subledger_posting_commit "
                    "WHERE subledger_posting_id = :posting"
                ),
                {"posting": posting},
            )
            == stamp
        )


def test_commit_visibility_catalogue_matches_migration(world: K11World) -> None:
    with world.place.uow() as uow:
        rows = uow.session.execute(
            text("SELECT code, ipe_logic FROM erev.report_definition WHERE version = 1")
        ).all()
    stored = dict(rows)
    for code in (*COMMIT_VISIBILITY_REPORTS, *RETAINED_COMMIT_REPORTS):
        assert stored[code] == DEFINITIONS_BY_CODE[code].ipe_logic


def test_commit_recovery_continues_after_failed_posting_and_retries_next_sweep(
    world: K11World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commit_evidence, "retain_after_commit", lambda *args: None)
    first, stored = _posted(world)
    with world.place.uow() as uow:
        second = subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:recovery",
            description="Recovery continues after an unavailable commit",
            lines=[{**line, "id": new_id()} for line in _lines_of(world, first)],
            contract_computation_id=stored["id"],
        )
        uow.commit()
    failed_id, healthy_id = sorted((first, second.posting_id))
    capture = commit_evidence._capture

    def unavailable(session: Session, posting_id: UUID) -> None:
        if posting_id == failed_id:
            session.execute(text("SELECT 1 / 0"))
        capture(session, posting_id)

    monkeypatch.setattr(commit_evidence, "_capture", unavailable)
    assert commit_evidence.recover_pending(world.place.tenant_id, batch_size=1) == (1, 1)
    assert world.place.scalar(select(func.erev.subledger_commit_time(healthy_id))) is not None
    monkeypatch.setattr(commit_evidence, "_capture", capture)
    assert commit_evidence.recover_pending(world.place.tenant_id, batch_size=1) == (1, 0)
    assert commit_evidence.recover_pending(world.place.tenant_id, batch_size=1) == (0, 0)


def test_retained_sources_and_incremental_extract_use_commit_window(world: K11World) -> None:
    first, stored = _posted(world)
    lines = _lines_of(world, first)
    periods = {line["period_id"] for line in lines}
    with world.place.uow() as uow:
        later = subledger.post(
            uow,
            book_code="ASC606",
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=f"{subledger.compute_key(stored['id'])}:retained-cutoff",
            description="Late commit with an earlier business record timestamp",
            lines=[{**line, "id": new_id()} for line in lines],
            contract_computation_id=stored["id"],
        )
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        uow.commit()
    params = ReportParams(
        report_code=extract_subledger_lines.CODE,
        report_version=1,
        parameters={},
        entity_ids=(world.entity_id,),
        known_at=cutoff,
        book_code="ASC606",
        sources=SourceCollector(),
    )
    with world.place.uow() as uow:
        original = extract_subledger_lines.build(uow, params)
        bbr = bbr_sources.read(uow, replace(params, sources=None), period_ids=periods)
    assert {row["subledger_posting_id"] for row in original.rows} == {str(first)}
    assert {row["id"] for row in bbr["revenue"]} == {
        str(line["id"]) for line in lines if str(line["account_role"]) == "REVENUE"
    }
    assert params.sources is not None
    bound = params.sources.binding(row_keys=[row["row_key"] for row in original.rows])
    end = world.place.scalar(select(func.clock_timestamp()))
    with world.place.uow() as uow:
        incremental = extract_subledger_lines.build(
            uow,
            replace(
                params,
                known_at=end,
                sources=None,
                parameters={"mode": "INCREMENTAL", "known_since": cutoff.isoformat()},
            ),
        )
        rerun = extract_subledger_lines.build(
            uow, replace(params, binding=bound, known_at=end, sources=None)
        )
    assert {row["subledger_posting_id"] for row in incremental.rows} == {str(later.posting_id)}
    assert rerun.rows == original.rows
    legacy_evidence = dict(bound.evidence)
    legacy_evidence.pop(extract_subledger_lines.COMMIT_EVIDENCE)
    legacy_evidence[extract_subledger_lines.EVIDENCE] = [
        {key: value for key, value in row.items() if key != "_committed_server_at"}
        for row in legacy_evidence[extract_subledger_lines.EVIDENCE]
    ]
    with world.place.uow() as uow:
        legacy = extract_subledger_lines.build(
            uow, replace(params, binding=replace(bound, evidence=legacy_evidence), sources=None)
        )
    assert legacy.rows == original.rows
