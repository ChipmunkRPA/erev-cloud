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
    # The same overlapping event/version transaction must also stay out of the sample pack.
    import json

    from erev_api.domain.reports import evidence_sample_computations, evidence_sample_events
    from erev_api.domain.reports.evidence_commands import PERMISSIONS
    from erev_api.schemas.evidence_packs import ContractSamplePackCreateIn

    world.place.clock.set(end)
    principal = replace(
        world.place.principal,
        permissions=world.place.principal.permissions | PERMISSIONS,
        permission_scopes={
            **world.place.principal.permission_scopes,
            **{permission: "*" for permission in PERMISSIONS},
        },
    )
    external_id = world.place.scalar(select(contract.c.external_id).where(contract.c.id == cid))
    request = ContractSamplePackCreateIn(
        kind="CONTRACT_SAMPLE", contract_external_ids=[external_id], as_of=date(2026, 9, 30)
    )
    with world.place.uow(principal) as reader:
        old_events = evidence_sample_events.collect(reader, request, known_at=cutoff)
        new_events = evidence_sample_events.collect(reader, request, known_at=end)
        assert appended[0]["id"] not in old_events.event_ids
        assert appended[0]["id"] in new_events.event_ids
        old_identity = json.loads(old_events.files[0].content)["contracts"][0]
        new_identity = json.loads(new_events.files[0].content)["contracts"][0]
        assert old_identity["external_id"] == new_identity["external_id"] == external_id
        assert old_identity["source_revision_id"] != new_identity["source_revision_id"]
        assert old_identity["committed_server_at"] < new_identity["committed_server_at"]
        old_computations = evidence_sample_computations.collect(
            reader, old_events.selection, as_of=request.as_of
        )
        new_computations = evidence_sample_computations.collect(
            reader, new_events.selection, as_of=request.as_of
        )
        assert first in old_computations.version_ids
        assert later not in old_computations.version_ids
        assert later in new_computations.version_ids
        old_index = json.loads(old_computations.files[0].content)
        new_index = json.loads(new_computations.files[0].content)
        assert {row["version_id"] for row in old_index["selected_versions"]} == {str(first)}
        assert {row["version_id"] for row in new_index["selected_versions"]} == {str(later)}
        assert all(row["committed_server_at"] for row in new_index["versions"])
        old_members = json.loads(
            next(
                file.content
                for file in old_computations.files
                if file.path.endswith("/members.json")
            )
        )
        assert old_members[0]["source_revision_id"] == old_identity["source_revision_id"]
        from datetime import timedelta

        from erev_api.db.tables import report_source_revision
        from erev_api.problems import Problem

        first_commit = reader.session.execute(
            select(
                func.erev.source_commit_time("report_source_revision", report_source_revision.c.id)
            ).where(
                report_source_revision.c.source_kind == "contract",
                report_source_revision.c.source_id == cid,
                report_source_revision.c.revision_no == 1,
            )
        ).scalar_one()
        with pytest.raises(Problem, match="Contract identities are unavailable"):
            evidence_sample_events.collect(
                reader, request, known_at=first_commit - timedelta(microseconds=1)
            )
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
        if row.source_kind in {"contract_event", "contract_version"}
    ] == [("contract_event", "CONTRACT_ACTIVATED")]
    assert any(row.source_kind == "approval_decision" for row in pending)
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
    audit_source = world.place.scalar(
        select(historical_source_commit.c.source_id)
        .where(historical_source_commit.c.source_kind == "audit_event")
        .limit(1)
    )
    assert audit_source is not None
    with pytest.raises(DBAPIError, match="permission denied for table historical_source_commit"):
        with world.place.uow() as uow:
            uow.session.execute(
                update(historical_source_commit)
                .where(historical_source_commit.c.source_id == audit_source)
                .values(source_occurred_at=func.clock_timestamp())
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
        "approvals_register",
        "audit_log_export",
        "chain_verification_report",
        "intercompany_pairs",
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


def test_approval_register_uses_committed_entity_codes(world: K11World) -> None:
    from erev_api.db.tables import approval_request, legal_entity
    from erev_api.domain.reports.builders import RETAINED, approvals_register
    from sqlalchemy import insert
    from support.rows import approval_request_values

    stamp = world.place.scalar(select(func.clock_timestamp()))
    request = approval_request_values(
        world.place.tenant_id,
        entity_id=world.entity_id,
        submitted_at=stamp,
    )
    with world.place.uow() as uow:
        uow.session.execute(insert(approval_request).values(**request))
        uow.commit()
    original_code = world.place.scalar(
        select(legal_entity.c.code).where(legal_entity.c.id == world.entity_id)
    )
    with world.place.uow() as writer:
        writer.session.execute(
            update(legal_entity)
            .where(legal_entity.c.id == world.entity_id)
            .values(code="RENAMED-COMMIT")
        )
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    now = world.place.scalar(select(func.clock_timestamp()))
    params = ReportParams(
        report_code="approvals_register",
        report_version=1,
        parameters={"from_date": stamp.date().isoformat(), "to_date": stamp.date().isoformat()},
        entity_ids=(world.entity_id,),
        known_at=cutoff,
        historical=True,
        sources=SourceCollector(),
    )
    with world.place.uow() as reader:
        old = approvals_register.build(reader, params)
        latest = approvals_register.build(reader, replace(params, known_at=now, sources=None))
        assert old.rows and latest.rows
        assert {row["entity_code"] for row in old.rows} == {original_code}
        assert {row["entity_code"] for row in latest.rows} == {"RENAMED-COMMIT"}
        assert params.sources is not None
        proof = params.sources.evidence["approval_entity_code_revisions_v1"]
        assert len(proof) == 1 and proof[0]["source_revision_id"]
        bound = params.sources.binding(
            row_keys=[row["row_key"] for row in old.rows], strategy=RETAINED
        )
        assert (
            approvals_register.build(reader, replace(params, sources=None, binding=bound)).rows
            == old.rows
        )


def test_verification_report_excludes_late_commits_and_retains_inputs(world: K11World) -> None:
    from types import SimpleNamespace

    from erev_api.db import new_id
    from erev_api.db.tables import audit_chain_verification
    from erev_api.domain.reports.builders import RETAINED
    from erev_api.domain.reports.builders import chain_verification_report as report
    from sqlalchemy import insert

    stamp = world.place.scalar(select(func.clock_timestamp()))
    values = {
        "tenant_id": world.place.tenant_id,
        "id": new_id(),
        "trigger": "SCHEDULED",
        "from_chain_seq": 1,
        "to_chain_seq": 1,
        "events_checked": 1,
        "result": "PASS",
        "digest_last_hmac": "a" * 64,
        "started_at": stamp,
        "finished_at": stamp,
        "created_at": stamp,
        "created_by": None,
        "created_by_kind": "SYSTEM",
    }
    with world.place.uow() as setup:
        setup.session.execute(insert(audit_chain_verification).values(**values))
        setup.commit()
    late_id = new_id()
    with world.place.uow() as writer:
        writer.session.execute(
            insert(audit_chain_verification).values(
                **{
                    **values,
                    "id": late_id,
                    "result": "FAIL",
                    "first_failure_seq": 1,
                    "digest_last_hmac": None,
                },
            )
        )
        cutoff = world.place.scalar(select(func.clock_timestamp()))
        writer.commit()
    now = world.place.scalar(select(func.clock_timestamp()))
    params = ReportParams(
        report_code=report.CODE,
        report_version=1,
        parameters={},
        entity_ids=(),
        known_at=cutoff,
        historical=True,
        sources=SourceCollector(),
    )
    with world.place.uow() as reader:
        old = report.build(reader, params)
        latest = report.build(reader, replace(params, known_at=now, sources=None))
    assert old.control_totals["verification_count"] == 1
    assert old.control_totals["failure_count"] == 0
    assert latest.control_totals["verification_count"] == 2
    assert latest.control_totals["failure_count"] == 1
    assert latest.rows[1]["row_key"].endswith(":2")
    assert params.sources is not None
    binding = params.sources.binding(row_keys=[r["row_key"] for r in old.rows], strategy=RETAINED)
    assert binding.evidence[report.EVIDENCE]["records"][0]["committed_server_at"]
    rebuilt = report.build(
        SimpleNamespace(principal=world.place.principal),
        replace(params, sources=None, binding=binding, known_at=now),
    )
    assert rebuilt.rows == old.rows and rebuilt.control_totals == old.control_totals
    commit_evidence.recover_pending_sources(world.place.tenant_id)
    committed = world.place.scalar(
        select(historical_source_commit.c.committed_server_at).where(
            historical_source_commit.c.source_kind == "audit_chain_verification",
            historical_source_commit.c.source_id == late_id,
        )
    )
    assert cutoff < committed <= now
