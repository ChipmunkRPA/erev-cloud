"""Configuration kernel KRN-CFG (docs/dev-guide.md §5.1, §2.3, §2.4; docs/05-ARCHITECTURE.md §2.8).

Settings are read once per process into a frozen object. Validation failures name the variable
and the rule, never the value (DG-KRN-CFG-02); secrets are ``SecretStr`` (DG-KRN-CFG-03).

Hosted production (``EREV_ENV=production`` with ``EREV_KEY_PROVIDER=gcp``, 05 CFG-11, CFG-13)
selects the Cloud KMS and Secret Manager providers for keys only. The database URLs are injected
into the process environment by the platform from pinned Secret Manager versions
(``secret_key_ref``, 05 SAR-25, DPL-31), so ``EREV_DB_APP_URL`` is read from the environment in
every environment and the three CFG-26 master keys are required only by the local provider. The
file store follows ``EREV_FILE_BACKEND`` (CFG-05): ``gcs`` names the buckets of CFG-07 and is
refused outside production.
"""

from __future__ import annotations

import os
import re
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# The eight job queues of docs/05-ARCHITECTURE.md §5.6 (DG-KRN-JOB-10, DG-KRN-JOB-11).
WORKER_QUEUE_NAMES: Final[tuple[str, ...]] = (
    "compute",
    "imports",
    "close",
    "outbox",
    "reports",
    "maintenance",
    "integrations",
    "ai",
)

_MASTER_KEY = re.compile(r"[0-9a-f]{64}")
_PUBLIC_ORIGIN = re.compile(r"^https?://[^/?#]+$")
# A Cloud KMS key resource name (05 KEY-04 `erev-app-kek`); KMS selects the primary version.
_KMS_KEY = re.compile(r"^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$")
# A Cloud Storage bucket name: 3 to 222 lowercase letters, digits, dots, hyphens and underscores.
_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
_LOOPBACK_ORIGIN_PREFIX: Final = "http://127.0.0.1:"
# DG-ENV-13: the one database allow-list; scripts/check_env.py holds a copy compared by test.
ALLOWED_DATABASE: Final = re.compile(r"^(erev|erev_test|erev_e2e|erev_rv_[a-z0-9_]+)$")
# libpq URL query parameters that can select a database other than the URL path (D-78).
REDIRECTING_QUERY_PARAMETERS: Final = ("dbname", "service", "servicefile")
_LOG_LEVELS: Final = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_RANGES: Final[dict[str, tuple[int, int]]] = {
    "api_port": (1024, 65535),
    "web_port": (1024, 65535),
    "e2e_api_port": (1024, 65535),
    "e2e_web_port": (1024, 65535),
    "trusted_proxy_hops": (0, 5),
    "worker_concurrency": (1, 64),
    "worker_probe_port": (1, 65535),
    "engine_processes": (1, 64),
    "security_hmac_secret_version": (1, 1_000_000),
    "dataset_freeze_idle_seconds": (60, 86_400),
    "migration_statement_timeout_seconds": (30, 86_400),
}


class SettingsError(RuntimeError):
    """A configuration value cannot be used; the message names the variable, never its value."""


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    E2E = "e2e"
    PRODUCTION = "production"


