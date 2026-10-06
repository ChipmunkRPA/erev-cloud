"""KRN-CFG contract (dev-guide §5.1 DG-KRN-CFG-02, 03; §2.4 DG-ENV-10, 11; BUILD_SPEC FND-2)."""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest
from erev_api.config import Settings, SettingsError, get_settings, settings_override
from pydantic import ValidationError

ENCRYPTION_KEY = "0123456789abcdef" * 4
AUDIT_KEY = "fedcba9876543210" * 4
SECURITY_KEY = "13579bdf02468ace" * 4


def _url(role: str, credential: str, database: str) -> str:
    return f"postgresql://{role}:{credential}@127.0.0.1:5432/{database}"


BASE_ENVIRONMENT = {
    "EREV_ENV": "dev",
    "EREV_DB_OWNER_URL": _url("erev_owner", "dev-owner-credential", "erev"),
    "EREV_DB_APP_URL": _url("erev_app", "dev-app-credential", "erev"),
    "EREV_TEST_DB_OWNER_URL": _url("erev_owner", "test-owner-credential", "erev_test"),
    "EREV_TEST_DB_APP_URL": _url("erev_app", "test-app-credential", "erev_test"),
    "EREV_E2E_DB_OWNER_URL": _url("erev_owner", "e2e-owner-credential", "erev_e2e"),
    "EREV_E2E_DB_APP_URL": _url("erev_app", "e2e-app-credential", "erev_e2e"),
    "EREV_ENCRYPTION_KEY": ENCRYPTION_KEY,
    "EREV_AUDIT_HMAC_MASTER_KEY": AUDIT_KEY,
    "EREV_SECURITY_EVENT_HMAC_KEY": SECURITY_KEY,
}

Build = Callable[..., Settings]


@pytest.fixture
def build(monkeypatch: pytest.MonkeyPatch) -> Build:
    """Construct Settings from BASE_ENVIRONMENT plus overrides, ignoring the developer's .env."""

    def construct(**overrides: str) -> Settings:
        for name in list(os.environ):
            if name.startswith("EREV_") or name == "ANTHROPIC_API_KEY":
                monkeypatch.delenv(name)
        for name, value in {**BASE_ENVIRONMENT, **overrides}.items():
            monkeypatch.setenv(name, value)
        return Settings(_env_file=None)

    return construct


def _rejects(build: Build, variable: str, **overrides: str) -> str:
    with pytest.raises(ValidationError) as excinfo:
        build(**overrides)
    message = str(excinfo.value)
    assert variable in message
    return message


def test_krn_cfg_02_keys_must_be_64_lowercase_hex(build: Build) -> None:
    for value in (ENCRYPTION_KEY[:63], ENCRYPTION_KEY.upper()):
        message = _rejects(build, "EREV_ENCRYPTION_KEY", EREV_ENCRYPTION_KEY=value)
        assert "64 lowercase hexadecimal characters" in message
        leaked = [i for i in range(len(value) - 7) if value[i : i + 8] in message]
        assert not leaked, "the validation message contains part of the key value"
    assert build().encryption_key.get_secret_value() == ENCRYPTION_KEY


