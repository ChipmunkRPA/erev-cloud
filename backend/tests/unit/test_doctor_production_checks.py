"""05 SAR-40 production checks of ``erev doctor`` (BUILD_SPEC SOP-6; dev-guide DG-MK-doctor;
runbook RB-03 "Production checks (05 SAR-40)"), as pure predicates over injected observations.

No database: every observation is seeded. Each predicate is shown failing on a bad observation and
passing on the good one. The command wiring, the database collectors (connections, partitions),
the key-provider probe and REL-07 are later SOP-6 phases (lane record P4-doctor).
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from erev_api.config import Environment, Settings, settings_override
from erev_api.controls import doctor
from erev_api.controls.doctor import (
    ANTHROPIC_KEY,
    BACKUP_URL_NAME,
    CORS_ORIGINS,
    DEFUSEDXML,
    EMAIL_BACKEND,
    INDEX_CONDITIONS,
    INTEGRATION_URLS,
    KEY_PROVIDER,
    KEY_VERSION_PIN,
    LOCK_BUDGET,
    MASTER_KEYS,
    OPERATOR_ALERTS,
    PARTITION_WINDOW,
    PENDING_INTEGRATION_TABLE,
    PENDING_KEY_ID_ACCESSOR,
    PENDING_REASONS,
    PRODUCTION_CHECK_NAMES,
    RECOVERY_PROVIDER,
    RECOVERY_PROVIDER_NAME,
    RELEASE_STAMP,
    RESTORE_ADMIN_URL_NAME,
    SECURITY_HMAC_SECRET_VERSION_NAME,
    SESSION_COOKIE,
    CheckResult,
    CollectorPending,
    IndexConditionsObservation,
    IntegrationConnectionObservation,
    LockBudgetObservation,
    PartitionWindowObservation,
    ProductionObservations,
    Provenance,
    ProviderObservation,
    ReleaseObservation,
    SettingsSnapshot,
    collect_production_observations,
    observe_anthropic_key,
    observe_defusedxml,
    observe_index_conditions,
    observe_integration_connections,
    observe_key_provider,
    observe_lock_budget,
    observe_partition_windows,
    observe_release,
    partition_upper_bound,
    private_url_reason,
    production_checks,
    production_collector,
    run_doctor,
    snapshot_settings,
)
from erev_api.db import tables as db_tables
from erev_api.db.migration_ops import code_head
from erev_engine import ENGINE_VERSION
from support.clock import frozen_clock
from support.operators import invoke, operator_services

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
BUILD_SHA = "0123456789abcdef0123456789abcdef01234567"
KEK = "projects/erev-prod/locations/us/keyRings/erev/cryptoKeys/erev-app-kek"
SALESFORCE = IntegrationConnectionObservation(
    tenant_code="acme", code="sf-prod", status="ACTIVE", base_url="https://acme.my.salesforce.com"
)
DISABLED_MOCK = IntegrationConnectionObservation(
    tenant_code="acme", code="ns-mock", status="DISABLED", base_url="http://127.0.0.1:8190"
)
ACTIVE_MOCK = IntegrationConnectionObservation(
    tenant_code="acme", code="ns-mock", status="ACTIVE", base_url="http://127.0.0.1:8190"
)
NO_URL = IntegrationConnectionObservation(
    tenant_code="acme", code="stripe", status="ACTIVE", base_url=None
)
TABLES = ("audit_event", "schedule_line", "subledger_line")
WINDOWS = tuple(PartitionWindowObservation(table, date(2033, 1, 1)) for table in TABLES)
RELEASE = ReleaseObservation(manifest_present=True, build_sha=BUILD_SHA, error=None)
PROVIDER = ProviderObservation(
    kind="gcp", identity=KEK, healthy=True, security_hmac_key_id="security-hmac:3"
)
# 05 §2.7 lock budget at revision 0072: 3,094 partition locks (audit_event 1,092, schedule_line
# 910, subledger_line 1,092) and 5,044 relations. LOCKS is the hosted shape (the Terraform
# defaults), COMPOSE_LOCKS the compose server, DEFAULT_LOCKS a server left at PostgreSQL's defaults.
FOOTPRINT, RELATIONS = 3094, 5044
LOCKS = LockBudgetObservation(4096, 600, 0, FOOTPRINT, RELATIONS)
COMPOSE_LOCKS = LockBudgetObservation(4096, 100, 0, FOOTPRINT, RELATIONS)
DEFAULT_LOCKS = LockBudgetObservation(64, 100, 0, FOOTPRINT, RELATIONS)
# 05 §2.7 index conditions (SAR-40 rev 1.156): what the catalogue check answers on a schema
# as the revisions build it - no finding - and its two kinds of finding as text. LISTED stands
# for the length of the check's list; the collector's test reads the real one.
LISTED = 30
INDEX_KEYS = IndexConditionsObservation(findings=(), listed=LISTED)
BY_HAND = (
    "tenant_membership.ix_tenant_membership__by_hand: nothing but the tenant stands in front of "
    "status, whose comparison is not leakproof: the index is entered by the tenant alone"
)
NOT_AS_LISTED = (
    "-.ix_contract__status: listed in ALLOWED, but its key has no finding: remove the entry"
)
PLACEHOLDER_KEY = (
    "EREV_ENCRYPTION_KEY is a placeholder, not a generated key: fewer than 16 distinct byte "
    "values (05 CFG-26)"
)
INVALID_PIN = (
    f"{SECURITY_HMAC_SECRET_VERSION_NAME} must be a positive integer version number of at most 7 "
    "ASCII digits"
)
UNVERIFIED_PIN = (
    "the provider's current security-hmac key id was not collected; "
    f"{SECURITY_HMAC_SECRET_VERSION_NAME}=3 is not verified (05 KEY-03, SAR-40)"
)
MASTER_KEYS_FIXTURE = {
    "EREV_ENCRYPTION_KEY": "0123456789abcdef" * 4,
    "EREV_AUDIT_HMAC_MASTER_KEY": "fedcba9876543210" * 4,
    "EREV_SECURITY_EVENT_HMAC_KEY": "13579bdf02468ace" * 4,
}
# A hosted production process. The platform injects the app database URL from a pinned Secret
# Manager version into the environment (DG-ENV-10 as ruled for lane P2; cloud_run.tf
# secret_key_ref), so Settings requires it; the owner URL is never held by the api or worker.
# The value is a fixture placeholder, not a credential.
PRODUCTION_ENVIRONMENT = {
    **MASTER_KEYS_FIXTURE,
    "EREV_ENV": "production",
    "EREV_KEY_PROVIDER": "gcp",
    "EREV_GCP_PROJECT": "erev-prod",
    "EREV_GCP_KMS_KEK": KEK,
    "EREV_EMAIL_BACKEND": "smtp",
    # 05 CFG-18: the smtp backend names its relay and its sender (SAR-40 rev 1.53).
    "EREV_SMTP_HOST": "smtp.erev.example",
    "EREV_SMTP_FROM": "erev@erev.example",
    "EREV_PUBLIC_ORIGIN": "https://app.erev.example",
    "EREV_CORS_ORIGINS": "https://app.erev.example, https://*.erev.example",
    # Required by lane P2's Settings under production; ignored by a build without the field.
    "EREV_SECURITY_HMAC_SECRET_VERSION": "3",
    "EREV_DB_APP_URL": "postgresql://erev_app:fixture-placeholder@127.0.0.1:5432/erev_fixture",
}


def snapshot(**overrides: object) -> SettingsSnapshot:
    """A healthy hosted production snapshot (gcp key provider, MANAGED recovery)."""
    values: dict[str, object] = {
        "env": Environment.PRODUCTION,
        "email_backend": "smtp",
        "cors_origins": ("https://app.erev.example",),
        "public_origin": "https://app.erev.example",
        "ai_provider": "fake",
        "anthropic_api_key_set": False,
        "key_provider": "gcp",
        "gcp_project_set": True,
        "gcp_kms_kek_set": True,
        "security_hmac_secret_version": "3",
        "recovery_provider": "MANAGED",
        "backup_url_set": False,
        "restore_admin_url_set": False,
        "undefined": frozenset(),
        "operator_alert_email_set": True,
        "operator_alert_delivery": None,
        "smtp_host_set": True,
        "smtp_from_set": True,
        "master_key_findings": (),
    }
    values.update(overrides)
    return SettingsSnapshot(**values)  # type: ignore[arg-type]


def compose_snapshot(**overrides: object) -> SettingsSnapshot:
    """A healthy compose-shaped production snapshot: the local key provider, which uses the
    CFG-26 master keys, with the NATIVE recovery configuration it implies (D-95)."""
    values: dict[str, object] = {
        "key_provider": "local",
        "gcp_project_set": False,
        "gcp_kms_kek_set": False,
        "recovery_provider": "NATIVE",
        "backup_url_set": True,
        "restore_admin_url_set": True,
    }
    values.update(overrides)
    return snapshot(**values)


def observations(**overrides: object) -> ProductionObservations:
    values: dict[str, object] = {
        "settings": snapshot(),
        "defusedxml": True,
        "anthropic_key_resolves": None,
        "integration_connections": (SALESFORCE, DISABLED_MOCK, NO_URL),
        "partition_windows": WINDOWS,
        "release": RELEASE,
        "provider": PROVIDER,
        "lock_budget": LOCKS,
        "index_conditions": INDEX_KEYS,
    }
    values.update(overrides)
    return ProductionObservations(**values)  # type: ignore[arg-type]


def _by_check(results: Iterable[CheckResult]) -> dict[str, CheckResult]:
    return {result.check: result for result in results}


def _failing(results: Iterable[CheckResult]) -> list[str]:
    return [result.check for result in results if not result.ok]


def _run(seeded: ProductionObservations) -> dict[str, CheckResult]:
    return _by_check(production_checks(seeded, now=NOW))


def _windows(**ends_on: date | None) -> tuple[PartitionWindowObservation, ...]:
    return tuple(
        PartitionWindowObservation(table, ends_on.get(table, date(2033, 1, 1))) for table in TABLES
    )


@pytest.fixture
def production_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    for name, value in PRODUCTION_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_sar_40_production_checks() -> None:
    """Under production each SAR-40 condition fails exactly its named check; the good
    observations pass every check; the Anthropic case warns without failing."""
    good = production_checks(observations(), now=NOW)
    assert [result.check for result in good] == list(PRODUCTION_CHECK_NAMES)
    assert all(result.ok and not result.warnings for result in good), [r.lines() for r in good]
    assert all(result.lines() == [f"OK {result.check}: {result.summary}"] for result in good)

    seeded = {
        EMAIL_BACKEND: observations(settings=snapshot(email_backend="fake")),
        INTEGRATION_URLS: observations(integration_connections=(SALESFORCE, ACTIVE_MOCK)),
        CORS_ORIGINS: observations(
            settings=snapshot(cors_origins=("https://app.erev.example", "*"))
        ),
        SESSION_COOKIE: observations(settings=snapshot(public_origin="http://127.0.0.1:5270")),
        DEFUSEDXML: observations(defusedxml=False),
        PARTITION_WINDOW: observations(partition_windows=_windows(subledger_line=date(2027, 6, 1))),
        OPERATOR_ALERTS: observations(settings=snapshot(operator_alert_email_set=False)),
        LOCK_BUDGET: observations(lock_budget=DEFAULT_LOCKS),
        MASTER_KEYS: observations(
            settings=compose_snapshot(master_key_findings=(PLACEHOLDER_KEY,))
        ),
    }
    for check, bad in seeded.items():
        results = production_checks(bad, now=NOW)
        assert _failing(results) == [check], (check, [r.lines() for r in results if not r.ok])
        failing = _by_check(results)[check]
        assert failing.lines() == [f"FAIL {check}: {finding}" for finding in failing.failures]
        assert failing.failures, check

    anthropic = observations(
        settings=snapshot(ai_provider="anthropic"), anthropic_key_resolves=False
    )
    warned = production_checks(anthropic, now=NOW)
    assert _failing(warned) == []
    warning = _by_check(warned)[ANTHROPIC_KEY]
    assert warning.ok and len(warning.warnings) == 1
    assert warning.lines() == [f"WARN {ANTHROPIC_KEY}: {warning.warnings[0]}"]
    assert "ANTHROPIC_API_KEY" in warning.warnings[0] and "KEY-10" in warning.warnings[0]
    resolved = observations(settings=snapshot(ai_provider="anthropic"), anthropic_key_resolves=True)
    assert _run(resolved)[ANTHROPIC_KEY].lines() == [
        f"OK {ANTHROPIC_KEY}: EREV_AI_PROVIDER is anthropic and ANTHROPIC_API_KEY resolves"
    ]
    # Without a probe result the predicate falls back to the settings snapshot.
    unset = observations(settings=snapshot(ai_provider="anthropic", anthropic_api_key_set=False))
    assert _run(unset)[ANTHROPIC_KEY].warnings
    present = observations(settings=snapshot(ai_provider="anthropic", anthropic_api_key_set=True))
    assert not _run(present)[ANTHROPIC_KEY].warnings


def test_findings_name_the_offending_object() -> None:
    urls = _run(observations(integration_connections=(ACTIVE_MOCK, NO_URL)))[INTEGRATION_URLS]
    assert urls.failures == (
        "connection ns-mock of tenant acme: base URL host 127.0.0.1 is a loopback address "
        "(05 SAR-40)",
    )
    ok_urls = _run(observations())[INTEGRATION_URLS]
    assert ok_urls.summary == "2 active integration connections have public or no base URLs"

    window = _run(observations(partition_windows=_windows(subledger_line=date(2027, 6, 1))))
    assert window[PARTITION_WINDOW].failures == (
        "partition window of subledger_line ends 2027-06-01, within 12 months of 2026-09-19 "
        "(04 §1.6 rule 2)",
    )
    # Boundary: a window ending on the horizon fails; one day later passes.
    at_horizon = _run(observations(partition_windows=_windows(audit_event=date(2027, 9, 19))))
    assert _failing(at_horizon.values()) == [PARTITION_WINDOW]
    past_horizon = _run(observations(partition_windows=_windows(audit_event=date(2027, 9, 20))))
    assert _failing(past_horizon.values()) == []
    assert past_horizon[PARTITION_WINDOW].summary == (
        "every partition window ends after 2027-09-19 (earliest 2027-09-20)"
    )
    missing = _run(observations(partition_windows=WINDOWS[:2]))[PARTITION_WINDOW]
    assert missing.failures == ("table subledger_line has no partition window observation",)
    unbounded = _run(observations(partition_windows=_windows(subledger_line=None)))
    assert unbounded[PARTITION_WINDOW].failures == (
        "table subledger_line has no bounded partition (04 §1.6 rule 1)",
    )

    loopback = _run(observations(settings=snapshot(public_origin="http://127.0.0.1:5270")))
    assert loopback[SESSION_COOKIE].failures == (
        "EREV_PUBLIC_ORIGIN names 127.0.0.1, a loopback host that only this machine reaches "
        "(05 CFG-09)",
        "EREV_PUBLIC_ORIGIN scheme is http, not https; a session cookie needs an https origin "
        "(05 SAR-09)",
    )
    # 05 SAR-09 rev 1.53 (R-53 (1)): an https loopback origin is reported as loopback only, and an
    # http origin on a public name by its scheme only — its cookie is Secure and never returned.
    localhost = _run(observations(settings=snapshot(public_origin="https://localhost")))
    assert localhost[SESSION_COOKIE].failures == (
        "EREV_PUBLIC_ORIGIN names localhost, a loopback host that only this machine reaches "
        "(05 CFG-09)",
    )
    plain = _run(observations(settings=snapshot(public_origin="http://app.erev.example")))
    assert plain[SESSION_COOKIE].failures == (
        "EREV_PUBLIC_ORIGIN scheme is http, not https; a session cookie needs an https origin "
        "(05 SAR-09)",
    )
    assert _run(observations())[SESSION_COOKIE].summary == (
        "the session cookie is Secure on https://app.erev.example"
    )

    wildcard = _run(observations(settings=snapshot(cors_origins=("https://*.erev.example",))))
    assert wildcard[CORS_ORIGINS].failures == (
        "EREV_CORS_ORIGINS contains a wildcard origin (05 SAR-12)",
    )
    disabled = _run(observations(settings=snapshot(cors_origins=())))[CORS_ORIGINS]
    assert disabled.ok and disabled.summary == "CORS is disabled (EREV_CORS_ORIGINS is empty)"

    fake = _run(observations(settings=snapshot(email_backend="fake")))[EMAIL_BACKEND]
    assert fake.failures == (
        "EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)",
    )
    off = _run(observations(defusedxml=False))[DEFUSEDXML]
    assert off.failures == (
        "openpyxl.DEFUSEDXML is false; defusedxml is not installed (05 UPL-05)",
    )


@pytest.mark.parametrize(
    ("field", "failing"),
    [
        ("integration_connections", [INTEGRATION_URLS]),
        ("partition_windows", [PARTITION_WINDOW]),
        ("defusedxml", [DEFUSEDXML]),
        ("release", [RELEASE_STAMP]),
        # Codex P4-R1: without the provider observation the pin cannot be verified either.
        ("provider", [KEY_PROVIDER, KEY_VERSION_PIN]),
        # 05 SAR-40 rev 1.156: the warning-only check fails closed as every other does.
        ("index_conditions", [INDEX_CONDITIONS]),
    ],
)
def test_uncollected_observation_fails_closed(field: str, failing: list[str]) -> None:
    results = _run(observations(**{field: None}))
    assert _failing(results.values()) == failing
    for check in failing:
        assert "was not collected" in results[check].failures[0], results[check].failures


@pytest.mark.parametrize("env", [Environment.DEV, Environment.TEST, Environment.E2E])
def test_production_checks_do_not_run_outside_production(env: Environment) -> None:
    local = snapshot(env=env, email_backend="fake", cors_origins=("*",), key_provider="local")
    assert production_checks(observations(settings=local, defusedxml=None), now=NOW) == []


def test_release_stamp_key_provider_and_version_pin() -> None:
    absent = ReleaseObservation(
        manifest_present=False,
        build_sha=None,
        error="release-manifest.json is required in production (REL-03)",
    )
    assert _run(observations(release=absent))[RELEASE_STAMP].failures == (absent.error,)
    stamped = _run(observations())[RELEASE_STAMP]
    assert stamped.summary == f"release-manifest.json describes build {BUILD_SHA[:12]}"

    unhealthy = ProviderObservation(
        kind="gcp",
        identity=KEK,
        healthy=False,
        security_hmac_key_id=None,
        detail="PermissionDenied on secret erev-security-hmac",
    )
    assert _run(observations(provider=unhealthy))[KEY_PROVIDER].failures == (
        f"key provider {KEK} probe failed: PermissionDenied on secret erev-security-hmac",
    )
    assert _run(observations(settings=snapshot(gcp_project_set=False)))[KEY_PROVIDER].failures == (
        "EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT (05 CFG-13)",
    )
    assert _run(observations(settings=snapshot(gcp_kms_kek_set=False)))[KEY_PROVIDER].failures == (
        "EREV_KEY_PROVIDER=gcp requires EREV_GCP_KMS_KEK (05 CFG-13)",
    )
    assert _run(observations())[KEY_PROVIDER].summary == f"key provider {KEK} is healthy"
    # The compose shape: a local key provider passes key-provider without a probe (05 CFG-11), but
    # the pin still needs the collected current key id (Codex P4-R1).
    compose = snapshot(
        key_provider="local",
        recovery_provider="NATIVE",
        backup_url_set=True,
        restore_admin_url_set=True,
    )
    local_provider = ProviderObservation("local", "LocalKeyProvider", True, "security-hmac:3")
    local = _run(observations(settings=compose, provider=local_provider))
    assert local[KEY_PROVIDER].ok and local[RECOVERY_PROVIDER].ok and local[KEY_VERSION_PIN].ok
    assert local[KEY_PROVIDER].summary == "EREV_KEY_PROVIDER is local (compose shape, 05 CFG-11)"
    unprobed_local = _run(observations(settings=compose, provider=None))
    assert unprobed_local[KEY_PROVIDER].ok and not unprobed_local[KEY_VERSION_PIN].ok
    unhealthy_local = ProviderObservation("local", "LocalKeyProvider", False, None, "no master key")
    assert not _run(observations(settings=compose, provider=unhealthy_local))[KEY_PROVIDER].ok

    name = SECURITY_HMAC_SECRET_VERSION_NAME
    pin = _run(observations(settings=snapshot(security_hmac_secret_version=None)))[KEY_VERSION_PIN]
    assert pin.failures == (f"{name} must be set under production (05 KEY-03)",)
    text = _run(observations(settings=snapshot(security_hmac_secret_version="three")))
    assert text[KEY_VERSION_PIN].failures == (INVALID_PIN,)
    zero = _run(observations(settings=snapshot(security_hmac_secret_version="0")))
    assert text[KEY_VERSION_PIN].failures == zero[KEY_VERSION_PIN].failures
    drift = _run(observations(settings=snapshot(security_hmac_secret_version="2")))
    assert drift[KEY_VERSION_PIN].failures == (
        f"{name}=2 differs from the provider's current security-hmac key id version 3 (05 KEY-03)",
    )
    assert _run(observations())[KEY_VERSION_PIN].summary == (
        "security-hmac pinned at version 3, matching the provider's current key id"
    )
    # Codex P4-R1: a configured pin is never a verified match without the collected identity.
    unprobed = _run(observations(provider=None))[KEY_VERSION_PIN]
    assert unprobed.failures == (UNVERIFIED_PIN,)
    pending = snapshot(security_hmac_secret_version=None, undefined=frozenset({name}))
    warned = _run(observations(settings=pending))[KEY_VERSION_PIN]
    assert warned.ok and warned.lines() == [
        f"WARN {KEY_VERSION_PIN}: {name} is not defined by this build (pending lane P2 merge); "
        "not checked"
    ]


def test_recovery_provider_rules() -> None:
    name = RECOVERY_PROVIDER_NAME

    def check(**overrides: object) -> CheckResult:
        return _run(observations(settings=snapshot(**overrides)))[RECOVERY_PROVIDER]

    assert check(recovery_provider="cloud").failures == (
        f"{name} must be NATIVE or MANAGED (05 CFG-30, D-95)",
    )
    assert check(recovery_provider="NATIVE").failures == (
        f"{name}=NATIVE contradicts EREV_KEY_PROVIDER=gcp (D-95: local → NATIVE, gcp → MANAGED)",
    )
    assert check(key_provider="local", recovery_provider="native").failures == (
        f"{name}=NATIVE requires {BACKUP_URL_NAME} under production (05 CFG-30)",
        f"{name}=NATIVE requires {RESTORE_ADMIN_URL_NAME} under production (05 CFG-30)",
    )
    assert check(recovery_provider="managed", restore_admin_url_set=True).failures == (
        f"{name}=MANAGED refuses a set {RESTORE_ADMIN_URL_NAME} (05 CFG-30)",
    )
    assert check().summary == f"{name} is MANAGED"
    defaulted = check(recovery_provider=None)
    assert defaulted.ok and not defaulted.warnings
    assert defaulted.summary == f"{name} is MANAGED (defaulted from EREV_KEY_PROVIDER=gcp)"
    native_default = check(key_provider="local", recovery_provider=None)
    assert native_default.failures == (
        f"{name}=NATIVE requires {BACKUP_URL_NAME} under production (05 CFG-30)",
        f"{name}=NATIVE requires {RESTORE_ADMIN_URL_NAME} under production (05 CFG-30)",
    )
    pending_warning = [
        f"WARN {RECOVERY_PROVIDER}: {name} is not defined by this build (pending lane P6 merge); "
        "not checked"
    ]
    pending = check(recovery_provider=None, undefined=frozenset({name}))
    assert pending.ok and pending.lines() == pending_warning
    # Codex P4-R2: a supplied value does not hide the undefined status, and no rule runs on it.
    supplied = check(recovery_provider="MANAGED", undefined=frozenset({name}))
    assert supplied.ok and supplied.lines() == pending_warning
    native_no_urls = check(
        key_provider="local", recovery_provider="NATIVE", undefined=frozenset({name})
    )
    assert native_no_urls.ok and native_no_urls.failures == ()


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://127.0.0.1:8190", "is a loopback address"),
        ("http://127.10.0.1/", "is a loopback address"),
        ("http://[::1]:8190", "is a loopback address"),
        ("http://10.0.0.5/api", "is a private address"),
        ("https://192.168.1.20", "is a private address"),
        ("https://172.16.0.9:8443", "is a private address"),
        ("http://[fd12:3456::1]", "is a private address"),
        ("http://169.254.169.254/latest", "is a link-local address"),
        ("http://[fe80::1]", "is a link-local address"),
        ("http://0.0.0.0:80", "is an unspecified address"),
        ("http://localhost:8190", "is a local name"),
        ("http://LOCALHOST", "is a local name"),
        ("http://mock.localhost", "is a local name"),
        ("http://netsuite.internal/", "is a local name"),
        ("http://printer.local", "is a local name"),
        ("http://netsuite-mock:8080", "is a single-label host name"),
        ("not a url", "has no host"),
        ("https://", "has no host"),
        ("https://acme.my.salesforce.com", None),
        ("https://api.stripe.com/v1", None),
        ("https://8.8.8.8", None),
        ("https://[2001:4860:4860::8888]", None),
    ],
)
def test_private_url_reason(url: str, reason: str | None) -> None:
    assert private_url_reason(url) == reason


def test_snapshot_settings_reads_documented_names_and_carries_no_secret(
    production_settings: Settings,
) -> None:
    environ = {
        SECURITY_HMAC_SECRET_VERSION_NAME: "3",
        RECOVERY_PROVIDER_NAME: "managed",
        BACKUP_URL_NAME: "   ",
        RESTORE_ADMIN_URL_NAME: "postgresql://admin:drill-credential@127.0.0.1:5432/erev_rv_drill",
    }
    taken = snapshot_settings(production_settings, environ=environ)
    assert taken.env is Environment.PRODUCTION
    assert taken.email_backend == "smtp" and taken.key_provider == "gcp"
    assert taken.cors_origins == ("https://app.erev.example", "https://*.erev.example")
    assert taken.public_origin == "https://app.erev.example"
    assert taken.ai_provider == "fake" and taken.anthropic_api_key_set is False
    assert taken.gcp_project_set is True and taken.gcp_kms_kek_set is True
    assert taken.backup_url_set is False and taken.restore_admin_url_set is True
    supported = {
        SECURITY_HMAC_SECRET_VERSION_NAME: "security_hmac_secret_version" in Settings.model_fields,
        # Lane P6 resolves CFG-30 outside Settings; its module marks the build as defining it.
        RECOVERY_PROVIDER_NAME: "recovery_provider" in Settings.model_fields
        or importlib.util.find_spec("erev_api.controls.recovery_preflight") is not None,
    }
    expected = {name for name, defined in supported.items() if not defined}
    assert taken.undefined == frozenset(expected)
    # Codex P4-R2: a value the build does not define is never read into the snapshot.
    pin_defined = supported[SECURITY_HMAC_SECRET_VERSION_NAME]
    assert taken.security_hmac_secret_version == ("3" if pin_defined else None)
    assert taken.recovery_provider == ("managed" if supported[RECOVERY_PROVIDER_NAME] else None)
    text = repr(taken)
    for secret in (*MASTER_KEYS_FIXTURE.values(), "drill-credential", "erev_rv_drill"):
        assert secret not in text

    bare = snapshot_settings(production_settings)
    assert bare.undefined == frozenset(expected)
    # Lane P2 merged: the Settings field carries the pinned version; otherwise nothing is read.
    assert bare.security_hmac_secret_version == ("3" if pin_defined else None)
    assert bare.recovery_provider is None or supported[RECOVERY_PROVIDER_NAME]
    assert bare.backup_url_set is False and bare.restore_admin_url_set is False


def test_observe_release_reports_manifest_state(tmp_path: Path) -> None:
    manifest = tmp_path / "release-manifest.json"
    absent = observe_release(
        Environment.PRODUCTION, manifest_path=manifest, build_sha=lambda: "dev"
    )
    assert absent == ReleaseObservation(
        manifest_present=False,
        build_sha=None,
        error="release-manifest.json is required in production (REL-03)",
    )
    derived = observe_release(Environment.DEV, manifest_path=manifest, build_sha=lambda: "dev")
    assert derived == ReleaseObservation(manifest_present=False, build_sha="dev", error=None)

    manifest.write_text(
        json.dumps(
            {"engine_version": "0.0.0-other", "schema_revision": "x", "build_sha": BUILD_SHA}
        ),
        encoding="utf-8",
    )
    other = observe_release(Environment.PRODUCTION, manifest_path=manifest, build_sha=lambda: "dev")
    assert other.manifest_present and other.build_sha is None
    assert other.error == "the release manifest names another engine version"

    manifest.write_text(
        json.dumps(
            {
                "engine_version": ENGINE_VERSION,
                "schema_revision": code_head(),
                "build_sha": BUILD_SHA,
            }
        ),
        encoding="utf-8",
    )
    good = observe_release(Environment.PRODUCTION, manifest_path=manifest, build_sha=lambda: "dev")
    assert good == ReleaseObservation(manifest_present=True, build_sha=BUILD_SHA, error=None)


def test_observe_defusedxml_reads_the_installed_openpyxl() -> None:
    # defusedxml is a locked runtime dependency (05 UPL-05), so the flag is true here.
    assert observe_defusedxml() is True


def test_collect_production_observations_injects_every_collector(
    production_settings: Settings,
) -> None:
    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={SECURITY_HMAC_SECRET_VERSION_NAME: "3", RECOVERY_PROVIDER_NAME: "MANAGED"},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=lambda: WINDOWS,
        release=lambda env: RELEASE,
        provider=lambda: PROVIDER,
        lock_budget=lambda: LOCKS,
        index_conditions=lambda: INDEX_KEYS,
    )
    assert collected.settings.env is Environment.PRODUCTION
    assert collected.defusedxml is True
    # The fake provider needs no key: the default resolver reads the settings snapshot.
    assert collected.anthropic_key_resolves is False
    assert collected.integration_connections == (SALESFORCE,)
    assert collected.partition_windows == WINDOWS
    assert collected.release is RELEASE and collected.provider is PROVIDER
    assert collected.lock_budget is LOCKS
    assert collected.index_conditions is INDEX_KEYS
    # PRODUCTION_ENVIRONMENT carries a wildcard CORS origin on purpose (snapshot test), so the
    # collected run reports exactly that SAR-40 condition.
    results = production_checks(collected, now=NOW)
    assert _failing(results) == [
        CORS_ORIGINS,
        OPERATOR_ALERTS,
    ]  # no operator-alert recipient set here
    # Codex P4-R2 through the actual snapshot/collector composition: the environment supplied
    # 3 and MANAGED, but a build that does not define the settings prints WARN, not a result.
    by_check = _by_check(results)
    for name, check in (
        (SECURITY_HMAC_SECRET_VERSION_NAME, KEY_VERSION_PIN),
        (RECOVERY_PROVIDER_NAME, RECOVERY_PROVIDER),
    ):
        if name in collected.settings.undefined:
            assert by_check[check].ok and by_check[check].failures == ()
            assert by_check[check].lines() == [
                f"WARN {check}: {name} is not defined by this build (pending lane "
                f"{doctor.PENDING_LANES[name]} merge); not checked"
            ]
        else:  # the owning lane merged: the value is read and checked
            assert by_check[check].ok and not by_check[check].warnings

    defaults = collect_production_observations(production_settings, now=NOW, environ={})
    assert isinstance(defaults.defusedxml, bool)
    assert defaults.release is not None
    # The database and key-provider collectors are pending SOP-6 phases: not collected, so the
    # production run fails closed on exactly those checks.
    assert defaults.integration_connections is None and defaults.partition_windows is None
    assert defaults.provider is None and defaults.lock_budget is None
    assert defaults.index_conditions is None
    default_results = _by_check(production_checks(defaults, now=NOW))
    failing = _failing(default_results.values())
    assert {
        INTEGRATION_URLS,
        PARTITION_WINDOW,
        KEY_PROVIDER,
        LOCK_BUDGET,
        INDEX_CONDITIONS,
    } <= set(failing)
    assert default_results[INDEX_CONDITIONS].failures == (
        "the index catalogue was not collected: no collector composed for this member (SOP-6)",
    )
    assert default_results[LOCK_BUDGET].failures == (
        "the lock table settings was not collected: no collector composed for this member (SOP-6)",
    )
    # P4b: an uncomposed collector is named in the FAIL line through its provenance.
    assert default_results[INTEGRATION_URLS].failures == (
        "the active integration connections was not collected: no collector composed for this "
        "member (SOP-6)",
    )
    assert {p.member for p in defaults.provenance} == {
        "defusedxml",
        "anthropic_key_resolves",
        "integration_connections",
        "partition_windows",
        "release",
        "provider",
        "lock_budget",  # 05 SAR-40 rev 1.53
        "index_conditions",  # 05 SAR-40 rev 1.156
    }
    assert all(p.collected_at == NOW for p in defaults.provenance)


def test_check_result_line_formats() -> None:
    assert CheckResult("x", "fine").lines() == ["OK x: fine"]
    assert CheckResult("x", "fine", failures=("a", "b")).lines() == ["FAIL x: a", "FAIL x: b"]
    warned = CheckResult("x", "fine", warnings=("w",))
    assert warned.ok and warned.lines() == ["WARN x: w"]
    both = CheckResult("x", "fine", failures=("a",), warnings=("w",))
    assert not both.ok and both.lines() == ["FAIL x: a"]


def test_run_doctor_accepts_production_observations() -> None:
    parameter = inspect.signature(run_doctor).parameters["production"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None


def test_r1_unknown_current_key_identity_is_a_named_fail() -> None:
    """Codex P4-R1: a healthy provider that reports no current key id, a missing provider, or a
    malformed key id never lets a configured pin count as a verified match."""
    silent = ProviderObservation(kind="gcp", identity=KEK, healthy=True, security_hmac_key_id=None)
    results = _run(observations(provider=silent))
    assert _failing(results.values()) == [KEY_VERSION_PIN]
    assert results[KEY_VERSION_PIN].failures == (UNVERIFIED_PIN,)
    assert results[KEY_VERSION_PIN].lines() == [f"FAIL {KEY_VERSION_PIN}: {UNVERIFIED_PIN}"]
    missing = _run(observations(provider=None))
    assert _failing(missing.values()) == [KEY_PROVIDER, KEY_VERSION_PIN]
    assert missing[KEY_VERSION_PIN].failures == (UNVERIFIED_PIN,)
    # A malformed key id is external text: named, never echoed (Codex P4B-R1 ruling).
    for key_id in ("security-hmac:x", "audit-hmac:3", "security-hmac:", "SECURITY-HMAC:3"):
        malformed = ProviderObservation("gcp", KEK, True, key_id)
        assert _run(observations(provider=malformed))[KEY_VERSION_PIN].failures == (
            "the provider's current security-hmac key id is malformed (05 KEY-03)",
        ), key_id


def test_r1_run_doctor_composition_carries_the_pin_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P4-R1 composition control: the real ``run_doctor`` body, with its five database
    checks and sessions replaced by inert sentinels, reports the pin failure after them."""

    @contextmanager
    def no_connection(*, request_id: str) -> Iterable[None]:
        yield None

    def sentinel(name: str) -> object:
        return lambda *args, **kwargs: CheckResult(name, "sentinel")

    monkeypatch.setattr(doctor, "catalogue_connection", no_connection)
    monkeypatch.setattr(doctor, "row_level_security", sentinel(doctor.ROW_LEVEL_SECURITY))
    monkeypatch.setattr(doctor, "app_role", sentinel(doctor.APP_ROLE_CHECK))
    monkeypatch.setattr(doctor, "immutability_triggers", sentinel(doctor.IMMUTABILITY_TRIGGERS))
    monkeypatch.setattr(doctor, "_tenants", lambda *, keyring, request_id: [])
    monkeypatch.setattr(doctor, "audit_chain", sentinel(doctor.AUDIT_CHAIN))
    monkeypatch.setattr(doctor, "ai", sentinel(doctor.AI))
    monkeypatch.setattr(doctor, "setting_references", sentinel(doctor.SETTING_REFERENCES))
    monkeypatch.setattr(doctor, "observe_setting_references", lambda connection: ())

    def run(production: ProductionObservations | None) -> list[CheckResult]:
        return run_doctor(
            clock=frozen_clock(NOW),
            keyring=None,  # type: ignore[arg-type]  (the tenant directory is a sentinel)
            request_id="test",
            ai_kill_switch=False,
            production=production,
        )

    silent = ProviderObservation("gcp", KEK, True, None)
    results = run(observations(provider=silent))
    assert [r.check for r in results] == list(doctor.CHECK_NAMES) + list(PRODUCTION_CHECK_NAMES)
    assert _failing(results) == [KEY_VERSION_PIN]
    healthy = run(observations())
    # + operator-alerts (05 OPR-24 rev 1.27), lock-budget and master-keys (05 SAR-40 rev 1.53),
    # index-conditions (05 SAR-40 rev 1.156)
    assert len(healthy) == 21 and _failing(healthy) == []
    assert [r.check for r in run(None)] == list(doctor.CHECK_NAMES)


