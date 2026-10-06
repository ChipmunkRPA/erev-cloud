"""``WorkspaceAdapter`` on the mock invoker (record §14.1 "DbPlatform, next slice"; DG-AK-41).

No database and no live call: a ``RecordingInvoker`` keeps every ``Call`` the adapter derives from
the plan steps of POS-CHK-012, so the mapping (handler, persona, keyword arguments from the key,
stream versions per contract) is verified; the server clock is a fake; reads raise
``NotProvisioned`` (following slice). The run against ``erev_rv_l17_test`` waits on the Ray-side
databases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
import yaml
from erev_api.auth.principal import Principal
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, H, load_platform_key, plan
from support.answer_keys.platform_runner import (
    EXECUTED,
    NOT_RUN,
    DbPlatform,
    NotProvisioned,
    platform_outcome,
    run_platform,
)
from support.answer_keys.workspace_adapter import (
    PENDING_APPROVAL,
    Call,
    RecordingInvoker,
    WorkspaceAdapter,
    _principal_for,
    booking_body,
    problem_code,
    real_invoker,
)

POS_012 = PLATFORM_KEY_IDS[0]


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2025, 12, 31, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _run(loaded, invoker: RecordingInvoker):  # noqa: ANN001, ANN202
    # The constant fingerprint is an explicit, named mock fixture (WSA-2), never a default.
    adapter = WorkspaceAdapter(
        loaded, invoker=invoker, clock=_Clock(), fingerprint=lambda: "mock-fixture"
    )
    return adapter, run_platform(loaded, DbPlatform(loaded, adapter))


def test_every_step_maps_to_one_call_with_arguments_from_the_key() -> None:
    loaded = load_platform_key(POS_012)
    invoker = RecordingInvoker()
    adapter, result = _run(loaded, invoker)
    steps = [step for step in plan(loaded).steps if step.phase not in ("CHECKPOINT", "RUNNER")]
    assert [call.step for call in invoker.calls] == steps
    assert [call.handler for call in invoker.calls] == [step.handler for step in steps]
    assert all(call.actor == call.step.actor for call in invoker.calls)
    by_handler: dict[str, list[Call]] = {}
    for call in invoker.calls:
        by_handler.setdefault(call.handler, []).append(call)
    world = loaded.key.world
    (provision,) = by_handler[H["provision"]]
    assert provision.kwargs["reporting_currency"] == world.tenant.reporting_currency == "USD"
    assert provision.kwargs["database"] == "erev_test" and provision.kwargs["is_demo"] is False
    (entity,) = by_handler[H["entity"]]
    assert (
        entity.kwargs["entity_code"],
        entity.kwargs["functional_currency"],
        entity.kwargs["time_zone"],
    ) == (
        "US01",
        "USD",
        "America/New_York",
    )
    assert {call.kwargs["code"] for call in by_handler[H["gl_account"]]} == {
        account.code for account in world.gl_accounts
    }
    assert {call.kwargs["code"] for call in by_handler[H["customer"]]} == {
        c.code for c in world.customers
    }
    assert {call.kwargs["code"] for call in by_handler[H["template"]]} == {
        t.code for t in world.pob_templates
    }
    assert {call.kwargs["code"] for call in by_handler[H["product"]]} == {
        p.code for p in world.products
    }
    (policy,) = by_handler[H["policy"]]
    assert policy.kwargs == {
        "scope": "TENANT",
        "scope_code": "tenant",
        # 04 §16.5 rule 3: the first period start at the entity's local midnight (New York) — the
        # plan dates every policy version there (batch #6 keys-platform; record §4.25).
        "effective_from": "2026-01-01T05:00:00Z",
        "values": {"billing.posting": "ERP"},
    }
    bookings = by_handler[H["book"]]
    assert [call.kwargs["body"]["external_id"] for call in bookings] == [
        c.external_id for c in loaded.key.contracts
    ]
    assert all(call.kwargs["body"]["contracting_entity_code"] == "US01" for call in bookings)
    first_body = bookings[0].kwargs["body"]
    assert first_body["lines"][0]["total_price"]["currency"] == "USD"
    assert {line["obligation_key"] for line in first_body["lines"]} == {
        line.obligation_key for line in loaded.key.contracts[0].lines
    }
    # Stream versions: booking = 1; before the activation the runner's Step 1 assessment appends
    # one event per enabled book of the contracting entity (DG-AK-41 layer 4: no key states Step
    # 1 itself); the approved activation appends one; every recorded event one more.
    appends = [call for call in invoker.calls if call.handler == H["record_events"]]
    assessments = [call for call in appends if call.kwargs.get("step1")]
    events = [call for call in appends if not call.kwargs.get("step1")]
    assert [
        (call.kwargs["contract"], call.kwargs["expected_stream_version"], call.kwargs["events"])
        for call in assessments
    ] == [
        (
            contract.external_id,
            1,
            [
                {
                    "event_type": "COLLECTIBILITY_ASSESSED",
                    "effective_date": contract.inception_date,
                    "payload": {"book": "ASC606", "is_probable": True},
                }
            ],
        )
        for contract in loaded.key.contracts
    ]
    assert all(call.step.phase == "CONTRACTS" for call in assessments)
    assert all(call.step.phase == "TIMELINE" for call in events)
    per_contract: dict[str, list[int]] = {}
    for call in events:
        per_contract.setdefault(call.kwargs["contract"], []).append(
            call.kwargs["expected_stream_version"]
        )
    for contract, versions in per_contract.items():
        assert versions == list(range(3, 3 + len(versions))), (
            contract
        )  # after booking (1) + the assessment (2) + the approved activation (3)
        assert all(len(call.kwargs["events"]) == 1 for call in events)
    computes = [call for call in invoker.calls if call.handler == H["compute"]]
    assert len(computes) == len(events) and all(
        call.kwargs["group"].startswith("CG-") for call in computes
    )
    decisions = [call for call in invoker.calls if call.handler == H["decide"]]
    assert decisions and all(
        call.kwargs["approval_request_id"] == PENDING_APPROVAL for call in decisions
    )
    # Stamps: one per committed timeline item from the (fake) server clock, strictly increasing.
    seqs = [item.seq for item in loaded.key.timeline]
    assert sorted(result.known_at) == seqs
    stamps = [result.known_at[seq] for seq in seqs]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
    assert all(item.status == EXECUTED for item in result.executed)
    # Without persisted reads (record §19, READ-1) every block is not run, the key not_run.
    assert all(block.status == NOT_RUN for cp in result.checkpoints for block in cp.blocks)
    status, message = platform_outcome(loaded, result)
    assert status == NOT_RUN and message.startswith("not run")
    assert all(
        "no persisted reads" in (block.reason or "") and "READ-1" in (block.reason or "")
        for cp in result.checkpoints
        for block in cp.blocks
    )
    assert adapter.stream == {
        c.external_id: 3 + len(per_contract.get(c.external_id, [])) for c in loaded.key.contracts
    }


def _variant(tmp_path: Path, item: dict[str, object]) -> object:
    source = yaml.safe_load((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text())
    source["timeline"].append(item)
    target = tmp_path / "pos" / f"{POS_012}.yaml"
    target.parent.mkdir()
    target.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True))
    return load(target)


def test_refusal_of_a_built_command_reads_the_problem_code(tmp_path: Path) -> None:
    """An event with ``expect_problem`` runs through ``record_events``: the refusing invoker's
    ``Problem`` code and the unchanged fingerprint verify it (executed, no stamp); an accepting
    invoker fails the key (PLAT-1)."""
    source = yaml.safe_load((ANSWER_KEY_ROOT / "pos" / f"{POS_012}.yaml").read_text())
    template = next(item for item in source["timeline"] if item["event_type"] == "BILLING_RECORDED")
    refused_event = {
        **template,
        "seq": 12,
        "expect_problem": {"code": "validation-failed", "status": 422},
    }
    loaded = _variant(tmp_path, refused_event)
    refusing = RecordingInvoker(raises={12: Problem("validation-failed")})
    adapter, result = _run(loaded, refusing)
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == EXECUTED and 12 not in result.known_at
    assert refusing.calls[-1].handler == H["record_events"]
    assert problem_code(Problem("validation-failed")) == "validation-failed"
    assert problem_code(ValueError("x")) == "ValueError"
    accepting = RecordingInvoker()
    _, result = _run(loaded, accepting)
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == "failed" and "got no refusal" in (refusal.reason or "")
    assert platform_outcome(loaded, result)[0] == "failed"


def test_refusal_of_an_unbuilt_command_is_not_run(tmp_path: Path) -> None:
    """A ``lock_period`` with ``expect_problem`` has no handler — the plan builds no lock
    (``platform_plan.LOCK_COMMAND_GAP``): the database platform cannot enforce the refusal, so
    the step is not run, never executed (PLAT-1)."""
    loaded = _variant(
        tmp_path,
        {
            "seq": 12,
            "kind": "command",
            "command": {
                "name": "lock_period",
                "params": {"entity": "US01", "book": "ASC606", "period_key": "FY2026-P01"},
            },
            "expect_problem": {"code": "close-gates-failed", "status": 409},
        },
    )
    _, result = _run(loaded, RecordingInvoker())
    (refusal,) = [item for item in result.executed if item.step.seq == 12]
    assert refusal.status == NOT_RUN and "close-gates-failed" in (refusal.reason or "")
    assert platform_outcome(loaded, result)[0] == NOT_RUN


class _NoDatabase:
    """A workspace stand-in whose unit of work is not provisioned (no live call is possible)."""

    clock = None
    keyring = None

    def uow(self, principal=None):  # noqa: ANN001, ANN201
        raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")


class _Recording(_NoDatabase):
    """A workspace stand-in that records which principal each unit of work was asked for."""

    def __init__(self) -> None:
        self.principals: list[object] = []

    def uow(self, principal=None):  # noqa: ANN001, ANN201
        self.principals.append(principal)
        raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")


def _principal(
    name: str,
    roles: tuple[str, ...],
    tenant: UUID,
    permissions: frozenset[str] | None = None,
) -> Principal:
    """A fake persona: its permissions are what ``DEFAULT_ROLES`` grants its roles (as the API
    resolves them) unless a test hands an explicit set to exercise ACT-2."""
    from erev_api.auth.permissions import DEFAULT_ROLES

    granted = frozenset[str]().union(*(DEFAULT_ROLES.get(code, frozenset()) for code in roles))
    return Principal(
        kind=PrincipalKind.USER,
        id=uuid5(NAMESPACE_URL, f"erev://answer-keys/user/{name}"),
        tenant_id=tenant,
        membership_id=uuid5(NAMESPACE_URL, f"erev://answer-keys/membership/{name}"),
        display_name=name,
        roles=tuple(sorted(roles)),
        permissions=granted if permissions is None else permissions,
        permission_scopes={},
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


VERIFIED_AT = datetime(2026, 1, 1, 9, tzinfo=UTC)  # the workspace clock a witness hands in
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/tenant")
PERSONAS = {
    "ak-preparer": _principal("Ak Preparer", ("revenue_accountant",), TENANT),
    "ak-approver": _principal("Ak Approver", ("controller",), TENANT),  # D-98 107: no approver role
    "operator": _principal("Operator", ("tenant_admin",), TENANT),
    "ak-ssp-analyst": _principal("Ak Ssp Analyst", ("ssp_analyst",), TENANT),  # D-98 107a
    "ak-ssp-approver": _principal("Ak Ssp Approver", ("ssp_approver",), TENANT),
}


def test_without_an_invoker_or_clock_the_adapter_is_not_provisioned() -> None:
    loaded = load_platform_key(POS_012)
    adapter = WorkspaceAdapter(loaded)
    step = next(step for step in plan(loaded).steps if step.handler == H["provision"])
    with pytest.raises(NotProvisioned, match="provision_tenant"):
        adapter.run(step)
    with pytest.raises(NotProvisioned, match="clock_timestamp"):
        adapter.clock_timestamp()
    # The real invoker converts the call first (request models, ids), then needs the unit of work.
    from support.answer_keys.request_models import MockResolver

    booking = next(step for step in plan(loaded).steps if step.handler == H["book"])
    call = WorkspaceAdapter(loaded).plan_call(booking)
    assert call is not None
    with pytest.raises(NotProvisioned, match="unit of work"):
        real_invoker(_NoDatabase(), loaded.key, [], PERSONAS)(call)  # no ids needed for a booking
    assert MockResolver(POS_012).customer_id("X")  # the mock stays a test fixture only
    body = booking_body(loaded.key.contracts[0])
    assert body["customer_code"] == loaded.key.contracts[0].customer
    assert all("total_price" in line for line in body["lines"])


def test_an_adapter_over_nothing_waits_for_the_databases_and_says_so() -> None:
    """Item AK-NOT-RUN-REASON-1: an adapter without its invoker, its clock, its fingerprint
    collector, its reads or its job runner has no database behind it, and its refusals are the
    ones that say "databases not provisioned". A refusal of a rule of the adapter's own (ACT-1)
    opens with that rule's reason and never carries those words."""
    from types import SimpleNamespace
    from typing import cast

    from support.answer_keys.platform_runner import NOT_PROVISIONED
    from support.answer_keys.workspace_adapter import _server_clock
    from support.answer_keys.workspace_reads import PersistedReads

    loaded = load_platform_key(POS_012)
    bare = WorkspaceAdapter(loaded)
    step = next(step for step in plan(loaded).steps if step.handler == H["currencies"])
    dlt = load_platform_key(next(key for key in PLATFORM_KEY_IDS if key.startswith("DLT-")))
    with_journals = next(checkpoint for checkpoint in dlt.key.checkpoints if checkpoint.journals)
    assert with_journals.journals is not None
    ex21 = load_platform_key(next(key for key in PLATFORM_KEY_IDS if "EX21" in key))
    (with_reports,) = ex21.key.checkpoints
    assert with_reports.reports is not None
    reads_only = WorkspaceAdapter(ex21, reads=cast(PersistedReads, object()))
    attempts = {
        "no invoker": lambda: bare.run(step),
        "no clock": bare.clock_timestamp,
        "no fingerprint collector": lambda: bare.refusal(step, "validation-failed"),
        "no persisted reads": lambda: bare.checkpoint_run(loaded.key.checkpoints[0]),
        # a report run is the job collaborator's; a journals block's run is a step of the plan
        # since item AK-JOURNAL-RUN-PLAN-1 and asks for no job runner (below)
        "no job runner": lambda: reads_only.report_rows(with_reports, with_reports.reports[0]),
        "no server clock": lambda: _server_clock(SimpleNamespace(scalar=lambda statement: None)),
    }
    for name, attempt in attempts.items():
        with pytest.raises(NotProvisioned) as waits:
            attempt()
        assert waits.value.unprovisioned is True, name
        assert str(waits.value).startswith(f"{NOT_PROVISIONED}: "), name
    call = bare.plan_call(step)
    assert call is not None
    with pytest.raises(NotProvisioned) as own:
        _principal_for(call, None)
    assert own.value.unprovisioned is False
    assert str(own.value).startswith("not run — WORLD tenant currencies: no principal mapped ")
    # A journals block whose step of the plan did not run: a reason of its own, too. The read
    # makes no run — it answers from what the step kept in the ledger.
    with pytest.raises(NotProvisioned) as unmade:
        WorkspaceAdapter(dlt).journal_run(with_journals, with_journals.journals[0])
    assert unmade.value.unprovisioned is False
    assert str(unmade.value) == (
        "not run — journals ME1 FY2023-P01 GROSS: the step that makes the block's journal run "
        f"after seq 13 did not run ({H['journal_create']})"
    )


