"""DIN-15 Avenmoor data-in seed: WLD-B-04 (docs/02-PRD.md §2.1 WLD-R-02; §2.9 WLD-B-04; SCREENS
§12.2 sample world, §13.2; BUILD_SPEC DIN-15, XR-09).

As in the RFD-16 and CTR-20 modules, WLD-T-01 is seeded through ``seed_demo`` under a stand-in
tenant code with the PRD §2.3 cast at module-unique ``demo.erev`` addresses. The builders of the
world before ``imports`` run as registered, except that the key contracts are left out and only
the fourteen background contracts the progress files name are booked and activated: the imports
builder reads nothing else, and the full world takes minutes (DG-TST-08).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    contract_event,
    exception_item,
    file_object,
    import_row,
    import_upload,
    job,
    tenant,
)
from erev_api.domain.demo import builders, personas, seed, tenants
from erev_api.domain.demo.avenmoor import background, imports, policies, reference, ssp
from erev_api.domain.demo.avenmoor import contracts as key_contracts
from erev_api.domain.demo.builders import BuildContext
from erev_api.files.store import LocalFileStore
from sqlalchemy import and_, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release

# Seeding the reference data, policies and fourteen activations takes more than 10 seconds.
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-din-15"
AVENMOOR = tenants.CATALOGUE[1]  # WLD-T-01
OVER_DELIVERY = "PROGRESS_OVER_DELIVERY"


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    code: str
    user_ids: Mapping[str, UUID]  # persona key → app_user id


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _prerequisites(ctx: BuildContext) -> None:
    """The product assessments activations need (``contracts.assess_products``, L5-4-Q-8)."""
    key_contracts.assess_products(ctx)


def _named_background(ctx: BuildContext) -> None:
    """The background contracts the progress files name, booked and activated as ``background``
    does."""
    named = [spec for spec in background.specs() if spec.external_id in imports.CONTRACTS]
    background.build(ctx, named)


def _build(keyring: KeyRing, root: Path, env: tuple[str, str], clock: FrozenClock) -> World:
    stamp_test_release()  # 05 REL-03: the release row a computation names
    code = f"avm-{secrets.token_hex(4)}"
    suffix = secrets.token_hex(3)
    cast = tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )
    world_builders = (
        reference.build,
        ssp.build,
        policies.build,
        _prerequisites,
        _named_background,
        imports.build,
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=code)))
        patch.setattr(builders, "BUILDERS", {AVENMOOR.wld_id: world_builders})
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
    return World(tenant_id=UUID(str(found_id)), code=code, user_ids=user_ids)


@pytest.fixture(scope="module")
def world(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> World:
    env = (f"Seed-{secrets.token_urlsafe(12)}", pyotp.random_base32())
    return _build(keyring, tmp_path_factory.mktemp("din-15"), env, frozen_clock())


def _imports(world: World) -> dict[str, dict[str, Any]]:
    rows = _rows(
        world.tenant_id,
        select(
            import_upload.c.id,
            import_upload.c.template_code,
            import_upload.c.status,
            import_upload.c.row_count,
            import_upload.c.valid_row_count,
            import_upload.c.warning_count,
            import_upload.c.error_count,
            import_upload.c.created_by,
            import_upload.c.approval_request_id,
            file_object.c.original_filename,
        ).select_from(
            import_upload.join(
                file_object,
                and_(
                    file_object.c.tenant_id == import_upload.c.tenant_id,
                    file_object.c.id == import_upload.c.file_object_id,
                ),
            )
        ),
    )
    return {str(row["original_filename"]): row for row in rows}


def _status(value: Any) -> str:
    return str(getattr(value, "value", value))


def test_wld_b_04_invalid_import_and_items(world: World) -> None:
    found = _imports(world)
    assert set(found) == {imports.INVALID_FILE, imports.CORRECTED_FILE}
    maya = world.user_ids["maya"]
    booked = imports.booked_quantities()

    # WLD-B-04: the invalid upload is INVALID with two PROGRESS_OVER_DELIVERY errors, rows 5 and 9.
    invalid = found[imports.INVALID_FILE]
    assert (invalid["template_code"], _status(invalid["status"]), invalid["created_by"]) == (
        "progress_events",
        "INVALID",
        maya,
    )
    assert (
        invalid["row_count"],
        invalid["valid_row_count"],
        invalid["warning_count"],
        invalid["error_count"],
    ) == (14, 12, 0, 2)
    items = _rows(
        world.tenant_id,
        select(
            exception_item.c.code,
            exception_item.c.source,
            exception_item.c.severity,
            exception_item.c.status,
            exception_item.c.message,
            import_row.c.row_number,
        )
        .select_from(
            exception_item.join(
                import_row,
                and_(
                    import_row.c.tenant_id == exception_item.c.tenant_id,
                    import_row.c.id == exception_item.c.import_row_id,
                ),
            )
        )
        .where(exception_item.c.import_upload_id == invalid["id"])
        .order_by(import_row.c.row_number),
    )
    expected = []
    for row_number, external_id in ((5, "BG-AVM-0004"), (9, "BG-AVM-0008")):
        quantity = booked[external_id]
        expected.append(
            (
                OVER_DELIVERY,
                "IMPORT",
                "BLOCKING",
                "OPEN",
                f"Row {row_number}, column Quantity: {external_id}, obligation O1 (AVM-SEAT-MO): "
                f"requested {quantity + imports.EXTRA}, remaining {quantity}. ({OVER_DELIVERY})",
                row_number,
            )
        )
    assert [
        (
            _status(item["code"]),
            _status(item["source"]),
            _status(item["severity"]),
            _status(item["status"]),
            item["message"],
            item["row_number"],
        )
        for item in items
    ] == expected
    assert invalid["approval_request_id"] is None

    # The corrected file is committed: maya submitted it, priya approved the IMPORT_COMMIT request.
    corrected = found[imports.CORRECTED_FILE]
    assert (_status(corrected["status"]), corrected["created_by"]) == ("COMMITTED", maya)
    assert (corrected["row_count"], corrected["valid_row_count"], corrected["error_count"]) == (
        14,
        14,
        0,
    )
    [request] = _rows(
        world.tenant_id,
        select(
            approval_request.c.id, approval_request.c.status, approval_request.c.preparer_id
        ).where(
            approval_request.c.subject_type == "IMPORT_COMMIT",
            approval_request.c.subject_id == corrected["id"],
        ),
    )
    assert (_status(request["status"]), request["preparer_id"]) == ("APPROVED", maya)
    assert request["id"] == corrected["approval_request_id"]
    decisions = _rows(
        world.tenant_id,
        select(approval_decision.c.decision, approval_decision.c.approver_id).where(
            approval_decision.c.approval_request_id == request["id"]
        ),
    )
    assert [(_status(item["decision"]), item["approver_id"]) for item in decisions] == [
        ("APPROVE", world.user_ids["priya"])
    ]
    events = _rows(
        world.tenant_id,
        select(
            contract_event.c.event_type, contract_event.c.origin, contract_event.c.payload
        ).where(contract_event.c.import_upload_id == corrected["id"]),
    )
    assert len(events) == 14
    assert {(_status(item["event_type"]), _status(item["origin"])) for item in events} == {
        ("DELIVERY_RECORDED", "IMPORT")
    }
    assert (
        sorted(str(item["payload"]["quantity"]) for item in events) == [str(imports.DELIVERED)] * 14
    )
    assert (
        _rows(
            world.tenant_id,
            select(exception_item.c.id).where(exception_item.c.import_upload_id == corrected["id"]),
        )
        == []
    )
    # Every job of both imports ran to the end as the worker runs it.
    states = _rows(
        world.tenant_id,
        select(job.c.kind, job.c.state).where(
            job.c.subject_id.in_([invalid["id"], corrected["id"]])
        ),
    )
    assert sorted((_status(item["kind"]), _status(item["state"])) for item in states) == [
        ("IMPORT_COMMIT", "SUCCEEDED"),
        ("IMPORT_DIFF", "SUCCEEDED"),
        ("IMPORT_VALIDATE", "SUCCEEDED"),
        ("IMPORT_VALIDATE", "SUCCEEDED_WITH_EXCEPTIONS"),
    ]
