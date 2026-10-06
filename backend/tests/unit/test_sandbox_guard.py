"""BUILD_SPEC SNP-4 — the production guard and the webhook layers, CPU only (05 §10 SBX-08
rev 1.64; 03 REQ-PLT-022; CTL-043; security finding SF-1, supervisor ruling R-33).

``guards.ensure_production`` is what every restricted command calls: in a sandbox it audits the
attempt ``DENIED`` through ``audit_writer.record_now`` — a transaction of its own — and raises 403
``sandbox-restricted``; in production it does nothing. The webhook endpoint commands call it before
they read, validate, generate or write anything, and ``emit_webhook`` returns before it touches
the session. The database witnesses are ``tests/domain/platform/test_sandbox_restrictions.py``.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.platform import guards, privacy, webhook_endpoints
from erev_api.enums import AuditOutcome, FilePurpose, PrincipalKind, TenantKind
from erev_api.events import webhooks
from erev_api.files import store
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
TENANT = UUID(int=0xA1)
USER = UUID(int=0x51)
ENDPOINT = UUID(int=0xE1)
KIND = "period.locked"


class _Untouched:
    """A session or key ring the refused command must not reach."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the refused command reached {name!r}")


class _Rows:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _Rows:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._row


class _Session:
    """Answers every read with ``row`` and records the statements."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.statements: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Rows:
        self.statements.append(str(statement).split(" ", 1)[0])
        return _Rows(self.row)


def _uow(kind: TenantKind, *, session: Any = None, keyring: Any = None) -> tuple[UnitOfWork, Any]:
    principal = SimpleNamespace(id=USER, kind=PrincipalKind.USER, tenant_id=TENANT)
    fake = SimpleNamespace(
        session=_Untouched() if session is None else session,
        keyring=_Untouched() if keyring is None else keyring,
        now=NOW,
        principal=principal,
        ctx=SimpleNamespace(tenant_kind=kind, principal=principal),
        audited=[],
    )
    fake.audit = lambda **kwargs: fake.audited.append(dict(kwargs))
    return cast(UnitOfWork, fake), fake


@pytest.fixture
def denials(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What ``audit_writer.record_now`` was asked to write in its own transaction."""
    seen: list[dict[str, Any]] = []

    def record_now(ctx: Any, **kwargs: Any) -> None:
        seen.append({"ctx": ctx, **kwargs})

    monkeypatch.setattr(guards.audit_writer, "record_now", record_now)
    return seen


def _endpoint_row(*, is_active: bool) -> dict[str, Any]:
    return {
        "id": ENDPOINT,
        "url": "https://hooks.example/erev",
        "description": None,
        "event_kinds": [KIND],
        "is_active": is_active,
        "created_at": NOW,
        "updated_at": NOW,
        "row_version": 1,
    }


def test_the_guard_does_nothing_in_a_production_tenant(denials: list[dict[str, Any]]) -> None:
    uow, _ = _uow(TenantKind.PRODUCTION)
    guards.ensure_production(uow, action="x.do", object_type="x", object_id=ENDPOINT)
    assert denials == []


def test_the_guard_audits_the_attempt_and_refuses_in_a_sandbox(
    denials: list[dict[str, Any]],
) -> None:
    uow, fake = _uow(TenantKind.SANDBOX)
    with pytest.raises(Problem) as excinfo:
        guards.ensure_production(
            uow,
            action="journal_run.request_export",
            object_type="journal_run",
            object_id=ENDPOINT,
            detail={"adapter": "NETSUITE"},
        )
    problem = excinfo.value
    assert (problem.slug, problem.status) == ("sandbox-restricted", 403)
    assert problem.detail == "Sandbox workspaces cannot post or export journals."  # PRD ERR-17
    [denial] = denials
    assert denial == {
        "ctx": fake.ctx,
        "action": "journal_run.request_export",
        "object_type": "journal_run",
        "object_id": ENDPOINT,
        "outcome": AuditOutcome.DENIED,
        "detail": {"adapter": "NETSUITE", "problem": "sandbox-restricted"},
        "keyring": fake.keyring,
    }
    # The command's own unit of work wrote nothing: the evidence is the separate transaction's.
    assert fake.audited == []


def test_the_guard_carries_the_commands_own_message(denials: list[dict[str, Any]]) -> None:
    uow, _ = _uow(TenantKind.SANDBOX)
    with pytest.raises(Problem) as excinfo:
        guards.ensure_production(
            uow, action="x.do", object_type="x", object_id=None, message="Not in a sandbox."
        )
    assert excinfo.value.detail == "Not in a sandbox."
    assert denials[0]["detail"] == {"problem": "sandbox-restricted"}


