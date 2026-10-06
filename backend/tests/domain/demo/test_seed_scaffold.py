"""WEB-10 demo seed scaffold (docs/02-PRD.md §2.1 WLD-R-02, WLD-R-04; §2.3 WLD-U-01 to WLD-U-11,
WLD-U-R2; §2.4 WLD-T-00 to WLD-T-07; dev-guide DG-MK-seed, DG-RUN-32; BUILD_SPEC BS1-D-20).

The module seeds every demo tenant once with ``erev seed demo --tenants all`` under
``EREV_ENV=test``, with a generated ``EREV_DEMO_PASSWORD`` and TOTP seed in the environment, and the
tests read what the persona commands wrote.
"""

from __future__ import annotations

import io
import json
import os
import re
import secrets
import stat
import subprocess
import traceback
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

import pyotp
import pytest
from click.testing import Result
from erev_api import cli
from erev_api.auth import mfa, sessions, totp
from erev_api.auth.keyring import KeyRing
from erev_api.auth.sessions import RequestFacts
from erev_api.clock import FrozenClock
from erev_api.config import Environment, get_settings
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    audit_event,
    outbox_message,
    role,
    role_assignment,
    role_permission,
    rule,
    security_event,
    tenant,
    tenant_membership,
    user_mfa_factor,
    user_recovery_code,
    user_session,
)
from erev_api.domain.demo import SeedRefused, personas, seed, tenants
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import GlAdapter
from erev_api.files.store import LocalFileStore
from sqlalchemy import Table, and_, func, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import tenant_factory
from support.operators import invoke

# Seeding the eight tenants through the persona commands takes about 15 seconds (DG-TST: slow).
pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[4]
# The replaced ``cli_services`` configures no logging, so console log lines share stdout here.
COMMAND_LINE = re.compile(r"^(seeded|skipped) \S+$|^recovery codes written to ")
REQUEST_ID = "tests-web-10"
CATALOGUE = {
    "legacy-parity": "Legacy parity pack (Demo)",
    "avenmoor": "Avenmoor Holdings (Demo)",
    "fernhill": "Fernhill Software, Inc. (Demo)",
    "bracken": "Bracken Robotics Corp. (Demo)",
    "granitefield": "Granitefield Engineering Group (Demo)",
    "juniper-street": "Juniper Street Coffee Co. (Demo)",
    "riverbend": "Riverbend Health System (Demo)",
    "wayfarer": "Wayfarer Marketplace (Demo)",
}
INDUSTRY = ("fernhill", "bracken", "granitefield", "juniper-street", "riverbend", "wayfarer")
# PRD §2.3, column WLD-T-01 Avenmoor.
AVENMOOR_ROLES: Mapping[str, frozenset[str]] = {
    "maya": frozenset({"revenue_accountant", "ssp_analyst"}),
    "priya": frozenset({"revenue_reviewer", "ssp_approver"}),
    "marcus": frozenset({"controller", "ssp_approver"}),
    "elena": frozenset({"controller"}),
    "robert": frozenset({"viewer"}),
    "hannah": frozenset({"auditor"}),
    "samuel": frozenset({"auditor"}),
    "tomas": frozenset({"tenant_admin"}),
    "grace": frozenset({"tenant_admin"}),
    "nikhil": frozenset({"integration_admin"}),
    "jordan": frozenset({"viewer", "deal_desk_analyst"}),
}
# PRD WLD-U-R2 (rev 1.153): the holders of a ``requires_mfa`` permission, and ``maya``, whose
# journey signs off (a sign-off needs an MFA-verified session; supervisor ruling R-83 (f)).
MFA_PERSONAS = frozenset({"maya", "priya", "marcus", "elena", "tomas", "grace", "nikhil"})
MISSING_PASSWORD = "EREV_DEMO_PASSWORD is not set. Copy it from .env.example."
RECOVERY_CODE = re.compile(r"^[2-9a-hjkmnp-z]{4}-[2-9a-hjkmnp-z]{4}$")
IDENTITY_TABLES: tuple[Table, ...] = (app_user, user_mfa_factor, user_recovery_code, user_session)
TENANT_TABLES: tuple[Table, ...] = (
    tenant_membership,
    role,
    role_assignment,
    role_permission,
    approval_request,
    approval_decision,
    audit_event,
    outbox_message,
)


@dataclass(frozen=True, slots=True)
class DemoRun:
    services: cli.CliServices
    first: Result
    password: str
    totp_secret: str
    credentials: Path


