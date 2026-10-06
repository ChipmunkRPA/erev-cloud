"""DIN-10 import mapping profiles (04 T-IMP-06, E-12, E-119, §15.3 API-R-43, §16.6 ``header_match``;
PRD SM-04, ACT-22, §2.5 routing row ``MAPPING_PROFILE_VERSION``; SCREENS §12.2 step 2, §12.4; 03
REQ-DAT-013; BUILD_SPEC DIN-10).

World: a tenant whose author holds Revenue Accountant (``config.author``, ``import.upload``) and
Controller (``config.approve``), enrolled in MFA, and a second Controller who approves. The CSV v2
``contracts`` files are validated as the worker validates them; the legal entity they name,
AVM-US, exists (04 rev 1.107 table 15.4-B ``IMPORT_ENTITY_NOT_AVAILABLE``, ruling R-29: a row
naming an entity that does not exist is an ERROR of the validation).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import import_row
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    ImportWorld,
    run_import_job,
    stamp_test_release,
    upload_import_source,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import approve, assign, calendar, entity, get, post, slug

PROFILES = "/api/v1/import-mapping-profiles"
# The required ``contracts`` columns (NC-19 flattening of API-S-ContractCreate).
REQUIRED = {
    "external_id": "SF-ORD-50001",
    "contracting_entity_code": "AVM-US",
    "transaction_currency": "USD",
    "inception_date": "2026-03-01",
    "lines.obligation_key": "O1",
    "lines.product_code": "AVM-PLAT-100",
    "lines.quantity": "1",
    "lines.total_price.amount": "100000.00",
    "lines.total_price.currency": "USD",
}


@dataclass(frozen=True, slots=True)
class ProfileWorld:
    imports: ImportWorld
    approver: Actor

    @property
    def app(self) -> FastAPI:
        return self.imports.app

    @property
    def author(self) -> Actor:
        return self.imports.actor


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ProfileWorld:
    someone = member(keyring, clock)
    for role in ("revenue_accountant", "controller"):
        assign(someone, role)
    author = enrolled(app, clock, someone)
    # The entity REQUIRED names: since ruling R-29 the validation refuses a row whose entity does
    # not exist, so the world holds it (the files of this module are about headers, not entities).
    entity(app, author, code="AVM-US", calendar_id=calendar(app, author))
    other = colleague(someone.tenant_id, "marcus")
    assign(other, "controller")
    files = LocalFileStore(app_settings.file_root)
    # 05 REL-03 (rev 1.15; D-98 60): the IMPORT_COMMIT job (run_import_job) runs in THIS process and
    # its CTL-001 / CTL-044 evidence producer stamps the process release — a process that never
    # stamped fails closed (release-mismatch) whatever rows the table holds, so the job runtime
    # stamps through the shared support exactly as the world factories do (P5-DOCTOR-R1).
    stamp_test_release()
    return ProfileWorld(
        imports=ImportWorld(
            app=app,
            actor=author,
            runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
            clock=clock,
        ),
        approver=enrolled(app, clock, other),
    )


def _csv(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _created(world: ProfileWorld, mappings: Mapping[str, Any], code: str = "SF-EXPORT") -> Any:
    created = post(
        world.app,
        PROFILES,
        world.author,
        {
            "code": code,
            "name": "Salesforce export",
            "template_code": "contracts",
            "mappings": dict(mappings),
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    return created.json()


def _submitted(world: ProfileWorld, mappings: Mapping[str, Any]) -> Any:
    profile = _created(world, mappings)
    tested = post(world.app, f"{PROFILES}/{profile['id']}/test", world.author, {})
    assert (tested.status_code, tested.json()["status"]) == (200, "TESTED"), tested.text
    submitted = post(
        world.app, f"{PROFILES}/{profile['id']}/submit", world.author, {"comment": "Export"}
    )
    assert (submitted.status_code, submitted.json()["status"]) == (200, "SUBMITTED"), submitted.text
    return submitted.json()


def _published(world: ProfileWorld, mappings: Mapping[str, Any]) -> Any:
    profile = _submitted(world, mappings)
    decided = approve(world.app, str(profile["approval_request_id"]), world.approver)
    assert decided.status_code == 200, decided.text
    shown = get(world.app, f"{PROFILES}/{profile['id']}", world.author)
    assert (shown.status_code, shown.json()["status"]) == (200, "PUBLISHED"), shown.text
    return shown.json()


def _import(world: ProfileWorld, content: bytes, profile_id: str) -> Any:
    """``POST /imports`` of a ``contracts`` file through a profile."""
    file_id = upload_import_source(world.imports, "salesforce-export.csv", content)
    body = {"file_id": file_id, "template_code": "contracts", "mapping_profile_id": profile_id}
    return post(world.app, IMPORTS_PATH, world.author, body)


def _validated(world: ProfileWorld, content: bytes, profile_id: str) -> dict[str, Any]:
    created = _import(world, content, profile_id)
    assert created.status_code == 202, created.text
    run_import_job(world.imports, UUID(created.json()["id"]))
    shown = get(world.app, f"{IMPORTS_PATH}/{created.headers['X-Erev-Import-Id']}", world.author)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _match(done: Mapping[str, Any], source_column: str) -> dict[str, Any]:
    (found,) = [item for item in done["header_match"] if item["source_column"] == source_column]
    return dict(found)


def test_alias_profile_maps_headers(world: ProfileWorld) -> None:
    profile = _published(world, {"aliases": {"Order Ref": "external_id"}})
    assert profile["mappings"] == {
        "aliases": {"Order Ref": "external_id"},
        "constants": {},
        "custom_attributes": [],
    }
    headers = ["Order Ref", *[name for name in REQUIRED if name != "external_id"]]
    content = _csv(headers, [[REQUIRED["external_id"], *list(REQUIRED.values())[1:]]])
    done = _validated(world, content, profile["id"])
    assert done["status"] == "VALIDATED", done
    # REQ-DAT-013; E-119: the source header "Order Ref" is the template field through the profile.
    assert _match(done, "Order Ref") == {
        "source_column": "Order Ref",
        "samples": ["SF-ORD-50001"],
        "template_field": "external_id",
        "match": "ALIAS",
        "alias_profile_code": "SF-EXPORT",
    }
    assert _match(done, "transaction_currency")["match"] == "EXACT"
    assert [item for item in done["header_match"] if item["match"] == "MISSING"] == []


def test_constants_and_custom_attributes(world: ProfileWorld) -> None:
    profile = _published(
        world,
        {"constants": {"transaction_currency": "USD"}, "custom_attributes": ["Region Code"]},
    )
    headers = [name for name in REQUIRED if name != "transaction_currency"] + ["Region Code"]
    values = [value for name, value in REQUIRED.items() if name != "transaction_currency"]
    done = _validated(world, _csv(headers, [[*values, "EMEA"]]), profile["id"])
    assert (done["status"], done["counts"]["valid"]) == ("VALIDATED", 1), done
    (row,) = world.imports.rows(
        select(import_row.c.normalized).where(import_row.c.import_upload_id == UUID(done["id"]))
    )
    assert row["normalized"]["transaction_currency"] == "USD"
    assert row["normalized"]["custom_attributes"] == {"Region Code": "EMEA"}
    assert _match(done, "Region Code") == {
        "source_column": "Region Code",
        "samples": ["EMEA"],
        "template_field": None,
        "match": "NOT_MAPPED",
        "alias_profile_code": None,
    }
    assert "transaction_currency" not in {
        item["template_field"] for item in done["header_match"] if item["match"] == "MISSING"
    }


def test_unpublished_profile_refused(world: ProfileWorld) -> None:
    profile = _created(world, {"aliases": {"Order Ref": "external_id"}})
    refused = _import(world, _csv(list(REQUIRED), [list(REQUIRED.values())]), profile["id"])
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    assert [(error["field"], error["rule_id"]) for error in refused.json()["errors"]] == [
        ("mapping_profile_id", "REQ-DAT-013")
    ]
    assert refused.json()["errors"][0]["message"] == (
        "Mapping profile SF-EXPORT version 1 is not published. Choose a published version."
    )


def test_profile_needs_other_approver(world: ProfileWorld) -> None:
    profile = _submitted(world, {"aliases": {"Order Ref": "external_id"}})
    request_id = str(profile["approval_request_id"])
    own = approve(world.app, request_id, world.author)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    shown = get(world.app, f"{PROFILES}/{profile['id']}", world.author)
    assert shown.json()["status"] == "SUBMITTED"

    decided = approve(world.app, request_id, world.approver)
    assert decided.status_code == 200, decided.text
    published = get(world.app, f"{PROFILES}/{profile['id']}", world.author).json()
    assert (published["status"], published["approval_request_id"]) == ("PUBLISHED", request_id)
    assert published["published_at"] is not None
