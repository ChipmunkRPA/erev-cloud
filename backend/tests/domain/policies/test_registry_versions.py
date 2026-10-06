"""Tenant accounting policy set: the catalogue, registry versions, resolution and the lifecycle (04
T-PLT-31, T-PLT-32, §15.3 API-R-13, §16.5; POLICIES §0.5, §1.12; dev-guide DG-KRN-REG-01,
DG-KRN-REG-04, DG-KRN-REG-06; PRD BR-POL-01, SM-04, ERR-75; 03 REQ-POL-004, REQ-POL-007,
REQ-POL-011, REQ-REF-016; CTL-031; BUILD_SPEC RFD-11).

Maya holds Revenue Accountant (``config.author``, ``masterdata.maintain``) and authors versions;
Marcus holds Controller (``config.approve``), is enrolled in MFA and approves them (``policies``
fixture). AVM-US (New York) and AVM-DE (Berlin) share a monthly calendar for 2026 and 2027. The
worker is simulated: a test marks the job's Procrastinate task as fetched and runs
``jobs.registry.run_job``. The frozen clock reads 2026-09-12T12:00Z, inside September 2026.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    job,
    registry_version,
)
from erev_api.db.tables.platform import registry_parameter_correction
from erev_api.domain.policies import lifecycle, registry_versions
from erev_api.enums import BookCode, RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.registry.effective import EFFECTIVE_REGISTRY_PARAMETER
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.resolve import resolve
from sqlalchemy import func, insert, select, text
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.reference import PERIODS, calendar, entity, fields, periods, post, slug
from support.rows import insert_registry_version, publish_registry_version

if TYPE_CHECKING:
    from conftest import Policies

POLICIES = "/api/v1/policies"
RESOLVE = f"{POLICIES}/resolve"
PARAMETERS = "/api/v1/registry/parameters"
JOBS = "/api/v1/jobs"
APPROVALS = "/api/v1/approvals"
PUBLISHED_AT = datetime(2026, 9, 1, tzinfo=UTC)
# 00:00 on 1 October 2026 in New York (EDT) is 06:00 in Berlin: the first day of October for both.
OCTOBER = "2026-10-01T04:00:00Z"
SEPTEMBER_20 = "2026-09-20T12:00:00Z"
EXPEDIENTS: Mapping[str, str] = {
    "costs.obtain_expedient": "DO_NOT_APPLY",
    "rpo.exemption_original_duration_one_year": "APPLY",
    "sfc.one_year_expedient": "DO_NOT_APPLY",
}
KERNEL_LEVELS: Mapping[str, str] = {
    "B": "BOOK",
    "E": "ENTITY",
    "T": "TENANT",
    "DEFAULT": "FRAMEWORK_DEFAULT",
}
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@dataclass(frozen=True, slots=True)
class World:
    policies: Policies
    us_id: UUID
    de_id: UUID

    @property
    def tenant_id(self) -> UUID:
        return self.policies.tenant_id


@pytest.fixture
def world(policies: Policies) -> World:
    calendar_id = calendar(policies.app, policies.maya, years=(2026, 2027))
    us = entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    de = entity(
        policies.app,
        policies.maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )
    return World(policies=policies, us_id=UUID(str(us["id"])), de_id=UUID(str(de["id"])))


def created(world: World, **body: Any) -> dict[str, Any]:
    response = world.policies.post(POLICIES, body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def shown(world: World, version_id: str) -> dict[str, Any]:
    response = world.policies.get(f"{POLICIES}/{version_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def work(world: World, job_id: str) -> dict[str, Any]:
    """The worker fetches the job's task and runs it; returns API-S-Job."""
    policies = world.policies
    runtime = JobRuntime(
        clock=policies.clock,
        keyring=policies.keyring,
        files=LocalFileStore(policies.settings.file_root),
    )
    with tenant_session(context(world.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == UUID(job_id))
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(UUID(job_id), world.tenant_id, attempt=1, runtime=runtime)
    response = policies.get(f"{JOBS}/{job_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def pass_tests(world: World, version_id: str) -> dict[str, Any]:
    requested = world.policies.post(f"{POLICIES}/{version_id}/test", {})
    assert requested.status_code == 202, requested.text
    finished = work(world, str(requested.json()["id"]))
    assert finished["state"] == "SUCCEEDED", finished
    current = shown(world, version_id)
    assert current["status"] == "TESTED", current
    return current


def submitted(world: World, version_id: str) -> dict[str, Any]:
    response = world.policies.post(f"{POLICIES}/{version_id}/submit", {"comment": "Ready"})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def published(world: World, **body: Any) -> dict[str, Any]:
    """A version created, tested and submitted by Maya and approved, so published, by Marcus."""
    version = created(world, **body)
    pass_tests(world, version["id"])
    request_id = str(submitted(world, version["id"])["approval_request_id"])
    approved = world.policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    current = shown(world, version["id"])
    assert current["status"] == "PUBLISHED", current
    return current


def resolved(world: World, **params: str) -> dict[str, Any]:
    response = world.policies.get(RESOLVE, **params)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def outcome(body: Mapping[str, Any]) -> tuple[Any, str, str | None, bool]:
    return (body["value"], body["level"], body["source"]["id"], body["is_forced"])


def links(body: Mapping[str, Any]) -> list[tuple[str, bool, str | None]]:
    return [(link["level"], link["found"], link["source_id"]) for link in body["chain"]]


def kernel(
    world: World,
    code: str,
    *,
    known_at: datetime,
    book_code: BookCode = BookCode.ASC606,
    entity_id: UUID | None = None,
) -> tuple[Any, str]:
    """``registry.resolve`` in a tenant session: value and level name."""
    with tenant_session(context(world.tenant_id), read_only=True) as session:
        found = resolve(session, code, book_code=book_code, entity_id=entity_id, known_at=known_at)
    return found.value, KERNEL_LEVELS[found.level]


def default_version_id(world: World, category: RegistryCategory) -> str:
    rows = world.policies.rows(
        select(registry_version.c.id).where(
            registry_version.c.category == category.value,
            registry_version.c.scope == RegistryScope.TENANT.value,
            registry_version.c.version_no == 1,
        )
    )
    return str(rows[0]["id"])


def publish_row(world: World, **values: Any) -> str:
    with tenant_session(context(world.tenant_id)) as session:
        version_id = publish_registry_version(
            session, tenant_id=world.tenant_id, at=PUBLISHED_AT, **values
        )
    return str(version_id)


RETENTION_CODE = "platform.snapshot_retention_families"
# (section, description) of the two corrections the fixture appends; their numbers are relative to
# the catalogue's latest correction at the time (append-only: the test repeats in any order).
_CORRECTIONS = (
    ("Corrected once", "First correction of the retention description."),
    ("Corrected twice", "Latest correction: retention families per copied family."),
)
_APPENDED_BY: Mapping[str, str] = {"applied_by_revision": "tests", "created_by_kind": "SYSTEM"}


def _effective_retention(owner: Any) -> tuple[str, str]:
    """(section, description) the API advertises for the retention code (T-PLT-31 rule 3)."""
    row = owner.execute(
        select(
            EFFECTIVE_REGISTRY_PARAMETER.c.section, EFFECTIVE_REGISTRY_PARAMETER.c.description
        ).where(EFFECTIVE_REGISTRY_PARAMETER.c.code == RETENTION_CODE)
    ).one()
    return str(row.section), str(row.description)


def _latest_correction_no(owner: Any) -> int:
    number = owner.execute(
        select(func.max(registry_parameter_correction.c.correction_no)).where(
            registry_parameter_correction.c.code == RETENTION_CODE
        )
    ).scalar_one()
    assert number is not None, "0066 seeds correction 1 of the retention parameter"
    return int(number)


def _append_correction(owner: Any, number: int, *, section: str, description: str) -> None:
    spec = PLATFORM_PARAMETERS[RETENTION_CODE]
    owner.execute(
        insert(registry_parameter_correction).values(
            code=RETENTION_CODE,
            correction_no=number,
            value_schema=spec.value_schema,
            description=description,
            source_ref=spec.source_ref,
            section=section,
            **_APPENDED_BY,
        )
    )


@pytest.fixture
def corrected_retention_catalogue(test_database: TestDatabase) -> Iterator[None]:
    """Two corrections of the retention parameter appended as erev_owner (a governed revision would
    append them) and RESTORED append-only, migration-free: the cleanup appends one more correction
    restating the catalogue's spec, so the effective row the API reads returns to the seeded values
    while T-PLT-47 keeps its history (DB-01; the numbers are relative to the latest correction, so
    the test repeats in any order). The precondition refuses a polluted catalogue by name instead
    of colliding on the keys. The earlier isolation through the migration boundary (downgrade to
    0065, upgrade to head; Codex 0515 / 0533) was retired at batch #6 on 9e7d1031: 0067's
    downgrade is refused on data once OPENING_BALANCES batches without a cutover exist, which the
    shared database holds after tests/api (F-SNP record §14.4)."""
    spec = PLATFORM_PARAMETERS[RETENTION_CODE]
    with test_database.owner_engine.begin() as owner:
        advertised, _ = _effective_retention(owner)
        assert advertised == spec.section, f"catalogue polluted before the test: {advertised}"
        base = _latest_correction_no(owner)
        for offset, (section, description) in enumerate(_CORRECTIONS, start=1):
            _append_correction(owner, base + offset, section=section, description=description)
    try:
        yield
    finally:
        with test_database.owner_engine.begin() as owner:
            _append_correction(
                owner,
                base + len(_CORRECTIONS) + 1,
                section=spec.section,
                description=spec.description,
            )
            restored = _effective_retention(owner)
        if restored != (spec.section, spec.description):
            raise RuntimeError(f"catalogue not restored after the correction test: {restored}")


def test_parameters_catalogue_advertises_corrections(
    policies: Policies, corrected_retention_catalogue: None
) -> None:
    """04 rev 1.59 T-PLT-31 rule 3 / API-R-13 (lane F-SNP; written NOT RUN on the lane — databases
    Ray-side): the list, its section filter, its q search and its pagination all read the effective
    relation. Two corrections of one code (the latest wins), fallback for every other code, a
    changed section reached by the filter, a changed description found by q, and one row per code
    with unchanged totals. The catalogue oracle of test_parameters_catalogue is untouched: the
    fixture restores the effective catalogue (a restoring correction) after this test, pass or
    fail."""
    code = RETENTION_CODE
    spec = PLATFORM_PARAMETERS[code]
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    while True:
        params = {"limit": "100"} if cursor is None else {"limit": "100", "cursor": cursor}
        page = policies.get(PARAMETERS, **params)
        assert page.status_code == 200, page.text
        items += page.json()["items"]
        cursor = page.json()["next_cursor"]
        pages += 1
        if cursor is None:
            break
    by_code = {item["code"]: item for item in items}
    assert pages == 2 and len(items) == len(by_code) == 155  # one row per code, totals unchanged
    assert [item["code"] for item in items] == sorted(by_code)  # code order
    latest = by_code[code]
    assert latest["section"] == "Corrected twice"  # the latest correction wins
    assert latest["description"].startswith("Latest correction")
    assert latest["value_schema"] == spec.value_schema
    assert latest["pin"] == spec.pin and latest["approval_code"] == spec.approval_code  # seed
    other = by_code["ai.enabled"]  # fallback: a code without corrections shows its seed
    assert other["section"] == PLATFORM_PARAMETERS["ai.enabled"].section
    assert other["description"] == PLATFORM_PARAMETERS["ai.enabled"].description
    filtered = policies.get(PARAMETERS, section="Corrected twice")
    assert filtered.status_code == 200, filtered.text
    assert [item["code"] for item in filtered.json()["items"]] == [code]
    stale = policies.get(PARAMETERS, section="Corrected once")
    assert stale.status_code == 200 and stale.json()["items"] == []  # superseded, not advertised
    searched = policies.get(PARAMETERS, q="Latest correction")
    assert searched.status_code == 200, searched.text
    assert [item["code"] for item in searched.json()["items"]] == [code]
    old_text = policies.get(PARAMETERS, q="confirms nothing")  # the seed's description
    assert old_text.status_code == 200 and old_text.json()["items"] == []


def test_parameters_catalogue(policies: Policies) -> None:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    while True:
        params = {"limit": "100"} if cursor is None else {"limit": "100", "cursor": cursor}
        page = policies.get(PARAMETERS, **params)
        assert page.status_code == 200, page.text
        items += page.json()["items"]
        cursor = page.json()["next_cursor"]
        pages += 1
        if cursor is None:
            break
    by_code = {item["code"]: item for item in items}
    assert pages == 2
    # 131 POL + 24 platform parameters (the 24th: platform.snapshot_retention_families, F-SNP).
    assert len(items) == len(by_code) == 155
    assert set(by_code) == set(POLICY_PARAMETERS) | set(PLATFORM_PARAMETERS)
    assert len(POLICY_PARAMETERS) == 131
    billing = by_code["billing.posting"]
    assert (
        billing["pol_id"],
        billing["category"],
        billing["value_schema"],
        billing["default_asc606"],
        billing["default_ifrs15"],
        billing["legacy_parity_value"],
        billing["is_forced_asc606"],
        billing["is_forced_ifrs15"],
        billing["allowed_levels"],
        billing["pin"],
        billing["approval_code"],
        billing["section"],
    ) == (
        "POL-004",
        "ACCOUNTING_POLICY",
        {"type": "string", "enum": ["ERP", "ENGINE"]},
        "ERP",
        "ERP",
        "ERP",
        False,
        False,
        ["TENANT"],
        "P",
        "CFG",
        "Platform, books, posting and rounding",
    )
    outside = by_code["ssp.outside_range_point"]
    assert (outside["pol_id"], outside["default_asc606"], outside["pin"]) == (
        "POL-072",
        "NEAREST_BOUND",
        "K",
    )
    for code, spec in PLATFORM_PARAMETERS.items():
        item = by_code[code]
        assert (
            item["pol_id"],
            item["category"],
            item["default_asc606"],
            item["legacy_parity_value"],
            item["allowed_levels"],
            item["pin"],
            item["approval_code"],
            item["section"],
        ) == (
            None,
            spec.category.value,
            spec.default_asc606,
            spec.legacy_parity_value,
            ["TENANT"],
            "P",
            "CFG",
            "Platform",
        )
    for code, policy in POLICY_PARAMETERS.items():
        item = by_code[code]
        assert (item["pol_id"], item["default_asc606"], sorted(item["allowed_levels"])) == (
            policy.pol_id,
            policy.default_asc606,
            sorted(level.value for level in policy.allowed_levels),
        )
    platform = policies.get(PARAMETERS, category="PLATFORM", limit="500")
    assert platform.status_code == 200, platform.text
    assert {item["code"] for item in platform.json()["items"]} == {
        code
        for code, spec in {**POLICY_PARAMETERS, **PLATFORM_PARAMETERS}.items()
        if spec.category is RegistryCategory.PLATFORM
    }
    searched = policies.get(PARAMETERS, q="billing.posting")
    assert [item["code"] for item in searched.json()["items"]] == ["billing.posting"]
    unknown = policies.get(PARAMETERS, category="RETIRED")
    assert (unknown.status_code, fields(unknown)) == (422, [("category", "API-C-09")])


def test_resolution_levels(world: World) -> None:
    policies = world.policies
    default_id = default_version_id(world, RegistryCategory.ACCOUNTING_POLICY)
    before = resolved(world, key="billing.posting", entity="AVM-US", book="ASC606")
    assert (before["key"], before["known_at"], before["source"]["type"]) == (
        "billing.posting",
        "2026-09-12T12:00:00Z",
        "framework_default",
    )
    assert outcome(before) == ("ERP", "FRAMEWORK_DEFAULT", None, False)
    assert links(before) == [("TENANT", False, default_id), ("FRAMEWORK_DEFAULT", True, None)]

    tenant_id = publish_row(
        world, category=RegistryCategory.ACCOUNTING_POLICY, values={"billing.posting": "ENGINE"}
    )
    engine = resolved(world, key="billing.posting", entity="AVM-US", book="ASC606")
    assert (engine["source"]["type"], outcome(engine)) == (
        "registry_version",
        ("ENGINE", "TENANT", tenant_id, False),
    )
    assert links(engine) == [("TENANT", True, tenant_id)]

    # L3-1-Q-1: POL-004 allows level T only, so an ENTITY version for AVM-DE is refused, and a
    # stored ENTITY row holding the key is skipped: AVM-DE resolves ENGINE at TENANT.
    refused = policies.post(
        POLICIES,
        {
            "category": "ACCOUNTING_POLICY",
            "scope": "ENTITY",
            "entity_code": "AVM-DE",
            "values": {"billing.posting": "ERP"},
        },
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "policy-level-not-allowed",
        [("values.billing.posting", "POLICY_LEVEL_NOT_ALLOWED")],
    )
    de_id = publish_row(
        world,
        category=RegistryCategory.ACCOUNTING_POLICY,
        scope=RegistryScope.ENTITY,
        entity_id=world.de_id,
        values={"billing.posting": "ERP", "je.posting_mode": "DELTA"},
    )
    for code in ("AVM-DE", "AVM-US", str(world.de_id)):
        skipped = resolved(world, key="billing.posting", entity=code, book="ASC606")
        assert outcome(skipped) == ("ENGINE", "TENANT", tenant_id, False)
        assert links(skipped) == [("TENANT", True, tenant_id)]

    # The ENTITY level answers for a key whose levels include E (POL-005 je.posting_mode: T, E).
    german = resolved(world, key="je.posting_mode", entity="AVM-DE", book="ASC606")
    assert outcome(german) == ("DELTA", "ENTITY", de_id, False)
    assert links(german) == [("ENTITY", True, de_id)]
    american = resolved(world, key="je.posting_mode", entity="AVM-US", book="ASC606")
    assert outcome(american) == ("GROSS", "FRAMEWORK_DEFAULT", None, False)
    assert links(american) == [
        ("ENTITY", False, None),
        ("TENANT", False, tenant_id),
        ("FRAMEWORK_DEFAULT", True, None),
    ]
    tenant_wide = resolved(world, key="je.posting_mode")
    assert links(tenant_wide) == [("TENANT", False, tenant_id), ("FRAMEWORK_DEFAULT", True, None)]

    # The route answers what registry.resolve answers (DG-KRN-REG-01).
    for code, entity_id, body in (
        ("billing.posting", world.us_id, engine),
        ("billing.posting", world.de_id, skipped),
        ("je.posting_mode", world.de_id, german),
        ("je.posting_mode", world.us_id, american),
    ):
        assert kernel(world, code, known_at=FROZEN_AT, entity_id=entity_id) == (
            body["value"],
            body["level"],
        )
    # Before the versions were published, the defaults answer.
    earlier = resolved(world, key="billing.posting", known_at="2026-08-31T00:00:00Z")
    assert outcome(earlier) == ("ERP", "FRAMEWORK_DEFAULT", None, False)


def test_resolve_refusals(world: World) -> None:
    policies = world.policies
    # CTR-15: an unknown contract, and an obligation without its contract, are refused.
    unknown = policies.get(RESOLVE, key="billing.cadence", entity="AVM-XX", contract="K-11")
    assert (unknown.status_code, fields(unknown)) == (
        422,
        [("key", "T-PLT-31"), ("contract", "T-CON-01"), ("entity", "T-REF-01")],
    )
    obligation = policies.get(RESOLVE, key="billing.posting", obligation="POB #1")
    assert fields(obligation) == [("obligation", "T-CON-10")]
    naive = policies.get(RESOLVE, key="billing.posting", known_at="2026-09-12T12:00:00")
    assert naive.status_code == 422, naive.text
    forced = resolved(world, key="rounding.posting_mode", book="IFRS15")
    assert outcome(forced) == ("HALF_UP", "FRAMEWORK_DEFAULT", None, True)
    assert links(forced) == [("FRAMEWORK_DEFAULT", True, None)]


def test_scope_key_refusals(world: World) -> None:
    policies = world.policies
    base = {"category": "ACCOUNTING_POLICY", "values": {"je.posting_mode": "DELTA"}}
    cases = (
        ({"scope": "ENTITY"}, [("entity_code", "T-PLT-32")]),
        ({"scope": "ENTITY", "entity_code": "AVM-XX"}, [("entity_code", "T-REF-01")]),
        (
            {"scope": "TENANT", "entity_code": "AVM-US", "book": "ASC606"},
            [
                ("entity_code", "T-PLT-32"),
                ("book", "T-PLT-32"),
            ],
        ),
        ({"scope": "BOOK"}, [("book", "T-PLT-32")]),
        ({"scope": "PRODUCT"}, [("scope", "T-PLT-32")]),
    )
    for body, expected in cases:
        refused = policies.post(POLICIES, {**base, **body})
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            expected,
        ), body
    assert (
        policies.rows(select(registry_version.c.id).where(registry_version.c.version_no > 1)) == []
    )


def test_level_not_allowed(world: World) -> None:
    policies = world.policies
    refused = policies.post(
        POLICIES,
        {
            "category": "ACCOUNTING_POLICY",
            "scope": "BOOK",
            "book": "ASC606",
            "values": {"rpo.time_bands": [12, 24, 36]},
        },
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "policy-level-not-allowed",
        [("values.rpo.time_bands", "POLICY_LEVEL_NOT_ALLOWED")],
    )
    assert refused.json()["errors"][0]["message"] == "This parameter cannot be set at BOOK level."
    # POL-201 allows T and E.
    tenant = created(
        world, category="ACCOUNTING_POLICY", scope="TENANT", values={"rpo.time_bands": [12, 24, 36]}
    )
    assert (tenant["status"], tenant["version_no"], tenant["book"], tenant["entity_code"]) == (
        "DRAFT",
        2,
        None,
        None,
    )
    # A stored BOOK row with the key fails the test request before any job (DG-KRN-REG-06).
    with tenant_session(context(world.tenant_id)) as session:
        book_id = insert_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.BOOK,
            book_code=BookCode.ASC606,
            values={"rpo.time_bands": [12]},
            version_no=1,
        )
    requested = policies.post(f"{POLICIES}/{book_id}/test", {})
    assert (requested.status_code, slug(requested)) == (422, "policy-level-not-allowed")
    assert policies.rows(select(job.c.id).where(job.c.subject_id == book_id)) == []


