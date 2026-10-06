"""Products, principal-or-agent changes and the approved change of a product's policy values (04
T-REF-20, E-89, E-105, API-R-23 and §16.10 rev 1.110, the T-REF-15 product key; 03 REQ-REF-012,
REQ-REF-014, REQ-POL-003; PRD §2.5 routing row ``PRINCIPAL_AGENT_CHANGE``, §2.6; SCREENS §10;
POLICIES §0.5, §0.6; CTL-031; BUILD_SPEC RFD-9; security finding SN-7, supervisor ruling R-21;
item PRODUCT-CODE-FREEZE-1, 04 §14.1 DB-05 rev 1.160, supervisor ruling R-112 (i)).

Maya holds Revenue Accountant (``masterdata.maintain``, ``contract.read``, ``config.author``) and
maintains products; Carmen holds Controller (``config.approve``), is enrolled in MFA and approves
principal-or-agent changes; Omar holds Viewer (docs/02-PRD.md §5.6). The products are those of
PRD §2.6. The frozen clock reads 2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    obligation,
    product,
    ssp_book,
    ssp_book_version,
    ssp_entry,
)
from erev_api.domain.reference import products
from erev_api.enums import RegistryCategory
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import (
    TPL_PROD_UNITS,
    TPL_SUB_DAILY,
    published_template,
    set_default_template,
)
from support.plans import sent
from support.principals import Actor, colleague, enrolled, member
from support.reference import (
    ACCOUNT_MAPPINGS,
    APPROVALS,
    PRODUCTS,
    approve,
    assign,
    delete,
    fields,
    get,
    gl_account,
    holding,
    mapping_published,
    new_product,
    patch,
    post,
    put,
    reject,
    slug,
)
from support.rows import (
    insert_obligation_rows,
    insert_version_rows,
    publish_registry_version,
    ssp_book_values,
    ssp_book_version_values,
    ssp_entry_values,
)

PLATFORM_100 = "Platform, 100 seats, 12 months"
RATIONALE = "Controls the platform before transfer."
PUBLISHED_AT = datetime(2026, 9, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class World:
    maya: Actor
    carmen: Actor

    @property
    def tenant_id(self) -> UUID:
        return self.maya.member.tenant_id


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> World:
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    carmen_member = colleague(maya_member.tenant_id, "carmen")
    assign(carmen_member, "controller")
    carmen = enrolled(app, clock, carmen_member)
    return World(maya=maya, carmen=carmen)


def path(product_id: str, suffix: str = "") -> str:
    return f"{PRODUCTS}/{product_id}{suffix}"


def tenant_context(world: World) -> DbContext:
    return DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")


def audits(world: World, action: str) -> list[dict[str, Any]]:
    """The audit events of ``action`` in chain order."""
    statement = (
        select(
            audit_event.c.object_id,
            audit_event.c.before,
            audit_event.c.after,
            audit_event.c.approval_request_id,
        )
        .where(audit_event.c.action == action)
        .order_by(audit_event.c.chain_seq)
    )
    with tenant_session(tenant_context(world), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def shown(app: FastAPI, actor: Actor, product_id: str) -> dict[str, Any]:
    response = get(app, path(product_id), actor)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_product_attributes_round_trip(app: FastAPI, world: World) -> None:
    body = {
        "code": "AVM-PLAT-100",
        "sku_number": "100",
        "name": PLATFORM_100,
        "product_family": "Platform",
        "revenue_category": "SUBSCRIPTION",
        "disaggregation": {"channel": "direct", "region": "AMER"},
        "principal_agent": "NOT_ASSESSED",
        "distinctness_default": "distinct",
        "unit_of_measure": "EA",
        "is_bundle": False,
        "assurance_cost_per_unit": "12.500",
        "is_franchisor_preopening_service": False,
        "policy_values": {"material_right.ssp_method": "ENTERED_AMOUNT"},
        "is_active": True,
    }
    created = post(app, PRODUCTS, world.maya, body)
    assert created.status_code == 201, created.text
    platform = created.json()
    assert created.headers["ETag"] == '"r1"'
    assert created.headers["Location"] == path(platform["id"])
    expected = {**body, "default_pob_template_id": None, "assurance_cost_per_unit": "12.5"}
    assert {name: platform[name] for name in expected} == expected
    assert (
        platform["pending_approval_request_id"],
        platform["usability"],
        platform["row_version"],
    ) == (None, {"usable": True, "missing": []}, 1)
    one = get(app, path(platform["id"]), world.maya)
    assert (one.status_code, one.headers["ETag"]) == (200, '"r1"'), one.text
    assert one.json() == platform

    # The T-REF-20 column defaults.
    seat = new_product(
        app, world.maya, code="AVM-SEAT-MO", name="Platform seat, per seat per month"
    )
    assert {name: seat[name] for name in expected if name not in ("code", "name")} == {
        "sku_number": None,
        "product_family": None,
        "revenue_category": None,
        "default_pob_template_id": None,
        "disaggregation": {},
        "principal_agent": "NOT_ASSESSED",
        "distinctness_default": "distinct",
        "unit_of_measure": "EA",
        "is_bundle": False,
        "assurance_cost_per_unit": None,
        "is_franchisor_preopening_service": False,
        "policy_values": {},
        "is_active": True,
    }

    # SCREENS §10.3: quick search, product family filter and sort.
    searched = get(app, PRODUCTS, world.maya, {"q": "platform", "sort": "-code"})
    assert searched.status_code == 200, searched.text
    assert [item["code"] for item in searched.json()["items"]] == ["AVM-SEAT-MO", "AVM-PLAT-100"]
    family = get(app, PRODUCTS, world.maya, {"product_family": "Platform"})
    assert [item["code"] for item in family.json()["items"]] == ["AVM-PLAT-100"]
    assert [str(event["object_id"]) for event in audits(world, "product.create")] == [
        platform["id"],
        seat["id"],
    ]


def test_principal_agent_patch_refused(app: FastAPI, world: World) -> None:
    platform = new_product(app, world.maya, code="AVM-PLAT-100", name=PLATFORM_100)
    refused = patch(
        app, path(platform["id"]), world.maya, {"principal_agent": "AGENT"}, if_match='"r1"'
    )
    assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
    first = refused.json()["errors"][0]
    assert (first["field"], first["rule_id"]) == ("principal_agent", "REQ-REF-012")
    assert first["message"] == (
        "Principal or agent changes need approval. Propose a principal or agent change instead."
    )
    current = shown(app, world.maya, platform["id"])
    assert (current["principal_agent"], current["row_version"]) == ("NOT_ASSESSED", 1)

    # POL-030 set on the product is the same conclusion (POLICIES §0.5 level P).
    policy = patch(
        app,
        path(platform["id"]),
        world.maya,
        {"policy_values": {"pob.principal_or_agent": "AGENT"}},
        if_match='"r1"',
    )
    assert fields(policy) == [("policy_values.pob.principal_or_agent", "REQ-REF-012")]

    # Sending the stored conclusion back changes nothing about it.
    renamed = patch(
        app,
        path(platform["id"]),
        world.maya,
        {"principal_agent": "NOT_ASSESSED", "name": "Platform, 100 seats"},
        if_match='"r1"',
    )
    assert renamed.status_code == 200, renamed.text
    assert (renamed.headers["ETag"], renamed.json()["principal_agent"]) == ('"r2"', "NOT_ASSESSED")
    assert audits(world, "product.principal_agent_change") == []


def test_principal_agent_change_through_approval(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    tomas_member = colleague(world.tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    assign(tomas_member, "controller")
    tomas = enrolled(app, clock, tomas_member)
    platform = new_product(app, world.maya, code="AVM-PLAT-100", name=PLATFORM_100)
    propose_path = path(platform["id"], "/propose-principal-agent-change")

    proposed = post(
        app, propose_path, tomas, {"principal_agent": "PRINCIPAL", "rationale": RATIONALE}
    )
    assert proposed.status_code == 200, proposed.text
    request_id = proposed.json()["approval_request_id"]
    detail = get(app, f"{APPROVALS}/{request_id}", world.carmen)
    assert detail.status_code == 200, detail.text
    request = detail.json()
    assert (
        request["subject"]["type"],
        request["subject"]["id"],
        request["subject"]["href"],
        request["status"],
        request["summary"],
        [step["required_permission"] for step in request["steps"]],
    ) == (
        "PRINCIPAL_AGENT_CHANGE",
        platform["id"],
        f"/settings/products/{platform['id']}",
        "PENDING",
        "Principal or agent change for AVM-PLAT-100",
        ["config.approve"],
    )
    # The proposal is stored as the preview's "after" member (BS1-D-24).
    assert request["impact_preview"]["file_id"] is not None
    current = shown(app, world.maya, platform["id"])
    assert (current["principal_agent"], current["pending_approval_request_id"]) == (
        "NOT_ASSESSED",
        request_id,
    )

    # One pending change per product.
    again = post(
        app, propose_path, world.maya, {"principal_agent": "AGENT", "rationale": "Arranges supply."}
    )
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    # The proposer holds config.approve and is refused; the product keeps its conclusion.
    refused = approve(app, request_id, tomas)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert shown(app, world.maya, platform["id"])["principal_agent"] == "NOT_ASSESSED"

    # Another config.approve holder approves: the product shows PRINCIPAL.
    approved = approve(app, request_id, world.carmen)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    current = shown(app, world.maya, platform["id"])
    assert (
        current["principal_agent"],
        current["pending_approval_request_id"],
        current["row_version"],
    ) == ("PRINCIPAL", None, 2)
    [event] = audits(world, "product.principal_agent_change")
    assert (
        str(event["object_id"]),
        event["before"],
        event["after"],
        str(event["approval_request_id"]),
    ) == (
        platform["id"],
        {"principal_agent": "NOT_ASSESSED"},
        {"principal_agent": "PRINCIPAL"},
        request_id,
    )


def test_mandatory_disaggregation_attributes_gate_usability(app: FastAPI, world: World) -> None:
    with tenant_session(tenant_context(world)) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.DISCLOSURE_ELECTION,
            values={"disclosure.mandatory_disaggregation_attributes": ["channel"]},
            at=PUBLISHED_AT,
        )
    platform = new_product(app, world.maya, code="AVM-PLAT-100", name=PLATFORM_100)
    product_id = UUID(platform["id"])
    with tenant_session(tenant_context(world), read_only=True) as session:
        assert products.usability(session, product_id) == {"usable": False, "missing": ["channel"]}
    assert platform["usability"] == {"usable": False, "missing": ["channel"]}

    # Another attribute does not satisfy the gate.
    regional = patch(
        app,
        path(platform["id"]),
        world.maya,
        {"disaggregation": {"region": "AMER"}},
        if_match='"r1"',
    )
    assert regional.status_code == 200, regional.text
    assert regional.json()["usability"] == {"usable": False, "missing": ["channel"]}

    direct = patch(
        app,
        path(platform["id"]),
        world.maya,
        {"disaggregation": {"channel": "direct", "region": "AMER"}},
        if_match='"r2"',
    )
    assert direct.status_code == 200, direct.text
    assert direct.json()["usability"] == {"usable": True, "missing": []}
    with tenant_session(tenant_context(world), read_only=True) as session:
        assert products.usability(session, product_id) == {"usable": True, "missing": []}
        with pytest.raises(LookupError):
            products.usability(session, world.tenant_id)

    # A deactivated product is not usable either.
    inactive = patch(app, path(platform["id"]), world.maya, {"is_active": False}, if_match='"r3"')
    assert inactive.json()["usability"] == {"usable": False, "missing": []}


@pytest.mark.control("CTL-031")
def test_ctl_031_principal_agent_change_without_approval_not_applied(
    app: FastAPI, world: World
) -> None:
    platform = new_product(app, world.maya, code="AVM-PLAT-100", name=PLATFORM_100)
    propose_path = path(platform["id"], "/propose-principal-agent-change")
    proposal = {"principal_agent": "AGENT", "rationale": "The supplier controls the platform."}

    proposed = post(app, propose_path, world.maya, proposal)
    assert proposed.status_code == 200, proposed.text
    request_id = proposed.json()["approval_request_id"]

    def stored() -> str:
        statement = select(product.c.principal_agent).where(product.c.id == UUID(platform["id"]))
        with tenant_session(tenant_context(world), read_only=True) as session:
            return str(session.execute(statement).scalar_one())

    # PENDING: unchanged.
    assert stored() == "NOT_ASSESSED"
    assert shown(app, world.maya, platform["id"])["pending_approval_request_id"] == request_id

    # REJECTED: unchanged.
    rejected = reject(app, request_id, world.carmen, "Evidence of control is missing.")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert stored() == "NOT_ASSESSED"
    current = shown(app, world.maya, platform["id"])
    assert (
        current["principal_agent"],
        current["pending_approval_request_id"],
        current["row_version"],
    ) == (
        "NOT_ASSESSED",
        None,
        1,
    )
    assert audits(world, "product.principal_agent_change") == []

    # A rejected request does not block a new proposal, which is again PENDING and not applied.
    renewed = post(app, propose_path, world.maya, proposal)
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["approval_request_id"] != request_id
    assert stored() == "NOT_ASSESSED"


def test_product_findings_and_permissions(app: FastAPI, world: World) -> None:
    omar = holding(app, colleague(world.tenant_id, "omar"), "viewer")
    kit_body = {"code": "AVM-KIT", "name": "Sensor kit", "revenue_category": "PRODUCT"}
    denied = post(app, PRODUCTS, omar, kit_body)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    kit = new_product(app, world.maya, **kit_body)

    # contract.read reads; masterdata.maintain is needed for every command.
    assert get(app, path(kit["id"]), omar).status_code == 200
    for refused in (
        patch(app, path(kit["id"]), omar, {"name": "Kit"}, if_match='"r1"'),
        post(
            app,
            path(kit["id"], "/propose-principal-agent-change"),
            omar,
            {"principal_agent": "PRINCIPAL", "rationale": RATIONALE},
        ),
        post(
            app,
            path(kit["id"], "/propose-policy-values-change"),
            omar,
            {"policy_values": {"recognition.time_convention": "MID_MONTH"}, "rationale": RATIONALE},
        ),
        put(app, path(kit["id"], "/bundle-components"), omar, {"components": []}),
    ):
        assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text

    findings = post(
        app,
        PRODUCTS,
        world.maya,
        {
            "code": "AVM-KIT",
            "name": " ",
            "revenue_category": "not a category!",
            "default_pob_template_id": str(world.tenant_id),
            "disaggregation": {"channel": " "},
            "unit_of_measure": " ",
            "assurance_cost_per_unit": "-1",
            "policy_values": {
                "rounding.posting_mode": "HALF_UP",
                "material_right.ssp_method": "NOPE",
                "no.such": 1,
            },
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("code", "T-REF-20"),
        ("name", "T-REF-20"),
        ("revenue_category", "T-REF-20"),
        ("default_pob_template_id", "T-REF-20"),
        ("disaggregation.channel", "T-REF-20"),
        ("unit_of_measure", "T-REF-20"),
        ("assurance_cost_per_unit", "T-REF-20"),
        ("policy_values.material_right.ssp_method", "POLICY_VALUE_INVALID"),
        ("policy_values.no.such", "POLICY_VALUE_INVALID"),
        ("policy_values.rounding.posting_mode", "POLICY_LEVEL_NOT_ALLOWED"),
    ]
    assert findings.json()["errors"][0]["message"] == "Product code AVM-KIT is already used."
    numeric = post(
        app,
        PRODUCTS,
        world.maya,
        {"code": "AVM-GW", "name": "Gateway", "assurance_cost_per_unit": 1},
    )
    assert fields(numeric) == [("assurance_cost_per_unit", "API-C-06")], numeric.text

    unguarded = patch(app, path(kit["id"]), world.maya, {"name": "Kit"}, if_match=None)
    assert unguarded.status_code == 428, unguarded.text
    nulls = patch(
        app, path(kit["id"]), world.maya, {"name": None, "unit_of_measure": None}, if_match='"r1"'
    )
    assert fields(nulls) == [("name", "T-REF-20"), ("unit_of_measure", "T-REF-20")]
    missing = get(app, path(str(world.tenant_id)), world.maya)
    assert (missing.status_code, slug(missing)) == (404, "not-found"), missing.text

    unchanged = post(
        app,
        path(kit["id"], "/propose-principal-agent-change"),
        world.maya,
        {"principal_agent": "NOT_ASSESSED", "rationale": " "},
    )
    assert fields(unchanged) == [("principal_agent", "REQ-REF-012"), ("rationale", "REQ-REF-012")]
    unknown = post(
        app,
        path(str(world.tenant_id), "/propose-principal-agent-change"),
        world.maya,
        {"principal_agent": "PRINCIPAL", "rationale": RATIONALE},
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    deactivated = patch(app, path(kit["id"]), world.maya, {"is_active": False}, if_match='"r1"')
    assert deactivated.status_code == 200, deactivated.text
    active = get(app, PRODUCTS, world.maya, {"is_active": "true"})
    assert [item["code"] for item in active.json()["items"]] == []
    assert [event["after"] for event in audits(world, "product.update")] == [{"is_active": False}]


def test_mapping_rules_name_products(app: FastAPI, world: World) -> None:
    kit = new_product(app, world.maya, code="AVM-KIT", name="Sensor kit")
    part = new_product(app, world.maya, code="AVM-PART", name="Automotive sensor part")
    accounts = {
        code: gl_account(
            app, world.maya, code=code, name=name, account_type="REVENUE", normal_balance="C"
        )
        for code, name in (("4000", "Revenue - products"), ("4010", "Revenue - services"))
    }
    mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from="2026-01-01T00:00:00Z",
        rules=[
            {"account_role": "REVENUE", "gl_account_id": accounts["4010"]},
            {"account_role": "REVENUE", "gl_account_id": accounts["4000"], "product_id": kit["id"]},
        ],
    )
    resolve_path = f"{ACCOUNT_MAPPINGS}/resolve"
    by_code = get(app, resolve_path, world.maya, {"role": "REVENUE", "product": "AVM-KIT"})
    assert by_code.status_code == 200, by_code.text
    body = by_code.json()
    assert (body["gl_account"]["code"], body["product_id"], body["source"]["specificity"]) == (
        "4000",
        kit["id"],
        2,
    )
    by_id = get(app, resolve_path, world.maya, {"role": "REVENUE", "product": part["id"]})
    assert (by_id.json()["gl_account"]["code"], by_id.json()["product_id"]) == ("4010", part["id"])
    unknown = get(app, resolve_path, world.maya, {"role": "REVENUE", "product": "AVM-NONE"})
    assert fields(unknown) == [("product", "T-REF-15")], unknown.text

    draft = post(app, ACCOUNT_MAPPINGS, world.maya, {"name": "AVM-MAP-2026-02"})
    assert draft.status_code == 201, draft.text
    refused = post(
        app,
        f"{ACCOUNT_MAPPINGS}/{draft.json()['id']}/rules",
        world.maya,
        {
            "account_role": "REVENUE",
            "gl_account_id": accounts["4000"],
            "product_id": str(world.tenant_id),
        },
    )
    assert fields(refused) == [("product_id", "T-REF-15")], refused.text
    added = post(
        app,
        f"{ACCOUNT_MAPPINGS}/{draft.json()['id']}/rules",
        world.maya,
        {"account_role": "REVENUE", "gl_account_id": accounts["4000"], "product_id": part["id"]},
    )
    assert (added.status_code, added.json()["specificity"]) == (201, 2), added.text


def _template(
    app: FastAPI, world: World, approver: Actor, code: str, outputs: dict[str, Any], product: str
) -> str:
    """A PUBLISHED template version (T-REF-20 admits only those as a default) whose one test case
    books ``product``."""
    return published_template(
        app,
        world.maya,
        approver,
        code=code,
        outputs=outputs,
        case_line={
            "obligation_key": "POB-01",
            "product_code": product,
            "quantity": "1",
            "total_price": "1200.00",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
        },
    )["template_id"]


def _template_approver(app: FastAPI, world: World, clock: FrozenClock) -> Actor:
    someone = colleague(world.tenant_id, "marcus")
    for role in ("controller", "ssp_approver", "tenant_admin"):
        assign(someone, role)
    return enrolled(app, clock, someone)


def test_ssp_admission_r1_requires_explicit_ssp_basis_is_derived_from_the_default_template(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """SSP-ADMISSION-R1 / D-97 (3a): ``requires_explicit_ssp_basis`` is true iff the product's
    default POB template has a version of ``series`` distinctness — the admission guard's own
    predicate — whatever ``distinctness_default`` says (Codex's differing-attribute control: a
    ``distinct`` product with a series default template requires the basis); read-only, absent from
    the write schema."""
    maya = world.maya
    plain = new_product(app, maya, code="P-PLAIN", name="No template")
    differing = new_product(
        app, maya, code="P-SERIES", name="Distinct by attribute, series by template"
    )
    assert differing["distinctness_default"] == "distinct"
    units = new_product(app, maya, code="P-UNITS", name="Units template")
    approver = _template_approver(app, world, clock)
    series_template = _template(app, world, approver, "TPL-SER", TPL_SUB_DAILY, "P-SERIES")
    units_template = _template(app, world, approver, "TPL-UNITS", TPL_PROD_UNITS, "P-UNITS")
    set_default_template(app, maya, str(differing["id"]), series_template)
    set_default_template(app, maya, str(units["id"]), units_template)
    assert shown(app, maya, str(plain["id"]))["requires_explicit_ssp_basis"] is False
    assert shown(app, maya, str(differing["id"]))["requires_explicit_ssp_basis"] is True
    assert shown(app, maya, str(units["id"]))["requires_explicit_ssp_basis"] is False
    listed = get(app, PRODUCTS, maya, {"q": "P-", "limit": 50})
    assert listed.status_code == 200, listed.text
    assert {
        item["code"]: item["requires_explicit_ssp_basis"] for item in listed.json()["items"]
    } == {
        "P-PLAIN": False,
        "P-SERIES": True,
        "P-UNITS": False,
    }
    # The member is derived: sending it is refused by the write schema (extra="forbid").
    refused = post(
        app,
        PRODUCTS,
        maya,
        {"code": "P-WRITE", "name": "Writes the flag", "requires_explicit_ssp_basis": True},
    )
    assert refused.status_code == 422, refused.text


# --- a product's policy values change only by approval (SN-7; 04 API-R-23 rev 1.110) -----------

ENTERED = {"material_right.ssp_method": "ENTERED_AMOUNT"}  # POL-026: level P; approval code EST
CONVENTION = "recognition.time_convention"  # POL-090: levels T, P; approval code CFG
BY_APPROVAL = (
    "Policy values of a product change only by approval. Propose a policy values change instead."
)
CONVENTION_RATIONALE = "Seat plans are sold and earned by whole months."


@pytest.mark.control("CTL-031")
def test_sn7_patch_refuses_changed_policy_values(app: FastAPI, world: World) -> None:
    """``PATCH /products/{id}`` no longer stores level-P values (REQ-POL-003): a key that is
    added, changed or removed is refused by name, whatever its approval code, and nothing is
    written. The values of a new product are recorded as sent, and the stored map sent back
    beside another member is no change."""
    kit = new_product(app, world.maya, code="AVM-KIT", name="Sensor kit", policy_values=ENTERED)
    assert (kit["policy_values"], kit["row_version"]) == (ENTERED, 1)

    added = patch(
        app,
        path(kit["id"]),
        world.maya,
        {"policy_values": {**ENTERED, CONVENTION: "MONTHLY_EVEN"}},
        if_match='"r1"',
    )
    assert (added.status_code, slug(added)) == (422, "validation-failed"), added.text
    assert fields(added) == [(f"policy_values.{CONVENTION}", "REQ-POL-003")]
    assert added.json()["errors"][0]["message"] == BY_APPROVAL
    changed = patch(
        app,
        path(kit["id"]),
        world.maya,
        {"policy_values": {"material_right.ssp_method": "RENEWAL_ALTERNATIVE"}, "name": "Kit"},
        if_match='"r1"',
    )
    removed = patch(app, path(kit["id"]), world.maya, {"policy_values": {}}, if_match='"r1"')
    for refused in (changed, removed):
        assert refused.status_code == 422, refused.text
        assert ("policy_values.material_right.ssp_method", "REQ-POL-003") in fields(refused)
    # A value the level does not admit is reported as such, once; the removed key beside it.
    invalid = patch(
        app, path(kit["id"]), world.maya, {"policy_values": {CONVENTION: "NOPE"}}, if_match='"r1"'
    )
    assert fields(invalid) == [
        (f"policy_values.{CONVENTION}", "POLICY_VALUE_INVALID"),
        ("policy_values.material_right.ssp_method", "REQ-POL-003"),
    ]

    # Nothing was written, no request was opened.
    current = shown(app, world.maya, kit["id"])
    assert (
        current["policy_values"],
        current["name"],
        current["row_version"],
        current["pending_approval_request_id"],
    ) == (ENTERED, "Sensor kit", 1, None)
    assert audits(world, "product.update") == []
    assert audits(world, "product.policy_values_change") == []

    # The stored map sent back is no change: the other member is stored.
    renamed = patch(
        app, path(kit["id"]), world.maya, {"policy_values": ENTERED, "name": "Kit"}, if_match='"r1"'
    )
    assert (renamed.status_code, renamed.headers["ETag"]) == (200, '"r2"'), renamed.text
    assert [event["after"] for event in audits(world, "product.update")] == [{"name": "Kit"}]


@pytest.mark.control("CTL-031")
def test_sn7_policy_values_change_through_approval(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """``POST /products/{id}/propose-policy-values-change``: the request of the subject
    ``principal_agent`` uses (``PRINCIPAL_AGENT_CHANGE``). The product keeps its values while the
    request is pending and after a rejection; the proposer cannot approve it; one request per
    product is open at a time, whatever it proposes; another ``config.approve`` holder's approval
    stores exactly the proposed map and leaves the conclusion alone."""
    tomas_member = colleague(world.tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    assign(tomas_member, "controller")
    tomas = enrolled(app, clock, tomas_member)
    kit = new_product(app, world.maya, code="AVM-KIT", name="Sensor kit", policy_values=ENTERED)
    propose_path = path(kit["id"], "/propose-policy-values-change")
    monthly = {**ENTERED, CONVENTION: "MONTHLY_EVEN"}

    # Findings: the stored map, a blank rationale, values the product level does not admit.
    unchanged = post(app, propose_path, world.maya, {"policy_values": ENTERED, "rationale": " "})
    assert fields(unchanged) == [("policy_values", "REQ-POL-003"), ("rationale", "REQ-POL-003")]
    findings = post(
        app,
        propose_path,
        world.maya,
        {
            "policy_values": {
                CONVENTION: "NOPE",
                "pob.principal_or_agent": "AGENT",
                "rounding.posting_mode": "HALF_UP",
            },
            "rationale": CONVENTION_RATIONALE,
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("policy_values.pob.principal_or_agent", "REQ-REF-012"),
        (f"policy_values.{CONVENTION}", "POLICY_VALUE_INVALID"),
        ("policy_values.rounding.posting_mode", "POLICY_LEVEL_NOT_ALLOWED"),
    ]
    unknown = post(
        app,
        path(str(world.tenant_id), "/propose-policy-values-change"),
        world.maya,
        {"policy_values": monthly, "rationale": CONVENTION_RATIONALE},
    )
    assert (unknown.status_code, slug(unknown)) == (404, "not-found"), unknown.text

    # Tomas proposes; the request is the product's pending change and nothing is stored yet.
    proposed = post(
        app,
        propose_path,
        tomas,
        {"policy_values": monthly, "rationale": CONVENTION_RATIONALE},
    )
    assert proposed.status_code == 200, proposed.text
    request_id = proposed.json()["approval_request_id"]
    request = get(app, f"{APPROVALS}/{request_id}", world.carmen).json()
    assert (
        request["subject"]["type"],
        request["subject"]["id"],
        request["subject"]["href"],
        request["status"],
        request["summary"],
        [step["required_permission"] for step in request["steps"]],
    ) == (
        "PRINCIPAL_AGENT_CHANGE",
        kit["id"],
        f"/settings/products/{kit['id']}",
        "PENDING",
        "Policy values change for AVM-KIT",
        ["config.approve"],
    )
    assert request["impact_preview"]["file_id"] is not None
    current = shown(app, world.maya, kit["id"])
    assert (current["policy_values"], current["pending_approval_request_id"]) == (
        ENTERED,
        request_id,
    )

    # One pending change per product, of either kind.
    for again in (
        post(
            app,
            propose_path,
            world.maya,
            {"policy_values": {}, "rationale": "No level-P values after all."},
        ),
        post(
            app,
            path(kit["id"], "/propose-principal-agent-change"),
            world.maya,
            {"principal_agent": "PRINCIPAL", "rationale": RATIONALE},
        ),
    ):
        assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text

    # The proposer holds config.approve and is refused; the product keeps its values.
    refused = approve(app, request_id, tomas)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert shown(app, world.maya, kit["id"])["policy_values"] == ENTERED

    # Another config.approve holder approves: the product holds exactly the proposed map.
    approved = approve(app, request_id, world.carmen)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    current = shown(app, world.maya, kit["id"])
    assert (
        current["policy_values"],
        current["principal_agent"],
        current["pending_approval_request_id"],
        current["row_version"],
    ) == (monthly, "NOT_ASSESSED", None, 2)
    [event] = audits(world, "product.policy_values_change")
    assert (
        str(event["object_id"]),
        event["before"],
        event["after"],
        str(event["approval_request_id"]),
    ) == (kit["id"], {"policy_values": ENTERED}, {"policy_values": monthly}, request_id)
    assert audits(world, "product.principal_agent_change") == []

    # A rejected proposal is not applied, and does not block the next one.
    second = post(
        app,
        propose_path,
        world.maya,
        {"policy_values": {}, "rationale": "Drop the level-P values."},
    )
    assert second.status_code == 200, second.text
    rejected = reject(app, second.json()["approval_request_id"], world.carmen, "Keep them.")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    current = shown(app, world.maya, kit["id"])
    assert (
        current["policy_values"],
        current["pending_approval_request_id"],
        current["row_version"],
    ) == (monthly, None, 2)
    assert len(audits(world, "product.policy_values_change")) == 1
    third = post(
        app, propose_path, world.maya, {"policy_values": ENTERED, "rationale": "Daily after all."}
    )
    assert third.status_code == 200, third.text
    assert shown(app, world.maya, kit["id"])["policy_values"] == monthly


def code_frozen(holders: str) -> tuple[int, str, list[tuple[str | None, str | None]], str]:
    """The refusal of a changed code: status, slug, fields and the message naming the holders."""
    return (
        422,
        "validation-failed",
        [("code", "DB-05")],
        products.CODE_FROZEN.format(holders=holders),
    )


def recoded(app: FastAPI, world: World, product_id: str, code: str) -> Any:
    answer = patch(
        app,
        path(product_id),
        world.maya,
        {"code": code},
        if_match=f'"r{shown(app, world.maya, product_id)["row_version"]}"',
    )
    if answer.status_code == 200:
        return answer.json()["code"]
    return (answer.status_code, slug(answer), fields(answer), answer.json()["errors"][0]["message"])


def test_db_05_the_code_of_a_product_in_use_is_frozen(app: FastAPI, world: World) -> None:
    """Item PRODUCT-CODE-FREEZE-1. Contract lines, a contract's product pin and the engine's
    bundle name a product by its code, while SSP entries and mapping rules hold its id: a product
    renamed in use left its contracts without an SSP entry (``SSP_KEY_NOT_FOUND`` at their next
    computation). The code changes while nothing references the product; an account mapping rule,
    an SSP entry and a contract line each freeze it, by name, and every other member still
    changes. The database refuses the same update (``tests/pg/test_db_invariants.py``)."""
    free = new_product(app, world.maya, code="AVM-FREE", name="Unused product")
    assert recoded(app, world, free["id"], "AVM-FREE-2") == "AVM-FREE-2"
    assert [event["after"] for event in audits(world, "product.update")] == [{"code": "AVM-FREE-2"}]

    # An account mapping rule of a draft version, through its route.
    kit = new_product(app, world.maya, code="AVM-KIT", name="Sensor kit")
    account = gl_account(
        app,
        world.maya,
        code="4000",
        name="Revenue - products",
        account_type="REVENUE",
        normal_balance="C",
    )
    draft = post(app, ACCOUNT_MAPPINGS, world.maya, {"name": "AVM-MAP-2026-01"})
    assert draft.status_code == 201, draft.text
    rule = post(
        app,
        f"{ACCOUNT_MAPPINGS}/{draft.json()['id']}/rules",
        world.maya,
        {"account_role": "REVENUE", "gl_account_id": account, "product_id": kit["id"]},
    )
    assert rule.status_code == 201, rule.text
    assert recoded(app, world, kit["id"], "AVM-KIT-2") == code_frozen("account mapping rules")

    # An SSP entry and a contract line, as rows.
    priced = new_product(app, world.maya, code="AVM-PRICED", name="Priced product")
    with tenant_session(tenant_context(world)) as session:
        book = ssp_book_values(world.tenant_id)
        session.execute(insert(ssp_book).values(**book))
        version = ssp_book_version_values(world.tenant_id, ssp_book_id=book["id"])
        session.execute(insert(ssp_book_version).values(**version))
        session.execute(
            insert(ssp_entry).values(
                **ssp_entry_values(
                    world.tenant_id,
                    ssp_book_version_id=version["id"],
                    product_id=UUID(priced["id"]),
                )
            )
        )
        # A contract version of price 0 needs no allocated obligation version (DB-17).
        rows = insert_version_rows(session, world.tenant_id, transaction_price=Decimal("0"))
        insert_obligation_rows(session, world.tenant_id, rows)
        sold_id = str(
            session.execute(
                select(obligation.c.product_id).where(obligation.c.tenant_id == world.tenant_id)
            ).scalar_one()
        )
    assert recoded(app, world, priced["id"], "AVM-PRICED-2") == code_frozen("SSP entries")
    assert recoded(app, world, sold_id, "AVM-SOLD-2") == code_frozen("contract lines")
    with tenant_session(tenant_context(world), read_only=True) as session:
        assert products.code_references(session, UUID(free["id"])) == []
        assert products.code_references(session, UUID(sold_id)) == ["contract lines"]

    # Nothing of a refused change is stored, and the other members of a product in use change.
    assert shown(app, world.maya, kit["id"])["code"] == "AVM-KIT"
    named = patch(app, path(kit["id"]), world.maya, {"name": "Sensor kit, boxed"}, if_match='"r1"')
    assert (named.status_code, named.json()["name"]) == (200, "Sensor kit, boxed"), named.text


def test_code_frozen_is_the_refusal_of_a_changed_code_read_in_advance(
    app: FastAPI, world: World
) -> None:
    """04 API-R-23 (the product read model's ``code_frozen``; DB-05): true when a contract line,
    an SSP entry or an account mapping rule references the product — on the single read, in a row
    of the list and in the answers of POST and PATCH. It is the predicate of the update command's
    refusal (``products.code_holders``): a product that reads false is recoded, one that reads
    true is refused by name, and a product whose last holder is gone reads false again. The list
    reads the member for its page in one statement (DG-LST-10). Before: no read carried it — the
    product drawer offered a Code field the server refused."""
    maya = world.maya
    free = new_product(app, maya, code="AVM-FREE", name="Unused product")
    assert free["code_frozen"] is False  # the answer of POST

    kit = new_product(app, maya, code="AVM-KIT", name="Sensor kit")
    account = gl_account(
        app,
        maya,
        code="4000",
        name="Revenue - products",
        account_type="REVENUE",
        normal_balance="C",
    )
    draft = post(app, ACCOUNT_MAPPINGS, maya, {"name": "AVM-MAP-2026-01"})
    assert draft.status_code == 201, draft.text
    rules = f"{ACCOUNT_MAPPINGS}/{draft.json()['id']}/rules"
    rule = post(
        app,
        rules,
        maya,
        {"account_role": "REVENUE", "gl_account_id": account, "product_id": kit["id"]},
    )
    assert rule.status_code == 201, rule.text
    priced = new_product(app, maya, code="AVM-PRICED", name="Priced product")
    with tenant_session(tenant_context(world)) as session:
        book = ssp_book_values(world.tenant_id)
        session.execute(insert(ssp_book).values(**book))
        version = ssp_book_version_values(world.tenant_id, ssp_book_id=book["id"])
        session.execute(insert(ssp_book_version).values(**version))
        session.execute(
            insert(ssp_entry).values(
                **ssp_entry_values(
                    world.tenant_id,
                    ssp_book_version_id=version["id"],
                    product_id=UUID(priced["id"]),
                )
            )
        )
        # A contract version of price 0 needs no allocated obligation version (DB-17).
        rows = insert_version_rows(session, world.tenant_id, transaction_price=Decimal("0"))
        insert_obligation_rows(session, world.tenant_id, rows)
        sold_id = str(
            session.execute(
                select(obligation.c.product_id).where(obligation.c.tenant_id == world.tenant_id)
            ).scalar_one()
        )
    sold_code = str(shown(app, maya, sold_id)["code"])
    expected = {"AVM-FREE": False, "AVM-KIT": True, "AVM-PRICED": True, sold_code: True}
    ids = {
        "AVM-FREE": free["id"],
        "AVM-KIT": kit["id"],
        "AVM-PRICED": priced["id"],
        sold_code: sold_id,
    }

    # The single read and the row of the list say the same.
    assert {code: shown(app, maya, ids[code])["code_frozen"] for code in ids} == expected

    def listed(limit: int) -> tuple[dict[str, bool], list[str]]:
        with sent() as seen:
            page = get(app, PRODUCTS, maya, {"limit": limit})
        assert page.status_code == 200, page.text
        flags = {item["code"]: item["code_frozen"] for item in page.json()["items"]}
        return flags, [statement for statement, _ in seen]

    flags, of_all = listed(50)
    assert flags == expected
    one, of_one = listed(1)
    assert one == {min(expected): expected[min(expected)]}  # sorted by code
    # ... for a page in one statement, whatever the page holds (DG-LST-10)
    assert len(of_all) == len(of_one)
    for statements in (of_all, of_one):
        assert sum("erev.ssp_entry" in statement for statement in statements) == 1
        assert sum("erev.account_mapping_rule" in statement for statement in statements) == 1

    # The member is the command's refusal, read in advance.
    with tenant_session(tenant_context(world), read_only=True) as session:
        assert products.code_holders(session, [UUID(value) for value in ids.values()]) == {
            UUID(kit["id"]): ["account mapping rules"],
            UUID(priced["id"]): ["SSP entries"],
            UUID(sold_id): ["contract lines"],
        }
        # ... for the products asked about and no other
        assert products.code_holders(session, [UUID(free["id"]), UUID(kit["id"])]) == {
            UUID(kit["id"]): ["account mapping rules"]
        }
        assert products.code_holders(session, [UUID(free["id"])]) == {}
        assert products.code_holders(session, []) == {}
    assert recoded(app, world, kit["id"], "AVM-KIT-2") == code_frozen("account mapping rules")
    assert recoded(app, world, priced["id"], "AVM-PRICED-2") == code_frozen("SSP entries")
    assert recoded(app, world, sold_id, f"{sold_code}-2") == code_frozen("contract lines")
    named = patch(app, path(kit["id"]), maya, {"name": "Sensor kit, boxed"}, if_match='"r1"')
    assert named.status_code == 200, named.text
    assert named.json()["code_frozen"] is True  # the answer of PATCH

    # A product whose last holder is gone is free again: the member is derived, never stored.
    removed = delete(app, f"{rules}/{rule.json()['id']}", maya)
    assert removed.status_code == 204, removed.text
    assert shown(app, maya, kit["id"])["code_frozen"] is False
    assert recoded(app, world, kit["id"], "AVM-KIT-2") == "AVM-KIT-2"
    assert recoded(app, world, free["id"], "AVM-FREE-2") == "AVM-FREE-2"

    # ... and it is read-only: the write schemas refuse it (extra="forbid").
    refused = post(
        app, PRODUCTS, maya, {"code": "P-WRITE", "name": "Writes it", "code_frozen": False}
    )
    assert refused.status_code == 422, refused.text
    refused = patch(app, path(free["id"]), maya, {"code_frozen": True}, if_match='"r2"')
    assert refused.status_code == 422, refused.text


# --- a level P value no computation reads (item PRODUCT-POLICY-VALUE-NOT-READ-1; PRD ERR-103) --

TIER_METHOD = "usage.tier_minimum_method"  # POL-240: levels P and C; default DERIVED
BENEFIT_PERIOD = "upfront_fee.recognition_period"  # POL-029: level P alone
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021: levels T, E and P
NOT_READ = "POLICY_PRODUCT_LEVEL_NOT_READ"
DEFAULTS = {TIER_METHOD: "DERIVED", BENEFIT_PERIOD: "EXPECTED_BENEFIT_PERIOD"}
# PRD ERR-103, the two sentences as ruled, each naming its parameter by the code;
# ``tests/unit/policies/test_level_p_not_read.py`` holds the product's constants to them.
DEFAULT_APPLIES = (
    "This release reads {key} from no product or template. The framework's default applies to "
    "every contract: leave it out, or state the default."
)
REGISTRY_APPLIES = (
    "This release reads {key} from no product or template. The entity's or the workspace's "
    "value applies where the framework does not fix it: set it by a policy version."
)


def answered(response: Any) -> list[tuple[str | None, str | None, str]]:
    """Field, rule id and sentence of each error of a refusal."""
    return [
        (error["field"], error["rule_id"], error["message"]) for error in response.json()["errors"]
    ]


def not_read(key: str) -> tuple[str, str, str]:
    """The error of PRD ERR-103 for parameter ``key``: its field, the rule id and the sentence of
    the parameter, which names it."""
    sentence = REGISTRY_APPLIES if key == SHIPPING else DEFAULT_APPLIES
    return (f"policy_values.{key}", NOT_READ, sentence.format(key=key))


def test_err_103_a_level_p_value_no_computation_reads_is_refused_at_each_door_of_a_product(
    app: FastAPI, world: World
) -> None:
    """Item PRODUCT-POLICY-VALUE-NOT-READ-1 (register index 309; 04 T-REF-20 rev 1.323; POLICIES
    §0.5 rule 1 rev 1.125; PRD ERR-103). The engine reads POL-240, POL-029 and POL-021 for a
    contract, and a product's value is given to it for an obligation, so a value stated here was
    stored and taken by no rule. The three doors of a product — its creation, its direct change
    and the proposal of a change — refuse it by name with what applies instead and store
    nothing. The framework's default of POL-240 and of POL-029 is the value every contract
    takes and may be stated; no value of POL-021 may. Each door takes an admitted map: the
    refusal is the value's."""
    # The creation: one error a key, beside a value the check admits.
    refused = post(
        app,
        PRODUCTS,
        world.maya,
        {
            "code": "AVM-USAGE",
            "name": "Usage plan",
            "policy_values": {
                **ENTERED,
                TIER_METHOD: "ESTIMATE_MEASUREMENT_PERIOD_TP",
                BENEFIT_PERIOD: "CONTRACT_TERM",
                SHIPPING: "FALSE",
            },
        },
    )
    assert refused.status_code == 422, refused.text  # before the rule: 201, the values stored
    assert slug(refused) == "validation-failed"
    assert answered(refused) == [
        not_read(SHIPPING),
        not_read(BENEFIT_PERIOD),
        not_read(TIER_METHOD),
    ]
    assert refused.json()["errors"][2]["message"] == (
        "This release reads usage.tier_minimum_method from no product or template. The "
        "framework's default applies to every contract: leave it out, or state the default."
    )
    for value in ("TRUE", "FALSE"):  # the default of each framework is a value like any other
        elected = post(
            app,
            PRODUCTS,
            world.maya,
            {"code": "AVM-USAGE", "name": "Usage plan", "policy_values": {SHIPPING: value}},
        )
        assert answered(elected) == [not_read(SHIPPING)], value
    assert get(app, PRODUCTS, world.maya).json()["items"] == []
    stated = {**ENTERED, **DEFAULTS}
    usage = new_product(app, world.maya, code="AVM-USAGE", name="Usage plan", policy_values=stated)
    assert (usage["policy_values"], usage["row_version"]) == (stated, 1)

    # The direct change: the refusal is this one alone, not also "by approval".
    for values, expected in (
        ({**stated, TIER_METHOD: "ESTIMATE_MEASUREMENT_PERIOD_TP"}, [not_read(TIER_METHOD)]),
        ({**stated, BENEFIT_PERIOD: "CONTRACT_TERM"}, [not_read(BENEFIT_PERIOD)]),
        ({**stated, SHIPPING: "TRUE"}, [not_read(SHIPPING)]),
    ):
        changed = patch(
            app, path(usage["id"]), world.maya, {"policy_values": values}, if_match='"r1"'
        )
        assert (changed.status_code, slug(changed)) == (422, "validation-failed"), changed.text
        assert answered(changed) == expected

    # The proposal of a change: refused before a request is opened.
    propose_path = path(usage["id"], "/propose-policy-values-change")
    proposal = post(
        app,
        propose_path,
        world.maya,
        {
            "policy_values": {**ENTERED, BENEFIT_PERIOD: "CONTRACT_TERM", SHIPPING: "FALSE"},
            "rationale": CONVENTION_RATIONALE,
        },
    )
    assert (proposal.status_code, slug(proposal)) == (422, "validation-failed"), proposal.text
    assert answered(proposal) == [not_read(SHIPPING), not_read(BENEFIT_PERIOD)]

    # Nothing was written and no request was opened.
    current = shown(app, world.maya, usage["id"])
    assert (
        current["policy_values"],
        current["row_version"],
        current["pending_approval_request_id"],
    ) == (stated, 1, None)
    assert audits(world, "product.update") == []
    assert audits(world, "product.policy_values_change") == []

    # The same roads take what the check admits: the stored map beside another member, and a
    # proposal that drops a stated default, which the approval stores.
    renamed = patch(
        app,
        path(usage["id"]),
        world.maya,
        {"policy_values": stated, "name": "Usage plan, metered"},
        if_match='"r1"',
    )
    assert (renamed.status_code, renamed.headers["ETag"]) == (200, '"r2"'), renamed.text
    fewer = {**ENTERED, TIER_METHOD: "DERIVED"}
    proposed = post(
        app, propose_path, world.maya, {"policy_values": fewer, "rationale": CONVENTION_RATIONALE}
    )
    assert proposed.status_code == 200, proposed.text
    approved = approve(app, proposed.json()["approval_request_id"], world.carmen)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    assert shown(app, world.maya, usage["id"])["policy_values"] == fewer
