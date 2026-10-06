# B3 review: BUILD_SPEC coverage and ordering

| Field | Value |
|---|---|
| Owner | Build-spec coverage and ordering reviewer (design phase B3, slug `bs-coverage`) |
| Date | 2026-09-12 |
| Status | Review report. It records findings and governs nothing (`docs/01-DECISIONS.md` §0; header §2 rule 1). The fix pass and the supervisor rerun the scripts |
| Inputs | `docs/build-spec/00-header.md`, `PHASES.md`, `11-foundation-platform.md`, `12-engine.md`, `13-reference-contracts-data.md`, `14-close-reports-ai-demo-release.md`; 03 §3 and §4.1; PRD §4; dev-guide §4; SCREENS §0.4 and §0.12; SCREENS_B §15; `docs/accounting/answer-keys/`; `docs/legacy/golden/deviations.json` and `golden-tests.json` |
| Scripts | `research-harness/buildspec/check_buildspec.py` (checks 1 to 11); `research-harness/buildspec/selftest.py` (mutation self-test) |
| Revision | 1.0 (2026-09-12), first issue |

## Revision log

| Rev | Date | Change |
|---|---|---|
| 1.0 | 2026-09-12 | First issue: checks 1 to 11, a 21-case mutation self-test, findings BSC-01 to BSC-05 |

### Decisions taken in B3 (D-77)

None of these opens a question. Each fixes how a check reads the documents.

| Id | Decision | Rationale |
|---|---|---|
| BSC-D-01 | The merged order is `00-header.md`, then every `## <nn> <code>` section of the other `docs/build-spec/*.md` files (`PHASES.md` excluded), placed by the PHASES §3 `Sequence:` line. Lines inside code fences are ignored | The phase files hold several phases each; the "Assembly" row of `11-foundation-platform.md` places sections, not files |
| BSC-D-02 | An item is a line `- [ ] **<CODE>-<n> <title>.**` or `- [ ] **GATE-<CODE> <title>.**` with its indented body. Fields are `  - **Name:**` lines; sub-fields are `    - Name:` lines | Header §5.1 template. The BS-D-24 grep of REL-2 yields the same 406 ids |
| BSC-D-03 | Citations count only in non-GATE items | GATE items restate membership and build nothing (header §6) |
| BSC-D-04 | Ranges (`REQ-X-001 to REQ-X-004`, `RT-08 to RT-21`, `J-01.1 to J-01.11`, `J-02-AC-1 to J-02-AC-7`) and abbreviations (`REQ-PLT-001, 002`) count as citations, except under "REQs completed". There only full ids count | The REL-2 G1 grep reads full ids only |
| BSC-D-05 | A family-level answer-key criterion is `` `F` n `` on an item's "Answer keys" line, where n equals the PHASES §8.2 count of active family-F keys closing in the item's phase. It covers only keys that the item's `ID=` selection also lists | A matching count must not hide an omitted key (self-test case "Key id mistyped everywhere") |
| BSC-D-06 | `make parity K=` expressions are evaluated with pytest `-k` semantics (`and`, `or`, `not`, parentheses, case-insensitive substring) against `test_golden_parity[<kind>::<test id>]` for the 122 ids of `deviations.json`. A non-GATE Acceptance line asserts that the cases pass. A line whose value starts with `none` defers them | The parity node id form of GPA-1 (one case per id `<kind>::<test id>`) |
| BSC-D-07 | A capture is a backticked `sf-…`, `x-…` or `explain-panel` token in an item's Acceptance. It is assigned to the screen id whose SCREENS SCR-TID-03 normalisation is its longest prefix | BS-D-09 |
| BSC-D-08 | A make target is introduced by the item whose Scope Paths names it, in backticks or as `DG-MK-<target>`, inside the segment that names `` `Makefile` `` | Every introducing item uses this form |
| BSC-D-09 | Check 11 is a heuristic and never sets the exit status. Criteria count as the bullets under Tests plus each non-`none` Answer keys, Golden, Controls, Screens, Journeys, Properties and Evidence sub-field. Modules count as domain areas, kernel modules, adapter kinds, engine stages, and route or app areas. Tests, schemas, API routers, migrations, registries and demo builders are excluded. Components, web foundation and scripts each count once, and same-named areas merge. SZ-02 limits are counted where they are countable | Header SZ-02; SZ-05 already lets the loop propose a split |

## 1. Result

The merged BUILD_SPEC has 406 items across 27 phases. Eight checks report no gaps: 1, 2, 3, 6, 7, 8, 9 and 10. Checks 4 and 5 report 7 gaps from two defects:

- BSC-01 blocks four checkpoints;
- BSC-02 is minor.

Check 11 raises 31 sizing flags (BSC-03 to BSC-05). The self-test injected 21 kinds of defect into a scratch copy, and the checker detected all 21. A zero therefore holds for each pattern tested.

