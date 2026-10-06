# B4 post-B3 residue sweep: cross-document residue (slug `doc-residue`)

| Field | Value |
|---|---|
| Author | Principal technical writer and architect, cross-document residue sweeper (post-B3 residue sweep) |
| Date | 2026-09-12 |
| Mandate | Supervisor-directed correction of known residue so the build loop does not fail on contradictions. The design is frozen (D-77): no question is opened, and each choice takes the most reasonable default and is logged |
| Files edited | `docs/04-DATA_MODEL.md` rev 1.3; `docs/05-ARCHITECTURE.md` rev 1.3; `docs/dev-guide.md` rev 1.3 outside §9.5; `docs/03-REQUIREMENTS.md` rev 1.3; `docs/02-PRD.md` rev 1.3; `docs/design/DESIGN_SYSTEM.md` rev 1.3; `docs/design/SCREENS.md` rev 1.3 |
| Verified, not edited | `docs/GLOSSARY.md`, `docs/design/SCREENS_B.md`, `docs/design/tokens.css` (no residue found) |
| Binding inputs | `docs/reviews/B4-numeric-residue.md`; `docs/reviews/B4-requests-for-04.md`; `docs/reviews/B3-fix-*.md`; `B3-buildspec-final.md`; `B3-buildspec-coverage.md`; `docs/BUILD_SPEC.md` header (BSF-D) and Appendix B (BS1-D, B3-BS2, BS3-D, BS4-D); `docs/build-spec/PHASES.md` (BS-D) |
| Scratch | `.scratch/b4-doc-residue/`: `backup/` (pre-sweep copies), `wld_x24.py` and `wld_x24.txt` (calculator recomputation), `check_b4_doc_residue.py` (sweep self-check), copies of the six B3 checkers, run logs `run-*.txt` |
| Loop state | `git log` shows the loop at FND-4. No migration exists yet for any table touched here, and no code implements the drift test or the calculator |

## 1. Residue items → changes

### 1.1 Requests and items named in the brief