def test_a_sandbox_refuses_to_create_a_webhook_endpoint_before_anything_else(
    denials: list[dict[str, Any]],
) -> None:
    """Security finding SF-1: the endpoint would be created active. The refusal comes before the
    validation — an invalid URL answers 403, not 422 — and before the secret is generated or
    sealed: the session and the key ring of the command are never reached."""
    uow, fake = _uow(TenantKind.SANDBOX)  # its session and its key ring raise when reached
    for url in ("https://hooks.example/erev", "not a url"):
        with pytest.raises(Problem) as excinfo:
            webhook_endpoints.create_endpoint(uow, url=url, description=None, event_kinds=[KIND])
        assert (excinfo.value.slug, excinfo.value.status) == ("sandbox-restricted", 403)
        assert excinfo.value.detail == webhook_endpoints.SANDBOX_ENDPOINT
    assert [
        (d["action"], d["object_type"], d["object_id"], d["outcome"], d["detail"]) for d in denials
    ] == [
        (
            "webhook_endpoint.create",
            "webhook_endpoint",
            None,
            AuditOutcome.DENIED,
            {"is_active": True, "problem": "sandbox-restricted"},
        )
    ] * 2
    assert fake.audited == []


@pytest.mark.parametrize(
    ("stored_active", "changes", "refused"),
    [
        (False, {"is_active": True}, True),  # the activation
        (False, {"is_active": True, "url": "not a url"}, True),  # refused before validation
        (True, {"description": "still on"}, True),  # an active row that would stay active
        (True, {"is_active": None}, True),  # a null member of an active row: refused, not 422
        (True, {"is_active": False}, False),  # deactivating stays possible
        (False, {"description": "kept for reference"}, False),  # so does editing an inactive one
    ],
)
def test_a_sandbox_refuses_every_change_that_leaves_an_endpoint_active(
    denials: list[dict[str, Any]],
    stored_active: bool,
    changes: dict[str, Any],
    refused: bool,
) -> None:
    session = _Session(_endpoint_row(is_active=stored_active))
    uow, fake = _uow(TenantKind.SANDBOX, session=session, keyring=object())
    if refused:
        with pytest.raises(Problem) as excinfo:
            webhook_endpoints.update_endpoint(
                uow, ENDPOINT, changes, check_version=lambda actual: None
            )
        assert (excinfo.value.slug, excinfo.value.status) == ("sandbox-restricted", 403)
        [denial] = denials
        assert (denial["action"], denial["object_id"], denial["outcome"]) == (
            "webhook_endpoint.update",
            ENDPOINT,
            AuditOutcome.DENIED,
        )
        assert denial["detail"] == {
            "is_active": True,
            "was_active": stored_active,
            "problem": "sandbox-restricted",
        }
        # Only the locked read of the row happened; no UPDATE, no success event.
        assert session.statements == ["SELECT"] and fake.audited == []
    else:
        webhook_endpoints.update_endpoint(uow, ENDPOINT, changes, check_version=lambda actual: None)
        assert denials == []
        assert "UPDATE" in session.statements
        assert [event["action"] for event in fake.audited] == ["webhook_endpoint.update"]


def test_production_changes_an_endpoint_without_the_guard(denials: list[dict[str, Any]]) -> None:
    session = _Session(_endpoint_row(is_active=False))
    uow, fake = _uow(TenantKind.PRODUCTION, session=session, keyring=object())
    webhook_endpoints.update_endpoint(
        uow, ENDPOINT, {"is_active": True}, check_version=lambda actual: None
    )
    assert denials == [] and "UPDATE" in session.statements
    assert fake.audited[0]["after"]["is_active"] is True


def test_emit_webhook_emits_nothing_in_a_sandbox_whatever_the_rows_say() -> None:
    """05 SBX-08, the second layer: the session is never read, so an endpoint row that is active
    — however it came to be — cannot receive a delivery. The caller's mistakes are still named."""
    uow, _ = _uow(TenantKind.SANDBOX)  # its session raises when reached
    assert webhooks.emit_webhook(uow, event_kind=KIND, payload={"period_id": ENDPOINT}) == 0
    with pytest.raises(ValueError, match="unknown webhook event kind"):
        webhooks.emit_webhook(uow, event_kind="contract.created", payload={})
    with pytest.raises(ValueError, match="must be an id or an href"):
        webhooks.emit_webhook(uow, event_kind=KIND, payload={"amount": "12.00"})