| # | Check | Gaps | Evidence |
|---|---|---:|---|
| 1 | Every release-1.0 REQ cited; "REQs completed" names each exactly once, in its PHASES §6 phase | 0 | 409 of 409 cited by explicit id; 409 completed exactly once; no abbreviation or range under "REQs completed"; each completing phase equals PHASES §6 |
| 2 | CTL-001 to CTL-049 in acceptance criteria | 0 | 49 of 49 in Acceptance, each with a named failure-path test in its PHASES §7 phase |
| 3 | Answer-key families and key ids | 0 | 27 primary families; 231 of 231 active keys cited by id; every `ID=` selection names existing active keys and states its true size; neither withdrawn key is selected |
| 4 | Golden kinds and the parity gate | 5 | 7 of 7 kinds cited in their PHASES §9 phase. GPB-4, DMO-8, REL-1 and REL-3 accept on unfiltered `make parity` with 122 cases. Every stated `K=` count equals the computed selection. The five 4k gaps are one defect (BSC-01) |
| 5 | Screen ids and RT rows cited, with captures | 2 | 112 of 112 RT rows and 122 of 122 screen ids cited by explicit id; 80 of 80 audit rows captured, with a distinct capture per row where one id has two rows; SF-21 and SF-23 have no capture (BSC-02) |
| 6 | J-01 to J-26 and their steps | 0 | 26 journeys; 180 steps, 98 acceptance items and 22 alternates, all cited |
| 7 | Loop make targets introduced | 0 | 35 of 35 loop targets and 6 of 6 supervisor targets introduced, each in its PHASES §13 phase; no Gates field runs a target that a later item introduces |
| 8 | Prerequisites exist and precede | 0 | No unknown, later or self prerequisite. Every phase's first item requires the previous GATE. Every GATE range equals the phase's first and last item |
| 9 | Item ids unique and well formed | 0 | 406 distinct ids; 27 sections numbered as PHASES §3; exactly one GATE per phase, placed last, and none in REL |
| 10 | Acceptance criteria and doc citations | 0 | Every item has the five fields and its header §5.1 sub-fields. Every Tests names a node id, spec, command or journey-spec step. Every Read cites a document, and every Gates names a GK id |
| 11 | Sizing (heuristic) | 31 flags | 22 items over 12 criteria; 4 over 3 modules; 2 over 12 routes; 3 over 4 screen ids; every phase within a third of PHASES §1 |

## 2. Findings

### BSC-01 Four GATE items run parity cases that cannot pass yet (high; blocks GATE-CLO, GATE-RPS, GATE-SNP and GATE-LMG)

- **Facts.**
  - `12-engine.md` B3-BS2-04 moves probes P1, P2 and P4 to GPB.
  - GPA-6 makes their journal expectations fail closed while `legacy_je_summary` (RPT-13) is absent. GPA-6 passes 94 cases.
  - GATE-GPA and GATE-EDS run `K="initial_allocation or pob_position or contract_position or cumulative_catchup or probe-P3-over-delivery-validation"` (94 cases). The first item whose acceptance passes P1, P2 and P4 is GPB-1, which comes after GATE-LMG.
- **Conflict.**
  - GATE-CLO (`14-close-reports-ai-demo-release.md:776`), GATE-RPS (`:1433`), GATE-SNP (`:1588`) and GATE-LMG (`13-reference-contracts-data.md:2302`, `:2304`) run `K="… or legacy_probe"` and state 97.
  - The phase preambles repeat it at `14-…:61`, `:795`, `:1450` and `13-…:2002`.
  - The source is PHASES itself: §1 row GPA (`PHASES.md:74`) and §4 row GATE-GPA (`PHASES.md:176`), which the "as GATE-GPA" rows inherit, still read `legacy_probe` (97).
- **Effect.**
  - At GATE-CLO the selection is red by construction, because RPT-13 is built in RPS.
  - At GATE-RPS, GATE-SNP and GATE-LMG no item has yet made P1, P2 and P4 pass. A red run blocks the tick (DG-GATE-01), and fixing it pulls GPB-1 work forward, which XR-19 forbids.
- **Fix.**
  - BS-3 (GATE-LMG) and BS-4 (GATE-CLO, GATE-RPS, GATE-SNP) replace `legacy_probe"` (97 cases or 97 passed) with `probe-P3-over-delivery-validation"` (94 cases; B3-BS2-04) at the nine lines above.
  - The supervisor amends PHASES §1 row GPA and §4 row GATE-GPA to the 94-case selection, as B3-BS2-04 invites.
  - Verify: sub-check 4k reports 0.

### BSC-02 SF-21 and SF-23 have no capture (low)

- **Facts.**
  - Both screen ids are SCREENS §0.4 placements.
  - WEB-9 cites both and tests SF-21 in Vitest (`frontend/src/app/shell/NotificationsPanel.test.tsx` "SF-21").
  - WEB-12 captures `sf-23-select` for the SCREENS_B §15 row SF-23:select. RFD-19 binds the context pill and notes that it appears in every capture.
  - Neither SCREENS §0.12 nor SCREENS_B §15 has a row for SF-21 or bare SF-23. The gap is against this review's rule that every screen id has a capture, not against a SCREENS audit row.
