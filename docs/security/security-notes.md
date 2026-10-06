# Security notes

Security-relevant behaviour changed by remediation items, with the rule it implements and the tests that prove it (BUILD_SPEC XR-16; dev-guide DG-DONE-07). The threat model and the ASVS checklist follow in SOP-9.

## MFA challenge limits (05 SAR-13; 01-DECISIONS D-80; BUILD_SPEC WEB-3a)

| Behaviour | Rule | Evidence |
|---|---|---|
| Rate limit | `POST /api/v1/session/mfa` is admitted through the sign-in buckets before any code is checked: at most 10 attempts per minute per client address and normalised email, and 50 per minute per client address, shared with `POST /api/v1/session/login`. A refused attempt returns 429 `rate-limited` with `Retry-After` and writes nothing. | `backend/tests/api/test_mfa.py::test_sar_13_mfa_rate_limit` |
| Lockout | A wrong TOTP code or recovery code writes `MFA_CHALLENGE_FAILED`. The fifth failure since the factor's last successful verification and since the user's latest `ACCOUNT_LOCKED` sets `app_user.locked_until` 15 minutes ahead, writes `ACCOUNT_LOCKED` and returns 423 `account-locked`. A password sign-in does not restart the count. | `backend/tests/api/test_mfa.py::test_ctl_033_mfa_lockout_after_five_failures` (CTL-033) |
| While locked | The route returns 423 without verifying the code, and password sign-in returns 423 as well. The lock lapses by itself. | same test |

- Residual risk: the limiter counts inside each api process, so several instances each allow the limit (runbook "Sign-in throttling and sessions"). The lockout counts stored events and holds across processes.
- The failure count compares security event times with the factor's `updated_at`, both from the database clock, and anchors the lock by the position of its `ACCOUNT_LOCKED` event (PROGRESS SPEC-Q-206).

## MFA reset and invitations of existing identities (05 THR-03, THR-07, THR-20; D-80; WEB-3a)

| Behaviour | Rule | Evidence |
|---|---|---|
| Reset scope | `POST /api/v1/users/{id}/reset-mfa` needs a membership that is `ACTIVE` or `SUSPENDED`; an invitation not yet accepted returns 409 `invalid-transition`, so a workspace cannot reset the factor of a person it merely invited. | `backend/tests/api/test_users_api.py::test_reset_mfa_refused_for_unaccepted_invitation` |
| Operators | An operator email cannot be invited (422 `validation-failed`, rule `T-PLT-02`), and a reset whose target is a platform operator returns 404. | `backend/tests/api/test_users_api.py::test_operator_identity_not_invitable_or_resettable` |
| Audit | The reset writes `user_mfa_factor.reset` in the acting workspace and in the workspace of every other ACTIVE membership of the person. | `backend/tests/api/test_users_api.py::test_reset_mfa_audited_in_every_active_workspace` |

## One-time secrets and replay (03 REQ-SEC-003; 05 SAR-18, THR-04; D-80; WEB-3b)

- `POST /api/v1/api-clients`, `POST /api/v1/api-clients/{id}/rotate-secret` and `POST /api/v1/webhook-endpoints` store their first response in `idempotency_record` with `client_secret` or `signing_secret` null (`run_command(..., stored_body=withheld(...))`). A replay returns that body with `Idempotent-Replay: true`, so the value appears only in the first response and is never kept in plaintext.
- Evidence: `backend/tests/api/test_api_clients.py::test_client_secret_not_kept_for_replay`, `backend/tests/api/test_webhooks_api.py::test_signing_secret_not_kept_for_replay`.

## Password change rotates the session (05 SAR-09, SAR-42; D-80; WEB-3b)

- `POST /api/v1/me/password` ends the other sessions with `PASSWORD_CHANGED` and reissues the presented one in the same transaction: the presented token ends `REVOKED`, and the 204 carries the new `erev_session` cookie. A token captured before the change stops working.
- Evidence: `backend/tests/api/test_me_password.py::test_change_password`.

## Outbound destination guard (05 SAR-15, THR-15, NTR-13; D-80; WEB-3b)

| Behaviour | Rule | Evidence |
|---|---|---|
| Address rule | Outside `dev`, `test` and `e2e`, `adapters/http/guard.py` refuses every resolved address that is not global unicast: `is_global` false, multicast, reserved, unspecified or IPv6 site-local. NAT64, 6to4, IPv4-mapped and IPv4-compatible addresses are judged by their embedded IPv4 address. The caller connects to the checked address, so a second DNS answer cannot redirect it. | `backend/tests/domain/platform/test_webhooks.py::test_sar_15_destination_guard` |
| Identity providers | `HttpxOidcHttp` checks every discovery, JWKS and token URL and connects to the checked address with SNI. A refusal raises before any request and fails the sign-in with `provider_request_failed`. `erev idp create` refuses http and loopback issuers under `production` (rule `T-PLT-03`). | `backend/tests/unit/test_oidc_client.py::test_sar_15_provider_urls_guarded`, `backend/tests/api/test_oidc.py::test_sar_15_callback_refuses_private_endpoints`, `backend/tests/unit/test_cli_idp.py::test_idp_create_refuses_loopback_http_issuer_in_production` |
| SMTP | `SmtpEmailSender.send` checks `EREV_SMTP_HOST` before any socket opens, connects to the checked address and verifies the certificate against the host name. | `backend/tests/domain/platform/test_outbox.py::test_sar_15_smtp_host_guarded` |

