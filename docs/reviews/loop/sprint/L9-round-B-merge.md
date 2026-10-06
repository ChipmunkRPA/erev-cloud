# Sprint L9 merge (round B): D-91 engine lanes, gates and remaining items

Supervisor record of the Level 9 round B merge on main (2026-09-18 PDT; the Codex evidence files carry the 2026-09-19 UTC date). Round B implements D-91 (`docs/01-DECISIONS.md`; the ASC 606 review dispositions C606-01 to C606-05, the contract and obligation gaps and the platform job reference) in three engine lanes on worktrees `~/dev/erev-wt/l6` (ENG-B1, `sprint/l6`), `~/dev/erev-wt/l5` (ENG-B2, `sprint/l5`) and `~/dev/erev-wt/l3` (ENG-B3, `sprint/l3`), all branched from main at cdd84a4 (D-91 and its first wording alignment). The independent Codex review (`~/Plaid FinOps/eRev ASC 606 Review/`, dialogue `CLAUDE-RESPONSE-20260918.md`, inbox `CLAUDE-INBOX.md`) retested every lane head against ruled expected figures before its merge and then reviewed the merged revision 0104e86 (bounded combined-code acceptance, recorded below); its findings on B3 are recorded below. The supervisor merged the lanes in the ruled order B1 → B2 → B3 and ran the combined release gate on the final merged revision with `.run/l9bgate/gates.sh` (logs `.run/l9bgate/g/`, summary `.run/l9bgate/summary.txt`). The release gate is a measurement of the merged revision; it is not an accounting sign-off, and the independent revenue-accountant G12 review of the D-91 judgments remains outstanding.

## Documents first (main, before any lane code)

| Commit | Change |
|---|---|
| 459f56e | D-91 appended after D-90e; specification amendments ENGINE_SPEC 1.6, ENGINE_SPEC_B 1.7, POLICIES 1.7, 04 1.11 (table 15.4-C `CPC_RELATED_SCOPE_INVALID`), PRD 1.4 (IMP-107), SCREENS_B 1.5, dev-guide 1.7, 03 1.4, 05 1.4; BUILD_SPEC items ENA-2b, END-4b, ENA-4b (plan.json, SPRINT-1.0rc deferred rows); DG-ARC-13 pin 106 → 107 |
| cdd84a4 | Codex 19:42 alignments: zero-net-cycle restoration conditioned on the cycle-start carried posting (70/140 → 70/140.03 → 70.01/140.02 example); S04-R-17 and the stage 10 finding description read E ≤ 0 with R(t) ≠ 0 raises `NON_FINITE_AMOUNT`, R(t) = 0 gives 0 |
| 0a8a2fb | Codex committed-D-91 review: 04 §16.3 mismatch only when both `obligation_key`s are non-null and differ; ENGINE_SPEC_B §9.2.7 iterates the kept-lines view with the billing mode resolved per kept line; S05-R-14 "present and non-empty" evidence; §0.5 ownership row `BalanceState.customer_consideration` (stage 10) |
| d3e26b9 | B1 follow-up: S10-R-07 detail wording (an amount mismatch keeps its detail; only an `obligation_key` mismatch adds member `obligation_key`); D-91 key subledger erratum (ALG-02 JET-06 reclass, 2100 dr 1,000.00 / 1200 dr 8,000.00); §9.2.7 `kept_lines` contract; learnings |
| c97ca94 | B3 follow-up: ENGINE_SPEC_B rev 1.8, S10-R-26 count-once numerator and concession subledger conservation as implemented at 4cb7070; §10.1 / §10.5 rows; S09-R-23a kept-lines wording; ENGINE_SPEC S04-R-17 and §0.5; POLICIES PT-10 and 04 T-CON-13 "each concession counted once"; 04 15.4-B detail wording; dev-guide §9.5.4 `allocation_criteria_evidence`; D-91 C606-03 errata; post-rc register entries |
| 80f31d0 | Codex c97ca94 review: the differing-calendar dated-journal effects are "an unchanged legacy posting-timing limitation whose accounting disposition remains open (not introduced by this correction …)"; the 4cb7070 gate note names the filtered parity selection |
| 1b52fc7 | D-91 run-8 note replaced with the measured `make ci` on 4cb7070 (backend 2,282, vitest 614, rc 0) |

## Merges, conflict resolutions and selection commits

