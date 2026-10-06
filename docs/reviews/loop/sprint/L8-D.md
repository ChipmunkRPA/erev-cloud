# L8-D: engine fix lane D, Level 8 remediation

Lane builder record for lane L8-D (stages 01, 04 to 09 and the answer-key runner) on `sprint/l5` (worktree `~/dev/erev-wt/l5`). Binding rulings: `D-88-rulings.md` (L7-5 section) and `D-89-rulings.md`.

## Batch 1

### Start

- STEP 0: `git merge --ff-only main` to 0266227 (clean tree), then `make setup` (OK setup).
- Release-gate selection at 0266227 (`rg-selection.txt`, 174 ids): 158 passed, 16 failed: `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT`, `ALC-CHK-032-S4-EX34-CASEC-REJECTED`, `ALC-S4-EX35-CASEB`, `COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT`, `DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT`, `FX-CHK-084-A-REFUND-LIABILITY-REMEASURED`, `JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE`, `MOD-CHK-112`, `MOD-FS-09-CANCELLATION-REFUND-COMMISSION`, `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION`, `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION`, `ONB-RB-06-RELIEF-GRANT-ROUTED-OUT`, `REC-S5-UPFRONTFEE-OWN-A`, `REC-S5-UPFRONTFEE-OWN-B`, `RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION`, `RND-CHK-003C`.

### L7-5-Q-5 (END-10 tick evidence; 2aefeb9)

- `backend/tests/engine/s14_posting/test_tc_je.py::test_tc_je_08_full_year_gross_and_delta` asserts C4 POB #3 at −293.92 to the cent, inside the same gross and delta dictionaries as every other C2 and C4 figure (C2 +1,100.00 / −573.20 / −385.19 / −141.61; C4 +1,200.00 gross and +1,050.00 delta; POB #1 −479.69 gross and −329.69 delta; POB #2 −426.39; POB #3 −293.92). The one-minor-unit tolerance is gone; the comment cites DEVIATIONS §4.1 (bound A 293.92 below round(X) 293.93).
- `test_tc_je.py`: 6 of 6. C3 POB #3 keeps its L3-2-Q-22 tolerance (not in this ruling).
- END-10 ticks on this file as written.

### L7-5-Q-12 (runner subledger period selection; 204c4e6)

- `_CheckpointComparison.aggregate` compares a block's own `period_key` from the checkpoint's outputs whatever `as_of`; `as_of` still selects the labelled balances. Class docstring records the post-rc §9.5.6 editorial amendment.
- Corpus scan (`.run/l8d_probe_q12.py`): the only block of a period ending after its checkpoint `as_of` is `REC-S5-UPFRONTFEE-OWN-B` `end-of-january` FY2026-P02, so no other key's comparison changes.
- Figures reproduce as ruled: FY2026-P02 L1-SUB 2100 Dr / 4010 Cr 1,000.00 and L2-FEE 83.34; the key passes.
- Test: `test_runner_engine.py::test_l8_d_subledger_block_compares_its_own_period_whatever_as_of`.
- Keys now passing: `REC-S5-UPFRONTFEE-OWN-B`. Selection 159 of 174, no new failure.

### L7-5-Q-13 (runner `_terms_conversions`, delta branch; df8b7d1)

- A delta-form line of a `TERMINATION` modification with action CHANGE, quantity_delta 0 and `end_date` on or before d becomes REMOVE with quantity_delta −(quantity in force − net delivered on or before d). consideration_delta, dates and `price_change_amount` stay as keyed. The converted lines live in `_Assembler.terminations` (not `terms`, so no L5-3-Q-19 null price change applies). Run note: `L7-5-Q-13: C-TERM MOD-TERM delta-form TERMINATION line L1-SUB CHANGE quantity_delta 0 with end_date 2027-06-30 on or before 2027-06-30 read as REMOVE quantity_delta -1 (quantity in force 1 less net delivered 0); consideration_delta and dates as keyed`.
- Next stop measured: stage 10 `_concessions` "a refund quota names an obligation absent from the state" (`C-TERM#TERMINATION@C-TERM/EV-000007`), which is lane L8-E's L7-5-Q-2 (i).
- Test: `test_runner_engine.py::test_l8_d_termination_change_line_ending_by_d_reads_as_remove`.
- Selection 159 of 174, same failures.

### MOD-CHK-112 at-termination and MOD-FS-09: first green at the merge (eb68a00, aed8a6b)

- Probe with lane L8-E's L7-5-Q-2 (i) stood in by an in-process monkeypatch (stage 10 `_concessions` ignores `<contract>#TERMINATION@<event key>` quotas; no file change): both keys stopped only on DG-AK-54 `reevaluate(trace)`, 18 mismatches each, in every checkpoint.
  - MOD-CHK-112: `catch_up_amount`, `catch_up_cum` and `catch_up_modification_cum` of `C-TERM/L1-SUB` stored 0.00 while citing `catch_up@C-TERM/EV-000007:C-TERM/L1-SUB:-` = 10,000.00 (`mod.catch_up.v1`, measured_on 2027-06-29, exact_before 170,000, exact_after 180,000).
  - MOD-FS-09: the same nodes stored 0.00 against 8,000.00.
