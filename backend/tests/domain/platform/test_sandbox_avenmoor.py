"""05 SBX-05 on a whole tenant (rev 1.50; supervisor rulings R-9 (iii) and R-43 (a)): the Avenmoor
key contracts of PRD §2.7 — five entities, four currencies, published FX rate sets, twelve
combination groups built through the persona commands — copied into a sandbox and verified pair
by pair.

Every group of this tenant was computed SEVERAL times in the source (booking, activation, each
append), which is what a real tenant looks like and what no output hash can verify: the engine is
incremental and the sandbox recomputes once. The witness shows both halves of the rule on the
engine's actual bundles, observed by a spy:

* what a load changes about a computation — the arrival stamps and the trigger — changes nothing
  but ``input_sha256``, for every group, the GBP order with same-date stage 12 layers included;
* what the source's history changes — the activity of the last computation, the posting deltas,
  the trace — leaves every member of the MONETARY STATE equal, so every pair is VERIFIED.

Three substitutions, named. (1) The seed runs the reference, SSP, policy and key-contract builders
only: the background contracts and their imports are volume, not substance. (2) K-04
``SF-ORD-UK-2001`` is activated — the seed keeps it a draft for the rc gate clause of D-88
L7-6-Q-1, not for an engine refusal — so that the tenant holds a multi-currency group with
same-date stage 12 layers. (3) The snapshot's retention gate reads a confirmed policy from a stub:
the demo publishes its PLATFORM policy version effective at the NEXT period start, so a
confirmation written into this world would hold or not depending on the wall clock; the gate is
not the subject (its witnesses are ``test_snapshots.py`` and
``tests/pg/test_snapshot_retention_evidence.py``).
"""

from __future__ import annotations

import dataclasses
import json
import secrets
from collections import Counter
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import erev_engine
import pyotp
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    audit_event,
    contract,
    contract_computation,
    contract_version,
    tenant,
    tenant_snapshot,
)
from erev_api.domain.demo import builders, personas, seed, tenants
from erev_api.domain.demo.avenmoor import contracts as key_contracts
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.enums import JobKind
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_engine.bundle import InputBundle, OutputBundle
from sqlalchemy import insert, select
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.rows import tenant_snapshot_values
from support.snapshots import cutoff_after, load_outcome, run_dispatched_snapshot

# Seeding the key contracts through the persona commands takes about a minute (DG-TST-08).
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-sandbox-avenmoor"
AVENMOOR = tenants.CATALOGUE[1]  # WLD-T-01
K04 = "SF-ORD-UK-2001"  # Saltmarsh: a GBP order with a line performed by AVM-US (USD)
# A draft of AVM-JP, the entity whose calendar starts before its books' first period. Until
# ENG-CAL-PREBOOK-1 (main 1a0f5d3c; supervisor rulings R-58 (a) to (c)) the engine refused it and
# it had no version on either side; it computes now and is verified like every other group.
K10 = "JP-LIC-0001"
KEY_BUILDERS = 4  # reference, SSP, policies, key contracts


@pytest.fixture
def job() -> Iterator[ModuleType]:
    """The handler module, registered for the test, with the engine release stamped as the worker's
    startup stamps it (05 REL-03, REL-05) — the shape of ``test_sandbox_replay.py``."""
    from erev_api.domain.platform import snapshot_job

    stamp_test_release()
    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS  # the worker registers it (DG-ARC-08)
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    yield snapshot_job
    if not present:
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _seeded(
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[UUID, UUID]:
    """WLD-T-01 under a fresh code with its key contracts (substitutions 1 and 2 of the module
    docstring); returns the tenant id and Marcus's user id (Controller: the sandbox requester)."""
    monkeypatch.setattr(
        key_contracts,
        "KEY_CONTRACTS",
        tuple(
            replace(spec, activates=True) if spec.external_id == K04 else spec
            for spec in key_contracts.KEY_CONTRACTS
        ),
    )
    monkeypatch.setattr(
        builders,
        "BUILDERS",
        {**builders.BUILDERS, AVENMOOR.wld_id: builders.BUILDERS[AVENMOOR.wld_id][:KEY_BUILDERS]},
    )
    suffix = secrets.token_hex(3)
    cast = tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )
    code = f"avm-{secrets.token_hex(4)}"
    monkeypatch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=code)))
    result = seed.seed_demo(
        [code],
        clock,
        keyring=keyring,
        files=files,
        secrets=seed.DemoSecrets(
            password=f"Seed-{secrets.token_urlsafe(12)}", totp_secret=pyotp.random_base32()
        ),
        credentials_path=root / "run" / seed.CREDENTIALS_FILE,
        request_id=REQUEST_ID,
        personas=cast,
    )
    assert result.outcomes == ((code, "seeded"),)
    with platform_session("tenant_directory", actor_user_id=None, request_id=REQUEST_ID) as db:
        tenant_id = db.execute(select(tenant.c.id).where(tenant.c.code == code)).scalar_one()
    marcus = next(persona.email for persona in cast if persona.key == "marcus")
    with identity_session(request_id=REQUEST_ID) as db:
        user_id = db.execute(select(app_user.c.id).where(app_user.c.email == marcus)).scalar_one()
    return UUID(str(tenant_id)), UUID(str(user_id))


