# Input variables (05 §8.3 DPL-30 to DPL-42; PRV-10; hosted runtime contract of 2026-09-19).
#
# Every external value that nobody inside the repository can know (project ids, region, domains,
# channel ids, image digests, secret versions: the unknown inputs UI-1 to UI-10 of the production
# programme) is a variable with NO default and a documented placeholder in envs/*.tfvars.example.
# Nothing here is a real identifier or a credential. Values fixed by the specification (retention
# periods, key rotation, the Cloud Armor throttle, DPL-31 instance shapes) are locals or defaults so
# that a tfvars file cannot silently weaken them without a visible diff.

# ---------------------------------------------------------------------------------------------
# UI-1: project and environment
# ---------------------------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project id of THIS deployment (UI-1). Staging and production are separate projects (05 OPR-07): one root module state per project, never one project with two environments."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project id (6 to 30 characters, lowercase letters, digits and hyphens, starting with a letter)."
  }
}

variable "environment" {
  description = "Deployment environment label used in resource names (buckets erev-files-<env>, erev-audit-digests-<env>; 05 DPL-35). Both environments run EREV_ENV=production (05 CFG-01, OPR-07)."
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be \"staging\" or \"production\"."
  }
}

variable "region" {
  description = "The one GCP region of this deployment (UI-2; 05 PRV-10): Cloud SQL, Cloud Run, GCS, KMS, Secret Manager replicas and the log bucket all live here. Multi-region residency is served by separate deployments."
  type        = string

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "region must be a GCP region name such as europe-west1."
  }
}

variable "name_prefix" {
  description = "Prefix of every resource name and of the service accounts (erev-api, erev-worker, erev-migrate, erev-provisioning, erev-web). Fixed to \"erev\" by 05 DPL-31 and DPL-33; change only with a spec amendment."
  type        = string
  default     = "erev"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,14}$", var.name_prefix))
    error_message = "name_prefix must be 2 to 15 lowercase characters, digits or hyphens."
  }
}

