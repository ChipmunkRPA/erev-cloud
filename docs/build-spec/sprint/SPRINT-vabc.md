# eRev Cloud 1.0-rc sprint plan, variant V-ABC (levels L2 onward)

| Field | Value |
|---|---|
| Owner | Sprint planner (slug `replan-vabc`) |
| Date | 2026-09-13 |
| Status | Proposed for the supervisor under D-82. Independently validated by `validate-vabc` (§9): every check passes after four fixes, and one supervisor decision is requested (§8 R-06) |
| Inputs | `docs/build-spec/sprint/plan.json` (L1 as validated, validator edges V-01 to V-10, variant V-ABC `levels_compact`); `SPRINT-1.0rc.md`; `docs/01-DECISIONS.md` D-81, D-82; `docs/BUILD_SPEC.md` (sha256 in `plan-vabc.json`) |
| Machine-readable plan | `docs/build-spec/sprint/plan-vabc.json`: levels L2 to L7, `l1_assumed` (28 ids), release gate, integration notes, review entries |
| Supervisor item | `docs/build-spec/sprint/sup-rc-smoke.md` |
| Generator and checks | Planner's generator `.scratch/sprint-vabc/evaluate.py` (`emit`, `fill`). Independent validator `docs/build-spec/sprint/validate_vabc.py` (§9). `plan.json` and `SPRINT-1.0rc.md` are unchanged |

## 1. Conclusions

**V-ABC finishes in 7 levels and about 35.1 h of wall-clock time, L1 included (L2 to L7: about 30.5 h).** That is one level and about 4.1 h less than the unvalidated V-ABC estimate in `plan.json` (8 levels, 39.2 h), and 12.1 h less than validated V-0 (10 levels, 47.2 h).

| Measure | Value |
|---|---|
| Scope | 144 items: 28 in L1 (`l1_assumed`), 116 scheduled in L2 to L7, plus SUP-RC-SMOKE in L7 |
| Revisions in L2 to L7 | 21. Two migration lanes in L4 and L5 only |
| Integration-after-merge items | 12 (18 contract edges), listed in the generated block |
| Checkpoint after 9 h | Unchanged: the L2 boundary at 9.3 h, with 62 items merged |
| Release gate | 176 engine-runner answer keys (V-0: 180), 121 of 122 golden cases, `screens.spec.ts` with the R-RC-1 fragments hidden and the DIN-9 fragments not green (§6.2), SUP-RC-SMOKE less RC-SMOKE.4 |

Why 7 levels is the floor under the rules:

- The answer-key sweeps AKS-1 to AKS-7 are serial (420 min). They start only after `compute` merges in L3, so they fill L4 and L5.
- GPA-2 to GPA-5 and GPB-2 carry the correction scope `backend/erev_engine/stages/`. They cannot share a level with a sweep, so parity runs in L6 and L7.
- V-A helps only in L4 and L5, where the contracts, data-in, close and report schemas branch. The reference-data chain of L2 and the contracts-core chain of L3 are strictly serial.
- On the L2+ scope, the packers of `plan_tools.py` return 8 levels (greedy) and 9 (first fit). The hand layout starts from the greedy result, adds the validator edges and reaches the 6-level floor for L2 to L7.

Recommendations:

1. **Adopt `plan-vabc.json` for L2 onward.** L2 is identical to the validated V-0 L2 in items, batches, notes, gates and estimate; only the display name of lane L2-1 changes.
2. **Approve the declared 5-minute lane-box exception in L5-1 (§4.3),** or take the compliant fallback at about +0.9 h.
3. **Rule on the DIN-9 fragments before L6 (§8, R-06).** The DIN-15 WLD-B-04 seed and the DIN-16 REQ-UX-021 step upload Progress events (CSV v2) files, and that emitter is in deferred DIN-9. Without a ruling, DIN-15, DIN-16, DIN-17 and SUP-RC-SMOKE run as partial items (§3.3).
4. **Use the unquoted key ids of `plan-vabc.json` for the release gate and merge gates.** `plan.json` lists 87 of its 180 runnable ids with literal quotes. Its merge gates from L4 onward also include 21 blocked keys that cannot pass (§6.1).

## 2. Method

| Rule | Application |
|---|---|
| L1 fixed | The `plan.json` L1 lanes and items are counted as merged when scheduling L2 onward |
| Edges | Planner edges of `plan_tools.all_edges`, with the validator's `VERIFIED_EDGES` (V-01 to V-08) added to the manual edges. Validator-derived edges (`validate_plan.derive_edges`) are checked in addition |
| V-B, R-RC-1 | The 21 `RULING_R_RC_1` edges are dropped from both edge sets. The closure loses 19 items (§3.2) |
| V-C | An edge from a platform item (RFD, CTR, DIN, CLO, RPS, WEB) to an engine item (ENA to EDS) may cross lanes within a level when it carries an integration note. The consumer codes against ENGINE_SPEC §0.5 (`OutputBundle`) with fakes. It is used once: CTR-2 on END-9, END-10 and EDS-1 in L3 |
| V-A | At most two lanes per level add revisions. The merge step re-parents the second (§5.2) |
| Packing | At most 5 lanes per level. Batches hold 1 to 4 items and at most 75 min. Lanes hold at most 240 min, with one declared exception. Correction scope applies. No two lanes of a level share a file without a merge rule |
| Estimate | Longest lane + 35 min merge + 25 min when screens or journeys merge + 10 min per integration-after-merge item + 10 min when a second migration lane is re-parented |
| Review entries | Four derived edges are reviewed as over-approximations (§3.4) |

## 3. Scope

### 3.1 Partition

| Set | Count | Where |
|---|---:|---|
| Done on `main` | 80 | `plan-vabc.json` `done` (same as `plan.json`) |
| L1, assumed merged | 28 | `l1_assumed` |
| Scheduled in L2 to L7 | 116 | `levels` |
| Supervisor item | 1 | SUP-RC-SMOKE, `supervisor_items` |
| Deferred | 203 | `deferred`: the 184 V-0 items plus the 19 R-RC-1 items |

### 3.2 Moved post-rc by R-RC-1

| Items | Consequence in the rc |
|---|---|
| CTR-11, CTR-17 | The CTR-22 void and regroup drawers are hidden (XR-14). RPS-4 tests k02 without CR-MARROWBY-2026-09 |
| CTR-14 | No K-09 commission in CTR-20; the CTR-23 billing-plan and costs panels are hidden; the RPS-4 k09 world moves post-rc |
| DIN-12, DIN-14 | No Salesforce or NetSuite mocks. CLO-13 creates `backend/erev_api/adapters/gl/` itself |
| EDS-4 | RPT-05 revenue from prior-period obligations and four `revenue_prior_period` keys move post-rc (§6.1) |
| EDS-5, EDS-6 | No cost rollforward, lock snapshot content or variance between closes |
| CLO-5, CLO-6, CLO-7 | No monitors, locks, snapshots or reopen. SF-05 locked and the SF-04 and SF-08 as-locked captures move to DMO. The CLO-11 reopened-period test moves post-rc |
| CLO-14 to CLO-20, CLO-22 | No acknowledgements, reconciliations, close runs or seeded close history. CLO-26 and RPS-7 use a run created in `beforeAll` through the API; SF-06 shows CSV export without acknowledgements |

