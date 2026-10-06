# B2 fix pass: `docs/dev-guide.md` (slug `fix-dev-guide`)

| Field | Value |
|---|---|
| Owner | Owner-editor, design phase B2 |
| Date | 2026-09-12 |
| File edited | `docs/dev-guide.md`, rev 1.0 → rev 1.1 (Revision log at the top of the file) |
| Inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` §7 (D-11a to D-75); `docs/reviews/B1-consistency.md`; `docs/05-ARCHITECTURE.md` §2.3, §2.8, §4, §5.3, §5.5, §5.6, §6.5, §7.3, §7.8, §10; `docs/04-DATA_MODEL.md` rev 1.1 (§14.3, §15.3 API-R-54, §15.4, E-01, E-15, E-21, E-109); `docs/03-REQUIREMENTS.md` rev 1.1 (REQ-PLT-038, REQ-UX-010); `docs/legacy/golden/deviations.json` (probe expectations) |
| Self-check | `.scratch/design-fix-dev-guide/selfcheck.py`, final run: 0 table problems (column counts, text touching a table, fences); 0 undefined DG ids; 0 cross-document ids missing from their owners (REQ, CTL, POL, CHK, E-nn, T-, API-R, API-C, SF, J, WLD, BR, LTM, E2E, 05 ids, DS, D-) |

## 1. Assigned findings

| Finding or decision | Change made (file, section, id) | Status |
|---|---|---|
| B1-002 Probe import statuses | dev-guide §9.6: DG-PAR-06 (assertion scope, upload-named expected objects such as P4 `first_2_28_upload`, `sha256`, provenance keys not asserted); new DG-PAR-10 (normative classification, `import_status_basis.e40_import_status` and `problem` cross-check, no new E-40 value); new DG-PAR-11 (finding order, `worksheet_row`, `pob` from `business_key`, extra string keys such as `blank_memos` matched in the message); new table "Probe import-status mapping" (`COMMITTED`, `COMMITTED_WITH_FINDINGS`, `REJECTED` from `INVALID` or from 409 `duplicate-import`; `error_code` = first `ERROR` finding code or `errors[0].rule_id`; `detail`); DG-KRN-ERR-05 cites `IMPORT_FILE_DUPLICATE` | Applied |
| B1-002, 05 part | 05 IPL-01 returns `errors[0].rule_id = "IMPORT_FILE_DUPLICATE"` | Not applicable: 05 owner |
| B1-008 Architecture vs dev guide | §2.3 `.env.example`: adds `EREV_RUN_DIR`, `EREV_PUBLIC_ORIGIN`, `EREV_CORS_ORIGINS`, `EREV_TRUSTED_PROXY_HOPS`, `EREV_WORKER_CONCURRENCY`, `EREV_WORKER_QUEUES`, `EREV_KEY_PROVIDER`, `EREV_EMAIL_BACKEND`, `EREV_METRICS_ENABLED`, `EREV_METRICS_TOKEN`, plus a note on the 05 variables not used (`EREV_AI_DISABLED`, `EREV_LOCAL_KEYRING_PATH`, `EREV_MOCKS_BASE_URL`); §5.1 `Settings` fields and DG-KRN-CFG-02 validations (`NoDecode` lists, origin rule, local and fake required in dev, test, e2e); DG-ENV-10 (exactly four `EREV_ENV` values; `EREV_PERF_RUN` exception); DG-ENV-17 and new §5.19 DG-KRN-KEY-01 to DG-KRN-KEY-07 (key model); DG-RUN-04 origin; performance database per Q7 (below) | Applied |
| B1-008, 05 part | 05 §2.2 to §2.4, §2.8, §3.2 ENG-02, §3.4, §5.2 ADP-15, §5.3, §5.10, §8.2 amended to the dev guide; OQ-ARC-07 withdrawn | Not applicable: 05 owner |
| B1-009 Job queues | DG-RUN-02 (no `--queues`; DG-RUN-05 inherits it); §5.12 `QueueName`, `QUEUES`, `JOB_QUEUE`, `task()` without a queue parameter, `main(queues=QUEUES)`; DG-KRN-JOB-09 (perf use of `run_inline`); new DG-KRN-JOB-10 (the 25 E-14 kinds mapped to the eight 05 §5.6 queues) and DG-KRN-JOB-11 (all queues by default; `--queues` only for the hosted split); DG-ARC-08 checks `JOB_QUEUE` | Applied |
| B1-010 Make targets | §4.1 DG-MK-00f (loop offline), DG-MK-00g (report gains `command`, `build_sha`, `worktree_dirty`; `.run/reports/` replaces `.run/gates/`), new DG-MK-00h (target classes); §4.2 new DG-MK-db-reset, DG-MK-seed step 2 uses it; §4.4 DG-MK-perf amended, new DG-MK-perf-seed and DG-MK-release-manifest; DG-MK-compose-verify and DG-MK-tf-validate moved to the new §4.5 "Supervisor targets (never run by the loop)" with DG-MK-audit-deps, DG-MK-zap-baseline, DG-MK-docker-build and DG-MK-backup; §10.1 G9 and G11 rows; DG-FORBID-07 and new DG-FORBID-12; DG-LAY-08 gitignores `release-manifest.json`; §1.1 scripts | Applied |
| B1-010, other parts | 05 replaces `make dev`, `make compose-up`, `.run/gates/`; DS OQ-04 wording | Not applicable: 05 and DESIGN_SYSTEM owners |
| B1-012 Tenant creation | New §5.20 KRN-TEN: `provision_tenant` signature, `OperatorActor`, `OperatorContext`, Typer `erev tenant create` signature, route `POST /api/v1/operator/tenants` with the 04 API-R-54 request and 201 body; DG-KRN-TEN-01 to DG-KRN-TEN-07 (04 §14.3 rows, 422 `TENANT_CODE_EXISTS` for a duplicate code, CLI JSON equal to the route body, operator session with MFA, idempotency header validated without a stored record, OpenAPI tag, tests); `require_operator()` in §5.3; DG-KRN-AUTH-03; DG-KRN-IDEM-01; DG-ARC-04; new DG-E2E-12 (fresh-tenant helper runs the CLI); §1.1 `cli.py` note. Aligned during the pass with 04 API-R-54 and §14.3, which landed concurrently (the first draft used another path and code idempotency) | Applied |
| B1-012, other parts | 03 REQ-PLT-038; 04 §14.3 invitation and `AUTO-BOOTSTRAP` rows; API catalogue row | Not applicable: 03 and 04 owners (already landed) |
| B1-029 Vocabulary lint | DG-MK-vocab-check rewritten: the 12 REQ-UX-010 terms (DS-CPY-02 "Unplanned revenue" matched through "Unplanned"), case-insensitive whole words, whitespace and apostrophe rules, docstrings excluded, allow-list with legacy column files and `frontend/src/messages/en.json` keys starting `help.legacy-transition.` (SF-26), self-test fixtures, output format; §1.1 `vocab_check_fixtures/` | Applied |
| B1-029, DS part | DS-LINT-19 references `make vocab-check` | Not applicable: DESIGN_SYSTEM owner |

## 2. Open questions and §8 questions (D-75)

| Question | Change made | Status |
|---|---|---|
| DG-OQ-01 to DG-OQ-10 | §12 gains a "Resolution (rev 1.1)" column; each row reads "Resolved by D-75" with the ruling (DG-OQ-09 also D-72) | Applied |
| B1 §8 Q5 Job queues | DG-KRN-JOB-10, DG-KRN-JOB-11, DG-RUN-02 | Applied |
| B1 §8 Q7 Performance tenant | DG-MK-perf-seed (idempotent `perf-volume` in `erev` to month 23 locked, `SANDBOX_SEED` snapshot), DG-MK-perf (restore into a `perf-run-*` sandbox, append month 24, measure there), DG-PERF-01, DG-PERF-02, DG-PERF-03 (`EREV_ENV=dev`, sandbox session), new DG-PERF-06 (isolation) and DG-PERF-07 (storage), DG-ENV-10, DG-ENV-13 | Applied |
| B1 §8 Q8 Local keys | DG-ENV-17; §5.19 `SecretStore`, `EnvSecretStore`, `KeyProvider`, `LocalKeyProvider`, `KeyRing`; HKDF-SHA256 per key id `audit-hmac:<tenant id>:<n>`; no keyring file; `make backup` copies `.env` | Applied |
| New DG-OQ-11 (operator route catalogue row) | Opened and closed within the pass: 04 API-R-54 now catalogues the route | Closed |
| New DG-OQ-12 (perf sandboxes accumulate) | Recommended default: accept for 1.0; runbook documents `make db-reset` then `make perf-seed` | Open |
| New DG-OQ-13 (D-48a "offline" vs dependency installation) | Recommended default: D-48a governs target behaviour; `make setup` and DG-ENV-08 installs are the only loop network use | Open |

## 3. Amendments D-11a to D-75

| Decision | Change made | Status |
|---|---|---|
| D-11a Posting composition | DG-KRN-MONEY-03 restated (X exact, f_t exact, A posted; C_t = round_half_up(X × f_t) bounded by A, equal to A at completion; CHK-007 example); signature comments in §5.9; DG-PAR-03 requires `posting_rule` containing `EXACT-CUM`; §9.5.9 intro | Applied |
| D-13a, D-21a Registry literals | DG-READ-03; §9.5.3 enumeration table row "Registry option literals" | Applied |
| D-14a Account roles | §9.5.3 enumeration table (33 E-01 roles, reserved roles marked; `clearing_purpose` six literals), `account_mapping.clearing_purpose?`, subledger `lines.clearing_purpose?`, DG-AK-32 checks; list verified against 04 E-01 rev 1.1 | Applied |
| D-17a Cent-difference class | DG-PAR-08 (DEV-002 class sign-off) | Applied |
| D-25a Refundable advances | No dev-guide content | Not applicable |
| D-30a Findings | DG-PAR-10 severities `ERROR` and `WARNING` | Applied |
| D-40a SQLite | New DG-LAY-11; DG-ARC-05 fails on `sqlite3` outside the allowed paths; DG-PAR-02 | Applied |
| D-48a Targets | §4.5; DG-MK-00f, DG-MK-00h; DG-FORBID-12; §10.1 G11 | Applied |
| D-72 Mock adapters | DG-API-09 (adapters, `__admin` routes, dev, test and e2e only, `include_in_schema=False`, base URL on the api port, no extra ports); DG-ARC-04; DG-KRN-AUTH-03; DG-KRN-IDEM-01 | Applied |
| D-73 Identifier authority | New §0.6 DG-READ-03; DG-KRN-ERR-05 and DG-ENG-06 cite 04 §15.4; DG-SM-01 (B1-006); §9.5.6 `exceptions` severity mapping `ERROR` ↔ `BLOCKING` (B1-014), verified against 04 §15.4; DG-FE-02 routes owned by SCREENS | Applied |
| D-74 Split contracts | New §0.6 DG-READ-01, DG-READ-02 and the DG-READ-04 reading lists; §1.1 `stages/`; §7 intro; DG-ENG-07; §8.1; DG-FE-02; DG-E2E-07 | Applied |
| D-75 Ratable conventions | §9.5.3 `pob_templates` row and enumeration table (`DAILY`, `MONTHLY_EVEN`, `MID_MONTH`); example key uses `MONTHLY_EVEN` in two places (figures unchanged) | Applied |
| D-75 Q9 Tenant provisioning | §5.20 (see B1-012) | Applied |
| D-75 Q10 Upload limits | DG-KRN-FILE-01 already applies the per-purpose T-PLT-29 limits | No change needed |
| D-75 Q11 G4 coverage lists | DG-AK-33 adds the 49 research 05 §26 scenario ids of D01, D02, D04, D05, D08, D12, and research 04 §1 to §13 through `S<n>-` ids or the tag `r04-s<n>` (research 04 has no `S13-` id). B1-017 names the dev guide as its only owner | Applied |
| D-75 Q12 Reopen approvers | No dev-guide content | Not applicable |
| D-75 Demo users (PRD Q1) | DG-MK-seed (persona users; fail without `EREV_DEMO_PASSWORD`); DG-RUN-32 (no generated passwords) | Applied |
| D-75 Negative number style (PRD Q8) | Owned by DESIGN_SYSTEM; no dev-guide rule states a single style | Not applicable |
| D-75 Mock ports (05 OQ-ARC-07) | DG-OQ-09 resolution; DG-API-09 | Applied |
| D-75 Copyright (03 Q2) | §1.1 `LICENSE` line | Applied |
| D-75 03 Q3 Single currency per group | No dev-guide content | Not applicable |
| B1-027 Id collisions (citation form) | §0.2 citation rule for `PT-`, `OQ-nn` and 05 ids | Applied |
| B1-033 Migration revisions | DG-OQ-01, DG-OQ-02 resolutions; no rule change | Applied |

## 4. Deferred or noted, not changed

| Item | Reason | Status |
|---|---|---|
| DG-PAR-03 `EXACT-CUM` precondition is red today: `deviations.json` `posting_rule` still names PJR-1 to PJR-5 | The fix is the supervisor rerun of `build_deviations.py` (B1-001 steps 2 and 3); BUILD_SPEC holds `GT:journal_entry_totals` items until then | Deferred: supervisor |
| DG-PERF-03 measurement protocol (7 endpoints, 200 requests, 4 clients) differs from 05 PERF-02 and PERF-30 (2,000 requests, concurrency 8, endpoint mix) | Not in the assigned findings; the dev guide governs test contracts (D-§0) | Deferred: supervisor decision |
| DG-PERF-02 close step list is shorter than 05 PERF-01 (export, acknowledgement, GL tie-out, `DATASET_FREEZE`) | Not in the assigned findings; D-75 Q7 changed only the database and the sandbox copy | Deferred: supervisor decision |
| DG-AI-01 forces the fake provider under `test` only; 05 AIA-02 also under `e2e` and `perf` | B1-008 assigns the alignment to 05 | Not applicable: 05 owner |
| 05 still names the keyring file, the `erev_mocks` process on 8191, `.run/gates/` and `EREV_ENV=compose` at the time of this pass | 05 owner's B1-008 and B1-010 work; the dev guide already follows D-72 and D-75 | Not applicable: 05 owner |
| DG-OQ-12, DG-OQ-13 | Genuine new items with recommended defaults | Deferred: supervisor |