- **Fix (default).**
  - WEB-16 adds capture `sf-21`: persona `maya`, `/approvals`, bell popover open.
  - RFD-19 adds capture `sf-23`: persona `tomas`, context pill menu open.
  - Verify: sub-check 5c reports 0. Alternative: the supervisor exempts these two placements from captures.

### BSC-03 Items over twelve acceptance criteria (low; heuristic)

- 22 items.
- Split candidates by size:
  - ENC-12 (19 criteria);
  - DIN-7 (19);
  - FND-3 (18; also five modules, BSC-04);
  - PLF-10 (17);
  - ENB-6 (15);
  - ENC-3 (15).
- REL-1 (16) and REL-3 (20) are release sweeps whose criteria are the header §7 table; they need no split.
- The other 14 items hold 13 or 14 criteria: FND-2, FND-8, EKC-1, RFD-2, RFD-11, RFD-13, ENB-12, END-9, CTR-5, CTR-16, DIN-6, CLO-6, CLO-9 and LMG-10.
- Nothing is required before the build; SZ-05 lets the loop propose a split after two iterations.

### BSC-04 Items spanning more than three modules (low; heuristic)

- FND-3: key and secret adapters, engine kernel, auth, scripts.
- CLO-13: GL adapters, close, journals, events, jobs.
- PLF-13: email adapter, platform, approvals, events.
- CLO-7: close, contracts, imports, approvals.

Each is an integration item. FND-3 and CLO-13 have the widest spread and are the first split candidates.

### BSC-05 SZ-02 formal limits exceeded (low)

- **Routes.** PLF-17 and CTR-12 each hold 13 HTTP methods in Scope API; the limit is twelve routes.
- **Screen ids.** Three items exceed four list and detail screen ids:
  - WEB-13: five SF-22 authentication screens;
  - WEB-14: four SF-12 views plus X:not-found;
  - WEB-16: SF-15, SF-15:notifications, SF-27 and two X placements.

  These are small forms and states. Either accept them, or move the X placements to their own item.
- **Within limits.** No item holds more than one migration revision, eight tables, forty selected keys, twenty-five completed REQs or ten steps of one journey.

### Information (no action required)

- **8g.** 163 later item ids appear in Scope, Acceptance, Read or Gates. They are hint-closure notes (for example "closes in AKS-6"), fail-closed consumers (XR-12) and interface notes; none is a prerequisite.
- **7f.** FND-5 names `make dev-down` inside an expected error message, not as a command it runs.
- **2f.** `CTL-50` and `CTL-050` in FND-11 and SOP-1 are negative fixtures of the control-marker validation test.
- **4l.** CLO-9 names `K=journal_entry_totals` under "Golden: none … closes in GPB", a deferral, not a passing criterion.
- **G1 command.** The REL-2 item-set grep over the merged files yields the same 406 unique ids as the parser.
- **Assembly.**
  - Sections live in four multi-phase files. `12-engine.md`, `13-reference-contracts-data.md` and `14-close-reports-ai-demo-release.md` open with a title, a revision log and B3 decisions before their first section.
  - PHASES §0 and §2 still name one file per phase (`docs/build-spec/<nn>-<code>.md`).
  - Assembling `docs/BUILD_SPEC.md` must place sections in PHASES §3 order, as the "Assembly" row of `11-foundation-platform.md` states, and must decide where the author revision logs go.

## 3. Method and limits

- **Checker.** `check_buildspec.py` uses the standard library only (tested with Python 3.14). It reads the binding documents, never writes them, and computes every sub-check from the sources on each run, so no count is hard-coded.
  - Exit status 0 means checks 1 to 10 have no gap; 1 means at least one gap; 2 means a parse failure.
  - `--json` writes every list, the inventory and a SHA-256 per input file.
  - `--report` rewrites only the GENERATED block of this file.
- **Self-test.** `selftest.py` copies the inputs to `.scratch/b3-bs-coverage/selftest/repo/` and injects 21 defects one at a time:
  - an uncited REQ, a REQ completed twice, an abbreviated completed list;
  - a removed control;
  - a mistyped key, a wrong key count, a wrong parity count;
  - an unnamed golden kind, an uncited RT row, a removed capture, two audit rows with one capture;
  - an added journey step;
  - a dropped make target, a Gates field running a later target, a parity run before any case passes;
  - a later, unknown or stale-range prerequisite;
  - a duplicate id;
  - a Read without citations, a renamed Acceptance field.

  It asserts that each named sub-check rises; 21 of 21 are detected.
- **Limits.**
  - A citation check proves that an id is named, not that the named test asserts the right values.
  - Captures are proved by name. Persona per audit row is matched only on the capture line (information sub-check 5i).
  - Placeholder selections (`ID=<§8.2.1 ids>`, `K="<the 13-case selection above>"`) are not evaluated; the explicit selections they reference are.
  - Phase preambles are not items and are not checked; BSC-01 lists the preamble lines for consistency.
  - Check 11 is heuristic (BSC-D-09).

## 4. Rerun

From the repository root:

```sh
python3 research-harness/buildspec/check_buildspec.py --json .scratch/b3-bs-coverage/coverage.json
python3 research-harness/buildspec/check_buildspec.py --report docs/reviews/B3-buildspec-coverage.md
python3 research-harness/buildspec/selftest.py
```

After BSC-01 and BSC-02 are fixed, the first command prints `total gaps (checks 1-10): 0` and exits 0.

## 5. Generated results

The block below is regenerated by the second command above, and every list in it is exact. Gap lists are printed in full. Information lists are capped at 80 lines; the JSON output holds the rest.

<!-- BEGIN GENERATED: research-harness/buildspec/check_buildspec.py -->

Generated 2026-09-12T17:54:16Z by `research-harness/buildspec/check_buildspec.py` over 246 input files (SHA-256 per file in the JSON output). Rerun: `python3 research-harness/buildspec/check_buildspec.py --report docs/reviews/B3-buildspec-coverage.md`.

### G.0 Inventory

| Measure | Value |
|---|---|
| Phase files read (merged order) | docs/build-spec/00-header.md, docs/build-spec/11-foundation-platform.md, docs/build-spec/12-engine.md, docs/build-spec/13-reference-contracts-data.md, docs/build-spec/14-close-reports-ai-demo-release.md |
| Items (GATE included) | 406 |
| Items per phase (PHASES §3 order) | FND 18; EKC 13; PLF 29; WEB 23; ENA 14; RFD 26; ENB 13; ENC 15; END 15; AKS 9; CTR 28; DIN 18; GPA 7; EDS 8; CLO 27; RPS 25; SNP 6; LMG 12; GPB 5; PRP 9; FCS 9; AIX 13; SOP 10; DMO 35; PRF 7; DEP 9; REL 3 |
| 03 release-1.0 REQs / later | 409 / 25 |
| 03 §4.1 controls | 49 |
| Answer-key files / active / withdrawn | 233 / 231 / 2 |
| Golden cases / kinds | 122 / 7 |
| SCREENS §0.4 RT rows / placements / audit rows | 112 / 9 / 80 |
| PRD journeys / steps / AC / ALT | 26 / 180 / 98 / 22 |
| dev-guide §4.2 to §4.4 loop targets / §4.5 supervisor targets | 35 / 6 |

### G.1 Gap counts

| Check | Title | Gaps | Sub-checks with gaps | Information |
|---|---|---:|---|---|
| 1 | Release-1.0 requirements cited and completed | 0 | none | none |
| 2 | Controls in acceptance criteria | 0 | none | 2f 3 |
| 3 | Answer-key families and key ids | 0 | none | 3j 1 |
| 4 | Golden parity kinds and the parity gate | 5 | 4k 5 | 4i 7, 4j 17, 4l 1 |
| 5 | Screen ids and route rows cited, with captures | 2 | 5c 2 | none |
| 6 | Journeys and their steps | 0 | none | none |
| 7 | Loop make targets introduced | 0 | none | 7f 1 |
| 8 | Prerequisites exist and precede | 0 | none | 8g 163 |
| 9 | Item ids unique and well formed | 0 | none | none |
| 10 | Acceptance criteria and doc citations | 0 | none | none |
| 11 | Sizing heuristics (heuristic) | 31 | 11a 22, 11b 4, 11e 2, 11i 3 | none |

Checks 1 to 10: **7** gaps. Check 11 (heuristic): **31** flags.

### G.1 Check 1: Release-1.0 requirements cited and completed

Counts: release_1_0 409; later 25; cited_explicitly 409; completed_once 409.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 1a | gap | 0 | Release-1.0 REQ not cited by any non-GATE item (explicit id, range or abbreviation) |
| 1b | gap | 0 | Release-1.0 REQ listed under "REQs completed" by no item (header §6; BS-D-24) |
| 1c | gap | 0 | REQ listed under "REQs completed" by more than one item (header §6) |
| 1d | gap | 0 | "REQs completed" names a REQ that is not release 1.0 in 03 §3 |
| 1e | gap | 0 | "REQs completed" line uses an abbreviation or range that the REL-2 grep cannot read |
| 1f | gap | 0 | Completing item's phase differs from the PHASES §6 build phase (BS-D-19) |
| 1g | gap | 0 | Release-1.0 REQ without a PHASES §6 row, or with more than one |
| 1h | information | 0 | Release-1.0 REQ cited only through a range or abbreviation |

### G.2 Check 2: Controls in acceptance criteria

Counts: controls 49; in_acceptance 49; with_named_test 49.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 2a | gap | 0 | Control not named in any non-GATE item's Acceptance |
| 2b | gap | 0 | Control without a named failure-path test (Controls line with a test node id, or `test_ctl_<nnn>_`) |
| 2c | gap | 0 | No named failure-path test in the phase PHASES §7 assigns |
| 2d | gap | 0 | Control id in a Controls line or Read that 03 §4.1 does not define |
| 2e | information | 0 | Control in Acceptance only through a range |
| 2f | information | 3 | Undefined control id elsewhere in an item (for example a negative test fixture) |

**2f** (3, information):

- CTL-50 (FND-11)
- CTL-050 (FND-11)
- CTL-50 (SOP-1)