variable "labels" {
  description = "Additional labels merged onto every labelled resource (cost centre, owner). Keys and values follow GCP label rules."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------------------------
# UI-2: Cloud SQL edition, tier, CMEK and PITR retention
# ---------------------------------------------------------------------------------------------

variable "db_tier" {
  description = "Cloud SQL machine tier (UI-2). The default is a 4 vCPU / 16 GiB custom tier; confirm against the connection budget outputs (max_db_connections_used must stay under 80% of db_max_connections, 05 §2.7) and the performance record (PRF)."
  type        = string
  default     = "db-custom-4-16384"
}

variable "db_edition" {
  description = "Cloud SQL edition (05 DPL-32; UI-2): ENTERPRISE (default) or ENTERPRISE_PLUS."
  type        = string
  default     = "ENTERPRISE"

  validation {
    condition     = contains(["ENTERPRISE", "ENTERPRISE_PLUS"], var.db_edition)
    error_message = "db_edition must be ENTERPRISE or ENTERPRISE_PLUS."
  }
}

variable "db_availability_type" {
  description = "Cloud SQL availability. Production must be REGIONAL (05 DPL-32; a precondition on the instance enforces it); staging may use ZONAL to save cost."
  type        = string
  default     = "REGIONAL"

  validation {
    condition     = contains(["REGIONAL", "ZONAL"], var.db_availability_type)
    error_message = "db_availability_type must be REGIONAL or ZONAL."
  }
}

variable "pitr_log_retention_days" {
  description = "Transaction-log retention for point-in-time recovery in days (05 DPL-32, OPR-08: 7). UI-2 confirms the value the RPO/RTO statement is grounded on. Cloud SQL accepts 1 to 7 for ENTERPRISE and up to 35 for ENTERPRISE_PLUS."
  type        = number
  default     = 7

  validation {
    condition     = var.pitr_log_retention_days >= 1 && var.pitr_log_retention_days <= 35 && floor(var.pitr_log_retention_days) == var.pitr_log_retention_days
    error_message = "pitr_log_retention_days must be a whole number between 1 and 35."
  }
}

variable "use_cmek" {
  description = "Encrypt Cloud SQL and both buckets with the customer-managed KMS keys erev-cloudsql and erev-gcs (05 DPL-32, DPL-35, KEY-01, KEY-02). UI-1 records whether an org policy enforces CMEK; the default keeps it on."
  type        = bool
  default     = true
}

variable "db_max_connections" {
  description = "PostgreSQL max_connections flag set on the instance. The connection budget output must stay under 80% of it (05 §2.7). The default fits the default db_tier; raise the tier before raising this."
  type        = number
  default     = 600

  validation {
    condition     = var.db_max_connections >= 100 && floor(var.db_max_connections) == var.db_max_connections
    error_message = "db_max_connections must be a whole number of at least 100."
  }
}

variable "db_max_locks_per_transaction" {
  description = "PostgreSQL max_locks_per_transaction flag set on the instance (05 §2.7 lock budget). The shared lock table holds max_locks_per_transaction × max_connections slots for the whole instance; a statement that reads the three partitioned tables without the month locks 3,094 relations until its transaction ends. Rule: max_locks_per_transaction × max_connections >= floor(0.8 × max_connections) × partition lock footprint + relations, which needs 2,526 at 100 connections and 2,484 at 600 at schema revision 0072; the default leaves room for nine more years of monthly partitions. `erev doctor` evaluates the rule on the live catalogue (lock-budget). Changing the flag restarts the instance; PostgreSQL 17 computes about 1.1 GiB of shared memory at 4096 × 600 connections."
  type        = number
  default     = 4096

  validation {
    condition     = var.db_max_locks_per_transaction >= 3072 && floor(var.db_max_locks_per_transaction) == var.db_max_locks_per_transaction
    error_message = "db_max_locks_per_transaction must be a whole number of at least 3072 (05 §2.7 lock budget)."
  }
}

# ---------------------------------------------------------------------------------------------
# UI-3: bucket names and the KMS key ring
# ---------------------------------------------------------------------------------------------

variable "files_bucket_name" {
  description = "Globally unique name of the file-store bucket (UI-3). null derives <name_prefix>-files-<environment> (05 DPL-35), which may collide with another organisation's bucket: set it explicitly when the derived name is taken."
  type        = string
  default     = null
}

variable "digest_bucket_name" {
  description = "Globally unique name of the audit-digest bucket (UI-3). null derives <name_prefix>-audit-digests-<environment> (05 DPL-35). Its 7-year retention policy is created UNLOCKED; locking is the one-time manual step of RB-13 (05 SAR-31)."
  type        = string
  default     = null
}

variable "kms_key_ring_name" {
  description = "KMS key ring holding erev-cloudsql, erev-gcs and erev-app-kek (05 DPL-34; UI-3). Key rings cannot be deleted, so a fresh name is needed if one already exists in the region."
  type        = string
  default     = "erev"
}

# ---------------------------------------------------------------------------------------------
# UI-4: Secret Manager prefix and pinned versions
# ---------------------------------------------------------------------------------------------

variable "secret_prefix" {
  description = "Secret Manager id prefix, equal to EREV_GCP_SECRET_PREFIX (05 CFG-13; default erev-). Static secrets are <prefix>db-owner-url, <prefix>db-app-url, <prefix>security-hmac, <prefix>anthropic-api-key, <prefix>smtp-password, <prefix>metrics-token; tenant audit HMAC secrets are <prefix>audit-hmac-<tenant id> (KEY-05), created at runtime by the provisioning identity."
  type        = string
  default     = "erev-"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]{1,32}$", var.secret_prefix))
    error_message = "secret_prefix must be 1 to 32 letters, digits, hyphens or underscores."
  }
}

variable "secret_versions" {
  description = "Pinned Secret Manager VERSION NUMBERS injected through secret_key_ref (05 SAR-25, DPL-31; UI-4). Terraform never creates these versions (05 DPL-36): an operator adds a version out of band, then pins its number here per release. \"latest\" is refused. The two KEY-06 database URLs are pinned automatically to the version this module creates."
  type = object({
    security_hmac     = string
    anthropic_api_key = string
    smtp_password     = string
    metrics_token     = string
  })

  validation {
    condition     = alltrue([for v in values(var.secret_versions) : can(regex("^[0-9]+$", v))])
    error_message = "Every secret version must be a numeric version string such as \"1\"; \"latest\" is not pinned and is refused (SAR-25)."
  }
}

