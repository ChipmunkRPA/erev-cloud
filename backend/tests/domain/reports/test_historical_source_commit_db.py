"""Original event/version commits govern historical selection and incremental exports."""

from dataclasses import replace
from datetime import date
from uuid import UUID

import pytest
from erev_api.db.tables import contract, contract_version, customer, historical_source_commit
from erev_api.domain.contracts import bundles, computation
from erev_api.domain.journals import commit_evidence
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import (
    ReportParams,
    SourceCollector,
    bbr_sources,
    extract_contract_versions,
    extract_contracts,
    extract_events,
    rpo,
)
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE, SOURCE_COMMIT_REPORTS
from erev_api.enums import ComputationTrigger, ContractEventType
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.money import MoneyIn
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from support.factories import K11World, engine
from tests.domain.reports.test_historical_line_cutoff_db import _lines_of, _posted
from tests.domain.reports.test_historical_line_cutoff_db import app as app
from tests.domain.reports.test_historical_line_cutoff_db import world as world


def test_late_event_and_version_commit_keeps_previous_historical_version(world: K11World) -> None:
    posting, stored = _posted(world)
    first = UUID(stored["contract_version_ids"]["ASC606"])
    lines = _lines_of(world, posting)
    cid = lines[0]["contract_id"]
    group = world.place.scalar(
        select(contract_version.c.combination_group_id).where(contract_version.c.id == first)
    )
    head = world.place.scalar(select(contract.c.head_stream_version).where(contract.c.id == cid))
    with world.place.uow() as uow:
        appended = append_events(
            uow,
            contract_id=cid,
            expected_stream_version=head,
            origin="UI",
            events=[
                EventIn(
                    event_type=ContractEventType.BILLING_RECORDED,
                    effective_date=date(2026, 9, 16),
                    payload=BillingRecordedV1(
                        invoice_number="COMMIT-WINDOW",
                        line_external_id="COMMIT-WINDOW-1",
                        obligation_key="O1",
                        amount=MoneyIn(amount="5000.00", currency="USD"),
                        issue_date=date(2026, 9, 16),
                    ),
                )
            ],
        )
        bundle = bundles.build(uow.session, group, uow.now, (), ComputationTrigger.COMMAND)
        result = computation.persist(uow, bundle, engine()(bundle))
        later = UUID(result["contract_version_ids"]["ASC606"])
        assert later != first
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        uow.commit()
    params = ReportParams(
        report_code="contract_balances",
        report_version=1,
        parameters={},
        entity_ids=(world.entity_id,),
        known_at=cutoff,
        book_code="ASC606",
        historical=True,
        sources=SourceCollector(),
    )
    end = world.place.scalar(select(func.clock_timestamp()))
    with world.place.uow() as uow:
        assert tie_outs.versions_for(uow.session, params, book_code="ASC606", cutoff=cutoff) == (
            first,
        )
        assert tie_outs.versions_for(uow.session, params, book_code="ASC606", cutoff=end) == (
            later,
        )
        rpo_history = rpo.load(
            uow.session,
            entity_ids=params.entity_ids,
            book_code="ASC606",
            cutoff=cutoff,
            params=params,
        )
        assert later not in {
            version.id for chain in rpo_history.chains.values() for version in chain
        }
        assert first in {version.id for chain in rpo_history.chains.values() for version in chain}
        sources = bbr_sources.read(
            uow, replace(params, sources=None), period_ids={line["period_id"] for line in lines}
        )
        assert str(appended[0]["id"]) not in {row["id"] for row in sources["events"]}
        header_params = replace(
            params, report_code=extract_contracts.CODE, sources=SourceCollector()
        )
        original_headers = extract_contracts.build(uow, header_params)
        assert (
            next(row for row in original_headers.rows if row["id"] == str(cid))[
                "head_stream_version"
            ]
            == head
        )
        changed_headers = extract_contracts.build(
            uow,
            replace(
                header_params,
                known_at=end,
                sources=None,
                parameters={"mode": "INCREMENTAL", "known_since": cutoff.isoformat()},
            ),
        )
        assert {row["id"] for row in changed_headers.rows} == {str(cid)}
        assert changed_headers.rows[0]["head_stream_version"] == head + 1
        for builder, expected in (
            (extract_events, appended[0]["id"]),
            (extract_contract_versions, later),
        ):
            base = replace(params, report_code=builder.CODE, sources=SourceCollector())
            original = builder.build(uow, base)
            assert str(expected) not in {row["id"] for row in original.rows}
            incremental = builder.build(
                uow,
                replace(
                    base,
                    known_at=end,
                    sources=None,
                    parameters={"mode": "INCREMENTAL", "known_since": cutoff.isoformat()},
                ),
            )
            assert {row["id"] for row in incremental.rows} == {str(expected)}
            assert base.sources is not None
            bound = base.sources.binding(row_keys=[row["row_key"] for row in original.rows])
            rerun = builder.build(uow, replace(base, binding=bound, sources=None, known_at=end))
            assert rerun.rows == original.rows
            legacy = dict(bound.evidence)
            legacy.pop(builder.COMMIT_EVIDENCE)
            legacy[builder.EVIDENCE] = [
                {key: value for key, value in row.items() if key != "_committed_server_at"}
                for row in legacy[builder.EVIDENCE]
            ]
            old = builder.build(
                uow,
                replace(
                    base,
                    binding=replace(bound, evidence=legacy),
                    sources=None,
                    known_at=end,
                ),
            )
            assert old.rows == original.rows
    with world.place.uow() as uow:
        pending = uow.session.execute(
            text(
                "SELECT h.source_kind, e.event_type, h.source_id "
                "FROM erev.historical_source_commit h "
                "LEFT JOIN erev.contract_event e ON e.id=h.source_id AND e.tenant_id=h.tenant_id "
                "WHERE h.committed_server_at IS NULL"
            )
        ).all()
    # Activation uses a delegated SYSTEM unit in the outer transaction. Its durable queue
    # is recovered by the minute worker even when that delegated unit does not run hooks.
    assert [
        (row.source_kind, row.event_type)
        for row in pending
        if row.source_kind != "report_source_revision"
    ] == [("contract_event", "CONTRACT_ACTIVATED")]
    assert commit_evidence.recover_pending_sources(world.place.tenant_id, batch_size=1) == (
        len(pending),
        0,
    )
    assert commit_evidence.recover_pending_sources(world.place.tenant_id) == (0, 0)


