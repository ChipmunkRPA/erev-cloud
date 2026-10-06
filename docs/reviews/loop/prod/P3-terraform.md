# P3: Terraform artifacts for GCP (DEP-3, DEP-4, DEP-5 tf-validate part)

Lane record for platform lane P3 on `sprint/l7` (worktree `~/dev/erev-wt/l7`, base main 9467de0). Files-only lane: no database, no server, no Docker, no cloud call. Binding text: `docs/05-ARCHITECTURE.md` §8.3 DPL-30 to DPL-42 (rev 1.1), §2.7, §6.5, §7.2 OPR-07/08/16/17, §7.5 SLO table; BUILD_SPEC DEP-3 and DEP-4 (`docs/build-spec/14-close-reports-ai-demo-release.md:3263-3311`) and the tf-validate part of DEP-5; `docs/dev-guide.md` §1.1 file tree, §4.5 DG-MK-tf-validate, DG-FORBID-07, DG-FORBID-12; `docs/00-GOAL.md` §2 item 14 and §4 ("Applying Terraform, deploying to any cloud … out of scope"); D-47, D-48a; the hosted runtime contract (PRODUCTION-HOSTED-RUNTIME-CONTRACT-20260919) and deployment audit row DEP-D / package 3; the lane package `.run/supervisor/prod/lanes/P3.md`; `.run/supervisor/prod/unknown-inputs.md` UI-1 to UI-10. Nothing here is accounting approval, and nothing was provisioned, published or pushed.

## Commits (`sprint/l7`, main..HEAD)

| Commit | Files | Change |
|---|---|---|
| 6a72ff8 | `deploy/terraform/gcp/{versions,providers,variables,main,cloud_sql,secrets,cloud_run,artifact_registry,load_balancer,outputs}.tf`, `backend.tf.example`, `envs/staging.tfvars.example`, `envs/production.tfvars.example`, `README.md`, `.terraform.lock.hcl` | The root module (inventory below); the lock file pins the provider versions validated against, with darwin_arm64, darwin_amd64, linux_amd64 and linux_arm64 hashes |
| 08c06fe | `scripts/tf_validate.sh`, `Makefile` (delimited "lane P3" block with its own `.PHONY: tf-validate` line), `backend/tests/unit/test_makefile_targets.py` (`BUILT_TARGETS` + `tf-validate`; `test_dep_tf_validate_target`) | DG-MK-tf-validate supervisor target |
| 2289d09 | `backend/tests/support/terraform.py`, `backend/tests/unit/deploy/test_terraform_data.py`, `test_terraform_compute.py`, `test_supervisor_scripts.py` | Offline resource tests and script rules |
| 3ef1fa4 | `test_terraform_compute.py` | `test_no_apply_commands` pattern excludes Python import lines (it matched `from support.terraform import` once the tests were tracked) |
| this commit | `docs/reviews/loop/prod/P3-terraform.md`, `PROGRESS.md` (one line under "Supervisor verification needed") | Record |

## Spec quotes applied

