"""Terraform data, key and storage resources (05 §8.3 DPL-30, DPL-32, DPL-34 to DPL-36, DPL-39;
§7.2 OPR-08, OPR-17; BUILD_SPEC DEP-3). REQs contributed: REQ-OPS-002, REQ-SEC-002.

The ``.tf`` files under ``deploy/terraform/gcp`` are read as text (``support.terraform``): the loop
never runs Terraform (DG-FORBID-07, DG-FORBID-12; ``make tf-validate`` is a supervisor target).
"""

from __future__ import annotations

import re
from pathlib import Path

from support.terraform import (
    ROOT,
    TERRAFORM_DIR,
    all_text,
    local_value,
    outputs,
    read_blocks,
    resource,
    resources,
    tf_files,
    unquote,
    variable_default,
    variables,
)

LOCK_FILE = TERRAFORM_DIR / ".terraform.lock.hcl"
# 05 DPL-30 rev 1.1: the dev guide §1.1 governs the root file names.
DEV_GUIDE_FILES = (
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "cloud_run.tf",
    "cloud_sql.tf",
    "secrets.tf",
    "artifact_registry.tf",
    "load_balancer.tf",
    "outputs.tf",
    "README.md",
)
EXAMPLE_FILES = (
    "backend.tf.example",
    "envs/staging.tfvars.example",
    "envs/production.tfvars.example",
)


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_versions() -> None:
    # DPL-30: layout per the dev guide, Terraform >= 1.6, hashicorp/google ~> 6.0.
    for name in DEV_GUIDE_FILES + EXAMPLE_FILES:
        assert (TERRAFORM_DIR / name).is_file(), f"{name} missing"
    assert not (TERRAFORM_DIR / "backend.tf").exists(), "the GCS backend is never active"

    (terraform_block,) = [block for block in read_blocks() if block.kind == "terraform"]
    required = unquote(terraform_block.attribute("required_version"))
    assert required is not None
    operator, minimum = re.fullmatch(r"(>=)\s*([0-9.]+)", required).groups()  # type: ignore[union-attr]
    assert operator == ">=" and _version_tuple(minimum) >= (1, 6)

    (providers,) = terraform_block.nested("required_providers")
    google = re.search(r"google\s*=\s*\{([^}]*)\}", providers.body, re.S)
    assert google is not None, "required_providers.google"
    assert re.search(r'source\s*=\s*"hashicorp/google"', google.group(1))
    assert re.search(r'version\s*=\s*"~> 6\.0"', google.group(1))

    # The lock file records the exact provider the configuration was validated against.
    lock = LOCK_FILE.read_text(encoding="utf-8")
    match = re.search(
        r'provider "registry\.terraform\.io/hashicorp/google" \{\s*version\s*=\s*"([^"]+)"', lock
    )
    assert match is not None, ".terraform.lock.hcl pins hashicorp/google"
    assert _version_tuple(match.group(1))[0] == 6

    # No provider credentials in code (REQ-SEC-002; DG-FORBID-01); google and google-beta only.
    providers_declared = [block for block in read_blocks() if block.kind == "provider"]
    assert {block.labels[0] for block in providers_declared} == {"google", "google-beta"}
    for provider in providers_declared:
        for forbidden in ("credentials", "access_token", "impersonate_service_account"):
            assert provider.attribute(forbidden) is None, forbidden


