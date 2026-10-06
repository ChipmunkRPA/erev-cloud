# ENG-C4: EDS-4 revenue from obligations satisfied in prior periods and disaggregation tags; EDS-7; DISC-CATCH-UP input clarification

Lane builder record for lane ENG-C4 on `sprint/l4` (worktree `~/dev/erev-wt/l4`, fast-forwarded to main 2a16cf6 after lane ENG-C2a's merge; clean tree). Binding: `.run/supervisor/d91/lane-dispatch-common.md` (incl. the 12:16 gate-slot amendment and GATE-BIND-1), the lane package `docs/reviews/loop/prod/lanes/ENG-C4.md`; BUILD_SPEC EDS-4 (`:7845-7868`) and EDS-7 (`:7918-7935`); ENGINE_SPEC_B §15.2.4 S15-R-13, S15-R-14, §15.2.5 S15-R-15, S15-R-16, S15-INV-03, §15.5, §15.7 EX-15-B, EX-15-C; ENGINE_SPEC §8.5 S08-R-14 to S08-R-16, CV-13, CV-63; POLICIES POL-204, POL-191, ALG-10 §2.11.3; D-87 L6-5-Q-27 (runner alias; the spec stays); AD-22 (G12 package, pending the fixture owner). No ENGINE_VERSION bump; no key or golden edit; docs first (no spec text changed by the lane — amendments are returned as questions).

## Facts verified on 2a16cf6

| Claim | Verified | Where |
|---|---|---|
| Stage 08 `decompose_prior_period` exists and has no caller; its docstring says "called by stage 15" | Yes | `s08_estimates_late_events/decompose.py:65,102`; `__init__.py:12-13`; `grep decompose_prior_period backend/erev_engine` finds the package only |
| Stage 15 has no prior-period or disaggregation consumer | Yes | `s15_disclosures/__init__.py:20` "arrive with later items (EDS-4 to EDS-7)"; package files `rollforward.py`, `rpo.py`, `waterfall.py` |
| The keys asserting the `revenue_prior_period` row fail on it alone | Yes | all-active at 2a16cf6 (`.run/eng-c4/base-keys-all.log`): DISC-CHK-101 FY2027-P02 5,000.00, JE-CHK-026 FY2027-P01 60,000.00 and FY2027-P12 0.00, VC-FS-02 FY2026-P06 25,000.00 — "actual <absent>" each |
| DISC-CATCH-UP-BY-CAUSE stops at `NEGATIVE_WEIGHT` | Yes | weights `[Fraction(-50000, 1)]`, total 7,500,000 minor: the runner's `_convert_terms` reads the terms-form line `quantity: "0"` (YAML:117) as ΔQ = 0 − 1 = −1 (`runners.py:643-706`) and `weights.nondistinct` (`weights.py:285`) gives (1 − 0.5) × 100,000 − 100,000 = −50,000 |
| Stage 14 writes no disaggregation dimensions; `ObligationState.dimensions` is always `{}` | Yes | `s14_posting/intents.py:132-160` (R3 identity dimensions only); `s05_allocation/original.py:124`, `s06_modifications/__init__.py:651` |
| Lane baseline (all active, 2a16cf6) | 193 passed, 48 failed, 2 withdrawn; 10 keys newly pass on main versus the L9 baseline (ENC-5 and the D-91 merges) | `.run/eng-c4/base-keys-all-failed.txt`, `base-keys-all-report.json` |
| DISC-S10-DISCLOSURES-REPORTS-EX21-… and DISC-S10-DISCLOSURES-RPO-EX42-… | `runner: platform` (fail closed until PRP-1; ENG-E1) | the two YAMLs :41, :44 |

## Design implemented

1. **Prior-period consumer** (`s15_disclosures/prior_period.py`, S15-R-13, S15-R-14). `build(ctx, allocated, recognition, posted, tb)`: for every performing entity of the obligations stage 09 measured (`recognition.obligation_measures`; a `LEASE_842` scope routed out under S09-R-13 has no revenue to decompose) and every period of that entity's calendar from the group's inception period through its horizon (CV-13; the period set stages 09 and 10 evaluate), calls `decompose_prior_period(ctx, view, period_key, tb, posted=posted)` with the allocated state viewed through that entity's obligations, so each obligation is decomposed on its own calendar; the S08-R-16 nodes `revenue_prior_period:<ob>:<period>` (`estimate.prior_period.v1`) therefore exist for every measured obligation and period, zero when nothing in the period changed the revenue of performance before its start (boundaries, S08-R-14; late carries from `posted`, S08-R-15). Per (contract, contracting entity, period) a sum node `revenue_prior_period_sum:<contract>@<entity>:<period>` (new formula `disc.prior_period_sum.v1`: Σ inputs, params `count`, `period`; narrative registered) — the S15-R-14 report grain (`PRIOR_PERIOD_POB_REVENUE`, (entity, contract, obligation) Σ amount). `DisclosureState.prior_period: PriorPeriod(targets, sums)`. `FORMULA_IDS` gains the formula.
2. **Disaggregation tags** (S15-R-15). `stages.state.disaggregation_tags(canonical, …)` (public): the template `disaggregation` mapping (T-REF-23), product family and revenue category (T-REF-20), contract region, channel and contract type (T-CON-01), the performing entity and `timing_of_transfer` ∈ {POINT_IN_TIME, OVER_TIME} from the satisfaction pattern (E-19); absent values omitted; a template attribute of a derived code wins. Stamped on `ObligationState.dimensions` by stage 05 (inception) and stage 06 (added lines); stage 14 writes them on a `REVENUE` line of an obligation beside the JET rule R3 identity dimensions and on no other role.
3. **Disaggregation rows and tie-out** (`s15_disclosures/disaggregation.py`, S15-R-16, S15-INV-03). `build(intents)` groups the period's `REVENUE` lines of the consumed posting intents — JET-02, JET-13 performing-side, JET-05c, JET-14 and JET-01b lines alike — per (entity, posting period, dimension, value), credit positive, a missing dimension under `-`; totals per (entity, period) = the revenue journal total; S15-INV-03 fails closed (`ENGINE_INVARIANT_VIOLATED`, rule S15-INV-03) when a dimension's rows do not sum to it. `DisclosureState.disaggregation: Disaggregation(rows, totals, dimensions)`. POL-191 `ELECT` is a report relief (F-RPS): the rows are still built.
4. **AD-22 (second half, pending the ruling).** No key edited. Measured both ways on a scratch copy (`.run/eng-c4/disc/…yaml`, the terms line `quantity: "1"`; `ad22_both_ways.py`, `ad22-both-ways.log`): as keyed — `NEGATIVE_WEIGHT`; under the input clarification (quantity unchanged, runner ΔQ 0, consideration_delta 20,000.00) — **every checkpoint passes**: cumulative 78,000.00, April 28,000.00, causes 5,000 + 10,000 + 13,000, prior-period 15,000.00 (the FY2026-P04 `revenue_prior_period` row now produced). The `NEGATIVE_WEIGHT` guard, stage 06 weights and the runner `_convert_terms` semantics are untouched.
5. **EX-15-C's second portion** (EAC totals change, −24,404.59) is not produced: an `EAC` version adds no segment, so `decompose._parts` measures no totals change (S08-R-14's "measure-only versions that change progress totals"; ENC-5 note "adds no segment (S08-R-02) … estimate_points measures C_after − C_before"). The consumer passes through whatever the producer emits; the producer gap is returned (Q-2). None of the four target keys involves an EAC change.

## Commits (`sprint/l4`, main..HEAD)

| Commit | Files | Change |
|---|---|---|
| b8f56ae | `stages/s15_disclosures/prior_period.py` (new), `stages/s15_disclosures/__init__.py`, `formulas.py`, `erev_api/explain/narratives.py`; tests `s15_disclosures/test_s15_prior_period_disaggregation.py` (new), `test_s15_rpo.py` | Design item 1 and its tests; the FASB Example 42 contract A fake (L3-2-Q-29) bypasses the consumer as it bypasses stage 09 |
| 74a8e93 | `test_s15_prior_period_disaggregation.py` | Late carry through stage 15; each performing entity's own calendar |
| 3de999f | `stages/state.py`, `stages/s05_allocation/original.py`, `stages/s06_modifications/__init__.py`, `stages/s14_posting/intents.py`, `stages/s15_disclosures/disaggregation.py` (new), `stages/s15_disclosures/__init__.py`; tests | Design items 2 and 3 and their tests |

## Fail-first evidence

| Test | On the base | On HEAD |
|---|---|---|
| `test_s15_prior_period_disaggregation.py` (prior-period part) on the 2a16cf6 engine overlay | collection error: the module imports `s15_disclosures.prior_period`, absent on the base (`fail-first-prior-period-2a16cf6.log`); the three keys fail on the absent row alone (`base-keys-all.log`) | 10 passed |
| The disaggregation tests (`-k "s15_r15 or s15_r16"`) on the 74a8e93 engine overlay (after item 1, before items 2–3) | 5 failed: `KeyError: 'performing_entity'` — no tag on any REVENUE line (`fail-first-disaggregation-74a8e93.log`) | 5 passed |
| `make answer-keys ID=DISC-CHK-101…,JE-CHK-026…,VC-FS-02…,DISC-CATCH-UP…` | 4 failed at 2a16cf6 (the three on the absent row; DISC-CATCH-UP on NEGATIVE_WEIGHT) | 3 passed, DISC-CATCH-UP still NEGATIVE_WEIGHT (`keys-four-after.log`) |

## Tests (15 in the new module)