def test_krn_cfg_02_anthropic_provider_rules(build: Build) -> None:
    anthropic = {"EREV_AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "not-a-real-provider-key"}
    _rejects(build, "EREV_AI_PROVIDER", EREV_ENV="test", **anthropic)
    _rejects(build, "EREV_AI_PROVIDER", EREV_ENV="e2e", **anthropic)
    _rejects(build, "EREV_PERF_RUN", EREV_ENV="dev", EREV_PERF_RUN="1", **anthropic)
    _rejects(build, "ANTHROPIC_API_KEY", EREV_ENV="dev", EREV_AI_PROVIDER="anthropic")
    _rejects(
        build,
        "ANTHROPIC_API_KEY",
        EREV_ENV="dev",
        EREV_AI_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="",
    )
    assert build(EREV_ENV="dev", **anthropic).ai_provider == "anthropic"
    assert build(EREV_ENV="test").ai_provider == "fake"


def test_krn_cfg_02_public_origin_loopback(build: Build) -> None:
    _rejects(build, "EREV_PUBLIC_ORIGIN", EREV_PUBLIC_ORIGIN="http://localhost:5270")
    assert (
        build(EREV_PUBLIC_ORIGIN="http://127.0.0.1:5279").public_origin == "http://127.0.0.1:5279"
    )
    message = _rejects(
        build,
        "EREV_PUBLIC_ORIGIN",
        EREV_ENV="production",
        EREV_PUBLIC_ORIGIN="https://erev.example/path",
    )
    assert "^https?://[^/?#]+$" in message
    production = build(
        EREV_ENV="production",
        EREV_PUBLIC_ORIGIN="https://erev.example",
        EREV_SECURITY_HMAC_SECRET_VERSION="1",
    )
    assert production.public_origin == "https://erev.example"


def test_krn_cfg_02_comma_lists(build: Build) -> None:
    assert build(EREV_WORKER_QUEUES="compute,close").worker_queues == ("compute", "close")
    assert build(EREV_WORKER_QUEUES="").worker_queues == ()
    _rejects(build, "EREV_WORKER_QUEUES", EREV_WORKER_QUEUES="gpu")
    origins = build(EREV_CORS_ORIGINS="http://127.0.0.1:5270, http://127.0.0.1:5279")
    assert origins.cors_origins == ("http://127.0.0.1:5270", "http://127.0.0.1:5279")
    json_like = '["http://127.0.0.1:5270"]'
    assert build(EREV_CORS_ORIGINS=json_like).cors_origins == (json_like,)
    assert build(EREV_CORS_ORIGINS="").cors_origins == ()


def test_krn_cfg_02_local_and_fake_required_outside_production(build: Build) -> None:
    _rejects(build, "EREV_KEY_PROVIDER", EREV_ENV="test", EREV_KEY_PROVIDER="gcp")
    _rejects(build, "EREV_EMAIL_BACKEND", EREV_ENV="test", EREV_EMAIL_BACKEND="smtp")
    assert (
        build(
            EREV_ENV="production",
            EREV_KEY_PROVIDER="local",
            EREV_SECURITY_HMAC_SECRET_VERSION="1",
        ).key_provider
        == "local"
    )
    # Lane P2: the hosted provider is accepted only with its CFG-13 configuration (fail closed).
    hosted = build(
        EREV_ENV="production",
        EREV_KEY_PROVIDER="gcp",
        EREV_GCP_PROJECT="erev-staging-example",
        EREV_GCP_KMS_KEK=KMS_KEK,
        EREV_SECURITY_HMAC_SECRET_VERSION="1",
    )
    assert hosted.key_provider == "gcp"


def test_krn_cfg_02_ranges(build: Build) -> None:
    _rejects(build, "EREV_API_PORT", EREV_API_PORT="1023")
    assert build(EREV_API_PORT="8190").api_port == 8190
    _rejects(build, "EREV_METRICS_TOKEN", EREV_METRICS_ENABLED="true")
    _rejects(build, "EREV_TRUSTED_PROXY_HOPS", EREV_TRUSTED_PROXY_HOPS="6")
    _rejects(build, "EREV_WORKER_CONCURRENCY", EREV_WORKER_CONCURRENCY="65")
    _rejects(build, "EREV_ENGINE_PROCESSES", EREV_ENGINE_PROCESSES="0")
    assert build(EREV_ENGINE_PROCESSES="").engine_processes is None


def test_cfg_29_the_dataset_freezes_idle_bound_has_a_default_and_a_range(build: Build) -> None:
    """05 CFG-29 and TXN-03 rev 1.121 (supervisor rulings R-116 (h) and R-119 (d)): the bound the
    transactions of a dataset freeze set on their idle time is 15 minutes unless configured, and
    is validated at start — never below the 60 s of the connection it overrides, never above a
    day."""
    assert build().dataset_freeze_idle_seconds == 900
    assert build(EREV_DATASET_FREEZE_IDLE_SECONDS="60").dataset_freeze_idle_seconds == 60
    assert build(EREV_DATASET_FREEZE_IDLE_SECONDS="86400").dataset_freeze_idle_seconds == 86_400
    for value in ("59", "86401", "0", "-1"):
        message = _rejects(
            build, "EREV_DATASET_FREEZE_IDLE_SECONDS", EREV_DATASET_FREEZE_IDLE_SECONDS=value
        )
        assert "must lie in 60 to 86400" in message


def test_cfg_29_a_migrations_statement_timeout_has_a_default_and_a_range(build: Build) -> None:
    """05 CFG-29 and TXN-03 rev 1.199 (item MIGRATION-STATEMENT-TIMEOUT-1): the statement timeout
    of a migration's connection is 30 minutes unless configured — the default of the hosted
    migration job's own time limit — and is validated at start: never below the 30 s of a
    request, which it replaces, never above a day."""
    assert build().migration_statement_timeout_seconds == 1800
    name = "EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS"
    assert build(**{name: "30"}).migration_statement_timeout_seconds == 30
    assert build(**{name: "86400"}).migration_statement_timeout_seconds == 86_400
    for value in ("29", "86401", "0", "-1"):
        assert "must lie in 30 to 86400" in _rejects(build, name, **{name: value})


def test_krn_cfg_02_paths_resolve_against_repo_root(build: Build) -> None:
    from erev_api.config import REPO_ROOT

    settings = build()
    assert settings.file_root == REPO_ROOT / ".data" / "files"
    assert settings.run_dir == REPO_ROOT / ".run"


def test_dg_env_10_database_pair_by_env(build: Build) -> None:
    settings = build(EREV_ENV="test")
    assert settings.database_name() == "erev_test"
    assert settings.app_database_url().startswith("postgresql+psycopg://erev_app:")
    assert settings.owner_database_url().startswith("postgresql+psycopg://erev_owner:")
    assert build(EREV_ENV="e2e").database_name() == "erev_e2e"
    assert build(EREV_ENV="dev").database_name() == "erev"
    _rejects(build, "EREV_TEST_DB_APP_URL", EREV_ENV="test", EREV_TEST_DB_APP_URL="")


def test_dg_env_13_database_outside_allow_list_names_database_only(build: Build) -> None:
    settings = build(EREV_DB_APP_URL=_url("erev_app", "dev-app-credential", "postgres"))
    with pytest.raises(SettingsError) as excinfo:
        settings.app_database_url()
    message = str(excinfo.value)
    assert "EREV_DB_APP_URL" in message and "'postgres'" in message
    assert "dev-app-credential" not in message and "erev_app" not in message


def test_krn_cfg_03_repr_contains_no_secret() -> None:
    previous_key = os.environ.get("EREV_ENCRYPTION_KEY")
    credentials = ("test-owner-credential", "test-app-credential")
    with settings_override(
        env="test",
        encryption_key=ENCRYPTION_KEY,
        audit_hmac_master_key=AUDIT_KEY,
        security_event_hmac_key=SECURITY_KEY,
        test_db_owner_url=_url("erev_owner", credentials[0], "erev_test"),
        test_db_app_url=_url("erev_app", credentials[1], "erev_test"),
    ) as settings:
        assert settings is get_settings()
        text = repr(get_settings())
    secrets = {
        "EREV_ENCRYPTION_KEY": ENCRYPTION_KEY,
        "EREV_AUDIT_HMAC_MASTER_KEY": AUDIT_KEY,
        "EREV_SECURITY_EVENT_HMAC_KEY": SECURITY_KEY,
        "test owner credential": credentials[0],
        "test app credential": credentials[1],
    }
    leaked = sorted(name for name, value in secrets.items() if value in text)
    assert not leaked, f"repr(get_settings()) contains secret values of {leaked}"
    assert os.environ.get("EREV_ENCRYPTION_KEY") == previous_key


# ---- lane P2: hosted composition root (05 CFG-05, CFG-07, CFG-11, CFG-13, CFG-26; DG-ENV-10 as
# amended; deployment audit DEP-B) --------------------------------------------------------------

KMS_KEK = (
    "projects/erev-staging-example/locations/europe-west1/keyRings/erev/cryptoKeys/erev-app-kek"
)
HOSTED_ENVIRONMENT = {
    "EREV_ENV": "production",
    "EREV_KEY_PROVIDER": "gcp",
    "EREV_GCP_PROJECT": "erev-staging-example",
    "EREV_GCP_KMS_KEK": KMS_KEK,
    "EREV_SECURITY_HMAC_SECRET_VERSION": "4",
    "EREV_PUBLIC_ORIGIN": "https://erev.example.com",
    "EREV_FILE_BACKEND": "gcs",
    "EREV_GCS_FILES_BUCKET": "erev-files-staging",
    "EREV_GCS_AUDIT_DIGEST_BUCKET": "erev-audit-digests-staging",
    # The platform injects the app URL from a pinned secret version (SAR-25); no owner URL and
    # no master keys reach a hosted api or worker.
    "EREV_DB_OWNER_URL": "",
    "EREV_ENCRYPTION_KEY": "",
    "EREV_AUDIT_HMAC_MASTER_KEY": "",
    "EREV_SECURITY_EVENT_HMAC_KEY": "",
}


def test_p2_hosted_production_starts_without_master_keys_or_owner_url(build: Build) -> None:
    settings = build(**HOSTED_ENVIRONMENT)
    assert settings.key_provider == "gcp" and settings.file_backend == "gcs"
    assert settings.encryption_key is None
    assert settings.audit_hmac_master_key is None
    assert settings.security_event_hmac_key is None
    assert settings.gcs_files_bucket == "erev-files-staging"
    assert settings.gcs_audit_digest_bucket == "erev-audit-digests-staging"
    assert settings.security_hmac_version() == 4
    assert build().security_hmac_version() == 1
    assert build(EREV_SECURITY_HMAC_SECRET_VERSION="2").security_hmac_version() == 2
    assert settings.database_name() == "erev"
    assert settings.app_database_url().startswith("postgresql+psycopg://erev_app:")
    # Owner/app separation: an owner-only command without the owner URL fails closed by name.
    with pytest.raises(SettingsError, match="EREV_DB_OWNER_URL") as excinfo:
        settings.owner_database_url()
    assert "credential" not in str(excinfo.value)
    assert "erev_app" not in repr(settings) and "credential" not in repr(settings)


def test_p2_local_provider_requires_the_master_keys(build: Build) -> None:
    for field in (
        "EREV_ENCRYPTION_KEY",
        "EREV_AUDIT_HMAC_MASTER_KEY",
        "EREV_SECURITY_EVENT_HMAC_KEY",
    ):
        message = _rejects(build, field, **{field: ""})
        assert "must be set when EREV_KEY_PROVIDER is local" in message


def test_p2_gcp_provider_requires_project_and_well_formed_kek(build: Build) -> None:
    message = _rejects(build, "EREV_GCP_KMS_KEK", **{**HOSTED_ENVIRONMENT, "EREV_GCP_KMS_KEK": ""})
    assert "EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT and EREV_GCP_KMS_KEK" in message
    _rejects(build, "EREV_GCP_PROJECT", **{**HOSTED_ENVIRONMENT, "EREV_GCP_PROJECT": ""})
    malformed = "not-a-kms-resource-name-7f3a"
    message = _rejects(
        build, "EREV_GCP_KMS_KEK", **{**HOSTED_ENVIRONMENT, "EREV_GCP_KMS_KEK": malformed}
    )
    assert "cryptoKeys/<key>" in message and malformed not in message
    _rejects(
        build, "EREV_GCP_SECRET_PREFIX", **{**HOSTED_ENVIRONMENT, "EREV_GCP_SECRET_PREFIX": " "}
    )
    _rejects(
        build,
        "EREV_SECURITY_HMAC_SECRET_VERSION",
        **{**HOSTED_ENVIRONMENT, "EREV_SECURITY_HMAC_SECRET_VERSION": ""},
    )
    _rejects(build, "EREV_SECURITY_HMAC_SECRET_VERSION", EREV_SECURITY_HMAC_SECRET_VERSION="0")
    # 05 KEY-03 rev 1.17: the pin is a production requirement for every provider; `latest` and other
    # non-numeric values fail construction naming the variable, never the value.
    compose_without_pin = _rejects(
        build,
        "EREV_SECURITY_HMAC_SECRET_VERSION",
        EREV_ENV="production",
        EREV_PUBLIC_ORIGIN="http://127.0.0.1:8195",
    )
    assert "must be set when EREV_ENV is production" in compose_without_pin
    for bad in ("latest", "v2", "2.0"):
        message = _rejects(
            build,
            "EREV_SECURITY_HMAC_SECRET_VERSION",
            EREV_ENV="production",
            EREV_PUBLIC_ORIGIN="http://127.0.0.1:8195",
            EREV_SECURITY_HMAC_SECRET_VERSION=bad,
        )
        assert bad not in message.replace("EREV_SECURITY_HMAC_SECRET_VERSION", "")
    # dev, test and e2e still refuse the hosted provider (DG-KRN-KEY-03).
    _rejects(build, "EREV_KEY_PROVIDER", EREV_KEY_PROVIDER="gcp")


def test_p2_file_backend_rules(build: Build) -> None:
    local_environment_message = _rejects(
        build,
        "EREV_FILE_BACKEND",
        EREV_FILE_BACKEND="gcs",
        EREV_GCS_FILES_BUCKET="erev-files-x",
        EREV_GCS_AUDIT_DIGEST_BUCKET="erev-digests-x",
    )
    assert "must be local when EREV_ENV is dev, test or e2e" in local_environment_message
    message = _rejects(
        build, "EREV_GCS_FILES_BUCKET", **{**HOSTED_ENVIRONMENT, "EREV_GCS_FILES_BUCKET": ""}
    )
    assert "requires EREV_GCS_FILES_BUCKET and EREV_GCS_AUDIT_DIGEST_BUCKET" in message
    message = _rejects(
        build,
        "EREV_GCS_FILES_BUCKET",
        **{**HOSTED_ENVIRONMENT, "EREV_GCS_AUDIT_DIGEST_BUCKET": "erev-files-staging"},
    )
    assert "must name different buckets" in message
    # A bucket named while the backend is local is contradictory and refused (never a silent
    # fall-back to instance-local storage, OPR-09).
    message = _rejects(build, "EREV_GCS_FILES_BUCKET", EREV_GCS_FILES_BUCKET="erev-files-x")
    assert "is set but EREV_FILE_BACKEND is local" in message
    message = _rejects(
        build,
        "EREV_GCS_AUDIT_DIGEST_BUCKET",
        **{**HOSTED_ENVIRONMENT, "EREV_GCS_AUDIT_DIGEST_BUCKET": "Not A Bucket"},
    )
    assert "must be a Cloud Storage bucket name" in message
    assert build().file_backend == "local"


def test_p2_production_requires_the_app_url_only(build: Build) -> None:
    message = _rejects(build, "EREV_DB_APP_URL", **{**HOSTED_ENVIRONMENT, "EREV_DB_APP_URL": ""})
    assert "EREV_DB_APP_URL must be set when EREV_ENV is production" in message
    assert "EREV_DB_OWNER_URL" not in message
    # Compose (production with the local provider) keeps reading both URLs from the environment.
    compose = build(
        EREV_ENV="production",
        EREV_PUBLIC_ORIGIN="http://127.0.0.1:8195",
        EREV_DB_OWNER_URL="",
        EREV_SECURITY_HMAC_SECRET_VERSION="1",
    )
    with pytest.raises(SettingsError, match="EREV_DB_OWNER_URL"):
        compose.owner_database_url()
    # The local environments still need the whole pair (DG-ENV-10 unchanged for dev, test, e2e).
    _rejects(build, "EREV_DB_OWNER_URL", EREV_DB_OWNER_URL="")
    _rejects(build, "EREV_TEST_DB_OWNER_URL", EREV_ENV="test", EREV_TEST_DB_OWNER_URL="")
