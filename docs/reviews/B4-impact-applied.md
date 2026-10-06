# B4 BUILD_SPEC impact: application record (slug `apply-b4-impact`)

| Field | Value |
|---|---|
| Author | BUILD_SPEC maintainer (supervisor task; D-70) |
| Date | 2026-09-12 |
| Input | `docs/reviews/B4-buildspec-impact.md`: 72 replacement rows BI-01 to BI-72 over 38 items and 14 phase preambles, 6 non-item rows BN-01 to BN-06, 10 PHASES companion rows BP-01 to BP-10 |
| HEAD during application | `8a8fe9e` at start. The loop committed `27a8a5b` and `c91e9c6` (FND-8) during application; neither commit touches a `docs/` path |
| Files edited (uncommitted; no git write) | `docs/BUILD_SPEC.md`; `docs/build-spec/00-header.md`, `11-foundation-platform.md`, `12-engine.md`, `13-reference-contracts-data.md`, `14-close-reports-ai-demo-release.md`, `PHASES.md` |
| Method | Edit tool, old text to new text, applied to `docs/BUILD_SPEC.md` and the matching source in the same step. Appendix A rows edited to the text a fresh merge generates. `merge_buildspec.py` run only with `--check` |
| Scratch | `.scratch/b4-apply-impact/`: `frag.py` (old-text locator), `residue.py` (stale-literal sweep), `baseline.json`, `merged.json`, `merge_check.txt`, `check_merged.txt` |
| Result | All 88 report rows applied: BI 72 (B 36, G 11, C 25), BN 6, BP 10. Six supplementary rows S-01 to S-06 applied for uncovered occurrences of the same counts (§2.4). No row withheld. `merge_buildspec.py --check`: equal to a fresh merge. `check_merged.py`: checks 1 to 10 at 0 gaps, 18 check-11 flags reconciled with 18 waiver rows, coverage OK. Baseline before application: check 3 at 2 gaps (3b=1, 3g=1), coverage FAIL |

## 1. Loop state and build order

Rows were applied in build order, FND-9 first. PROGRESS.md "In flight" was re-read before each batch.

| Batch | PROGRESS "In flight" | Ticked | Rows applied |
|---|---|---|---|
| 1 | FND-8 | FND-1 to FND-7 | BI-01, BI-02 (FND-9) |
| 2 | FND-8 | FND-1 to FND-7 | BI-03 to BI-12 (EKC), BI-14, BI-15 (PLF) |
| 3 | (none) | FND-8 ticking | BI-13, BI-16 to BI-42 (ENA, RFD, ENC, AKS, with the GPA lines of BI-48), S-01 to S-03, BN-04 (AKS rows), BN-05, BN-06 |
| 4 | (none); Next = FND-9 | FND-1 to FND-8 (`27a8a5b`, `c91e9c6`) | BI-43 to BI-72 (CTR to REL), S-04, S-05, BN-01 to BN-03, BN-04 (EDS row), BP-01 to BP-10, S-06 |
| After verification | FND-9 (iteration 9) | FND-1 to FND-8 | none |

FND-9 moved to in flight only after BI-01 and BI-02 were in the tree. Commit `c91e9c6` "FND-8: Note supervisor FND-9 amendment in PROGRESS next step" shows that the loop read the amended FND-9 before starting it. None of the 38 affected items was ticked or in flight when its rows were applied.

## 2. Rows applied

Every BI and BN row was applied to `docs/BUILD_SPEC.md` and to the source named below. The exception is BN-04, which edits generated Appendix A text in the merged file only. BP and S-06 rows edit `docs/build-spec/PHASES.md`, which is not merged. Source abbreviations: 00 = `00-header.md`, 11 = `11-foundation-platform.md`, 12 = `12-engine.md`, 13 = `13-reference-contracts-data.md`, 14 = `14-close-reports-ai-demo-release.md`.

### 2.1 Replacement rows BI-01 to BI-72

