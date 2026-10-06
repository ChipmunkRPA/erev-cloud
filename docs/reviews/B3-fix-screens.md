# B3 fix pass: screen specifications and design system (slug `fix-screens`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B3 (slug `fix-screens`) |
| Date | 2026-09-12 |
| Files edited | `docs/design/SCREENS.md` (rev 1.2; revision log with tables 1.2-A and 1.2-S added); `docs/design/SCREENS_B.md` (rev 1.2; tables 1.2-A and 1.2-S); `docs/design/DESIGN_SYSTEM.md` (rev 1.1 → 1.2; revision log rows and table 1.2-DS) |
| Binding inputs | `docs/01-DECISIONS.md` D-25b, D-76, D-77; `docs/04-DATA_MODEL.md` rev 1.2 (§3 E-110 to E-124, table 3.4-R, table 10-T, table 15.4-I, §15.3, §16.0 to §16.14, table 1.2-D); `docs/reviews/B3-fix-fix-data-model.md`; `docs/05-ARCHITECTURE.md` TZ-10; `docs/dev-guide.md` DG-FE-20; `docs/accounting/POLICIES.md` POL-072 |
| Backups | `.scratch/b3-fix-screens/SCREENS.rev-before-b3.md`, `SCREENS_B.rev-before-b3.md`, `DESIGN_SYSTEM.rev1.1.md` |
| Self-check | `.scratch/b3-fix-screens/selfcheck.py`: table cell counts; undefined DS, SCR, RT, OQ, B3, RPT-R, RV, SB-R and BLK ids; 04 ids (E, API-R, API-S, T, B3-D); leftover "proposed", "R-nn" and "§14" markers; §0.8 and §0.4 chip words against DS-CMP-19; SCREENS_B inline paths against the route table. Final result: **0 findings** (268 DS ids, 87 SCR ids, 112 RT rows, 82 chip words). `endpoints_check.py`: 450 endpoints parsed from 04; the 8 unmatched mentions are parser artefacts of shorthand paths (`/test`, `/submit`, `{lock request id}`), each verified against 04 by hand. `params_check.py`: 0 query parameters outside the 04 filter columns (5 found and fixed during the pass) |

