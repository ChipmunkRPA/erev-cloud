# eRev Cloud customer-operated ITGC guide

eRev Cloud runs the same application controls in every deployment. A self-hosting customer operates the IT general controls around it: logical access to the infrastructure and the database, change management of the deployed version, backups and restore tests, job monitoring, secrets and key management, and database logging (REQ-CTL-004; `docs/03-REQUIREMENTS.md` §6.4). This guide grows with the product. It currently covers the database roles and the checks that run before eRev Cloud uses a database.

The application controls that the governed documents state and release 1.0 does not enforce are listed in [the limits of release 1.0](../release/LIMITS-1.0.md), section B.1; they belong in a customer's assessment of the controls it relies on.

## Database roles and prerequisites

The database operator provisions two roles and the databases before installation (D-42).

| Role | Attributes | Used for |
|---|---|---|
| `erev_owner` | `NOSUPERUSER` | Migrations; owns the schema objects; resets test schemas |
| `erev_app` | `NOSUPERUSER NOBYPASSRLS` | The API, worker, command-line tools and tests |

- `erev_owner` owns the databases, so it can create schema `erev` (DG-ENV-15).
- eRev Cloud never administers the database server. The build fails (DG-ENV-14, DG-ARC-05) when `backend/`, `scripts/`, `frontend/` or the Makefile holds one of these statements: `CREATE`, `ALTER` or `DROP` of a database, role, user, group, extension or tablespace, plus `ALTER SYSTEM`.
- Neither the application nor the isolation tests connect as a superuser.
- Control who holds the `erev_owner` credentials: grant them to the deployment pipeline and keep no standing human write access to the database.

### Checks before use

`make setup` (step 8) and stage 1 of `make ci` run `scripts/check_env.py --db` over the database pairs of `erev`, `erev_test` and `erev_e2e`. The checks print variable names, database names and role names only, never URLs or credentials.

| Check | Rule | Output on failure |
|---|---|---|
| Variables present | Every owner and app URL variable is set | `missing variable: <name>` |
| Query parameters (DG-ENV-13) | No URL sets `dbname`, `service` or `servicefile`, which could make libpq connect to another database | `database URL sets query parameter <parameter> (<variable>)` |
| Database allow-list (DG-ENV-13) | Every URL names `erev`, `erev_test`, `erev_e2e` or `erev_rv_<name>` | `database not allowed: <database> (<variable>)` |
| Connection | Both roles can connect | `cannot connect to <database> (<variable>): <error class>` |
| App role guard (DG-ENV-12) | The app connection is `erev_app` with `rolsuper` and `rolbypassrls` false | `role guard: expected erev_app without SUPERUSER or BYPASSRLS on <database>, found <role>` |
| Owner role guard (DG-ENV-12) | The owner connection is `erev_owner` with `rolsuper` false | `role guard: expected erev_owner without SUPERUSER on <database>, found <role>` |
| CREATE privilege (DG-ENV-15) | `has_database_privilege('erev_owner', current_database(), 'CREATE')` | `BLOCKED: erev_owner lacks CREATE on <database>` |
| Recovery URLs (runbook RB-04, RB-11) | `EREV_BACKUP_URL`, when present, is a `postgresql://` URL naming the allow-listed database of `EREV_DB_OWNER_URL`; `EREV_RESTORE_ADMIN_URL`, when present, names an isolated `erev_rv_*` database. The recovery provider of ruling D-95 (`EREV_RECOVERY_PROVIDER`, default `NATIVE` with `EREV_KEY_PROVIDER=local` and `MANAGED` with `gcp`; a contradicting explicit value is an error) decides: `NATIVE` requires both under `EREV_ENV=production` and reports an absent one by name elsewhere, because `make backup` and `make restore-verify` fail closed without it; `MANAGED` refuses a set value, because the native `BYPASSRLS` role is unestablished on Cloud SQL (no customer superuser, no documented grant) and the hosted backup is Cloud SQL's automated backup and PITR (05 OPR-08), and notes the managed-drill inputs as unknown (UI-P6-2). Neither is connected to or printed | `recovery URL required: <name> (EREV_ENV=production, recovery provider NATIVE; RB-04)`; `recovery URL not applicable: <name> is set under recovery provider MANAGED …`; `EREV_RECOVERY_PROVIDER=<value> contradicts EREV_KEY_PROVIDER=<value> (D-95 …)`; `recovery URL absent: <name>`; `<name> must name the database of EREV_DB_OWNER_URL (<database>), not <database>`; `<name> must name an isolated erev_rv_* restore target, not <database> (05 OPR-11)` |