| Id | Item | Field | Class | Source |
|---|---|---|---|---|
| BI-01 | FND-9 | Acceptance / Tests (`test_dg_arc_13_imp_rows_cover_codes`, 105 IMP rows) | B | 11 |
| BI-02 | FND-9 | Read | C | 11 |
| BI-03 | EKC phase preamble | Exit criteria (234 files) | B | 12 |
| BI-04 | EKC-4 | Scope / Paths (`month_ends_between`) | G | 12 |
| BI-05 | EKC-4 | Acceptance / Tests (new `test_month_ends_between`) | G | 12 |
| BI-06 | EKC-4 | Read | C | 12 |
| BI-07 | EKC-8 | Acceptance / Tests (`discover()` 234 paths) | B | 12 |
| BI-08 | EKC-8 | Acceptance / Tests (232 active, 227 engine runner) | B | 12 |
| BI-09 | EKC-8 | Read | C | 12 |
| BI-10 | EKC-9 | Acceptance / Tests (rejected payloads) | G | 12 |
| BI-11 | EKC-9 | Read | C | 12 |
| BI-12 | EKC-11 | Acceptance / Tests (new `test_judgement_questionnaire_enters_outcome`) | G | 12 |
| BI-13 | EKC-11 | Read | C | 12 |
| BI-14 | PLF-12 | Read | C | 11 |
| BI-15 | PLF-14 | Read | C | 11 |
| BI-16 | ENA-7 | Acceptance / Tests (signed `expected_returns_amount`) | B | 12 |
| BI-17 | ENA-7 | Acceptance / Tests (new `test_ex_04_g2_memo_on_returned_and_expected`) | G | 12 |
| BI-18 | ENA-7 | Read | C | 12 |
| BI-19 | ENA-8 | Scope / Engine (two fragments) | C | 12 |
| BI-20 | ENA-8 | Acceptance / Tests (`test_s04_r12_month_count_calendar_month_ends`) | C | 12 |
| BI-21 | ENA-8 | Acceptance / Tests (new `test_ex_04_h_accretion_suspended_while_returns_exclude_consideration`) | G | 12 |
| BI-22 | ENA-8 | Acceptance / Tests (new `test_s04_r12a_advance_payment_never_suspended`) | G | 12 |
| BI-23 | ENA-8 | Read (two fragments) | C | 12 |
| BI-24 | ENA-9 | Acceptance / Tests (signed `consideration_payable_amount`, V1) | B | 12 |
| BI-25 | ENA-9 | Read | C | 12 |
| BI-26 | RFD-15 | Acceptance / Tests (`inside_count = 16`, `compliance_ratio = 0.40`) | B | 13 |
| BI-27 | RFD-15 | Acceptance / Tests (post-exclusion band) | C | 13 |
| BI-28 | RFD-15 | Acceptance / Tests (new `test_publication_coverage_counts_linked_run`) | G | 13 |
| BI-29 | RFD-15 | Read (two fragments) | C | 13 |
| BI-30 | ENC-15 | Acceptance / Tests (new `test_ex_11_a_impairment_floor`) | G | 12 |
| BI-31 | ENC-15 | Read | C | 12 |
| BI-32 | AKS phase preamble | Gate scope (221 keys) | B | 12 |
| BI-33 | AKS-2 | Acceptance / Tests (two new bullets: CPC-CHK-133, POB-JS-05) | G | 12 |
| BI-34 | AKS-2 | Read | C | 12 |
| BI-35 | AKS-3 | Header (38 keys) | B | 12 |
| BI-36 | AKS-3 | Acceptance / Tests (two new bullets: RET-CHK-029, SFC-S3-EX26-RETURN-RIGHT) | G | 12 |
| BI-37 | AKS-3 | Acceptance / Answer keys (id added; 38 of 38; `SFC` 8) | B | 12 |
| BI-38 | AKS-3 | Acceptance / Hint closure | C | 12 |
| BI-39 | AKS-3 | Read | C | 12 |
| BI-40 | AKS-3 | Gates | B | 12 |
| BI-41 | AKS-8 | Header; Acceptance / Tests; Gates | B | 12 |
| BI-42 | GATE-AKS | Acceptance / Gates | B | 12 |
| BI-43 | CTR phase preamble | Gate scope | B | 13 |
| BI-44 | CTR-5 | Read | C | 13 |
| BI-45 | DIN phase preamble | Gate scope | B | 13 |
| BI-46 | DIN-9 | Acceptance / Tests (`tax_lines` members) | C | 13 |
| BI-47 | DIN-9 | Read | C | 13 |
| BI-48 | GPA phase preamble; GATE-GPA | Gate scope; Acceptance / Gates | B | 12 |
| BI-49 | EDS phase preamble | Gate scope | B | 12 |
| BI-50 | EDS-7 | Header; Acceptance / Answer keys | B | 12 |
| BI-51 | GATE-EDS | Exit criteria; Gates | B | 12 |
| BI-52 | CLO phase preamble | Gate scope | B | 14 |
| BI-53 | CLO-4 | Read | C | 14 |
| BI-54 | GATE-CLO | Acceptance / Gates | B | 14 |
| BI-55 | RPS phase preamble; GATE-RPS | Gate scope; Gates | B | 14 |
| BI-56 | SNP phase preamble; GATE-SNP | Gate scope; Gates | B | 14 |
| BI-57 | LMG phase preamble | Gate scope | B | 13 |
| BI-58 | LMG-6 | Acceptance / Tests (`OPENING_BALANCE_INCONSISTENT`) | C | 13 |
| BI-59 | GATE-LMG | Acceptance / Gates | B | 13 |
| BI-60 | GPB phase preamble; GATE-GPB | Gate scope; Gates | B | 12 |
| BI-61 | PRP phase preamble | Exit criteria; Gate scope | B | 12 |
| BI-62 | PRP-8 | Acceptance / Tests; Answer keys | B | 12 |
| BI-63 | GATE-PRP | Exit criteria; Gates | B | 12 |
| BI-64 | FCS phase preamble; GATE-FCS | Gate scope; Gates | B | 14 |
| BI-65 | AIX phase preamble; GATE-AIX | Gate scope; Gates | B | 14 |
| BI-66 | DMO-12 | Acceptance / Tests (J-02.1, J-02.2, J-02.5) | B | 14 |
| BI-67 | DMO-12 | Read | C | 14 |
| BI-68 | DMO-19 | Acceptance / Tests (J-11.4 status chip) | C | 14 |
| BI-69 | GATE-DMO | Acceptance / Gates | B | 14 |
| BI-70 | GATE-PRF | Acceptance / Gates | B | 14 |
| BI-71 | REL-1 | Acceptance / Tests; Answer keys | B | 14 |
| BI-72 | REL-3 | Acceptance / Tests; Answer keys | B | 14 |

