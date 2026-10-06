# P3b: Terraform corrections for the independent review of 3e50ac3

Lane record for platform lane P3b on `sprint/l9` (worktree `~/dev/erev-wt/l9`, base main 87368bd, which contains the P3 merge 3e50ac3 and its two integration-fix commits). Files-only lane: no database, no server, no Docker, no cloud call; nothing merged or pushed. Input: `PRODUCTION-P3-INDEPENDENT-REVIEW-3e50ac3.md` (Codex, read in full), the supervisor's P3 rulings (`.run/supervisor/prod/rulings-for-lanes.md`: services stand, §2.7 pool alignment by P5, pinned DB URL injection, separate projects, preview default true, first-migration role hardening, P6 backup role), and the team lead's brief (R1 to R6 plus pgAudit, provenance and the `erev_backup` variable). Everything the review accepted is preserved: worker services with the contract's probes, revision-level scaling with 100 % latest traffic and no tags, the pool architecture and its 440-connection default, retention separation, first-migration role hardening.

Official semantics consulted for the corrections (documentation reads only; no product call): Cloud Run "Managing access" (allUsers invoker; the invoker IAM check may be disabled, recommended under domain-restricted sharing), the external ALB serverless-NEG setup (`--allow-unauthenticated`, ingress internal-and-cloud-load-balancing), "Enabling IAP for Cloud Run" (grant `roles/run.invoker` to `service-<project number>@gcp-sa-iap.iam.gserviceaccount.com`; create the IAP service identity first), IAP "Programmatic authentication" ("If you configured your application to use the Google-managed OAuth 2.0 client … you cannot use programmatic access"), Cloud Armor "Security policy overview" (lowest priority number first; "If a request triggers a preview, Cloud Armor continues to evaluate other rules until finding a match"; default rule 2147483647), Cloud Armor rate limiting (conform action is always allow), Cloud SQL pgAudit (flag, `CREATE EXTENSION pgaudit` by a `cloudsqlsuperuser` member, "Cloud SQL doesn't support using Terraform to create the pgAudit extension", logs delivered as Data Access audit logs), and the provider schema of `hashicorp/google 6.50.0` (no `google_project_service_identity`; `invoker_iam_disabled` present; uptime `service_agent_authentication` has `type` only, no audience).

## Commits (`sprint/l9`, main..HEAD)

| Commit | Files | Change |
|---|---|---|
| ebf702b | `deploy/terraform/gcp/{versions,providers,variables,main,cloud_sql,secrets,cloud_run,load_balancer,outputs}.tf`, `README.md`, `.terraform.lock.hcl`, `envs/*.tfvars.example` | R1 to R6, pgAudit Data Access logging, `erev_backup` role; google-beta 6.50.0 added to the lock with darwin_arm64, darwin_amd64, linux_amd64, linux_arm64 hashes |
| ff37a60 | `scripts/tf_validate.sh` | Report bound to start and end Git identity plus input and lock hashes |
| 22c5cc0 | `backend/tests/unit/deploy/test_terraform_policy.py` (new), `test_terraform_compute.py`, `test_terraform_data.py`, `test_supervisor_scripts.py` | Effective-policy and provenance tests; structural updates |
| 598a576 | `docs/reviews/loop/prod/P3b-terraform-corrections.md` | Record |
| d1f01b4 | `variables.tf`, `cloud_sql.tf`, `secrets.tf`, `README.md`, record | `erev_backup` BYPASSRLS statement marked pending the P6 re-ruling; the six supervisor rulings recorded |
| 21d9d29 | `test_terraform_policy.py`, record | Main's DG-ARC-05 fixes 646a346 + 7493c16 adopted as identical patches; architecture-suite omission and its fix recorded in the gate table |
| 223fcd7 | `main.tf`, `cloud_run.tf`, `test_terraform_policy.py`, `README.md`, record | Lane P2 follow-up: `erev-migrate` also injects the version-pinned `EREV_DB_APP_URL` and its identity gets `secretAccessor` on `erev-db-app-url`, because `erev migrate` runs the DB-14 lint as `erev_app` after the upgrade (DG-MK-migrate step 2); matrix row and README updated; least privilege otherwise unchanged (the owner URL stays migrate-only) |
| ccf61e8 | `main.tf`, `outputs.tf`, `variables.tf`, `cloud_sql.tf`, `README.md`, `scripts/tf_validate.sh`, `test_terraform_policy.py`, `test_supervisor_scripts.py`, record | Codex residual review (inbox 1846): TCP front-door uptime check under IAP-on/no-exemption with the stated contract; BYPASSRLS wording; `start_end_bound` provenance claim (committed with one failing test, see the gate table) |
| aef44de | `test_terraform_policy.py`, record | `test_uptime_check_contract` fixed (multi-line local read); ccf61e8's check claim corrected in the gate table |
| this commit | `variables.tf`, `cloud_sql.tf`, `secrets.tf`, `outputs.tf`, `main.tf`, `cloud_run.tf`, `envs/*.tfvars.example`, `README.md`, `test_terraform_policy.py`, record | D-95: `backup_user_enabled` default false (variables kept for the unestablished path), `restore_test_instance` (UI-P6-2) + `output restore_test_target`, BYPASSRLS wording; P2 finding: no SMTP secret or accessor for `erev-tenant-provision` |