Every consuming item records its hidden fragment as a spec question under XR-14. The batch notes of `plan-vabc.json` name each fragment.

### 3.3 Partial items

These items run their runnable subset, record a SPEC-Q and stay unticked. The V-0 figures missed 21 quoted blocked ids (§6.1). R-RC-1 accounts only for one key each in AKS-3 and AKS-6 and two in RPS-3.

| Item | Runnable of named keys (V-ABC) | V-0 figure | Waiting for |
|---|---|---|---|
| AKS-2 | 36 of 40 | 38 of 40 | ENC-6 |
| AKS-3 | 24 of 38 | 30 of 38 | ENC-5, ENC-6, ENC-8, EDS-4 |
| AKS-4 | 20 of 33 | 26 of 33 | ENC-5, ENC-6 |
| AKS-5 | 21 of 34 | 28 of 34 | ENC-5, ENC-8 |
| AKS-6 | 22 of 27 | 24 of 27 | ENC-5, EDS-4 |
| CTR-7 | 6 of 7 | 6 of 7 | ENC-5 |
| CTR-12 | 2 of 3 | not listed | ENC-5 |
| RPS-3 | 2 of 4 | 4 of 4 | EDS-4 |
| DIN-15 | WLD-B-04 seed test and SF-10 grid row wait | not listed | DIN-9 |
| DIN-16 | REQ-UX-021 step and SF-10:detail capture wait | not listed | DIN-9 |
| DIN-17 | SF-11:item capture waits | not listed | DIN-9 |
| SUP-RC-SMOKE | RC-SMOKE.4 waits | not listed | DIN-9 |

AKS-1 (33 keys) and AKS-7 (16 keys) are fully runnable.

### 3.4 Reviewed edges

| Item → dependency | Derived by | Ruling |
|---|---|---|
| CTR-22 → CTR-14 | validator `api-bind` | API-R-28 has several producers. SF-03 binds the contract reads of CTR-4, not the CTR-14 usage-commitment and cost routes. Not a dependency |
| CLO-13 → DIN-14 | validator `dir` | `backend/erev_api/adapters/gl/` does not exist on `main`; CLO-13 creates the package. This is the same ruling as `plan_tools.py` `IGNORED_AUTO_EDGES` |
| RPS-22 → CLO-6 | validator `api-bind` | API-R-09 is the approvals row of PLF and WEB-15. CLO-6 only adds lock execution on approval |
| RPS-7 → CLO-6, CLO-7 | validator `api-bind` | SF-04 binds `GET /periods` (RFD-1, blockers from CLO-4). Lock and reopen routes are not called |

## 4. Levels and lanes

### 4.1 Overview

The generated block (§10) holds the overview, the lane tables, merge orders, re-parenting and merge gates. Lane ids are `L<level>-<n>` in merge order.

| Level | Hours (cumulative) | Lanes | Migration lanes | Integration after merge |
|---|---|---:|---|---|
| L1 (fixed) | 4.6 (4.6) | 5 | L1-1 | none |
| L2 | 4.8 (9.3) | 5 | L2-1 | END-1 on ENC-15 |
| L3 | 5.5 (14.8) | 3 | L3-1 | CTR-2 on END-9, END-10, EDS-1; CTR-3 and CTR-4 on END-9 (V-C) |
| L4 | 5.0 (19.8) | 5 | L4-1, L4-2 | none |
| L5 | 5.2 (25.1) | 4 | L5-1, L5-2 | none |
| L6 | 5.3 (30.4) | 5 | L6-1 | DIN-15, DIN-16 on DIN-10; DIN-17 on DIN-11; CLO-26 on CLO-8, CLO-11, CLO-13 |
| L7 | 4.7 (35.1) | 3 | none | RPS-6, RPS-7 on RPS-5; RPS-7 on CLO-4; RPS-22 on RPS-6, RPS-7; SUP-RC-SMOKE on RPS-22 |

### 4.2 Execution

- Lane n of any level runs in `~/dev/erev-wt/l<n>`, with that worktree's databases `erev_rv_l<n>_{dev,test,e2e}` and its `.env` ports (D-81). The lane branches from the previous level's merge commit.
- Idle worktrees: l4 and l5 in L3 and L7, and l5 in L5. The merge step may use them for fix batches. Moving work into them would not shorten any level, because the longest lane sets the level length.
- The ceremony, evidence and spec-question numbering of D-81 and SPRINT-1.0rc.md §4.1 apply unchanged.

### 4.3 Declared exception and fallback

L5-1 holds DIN-2, DIN-3, DIN-4, DIN-5, DIN-6 and GPA-1 for 245 min, 5 min above the lane box. Placing DIN-6 in L5 lets L6 carry CLO-9, DIN-7 and DIN-8, which shortens L7-1 from 240 min to 170 min.

Compliant fallback, if L5-1 runs late or the exception is refused:

- DIN-6 moves to the head of L6-2;
- CLO-9 and DIN-8 move to L7-1, which becomes DIN-8, GPA-6, CLO-9, RPS-5, GPB-1, GPB-2 (240 min).

L5 drops by 5 min and L7 grows by 60 min, giving 36.0 h.

### 4.4 Why L3 and L7 run three lanes

- **L3.** RFD-11 and RFD-14 sit in the migration lane before CTR-2, because CTR-2 pins policy versions and resolves SSP versions (hard edges). RFD-16 needs RFD-11, so it moves to L4-4, ahead of the reference-data screens. This change unlocks CTR-2 to CTR-4 one level earlier than V-0.
- **L7.** The only work left after L6 is the GPB journal totals, the home chain and the report screens.

## 5. Merge procedure

### 5.1 Per level

SPRINT-1.0rc.md §6 applies, with these changes:

1. Merge order: lane 1 (schema chain A), then lane 2 when it is schema chain B (re-parented, §5.2), then engine and sweep lanes, then parity and platform lanes, and frontend lanes last. `merge_order` in `plan-vabc.json` is binding.
2. In L4 and L5, run `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"` right after merging lane 2 and before merging lane 3.
3. After the last lane: `make openapi`, the ticks in `PROGRESS.md`, spec-question renumbering, then the level's `merge_gates` on a clean tree.
4. Integration-after-merge defects are fixed on `main` with their own test (DG-GATE-02). In L2 to L6 the fix may instead become the first batch of the next level (D-81). In L7 no next level exists, so the fix happens before the tag.

### 5.2 Re-parenting a second migration lane (V-A)

Both migration lanes of L4 and L5 branch from the same level base and run `make revision` normally. A lane never renumbers itself. The plan has no hard edge between the two lanes of a level, so no revision of lane 2 references an object created by lane 1 in the same level.