def test_invalid_literal(world: World) -> None:
    policies = world.policies
    refused = policies.post(
        POLICIES,
        {
            "category": "ACCOUNTING_POLICY",
            "scope": "TENANT",
            "values": {"billing.posting": "SOMETIMES"},
        },
    )
    assert (refused.status_code, slug(refused), fields(refused)) == (
        422,
        "validation-failed",
        [("values.billing.posting", "POLICY_VALUE_INVALID")],
    )
    assert refused.json()["errors"][0]["message"] == (
        "Values.billing.posting must be one of ERP, ENGINE."
    )
    listed = policies.get(POLICIES, category="ACCOUNTING_POLICY", scope="TENANT")
    assert listed.status_code == 200, listed.text
    assert [
        (item["version_no"], item["status"], item["preset_code"], item["created_by"]["kind"])
        for item in listed.json()["items"]
    ] == [(1, "PUBLISHED", "DEFAULT", "SYSTEM")]
    other = policies.post(
        POLICIES,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "TENANT",
            "values": {"billing.posting": "ERP"},
        },
    )
    assert (other.status_code, fields(other)) == (
        422,
        [("values.billing.posting", "POLICY_VALUE_INVALID")],
    )
    assert (
        other.json()["errors"][0]["message"] == "Use a parameter of category PRACTICAL_EXPEDIENT."
    )