| Commit | Change |
|---|---|
| 1f57778 | merge L9-ENG-B1 (`sprint/l6` at 45dbc6e, code head ecaac4a); no conflicts; 24 files, +2,852 / −177; corpus pins at the lane's 235 files/ids, 233 active, 228 engine-runner keys |
| fc9b1ed | release selection + `RET-CHK-029-S3-EX22-STATUS-UPDATE` — appended on a second line without a separator, which the gate's `tr` join would have read as the malformed id `VC-S3-EX24RET-CHK-029-S3-EX22-STATUS-UPDATE` |
| e6a0f28 | fix: `rg-selection.txt` rewritten as its one comma-separated line, 174 ids; measured from the file: 174 selected, 174 passed |
| 6bab66f | merge L9-ENG-B2 (`sprint/l5` at ababf9a, code head 741c7bd). Conflicts: `returns.py` `__all__` (both lanes' exports kept, sorted); the three corpus-pin tests (each lane had pinned +1 for its own key) set to the merged 236 files/ids, 234 active, 229 engine-runner keys, including the pins both lanes had changed identically and git had auto-merged one short |
| 4579788 | release selection + `VC-D91-01-TARGETED-THEN-UNTARGETED-CHANGE` (175 ids) |
| cd5543d | merge L9-ENG-B3 (`sprint/l3` at c91fd54, engine head 4cb7070). Conflicts: the three corpus-pin tests only, set to 243 files/ids, 241 active, 236 engine-runner keys (234 + B1 + B2 + seven B3 keys); every engine file (formulas.py, state.py, narratives.py, refund_liability.py, s06, s08, s10 `__init__`, `erev_engine/__init__.py`, `test_chk_alg06.py`, `support/recognition.py`) auto-merged |
| 0104e86 | release selection + the seven `CPC-CHK-120-*` keys (ADVANCE-BILLING, DELAYED-BILLING, ELEMENT-ONLY, FRACTIONAL-CAP, GRANT-AFTER-PERFORMANCE, MIXED-ORDINARY, OVER-TIME-QUARTERLY): 182 ids |

Selection membership follows D-91 "Lanes, sequence, gates": a key D-91 authors enters `rg-selection.txt` at the round B merge once it passes on merged main (MOD-JS-06 precedent); 173 → 174 → 175 → 182.

## Lane commits merged

ENG-B1 (`sprint/l6`; record `docs/reviews/loop/sprint/L9-ENG-B1.md`, commit 45dbc6e):

| Commit | Change |
|---|---|
| 8ea1acf | kernel `erev_engine/billing_identity.py` (`line_identity`, `is_cancellable`, `iter_billing_lines`; S10-R-07 at contract scope) and `state.billing_mode_at` (one POL-123 / POL-004 resolution); kernel test |
| fbadd77 | stage 10 classifies through the helper; `INVOICE_STATUS_UPDATE_MISMATCH` with detail member `obligation_key` when both keys are non-null and differ; the amount finding unchanged |
| 69587c3 | C606-01: E_b counts one line per identity from its S10-R-06 unconditional date, credit memos outside the base; `returns.units_billed.v1`, `returns.refundable_units.v1`, `rl.return.v2` (v1 kept); RETURN component cites the E_b node |
| f93bd69 | C606-05: `_judged_points` → `JudgedPoints` through the helper; status updates add no payment point; gap params `payment_points`, `status_updates_ignored`; 05g not implemented (post-rc by ruling) |
| 72ffa32 | s14 full-compute refund-liability-by-mode tests; new key `RET-CHK-029-S3-EX22-STATUS-UPDATE` (review status pending) |
| 8899862 | `ENGINE_VERSION` 0.1.0 → 0.2.0 (DG-ENG-10 changed result) |
| 57544fa | `billing_identity.kept_lines` view; stage 09 iterates it with the billing mode per kept line at its date (spec 0a8a2fb) |
| ecaac4a | lane corpus pins 235 / 233 / 228 |
| 45dbc6e | lane record |

ENG-B2 (`sprint/l5`; record `L9-ENG-B2.md`, commit ababf9a):

| Commit | Change |
|---|---|
| 4ffac26 | C606-02: `inception_weight` and `targeted_vc_quota_history` on the state; stage 05 seeds; routing `weight` / `check_version` / `_reapportion` / `_incremental` with `estimate.route.inception.v2` (v1 registered); `estimates.apply` S08-R-06 exact-transition negativity predicate and S08-R-04 target-set / evidence guards before the zero-delta return (shared `targeted.evidenced`: None or empty string is unevidenced) |
| 86c5216 | C606-04: `returns.reduction` / `reduction_from_state`; `rpo.py` published-basis `_rpo_at`, NET boundary lines, −Δρ between boundaries, strictly-post-termination-boundary suppression with history and the CANCELLATIONS removal retained, dated POL-200 quotas (`quota_as_of`, `quota_nodes`); S15-INV-08 |
| 21ce612 | tests: 23 stage 08 cases, stage 15 RPO and `test_s15_rpo_returns.py` (18 cases), K-02 S15-INV-08, `support/allocation_worlds.py` |
| db5d965 | new key `VC-D91-01-TARGETED-THEN-UNTARGETED-CHANGE` and the element-level key-schema member `allocation_criteria_evidence` (T-CON-12) |
| 3e830c2 | private `targeted._evidenced` alias kept for the frozen Codex probes |
| dad5a9f, 741c7bd | lane corpus pins 235 / 233 / 228 |
| ababf9a | lane record |

ENG-B3 (`sprint/l3`; record `L9-ENG-B3.md`, commit c91fd54):

| Commit | Change |
|---|---|
| 74953d8 | registers `tp.cpc_share_based.v1` and its narrative |
| f6b455e | C606-03: share-based consideration payable from posted related revenue (stages 04, 10, 12, 13, 14, root); stage 10 tail consumer `customer_consideration.py`; per-part / per-element rounding (P = round(O), E = Σ round(S_e), T = P + E); rc stage 13 fail-closed guard for the deposit gaps |
| 554c7aa | tests: stage 10 share-based worlds, JET-14 composition, stage 04 ordinary series, rc guard, formula ownership |
| a1653f3 | oracle `specs_b3.py` amendment (posted revenue basis, promise-or-element scope, per-element rounding) and seven new `CPC-CHK-120-*` keys; CHK-120 ×2 regenerated byte-identical |
| d329f61 | lane corpus pins 241 / 239 / 234 |
| b2029bb, 220e016 | Q-1 count once: producer-derived EMBEDDED / SEPARATE marker (superseded structure kept as the forward SEPARATE stamp); ruff F401 fix |
| 14479e4 | count once per selected revenue node (cutoff ruling), marker dropped |
| 3ba0ec9 | marker structure plus the selected-node date rule |
| cf5b2f9 | dated concession subledger (`ConcessionAddition`, `AllocatedState.concession_history`); the cutoff rule runs per portion; `concession_portion@<event>:<obligation>:<period>` nodes |
| b260878 | full-history conservation `check_history`; temporal lower bound (superseded) |
| 4cb7070 | no temporal comparison with the legacy aggregate; empty-quota exit only when exact and posted are both zero; test (vi) mixed 06/08 and the sub-cent controls |
| c91fd54 | lane record |

## Codex blocker sequence on B3 (each retested on an immutable lane commit)

| Lane commit | Codex finding | Ruling and correction |
|---|---|---|
| 554c7aa | double deduction: a stage 06 PRICE_CHANGE concession already nets stage 09 revenue (400,000 → 350,000) and the written S10-R-26 subtracted the 50,000 quota again (numerator 300,000; 15,000 instead of 17,500; net 335,000 instead of 332,500); all 714 trace nodes replayed | count each concession once (L9-ENG-B3-Q-1 ruled); fail-first full-compute regression |
| b2029bb / 220e016 | source review: embedding is a property of the selected revenue node, not of the producer (performing close 29 Aug, concession 30 Aug, contracting close 31 Aug: the selected node is pre-concession); public compute measured share 17,500 / 17,500 / 15,000 at 31 Aug / 30 Sep / 31 Oct on 554c7aa | selected-node cutoff rule: subtract the quotas dated after the selected node's cutoff and ≤ t; a quota embedded by a later performing close drops out |
| 14479e4 | two dated concessions (15 Aug 20,000; 30 Aug 30,000) gave 16,500 at August and September: the aggregate quota inherited only the latest event's date | per-portion dating from a dated source subledger; the aggregate refund component, its trace node, JET-05c / JET-04b netting and consumption unchanged (integration constraint) |
| cf5b2f9 | a July / August pair aborted with `ENGINE_INVARIANT_VIOLATED` at P07: the conservation guard compared dated history through t with the aggregate target dated at the latest event | conservation of the full history against the final quota; no strict per-cutoff equality |
| b260878 | a mixed S06-July / S08-August pair still aborted at P07 (the aggregate is dated by `_concession_event`'s preferred settled modification, 15 Jul); `check_history` accepted exact 1/300, posted 0, absent history | no temporal comparison with the legacy aggregate; the empty-quota exit requires exact and posted both zero; test (vi) and four history controls |
| 4cb7070 | accepted within scope: mixed pair 19,000 / 17,500 / 17,500 / 17,500 with actual event lineage (1,150 nodes replay, intents balance); four history controls; cross-month output byte-equal to b260878; prior 20 cases unchanged; seven non-incentive journals equal to the legacy control | retest revision; merged in cd5543d |

Codex's bounded acceptances of B1 (ecaac4a: 38 of 38 cases, 641 comparisons; 27 API / stage 09 checks) and B2 (db5d965: 18 of 18 case groups; cross-calendar J2, JPY and BHD supplement; 741c7bd inventory-only) are recorded in the dialogue file. None of these is an accounting sign-off.

## Codex bounded combined-code acceptance of the merged revision

Independent combined-code checks passed on 0104e86 (bounded; not release or G12 sign-off). `COMBINED-0104E86-REVIEW-20260919.md` (2026-09-19 03:01 UTC; inbox Message ID review-20260919-0301, with three linked reports on source integration, B1/B2 and B3) states that all assigned B1, B2 and B3 independent checks passed on the immutable merged main 0104e864fe6df6875a93ac90fd61f9978704b925; no topic (C606-01 to C606-05, the gaps) awaits a Codex retest of merged main:

| Scope | Codex result |
|---|---|
| Source preservation | 46 single-side files match the accepted lane owners; ten shared files match reconstructed three-way merges; the three conflict resolutions change only inventory pins; no unexpected source edit |
| B1 billing, refund and financing | 38 case outcomes (including the required rejections) and 641 comparisons pass; 27 API / stage 09 checks pass; values equal the accepted lane evidence |
| B2 allocation and RPO | 18 case groups plus three calendar / JPY / BHD supplement groups pass with unchanged named-case details |
| B3 consideration and incentives | 26 assigned cases pass: 21 public computations, one expected rejection, four controlled history guards; the established main17 set holds 4,657 passing comparisons and the zero-E supplement ten |
| Provenance and selection | 1,579 frozen file hashes and the protected imports verified; corpus 243 total / 241 active / 236 active engine keys; the release selection has 182 unique valid active ids |

Codex records the mixed S06-July / S08-August fixture at 19,000 (July) and 17,500 (August, September, October) with 1,150 nodes replayed, the `ENGINE_VERSION` 0.1.0 → 0.2.0 public-input-hash change and the mixed trace's adoption of `estimate.route.inception.v2` (`ssp_weights` for v1 `weights`; monetary value, inputs and journals unchanged) as disclosed differences. The acceptance is explicitly bounded: it closes the merge and regression review only and is neither a release sign-off nor the G12 review. Its open scope (mixed-producer dated net revenue, nonzero credit-memo FIFO consumption, swapped-amount history corruption, broader producer-order and currency combinations, the B1 / B2 coverage and policy deferrals, C606-05g, the standing 58 all-active failures, the filtered parity selection and the selected property tests) is carried into the open items below. The review was written while the release gate was running (openapi and heads had passed); the gate results follow.

## Measurements on the merged tree at each step

| Step | Result |
|---|---|
| after 1f57778 (B1) | `make lint` OK; architecture 72 passed; release selection 173/173 plus the new key 1/1 (174 of 174 with the explicit list; 174 selected / 174 passed from the file at e6a0f28) |
| after 6bab66f (B2) | `make lint` OK; architecture + answer-key unit tests 181 passed; release selection 174/174 plus the B2 key 1/1 (175 of 175); all active 236 selected, 176 passed, 58 failed, 2 withdrawn — the 58 failing ids identical to the 22d6c6e base set (diff empty). Qualification: the all-active report (build_sha 6bab66f) was produced while the working tree carried the B1 docs agent's uncommitted edits to four documents (PROGRESS.md, 01-DECISIONS.md, ENGINE_SPEC_B.md, ticks.md; no code, test or key), so it records `worktree_dirty=true`; it is test evidence, not a pristine-tree gate |
| after cd5543d (B3) | `make lint` OK; architecture + answer-key unit tests 181 passed; release selection 175/175 plus the seven CPC keys 7/7 (182 of 182) |

The 58 all-active failures are the standing plan-blocked set of the round A gate (`.run/l9gate/keys-all-failed.txt`); no key that passed on any lane or on main fails on the merged tree, and the only new passes are the nine keys D-91 authored.

## Combined release gate on the final merged revision

`.run/l9bgate/gates.sh` on main at 0104e86, tree clean (dirty 0) at start and end; START 2026-09-18 19:51:32, DONE 20:50:36 (PDT; 02:51:32 to 03:50:36 UTC on 2026-09-19); logs `.run/l9bgate/g/`, summary `.run/l9bgate/summary.txt`.

| Gate | Result |
|---|---|
| openapi no drift | OK (no drift) |
| single Alembic head (test-pg heads selection) | OK, 3 passed (`test_single_head`, `test_upgrade_downgrade_upgrade`, `test_lint_after_upgrade`) |
| make ci | OK, 38 min (backend, raw pytest classification in `ci.log`: 2,419 passed, 5 xfailed (expected failures; 0 xfailed measured at 790a93e after lane ENG-B4 — D-97 (32) annotation, the 0104e86 figures above are unchanged history), 371 deselected, 0 failed; vitest 614 passed, 0 failed). The five expected failures are the strict-xfail parametrisations of `tests/engine/kernel/test_billing_identity.py::test_four_consumers_agree` for the taxes and specialist consumers (`taxes-repeat_true`, `taxes-repeat_string_true`, `taxes-other_contract`, `specialist-repeat_true`, `specialist-repeat_string_true`), reason "post-rc 05h alignment (D-91)"; the "5 skipped" in `summary.txt` is the runner's generic count, not the pytest classification |
| make test-pg | OK (290 passed, 0 failed) |
| make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07" | OK 10 passed (the gate selection; 2 deselected) |
| make parity K="not point_in_time_equivalence" | OK 121 selected, 121 passed, 0 failed (raw 129 passed, 1 deselected) |
| make answer-keys, release selection (rg-selection.txt, 182 ids) | OK 182 selected, 182 passed, 0 failed, 0 withdrawn |
| make answer-keys, all active | rc=2 (a failed gate): 243 selected, 183 passed, 58 failed, 2 withdrawn (183 of 241); every one of the 243 keys has review status pending (243 not approved). The exact 58 failing ids equal the 22d6c6e round A gate (`.run/l9bgate/keys-all-failed.txt` = `.run/l9gate/keys-all-failed.txt`, diff empty) and the sets the lane records measured on their heads (B1 ecaac4a, B2 741c7bd, B3 4cb7070): the standing plan-blocked set, not a regression and not resolved; the passes grew from 174 to 183 by the nine D-91 keys |
| make e2e screens.spec.ts | OK 52 passed, 0 failed, 0 flaky |
| make e2e avenmoor-serial.spec.ts (SUP-RC-SMOKE, hard assertions only) | OK 1 passed |

## SPRINT-1.0rc §7.4 verification

- Fresh builds (`.run/l9b/docker/build-fresh.sh`, `docker build --no-cache`, 2026-09-18 19:52:21 to 19:53:01 PDT, revision 0104e864fe6df6875a93ac90fd61f9978704b925, tree clean (dirty 0); logs and summary under `.run/l9b/docker/fresh/`): api rc 0 (13 s), image sha256:051de8c1ee739cb09d3fc93be24ee83fb219e5a4cc81ac1ad8883c14f559d0e3; worker rc 0 (9 s), sha256:ca344e69d02f5473b7a4bcfde03f5c47ede4f1a3e9aca48d5b133908ae8f42ef; web rc 0 (18 s), sha256:35f6028be8a8d3de5744207fc990b1a3b7f4dc667741206a61e6ba7823706fb4 (tags `erev-<c>:l9b-0104e86`). The "CACHED" lines (api 3, worker 3, web 2) are the `docker/dockerfile:1` syntax image and the base-image `FROM` layers (python 3.12-slim and uv for api and worker; nginx-unprivileged for web, whose node base image was pulled); every `COPY` and `RUN` step (uv sync twice; `npm ci`, `npm run build`; the runtime user setup) executed. `docker compose -f deploy/compose.yaml config --quiet` rc 0, with the expected warnings for the unset `EREV_COMPOSE_*` secrets.
- Multi-role browser QA: the round A pass 2 record stands (`docs/qa/G12-multi-role-qa-2026-09-17.md`); round B changes the engine only (no screen, API shape or migration), so no new browser pass is claimed. robert's SF-05 browser rendering remains owed (the chrome-devtools connection of the supervisor session was lost during pass 2 and was not restored).

## Rulings applied in round B (texts in `docs/01-DECISIONS.md` D-91 and its erratum notes)

- C606-01 (stage 09 refund billing identity and E_b basis; stage 10 mismatch finding): B1 8ea1acf, fbadd77, 69587c3, 57544fa; S10-R-07 detail wording and the kept-lines contract d3e26b9; L9-ENG-B1 Q-2 and Q-3 ruled as implemented (ALG-02 governs the key's presentation).
- C606-02 (S08-R-07 carried quotas and one apportionment per untargeted change; S08-R-06 exact-transition negativity; S08-R-04 guards before the zero-delta return; dated POL-200 quotas): B2 4ffac26; zero-net-cycle restoration on the cycle-start carried posting (cdd84a4); L9-ENG-B2 Q-1 to Q-6 accepted as returned (Q-1 dev-guide §9.5.4 member c97ca94; Q-2 guard scope rc; Q-5 same-day boundary ρ_prior to the post-rc register).
- C606-03 (share-based consideration payable): B3 74953d8 through 4cb7070; S10-R-26 rev 1.8 (c97ca94) transcribes the count-once numerator, the selected-node cutoff, the per-portion citation and the subledger conservation as implemented; D-91 errata: 902,500.00 net for 952,500.00; case A 849,178.08 assumes invoices dated the 1st (period-end invoices give 947,808.21); lineage through portion nodes.
- C606-04 (S15-R-12 returns-adjusted basis, movement classification, S15-INV-08, strictly-post-boundary termination suppression): B2 86c5216; the termination fixture is classification evidence only.
- C606-05 (financing payment points through the S10-R-07 identity; 05g post-rc): B1 f93bd69.
- Gaps (stage 13 rc fail-closed guard for a 25-7 recognition without a bound JET-01b part): B3 f6b455e; ENA-2b, END-4b, ENA-4b post-rc (459f56e).
- Platform job reference: merged at ad06f60 (round A); D-90e dispositions referenced, not re-ruled.

## Residual limits (from the lane records and the Codex retests)

- No temporal check of the concession subledger at an intermediate close: a corruption that still conserves the final quota in exact and posted terms with real, correctly dated events and known producers is not detected; conservation is asserted per obligation over the whole history, per-(obligation, event) is implied.
- Legacy aggregate dating: `refund_liability._concession_event` dates the aggregate CONCESSION quota by a settled modification before a later TP_CHANGE (50,000 from P07 in the mixed-producer fixture); JET-05c timing follows it; preserved, not changed (post-rc register).
- Mixed-producer coverage is one ordering (stage 06 then stage 08); credit-memo consumption is zero in every concession fixture, so JET-05c FIFO neutrality with non-zero consumption is not certified; reversals of concession history and foreign-currency share-based parts are not exercised (the foreign part fails closed as before).
- Stage 13 intercompany addback timing at intermediate non-coincident closes (31 Jul basis 0 / net −20,000; 3 Oct 400,000 / 382,500, the performing mirror in US02 P09 ending 3 Oct) and the mixed-producer fixture's dated total net revenue of 382,500 at 31 Aug and 30 Sep, 332,500 at 31 Oct and −69,000 at 31 Jul (Codex-measured on 4cb7070 and again on 0104e86): an unchanged legacy posting-timing limitation whose accounting disposition remains open; not introduced by the correction; journal and refund timing unchanged (D-91 register, 80f31d0).
- Not implemented by ruling (post-rc): C606-05g (ENGINE-mode payment-point date basis; `SFC_REVIEW_REQUIRED` on zero eligible points), 05h (taxes and specialist through the helper; the five strict-xfail rows of the kernel test), the S10-R-07 API 422 clause and the `_fold`/s01 bound, the unapplied-cash and unbilled-receivable legs of E_b, the WARNING findings (late-supplied attribution, repeated cancellable identity, CONTRACT-wide evidence), L9-C606-02-Q4 targeted-path penny drift and Q5 stage 05 double rounding, evidence-at-v2 support, PERIOD_VC in the RPO basis, cross-calendar case K, RPT-06/RPT-07 basis, -RETURN / -CONCESSION CPC keys (the oracle engine models neither), same-day FIXED boundary ρ_prior fail-closed check.
- Parity `point_in_time_equivalence::shipped-db-equivalence` ("no parity reader yet") is deselected by every gate and fails identically on every revision; the properties gate runs the seven-property selection, not the full property set.
- Trace hashes change for every returns key, the S04-R-10a keys and 16 routing keys (params only; no checkpoint value changes); `ENGINE_VERSION` 0.2.0.
- The independent revenue-accountant G12 review of D-91's flagged supervisor calls (A1, A8, A14, A18, A20, A21 and the C606-03 window and scope rulings), the admin and auditor personas and designer visual QA remain outstanding; robert's SF-05 browser rendering is owed.

## Supervisor notes

- Merge hygiene: the corpus-pin tests conflict at every lane merge because each lane pins +n for its own keys; pins both lanes moved identically auto-merge one short and must be recomputed (236 → 243 at the B3 merge). `rg-selection.txt` is one comma-separated line (fc9b1ed → e6a0f28).
- Environment: two lanes migrating the shared Postgres concurrently exhaust `max_locks_per_transaction`; DB gates serialize through the gate slots (one PID per slot file); a lane's wait loop that pipes `pgrep -f` output through a pathname exclusion never excludes (fixed in the B3 chain with cwd resolution).
- Codex inbox: `CLAUDE-INBOX.md` Message IDs review-20260919-0003, 0200, 0225, 0236 and 0243 received through the session's file monitor and dispositioned in the dialogue file before the merges; 0255 (three lane-record wording corrections, applied to `L9-ENG-B3.md` in the close-out commit), 0301 (the combined-code review above) and 0358 (final-record alignment: the five ci xfails and the combined acceptance state, both reflected in this record) received after the merge; the monitor is re-armed every 30 minutes while the session is active and the inbox is read before each merge.
- Commit trailers: round B commits by the supervisor session carry "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" (D-90e (iv)); lane commits carry the trailer their sessions used; recorded, not amended.

## Post-rc register and open items

- D-91 "Post-rc register opened by this decision" (`docs/01-DECISIONS.md`, extended by c97ca94 and 80f31d0): L9-C606-02-Q4 and Q5; the legacy aggregate dating; the stage 13 intercompany mirror and the mixed-producer dated totals; -RETURN / -CONCESSION CPC keys; the POL-122 CONDITIONAL pin on CPC-CHK-120-DELAYED-BILLING; CONTRACT-wide evidence WARNING; same-day FIXED boundary ρ_prior; SEPARATE-producer forward requirement; ENA-2b, END-4b, ENA-4b.
- Round A items carried (`L9-merge.md` "Post-rc and open items"): QA-L9-2, 5b, 3a, activity verbs; L8-C-Q-3, L8-R-Q-1/Q-3; L9-RUN-Q-2/Q-7/Q-9; L9-PLT-Q-5/Q-6; the Currency cell on mixed-currency totals rows (K-04, CTR-20); ONB-CHK-121 with ENB-9; VC-CHK-113; the dev-guide P14 row and SCREENS §15.8 editorials.
- Answer keys: nine new keys authored under D-91 (RET-CHK-029-S3-EX22-STATUS-UPDATE, VC-D91-01-TARGETED-THEN-UNTARGETED-CHANGE, seven CPC-CHK-120 keys) carry review status pending until the G12 review, as do all 243 keys of the corpus; `docs/accounting/answer-keys/_coverage/answer-keys-topics.md` indexes them from the close-out commit.
- Open at close-out (none closed by the gate or by the Codex acceptance):
  - the mixed-producer legacy posting timing (dated total net revenue 382,500 / 382,500 / 332,500 / −69,000 at 31 Aug / 30 Sep / 31 Oct / 31 Jul) with its accounting disposition open;
  - nonzero credit-memo FIFO neutrality of JET-05c untested;
  - the legacy aggregate concession dating by `_concession_event`;
  - the seven CPC-CHK-120 keys and the two other new keys with review status pending;
  - the 58 standing all-active answer-key failures (plan-blocked; outside the release selection);
  - robert's SF-05 browser rendering (chrome-devtools connection lost in the supervisor session);
  - the independent revenue-accountant G12 review of D-91;
  - the post-rc register in D-91.