- DPL-30 rev 1.1: "where `docs/dev-guide.md` §1.1 names other Terraform file names, the dev guide governs the file names and the resource groups below map onto those files". Applied: one flat root module with the dev-guide names; no `modules/` directory. DEP-3 places network, KMS and storage in `main.tf`; DEP-4 places IAM, monitoring and Cloud Armor there too, which makes `main.tf` the largest file (905 lines).
- DPL-31: "`erev-worker-compute` (`erev worker --queues compute,close` … min 1, max 4; CPU always allocated; 4 vCPU, 8 GiB; ingress internal only)". Applied as `args = ["worker", "--queues", join(",", local.compute_queues)]`, `cpu_idle = false`, `INGRESS_TRAFFIC_INTERNAL_ONLY`, limits cpu "4" / memory "8Gi". "Output `max_db_connections_used` computed from pool sizes (§2.7)": `output "max_db_connections_used"` plus `output "db_connection_budget"` and `check "db_connection_budget"`.
- Runtime contract §2 and §3: "Set worker `resources.cpu_idle = false` … and a minimum of one instance"; "Proposed startup: `/startupz`, 5-second period, 2-second timeout, failure threshold 36 (180 seconds) … liveness: `/livez`, 15-second period, 2-second timeout, threshold 4". Applied verbatim on both worker services; `worker_health_port` (default 8080) is the injected `PORT`.
- DPL-32: "`database_version = "POSTGRES_17"`, private IP only (`ipv4_enabled = false`) … `transaction_log_retention_days = var.pitr_log_retention_days`, `retained_backups = 30` … `deletion_protection = true`, `encryption_key_name` from `kms` when `use_cmek` … `random_password` and written to Secret Manager (no password in outputs)". Applied literally; `ssl_mode = "ENCRYPTED_ONLY"` added.
- DPL-35 / SAR-31: "`retention_policy { retention_period = 220752000 }` (7 years) unlocked". Applied with `is_locked = false`; RB-13 locks it.
- DPL-36: "no secret versions with real values in Terraform" versus DPL-32 "written to Secret Manager". Resolution: the two KEY-06 database URLs are the only `google_secret_manager_secret_version` resources, and their values are derived from `random_password` (state only, never code); every other secret has no version resource and is pinned by `var.secret_versions`. `backend.tf.example` therefore requires a CMEK-encrypted, access-restricted state bucket.
- DPL-41: "OWASP preconfigured rules in preview mode and a rate-based throttle of 1,000 requests per minute per client IP". Preview is `var.cloud_armor_preview` (default true) on the WAF rules only; the throttle is always enforced.
- DPL-42 / DG-MK-tf-validate: "(1) if `terraform` is absent, write `{"result": "skipped-not-installed"}` and exit 0; (2) `TF_PLUGIN_CACHE_DIR=$(CURDIR)/.run/terraform-plugin-cache terraform -chdir=deploy/terraform/gcp init -backend=false -input=false`; (3) `fmt -check -recursive`; (4) `validate` … When provider download fails, exit 1 with "provider download failed; supervisor verification needed"". Applied in `scripts/tf_validate.sh`; the report adds `terraform_version` and the lock-file provider versions.

## Resource inventory against the DPL items

