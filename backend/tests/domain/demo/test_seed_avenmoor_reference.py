"""RFD-16 Avenmoor reference-data demo seed (docs/02-PRD.md §2.1 WLD-R-01 to WLD-R-04, §2.2, §2.5 to
§2.7; BUILD_SPEC RFD-16, XR-09, BS3-D-09).

The test database is shared by the session, and the persona users are global identities, so the
module seeds WLD-T-01 through ``seed_demo`` under stand-in tenant codes, with the PRD §2.3 cast at
module-unique ``demo.erev`` addresses. The tests read what the persona commands wrote.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    app_user,
    approval_decision,
    approval_request,
    book,
    customer,
    entity_book,
    fiscal_calendar,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    legal_entity,
    notification,
    period,
    period_state,
    pob_template,
    pob_template_version,
    product,
    registry_version,
    related_party_group,
    rule,
    rule_set,
    rule_set_version,
    rule_test_case,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
    tenant,
    tenant_currency,
    tenant_membership,
)
from erev_api.domain.demo import SeedRefused, builders, personas, seed, tenants
from erev_api.domain.demo.personas import Persona
from erev_api.domain.reference import fx, mapping
from erev_api.enums import AccountRole, ApprovalSubjectType, BookCode, ClearingPurpose
from erev_api.files.store import LocalFileStore
from erev_api.registry.resolve import resolve
from sqlalchemy import Table, and_, func, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import tenant_factory

# Seeding Avenmoor twice through the persona commands takes well over ten seconds (DG-TST-08).
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-rfd-16"
AVENMOOR = tenants.CATALOGUE[1]  # WLD-T-01
ENTITY_CODES = ("AVM-DE", "AVM-JP", "AVM-UK", "AVM-US")
FIRST_OPEN = date(2026, 1, 1)
LAST_OPEN = date(2026, 9, 1)
FIRST_FUTURE = date(2026, 10, 1)
LAST_FUTURE = date(2027, 12, 1)
# PRD §2.7 customers: code → (source system, external id, related-party group).
CUSTOMERS: Mapping[str, tuple[str | None, str | None, str | None]] = {
    "WLD-C-01": ("SALESFORCE", "001DEMO0001", None),
    "WLD-C-02": ("SALESFORCE", "001DEMO0002", None),
    "WLD-C-03": ("API", "CB-2026", None),
    "WLD-C-04": ("SALESFORCE", "001DEMO0104", None),
    "WLD-C-05": ("NETSUITE", "C-DE-3001", "HOLLENBRAND"),
    "WLD-C-06": ("NETSUITE", "C-DE-3002", None),
    "WLD-C-07": ("NETSUITE", "C-DE-3003", None),
    "WLD-C-08": ("SALESFORCE", "001DEMO0005", None),
    "WLD-C-09": ("SALESFORCE", "001DEMO0006", None),
    "WLD-C-10": ("NETSUITE", "C-JP-0001", None),
    "WLD-C-11": ("NETSUITE", "C-DE-3004", "HOLLENBRAND"),
    "WLD-C-12": ("SALESFORCE", "001DEMO0417", None),
    "WLD-C-13": ("MANUAL_UI", None, None),
}
PRODUCTS = frozenset(
    {
        "AVM-PLAT-ENT",
        "AVM-SEAT-MO",
        "AVM-PLAT-100",
        "AVM-IMPL-STD",
        "AVM-IMPL-PLUS",
        "AVM-API-CALL",
        "AVM-ENG-BUILD",
        "AVM-KIT",
        "AVM-PART",
        "AVM-GW",
        "AVM-FLEET",
        "AVM-SUP-12",
        "AVM-EXP-CREDIT",
        "AVM-PLAT-UK",
        "AVM-IMPL-UK",
        "AVM-LIB-LIC",
        "AVM-ROYALTY",
    }
)
TEMPLATES = frozenset(
    {
        "TPL-SUB-DAILY",
        "TPL-SVC-PCT",
        "TPL-SVC-HOURS",
        "TPL-USAGE",
        "TPL-ENG-C2C",
        "TPL-PROD-PIT",
        "TPL-PROD-UNITS",
        "TPL-OPTION",
        "TPL-LIC-FUNC",
    }
)
_S = ApprovalSubjectType
# PRD §2.5 routing table rows: (subjects, threshold condition field or None, steps).
ROUTING_ROWS: tuple[tuple[frozenset[str], str | None, int], ...] = (
    (frozenset({_S.CONTRACT_ACTIVATION}), None, 1),
    (frozenset({_S.CONTRACT_ACTIVATION}), "amount.functional", 2),
    (frozenset({_S.MODIFICATION}), None, 1),
    (frozenset({_S.MODIFICATION}), "amount.functional", 2),
    (frozenset({_S.ESTIMATE_VERSION}), None, 1),
    (frozenset({_S.ESTIMATE_VERSION}), "amount.functional", 2),
    (frozenset({_S.MANUAL_EVENT}), None, 1),
    (frozenset({_S.JUDGEMENT_RECORD}), None, 1),
    (frozenset({_S.COMBINATION_GROUP}), None, 1),
    (frozenset({_S.SSP_OVERRIDE}), None, 1),
    (frozenset({_S.MANUAL_ADJUSTMENT}), None, 1),
    (frozenset({_S.MANUAL_ADJUSTMENT}), "amount.functional", 2),
    (frozenset({_S.IMPORT_COMMIT}), None, 1),
    (frozenset({_S.SSP_BOOK_VERSION}), None, 1),
    (frozenset({_S.SSP_BOOK_VERSION}), "flags", 2),
    (
        frozenset(
            {
                _S.REGISTRY_VERSION,
                _S.RULE_SET_VERSION,
                _S.POB_TEMPLATE_VERSION,
                _S.ACCOUNT_MAPPING_VERSION,
                _S.FX_RATE_SET_VERSION,
                _S.PRINCIPAL_AGENT_CHANGE,
                _S.MAPPING_PROFILE_VERSION,
            }
        ),
        None,
        1,
    ),
    (frozenset({_S.POLICY_OVERRIDE}), None, 1),
    (frozenset({_S.ATTRIBUTE_CHANGE}), None, 1),
    (frozenset({_S.AI_PROPOSAL_ACCEPTANCE}), None, 1),
    (frozenset({_S.EXCEPTION_WAIVER}), None, 1),
    (frozenset({_S.JOURNAL_RUN}), None, 1),
    (frozenset({_S.PERIOD_LOCK}), None, 1),
    (frozenset({_S.PERIOD_REOPEN}), None, 1),
    (frozenset({_S.MIGRATION_PROMOTION}), None, 1),
    (frozenset({_S.CONTRACT_VOID}), None, 1),
    (frozenset({_S.CONTRACT_VOID}), "flags", 2),
    (frozenset({_S.ROLE_ASSIGNMENT, _S.ROLE_CHANGE, _S.SOD_EXCEPTION}), None, 1),
    (frozenset({_S.SUPPORT_GRANT}), None, 1),
    # PRD §2.5 rev 1.71 (lane SECFIX-IMP part B; supervisor rulings R-49 (a) and R-86).
    (frozenset({_S.EVIDENCE_SHRED}), None, 1),
)
CONFIG_VERSION_TABLES: tuple[Table, ...] = (
    account_mapping_version,
    pob_template_version,
    ssp_book_version,
    fx_rate_set_version,
    rule_set_version,
    registry_version,
)
# The reference rows of the canonical hash (WLD-R-01).
REFERENCE_TABLES: tuple[Table, ...] = (
    fiscal_calendar,
    period,
    legal_entity,
    book,
    entity_book,
    period_state,
    tenant_currency,
    fx_rate_set,
    fx_rate_set_version,
    fx_rate,
    gl_account,
    account_mapping_version,
    account_mapping_rule,
    related_party_group,
    customer,
    product,
    pob_template,
    pob_template_version,
    rule_test_case,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
    rule_set,
    rule_set_version,
    rule,
    registry_version,
)


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    code: str
    cast: tuple[Persona, ...]
    user_ids: Mapping[str, UUID]  # persona key → app_user id
    clock: FrozenClock


def _read(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_read(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _cast(suffix: str) -> tuple[Persona, ...]:
    """The PRD §2.3 personas at addresses of this module only (WLD-R-04 domain kept)."""
    return tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )


def _build(keyring: KeyRing, root: Path, cast: tuple[Persona, ...], env: tuple[str, str]) -> World:
    """Seed a stand-in WLD-T-01 under a fresh code through ``seed_demo`` with the frozen clock."""
    code = f"avm-{secrets.token_hex(4)}"
    clock = frozen_clock()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=code)))
        # The RFD-16 builders only: the CTR-20 contract builders take minutes and have their own
        # module (test_seed_avenmoor_contracts.py).
        patch.setattr(
            builders, "BUILDERS", {AVENMOOR.wld_id: builders.BUILDERS[AVENMOOR.wld_id][:3]}
        )
        result = seed.seed_demo(
            [code],
            clock,
            keyring=keyring,
            files=LocalFileStore(root / "files"),
            secrets=seed.DemoSecrets(password=env[0], totp_secret=env[1]),
            credentials_path=root / "run" / seed.CREDENTIALS_FILE,
            request_id=REQUEST_ID,
            personas=cast,
        )
    assert result.outcomes == ((code, "seeded"),)
    with platform_session("tenant_directory", actor_user_id=None, request_id=REQUEST_ID) as db:
        found_id = db.execute(select(tenant.c.id).where(tenant.c.code == code)).scalar_one()
    tenant_id = UUID(str(found_id))
    emails = {persona.email: persona.key for persona in cast}
    with identity_session(request_id=REQUEST_ID) as db:
        found = db.execute(
            select(app_user.c.email, app_user.c.id).where(app_user.c.email.in_(sorted(emails)))
        ).all()
    user_ids = {emails[str(email)]: UUID(str(user_id)) for email, user_id in found}
    return World(tenant_id=tenant_id, code=code, cast=cast, user_ids=user_ids, clock=clock)


@pytest.fixture(scope="module")
def demo_env() -> tuple[str, str]:
    return (f"Seed-{secrets.token_urlsafe(12)}", pyotp.random_base32())


@pytest.fixture(scope="module")
def cast() -> tuple[Persona, ...]:
    return _cast(secrets.token_hex(3))


@pytest.fixture(scope="module")
def world(
    test_database: TestDatabase,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    cast: tuple[Persona, ...],
    tmp_path_factory: pytest.TempPathFactory,
) -> World:
    return _build(keyring, tmp_path_factory.mktemp("rfd-16-a"), cast, demo_env)


def test_entities_calendars_and_periods(world: World) -> None:
    entities = _rows(
        world.tenant_id,
        select(
            legal_entity.c.id,
            legal_entity.c.code,
            legal_entity.c.functional_currency,
            legal_entity.c.time_zone,
            legal_entity.c.parent_entity_id,
            fiscal_calendar.c.fiscal_year_start_month,
        ).select_from(
            legal_entity.join(
                fiscal_calendar,
                and_(
                    fiscal_calendar.c.tenant_id == legal_entity.c.tenant_id,
                    fiscal_calendar.c.id == legal_entity.c.calendar_id,
                ),
            )
        ),
    )
    by_code = {row["code"]: row for row in entities}
    assert {
        code: (row["functional_currency"], row["time_zone"], row["fiscal_year_start_month"])
        for code, row in by_code.items()
    } == {
        "AVM-US": ("USD", "America/New_York", 1),
        "AVM-UK": ("GBP", "Europe/London", 1),
        "AVM-DE": ("EUR", "Europe/Berlin", 1),
        "AVM-JP": ("JPY", "Asia/Tokyo", 4),
    }
    us_id = by_code["AVM-US"]["id"]
    assert {code: row["parent_entity_id"] for code, row in by_code.items()} == {
        "AVM-US": None,
        "AVM-UK": us_id,
        "AVM-DE": us_id,
        "AVM-JP": us_id,
    }
    kept = _rows(
        world.tenant_id,
        select(legal_entity.c.code, entity_book.c.book_code)
        .select_from(
            entity_book.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == entity_book.c.tenant_id,
                    legal_entity.c.id == entity_book.c.entity_id,
                ),
            )
        )
        .where(entity_book.c.is_enabled.is_(True)),
    )
    books: dict[str, set[str]] = {}
    for row in kept:
        books.setdefault(row["code"], set()).add(str(row["book_code"]))
    assert books == {
        "AVM-US": {"ASC606", "IFRS15"},  # D-87 L6-5-Q-24
        "AVM-UK": {"ASC606", "IFRS15"},
        "AVM-DE": {"ASC606"},
        "AVM-JP": {"ASC606"},
    }

    states = _rows(
        world.tenant_id,
        select(
            legal_entity.c.code,
            period_state.c.book_code,
            period.c.start_date,
            period.c.period_key,
            period_state.c.state,
        ).select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            ).join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
        ),
    )
    japan_september = [
        row["period_key"]
        for row in states
        if row["code"] == "AVM-JP" and row["start_date"] == LAST_OPEN
    ]
    assert japan_september == ["FY2027-P06"]
    for code, kept_books in books.items():
        for book_code in kept_books:
            mine = {
                row["start_date"]: str(row["state"])
                for row in states
                if row["code"] == code and str(row["book_code"]) == book_code
            }
            opened = {day for day, state in mine.items() if FIRST_OPEN <= day <= LAST_OPEN}
            future = {day for day, state in mine.items() if FIRST_FUTURE <= day <= LAST_FUTURE}
            assert len(opened) == 9, (code, book_code)
            assert len(future) == 15, (code, book_code)
            assert {mine[day] for day in opened} == {"open"}, (code, book_code)
            assert {mine[day] for day in future} == {"future"}, (code, book_code)


def test_fx_rates(world: World) -> None:
    with tenant_session(_read(world.tenant_id), read_only=True) as session:
        found = (
            fx.rate(session, rate_type="closing", base="EUR", quote="USD", on=date(2026, 9, 30)),
            fx.rate(session, rate_type="average", base="GBP", quote="USD", on=date(2026, 9, 30)),
            fx.rate(session, rate_type="average", base="JPY", quote="USD", on=date(2026, 8, 31)),
            fx.rate(session, rate_type="average", base="EUR", quote="USD", on=date(2026, 1, 31)),
        )
    assert found == (
        Decimal("1.120000"),
        Decimal("1.280000"),
        Decimal("0.006800"),
        Decimal("1.100000"),
    )


def _decisions(tenant_id: UUID, request_id: Any) -> list[tuple[str, UUID | None]]:
    return [
        (str(row["decision"]), row["approver_id"])
        for row in _rows(
            tenant_id,
            select(approval_decision.c.decision, approval_decision.c.approver_id).where(
                approval_decision.c.approval_request_id == request_id
            ),
        )
    ]


def test_chart_of_accounts_and_mapping(world: World) -> None:
    codes = [
        row["code"]
        for row in _rows(world.tenant_id, select(gl_account.c.code).order_by(gl_account.c.code))
    ]
    assert (len(codes), codes[0], codes[-1]) == (32, "1100", "7900")
    [version] = _rows(
        world.tenant_id,
        select(account_mapping_version).where(account_mapping_version.c.created_by.is_not(None)),
    )
    assert (version["name"], str(version["status"])) == ("AVM-MAP-2026-01", "PUBLISHED")
    assert version["effective_from"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert _decisions(world.tenant_id, version["approval_request_id"]) == [
        ("APPROVE", world.user_ids["marcus"])
    ]
    at = datetime(2026, 9, 1, tzinfo=UTC)
    with tenant_session(_read(world.tenant_id), read_only=True) as session:
        clearing = {
            purpose: mapping.resolve_account(
                session, role=AccountRole.BILLING_CLEARING, clearing_purpose=purpose, known_at=at
            ).gl_account_code
            for purpose in ClearingPurpose
        }
    assert clearing == dict.fromkeys(ClearingPurpose, "2090")
    roles = {
        str(row["account_role"])
        for row in _rows(
            world.tenant_id,
            select(account_mapping_rule.c.account_role).where(
                account_mapping_rule.c.account_mapping_version_id == version["id"]
            ),
        )
    }
    assert AccountRole.PRE_STANDARD_REVENUE.value not in roles
    assert AccountRole.RECEIVABLE_CONTRA.value not in roles


def test_customers_products_templates(world: World) -> None:
    rows = _rows(
        world.tenant_id,
        select(
            customer.c.code,
            customer.c.source_system,
            customer.c.external_id,
            related_party_group.c.code.label("group_code"),
        ).select_from(
            customer.outerjoin(
                related_party_group,
                and_(
                    related_party_group.c.tenant_id == customer.c.tenant_id,
                    related_party_group.c.id == customer.c.related_party_group_id,
                ),
            )
        ),
    )
    assert {
        row["code"]: (
            None if row["source_system"] is None else str(row["source_system"]),
            row["external_id"],
            row["group_code"],
        )
        for row in rows
    } == CUSTOMERS
    [group] = _rows(world.tenant_id, select(related_party_group.c.code))
    assert group["code"] == "HOLLENBRAND"
    products = {row["code"] for row in _rows(world.tenant_id, select(product.c.code))}
    assert products == PRODUCTS
    published = _rows(
        world.tenant_id,
        select(pob_template.c.code, pob_template_version.c.status).select_from(
            pob_template.join(
                pob_template_version,
                and_(
                    pob_template_version.c.tenant_id == pob_template.c.tenant_id,
                    pob_template_version.c.pob_template_id == pob_template.c.id,
                ),
            )
        ),
    )
    assert {row["code"]: str(row["status"]) for row in published} == dict.fromkeys(
        TEMPLATES, "PUBLISHED"
    )


def test_ssp_books(world: World) -> None:
    versions = _rows(
        world.tenant_id,
        select(
            ssp_book.c.code,
            ssp_book_version.c.legacy_version_label,
            ssp_book_version.c.effective_from_date,
            ssp_book_version.c.status,
            ssp_book_version.c.created_by,
            ssp_book_version.c.approval_request_id,
        ).select_from(
            ssp_book.join(
                ssp_book_version,
                and_(
                    ssp_book_version.c.tenant_id == ssp_book.c.tenant_id,
                    ssp_book_version.c.ssp_book_id == ssp_book.c.id,
                ),
            )
        ),
    )
    shown = {
        f"{row['code']} {row['legacy_version_label']}": (
            row["effective_from_date"],
            str(row["status"]),
        )
        for row in versions
    }
    assert shown == {
        "US-LIST 2026-H1": (date(2026, 1, 1), "APPROVED"),
        "UK-LIST 2026": (date(2026, 1, 1), "APPROVED"),
        "DE-LIST 2026": (date(2026, 1, 1), "APPROVED"),
        "JP-LIST FY2027": (date(2026, 4, 1), "APPROVED"),
    }
    [us] = [row for row in versions if row["code"] == "US-LIST"]
    assert us["created_by"] == world.user_ids["maya"]
    assert _decisions(world.tenant_id, us["approval_request_id"]) == [
        ("APPROVE", world.user_ids["priya"])
    ]
    joined = (
        ssp_entry.join(
            ssp_range,
            and_(
                ssp_range.c.tenant_id == ssp_entry.c.tenant_id,
                ssp_range.c.ssp_entry_id == ssp_entry.c.id,
            ),
        )
        .join(
            ssp_book_version,
            and_(
                ssp_book_version.c.tenant_id == ssp_entry.c.tenant_id,
                ssp_book_version.c.id == ssp_entry.c.ssp_book_version_id,
            ),
        )
        .join(
            ssp_book,
            and_(
                ssp_book.c.tenant_id == ssp_entry.c.tenant_id,
                ssp_book.c.id == ssp_book_version.c.ssp_book_id,
            ),
        )
        .join(
            product,
            and_(
                product.c.tenant_id == ssp_entry.c.tenant_id, product.c.id == ssp_entry.c.product_id
            ),
        )
    )
    gateway = _rows(
        world.tenant_id,
        select(
            ssp_entry.c.currency,
            ssp_range.c.low_value,
            ssp_range.c.mid_value,
            ssp_range.c.high_value,
        )
        .select_from(joined)
        .where(ssp_book.c.code == "DE-LIST", product.c.code == "AVM-GW"),
    )
    assert [
        (
            row["currency"],
            Fraction(row["low_value"]),
            Fraction(row["mid_value"]),
            Fraction(row["high_value"]),
        )
        for row in gateway
    ] == [("EUR", Fraction(405), Fraction(450), Fraction(495))]


def _rule_set(world: World, code: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    [version] = _rows(
        world.tenant_id,
        select(
            rule_set.c.kind,
            rule_set_version.c.id,
            rule_set_version.c.version_no,
            rule_set_version.c.status,
        )
        .select_from(
            rule_set.join(
                rule_set_version,
                and_(
                    rule_set_version.c.tenant_id == rule_set.c.tenant_id,
                    rule_set_version.c.rule_set_id == rule_set.c.id,
                ),
            )
        )
        .where(rule_set.c.code == code),
    )
    rules = _rows(
        world.tenant_id,
        select(rule.c.rule_key, rule.c.conditions, rule.c.outputs).where(
            rule.c.rule_set_version_id == version["id"]
        ),
    )
    return version, rules


def _subjects(conditions: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    [subject] = [condition for condition in conditions if condition["field"] == "subject.type"]
    value = subject["value"]
    return frozenset(value if isinstance(value, list) else [value])


def test_routing_and_auto_approval_rule_sets(world: World) -> None:
    routing, routing_rules = _rule_set(world, "APPROVAL_ROUTING")
    assert (str(routing["kind"]), routing["version_no"], str(routing["status"])) == (
        "APPROVAL_ROUTING",
        1,
        "PUBLISHED",
    )
    shapes = [
        (
            _subjects(item["conditions"]),
            next((c["field"] for c in item["conditions"] if c["field"] != "subject.type"), None),
            len(item["outputs"]["steps"]),
        )
        for item in routing_rules
    ]
    for row in ROUTING_ROWS:
        assert row in shapes, row
    covered = {subject for shape in shapes for subject in shape[0]}
    # PRD §2.5 rev 1.15 (D-98 133 AMENDMENT 4; 04 rev 1.72): the one routing row of
    # ``MIGRATION_SSP_REPLAY`` is an auto-approval — "Auto-approve under rule `AUTO-MIG-01`; the
    # human control point stays `MIGRATION_PROMOTION`" — so its rule is an auto-approval rule
    # (the provisioned set's, asserted below), never a routing step; every other E-08 subject has
    # a routing rule.
    every_subject = {member.value for member in ApprovalSubjectType}
    auto_only = {ApprovalSubjectType.MIGRATION_SSP_REPLAY.value}
    assert covered == every_subject - auto_only

    auto, auto_rules = _rule_set(world, "AUTO_APPROVAL")
    assert (str(auto["kind"]), auto["version_no"], str(auto["status"])) == (
        "AUTO_APPROVAL",
        1,
        "PUBLISHED",
    )
    by_key = {item["rule_key"]: item for item in auto_rules}
    # 04 §16.10 rev 1.104 (supervisor ruling R-41 (7)): a tenant's own auto-approval rules name
    # the two tenant-approvable subject types only, and the legacy SSP replay is approved by the
    # rule set provisioning seeds — 04 rev 1.72 `AUTO-MIG-01` "for every tenant (the demo seed
    # too)", §14.3 item 2 — which this workspace has like any other (asserted below).
    assert set(by_key) == {"AUTO-CON-01", "AUTO-IMP-01"}
    assert _subjects(by_key["AUTO-CON-01"]["conditions"]) == {"CONTRACT_ACTIVATION"}
    assert _subjects(by_key["AUTO-IMP-01"]["conditions"]) == {"IMPORT_COMMIT"}
    seeded, [seeded_rule] = _rule_set(world, "AUTO-MIG-01")
    assert (str(seeded["kind"]), seeded["version_no"], str(seeded["status"])) == (
        "AUTO_APPROVAL",
        1,
        "PUBLISHED",
    )
    assert seeded_rule["rule_key"] == "AUTO-MIG-01"
    assert seeded_rule["conditions"] == [
        {"field": "subject.type", "op": "eq", "value": "MIGRATION_SSP_REPLAY"},
        {"field": "source.channel", "op": "eq", "value": "USER"},
    ]
    assert {key: item["outputs"] for key, item in by_key.items()} == dict.fromkeys(
        by_key, {"auto_approve": True}
    )
    assert seeded_rule["outputs"] == {"auto_approve": True}
    # A rule for every subject row of the PRD §2.5 table, in one set or another.
    automatic = {s for item in (*auto_rules, seeded_rule) for s in _subjects(item["conditions"])}
    assert covered | automatic == every_subject and auto_only <= automatic


def test_tenant_policy_version(world: World) -> None:
    versions = _rows(
        world.tenant_id,
        select(registry_version).where(
            registry_version.c.created_by == world.user_ids["maya"],
            registry_version.c.status == "PUBLISHED",
        ),
    )
    tenant_versions = {
        str(row["category"]): row for row in versions if str(row["scope"]) == "TENANT"
    }
    assert set(tenant_versions) == {"ACCOUNTING_POLICY", "PLATFORM", "INTEGRATION"}
    # A version of a settings category names no date and takes effect when it is approved (04
    # §16.5 "Order of effective instants"; the supervisor's ruling of 2026-10-01 on item
    # CFG-PLATFORM-PIN-1): dated at the next period start, the seeded versions kept every later
    # change of a workspace setting waiting for that day (PRD ERR-81). The accounting policy set
    # is period-scoped and keeps its date.
    assert {
        category: row["effective_from"] is None for category, row in tenant_versions.items()
    } == {"ACCOUNTING_POLICY": False, "PLATFORM": True, "INTEGRATION": True}
    with tenant_session(_read(world.tenant_id), read_only=True) as session:
        in_force_now = {
            code: resolve(
                session, code, book_code=BookCode.ASC606, known_at=world.clock.now()
            ).source_id
            for code in ("ui.negative_number_style", "data.quarantine_failed_rows")
        }
    assert in_force_now == {
        "ui.negative_number_style": tenant_versions["PLATFORM"]["id"],
        "data.quarantine_failed_rows": tenant_versions["INTEGRATION"]["id"],
    }
    entities = {
        row["code"]: row["id"]
        for row in _rows(world.tenant_id, select(legal_entity.c.code, legal_entity.c.id))
    }
    at = tenant_versions["ACCOUNTING_POLICY"]["effective_from"]
    expected = {
        "billing.posting": "ERP",
        "je.posting_mode": "GROSS",
        "je.summarization": "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
        "ui.negative_number_style": "PARENTHESES",
        "data.quarantine_failed_rows": False,
    }
    with tenant_session(_read(world.tenant_id), read_only=True) as session:
        resolved = {
            code: resolve(session, code, book_code=BookCode.ASC606, known_at=at)
            for code in expected
        }
        reporting = {
            code: resolve(
                session,
                "entity.reporting_type",
                book_code=BookCode.ASC606,
                entity_id=entity_id,
                known_at=at,
            )
            for code, entity_id in entities.items()
        }
    assert {code: found.value for code, found in resolved.items()} == expected
    version_ids = {row["id"] for row in tenant_versions.values()}
    assert {found.source_id for found in resolved.values()} <= version_ids
    assert {code: found.value for code, found in reporting.items()} == dict.fromkeys(
        ENTITY_CODES, "PBE"
    )
    # Resolved from the ENTITY versions the seed published, not the framework default.
    assert {found.level for found in reporting.values()} == {"E"}
    entity_versions = {row["id"] for row in versions if str(row["scope"]) == "ENTITY"}
    assert len(entity_versions) == len(ENTITY_CODES)
    assert {found.source_id for found in reporting.values()} == entity_versions


def test_web_17_setup_completed_and_no_unread_notification(world: World) -> None:
    """D-84 (WEB-17 ``sf-15``, ``sf-21``): the seeded workspace completed setup (BR-PLT-02, once
    ``marcus`` opened the first period), and ``grace`` opened her APPROVAL_ASSIGNED notification of
    the deal desk analyst role change before approving it, so she holds no unread notification."""
    [row] = _rows(
        world.tenant_id,
        select(tenant.c.setup_completed_at).where(tenant.c.id == world.tenant_id),
    )
    assert row["setup_completed_at"] is not None
    received = _rows(
        world.tenant_id,
        select(notification.c.kind, notification.c.title, notification.c.read_at)
        .select_from(
            notification.join(
                tenant_membership,
                and_(
                    tenant_membership.c.tenant_id == notification.c.tenant_id,
                    tenant_membership.c.id == notification.c.recipient_membership_id,
                ),
            )
        )
        .where(tenant_membership.c.user_id == world.user_ids["grace"]),
    )
    assert ("APPROVAL_ASSIGNED", "Approval needed: Add the custom role Deal desk analyst") in {
        (str(item["kind"]), item["title"]) for item in received
    }
    assert [item["title"] for item in received if item["read_at"] is None] == []


def _canonical(value: Any) -> Any:
    """``value`` without generated ids, timestamps or content digests (which embed ids)."""
    if isinstance(value, UUID | datetime):
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not str(key).endswith("sha256") and key != "tenant_id"
        }
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, str):
        try:
            UUID(value)
        except ValueError:
            pass
        else:
            return None
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return value
        return None if "T" in value else value
    if isinstance(value, Decimal | date):
        return str(value)
    return value


def _reference_hash(tenant_id: UUID) -> str:
    content: dict[str, list[str]] = {}
    with tenant_session(_read(tenant_id), read_only=True) as session:
        for table in REFERENCE_TABLES:
            rows = [
                json.dumps(_canonical(dict(row)), sort_keys=True)
                for row in session.execute(select(table)).mappings()
            ]
            content[table.name] = sorted(rows)
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def test_seed_deterministic_and_built_by_commands(
    world: World,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    cast: tuple[Persona, ...],
    tmp_path: Path,
) -> None:
    again = _build(keyring, tmp_path, cast, demo_env)
    assert again.tenant_id != world.tenant_id
    assert _reference_hash(again.tenant_id) == _reference_hash(world.tenant_id)

    personas_by_id = {user_id: key for key, user_id in world.user_ids.items()}
    prepared = 0
    for table in CONFIG_VERSION_TABLES:
        rows = _rows(
            world.tenant_id,
            select(
                table.c.id, table.c.created_by, table.c.created_by_kind, table.c.approval_request_id
            ),
        )
        for row in rows:
            if str(row["created_by_kind"]) != "USER":
                continue  # provisioning rows of the SYSTEM principal (04 §14.3)
            prepared += 1
            assert row["created_by"] in personas_by_id, (table.name, row)
            assert row["approval_request_id"] is not None, (table.name, row)
            [request] = _rows(
                world.tenant_id,
                select(approval_request.c.preparer_id, approval_request.c.status).where(
                    approval_request.c.id == row["approval_request_id"]
                ),
            )
            assert (request["preparer_id"], str(request["status"])) == (
                row["created_by"],
                "APPROVED",
            )
            decisions = _decisions(world.tenant_id, row["approval_request_id"])
            assert decisions, (table.name, row)
            for decision, approver in decisions:
                assert decision == "APPROVE"
                assert approver in personas_by_id and approver != row["created_by"]
    # 1 mapping, 9 templates, 4 SSP versions, 3 rate sets, 2 rule sets, 3 tenant and 4 entity
    # policy versions.
    assert prepared == 26


def test_seed_refuses_non_demo_tenant(keyring: KeyRing, clock: FrozenClock, tmp_path: Path) -> None:
    plain = tenant_factory(keyring=keyring, clock=clock)  # is_demo false
    tenant_id = UUID(str(plain.tenant["id"]))
    code = str(plain.tenant["code"])

    def no_persona(_persona: Persona, _tenant_id: UUID) -> Any:
        raise AssertionError("the builder ran a command before the WLD-R-04 check")

    def no_guard(_ctx: Any, _permission: str) -> None:
        raise AssertionError("the builder guarded a command before the WLD-R-04 check")

    ctx = builders.BuildContext(
        tenant_id=tenant_id,
        tenant_code=code,
        wld_id=AVENMOOR.wld_id,
        cast={persona.key: persona for persona in personas.PERSONAS},
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(tmp_path / "files"),
        request_id=REQUEST_ID,
        principal_context=no_persona,
        guard=no_guard,
    )
    with pytest.raises(SeedRefused, match=rf"^Refusing to seed {code}: is_demo is false$"):
        builders.run(ctx)
    [count] = _rows(tenant_id, select(func.count().label("entities")).select_from(legal_entity))
    assert count == {"entities": 0}
