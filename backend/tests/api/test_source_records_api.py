"""API-R-56 source records (04 §15.3 API-R-56, §16.14 API-S-SourceRecord; T-SRC-01; 05 ADP-04,
PRV-05; 03 REQ-SEC-007; BUILD_SPEC DIN-2).

World: ``support.factories.import_world`` (a Revenue Accountant, ``contract.read``). Records are
stored through ``normalise.store_source_record``: an API customer delivered by the client
``svc-salesforce`` with its request id and ``Idempotency-Key``, and a legacy SKU SSP file row with
its upload and row.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, file_object, import_row, import_upload
from erev_api.domain.integrations import normalise
from erev_api.domain.integrations.normalise import SourceIdentity
from erev_api.enums import FilePurpose, PrincipalKind, SourceObjectType, SourceSystem, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import UnitOfWork, unit_of_work
from fastapi import FastAPI
from sqlalchemy import insert
from support.db import TestDatabase
from support.factories import ImportWorld, import_world, maya_principal
from support.reference import get
from support.rows import (
    api_client_values,
    file_object_values,
    import_row_values,
    import_upload_values,
)

SOURCE_RECORDS = "/api/v1/source-records/{record_id}"
IDEMPOTENCY_KEY = "6c1f0f5e-2b7d-4d61-9f0e-5a0d3c7b9e21"
MEMBERS = [
    "id",
    "source_system",
    "object_type",
    "external_id",
    "external_version",
    "received_at",
    "api_client",
    "idempotency_key",
    "request_id",
    "payload_sha256",
    "payload",
    "import_upload_id",
    "import_row_id",
    "sync_run_id",
]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ImportWorld:
    return import_world(app, keyring, clock, files)


@contextmanager
def _uow(
    world: ImportWorld, principal: Principal, keyring: KeyRing, files: LocalFileStore
) -> Iterator[UnitOfWork]:
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-source-record-route",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=world.clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=world.clock, keyring=keyring, files=files) as uow:
        yield uow


def test_source_record_route_redacts_contacts(
    world: ImportWorld, keyring: KeyRing, files: LocalFileStore
) -> None:
    maya = maya_principal(world.actor.member)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    client = api_client_values(world.tenant_id, name="svc-salesforce")
    stored_file = file_object_values(world.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
    upload = import_upload_values(world.tenant_id, file_object_id=stored_file["id"])
    sheet_row = import_row_values(world.tenant_id, import_upload_id=upload["id"])
    with tenant_session(context) as session:
        session.execute(insert(api_client).values(**client))
        session.execute(insert(file_object).values(**stored_file))
        session.execute(insert(import_upload).values(**upload))
        session.execute(insert(import_row).values(**sheet_row))
    service = replace(
        maya,
        kind=PrincipalKind.API_CLIENT,
        id=UUID(str(client["id"])),
        membership_id=None,
        display_name="svc-salesforce",
        roles=(),
    )
    with _uow(world, service, keyring, files) as uow:
        delivered = normalise.store_source_record(
            uow,
            identity=SourceIdentity(SourceSystem.API, SourceObjectType.CUSTOMER, "C-77", "1"),
            version_order=1,
            payload={
                "code": "C-77",
                "name": "Harbourline Freight Ltd (Demo)",
                "contact_name": "Ines Carvalho",
                "contact_email": "ines@harbourline.example",
                "contact_phone": "+351 21 555 0100",
                "billing_address": {"line1": "4 Quay Street", "city": "Lisbon"},
                "credit_limit": "5000.00",
            },
            request_id="req-c77",
            idempotency_key=IDEMPOTENCY_KEY,
        )
        uow.commit()
    with _uow(world, maya, keyring, files) as uow:
        file_row = normalise.store_source_record(
            uow,
            identity=normalise.file_row_identity(
                source_system=SourceSystem.LEGACY_TEMPLATE_V1,
                object_type=SourceObjectType.SSP_ROW,
                import_upload_id=UUID(str(upload["id"])),
                sheet_name="SKU Setup",
                row_number=2,
            ),
            version_order=1,
            payload={"SKU Name": "Hardware 1", "SKU Unit List Price": "100"},
            import_upload_id=UUID(str(upload["id"])),
            import_row_id=UUID(str(sheet_row["id"])),
        )
        uow.commit()

    response = get(world.app, SOURCE_RECORDS.format(record_id=delivered.id), world.actor)
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == MEMBERS
    assert (
        body["id"],
        body["source_system"],
        body["object_type"],
        body["external_id"],
        body["external_version"],
    ) == (str(delivered.id), "API", "CUSTOMER", "C-77", "1")
    assert body["payload"] == {
        "code": "C-77",
        "name": "Harbourline Freight Ltd (Demo)",
        "contact_name": "[redacted]",
        "contact_email": "[redacted]",
        "contact_phone": "[redacted]",
        "billing_address": "[redacted]",
        "credit_limit": "5000.00",
    }
    assert body["api_client"] == {"id": str(client["id"]), "name": "svc-salesforce"}
    assert (
        body["idempotency_key"],
        body["request_id"],
        body["import_upload_id"],
        body["import_row_id"],
        body["sync_run_id"],
    ) == (IDEMPOTENCY_KEY, "req-c77", None, None, None)
    assert body["payload_sha256"] == delivered.payload_sha256
    assert body["received_at"].endswith("Z") or "+00:00" in body["received_at"]
    for clear in (
        "Ines Carvalho",
        "ines@harbourline.example",
        "555 0100",
        "4 Quay Street",
        "hmac:",
    ):
        assert clear not in response.text

    lineage = get(world.app, SOURCE_RECORDS.format(record_id=file_row.id), world.actor)
    assert lineage.status_code == 200, lineage.text
    found = lineage.json()
    assert (
        found["api_client"],
        found["idempotency_key"],
        found["request_id"],
        found["import_upload_id"],
        found["import_row_id"],
        found["sync_run_id"],
        found["payload"],
    ) == (
        None,
        None,
        None,
        str(upload["id"]),
        str(sheet_row["id"]),
        None,
        {"SKU Name": "Hardware 1", "SKU Unit List Price": "100"},
    )
    assert found["external_id"] == f"{upload['id']}:SKU Setup:2"

    missing = get(world.app, SOURCE_RECORDS.format(record_id=new_id()), world.actor)
    assert missing.status_code == 404
    assert missing.json()["type"].endswith("not-found")
