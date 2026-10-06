# eRev Cloud OWASP ASVS level 2 checklist
Scope: the API and the web app of eRev Cloud 1.0 against every level 1 and level 2 requirement of OWASP ASVS 5.0.0 (03 REQ-SEC-005; 05 SAR-41; BUILD_SPEC SOP-9), one row per requirement id. This document measures nothing itself: a `MET` row is evidence only when the gate that runs the named test is green on a clean tree (the DB-bound and e2e families run in `make ci`, `make test-pg` and `make e2e`, not in a lane), and rows marked "written NOT RUN by lane P8" name tests that have not run anywhere yet. Applicability decisions, organisation facts and approvals stay open and are owned by Ray and the security owner; the statuses below are the lane's own assessment of this tree (branch `sprint/l16`), not an acceptance.
**Attribution.** Requirement identifiers are those of the OWASP Application Security Verification Standard version 5.0.0, release commit `5cf9b032440be53ce345ab3c130fda46ba1ce7a2` (tag `v5.0.0_release`), © OWASP Foundation, licensed under the Creative Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0). This checklist lists the identifiers only and references the official catalogue for the requirement text; no requirement text is reproduced here, because a share-alike derivative is a licensing decision for Ray and Legal. Official catalogue JSON SHA-256 `bcdbec214d70abcfad9284a31d4f9e5134305831d628aad3aa85d7e26626cb35`; the committed L1 + L2 identifier inventory `docs/security/asvs-5.0.0-l1-l2-ids.json` (253 ids: 70 L1, 183 L2; ids, levels, chapters and sections only) SHA-256 `775ad22cc99e68b33882c78ca6b24a629c2d425000dadfdce266486e2b4c5aba`; `backend/tests/unit/test_security_documents.py::test_asvs_rows_have_status_and_evidence` pins that hash and checks that the rows below are exactly that set, once each.
**Status vocabulary.** `MET` — a named test node id (or a governed document for a documentation requirement) exists in this repository and proves the control; `NOT_APPLICABLE` — the technology or feature the requirement governs is absent, with the reason; `ACCEPTED_RISK` — a THR id of `docs/security/threat-model.md` and an owner; `GAP` — the control is not proven or not built, with an owner. A support file that merely resolves a reference is not evidence; every `MET` row names the test that exercises the control. Where a `MET` test is written but not yet run, the row says so.
Counts at this revision: MET 164, NOT_APPLICABLE 50, ACCEPTED_RISK 4, GAP 35 (253 rows).
Node-id prefixes are written in full in every row (no abbreviations), so each reference resolves on its own.

