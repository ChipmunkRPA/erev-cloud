"""Audit writer and chain DG-KRN-AUD-02 to 06, DG-KRN-AUTH-05 (dev-guide §5.5; BUILD_SPEC PLF-3)."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.audit.chain import canonical_event, compute_hmac
from erev_api.audit.verify import verify_tenant_chain
from erev_api.audit.writer import record, record_denied, record_facts
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_chain_head, audit_event
from erev_api.enums import ControlResult, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.uow import UnitOfWork, unit_of_work
from erev_engine.canonical import sha256_hex
from sqlalchemy import select
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of


@pytest.fixture
def tenant(committed_db: TestDatabase, keyring: KeyRing) -> UUID:
    """A fresh tenant; provisioning wrote event 1 ``tenant.provision``."""
    return tenant_id_of(tenant_factory(keyring=keyring))


def _context(tenant_id: UUID, clock: FrozenClock) -> RequestContext:
    return RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-audit-writer",
        source_ip="192.0.2.10",
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )


@contextmanager
def _uow(
    tenant_id: UUID, clock: FrozenClock, keyring: KeyRing, settings: Settings
) -> Iterator[UnitOfWork]:
    with unit_of_work(
        _context(tenant_id, clock),
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(settings.file_root),
    ) as uow:
        yield uow


def _scope(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _events(tenant_id: UUID) -> list[Mapping[str, Any]]:
    with tenant_session(_scope(tenant_id)) as session:
        return list(
            session.execute(select(audit_event).order_by(audit_event.c.chain_seq)).mappings()
        )


def _head(tenant_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_scope(tenant_id)) as session:
        return session.execute(select(audit_chain_head)).mappings().one()


def test_krn_aud_02_flush_chains_in_buffer_order(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    # Provisioning writes tenant.provision and the bootstrap admin grant events (04 §14.3).
    base = len(_events(tenant))
    with _uow(tenant, clock, keyring, app_settings) as uow:
        uow.audit(
            action="tenant.update",
            object_type="tenant",
            object_id=tenant,
            before={"display_name": "A"},
            after={"display_name": "B"},
        )
        uow.audit(action="tenant.complete_setup", object_type="tenant", object_id=tenant)
        assert [event["action"] for event in uow.audit_events] == [
            "tenant.update",
            "tenant.complete_setup",
        ]
        uow.commit()

    events = _events(tenant)
    assert events[0]["action"] == "tenant.provision"
    assert [(event["chain_seq"], event["action"]) for event in events[base - 1 :]] == [
        (base, events[base - 1]["action"]),
        (base + 1, "tenant.update"),
        (base + 2, "tenant.complete_setup"),
    ]
    updated, completed = events[base], events[base + 1]
    assert updated["prev_hmac"] == events[base - 1]["hmac"]
    assert completed["prev_hmac"] == updated["hmac"]
    assert updated["occurred_at"] == clock.now()
    assert (updated["actor_kind"], updated["auth_method"], updated["request_id"]) == (
        "SYSTEM",
        "system",
        "r-audit-writer",
    )
    assert str(updated["source_ip"]) == "192.0.2.10"
    head = _head(tenant)
    assert (head["last_chain_seq"], head["last_hmac"]) == (base + 2, completed["hmac"])

    # A unit of work without buffered events writes nothing.
    with _uow(tenant, clock, keyring, app_settings) as uow:
        uow.commit()
    assert len(_events(tenant)) == base + 2
    assert _head(tenant) == head

    with tenant_session(_scope(tenant)) as session:
        verified = verify_tenant_chain(session, tenant_id=tenant, keyring=keyring)
        tail = verify_tenant_chain(session, tenant_id=tenant, keyring=keyring, from_seq=base + 1)
    assert (verified.result, verified.events_checked, verified.digest_last_hmac) == (
        ControlResult.PASS,
        base + 2,
        completed["hmac"],
    )
    assert (tail.result, tail.from_chain_seq, tail.to_chain_seq, tail.events_checked) == (
        ControlResult.PASS,
        base + 1,
        base + 2,
        2,
    )


def test_krn_aud_03_hmac_construction() -> None:
    tenant_id = UUID("0191e0a0-0000-7000-8000-0000000000a1")
    row: dict[str, Any] = {name: None for name in audit_event.c.keys()}
    row.update(
        tenant_id=tenant_id,
        occurred_at=datetime(2026, 9, 12, 12, 0, 0, 123456, tzinfo=UTC),
        id=UUID("0191e0a0-0000-7000-8000-0000000000a2"),
        chain_seq=2,
        actor_kind="SYSTEM",
        actor_roles=[],
        request_id="r-hmac",
        action="tenant.update",
        object_type="tenant",
        outcome="SUCCESS",
        detail={"b": 1, "a": "x"},
        prev_hmac="ab" * 32,
        hmac="ff" * 32,
        hmac_key_id=f"audit-hmac:{tenant_id}:1",
    )
    key = b"k" * 32
    expected = hmac.new(key, ("ab" * 32).encode("ascii") + canonical_event(row), "sha256")
    assert compute_hmac(key, "ab" * 32, row) == expected.hexdigest()
    assert compute_hmac(key, None, row) == hmac.new(key, canonical_event(row), "sha256").hexdigest()
    # Every column except hmac is covered.
    assert canonical_event({**row, "hmac": "00" * 32}) == canonical_event(row)
    assert canonical_event({**row, "request_id": "r-other"}) != canonical_event(row)
    assert b'"detail":{"a":"x","b":1}' in canonical_event(row)


def _changed(name: str, value: Any) -> Any:
    """Another value of the column's type."""
    if name == "source_ip":
        return "192.0.2.11"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, UUID):
        return UUID(int=value.int + 1)
    if isinstance(value, datetime):
        return value.replace(microsecond=value.microsecond + 1)
    if isinstance(value, list):
        return [*value, {"path": "extra"}]
    if isinstance(value, dict):
        return {**value, "extra": 1}
    assert isinstance(value, str), name
    return "cd" * 32 if name in {"prev_hmac", "hmac"} else value + "x"


