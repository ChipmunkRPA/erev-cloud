"""The legacy-parity preset (POLICIES §6.3; 04 T-PLT-32, §16.5; dev-guide DG-KRN-REG-05; PRD
BR-POL-02; 03 REQ-POL-005; BUILD_SPEC RFD-11).

Maya holds Revenue Accountant (``config.author``) and applies the preset; Marcus holds Controller
(``config.approve``), is enrolled in MFA and approves it (``policies`` fixture). The worker is
simulated as in ``test_registry_versions.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import job, registry_version
from erev_api.enums import BookCode, RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.registry import presets
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.registry.resolve import resolve
from sqlalchemy import select, text
from support.reference import calendar, entity, fields, slug

if TYPE_CHECKING:
    from conftest import Policies

POLICIES = "/api/v1/policies"
PRESET = f"{POLICIES}/presets/legacy-parity"
JOBS = "/api/v1/jobs"
OCTOBER = "2026-10-01T04:00:00Z"
# REQ-POL-005 and BUILD_SPEC RFD-11: the named preset values.
NAMED: dict[str, str] = {
    "billing.posting": "ERP",
    "je.posting_mode": "GROSS",
    "material_right.exercise": "MODIFICATION",
    "mod.catch_up_scope": "ALL_POBS_FULL_REALLOCATION",
    "mod.ssp_basis": "LEGACY_CARRIED_PLUS_FILE_VERSION",
    "position.reclass_attribution_key": "CUMULATIVE_SSP_DELIVERED",
    "returns.reversal_rate": "CURRENT_REMAINING_RATE",
    "ssp.inside_range_point": "CONTRACT_PRICE",
    "ssp.outside_range_point": "NEAREST_BOUND",
    "ssp.range_validation": "NOT_ENFORCED",
    "ssp.version_basis": "NAMED_VERSION",
}
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def work(policies: Policies, job_id: str) -> dict[str, Any]:
    """The worker fetches the job's task and runs it; returns API-S-Job."""
    runtime = JobRuntime(
        clock=policies.clock,
        keyring=policies.keyring,
        files=LocalFileStore(policies.settings.file_root),
    )
    with tenant_session(context(policies.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == UUID(job_id))
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(UUID(job_id), policies.tenant_id, attempt=1, runtime=runtime)
    response = policies.get(f"{JOBS}/{job_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def test_legacy_parity_preset_values(policies: Policies) -> None:
    created = policies.post(PRESET, {"scope": "TENANT"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert (created.headers["Location"], created.headers["ETag"]) == (
        f"{POLICIES}/{body['id']}",
        '"r1"',
    )
    assert (
        body["status"],
        body["preset_code"],
        body["category"],
        body["scope"],
        body["book"],
        body["entity_code"],
        body["version_no"],
        body["effective_from"],
    ) == ("DRAFT", "LEGACY_PARITY", "ACCOUNTING_POLICY", "TENANT", None, None, 2, None)
    values: dict[str, Any] = body["values"]
    assert {code: values[code] for code in NAMED} == NAMED
    # L3-1-Q-4: POL-026 material_right.ssp_method (parity ENTERED_AMOUNT) allows levels P, C and O
    # only, so a TENANT version cannot hold it.
    ssp_method = POLICY_PARAMETERS["material_right.ssp_method"]
    assert ssp_method.legacy_parity_value == "ENTERED_AMOUNT"
    assert "material_right.ssp_method" not in values
    # Every other key equals its legacy_parity_value, and the keys are exactly the ACCOUNTING_POLICY
    # parameters a TENANT version may hold that have a parity value.
    assert values == {
        code: spec.legacy_parity_value
        for code, spec in POLICY_PARAMETERS.items()
        if spec.category is RegistryCategory.ACCOUNTING_POLICY
        and RegistryScope.TENANT in spec.allowed_levels
        and not (spec.is_forced_asc606 and spec.is_forced_ifrs15)
        and spec.legacy_parity_value is not None
    }
    assert "pob.shipping_as_fulfilment" not in values  # POL-021 is a practical expedient
    assert body["diff_against_current"] == [
        {"code": code, "before": None, "after": value, "change": "ADDED"}
        for code, value in sorted(values.items())
    ]

    again = policies.post(PRESET, {"scope": "TENANT"})
    assert (again.status_code, slug(again), fields(again)) == (
        409,
        "invalid-transition",
        [("status", "SM-04")],
    )
    book = policies.post(PRESET, {"scope": "BOOK"})
    assert book.status_code == 201, book.text
    assert (book.json()["book"], book.json()["values"]) == (
        "ASC606",
        presets.legacy_parity_values(scope=RegistryScope.BOOK, book_code=BookCode.ASC606),
    )
    wrong = policies.post(PRESET, {"scope": "TENANT", "book": "IFRS15"})
    assert (wrong.status_code, fields(wrong)) == (422, [("book", "T-PLT-32")])
    unknown = policies.post(PRESET, {"scope": "ENTITY", "entity_code": "AVM-XX"})
    assert fields(unknown) == [("entity_code", "T-REF-01")]


def test_preset_follows_configuration_lifecycle(policies: Policies) -> None:
    calendar_id = calendar(policies.app, policies.maya)
    entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    created = policies.post(PRESET, {"scope": "TENANT"})
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    default_id = str(created.json()["supersedes_version_id"])
    # The preset holds period-scoped parameters (billing.posting, je.posting_mode), so it takes
    # effect on the first day of a future open period.
    undated = policies.patch(
        f"{POLICIES}/{version_id}", {"effective_from": "2026-09-20T04:00:00Z"}, etag='"r1"'
    )
    assert (undated.status_code, fields(undated)) == (422, [("effective_from", "T-PLT-32")])
    dated = policies.patch(f"{POLICIES}/{version_id}", {"effective_from": OCTOBER}, etag='"r1"')
    assert dated.status_code == 200, dated.text

    requested = policies.post(f"{POLICIES}/{version_id}/test", {})
    assert requested.status_code == 202, requested.text
    assert work(policies, str(requested.json()["id"]))["state"] == "SUCCEEDED"
    submitted = policies.post(f"{POLICIES}/{version_id}/submit", {"comment": "Legacy parity"})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"
    approved = policies.approve(str(submitted.json()["approval_request_id"]))
    assert approved.status_code == 200, approved.text

    current = policies.get(f"{POLICIES}/{version_id}").json()
    assert (
        current["status"],
        current["preset_code"],
        current["effective_from"],
        current["published_by"]["id"],  # API-S-Actor (04 rev 1.139)
    ) == ("PUBLISHED", "LEGACY_PARITY", OCTOBER, str(policies.marcus.member.user_id))
    superseded = policies.get(f"{POLICIES}/{default_id}").json()
    assert (superseded["status"], superseded["preset_code"], superseded["effective_to"]) == (
        "SUPERSEDED",
        "DEFAULT",
        OCTOBER,
    )
    resolved = policies.get(f"{POLICIES}/resolve", key="material_right.exercise", known_at=OCTOBER)
    assert resolved.status_code == 200, resolved.text
    assert (
        resolved.json()["value"],
        resolved.json()["level"],
        resolved.json()["source"],
    ) == ("MODIFICATION", "TENANT", {"type": "registry_version", "id": version_id})
    earlier = policies.get(
        f"{POLICIES}/resolve", key="material_right.exercise", known_at="2026-09-20T12:00:00Z"
    )
    assert (earlier.json()["value"], earlier.json()["level"]) == (
        "CONTINUATION",
        "FRAMEWORK_DEFAULT",
    )
    with tenant_session(context(policies.tenant_id), read_only=True) as session:
        found = resolve(
            session,
            "material_right.exercise",
            book_code=BookCode.ASC606,
            known_at=datetime(2026, 10, 1, 4, tzinfo=UTC),
        )
        statuses = session.execute(
            select(registry_version.c.version_no, registry_version.c.status)
            .where(registry_version.c.category == RegistryCategory.ACCOUNTING_POLICY.value)
            .order_by(registry_version.c.version_no)
        ).all()
    assert (found.value, found.level, str(found.source_id)) == ("MODIFICATION", "T", version_id)
    assert [tuple(row) for row in statuses] == [(1, "SUPERSEDED"), (2, "PUBLISHED")]