- Root cause: stage 09 recomputed a boundary's delta as C_after(d) − C_before(d) of its own segment targets. Stage 06 measures a time-elapsed boundary on the close of d − 1 (EX-09-A `boundary_as_of`); at a month-end termination stage 09's target at d is 180,000.00 on both sides, so the sums published 0 while citing the 10,000.00 node. S09-R-36: the delta is the stage 06 or stage 08 node, cited and never recomputed.
- Fix: `decompose.cited_posted(tb, mu)` reads the posted value of a `catch_up@` node the builder holds; `boundary_points` and `points` take it as the boundary delta when present (recomputation stays only where no node exists). Callers: `components.revenue_targets` and both `schedule.py` call sites.
- With the stand-in, both keys PASS at eb68a00. On this branch alone they still stop at the stage 10 quota lookup.
- Test: `backend/tests/engine/s09_recognition/test_s09_catch_up_exact.py::test_s09_r36_boundary_delta_is_the_cited_node_never_recomputed` (month-end termination world: recomputed delta 0, cited 1,000.00, catch-up measures reproduce under `reevaluate`; the recomputed form does not).
- Engine tests `s06_modifications`, `s08_estimates_late_events`, `s09_recognition`: 152 passed. Parity 121 of 121. Selection 159 of 174, same failures.

### L7-5-Q-2 (ii) (runner questionnaire member for MOD-JS-06; 5a00650)

- `_Assembler.distinct_answers`: when a key modification has no `remaining_goods_distinct_from_transferred` answer for an existing obligation that a checkpoint `modifications[].proposed_treatments` of that reference lists, the runner supplies true for PROSPECTIVE and false for CUMULATIVE_CATCH_UP, merged into the T-CON-06 questionnaire section, with a run note. The S06-R-05 defaults stay for platform commands.
- Keys receiving a supplied answer: `ALC-S4-EX6`, `BRK-CAP-CREDITS-ROLLOVER-RENEWAL`, `DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION`, `MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE`, `MOD-FS-10-CLOUD-CONVERSION-CREDIT`, `MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM`, `MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE`, `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION`, `REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST`, `REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN`, `REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT`. Of the 24 keys that list `proposed_treatments`, only MOD-JS-06 changes outcome (9 to 12 mismatches); `ALC-S4-EX6` keeps passing.
- MOD-JS-06 measured after the supply:
  - L1-STORE1 class D by QUESTIONNAIRE (f 0.025); proposed_treatments L1-STORE1 and L2-STORE2 PROSPECTIVE, as keyed (before: L1-STORE1 CUMULATIVE_CATCH_UP, revenue_cum 1,827.00).
  - Pool 109,000.00, as ruled.
  - Weights (`mod.weights.d18.v1`, D18_DEFAULT): L1-STORE1 40,000 (remaining_quantity 1 × 40,000), L2-STORE2 40,000; shares 54,500.00 / 54,500.00. The ruling uses 39,000 / 40,000 (53,810.13 / 55,189.87). See L8-D-Q-1.
  - schedule-revised: L1-STORE1 allocated 55,500.00 (key 54,810.13), L2-STORE2 54,500.00 (55,189.87), revenue_cum 1,465.81 (1,459.92), FY2026-P10 CL Dr / revenue Cr 465.81 (459.92), CL 98,534.19 (98,540.08).
  - year-end: revenue_cum 2,397.44 (2,379.75), CL 97,602.56 (97,620.25).
- Test: `test_runner_engine.py::test_l8_d_runner_supplies_the_remaining_goods_distinct_answer`.
- Selection 159 of 174, same failures.

### L7-5-Q-11 (runner supplied judgement; 50fe154)

- `_Assembler.nondistinct`: a booked key line whose template `obligation_kind` is STANDARD, that names `bundle_parent_obligation_key`, and whose obligation key no checkpoint row (obligations, schedule, subledger `obligation_key`, modifications) and no timeline payload names gets a REVIEWED `POB_DISTINCT_OVERRIDE` {obligation_key, distinctness nondistinct, integrates_into_obligation_key the parent}, judgement key `<contract>/RUNNER-POB-NONDISTINCT-<line>`, with a run note.
- Corpus scan: only `REC-S5-UPFRONTFEE-OWN-A` `L2-FEE` meets it; `POB-S2-SHIPPING-OWN-ON`, `-OFF` and `IFRS-S13-SWITCH-SHIPPING` have SHIPPING-kind lines.
- Figures as ruled, and the key passes: end-of-january TP 15,000.00, L1-SUB allocated 15,000.00, revenue_cum 1,250.00, scheduled 13,750.00, CL 13,750.00, schedule FY2026-P01 / P02 / P12 1,250.00, FY2026-P01 2100 Dr / 4010 Cr 1,250.00; end-of-year-1 revenue_cum 15,000.00, CL 0.00.
- Test: `test_runner_engine.py::test_l8_d_runner_supplies_the_bundle_parent_nondistinct_override`.
- Keys now passing: `REC-S5-UPFRONTFEE-OWN-A`. Selection 160 of 174, no new failure.

