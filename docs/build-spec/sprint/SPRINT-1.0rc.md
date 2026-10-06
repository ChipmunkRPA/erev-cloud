# eRev Cloud 1.0-rc sprint plan

| Field | Value |
|---|---|
| Owner | Principal engineering manager, sprint planner (slug `sprint-planner`) |
| Date | 2026-09-13 |
| Status | Proposed for the supervisor, validated by `sprint-validator` with fixes V-01 to V-10 applied (section 11). Tonight's execution needs the preconditions of section 4.2 and the decisions of section 8 |
| Inputs | `docs/BUILD_SPEC.md` (427 items, sha256 recorded in `plan.json`), `docs/build-spec/PHASES.md`, `docs/accounting/ENGINE_SPEC_B.md` §0.2, `docs/accounting/answer-keys/`, `docs/dev-guide.md` (DG-ENV-13, DG-MK-00e, DG-MK-e2e, DG-TST-10), `git log` on `main` |
| Machine-readable plan | `docs/build-spec/sprint/plan.json` |
| Generator and checks | `python3 docs/build-spec/sprint/plan_tools.py all` rewrites `plan.json` and the generated block of this file; `plan_tools.py check` validates `plan.json`; `python3 docs/build-spec/sprint/validate_plan.py check` is the independent validator (section 11) |
| Scratch | `.scratch/sprint-plan/` (`closure.json`, `tables.md`) |

## 1. Conclusions

**The MVP will not land as an end-to-end rc within about 9 hours under the brief's rules. The plan needs 10 levels and about 47.2 hours of wall-clock time.** Three independent measurements agree on this:

| Measure | Value | Source |
|---|---:|---|
| In-scope items, closure minus done | 163, including 47 forced prerequisites the brief did not list | section 3 |
| Agent work in scope | 106.8 agent-hours (29 items add Alembic revisions) | cost model, section 2.5 |
| Capacity floor with 5 lanes and 4-hour levels | 6 levels, about 27.5 h, before any dependency waits | 106.8 h ÷ (5 × 4 h) |
| Dependency critical path, hard edges only | 18.8 h serial, 29 items: ENA-10 → ENA-13 → ENB-13 → END-7 to END-10 → CTR-2 to CTR-5 → DIN-1 to DIN-3 → CLO-3 to CLO-7 → CLO-11, CLO-13, CLO-15, CLO-17, CLO-20, CLO-22 → CLO-26 → RPS-7 | `plan_tools.py` |
| Compliant packing (one migration lane per level) | 10 levels, 47.2 h after validation (47.9 h as emitted) | `plan.json` |

What main holds at the first level boundary after 9 hours (L2, 9.3 h; 62 items merged):

- **Engine:** every stage package from 01 to 14 (stage 15 lands in L3), not yet folded or registered. Stage 06 (ENB-2 to ENB-8) is complete in L2. `compute` lands in L3, at 14.2 h.
- **Reference data backend:** RFD-1 to RFD-10, RFD-12, RFD-13 and RFD-15.
- **Frontend foundation:** WEB-8, WEB-9 and WEB-10.
- **Deploy:** DEP-1 and DEP-2.

There are no contracts, imports, close, reports or product screens yet. Contracts API and computed versions arrive in L4 (19.2 h), the contracts screens in L8 and L9, the imports, close and report screens in L9 and L10, and golden parity in L7 to L10.

Recommendations:

1. **Decide the target, not the lane count.** Either accept a multi-night rc (L1 to L10, about 47 h at 5 lanes), or cut acceptance through ruling R-RC-1 (section 8) together with two migration lanes (variant V-A). That combination is V-ABC: 144 items, 8 levels, about 39.2 h. No variant I evaluated brings the e2e rc under about 39 h.
2. **Start L1 and L2 tonight regardless.** They are identical in every variant, and they carry the engine, the schema chain and the shell.
3. **Treat the L2 merge (about 9.3 h) as tonight's checkpoint.** Its gate is `make ci`, `make test-pg` and `make properties K="p01 or p04 or p10 or p12 or p05"`, run on a clean tree.

Engine finding that changed the scope: the stage state chain is strictly linear (ENGINE_SPEC_B §0.2 table: s09 `RecognitionState` → s10 `BalanceState` → s11 `CostLossState` → s12 `FxState` → s14 `PostingState` → s15 `DisclosureState`), and S14-R-10 takes every functional amount from stage 12. So stage 11 (ENC-15, ENC-16) and stage 12 (END-1 to END-3) cannot be deferred at engine level. Their platform consumers stay deferred: FX rate screens, multi-entity close and cost reports.

## 2. Method

### 2.1 Parser

`plan_tools.py parse_items` reads every `- [ ] **<ID> <Title>.**` block, 427 in all, and extracts:

- id, title, phase and document order;
- Prerequisites ids;
- Scope Paths, normalised so that a bare file name inherits the previous directory;
- the Schema, API, Engine and Screens lines;
- Answer keys, Golden and Journeys;
- Gates.

An item adds a migration when its Paths name `db/migrations/versions/`. RFD-13 is an override: it adds DB-04 and DB-05 triggers in its own revision.

Done items come from `git log --format=%s`: FND, EKC and PLF with their GATEs, WEB-1 to WEB-6 and WEB-3a to WEB-3d. WEB-7 is treated as done (80 items).

### 2.2 Why the declared prerequisites are not used for scope

Every BUILD_SPEC item names its predecessor, and the first item of each phase names the previous GATE. The closure of the brief's list over that field reaches **337 of the 347 open items**: DEP-2 alone pulls PRF, DMO, SOP, AIX, FCS, PRP and LMG. The field encodes loop order, not technical dependency, so scope uses the edges below instead.

### 2.3 Technical edges

| Source | Rule | Examples |
|---|---|---|
| Explicit ids | Ids in Prerequisites other than the serial predecessor | RPS-5 → CLO-9 (`journals.views.legacy_view`) |
| File producer | The first item listing a path creates it; a later item listing it depends on the creator (the section 4.3 hotspots excepted) | CLO-26 → CLO-22 (`domain/demo/close_history.py`) |
| Directory producer | A file inside a directory created by an earlier item | ENB-11 → ENB-10 (`s08_estimates_late_events/`) |
| Fixture producer | Worlds, golden streams and parity support named in Paths | RPS-3 → CLO-6 (`worlds.py`, `k01_pellworth`) |
| Bound API row | An item whose API line is "none (binds API-R-nn)" → the first producer of that row | DIN-15 → DIN-1 (API-R-43) |
| Created table | A T-id in a Schema line → the item that first created it | CTR-5 → CTR-1 |
| `MANUAL_EDGES` | Verified by reading the items: state-type chain, registrations, bindings, seeds, captures, named tests, answer keys, foreign keys named by table | ENB-13 → ENB-4, ENB-5, ENB-9, ENB-10 (`BOUNDARY_HANDLERS` complete for Table 0.3-A); CTR-20 → CTR-7 to CTR-14 (seeded judgement, suggestion, hold, estimate and commission) |
| `IGNORED_AUTO_EDGES` | Rejected auto edges, with reasons | CLO-13 → DIN-14 (sibling adapter module) |

Edge kinds:

- **hard:** the dependency is merged in an earlier level, or sits earlier in the same lane.
- **contract:** the item codes against a documented contract with fakes and may sit in another lane of the same level, flagged integration-after-merge. The base plan uses contracts only for the engine state types (ENGINE_SPEC Table 0.2-A) and for screens against 04 API schemas (MSW). Their e2e captures run in the merge gate.

### 2.4 Answer-key support

`key_facts` reads each key's `families`, `status`, `runner`, `recognition_method` values and timeline `event_type` values. A key is blocked when it needs a deferred item:

| Key content | Blocked by |
|---|---|
| Methods `COST_TO_COST`, `LABOUR_HOURS` or `COST_RECOVERY` | ENC-5 |
| Methods `RIGHT_TO_INVOICE` or `USAGE`, or events `USAGE_REPORTED` | ENC-6 |
| Methods `REDEMPTION_PATTERN` or `ROYALTY`, or events `MATERIAL_RIGHT_EXPIRED` | ENC-8 |
| Platform runner | PRP-1 |

Result: 180 engine-runner keys are runnable and 52 active keys are blocked. The classifier is a heuristic, so the L4 merge gate (the first `AKS-1` and `AKS-2` runs) confirms or corrects it.

### 2.5 Scheduler, cost model and checks

Costs are minutes of agent work, gates included. They are calibrated on the loop's last 40 iterations (about 26 minutes per iteration, about 32 minutes per item) plus worktree overhead.

| Kind | Minutes |
|---|---:|
| Engine stage item | 30 |
| Backend command or route item | 35 |
| Migration item | 40 |
| Seed builder | 50 to 60 |
| Screen with `make e2e` | 55 |
| Parity item | 45 to 60 |
| Answer-key sweep | 60 |
| Deploy | 25 |
| WEB-11 harness | 70 |

Packing rules:

- Each lane holds at most 240 minutes per level.
- Batches hold 1 to 4 items and at most 75 minutes.
- A merge step costs 35 minutes, plus 25 when screens merge, plus 10 per integration-after-merge item.

`schedule` runs two packers and keeps the cheaper result. One is first fit in earliest-start order; the other is level-by-level greedy by criticality. Both enforce:

- at most 5 lanes;
- engine items only in engine lanes;
- one migration lane per level, which never takes unrelated work;
- no cross-lane overlap of non-hotspot files, where a directory scope overlaps every file below it;
- answer-key and parity correction items carry the pseudo scope `backend/erev_engine/stages/`.

`check_plan` fails on any of these:

- coverage gaps, or overlap between in-scope, deferred and done;
- an item scheduled twice;
- more than 5 lanes, or more than one migration lane, in a level;
- a batch outside 1 to 4 items;
- a merge order that does not list every lane;
- a non-hotspot file overlap;
- a dependency on a deferred item;
- a hard dependency in another lane of the same level, or later;
- a contract dependency without an integration note.

The emitted plan passes `check`.

## 3. Scope decisions

### 3.1 Forced prerequisites beyond the brief's list

| Cause | Items |
|---|---|
| Linear engine state chain and `compute` registration | ENC-15, ENC-16, END-1, END-2, END-3; ENB-4, ENB-5, ENB-9, ENB-10, ENB-12 (ENB-13 completes `BOUNDARY_HANDLERS` and registers stages 06 to 08); ENC-9 (stage 09 schedule versioning over holds and manual release) |
| Stage 15 content consumed by close and reports | EDS-4, EDS-5, EDS-6 (lock snapshot content, variance between closes, revenue from prior-period obligations) |
| Configuration lifecycle used by every versioned configuration | RFD-4, RFD-5 |
| Calculator and context pill bound by in-scope items | RFD-15 (CTR-2 committed-obligation provider; RFD-24), RFD-19 (CLO-23), WEB-9 (`ContextPill.tsx`) |
| Rail completion of RPS-22 | RFD-22 (Policies), WEB-17 (Settings) |
| Contracts seed and workbench | CTR-7, CTR-8, CTR-9, CTR-10, CTR-11, CTR-12, CTR-14, CTR-17 (CTR-20 seeds activations, judgements, dismissed suggestions, holds, estimate versions and commission costs; CTR-22 drawers; CTR-23 billing plan and costs) |
| Data in behind screens and parity | DIN-7, DIN-8 (probe finding messages), DIN-10 (import wizard `map` step), DIN-12, DIN-14 (mock router and NetSuite adapter used by CLO-15) |
| Seeded close history captured by CLO-23, CLO-26, RPS-6, RPS-7 and worlds used by RPS-3 | CLO-4, CLO-5, CLO-6, CLO-7, CLO-14 to CLO-20, CLO-22 |
| Home read model | RPS-17 |

`closure.json` in scratch lists every reason behind each in-scope item.

### 3.2 Roots excluded and the J-01 decision

| Root | Decision |
|---|---|
| GPB-4 | Deferred. Full G3 needs GPB-3 `point_in_time_equivalence`, which replays into a sandbox through LMG-4 and SNP-1 to SNP-3. The rc selection is 121 of 122 cases |
| AKS-8 | Deferred. The 221-key sweep cannot pass while ENC-5, ENC-6 and ENC-8 are deferred |
| RPS-23, RPS-24 (J-01) | Deferred: its prerequisites do not fit. J-01 would add WEB-13, WEB-19, RFD-18, RFD-23, RPS-21, DIN-18 and the QuickBooks Online realm, on top of CLO-15. The smoke journey SUP-RC-SMOKE (section 7.3) replaces it |

### 3.3 Partial items

