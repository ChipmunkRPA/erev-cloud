# Outputs (05 DPL-30, DPL-31 `max_db_connections_used`, §2.7). No password, secret value or
# connection URL is ever output (DPL-32; REQ-SEC-002): the database URLs live only in Secret
# Manager versions whose NUMBERS are output for the release record.

output "lb_ip_address" {
  description = "Global IPv4 address of the HTTPS load balancer; point the DNS A record of public_domain here (UI-6)."
  value       = google_compute_global_address.lb.address
}

output "public_url" {
  description = "Public origin served by the load balancer (EREV_PUBLIC_ORIGIN)."
  value       = "https://${var.public_domain}"
}

output "managed_certificate_name" {
  description = "Google-managed certificate; ACTIVE only after DNS resolves to lb_ip_address."
  value       = google_compute_managed_ssl_certificate.erev.name
}

output "cloud_run_services" {
  description = "Cloud Run service names and internal URIs (api and web are reachable through the load balancer only; workers have no public endpoint)."
  value = {
    api            = { name = google_cloud_run_v2_service.api.name, uri = google_cloud_run_v2_service.api.uri }
    worker_compute = { name = google_cloud_run_v2_service.worker_compute.name, uri = google_cloud_run_v2_service.worker_compute.uri }
    worker_general = { name = google_cloud_run_v2_service.worker_general.name, uri = google_cloud_run_v2_service.worker_general.uri }
    web            = { name = google_cloud_run_v2_service.web.name, uri = google_cloud_run_v2_service.web.uri }
  }
}

output "cloud_run_jobs" {
  description = "Finite jobs: erev-migrate (RB-02) and erev-tenant-provision."
  value = {
    migrate          = google_cloud_run_v2_job.migrate.name
    tenant_provision = google_cloud_run_v2_job.tenant_provision.name
  }
}

output "image_references" {
  description = "The digest-pinned image references deployed by this state; identical in staging and production for one release (05 OPR-07)."
  value       = local.images
}

output "artifact_registry" {
  description = "Docker repository path the release pipeline pushes to (UI-5)."
  value       = local.registry
}

output "sql_instance" {
  description = "Cloud SQL instance identity for RB-02, RB-04 and OPR-11 (no credentials)."
  value = {
    name            = google_sql_database_instance.erev.name
    connection_name = google_sql_database_instance.erev.connection_name
    private_ip      = google_sql_database_instance.erev.private_ip_address
    edition         = var.db_edition
    tier            = var.db_tier
    pitr_days       = var.pitr_log_retention_days
  }
}

output "buckets" {
  description = "File store and audit digest buckets (05 DPL-35). The digest retention policy is unlocked until RB-13."
  value = {
    files         = google_storage_bucket.files.name
    audit_digests = google_storage_bucket.audit_digests.name
  }
}

output "kms_keys" {
  description = "Customer-managed keys (05 DPL-34). EREV_GCP_KMS_KEK equals app_kek."
  value = {
    cloudsql = google_kms_crypto_key.cloudsql.id
    gcs      = google_kms_crypto_key.gcs.id
    app_kek  = google_kms_crypto_key.app_kek.id
  }
}

output "service_accounts" {
  description = "Least-privilege identities (05 DPL-33 plus the tenant-secret provisioning identity)."
  value       = merge(local.service_accounts, { web = google_service_account.web.email })
}

output "secret_ids" {
  description = "Secret Manager ids of the static secrets (05 DPL-36) and the KEY-05 tenant template prefix."
  value = merge(
    { for key, secret in google_secret_manager_secret.static : key => secret.secret_id },
    { tenant_audit_hmac_prefix = local.tenant_audit_hmac_secret_prefix },
  )
}

output "pinned_secret_versions" {
  description = "Version NUMBERS this release binds (SAR-25): the database URLs are the versions this module created and injects; smtp_password, metrics_token and (when ai_provider = anthropic) anthropic_api_key are injected through secret_key_ref; security_hmac reaches the runtime as EREV_SECURITY_HMAC_SECRET_VERSION for the GcpKeyProvider (P3-R6). Numbers only, never values."
  value = {
    db_owner_url      = google_secret_manager_secret_version.db_owner_url.version
    db_app_url        = google_secret_manager_secret_version.db_app_url.version
    db_backup_url     = var.backup_user_enabled ? google_secret_manager_secret_version.db_backup_url[0].version : null
    security_hmac     = var.secret_versions.security_hmac
    anthropic_api_key = var.secret_versions.anthropic_api_key
    smtp_password     = var.secret_versions.smtp_password
    metrics_token     = var.secret_versions.metrics_token
  }
}

output "invocation_policy" {
  description = "Effective Cloud Run invocation policy of this configuration (P3-R1): who may invoke erev-api and erev-web, whether the invoker IAM check is disabled on them, what the uptime check probes, and that the workers have no invoker."
  value = {
    enable_iap                = var.enable_iap
    iap_healthz_exemption     = var.iap_healthz_exemption
    api_invokers              = [for key, binding in local.invoker_bindings : binding.member if binding.service == "api"]
    web_invokers              = [for key, binding in local.invoker_bindings : binding.member if binding.service == "web"]
    api_invoker_iam_disabled  = local.api_invoker_iam_disabled
    web_invoker_iam_disabled  = local.web_invoker_iam_disabled
    worker_invokers           = []
    uptime_check_probes       = local.uptime_check_contract
    healthz_bypasses_iap      = var.enable_iap && var.iap_healthz_exemption
    iap_service_agent_created = true
  }
}

