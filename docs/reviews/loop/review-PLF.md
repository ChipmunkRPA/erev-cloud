# PLF review: phase 03, items PLF-1 to PLF-30 and remediation items PLF-3a to PLF-3c

| Field | Value |
|---|---|
| Reviewed commit | `0eb193d` (PLF-30 backfill), worktree `~/dev/erev-rv/plf`. The loop ran the GATE-PLF gates at `da6b20a` and ticked GATE-PLF at `04759db` |
| Main HEAD at synthesis | `a04f0c8` (WEB-2). Since `0eb193d` the backend gained only `domain/reports/number_formats.py` and its unit test. No cited file changed, so every finding below is still current |
| Date | 2026-09-13 |
| Inputs | Setup baseline; five lenses (authn, authz-tenancy, controls, reliability, conformance-gates); two verifier passes per lens with findings (reproduction and authority); the lead's own reading of the code at `0eb193d` |
| Remediation | `~/dev/erev-rv/reports/plf/SUPERVISOR-ITEM.md`: SUP-PLF-1 to SUP-PLF-4 |

## Result

**Every GATE-PLF gate is green and every count the loop claimed reproduces exactly, but the phase carries four P1 findings. None of them is caught by a gate.**

| Id | P1 finding | Consequence |
|---|---|---|
| PR-A-01 | `POST /session/mfa` has no rate limit and no lockout | Anyone holding a password can brute-force TOTP. 150 wrong codes in one minute gave 150 × 422, then the right code gave 200 |
| PR-Z-01 | A Tenant Admin can reset the MFA of any user in any tenant by first inviting that user's email | The victim's global factor is disabled and every session ends, including the victim's sessions in their own tenant and those of a platform operator. The victim's tenant gets no audit event |
| PR-K-02 | The SoD check at approval takes no lock | Two concurrent approvals grant both halves of SoD-3. In 8 of 8 unpatched trials the member ended up holding both roles |
| PR-K-01 | Chain verification is not anchored to `audit_chain_head` or the last digest | Deleting the newest audit events gives a false PASS. If the head is also rewound, the deletion is never detected |

**Other counts.** There are 15 P2 and 6 P3 findings. Three lens findings are dropped (PR-A-05, PR-K-04 with PR-C-07, PR-R-10). Two findings were merged into others: PR-C-01 into PR-K-01, and PR-R-07 into setup S-1.

**Provenance of PR-Z-01 and PR-Z-02.** The authz-tenancy lens returned a placeholder ("test") with no findings. Its probe output (`authz-tenancy/live_probe.out`, `db_probe.out`) holds end-to-end evidence, and the lead confirmed the mechanism in the code. No verifier pass ran on these two findings.

**EKC remediation.** All 14 finding ids of PLF-3a to PLF-3c are implemented. Each named test exists and passes, and each fails again when its defect is reintroduced (table below).

**Placement.**
- Insert SUP-PLF-1 to SUP-PLF-4 after WEB-2 and ahead of WEB-3, the loop's next unticked item, as WEB-2a to WEB-2d.
- They must land before WEB-12 (MFA challenge screen), WEB-14 (password change), WEB-19 (users screens), SOP-4 and SOP-8.

## Baseline (setup reviewer, `setup/baseline.md`)

| Gate | Result at `0eb193d` on `erev_rv_*` and the review ports |
|---|---|
| `make setup` | exit 0; DB-14 lint 0 findings; 2 moderate npm advisories (already under "Supervisor verification needed") |
| `make ci` | exit 0, 225 s. Backend 753 passed, 0 failed, 0 skipped; Vitest 197 passed; build OK. `erev controls-report --tags-only`: 47 tagged tests covering CTL-014 and CTL-033 to CTL-040 |
| `make test-pg` | 114 passed, 0 failed, 0 skipped |
| `make properties` (unfiltered) | 4 passed |
| `make answer-keys` (unfiltered) | Fails closed as designed. 232 active keys: 227 engine keys fail naming END-9 and 5 platform keys fail naming PRP-1; 2 withdrawn; coverage 0 gaps |
| `make dev-up` (review ports exported), `readyz`, `make status`, `make dev-down` | 200; api 8192, web 5272, worker alive; stopped by PID; ports free |
| `make doctor` (`erev_rv_2`) | exit 0. The RLS check (34 tables), the app-role check and the trigger check (634 triggers) are substantive. The audit-chain and AI checks pass vacuously on an unseeded database |

After every run `git status --porcelain` was empty, and no process started by a reviewer is left running.

Setup's own findings:
- S-1 (P2): the review `.env` ports never reach make, `proc.sh` or Vite. Merged with PR-R-07 below.
- S-2 (P3) and S-4 (P3): listed with the P3 findings.
- S-3 (review environment): the review `.env` lacks `EREV_PUBLIC_ORIGIN`, so browser sign-in on 5272 is refused with 403 `API-C-02`. This is supervisor provisioning, not a loop defect.

## Confirmed findings

Verdict notation: repro and authority verifier, in that order. Code locations are at `0eb193d`, and every file path is under `backend/erev_api/` unless stated otherwise.

### P1

#### PR-A-01: `POST /session/mfa` is neither rate-limited nor locked out, so TOTP can be brute-forced (PLF-2, PLF-5)

- **Where:**
  - `api/v1/session.py:343-372` `session_verify_mfa` calls `mfa.verify` with no limiter.
  - `auth/mfa.py:406-461`: a wrong code writes `MFA_CHALLENGE_FAILED` and returns 422, with no counter and no lock.
  - `LoginRateLimiter` is wired only to login (`session.py:153-164`) and to operator provisioning (`operator_tenants.py:107`).
  - `mfa.py:371-403`: a recovery-code attempt runs up to 10 argon2id verifications, also without a limit.
- **Contract:**
  - 05 SAR-13 (`05:1152`, "login and MFA endpoints 10 requests per minute per (client IP, normalised email) and 50 per minute per client IP").
  - BUILD_SPEC PLF-2 scope (`:1512`, "login and MFA buckets of 05 SAR-13; BS1-D-22").
  - 03 REQ-SEC-004 (`03:670`); PRD NFR-43 (`02:1904`); THR-01, THR-03; CTL-033.
  - SOP-4 covers only the per-client and per-session limits, and no spec question defers this bucket.