### Spec questions

- **L8-D-Q-1 (MOD-JS-06: S06-R-11 weight of a distinct time-elapsed licence).** With L7-5-Q-2 (ii) implemented, the pool and treatments reproduce but the weights do not. `TPL-FRANCHISE-LIC` is `distinct` (not `series`), quantity 1, TIME_ELAPSED. S06-R-11 `D18_DEFAULT` gives class D existing `resolve_ssp(at = d, quantity = RQ⁰_p, price = RQ⁰_p × ū_p).selected` = 40,000 for L1-STORE1 (RQ⁰ 1); only class D series takes "the d SSP of the remaining increments". The ruling and the key summary use 39,000 = 40,000 × (1 − 0.025). Measured figures are listed under L7-5-Q-2 (ii). Supervisor to rule whether a class D existing obligation measured by time elapsed weighs (1 − f_p(d)) × the d SSP (S06-R-11 amendment), or another path; no rule was invented.

### Deviations

- L7-5-Q-13: a CHANGE line without quantity_delta counts as quantity_delta 0 (as the state update reads it). The conversion reads the quantity in force from the running state; a key not in force would read 0 (not reached in the corpus).
- L7-5-Q-2 (ii): "existing obligation" is read as the booked lines plus the lines of the modifications before it in (effective date, key order). Two checkpoints implying different answers raise `AnswerKeyError` (not reached).
- L7-5-Q-11: only booked `contract.lines` are candidates; a line the key already overrides with its own `POB_DISTINCT_OVERRIDE` gets none (not reached); the timeline scan is recursive over every event payload (string values and member names).
- Stage 09 S09-R-36 fix: not a named ruling; it is the lane D stop found while making MOD-CHK-112 at-termination and MOD-FS-09 first green at the merge.

### Shared files touched

- `backend/erev_engine/trace.py`: additive `TraceBuilder.value(node_id)` accessor (the encoded value of an emitted node, or None). No other kernel change.
- Not touched: `backend/erev_engine/__init__.py` `_framework_output`, `s10_billing_balances/position.py`, `s10_billing_balances/refund_liability.py`.
- Runner files with additive sections only: `backend/tests/support/answer_keys/runners.py`, `backend/tests/unit/answer_keys/test_runner_engine.py` (section "Engine fix lane D, Level 8").

### Gates

| Gate (head 661434a unless noted) | Result |
|---|---|
| `make answer-keys` release-gate selection (`rg-selection.txt`, 174 ids) | 160 passed, 14 failed (baseline 158 at 0266227; newly passing `REC-S5-UPFRONTFEE-OWN-A`, `REC-S5-UPFRONTFEE-OWN-B`; no new failure) |
| `make parity K="not point_in_time_equivalence"` | OK: 121 of 121 |
| `make lint` | OK |
| `make typecheck` (at aed8a6b; later commits change comments only) | OK |
| `make ci` | OK: backend 2114 passed, vitest 595 passed, 0 failed, 0 skipped |
| `make test-pg` | OK: backend 290 passed, 0 failed, 0 skipped |

Commits: 2aefeb9 (L7-5-Q-5), 204c4e6 (L7-5-Q-12), df8b7d1 (L7-5-Q-13), eb68a00 and aed8a6b (stage 09 S09-R-36 fix for MOD-CHK-112 and MOD-FS-09), 5a00650 (L7-5-Q-2 (ii)), 50fe154 and 661434a (L7-5-Q-11). No Alembic revision in this batch (L7-5-Q-6 is batch 2 or 3).

Failing selection ids at 661434a and their owners:
- `MOD-CHK-112`, `MOD-FS-09-CANCELLATION-REFUND-COMMISSION`: stage 10 S06-R-09 quota lookup, lane L8-E L7-5-Q-2 (i); both pass here with that skip stood in (first green at the merge).
- `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION`: L8-D-Q-1 (S06-R-11 weight).
- Not in batch 1 (lane D batches 2 and 3): `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT` (L7-5-Q-6), `ALC-CHK-032-S4-EX34-CASEC-REJECTED` (Q-7), `ALC-S4-EX35-CASEB` (Q-8), `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION` (Q-9), `ONB-RB-06-RELIEF-GRANT-ROUTED-OUT` (Q-10), `FX-CHK-084-A-REFUND-LIABILITY-REMEASURED` (Q-3), `RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION` (Q-1).
- Lane L8-E: `COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT`, `DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT`, `JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE`, `RND-CHK-003C`.

Targeted tests: `test_runner_engine.py` 36 passed; `test_s09_catch_up_exact.py` 3 passed; `test_tc_je.py` 6 passed; `backend/tests/engine/s06_modifications`, `s08_estimates_late_events`, `s09_recognition` 152 passed.

## Batch 2 (D-88 L7-5-Q-1, Q-3, Q-7, Q-8, Q-10, Q-4 (iii))

