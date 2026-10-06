# Root module: shared locals, project APIs, network (DPL-39), KMS (DPL-34), storage (DPL-35), IAM
# (DPL-33 plus the tenant-secret provisioning identity of the runtime contract), monitoring and
# logging (DPL-37, SAR-30) and Cloud Armor (DPL-41). The dev guide §1.1 names these root files;
# 05 DPL-30 rev 1.1 maps its `network`, `kms`, `storage`, `iam`, `monitoring` groups onto this file
# (BUILD_SPEC DEP-3 "main.tf (network, KMS, storage)", DEP-4 "main.tf (IAM, monitoring, Cloud
# Armor)"). Cloud SQL, secrets, Cloud Run, the registry and the load balancer have their own files.
#
# Artifacts only: never applied by the loop (00-GOAL §4; DG-FORBID-07).

locals {
  env  = var.environment
  name = var.name_prefix

  labels = merge(
    {
      app         = "erev"
      environment = var.environment
      managed-by  = "terraform"
    },
    var.labels,
  )

  # Constants fixed by the specification. They are locals, not variables, so a tfvars file cannot
  # weaken them without a visible code change.
  digest_retention_seconds       = 220752000  # 7 years (05 DPL-35, SAR-31)
  files_soft_delete_seconds      = 604800     # 7 days (05 DPL-35, PRV-06, PRV-07)
  log_retention_days             = 400        # 05 SAR-30, DPL-37
  kms_rotation_period            = "7776000s" # 90 days (05 DPL-34, KEY-01, KEY-02, KEY-04)
  kms_destroy_scheduled_duration = "2592000s" # 30 days (05 OPR-17)
  cloud_armor_throttle_rpm       = 1000       # per client IP per minute (05 SAR-13, DPL-41)

  files_bucket  = coalesce(var.files_bucket_name, "${local.name}-files-${local.env}")
  digest_bucket = coalesce(var.digest_bucket_name, "${local.name}-audit-digests-${local.env}")

  # KEY-05 template: erev-audit-hmac-<tenant id>, created at runtime by the provisioning identity
  # (05 DPL-36; runtime contract "Persistent key and secret providers").
  tenant_audit_hmac_secret_prefix = "${var.secret_prefix}audit-hmac-"

  project_number = data.google_project.this.number

  # Google-managed service agents. The Cloud SQL and IAP agents are CREATED by
  # google_project_service_identity below (P3-R5: a fresh project has no such identity until the
  # service identity is provisioned; Google's CMEK workflow creates it before the key grant) and
  # referenced through the resource, so the grant depends on the identity in the graph. The Cloud
  # Run agent exists once run.googleapis.com is enabled; the GCS agent comes from its data source.
  cloud_sql_service_agent = google_project_service_identity.cloud_sql.member
  iap_service_agent       = google_project_service_identity.iap.member
  cloud_run_service_agent = "service-${local.project_number}@serverless-robot-prod.iam.gserviceaccount.com"
  gcs_service_agent       = data.google_storage_project_service_account.gcs.email_address

  psa_cidr = "${google_compute_global_address.psa_range.address}/${google_compute_global_address.psa_range.prefix_length}"
}

# ---------------------------------------------------------------------------------------------
# Project APIs
# ---------------------------------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "compute.googleapis.com",
    "containerscanning.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    # Strict-IAP health probe (P3c): Cloud Run functions build/deploy, IAM Credentials signJwt.
    "cloudfunctions.googleapis.com",
    "cloudbuild.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "this" {
  project_id = var.project_id
}

data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

# Service identities (google-beta; the GA provider 6.50.0 has no google_project_service_identity).
# Cloud SQL's agent must exist before it can be granted the CMEK key (P3-R5); IAP's agent must exist
# before it can be granted roles/run.invoker on the api and web services (P3-R1).
resource "google_project_service_identity" "cloud_sql" {
  provider = google-beta
  project  = var.project_id
  service  = "sqladmin.googleapis.com"

  depends_on = [google_project_service.apis]
}

resource "google_project_service_identity" "iap" {
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------------------------
# Network (05 DPL-39): VPC, subnet for Direct VPC egress, private services access for Cloud SQL
# ---------------------------------------------------------------------------------------------

resource "google_compute_network" "vpc" {
  name                    = "${local.name}-vpc-${local.env}"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "run_egress" {
  name                     = "${local.name}-run-egress-${local.env}"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.vpc_subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_MIN"
    flow_sampling        = 0.5
    metadata             = "EXCLUDE_ALL_METADATA"
  }
}

# The peered range Cloud SQL allocates its private IP from; no public IP exists (DPL-32, DPL-39).
resource "google_compute_global_address" "psa_range" {
  name          = "${local.name}-psa-range-${local.env}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.psa_prefix_length
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range.name]

  depends_on = [google_project_service.apis]
}

# Direct VPC egress instances reach only the private Cloud SQL address over 5432.
resource "google_compute_firewall" "egress_cloud_sql" {
  name      = "${local.name}-egress-cloudsql-${local.env}"
  network   = google_compute_network.vpc.id
  direction = "EGRESS"
  priority  = 1000

  destination_ranges = [local.psa_cidr]

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  log_config {
    metadata = "EXCLUDE_ALL_METADATA"
  }
}

# Nothing initiates connections into the egress subnet.
resource "google_compute_firewall" "deny_ingress" {
  name      = "${local.name}-deny-ingress-${local.env}"
  network   = google_compute_network.vpc.id
  direction = "INGRESS"
  priority  = 65000

  source_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "all"
  }
}

# ---------------------------------------------------------------------------------------------
# KMS (05 DPL-34, OPR-17, KEY-01, KEY-02, KEY-04)
# ---------------------------------------------------------------------------------------------

resource "google_kms_key_ring" "erev" {
  name     = var.kms_key_ring_name
  location = var.region

  depends_on = [google_project_service.apis]
}

