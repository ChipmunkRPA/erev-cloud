"""CTR-20 Avenmoor key contracts demo seed (docs/02-PRD.md §2.1 WLD-R-01, WLD-R-02, WLD-R-06; §2.7;
§2.8 WLD-X-01, WLD-X-05, WLD-X-20 to WLD-X-22; §2.9; BUILD_SPEC CTR-20, XR-09, BS3-D-09).

As in the RFD-16 module, WLD-T-01 is seeded through ``seed_demo`` under a stand-in tenant code with
the PRD §2.3 cast at module-unique ``demo.erev`` addresses, and the tests read what the persona
commands wrote. Figures are schedule and allocation amounts that no close run changes (BS3-D-09).

R-RC-1 (plan L5-4-B1): K-06 estimate versions (CTR-12 fragment) and the K-09 commission cost
(CTR-14) are not seeded, so no test here asserts them.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.auth import totp
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    contract,
    contract_event,
    contract_hold,
    contract_version,
    exception_item,
    job,
    judgement_record,
    legal_entity,
    modification,
    obligation_version,
    period,
    schedule_line,
    tenant,
    tenant_membership,
)
from erev_api.domain.contracts import modifications
from erev_api.domain.demo import builders, personas, seed, tenants
from erev_api.domain.demo.avenmoor import ACCOUNTANT, background
from erev_api.domain.demo.builders import BuildContext
from erev_api.domain.demo.personas import Persona
from erev_api.enums import ModificationKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from erev_api.schemas.modifications import ModificationCreateIn
from sqlalchemy import and_, func, select, text
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import Member, sign_in, workspace
from support.reference import get, post

# Seeding Avenmoor with its contracts through the persona commands takes minutes (DG-TST-08).
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-ctr-20"
AVENMOOR = tenants.CATALOGUE[1]  # WLD-T-01
KEY_CONTRACTS = {
    "K-01": "SF-ORD-10001",
    "K-01b": "SF-ORD-10388",
    "K-02": "SF-ORD-10002",
    "K-03": "PRJ-CB-2026-01",
    "K-04": "SF-ORD-UK-2001",
    "K-05": "NS-SO-DE-5001",
    "K-06": "NS-SO-DE-5002",
    "K-07": "NS-SO-DE-5003",
    "K-08": "SF-ORD-10003",
    "K-09": "SF-ORD-10417",
    "K-10": "JP-LIC-0001",
    "K-11": "NS-SO-DE-5004",
}
# L5-4-Q-9 (COST_TO_COST, USAGE measures not built), D-88 L7-6-Q-1 (K-04: the gate clause keeps it a
# draft for the rc; the L8 release gate failed the screens e2e with its GBP lines in AVM-US),
# L5-4-Q-12 (stateless April-calendar periods before AVM-JP's first period).
BLOCKED = frozenset({"K-03", "K-04", "K-08", "K-10"})
DISMISSED_RATIONALE = "Separate purchasing entities; negotiated independently."
HOLD_REASON = "Customer dispute on invoice INV-US-3988"


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    code: str
    user_ids: Mapping[str, UUID]  # persona key → app_user id
    # The K-02 change of PRD WLD-X-06 as the seeded world previews it (``_k02_change``).
    k02_preview: Mapping[str, Any]


def _read(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_read(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _cast(suffix: str) -> tuple[Persona, ...]:
    return tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )


# PRD WLD-X-06 / J-05.1: K-02's change order CR-MARROWBY-2026-09 — 50 seats from 16 Sep 2026 to
# 31 Dec 2027 for 60,000.00, counted in seat-months (775) as the AVM-SEAT-MO entry prices them.
K02_CHANGE = {
    "effective_date": "2026-09-16",
    "kind": ModificationKind.CO_TERM.value,
    "reference": "CR-MARROWBY-2026-09",
    "lines": [
        {
            "obligation_key": "O2",
            "action": "ADD",
            "product_code": "AVM-SEAT-MO",
            "quantity_delta": "775",
            "consideration_delta": {"amount": "60000.00", "currency": "USD"},
            "start_date": "2026-09-16",
            "end_date": "2027-12-31",
        }
    ],
    "rationale": "Marrowby adds 50 seats for the remaining term (PRD WLD-X-06).",
}


def _k02_change(found: dict[str, Any]) -> builders.Builder:
    """A last builder of the seed run: Maya drafts the K-02 change, classifies it and asks for
    its preview; the worker's run stores it; ``found`` keeps the proposal and the stored
    summary. Inside the run, because the run signs its cast out when it ends. The preview is a
    dry run (CV-16): no event, no contract version — a DRAFT modification stays on K-02."""

    def build(ctx: BuildContext) -> None:
        create = modifications.CREATE_PERMISSION
        with ctx.read() as session:
            contract_id = session.execute(
                select(contract.c.id).where(contract.c.external_id == KEY_CONTRACTS["K-02"])
            ).scalar_one()
        with ctx.command(ACCOUNTANT, create) as uow:
            created = modifications.create_modification(
                uow, contract_id=contract_id, body=ModificationCreateIn.model_validate(K02_CHANGE)
            )
        with ctx.command(ACCOUNTANT, create) as uow:
            classified = modifications.classify(uow, modification_id=created.id)
        with ctx.command(ACCOUNTANT, create) as uow:
            queued = modifications.request_preview(uow, modification_id=created.id)
        # The worker fetches the job's task and runs it (the seam of the CTR-17 acceptance tests).
        with tenant_session(_read(ctx.tenant_id)) as session:
            task_id = session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == queued.id)
            ).scalar_one()
            session.execute(
                text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                {"id": task_id},
            )
        run_job(
            queued.id,
            ctx.tenant_id,
            attempt=1,
            runtime=JobRuntime(clock=ctx.clock, keyring=ctx.keyring, files=ctx.files),
        )
        with ctx.read() as session:
            row = (
                session.execute(select(modification).where(modification.c.id == created.id))
                .mappings()
                .one()
            )
            document = modifications.read_preview(
                session, dict(row), files=ctx.files, keyring=ctx.keyring
            )
        assert document is not None, "the preview job stored no preview"
        found["proposed"] = dict(classified.proposed_treatments)
        found["summary"] = document["summary"]

    return build


def _assert_prd_split(preview: Mapping[str, Any]) -> None:
    """PRD WLD-X-06 (rev 1.21), SCREENS §7.12 and CTR-17's acceptance: both obligations
    prospective, the price 240,000.00 → 300,000.00 with no catch-up, and the remaining
    allocation O1 148,451.55 / O2 66,726.53."""
    summary = preview["summary"]
    assert preview["proposed"] == {"O1": "PROSPECTIVE", "O2": "PROSPECTIVE"}
    assert (
        Decimal(summary["transaction_price_before"]["amount"]),
        Decimal(summary["transaction_price_after"]["amount"]),
        Decimal(summary["catch_up_total"]["amount"]),
    ) == (Decimal("240000.00"), Decimal("300000.00"), Decimal("0.00"))
    assert {
        item["obligation_key"]: Decimal(item["amount"]["amount"])
        for item in summary["remaining_allocation_after"]
    } == {"O1": Decimal("148451.55"), "O2": Decimal("66726.53")}


def _build(
    keyring: KeyRing,
    root: Path,
    cast: tuple[Persona, ...],
    env: tuple[str, str],
    clock: FrozenClock,
) -> World:
    """Seed a stand-in WLD-T-01 under a fresh code through ``seed_demo`` with the frozen clock."""
    stamp_test_release()  # 05 REL-03: the release row a computation names
    code = f"avm-{secrets.token_hex(4)}"
    preview: dict[str, Any] = {}
    registered = builders.BUILDERS[AVENMOOR.wld_id]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=code)))
        patch.setattr(
            builders,
            "BUILDERS",
            {**builders.BUILDERS, AVENMOOR.wld_id: (*registered, _k02_change(preview))},
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
    emails = {persona.email: persona.key for persona in cast}
    with identity_session(request_id=REQUEST_ID) as db:
        found = db.execute(
            select(app_user.c.email, app_user.c.id).where(app_user.c.email.in_(sorted(emails)))
        ).all()
    user_ids = {emails[str(email)]: UUID(str(user_id)) for email, user_id in found}
    return World(tenant_id=UUID(str(found_id)), code=code, user_ids=user_ids, k02_preview=preview)


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
    return _build(keyring, tmp_path_factory.mktemp("ctr-20-a"), cast, demo_env, frozen_clock())


def _contracts(world: World, external_ids: list[str]) -> dict[str, dict[str, Any]]:
    rows = _rows(
        world.tenant_id,
        select(contract.c.id, contract.c.external_id, contract.c.status).where(
            contract.c.external_id.in_(sorted(external_ids))
        ),
    )
    return {str(row["external_id"]): row for row in rows}


def test_key_contracts_booked_and_active(world: World) -> None:
    """Not asserted (L5-4-Q-9, Q-12; D-88 L7-6-Q-1): K-03, K-04, K-08 and K-10 ACTIVE. The rc engine
    refuses the activations of K-03, K-08 and K-10, and the L7-6-Q-1 gate clause keeps K-04 a draft,
    so they stay drafts with a reviewed Step 1 record."""
    found = _contracts(world, list(KEY_CONTRACTS.values()))
    assert {external: str(row["status"]) for external, row in found.items()} == {
        external: "DRAFT" if key in BLOCKED else "ACTIVE" for key, external in KEY_CONTRACTS.items()
    }
    personas_by_id = {user_id: key for key, user_id in world.user_ids.items()}
    maya = world.user_ids["maya"]
    for key in BLOCKED:
        [record] = _rows(
            world.tenant_id,
            select(judgement_record.c.status, judgement_record.c.reviewer_id).where(
                judgement_record.c.contract_id == found[KEY_CONTRACTS[key]]["id"],
                judgement_record.c.topic == "COLLECTIBILITY",
            ),
        )
        assert (str(record["status"]), record["reviewer_id"]) == (
            "REVIEWED",
            world.user_ids["priya"],
        ), key
    active = {KEY_CONTRACTS[key] for key in KEY_CONTRACTS if key not in BLOCKED}
    for external, row in found.items():
        if external not in active:
            continue
        [request] = _rows(
            world.tenant_id,
            select(
                approval_request.c.id, approval_request.c.status, approval_request.c.preparer_id
            ).where(
                approval_request.c.subject_type == "CONTRACT_ACTIVATION",
                approval_request.c.subject_id == row["id"],
            ),
        )
        assert (str(request["status"]), request["preparer_id"]) == ("APPROVED", maya), external
        decisions = _rows(
            world.tenant_id,
            select(approval_decision.c.decision, approval_decision.c.approver_id).where(
                approval_decision.c.approval_request_id == request["id"]
            ),
        )
        assert decisions, external
        for decision in decisions:
            assert str(decision["decision"]) == "APPROVE", external
            assert decision["approver_id"] in personas_by_id, external
            assert decision["approver_id"] != maya, external
        [activated] = _rows(
            world.tenant_id,
            select(contract_event.c.approval_request_id, contract_event.c.origin).where(
                contract_event.c.contract_id == row["id"],
                contract_event.c.event_type == "CONTRACT_ACTIVATED",
            ),
        )
        assert (activated["approval_request_id"], str(activated["origin"])) == (
            request["id"],
            "SYSTEM",
        ), external
    [k09] = _rows(
        world.tenant_id,
        select(approval_request.c.id).where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == found[KEY_CONTRACTS["K-09"]]["id"],
        ),
    )
    approvers = _rows(
        world.tenant_id,
        select(approval_decision.c.approver_id).where(
            approval_decision.c.approval_request_id == k09["id"]
        ),
    )
    assert [personas_by_id[item["approver_id"]] for item in approvers] == ["priya"]


def _allocations(world: World, external_id: str) -> dict[str, Decimal]:
    """Allocated amount per obligation in the contract's latest ASC606 version."""
    rows = _rows(
        world.tenant_id,
        select(
            obligation_version.c.obligation_key,
            obligation_version.c.allocated_amount,
            contract_version.c.version_no,
        )
        .select_from(
            obligation_version.join(
                contract_version,
                and_(
                    contract_version.c.tenant_id == obligation_version.c.tenant_id,
                    contract_version.c.id == obligation_version.c.contract_version_id,
                ),
            ).join(
                contract,
                and_(
                    contract.c.tenant_id == obligation_version.c.tenant_id,
                    contract.c.id == obligation_version.c.contract_id,
                ),
            )
        )
        .where(contract.c.external_id == external_id, obligation_version.c.book_code == "ASC606"),
    )
    latest = max(int(row["version_no"]) for row in rows)
    return {
        str(row["obligation_key"]): Decimal(row["allocated_amount"])
        for row in rows
        if int(row["version_no"]) == latest
    }