| # | Residue item | Change | Files and ids |
|---|---|---|---|
| 1 | R04-01 to R04-04 (`B4-requests-for-04.md`) | Applied verbatim: `expected_returns_amount` and `consideration_payable_amount` ≤ 0 notes; `revenue_cum` net of the JET-14 release; `tax_lines` `{tax_type, jurisdiction?, amount, principal_or_agent}` | 04 T-CON-08, T-SRC-05 |
| 2 | 04 E-01 row 29 lists zero-margin uninstalled materials under `COST_OF_REVENUE` (D-76) | Row now matches POLICIES §0.8: return-asset recognition and remeasurement (JET-07c), the warranty-claim release (JET-16), and no `COST_OF_REVENUE` line for uninstalled materials | 04 §3.1 E-01 row 29 |
| 3 | 04 §15.3 has no route for T-CLS-02 rows (BS4-D-06) | `GET, POST /close-checklist-templates`; `PATCH /close-checklist-templates/{id}` (IM-M, `If-Match`; read `config.read`, write `settings.manage`) | 04 API-R-18; T-CLS-02 purpose |
| 4 | 04 DB-07 guards only `subledger_line` (BS4-D-02) | `tg_journal_line__period_guard` applies the same state rule to `journal_line` with `EREV-LED-003` | 04 §14.1 DB-07 |
| 5 | 04 T-IMP-01 has no onboarding columns (BS3-D-25) | New paragraph: CSV v2 `contracts` template with optional `opening.<member>` columns and `opening.fair_value_contract_liability`, as the one NC-19 exception; batch parameters `onboarding.method`, `cutover_date`, `onboarding_reason`, and for acquisitions `bc.expedient_modification_aggregation` and `bc.expedient_ssp_at_acquisition`; commit appends `CONTRACT_BOOKED`, `CONTRACT_ACTIVATED`, `OPENING_BALANCE_ESTABLISHED` | 04 NC-19; T-IMP-01; T-IMP-02 `parameters`; table 15.4-C `OPENING_BALANCE_INCONSISTENT` (raised as F) |
| 6 | 04 mode (a) emits events directly (BS3-D-26) | Mode (a) events are staged until the `MIGRATION_PROMOTION` approval, which appends the three events in one transaction; E-03 approval column adds `MIGRATION_PROMOTION` | 04 T-MIG-01; §3 E-03 `OPENING_BALANCE_ESTABLISHED` |
| 7 | 04 §18 places T-INT-03 and T-IMP-05 in step 0007 (BS1-D-04, BS3-D-02, BS3-D-03) | New rule 7: T-INT-03 created in PLF; T-IMP-05 created by CTR-5 with its DIN foreign keys added later; T-REF-24 to T-REF-27 in PLF (PHASES BS-D-11) | 04 §18 rule 7 |
| 8 | 05 uses literals 04 does not publish: `AUTO_OPEN`, `PERIOD_IN_CLOSE` | `PERIOD_IN_CLOSE` added to the free-text T-PLT-17 `flags` examples; 05 SCH-05 opens periods with `reason_code` null and a fixed comment, because T-REF-07 needs no reason code for future → open | 04 T-PLT-17; 05 §5.5 rules, SCH-05 |
| 9 | dev-guide DG-AI-01 and DG-KRN-CFG-02 must force the fake provider under test, e2e and perf | Verified: both already state `EREV_ENV=test`, `EREV_ENV=e2e` and `EREV_PERF_RUN=1` (rev 1.2). No change | dev-guide DG-AI-01, DG-KRN-CFG-02 |
| 10 | ERR and IMP copy drift test (PRD Q12) | Verified DG-ARC-13 exists. Amended: ERR-05 and ERR-35 are convention rows (BS1-D-09); IMP ids match `^IMP-\d{2,3}$` so IMP-100 to IMP-105 count | dev-guide DG-ARC-13 |
| 11 | 05 "until OQ-ARC-10 is ruled" in PERF-01, PERF-02, PERF-20, §2.3 | Verified absent (the B3 architecture pass removed it). No change | 05 PERF-01, PERF-02, PERF-20, §2.3 |
| 12 | 05 UPL-06 and RCP-20 codes | UPL-06 already cites `FORMULA_NO_CACHED_VALUE`; RCP-20 now names `TRACE_TOO_LARGE` beside the §3.9 row | 05 RCP-20 |
| 13 | 05 stage-12 D-25b wording against ENGINE_SPEC_B | Aligned with S12-R-19 (layers at spot on recognition, JET-10d difference), S12-R-20 (settlements remeasured to spot; criteria met creates a contract-liability layer at the transfer-date spot) and S12-R-21 (consideration payable stays open) | 05 RCP-07, EMOD-14, §3.6.4 and §3.6.7 foreign currency rows |
| 14 | 03 REQ-MOD-021 wording | Verified: already `MOD_ATTRIBUTE_CONFLICT` (`ERROR`) blocking the upload. No change | 03 REQ-MOD-021 |
| 15 | PRD WLD-X-24 / J-02.2 count "reported as 16, not 17" | Recomputed (section 2). J-02.2's 17 of 39 inside 96,050.00 to 129,950.00 (43.6%) is correct. The 16 is the count inside 95,200.00 to 128,800.00: before the exclusion 16 of 40 (40.0%), now in WLD-X-24 and J-02.1; for the J-02.5 publication coverage 16 of 39 (41.0%), replacing 43.6% | PRD WLD-X-24, J-02.1, J-02.2, J-02.5; SCREENS §11.4, §11.5 |
| 16 | PRD IMP copy for every §15.4 code added in 04 rev 1.2 | IMP-97 to IMP-105 for `REASON_CODE_NOT_ALLOWED`, `DEAL_PREVIEW_SAVE_NOT_ALLOWED` (15.4-D) and the seven 15.4-I checklist codes (messages = SCREENS §4.9.8); intro and §9 Q12 updated | PRD §5.5, §9 Q12 |
| 17 | PRD figures changed by B4-numeric-residue | Verified none: no PRD or SCREENS text cites CHK-029, CHK-060, CHK-133, CHK-136, CHK-137, JET-09c or S3-EX26 figures; K-05 and K-06 are unaffected | PRD; SCREENS |
| 18 | DESIGN_SYSTEM DS-LINT number for TZ-10 | Verified DS-LINT-23 exists (B3). 05 TZ-10 and DG-FE-20 now cite it | 05 TZ-10; dev-guide DG-FE-20 |
| 19 | DESIGN_SYSTEM OQ-06 names `ui.negative_money_style` | Proposal cell names `ui.negative_number_style`; resolution cell no longer names the unpublished key | DESIGN_SYSTEM §15 OQ-06 |
| 20 | SCREENS R-12 binds `status_label` | §4.4 renders `status` literals as DS-CMP-19 chips "In progress", "Met", "Shortfall" plus "billable at <status_date>"; tables 16-A and 16-B rows R-12 bind `status`; DS-CMP-19 gains "Met" (positive) and "Shortfall" (warning) | SCREENS §4.4, table 16-A, table 16-B; DESIGN_SYSTEM DS-CMP-19 |