| Step | Action |
|---|---|
| 1 | Merge lane 1 (`--no-ff`). Its revisions keep their numbers |
| 2 | Merge lane 2 with `--no-ff --no-commit`. Rename its `versions/NNNN_<slug>.py` files to the numbers after lane 1's head, in the lane's commit order |
| 3 | In each renamed file, set `revision = "<new NNNN>"` and `down_revision` to the previous revision; the first points at lane 1's head. Docstrings keep their item ids |
| 4 | In `backend/tests/pg/test_migrations.py`, set the `test_single_head` literal to the new head. Set the `test_upgrade_downgrade_upgrade` function count to the base count plus the functions added by both lanes, and take the union of the comment lines |
| 5 | Union the files of SPRINT-1.0rc.md §4.3: `db/tables/__init__.py`, `tests/support/rows.py`, `test_rls_isolation.py`, `test_db_invariants.py`, `test_immutability_and_grants.py`, `provisioning.py`, `transitions.py` |
| 6 | Grep lane 2's files for its old revision numbers (tests, docstrings, guides) and correct them. Commit the merge |
| 7 | Run the §5.1 step 2 gate. A red result is fixed in the merge step, not sent back to the lane |

| Level | Lane 1 revisions (base) | Lane 2 revisions (re-parented) |
|---|---|---|
| L4 | CTR-5, CTR-7, CTR-10, DIN-1 | CTR-15, CLO-1, CLO-2, RPS-1 |
| L5 | DIN-2, DIN-4 | CTR-12 |

### 5.3 Shared files added for V-ABC

Every rule of SPRINT-1.0rc.md §4.3 still applies. These files are added:

| File | Rule |
|---|---|
| `backend/erev_api/db/migrations/versions/` | Two lanes may add revisions in L4 and L5; the merge step re-parents lane 2 (§5.2) |
| `backend/tests/pg/test_migrations.py` | Head literal and function count set by the merge step (§5.2 step 4); union of comment lines |
| `backend/tests/pg/test_catalogue_lint.py` | Union of test functions; most items only run the DB-14 lint after their revision |

### 5.4 Merge gates

The gates are cumulative, and `plan-vabc.json` holds the full selections.

| Gate | Levels |
|---|---|
| `git status --porcelain` empty; `make openapi` diff clean; `make ci`; `make test-pg` | every level |
| `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"` after re-parenting | L4, L5 |
| `make properties K=…` of every merged item | L2 onward |
| `make answer-keys ID=…`: keys named by merged items, less blocked keys | L3 onward |
| `make parity K=…`: merged GPA and GPB selections | L5 (initial allocation), L6 (steps 04 to 14), L7 (GATE-GPA selection and journal totals) |
| `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` | every level that merges screens (L3 to L7) |
| `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts` (SUP-RC-SMOKE) | L7 |

## 6. Release gate for the rc (V-ABC)

Run on a clean tree after the L7 merge commit.

| Gate | Command | Pass criterion |
|---|---|---|
| OpenAPI current | `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts` | No diff |
| CI | `make ci` | Five stages pass |
| Isolation and immutability | `make test-pg` | Every `pg` test passes, none skipped |
| Engine properties | `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"` | Every selected property passes under `thorough` |
| Answer keys | `make answer-keys ID=<release_gate.answer_keys.runnable_engine_runner_ids>` | 176 of 176 pass |
| Golden parity | `make parity K="not point_in_time_equivalence"` | 121 of 122 pass, none skipped |
| Screens | `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` | Every row of an in-scope screen item passes, less the fragments of §6.2, with no serious or critical axe violation; both themes read against SCREENS |
| Smoke journey | `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts` | RC-SMOKE.1 to RC-SMOKE.10 pass, less RC-SMOKE.4 until DIN-9 lands or the supervisor rules (§8 R-06) |

The supervisor verification of SPRINT-1.0rc.md §7.4 is unchanged: by-hand `docker build` and `docker compose config`, and multi-role browser QA as `maya`, `priya`, `marcus` and `robert`.

### 6.1 Answer-key selection

| Change | Keys | Reason |
|---|---|---|
| Removed from the runnable list | `DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION`, `DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE` (named by RPS-3); `JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP` (AKS-6); `VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE` (AKS-3) | Each asserts measure `revenue_prior_period` (ENGINE_SPEC_B §15.2.4), which EDS-4 produces |
| Families no longer fully or equally runnable | DISC 4 of 8 (was 6), JE 10 of 12 (was 11), VC 9 of 14 (was 10) | as above |
| Id format | All 176 ids unquoted | `plan_tools.key_facts` keeps YAML quotes (`^id:\s*(\S+)`). `plan.json` lists 87 of its 180 ids with literal quotes, and its blocked-key filter misses 21 quoted blocked ids, so its merge gates from L4 onward select keys that cannot pass. The scratch copy strips the quotes; the normalised V-0 set equals the validator's 180 |

The merge gates select the runnable keys named by merged items: 4 at L3, 99 at L4, 172 at L5, and 176 at L6 and L7. The L6 and L7 selections equal the release list.

### 6.2 Screens hidden under R-RC-1

| Item | Hidden or substituted fragment |
|---|---|
| CLO-23 | `sf-05-locked`; SF-05 captures the FY2026-P09 open cockpit only |
| CLO-26 | Seeded runs and acknowledged batches; the run is created in `beforeAll`, and SF-06:run-batches shows CSV export |
| RPS-6 | `sf-08-report-rpo-locked` |
| RPS-7 | `sf-04-locked`; SF-06:entries reads the `beforeAll` run instead of seeded Aug 2026 history |
| CTR-22 | Void and regroup drawers |
| CTR-23 | SF-03:billing billing plan and the SF-03:schedules contract-costs panel |

Not green until DIN-9 (CSV v2 `progress_events`) lands, unless the supervisor rules otherwise (§8 R-06):

| Item | Fragment waiting for DIN-9 |
|---|---|
| DIN-15 | WLD-B-04 seed test and the SF-10 grid row of `avm-us-progress-2026-09-invalid.csv` |
| DIN-16 | REQ-UX-021 job-progress step on WLD-F-21; SF-10:detail WLD-B-04 capture |
| DIN-17 | SF-11:item WLD-B-04 capture |
| SUP-RC-SMOKE | RC-SMOKE.4 |

## 7. SUP-RC-SMOKE

- **Placement.** Lane L7-3, batch 3 (70 min), after RPS-6 and RPS-7. The supervisor appends the text of `sup-rc-smoke.md` before L7 starts.
- **Journey.** Ten steps on WLD-T-01: sign-in with MFA; a legacy v1 SKU SSP import with maker-checker approval, plus the WLD-B-04 legacy progress findings; the K-01 workbench and Explain; schedules (K-01 O1 FY2026-P09 9,764.38, K-02 9,863.01, SF-04); a Sep 2026 journal run calculated, submitted, approved and exported to CSV, with the batch download manifest; and the revenue waterfall and RPO reports (K-09 105,043.80).
- **Integration.** It codes against the RPS-22 landing route and rail (lane L7-2) and turns green in the L7 merge gate.
- **Assumptions.** Its notes N-3 and N-4 record the two assumptions to confirm: the SKU SSP template commits on a tenant without the legacy preset, and the waterfall tie-out is asserted as present, not as Pass.
- **Validator finding.** `sup-rc-smoke.md` describes the WLD-B-04 import of RC-SMOKE.4 as a legacy v1 progress import. SCREENS §12.2 shows it as Progress events (CSV v2), whose emitter is deferred DIN-9. RC-SMOKE.4 waits for DIN-9 or a ruling (§8 R-06). The supervisor corrects the item text before appending it.

## 8. Risks