def test_krn_aud_03_hmac_covers_every_column() -> None:
    tenant_id = UUID("0191e0a0-0000-7000-8000-0000000000b1")
    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "occurred_at": datetime(2026, 9, 12, 12, 0, 0, 123456, tzinfo=UTC),
        "id": UUID("0191e0a0-0000-7000-8000-0000000000b2"),
        "chain_seq": 2,
        "actor_id": UUID("0191e0a0-0000-7000-8000-0000000000b3"),
        "actor_kind": "USER",
        "actor_roles": ["tenant_admin"],
        "auth_method": "password",
        "mfa_verified": True,
        "on_behalf_of_id": UUID("0191e0a0-0000-7000-8000-0000000000b4"),
        "api_client_id": UUID("0191e0a0-0000-7000-8000-0000000000b5"),
        "support_grant_id": UUID("0191e0a0-0000-7000-8000-0000000000b6"),
        "source_ip": "192.0.2.10",
        "request_id": "r-hmac-columns",
        "action": "tenant.update",
        "object_type": "tenant",
        "object_id": UUID("0191e0a0-0000-7000-8000-0000000000b7"),
        "object_version": "r3",
        "before": {"display_name": "A"},
        "after": {"display_name": "B"},
        "diff": [{"path": "display_name", "before": "A", "after": "B"}],
        "reason_code": "CORRECTION",
        "comment": "Corrected the workspace name",
        "approval_request_id": UUID("0191e0a0-0000-7000-8000-0000000000b8"),
        "outcome": "SUCCESS",
        "detail": {"a": "x"},
        "prev_hmac": "ab" * 32,
        "hmac": "ff" * 32,
        "hmac_key_id": f"audit-hmac:{tenant_id}:1",
    }
    assert set(row) == set(audit_event.c.keys())
    canonical = canonical_event(row)
    for name in audit_event.c.keys():
        changed = canonical_event({**row, name: _changed(name, row[name])})
        if name == "hmac":
            assert changed == canonical
        else:
            assert changed != canonical, name