def test_emit_webhook_reads_the_endpoints_in_production() -> None:
    """The positive control of the case above: the same call in a production tenant reaches the
    session (here: the fake that refuses to be reached)."""
    uow, _ = _uow(TenantKind.PRODUCTION)
    with pytest.raises(AssertionError, match="the refused command reached"):
        webhooks.emit_webhook(uow, event_kind=KIND, payload={"period_id": ENDPOINT})


def test_db_15_revision_refuses_the_activation_and_not_the_state() -> None:
    """Revision 0091 (04 §14.1 DB-15 rev 1.125): the body returns before it reads the tenant for
    a row that is not active and for an UPDATE of a row that already was; only then is the
    tenant's kind read and ``EREV-SBX-001`` raised for a sandbox. The downgrade drops the trigger
    and its function."""
    versions = Path(webhooks.__file__).resolve().parents[1] / "db" / "migrations" / "versions"
    name = "0091_snp_4_webhook_endpoint_sandbox"
    spec = importlib.util.spec_from_file_location(name, versions / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.TABLE, module.PURPOSE) == (
        "0091",
        "webhook_endpoint",
        "sandbox",
    )
    body = module.ENDPOINT_SANDBOX_BODY
    inactive = body.index("IF NOT NEW.is_active THEN")
    already = body.index("IF TG_OP = 'UPDATE' AND OLD.is_active THEN")
    kind = body.index("FROM erev.tenant t WHERE t.id = NEW.tenant_id")
    refusal = body.index("EREV-SBX-001")
    assert inactive < already < kind < refusal
    assert "IF tenant_kind = 'sandbox' THEN" in body[kind:refusal]


# --- 05 SBX-08 rev 1.164: a sandbox shreds what it stored itself and nothing it shares ---------

SOURCE = UUID(int=0xB2)  # the workspace the sandbox ``TENANT`` was copied from
DIGEST = "ab" * 32


def test_sbx_08_a_stored_file_is_a_workspaces_own_by_the_first_segment_of_its_key() -> None:
    """ "Own" is read from ``file_object.storage_key``: its first segment is the id of the
    workspace that stored the object, and the rows of a copy keep the keys of their source
    (SBX-03). The reading is pinned against the function that WRITES keys: if the form of a key
    changes, ``owns_key`` no longer recognises a workspace's own key and this test fails — the
    door closes; it is not opened silently."""
    for purpose in FilePurpose:
        own = store.storage_key(TENANT, purpose, DIGEST)
        assert own == f"{TENANT}/{purpose.value}/{DIGEST}", "the form the reading relies on"
        assert store.owns_key(TENANT, own)
        assert not store.owns_key(TENANT, store.storage_key(SOURCE, purpose, DIGEST))
        assert not store.owns_key(SOURCE, own)


OTHER_FORMS = [
    "",  # nothing
    str(TENANT),  # no separator
    f"{TENANT}/ATTACHMENT",  # too few segments
    f"/ATTACHMENT/{DIGEST}",  # an empty first segment
    f"/{TENANT}/ATTACHMENT/{DIGEST}",  # the id is not the first segment
    f"files/{TENANT}/ATTACHMENT/{DIGEST}",  # a prefix before the id
    f"{TENANT}x/ATTACHMENT/{DIGEST}",  # the id as a prefix of the segment
    f"{str(TENANT).upper()}/ATTACHMENT/{DIGEST}",  # another case
    f"{TENANT}/ATTACHMENT/{DIGEST}/extra",  # too many segments
]


@pytest.mark.parametrize("key", OTHER_FORMS)
def test_sbx_08_a_key_of_another_form_is_nobodys_own(key: str) -> None:
    """A storage key that does not have the form at all is not own: the answer is False, never
    an error — the guard then refuses in a sandbox, it does not raise."""
    assert store.owns_key(TENANT, key) is False


def _file_row(key: str) -> dict[str, Any]:
    return {"id": ENDPOINT, "storage_key": key}