- `test_eds4_answer_key_rows_exist` × 4 rows: the key's `revenue_prior_period` node exists with the key's value and `estimate.prior_period.v1`; replay exact.
- `test_eds4_disc_101_estimate_change_cause`: the February 2027 node cites the version 2 ESTIMATE_CHANGED event as its one boundary (rule S08-R-14; E 50,000 → 55,000 at the period start, f(s) = 1, part 5,000.00); December and January zero; the contract-entity sums; `DisclosureState.prior_period` targets and sums.
- `test_eds4_zero_nodes_through_each_horizon`: JE-CHK-026 year-2-close carries one node per period of the 2026-01 to 2028-12 calendar, zero except FY2027-P01 60,000.00 (CHK-100); year-1-close twelve zero nodes.
- `test_eds4_vc_fs_02_split_of_the_june_catch_up`: 25,000.00 = round(60,000 × 5/12) from the ESTIMATE_CHANGED boundary; every other period zero.
- `test_eds4_sum_formula_reevaluates_and_matches_the_obligation_nodes`: the sum node's inputs, params and re-evaluation.
- `test_eds4_late_carry_enters_the_posting_period`: deliveries in closed January recorded afterwards post in February: February nodes 1,000.00 with `carries 1`, `late_origin_1 FY2026-P01`, `late_target_1 100000`, `late_posted_1 0`; January zero; sum 2,000.00; with January open every node zero.
- `test_eds4_each_entity_decomposes_on_its_own_calendar`: POB-01 on the monthly entity (12 keys) and POB-02 performing on a calendar-quarter entity (4 keys), each from the inception period through its horizon.
- `test_s15_r15_revenue_lines_carry_the_obligation_tags` × 3 worlds: every REVENUE line carries `performing_entity` and the timing tag of its obligation; no other role does; S15-INV-03 per (entity, period) and dimension.
- `test_s15_r16_performing_side_lines_carry_tags_and_tie_out`: the JET-13 performing-side line on US02 carries `performing_entity US02`; totals tie per entity.
- `test_s15_r15_timing_split_and_template_mapping`: EX-15-B's April as a bundle — POINT_IN_TIME 8,200.00 (8,000.00 delivery + 200.00 targeted bonus), OVER_TIME 600.00 (7,200.00 monthly even), `segment: Enterprise` from the template mapping, product families, `revenue_category SUBSCRIPTION`, total 8,800.00; prior-period nodes zero; replay exact.

## Keys

| Key | Before (2a16cf6) | After (3de999f) |
|---|---|---|
| DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE | fails: `revenue_prior_period` FY2027-P02 absent | **passes** |
| JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP | fails: FY2027-P01 and FY2027-P12 rows absent | **passes** |
| VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE | fails: FY2026-P06 row absent (its only residual after ENG-C2a) | **passes** |
| DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION | `NEGATIVE_WEIGHT` | unchanged as keyed; passes every checkpoint under the AD-22 input clarification on a scratch copy — where it stops next: nowhere (see Design 4) |
| EDS-7's six named keys | — | DISC-CHK-006-…, DISC-CHK-101-…, DISC-GE-06-…, DISC-S10-DISCLOSURES-ROLLFORWARD-EX21, DISC-S10-DISCLOSURES-RPO-EX42 pass; DISC-CATCH-UP waits on AD-22 — EDS-7's "6 of 6" is blocked by AD-22 alone |

## Measured counts

| Gate | Result |
|---|---|
| `backend/tests/engine` + `tests/unit/answer_keys` + `unit/test_explain_service.py` + `unit/test_vc_direction_adapters.py` | 1,161 passed, 5 xfailed (`engine-suite-3.log`, at 3de999f) |
| `make answer-keys ID=<rg-selection.txt>` (182) | 182 passed, 0 failed (`keys-rg-3.log`) |
| `make answer-keys` all active (243 selected, 2 withdrawn) | 196 passed, 45 failed = the lane baseline (48) minus the three keys turned green; 0 new failures (`keys-all-3.log`, `keys-all-3-failed.txt`); against the L9 baseline (58): 13 fewer |
| Non-monetary output sweep (`digest_money.py`; 236 active engine keys, 687 checkpoint bundles; 2a16cf6 engine overlay against 3de999f) | full-output digest changed for 218 keys (the new trace nodes; REVENUE-line tags); **money-only digest (intents without dimensions, balances, versions, schedules) changed for 0 keys** (`digest-money-diff.json`) |
| `make lint` | OK (`lint-1.log`, `lint-2.log`) |
| mypy --strict (engine + API) | clean |
| `make properties`, `make test-pg`, `make ci`, `make parity K="not point_in_time_equivalence"` (one hardened chain, `gates-eng-c4.sh`, 12:16 protocol + worktree lock) | GATES_PENDING — chains 71152 / 89005 / 94694 / 66774 were stopped unclaimed on the supervisor's sequencing instructions; ONE chain runs on the final head after the CPU gates (see the D-97 section) |

## Return, do not decide (questions for the supervisor)

- **Q-1 — ruled: D-97 (1) input authoring defect (fixture corrected c45b2f7 / b8a2874; loader rule 4a42914, CHANGE-only at 2240d49). Original text:** (AD-22 ruling request, with the verified mechanism). The terms-form line `{quantity: "0", total_price: "20000.00"}` of MOD-DISC-01 is read by the runner as ΔQ = 0 − 1 = −1, so `weights.nondistinct` gives −50,000 and `NEGATIVE_WEIGHT`. Under the input clarification "quantity unchanged" (terms `quantity: "1"`, runner ΔQ 0, consideration_delta 20,000.00) the key passes every checkpoint at its recorded figures. Proposed treatment: the key notes carry the explicit unchanged quantity (an input clarification with a recorded trail, not an oracle change); `NEGATIVE_WEIGHT`, the stage 06 weights and `_convert_terms` stay. Alternative recorded: a real quantity change (then stage 06 weights and the fixture's values under a D-number).
- **Q-2 — ruled: D-97 (10), implemented 15e6eee / 7cbad2e. Original text:** (producer gap, S08-R-14 measure-only versions). `decompose._parts` measures only boundaries that give a new `FIXED` segment; an EAC version adds no segment (S08-R-02; ENC-5), so the totals-change portion of EX-15-C (−24,404.59) is not produced and BUILD_SPEC's `test_ex_15_c_prior_period_aggregation` figure 67,058.82 is not reachable through this consumer today (the modification portion 91,463.41 is). Stage 08/09 work outside this lane's scope; which lane?
- **Q-3 — ruled: D-97 (19), applied 2a3941f (wording for supervisor review at merge). Original text:** (spec text). ENGINE_SPEC_B §15.1 `DisclosureState` members `prior_period` and `disaggregation`; §15.5 the sum node `revenue_prior_period_sum:<contract>@<entity>:<period>` (`disc.prior_period_sum.v1`); S15-R-15's stamping point (stages 05/06 stamp `ObligationState.dimensions`, stage 14 writes them on REVENUE lines) and the `-` bucket for a missing dimension in S15-R-16.
- **Q-4 — ruled: D-97 (20), note applied 32fbcb4; ProductInput work is ENG-C4 phase 2. Original text:** (disaggregation attributes outside T-CON). The derived codes are `product_family`, `revenue_category`, `region`, `channel`, `contract_type`, `performing_entity`, `timing_of_transfer`, all from T-REF-20 / T-CON-01 / E-19; the template mapping's own codes are the configured attributes (T-REF-23, `disclosure.mandatory_disaggregation_attributes`). 04 :2251 also names a product-level `disaggregation` mapping, which `ProductInput` does not carry — should product attributes reach the tags?
- **Q-5 — confirmed: D-97 (21), stays with F-RPS / ENG-E1. Original text:** (RPT-05 builder inputs, L6-3-Q-31). The engine measure is exposed (`DisclosureState.prior_period`, the trace nodes and sums); the platform report `revenue_from_prior_period_obligations` and `worlds.k06_drossel` / `test_prior_period_obligation_revenue_k06` stay with F-RPS / ENG-E1.

## Deviations and notes

- The FASB Example 42 contract A harness (`test_s15_rpo.py`) runs the real stage 15 over a stage 09 fake because stage 09 fails closed on a right-to-invoice measure (L3-2-Q-29); the new consumer reads that measure through stage 08, so the fake bypasses it too (`mock.patch.object(prior_period, "build", …)`); in the engine such an obligation never reaches stage 15.
- The first cut decomposed every obligation and raised "the measure of progress is not built" on ALC-BR-06's routed-out LEASE_842 obligation; the consumer now follows the RPO consumers and decomposes the obligations stage 09 measured.
- Test worlds: the late-carry and two-calendar worlds replicate the closed-period world of `test_s08_late_events_compute.py` (test modules are not packages); the two-calendar world maps the JET-13 intercompany roles.
- Scratch under `.run/eng-c4/` (never `/tmp`); `report.json` snapshotted after every run (`*-report.json`).
- Gate chain (`gates-eng-c4.sh`): the 12:16 slot amendment (atomic `mkdir gate-slot-N.d` claim with an owner file of PID and start time, liveness by PID and start, UNKNOWN = held, at most two concurrent DB stages counted before every DB stage, release only when the owner file names its PID) plus the per-lane resource admission amendment: the chain takes the worktree lock `.run/gates/chain-lock.d` (owner: PID, `ps -o lstart=`, script) before entering the global-slot loop, refuses to start under an alive owner, and releases the global claim and the lock in one EXIT trap. A first chain (pid 71152) launched before the admission rule had claimed nothing and was stopped by its exact PID (verified dead) and relaunched as pid 89005 with the lock; on the supervisor's sequencing instruction (no global claim before 2026-09-19T22:30:00Z: C3's rerun, P6's test-pg and P1's gates first) 89005 — still unclaimed — was stopped the same way, its own stale lock removed, and the chain relaunched once as pid 94694 (21:27:12Z) with the lock taken first and the 22:30Z hold before the claim loop. Both slots were claimed by other lanes at launch; the chain waits CPU-idle.

## Residual limits

