# ENC-5 input measures (lane ENG-C1, sprint/l5)

Production-readiness programme (Ray's expanded objective, 2026-09-19), engine lane C1. Base
commit 9467de0 (main, clean tree). Governing text: BUILD_SPEC item ENC-5 (`docs/build-spec/12-engine.md`
"Input measures: cost to cost with EAC, uninstalled materials, waste, labour hours and cost
recovery", deferred by the rc: `docs/build-spec/sprint/plan.json` deferred_notes ENC-5 "keys with
those recognition methods fail closed"); ENGINE_SPEC_B §9.2.5 S09-R-14 to S09-R-17, §9.2.10, §9.4,
§9.5, §9.7 EX-09-B and EX-09-C; ENGINE_SPEC S01-R-18, S06-R-15, S06-R-17, S08-R-02; POLICIES POL-091
and the JET-02 row "Uninstalled materials"; 04 T-CON-12, T-CON-13 (`uninstalled_materials_cost`);
D-20; D-76 (uninstalled materials); 03 REQ-REC-007, REQ-REC-008. Rules of the dispatch: no key or
golden edits, fail-first, `make lint`, parity alone, gate slots.

## 1. Spec quotes the build follows

- S09-R-14: "`COST_TO_COST`: progress = margin-bearing costs incurred ÷ (EAC − expected uninstalled
  materials); `progress_ratio` (T-CON-11) holds this margin-bearing progress (REC-S5-EX19 asserts
  0.20), while the posted target uses φ = E ÷ X. Costs flagged `is_wasted` are excluded from the
  numerator and are never in the EAC … Costs flagged `is_uninstalled_material` that meet
  606-10-55-21(b) earn revenue equal to their cost and are excluded from progress and from the
  margin-bearing allocation … The expected total materials cost is the `EAC` parameter
  `uninstalled_materials_cost` …, and absent it the materials cost incurred to date."
- §9.2.5 pseudocode: "E = f × (X − UM_exp) + UM_inc; f_total = E ÷ X; C = cumulative_posted(X, A,
  f_total)"; "if denom <= 0: if K_prog > 0: finding("NON_FINITE_AMOUNT", …
  reason="EAC_NET_OF_MATERIALS_NOT_POSITIVE"); return Fraction(0), UM_inc".
- S09-R-15: "`LABOUR_HOURS`: f = hours to date ÷ expected total hours, where hours to date is the
  latest `PROGRESS_RECORDED.hours_to_date` with `measure = LABOUR_HOURS` at or before d and expected
  hours is the `EAC` pin's `expected_quantity`. A pin without `expected_quantity` gives
  `NON_FINITE_AMOUNT` when hours are positive".
- S09-R-16: "`COST_RECOVERY` (606-10-25-37): while no APPROVED `EAC` pin exists at d, E = min(X, all
  progress costs incurred to d) and f = E ÷ X; from the effective date of the first `EAC` pin the
  obligation is measured as `COST_TO_COST`, and the difference posts as a `CATCH_UP` (§9.2.10). A
  `COST_TO_COST` or `LABOUR_HOURS` obligation with costs and no pin gives f = 0, finding
  `LOSS_EAC_MISSING` when the contract is in 605-35 scope (§11.4), and the costs wait".
- S09-R-17: "When costs recorded after the version exceed the EAC net of materials, stage 09 caps f
  at 1 …; no finding is raised".
- S08-R-02: a new `EAC` version "changes no allocation: stages 09 to 11 read the pin at each date …
  and their target differences post as catch-ups by cause (ENGINE_SPEC_B §9.2.10)".
- S06-R-15 (class N): "`totals` updated: … the `EAC` pin effective at d …; f′_p(d) over updated
  totals (… cost costs to date ÷ updated EAC …)".
- §9.1: "Stage 09 measures progress with the shared functions …, which stages 06 and 08 also use to
  measure catch-ups, so allocation and recognition read one progress function".
- §9.5: formula ids `rec.progress.cost_to_cost.v1`, `rec.progress.labour_hours.v1`,
  `rec.progress.cost_recovery.v1` (progress_ratio) and `rec.uninstalled_materials.v1`
  (revenue_target_exact); `rec.catch_up.sum.v1` inputs "revenue_by_cause nodes, estimate version
  pair".
- D-76 / POLICIES JET-02 row "Uninstalled materials": "Revenue equal to the cost of the uninstalled
  materials whose control has transferred …, at zero margin. The ERP posts the materials cost; the
  engine posts no `COST_OF_REVENUE` line".

## 2. Design

New module `backend/erev_engine/stages/s09_recognition/progress_inputs.py` (the BUILD_SPEC path):