| Id | Risk | Effect | Mitigation |
|---|---|---|---|
| R-01 | L5-1 runs at 245 min, 5 min over the lane box | L5 runs longer | Fallback §4.3 (+0.9 h in total) |
| R-02 | Re-parenting defects: the hard-coded head literal and function count, and old revision numbers in tests or docs | Red `test-pg` in L4 or L5 | §5.2 steps 4 to 6 and the targeted `test-pg` before lane 3 merges. No same-level hard edge exists between the two migration lanes |
| R-03 | V-C in L3: CTR-2, CTR-3 and CTR-4 code against a fake of `erev_engine.compute` | Their number-asserting tests (K-01 9,764.38; K-11 53,504.59 EUR; SF-ORD-20417 97,627.12) turn green only in the L3 merge gate | A fix batch in L4-4, which holds only CTR-19 (35 min) |
| R-04 | Last-level integration: RPS-6 and RPS-7 on RPS-5, RPS-22 on the report screens, SUP-RC-SMOKE on RPS-22 | L7 merge fixes lengthen the final merge; there is no next level | 40 min budgeted. RPS-5's `legacy_je_summary` and export schemas are 04 API contracts |
| R-05 | The answer-key blocker classifier is heuristic (ENC-5, ENC-6, ENC-8, PRP-1, and now EDS-4 by measure) | The 176-key selection may shift | The L4 gate is the first sweep run; regenerate the release list from the scratch tools after corrections |
| R-06 | DIN-9 is deferred, but DIN-15 seeds WLD-B-04 through a Progress events (CSV v2) upload (SCREENS §12.2), and DIN-16's REQ-UX-021 step uploads WLD-F-21 with that template (PRD J-04.1). V-0 carried the same gap | DIN-15, DIN-16, DIN-17 and SUP-RC-SMOKE run as partial items; the WLD-B-04 captures and RC-SMOKE.4 are not green | Supervisor ruling before L6: (1) keep the partial items, as validated; (2) seed WLD-B-04 and run REQ-UX-021 through the legacy v1 progress template (DIN-5), with a SPEC-Q under XR-14; or (3) bring a `progress_events` slice of DIN-9 into scope, which needs a new layout |
| R-07 | Loop-order edges not satisfied by position (§9) may hide dependencies the item text does not name | Red lane gates | Lane gates and cumulative merge gates. None is corroborated without a review entry |
| R-08 | SUP-RC-SMOKE assumptions (sup-rc-smoke.md N-3 to N-5) | RC-SMOKE.2, RC-SMOKE.3 or later DMO journeys are affected | A SPEC-Q and unticked steps. Remove `rcSmoke()` when DMO appends the E2E-04 journeys |
| R-09 | L6 runs two e2e lanes (L6-4, L6-5), and L4 and L5 run e2e alongside the sweeps, on a shared machine | Memory pressure and seeding time (SZ-06) | PRE-3 to PRE-5 of SPRINT-1.0rc.md; PID-file process control |
| R-10 | Estimates use the V-0 cost model; the 10-minute re-parenting cost is a planner estimate | Levels may run longer | Level lengths are set by the longest lane, which the lane boxes cap |
| R-11 | Edges are re-derived from item text. Hidden seed and fixture dependencies, such as R-06, surface only by reading | Red lane or merge gates | Cumulative merge gates; rerun `validate_vabc.py check` after any BUILD_SPEC or plan change |

## 9. Validation

Independent validator `validate-vabc`, 2026-09-13. `python3 -B docs/build-spec/sprint/validate_vabc.py check` runs checks (a) to (g); `record` writes them to `plan-vabc.json` `validation`. The script does not import the planner's generator.

### 9.1 Method

| Source | Use |
|---|---|
| `validate_plan.py` parser | Item blocks, derived edges, migration items, file touches, loop-order corroboration, §4.3 rules and the cost table, from BUILD_SPEC, the tree and `git log` |
| `plan_tools.py` literals, read with `ast` | `MANUAL_EDGES` as a second edge set; `RULING_R_RC_1`; `API_SCREEN_CONTRACTS`; `CORRECTION_ITEMS` |
| D-82; SPRINT-1.0rc.md §3.1, §3.2; `sup-rc-smoke.md` | Moved items, forced prerequisites, excluded roots, supervisor item edges |
| Item text read by the validator | `VABC_VERIFIED` edges, `PARTIAL` fragments and `REVIEWED` entries in the script |

| Check | Rule |
|---|---|
| (a) | Each edge of an L2+ item is done, in L1, at an earlier level or earlier in its lane. A same-level cross-lane edge needs an integration note and a contract kind: engine state type, 04 API binding of a screen, or V-C (platform on engine). Integration notes must join two lanes of their level |
| (b) | No in-scope item, L1 included, has a hard or corroborated edge to a deferred item, except R-RC-1 dropped edges, reviews and noted partial fragments. The moved set equals D-82, and each dropped edge carries its R-RC-1 note |
| (c) | Capabilities C1 to C11, the D-81 scope, the §3.1 forced prerequisites (in scope or moved), the §3.2 exclusions, and SUP-RC-SMOKE in the last level |
| (d) | At most two migration lanes, merged first and second, the second re-parented and no edge between them. Cross-lane overlaps only on §4.3 files, or on the V-A files between the two migration lanes. Correction scope kept apart |
| (e) | Batches of 1 to 4 items and at most 75 min; at most 5 lanes; ids and worktrees in merge order; migration lanes first, lanes with screens last; lane box 240 min unless declared with a fallback |
| (f) | Each in-scope item once; the 427 items partitioned; in scope = V-0 scope less the moved items |
| (g) | Batch, lane and level minutes; cumulative hours; merge gates (re-parenting, properties, answer keys, parity, e2e); release keys recomputed from the answer-key files |

### 9.2 Findings and changes

| Id | Check | Finding | Change |
|---|---|---|---|
| VV-01 | (e) | L4-5 (CTR-19, backend only) merged after L4-4, a lane with screens | Lanes swapped. L4-4 is CTR-19 in `~/dev/erev-wt/l4`; L4-5 holds RFD-16, RFD-19, RFD-22 and RFD-24 in `~/dev/erev-wt/l5` |
| VV-02 | (a) | CTR-3 and CTR-4 (L3-1) assert figures computed by `erev_engine.compute` (END-9, L3-2): K-11 O1 53,504.59 EUR, and the SF-ORD-20417 allocation walk 97,627.12. Only CTR-2 carried a V-C note | Integration notes CTR-3 on END-9 and CTR-4 on END-9 (V-C), with batch notes. L3 grows by 20 min to 5.5 h; the total grows from 34.8 h to 35.1 h |
| VV-03 | (b) | DIN-9 is deferred, and DIN-3 creates only the customers and contracts emitters. DIN-15 seeds WLD-B-04 through a Progress events (CSV v2) upload (SCREENS §12.2). DIN-16's REQ-UX-021 step uploads WLD-F-21 with that template (PRD J-04.1). DIN-17 and RC-SMOKE.4 read WLD-B-04. The planner's note had DIN-16 substitute a legacy v1 file without a ruling | DIN-15, DIN-16, DIN-17 and SUP-RC-SMOKE become partial items (§3.3, §6.2), and the substitution note is removed. `release_gate.e2e` and `deferred_notes.DIN-9` record the fragments. Decision requested (§8 R-06) |
| VV-04 | (g) | The L6 parity gate selected `journal_entry_totals`, whose value source GPB-1 merges in L7; the L7 gate named GPB-2 indirectly | The L5 to L7 parity gates are rebuilt as the union of the merged items' Golden selections |

