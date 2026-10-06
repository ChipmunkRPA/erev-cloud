"""RFD-17 industry policy templates (03 REQ-POL-009; PRD §5.3 BR-POL-03; POLICIES §0.5; BUILD_SPEC
RFD-17, BS3-D-10).

``create_industry_templates`` runs as Maya (``config.author``) through a unit of work; the API-R-13
and API-R-25 routes drive testing and submission as Maya and the approval as Marcus (``policies``
fixture). The frozen clock reads 2026-09-12T12:00Z.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from erev_api.auth.principal import RequestContext
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import pob_template, pob_template_version, registry_version
from erev_api.domain.policies import industry
from erev_api.domain.policies import templates as template_rules
from erev_api.enums import TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import and_, select
from support.factories import (
    CONFIG_TEST_CASES,
    JANUARY,
    POB_TEMPLATE_VERSIONS,
    maya_principal,
)
from support.reference import approve, get, new_product, patch, post

if TYPE_CHECKING:
    from conftest import Policies

RESOLVE = "/api/v1/policies/resolve"
D01 = "D01"
SAAS = industry.template_code(D01, "SAAS-RATABLE")
# The D01 draft's one non-default value: contract-level journal summarisation (POL-006), a grouping
# of the same postings; the framework default groups by account (team-lead ruling Q19).
SUMMARISATION = "je.summarization"
SUMMARISATION_DEFAULT = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"


@contextmanager
def _as_maya(policies: Policies) -> Iterator[UnitOfWork]:
    """A committed unit of work as Maya, the preparer of the drafts."""
    ctx = RequestContext(
        principal=maya_principal(policies.maya.member),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-rfd-17",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=policies.clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(policies.settings.file_root)
    with unit_of_work(ctx, clock=policies.clock, keyring=policies.keyring, files=files) as uow:
        yield uow
        uow.commit()


def _template_rows(policies: Policies) -> list[dict[str, Any]]:
    joined = pob_template_version.join(
        pob_template,
        and_(
            pob_template.c.tenant_id == pob_template_version.c.tenant_id,
            pob_template.c.id == pob_template_version.c.pob_template_id,
        ),
    )
    return policies.rows(
        select(
            pob_template.c.code,
            pob_template_version.c.id,
            pob_template_version.c.status,
            pob_template_version.c.version_no,
        ).select_from(joined)
    )


def _in_force_codes(policies: Policies) -> set[str]:
    """The template codes booking-line resolution sees now (``template_inputs``; CTL-031)."""
    scope = DbContext(tenant_id=policies.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as session:
        inputs = template_rules.template_inputs(session, known_at=policies.clock.now())
    return {item.template_code for item in inputs}


def test_industry_templates_created_as_draft(policies: Policies) -> None:
    with _as_maya(policies) as uow:
        drafts = industry.create_industry_templates(uow, cluster=D01)

    cluster = industry.cluster_of(D01)
    codes = {template.code for template in cluster.templates}
    assert drafts.cluster == D01
    assert set(drafts.template_ids) == codes
    assert set(drafts.template_version_ids) == codes
    assert cluster.tenant_values[SUMMARISATION] == "CONTRACT_ACCOUNT_DIMENSIONS"

    rows = _template_rows(policies)
    assert {row["code"]: (str(row["status"]), row["version_no"]) for row in rows} == {
        code: ("DRAFT", 1) for code in codes
    }
    assert {UUID(str(row["id"])) for row in rows} == set(drafts.template_version_ids.values())

    versions = policies.rows(
        select(
            registry_version.c.status,
            registry_version.c.scope,
            registry_version.c.category,
            registry_version.c.book_code,
            registry_version.c.entity_id,
            registry_version.c["values"],
            registry_version.c.effective_from,
        ).where(registry_version.c.id == drafts.registry_version_id)
    )
    assert len(versions) == 1
    version = versions[0]
    assert (str(version["status"]), str(version["scope"]), str(version["category"])) == (
        "DRAFT",
        "TENANT",
        "ACCOUNTING_POLICY",
    )
    assert (version["book_code"], version["entity_id"], version["effective_from"]) == (
        None,
        None,
        None,
    )
    assert version["values"] == dict(cluster.tenant_values)

    # BR-POL-03: a draft resolves nothing. The registry answers the framework default and the
    # booking-line template inputs hold none of the cluster's codes.
    resolved = policies.get(RESOLVE, key=SUMMARISATION)
    assert resolved.status_code == 200, resolved.text
    assert (resolved.json()["value"], resolved.json()["level"]) == (
        SUMMARISATION_DEFAULT,
        "FRAMEWORK_DEFAULT",
    )
    assert _in_force_codes(policies) & codes == set()


def test_draft_templates_usable_after_publication(policies: Policies) -> None:
    with _as_maya(policies) as uow:
        drafts = industry.create_industry_templates(uow, cluster=D01)
    version_id = str(drafts.template_version_ids[SAAS])
    app, maya, marcus = policies.app, policies.maya, policies.marcus
    new_product(
        app,
        maya,
        code="FS-PLAT",
        name="Fernhill platform, 12 months",
        revenue_category="SUBSCRIPTION",
        principal_agent="PRINCIPAL",
    )

    # Maya dates the draft, adds one example case, runs the tests and submits it.
    shown = get(app, f"{POB_TEMPLATE_VERSIONS}/{version_id}", maya)
    assert shown.status_code == 200, shown.text
    assert shown.json()["status"] == "DRAFT"
    dated = patch(
        app,
        f"{POB_TEMPLATE_VERSIONS}/{version_id}",
        maya,
        {"effective_from": JANUARY},
        if_match=shown.headers["ETag"],
    )
    assert dated.status_code == 200, dated.text
    case = post(
        app,
        CONFIG_TEST_CASES,
        maya,
        {
            "subject_type": "pob_template_version",
            "subject_id": version_id,
            "name": "FS-PLAT booking",
            "input": {
                "booking_date": "2026-01-01",
                "currency": "USD",
                "lines": [
                    {
                        "obligation_key": "POB-01",
                        "product_code": "FS-PLAT",
                        "total_price": "120000.00",
                        "start_date": "2026-01-01",
                        "end_date": "2026-12-31",
                    }
                ],
            },
            "expected_output": {"drafts": [{"obligation_key": "POB-01"}]},
        },
    )
    assert case.status_code == 201, case.text
    tested = post(app, f"{POB_TEMPLATE_VERSIONS}/{version_id}/test", maya, {})
    assert (tested.status_code, tested.json()["status"]) == (200, "TESTED"), tested.text
    sent = post(
        app, f"{POB_TEMPLATE_VERSIONS}/{version_id}/submit", maya, {"comment": "Ready for review"}
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "SUBMITTED"
    assert SAAS not in _in_force_codes(policies)

    # Marcus, another user, approves: the version is PUBLISHED and booking lines resolve it.
    decided = approve(app, str(sent.json()["pending_approval_request_id"]), marcus)
    assert decided.status_code == 200, decided.text
    published = get(app, f"{POB_TEMPLATE_VERSIONS}/{version_id}", maya)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["template_code"] == SAAS
    assert SAAS in _in_force_codes(policies)
    # The other drafts of the cluster stay DRAFT and out of force.
    others = {template.code for template in industry.cluster_of(D01).templates} - {SAAS}
    assert {row["code"]: str(row["status"]) for row in _template_rows(policies)} == {
        SAAS: "PUBLISHED",
        **dict.fromkeys(others, "DRAFT"),
    }
    assert _in_force_codes(policies) & others == set()


def test_unknown_cluster_is_refused(policies: Policies) -> None:
    with pytest.raises(LookupError, match="D03"), _as_maya(policies) as uow:
        industry.create_industry_templates(uow, cluster="D03")
    assert _template_rows(policies) == []