On success the output is `databases OK: erev, erev_test, erev_e2e` and the exit code is 0, preceded by `recovery URLs OK: <names>` for the recovery URLs that are present. Any failure exits 1.

The application repeats these checks at runtime. It refuses a database URL that sets `dbname`, `service` or `servicefile` or names a database outside the allow-list. On every new connection its app engine requires `erev_app` without SUPERUSER or BYPASSRLS, and its owner engine requires `erev_owner` without SUPERUSER (DG-ENV-12). Both engines also require `current_database()` to equal the database the URL names, and otherwise refuse the connection with `database guard: the URL names <database>, but the connection reached <database> (DG-ENV-13)`.

Destructive schema resets run only on `erev_test`, `erev_e2e` or `erev_rv_*` databases, or through `make db-reset` in the dev environment on a development database: `erev` or an `erev_rv_*` database in which no tenant lacks the demo marker (DG-ENV-13).

## Deployment self-check

`erev doctor` (03 REQ-CTL-005; runbook RB-03) is the deployment self-check the customer operates as an IT general
control over the database and the configuration. It connects as `erev_app` and prints one line per check: `OK
<check>: <summary>`, `FAIL <check>: <finding>` (one per finding, exit 1) or `WARN <check>: <finding>` (exit
unaffected). A deployment that fails it is unsupported.

What it checks, in every environment: forced row level security and a policy on every tenant table; `erev_app`
without `SUPERUSER` or `BYPASSRLS`; every immutability trigger enabled and present on every IM-A table and
partition; the latest audit chain verification `PASS` for every workspace; AI off unless a workspace enabled it;
and no schema-`erev` function referencing a session setting outside the documented `app.*` list (05 REL-07).
Under `EREV_ENV=production` the 05 SAR-40 production checks follow (email backend, integration URLs, CORS,
session cookie, `DEFUSEDXML`, partition window, release stamp, key provider, key-version pin, recovery provider,
Anthropic key); their rules and responses are the RB-03 "Production checks" table.

When to run it: after every installation or upgrade (`make doctor` in the loop; the hosted steps of RB-02 and
OPR-11 (3)); after any database administration that touches roles, triggers or partitions; before the first
production workspace; and on demand during an incident (RB-08). Run `erev doctor --analyze <tables>` as the
schema owner after bulk loads (05 PERF-27) — it runs `ANALYZE` and no check.

Evidence: keep the complete output (all `OK`, `FAIL` and `WARN` lines and the exit code) with the release
record of the deployment; a `FAIL` line names the object (table, trigger, function, workspace, variable) to act
on, never a credential. The command writes one `PLATFORM_SCOPE_USED` security event when it reads the
workspace list and nothing else; it changes no data.

## Complementary user entity controls (CU-01 to CU-12)

The controls a customer operates so that eRev Cloud's application controls achieve their objectives (03 REQ-CTL-004; research 07 §6.4). Each control names the product features that support it; the customer's own procedure, frequency and evidence retention are the customer's to define.

### CU-01 Approve user provisioning and role assignments consistent with SoD policy

Features: the role matrix (`GET /api/v1/roles`), the preventive SoD block that refuses a conflicting role assignment at invitation or assignment time (REQ-PLT-010, CTL-034), the role assignment approval routed to an `access.approve` holder other than the requester (REQ-PLT-009), and the SoD exception register with compensating controls (`sod_exception`). Evidence: `audit_event` actions `tenant_membership.invite`, `role_assignment.*`, `sod_exception.*`.

### CU-02 Perform periodic user access reviews

Features: access review campaigns (`POST /api/v1/access-reviews`) that snapshot every membership with its roles and last sign-in, reviewer decisions with a required comment for revocations, and the revocation confirmation (REQ-CTL-006); the user listing (`GET /api/v1/users`) as the information produced by the entity. Evidence: `access_review_campaign` and `access_review_item` rows; audit actions `access_review.*`.

### CU-03 Remove access for terminated or transferred users timely