def test_sbx_08_a_sandbox_is_refused_a_file_it_shares_and_not_its_own(
    denials: list[dict[str, Any]],
) -> None:
    """``privacy.refuse_shared_in_sandbox`` — what the three commands that destroy a stored file
    call once they hold its row: in a sandbox a key of the source, and a key of no form, are
    refused 403 ``sandbox-restricted`` with the ``DENIED`` event of the command and the line of
    the refusal; the sandbox's own key passes without a word; a production workspace passes
    whatever the key."""
    own = store.storage_key(TENANT, FilePurpose.ATTACHMENT, DIGEST)
    shared = store.storage_key(SOURCE, FilePurpose.ATTACHMENT, DIGEST)
    sandbox, fake = _uow(TenantKind.SANDBOX)
    privacy.refuse_shared_in_sandbox(
        sandbox, _file_row(own), action="file_object.shred", detail={"reason": "DSR-1"}
    )
    assert denials == []
    for key in (shared, "", "no-separator"):
        with pytest.raises(Problem) as excinfo:
            privacy.refuse_shared_in_sandbox(
                sandbox, _file_row(key), action="file_object.shred", detail={"reason": "DSR-1"}
            )
        assert (excinfo.value.slug, excinfo.value.status) == ("sandbox-restricted", 403)
        assert excinfo.value.detail == (
            "This file belongs to the workspace this sandbox was copied from and cannot be "
            "shredded here."
        )
    assert [
        (d["action"], d["object_type"], d["object_id"], d["outcome"], d["detail"]) for d in denials
    ] == [
        (
            "file_object.shred",
            "file_object",
            ENDPOINT,
            AuditOutcome.DENIED,
            {"reason": "DSR-1", "problem": "sandbox-restricted"},
        )
    ] * 3
    assert fake.audited == []
    production, _ = _uow(TenantKind.PRODUCTION)
    for key in (own, shared, ""):
        privacy.refuse_shared_in_sandbox(
            production, _file_row(key), action="file_object.shred", detail={"reason": "DSR-1"}
        )
    assert len(denials) == 3


# --- 05 SBX-03 rev 1.196 (item SBX-FILE-READ-1): the workspace a stored file's content names ----

THIRD = UUID(int=0xC3)  # a workspace that is neither the sandbox nor its source


def test_sbx_03_the_workspace_of_a_key_is_read_as_own_is_read() -> None:
    """``store.key_tenant`` reads the workspace that stored an object from its key, pinned
    against the function that WRITES keys as ``owns_key`` is: for every purpose the key a
    workspace writes names that workspace, and a key is a workspace's own exactly when it names
    it. If the form of a key changes, both readings fail here together."""
    for purpose in FilePurpose:
        own = store.storage_key(TENANT, purpose, DIGEST)
        assert store.key_tenant(own) == TENANT
        assert store.key_tenant(store.storage_key(SOURCE, purpose, DIGEST)) == SOURCE
        for workspace in (TENANT, SOURCE, THIRD):
            assert store.owns_key(workspace, own) is (store.key_tenant(own) == workspace)


@pytest.mark.parametrize("key", OTHER_FORMS)
def test_sbx_03_a_key_of_another_form_names_no_workspace(key: str) -> None:
    """The forms ``owns_key`` calls nobody's own name no workspace either: None, never an
    error, and never a workspace read out of a key that only resembles one."""
    assert store.key_tenant(key) is None
    assert store.content_tenant(TENANT, key, source_tenant_id=SOURCE) == TENANT


def test_sbx_03_a_row_names_its_own_workspace_or_the_source_of_its_sandbox() -> None:
    """``store.content_tenant`` — the workspace the associated data of a stored file names: the
    one that STORED the object. A row under its own key names its own workspace, whether or not
    it has a source; a copied row, under its source's key, names the source and only the
    source — without a source, or with another one, the key is nobody's the row may open. The
    rule has one direction: the source never opens its sandbox's object."""
    own = store.storage_key(TENANT, FilePurpose.ATTACHMENT, DIGEST)
    shared = store.storage_key(SOURCE, FilePurpose.ATTACHMENT, DIGEST)
    assert store.content_tenant(TENANT, own, source_tenant_id=None) == TENANT
    assert store.content_tenant(TENANT, own, source_tenant_id=SOURCE) == TENANT
    assert store.content_tenant(TENANT, shared, source_tenant_id=SOURCE) == SOURCE
    assert store.content_tenant(TENANT, shared, source_tenant_id=None) is None
    assert store.content_tenant(TENANT, shared, source_tenant_id=THIRD) is None
    assert store.content_tenant(SOURCE, own, source_tenant_id=None) is None
    assert store.content_tenant(THIRD, shared, source_tenant_id=TENANT) is None
