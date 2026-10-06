# Sprint L9 merge (round A): gates, selections and remaining items

Supervisor record of the Level 9 round A merge on main (2026-09-18). Level 9 grew out of the L8 remediation: the four release-selection failures and the lane questions left at the L8 merge were ruled in D-90 to D-90d (`docs/01-DECISIONS.md`; ruling summaries in `docs/reviews/loop/sprint/L8-merge.md` "D-90 rulings", "D-90a rulings", "D-90b ruling", "D-90d rulings"; D-90c in `docs/01-DECISIONS.md` and the L9-ENG batch 2 record), and three lanes implemented them in worktrees `~/dev/erev-wt/l2` (platform, `sprint/l2`), `~/dev/erev-wt/l5` (answer-key runner, `sprint/l5`) and `~/dev/erev-wt/l6` (engine, `sprint/l6`). The merge workflow (erev-sprint-L9-merge) merged the three lanes in order PLT, RUN, ENG on main at 1dda2d1 (docs only since 68301bd; all three worktrees clean). The supervisor ran the release gate on main at 22d6c6e with `.run/l9gate/gates.sh` (logs `.run/l9gate/g/`, summary `.run/l9gate/summary.txt`). The lane questions left open at the merge and the QA pass 2 verdicts are ruled in D-90e ("D-90e ruling" below).

## Merges and integration fixes

- Merges, all `--no-ff` and without conflicts: ad06f60 (L9-PLT, `sprint/l2` at 803ba75; 21 files; `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` auto-merged), ea545fd (L9-RUN, `sprint/l5` at 95912e4; 4 files), 22d6c6e (L9-ENG, `sprint/l6` at c570ea5; 30 files). The lanes share no changed file.
- `make openapi` after the last merge: no drift (`git status --porcelain` on `docs/api/openapi.json` and `schema.d.ts` empty); no commit needed.
- Alembic: no lane adds a revision (54 version files on main and on every lane branch); heads selection 3 passed; `alembic heads` 0054.
- `make lint` OK (175 tagged control tests of 2609 collected; one Alembic head); `make typecheck` OK (mypy 558 source files; tsc) on the merged tree.
- No integration fix was needed: no "L9-merge:" commit exists. The two `make ci` failures the lanes reported as pre-existing on main (`test_d85_key_implied_price_change_settlement`, fixed by 9df7678 in the runner lane; `test_dg_arc_13_imp_rows_cover_codes`, fixed by IMP-106 and the pin 106 in 1dda2d1) are resolved on the merged tree: a non-DB sweep of `backend/tests/engine` plus the DG-ARC-13 catalogue test gave 724 passed.

### Lane commits merged

Platform lane L9-PLT (`sprint/l2`; evidence `docs/reviews/loop/sprint/L9-PLT.md`):

| Commit | Ruling | Change |
|---|---|---|
| ef4837c | D-90a QA-L9-7 with L8-C-Q-2 | 04 API-S-PeriodCockpit `pending_requests` (`BLOCKER_REQUEST_TYPES`: `JUDGEMENT_RECORD`, then `MANUAL_ADJUSTMENT`; `PendingRequestCountOut`); the SF-05 cockpit subtracts them for BLK-06 and BLK-15 and no longer reads `GET /approvals` for blockers |
| b5c4f0d | D-90a QA-L9-5a | SF-12:request generic field diff formats money objects and arrays (DS-FMT-01), period amounts with the tenant calendar label, records to depth 2, hides `id` and `*_ids`, labels members from catalogue keys |
| 7600b93 | D-90 L8-R-Q-4 | SF-06:entries failed-run banner names "Reference <job id prefix>" |
| 08d72b7 | evidence | L9-PLT batch 1 record with measured gates |
| ef985d6 | merge | `main` (198491c, docs only) into `sprint/l2` |
| 14100e7 | supervisor finding plt-job-reference | `useReportRun` binds the (run id, job id) pair from the 202 (`X-Erev-Report-Run-Id`, `Location`) and exposes `createdJobId` only while the displayed run is that run; SF-08:report and SF-06:entries read it; six vitest cases fail on the batch-1 code |
| 803ba75 | evidence | L9-PLT batch 2 record |