def test_act_1_persona_principals_are_proven_never_defaulted() -> None:
    """Rule ACT-1: a missing mapping and a wrong principal are refused by name before any unit of
    work; the right mapping reaches the unit of work under that principal; the system actor is the
    tenant's SYSTEM principal; Workspace.uow(None) is never entered."""

    class _Seen:
        clock = None
        keyring = None

        def __init__(self) -> None:
            self.principals: list[object] = []

        def uow(self, principal=None):  # noqa: ANN001, ANN201
            self.principals.append(principal)
            raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")

    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    adapter = WorkspaceAdapter(loaded)
    # D-98 candidate 107 (Q-14): tenant settings are the operator's (DG-AK-41 rev 1.38).
    currencies = adapter.plan_call(next(s for s in steps if s.handler == H["currencies"]))
    assert currencies is not None and currencies.actor == "operator"
    decision = adapter.plan_call(next(s for s in steps if s.actor == "ak-approver"))
    assert decision is not None and decision.actor == "ak-approver"
    place = _Seen()
    with pytest.raises(NotProvisioned, match="no principal mapped for actor 'operator'"):
        real_invoker(place, loaded.key, [], {})(currencies)
    with pytest.raises(NotProvisioned, match="no principal mapped for actor 'ak-approver'"):
        real_invoker(place, loaded.key, [], None)(decision)
    wrong = {**PERSONAS, "ak-approver": PERSONAS["ak-preparer"]}  # the preparer as approver
    with pytest.raises(NotProvisioned, match=r"lacks roles \['controller'\]"):
        real_invoker(place, loaded.key, [], wrong)(decision)
    # The operator is checked like every other actor (Q-14 closes the ROLE_CODES gap).
    demoted = {**PERSONAS, "operator": _principal("Operator", ("viewer",), TENANT)}
    with pytest.raises(NotProvisioned, match=r"'operator' lacks roles \['tenant_admin'\]"):
        real_invoker(place, loaded.key, [], demoted)(currencies)
    other_tenant = {
        **PERSONAS,
        "operator": _principal("Elsewhere", ("tenant_admin",), uuid5(TENANT, "x")),
    }
    with pytest.raises(NotProvisioned, match="span 2 tenants"):
        real_invoker(place, loaded.key, [], other_tenant)(currencies)
    assert place.principals == []  # every refusal came before a unit of work
    with pytest.raises(NotProvisioned, match="unit of work"):
        real_invoker(place, loaded.key, [], PERSONAS)(currencies)
    assert place.principals == [PERSONAS["operator"]]
    system_call = next(  # the compute job: the one step the plan runs as SYSTEM
        adapter.plan_call(s) for s in steps if s.handler == H["compute"] and s.actor == "system"
    )
    assert system_call is not None
    system = _principal_for(system_call, PERSONAS)
    assert system.kind is PrincipalKind.SYSTEM and system.tenant_id == TENANT
    with pytest.raises(NotProvisioned, match="not of kind SYSTEM"):
        _principal_for(system_call, {**PERSONAS, "system": PERSONAS["ak-approver"]})
    with pytest.raises(NotProvisioned, match="no mapped tenant"):
        _principal_for(system_call, {})
    assert _principal_for(system_call, {"system": system}) is system