### 1.2 Other mechanical residue

| # | Source | Residue | Change | Files and ids |
|---|---|---|---|---|
| 21 | B4-numeric R-COST-03 | Impairment formula uncapped | Capped at the carrying amount; asset floors at 0.00 | 05 §3.6.1; 03 REQ-CST-004 |
| 22 | B4-numeric R-SFC-04, R-SFC-05 | 05 schedule construction silent on month count and suspension | m(a, b) month-end count; S04-R-12a suspended accretion | 05 §3.6.3 Schedule construction |
| 23 | B4-numeric R-SFC-05 | 05 and B3D-ARC-07 call S3-EX26 a documentation example with no key | Both acceptance rows cite key `SFC-S3-EX26-RETURN-RIGHT`; B3D-ARC-07 marked superseded | 05 §3.6.3, §3.6.4 Acceptance; B3D-ARC-07 |
| 24 | B4-numeric R-SGN-01, R-RET-01 | 05 returns rows silent on memo sign and Y + E basis | `expected_returns_amount` ≤ 0; memo = −Σ round(r × (Y + E)) | 05 §3.6.4 Measurement, Persisted state |
| 25 | BS4-D-03, BS4-D-04 | T-CLS-01 silent on observation steps, `LOCK` step and freeze hashes | Observation steps; `LOCK` stays `PENDING`; run `SUCCEEDED` after steps 1 to 13; `counts.datasets` | 04 T-CLS-01 |
| 26 | BS4-D-16 | 05 PERF-01 and DG-PERF-02 describe a one-pass measurement that exports and acknowledges inside the run | Two-pass measurement; wall time to the last second-pass `DATASET_FREEZE` | 05 PERF-01; dev-guide DG-PERF-02 |
| 27 | BS4-D-07 | Checklist waiver subject unnamed | `EXCEPTION_WAIVER` covering `close_checklist_item`, routed to `exception.waive` held by another user | 04 §16.8 waive row |
| 28 | BS4-D-08 | 04 §16.8 `request-lock` refusal says `invalid-transition` | 409 `close-gates-failed`, one `errors[]` entry per failing gate | 04 §16.8 |
| 29 | BS4-D-11 | Scenario creation job purpose unnamed | `SANDBOX_COPY` creates the scenario tenant | 04 T-PLT-34 `purpose` |
| 30 | BS1-D-05, BS4-D-09 | 04 T-REF-26 lists fields only for `POB_ASSIGNMENT` | Fields for `APPROVAL_ROUTING` and `AUTO_APPROVAL` | 04 T-REF-26 `conditions` |
| 31 | BS3-D-15 | T-REF-34 `source_ref_id` has no rule for pool-file observations | uuid5 reference | 04 T-REF-34 |
| 32 | BS1-D-36 | 04 and 05 say api and worker serve `/metrics` | api process only; worker figures read from the database | 04 API-R-53; 05 §7.4; 03 REQ-OPS-012 |
| 33 | BS1-D-07 | 05 SAR-08 argon2 parameters differ from DG-KRN-AUTH-06 | 05 cites the DG-KRN-AUTH-06 defaults | 05 SAR-08 |
| 34 | BS1-D-08 | 05 NTR-11 header `Erev-Signature` | `X-Erev-Signature` (DG-KRN-EVT-07) | 05 NTR-11 |
| 35 | BS1-D-10 | 05 OPR-23 silent on the `readyz` failure body | 503 JSON body, not a problem response | 05 OPR-23 |
| 36 | BS1-D-12 | DG-RUN-20 throws on every Vite config load, so `vite build` would fail | Throws only when a dev or preview server starts | dev-guide DG-RUN-20 |