def test_r2_supplied_values_never_hide_the_undefined_warning() -> None:
    """Codex P4-R2: a setting the build does not define prints WARN instead of a result, even
    when the environment supplied a value."""
    pin_name = SECURITY_HMAC_SECRET_VERSION_NAME
    for value in ("3", "2", "three"):
        supplied = snapshot(security_hmac_secret_version=value, undefined=frozenset({pin_name}))
        pin = _run(observations(settings=supplied))[KEY_VERSION_PIN]
        assert pin.ok and pin.failures == ()
        assert pin.lines() == [
            f"WARN {KEY_VERSION_PIN}: {pin_name} is not defined by this build (pending lane P2 "
            "merge); not checked"
        ], value
    rec_name = RECOVERY_PROVIDER_NAME
    for value in ("MANAGED", "NATIVE", "cloud"):
        pending = snapshot(recovery_provider=value, undefined=frozenset({rec_name}))
        rec = _run(observations(settings=pending))[RECOVERY_PROVIDER]
        assert rec.ok and rec.failures == ()
        assert rec.lines() == [
            f"WARN {RECOVERY_PROVIDER}: {rec_name} is not defined by this build (pending lane P6 "
            "merge); not checked"
        ], value


def test_r3_absent_manifest_observation_fails_closed() -> None:
    """Codex P4-R3: an observation reporting absence fails even without a collector error."""
    for build_sha in (None, "dev", BUILD_SHA):
        absent = ReleaseObservation(manifest_present=False, build_sha=build_sha, error=None)
        result = _run(observations(release=absent))[RELEASE_STAMP]
        assert result.failures == (
            "release-manifest.json is absent; production requires the release manifest (05 REL-03)",
        ), build_sha