def _schedule(world: World, external_id: str, obligation_key: str, month: date) -> Decimal:
    """The obligation's NORMAL schedule amount of the period starting ``month`` in the latest
    ASC606 version."""
    joined = (
        schedule_line.join(
            contract_version,
            and_(
                contract_version.c.tenant_id == schedule_line.c.tenant_id,
                contract_version.c.id == schedule_line.c.contract_version_id,
            ),
        )
        .join(
            contract,
            and_(
                contract.c.tenant_id == schedule_line.c.tenant_id,
                contract.c.id == schedule_line.c.contract_id,
            ),
        )
        .join(
            period,
            and_(
                period.c.tenant_id == schedule_line.c.tenant_id,
                period.c.id == schedule_line.c.period_id,
            ),
        )
        .join(
            obligation_version,
            and_(
                obligation_version.c.tenant_id == schedule_line.c.tenant_id,
                obligation_version.c.contract_version_id == schedule_line.c.contract_version_id,
                obligation_version.c.obligation_id == schedule_line.c.subject_id,
            ),
        )
    )
    rows = _rows(
        world.tenant_id,
        select(schedule_line.c.amount, contract_version.c.version_no)
        .select_from(joined)
        .where(
            contract.c.external_id == external_id,
            schedule_line.c.book_code == "ASC606",
            schedule_line.c.line_type == "NORMAL",
            obligation_version.c.obligation_key == obligation_key,
            period.c.start_date == month,
        ),
    )
    latest = max(int(row["version_no"]) for row in rows)
    return sum(
        (Decimal(row["amount"]) for row in rows if int(row["version_no"]) == latest), Decimal(0)
    )


