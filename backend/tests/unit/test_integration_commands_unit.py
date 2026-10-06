"""DIN-12 connection commands over a fake unit of work — CPU only (Codex 0339 §3
DIN12-SANDBOX-ADMISSION-1; 05 SBX-08; REQ-PLT-022; CTL-043): in a sandbox an inbound connection is
refused on create, on activation, on a sync request and at the webhook receiver's command, each as
403 ``sandbox-restricted`` with the attempt audited DENIED in its own transaction; a CSV_GL export
connection in a sandbox and every production path are admitted. BUILD_SPEC SNP-4 (05 SBX-08
rev 1.64): the refusals go through the one guard ``domain.platform.guards.ensure_production``, and
the activation of an outbound adapter other than ``CSV_GL`` is refused by it before the DB-15
trigger, so that the attempt is audited.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.domain.integrations import commands, ports
from erev_api.domain.platform import guards
from erev_api.enums import AuditOutcome, PrincipalKind, SourceObjectType, TenantKind
from erev_api.problems import Problem
from erev_api.schemas.integrations import IntegrationConnectionIn
from erev_api.uow import UnitOfWork
from sqlalchemy.dialects import postgresql

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
TENANT = UUID(int=0xA1)
# A secret of the tenant's own namespace of the secret store (05 KEY-09 rev 1.47; R-48 (f)).
SECRET_REF = f"tenant-{TENANT}-sf-client-secret"
USER = UUID(int=0x51)
CONNECTION = UUID(int=0xC1)
JOB = UUID(int=0x0B)


class _Result:
    def __init__(self, *, rows: tuple[Any, ...] = (), scalar: Any = None) -> None:
        self._rows, self._scalar = rows, scalar

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def one(self) -> Any:
        return self._rows[0]

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def scalars(self) -> Any:
        return iter(self._rows)

    def __iter__(self) -> Any:
        return iter(self._rows)


class _Session:
    """Table-keyed answers (``FROM erev.<table>`` / ``INSERT INTO erev.<table>``); everything else
    is an empty result."""

    def __init__(self, answers: dict[str, _Result] | None = None) -> None:
        self.answers = dict(answers or {})
        self.calls: list[str] = []

    def execute(self, statement: Any, params: Any = None) -> _Result:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.calls.append(sql)
        for table, result in self.answers.items():
            if f"erev.{table}" in sql:
                return result
        return _Result()

    def scalars(self, statement: Any) -> Any:
        return iter(())


class _Uow:
    def __init__(self, kind: TenantKind, answers: dict[str, _Result] | None = None) -> None:
        self.session = _Session(answers)
        self.now = NOW
        # An Integration Admin of all entities: a connection is reached, and made to serve
        # entities, only within the caller's own scope (04 API-C-03 rev 1.243).
        self.principal = SimpleNamespace(
            id=USER,
            kind=PrincipalKind.USER,
            tenant_id=TENANT,
            permission_scopes={"integration.manage": "*"},
        )
        self.ctx = SimpleNamespace(tenant_kind=kind, principal=self.principal)
        self.keyring = object()
        self.audited: list[dict[str, Any]] = []
        self.deferred: list[tuple[Any, dict[str, Any]]] = []

    def audit(self, **kwargs: Any) -> None:
        self.audited.append(dict(kwargs))

    def defer(self, kind: Any, params: Any, **kwargs: Any) -> dict[str, Any]:
        self.deferred.append((kind, dict(params)))
        return {"id": JOB}


def _uow(kind: TenantKind, answers: dict[str, _Result] | None = None) -> tuple[UnitOfWork, _Uow]:
    fake = _Uow(kind, answers)
    return cast(UnitOfWork, fake), fake


def _connection_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "tenant_id": TENANT,
        "id": CONNECTION,
        "code": "sf-quayside",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "entity_ids": [],
        "base_url": "/api/v1/__mocks__/salesforce",
        "config": {},
        "secret_ref": SECRET_REF,
        "status": "ACTIVE",
        "checkpoint": {},
        "last_test_at": None,
        "last_test_result": None,
        "last_test_detail": None,
        "created_at": NOW,
        "created_by": USER,
        "created_by_kind": "USER",
        "updated_at": NOW,
        "updated_by": USER,
        "updated_by_kind": "USER",
        "row_version": 1,
    }
    row.update(over)
    return row


@pytest.fixture
def denials(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Captures ``audit_writer.record_now`` (the SBX-08 own-transaction denial audit), which the
    commands reach through ``guards.ensure_production`` since SNP-4."""
    seen: list[dict[str, Any]] = []

    def record_now(ctx: Any, **kwargs: Any) -> None:
        seen.append({"ctx": ctx, **kwargs})

    monkeypatch.setattr(guards.audit_writer, "record_now", record_now)
    return seen