@pytest.mark.parametrize(
    "text",
    ["²", "٣", "３", "1e3", "-1", "+3", "0", "three", "", " 3", "3 ", "00000000", "3.0"],
)
def test_r4_malformed_pin_text_is_a_named_fail(text: str) -> None:
    """Codex P4-R4: text that satisfies ``str.isdigit`` but not ``int`` (or any other malformed
    pin) is a named FAIL; the check list never aborts."""
    seeded = observations(settings=snapshot(security_hmac_secret_version=text))
    results = production_checks(seeded, now=NOW)
    assert [r.check for r in results] == list(PRODUCTION_CHECK_NAMES)
    assert _by_check(results)[KEY_VERSION_PIN].failures == (INVALID_PIN,)
    assert _failing(results) == [KEY_VERSION_PIN]


class _FakeKeyRing:
    """A key ring for the collectors: ``current_security_key_id`` only when ``key_id`` is given
    (lane P2's accessor); ``security_event_key`` returns ``material`` or raises ``failure``."""

    def __init__(
        self,
        key_id: str | None = "security-hmac:3",
        *,
        material: bytes = b"k" * 32,
        failure: Exception | None = None,
        secrets: dict[str, str] | None = None,
    ) -> None:
        self._material = material
        self._failure = failure
        self._secrets = secrets or {}
        if key_id is not None:
            self.current_security_key_id = lambda: key_id  # type: ignore[method-assign]

    def security_event_key(self, hmac_key_id: str) -> bytes:
        if self._failure is not None:
            raise self._failure
        return self._material

    def secret(self, ref: str) -> str:
        return self._secrets[ref]


