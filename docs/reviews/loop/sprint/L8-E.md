# Sprint L8, lane E (engine fix lane E: stages 10 to 14, the bundle and the journals summaries)

Builder evidence for Level 8 remediation, worktree `~/dev/erev-wt/l6` (branch `sprint/l6`). Step 0: `git merge --ff-only main` (0266227), then `make setup`, both OK.

## Batch 1

Rulings: D-88 L7-5-Q-2 (i), D-88 L7-6-Q-5, D-89 L7-6-Q-7 and D-89 L7-6-Q-9. Every ruling first had a unit test that failed on the old code, then the fix, the affected keys, the release-gate selection (`docs/reviews/loop/sprint/rg-selection.txt`, 174 ids) and a commit.

Baseline at 0266227 (measured before the first fix): selection 158 of 174, the 16 failing ids of `L7-merge.md`.

### D-88 L7-5-Q-2 (i): MOD-FS-09 termination refund key (commit a804536)

- Root cause: stage 10 `refund_liability._concessions` read the stage 06 key `<contract subject>#TERMINATION@<event key>` (S06-R-21) as an obligation subject key. It raised S06-R-09 for `FS-09#TERMINATION@FS-09/EV-000007`.
- Fix: `_concessions` skips a key of that form. The mark `#TERMINATION@` is matched as a constant in `refund_liability.py`, not imported (DG-ENG-07). `_terminations` still creates the component from the event. Any other key that names no obligation still raises S06-R-09.
- Test: `tests/engine/s10_billing_balances/test_chk_alg06.py::test_l8_e_termination_refund_quota_is_not_a_concession`. It checks one TERMINATION component of 300.00, refund liability 0 / 300.00 / 300.00, and S06-R-09 for `K-01/P9`. It also checks S06-R-09 for a termination-form key naming an event the state does not hold.
- MOD-FS-09: every checkpoint figure of the ruling now passes: termination balances, the FY2027-P03 and FY2027-P04 subledger, and billed 120,000.00 with RL 0.00 after the credit memo. The key still fails on 18 DG-AK-54 trace mismatches only (L8-E-Q-1).
- Selection: 158 of 174. No id newly fails.
- Deviation (strictness): the skip needs the event key after the mark to name a `CONTRACT_TERMINATED` event of the state. A key of the termination form with no such event stays fail-closed (S06-R-09). Without such an event, `_terminations` creates no component, and skipping the key would drop the refund quota silently.

### D-88 L7-6-Q-5: K_t without `constrained_amount` (commit 404714a)

- Root cause: the derived branch took K_t from the version's `constrained_amount` only. A REBATE, PRICE_PROTECTION, REFUND or VOLUME_TIER pin without it therefore published 0.
- Fix: `refund_liability._constrained_reduction`. K_t = |posted amount| of the `VcElementView` whose `(estimate_key, version_key)` is the pin in force. It is read from the latest `AllocatedState.tp_history` build-up with `at` ≤ t; on equal dates the later build-up wins. When no build-up names the version, K_t = |`constrained_amount`|, else 0. Input 0 of the `rl.vc_target.v1` excess node cites the estimate version with detail member `vc_constrained` and value K.
- Test: `tests/engine/s10_billing_balances/test_s10_vc_refund_liability.py::test_l8_e_k_is_the_stage_04_constrained_reduction_without_constrained_amount`.
  - World: VC-S3-EX24 with version 2 as REBATE, MOST_LIKELY_AMOUNT scenarios {5,750.00 at 0.6; 0.00 at 0.4} and no `constrained_amount`.
  - Result: RL(30 June) 5,750.00; the node's input 0 is {member `vc_constrained`, value 5750.00}. The old code gave RL 0.
- Keys: VC-S3-EX24, JE-CHK-025, RET-WM-04, VC-BR-02 and VC-RB-04 pass. The D-87 figures stand.
  - RET-BR-03 still stops on "the returns target lies outside the allocation" (L7-6-Q-3; lane D).
  - VC-FS-02 (not in the selection) stops before stage 10 on ACCOUNT_MAPPING_MISSING (CV-15).
- Selection: 158 of 174, same failures.
- The same commit restores `test_chk_alg06.py` imports to the project isort order (`ruff --config backend/pyproject.toml`). The first commit had been formatted without the project config.

### D-89 L7-6-Q-9: ENGINE-mode `billed_cum` from the unconditional date (commit 5e73242)

- Root cause: `_Emitter.billed` counted every invoice line from its effective date. An ENGINE-mode cancellable invoice therefore gave version `billed_cum` 1,000.00 while memo-only (JE-CHK-024 Case A).
- Fix, part 1 (`classification.py`): `Line.unconditional_source`.
  - The line's own event when the unconditional date is its effective date. Credit-memo lines, ERP-mode lines and noncancellable lines also take their own event.
  - Else the payment or status update that sets the S10-R-06 date: the earliest by (effective date, order key).
  - None while memo-only.