def test_us_only_flag_forced_in_ifrs15(world: World) -> None:
    policies = world.policies
    for value in ("TRUE", "FALSE"):
        refused = policies.post(
            POLICIES,
            {
                "category": "PRACTICAL_EXPEDIENT",
                "scope": "BOOK",
                "book": "IFRS15",
                "values": {"pob.shipping_as_fulfilment": value},
            },
        )
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [("values.pob.shipping_as_fulfilment", "POLICY_VALUE_INVALID")],
        )
        assert refused.json()["errors"][0]["message"] == (
            "The framework fixes this value in the IFRS15 book."
        )
    # In the ASC606 book the flag is not forced, and BOOK is not among its levels (T, E, P).
    american_book = policies.post(
        POLICIES,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "BOOK",
            "book": "ASC606",
            "values": {"pob.shipping_as_fulfilment": "TRUE"},
        },
    )
    assert slug(american_book) == "policy-level-not-allowed"
    # A TENANT election applies to ASC606; IFRS15 keeps the forced FALSE (REQ-POL-011).
    tenant_id = publish_row(
        world,
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        values={"pob.shipping_as_fulfilment": "TRUE"},
    )
    asc606 = resolved(world, key="pob.shipping_as_fulfilment", entity="AVM-US", book="ASC606")
    assert outcome(asc606) == ("TRUE", "TENANT", tenant_id, False)
    ifrs15 = resolved(world, key="pob.shipping_as_fulfilment", entity="AVM-US", book="IFRS15")
    assert outcome(ifrs15) == ("FALSE", "FRAMEWORK_DEFAULT", None, True)
    assert links(ifrs15) == [("FRAMEWORK_DEFAULT", True, None)]