## V1 Encoding and sanitization
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V1.1.1 | L2 | GAP | single canonical decoding of inputs is not proven by a named test (JSON bodies are decoded once by the framework; query and path decoding not assessed); owner: security owner (Ray) |
| V1.1.2 | L2 | MET | `backend/tests/unit/test_export_formula_injection.py::test_req_sec_011_prefix`; `backend/tests/unit/test_problems.py::test_problem_response_media_type_errors_and_extensions` — export (CSV / XLSX) and JSON contexts; the React text rendering context is not assessed by a test (see V3.2.2) |
| V1.2.1 | L1 | GAP | output encoding per HTTP / HTML context is not proven by a named test; the API emits JSON with an exact media type (`backend/tests/unit/test_problems.py::test_problem_response_media_type_errors_and_extensions`); owner: security owner (Ray) |
| V1.2.2 | L1 | GAP | encoding of untrusted data in dynamically built URLs (frontend routes, Location headers) not assessed by a test; owner: security owner (Ray) |
| V1.2.3 | L1 | MET | `backend/tests/unit/test_problems.py::test_krn_err_01_problem_json_shape` — JSON is produced by the framework serializer only; no hand-built JSON or script content |
| V1.2.4 | L1 | MET | `backend/tests/unit/test_lists.py::test_dg_lst_02_fixed_direction_and_filter_literals`; `backend/tests/unit/test_lists.py::test_dg_lst_03_foreign_or_malformed_cursor`; `backend/tests/pg/test_session_guards.py::test_krn_db_04_context_free_sql_refused` — SQLAlchemy Core bound parameters everywhere; sort keys and filters allow-listed per resource (API-C-09); ruff S608 in `make lint` (THR-14) |
| V1.2.5 | L1 | NOT_APPLICABLE | the only OS invocations are fixed `git` commands in `controls/registry.py` and `controls/release.py` with no request data (grep at this revision); no shell is spawned with user input |
| V1.2.6 | L2 | NOT_APPLICABLE | no LDAP directory is queried (grep at this revision) |
| V1.2.7 | L2 | NOT_APPLICABLE | no XPath or XQuery is evaluated; XML is read only by openpyxl under defusedxml (grep at this revision) |
| V1.2.8 | L2 | NOT_APPLICABLE | no LaTeX processor is used |
| V1.2.9 | L2 | NOT_APPLICABLE | no regular expression is built from user input; the three formatted patterns in `adapters/keys/provider.py` interpolate module constants only (grep at this revision) |
| V1.3.1 | L1 | NOT_APPLICABLE | no WYSIWYG or HTML input exists; memos and comments are plain text rendered as text |
| V1.3.2 | L1 | NOT_APPLICABLE | no dynamic code execution feature (`eval`, `exec`, expression languages) in the application code (grep at this revision) |
| V1.3.3 | L2 | MET | `backend/tests/unit/test_local_file_store.py::test_invalid_storage_keys_raise`; `backend/tests/unit/test_local_file_store.py::test_put_is_content_addressed_and_atomic`; `backend/tests/api/test_security_headers.py::test_sar_42_headers_on_api_errors_and_files` (written NOT RUN by lane P8) — file paths are internal content addresses; served names go through Content-Disposition |
| V1.3.4 | L2 | NOT_APPLICABLE | SVG is not an admitted upload type (`backend/tests/unit/test_upload_policy.py::test_upl_02_attachment_types_by_content`) |
| V1.3.5 | L2 | NOT_APPLICABLE | no Markdown, CSS, XSL, BBCode or template content from users is rendered |
| V1.3.6 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_blocked_ranges`; `backend/tests/unit/test_ssrf_guard.py::test_sar_15_scheme_credentials_and_resolution`; `backend/tests/unit/test_ssrf_guard.py::test_sar_15_connects_to_the_resolved_address`; `backend/tests/unit/test_oidc_client.py::test_sar_15_provider_urls_guarded`; `backend/tests/api/test_oidc.py::test_sar_15_callback_refuses_private_endpoints` |
| V1.3.7 | L2 | NOT_APPLICABLE | no server-side template engine builds templates from untrusted input (grep at this revision); e-mail bodies are composed from fixed strings |
| V1.3.8 | L2 | NOT_APPLICABLE | no JNDI (not a JVM application) |
| V1.3.9 | L2 | NOT_APPLICABLE | no memcache or other text-protocol cache is used |
| V1.3.10 | L2 | MET | `backend/tests/unit/test_logging.py::test_dg_log_01_json_fields`; `backend/tests/unit/test_logging.py::test_opr_21_logger_extension_and_truncation` — structured JSON logging; no printf-style formatting of user data |
| V1.3.11 | L2 | GAP | SMTP header injection through recipient or subject values is not proven by a named test (addresses are pydantic-validated; the fake mail adapter records structured messages); owner: security owner (Ray) |
| V1.4.1 | L2 | NOT_APPLICABLE | Python and TypeScript with managed memory; no native code of our own |
| V1.4.2 | L2 | NOT_APPLICABLE | Python integers are unbounded and money is `Decimal` (API-C-06; `backend/tests/unit/test_api_money.py`); no fixed-width arithmetic of our own |
| V1.4.3 | L2 | NOT_APPLICABLE | managed memory; no manual allocation |
| V1.5.1 | L1 | MET | `backend/tests/unit/test_doctor_production_checks.py::test_observe_defusedxml_reads_the_installed_openpyxl`; `backend/tests/api/test_upload_attacks.py::test_sar_42_upload_fixtures_rejected`; `backend/tests/api/test_upload_attacks.py::test_sar_42_dtd_detected_in_utf16_parts` — defusedxml active under openpyxl; any OOXML part declaring a DTD is refused at upload in every encoding |
| V1.5.2 | L2 | MET | `backend/tests/unit/test_problems.py::test_krn_err_02_validation_error_field_path`; `backend/tests/unit/test_migration_schemas.py` — pydantic models with closed field sets deserialize JSON only; no pickle or object deserialization (forbidden-pattern guard `backend/tests/architecture/test_forbidden_patterns.py::test_dg_arc_05_repository_clean`) |

## V2 Validation and business logic
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V2.1.1 | L1 | MET | `docs/04-DATA_MODEL.md`; `docs/03-REQUIREMENTS.md` — 04 §15 API-C rules (money, dates, versions, list literals) and the REQ-DAT validation rows define the expected structure of every input |
| V2.1.2 | L2 | MET | `docs/04-DATA_MODEL.md`; `docs/02-PRD.md` — 04 table 15.4-E data-quality findings and the PRD BR rules define cross-field consistency (over-delivery, period order, entity and book pairs) |
| V2.1.3 | L2 | MET | `docs/05-ARCHITECTURE.md` — upload limits (UPL), body limit (DPL-12), job profiles and per-tenant job cap (JOB-03), rate limits (SAR-13) are stated per user and globally |
| V2.2.1 | L1 | MET | `backend/tests/unit/test_api_money.py`; `backend/tests/unit/test_problems.py::test_krn_err_02_validation_error_field_path` — positive validation through typed schemas; refusals name the field (422 `validation-failed`) |
| V2.2.2 | L1 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_commands_depend_on_command`; `backend/tests/unit/test_api_money.py` — validation is server-side in the schemas and the domain; the browser application only improves usability |
| V2.2.3 | L2 | MET | `backend/tests/domain/close/test_period_states.py`; `backend/tests/domain/close/test_reopen.py` — related items are checked together (period order, later-period lock before reopen, entity and book pairing) |
| V2.3.1 | L1 | MET | `backend/tests/domain/close/test_period_states.py`; `backend/tests/domain/ssp/test_publication.py`; `backend/tests/domain/platform/test_approval_engine.py::test_krn_apr_01_submit_stores_hash_and_one_step` — state machines refuse skipped steps with 409 `invalid-transition` |
| V2.3.2 | L2 | ACCEPTED_RISK | THR-18: job caps and upload limits are implemented; the per-route API-client and browser admission limits are SOP-4 work (browser admission gap P4-SOP4-BROWSER-1 open); owner lane-p4-doctor |
| V2.3.3 | L2 | ACCEPTED_RISK | THR-26: every command runs in ONE unit of work that commits whole or rolls back and stores no success (`backend/tests/pg/test_session_guards.py::test_krn_db_01_normal_exit_commits_and_exception_rolls_back`; `backend/tests/domain/platform/test_approval_engine.py::test_krn_apr_02_on_approved_runs_in_transaction`); the exception is the erasure of a person who belongs to several workspaces — the other workspaces' removals commit one transaction each before the identity changes, so a failure in between leaves committed removals and an owed completion event; this is the accepted durable-progress design (Codex 2254 / 2322 / 2359; supervisor), made resumable by durable markers and a manual second command (`backend/tests/domain/platform/test_privacy_commands.py::test_prv_07a_three_tenant_partial_completion`; `backend/tests/domain/platform/test_privacy_commands.py::test_prv_07a_alternate_workspace_completion` (written NOT RUN by lane P8)); owner privacy owner (Ray) |
| V2.3.4 | L2 | MET | `backend/tests/unit/test_activation_lock_order.py`; `backend/tests/architecture/test_lock_order.py`; `backend/tests/domain/platform/test_approval_engine.py::test_ctl_034_concurrent_conflicting_approvals_serialised` — row locks in one global order; concurrent conflicting approvals serialised |
| V2.4.1 | L2 | ACCEPTED_RISK | THR-18: login and MFA limits are MET (`backend/tests/api/test_session.py::test_sar_13_login_rate_limit`; `backend/tests/api/test_mfa.py::test_sar_13_mfa_rate_limit`); API-client and browser admission limits are SOP-4 (`backend/tests/unit/test_rate_limit_policy.py::test_api_client_limit_five_refuses_the_sixth_with_retry_after_and_resets_after_a_minute` tests the policy, not the wiring); owner lane-p4-doctor |

## V3 Web frontend security
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V3.2.1 | L1 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — `X-Content-Type-Options: nosniff` and an exact media type on every response |
| V3.2.2 | L1 | GAP | safe text rendering in the React application is not proven by a lint rule or test (no `dangerouslySetInnerHTML` audit); owner: WEB lane |
| V3.3.1 | L1 | GAP | the session cookie `erev_session` carries `Secure` outside `dev` but neither the `__Host-` nor the `__Secure-` prefix; renaming is a product decision; owner: security owner (Ray) |
| V3.3.2 | L2 | MET | `backend/tests/api/test_session.py::test_login_sets_cookie_and_returns_csrf` — `SameSite=Lax` (SAR-09) |
| V3.3.3 | L2 | GAP | no `__Host-` prefix on the session cookie (see V3.3.1); owner: security owner (Ray) |
| V3.3.4 | L2 | MET | `backend/tests/api/test_session.py::test_login_sets_cookie_and_returns_csrf` — `HttpOnly` |
| V3.4.1 | L1 | GAP | HSTS is not set by the application; it is expected at the hosted load balancer and is not asserted by the Terraform policy tests; owner: deploy lane (lane-p2-hosted-providers) and self-hosters |
| V3.4.2 | L1 | MET | `backend/tests/api/test_session.py::test_krn_auth_02_csrf_and_origin`; `backend/tests/unit/test_doctor_production_checks.py::test_sar_40_production_checks` — fixed CORS origins from configuration; the doctor's `cors-origins` check |
| V3.4.3 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — strict CSP without inline scripts (SAR-20) |
| V3.4.4 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` |
| V3.4.5 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — `Referrer-Policy: same-origin` |
| V3.4.6 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — `frame-ancestors 'none'` (THR-25) |
| V3.5.1 | L1 | MET | `backend/tests/api/test_session.py::test_krn_auth_02_csrf_and_origin`; `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_csrf_rejected` (written NOT RUN by lane P8) — CSRF token and Origin check on every command (API-C-02) |
| V3.5.2 | L1 | NOT_APPLICABLE | the application does not rely on the CORS preflight for protection; it uses the token and Origin check of V3.5.1 |
| V3.5.3 | L1 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_commands_depend_on_command` — every state change is a POST, PATCH, PUT or DELETE command; GET routes read only |
| V3.5.4 | L2 | NOT_APPLICABLE | one application on one origin; no second application shares the host |
| V3.5.5 | L2 | NOT_APPLICABLE | no `postMessage` interface in the web application (grep at this revision) |
| V3.7.1 | L2 | MET | `backend/tests/unit/test_licence_check.py::test_repository_dependencies_pass`; `docs/dev-guide.md` — React 19, TypeScript and Vite from the lock file; `make audit-deps` (SAR-17) reports vulnerable versions |
| V3.7.2 | L2 | MET | `backend/tests/api/test_oidc.py::test_state_or_nonce_mismatch_refused`; `backend/tests/api/test_oidc.py::test_sar_15_callback_refuses_private_endpoints` — the only cross-host redirect is the OIDC start to a configured provider; no `next`-style open redirect parameter exists in the API |