## Findings and corrections

### P3-R1 (high): Cloud Run invocation policy

Before: no invoker binding, no disabled invoker check, no IAP service-agent grant; api and web behind the load balancer were not invocable in either mode, and the uptime check assumed an unauthenticated `/api/v1/healthz` under IAP.

Now (`main.tf` "Cloud Run invocation policy"; `cloud_run.tf` `invoker_iam_disabled`; `load_balancer.tf` `api_health` backend and path rule; monitoring uptime check): `google_cloud_run_v2_service_iam_member.invoker` iterates `local.invoker_bindings`, whose keys are static (`api/iap`, `web/iap`, `api/public`, `web/public`) and whose conditions are pure variable expressions. Effective policy, evaluated by `test_cloud_run_invocation_policy_matrix` for all eight combinations of `enable_iap`, `iap_healthz_exemption`, `invoker_iam_disabled`:

| Mode | erev-api | erev-web | uptime check |
|---|---|---|---|
| IAP off | `allUsers`, or the invoker IAM check disabled (`invoker_iam_disabled`) | same | `/api/v1/healthz`, 2xx |
| IAP on, no exemption (default) | IAP service agent only | IAP service agent only | `/`, expects the IAP challenge (3xx): DNS, certificate, load balancer, IAP; api liveness from the Cloud Run probes and SLO-01 |
| IAP on, `iap_healthz_exemption` | IAP service agent and public invocation (Cloud Run IAM cannot see paths) | IAP service agent only | `/api/v1/healthz`, 2xx, through `google_compute_backend_service.api_health` (same NEG, no IAP, Cloud Armor on), reached only by the exact-path rule; every other path stays behind IAP |

Workers keep `INGRESS_TRAFFIC_INTERNAL_ONLY`, never set `invoker_iam_disabled`, and receive no binding; jobs receive none. The IAP service agent is created by `google_project_service_identity.iap` (google-beta) and referenced through `.member`, so the grant depends on the identity. Why no authenticated uptime probe through IAP: the uptime check's service-agent OIDC token has no configurable audience and IAP's Google-managed OAuth client permits no programmatic access; the two IAP-on rows are the honest options and UI-7 chooses (`iap_healthz_exemption` defaults to false, the stricter one).

### P3-R2 (high): WAF rules shadowed by the throttle

Before: throttle at priority 1000 with `conform_action = allow`, WAF rules at 1100 to 1240; a below-limit malicious request matched the throttle first and was allowed in both preview and enforced mode.

Now: WAF rules at 100 to 240 (`local.owasp_rules`), throttle at `local.cloud_armor_throttle_priority = 1000`, default allow at 2147483647. `test_cloud_armor_waf_precedes_throttle` sorts the actual rule set by priority and runs eight cases through the documented semantics (first matching enforced rule decides; a preview match is logged and evaluation continues):

| Request | preview (default) | enforced |
|---|---|---|
| benign, below | allow (throttle) | allow (throttle) |
| benign, above | deny 429 (throttle) | deny 429 (throttle) |
| malicious, below | logged, allow (throttle) | deny 403 (WAF) |
| malicious, above | logged, deny 429 (throttle) | deny 403 (WAF) |