def _body(**over: Any) -> IntegrationConnectionIn:
    values: dict[str, Any] = {
        "code": "sf-quayside",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "secret_ref": SECRET_REF,
    }
    values.update(over)
    return IntegrationConnectionIn.model_validate(values)


def test_is_inbound_by_direction_or_adapter() -> None:
    assert commands.is_inbound("SALESFORCE", "INBOUND")
    assert commands.is_inbound("STRIPE", "BOTH")
    assert commands.is_inbound("SALESFORCE", "OUTBOUND")  # a CRM adapter is inbound by nature
    assert commands.is_inbound("NETSUITE", "BOTH")
    assert not commands.is_inbound("NETSUITE", "OUTBOUND")
    assert not commands.is_inbound("CSV_GL", "OUTBOUND")


def test_sandbox_refuses_an_inbound_connection_on_create_and_audits_the_attempt(
    denials: list[dict[str, Any]],
) -> None:
    uow, fake = _uow(TenantKind.SANDBOX)
    with pytest.raises(Problem) as excinfo:
        commands.create_connection(uow, _body())
    assert excinfo.value.slug == "sandbox-restricted" and excinfo.value.status == 403
    [denial] = denials
    assert denial["outcome"] is AuditOutcome.DENIED
    assert denial["action"] == "integration_connection.create"
    assert denial["detail"]["problem"] == "sandbox-restricted"
    assert denial["detail"]["adapter"] == "SALESFORCE"
    assert denial["keyring"] is fake.keyring  # audited in its own transaction, before the raise
    assert fake.session.calls == [] and fake.audited == []  # nothing written in the unit of work


def test_sandbox_admits_a_csv_gl_export_connection(denials: list[dict[str, Any]]) -> None:
    uow, fake = _uow(TenantKind.SANDBOX)
    out = commands.create_connection(
        uow, _body(code="csv-gl", adapter="CSV_GL", direction="OUTBOUND")
    )
    assert out["status"] == "DISABLED" and out["adapter"] == "CSV_GL"
    assert denials == [] and [a["action"] for a in fake.audited] == [
        "integration_connection.create"
    ]
    assert any("INSERT INTO erev.integration_connection" in sql for sql in fake.session.calls)


def test_production_admits_an_inbound_connection(denials: list[dict[str, Any]]) -> None:
    uow, fake = _uow(TenantKind.PRODUCTION)
    out = commands.create_connection(uow, _body())
    assert out["secret_ref"] == SECRET_REF and out["status"] == "DISABLED"
    assert denials == [] and len(fake.audited) == 1


def test_sandbox_refuses_activation_of_an_inbound_connection(denials: list[dict[str, Any]]) -> None:
    row = _connection_row(status="DISABLED")
    uow, fake = _uow(TenantKind.SANDBOX, {"integration_connection": _Result(rows=(row,))})
    with pytest.raises(Problem) as excinfo:
        commands.update_connection(
            uow, CONNECTION, {"status": "ACTIVE"}, check_version=lambda v: None
        )
    assert excinfo.value.slug == "sandbox-restricted"
    [denial] = denials
    assert denial["action"] == "integration_connection.update" and denial["object_id"] == CONNECTION
    assert fake.audited == []
    # A rename of the same connection in the sandbox is not an activation: admitted.
    uow2, fake2 = _uow(TenantKind.SANDBOX, {"integration_connection": _Result(rows=(row,))})
    commands.update_connection(uow2, CONNECTION, {"name": "CRM"}, check_version=lambda v: None)
    assert len(denials) == 1 and [a["action"] for a in fake2.audited] == [
        "integration_connection.update"
    ]


