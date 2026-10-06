"""PLAT-G4-1 (record §35; DG-AK-41): the database platform over the real adapter — its runner
workspace, the persona principals built from the committed ledger with the API's own grants, the
lazily resolved job persona, and the fail-closed factory — proved on CPU with fakes. The database
run itself stays **not run — databases not provisioned** (lane databases are Ray-side).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.permissions import DEFAULT_ROLES, Grants
from erev_api.clock import FrozenClock
from erev_api.config import Environment
from erev_api.enums import PrincipalKind
from support.answer_keys import database_platform, request_models
from support.answer_keys.database_platform import (
    LedgerPrincipals,
    RunnerWorkspace,
    database_adapter,
)
from support.answer_keys.platform_plan import PLATFORM_KEY_IDS, H, Step, load_platform_key, plan
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.workspace_adapter import (
    JOURNAL_PERSONA,
    REPORT_PERSONA,
    Call,
    LedgerEntry,
    WorkspaceAdapter,
    WorkspaceJobs,
    _principal_for,
)

POS_012 = PLATFORM_KEY_IDS[0]
NOW = datetime(2026, 1, 2, 17, tzinfo=UTC)
TENANT = uuid5(NAMESPACE_URL, "erev://answer-keys/g4/tenant")
ADMIN, PREPARER_M, APPROVER_M = (
    uuid5(NAMESPACE_URL, f"erev://answer-keys/g4/membership/{name}")
    for name in ("admin", "ak-preparer", "ak-approver")
)
USERS = {
    ADMIN: (uuid5(NAMESPACE_URL, "erev://answer-keys/g4/user/admin"), "Provisioning admin"),
    PREPARER_M: (uuid5(NAMESPACE_URL, "erev://answer-keys/g4/user/prep"), "ak-preparer"),
    APPROVER_M: (uuid5(NAMESPACE_URL, "erev://answer-keys/g4/user/appr"), "ak-approver"),
}
ROLES = {ADMIN: ("tenant_admin",), PREPARER_M: ("revenue_accountant",), APPROVER_M: ("controller",)}


def _grants_of(membership_id: UUID) -> Grants:
    roles = ROLES[membership_id]
    permissions = frozenset[str]().union(*(DEFAULT_ROLES[code] for code in roles))
    return Grants(roles, permissions, {code: "*" for code in permissions}, "*")


def _user_of(membership_id: UUID) -> tuple[UUID, str]:
    return USERS[membership_id]


def _entry(handler: str, actor: str, subject: str, result: object) -> LedgerEntry:
    call = Call(handler, actor, {}, Step("PERSONAS", actor, handler, subject))
    return LedgerEntry(call, actor, None, None, None, result)


def _provisioned() -> LedgerEntry:
    result = SimpleNamespace(tenant={"id": TENANT}, admin_membership_id=ADMIN, roles=None)
    return _entry(H["provision"], "operator", "tenant", result)


def test_persona_principals_come_from_the_committed_ledger_and_the_apis_grants() -> None:
    """No persona exists before its committed step: the operator after provisioning (the admin
    membership), each persona after its invite; roles, permissions and scopes are the API's
    ``effective_grants`` of that membership, never a default; ACT-1 reads the mapping as it reads
    a dict; the system principal is not a persona (ACT-1 builds it from the tenant)."""
    ledger: list[LedgerEntry] = []
    principals = LedgerPrincipals(ledger, grants_of=_grants_of, user_of=_user_of, now=lambda: NOW)
    assert dict(principals) == {} and not principals
    ledger.append(_provisioned())
    assert set(principals) == {"operator"}
    operator = principals["operator"]
    assert operator.kind is PrincipalKind.USER and operator.tenant_id == TENANT
    assert operator.membership_id == ADMIN and operator.id == USERS[ADMIN][0]
    assert operator.roles == ("tenant_admin",) and "settings.manage" in operator.permissions
    assert operator.permission_scopes["settings.manage"] == "*" and operator.entity_scope == "*"
    ledger.append(_entry(H["invite"], "operator", "ak-preparer", PREPARER_M))
    ledger.append(_entry(H["invite"], "operator", "ak-approver", APPROVER_M))
    assert set(principals) == {"operator", "ak-preparer", "ak-approver"} and len(principals) == 3
    preparer, approver = principals["ak-preparer"], principals["ak-approver"]
    assert (
        preparer.roles == ("revenue_accountant",) and "masterdata.maintain" in preparer.permissions
    )
    assert approver.roles == ("controller",) and approver.display_name == "ak-approver"
    # The runner's personas are verified sessions: approvals/engine.py refuses `mfa_verified_at is
    # None` with mfa-required (batch #6 POS-117); the stamp is the application clock.
    assert approver.mfa_verified_at == NOW and operator.mfa_verified_at == NOW
    assert approver.id == USERS[APPROVER_M][0] and approver.tenant_id == TENANT
    with pytest.raises(KeyError):
        principals["system"]
    assert principals.get("system") is None
    loaded = load_platform_key(POS_012)
    currencies = WorkspaceAdapter(loaded).plan_call(
        next(s for s in plan(loaded).steps if s.handler == H["currencies"])
    )
    assert currencies is not None
    assert _principal_for(currencies, principals) == operator


def test_the_runner_workspace_names_its_tenant_from_the_committed_provisioning() -> None:
    """The workspace's tenant is the provisioned one — read from the ledger, never configured —
    and its unit of work is never opened without a principal (ACT-1)."""
    ledger: list[LedgerEntry] = []
    workspace = RunnerWorkspace(clock=FrozenClock(NOW), keyring=None, files=None, ledger=ledger)
    with pytest.raises(NotProvisioned, match="no committed provisioning"):
        _ = workspace.tenant_id
    ledger.append(_provisioned())
    assert workspace.tenant_id == TENANT
    with pytest.raises(NotProvisioned, match="ACT-1"), workspace.uow(None):
        pass


def test_the_factory_refuses_outside_a_test_database_and_names_only_the_exception_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory runs only with ``EREV_ENV=test`` on ``erev_test`` / ``erev_rv_*`` (DG-ENV-13);
    a preparation failure is refused by name with the database's name (safe to log, DG-ENV-11)
    and the exception type — never a URL or credentials."""
    loaded = load_platform_key(POS_012)
    dev = SimpleNamespace(env=Environment.DEV, database_name=lambda: "erev")
    monkeypatch.setattr(database_platform, "get_settings", lambda: dev)
    with pytest.raises(
        NotProvisioned,
        match=(
            r"database platform: EREV_ENV=test on erev_test or erev_rv_\* required; "
            r"selected erev \(dev\)"
        ),
    ) as outside:
        database_adapter(loaded)
    # The factory's refusals are the lane's own reason and say so (item AK-NOT-RUN-REASON-1).
    assert outside.value.unprovisioned is True
    assert str(outside.value).startswith(
        "not run — databases not provisioned: database platform: EREV_ENV=test on erev_test"
    )
    lane = SimpleNamespace(env=Environment.TEST, database_name=lambda: "erev_rv_l17_test")
    monkeypatch.setattr(database_platform, "get_settings", lambda: lane)

    class _Unreachable(Exception):
        pass

    def failing(_settings: object) -> object:
        raise _Unreachable("postgresql://user:secret@host/erev_rv_l17_test")

    monkeypatch.setattr(database_platform, "prepare_database", failing)
    with pytest.raises(NotProvisioned) as refused:
        database_adapter(loaded)
    text = str(refused.value)
    assert "database platform: database erev_rv_l17_test is not available (_Unreachable)" in text
    assert "secret" not in text and "postgresql://" not in text
    assert refused.value.unprovisioned is True
    assert text.startswith("not run — databases not provisioned: database platform: database ")


