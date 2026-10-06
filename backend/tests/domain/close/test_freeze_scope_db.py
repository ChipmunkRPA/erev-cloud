"""CLO-FREEZE-SCOPE-1: the frozen dataset of an entity, book and period is the same whoever decides
the lock (supervisor ruling R-94 (a) of 2026-09-30 — PRODUCT DEFECT; ENGINE_SPEC_B S15-R-18c rev
1.88; 04 T-CLS-05 rev 1.140; dev-guide DG-AK-60 rev 1.123). PostgreSQL-bound.

World: WLD-K-04 through the product's commands — ``SF-ORD-UK-2001`` is concluded by AVM-UK, its
obligation O1 is performed by AVM-US and O2 by AVM-UK. Each entity's April and May therefore hold
rows that carry the OTHER entity: AVM-US's lines belong to a contract AVM-UK concluded, and AVM-UK's
contract has an obligation whose lines AVM-US posts.

For each of the two entities, its April and its May, and each of the twelve E-64 kinds, two
deciders freeze the dataset through the production consumer (``close.snapshots.freeze_datasets``,
one kind per call): one whose roles cover every entity, and one whose roles name the lock's entity
alone — row-level security hides the other entity's rows from the second. Both must freeze the
same bytes (``file_sha256``), row count and control totals.

Fail-first (the producers read through the decider's session): the scoped decider is refused 422
``RPT05_KEY_COLUMN_UNRESOLVED`` on AVM-US's ``PRIOR_PERIOD_POB_REVENUE`` — the defect as ruled —
and, without any refusal, freezes other datasets SHORT of the rows row-level security hides; the
cases that fail are listed in the lane's report.

The freezes run once for the module (a world and ninety-six one-kind freezes); every unit of work
is rolled back, so nothing of them is stored.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal
from erev_api.config import get_settings
from erev_api.db.tables import contract
from erev_api.domain.close import dependencies, freeze, snapshots
from erev_api.enums import SnapshotKind
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from sqlalchemy import func, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.reference import periods
from support.worlds import AVM_UK, AVM_US, K04World, k04_saltmarsh

BOOK: Final = "ASC606"
KINDS: Final = tuple(kind.value for kind in SnapshotKind)
PERIOD_KEYS: Final = ("FY2026-P04", "FY2026-P05")
ENTITIES: Final = (AVM_US, AVM_UK)
EVERY_ENTITY: Final = "a decider of every entity"
LOCK_ENTITY_ONLY: Final = "a decider scoped to the lock's entity"
# O1 of SF-ORD-UK-2001 is performed by AVM-US: its April revenue in AVM-US's books (the figure the
# disaggregation of AVM-US states; allocation 58,285.71 over 365 days, 30 days of April).
O1_APRIL: Final = {"GBP": "4790.61"}


@dataclasses.dataclass(frozen=True)
class Frozen:
    """What one decider froze for one kind: the T-CLS-05 facts of the dataset."""

    file_sha256: str
    row_count: int
    control_totals: str  # canonical JSON


@dataclasses.dataclass(frozen=True)
class Refused:
    """A freeze that did not happen, by name."""

    problem: str
    rules: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Freezes:
    """Every one-kind freeze of the module, by (entity code, period key, kind, decider), and how
    many rows of the contract each decider reads directly."""

    results: Mapping[tuple[str, str, str, str], Frozen | Refused]
    contract_rows: Mapping[tuple[str, str], int]


def _scoped(wide: Principal, entity_id: UUID) -> Principal:
    """``wide`` with every role narrowed to one entity — the principal an entity-scoped grant
    gives (such a grant cannot be created through the product yet: supervisor ruling R-63 (e))."""
    return dataclasses.replace(
        wide,
        entity_scope=(entity_id,),
        permission_scopes={name: frozenset({entity_id}) for name in wide.permission_scopes},
    )


def _freeze_one(
    world: K04World,
    principal: Principal,
    *,
    entity_id: UUID,
    period_id: UUID,
    kind: str,
    cutoff: Any,
) -> Frozen | Refused:
    engine = dataclasses.replace(dependencies.snapshot_engine(), kinds=(kind,))
    refusal = dependencies.snapshot_registry().refusal
    with world.report.place.uow(principal) as uow:
        try:
            (dataset,) = snapshots.freeze_datasets(
                uow, entity_id, BOOK, period_id, cutoff, frozen_at=cutoff, engine=engine
            )
        except Problem as problem:
            return Refused(problem.slug, tuple(str(error.rule_id) for error in problem.errors))
        except refusal as refused:
            return Refused(type(refused).__name__, (str(getattr(refused, "reason", refused)),))
        finally:
            uow.session.rollback()  # a witness stores nothing
    return Frozen(
        file_sha256=dataset.file_sha256,
        row_count=dataset.row_count,
        control_totals=json.dumps(dataset.control_totals, sort_keys=True, default=str),
    )


@pytest.fixture(scope="module")
def freezes(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> Freezes:
    clock = frozen_clock()
    settings = get_settings().model_copy(
        update={"file_root": tmp_path_factory.mktemp("freeze-scope") / "files"}
    )
    app = create_app(settings, clock=clock)
    world = k04_saltmarsh(app, keyring, clock, LocalFileStore(settings.file_root))
    place = world.report.place
    wide = place.principal
    entity_ids = {AVM_US: world.us_entity_id, AVM_UK: world.uk_entity_id}
    with place.uow() as uow:  # ONE cutoff for every freeze, after everything the world recorded
        cutoff = freeze.freeze_cutoff(uow.session, uow.now)
    results: dict[tuple[str, str, str, str], Frozen | Refused] = {}
    contract_rows: dict[tuple[str, str], int] = {}
    for code, entity_id in entity_ids.items():
        deciders = {EVERY_ENTITY: wide, LOCK_ENTITY_ONLY: _scoped(wide, entity_id)}
        period_ids = {
            item["period"]["period_key"]: UUID(str(item["period"]["id"]))
            for item in periods(app, world.report.maya, entity=code)
            if item["period"]["period_key"] in PERIOD_KEYS
        }
        for label, principal in deciders.items():
            with place.uow(principal) as uow:
                contract_rows[(code, label)] = int(
                    uow.session.execute(
                        select(func.count())
                        .select_from(contract)
                        .where(contract.c.id == world.contract_id)
                    ).scalar_one()
                )
            for period_key in PERIOD_KEYS:
                for kind in KINDS:
                    results[(code, period_key, kind, label)] = _freeze_one(
                        world,
                        principal,
                        entity_id=entity_id,
                        period_id=period_ids[period_key],
                        kind=kind,
                        cutoff=cutoff,
                    )
    return Freezes(results=results, contract_rows=contract_rows)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("period_key", PERIOD_KEYS)
@pytest.mark.parametrize("entity_code", ENTITIES)
def test_r94_a_dataset_is_frozen_alike_whoever_decides(
    freezes: Freezes, entity_code: str, period_key: str, kind: str
) -> None:
    """R-94 (a): the decider of every entity freezes the kind, and the decider scoped to the
    lock's entity freezes the SAME dataset — hash, row count, control totals."""
    by_every_entity = freezes.results[(entity_code, period_key, kind, EVERY_ENTITY)]
    by_lock_entity = freezes.results[(entity_code, period_key, kind, LOCK_ENTITY_ONLY)]
    assert isinstance(by_every_entity, Frozen), by_every_entity
    assert by_lock_entity == by_every_entity, {
        LOCK_ENTITY_ONLY: by_lock_entity,
        EVERY_ENTITY: by_every_entity,
    }


def test_r94_the_scope_is_widened_for_the_freeze_alone(freezes: Freezes) -> None:
    """The positive control of the witness above: the scoped deciders ARE scoped — the contract
    row itself is read by the decider of every entity and by the decider scoped to AVM-UK, which
    concluded it, and hidden from the decider scoped to AVM-US — while the dataset AVM-US's
    decider freezes holds what derives from that contract: O1's April revenue in AVM-US's books.
    Row-level security is not relaxed for anything but the producers' reads."""
    assert freezes.contract_rows == {
        (AVM_US, EVERY_ENTITY): 1,
        (AVM_US, LOCK_ENTITY_ONLY): 0,
        (AVM_UK, EVERY_ENTITY): 1,
        (AVM_UK, LOCK_ENTITY_ONLY): 1,
    }
    disaggregation = freezes.results[(AVM_US, "FY2026-P04", "DISAGGREGATION", LOCK_ENTITY_ONLY)]
    assert isinstance(disaggregation, Frozen) and disaggregation.row_count == 1
    assert json.loads(disaggregation.control_totals)["revenue_total"] == O1_APRIL