- **Reproduction:**
  - `authn/probe_authn.py::test_probe_mfa_challenge_unthrottled`, run on `erev_rv_1`. After a password-only sign-in, 150 wrong codes within one FrozenClock minute gave `{"422": 150}`, no 429, and 150 `MFA_CHALLENGE_FAILED` events. The right code then returned 200.
  - The verifier's run: 120 wrong codes at 165 requests/s with `failed_login_count` 0; a wrong recovery code takes 315 ms against 6.5 ms for a TOTP code.
  - Control: the login bucket returned `[401 × 10, 429]`.
- **Impact:** with a ±1 step window, a 50% hit needs about 231,000 guesses, and nothing caps them. MFA stops protecting any account whose password is known.
- **Verdicts:** confirmed P1; confirmed P1.
- **Fix:** SUP-PLF-1. The SAR-13 buckets are applied to the MFA route, plus a consecutive-failure lock (D-80).

#### PR-Z-01: cross-tenant MFA reset through an invitation the victim never accepted (PLF-17; lead-verified)

- **Where:**
  - `domain/platform/users.py:303-313` `invite_user` looks up the global `app_user` by email. It refuses only when that user already holds a membership in the current tenant (RLS limits the query to the current tenant). Any known email therefore gets an `INVITED` membership.
  - `users.py:559-604` `reset_mfa` locks that membership but never checks its status. It then:
    - disables the user's global `user_mfa_factor` (`:577-581`);
    - ends every session of the user in every tenant through `end_user_sessions` (`:582`);
    - audits only in the acting tenant (`:596-604`).