output "restore_test_target" {
  description = "OPR-12 restore-drill target declared by var.restore_test_instance (D-95; UI-P6-2): the isolated project and the fresh instance the latest OPR-08 automated backup of sql_instance is restored into during the quarterly drill. null when not declared. An operator step, never an apply of this module."
  value       = var.restore_test_instance
}

output "iap_probe" {
  description = "Strict-IAP health probe (P3c): present only when IAP is on without the healthz exemption and iap_synthetic_health is true. What it proves is in `contract`; the signer may sign JWTs for itself only and is an IAP accessor on the api backend only."
  value = {
    enabled       = local.synthetic_enabled
    target        = local.synthetic_enabled ? local.iap_probe_target : null
    signer_email  = one(google_service_account.iap_probe[*].email)
    function_name = one(google_cloudfunctions2_function.iap_probe[*].name)
    check_id      = one(google_monitoring_uptime_check_config.iap_healthz_synthetic[*].uptime_check_id)
    period        = local.synthetic_enabled ? var.iap_probe_period : null
    contract      = local.synthetic_enabled ? local.uptime_check_contract : null
    tcp_fallback  = local.tcp_fallback
    # P3c-R1: alert windows derived from the period.
    failure_window   = local.synthetic_enabled ? local.iap_probe_failure_window : null
    absence_duration = local.synthetic_enabled ? local.iap_probe_absence_duration : null
    # P3c-R2: metric absence cannot see a monitor that never emitted; the first execution is
    # deployment evidence recorded by the operator.
    bootstrap = {
      first_execution_recorded = var.iap_probe_first_execution != null
      first_execution          = var.iap_probe_first_execution
      never_started_detection  = "none by metric (absence needs a prior data point); the first execution is recorded as deployment evidence"
    }
  }
}

output "backup_user" {
  description = "The optional backup role and its URL secret id (no password, no URL); null under the D-95 default (backup_user_enabled = false: hosted production has no erev_backup)."
  value = var.backup_user_enabled ? {
    name      = google_sql_user.backup[0].name
    secret_id = google_secret_manager_secret.static["db_backup_url"].secret_id
    readers   = var.backup_url_secret_accessors
  } : null
}

output "log_bucket" {
  description = "Cloud Logging bucket with 400-day retention (05 SAR-30)."
  value       = google_logging_project_bucket_config.erev.bucket_id
}

output "alert_policies" {
  description = "Alert policy names for SLO-01, SLO-04, SLO-05, SLO-06, the uptime check and the operator alerts of a failed job and of a shred that is not completed (05 DPL-37)."
  value = {
    uptime                = one(google_monitoring_alert_policy.uptime[*].name)
    iap_probe_failed      = one(google_monitoring_alert_policy.iap_probe_failed[*].name)
    iap_probe_missing     = one(google_monitoring_alert_policy.iap_probe_missing[*].name)
    slo_01                = google_monitoring_alert_policy.slo_01_availability.name
    slo_04                = google_monitoring_alert_policy.slo_04_job_pickup.name
    slo_05                = google_monitoring_alert_policy.slo_05_outbox_dead.name
    slo_06                = google_monitoring_alert_policy.slo_06_audit_chain.name
    job_failed            = google_monitoring_alert_policy.ops_job_failed.name
    file_shred_incomplete = google_monitoring_alert_policy.ops_file_shred_incomplete.name
  }
}

# 05 DPL-31: "Output max_db_connections_used computed from pool sizes (§2.7)".
output "max_db_connections_used" {
  description = "Budgeted database connections: steady state at maximum instances + the old revision draining at its MINIMUM during a rollout (a documented assumption, not a worst-case bound) + migrate allowance + reserve (05 §2.7; runtime contract). Enforced by a blocking precondition on the Cloud SQL instance."
  value       = local.max_db_connections_used
}

output "db_connection_budget" {
  description = "The arithmetic behind max_db_connections_used and the 80% ceiling enforced by the blocking precondition on google_sql_database_instance.erev (P3-R4)."
  value = {
    api_connections_per_instance    = local.api_connections_per_instance
    worker_connections_per_instance = local.worker_connections_per_instance
    api_steady                      = local.api_connections_steady
    worker_compute_steady           = local.worker_compute_connections_steady
    worker_general_steady           = local.worker_general_connections_steady
    steady_state                    = local.connections_steady_state
    rollout_overlap                 = local.connections_rollout_overlap
    migrate_allowance               = var.migrate_connection_allowance
    reserve                         = var.db_connection_reserve
    total                           = local.max_db_connections_used
    db_max_connections              = var.db_max_connections
    ceiling_80_percent              = local.db_connection_budget
    within_budget                   = local.max_db_connections_used <= local.db_connection_budget
  }
}

output "db_lock_budget" {
  description = "The lock table the instance starts with (05 §2.7 lock budget): max_locks_per_transaction × max_connections slots, and the session ceiling the rule multiplies by the partition lock footprint. `erev doctor` evaluates the rule on the live catalogue (lock-budget)."
  value = {
    db_max_locks_per_transaction = var.db_max_locks_per_transaction
    db_max_connections           = var.db_max_connections
    lock_slots                   = var.db_max_locks_per_transaction * var.db_max_connections
    sessions_ceiling_80_percent  = local.db_connection_budget
  }
}
