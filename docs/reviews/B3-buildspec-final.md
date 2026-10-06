# B3 review: BUILD_SPEC final assembly and coverage

| Field | Value |
|---|---|
| Owner | BUILD_SPEC finisher (design phase B3, slug `bs-finish`) |
| Date | 2026-09-12 |
| Status | Review report. It records evidence and governs nothing (`docs/01-DECISIONS.md` §0). `docs/BUILD_SPEC.md` governs |
| Inputs | `docs/reviews/B3-buildspec-coverage.md` (findings BSC-01 to BSC-05); `docs/build-spec/00-header.md`, `PHASES.md`, `11-foundation-platform.md`, `12-engine.md`, `13-reference-contracts-data.md`, `14-close-reports-ai-demo-release.md`; `research-harness/buildspec/check_buildspec.py` and `selftest.py` (unchanged) |
| Outputs | `docs/BUILD_SPEC.md` (merged, authoritative); `docs/build-spec/90-appendices.md` (Appendix C); `research-harness/buildspec/merge_buildspec.py`; `research-harness/buildspec/check_merged.py`; edits to the six source files above |
| Revision | 1.0 (2026-09-12), first issue |

## Revision log

| Rev | Date | Change |
|---|---|---|
| 1.0 | 2026-09-12 | First issue: BSC-01 and BSC-02 fixed; 12 items split; merged file assembled; checks 1 to 10 at zero on the merged file; 18 sizing flags waived |

### Decisions taken in B3 (D-77)

This report takes no decision of its own. The finisher's decisions are BSF-D-01 to BSF-D-11 in the revision log of `docs/build-spec/00-header.md`, which the merged file carries in its header.

## 1. Result

`docs/BUILD_SPEC.md` is assembled and authoritative. It holds 417 items across 27 phases: 391 build items and 26 checkpoint items.

- **Checks 1 to 10: 0 gaps** on the merged file, and 0 on the sources.
- **Check 11: 18 flags, each waived** in Appendix C with its reason. No formal SZ-02 limit is waived; every item beyond one was split.
- **Reconciliation.** The merged file parses to the same 417 items, in the same order and with the same text, as the sources. `merge_buildspec.py --check` reports equality with a fresh merge.
- **Self-test.** `selftest.py` detects 21 of 21 injected defects over the edited sources.
- **G1 grep.** The REL-2 item-set grep over `docs/BUILD_SPEC.md` yields 417 unique ids, the parser's count; the header's two fenced template lines do not match it.

| Review finding | Disposition | Where |
|---|---|---|
| BSC-01 parity gates red before GPB | Fixed. The selection becomes `probe-P3-over-delivery-validation`, 94 cases, at GATE-CLO, GATE-RPS, GATE-SNP, GATE-LMG and their preambles. PHASES §1 rows GPA and GPB, §4 row GATE-GPA, the membership counts (GPA 94, GPB 28) and §9 (two `legacy_probe` rows) are amended. Sub-check 4k: 5 → 0 | BSF-D-03 |
| BSC-02 SF-21 and SF-23 without capture | Fixed. WEB-17 captures `sf-21` (`grace`, popover open); RFD-19 captures `sf-23` (`tomas`, context pill listbox open). Sub-check 5c: 2 → 0; 122 of 122 screen ids captured | BSF-D-04 |
| BSC-03 items over 12 criteria | Six split (FND-3, PLF-10, ENB-6, ENC-3, ENC-12, DIN-7). The 14 items at 13 or 14 criteria, REL-1 and REL-3 are waived | BSF-D-06; Appendix C CW-01 to CW-16 |
| BSC-04 items over 3 modules | FND-3 and CLO-13 split. PLF-13 (now PLF-14) and CLO-7 waived as integration items | Appendix C CW-17, CW-18 |
| BSC-05 SZ-02 limits | All five split or reduced: PLF-17 and CTR-12 (13 routes); WEB-13 (5 screen ids); WEB-16 (5 screen ids, placements moved to their own item); WEB-14 (X:not-found moved into that placement item) | BSF-D-06 |
| Information: assembly, PHASES §0 and §2, author revision logs | Resolved. The merge script places the sections, PHASES §0 and §2 name the real files, and the author metadata is reproduced in Appendix B | BSF-D-01, BSF-D-02 |