These items stay in scope, but their named keys include keys blocked by deferred stages. A lane runs the runnable subset, records a SPEC-Q and leaves the item unticked. Every phase GATE stays unticked for the same reason.

| Item | Named keys runnable | Waiting for |
|---|---|---|
| AKS-2 | 38 of 40 | ENC-6 |
| AKS-3 | 30 of 38 | ENC-5, ENC-6, ENC-8 |
| AKS-4 | 26 of 33 | ENC-5, ENC-6 |
| AKS-5 | 28 of 34 | ENC-5, ENC-8 |
| AKS-6 | 24 of 27 | ENC-5 |
| CTR-7 | 6 of 7 | ENC-5 |

AKS-1 (33 keys) and AKS-7 (16 keys) are fully runnable.

## 4. Execution model

### 4.1 Lanes, branches and evidence

- Each lane runs in its own worktree on branch `sprint/1.0rc/L<level>-<lane>`, created from `main` after the previous level's merge commit.
- A lane works its batches in order and commits each item separately (DG-GIT-01). Per-item evidence goes in the commit body, as the loop already does.
- **Lanes never edit `PROGRESS.md`.** The merge step appends the ticks in merge order.
- **Spec questions:** lanes number them `SPEC-Q-L<level>-<lane>-<n>` in commit bodies. The merge step renumbers them into the global `SPEC-Q-<n>` sequence in `PROGRESS.md`, because a shared counter would collide across lanes.
- Supervisor documents and answer keys stay read-only, as in the loop (DG-GIT-05).

### 4.2 Preconditions before L1

| Id | Precondition | Why |
|---|---|---|
| PRE-1 | WEB-7 committed on `main`, including its `frontend/package.json` and lock change | The lanes branch from a clean tree |
| PRE-2 | One supervisor commit on `main` adding the libraries in-scope items need that are not locked yet: backend `openpyxl`, `xlsxwriter` (dev-guide §2.2) and `defusedxml` (DIN-1 parse); frontend `otpauth` and `@axe-core/playwright` (dev-guide §2.2), through `make setup LOCK=1` | `pyproject.toml`, `uv.lock` and `package-lock.json` are not mergeable across lanes, and only `make setup` may use the network |
| PRE-3 | Per-lane databases provisioned by the supervisor: `erev_rv_l<n>_test` and `erev_rv_l<n>_e2e` for n = 1 to 5 (DG-ENV-13 allow-list; DG-FORBID-03 forbids the loop from creating them) | `make ci` and `make test-pg` take a session advisory lock and reset the test schema (DG-TST-10); `make e2e` resets `erev_e2e` (DG-MK-e2e). A shared database would serialise or corrupt the lanes |
| PRE-4 | Per-worktree `.env` with `EREV_TEST_DB_OWNER_URL`/`EREV_TEST_DB_APP_URL`, `EREV_E2E_DB_OWNER_URL`/`EREV_E2E_DB_APP_URL`, `EREV_API_PORT`, `EREV_WEB_PORT`, `EREV_E2E_API_PORT` and `EREV_E2E_WEB_PORT`, on ports probed free and distinct from 8190, 8199, 5270 and 5279 (D-70 and D-80 precedent) | Fixed ports otherwise collide; the e2e lock `.run/locks/e2e-ports` is per worktree (DG-MK-00e) |
| PRE-5 | Memory headroom for five concurrent `make ci` runs, each with a Vite build and Playwright Chromium | Shared machine; concurrent builds have killed long jobs before |

### 4.3 Shared files and merge rules

These files create no dependency edge. Several lanes may edit them in one level, and the merge step resolves them by the rule shown. Any other cross-lane file overlap fails `check`.

| File | Rule |
|---|---|
| `docs/api/openapi.json`, `frontend/src/lib/api/schema.d.ts` | Never hand-merge; run `make openapi` on `main` after the last lane merges |
| `frontend/src/app/router.tsx` | Union of route objects in SCREENS §0.4 order |
| `frontend/src/messages/en.json` | JSON key union by namespace |
| `frontend/e2e/projects/screens.spec.ts` | Union of test blocks, keeping capture order per BS-D-09 |
| `frontend/src/routes/settings/index.tsx` | Union of built-page links |
| `backend/erev_api/api/router.py` | Union of `ROUTERS` entries (implicit edit by every new `api/v1` module) |
| `backend/erev_api/db/tables/__init__.py` | Union of imports; only the migration lane adds table modules |
| `backend/erev_engine/stages/__init__.py`, `backend/tests/engine/kernel/test_stage_registry.py` | Union of registrations and `PENDING_STAGES` removals in Table 0.2-A order |
| `backend/tests/architecture/test_registries_complete.py`, `backend/erev_api/approvals/subjects.py` | Union of `PENDING_` removals and `SUBJECTS` entries |
| `backend/tests/support/rows.py`, `backend/tests/pg/test_db_invariants.py`, `test_rls_isolation.py`, `test_immutability_and_grants.py` | Union |
| `backend/erev_api/domain/platform/provisioning.py`, `backend/erev_api/db/transitions.py` | Union in 04 §14.3 order |
| `backend/erev_api/domain/demo/builders.py`, `backend/erev_api/domain/demo/__init__.py`, `backend/erev_api/cli.py`, `Makefile`, `backend/tests/unit/test_makefile_targets.py` | Union |
| `docs/guides/user-guide.md`, `docs/guides/runbook.md` | Union of sections |
| `backend/tests/support/fold.py`, `backend/tests/properties/test_prop_p01_allocation_sum.py` | Union |
| `PROGRESS.md` | Lanes never edit it |

Alembic: only the migration lane of a level runs `make revision`, so the revision chain has a single head. The next level branches from the merged chain.

## 5. Levels and lanes (overview)

The full batch tables, with notes, merge orders and merge gates, sit in section 10 (generated). Lane ids are `L<level>-<n>` in merge order.

| Level | Hours (cumulative) | Lanes and items |
|---|---|---|
| L1 | 4.6 (4.6) | L1-1 schema: RFD-1, RFD-6, RFD-2, RFD-3, RFD-8 · L1-2 engine: ENA-1, ENA-2, ENA-3, ENA-5, ENB-1, ENA-6, ENA-10, ENA-11 · L1-3 engine: ENC-1, ENC-2, ENC-3, ENC-4, ENC-7, ENC-9, ENB-9, ENB-10 · L1-4 platform: RFD-4, RFD-5, WEB-8, WEB-9, DEP-1, DEP-2 · L1-5: WEB-10 |
| L2 | 4.8 (9.3) | L2-1 schema: RFD-7, RFD-9, RFD-12, RFD-13, RFD-10, RFD-15 · L2-2 engine: ENA-4, ENA-7, ENA-8, ENA-9, ENA-12, ENA-13 · L2-3 engine: ENB-2, ENB-3, ENB-4, ENB-5, ENB-6, ENB-7, ENB-8 · L2-4 engine: ENC-10, ENC-11, ENC-12, ENC-13, ENC-14, ENC-15, ENC-16 · L2-5 engine: ENB-11, ENB-12, END-1, END-2, END-3, END-4, END-5, END-6 |
| L3 | 4.9 (14.2) | L3-1 schema: CTR-1 · L3-2 engine and compute: ENB-13, END-7, END-8, END-9, END-10, EDS-1, EDS-2 · L3-3: RFD-11, RFD-14, RFD-16 · L3-4 frontend: WEB-11, WEB-12, WEB-15, WEB-17 |
| L4 | 5.0 (19.2) | L4-1 schema: CTR-2, CTR-3, CTR-4, CTR-5, DIN-1 · L4-2 engine: EDS-3, EDS-4, EDS-5, EDS-6, AKS-1, AKS-2 · L4-3 frontend: RFD-19, RFD-22, RFD-24 |
| L5 | 4.6 (23.8) | L5-1 schema: CLO-1, DIN-2, CLO-2, CTR-7, CTR-15, DIN-3 · L5-2 keys: AKS-3, AKS-4, AKS-5, AKS-6 · L5-3: CTR-8 |
| L6 | 4.6 (28.4) | L6-1 schema: CTR-10, CTR-12, CTR-14, DIN-12, RPS-1, DIN-10 · L6-2 keys: AKS-7 · L6-3: CLO-3 |
| L7 | 4.2 (32.7) | L7-1: CLO-4, CLO-5, CLO-6, CLO-16, CLO-18, CLO-19 · L7-2 schema: CTR-9, DIN-4, CTR-17, GPA-1, DIN-5 · L7-3: CTR-19 · L7-4: DIN-14 |
| L8 | 4.5 (37.2) | L8-1: GPA-2 · L8-2: CLO-7, CLO-8, CLO-11, CLO-13, CLO-14, CLO-15 · L8-3: CTR-20, CTR-21, CTR-11, CTR-22 · L8-4: DIN-6, DIN-7, DIN-8, DIN-11 |
| L9 | 4.7 (41.8) | L9-1: GPA-3, GPA-4, GPA-5, CLO-9, GPA-6 · L9-2: CLO-17, CLO-20, CLO-22, CLO-26 · L9-3: RPS-2 · L9-4 frontend: DIN-15, CTR-26, DIN-16, DIN-17 · L9-5 frontend: CTR-23 |
| L10 | 5.3 (47.2) | L10-1: RPS-3, RPS-4, RPS-5, RPS-17, GPB-1, GPB-2 · L10-2 frontend: CLO-23, RPS-6, RPS-7, RPS-22 |

Integration-after-merge items, which code against a contract built in another lane of the same level:

- L2: END-1 on `CostLossState` from ENC-15. END-5 now follows ENB-11 in lane L2-5 (validation fix V-06).
- L10: RPS-6 on RPS-3 (report-cell explain route, added by V-08), RPS-4 and RPS-5; RPS-7 on RPS-3 and RPS-5; RPS-22 on RPS-17.

Their acceptance turns green in the level's merge gate, and the merge step fixes any defect before tagging.

## 6. Merge procedure and gates

For every level, in order:

1. Wait until every lane of the level reports its batches committed, with lane gates green in the lane worktree: `make ci` and each item's GK targets, run against the lane's own databases and ports.
2. On `main`, merge the lane branches with `git merge --no-ff`, in the level's `merge_order`: the migration lane first, then engine lanes, parity and platform lanes, and frontend lanes last. Resolve hotspot conflicts by the section 4.3 rules; a conflict in any other file stops the merge and goes back to the lane.
3. Run `make openapi` and commit the regenerated `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` when they changed.
4. Append the ticks of the merged items to `PROGRESS.md` in merge order, renumber lane spec questions, and commit.
5. Run the level's `merge_gates` from `plan.json` on a clean tree (`git status --porcelain` empty). They grow cumulatively:
   - always `make ci` and `make test-pg`;
   - `make properties K=…` for every property named by a merged item (from L2);
   - `make answer-keys ID=…` with every runnable key named by a merged item (from L3);
   - `make parity K=…` with the merged GPA and GPB selections (from L7);
   - `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` once WEB-11 is merged and a level merges screens.
6. When a gate is red, the merge step fixes the defect on `main` with its own test (DG-GATE-02). The next level starts only when every gate is green.
7. Tag `sprint-1.0rc-L<n>` and create the next level's lane branches from that commit.

## 7. Release gate for the rc

### 7.1 Commands, run on a clean tree after the last merge commit

| Gate | Command | Pass criterion |
|---|---|---|
| OpenAPI current | `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts` | No diff |
| CI | `make ci` | Five stages pass |
| Isolation and immutability | `make test-pg` | Every `pg` test passes, none skipped |
| Engine properties | `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"` | Every selected property passes under `thorough` |
| Answer keys | `make answer-keys ID=<release_gate.answer_keys.runnable_engine_runner_ids>` | 180 of 180 pass. The ids are in `plan.json` |
| Golden parity | `make parity K="not point_in_time_equivalence"` | 121 of 122 pass, none skipped |
| Screens | `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` | Every row added by an in-scope screen item passes, with no serious or critical axe violation; both themes read against SCREENS |
| Smoke journey | `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts` | SUP-RC-SMOKE passes, once appended by the supervisor |

### 7.2 Answer-key families

| Status | Families |
|---|---|
| Runnable in full | ALC 10, COST 5, CPC 6, ENT 5, FX 11, LATE 3, NCC 1, ONB 3, RET 7, RND 25, SFC 8, SSP 8, STP1 5, TAX 2 |
| Partly runnable | DISC 6 of 8 (ENC-6, PRP), DLT 1 of 2 (PRP), IFRS 3 of 4 (ENC-5), JE 11 of 12 (ENC-5), MOD 10 of 19 (ENC-5), MR 8 of 12 (ENC-8), POB 12 of 16 (ENC-6), POS 6 of 11 (ENC-5, ENC-6, PRP), REC 14 of 24 (ENC-5, ENC-6), VC 10 of 14 (ENC-5, ENC-6) |
| Not runnable | BRK 0 of 6 (ENC-8), LOSS 0 of 2 (ENC-5), ROY 0 of 3 (ENC-6, ENC-8) |