- Fix, part 2 (`billing.py`):
  - `_counted`: a credit memo counts by ENG-06 position; an invoice line counts from its unconditional date. `in_position` is not applied (S10-R-04 stands).
  - `billed()` counts the counted lines.
  - Unreferenced shares use `_restricted` over the counted lines. When only part of a document is counted, the share is a new node `billed_attributed@<document>@<latest unconditional date>` under `bil.attribution.v1` mode `apportion`, cached per subject.
  - `_billed_before` counts a line whose source order key precedes the boundary.
  - `billed_amount` = the restricted share of the lines counted at d_v, less the restricted share of the counted lines whose source is not new.
- Tests (`tests/engine/s10_billing_balances/test_s10_billing.py`):
  - `test_s10_r06_erp_and_engine_modes`: amended as ruled (P01 to P03 give 0 / 0 / 1,000.00; ERP-mode P01 gives 1,000.00; status-update P01 gives 0).
  - New `test_l8_e_engine_billed_cum_counts_from_the_unconditional_source`:
    - sources: payment, invoice's own event, None;
    - `billed_amount`: 1,000.00 when the payment is new and 0 when it is not;
    - PROSPECTIVE boundary: `remaining_billing` 0 in ENGINE mode (the payment follows the boundary) and 1,000.00 in ERP mode.
- Keys: JE-CHK-024 Case A now passes. Case B, JE-CHK-023, POS-CHK-013 (engine billing) and VC-RB-04 still pass.
- Selection: 159 of 174. JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE newly passes; none newly fails.
- Engine tests, stages 10 to 15: 230 passed.
- Deviation:
  - `_billed_before` now tests each line's source order key. Before, the whole document tested its first line's order key.
  - In ERP mode the two differ only when a PROSPECTIVE boundary event sorts between the lines of one document.

### D-89 L7-6-Q-7: renewal segment date and run-off of remaining costs (commit df48155)

- Root cause 1: `_renewal_change` started a RENEWAL_EXPECTATION segment on the effective date. Version 2, effective 30 June, re-based June: amortisation 142.73 and impairment 20,690.60.
- Root cause 2: `_test` kept remaining costs at the EAC when no PROGRESS_INPUT cost existed. The July recoverable amount of −5,000.00 impaired the whole 4,166.67.
- Fix 1: the segment starts on max(effective date + 1 day, amortisation start). Its base is the carrying amount after amortisation through the day before the start.
- Fix 2: `capitalise.has_progress_input`. Without a PROGRESS_INPUT cost of the related obligations (or of none) effective by t, costs = Σ cumulative_posted(eac_v, g_v) over the latest EAC versions (`impair._run_off`).
  - g_v = (C_t − C_0) ÷ (A_t − C_0), capped to [0, 1], and 1 when A_t = C_0. C is the related obligations' posted revenue target of the latest period end on or before the date; A is their posted allocation.
  - `cost_recoverable` gains params `costs_basis` (`progress` or `run_off`) and `progress`. `cost.recoverable.v1` still re-reads `costs`.
  - `_eac` returns the version objects.
- Tests (`tests/engine/s11_costs_loss/test_s11_costs.py`):
  - `test_s11_r05_renewal_expectation_prospective`: version 2 re-dated to 30 June. Every figure is kept: CostSegment(1 Jul 2026, 31 Dec 2028, 9,000.00, PERIOD_CHANGE); July 300.00; December 4,800.00 / 7,200.00; 24 months.
  - New `test_l8_e_renewal_fall_runs_off_the_remaining_costs` (the COST-CAP world):
    - June: line 833.33, impairment 20,000.00, carrying 5,000.00, recoverable 5,000.00 with costs basis `run_off`;
    - P07 to P11: recoverable equals carrying and `impaired_cum` stays 20,000.00 each month;
    - July: costs 9,166.67 at progress 1/6;
    - December: amortised 10,000.00, carrying 0, recoverable 0.00;
    - with a 9,000.00 PROGRESS_INPUT cost on 31 July: costs basis `progress`.
- Keys: COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT now passes. COST-S8 EX1, EX2, EXPEDIENT and IMPAIRMENT, JE-CHK-130 and both JE-CHK-131 keys still pass.
- Ruling (c) measured: the JE-CHK-131 IMPAIRMENT-AND-IFRS15-REVERSAL ASC606 checkpoint gives P03 recoverable 12,500.00 (costs 87,500.00 run-off) and P04 0.00. No checkpoint asserts them.
- Selection: 160 of 174. COST-CAP newly passes; none newly fails.
- Engine tests, stages 10 to 15: 231 passed.
- Deviations:
  - The version-key assertion of `test_s11_r05` changes with the ruled re-dating. Version 2 is in force at the June test, so the assertion reads May v1, June v2 and December v2.
  - C_0 at a mid-period effective date is the revenue target of the latest period end on or before it. Stage 11 holds period-end revenue targets only, as `amortise._progress` does.

### Shared files touched (batch 1)

- None of the named shared sites. `backend/erev_engine/__init__.py` `_framework_output` and `stages/s10_billing_balances/position.py` were not edited.
- Lane E files edited:
  - `stages/s10_billing_balances/refund_liability.py`, `billing.py` and `classification.py`;
  - `stages/s11_costs_loss/impair.py` and `capitalise.py`;
  - tests under `tests/engine/s10_billing_balances/` and `tests/engine/s11_costs_loss/`.