Confirmed without change:

- the 144-item scope, the D-82 moved set and the 203 deferred items;
- the five review entries of §3.4, plus the V-0 validator's `SERIAL_REVIEW`;
- the V-A pairs of L4 and L5. No edge joins the two lanes; the only cross-lane V-A file is `test_catalogue_lint.py` in L4;
- 37 cross-lane overlaps, all on §4.3 regenerate or union files;
- 176 runnable engine-runner keys (232 active, 56 blocked), equal to the release list. Every merge-gate selection sits inside it;
- the L5-1 lane-box exception (245 min), declared with a compliant fallback (§4.3). The 240-minute box is a packing rule of SPRINT-1.0rc.md §2.5, not a D-81 or D-82 rule;
- three uncorroborated loop-order edges not satisfied by position: RFD-12 on RFD-11, RFD-15 on RFD-14, and CLO-9 on CLO-8. CLO-9 adds `journals/views.py` over subledger lines and names no CLO-8 file or symbol.

### 9.3 Open items

| Id | Item | Owner |
|---|---|---|
| OI-1 | Ruling R-06 before L6 | Supervisor |
| OI-2 | Correct RC-SMOKE.4 in `sup-rc-smoke.md` (WLD-B-04 is a CSV v2 import) before appending | Supervisor |
| OI-3 | Rerun `validate_vabc.py check` after any BUILD_SPEC change or plan edit | Merge step |

The results table sits in the generated block.

## 10. Generated tables

The block below is rewritten by `python3 -B .scratch/sprint-vabc/evaluate.py fill` from `plan-vabc.json`. Do not edit it by hand.

<!-- generated by .scratch/sprint-vabc/evaluate.py: begin -->

| Level | Hours (cumulative) | Lanes and items |
|---|---|---|
| L1 (fixed) | 4.6 (4.6) | L1-1 schema: RFD-1, RFD-6, RFD-2, RFD-3, RFD-8 · L1-2: ENA-1, ENA-2, ENA-3, ENA-5, ENB-1, ENA-6, ENA-10, ENA-11 · L1-3: ENC-1, ENC-2, ENC-3, ENC-4, ENC-7, ENC-9, ENB-9, ENB-10 · L1-4: RFD-4, RFD-5, WEB-8, WEB-9, DEP-1, DEP-2 · L1-5: WEB-10 |
| L2 | 4.8 (9.3) | L2-1 schema: RFD-7, RFD-9, RFD-12, RFD-13, RFD-10, RFD-15 · L2-2: ENA-4, ENA-7, ENA-8, ENA-9, ENA-12, ENA-13 · L2-3: ENB-2, ENB-3, ENB-4, ENB-5, ENB-6, ENB-7, ENB-8 · L2-4: ENC-10, ENC-11, ENC-12, ENC-13, ENC-14, ENC-15, ENC-16 · L2-5: ENB-11, ENB-12, END-1, END-2, END-3, END-4, END-5, END-6 |
| L3 | 5.5 (14.8) | L3-1 schema: RFD-11, RFD-14, CTR-1, CTR-2, CTR-3, CTR-4 · L3-2: ENB-13, END-7, END-8, END-9, END-10, EDS-1, EDS-2 · L3-3: WEB-11, WEB-12, WEB-15, WEB-17 |
| L4 | 5.0 (19.8) | L4-1 schema: CTR-5, CTR-7, CTR-8, CTR-9, CTR-10, DIN-1 · L4-2 schema: CTR-15, CLO-1, CLO-2, RPS-1 · L4-3: EDS-3, AKS-1, AKS-2, AKS-3 · L4-4: CTR-19 · L4-5: RFD-16, RFD-19, RFD-22, RFD-24 |
| L5 | 5.2 (25.1) | L5-1 schema: DIN-2, DIN-3, DIN-4, DIN-5, DIN-6, GPA-1 · L5-2 schema: CTR-12, RPS-2 · L5-3: AKS-4, AKS-5, AKS-6, AKS-7 · L5-4: CTR-20, CTR-21, CTR-22, CTR-23 |
| L6 | 5.3 (30.4) | L6-1 schema: DIN-7, DIN-10, DIN-8, DIN-11 · L6-2: GPA-2, GPA-3, GPA-4, GPA-5, CLO-9 · L6-3: CLO-3, CLO-8, CLO-11, CLO-13, RPS-3, RPS-4 · L6-4: CTR-26, DIN-15, DIN-16, DIN-17 · L6-5: CLO-26 |
| L7 | 4.7 (35.1) | L7-1: GPA-6, RPS-5, GPB-1, GPB-2 · L7-2: CLO-4, CLO-23, RPS-17, RPS-22 · L7-3: RPS-6, RPS-7, SUP-RC-SMOKE |

#### L2: about 4.8 h (cumulative 9.3 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L2-1 | `~/dev/erev-wt/l1` | Schema chain A: reference data revisions | yes (240 min) | B1: RFD-7 (40)<br>B2: RFD-9 (40)<br>B3: RFD-12 (40)<br>B4: RFD-13 (40)<br>B5: RFD-10 (40)<br>B6: RFD-15 (40) | RFD-7 adds a revision (make revision ITEM=RFD-7)<br>RFD-9 adds a revision (make revision ITEM=RFD-9)<br>RFD-12 adds a revision (make revision ITEM=RFD-12)<br>RFD-13 adds a revision (make revision ITEM=RFD-13)<br>RFD-10 adds a revision (make revision ITEM=RFD-10)<br>RFD-15 adds a revision (make revision ITEM=RFD-15) |
| L2-2 | `~/dev/erev-wt/l2` | Engine: stages 03 to 05 and the inception fold | no (190 min) | B1: ENA-4, ENA-7 (60)<br>B2: ENA-8, ENA-9 (60)<br>B3: ENA-12, ENA-13 (70) |  |
| L2-3 | `~/dev/erev-wt/l3` | Engine: stage 06 modifications | no (210 min) | B1: ENB-2, ENB-3 (60)<br>B2: ENB-4, ENB-5 (60)<br>B3: ENB-6, ENB-7 (60)<br>B4: ENB-8 (30) |  |
| L2-4 | `~/dev/erev-wt/l4` | Engine: stages 09 to 11 | no (210 min) | B1: ENC-10, ENC-11 (60)<br>B2: ENC-12, ENC-13 (60)<br>B3: ENC-14, ENC-15 (60)<br>B4: ENC-16 (30) |  |
| L2-5 | `~/dev/erev-wt/l5` | Engine: stage 08 late events and stages 12 to 14 | no (240 min) | B1: ENB-11, ENB-12 (60)<br>B2: END-1, END-2 (60)<br>B3: END-3, END-4 (60)<br>B4: END-5, END-6 (60) | END-1 integration-after-merge: codes against the contract of ENC-15 (s12 consumes the CostLossState type of s11) |

Merge order: L2-1 → L2-2 → L2-3 → L2-4 → L2-5

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05"`