@pytest.fixture(scope="module")
def demo_env() -> Iterator[tuple[str, str]]:
    """A generated demo password and TOTP seed in the environment the CLI settings read."""
    generated = (f"Seed-{secrets.token_urlsafe(12)}", pyotp.random_base32())
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("EREV_DEMO_PASSWORD", generated[0])
        patch.setenv("EREV_DEMO_TOTP_SECRET", generated[1])
        get_settings.cache_clear()
        yield generated
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def demo(
    test_database: TestDatabase,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    tmp_path_factory: pytest.TempPathFactory,
) -> DemoRun:
    """Every demo tenant, seeded once through the CLI with the frozen test clock."""
    root = tmp_path_factory.mktemp("web-10")
    services = cli.CliServices(
        clock=frozen_clock(),
        keyring=keyring,
        files=LocalFileStore(root / "files"),
        env=Environment.TEST,
        run_dir=root / "run",
    )
    first = invoke(services, ["seed", "demo", "--tenants", "all"])
    password, totp_secret = demo_env
    return DemoRun(services, first, password, totp_secret, root / "run" / seed.CREDENTIALS_FILE)


def _directory(
    codes: Iterator[str] | tuple[str, ...] | list[str],
) -> dict[str, Mapping[str, object]]:
    with platform_session("tenant_directory", actor_user_id=None, request_id=REQUEST_ID) as db:
        rows = db.execute(select(tenant).where(tenant.c.code.in_(sorted(codes)))).mappings().all()
    return {str(row["code"]): dict(row) for row in rows}


def _tenant_ids() -> dict[str, UUID]:
    return {code: UUID(str(row["id"])) for code, row in _directory(list(CATALOGUE)).items()}