### G.3 Check 3: Answer-key families and key ids

Counts: files 233; active 231; withdrawn 2; families 27; explicitly_cited 231; covered_by_family_criterion_only 0.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 3a | gap | 0 | Primary family (`families[0]`) with neither a family-level criterion nor any cited key |
| 3b | gap | 0 | Active key neither cited by id in a non-GATE item nor covered by a family-level criterion (`` `F` n `` equal to the PHASES §8.2 count of F in the item's phase) |
| 3c | gap | 0 | `make answer-keys ID=` selection names an id that is not a key |
| 3d | gap | 0 | Selection names a withdrawn key (DG-AK-13) |
| 3e | gap | 0 | Stated pass count differs from the size of the selection |
| 3f | gap | 0 | Family-level criterion whose count differs from PHASES §8.2, or whose item selection omits keys of that family |
| 3g | gap | 0 | Corpus integrity: duplicate key id, status other than active or withdrawn, active key without a PHASES §8.2 row, or §8.2 id that is not an active key |
| 3h | information | 0 | Active key not selected by id in an item of its PHASES §8.2 closing phase (covered by a placeholder selection or a family criterion instead) |
| 3i | information | 0 | Withdrawn key not named in any item |
| 3j | information | 1 | Secondary family codes (DG-AK-33 needs a key per code; never a primary family) |

**3j** (1, information):

PAR

### G.4 Check 4: Golden parity kinds and the parity gate

Counts: cases 122; kinds 7; filtered_selections 17; cases_selected_by_filtered_runs 122; full_gate_items 7.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 4a | gap | 0 | Golden kind of deviations.json not named in any non-GATE item's Acceptance |
| 4b | gap | 0 | No non-GATE item accepts on unfiltered `make parity` with 122 cases (G3) |
| 4c | gap | 0 | deviations.json and golden-tests.json disagree on kinds or test ids |
| 4d | gap | 0 | `make parity K=` stated count (passes N of N; N pass; N passed; N cases) differs from the cases the expression selects, in any item's Acceptance or Gates (pytest -k semantics over `<kind>::<test id>`) |
| 4e | gap | 0 | `make parity K=` expression that does not parse |
| 4f | gap | 0 | deviations.json `signoff_required` test id or `signoff_units` unit not named by any item (DG-PAR-08) |
| 4g | gap | 0 | Kind not named in an item of its PHASES §9 phase |
| 4k | gap | 5 | `make parity K=` run (GATE items and Gates fields included) that selects cases no passing criterion at or before that item covers: the gate cannot be green when it runs |
| 4h | information | 0 | Cases that no filtered `make parity K=` selection reaches (only the unfiltered run covers them) |
| 4i | information | 7 | Items accepting on unfiltered `make parity` with 122 cases |
| 4j | information | 17 | Passing `make parity K=` criteria of non-GATE items and the number of cases each selects |
| 4l | information | 1 | `make parity K=` selection named on a 'none' line (deferred, not a passing criterion) |

**4k** (5):

- GATE-CLO Acceptance: K='initial_allocation or pob_position or contract_position or cumulative_catchup or legacy_probe' runs 97 cases; 3 have no passing criterion at or before GATE-CLO: probe-P1-blank-memo-drops-progress-rows (first passing criterion: GPB-1), probe-P2-mod-reposts-pre-asc606-in-delta-je (first passing criterion: GPB-1), probe-P4-duplicate-upload-double-counts (first passing criterion: GPB-1)
- GATE-RPS Acceptance: K='initial_allocation or pob_position or contract_position or cumulative_catchup or legacy_probe' runs 97 cases; 3 have no passing criterion at or before GATE-RPS: probe-P1-blank-memo-drops-progress-rows (first passing criterion: GPB-1), probe-P2-mod-reposts-pre-asc606-in-delta-je (first passing criterion: GPB-1), probe-P4-duplicate-upload-double-counts (first passing criterion: GPB-1)
- GATE-SNP Acceptance: K='initial_allocation or pob_position or contract_position or cumulative_catchup or legacy_probe' runs 97 cases; 3 have no passing criterion at or before GATE-SNP: probe-P1-blank-memo-drops-progress-rows (first passing criterion: GPB-1), probe-P2-mod-reposts-pre-asc606-in-delta-je (first passing criterion: GPB-1), probe-P4-duplicate-upload-double-counts (first passing criterion: GPB-1)
- GATE-LMG Acceptance: K='initial_allocation or pob_position or contract_position or cumulative_catchup or legacy_probe' runs 97 cases; 3 have no passing criterion at or before GATE-LMG: probe-P1-blank-memo-drops-progress-rows (first passing criterion: GPB-1), probe-P2-mod-reposts-pre-asc606-in-delta-je (first passing criterion: GPB-1), probe-P4-duplicate-upload-double-counts (first passing criterion: GPB-1)
- GATE-LMG Gates: K='initial_allocation or pob_position or contract_position or cumulative_catchup or legacy_probe' runs 97 cases; 3 have no passing criterion at or before GATE-LMG: probe-P1-blank-memo-drops-progress-rows (first passing criterion: GPB-1), probe-P2-mod-reposts-pre-asc606-in-delta-je (first passing criterion: GPB-1), probe-P4-duplicate-upload-double-counts (first passing criterion: GPB-1)

**4i** (7, information):

GPB-4, GPB-4, DMO-8, REL-1, REL-1, REL-3, REL-3

**4j** (17, information):

- GPA-1: K='initial_allocation' selects 16
- GPA-1: K='initial_allocation' selects 16
- GPA-2: K='contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)' selects 22
- GPA-2: K='contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)' selects 22
- GPA-3: K='catchup-08 or catchup-09 or rollforward-08 or rollforward-09' selects 11
- GPA-3: K='catchup-08 or catchup-09 or rollforward-08 or rollforward-09' selects 11
- GPA-4: K='catchup-10 or catchup-11 or catchup-12 or catchup-13 or rollforward-10 or rollforward-11 or rollforward-12 or rollforward-13' selects 23
- GPA-4: K='catchup-10 or catchup-11 or catchup-12 or catchup-13 or rollforward-10 or rollforward-11 or rollforward-12 or rollforward-13' selects 23
- GPA-5: K='pob_position or rollforward-14' selects 21
- GPA-5: K='pob_position or rollforward-14' selects 21
- GPA-6: K='probe-P3-over-delivery-validation' selects 1
- GPA-6: K='initial_allocation or pob_position or contract_position or cumulative_catchup or probe-P3-over-delivery-validation' selects 94
- GPA-6: K='initial_allocation or pob_position or contract_position or cumulative_catchup or probe-P3-over-delivery-validation' selects 94
- GPB-1: K='je-step-02 or je-step-03 or je-step-04 or je-step-05 or je-step-06 or je-step-07 or je-month-2023-01 or je-month-2023-02 or je-month-2023-03 or je-month-2023-04 or probe-P1-blank-memo-drops-progress-rows or probe-P2-mod-reposts-pre-asc606-in-delta-je or probe-P4-duplicate-upload-double-counts' selects 13
- GPB-2: K='je-step-08 or je-step-09 or je-step-10 or je-step-11 or je-step-12 or je-step-13 or je-step-14 or je-month-2023-05 or je-month-2023-06 or je-month-2023-07 or je-month-2023-08 or je-month-2023-09 or je-month-2023-10 or je-month-2023-full-year' selects 14
- GPB-3: K='point_in_time_equivalence' selects 1
- GPB-3: K='point_in_time_equivalence' selects 1

**4l** (1, information):

- CLO-9 Acceptance: K='journal_entry_totals' (24 cases) named under 'none'

### G.5 Check 5: Screen ids and route rows cited, with captures

Counts: rt_rows 112; placements 9; audit_rows 80; screen_ids 122; screen_ids_with_capture 120.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 5a | gap | 0 | RT row not cited by any non-GATE item (explicit id or range) |
| 5b | gap | 0 | Screen id (route table, placements, audit lists) not cited by any non-GATE item |
| 5c | gap | 2 | Screen id without a capture name in any non-GATE item's Acceptance (SCR-TID-03 normalisation, BS-D-09) |
| 5d | gap | 0 | RT row whose screen id has no capture |
| 5e | gap | 0 | Screen audit row (SCREENS §0.12, SCREENS_B §15) with a screen id that has no capture |
| 5f | gap | 0 | Capture name in a Screens line that maps to no screen id |
| 5g | gap | 0 | RT id or screen id cited that neither SCREENS nor the PRD surface table defines |
| 5j | gap | 0 | Screen id with more audit rows than distinct capture names |
| 5h | information | 0 | RT row cited only through a range |
| 5i | information | 0 | Audit row whose persona is not named on any line carrying one of its captures |

**5c** (2):

SF-21, SF-23

### G.6 Check 6: Journeys and their steps

Counts: journeys 26; steps 180; acceptance_items 98; alternates 22.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 6a | gap | 0 | Journey not cited by any non-GATE item |
| 6b | gap | 0 | Journey step J-nn.s not cited (explicit or range) |
| 6c | gap | 0 | Journey acceptance item J-nn-AC-n not cited |
| 6d | gap | 0 | Journey alternate J-nn-ALT-n not cited |
| 6e | gap | 0 | Step, AC or ALT id cited that PRD §4 does not define |
| 6f | information | 0 | Journey whose last cited step lies outside its PHASES §11 phase |

### G.7 Check 7: Loop make targets introduced

Counts: loop_targets 35; supervisor_targets 6; introduced 35.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 7a | gap | 0 | Loop target of dev-guide §4.2 to §4.4 that no item's Scope introduces (a `Makefile` path segment naming the target) |
| 7b | gap | 0 | Supervisor target of dev-guide §4.5 that no item introduces |
| 7c | gap | 0 | Introducing item's phase differs from PHASES §13 |
| 7d | gap | 0 | Gates field runs a target that a later item introduces (PHASES §13: no item calls a later target) |
| 7e | information | 0 | Target named as introduced by more than one item (extensions of an existing recipe are normal) |
| 7f | information | 1 | Acceptance runs a target that a later item introduces (may be a fail-closed or 'not yet' statement) |

**7f** (1, information):

- FND-5 runs `make dev-down`, introduced later by PLF-28

### G.8 Check 8: Prerequisites exist and precede

Counts: items 406.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 8a | gap | 0 | Prerequisite names an id that no item defines |
| 8b | gap | 0 | Prerequisite names an item that appears later in the merged order |
| 8c | gap | 0 | Item lists itself as a prerequisite |
| 8d | gap | 0 | GATE prerequisite range differs from the phase's first and last item |
| 8e | gap | 0 | First item of a phase does not require GATE-<previous phase> (header §5.1) |
| 8f | gap | 0 | Prerequisites field names no item id and is not 'none' |
| 8g | information | 163 | Scope, Acceptance, Read or Gates names a later item (allowed for fail-closed consumers, XR-12, and interface notes) |

**8g** (163, information):

- AIX-2 Acceptance names later AIX-3
- AIX-8 Acceptance names later AIX-12
- AKS-2 Acceptance names later AKS-6
- AKS-2 Acceptance names later EDS-7
- AKS-3 Acceptance names later AKS-6
- AKS-3 Acceptance names later EDS-7
- AKS-4 Acceptance names later PRP-1
- AKS-8 Acceptance names later EDS-7
- AKS-8 Acceptance names later PRP-1
- AKS-8 Acceptance names later PRP-3
- CLO-4 Acceptance names later CLO-5
- CLO-4 Acceptance names later CLO-10
- CLO-4 Acceptance names later CLO-13
- CLO-4 Acceptance names later CLO-16
- CLO-5 Scope names later CLO-18
- CLO-9 Scope names later RPS-5
- CLO-9 Scope names later RPS-7
- CLO-19 Scope names later RPS-7
- CLO-22 Acceptance names later RPS-8
- CLO-22 Acceptance names later RPS-11
- DEP-2 Acceptance names later DEP-5
- DMO-10 Acceptance names later DMO-33
- DMO-24 Acceptance names later DMO-25
- DMO-31 Acceptance names later DMO-32
- EDS-1 Acceptance names later EDS-7
- EDS-3 Acceptance names later EDS-7
- EDS-3 Acceptance names later PRP-4
- EDS-4 Acceptance names later EDS-7
- EDS-5 Acceptance names later PRP-4
- EDS-7 Acceptance names later PRP-3
- EKC-2 Acceptance names later AKS-1
- EKC-2 Acceptance names later EKC-7
- EKC-2 Acceptance names later ENC-9
- EKC-11 Acceptance names later END-9
- EKC-12 Acceptance names later END-9
- ENA-2 Acceptance names later ENA-13
- ENA-2 Acceptance names later END-5
- ENA-3 Acceptance names later AKS-2
- ENA-3 Acceptance names later GPA-1
- ENA-3 Acceptance names later GPA-5
- ENA-4 Acceptance names later AKS-2
- ENA-4 Acceptance names later AKS-5
- ENA-5 Acceptance names later AKS-2
- ENA-5 Acceptance names later AKS-6
- ENA-5 Acceptance names later ENA-11
- ENA-6 Acceptance names later AKS-3
- ENA-7 Acceptance names later AKS-2
- ENA-7 Acceptance names later AKS-3
- ENA-8 Acceptance names later AKS-3
- ENA-8 Acceptance names later AKS-6
- ENA-9 Acceptance names later AKS-2
- ENA-10 Acceptance names later AKS-1
- ENA-10 Acceptance names later ENA-11
- ENA-10 Acceptance names later ENB-12
- ENA-10 Acceptance names later GPA-1
- ENA-11 Acceptance names later AKS-1
- ENA-11 Acceptance names later AKS-2
- ENA-11 Acceptance names later GPA-1
- ENA-12 Acceptance names later AKS-2
- ENA-13 Acceptance names later AKS-2
- ENA-13 Acceptance names later GPA-1
- ENA-13 Scope names later END-9
- ENB-1 Acceptance names later AKS-5
- ENB-1 Acceptance names later ENC-3
- ENB-2 Acceptance names later AKS-1
- ENB-2 Acceptance names later AKS-5
- ENB-2 Acceptance names later ENB-3
- ENB-3 Acceptance names later AKS-5
- ENB-3 Acceptance names later ENC-11
- ENB-4 Acceptance names later AKS-3
- ENB-4 Acceptance names later AKS-5
- ENB-4 Acceptance names later AKS-6
- ENB-4 Acceptance names later END-12
- ENB-5 Acceptance names later AKS-5
- ENB-5 Acceptance names later GPA-4
- ENB-6 Acceptance names later AKS-5
- ENB-6 Acceptance names later GPA-3
- ENB-6 Acceptance names later GPA-4
- ENB-7 Acceptance names later AKS-5
- ENB-7 Acceptance names later GPA-4
- ... 83 more in the JSON output

### G.9 Check 9: Item ids unique and well formed

Counts: items 406; distinct_ids 406; sections 27.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 9a | gap | 0 | Duplicate item id |
| 9b | gap | 0 | Item id code differs from its section (BS-D-01) |
| 9c | gap | 0 | Item number zero-padded (BS-D-01: unpadded from 1) |
| 9d | gap | 0 | GATE item missing, duplicated or not last (header §6) |
| 9e | gap | 0 | Section heading missing, duplicated, misnumbered or outside PHASES §3 |
| 9f | gap | 0 | Item outside any phase section, or malformed item line |
| 9g | information | 0 | Gaps in item numbering |
| 9h | information | 0 | Item title without the template's closing full stop |

### G.10 Check 10: Acceptance criteria and doc citations

Counts: items 406.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 10a | gap | 0 | Required field missing (Prerequisites, Scope, Acceptance, Read, Gates) |
| 10b | gap | 0 | Template sub-field missing (header §5.1; GATE items: Exit criteria, Membership, Gates) |
| 10c | gap | 0 | Acceptance holds no criterion other than 'none' |
| 10d | gap | 0 | Tests names no concrete test node id, spec, command or check (IT-03); journey items qualify when Scope names the `.journey.ts` spec, Gates run `make e2e SPEC=J-nn` and Tests assert steps |
| 10e | gap | 0 | Read is empty or cites no binding document section or id (IT-05) |
| 10f | gap | 0 | Gates names no GK id (IT-06) |

### G.11 Check 11: Sizing heuristics

Counts: builder_items 380.

| Sub-check | Kind | Count | Rule |
|---|---|---:|---|
| 11a | gap | 22 | More than 12 acceptance criteria (test bullets plus non-'none' Answer keys, Golden, Controls, Screens, Journeys, Properties, Evidence) |
| 11b | gap | 4 | More than 3 unrelated modules in Scope Paths (domain areas, kernel modules, adapter kinds, engine stages, route areas and web app areas; components, web foundation and scripts each count once; tests, schemas, API routers, migrations, registries and demo builders excluded; same-named areas merged) |
| 11c | gap | 0 | SZ-02: more than one migration revision |
| 11d | gap | 0 | SZ-02: more than eight tables in Scope Schema |
| 11e | gap | 2 | SZ-02: more than twelve routes in Scope API (HTTP verbs counted) |
| 11f | gap | 0 | SZ-02: more than forty answer keys selected |
| 11g | gap | 0 | SZ-02: more than twenty-five REQs completed |
| 11h | gap | 0 | SZ-02 / BS-D-15: more than ten steps of one journey |
| 11i | gap | 3 | SZ-02: more than four screen ids, or more than two of SF-03, SF-05, SF-07, in Scope Screens (journey items excluded) |
| 11j | gap | 0 | Phase item count (GATE excluded) differs from the PHASES §1 indicative count by more than a third (SZ-07) |

**11a** (22):

- FND-2: 13 criteria (13 test bullets)
- FND-3: 18 criteria (17 test bullets)
- FND-8: 14 criteria (14 test bullets)
- EKC-1: 14 criteria (14 test bullets)
- PLF-10: 17 criteria (16 test bullets)
- RFD-2: 14 criteria (14 test bullets)
- RFD-11: 13 criteria (12 test bullets)
- RFD-13: 13 criteria (12 test bullets)
- ENB-6: 15 criteria (15 test bullets)
- ENB-12: 13 criteria (13 test bullets)
- ENC-3: 15 criteria (15 test bullets)
- ENC-12: 19 criteria (19 test bullets)
- END-9: 13 criteria (10 test bullets)
- CTR-5: 13 criteria (11 test bullets)
- CTR-16: 13 criteria (11 test bullets)
- DIN-6: 13 criteria (12 test bullets)
- DIN-7: 19 criteria (19 test bullets)
- CLO-6: 13 criteria (12 test bullets)
- CLO-9: 13 criteria (13 test bullets)
- LMG-10: 14 criteria (11 test bullets)
- REL-1: 16 criteria (10 test bullets)
- REL-3: 20 criteria (14 test bullets)

**11b** (4):

- FND-3: 5 modules (adapters:keys; adapters:secrets; engine:kernel; kernel:auth; scripts:scripts)
- PLF-13: 4 modules (adapters:email; domain:platform; kernel:approvals; kernel:events)
- CLO-7: 4 modules (domain:close; domain:contracts; domain:imports; kernel:approvals)
- CLO-13: 5 modules (adapters:gl; domain:close; domain:journals; kernel:events; kernel:jobs)

**11e** (2):

- PLF-17: about 13 routes
- CTR-12: about 13 routes

**11i** (3):

- WEB-13: 5 screen ids (SF-22:accept-invitation, SF-22:mfa-enrol, SF-22:password-change, SF-22:password-reset, SF-22:password-reset-confirm)
- WEB-14: 5 screen ids (SF-12, SF-12:all, SF-12:request, SF-12:submitted, X:not-found)
- WEB-16: 5 screen ids (SF-15, SF-15:notifications, SF-27, X:narrow-viewport, X:session-expiring)

<!-- END GENERATED -->