## 2. Check results on the merged file

Command: `python3 research-harness/buildspec/check_merged.py --json .scratch/b3-bs-finish/merged.json`. The checker read 242 input files, and its inventory names `docs/BUILD_SPEC.md` as the only phase file.

| # | Check | Gaps | Evidence | Information sub-checks |
|---|---|---:|---|---|
| 1 | Release-1.0 requirements cited and completed | 0 | 409 of 409 cited by explicit id; 409 completed exactly once, each in its PHASES §6 phase | none |
| 2 | Controls in acceptance criteria | 0 | 49 of 49 in Acceptance with a named failure-path test | 2f 3 (negative fixtures `CTL-50`, `CTL-050`) |
| 3 | Answer-key families and key ids | 0 | 27 families; 231 of 231 active keys cited by id; every selection size correct | 3j 1 (secondary family `PAR`) |
| 4 | Golden parity kinds and the parity gate | 0 | 7 of 7 kinds; 122 cases reached by filtered selections; no run selects a case before its first passing criterion | 4i 7, 4j 17, 4l 1 |
| 5 | Screen ids and route rows cited, with captures | 0 | 112 of 112 RT rows; 122 of 122 screen ids with a capture; 80 of 80 audit rows | none |
| 6 | Journeys and their steps | 0 | 26 journeys; 180 steps, 98 acceptance items, 22 alternates | none |
| 7 | Loop make targets introduced | 0 | 35 of 35 loop targets and 6 of 6 supervisor targets, each in its PHASES §13 phase | 7f 1 (FND-6 names `make dev-down` in an error message) |
| 8 | Prerequisites exist and precede | 0 | 417 items; no unknown, later or self prerequisite; every GATE range equals its phase's first and last item | 8g 170 (interface and fail-closed notes; 163 before, the increase is the new placement and capture notes) |
| 9 | Item ids unique and well formed | 0 | 417 distinct ids; 27 sections numbered as PHASES §3; one GATE per phase, last | none |
| 10 | Acceptance criteria and doc citations | 0 | Every item has the template fields, a concrete test, a cited Read and a GK gate | none |
| 11 | Sizing heuristics | 18 flags | 11a 16, 11b 2; 0 for 11c to 11j (every phase within a third of PHASES §1) | not applicable |

Waiver reconciliation: 18 flags, 18 waiver rows, 0 unwaived, 0 stale, 0 measured values differing, 0 duplicates.

## 3. Item counts per phase

"Before" is rev 1.0 of the sources, and "after" is the merged file. Counts exclude the checkpoint item, which every phase except REL adds.

| # | Phase | PHASES §1 indicative | Before | After | Change |
|---:|---|---:|---:|---:|---|
| 01 | FND | 14 | 17 | 18 | +1: FND-3 split |
| 02 | EKC | 12 | 12 | 12 | |
| 03 | PLF | 24 | 28 | 30 | +2: PLF-10 and PLF-17 split |
| 04 | WEB | 22 | 22 | 24 | +2: WEB-13 and WEB-16 split |
| 05 | ENA | 14 | 13 | 13 | |
| 06 | RFD | 20 | 25 | 25 | capture `sf-23` added |
| 07 | ENB | 12 | 12 | 13 | +1: ENB-6 split |
| 08 | ENC | 16 | 14 | 16 | +2: ENC-3 and ENC-12 split |
| 09 | END | 16 | 14 | 14 | |
| 10 | AKS | 8 | 8 | 8 | |
| 11 | CTR | 26 | 27 | 28 | +1: CTR-12 split |
| 12 | DIN | 16 | 17 | 18 | +1: DIN-7 split |
| 13 | GPA | 7 | 6 | 6 | |
| 14 | EDS | 8 | 7 | 7 | |
| 15 | CLO | 24 | 26 | 27 | +1: CLO-13 split; GATE parity selection |
| 16 | RPS | 22 | 24 | 24 | GATE parity selection |
| 17 | SNP | 6 | 5 | 5 | GATE parity selection |
| 18 | LMG | 12 | 11 | 11 | GATE parity selection |
| 19 | GPB | 4 | 4 | 4 | |
| 20 | PRP | 8 | 8 | 8 | |
| 21 | FCS | 10 | 8 | 8 | |
| 22 | AIX | 12 | 12 | 12 | |
| 23 | SOP | 10 | 9 | 9 | |
| 24 | DMO | 34 | 34 | 34 | |
| 25 | PRF | 6 | 6 | 6 | |
| 26 | DEP | 8 | 8 | 8 | |
| 27 | REL | 3 | 3 | 3 | |
| | **Total** | **374** | **380** | **391** | +11 build items; 26 checkpoints unchanged; 406 → 417 items |