def test_sandbox_refuses_activation_of_an_outbound_adapter_and_audits_it(
    denials: list[dict[str, Any]],
) -> None:
    """05 SBX-08 rev 1.64 (BUILD_SPEC SNP-4): until this line only the DB-15 trigger refused the
    activation of an outbound GL adapter in a sandbox — inside the command's transaction, so no
    DENIED event survived. The guard refuses first and audits; nothing is read after the row and
    nothing is written."""
    row = _connection_row(adapter="NETSUITE", direction="OUTBOUND", status="DISABLED")
    uow, fake = _uow(TenantKind.SANDBOX, {"integration_connection": _Result(rows=(row,))})
    with pytest.raises(Problem) as excinfo:
        commands.update_connection(
            uow, CONNECTION, {"status": "ACTIVE"}, check_version=lambda v: None
        )
    assert excinfo.value.slug == "sandbox-restricted" and excinfo.value.status == 403
    assert excinfo.value.detail == commands.SANDBOX_OUTBOUND
    [denial] = denials
    assert denial["outcome"] is AuditOutcome.DENIED
    assert denial["action"] == "integration_connection.update" and denial["object_id"] == CONNECTION
    assert denial["detail"] == {
        "status": "ACTIVE",
        "adapter": "NETSUITE",
        "direction": "OUTBOUND",
        "problem": "sandbox-restricted",
    }
    # The row was read (and locked) to learn the adapter; no statement changed it.
    assert fake.audited == []
    assert not any(sql.lstrip().startswith("UPDATE") for sql in fake.session.calls)


def test_sandbox_admits_activation_of_the_csv_gl_export_and_production_any_adapter(
    denials: list[dict[str, Any]],
) -> None:
    """The positive controls of the outbound refusal: ``CSV_GL`` is the one adapter a sandbox may
    hold ACTIVE (04 DB-15), and a production tenant activates any outbound adapter."""
    csv_gl = _connection_row(adapter="CSV_GL", direction="OUTBOUND", status="DISABLED")
    netsuite = _connection_row(adapter="NETSUITE", direction="OUTBOUND", status="DISABLED")
    for kind, row in ((TenantKind.SANDBOX, csv_gl), (TenantKind.PRODUCTION, netsuite)):
        uow, fake = _uow(kind, {"integration_connection": _Result(rows=(row,))})
        commands.update_connection(
            uow, CONNECTION, {"status": "ACTIVE"}, check_version=lambda v: None
        )
        assert [a["action"] for a in fake.audited] == ["integration_connection.update"]
        assert fake.audited[0]["after"] == {"status": "ACTIVE"}
    assert denials == []


def test_sandbox_refuses_a_sync_request_and_the_webhook_command(
    denials: list[dict[str, Any]],
) -> None:
    row = _connection_row()
    uow, fake = _uow(TenantKind.SANDBOX, {"integration_connection": _Result(rows=(row,))})
    with pytest.raises(Problem) as excinfo:
        commands.request_sync(uow, CONNECTION, kind="INBOUND_POLL")
    assert excinfo.value.slug == "sandbox-restricted" and fake.deferred == []
    notice = ports.WebhookNotice(
        verified=True,
        notifications=(
            ports.Notification("NTF-1", SourceObjectType.ORDER, "SF-ORD-Q-001", "1", 1),
        ),
    )
    uow2, fake2 = _uow(TenantKind.SANDBOX)
    with pytest.raises(Problem) as excinfo2:
        commands.receive_webhook(uow2, row, notice)
    assert excinfo2.value.slug == "sandbox-restricted" and fake2.deferred == []
    assert [d["action"] for d in denials] == ["sync_run.request", "sync_run.webhook"]