- No Alembic revision. Not touched: PROGRESS.md, other documents, key files and golden expected values.

### Gates (batch 1, build df48155)

- Release-gate selection (`rg-selection.txt`, 174 ids): 160 of 174. The baseline was 158. JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE and COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT newly pass; none newly fails. The 14 failing ids:
  - ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT, ALC-CHK-032-S4-EX34-CASEC-REJECTED, ALC-S4-EX35-CASEB;
  - DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT;
  - FX-CHK-084-A-REFUND-LIABILITY-REMEASURED;
  - MOD-CHK-112, MOD-FS-09-CANCELLATION-REFUND-COMMISSION (L8-E-Q-1), MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION;
  - ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION, ONB-RB-06-RELIEF-GRANT-ROUTED-OUT;
  - REC-S5-UPFRONTFEE-OWN-A, REC-S5-UPFRONTFEE-OWN-B;
  - RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION;
  - RND-CHK-003C.
- `make parity K="not point_in_time_equivalence"`: 121 of 121 (df48155).
- `make lint`: OK. `make typecheck`: OK (557 source files).
- `make ci` (gate slot 2): OK. Backend 2113 passed, vitest 595 passed, 0 failed, 0 skipped.
- `make test-pg` (gate slot 2): OK. Backend 290 passed, 0 failed, 0 skipped.

### Spec questions