Runner lane L9-RUN (`sprint/l5`; evidence `docs/reviews/loop/sprint/L9-RUN.md`):

| Commit | Ruling | Change |
|---|---|---|
| 9df7678 | D-90 RND-CHK-003C | `test_d85` expects the per-obligation REFUND_LIABILITY credits of the regenerated key (cr 33.34 / 33.33 / 33.33) |
| faf425a | D-90 RET-BR-03 | the engine runner attributes a contract-filtered subledger entry by the `contract_key` its lines carry, fails closed, reports unattributable entries once through `subledger()` |
| 6511ce3 | D-90 RET-BR-03 review fix | refund component sources parse by their kind grammar (RETURN and VARIABLE_CONSIDERATION `<contract>/<obligation or element>`; TERMINATION `<contract>/EV-<n>`; CONCESSION `<contract>/EV-<n>/<contract>/<obligation>` or `…/<contract>@<entity>`); split on encoded delimiters before decoding; UNCLAIMED_PROPERTY fails closed |
| 95912e4 | evidence | L9-RUN record: source grammar table, fail-first proof on a faf425a overlay (24 failed, 26 passed), engine subject census (16,539 intents; 0 unparsed, 0 attribution differences), measured gates at 6511ce3 |

Engine lane L9-ENG (`sprint/l6`; evidence `docs/reviews/loop/sprint/L9-ENG.md`):

| Commit | Ruling | Change |
|---|---|---|
| 81d9b5e | D-90b S06-R-11 | remaining service ρ_p of a class D time-elapsed obligation over reconstructed unit layers (`segments.convention_of`, `calendar_of`, `term_in_force`, `eligible`, `unit_layers`, `remaining_scale`; `weights.existing`, `inception_basis.existing`; additive trace params on `mod.weights.d18.v1` and `mod.weights.inception_all.v1`) |
| 0020a1e | D-90b S06-R-08 | `MOD_UNIT_HISTORY_AMBIGUOUS` in the `_check_remaining` loop, before any weight |
| 017d293 | D-90b fixtures | TPL-SAAS fixture template becomes a series (increment day) in `test_s06_prospective.py` and `test_s15_rpo.py`; no figure, key or golden change |
| 4fc5d43 | D-90b tests | `test_s06_remaining_service.py`, 53 tests |
| bfad602 | evidence | L9-ENG batch 1 record |
| c860fe1 | merge | `main` (198491c) into `sprint/l6` |
| 6fcf857 | D-90c | same-date modifications are ordered boundaries; the `OPPOSITE_SAME_DATE` condition is withdrawn; both orders accepted with the D-90c figures (ρ 11/40 and 4/15) |
| d06f3a8 | D-90d Q-3, Q-4, Q-8 | CV-21 encoded group, entity and contract heads in stage 10, 12 and 15 subjects (`s01 group_entity_subject_key`); `refund_liability.measure` encoded-head lookup; `s08 routing._element_contract`; `assign.subject_contracts` and `_component_contract` resolve refund component keys to the owning member |
| c570ea5 | evidence | L9-ENG batch 2 record |

## Selections measured at the merge (main at 22d6c6e; logs `.run/l9merge/`)