def test_production_queues_the_sync_run_and_the_webhook_batch(
    denials: list[dict[str, Any]],
) -> None:
    row = _connection_row()
    uow, fake = _uow(TenantKind.PRODUCTION, {"integration_connection": _Result(rows=(row,))})
    requested = commands.request_sync(uow, CONNECTION, kind="INBOUND_POLL")
    assert requested.job_id == JOB and requested.run["kind"] == "INBOUND_POLL"
    assert requested.run["status"] == "QUEUED" and requested.run["job_id"] == JOB
    [(kind, params)] = fake.deferred
    assert kind.value == "SYNC_RUN" and params["sync_run_id"] == str(requested.run_id)
    notice = ports.WebhookNotice(
        verified=True,
        notifications=(
            ports.Notification("NTF-1", SourceObjectType.ORDER, "SF-ORD-Q-001", "1", 1),
        ),
    )
    batch = commands.receive_webhook(uow, row, notice)
    assert batch.run["kind"] == "WEBHOOK_BATCH"
    assert fake.deferred[1][1]["notifications"][0]["notification_id"] == "NTF-1"
    assert denials == []


def test_receive_webhook_requires_a_verified_notice() -> None:
    uow, _ = _uow(TenantKind.PRODUCTION)
    with pytest.raises(ValueError):
        commands.receive_webhook(uow, _connection_row(), ports.WebhookNotice(verified=False))


# --- base_url: the static form of 05 SAR-15 at save (04 T-INT-01 rev 1.115; ruling R-45 (c)) ------

PUBLIC_URLS = (
    "https://acme.my.salesforce.com",
    "https://api.stripe.com/",
    "https://4411.suitetalk.api.netsuite.com:443/services/rest",
    "https://8.8.8.8/v1",
    "HTTPS://Acme.Example.COM/path?x=1",
    "https://xn--bcher-kva.example/api",
    "https://tstdrv4411-sb1.suitetalk.api.netsuite.com",
    "https://api.example.com./v1",
)
# ``127.0.0.1`` in full-width digits and ``example`` with a full-width dot: a resolver's name
# mapping folds them into ASCII (the first into an address); kept out of the source as literals.
FULL_WIDTH_LOOPBACK = "".join(chr(0xFF10 + int(c)) if c.isdigit() else c for c in "127.0.0.1")
FULL_WIDTH_DOT = f"api{chr(0xFF0E)}example{chr(0x3002)}com"
NOT_A_DNS_NAME = "its host is not a DNS name"
OTHER_FORM = "a form other than dotted decimal"
REFUSED_URLS = (
    ("http://acme.my.salesforce.com", "it does not use https"),
    ("/api/v1/__mocks__/salesforce", "it does not use https"),
    ("ftp://files.example.com", "it does not use https"),
    ("https://", "it names no host"),
    ("https://user:pw@api.example.com/x", "it carries credentials"),
    ("https://api.example.com:99999/x", "it is not a URL"),
    ("https://localhost/x", "it names a local host"),
    ("https://LOCALHOST./x", "it names a local host"),
    ("https://erp.localhost", "it names a local host"),
    ("https://printer.local/ipp", "it names a local host"),
    ("https://netsuite.corp.internal", "it names a local host"),
    ("https://intranet/api", "it names a single-label host"),
    ("https://127.0.0.1:8190/api/v1/__mocks__/stripe", "non-public address"),
    ("https://10.0.0.8", "non-public address"),
    ("https://172.16.4.4", "non-public address"),
    ("https://192.168.1.1", "non-public address"),
    ("https://169.254.169.254/latest/meta-data", "non-public address"),
    ("https://100.64.0.1", "non-public address"),
    ("https://0.0.0.0", "non-public address"),
    ("https://[::1]/x", "non-public address"),
    ("https://[fe80::1]/x", "non-public address"),
    ("https://[fd00::8]/x", "non-public address"),
    ("https://[::ffff:10.0.0.8]/x", "non-public address"),
    ("https://224.0.0.1", "non-public address"),
    # an address written the other ways a resolver reads one: refused, never interpreted
    ("https://127.1/x", OTHER_FORM),
    ("https://0x7f.0.0.1/x", OTHER_FORM),
    ("https://10.0.513/x", OTHER_FORM),
    ("https://0177.0.0.01/x", OTHER_FORM),
    ("https://erp.example.0x10/x", OTHER_FORM),
    ("https://2130706433/x", "it names a single-label host"),
    (f"https://{FULL_WIDTH_LOOPBACK}/x", NOT_A_DNS_NAME),
    (f"https://{FULL_WIDTH_DOT}/x", NOT_A_DNS_NAME),
    ("https://127.0.0.1\\.example.com/x", NOT_A_DNS_NAME),
    ("https://api.example.com%2e/x", NOT_A_DNS_NAME),
    ("https://api example.com/x", NOT_A_DNS_NAME),
    ("https://[fe80::1%25eth0]/x", "non-public address"),
    ("https://example.com@10.0.0.8/x", "it carries credentials"),
)