def test_act_1_the_db_stand_in_personas_cover_the_ledger_resolver_steps() -> None:
    """PLAT-ACT-1 (record §31). The ledger-resolver DB test runs POS-CHK-012's world steps through
    the real invoker but handed ``for_database`` no principal map, so ACT-1 refused its first step
    by name (batch ci on main 065e7f65: "WORLD tenant currencies: no principal mapped for actor
    'ak-approver' …"). The stand-in map of ``db_personas`` covers every actor those steps name, in
    one tenant, from T-PLT-09 role codes only (a provisioned tenant can assign no other). D-98
    candidate 107 (record §32): ``ak-approver`` holds the controller role only (Q-13 — no
    ``approver`` platform role exists) and tenant settings are the operator's (Q-14 — ``PUT
    /tenant-currencies`` needs ``settings.manage``, which only ``tenant_admin`` holds), so the map
    carries an ``operator`` stand-in that ACT-1 checks like every other actor."""
    from types import SimpleNamespace

    from erev_api.auth.permissions import DEFAULT_ROLES
    from support.answer_keys.db_personas import (
        LEDGER_RESOLVER_HANDLERS,
        PERSONA_ROLES,
        actors_of,
        principal_map,
    )

    loaded = load_platform_key(POS_012)
    adapter = WorkspaceAdapter(loaded)
    steps = [step for step in plan(loaded).steps if step.handler in LEDGER_RESOLVER_HANDLERS]
    calls = [adapter.plan_call(step) for step in steps]
    assert len(calls) >= 5 and all(call is not None for call in calls)
    first = calls[0]
    assert first is not None
    assert first.step.subject == "tenant currencies" and first.actor == "operator"
    # The ci refusal's shape, reproduced: no map → refused by name before any unit of work. Its
    # reason is ACT-1's own and says nothing of databases (item AK-NOT-RUN-REASON-1).
    with pytest.raises(
        NotProvisioned,
        match=(
            r"^not run — WORLD tenant currencies: no principal mapped "
            r"for actor 'operator'; Workspace\.uow\(None\) is never used \(rule ACT-1\) "
            r"\(erev_api\.domain\.reference\.commands\.put_tenant_currencies\)$"
        ),
    ):
        _principal_for(first, None)
    maya = SimpleNamespace(
        user_id=uuid5(TENANT, "maya"), tenant_id=TENANT, membership_id=uuid5(TENANT, "maya-m")
    )
    marcus = SimpleNamespace(
        user_id=uuid5(TENANT, "marcus"), tenant_id=TENANT, membership_id=uuid5(TENANT, "marcus-m")
    )
    principals = principal_map(maya, marcus, verified_at=VERIFIED_AT)
    with pytest.raises(TypeError):  # the stamp is required: a caller cannot forget it
        principal_map(maya, marcus)  # type: ignore[call-arg]
    assert actors_of(steps) <= set(principals)  # the ci defect: every actor is now mapped
    assert actors_of(steps) == {"ak-preparer", "operator"}
    assert {principal.tenant_id for principal in principals.values()} == {TENANT}
    for persona, principal in principals.items():
        assert set(PERSONA_ROLES[persona]) <= set(DEFAULT_ROLES)  # honest T-PLT-09 codes only
        assert principal.roles == tuple(sorted(PERSONA_ROLES[persona]))
        # approvals/engine.py refuses `mfa_verified_at is None` (mfa-required; batch #6 POS-117):
        # every persona principal is the verified session the API would present, stamped with
        # the WORKSPACE clock handed in (never datetime.now()); the shape is otherwise unchanged.
        assert principal.mfa_verified_at == VERIFIED_AT
        assert (principal.kind, principal.auth_method) == (PrincipalKind.USER, "password")
        assert principal.session_id is None and principal.support_grant_id is None
        assert principal.permissions == frozenset().union(
            *(DEFAULT_ROLES[code] for code in PERSONA_ROLES[persona])
        )
    preparer_calls = [call for call in calls if call is not None and call.actor == "ak-preparer"]
    assert len(preparer_calls) == len(calls) - 1
    assert all(
        _principal_for(call, principals) is principals["ak-preparer"] for call in preparer_calls
    )
    # The operator stand-in (marcus, holding the provisioned tenant_admin grant) applies the
    # tenant settings; the honest approver stand-in (controller) satisfies ROLE_CODES (Q-13 ruled).
    assert _principal_for(first, principals) is principals["operator"]
    assert set(principals) == {"ak-preparer", "ak-approver", "operator"}
    assert principals["ak-approver"].roles == ("controller", "tenant_admin")