Head at the start of the batch: d385012 (selection 160 of 174). The workflow was interrupted with the L7-5-Q-1 change uncommitted; it was reviewed against the amended Q-1 row, adopted unchanged and verified.

### L7-5-Q-1 (stage 09 `returns.unit_rate`; 4515e46)

- `unit_rate(path, ob, d)` = `x_exact ÷ ob.quantity` of the latest `FIXED` segment of `ob` with effective date ≤ d, in segment order (the `s13_books._rates` selection). `path.r` is the fallback only when no `FIXED` segment is in force or Q = 0; `ReturnPath.r` stays the inception publication. Callers unchanged.
- Figures as ruled on the unit world: shipment-month r 200, target 200,000.00; price-protection (TP_CHANGE 2026-05-15, x_exact 188,000.00) r 188, target 188,000.00, trace reproduces.
- Test: `backend/tests/engine/s09_recognition/test_s09_returns.py::test_l8_d_unit_rate_from_the_fixed_segment_in_force`.
- Re-runs: `RET-CHK-029-S3-EX22`, `RET-CHK-060-S3-EX22-REVISED`, `RET-CHK-061-GT08`, `RET-CHK-116`, `RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET`, `SFC-S3-EX26` PASS; `FX-CHK-084-A` unchanged (19 mismatches, Q-3).
- `RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION` no longer raises S09-R-23 ("the returns target lies outside the allocation"); it now stops only on 10 refund-liability subledger lines (FY2026-P03, P05, P06, P08 `REFUND_LIABILITY` 2110 against `CONTRACT_LIABILITY` 2100), lane E under L5-3-Q-7, as the ruling expects.
- Selection 160 of 174, same failures.

### L7-5-Q-3 (stage 09 `returns._billed`; a1fbe31)

- `_billed(ctx, st, contract, ob, d, position)` counts the `BILLING_RECORDED` lines naming `ob` as before, plus `ob`'s S10-R-01 share of each document's unreferenced lines (payload without `obligation_key`): the document total (minor units) is apportioned once by largest remainder over the posted allocations at the document date of the contract's non-VC obligations with the header's contracting entity, else their resolved SSPs. Computed from stage 09's own state (`_attribution_weights`), no s10 import.
- Figures reproduce: march-close E 3, E_b 3, RL 300.00 (functional 336.00), revenue 9,700.00; april-close Y 2, E 1, E_b 1, RL 100.00 (108.00); may-close expired, E 0, revenue_cum 9,800.00.
- Test: `test_s09_returns.py::test_l8_d_billed_counts_the_share_of_an_unreferenced_invoice` (FX-CHK-084-A world, invoice without obligation_key).
- Keys now passing: `FX-CHK-084-A-REFUND-LIABILITY-REMEASURED`. RET re-runs and `SFC-S3-EX26` still pass. Selection 161 of 174, no new failure.

### L7-5-Q-7 (stage 05 `exceptions.residual`; d28381c)

- `residual(..., identified)`: while the candidate's contract is latest `DRAFT` (s02 `timelines`, an accessor like s03 `agent._latest_status`), a range failure raises nothing and the candidate takes R. R ≤ 0 and several candidates still raise; the `CONTRACT_ACTIVATED` step bundle still raises `RESIDUAL_REJECTED` and supplies the checkpoint exception row.
- `test_s05_exceptions.py::test_chk_032_residual_rejected_case_c` restated: the ex_34 world takes `activated=True` (a `CONTRACT_ACTIVATED` event) for both the REQUIRE_ESTIMATED_SSP and BLOCK variants; a DRAFT case asserts no finding and L4-D posted 500 (D = 5.00).
- Figures: activation-refused status_in_book DRAFT, transaction_price 105.00, exception RESIDUAL_REJECTED ERROR on C-EX34/L4-D.
- Re-runs PASS: `ALC-CHK-032-S4-EX34-CASEC-ESTIMATED`, `ALC-CHK-033-S4-EX34-CASEB`, `ALC-CHK-034-S4-EX34-CASEA`, `SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL`.
- Keys now passing: `ALC-CHK-032-S4-EX34-CASEC-REJECTED`. Selection 162 of 174, no new failure.

### L7-5-Q-8 (stage 04 build-up and stage 08 effect; aa11cd2)

- Stage 04 `buildup.royalty_accruals`: a `ROYALTY_ACCRUAL` pin at `at` (before `before`) with `allocation_target = CONTRACT`, on a contract none of whose obligations is measured by `ROYALTY` or `USAGE`, under POL-056 `ACCRUE_ESTIMATE` (resolved at the contracting entity and the period of `at`; the policy is period-scoped), whose `usage_period_end_date` ≤ at and with no royalty statement for that period, enters `vc_constrained` (its `constrained_amount`, else `expected_total_amount`). Node `realised_royalty_accrual:<estimate key>:-` (formula `tp.realised_usage.v1`, input the estimate version member) is a signed input of `vc_constrained_amount`.
- Stage 08 `estimates.apply`: such a version is a reallocating kind; ΔTP routes on the inception basis (`routing._reapportion`) over every obligation. Royalty-component obligations keep S08-R-02.
- Figures reproduce: y-transferred TP 300.00, L1-X 133.33, L2-Y 166.67; january-royalty TP 500.00, L1-X 222.22, L2-Y 277.78, revenue_cum 277.78, billed 500.00, CL 222.22; x-transferred revenue_cum 500.00.
- Tests: `backend/tests/engine/s04_transaction_price/test_s04_buildup.py::test_l8_d_contract_royalty_accrual_enters_vc_constrained`; `backend/tests/engine/s08_estimates_late_events/test_s08_estimates.py::test_l8_d_contract_royalty_accrual_reallocates`.
- Keys now passing: `ALC-S4-EX35-CASEB`. Selection 163 of 174, no new failure.