def test_base_url_static_rule_admits_public_https_and_names_every_refusal() -> None:
    """05 SAR-15 in its static form: ``https``, no credentials, a host that is neither a literal
    non-global address nor a local or single-label name. Nothing is resolved."""
    for url in PUBLIC_URLS:
        assert commands.base_url_refusal(url) is None, url
    for url, reason in REFUSED_URLS:
        found = commands.base_url_refusal(url)
        assert found is not None and reason in found, (url, found)


def test_create_and_update_hold_base_url_to_the_static_rule_unless_the_deployment_is_local(
    denials: list[dict[str, Any]],
) -> None:
    """04 T-INT-01 rev 1.115: a caller that does not say the deployment is ``dev``, ``test`` or
    ``e2e`` gets the production rule — a mock path or a private address is 422 naming
    ``base_url`` and nothing is written; a local deployment keeps the mock URLs; a public https
    address passes everywhere; no ``base_url`` is no finding."""
    mock_url = "/api/v1/__mocks__/salesforce"
    uow, fake = _uow(TenantKind.PRODUCTION)
    with pytest.raises(Problem) as refused:
        commands.create_connection(uow, _body(base_url=mock_url))
    assert refused.value.slug == "validation-failed" and refused.value.status == 422
    [error] = refused.value.errors
    assert (error.field, error.rule_id) == ("base_url", "T-INT-01")
    assert error.message == ("Enter a public https address as the base URL: it does not use https.")
    assert fake.audited == [] and not any("INSERT" in sql for sql in fake.session.calls)

    local, local_fake = _uow(TenantKind.PRODUCTION)
    created = commands.create_connection(local, _body(base_url=mock_url), local_destinations=True)
    assert created["base_url"] == mock_url and len(local_fake.audited) == 1
    public, public_fake = _uow(TenantKind.PRODUCTION)
    out = commands.create_connection(public, _body(base_url="https://acme.my.salesforce.com"))
    assert out["base_url"] == "https://acme.my.salesforce.com" and len(public_fake.audited) == 1
    assert denials == []

    row = _connection_row(status="DISABLED", base_url="https://acme.my.salesforce.com")
    stored = {"integration_connection": _Result(rows=(row,))}
    for url in ("https://10.0.0.8/services", "http://acme.my.salesforce.com", mock_url):
        uow2, fake2 = _uow(TenantKind.PRODUCTION, dict(stored))
        with pytest.raises(Problem) as changed:
            commands.update_connection(
                uow2, CONNECTION, {"base_url": url}, check_version=lambda v: None
            )
        assert [e.field for e in changed.value.errors] == ["base_url"], url
        assert fake2.audited == []
    # a change that does not send ``base_url`` is not re-judged: a stored mock URL may be renamed
    legacy = {"integration_connection": _Result(rows=(_connection_row(status="DISABLED"),))}
    uow3, fake3 = _uow(TenantKind.PRODUCTION, legacy)
    commands.update_connection(uow3, CONNECTION, {"name": "CRM"}, check_version=lambda v: None)
    assert [a["action"] for a in fake3.audited] == ["integration_connection.update"]


def test_routes_admit_mock_urls_in_local_deployments_only() -> None:
    """The route says whether the deployment is local: ``dev``, ``test`` and ``e2e`` are,
    ``production`` is not (05 SAR-15)."""
    from erev_api.api.deps import KernelDeps
    from erev_api.api.v1 import integrations as routes
    from erev_api.config import Environment

    def deps(env: Environment) -> KernelDeps:
        settings: Any = SimpleNamespace(env=env)
        return KernelDeps(
            settings=settings, clock=cast(Any, None), keyring=cast(Any, None), files=cast(Any, None)
        )

    assert [routes._local(deps(env)) for env in Environment] == [True, True, True, False]
    assert [env.value for env in Environment] == ["dev", "test", "e2e", "production"]
