"""PLAT-G4-1 — the database platform over the real adapter (record §35; dev-guide DG-AK-41;
BUILD_SPEC PRP-1; D-98 candidate 107 ACT-1 / ACT-2).

``platform_runner._platform`` selects this factory under ``EREV_AK_PLATFORM=db``:
``database_adapter`` builds the real ``WorkspaceAdapter`` (``for_database``) over a **runner
workspace** — an isolated tenant the plan itself provisions (PROVISION), personas the plan itself
invites and grants and who accept their invitation before they act (PERSONAS), units of work
opened only under a proven principal (ACT-1) whose API
permission is checked before every direct domain call (ACT-2), the server clock for ``known_at``
(DB-08), persisted reads and job execution — on a **test database only**: ``EREV_ENV=test`` on
``erev_test`` or a lane database ``erev_rv_*`` (DG-ENV-13), prepared once per process exactly as
the ``test_database`` fixture prepares it (advisory lock, schema reset, ``alembic upgrade head``,
DB-14 lint).

Fail closed, never silently: without such a database the factory refuses by name — the
database's name (safe to log, DG-ENV-11) and the exception **type**, never a URL — and
``DbPlatform`` marks every step and block not run with that reason; there is no fallback to
``MockAdapter`` or the in-memory platform. Lane databases are Ray-side provisioning; this module
creates none.

Persona principals are the API's own: ``LedgerPrincipals`` reads which memberships the committed
ledger created (the provisioning admin is the operator; each invite is its persona) and builds
each ``Principal`` as ``auth.dependencies._session_context`` does — ``effective_grants`` of the
membership at the application clock — never a default and never before the step that created it
committed. The world's API client (``ak-integration``; BUILD_SPEC CTR-6) is read the same way:
from the committed ``create_api_client`` step, with the grants ``auth.api_clients.token_principal``
gives a token of all the client's scopes (``api_client_grants``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_api.auth.permissions import Grants, api_client_grants, effective_grants
from erev_api.auth.principal import Principal, RequestContext
from erev_api.config import Environment, Settings, get_settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.enums import PrincipalKind, TenantKind
from sqlalchemy import select, text
from support.answer_keys.platform_plan import INTEGRATION, OPERATOR, H
from support.answer_keys.platform_runner import DomainAdapter, NotProvisioned

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork
    from support.answer_keys.loader import LoadedKey
    from support.answer_keys.workspace_adapter import LedgerEntry

TEST_DATABASES: Final = re.compile(r"^(erev_test|erev_rv_[a-z0-9_]+)$")  # DG-ENV-13, as conftest
REQUEST_ID: Final = "answer-keys-platform"
PREPARE_HANDLER: Final = "erev_api.db.session.owner_engine"


class RunnerWorkspace:
    """The adapter's workspace over the tenant the plan provisions: units of work under an explicit
    principal (ACT-1), tenant-scoped read sessions, the application clock, key ring and file
    store. The tenant is read from the committed provisioning result, never configured."""

    def __init__(
        self, *, clock: Any, keyring: Any, files: Any, ledger: Sequence[LedgerEntry]
    ) -> None:
        self.clock = clock
        self.keyring = keyring
        self.files = files
        self.ledger = ledger

    @property
    def tenant_id(self) -> UUID:
        for entry in self.ledger:
            if entry.call.handler == H["provision"]:
                tenant = getattr(entry.result, "tenant", None)
                if isinstance(tenant, Mapping) and "id" in tenant:
                    return UUID(str(tenant["id"]))
        raise NotProvisioned("tenant id: no committed provisioning in the ledger", H["provision"])

    @contextmanager
    def uow(self, principal: Principal | None = None, *, clock: Any = None) -> Iterator[UnitOfWork]:
        """A unit of work for ``principal`` capturing ``now`` from the workspace's application
        clock — or from ``clock`` when a caller supplies one: the record-time clock of a
        checkpoint report run (``WorkspaceJobs.report_run``; F-RPS-CUTOFF-R1, record §43)."""
        if principal is None:
            raise NotProvisioned(
                "workspace unit of work: no principal (rule ACT-1); the runner workspace has no "
                "default principal",
                "support.answer_keys.database_platform.RunnerWorkspace.uow",
            )
        from erev_api.uow import unit_of_work

        at = self.clock if clock is None else clock
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id=REQUEST_ID,
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=at.now(),
            format_locale="en-US",
        )
        with unit_of_work(ctx, clock=at, keyring=self.keyring, files=self.files) as uow:
            yield uow

    def _context(self) -> DbContext:
        return DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")

    def rows(self, statement: Any) -> list[dict[str, Any]]:
        with tenant_session(self._context(), read_only=True) as session:
            return [dict(row) for row in session.execute(statement).mappings()]

    def scalar(self, statement: Any) -> Any:
        with tenant_session(self._context(), read_only=True) as session:
            return session.execute(statement).scalar_one()


class LedgerPrincipals(Mapping[str, Principal]):
    """Persona → ``Principal`` from the committed ledger (rule ACT-1): the provisioning admin is
    the ``operator``; each committed invite is the persona its step names; grants are the API's
    ``effective_grants`` of the membership at the application clock. A persona whose creating
    step has not committed is absent (never defaulted); ``system`` is not a persona. The world's
    API client (``INTEGRATION``; BUILD_SPEC CTR-6) is the client the committed
    ``create_api_client`` step created, with the grants of a token of all its scopes
    (``client_grants_of``); without that reader, or before that step committed, it is absent."""

    def __init__(
        self,
        ledger: Sequence[LedgerEntry],
        *,
        grants_of: Callable[[UUID], Grants],
        user_of: Callable[[UUID], tuple[UUID, str]],
        now: Callable[[], datetime],
        client_grants_of: Callable[[UUID, Sequence[str]], Grants] | None = None,
    ) -> None:
        self.ledger = ledger
        self.grants_of = grants_of
        self.user_of = user_of
        self.now = now
        self.client_grants_of = client_grants_of

    def _memberships(self) -> dict[str, tuple[UUID, UUID]]:
        found: dict[str, tuple[UUID, UUID]] = {}
        tenant: UUID | None = None
        for entry in self.ledger:
            handler, result = entry.call.handler, entry.result
            if handler == H["provision"]:
                tenant_row = getattr(result, "tenant", None)
                admin = getattr(result, "admin_membership_id", None)
                if isinstance(tenant_row, Mapping) and "id" in tenant_row and admin is not None:
                    tenant = UUID(str(tenant_row["id"]))
                    found[OPERATOR] = (tenant, UUID(str(admin)))
            elif handler == H["invite"] and tenant is not None and isinstance(result, UUID):
                found[entry.call.step.subject] = (tenant, result)  # the invite's subject: persona
        return found

    def _client(self) -> tuple[UUID, Mapping[str, Any]] | None:
        """(tenant, the ``api_client`` row) of the committed ``create_api_client`` step."""
        tenant: UUID | None = None
        for entry in self.ledger:
            handler, result = entry.call.handler, entry.result
            if handler == H["provision"]:
                tenant_row = getattr(result, "tenant", None)
                if isinstance(tenant_row, Mapping) and "id" in tenant_row:
                    tenant = UUID(str(tenant_row["id"]))
            elif handler == H["api_client"] and tenant is not None:
                client = getattr(result, "client", None)
                if isinstance(client, Mapping) and "id" in client:
                    return tenant, client
        return None

    def _integration(self) -> Principal:
        found = self._client()
        if found is None or self.client_grants_of is None:
            raise KeyError(INTEGRATION)
        tenant, client = found
        client_id = UUID(str(client["id"]))
        grants = self.client_grants_of(client_id, [str(code) for code in client["scopes"]])
        return Principal(
            kind=PrincipalKind.API_CLIENT,
            id=client_id,
            tenant_id=tenant,
            membership_id=None,
            display_name=str(client["name"]),
            roles=grants.roles,
            permissions=grants.permissions,
            permission_scopes=grants.permission_scopes,
            entity_scope=grants.entity_scope,
            auth_method="client_credentials",
            mfa_verified_at=None,
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        )

    def _names(self) -> list[str]:
        names = list(self._memberships())
        if self._client() is not None and self.client_grants_of is not None:
            names.append(INTEGRATION)
        return names

    def __getitem__(self, persona: str) -> Principal:
        if persona == INTEGRATION:
            return self._integration()
        tenant, membership = self._memberships()[persona]
        grants = self.grants_of(membership)
        user_id, display_name = self.user_of(membership)
        return Principal(
            kind=PrincipalKind.USER,
            id=user_id,
            tenant_id=tenant,
            membership_id=membership,
            display_name=display_name,
            roles=grants.roles,
            permissions=grants.permissions,
            permission_scopes=grants.permission_scopes,
            entity_scope=grants.entity_scope,
            auth_method="password",
            # The runner acts as each persona's verified session (approvals refuse an unverified
            # principal: approvals/engine.py `mfa-required`); the stamp is the application clock.
            mfa_verified_at=self.now(),
            session_id=None,
            support_grant_id=None,
            on_behalf_of_id=None,
        )

    def __iter__(self) -> Iterator[str]:
        return iter(self._names())

    def __len__(self) -> int:
        return len(self._names())


@dataclass(frozen=True, slots=True)
class PreparedDatabase:
    """The engines of the prepared test database and the application clock of the run."""

    app_engine: Any
    owner_engine: Any
    clock: Any


_PREPARED: dict[str, PreparedDatabase] = {}
_LOCKS: dict[str, Any] = {}


def prepare_database(settings: Settings) -> PreparedDatabase:
    """Prepare the selected test database once per process exactly as ``tests/conftest.py``'s
    ``test_database`` does: the session advisory lock, schema reset, ``alembic upgrade head`` and
    the DB-14 lint as ``erev_app``. Refuses (``DestructiveResetRefused``) outside the DG-ENV-13
    allow-list. Creates no database."""
    name = settings.database_name()
    if name in _PREPARED:
        return _PREPARED[name]
    from alembic import command
    from erev_api.db.lint import lint_as_app
    from erev_api.db.session import app_engine, owner_engine
    from support.clock import frozen_clock
    from support.db import TEST_DB_LOCK_KEY, alembic_config, reset_schema

    owner, app = owner_engine(), app_engine()
    lock_connection = owner.connect()
    lock_connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": TEST_DB_LOCK_KEY})
    lock_connection.commit()
    _LOCKS[name] = lock_connection  # held for the process, as the fixture holds it for the session
    reset_schema(settings.owner_database_url())
    command.upgrade(alembic_config(), "head")
    findings = lint_as_app(request_id="answer-keys-lint")
    if findings:
        raise RuntimeError(f"DB-14 lint after upgrade: {len(findings)} findings")
    prepared = PreparedDatabase(app_engine=app, owner_engine=owner, clock=frozen_clock())
    _PREPARED[name] = prepared
    return prepared


def _grants_reader(workspace: RunnerWorkspace) -> Callable[[UUID], Grants]:
    def grants_of(membership_id: UUID) -> Grants:
        with tenant_session(workspace._context(), read_only=True) as session:
            return effective_grants(session, membership_id, at=workspace.clock.now())

    return grants_of


def _client_grants_reader(
    workspace: RunnerWorkspace,
) -> Callable[[UUID, Sequence[str]], Grants]:
    def client_grants_of(api_client_id: UUID, scopes: Sequence[str]) -> Grants:
        with tenant_session(workspace._context(), read_only=True) as session:
            return api_client_grants(
                session, api_client_id, token_scopes=scopes, at=workspace.clock.now()
            )

    return client_grants_of


def _user_reader(workspace: RunnerWorkspace) -> Callable[[UUID], tuple[UUID, str]]:
    def user_of(membership_id: UUID) -> tuple[UUID, str]:
        from erev_api.db.tables import app_user, tenant_membership

        statement = (
            select(tenant_membership.c.user_id, app_user.c.display_name)
            .join(app_user, app_user.c.id == tenant_membership.c.user_id)
            .where(tenant_membership.c.id == membership_id)
        )
        (row,) = workspace.rows(statement)
        return UUID(str(row["user_id"])), str(row["display_name"])

    return user_of


def database_adapter(loaded: LoadedKey) -> DomainAdapter:
    """The real adapter for ``DbPlatform`` (``platform_runner._platform`` under
    ``EREV_AK_PLATFORM=db``), or a named refusal: never a mock, never in memory."""
    from erev_api.auth.keyring import build_keyring
    from erev_api.files.store import LocalFileStore
    from support.answer_keys.workspace_adapter import WorkspaceAdapter
    from support.factories import stamp_test_release

    settings = get_settings()
    name = settings.database_name()  # the name is safe to log (DG-ENV-11); URLs never are
    if settings.env is not Environment.TEST or not TEST_DATABASES.fullmatch(name):
        raise NotProvisioned(
            "database platform: EREV_ENV=test on erev_test or erev_rv_* required; "
            f"selected {name} ({settings.env.value})",
            H["provision"],
            unprovisioned=True,
        )
    try:
        prepared = prepare_database(settings)
    except NotProvisioned:
        raise
    except Exception as error:  # noqa: BLE001 — the exception type only, never its text (URLs)
        raise NotProvisioned(
            f"database platform: database {name} is not available ({type(error).__name__})",
            PREPARE_HANDLER,
            unprovisioned=True,
        ) from None
    # 05 REL-03 / CTL-032: a computation names the release its process stamped at startup. The
    # runner's process has no api lifespan and no worker start, so it stamps here, as the test
    # workspaces do (``support.factories.stamp_test_release``); a process that stamped nothing is
    # refused at its first computation (503 release-mismatch).
    stamp_test_release()
    workspace = RunnerWorkspace(
        clock=prepared.clock,
        keyring=build_keyring(settings),
        files=LocalFileStore(settings.file_root),
        ledger=[],
    )
    principals = LedgerPrincipals(
        workspace.ledger,
        grants_of=_grants_reader(workspace),
        user_of=_user_reader(workspace),
        now=workspace.clock.now,
        client_grants_of=_client_grants_reader(workspace),
    )
    adapter = WorkspaceAdapter.for_database(loaded, workspace, principals)
    # One ledger: the adapter's, read by the workspace (tenant) and the principals (personas).
    workspace.ledger = adapter.ledger
    principals.ledger = adapter.ledger
    return adapter