| DPL | Delivered | File | Notes |
|---|---|---|---|
| DPL-30 | root files per dev guide, `backend.tf.example`, two `envs/*.tfvars.example`, `.terraform.lock.hcl` | all | no `modules/` (rev 1.1 mapping) |
| DPL-31 | `google_cloud_run_v2_service` `erev-api` (min 1 / max 10 / concurrency 40 / 2 vCPU / 2 GiB / `cpu_idle = true` / `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`), `erev-worker-compute`, `erev-worker-general` (2 vCPU / 4 GiB, a lane choice: the spec fixes no size), `erev-web`; `google_cloud_run_v2_job` `erev-migrate` (`args = ["migrate"]`, SA `erev-migrate`) and `erev-tenant-provision` (SA `erev-provisioning`); `secret_key_ref` with `version = env.value.version`, never `latest`; Direct VPC egress `PRIVATE_RANGES_ONLY` on every Python workload | `cloud_run.tf` | images `<registry>/erev-<x>@${var.image_digests.<x>}` |
| DPL-32 | `google_sql_database_instance` `erev-pg17-<env>`, `google_sql_database` `erev`, `google_sql_user` `erev_owner` / `erev_app`, `random_password` ×2, `google_secret_manager_secret_version` ×2 (KEY-06) | `cloud_sql.tf` | SAR-30 flags + `max_connections = var.db_max_connections`; production precondition `REGIONAL` |
| DPL-33 | SAs `erev-api`, `erev-worker`, `erev-migrate`, plus `erev-provisioning` (contract) and `erev-web` (no role); `roles/cloudsql.client`; `roles/secretmanager.secretAccessor` on named secrets (`google_secret_manager_secret_iam_member`) and a conditional project-level accessor for `erev-audit-hmac-*`; `roles/storage.objectAdmin` files bucket (api, worker); `roles/storage.objectCreator` digest bucket (worker) and `roles/storage.objectViewer` (api, verifier identity); `roles/cloudkms.cryptoKeyEncrypterDecrypter` on `erev-app-kek` (api, worker); custom role `erevTenantSecretProvisioner`; no `roles/editor` or `roles/owner` | `main.tf` | |
| DPL-34 | key ring `erev`; keys `erev-cloudsql`, `erev-gcs`, `erev-app-kek`, `rotation_period = "7776000s"`, `destroy_scheduled_duration = "2592000s"`, `prevent_destroy = true`; service-agent grants under `use_cmek` | `main.tf` | Cloud SQL service agent derived from the project number (no `google-beta` `google_project_service_identity`) |
| DPL-35 | `erev-files-<env>` (uniform, PAP enforced, versioning, soft delete 604800 s, CMEK dynamic); `erev-audit-digests-<env>` (retention 220752000 s unlocked, uniform, PAP enforced, CMEK dynamic, no versioning) | `main.tf` | names overridable by UI-3 variables |
| DPL-36 | six `google_secret_manager_secret` (KEY-03, KEY-06 ×2, KEY-10, KEY-11, KEY-12), `user_managed` replication in `var.region`; KEY-05 template `erev-audit-hmac-<tenant id>` documented and used in the IAM condition | `secrets.tf` | no Secret Manager CMEK (not in the spec) |
| DPL-37 | uptime check `/api/v1/healthz` + uptime alert; alert policies SLO-01 (5xx ratio burn 14.4× / 1 h and 6× / 6 h on `run.googleapis.com/request_count`), SLO-04 (p95 pickup latency > 60 s for 15 min on `var.job_pickup_latency_metric_type`), SLO-05 (log match `var.outbox_dead_log_filter`), SLO-06 (log match `var.audit_chain_failure_log_filter`, CRITICAL); log bucket `erev-logs-<env>` 400 days; sinks to the log bucket and pgAudit to the digest bucket | `main.tf` | metric and log-event names are P5's to confirm (defaults documented) |
| DPL-38 | `google_artifact_registry_repository` `DOCKER`, `immutable_tags = true`, `vulnerability_scanning_config { enablement_config = "INHERITED" }` under `var.vulnerability_scanning`; reader grant to the Cloud Run service agent | `artifact_registry.tf` | G19 |
| DPL-39 | VPC, subnet `erev-run-egress-<env>` (private Google access, flow logs), PSA range `/16` + `google_service_networking_connection`, egress firewall to 5432 on the PSA range, deny-all ingress | `main.tf` | no serverless VPC connector |
| DPL-40 | global address, serverless NEGs (api, web), backend services `EXTERNAL_MANAGED` with Cloud Armor and `dynamic "iap" { enabled = true }` under `var.enable_iap`, IAP accessor grants from `var.iap_allowed_principals`, url map `/api`, `/api/*` → api, default → web, managed certificate, SSL policy `MODERN` / `TLS_1_2`, HTTPS proxy, HTTP→HTTPS redirect, forwarding rules 443 and 80 | `load_balancer.tf` | |
| DPL-41 | `google_compute_security_policy`: throttle 1,000 rpm per IP (`deny(429)`), 15 `evaluatePreconfiguredWaf` rules with `preview = var.cloud_armor_preview`, default allow, adaptive protection | `main.tf` | |
| DPL-42 | `make tf-validate` → `scripts/tf_validate.sh`; report `.run/reports/tf-validate/report.json` | `Makefile`, `scripts/` | loop-forbidden; run by the supervisor |
| §2.7 | `max_db_connections_used`, `db_connection_budget`, `check "db_connection_budget"` | `main.tf`, `outputs.tf` | arithmetic below |

## Validate outputs (lane-run equivalents of DG-MK-tf-validate; `make tf-validate` itself left to the supervisor, DG-FORBID-12)

```
$ terraform version
Terraform v1.15.6 on darwin_arm64
$ TF_PLUGIN_CACHE_DIR=.run/terraform-plugin-cache terraform -chdir=deploy/terraform/gcp init -backend=false -input=false
- Installing hashicorp/google v6.50.0...  Installed hashicorp/google v6.50.0 (signed by HashiCorp)
- Installing hashicorp/random v3.9.1...   Installed hashicorp/random v3.9.1 (signed by HashiCorp)
Terraform has been successfully initialized!
$ terraform -chdir=deploy/terraform/gcp fmt -check -recursive        → exit 0 (no output)
$ terraform -chdir=deploy/terraform/gcp validate                     → Success! The configuration is valid.
$ terraform -chdir=deploy/terraform/gcp providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64 -platform=linux_arm64
Success! Terraform has updated the lock file.
```