def test_job_runs_resolve_the_job_persona_when_they_run_not_at_construction() -> None:
    """The job collaborator reads the approver from the principal mapping when a run starts —
    the persona is invited after the collaborator exists — and refuses by name until then."""
    principals: dict[str, object] = {}
    jobs = WorkspaceJobs(SimpleNamespace(), principals)
    with pytest.raises(NotProvisioned, match="no principal mapped for 'ak-preparer'"):
        jobs._principal("journals US01 FY2026-P01 GROSS", "ak-preparer")
    with pytest.raises(NotProvisioned, match="no principal mapped for 'ak-approver'"):
        jobs._principal("reports rpo", "ak-approver")
    preparer, approver = object(), object()
    principals["ak-preparer"], principals["ak-approver"] = preparer, approver
    assert jobs._principal("journals US01 FY2026-P01 GROSS", "ak-preparer") is preparer
    assert jobs._principal("reports rpo", "ak-approver") is approver


class _TenantBoundWorkspace(RunnerWorkspace):
    """The runner workspace with its two database reads faked: like the real ones they need the
    tenant (``_context()`` → ``tenant_id`` from the ledger) before they can answer."""

    def __init__(self) -> None:
        super().__init__(clock=FrozenClock(NOW), keyring=object(), files=object(), ledger=[])
        self.stamps = 0

    def scalar(self, statement: object) -> datetime:
        self._context()  # NotProvisioned until the ledger names the tenant
        self.stamps += 1
        return datetime(2026, 1, 2, 17, 0, self.stamps, tzinfo=UTC)

    def rows(self, statement: object) -> list[dict[str, object]]:
        self._context()
        raise NotProvisioned("workspace rows", "test double")


