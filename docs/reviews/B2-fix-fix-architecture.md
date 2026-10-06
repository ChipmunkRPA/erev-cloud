# B2 fix pass: `docs/05-ARCHITECTURE.md` (slug `fix-architecture`)

| Field | Value |
|---|---|
| Owner | Owner-editor, design phase B2 (slug `fix-architecture`) |
| Date | 2026-09-12 |
| File edited | `docs/05-ARCHITECTURE.md`, rev 1.0 → rev 1.1 (Revision log under the header) |
| Inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` including §7 D-11a to D-75; `docs/reviews/B1-consistency.md`; `docs/reviews/B2-fix-fix-dev-guide.md`; `docs/dev-guide.md` rev 1.1; `docs/04-DATA_MODEL.md` rev 1.1 (§15.2, §15.4, E-40, E-69, T-CON-13, T-INT-01, T-PLT-31, API-C-17, API-R-53); `docs/accounting/POLICIES.md` rev 1.1 (JET-01b, JET-07, ALG-06, ALG-10); `docs/02-PRD.md` §5.4 |
| Backup | `.scratch/design-fix-architecture/05-ARCHITECTURE.rev1.0.bak.md` |
| Self-check | `.scratch/design-fix-architecture/selfcheck.py`, final run: 0 table problems; 0 undefined 05 ids (527 referenced); 0 cross-document ids missing from their owners (REQ, CTL, POL, ALG, JET, CHK, E-nn, T-, DB-, API-C, API-R, NC, TY, RLS, IM, AUD, DG-, D-, WLD, BR, PRD NTF, DS); 0 unknown problem slugs; 0 hyphenated finding codes; every rev 1.0 residue hit reviewed and confirmed to be a withdrawal note, history or PRD citation |

Statuses: **applied**; **not applicable** (no text in this file is affected, or another owner's part); **deferred** (reason given).

## 1. Assigned findings

| Finding or decision | Change made (section and id) | Status |
|---|---|---|
| B1-002 Probe import statuses | §5.5 IPL-01: a duplicate (tenant, template version, file SHA-256) returns 409 `duplicate-import` with `errors[0].rule_id = "IMPORT_FILE_DUPLICATE"`; no `file_object` or `import_upload` row, no validation job. Rules paragraph: the probe statuses `COMMITTED_WITH_FINDINGS` and `REJECTED` are the DG §9.6 (DG-PAR-10) test-side mapping; E-40 gains no value; approver rejection → `REJECTED`. IPL-05 severities (`ERROR` → `INVALID`, `WARNING` processed); IPL-07 `DIFFING`; IPL-10 `COMMITTING` (E-40 literals) | Applied |
| B1-002, other parts | DG-PAR-06, DG-PAR-10, DG-PAR-11 (dev guide); 04 §15.2 `duplicate-import` row | Not applicable: landed by other owners |
| B1-008 Process model, packaging, configuration, adapters | Header precedence row (dev guide governs paths, commands, processes, variables, test contracts). §2.1 key provider label. §2.2 CMP-02 (SQLAlchemy Core only; in-process mock routers), CMP-03, CMP-06 withdrawn, CMP-07 (`LocalKeyProvider` over `EnvSecretStore`, HKDF), CMP-08 (DG command list; no `keys init`, no `mocks`), CMP-09. §2.3 table and rules per DG-RUN-01 to DG-RUN-15 (`api.pid`, `worker.pid`, `web.pid`, `api-e2e.pid`, `worker-e2e.pid`, `web-e2e.pid`, `api-perf.pid`; PID written at spawn; 15 s stop wait; no mock ports). §2.4 PKG-01 (no `pydantic`; DG-ARC-02 allow-list), PKG-02, PKG-03 withdrawn, PKG-04 `frontend/`, PKG-05 `backend/tests/`, `scripts/`, PKG-06 (DG §6.8 architecture tests; no `import-linter`), PKG-07, PKG-08 `ENGINE_VERSION`. §2.8 intro; CFG-01 (four `EREV_ENV` values), CFG-11, CFG-12 withdrawn, CFG-15 `EREV_AI_KILL_SWITCH`, CFG-17, CFG-19 withdrawn, CFG-20, CFG-23, CFG-24, CFG-25, new CFG-26 to CFG-29. §3.2 binding signature note, ENG-02, ENG-04 (DG §5.9 helper names). §3.3 STG-01, STG-14, STG-15 domain paths. §3.4 RCP-01, RCP-07, RCP-12; §3.5 intro (stage modules under `erev_engine/stages/`); RCP-25. TXN-01 (`unit_of_work`, DG §5.18), TXN-02. §5.2 intro and ADP-15 (`backend/tests/unit/adapters/`). §5.3 ADP-20 to ADP-22 (routers under `/api/v1/__mocks__/<adapter>` in `dev`, `test`, `e2e`). §5.10 flow step 1, AIA-01 (DG §6.7 signature), AIA-02, AIA-03 (DG-AI-02 fixture path), AIA-04, AIA-08 (DG-AI-05 path), AIA-10. §6.1 asset row, TB-6; THR-05. §6.5 KEY-03 to KEY-05 (HKDF key ids), KEY-09, SAR-21, SAR-23, SAR-24. SAR-01, SAR-14, SAR-15, SAR-40. §7.1 OPR-01, OPR-03, OPR-04, OPR-06, OPR-07; OPR-16, OPR-17, OPR-23. §8.1 DPL-02, DPL-05; §8.2 DPL-10, DPL-13, DPL-15 withdrawn, DPL-16; §8.3 DPL-30, DPL-31, DPL-42. PERF-10, PERF-11, PERF-15, PERF-53, PERF-55 | Applied |
| B1-008, dev-guide part | DG §2.3 variables, DG-ENV-10, DG-ENV-17, §5.19 key model, DG-API-09 | Not applicable: landed in dev guide rev 1.1 |
| B1-009 Job queues | §5.6 intro: `JOB_QUEUE` equals the profile table (DG-KRN-JOB-10; DG-ARC-08). Verified: the 25 E-14 kinds map to the same eight queues in 05 and DG-KRN-JOB-10. The ambiguous rev 1.0 row (`RETENTION_SWEEP`, `WEBHOOK_DELIVERY`, `EMAIL_DELIVERY` → `maintenance` / `outbox`) is split into `RETENTION_SWEEP` → `maintenance` and `WEBHOOK_DELIVERY`, `EMAIL_DELIVERY` → `outbox`, as DG maps them. Closing paragraph: workers consume all eight queues by default (DG-KRN-JOB-11); `--queues` only for the hosted split (DPL-31). CMP-03, CFG-23, DPL-02, DPL-31 cite it | Applied |
| B1-010 Make targets | ARC-13 (loop targets offline per DG §4.2 to §4.4; supervisor targets DG §4.5 never run by the loop; D-48a). §2.3 `make dev-up`, `make compose-verify`. PERF-04, PERF-11 `make perf-seed`, `make db-reset`. SAR-17 `make audit-deps`; SAR-43 `make zap-baseline`; DPL-05 `make docker-build`; DPL-16 `make compose-verify`; DPL-42 `make tf-validate`; OPR-15, OPR-17 `make backup` (copies `.env`). REL-01 `make release-manifest` (DG-MK-release-manifest); REL-02 `.run/reports/<gate>/report.json` replaces `.run/gates/`, with PASS, FAIL and NOT_RUN rules; REL-04 `impact_paths` and base tag. RB-01, RB-02, RB-05; PERF-05 report path | Applied |
| B1-010, other parts | DG §4 targets; DESIGN_SYSTEM OQ-04 wording | Not applicable: other owners |
| B1-013 Notification kinds and defaults | §5.8 NTR-01 (kinds, triggers and recipients are PRD §5.4 NTF-01 to NTF-12; E-69 literals including `ITEM_APPROVED`, `PERIOD_LOCKED`, `PERIOD_REOPENED`; merge rule NTF-R1). NTR-02 (recipients from PRD §5.4; rev 1.0 list withdrawn). NTR-03 (email defaults from the PRD column seeded by 04 T-PLT-25; `CHAIN_VERIFICATION_FAILED` mandatory per NTF-R2; rev 1.0 defaults and the `APPROVAL_ASSIGNED` in-app rule withdrawn). NTR-04 (NTF-R3). JOB-07 (`JOB_FAILED` recipients per PRD NTF-05). IPL-12 (`EXCEPTION_ASSIGNED` to the integration owner) | Applied |
| B1-013, 04 part | E-69 appended kinds; T-PLT-25 seeds and CHECK | Not applicable: landed in 04 rev 1.1 |
| B1-027 Id collisions | §0.2: collision claim corrected; known collisions and citation rules (`NTF-nn` is PRD; `PT-` in 04 and POLICIES written "04 PT-…" and "POL PT-nn"; 05 ids cited as "05 <id>"; `<document>:OQ-nn`). Family `NTF-nn` renamed `NTR-nn` with unchanged numbers in §0.2, §5.8 (NTR-01 to NTR-06), §5.9 (NTR-10 to NTR-13), CFG-17, KEY-08, §11. EMOD-22 cites "POL PT-10"; SAR-13 and OQ-ARC-01 cite `04:OQ-12` | Applied |
| B1-027, POLICIES part | POLICIES §0.3 citation rules | Not applicable: landed in POLICIES rev 1.1 |

## 2. Open questions (D-75)

| Question | Change made | Status |
|---|---|---|
| OQ-ARC-01 rate-limit counter | §13 Resolution column: resolved by D-75, per-process limiting in 1.0, table later (04:OQ-12); SAR-13 judgement updated | Applied |
| OQ-ARC-02 Terraform additions | Resolved by D-75; §8.3 additions stand as artifacts only | Applied |
| OQ-ARC-03 estimate parameters | Resolved by D-75 and implemented by 04 T-CON-13 `parameters`; §3.6.4 Estimate row cites `EstimateParameters`; interim `scenarios` element withdrawn | Applied |
| OQ-ARC-04 deposit remeasurement | Resolved by D-75; §3.6.7 foreign-currency rule stands until a POL row is added | Applied |
| OQ-ARC-05 security-log retention | Resolved by D-75; PRV-09 states the ruling | Applied |
| OQ-ARC-06 anonymise and shred routes | Resolved by D-75, catalogued in 04 API-R-05 and API-R-12; PRV-07 cites the routes and `FILE_RETENTION_ACTIVE` | Applied |
| OQ-ARC-07 mock ports | Superseded by D-72 (D-75 ruling): no mock ports; §2.3 rule 1, CFG-19, DPL-15 | Applied |
| OQ-ARC-08 performance database | Resolved by D-75 Q7; PERF-01, PERF-04, PERF-05, PERF-11, PERF-15, OPR-01, OPR-04 | Applied |
| OQ-ARC-09 metrics route | Resolved by D-75; 04 API-R-53 records `GET /metrics`; §7.4 rule cites it | Applied |
| B1 §8 Q5, Q6, Q7, Q8, Q9, Q10 in 05 | Q5 §5.6; Q6 §5.3; Q7 §4; Q8 §6.5; Q9 CMP-08, SAR-24, §11 REQ-PLT-038 row; Q10 UPL-01 already per T-PLT-29 (no change needed) | Applied |
| New OQ-ARC-10 to OQ-ARC-14 | Opened with recommended defaults (§4 below) | Open |

## 3. Amendments D-11a to D-75

| Decision | Change made | Status |
|---|---|---|
| D-11a Posting composition | §3.6.8 catch-up C′_p = round(X′_p × f_p(d)) bounded by A′_p; prior-period decomposition over ΔX_p,k (ALG-10 rev 1.1); ENG-04 names `cumulative_posted` and `period_amounts` | Applied |
| D-13a Registry literals | 05 already writes `ERP` and `ENGINE` (RCP-07, EMOD-20) | No change needed |
| D-14a Account roles | §3.6.1 JET-09a credit `CONTRACT_COST_CLEARING`, failure codes, counter-entry row resolved; §3.6.4 JET-07c Cr `COST_OF_REVENUE`, JET-07d Dr `BILLING_CLEARING` (`INVENTORY`); §3.6.7 JET-01b `UNAPPLIED_CASH` | Applied |
| D-17a Cent-difference class | No 05 content | Not applicable |
| D-21a Option SSP | 05 cites POL-026, ALG-05 and the `MODIFICATION` literal; no formula text | No change needed |
| D-25a Refundable advances | No 05 content | Not applicable |
| D-30a Findings | IPL-05 severities; §3.9 `PROGRESS_MEMO_BLANK` | Applied |
| D-40a SQLite | UPL-09 reads a legacy database read-only, which D-40a permits | No change needed |
| D-48a Targets | See B1-010 | Applied |
| D-72 Mock adapters | See B1-008 (§2.2, §2.3, §2.4, §2.8, §5.3, §6.1, SAR-15, OPR, DPL-15) | Applied |
| D-73 Identifier authority | Codes renamed per 04 table 15.4-S: `COST_NO_EAC`, `COST_RELATED_POB_MISSING`, `COST_PATTERN_INVALID`, `LOSS_EAC_MISSING`, `SFC_REVIEW_REQUIRED`, `SFC_RATE_MISSING`, `SFC_SCHEDULE_UNSETTLED`, `RETURN_EXCEEDS_DELIVERED`, `REFUND_EXCEEDS_BILLED`, `RETURN_ESTIMATE_MISSING`, `BREAKAGE_EXPECTED_ZERO`, `BREAKAGE_OVER_REDEMPTION`, `ROYALTY_ACCRUAL_MISSING`, `ESTIMATE_METHOD_LOCKED`, `VC_REASSESSMENT_MISSING`, `ESTIMATE_VERSION_NOT_APPROVED`, `ESTIMATE_CONSTRAINT_RANGE`, `ENGINE_INVARIANT_VIOLATION`, `ACCOUNT_MAPPING_MISSING`, `CONTROL_TOTALS_MISMATCH`, `STALE_SOURCE_VERSION`, `SANDBOX_DETERMINISM_MISMATCH`. RCP-20 code rule. §3.9 500 `about:blank` replaces `internal-error` and `eng-internal-error`. §2.5 step 3 per API-C-17 (04:OQ-11). UPL-02 → 422 `upload-type-not-allowed`; UPL-06 code pending (OQ-ARC-12). E-40 literals in IPL rows | Applied |
| D-74 Split contracts | Header precedence; §3 intro; §3.2 note; §3.5 intro; §3.6 intro | Applied |
| D-75 Q3 ratable conventions | No convention literal in 05 | Not applicable |
| D-75 Q5, Q7, Q8, Q9 | See §2 | Applied |
| D-75 Q10 upload limits | UPL-01 and DPL-12 already per T-PLT-29 | No change needed |
| D-75 Q11, Q12, Q13; POLICIES OQ-05; negative style; copyright; single currency | No 05 content | Not applicable |
| D-75 demo users | CFG-24 (`EREV_DEMO_PASSWORD` default in `.env.example`; seed fails when absent); PERF-15 personas unchanged | Applied |
| D-75 mock ports | OQ-ARC-07 | Applied |

## 4. Additional alignments, follow-ups and deferred items

| Item | Change made or reason | Status |
|---|---|---|
| Kernel contracts (D-§0) | JOB-03 cites the DG-KRN-JOB-03 slot mechanism; SCH-01 `0 2 * * *` (DG-KRN-JOB-07); SCH-04 every minute (DG-KRN-JOB-06) | Applied |
| JOB-03 child-job exemption | Kept in 05: a close run holding a slot while it polls its children deadlocks a tenant with `platform.job_concurrency = 1` (range 1 to 16, T-PLT-31). DG-KRN-JOB-03 has no exemption | Deferred: supervisor (OQ-ARC-14) |
| Performance harness | DG-PERF-02 runs the close through `run_inline` with no worker, although RCP-19 defers child jobs; the step list, entities and endpoint protocol differ from PERF-01, PERF-02, PERF-20 and PERF-30. 05 states that the dev guide governs until a ruling | Deferred: supervisor (OQ-ARC-10) |
| Compose environment | DG-ENV-10 reads production database URLs from the secret store adapter, which compose lacks. DPL-13 uses `production` with `EREV_KEY_PROVIDER=local` as the recommended default | Deferred: supervisor (OQ-ARC-11) |
| Codes missing from 04 §15.4 | `TRACE_TOO_LARGE` (§3.9) and `FORMULA_NO_CACHED_VALUE` (UPL-06) proposed | Deferred: 04 owner (OQ-ARC-12) |
| Lints without a DG contract | SAR-18 secrets scan, TZ-09 SQL tokens, TZ-10 web `new Date(` lint | Deferred: dev-guide and DESIGN_SYSTEM owners (OQ-ARC-13) |
| AI fake provider under e2e and perf | AIA-02 states the G§5 rule; DG-AI-01 and DG-KRN-CFG-02 force `fake` only under `test` | Follow-up: dev-guide owner |
| Q&A tool use | AIA-10 judgement: single-turn retrieval, because DG §6.7 `AIRequest` has no tool fields | Applied; follow-up for the dev guide only if a later REQ needs multi-turn tools |
| Refund on termination while `NOT_A_CONTRACT` | §3.6.7 gives the refund line `clearing_purpose = UNAPPLIED_CASH`; POLICIES JET-01b has no refund row | Follow-up: POLICIES owner |
| JET-07d entry kind | §3.6.4 uses `RETURN_ASSET` (E-29); POLICIES JET-07 states no entry kind | Follow-up: POLICIES owner |
| Container entrypoints | CMP-08 records `api`, `healthcheck`, `migrate` for DPL-01, DPL-02 and DPL-11; DG §5 does not name them | Follow-up: dev-guide owner |
| Process settings | CFG-29 `EREV_ENGINE_PROCESSES`, `EREV_SQL_PROFILE` as `Settings` additions under DG §0.4, outside `.env.example` | Follow-up: dev-guide owner (DG §5.1) |
| Pre-existing internal literals | Self-check advisory: `AUTO_OPEN` (SCH-05 reason), `PERIOD_IN_CLOSE` (approval flag), `MATERIAL_RIGHT_EXPIRY` (time trigger kind), `DRY_RUN` (engine mode beyond E-87) are not 04 enumeration values. Not changed; outside the assigned findings | Deferred: 04 owner to catalogue or confirm as internal |
| Module paths outside the DG tree | `erev_api.security.ratelimit` (SAR-13), `erev_api.privacy` (PRV-01, PRV-08), `erev_api.db.instrumentation` (PERF-51) are not in DG §1.1 or the DG-LAY-03 layer list. Not changed; outside the assigned findings | Deferred: dev-guide owner |
| Readiness scope | OPR-23 `readyz` adds file-store and key-provider probes to DG-API-08 | Deferred: not in the assigned findings |
| Self-check table fixes | Pipes inside inline code escaped in SAR-19, SAR-21 and PRV-01 (rev 1.0 rows that rendered with extra cells) | Applied |