def test_p4b_provenance_names_the_collector_reason_in_the_fail_line(
    production_settings: Settings,
) -> None:
    """Every member carries provenance; a raising collector leaves the member None with the
    redacted reason, which the FAIL line of its check then names."""

    def broken() -> tuple[PartitionWindowObservation, ...]:
        raise RuntimeError(
            "catalogue read failed for postgresql://erev_app:secret-pw@db.internal/erev"
        )

    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=broken,
        release=lambda env: RELEASE,
        provider=lambda: PROVIDER,
    )
    by_member = {p.member: p for p in collected.provenance}
    assert collected.partition_windows is None
    assert by_member["partition_windows"].source == "pg_inherits"
    assert by_member["partition_windows"].error == (
        "RuntimeError while reading the partition bounds from pg_inherits"
    )
    assert "secret-pw" not in repr(collected)
    assert by_member["release"].error is None and by_member["provider"].error is None
    results = _by_check(production_checks(collected, now=NOW))
    assert results[PARTITION_WINDOW].failures == (
        "the partition windows was not collected: RuntimeError while reading the partition bounds "
        "from pg_inherits",
    )
    assert results[PARTITION_WINDOW].lines()[0].startswith(f"FAIL {PARTITION_WINDOW}: ")
    # A pending-lane collector reports its CollectorPending reason the same way.
    pending = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=lambda: WINDOWS,
        release=lambda env: RELEASE,
        provider=lambda: observe_key_provider(production_settings, _FakeKeyRing(None)),  # type: ignore[arg-type]
    )
    pending_results = _by_check(production_checks(pending, now=NOW))
    assert pending_results[KEY_PROVIDER].failures == (
        "the key provider probe was not collected: CollectorPending: "
        "KeyRing.current_security_key_id() is not on this build (lane P2 pending); the current "
        "security-hmac key id cannot be collected",
    )
    assert Provenance("m", "s", NOW).error is None