def test_cloud_sql() -> None:
    # DPL-32; REQ-SEC-002.
    instance = resource("google_sql_database_instance", "erev")
    assert unquote(instance.attribute("database_version")) == "POSTGRES_17"
    assert instance.attribute("deletion_protection") == "true"
    encryption = instance.attribute("encryption_key_name")
    assert encryption is not None
    assert "var.use_cmek" in encryption and "google_kms_crypto_key.cloudsql" in encryption

    (settings,) = instance.nested("settings")
    assert settings.attribute("edition") == "var.db_edition"
    assert unquote(variable_default("db_edition")) == "ENTERPRISE"
    (ip_configuration,) = settings.nested("ip_configuration")
    assert ip_configuration.attribute("ipv4_enabled") == "false"
    assert ip_configuration.attribute("private_network") == "google_compute_network.vpc.id"

    (backup,) = settings.nested("backup_configuration")
    assert backup.attribute("enabled") == "true"
    assert backup.attribute("point_in_time_recovery_enabled") == "true"
    assert backup.attribute("transaction_log_retention_days") == "var.pitr_log_retention_days"
    assert variable_default("pitr_log_retention_days") == "7"
    (retention,) = backup.nested("backup_retention_settings")
    assert retention.attribute("retained_backups") == "30"

    # SAR-30 flags.
    flags = local_value("db_flags")
    assert flags is not None
    locals_body = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    for flag, value in (
        ("cloudsql.enable_pgaudit", "on"),
        ("pgaudit.log", "ddl,role"),
        ("cloudsql.pgaudit_mask_literals", "on"),
        ("log_connections", "on"),
        ("log_disconnections", "on"),
    ):
        assert re.search(rf'"{re.escape(flag)}"\s*=\s*"{re.escape(value)}"', locals_body), flag

    # Users erev_owner and erev_app (plus the P6 backup role) with random_password written to
    # Secret Manager.
    users = {unquote(user.attribute("name")): user for user in resources("google_sql_user")}
    assert set(users) == {"erev_owner", "erev_app", "var.backup_user_name"}
    for name, generator in (
        ("erev_owner", "owner"),
        ("erev_app", "app"),
        ("var.backup_user_name", "backup[0]"),
    ):
        assert users[name].attribute("password") == f"random_password.{generator}.result"
        resource("random_password", generator.split("[")[0])
    versions = {block.name: block for block in resources("google_secret_manager_secret_version")}
    assert set(versions) == {"db_owner_url", "db_app_url", "db_backup_url"}
    for name, generator in (
        ("db_owner_url", "owner"),
        ("db_app_url", "app"),
        ("db_backup_url", "backup[0]"),
    ):
        data = versions[name].attribute("secret_data")
        assert data is not None
        assert f"random_password.{generator}.result" in data
        assert "google_sql_database_instance.erev.private_ip_address" in data

    # No password reaches an output (REQ-SEC-002).
    for name, output in outputs().items():
        assert "password" not in name.lower(), name
        assert "random_password" not in output.body, name
        assert "secret_data" not in output.body, name
        assert ".password" not in output.body, name
        assert re.search(r"google_sql_user\.[a-z_]+(\[0\])?\.password", output.body) is None, name


def test_kms_and_storage() -> None:
    # DPL-34, OPR-17.
    keys = {unquote(key.attribute("name")): key for key in resources("google_kms_crypto_key")}
    assert set(keys) == {"erev-cloudsql", "erev-gcs", "erev-app-kek"}
    rotation = local_value("kms_rotation_period")
    assert unquote(rotation) == "7776000s"
    for name, key in keys.items():
        assert key.attribute("rotation_period") == "local.kms_rotation_period", name
        (lifecycle,) = key.nested("lifecycle")
        assert lifecycle.attribute("prevent_destroy") == "true", name
        assert key.attribute("key_ring") == "google_kms_key_ring.erev.id", name
    assert unquote(local_value("kms_destroy_scheduled_duration")) == "2592000s"

    # DPL-35: files bucket.
    files = resource("google_storage_bucket", "files")
    assert files.attribute("name") == "local.files_bucket"
    files_name = local_value("files_bucket")
    assert files_name is not None and "-files-${local.env}" in files_name
    assert files.attribute("uniform_bucket_level_access") == "true"
    assert unquote(files.attribute("public_access_prevention")) == "enforced"
    assert files.attribute("location") == "var.region"
    (versioning,) = files.nested("versioning")
    assert versioning.attribute("enabled") == "true"
    (soft_delete,) = files.nested("soft_delete_policy")
    assert soft_delete.attribute("retention_duration_seconds") == "local.files_soft_delete_seconds"
    assert local_value("files_soft_delete_seconds") == "604800"
    (encryption,) = files.nested("encryption")
    assert encryption.attribute("default_kms_key_name") == "google_kms_crypto_key.gcs.id"
    assert "var.use_cmek" in encryption.body or "var.use_cmek" in files.body

    # DPL-35, SAR-31: digest bucket with the 7-year retention policy, unlocked.
    digests = resource("google_storage_bucket", "audit_digests")
    digests_name = local_value("digest_bucket")
    assert digests_name is not None and "-audit-digests-${local.env}" in digests_name
    (retention,) = digests.nested("retention_policy")
    assert retention.attribute("retention_period") == "local.digest_retention_seconds"
    assert local_value("digest_retention_seconds") == "220752000"
    assert retention.attribute("is_locked") == "false"
    assert digests.attribute("uniform_bucket_level_access") == "true"
    assert unquote(digests.attribute("public_access_prevention")) == "enforced"
    assert not digests.nested("versioning"), "a retention policy excludes object versioning"