### L7-5-Q-10 (ONB-RB-06; dd56243)

- (1) Stage 05 `run`: when the group has no obligation, at least one S03-R-11 routed-out line and `allocation_basis.posted = 0`, it returns the allocated state with no obligations and no finding. Σw = 0 with an obligation still raises `TOTAL_SSP_ZERO`.
- (2) Output assembly `_excluded_line_versions` (additive to `_framework_output`): one `obligation_version` row per routed-out draft of stage 03 (`obligation_key`, `scope_flag`, every money column 0, no trace nodes). Deviation, see L8-D-Q-2: published only when the group allocated nothing.
- (3) Stage 10 `position.empty_member_balances` (additive; called from `s10_billing_balances.run`): for a member contract with no obligation, zero member balance targets `contract_liability`, `contract_asset`, `unbilled_receivable` per period end of its contracting entity, plus `accounts_receivable` outside ENGINE mode (in ENGINE mode S10-R-19 publishes it).
- Figures reproduce at grant-received: transaction_price 0.00, out_of_scope 250,000.00, revenue_cum 0.00; L1-GRANT scope_flag CONTRIBUTION_958_605, revenue_cum 0.00; balances CL, CA, UR, AR 0.00; FY2026-P05 lines [].
- Tests: `test_s05_exceptions.py::test_l8_d_every_line_excluded_allocates_nothing`; `backend/tests/engine/s10_billing_balances/test_chk_alg02_alg03.py::test_l8_d_member_contract_without_obligations_publishes_zero_balances` (ERP and ENGINE mode).
- Keys now passing: `ONB-RB-06-RELIEF-GRANT-ROUTED-OUT`. Selection 164 of 174, no new failure.

### L7-5-Q-4 (iii) (stage 08 concession producer; abd95bd)