The test also shows the pre-correction order allowing a below-limit malicious request when enforced, so the assertion is not vacuous. Preview stays the default (supervisor ruling; UI-7 flips it).

### P3-R3 (high): provisioning identity could reach every project secret

Before: one custom role (`secrets.create`, `secrets.get`, `versions.add`, `versions.access`, `versions.get`, `versions.list`) bound unconditionally at project scope; it could read the owner database URL and append versions to any secret.

Now: `erevTenantSecretCreator` holds `secretmanager.secrets.create` only (creation is checked against the project, so it cannot be narrowed by a resource-name condition and it alone reads or adds nothing); `erevTenantSecretInitializer` holds get/add/access/get-version/list and is bound at project level only under `resource.name.startsWith("projects/<project number>/secrets/<prefix>audit-hmac-")`. Named static grants: the provisioning identity reads `db-app-url`, `security-hmac` and `smtp-password` (`erev tenant create` invites the Tenant Admin by email, `backend/erev_api/cli.py` `tenant_create`), never `db-owner-url`, `anthropic-api-key`, `metrics-token`, `db-backup-url` or an unrelated secret. The `erev-tenant-provision` job injects `EREV_DB_APP_URL` and `EREV_SMTP_PASSWORD` only and runs with `EREV_AI_PROVIDER = "fake"`; the Anthropic injection is removed. `test_secret_access_matrix` resolves the named grants, the conditional project grants and the two roles into an allow / add / create matrix for five identities × nine secrets (the tenant HMAC secret, the owner DB URL, the app URL, SMTP, Anthropic, metrics, security HMAC, backup URL, an unrelated secret) and asserts every negative; it also asserts that no unconditional project-level binding can read or add to a secret and that no delete / destroy / disable / setIamPolicy permission or admin role appears.

### P3-R4 (medium): budget guard did not fail closed

Before: a `check` block (warning only); README said it "fails a plan".

Now: `lifecycle { precondition { condition = local.db_connection_budget_ok } }` on `google_sql_database_instance.erev` (the instance carrying the `max_connections` flag), which blocks the plan; no `check` block remains. `test_connection_budget_is_blocking` recomputes the arithmetic from the variable defaults: default 440 ≤ 480 passes; boundary `db_max_connections = 550` gives 440 ≤ 440 passes; 500 gives 440 > 400 and must fail; `api_max_instances = 12` gives 480 ≤ 480, 13 gives 500 > 480. The rollout-overlap wording in `outputs.tf` and the README now states the assumption (old revision at its minimum) rather than a worst-case bound. The 440 code-value budget stands until P5 aligns the pools to 05 §2.7 (ruling).

### P3-R5: Cloud SQL CMEK service agent

Before: the agent's email was constructed from the project number and granted the KMS key; nothing created the identity in a fresh project.

Now: `google_project_service_identity.cloud_sql` (`sqladmin.googleapis.com`, google-beta 6.50.0, the GA provider has no such resource) is created after the APIs; `local.cloud_sql_service_agent = google_project_service_identity.cloud_sql.member` feeds the KMS grant, and the instance depends on the grant, so the graph is identity → grant → instance (`test_cloud_sql_cmek_identity_bootstrap`). The README documents the external alternative (`gcloud services identity create`) for projects where the beta resource is not permitted; no cloud bootstrap enters the gate.

### P3-R6: security HMAC version not connected to the runtime

Before: `secret_versions.security_hmac` was consumed only by an output.

Now: every Python workload receives `EREV_SECURITY_HMAC_SECRET_VERSION = var.secret_versions.security_hmac` (in `local.python_env`, merged into the api, worker, migrate and provisioning environments). Interface P2 must consume (README "Security HMAC version"): the `GcpKeyProvider` reads `projects/<project>/secrets/<prefix>security-hmac/versions/<number>` as the current signing key (never `latest`), records key id `security-hmac:<number>` on new security events, verifies a historical event with the version named in its stored `hmac_key_id`, and treats rotation as add-a-version → pin → release; acceptance is requested version == returned version identifier at startup plus a verification sample across a rotation. KEY-05 tenant keys are explicitly the application-owned dynamic model (provisioning creates the secret and first version; `tenant.audit_hmac_key_id` records `audit-hmac:<tenant>:<n>`). `test_security_hmac_version_reaches_runtime` covers the env binding and the README interface.