def _read(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _persona_ids() -> dict[str, UUID]:
    emails = [persona.email for persona in personas.PERSONAS]
    with identity_session(request_id=REQUEST_ID) as db:
        rows = db.execute(
            select(app_user.c.email, app_user.c.id).where(app_user.c.email.in_(emails))
        ).all()
    return {str(email).split("@", 1)[0]: UUID(str(user_id)) for email, user_id in rows}


def _members(tenant_id: UUID, ids: Mapping[str, UUID]) -> dict[str, tuple[str, frozenset[str]]]:
    """Persona → (membership status, codes of the active roles it holds for all entities)."""
    keys = {user_id: key for key, user_id in ids.items()}
    with tenant_session(_read(tenant_id), read_only=True) as db:
        memberships = db.execute(
            select(tenant_membership.c.id, tenant_membership.c.user_id, tenant_membership.c.status)
        ).all()
        assignments = db.execute(
            select(role_assignment.c.membership_id, role.c.code, role_assignment.c.is_all_entities)
            .select_from(
                role_assignment.join(
                    role,
                    and_(
                        role.c.tenant_id == role_assignment.c.tenant_id,
                        role.c.id == role_assignment.c.role_id,
                    ),
                )
            )
            .where(role_assignment.c.revoked_at.is_(None), role.c.is_active.is_(True))
        ).all()
    assert all(is_all for _, _, is_all in assignments)
    held: dict[UUID, set[str]] = {}
    for membership_id, code, _ in assignments:
        held.setdefault(UUID(str(membership_id)), set()).add(str(code))
    return {
        keys[UUID(str(user_id))]: (str(status), frozenset(held.get(UUID(str(membership_id)), ())))
        for membership_id, user_id, status in memberships
    }


def _row_counts(tenant_ids: Mapping[str, UUID]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with identity_session(request_id=REQUEST_ID) as db:
        for table in IDENTITY_TABLES:
            counts[table.name] = int(
                db.execute(select(func.count()).select_from(table)).scalar_one()
            )
        for kind, number in db.execute(
            select(security_event.c.kind, func.count()).group_by(security_event.c.kind)
        ).tuples():
            counts[f"security_event:{getattr(kind, 'value', kind)}"] = int(number)
    for code, tenant_id in tenant_ids.items():
        with tenant_session(_read(tenant_id), read_only=True) as db:
            for table in TENANT_TABLES:
                counts[f"{code}:{table.name}"] = int(
                    db.execute(select(func.count()).select_from(table)).scalar_one()
                )
    return counts


def _failure(result: Result) -> str:
    """The command output and, for an unexpected exception, its traceback."""
    if result.exc_info is None or isinstance(result.exception, SystemExit):
        return result.output
    return result.output + "".join(traceback.format_exception(*result.exc_info))


def test_wld_t_catalogue(demo: DemoRun) -> None:
    assert demo.first.exit_code == 0, _failure(demo.first)
    printed = [line for line in demo.first.stdout.splitlines() if COMMAND_LINE.match(line)]
    assert printed == [
        *(f"seeded {code}" for code in CATALOGUE),
        f"recovery codes written to {demo.credentials}",
    ]
    found = _directory(list(CATALOGUE))
    assert set(found) == set(CATALOGUE)
    for code, name in CATALOGUE.items():
        row = found[code]
        assert (row["display_name"], row["kind"], row["is_demo"], row["reporting_currency"]) == (
            name,
            "production",
            True,
            "USD",
        )


def test_wld_u_personas_and_roles(demo: DemoRun) -> None:
    ids = _persona_ids()
    assert set(ids) == set(AVENMOOR_ROLES)
    tenant_ids = _tenant_ids()
    assert _members(tenant_ids["avenmoor"], ids) == {
        key: ("ACTIVE", held) for key, held in AVENMOOR_ROLES.items()
    }
    everyone = set(AVENMOOR_ROLES)
    for code in INDUSTRY:
        industry = _members(tenant_ids[code], ids)
        assert "samuel" not in industry
        assert set(industry) == everyone - {"samuel"}
        assert {status for status, _ in industry.values()} == {"ACTIVE"}
    legacy = _members(tenant_ids["legacy-parity"], ids)
    assert not {"samuel", "nikhil", "jordan"} & set(legacy)
    assert set(legacy) == everyone - {"samuel", "nikhil", "jordan"}


def test_wld_u_r2_totp_factors(demo: DemoRun, keyring: KeyRing) -> None:
    ids = _persona_ids()
    with identity_session(request_id=REQUEST_ID) as db:
        confirmed = set(
            db.scalars(
                select(user_mfa_factor.c.user_id).where(
                    user_mfa_factor.c.user_id.in_(list(ids.values())),
                    user_mfa_factor.c.confirmed_at.is_not(None),
                    user_mfa_factor.c.disabled_at.is_(None),
                )
            )
        )
    assert {key for key, user_id in ids.items() if user_id in confirmed} == MFA_PERSONAS

    # The seed confirmed at the frozen step; the next step's code is inside the window once.
    now = demo.services.clock.now()
    facts = RequestFacts(
        request_id=f"{REQUEST_ID}-marcus", source_ip=None, user_agent=None, now=now
    )
    signed = sessions.sign_in(
        email="marcus@demo.erev",
        password=demo.password,
        facts=facts,
        keyring=keyring,
        previous_token=None,
    )
    code = totp.code_at(demo.totp_secret, totp.time_step(now) + totp.WINDOW)
    verified = mfa.verify(signed, code=code, recovery_code=None, keyring=keyring)
    assert verified.auth.session.mfa_verified_at == now
    assert verified.recovery_codes_remaining is None


def test_dg_run_32_credentials_file(demo: DemoRun) -> None:
    path = demo.credentials
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text(encoding="utf-8")
    assert demo.password not in text
    assert demo.totp_secret not in text
    listed: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        kind, email, *codes = line.split()
        assert kind == "recovery-codes"
        listed[email] = codes
    assert set(listed) == {f"{key}@demo.erev" for key in MFA_PERSONAS}
    for codes in listed.values():
        assert len(codes) == 10
        assert all(RECOVERY_CODE.fullmatch(code) for code in codes)


def test_bs1_d_20_commands_as_personas(demo: DemoRun) -> None:
    ids = _persona_ids()
    avenmoor = _tenant_ids()["avenmoor"]
    with tenant_session(_read(avenmoor), read_only=True) as db:
        inviters = db.execute(
            select(audit_event.c.actor_id, audit_event.c.actor_kind).where(
                audit_event.c.action == "tenant_membership.invite"
            )
        ).all()
        decisions = db.execute(
            select(
                tenant_membership.c.user_id,
                approval_decision.c.decision,
                approval_decision.c.approver_id,
                rule.c.rule_key,
            ).select_from(
                role_assignment.join(
                    approval_decision,
                    and_(
                        approval_decision.c.tenant_id == role_assignment.c.tenant_id,
                        approval_decision.c.approval_request_id
                        == role_assignment.c.approval_request_id,
                    ),
                )
                .join(
                    tenant_membership,
                    and_(
                        tenant_membership.c.tenant_id == role_assignment.c.tenant_id,
                        tenant_membership.c.id == role_assignment.c.membership_id,
                    ),
                )
                .outerjoin(
                    rule,
                    and_(
                        rule.c.tenant_id == approval_decision.c.tenant_id,
                        rule.c.id == approval_decision.c.auto_rule_id,
                    ),
                )
            )
        ).all()
        custom = db.execute(select(role).where(role.c.code == "deal_desk_analyst")).mappings().one()
        permissions = sorted(
            db.scalars(
                select(role_permission.c.permission_code).where(
                    role_permission.c.role_id == custom["id"]
                )
            )
        )
        change = (
            db.execute(
                select(approval_request).where(
                    approval_request.c.subject_type == "ROLE_CHANGE",
                    approval_request.c.subject_id == custom["id"],
                )
            )
            .mappings()
            .one()
        )
        approvers = db.execute(
            select(approval_decision.c.decision, approval_decision.c.approver_id).where(
                approval_decision.c.approval_request_id == change["id"]
            )
        ).all()
    # Ten invitations, every one by tomas as a person.
    assert len(inviters) == len(AVENMOOR_ROLES) - 1
    assert {(actor_id, str(kind)) for actor_id, kind in inviters} == {(ids["tomas"], "USER")}
    # Fifteen assignments (tomas's provisioning grant included). Rule AUTO-BOOTSTRAP approved the
    # thirteen written or requested while nobody but tomas could approve access: every persona
    # without a custom role is invited before anyone accepts. jordan's two came after grace had
    # approved the custom role — a second approver exists from then on, so the exception has ended
    # and she approved them (04 §14.3 item 3; supervisor ruling R-38 (iv) addendum; BS1-D-20).
    assert len(decisions) == sum(len(held) for held in AVENMOOR_ROLES.values())
    later = [row for row in decisions if row.user_id == ids["jordan"]]
    setup_grants = [row for row in decisions if row.user_id != ids["jordan"]]
    assert {(str(row.decision), row.rule_key) for row in setup_grants} == {
        ("AUTO_APPROVE", "AUTO-BOOTSTRAP")
    }
    assert len(setup_grants) == sum(
        len(held) for key, held in AVENMOOR_ROLES.items() if key != "jordan"
    )
    assert [(str(row.decision), row.approver_id, row.rule_key) for row in later] == [
        ("APPROVE", ids["grace"], None)
    ] * len(AVENMOOR_ROLES["jordan"])
    assert (custom["is_active"], custom["is_system"]) == (True, False)
    assert permissions == ["scenario.use"]
    assert (str(change["status"]), change["preparer_id"]) == ("APPROVED", ids["tomas"])
    assert [(str(decision), approver) for decision, approver in approvers] == [
        ("APPROVE", ids["grace"])
    ]


def test_wld_r_04_refuses_non_demo_tenant_and_domain(
    demo: DemoRun,
    keyring: KeyRing,
    clock: FrozenClock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = tenant_factory(keyring=keyring, clock=clock)  # is_demo false
    code = str(plain.tenant["code"])
    stand_in = replace(tenants.CATALOGUE[2], wld_id="WLD-T-90", code=code)
    monkeypatch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, stand_in))
    refused = invoke(demo.services, ["seed", "demo", "--tenants", code])
    assert refused.exit_code == 1, refused.output
    assert refused.stderr.strip() == f"Refusing to seed {code}: is_demo is false"
    assert refused.stdout == ""

    fresh = f"demo-{secrets.token_hex(4)}"
    monkeypatch.setattr(
        tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(stand_in, wld_id="WLD-T-91", code=fresh))
    )
    outsider = replace(personas.PERSONAS[0], email="maya@example.test")
    before = _row_counts({})
    with pytest.raises(
        SeedRefused, match=r"^Refusing to seed persona WLD-U-01: its email is outside demo\.erev$"
    ):
        seed.seed_demo(
            [fresh],
            clock,
            keyring=keyring,
            files=LocalFileStore(tmp_path / "files"),
            secrets=seed.DemoSecrets(password=demo.password, totp_secret=demo.totp_secret),
            credentials_path=tmp_path / seed.CREDENTIALS_FILE,
            request_id=f"{REQUEST_ID}-outsider",
            personas=(outsider, *personas.PERSONAS[1:]),
        )
    assert _row_counts({}) == before  # not even the directory read ran
    assert fresh not in _directory([fresh])
    assert not (tmp_path / seed.CREDENTIALS_FILE).exists()