`plan.json` `release_gate.answer_keys.blocked_keys` lists the blocked key ids. The five platform-runner keys wait for PRP.

### 7.3 Proposed supervisor item SUP-RC-SMOKE (replaces J-01 tonight)

The item uses the BUILD_SPEC template, is appended by the supervisor after CLO-26 and RPS-22 land, and is sized as one journey part. It lives at `frontend/e2e/journeys/rc-smoke.journey.ts`, called from `frontend/e2e/projects/avenmoor-serial.spec.ts` on WLD-T-01. The steps use only in-scope screens and seeded data:

1. As `maya`, sign in (SF-22) and open SF-02. `SF-ORD-10001` is listed.
2. On K-02, open SF-03:schedules. `FY2026-P09` shows 9,863.01.
3. On K-01 O1, open Explain for the Sep 2026 schedule amount. The panel shows USD 9,764.38.
4. On SF-10:new, upload `avm-de-progress-2026-09.csv`. The import reaches `DIFF_READY` and is submitted.
5. As `priya`, with TOTP (SF-22:mfa-challenge), approve the import on SF-12:request.
6. On SF-11, the WLD-B-04 `PROGRESS_OVER_DELIVERY` item is listed.
7. On SF-05 `/close/AVM-US/ASC606/FY2026-P09`, the checklist lists the gates.
8. On SF-06:run, the seeded FY2026-P08 run balances with difference 0.00.
9. On SF-08:report `revenue_waterfall`, the tie-out strip passes.
10. On SF-01 as `priya`, "Waiting for you" lists WLD-B-01 to WLD-B-03.

`a11y.check` runs on every surface.

### 7.4 Supervisor verification

- By hand: `docker build` of the three `deploy/docker` Dockerfiles, and `docker compose -f deploy/compose.yaml config`. The DEP-5 scripts are deferred.
- Multi-role browser QA of the rc screens as `maya`, `priya`, `marcus` and `robert` (G12).

## 8. Estimates, variants and decisions requested

| Variant | Change | In scope | Levels | Hours | Merged by 9.5 h | Moved to post-rc |
|---|---|---:|---:|---:|---:|---|
| V-0 (validated) | Brief's rules; screens code against 04 API schemas; validator fixes V-01 to V-09 | 163 | 10 | 47.2 | 62 (by 9.3 h) | none |
| V-A | Two migration lanes per level. The merge step re-parents the second lane's revisions onto the first (edits `down_revision`, renumbers `NNNN_`), then `make test-pg` runs `test_single_head` and `test_upgrade_downgrade_upgrade` | 163 | 9 | 43.8 | 61 | none |
| V-B | Ruling R-RC-1 (below) | 144 | 10 | 44.9 | 61 | CTR-11, CTR-14, CTR-17, DIN-12, DIN-14, EDS-4, EDS-5, EDS-6, CLO-5, CLO-6, CLO-7, CLO-14 to CLO-20, CLO-22 |
| V-C | Platform consumers of engine functions code against ENGINE_SPEC §0.5 with fakes (integration-after-merge) | 163 | 10 | 47.9 | 61 | none (no gain: the platform chain waits on the schema lane and same-level hard edges, not on `compute`) |
| V-ABC | V-A, V-B and V-C | 144 | 8 | 39.2 | 61 | as V-B |

`plan.json` `variants[].levels_compact` holds the lane lists of each variant, so the orchestrator can switch after a ruling.

Decisions requested from the supervisor:

1. **Target:** a multi-night rc on V-0, or V-ABC (about 39 h) after rulings 2 and 3.
2. **Ruling R-RC-1**, a descoping of acceptance fragments that under XR-14 are hidden and recorded as SPEC-Q by the consuming item:
   - SF-05 and SF-06 captures of seeded close history, NetSuite acknowledgements and as-locked views move to DMO;
   - CTR-22 void and regroup drawers are hidden;
   - CTR-23 billing plan and cost panels are hidden;
   - CTR-20 K-06 estimate versions and K-09 commission move post-rc;
   - RPS-3 as-locked, prior-period, reconciliation and k03 tests move post-rc;
   - RPS-4 k02 modification and k09 commission tests move post-rc;
   - CLO-11 reopened-period test moves post-rc.

   `RULING_R_RC_1` in `plan_tools.py` lists the dropped edges.
3. **Merge procedure V-A:** approve revision re-parenting at merge, relaxing "at most one lane per level adds migrations".
4. **Preconditions PRE-2 to PRE-5**, including provisioning of the ten `erev_rv_l<n>_*` databases.
5. **SUP-RC-SMOKE** as a supervisor item.

## 9. Risks

| Id | Risk | Effect | Mitigation |
|---|---|---|---|
| R-01 | The rc needs about 47 h (V-0 after validation) or about 39 h (V-ABC, not re-validated), not 9 h | Tonight ends at the L2 checkpoint with no product screens | Section 8 decisions; L1 and L2 start now in every variant |
| R-02 | One migration lane per level is the throughput limit (29 revision items, 19.6 h of serial lane work) | The schema lane is full in L2, L4, L5 and L6 while other lanes idle (L3-1, L5-3, L6-2, L6-3, L7-3, L7-4, L8-1, L9-3 and L9-5 hold one item each) | V-A merge re-parenting |
| R-03 | Closure is conservative where items say little (ENB-13 needs ENB-12; ENC-10 needs ENC-9; RFD-13 adds a revision; worlds and captures) | Some forced prerequisites may be avoidable | `MANUAL_EDGES` carry reasons; rerun `plan_tools.py all` after correcting an edge |
| R-04 | Integration-after-merge items (END-1, RPS-6, RPS-7, RPS-22) and cross-lane contract drift | Red merge gates; fixes on `main` lengthen merges | 10 minutes per item budgeted; lanes code to ENGINE_SPEC_B tables and 04 schemas verbatim |
| R-05 | The answer-key classifier is heuristic | The 180-key release selection may shift | Validate at the L4 gate (AKS-1, AKS-2); regenerate `plan.json` with corrected blockers |
| R-06 | Seeding grows towards the SZ-06 15-minute ceiling | Screen-heavy merge gates (L9, L10) exceed their budget | Per-lane e2e databases (PRE-3); screen lanes limited to one per level in most levels |
| R-07 | Hotspot conflicts (`router.tsx`, `en.json`, `screens.spec.ts`, registries) | Manual merge effort | Section 4.3 union rules; frontend lanes merge last |
| R-08 | Shared machine: five lanes with Vite builds, Playwright and Postgres | Memory pressure kills builds; port clashes | PRE-4 and PRE-5; PID files, never pattern kills |
| R-09 | Partial items (AKS-2 to AKS-6, CTR-7) and every phase GATE stay unticked | G1 counts do not move for them | Reported under Spec questions; ENC-5, ENC-6 and ENC-8 as the first post-rc level |
| R-10 | Parity and answer-key corrections touch stage packages | File overlap with engine lanes | Pseudo scope `backend/erev_engine/stages/` keeps correction items out of levels with engine lanes; the check enforces it |
| R-11 | The declared chain order changes (supervisor inserts items) | Plan drift | `check` warns on a BUILD_SPEC hash change; rerun `plan_tools.py all` |

## 10. Generated tables

The block below is rewritten by `python3 docs/build-spec/sprint/plan_tools.py all`. Do not edit it by hand. The validator rewrote its Levels tables and the V-0 row through `python3 docs/build-spec/sprint/validate_plan.py apply` (section 11); rerunning `plan_tools.py all` reverts them unless the validator edges are added to `MANUAL_EDGES` first.

<!-- generated by plan_tools.py: begin -->

### Scope table