resource "google_kms_crypto_key" "cloudsql" {
  name                       = "erev-cloudsql"
  key_ring                   = google_kms_key_ring.erev.id
  purpose                    = "ENCRYPT_DECRYPT"
  rotation_period            = local.kms_rotation_period
  destroy_scheduled_duration = local.kms_destroy_scheduled_duration
  labels                     = local.labels

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "gcs" {
  name                       = "erev-gcs"
  key_ring                   = google_kms_key_ring.erev.id
  purpose                    = "ENCRYPT_DECRYPT"
  rotation_period            = local.kms_rotation_period
  destroy_scheduled_duration = local.kms_destroy_scheduled_duration
  labels                     = local.labels

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# KEY-04: the application key-encryption key used through encrypt/decrypt calls on DEKs only.
# Rotation creates a new primary version; old versions stay enabled for decryption (runtime
# contract) and are never destroyed by this module.
resource "google_kms_crypto_key" "app_kek" {
  name                       = "erev-app-kek"
  key_ring                   = google_kms_key_ring.erev.id
  purpose                    = "ENCRYPT_DECRYPT"
  rotation_period            = local.kms_rotation_period
  destroy_scheduled_duration = local.kms_destroy_scheduled_duration
  labels                     = local.labels

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Service agents that encrypt with the CMEK keys (only when use_cmek).
resource "google_kms_crypto_key_iam_member" "cloudsql_service_agent" {
  count = var.use_cmek ? 1 : 0

  crypto_key_id = google_kms_crypto_key.cloudsql.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = local.cloud_sql_service_agent
}

resource "google_kms_crypto_key_iam_member" "gcs_service_agent" {
  count = var.use_cmek ? 1 : 0

  crypto_key_id = google_kms_crypto_key.gcs.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${local.gcs_service_agent}"
}

# ---------------------------------------------------------------------------------------------
# Storage (05 DPL-35, PRV-06, PRV-07, SAR-31; runtime contract "GCS immutable file and wrapped-key
# contract")
# ---------------------------------------------------------------------------------------------

# File store: immutable content-addressed payloads and wrapped .dek sidecars. Versioning and the
# seven-day soft delete make erasure reversible until retention expires (PRV-07).
resource "google_storage_bucket" "files" {
  name                        = local.files_bucket
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = local.files_soft_delete_seconds
  }

  dynamic "encryption" {
    for_each = var.use_cmek ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.gcs.id
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_service_agent]
}

# Daily audit digests (SAR-31): 7-year retention policy created UNLOCKED. Locking is the one-time
# manual step of RB-13 because a locked policy can never be removed. Object versioning cannot be
# combined with a retention policy; digests are create-only objects (objectCreator, DPL-33).
resource "google_storage_bucket" "audit_digests" {
  name                        = local.digest_bucket
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  retention_policy {
    retention_period = local.digest_retention_seconds
    is_locked        = false
  }

  dynamic "encryption" {
    for_each = var.use_cmek ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.gcs.id
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_service_agent]
}

# ---------------------------------------------------------------------------------------------
# IAM (05 DPL-33; runtime contract: separate tenant-secret provisioning identity)
#
# Five service accounts, no project-wide editor or owner role anywhere:
#   erev-api           serves requests; reads the app database URL, static secrets and tenant
#                      audit HMAC secrets; reads and writes file objects; verifies digests.
#   erev-worker        runs jobs; same secret access as the api; writes digests (create-only).
#   erev-migrate       Alembic upgrade as erev_owner; only the owner database URL.
#   erev-provisioning  creates and initialises tenant audit HMAC secrets (KEY-05) through two
#                      custom roles: creation (project-scoped, unavoidable, creation only) and
#                      initialisation (get/add/access, conditioned to the KEY-05 prefix); reads the
#                      app database URL and the security HMAC key only. The Tenant Admin invitation
#                      of `erev tenant create` is an outbox EMAIL row that the worker's SCH-03 relay
#                      sends, so the job holds no SMTP credential (lane P2). It can read neither the
#                      owner database URL nor any static secret it is not named on (P3-R3).
#   erev-web           serves the SPA; no role at all (avoids the default compute account).
# Cloud Run invocation (P3-R1) is a separate block below: only erev-api and erev-web are ever
# invocable, by allUsers (or with the invoker IAM check disabled) when IAP is off and by the IAP
# service agent when IAP is on; the workers and jobs have no invoker at all.
# ---------------------------------------------------------------------------------------------

resource "google_service_account" "api" {
  account_id   = "${local.name}-api"
  display_name = "eRev api (Cloud Run erev-api)"
  description  = "05 DPL-33: request serving identity; least privilege."
}

resource "google_service_account" "worker" {
  account_id   = "${local.name}-worker"
  display_name = "eRev worker (Cloud Run erev-worker-compute and erev-worker-general)"
  description  = "05 DPL-33: job runner identity; writes audit digests create-only."
}

resource "google_service_account" "migrate" {
  account_id   = "${local.name}-migrate"
  display_name = "eRev migrate (Cloud Run job erev-migrate)"
  description  = "05 DPL-33, CMP-09: Alembic upgrade head as erev_owner."
}

resource "google_service_account" "provisioning" {
  account_id   = "${local.name}-provisioning"
  display_name = "eRev tenant-secret provisioning"
  description  = "Runtime contract: creates and initialises tenant audit HMAC secrets (KEY-05); never attached to the api or worker services."
}

resource "google_service_account" "web" {
  account_id   = "${local.name}-web"
  display_name = "eRev web (Cloud Run erev-web)"
  description  = "Static SPA; holds no IAM role."
}

locals {
  service_accounts = {
    api          = google_service_account.api.email
    worker       = google_service_account.worker.email
    migrate      = google_service_account.migrate.email
    provisioning = google_service_account.provisioning.email
  }

  # Identities that open database connections (Cloud SQL Auth is not used over private IP, but
  # roles/cloudsql.client is the documented least privilege for connecting identities).
  cloudsql_clients = {
    api          = google_service_account.api.email
    worker       = google_service_account.worker.email
    migrate      = google_service_account.migrate.email
    provisioning = google_service_account.provisioning.email
  }

  # (static secret key, identity) pairs allowed to read that named secret (DPL-33 "on named
  # secrets only"); `key` indexes local.static_secrets.
  secret_accessors = {
    "db_app_url/api"          = { key = "db_app_url", member = google_service_account.api.email }
    "db_app_url/worker"       = { key = "db_app_url", member = google_service_account.worker.email }
    "db_app_url/provisioning" = { key = "db_app_url", member = google_service_account.provisioning.email }
    "db_owner_url/migrate"    = { key = "db_owner_url", member = google_service_account.migrate.email }
    # `erev migrate` upgrades as erev_owner and then runs the DB-14 catalogue lint as erev_app
    # (DG-MK-migrate step 2), so the job also reads the app URL (lane P2 follow-up).
    "db_app_url/migrate"         = { key = "db_app_url", member = google_service_account.migrate.email }
    "security_hmac/api"          = { key = "security_hmac", member = google_service_account.api.email }
    "security_hmac/worker"       = { key = "security_hmac", member = google_service_account.worker.email }
    "anthropic_api_key/api"      = { key = "anthropic_api_key", member = google_service_account.api.email }
    "anthropic_api_key/worker"   = { key = "anthropic_api_key", member = google_service_account.worker.email }
    "smtp_password/api"          = { key = "smtp_password", member = google_service_account.api.email }
    "smtp_password/worker"       = { key = "smtp_password", member = google_service_account.worker.email }
    "metrics_token/api"          = { key = "metrics_token", member = google_service_account.api.email }
    "security_hmac/provisioning" = { key = "security_hmac", member = google_service_account.provisioning.email }
    # No SMTP or AI credential for provisioning: `erev tenant create` writes the Tenant Admin
    # invitation as an outbox EMAIL row that the worker's SCH-03 relay sends (lane P2; P3-R3).
  }

  # Identities that read tenant audit HMAC secret versions created at runtime (KEY-05).
  tenant_secret_readers = {
    api    = google_service_account.api.email
    worker = google_service_account.worker.email
  }
}

resource "google_project_iam_member" "cloudsql_client" {
  for_each = local.cloudsql_clients

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${each.value}"
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = local.secret_accessors

  project   = var.project_id
  secret_id = google_secret_manager_secret.static[each.value.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.member}"
}

# Tenant secrets do not exist at plan time, so their accessor grant is a project-level binding
# narrowed by an IAM condition to names under the KEY-05 prefix. Secret Manager resource names
# carry the project NUMBER.
resource "google_project_iam_member" "tenant_secret_accessor" {
  for_each = local.tenant_secret_readers

  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${each.value}"

  condition {
    title       = "erev-tenant-audit-hmac-secrets"
    description = "Only tenant audit HMAC secrets (KEY-05 template ${local.tenant_audit_hmac_secret_prefix}<tenant id>)."
    expression  = "resource.name.startsWith(\"projects/${local.project_number}/secrets/${local.tenant_audit_hmac_secret_prefix}\")"
  }
}

# The provisioning identity (P3-R3 split). Creation is checked against the PROJECT, so it cannot be
# narrowed by a resource-name condition: the creator role therefore holds secretmanager.secrets.create
# and nothing else (it cannot read, add to or list any secret). Initialisation (get, add the first
# version, read it back to verify: runtime contract "tenant creation commits only after the key can
# be read") is a second role whose project-level binding carries the KEY-05 prefix condition, so the
# owner database URL, the SMTP and API credentials and every unrelated secret stay unreadable and
# un-appendable for this identity. Neither role deletes, destroys or changes IAM.
resource "google_project_iam_custom_role" "tenant_secret_creator" {
  project     = var.project_id
  role_id     = "erevTenantSecretCreator"
  title       = "eRev tenant secret creator"
  description = "secretmanager.secrets.create only (KEY-05 tenant audit HMAC secrets); no read, add, delete, destroy or IAM permission."
  stage       = "GA"

  permissions = [
    "secretmanager.secrets.create",
  ]
}

resource "google_project_iam_custom_role" "tenant_secret_initializer" {
  project     = var.project_id
  role_id     = "erevTenantSecretInitializer"
  title       = "eRev tenant secret initializer"
  description = "Get, add a version to and read back a tenant audit HMAC secret (KEY-05); bound only under the tenant-prefix condition."
  stage       = "GA"

  permissions = [
    "secretmanager.secrets.get",
    "secretmanager.versions.add",
    "secretmanager.versions.access",
    "secretmanager.versions.get",
    "secretmanager.versions.list",
  ]
}

resource "google_project_iam_member" "provisioning_creator" {
  project = var.project_id
  role    = google_project_iam_custom_role.tenant_secret_creator.id
  member  = "serviceAccount:${google_service_account.provisioning.email}"
}

resource "google_project_iam_member" "provisioning_initializer" {
  project = var.project_id
  role    = google_project_iam_custom_role.tenant_secret_initializer.id
  member  = "serviceAccount:${google_service_account.provisioning.email}"

  condition {
    title       = "erev-tenant-audit-hmac-secrets-initialise"
    description = "Only tenant audit HMAC secrets (KEY-05 template ${local.tenant_audit_hmac_secret_prefix}<tenant id>)."
    expression  = "resource.name.startsWith(\"projects/${local.project_number}/secrets/${local.tenant_audit_hmac_secret_prefix}\")"
  }
}

# ---------------------------------------------------------------------------------------------
# Cloud Run invocation policy (P3-R1; 05 DPL-40). An external Application Load Balancer forwards to
# a serverless NEG without an identity token, so a Cloud Run service behind it must accept public
# invocation (Google's serverless-NEG setup deploys with --allow-unauthenticated) unless IAP sits on
# the backend service, in which case IAP invokes the service as its own service agent, which needs
# roles/run.invoker. Ingress stays INTERNAL_LOAD_BALANCER on api and web, so the load balancer is
# the only path in. Effective policy by mode (tested offline in test_terraform_policy.py):
#   IAP off                      api, web: allUsers invoker, or invoker IAM check disabled
#                                (invoker_iam_disabled, for the domain-restricted-sharing policy).
#   IAP on, no healthz exemption api, web: the IAP service agent only. The public uptime check
#                                is a TCP 443 front-door check (uptime checks follow redirects, so
#                                no HTTPS probe can observe the IAP challenge), see monitoring.
#   IAP on, healthz exemption    api: IAP agent AND public invocation (Cloud Run IAM cannot see
#                                paths; the url map routes only /api/v1/healthz around IAP);
#                                web: the IAP agent only.
#   Workers, jobs                no invoker binding in any mode; workers keep INTERNAL_ONLY ingress.
# ---------------------------------------------------------------------------------------------

locals {
  api_public_invocation = !var.enable_iap || var.iap_healthz_exemption
  web_public_invocation = !var.enable_iap

  # The invoker IAM check is disabled only where invocation is public anyway.
  api_invoker_iam_disabled = var.invoker_iam_disabled && local.api_public_invocation
  web_invoker_iam_disabled = var.invoker_iam_disabled && local.web_public_invocation

  # Static keys (for_each keys must be known at plan time); the member values may be unknown.
  invoker_bindings = merge(
    var.enable_iap ? { "api/iap" = { service = "api", member = local.iap_service_agent } } : {},
    var.enable_iap ? { "web/iap" = { service = "web", member = local.iap_service_agent } } : {},
    local.api_public_invocation && !var.invoker_iam_disabled ? { "api/public" = { service = "api", member = "allUsers" } } : {},
    local.web_public_invocation && !var.invoker_iam_disabled ? { "web/public" = { service = "web", member = "allUsers" } } : {},
  )
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = local.invoker_bindings

  project  = var.project_id
  location = var.region
  name     = each.value.service == "api" ? google_cloud_run_v2_service.api.name : google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = each.value.member
}

# KEY-04 encrypt/decrypt on the KEK for the identities that wrap and unwrap DEKs.
resource "google_kms_crypto_key_iam_member" "app_kek_users" {
  for_each = {
    api    = google_service_account.api.email
    worker = google_service_account.worker.email
  }

  crypto_key_id = google_kms_crypto_key.app_kek.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${each.value}"
}

# Files bucket: object admin for the two runtime identities (DPL-33). Create-only application
# logic is not an immutability boundary here (runtime contract), which is why the digest bucket
# below is separate and creator-only.
resource "google_storage_bucket_iam_member" "files_object_admin" {
  for_each = {
    api    = google_service_account.api.email
    worker = google_service_account.worker.email
  }

  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${each.value}"
}

# Digest bucket: the worker (SCH-01 daily verification) may only create; the api is the separate
# verifier identity that reads digests back for OPR-11 step 3 and RB-08 comparisons.
resource "google_storage_bucket_iam_member" "digests_object_creator" {
  bucket = google_storage_bucket.audit_digests.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_storage_bucket_iam_member" "digests_object_viewer" {
  bucket = google_storage_bucket.audit_digests.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------------------------------------
# Logging (05 SAR-30, DPL-37): 400-day bucket for pgAudit and application logs, and a sink of
# the pgAudit stream into the digest bucket.
# ---------------------------------------------------------------------------------------------

resource "google_logging_project_bucket_config" "erev" {
  project          = var.project_id
  location         = var.region
  bucket_id        = "${local.name}-logs-${local.env}"
  retention_days   = local.log_retention_days
  enable_analytics = true
  description      = "eRev application and pgAudit logs; 400-day retention (05 SAR-30)."

  depends_on = [google_project_service.apis]
}

locals {
  # pgAudit ('ddl,role') and connection logs of the Cloud SQL instance plus the four Cloud Run
  # workloads' structured logs.
  log_filter_pgaudit = "resource.type=\"cloudsql_database\" AND resource.labels.database_id=\"${var.project_id}:${google_sql_database_instance.erev.name}\" AND (logName:\"cloudaudit.googleapis.com%2Fdata_access\" OR logName:\"postgres.log\")"
  log_filter_run     = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"^${local.name}-(api|worker-compute|worker-general|web)$\""
  log_filter_job     = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=~\"^${local.name}-(migrate|tenant-provision)$\""
}

resource "google_logging_project_sink" "erev_logs" {
  name                   = "${local.name}-logs-${local.env}"
  project                = var.project_id
  destination            = "logging.googleapis.com/projects/${var.project_id}/locations/${var.region}/buckets/${google_logging_project_bucket_config.erev.bucket_id}"
  filter                 = "(${local.log_filter_pgaudit}) OR (${local.log_filter_run}) OR (${local.log_filter_job})"
  unique_writer_identity = true
}

resource "google_project_iam_member" "erev_logs_writer" {
  project = var.project_id
  role    = "roles/logging.bucketWriter"
  member  = google_logging_project_sink.erev_logs.writer_identity
}

# pgAudit prerequisites (SAR-30; Google "pgAudit for Cloud SQL"): (1) the cloudsql.enable_pgaudit,
# pgaudit.log and cloudsql.pgaudit_mask_literals flags (cloud_sql.tf); (2) Data Access audit logs
# enabled for Cloud SQL in the project, because pgAudit records are delivered as
# cloudaudit.googleapis.com/data_access entries (this resource); (3) `CREATE EXTENSION pgaudit` in
# database erev by a cloudsqlsuperuser member, which "Cloud SQL doesn't support using Terraform" for:
# the first erev-migrate run creates it idempotently next to the role attributes (P2 executes,
# RB-11 documents). Without (2) and (3) the flags alone produce no audit records.
resource "google_project_iam_audit_config" "cloudsql_data_access" {
  project = var.project_id
  service = "cloudsql.googleapis.com"

  audit_log_config {
    log_type = "ADMIN_READ"
  }

  audit_log_config {
    log_type = "DATA_READ"
  }

  audit_log_config {
    log_type = "DATA_WRITE"
  }
}

# SAR-30: the DDL/role audit stream also lands in the write-once digest bucket.
resource "google_logging_project_sink" "pgaudit_to_digests" {
  name                   = "${local.name}-pgaudit-digests-${local.env}"
  project                = var.project_id
  destination            = "storage.googleapis.com/${google_storage_bucket.audit_digests.name}"
  filter                 = local.log_filter_pgaudit
  unique_writer_identity = true
}

resource "google_storage_bucket_iam_member" "pgaudit_sink_creator" {
  bucket = google_storage_bucket.audit_digests.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.pgaudit_to_digests.writer_identity
}

# ---------------------------------------------------------------------------------------------
# Monitoring (05 DPL-37; §7.5 SLO-01, SLO-04, SLO-05, SLO-06)
# ---------------------------------------------------------------------------------------------

# The public uptime checker sends no credential and FOLLOWS redirects, evaluating the FINAL response
# (Google "About uptime checks"). While /api/v1/healthz is publicly invocable (IAP off, or IAP on
# with the healthz exemption) an HTTPS check probes that path and expects 2xx: api reachable and
# healthy through the load balancer. With IAP on and no exemption the path is behind IAP, whose
# Google-managed OAuth client permits no programmatic access and whose answer to an unauthenticated
# GET is a redirect to the Google sign-in page: an HTTPS probe would land on that page (2xx) and could
# only validate Google's login page, and it can never observe the 3xx challenge. The front door is
# therefore probed with a TCP check on port 443, which asserts exactly DNS resolution plus the load
# balancer's forwarding rule and TLS listener accepting connections; it asserts nothing about the
# certificate, IAP or the api. In that mode api liveness comes from the Cloud Run startup/liveness
# probes and SLO-01, and the managed certificate's ACTIVE status is an operator check (P3-R1; Codex
# residual review, inbox 1846). test_uptime_check_contract models both matchers.
# Strict mode (IAP on, no healthz exemption) has two options (P3c): the default synthetic probe
# (below, "Strict-IAP health probe"), which calls the protected path with a service-account JWT and
# therefore observes DNS, TLS, IAP routing and the api health body from outside; or, with
# iap_synthetic_health = false, the TCP 443 front-door check, which proves reachability only.
locals {
  uptime_probes_healthz = local.api_public_invocation
  iap_strict            = var.enable_iap && !var.iap_healthz_exemption
  synthetic_enabled     = local.iap_strict && var.iap_synthetic_health
  tcp_fallback          = local.iap_strict && !var.iap_synthetic_health
  # `one()` of a possibly-empty splat is null; try() keeps the synthetic mode (both null) from
  # failing coalesce, and the plain uptime alert is not created in that mode.
  uptime_check_id = try(
    coalesce(
      one(google_monitoring_uptime_check_config.healthz[*].uptime_check_id),
      one(google_monitoring_uptime_check_config.front_door_tcp[*].uptime_check_id),
    ),
    null,
  )
  uptime_check_contract = local.uptime_probes_healthz ? "HTTPS GET /api/v1/healthz, final response 2xx (api reachable and healthy through the load balancer)" : (local.synthetic_enabled ? "Synthetic monitor: GET https://${var.public_domain}/api/v1/healthz through IAP with a JWT signed for exactly that URL by the probe identity, redirects disabled, certificate verified; passes only on 200 with JSON status ok (DNS, TLS, IAP routing, load balancer routing and api liveness observed from outside)" : "TCP 443 handshake on the public domain (DNS and load balancer reachability only; no certificate, IAP or api assertion; api health from Cloud Run probes and SLO-01)")
}

resource "google_monitoring_uptime_check_config" "healthz" {
  count = local.uptime_probes_healthz ? 1 : 0

  display_name = "erev ${local.env} /api/v1/healthz"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path           = "/api/v1/healthz"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.public_domain
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_uptime_check_config" "front_door_tcp" {
  count = local.tcp_fallback ? 1 : 0

  display_name = "erev ${local.env} front door TCP 443 (IAP on, no healthz exemption)"
  timeout      = "10s"
  period       = "60s"

  tcp_check {
    port = 443
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.public_domain
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "uptime" {
  count = local.synthetic_enabled ? 0 : 1

  display_name          = "erev ${local.env} uptime check failing"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "uptime check failed"

    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.labels.check_id=\"${local.uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "300s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "The public uptime check fails from more than one region. Contract of this deployment's check: ${local.uptime_check_contract}. Runbook: RB-10 incident handling."
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------------------------
# Strict-IAP health probe (P3c; 05 DPL-37, DEP-4; Codex inbox 1910 / PRODUCTION-P3B-FOLLOWUP-c53b122
# "Concrete supported replacement contract"). IAP with the Google-managed OAuth client permits no
# OAuth programmatic access, but Google documents the service-account SELF-SIGNED JWT exception:
# iss = sub = the service account, aud = the exact protected URL, exp within 3600 s, sent as
# `Authorization: Bearer`, signed through IAM Credentials signJwt (no exported key). A Cloud
# Monitoring synthetic monitor executes the Node.js runner in synthetic/iap-healthz on a schedule;
# the runner mints such a JWT for ITS OWN identity, GETs https://<public_domain>/api/v1/healthz with
# redirects disabled and normal certificate verification, and passes only on 200 + JSON status "ok".
# IAM scope: the probe identity may sign JWTs for itself only (custom role holding exactly
# iam.serviceAccounts.signJwt, bound on that one service account) and is an IAP accessor on the api
# backend only; it receives no Cloud Run invoker, no other IAP grant and no key. Failures are
# classified by the runner (transport, iap-challenge, auth, backend, body, signing) and never carry
# a token; a monitor that STOPS after its first execution is caught by the missing-execution alert
# (metric absence needs a prior data point, so a never-started monitor is caught only by the
# first-execution bootstrap evidence, see iap_probe_first_execution). test_terraform_policy.py
# asserts the scope and the contract; probe.test.mjs exercises the runner with mocked I/O.
# ---------------------------------------------------------------------------------------------

locals {
  iap_probe_target = "https://${var.public_domain}/api/v1/healthz"
  # P3c-R1: both alert windows follow the execution period, so every supported period behaves the
  # same way. Failure window = two execution periods plus one minute of ingestion margin, so
  # count_false > 1 means AT LEAST TWO FAILED RESULTS WITHIN THE ALIGNMENT WINDOW at any period
  # (consecutive or not; DPL-37 and the SLO table require no consecutiveness). Results of a
  # regular series are p apart: two consecutive results fit in any window >= p, and the 2p + 60 s
  # window admits two consecutive results plus, with the 60 s margin, the non-consecutive F,T,F
  # pattern; a single isolated failure yields count_false = 1 and never fires. Absence duration =
  # two healthy gaps (a
  # healthy series never trips it), never below the 600 s the default period used, always a
  # multiple of 60 s and far below Google's 23.5 h ceiling. Alignment and ingestion still shift
  # the exact incident time; no live alert time is claimed.
  iap_probe_period_seconds   = tonumber(trimsuffix(var.iap_probe_period, "s"))
  iap_probe_failure_window   = "${2 * local.iap_probe_period_seconds + 60}s"
  iap_probe_absence_duration = "${max(600, 2 * local.iap_probe_period_seconds)}s"
  # The synthetic executor invokes the function as the Monitoring notification service agent; it
  # exists once monitoring.googleapis.com is enabled (verify in the supervisor's staging run).
  monitoring_notification_service_agent = "serviceAccount:service-${local.project_number}@gcp-sa-monitoring-notification.iam.gserviceaccount.com"
}

resource "google_service_account" "iap_probe" {
  count = local.synthetic_enabled ? 1 : 0

  account_id   = "${local.name}-iap-probe"
  display_name = "eRev strict-IAP health probe"
  description  = "P3c: signs its own short-lived IAP JWTs (signJwt on itself only) and passes IAP for the api backend only; no other grant."
}

# Exactly the signing permission, and only on the probe's own account.
resource "google_project_iam_custom_role" "iap_probe_jwt_signer" {
  count = local.synthetic_enabled ? 1 : 0

  project     = var.project_id
  role_id     = "erevIapProbeJwtSigner"
  title       = "eRev IAP probe JWT signer"
  description = "iam.serviceAccounts.signJwt only; bound on the probe service account itself (P3c)."
  stage       = "GA"

  permissions = [
    "iam.serviceAccounts.signJwt",
  ]
}

resource "google_service_account_iam_member" "iap_probe_self_sign" {
  count = local.synthetic_enabled ? 1 : 0

  service_account_id = google_service_account.iap_probe[0].name
  role               = google_project_iam_custom_role.iap_probe_jwt_signer[0].id
  member             = google_service_account.iap_probe[0].member
}

# IAP accessor on the API backend only (never the web backend, never iap_allowed_principals).
resource "google_iap_web_backend_service_iam_member" "iap_probe_api" {
  count = local.synthetic_enabled ? 1 : 0

  project             = var.project_id
  web_backend_service = google_compute_backend_service.api.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = google_service_account.iap_probe[0].member
}

# Runner source: the committed synthetic/iap-healthz directory (index.js, probe.js, package.json),
# zipped at plan time without its unit test; the object name carries the content hash so a changed
# runner is a new object and a new function revision.
data "archive_file" "iap_probe" {
  type        = "zip"
  source_dir  = "${path.module}/synthetic/iap-healthz"
  output_path = "${path.module}/.terraform/iap-probe-source.zip"
  excludes    = ["probe.test.mjs"]
}

resource "google_storage_bucket" "iap_probe_source" {
  count = local.synthetic_enabled ? 1 : 0

  name                        = "${var.project_id}-${local.name}-iap-probe-source"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  dynamic "encryption" {
    for_each = var.use_cmek ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.gcs.id
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_service_agent]
}

resource "google_storage_bucket_object" "iap_probe_source" {
  count = local.synthetic_enabled ? 1 : 0

  name   = "iap-healthz-${data.archive_file.iap_probe.output_md5}.zip"
  bucket = google_storage_bucket.iap_probe_source[0].name
  source = data.archive_file.iap_probe.output_path
}

resource "google_cloudfunctions2_function" "iap_probe" {
  count = local.synthetic_enabled ? 1 : 0

  name        = "${local.name}-iap-probe-${local.env}"
  location    = var.region
  description = "Strict-IAP health probe: synthetic monitor runner calling the IAP-protected /api/v1/healthz with a self-signed service-account JWT (P3c)."
  labels      = local.labels

  build_config {
    runtime     = var.iap_probe_runtime
    entry_point = "SyntheticFunction"

    source {
      storage_source {
        bucket = google_storage_bucket.iap_probe_source[0].name
        object = google_storage_bucket_object.iap_probe_source[0].name
      }
    }
  }

  service_config {
    service_account_email          = google_service_account.iap_probe[0].email
    available_memory               = "256M"
    timeout_seconds                = 60
    min_instance_count             = 0
    max_instance_count             = 1
    all_traffic_on_latest_revision = true
    # Invocation is IAM-gated (only the Monitoring executor below); no allUsers, no VPC access.
    ingress_settings = "ALLOW_ALL"

    environment_variables = {
      EREV_PROBE_TARGET_URL      = local.iap_probe_target
      EREV_PROBE_SIGNER_EMAIL    = google_service_account.iap_probe[0].email
      EREV_PROBE_JWT_TTL_SECONDS = tostring(var.iap_probe_jwt_ttl_seconds)
      EREV_PROBE_TIMEOUT_MS      = "10000"
    }
  }

  depends_on = [
    google_project_service.apis,
    google_service_account_iam_member.iap_probe_self_sign,
    google_iap_web_backend_service_iam_member.iap_probe_api,
  ]
}

# The synthetic executor must be allowed to invoke the function's Cloud Run service.
resource "google_cloud_run_v2_service_iam_member" "iap_probe_executor" {
  count = local.synthetic_enabled ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.iap_probe[0].name
  role     = "roles/run.invoker"
  member   = local.monitoring_notification_service_agent
}

resource "google_monitoring_uptime_check_config" "iap_healthz_synthetic" {
  count = local.synthetic_enabled ? 1 : 0

  display_name = "erev ${local.env} strict-IAP /api/v1/healthz (synthetic, signed JWT)"
  period       = var.iap_probe_period
  timeout      = "60s"

  synthetic_monitor {
    cloud_function_v2 {
      name = google_cloudfunctions2_function.iap_probe[0].id
    }
  }

  depends_on = [google_cloud_run_v2_service_iam_member.iap_probe_executor]
}

# Synthetic results are recorded against the function's Cloud Run revision, not an uptime_url.
resource "google_monitoring_alert_policy" "iap_probe_failed" {
  count = local.synthetic_enabled ? 1 : 0

  display_name          = "erev ${local.env} strict-IAP health probe failing"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "synthetic /api/v1/healthz probe: at least two failed results within ${local.iap_probe_failure_window} (period ${var.iap_probe_period})"

    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"cloud_run_revision\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.iap_healthz_synthetic[0].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "0s"

      aggregations {
        alignment_period     = local.iap_probe_failure_window
        per_series_aligner   = "ALIGN_COUNT_FALSE"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "The strict-IAP health probe failed: the runner classified the failure (transport = DNS/TLS/connection/timeout; iap-challenge = redirect to sign-in, never healthy; auth = 401/403, JWT expired/rejected or signer not an IAP accessor; backend = non-200; body = 200 without JSON status ok; signing = IAM Credentials signJwt or metadata token). Read the class from the function log line probe=erev-iap-healthz (no token is logged). Contract: ${local.uptime_check_contract}. Runbook: RB-10 incident handling."
    mime_type = "text/markdown"
  }
}

# A monitor that STOPS must not look healthy: alert when no execution is recorded for two periods.
# P3c-R2: a metric-absence condition "requires at least one successful measurement" and "won't be
# met when the subsystem that writes metric data has never written a data point" (Google, "Create
# metric-absence alerting policies"), so this policy detects a monitor that stops after it has
# executed once; it cannot detect a monitor that never deployed or never emitted. That case is
# covered by deployment evidence, not by a metric: the first synthetic execution and its first
# check_passed data point are recorded in var.iap_probe_first_execution (README staging checklist)
# and echoed by output iap_probe.bootstrap; until then the deployment is "unmonitored", and the
# README says so. Failed executions still write (false) samples, so a failing monitor is a
# iap_probe_failed incident, not an absence.
resource "google_monitoring_alert_policy" "iap_probe_missing" {
  count = local.synthetic_enabled ? 1 : 0

  display_name          = "erev ${local.env} strict-IAP health probe stopped executing"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "no synthetic execution recorded for ${local.iap_probe_absence_duration} (period ${var.iap_probe_period})"

    condition_absent {
      filter   = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"cloud_run_revision\" AND metric.labels.check_id=\"${google_monitoring_uptime_check_config.iap_healthz_synthetic[0].uptime_check_id}\""
      duration = local.iap_probe_absence_duration

      aggregations {
        alignment_period   = var.iap_probe_period
        per_series_aligner = "ALIGN_COUNT"
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "The strict-IAP health probe, which had executed before, produced no execution result for ${local.iap_probe_absence_duration}: the synthetic monitor is paused or deleted, or the executor lost roles/run.invoker. Health is UNKNOWN until it resumes. A monitor that never started is not detected here (metric absence needs a prior data point): check output iap_probe.bootstrap and the staging checklist. Runbook: RB-10."
    mime_type = "text/markdown"
  }
}

# SLO-01: API availability >= 99.5% non-5xx over 30 days; alert on burn rate 14.4x over 1 hour or
# 6x over 6 hours (error-budget 0.5%: 7.2% and 3.0% 5xx ratios).
resource "google_monitoring_alert_policy" "slo_01_availability" {
  display_name          = "SLO-01 erev ${local.env} api availability burn rate"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "SLO-01 fast burn: 5xx ratio > 7.2% over 1 hour (14.4x)"

    condition_threshold {
      filter             = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.name}-api\" AND metric.labels.response_code_class=\"5xx\""
      denominator_filter = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.name}-api\""
      comparison         = "COMPARISON_GT"
      threshold_value    = 0.072
      duration           = "0s"

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  conditions {
    display_name = "SLO-01 slow burn: 5xx ratio > 3.0% over 6 hours (6x)"

    condition_threshold {
      filter             = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.name}-api\" AND metric.labels.response_code_class=\"5xx\""
      denominator_filter = "metric.type=\"run.googleapis.com/request_count\" AND resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.name}-api\""
      comparison         = "COMPARISON_GT"
      threshold_value    = 0.030
      duration           = "0s"

      aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      denominator_aggregations {
        alignment_period     = "21600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "05 §7.5 SLO-01: API availability >= 99.5% non-5xx over 30 days, excluding 503 during declared maintenance. Runbook RB-10."
    mime_type = "text/markdown"
  }
}

# SLO-04: job pickup latency p95 <= 30 s for compute, close and outbox; alert p95 > 60 s for
# 15 minutes. INERT today: the application exports no pickup latency metric to Cloud
# Monitoring (var.job_pickup_latency_metric_type says why), so the policy has no time series.
resource "google_monitoring_alert_policy" "slo_04_job_pickup" {
  display_name          = "SLO-04 erev ${local.env} job pickup latency p95 > 60 s"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "SLO-04 pickup latency p95 above 60 s for 15 minutes (compute, close, outbox)"

    condition_threshold {
      filter          = "metric.type=\"${var.job_pickup_latency_metric_type}\" AND resource.type=\"global\" AND (metric.labels.queue=\"compute\" OR metric.labels.queue=\"close\" OR metric.labels.queue=\"outbox\")"
      comparison      = "COMPARISON_GT"
      threshold_value = 60
      duration        = "900s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
        group_by_fields      = ["metric.label.queue"]
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "05 §7.5 SLO-04: job pickup latency p95 <= 30 s over 7 days for compute, close and outbox. Inert until the application exports the metric this policy reads: it has no time series and never fires (05 DPL-37). Runbook RB-07 stuck jobs; check worker instance counts and the release-mismatch guard (REL-05)."
    mime_type = "text/markdown"
  }
}

# SLO-05: journal export dispatch p95 <= 2 minutes; alert on ANY dead-lettered outbox message.
resource "google_monitoring_alert_policy" "slo_05_outbox_dead" {
  display_name          = "SLO-05 erev ${local.env} outbox message DEAD"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "SLO-05 a journal export message reached DEAD"

    condition_matched_log {
      filter = "${local.log_filter_run} AND ${var.outbox_dead_log_filter}"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "1800s"
  }

  documentation {
    content   = "05 §7.5 SLO-05: any outbox message DEAD pages (log line outbox.dispatch_failed with outcome DEAD). Runbook: dead letters of JOURNAL_EXPORT (RB-07)."
    mime_type = "text/markdown"
  }
}

# SLO-06: audit chain verification 100% success; any failure pages (RB-08, SEV-1).
resource "google_monitoring_alert_policy" "slo_06_audit_chain" {
  display_name          = "SLO-06 erev ${local.env} audit chain verification failed"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids
  severity              = "CRITICAL"

  conditions {
    display_name = "SLO-06 audit or security chain verification failure"

    condition_matched_log {
      filter = "${local.log_filter_run} AND ${var.audit_chain_failure_log_filter}"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "86400s"
  }

  documentation {
    content   = "05 §7.5 SLO-06 and §7.6 SEV-1: a chain verification failure is a confidentiality/integrity incident (log line operator_alert.raised, audit or security chain). Runbook RB-08; preserve evidence before remediation."
    mime_type = "text/markdown"
  }
}

# 05 JOB-07, OPR-24 (rev 1.165): a job that no user started ended FAILED - a periodic job of the
# scheduler, a job of an API client - and the application notifies nobody of it. A warning, not a
# page: the job is read and the operation started again (runbook RB-07).
resource "google_monitoring_alert_policy" "ops_job_failed" {
  display_name          = "erev ${local.env} job failed with nobody to notify"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids
  severity              = "WARNING"

  conditions {
    display_name = "a job that no user started ended FAILED"

    condition_matched_log {
      filter = "${local.log_filter_run} AND ${var.job_failed_log_filter}"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "86400s"
  }

  documentation {
    content   = "05 §5.6 JOB-07 and §7.4 OPR-24: a job that no user started ended FAILED after its last attempt (log line operator_alert.raised with kind JOB_FAILED; alert_fields name the tenant, the job, its kind and the slug of its problem). Runbook RB-07: read the job, fix the cause, start the operation again; a periodic job is deferred again at its next tick."
    mime_type = "text/markdown"
  }
}

# 05 PRV-07 b, OPR-24 (rev 1.171): a workspace holds a file whose shred was decided and whose
# wrapped key the sweep SCH-16 could not destroy within 60 minutes - the store, its credentials or
# a lock. A warning, not a page: every reader of the workspace refuses such a file by its row
# already; what is late is the destruction of its key (runbook RB-14). The application raises the
# alert once an hour while it lasts.
resource "google_monitoring_alert_policy" "ops_file_shred_incomplete" {
  display_name          = "erev ${local.env} shred decided and not completed"
  combiner              = "OR"
  notification_channels = var.notification_channel_ids
  severity              = "WARNING"

  conditions {
    display_name = "a decided shred is not completed after 60 minutes"

    condition_matched_log {
      filter = "${local.log_filter_run} AND ${var.file_shred_incomplete_log_filter}"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s"
    }
    auto_close = "86400s"
  }

  documentation {
    content   = "05 §6.17 PRV-07 b and §7.4 OPR-24: a workspace holds files whose shred was decided and whose wrapped key is not destroyed 60 minutes later (log line operator_alert.raised with kind FILE_SHRED_INCOMPLETE; alert_fields name the tenant, the number of files and the age of the oldest decision in minutes, and no file). Every reader of the workspace refuses such a file by its row already. Runbook RB-14: find why the file store does not answer the worker (its credentials, the bucket, a lock); the sweep SCH-16 then completes the shred at its next run, and POST /files/{id}/shred sent again with a new Idempotency-Key completes it at once."
    mime_type = "text/markdown"
  }
}

# ---------------------------------------------------------------------------------------------
# Cloud Armor (05 DPL-41, SAR-13): OWASP preconfigured rules (preview by default) and an enforced
# per-IP throttle of 1,000 requests per minute.
# ---------------------------------------------------------------------------------------------

# Cloud Armor evaluates rules from the lowest priority number and applies the first matching rule;
# a preview-mode match is logged and evaluation continues. The catch-all throttle (priority 1000)
# matches every request, so every WAF rule sits BELOW 1000 (100 to 240): an enforced WAF rule
# denies a malicious request whatever its rate; in preview it is logged and the request falls
# through to the throttle (P3-R2). test_terraform_policy.py models the eight request cases.
locals {
  cloud_armor_throttle_priority = 1000

  owasp_rules = {
    sqli              = { priority = 100, expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1})" }
    xss               = { priority = 110, expression = "evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})" }
    lfi               = { priority = 120, expression = "evaluatePreconfiguredWaf('lfi-v33-stable', {'sensitivity': 1})" }
    rfi               = { priority = 130, expression = "evaluatePreconfiguredWaf('rfi-v33-stable', {'sensitivity': 1})" }
    rce               = { priority = 140, expression = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 1})" }
    method            = { priority = 150, expression = "evaluatePreconfiguredWaf('methodenforcement-v33-stable', {'sensitivity': 1})" }
    scanner           = { priority = 160, expression = "evaluatePreconfiguredWaf('scannerdetection-v33-stable', {'sensitivity': 1})" }
    protocol          = { priority = 170, expression = "evaluatePreconfiguredWaf('protocolattack-v33-stable', {'sensitivity': 1})" }
    session_fixation  = { priority = 180, expression = "evaluatePreconfiguredWaf('sessionfixation-v33-stable', {'sensitivity': 1})" }
    php               = { priority = 190, expression = "evaluatePreconfiguredWaf('php-v33-stable', {'sensitivity': 1})" }
    nodejs            = { priority = 200, expression = "evaluatePreconfiguredWaf('nodejs-v33-stable', {'sensitivity': 1})" }
    java              = { priority = 210, expression = "evaluatePreconfiguredWaf('java-v33-stable', {'sensitivity': 1})" }
    cve               = { priority = 220, expression = "evaluatePreconfiguredWaf('cve-canary', {'sensitivity': 1})" }
    json_sqli_canary  = { priority = 230, expression = "evaluatePreconfiguredWaf('json-sqli-canary', {'sensitivity': 1})" }
    protocol_attack_2 = { priority = 240, expression = "evaluatePreconfiguredWaf('rce-v33-stable', {'sensitivity': 2})" }
  }
}

resource "google_compute_security_policy" "erev" {
  name        = "${local.name}-armor-${local.env}"
  description = "05 DPL-41: OWASP preconfigured WAF (preview=${var.cloud_armor_preview}) and SAR-13 per-IP throttle."
  type        = "CLOUD_ARMOR"

  # SAR-13, DPL-41: 1,000 requests per minute per client IP, always enforced; evaluated after
  # every WAF rule (all WAF priorities are lower numbers).
  rule {
    action      = "throttle"
    priority    = local.cloud_armor_throttle_priority
    description = "SAR-13 per-client-IP throttle: ${local.cloud_armor_throttle_rpm} requests per minute"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"

      rate_limit_threshold {
        count        = local.cloud_armor_throttle_rpm
        interval_sec = 60
      }
    }
  }

  dynamic "rule" {
    for_each = local.owasp_rules
    content {
      action      = "deny(403)"
      priority    = rule.value.priority
      preview     = var.cloud_armor_preview
      description = "OWASP ${rule.key}"

      match {
        expr {
          expression = rule.value.expression
        }
      }
    }
  }

  rule {
    action      = "allow"
    priority    = 2147483647
    description = "default allow"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------------------------------------
# Connection budget (05 §2.7 hosted rule; runtime contract "The infrastructure connection budget
# must include both worker pools of database connections, API connections, rollout overlap and an
# operational reserve"). Per-instance figures are the CODE's, which the §2.7 table states since 05
# rev 1.106 (build_engine pool_size 10 / max_overflow 10; worker Procrastinate pool concurrency + 2).
#
#   api instance      = api_pool_size + api_max_overflow                     (one app engine)
#   worker instance   = (worker_concurrency + 2)                             Procrastinate pool
#                     + worker_sqlalchemy_pool_size + worker_sqlalchemy_max_overflow
#   steady state      = api_max × api instance + compute_max × worker instance
#                     + general_max × worker instance
#   rollout overlap   = the old revision draining at its minimum instance count while the new
#                       revision runs at its maximum (Cloud Run may briefly exceed max instances,
#                       so this is a budget, not a semaphore)
#   total             = steady state + rollout overlap + migrate allowance + reserve
#   rule              = total <= 80% of db_max_connections, enforced by a BLOCKING lifecycle
#                       precondition on the Cloud SQL instance (cloud_sql.tf), which fails the
#                       plan; a `check` block would only warn (P3-R4).
# The rollout term budgets the old revision at its MINIMUM instance count only; it is a documented
# assumption, not a worst-case bound (Cloud Run may briefly exceed max instances). The variables'
# defaults, the §2.7 table and build_engine are held together by
# backend/tests/unit/deploy/test_lock_budget_settings.py; P5 re-derives the budget when the pools
# become configurable.
# ---------------------------------------------------------------------------------------------

locals {
  api_connections_per_instance    = var.api_pool_size + var.api_max_overflow
  worker_procrastinate_pool       = var.worker_concurrency + 2
  worker_connections_per_instance = local.worker_procrastinate_pool + var.worker_sqlalchemy_pool_size + var.worker_sqlalchemy_max_overflow

  api_connections_steady            = var.api_max_instances * local.api_connections_per_instance
  worker_compute_connections_steady = var.worker_compute_max_instances * local.worker_connections_per_instance
  worker_general_connections_steady = var.worker_general_max_instances * local.worker_connections_per_instance
  connections_steady_state          = local.api_connections_steady + local.worker_compute_connections_steady + local.worker_general_connections_steady

  connections_rollout_overlap = (
    var.api_min_instances * local.api_connections_per_instance
    + var.worker_compute_min_instances * local.worker_connections_per_instance
    + var.worker_general_min_instances * local.worker_connections_per_instance
  )

  max_db_connections_used = local.connections_steady_state + local.connections_rollout_overlap + var.migrate_connection_allowance + var.db_connection_reserve
  db_connection_budget    = floor(var.db_max_connections * 0.8)
}

locals {
  db_connection_budget_ok = local.max_db_connections_used <= local.db_connection_budget
}