def test_expedient_flags_publish_through_approval(world: World) -> None:
    policies = world.policies
    # L3-1-Q-1: POL-197 allows level E only, so the three flags form an ENTITY version of AVM-US.
    tenant = policies.post(
        POLICIES, {"category": "PRACTICAL_EXPEDIENT", "scope": "TENANT", "values": dict(EXPEDIENTS)}
    )
    assert (tenant.status_code, slug(tenant), fields(tenant)) == (
        422,
        "policy-level-not-allowed",
        [("values.rpo.exemption_original_duration_one_year", "POLICY_LEVEL_NOT_ALLOWED")],
    )
    version = created(
        world,
        category="PRACTICAL_EXPEDIENT",
        scope="ENTITY",
        entity_code="AVM-US",
        values=dict(EXPEDIENTS),
        effective_from=OCTOBER,
    )
    assert (
        version["status"],
        version["version_no"],
        version["entity_code"],
        version["entity_id"],
        version["book"],
        version["effective_from"],
        version["test_evidence"],
        version["impact_simulation"],
        version["supersedes_version_id"],
        version["created_by"]["id"],
        version["row_version"],
    ) == (
        "DRAFT",
        1,
        "AVM-US",
        str(world.us_id),
        None,
        OCTOBER,
        None,
        None,
        None,
        str(policies.maya.member.user_id),
        1,
    )
    assert version["diff_against_current"] == [
        {"code": code, "before": None, "after": value, "change": "ADDED"}
        for code, value in sorted(EXPEDIENTS.items())
    ]

    requested = policies.post(f"{POLICIES}/{version['id']}/test", {})
    assert requested.status_code == 202, requested.text
    queued = requested.json()
    assert (queued["kind"], queued["state"], requested.headers["Location"]) == (
        "POLICY_SIMULATION",
        "QUEUED",
        f"{JOBS}/{queued['id']}",
    )
    assert shown(world, version["id"])["status"] == "DRAFT"
    finished = work(world, str(queued["id"]))
    assert finished["state"] == "SUCCEEDED", finished
    assert (finished["result"]["href"], finished["result"]["counts"]) == (
        f"/api/v1/policies/{version['id']}",
        {"parameters": 3, "contracts_affected": 0},
    )
    current = shown(world, version["id"])
    assert current["status"] == "TESTED"
    assert (
        current["test_evidence"]["result"],
        current["test_evidence"]["parameters"],
        current["test_evidence"]["content_sha256"],
    ) == ("PASS", 3, current["content_sha256"])
    assert current["impact_simulation"]["summary"] == {
        "contracts_affected": 0,
        "revenue_delta_by_period": [],
        "balance_delta": [],
        "journal_delta": [],
        "statement": "No contracts affected",
    }

    sent = submitted(world, version["id"])
    request_id = str(sent["approval_request_id"])
    assert (sent["status"], sent["pending_approval_request_id"]) == ("SUBMITTED", request_id)
    detail = policies.get(f"{APPROVALS}/{request_id}", policies.marcus)
    assert detail.status_code == 200, detail.text
    assert [step["required_permission"] for step in detail.json()["steps"]] == ["config.approve"]
    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    final = shown(world, version["id"])
    assert (
        final["status"],
        final["approval_request_id"],
        final["pending_approval_request_id"],
        final["published_by"]["id"],  # API-S-Actor (04 rev 1.139)
        final["effective_from"],
        final["effective_to"],
    ) == ("PUBLISHED", request_id, None, str(policies.marcus.member.user_id), OCTOBER, None)

    defaults = {code: POLICY_PARAMETERS[code].default_asc606 for code in EXPEDIENTS}
    assert defaults == {
        "costs.obtain_expedient": "APPLY",
        "rpo.exemption_original_duration_one_year": "DO_NOT_APPLY",
        "sfc.one_year_expedient": "APPLY",
    }
    for code in EXPEDIENTS:
        early = resolved(world, key=code, entity="AVM-US", known_at=SEPTEMBER_20)
        assert outcome(early) == (defaults[code], "FRAMEWORK_DEFAULT", None, False)
        effective = resolved(world, key=code, entity="AVM-US", known_at=OCTOBER)
        assert outcome(effective) == (EXPEDIENTS[code], "ENTITY", version["id"], False)
    events = policies.rows(
        select(audit_event.c.action)
        .where(audit_event.c.object_id == UUID(version["id"]))
        .order_by(audit_event.c.chain_seq)
    )
    assert [event["action"] for event in events] == [
        "registry_version.create",
        "registry_version.test_requested",
        "registry_version.tested",
        "registry_version.submitted",
        "registry_version.approved",
        "registry_version.published",
    ]