Features: `POST /api/v1/users/{membership_id}/suspend` and `/remove` (both end the member's sessions in the workspace and are audited with a reason); the access review snapshot's `last_login_at`; the personal-data erasure command for leavers whose identity must go (RB-14). SCIM deprovisioning is later (REQ-PLT-007). Evidence: audit actions `tenant_membership.suspend`, `tenant_membership.remove`.

### CU-04 Configure and maintain SSO and MFA policies in the identity provider

Features: OIDC identity providers configured by the platform operator (`erev idp create`, and afterwards `erev idp domains`, `erev idp disable` and `erev idp enable`; `identity_provider`), the sessions opened through a disabled provider ended by the operator's command (`erev idp end-sessions`; `user_session.end_reason` `REVOKED`), with roles never taken from the provider (REQ-PLT-006); MFA enforced by the `requires_mfa` flag of permissions (T-PLT-11, API-C-03) and the TOTP enrolment, lockout and reset commands (REQ-PLT-005). The identity provider's own MFA policy is the customer's. Evidence: `security_event` kinds `MFA_ENROLLED`, `MFA_RESET`, `PLATFORM_SCOPE_USED`.

### CU-05 Ensure completeness and accuracy of source data and resolve interface exceptions

Features: import control totals and the validation, diff and commit stages (`import_upload.control_totals`, REQ-IMP), the exception queue with owners and dispositions (`exception_item`), sync runs with source and loaded totals (`sync_run`), and the reconciliations of the close (T-CLS-06). Evidence: import manifests; `exception_item` resolutions; sync run totals.

### CU-06 Review and approve SSPs, accounting policies, configurations and significant judgments

Features: publish-immutable configuration versions that leave DRAFT only through approval (IM-P, DB-04): SSP book versions, POB templates, rule sets, account mappings and registry (policy) versions; contract, modification and estimate approvals with content hashes and impact previews (REQ-PLT-014, REQ-PLT-015); judgement records (T-CON-19). Evidence: `approval_request` and `approval_decision` rows; version `published_by` and `approval_request_id`.

### CU-07 Review and sign off reconciliations and rollforwards

Features: the close checklist and its sign-offs with content hashes (T-CLS-03, T-CLS-08), reconciliations and their items (T-CLS-06, T-CLS-07), period locks and lock snapshots (T-CLS-04, T-CLS-05), and evidence packs assembled per period (REQ-RPT-025). Evidence: `signoff` rows; evidence pack manifests with SHA-256 sums.

### CU-08 Confirm exported journal entries posted in the ERP and restrict direct GL entries

Features: journal runs and batches with deterministic external ids and idempotent export (ADP-10 to ADP-13, CTL-021), posting acknowledgements from the ERP (`posting_ack`), the dead-letter handling of failed export messages (RB-07), and the direct-GL-entry review the customer performs in its ERP over the subledger-controlled accounts. Evidence: `posting_ack` rows; journal export manifests.

### CU-09 Approve provider support sessions and review the support session log

Features: support grants requested by the operator and approved by a Tenant Admin, read-only, 72 hours maximum, ended on expiry (REQ-PLT-036, CTL-035); the support session log in the workspace's audit trail (every action under a grant carries `support_grant_id`) and the `PLATFORM_SCOPE_USED` security events. Evidence: `support_grant` rows and approvals; audit events filtered by `support_grant_id`.

### CU-10 Review release notes and evaluate effects on customer controls; test significant changes in a sandbox

Features: the release manifest with its control-impact tags (REQ-CTL-003; `engine_release.control_impact_tags`), the engine release stamped on every computation and run, the upgrade validation before a new engine release is enabled (RB-16, REL-06), and sandbox tenants restored from a snapshot for testing (REQ-PLT-024, DB-15). Evidence: `engine_release` rows; release validation records; sandbox tenant snapshots.

### CU-11 Designate period lock and reopen approvers and govern reopen requests

Features: the `period.lock` permission and its approval routing, period locks with lock snapshots (T-CLS-04, T-CLS-05), the period state transitions and their log (T-REF-06, T-REF-07), and the reopen request as an approval request. Evidence: `period_state_transition` rows; approval decisions of the `PERIOD_LOCK` subject.

### CU-12 Safeguard and rotate API keys and service account credentials

Features: API clients whose scopes are an access grant — a client is requested (`POST /api/v1/api-clients`), waits `PENDING_APPROVAL`, and is approved by another person who holds `access.approve` for its entities before its first secret is issued (REQ-PLT-033) — with a client secret shown once, by the command that issues it and not by the approval, an expiry (default 365 days), rotation and revocation (`POST /api/v1/api-clients/{id}/rotate-secret`, `/revoke`; T-PLT-15) by a holder of `api_client.manage` for every entity of the client, access tokens that expire after 60 minutes and are hashed at rest (T-PLT-16), scopes that exclude approvals (DB-12, CTL-037), and the API client inventory (`GET /api/v1/api-clients`). Adapter credentials are held as secret references and rotated by the customer (RB-15). Evidence: audit actions `api_client.create`, `api_client.activate` or `api_client.reject` (the decision), `api_client.rotate_secret`, `api_client.revoke`; the approval request of the grant and its decisions, named by the client's `approval_request_id`; `DENIED` audit events of a command on a client beyond the actor's entities and of a request beyond the requester's own; the inventory listing.

## IT general controls for self-hosted deployments

A self-hosting customer operates these controls around the application (03 §6.4; REQ-CTL-004). A hosted deployment's operator operates the same controls and evidences them to its tenants.

### Logical access to infrastructure and the database

Who holds `erev_owner`: the deployment pipeline identity only, used for migrations; no standing human write access to the database (TB-7, RB-11). `erev_app` runs the api, worker and command-line tools without `SUPERUSER` or `BYPASSRLS`; the backup role `erev_backup` is `BYPASSRLS` and read-only, and the restore-target admin exists only on the isolated restore database (OPR-15, RB-04, RB-11). Infrastructure access (cloud project, hosts, container registry) follows the customer's own identity and access management with MFA; support access to a workspace's data goes through support grants only (CU-09). Evidence: the role catalogue (`\du` or the provider's IAM listing), the pipeline identity configuration, `erev doctor` output (role guards), access review records for infrastructure accounts.

### Change management through the release manifest

Only released versions are deployed: the release manifest (REQ-CTL-003; `make release-manifest`) records the engine semantic version, build hash, migration head, the gate results with output hashes and the control-impact tags of the touched controls; every computation and run stamps its engine release (`engine_release`). No local code changes to the engine, the immutability triggers or the schema are made outside a release; a MINOR or MAJOR engine release is enabled only after the upgrade validation (RB-16, REL-06). Evidence: the release manifests of every deployed version, `engine_release` rows, the upgrade validation records, `erev doctor` output after each upgrade (RB-03).

### Backups and restore tests

Backups run as `erev_backup` to `EREV_BACKUP_URL` (NATIVE, self-hosted) or through the platform's automated backups and point-in-time recovery (MANAGED, hosted) (OPR-08, RB-04); the master keys are backed up separately (`make backup` copies `.env` with mode 0600, RB-05). Restores go to the isolated restore-target database and are verified under the application roles before any cutover, with the audit mirroring of OPR-11; a restore test is performed and recorded on the OPR-12 schedule with the recovery age (RB-06). Evidence: backup logs, the restore-test record fields of OPR-12, the `.env` backup custody record.

### Job monitoring

The worker's heartbeat, the job monitoring views and the stuck-job and dead-letter procedures of RB-07 (JOB-06, JOB-07): failed and dead-lettered jobs are reviewed and dispositioned, `JOURNAL_EXPORT` dead letters in particular before the ERP close; the daily audit-chain verification (SCH-01, SCH-02) and its notifications on failure (RB-08) are part of the monitoring. Evidence: the job listing (`GET /api/v1/jobs`), dead-letter dispositions, `audit_chain_verification` rows.

### Secrets and key management

Master keys (`EREV_ENCRYPTION_KEY`, `EREV_AUDIT_HMAC_MASTER_KEY`, `EREV_SECURITY_EVENT_HMAC_KEY`) live in Secret Manager hosted or in `.env` self-hosted, never in code, logs or the database (ARC-11, SAR-19, SAR-22); per-tenant and per-file keys derive from or are wrapped under them (KEY-02 to KEY-07). Rotation follows SAR-23 and RB-05 (a new key id; old ids stay derivable for verification and decryption); adapter and identity-provider credentials are secret references rotated by the customer (RB-15, CU-12). Evidence: the key id catalogue and rotation record, Secret Manager versions, the `make secrets-check` result of each release.

### Database logging

Hosted deployments enable pgAudit for DDL and role statements with literal masking (SAR-30) and keep the logs for 400 days (DPL-37). A self-hosting customer enables pgAudit or an equivalent database log of DDL and role changes on its PostgreSQL, so that any disabling of a trigger, change of a policy or grant is logged outside the application (the residual risk of THR-09). Evidence: the database log configuration and the retention setting; periodic review of DDL and role events against the release record.