def test_source_commit_archive_and_catalogue_are_protected(world: K11World) -> None:
    _, stored = _posted(world)
    version_id = UUID(stored["contract_version_ids"]["ASC606"])
    commit_evidence.recover_pending_sources(world.place.tenant_id)
    stamp = world.place.scalar(select(func.erev.source_commit_time("contract_version", version_id)))
    assert stamp is not None
    with pytest.raises(DBAPIError, match="EREV-IMM-001"):
        with world.place.uow() as uow:
            uow.session.execute(
                update(historical_source_commit)
                .where(
                    historical_source_commit.c.source_kind == "contract_version",
                    historical_source_commit.c.source_id == version_id,
                )
                .values(committed_server_at=func.clock_timestamp())
            )
    with world.place.uow() as uow:
        stored_ipe = dict(
            uow.session.execute(
                text("SELECT code, ipe_logic FROM erev.report_definition WHERE version=1")
            ).all()
        )
    from erev_api.domain.reports.catalogue import JOURNAL_COMMIT_REPORTS

    for code in (
        *SOURCE_COMMIT_REPORTS,
        *JOURNAL_COMMIT_REPORTS,
        "extract_contracts",
        "je_population",
        "contract_sample_pack",
    ):
        assert stored_ipe[code] == DEFINITIONS_BY_CODE[code].ipe_logic, code


def test_contract_incremental_export_includes_committed_label_changes(world: K11World) -> None:
    _posted(world)
    cutoff = world.place.scalar(select(func.clock_timestamp()))
    params = ReportParams(
        report_code=extract_contracts.CODE,
        report_version=1,
        parameters={},
        entity_ids=(world.entity_id,),
        known_at=cutoff,
        sources=SourceCollector(),
    )
    with world.place.uow() as uow:
        original = extract_contracts.build(uow, params)
    assert original.rows
    with world.place.uow() as uow:
        uow.session.execute(
            update(customer)
            .where(customer.c.id == world.customer_id)
            .values(code="COMMIT-CUSTOMER")
        )
        uow.commit()
    end = world.place.scalar(select(func.clock_timestamp()))
    with world.place.uow() as uow:
        delta = extract_contracts.build(
            uow,
            replace(
                params,
                sources=None,
                known_at=end,
                parameters={"mode": "INCREMENTAL", "known_since": cutoff.isoformat()},
            ),
        )
        assert {row["id"] for row in delta.rows} == {row["id"] for row in original.rows}
        assert {row["customer_code"] for row in delta.rows} == {"COMMIT-CUSTOMER"}
        assert params.sources is not None
        bound = params.sources.binding(row_keys=[row["row_key"] for row in original.rows])
        assert (
            extract_contracts.build(uow, replace(params, binding=bound, sources=None)).rows
            == original.rows
        )
        legacy = dict(bound.evidence)
        legacy.pop(extract_contracts.COMMIT_EVIDENCE)
        legacy[extract_contracts.EVIDENCE] = [
            {key: value for key, value in row.items() if key != "_committed_server_at"}
            for row in legacy[extract_contracts.EVIDENCE]
        ]
        assert (
            extract_contracts.build(
                uow,
                replace(
                    params,
                    binding=replace(bound, evidence=legacy),
                    sources=None,
                ),
            ).rows
            == original.rows
        )