- Residual risk: the guard judges addresses, not services. A public address that forwards to internal services is outside its reach, and so is an operator-configured proxy (the clients ignore proxy environment variables). IPv6 site-local judgement adds `is_site_local` to the D-80 list, because Python classifies `fec0::/10` as global (PROGRESS SPEC-Q-214).

## Invitations of existing identities, and members who are no longer members (05 THR-07, PRV-01; 04 T-PLT-02; D-80; WEB-3b)

- A workspace is shown a person's own facts only while the person is its member (item IDENTITY-WITHHELD-BY-STATUS-1; 04 T-PLT-02 rev 1.316). While a membership is `INVITED` or `REMOVED`, API-S-User answers `last_login_at` and `mfa_enrolled` as null, whoever created the account, and says so with `sign_in_withheld`; it shows the email as `display_name` unless this membership's invitation created the account, a name the workspace typed itself. The user list searches and sorts on the name it shows, so a withheld name cannot be probed with `q`. An erased identity (05 PRV-07 a) is not withheld: the erasure removes every membership of the person and leaves the product's own label, `Erased user <8 hex>`, which every workspace reads, as an actor read by user id does.
- The rule goes by the membership's status. Until rev 1.316 it read "never accepted" (`activated_at` null); measured through the routes, that let a workspace keep reading a person it had removed: the `REMOVED` row of a member who had accepted gave the person's current name, MFA state and last sign-in, and the sign-in it gave was one made after the removal; a second invitation gave the same before its acceptance. The user access listing (RPT-24) withholds the same two cells of an `INVITED` or `REMOVED` row: null in the run's data, empty in CSV, "Not shown" in XLSX and PDF, by the row's own Membership value.
- `PATCH /api/v1/users/{id}` renames only a person whose `app_user` row the invitation created (`created_at` equal to `invited_at` and `created_by` equal to the membership's `created_by`); otherwise 409 `invalid-transition`.
- The rule is one rule for every reader of the person behind a membership, not for API-S-User alone (item IDENTITY-BEFORE-ACCEPTANCE-READERS-1; 04 T-PLT-02 rev 1.315; dev-guide DG-KRN-DB-13): while the rule withholds them, the summary of a role request or of an SoD exception request, `member_name` of a role assignment and of an SoD exception, the label of the membership's audit events, an access review's items, reviewers and snapshot file and, since rev 1.316, the owner of an exception item and the two parties of a delegation's own row show the email and no last sign-in. Measured through the routes before that item: each of them gave the name another workspace had typed for a person this workspace had only invited, and the access review gave that person's last sign-in elsewhere — whoever may invite an address learnt the name behind it. A request's summary and a review's snapshot are written once and keep what the workspace was shown when they were written.
- What stays named, and one limit. The record of an act names the person who acted: an actor of an audit event and a decision's `on_behalf_of`, by the user id the row carries, in the approvals reads and the approvals register; and the delegator in the SoD conflict report's "Through delegations", by the delegation's membership. So an ENDED delegation's own row shows the email of a removed party whose account this workspace did not create, while the decisions taken under it keep the name; both are meant. An access review's item stores no status of its membership: the null of its last sign-in means "never" for a member and "not shown" for an invited one, and its screen prints "Never" for both (the remedy is a column on the item).
- Evidence: `backend/tests/api/test_users_api.py::test_invitation_of_existing_user_discloses_nothing`, `backend/tests/api/test_users_api.py::test_rename_only_users_created_by_the_invitation`, `backend/tests/api/test_users_api.py::test_a_person_only_invited_is_named_by_no_reader_before_acceptance`, `backend/tests/api/test_users_api.py::test_who_is_not_a_member_now_is_shown_as_one_only_invited`, `backend/tests/api/test_users_api.py::test_an_erased_person_reads_by_the_erasure_label_whoever_created_the_identity`, `backend/tests/domain/reports/test_registers_access.py::test_user_access_listing_states_a_removal_that_a_later_invitation_ended`, `backend/tests/unit/reports/test_not_shown.py`, `backend/tests/architecture/test_shown_identity.py::test_dg_krn_db_13_the_person_of_a_membership_is_read_through_the_rule`.

## Separation of duties at approval (03 REQ-PLT-010; CTL-034; D-80; WEB-3a)

- Approving a role assignment locks the member's membership row before the SoD check, and approving a role change locks the membership of every holder, in ascending id order. Concurrent approvals for one member therefore run one after the other, and the second sees the first grant (`backend/tests/domain/platform/test_approval_engine.py::test_ctl_034_concurrent_conflicting_approvals_serialised`, `backend/tests/api/test_roles_api.py::test_ctl_034_second_pending_grant_refused_at_approval`).

## Audit chain anchoring (05 SAR-31, THR-09; CTL-038, CTL-039; D-80; WEB-3a)

- Verification compares the end of the chain with `audit_chain_head` and the latest earlier `PASS` digest; the head advances only through appends (`tg_audit_chain_head__guard`). Runbook "Chain verification".
- Evidence: `backend/tests/domain/platform/test_audit_verification.py::test_ctl_039_truncated_chain_fails`, `backend/tests/pg/test_db_invariants.py::test_db_09_chain_head_advances_only_through_append`, `backend/tests/pg/test_chains.py::test_ctl_038_actor_tamper_detected`, `backend/tests/domain/platform/test_audit_writer.py::test_krn_aud_03_hmac_covers_every_column`.
- Residual risk: `erev_owner` can also delete `audit_chain_verification` rows and disable the guard, so only digests copied outside the database (the hosted digest bucket) fully resist that actor (THR-09).

## Configuration versions only leave DRAFT along E-12 (04 DB-04, §1.5 IM-P; CTL-011, CTL-031, CTL-034; D-80; WEB-3d)

- `erev.tg_config_version()` refuses an INSERT of a `sod_rule`, `registry_version` or `rule_set_version` whose status is not DRAFT unless the transaction runs under the provisioning platform scope (`EREV-CFG-002`). A tenant session can no longer publish content, such as a weaker SoD rule, without an approval request.
- Evidence: `backend/tests/pg/test_db_invariants.py::test_db_04_insert_outside_draft_refused`.

## SoD conflict reports as of a date (03 REQ-PLT-010; CTL-034; D-80; WEB-3d)

- `conflict_report(as_of)` applies the rule versions in force at that instant (a SUPERSEDED version for `[published_at, effective_to)`) and counts assignments revoked after it. A report for a past date no longer hides a conflict that a later rule change or revocation removed.
- Evidence: `backend/tests/domain/platform/test_sod.py::test_conflict_report_as_of_uses_rule_in_force_then`, `::test_krn_perm_03_rules_from_published_rows_only`.

## Upload and body limits on actual bytes (05 UPL-01, UPL-04, THR-12, THR-18; 04 API-C-17; REQ-SEC-012; D-80; WEB-3d)

| Behaviour | Rule | Evidence |
|---|---|---|
| ZIP inflation | `files/policy.py` inflates every OOXML entry in 64 KiB reads that stop one byte past its declared size. An entry that produces more or less than it declares, whose local header and central directory declare different sizes, or that uses a method other than stored or deflate is refused, so the UPL-04 entry, total and ratio limits hold for the output actually produced. | `backend/tests/unit/test_upload_policy.py::test_upl_04_declared_sizes_not_trusted` |
| Streamed bodies | The request middleware passes body messages to the route one at a time and counts them; past the route limit the route receives `http.disconnect` and the answer is 422 `validation-failed` (`API-C-17`). `POST /api/v1/files` without `Content-Length` is refused before any byte is read. | `backend/tests/api/test_middleware.py::test_api_c_17_chunked_upload_needs_declared_length`, `::test_api_c_17_body_limit_without_declared_length` |

- Residual risk: a declared `Content-Length` up to 500 MiB plus framing still reaches the multipart parser for uploads, which spools to disk; the per-purpose limit applies after parsing, and downloads and sealing still hold whole files in memory (PR-R-09, not carried).

## Cross-origin response policies (05 SAR-20; supervisor ruling R-37 (a))

Every response of nginx, of the api and of the Vite preview server carries `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-origin`: a page of another origin can neither keep a window reference to the application nor embed one of its responses as a script, an image or a frame (`frame-ancestors 'none'` and `X-Frame-Options: DENY` already refuse framing). Requests from an origin on the CORS allow-list (05 SAR-12) are made in CORS mode and are not subject to the resource policy.

`Cross-Origin-Embedder-Policy` is deliberately not sent. It is the second half of cross-origin isolation, which a page needs only for `SharedArrayBuffer` and high-resolution timers; the application uses neither, and `require-corp` would oblige every resource it ever embeds to opt in. The ZAP baseline therefore keeps one low-risk informational alert for the absent header (rule 90004); it is accepted here, not suppressed in the scan.
