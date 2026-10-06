"""Account-role mapping versions and account resolution (04 T-REF-14, T-REF-15, E-01, E-109, DB-04,
§15.2 ``unmapped-account-role``, §15.4 ``ACCOUNT_MAPPING_MISSING``; POLICIES §0.8; PRD §2.6, ERR-46;
legacy 06 §7.3 TC-JE-12; 03 REQ-REF-008, REQ-POL-002; CTL-031; BUILD_SPEC RFD-7).

Maya holds Revenue Accountant (``config.author``, ``masterdata.maintain``) and authors mapping
versions; Carmen holds Controller (``config.approve``), is enrolled in MFA and approves them; Omar
holds Viewer (docs/02-PRD.md §5.6). The workspace has a January calendar with FY2026, the entities
AVM-US and AVM-DE and the PRD §2.6 accounts the tests map. The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import engine
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event
from erev_api.domain.reference import mapping
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.principals import Actor, colleague, enrolled, member
from support.reference import (
    ACCOUNT_MAPPINGS,
    APPROVALS,
    approve,
    assign,
    calendar,
    delete,
    entity,
    fields,
    get,
    gl_account,
    holding,
    mapping_draft,
    mapping_published,
    mapping_submitted,
    patch,
    post,
    slug,
)

KNOWN_AT = datetime(2026, 9, 12, 12, tzinfo=UTC)
JANUARY = "2026-01-01T00:00:00Z"
OCTOBER = "2026-10-01T00:00:00Z"
ACCOUNTS = (
    ("1105", "Unbilled receivable", "ASSET", "D"),
    ("2090", "Subledger clearing", "LIABILITY", "C"),
    ("2100", "Contract liability", "LIABILITY", "C"),
    ("2105", "Deposit liability", "LIABILITY", "C"),
    ("4000", "Revenue - products", "REVENUE", "C"),
    ("4010", "Revenue - services and subscriptions", "REVENUE", "C"),
    ("4020", "Revenue - licences and royalties", "REVENUE", "C"),
    ("5001", "Legacy POB revenue account", "REVENUE", "C"),
)
PURPOSES = ("BILLING", "UNAPPLIED_CASH", "AP_SUPPLIER", "INVENTORY", "EQUITY", "INVESTMENTS")


@dataclass(frozen=True, slots=True)
class World:
    maya: Actor
    carmen: Actor
    calendar_id: str
    us: str
    de: str
    accounts: dict[str, str]

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
    calendar_id = calendar(app, maya)
    us = entity(app, maya, code="AVM-US", calendar_id=calendar_id)["id"]
    de = entity(
        app,
        maya,
        code="AVM-DE",
        calendar_id=calendar_id,
        functional_currency="EUR",
        time_zone="Europe/Berlin",
    )["id"]
    accounts = {
        code: gl_account(
            app, maya, code=code, name=name, account_type=kind, normal_balance=normal_balance
        )
        for code, name, kind, normal_balance in ACCOUNTS
    }
    return World(maya=maya, carmen=carmen, calendar_id=calendar_id, us=us, de=de, accounts=accounts)


def rule(world: World, role: str, code: str, **extra: Any) -> dict[str, Any]:
    return {"account_role": role, "gl_account_id": world.accounts[code], **extra}


def path(version_id: str, suffix: str = "") -> str:
    return f"{ACCOUNT_MAPPINGS}/{version_id}{suffix}"


def resolve(world: World, **kwargs: Any) -> mapping.Resolution:
    """``mapping.resolve_account`` in a read-only session of the workspace (all entities)."""
    known_at = kwargs.pop("known_at", KNOWN_AT)
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        return mapping.resolve_account(session, known_at=known_at, **kwargs)


def instant(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def test_clearing_purpose_required_only_for_billing_clearing(app: FastAPI, world: World) -> None:
    draft = mapping_draft(app, world.maya, name="AVM-MAP-2026-01", effective_from=JANUARY, rules=[])
    rules_path = path(draft["id"], "/rules")

    missing = post(app, rules_path, world.maya, rule(world, "BILLING_CLEARING", "2090"))
    assert (missing.status_code, slug(missing)) == (422, "validation-failed"), missing.text
    assert fields(missing) == [("clearing_purpose", "T-REF-15")]
    assert missing.json()["errors"][0]["message"] == (
        "Choose a clearing purpose for billing clearing."
    )

    extra = post(
        app, rules_path, world.maya, rule(world, "REVENUE", "4010", clearing_purpose="BILLING")
    )
    assert (extra.status_code, slug(extra)) == (422, "validation-failed"), extra.text
    assert fields(extra) == [("clearing_purpose", "T-REF-15")]
    assert extra.json()["errors"][0]["message"] == (
        "A clearing purpose applies only to billing clearing."
    )

    unknown = post(
        app, rules_path, world.maya, rule(world, "BILLING_CLEARING", "2090", clearing_purpose="TAX")
    )
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text

    added = post(
        app,
        rules_path,
        world.maya,
        rule(world, "BILLING_CLEARING", "2090", clearing_purpose="UNAPPLIED_CASH"),
    )
    assert added.status_code == 201, added.text
    body = added.json()
    assert (body["account_role"], body["clearing_purpose"], body["specificity"]) == (
        "BILLING_CLEARING",
        "UNAPPLIED_CASH",
        0,
    )
    assert body["gl_account"] == {
        "id": world.accounts["2090"],
        "code": "2090",
        "name": "Subledger clearing",
    }
    listed = get(app, rules_path, world.maya)
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]


def test_reserved_roles_accept_no_rule(app: FastAPI, world: World) -> None:
    draft = mapping_draft(app, world.maya, name="AVM-MAP-2026-01", effective_from=JANUARY, rules=[])
    rules_path = path(draft["id"], "/rules")
    for role, label in (
        ("RETAINED_EARNINGS", "Retained earnings (reserved)"),
        ("FINANCING_OBLIGATION", "Financing obligation (reserved)"),
    ):
        refused = post(app, rules_path, world.maya, rule(world, role, "2100"))
        assert (refused.status_code, slug(refused)) == (422, "validation-failed"), refused.text
        assert fields(refused) == [("account_role", "T-REF-15")]
        assert refused.json()["errors"][0]["message"] == (
            f"{label} is reserved: no mapping rule is allowed."
        )
    assert get(app, rules_path, world.maya).json()["items"] == []
    assert get(app, path(draft["id"]), world.maya).json()["rule_count"] == 0


def test_resolution_precedence(app: FastAPI, world: World) -> None:
    published = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[
            rule(world, "REVENUE", "4010"),
            rule(world, "REVENUE", "4000", entity_id=world.us, revenue_category="PRODUCT"),
        ],
    )
    us, de = UUID(world.us), UUID(world.de)

    # Step 3: the most specific rule of the PUBLISHED version.
    product_us = resolve(world, role="REVENUE", entity_id=us, revenue_category="PRODUCT")
    assert (
        product_us.gl_account_code,
        product_us.specificity,
        product_us.source_type,
        product_us.version_no,
    ) == ("4000", 10, "account_mapping_rule", 1)
    assert str(product_us.account_mapping_version_id) == published["id"]
    product_de = resolve(world, role="REVENUE", entity_id=de, revenue_category="PRODUCT")
    assert (product_de.gl_account_code, product_de.specificity) == ("4010", 0)

    # Step 2: the template override wins over both rules.
    template = {"REVENUE": world.accounts["4020"]}
    by_template = resolve(
        world, role="REVENUE", entity_id=us, revenue_category="PRODUCT", template_overrides=template
    )
    assert (by_template.gl_account_code, by_template.source_type, by_template.rule_id) == (
        "4020",
        "template_override",
        None,
    )

    # Step 1: the obligation override wins over the template override.
    by_obligation = resolve(
        world,
        role="REVENUE",
        entity_id=us,
        revenue_category="PRODUCT",
        template_overrides=template,
        obligation_overrides={"REVENUE": world.accounts["5001"]},
    )
    assert (by_obligation.gl_account_code, by_obligation.source_type) == (
        "5001",
        "obligation_override",
    )

    # An override of another role does not apply.
    other = resolve(
        world, role="REVENUE", entity_id=de, obligation_overrides={"CONTRACT_LIABILITY": us}
    )
    assert other.gl_account_code == "4010"

    # The resolve route answers the same rule.
    routed = get(
        app,
        f"{ACCOUNT_MAPPINGS}/resolve",
        world.maya,
        {"role": "REVENUE", "entity": "AVM-US", "revenue_category": "PRODUCT"},
    )
    assert routed.status_code == 200, routed.text
    assert (routed.json()["gl_account"]["code"], routed.json()["source"]["specificity"]) == (
        "4000",
        10,
    )


def test_billing_clearing_by_purpose(app: FastAPI, world: World) -> None:
    published = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[rule(world, "BILLING_CLEARING", "2090", clearing_purpose=p) for p in PURPOSES],
    )
    assert published["rule_count"] == 6
    us = UUID(world.us)
    resolved = {
        purpose: resolve(world, role="BILLING_CLEARING", clearing_purpose=purpose, entity_id=us)
        for purpose in PURPOSES
    }
    assert {
        purpose: (item.gl_account_code, item.override_key) for purpose, item in resolved.items()
    } == {purpose: ("2090", f"BILLING_CLEARING:{purpose}") for purpose in PURPOSES}
    assert len({item.rule_id for item in resolved.values()}) == 6

    # The override key names the purpose, so it answers for that purpose only.
    overrides = {
        "BILLING_CLEARING:UNAPPLIED_CASH": world.accounts["2090"],
        "BILLING_CLEARING": world.accounts["2100"],
    }
    unapplied = resolve(
        world,
        role="BILLING_CLEARING",
        clearing_purpose="UNAPPLIED_CASH",
        template_overrides=overrides,
    )
    assert (unapplied.gl_account_code, unapplied.source_type, unapplied.override_key) == (
        "2090",
        "template_override",
        "BILLING_CLEARING:UNAPPLIED_CASH",
    )
    billing = resolve(
        world, role="BILLING_CLEARING", clearing_purpose="BILLING", template_overrides=overrides
    )
    assert (billing.gl_account_code, billing.source_type) == ("2090", "account_mapping_rule")

    # A clearing line without its purpose matches no rule and fails closed.
    with pytest.raises(Problem) as raised:
        resolve(world, role="BILLING_CLEARING", entity_id=us)
    assert raised.value.slug == "unmapped-account-role"


def test_publish_lint_rejects_ambiguous_rules(app: FastAPI, world: World) -> None:
    twin = rule(
        world, "REVENUE", "4000", entity_id=world.us, revenue_category="PRODUCT", priority=5
    )
    draft = mapping_draft(
        app,
        world.maya,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[twin, {**twin, "gl_account_id": world.accounts["4010"]}],
    )
    message = (
        "Rules 1 and 2 resolve the same role, clearing purpose and key with equal specificity "
        "and priority."
    )
    published = post(app, path(draft["id"], "/publish"), world.maya, {})
    assert (published.status_code, slug(published)) == (422, "validation-failed"), published.text
    assert [
        (error["field"], error["rule_id"], error["message"]) for error in published.json()["errors"]
    ] == [("rules", "REQ-POL-002", message)]
    tested = post(app, path(draft["id"], "/test"), world.maya, {})
    assert (tested.status_code, fields(tested)) == (422, [("rules", "REQ-POL-002")]), tested.text
    assert get(app, path(draft["id"]), world.maya).json()["status"] == "DRAFT"

    # Another priority separates the rules.
    rules = get(app, path(draft["id"], "/rules"), world.maya).json()["items"]
    removed = delete(app, path(draft["id"], f"/rules/{rules[1]['id']}"), world.maya)
    assert removed.status_code == 204, removed.text
    readded = post(
        app,
        path(draft["id"], "/rules"),
        world.maya,
        {**twin, "gl_account_id": world.accounts["4010"], "priority": 6},
    )
    assert readded.status_code == 201, readded.text
    retested = post(app, path(draft["id"], "/test"), world.maya, {})
    assert retested.status_code == 200, retested.text
    assert retested.json()["status"] == "TESTED"
    assert retested.json()["content_sha256"] is not None


def test_effective_dated_versions(app: FastAPI, world: World) -> None:
    first = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[rule(world, "CONTRACT_LIABILITY", "2100")],
    )
    second = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-10",
        effective_from=OCTOBER,
        rules=[rule(world, "CONTRACT_LIABILITY", "2105")],
    )
    listed = get(app, ACCOUNT_MAPPINGS, world.maya).json()["items"]
    assert [
        (
            item["version_no"],
            item["status"],
            instant(item["effective_from"]),
            instant(item["effective_to"]),
            item["rule_count"],
            item["supersedes_version_id"],
        )
        for item in listed
    ] == [
        (2, "PUBLISHED", datetime(2026, 10, 1, tzinfo=UTC), None, 1, first["id"]),
        (
            1,
            "PUBLISHED",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
            1,
            None,
        ),
    ]

    september = resolve(
        world, role="CONTRACT_LIABILITY", known_at=datetime(2026, 9, 12, tzinfo=UTC)
    )
    assert (september.gl_account_code, september.version_no) == ("2100", 1)
    october = resolve(world, role="CONTRACT_LIABILITY", known_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert (october.gl_account_code, october.version_no) == ("2105", 2)
    with pytest.raises(Problem) as before:
        resolve(world, role="CONTRACT_LIABILITY", known_at=datetime(2025, 12, 31, tzinfo=UTC))
    assert before.value.slug == "unmapped-account-role"

    # A version effective in June would overlap version 2, so its approval refuses publication.
    june = mapping_submitted(
        app,
        world.maya,
        name="AVM-MAP-2026-06",
        effective_from="2026-06-01T00:00:00Z",
        rules=[rule(world, "CONTRACT_LIABILITY", "2090")],
    )
    overlap = approve(app, june["pending_approval_request_id"], world.carmen)
    assert (overlap.status_code, slug(overlap)) == (409, "configuration-overlap"), overlap.text
    assert overlap.json()["code"] == "EREV-CFG-001"
    assert fields(overlap) == [("effective_from", "DB-04")]
    assert overlap.json()["errors"][0]["message"] == (
        "The effective range of this version overlaps published version 2."
    )
    assert get(app, path(june["id"]), world.maya).json()["status"] == "SUBMITTED"
    kept = get(app, path(first["id"]), world.maya).json()
    assert (kept["status"], instant(kept["effective_to"])) == (
        "PUBLISHED",
        datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert get(app, path(second["id"]), world.carmen).json()["status"] == "PUBLISHED"

    # Publication audits the end of version 1 and the publication of version 2.
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        actions = session.execute(
            select(audit_event.c.action, audit_event.c.object_id)
            .where(audit_event.c.object_type == "account_mapping_version")
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert [
        (action, str(object_id))
        for action, object_id in actions
        if action
        in {
            "account_mapping_version.end",
            "account_mapping_version.published",
        }
    ] == [
        ("account_mapping_version.published", first["id"]),
        ("account_mapping_version.end", first["id"]),
        ("account_mapping_version.published", second["id"]),
    ]


def test_tc_je_12_missing_unbilled_account_names_contract_and_pob(
    app: FastAPI, world: World
) -> None:
    mock = entity(app, world.maya, code="Mock Entity 1", calendar_id=world.calendar_id)["id"]
    mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[rule(world, "CONTRACT_LIABILITY", "2100")],
    )
    with pytest.raises(Problem) as raised:
        resolve(
            world,
            role="UNBILLED_RECEIVABLE",
            entity_id=UUID(mock),
            book_code="ASC606",
            contract="Contract 2",
            obligation_key="POB #1",
            obligation_overrides={},
            template_overrides={},
        )
    problem = raised.value
    assert (problem.slug, problem.status) == ("unmapped-account-role", 422)
    body = problem.to_json(instance="urn:erev:request:tc-je-12")
    first = body["errors"][0]
    assert {name: first[name] for name in ("rule_id", "contract", "obligation_key", "role")} == {
        "rule_id": "ACCOUNT_MAPPING_MISSING",
        "contract": "Contract 2",
        "obligation_key": "POB #1",
        "role": "UNBILLED_RECEIVABLE",
    }
    assert (first["clearing_purpose"], first["entity"]) == (None, "Mock Entity 1")
    copy = (
        "No account is mapped for role Unbilled receivable for Mock Entity 1. "
        "Publish an account mapping, then retry."
    )
    assert first["message"] == body["detail"] == copy

    # The resolve route answers the same problem.
    routed = get(
        app,
        f"{ACCOUNT_MAPPINGS}/resolve",
        world.maya,
        {"role": "UNBILLED_RECEIVABLE", "entity": "Mock Entity 1", "book": "ASC606"},
    )
    assert (routed.status_code, slug(routed)) == (422, "unmapped-account-role"), routed.text
    assert (routed.json()["errors"][0]["rule_id"], routed.json()["detail"]) == (
        "ACCOUNT_MAPPING_MISSING",
        copy,
    )


@pytest.mark.control("CTL-031")
def test_ctl_031_mapping_publish_requires_approval(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    tomas_member = colleague(world.tenant_id, "tomas")
    assign(tomas_member, "revenue_accountant")
    assign(tomas_member, "controller")
    tomas = enrolled(app, clock, tomas_member)
    submitted = mapping_submitted(
        app,
        tomas,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[rule(world, "CONTRACT_LIABILITY", "2100")],
    )
    version_id = submitted["id"]
    request_id = submitted["pending_approval_request_id"]
    assert request_id is not None
    assert submitted["impact_simulation_file_id"] is not None

    # A SUBMITTED version is not published by /publish and resolves nothing.
    early = post(app, path(version_id, "/publish"), tomas, {})
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    with pytest.raises(Problem):
        resolve(world, role="CONTRACT_LIABILITY")

    # Its author, who holds config.approve, is refused.
    refused = approve(app, request_id, tomas)
    assert (refused.status_code, slug(refused)) == (403, "self-approval"), refused.text
    assert get(app, path(version_id), tomas).json()["status"] == "SUBMITTED"
    with pytest.raises(Problem):
        resolve(world, role="CONTRACT_LIABILITY")

    # Another user's approval publishes it.
    approved = approve(app, request_id, world.carmen)
    assert approved.status_code == 200, approved.text
    shown = get(app, path(version_id), tomas).json()
    assert (
        shown["status"],
        shown["approval_request_id"],
        shown["pending_approval_request_id"],
    ) == (
        "PUBLISHED",
        request_id,
        None,
    )
    assert shown["published_by"] not in (None, submitted["created_by"])
    assert resolve(world, role="CONTRACT_LIABILITY").gl_account_code == "2100"
    again = post(app, path(version_id, "/publish"), tomas, {})
    assert (again.status_code, again.json()["status"]) == (200, "PUBLISHED"), again.text


def test_mapping_version_authoring(app: FastAPI, world: World) -> None:
    omar = holding(app, colleague(world.tenant_id, "omar"), "viewer")
    denied = post(app, ACCOUNT_MAPPINGS, omar, {"name": "AVM-MAP-2026-01"})
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text

    created = post(
        app, ACCOUNT_MAPPINGS, world.maya, {"name": " AVM-MAP-2026-01 ", "notes": "PRD §2.6 chart"}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert created.headers["ETag"] == '"r1"'
    assert created.headers["Location"] == path(body["id"])
    assert (body["name"], body["version_no"], body["status"], body["rule_count"]) == (
        "AVM-MAP-2026-01",
        1,
        "DRAFT",
        0,
    )
    second = post(app, ACCOUNT_MAPPINGS, world.maya, {"name": "AVM-MAP-2026-02"})
    assert (second.status_code, slug(second)) == (409, "invalid-transition"), second.text
    assert fields(second) == [("status", "SM-04")]

    version_path = path(body["id"])
    unguarded = patch(app, version_path, world.maya, {"effective_from": JANUARY}, if_match=None)
    assert unguarded.status_code == 428, unguarded.text
    stale = patch(app, version_path, world.maya, {"effective_from": JANUARY}, if_match='"r9"')
    assert stale.status_code == 412, stale.text
    blank = patch(app, version_path, world.maya, {"name": " "}, if_match='"r1"')
    assert (blank.status_code, fields(blank)) == (422, [("name", "T-REF-14")]), blank.text
    dated = patch(app, version_path, world.maya, {"effective_from": JANUARY}, if_match='"r1"')
    assert dated.status_code == 200, dated.text
    assert dated.headers["ETag"] == '"r2"'
    assert instant(dated.json()["effective_from"]) == datetime(2026, 1, 1, tzinfo=UTC)

    rules_path = path(body["id"], "/rules")
    probe = str(world.tenant_id)
    findings = post(
        app,
        rules_path,
        world.maya,
        {
            "account_role": "REVENUE",
            "gl_account_id": probe,
            "entity_id": probe,
            "product_id": probe,
            "revenue_category": "PRODUCT",
            "default_dimensions": {"region": "EU", "department": "NOPE"},
        },
    )
    assert (findings.status_code, slug(findings)) == (422, "validation-failed"), findings.text
    assert fields(findings) == [
        ("entity_id", "T-REF-15"),
        ("product_id", "T-REF-15"),
        ("revenue_category", "T-REF-15"),
        ("gl_account_id", "T-REF-15"),
        ("default_dimensions.department", "T-REF-15"),
        ("default_dimensions.region", "T-REF-15"),
    ]
    restricted = gl_account(
        app, world.maya, code="1200", name="Contract asset", entity_ids=[world.de]
    )
    elsewhere = post(
        app,
        rules_path,
        world.maya,
        {"account_role": "CONTRACT_ASSET", "gl_account_id": restricted, "entity_id": world.us},
    )
    assert fields(elsewhere) == [("gl_account_id", "T-REF-15")], elsewhere.text

    value = post(
        app, "/api/v1/dimensions/department/values", world.maya, {"code": "SALES", "name": "Sales"}
    )
    assert value.status_code == 201, value.text
    added = post(
        app,
        rules_path,
        world.maya,
        rule(
            world,
            "CONTRACT_LIABILITY",
            "2100",
            entity_id=world.us,
            book_code="ASC606",
            priority=3,
            default_dimensions={"department": "SALES"},
        ),
    )
    assert added.status_code == 201, added.text
    out = added.json()
    assert (out["specificity"], out["priority"], out["book_code"], out["default_dimensions"]) == (
        12,
        3,
        "ASC606",
        {"department": "SALES"},
    )
    unknown_rule = delete(app, path(body["id"], f"/rules/{probe}"), world.maya)
    assert unknown_rule.status_code == 404, unknown_rule.text
    only_liability = get(app, rules_path, world.maya, {"account_role": "CONTRACT_LIABILITY"})
    assert [item["id"] for item in only_liability.json()["items"]] == [out["id"]]
    assert get(app, rules_path, world.maya, {"account_role": "REVENUE"}).json()["items"] == []

    # Once submitted, the version and its rules are frozen (DB-04).
    assert post(app, path(body["id"], "/test"), world.maya, {}).status_code == 200
    submitted = post(app, path(body["id"], "/submit"), world.maya, {"comment": "Review"})
    assert submitted.status_code == 200, submitted.text
    frozen_rule = post(app, rules_path, world.maya, rule(world, "REVENUE", "4010"))
    assert (frozen_rule.status_code, slug(frozen_rule)) == (409, "configuration-frozen")
    assert fields(frozen_rule) == [("status", "DB-04")]
    etag = f'"r{submitted.json()["row_version"]}"'
    frozen_patch = patch(app, version_path, world.maya, {"name": "Renamed"}, if_match=etag)
    assert (frozen_patch.status_code, slug(frozen_patch)) == (409, "configuration-frozen")
    frozen_delete = delete(app, path(body["id"], f"/rules/{out['id']}"), world.maya)
    assert (frozen_delete.status_code, slug(frozen_delete)) == (409, "configuration-frozen")
    retest = post(app, path(body["id"], "/test"), world.maya, {})
    assert (retest.status_code, slug(retest)) == (409, "invalid-transition"), retest.text

    # The Viewer reads the versions and rules.
    [item] = get(app, ACCOUNT_MAPPINGS, omar).json()["items"]
    assert (item["status"], item["rule_count"], item["pending_approval_request_id"]) == (
        "SUBMITTED",
        1,
        submitted.json()["pending_approval_request_id"],
    )
    denied_rule = post(app, rules_path, omar, rule(world, "REVENUE", "4010"))
    assert denied_rule.status_code == 403, denied_rule.text

    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        actions = session.scalars(
            select(audit_event.c.action)
            .where(
                audit_event.c.object_type.in_(["account_mapping_version", "account_mapping_rule"])
            )
            .order_by(audit_event.c.chain_seq)
        ).all()
    assert [action for action in actions if not action.endswith("DENIED")] == [
        "account_mapping_version.create",
        "account_mapping_version.update",
        "account_mapping_rule.create",
        "account_mapping_version.tested",
        "account_mapping_version.submitted",
    ]


def test_same_instant_republication_supersedes(app: FastAPI, world: World) -> None:
    first = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[rule(world, "CONTRACT_LIABILITY", "2100")],
    )
    copied = post(
        app,
        ACCOUNT_MAPPINGS,
        world.maya,
        {"name": "AVM-MAP-2026-01 correction", "source_version_id": first["id"]},
    )
    assert copied.status_code == 201, copied.text
    correction = copied.json()
    assert (
        correction["version_no"],
        correction["rule_count"],
        correction["supersedes_version_id"],
    ) == (
        2,
        1,
        first["id"],
    )
    [kept] = get(app, path(correction["id"], "/rules"), world.maya).json()["items"]
    assert kept["gl_account"]["code"] == "2100"
    assert (
        delete(app, path(correction["id"], f"/rules/{kept['id']}"), world.maya).status_code == 204
    )
    replaced = post(
        app, path(correction["id"], "/rules"), world.maya, rule(world, "CONTRACT_LIABILITY", "2105")
    )
    assert replaced.status_code == 201, replaced.text
    tested = post(app, path(correction["id"], "/test"), world.maya, {})
    assert tested.status_code == 200, tested.text

    # The effective date is required before submission, and freezes afterwards.
    undated = post(app, path(correction["id"], "/submit"), world.maya, {})
    assert (undated.status_code, fields(undated)) == (422, [("effective_from", "T-REF-14")])
    etag = f'"r{tested.json()["row_version"]}"'
    dated = patch(
        app, path(correction["id"]), world.maya, {"effective_from": JANUARY}, if_match=etag
    )
    assert dated.status_code == 200, dated.text
    stale = post(app, path(correction["id"], "/submit"), world.maya, {})
    assert (stale.status_code, fields(stale)) == (409, [("status", "REQ-POL-003")]), stale.text
    assert post(app, path(correction["id"], "/test"), world.maya, {}).status_code == 200
    submitted = post(app, path(correction["id"], "/submit"), world.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["pending_approval_request_id"], world.carmen)
    assert approved.status_code == 200, approved.text

    replaced_first = get(app, path(first["id"]), world.maya).json()
    assert (replaced_first["status"], replaced_first["effective_to"]) == ("SUPERSEDED", None)
    shown = get(app, path(correction["id"]), world.maya).json()
    assert (shown["status"], shown["effective_to"]) == ("PUBLISHED", None)
    resolved = resolve(world, role="CONTRACT_LIABILITY")
    assert (resolved.gl_account_code, resolved.version_no) == ("2105", 2)


NOVEMBER = "2026-11-01T00:00:00Z"


def test_r64_superseding_mapping_is_bound_to_the_entities_of_the_version_it_ends(
    app: FastAPI, world: World, clock: FrozenClock
) -> None:
    """Supervisor ruling R-64 (2); 04 §16.10 rev 1.104 part 6 row ``ACCOUNT_MAPPING_VERSION``: a
    superseding version binds what it ends. Version 1 is in force with a rule for AVM-US and one
    for AVM-DE. Version 2 keeps the US rule and drops the German one; its own rules name AVM-US
    alone, but its approval ends version 1 — and with it the German entity's mapping — so the
    request names both entities. Ulla, a Controller for AVM-US, reads it and cannot decide it;
    before the ruling she approved it, and AVM-DE lost its account without anyone who approves
    for AVM-DE. Carmen, who approves for every entity, publishes it. Version 3 names no entity at
    all and ends version 2, which names AVM-US: it is that entity's change, not tenant
    configuration, and Ulla decides it."""
    us, de = world.us, world.de
    first = mapping_published(
        app,
        world.maya,
        world.carmen,
        name="AVM-MAP-2026-01",
        effective_from=JANUARY,
        rules=[
            rule(world, "REVENUE", "4000"),
            rule(world, "REVENUE", "4010", entity_id=us),
            rule(world, "REVENUE", "4020", entity_id=de),
        ],
    )
    ulla_member = colleague(world.tenant_id, "ulla")
    assign(ulla_member, "controller", entity_ids=[UUID(us)])
    ulla = enrolled(app, clock, ulla_member)

    second = mapping_submitted(
        app,
        world.maya,
        name="AVM-MAP-2026-10",
        effective_from=OCTOBER,
        rules=[rule(world, "REVENUE", "4000"), rule(world, "REVENUE", "4010", entity_id=us)],
    )
    request_id = second["pending_approval_request_id"]
    shown = get(app, f"{APPROVALS}/{request_id}", world.carmen).json()
    assert sorted(item["code"] for item in shown["entities"]) == ["AVM-DE", "AVM-US"]
    assert (shown["entity_count"], shown["all_entities"]) == (2, False)

    refused = approve(app, request_id, ulla)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == engine.EVERY_ENTITY_DETAIL
    assert get(app, path(second["id"]), world.maya).json()["status"] == "SUBMITTED"
    still = get(app, path(first["id"]), world.maya).json()
    assert (still["status"], still["effective_to"]) == ("PUBLISHED", None)
    assert resolve(world, role="REVENUE", entity_id=UUID(de)).gl_account_code == "4020"

    approved = approve(app, request_id, world.carmen)
    assert approved.status_code == 200, approved.text
    assert get(app, path(second["id"]), world.maya).json()["status"] == "PUBLISHED"
    ended = get(app, path(first["id"]), world.maya).json()
    assert instant(ended["effective_to"]) == instant(OCTOBER)

    # A version without an entity of its own that ends one with AVM-US: bound to AVM-US.
    third = mapping_submitted(
        app,
        world.maya,
        name="AVM-MAP-2026-11",
        effective_from=NOVEMBER,
        rules=[rule(world, "REVENUE", "4000")],
    )
    general = get(app, f"{APPROVALS}/{third['pending_approval_request_id']}", world.carmen).json()
    assert [item["code"] for item in general["entities"]] == ["AVM-US"]
    assert (general["entity"]["code"], general["entity_count"]) == ("AVM-US", 1)
    decided = approve(app, third["pending_approval_request_id"], ulla)
    assert decided.status_code == 200, decided.text
    assert get(app, path(third["id"]), world.maya).json()["status"] == "PUBLISHED"
