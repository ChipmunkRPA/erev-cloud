# B2 fix pass: requirements register and glossary (slug `fix-register`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B2 (slug `fix-register`) |
| Date | 2026-09-12 |
| Files edited | `docs/03-REQUIREMENTS.md` (rev 1.1); `docs/GLOSSARY.md` (rev 1.1) |
| Inputs | `docs/reviews/B1-consistency.md` findings B1-003, B1-004, B1-011, B1-012, B1-015, B1-016, B1-017, B1-021, B1-023, B1-024, B1-025, B1-029, B1-035, §8 Q13; 03 §11 Q1 to Q3; `docs/01-DECISIONS.md` D-11a to D-75 |
| Self-check | `.scratch/design-fix-register/self_check.py`: markdown table cell counts and undefined id references (REQ, CTL, POL, ALG, JET, CHK, E, T, D, DG, BR, SF, J, research 04 key ids, research 05 scenario ids) in both files |

Statuses: **applied**; **not applicable** (no text in these two files is affected); **deferred** (reason given). Parts of a finding owned by another document are listed as not applicable here, naming the owner.

## 1. Assigned findings

| Finding or decision | Change made (file, section, id) | Status |
|---|---|---|
| B1-003 policy keys and literals | 03 §2.1 S1 row (`billing.posting = ERP`); REQ-POL-004 (every entry cites its POLICIES §1 key); REQ-POL-005 (preset values as POL literals, POLICIES §6.3); REQ-POB-007 (`material_right.exercise` `CONTINUATION` / `MODIFICATION`); REQ-TP-002 (POL-040 `EXPECTED_VALUE`, `MOST_LIKELY_AMOUNT`); REQ-TP-009 (POL-052 `AVERAGE_CARRYING_RATE`, `CURRENT_REMAINING_RATE`); REQ-SSP-002 (E-47 literals, POL-074); REQ-CST-003 (POL-143 `STRAIGHT_LINE`, `PROPORTIONAL_TO_RELATED_REVENUE`); REQ-BK-004 (`je.posting_mode = DELTA`); REQ-BIL-002, REQ-BIL-008, REQ-BIL-011 (`billing.posting`, `ERP`, `ENGINE`). GLOSSARY: "Billing posting", "Accounts receivable", "Adjustment journal", "Gross journal", "Material right" | applied. PRD §1.1, 04 §2.1 and POL-074 parts: not applicable here (PRD, 04, POLICIES owners) |
| B1-004 ratable conventions | 03 REQ-REC-003 cites POL-090 `DAILY`, `MONTHLY_EVEN`, `MID_MONTH` (04 E-21), POLICIES ALG-01 §2.1.3 via REQ-REC-019, ALG-11 (§2.12) and CHK-140 to CHK-145; REQ-POL-001 output "measure of progress and ratable convention (POL-091, POL-090)". GLOSSARY: new term "Ratable convention"; §4 map row uses the literals | applied. POL-090 algorithm, E-21, PRD §2.6: not applicable here |
| B1-011 demo users | 03 REQ-DEMO-005: named persona users `<name>@demo.erev` (PRD §2.3, WLD-U-01 to WLD-U-11), password only via `EREV_DEMO_PASSWORD` (`Demo1234!Demo` in `.env.example`) | applied |
| B1-012 tenant provisioning | 03 new REQ-PLT-038 (P0, 1.0): `erev tenant create` CLI plus operator-only admin API route, both running 04 §14.3 `tenant.provision`, with the BR-PLT-02 `AUTO-BOOTSTRAP` rule; §7 module 1 row; §8 counts (PLT 24/11/2/37/1/0/1/38; totals 286/114/9/409/6/19/25/434). GLOSSARY "Tenant" | applied. CLI signature publication (DG §5) and the route path (04 §15.3): not applicable here |
| B1-015 counter-entry roles, D-14a | 03 REQ-REF-008 (33-value E-01; `clearing_purpose` E-109 required for BILLING_CLEARING); REQ-TP-008 (COST_OF_REVENUE); REQ-TP-015 (RECEIVABLE_CONTRA under `ENGINE`); REQ-REC-007 (COST_OF_REVENUE for uninstalled materials); REQ-CST-002 (CONTRACT_COST_CLEARING); REQ-REC-015 and REQ-BK-007 (reserved FINANCING_OBLIGATION, RETAINED_EARNINGS); §6.8 topside row; §11 Q1. GLOSSARY: "Account role", "Account mapping"; new terms "Billing clearing", "Clearing purpose", "Contract cost clearing", "Cost of revenue", "Receivable contra", "Financing obligation (reserved role)", "Retained earnings (reserved role)" | applied (RECEIVABLE_CONTRA included per D-14a, departing from the B1-015 default) |
| B1-016 upload limits | 03 REQ-SEC-012 per-purpose limits of 04 T-PLT-29 (`ATTACHMENT`, `SSP_STUDY` 25 MiB; `IMPORT_SOURCE` 50 MiB and 50,000 rows per sheet; `LEGACY_DATABASE` 500 MiB); REQ-PLT-035 cites the `ATTACHMENT` limit | applied. PRD NFR-50, ERR-37: not applicable here |
| B1-017 G4 corpus scope | 03 new §12 "G4 coverage lists": list A (49 research 05 §26 scenarios of D01, D02, D04, D05, D08, D12), list B (46 research 04 topics §1.1 to §13 with mechanical conditions), list C (every POLICIES CHK id, snapshot by family); §1.4 `AK-FAM` hint points to §12 | applied. DG-AK-33 implementation and the answer-key README: not applicable here |
| B1-021 range policy | 03 REQ-SSP-005 cites POL-071 and POL-072 registry values at levels T, E, P; GLOSSARY "SSP range and range policy" | applied |
| B1-023 series | 03 REQ-POB-003, REQ-POB-005 (distinctness `series` with `series_increment_unit`, no flag), REQ-POL-001, REQ-MIG-006. GLOSSARY "Distinct", "Series", §5 SKU attributes | applied |
| B1-024 MFA rule | 03 REQ-PLT-005 cites 04 T-PLT-11 `requires_mfa` as the sole rule | applied |
| B1-025 external id | 03 REQ-PLT-007 writes `app_user.external_id` (04 T-PLT-02) | applied |
| B1-029 vocabulary lint | 03 REQ-UX-010: union list, case-insensitive whole words, allow-list adds the SF-26 legacy-transition help catalogue | applied. DG-MK-vocab-check, DS-LINT-19: not applicable here |
| B1-035 restore cadence | 03 REQ-OPS-013: quarterly restore verification plus annual DR exercise (05 OPR-12) | applied. PRD NFR-11: not applicable here |
| B1 §8 Q13 M-RA-04 | 03 §6.8 new row: casino gaming, oil and gas, broker-dealers and depository institutions, timeshare, insurers' non-insurance fees recorded as later; §10 row | applied |
| 03 §11 Q1 | Marked "Resolved by D-75": D-14a roles (COST_OF_REVENUE, CONTRACT_COST_CLEARING instead of CONTRACT_COST_OFFSET, RECEIVABLE_CONTRA; reserved RETAINED_EARNINGS, FINANCING_OBLIGATION; `clearing_purpose`) | applied |
| 03 §11 Q2 | Marked "Resolved by D-75": `Copyright (c) 2025-2026 ChipmunkRPA`; About shows "eRev by Chipmunk Robotics"; §6.5 "Names and marks" row states the ruling | applied |
| 03 §11 Q3 | Marked "Resolved by D-75": single transaction currency per combination group accepted for 1.0; REQ-CON-019 unchanged | applied |