def _confirmed_retention(monkeypatch: pytest.MonkeyPatch, job: ModuleType) -> None:
    """Substitution 3 of the module docstring: the gate's resolution, confirmed."""
    confirmed = job.RetentionResolution(
        sd.RetentionPolicy(families=dict(sd.RETENTION_FAMILIES), source="tests (stubbed gate)")
    )
    monkeypatch.setattr(job, "retention_policy_for", lambda session, known_at: confirmed)


def _load_report(sandbox_id: UUID, runtime: JobRuntime, keyring: KeyRing) -> dict[str, Any]:
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        detail = session.execute(
            select(audit_event.c.detail).where(audit_event.c.action == sb.ACTION_LOADED)
        ).scalar_one()
        _, stream = open_file(
            session, UUID(str(detail["load_report_file_id"])), files=runtime.files, keyring=keyring
        )  # type: ignore[arg-type]
        return dict(json.loads(stream.read()))


def _with_source_stamps(bundle: InputBundle, source: InputBundle) -> InputBundle:
    """The sandbox's bundle carrying the SOURCE's arrival stamps and trigger — everything a load
    changes about a computation, undone; the facts, their order and the one-shot history stay."""
    stamps = {event.event_key: event for event in source.events}
    return dataclasses.replace(
        bundle,
        trigger=source.trigger,
        events=tuple(
            dataclasses.replace(
                event,
                record_seq=stamps[event.event_key].record_seq,
                recorded_at=stamps[event.event_key].recorded_at,
            )
            for event in bundle.events
        ),
    )