def test_dg_mk_seed_requires_password(demo: DemoRun, monkeypatch: pytest.MonkeyPatch) -> None:
    prefixes = ("MAKEFLAGS", "MAKELEVEL", "MFLAGS", "PYTEST_")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(prefixes) and key != "EREV_DEMO_PASSWORD"
    }
    env["EREV_DOTENV"] = str(ROOT / ".run" / "tmp" / "absent.env")
    result = subprocess.run(
        ["make", "--no-print-directory", "seed"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    # L1-5-Q-6: the recipe exits 1; GNU make then reports the failed target and exits 2.
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[seed] Error 1" in result.stderr
    assert result.stdout.splitlines() == [f"FAIL seed: {MISSING_PASSWORD}"]

    # DG-RUN-32: the command itself refuses too. An empty variable overrides any .env line.
    with monkeypatch.context() as patch:
        patch.setenv("EREV_DEMO_PASSWORD", "")
        get_settings.cache_clear()
        refused = invoke(demo.services, ["seed", "demo", "--tenants", "avenmoor"])
    get_settings.cache_clear()
    assert refused.exit_code == 1, refused.output
    assert refused.stderr.strip() == MISSING_PASSWORD


def test_seed_second_run_skips(demo: DemoRun, log_stream: io.StringIO) -> None:
    tenant_ids = _tenant_ids()
    before = _row_counts(tenant_ids)
    again = invoke(demo.services, ["seed", "demo", "--tenants", "all"])
    assert again.exit_code == 0, again.output
    assert again.stdout.splitlines() == [f"skipped {code}" for code in CATALOGUE]
    after = _row_counts(tenant_ids)
    scope_key = "security_event:PLATFORM_SCOPE_USED"
    # L1-5-Q-1: the one directory read is recorded (DG-KRN-DB-03); nothing else is written.
    assert after.pop(scope_key) - before.pop(scope_key) == 1
    assert after == before
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert [
        event["tenant_code"] for event in events if event["event"] == "seed.tenant_skipped"
    ] == list(CATALOGUE)


def test_dg_mk_seed_with_close_refuses_a_tenant_seeded_without_its_close(
    demo: DemoRun, monkeypatch: pytest.MonkeyPatch, log_stream: io.StringIO
) -> None:
    """BUILD_SPEC CLO-22 (dev-guide DG-MK-seed rev 1.221): the close is a stage the seed runs
    before the tenant's open-period items, which hold every lock made after them. The module's
    tenants are seeded without it, so ``--with-close`` is refused for ``avenmoor`` by name and
    before any write; a tenant that has no such stage is skipped as without the flag."""
    # Asked for the close, the command registers the CSV ledger adapter in its process (DG-LAY-03),
    # which here is the test's: the registry is put back as it was.
    monkeypatch.delitem(gl_ports.GL_ADAPTERS, GlAdapter.CSV, raising=False)
    tenant_ids = _tenant_ids()
    before = _row_counts(tenant_ids)
    refused = invoke(demo.services, ["seed", "demo", "--tenants", "avenmoor", "--with-close"])
    assert refused.exit_code == 1, refused.output
    assert refused.stderr.strip() == (
        "Refusing to close avenmoor: it is seeded without its close, and its open items hold "
        "every lock; run make seed RESET=1 CLOSE=1"
    )
    assert refused.stdout == ""
    skipped = invoke(demo.services, ["seed", "demo", "--tenants", "fernhill", "--with-close"])
    assert skipped.exit_code == 0, skipped.output
    # The command's own line is all of stdout: its log goes to the pipeline (here ``log_stream``,
    # as for the run before; ``erev`` itself installs it on stderr, DG-KRN-TEN-04).
    assert skipped.stdout.splitlines() == ["skipped fernhill"]
    events = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert [
        event["tenant_code"] for event in events if event["event"] == "seed.tenant_skipped"
    ] == ["fernhill"]
    assert GlAdapter.CSV in gl_ports.GL_ADAPTERS
    after = _row_counts(tenant_ids)
    scope_key = "security_event:PLATFORM_SCOPE_USED"
    assert after.pop(scope_key) - before.pop(scope_key) == 2  # the two directory reads
    assert after == before