- **L8-E-Q-1 (MOD-FS-09 catch-up trace after the termination).** With L7-5-Q-2 (i) in, MOD-FS-09 passes every checkpoint figure. It fails on 18 DG-AK-54 `reevaluate(trace)` mismatches at checkpoints `termination` and `credit-memo`:
  - The stage 09 nodes `catch_up_amount`, `catch_up_cum` and `catch_up_modification_cum:FS-09/L1-SUB:-` publish 0.00 (Σ `CausePoint.delta`).
  - They cite the stage 06 node `catch_up@FS-09/EV-000007:FS-09/L1-SUB:-` (`mod.catch_up.v1`, cause TERMINATION, a_before 192,000.00, a_after 120,000.00, base 112,000.00, value 8,000.00). `rec.catch_up.sum.v1` therefore re-evaluates them to 8,000.00.
  - The stage 09 boundary delta of the termination event (segment target after − before at its position) is 0, while stage 06 measures 8,000.00. The 8,000.00 FY2027-P03 revenue credit of the ruling does post.
  - Owner outside lane E: stage 09 `decompose.emit_catch_up_measures` or the stage 06 TERMINATION producer (lane D's `_terms_conversions`, L7-5-Q-13). Supervisor to route. Candidates: stage 09 takes the cited node's posted value as the point delta; or stage 06 emits no `catch_up@` node for the REMOVE conversion.

## Batch 2

Rulings: D-88 L7-5-Q-4 (i), (ii) and the lane E part (1) to (3), plus the s10 half of (iii); D-89 L7-6-Q-8. Resumed at 1fc5367; stale PID files under `.run/l8b1` were dead. Each ruling first had tests that failed on the old code, then the fix, the affected keys, the release-gate selection (`rg-selection.txt`, 174 ids) and a commit. Scratch and logs: `.run/l8b2/`.

Baseline at 1fc5367: selection 160 of 174 (the 14 failing ids of batch 1). RND-CHK-003C failed on 10 FY2026-P02 subledger mismatches: REVENUE Dr 66.68 / 66.66 / 66.66, a CONTRACT_LIABILITY Dr 100.00 line with Cr 33.34 / 33.33 / 33.33 per POB, and REFUND_LIABILITY Cr 33.34 / 33.33 / 33.33 per POB. MOD-CHK-112 stops in stage 06 (`MOD-TERM ... S06-R-21`, lane D).

### D-88 L7-5-Q-4: concession relief, JET-04b netting by cause, concession flows (commit 48e5cac)

- Root causes:
  - Stage 13 `_relief_targets` bound relief = `revenue_cum` only, while s10 `position.py` adds `Refunds.concession_total`.
  - Stage 14 `_refund_liabilities` indexed the JET-05c created amounts by (entity, obligation, period). The JET-04b target is keyed by component key, so a concession never netted and posted Dr CL / Cr RL beside JET-05c.
  - Stage 13 `_monetary_flows` bound a CONCESSION component's balance movements with control DEBIT.
- Fix:
  - (1) `s13_books._relief_targets(..., concessions)`: relief(o, t) = `revenue_cum` (or max(G_t, R_t)) + Σ `concession_created_cum` on o at t, in both the same-entity and the cross-entity branch. The target keeps the revenue node. The stage 14 relief part (`_relief`) cites the revenue node and each concession node in `value_inputs` and `node_ids` (L8-E-Q-3).
  - (2) s10 `refund_liability.measure`: every `concession_created_cum` Target has `cause` = component key. s14 `_refund_liabilities` indexes created amounts by (entity, cause, period) and nets a CONCESSION JET-04b part where `target.subject_key == cause`. A concession target without a cause raises. JET-05c parts stay per obligation. A netted foreign part still takes no functional amount, so it still fails closed.
  - (3) `s13_books._concession_flows`: per CONCESSION component, the creation is an INCREASE of `created_amount` at the first balance target's period end with `control=None`, source `<component>@<period>`. The consumption is a DECREASE of each period's movement of Σ consumed (created − balance), control CREDIT, source `<component>@<period>#consumed`, so it sorts after the creation on one date. A falling consumption raises S10-INV-07. Other kinds are unchanged.
  - (iii), s10 half: `_concession_event` takes the settled CONTRACT_AMENDED, else the latest MODIFICATION boundary, else the latest TP_CHANGE boundary. A MODIFICATION boundary still wins. The s08 producer is lane D's.
- Tests:
  - `tests/engine/s10_billing_balances/test_s10_position.py::test_l8_e_concession_cause_relief_and_monetary_flows` (EX-10-A world). Concession causes = component key; `revenue_cum` P3 FY2026-P02 500.00; relief P3 1,000.00 / 1,000.00 / 1,000.00; flows INCREASE 500.00 on 28 Feb (control None) and DECREASE 500.00 on 31 Mar (control CREDIT). The old code gave cause None.
  - `test_l8_e_concession_event_accepts_a_tp_change_boundary`: a TP_CHANGE ESTIMATE_CHANGED boundary is returned, and a later MODIFICATION boundary wins. The old code raised S10-R-13.
  - `tests/engine/s14_posting/test_s14_templates.py::test_l8_e_jet_04b_nets_the_concession_of_its_own_component`: component A (created 50.00, balance 20.00) posts JET-04b −30.00; component B posts 30.00 un-netted; JET-05c 50.00; the February relief part cites `revenue_relief_cum` and `concession_created_cum#A`.
  - Adjusted to the ruled keying: `test_s14_r02_jet_05b_through_revenue_relief` (component-keyed refund target and concession cause; row order; the part slice [2:4]) and `tests/properties/test_prop_p05_journal_balance.py`. Their faked relief nodes hold `revenue_cum` alone and the relief targets include the created amounts.
- Keys:
  - RND-CHK-003C-USD-NEGATIVE-CREDIT-MEMO-APPORTIONMENT still passes.
  - RND-CHK-003C drops from 10 mismatches to 4. REVENUE Dr 33.34 / 33.33 / 33.33 now match, and no CONTRACT_LIABILITY or JET-04b line posts. REFUND_LIABILITY posts per obligation instead of one Cr 100.00 line (L8-E-Q-2).
  - MOD-CHK-112 still stops in stage 06 (lane D).
  - VC-CHK-113 is outside the selection; it waits for lane D's s08 producer at the merge.
  - The S12-INV-03 layer ties hold for RND-CHK-003C: stage 12 raises no invariant.
- Selection: 160 of 174. None newly passes; none newly fails.
- Engine suites (stages 10 to 14 and properties, `HYPOTHESIS_PROFILE=ci`): 208 passed.
  - Under the default Hypothesis profile, `test_p12_fx_layers` once found a case with average rate 1E-12 (functional 518160 vs 518161). It passes under the ci profile.
  - Neither stage 12 nor P12 changed in this batch, so the finding is not caused by this change.

### D-89 L7-6-Q-8: LEGACY JET-15 as Dr PRE_STANDARD_REVENUE / Cr CONTRACT_LIABILITY; DELTA = primary + LEGACY (commit b1886ec)

- Root cause: JET-15 mirrored the ERP (Dr CL / Cr PRE), and every DELTA read negated the LEGACY lines.
- Fix, in one commit:
  - `templates.py` JET-15 debit PRE_STANDARD_REVENUE, credit CONTRACT_LIABILITY;
  - `legacy_book.py` docstring;
  - `summarise.py` DELTA LEGACY lines `sign=1` and docstrings;
  - `views.py` `signs[LEGACY] = 1` and docstring;
  - `tests/support/intent_totals.py` `{LEGACY: 1}` and docstring;
  - `tests/support/worlds.py::post_pre_standard` seeds CL −66.00 / −88.00 and PRE +66.00 / +88.00;
  - `test_chk_delta.py::test_chk_020_january_delta` asserts [(POB #2, C, CL, 21001, 66.00), (POB #2, D, PRE, 5002, 66.00), (POB #3, C, CL, 21001, 88.00), (POB #3, D, PRE, 5003, 88.00)]. The `lines` helper sorts, so side C precedes D. The DELTA by_account figures and 240.22 are unchanged;
  - `test_s13_legacy.py`: EX-13-A LEGACY lines [D PRE 1,200.00; C CL 1,200.00], DELTA = primary + LEGACY with figures unchanged; the March reduction {PRE −200.00, CL +200.00}.
- Extra sites in the same commit, beyond the ruling's list:
  - `erev_api/domain/journals/queries.py` (line drill of a DELTA run) `sign=1`. `grouping_key` does not read the sign, so the drill does not change.
  - `summarise.py` orders lines by (book is LEGACY, chain_seq, id), not by −sign, so primary lines still precede LEGACY lines.
  - `test_s14_templates.py::test_jet_parts_cover_policies_templates` no longer swaps the JET-15 sides. The part now posts Table 14-A's sides.
- Tests before the fix: `test_ex_13_a_delta_identity`, `test_s13_inv_02_no_revenue_in_legacy` and `test_chk_020_january_delta` failed on the old sides.
- After the fix: stages 13 and 14, `tests/domain/journals`, `tests/domain/reports/test_legacy_reports.py`, `tests/unit/parity` and `tests/unit/reports/test_catalogue.py`: 192 passed. These include `test_summarise.py::test_delta_run_january_2023_chk_020` and `test_legacy_views.py::test_tc_je_02_january_delta`.
- Parity: `make parity K="not point_in_time_equivalence"` 121 of 121. The je-step-*, je-month-* and legacy_probe cases pass.
- Selection: 161 of 174. DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT newly passes; none newly fails.
- Data note, from the ruling: a dev or QA tenant already holding LEGACY lines under the old sign must be reseeded.

### Shared files touched (batch 2)

- The named shared sites were not edited: `backend/erev_engine/__init__.py` `_framework_output` and `stages/s10_billing_balances/position.py`.
- Lane E engine files:
  - `stages/s10_billing_balances/refund_liability.py` (Target cause; `_concession_event`);
  - `stages/s13_books/__init__.py` (`_relief_targets`, `_monetary_flows`, `_concession_flows`);
  - `stages/s13_books/legacy_book.py` (docstring);
  - `stages/s14_posting/targets.py` (`_refund_liabilities`, `_relief`);
  - `stages/s14_posting/templates.py` (JET-15).
- Journals-owner files, edited under L7-6-Q-8: `backend/erev_api/domain/journals/summarise.py`, `views.py` and `queries.py`.
- Test support: `backend/tests/support/intent_totals.py` and `worlds.py`.
- Tests:
  - `tests/engine/s10_billing_balances/test_s10_position.py`;
  - `tests/engine/s13_books/test_s13_legacy.py`;
  - `tests/engine/s14_posting/test_s14_templates.py` and `test_chk_delta.py`;
  - `tests/properties/test_prop_p05_journal_balance.py`.
- No Alembic revision. Not touched: PROGRESS.md, other documents, key files and golden expected values.

### Spec questions (batch 2)

- **L8-E-Q-2 (RND-CHK-003C refund-liability grain).** Under L7-5-Q-4 as ruled, JET-05c posts per obligation, and the JET-04b part of the concession component nets to 0.
  - Measured at FY2026-P02 (`role_account_obligation`):
    - REVENUE 4000 Dr 33.34 / 33.33 / 33.33 (matches);
    - no CONTRACT_LIABILITY line and no JET-04b line (matches);
    - REFUND_LIABILITY 2110 Cr 33.34 / 33.33 / 33.33 on POB-001 / POB-002 / POB-003. The key expects one REFUND_LIABILITY 2110 Cr 100.00 line without an obligation key.
  - A stage 14 line takes its obligation dimension from the part's subject (`intents._dimensions`; runner `_line_obligation`), and JET-05c's subject is OBLIGATION.
  - Candidates: JET-05c credits REFUND_LIABILITY at the component, which amends "JET-05c parts stay per obligation"; or the key's line carries the obligation keys. Supervisor to rule. RND-CHK-003C stays failing.
- **L8-E-Q-3 (where relief cites the concession nodes).** The ruling reads "`_relief_targets` ... citing both nodes". A stage 13 `Target` holds one `node_id`, and `costs_view` has no TraceBuilder. A new relief node would need a new formula id, and `test_explain_service` requires an explain narrative for every registered formula, which lives outside lane E.
  - The relief target keeps the revenue node with value revenue + concessions. The stage 14 relief part cites the revenue node plus the `concession_created_cum` nodes, so the `post.role_target` nodes re-evaluate.
  - Supervisor to confirm, or to route a `books.relief` formula with its narrative.

### Gates (batch 2, build b1886ec)

- Release-gate selection (`rg-selection.txt`, 174 ids): 161 of 174. The batch baseline was 160. DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT newly passes; none newly fails. The 13 failing ids:
  - ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT, ALC-CHK-032-S4-EX34-CASEC-REJECTED, ALC-S4-EX35-CASEB;
  - FX-CHK-084-A-REFUND-LIABILITY-REMEASURED;
  - MOD-CHK-112 (stage 06, lane D), MOD-FS-09-CANCELLATION-REFUND-COMMISSION (L8-E-Q-1), MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION;
  - ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION, ONB-RB-06-RELIEF-GRANT-ROUTED-OUT;
  - REC-S5-UPFRONTFEE-OWN-A, REC-S5-UPFRONTFEE-OWN-B;
  - RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION;
  - RND-CHK-003C (L8-E-Q-2).
- `make parity K="not point_in_time_equivalence"`: 121 of 121 (b1886ec).
- `make lint`: OK. `make typecheck`: OK (557 source files).
- `make ci` (gate slot 1): OK. Backend 2116 passed, vitest 595 passed, 0 failed, 0 skipped.
- `make test-pg` (gate slot 1): OK. Backend 290 passed, 0 failed, 0 skipped.

## Batch 3

Rulings: D-88 L7-6-Q-2 with the D-89b P12 property amendment (`L7-merge.md` section P12), D-88 L7-6-Q-6 and D-88 L7-6-Q-1 with the K-04 activation. Resumed at 3d0ecc2; `main..HEAD` held batches 1 and 2, main had no new commits. Each ruling first had tests that failed on the old code (run from a `git archive HEAD backend` overlay under `.run/l8b3/head` with the new test file copied in), then the fix, the affected keys, the release-gate selection (`rg-selection.txt`, 174 ids) and a commit. Scratch and logs: `.run/l8b3/`.

Baseline at 3d0ecc2: selection 161 of 174 (the 13 failing ids of batch 2). `make properties K=p12` replayed a saved falsifying example and failed (a CONTRACT_LIABILITY layer created by a release at 518160 against round(amount × spot) 518161).

### D-88 L7-6-Q-2 and D-89b P12: the release residue folds into the last asset settlement (commit 151e2ca)

- Root cause: when the open contract-asset layers absorb a whole release (S12-R-03 settles assets first), no contract-liability layer is created. The asset settlements at round(take × spot) then differ from the portions consumed at spot by up to k − 1 minor units, a GL-to-layer residue.
- Fix (`stages/s12_fx_entities/layers.py`):
  - `UnitBook.credit` passes `release = (released, earlier settlements)` to `settle` for the take that leaves `left == 0` when `released` is given. A release that also creates a contract-liability layer keeps `create_released`.
  - `settle`: r = Σ released − Σ settled amounts, this one included. When r ≠ 0, ASSET_LAYER_REMEASURED (reason SETTLEMENT) records d + r, ASSET_LAYER_SETTLED records round(take × spot) + r, `fn_carrying` still leaves by its carrying share, and JET-10a takes d + r. No ROUNDING line.
  - `release_residue` emits the `fx.gain_loss.sum.v1` nodes `fx_layer_remeasured` `<layer>@<flow>#release_residue` (released pieces +1, settled amount nodes −1), `fx_layer_remeasured` `<layer>@<flow>#release_total` (difference node + residue node) and `fx_layer_settled` `<layer>@<flow>#release_total` (amount node + residue node). The two movements cite the total nodes.
- D-89b (`backend/tests/properties/test_prop_p12_fx_layers.py`), exactly as `L7-merge.md` states:
  1. `releases` = the source keys of the monetary DECREASE flows with control CREDIT; helper `of_source(key, kind, roles)`. A CONTRACT_LIABILITY layer created by a release expects Σ LIABILITY_LAYER_CONSUMED (monetary roles) − Σ ASSET_LAYER_SETTLED (CONTRACT_ASSET) of that source, with `abs(expected − _at(amount_txn, spot)) <= len(consumed) + len(settled)`; any other layer expects `_at(amount_txn, spot)`. The module docstring names D-87 L6-5-Q-26, D-88 L7-6-Q-2 and D-89b; the comment reads "created at spot, or at the release carrying".
  2. A CONTRACT_ASSET settlement of a release source keeps the same bound against spot instead of the per-movement equality, and each release ties per source: consumed == settled + created. "A fully settled layer ends at 0" stays.
- Tests (`backend/tests/engine/s12_fx_entities/test_s12_remeasurement.py`), world: refund-liability layers EUR 100.05 and 200.05 released on 15 April at spot 1.1000 (consumed 110.06 + 220.06 = 330.12) into a contract asset created at the March average 1.0800:
  - (a) `test_l8_e_release_residue_folds_into_the_last_asset_settlement`: asset EUR 300.10 at 324.11, full take. Remeasured 601 (6.00 + 0.01), settled 33012, no contract-liability layer, residue node "0.01" with signs 1|1|-1, total nodes "6.01" and "330.12" cited by the movements, JET-10a P04 601, no open layer, control-role GL (revenue functional + JET-04b release functional + JET-10a) 0.
  - (b) `test_l8_e_partial_take_folds_the_residue_and_keeps_the_carrying`: asset EUR 500.00 at 540.00. Remeasured 601, settled 33012, open (19990, 21589), control-role GL 21589, and the May reclass attribution publishes `netting_reclass_amount` 19990 / 21589, so `reclass._shares` ties the movements to the carrying.
  - On the old engine both fail on remeasured 600 against 601.
  - With the amended property and the old engine, `make properties K=p12` failed on the release tie per source (consumed 0 against settled 1), which is the residue.
- Keys: FX-CHK-080, 081, 082, 083, FX-CHK-084-B, FX-CHK-084-C, FX-POL-160 and FX-POL-161 pass. FX-CHK-084-A fails with the same 19 mismatches as at batch 2 (lane D, L7-5-Q-3).
- `make properties K=p12`: OK, 1 passed (backend/.hypothesis replayed first). Stage 12 engine tests: 36 passed.
- Selection: 161 of 174. None newly passes; none newly fails.
- Deviation: when d + r = 0 the settlement records no ASSET_LAYER_REMEASURED movement, as the existing rule never records a zero remeasurement; JET-10a still cites the total node.

### D-88 L7-6-Q-6: functional JET-14 release at historical carrying (commit f7fc61a)

- Root cause: stage 14 `_customer_consideration` passed a stage 12 functional amount to JET-14 promised only. A non-zero foreign-currency release part raised "stage 12 publishes no functional amount for a foreign-currency part target", and T-CON-09 released the incentive asset at historical carrying with no GL counterpart.
- Fix:
  - `stages/s12_fx_entities/balances.py`: `release_functional(P_fn, P_txn, Rel, μ_fn)` = cumulative_posted(P_fn ÷ 10^μ_fn, P_fn, Rel ÷ P_txn, μ_fn). `release_targets(book, allocated, published)` reads `allocated.specialist_targets.customer_consideration` for a unit whose functional currency differs from the transaction currency. Per (entity, `<contract>@<entity>`, period) with Rel = `incentive_release_cum` − `share_based_reduction_cum` > 0, it publishes an FxTarget `incentive_release_cum` with amount_txn Rel, amount_functional F_rel of the promised FxTarget of that period (P_fn, P_txn), its rates, and node `fx_layer_settled` `<contract>@<entity>#JET-14 release` (`fx.settlement.spot.v1`, params output SHARE, amount_txn Rel, open_before P_txn, carrying_before P_fn, minor_unit). Rel = 0 publishes nothing. A release with no promised FxTarget in its period, or above P_txn, raises ENGINE_INVARIANT_VIOLATED (rule POL-164).
  - `stages/s12_fx_entities/__init__.py` `run` appends `release_targets` to the unit's functional targets.
  - `_incentive_functional(promised, payable_txn, released)` = P_fn − the published F_rel of the row's period (0 when none), so T-CON-09 and the GL tie by construction.
  - `stages/s14_posting/targets.py` `_customer_consideration` passes that FxTarget as `fx` to the JET-14 release part. No JET-10 line; a foreign share-based part still fails closed.
- Tests (`backend/tests/engine/s13_books/test_s13_payable_flows.py`):
  - `test_l8_e_foreign_release_posts_jet_14_at_historical_carrying`: EUR 50,000.00 promised on 1 June at 1.1000 with EUR 10,000.00 released gives FxTarget (1,000,000; 1,100,000; 1 June spot), node `fx_layer_settled:K-01@US01#JET-14 release:FY2026-P06`; stage 14 JET-14 promised (5,000,000; 5,500,000) and release (1,000,000; 1,100,000) at the 1 June spot; asset 4,400,000. Whole release: F_rel 5,500,000, asset 0. `release_functional(110, 300, 100, 2)` = 37, asset 73. A USD book publishes none.
  - `test_l8_e_release_without_amount_and_share_based_parts`: EUR 15,000.00 released with a 5,000.00 share-based reduction publishes F_rel 1,100,000 and stage 14 still refuses the foreign share-based part; Rel 0 publishes nothing and JET-14 release posts 0 / 0; a release in FY2026-P05, before the promise, raises.
  - `test_l7_6_incentive_asset_releases_at_historical_carrying` amended to the new signature with every figure kept.
  - On the old engine (overlay at 151e2ca) all three fail.
- Keys: CPC-CHK-133-S3-EX32, CPC-CHK-120-SHARE-BASED-WARRANTS-NOT-PROBABLE, CPC-CHK-120-SHARE-BASED-WARRANTS-PROBABLE and FX-CHK-084-C pass (4 of 4). FX-CHK-084-C publishes no release target and keeps the asset at 55,000.00 (`test_l6_5_foreign_promise_posts_jet_14_at_spot_and_remeasures_the_payable`).
- Stage 12 to 14 engine tests: 137 passed. `ruff` and strict `mypy` on the changed files: OK.
- Selection: 161 of 174. None newly passes; none newly fails.
- Deviation: `_incentive_functional` subtracts the published F_rel instead of recomputing it from the T-CON-09 transaction columns. The figures are the same (payable − asset = Rel by stage 04 construction), and the column cannot drift from the posted release. No carry-forward is applied to F_rel, because nothing is published while Rel = 0.

### D-88 L7-6-Q-1: one rate stamp per posting line; K-04 activates (commit 9158bc8)

- Root cause: `BookOutput` did not carry `PostingState.line_rates`, so `computation._post_book` refused every foreign-currency line (L3-1-Q-30), and K-04's AVM-US performing lines (GBP to USD) could not persist.
- Fix:
  - (1) `erev_engine/bundle.py`: `BookOutput.line_rates: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()` as the last member. `erev_engine/__init__.py` (the compute output assembly, not `_framework_output`) copies `PostingState.line_rates` sorted by line key as (rate key, version key) pairs. The LEGACY `book_output` keeps ().
  - (2) `erev_api/domain/contracts/bundles.py`: `_fx_rate_rows` is the `_fx_rates` query that also selects `fx_rate.id` and `fx_rate_set_version.id`; `_fx_rates` projects it unchanged. `fx_rate_ids(session, bundle)` maps each rate key of the bundle to (fx_rate.id, fx_rate_set_version.id, rate), using the bundle's currencies at `known_at`.
  - `computation._post_book` stamps a foreign-currency line with `_rate_stamp`: the RateRef with the latest effective date (ties: greatest rate key) gives `fx_rate_id` and `fx_rate_set_version_id`. It still raises ValueError when the line has no RateRef, and raises for a RateRef the bundle does not pin or whose version differs.
  - A line with several RateRefs appends `<book>:<line key>` to an optional `deviations` list. `persist` records the sorted list as `rate_stamp_deviations` in the `contract_computation.create` fact detail; the full list stays in the calculation trace. The parity netting stand-in calls `_post_book` without the list.
  - (3) `avenmoor/contracts.py` sets K-04 `activates=True` (comment and module docstring amended), and `test_seed_avenmoor_contracts.py` drops K-04 from `BLOCKED` (comment and docstring amended).
- Tests:
  - `backend/tests/engine/s13_books/test_s13_payable_flows.py::test_l8_e_book_output_carries_the_line_rates`: in FX-CHK-084-C the line-rate keys equal the sorted keys of the two foreign-currency lines, each carrying the 1 June spot of the bundle.
  - `backend/tests/domain/contracts/test_computation.py::test_l8_e_rate_stamp_takes_the_latest_rate_ref` (no database): latest effective date wins; on the same date the greatest rate key wins; an unpinned rate or another version raises.
  - Ruling gate `make test TESTS="backend/tests/domain/demo backend/tests/domain/contracts/test_computation.py" SLOW=1`: 33 passed, including `test_key_contracts_booked_and_active` with K-04 ACTIVE.
  - Not run here, as instructed: `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` and `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts` (RC-SMOKE.7, .9 and .10 with the K-04 GBP lines in AVM-US). The supervisor judges K-04 at the merge gate, and CTR-20 stays unticked until then.
  - K-04 figures of the ruling (O1 58,285.71, O2 9,714.29, O1 Sep 2026 4,790.61) not measured in this lane: the seeded world is torn down after the demo tests.
- Engine suites (kernel `test_bundle.py`, `tests/unit/answer_keys`, stages 12 to 14): 205 passed. `ruff` and strict `mypy` on the changed files: OK.
- Selection: 161 of 174. None newly passes; none newly fails.
- Deviation: the rate row ids are re-read in `_post_book` through `fx_rate_ids` (the same `_fx_rate_rows` query at the bundle's `known_at`), because `persist` receives the built bundle, not the build's rows.

### Shared files touched (batch 3)

- `backend/erev_engine/__init__.py`: an additive `line_rates` member in the compute `BookOutput` assembly (L7-6-Q-1). `_framework_output` and `stages/s10_billing_balances/position.py` were not edited.
- `backend/erev_engine/bundle.py`: `BookOutput.line_rates` (additive, defaulted last member).
- Platform files named by L7-6-Q-1: `erev_api/domain/contracts/bundles.py` (`_fx_rate_rows`, `fx_rate_ids`), `computation.py` (`_post_book`, `_rate_stamp`, `persist` fact detail), `erev_api/domain/demo/avenmoor/contracts.py`; tests `tests/domain/demo/test_seed_avenmoor_contracts.py` and `tests/domain/contracts/test_computation.py`.
- Lane E engine files: `stages/s12_fx_entities/layers.py`, `balances.py`, `__init__.py`; `stages/s14_posting/targets.py`.
- Tests: `tests/engine/s12_fx_entities/test_s12_remeasurement.py`, `tests/engine/s13_books/test_s13_payable_flows.py`, `tests/properties/test_prop_p12_fx_layers.py`.
- No Alembic revision. Not touched: PROGRESS.md, other documents, key files and golden expected values.

### Spec questions (batch 3)

- None new. L8-E-Q-1 (MOD-FS-09 catch-up trace), L8-E-Q-2 (RND-CHK-003C refund-liability grain) and L8-E-Q-3 (relief citation) stay open with the supervisor. MOD-FS-09-CANCELLATION-REFUND-COMMISSION and RND-CHK-003C still fail as recorded.

### Gates (batch 3, build 9158bc8)

- Release-gate selection (`rg-selection.txt`, 174 ids): 161 of 174, run on the 9158bc8 tree. None newly passes; none newly fails. The 13 failing ids:
  - ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT, ALC-CHK-032-S4-EX34-CASEC-REJECTED, ALC-S4-EX35-CASEB;
  - FX-CHK-084-A-REFUND-LIABILITY-REMEASURED;
  - MOD-CHK-112 (stage 06, lane D), MOD-FS-09-CANCELLATION-REFUND-COMMISSION (L8-E-Q-1), MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION;
  - ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION, ONB-RB-06-RELIEF-GRANT-ROUTED-OUT;
  - REC-S5-UPFRONTFEE-OWN-A, REC-S5-UPFRONTFEE-OWN-B;
  - RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION;
  - RND-CHK-003C (L8-E-Q-2).
- `make properties K=p12`: OK, 1 passed (151e2ca). This clears the L7 merge gate's P12 failure.
- `make parity K="not point_in_time_equivalence"`: 121 of 121 (9158bc8).
- `make ci` (gate slot 2): OK. Backend 2121 passed, vitest 595 passed, 0 failed, 0 skipped. It includes lint and typecheck.
- `make test-pg` (gate slot 2): OK. Backend 290 passed, 0 failed, 0 skipped.