def test_the_avenmoor_key_contracts_verify_pair_by_pair(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load of the Avenmoor key contracts SUCCEEDS and verifies every (group, book) pair the
    source holds a version for: ``derived_mismatches = 0``, none of them by hash — no pair is a
    first computation. Every one of the twelve groups holds a version and is recomputed; K-10's
    draft among them, whose bundle leaves out the periods before its books' first period
    (ENG-CAL-PREBOOK-1, 05 RCP-15 rev 1.62) in the source and in the sandbox alike: the sandbox's
    one recompute equals the source's latest version in every member of the monetary state.

    On the engine's own bundles: (a) arrival — the sandbox's output equals, but for
    ``input_sha256``, a one-shot computation of the same bundle under the source's stamps, for
    every recomputed group; (b) history — the source computed each of those groups more than
    once, and its latest output does NOT equal the sandbox's under the substituted hash, so the
    monetary state is what verified them; (c) K-04 — the GBP group books in USD and GBP and its
    recompute writes stage 12 layer movements, several on one date for one entity and kind."""
    calls: list[tuple[InputBundle, OutputBundle]] = []
    real = erev_engine.compute

    def spy(bundle: InputBundle) -> OutputBundle:
        output = real(bundle)
        calls.append((bundle, output))
        return output

    monkeypatch.setattr(erev_engine, "compute", spy)  # observes; the product runs the real engine
    files = LocalFileStore(app_settings.file_root)
    tenant_id, marcus = _seeded(keyring, clock, files, tmp_path, monkeypatch)
    seeded = len(calls)
    with tenant_session(_context(tenant_id), read_only=True) as session:
        contracts = {
            str(row["external_id"]): dict(row)
            for row in session.execute(
                select(contract.c.external_id, contract.c.status, contract.c.combination_group_id)
            ).mappings()
        }
        pairs = {
            (UUID(str(group)), str(book))
            for group, book in session.execute(
                select(contract_version.c.combination_group_id, contract_version.c.book_code)
            )
        }
    assert len(contracts) == len(key_contracts.KEY_CONTRACTS) == 12
    assert contracts[K04]["status"] == "ACTIVE"
    groups = {UUID(str(row["combination_group_id"])) for row in contracts.values()}
    assert len(groups) == 12  # no combination among the key contracts
    unversioned = groups - {group for group, _ in pairs}
    assert unversioned == set()  # K-10 included: a draft with a provisional version since B-1
    k10_group = UUID(str(contracts[K10]["combination_group_id"]))
    assert contracts[K10]["status"] == "DRAFT" and (k10_group, "ASC606") in pairs

    _confirmed_retention(monkeypatch, job)
    known_at = cutoff_after(tenant_id, clock)
    with tenant_session(_context(tenant_id)) as session:
        row = tenant_snapshot_values(tenant_id, known_at=known_at, purpose="SANDBOX_COPY")
        session.execute(insert(tenant_snapshot).values(**row))
    sandbox_id = UUID(int=int(row["id"]) ^ 1)
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    params = {
        "tenant_snapshot_id": str(row["id"]),
        "known_at": known_at.isoformat(),
        "purpose": "SANDBOX_COPY",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name="Avenmoor copy", requested_by=marcus, restore=False
        ),
    }
    outcome = run_dispatched_snapshot(tenant_id, params, runtime=runtime, now=known_at)
    assert outcome["state"] == "SUCCEEDED", outcome["problem"]
    counts = outcome["result"]["counts"]
    assert (counts["groups_recomputed"], counts["groups_not_recomputed"]) == (12, 0)
    assert counts["derived_mismatches"] == 0 and counts["blocked_periods"] == 0, load_outcome(
        counts
    )
    report = _load_report(sandbox_id, runtime, keyring)
    assert report["compared"] == len(pairs) and report["mismatches"] == []
    assert report["first_computations"] == 0  # every pair verified by its monetary state alone
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        refused = {
            UUID(str(group))
            for group in session.scalars(
                select(contract_computation.c.combination_group_id).where(
                    contract_computation.c.status != "SUCCEEDED"
                )
            )
        }
    assert refused == unversioned  # none, as in the source

    # the engine's own bundles: the source's computations, then the sandbox's recomputes
    latest: dict[str, tuple[InputBundle, OutputBundle]] = {}
    computed_in_source: Counter[str] = Counter()
    for bundle, output in calls[:seeded]:
        latest[bundle.group.group_key] = (bundle, output)
        computed_in_source[bundle.group.group_key] += 1
    recomputes = [(b, o) for b, o in calls[seeded:] if b.trigger == "MIGRATION"]
    assert len(recomputes) == 12
    # K-10 is one of them, and the loop below holds it to the same two comparisons as the rest
    assert sum(K10 in bundle.group.member_contract_keys for bundle, _ in recomputes) == 1
    for bundle, output in recomputes:
        key = bundle.group.group_key
        source_bundle, source_output = latest[key]
        assert [e.event_key for e in bundle.events] == [e.event_key for e in source_bundle.events]
        # (a) arrival: nothing but the input hash
        one_shot = real(_with_source_stamps(bundle, source_bundle))
        assert one_shot.input_sha256 != output.input_sha256, key
        assert dataclasses.replace(output, input_sha256=one_shot.input_sha256) == one_shot, key
        # (b) history: computed more than once, and no hash could say so
        assert computed_in_source[key] >= 2, key
        substituted = dataclasses.replace(output, input_sha256=source_output.input_sha256)
        assert substituted.sha256() != source_output.sha256(), key
    # (c) K-04: two functional currencies, stage 12 layers, several on one date
    ((saltmarsh, layered),) = [(b, o) for b, o in recomputes if K04 in b.group.member_contract_keys]
    assert saltmarsh.group.transaction_currency == "GBP"
    assert {entity.functional_currency for entity in saltmarsh.entities} == {"GBP", "USD"}
    movements = [m for book in layered.books for m in book.fx_layer_movements]
    same_day = Counter(
        (
            m.columns["book_code"],
            m.columns["entity"],
            m.columns["movement_kind"],
            m.columns["effective_date"],
        )
        for m in movements
    )
    assert movements and max(same_day.values()) >= 2