### 1.3 Decisions taken in the sweep (D-77)

| # | Decision | Rationale | Where logged |
|---|---|---|---|
| B4-DR-01 | `PERIOD_IN_CLOSE` joins the free-text `flags` examples; `AUTO_OPEN` is withdrawn from 05, not added to E-110 | Neither changes a type; T-REF-07 requires no reason code for future → open | 04 rev 1.3 row; 05 rev 1.3 decisions row |
| B4-DR-02 | The `opening.*` multi-obligation refusal reuses `OPENING_BALANCE_INCONSISTENT` (raised as F, stage cross-row) | A new code would need a §15.4 row, an IMP row and a drift update; IMP-92 `<rule detail>` names the column | 04 rev 1.3 row; table 15.4-C |
| B4-DR-03 | J-02.5 coverage counts the non-excluded observations of the linked calculator run inside the published range | 04 T-REF-33 `inside_count` counts non-excluded observations; POLICIES §3.3 measures c over [lo, hi] | PRD rev 1.3 row |
| B4-DR-04 | IMP ids continue past 99; DG-ARC-13 accepts `^IMP-\d{2,3}$` | Renumbering existing ids is forbidden, and a second id family would split the catalogue | PRD and dev-guide rev 1.3 rows |
| B4-DR-05 | Chip "Met" positive with CheckCircle; "Shortfall" warning with WarningCircle | Tones of the nearest existing states ("Satisfied", "Not mapped") | DESIGN_SYSTEM rev 1.3 row |
| B4-DR-06 | 05 PERF-01 follows BS4-D-16 | The BUILD_SPEC item and DG-PERF-02 rank above 05 for test contracts (B1-008) | 05 rev 1.3 decisions row |

## 2. WLD-X-24 recomputation

Source: PRD WLD-F-18, 40 prices from 73,000.00 to 151,000.00 in steps of 2,000.00. Script: `.scratch/b4-doc-residue/wld_x24.py`, exact decimals, inclusive bounds (POLICIES §3.3).

| Case | Pool | Median | Range | Inside | Share | Document state after the sweep |
|---|---|---|---|---|---|---|
| J-02.1 calculator band | 40 | 112,000.00 | 95,200.00 to 128,800.00 | 16 (97,000 to 127,000) | 40.0% | New in WLD-X-24 and J-02.1 |
| J-02.2 band after excluding 73,000.00 | 39 | 113,000.00 | 96,050.00 to 129,950.00 | 17 (97,000 to 129,000) | 43.6% | Unchanged figures; bounds added |
| J-02.5 publication coverage, range of J-02.4 | 39 | n/a | 95,200.00 to 128,800.00 | 16 | 41.0% | Was 43.6%; corrected in PRD J-02.5 and SCREENS §11.4 |

## 3. Verification (run 2026-09-12 after the last change)