| Piece | Rule | Behaviour |
|---|---|---|
| `cost_inputs(st, ob, d, position)` | S09-R-14 | `COST_INCURRED` with `purpose = PROGRESS_INPUT` naming the obligation (or unnamed on a sole-obligation contract, the stage 11 `_names_unit` reading), split into margin-bearing, `is_uninstalled_material` and `is_wasted` |
| `hours_to_date(st, ob, d, position)` | S09-R-15 | latest `PROGRESS_RECORDED.hours_to_date` with `measure = LABOUR_HOURS` at the position |
| `eac_keys(st, ob, seg)` | T-CON-12; S09-R-14 | the segment's `eac_element_code` when one is named (stage 05 names none, L1-2-Q-51), else the contract's `EAC` elements naming the obligation (`obligation_key`, an `OBLIGATIONS` target) or an unnamed element of a sole-obligation contract; `EAC_IAS37` never measures progress; more than one element fails closed |
| `eac_version(st, ob, seg, d, position)` | S01-R-18; S06-R-15 | greatest `effective_date ≤ d` (ties `version_no`) among versions whose `ESTIMATE_CHANGED` event the position admits, plus, from a class N boundary (INCEPTION basis, cause MODIFICATION) on, every version effective on or before that boundary date |
| `progress(st, ob, seg, d, position)` | S09-R-14 to S09-R-17, S09-R-06 | the `Progress` (value, formula id, params), the `Materials` (UM_exp, UM_inc, UM_k) when materials are expected or incurred, and `NON_FINITE_AMOUNT` findings; TERMINATION gives 1; no pin gives 0 (`reason = EAC_PIN_MISSING`, no finding) |

Formulas (`formulas.py`), all params additive and exact rationals, every node re-evaluates under
`reevaluate(trace)`:

| Formula id | Params | Value |
|---|---|---|
| `rec.progress.cost_to_cost.v1` | `costs`, `eac`, `uninstalled_expected`, `eac_version`, optional `base_costs` (K_k), `wasted`, `reason`, `measure`, `rule` | min(1, (costs − K_k) ÷ (eac − UM_exp − K_k)); 0 with `reason = EAC_NET_OF_MATERIALS_NOT_POSITIVE`; 1 for `rule = S09-R-06` |
| `rec.progress.labour_hours.v1` | `hours`, `expected_hours`, optional `base_hours`, `reason` | min(1, (h − h_k) ÷ (H − h_k)); 0 with `reason = EXPECTED_HOURS_MISSING` |
| `rec.progress.cost_recovery.v1` | `costs`, `x_exact` | min(X, costs) ÷ X |
| `rec.uninstalled_materials.v1` | input (f); `x_exact`, `uninstalled_expected`, `uninstalled_incurred`, optional `base_revenue_exact`, `base_uninstalled` | E = f × (X − UM_exp) + UM_inc; since a boundary E = b_k + g × (X − b_k − (UM_exp − UM_k)) + (UM_inc − UM_k) |

`components.segment_target` dispatches the three methods; `FixedPart` gains `materials` and
`findings`; `_emit_components` emits `revenue_target_exact` with `rec.uninstalled_materials.v1` when
materials exist, else the unchanged inception/prospective formulas (plain cost-to-cost traces keep
their ids and params). `progress_ratio` (T-CON-11 and the trace node) is the margin-bearing f
(REC-S5-EX19 asserts 0.20) while `rec.revenue_cum.v1` posts φ = E ÷ X unchanged.

`decompose`: an `ESTIMATE_CHANGED` that applies an `EAC` version of the element measuring an
input-measured obligation adds no segment (S08-R-02), so `estimate_points` measures C_after − C_before
of the segment targets at the event position, cause `CATCH_UP`, carried by a `contract_event`
source reference (`revenue_delta`) with the exact E_after − E_before; `boundary_points` returns
boundaries and estimate points in ENG-06 order; `emit_catch_up_measures` and
`schedule.obligation_measures` sum every point whose cause is a catch-up measure (cited boundary
nodes and estimate points), so `catch_up_estimate_cum` carries the EAC catch-ups (S09-R-36). A
version recorded after a class N amendment with the same effective date moves nothing (the class N
segment already reads it, S06-R-15), so no spurious `CATCH_UP` appears (EX-09-B).

Stage 06 (`segments._progress`, `segments._eac`, `classify.progress_at`) measures cost-to-cost and
labour-hours boundaries through the stage 09 exports `input_progress` and `eac_version_at`
(`inclusive = not eac_before`): the state before the event with the pins before it, the class N
segment with the updated EAC effective at d. Stage 06 still fails closed at a boundary of a
cost-based obligation without an element or an approved version (S06-R-15, unchanged behaviour);
the element is now resolved by obligation, so answer keys no longer depend on the test-only
`totals.eac_element_code` patch (L1-2-Q-51).

Explain narratives for the four formula ids in `backend/erev_api/explain/narratives.py` and
`frontend/src/messages/en.json` (the cost-to-cost message already existed).

## 3. Fail-first

Base 9467de0, `make answer-keys ID=<24 ids>`: 24 selected, 0 passed, 24 failed, every key at
`EngineError: ENGINE_INVARIANT_VIOLATED: the measure of progress is not built`
(`components.py:274`, rule S09-R-02). Log `.run/l5-enc5/keys-base.log`; per-key extraction in the
same folder. `backend/tests/engine/s09_recognition/test_s09_inputs.py` did not exist.

## 4. After state per key (commit aded5d4)

`make answer-keys ID=<24 ids>`: 24 selected, 10 passed, 14 failed (`.run/l5-enc5/keys-step1.log`).
Every key leaves the measure; the first remaining mismatch of each failing key and its class:

| Key | State | First remaining mismatch | Class |
|---|---|---|---|
| POS-GE-07-RETAINAGE-PRESENTATION | PASS | | |
| REC-FS-07-FIXED-FEE-EAC-HOURS-REVISION | PASS | | |
| REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN | PASS | | |
| REC-S5-EX19 | PASS | | |
| REC-S5-OVERTIME-OWN-OT | PASS | | |
| REC-S5-PROGRESS-VARIANTS-COSTRECOVERY | PASS | | |
| REC-S5-PROGRESS-VARIANTS-WASTE | PASS | | |
| VC-CHK-100-S3-EX21-EXTENDED | PASS | | |
| VC-GE-04-CPIF-EAC-REVISIONS | PASS | | |
| VC-GE-05-AWARD-FEE-POOL-CONSTRAINT | PASS | | |
| IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY | FAIL | balance `loss_provision` expected 0.00 / 60,000.00 (IFRS15), actual absent; subledger LOSS_PROVISION/LOSS_EXPENSE absent | (b) unbuilt item: loss-provision balance and posting wiring (§6.1) |
| JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE | FAIL | balance `loss_provision` expected 0.00 / 30,000.00 / 0.00, actual absent; JET-12 lines absent | (b) as above |
| LOSS-GE-03-LOSS-CONTRACT-PROVISION | FAIL | balance `loss_provision` expected 0.00 / 100,000.00 / 50,000.00 / 0.00, actual absent | (b) as above |
| LOSS-S7-LOSS-OWN | FAIL | balance `loss_provision` expected 0.00 / 30,000.00 / 0.00, actual absent | (b) as above |
| MOD-CHK-027-S6-EX8 | FAIL | `catch_up_modification_cum` expected 91,463.41, actual 76,829.26 (`revenue_cum` 691,463.41 agrees) | (c) expected-value question: cause attribution when the EAC version precedes the amendment (§6.2) |
| MOD-CHK-042-D18 | FAIL | `revenue_cum` expected 70,918.92, actual 70,880.00; L2-B allocated 77,297.30 vs 77,200.00 | (c) same root: the class N weight reads f = 0.4 (updated EAC 75,000 recorded before the amendment) instead of 0.5 (§6.2) |
| MOD-CHK-042-INCEPTION | FAIL | `catch_up_modification_cum` expected 2,000.00, actual 8,000.00 (`revenue_cum` 32,000.00 agrees) | (c) §6.2 |
| MOD-CHK-115 | FAIL | `catch_up_modification_cum` expected −15,555.56, actual 0.00; `catch_up_estimate_cum` expected 0.00, actual −15,555.56 | (c) §6.2 |
| MOD-S6-COMBINED-MOD-OWN | FAIL | `catch_up_modification_cum` expected −5,142.86, actual 20,571.43 (`revenue_cum` agrees) | (c) §6.2 |
| MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM | FAIL | trace node `catch_up:GE-02/L1-WORK:FY2026-P06` expected −4,705.88, actual absent; then `transaction_price` 5,580,000.00 vs 5,480,000.00 at claim-attested | (c) node naming (§6.3); then (b) VC claim constraint outside ENC-5 |
| REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST | FAIL | trace node `catch_up:BR-08/L1-TOOL:FY2026-P04` expected 2,941.18, actual absent (only mismatch) | (c) node naming (§6.3) |
| MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE | FAIL | subledger FY2026-P07 REVENUE cr expected 15,400.00, actual 9,900.00 (the L3-SEATS `SEPARATE_CONTRACT` revenue 5,500.00 is not in the FS-03 subledger); labour-hours L2-IMPL agrees at every checkpoint | (b) separate-contract treatment / subledger attribution, outside ENC-5 |
| MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE | FAIL | L1-SUB allocated 116,600.00 vs 128,040.00; L3-SEATS 28,600.00 vs 17,160.00 after the prospective modification (pool 85,800.00 split 2:1 expected, 4:1 actual); labour-hours L2-IMPL agrees | (a)/(c) stage 06 S06-R-11 remaining-service weight of a time-elapsed subscription against added seats, outside ENC-5 |
| MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE | FAIL | after the partial termination L1-PROTO allocated 1,500,000.00 vs 1,800,000.00, L2-UNITS quantity 5 vs 2 (the whole remaining 8 units terminated and the price reallocated); prototype cost-to-cost completes at 1,500,000.00 before it | (a)/(c) stage 06 `CONTRACT_TERMINATED` PARTIAL with a quantity line, outside ENC-5 |

Classes: (a) engine defect against the spec, (b) another unbuilt item, (c) expected-value question
with evidence. No key was edited.

## 5. Tests