Exact provider tested: `hashicorp/google 6.50.0` (constraint `~> 6.0`), `hashicorp/random 3.9.1` (`~> 3.6`). The network was used only for these provider downloads and hashes; no cloud authentication, no state, no plan. Logs: `.run/p3/tf-init.log`, `.run/p3/tf-validate.log`.

Out of scope, stated: policy tests on a plan JSON and `terraform test` in plan mode need project credentials (the `google_project` and `google_storage_project_service_account` data sources resolve at plan time), so they are not part of the gate; the offline assertions are the two pytest modules.

## Gates (measured on `sprint/l7`)

| Gate | Result |
|---|---|
| `make lint` | OK (`.run/p3/make-lint.log`; secrets-check 2772 files, 0 findings after the `secret =` → `key =` rename in `local.secret_accessors`, which the PASSWORD_ASSIGNMENT scan had flagged 12 times) |
| `make typecheck` | OK (560 source files) |
| `make build` | OK |
| `make test TESTS="backend/tests/unit/deploy backend/tests/unit/test_makefile_targets.py" FRONTEND=0` | OK, 46 passed (`.run/p3/make-test.log`, `.run/reports/test/report.json`) |
| direct pytest of the same files | 46 passed |
| `make ci` | FAIL at stage `env`: `cannot connect to erev_rv_l7_dev / erev_rv_l7_test / erev_rv_l7_e2e (OperationalError)` (`.run/p3/make-ci.log`, `.run/reports/ci/report.json`). The l7 worktree had no `.env`; the lane created a gitignored `.env` from `.env.example` with the non-existent database names `erev_rv_l7_*` and review ports 8197/5277 so that lint (the `erev openapi` check needs settings) can run without touching the dev database `erev` or ports 8190/5270. No database was created (DG-FORBID-03). `make ci` needs the supervisor to provision `erev_rv_l7_*` or to run it at merge. |
| `make test-pg` | not run: no DB code changed; no database in l7 |
| `make tf-validate` | not run by the lane (DG-FORBID-12); `SUPERVISOR VERIFICATION NEEDED: make tf-validate` recorded in PROGRESS.md; the four underlying commands passed as shown above |

## Fail-first evidence

`git archive 9467de0` extracted to `.run/p3/base/` with the final test files, `support/terraform.py` and `test_makefile_targets.py` copied in and the l7 venv symlinked (`.run/p3/fail-first.log`): **20 failed** (every test of the three new modules plus `test_dep_tf_validate_target` and `test_req_ops_007_fnd_targets_exist_and_are_phony`, because `deploy/terraform/gcp`, `scripts/tf_validate.sh` and the Makefile target do not exist on the base). On HEAD: 46 passed (27 deploy + 19 Makefile).

## Tests delivered

- `test_terraform_data.py` (DEP-3 names): `test_versions`, `test_cloud_sql`, `test_kms_and_storage`, `test_secrets_and_network`, plus `test_example_files_hold_placeholders_only` (every required variable set in both examples, `PLACEHOLDER` and `example.com` present, all-zero digests, no `latest`, no token patterns, `.gitignore` entries).
- `test_terraform_compute.py` (DEP-4 names): `test_cloud_run` (DPL-31 shapes via variable defaults; `cpu_idle` true on the api and false on both workers; internal ingress; `/startupz` 5/2/36 and `/livez` 15/2/4; `args` start with `["worker", "--queues", `; `secret_key_ref` versions pinned; Direct VPC egress; images by digest), `test_iam_least_privilege`, `test_load_balancer_https_only`, `test_registry_and_monitoring`, `test_no_apply_commands` (scans `git ls-files` for a state-changing Terraform subcommand written as a command; allows only the supervisor documents that state the rule: `docs/dev-guide.md`, `docs/05-ARCHITECTURE.md`, `docs/03-REQUIREMENTS.md`, `docs/BUILD_SPEC.md`, `docs/build-spec/**`; DEP-4 says "the dev-guide forbidden-command tables" — the other three documents quote the same rule and are read-only for the loop, so they are allowed too; recorded as a deviation).
- `test_supervisor_scripts.py` (DEP-5, tf-validate part only): `test_tf_validate_script_parses`, `test_tf_validate_rules`, `test_makefile_tf_validate_target`, `test_tf_validate_skipped_not_installed`, `test_tf_validate_runs_init_fmt_validate_in_order`, `test_tf_validate_failures_exit_1[init|fmt|validate]` — all against a stand-in `terraform` in a scratch root under `.run/tmp` (GIT_CEILING_DIRECTORIES stops repository discovery, so `build_sha` is `nogit`). The docker/compose/zap/audit-deps/backup parts belong to P1 and P6; P6 extends this file.
- `backend/tests/support/terraform.py`: text-level block scanner (no HCL dependency; DG-FORBID-08), `dynamic "x"` blocks flattened with their `content`.