### 3.1 Splits

| Before | After | Cause | Completing requirements after the split |
|---|---|---|---|
| FND-3 Canonical hashing, keys and secrets | FND-3 Canonical hashing and the secrets check; FND-4 Keys, secrets and envelope encryption | 18 criteria, 5 modules | REQ-SEC-003 in FND-4 |
| PLF-10 Approval engine, stale invalidation and delegation | PLF-10 Approval requests, steps, decisions and the self-approval block; PLF-11 Stale invalidation, withdrawal, bulk approval and delegated decisions | 17 criteria | REQ-PLT-011 in PLF-10; REQ-PLT-014 in PLF-11 |
| PLF-17 Roles, role assignments and separation-of-duties API | PLF-18 Permissions, roles and role assignments API; PLF-19 Separation-of-duties rules and exceptions API | 13 routes | none (contributions only, as before) |
| WEB-13 MFA enrolment, password change, invitation acceptance and password reset screens | WEB-13 Invitation acceptance and MFA enrolment screens; WEB-14 Password change and password reset screens | 5 screen ids | REQ-PLT-005 in WEB-13; REQ-SEC-004 in WEB-14 |
| WEB-14 Approvals inbox and request detail | WEB-15, the same title, without X:not-found | 5 screen ids | REQ-PLT-013, REQ-UX-012 (unchanged) |
| WEB-16 Settings index, notification preferences and shell placement captures | WEB-17 Settings index, notification preferences and the notifications popover capture; WEB-18 Shell placement captures: About, session expiry, narrow viewport and not found | 5 screen ids; BSC-02 | REQ-PLT-021 in WEB-17 |
| ENB-6 Stage 06 legacy retrospective and POB-specific VC templates, with the attribute-conflict validator | ENB-6 Stage 06 legacy retrospective template, with the attribute-conflict validator; ENB-7 Stage 06 legacy POB-specific VC template | 15 criteria | REQ-MOD-008, REQ-MOD-021 in ENB-6; REQ-TP-007 in ENB-7 |
| ENC-3 Point-in-time and output measures: control-transfer triggers, units, milestones, percent complete, bill-and-hold and repurchase outcomes | ENC-3 without units; ENC-4 Units measure: golden delivery revenue and progress edge cases | 15 criteria | REQ-REC-001, 005, 006, 012 to 015 in ENC-3; REQ-REC-004, 026 in ENC-4 |
| ENC-12 Stage 10 receivable contra, receivables, contract asset versus unbilled receivable, reclass attribution and current split | ENC-13 Stage 10 receivables, receivable contra and contract asset versus unbilled receivable; ENC-14 Stage 10 reclass attribution, netting reclass targets and current split | 19 criteria | REQ-BIL-004 in ENC-13; REQ-BIL-005, 006, 010 in ENC-14 |
| CTR-12 Estimates and portfolios | CTR-12 Estimates and estimate versions; CTR-13 Portfolios and portfolio-scoped estimates | 13 routes | REQ-TP-004, 005 in CTR-12; REQ-TP-017 in CTR-13 |
| DIN-7 Legacy silent defects made explicit and row-level messages | DIN-7 Legacy setup and SSP template defects made explicit, with row-level messages; DIN-8 Legacy progress, modification and POB-specific VC template defects made explicit | 19 criteria | REQ-DAT-005, REQ-DAT-006 in DIN-8 |
| CLO-13 GL adapter interface, CSV export, outbox relay and acknowledgements | CLO-13 GL adapter interface, CSV export and the journal export relay; CLO-14 Journal batch acknowledgements, retry and the acknowledgement lock gate | 5 modules | REQ-JE-011 to 013 in CLO-13; REQ-JE-016 in CLO-14 |