# 05 SAR-09, SAR-40: the hosts of an origin that only the machine itself reaches. The session
# cookie goes without Secure to an http origin on one of them, and to no other origin.
LOOPBACK_ORIGIN_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1"})
# DG-ENV-10: the environments that run on one machine with the in-process mocks.
LOCAL_ENVIRONMENTS: Final = frozenset({Environment.DEV, Environment.TEST, Environment.E2E})
# The CFG-26 master keys, required by the local key provider only (DG-KRN-KEY-01).
MASTER_KEY_FIELDS: Final = ("encryption_key", "audit_hmac_master_key", "security_event_hmac_key")
# 05 CFG-26 (rev 1.53): a generated key has about 30 distinct byte values among its 32; a
# documentation placeholder such as 00…01 has two and a repeated 8-byte pattern eight.
MASTER_KEY_MIN_DISTINCT_BYTES: Final = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    env: Environment = Field(Environment.DEV, validation_alias="EREV_ENV")
    db_owner_url: SecretStr | None = Field(None, validation_alias="EREV_DB_OWNER_URL")
    db_app_url: SecretStr | None = Field(None, validation_alias="EREV_DB_APP_URL")
    test_db_owner_url: SecretStr | None = Field(None, validation_alias="EREV_TEST_DB_OWNER_URL")
    test_db_app_url: SecretStr | None = Field(None, validation_alias="EREV_TEST_DB_APP_URL")
    e2e_db_owner_url: SecretStr | None = Field(None, validation_alias="EREV_E2E_DB_OWNER_URL")
    e2e_db_app_url: SecretStr | None = Field(None, validation_alias="EREV_E2E_DB_APP_URL")
    api_port: int = Field(8190, validation_alias="EREV_API_PORT")
    web_port: int = Field(5270, validation_alias="EREV_WEB_PORT")
    e2e_api_port: int = Field(8199, validation_alias="EREV_E2E_API_PORT")
    e2e_web_port: int = Field(5279, validation_alias="EREV_E2E_WEB_PORT")
    # CFG-26: required when EREV_KEY_PROVIDER is local; unused, and so not required, under gcp.
    encryption_key: SecretStr | None = Field(None, validation_alias="EREV_ENCRYPTION_KEY")
    audit_hmac_master_key: SecretStr | None = Field(
        None, validation_alias="EREV_AUDIT_HMAC_MASTER_KEY"
    )
    security_event_hmac_key: SecretStr | None = Field(
        None, validation_alias="EREV_SECURITY_EVENT_HMAC_KEY"
    )
    demo_password: SecretStr | None = Field(None, validation_alias="EREV_DEMO_PASSWORD")
    demo_totp_secret: SecretStr | None = Field(None, validation_alias="EREV_DEMO_TOTP_SECRET")
    ai_provider: Literal["fake", "anthropic"] = Field("fake", validation_alias="EREV_AI_PROVIDER")
    ai_kill_switch: bool = Field(False, validation_alias="EREV_AI_KILL_SWITCH")
    anthropic_api_key: SecretStr | None = Field(None, validation_alias="ANTHROPIC_API_KEY")
    file_root: Path = Field(Path(".data/files"), validation_alias="EREV_FILE_ROOT")
    # 05 CFG-05 and CFG-07 (bucket variable names as the Terraform module injects them, lane P3).
    file_backend: Literal["local", "gcs"] = Field("local", validation_alias="EREV_FILE_BACKEND")
    gcs_files_bucket: str | None = Field(None, validation_alias="EREV_GCS_FILES_BUCKET")
    gcs_audit_digest_bucket: str | None = Field(
        None, validation_alias="EREV_GCS_AUDIT_DIGEST_BUCKET"
    )
    log_level: str = Field("INFO", validation_alias="EREV_LOG_LEVEL")
    log_format: Literal["json", "console"] = Field("json", validation_alias="EREV_LOG_FORMAT")
    run_dir: Path = Field(Path(".run"), validation_alias="EREV_RUN_DIR")
    public_origin: str = Field("http://127.0.0.1:5270", validation_alias="EREV_PUBLIC_ORIGIN")
    cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        (), validation_alias="EREV_CORS_ORIGINS"
    )
    trusted_proxy_hops: int = Field(0, validation_alias="EREV_TRUSTED_PROXY_HOPS")
    worker_concurrency: int = Field(4, validation_alias="EREV_WORKER_CONCURRENCY")
    # 05 CFG-32 (rev 1.28): the worker probe listener opens only when set; Cloud Run injects PORT.
    worker_probe_port: int | None = Field(
        None, validation_alias=AliasChoices("EREV_WORKER_PROBE_PORT", "PORT")
    )
    worker_queues: Annotated[tuple[str, ...], NoDecode] = Field(
        (), validation_alias="EREV_WORKER_QUEUES"
    )
    key_provider: Literal["local", "gcp"] = Field("local", validation_alias="EREV_KEY_PROVIDER")
    # Hosted-only (05 CFG-13); absent from .env.example (dev-guide §2.3 note).
    gcp_project: str | None = Field(None, validation_alias="EREV_GCP_PROJECT")
    gcp_kms_kek: str | None = Field(None, validation_alias="EREV_GCP_KMS_KEK")
    gcp_secret_prefix: str = Field("erev-", validation_alias="EREV_GCP_SECRET_PREFIX")
    # 05 KEY-03 (rev 1.17): the pinned version of `security-hmac` that signs new security events,
    # required in production; historical events verify under the key id stored on their row.
    security_hmac_secret_version: int | None = Field(
        None, validation_alias="EREV_SECURITY_HMAC_SECRET_VERSION"
    )
    email_backend: Literal["fake", "smtp"] = Field("fake", validation_alias="EREV_EMAIL_BACKEND")
    # 05 CFG-18: the smtp backend only; absent from .env.example like the hosted variables.
    smtp_host: str | None = Field(None, validation_alias="EREV_SMTP_HOST")
    smtp_port: int = Field(587, validation_alias="EREV_SMTP_PORT")
    smtp_username: str | None = Field(None, validation_alias="EREV_SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(None, validation_alias="EREV_SMTP_PASSWORD")
    smtp_from: str | None = Field(None, validation_alias="EREV_SMTP_FROM")
    # 05 CFG-18 rev 1.53 (supervisor ruling R-39): the operator's opt-in that admits an SMTP relay
    # on a private-use or loopback address (SAR-15), and the PEM bundle of the certificate
    # authorities the relay's certificate is verified against instead of the system trust store.
    smtp_private_relay: bool = Field(False, validation_alias="EREV_SMTP_PRIVATE_RELAY")
    smtp_ca_file: Path | None = Field(None, validation_alias="EREV_SMTP_CA_FILE")
    # 05 CFG-31 (rev 1.27): the operator-alert recipient and the explicit log-only acknowledgement;
    # hosted variables, absent from .env.example (OPR-24; SAR-40 `operator-alerts`).
    operator_alert_email: str | None = Field(None, validation_alias="EREV_OPERATOR_ALERT_EMAIL")
    operator_alert_delivery: Literal["log-only"] | None = Field(
        None, validation_alias="EREV_OPERATOR_ALERT_DELIVERY"
    )
    metrics_enabled: bool = Field(False, validation_alias="EREV_METRICS_ENABLED")
    metrics_token: SecretStr | None = Field(None, validation_alias="EREV_METRICS_TOKEN")
    perf_run: bool = Field(False, validation_alias="EREV_PERF_RUN")
    engine_processes: int | None = Field(None, validation_alias="EREV_ENGINE_PROCESSES")
    # 05 TXN-03 and CFG-29 (rev 1.121; supervisor rulings R-116 (h) and R-119 (d)): the
    # idle-in-transaction bound the transactions of a dataset freeze set for themselves. A freeze
    # works on two connections and each is idle while the other works; the connection default of
    # 60 s ended a lock decision, or a close run's step, while a dataset was produced.
    dataset_freeze_idle_seconds: int = Field(
        900, validation_alias="EREV_DATASET_FREEZE_IDLE_SECONDS"
    )
    # 05 TXN-03 and CFG-29 (rev 1.199; item MIGRATION-STATEMENT-TIMEOUT-1): the statement timeout
    # of a migration's connection (``db.session.migration_engine``), in place of the request's
    # 30 s: a revision's statement — a foreign key added over a partitioned table — may run long.
    # The default is that of the hosted migration job's own time limit; an operator raises it for
    # one run. The lock timeout of that connection is not a setting: it stays 10 s.
    migration_statement_timeout_seconds: int = Field(
        1800, validation_alias="EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS"
    )

    @classmethod
    def variable_name(cls, field_name: str) -> str:
        """The environment variable that feeds ``field_name``."""
        alias = cls.model_fields[field_name].validation_alias
        return alias if isinstance(alias, str) else field_name.upper()

    @field_validator(
        "db_owner_url",
        "db_app_url",
        "test_db_owner_url",
        "test_db_app_url",
        "e2e_db_owner_url",
        "e2e_db_app_url",
        "demo_password",
        "demo_totp_secret",
        "anthropic_api_key",
        "metrics_token",
        "engine_processes",
        "security_hmac_secret_version",
        *MASTER_KEY_FIELDS,
        "gcp_project",
        "gcp_kms_kek",
        "gcs_files_bucket",
        "gcs_audit_digest_bucket",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "smtp_from",
        "smtp_ca_file",
        "operator_alert_email",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # `.env.example` carries `ANTHROPIC_API_KEY=` and `EREV_METRICS_TOKEN=`: blank means unset.
        # Compose interpolates an unset `${EREV_COMPOSE_SMTP_USERNAME}` to the empty string too.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("security_hmac_secret_version", mode="before")
    @classmethod
    def _pinned_version_format(cls, value: object) -> object:
        # 05 KEY-03 rev 1.17: a deployment pin is a version number and nothing else; pydantic's lax
        # integer parsing would otherwise accept "2.0", so the string form is checked first.
        if isinstance(value, str) and not re.fullmatch(r"[1-9][0-9]*", value.strip()):
            raise ValueError(
                "EREV_SECURITY_HMAC_SECRET_VERSION must be a positive integer version number; "
                "a version alias is refused (05 KEY-03)"
            )
        return value

    @field_validator(*MASTER_KEY_FIELDS)
    @classmethod
    def _master_key_format(cls, value: SecretStr | None, info: ValidationInfo) -> SecretStr | None:
        if value is not None and not _MASTER_KEY.fullmatch(value.get_secret_value()):
            name = cls.variable_name(str(info.field_name))
            raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("gcp_kms_kek")
    @classmethod
    def _kms_key_format(cls, value: str | None) -> str | None:
        # The value is a resource name, not a secret; the message still names only the rule.
        if value is not None and not _KMS_KEY.fullmatch(value.strip()):
            raise ValueError(
                "EREV_GCP_KMS_KEK must be a Cloud KMS key resource name "
                "projects/<project>/locations/<location>/keyRings/<ring>/cryptoKeys/<key>"
            )
        return None if value is None else value.strip()

    @field_validator("gcs_files_bucket", "gcs_audit_digest_bucket")
    @classmethod
    def _bucket_name_format(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not _BUCKET_NAME.fullmatch(value.strip()):
            name = cls.variable_name(str(info.field_name))
            raise ValueError(f"{name} must be a Cloud Storage bucket name")
        return None if value is None else value.strip()

    @field_validator(*_RANGES)
    @classmethod
    def _within_range(cls, value: int | None, info: ValidationInfo) -> int | None:
        field_name = str(info.field_name)
        low, high = _RANGES[field_name]
        if value is not None and not low <= value <= high:
            raise ValueError(f"{cls.variable_name(field_name)} must lie in {low} to {high}")
        return value

    @field_validator("file_root", "run_dir")
    @classmethod
    def _resolve_against_repo_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

    @field_validator("smtp_private_relay", mode="before")
    @classmethod
    def _blank_is_off(cls, value: object) -> object:
        # Compose interpolates an unset `${EREV_COMPOSE_SMTP_PRIVATE_RELAY}` to the empty string:
        # an environment file written before rev 1.53 leaves the opt-in off.
        if isinstance(value, str) and not value.strip():
            return False
        return value

    @field_validator("smtp_ca_file")
    @classmethod
    def _resolve_optional_against_repo_root(cls, value: Path | None) -> Path | None:
        return value if value is None or value.is_absolute() else REPO_ROOT / value

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _LOG_LEVELS:
            raise ValueError("EREV_LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return level

    @field_validator("cors_origins", "worker_queues", mode="before")
    @classmethod
    def _comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("worker_queues")
    @classmethod
    def _known_queues(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(queue not in WORKER_QUEUE_NAMES for queue in value):
            allowed = ", ".join(WORKER_QUEUE_NAMES)
            raise ValueError(f"EREV_WORKER_QUEUES may name only the queues {allowed}")
        return value

    @field_validator("public_origin")
    @classmethod
    def _origin_pattern(cls, value: str) -> str:
        if not _PUBLIC_ORIGIN.fullmatch(value):
            raise ValueError("EREV_PUBLIC_ORIGIN must match ^https?://[^/?#]+$")
        return value

    @model_validator(mode="after")
    def _cross_field_rules(self) -> Settings:
        failures: list[str] = []
        if self.ai_provider == "anthropic":
            if self.env in (Environment.TEST, Environment.E2E):
                failures.append(
                    "EREV_AI_PROVIDER=anthropic is not allowed when EREV_ENV is test or e2e"
                )
            if self.perf_run:
                failures.append("EREV_AI_PROVIDER=anthropic is not allowed when EREV_PERF_RUN=1")
            if self.anthropic_api_key is None:
                failures.append("EREV_AI_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        if self.env in LOCAL_ENVIRONMENTS:
            if not self.public_origin.startswith(_LOOPBACK_ORIGIN_PREFIX):
                failures.append(
                    "EREV_PUBLIC_ORIGIN must start with http://127.0.0.1: when EREV_ENV is "
                    "dev, test or e2e"
                )
            if self.key_provider != "local":
                failures.append("EREV_KEY_PROVIDER must be local when EREV_ENV is dev, test or e2e")
            if self.email_backend != "fake":
                failures.append("EREV_EMAIL_BACKEND must be fake when EREV_ENV is dev, test or e2e")
        if self.metrics_enabled and self.metrics_token is None:
            failures.append("EREV_METRICS_ENABLED=true requires EREV_METRICS_TOKEN")
        failures += self._key_provider_rules()
        failures += self._file_backend_rules()
        # 05 KEY-03 (rev 1.17): the platform security key version is a deployment pin in production.
        if self.env is Environment.PRODUCTION and self.security_hmac_secret_version is None:
            failures.append(
                "EREV_SECURITY_HMAC_SECRET_VERSION must be set when EREV_ENV is production (the "
                "pinned version of the platform security key, 05 KEY-03)"
            )
        # DG-ENV-10 as amended (lane P2): the platform injects the database URLs from pinned
        # secret versions, so the app URL is read from the environment everywhere. The owner URL
        # is needed only by the processes that migrate; hosted api and worker never hold it
        # (DPL-33 least privilege), while the local environments keep the whole pair.
        (owner_name, owner_value), (app_name, app_value) = self._database_pair()
        if app_value is None:
            failures.append(f"{app_name} must be set when EREV_ENV is {self.env.value}")
        if owner_value is None and self.env in LOCAL_ENVIRONMENTS:
            failures.append(f"{owner_name} must be set when EREV_ENV is {self.env.value}")
        if failures:
            raise ValueError("; ".join(failures))
        return self

    def _key_provider_rules(self) -> list[str]:
        """CFG-11, CFG-13, CFG-26: each provider needs exactly its own configuration."""
        failures: list[str] = []
        if self.key_provider == "local":
            for field_name in MASTER_KEY_FIELDS:
                if getattr(self, field_name) is None:
                    name = self.variable_name(field_name)
                    failures.append(f"{name} must be set when EREV_KEY_PROVIDER is local")
        else:
            if self.gcp_project is None or self.gcp_kms_kek is None:
                failures.append(
                    "EREV_KEY_PROVIDER=gcp requires EREV_GCP_PROJECT and EREV_GCP_KMS_KEK"
                )
            if not self.gcp_secret_prefix.strip():
                failures.append(
                    "EREV_GCP_SECRET_PREFIX must not be blank under EREV_KEY_PROVIDER=gcp"
                )
        return failures

    def master_key_findings(self) -> tuple[str, ...]:
        """Why the CFG-26 master keys are unfit for production (05 CFG-26 rev 1.53; SAR-40
        ``master-keys``): a key with fewer than ``MASTER_KEY_MIN_DISTINCT_BYTES`` distinct byte
        values is a placeholder, not a generated key, and two keys with one value make one
        purpose's key the key of another. Each finding names the variables, never a value. The
        keys are unused, and so unjudged, under the ``gcp`` provider."""
        if self.key_provider != "local":
            return ()
        findings: list[str] = []
        present: list[tuple[str, str]] = []
        for field_name in MASTER_KEY_FIELDS:
            value = getattr(self, field_name)
            if value is None:
                continue
            name = self.variable_name(field_name)
            text = value.get_secret_value()
            present.append((name, text))
            if len(set(bytes.fromhex(text))) < MASTER_KEY_MIN_DISTINCT_BYTES:
                findings.append(
                    f"{name} is a placeholder, not a generated key: fewer than "
                    f"{MASTER_KEY_MIN_DISTINCT_BYTES} distinct byte values (05 CFG-26)"
                )
        for index, (name, text) in enumerate(present):
            for other, other_text in present[index + 1 :]:
                if text == other_text:
                    findings.append(
                        f"{name} and {other} hold the same value; the master keys must differ "
                        "(05 CFG-26)"
                    )
        return tuple(findings)

    def smtp_ca_findings(self) -> tuple[str, ...]:
        """Why ``EREV_SMTP_CA_FILE`` is unfit (05 CFG-18 rev 1.53; SAR-40 ``email-backend``). The
        bundle is loaded exactly as the SMTP sender loads it, so a missing or unreadable file and
        one that holds no PEM certificate are found before the first message fails. The finding
        names the variable, never the path."""
        if self.smtp_ca_file is None:
            return ()
        try:
            ssl.create_default_context(cafile=str(self.smtp_ca_file))
        except OSError:  # ssl.SSLError, which a file without a certificate raises, is one
            return (
                "EREV_SMTP_CA_FILE is not a readable PEM bundle of certificate authorities "
                "(05 CFG-18)",
            )
        return ()

    def security_hmac_version(self) -> int:
        """The version of `security-hmac:<n>` that signs new security events (05 KEY-03): the
        pinned Secret Manager version hosted; locally the derivation version, 1 unless set."""
        return 1 if self.security_hmac_secret_version is None else self.security_hmac_secret_version

    def _file_backend_rules(self) -> list[str]:
        """CFG-05, CFG-07: the gcs backend is hosted-only and names two distinct buckets; a bucket
        named while the backend is local is a contradictory configuration and is refused, so a
        hosted deployment can never fall back to instance-local storage unnoticed (OPR-09)."""
        failures: list[str] = []
        if self.file_backend == "gcs":
            if self.env in LOCAL_ENVIRONMENTS:
                failures.append("EREV_FILE_BACKEND must be local when EREV_ENV is dev, test or e2e")
            if self.gcs_files_bucket is None or self.gcs_audit_digest_bucket is None:
                failures.append(
                    "EREV_FILE_BACKEND=gcs requires EREV_GCS_FILES_BUCKET and "
                    "EREV_GCS_AUDIT_DIGEST_BUCKET"
                )
            elif self.gcs_files_bucket == self.gcs_audit_digest_bucket:
                failures.append(
                    "EREV_GCS_FILES_BUCKET and EREV_GCS_AUDIT_DIGEST_BUCKET must name different "
                    "buckets (05 DPL-35)"
                )
        else:
            for field_name in ("gcs_files_bucket", "gcs_audit_digest_bucket"):
                if getattr(self, field_name) is not None:
                    name = self.variable_name(field_name)
                    failures.append(f"{name} is set but EREV_FILE_BACKEND is local")
        return failures

    def _database_pair(self) -> tuple[tuple[str, SecretStr | None], tuple[str, SecretStr | None]]:
        """(owner, app) variable names and values selected by EREV_ENV (DG-ENV-10)."""
        if self.env is Environment.TEST:
            return (
                ("EREV_TEST_DB_OWNER_URL", self.test_db_owner_url),
                ("EREV_TEST_DB_APP_URL", self.test_db_app_url),
            )
        if self.env is Environment.E2E:
            return (
                ("EREV_E2E_DB_OWNER_URL", self.e2e_db_owner_url),
                ("EREV_E2E_DB_APP_URL", self.e2e_db_app_url),
            )
        return (("EREV_DB_OWNER_URL", self.db_owner_url), ("EREV_DB_APP_URL", self.db_app_url))

    def app_database_url(self) -> str:
        """SQLAlchemy URL of the runtime role for the selected environment (DG-ENV-10 to 13)."""
        return _normalised_url(*self._database_pair()[1])

    def owner_database_url(self) -> str:
        """SQLAlchemy URL of the migration role for the selected environment.

        Hosted api and worker processes carry no owner URL (DPL-33), so this raises
        ``SettingsError`` naming the variable when an owner-only command runs without one.
        """
        return _normalised_url(*self._database_pair()[0])

    def database_name(self) -> str:
        """Database named by the selected app URL; safe to log (DG-ENV-11)."""
        return _database_of(*self._database_pair()[1])


def database_of_url(url: str, *, variable: str | None = None) -> str:
    """Database named by a PostgreSQL URL, checked against the DG-ENV-13 allow-list; safe to log.

    A query parameter that libpq could use to reach another database is refused (D-78). Messages
    name the variable, the parameter and the database, never the URL or its credentials.
    """
    source = variable or "database URL"
    parts = urlsplit(url)
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        parameter = key.strip().lower()
        if parameter in REDIRECTING_QUERY_PARAMETERS:
            raise SettingsError(
                f"{source} sets query parameter {parameter}, which could select another "
                "database (DG-ENV-13)"
            )
    database = unquote(parts.path.lstrip("/"))
    if not ALLOWED_DATABASE.fullmatch(database):
        raise SettingsError(
            f"{source} names database {database!r}, which is outside the allow-list erev, "
            "erev_test, erev_e2e, erev_rv_* (DG-ENV-13)"
        )
    return database


def _database_of(name: str, value: SecretStr | None) -> str:
    if value is None:
        raise SettingsError(f"{name} is not set")
    return database_of_url(value.get_secret_value(), variable=name)


def _normalised_url(name: str, value: SecretStr | None) -> str:
    _database_of(name, value)
    assert value is not None
    url = value.get_secret_value()
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise SettingsError(f"{name} must be a postgresql:// URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process settings; only composition roots call this (DG-KRN-CFG-01)."""
    return Settings()


def _environment_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, tuple | list):
        return ",".join(str(item) for item in value)
    return str(value)


@contextmanager
def settings_override(**values: object) -> Iterator[Settings]:
    """Tests only: set the variables behind the named fields and rebuild the cached settings."""
    names = {field: Settings.variable_name(field) for field in values}
    unknown = sorted(field for field in values if field not in Settings.model_fields)
    if unknown:
        raise TypeError(f"unknown settings fields: {', '.join(unknown)}")
    previous = {name: os.environ.get(name) for name in names.values()}
    get_settings.cache_clear()
    try:
        for field, value in values.items():
            os.environ[names[field]] = _environment_value(value)
        yield get_settings()
    finally:
        for name, old in previous.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        get_settings.cache_clear()