@pytest.mark.parametrize(
    ("bound", "upper"),
    [
        ("FOR VALUES FROM ('2032-12-01') TO ('2033-01-01')", date(2033, 1, 1)),
        (
            "FOR VALUES FROM ('2032-12-01 00:00:00+00') TO ('2033-01-01 00:00:00+00')",
            date(2033, 1, 1),
        ),
        ("FOR VALUES FROM (MINVALUE) TO ('2018-01-01')", date(2018, 1, 1)),
        ("DEFAULT", None),
        ("FOR VALUES IN (1, 2)", None),
    ],
)
def test_p4b_partition_upper_bound(bound: str, upper: date | None) -> None:
    assert partition_upper_bound(bound) == upper


def test_p4b_observe_partition_windows_reads_the_catalogue_rows() -> None:
    """The catalogue collector over a fake connection: max bounded upper bound per PT parent,
    DEFAULT excluded, None without a bounded partition."""

    class _Rows:
        def __init__(self, rows: list[tuple[str, str]]) -> None:
            self._rows = rows

        def all(self) -> list[tuple[str, str]]:
            return self._rows

    class _Connection:
        def __init__(self) -> None:
            self.parents: list[str] = []

        def execute(self, statement: object, parameters: dict[str, str]) -> _Rows:
            self.parents.append(parameters["parent"])
            if parameters["parent"] == "erev.audit_event":
                return _Rows([("audit_event_pdefault", "DEFAULT")])
            return _Rows(
                [
                    ("p202612", "FOR VALUES FROM ('2032-12-01') TO ('2033-01-01')"),
                    ("p202611", "FOR VALUES FROM ('2032-11-01') TO ('2032-12-01')"),
                    ("pdefault", "DEFAULT"),
                ]
            )

    connection = _Connection()
    windows = observe_partition_windows(connection)  # type: ignore[arg-type]
    assert connection.parents == ["erev.audit_event", "erev.schedule_line", "erev.subledger_line"]
    assert windows == (
        PartitionWindowObservation("audit_event", None),
        PartitionWindowObservation("schedule_line", date(2033, 1, 1)),
        PartitionWindowObservation("subledger_line", date(2033, 1, 1)),
    )
    assert _run(observations(partition_windows=windows))[PARTITION_WINDOW].failures == (
        "table audit_event has no bounded partition (04 §1.6 rule 1)",
    )


def test_p4b_observe_key_provider_shapes(production_settings: Settings) -> None:
    with pytest.raises(CollectorPending, match="lane P2 pending"):
        observe_key_provider(production_settings, _FakeKeyRing(None))  # type: ignore[arg-type]
    healthy = observe_key_provider(production_settings, _FakeKeyRing())  # type: ignore[arg-type]
    assert healthy == ProviderObservation(
        "gcp", f"GcpKeyProvider project erev-prod KEK {KEK}", True, "security-hmac:3"
    )
    assert _failing(_run(observations(provider=healthy)).values()) == []
    failing = observe_key_provider(
        production_settings,
        _FakeKeyRing(failure=PermissionError("denied for projects/erev-prod/secrets/x")),  # type: ignore[arg-type]
    )
    assert failing.healthy is False and failing.security_hmac_key_id == "security-hmac:3"
    assert failing.detail == "PermissionError while deriving the current security-hmac key"
    short = observe_key_provider(production_settings, _FakeKeyRing(material=b"short"))  # type: ignore[arg-type]
    assert short.healthy is False and short.detail == "the security-hmac key is not 32 bytes"
    drift = observe_key_provider(production_settings, _FakeKeyRing("security-hmac:4"))  # type: ignore[arg-type]
    assert _run(observations(provider=drift))[KEY_VERSION_PIN].failures == (
        f"{SECURITY_HMAC_SECRET_VERSION_NAME}=3 differs from the provider's current security-hmac "
        "key id version 4 (05 KEY-03)",
    )


def test_p4b_observe_anthropic_key_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """The setting resolves directly; under gcp with the anthropic provider the Secret Manager
    reference resolves through the key ring; nothing is probed for the fake provider."""

    class _Settings:
        def __init__(self, provider: str, key_provider: str, key: object) -> None:
            self.ai_provider = provider
            self.key_provider = key_provider
            self.anthropic_api_key = key

    ring = _FakeKeyRing(secrets={"anthropic-api-key": "resolved"})
    assert observe_anthropic_key(_Settings("anthropic", "local", object()), ring) is True  # type: ignore[arg-type]
    assert observe_anthropic_key(_Settings("anthropic", "gcp", None), ring) is True  # type: ignore[arg-type]
    assert observe_anthropic_key(_Settings("anthropic", "gcp", None), _FakeKeyRing()) is False  # type: ignore[arg-type]
    assert observe_anthropic_key(_Settings("anthropic", "local", None), ring) is False  # type: ignore[arg-type]
    assert observe_anthropic_key(_Settings("fake", "gcp", None), ring) is False  # type: ignore[arg-type]


def test_p4b_observe_integration_connections_until_the_table_exists() -> None:
    table = getattr(db_tables, "integration_connection", None)
    if table is None:
        with pytest.raises(CollectorPending, match="T-INT-01 integration_connection"):
            observe_integration_connections([])
    else:  # the INT lane merged: the collector reads these T-INT-01 columns (pg test covers rows)
        assert {"code", "status", "base_url"} <= set(table.c.keys())
        assert observe_integration_connections([]) == ()