| Check | Command | Result |
|---|---|---|
| Sweep self-check | `python3 .scratch/b4-doc-residue/check_b4_doc_residue.py` | 0 reference findings (131 BUILD_SPEC decision ids resolved; ENGINE_SPEC, POLICIES, ADJUDICATION, DS and DG ids present); 0 residue-probe findings; every changed file has a rev 1.3 row; DG-ARC-13 simulation: 47 slugs with one ERR row each outside ERR-05 and ERR-35, 105 codes of tables 15.4-A onward (not H, not S) with one IMP row each, IMP-01 to IMP-105 contiguous, severities equal. 15 table-count rows reported, all identical in the pre-sweep backups (pipes inside code spans in wireframe-like rows); none introduced |
| 04 checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_check_04.py` | 0 findings; 447 ids, 47 slugs, 106 codes |
| 05 checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_selfcheck_05.py` | 0 table problems; 535 05 ids, 0 undefined; 0 missing answer-key ids; 0 unknown slugs. "D-07, D-08, D-36 not found" are artifacts: the D-number regex matches BUILD_SPEC ids BS1-D-07, BS1-D-08, BS1-D-36. The residue and literal lists are the pre-existing items the B3 author reviewed |
| SCREENS and DESIGN_SYSTEM checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_selfcheck_screens.py` | 0 findings; 268 DS ids, 87 SCR ids, 112 RT rows, 84 chip words |
| dev-guide checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_selfcheck_dg.py` | 0 table problems; 479 DG ids, 0 undefined; cross-references 0 missing except "D-09", an artifact of BS1-D-09 |
| PRD checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_prd_check.py` | 150 tables, no table problem. Six "no IMP row" problems are an artifact: its IMP regex is `IMP-\d{2}`, so it cannot see IMP-100 to IMP-105 (the sweep simulation above covers them). 8 review cases carried over from B2 |
| 03 and GLOSSARY checker (B3 copy) | `python3 .scratch/b4-doc-residue/b3_register_glossary_check.py` | 0 problems |

## 4. Not applied, and follow-ups for the supervisor

| Item | Reason | Owner |
|---|---|---|
| BUILD_SPEC FND-9 `test_dg_arc_13_imp_rows_cover_codes` states "the 96 IMP rows" | With 96 rows the test cannot pass: 9 codes of tables 15.4-D and 15.4-I had no IMP row. PRD rev 1.3 has 105 rows | Supervisor (D-70): 96 → 105 |
| BUILD_SPEC RFD-15 `test_pool_of_forty_sales`: `inside_count = 17 (prices 96,000.00 to 128,000.00 …)`, `compliance_ratio = 0.425` | The pool holds only odd thousands; the correct figures are 16 (97,000.00 to 127,000.00) and 0.40 (section 2; PRD WLD-X-24 rev 1.3) | Supervisor (D-70) |
| BUILD_SPEC DMO J-02 item (J-02.5 figure "(43.6%)") | Should read "(41.0%)" per PRD J-02.5 rev 1.3 | Supervisor (D-70) |
| BUILD_SPEC BS3-D-25 names no finding code for the `opening.*` refusal | 04 rev 1.3 names `OPENING_BALANCE_INCONSISTENT` (B4-DR-02); the DIN item may cite it | Supervisor (D-70), optional |
| Settlement record for a consideration-payable promise (B3-fix-engine-spec §4) | Adding an event would open a question (D-77); ENGINE_SPEC_B S12-R-21 governs | Supervisor |
| ENGINE_SPEC S02-R-06 reads `enforceable_consideration`, which 04 T-CON-19 does not list (B4-numeric observation b) | Adding it would change dev-guide §9.5 exact member sets and key inputs, which belong to other owners | Supervisor or answer-key owner |
| SCREENS_B RPT-R-09 row field `section` against 04 §16.9 (B3-fix-screens §4) | Owner action was "none under D-77"; a new API field would be a schema decision | Build Spec question if needed |
| B3-fix-screens §3 deferred regions | Outside 1.0 by the B3 decision | None |
| dev-guide §9.5 `tax_lines` | Owned by the numeric sweep (brief) | None |
| BUILD_SPEC decisions on which the binding documents are silent: BS1-D-24, BS1-D-25, BS1-D-27, BS1-D-28, BS1-D-29, BS1-D-31, BS3-D-16, BS3-D-21, BS4-D-13 | No contradiction; the BUILD_SPEC items govern their own acceptance | None |
| The B3 checkers' IMP regex and D-number regex | Scratch tools of other slugs; not binding | None |