## V4 API and web service
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V4.1.1 | L1 | MET | `backend/tests/unit/test_problems.py::test_problem_response_media_type_errors_and_extensions`; `backend/tests/api/test_security_headers.py::test_sar_42_headers_on_api_errors_and_files` (written NOT RUN by lane P8) |
| V4.1.2 | L2 | GAP | HTTP-to-HTTPS redirection is a load-balancer setting not asserted by the Terraform policy tests; owner: deploy lane (lane-p2-hosted-providers) and self-hosters |
| V4.1.3 | L2 | GAP | trust of intermediary headers (`X-Forwarded-For` for rate limiting, `X-Request-Id` accepted from clients when well-formed) is not assessed by a test; owner: lane-p4-doctor (SOP-4) with the deploy lane |
| V4.2.1 | L2 | GAP | request-boundary handling (smuggling) depends on the load balancer and uvicorn / h11; not assessed; owner: deploy lane (lane-p2-hosted-providers) |
| V4.3.1 | L2 | NOT_APPLICABLE | no GraphQL or data-layer expression API |
| V4.3.2 | L2 | NOT_APPLICABLE | no GraphQL API is exposed (see V4.3.1) |
| V4.4.1 | L1 | NOT_APPLICABLE | no WebSocket connections |
| V4.4.2 | L2 | NOT_APPLICABLE | no WebSocket connections |
| V4.4.3 | L2 | NOT_APPLICABLE | no WebSocket connections |
| V4.4.4 | L2 | NOT_APPLICABLE | no WebSocket connections |