def test_period_pinned_effective_from_future_open_period(world: World) -> None:
    policies = world.policies
    states = {
        item["period"]["period_key"]: item
        for item in periods(policies.app, policies.maya, entity="AVM-US")
    }
    # Periods open in order (PRD SM-07 guard "Previous period not future"; supervisor ruling
    # R-58 (d)): January to September, where this test opened September alone until that ruling.
    for month in range(1, 10):
        opened = post(
            policies.app,
            f"{PERIODS}/{states[f'FY2026-P{month:02d}']['id']}/open",
            policies.maya,
            {"comment": "Setup"},
            if_match='"r1"',
        )
        assert opened.status_code == 200, opened.text
    body = {
        "category": "PRACTICAL_EXPEDIENT",
        "scope": "ENTITY",
        "entity_code": "AVM-US",
        "values": {"rpo.exemption_original_duration_one_year": "APPLY"},
    }
    # Inside the open September period, its first day (already started), and mid-October.
    for effective_from in ("2026-09-15T04:00:00Z", "2026-09-01T04:00:00Z", "2026-10-15T04:00:00Z"):
        refused = policies.post(POLICIES, {**body, "effective_from": effective_from})
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [("effective_from", "T-PLT-32")],
        ), effective_from
        assert refused.json()["errors"][0]["message"] == registry_versions.PERIOD_START_REQUIRED
    version = created(world, **body, effective_from=OCTOBER)
    moved = policies.patch(
        f"{POLICIES}/{version['id']}", {"effective_from": "2026-09-15T04:00:00Z"}, etag='"r1"'
    )
    assert (moved.status_code, fields(moved)) == (422, [("effective_from", "T-PLT-32")])
    # A version without period-scoped parameters takes any effective date (pin K).
    contract_pinned = created(
        world,
        category="PRACTICAL_EXPEDIENT",
        scope="ENTITY",
        entity_code="AVM-DE",
        values={"sfc.one_year_expedient": "DO_NOT_APPLY"},
        effective_from="2026-09-15T00:00:00Z",
    )
    assert contract_pinned["status"] == "DRAFT"