Test lines moved into the parts verbatim; no money figure was retyped. The test names that changed or were added are listed in BSF-D-07.

### 3.2 Rename map (BSF-D-05)

Ids of other phases are unchanged. The full map is in `.scratch/b3-bs-finish/renumber-map.json`; the ids below are rev 1.0 → rev 1.1.

| Phase | Renamed |
|---|---|
| FND | FND-4 to FND-17 → FND-5 to FND-18 |
| PLF | PLF-11 to PLF-16 → PLF-12 to PLF-17; PLF-17 → PLF-18 and PLF-19; PLF-18 to PLF-28 → PLF-20 to PLF-30 |
| WEB | WEB-14 → WEB-15; WEB-15 → WEB-16; WEB-16 → WEB-17 and WEB-18; WEB-17 to WEB-22 → WEB-19 to WEB-24 |
| ENB | ENB-7 to ENB-12 → ENB-8 to ENB-13 |
| ENC | ENC-4 to ENC-11 → ENC-5 to ENC-12; ENC-12 → ENC-13 and ENC-14; ENC-13, ENC-14 → ENC-15, ENC-16 |
| CTR | CTR-13 to CTR-27 → CTR-14 to CTR-28, with the migration file names (`NNNN_ctr_14_…` and later) |
| DIN | DIN-8 to DIN-17 → DIN-9 to DIN-18, with the migration file names (`NNNN_din_10_…`, `NNNN_din_12_…`) |
| CLO | CLO-14 to CLO-26 → CLO-15 to CLO-27 |

340 references in the four author files were rewritten in one pass: prerequisites, GATE ranges and membership lists, decisions and notes. The rev 1.0 revision-log rows keep their historical text.

## 4. Coverage waivers

Every waiver is a check 11 heuristic flag; no coverage or ordering gap is waived. Appendix C of `docs/BUILD_SPEC.md` holds each reason.

| Id | Sub-check | Item | Measured | Class |
|---|---|---|---|---|
| CW-01 | 11a | FND-2 | 13 criteria | One kernel area, single-assertion unit tests |
| CW-02 | 11a | FND-9 | 14 criteria | Table-driven problem and money-type tests |
| CW-03 | 11a | EKC-1 | 14 criteria | ALG-01 CHK rows over one engine module |
| CW-04 | 11a | RFD-2 | 14 criteria | One migration; four requirements completed together |
| CW-05 | 11a | RFD-11 | 13 criteria | Registry configuration, no schema |
| CW-06 | 11a | RFD-13 | 13 criteria | One SSP publication lifecycle with CHK-031 |
| CW-07 | 11a | ENB-13 | 13 criteria | One engine registry, one requirement |
| CW-08 | 11a | END-9 | 13 criteria | `compute` orchestration cannot be built in part |
| CW-09 | 11a | CTR-5 | 13 criteria | One command path and one migration |
| CW-10 | 11a | CTR-17 | 13 criteria | One modification object over one migration |
| CW-11 | 11a | DIN-6 | 13 criteria | Four template modes sharing one importer |
| CW-12 | 11a | CLO-6 | 13 criteria | One SM-07 transition group |
| CW-13 | 11a | CLO-9 | 13 criteria | One query module of journal views |
| CW-14 | 11a | LMG-10 | 14 criteria | Journey part of at most ten steps (BS-D-15) |
| CW-15 | 11a | REL-1 | 16 criteria | Release sweep; header §7 rows (BSC-03) |
| CW-16 | 11a | REL-3 | 20 criteria | Final gate; header §7 rows (BSC-03) |
| CW-17 | 11b | PLF-14 | 4 modules | Integration item: outbox, notifications and hooks (BSC-04) |
| CW-18 | 11b | CLO-7 | 4 modules | Integration item: reopen with its guards (BSC-04) |