## V5 File handling
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V5.1.1 | L2 | MET | `docs/05-ARCHITECTURE.md`; `backend/tests/unit/test_upload_policy.py::test_size_limits_per_purpose` — UPL-01 to UPL-12 define the admitted types, extensions and limits per purpose, including unpacked sizes |
| V5.2.1 | L1 | MET | `backend/tests/unit/test_upload_policy.py::test_size_limits_per_purpose`; `backend/tests/unit/test_upload_policy.py::test_upl_04_declared_sizes_not_trusted`; `backend/tests/api/test_files.py::test_upload_limits_per_purpose` |
| V5.2.2 | L1 | MET | `backend/tests/unit/test_upload_policy.py::test_upl_02_extension_must_match_content`; `backend/tests/unit/test_upload_policy.py::test_upl_02_attachment_types_by_content` |
| V5.2.3 | L2 | MET | `backend/tests/unit/test_upload_policy.py::test_upl_04_zip_limits`; `backend/tests/api/test_files.py::test_upl_04_zip_limits` — uncompressed size, entry count and ratio limits before any part is read |
| V5.3.1 | L1 | MET | `backend/tests/unit/test_local_file_store.py::test_put_stores_ciphertext_under_the_plaintext_key`; `backend/tests/api/test_security_headers.py::test_sar_42_headers_on_api_errors_and_files` (written NOT RUN by lane P8) — uploads are stored encrypted under content addresses outside any served directory and downloaded as attachments; nothing is executed or rendered |
| V5.3.2 | L1 | MET | `backend/tests/unit/test_local_file_store.py::test_invalid_storage_keys_raise`; `backend/tests/unit/test_local_file_store.py::test_put_is_content_addressed_and_atomic` |
| V5.4.1 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_42_headers_on_api_errors_and_files` (written NOT RUN by lane P8) — `Content-Disposition: attachment` with a server-chosen file name |
| V5.4.2 | L2 | GAP | RFC 6266 encoding of non-ASCII served file names (`filename*`) is not asserted by a test; owner: security owner (Ray) |
| V5.4.3 | L2 | ACCEPTED_RISK | THR-12: no antivirus scanning in 1.0 (UPL-12): files are never executed or rendered, macro containers are rejected, parsers run in the worker; owner Prov (hosting provider or self-hoster) |

## V6 Authentication
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V6.1.1 | L1 | MET | `docs/05-ARCHITECTURE.md`; `backend/tests/api/test_session.py::test_ctl_033_lockout_after_five_failures`; `backend/tests/api/test_session.py::test_sar_13_login_rate_limit` — SAR-06 / SAR-13 document lockout and limits |
| V6.1.2 | L2 | GAP | no documented list of context-specific words (product and organisation names) for the password check; owner: security owner (Ray) |
| V6.1.3 | L2 | MET | `docs/05-ARCHITECTURE.md` — the three pathways (password + TOTP, OIDC linked to an existing verified e-mail, API client credentials) with their controls (SAR-06 to SAR-13) |
| V6.2.1 | L1 | MET | `backend/tests/unit/test_passwords.py::test_req_plt_004_password_policy` |
| V6.2.2 | L1 | MET | `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_session_token_rotates` (written NOT RUN by lane P8); `backend/tests/api/test_me_password.py` |
| V6.2.3 | L1 | MET | `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_session_token_rotates` (written NOT RUN by lane P8) — `current_password` and `new_password` |
| V6.2.4 | L1 | MET | `backend/tests/unit/test_passwords.py::test_common_password_list_is_bundled`; `backend/tests/unit/test_passwords.py::test_common_password_list_notice_records_provenance` |
| V6.2.5 | L1 | MET | `backend/tests/unit/test_passwords.py::test_req_plt_004_password_policy` — length only; no composition rules |
| V6.2.6 | L1 | GAP | `type=password` on the sign-in and password forms is not asserted by a frontend test; owner: WEB lane |
| V6.2.7 | L1 | GAP | paste and password-manager friendliness of the forms is not asserted by a frontend test; owner: WEB lane |
| V6.2.8 | L1 | MET | `backend/tests/unit/test_passwords.py::test_verification_of_malformed_or_dummy_hash_is_false`; `backend/tests/unit/test_passwords.py::test_pr_c_06_frequent_long_passwords_are_refused` — argon2id verification of the received string; no truncation or case folding |
| V6.2.9 | L2 | MET | `backend/tests/unit/test_passwords.py::test_pr_c_06_frequent_long_passwords_are_refused` — long passwords are accepted unless they are common |
| V6.2.10 | L2 | MET | `docs/03-REQUIREMENTS.md` — REQ-PLT-004 defines no expiry; no rotation prompt exists |
| V6.2.11 | L2 | GAP | depends on V6.1.2 (no context-specific word list); owner: security owner (Ray) |
| V6.2.12 | L2 | MET | `backend/tests/unit/test_passwords.py::test_common_password_list_is_bundled` — the bundled top-common list is breach-derived (provenance recorded in NOTICE) |
| V6.3.1 | L1 | MET | `backend/tests/api/test_session.py::test_ctl_033_lockout_after_five_failures`; `backend/tests/api/test_session.py::test_sar_13_login_rate_limit`; `backend/tests/api/test_session.py::test_sar_06_unknown_email` |
| V6.3.2 | L1 | MET | `backend/tests/unit/test_cli_tenant.py`; `backend/tests/unit/test_cli_operator.py` — provisioning invites a named administrator; no default account or password exists |
| V6.3.3 | L2 | GAP | TOTP is enforced for the user, by the server: a user who holds a permission marked `requires_mfa`, or who enrolled a factor, has no usable session without it (`backend/tests/api/test_mfa.py::test_ctl_033_mfa_required_permission_blocks_until_verified`; `backend/tests/api/test_mfa.py::test_ctl_033_unenrolled_mandatory_user_reaches_only_enrolment`; `backend/tests/api/test_mfa.py::test_ctl_033_password_only_session_of_an_enrolled_user_reaches_only_the_challenge`; `backend/tests/api/test_mfa.py::test_ctl_033_every_route_refuses_a_session_that_owes_its_second_factor`); a tenant-wide rule that every user must complete MFA before any access is a policy decision not yet ruled; owner: security owner (Ray) |
| V6.3.4 | L2 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_every_route_guarded`; `docs/05-ARCHITECTURE.md` — every route is guarded; the pathways are those of V6.1.3 |
| V6.4.1 | L1 | MET | `backend/tests/unit/test_invitation_lookup_failures.py`; `backend/tests/api/test_users_api.py::test_resend_invitation_replaces_token` — invitation tokens are random, hashed at rest and expire in 7 days |
| V6.4.2 | L1 | MET | `docs/api/openapi.json` — no password hint or knowledge-based recovery route exists (recovery codes and administrator MFA reset only) |
| V6.4.3 | L2 | MET | `backend/tests/api/test_password_reset.py::test_request_always_202`; `backend/tests/api/test_password_reset.py::test_confirm_resets_and_ends_sessions`; `backend/tests/api/test_mfa.py::test_login_next_step_flags` — a reset changes the password and ends sessions; the TOTP factor stays enrolled and is still required |
| V6.4.4 | L2 | MET | `backend/tests/api/test_users_api.py::test_reset_mfa_step_up_and_sessions`; `backend/tests/api/test_users_api.py::test_reset_mfa_audited_in_every_active_workspace` — a lost factor is reset only by an administrator under step-up, audited |
| V6.5.1 | L2 | MET | `backend/tests/unit/test_totp.py::test_sar_26_rfc6238_vector_and_window`; `backend/tests/api/test_mfa.py::test_recovery_code_single_use` — `last_used_step` replay block; recovery codes single use |
| V6.5.2 | L2 | MET | `backend/tests/api/test_mfa.py::test_enrolment_returns_ten_codes_once`; `backend/tests/api/test_mfa.py::test_regenerate_recovery_codes_invalidates_previous_batch` — recovery codes shown once and hashed at rest (argon2id) |
| V6.5.3 | L2 | MET | `backend/tests/unit/test_totp.py::test_provisioning_uri_and_new_secret` — secrets from the `secrets` module (CSPRNG) |
| V6.5.4 | L2 | MET | `backend/tests/unit/test_totp.py::test_sar_26_rfc6238_vector_and_window`; `backend/tests/api/test_mfa.py::test_enrolment_returns_ten_codes_once` — six-digit TOTP; recovery codes above the minimum entropy |
| V6.5.5 | L2 | MET | `backend/tests/unit/test_totp.py::test_sar_26_rfc6238_vector_and_window`; `backend/tests/api/test_mfa.py::test_bs1_d_19_step_up_window` — 30-second steps with a bounded window; five-minute step-up validity |
| V6.6.1 | L2 | NOT_APPLICABLE | no SMS or telephone one-time codes |
| V6.6.2 | L2 | NOT_APPLICABLE | no out-of-band authentication |
| V6.6.3 | L2 | NOT_APPLICABLE | no out-of-band authentication |
| V6.8.1 | L2 | MET | `backend/tests/api/test_oidc.py::test_links_existing_user_by_verified_email`; `backend/tests/api/test_oidc.py::test_unknown_or_unverified_email_refused` — an ID token links only to an existing user by a verified e-mail; roles never come from the provider |
| V6.8.2 | L2 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` |
| V6.8.3 | L2 | NOT_APPLICABLE | no SAML assertions are accepted; OIDC only |
| V6.8.4 | L2 | MET | `backend/tests/api/test_mfa.py::test_bs1_d_19_step_up_window`; `backend/tests/domain/platform/test_approval_engine.py::test_decide_requires_mfa_verified_session` — sensitive functions require eRev's own fresh TOTP step-up whatever the sign-in pathway |

## V7 Session management
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V7.1.1 | L2 | MET | `docs/05-ARCHITECTURE.md`; `backend/tests/api/test_session.py::test_ctl_033_idle_and_absolute_timeout` — idle 30 min, absolute 12 h (SAR-09) |
| V7.1.2 | L2 | GAP | the number of concurrent sessions per account and the intended behaviour are not documented; owner: security owner (Ray) |
| V7.1.3 | L2 | MET | `docs/05-ARCHITECTURE.md` — OIDC relying-party sessions are eRev sessions; provider sessions are documented as outside the boundary |
| V7.2.1 | L1 | MET | `backend/tests/api/test_session.py::test_logout_invalidates_session_server_side`; `backend/tests/api/test_session.py::test_ctl_033_idle_and_absolute_timeout` — server-side session rows verified on every request |
| V7.2.2 | L1 | MET | `backend/tests/api/test_session.py::test_sar_09_tenant_selection_rotates_token`; `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_session_token_rotates` (written NOT RUN by lane P8) — opaque reference tokens generated per session |
| V7.2.3 | L1 | MET | `backend/tests/api/test_session.py::test_login_sets_cookie_and_returns_csrf`; `backend/tests/api/test_session.py::test_sar_09_tenant_selection_rotates_token` — unique random tokens, hashed at rest |
| V7.2.4 | L1 | MET | `backend/tests/api/test_session.py::test_sar_09_tenant_selection_rotates_token`; `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_session_token_rotates` (written NOT RUN by lane P8) |
| V7.3.1 | L2 | MET | `backend/tests/api/test_session.py::test_ctl_033_idle_and_absolute_timeout` |
| V7.3.2 | L2 | MET | `backend/tests/api/test_session.py::test_ctl_033_idle_and_absolute_timeout` |
| V7.4.1 | L1 | MET | `backend/tests/api/test_session.py::test_logout_invalidates_session_server_side` |
| V7.4.2 | L1 | MET | `backend/tests/api/test_users_api.py::test_suspend_ends_sessions`; `backend/tests/domain/platform/test_privacy_commands.py::test_prv_07a_anonymise_user` (written NOT RUN by lane P8) — suspension, removal and erasure end every session of the person |
| V7.4.3 | L2 | MET | `backend/tests/api/test_password_reset.py::test_confirm_resets_and_ends_sessions`; `backend/tests/api/test_users_api.py::test_reset_mfa_step_up_and_sessions` — a password reset or an MFA reset ends the other sessions itself (no opt-in needed) |
| V7.4.4 | L2 | GAP | visible logout on every authenticated page is a frontend property not asserted by a test; owner: WEB lane |
| V7.4.5 | L2 | MET | `backend/tests/api/test_users_api.py::test_suspend_ends_sessions` — an administrator ends a person's sessions by suspending the membership; no all-users command exists (documented limit) |
| V7.5.1 | L2 | MET | `backend/tests/api/test_csrf_and_session_fixation.py::test_sar_42_session_token_rotates` (written NOT RUN by lane P8) — password change needs the current password; the e-mail address cannot be changed by the user |
| V7.5.2 | L2 | GAP | users cannot list or end their own other sessions; only logout and the administrator's suspension end sessions; owner: product (Ray) |
| V7.6.1 | L2 | MET | `docs/05-ARCHITECTURE.md` — provider sessions are not consumed after sign-in; eRev's own timeouts apply |
| V7.6.2 | L2 | MET | `backend/tests/api/test_session.py::test_login_sets_cookie_and_returns_csrf`; `backend/tests/api/test_oidc.py::test_get_session_lists_enabled_providers` — a session exists only after an explicit sign-in or OIDC start |

## V8 Authorization
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V8.1.1 | L1 | MET | `backend/tests/unit/test_permissions.py::test_default_roles_follow_prd_5_6`; `docs/02-PRD.md`; `docs/04-DATA_MODEL.md` — PRD §5.6 and 04 T-PLT-11 define function-level and data-level (tenant, entity) rules |
| V8.1.2 | L2 | MET | `docs/04-DATA_MODEL.md` — API-S schemas define the fields each read returns; one-time secrets are withheld after creation (D-80) |
| V8.2.1 | L1 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_every_route_guarded`; `backend/tests/api/test_mfa.py::test_ctl_033_mfa_required_permission_blocks_until_verified`; `backend/tests/api/test_users_api.py::test_viewer_forbidden_and_denied_audit` |
| V8.2.2 | L1 | MET | `backend/tests/pg/test_rls_isolation.py::test_ctl_036_cross_tenant_isolation`; `backend/tests/api/test_idor.py::test_sar_42_other_tenant_and_entity_ids_not_found`; `backend/tests/api/test_idor.py::test_sar_42_entity_excluded_ids_not_found` (written NOT RUN by lane P8); `backend/tests/api/test_idor.py::test_sar_42_route_table_map_is_complete` |
| V8.2.3 | L2 | MET | `backend/tests/api/test_api_clients.py::test_create_client_secret_shown_once`; `backend/tests/api/test_api_clients.py::test_client_secret_not_kept_for_replay` — field-level withholding of secrets; schemas never expose hashes |
| V8.3.1 | L1 | MET | `backend/tests/pg/test_rls_isolation.py::test_rls_tn_tenant_visibility`; `backend/tests/pg/test_rls_isolation.py::test_rls_tm_user_policy`; `backend/tests/pg/test_session_guards.py::test_krn_db_04_context_free_sql_refused` — row-level security in the database plus the route guard |
| V8.4.1 | L2 | MET | `backend/tests/pg/test_rls_isolation.py::test_ctl_036_cross_tenant_isolation`; `backend/tests/pg/test_sandbox_isolation.py::test_sandbox_session_cannot_write_source` |