### 2.2 Non-item rows BN-01 to BN-06

| Id | Location | Class | Source |
|---|---|---|---|
| BN-01 | Header table, row "Revision" (1.3) | C | 00 |
| BN-02 | Header revision log, new row 1.3 | C | 00 |
| BN-03 | Header §7, row G4 (232 at issue) | C | 00 |
| BN-04 | Appendix A rows AKS-3 (38 keys), AKS-8 (221 keys), EDS-7 (227 keys) | C | generated; merged file only |
| BN-05 | Appendix B.2, row B3-BS2-11 (221 keys) | C | 12 (author metadata) |
| BN-06 | Appendix B.2, row B3-BS2-13 (resolved by R-SGN-01) | C | 12 (author metadata) |

### 2.3 PHASES companion rows BP-01 to BP-10

| Id | PHASES location | Change |
|---|---|---|
| BP-01 | L26, BS-D-02 rationale | 188 of the 232 active keys; 192 labelled balances |
| BP-02 | L27, BS-D-03 | 234 files, 232 active; 227 engine runner |
| BP-03 | L82, §1 row PRP | 232 active keys |
| BP-04 | L104 row AKS; L122 Total row | 220 to 221; **231** to **232** |
| BP-05 | L176, L178, L180, §4 gate rows | 221 keys; 227 keys; 232 keys |
| BP-06 | L883, §8.1 row SFC | 8 and 8 |
| BP-07 | L888, §8.1 Total | **232**, **227** |
| BP-08 | L890, family codes | REC 108, RET 15, SFC 10 |
| BP-09 | L894 heading; L919 row SFC | `8.2.1 AKS: 221 keys`; SFC 8 with `SFC-S3-EX26-RETURN-RIGHT` added |
| BP-10 | L1415, audit row | 234 files: 232 active (221 AKS, 6 EDS, 5 PRP) |