def test_secrets_and_network() -> None:
    # DPL-36, PRV-10: user-managed replication in var.region; no secret values.
    secrets = resources("google_secret_manager_secret")
    assert secrets, "google_secret_manager_secret resources exist"
    for secret in secrets:
        (replication,) = secret.nested("replication")
        (user_managed,) = replication.nested("user_managed")
        (replicas,) = user_managed.nested("replicas")
        assert replicas.attribute("location") == "var.region", secret.name
        assert "automatic" not in replication.body
    ids = "\n".join(block.body for block in read_blocks() if block.kind == "locals")
    for suffix in (
        "db-owner-url",
        "db-app-url",
        "security-hmac",
        "anthropic-api-key",
        "smtp-password",
        "metrics-token",
    ):
        assert f'"${{var.secret_prefix}}{suffix}"' in ids, suffix
    # KEY-05 template: created per tenant by the application, never as a resource.
    assert "audit-hmac-" in ids
    # Every secret version is derived from state (random_password), never a literal.
    for version in resources("google_secret_manager_secret_version"):
        data = version.attribute("secret_data")
        assert data is not None and "random_password." in data, version.name
        assert version.name in ("db_owner_url", "db_app_url", "db_backup_url"), version.name
    text = all_text()
    assert re.search(r'version\s*=\s*"latest"', text) is None, "versions are pinned (SAR-25)"

    # DPL-39: no public IP, a private services access range, Direct VPC egress subnet.
    instance = resource("google_sql_database_instance", "erev")
    assert "ipv4_enabled                                  = false" in instance.body or (
        "ipv4_enabled = false" in re.sub(r"\s+", " ", instance.body)
    )
    psa = resource("google_compute_global_address", "psa_range")
    assert unquote(psa.attribute("purpose")) == "VPC_PEERING"
    assert unquote(psa.attribute("address_type")) == "INTERNAL"
    connection = resource("google_service_networking_connection", "psa")
    assert "google_compute_global_address.psa_range.name" in connection.body
    resource("google_compute_network", "vpc")
    subnet = resource("google_compute_subnetwork", "run_egress")
    assert subnet.attribute("private_ip_google_access") == "true"
    # No serverless VPC connector: Direct VPC egress only (DPL-31).
    assert not resources("google_vpc_access_connector")


def test_example_files_hold_placeholders_only() -> None:
    # DPL-30 examples: every UI-1..UI-10 variable is set, no real identifier or credential.
    declared = set(variables())
    required = {name for name, block in variables().items() if block.attribute("default") is None}
    for example in EXAMPLE_FILES[1:]:
        text = (TERRAFORM_DIR / example).read_text(encoding="utf-8")
        assigned = set(re.findall(r"^([a-z_]+)\s*=", text, re.MULTILINE))
        assert required <= assigned, f"{example} misses {sorted(required - assigned)}"
        assert assigned <= declared, f"{example} sets unknown {sorted(assigned - declared)}"
        assert "PLACEHOLDER" in text
        assert "example.com" in text
        digests = re.findall(r'"sha256:([0-9a-f]{64})"', text)
        assert len(digests) == 3 and set(digests) == {"0" * 64}
        assert re.search(r'=\s*"latest"', text) is None
        for pattern in (
            r"sk-ant-",
            r"AKIA[0-9A-Z]{16}",
            r"xox[abprs]-",
            r"BEGIN [A-Z ]*PRIVATE KEY",
        ):
            assert re.search(pattern, text) is None, pattern
    backend = (TERRAFORM_DIR / "backend.tf.example").read_text(encoding="utf-8")
    assert 'backend "gcs"' in backend and "PLACEHOLDER" in backend
    for forbidden in ("credentials", "access_token"):
        assert re.search(rf"^\s*{forbidden}\s*=", backend, re.MULTILINE) is None

    # The plugin cache and .terraform directory stay out of git (DG-LAY-08 additions).
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "deploy/terraform/gcp/.terraform/" in gitignore
    assert "*.tfstate" in gitignore
    assert all(path.suffix == ".tf" for path in tf_files())
    assert not list(Path(TERRAFORM_DIR).glob("*.tfvars")), "only .tfvars.example files are tracked"