| Selection | Result |
|---|---|
| Alembic heads (`make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"`) | 3 passed; head 0054 |
| `make lint`, `make typecheck` | OK, OK |
| `make openapi` and drift check | OK, no drift |
| `make answer-keys`, release selection (`rg-selection.txt`, 173 ids) | 173 of 173 passed, 0 failed (the first fully green selection); newly passing against 68301bd: MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION, RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION; against 30db7f4 (L8 gate) also RND-CHK-003C |
| `make answer-keys`, all active | 174 of 232 (234 selected; 58 failed, 2 withdrawn); +2 over the 68301bd baseline (172) |
| Lost-fix proof (`.run/l9merge/keys-all-failed.txt`) | the merged failing set (58) is a strict subset of the ENG batch 2 failing set (59; difference RET-BR-03), of the RUN failing set at 6511ce3 (59; difference MOD-JS-06), of main at 68301bd (60; differences MOD-JS-06, RET-BR-03) and of main at 30db7f4 (61; differences MOD-JS-06, RET-BR-03, RND-CHK-003C). No key that passed on any lane or on main fails on the merged tree |
| `make parity K="not point_in_time_equivalence"` | 121 of 121 (ran alone; no lock timeouts) |
| `make properties K=p14` | 0 collected (exit 5): no `test_prop_p14*.py` exists on HEAD, 68301bd, any lane branch or anywhere in history (dev-guide row P14 names `test_prop_p14_trace_reevaluation.py`; the 12 collected property tests are p01 to p13). Not a merge regression; P14 (`reevaluate(trace)` exact) is exercised by DG-AK-54 in every answer-key checkpoint and by the ENG reevaluate tests. Recorded as an editorial for the dev-guide P-list |
| Targeted pytest (`backend/tests/unit/answer_keys`, `engine/s06_modifications`, `engine/s15_disclosures`, `api/test_cockpit.py`, `domain/close`; slow included) | 265 passed, 0 failed (includes `test_d85_key_implied_price_change_settlement`) |
| Targeted vitest (cockpit, request, viewer suites) | 4 files, 42 passed |
| Non-DB sweep of the remaining `backend/tests/engine` plus the DG-ARC-13 catalogue test | 724 passed |

Lane-reported selections before the merge: RUN 172 of 173 (MOD-JS-06 failing; its fix was in ENG), ENG 172 of 173 (RET-BR-03 failing; its fix was in RUN). The merge resolves both. "234 not approved" is the standing ADJUDICATION status present in every prior gate log.

The 58 all-active failures are plan-blocked keys outside the release selection (AKS-1 to AKS-7; ENC, DISC, BRK, LOSS, POB, POS, REC, ROY, VC families and MOD keys waiting for CTR-17, ENC-5 or ENB-9), plus ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION (post-rc with ENB-9, D-90) and VC-CHK-113-TC-POBVC-16 (D-90, outside the selection). The full failing id list is in `.run/l9merge/keys-all-failed.txt`.

## Release gate on main at 22d6c6e

`.run/l9gate/gates.sh` on main at 22d6c6e, tree clean (dirty 0) at start and end; START 11:32:18, DONE 12:26:28 (2026-09-18); logs `.run/l9gate/g/`, summary `.run/l9gate/summary.txt`.

| Gate | Result |
|---|---|
| openapi no drift | OK (no drift) |
| single Alembic head (test-pg heads selection) | OK, 3 passed; head 0054 |
| make ci | OK, 34 min (backend 2247 passed, 0 failed, 0 skipped; vitest 614 passed, 0 failed) |
| make test-pg | OK (290 passed, 0 failed) |
| make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07" | OK 10 passed (the gate selection; 2 deselected) |
| make parity K="not point_in_time_equivalence" | OK 121 selected, 121 passed (129 tests, 1 deselected) |
| make answer-keys, release selection (rg-selection.txt, 173 ids) | OK 173 selected, 173 passed, 0 failed, 0 withdrawn (the first fully green release selection in a gate) |
| make answer-keys, all active | rc=2: 234 selected, 174 passed, 58 failed, 2 withdrawn (174 of 232). The failing set is identical to the merge measurement (`.run/l9gate/keys-all-failed.txt` = `.run/l9merge/keys-all-failed.txt`, 58 ids): the standing plan-blocked set, not a regression |
| make e2e screens.spec.ts | OK 52 passed, 0 failed, 0 flaky |
| make e2e avenmoor-serial.spec.ts (SUP-RC-SMOKE, hard assertions only) | OK 1 passed |

## SPRINT-1.0rc §7.4 verification