### pgAudit prerequisites (SAR-30)

`google_project_iam_audit_config.cloudsql_data_access` enables `DATA_READ`, `DATA_WRITE` and `ADMIN_READ` Data Access audit logs for `cloudsql.googleapis.com` (pgAudit records arrive as `cloudaudit.googleapis.com/data_access`). `CREATE EXTENSION pgaudit` is assigned explicitly to the first `erev-migrate` run next to the role attributes (P2 executes, RB-11 documents), since Cloud SQL does not support creating it through Terraform. `test_pgaudit_prerequisites_assigned` checks the flags, the audit config and the assignment.

### tf_validate.sh provenance

HEAD, dirty state, the SHA-256 over every `*.tf`, `*.example` and the lock file under the module (sorted relative paths and bytes) and the lock hash are sampled before `init` and again after `validate`; the report carries both samples (`build_sha` / `build_sha_end`, `worktree_dirty` / `worktree_dirty_end`, `source_sha256_start` / `source_sha256_end`, `lock_sha256`) and `start_end_bound` (start/end-bound evidence, not immutable execution, which is pending GATE-BIND-1); a difference is `source-changed`, exit 1, failure stage `provenance`. `test_tf_validate_runs_init_fmt_validate_in_order` asserts a bound report; `test_tf_validate_detects_source_change` mutates a module file during the stub's `validate` and asserts the failure shape.

### `erev_backup` (P6 ruling)

`backup_user_enabled` (default true), `backup_user_name` (`erev_backup`), `backup_url_secret_accessors` (default empty): `google_sql_user.backup` with `random_password.backup`, secret `<prefix>db-backup-url` and its version (the third and last secret version this module writes), accessor grants only to the members P6 names. Role attributes (read-only, `NOSUPERUSER`) are applied by the first migration and documented in RB-11; **`BYPASSRLS` is pending the P6 re-ruling** (supervisor, on P3b question 5): specifying it requires a superuser or an actor already holding `BYPASSRLS`, and on Cloud SQL a customer bootstrap path is unestablished (not impossible); the native backup role applies where provisionable and hosted recovery uses managed backups and PITR (OPR-08/11/16) under an explicit recovery provider; the `backup_user_*` variables stay either way; `EREV_RESTORE_ADMIN_URL` stays DBA-provisioned outside the module. No output carries a password or URL (`test_backup_user_role`, `test_cloud_sql`).

### Codex residual review (inbox 1846): three corrections in the same commit

