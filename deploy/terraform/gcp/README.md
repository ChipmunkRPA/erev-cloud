# eRev Cloud hosted artifacts: Terraform for GCP (Cloud Run + Cloud SQL)

Specification: `docs/05-ARCHITECTURE.md` §8.3 (DPL-30 to DPL-42), §2.7 (connection pools), §6.5
(key catalogue), §7.2 (OPR-07, OPR-08, OPR-11, OPR-16, OPR-17), §7.5 (SLO table); BUILD_SPEC DEP-3
and DEP-4 (`docs/build-spec/14-close-reports-ai-demo-release.md`); the hosted runtime contract of
2026-09-19 (worker services with a health listener, GCS immutable-object contract, pinned secret
versions, separate tenant-secret provisioning identity); D-47.

**These files are artifacts only. They are never applied by the loop or by any lane**
(`docs/00-GOAL.md` §2 item 14 and §4; DG-FORBID-07). The only Terraform commands the repository
runs are `init -backend=false -input=false`, `fmt -check -recursive` and `validate`, through the
supervisor target `make tf-validate` (`scripts/tf_validate.sh`, DG-MK-tf-validate). No subcommand
that reads or writes state, needs cloud credentials or changes cloud resources appears in any make
target, script or documented command. Live provisioning needs Ray's explicit authorisation at that
step.

## Layout

One root module, one state per GCP project. File names follow `docs/dev-guide.md` §1.1 (05 DPL-30
rev 1.1: the dev guide governs the names; the DPL-30 resource groups map onto them).

| File | DPL-30 group | Contents |
|---|---|---|
| `versions.tf` | root | Terraform `>= 1.6`; `hashicorp/google ~> 6.0`; `hashicorp/google-beta ~> 6.0` (service identities only); `hashicorp/random ~> 3.6`; `hashicorp/archive ~> 2.4` (the probe runner zip) |
| `providers.tf` | root | `google` and `google-beta` providers: project and region only; no credentials |
| `variables.tf` | root | every input, with the unknown inputs UI-1 to UI-10 as variables without defaults |
| `main.tf` | `network`, `kms`, `storage`, `iam`, `monitoring` | APIs, Cloud SQL and IAP service identities, VPC + Direct VPC egress subnet + private services access (DPL-39), key ring and three keys (DPL-34), files and digest buckets (DPL-35), service accounts and bindings (DPL-33 + the two provisioning roles), the Cloud Run invocation policy, Cloud SQL Data Access audit logging, log bucket and sinks (SAR-30), uptime checks, the strict-IAP synthetic health probe (signer identity, function, monitor, alerts) and SLO alert policies (DPL-37), Cloud Armor (DPL-41), connection budget locals |
| `synthetic/iap-healthz/` | `monitoring` | The probe runner: `index.js` (Synthetics SDK entry point), `probe.js` (pure core: JWT minting through IAM Credentials, the guarded GET, failure classes, token redaction), `package.json` (exact pins), `probe.test.mjs` (offline mocked tests, run by pytest) |
| `cloud_sql.tf` | `sql` | PostgreSQL 17 private instance, PITR, backups, CMEK, pgAudit flags, roles with generated passwords, the two KEY-06 URL secret versions (DPL-32) |
| `secrets.tf` | `secrets` | Secret Manager secrets with user-managed replication in `var.region`; KEY-05 template documented (DPL-36) |
| `cloud_run.tf` | `run` | `erev-api`, `erev-worker-compute`, `erev-worker-general`, `erev-web` services; `erev-migrate` and `erev-tenant-provision` jobs (DPL-31) |
| `artifact_registry.tf` | `registry` | Docker repository, immutable tags, vulnerability scanning (DPL-38, G19) |
| `load_balancer.tf` | `lb` | global external ALB, serverless NEGs, managed certificate, `MODERN` SSL policy, HTTP→HTTPS redirect, IAP toggle (DPL-40) |
| `outputs.tf` | root | identities, names, `max_db_connections_used`, budget breakdown; never a secret |
| `backend.tf.example` | root | GCS state backend example, never active |
| `envs/staging.tfvars.example`, `envs/production.tfvars.example` | root | placeholders for every input; one file per project |
| `.terraform.lock.hcl` | root | the provider versions the configuration was validated against |

## Variables

Every value nobody inside the repository can know is a variable **without a default**, with a
placeholder in both `envs/*.tfvars.example` files. Nothing in this directory is a real identifier
or a credential.

