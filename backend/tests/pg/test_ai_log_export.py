"""Call-export datasets keep the API's scope and uncertainty in both file formats."""

import csv
import io
from dataclasses import replace
from datetime import timedelta

import openpyxl
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import ai_model_log
from erev_api.domain.ai.log_export import ExportAccess, capture_access, require_access
from erev_api.domain.ai.log_export import dataset as bound_dataset
from erev_api.domain.reports.outputs import ReportData, RunStamp
from erev_api.domain.reports.outputs.csv import render_csv
from erev_api.domain.reports.outputs.xlsx import render_xlsx
from erev_api.enums import PrincipalKind, TenantKind
from erev_api.problems import Problem
from sqlalchemy import insert
from support.db import TestDatabase
from support.principals import colleague, member
from support.rows import RowContext, ai_model_log_row

pytestmark = pytest.mark.pg


def dataset(ctx: RequestContext) -> ReportData:
    return bound_dataset(ctx, capture_access(ctx))


def test_export_dataset_scope_uncertainty_and_spreadsheet_safety(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = member(keyring, clock)
    peer = colleague(owner.tenant_id, "export_peer")
    other = member(keyring, clock)
    own_ids = []
    for index, person in enumerate((owner, peer, owner, other)):
        with tenant_session(DbContext(person.tenant_id, person.user_id, "*")) as session:
            row = ai_model_log_row(RowContext(person.tenant_id, person.user_id), session)
            row.update(
                created_by=person.user_id,
                created_by_kind="USER",
                created_at=clock.now() - timedelta(seconds=10 - index),
                model_id="=SUM(A1)",
                input_tokens=0,
                output_tokens=0,
                outcome="ERROR" if index == 2 else "SUCCESS",
                response_sha256=None if index == 2 else "b" * 64,
                parameters={"usage_evidence": "UNKNOWN" if index == 2 else "REPORTED"},
            )
            session.execute(insert(ai_model_log).values(**row))
            if person == owner:
                own_ids.append(str(row["id"]))
    principal = replace(
        system_principal(owner.tenant_id),
        kind=PrincipalKind.USER,
        id=owner.user_id,
        permissions=frozenset({"ai.use", "report.export"}),
        permission_scopes={"ai.use": "*", "report.export": "*"},
    )
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="export-test",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    data = dataset(ctx)
    assert [row["id"] for row in data.rows] == own_ids[::-1]
    assert data.control_totals == {
        "row_count": 2,
        "unknown_usage_calls": 1,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
    }
    csv_rows = list(csv.DictReader(io.StringIO(render_csv(data).decode("utf-8"))))
    assert csv_rows[0]["Input tokens"] == csv_rows[0]["Output tokens"] == ""
    assert csv_rows[1]["Input tokens"] == csv_rows[1]["Output tokens"] == "0"
    assert all(row["Model"] == "'=SUM(A1)" for row in csv_rows)
    assert set(csv_rows[0]) == {column.header for column in data.columns}
    stamp = RunStamp(
        report_code="ai_call_log",
        report_name="AI calls",
        report_version=1,
        report_run_no="TEST-1",
        parameters={},
        entity_codes=(),
        book=None,
        as_of=None,
        source="test",
        engine_version="test",
        build_sha="test",
        run_by="Export test",
        run_at=clock.now(),
        output_sha256="a" * 64,
    )
    workbook = openpyxl.load_workbook(io.BytesIO(render_xlsx(data, stamp)))
    cells = [cell for sheet in workbook for line in sheet for cell in line]
    assert any(cell.value == "Unknown" for cell in cells)
    assert any(cell.value == 0 and cell.data_type == "n" for cell in cells)
    assert any(cell.value == "'=SUM(A1)" for cell in cells)
    assert all(cell.data_type != "f" for cell in cells)
    administrator = replace(
        principal,
        permissions=frozenset({"settings.manage", "report.export"}),
        permission_scopes={"settings.manage": "*", "report.export": "*"},
    )
    assert dataset(replace(ctx, principal=administrator)).row_count == 3
    scoped = replace(
        administrator, permission_scopes={"settings.manage": frozenset({owner.tenant_id})}
    )
    with pytest.raises(Problem):
        dataset(replace(ctx, principal=scoped))
    with pytest.raises(Problem):
        dataset(replace(ctx, principal=system_principal(owner.tenant_id)))

    with pytest.raises(Problem):
        dataset(replace(ctx, principal=replace(administrator, id=None)))
    with pytest.raises(Problem):
        dataset(replace(ctx, principal=replace(administrator, kind=PrincipalKind.OPERATOR)))

    own_access = capture_access(ctx)
    # The queued record survives serialization; current rights cannot expand its maximum scope.
    retained = ExportAccess.model_validate_json(own_access.model_dump_json())
    promoted_ctx = replace(ctx, principal=administrator)
    assert bound_dataset(promoted_ctx, retained).row_count == 2
    wide_access = capture_access(promoted_ctx)
    assert wide_access.scope == "TENANT"
    with pytest.raises(Problem) as demoted:
        require_access(ctx, wide_access)
    assert demoted.value.slug == "forbidden"
    for changed in (
        replace(principal, id=peer.user_id),
        replace(principal, tenant_id=other.tenant_id),
        replace(principal, kind=PrincipalKind.API_CLIENT),
    ):
        with pytest.raises(Problem) as hidden:
            require_access(replace(ctx, principal=changed), retained)
        assert hidden.value.slug == "not-found"
    with pytest.raises(Problem):
        require_access(
            replace(ctx, principal=replace(principal, permissions=frozenset())), retained
        )
    with pytest.raises(Problem):
        require_access(replace(ctx, principal=replace(principal, permission_scopes={})), retained)

    limited_export = replace(
        principal, permission_scopes={"ai.use": "*", "report.export": frozenset({owner.tenant_id})}
    )
    assert bound_dataset(replace(ctx, principal=limited_export), retained).row_count == 2
    limited_admin_export = replace(
        administrator,
        permission_scopes={"settings.manage": "*", "report.export": frozenset({owner.tenant_id})},
    )
    with pytest.raises(Problem):
        require_access(replace(ctx, principal=limited_admin_export), wide_access)
    with pytest.raises(Problem):
        capture_access(
            replace(ctx, principal=replace(principal, permissions=frozenset({"ai.use"})))
        )
    with pytest.raises(Problem):
        require_access(
            replace(ctx, principal=replace(principal, permissions=frozenset({"ai.use"}))), retained
        )