#### L3: about 5.5 h (cumulative 14.8 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L3-1 | `~/dev/erev-wt/l1` | Schema chain A: policy set, SSP resolution and the contracts core | yes (240 min) | B1: RFD-11, RFD-14 (70)<br>B2: CTR-1 (40)<br>B3: CTR-2 (50)<br>B4: CTR-3 (45)<br>B5: CTR-4 (35) | CTR-1 adds a revision (make revision ITEM=CTR-1)<br>CTR-2 integration-after-merge: codes against the contract of END-10 (computation.persist stores compute output bundles (DG-CMD-10)) (V-C: ENGINE_SPEC §0.5 with fakes); CTR-2 integration-after-merge: codes against the contract of EDS-1 (contract_version.rpo_amount comes from stage 15) (V-C: ENGINE_SPEC §0.5 with fakes); CTR-2 integration-after-merge: codes against the contract of END-9 (computed versions persist(uow, bundle, output) the result of erev_engine.compute (END-9)) (V-C: ENGINE_SPEC §0.5 with fakes); CTR-2 adds a revision (make revision ITEM=CTR-2); CTR-2 V-C: persists the ENGINE_SPEC §0.5 OutputBundle through a fake of erev_engine.compute until the L3 merge; its number-asserting tests turn green in the L3 merge gate<br>CTR-3 integration-after-merge: codes against the contract of END-9 (persists the postings of a computed K-11 (O1 53,504.59 EUR)) (V-C: ENGINE_SPEC §0.5 with fakes); CTR-3 V-C: its number-asserting tests turn green in the L3 merge gate; CTR-3 adds a revision (make revision ITEM=CTR-3)<br>CTR-4 integration-after-merge: codes against the contract of END-9 (reads computed versions, KPIs and the allocation walk (97,627.12)) (V-C: ENGINE_SPEC §0.5 with fakes); CTR-4 V-C: its number-asserting tests turn green in the L3 merge gate |
| L3-2 | `~/dev/erev-wt/l2` | Engine: boundary fold, books and compute, stage 15 | no (235 min) | B1: ENB-13, END-7 (70)<br>B2: END-8, END-9 (75)<br>B3: END-10, EDS-1 (60)<br>B4: EDS-2 (30) |  |
| L3-3 | `~/dev/erev-wt/l3` | Frontend: e2e harness, sign-in, MFA, approvals and settings | no (235 min) | B1: WEB-11 (70)<br>B2: WEB-12 (55)<br>B3: WEB-15 (55)<br>B4: WEB-17 (55) |  |

