"""The reconciliation lines of a migration as the route answers them (04 §15.3 API-R-48, API-C-06;
T-MIG-03; SCREENS_B §10.3; RPT-41 "exact decimal text").

A T-MIG-03 value is ``erev.exact`` — NUMERIC(38,18) — and API-C-06 states such a value as a string
with trailing zeros trimmed and no exponent. The route wrote ``str`` of the stored ``Decimal``
instead, which reads a zero at that scale as ``0E-18``: the response model refuses the text, so
``GET /migrations/{id}/reconciliation-lines`` answered 500 for every batch that holds a line that
reconciles — every reconciled migration. Measured on WLD-K-04 with one line whose difference is
zero (item SCOPE-WORKSPACE-LISTS-1 (c2), answer Q5 of the supervisor's ruling of 2026-10-01).

World: ``support.factories.import_world`` — a Revenue Accountant of all entities
(``migration.run``). The batch and its lines are rows of the test world, written as the
reconciliation job writes them (``Decimal`` values into the exact columns).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import file_object, migration_batch, migration_reconciliation_line
from erev_api.enums import FilePurpose, MigrationStatus
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert
from support.db import TestDatabase
from support.factories import ImportWorld, import_world
from support.reference import get
from support.rows import (
    file_object_values,
    migration_batch_values,
    migration_reconciliation_line_values,
)

MIGRATIONS: Final = "/api/v1/migrations"
# contract, obligation, measure, source, eRev, difference, the deviation that explains it
LINES: Final = (
    ("Contract 1", None, "TRANSACTION_PRICE", "1300", "1300", "0", None),
    ("Contract 1", "POB 1", "ALLOCATION", "433.333333333333333333", "433.3333333", None, None),
    # outside the tolerance: T-MIG-03 admits the line with its deviation reference
    ("Contract 2", None, "TRANSACTION_PRICE", "900", "900.5", "-0.5", "DEV-052"),
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> ImportWorld:
    return import_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def reconciled_batch(world: ImportWorld) -> UUID:
    """A RECONCILED batch with the three lines of ``LINES``; a difference left open is computed."""
    tenant_id = world.tenant_id
    source = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
    batch = migration_batch_values(
        tenant_id, source_file_id=UUID(str(source["id"])), status=MigrationStatus.RECONCILED.value
    )
    batch_id = UUID(str(batch["id"]))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        session.execute(insert(file_object).values(**source))
        session.execute(insert(migration_batch).values(**batch))
        for contract, obligation, measure, legacy, erev, difference, deviation in LINES:
            stated = Decimal(legacy) - Decimal(erev) if difference is None else Decimal(difference)
            session.execute(
                insert(migration_reconciliation_line).values(
                    **migration_reconciliation_line_values(
                        tenant_id,
                        migration_batch_id=batch_id,
                        contract_external_id=contract,
                        obligation_key=obligation,
                        measure=measure,
                        source_value=Decimal(legacy),
                        erev_value=Decimal(erev),
                        difference=stated,
                        is_within_tolerance=deviation is None,
                        deviation_ref=deviation,
                    )
                )
            )
    return batch_id


def test_the_lines_of_a_reconciled_migration_are_answered_as_plain_decimal_text(
    world: ImportWorld,
) -> None:
    """A line that reconciles states its difference as ``"0"``, a difference below one millionth
    in full, and every value without trailing zeros (04 API-C-06). Before: 500 — the stored zero
    left as ``0E-18`` and the small difference as ``3.3333333333E-8``."""
    batch_id = reconciled_batch(world)

    answered = get(world.app, f"{MIGRATIONS}/{batch_id}/reconciliation-lines", world.actor)

    assert answered.status_code == 200, answered.text
    stated: list[tuple[Any, ...]] = [
        (
            line["contract_external_id"],
            line["obligation_key"],
            line["measure"],
            line["source_value"],
            line["erev_value"],
            line["difference"],
            line["tolerance"],
            line["is_within_tolerance"],
            line["deviation_ref"],
        )
        for line in answered.json()["items"]
    ]
    assert stated == [
        ("Contract 1", None, "TRANSACTION_PRICE", "1300", "1300", "0", "0.0001", True, None),
        (
            "Contract 1",
            "POB 1",
            "ALLOCATION",
            "433.333333333333333333",
            "433.3333333",
            "0.000000033333333333",
            "0.0001",
            True,
            None,
        ),
        (
            "Contract 2",
            None,
            "TRANSACTION_PRICE",
            "900",
            "900.5",
            "-0.5",
            "0.0001",
            False,
            "DEV-052",
        ),
    ]