`backend/tests/engine/s09_recognition/test_s09_inputs.py`, 24 tests, all fail-first (the file is
new; the measure raised before): `test_ex_09_b_cost_to_cost_modification_and_eac_change` (C
600,000.00 → 691,463.41 `MODIFICATION` 91,463.41 → 826,463.41 `NORMAL` 135,000.00 → 797,294.12
`CATCH_UP` (29,169.29); September 197,294.12; `revenue_cum` exact 797,294.117647…; the EAC v2
version recorded after the amendment moves nothing), `test_ex_09_b_j14_correction_replay`
(`NORMAL` +33,750.00 then `CATCH_UP` (30,360.47); September 229,852.94),
`test_s06_r15_updated_eac_read_from_the_class_n_boundary`, `test_ex_09_c_uninstalled_materials`
(700,000.00 before the elevators, 2,200,000.00 after; f = 1/5; `rec.uninstalled_materials.v1`; no
`COST_OF_REVENUE` target or schedule kind), `test_ex_09_c_uninstalled_materials_without_the_parameter`
(625,000.00 in November: absent parameter means materials incurred to date), `test_ex_09_c_waste`
(f = 3/8, 375,000.00), `test_s09_r15_labour_hours` (30,000.00; 83,076.92 with `CATCH_UP`
(2,307.69) at the 650-hour version), `test_s09_r15_hours_without_expected_hours_are_non_finite`,
`test_s09_r16_cost_recovery_until_eac` (100,000.00 until the pin, 150,000.00 and `CATCH_UP`
50,000.00 from it), `test_s09_r16_cost_recovery_never_exceeds_the_allocation`,
`test_s09_r16_costs_wait_without_a_pin`, `test_s09_inv_10_progress_bounded`,
`test_s09_r14_eac_net_of_materials_not_positive_is_non_finite`, ten formula cases and the
uninstalled-materials formula (inception and prospective forms).

Existing stage 06 cost-to-cost tests (`test_s06_catch_up.py` CHK-027, CHK-042; `test_s06_prospective`)
pass unchanged through the shared function.

## 6. Questions for the supervisor (returned, not decided)

### 6.1 Loss provision balance and JET-12 posting are not wired (four keys)

Affected keys: IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY, JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE,
LOSS-GE-03-LOSS-CONTRACT-PROVISION, LOSS-S7-LOSS-OWN. Rule text read: ENGINE_SPEC_B §11.2.7 and
S11-R-14 ("the provision required at t is max(0, max(0, EAC − TP_u) − max(0, costs − revenue)) and
the movement is required(t) − required(t − 1)"), S11-R-17 (the release projection), POLICIES JET-12
(Dr `LOSS_EXPENSE` / Cr `LOSS_PROVISION` for the movement, the reverse for a release), 04 T-CON-09
(`loss_provision_txn`; the column exists in `erev_api/db/tables/engine_output.py`), 04 T-CON-17.

What the engine does on e467e25: stage 11 computes every expected figure from the new cost-to-cost
revenue (T-CON-17 `loss_provision_versions`, minor units shown as amounts):

| Key | Period | costs to date | revenue to date | EAC | provision balance | movement | Key expects |
|---|---|---|---|---|---|---|---|
| LOSS-S7-LOSS-OWN, JE-CHK-132 | FY2026-P12 | 450,000.00 | 500,000.00 | 900,000.00 | 0.00 | 0.00 | 0.00 |
| | FY2027-P12 | 770,000.00 | 700,000.00 | 1,100,000.00 | 30,000.00 | 30,000.00 | 30,000.00; Dr LOSS_EXPENSE 30,000.00 / Cr LOSS_PROVISION 30,000.00 |
| | FY2028-P12 | 1,100,000.00 | 1,000,000.00 | 1,100,000.00 | 0.00 | (30,000.00) | 0.00; Dr LOSS_PROVISION 30,000.00 / Cr LOSS_EXPENSE 30,000.00 |
| LOSS-GE-03 | FY2026-P06 | 800,000.00 | 960,000.00 | 2,000,000.00 | 0.00 | 0.00 | 0.00 |
| | FY2026-P09 | 1,300,000.00 | 1,200,000.00 | 2,600,000.00 | 100,000.00 | 100,000.00 | 100,000.00; Dr LOSS_EXPENSE 100,000.00 |
| | FY2026-P12 | 1,950,000.00 | 1,800,000.00 | 2,600,000.00 | 50,000.00 | (50,000.00) | 50,000.00; Cr LOSS_EXPENSE 50,000.00 |
| | FY2027-P03 | 2,600,000.00 | 2,400,000.00 | 2,600,000.00 | 0.00 | (50,000.00) | 0.00; Cr LOSS_EXPENSE 50,000.00 |
| IFRS-SW11 (IFRS15 book) | FY2026-P03 | 0.00 | 0.00 | 1,100,000.00 | 100,000.00 | 0.00 | (not asserted) |
| | FY2026-P06 | 440,000.00 | 400,000.00 | 1,100,000.00 | 60,000.00 | (40,000.00) | 60,000.00; Dr LOSS_PROVISION 40,000.00 / Cr LOSS_EXPENSE 40,000.00 |
| IFRS-SW11 (ASC606 book) | FY2026-P06 | out of 605-35 scope | | | none | | 0.00 |

But no T-CON-09 `loss_provision_txn` column is produced (`erev_engine/__init__.py` adds
`cost_asset_carrying_txn` only) and no posting intent with `LOSS_PROVISION` or `LOSS_EXPENSE` is
derived (stage 14 holds the JET-12 template rows but nothing derives entries from
`CostLossState.loss_provisions`), so the keys stop at `loss_provision: actual <absent>` and the
JET-12 subledger lines are absent.

Candidate treatments: (A) build the wiring as a separate item (stage 11 `provision_balance` →
T-CON-09 `loss_provision_txn` per contract, entity and period, on the pattern of
`_cost_asset_carrying`; stage 14 JET-12 entries from `provision_movement` per period, a release
posting the reverse): every figure in the table then posts as the keys expect, the ASC606 book of
IFRS-SW11 reading 0.00 through the S10-INV-08 zero of an out-of-scope unit; (B) leave the four keys
failing until that item is scheduled. Either way the ENC-5 inputs to the loss test are proven.

### 6.2 Cause attribution when an EAC version is recorded before the amendment (five keys)

Affected keys: MOD-CHK-027-S6-EX8, MOD-CHK-042-D18, MOD-CHK-042-INCEPTION, MOD-CHK-115,
MOD-S6-COMBINED-MOD-OWN. Each records the `EAC` `ESTIMATE_CHANGED` (and, where present, the VC
version) with the modification's effective date but a lower `seq` than the `CONTRACT_AMENDED`
(CHK-027 seq 6, 7 < 8; CHK-042 6 < 7; CHK-115 5, 6 < 7; COMBINED 5 < 6).

Rule text read: S09-R-04 "Segment selection uses ENG-06 order: an event on date d with a lower
`record_seq` than the boundary event is measured in the previous segment. A catch-up is therefore
C_after(d) − C_before(d), both evaluated at the same progress"; S09-R-35 with `CAUSE_OF_ESTIMATE_KIND`
(`EAC` → `CATCH_UP`, `VARIABLE_CONSIDERATION` → `TP_CHANGE`) and `CAUSE_OF_EVENT` (`CONTRACT_AMENDED`
→ `MODIFICATION`); S06-R-17 "CU_posted = C_after(d) − C_before(d), with C and E per CV-63 at the
same ENG-06 position"; S06-R-15 (class N reads "the `EAC` pin effective at d"); S08-R-02 (a new
`EAC` version "changes no allocation … their target differences post as catch-ups by cause"); ALG-04
§2.5.5 (the class N weight uses f_p at the boundary, ALG-04 step "progress f_p (cost-to-cost: costs
to date ÷ EAC)"). Answer-key convention (runners.py, D-87 L6-5-Q-27): a key's `catch_up_estimate_cum`
compares with the engine's `catch_up_tp_change_cum` + `catch_up_estimate_cum`.