| Unknown input | Variables | Placeholder in the examples |
|---|---|---|
| UI-1 project, environment | `project_id`, `environment`, `invoker_iam_disabled` (public invocation without an `allUsers` binding, for the domain-restricted-sharing org policy) | `PLACEHOLDER-erev-<env>-project`, `staging` / `production`, `false` |
| UI-2 region, Cloud SQL | `region`, `db_tier`, `db_edition`, `db_availability_type`, `pitr_log_retention_days`, `use_cmek`, `db_max_connections`, `db_max_locks_per_transaction` | `europe-west1`, `db-custom-4-16384`, `ENTERPRISE`, `REGIONAL` (production), 7, `true`, 600, 4096 |
| UI-3 buckets, KMS | `files_bucket_name`, `digest_bucket_name` (null derives `erev-files-<env>`, `erev-audit-digests-<env>`), `kms_key_ring_name` | `null`, `null`, `erev` |
| UI-4 secrets | `secret_prefix`, `secret_versions` (numeric version strings; `latest` refused) | `erev-`, `"1"` each |
| UI-5 registry, images | `artifact_registry_repository`, `image_digests` (`sha256:` + 64 hex), `vulnerability_scanning` | `erev`, all-zero digests, `true` |
| UI-6 domain | `public_domain`, `trusted_proxy_hops` | `erev.example.com`, 2 |
| UI-7 IAP, Cloud Armor | `enable_iap`, `iap_allowed_principals`, `iap_healthz_exemption`, `cloud_armor_preview` | `false`, `[]`, `false`, `true` |
| strict-IAP health probe (P3c) | `iap_synthetic_health`, `iap_probe_period`, `iap_probe_runtime`, `iap_probe_jwt_ttl_seconds` | `true`, `60s`, `nodejs22`, 300 |
| UI-8 email, AI | `smtp_host`, `smtp_port`, `smtp_username`, `smtp_from`, `ai_provider` | `smtp-relay.example.com`, 587, `PLACEHOLDER-smtp-user`, `erev@example.com`, `fake` |
| UI-9 alerting | `notification_channel_ids`, `job_pickup_latency_metric_type`, `outbox_dead_log_filter`, `audit_chain_failure_log_filter`, `job_failed_log_filter`, `file_shred_incomplete_log_filter` | `projects/<placeholder>/notificationChannels/PLACEHOLDER_CHANNEL_ID`; the four log filters name what the application logs today (`outbox.dispatch_failed` with `outcome` `DEAD`; `operator_alert.raised` of a chain verification; `operator_alert.raised` of kind `JOB_FAILED`, a job that no user started; `operator_alert.raised` of kind `FILE_SHRED_INCOMPLETE`, a shred decided and not completed 60 minutes later); the metric type is inert until the application exports a pickup latency metric (05 DPL-37) |
| UI-10 worker shape | `worker_request_timeout_seconds`, `worker_health_port`, `worker_concurrency`, `*_min_instances`, `*_max_instances`, `migrate_timeout_seconds` | 300, 8080, 4, DPL-31 values, 1800 |
| connection budget | `api_pool_size`, `api_max_overflow`, `worker_sqlalchemy_pool_size`, `worker_sqlalchemy_max_overflow`, `migrate_connection_allowance`, `db_connection_reserve` | the coded pool sizes (10, 10, 10, 10), 2, 10 |
| backup role (P6 ruling, D-95) | `backup_user_enabled`, `backup_user_name`, `backup_url_secret_accessors` | `false`, `erev_backup`, `[]` |
| OPR-12 restore drill (D-95; UI-P6-2) | `restore_test_instance` (`{ project_id, instance_name }` or null) | `null` |
| network | `vpc_subnet_cidr`, `psa_prefix_length` | `10.10.0.0/24` (staging) / `10.20.0.0/24` (production), 16 |

Constants fixed by the specification are locals, not variables, so a tfvars file cannot weaken them
silently: digest retention 220,752,000 s (7 years), files soft delete 604,800 s (7 days), log
retention 400 days, KMS rotation `7776000s` and destroy scheduling `2592000s`, the Cloud Armor
throttle of 1,000 requests per minute per client IP, the `erev` name prefix of every service and
service account.

## Validate

```sh
make tf-validate          # supervisor target (D-48a): init -backend=false, fmt -check, validate
```

The target writes `.run/reports/tf-validate/report.json` with the Terraform version and the provider
versions pinned by `.terraform.lock.hcl`. Without Terraform it records `skipped-not-installed`
(never a pass). A failed provider download exits 1 with "provider download failed; supervisor
verification needed". The plugin cache lives under `.run/terraform-plugin-cache`.