def _sentinel_database_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the five database checks, their sessions and the tenant directory with sentinels."""

    @contextmanager
    def no_connection(*, request_id: str) -> Iterable[None]:
        yield None

    def sentinel(name: str) -> object:
        return lambda *args, **kwargs: CheckResult(name, "sentinel")

    monkeypatch.setattr(doctor, "catalogue_connection", no_connection)
    monkeypatch.setattr(doctor, "row_level_security", sentinel(doctor.ROW_LEVEL_SECURITY))
    monkeypatch.setattr(doctor, "app_role", sentinel(doctor.APP_ROLE_CHECK))
    monkeypatch.setattr(doctor, "immutability_triggers", sentinel(doctor.IMMUTABILITY_TRIGGERS))
    monkeypatch.setattr(doctor, "_tenants", lambda *, keyring, request_id: [])
    monkeypatch.setattr(doctor, "audit_chain", sentinel(doctor.AUDIT_CHAIN))
    monkeypatch.setattr(doctor, "ai", sentinel(doctor.AI))
    monkeypatch.setattr(doctor, "setting_references", sentinel(doctor.SETTING_REFERENCES))
    monkeypatch.setattr(doctor, "observe_setting_references", lambda connection: ())


def test_p4b_run_doctor_passes_the_tenant_directory_to_a_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sentinel_database_checks(monkeypatch)
    seen: list[object] = []

    def collector(tenants: object) -> ProductionObservations:
        seen.append(tenants)
        return observations()

    results = run_doctor(
        clock=frozen_clock(NOW),
        keyring=None,  # type: ignore[arg-type]
        request_id="test",
        ai_kill_switch=False,
        production=collector,
    )
    assert seen == [[]] and len(results) == 21 and _failing(results) == []


def test_p4b_cli_doctor_composes_the_real_collectors_under_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``erev doctor`` under ``EREV_ENV=production`` through the real composition path (no injected
    observations): the SAR-40 lines follow the five checks, uncollected observations are named
    FAILs with the collector's reason, and ``--db test`` prints only the five checks."""
    _sentinel_database_checks(monkeypatch)
    monkeypatch.setattr(doctor, "observe_partition_windows", lambda connection: WINDOWS)
    monkeypatch.setattr(doctor, "observe_lock_budget", lambda connection: COMPOSE_LOCKS)
    monkeypatch.setattr(doctor, "observe_index_conditions", lambda connection: INDEX_KEYS)
    monkeypatch.setattr(doctor, "MANIFEST_PATH", tmp_path / "release-manifest.json")
    # The missing-recovery-configuration case is deterministic: the three recovery variables the
    # `recovery-provider` check reads are cleared whatever the ambient environment carries (Codex
    # production-20260921-2338 §4-§5); the fixture stays an unconfigured production.
    for name in ("EREV_RECOVERY_PROVIDER", "EREV_BACKUP_URL", "EREV_RESTORE_ADMIN_URL"):
        monkeypatch.delenv(name, raising=False)
    ring = _FakeKeyRing(None)  # a ring that serves no pinned key id: the pin check must FAIL
    with settings_override(env="production", security_hmac_secret_version=1) as settings:
        assert settings.env is Environment.PRODUCTION and settings.key_provider == "local"
        services = operator_services(ring, frozen_clock(NOW), tmp_path, env=Environment.PRODUCTION)  # type: ignore[arg-type]
        result = invoke(services, ["doctor"])
        five = invoke(services, ["doctor", "--db", "test"])

    lines = result.stdout.splitlines()
    checks = [line.split(":", 1)[0].split(" ", 1)[1] for line in lines]
    assert checks[:6] == list(doctor.CHECK_NAMES)
    assert [c for i, c in enumerate(checks) if i >= 6 and c != checks[i - 1]] == list(
        PRODUCTION_CHECK_NAMES
    ), lines
    assert result.exit_code == 1, result.output
    failing = {
        line.split(":", 1)[0].removeprefix("FAIL ") for line in lines if line.startswith("FAIL ")
    }
    # DIN-12 (revision 0072): T-INT-01 is on the build, so the collector reads the (empty) tenant
    # directory and the check passes with zero active connections.
    # + operator-alerts: the production env sets neither EREV_OPERATOR_ALERT_EMAIL nor the
    # log-only acknowledgement (05 OPR-24 / CFG-31 rev 1.27), so that check FAILs by design.
    expected_failing = {EMAIL_BACKEND, SESSION_COOKIE, RELEASE_STAMP, OPERATOR_ALERTS}
    if (
        "security_hmac_secret_version" in Settings.model_fields
    ):  # lane P2 merged: the pin is checked
        expected_failing.add(KEY_VERSION_PIN)
    # Lane P6 merged (erev_api.controls.recovery_preflight on this build): the fixture is a
    # deliberately unconfigured production — key provider `local` defaults the recovery provider to
    # NATIVE (D-95), and NATIVE under production requires both recovery URLs (05 CFG-30), which the
    # fixture does not set — so the check FAILs, one line per missing URL (P6 fix-forward on p6r2).
    expected_failing.add(RECOVERY_PROVIDER)
    assert failing == expected_failing, lines
    assert (
        f"OK {INTEGRATION_URLS}: 0 active integration connections have public or no base URLs"
    ) in lines
    assert (
        f"FAIL {RELEASE_STAMP}: release-manifest.json is required in production (REL-03)" in lines
    )
    assert f"OK {KEY_PROVIDER}: EREV_KEY_PROVIDER is local (compose shape, 05 CFG-11)" in lines
    assert (
        f"OK {PARTITION_WINDOW}: every partition window ends after 2027-09-19 (earliest 2033-01-01)"
        in lines
    )
    assert f"OK {ANTHROPIC_KEY}: EREV_AI_PROVIDER is fake" in lines
    assert (
        f"OK {LOCK_BUDGET}: 409600 lock slots (max_locks_per_transaction 4096) cover 80 sessions "
        "× 3094 partition locks + 5044 relations = 252564 (05 §2.7)"
    ) in lines
    assert lines[-1] == (
        f"OK {INDEX_CONDITIONS}: every index of a table with a row-level-security policy has a "
        f"key the policy can use, or is one of the {LISTED} listed with a reason (05 §2.7)"
    ), lines[-1:]
    pin_line = next(line for line in lines if f" {KEY_VERSION_PIN}: " in line)
    if "security_hmac_secret_version" in Settings.model_fields:  # lane P2 merged
        assert pin_line.startswith(f"FAIL {KEY_VERSION_PIN}: ")
    else:
        assert pin_line == (
            f"WARN {KEY_VERSION_PIN}: {SECURITY_HMAC_SECRET_VERSION_NAME} is not defined by this "
            "build (pending lane P2 merge); not checked"
        )
    recovery_lines = [line for line in lines if f" {RECOVERY_PROVIDER}: " in line]
    assert importlib.util.find_spec("erev_api.controls.recovery_preflight") is not None
    assert recovery_lines == [
        f"FAIL {RECOVERY_PROVIDER}: {RECOVERY_PROVIDER_NAME}=NATIVE requires EREV_BACKUP_URL "
        "under production (05 CFG-30)",
        f"FAIL {RECOVERY_PROVIDER}: {RECOVERY_PROVIDER_NAME}=NATIVE requires "
        "EREV_RESTORE_ADMIN_URL under production (05 CFG-30)",
    ], lines
    assert five.exit_code == 0, five.output
    assert five.stdout.splitlines() == [f"OK {name}: sentinel" for name in doctor.CHECK_NAMES]


def test_p4b_production_collector_composes_every_source(
    monkeypatch: pytest.MonkeyPatch, production_settings: Settings, tmp_path: Path
) -> None:
    """The real composition ``cli.py`` uses: every member collected through its source, with the
    tenant directory supplied by ``run_doctor`` and the catalogue connection opened once."""
    opened: list[str] = []

    @contextmanager
    def catalogue(*, request_id: str) -> Iterable[None]:
        opened.append(request_id)
        yield None

    monkeypatch.setattr(doctor, "catalogue_connection", catalogue)
    monkeypatch.setattr(doctor, "observe_partition_windows", lambda connection: WINDOWS)
    monkeypatch.setattr(doctor, "observe_lock_budget", lambda connection: LOCKS)
    monkeypatch.setattr(doctor, "observe_index_conditions", lambda connection: INDEX_KEYS)
    monkeypatch.setattr(doctor, "MANIFEST_PATH", tmp_path / "release-manifest.json")
    collect = production_collector(
        production_settings,
        keyring=_FakeKeyRing(),  # type: ignore[arg-type]
        environ={},
        request_id="cli-test",
        now=NOW,
    )
    collected = collect([])
    # One catalogue connection per catalogue collector: the partition bounds, since 05 SAR-40
    # rev 1.53 the lock table settings and, since rev 1.156, the index keys.
    assert opened == ["cli-test", "cli-test", "cli-test"]
    assert collected.partition_windows == WINDOWS
    assert collected.lock_budget == LOCKS
    assert collected.index_conditions == INDEX_KEYS
    assert collected.provider == ProviderObservation(
        "gcp", f"GcpKeyProvider project erev-prod KEK {KEK}", True, "security-hmac:3"
    )
    assert collected.release is not None and collected.release.error == (
        "release-manifest.json is required in production (REL-03)"
    )
    assert collected.anthropic_key_resolves is False and collected.defusedxml is True
    by_member = {p.member: p for p in collected.provenance}
    if getattr(db_tables, "integration_connection", None) is None:
        assert collected.integration_connections is None
        assert by_member["integration_connections"].error == (
            "CollectorPending: T-INT-01 integration_connection is not on this build (INT lane "
            "pending)"
        )
    else:
        assert collected.integration_connections == ()
    assert all(p.collected_at == NOW for p in collected.provenance)
    assert {p.source for p in collected.provenance} == {
        "openpyxl",
        "Settings, key ring",
        "erev.integration_connection (T-INT-01)",
        "pg_inherits",
        "release-manifest.json",
        "KeyRing",
        "pg_settings, pg_class, pg_inherits, pg_index",
        "pg_index, pg_class, pg_attribute, pg_opclass, pg_amop, pg_proc",
    }


# Codex P4B-R1: fabricated credential canaries only, never a real value.
CANARY = "P4B-SYNTHETIC-CANARY-0f9a"
# The original seven-control forms, the retest's structured forms (quoted JSON field names and
# quoted multi-word values), and the lane's own quoted multi-word value and JSON-quoted key.
UNTRUSTED_MESSAGES = [
    f"https://api.example/v1?token={CANARY}&page=2",
    f"Authorization: Bearer {CANARY}",
    f"password={CANARY}",
    f"postgresql://erev_app:{CANARY}@db.internal/erev",
    f'{{"password": "{CANARY}"}}',
    f'{{"access_token": "{CANARY}"}}',
    f'{{"Authorization": "Basic {CANARY}"}}',
    f'password="prefix {CANARY}"',
    f'{{"api_key": "{CANARY}"}}',
    f"{{'token': '{CANARY}'}}",
    f'Authorization="Bearer {CANARY}"',
    f'"client_secret": "{CANARY}"',
    f'PGPASSWORD="a b {CANARY}"',
    f'{{"EREV_DB_APP_URL": "postgresql://u:{CANARY}@h/db"}}',
    f'{{"key": "{CANARY}", "note": "json-quoted key"}}',
    f'secret = "two words {CANARY}"',
    f"first line ok\nsecond line password={CANARY}",
]
CLI_MESSAGES = UNTRUSTED_MESSAGES[4:8] + UNTRUSTED_MESSAGES[14:16]
PARTITION_ATTEMPT = "RuntimeError while reading the partition bounds from pg_inherits"
PROBE_ATTEMPT = "PermissionError while deriving the current security-hmac key"


@pytest.mark.parametrize("message", UNTRUSTED_MESSAGES)
def test_p4b_r1_untrusted_exception_text_never_reaches_a_fail_line(
    message: str, production_settings: Settings
) -> None:
    """Codex P4B-R1 (retest ruling): an arbitrary external failure renders as its exception type
    plus the code-owned attempt; the exception's message is never read into a diagnostic, so no
    text shape can leak."""

    def leaking() -> tuple[PartitionWindowObservation, ...]:
        raise RuntimeError(message)

    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=leaking,
        release=lambda env: RELEASE,
        provider=lambda: observe_key_provider(
            production_settings,
            _FakeKeyRing(failure=PermissionError(message)),  # type: ignore[arg-type]
        ),
        lock_budget=lambda: LOCKS,
        index_conditions=lambda: INDEX_KEYS,
    )
    assert CANARY not in repr(collected)
    by_member = {p.member: p for p in collected.provenance}
    assert by_member["partition_windows"].error == PARTITION_ATTEMPT
    assert collected.provider is not None and collected.provider.detail == PROBE_ATTEMPT
    results = production_checks(collected, now=NOW)
    rendered = "\n".join(line for result in results for line in result.lines())
    assert CANARY not in rendered
    # PRODUCTION_ENVIRONMENT carries its deliberate wildcard CORS origin (snapshot test).
    assert _failing(results) == [CORS_ORIGINS, PARTITION_WINDOW, KEY_PROVIDER, OPERATOR_ALERTS]
    by_check = _by_check(results)
    assert by_check[PARTITION_WINDOW].failures == (
        f"the partition windows was not collected: {PARTITION_ATTEMPT}",
    )
    assert by_check[KEY_PROVIDER].failures == (
        f"key provider GcpKeyProvider project erev-prod KEK {KEK} probe failed: {PROBE_ATTEMPT}",
    )