def test_act_2_the_steps_api_permission_is_checked_before_any_domain_call() -> None:
    """ACT-2 (record §34; DG-AK-41 rev 1.38, D-98 candidate 107): after ACT-1 proves the principal
    and before the conversion or any unit of work, the invoker checks the step's declared API
    permission against the principal's permissions the way the API's guard does. A principal that
    holds the actor's roles but whose permissions do not grant the step is refused by name; the
    operator's provisioned grant (``settings.manage``) reaches the unit of work; a per-subject
    step names its any-of set."""
    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    adapter = WorkspaceAdapter(loaded)
    currencies = adapter.plan_call(next(s for s in steps if s.handler == H["currencies"]))
    entity = adapter.plan_call(next(s for s in steps if s.handler == H["entity"]))
    assert currencies is not None and entity is not None
    place = _Recording()
    titled = {
        **PERSONAS,
        "operator": _principal("Titled", ("tenant_admin",), TENANT, frozenset({"config.read"})),
    }
    with pytest.raises(
        NotProvisioned,
        match=(
            r"ACT-2: actor 'operator' lacks permission settings\.manage for step "
            r"'tenant currencies'"
        ),
    ):
        real_invoker(place, loaded.key, [], titled)(currencies)
    clerk = {
        **PERSONAS,
        "ak-preparer": _principal(
            "Clerk", ("revenue_accountant",), TENANT, frozenset({"contract.read"})
        ),
    }
    with pytest.raises(
        NotProvisioned,
        match=(
            r"ACT-2: actor 'ak-preparer' lacks permission any of masterdata\.maintain, "
            r"settings\.manage for step 'entity "
        ),
    ):
        real_invoker(place, loaded.key, [], clerk)(entity)
    assert place.principals == []  # every refusal came before a unit of work
    with pytest.raises(NotProvisioned, match="unit of work"):
        real_invoker(place, loaded.key, [], PERSONAS)(currencies)
    assert place.principals == [PERSONAS["operator"]]
    assert "settings.manage" in PERSONAS["operator"].permissions
    assert "masterdata.maintain" in PERSONAS["ak-preparer"].permissions