def test_krn_aud_05_diff_and_redaction(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    with _uow(tenant, clock, keyring, app_settings) as uow:
        record(
            uow,
            action="tenant.update",
            object_type="tenant",
            object_id=tenant,
            before={"display_name": "A", "password_hash": "x"},
            after={"display_name": "B", "password_hash": "y"},
        )
        record(
            uow,
            action="identity_provider.update",
            object_type="identity_provider",
            object_id=None,
            before={"config": {"client": {"secret": "s-1", "label": "Old"}}},
            after={"config": {"client": {"secret": "s-2", "label": "New"}}},
        )
        uow.commit()
    flat, nested = _events(tenant)[-2:]
    assert flat["diff"] == [{"path": "display_name", "before": "A", "after": "B"}]
    assert flat["before"] == {"display_name": "A", "password_hash": "[REDACTED]"}
    assert flat["after"] == {"display_name": "B", "password_hash": "[REDACTED]"}
    assert nested["before"] == {"config": {"client": {"secret": "[REDACTED]", "label": "Old"}}}
    assert nested["after"] == {"config": {"client": {"secret": "[REDACTED]", "label": "New"}}}
    assert nested["diff"] == [{"path": "config.client.label", "before": "Old", "after": "New"}]


def test_krn_aud_06_personal_fields_pseudonymised(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    with _uow(tenant, clock, keyring, app_settings) as uow:
        uow.audit(
            action="app_user.update",
            object_type="app_user",
            object_id=None,
            before={"email": "old@acme.test"},
            after={"email": "maya@acme.test"},
        )
        uow.commit()
    event = _events(tenant)[-1]
    key = keyring.tenant_audit_key(event["hmac_key_id"])
    pseudonym = {
        "hmac": hmac.new(key, b"maya@acme.test", hashlib.sha256).hexdigest(),
        "length": 14,
    }
    assert event["after"] == {"email": pseudonym}
    assert event["diff"][0]["after"] == pseudonym
    assert "maya@acme.test" not in str(event["before"]) + str(event["after"]) + str(event["diff"])
    with tenant_session(_scope(tenant)) as session:
        assert verify_tenant_chain(session, tenant_id=tenant, keyring=keyring).result is (
            ControlResult.PASS
        )


def test_krn_aud_05_record_facts_above_100_ids(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    many = [UUID(int=number) for number in range(101, 0, -1)]
    few = many[:3]
    # A stream append is a contract's fact: it names the contract (04 T-PLT-19, rev 1.154).
    stream = UUID(int=7_000)
    fact = {"action": "contract_event.submit", "object_type": "contract_event"}
    with _uow(tenant, clock, keyring, app_settings) as uow:
        record_facts(uow, **fact, ids=many, contract_id=stream)
        record_facts(uow, **fact, ids=few, contract_id=stream)
        uow.commit()
    summary, listed = _events(tenant)[-2:]
    ordered = sorted(str(value) for value in many)
    assert summary["detail"] == {
        "count": 101,
        "first_id": ordered[0],
        "last_id": ordered[-1],
        "ids_sha256": sha256_hex(ordered),
        "contract_id": str(stream),
    }
    assert summary["object_id"] is None
    assert listed["detail"] == {
        "ids": sorted(str(value) for value in few),
        "contract_id": str(stream),
    }


def test_krn_aud_04_action_pattern(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    with _uow(tenant, clock, keyring, app_settings) as uow:
        with pytest.raises(ValueError, match="must match"):
            record(uow, action="Contract.Book", object_type="contract", object_id=None)
        assert uow.audit_events == ()


def test_krn_auth_05_denied_command_audited(
    tenant: UUID, clock: FrozenClock, keyring: KeyRing, app_settings: Settings
) -> None:
    base = len(_events(tenant))
    with pytest.raises(RuntimeError, match="business transaction failed"):
        with _uow(tenant, clock, keyring, app_settings) as uow:
            uow.audit(
                action="role_assignment.create", object_type="role_assignment", object_id=None
            )
            record_denied(
                uow.ctx,
                action="role_assignment.create",
                object_type="role_assignment",
                object_id=None,
                permission="role.manage",
            )
            raise RuntimeError("business transaction failed")

    events = _events(tenant)
    # The DENIED event directly follows provisioning's last event; the business event rolled back.
    assert [(event["chain_seq"], event["outcome"]) for event in events[base - 1 :]] == [
        (base, "SUCCESS"),
        (base + 1, "DENIED"),
    ]
    denied = events[base]
    assert (denied["action"], denied["object_type"], denied["detail"]) == (
        "role_assignment.create",
        "role_assignment",
        {"permission": "role.manage"},
    )
    with tenant_session(_scope(tenant)) as session:
        assert verify_tenant_chain(session, tenant_id=tenant, keyring=keyring).result is (
            ControlResult.PASS
        )