@pytest.mark.parametrize("message", CLI_MESSAGES)
def test_p4b_r1_cli_stdout_never_carries_untrusted_exception_text(
    message: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Codex P4B-R1 through the actual Typer ``doctor`` stdout under production: a catalogue
    failure and a key-derivation failure carrying the structured canaries render as type plus
    attempt; exit 1; no canary anywhere in the output."""
    _sentinel_database_checks(monkeypatch)

    def leaking(connection: object) -> tuple[PartitionWindowObservation, ...]:
        raise RuntimeError(message)

    monkeypatch.setattr(doctor, "observe_partition_windows", leaking)
    monkeypatch.setattr(doctor, "MANIFEST_PATH", tmp_path / "release-manifest.json")
    ring = _FakeKeyRing(failure=PermissionError(message))
    with settings_override(env="production", security_hmac_secret_version=1):
        services = operator_services(ring, frozen_clock(NOW), tmp_path, env=Environment.PRODUCTION)  # type: ignore[arg-type]
        result = invoke(services, ["doctor"])
    assert result.exit_code == 1, result.output
    assert CANARY not in result.output
    lines = result.stdout.splitlines()
    assert (
        f"FAIL {PARTITION_WINDOW}: the partition windows was not collected: {PARTITION_ATTEMPT}"
    ) in lines
    assert (
        f"FAIL {KEY_PROVIDER}: key provider LocalKeyProvider probe failed: {PROBE_ATTEMPT}" in lines
    )


def test_p4b_r1_only_code_owned_reasons_pass_through_verbatim(
    production_settings: Settings,
) -> None:
    """The only free-form text a FAIL line carries verbatim is an enumerated, code-owned pending
    reason; ``CollectorPending`` refuses anything else, and a plain exception subclass renders as
    type plus attempt."""
    with pytest.raises(ValueError, match="code-owned reason"):
        CollectorPending(f"T-INT-01 {CANARY}")
    assert PENDING_REASONS == frozenset({PENDING_INTEGRATION_TABLE, PENDING_KEY_ID_ACCESSOR})
    for reason in PENDING_REASONS:
        assert CollectorPending(reason).reason == reason and CANARY not in reason

    def pending() -> tuple[IntegrationConnectionObservation, ...]:
        raise CollectorPending(PENDING_INTEGRATION_TABLE)

    class _LooksPending(RuntimeError):
        pass

    def impostor() -> tuple[PartitionWindowObservation, ...]:
        raise _LooksPending(f"{PENDING_INTEGRATION_TABLE} {CANARY}")

    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=pending,
        partition_windows=impostor,
        release=lambda env: RELEASE,
        provider=lambda: PROVIDER,
    )
    by_member = {p.member: p for p in collected.provenance}
    assert by_member["integration_connections"].error == (
        f"CollectorPending: {PENDING_INTEGRATION_TABLE}"
    )
    assert by_member["partition_windows"].error == (
        "_LooksPending while reading the partition bounds from pg_inherits"
    )
    assert CANARY not in repr(collected)
    # The provider's key id is external text as well: a malformed one is named, never echoed.
    junk = ProviderObservation("gcp", KEK, True, f"security-hmac:{CANARY}")
    pin = _run(observations(provider=junk))[KEY_VERSION_PIN]
    assert pin.failures == ("the provider's current security-hmac key id is malformed (05 KEY-03)",)
    assert CANARY not in "".join(pin.lines())


def test_operator_alerts_check_accepts_the_explicit_log_only_acknowledgement() -> None:
    """05 OPR-24 / CFG-31 / SAR-40 rev 1.27: a recipient passes; the explicit log-only
    acknowledgement passes with its summary; neither fails by name."""
    from erev_api.controls.doctor import operator_alerts

    assert operator_alerts(snapshot()).ok
    acknowledged = operator_alerts(
        snapshot(operator_alert_email_set=False, operator_alert_delivery="log-only")
    )
    assert acknowledged.ok and "log-only" in acknowledged.summary
    silent = operator_alerts(snapshot(operator_alert_email_set=False))
    assert silent.failures == (
        "neither EREV_OPERATOR_ALERT_EMAIL nor EREV_OPERATOR_ALERT_DELIVERY=log-only is set; "
        "operator alerts would go silent (05 OPR-24, CFG-31, SAR-40)",
    )


def test_lock_budget_rule_passes_the_shipped_settings_and_fails_a_default_server() -> None:
    """05 §2.7 / SAR-40 rev 1.53: ``max_locks_per_transaction × (max_connections +
    max_prepared_transactions) ≥ ⌊0.8 × max_connections⌋ × partition lock footprint + relations``.
    The shipped 4096 passes at the hosted 600 connections and the compose 100; a server left at
    PostgreSQL's default of 64 fails by name with the smallest sufficient setting."""
    from erev_api.controls.doctor import lock_budget

    hosted = lock_budget(LOCKS)
    assert hosted.lines() == [
        f"OK {LOCK_BUDGET}: 2457600 lock slots (max_locks_per_transaction 4096) cover 480 sessions "
        "× 3094 partition locks + 5044 relations = 1490164 (05 §2.7)"
    ]
    assert lock_budget(COMPOSE_LOCKS).ok
    default = lock_budget(DEFAULT_LOCKS)
    assert default.lines() == [
        f"FAIL {LOCK_BUDGET}: max_locks_per_transaction 64 × (max_connections 100 + "
        "max_prepared_transactions 0) gives 6400 lock slots; 80 sessions × 3094 partition locks + "
        "5044 relations need 252564 (05 §2.7): set max_locks_per_transaction to at least 2526 and "
        "restart PostgreSQL"
    ]
    # The boundary: 2,526 × 100 = 252,600 ≥ 252,564; 2,525 × 100 = 252,500 is short by 64.
    assert lock_budget(LockBudgetObservation(2526, 100, 0, FOOTPRINT, RELATIONS)).ok
    short = lock_budget(LockBudgetObservation(2525, 100, 0, FOOTPRINT, RELATIONS))
    assert not short.ok and "at least 2526" in short.failures[0]
    # 2,484 at 600 connections (⌈1,490,164 ÷ 600⌉); 2,483 fails and names it.
    assert lock_budget(LockBudgetObservation(2484, 600, 0, FOOTPRINT, RELATIONS)).ok
    assert (
        "at least 2484"
        in lock_budget(LockBudgetObservation(2483, 600, 0, FOOTPRINT, RELATIONS)).failures[0]
    )
    # Prepared transactions add slots (the PostgreSQL formula), never sessions.
    assert lock_budget(LockBudgetObservation(2500, 100, 2, FOOTPRINT, RELATIONS)).ok
    assert not lock_budget(LockBudgetObservation(2500, 100, 1, FOOTPRINT, RELATIONS)).ok
    # A window extension or a further index on a partitioned table raises the footprint; the
    # check follows the catalogue, so the shipped setting fails once the margin is used up.
    assert lock_budget(LockBudgetObservation(4096, 100, 0, 5056, RELATIONS)).ok
    grown = lock_budget(LockBudgetObservation(4096, 100, 0, 5057, RELATIONS))
    assert not grown.ok and "at least 4097" in grown.failures[0]


def test_lock_budget_fails_closed_without_a_measurable_footprint() -> None:
    """An uncollected observation and a catalogue without a partitioned table both fail by name;
    neither lets the rule pass on a requirement of zero."""
    from erev_api.controls.doctor import lock_budget

    assert lock_budget(None).failures == (
        "the lock table settings was not collected; the SOP-6 collector is pending",
    )
    empty = lock_budget(LockBudgetObservation(4096, 100, 0, 0, RELATIONS))
    assert empty.failures == (
        "schema erev has no partitioned table, so the partition lock footprint cannot be measured "
        "(04 §1.6; 05 §2.7)",
    )
    results = _run(observations(lock_budget=None))
    assert _failing(results.values()) == [LOCK_BUDGET]


def test_observe_lock_budget_reads_the_settings_and_the_catalogue(
    production_settings: Settings,
) -> None:
    """The collector over a fake connection: one statement, five integers; a failing catalogue
    read leaves the member uncollected and the FAIL line names the code-owned attempt, never the
    driver's message."""

    class _Row:
        def one(self) -> tuple[object, ...]:
            return ("4096", 600, 0, 3094, 5044)  # a setting arrives as text or integer

    class _Connection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> _Row:
            self.statements.append(str(statement))
            return _Row()

    connection = _Connection()
    assert observe_lock_budget(connection) == LOCKS  # type: ignore[arg-type]
    (statement,) = connection.statements
    for name in ("max_locks_per_transaction", "max_connections", "max_prepared_transactions"):
        assert f"current_setting('{name}')" in statement
    assert "pg_inherits" in statement and "pg_index" in statement and "relkind = 'p'" in statement

    def refused() -> LockBudgetObservation:
        raise RuntimeError(f"password={CANARY}")

    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=lambda: WINDOWS,
        release=lambda env: RELEASE,
        provider=lambda: PROVIDER,
        lock_budget=refused,
    )
    assert collected.lock_budget is None and CANARY not in repr(collected)
    assert _by_check(production_checks(collected, now=NOW))[LOCK_BUDGET].failures == (
        "the lock table settings was not collected: RuntimeError while reading the lock table "
        "settings and the partition catalogue",
    )