- DISC-CATCH-UP: input corrected under D-97 (1) (1 selected, 1 passed); EDS-7's six named keys pass on the corrected input — an input-corrected result, not an original-key pass or accountant approval.
- The EAC totals-change portion of S08-R-14 is produced (D-97 (10)); the 52 changed prior-period node values in 16 keys are measured, not adjudicated (Codex / supervisor).
- Pending after the chain: D-97 (24) (prepared patch and docs) and (20) phase 2 (`ProductInput` disaggregation).
- The platform disclosure keys (DISC-S10-DISCLOSURES-REPORTS-EX21-…, DISC-S10-DISCLOSURES-RPO-EX42-…) and the RPT-05 report belong to ENG-E1 / F-RPS.
- Gate evidence from the lane chain is progress/merge evidence, not release evidence (GATE-BIND-1).


## Codex review corrections (2026-09-19)

### C4-R1 — configured `revenue_category` lost between allocation and journal (be9c49e)

Codex report `PRODUCTION-C4-INDEPENDENT-f764ca0.md` (SHA-256 0a29801d…1309; independent checks 69/70; three keys pass across ten bundles; DISC-CATCH-UP's `NEGATIVE_WEIGHT` preserved until D-97 (1)). Cause confirmed: `s14_posting/intents._dimensions` copied the obligation's S15-R-15 tags onto the `REVENUE` line, then overwrote `revenue_category` with the ordinary obligation field, so a configured `TPL-OT.disaggregation["revenue_category"]` reached the native state (`disaggregation_tags` keeps the template value) but not the journal or the bucket. Fix: the R3 default fills `revenue_category` only when the `REVENUE` tags carry none; no other line, role or amount changes; no new collision rule (the documented precedence is enforced). Regression exactly as Codex's fixture: `_timing_world(configured_category="CONFIGURED-CATEGORY")`; asserts native state → the April 600.00 `REVENUE` credit's tag → bucket (`(US01, FY2026-P04, revenue_category, CONFIGURED-CATEGORY)` = 60,000 cents; `SUBSCRIPTION` row absent; April 880,000 cents), and money unchanged (every posting line without dimensions and every total equal the positive fixture; S15-INV-03 and replay on both). Fail-first `fail-first-c4-r1-base.log` (stage 14 byte-identical to 3de999f): the native-state assertion passes, the journal tag fails `'SUBSCRIPTION' == 'CONFIGURED-CATEGORY'`; after `fail-first-c4-r1-after.log`: 1 passed; stages 14 + 15: 115 passed.

### (1c) v3 — the loader guard of 4a42914 over-refused non-CHANGE actions (f33d55b docs, 2240d49 code)

Codex report `PRODUCTION-C4-AD22-LOADER-REVIEW-4a42914.md` (SHA-256 6f6318ff…384a). Raw 26/35 kept straight: 4 real regressions (an inferred ADD on a new key, `REMOVE_OBLIGATION`, `TERMINATION`, a `PRICE_CHANGE` line ended before the effective date — previously loaded, refused by 4a42914, mapped by the runner to ADD / REMOVE / REMOVE / REMOVE); 3 malformed-decimal admissions that are PRE-EXISTING (quantity / price `not-a-number`, `NaN`: admitted by the old and the new loader, failing in conversion — not widened or fixed in this series, recorded as known); 1 corrected original-path setup (the `/families/0` pointer of the first probe came from the evidence directory, not the bytes); 1 invalid harness expectation (a YAML `[1]` note is `["1"]` under DG-AK-31 — the `notes` handling is right). Correction: `support.answer_keys.terms.terms_line_action` is the conversion's own classification (ADD when the key is not in force at d; REMOVE for `REMOVE_OBLIGATION` / `TERMINATION` or `end_date` < d; CHANGE otherwise); `runners._convert_terms` reads its action from it (behaviour unchanged; `make answer-keys FAMILY=MOD` → the same nine baseline failures, `keys-mod-after-1c.log`); the loader folds the in-force keys as `_terms_conversions` does and fires only on a CHANGE line with quantity 0 and a non-zero finite `total_price` (NaN admitted as before). Controls, one per action (`GUARD_CONTROLS`): ADD on a new line, `REMOVE_OBLIGATION`, `TERMINATION`, ended `PRICE_CHANGE` line, zero-price CHANGE, malformed quantity, malformed price NaN — fail-first `fail-first-1c-scope-base.log` (loader of 4a42914): the four action controls and the NaN control REFUSED, zero-price and malformed quantity accepted; after `fail-first-1c-scope-after.log`: 17 passed incl. `test_corpus_cross_validates`. The original DISC-CATCH-UP bytes (SHA-256 89755696…4022) are the guard's negative control outside the corpus (`backend/tests/unit/answer_keys/negative/disc/`), refused at `/contracts/0/modifications/0/lines/0/quantity`; the corrected key is published as input-corrected (b8a2874: exact field diff `quantity "0" -> "1"`, original SHA-256, D-97 provenance). Dev-guide §9.5.4 and DG-AK-32 restated CHANGE-only; it is a key-format rule of the test loader, not API or import enforcement. Action-boundary coverage is the seven controls plus the CHANGE negative — not claimed beyond them.

## D-97 follow-up (supervisor rulings (2), (1), (1c), (10), (19), (20), (24); this lane)

Order as instructed: docs first, each commit inside `if make lint; then …`. Scratch under `.run/eng-c4/`; no `/tmp`.

| Item | Commit | What changed | Evidence |
|---|---|---|---|
| (2) DG-AK-59 `notes` | 1bc8608 | dev-guide §9.5.2 row DG-AK-59 (optional array of strings; documentary; the loader and the runner read nothing from it; numbered against main's DG-AK-58); dev-guide rev row 1.16 (against main's 1.15); `models.AnswerKey.notes: tuple[Text, ...] = ()` with `extra="forbid"` kept; `test_dg_ak_59_notes_are_documentary` | fail-first: `fail-first-dg-ak-59-base.log` — on the base model the test fails with "/notes: Extra inputs are not permitted"; after: `fail-first-dg-ak-59-after.log` — 8 passed |
| (1) DISC-CATCH-UP input | c45b2f7; b8a2874 (input-corrected publication: exact field diff, original SHA-256, provenance) | MOD-DISC-01 terms-form line `quantity: "1"` (total_price unchanged); a `notes` entry citing D-97 (1) and (1c). No expected value changed (cumulative 78,000.00; April 28,000.00; causes 5,000 + 10,000 + 13,000; revenue_prior_period 15,000.00; consideration_delta 20,000.00). `_convert_terms`, stage 06 weights, `NEGATIVE_WEIGHT` untouched | `make answer-keys ID=DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION` → 1 selected, 1 passed, 0 mismatches (conversion note "L1-BUILD CHANGE quantity_delta 0 consideration_delta 20000.00"); `d97-1-disc-catch-up-run.log`, snapshot `report-d97-1-disc-catch-up.json` |
| (1c) loader rule, docs | 29a3406 | dev-guide §9.5.4 `modifications` row and DG-AK-32: a terms-form line with `quantity` 0 and a non-zero `total_price` is refused at load ("a removal of every unit prices 0") | — |
| (1c) loader rule, code | 4a42914 | `_CrossValidator` finding at `/contracts/<i>/modifications/<j>/lines/<k>/quantity`; malformed decimals left to DG-AK-03 / DG-AK-51; CASES entry "terms-form line removing every unit priced" | both logs kept: `fail-first-1c-old-loader-accepts.log` (the uncorrected fixture, quantity "0" / 20,000.00, ACCEPTED by the loader at 9fe956d) and `fail-first-1c-new-loader-refuses.log` (REFUSED by the new loader at that pointer; the corrected fixture accepted with its note). Corpus scan: no other terms-form modification line with quantity 0. `test_loader_validation.py` 8 passed incl. `test_corpus_cross_validates` |
| (10) producer: measure-only `EAC` versions | 15e6eee (docs), 7cbad2e (code) | stage 08 `decompose._parts`: a measure-only `EAC` version applied in t to an input-measured obligation is a boundary of its own; every E_k of an input-measured obligation is measured through `_measure` with the `EAC` version in force after k (`eac_version_at` at k, inclusive — the S06-R-15 updated EAC of a class N amendment) standing alone for its element in a state view dated no later than the day before s (`_with_version`), at the ENG-06 position of k; a version the previous boundary already read moves nothing and adds no part; additive node param `version_<k>`; `measures_eac` exported from stage 09. ENGINE_SPEC S08-R-14 / S08-R-16 (rev 1.9) docs first | fail-first `fail-first-d97-10-base-worktree.log` (and the shadow's `fail-first-d97-10-base.log`, engine identical): the new stage 08 test gives 210,000.00 (one part: the amendment measured against EAC v1) and the new stage 15 aggregation test `'210000.00' != '67058.82'`; after `fail-first-d97-10-after-worktree.log`: stages 06, 08, 09, 14, 15 — 397 passed (shadow: 330 passed over 06/08/09/15). EX-15-C reached both ways: parts 91,463.41 and (24,404.59), 67,058.82; September 197,294.12 / 130,235.30; the J-14 cost adds nothing (229,852.94) |
| (19) spec sentences | 2a3941f | ENGINE_SPEC_B rev 1.19 (renumbered at the group-2 merge): §15.1 `DisclosureState.prior_period` (`targets`, `sums`) and `disaggregation` (`rows`, `totals`, `dimensions`); S15-R-15 stamping point (stages 05/06 stamp `ObligationState.dimensions`; stage 14 writes them on `REVENUE` lines only); S15-R-16 the `-` bucket and S15-INV-03 per dimension; §15.5 row `revenue_prior_period_sum:<contract>@<entity>:<period>` (`disc.prior_period_sum.v1`) | supervisor reviews the wording at merge |
| (20) product attributes | 32fbcb4 | 04 T-REF-20 `product.disaggregation`: rev-pending note (04 rev 1.28, renumbered at the group-2 merge) — the attributes reach the S15-R-15 tags once `ProductInput` carries them (lane ENG-C4 phase 2 after C4-R1 and EDS-4; acceptance controls for product / template precedence and API-to-engine admission) | note only |
| (24) unsupported refund target (C2a follow-up) | after the chain (prepared: `.run/eng-c4/patches/d97-24.patch`, `apply_docs_d97.py 24`) | 04 table 15.4-B `REFUND_TARGET_TYPE_UNSUPPORTED` (ERROR; X `ENGINE`, P) and T-CON-13 "explicit `null` = absent" (rev 1.17); `_version_errors` refuses an explicit `refund_liability_target` when the element's `vc_element_type` is outside `REFUND_SETTLED_TYPES` (create, PATCH and submit; 422 `validation-failed`, field `parameters.refund_liability_target`); the engine's `refuse_unsupported_target` unchanged; test `test_refund_target_type_unsupported_refused` (create refused, explicit null stored and accepted, PATCH refused, a stored draft refused at submit and left DRAFT, the REBATE v2 target accepted) | its API test needs the test database: runs when DB capacity allows (two-DB-stage rule), after the chain |

### (10) corpus effect (shadow engine against the worktree engine at 4a42914; `digest-d97-10-*.json`, `pp-nodes-*.json`)

- 236 active engine keys, 687 checkpoint bundles: full-output digest changed for 35 bundles in 16 keys; money-only digest (postings with dimensions blanked, balances, versions, schedules) changed for 0 — the change is confined to the `revenue_prior_period` / `revenue_prior_period_sum` trace nodes.
- 52 node values changed (26 obligation nodes and their 26 sums; `pp-nodes-diff.json`); every changed obligation node names a `version_<k>` param (26 of 26; `pp-params-new-all.json`), so the `EAC` path drove every change and the ENG-06 position alone changed nothing.
- Examples: MOD-CHK-027-S6-EX8 C-EX8/L1-BUILD FY2027-P02 210,000.00 → 91,463.41 (the EX8 / EX-15-C figure); MOD-CHK-042-INCEPTION C-MIXED/L2-B FY2026-P07 10,000.00 → 2,000.00 (D18 8,600.00 → 880.00); LOSS-S7-LOSS-OWN and JE-CHK-132 C-…/L1-BUILD FY2027-P12 0.00 → (90,909.09); REC-FS-07 FS-07/L1-IMPL FY2026-P02 0.00 → (2,307.69); REC-GE-01, VC-GE-04, MOD-GE-02, MOD-CHK-115, REC-BR-08, LOSS-GE-03, VC-GE-05, MOD-GE-08, MOD-S6-COMBINED, VC-CHK-100 likewise. None of these keys asserts `revenue_prior_period`; the four EDS-4 keys that do are unchanged and pass. Whether each new figure is the intended disclosure value is Codex's / the supervisor's to confirm — the lane reports the measured change.
- Shadow full engine + unit suite after the change: 1,033 passed, 5 xfailed, 1 failed = `tests/unit/deploy/test_compose.py::test_services` (FileNotFoundError — the shadow copy has no `deploy/` directory; not the change; the worktree gates decide) (`shadow-engine-suite.log`).

### Development method while the chain ran

The gate chain measures the working tree for its whole run, so items (10), (19), (20) and (24) were developed on a shadow copy of `backend/` under `.run/eng-c4/shadow/` (PYTHONPATH precedence over the editable install; `docs` symlinked for the loader), linted with the repo config (`ruff --config backend/pyproject.toml`), and saved as patches (`patches/d97-10.patch`, `patches/d97-24.patch`, `patches/apply_docs_d97.py`) applied to the worktree after the chain's END.

### C4-EAC-R1 — stale inception view after a new-basis PROSPECTIVE boundary (f6da337 docs, ffea15c code)

Codex (evidence `2026-09-19-c4-eac-prospective-32fbcb4.json`, SHA-256 ed983df5…3694): the independent K-03 fixture with ONLY the amendment treatment changed to PROSPECTIVE gave prior-period revenue (105,882.35) on 7cbad2e where 0 is expected (CV-63); September total 143,023.26 and the replay were unchanged — a disclosure attribution regression. Cause confirmed: `_parts` appended the zero 25-13(a) part and continued without touching `view`, so the later measure-only branch remeasured the stale inception view (1,000,000 at costs 420,000) against 820,000 and 850,000 ((87,804.88) + (18,077.47)). Fix: the new-basis PROSPECTIVE branch resets the measured view — the basis in force starts at the boundary, so nothing of it is measured at s; later measure-only versions of t add nothing; a later segment boundary sets the view again; a measure-only version before the boundary keeps its part; a PROSPECTIVE boundary in force at s is unchanged. ENGINE_SPEC S08-R-14 (rev 1.9 row) states it (docs first). Regressions exactly as Codex's variant, unit and bundle: prior-period 0.00 with one CV-63 part; September 143,023.26. Fail-first `fail-first-c4-eac-r1-base.log` (`-10588235 == 0`; `'-105882.35' == '0.00'`); after `fail-first-c4-eac-r1-after.log` (2 passed; stages 06/08/09/14/15: 399 passed). Chain 70993 (head 1c39b4e; properties OK 12 passed, test-pg OK 290 passed, ci interrupted) was stopped by exact PID on the supervisor's instruction — its head is not the merge candidate; its trap released slot 1 and the lock, and its orphaned `make ci` / gate_report / pytest children in l4 were stopped by exact PIDs (`gates-summary-70993-stopped.txt`).

### Final CPU gates and corpus effect on ffea15c

| Gate | Result |
|---|---|
| `backend/tests/engine` + `tests/unit` | 1,482 passed, 5 xfailed, 1 failed = `test_repository_layout.py::test_dg_lay_01_top_level_directories` on an ignored top-level `.ruff_cache/` created by the lane's direct ruff pre-checks from the worktree root (not tracked; `make lint` writes to `backend/.ruff_cache`); removed and the layout module rerun: 6 passed (`engine-unit-suite-final-2.log`; the same cache tripped the first run on 32fbcb4, `engine-unit-suite-final.log`) |
| `make answer-keys` (all active) | 243 selected; 197 passed, 44 failed, 2 withdrawn — the lane baseline of 45 failures minus DISC-CATCH-UP (passing on the corrected input); no new failure (`keys-all-final-2.log`, `report-keys-all-final-2.json`; identical result on 32fbcb4, `keys-all-final.log`) |
| Corpus digest sweep (`digest_money.py`, 687 checkpoint bundles; ffea15c against the 4a42914 engine) | full-output digest changed for 35 bundles in 16 keys; money-only digest (postings with dimensions blanked, balances, versions, schedules) changed for 0 (`digest-d97-10-final.json`, `digest-d97-10-final-diff.json`) |
| Prior-period node values (`pp_nodes.py`) — ffea15c against 4a42914, and against the pre-fix 7cbad2e producer | 52 `revenue_prior_period` / `_sum` node values changed against 4a42914 (the same 26 obligation nodes and 26 sums as the pre-fix sweep, every obligation node naming a `version_<k>`); 0 node values differ from the pre-fix 7cbad2e producer — no corpus key has a new-basis PROSPECTIVE boundary followed by a measure-only EAC version in one period (`pp-nodes-final.json`, `pp-nodes-final-diff.json`) |
| `make lint` | OK on every commit (`lint-*.log`) |
| `make properties`, `make test-pg`, `make ci`, `make parity K="not point_in_time_equivalence"` | ONE chain on the final head (record commit on ffea15c): PID and results reported on END; the earlier chains 71152 / 89005 / 94694 / 66774 / 70993 were stopped unclaimed or mid-ci on the supervisor's sequencing instructions (their partial results are progress evidence only) |

### Codex retests recorded (hashes verified)

- `PRODUCTION-C4-CATEGORY-RETEST-be9c49e.md` (6a0975b5…30e65): C4-R1 closed — the original timing control and the exact category counterexample 20/20 (April 600 credit and bucket keep CONFIGURED-CATEGORY, no SUBSCRIPTION bucket, total 8,800 and all monetary lines / trace bindings stable; raw 22/23 retains one invalid probe assumption, not a defect).
- `PRODUCTION-C4-EAC-LOADER-RETEST-32fbcb4.md` (fb4040f8…d0df): C4-EAC-R1 confirmed on 7cbad2e's producer — the false (105,882.35) in the native obligation target, the native contract sum and the public prior-period trace, SourceRefs EV5 = 0, EV6 = (87,804.88), EV8 = (18,077.47); September 143,023.26 and every non-trace public output unchanged (fixed at ffea15c: EV5 = 0 only). Six intended EAC cases 72/73 raw; the seventh (exploratory COST_RECOVERY with an amendment) refuses at S06-R-17 with `ENGINE_INVARIANT_VIOLATED` on both engines — pre-existing, not this lane's regression, recorded. Loader domain raw 11/15: the four action regressions close; the quantity-0 bytes refuse with the CHANGE-only diagnosis; the four malformed / non-finite numeric admissions match the pre-guard baseline (NaN price now left to conversion explicitly); the corrected quantity-1 key matches a fresh frozen earlier-engine execution.
- `PRODUCTION-C4-EAC-R1-RETEST-ffea15c.md` (355e2d47…4c13): C4-EAC-R1 closed — the unchanged counterexample 3/3 (prior-period 0, total 143,023.26, EV5 zero SourceRef only; the full OutputBundle restored to be9c49e's); six ordinary EAC cases preserved (raw 72/73, the COST_RECOVERY refusal known); an added earlier-period prospective positive 12/12 (September 10 reset, September 25 cost 82,000, EAC v3 moved to October 10 → October prior-period / total (10,726.74) bound to EV8 / v3 — the fix does not skip EAC changes after a historical prospective basis); integrity 42/42.

## D-98 candidates 85 and 91 / 91a (2026-09-20; this lane)

### Heads on sprint/l4

| Head | Content |
|---|---|
| 4be487cb | D-98 85 docs first: SCREENS_B §5.6.1 RPT-05 `revenue_from_prior_period_obligations` dataset identity (code columns `entity_code`, `contract_external_id`, `obligation_key`; one row per obligation; `cause` an attribute) with ENGINE_SPEC_B §15.2.7 and 04 T-CLS-05 companions; builder deferred to the PRIOR_PERIOD_POB_REVENUE slice |
| b42d4683 | Merge of main a7347356: the D-98 85 rows renumbered to the merge-prep numbers SCREENS_B 1.12, 04 1.40, ENGINE_SPEC_B 1.25 |
| ea27bf9b, 5fc9802a | D-98 91 / 91a docs first (ENGINE_SPEC_B 1.26: S15-R-08 gross basis, S15-INV-08 closing = gross − exempt, §15.5 additive params, §15.1 output row; 04 1.43 (provisional 1.41 at the time): T-CON-08 `rpo_amount` note) |
| 36b1241e | D-98 91 / 91a code: stage 15 `rpo.build` group node sums the obligation nodes (gross; additive params `excluded`, `exempt_nodes` when an expedient applies); `Rpo.excluded` / `after_exemptions`; `DisclosureState.rpo_after_exemptions` (the named net); tests. Codex's retest target |
| 69935f6e | Merge of main 065e7f65 (wave 2): `test_platform_runner.py` resolved to the no-mismatch shape; 04 row 1.41 → 1.43; ENGINE_SPEC_B 1.26 confirmed |

### D-98 91 / 91a — the S09-R-18 / S15-R-08 field-basis conflict

Codex packet 0904 identified the conflict: S09-R-18 states EX42 P 12,000 − R 3,000 → RPO 9,000 while S15-R-08 summed
`contract_version.rpo_amount` after the S15-R-09 exemptions, so POL-198 (basis ALL) removed the whole 9,000 at the group
aggregate (base trace: obligation `rpo_amount:C-EX42-A/A1-CLEANING:-` 9000.00, `rpo_excluded:…/POL-198:-` 9000.00, group
`rpo_amount:CG-C-EX42-A:-` 0.00 with signs `+|-`; `ex42-trace-base.log`). Ruling 91a (supervisor; POL-198 per the 09:13Z
addendum): `rpo_amount` carries the GROSS contractual remaining amount; the exemption is carried separately; the bands and
the report's included / excluded split stay net; gross = net + exempt stated in the trace. After 36b1241e the group node is
9000.00 with inputs = (the obligation node,), signs `+`, params `excluded` 900000 / `exempt_nodes` the POL-198 node; the
version column 900000 minor; `rpo_after_exemptions` 0; row total / excluded / bands unchanged (`ex42-trace-after.log`).
Specification consistency only — flagged for G12; no key edited (C-EX42-A 9,000.00, C-EX42-B 7,200.00 and the twelve RPO
report cells stand). The D-91 sentence in `docs/01-DECISIONS.md` (~line 699, "closes at `contract_version.rpo_amount`") is
supervisor-owned; an erratum pointer is recorded under 91a.

Fail-first (`.run/eng-c4/fail-first-d98-91-*.log`): the F-RPS platform-runner test as on main a7347356 fails on the base
engine with `'compared' == 'error'` (post-ENC-6 the engine no longer stops); the rewritten no-mismatch test fails on the base
engine with exactly one Mismatch (C-EX42-A `rpo_amount` expected 9000.00, actual 0.00); the gross / net stage-15 assertions
fail on the base engine (`rpo_after_exemptions` absent); after the change 43 passed / 1 failed (the `dated_rpo` helper still
on the gross `.total`), then 26 passed with the helper on `.after_exemptions` (S15-INV-08 sweep: keys 20, returnable cells
379 with 0 mismatches, other cells 755 with no residual, same-cutoff ties 24/24).

Consumer impact map (every reader of `rpo_amount`; non-exempt contracts gross = net): erev_engine `_version_columns`
(gross; trace alias = the gross group node); erev_api `contracts/computation.py` fallback (Σ scheduled + awaiting, already
gross), `contracts/queries.py` KPI / version API `rpo` and `contracts/events.py` before / after summaries (gross for exempt
contracts; no code change); the answer-key as-of overlay (`runners.py`, obligation nodes with `included == "true"`, gross —
now consistent); the RPO report builder (`builders/rpo.py`, rebuilt from obligation versions; exempt contracts in section 2
`excluded_amount`; unchanged); the RPO dataset / lock snapshots (engine rows unchanged); `disc.rpo_band.v1` and
`disc.rpo_exemption.v1` nodes unchanged; answer keys — only the two EX42 keys carry POL-198, VC-D91-01 (POL-200) omits 0.

### Captured statuses

| Head | typecheck | lint | engine + architecture + unit | keys |
|---|---|---|---|---|
| 36b1241e | OK (602 files) | OK | 2,565 passed, 1 xfailed (Q-11, known); rc 0 | EX42 key alone: `not_run`, 0 mismatches, "blocks compared clean: december-2026-rpo contracts; DB-bound blocks: december-2026-rpo reports rpo" (the gate exits non-zero for a not-run key — the in-memory boundary, XR-12); DISC-S10-DISCLOSURES-RPO-EX42 + VC-D91-01 2/2; 220-id selection 220/220 rc 0 |
| 69935f6e | OK (604 files) | OK | 2,577 passed, 1 xfailed; rc 0 | EX42 key alone `not_run`, 0 mismatches (same message); the two keys 2/2; 220-id selection 220/220 rc 0 (`keys-merge-69935f6e.log`, `report-selection-220-69935f6e.json`); focused 46 passed incl. the governed-docs and layout preflight |

Not run this slice: `make properties` (p07 ran directly and passed), `make parity`, `make test-pg`, `make ci` (no chain; no DB
stage). Codex's one-key in-memory retest of 36b1241e (`PRODUCTION-EX42-FIX-NATIVE-RETEST-36b1241e.md`, reported by the
supervisor: contracts COMPARED with zero mismatches, nine supplied fields matching, twelve report cells NOT_RUN, 24 cached
differences all the contract A corrections, 254 YAML keys unchanged) is recorded as reported; its hash was not verified by
this lane.

### Merge of main 065e7f65 (69935f6e)

One content conflict, `backend/tests/unit/answer_keys/test_platform_runner.py`: F-RPS's bounded diagnostic
`test_ex42_reaches_comparison_after_enc_6_and_fails_on_the_rpo_amount` (c60529ab; asserted the observed mismatch) replaced
by `test_ex42_compares_clean_and_its_rpo_report_is_db_bound` — every block `!= ERROR`, no `ENGINE_INVARIANT_VIOLATED`
reason, contracts `COMPARED` with `reason is None` and `mismatches == ()`, `result.mismatches == ()`, "reports rpo" `NOT_RUN`,
`platform_outcome` `NOT_RUN` starting with the not-provisioned text, `assert_platform_checkpoints` raises nothing; F-RPS's
evidence pointer (`.run/f-rps-e1/fail-first-ex42-enc6.log`) and history kept in the docstring; no other hunk of the file
changed. Governed docs merged without conflict; touched: `docs/04-DATA_MODEL.md` (row 1.41 → 1.43: header entry, log row,
T-CON-08 in-text marker; "provisional" phrases replaced) and `docs/accounting/ENGINE_SPEC_B.md` (1.26 "confirmed at the
merge of main 065e7f65"). SCREENS_B untouched by the merge (1.12 already applied at b42d4683).

### PRIOR_PERIOD_POB_REVENUE builder (D-98 85 phase 2; 2026-09-20)

| Head | Content |
|---|---|
| 4056c168 | main (the 91 / 91a merge) fast-forwarded into sprint/l4 |
| c9a19420 | docs first: SCREENS_B 1.16 — RPT-05 reading rule (the traces named by the range's `REVENUE` subledger lines recorded by `known_at`; one latest recorded version per combination group and period; every `revenue_prior_period` node of that trace read), the identity `PRIOR_PERIOD_ROWS_EQ_SUM_NODES` (Σ obligation nodes = the `revenue_prior_period_sum` node of the same trace, S15-R-13) as the control total `prior_period_sum_total` with refusal by name, all-zero rows omitted, `cause` lists the non-zero causes, `row_key` components CV-21 encoded (D-98 104) with a same-contract collision witness, `period_lock_id` refused by name until F-CLO's locked-dataset branch (D-98 96) |
| 553049d3 | docs first: 04 1.51 — T-CLS-05 `control_totals` of the dataset gains `prior_period_sum_total` (note only) |
| c646cea9 | code: `erev_api/domain/reports/builders/revenue_from_prior_period_obligations.py` registered in `framework.BUILDERS`; CPU tests `tests/unit/reports/test_revenue_from_prior_period_obligations.py` (14); DB path test `tests/domain/reports/test_prior_period_report.py` (slow, NOT RUN) |

Shape (SCREENS_B RPT-05 rev 1.12 / 1.16; ENGINE_SPEC_B §15.2.7 rev 1.25; 04 T-CLS-05 rev 1.40 / 1.51): one row per
(performing entity, contract, obligation) with the code columns `entity_code`, `contract_external_id`, `obligation_key` (the
KeySpec key F-CLO's 4d8e875b names), attributes `product_code`, `satisfied_period_key`, `cause`, `currency`, measures
`from_price_changes`, `from_estimate_changes`, `from_modifications`, `from_late_events`, `from_other`, `revenue` (typed
API-S-Money through `tie_outs.money`; C6-RPT-R1); `row_key` `obligation:<entity>:<contract>:<key>` with CV-21-encoded
components; control totals `row_count`, `revenue_total`, `prior_period_sum_total` per currency. Cause attribution from each
node's `contract_event` source references and `rule_<k>` / `version_<k>` params: `ESTIMATE_CHANGED` reallocating → price
change, measure-only `EAC` version → estimate change; `CONTRACT_AMENDED` / `LINE_ATTRIBUTES_CHANGED` / `REGROUPED` →
modification; carries (`late_target_<k>` − `late_posted_<k>`) → late event; `S09-R-06` / `CONTRACT_TERMINATED`, material-right
exercises and CV-63 zero parts → other. Refusals by name: `RPT05_KEY_COLUMN_MISSING`, `RPT05_KEY_COLUMN_UNRESOLVED`,
`RPT05_NODE_SPLIT_MISMATCH`, `RPT05_SUM_NODE_MISMATCH`, `RPT05_EVENT_UNRESOLVED`, `RPT05_TRACE_MISSING`,
`RPT05_LOCK_SOURCE_NOT_SUPPORTED` (422 `validation-failed`, rule id = the code). No new tie-out code: 04 table 10-T holds 13
governed codes seeded by migration 0048, so the identity is published as a control total and enforced by refusal instead.
As-of reads (D-98 96): lines `recorded_at ≤ known_at`, versions `known_at ≤ tie_outs.version_cutoff`.

Fail-first (`.run/eng-c4/`): `fail-first-pp-builder-base.log` — base c9a19420 (docs first committed, no code): the builder
module is absent and `revenue_from_prior_period_obligations` is not in `framework.BUILDERS` (AssertionError recorded).
`fail-first-pp-builder-after.log` — first run with the builder and its tests: 30 passed / 1 failed in
`test_rpt_05_grid_matches_the_builder_columns`; wrong was the test's SCREENS_B grid parse, not the builder: the RPT-32/36
regex requires the field cell to be exactly "`<field>`", while the RPT-05 "Satisfied in" row renders
"`satisfied_period_key` → label", so the parsed grid lacked that row (index 4 read "Cause" against the builder's
"Satisfied in"); the regex gained an optional " → label" suffix. The second run failed the same test on the Cause labels:
the cell quotes the "; " separator, which the label regex collected as a label; the separator is now excluded. Green
rerun on c646cea9 with the exit status captured: 31 passed, 1 deselected (the slow DB test), pytest exit 0.

Captured statuses on c646cea9 (clean tree): `make typecheck` OK (605 source files; `typecheck-focused-pp.log`); `make lint`
OK (`lint-pp-docs.log`, `lint-pp-docs-04.log`, `lint-pp-code.log`); focused `tests/unit/reports` + governed-docs + layout +
the DB test module deselected: 47 passed, 1 deselected (`typecheck-focused-pp.log`); engine + architecture + unit
(`-m "not parity and not answer_key and not perf and not slow"`): 2,591 passed, 1 xfailed (Q-11, known), 6m55s
(`cpu-suites-pp-c646cea9.log`); EX42 key alone `not_run`, 0 mismatches, "blocks compared clean: december-2026-rpo contracts;
DB-bound blocks: december-2026-rpo reports rpo", gate exit 2 for the not-run key (`keys-pp-c646cea9.log`,
`report-ex42-pp-c646cea9.json`); DISC-S10-DISCLOSURES-RPO-EX42 + VC-D91-01 2/2; 220-id release selection 220/220, rc 0
(`report-selection-220-pp-c646cea9.json`, captured_sha c646cea9, dirty False). NOT RUN: the DB path test
`test_prior_period_report_k01_september_2026_is_empty` (slow; admitted DB slot only), `make properties`, `make parity`,
`make test-pg`, `make ci` (no chain, no DB stage). Open for F-CLO: the relock KeySpec entry for this kind keys on the three
code columns with the six money columns as measures and `cause`, `product_code`, `satisfied_period_key` as attributes — no
KeySpec change is needed if 4d8e875b already names them so.

### C4-PP-R1 / C4-PP-R2 — reader corrections (Codex packet production-20260920-1314; 2026-09-20)

Codex's source review of 19d26c61 (PRODUCTION-C4-PRIOR-PERIOD-SOURCE-REVIEW-19d26c61.md, SHA-256
c23c5f26…6be8; 28-artifact manifest 0d96abd6…68e4) found two source-supported reader defects — implementation reconciliation, not
an accounting ruling, not an executed report failure.

| Head | Content |
|---|---|
| 79e64e4b | docs first: SCREENS_B 1.16 and 04 1.51 amended IN PLACE (unlanded rows, no new numbers) — the identity at the CONTRACTING-entity grain over the contract's complete obligation population, input set checked, rows restricted to the entity scope only after the identity holds; `prior_period_sum_total` equals `revenue_total` only when the scope covers every performing entity of the contracts read and otherwise differs from it by the SIGNED sum of the out-of-scope rows (Codex 1404: not always "exceeds" — negative contributions can make it smaller; wording corrected in place at b76c2d4e) |
| 01b66504 | code: `read_trace` (pure) + `IdentityItem` / `TraceRead` / `ObligationRef`; `event_refs` (pure) + `_encoded_contracts`; `_entity_codes`; `support/prior_period_worlds.py` (the admitted cross-entity, distinct-calendar world lifted from the D-97 (19) engine test); tests on ACTUAL native traces |

C4-PP-R1 (entity grain). Defect: `build` resolved and filtered the obligation's PERFORMING entity, summed per (contract, performing
entity) and sought `revenue_prior_period_sum:<contract>@<performing entity>:<period>`, while stage 15 `prior_period._sums` emits the sum
under the CONTRACTING entity collecting every performing entity's obligation nodes of the period key. Fail-first
(`fail-first-c4-pp-r1-base.log`, exit 1): the native cross-entity world (US01 monthly with January closed, US02 quarterly with Q1
closed, both obligations delivered 20 January and recorded after the closes) yields `revenue_prior_period:K-LATE/POB-01:FY2026-P02`
1000.00 and `…/POB-02:FY2026-P02` 1000.00 (February on US01, the second quarter on US02 — one key string, two calendars), the sum
`revenue_prior_period_sum:K-LATE@US01:FY2026-P02` 2000.00 with both nodes as inputs, and NO sum under `@US02`; the base US01 subset
(1,000) disagrees with the full sum (2,000). Fix: `read_trace` groups every `revenue_prior_period` node of a period key by contract
(an unknown subject refused by name, never a silent subset), reconciles Σ and the input set against the contracting entity's sum node
(`check_identity`; absent / value / input-set differences refuse `RPT05_SUM_NODE_MISMATCH`), and only then keeps the rows whose
(performing entity, key) is in the run's scope. `prior_period_sum_total` is Σ over the complete population.

C4-PP-R2 (encoded vs raw contract id). Defect: `_event_pairs` returned the CV-21-ENCODED prefix of the CV-22 key
(`bundles._event_key` = `contract_subject_key(external_id)/EV-<n>`) and `_event_types` matched it against RAW `contract.external_id`.
Fail-first (`fail-first-c4-pp-r2-base.log`, exit 1): raw `C@x` → key `C%40x/EV-000004`; the base takes raw `C%40x`'s event
(CONTRACT_AMENDED) instead of `C@x`'s (ESTIMATE_CHANGED); with only `C@x` present it would refuse `RPT05_EVENT_UNRESOLVED`. Fix:
`event_refs` matches the encoded prefix against `contract_subject_key(external_id)` of every contract of the groups read
(`_encoded_contracts`), never a raw id and never by decoding; `_event_types` then reads `contract_event` by (contract id, stream
version).

Tests (`test_revenue_from_prior_period_obligations.py`, 30): native-trace R1 set — the admitted world's shape (dates, entities, both
nodes, the @US01 sum with exactly two inputs, no @US02 sum), all-entity scope (one identity item, 2,000 = 2,000, two rows, both totals
2,000.00), single-entity scopes US01 / US02 (same identity item; one row; `prior_period_sum_total` 2,000.00 vs `revenue_total`
1,000.00), complete-sum-input coverage (partial input set / value difference / absent sum / unknown subject refused by name; a key no
calendar carries yields nothing; December yields one zero item over POB-01 alone), January zero nodes reconciled and omitted;
R2 set — `C@x`, `C%40x`, `A/B`, `K#1`, `P:Q`, `50%` resolve to their own contracts with distinct event types, raw prefixes and
malformed tails resolve to nothing, end-to-end cause attribution per contract with the unresolved boundary refused. After-run
(`fail-first-c4-pp-r1-r2-after.log`): 55 passed / 1 failed on a wrong test assumption (`FY2026-P12` carries POB-01's zero node, so an
identity item exists), corrected; 56 passed, pytest exit 0 (with the RPT-32/36 cross-check, catalogue, governed-docs, layout and the
stage-15 prior-period engine tests).

Captured statuses on 01b66504 (clean tree): typecheck OK (605 files; `typecheck-pp-r1r2.log`); lint OK (`lint-pp-r1-docs.log`,
`lint-pp-r1r2-code.log`); engine + architecture + unit: 2,598 passed, 1 xfailed (Q-11, known), pytest exit 0, 6m48s (`cpu-suites-pp-r1r2-01b66504.log`); EX42 key alone `not_run`, 0 mismatches, "blocks compared clean: december-2026-rpo contracts; DB-bound blocks: december-2026-rpo reports rpo", make exit 2 for the not-run key (the in-memory boundary, XR-12)
(`keys-pp-r1r2-01b66504.log`); DISC-S10-DISCLOSURES-RPO-EX42 + VC-D91-01 2/2 passed, make exit 0; 220-id release selection 220 selected / 220 passed, make exit 0, captured_sha 01b66504, dirty False
(`report-selection-220-pp-r1r2-01b66504.json`). NOT RUN: the DB path test `test_prior_period_report_k01_september_2026_is_empty`
(slow; admitted DB slot only), `make properties`, `make parity`, `make test-pg`, `make ci`. No main merge (hold; slot after ENG-C6).
Column names, measures and attributes unchanged (F-CLO's six-measure KeySpec declaration stands).

### C4-PP-R3-HISTORICAL-MEMBERSHIP — event candidates as of `known_at` (Codex packet production-20260920-1342; 2026-09-20)

Codex's review of 01b66504 (source snapshots and source-manifest.json under the packet; root tools 6f1ad9 / acc854 / ba03a6; the
broader review of 01b66504 still in progress): the encoded-to-encoded matching of C4-PP-R2 is right, but its CANDIDATE population
used CURRENT `contract.combination_group_id` for a HISTORICAL selected version, while `contracts/combination._move` closes the old
T-CON-04 `combination_group_member` row at the event's `recorded_at`, opens the target row and updates the current field. Admitted
case: version V of group G (selected at a fixed `known_at`) cites contract C's event; C JOINs another group after `known_at`; the
same historical report still selects V / G but C is no longer a current member, `_encoded_contracts` omits it, `event_refs` cannot
resolve the unchanged encoded key and `split_node` refuses `RPT05_EVENT_UNRESOLVED`. Source-derived; no DB result, no monetary
discrepancy.

| Head | Content |
|---|---|
| 46cfce22 | code: `_encoded_contracts(session, group_ids, version_ids, known_at)` selects the selected groups' `combination_group_member` rows with `valid_from_known_at ≤ known_at` (pure `historical_candidates`: a later LEAVE or JOIN never removes a candidate; a membership that starts after `known_at` is not one) plus the selected versions' own obligation contracts, then `encoded_index` (`contract_subject_key` per candidate); the current group field is no longer read. Encoded-to-encoded matching, both native identities, tenant guards and money unchanged. Docs: none (SCREENS_B RPT-05 does not name the candidate population) |

Fail-first (`fail-first-c4-pp-r3-base.log`, exit status 1, on 01b66504): the 01b66504 filter `contract.c.combination_group_id.in_(ids)`
quoted; a fake world with C (`C@x`) and D current members of G, V's node citing `C%40x/EV-000004`: before the move labels
{Transaction price change}, amount 1,000 minor; after C joins H (recorded after `known_at`, same V / G / `known_at`) the emulated
current-membership rule loses C → `RPT05_EVENT_UNRESOLVED`. After (`fail-first-c4-pp-r3-after.log`): first run exit 2 (`UUID` not
imported in the test module — a test defect, fixed), then 58 passed, pytest exit 0 (builder tests + RPT-32/36 cross-check +
catalogue + governed-docs + layout + the stage-15 prior-period engine tests).

Tests (`test_revenue_from_prior_period_obligations.py`, 32): a fake T-CON-04 store moved the way `_move` does — identical candidate
set, event resolution, cause labels and revenue before and after a JOIN and a LEAVE recorded after `known_at`; the emulated
01b66504 rule refuses by name after the first move; as-of validation (a membership started after `known_at` excluded; a contract
that left G before `known_at` kept — a version recorded by `known_at` can cite its LEAVE event; other groups ignored);
`encoded_index` of adversarial ids.

Captured statuses on 46cfce22 (clean tree): typecheck OK (605 files; `typecheck-pp-r3.log`); lint OK (`lint-pp-r3-code.log`);
engine + architecture + unit: 2,600 passed, 1 xfailed (Q-11, known), pytest exit 0, 7m01s (`cpu-suites-pp-r3-46cfce22.log`); EX42 key alone `not_run`, 0 mismatches, "blocks compared clean: december-2026-rpo contracts; DB-bound blocks: december-2026-rpo reports rpo", make exit 2 for the not-run key (the in-memory boundary, XR-12) (`keys-pp-r3-46cfce22.log`);
DISC-S10-DISCLOSURES-RPO-EX42 + VC-D91-01 2/2 passed, make exit 0; 220-id release selection 220 selected / 220 passed, make exit 0, captured_sha 46cfce22, dirty False (`report-selection-220-pp-r3-46cfce22.json`).
NOT RUN: the DB path test `test_prior_period_report_k01_september_2026_is_empty` (slow; admitted DB slot only — the producer's DB
execution gate), `make properties`, `make parity`, `make test-pg`, `make ci`. No main merge (hold; slot after ENG-C6). Column names,
measures and attributes unchanged.

Codex packet production-20260920-1404 item 3 (PRODUCTION-C4-PRIOR-PERIOD-CORRECTIONS-46cfce22.md, SHA-256 5b452646…6b00f9; manifest
d75335ea…9a5b; 13 artifacts) resolves C4-PP-R1 / R2 / R3 at source on 46cfce22: the complete obligation population reconciles under the
contracting entity before report-row scope; encoded identities exact; the historical candidate union uses membership starts at or
before `known_at` plus the selected obligation-version contracts, never the current group; keeping ended memberships is intentional
(old trace causes may cite them); engine / key / fixture trees and money expectations preserved; no further blocking source finding
in these three paths. Boundaries Codex keeps (recorded as stated): the R3 tests are fake membership-store / pure-resolver checks —
they do NOT call the `_encoded_contracts` SQL, exercise selected-version ownership, or execute a real JOIN / LEAVE; the actual
nonempty reader, the fixed-`known_at` later-membership lifecycle, the `period_lock_id` refusal on the database path and the broader
acceptance gates remain NOT RUN / separate. Docs wording corrected in place (b76c2d4e): the complete-population total differs from
the scoped total by the SIGNED sum of the out-of-scope rows, not always exceeds it.

### Wave-3 re-merge of main 7bf044a5 (2026-09-20)

Pre-check (read-only, quoted): `git merge-tree --write-tree --name-only HEAD 7bf044a5` on sprint/l4 45487364 → exit 1 (conflicts),
tree 8d7c109c…, conflicting files `docs/04-DATA_MODEL.md`, `docs/design/SCREENS_B.md`; `backend/erev_api/domain/reports/framework.py`
auto-merges. Merge base 4056c168; 515 files changed on main since the base; this lane's files since the base: the builder, framework.py,
`tests/domain/reports/test_prior_period_report.py`, `tests/support/prior_period_worlds.py`, `tests/unit/reports/test_revenue_from_prior_period_obligations.py`,
04, SCREENS_B, this record. `git merge --no-ff --no-edit 7bf044a5` (no rebase).

Conflicts resolved by union: 04 header Revision cell = main's cell with the 1.51 entry inserted in descending order (1.54, 1.53, 1.51,
1.50, 1.49, 1.48, …; uniqueness and descent checked with integer (major, minor) keys — a float comparison mis-orders 1.10 vs 1.9); the
revision log keeps every main row verbatim (1.49, 1.45, 1.44, 1.47, 1.48 in the block) plus the 1.51 row (4 cells); T-CLS-05 = main's new
"Dataset identity (rev 1.39)" paragraph followed by this lane's amended "Dataset identity companions (rev 1.40)" paragraph (the
`prior_period_sum_total` clause — the only difference from main's copy). SCREENS_B: main's Owner cell (a superset of this lane's,
compared entry-wise) and Date "(revision 1.18)" (the maximum; 1.16 stays this lane's row number); the log keeps every main row verbatim
(1.13, 1.10, 1.11, 1.14, 1.15, 1.17, 1.18 in the block; two of them are valid FOUR-cell Markdown rows whose cells contain escaped literal pipes `\|` — no shape defect; this lane's earlier phrase "6 and 5 cells as authored" counted unescaped pipes and is corrected here per Codex 2341) plus the 1.16 row placed before 1.17.
Governed-docs + layout preflight: 10 passed. No Alembic revision from this lane (0 migration files vs the base); the merged migrations and
pins are identical to main's (Alembic head 0064_subledger_line_event; `test_migrations.py` function count 78).

Environment step first (`uv-sync-merge-7bf044a5.log`): `uv sync --project backend --frozen --all-extras` exit status 0 (P2's gcp extra
installed: protobuf, pyasn1, requests, urllib3, …); `backend/.venv/bin/python -c 'import erev_api'` resolves to
`/Users/rsang/dev/erev-wt/l4/backend/erev_api/__init__.py`.

Gates under a free global slot (gate-slot-1.d, claimed by atomic mkdir at 22:33:52Z when it freed, pid 34200, released by the owning PID at 22:44:26Z; both slots were taken at 22:24Z by another lane's remerge-gates and F-CTR l20, so a detached retry
loop claimed the first free slot; `remerge-7bf044a5-gates.log`): make lint rc 0 (the merge-commit guard) → merge commit 5cc79a71;
make typecheck rc 0 (640 source files); focused (unit/reports + governed docs + layout, DB test module deselected) rc 0 — 108 passed, 1 deselected;
CPU set engine + architecture + unit (no DB-fixture modules) rc 0 — 3,102 passed, 1 xfailed (Q-11, known), 6m54s; 220-id release selection rc 0 — 220 selected / 220 passed
(`report-selection-220-remerge-5cc79a71.json`). NOT RUN: the DB path test (slow; lane DB Ray-side), `make properties`, `make parity`,
`make test-pg`, `make ci`. Slot released by the owning PID at the end.

### Wave-3 landing of engc4r (2026-09-20)

Queue line (appended 16:43:49 PDT after the docs lane's COMMIT 45 landed on main 4f37f992):
`engc4r|sprint/l4|864f4057|/Users/rsang/dev/erev/.run/supervisor/lane-merge/msg-engc4r-864f4057.txt|docs/04-DATA_MODEL.md docs/design/SCREENS_B.md`;
the supervisor's read-only pre-check `git merge-tree --write-tree --name-only 4f37f992 864f4057` → tree 00cf5cc6 with
`docs/04-DATA_MODEL.md` the only conflicting path, routed to the chain's revision-row resolver. Two attempts, quoted as measured:

| Attempt | Result |
|---|---|
| 16:45:16 PDT (sealed `attempts/engc4r-864f4057-20260920T164418-81921`, preserved stage directory) | STOP before any commit — "engc4r script rc=6 … STOP" after "conflicts docs/04-DATA_MODEL.md -> merge-revrows": the pre-commit architecture tests failed on the resolved tree with DG-ARC-14 "docs/04-DATA_MODEL.md:9: header row not bracketed by '\|'". Cause (supervisor, reproduced in scratch): a SUPERVISOR resolver defect — the revision-header union split entries on "; " and T1F's 1.52 entry (on main since 71d81d51) contains an internal "; §17.1 rule 7 and LM-CL-14 …"; the fragment became an un-numbered entry that the v5.2 descending sort moved past "see the revision log below. \|", so the merged header no longer ended with "\|". Main untouched (4f37f992, clean, no MERGE_HEAD). This lane's 04 1.51 entry and row were not at fault |
| 17:00:08 PDT (sealed `attempts/engc4r-864f4057-20260920T165004-3352`; controller v6 also sealed the structured answer-keys report, build_sha 3af05338) | "engc4r PASS: merged engc4r sprint/l4@864f4057 onto 4f37f992: **3af05338** \| POSTCHECKS: typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS" after the supervisor's resolver fix (resolve_rev_rows.v6: header entries split only at entry boundaries); the 04 header row on main 3af05338 is bracketed and carries the 1.51 entry in descending order; wrapper "engine+unit: 3042 passed, 1 xfailed in 380.09s"; "selection keys: 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved" |

Merged ≠ gate-measured (Codex production-20260921-0020 item 1, folded here): COMPLETED ordinary integration checks — the chain's
typecheck / cpu / selection post-checks on 3af05338 (verified by Codex 0007); FULL-RELEASE checks still owed to the integrated batch —
the slow DB path test `test_prior_period_report_k01_september_2026_is_empty` (lane DB Ray-side), `make properties`, `make parity`,
`make test-pg`, `make ci` and the canonical `AK_SCOPE=full` corpus. F-RPS composes the builder's SourceContract at its re-merge after this landing (never a
count pin). Codex 2341 verified the record commit 864f4057 as record-only (29 appended lines; accepted source 5cc79a71 unchanged;
PRODUCTION-C4-RECORD-864f4057.md SHA ee93f3a9…; 10 artifacts + 2 references); its terminology item is folded above.

### Returned ci item — empty-report control totals (integrated batch on main 0cb36c14; 2026-09-21)

The integrated batch's ci stage on main 0cb36c14 ("18:58:32 STAGE ci rc=2"; run-0cb36c14-…-20260920T180217/ci.log, read-only) executed
`tests/domain/reports/test_prior_period_report.py::test_prior_period_report_k01_september_2026_is_empty` on a database for the first
time: ci.log 21643 `{'prior_period_sum_total': {'USD': '0.00'}} != {'prior_period_sum_total': {}}` — the report RAN and built its totals,
so the item is real at head (the 58 `StaleBasis` mentions in the same log belong to the journals export / legacy-view ERRORs, P5's D-98
101d item); `k01_pellworth` seeds through the API, not a legacy import. Cause: the K-01 September population is all zero-valued
`revenue_prior_period` nodes with a zero USD `revenue_prior_period_sum` node; every row is omitted (all-zero) while `read_trace` recorded
the zero USD sum, so `control_totals` published `prior_period_sum_total {'USD': '0.00'}` against `revenue_total {}`.

| Head | Content |
|---|---|
| 78f3dda2 | merge of main 0cb36c14 into sprint/l4 (pre-check `git merge-tree --write-tree --name-only HEAD 0cb36c14` exit 0, tree acd02799, no conflicting path; `git merge --no-ff --no-edit`; main's copy of the builder identical). **Deviation, recorded:** the clean auto-merge committed OUTSIDE `if make lint` — every commit, merges included, goes through the guard (a clean auto-merge can still break lint: imports, licence-check, generated files); the guard ran green on the two following commits, so nothing is lost. `uv sync --project backend --frozen --all-extras` rc 0 (`uv-sync-merge-0cb36c14.log`); erev_api resolves to l4 |
| 6c25d06d | docs first: 04 **1.58** (assigned; 1.56 F-SNP, 1.57 F-RPS) T-CLS-05 note — currency entries: `revenue_total` lists the currencies of the published rows (no row, no entry); `prior_period_sum_total` lists a currency when a published row carries it or its Σ of sum nodes is non-zero; an empty report carries `{}` for both, rows netting to 0.00 carry "0.00" in both, a non-zero out-of-scope population still appears in the sum total (the signed-difference rule stands), a population of zero-valued sum nodes with no row adds no entry. The landed SCREENS_B 1.16 sentence stays true |
| c045c586 | code: `control_totals` applies the rule (producer fixed; the DB test's `{}` expectation stays); tests — the empty rule, rows netting to 0.00, a non-zero out-of-scope EUR population alone, the native zero-node world's totals `{}` for both |

Fail-first: `fail-first-pp-empty-totals-base.log` (exit status 1 on the merged tree 78f3dda2: `control_totals([], {("USD", 2): 0})` →
`{'row_count': 0, 'revenue_total': {}, 'prior_period_sum_total': {'USD': '0.00'}}`) → `fail-first-pp-empty-totals-after.log` (41 passed,
1 deselected, pytest exit status 0); typecheck OK (641 files; `typecheck-pp-empty.log`); lint OK on both commits (`lint-pp-empty-docs.log`,
`lint-pp-empty-code.log`).

Gates on c045c586 under gate-slot-1.d (claimed by atomic mkdir at 02:30:08Z when it freed, pid 47458; released by the owning PID at 02:41:31Z) (pid-first owner line; mkdir-only claim, no stale removal; both slots were held by F-SNP l23 and pid 23785 at
02:18Z, owners alive; `empty-totals-gates.log`): make typecheck rc 0 (641 source files); focused rc 0 — 124 passed, 1 deselected; CPU set engine +
architecture + unit rc 0 — 3,147 passed, 1 xfailed (Q-11, known), 8m14s; 220-id release selection rc 0 ("OK answer-keys-filtered") — 220 selected / 220 passed (`report-selection-220-empty-c045c586.json`).
NOT RUN: the DB path test itself (slow; lane DB Ray-side — the integrated batch re-executes it), `make properties`, `make parity`,
`make test-pg`, `make ci`. Files vs 0cb36c14: the builder, its unit test module, 04-DATA_MODEL.md, this record.

Codex production-20260921-0247 (PRODUCTION-C4-EMPTY-TOTALS-REVIEW-c045c586.md, SHA 2c169589…): the correction is SOURCE-CLOSED — "omits a
zero currency only when no published row carries it; offsetting rows keep zero, currencies are independent, and a nonzero out-of-scope sum
remains visible", so "empty report → {}" is qualified by the explicit non-zero exception; amounts, populations, refusals and the
reconciliation unchanged; the original DB test blob cbbd06d9 unchanged. The original ci failure is not converted to PASS without a corrected
execution — the next integrated batch re-executes the DB test.

### Landing of engc4 (b38f1d29 → main 452997ba; 2026-09-21)

Queue line (appended 20:16:48 PDT after the docs lane's COMMIT 49 landed on main ab524b24; append-queue.sh guards passed):
`engc4|sprint/l4|b38f1d29|/Users/rsang/dev/erev/.run/supervisor/lane-merge/msg-engc4-b38f1d29.txt|docs/04-DATA_MODEL.md`; pre-check
`git merge-tree --write-tree --name-only ab524b24 b38f1d29` → tree df1b4283…, rc 0, no conflict (04 named as the safety-net file only).
Controller v13 (pid 6993): "20:16:56 step 48: engc4 sprint/l4@b38f1d29"; "tooling sealed at start — controller 0cba35cb7293e19f…
validator dee51cfea9f96d5b… selection 6dbb673d15197aa6…"; "clean merge -> merge-lane". Terminal line, verbatim: "20:28:42 engc4 PASS:
merged engc4 sprint/l4@b38f1d29 onto ab524b24: **452997ba** \| POSTCHECKS: typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS" (script
rc=0). Wrapper: "postcheck ok: typecheck rc=0"; "engine+architecture+unit: 3148 passed, 1 xfailed in 481.43s (0:08:01)"; "postcheck ok:
cpu rc=0"; "selection keys: 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved"; "postcheck ok: selection
rc=0". Sealed attempt (read-only): `.run/supervisor/lane-merge/attempts/engc4-b38f1d29-20260920T201656-6993` — answer-keys-report.json
(sha256 e22af7623ae6e021…; target answer-keys-filtered; captured_sha 452997ba; tree df1b4283… = tree_sha_end = the pre-check tree; run_id
2e94ac45… bound; validator dee51cfe… rc 0), the at-start tooling copies + tooling.at-start.sha256, rg-selection.at-start.txt (220 ids),
stage-dir. 04 **1.58** is on main (ledger: 1.58 landed; 1.56 / 1.57 still unlanded).

Merged ≠ gate-measured: completed — the chain's typecheck / cpu / selection post-checks on 452997ba; owed to the next integrated batch —
the corrected DB execution of `tests/domain/reports/test_prior_period_report.py::test_prior_period_report_k01_september_2026_is_empty`
(the original ci failure on 0cb36c14 is not converted to PASS without it), `make properties`, `make parity`, `make test-pg`, `make ci`
and the canonical `AK_SCOPE=full` corpus.

Tooling note (queued touch, folded): main's REL-COV-1 (DG-AK-42 rev 1.43) names a filtered answer-keys run `answer-keys-filtered` and
writes its report to `.run/reports/answer-keys-filtered/report.json`; this lane's gate scripts copied `.run/reports/answer-keys/report.json`
(the stale unfiltered report of the 5cc79a71 run) as the retained selection report of the c045c586 gates — the retained copy
`report-selection-220-empty-c045c586.json` was replaced by the filtered report (captured_sha c045c586, 220 / 220, exit 0) before the
READY, and the scripts' copy path is corrected before their next run. Codex production-20260921-0020's two record items are folded in the
"Wave-3 landing of engc4r" section above (the completed-vs-owed split; the escaped pipe in the first Attempt row's quoted diagnostic).