Treatment (A), the spec as written and as built: the version recorded before the amendment is in
force before it, so C_before at the boundary already carries it and its effect is a separate
`CATCH_UP` (or `TP_CHANGE`); the class N weight is measured with the updated EAC. Treatment (B), the
keys' reading (and EX-09-B, whose amendment "records EAC 820,000.00" and whose stage 06 unit test
records the version after the amendment): a version effective on the modification date and recorded
in the same stream position group is the modification's updated EAC, its effect and the VC's part
of the `MODIFICATION` cause, and the class N weight is measured with the previous EAC. Totals agree
under both; the figures each yields:

| Key (checkpoint) | (A) engine on e467e25 | (B) key expectation |
|---|---|---|
| MOD-CHK-027 (FY2027-P02) | `CATCH_UP` (87,804.88) [EAC v2: round(1,000,000 × 420,000 ÷ 820,000) − 600,000.00]; `TP_CHANGE` 102,439.03 [bonus includable: round(1,200,000 × 420,000 ÷ 820,000) − 512,195.12]; `MODIFICATION` 76,829.26 [round(1,350,000 × 420,000 ÷ 820,000) − 614,634.15]; `catch_up_modification_cum` 76,829.26; revenue_cum 691,463.41 | `catch_up_modification_cum` 91,463.41 (the whole 691,463.41 − 600,000.00); revenue_cum 691,463.41 |
| MOD-CHK-042-D18 (2026-07-01) | class N weight of B with f = 30,000 ÷ 75,000 = 0.4: 75,000 × 0.6 + 25,000 = 70,000 against C 30,000; shares 53,200.00 / 22,800.00; B allocated 77,200.00, revenue 30,880.00, `CATCH_UP` (6,000.00) [60,000 × 0.4 − 30,000] then `MODIFICATION` 6,880.00; contract revenue_cum 70,880.00 | f = 30,000 ÷ 60,000 = 0.5: weight 75,000 × 0.5 + 25,000 = 62,500 against 30,000; shares 47,297.30 / 22,702.70; B allocated 77,297.30, revenue 30,918.92, `catch_up_modification_cum` 918.92; contract revenue_cum 70,918.92 (BUILD_SPEC `test_chk_042_mixed_d18_default` figures) |
| MOD-CHK-042-INCEPTION (2026-07-01) | `CATCH_UP` (6,000.00) then `MODIFICATION` 8,000.00; revenue 32,000.00 | `catch_up_modification_cum` 2,000.00; revenue 32,000.00 |
| MOD-CHK-115 (2026-07-01; 2026-10-01) | `CATCH_UP` (55,555.56) [1,000,000 × 400,000 ÷ 900,000 − 500,000]; `TP_CHANGE` 40,000.00 [90,000 × 4 ÷ 9]; `MODIFICATION` 0.00; then `TP_CHANGE` 13,333.33 at the price agreement; the key's estimate bucket reads (15,555.56) then (2,222.23) | `catch_up_modification_cum` (15,555.56) [1,090,000 × 4 ÷ 9 − 500,000, POLICIES CHK-115]; estimate 0.00 then 13,333.33 |
| MOD-S6-COMBINED-MOD-OWN (FY2026-P06) | `CATCH_UP` (25,714.29) [450,000 × 120,000 ÷ 350,000 − 180,000]; `MODIFICATION` 20,571.43 [510,000 × 120,000 ÷ 350,000 − 154,285.71]; revenue 174,857.14 | `catch_up_modification_cum` (5,142.86); revenue 174,857.14 |