### 2.4 Supplementary rows (not in the impact report)

The residue sweep found six occurrences of the same corpus counts that no row covers. Each would contradict PHASES §8.2.1 or §1 once BP-09 or BI-03 applies, so the intended change was applied and is recorded here.

| Id | Item | Field | Class (by the report's scale) | Old text | New text | Reason |
|---|---|---|---|---|---|---|
| S-01 | AKS-8 | Acceptance / Tests (`test_aks_selection_equals_phases_8_2_1`) | B | `the module constant holds the 220 ids of PHASES §8.2.1.` | `the module constant holds the 221 ids of PHASES §8.2.1.` | The constant must equal PHASES §8.2.1, which BP-09 makes 221 ids; the test could not pass as written |
| S-02 | AKS-8 | Acceptance / Answer keys | B | ``Answer keys: `make answer-keys ID=<the 220 ids of PHASES §8.2.1>` (220 pass)`` | ``Answer keys: `make answer-keys ID=<the 221 ids of PHASES §8.2.1>` (221 pass)`` | BI-41 covers Header, Tests and Gates, but not this sub-field (L5277 at `d566710`) |
| S-03 | GATE-AKS | Acceptance / Exit criteria | B | ```make answer-keys ID=<§8.2.1 ids>` reports 220 of 220 passed`` | ```make answer-keys ID=<§8.2.1 ids>` reports 221 of 221 passed`` | BI-42 covers the Gates line only (L5292 at `d566710`) |
| S-04 | GATE-CTR | Acceptance / Gates | B | `` `make answer-keys ID=<the 220 ids of PHASES §8.2.1>` `` | `` `make answer-keys ID=<the 221 ids of PHASES §8.2.1>` `` | BI-43 covers the CTR preamble only (L6060 at `d566710`) |
| S-05 | GATE-DIN | Acceptance / Gates | B | `` `make answer-keys ID=<the 220 ids of PHASES §8.2.1>` `` | `` `make answer-keys ID=<the 221 ids of PHASES §8.2.1>` `` | BI-45 covers the DIN preamble only (L6573 at `d566710`) |
| S-06 | PHASES §1 row EKC | Exit criterion (3) (L64) | C | `loading all 233 files with zero errors` | `loading all 234 files with zero errors` | Companion of BI-03: the EKC preamble "Exit criteria (PHASES §1 row EKC)" quotes this row |

## 3. Rows not applied

None. No affected item was ticked or in flight when its rows were applied (§1), so no follow-up item is needed for this report.

## 4. Adjusted matches

Every old-text fragment of the BI, BN and BP rows occurred verbatim on the line the report cites. The report was written at `d566710`, and commit `8a8fe9e` shifted no BUILD_SPEC or PHASES line. No intended change needed re-derivation. The adjustments below concern anchoring and application mode only.

| Rows | Adjustment | Reason |
|---|---|---|
| BI-05, BI-12, BI-17, BI-21 and BI-22, BI-28, BI-30, BI-33, BI-36 | Inserted by anchoring on the tail of the preceding test bullet and the head of the next line, at the sibling indentation (six spaces) | "Insert after L…" rows carry no old text |
| BI-21, BI-22 | Applied as one insertion | BI-22 is "insert after BI-21" |
| BI-29 (first fragment) | Matched as `SCREENS §11.5; PRD §2.8 WLD-X-24; PRD §2.12 WLD-F-18;` | `PRD §2.8 WLD-X-24;` also occurs in DMO-12 (BI-67) |
| BI-34 | Matched with the prefix `JET-14, JET-16, JET-17; ` | Uniqueness guard |
| BI-35, BI-50 (Header) | Matched with the trailing period of the title | The titles also occur in Appendix A without a period (BN-04) |
| BI-41 (Header) | Matched as `**AKS-8 Engine-runner corpus sweep (220 keys)` | The title also occurs in Appendix A (BN-04) |
| BN-02 | Row inserted after the rev 1.1 row, with the report's escaped table pipes restored | The report escapes pipes inside its table cells |
| BN-04 | Appendix A rows edited by hand to the generated text; `--check` confirms equality with a fresh merge | Rows are applied with the Edit tool; merge write mode was not used |
| BP-04 (Total row) | Matched as `\| **26** \| **231** \| **122** \| **41** \|` | `**231**` also occurs in the §8.1 Total row (BP-07) |
| BP-08 | Applied as one phrase: `POS 63, REC 107, RET 14, RND 31, ROY 7, SFC 9, SSP 17` to `POS 63, REC 108, RET 15, RND 31, ROY 7, SFC 10, SSP 17` | Three fragments on one line |
| BP-09 (row SFC) | Matched as `\| SFC \| 7 \| SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE,` | `\| SFC \| 7 \| ` also occurred in the §8.1 table (BP-06) |

`replace_all` was used only where every occurrence of a fragment in the file belongs to the rows listed. The counts were verified with `frag.py` before each edit.

| Fragment (old to new count) | Rows | Occurrences: merged; source |
|---|---|---|
| `` `make answer-keys ID=<§8.2.1 ids>` (220 keys) `` to 221 | BI-32, BI-42, BI-48 (two lines) | 4; 4 in 12 |
| `` `make answer-keys ID=<PHASES §8.2.1 ids>` (220 keys) `` to 221 | BI-43, BI-45 | 2; 2 in 13 |
| `` `make answer-keys ID=<the 220 ids of PHASES §8.2.1>` `` to 221 (after BI-41 and S-02) | S-04, S-05 | 2; 2 in 13 |
| `` `make answer-keys ID=<§8.2.1 and §8.2.2 ids>` (226 keys) `` to 227 | BI-49, BI-51 (Gates), BI-52, BI-55 (preamble), BI-56 (preamble), BI-60 (two lines) | 7; 4 in 12 and 3 in 14 |
| `` `make answer-keys ID=<§8.2.1 and §8.2.2 ids>` (226 passed) `` to 227 | BI-54, BI-55 (Gates), BI-56 (Gates) | 3; 3 in 14 |
| `(231 keys, zero corpus gaps)` to 232 | BI-64, BI-65 (preambles) | 2; 2 in 14 |
| `(231 passed, zero corpus gaps)` to 232 | BI-64, BI-65 (Gates), BI-69 | 3; 3 in 14 |
| `every active key passes (231 at issue)` to 232 | BI-71, BI-72 (Tests) | 2; 2 in 14 |
| `` `make answer-keys` unfiltered (231) `` to 232 | BI-71, BI-72 (Answer keys) | 2; 2 in 14 |

Observations for the supervisor. The row text was applied verbatim, and nothing below was changed.

1. **BI-31 citation order (ENC-15 Read).** The line now reads "… JET-09a to JET-09d (CHK-130, CHK-131; JET-09c rev 1.3); `_coverage/ADJUDICATION.md` §10 R-COST-03, §6.2 row 10; D-76 (contract-cost impairment); …". "§6.2 row 10" was a POLICIES citation and now follows the ADJUDICATION citation. Suggested follow-up wording: "… (CHK-130, CHK-131; JET-09c rev 1.3), §6.2 row 10; `_coverage/ADJUDICATION.md` §10 R-COST-03; D-76 …". Class C; no behaviour changes.
2. **PHASES §8.2 is headed "(generated)".** No script under `research-harness/` references "Key ids by closing phase" or "8.2.1 AKS", so BP-06 to BP-10 were hand edits. If a generator exists elsewhere, re-run it and compare.
3. **Left unchanged by design.**
   - The rev 1.0 row of the `12-engine.md` author revision log (Appendix B.2) records "231 of 231 active keys" at first issue. It is history.
   - BI-10 keeps `"300.00"` as a rejected payload.
   - DMO-12 J-02.2 keeps "(96,050.00 to 129,950.00; 43.6%)", per BI-66.
4. **Residue sweep.** After application, `residue.py` scanned the merged file and all sources. It finds no other stale corpus count (220, 226, 231, 233, 37 keys) and no superseded figure (96 IMP rows, 0.425, J-02.5 at 43.6%, unsigned memo figures).

## 5. Verification

### 5.1 `python3 research-harness/buildspec/merge_buildspec.py --check`

```
items 417 (build 391, checkpoints 26); per phase: FND 18; EKC 12; PLF 30; WEB 24; ENA 13; RFD 25; ENB 13; ENC 16; END 14; AKS 8; CTR 28; DIN 18; GPA 6; EDS 7; CLO 27; RPS 24; SNP 5; LMG 11; GPB 4; PRP 8; FCS 8; AIX 12; SOP 9; DMO 34; PRF 6; DEP 8; REL 3
docs/BUILD_SPEC.md equals a fresh merge
merge rc=0
```

### 5.2 `python3 research-harness/buildspec/check_merged.py --json .scratch/b4-apply-impact/merged.json`

```
check  1 Release-1.0 requirements cited and completed         gaps    0  -
check  2 Controls in acceptance criteria                      gaps    0  -
check  3 Answer-key families and key ids                      gaps    0  -
check  4 Golden parity kinds and the parity gate              gaps    0  -
check  5 Screen ids and route rows cited, with captures       gaps    0  -
check  6 Journeys and their steps                             gaps    0  -
check  7 Loop make targets introduced                         gaps    0  -
check  8 Prerequisites exist and precede                      gaps    0  -
check  9 Item ids unique and well formed                      gaps    0  -
check 10 Acceptance criteria and doc citations                gaps    0  -
check 11 Sizing heuristics                                    gaps   18  11a=16, 11b=2
total gaps (checks 1-10): 0
merged item model equals the sources: yes (417 items)
check 11 flags 18; waiver rows 18; unwaived 0; stale 0; measured differs 0; duplicate 0; reason too short 0
merged BUILD_SPEC coverage: OK
check rc=0
```

The baseline was taken after BI-01 and BI-02 only (`.scratch/b4-apply-impact/baseline.json`):
- check 3 reported 2 gaps, 3b=1 and 3g=1, both for `SFC-S3-EX26-RETURN-RIGHT`, which no item cited and which had no PHASES §8.2 row;
- total gaps for checks 1 to 10: 2; coverage FAIL; exit 1.

Check 11 stayed at 18 flags (11a=16, 11b=2) with 18 matching waiver rows, as report §3 predicted. No waiver row changed.

## 6. Commit note

Nothing was committed. Report note 3 requires BI-35 to BI-42 and BP-01 to BP-10 in one commit, so commit all of this as one supervisor commit. The loop is building FND-9 in the same checkout. Stage the seven edited paths and this file explicitly, never with `git add -A`, and verify the staged tree before pushing.