- `estimates._concession_quotas`: a `VARIABLE_CONSIDERATION` version with `allocation_target = OBLIGATIONS`, `vc_element_type` DISCOUNT or SLA_CREDIT and no `refund_liability_target` parameter, whose negative share goes to an obligation with φ = 1 at d (`target_at_position(..., inclusive=True).complete`), adds `refund_components[subject] += Quota(−exact, −delta)` (stage 06's CREDIT_OR_REFUND convention).
- Test: `test_s08_estimates.py::test_l8_d_targeted_concession_on_a_satisfied_obligation_adds_a_refund_quota` (satisfied receiver adds Quota(60, 6000); unsatisfied receiver and a `refund_liability_target` add none).
- Measured on `VC-CHK-113-TC-POBVC-16` (out of the selection per D-88 Q-4): the producer receives `Contract 2/VC-CONC-2@v1` on EV-000015 (2023-11-15), share −6,000 on POB #2, φ = 1, and adds Quota(60, 6000). Stage 10 `_concessions` consumes it but `_concession_event` dates it at the latest MODIFICATION boundary `Contract 2/EV-000008` (2023-05-31), so the 7 mismatches are unchanged on this branch. First green at the merge with lane L8-E's TP_CHANGE acceptance in `_concession_event`.
- `RND-CHK-003C` has no ESTIMATE_CHANGED; its 10 mismatches are the lane E Q-4 (i)/(ii) flows. `RND-CHK-003C-USD-NEGATIVE-CREDIT-MEMO-APPORTIONMENT` PASS. `MOD-CHK-112` stops at the stage 10 S06-R-09 quota lookup (lane E L7-5-Q-2 (i)), as before.
- Selection 164 of 174, same failures.

### Spec questions

- **L8-D-Q-2 (L7-5-Q-10 (2): excluded-line obligation rows and platform persistence).** Publishing one `obligation_version` row per S03-R-11 excluded line in every group conflicts with the platform: `erev_api/domain/contracts/computation.py` `require_lineage` refuses any row without SSP lineage (CTL-011: `ssp_book_version_key`, `ssp_entry_key`, `original_ssp_selected` are None for an excluded line), and the insert loop raises "names no obligation row" because the platform creates no obligation for an excluded line. `backend/tests/api/test_contracts_api.py::test_out_of_scope_line_removed_from_price` books a GUARANTEE_460 line beside obligations and must keep passing. The engine publishes the rows only for a group that allocated nothing (ONB-RB-06). Supervisor to rule whether excluded-line rows are published for every group (with a platform amendment to CTL-011 and the insert loop, outside lane D), or only for all-excluded groups as built. The platform path for an all-excluded group is not exercised by any platform test.

### Deviations

- L7-5-Q-3: only `BILLING_RECORDED` lines count (credit memos stay outside `_billed`, as before); an unreferenced line repeated with the same (invoice_number, line_external_id) counts once (S10-R-07 status update); a document whose weights sum to 0 contributes no share (stage 10 owns the S10-R-01 invariant).
- L7-5-Q-8: a statement is a `USAGE_REPORTED` of the contract with `is_royalty_statement` true and `usage_period_end` equal to the accrual's `usage_period_end_date`, preceding the position; the stage 04 standalone trace of `price_at` cites stage 03 nodes, so the unit test checks the accrual node and its citation instead of `reevaluate` (the key run re-evaluates the full trace).
- L7-5-Q-10 (2): see L8-D-Q-2.

### Shared files touched

- `backend/erev_engine/__init__.py` `_framework_output`: one additive line calling the new `_excluded_line_versions` (Q-10 (2)).
- `backend/erev_engine/stages/s10_billing_balances/position.py`: additive `empty_member_balances` and the `AllocatedState` import (Q-10 (3)).
- `backend/erev_engine/stages/s10_billing_balances/__init__.py`: `member_balances` extended with `position.empty_member_balances` (Q-10 (3)).
- `backend/tests/engine/s10_billing_balances/test_chk_alg02_alg03.py`: one added test.
- Not touched: `s10_billing_balances/refund_liability.py`.

### Gates (batch 2)

| Gate (head abd95bd unless noted) | Result |
|---|---|
| `make answer-keys` release-gate selection (`rg-selection.txt`, 174 ids) | 164 passed, 10 failed (batch 1 end 160; newly passing `FX-CHK-084-A-REFUND-LIABILITY-REMEASURED`, `ALC-CHK-032-S4-EX34-CASEC-REJECTED`, `ALC-S4-EX35-CASEB`, `ONB-RB-06-RELIEF-GRANT-ROUTED-OUT`; no new failure after any ruling) |
| `make parity K="not point_in_time_equivalence"` | OK: 121 of 121 |
| `make lint` (with this evidence) | OK |
| `make ci` (typecheck stage in the ci run: OK) | OK: backend 2121 passed, vitest 595 passed, 0 failed, 0 skipped |
| `make test-pg` | OK: backend 290 passed, 0 failed, 0 skipped |

Commits: 4515e46 (L7-5-Q-1), a1fbe31 (L7-5-Q-3), d28381c (L7-5-Q-7), aa11cd2 (L7-5-Q-8), dd56243 (L7-5-Q-10), abd95bd (L7-5-Q-4 (iii)). No Alembic revision in this batch (L7-5-Q-6 is batch 3).

Failing selection ids at abd95bd and their owners:
- `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT` (L7-5-Q-6) and `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION` (L7-5-Q-9): lane D batch 3.
- `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION`: L8-D-Q-1 (S06-R-11 weight).
- `MOD-CHK-112`, `MOD-FS-09-CANCELLATION-REFUND-COMMISSION`: stage 10 S06-R-09 quota lookup, lane L8-E L7-5-Q-2 (i) (first green at the merge).
- `RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION`: refund-liability lines only, lane L8-E L5-3-Q-7 (L7-5-Q-1 done here).
- `RND-CHK-003C`: lane L8-E L7-5-Q-4 (i), (ii) and the L7-6 flows.
- `COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT`, `DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT`, `JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE`: lane L8-E.
- Outside the selection: `VC-CHK-113-TC-POBVC-16` (D-88 L7-5-Q-4), producer done here, first green at the merge for its after-concession checkpoints.

Targeted tests: `backend/tests/engine/s04_transaction_price` and `s08_estimates_late_events` 56 passed; `s05_allocation` and `s10_billing_balances` 94 passed; `s08_estimates_late_events` and `s09_recognition` 89 passed.

## Batch 3 (D-88 L7-5-Q-6, Q-9)

Head at the start of the batch: b31b24a (selection 164 of 174). Main had not moved (0266227).

### L7-5-Q-6 (transaction price net of routed-out leases; revision 0054; 5004fa7)

- Baseline: `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT` first-month and year-1 `transaction_price` 108,000.00 against 27,000.00 (2 mismatches).
- Output assembly `_contract_version`: `transaction_price` = `total.posted` (after the returns-memo adjustment) − Σ `a_posted` of the routed-out `LEASE_842` obligations over their segments in force at the version date (`_routed_out_lease_allocation`). When a lease is deducted the column no longer cites the version-state `transaction_price` node. `fixed_consideration`, `out_of_scope_amount`, `transaction_price_buildup`, the allocation pool and P1 are unchanged.
- `_assert_allocation` IDENTITY_PRICE (DB-17 V1): Σ `allocated_amount` over the rows with `scope_flag = IN_SCOPE_606` = `transaction_price − consideration_payable_amount`. IDENTITY_BASIS (S04-R-02) still sums every row.
- Answer-key runner DG-AK-54 IDENTITY_PRICE (`runners.py` identities): the same filter. A row without the column takes the T-CON-11 default `IN_SCOPE_606`, because the stub book of `test_runner_engine.py::test_expect_problem_leaves_state_unchanged` publishes no `scope_flag`.
- Revision 0054 (`backend/erev_api/db/migrations/versions/0054_db_17_v1_in_scope_allocation.py`, down_revision 0053, chained on main's head): `CREATE OR REPLACE` of `erev.tg_contract_version__allocation()` adds `AND o.scope_flag = 'IN_SCOPE_606'`. downgrade() restores the 0039 body. Grants, the deferred constraint trigger and the `EREV-ALC-001` message are unchanged; the function count stays 75. The 04 DB-17 V1 amendment is the supervisor's.
- Head pins: `backend/tests/pg/test_migrations.py::test_single_head` 0054 (plus the function-history comment) and `backend/tests/api/test_me.py` `schema_revision` 0054.
- Figures reproduce as ruled and the key passes: first-month TP 27,000.00, out_of_scope 81,000.00, L2-SERVICE allocated 27,000.00, revenue_cum 750.00, billed 2,250.00, CL 1,500.00, FY2026-P01 2100 Dr / 4010 Cr 750.00; year-1 revenue_cum 9,000.00, billed 9,000.00, CL 0.00.
- Test: `backend/tests/engine/s05_allocation/test_s05_allocation.py::test_l8_d_routed_out_lease_leaves_the_transaction_price`. It runs the CHK-118 world through `compute`: the lease row LEASE_842 is allocated 7,500.00 and maintenance IN_SCOPE_606 2,500.00; fixed 10,000.00; out_of_scope 7,000.00 (the line has no `out_of_scope_amount`); transaction_price 2,500.00; the in-scope sum ties; no `transaction_price` citation.
- Re-runs:
  - `ALC-CHK-118` PASS (7,500.00 / 2,500.00, total_ssp 12,000).
  - `REC-S5-EX62-CASEB` PASS.
  - `backend/tests/api/test_contracts_api.py::test_out_of_scope_line_removed_from_price` 1 passed on the migrated database.
  - `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"` OK, 3 passed.
  - `s05_allocation`, `kernel/test_ctl_012_compute.py` and `unit/answer_keys/test_runner_engine.py`: 48 passed.
- Keys now passing: `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT`. Selection 165 of 174, no new failure.

### L7-5-Q-9 (IFRS15 business-combination build-up; c8db6eb)

- Baseline: every checkpoint raised `ENGINE_INVARIANT_VIOLATED` IFRS15 "S04-R-02 sum a_posted = allocation_basis" (Σ a_posted 90,000.00 against 240,000.00).
- `s07_onboarding/business_combination.ifrs_fair_value` → `_fair_value_price` appends one `TpBuildUp` to `tp_history`:
  - `at` is the event date and `before_event_key` the next event; fixed = total = allocation_basis = V (exact 90,000, posted 9,000,000); every other member 0; elements ().
  - Nodes, under the group subject: `fixed_consideration@<event key>` (`tp.fixed.v1`, input the payload member `fair_value_contract_liability`), then `transaction_price@<event key>` and `tp_allocation_basis@<event key>` (`tp.buildup.v1`, signs +).
  - The ASC606 book is unchanged.
- Stage 13 `_trace_boundary_price` re-measures the price over the booking lines (240,000.00). That differs from the appended entry, so stage 13 traces nothing and the stage 07 nodes stand; no stage 13 change.
- Test: `backend/tests/engine/s07_onboarding/test_s07_rules.py::test_l8_d_ifrs_fair_value_appends_the_price_buildup`. ASC606 appends nothing. In IFRS15 the members are as above, Σ a_posted = 90,000.00, and the three nodes re-evaluate and cite the payload member. `s07_onboarding`, `s13_books` and `kernel` engine tests: 161 passed.
- Measured further stop, as the supervisor call directs. After the change ONB-CHK-121 computes every checkpoint with 12 mismatches, all in balances and journal lines:
  - january-2026-asc606:
    - balance CL FY2026-P01 0.00 (key 110,000.00);
    - FY2026-P01 CONTRACT_ASSET 1200 Dr 130,000.00 (key: no line);
    - CONTRACT_LIABILITY 2100 Cr 120,000.00 where the key lists Dr 10,000.00;
    - lines at origin FY2025-P12: CONTRACT_LIABILITY 2100 Dr 120,000.00 and REVENUE 4010 Cr 120,000.00 (key: none).
  - year-end-2026-asc606: FY2026-P12 CONTRACT_ASSET Dr 10,000.00 where the key lists CONTRACT_LIABILITY Dr 10,000.00.
  - january-2026-ifrs15 and year-end-2026-ifrs15: CL 0.00 at January (key 82,500.00), and CONTRACT_ASSET Dr 7,500.00 where the key lists CONTRACT_LIABILITY Dr 7,500.00 (FY2026-P01 and FY2026-P12).
  - `cutover-no-postings` passes, and obligation `revenue_cum` matches in all four other checkpoints (130,000.00 / 240,000.00 / 7,500.00 / 90,000.00).
  - Inference, not measured stage by stage: the opening baseline `billed_cum` (240,000.00 ASC606, 90,000.00 IFRS15) does not enter the stage 10 position, and stage 14 posts the pre-cutover opening revenue into the first open period. These are opening-balance flows of stages 10 and 14, not TpBuildUp invariants. Per the D-88 supervisor call, ONB-CHK-121 moves post-rc with ENB-9; no rule was invented.
- Keys now passing: none. Selection 165 of 174, no new failure.

### Release-gate failures in lane D stages

- `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT`: passes (L7-5-Q-6).
- `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION`: measured stop recorded under L7-5-Q-9; post-rc with ENB-9.
- `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION`: 12 mismatches, unchanged; L8-D-Q-1 (S06-R-11 weight) has no ruling in D-89, so there is nothing to implement (schedule-revised L1-STORE1 allocated 55,500.00 against 54,810.13, revenue_cum 1,465.81 against 1,459.92).
- Every other failing id belongs to lane L8-E (list under Gates).

### Spec questions

- No new question. L8-D-Q-1 (S06-R-11 weight) and L8-D-Q-2 (excluded-line rows) have no ruling in D-89 and stay open.

### Deviations

- L7-5-Q-6: "a_posted at the version date" is read as Σ `a_posted` of each LEASE_842 obligation's segments in force per component (`_current`, the selection of the obligation row without measures). The `transaction_price` trace-node citation is dropped when a lease is deducted. The runner treats a row without `scope_flag` as `IN_SCOPE_606`.
- L7-5-Q-9: the build-up's `at` and `before_event_key` follow stage 06's price after a boundary. Stage 07 `FORMULA_IDS` (Table 0.10-A row 07) is not extended with `tp.fixed.v1` and `tp.buildup.v1`, because no registry check covers stage 07 and the stage 13 memo formula list stays unchanged. Not reached in the corpus, since only ONB-CHK-121 carries `fair_value_contract_liability`: a later reallocating boundary would re-price from the booking lines and replace V; and if that price ever equalled V, stage 13 would emit the same node ids a second time.

### Shared files touched (batch 3)

- `backend/erev_engine/__init__.py`: `_contract_version` (additive deduction block), new `_routed_out_lease_allocation` and `_IN_SCOPE`, `_assert_allocation` IDENTITY_PRICE filter. `_framework_output` not touched in this batch.
- `backend/tests/support/answer_keys/runners.py`: DG-AK-54 IDENTITY_PRICE filter.
- `backend/erev_api/db/migrations/versions/0054_db_17_v1_in_scope_allocation.py`: the level's one Alembic revision.
- `backend/tests/pg/test_migrations.py`, `backend/tests/api/test_me.py`: head pins.
- `backend/erev_engine/stages/s07_onboarding/business_combination.py` (not a lane D stage; assigned by the ruling), `backend/tests/engine/s07_onboarding/test_s07_rules.py`, `backend/tests/engine/s05_allocation/test_s05_allocation.py`.
- Not touched: `s10_billing_balances/position.py`, `s10_billing_balances/refund_liability.py`.

### Gates (batch 3)

| Gate (head c8db6eb) | Result |
|---|---|
| `make answer-keys` release-gate selection (`rg-selection.txt`, 174 ids) | 165 passed, 9 failed (batch 2 end 164; newly passing `ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT`; no new failure after either ruling) |
| `make test-pg K="test_single_head or test_upgrade_downgrade_upgrade or test_lint_after_upgrade"` (at the Q-6 change) | OK: 3 passed |
| `make parity K="not point_in_time_equivalence"` | OK: 121 of 121 |
| `make lint` (with this evidence) | OK |
| `make typecheck` | OK (558 source files) |
| `make ci` | OK: backend 2123 passed, vitest 595 passed, 0 failed, 0 skipped |
| `make test-pg` | OK: backend 290 passed, 0 failed, 0 skipped |

Commits: 5004fa7 (L7-5-Q-6, with revision 0054, the level's one Alembic revision), c8db6eb (L7-5-Q-9).

Failing selection ids at c8db6eb and their owners:
- `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION` (12 mismatches): L7-5-Q-9 implemented; the measured further stop is the stage 10 and 14 opening-balance flows. Post-rc with ENB-9 per the supervisor call, for the supervisor to take out of the rc selection.
- `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION` (12 mismatches): L8-D-Q-1 (S06-R-11 weight), unruled.
- `MOD-CHK-112`, `MOD-FS-09-CANCELLATION-REFUND-COMMISSION`: stage 10 S06-R-09 quota lookup, lane L8-E L7-5-Q-2 (i) (first green at the merge; batch 1).
- `RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION` (10 mismatches): refund-liability lines, lane L8-E L5-3-Q-7.
- `RND-CHK-003C` (10 mismatches): lane L8-E L7-5-Q-4 (i), (ii).
- `COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT` (4), `DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT` (2), `JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE` (1): lane L8-E.