# ---------------------------------------------------------------------------------------------
# UI-5: Artifact Registry and image digests
# ---------------------------------------------------------------------------------------------

variable "artifact_registry_repository" {
  description = "Artifact Registry Docker repository id in var.region (05 DPL-38; UI-5). Images are erev-api, erev-worker and erev-web inside it."
  type        = string
  default     = "erev"
}

variable "image_digests" {
  description = "Image digests of the release being deployed (05 DPL-05, DPL-31; UI-5). Images are referenced by digest only, never by tag, so promotion from staging to production reuses the SAME three digests (05 OPR-07). Placeholders in the examples are all-zero digests that no registry holds."
  type = object({
    api    = string
    worker = string
    web    = string
  })

  validation {
    condition     = alltrue([for d in values(var.image_digests) : can(regex("^sha256:[0-9a-f]{64}$", d))])
    error_message = "Every image digest must be sha256:<64 lowercase hex characters>."
  }
}

variable "vulnerability_scanning" {
  description = "Enable Artifact Registry vulnerability scanning on the repository (G19 spec amendment; needs containerscanning.googleapis.com, enabled by this module)."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------------------------
# UI-6: domain and proxies
# ---------------------------------------------------------------------------------------------

variable "public_domain" {
  description = "Public host name served by the HTTPS load balancer and named by the managed certificate (05 DPL-40; UI-6). DNS A record must point at output lb_ip_address before the certificate can become ACTIVE. Also EREV_PUBLIC_ORIGIN = https://<public_domain>."
  type        = string

  validation {
    condition     = can(regex("^([a-z0-9-]+\\.)+[a-z]{2,}$", var.public_domain))
    error_message = "public_domain must be a lowercase DNS host name such as erev.example.com."
  }
}

variable "trusted_proxy_hops" {
  description = "EREV_TRUSTED_PROXY_HOPS (05 CFG-25): 2 hosted (the global load balancer and the Cloud Run front end each append to X-Forwarded-For). UI-6 confirms."
  type        = number
  default     = 2

  validation {
    condition     = var.trusted_proxy_hops >= 0 && var.trusted_proxy_hops <= 5
    error_message = "trusted_proxy_hops must be between 0 and 5 (05 CFG-25)."
  }
}

# ---------------------------------------------------------------------------------------------
# UI-7: IAP and Cloud Armor
# ---------------------------------------------------------------------------------------------

variable "enable_iap" {
  description = "Put Identity-Aware Proxy in front of both backend services (05 DPL-40, default false; UI-7). Uses the Google-managed OAuth client of the project's IAP brand: no client secret is passed through Terraform."
  type        = bool
  default     = false
}

variable "iap_healthz_exemption" {
  description = "When enable_iap is true: route ONLY /api/v1/healthz to a second api backend without IAP so the public uptime check keeps probing the api (P3-R1). Requires the api service to accept public invocation (allUsers or invoker_iam_disabled) because Cloud Run IAM cannot distinguish paths; the load balancer's url map is then the enforcement point and every other path stays behind IAP. Default false: no exemption, the uptime check probes the IAP front door instead (expects the IAP challenge) and api health comes from the Cloud Run probes and SLO-01. UI-7 decides."
  type        = bool
  default     = false
}

variable "invoker_iam_disabled" {
  description = "Public invocation of erev-api and erev-web WITHOUT an allUsers IAM binding, by disabling the Cloud Run invoker IAM check on the public paths (Google's recommended form under the domain-restricted-sharing org policy; UI-1). false (default) grants roles/run.invoker to allUsers instead. Applies only where invocation is public: IAP-off api/web, or the api under iap_healthz_exemption. Workers are never public."
  type        = bool
  default     = false
}

variable "iap_allowed_principals" {
  description = "IAM members granted roles/iap.httpsResourceAccessor on the backend services when enable_iap is true (UI-7), e.g. [\"domain:example.com\"] or [\"group:erev-users@example.com\"]. Ignored when IAP is off."
  type        = list(string)
  default     = []
}

variable "iap_synthetic_health" {
  description = "IAP on WITHOUT the healthz exemption (the strict mode): run the strict-IAP health probe, a Cloud Monitoring synthetic monitor backed by a Node.js Cloud Run function that calls the IAP-protected https://<public_domain>/api/v1/healthz with a short-lived service-account JWT signed through IAM Credentials signJwt (05 DPL-37 and DEP-4 external /api/v1/healthz coverage; lane P3c). true (default) keeps IAP strict and still observes DNS, TLS, IAP routing and the api health body from outside. false falls back to the TCP 443 front-door check, which proves reachability only. Ignored unless enable_iap is true and iap_healthz_exemption is false."
  type        = bool
  default     = true
}

variable "iap_probe_period" {
  description = "Execution period of the strict-IAP synthetic probe. Cloud Monitoring synthetic monitors run every 1, 5, 10 or 15 minutes."
  type        = string
  default     = "60s"

  validation {
    condition     = contains(["60s", "300s", "600s", "900s"], var.iap_probe_period)
    error_message = "iap_probe_period must be 60s, 300s, 600s or 900s."
  }
}

variable "iap_probe_runtime" {
  description = "Node.js runtime of the probe's Cloud Run function (synthetic monitors are Node.js only)."
  type        = string
  default     = "nodejs22"

  validation {
    condition     = can(regex("^nodejs(20|22|24)$", var.iap_probe_runtime))
    error_message = "iap_probe_runtime must be nodejs20, nodejs22 or nodejs24."
  }
}

variable "iap_probe_first_execution" {
  description = "Bootstrap evidence for the strict-IAP health probe (P3c-R2): the synthetic monitor's FIRST execution id and the RFC 3339 time its first check_passed data point was observed, recorded by the operator after the staging/production apply (README 'staging checklist'). Metric-absence alerting needs a prior data point, so iap_probe_missing cannot detect a monitor that never started; this record is that evidence. null (default) = not yet recorded = the probe is UNMONITORED for the never-started case. Both values are UI-7 unknown inputs supplied after the first authorized run."
  type = object({
    execution_id = string
    observed_at  = string
  })
  default = null

  validation {
    condition = var.iap_probe_first_execution == null || try(
      length(var.iap_probe_first_execution.execution_id) > 0
      && can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$", var.iap_probe_first_execution.observed_at)),
      false,
    )
    error_message = "iap_probe_first_execution must be null or { execution_id = <non-empty>, observed_at = <RFC 3339 timestamp> }."
  }
}

variable "iap_probe_jwt_ttl_seconds" {
  description = "Lifetime of each probe JWT (IAP requires exp within 3600 s of iat; the probe needs a few seconds)."
  type        = number
  default     = 300

  validation {
    condition     = var.iap_probe_jwt_ttl_seconds >= 60 && var.iap_probe_jwt_ttl_seconds <= 3600
    error_message = "iap_probe_jwt_ttl_seconds must be between 60 and 3600 (IAP bound)."
  }
}

variable "cloud_armor_preview" {
  description = "Run the OWASP preconfigured WAF rules in preview mode (logged, not enforced; 05 DPL-41 default) or enforce them (false). UI-7 decides when to flip. The per-IP throttle (SAR-13) is always enforced."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------------------------
# UI-8: email relay and AI provider
# ---------------------------------------------------------------------------------------------

variable "smtp_host" {
  description = "SMTP relay host for EREV_EMAIL_BACKEND=smtp, mandatory in production (05 SAR-40; UI-8). The password is the pinned secret <secret_prefix>smtp-password (KEY-11)."
  type        = string
}

variable "smtp_port" {
  description = "SMTP relay port (UI-8)."
  type        = number
  default     = 587
}

variable "smtp_username" {
  description = "SMTP relay user name (UI-8). Not a secret; the password is KEY-11."
  type        = string
}

variable "smtp_from" {
  description = "From address of platform email (UI-8)."
  type        = string
}

variable "ai_provider" {
  description = "EREV_AI_PROVIDER (05 CFG; UI-8): fake (default, no outbound AI call) or anthropic, which injects ANTHROPIC_API_KEY from the pinned secret <secret_prefix>anthropic-api-key (KEY-10). The kill switch stays an application setting."
  type        = string
  default     = "fake"

  validation {
    condition     = contains(["fake", "anthropic"], var.ai_provider)
    error_message = "ai_provider must be fake or anthropic."
  }
}

# ---------------------------------------------------------------------------------------------
# UI-9: monitoring notification channels
# ---------------------------------------------------------------------------------------------

variable "notification_channel_ids" {
  description = "Cloud Monitoring notification channel resource names for the SLO alert policies and the uptime alert (05 DPL-37, SLO-01/04/05/06; UI-9), e.g. projects/<project>/notificationChannels/<id>. The channels themselves (email, Slack, PagerDuty) are created outside this module."
  type        = list(string)

  validation {
    condition     = alltrue([for c in var.notification_channel_ids : can(regex("^projects/[a-z][a-z0-9-]+/notificationChannels/[0-9A-Za-z_-]+$", c))])
    error_message = "Each entry must look like projects/<project>/notificationChannels/<id>."
  }
}

variable "job_pickup_latency_metric_type" {
  description = "Inert until the application exports a job pickup latency metric to Cloud Monitoring: no metric of 05 MET-01 to MET-11 measures the pickup latency, the api serves them on GET /metrics alone (BS1-D-36) and this module builds no collector, so the SLO-04 policy has no time series and never fires. The default is the name such a metric would take (queues compute, close, outbox); set it when the metric exists."
  type        = string
  default     = "custom.googleapis.com/erev/job_pickup_latency_seconds"
}

variable "outbox_dead_log_filter" {
  description = "Cloud Logging filter fragment that matches one dead-lettered outbox message (SLO-05): the relay's log line outbox.dispatch_failed with outcome DEAD, written once the message is recorded DEAD (backend/erev_api/events/outbox.py; dev-guide DG-KRN-EVT-05)."
  type        = string
  default     = "jsonPayload.event=\"outbox.dispatch_failed\" AND jsonPayload.outcome=\"DEAD\""
}

variable "audit_chain_failure_log_filter" {
  description = "Cloud Logging filter fragment that matches one failed chain verification (SLO-06, RB-08): the operator alert of the SCH-01 job and of the SCH-02 task, logged as operator_alert.raised with kind AUDIT_CHAIN_VERIFICATION_FAILED or SECURITY_CHAIN_VERIFICATION_FAILED (backend/erev_api/controls/operator_alerts.py; 05 OPR-24)."
  type        = string
  default     = "jsonPayload.event=\"operator_alert.raised\" AND (jsonPayload.kind=\"AUDIT_CHAIN_VERIFICATION_FAILED\" OR jsonPayload.kind=\"SECURITY_CHAIN_VERIFICATION_FAILED\")"
}

variable "job_failed_log_filter" {
  description = "Cloud Logging filter fragment that matches one job that no user started and that ended FAILED after its last attempt (05 JOB-07, OPR-24; RB-07): the operator alert of the jobs registry, logged as operator_alert.raised with kind JOB_FAILED (backend/erev_api/jobs/registry.py; backend/erev_api/controls/operator_alerts.py). A job a user started notifies that user and is not matched."
  type        = string
  default     = "jsonPayload.event=\"operator_alert.raised\" AND jsonPayload.kind=\"JOB_FAILED\""
}

variable "file_shred_incomplete_log_filter" {
  description = "Cloud Logging filter fragment that matches one workspace that holds a shred decided and not completed 60 minutes later (05 PRV-07 b, OPR-24; RB-14): the operator alert of the sweep SCH-16, logged as operator_alert.raised with kind FILE_SHRED_INCOMPLETE (backend/erev_api/domain/platform/shred_completion.py; backend/erev_api/controls/operator_alerts.py). It is raised once an hour while a workspace holds such a file."
  type        = string
  default     = "jsonPayload.event=\"operator_alert.raised\" AND jsonPayload.kind=\"FILE_SHRED_INCOMPLETE\""
}

# ---------------------------------------------------------------------------------------------
# UI-10 and DPL-31: Cloud Run shapes, worker timeout, connection budget inputs
# ---------------------------------------------------------------------------------------------

variable "api_min_instances" {
  description = "erev-api minimum instances (05 DPL-31: 1)."
  type        = number
  default     = 1
}

variable "api_max_instances" {
  description = "erev-api maximum instances (05 DPL-31: 10). Enters the connection budget."
  type        = number
  default     = 10
}

variable "api_concurrency" {
  description = "erev-api maximum concurrent requests per instance (05 DPL-31: 40)."
  type        = number
  default     = 40
}

variable "worker_compute_min_instances" {
  description = "erev-worker-compute minimum instances (05 DPL-31: 1). Never 0: CPU is always allocated and the queue consumer must exist (runtime contract §2)."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_compute_min_instances >= 1
    error_message = "worker_compute_min_instances must be at least 1 (runtime contract: min 1 with cpu_idle=false)."
  }
}

variable "worker_compute_max_instances" {
  description = "erev-worker-compute maximum instances (05 DPL-31: 4). Cloud Run scales services on CPU and HTTP concurrency, not on queue depth: max 4 is a ceiling, not a promise of four busy consumers (runtime contract §5). UI-10 confirms against the perf record."
  type        = number
  default     = 4
}

variable "worker_general_min_instances" {
  description = "erev-worker-general minimum instances (05 DPL-31: 1)."
  type        = number
  default     = 1

  validation {
    condition     = var.worker_general_min_instances >= 1
    error_message = "worker_general_min_instances must be at least 1."
  }
}

variable "worker_general_max_instances" {
  description = "erev-worker-general maximum instances (05 DPL-31: 2)."
  type        = number
  default     = 2
}

variable "web_min_instances" {
  description = "erev-web minimum instances (static SPA behind nginx; not fixed by the spec)."
  type        = number
  default     = 1
}

variable "web_max_instances" {
  description = "erev-web maximum instances."
  type        = number
  default     = 4
}

variable "worker_concurrency" {
  description = "EREV_WORKER_CONCURRENCY per worker instance (05 CFG; code default 4). The Procrastinate pool is concurrency + 2 connections (backend/erev_api/worker.py), so it enters the connection budget."
  type        = number
  default     = 4

  validation {
    condition     = var.worker_concurrency >= 1 && var.worker_concurrency <= 64
    error_message = "worker_concurrency must be between 1 and 64 (05 CFG bounds)."
  }
}

variable "worker_request_timeout_seconds" {
  description = "Cloud Run request timeout of the worker services (UI-10). Applies to probe and health requests only: the queue consumer is not a request. Cloud Run's shutdown grace after SIGTERM is fixed at 10 seconds by the container contract and is not configurable here; the worker's graceful stop must fit inside it (runtime contract §6)."
  type        = number
  default     = 300

  validation {
    condition     = var.worker_request_timeout_seconds >= 1 && var.worker_request_timeout_seconds <= 3600
    error_message = "worker_request_timeout_seconds must be between 1 and 3600."
  }
}

variable "worker_health_port" {
  description = "Container port of the worker health listener (runtime contract §1: the worker binds 0.0.0.0:$PORT; Cloud Run injects PORT from this value). Probes /startupz and /livez target it."
  type        = number
  default     = 8080
}

variable "migrate_timeout_seconds" {
  description = "Cloud Run job timeout of erev-migrate (CMP-09). A migration that exceeds it fails and is recovered by OPR-16 (restore from the pre-migration backup)."
  type        = number
  default     = 1800
}

variable "api_pool_size" {
  description = "SQLAlchemy pool_size of the api app engine as CODED in backend/erev_api/db/session.py build_engine (10). 05 §2.7 lists 10; keep equal to the code until the pool becomes configurable (lane P5)."
  type        = number
  default     = 10
}

variable "api_max_overflow" {
  description = "SQLAlchemy max_overflow of the api app engine as CODED in backend/erev_api/db/session.py build_engine (10), which 05 §2.7 states since rev 1.106 (it listed 5). Keep equal to the code: the runtime contract budgets the limits actually configured."
  type        = number
  default     = 10
}

variable "worker_sqlalchemy_pool_size" {
  description = "SQLAlchemy pool_size of the worker's app engine as CODED (build_engine, 10), which 05 §2.7 states since rev 1.106 (it said concurrency + 2, the size of the Procrastinate pool). Keep equal to the code until the pool becomes configurable (lane P5)."
  type        = number
  default     = 10
}

variable "worker_sqlalchemy_max_overflow" {
  description = "SQLAlchemy max_overflow of the worker's app engine as CODED (10)."
  type        = number
  default     = 10
}

variable "migrate_connection_allowance" {
  description = "Connections reserved for one erev-migrate execution (Alembic holds one; the DB-14 lint one more). The migration runs before a rollout, never during one."
  type        = number
  default     = 2
}

variable "db_connection_reserve" {
  description = "Operational reserve added to the connection budget: superuser_reserved_connections, break-glass sessions (RB-10), the restore verification of OPR-11."
  type        = number
  default     = 10
}

# ---------------------------------------------------------------------------------------------
# Backup role and restore drill (P6 ruling 2026-09-19 as re-ruled by D-95; 05 OPR-15 amended by the
# supervisor). D-95: specifying BYPASSRLS requires a superuser or a BYPASSRLS holder, and Cloud SQL customers have neither (cloudsqlsuperuser = CREATEROLE/CREATEDB/LOGIN; its membership does not inherit BYPASSRLS), so no documented path exists. Hosted production therefore has NO erev_backup role and NO pg_dump backup: its backup is the OPR-08 automated backup + PITR and its drill is OPR-12 (restore into the fresh instance named by var.restore_test_instance, UI-P6-2). The backup_user_* variables are kept, default OFF, for the unestablished path
# (a future documented BYPASSRLS bootstrap, or a non-Cloud-SQL PostgreSQL where a superuser exists).
# ---------------------------------------------------------------------------------------------

variable "backup_user_enabled" {
  description = "Create the Cloud SQL user named by backup_user_name with a generated password written to Secret Manager as <secret_prefix>db-backup-url (KEY-06 family; the secret exists only when this is true). Default FALSE (D-95): the ruled read-only BYPASSRLS backup role has no documented provisioning path on Cloud SQL (specifying BYPASSRLS requires a superuser or a BYPASSRLS holder; Cloud SQL customers have neither, cloudsqlsuperuser being CREATEROLE/CREATEDB/LOGIN without inherited BYPASSRLS), so hosted production has no erev_backup and no pg_dump backup; its backup is the OPR-08 automated backup + PITR and its drill is OPR-12 (restore_test_instance). Set true only on a PostgreSQL where the attributes can be applied (first erev-migrate run, RB-11)."
  type        = bool
  default     = false
}

variable "backup_user_name" {
  description = "Name of the backup database role (P6 ruling: erev_backup)."
  type        = string
  default     = "erev_backup"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{2,62}$", var.backup_user_name))
    error_message = "backup_user_name must be a lowercase PostgreSQL role name."
  }
}