## 1. Rulings and questions → changes

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| D-25b monetary liabilities | No text of the three files says that refund liabilities, deposit liabilities or consideration payable stay at historical rates; SF-05:close-run already has the "FX remeasurement" step and RPT-03 an FX line | not applicable |
| `SCREENS:OQ-S-01`, `OQ-S-02` | SCREENS §16 Status; SCR-IA-02 cites REQ-UX-004 as amended | applied (the register owner amended 03) |
| `SCREENS:OQ-S-03`, `R-01` to `R-40` | Every "OQ-S-03 row R-nn" and "R-nn" marker replaced by the 04 id: §1.4, §2.5, §2.6, §4.1.3, §4.1.3.1, §4.1.4, §4.1.7, §4.3 to §4.10, §5.4, §5.6, §5.8, §6.3, §6.5, §6.6, §7.5, §7.7, §8.4 to §8.6, §9.4, §10.3, §11.1 to §11.6, §12.2, §13.3 to §13.5, §14.3, §15.3, §15.4; new table 16-B maps each row to its 04 id | applied |
| `SCREENS:OQ-S-04` | SCREENS §2.5, §3.4 cite E-111 | applied |
| `SCREENS:OQ-S-05` | DESIGN_SYSTEM DS-CMP-18 "Scope of the anatomy"; ARIA label per flow | applied |
| `SCREENS:OQ-S-06` | DESIGN_SYSTEM DS-CMP-18 Upload, Map columns, Validate, Review changes, footer: immutable staging rows, read-only header match (E-119), corrections by re-upload, "Save mapping as preset" and inline editing removed (04 defines neither) | applied |
| `SCREENS:OQ-S-07` | SCREENS §11.0 cites the 04 §16.5 publish note | applied |
| `SCREENS:OQ-S-08`, `-14`, `-16`, `-19` | Defaults adopted; §16 Status only | applied |
| `SCREENS:OQ-S-09`, `-10` | §16 Status; DG-FE-02 and PRD §3 were amended by their owners | applied (status) |
| `SCREENS:OQ-S-11` | DESIGN_SYSTEM DS-CMP-01 items 5 and 6; SCREENS §1.1 reads `tenant_settings.ai_enabled` | applied |
| `SCREENS:OQ-S-12`, `SCREENS_B:OQ-B-01` | DESIGN_SYSTEM DS-CMP-19 adds 54 words; "proposed" markers removed from SCREENS §0.2, §0.8, §2.6, §11.6, §15.7 and SCREENS_B §0.4, RPT-28, §6.3, §8.5, §8.6, §13 | applied |
| `SCREENS:OQ-S-13` | DESIGN_SYSTEM DS-CMP-17 step 3 "Transaction price" | applied |
| `SCREENS:OQ-S-15` | SCREENS SCR-IA-08 cites 04 T-PLT-37 | applied |
| `SCREENS:OQ-S-17`, `SCREENS_B:OQ-B-06` | SCREENS §4.9.6; SCREENS_B §1.1 (end soft close, reopen), §1.4 cite E-110 and table 3.4-R | applied |
| `SCREENS:OQ-S-18` | §16 Status | applied (status) |
| `SCREENS:OQ-S-20` | DESIGN_SYSTEM DS-CMP-08 variants are examples | applied |
| `SCREENS:OQ-S-21` | SCREENS §13.5 cites 04 T-IMP-05 and the catalogue fallback | applied |
| `SCREENS_B:OQ-B-02` | SCREENS_B RV-05, RPT-R-08 (adds `TO_BRIDGE_DRIVERS_EQ_DIFFERENCE`), RPT-33, §4.1 cite 04 table 10-T | applied |
| `SCREENS_B:OQ-B-03` | SCREENS_B §1.2 cites E-62 and T-CLS-01 | applied |
| `SCREENS_B:OQ-B-04`, `-05`, `-12`, `-21` | Defaults adopted; §18 Status only | applied |
| `SCREENS_B:OQ-B-07` | SCREENS_B §3.2: KPI strip bound to `totals` and the functional balance check; summary grid bound to API-S-JournalRunSummary `lines[]`; new balance checks grid with `basis` (04 B3-D20) and test hook | applied; unavailable columns deferred to later (§3 below) |
| `SCREENS_B:OQ-B-08`, `-17` | SCREENS_B RPT-R-01 lists the 04 `parameters` keys; §1.4 | applied |
| `SCREENS_B:OQ-B-09` | SCREENS_B §5.4 cites T-RPT-01 rule 2 and T-RPT-02 | applied |
| `SCREENS_B:OQ-B-10` | SCREENS_B §6.1 cites API-S-EvidencePackCreate | applied; list filters deferred to later |
| `SCREENS_B:OQ-B-11` | SCREENS_B §6.2 cites the T-RPT-04 manifest layout | applied |
| `SCREENS_B:OQ-B-13` | SCREENS_B §7.4 binding `{contract_external_id}` → `{saved_contract_id}`; save confirmation adds the required field | applied |
| `SCREENS_B:OQ-B-14` | SCREENS_B §8.2 document text shape and accept response (E-121) | applied |
| `SCREENS_B:OQ-B-15`, `-16` | DESIGN_SYSTEM DS-CMP-25 (two-decimal confidence, "Accept" only for command-bound proposals); SCREENS_B §8.2, §8.3 | applied |
| `SCREENS_B:OQ-B-18` | SCREENS_B §8.5 roles row and kill-switch binding (T-PLT-01, 04 B3-D09) | applied |
| `SCREENS_B:OQ-B-19` | SCREENS_B §9 permission note; §9.2 to §9.4 any-of permissions; API-R-20 unchanged | applied |
| `SCREENS_B:OQ-B-20` | SCREENS_B §9.9 (E-123, E-124), §9.14 (API-S-Session), §11.2, §11.3 (`memberships[].last_opened_at`) | applied; SF-23:select columns deferred to later |
| `SCREENS_B:OQ-B-22` | SCREENS_B BLK-10, BLK-13 and the cockpit binding cite `derived_blockers[]` (E-122) | applied |
| `SCREENS_B:OQ-B-23` | SCREENS_B §1.5 binding and refusal states (`results[].problem`) | applied |
| `SCREENS_B:OQ-B-24` | SCREENS_B §11.5 | applied |
| `SCREENS_B:OQ-B-25` | SCREENS_B §2.2 `gl_document_reference` | applied |
| `SCREENS_B:OQ-B-26` | SCREENS_B §8.4 | applied |
| `SCREENS_B:OQ-B-27` | DESIGN_SYSTEM new DS-CMP-32 Tour step popover; DS-VER-06; SCREENS_B §11.2, §13 | applied |
| `SCREENS_B:OQ-B-28` | SCREENS_B §12.3 bindings (§16.12 commands, lookup response, T-PLT-42) | applied |
| `SCREENS_B:OQ-B-29` "Take the tour" banner | SCREENS §2.3 region, §2.4 condition and copy, §2.5 binding, §2.9 sample world, §2.10 test hook, §0.4 SF-25 placement; SCREENS_B §11.2, §14.2, §16 J-24.2 | applied |
| `SCREENS_B:OQ-B-30` screen parameters | SCREENS SCR-URL-15 amended; SCR-URL-24 to SCR-URL-32 added; SCR-URL-20 order extended; SCREENS_B §14.3 and the route rows of §3.5, §4.1, §5.2, §5.5, §7.2, §9.3, §9.4, §10.2, §10.3 cite them | applied |
| `SCREENS_B:OQ-B-31`, `-32` | §18 Status; PRD J-18.5 and J-20.1 were amended by their owner | applied (status) |
| `DESIGN_SYSTEM:OQ-06` | DESIGN_SYSTEM DS-FMT-06 reads `ui.negative_number_style` through `GET /me` `tenant_settings.negative_number_style`; §15 Status | applied under the 04 name (not `ui.negative_money_style`; 04 B3-D01) |
| `DESIGN_SYSTEM:OQ-07` | DESIGN_SYSTEM DS-CMP-05 "Mark all as read" → `POST /me/notifications/read-all`; SCREENS §1.2 | applied |
| `05:OQ-ARC-13` (TZ-10 lint rule) | DESIGN_SYSTEM new DS-LINT-23 (`new Date(` and `Date.parse(` outside the format module; not suppressible; fixture rule); aligned with DG-FE-20 | applied |
| Brief: DS-VER-06 lists the route-error demo button | DESIGN_SYSTEM DS-VER-06; SCREENS_B §13 composition row 10 | applied |
| Brief: route table RT-99 to RT-112 against SCREENS_B §14 | Compared row by row: paths, titles, permissions identical. SCREENS_B §14 rewritten to cite RT rows without restating paths; SB-R-03 amended; the "(proposed, §14)" screen id markers replaced by SCREENS.md §0.4 citations; SCREENS §0.4 note and index row updated | applied |
| Brief: "API gap" markers | The files carried no literal "API gap" text; the markers were the "R-nn" and "OQ-B-nn" citations above, all replaced by 04 names | applied |
| Latent gaps found by `params_check.py` (not flagged as open questions) | SCREENS_B §5.1 recent runs and §8.3 earlier answers filter by creator on the client; §6.4 reads the verification by paging the list; §5.2 and RPT-R-09 carry sections as a row field; §6.1 and §8.6 filters deferred to later | applied (B3-SB01 to B3-SB05) |