def test_email_backend_requires_the_relay_and_the_sender_under_smtp() -> None:
    """05 CFG-17, CFG-18 (SAR-40 rev 1.53): ``fake`` fails, and so does ``smtp`` that names no
    relay or no sender — every send would fail; the finding names what is missing."""
    from erev_api.controls.doctor import email_backend

    assert email_backend(snapshot()).lines() == [f"OK {EMAIL_BACKEND}: EREV_EMAIL_BACKEND is smtp"]
    assert email_backend(snapshot(email_backend="fake")).failures == (
        "EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)",
    )
    assert email_backend(snapshot(smtp_host_set=False)).failures == (
        "EREV_EMAIL_BACKEND is smtp and EREV_SMTP_HOST is not set (05 CFG-18, SAR-40)",
    )
    assert email_backend(snapshot(smtp_from_set=False)).failures == (
        "EREV_EMAIL_BACKEND is smtp and EREV_SMTP_FROM is not set (05 CFG-18, SAR-40)",
    )
    assert email_backend(snapshot(smtp_host_set=False, smtp_from_set=False)).failures == (
        "EREV_EMAIL_BACKEND is smtp and EREV_SMTP_HOST and EREV_SMTP_FROM are not set "
        "(05 CFG-18, SAR-40)",
    )


def test_email_backend_warns_on_the_private_relay_opt_in_and_fails_on_the_bundle() -> None:
    """05 SAR-40 rev 1.53 (ruling R-39): the operator's opt-in for a relay on a private or
    loopback address is a notice — ``WARN``, the check stays ok — and a certificate bundle that
    cannot be read is a failure, which outranks the notice."""
    from erev_api.controls.doctor import PRIVATE_RELAY_NOTICE, email_backend

    opted = email_backend(snapshot(smtp_private_relay=True))
    assert opted.ok and opted.failures == ()
    assert opted.lines() == [
        f"WARN {EMAIL_BACKEND}: EREV_SMTP_PRIVATE_RELAY is on: the SMTP relay may be on a private "
        "or loopback address (05 SAR-15, CFG-18)"
    ]
    assert opted.warnings == (PRIVATE_RELAY_NOTICE,)
    finding = (
        "EREV_SMTP_CA_FILE is not a readable PEM bundle of certificate authorities (05 CFG-18)"
    )
    for private in (False, True):
        unreadable = email_backend(
            snapshot(smtp_private_relay=private, smtp_ca_findings=(finding,))
        )
        assert not unreadable.ok
        assert unreadable.lines() == [f"FAIL {EMAIL_BACKEND}: {finding}"]
    # The fake backend and a missing relay are reported before either.
    fake = email_backend(snapshot(email_backend="fake", smtp_private_relay=True))
    assert fake.failures and "is fake" in fake.failures[0] and fake.warnings == ()


def test_master_keys_check_reads_the_settings_findings() -> None:
    """05 CFG-26 (SAR-40 rev 1.53): under the local provider the findings of
    ``Settings.master_key_findings`` fail the check, one line each; under ``gcp`` the keys are
    not used and the check passes whatever they hold."""
    from erev_api.controls.doctor import STARTUP_CHECK_NAMES, master_keys

    assert master_keys(compose_snapshot()).lines() == [
        f"OK {MASTER_KEYS}: the three CFG-26 master keys differ and none is a placeholder"
    ]
    repeated = (
        "EREV_ENCRYPTION_KEY and EREV_AUDIT_HMAC_MASTER_KEY hold the same value; the master keys "
        "must differ (05 CFG-26)"
    )
    failing = master_keys(compose_snapshot(master_key_findings=(PLACEHOLDER_KEY, repeated)))
    assert failing.lines() == [
        f"FAIL {MASTER_KEYS}: {PLACEHOLDER_KEY}",
        f"FAIL {MASTER_KEYS}: {repeated}",
    ]
    hosted = master_keys(snapshot(master_key_findings=(PLACEHOLDER_KEY,)))
    assert hosted.lines() == [
        f"OK {MASTER_KEYS}: EREV_KEY_PROVIDER is gcp; the CFG-26 master keys are not used"
    ]
    assert STARTUP_CHECK_NAMES == (EMAIL_BACKEND, MASTER_KEYS)
    assert set(STARTUP_CHECK_NAMES) < set(PRODUCTION_CHECK_NAMES)


def test_snapshot_carries_the_key_findings_and_never_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The snapshot observes the SMTP variables as set or unset and the master keys as findings
    that name variables; no key value is in it (the patterned fixture keys here stand in for
    placeholders)."""
    for name in list(os.environ):
        if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(name)
    environment = {
        **PRODUCTION_ENVIRONMENT,
        "EREV_KEY_PROVIDER": "local",
        "EREV_SECURITY_EVENT_HMAC_KEY": MASTER_KEYS_FIXTURE["EREV_AUDIT_HMAC_MASTER_KEY"],
    }
    for name in ("EREV_GCP_PROJECT", "EREV_GCP_KMS_KEK", "EREV_SMTP_FROM"):
        del environment[name]
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    collected = snapshot_settings(Settings(_env_file=None))
    assert (collected.smtp_host_set, collected.smtp_from_set) == (True, False)
    assert collected.master_key_findings == (
        "EREV_ENCRYPTION_KEY is a placeholder, not a generated key: fewer than 16 distinct byte "
        "values (05 CFG-26)",
        "EREV_AUDIT_HMAC_MASTER_KEY is a placeholder, not a generated key: fewer than 16 distinct "
        "byte values (05 CFG-26)",
        "EREV_SECURITY_EVENT_HMAC_KEY is a placeholder, not a generated key: fewer than 16 "
        "distinct byte values (05 CFG-26)",
        "EREV_AUDIT_HMAC_MASTER_KEY and EREV_SECURITY_EVENT_HMAC_KEY hold the same value; the "
        "master keys must differ (05 CFG-26)",
    )
    for value in MASTER_KEYS_FIXTURE.values():
        assert value not in repr(collected)


def test_index_conditions_is_a_warning_and_fails_closed_when_not_collected() -> None:
    """05 §2.7 / SAR-40 rev 1.156 (04 NC-20; dev-guide DG-KRN-DB-10): the last production
    check. A schema as the revisions build it passes. A finding of the catalogue check - an index
    built by hand whose key the policy cannot use, an index the list names that this schema does
    not have so - prints as a warning in the catalogue check's own words and never fails the
    command: it costs time at volume and never a wrong answer. An observation that was not
    collected fails by name, as with every production check."""
    from erev_api.controls.doctor import index_conditions

    assert PRODUCTION_CHECK_NAMES[-1] == INDEX_CONDITIONS == "index-conditions"
    assert INDEX_CONDITIONS not in doctor.CHECK_NAMES + doctor.STARTUP_CHECK_NAMES
    passed = index_conditions(INDEX_KEYS)
    assert passed.ok and passed.warnings == ()
    assert passed.lines() == [
        f"OK {INDEX_CONDITIONS}: every index of a table with a row-level-security policy has a "
        f"key the policy can use, or is one of the {LISTED} listed with a reason (05 §2.7)"
    ]

    found = IndexConditionsObservation(findings=(NOT_AS_LISTED, BY_HAND), listed=LISTED)
    warned = index_conditions(found)
    assert warned.ok and warned.failures == ()
    assert warned.lines() == [
        f"WARN {INDEX_CONDITIONS}: {NOT_AS_LISTED}",
        f"WARN {INDEX_CONDITIONS}: {BY_HAND}",
    ]
    results = production_checks(observations(index_conditions=found), now=NOW)
    assert _failing(results) == [] and results[-1] == warned

    assert index_conditions(None).failures == (
        "the index catalogue was not collected; the SOP-6 collector is pending",
    )
    assert _failing(_run(observations(index_conditions=None)).values()) == [INDEX_CONDITIONS]


def test_observe_index_conditions_reads_the_catalogue_check(
    production_settings: Settings,
) -> None:
    """The collector over a stand-in of the catalogue: what ``db.index_conditions.findings``
    answers on the connection it is given, as text in that module's words and order, with the
    length of its list. A failing catalogue read leaves the member uncollected and the FAIL line
    names the code-owned attempt, never the driver's message."""
    from types import SimpleNamespace

    from erev_api.db import index_conditions as catalogue_check

    def row(table: str, index: str, columns: list[str], leakproof: list[bool]) -> SimpleNamespace:
        return SimpleNamespace(
            table_name=table, index_name=index, method="btree", columns=columns, leakproof=leakproof
        )

    class _Connection:
        """Every index the list names, with a key the policy cannot use - but for one, which
        this schema has with a key it can - and one index nobody listed."""

        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> list[SimpleNamespace]:
            self.statements.append(str(statement))
            listed = [
                row("listed", name, ["tenant_id", "status"], [True, name == "ix_contract__status"])
                for name in catalogue_check.ALLOWED
            ]
            by_hand = row(
                "tenant_membership",
                "ix_tenant_membership__by_hand",
                ["tenant_id", "status"],
                [True, False],
            )
            return [*listed, by_hand]

    connection = _Connection()
    observed = observe_index_conditions(connection)  # type: ignore[arg-type]
    assert observed == IndexConditionsObservation(
        findings=(NOT_AS_LISTED, BY_HAND), listed=len(catalogue_check.ALLOWED)
    )
    assert observed.findings == tuple(
        str(finding)
        for finding in catalogue_check.findings(connection)  # type: ignore[arg-type]
    )
    assert len(connection.statements) == 2 and "pg_index" in connection.statements[0]
    assert "relrowsecurity" in connection.statements[0]

    def refused() -> IndexConditionsObservation:
        raise RuntimeError(f"password={CANARY}")

    collected = collect_production_observations(
        production_settings,
        now=NOW,
        environ={},
        defusedxml=lambda: True,
        integration_connections=lambda: (SALESFORCE,),
        partition_windows=lambda: WINDOWS,
        release=lambda env: RELEASE,
        provider=lambda: PROVIDER,
        lock_budget=lambda: LOCKS,
        index_conditions=refused,
    )
    assert collected.index_conditions is None and CANARY not in repr(collected)
    assert _by_check(production_checks(collected, now=NOW))[INDEX_CONDITIONS].failures == (
        "the index catalogue was not collected: RuntimeError while reading the index keys from "
        "the catalogue",
    )