## 5. First 10 items in order

| # | Item | Title |
|---:|---|---|
| 1 | FND-1 | Repository skeleton, toolchain and make setup |
| 2 | FND-2 | Configuration, clock and structured logging kernel |
| 3 | FND-3 | Canonical hashing and the secrets check |
| 4 | FND-4 | Keys, secrets and envelope encryption |
| 5 | FND-5 | Database sessions, role guard and test database fixtures |
| 6 | FND-6 | Migration framework, schema foundation revision and catalogue lint |
| 7 | FND-7 | Enumeration mirrors, permission catalogue and currency catalogue |
| 8 | FND-8 | Policy registry generator and registry parameter catalogue |
| 9 | FND-9 | Problem details, API money types and float-rejecting column types |
| 10 | FND-10 | Application factory, health routes and OpenAPI document |

## 6. Merged file layout (BSF-D-02)

| Part | Content | Source |
|---|---|---|
| Header §1 to §7, revision log, BSF-D decisions | Authority, gates, cross-cutting rules, template, sizing (SZ-08 added), checkpoints, release | `docs/build-spec/00-header.md` |
| §8 Phase index | 27 rows: build items, first and last item, checkpoint, source file; totals 391 and 26 | generated |
| Sections 01 FND to 27 REL | Phase preambles and items, each preceded by a source comment | the four author files |
| Appendix A Table of contents | 417 rows: order, phase, item id, title | generated |
| Appendix B Author notes and decisions taken in B3 | BS-1, BS-2, BS-3 and BS-4 metadata, revision logs and decisions, headings demoted two levels | the four author files |
| Appendix C Coverage waivers | 18 waiver rows with rules | `docs/build-spec/90-appendices.md` |

## 7. Method, limits and rerun

- **Method.**
  - The fixes and splits were applied by scratch scripts under `.scratch/b3-bs-finish/`. Each substitution asserts its occurrence count, and a placeholder copies each test line verbatim from its original item.
  - The originals are kept in `.scratch/b3-bs-finish/orig/`.
  - `check_buildspec.py` and `selftest.py` were not changed. `check_merged.py` imports the checker and substitutes only its item loader.
- **Limits.**
  - The checks prove citation, ordering and form, not that a named test asserts the right values.
  - The scope, engine and read lines of the split parts divide existing content. The new test contracts of BSF-D-07 were written in this pass and are unreviewed:
    - the delegation window check, the role assignment with an approved exception, and portfolio membership over record time;
    - the WEB-18 placement tests, whose copy comes from SCREENS_B §12.4 and SCREENS SCR-ST-07;
    - "SF-23 tomas".
  - Check 11 is heuristic (BSC-D-09).
  - The GENERATED block of `docs/reviews/B3-buildspec-coverage.md` still shows the rev 1.0 results; this pass did not rewrite that report.
  - Two generated PHASES tables carry hand amendments (PHASES "Generation" row); a regeneration by `.scratch/b3-bs-lead/phases.py` must carry them.
  - Nothing is committed (brief).
- **Rerun**, from the repository root:

```sh
python3 research-harness/buildspec/merge_buildspec.py --check
python3 research-harness/buildspec/check_merged.py --json .scratch/b3-bs-finish/merged.json
python3 research-harness/buildspec/check_buildspec.py --json .scratch/b3-bs-finish/sources.json
python3 research-harness/buildspec/selftest.py
```

Expected: equality with a fresh merge; `merged BUILD_SPEC coverage: OK`; `total gaps (checks 1-10): 0`; `21 of 21 mutations detected`.