- **Contract:**
  - PRD membership state machine (`02:1501`): `INVITED → ACTIVE` only by accepting the invitation.
  - SCREENS_B §9.10 (`SCREENS_B:5473`, `:5518`): Reset MFA is an action on an Active member row.
  - 05 THR-07 (tenant isolation: "cross-tenant read or write through ... crafted ids").
  - 04 T-PLT-02 `is_operator` (`04:786`): an operator acts in a tenant only under a support grant (REQ-PLT-036, THR-20).
  - THR-03 ("MFA reset is an audited admin command"); SAR-42 (IDOR tests expect 404 for another tenant's objects).
- **Reproduction** (`authz-tenancy/live_probe.py` over the ASGI app on `erev_rv_2`; output `live_probe.out`):
  - **P-2:** the Tenant Admin of workspace A posts `POST /users` with the email of the admin of workspace B and returns 201 `INVITED`.
  - **P-3:** `POST /users/{invited membership}/reset-mfa` returns 200. The victim's factor gets `disabled_at` and open sessions drop to 0. The victim's session in B then gets 401 on `GET /users`. B holds 0 `user_mfa_factor.reset` events and A holds 1.
  - **P-4:** the same sequence against an enrolled platform operator returns 201, then 200: the factor is disabled and sessions drop to 0.
  - **Controls:** cross-tenant ids return 404 (P-1), and a forged bearer tenant prefix returns 401 (P-7).
- **Impact:**
  - Any Tenant Admin with a fresh step-up can strip MFA from, and log out, any user of any tenant, including a platform operator.
  - After the reset the victim must enrol again at the next sign-in (SCREENS_B:5518). An attacker who also holds the password can therefore enrol their own factor and take over the account.
- **Verdicts:** no verifier pass (lens return was a placeholder). The lead read `users.py:287-604` and `sessions.py:820-832` at `0eb193d`, and the probe output matches the code path. Lead ruling: P1 (tenant isolation break and circumvention of the MFA control).
- **Fix:** SUP-PLF-1 (D-80). Reset MFA needs an `ACTIVE` or `SUSPENDED` membership, operator identities cannot be invited or reset from a tenant, and the reset is audited in every ACTIVE membership (PR-C-04).

#### PR-K-02: the SoD re-check at approval is unserialised, so concurrent approvals grant a conflicting pair (PLF-6, PLF-17, PLF-18)

- **Where:**
  - `approvals/subjects.py:146-172` `_apply_role_assignment` checks at `:155` and inserts at `:157`, without locking `tenant_membership`.
  - `auth/sod.py:103-165` only reads.
  - `approvals/engine.py:173-184` `decide` locks only its own request.
  - `domain/platform/roles.py:262-378` ignores other pending requests.
  - `subjects.py:245-264` `_apply_role_change` locks the role but not the holders' memberships.
- **Contract:**
  - 03 REQ-PLT-010 (`03:175`, conflicting assignments "are blocked").
  - PRD SM-13 (`02:1502`, "SoD check at request and at approval").
  - dev-guide DG-KRN-PERM-02 (`dev-guide:751`) and DG-CMD-02 (commands read the rows they depend on `FOR UPDATE`).
  - CTL-034, a preventive automated control.
- **Reproduction** (`controls/probes/defects/test_probe_defects.py::test_probe_sod_conflict_race_at_approval`, log `controls/logs/defects.log`):
  - Setup: member M has two PENDING requests, for `revenue_accountant` and `revenue_reviewer`, and two approvers decide concurrently.
  - Output: `results={'revenue_accountant':'APPROVED','revenue_reviewer':'APPROVED'}`, `held=['revenue_accountant','revenue_reviewer']`, `conflicts=[('SoD-3', None)]`.
  - Verifier, unpatched: 8 of 8 trials granted both roles, with READ COMMITTED isolation.
  - Sequential control: the second approval gets 409 `sod-conflict`.
- **Verdicts:** confirmed P1; confirmed P1.
- **Fix:** SUP-PLF-1. The membership row is locked before the check, in both apply functions. PR-C-03 adds the missing sequential test.

#### PR-K-01 (merges PR-C-01): chain verification is not anchored to the head or the last digest, so tail truncation verifies as PASS (PLF-3, PLF-23)

- **Where:**
  - `audit/verify.py:138-199` `verify_tenant_chain` walks the existing rows and returns PASS at `expected - 1`.
  - `record_tenant_verification` (`:223-308`) never reads `audit_chain_head` or an earlier verification.
  - `audit_chain_head` is IM-X, so `erev_app` holds UPDATE on it and no guard protects it (`db/migration_ops.py:64`; `controls/logs/catalogue.log`).
  - Test gap: the CTL-038 and CTL-039 tests tamper only with `after` or `detail`.
- **Contract:**
  - dev-guide DG-KRN-AUD-07 (`dev-guide:800`, "checks continuity").
  - 04 T-PLT-22 (`04:1291`, "per-tenant chain pointer") and DB-09 (`04:4810`).
  - 05 SAR-31 (`05:1195`, digest `{last_chain_seq, last_hmac, ...}`) and OPR-11 (3) (`05:1256`, compare the head with the latest digest).
  - PLF-23 `test_req_plt_020_pass_writes_digest` (`BUILD_SPEC:2353`, `digest_last_hmac` equal to the head).
  - 05 THR-09 (`05:1047`), whose mitigation is "HMAC chain; daily verification and digests"; REQ-PLT-020; CTL-039.
- **Reproduction:**
  - `controls/logs/defects.log`: an owner with a data-fix ticket deletes `chain_seq` 4-5. Output: `{'result':'PASS','to_chain_seq':3,'events_checked':3}` while `head_last_chain_seq=5`. With the head also rewound to 3, the first and second verifications both give PASS.
  - Conformance run (`conformance-gates/logs/scratch-chain-tail.log`): 12 events, 11-12 deleted, `after: result=PASS to=10`.
  - Repro verifier: in the rewind case, history is `[PASS 14, PASS 13, PASS 15]`, and the event now at 14 carries a different HMAC from the earlier digest.
- **Narrowed claim:**
  - Plain truncation with the head untouched gives one false PASS with a digest. The next run fails, because the verification's own AUD-FACT event makes the sequence non-contiguous.
  - Truncation plus a head rewind, which `erev_app` can do without a ticket, is never detected.
- **Verdicts:**
  - Controls lens: confirmed P1; confirmed P2 (authority).
  - Conformance lens: confirmed P2; refuted (authority). The authority verifier held that no clause requires the anchor, and that the owner is a THR-09 residual actor.
- **Adjudication:** kept, **P1**.
  - The tamper actor, `erev_owner` with a data-fix ticket, is exactly the DG-TST-22 model that CTL-038 and CTL-039 are tested against. The THR-09 residual concerns disabling triggers, not an undetected sanctioned edit.
  - The contract intent is explicit in T-PLT-22, SAR-31, OPR-11 and the PLF-23 test.
  - The rubric names audit tamper as P1.
  - The authority verifier's caveat stands: `audit_chain_verification` rows can also be deleted by the owner, so only the write-once digest bucket fully resists that actor.
- **Fix:** SUP-PLF-1 (D-80).
  - Verification fails when the chain ends before the head, or when the latest earlier PASS digest no longer matches the chain.
  - A DB-09 guard makes the head advance only through `tg_audit_event__chain`.

### P2

#### PR-A-02: API client and webhook secrets are kept in plaintext in `idempotency_record` for 7 days and returned again on replay (PLF-24, PLF-25)

- **Where:**
  - `api/v1/api_clients.py:112-140` (create) and `:162-183` (rotate-secret) return `client_secret` through `run_command`.
  - `api/deps.py:339-362` stores the body, through `idempotency/store.py:257-291`, and `store.py:217-229` replays it.
  - `api/v1/webhooks.py:141-149` does the same with `signing_secret`.
- **Contract:**
  - 03 REQ-SEC-003 (`03:669`, API client secrets "encrypted or hashed at rest").
  - 05 SAR-18 (`05:1110`, no secret values in the database); 04 T-PLT-15 (`secret_hash`, "shown once"); THR-04.
- **Reproduction:** `authn/probe_authn.py::test_probe_api_client_secret_kept_in_idempotency_record` gives `stored_body_contains_client_secret true`, `record_lifetime '7 days'`, and a replay 201 with the same secret. The verifier also found the new secret in the rotate-secret record.
- **Verdicts:** confirmed P2; confirmed P2. SPEC-Q-190 (b) and SPEC-Q-189 (b) are wrong (rulings below).
- **Fix:** SUP-PLF-2 (D-80: the stored and replayed body carries the secret member as null).

#### PR-A-04 (absorbs the OIDC part of PR-R-08): OIDC provider requests skip the SAR-15 guard, and a loopback http issuer is accepted in any environment (PLF-27)

- **Where:**
  - `adapters/idp/oidc_http.py:21-47` uses plain httpx without `check_destination`.
  - `auth/oidc.py:186-199` `discover` accepts any `token_endpoint` or `jwks_uri`.
  - `oidc.py:364-376` requests both URLs and posts the client-secret form.
  - `oidc.py:397-401` `_issuer_valid` accepts `http://127.0.0.1…` without looking at the environment.
- **Contract:** 05 SAR-15 (`05:1179`, which names "OIDC issuers", with loopback and plain http only in dev, test and e2e); THR-15; NTR-13.
- **Reproduction:**
  - `authn/probe_oidc_ssrf.py`: the adapter requested `http://169.254.169.254/latest/meta-data/` and `http://10.0.0.5/internal-admin`.
  - The verifier, end to end through start, authorize and callback, saw a POST to `http://10.0.0.5/internal-admin` with the `code_verifier` form, and a GET of the metadata URL before the 401.
- **Verdicts:** confirmed P2; confirmed P2. SPEC-Q-192 (f) ignores the SAR-15 environment gating.
- **Fix:** SUP-PLF-2.

#### PR-Z-02: global identity data is readable and writable through an unaccepted invitation (PLF-17; lead-verified)

- **Where:**
  - `users.py:640-656` `member_select` and `:903-904` return the global `display_name`, `last_login_at` and `mfa_enrolled` for any membership, including an `INVITED` one of a pre-existing user.
  - `users.py:420-470` `update_user` renames the global `app_user.display_name` of any invited user who has never signed in. No audit event reaches that user's other tenants.
- **Contract:**
  - 05 THR-07 (cross-tenant read or write).
  - PRV-01 (`05:1202`): `app_user.display_name` is C3 personal data.
  - 04 T-PLT-02 (`04:768`): a global identity, and "AUD-CMD for other changes, written to each tenant in which the user is ACTIVE".
  - SPEC-Q-182 (c) ("a known email reuses the `app_user` and keeps its name") produces the disclosure.
- **Reproduction** (`authz-tenancy/live_probe.out`):
  - **P-2:** A's invitation of B's admin returns `display_name='b admin real name' last_login_at='2026-09-13T16:46:41Z' mfa_enrolled=True`.
  - **P-5:** A invites the never-signed-in admin of workspace C, then `PATCH /users/{id} {display_name: "Renamed from tenant A"}` returns 200. The global name changes from `c-admin@…` to `Renamed from tenant A`, and C gets 0 audit events.
- **Verdicts:** no verifier pass. The lead read the code; the finding is P2 because the disclosure needs the email, and the rename is limited to users who have never signed in.
- **Fix:** SUP-PLF-2 (D-80).

#### PR-C-04: an MFA reset is audited only in the acting workspace (PLF-17)

- **Where:** `users.py:596-604` writes one `uow.audit` in `principal.tenant_id`. By contrast, `auth/mfa.py:264-293` `_audit_enrolment` writes to every ACTIVE membership's tenant.
- **Contract:** 04 T-PLT-04 (`04:817`, "MFA_ENROLLED, MFA_RESET go to `security_event` and to the tenant audit log of each ACTIVE membership"); REQ-PLT-019.
- **Reproduction:** `verify-conformance-gates-repro/logs/PR-C-04-mfa-reset.log`. Lena is ACTIVE in A and B; after a reset from A, the reset audit events are A=1 and B=0. `live_probe.out` P-3 shows the same.
- **Verdicts:** confirmed P2; confirmed P2. SPEC-Q-182 (d) is wrong.
- **Fix:** SUP-PLF-1 (same function as PR-Z-01).

#### PR-A-03: password change does not rotate the current session token (PLF-15)

- **Where:**
  - `auth/credentials.py:86-136`: `end_user_sessions(..., keep_session_id=auth.session.id)` at `:121-127`, and no `sessions.reissue`.
  - `api/v1/me.py:127-147` returns 204 without `Set-Cookie`.
  - The loop's `tests/api/test_me_password.py:82-84` asserts that the old token still works.
- **Contract:**
  - 05 SAR-09 (`05:1132`, "The token rotates on login, MFA verification, password change and tenant selection; the old session row ends with REVOKED").
  - SAR-42 (session fixation); SOP-8 `test_sar_42_session_token_rotates` (`BUILD_SPEC:10435`).
  - 04 §16.12 "keeps the current session" still holds under rotation, as SPEC-Q-126 applies to tenant selection.
- **Reproduction:** `probe_authn.py::test_probe_password_change_keeps_token` and the verifier: 204 without a cookie, the old cookie still authenticates, and `end_reason` is null. Control: `POST /session/tenant` rotates.
- **Verdicts:** confirmed P2; confirmed P2.
- **Fix:** SUP-PLF-2 (D-80 clarifies the PLF-15 test wording).

#### PR-K-03: DB-04 change control is bypassed by inserting a configuration version as PUBLISHED (PLF-6, PLF-12, PLF-13)

- **Where:** `db/migration_ops.py:970-1047` `CONFIG_VERSION_BODY`.
  - On INSERT it checks only `content_sha256` (`:988`) and range overlap (`:1028`).
  - The APPROVED-request check runs only on UPDATE (`:993`, `:1014-1026`).
  - `erev_app` holds INSERT on `sod_rule`, `registry_version` and `rule_set_version`.
- **Contract:**
  - 04 DB-04 (`04:4805`) and §1.5 IM-P (`04:243`, lifecycle only "along E-12").
  - REQ-PLT-009, REQ-PLT-010, REQ-PLT-016; CTL-011, CTL-031.
- **Reproduction** (`controls/logs/db04.log`): as `erev_app` in the tenant context, supersede SoD-3 v1 and insert v2 PUBLISHED with other permissions and `approval_request_id` NULL. Output: conflicts `['SoD-3']` before and `[]` after, with 0 ROLE_CHANGE requests. The verifier also inserted APPROVED directly.
- **Verdicts:** confirmed P2; confirmed P2. The call in SPEC-Q-151 is wrong in effect; SPEC-Q-175 is the precedent for restricting to the provisioning scope.
- **Fix:** SUP-PLF-4.

#### PR-C-05: the SoD conflict report as of a past date applies today's rules (PLF-6, PLF-19)

- **Where:**
  - `auth/sod.py:48-71` `_published_rules` filters on `status == PUBLISHED` only.
  - Under SPEC-Q-184 (a) published versions keep `effective_from` NULL, so the newest content counts at every past date.
  - `tests/domain/platform/test_sod.py:240-247` pins this.
  - `conflict_report` also filters `revoked_at IS NULL`, so a past-date report omits assignments revoked later.
- **Contract:**
  - 03 REQ-PLT-010 (`03:175`, "SoD conflict report as of any date"); CTL-034 evidence; SCREENS_B RPT-25.
  - dev-guide DG-KRN-PERM-03 (`:752`) forbids hard-coded content, not former published versions.
  - `registry/resolve.py:7,61` already counts SUPERSEDED versions for earlier instants.
- **Reproduction** (`verify-conformance-gates-repro/logs/PR-C-04-05-scratch.log`): `conflict_report(as_of=2026-01-02)` returns `['SoD-3']` while v1 is published and `[]` once v2 supersedes v1.
- **Verdicts:** confirmed P2; confirmed P2. SPEC-Q-150 is wrong.
- **Fix:** SUP-PLF-4.

#### PR-C-03: the approval-time SoD re-check has no test that can fail (PLF-17, PLF-18)

- **Where:** `subjects.py:146-155`. Every `sod-conflict` assertion runs at request time or on a role change (`test_users_api.py:305`, `test_roles_api.py:283`, `:458`, `test_sod.py:119`).
- **Contract:** PRD SM-13; BUILD_SPEC PLF-17 scope (`:2194`, "SoD check at request and at approval"); dev-guide DG-TST-06 (`:1936`); BUILD_SPEC SZ-03.
- **Reproduction:**
  - Probe G3e swallows the Problem at approval, and 45 existing tests still pass (`conformance-gates/logs/G3e-sod-recheck-at-approval-never-refuses.log`).
  - Scratch API test: on clean code the second approval returns 409 and Lena holds 1 assignment. Under G3e it returns 200 and she holds 2.
- **Verdicts:** confirmed P2; confirmed P2. This is a test gap next to PR-K-02, not a duplicate of it.
- **Fix:** SUP-PLF-1.

#### PR-R-04: a failure before QUEUED → RUNNING strands the job and permanently stops SCH-01, SCH-03, SCH-07 and SCH-12 for the tenant (PLF-9, PLF-22)

- **Where:**
  - `jobs/registry.py:469-529` `run_job` can raise before the RUNNING move, and `worker.py:90-93` `erev.run_job` has no retry.
  - `jobs/sweeper.py:48-70` requeues only rows with a null `procrastinate_job_id`, and `:79-111` only RUNNING rows.
  - `registry.py:359-383` `_defer_unless_pending` treats any QUEUED row as pending.
- **Contract:** 05 JOB-06 part one (`05:907`) and SCH-04 (`05:943`, "Retry stalled Procrastinate jobs"); ADP-32 (`05:873`); DG-KRN-JOB-06 (`dev-guide:1152`).
- **Reproduction:** probe C and verifier probe V6. Two days after the failure the job is still QUEUED, the sweeper reports (requeued, stalled) = (0, 0), and SCH-03 and SCH-12 defer 0 despite due work. The verifier added that SCH-01 (daily `AUDIT_CHAIN_VERIFY`, CTL-039) is blocked as well, while `erev doctor` still shows the last PASS.
- **Verdicts:** confirmed P2 ("P2 or higher"); confirmed P2. SPEC-Q-187 (b) is wrong.
- **Fix:** SUP-PLF-3.

#### PR-R-03: outbox, webhook and chain-verify handlers never heartbeat, so the stall sweeper fails healthy runs and starts concurrent executions (PLF-14, PLF-22, PLF-23, PLF-24)

- **Where:**
  - The only `heartbeat()` caller is `domain/platform/retention.py:48`.
  - These handlers never heartbeat: `events/outbox.py:379-395`, `events/webhooks.py:381-393` and `domain/platform/audit_jobs.py:34`.
  - `jobs/sweeper.py:79-111` settles any RUNNING row silent for 10 minutes.
- **Contract:** dev-guide DG-KRN-JOB-04 (`:1150`, "heartbeat at least every 30 seconds"); 05 JOB-02, JOB-06.
- **Reproduction** (verifier probes V3 to V5):
  - A user's OUTBOX_RELAY is FAILED with "no heartbeat for 10 minutes" and a `JOB_FAILED` notification, while its messages end DISPATCHED.
  - A WEBHOOK_DELIVERY attempt 2 runs concurrently with attempt 1, posting `[1, 1, 2]`.
  - Attempt 1's completion marks attempt 2's row SUCCEEDED.
- **Verdicts:** confirmed P2; confirmed P2.
- **Fix:** SUP-PLF-3.

#### PR-R-01: the webhook batch lease expires mid-batch, giving duplicate POSTs and a failed delivery job (PLF-24)

- **Where:**
  - `events/webhooks.py:58` sets a 120 s lease for a batch of up to 100 serial POSTs, with a 10 s timeout each (`:220-272`).
  - The lease is never re-checked before a POST.
  - `_record` (`:275-287`) raises `invalid-transition` after another deliverer has recorded.
- **Contract:** 04 T-PLT-36 and 05 NTR-12 (`05:973`, one attempt per schedule step); DG-KRN-JOB-04 (idempotent handlers). SPEC-Q-189 (c) "never post one attempt twice" is false once a batch outlives 120 s.
- **Reproduction:** probe A gave POSTs per envelope `[1, 2, 2]` with two `invalid-transition` failures. Verifier probe V1 gave `[1, 1, 2]`.
- **Verdicts:** confirmed P2; confirmed P2.
- **Fix:** SUP-PLF-3.

#### PR-R-02: the 15-minute outbox re-claim takes a live relay's in-flight messages, so emails are sent twice (PLF-14)

- **Where:**
  - `events/outbox.py:79` and `:185-196` re-claim DISPATCHING rows 15 minutes old.
  - `:207-255` stamps `updated_at` once per batch of up to 100.
  - `:258-304` dispatches serially and records against `expected_status=DISPATCHING`.
- **Contract:** 05 ADP-32 (re-claim exists for lost tasks and crashed workers); DG-KRN-EVT-05 (`dev-guide:1097`).
- **Reproduction:** probe B gave sends per message `[1, 2, 2]`. Verifier probe V2 gave `[1, 1, 2]`, and relay 1 ended FAILED `invalid-transition`.
- **Verdicts:** confirmed P2; confirmed P2.
- **Fix:** SUP-PLF-3.

#### PR-R-05: the UPL-04 ZIP limits trust central-directory sizes, so a 199 KiB xlsx is accepted after allocating 200 MiB or more (PLF-8)

- **Where:** `files/policy.py:170-195` checks the declared `file_size` and `compress_size`, and `:209` `archive.read` inflates the whole stream.
- **Contract:** 05 UPL-04 (`05:1161`); THR-12 (`05:1050`); SAR-42 (zip bomb fixture); REQ-SEC-012.
- **Reproduction:**
  - `reliability/probes/zip_declared_size_bomb.py`: accepted as xlsx, with RSS growth of 300 MiB for a 299 KiB upload.
  - The verifier's independent builder: accepted, RSS +401 MiB for 199 KiB.
- **Verdicts:** confirmed P2; confirmed P2.
- **Fix:** SUP-PLF-4.

#### PR-R-06: a chunked `POST /api/v1/files` is buffered in memory up to 500 MiB before routing or authentication (PLF-8)

- **Where:** `api/middleware.py:156-182` `_receive_within_limit` appends every message until the body ends or exceeds 500 MiB + 64 KiB (`:44`). The middleware is outermost (`main.py:112`).
- **Contract:** 04 API-C-17 (`04:4887`, "rejects a request body above the route limit before reading it"); 05 UPL-01; THR-18.
- **Reproduction:** verifier, through `create_app()` over `httpx.ASGITransport`: 401 `unauthenticated` only after 192 MiB of 192 MiB was consumed, with RSS +202 MiB.
- **Verdicts:** confirmed P2; confirmed with a P3 suggestion, because nginx (DPL-12) and the hosted load balancer cap bodies.
- **Adjudication:** P2.
  - API-C-17 binds the api itself.
  - The DPL-12 nginx is not built at this commit.
  - LMG will stream 500 MiB legacy databases through this path.
- **Fix:** SUP-PLF-4.

#### PR-R-07 (setup S-1): `make dev-up` in a review worktree binds 8190 and 5270, because make, `proc.sh` and Vite never read the `.env` port override (PLF-30)

- **Where:**
  - `Makefile:46,48` resolve the ports from the environment only.
  - `scripts/proc.sh:37-42` `port_of` and `frontend/vite.config.ts:66` do the same.
  - `config.py:85-86` does read `.env`, so the mock OIDC issuer advertises 8192 while uvicorn binds 8190 (`adapters/mocks/oidc.py:63`).
- **Contract:** dev-guide §2.3 (`dev-guide:357-359`, `.env` carries the override in review worktrees, D-70); D-78 port row; DG-MK-dev-up (`:487`); XR-17.
- **Reproduction:** with no `EREV_*` variable exported, `make -n dev-up` prints `proc.sh start api 8190` and `proc.sh start web 5270`; exported, it prints 8192 and 5272. `make dev-up` itself was not run that way.
- **Verdicts:** setup P2; repro verifier confirmed with a P3 suggestion; authority verifier confirmed P2. **Adjudication: P2.**
- **Fix:** SUP-PLF-4.

### P3

| Id | Finding | Evidence and contract | Verdicts | Fix |
|---|---|---|---|---|
| PR-C-02 | No test pins the columns the audit HMAC covers | `audit/chain.py:35-41` is correct today. Probe G2b drops actor, action, object and outcome from `canonical_event`, and 26 tests stay green (`verify-conformance-gates-repro/logs/G2b-broad.log`). DG-KRN-AUD-03; CTL-038 | Confirmed P2; confirmed, downgraded to P3. **Adjudication: P3**, because the code conforms and only a test is missing | SUP-PLF-1 |
| PR-R-08 | SAR-15 guard gaps: NAT64, 6to4, IPv4-compatible, site-local, multicast and reserved ranges are accepted, and SMTP is unguarded | `adapters/http/guard.py:27-38,79-84` uses an enumerated deny list; `adapters/email/smtp.py:52`. Under production the guard allows `64:ff9b::7f00:1`, `2002:7f00:1::1` and `fec0::5`. 05 SAR-15 names SMTP hosts | Confirmed P3; confirmed P3 | SUP-PLF-2 (OIDC part merged into PR-A-04) |
| PR-C-06 | `common-passwords.txt` is generator output, so `111111111111`, `123123123123` and `1q2w3e4r5t6y` pass | REQ-PLT-004 (`03:169`, "the 10,000 most common passwords"); SAR-06. SPEC-Q-128 records where the file came from | Confirmed P3; confirmed P3 | Not carried. It needs a frequency-ranked corpus with a recorded licence, supplied by the supervisor (the loop has no network) |
| PR-R-09 | Sealing and downloads hold whole files in memory | `files/store.py:199-203`, `:279-284`; `domain/platform/attachments.py:388-390`; `api/v1/files.py:157`. DG-KRN-FILE-03 "Downloads stream" | Confirmed P3; confirmed P3 | Not carried. A streaming AEAD format change is needed before LMG (500 MiB legacy databases) |
| S-2 | A `WEB_PORT` given to make never reaches Vite | `Makefile:50-51`; DG-RUN-03, DG-RUN-21 (`dev-guide:426`, `:453`) | Setup (dry run) | SUP-PLF-4 |
| S-4 | `MoneyType`, `ExactType` and `FxRateType` disable statement caching | `db/types.py:18-20,45,53,61`; 252 `SAWarning` in `make ci`; DG-KRN-MONEY-05 | Setup (reproduced without a database) | SUP-PLF-4 |

## Dropped findings

| Id | Claim | Verdicts | Reason for dropping |
|---|---|---|---|
| PR-A-05 | The timing of a password-reset response reveals whether an account exists | Confirmed P3; refuted | Adjudicated: dropped.<br>- 04 T-PLT-42 rule 1 (202 with an empty body) is met.<br>- The SCREENS_B:6629 purpose line concerns copy.<br>- No SAR, THR or REQ requires constant-time reset; only login has SAR-06.<br>- The lockout by design already reveals account existence (423 for a known account).<br>- T-PLT-42 rule 2 limits probing, and each probe emails the victim.<br>This is a hardening note only |
| PR-K-04 and PR-C-07 | `erev controls-report --tags-only` cannot fail GATE-PLF criterion (6) | K-04 refuted twice; C-07 confirmed P3 and refuted | Adjudicated: dropped.<br>- DG-MK-controls-report (`dev-guide:530`) defines `--tags-only` as id validation.<br>- PHASES BS-D-18 defers completeness to GATE-SOP, where the full report exits 1 on a missing control.<br>- The FND acceptance requires exit 0 with no tagged test.<br>- Criterion (6) holds in fact: all 9 PLF controls are tagged.<br>Residual: criterion (6) says the command "lists" tests, but it prints a count |
| PR-R-10 | OpenAPI declares no `Idempotency-Key`, `If-Match`, `ETag` or total-count headers | Confirmed P3; refuted | Adjudicated: dropped. REQ-PLT-032 (`03:197`) and API-C-01 require only a generated, committed and non-stale document. DG-FE-05 has the client set both headers, and WEB-1 does so (`frontend/src/lib/api/commands.ts:97-100`) |
| authz P-6 | `security_event` rows of tenant B are visible in tenant A's context | Lead | By design: T-PLT-06 is RLS-NONE-U (SPEC-Q-114), and the app reads it only through `identity_session` |
| authz DB probe | `CREATE TEMP TABLE` succeeds as `erev_app` | Lead | Temporary objects are session-local. DG-ENV-14 and DG-ARC-05 forbid database, role and extension administration, not temporary tables. This is an observation only |

**Watch items, not findings:**
- `/session/invitations/lookup` is unauthenticated and unlimited, and writes one security event per call (SPEC-Q-180 a).
- A wrong current password on `/me/password` neither counts towards the lockout nor is rate-limited (SPEC-Q-180 f).
- The raw invitation token sits in the outbox payload (PLF-14 mandates this).
- The sweep tasks run on queue `outbox` rather than `maintenance` (SPEC-Q-179).

## EKC remediation verification (PLF-3a to PLF-3c)

Method: conformance-gates lens. For each id, the probe injected the original defect into a private `git archive` copy of `0eb193d` and ran the named tests, then restored the bytes and checked SHA-256. Results are in `conformance-gates/results.jsonl` and `logs/E01…E14c`. Every probe exited 1, which means the tests went red. The same lens confirmed that every named test exists and passes on the clean tree.

| Item | Finding id | Named test that turns red when the defect is reintroduced | Result |
|---|---|---|---|
| PLF-3a | ER-N-01 | `test_dates.py::test_s08_r08_first_postable_period_includes_closing`, `test_period_lookup` (E01) | Verified |
| PLF-3a | ER-N-02 | `test_prop_p04_schedule_bounds.py::test_p04_exemption_rejects_unbound_values` (E04) | Verified |
| PLF-3a | ER-C-03 | `test_progress.py::test_alg_11_mid_month_after_term_end` (E02) | Verified |
| PLF-3a | ER-S-03 | `test_engine_purity.py::test_dg_arc_02_builtins_and_owner_free_clock_reads` and 3 more (E05a, E05b) | Verified |
| PLF-3a | ER-S-06 | `test_guards.py::test_no_floats_detail_independent_of_hash_seed` (E03) | Verified |
| PLF-3b | ER-C-01 | `test_assert_checkpoints.py::test_implicit_assertions` (E06) | Verified |
| PLF-3b | ER-C-02 | `test_runner_engine.py::test_expect_problem_leaves_state_unchanged` (E07) | Verified |
| PLF-3b | ER-G-01 | Both `dg_ak_13` tests (E08a, E08b). End to end, `make answer-keys ID=<withdrawn id>` prints `FAIL … no active answer key` | Verified |
| PLF-3c | ER-G-03 | `test_makefile_targets.py::test_g5_skipped_property_test_fails_properties` (E09a, E09b). End to end, `make properties` with a runtime skip prints `FAIL properties: 1 skipped test` | Verified |
| PLF-3c | ER-G-04 | `test_makefile_targets.py::test_dg_mk_ci_refuses_command_line_overrides` (E10). End to end, `make ci PYTEST_PATHS=…` prints `FAIL ci … OVERRIDES` | Verified |
| PLF-3c | ER-G-05 (a) | `test_controls_report.py::test_dg_tst_07_root_hook_calls_markers_check` (E11) | Verified |
| PLF-3c | ER-G-05 (b) | `test_coverage.py::test_withdrawn_key_does_not_cover` (E12) | Verified |
| PLF-3c | ER-C-05 | `test_assert_checkpoints.py::test_books_and_contract_version_required` (E13a, E13b) | Verified |
| PLF-3c | ER-G-02 | `test_assert_checkpoints.py::test_optional_blocks_compared` (E14a quantity, E14b `proposed_treatments`, E14c `formula_id`) | Verified |

No verifier disputed this section.

## Spec-question rulings

These cover only the calls that reviewers showed to be wrong.

| Spec question | Loop's call | Ruling |
|---|---|---|
| SPEC-Q-190 (b), SPEC-Q-189 (b) | The idempotency store keeps the one-time 201 body, secret included, for replay | **Overruled** by REQ-SEC-003, SAR-18 and T-PLT-15 ("shown once"). The stored and replayed body carries the secret member as null (D-80) |
| SPEC-Q-192 (f) | The issuer URL form is checked at creation only; loopback http is always allowed | **Overruled** by SAR-15. Every provider URL passes `check_destination` at request time, and loopback or http issuers are refused under `production` (D-80) |
| SPEC-Q-182 (c) | A known email reuses the `app_user`, keeps its name, and API-S-User shows its global state | **Partly overruled** by THR-07 and PRV-01. Before acceptance, an invitation of a pre-existing user exposes no global identity data, and only an invitation that created the user may rename it (D-80) |
| SPEC-Q-182 (d) | The MFA reset is audited in the acting workspace only | **Overruled** by 04 T-PLT-04: the reset is written to each ACTIVE membership's audit log |
| SPEC-Q-151 | A non-DRAFT INSERT with `content_sha256` is allowed in any session | **Overruled** by DB-04 and IM-P ("only along E-12"). A non-DRAFT INSERT is allowed only under `app.platform_scope = 'provisioning'`, as SPEC-Q-175 already does for child rows (D-80) |
| SPEC-Q-150 (with SPEC-Q-184 a) | Only PUBLISHED rows count, at any date | **Overruled** by REQ-PLT-010 "as of any date". A SUPERSEDED version counts for instants in `[published_at, effective_to)`, and the report counts assignments in force at `as_of` (D-80) |
| SPEC-Q-187 (b) | The sweeper neither retries nor finishes a dead worker's Procrastinate task | **Overruled** by 05 JOB-06 part one and SCH-04. Failed, cancelled, aborted and stalled tasks of QUEUED jobs are re-dispatched (D-80) |
| SPEC-Q-189 (c) | A 120 s claim lease means no attempt is posted twice | **Corrected**: this holds only if the claim covers one delivery at a time. Deliveries and outbox messages are claimed one at a time immediately before dispatch (D-80) |
| SPEC-Q-128 | `common-passwords.txt` is the user's generator output | **Weak, not overruled.** The supervisor supplies a frequency-ranked list with a recorded licence before REL; this goes on the supervisor verification register |

## Proposed D-80 "PLF review rulings"

Record these under a new section 11 of `docs/01-DECISIONS.md`, "Rulings after the phase PLF review (2026-09-13)". Where a ruling differs from the text of the dev-guide, 04 or 05, the ruling governs, as under D-78 and D-79.

| Topic | Ruling | Departs from |
|---|---|---|
| MFA challenge limits (PR-A-01) | 1. `POST /session/mfa` is admitted through the SAR-13 login buckets, keyed by client IP and the session user's normalised email. The admission runs before verification. A refused attempt returns 429 `rate-limited` with `Retry-After` and writes no `MFA_CHALLENGE_FAILED`.<br>2. A wrong recovery code counts as one challenge.<br>3. Five `MFA_CHALLENGE_FAILED` events for a user after the later of the factor's last successful verification (`user_mfa_factor.updated_at`) and `app_user.locked_until` lock the account for 15 minutes: `locked_until` is set and `ACCOUNT_LOCKED` is written, and the fifth failure returns 423 `account-locked`.<br>4. While the account is locked, the route returns 423 without verifying anything.<br>5. A password sign-in does not restart the count | 05 SAR-06 (lockout counted password failures only); NFR-43 is read as covering MFA |
| MFA reset and invitations of existing identities (PR-Z-01, PR-Z-02, PR-C-04) | 1. `POST /users/{id}/reset-mfa` needs membership `ACTIVE` or `SUSPENDED`; otherwise it returns 409 `invalid-transition`.<br>2. A target whose `app_user.is_operator` is true returns 404 `not-found`.<br>3. `POST /users` refuses an operator email with 422 `validation-failed` on `email`, rule `T-PLT-02`, copy "This email cannot be invited to a workspace."<br>4. The reset writes `user_mfa_factor.reset` in every ACTIVE membership's tenant.<br>5. Until the membership is accepted, the API-S-User of an `INVITED` membership whose `app_user` was not created by that invitation shows `display_name` = the email, `last_login_at` null and `mfa_enrolled` null.<br>6. `PATCH /users/{id}` renames a user only when the invitation created the `app_user` row (`app_user.created_at = tenant_membership.invited_at` and `app_user.created_by = tenant_membership.created_by`); otherwise it returns 409 `invalid-transition` | 04 API-R-05 (no status precondition); SPEC-Q-182 (b), (c), (d) |
| Audit chain anchoring (PR-K-01) | 1. `verify_tenant_chain` reads `audit_chain_head` in the same transaction. It fails with reason "the chain ends before the head", and `first_failure_seq` = last checked seq + 1, when the last checked `chain_seq` or `hmac` differs from the head.<br>2. `record_tenant_verification` also fails, with reason "a verified event is missing or changed", when the event at the latest earlier PASS row's `to_chain_seq` is missing or its `hmac` differs from that row's `digest_last_hmac`.<br>3. DB-09 gains `tg_audit_chain_head__guard` (BEFORE UPDATE). It refuses with `EREV-AUD-001` any update not issued from inside `tg_audit_event__chain` (`pg_trigger_depth() < 2`), and any update that does not set `last_chain_seq = OLD.last_chain_seq + 1` | dev-guide DG-KRN-AUD-07; 04 DB-09, T-PLT-22 (IM-X free update) |
| One-time secrets and replay (PR-A-02) | The stored response of `POST /api-clients`, `POST /api-clients/{id}/rotate-secret` and `POST /webhook-endpoints` carries `client_secret` or `signing_secret` as null. A replay returns that stored body with `Idempotent-Replay: true`, and the schemas declare the member nullable. The value appears only in the first response | dev-guide DG-KRN-IDEM-03, DG-KRN-IDEM-04 |
| Password change (PR-A-03) | "Keeps the current session" (04 §16.12; PLF-15) means the user stays signed in under a rotated token (SAR-09). The presented session ends `REVOKED`, and the 204 carries the new `erev_session` cookie | BUILD_SPEC PLF-15 `test_change_password` wording; the loop's `test_me_password.py:82-84` |
| Outbound destinations (PR-A-04, PR-R-08) | 1. Outside `dev`, `test` and `e2e`, the guard refuses every resolved address that is not global unicast (`is_global` false, `is_multicast`, `is_reserved` or `is_unspecified`). NAT64 (`64:ff9b::/96`), 6to4 (`2002::/16`), IPv4-mapped and IPv4-compatible addresses are judged by their embedded IPv4 address.<br>2. OIDC discovery, JWKS and token requests, and SMTP connections, pass through the guard and connect to the checked address.<br>3. `_issuer_valid` and `erev idp create` take the environment and refuse http or loopback issuers under `production` (rule `T-PLT-03`) | 05 SAR-15 (enumerated ranges) |
| Configuration inserts (PR-K-03) | `erev.tg_config_version()` refuses an INSERT with `status <> 'DRAFT'` unless `current_setting('app.platform_scope', true) = 'provisioning'` (`EREV-CFG-002`) | 04 DB-04; SPEC-Q-151 |
| SoD rules as of a date (PR-C-05) | 1. For instant `at`, a code's rule is its PUBLISHED version with `published_at <= at`, or its SUPERSEDED version with `published_at <= at < effective_to`. A provisioning seed without `published_at` counts from the tenant's `created_at`.<br>2. `conflict_report(as_of)` counts assignments with `valid_from <= as_of` and (`revoked_at` null or `revoked_at > as_of`).<br>3. Commands keep `at = now` | dev-guide DG-KRN-PERM-03; SPEC-Q-150 |
| Dispatch and job recovery (PR-R-01 to PR-R-04) | 1. Webhook deliveries and outbox messages are claimed and committed one at a time, immediately before dispatch. The record step matches the claim stamp, and a lost claim settles without raising.<br>2. The OUTBOX_RELAY, EMAIL_DELIVERY, WEBHOOK_DELIVERY and AUDIT_CHAIN_VERIFY handlers heartbeat after each message, delivery or 1,000 verified events.<br>3. `run_job` records completion only on the RUNNING row of its own attempt.<br>4. The sweeper re-dispatches QUEUED jobs whose Procrastinate task is `failed`, `cancelled` or `aborted`, and retries tasks stalled in `doing` through `JobManager.get_stalled_jobs` (Procrastinate 3.9.0).<br>5. `_defer_unless_pending` counts only QUEUED rows whose task is `todo` or `doing` | dev-guide DG-KRN-EVT-05, DG-KRN-JOB-06; SPEC-Q-187 (b), SPEC-Q-189 (c) |
| Upload bodies (PR-R-06) | 1. The middleware counts body bytes while streaming and never holds more than one received message.<br>2. `POST /api/v1/files` without `Content-Length` returns 422 `validation-failed` with `errors[0].rule_id = "API-C-17"` before reading the body | 04 API-C-17 (silent on chunked uploads) |
| Launcher ports (PR-R-07, S-2) | 1. Make and `scripts/proc.sh` take `EREV_API_PORT`, `EREV_WEB_PORT`, `EREV_E2E_API_PORT` and `EREV_E2E_WEB_PORT` from the environment, else from the `.env` file named by `EREV_DOTENV` (default `.env`), else the defaults. Values are never printed.<br>2. Make passes `EREV_WEB_PORT` to the web process, which Vite reads (DG-RUN-21) | dev-guide DG-MK-dev-up, DG-RUN-03, DG-RUN-21; D-78 port row |

## Items not carried, and supervisor register entries

- PR-C-06: supply a frequency-ranked common-password list with its source and licence recorded, then add a supervisor item for the test.
- PR-R-09: schedule streaming seal and download before the first LMG item.
- S-3: add `EREV_PUBLIC_ORIGIN=http://127.0.0.1:5272` to the review worktree `.env` before browser QA, and state in `.env.example` that the origin follows the web port in review worktrees.
- Coverage gap: the authz-tenancy lens produced no findings list. Before placement, run a verifier pass on PR-Z-01 and PR-Z-02 and a route-inventory IDOR check (`authz-tenancy/route_inventory.json` exists but was never reported).