## V9 Self-contained tokens
eRev issues no self-contained tokens (sessions are server-side rows behind an opaque cookie; API client tokens are opaque and validated by lookup), but it RECEIVES OIDC ID tokens (`auth/oidc.py::validated_claims`), so every row below is assessed from the receiver's side (Codex production-20260922-0055 APPLICABILITY-1); the relying-party flow controls are V10.5.
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V9.1.1 | L1 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` — eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: the RS256 signature is verified against the provider's key set before any claim is read (an impostor key with the same `kid` is refused) |
| V9.1.2 | L1 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_refuses_non_rs256_tokens` — eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: relying-party verification allowlist, locally witnessed: `backend/erev_api/auth/oidc.py:56` `ID_TOKEN_ALGORITHMS: Final = ("RS256",)`, applied at `backend/erev_api/auth/oidc.py:318` `jwt.decode(id_token, key_set, algorithms=list(ID_TOKEN_ALGORITHMS))`; the witness proves BOTH refusals through `validated_claims` — an HS256-signed token and a hand-built unsigned `alg: none` compact token (empty signature) — and admits the RS256 control; the HS256 refusal alone does not isolate the allowlist from the RSA-only key set, so the widening sensitivity is carried by the witness's explicit pin `ID_TOKEN_ALGORITHMS == ("RS256",)` (supervisor's three conditions, 2026-09-21; Codex 0315 §3) |
| V9.1.3 | L1 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce`; `backend/tests/unit/test_oidc_client.py::test_sar_15_provider_urls_guarded` — eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: keys come only from the configured provider's `jwks_uri` (discovery under the SAR-15 destination guard) and are imported as the key set the decoder is given; a key the token itself would name is never consulted |
| V9.2.1 | L1 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce`; `backend/tests/unit/test_oidc_client.py::test_validated_claims_rejects_future_nbf_and_iat_within_leeway` — eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: the admissible window is `exp` (an essential claim) AND, WHEN PRESENT, `nbf` and `iat` under the 60-second `CLOCK_LEEWAY_SECONDS` — `nbf` and `iat` are not newly required claims: an expired token, a future not-before and a future issued-at are refused; a not-before inside the leeway is admitted (Codex production-20260922-0133 §6 refinement 2 and 0315 §3; witnesses only, the validator unchanged) |
| V9.2.2 | L2 | GAP | eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: the token is accepted only for the sign-in that started it (`nonce`, `iss`, `aud` essential), but its type is not validated explicitly (no `typ` header check; no `at_hash` binding), so the purpose check rests on the nonce and audience; owner: security owner (Ray) |
| V9.2.3 | L2 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` — eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: `aud` must equal this client's id (a token for another client is refused) |
| V9.2.4 | L2 | GAP | eRev issues no self-contained tokens (opaque server-side sessions, SAR-09; opaque API tokens, T-PLT-16) but RECEIVES OIDC ID tokens: the RELYING-PARTY portion is proved — a token whose `aud` is not this client is refused (`backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce`); the ISSUER's unique intended-audience policy when one key signs for several audiences, and its conditional dynamic-registration policy, are the configured identity provider's organisation evidence — not verifiable in this repository and NOT inferred from V9.2.3 (Codex production-20260922-0133 §6 P8-SOP9-V9-ISSUER-1); owner: security owner (Ray) — external applicability / evidence decision |

## V10 OAuth and OIDC
eRev is an OIDC relying party (browser sign-in through a configured provider) and the issuer of opaque client-credentials tokens for its own API clients; it is not an OpenID Provider and offers no authorization-code, refresh-token or consent flows of its own.
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V10.1.1 | L2 | MET | `backend/tests/api/test_api_clients.py::test_client_credentials_token`; `backend/tests/api/test_api_clients.py::test_bearer_requests_skip_csrf` — API tokens reach only the API; the browser holds a session cookie, never a token |
| V10.1.2 | L2 | MET | `backend/tests/api/test_oidc.py::test_state_or_nonce_mismatch_refused` — codes and ID tokens are accepted only for a flow this relying party started |
| V10.2.1 | L2 | MET | `backend/tests/api/test_oidc.py::test_state_or_nonce_mismatch_refused`; `backend/tests/unit/test_oidc_client.py::test_token_form_sends_verifier_and_referenced_secret` — `state`, `nonce` and PKCE S256 |
| V10.2.2 | L2 | MET | `backend/tests/api/test_oidc.py::test_state_or_nonce_mismatch_refused` — the callback route is per provider and the state is bound to it |
| V10.3.1 | L2 | MET | `backend/tests/api/test_api_clients.py::test_token_expiry_revocation_and_rotation` — eRev is the only issuer and consumer of its opaque API tokens |
| V10.3.2 | L2 | MET | `backend/tests/api/test_api_clients.py::test_ctl_037_approval_scope_rejected`; `backend/tests/api/test_api_clients.py::test_krn_apr_04_api_client_cannot_decide` |
| V10.3.3 | L2 | NOT_APPLICABLE | API tokens identify a service client, never a person; person identity comes from the session, not from a token |
| V10.3.4 | L2 | MET | `backend/tests/api/test_api_clients.py::test_krn_apr_04_api_client_cannot_decide` — functions needing a human step-up are refused to API clients |
| V10.4.1 | L1 | NOT_APPLICABLE | eRev's token endpoint issues client-credentials tokens only; no redirect URIs |
| V10.4.2 | L1 | NOT_APPLICABLE | no authorization codes are issued |
| V10.4.3 | L1 | NOT_APPLICABLE | no authorization codes are issued |
| V10.4.4 | L1 | MET | `backend/tests/api/test_api_clients.py::test_client_credentials_token` — only `client_credentials` is accepted |
| V10.4.5 | L1 | NOT_APPLICABLE | no refresh tokens are issued |
| V10.4.6 | L2 | NOT_APPLICABLE | no code grant is issued (PKCE as a client is V10.2.1) |
| V10.4.7 | L2 | NOT_APPLICABLE | no dynamic client registration |
| V10.4.8 | L2 | NOT_APPLICABLE | no refresh tokens are issued |
| V10.4.9 | L2 | MET | `backend/tests/api/test_api_clients.py::test_token_expiry_revocation_and_rotation` — API clients are revoked and secrets rotated by an administrator |
| V10.4.10 | L2 | MET | `backend/tests/api/test_api_clients.py::test_client_credentials_token`; `backend/tests/api/test_api_clients.py::test_client_secret_not_kept_for_replay` — client secret required at the token endpoint |
| V10.4.11 | L2 | MET | `backend/tests/api/test_api_clients.py::test_ctl_037_approval_scope_rejected` — scopes assigned per client; approval scopes refused |
| V10.5.1 | L2 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` |
| V10.5.2 | L2 | GAP | the relying party links the provider identity by verified e-mail (REQ-PLT: link only to an existing user), not by the `sub` claim; binding `sub` after the first link is a design decision; owner: security owner (Ray) |
| V10.5.3 | L2 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` — issuer checked against the configured provider |
| V10.5.4 | L2 | MET | `backend/tests/unit/test_oidc_client.py::test_validated_claims_checks_signature_issuer_audience_expiry_and_nonce` — `aud` must equal the client id |
| V10.5.5 | L2 | NOT_APPLICABLE | OIDC back-channel logout is not supported |
| V10.6.1 | L2 | NOT_APPLICABLE | eRev is not an OpenID Provider |
| V10.6.2 | L2 | NOT_APPLICABLE | eRev is not an OpenID Provider |
| V10.7.1 | L2 | NOT_APPLICABLE | no user-consent authorization flows are offered by eRev's token endpoint (client credentials only) |
| V10.7.2 | L2 | NOT_APPLICABLE | as V10.7.1: no consent flows are offered |
| V10.7.3 | L2 | NOT_APPLICABLE | as V10.7.1: no consent flows are offered |

## V11 Cryptography
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V11.1.1 | L2 | MET | `docs/05-ARCHITECTURE.md`; `docs/guides/runbook.md` — KEY-01 to KEY-10 and runbook RB-05 (key backup and rotation) define the key lifecycle |
| V11.1.2 | L2 | MET | `docs/05-ARCHITECTURE.md` — the algorithms and keys in use are enumerated (argon2id, AES-256-GCM envelope, HKDF-SHA256, HMAC-SHA256 chains, TLS at the boundary) |
| V11.2.1 | L2 | MET | `backend/tests/unit/test_keys.py::test_krn_key_04_envelope_roundtrip_and_context_binding`; `backend/tests/unit/test_keys.py::test_key_04_gcp_provider_wraps_deks_through_kms` — the `cryptography` library and Cloud KMS |
| V11.2.2 | L2 | MET | `backend/tests/pg/test_chains.py::test_p2_security_chain_verifies_across_a_key_rotation`; `backend/tests/unit/test_keys.py::test_krn_key_06_new_tenant_audit_key_id` — versioned keys; verification across rotations |
| V11.2.3 | L2 | MET | `backend/tests/unit/test_keys.py::test_krn_key_04_blob_carries_wrapped_dek_length` — 256-bit keys throughout |
| V11.3.1 | L1 | MET | `backend/tests/unit/test_keys.py::test_krn_key_04_envelope_roundtrip_and_context_binding` — AES-GCM only; no ECB, no PKCS#1 v1.5 |
| V11.3.2 | L1 | MET | `backend/tests/unit/test_keys.py::test_krn_key_04_envelope_roundtrip_and_context_binding` |
| V11.3.3 | L2 | MET | `backend/tests/unit/test_keys.py::test_krn_key_04_envelope_roundtrip_and_context_binding` — authenticated encryption with context binding |
| V11.4.1 | L1 | MET | `backend/tests/unit/test_keys.py::test_krn_key_07_hkdf_rfc5869_case_3`; `backend/tests/pg/test_chains.py::test_ctl_038_audit_append_only_and_chain` — SHA-256 family only |
| V11.4.2 | L2 | MET | `backend/tests/unit/test_passwords.py::test_verification_of_malformed_or_dummy_hash_is_false`; `backend/tests/unit/test_passwords.py::test_req_plt_004_password_policy` — argon2id |
| V11.4.3 | L2 | MET | `backend/tests/pg/test_chains.py::test_ctl_038_audit_append_only_and_chain`; `backend/tests/pg/test_chains.py::test_ctl_038_actor_tamper_detected` — SHA-256 / HMAC-SHA256 chains |
| V11.4.4 | L2 | MET | `backend/tests/unit/test_passwords.py::test_verification_of_malformed_or_dummy_hash_is_false` — argon2id with tuned parameters (SAR-06) |
| V11.5.1 | L2 | MET | `backend/tests/unit/test_totp.py::test_provisioning_uri_and_new_secret`; `backend/tests/unit/test_keys.py::test_krn_key_04_envelope_roundtrip_and_context_binding` — `secrets` / OS CSPRNG for tokens, nonces and keys |
| V11.6.1 | L2 | MET | `backend/tests/unit/test_keys.py::test_krn_key_07_hkdf_rfc5869_case_3`; `backend/tests/pg/test_chains.py::test_dg_tst_22_security_event_chain_detects_tampering` — HKDF and HMAC-SHA256; no digital signatures of our own |

## V12 Secure communication
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V12.1.1 | L1 | GAP | TLS versions at the hosted load balancer are not asserted by the Terraform policy tests; owner: deploy lane (lane-p2-hosted-providers) and self-hosters |
| V12.1.2 | L2 | GAP | cipher-suite policy at the load balancer not asserted (see V12.1.1); owner: deploy lane (lane-p2-hosted-providers) |
| V12.1.3 | L2 | NOT_APPLICABLE | no mTLS client certificates are used |
| V12.2.1 | L1 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_local_environments_allow_loopback_and_http_only`; `backend/tests/unit/test_config.py::test_krn_cfg_02_public_origin_loopback` — `https` required for public origins and outbound calls outside local environments; the client-facing TLS terminator is boundary TB-1 |
| V12.2.2 | L1 | GAP | publicly trusted certificates are a load-balancer setting not asserted by a test; owner: deploy lane (lane-p2-hosted-providers) and self-hosters |
| V12.3.1 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_scheme_credentials_and_resolution`; `backend/tests/unit/deploy/test_terraform_policy.py::test_cloud_sql_cmek_identity_bootstrap` — outbound calls are `https` only; Cloud SQL connections are TLS |
| V12.3.2 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_connects_to_the_resolved_address` — httpx verifies server certificates by default; no `verify=False` (forbidden-pattern guard) |
| V12.3.3 | L2 | MET | `backend/tests/unit/deploy/test_terraform_policy.py::test_cloud_sql_cmek_identity_bootstrap`; `backend/tests/unit/deploy/test_terraform_policy.py::test_cloud_run_invocation_policy_matrix` — internal hops are Cloud Run to Cloud SQL over TLS and IAM-authenticated invocations |
| V12.3.4 | L2 | MET | `backend/tests/unit/deploy/test_terraform_policy.py::test_cloud_run_invocation_policy_matrix` — Google-managed certificates on internal hops; no self-signed certificates |