| Id | Title | Kind | Min | Why in scope (first reason) |
|---|---|---|---:|---|
| WEB-8 | App shell frame, rail, router and error placements | frontend | 40 | root C1 frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals |
| WEB-9 | Top-bar surfaces: notifications, tenant switcher, indicators, command palette, menus, About and session expiry | frontend | 40 | RFD-19 (hard): file frontend/src/app/shell/ContextPill.tsx created by WEB-9 |
| WEB-10 | Demo seed scaffold | seed | 50 | root C1 frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals |
| WEB-11 | Playwright harness and sign-in screen | screen | 70 | root C1 frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals |
| WEB-12 | MFA challenge, workspace selection, profile and persona sign-in | screen | 55 | root C1 frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals |
| WEB-15 | Approvals inbox and request detail | screen | 55 | root C1 frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals |
| WEB-17 | Settings index, notification preferences and the notifications popover capture | screen | 55 | RPS-22 (contract): rail destination Settings |
| ENA-1 | Stage 01 engine canonicalisation, voids, quantity ledger and estimate pins | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-2 | Stage 02 contract identification: Step 1 gate, enforceable term and deposits | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-3 | Stage 03 POB builder: lines, template resolution, bundles, negative and $0 lines, distinctness and series | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-4 | Stage 03 options, warranties, principal or agent, licences and time triggers | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-5 | Stage 03 scope routing, repurchase outcomes, immaterial promises, shipping, franchisor, custodial, measure and legacy templates | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-6 | Stage 04 transaction price build-up, variable consideration elements and constraint | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-7 | Stage 04 expected returns, implicit price concessions, sales taxes and the unconstrained view | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-8 | Stage 04 significant financing component | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-9 | Stage 04 consideration payable, share-based consideration payable, noncash consideration and warranty accrual | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-10 | Stage 05 SSP resolution: book, version, entry, currency, extended values and SSP points | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-11 | Stage 05 relative-SSP allocation, original columns, immaterial-promise merge and the parity preset | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-12 | Stage 05 targeted variable consideration, discount exception, residual approach and pipeline order | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENA-13 | Inception fold over stages 01 to 05, P1 at stage 05 and fail-closed allocation identities (CTL-012) | engine | 40 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| RFD-1 | Fiscal calendars and period generation | migration | 40 | root C4 reference data backend |
| RFD-2 | Legal entities, books, period states and entity-scoped access | migration | 40 | root C4 reference data backend |
| RFD-3 | Currencies and FX rate sets | migration | 40 | root C4 reference data backend |
| RFD-4 | Rule set authoring | backend | 35 | RFD-10 (hard): directory backend/erev_api/domain/policies/ created by RFD-4 |
| RFD-5 | Configuration lifecycle, rule evaluation and rule-based auto-approval | backend | 35 | RFD-7 (hard): mapping versions use the SM-04 lifecycle (/test, /submit, /publish) |
| RFD-6 | Chart of accounts and dimensions | migration | 40 | root C4 reference data backend |
| RFD-7 | Account-role mapping versions | migration | 40 | root C4 reference data backend |
| RFD-8 | Customers and related-party groups | migration | 40 | root C4 reference data backend |
| RFD-9 | Products, bundles and principal-or-agent changes | migration | 40 | root C4 reference data backend |
| RFD-10 | Obligation templates | migration | 40 | root C4 reference data backend |
| RFD-11 | Tenant accounting policy set, practical expedients and the legacy-parity preset | backend | 35 | root C4 reference data backend |
| RFD-12 | SSP books, versions and entries | migration | 40 | root C4 reference data backend |
| RFD-13 | SSP publication: study, maker-checker, range validation and immutability | migration | 40 | root C4 reference data backend |
| RFD-14 | SSP resolution by effective date and named version | backend | 35 | root C4 reference data backend |
| RFD-15 | Historical SSP calculator | migration | 40 | CTR-2 (hard): committed-obligation provider in domain/ssp/calculator.py |
| RFD-16 | Avenmoor reference-data demo seed | seed | 60 | root C4 reference data backend |
| RFD-19 | Chart of accounts, workspace settings, workspace setup and the context pill | screen | 55 | CLO-23 (contract): context pill binding |
| RFD-22 | Revenue policies, control rules and rule set version screens | screen | 55 | RPS-22 (contract): rail destination Policies |
| RFD-24 | SSP books and historical SSP calculator screens | screen | 55 | root C9 MVP screens |
| ENB-1 | Golden event streams for engine tests and the stage 06 modification proposal | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-2 | Stage 06 native prospective modification (25-13(a)): SSP basis, pools, segments and lineage | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-3 | Stage 06 cumulative catch-up and mixed modifications, satisfied performance, targeted concessions, reductions and price-only changes | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-4 | Stage 06 subscription changes, terminations, unpriced change orders, credit-rollover renewals and negative allocation | engine | 30 | ENB-13 (hard): BOUNDARY_HANDLERS complete for Table 0.3-A: CONTRACT_TERMINATED |
| ENB-5 | Stage 06 material-right exercise, expiry, attribute changes and regrouping | engine | 30 | ENB-13 (hard): BOUNDARY_HANDLERS: MATERIAL_RIGHT_EXERCISED, LINE_ATTRIBUTES_CHANGED, REGROUPED |
| ENB-6 | Stage 06 legacy retrospective template, with the attribute-conflict validator | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-7 | Stage 06 legacy POB-specific VC template | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-8 | Stage 06 legacy prospective template and catch-up disclosure measures | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-9 | Stage 07 onboarding: opening balances, recomputation from inception and business combinations | engine | 30 | ENB-13 (hard): BOUNDARY_HANDLERS: OPENING_BALANCE_ESTABLISHED; stage 07 in STAGES |
| ENB-10 | Stage 08 estimate reassessment: pins, measure-only and reallocating kinds, and 32-45 routing | engine | 30 | ENB-11 (hard): directory backend/erev_engine/stages/s08_estimates_late_events/ created by ENB-10 |
| ENB-11 | Stage 08 late events, replay and posting-period assignment | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENB-12 | Stage 08 prior-period decomposition | engine | 30 | ENB-13 (hard): stage 08 exports complete before registration |
| ENB-13 | Boundary handler registry, boundary fold and modification integrity | engine | 40 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-1 | Stage 09 recognition components, FIXED targets over segments, time elapsed and status guards | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-2 | Time-elapsed conventions and re-baselined ratable schedules | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-3 | Point-in-time and output measures: control-transfer triggers, milestones, percent complete, bill-and-hold and repurchase outcomes | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-4 | Units measure: golden delivery revenue and progress edge cases | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-7 | Returns within the units measures | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-9 | Sequential cause decomposition, manual release, deferral, schedule overrides and recognition holds | engine | 30 | ENC-10 (hard): schedule versioning over manual release, holds and cause decomposition |
| ENC-10 | Obligation measures, schedules and versioning; P4 at schedule level and P10 | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-11 | Stage 10 billing ingestion, attribution and unconditional billing | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-12 | Stage 10 net position, refund liabilities and return assets | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-13 | Stage 10 receivables, receivable contra and contract asset versus unbilled receivable | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-14 | Stage 10 reclass attribution, netting reclass targets and current split | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| ENC-15 | Stage 11 contract costs: capitalisation, amortisation segments, impairment and the IFRS reversal | engine | 30 | END-1 (contract): s12 consumes the CostLossState type of s11 |
| ENC-16 | Stage 11 clawbacks, termination acceleration and loss provisions | engine | 30 | END-7 (hard): book loop runs stage 11 |
| END-1 | Stage 12 rates and contract-liability layers | engine | 30 | END-4 (contract): s14 consumes FxState; S14-R-10 functional amounts come from stage 12 |
| END-2 | Stage 12 period-end remeasurement, monetary liabilities and late-event rates; P12 | engine | 30 | END-3 (hard): stage 12 registration after remeasurement |
| END-3 | Stage 12 performing and contracting entities, intercompany pairs and reporting-currency translation | engine | 30 | END-7 (hard): book loop runs stage 12 |
| END-4 | Stage 14 template parts, counter roles and amount classes | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-5 | Stage 14 role targets and deltas: posting classes, period assignment, netting reclass, voids and mapping changes | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-6 | Stage 14 functional amounts, entries, accounts and keys; P5 engine part | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-7 | Stage 13 book loop, stage keys and framework switches; P13 | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-8 | Stage 13 LEGACY book fold and the delta identity | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-9 | `compute`: orchestration, blocking findings, fail-closed identities and the first answer-key run | engine | 45 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| END-10 | Delta posting and pre-standard revenue end to end (GT-07 journals at engine level) | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| AKS-1 | Rounding and SSP families pass (33 keys), with DG-AK-45 range validation wired | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-2 | Allocation, Step 1, obligation, tax, noncash and customer-consideration families pass (40 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-3 | Variable consideration, returns, financing, breakage and royalty families pass (38 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-4 | Recognition and presentation families pass (33 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-5 | Modification, material-right and late-event families pass (34 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-6 | Journal, delta, cost, loss, IFRS and onboarding families pass (27 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| AKS-7 | Foreign-currency and multi-entity families pass (16 keys) | aks | 60 | root C3 golden parity and answer-key sweeps |
| CTR-1 | Contract headers, combination groups and event streams | migration | 40 | root C5 contracts backend |
| CTR-2 | Computed versions, schedules and calculation traces | migration | 50 | root C5 contracts backend |
| CTR-3 | Subledger postings, seals and ledger chains | migration | 45 | root C5 contracts backend |
| CTR-4 | Contract creation, drafts and time-travel reads | backend | 35 | root C5 contracts backend |
| CTR-5 | Fact-capture events, late events and the contract compute job | migration | 40 | root C5 contracts backend |
| CTR-7 | Step 1 review, collectibility, enforceable term and judgement records | migration | 40 | CTR-20 (hard): WLD-B-03 judgement SUBMITTED |
| CTR-8 | Contract combination and combination suggestions | backend | 35 | CTR-20 (hard): K-05 and K-11 suggestion DISMISSED |
| CTR-9 | Activation checklist, approval routing and unmapped-product blocking | backend | 35 | CTR-20 (hard): key contracts activated through CONTRACT_ACTIVATED approvals |
| CTR-10 | Field locks, memos, attribute changes and holds | migration | 40 | CTR-20 (hard): WLD-B-05 journal_export hold |
| CTR-11 | Contract void with reversal lines | backend | 35 | CTR-22 (contract): void drawer |
| CTR-12 | Estimates and estimate versions | migration | 40 | CTR-19 (hard): test_history_lists_estimate_pairs (K-06 estimate versions) |
| CTR-14 | Contract costs, material rights, loss provisions, FX layers and billing plans | migration | 40 | CTR-20 (hard): K-09 commission cost asset |
| CTR-15 | Obligation reads, SSP overrides and policy overrides | migration | 40 | root C5 contracts backend |
| CTR-17 | Modifications: object, guided classification, impact preview and regrouping | migration | 40 | RPS-4 (hard): k02_marrowby modification |
| CTR-19 | Calculation trace store and explain routes | backend | 35 | root C5 contracts backend |
| CTR-20 | Avenmoor key contracts demo seed | seed | 60 | root C5 contracts backend |
| CTR-21 | Contracts list screen | screen | 55 | root C9 MVP screens |
| CTR-22 | Contract workbench frame and obligation pane | screen | 55 | root C9 MVP screens |
| CTR-23 | Workbench schedules, billing and journals tabs | screen | 55 | root C9 MVP screens |
| CTR-26 | Explain panel and calculation trace page | screen | 55 | root C9 MVP screens |
| DIN-1 | Import registry, uploads, rows and the validation job | migration | 40 | root C6 data in |
| DIN-2 | Raw source store and canonical normalisation | migration | 40 | root C6 data in |
| DIN-3 | Dry-run diff, approval, atomic commit and control totals | backend | 35 | root C6 data in |
| DIN-4 | Legacy v1 SKU SSP and contract setup templates | migration | 40 | root C6 data in |
| DIN-5 | Legacy v1 progress tracking template | backend | 35 | root C6 data in |
| DIN-6 | Legacy v1 contract modification template modes | backend | 35 | root C6 data in |
| DIN-7 | Legacy setup and SSP template defects made explicit, with row-level messages | backend | 35 | GPA-6 (hard): probe P3 compares row-level finding messages (DG-PAR-11) |
| DIN-8 | Legacy progress, modification and POB-specific VC template defects made explicit | backend | 35 | GPB-1 (hard): probes P1 and P4: blank memo and duplicate upload findings |
| DIN-10 | Mapping profiles and the ingestion grouping policy | migration | 40 | DIN-15 (contract): queries/mapping-profiles.ts binds API-R-43 mapping profiles |
| DIN-11 | Exception queue commands | backend | 35 | root C6 data in |
| DIN-12 | Integration connections, the Salesforce mock adapter and canonical ingestion | migration | 40 | CLO-15 (hard): mock router mounting |
| DIN-14 | NetSuite chart-of-accounts mock and account sync | backend | 35 | CLO-15 (hard): NetSuite GL adapter and mock files |
| DIN-15 | Imports list and templates screens | screen | 55 | root C9 MVP screens |
| DIN-16 | Import wizard screens | screen | 55 | root C9 MVP screens |
| DIN-17 | Exception queue screens | screen | 55 | root C9 MVP screens |
| GPA-1 | Parity runner, integrity preconditions, scenario replay of steps 01 to 03, and the `initial_allocation` kind (16 cases) | parity | 60 | root C3 golden parity and answer-key sweeps |
| GPA-2 | Contract positions after steps 02 to 07 (22 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| GPA-3 | Retrospective and POB-specific VC templates: steps 08 and 09 (11 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| GPA-4 | Prospective, retrospective-reduction and material-right templates: steps 10 to 13 (23 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| GPA-5 | Full delivery end state: step 14 obligation and contract positions (21 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| GPA-6 | Legacy probe runner and probe P3; the GATE-GPA parity selection (94 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| EDS-1 | Stage 15 RPO, practical-expedient exemptions and time bands; P7 engine part | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| EDS-2 | Revenue waterfall measures and the RPO rollforward | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| EDS-3 | Contract balances rollforward with FX movement | engine | 30 | root C2 engine stages 01 to 15 needed for legacy parity and SaaS basics |
| EDS-4 | Revenue from obligations satisfied in prior periods, and disaggregation tags | engine | 30 | RPS-3 (hard): revenue_from_prior_period_obligations |
| EDS-5 | Contract-cost rollforward | engine | 30 | EDS-6 (hard): lock snapshot datasets include the cost rollforward |
| EDS-6 | Lock snapshot content, manifest hashing and variance between closes | engine | 30 | CLO-7 (hard): variance between closes (§15.2.8) |
| CLO-1 | Journal and manual adjustment tables | migration | 40 | root C7 close and journals |
| CLO-2 | Close tables and system close checklist | migration | 40 | root C7 close and journals |
| CLO-3 | Soft close commands and the closed-period guard | backend | 35 | root C7 close and journals |
| CLO-4 | Close cockpit read model, gate evaluation and close tasks | backend | 35 | RPS-7 (contract): GET /periods with blockers |
| CLO-5 | Data-quality monitors | backend | 35 | CLO-6 (hard): DATA_QUALITY_CLEAR gate signal |
| CLO-6 | Lock with certification, lock snapshots and permanent lock | backend | 35 | RPS-3 (hard): file backend/erev_api/domain/close/snapshots.py created by CLO-6 |
| CLO-7 | Reopen with dual approval, post-reopen postings and re-lock diff | backend | 35 | CLO-11 (hard): test_reopened_period_needs_human_approval |
| CLO-8 | Journal run calculation | backend | 35 | root C7 close and journals |
| CLO-9 | Legacy gross and adjustment date-range journal views | backend | 35 | root C7 close and journals |
| CLO-11 | Journal run approval and states | backend | 35 | root C7 close and journals |
| CLO-13 | GL adapter interface, CSV export and the journal export relay | backend | 35 | root C7 close and journals |
| CLO-14 | Journal batch acknowledgements, retry and the acknowledgement lock gate | backend | 35 | CLO-26 (contract): every batch acknowledged capture |
| CLO-15 | NetSuite and QuickBooks Online mock adapters and trial balance pull | backend | 35 | CLO-26 (contract): NetSuite mock acknowledgements |
| CLO-16 | Billing-to-subledger reconciliation | backend | 35 | RPS-3 (hard): file backend/erev_api/domain/close/reconciliations.py created by CLO-16 |
| CLO-17 | Subledger-to-GL reconciliation and auto-certification | backend | 35 | CLO-20 (hard): GL_TIE_OUT |
| CLO-18 | Per-contract AR tie-out | backend | 35 | CLO-20 (hard): EXCEPTION_CHECK AR tie-out |
| CLO-19 | Close run orchestration, recompute and quarantine | backend | 45 | CLO-20 (hard): file backend/erev_api/domain/close/close_runs.py created by CLO-19 |
| CLO-20 | Close run period-end steps, journal summarization and dataset freeze | backend | 50 | CLO-22 (hard): Jan to Aug closed through succeeded close runs |
| CLO-22 | Demo seed close history | seed | 60 | RPS-6 (hard): as-locked capture on the seeded lock |
| CLO-23 | Close cockpit and journal preview screens | screen | 55 | root C9 MVP screens |
| CLO-26 | Journal run screens | screen | 55 | root C9 MVP screens |
| RPS-1 | Report tables and the standard report catalogue | migration | 40 | root C8 reports |
| RPS-2 | Report run framework and stamped outputs | backend | 45 | root C8 reports |
| RPS-3 | Revenue waterfall, contract balances and contract balance rollforwards | backend | 35 | root C8 reports |
| RPS-4 | Remaining performance obligations, RPO rollforward, disaggregation and disclosure elections | backend | 35 | root C8 reports |
| RPS-5 | Contract history, latest status, legacy exports and the legacy journal summary | backend | 35 | root C8 reports |
| RPS-6 | Report catalogue and report viewer screens | screen | 55 | root C9 MVP screens |
| RPS-7 | Schedules waterfall and date-range journal entry screens | screen | 55 | root C9 MVP screens |
| RPS-17 | Home dashboard read model, favourites and reverse drill chain | backend | 35 | RPS-22 (contract): binds API-R-50 |
| RPS-22 | Home screen, landing route and rail completion | screen | 55 | root C9 MVP screens |
| GPB-1 | Journal totals of steps 02 to 07 and months January to April 2023, and probes P1, P2 and P4 (13 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| GPB-2 | Journal totals of steps 08 to 14, months May to October 2023 and the full year (14 cases) | parity | 45 | root C3 golden parity and answer-key sweeps |
| DEP-1 | Container images | deploy | 25 | root C11 deploy images and compose |
| DEP-2 | Compose file and local roles | deploy | 25 | root C11 deploy images and compose |

### Deferred table

| Id | Title | Capability | Reason |
|---|---|---|---|
| WEB-13 | Invitation acceptance and MFA enrolment screens | C1, C10 | invitation acceptance and MFA enrolment screens; fresh-tenant journeys wait |
| WEB-14 | Password change and password reset screens | none | not required by the rc capabilities |
| WEB-16 | Bulk approval and approval delegations | none | not required by the rc capabilities |
| WEB-18 | Shell placement captures: About, session expiry, narrow viewport and not found | none | not required by the rc capabilities |
| WEB-19 | Users and user detail screens | C10 | users screens visited by J-01 |
| WEB-20 | Roles and separation-of-duties screens | none | not required by the rc capabilities |
| WEB-21 | Access review screens | none | not required by the rc capabilities |
| WEB-22 | Security and support access screens | none | not required by the rc capabilities |
| WEB-23 | API clients and webhooks screen | none | not required by the rc capabilities |
| WEB-24 | Design gallery and design project | none | not required by the rc capabilities |
| GATE-WEB | Phase WEB checkpoint | none | phase checkpoint; needs every item of its phase |
| GATE-ENA | Phase ENA checkpoint | none | phase checkpoint; needs every item of its phase |
| RFD-17 | Industry tenant reference data and Draft industry policy templates | none | not required by the rc capabilities |
| RFD-18 | Entities, calendars and currencies settings screens | C10 | entities, calendars and currencies settings screens visited by J-01 |
| RFD-20 | Customers and related-party groups screens | none | not required by the rc capabilities |
| RFD-21 | Products screens | none | not required by the rc capabilities |
| RFD-23 | Obligation template editor and accounting policy screens | C10 | accounting policy screens visited by J-01 |
| RFD-25 | Account mapping screens | none | not required by the rc capabilities |
| GATE-RFD | Phase RFD checkpoint | none | phase checkpoint; needs every item of its phase |
| GATE-ENB | Phase ENB checkpoint | none | phase checkpoint; needs every item of its phase |
| ENC-5 | Input measures: cost to cost with EAC, uninstalled materials, waste, labour hours and cost recovery | C2, C3 | input measures (cost to cost, labour hours, cost recovery, uninstalled materials): keys with those recognition methods fail closed |
| ENC-6 | Right to invoice, usage, minimum commitments and prepaid drawdown | C2, C3 | right to invoice, usage and minimum commitments: usage and RTI keys fail |
| ENC-8 | Breakage, material-right recognition, credit rollover and royalties | C2, C3 | breakage, material-right recognition and royalties: BRK, ROY and redemption-pattern MR keys fail |
| GATE-ENC | Phase ENC checkpoint | none | phase checkpoint; needs every item of its phase |
| END-11 | JET template checks, part 1: deposits, sales tax, cancellable invoices, rebates and catch-ups | C2 | JET check tests part 1 only; the templates are built by END-4 to END-6 |
| END-12 | JET template checks, part 2: contract costs, loss, consideration payable, warranties, noncash, financing, concessions and terminations | C2 | JET check tests part 2 only |
| END-13 | Replay determinism (P8), trace re-evaluation (P14) and parity measures on the trace | C2 | P8 and P14 properties; trace re-evaluation stays covered by CTR-19 verify |
| END-14 | Metamorphic suite and engine phase completeness | C2 | metamorphic suite |
| GATE-END | Phase END checkpoint | none | phase checkpoint; needs every item of its phase |
| AKS-8 | Engine-runner corpus sweep (221 keys) and AK hint closure record | C3 | C3: the 221-key sweep cannot pass while ENC-5, ENC-6 and ENC-8 are deferred |
| GATE-AKS | Phase AKS checkpoint | none | phase checkpoint; needs every item of its phase |
| CTR-6 | Manual event maker-checker | none | not required by the rc capabilities |
| CTR-13 | Portfolios and portfolio-scoped estimates | C5 | portfolio-scoped estimates; estimate.portfolio_id keeps no foreign key |
| CTR-16 | Policy impact simulation, prospective effect and approved re-runs | C5 | policy impact simulation over contracts |
| CTR-18 | Subscription changes, terminations and idempotent commands for importable objects | C5 | subscription-change commands; MOD-FS keys still run through the engine runner |
| CTR-24 | Workbench modifications and history tabs and the draft contract form | none | not required by the rc capabilities |
| CTR-25 | Estimates workbench screens | none | not required by the rc capabilities |
| CTR-27 | Modification wizard screens | none | not required by the rc capabilities |
| CTR-28 | Search and the command palette results | none | not required by the rc capabilities |
| GATE-CTR | Phase CTR checkpoint | none | phase checkpoint; needs every item of its phase |
| DIN-9 | Modern CSV v2 templates and invoice ingestion | C6 | modern CSV v2 templates other than customers and contracts |
| DIN-13 | Stripe mock adapter, adapter contract-test suite and reconciliation sweep | C6 | Stripe mock adapter and the inbound adapter contract suite |
| DIN-18 | Integrations screens | C10 | integrations screens visited by J-01 part 2 |
| GATE-DIN | Phase DIN checkpoint | none | phase checkpoint; needs every item of its phase |
| GATE-GPA | Phase GPA checkpoint | none | phase checkpoint; needs every item of its phase |
| EDS-7 | Disclosure engine-runner keys pass (6 keys); regression over 227 keys | C3 | DISC closure item; DISC keys stay green through the RPS-3 and RPS-4 selections |
| GATE-EDS | Phase EDS checkpoint | none | phase checkpoint; needs every item of its phase |
| CLO-10 | Journal line validation and completeness assertions | C7 | journal line validation and completeness gates fail closed on the cockpit |
| CLO-12 | Manual adjustments with manual release and defer | C7 | manual adjustments; the MANUAL_ADJUSTMENTS_CLEARED gate fails closed |
| CLO-21 | Multi-entity close command | C7 | multi-entity close command |
| CLO-24 | Close run, close history and multi-entity close screens | none | not required by the rc capabilities |
| CLO-25 | Reconciliation screens | none | not required by the rc capabilities |
| CLO-27 | Journey J-23 integration setup against the mock Salesforce, Stripe and NetSuite | none | not required by the rc capabilities |
| GATE-CLO | Phase CLO checkpoint | none | phase checkpoint; needs every item of its phase |
| RPS-8 | Journal, modification and close registers | none | not required by the rc capabilities |
| RPS-9 | SSP reports | none | not required by the rc capabilities |
| RPS-10 | Access, configuration, approvals and audit registers | none | not required by the rc capabilities |
| RPS-11 | Judgement, estimate, scope exclusion and loss provision registers | none | not required by the rc capabilities |
| RPS-12 | Contract cost rollforward, book and adoption bridges, intercompany pairs and balance aging | none | not required by the rc capabilities |
| RPS-13 | Bookings, billings and revenue; variance between closes | none | not required by the rc capabilities |
| RPS-14 | Data extracts for BI | none | not required by the rc capabilities |
| RPS-15 | Disclosure snapshots and the disclosure pack | none | not required by the rc capabilities |
| RPS-16 | Period evidence packs and contract sample packs | none | not required by the rc capabilities |
| RPS-18 | Report run register, run record and disclosure pack screens | none | not required by the rc capabilities |
| RPS-19 | Revenue and close dashboard screens | none | not required by the rc capabilities |
| RPS-20 | Evidence pack screens | none | not required by the rc capabilities |
| RPS-21 | Audit log and chain verification screens | C10 | audit log screen visited by J-01 part 2 |
| RPS-23 | Journey J-01 legacy user onboarding, part 1 (setup, policies and SSP import) | C10 | C10: J-01 part 1 needs WEB-13, WEB-19, RFD-18, RFD-23 and the fresh-tenant invitation flow; replaced tonight by the proposed SUP-RC-SMOKE journey |
| RPS-24 | Journey J-01 legacy user onboarding, part 2 (contracts, deliveries, journals and QuickBooks Online export) | C10 | C10: J-01 part 2 needs RPS-21 and DIN-18 and the QuickBooks Online realm of CLO-15; replaced tonight by SUP-RC-SMOKE |
| GATE-RPS | Phase RPS checkpoint | none | phase checkpoint; needs every item of its phase |
| SNP-1 | Tenant snapshots and the snapshot dataset | none | not required by the rc capabilities |
| SNP-2 | Sandbox load and determinism verification | none | not required by the rc capabilities |
| SNP-3 | Sandbox reset by supersession | none | not required by the rc capabilities |
| SNP-4 | Sandbox restrictions and immutable tenant kind | none | not required by the rc capabilities |
| SNP-5 | Sandbox copies screen and the sandbox banner | none | not required by the rc capabilities |
| GATE-SNP | Phase SNP checkpoint | none | phase checkpoint; needs every item of its phase |
| LMG-1 | Migration batches, legacy database profiling and source handling | none | not required by the rc capabilities |
| LMG-2 | Opening balances staging and legacy field mapping | none | not required by the rc capabilities |
| LMG-3 | Migration reconciliation, the migration reconciliation report and promotion | none | not required by the rc capabilities |
| LMG-4 | Legacy template replay into a sandbox and promotion | none | not required by the rc capabilities |
| LMG-5 | Parallel-run comparison report | none | not required by the rc capabilities |
| LMG-6 | Onboarding from other systems | none | not required by the rc capabilities |
| LMG-7 | Acquired contracts from business combinations | none | not required by the rc capabilities |
| LMG-8 | Migrations list and new migration screens | none | not required by the rc capabilities |
| LMG-9 | Migration detail screen | none | not required by the rc capabilities |
| LMG-10 | Journey J-20 legacy `ASC606.db` import with opening balances | none | not required by the rc capabilities |
| LMG-11 | Journey J-21 legacy template replay into a sandbox, then promotion | none | not required by the rc capabilities |
| GATE-LMG | Phase LMG checkpoint | none | phase checkpoint; needs every item of its phase |
| GPB-3 | Point-in-time equivalence against the shipped legacy database (1 case) | C3 | point_in_time_equivalence needs LMG-4 and SNP-1 to SNP-3 |
| GPB-4 | Full legacy parity (G3): 122 cases and the DEV sign-off listing | C3 | C3: full G3 needs GPB-3 point_in_time_equivalence, which replays into a sandbox through LMG-4 and SNP-1 to SNP-3 (deferred); 121 of 122 cases are the rc selection |
| GATE-GPB | Phase GPB checkpoint | none | phase checkpoint; needs every item of its phase |
| PRP-1 | Platform answer-key runner and the per-contract netting key | none | not required by the rc capabilities |
| PRP-2 | Platform timeline commands and the gross and delta journals key | none | not required by the rc capabilities |
| PRP-3 | Report-block platform keys: rollforward, timing, RPO bands and balance aging | none | not required by the rc capabilities |
| PRP-4 | Platform journal balance (P5) and rollforward ties (P6) | none | not required by the rc capabilities |
| PRP-5 | Platform RPO and waterfall (P7) and idempotency (P9) | none | not required by the rc capabilities |
| PRP-6 | Closed-period immutability (P11) | none | not required by the rc capabilities |
| PRP-7 | Stateful machine over the platform with a reference oracle | none | not required by the rc capabilities |
| PRP-8 | Full accounting corpus (G4) and full invariant suite (G5) | none | not required by the rc capabilities |
| GATE-PRP | Phase PRP checkpoint | none | phase checkpoint; needs every item of its phase |
| FCS-1 | Forecast tables and scenario tenants | none | not required by the rc capabilities |
| FCS-2 | Forecast event sets and scenario refresh | none | not required by the rc capabilities |
| FCS-3 | Forecast runs and forecast outputs | none | not required by the rc capabilities |
| FCS-4 | Actual vs forecast report | none | not required by the rc capabilities |
| FCS-5 | What-if modifications in scenario tenants | none | not required by the rc capabilities |
| FCS-6 | Deal-desk allocation preview and scenario save | none | not required by the rc capabilities |
| FCS-7 | Scenario, forecast event set and forecast run screens | none | not required by the rc capabilities |
| FCS-8 | Deal preview screen | none | not required by the rc capabilities |
| GATE-FCS | Phase FCS checkpoint | none | phase checkpoint; needs every item of its phase |
| AIX-1 | AI tables and the provider interface with the fake provider | none | not required by the rc capabilities |
| AIX-2 | Anthropic SDK adapter against a mocked client | none | not required by the rc capabilities |
| AIX-3 | AI gateway, `AI_TASK` job, configuration evidence, redaction and token budget | none | not required by the rc capabilities |
| AIX-4 | Tenant enablement, turn-off and the kill switch | none | not required by the rc capabilities |
| AIX-5 | Contract review extraction proposals | none | not required by the rc capabilities |
| AIX-6 | Proposal acceptance into draft contracts and rejection | none | not required by the rc capabilities |
| AIX-7 | Explain narratives with number validation | none | not required by the rc capabilities |
| AIX-8 | Anomaly detectors and flag summaries | none | not required by the rc capabilities |
| AIX-9 | Revenue Q&A with citations | none | not required by the rc capabilities |
| AIX-10 | AI settings and AI call log screens | none | not required by the rc capabilities |
| AIX-11 | Contract review screens | none | not required by the rc capabilities |
| AIX-12 | Revenue Q&A panel and embedded AI blocks | none | not required by the rc capabilities |
| GATE-AIX | Phase AIX checkpoint | none | phase checkpoint; needs every item of its phase |
| SOP-1 | Control evidence registry | none | not required by the rc capabilities |
| SOP-2 | Release manifest and engine release stamping | none | not required by the rc capabilities |
| SOP-3 | Upgrade validation replay | none | not required by the rc capabilities |
| SOP-4 | API rate limits and metrics endpoint | none | not required by the rc capabilities |
| SOP-5 | Personal data erasure commands and classification | none | not required by the rc capabilities |
| SOP-6 | Deployment self-check | none | not required by the rc capabilities |
| SOP-7 | Audit coverage of the required actions | none | not required by the rc capabilities |
| SOP-8 | Automated security test suite | none | not required by the rc capabilities |
| SOP-9 | Security documents and customer-operated ITGC guide | none | not required by the rc capabilities |
| GATE-SOP | Phase SOP checkpoint | none | phase checkpoint; needs every item of its phase |
| DMO-1 | Demo generator, deterministic datasets and persona credentials | none | not required by the rc capabilities |
| DMO-2 | Avenmoor structure, settings, chart of accounts and SSP books | none | not required by the rc capabilities |
| DMO-3 | Avenmoor customers, key contracts and seed-state figures | none | not required by the rc capabilities |
| DMO-4 | Avenmoor close history and seeded open-period items | none | not required by the rc capabilities |
| DMO-5 | Fernhill Software and Bracken Robotics demo tenants | none | not required by the rc capabilities |
| DMO-6 | Granitefield Engineering and Juniper Street Coffee demo tenants | none | not required by the rc capabilities |
| DMO-7 | Riverbend Health and Wayfarer Marketplace demo tenants | none | not required by the rc capabilities |
| DMO-8 | Legacy parity pack through migration mode (b) | none | not required by the rc capabilities |
| DMO-9 | Seed orchestration, duration and the seed report | none | not required by the rc capabilities |
| DMO-10 | Guided tour and the demo tour banner | none | not required by the rc capabilities |
| DMO-11 | Legacy transition map screen and user guide map | none | not required by the rc capabilities |
| DMO-12 | Journey J-02 SSP book version publish with approval | none | not required by the rc capabilities |
| DMO-13 | Journey J-03 contract ingest, five-step review and activation | none | not required by the rc capabilities |
| DMO-14 | Journey J-04 delivery and billing events, late invoice and over-delivery | none | not required by the rc capabilities |
| DMO-15 | Journey J-05 prospective modification with classification, impact preview and approval | none | not required by the rc capabilities |
| DMO-16 | Journey J-06 cumulative catch-up modification with linked estimates | none | not required by the rc capabilities |
| DMO-17 | Journeys J-07 variable consideration reassessment and J-08 material-right exercise | none | not required by the rc capabilities |
| DMO-18 | Journeys J-09 returns and J-10 cost-to-cost progress and EAC update | none | not required by the rc capabilities |
| DMO-19 | Journey J-11 usage minimum true-up and royalty accrual | none | not required by the rc capabilities |
| DMO-20 | Journey J-12 contract cost capitalization | none | not required by the rc capabilities |
| DMO-21 | Journey J-16 explain a number and drill to the source row | none | not required by the rc capabilities |
| DMO-22 | Journey J-19 AI contract-review proposal: accept, edit and reject | none | not required by the rc capabilities |
| DMO-23 | Journey J-26 contract void | none | not required by the rc capabilities |
| DMO-24 | Journey J-13 month-end close, part 1 (blockers to journal run approval) | none | not required by the rc capabilities |
| DMO-25 | Journey J-13 month-end close, part 2 (export, reconciliations, lock and multi-entity close) | none | not required by the rc capabilities |
| DMO-26 | Journey J-14 reopen with dual approval and re-lock | none | not required by the rc capabilities |
| DMO-27 | Journey J-15 reports and the disclosure pack | none | not required by the rc capabilities |
| DMO-28 | Journey J-17 auditor self-service evidence | none | not required by the rc capabilities |
| DMO-29 | Journey J-18 forecast scenario and deal preview | none | not required by the rc capabilities |
| DMO-30 | Journey J-25 sandbox copy and reset | none | not required by the rc capabilities |
| DMO-31 | Journey J-22 administration, part 1 (invitation, MFA and SoD block) | none | not required by the rc capabilities |
| DMO-32 | Journey J-22 administration, part 2 (SoD exception, lockout, access review and suspension) | none | not required by the rc capabilities |
| DMO-33 | Journey J-24 guided tour on an industry demo tenant | none | not required by the rc capabilities |
| DMO-34 | Every screen audit row in its stated state and the unfiltered e2e run | none | not required by the rc capabilities |
| GATE-DMO | Phase DMO checkpoint | none | phase checkpoint; needs every item of its phase |
| PRF-1 | Volume tenant generator and manifest | none | not required by the rc capabilities |
| PRF-2 | `make perf-seed` for the persistent volume tenant | none | not required by the rc capabilities |
| PRF-3 | Performance harness processes and isolation | none | not required by the rc capabilities |
| PRF-4 | Month-24 close measurement | none | not required by the rc capabilities |
| PRF-5 | Workbench latency and endpoint mix | none | not required by the rc capabilities |
| PRF-6 | Performance report, baseline warning and storage procedure | none | not required by the rc capabilities |
| GATE-PRF | Phase PRF checkpoint | none | phase checkpoint; needs every item of its phase |
| DEP-3 | Terraform data, key and storage resources | none | not required by the rc capabilities |
| DEP-4 | Terraform compute, identity, registry, load balancer and monitoring | none | not required by the rc capabilities |
| DEP-5 | Supervisor target scripts | C11 | supervisor target scripts; the supervisor validates the images and compose file by hand |
| DEP-6 | Runbook and recovery objectives | none | not required by the rc capabilities |
| DEP-7 | User guide and legacy migration guide | none | not required by the rc capabilities |
| DEP-8 | OpenAPI currency and artifact presence | none | not required by the rc capabilities |
| GATE-DEP | Phase DEP checkpoint | none | phase checkpoint; needs every item of its phase |
| REL-1 | Pre-release gate sweep and regression fixes | none | not required by the rc capabilities |
| REL-2 | Traceability and the supervisor verification register | none | not required by the rc capabilities |
| REL-3 | Final release gate | none | not required by the rc capabilities |
| ENA-2b | Stage 02 time-elapsed 25-7(a) completion, dated evaluation, STEP1_MET netting, overpayment cap and RPO exclusion (D-91; L1-2-Q-9, GAPS-A3). Supervisor item | C2, C3 | stage 02 time-elapsed 25-7(a) completion, dated evaluation, STEP1_MET netting, overpayment cap and RPO exclusion (D-91): in the rc a nonrefundable deposit on a Step 1 failure completed by time keeps its deposit liability and recognises no revenue |
| END-4b | Stage 14 JET-01b 25-7 revenue part: s13/s14 binding, obligation attribution (S14-R-25), CLOSE_RELEASE time share and FX split (D-91; L5-5-Q-5). Supervisor item | C2, C3 | stage 14 JET-01b 25-7 revenue part with S14-R-25 attribution, CLOSE_RELEASE time share and FX split (D-91): in the rc a 25-7 recognition fails closed (stage 13 guard, ENG-B3) |
| ENA-4b | Stage 03 ASC 606-10-55-62 functional-IP exception: T-CON-19 members, S03-R-10 consumer and licence-nature drawer (D-91; L2-2-Q-4). Supervisor item | C2, C3 | ASC 606-10-55-62 functional-IP exception, T-CON-19 members and licence-nature drawer (D-91): in the rc a functional licence is a right to use; access for SYMBOLIC only |

### Levels


#### L1: about 4.6 h (cumulative 4.6 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L1-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: RFD-1 (40)<br>B2: RFD-6 (40)<br>B3: RFD-2 (40)<br>B4: RFD-3 (40)<br>B5: RFD-8 (40) | RFD-1 adds a revision (make revision ITEM=RFD-1)<br>RFD-6 adds a revision (make revision ITEM=RFD-6)<br>RFD-2 adds a revision (make revision ITEM=RFD-2)<br>RFD-3 adds a revision (make revision ITEM=RFD-3)<br>RFD-8 adds a revision (make revision ITEM=RFD-8) |
| L1-2 | Engine: stages 01 to 05 | no | B1: ENA-1, ENA-2 (60)<br>B2: ENA-3, ENA-5 (60)<br>B3: ENB-1, ENA-6 (60)<br>B4: ENA-10, ENA-11 (60) |  |
| L1-3 | Engine: stages 07 to 09 | no | B1: ENC-1, ENC-2 (60)<br>B2: ENC-3, ENC-4 (60)<br>B3: ENC-7, ENC-9 (60)<br>B4: ENB-9, ENB-10 (60) |  |
| L1-4 | Platform: RFD, WEB, DEP | no | B1: RFD-4, RFD-5 (70)<br>B2: WEB-8 (40)<br>B3: WEB-9, DEP-1 (65)<br>B4: DEP-2 (25) |  |
| L1-5 | Platform: WEB | no | B1: WEB-10 (50) |  |

Merge order: L1-1 → L1-2 → L1-3 → L1-4 → L1-5

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`

#### L2: about 4.8 h (cumulative 9.3 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L2-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: RFD-7 (40)<br>B2: RFD-9 (40)<br>B3: RFD-12 (40)<br>B4: RFD-13 (40)<br>B5: RFD-10 (40)<br>B6: RFD-15 (40) | RFD-7 adds a revision (make revision ITEM=RFD-7)<br>RFD-9 adds a revision (make revision ITEM=RFD-9)<br>RFD-12 adds a revision (make revision ITEM=RFD-12)<br>RFD-13 adds a revision (make revision ITEM=RFD-13)<br>RFD-10 adds a revision (make revision ITEM=RFD-10)<br>RFD-15 adds a revision (make revision ITEM=RFD-15) |
| L2-2 | Engine: stages 03 to 05 and the inception fold | no | B1: ENA-4, ENA-7 (60)<br>B2: ENA-8, ENA-9 (60)<br>B3: ENA-12, ENA-13 (70) |  |
| L2-3 | Engine: stage 06 modifications | no | B1: ENB-2, ENB-3 (60)<br>B2: ENB-4, ENB-5 (60)<br>B3: ENB-6, ENB-7 (60)<br>B4: ENB-8 (30) |  |
| L2-4 | Engine: stages 09 to 11 | no | B1: ENC-10, ENC-11 (60)<br>B2: ENC-12, ENC-13 (60)<br>B3: ENC-14, ENC-15 (60)<br>B4: ENC-16 (30) |  |
| L2-5 | Engine: stage 08 late events and stages 12 to 14 | no | B1: ENB-11, ENB-12 (60)<br>B2: END-1, END-2 (60)<br>B3: END-3, END-4 (60)<br>B4: END-5, END-6 (60) | END-1 integration-after-merge: codes against the contract of ENC-15 (s12 consumes the CostLossState type of s11) |

Merge order: L2-1 → L2-2 → L2-3 → L2-4 → L2-5

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05"`

#### L3: about 4.9 h (cumulative 14.2 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L3-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: CTR-1 (40) | CTR-1 adds a revision (make revision ITEM=CTR-1) |
| L3-2 | Engine: boundary fold, books and compute, stage 15 | no | B1: ENB-13, END-7 (70)<br>B2: END-8, END-9 (75)<br>B3: END-10, EDS-1 (60)<br>B4: EDS-2 (30) |  |
| L3-3 | Platform: RFD | no | B1: RFD-11, RFD-14 (70)<br>B2: RFD-16 (60) |  |
| L3-4 | Frontend: WEB | no | B1: WEB-11 (70)<br>B2: WEB-12 (55)<br>B3: WEB-15 (55)<br>B4: WEB-17 (55) |  |

Merge order: L3-1 → L3-2 → L3-3 → L3-4

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS  # 4 keys named by merged items must pass`
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L4: about 5.0 h (cumulative 19.2 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L4-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: CTR-2 (50)<br>B2: CTR-3 (45)<br>B3: CTR-4, CTR-5 (75)<br>B4: DIN-1 (40) | CTR-2 adds a revision (make revision ITEM=CTR-2)<br>CTR-3 adds a revision (make revision ITEM=CTR-3)<br>CTR-5 adds a revision (make revision ITEM=CTR-5)<br>DIN-1 adds a revision (make revision ITEM=DIN-1) |
| L4-2 | Engine: stages 12 to 15 and compute | no | B1: EDS-3, EDS-4 (60)<br>B2: EDS-5, EDS-6 (60)<br>B3: AKS-1 (60)<br>B4: AKS-2 (60) | AKS-2 partial: 38 of 40 named keys runnable; the rest wait for deferred ENC-6; tick only when every key passes |
| L4-3 | Frontend: RFD | no | B1: RFD-19 (55)<br>B2: RFD-22 (55)<br>B3: RFD-24 (55) |  |

Merge order: L4-1 → L4-2 → L4-3

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L5: about 4.6 h (cumulative 23.8 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L5-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: CLO-1 (40)<br>B2: DIN-2 (40)<br>B3: CLO-2 (40)<br>B4: CTR-7 (40)<br>B5: CTR-15, DIN-3 (75) | CLO-1 adds a revision (make revision ITEM=CLO-1)<br>DIN-2 adds a revision (make revision ITEM=DIN-2)<br>CLO-2 adds a revision (make revision ITEM=CLO-2)<br>CTR-7 adds a revision (make revision ITEM=CTR-7); CTR-7 partial: 6 of 7 named keys runnable; the rest wait for deferred ENC-5; tick only when every key passes<br>CTR-15 adds a revision (make revision ITEM=CTR-15) |
| L5-2 | Engine: answer-key sweeps | no | B1: AKS-3 (60)<br>B2: AKS-4 (60)<br>B3: AKS-5 (60)<br>B4: AKS-6 (60) | AKS-3 partial: 30 of 38 named keys runnable; the rest wait for deferred ENC-5, ENC-6, ENC-8; tick only when every key passes<br>AKS-4 partial: 26 of 33 named keys runnable; the rest wait for deferred ENC-5, ENC-6; tick only when every key passes<br>AKS-5 partial: 28 of 34 named keys runnable; the rest wait for deferred ENC-5, ENC-8; tick only when every key passes<br>AKS-6 partial: 24 of 27 named keys runnable; the rest wait for deferred ENC-5; tick only when every key passes |
| L5-3 | Platform: CTR | no | B1: CTR-8 (35) |  |

Merge order: L5-1 → L5-2 → L5-3

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)

#### L6: about 4.6 h (cumulative 28.4 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L6-1 | Schema chain: the only lane adding Alembic revisions this level | yes | B1: CTR-10 (40)<br>B2: CTR-12 (40)<br>B3: CTR-14 (40)<br>B4: DIN-12 (40)<br>B5: RPS-1 (40)<br>B6: DIN-10 (40) | CTR-10 adds a revision (make revision ITEM=CTR-10)<br>CTR-12 adds a revision (make revision ITEM=CTR-12)<br>CTR-14 adds a revision (make revision ITEM=CTR-14)<br>DIN-12 adds a revision (make revision ITEM=DIN-12)<br>RPS-1 adds a revision (make revision ITEM=RPS-1)<br>DIN-10 adds a revision (make revision ITEM=DIN-10) |
| L6-2 | Engine: answer-key sweeps | no | B1: AKS-7 (60) |  |
| L6-3 | Platform: CLO | no | B1: CLO-3 (35) |  |

Merge order: L6-1 → L6-2 → L6-3

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)

#### L7: about 4.2 h (cumulative 32.7 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L7-1 | Platform: CLO | no | B1: CLO-4, CLO-5 (70)<br>B2: CLO-6, CLO-16 (70)<br>B3: CLO-18 (35)<br>B4: CLO-19 (45) |  |
| L7-2 | Schema chain (CTR, DIN, GPA): the only lane adding Alembic revisions this level | yes | B1: CTR-9, DIN-4 (75)<br>B2: CTR-17 (40)<br>B3: GPA-1 (60)<br>B4: DIN-5 (35) | DIN-4 adds a revision (make revision ITEM=DIN-4)<br>CTR-17 adds a revision (make revision ITEM=CTR-17) |
| L7-3 | Platform: CTR | no | B1: CTR-19 (35) |  |
| L7-4 | Platform: DIN | no | B1: DIN-14 (35) |  |

Merge order: L7-1 → L7-2 → L7-3 → L7-4

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)
- `make parity K="(initial_allocation)"`

#### L8: about 4.5 h (cumulative 37.2 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L8-1 | Platform: GPA | no | B1: GPA-2 (45) |  |
| L8-2 | Platform: CLO | no | B1: CLO-7, CLO-8 (70)<br>B2: CLO-11, CLO-13 (70)<br>B3: CLO-14, CLO-15 (70) |  |
| L8-3 | Platform: CTR | no | B1: CTR-20 (60)<br>B2: CTR-21 (55)<br>B3: CTR-11 (35)<br>B4: CTR-22 (55) |  |
| L8-4 | Platform: DIN legacy v1 modes, template defects and exception queue | no | B1: DIN-6, DIN-7 (70)<br>B2: DIN-8, DIN-11 (70) |  |

Merge order: L8-1 → L8-2 → L8-3 → L8-4

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)
- `make parity K="(initial_allocation) or (contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07))"`
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L9: about 4.7 h (cumulative 41.8 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L9-1 | Platform: GPA, CLO | no | B1: GPA-3 (45)<br>B2: GPA-4 (45)<br>B3: GPA-5 (45)<br>B4: CLO-9 (35)<br>B5: GPA-6 (45) |  |
| L9-2 | Platform: CLO | no | B1: CLO-17 (35)<br>B2: CLO-20 (50)<br>B3: CLO-22 (60)<br>B4: CLO-26 (55) |  |
| L9-3 | Platform: RPS | no | B1: RPS-2 (45) |  |
| L9-4 | Frontend: DIN, CTR | no | B1: DIN-15 (55)<br>B2: CTR-26 (55)<br>B3: DIN-16 (55)<br>B4: DIN-17 (55) |  |
| L9-5 | Frontend: CTR workbench tabs | no | B1: CTR-23 (55) |  |

Merge order: L9-1 → L9-2 → L9-3 → L9-4 → L9-5

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)
- `make parity K="(initial_allocation) or (contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)) or (catchup-08 or catchup-09 or rollforward-08 or rollforward-09) or (catchup-10 or catchup-11 or catchup-12 o …` (full selection in plan.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

#### L10: about 5.3 h (cumulative 47.2 h)

| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |
|---|---|---|---|---|
| L10-1 | Platform: RPS, GPB | no | B1: RPS-3, RPS-4 (70)<br>B2: RPS-5, RPS-17 (70)<br>B3: GPB-1 (45)<br>B4: GPB-2 (45) |  |
| L10-2 | Frontend: CLO, RPS | no | B1: CLO-23 (55)<br>B2: RPS-6 (55)<br>B3: RPS-7 (55)<br>B4: RPS-22 (55) | RPS-6 integration-after-merge: codes against the contract of RPS-4 (rpo report capture); RPS-6 integration-after-merge: codes against the contract of RPS-5 (legacy export capture); RPS-6 integration-after-merge: codes against the contract of RPS-3 (a report cell opens the Explain panel through GET /explain/report-runs/{id}/cell (API-R-49))<br>RPS-7 integration-after-merge: codes against the contract of RPS-3 (binds revenue_waterfall); RPS-7 integration-after-merge: codes against the contract of RPS-5 (binds legacy_je_summary)<br>RPS-22 integration-after-merge: codes against the contract of RPS-17 (binds API-R-50) |

Merge order: L10-1 → L10-2

Merge gates:

- `git status --porcelain  # empty after the merge commits`
- `make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts`
- `make ci`
- `make test-pg`
- `make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07"`
- `make answer-keys ID=RND-CHK-001,RND-CHK-001-USD-EQUAL-SSP-THIRDS,RND-CHK-003A,RND-CHK-005-USD-100-OVER-THREE-MONTHS,RND-CHK-002-CHK-007-GT01-CONTRACT1,RND-CHK-003A-JPY-EQUAL-SSP-THIRDS,RND-CHK-003B,RND-CHK-003B-BHD-WEIGHTS-ONE-TWO,RND-CHK-003C,RND-CHK-003C-USD-NEGATIVE-CREDIT-MEM …` (full selection in plan.json)
- `make parity K="(initial_allocation) or (contract_position and (rollforward-02 or rollforward-03 or rollforward-04 or rollforward-05 or rollforward-06 or rollforward-07)) or (catchup-08 or catchup-09 or rollforward-08 or rollforward-09) or (catchup-10 or catchup-11 or catchup-12 o …` (full selection in plan.json)
- `make e2e SPEC=frontend/e2e/projects/screens.spec.ts`

### Answer-key support by family

| Family | Active | Runnable | Blocked by |
|---|---:|---:|---|
| ALC | 10 | 10 | none |
| BRK | 6 | 0 | ENC-8 |
| COST | 5 | 5 | none |
| CPC | 6 | 6 | none |
| DISC | 8 | 6 | ENC-6, PRP-1 |
| DLT | 2 | 1 | PRP-1 |
| ENT | 5 | 5 | none |
| FX | 11 | 11 | none |
| IFRS | 4 | 3 | ENC-5 |
| JE | 12 | 11 | ENC-5 |
| LATE | 3 | 3 | none |
| LOSS | 2 | 0 | ENC-5 |
| MOD | 19 | 10 | ENC-5 |
| MR | 12 | 8 | ENC-8 |
| NCC | 1 | 1 | none |
| ONB | 3 | 3 | none |
| POB | 16 | 12 | ENC-6 |
| POS | 11 | 6 | ENC-5, ENC-6, PRP-1 |
| REC | 24 | 14 | ENC-5, ENC-6 |
| RET | 7 | 7 | none |
| RND | 25 | 25 | none |
| ROY | 3 | 0 | ENC-6, ENC-8 |
| SFC | 8 | 8 | none |
| SSP | 8 | 8 | none |
| STP1 | 5 | 5 | none |
| TAX | 2 | 2 | none |
| VC | 14 | 10 | ENC-5, ENC-6 |

### Variants

| Variant | Description | In scope | Migration items | Levels | Hours | Merged by 9 h | Moved to post-rc |
|---|---|---:|---:|---:|---:|---:|---|
| V-0 | plan as emitted, with the validator layout fixes V-01 to V-09 applied | 163 | 29 | 10 | 47.2 | 62 | none |
| V-A | two migration lanes per level; the merge step re-parents the second lane's revisions onto the first (down_revision edit and renumber) and runs test_single_head and test_upgrade_downgrade_upgrade | 163 | 29 | 9 | 43.8 | 61 | none |
| V-B | supervisor descoping ruling R-RC-1: captures of seeded close history, drawers of unbuilt commands and worlds built on deferred commands move to post-rc | 144 | 26 | 10 | 44.9 | 61 | CTR-11, CTR-14, CTR-17, DIN-12, DIN-14, EDS-4, EDS-5, EDS-6, CLO-5, CLO-6, CLO-7, CLO-14, CLO-15, CLO-16, CLO-17, CLO-18, CLO-19, CLO-20, CLO-22 |
| V-C | platform consumers of engine functions and compute outputs code against ENGINE_SPEC §0.5 with fakes (integration-after-merge); number-asserting tests go green only in the merge gate | 163 | 29 | 10 | 47.9 | 61 | none |
| V-ABC | V-A, V-B and V-C together | 144 | 26 | 8 | 39.2 | 61 | CTR-11, CTR-14, CTR-17, DIN-12, DIN-14, EDS-4, EDS-5, EDS-6, CLO-5, CLO-6, CLO-7, CLO-14, CLO-15, CLO-16, CLO-17, CLO-18, CLO-19, CLO-20, CLO-22 |

<!-- generated by plan_tools.py: end -->

## 11. Validation

| Field | Value |
|---|---|
| Validator | Independent plan validator (slug `sprint-validator`) |
| Date | 2026-09-13 |
| Script | `python3 docs/build-spec/sprint/validate_plan.py check` (exit 1 on failure). The script does not import `plan_tools.py`; `apply` writes the layout fixes below into `plan.json` and the Levels tables of section 10 |
| Result | All six checks pass after fixes V-01 to V-10. Before them, check (a) failed with 13 findings |

### 11.1 Method

- **Parser.** The script has its own item-block parser. It reads Scope Paths at parenthesis depth 0, with bare names inheriting the previous directory, plus the files named in Acceptance, the Schema T-ids, API rows and Engine lines. Done items come from `git log`, with WEB-7 counted as done.
- **Hard edges.** These kinds are derived automatically:
  - declared prerequisites other than the loop predecessor, and ids named in provenance notes;
  - the first lister of a file not yet on disk;
  - package directories (source packages only; test directories carry no `__init__.py`);
  - the creator of a table named in Schema;
  - bound API rows, resolved through route qualifiers such as "list" and "balances";
  - the stage state chain of ENGINE_SPEC Table 0.2-A.

  In addition, 25 edges were confirmed by reading item text (`VERIFIED_EDGES`).
- **Loop-order edges.** A declared predecessor or phase gate is treated as loop order, confirming section 2.2. It fails check (a) or (b) only when the item text names a file stem or symbol that the predecessor creates. After the fixes, 51 loop-order edges are not satisfied by position:
  - 34 point to deferred items: the gates of ENA-1, RFD-1, ENB-1, ENC-1, END-1, AKS-1, CTR-1, DIN-1, GPA-1, EDS-1, CLO-1, RPS-1, GPB-1 and DEP-1, plus WEB-14, WEB-16, RFD-18, RFD-21, RFD-23, ENC-6, ENC-8, CTR-6, CTR-13, CTR-16, CTR-18, CTR-25, DIN-9, DIN-13, CLO-10, CLO-12, CLO-21, CLO-25, RPS-16 and RPS-21;
  - 17 sit at a later level or in another lane: WEB-10/WEB-9, ENA-5/ENA-4, ENA-10/ENA-9, RFD-4/RFD-3, RFD-6/RFD-5, RFD-8/RFD-7, RFD-12/RFD-11, RFD-15/RFD-14, ENB-9/ENB-8, CTR-8/CTR-7, CTR-10/CTR-9, CTR-12/CTR-11, CTR-15/CTR-14, DIN-12/DIN-11, CLO-16/CLO-15, CLO-18/CLO-17 and RPS-6/RPS-5.

  One corroborated edge was reviewed and accepted: RFD-19/RFD-18. SF-15:setup creates its entity and period through the RFD-1 and RFD-2 API.
- **Contract edges.** A same-level edge to another lane passes only for kinds `state` or `api-bind` with an integration note. File, table and verified edges cannot be coded against a fake. Accepted: END-1 on ENC-15, RPS-6 on RPS-3 and RPS-22 on RPS-17.
- **Shared files, check (d).** No two lanes of a level may touch the non-mergeable files: `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json` and Alembic `versions/`. The brief's mergeable registries and generated files may overlap only under a section 4.3 rule. Observed overlaps, all ruled, counted as lane pairs:

  | File | Lane pairs |
  |---|---:|
  | `openapi.json`, `schema.d.ts` | 13 each |
  | `api/router.py` | 10 |
  | `approvals/subjects.py` | 6 |
  | `test_registries_complete.py` | 4 |
  | `stages/__init__.py`, `test_stage_registry.py` (L2 engine lanes) | 3 each |
  | `router.tsx` (L9) | 1 |

  Nothing overlaps on a lock file or Alembic `versions/`, and every level has at most one migration lane.

### 11.2 Results

| Check | Before fixes | After fixes |
|---|---|---|
| (a) prerequisites placed | FAIL, 13 findings | PASS; 3 contract edges accepted |
| (b) no dependency on deferred items | PASS | PASS |
| (c) MVP capabilities covered | PASS | PASS; GPB-4, AKS-8, RPS-23 and RPS-24 excluded with recorded reasons; SUP-RC-SMOKE replaces J-01 |
| (d) migrations and shared files | PASS (RFD-13 reviewed) | PASS |
| (e) batch sizes, lanes, merge orders | PASS | PASS |
| (f) exactly once, partition | PASS | PASS; 163 in scope, 184 deferred, 80 done, 427 items |

### 11.3 Changes to `plan.json` and this file

| Id | Check | Finding (evidence in BUILD_SPEC) | Change |
|---|---|---|---|
| V-01 | (a) | DIN-7 (was L5-4) exercises the SKU SSP and contract setup templates of DIN-4 (L7-2): `test_defects.py::test_tc_setup_13` to `…_20` | DIN-7 moves to L8-4, after DIN-6 |
| V-02 | (a) | DIN-8 (was L5-4) uploads progress and modification files through DIN-5 (L7-2) and DIN-6 (L8-4): TC-delivery-12, 14 and 17; TC-RM-09, 10 and 16; TC-pob-vc-10 and 15 | DIN-8 moves to L8-4, after DIN-7. GPB-1 (L10) still follows |
| V-03 | (a) | DIN-11 (was L5-4) dismisses the `PROGRESS_OVER_DELIVERY` items of an INVALID progress import from DIN-5 (L7-2) | DIN-11 moves to L8-4. DIN-17 (L9) and RPS-22 (L10) still follow. Lane L5-4 is removed |
| V-04 | (a) | CTR-23 (was L6-4) renders tabs of the SF-03 frame built by CTR-22 and captures seeded K-02 from CTR-20; both are in L8-3 | CTR-23 moves to new lane L9-5. Lane L6-4, the L6 e2e gate and the CTR-23 integration note are removed |
| V-05 | (a) | ENA-3 (L1-2) consumes the `IdentifiedState` returned by ENA-2 (last batch of L1-3): a same-level state edge with no integration note | ENA-1 and ENA-2 open L1-2. ENB-10 moves to L1-3, and ENA-9 to L2-2 after ENA-8 |
| V-06 | (a) | ENB-4 (L2-3, batch 2) needs the pools of ENB-2 (L2-3, batch 4) and the catch-up of ENB-3 (L3-3): CHK-115, CU −15,555.56 | L2-3 holds ENB-2 to ENB-8 in document order. ENB-11 and ENB-12 open L2-5, so END-5 follows ENB-11 in its own lane and drops its integration note. Lane L3-3 is removed; L3-4 and L3-5 become L3-3 and L3-4 |
| V-07 | (a) | ENC-7 (L1-3) adjusts the units measure built by ENC-4 (L2-4): `test_chk_061_golden_return` | ENC-4 moves to L1-3, before ENC-7. L2-4 holds ENC-10 to ENC-16 in document order |
| V-08 | (a) | RPS-6 (L10-2) opens the Explain panel on a report cell through `GET /explain/report-runs/{id}/cell` (API-R-49, RPS-3 in L10-1) with no integration note | `integration_after_merge` gains RPS-6 on RPS-3 |
| V-09 | (a) | Declared predecessor later in the same lane. CLO-19 names `EXCEPTIONS_CLEARED` from CLO-18 | Batches reordered into document order: ENB-6/ENB-5, ENB-8/ENB-7, ENC-3/ENC-2, ENC-15/ENC-14, END-4/END-3, CLO-15/CLO-14 and CLO-19/CLO-18. No cost change |
| V-10 | (d) | RFD-13 adds DB-04 and DB-05 triggers in its own revision without naming the file | No move: RFD-13 already sits in the L2-1 migration lane. Recorded in `MIGRATION_REVIEW` |

Effect of the fixes:

- **Hours and lanes.** L2 drops from 4.9 h to 4.8 h and L6 from 5.2 h to 4.6 h; the total drops from 47.9 h to 47.2 h. Lanes per level: L3 from 5 to 4, L5 from 4 to 3, L6 from 4 to 3, L9 from 4 to 5. Scope is unchanged at 163 items.
- **`plan.json`.** It gains a `validation` block. The script recomputed `levels`, `integration_after_merge`, `horizon_9h` (L2 at 9.3 h, 62 items), `estimate_hours`, variant V-0 and the file scopes of the changed lanes.
- **Variants.** V-A, V-B, V-C and V-ABC carry a `validator_note`. They were packed on the pre-validation layout and are not re-validated.

### 11.4 Answer-key families (independent count)

The validator derives blockers from key method and event values, each mapped to a deferred item whose title names it: ENC-5 (cost to cost, labour hours, cost recovery), ENC-6 (right to invoice, usage) and ENC-8 (material rights, royalties). Platform-runner keys wait for PRP-1. The result is 180 of 232 active keys runnable and 52 blocked, matching section 7.2 family by family. A first pass missed method `COST_RECOVERY` (REC-S5-PROGRESS-VARIANTS-COSTRECOVERY); with that corrected, the counts match.

| Status | Families (runnable of active; blocked by) |
|---|---|
| Not runnable | BRK 0 of 6 (ENC-8); LOSS 0 of 2 (ENC-5); ROY 0 of 3 (ENC-6, ENC-8) |
| Partly runnable | DISC 6 of 8 (ENC-6, PRP-1); DLT 1 of 2 (PRP-1); IFRS 3 of 4 (ENC-5); JE 11 of 12 (ENC-5); MOD 10 of 19 (ENC-5); MR 8 of 12 (ENC-8); POB 12 of 16 (ENC-6); POS 6 of 11 (ENC-5, ENC-6, PRP-1); REC 14 of 24 (ENC-5, ENC-6); VC 10 of 14 (ENC-5, ENC-6) |

### 11.5 Estimates

- **Wall clock (V-0 after validation).** 10 levels, 47.2 h. The first boundary after 9 h is L2 at 9.3 h, with 62 items merged.
- **Longest chain of derived hard edges.** 7.7 h: WEB-10 → RFD-15 → CTR-2 → CTR-3 → CLO-8 → CLO-13 → CLO-15 → CLO-22 → CLO-26 → RPS-7. This is a lower bound, because the validator adds an edge only where the text proves it. The planner's 18.8 h path (section 1) also counts loop order inside the engine and close phases. Either way, the binding constraints are the one-migration-lane rule and level boundaries, not the dependency chain.

### 11.6 Residual risks

| Id | Risk | Mitigation |
|---|---|---|
| R-V1 | The 51 accepted loop-order edges may hide dependencies that the item text does not name | Lane GK gates and the level merge gates catch them. A defect goes to a supervisor item or to the next level |
| R-V2 | END-1 on ENC-15 remains a type contract, and `CostLossState` is not in `stages/state.py` | END-1 codes to ENGINE_SPEC_B §11.1 with a local fake, replaced in the L2 merge step |
| R-V3 | `plan_tools.py all` would revert these fixes | Add the `VERIFIED_EDGES` of `validate_plan.py` to `MANUAL_EDGES` first, or rerun `validate_plan.py apply`, then `validate_plan.py check` |
| R-V4 | DIN-11 on DIN-5 and ENB-4 on ENB-3 are judgements from test descriptions; a test could build its input without them | The moves cost no level. Revert them only after the lane confirms the tests build their own inputs |
| R-V5 | The plan still needs about 47 h against the brief's 9 h. At the 9.3 h checkpoint no contracts, imports, close or report capability exists | Section 8 decisions |
