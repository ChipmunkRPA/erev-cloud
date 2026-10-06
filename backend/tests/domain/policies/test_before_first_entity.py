"""A policy version before the workspace's first legal entity (PRD ERR-75 and ERR-80 rev 1.178; 04
§16.5 and T-PLT-32 rev 1.227; POLICIES §0.5 rule 3 rev 1.123; item PINP-PERIOD-VALUE-1, supervisor
rulings of 2026-10-01 and 2026-10-02).

The finding. A period takes the value in force at its own end (05 RCP-15 "The value of a
period"). A tenant's first REAL policy version supersedes the empty default that provisioning
writes, so it had to take effect at its submission or later — and the history a tenant migrates
lies before that: every legacy period computed under the framework defaults. The golden parity
scenario is that tenant (its preset was dated 2026, its legacy calendar is FY2023 and FY2024):
nine parity cases moved, 58.8462 to 58.85 in "Current Reclass to UAR".

The rule. While the workspace has no legal entity nothing has been computed, so a registry
version of an accounting category may supersede with an effective date that has passed, and the
period-start rule does not apply. From the first legal entity on both rules stand as before, and
a version submitted before it is judged again at the decision. The other categories hold
platform parameters, which acts read before any entity exists, and keep the rule.

The order of effective instants (PRD ERR-80) meets that rule at one place. Such a version
supersedes the default provisioning wrote, which names no date: for the order of versions that
default is in effect from its publication, for the value of a period it answers for every
earlier period (04 T-PLT-32). There the order yields, before the first legal entity; against a
published version that names a date it stands, before the first legal entity as after it.

Maya (``config.author``) applies the preset and Marcus (``config.approve``, MFA) approves it
(``policies`` fixture: a workspace without a legal entity). The frozen clock stands at
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_request, job, legal_entity, registry_version
from erev_api.domain.policies import lifecycle, registry_versions
from erev_api.enums import BookCode, RegistryCategory
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.registry import resolve as registry
from sqlalchemy import select, text
from support.reference import calendar, entity, fields, slug

if TYPE_CHECKING:
    from conftest import Policies

POLICIES = "/api/v1/policies"
PRESET = f"{POLICIES}/presets/legacy-parity"
JOBS = "/api/v1/jobs"
HISTORY = "2023-01-01T00:00:00Z"  # the first day of a migrated history; the clock stands in 2026
HISTORY_AT = datetime(2023, 1, 1, tzinfo=UTC)
OCTOBER = "2026-10-01T04:00:00Z"  # 1 October 2026 in New York: the first day of a future period
OCTOBER_AT = datetime(2026, 10, 1, 4, tzinfo=UTC)
RECLASS = "position.reclass_attribution_key"  # POL-121: pin P, TENANT; default POB_DEBIT_POSITIONS
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021: PRACTICAL_EXPEDIENT, pin K; default TRUE
EARLIER = "2022-06-01T00:00:00Z"  # before the first day of the migrated history
SEPTEMBER_20 = "2026-09-20T00:00:00Z"  # after the clock, before 1 October 2026
ERR_75 = (422, "validation-failed", [("effective_from", "REQ-POL-007")])
ERR_80 = (422, "validation-failed", [("effective_from", "REGISTRY_EFFECTIVE_ORDER")])
PERIOD_START = (422, "validation-failed", [("effective_from", "T-PLT-32")])
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


def shown(policies: Policies, version_id: str) -> dict[str, Any]:
    response = policies.get(f"{POLICIES}/{version_id}")
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def dated(policies: Policies, version_id: str, effective_from: str) -> None:
    current = shown(policies, version_id)
    moved = policies.patch(
        f"{POLICIES}/{version_id}",
        {"effective_from": effective_from},
        etag=f'"r{current["row_version"]}"',
    )
    assert moved.status_code == 200, moved.text


def pass_tests(policies: Policies, version_id: str) -> None:
    requested = policies.post(f"{POLICIES}/{version_id}/test", {})
    assert requested.status_code == 202, requested.text
    assert work(policies, str(requested.json()["id"]))["state"] == "SUCCEEDED"


def submitted(policies: Policies, version_id: str) -> str:
    """Submit a tested version; returns the id of its approval request."""
    response = policies.post(f"{POLICIES}/{version_id}/submit", {"comment": "Ready"})
    assert response.status_code == 200, response.text
    return str(response.json()["approval_request_id"])


def preset(policies: Policies) -> tuple[str, str]:
    """The DRAFT LEGACY_PARITY version of the TENANT scope and the default it would supersede."""
    created = policies.post(PRESET, {"scope": "TENANT"})
    assert created.status_code == 201, created.text
    return str(created.json()["id"]), str(created.json()["supersedes_version_id"])


def versions(policies: Policies, category: RegistryCategory) -> list[tuple[Any, ...]]:
    """(version_no, status, effective_from, effective_to) of the TENANT scope of ``category``."""
    return [
        (row["version_no"], row["status"], row["effective_from"], row["effective_to"])
        for row in policies.rows(
            select(
                registry_version.c.version_no,
                registry_version.c.status,
                registry_version.c.effective_from,
                registry_version.c.effective_to,
            )
            .where(
                registry_version.c.category == category.value,
                registry_version.c.scope == "TENANT",
            )
            .order_by(registry_version.c.version_no)
        )
    ]


def test_before_the_first_legal_entity_a_preset_is_dated_at_the_start_of_the_history(
    policies: Policies,
) -> None:
    """The migrating tenant: no legal entity yet, the preset dated at the first day of the
    history it will import. Saved, tested, submitted and approved; the empty default is closed at
    that day; and what a computation reads for a period of the history is the preset."""
    version_id, default_id = preset(policies)
    dated(policies, version_id, HISTORY)  # the period-start rule: no entity, any date
    pass_tests(policies, version_id)
    approved = policies.approve(submitted(policies, version_id))  # PRD ERR-75, twice
    assert approved.status_code == 200, approved.text
    assert (
        shown(policies, version_id)["status"],
        shown(policies, version_id)["effective_from"],
    ) == (
        "PUBLISHED",
        HISTORY,
    )
    assert versions(policies, RegistryCategory.ACCOUNTING_POLICY) == [
        (1, "SUPERSEDED", None, HISTORY_AT),
        (2, "PUBLISHED", HISTORY_AT, None),
    ]
    assert shown(policies, default_id)["effective_to"] == HISTORY
    with tenant_session(context(policies.tenant_id), read_only=True) as session:
        known = registry.known_versions(session, known_at=policies.clock.now())
        inside = registry.resolve_among(
            known, RECLASS, book_code=BookCode.ASC606, at=datetime(2023, 6, 30, 23, tzinfo=UTC)
        )
        before = registry.resolve_among(
            known, RECLASS, book_code=BookCode.ASC606, at=datetime(2022, 12, 31, 23, tzinfo=UTC)
        )
    assert (inside.value, inside.level, str(inside.source_id)) == (
        "CUMULATIVE_SSP_DELIVERED",
        "T",
        version_id,
    )
    assert (before.value, before.level) == ("POB_DEBIT_POSITIONS", "DEFAULT")


def test_a_practical_expedient_version_supersedes_with_a_passed_date_before_the_first_entity(
    policies: Policies,
) -> None:
    """The second accounting category, and PRD ERR-75 alone: POL-021 is contract-pinned, so the
    period-start rule does not ask."""
    created = policies.post(
        POLICIES,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "TENANT",
            "values": {SHIPPING: "FALSE"},
            "effective_from": HISTORY,
        },
    )
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    pass_tests(policies, version_id)
    approved = policies.approve(submitted(policies, version_id))
    assert approved.status_code == 200, approved.text
    assert versions(policies, RegistryCategory.PRACTICAL_EXPEDIENT) == [
        (1, "SUPERSEDED", None, HISTORY_AT),
        (2, "PUBLISHED", HISTORY_AT, None),
    ]


def test_from_the_first_legal_entity_on_a_passed_date_is_refused_as_before(
    policies: Policies,
) -> None:
    calendar_id = calendar(policies.app, policies.maya)
    entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    version_id, _ = preset(policies)
    refused = policies.patch(f"{POLICIES}/{version_id}", {"effective_from": HISTORY}, etag='"r1"')
    assert (refused.status_code, slug(refused), fields(refused)) == PERIOD_START, refused.text
    assert refused.json()["errors"][0]["message"] == registry_versions.PERIOD_START_REQUIRED
    # PRD ERR-75 alone, on a version the period-start rule does not ask about
    created = policies.post(
        POLICIES,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "TENANT",
            "values": {SHIPPING: "FALSE"},
            "effective_from": HISTORY,
        },
    )
    assert created.status_code == 201, created.text
    expedient_id = str(created.json()["id"])
    pass_tests(policies, expedient_id)
    late = policies.post(f"{POLICIES}/{expedient_id}/submit", {"comment": "Ready"})
    assert (late.status_code, slug(late), fields(late)) == ERR_75, late.text
    assert late.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED


def test_an_entity_created_before_the_decision_refuses_the_passed_date_by_name(
    policies: Policies,
) -> None:
    """Submitted while the workspace had no legal entity, decided after its first one: the date
    is judged again in the decision's transaction (PRD ERR-75) and refused by name; nothing of
    the decision is kept. The version is SUBMITTED with a PENDING request: its author withdraws
    it, dates it at the first day of a future open period and submits it again."""
    version_id, _ = preset(policies)
    dated(policies, version_id, HISTORY)
    pass_tests(policies, version_id)
    request_id = submitted(policies, version_id)

    calendar_id = calendar(policies.app, policies.maya)
    entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    refused = policies.approve(request_id)
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_75, refused.text
    assert refused.json()["errors"][0]["message"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert refused.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert versions(policies, RegistryCategory.ACCOUNTING_POLICY) == [
        (1, "PUBLISHED", None, None),
        (2, "SUBMITTED", HISTORY_AT, None),
    ]
    pending = policies.rows(
        select(approval_request.c.status).where(approval_request.c.id == UUID(request_id))
    )
    assert [row["status"] for row in pending] == ["PENDING"]

    withdrawn = policies.post(f"{POLICIES}/{version_id}/withdraw", {"comment": "An entity exists"})
    assert withdrawn.status_code == 200, withdrawn.text
    still = policies.patch(
        f"{POLICIES}/{version_id}",
        {"effective_from": HISTORY},
        etag=f'"r{shown(policies, version_id)["row_version"]}"',
    )
    assert (still.status_code, slug(still), fields(still)) == PERIOD_START, still.text
    dated(policies, version_id, OCTOBER)
    pass_tests(policies, version_id)
    approved = policies.approve(submitted(policies, version_id))
    assert approved.status_code == 200, approved.text
    assert versions(policies, RegistryCategory.ACCOUNTING_POLICY) == [
        (1, "SUPERSEDED", None, OCTOBER_AT),
        (2, "PUBLISHED", OCTOBER_AT, None),
    ]


def test_a_category_that_holds_a_platform_parameter_keeps_the_rule(policies: Policies) -> None:
    """Acts read platform parameters before any legal entity exists — a product's mandatory
    attributes, the late-entry window of a report — so their categories keep the rule in a
    workspace without one. DISCLOSURE_ELECTION holds one platform parameter and stays dated: the
    period-start rule refuses the passed date when the version is written. CLOSE is a settings
    category, which takes the instant form alone (``INSTANT_CATEGORIES``; supervisor ruling
    R-115 (e)): its version is written, and PRD ERR-75 refuses the passed time at the submit."""
    assert (
        frozenset({RegistryCategory.ACCOUNTING_POLICY, RegistryCategory.PRACTICAL_EXPEDIENT})
        == registry_versions.ENTITY_BOUND_CATEGORIES
    )
    assert RegistryCategory.CLOSE in registry_versions.INSTANT_CATEGORIES
    assert RegistryCategory.DISCLOSURE_ELECTION not in registry_versions.INSTANT_CATEGORIES
    refused = policies.post(
        POLICIES,
        {
            "category": "DISCLOSURE_ELECTION",
            "scope": "TENANT",
            "values": {"disclosure.mandatory_disaggregation_attributes": []},
            "effective_from": HISTORY,
        },
    )
    assert (refused.status_code, slug(refused), fields(refused)) == PERIOD_START, refused.text
    created = policies.post(
        POLICIES,
        {
            "category": "CLOSE",
            "scope": "TENANT",
            "values": {"close.late_entry_window_days": 7},
            "effective_from": HISTORY,
        },
    )
    assert created.status_code == 201, created.text
    close_id = str(created.json()["id"])
    pass_tests(policies, close_id)
    late = policies.post(f"{POLICIES}/{close_id}/submit", {"comment": "Ready"})
    assert (late.status_code, slug(late), fields(late)) == ERR_75, late.text
    assert late.json()["detail"] == lifecycle.EFFECTIVE_INSTANT_PASSED
    assert shown(policies, close_id)["status"] == "TESTED"


def expedient(policies: Policies, value: str, effective_from: str) -> str:
    """A TESTED practical-expedient version of the TENANT scope stating POL-021; its id. POL-021
    is contract-pinned, so the period-start rule does not ask and the date is free."""
    created = policies.post(
        POLICIES,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "TENANT",
            "values": {SHIPPING: value},
            "effective_from": effective_from,
        },
    )
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    pass_tests(policies, version_id)
    return version_id


def test_the_order_of_effective_instants_yields_to_an_undated_published_version_only(
    policies: Policies,
) -> None:
    """PRD ERR-80 (the supervisor's ruling of 2026-10-02). Before the first legal entity a
    version dated at the first day of the history is taken over the default provisioning wrote,
    which names no date and was published in 2026: the order yields there. A second version
    dated before that DATED published version is refused by the order, and nothing of it is
    kept. From the first legal entity on the order stands as well: with a published version
    dated 1 October 2026, a version dated 20 September 2026 — a time that has not passed, so
    PRD ERR-75 does not ask — is refused by it."""
    first = expedient(policies, "FALSE", HISTORY)
    approved = policies.approve(submitted(policies, first))  # the yield: an undated predecessor
    assert approved.status_code == 200, approved.text
    assert versions(policies, RegistryCategory.PRACTICAL_EXPEDIENT) == [
        (1, "SUPERSEDED", None, HISTORY_AT),
        (2, "PUBLISHED", HISTORY_AT, None),
    ]

    second = expedient(policies, "TRUE", EARLIER)
    refused = policies.post(f"{POLICIES}/{second}/submit", {"comment": "Ready"})
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_80, refused.text
    dated_copy = registry_versions.EFFECTIVE_ORDER_DATED
    assert refused.json()["detail"] == dated_copy.format(version_no=2, date="01 Jan 2023")
    assert shown(policies, second)["status"] == "TESTED"
    assert versions(policies, RegistryCategory.PRACTICAL_EXPEDIENT)[:2] == [
        (1, "SUPERSEDED", None, HISTORY_AT),
        (2, "PUBLISHED", HISTORY_AT, None),
    ]

    calendar_id = calendar(policies.app, policies.maya)
    entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    dated(policies, second, OCTOBER)  # a time that has not passed, after the published one
    pass_tests(policies, second)
    approved = policies.approve(submitted(policies, second))
    assert approved.status_code == 200, approved.text
    assert versions(policies, RegistryCategory.PRACTICAL_EXPEDIENT) == [
        (1, "SUPERSEDED", None, HISTORY_AT),
        (2, "SUPERSEDED", HISTORY_AT, OCTOBER_AT),
        (3, "PUBLISHED", OCTOBER_AT, None),
    ]
    third = expedient(policies, "FALSE", SEPTEMBER_20)
    refused = policies.post(f"{POLICIES}/{third}/submit", {"comment": "Ready"})
    assert (refused.status_code, slug(refused), fields(refused)) == ERR_80, refused.text
    assert refused.json()["detail"] == dated_copy.format(version_no=3, date="01 Oct 2026")
    assert shown(policies, third)["status"] == "TESTED"


def test_whether_the_workspace_has_an_entity_does_not_depend_on_who_asks(
    policies: Policies,
) -> None:
    """``legal_entity`` is RLS-TE: a reader whose scope names no entity sees none. The condition
    is the tenant's fact, read under the tenant's scope, and the reader's scope is given back."""
    narrow = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope=())
    with tenant_session(narrow, read_only=True) as session:
        assert lifecycle.has_legal_entity(session) is False
    calendar_id = calendar(policies.app, policies.maya)
    entity(policies.app, policies.maya, code="AVM-US", calendar_id=calendar_id)
    with tenant_session(narrow, read_only=True) as session:
        assert session.execute(select(legal_entity.c.id)).first() is None  # what the reader sees
        assert lifecycle.has_legal_entity(session) is True
        assert session.execute(select(legal_entity.c.id)).first() is None  # its scope is back