def test_the_real_invoker_sets_the_application_clock_to_the_steps_clock_at() -> None:
    """DG-AK-41 (PLAT-G4-1, record §35): each item runs with the application ``FrozenClock`` set to
    the plan's ``clock_at`` (the item's ``recorded_at``) before anything else happens — the DB-08
    record time then follows the server clock at commit; a step without ``clock_at`` leaves the
    clock where it is."""
    from erev_api.clock import FrozenClock

    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    adapter = WorkspaceAdapter(loaded)
    booking = adapter.plan_call(next(s for s in steps if s.handler == H["book"]))
    assert booking is not None and booking.step.clock_at is not None
    place = _Recording()
    place.clock = FrozenClock(datetime(2000, 1, 1, tzinfo=UTC))
    with pytest.raises(NotProvisioned):  # the booking needs ids the empty ledger cannot resolve
        real_invoker(place, loaded.key, [], PERSONAS)(booking)
    expected = datetime.strptime(booking.step.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert place.clock.now() == expected
    currencies = adapter.plan_call(next(s for s in steps if s.handler == H["currencies"]))
    assert currencies is not None and currencies.step.clock_at is None
    with pytest.raises(NotProvisioned, match="unit of work"):
        real_invoker(place, loaded.key, [], PERSONAS)(currencies)
    assert place.clock.now() == expected  # unchanged by a step without clock_at


def test_act_1_principal_is_proven_before_the_conversion_reads_anything() -> None:
    """Record §22 (b): a missing or wrong principal refuses before the conversion, so no read-side
    query runs; with the right principal the conversion may read (a Submitted's digest, then the
    digest of the impact preview its request shows — REQ-PLT-015) before the unit of work, which
    comes last."""
    from types import SimpleNamespace

    from erev_api.enums import ApprovalSubjectType
    from support.answer_keys.workspace_adapter import LedgerEntry

    class _Reads:
        def __init__(self) -> None:
            self.queries: list[tuple[str, tuple[UUID, ...]]] = []

        def approval_pairs(self, subject_type, subject_ids, *, where):  # noqa: ANN001, ANN201
            self.queries.append((subject_type.value, tuple(subject_ids)))
            return ((uuid5(TENANT, "request"), "b" * 64),)

        def impact_preview_sha256(self, approval_request_id):  # noqa: ANN001, ANN201
            self.queries.append(("impact preview", (approval_request_id,)))
            return "c" * 64

    class _Seen:
        clock = None
        keyring = None

        def __init__(self) -> None:
            self.principals: list[object] = []

        def uow(self, principal=None):  # noqa: ANN001, ANN201
            self.principals.append(principal)
            raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")

    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    adapter = WorkspaceAdapter(loaded)
    book = next(s for s in steps if s.handler == H["book"] and s.seq == 1)
    submit = next(s for s in steps if s.handler == H["submit_activation"] and s.seq == 2)
    decide = next(  # the activation's own approval: the runner's steps before it share seq 2
        s for s in steps if s.handler == H["decide"] and s.seq == 2 and s.phase == "TIMELINE"
    )
    at = datetime(2026, 1, 1, tzinfo=UTC)
    x = uuid5(TENANT, "X")
    ledger = [
        LedgerEntry(
            Call(H["book"], "ak-preparer", {"contract": "C-POS-012-X"}, book),
            "ak-preparer",
            at,
            at,
            at,
            SimpleNamespace(contract={"id": x}, combination_group={"id": uuid5(TENANT, "g")}),
        ),
        LedgerEntry(
            Call(H["submit_activation"], "ak-preparer", {"contract": "C-POS-012-X"}, submit),
            "ak-preparer",
            at,
            at,
            None,
            SimpleNamespace(contract={"id": x}, approval_request_id=uuid5(TENANT, "request")),
        ),
    ]
    decision = adapter.plan_call(decide)
    assert decision is not None and decision.actor == "ak-approver"
    reads, place = _Reads(), _Seen()
    with pytest.raises(NotProvisioned, match="no principal mapped for actor 'ak-approver'"):
        real_invoker(place, loaded.key, ledger, {}, reads)(decision)  # type: ignore[arg-type]
    assert reads.queries == [] and place.principals == []  # refused before any read or uow
    with pytest.raises(NotProvisioned, match="unit of work"):
        real_invoker(place, loaded.key, ledger, PERSONAS, reads)(decision)  # type: ignore[arg-type]
    assert reads.queries == [
        (ApprovalSubjectType.CONTRACT_ACTIVATION.value, (x,)),
        ("impact preview", (uuid5(TENANT, "request"),)),
    ]
    assert place.principals == [PERSONAS["ak-approver"]]  # the read preceded the uow, not the proof