variable "backup_url_secret_accessors" {
  description = "IAM members granted roles/secretmanager.secretAccessor on the backup URL secret (only meaningful when backup_user_enabled). Empty by default: no identity can read the backup credential until P6 names one."
  type        = list(string)
  default     = []
}

variable "restore_test_instance" {
  description = "OPR-12 restore-drill target (D-95): the isolated restore-test project (05 OPR-12 'a separate project') and the name of the FRESH Cloud SQL instance the quarterly drill restores the latest OPR-08 automated backup into. null (default) means the drill target is not declared. Both identifiers are unknown input UI-P6-2 (Ray). Terraform only declares the target (output restore_test_target); the restore itself is the P6 operator step of OPR-12 and never an apply of this module."
  type = object({
    project_id    = string
    instance_name = string
  })
  default = null

  validation {
    condition = var.restore_test_instance == null || try(
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.restore_test_instance.project_id))
      && can(regex("^[a-z][a-z0-9-]{0,96}$", var.restore_test_instance.instance_name)),
      false,
    )
    error_message = "restore_test_instance must be null or { project_id = <GCP project id>, instance_name = <Cloud SQL instance name> } (UI-P6-2)."
  }
}

# ---------------------------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------------------------

variable "vpc_subnet_cidr" {
  description = "CIDR of the subnet used for Cloud Run Direct VPC egress (05 DPL-39). Direct VPC egress consumes IPs per instance; a /24 covers the DPL-31 maxima with room for rollouts."
  type        = string
  default     = "10.10.0.0/24"

  validation {
    condition     = can(cidrhost(var.vpc_subnet_cidr, 0))
    error_message = "vpc_subnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "psa_prefix_length" {
  description = "Prefix length of the private services access range allocated for Cloud SQL (05 DPL-39). Google recommends /16 for the peered range."
  type        = number
  default     = 16
}