def test_the_committed_provisioning_is_recorded_before_the_server_stamp_needs_the_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAT-G4-R1 (record §37): with the initially empty adapter ledger, a native-shaped committed
    provisioning result is recorded first and the post-commit server stamp is then read with the
    tenant provenance the committed result gives — exactly one recorded provision, stamped, and
    the tenant and the operator resolve. No default principal, no fabricated stamp, no fallback."""
    loaded = load_platform_key(POS_012)
    workspace = _TenantBoundWorkspace()
    principals = LedgerPrincipals(
        workspace.ledger, grants_of=_grants_of, user_of=_user_of, now=lambda: NOW
    )
    adapter = WorkspaceAdapter.for_database(loaded, workspace, principals)
    workspace.ledger = adapter.ledger  # one ledger, as database_adapter binds it
    principals.ledger = adapter.ledger
    native = SimpleNamespace(
        tenant={"id": TENANT}, admin_membership_id=ADMIN, roles={"tenant_admin": uuid5(TENANT, "r")}
    )
    real_handler_of = request_models.handler_of

    def handler_of(path: str):  # noqa: ANN202 — the committed native call, without a database
        if path == H["provision"]:
            return lambda request, *, actor, clock, keyring: native
        return real_handler_of(path)

    monkeypatch.setattr(request_models, "handler_of", handler_of)
    provision = next(s for s in plan(loaded).steps if s.handler == H["provision"])
    adapter.run(provision)
    recorded = [e for e in adapter.ledger if e.call.handler == H["provision"]]
    assert len(recorded) == 1 and recorded[0].result is native
    assert recorded[0].server_at == datetime(2026, 1, 2, 17, 0, 1, tzinfo=UTC)
    # Two reads follow the commit: the clock, then the transaction horizon beside it (dev-guide
    # rev 1.246). This double answers the horizon read with an instant and no transaction id,
    # so the ledger keeps none rather than guess one; ``clock_timestamp`` reads nothing more.
    assert workspace.stamps == 2 and recorded[0].horizon is None
    assert adapter.clock_timestamp() == recorded[0].server_at and workspace.stamps == 2
    assert workspace.tenant_id == TENANT
    assert principals["operator"].membership_id == ADMIN


def test_for_database_keeps_the_live_principal_mapping_for_job_runs() -> None:
    """PLAT-G4-R2 (record §37): an initially empty live mapping is handed to the job collaborator
    as is — never Boolean-tested away — so once the shared ledger records the invites the journal
    and report personas resolve at run time."""
    loaded = load_platform_key(POS_012)
    principals = LedgerPrincipals([], grants_of=_grants_of, user_of=_user_of, now=lambda: NOW)
    assert not principals  # empty: the ledger has committed nothing yet
    adapter = WorkspaceAdapter.for_database(loaded, _TenantBoundWorkspace(), principals)
    assert adapter.jobs.principals is principals
    principals.ledger = adapter.ledger
    with pytest.raises(NotProvisioned, match="no principal mapped for 'ak-preparer'"):
        adapter.jobs._principal("journals US01 FY2026-P01 GROSS", JOURNAL_PERSONA)
    adapter.ledger.append(_provisioned())
    adapter.ledger.append(_entry(H["invite"], "operator", "ak-preparer", PREPARER_M))
    adapter.ledger.append(_entry(H["invite"], "operator", "ak-approver", APPROVER_M))
    journal = adapter.jobs._principal("journals US01 FY2026-P01 GROSS", JOURNAL_PERSONA)
    report = adapter.jobs._principal("reports rpo", REPORT_PERSONA)
    assert journal.membership_id == PREPARER_M and report.membership_id == APPROVER_M