- Fresh builds (`.run/l9/docker/build-fresh.sh`, `docker build --no-cache`, 2026-09-18 11:33 to 11:34, revision 22d6c6e, tree clean; logs and summary under `.run/l9/docker/fresh/`): api rc 0, image sha256:bae378c099bf9aa78ade0a644a18f364d4858858397cea3f9b65eb25a6ab6a85; worker rc 0, sha256:2ecf89a3f17892f78dba4561dcd900b6add78f6054ea0e4e6ec6297fb50aaa93; web rc 0, sha256:7dc559b2f48a0ae3ef847ca0b89c5d39b17a89116f68cb6c6145b8f8c4b8136c (tags `erev-<c>:l9-22d6c6e`). The three "CACHED" lines per build are the base-image `FROM` layers and the `.dockerignore` load; every `RUN` step (uv sync twice; `npm ci`, `npm run build`) executed. `docker compose -f deploy/compose.yaml config --quiet` rc 0, with the expected warnings for the unset `EREV_COMPOSE_*` secrets. The earlier cached builds at b634b1e (`.run/l9/docker/summary.txt`) are superseded.
- Multi-role browser QA pass 2 (SPRINT-1.0rc §7.4 rc verification, not full G12): `docs/qa/G12-multi-role-qa-2026-09-17.md` "Pass 2 (final revision)". Dev stack `make dev-up` on 22d6c6e (dev DB seeded at b634b1e; no new migration), one QA tab in the existing Chrome window, personas in sequence with sign-out and sign-in. QA-L9-7 (BLK-06, BLK-15) and QA-L9-5a are verified fixed on the merged tree for maya, priya and marcus in the browser; robert's cockpit payload is identical to maya's at the API level with the judgement request invisible to him (API-R-09). robert's SF-05 browser rendering was not captured (the chrome-devtools connection was lost after a hung header read) and is owed; it is recorded in the G12 record when taken.

## Rulings applied in Level 9 (summary; texts in `docs/01-DECISIONS.md`)