## Connection budget (from code, per the contract)

`build_engine` (`backend/erev_api/db/session.py:191`) sets `pool_size=10, max_overflow=10` for every engine; `worker.py:256` sizes the Procrastinate pool `max_size = worker_concurrency + 2`. 05 §2.7 says api `max_overflow = 5` and worker SQLAlchemy `pool_size = concurrency + 2`; the code governs the budget (contract: "Use actual configured limits"). Defaults: api 10 × 20 = 200; compute 4 × (6 + 20) = 104; general 2 × 26 = 52; steady state 356; rollout overlap (old revision at its minimum while the new is at maximum) 20 + 26 + 26 = 72; migrate 2; reserve 10; total **440** ≤ floor(0.8 × 600) = 480 with `db_max_connections = 600` (the flag is set explicitly; the default `db-custom-4-16384` tier would otherwise default to 500, which the budget exceeds — hence the 600 default and the tier note in `variables.tf`).

## Unknown inputs consumed (all as variables without defaults unless noted; placeholders in `envs/*.tfvars.example`)

UI-1 `project_id`, `environment`; UI-2 `region`, `db_tier`, `db_edition`, `db_availability_type`, `pitr_log_retention_days`, `use_cmek`, `db_max_connections`; UI-3 `files_bucket_name`, `digest_bucket_name` (null → derived), `kms_key_ring_name`; UI-4 `secret_prefix`, `secret_versions` (numeric only; `latest` refused by validation); UI-5 `artifact_registry_repository`, `image_digests` (`sha256:` + 64 hex), `vulnerability_scanning`; UI-6 `public_domain`, `trusted_proxy_hops`; UI-7 `enable_iap`, `iap_allowed_principals`, `cloud_armor_preview`; UI-8 `smtp_host`, `smtp_port`, `smtp_username`, `smtp_from`, `ai_provider`; UI-9 `notification_channel_ids`, `job_pickup_latency_metric_type`, `outbox_dead_log_filter`, `audit_chain_failure_log_filter`; UI-10 `worker_request_timeout_seconds`, `worker_health_port`, `worker_concurrency`, the six `*_min/max_instances`, `migrate_timeout_seconds`. No real id, domain, channel, digest, version or credential appears anywhere; `secrets-check` reports 0 findings.

## Decisions and deviations to confirm