def test_nonpublic_elections_need_nonpublic_entity(world: World) -> None:
    policies = world.policies
    base = {"category": "DISCLOSURE_ELECTION", "scope": "ENTITY", "entity_code": "AVM-US"}
    for values in (
        {"entity.reporting_type": "PBE", "disclosure.nonpublic_rpo_relief": "ELECT"},
        {"disclosure.nonpublic_rpo_relief": "ELECT"},
    ):
        refused = policies.post(POLICIES, {**base, "values": values})
        assert (refused.status_code, slug(refused), fields(refused)) == (
            422,
            "validation-failed",
            [("values.disclosure.nonpublic_rpo_relief", "POLICY_VALUE_INVALID")],
        )
        assert refused.json()["errors"][0]["message"] == registry_versions.NONPUBLIC_REQUIRED
    accepted = created(
        world,
        **base,
        values={"entity.reporting_type": "NONPUBLIC", "disclosure.nonpublic_rpo_relief": "ELECT"},
    )
    assert (accepted["status"], accepted["values"]) == (
        "DRAFT",
        {"disclosure.nonpublic_rpo_relief": "ELECT", "entity.reporting_type": "NONPUBLIC"},
    )
    back_to_public = policies.patch(
        f"{POLICIES}/{accepted['id']}",
        {"values": {"entity.reporting_type": "PBE", "disclosure.nonpublic_rpo_relief": "ELECT"}},
        etag='"r1"',
    )
    assert fields(back_to_public) == [
        ("values.disclosure.nonpublic_rpo_relief", "POLICY_VALUE_INVALID")
    ]
    # L3-1-Q-10 as the whole-set rule states it (04 T-PLT-32 rev 1.183; supervisor ruling
    # R-117 (b)): a successor DISCLOSURE_ELECTION version stands on the published one, so it keeps
    # the entity type it does not state. When its values are the whole set (basis DEFAULTS), or
    # when it returns the entity type to the default, the election has no NONPUBLIC entity type
    # to stand on. POL-202, a practical expedient, reads the entity type in force.
    publish_row(
        world,
        category=RegistryCategory.DISCLOSURE_ELECTION,
        scope=RegistryScope.ENTITY,
        entity_id=world.de_id,
        values={"entity.reporting_type": "NONPUBLIC"},
    )
    german_base = {"category": "DISCLOSURE_ELECTION", "scope": "ENTITY", "entity_code": "AVM-DE"}
    election = {"disclosure.nonpublic_cost_relief": "ELECT"}
    for statement in ({"basis": "DEFAULTS"}, {"unset": ["entity.reporting_type"]}):
        unstated = policies.post(POLICIES, {**german_base, "values": election, **statement})
        assert fields(unstated) == [
            ("values.disclosure.nonpublic_cost_relief", "POLICY_VALUE_INVALID")
        ], statement
    german = created(world, **german_base, values=election)
    assert (german["version_no"], german["values"], german["diff_against_current"]) == (
        2,
        election,
        [
            {
                "code": "disclosure.nonpublic_cost_relief",
                "before": None,
                "after": "ELECT",
                "change": "ADDED",
            }
        ],
    )
    franchisor = {
        "category": "PRACTICAL_EXPEDIENT",
        "scope": "ENTITY",
        "values": {"franchisor.preopening_expedient": "ELECT_DISTINCT_SERVICES"},
    }
    american = policies.post(POLICIES, {**franchisor, "entity_code": "AVM-US"})
    assert fields(american) == [("values.franchisor.preopening_expedient", "POLICY_VALUE_INVALID")]
    assert created(world, **franchisor, entity_code="AVM-DE")["status"] == "DRAFT"