## 2. Decisions D-11a to D-75

| Decision | Change made | Status |
|---|---|---|
| D-11a posting composition | 03 REQ-REC-019 (C_t = round_half_up(X × f_t), bounded by A, equal to A at completion); REQ-POL-004 rounding sentence; §1.4 `AK` hint. GLOSSARY "Cumulative rounding", §2 "Posted amounts" | applied |
| D-13a registry literals | As B1-003; 03 header precedence and §1.6 A2 name POLICIES §1 as the only machine vocabulary; GLOSSARY header precedence | applied |
| D-14a account roles | As B1-015 | applied |
| D-17a DEV-002 class | GLOSSARY "Deviation". No 03 text states the approval unit | applied (GLOSSARY); not applicable (03) |
| D-21a option SSP | 03 REQ-POB-006 (incremental discount formula, POL-026), REQ-POB-007; GLOSSARY "Material right" | applied |
| D-25a refundable advances | 03 REQ-FX-002 exception, REQ-POL-004 (POL-163); GLOSSARY "FX layer", "Contract liability" | applied |
| D-30a findings | 03 REQ-DAT-005 (blocking errors vs warnings, `PROGRESS_MEMO_BLANK`, 04 §15.4 codes); GLOSSARY new term "Finding" | applied |
| D-40a SQLite | No conflict: 03 mentions SQLite only as legacy behaviour (Legacy column, §6.7) and in the legacy database import (REQ-MIG-001, REQ-MIG-004), which D-40a permits | not applicable |
| D-48a targets | 03 REQ-OPS-007 (loop and supervisor targets), REQ-CTL-003 (`make release-manifest`) | applied |
| D-72 mock adapters | 03 REQ-INT-003 (in-process under `/api/v1/__mocks__/<adapter>`, no extra ports) | applied |
| D-73 identifier authority | 03 header precedence; REQ-PLT-021 (E-69 literals), REQ-PLT-026 (§15.2 `validation-failed`), REQ-CON-004 (E-03 `SIGNIFICANT_CHANGE_FLAGGED`, the 03 part of B1-005), REQ-POB-003, REQ-POB-005 (E-105), REQ-POB-010 (E-90), REQ-SSP-002 (E-47), REQ-DAT-005 (§15.4), REQ-DAT-008 (T-PLT-31 key), REQ-CLS-011 (`is_post_reopen`); GLOSSARY header | applied |
| D-74 split contracts | 03 header precedence (ENGINE_SPEC.md with ENGINE_SPEC_B.md), §1.6 A3 and REQ-UX-020 (SCREENS.md with SCREENS_B.md) | applied |
| D-75 Q3 ratable conventions | As B1-004 | applied |
| D-75 Q5 job queues | 03 and GLOSSARY name no worker queue | not applicable |
| D-75 Q7 performance tenant | 03 REQ-CLS-014, REQ-OPS-008, REQ-OPS-009 (`perf-volume` in `erev`, `make perf-seed`, month-24 close in a sandbox copy) | applied |
| D-75 Q8 local keys | 03 REQ-SEC-003 (`EnvSecretStore`, per-tenant HKDF, `LocalKeyProvider` adapter) | applied |
| D-75 Q9 tenant provisioning | As B1-012 | applied |
| D-75 Q10 upload limits | As B1-016 | applied |
| D-75 Q11 G4 coverage lists | As B1-017 | applied |
| D-75 Q12 reopen approvers | 03 REQ-CLS-011 (`period.reopen_approve` held by Controller and Revenue Reviewer; at least one Controller) | applied |
| D-75 Q13 M-RA-04 | As B1 §8 Q13 | applied |
| D-75 POLICIES OQ-05 | 03 REQ-BIL-005 (presentation balances, gross control role); GLOSSARY "Contract asset", "Unbilled receivable", "Contract liability", "Reclass (netting reclass)" | applied |
| D-75 PRD Q1 demo users | As B1-011 | applied |
| D-75 PRD Q4 notification kinds | 03 REQ-PLT-021 lists E-69 kinds including `ITEM_APPROVED`, `PERIOD_LOCKED`, `PERIOD_REOPENED` | applied |
| D-75 PRD Q8 negative style | 03 REQ-UX-006 (default parentheses); GLOSSARY §2 | applied |
| D-75 mock ports (05 OQ-ARC-07) | As D-72 | applied |
| D-75 03 Q2 copyright, Q3 single currency | As 03 §11 Q2, Q3 | applied |
| D-75 adopted defaults touching 03 | 04 OQ-01 (REQ-PLT-007); 04 OQ-05 (REQ-JE-010 `CONTRACT_ACCOUNT_DIMENSIONS`, the 03 part of B1-020); 04 OQ-06 (REQ-SSP-005); 04 OQ-07 (REQ-POL-004); DG-OQ-06 (REQ-PLT-026); 05 OQ-ARC-01 (REQ-PLT-037 per-process limit); 05 OQ-ARC-09 (REQ-OPS-012 `GET /metrics`); POLICIES OQ-10 (REQ-CST-003 cites POL-142); POLICIES OQ-11 (REQ-RPT-009 exemptions default `DO_NOT_APPLY`, POL-201 bands); DEVIATIONS OQ-D3, OQ-D4 (REQ-DAT-005) | applied |
| D-75 other adopted defaults | 04 OQ-02; POLICIES OQ-02, 03, 04, 06 to 09, 12; DEVIATIONS OQ-D1, D2, D5 to D10; PRD Q2, Q5 to Q7, Q9; 05 OQ-ARC-02 to 06, 08; DG-OQ-01 to 05, 07 to 10; DS OQ-01 to 04. No text in these two files is affected | not applicable |
| D-75 DS OQ-05 RPO bands | Not changed: REQ-RPT-009 keeps POL-201 [12, 24], which governs values. DS OQ-05's recommended five chart bands conflict with POL-201 and with B1-031; recorded as 03 §11 Q4 | deferred (supervisor confirmation; DESIGN_SYSTEM owns B1-031) |

## 3. Deferred items and dependencies

| Item | Reason |
|---|---|
| DS OQ-05 vs POL-201 RPO time bands | A literal reading of D-75 adopts five chart bands, while POL-201 and REQ-RPT-009 default to three and B1-031 closes DS OQ-05 by rendering API bands. 03 §11 Q4 asks the supervisor to confirm B1-031 |
| §12 list C snapshot | Not deferred; noted as a dependency. CHK-138 (JET-04c) and CHK-140 to CHK-145 (ALG-11 §2.12) were verified in POLICIES rev 1.1 on 2026-09-12. List C derives from POLICIES at run time, so later CHK additions need no register amendment |
