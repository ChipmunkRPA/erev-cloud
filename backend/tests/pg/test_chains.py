"""Hash-chain suite DG-TST-22: security events and audit events (04 T-PLT-06, T-PLT-19, DB-01,
DB-09; 05 KEY-03; BUILD_SPEC PLF-1, PLF-3)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from erev_api.adapters.keys.provider import GcpKeyProvider, LocalKeyProvider
from erev_api.adapters.secrets.store import EnvSecretStore, GcpSecretManagerStore
from erev_api.audit.verify import verify_security_event_chain, verify_tenant_chain
from erev_api.audit.writer import actor_of, build_event
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.auth.security_events import (
    CANONICAL_VERSION,
    FIRST_SECURITY_HMAC_KEY_ID,
    LEGACY_CANONICAL_VERSION,
    StaleSecurityKeyWriter,
    check_writer_admission_at_startup,
    record_security_event,
    required_security_key_ids,
    security_event_hmac,
)
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    audit_chain_head,
    audit_event,
    security_event,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.journals.subledger import verify_ledger_chain
from erev_api.enums import AuditOutcome, ControlResult, SecurityEventKind, TenantKind
from erev_api.files.store import LocalFileStore
from erev_api.uow import unit_of_work
from sqlalchemy import Connection, exc, func, insert, select, text
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.fake_gcp import ACCESSOR_PERMISSIONS, FakeKms, FakeSecretManager
from support.rows import (
    insert_audited_tenant,
    insert_ledger_parts,
    insert_ledger_rows,
    ledger_seal_values,
    subledger_line_values,
    subledger_posting_values,
)

pytestmark = pytest.mark.pg

DATA_FIX = text("SELECT set_config('app.data_fix_ticket', 'DF-TST-22', true)")
EVENTS = (
    (SecurityEventKind.LOGIN_FAILED, AuditOutcome.FAILED),
    (SecurityEventKind.LOGIN_SUCCEEDED, AuditOutcome.SUCCESS),
    (SecurityEventKind.LOGOUT, AuditOutcome.SUCCESS),
)


def _reset_security_chain(test_database: TestDatabase) -> None:
    """Empty the global chain as erev_owner with a data-fix ticket (DB-01); restart its sequence."""
    with test_database.owner_engine.begin() as connection:
        connection.execute(DATA_FIX)
        connection.exec_driver_sql("TRUNCATE erev.security_event")
        connection.exec_driver_sql("ALTER SEQUENCE erev.security_event_seq RESTART")


@pytest.fixture
def empty_security_chain(test_database: TestDatabase) -> Iterator[None]:
    """The chain is global, so the test starts from an empty one and empties it again after."""
    _reset_security_chain(test_database)
    try:
        yield
    finally:
        _reset_security_chain(test_database)


def test_dg_tst_22_security_event_chain_detects_tampering(
    test_database: TestDatabase, empty_security_chain: None, keyring: KeyRing
) -> None:
    for number, (kind, outcome) in enumerate(EVENTS, start=1):
        request_id = f"r-chain-{number}"
        with identity_session(request_id=request_id) as session:
            record_security_event(
                session,
                keyring=keyring,
                kind=kind,
                outcome=outcome,
                request_id=request_id,
                detail={"attempt": number},
            )

    with identity_session(request_id="tests-chain-verify") as session:
        rows = session.execute(
            select(
                security_event.c.chain_seq, security_event.c.prev_hmac, security_event.c.hmac
            ).order_by(security_event.c.chain_seq)
        ).all()
        verified = verify_security_event_chain(session, keyring=keyring)
    assert [row.chain_seq for row in rows] == [1, 2, 3]
    assert [row.prev_hmac for row in rows] == [None, rows[0].hmac, rows[1].hmac]
    assert (verified.result, verified.events_checked, verified.first_failure_seq) == (
        ControlResult.PASS,
        3,
        None,
    )
    assert verified.digest_last_hmac == rows[2].hmac

    with test_database.owner_engine.begin() as connection:
        connection.execute(DATA_FIX)
        connection.exec_driver_sql(
            "UPDATE erev.security_event SET detail = '{\"attempt\": 99}'::jsonb WHERE chain_seq = 2"
        )
    with identity_session(request_id="tests-chain-tampered") as session:
        tampered = verify_security_event_chain(session, keyring=keyring)
    assert (tampered.result, tampered.first_failure_seq, tampered.events_checked) == (
        ControlResult.FAIL,
        2,
        2,
    )


def _legacy_security_event(
    session: Session, keyring: KeyRing, *, kind: SecurityEventKind, request_id: str
) -> None:
    """A row as written before migration 0061: no key id, preimage form 1, signed with
    ``security-hmac:1`` (04 T-PLT-06 rev 1.42; DG-KRN-AUD-08)."""
    prev_hmac = session.execute(
        select(security_event.c.hmac).order_by(security_event.c.chain_seq.desc()).limit(1)
    ).scalar_one_or_none()
    chain_seq, occurred_at = session.execute(
        text("SELECT nextval('erev.security_event_seq'), now()")
    ).one()
    row: dict[str, object] = {
        "id": new_id(),
        "chain_seq": int(chain_seq),
        "occurred_at": occurred_at,
        "kind": kind.value,
        "outcome": AuditOutcome.SUCCESS.value,
        "user_id": None,
        "email_sha256": None,
        "session_id": None,
        "tenant_id": None,
        "ip_address": None,
        "user_agent": None,
        "request_id": request_id,
        "detail": {"legacy": True},
        "prev_hmac": prev_hmac,
        "hmac_key_id": None,
        "canonical_version": LEGACY_CANONICAL_VERSION,
    }
    row["hmac"] = security_event_hmac(
        keyring.security_event_key(FIRST_SECURITY_HMAC_KEY_ID), prev_hmac, row
    )
    session.execute(insert(security_event).values(**row))


TAMPER_DETAIL = text(
    "UPDATE erev.security_event SET detail = CAST(:detail AS jsonb) WHERE chain_seq = :seq"
)


def _synthetic_downgrade_event(session: Session, keyring: KeyRing, *, request_id: str) -> None:
    """A form-2 row signed with security-hmac:1 appended after a key-2 head by a writer outside
    the application (admission bypassed); the verifier must still reject it."""
    prev_hmac = session.execute(
        select(security_event.c.hmac).order_by(security_event.c.chain_seq.desc()).limit(1)
    ).scalar_one_or_none()
    chain_seq, occurred_at = session.execute(
        text("SELECT nextval('erev.security_event_seq'), now()")
    ).one()
    row: dict[str, object] = {
        "id": new_id(),
        "chain_seq": int(chain_seq),
        "occurred_at": occurred_at,
        "kind": SecurityEventKind.LOGOUT.value,
        "outcome": AuditOutcome.SUCCESS.value,
        "user_id": None,
        "email_sha256": None,
        "session_id": None,
        "tenant_id": None,
        "ip_address": None,
        "user_agent": None,
        "request_id": request_id,
        "detail": {"downgrade": True},
        "prev_hmac": prev_hmac,
        "hmac_key_id": FIRST_SECURITY_HMAC_KEY_ID,
        "canonical_version": CANONICAL_VERSION,
    }
    row["hmac"] = security_event_hmac(
        keyring.security_event_key(FIRST_SECURITY_HMAC_KEY_ID), prev_hmac, row
    )
    session.execute(insert(security_event).values(**row))


def _tamper_detail(test_database: TestDatabase, chain_seq: int) -> None:
    with test_database.owner_engine.begin() as connection:
        connection.execute(DATA_FIX)
        connection.execute(TAMPER_DETAIL, {"detail": '{"attempt": 99}', "seq": int(chain_seq)})


def test_p2_security_chain_verifies_across_a_key_rotation(
    test_database: TestDatabase, empty_security_chain: None, keyring: KeyRing
) -> None:
    """05 KEY-03 rev 1.17 and T-PLT-06 rev 1.42 (SPEC-Q-116 ruling): form-1 rows written before
    0061, form-2 rows under key version 1, then under version 2 after the pin moved, all verify
    under the key each row names; tampering in either segment, a backwards key version or form,
    and a verifier whose provider lacks a historical version fail closed."""
    rotated = KeyRing(LocalKeyProvider(EnvSecretStore(Settings()), security_hmac_version=2))
    assert keyring.current_security_key_id() == "security-hmac:1"
    assert rotated.current_security_key_id() == "security-hmac:2"

    with identity_session(request_id="r-legacy") as session:
        _legacy_security_event(session, keyring, kind=SecurityEventKind.LOGOUT, request_id="r-1")
        _legacy_security_event(session, keyring, kind=SecurityEventKind.LOGOUT, request_id="r-2")
    for number, signer in ((3, keyring), (4, keyring), (5, rotated), (6, rotated)):
        request_id = f"r-rotation-{number}"
        with identity_session(request_id=request_id) as session:
            record_security_event(
                session,
                keyring=signer,
                kind=SecurityEventKind.LOGIN_SUCCEEDED,
                outcome=AuditOutcome.SUCCESS,
                request_id=request_id,
                detail={"attempt": number},
            )
    with identity_session(request_id="tests-rotation-rows") as session:
        rows = session.execute(
            select(
                security_event.c.chain_seq,
                security_event.c.hmac_key_id,
                security_event.c.canonical_version,
            ).order_by(security_event.c.chain_seq)
        ).all()
    assert [(row.chain_seq, row.hmac_key_id, row.canonical_version) for row in rows] == [
        (1, None, 1),
        (2, None, 1),
        (3, "security-hmac:1", 2),
        (4, "security-hmac:1", 2),
        (5, "security-hmac:2", 2),
        (6, "security-hmac:2", 2),
    ]

    # Verification does not depend on the verifier's own pin: each row names its key.
    with identity_session(request_id="tests-rotation-verify") as session:
        for verifier in (rotated, keyring):
            result = verify_security_event_chain(session, keyring=verifier)
            assert (result.result, result.events_checked, result.first_failure_seq) == (
                ControlResult.PASS,
                6,
                None,
            )
        # P6 recovery interface: every key id a restore must serve, historical plus the pin.
        assert required_security_key_ids(session, rotated) == ["security-hmac:1", "security-hmac:2"]
        assert required_security_key_ids(session, keyring) == ["security-hmac:1", "security-hmac:2"]
        pinned_three = KeyRing(
            LocalKeyProvider(EnvSecretStore(Settings()), security_hmac_version=3)
        )
        assert required_security_key_ids(session, pinned_three) == [
            "security-hmac:1",
            "security-hmac:2",
            "security-hmac:3",
        ]
        assert required_security_key_ids(session, rotated, tenant_id=new_id()) == [
            "security-hmac:2"
        ], "no row of an unknown tenant; only the pin"

    # A provider that cannot serve version 2 fails closed at the first row naming it.
    secrets = FakeSecretManager()
    secrets.seed(
        "projects/p/secrets/erev-security-hmac",
        [(keyring.security_event_key("security-hmac:1").hex().encode(), "ENABLED")],
    )
    hosted_store = GcpSecretManagerStore(
        "p", prefix="erev-", client=secrets.client(ACCESSOR_PERMISSIONS)
    )
    without_v2 = KeyRing(GcpKeyProvider(hosted_store, kms_key="k", kms_client=FakeKms()))
    with identity_session(request_id="tests-rotation-missing") as session:
        missing = verify_security_event_chain(session, keyring=without_v2)
    assert (missing.result, missing.first_failure_seq, missing.events_checked) == (
        ControlResult.FAIL,
        5,
        5,
    )
    assert missing.failure_detail is not None
    assert "security-hmac:2" in str(missing.failure_detail["reason"])

    # Admission (Codex 76cbee4 finding): a writer still pinned at version 1 is refused BEFORE the
    # insert, under the chain lock, naming both key ids; no row and no sequence value is consumed.
    with identity_session(request_id="r-rotation-7") as session:
        with pytest.raises(StaleSecurityKeyWriter) as refused:
            record_security_event(
                session,
                keyring=keyring,
                kind=SecurityEventKind.LOGOUT,
                outcome=AuditOutcome.SUCCESS,
                request_id="r-rotation-7",
            )
        assert "security-hmac:1" in str(refused.value) and "security-hmac:2" in str(refused.value)
    with identity_session(request_id="tests-rotation-admission") as session:
        assert session.execute(select(func.count()).select_from(security_event)).scalar_one() == 6
        assert verify_security_event_chain(session, keyring=rotated).result is ControlResult.PASS
    with test_database.owner_engine.connect() as owner:  # erev_app holds USAGE, not SELECT
        last = owner.execute(text("SELECT last_value FROM erev.security_event_seq")).scalar_one()
        assert last == 6, "the refused append consumed no sequence value"
    # The startup fence refuses a stale process; the current pin passes.
    with pytest.raises(StaleSecurityKeyWriter):
        check_writer_admission_at_startup(keyring, request_id="tests-fence-stale")
    assert check_writer_admission_at_startup(rotated, request_id="tests-fence").key_id == (
        "security-hmac:2"
    )

    # A synthetic downgrade row that bypasses admission (a writer outside the application) is
    # still rejected by the verifier at the row that moves back, for a key and for a form.
    with identity_session(request_id="r-rotation-7-synthetic") as session:
        _synthetic_downgrade_event(session, keyring, request_id="r-7")
    with identity_session(request_id="tests-rotation-backwards") as session:
        backwards = verify_security_event_chain(session, keyring=rotated)
    assert (backwards.result, backwards.first_failure_seq) == (ControlResult.FAIL, 7)
    with identity_session(request_id="r-legacy-late") as session:
        _legacy_security_event(session, keyring, kind=SecurityEventKind.LOGOUT, request_id="r-8")
    with identity_session(request_id="tests-rotation-backwards-form") as session:
        late_form = verify_security_event_chain(session, keyring=rotated)
    assert (late_form.result, late_form.first_failure_seq) == (ControlResult.FAIL, 7)

    # Tampering is detected in the version-2 segment and in the legacy segment alike.
    _tamper_detail(test_database, 5)
    with identity_session(request_id="tests-rotation-tamper-v2") as session:
        tampered = verify_security_event_chain(session, keyring=rotated)
    assert (tampered.result, tampered.first_failure_seq) == (ControlResult.FAIL, 5)
    _tamper_detail(test_database, 1)
    with identity_session(request_id="tests-rotation-tamper-legacy") as session:
        tampered_legacy = verify_security_event_chain(session, keyring=rotated)
    assert (tampered_legacy.result, tampered_legacy.first_failure_seq) == (ControlResult.FAIL, 1)


def test_p6_required_security_key_ids_spans_history_and_pin(
    test_database: TestDatabase, empty_security_chain: None, keyring: KeyRing
) -> None:
    """P6 recovery interface (Codex P2/P6 integration control 2): rows under versions 1 and 3 with
    the current pin 5 give the complete inventory {1, 3, 5}; the GLOBAL chain, tenant NULL rows
    included; key ids only."""
    pinned_three = KeyRing(LocalKeyProvider(EnvSecretStore(Settings()), security_hmac_version=3))
    pinned_five = KeyRing(LocalKeyProvider(EnvSecretStore(Settings()), security_hmac_version=5))
    with identity_session(request_id="r-inventory-legacy") as session:
        _legacy_security_event(session, keyring, kind=SecurityEventKind.LOGOUT, request_id="i-1")
    with identity_session(request_id="r-inventory-3") as session:
        record_security_event(
            session,
            keyring=pinned_three,
            kind=SecurityEventKind.LOGIN_SUCCEEDED,
            outcome=AuditOutcome.SUCCESS,
            request_id="i-2",
        )
    with identity_session(request_id="tests-inventory") as session:
        assert required_security_key_ids(session, pinned_five) == [
            "security-hmac:1",
            "security-hmac:3",
            "security-hmac:5",
        ]
        assert required_security_key_ids(session, pinned_three) == [
            "security-hmac:1",
            "security-hmac:3",
        ]
        # The default pin (1 when unset locally) against a chain that ends above 1 is a forbidden
        # downgrade: the startup fence refuses before any append (P6 binds the clone pin).
        with pytest.raises(StaleSecurityKeyWriter) as refused:
            check_writer_admission_at_startup(keyring, request_id="tests-inventory-fence")
        assert "security-hmac:3" in str(refused.value) and "security-hmac:1" in str(refused.value)
        assert check_writer_admission_at_startup(pinned_five, request_id="tests-inventory-ok")
        for key_id in required_security_key_ids(session, pinned_five):
            assert len(pinned_five.security_event_key(key_id)) == 32, "every id is servable"


def _failure(bind: Session | Connection, statement: object, **params: object) -> tuple[str, str]:
    """SQLSTATE and primary message of a statement that must fail; only its savepoint rolls back."""
    savepoint = bind.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        bind.execute(statement, params)  # type: ignore[call-overload]
    savepoint.rollback()
    orig = excinfo.value.orig
    diag = getattr(orig, "diag", None)
    return str(getattr(orig, "sqlstate", None)), str(getattr(diag, "message_primary", "") or "")


@pytest.mark.control("CTL-038")
def test_ctl_038_audit_append_only_and_chain(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="r-ctl-038",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        uow.audit(
            action="tenant.update",
            object_type="tenant",
            object_id=tenant_id,
            before={"display_name": "A"},
            after={"display_name": "B"},
        )
        uow.commit()

    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Provisioning's events come first (04 §14.3); the update holds the last position.
        seq = int(session.execute(select(audit_chain_head.c.last_chain_seq)).scalar_one())
    of_tenant = {"tenant_id": tenant_id, "seq": seq}
    tamper_after = text(
        'UPDATE erev.audit_event SET after = \'{"display_name": "C"}\'::jsonb '
        "WHERE tenant_id = :tenant_id AND chain_seq = :seq"
    )
    remove = text("DELETE FROM erev.audit_event WHERE tenant_id = :tenant_id AND chain_seq = :seq")
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # erev_app holds SELECT and INSERT only (04 §14.2).
        assert _failure(session, tamper_after, **of_tenant)[0] == "42501"
        assert _failure(session, remove, **of_tenant)[0] == "42501"
        verified = verify_tenant_chain(session, tenant_id=tenant_id, keyring=keyring)
        assert (verified.result, verified.events_checked) == (ControlResult.PASS, seq)

        # DB-09: a wrong previous HMAC and an out-of-order sequence are refused.
        head = session.execute(select(audit_chain_head)).mappings().one()
        event = build_event(
            tenant_id=tenant_id,
            actor=actor_of(ctx),
            occurred_at=clock.now(),
            action="tenant.update",
            object_type="tenant",
            object_id=tenant_id,
        )
        chained = {**event, "hmac": "1" * 64, "hmac_key_id": f"audit-hmac:{tenant_id}:1"}
        wrong_prev = {**chained, "chain_seq": seq + 1, "prev_hmac": "0" * 64}
        out_of_order = {**chained, "chain_seq": seq + 2, "prev_hmac": head["last_hmac"]}
        for row in (wrong_prev, out_of_order):
            sqlstate, message = _failure(session, insert(audit_event).values(**row))
            assert sqlstate == "P0001"
            assert message.startswith("EREV-AUD-001")
        assert session.execute(select(audit_chain_head.c.last_chain_seq)).scalar_one() == seq

    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            # erev_owner is subject to FORCE RLS without a policy of its own (SPEC-Q-129).
            connection.exec_driver_sql("ALTER TABLE erev.audit_event NO FORCE ROW LEVEL SECURITY")
            for statement in (tamper_after, remove):
                sqlstate, message = _failure(connection, statement, **of_tenant)
                assert sqlstate == "P0001"
                assert message.startswith("EREV-IMM-001")
            connection.execute(DATA_FIX)
            assert connection.execute(tamper_after, of_tenant).rowcount == 1
            tampered = verify_tenant_chain(
                Session(bind=connection), tenant_id=tenant_id, keyring=keyring
            )
            assert (tampered.result, tampered.first_failure_seq, tampered.events_checked) == (
                ControlResult.FAIL,
                seq,
                seq,
            )
        finally:
            connection.rollback()


@pytest.mark.control("CTL-038")
def test_ctl_038_actor_tamper_detected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = insert_audited_tenant(keyring, events=3, at=FROZEN_AT)
    with committed_db.owner_engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE erev.audit_event NO FORCE ROW LEVEL SECURITY")
        connection.execute(DATA_FIX)
        changed = connection.execute(
            text(
                "UPDATE erev.audit_event SET actor_id = :actor_id "
                "WHERE tenant_id = :tenant_id AND chain_seq = 2"
            ),
            {"actor_id": new_id(), "tenant_id": tenant_id},
        ).rowcount
        connection.exec_driver_sql("ALTER TABLE erev.audit_event FORCE ROW LEVEL SECURITY")
    assert changed == 1

    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        tampered = verify_tenant_chain(session, tenant_id=tenant_id, keyring=keyring)
    assert (tampered.result, tampered.first_failure_seq) == (ControlResult.FAIL, 2)
    assert tampered.failure_detail == {"reason": "hmac does not match the event content"}


def test_ledger_seal_chain_verification(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-22 for ledger seals (CTR-3): the book's chain verifies seal by seal; a seal naming
    # another previous seal is refused (EREV-LED-005); after simulated tampering of a line by the
    # owner with a data-fix ticket, verification fails at that chain_seq.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        first = insert_ledger_rows(session, tenant_id)
    with tenant_session(context) as session:
        second = insert_ledger_rows(
            session, tenant_id, amounts=(Decimal("25.00"), Decimal("-25.00"))
        )
    with tenant_session(context) as session:
        verified = verify_ledger_chain(session, book_code="ASC606")
        assert (
            verified.result,
            verified.seals_checked,
            verified.first_failure_seq,
            verified.last_seal_sha256,
        ) == (ControlResult.PASS, 2, None, second.seal_sha256)
        parts = insert_ledger_parts(session, tenant_id)
        probe = session.begin_nested()
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        lines = [
            subledger_line_values(tenant_id, posting=posting, parts=parts, amount=Decimal(amount))
            for amount in ("5.00", "-5.00")
        ]
        session.execute(insert(subledger_line), lines)
        forked = ledger_seal_values(
            session, tenant_id, posting=posting, lines=lines, previous=first.seal_sha256
        )
        refused = _failure(session, insert(subledger_posting_seal).values(**forked))
        probe.rollback()
    assert refused == (
        "P0001",
        f"EREV-LED-005: the seal of posting {posting['id']} names previous seal "
        f"{first.seal_sha256}, but the ASC606 chain head is {second.seal_sha256}",
    )

    tampered_line = second.lines[1]
    with committed_db.owner_engine.begin() as connection:
        # erev_owner is subject to FORCE RLS without a policy of its own (SPEC-Q-129).
        connection.exec_driver_sql("ALTER TABLE erev.subledger_line NO FORCE ROW LEVEL SECURITY")
        connection.execute(DATA_FIX)
        changed = connection.execute(
            text(
                "UPDATE erev.subledger_line SET description = 'Adjusted by hand' "
                "WHERE tenant_id = :tenant_id AND id = :line_id"
            ),
            {"tenant_id": tenant_id, "line_id": tampered_line["id"]},
        ).rowcount
        connection.exec_driver_sql("ALTER TABLE erev.subledger_line FORCE ROW LEVEL SECURITY")
    assert changed == 1
    with tenant_session(context, read_only=True) as session:
        tampered = verify_ledger_chain(session, book_code="ASC606")
    assert (tampered.result, tampered.first_failure_seq, tampered.seals_checked) == (
        ControlResult.FAIL,
        2,
        2,
    )
    assert dict(tampered.failure_detail or {}) == {
        "reason": "seal_sha256 does not match the posting content"
    }