def test_key_figures(world: World) -> None:
    """Not asserted (L5-4-Q-12): K-10 revenue Apr 2026 50,000,000 JPY, since K-10 stays a draft."""
    assert _allocations(world, KEY_CONTRACTS["K-01"]) == {
        "O1": Decimal("118800.00"),
        "O2": Decimal("16200.00"),
    }
    assert _allocations(world, KEY_CONTRACTS["K-11"]) == {
        "O1": Decimal("89174.31"),
        "O2": Decimal("18825.69"),
    }
    september = date(2026, 9, 1)
    assert _schedule(world, KEY_CONTRACTS["K-02"], "O1", september) == Decimal("9863.01")
    assert _schedule(world, KEY_CONTRACTS["K-09"], "O1", september) == Decimal("2956.20")


def test_seeded_open_period_items(world: World) -> None:
    found = _contracts(
        world,
        [
            background.PENDING_ACTIVATION,
            background.HELD,
            background.JUDGED,
            background.DUPLICATED,
            background.DUPLICATE,
            KEY_CONTRACTS["K-05"],
            KEY_CONTRACTS["K-11"],
        ],
    )
    maya = world.user_ids["maya"]
    # WLD-B-01: the activation of BG-AVM-0020 (TP USD 146,000.00) waits for approval.
    [pending] = _rows(
        world.tenant_id,
        select(
            approval_request.c.status,
            approval_request.c.preparer_id,
            approval_request.c.amount_functional,
        ).where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == found[background.PENDING_ACTIVATION]["id"],
        ),
    )
    assert (str(pending["status"]), pending["preparer_id"]) == ("PENDING", maya)
    assert Decimal(pending["amount_functional"]) == Decimal("146000.00")
    assert str(found[background.PENDING_ACTIVATION]["status"]) == "DRAFT"  # read: PENDING_REVIEW
    # WLD-B-03: the PRINCIPAL_AGENT judgement record of BG-AVM-0023 is submitted, unreviewed.
    [judged] = _rows(
        world.tenant_id,
        select(
            judgement_record.c.status, judgement_record.c.created_by, judgement_record.c.reviewer_id
        ).where(
            judgement_record.c.contract_id == found[background.JUDGED]["id"],
            judgement_record.c.topic == "PRINCIPAL_AGENT",
        ),
    )
    assert (str(judged["status"]), judged["created_by"], judged["reviewer_id"]) == (
        "SUBMITTED",
        maya,
        None,
    )
    # WLD-B-05: the journal_export hold of BG-AVM-0021 is open.
    [held] = _rows(
        world.tenant_id,
        select(
            contract_hold.c.hold_type, contract_hold.c.reason, contract_hold.c.released_at
        ).where(contract_hold.c.contract_id == found[background.HELD]["id"]),
    )
    assert (str(held["hold_type"]), held["reason"], held["released_at"]) == (
        "journal_export",
        HOLD_REASON,
        None,
    )
    # WLD-B-08: BG-AVM-0030 duplicates BG-AVM-0029 and is active.
    assert str(found[background.DUPLICATE]["status"]) == "ACTIVE"
    assert str(found[background.DUPLICATED]["status"]) == "ACTIVE"
    # PRD WLD-K-11: the K-05 and K-11 suggestion is dismissed with the rationale. [J] L5-4-Q-2: the
    # dismissal needs contract.create (API-R-28; PRD ACT-04), so maya records it, not priya.
    ids = sorted(str(found[KEY_CONTRACTS[key]]["id"]) for key in ("K-05", "K-11"))
    suggestions = _rows(
        world.tenant_id,
        select(
            exception_item.c.status,
            exception_item.c.resolution,
            exception_item.c.resolved_by,
            exception_item.c.source_payload,
        ).where(exception_item.c.code == "COMBINATION_SUGGESTED"),
    )
    [k05_k11] = [
        item for item in suggestions if sorted(item["source_payload"]["contract_ids"]) == ids
    ]
    assert (str(k05_k11["status"]), k05_k11["resolution"], k05_k11["resolved_by"]) == (
        "DISMISSED",
        DISMISSED_RATIONALE,
        maya,
    )