def test_reporting_entity_types(world: World) -> None:
    policies = world.policies
    version = created(
        world,
        category="DISCLOSURE_ELECTION",
        scope="ENTITY",
        entity_code="AVM-DE",
        values={"entity.reporting_type": "PBE"},
    )
    etag = '"r1"'
    for literal in ("NFP_CONDUIT", "EBP_SEC", "NONPUBLIC", "PBE"):
        changed = policies.patch(
            f"{POLICIES}/{version['id']}", {"values": {"entity.reporting_type": literal}}, etag=etag
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["values"] == {"entity.reporting_type": literal}
        etag = changed.headers["ETag"]
    assert etag == '"r5"'
    public = policies.patch(
        f"{POLICIES}/{version['id']}", {"values": {"entity.reporting_type": "PUBLIC"}}, etag=etag
    )
    assert (public.status_code, fields(public)) == (
        422,
        [("values.entity.reporting_type", "POLICY_VALUE_INVALID")],
    )
    tenant = policies.post(
        POLICIES,
        {
            "category": "DISCLOSURE_ELECTION",
            "scope": "TENANT",
            "values": {"entity.reporting_type": "NONPUBLIC"},
        },
    )
    assert slug(tenant) == "policy-level-not-allowed"
    events = policies.rows(
        select(audit_event.c.action, audit_event.c.before, audit_event.c.after)
        .where(audit_event.c.object_id == UUID(version["id"]))
        .order_by(audit_event.c.chain_seq)
    )
    assert [event["action"] for event in events] == [
        "registry_version.create",
        *["registry_version.update"] * 4,
    ]
    assert (events[1]["before"], events[1]["after"]) == (
        {"values": {"entity.reporting_type": "PBE"}},
        {"values": {"entity.reporting_type": "NFP_CONDUIT"}},
    )


def test_book_scope_versions_per_book(world: World) -> None:
    effective_from = "2026-10-01T00:00:00Z"
    # [J] L3-1-Q-9: every BOOK-level parameter is forced in one framework, so each book sets the
    # parameter its framework leaves open.
    asc606 = published(
        world,
        category="ACCOUNTING_POLICY",
        scope="BOOK",
        book="ASC606",
        values={"loss.scope": "ALL_CONTRACTS_WITH_EAC"},
        effective_from=effective_from,
    )
    ifrs15 = published(
        world,
        category="ACCOUNTING_POLICY",
        scope="BOOK",
        book="IFRS15",
        values={"licence.renewal_start": "RENEWAL_PERIOD_START"},
        effective_from=effective_from,
    )
    assert [(item["book"], item["version_no"], item["status"]) for item in (asc606, ifrs15)] == [
        ("ASC606", 1, "PUBLISHED"),
        ("IFRS15", 1, "PUBLISHED"),
    ]
    cases = (
        ("loss.scope", "ASC606", ("ALL_CONTRACTS_WITH_EAC", "BOOK", asc606["id"], False)),
        ("loss.scope", "LEGACY", ("SCOPED_605_35_ONLY", "FRAMEWORK_DEFAULT", None, False)),
        ("loss.scope", "IFRS15", ("ALL_CONTRACTS_WITH_EAC", "FRAMEWORK_DEFAULT", None, True)),
        ("licence.renewal_start", "IFRS15", ("RENEWAL_PERIOD_START", "BOOK", ifrs15["id"], False)),
        (
            "licence.renewal_start",
            "ASC606",
            ("RENEWAL_PERIOD_START", "FRAMEWORK_DEFAULT", None, True),
        ),
    )
    for code, book, expected in cases:
        body = resolved(world, key=code, entity="AVM-US", book=book, known_at=effective_from)
        assert outcome(body) == expected, (code, book)
        assert kernel(
            world,
            code,
            known_at=datetime(2026, 10, 1, tzinfo=UTC),
            book_code=BookCode(book),
            entity_id=world.us_id,
        ) == (expected[0], expected[1])
    legacy = resolved(
        world, key="loss.scope", entity="AVM-US", book="LEGACY", known_at=effective_from
    )
    assert links(legacy) == [("BOOK", False, None), ("FRAMEWORK_DEFAULT", True, None)]
    listed = world.policies.get(POLICIES, scope="BOOK", sort="id")
    assert {item["book"] for item in listed.json()["items"]} == {"ASC606", "IFRS15"}


@pytest.mark.control("CTL-031")
def test_ctl_031_policy_version_not_effective_before_approval(world: World) -> None:
    policies = world.policies
    effective_from = "2026-10-01T00:00:00Z"
    later = datetime(2026, 10, 2, tzinfo=UTC)
    version = created(
        world,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={"material_right.exercise": "MODIFICATION"},
        effective_from=effective_from,
    )
    pass_tests(world, version["id"])
    sent = submitted(world, version["id"])
    assert sent["status"] == "SUBMITTED"
    for known_at in (FROZEN_AT, later):
        assert kernel(world, "material_right.exercise", known_at=known_at) == (
            "CONTINUATION",
            "FRAMEWORK_DEFAULT",
        )
    ignored = resolved(world, key="material_right.exercise", known_at="2026-10-02T00:00:00Z")
    assert outcome(ignored) == ("CONTINUATION", "FRAMEWORK_DEFAULT", None, False)
    early = policies.post(f"{POLICIES}/{version['id']}/publish")
    assert (early.status_code, slug(early), fields(early)) == (
        409,
        "invalid-transition",
        [("status", "DB-03")],
    )
    assert shown(world, version["id"])["status"] == "SUBMITTED"

    approved = policies.approve(str(sent["approval_request_id"]))
    assert approved.status_code == 200, approved.text
    assert kernel(world, "material_right.exercise", known_at=later) == ("MODIFICATION", "TENANT")
    effective = resolved(world, key="material_right.exercise", known_at="2026-10-02T00:00:00Z")
    assert outcome(effective) == ("MODIFICATION", "TENANT", version["id"], False)
    again = policies.post(f"{POLICIES}/{version['id']}/publish")
    assert (again.status_code, again.json()["status"]) == (200, "PUBLISHED")


def test_withdraw_returns_to_draft(world: World) -> None:
    policies = world.policies
    version = created(
        world,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={"returns.reversal_rate": "CURRENT_REMAINING_RATE"},
        effective_from="2026-10-01T00:00:00Z",
    )
    pass_tests(world, version["id"])
    sent = submitted(world, version["id"])
    withdrawn = policies.post(f"{POLICIES}/{version['id']}/withdraw", {"comment": "Not yet"})
    assert withdrawn.status_code == 200, withdrawn.text
    body = withdrawn.json()
    assert (
        body["status"],
        body["approval_request_id"],
        body["pending_approval_request_id"],
        body["content_sha256"],
        body["test_evidence"],
        body["impact_simulation"],
    ) == ("DRAFT", None, None, None, None, None)
    request = policies.rows(
        select(approval_request.c.status).where(
            approval_request.c.id == UUID(str(sent["approval_request_id"]))
        )
    )
    assert request == [{"status": "WITHDRAWN"}]
    again = policies.post(f"{POLICIES}/{version['id']}/withdraw", {})
    assert (again.status_code, slug(again)) == (409, "invalid-transition")
    pass_tests(world, version["id"])


def test_submit_needs_effective_from_and_current_tests(world: World) -> None:
    policies = world.policies
    version = created(
        world,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={"returns.reversal_rate": "CURRENT_REMAINING_RATE"},
    )
    draft = policies.post(f"{POLICIES}/{version['id']}/submit", {})
    assert (draft.status_code, slug(draft)) == (409, "invalid-transition")
    pass_tests(world, version["id"])
    undated = policies.post(f"{POLICIES}/{version['id']}/submit", {})
    assert (undated.status_code, fields(undated)) == (422, [("effective_from", "T-PLT-32")])
    changed = policies.patch(
        f"{POLICIES}/{version['id']}", {"effective_from": "2026-10-01T00:00:00Z"}, etag='"r3"'
    )
    assert changed.status_code == 200, changed.text
    stale = policies.post(f"{POLICIES}/{version['id']}/submit", {})
    assert (stale.status_code, fields(stale)) == (409, [("status", "REQ-POL-003")])


def test_test_job_refuses_changed_content(world: World) -> None:
    policies = world.policies
    version = created(
        world,
        category="ACCOUNTING_POLICY",
        scope="TENANT",
        values={"returns.reversal_rate": "CURRENT_REMAINING_RATE"},
    )
    requested = policies.post(f"{POLICIES}/{version['id']}/test", {"run_simulation": False})
    assert requested.status_code == 202, requested.text
    changed = policies.patch(
        f"{POLICIES}/{version['id']}",
        {"values": {"returns.reversal_rate": "AVERAGE_CARRYING_RATE"}},
        etag='"r1"',
    )
    assert changed.status_code == 200, changed.text
    failed = work(world, str(requested.json()["id"]))
    assert (failed["state"], failed["problem"]["status"]) == ("FAILED", 409)
    assert [(error["field"], error["rule_id"]) for error in failed["problem"]["errors"]] == [
        ("status", "REQ-POL-003")
    ]
    current = shown(world, version["id"])
    assert (current["status"], current["content_sha256"], current["test_evidence"]) == (
        "DRAFT",
        None,
        None,
    )
    # Without the simulation the test records no report; submission attaches one.
    requested = policies.post(f"{POLICIES}/{version['id']}/test", {"run_simulation": False})
    assert work(world, str(requested.json()["id"]))["state"] == "SUCCEEDED"
    assert shown(world, version["id"])["impact_simulation"] is None


# PRD ERR-75: the refusal of a superseding version's effective date, at submission and decision.
ERR_75 = (422, "validation-failed", [("effective_from", "REQ-POL-007")])
EXPEDIENT = "sfc.one_year_expedient"  # pin K: any effective date as far as rule 4 goes
SEPTEMBER_1 = datetime(2026, 9, 1, tzinfo=UTC)


def de_expedient(world: World, value: str, effective_from: str) -> dict[str, Any]:
    """A DRAFT version of AVM-DE's practical expedients: a scope without a provisioned version."""
    return created(
        world,
        category="PRACTICAL_EXPEDIENT",
        scope="ENTITY",
        entity_code="AVM-DE",
        values={EXPEDIENT: value},
        effective_from=effective_from,
    )


def de_expedient_published(world: World, value: str, effective_from: str) -> dict[str, Any]:
    version = de_expedient(world, value, effective_from)
    pass_tests(world, version["id"])
    request_id = str(submitted(world, version["id"])["approval_request_id"])
    approved = world.policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    current = shown(world, version["id"])
    assert current["status"] == "PUBLISHED", current
    return current


def de_expedient_versions(world: World) -> list[tuple[int, str, Any, Any]]:
    """(version_no, status, effective_from, effective_to) of AVM-DE's practical expedients."""
    return [
        (row["version_no"], row["status"], row["effective_from"], row["effective_to"])
        for row in world.policies.rows(
            select(
                registry_version.c.version_no,
                registry_version.c.status,
                registry_version.c.effective_from,
                registry_version.c.effective_to,
            )
            .where(
                registry_version.c.category == RegistryCategory.PRACTICAL_EXPEDIENT.value,
                registry_version.c.scope == RegistryScope.ENTITY.value,
                registry_version.c.entity_id == world.de_id,
            )
            .order_by(registry_version.c.version_no)
        )
    ]


def de_answer(world: World, known_at: datetime) -> tuple[Any, str, str | None, bool]:
    return outcome(resolved(world, key=EXPEDIENT, entity="AVM-DE", known_at=known_at.isoformat()))


def redated(world: World, version_id: str, effective_from: str) -> None:
    """Move the effective time of a TESTED version; it is content, so the tests run again."""
    current = shown(world, version_id)
    moved = world.policies.patch(
        f"{POLICIES}/{version_id}",
        {"effective_from": effective_from},
        etag=f'"r{current["row_version"]}"',
    )
    assert moved.status_code == 200, moved.text
    pass_tests(world, version_id)


def test_err_75_a_superseding_policy_version_never_takes_effect_in_the_past(world: World) -> None:
    """The instant form (supervisor ruling R-113 (b)): a registry version answers at the
    ``known_at`` of a computation, so a version that supersedes the published one takes effect at
    the instant of its submission and of its decision, or later — no past instant changes its
    answer. A first version of its scope keeps a free date (1 September here); rule 4 for
    period-scoped parameters stands beside it."""
    policies = world.policies
    first = de_expedient_published(world, "DO_NOT_APPLY", "2026-09-01T00:00:00Z")
    assert first["version_no"] == 1
    published_at = policies.clock.now()
    policies.clock.advance(timedelta(minutes=3))
    now = policies.clock.now()
    earlier = published_at + timedelta(seconds=90)  # after the publication, before now
    second = de_expedient(world, "APPLY", earlier.isoformat())
    pass_tests(world, second["id"])
    refused = policies.post(f"{POLICIES}/{second['id']}/submit", {"comment": "Ready"})
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert [row[:2] for row in de_expedient_versions(world)] == [(1, "PUBLISHED"), (2, "TESTED")]

    redated(world, second["id"], now.isoformat())  # the instant of the submission itself
    request_id = str(submitted(world, second["id"])["approval_request_id"])
    approved = policies.approve(request_id)
    assert approved.status_code == 200, approved.text
    assert de_expedient_versions(world) == [
        (1, "SUPERSEDED", SEPTEMBER_1, now),
        (2, "PUBLISHED", now, None),
    ]
    # Every instant before the decision keeps the answer it gave; the new version answers from
    # its own instant on.
    for known_at in (earlier, now - timedelta(seconds=1)):
        assert de_answer(world, known_at) == ("DO_NOT_APPLY", "ENTITY", first["id"], False)
    assert de_answer(world, now) == ("APPLY", "ENTITY", second["id"], False)


def test_err_75_a_policy_decision_after_the_effective_time_leaves_the_request_pending(
    world: World,
) -> None:
    policies = world.policies
    first = de_expedient_published(world, "DO_NOT_APPLY", "2026-09-01T00:00:00Z")
    ahead = policies.clock.now() + timedelta(minutes=1)
    second = de_expedient(world, "APPLY", ahead.isoformat())
    pass_tests(world, second["id"])
    request_id = str(submitted(world, second["id"])["approval_request_id"])

    policies.clock.advance(timedelta(minutes=2))  # the decision comes after the effective time
    refused = policies.approve(request_id)
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    # Nothing of the decision is kept: the request is pending and version 1 answers.
    assert policies.rows(
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
    ) == [{"status": "PENDING"}]
    decisions = policies.rows(
        select(approval_decision.c.id).where(
            approval_decision.c.approval_request_id == UUID(request_id)
        )
    )
    assert decisions == []
    assert de_expedient_versions(world) == [
        (1, "PUBLISHED", SEPTEMBER_1, None),
        (2, "SUBMITTED", ahead, None),
    ]
    assert de_answer(world, policies.clock.now()) == ("DO_NOT_APPLY", "ENTITY", first["id"], False)

    # The preparer's way on: withdraw, choose a later time, test and submit again.
    withdrawn = policies.post(f"{POLICIES}/{second['id']}/withdraw", {"comment": "Later"})
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "DRAFT"), withdrawn.text