## 2. Decisions taken in B3

No open question is raised (D-77). The choices are recorded in the revision logs:

| Table | Ids | Topics |
|---|---|---|
| DESIGN_SYSTEM table 1.2-DS | B3-DS01 to B3-DS08 | 04 name of the negative style key; `before` of read-all; TZ-10 as a path rule; duplicate upload refused; confidence display; extra chip words; AI state source; Sparkle import location |
| SCREENS table 1.2-S | B3-S01 to B3-S08 | Search routes from API links; dashboard parameters; deferred billing plan due date and reversed-line link; demo banner placement and persistence; SCR-URL-24 to SCR-URL-32; distinct review body; source record sync run link; lint status field |
| SCREENS_B table 1.2-S | B3-SB01 to B3-SB08 | Creator filtering on the client; verification read by paging; journal run summary scope; run data sections; deal preview external id; SF-23:select columns; multi-entity refusals |

## 3. Deferred to later

Each region below is outside 1.0 behaviour because 04 rev 1.2 returns no field or filter for it. None appears in the capture lists of SCREENS SCR-ST-20 or SCREENS_B §15, so no capture row changed.

| Region | Missing in 04 | Section |
|---|---|---|
| SF-24:results columns beyond `primary`, `secondary`, `status` (inception date, country, issue date, invoice amount) | API-S-SearchResult fields | SCREENS §1.4 |
| Billing plan due date column | API-S-ScheduleLine due date | SCREENS §4.4 |
| Link from a reversing subledger line to the reversed line | API-S-SubledgerLine `reverses_line_id` | SCREENS §4.5 |
| Journal run summary columns: account role, clearing purpose, functional debit and credit, line count | API-S-JournalRunSummary members | SCREENS_B §3.2 |
| Evidence pack list filters by kind and status | API-R-42 `kind`, `status` filters | SCREENS_B §6.1 |
| AI call log FilterBar (user, template, outcome, called) | API-R-47 model-log filters | SCREENS_B §8.6 |
| SF-23:select Industry, Roles and Source columns | API-S-Me membership fields | SCREENS_B §11.3 |
| Header sorting of report grids | `sort` on `GET /report-runs/{id}/data` | SCREENS_B §5.2, RPT-R-09 |

## 4. Cross-document residue (other owners; not edited)

| Document | Residue | Owner action |
|---|---|---|
| `docs/04-DATA_MODEL.md` | The deferred regions of §3 need API fields or filters that 04 rev 1.2 does not define; RPT-R-09 adds the row field `section` to multi-section report data, which 04 §16.9 describes only as "the definition's columns" | None under D-77; a build agent that needs them raises a Spec question in `PROGRESS.md` |
| `docs/dev-guide.md` | DG-FE-20 (ESLint, `make lint`) and DS-LINT-23 (`make design-check`) enforce the same path rule | None; the overlap is intentional |
| `docs/02-PRD.md` | J-24.1 banner copy already matches SCREENS §2.4 (register-prd fixer) | None |

## 5. Not applied

| Item | Reason |
|---|---|
| Brief's `ui.negative_money_style` literal | 04 keeps `ui.negative_number_style` (B3-D01), and D-76 adopts proposals "unless the owning document has renamed it" |
| A capture row for the SF-01 demo tour banner | Screens are captured after the journeys, when J-24 has completed the tour and the banner no longer renders; the J-24.2 journey covers it |