1. Flat root module (dev-guide names) instead of `modules/` (DPL-30 rev 1.1 mapping). `main.tf` carries network, KMS, storage, IAM, logging, monitoring, Cloud Armor and the budget, as DEP-3/DEP-4 place them.
2. Five service accounts, not three: `erev-provisioning` (contract) and `erev-web` (avoids the default compute account). The api holds `objectViewer` on the digest bucket as the "separate verifier identity" of the contract; the worker is creator-only.
3. `secret_key_ref` env injection of `EREV_DB_APP_URL` / `EREV_DB_OWNER_URL` (SAR-25, DPL-31) alongside `EREV_KEY_PROVIDER=gcp`, under which DG-ENV-10 says the URLs are read through `GcpSecretManagerStore` (which the contract notes uses `latest`). Both paths are wired; P2 decides which one the application reads hosted and corrects the `latest` use.
4. `EREV_GCS_FILES_BUCKET` and `EREV_GCS_AUDIT_DIGEST_BUCKET` are injected as the bucket-name settings for P2's GCS FileStore; P2 may rename them (one-line change in `local.python_env`).
5. `erev-tenant-provision` job (`args = ["tenant", "create"]`, provisioning SA, app-URL secret) is the hosted execution shape for the contract's provisioning identity; P2 owns the idempotent workflow and may change the command or role.
6. `test_no_apply_commands` allow-list covers the four supervisor documents that quote the rule, not only the dev-guide table (see Tests).
7. `.terraform.lock.hcl` is committed with four platform hashes so a Linux CI (UI-5) can `init` from the same pins.
8. No `tf-fmt` target: DEP-5 names `tf-validate` only, and `fmt -check` runs inside it; DG-GIT-05 forbids adding a DG-MK row for a new target, and DG-MK-tf-validate already exists in the dev guide, so no dev-guide edit was needed or made.

## Questions returned to the supervisor (not decided in the lane)

1. **Worker pools vs services (P2's decision):** transcribed DPL-31 services with the contract's listener and probes (`/startupz`, `/livez`, `cpu_idle = false`, min 1, internal ingress). If P2 chooses `google_cloud_run_v2_worker_pool`, DPL-31 and DEP-4 need an amendment first; the swap is local to `cloud_run.tf` and `test_cloud_run`.
2. **Connection budget conflict:** 05 §2.7 table (api 10 + 5; worker SQLAlchemy `concurrency + 2`) versus code (`build_engine` 10 + 10 for every engine; worker Procrastinate `concurrency + 2` plus a full SQLAlchemy pool). The budget uses the code and exposes the pool figures as variables for P5. Which side should be corrected: the table or the code? With the table's figures the total would be 10 × 15 + 4 × 12 + 2 × 12 + overlap (15 + 12 + 12) + 12 = 261, under 80% of 500.
3. **UI-10 worker timeout/grace:** `worker_request_timeout_seconds` defaults to 300 s and applies to probe requests only; Cloud Run's SIGTERM grace is fixed at 10 s for services. The application's graceful-stop value (P5) must fit 10 s. Confirm.
4. **UI-1 projects:** the module assumes separate staging and production projects (OPR-07): one state and one tfvars per project. Confirm; a single project with two environments would need name suffixes on project-scoped resources (custom role id, key ring, log bucket id).
5. **UI-7 Cloud Armor default:** preview `true` (DPL-41). Confirm when staging traffic shows no false positives; production example keeps `true`.
6. **Cloud SQL role attributes:** the API creates `erev_owner` and `erev_app` as `cloudsqlsuperuser` members; the compose init script's `NOSUPERUSER`, `NOBYPASSRLS` and `CREATE`-on-database attributes cannot be set from Terraform. Who applies them hosted (first `erev-migrate` run, or RB-11 by the pipeline identity)? P6.
7. **`make ci` for l7:** needs `erev_rv_l7_dev|test|e2e` provisioned, or the supervisor runs `make ci` on the merged tree. All other gates are green.
8. **Merge notes:** `Makefile` and `test_makefile_targets.py` are shared with P1 (`release-manifest`, `docker-build` in `BUILT_TARGETS` and the `.PHONY` line). P3 adds its own `.PHONY: tf-validate` line inside the delimited block, so only the `BUILT_TARGETS` frozenset line conflicts (trivial). `test_supervisor_scripts.py` is new here and will be extended by P6 (DEP-5 remaining parts). `PROGRESS.md` gains one line.

## Residual limits

- `terraform validate` proves schema and reference validity against `hashicorp/google 6.50.0` only; org-policy acceptance (CMEK enforcement, VPC-SC, domain-restricted sharing), quota, and IAM condition syntax for Secret Manager are checked only at plan/apply time, which never happens in 1.0.
- SLO-04, SLO-05 and SLO-06 alert on metric and log-event names that lane P5 has yet to publish; the defaults are recorded in `variables.tf` and the README.
- The `.env` created in l7 holds generated master keys and points at non-existent databases; it is gitignored, mode 0600, and never printed.