Under (B) the engine would need a rule that a version effective on the boundary date and recorded
before the boundary counts from the boundary only (an amendment of S09-R-04/S06-R-17), or the five
keys would move the `ESTIMATE_CHANGED` after the `CONTRACT_AMENDED` (a key correction). The lane
implemented (A) and edited no key.

### 6.3 Trace node naming `catch_up:<ob>:<period>` (two keys)

Affected keys: MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM (trace `measure: catch_up, subject_key:
L1-WORK, period_key: FY2026-P06, value −4,705.88`), REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST
(`catch_up`, L1-TOOL, FY2026-P04, 2,941.18; its only mismatch). Rule text read: CV-50 "Node ids.
`<measure>:<subject key>:<period key or '-'>`", S06-R-17 "Node `catch_up@<event key>:<ob>:-`",
ENGINE_SPEC OQ-A-23 "05 §3.6.8 names the catch-up node `catch_up:<obligation key>:<period key>`,
which collides when two boundaries fall in one period | CV-50 `catch_up@<event key>:<ob>:-`;
correct 05 mechanically | Resolved by D-76". Engine values on e467e25:
`catch_up@GE-02/EV-000005:GE-02/L1-WORK:-` −4,705.88 and
`revenue_by_cause:GE-02/L1-WORK/MODIFICATION:FY2026-P06` −4,705.88;
`catch_up@BR-08/EV-000008:BR-08/L1-TOOL:-` 2,941.18 and
`revenue_by_cause:BR-08/L1-TOOL/MODIFICATION:FY2026-P04` 2,941.18.

Candidate treatments: (A) the keys cite a CV-50 node (`catch_up@<event key>:<ob>:-`, or the period
node `revenue_by_cause:<ob>/<cause>:<period>`) — REC-BR-08 then passes and MOD-GE-02 proceeds to
its claim mismatch (§6.4), with the same figures; (B) the engine emits an additional
`catch_up:<ob>:<period>` node — the naming OQ-A-23 retired because two boundaries in one period
collide. A key correction under D-76 OQ-A-23, not a lane edit.

### 6.4 Items outside ENC-5 reached by the keys

- MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE (`SEPARATE_CONTRACT` upsell, S06-R-03): the FS-03 July
  subledger block (`match: subset`) expects REVENUE 15,400.00 = L1-SUB 9,900.00 + L3-SEATS 5,500.00
  (33,000.00 over six months); the engine posts 9,900.00 under FS-03 (L1-SUB 118,800.00 allocated,
  L2-IMPL satisfied at 16,200.00). Treatments: (A) the separate contract's revenue posts under its
  own contract key and the key's block names the wrong contract; (B) the block should include it.
  The lane did not verify where the 5,500.00 posts.
- MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE (S06-R-11 weights): pool 85,800.00 =
  (118,800.00 − 59,400.00) + 26,400.00; engine `mod_weight` L1-SUB 132,000 (basis `D18_DEFAULT`, the
  mod-date SSP entry, no remaining-service scale) against L3-SEATS 33,000 → shares 68,640.00 /
  17,160.00, allocations 128,040.00 / 17,160.00; the key expects 66,000 : 33,000 (the subscription's
  remaining six months) → 57,200.00 / 28,600.00, allocations 116,600.00 / 28,600.00, July revenue
  68,933.33 / 4,766.67. Treatments: (A) the series row of S06-R-11 (the mod-date entry prices the
  remaining increments; EX-09-A rev 1.6 note) with a 132,000.00 entry; (B) the time-elapsed
  remaining-service factor 0.5 on the subscription.
- MOD-GE-02 (after §6.3): at claim-attested the claim VC v1 (unconstrained 150,000.00, constrained
  100,000.00, effective 2026-11-30) is not in the price: TP 5,480,000.00 and constrained VC
  180,000.00 where the key expects 5,580,000.00 and 280,000.00 (revenue_cum 4,186,966.29 vs
  4,263,370.79). Stage 04 VC claim handling (606-10-32-11), outside ENC-5.
- MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE (S06-R-21, ALG-04 25-13(a)): the `TERMINATION`
  modification with a 5-unit line (−600,000.00) makes the engine terminate the whole L2-UNITS
  remainder (`mod_weight` `terminated: true`, `remaining_quantity` 0), post `TERMINATION` 300,000.00
  on L2-UNITS (allocated 600,000.00, quantity 2) and `MODIFICATION` 300,000.00 on the satisfied
  prototype (allocated 1,800,000.00); the key expects the prototype unchanged at 1,500,000.00 and
  the 3 kept units at 200,000.00 each (L2-UNITS 900,000.00, quantity 5, pool 600,000.00 with no
  catch-up on the satisfied prototype). Treatments: (A) a partial termination line reduces the
  quantity by the line's units; (B) it terminates the obligation's remainder. The cost-to-cost
  prototype completes at 1,500,000.00 on 30 June in both.

### 6.5 Accounting judgments the spec leaves open (implemented as stated, flagged)

- Uninstalled materials on a `PROSPECTIVE` (class D) segment: §9.2.5 gives the inception-basis form
  only. The lane generalised it as E = b_k + g × (X − b_k − (UM_exp − UM_k)) + (UM_inc − UM_k) with
  K_k and UM_k the margin-bearing costs and materials before the boundary (CV-62 reading). No key
  exercises it; `test_uninstalled_materials_formula` pins the form.
- `COST_RECOVERY` numerator: "all progress costs incurred to d" is read as every `PROGRESS_INPUT`
  cost including wasted and uninstalled-material costs (recoverable costs, 606-10-25-37). The key
  REC-S5-PROGRESS-VARIANTS-COSTRECOVERY carries no flags.
- A pin whose event the position does not admit but whose `effective_date` is on or before a
  class N boundary counts from that boundary (S06-R-15). The lane applies this to segments with
  basis INCEPTION and cause MODIFICATION only; TP_CHANGE copies of such a segment keep the
  extension through the earlier class N boundary date.
- `eac_keys` fails closed when more than one `EAC` element names the obligation (no key does).

### 6.6 Independent review findings (Codex, PRODUCTION-C1-INDEPENDENT-REVIEW-20260919): resolved

All three were reproduced fail-first on aded5d4 with the reviewer's figures, then fixed in the
second commit; the tests carry explicit chronology (pre-cutover cost, cutover, later cost) and
assert bases, causes and trace params.

| # | Finding | Fail-first on aded5d4 | Fix | After |
|---|---|---|---|---|
| 1 | Stage 06 measured a cost-to-cost boundary as X × f, dropping the zero-margin materials | `segments.measure` on EX-09-C at a 31 Dec amendment: exact 1,000,000.00 where stage 09's target before the event is 2,200,000.00 | `segments.measure` takes (f, E, C, φ) from the new stage 09 export `input_target` (`components.segment_target` at the event position, materials included); f keeps the S09-R-14 margin definition (0.2) for classes and S06-R-11 weights | `test_s06_boundary_measure_carries_the_uninstalled_materials`: f 1/5, E 2,200,000.00 = `target_at_position` before the event |
| 2 | Before an `OPENING_BALANCE` cutover the prospective base (costs before the cutover event) exceeded the costs at an earlier date and raised `NON_FINITE_AMOUNT` | X 1,000.00, baseline 200.00 at the 30 Jun cutover, pre-cutover cost 200.00 on 31 Mar: FY2026-P02 raised `NON_FINITE_AMOUNT: progress is undefined` | `progress_inputs._precedes_boundary`: a `PROSPECTIVE` segment evaluated before its boundary event (only the opening segment is in force then, S09-R-07) gives f = 0 with `reason = BEFORE_BOUNDARY` and no materials, so the target is the imported baseline | `test_s09_r07_opening_balance_cost_to_cost_keeps_the_baseline_before_the_cutover`: P02/P03/P06 200.00; P09 200.00 + 800.00 × (300 − 200) ÷ (800 − 200) = 333.33 (`base_costs` 200, f 1/6); no findings |
| 3 | No-EAC `COST_RECOVERY` since a boundary counted the imported baseline twice | same world, COST_RECOVERY: 360.00 at the cutover and 440.00 after +100.00 (f = min(X, costs) ÷ X applied to X − b_k) | `rec.progress.cost_recovery.v1` gains `base_costs` and `base_revenue_exact`: since a boundary g = min(1, (costs − K_k) ÷ (X − b_k)), the costs since the boundary over the remaining allocation (CV-62) | `test_s09_r16_cost_recovery_since_an_opening_balance`: P02 200.00, P06 200.00, P09 300.00 (g 0.125), cause `NORMAL` 100.00 |

The 24 ENC-5 keys give the same 10 passed / 14 failed with identical mismatch lines after the
fixes (no key in the corpus exercises an opening balance or a boundary with materials).

## 7. Gates (measured on e467e25 unless stated; nothing projected)