Provenance: the script samples the Git identity (HEAD, dirty state) and the SHA-256 of the
validated inputs (every `*.tf`, `*.example` and the lock file under this directory) before `init`
and again after `validate`. The report carries both samples (`build_sha` / `build_sha_end`,
`worktree_dirty` / `worktree_dirty_end`, `source_sha256_start` / `source_sha256_end`,
`lock_sha256`) and `start_end_bound = true` only when they agree; a change during the run is
reported as `source-changed` with exit 1. This is start/end-bound evidence, not proof of immutable
execution: equal samples cannot exclude a change and revert between them (A → B → A). Immutable
execution is pending GATE-BIND-1 (lane P1).

Gate-evidence shape (DG-MK-00g; the GATE-BIND-1 wrapper's usable-evidence rule): the report always
carries the nine keys `target`, `command`, `build_sha`, `worktree_dirty`, `started_at`,
`finished_at`, `exit_code`, `counts`, `failures`, with `target = "tf-validate"`, `build_sha` the
HEAD of the execution context (`EREV_GATE_CONTEXT` under the wrapper, else the current directory)
and a populated `counts` on every path: `counts.stages` names `init`, `fmt` and `validate` as
`pass`, `fail` or `skipped` (all `skipped` on the `skipped-not-installed` path) next to the
`tf_files` and `providers` figures, so the release manifest classifies the run instead of reading
an empty record as `NOT_RUN`. Under the wrapper the report is written to
`<context>/.run/reports/tf-validate/report.json`, where the wrapper reads it, whatever
`EREV_RUN_DIR` says; `execution_root` and `module_root` are recorded. The module validated is
always the execution context's `deploy/terraform/gcp`: under the wrapper a test-only
`EREV_TF_VALIDATE_ROOT` that does not resolve to the context is refused before any Terraform call
(`FAIL`, `failures[] {stage: source}`, result `foreign-module-root`, the rejected path recorded as
`module_root_override`), so a report bound to captured commit A can never describe module B;
without the wrapper the override is honoured only under `EREV_ENV=test`.

`terraform validate` checks schema and references against the locked provider. It does not prove
that the resources exist, that the project's org policies accept them, or that a plan converges;
those need credentials and are out of scope for 1.0 (00-GOAL §4). Native `terraform test` with a
plan-mode run needs the same credentials and is therefore not part of the gate; the offline resource
assertions are `backend/tests/unit/deploy/test_terraform_data.py` and
`test_terraform_compute.py`.

## Cloud Run invocation policy

An external Application Load Balancer forwards to a serverless NEG without an identity token, so a
Cloud Run service behind it must accept public invocation unless IAP sits on the backend service,
in which case IAP invokes the service as its own service agent
(`service-<project number>@gcp-sa-iap.iam.gserviceaccount.com`, created here by
`google_project_service_identity.iap`), which needs `roles/run.invoker`. Ingress stays
`INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` on `erev-api` and `erev-web`, so this load balancer is the
only way in; the workers keep `INGRESS_TRAFFIC_INTERNAL_ONLY` and no invoker at all; the jobs have
no invoker. The eight modes are evaluated offline by `test_terraform_policy.py`.

| Mode | `erev-api` invokers | `erev-web` invokers | Uptime check |
|---|---|---|---|
| IAP off (default) | `allUsers`, or the invoker IAM check disabled when `invoker_iam_disabled` | same as api | `GET /api/v1/healthz`, expects 2xx |
| IAP on, `iap_healthz_exemption = false` (default) | the IAP service agent only | the IAP service agent only | **Strict-IAP health probe** (default, `iap_synthetic_health = true`): a synthetic monitor calls `https://<public_domain>/api/v1/healthz` through IAP with a JWT signed for exactly that URL by the probe identity, redirects disabled, certificate verified; passes only on 200 + JSON `status: ok`. With `iap_synthetic_health = false`: TCP check on port 443 (DNS and load-balancer reachability only) |
| IAP on, `iap_healthz_exemption = true` | the IAP service agent AND public invocation (Cloud Run IAM cannot see paths) | the IAP service agent only | `GET /api/v1/healthz`, expects 2xx, routed by the url map to a second api backend without IAP; every other path stays behind IAP |

Why a plain HTTPS uptime check cannot probe the strict mode: Cloud Monitoring uptime checks
follow redirects and evaluate the final response. An unauthenticated `GET` under IAP is answered
with a redirect to the Google sign-in page, so such a probe can never observe the 3xx challenge; it
would land on Google's login page (2xx) and validate that page rather than this deployment, while
a backend outage behind IAP would still look healthy. The uptime check's own service-agent OIDC
token carries no configurable audience, and IAP with the Google-managed OAuth client accepts no
OAuth programmatic access. Google does document one authenticated path that works with the
Google-managed client: a service-account **self-signed JWT** (`iss` = `sub` = the service account,
`aud` = the exact protected URL, `exp` within 3600 s, sent as `Authorization: Bearer`). The
strict-IAP health probe below uses it. Where `iap_synthetic_health = false`, the TCP fallback
proves front-door reachability only and api health rests on the Cloud Run startup/liveness probes
and SLO-01. When `enable_iap` is true, `iap_allowed_principals` receive
`roles/iap.httpsResourceAccessor` on both IAP backends; the probe identity receives it on the api
backend only.

## Strict-IAP health probe (synthetic monitor)

Runs when `enable_iap = true`, `iap_healthz_exemption = false` and `iap_synthetic_health = true`
(the default strict mode). A Cloud Monitoring synthetic monitor executes the Node.js runner in
`synthetic/iap-healthz/` every `iap_probe_period`; the runner:

1. obtains its own workload access token from the metadata server and calls IAM Credentials
   `signJwt` for ITS OWN service account (`erev-iap-probe`), claims `iss` = `sub` = the account,
   `aud` = exactly `https://<public_domain>/api/v1/healthz`, `exp` = `iat` + `iap_probe_jwt_ttl_seconds`
   (≤ 3600). No private key exists anywhere: the custom role `erevIapProbeJwtSigner` holds exactly
   `iam.serviceAccounts.signJwt` and is bound on that one account for that one account;
2. `GET`s the exact URL with `Authorization: Bearer <jwt>`, **redirects disabled**, default
   certificate verification and a 10-second timeout;
3. passes only on status **200** with a JSON body whose `status` is `"ok"` (`api/v1/health.py`
   `healthz`, process liveness); everything else is a classified failure, reported to Cloud Logging
   as one credential-free line (`probe=erev-iap-healthz`, `class`, `status`, `latency_ms`) and
   turned into a failed check by the Synthetics SDK.

| Runner result | Meaning |
|---|---|
| `healthy` | DNS resolved, TLS handshake and certificate valid for the host, IAP accepted the signed identity and routed to the api backend, the load balancer routed the path, the api process answered its liveness body |
| `transport` | DNS (`ENOTFOUND`), TLS (`CERT_HAS_EXPIRED`, `ERR_TLS_CERT_ALTNAME_INVALID`, …), connection or timeout: the front door is unreachable or its certificate is wrong |
| `iap-challenge` | any 3xx (the sign-in redirect): IAP did not accept the identity as authenticated; never a success, never followed |
| `auth` | 401/403: the JWT expired, has the wrong audience/signature/issuer, or the signer lost `roles/iap.httpsResourceAccessor` on the api backend |
| `backend` | any other status (5xx, 404): routed past IAP but the api or its route is unhealthy |
| `body` | 200 without `application/json` `{"status":"ok"}`: a login or error page, or the wrong service |
| `signing` | metadata token or `signJwt` failed (the signer lost its self-signing role, IAM Credentials API disabled) |

What the probe does **not** prove: readiness (`/api/v1/readyz`, database and keys) and the
end-user OAuth sign-in flow; those stay with the Cloud Run readiness/liveness probes, SLO-01 and
manual QA. Alerts, both on `monitoring.googleapis.com/uptime_check/check_passed` with resource
type `cloud_run_revision` and the synthetic check id, with windows derived from `iap_probe_period`
so every supported period (60, 300, 600, 900 s) behaves the same way: `iap_probe_failed` counts
false results in a window of two periods plus one minute (`2p + 60`: 180, 660, 1260, 1860 s) and
fires on more than one, i.e. at least two failed results within the alignment window at any period
(consecutive or not; one isolated failure never fires); `iap_probe_missing` is a
metric-absence condition of two healthy gaps (`max(600, 2p)`: 600, 600, 1200, 1800 s), so a
healthy series never trips it and a monitor that stops after it has executed is caught. Metric
absence **needs a prior data point**: Google states that a metric-absence condition "requires at
least one successful measurement" and "won't be met when the subsystem that writes metric data has
never written a data point", so `iap_probe_missing` cannot detect a monitor that never deployed or
never emitted. That never-started case is covered by deployment evidence, not by a metric: after
the first authorized apply the operator triggers or awaits the first synthetic execution, confirms
its first `check_passed` data point for the check id, and records the execution id and time in
`iap_probe_first_execution` (echoed by `output iap_probe.bootstrap`); until then the probe is
unmonitored for that case and the README says so. No automated never-started detector is provided:
Cloud Monitoring has no "expected first point" condition and a deployment-time smoke execution
needs an authenticated call the loop never makes. Failed executions still write false samples, so
a failing monitor is an `iap_probe_failed` incident, not an absence. IAM footprint of the
probe identity: `erevIapProbeJwtSigner` on itself, `roles/iap.httpsResourceAccessor` on the api
backend service, nothing else (no Cloud Run invoker, no secret, no key); the Monitoring
notification service agent (`service-<project number>@gcp-sa-monitoring-notification…`) receives
`roles/run.invoker` on the probe function only. `test_terraform_policy.py` asserts the scope and
the monitor contract offline and runs `probe.test.mjs` (mocked fetch and clock: expired JWT → 401
auth failure; 302 to sign-in → failure, never followed; 200 HTML or wrong JSON → body failure; TLS,
DNS and timeout → transport failure; `signJwt` denied → signing failure and no target request;
no token in any message; body timeout or reset after the 200 headers → one classified transport
failure record, never an unhandled throw). The mocked cases ran on the local Node (v25.9.0); the
deploy runtime is `iap_probe_runtime` (nodejs22), which is a staging item.

Staging checklist for the probe (UI-7; supervisor-owned run, never the loop): (1) the Monitoring
notification service agent exists and holds `roles/run.invoker` on the probe function; (2) the
first synthetic execution completes (trigger or await it) and its `check_passed` data point for the
check id is visible; (3) record `{ execution_id, observed_at }` in `iap_probe_first_execution` and
re-plan so `output iap_probe.bootstrap.first_execution_recorded` is true (until then the
never-started case is unmonitored); (4) the probe's IAP acceptance with the Google-managed client
is observed as a `healthy` result; (5) the runtime `nodejs22` deploys.

## Cloud Armor evaluation order

Cloud Armor evaluates rules from the lowest priority number, applies the first matching rule, and
treats a preview-mode match as logged-and-continue. The catch-all throttle (priority 1000,
`conform_action = allow` below 1,000 requests per minute per IP, `deny(429)` above) matches every
request, so every OWASP preconfigured WAF rule sits at priorities 100 to 240, below it:

| Request | WAF preview (default) | WAF enforced |
|---|---|---|
| benign, below limit | allow (throttle) | allow (throttle) |
| benign, above limit | deny 429 (throttle) | deny 429 (throttle) |
| malicious, below limit | logged by the WAF rule, then allow (throttle) | deny 403 (WAF) |
| malicious, above limit | logged by the WAF rule, then deny 429 (throttle) | deny 403 (WAF) |

With the throttle first (the pre-correction layout) a below-limit malicious request was allowed
before any WAF rule ran, in both modes. `test_cloud_armor_waf_precedes_throttle` models the eight
cases against the actual rule set.

## Promotion flow (staging → production, same digests)

Staging and production are **separate GCP projects** (05 OPR-07), each with its own state, its own
tfvars file and its own copies of every resource. Nothing is shared between them, including the
Artifact Registry repository: the release pipeline pushes the same three images to both.

1. `make release-manifest` and `make docker-build` produce the release (lane P1); the pipeline
   pushes `erev-api`, `erev-worker`, `erev-web` to the staging registry and records their digests.
2. Operators add any new secret versions out of band and pin their numbers in
   `envs/staging.tfvars` (`secret_versions`); the database URL versions are pinned automatically.
3. `envs/staging.tfvars` receives the three digests in `image_digests`; an authorised operator runs
   the staging release (never the loop). `erev-migrate` is executed first, after the pre-migration
   backup (OPR-16, RB-02), then the services roll to the new revisions.
4. Staging acceptance: `erev doctor`, one tenant journey, the worker consuming a queued job, the
   digest export, the SLO dashboards quiet.
5. **Same-digest promotion:** copy the three `image_digests` values verbatim from
   `envs/staging.tfvars` into `envs/production.tfvars`. Images are referenced by digest only
   (`<registry>/erev-api@sha256:…`), never by tag, and the registry has immutable tags, so what ran
   in staging is byte-for-byte what runs in production. Pin the production secret versions, run
   `erev-migrate`, then roll the services.
6. `output image_references` and `output pinned_secret_versions` of both states are attached to the
   release record; a difference between the two states' digests is a failed promotion.

## Rollback by revision

Cloud Run keeps every revision. Each service sends 100% of traffic to the latest revision
(`TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST`), so a rollback is: (a) set `image_digests` back to the
previous release's digests and `secret_versions` back to its pinned versions, (b) redeploy. That
creates new revisions with the old image digests, which keeps the Terraform state authoritative. An
emergency traffic shift to a previous revision in the console is acceptable for the api and web
services only; a worker cannot be split by traffic percentage because both revisions would pull from
the same PostgreSQL queue (runtime contract §4), and REL-05 then re-defers jobs whose release differs
from the worker's. Schema rollback does not exist: production is forward-fix only and a failed
migration is recovered by OPR-11 (restore from the pre-migration backup into a clone, then cut over).

## Worker shape (runtime contract)

Both workers are Cloud Run **services**, as DPL-31 specifies and the contract recommends, not worker
pools or jobs:

- `resources.cpu_idle = false` and `min_instance_count >= 1` (instance-based billing; the queue
  consumer exists without requests);
- one supervised process per instance that owns the Procrastinate loop and an HTTP health listener
  on the injected `PORT` (`worker_health_port`, default 8080; lane P2 implements the listener);
- HTTP startup probe `/startupz` (5 s period, 2 s timeout, 36 failures = 180 s, inside Google's
  240 s bound) and liveness probe `/livez` (15 s period, 2 s timeout, 4 failures);
- `INGRESS_TRAFFIC_INTERNAL_ONLY`; no public business endpoint;
- `worker_request_timeout_seconds` governs probe requests only; Cloud Run's SIGTERM grace is fixed
  at 10 s and the worker's graceful stop must fit inside it (UI-10 confirms the application value);
- `max_instance_count` is a ceiling, not a promise of parallel consumers: Cloud Run scales services
  on CPU and HTTP concurrency, not queue depth (contract §5). The SLO-04 alert on pickup latency is
  built and inert until the application exports that metric (05 DPL-37): today no policy pages
  when jobs wait for a consumer.

If a later decision adopts native worker pools, DPL-31 and DEP-4 need an amendment first; this
module then swaps the two services for `google_cloud_run_v2_worker_pool` with manual scaling.

## Connection budget (05 §2.7; runtime contract)

Per-instance figures are the code's, and 05 §2.7 states the same since rev 1.106
(`backend/erev_api/db/session.py` `build_engine`: `pool_size = 10`, `max_overflow = 10` for every
engine; `backend/erev_api/worker.py`: Procrastinate pool `max_size = worker_concurrency + 2`). Until
that revision the table read an api overflow of 5 and a worker SQLAlchemy pool of `concurrency + 2`,
which the code never had. Lane P5 makes the pools configurable; until then the tfvars values equal
the code, and a test holds the variables' defaults, the table and `build_engine` together.

```
api instance       = api_pool_size + api_max_overflow                       = 10 + 10       = 20
worker instance    = (worker_concurrency + 2)                                = 6
                   + worker_sqlalchemy_pool_size + worker_sqlalchemy_max_overflow = 10 + 10  = 26
steady state       = 10 api × 20 + 4 compute × 26 + 2 general × 26           = 200 + 104 + 52 = 356
rollout overlap    = old revision draining at its minimum while the new one is at maximum
                   = 1 × 20 + 1 × 26 + 1 × 26                                = 72
migrate allowance  = 2        (runs before a rollout, never during one)
reserve            = 10       (superuser_reserved_connections, break-glass, restore verification)
max_db_connections_used = 356 + 72 + 2 + 10                                  = 440
ceiling            = floor(0.8 × db_max_connections) = floor(0.8 × 600)      = 480   → within budget
```

`output max_db_connections_used` (DPL-31) and `output db_connection_budget` expose the arithmetic.
The rule is enforced by a BLOCKING `lifecycle { precondition }` on `google_sql_database_instance.erev`
(the instance that carries the `max_connections` flag), which fails the plan when the budget
exceeds the ceiling; a Terraform `check` block would only warn, so none is used. Cases the offline
test recomputes from the defaults: 440 ≤ 480 passes (`db_max_connections = 600`); 440 ≤ 440 passes
at the boundary (550); 440 > 400 fails at 500. The `max_connections` flag is set from
`db_max_connections`, so the ceiling is explicit rather than the tier default. The rollout term
budgets the old revision at its minimum instance count only: a documented assumption, not a
worst-case bound (Cloud Run may briefly exceed `max_instance_count`). P5 re-derives the budget
after aligning the pools to 05 §2.7.

## Lock budget (05 §2.7)

PostgreSQL sizes its shared lock table at server start as `max_locks_per_transaction ×
(max_connections + max_prepared_transactions)` slots for the whole instance. Cloud SQL leaves
`max_locks_per_transaction` at 64 unless the flag is set, and the three partitioned tables need far
more: a statement that reads one of them without a value for the partition column locks the parent,
its partitioned indexes, every partition and every index of every partition until its transaction
ends.

```
partition lock footprint  = Σ (1 + parent indexes + partitions × (1 + indexes per partition))
  audit_event             = 1 + 5 + 181 × (1 + 5)                          = 1,092
  schedule_line           = 1 + 4 + 181 × (1 + 4)                          =   910
  subledger_line          = 1 + 5 + 181 × (1 + 5)                          = 1,092
  together                                                                  = 3,094   (schema revision 0072)
relations of the database (one DDL, dump or restore transaction may hold each once)  = 5,044
sessions                  = floor(0.8 × db_max_connections)                = 480     (the connection ceiling above)
required lock slots       = 480 × 3,094 + 5,044                            = 1,490,164
max_locks_per_transaction >= ceil(1,490,164 / 600)                         = 2,484   (2,526 at 100 connections)
db_max_locks_per_transaction = 4096  → 2,457,600 slots                     → within budget
```

`db_max_locks_per_transaction` sets the flag (default 4096; the variable refuses less than 3072) and
`output db_lock_budget` shows the slots. The default leaves room for nine more years of monthly
partitions or ten more indexes on partitioned tables. The footprint is a fact of the schema, which
Terraform cannot see, so the rule itself is evaluated by `erev doctor` on the live catalogue as the
production check `lock-budget` (05 SAR-40; runbook RB-03): run it after `erev-migrate` and before the
rollout, as RB-02 says. Changing the flag restarts the instance. PostgreSQL 17 computes 1,136 MB of
shared memory at 4096 × 600 connections against 168 MB at the default 64 (measured with
`postgres -C shared_memory_size`); lower `db_max_connections` before lowering the flag. Not verified
against a live Cloud SQL instance: this module is validated offline only.

## Identities and secrets

| Service account | Runs | Grants |
|---|---|---|
| `erev-api` | `erev-api` | `roles/cloudsql.client`; `secretAccessor` on `erev-db-app-url`, `erev-security-hmac`, `erev-anthropic-api-key`, `erev-smtp-password`, `erev-metrics-token`; conditional `secretAccessor` on `erev-audit-hmac-*`; `objectAdmin` on the files bucket; `objectViewer` on the digest bucket (verifier); `cryptoKeyEncrypterDecrypter` on `erev-app-kek` |
| `erev-worker` | both workers | as the api, minus `erev-metrics-token`, plus `objectCreator` (create-only) on the digest bucket instead of viewer |
| `erev-migrate` | `erev-migrate` job | `roles/cloudsql.client`; `secretAccessor` on `erev-db-owner-url` (Alembic upgrade) and `erev-db-app-url` (the DB-14 catalogue lint that `erev migrate` runs as `erev_app` afterwards, DG-MK-migrate); nothing else |
| `erev-provisioning` | `erev-tenant-provision` job | `roles/cloudsql.client`; `secretAccessor` on `erev-db-app-url` and `erev-security-hmac` only (the Tenant Admin invitation of `erev tenant create` is an outbox EMAIL row that the worker's SCH-03 relay sends, so no SMTP credential; lane P2); custom role `erevTenantSecretCreator` (`secretmanager.secrets.create` only; project-scoped because creation is checked against the project); custom role `erevTenantSecretInitializer` (`secrets.get`, `versions.add`, `versions.access`, `versions.get`, `versions.list`) bound only under the IAM condition `resource.name.startsWith("projects/<project number>/secrets/erev-audit-hmac-")`; no delete, destroy or IAM permission anywhere |
| `erev-web` | `erev-web` | none |

Effective Secret Manager access (evaluated offline by `test_secret_access_matrix`; "add" = add a
version, "create" = create a secret):

| Secret | api | worker | migrate | provisioning | web |
|---|---|---|---|---|---|
| `erev-audit-hmac-<tenant>` (KEY-05) | access | access | none | access, add, create | none |
| `erev-db-app-url` | access | access | access (DB-14 lint) | access | none |
| `erev-db-owner-url` | none | none | access | **none** | none |
| `erev-security-hmac` | access | access | none | access | none |
| `erev-smtp-password` | access | access | none | **none** | none |
| `erev-anthropic-api-key` | access | access | none | **none** | none |
| `erev-metrics-token` | access | none | none | none | none |
| `erev-db-backup-url` (exists only when `backup_user_enabled`) | none | none | none | none | none (readers named by `backup_url_secret_accessors`) |
| any unrelated secret | none | none | none | none (may create a new one, never read or add) | none |

No project-wide editor or owner role exists, and no unconditional project-level grant can read or
add to a secret. Secrets reach containers through `secret_key_ref` with pinned version **numbers**
(SAR-25); the KEY-06 database URLs pin the version this module creates, every other injected
version comes from `secret_versions`.

Security HMAC version (KEY-03; interface for lane P2): `secret_versions.security_hmac` is not only
an output. It reaches every Python workload as `EREV_SECURITY_HMAC_SECRET_VERSION`, and the
`GcpKeyProvider` must (a) read `projects/<project>/secrets/<prefix>security-hmac/versions/<number>`
as the CURRENT signing key, never `latest`; (b) record the key id `security-hmac:<number>` on each
new `security_event` (`hmac_key_id`); (c) verify a historical event with the version named in its
stored key id, whatever the current pin; (d) treat rotation as: add a version out of band, pin its
number in tfvars, release. Acceptance for P2: requested version == returned version identifier on
startup, and a verification sample across a rotation. Tenant audit HMAC keys (KEY-05) follow the
application-owned dynamic model: the provisioning identity creates `<prefix>audit-hmac-<tenant>`
and its first version, `tenant.audit_hmac_key_id` records `audit-hmac:<tenant>:<n>`, and readers
resolve that exact version.

## Backup, restore drill and the backup role (P6 ruling as re-ruled by D-95)

Hosted production has **no `erev_backup` role and no `pg_dump` backup**. Specifying `BYPASSRLS`
requires a superuser or a role that already holds `BYPASSRLS`, and Cloud SQL customers have
neither: `cloudsqlsuperuser` is `CREATEROLE`/`CREATEDB`/`LOGIN`, and membership in it does not
inherit `BYPASSRLS`, so no documented provisioning path exists for a read-only role that reads
every tenant's rows. The hosted backup is therefore the OPR-08 automated backup with PITR (30
retained backups, `pitr_log_retention_days` of transaction logs; `cloud_sql.tf`), and the hosted
drill is OPR-12: the latest automated backup is restored into a **fresh** Cloud SQL instance in the
isolated restore-test project, then `erev doctor` and `erev verify --all-tenants` run against it
(OPR-11 step 3). `restore_test_instance` declares that target (`{ project_id, instance_name }`,
default `null`; both identifiers are unknown input UI-P6-2) and `output restore_test_target` echoes
it; the restore itself is the P6 operator step, never an apply of this module.

`backup_user_enabled` defaults to `false` and the `backup_user_*` variables are kept for the
unestablished path (a future documented `BYPASSRLS` bootstrap, or a non-Cloud-SQL PostgreSQL with a
superuser). When set, Terraform creates the user `backup_user_name` with a generated password written
to `<secret_prefix>db-backup-url` (KEY-06 family; the secret exists only then), the first
`erev-migrate` run applies `NOSUPERUSER` and the read-only grants (RB-11), and no identity can read
the URL until `backup_url_secret_accessors` names the P6 backup job identity.
`EREV_RESTORE_ADMIN_URL` is DBA-provisioned outside this module.

## pgAudit prerequisites (SAR-30)

Three things are needed before a DDL or role change produces an audit record, and the flags alone
are not enough: (1) the flags `cloudsql.enable_pgaudit = on`, `pgaudit.log = ddl,role`,
`cloudsql.pgaudit_mask_literals = on` (`cloud_sql.tf`); (2) Data Access audit logs for Cloud SQL in
the project (`google_project_iam_audit_config` for `cloudsql.googleapis.com`, `DATA_READ`,
`DATA_WRITE`, `ADMIN_READ`), because pgAudit records arrive as `cloudaudit.googleapis.com/data_access`
entries; (3) `CREATE EXTENSION pgaudit` in database `erev`, which Cloud SQL does not support through
Terraform and which needs a `cloudsqlsuperuser` member: the first `erev-migrate` run creates it
idempotently next to the role attributes (P2 executes, RB-11 documents).

## Operator steps this module does not perform

- Lock the digest bucket retention policy (RB-13, SAR-31): created unlocked; locking is irreversible.
- Harden the Cloud SQL roles after creation: Cloud SQL creates `erev_owner`, `erev_app` and
  `erev_backup` as members of `cloudsqlsuperuser`; the compose init script's attributes
  (`NOSUPERUSER`, `NOBYPASSRLS` for `erev_app`, `CREATE` on the database for `erev_owner` only,
  and, only when `backup_user_enabled`, the read-only grants for `erev_backup`, see "Backup,
  restore drill and the backup role") and `CREATE EXTENSION pgaudit` are applied idempotently
  by the first `erev-migrate` run (supervisor ruling; RB-11).
- Service identities: `google_project_service_identity` (google-beta) creates the Cloud SQL and IAP
  service agents before their grants. In a project where that resource is not permitted, create them
  out of band (`gcloud services identity create --service=sqladmin.googleapis.com` and
  `--service=iap.googleapis.com`) and keep the resources in state through import by the supervisor
  workflow, never by the loop.
- Create notification channels (UI-9), the IAP brand (UI-7) and DNS records (UI-6).
- Add secret versions for KEY-03, KEY-10, KEY-11, KEY-12 and pin them (UI-4).
- Push images by digest (UI-5) and run `erev-migrate` before each rollout (RB-02, OPR-16).