Merge order: L3-1 → L3-2 → L3-3

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS  # 4 keys named by merged items must pass`
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L4: about 5.0 h (cumulative 19.8 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L4-1 | `~/dev/erev-wt/l1` | Schema chain A: contract events, Step 1, combination, activation, holds and the import registry | yes (230 min) | B1: CTR-5 (40)<br>B2: CTR-7, CTR-8 (75)<br>B3: CTR-9, CTR-10 (75)<br>B4: DIN-1 (40) | CTR-5 adds a revision (make revision ITEM=CTR-5)<br>CTR-7 adds a revision (make revision ITEM=CTR-7); CTR-7 partial: 6 of 7 named keys runnable; the rest wait for deferred ENC-5; tick only when every key passes<br>CTR-10 adds a revision (make revision ITEM=CTR-10)<br>DIN-1 adds a revision (make revision ITEM=DIN-1) |
| L4-2 | `~/dev/erev-wt/l2` | Schema chain B (re-parented onto L4-1 at merge): obligation overrides, journal, close and report tables | yes (160 min) | B1: CTR-15 (40)<br>B2: CLO-1 (40)<br>B3: CLO-2 (40)<br>B4: RPS-1 (40) | revisions re-parented onto the head of L4-1 at merge (V-A, SPRINT-vabc.md §5.2)<br>CTR-15 adds a revision (make revision ITEM=CTR-15); re-parented onto L4-1 at merge<br>CLO-1 adds a revision (make revision ITEM=CLO-1); re-parented onto L4-1 at merge<br>CLO-2 adds a revision (make revision ITEM=CLO-2); re-parented onto L4-1 at merge<br>RPS-1 adds a revision (make revision ITEM=RPS-1); re-parented onto L4-1 at merge |
| L4-3 | `~/dev/erev-wt/l3` | Engine: stage 15 rollforward and answer-key sweeps 1 to 3 | no (210 min) | B1: EDS-3 (30)<br>B2: AKS-1 (60)<br>B3: AKS-2 (60)<br>B4: AKS-3 (60) | AKS-2 partial: 36 of 40 named keys runnable; the rest wait for deferred ENC-6; tick only when every key passes<br>AKS-3 partial: 24 of 38 named keys runnable; the rest wait for deferred EDS-4, ENC-5, ENC-6, ENC-8; tick only when every key passes |
| L4-4 | `~/dev/erev-wt/l4` | Platform: calculation trace store and explain routes | no (35 min) | B1: CTR-19 (35) | CTR-19 R-RC-1: explain history estimate-pair test moves with CTR-12 (CTR-12 post-rc; SPEC-Q under XR-14) |
| L4-5 | `~/dev/erev-wt/l5` | Platform and frontend: reference seed and reference-data screens | no (225 min) | B1: RFD-16 (60)<br>B2: RFD-19 (55)<br>B3: RFD-22 (55)<br>B4: RFD-24 (55) |  |

Merge order: L4-1 → L4-2 → L4-3 → L4-4 → L4-5

Re-parenting: L4-2 (CTR-15, CLO-1, CLO-2, RPS-1) onto L4-1 (CTR-5, CTR-7, CTR-10, DIN-1).

Merge gates:

- `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"  # right after merging L4-2 re-parented onto L4-1, before L4-3`
- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD …` (full selection in plan-vabc.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L5: about 5.2 h (cumulative 25.1 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L5-1 | `~/dev/erev-wt/l1` | Schema chain A: source records, dry-run diff, legacy v1 templates and the first parity replay | yes (245 min) | B1: DIN-2, DIN-3 (75)<br>B2: DIN-4, DIN-5 (75)<br>B3: DIN-6 (35)<br>B4: GPA-1 (60) | 245 minutes: 5 minutes above the lane box, declared exception (SPRINT-vabc.md §4.3 fallback)<br>DIN-2 adds a revision (make revision ITEM=DIN-2)<br>DIN-4 adds a revision (make revision ITEM=DIN-4) |
| L5-2 | `~/dev/erev-wt/l2` | Schema chain B (re-parented onto L5-1 at merge): estimates and the report run framework | yes (85 min) | B1: CTR-12 (40)<br>B2: RPS-2 (45) | revisions re-parented onto the head of L5-1 at merge (V-A, SPRINT-vabc.md §5.2)<br>CTR-12 adds a revision (make revision ITEM=CTR-12); re-parented onto L5-1 at merge; CTR-12 partial: 2 of 3 named keys runnable; the rest wait for deferred ENC-5; tick only when every key passes |
| L5-3 | `~/dev/erev-wt/l3` | Engine: answer-key sweeps 4 to 7 | no (240 min) | B1: AKS-4 (60)<br>B2: AKS-5 (60)<br>B3: AKS-6 (60)<br>B4: AKS-7 (60) | AKS-4 partial: 20 of 33 named keys runnable; the rest wait for deferred ENC-5, ENC-6; tick only when every key passes<br>AKS-5 partial: 21 of 34 named keys runnable; the rest wait for deferred ENC-5, ENC-8; tick only when every key passes<br>AKS-6 partial: 22 of 27 named keys runnable; the rest wait for deferred EDS-4, ENC-5; tick only when every key passes |
| L5-4 | `~/dev/erev-wt/l4` | Platform and frontend: Avenmoor key contracts seed and the contracts screens | no (225 min) | B1: CTR-20 (60)<br>B2: CTR-21 (55)<br>B3: CTR-22 (55)<br>B4: CTR-23 (55) | CTR-20 R-RC-1: K-06 estimate versions seeded post-rc (CTR-12 post-rc; SPEC-Q under XR-14); CTR-20 R-RC-1: K-09 commission cost seeded post-rc (CTR-14 post-rc; SPEC-Q under XR-14)<br>CTR-22 R-RC-1: void drawer hidden (XR-14) (CTR-11 post-rc; SPEC-Q under XR-14); CTR-22 R-RC-1: regroup drawer hidden (XR-14) (CTR-17 post-rc; SPEC-Q under XR-14)<br>CTR-23 R-RC-1: billing tab without billing plan and usage commitments; costs panel hidden (CTR-14 post-rc; SPEC-Q under XR-14) |

Merge order: L5-1 → L5-2 → L5-3 → L5-4

Re-parenting: L5-2 (CTR-12) onto L5-1 (DIN-2, DIN-4).

Merge gates:

- `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"  # right after merging L5-2 re-parented onto L5-1, before L5-3`
- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD …` (full selection in plan-vabc.json)
- `make parity K="(initial_allocation)"`
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L6: about 5.3 h (cumulative 30.4 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L6-1 | `~/dev/erev-wt/l1` | Schema chain A: template defects, mapping profiles and exception queue | yes (145 min) | B1: DIN-7, DIN-10 (75)<br>B2: DIN-8, DIN-11 (70) | DIN-10 adds a revision (make revision ITEM=DIN-10) |
| L6-2 | `~/dev/erev-wt/l2` | Golden parity: steps 04 to 14 and the legacy journal views | no (215 min) | B1: GPA-2 (45)<br>B2: GPA-3 (45)<br>B3: GPA-4 (45)<br>B4: GPA-5 (45)<br>B5: CLO-9 (35) |  |
| L6-3 | `~/dev/erev-wt/l3` | Platform: soft close, journal runs, CSV export, waterfall and RPO reports | no (210 min) | B1: CLO-3, CLO-8 (70)<br>B2: CLO-11, CLO-13 (70)<br>B3: RPS-3, RPS-4 (70) | CLO-11 R-RC-1: reopened-period approval test moves with CLO-7 (CLO-7 post-rc; SPEC-Q under XR-14); CLO-13 creates backend/erev_api/adapters/gl/__init__.py beside csv.py (DIN-14 deferred; reviewed edge)<br>RPS-3 partial: 2 of 4 named keys runnable; the rest wait for deferred EDS-4; tick only when every key passes; RPS-3 R-RC-1: contract balances test uses k01 only; k03_castellan moves with CLO-7 (CLO-7 post-rc; SPEC-Q under XR-14); RPS-3 R-RC-1: revenue_from_prior_period_obligations (RPT-05) and its DISC keys move to post-rc (EDS-4 post-rc; SPEC-Q under XR-14); RPS-3 R-RC-1: as-locked run test moves with CLO-6; worlds.py k01 is created by RPS-3 (CLO-6 post-rc; SPEC-Q under XR-14); RPS-3 R-RC-1: CONTRACT_BALANCE_ROLLFORWARD reconciliation moves with CLO-16 (CLO-16 post-rc; SPEC-Q under XR-14); RPS-4 R-RC-1: worlds.py is created by RPS-3 in this variant (CLO-6 post-rc; SPEC-Q under XR-14); RPS-4 R-RC-1: rpo k02 test without the CR-MARROWBY-2026-09 modification (CTR-17 post-rc; SPEC-Q under XR-14); RPS-4 R-RC-1: k09 commission world moves with CTR-14 (CTR-14 post-rc; SPEC-Q under XR-14) |
| L6-4 | `~/dev/erev-wt/l4` | Frontend: explain panel and data-in screens | no (220 min) | B1: CTR-26 (55)<br>B2: DIN-15 (55)<br>B3: DIN-16 (55)<br>B4: DIN-17 (55) | DIN-15 integration-after-merge: codes against the contract of DIN-10 (queries/mapping-profiles.ts binds API-R-43 mapping profiles); DIN-15 partial: the WLD-B-04 seed test and the SF-10 grid row of the WLD-B-04 import wait for deferred DIN-9 (avm-us-progress-2026-09-invalid.csv is a Progress events (CSV v2) import, SCREENS §12.2); record a SPEC-Q; tick only when every step passes<br>DIN-16 integration-after-merge: codes against the contract of DIN-10 (validator [api-bind]: binds API-R-43 produced by DIN-10); DIN-16 partial: the REQ-UX-021 step on WLD-F-21 (Progress events (CSV v2), PRD J-04.1) and the SF-10:detail WLD-B-04 capture wait for deferred DIN-9; record a SPEC-Q; tick only when every step passes<br>DIN-17 integration-after-merge: codes against the contract of DIN-11 (binds API-R-44); DIN-17 partial: the SF-11:item capture of a WLD-B-04 item (seeded by DIN-15) waits for deferred DIN-9; record a SPEC-Q; tick only when every step passes |
| L6-5 | `~/dev/erev-wt/l5` | Frontend: journal run screens | no (55 min) | B1: CLO-26 (55) | CLO-26 integration-after-merge: codes against the contract of CLO-8 (binds API-R-38); CLO-26 integration-after-merge: codes against the contract of CLO-11 (approved runs); CLO-26 integration-after-merge: codes against the contract of CLO-13 (validator [api-bind]: binds API-R-38 produced by CLO-13); CLO-26 R-RC-1: SF-06 captures a run created in beforeAll through the API instead of seeded history (CLO-22 post-rc; SPEC-Q under XR-14); CLO-26 R-RC-1: run-batches capture shows CSV export without NetSuite acknowledgements (CLO-14 post-rc; SPEC-Q under XR-14); CLO-26 R-RC-1: no NetSuite mock acknowledgements (CLO-15 post-rc; SPEC-Q under XR-14) |

Merge order: L6-1 → L6-2 → L6-3 → L6-4 → L6-5

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD …` (full selection in plan-vabc.json)
- `make parity K="(initial_allocation) or (contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)) or (catchup-08 or catchup-09 or rollforward-08 or rollforward-09) or (catchup-10 or catchu …` (full selection in plan-vabc.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L7: about 4.7 h (cumulative 35.1 h)

| Lane | Worktree | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|---|
| L7-1 | `~/dev/erev-wt/l1` | Parity and reports: GATE-GPA selection, legacy exports and journal totals | no (170 min) | B1: GPA-6 (45)<br>B2: RPS-5 (35)<br>B3: GPB-1 (45)<br>B4: GPB-2 (45) |  |
| L7-2 | `~/dev/erev-wt/l2` | Platform and frontend: close cockpit, home read model and home screen | no (180 min) | B1: CLO-4 (35)<br>B2: CLO-23 (55)<br>B3: RPS-17 (35)<br>B4: RPS-22 (55) | CLO-23 R-RC-1: SF-05 captures the FY2026-P09 open cockpit only; the seeded locked FY2026-P08 capture moves to DMO (CLO-22 post-rc; SPEC-Q under XR-14); CLO-23 R-RC-1: no Locked chip capture until CLO-6 lands (CLO-6 post-rc; SPEC-Q under XR-14)<br>RPS-22 integration-after-merge: codes against the contract of RPS-6 (rail destination Reports); RPS-22 integration-after-merge: codes against the contract of RPS-7 (rail destination Schedules) |
| L7-3 | `~/dev/erev-wt/l3` | Frontend: report viewer, schedules and the rc smoke journey | no (180 min) | B1: RPS-6 (55)<br>B2: RPS-7 (55)<br>B3: SUP-RC-SMOKE (70) | RPS-6 integration-after-merge: codes against the contract of RPS-5 (legacy export capture); RPS-6 R-RC-1: the rpo as-locked capture moves to DMO (CLO-22 post-rc; SPEC-Q under XR-14)<br>RPS-7 integration-after-merge: codes against the contract of RPS-5 (binds legacy_je_summary); RPS-7 integration-after-merge: codes against the contract of CLO-4 (GET /periods with blockers); RPS-7 R-RC-1: the SF-04 as-locked capture moves to DMO (CLO-22 post-rc; SPEC-Q under XR-14); RPS-7 under R-RC-1: the SF-06:entries step reads a journal run created in beforeAll through the API, not seeded Aug 2026 history<br>SUP-RC-SMOKE integration-after-merge: codes against the contract of RPS-22 (supervisor item: landing route /home and the completed rail (BS-D-08; SCREENS SCR-IA-01)); SUP-RC-SMOKE supervisor item (D-82): text in docs/build-spec/sprint/sup-rc-smoke.md, appended by the supervisor before L7 starts; gate make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts; SUP-RC-SMOKE partial: RC-SMOKE.4 (WLD-B-04 findings) waits for deferred DIN-9; the other steps do not depend on it |

Merge order: L7-1 → L7-2 → L7-3

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD …` (full selection in plan-vabc.json)
- `make parity K="(initial_allocation) or (contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)) or (catchup-08 or catchup-09 or rollforward-08 or rollforward-09) or (catchup-10 or catchu …` (full selection in plan-vabc.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`
- `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts  # SUP-RC-SMOKE, RC-SMOKE.1 to RC-SMOKE.10`

#### Integration after merge

| Level | Item | Consumes | Kind | Contract |
|---|---|---|---|---|
| L2 | END-1 | ENC-15 | engine state type | s12 consumes the CostLossState type of s11 |
| L3 | CTR-2 | END-10 | V-C engine contract | computation.persist stores compute output bundles (DG-CMD-10) |
| L3 | CTR-2 | EDS-1 | V-C engine contract | contract_version.rpo_amount comes from stage 15 |
| L3 | CTR-2 | END-9 | V-C engine contract | validator: computed versions persist(uow, bundle, output) the result of erev_engine.compute (END-9) |
| L3 | CTR-3 | END-9 | V-C engine contract | validator: test_active_contract_posts_sealed_balanced_posting persists the postings of erev_engine.compute (K-11 O1 53,504.59 EUR) |
| L3 | CTR-4 | END-9 | V-C engine contract | validator: test_create_draft_computes_provisional_version and test_allocation_walk_sf_ord_20417 read computed versions (97,627.12) |
| L6 | DIN-15 | DIN-10 | 04 API schema | queries/mapping-profiles.ts binds API-R-43 mapping profiles |
| L6 | DIN-16 | DIN-10 | 04 API schema | validator [api-bind]: binds API-R-43 produced by DIN-10 |
| L6 | DIN-17 | DIN-11 | 04 API schema | binds API-R-44 |
| L6 | CLO-26 | CLO-8 | 04 API schema | binds API-R-38 |
| L6 | CLO-26 | CLO-11 | 04 API schema | approved runs |
| L6 | CLO-26 | CLO-13 | 04 API schema | validator [api-bind]: binds API-R-38 produced by CLO-13 |
| L7 | RPS-22 | RPS-6 | 04 API schema | rail destination Reports |
| L7 | RPS-22 | RPS-7 | 04 API schema | rail destination Schedules |
| L7 | RPS-6 | RPS-5 | 04 API schema | legacy export capture |
| L7 | RPS-7 | RPS-5 | 04 API schema | binds legacy_je_summary |
| L7 | RPS-7 | CLO-4 | 04 API schema | GET /periods with blockers |
| L7 | SUP-RC-SMOKE | RPS-22 | supervisor | supervisor item: landing route /home and the completed rail (BS-D-08; SCREENS SCR-IA-01) |

#### Partial items: named keys blocked by deferred items

| Item | Named keys | Runnable | Waiting for |
|---|---:|---:|---|
| AKS-2 | 40 | 36 | ENC-6 |
| AKS-3 | 38 | 24 | EDS-4, ENC-5, ENC-6, ENC-8 |
| AKS-4 | 33 | 20 | ENC-5, ENC-6 |
| AKS-5 | 34 | 21 | ENC-5, ENC-8 |
| AKS-6 | 27 | 22 | EDS-4, ENC-5 |
| CTR-7 | 7 | 6 | ENC-5 |
| CTR-12 | 3 | 2 | ENC-5 |
| RPS-3 | 4 | 2 | EDS-4 |

#### Validation results

| Check | Result | Failures | Waived |
|---|---|---:|---:|
| (f) every in-scope item exactly once; done, in scope and deferred partition the items | PASS | 0 | 0 |
| (e) batches 1-4 items and <=75 min; <=5 lanes; lane ids, worktrees and merge order; lane box | PASS | 0 | 1 |
| (a) ordering: edges done, in L1, earlier, or a flagged contract; integration notes match | PASS | 0 | 18 |
| (b) no in-scope item depends on a deferred item (R-RC-1, reviews and partial fragments excepted) | PASS | 0 | 4 |
| (c) MVP capabilities of SPRINT-1.0rc.md §1 and §3 covered; forced prerequisites; J-01 fallback | PASS | 0 | 0 |
| (d) <=2 migration lanes, re-parenting order, no edge between them; overlaps only on §4.3 or V-A files | PASS | 0 | 2 |
| (g) minutes, level estimates and cumulative hours; merge gates; release key list | PASS | 0 | 0 |

Loop-order edges not satisfied by position (validator `serial`): 3; none is corroborated without a review entry.
<!-- generated by .scratch/sprint-vabc/evaluate.py: end -->

## Supervisor amendment D-82a

DIN-9 (CSV v2 templates and invoice ingestion) moves into rc scope, in L5-1 directly after DIN-4 (VV-03 / R-06), which resolves the partial status of DIN-15, DIN-16, DIN-17 and SUP-RC-SMOKE. `validate_vabc.py check` reports bookkeeping differences in (b), (f) and (g), because it compares with V-0 less the D-82 moved items. The addition is intentional. The dependency ordering (a), capabilities (c), migration lanes and overlaps (d) and batch rules (e) pass. Scope is now 145 items, with 202 deferred.