1. **Uptime check under IAP-on / no exemption.** Cloud Monitoring uptime checks follow redirects and evaluate the final response, so the earlier HTTPS probe of `GET /` expecting the IAP 3xx challenge could never pass on a healthy flow (the final hop is Google's sign-in page, 2xx), and broadening it to 2xx would validate Google's login page while a backend outage behind IAP stayed green. Replaced by two counted checks: `google_monitoring_uptime_check_config.healthz` (HTTPS `GET /api/v1/healthz`, final 2xx; only while the path is publicly invocable) and `google_monitoring_uptime_check_config.front_door_tcp` (TCP 443 on the public domain; IAP on without exemption), the alert following whichever exists through `one()` of the two splats. What the TCP check asserts is stated in `local.uptime_check_contract`, the alert documentation, `output invocation_policy.uptime_check_probes` and the README: DNS resolution plus the load balancer's forwarding rule and TLS listener accepting connections; nothing about the certificate, IAP or the api, whose health under that mode comes from the Cloud Run startup/liveness probes and SLO-01, with the managed certificate's `ACTIVE` status an operator check. `test_uptime_check_contract` models both matchers against the public flow (200) and the IAP flow (302 → 200 on `accounts.google.com`): the 2xx matcher passes on the wrong host under IAP, the 3xx matcher fails on a healthy IAP flow, `STATUS_CLASS_3XX` no longer appears, and the TCP check exists exactly in the IAP-on/no-exemption mode.
2. **BYPASSRLS wording** (variables, cloud_sql, README, this record): specifying `BYPASSRLS` requires a superuser or an actor already holding `BYPASSRLS`; on Cloud SQL a customer bootstrap path is unestablished, not impossible; the native backup role applies where provisionable, and hosted recovery uses managed backups and PITR (OPR-08/11/16) under an explicit recovery provider (P6 ruling).
3. **`tf_validate.sh` claim**: the report field is renamed `start_end_bound` and every "immutable" claim is reworded to start/end-bound evidence, which cannot exclude a change and revert between the samples (A → B → A); immutable execution is pending GATE-BIND-1 (lane P1). No mechanism change; the tests follow the rename.

### D-95 (backup role re-ruling) and the P2 provisioning finding

- **D-95.** Specifying `BYPASSRLS` requires a superuser or a `BYPASSRLS` holder; Cloud SQL customers have neither (`cloudsqlsuperuser` is `CREATEROLE`/`CREATEDB`/`LOGIN` and its membership does not inherit `BYPASSRLS`), so no documented provisioning path exists. Hosted production therefore has no `erev_backup` and no `pg_dump` backup; its backup is the OPR-08 automated backup + PITR and its drill is OPR-12 into a fresh instance. Applied: `backup_user_enabled` default `false` (variables kept for the unestablished path); new `restore_test_instance` (`{ project_id, instance_name }`, default `null`, validated with `try()` so the null case never dereferences; both identifiers are unknown input UI-P6-2) and `output restore_test_target`; the `erev-db-backup-url` secret exists only when `backup_user_enabled`; wording replaced in `variables.tf`, `cloud_sql.tf`, `secrets.tf`, both tfvars examples and the README section "Backup, restore drill and the backup role". Tests: `test_backup_user_role` asserts the `false` default, the `null` default and validation of `restore_test_instance`, the output, the conditional secret and the README statements.
- **P2 finding.** `provision_tenant` writes the Tenant Admin invitation as an outbox EMAIL row that the worker's SCH-03 relay sends, so `erev-tenant-provision` needs no SMTP credential: `EREV_SMTP_PASSWORD` and the `"smtp_password/provisioning"` accessor are removed; the job injects exactly `EREV_DB_APP_URL`. `test_secret_access_matrix` now expects provisioning → `erev-smtp-password` denied and asserts the provisioning env is exactly the app URL; README identities and access tables updated.

## Validate outputs (lane-run equivalents of DG-MK-tf-validate; `make tf-validate` left to the supervisor on merged main)

```
terraform 1.15.6
init -backend=false -input=false  → hashicorp/google 6.50.0, hashicorp/google-beta 6.50.0 (new), hashicorp/random 3.9.1
providers lock -platform=darwin_arm64 -platform=darwin_amd64 -platform=linux_amd64 -platform=linux_arm64 → lock updated (12 h1 hashes)
fmt -check -recursive              → exit 0
validate                           → Success! The configuration is valid.
```

Logs: `.run/p3b/tf-init.log`, `.run/p3b/tf-validate.log`. Network was used only for the google-beta provider download and hashes; no cloud authentication, no state, no plan.

## Gates (measured on `sprint/l9`)

| Gate | Result |
|---|---|
| `make lint` | OK (`.run/p3b/make-lint.log`; secrets-check 0 findings) |
| `make typecheck` | OK (560 files) |
| `make build` | OK |
| `make test TESTS="backend/tests/unit/deploy backend/tests/unit/test_makefile_targets.py" FRONTEND=0` | OK, 56 passed (`.run/p3b/make-test.log`) |
| `backend/tests/architecture` | **Omitted from the P3 and P3b lane gate sets** (the lanes ran the deploy and Makefile unit tests only). On merged main 74c3fc1 the supervisor's run failed `test_forbidden_patterns.py::test_dg_arc_05_repository_clean` on the database-administration literal at `test_terraform_policy.py:635`; fixed on main by 646a346 (statement spelled in pieces) and 7493c16 (comment length, `make lint` rc 0), asserting the same text. Both fixes are adopted on `sprint/l9` as identical patches (commit below) so the merge is clean. Re-run here after adoption: `backend/tests/architecture` + `backend/tests/unit/deploy` + `test_makefile_targets.py` = 128 passed (`.run/p3b/arch-tests.log`); `make lint` checked by exit code = 0 (`.run/p3b/make-lint-2.log`). The architecture suite joins this lane's gate set from now on. |
| Codex-residual commit ccf61e8 | **Committed while one test failed**: `test_uptime_check_contract` read the multi-line `local.uptime_check_id` with the single-line attribute reader and saw only `coalesce(`; the assertion patch missed its anchor after ruff reformatting and the command chain was not gated on the pytest exit code, so ccf61e8's message claim "129 passed" was wrong (measured: 1 failed, 128 passed; `.run/p3b/arch-tests-3.log`). Fixed in the next commit with the chain gated by exit code: architecture + deploy + Makefile tests 129 passed (`.run/p3b/arch-tests-4.log`), `make lint` rc 0 (`.run/p3b/make-lint-5.log`), fmt -check 0, validate Success. |
| `make ci` | not run: l9 has no provisioned databases (its gitignored `.env`, created from `.env.example` with the non-existent names `erev_rv_l9_*` and ports 8189/5269, exists only so lint's `erev openapi` check can load settings; no database created) |
| `make tf-validate` | not run by the lane (DG-FORBID-12); the four underlying commands above passed |

Fail-first (`.run/p3b/fail-first.log`): the four corrected test modules against the pre-correction tree (HEAD 87368bd archive) = **15 failed, 13 passed** (all nine `test_terraform_policy.py` tests; `test_versions`, `test_cloud_sql`; `test_iam_least_privilege`; `test_tf_validate_rules`, `test_tf_validate_runs_init_fmt_validate_in_order`, `test_tf_validate_detects_source_change`). On HEAD: 37 deploy tests pass (28 of those four modules + 9 in the other deploy modules) and the 19 Makefile tests pass.

## Questions returned to the supervisor

1. **IAP-on uptime identity (UI-7):** two honest options are implemented, selected by `iap_healthz_exemption`: default false (no bypass; the uptime check probes the IAP front door and api liveness relies on the Cloud Run probes and SLO-01) or true (exactly one path, `/api/v1/healthz`, bypasses IAP through a second backend, which requires public invocation of the api service, so Cloud Run IAM is no longer the boundary for the api, only the url map). Which does security want?
2. **Public invocation form (UI-1):** `allUsers` (default) or `invoker_iam_disabled = true`; the latter is Google's recommendation under domain-restricted sharing and works with the `constraints/run.managed.requireInvokerIam` policy unless it is enforced. Confirm once the org-policy inventory arrives.
3. **Secret Manager condition form:** the initializer and the api/worker tenant-secret conditions use `projects/<project number>/secrets/<prefix>audit-hmac-`. Secret Manager resource names in IAM conditions use the project number; the staging acceptance run (supervisor-owned) is where this is verified against the real service.
4. **google-beta:** two resources (`google_project_service_identity` for sqladmin and iap) need the beta provider, pinned to the same 6.50.0. If a later ruling forbids beta providers, the identities become an external prerequisite (`gcloud services identity create`) and the README already states that path.
5. **P2 interface:** `EREV_SECURITY_HMAC_SECRET_VERSION` (R6), the two-role provisioning boundary, the SMTP credential of the provisioning job, `CREATE EXTENSION pgaudit` and the backup role attributes in the first migration.
6. **`make ci`:** needs `erev_rv_l9_*` provisioned or a run on the merged tree.

## Supervisor rulings on the P3b questions (2026-09-19)

(1) `iap_healthz_exemption = false` stays the default (strict front door); the exemption is a documented opt-in recorded as external input UI-7. (2) UI-1 stays external; default `allUsers` when IAP is off, `invoker_iam_disabled` as the alternative. (3) The Secret Manager conditions derive the project number from `data.google_project.this.number` (`local.project_number`, `main.tf`), not from a typed variable, so validate/plan resolve it; staging verification stays a supervisor-owned unknown input. (4) The google-beta 6.50.0 pin is accepted. (5) P2 interface items relayed to lane P2; the `erev_backup` BYPASSRLS statement is marked pending the P6 re-ruling (this commit). (6) `make ci` is not required for this lane; the merged tree's next gate batch covers it. No PROGRESS.md line.

## Residual limits

`terraform validate` proves schema and references against `hashicorp/google` and `google-beta` 6.50.0 only; IAM condition acceptance, org-policy constraints and the IAP OAuth-client behaviour are checked only at plan/apply time, which never happens in 1.0. The policy tests evaluate the HCL conditions the module writes; they do not exercise Google's IAM engine.