## V13 Configuration
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V13.1.1 | L2 | MET | `docs/05-ARCHITECTURE.md`; `docs/security/SUBPROCESSORS.md` — CMP and ADP rows and the subprocessor list name every external communication |
| V13.2.1 | L2 | MET | `backend/tests/unit/test_hosted_composition.py::test_secret_references_are_pinned_never_latest`; `backend/tests/unit/deploy/test_terraform_policy.py::test_cloud_run_invocation_policy_matrix` — service identities and pinned secret references between components |
| V13.2.2 | L2 | MET | `backend/tests/unit/test_guides.py::test_dg_env_14_itgc_guide_matches_enforced_rule`; `backend/tests/architecture/test_forbidden_patterns.py::test_dg_env_14_database_administration_synonyms`; `backend/tests/pg/test_session_guards.py::test_dg_env_12_app_role_guard` — `erev_app` runs the application, `erev_owner` only migrations |
| V13.2.3 | L2 | MET | `backend/tests/unit/test_config.py::test_p2_hosted_production_starts_without_master_keys_or_owner_url`; `backend/tests/unit/test_doctor_production_checks.py::test_sar_40_production_checks` — no default credentials; production refuses missing or placeholder configuration |
| V13.2.4 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_blocked_ranges`; `backend/tests/unit/test_doctor_production_checks.py::test_sar_40_production_checks` — configured integration URLs only (`integration-urls` check) and the SSRF destination guard |
| V13.2.5 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_blocked_ranges` — as V13.2.4 |
| V13.3.1 | L2 | MET | `backend/tests/unit/test_hosted_composition.py::test_hosted_keyring_needs_no_master_key_and_reads_pinned_versions`; `backend/tests/unit/test_hosted_composition.py::test_secret_references_are_pinned_never_latest`; `backend/tests/unit/deploy/test_terraform_policy.py::test_secret_access_matrix` — Secret Manager and Cloud KMS in hosted deployments; local master keys only in `dev` |
| V13.3.2 | L2 | MET | `backend/tests/unit/deploy/test_terraform_policy.py::test_secret_access_matrix` — per-service secret access |
| V13.4.1 | L1 | MET | `backend/tests/unit/deploy/test_dockerfiles.py`; `backend/tests/unit/deploy/test_docker_build.py` — images are built from `git archive HEAD`; no `.git` in the context |
| V13.4.2 | L2 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_mocks_excluded`; `backend/tests/unit/test_config.py::test_krn_cfg_02_local_and_fake_required_outside_production` — no mocks, fake providers or debug surface under `production` |
| V13.4.3 | L2 | GAP | directory listing of the static web assets depends on the web container's server configuration; not asserted; owner: deploy lane (lane-p2-hosted-providers) |
| V13.4.4 | L2 | GAP | `TRACE` handling is a load-balancer and server property not asserted by a test; owner: deploy lane (lane-p2-hosted-providers) |
| V13.4.5 | L2 | MET | `backend/tests/unit/test_openapi_export.py::test_dg_api_10_openapi_31_document`; `backend/tests/architecture/test_routes.py::test_dg_arc_04_mocks_excluded` — the OpenAPI document is published intentionally; no monitoring endpoint beyond health probes (`/metrics` is not built) |

## V14 Data protection
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V14.1.1 | L2 | MET | `backend/tests/unit/test_privacy_classification.py::test_prv_01_every_personal_column_classified`; `backend/tests/unit/test_privacy_classification.py::test_prv_01_catalogue_covers_every_code_column` — C0–C3 classification of every column (05 PRV-01) |
| V14.1.2 | L2 | MET | `backend/tests/unit/test_privacy_classification.py::test_prv_01_entries_consistent`; `docs/05-ARCHITECTURE.md` — retention, erasure and recipient handling per class; PRV-02 to PRV-11 |
| V14.2.1 | L1 | GAP | invitation and password-reset links carry their one-time token in the URL by design (hashed at rest, expiring); session and API tokens never appear in URLs; the exception is a documented decision to take; owner: security owner (Ray) |
| V14.2.2 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — `Cache-Control: no-store` on every response; no application-level cache of tenant data |
| V14.2.3 | L2 | MET | `docs/02-PRD.md`; `backend/tests/architecture/test_network_imports.py` — no third-party trackers or outbound browser requests (REQ-SEC-008); backend network calls only from adapters |
| V14.2.4 | L2 | MET | `backend/tests/unit/test_privacy_classification.py::test_prv_01_entries_consistent`; `backend/tests/unit/test_logging.py::test_dg_log_07_guard_detects_email_value`; `backend/tests/unit/test_privacy_shred_rules.py::test_shred_refusal_order_and_rule_ids` — encryption, retention, logging and erasure per class |
| V14.3.1 | L1 | GAP | clearing authenticated data from client storage at logout (`Clear-Site-Data`) is not implemented or asserted; owner: WEB lane |
| V14.3.2 | L2 | MET | `backend/tests/api/test_security_headers.py::test_sar_20_headers_on_error_responses` — `Cache-Control: no-store` |
| V14.3.3 | L2 | GAP | browser storage holds preferences and dismissal flags only; the absence of sensitive data there is not asserted by a test; owner: WEB lane |

## V15 Secure coding and architecture
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V15.1.1 | L1 | GAP | risk-based remediation time frames for vulnerable third-party components are not documented (SAR-16 requires updates, no time frame); owner: security owner (Ray) |
| V15.1.2 | L2 | MET | `backend/tests/unit/test_licence_check.py::test_repository_dependencies_pass`; `docs/dev-guide.md` — `uv.lock` and `package-lock.json` are the inventory; `make audit-deps` (SAR-17) |
| V15.1.3 | L2 | MET | `docs/05-ARCHITECTURE.md` — job profiles, timeouts and per-tenant caps document the resource-demanding functions (JOB, PERF) |
| V15.2.1 | L1 | GAP | depends on V15.1.1 (no documented time frames to measure against); owner: security owner (Ray) |
| V15.2.2 | L2 | MET | `backend/tests/unit/test_jobs_registry.py`; `backend/tests/unit/test_upload_policy.py::test_size_limits_per_purpose` — job timeouts and caps; body and upload limits |
| V15.2.3 | L2 | MET | `backend/tests/architecture/test_routes.py::test_dg_arc_04_mocks_excluded`; `backend/tests/unit/test_config.py::test_krn_cfg_02_local_and_fake_required_outside_production` |
| V15.3.1 | L1 | MET | `backend/tests/api/test_api_clients.py::test_create_client_secret_shown_once`; `backend/tests/api/test_me.py::test_api_s_me_shape` — response schemas return the API-S field sets only |
| V15.3.2 | L2 | MET | `backend/tests/unit/test_ssrf_guard.py::test_sar_15_scheme_credentials_and_resolution` — outbound calls never follow redirects (THR-15) |
| V15.3.3 | L2 | MET | `backend/tests/unit/test_problems.py::test_krn_err_02_validation_error_field_path`; `backend/tests/unit/test_migration_schemas.py` — request models forbid unknown fields; commands accept named fields only |
| V15.3.4 | L2 | GAP | client IP propagation through trusted proxy headers is not assessed (see V4.1.3); owner: lane-p4-doctor (SOP-4) with the deploy lane |
| V15.3.5 | L2 | MET | `docs/dev-guide.md`; `backend/tests/unit/test_api_money.py` — `mypy --strict` in `make typecheck`; money and decimals are strings on the wire and `Decimal` in code |
| V15.3.6 | L2 | GAP | prototype-pollution safe patterns in the TypeScript code are not enforced by a lint rule; owner: WEB lane |
| V15.3.7 | L2 | MET | `backend/tests/unit/test_lists.py::test_dg_lst_02_fixed_direction_and_filter_literals` — query parameters are typed and allow-listed; repeated parameters are refused or take the typed list |

## V16 Security logging and error handling
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V16.1.1 | L2 | MET | `docs/dev-guide.md`; `docs/05-ARCHITECTURE.md` — DG-LOG rules and OPR-21 define the log layers, events, format and sinks |
| V16.2.1 | L2 | MET | `backend/tests/unit/test_logging.py::test_dg_log_01_json_fields` — timestamp, request id, tenant, user, route and outcome on every record |
| V16.2.2 | L2 | MET | `backend/tests/unit/test_logging.py::test_dg_log_01_json_fields` — UTC timestamps |
| V16.2.3 | L2 | MET | `docs/dev-guide.md` — stdout JSON only; the platform log sink is configured by the deployment |
| V16.2.4 | L2 | MET | `backend/tests/unit/test_logging.py::test_dg_log_01_json_fields`; `backend/tests/unit/test_logging.py::test_dg_log_06_uvicorn_records_bridged` |
| V16.2.5 | L2 | MET | `backend/tests/unit/test_logging.py::test_sar_19_secret_keys_dropped_and_messages_redacted`; `backend/tests/unit/test_logging.py::test_dg_log_07_guard_detects_email_value`; `backend/tests/unit/test_logging.py::test_dg_log_03_forbidden_keys_removed` |
| V16.3.1 | L2 | MET | `backend/tests/pg/test_chains.py::test_dg_tst_22_security_event_chain_detects_tampering`; `backend/tests/api/test_session.py::test_ctl_033_lockout_after_five_failures` — `security_event` rows for logins, failures, lockouts, MFA and resets, with the authentication method |
| V16.3.2 | L2 | MET | `backend/tests/api/test_users_api.py::test_viewer_forbidden_and_denied_audit` — a denied command is audited |
| V16.3.3 | L2 | MET | `backend/tests/pg/test_chains.py::test_dg_tst_22_security_event_chain_detects_tampering`; `docs/04-DATA_MODEL.md` — the E-79 security event kinds |
| V16.3.4 | L2 | MET | `backend/tests/pg/test_session_guards.py::test_dg_log_03_db_error_logs_no_bound_parameters`; `backend/tests/unit/test_hosted_composition.py::test_provider_outage_and_denial_fail_closed` — unexpected errors and provider failures are logged without parameters |
| V16.4.1 | L2 | MET | `backend/tests/unit/test_logging.py::test_dg_log_01_json_fields` — structured JSON; values are encoded, never concatenated into a line |
| V16.4.2 | L2 | MET | `backend/tests/pg/test_chains.py::test_ctl_038_audit_append_only_and_chain`; `backend/tests/pg/test_chains.py::test_ctl_038_actor_tamper_detected` — the audit and security chains are append-only and tamper-evident; platform logs are the deployment's |
| V16.4.3 | L2 | MET | `docs/05-ARCHITECTURE.md` — hosted deployments ship stdout to Cloud Logging (a separate service); self-hosters are told to do the same (runbook) |
| V16.5.1 | L2 | MET | `backend/tests/unit/test_problems.py::test_krn_err_03_unhandled_error_is_about_blank`; `backend/tests/unit/test_doctor_production_checks.py::test_p4b_r1_untrusted_exception_text_never_reaches_a_fail_line` — an unhandled error is a generic problem with a request id |
| V16.5.2 | L2 | MET | `backend/tests/unit/test_hosted_composition.py::test_provider_outage_and_denial_fail_closed` |
| V16.5.3 | L2 | MET | `backend/tests/unit/test_hosted_composition.py::test_malformed_or_missing_configuration_fails_closed`; `backend/tests/pg/test_session_guards.py::test_krn_db_01_normal_exit_commits_and_exception_rolls_back` — fail closed; a failed command commits nothing |

## V17 WebRTC
eRev has no real-time media component.
| ID | Level | Status | Evidence, reason or gap owner |
|---|---|---|---|
| V17.1.1 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.2.1 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.2.2 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.2.3 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.2.4 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.3.1 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |
| V17.3.2 | L2 | NOT_APPLICABLE | eRev has no real-time media, TURN, DTLS, SRTP or signalling component |

## Maintenance

- A new or changed control updates its row in the same commit as the code; `test_asvs_rows_have_status_and_evidence` checks the id set, the uniqueness, the inventory hash, the attribution, the status vocabulary and that every `MET` node id resolves.
- Applicability rulings (the `NOT_APPLICABLE` reasons), the `GAP` owners and any `ACCEPTED_RISK` need the security owner's and Ray's sign-off; nothing here is accepted by the lane.
- The penetration test of 05 SAR-43 (UI-11) and the ZAP baseline (`make zap-baseline`, supervisor-run) are measurements outside this document.
- Dependency notes as of main 90ac73bf: the SOP-4 route tests (`tests/api/test_rate_limits.py`, `test_metrics.py`) and the SOP-7 walk (`tests/domain/platform/test_audit_coverage.py`) are not on main; the rate-limit POLICY tests (`tests/unit/test_rate_limit_policy.py`) are; the file-shred chain (`files/lifecycle.py::shred_sidecar`) is on main.