| Gate | Result |
|---|---|
| `make lint` | OK (ruff format, ruff check, design-check, vocab-check, licence-check, secrets-check, registry-seed, fixtures) |
| `make typecheck` | OK, 561 source files |
| `backend/tests/engine` + `backend/tests/unit` + `backend/tests/architecture` | 1,378 passed, 5 xfailed (the pre-existing billing-identity xfails), 0 failed |
| `backend/tests/engine/s09_recognition/test_s09_inputs.py` | 27 passed (24 on aded5d4 + the three review-finding tests) |
| `make answer-keys ID=<24 ENC-5 ids>` | 24 selected; 10 passed, 14 failed (same ids and mismatch lines as aded5d4; §4) |
| `make answer-keys ID=<rg-selection.txt, 182 ids>` | 182 selected; 182 passed, 0 failed, 0 withdrawn (also 182/182 on aded5d4) |
| `make answer-keys` (all active) | 243 selected; 193 passed, 48 failed, 0 not run, 2 withdrawn. Against the 58-id base `.run/l9bgate/keys-all-failed.txt`: no new failure; the 10 ids turned green are exactly POS-GE-07-RETAINAGE-PRESENTATION, REC-FS-07-FIXED-FEE-EAC-HOURS-REVISION, REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN, REC-S5-EX19, REC-S5-OVERTIME-OWN-OT, REC-S5-PROGRESS-VARIANTS-COSTRECOVERY, REC-S5-PROGRESS-VARIANTS-WASTE, VC-CHK-100-S3-EX21-EXTENDED, VC-GE-04-CPIF-EAC-REVISIONS, VC-GE-05-AWARD-FEE-POOL-CONSTRAINT (identical set on aded5d4) |
| `make parity` (alone, unfiltered) | 122 selected; 121 passed, 1 failed: `point_in_time_equivalence::shipped-db-equivalence`, "kind point_in_time_equivalence has no parity reader yet; BUILD_SPEC GPB builds it" (GPB-3, deferred; deselected by the release gate) |
| `make parity K="not point_in_time_equivalence"` (alone, the release-gate filter) | 121 selected; 121 passed, 0 failed, 0 skipped (129 passed, 1 deselected), the base gate's count |
| `make properties` | 12 passed, 0 failed, 0 skipped; OK properties |
| `make test-pg` (gate slot 2, chain `.run/l5-enc5/gates-chain.sh`, PID 62752) | backend 290 passed, 0 failed, 0 skipped (2,532 deselected); STAGE test-pg OK; log `.run/l5-enc5/chain/test-pg.log` |
| `make ci` (same chain) | backend 2,446 passed, 0 failed, 5 skipped (371 deselected, 5 xfailed); vitest 614 passed (94 files); "All checks passed!"; STAGE ci OK, 44 min; log `.run/l5-enc5/chain/ci.log`; summary `.run/l5-enc5/chain/summary.txt` (END 2026-09-19 12:26:39, head e467e25) |

## 8. Run log

- Fail-first 24 keys on 9467de0: 24 failed, "the measure of progress is not built".
- aded5d4 `make lint` OK; `make typecheck` OK (561 files); engine s06/s08/s09/s11/s15 311 passed;
  architecture 72 passed; engine + unit 1,277 passed, 2 failed then fixed in the same commit
  (`test_narratives_cover_referenced_keys`: narratives added; `test_dg_lay_01_top_level_directories`:
  a stray `.ruff_cache` from a bare `ruff format`, removed); `test_s09_inputs.py` 24 passed.
- 24 ENC-5 keys on aded5d4: 10 passed, 14 failed (table in §4). Release selection on aded5d4
  182/182; all active on aded5d4 243 / 193 passed / 48 failed / 2 withdrawn, no new failure.
- Review findings reproduced fail-first on aded5d4 (§6.6), fixed in e467e25; `make lint` OK,
  `make typecheck` OK; engine + unit + architecture 1,378 passed / 5 xfailed; 24 keys 10 / 14 with
  identical mismatch lines; selection 182/182; all active 243 / 193 / 48 / 2 with the same 10 greens;
  parity alone 121/122 unfiltered (the deferred GPB-3 kind) and 121/121 with the release-gate filter;
  properties 12 passed.
- DB stages: one long-lived chain `.run/l5-enc5/gates-chain.sh` (its own PID 62752 in the gate
  slot; waits while two other worktrees' DB stages run; test-pg then ci; releases the slot on exit
  only when the file still holds its own PID), started 2026-09-19 11:24:09 PDT on e467e25, took
  gate-slot-2 at 11:40:44 with one other DB stage running. The chain ran with one uncommitted file,
  this record (`docs/reviews/loop/sprint/ENC-5-input-measures.md`, docs only; no source, test, key
  or frontend file was uncommitted), so the measured code is e467e25 exactly; under GATE-BIND-1 lane
  chains are progress and merge evidence, and release evidence is produced on main. test-pg OK at
  11:42 (290 passed); ci started 11:42:10 and ended OK at 12:26:39 (backend 2,446 passed / 0
  failed / 5 skipped; vitest 614 passed); END head e467e25. While ci ran, gate-slot-2 was
  re-claimed by lane D1's chain (PID 7706, about 11:48); this chain did not intervene and its
  guarded release left that claim untouched (no RELEASED line).
- Commits on sprint/l5: aded5d4 (the measures, tests, narratives), e467e25 (the three review
  findings), then this record (docs only). Never merged or pushed by the lane.