- D-90 (889eb63): ONB-CHK-121 out of the selection (174 to 173) with ENB-9; RND-CHK-003C golden erratum (per-obligation credits 33.34 / 33.33 / 33.33); RET-BR-03 runner contract attribution rule (dev-guide §9.5.6 rev 1.5); L8 lane questions; editorials. Record: L8-merge.md "D-90 rulings".
- D-90a (5f303ad; narrowed 590709d): QA-L9-7 (BLK-06 and BLK-15 only) and QA-L9-5a rc fixes; QA-L9-4 accepted rc behaviour; QA-L9-2, 5b, 3a and the activity verbs deferred; editorials; the four-persona pass is the §7.4 rc verification, not full G12. Record: L8-merge.md "D-90a rulings".
- D-90b (68301bd): S06-R-11 remaining service ρ over unit layers; `MOD_UNIT_HISTORY_AMBIGUOUS`. Record: L8-merge.md "D-90b ruling".
- D-90c (1f2f25c, 34e9964): condition (b) of `MOD_UNIT_HISTORY_AMBIGUOUS` withdrawn; same-date modifications are ordered boundaries, each a boundary of its own (ENGINE_SPEC S06-R-08 rev 1.5 and table 0.8-A; 04 rev 1.10). Raised by the independent review of D-90b (L9-ENG-Q-1).
- D-90d (198491c): L9-RUN-Q-1 to Q-8 (Q-3, Q-4, Q-8 rc engine fixes; Q-2 and Q-7 post-rc with fixes recorded; Q-1, Q-5, Q-6 notes; new L9-RUN-Q-9). Record: L8-merge.md "D-90d rulings".
- D-90e (this record's commit): L9-PLT-Q-1 to Q-7, L9-ENG-Q-3, the QA pass 2 verdicts and the commit trailers. Record: "D-90e ruling" below.
- IMP-106 for `MOD_UNIT_HISTORY_AMBIGUOUS` (1dda2d1; PRD IMP table; DG-ARC-13 pin 106) closes L9-ENG-Q-2.

## Lane questions closed or carried

- L9-PLT-Q-1 to Q-3 (catalogue keys, generic body shapes, period label source): ruled in D-90e, as built for the rc (the shapes are those D-90a left open; SCREENS §15.8 lists the `approvals.diff.member.*` keys as an editorial owed). L9-PLT-Q-4 closed by 9df7678 at the merge. L9-PLT-Q-5 (stored failed run shows no Reference line; expose `report_run.job_id` in API-S-ReportRun) post-rc (D-90e). L9-PLT-Q-6 (`create.problem` across `run=`) post-rc (D-90e). L9-PLT-Q-7: the rc wording is "the new job is bound to the run the retry created" (D-90e).
- L9-RUN-Q-1 to Q-8: ruled in D-90d; L9-RUN-Q-9 (group-level entries of a multi-member group stay unattributed) post-rc.
- L9-ENG-Q-1 answered by D-90c; L9-ENG-Q-2 closed by IMP-106; L9-ENG-Q-3 (Q-8 implemented with Q-3, as D-90d rules) accepted in D-90e: the lane implemented D-90d as ruled.

## Supervisor notes

- Commit trailers: ruled in D-90e (iv). 198491c (D-90d docs) and 08d72b7 (L9-PLT batch 1 evidence) carry the trailer "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" (the harness attribution rule now in force); the lane and merge commits, including those after 198491c (1dda2d1 to 22d6c6e), carry the repository's earlier trailer "Co-Authored-By: Claude Code <noreply@anthropic.com>"; the two `main` into lane merges (ef985d6, c860fe1) carry none. Both trailers are recorded; neither is a defect; history is not amended.
- Environment: `make parity` beside a database-backed pytest errors on `pg_advisory_lock` timeouts (both engine and runner lanes reran `make test-pg` once for that reason); macOS has no GNU `timeout`; a standalone `ruff check` from the repository root misreads first-party imports (`make lint` is authoritative).
- The chrome-devtools MCP session hung on a `get_network_request` of a 202 response during QA pass 2 and did not recover in the session; the fourth persona's cockpit was measured at the API level (G12 record) with the browser rendering owed.
- Editorial owed: dev-guide P-list row P14 names a property test file that does not exist (P14 is covered by DG-AK-54); SCREENS §15.8 catalogue keys `approvals.diff.member.*` (L9-PLT-Q-1).

## Post-rc and open items

- QA: QA-L9-2 (SF-12:all `entity` and `f.status`; D-88 L7-2-Q-13 (i)); QA-L9-5b (SCREENS §15.4 CONTRACT_ACTIVATION "New contract" view); QA-L9-3a (`X:contract-redirect` before the id pattern check); the audit action verb catalogue; the IMPORT_COMMIT diff renders current-only `Import` and `Status` rows as Removed (observation, pass 2); robert's SF-05 browser rendering (owed confirmation, D-90e).
- Lane questions carried: L8-C-Q-3 (checklist waiver link under row-level security); L8-R-Q-1, L8-R-Q-3 (post-rc accessibility polish); L9-RUN-Q-2 (group code guard, DG-AK-58), L9-RUN-Q-7 (`_concession_event` cross-member boundary), L9-RUN-Q-9 (group-level entries of multi-member groups); L9-PLT-Q-5 (`report_run.job_id` exposure), L9-PLT-Q-6 (`create.problem` binding).
- UI: the per-currency totals-row Currency cell on mixed-currency grids (a K-04 and CTR-20 prerequisite).
- Demo seed: K-04 stays a draft and CTR-20 unticked (D-88 L7-6-Q-1 gate clause; L8-merge.md Supervisor notes).
- Answer keys: ONB-CHK-121 post-rc with ENB-9 (D-90); VC-CHK-113-TC-POBVC-16 outside the selection (D-90).
- Engine gaps recorded in the ASC 606 review: L1-2-Q-9, L5-5-Q-5, L2-2-Q-4 (post-rc with complete dispositions pending D-91).
- ASC 606 review (Codex, `~/Plaid FinOps/eRev ASC 606 Review/`; verification records `.run/l9/asc606-verify*.json`, `asc606-followup-verify*.json`): C606-01 (stage 09/10 refund liability status against S10-R-07), C606-02 (stage 08 routing against S08-R-07, cumulative rounding per pool), C606-03 (stage 04 share-based consideration against PT-10 and S04-R-17; mixed ordinary/share rounding), C606-04 (S15-R-12 RPO rollforward basis), C606-05 (stage 04 `_judged_points` identity). Rulings pending in D-91; implementation in round B engine lanes with fail-first tests, corpus, parity, properties, ci and test-pg, then a second merge and release gate. None is fixed until merged and measured.
- The independent revenue-accountant G12 review, admin and auditor persona coverage and designer visual QA remain outstanding (`docs/00-GOAL.md` G12).

## D-90e ruling

Supervisor rulings on the Level 9 lane questions left open at the merge and on the QA pass 2 verdicts (`docs/01-DECISIONS.md` D-90e; lane records `docs/reviews/loop/sprint/L9-PLT.md` and `L9-ENG.md`; QA record `docs/qa/G12-multi-role-qa-2026-09-17.md` "Pass 2 (final revision)"; gate `.run/l9gate/`).

- L9-PLT-Q-1 to Q-3, as built for the rc: the `approvals.diff.member.*` catalogue keys with SCREENS copy as their values (Q-1); the generic body shapes D-90a left open (Q-2: record arrays one per line at the top level and "; " nested, records deeper than depth 2 as the no-value mark, API-S-Ref by code and `account_role` through `accountRole.*`, `*_id` hidden with `*_ids` while `*external_id` stays visible, IMPORT_COMMIT `diff_summary` amounts as the API string, status literals and ISO dates raw); period labels from `GET /periods?entity=` for an entity request and the first `STRUCTURE_LIMIT` page of `GET /periods` for a tenant-wide request, raw key otherwise (Q-3). SCREENS §15.8 gains the `approvals.diff.member.*` key list: editorial owed.
- L9-PLT-Q-4 closed by 9df7678 (runner lane) at the merge. L9-PLT-Q-5 (a stored failed run opened by `run=` shows no Reference line because API-S-ReportRun does not expose `report_run.job_id`): accepted for the rc as the SCR-ST-12 reading; exposing `report_run.job_id` on API-S-ReportRun so a stored failed run names its own job is post-rc, platform lane. L9-PLT-Q-6 (`create.problem` not bound to a run across `run=`): post-rc, the same (run, problem) binding in `useReportRun`. L9-PLT-Q-7: the rc wording is "the new job is bound to the run the retry created" (Retry issues `POST /report-runs`, which creates a new run; the pair binds to the run named in `X-Erev-Report-Run-Id`).
- L9-ENG-Q-3 accepted: D-90d rules Q-8 "rc, engine lane, with Q-3", and the RET-BR-03 delimiter test (`BR-03/ARMS`, a routed PRICE_PROTECTION element) cannot pass without the stage 08 head resolution and the stage 10 encoded lookup; the lane implemented D-90d as ruled (d06f3a8).
- QA pass 2 verdicts (D-90a vocabulary): QA-L9-7 (BLK-06 and BLK-15 reader-independent through API-S-PeriodCockpit `pending_requests`; ef4837c) and QA-L9-5a (generic SF-12:request field-diff formatting; b5c4f0d) are merged (ad06f60), gate-measured at 22d6c6e and verified in pass 2, maya, priya and marcus in the browser and robert at the API level (cockpit payload byte-identical to maya's; 0 visible pending requests; 404 on the judgement request detail), so they move to "fixed"; robert's SF-05 browser rendering is an owed confirmation. QA-L9-4 stays accepted rc behaviour (pass 2 observed the tenant-wide "Waiting for you" list for priya). The SF-08/SF-06 job-reference binding (14100e7) is verified on the success path in the browser and on the failed-run banner by six vitest cases (`frontend/src/routes/reports/__tests__/viewer.test.tsx`), which the demo world cannot reproduce (no failing report job).
- Commit trailers: 198491c and 08d72b7 carry "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" per the harness attribution rule now in force; the lane and merge commits, including those after 198491c, carry "Co-Authored-By: Claude Code <noreply@anthropic.com>"; the two `main` into lane merges carry none. Both are recorded, neither is a defect, history is not amended.