def test_background_counts(world: World) -> None:
    rows = _rows(
        world.tenant_id,
        select(legal_entity.c.code, func.count().label("contracts"))
        .select_from(
            contract.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract.c.tenant_id,
                    legal_entity.c.id == contract.c.contracting_entity_id,
                ),
            )
        )
        .where(contract.c.external_id.like(f"{background.PREFIX}%"))
        .group_by(legal_entity.c.code),
    )
    assert {str(row["code"]): int(row["contracts"]) for row in rows} == {
        "AVM-US": 100,
        "AVM-UK": 30,
        "AVM-DE": 40,
        "AVM-JP": 10,
    }


def _canonical(value: Any) -> Any:
    """``value`` without generated ids, timestamps or content digests (which embed ids)."""
    if isinstance(value, UUID | datetime):
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not str(key).endswith("sha256")
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


def _event_hash(world: World) -> str:
    rows = _rows(
        world.tenant_id,
        select(
            contract.c.external_id,
            contract_event.c.stream_version,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.origin,
            contract_event.c.payload,
        )
        .select_from(
            contract_event.join(
                contract,
                and_(
                    contract.c.tenant_id == contract_event.c.tenant_id,
                    contract.c.id == contract_event.c.contract_id,
                ),
            )
        )
        .where(contract.c.external_id.in_(sorted(KEY_CONTRACTS.values())))
        .order_by(contract.c.external_id, contract_event.c.stream_version),
    )
    canonical = json.dumps([_canonical(row) for row in rows], sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_seed_deterministic(
    world: World,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    cast: tuple[Persona, ...],
    tmp_path: Path,
) -> None:
    again = _build(keyring, tmp_path, cast, demo_env, frozen_clock())
    assert again.tenant_id != world.tenant_id
    assert _event_hash(again) == _event_hash(world)
    assert background.specs() == background.specs()


def test_k02_change_previews_the_prd_split(world: World) -> None:
    """Item DEMO-SSP-BASIS-1 (supervisor's ruling on MOD-K02-SPLIT-1, 2026-10-01): PRD WLD-X-06 on
    the SEEDED world — the K-02 change ``CR-MARROWBY-2026-09`` previews O1 148,451.55 / O2
    66,726.53, as the PRD (rev 1.21), SCREENS §7.12 and CTR-17's acceptance state it. The seed
    had the AVM-SEAT-MO entry as ``AMOUNT`` — on a series entry the remaining-increments reading,
    taken as is — so the engine weighed O1 at 2,400 x 100.00 = 240,000.00 instead of its
    remaining increments at the modification date (155,178.08), and the demo's flagship change
    previewed 166,723.94 / 48,454.14. The entry declares ``PER_INCREMENT`` with ``INCREMENTS``
    (04 E-49; ENGINE_SPEC S06-R-11 series row). ``test_key_figures`` holds that the inception
    figures did not move with it."""
    _assert_prd_split(world.k02_preview)


def test_the_august_revenue_line_names_each_of_its_contracts(
    world: World,
    keyring: KeyRing,
    demo_env: tuple[str, str],
    cast: tuple[Persona, ...],
    app_settings: Settings,
) -> None:
    """04 API-S-SubledgerLine ``contract_external_id`` (rev 1.159; supervisor ruling of 2026-10-01
    on the e2e row ``SF-06:run-lines``). The journal run that row calculates — AVM-US, FY2026-P08,
    ASC606, as Maya — has one line on revenue account 4010: at the default grain it sums the August
    revenue of every seeded contract of the entity. The source-lines drawer read ``GET
    /contracts/{id}`` once per contract to name its rows (91 reads of about 0.2 s here) before it
    showed one. The drill now names the contract on every line, in the route's order, so nothing
    more is read. Last in the module: it adds a journal run to the seeded tenant."""
    clock = frozen_clock()
    # Maya holds a factor (PRD WLD-U-R2 rev 1.153). The seeds of this module spent the TOTP steps of
    # the frozen instant for her — the enrolment, then the second seed's verification — so her
    # sign-in answers the challenge two steps later.
    clock.advance(2 * totp.STEP)
    app = create_app(app_settings, clock=clock)
    email = next(persona.email for persona in cast if persona.key == "maya")
    [membership] = _rows(
        world.tenant_id,
        select(tenant_membership.c.id).where(tenant_membership.c.user_id == world.user_ids["maya"]),
    )
    someone = Member(
        user_id=world.user_ids["maya"],
        email=email,
        tenant_id=world.tenant_id,
        membership_id=UUID(str(membership["id"])),
    )
    maya = workspace(app, someone, sign_in(app, email, demo_env[0]), secret=demo_env[1])
    created = post(
        app,
        "/api/v1/journal-runs",
        maya,
        {"entity_code": "AVM-US", "period_key": "FY2026-P08", "book": "ASC606"},
    )
    assert created.status_code == 202, created.text
    job_id = UUID(str(created.json()["id"]))
    with tenant_session(_read(world.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"), {"id": task_id}
        )
    files = LocalFileStore(app_settings.file_root)
    run_job(
        job_id,
        world.tenant_id,
        attempt=1,
        runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
    )
    run_id = created.headers["X-Erev-Journal-Run-Id"]
    listed = get(
        app, f"/api/v1/journal-runs/{run_id}/lines", maya, {"limit": 200, "account_code": "4010"}
    )
    assert listed.status_code == 200, listed.text
    [revenue] = listed.json()["items"]
    assert revenue["contract"] is None  # the line belongs to no single contract

    drilled = get(app, revenue["links"]["drill"], maya, {"limit": 200})
    assert drilled.status_code == 200, drilled.text
    items = drilled.json()["items"]
    assert drilled.json()["next_cursor"] is None
    assert len(items) == revenue["source_line_count"] > 50
    external = {
        str(row["id"]): str(row["external_id"])
        for row in _rows(world.tenant_id, select(contract.c.id, contract.c.external_id))
    }
    assert all(item["contract_id"] is not None for item in items)
    assert [item["contract_external_id"] for item in items] == [
        external[item["contract_id"]] for item in items
    ]
    assert [item["id"] for item in items] == sorted(item["id"] for item in items)
    # one journal line, one contract per source line: what the drawer read one by one
    assert len({item["contract_id"] for item in items}) > 50
