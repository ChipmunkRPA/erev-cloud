# ENG-C8: END-11 / END-12 JET template check tests (test-only)

Lane builder record for lane ENG-C8 on `sprint/l10` (worktree `~/dev/erev-wt/l10`, fast-forwarded to main eb5546a, the ENG-C7 merge, before the first commit). Binding: the lane brief `docs/reviews/loop/prod/lanes/ENG-C8.md` (re-labelled from ENG-C7 on 2026-09-19), BUILD_SPEC END-11 (`docs/BUILD_SPEC.md:5947`) and END-12 (`:5972`), `.run/supervisor/d91/lane-dispatch-common.md` with its 12:16 PDT slot hardening and the per-lane worktree lock, and Codex's critical-path audit entry 7 (positive and negative template coverage; per-event / per-obligation conservation; mutation probes). Test-only: no template, engine, oracle or document other than this record was changed. The JET-05c concession leaf (AD-14 / AD-15) is not asserted. Status vocabulary: every item below is **committed (lane)**; nothing is merged or gate-measured on main.

## 1. Commits and files

| Commit | Files | Change |
|---|---|---|
| cd294c7 | `backend/tests/support/jet_lines.py` (new), `backend/tests/engine/s14_posting/test_chk_jet_part1.py` (new), `backend/tests/engine/s14_posting/test_chk_jet_part2.py` (new) | The END-11 / END-12 check tests (§2) and their helper: `run_checkpoint(key, checkpoint)` builds the key's checkpoint bundle with the answer-key assembler (DG-AK-40), runs `erev_engine.compute` and the runner's close passes in `runners.CLOSE_PASSES` order (FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS; RCP-08), and reads the posted lines per (entry kind, side, role, clearing purpose, counterparty), the T-CON-09 balance columns and the T-CON-08 version columns; `entries_balance` asserts S14-INV-01 in both currencies. |
| 27da8d7 | `backend/tests/engine/s14_posting/test_chk_jet_coverage.py` (new) | Coverage and conservation over the 20 worlds (§3). |
| (this commit) | `docs/reviews/loop/sprint/ENG-C8.md` | This record. |

Not touched: `templates.py`, `amount_classes.py`, every engine module, every answer key, golden file and accounting document, `rg-selection.txt`, PROGRESS.md. (The test-only phase, cb0c645. The Q-1 ruling then touched the engine, the specs and the platform posted-amount query: §9.)

## 2. Check tests (BUILD_SPEC END-11 and END-12 acceptance, item bodies quoted in the docstrings)

Every check runs the named CHK answer-key world on its unchanged inputs through the public path and names the template lines by their Table 14-A identity; the figures below are the item bodies' and the keys' subledger blocks (`.run/ENG-C8/explore-1.log` is the calibration print of every line).

`test_chk_jet_part1.py` (END-11; POLICIES JET-01b, JET-02, JET-03, JET-04a, JET-04b, JET-06):

| Test | World, checkpoints | Lines asserted |
|---|---|---|
| `test_chk_021_deposit_to_contract_liability` | JE-CHK-021 `may-close`, `june-close-after-criteria-met` | months 1–5: `DEPOSIT` Dr `BILLING_CLEARING` (UNAPPLIED_CASH) 20.00 / Cr `DEPOSIT_LIABILITY` 20.00 each; deposit liability 100.00 at P05, contract liability 0; June: `DEPOSIT` Dr clearing 20.00, Dr `DEPOSIT_LIABILITY` 100.00 (the 120.00 transfer net of the June receipt in one entry, S14-R-12; the key's block), Cr `CONTRACT_LIABILITY` 120.00; `REVENUE_RECOGNITION` Dr CL 120.00 / Cr `REVENUE` 120.00; deposit 0, CL 0, revenue_cum 120.00; the passes add nothing |
| `test_chk_023_sales_tax_engine_billing` | JE-CHK-023 `january-close` | `BILLING` Dr `ACCOUNTS_RECEIVABLE` 1,080.00 / Cr CL 1,000.00, Cr `SALES_TAX_PAYABLE` 80.00 (line order D AR, C CL, C TAX); JET-02 1,000.00; receivable 1,080.00, CL 0 |
| `test_chk_024_cancellable_and_noncancellable_invoices` | JE-CHK-024 A `january-close`, `receipt-1-march`, `march-close`; B `january-close`, `march-close` | A: no January line, receivable 0 and CL 0; 1 March `BILLING` Dr AR 1,000.00 / Cr CL 1,000.00 (CL 1,000.00); 31 March JET-02 1,000.00. B: `BILLING` on 31 January with receivable and CL 1,000.00 each; JET-02 1,000.00 in March, CL 0 |
| `test_chk_025_volume_rebate_refund_liability` | JE-CHK-025 `q1-close`, `q2-close` | Q1 JET-02 7,500.00; Q2 `REVENUE_RECOGNITION` Dr CL 44,250.00 / Cr REVENUE 44,250.00 (JET-02 45,000.00 less the JET-04a 750.00 through the relief target, S14-R-02/03), `REFUND_LIABILITY` Dr CL 5,750.00 / Cr `REFUND_LIABILITY` 5,750.00; revenue_cum 51,750.00; RL 5,750.00; CL 0, CA 0 |
| `test_chk_026_bonus_catch_up_lines` | JE-CHK-026 `year-2-january-catch-up`, `year-2-close` | January: compute posts JET-02 Dr CL 60,000.00 / Cr REVENUE 60,000.00 (the JET-04a catch-up); the NETTING_RECLASS pass Dr `CONTRACT_ASSET` 62,000.00 / Cr CL 62,000.00 with the 2,000.00 reversal → the key's Dr CA 60,000.00 / Cr REVENUE 60,000.00; CA 62,000.00. December: JET-02 1,062,000.00; reclass 124,000.00, reversal 62,000.00; Year 2 revenue 1,122,000.00; revenue_cum 2,124,000.00; CA 124,000.00 |

`test_chk_jet_part2.py` (END-12; POLICIES JET-04b, JET-04c, JET-09a to 09e, JET-10d, JET-11a/b, JET-12, JET-13, JET-14, JET-16, JET-17):

| Test | World, checkpoints | Lines asserted |
|---|---|---|
| `test_chk_130_commission_amortisation` | JE-CHK-130 `january-2026`, `year-end-2032` | JET-09a Dr `COST_TO_OBTAIN_ASSET` 10,000.00 and JET-09a′ Dr `COST_TO_FULFILL_ASSET` 140,000.00 / Cr `CONTRACT_COST_CLEARING` 150,000.00; JET-09b January 119.05 + 1,666.67 = 1,785.72; yearly obtain 1,428.57 (2026–2028, 2030–2032) and 1,428.58 (2029), fulfil 20,000.00 a year; carrying 148,214.28 then 128,571.43 … 21,428.57, 0.00 |
| `test_chk_131_impairment_and_reversal_lines` | JE-CHK-131 `asc606-period-1`, `asc606-period-2`, `ifrs15-period-2`; JE-CHK-131-…EXPEDIENT `january-close` | P01: 09a 40,000.00, 09b 10,000.00, 09c Dr `CONTRACT_COST_IMPAIRMENT` 15,000.00 / Cr asset; carrying 15,000.00; ASC606 P02: 09b 5,000.00, carrying 10,000.00, no reversal; IFRS15 P02: 09d Dr asset 10,000.00 / Cr `CONTRACT_COST_IMPAIRMENT` 10,000.00, carrying 20,000.00; expedient: only JET-02, carrying 0 |
| `test_chk_132_loss_provision_lines` | JE-CHK-132 three year ends | FY2027-P12 `LOSS_PROVISION` (TIME, CLOSE_RELEASE pass; none at compute) Dr `LOSS_EXPENSE` 30,000.00 / Cr `LOSS_PROVISION` 30,000.00; FY2028-P12 the reverse; `loss_provision_txn` 0 / 30,000.00 / 0 |
| `test_chk_133_consideration_payable_lines` | CPC-CHK-133 `at-inception`, `end-of-month-1` | inception `CONSIDERATION_PAYABLE` Dr `CUSTOMER_INCENTIVE_ASSET` 1,500,000.00 / Cr `CONSIDERATION_PAYABLE` 1,500,000.00; month 1 JET-02 2,000,000.00 and the JET-14 release Dr `REVENUE` 200,000.00 / Cr incentive 200,000.00 (roles netted in the one entry: incentive Dr 1,300,000.00); revenue_cum 1,800,000.00; incentive asset 1,300,000.00, payable 1,500,000.00 |
| `test_chk_134_assurance_warranty_accrual` | POB-CHK-134 `after-delivery` | `WARRANTY_ACCRUAL` Dr `WARRANTY_EXPENSE` 200.00 / Cr `WARRANTY_PROVISION` 200.00 beside JET-02 9,545.45; CL 954.55 |
| `test_chk_135_noncash_consideration_lines` | NCC-CHK-135 `end-of-january` | `NONCASH_CONSIDERATION` Cr CL 4,000.00 (four weekly 1,000.00), Dr `BILLING_CLEARING` (INVESTMENTS) 1,000.00, Dr `NONCASH_CONSIDERATION_ASSET` 3,000.00 (4,000.00 − 1,000.00 receipt); JET-02 4,000.00; CL 0 |
| `test_chk_136_advance_payment_accretion` | JE-CHK-136 three checkpoints; SFC-CHK-136-ANNUAL `transfer` | MONTHLY: `FINANCING_INTEREST` Dr `INTEREST_EXPENSE` / Cr CL 20.00 (month 1), 21.13 (month 12), year 1 246.71, 22.43 (month 24), year 2 261.93; CL 4,246.71 then 4,508.64; JET-02 4,508.64 at transfer. ANNUAL: 240.00 and 254.40; CL 4,240.00; revenue 4,494.40 |
| `test_chk_137_deferred_payment_month_1` | SFC-CHK-137 `end-of-month-1` | JET-02 848,346.53; JET-11a Dr CL 8,483.47 / Cr `INTEREST_INCOME` 8,483.47; the ERP instalment invoice 18,871.00 posts no engine line; JET-06 Dr `UNBILLED_RECEIVABLE` 837,959.00 (= 848,346.53 + 8,483.47 − 18,871.00); month 2 accretion 8,379.59 |
| `test_chk_138_implicit_price_concession_lines` | JE-CHK-138 `march-close` | `BILLING` Dr AR 1,000,000.00 / Cr CL; JET-02 400,000.00; `RECEIVABLE_CONTRA` Dr CL 600,000.00 / Cr `RECEIVABLE_CONTRA` 600,000.00; receivable 1,000,000.00, CL 0, revenue 400,000.00; no credit-loss line |
| `test_chk_112_termination_journal_lines` | MOD-CHK-112 `at-termination`, `after-credit-memo` | `REFUND_LIABILITY` Dr CL 60,000.00 / Cr RL 60,000.00; `CONTRACT_COST_AMORTIZATION` Dr 19,000.00 / Cr `COST_TO_OBTAIN_ASSET` 19,000.00 (18,000.00 acceleration + 1,000.00 of the month); June revenue 10,000.00; revenue_cum 180,000.00; cost asset 0; after the credit memo Dr RL 60,000.00 / Cr CL 60,000.00; RL 0; net position 0 |
| `test_chk_112_acceleration_carries_its_reason_code` | MOD-CHK-112 `at-termination` | **strict xfail** — Q-1 below |
| `test_chk_070_intercompany_lines` | ENT-CHK-070-…PERFORMING-ENTITY `end-of-p1` | US01: JET-02 60,000.00; `INTERCOMPANY` Dr CL 20,000.00 / Cr `INTERCOMPANY_DUE_TO` 20,000.00 (counterparty UK01); UK01: `INTERCOMPANY` Dr `INTERCOMPANY_DUE_FROM` 20,000.00 (counterparty US01) / Cr REVENUE 20,000.00; counterparty exactly on the intercompany roles; each entity's entries balance; CL 20,000.00; revenue_cum 80,000.00 |
| `test_chk_084_jet_10d_lines` | FX-CHK-084-A `march-close`, `may-close` | functional-only JET-10d lines (transaction 0.00): March period end loss 6.00 (TIME); April settlement loss 6.00 (EVENT) and period-end gain 4.00 (TIME); May settlement loss 2.00 (EVENT); functional revenue 10,670.00 + 110.00 = 10,780.00 |

Measured: `test_chk_jet_part1.py` 5 passed; `test_chk_jet_part2.py` 12 passed, 1 xfailed (strict).

## 3. Coverage and conservation (`test_chk_jet_coverage.py`, 51 passed)

- `test_world_posts_exactly_its_templates[20 worlds]`: the set of E-29 entry kinds posted through compute and the three passes equals the set the world's templates imply (positive), so a template without its trigger posts nothing (negative): no `BILLING` under ERP, no `FX_REMEASUREMENT` in a single-currency world, no `LOSS_PROVISION` without a loss unit, no `DEPOSIT` without a deposit, no `CONTRACT_COST_*` without a cost event; and none of `CREDIT_MEMO`, `RETURN_ASSET`, `PRE_STANDARD_REVENUE`, `SALES_TAX`, `MANUAL_ADJUSTMENT`, `REVERSAL` appears.
- `test_every_end_11_12_template_is_witnessed`: the 17 END-11 / END-12 entry kinds are each witnessed by at least one world.
- `test_every_entry_balances_and_names_its_obligation[20]`: per event, every intent balances in both currencies (S14-INV-01); per obligation, every `REVENUE_RECOGNITION` intent's subject is `obligation_subject_key(contract_key, obligation_key)` of its lines' dimensions (S14-R-12, S14-R-13).
- `test_revenue_lines_conserve_the_version_and_obligation_cumulatives[10]`: for the worlds whose version date is a period end (CHK-021, 024 A/B, 026, 131 IFRS15, 132, 133, 136 ANNUAL, 137, 070) the signed REVENUE lines of the periods ending on or before the version date equal the contract version `revenue_cum` (the JET-14 release Dr REVENUE included at contract level) and, per obligation dimension, the obligation `revenue_cum`. The other ten worlds have a mid-period version date, where the T-CON-08 / T-CON-11 columns are partial-period cumulatives and only the runner's to-date comparison applies (`.run/ENG-C8/conservation2.py` shows the mid-period differences, e.g. CHK-023 version 1,000.00 at 15 January vs the January period's lines).

## 4. Fail-first: seeded template mutations

The check tests did not exist on eb5546a; the brief's fail-first form is the mutation probe: each probe detaches ONE Table 14-A rule before collection by rebinding the constants the stage 14 derivation reads (`targets.JET_PARTS`, `targets.AMOUNT_CLASSES`, imported by name), so exactly the check that guards the rule fails while a control check passes. Plugin `.run/ENG-C8/mutations_c8.py` (pattern of `.run/mutations.py` and T1's `mutations_t1.py`; `-p mutations_c8`, `EREV_MUTATION=<probe>`, `PYTHONPATH=.run/ENG-C8:backend/tests`); runner `.run/ENG-C8/run_probes.sh`; one log per run under `.run/ENG-C8/probes/`; summary `probes/summary.txt` (DONE 15:45:21 at eb5546a with the same test files; repository templates untouched). **34 of 34 runs as expected (16 probes tripped their check; 18 controls passed).**

| Probe (`EREV_MUTATION`) | Rule detached | Check that fails | Control that passes |
|---|---|---|---|
| `jet-01b-criteria-met-to-revenue` | JET-01b criteria met credits REVENUE | `test_chk_021` | `test_chk_023` |
| `jet-03-tax-to-revenue` | JET-03 tax share of the split credit lands on REVENUE | `test_chk_023` | `test_chk_021` |
| `jet-04b-refund-to-cl` | JET-04b credits CONTRACT_LIABILITY (the entry nets away) | `test_chk_025`, `test_chk_112_termination` | `test_chk_023` |
| `jet-06-class-detached` | JET-06 reclass and reversal lose their NETTING_RECLASS TIME class | `test_chk_026`, `test_chk_137` | `test_chk_023` |
| `jet-09a-fulfil-to-obtain` | JET-09a′ capitalises on the obtain asset | `test_chk_130` | `test_chk_134` |
| `jet-09c-sides-swapped` | JET-09c Dr asset / Cr impairment | `test_chk_131` | `test_chk_130` |
| `jet-09e-to-clearing` | JET-09e credits CONTRACT_COST_CLEARING | `test_chk_112_termination` | `test_chk_131` |
| `jet-12-sides-swapped` | JET-12 Dr LOSS_PROVISION / Cr LOSS_EXPENSE on an increase | `test_chk_132` | `test_chk_130` |
| `jet-14-release-to-payable` | JET-14 release credits CONSIDERATION_PAYABLE | `test_chk_133` | `test_chk_134` |
| `jet-16-expense-to-cost-of-revenue` | JET-16 accrual debits COST_OF_REVENUE | `test_chk_134` | `test_chk_133` |
| `jet-17-receipt-purpose` | JET-17 receipt clears through UNAPPLIED_CASH | `test_chk_135` | `test_chk_134` |
| `jet-11b-sides-swapped` | JET-11b Dr CONTRACT_LIABILITY / Cr INTEREST_EXPENSE | `test_chk_136` | `test_chk_137` |
| `jet-11a-income-to-revenue` | JET-11a credits REVENUE | `test_chk_137` | `test_chk_136` |
| `jet-04c-contra-to-receivable` | JET-04c credits ACCOUNTS_RECEIVABLE | `test_chk_138` | `test_chk_023` |
| `jet-13-performing-to-cl` | JET-13 performing credits CONTRACT_LIABILITY | `test_chk_070` | `test_chk_138` |
| `jet-10d-no-period-end-pass` | JET-10d loses its FX_REMEASUREMENT period-end class | `test_chk_084` | `test_chk_070` |

## 5. Where the worlds stop (L5-3 table form; nothing claimed)

| Key | State on eb5546a (`.run/ENG-C7/combined/keys-all-report.json` and this lane's runs) | Where it stops next |
|---|---|---|
| JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP | failing (2 mismatches): `trace revenue_prior_period:C-JE-026/L1-BUILD:FY2027-P01 expected 60000.00 actual <absent>`, `…FY2027-P12 expected 0.00 actual <absent>` | the stage 15 `revenue_prior_period` trace node (disclosures; not stage 14). Its JET-02 / JET-04a / JET-06 lines and balances are reached and asserted by `test_chk_026_bonus_catch_up_lines` |
| the other 19 END-11 / END-12 worlds | passing | — |

## 6. Gates (measured on `sprint/l10`; none projected)

CPU-only, on the supervisor's instruction (a preparation lane; no DB chain is admitted for it, so `make test-pg`, `make ci`, `make parity` and `make properties` were NOT run here — the release evidence for those stages is the supervisor batch on merged main). Chain `.run/ENG-C8/gates/` (`summary.txt`, START 15:49:23 head 27da8d7 dirty 0):

| Gate | Measured on 27da8d7 | Log |
|---|---|---|
| `make lint` | `OK lint` (run before the two commits as the commit gate, on the same files) | `.run/ENG-C8/lint-1.log` |
| `make typecheck` | `OK typecheck` | `gates/typecheck.log` |
| `pytest backend/tests/engine backend/tests/architecture` | 1313 passed, 2 xfailed (the lane's 69 tests included: part 1 five, part 2 twelve + one strict xfail, coverage 51) | `gates/engine-arch.log` |
| `make answer-keys ID=<rg-selection.txt, 200 ids in this tree>` | 200 selected; 200 passed, 0 failed | `gates/keys-rg.log`, `keys-rg-report.json` |
| `make answer-keys ID=<main's rg-selection.txt at c8899be, 204 ids>` | 204 selected; 204 passed, 0 failed (main's file read with `git show main:…` at c8899be, since this tree sits on eb5546a with 200 ids; 8d76fea later widened the selection to 220 with the ENC-8 keys, which are not on this tree) | `gates/keys-rg-204.log`, `keys-rg-204-report.json` |
| `make answer-keys` (all active) | 251 selected; 205 passed, 44 failed, 2 withdrawn — 0 new failures against the base 58 (`.run/l9bgate/keys-all-failed.txt`) and the identical 44-id set of eb5546a (`.run/ENG-C7/combined/keys-all-report.json`); this test-only lane turns no key green | `gates/keys-all.log`, `keys-all-report.json` |
| seeded template mutations (§4) | 34 of 34 runs as expected (16 tripped, 18 controls passed) | `.run/ENG-C8/probes/` |


DB stages: none run in this lane (see above). No gate slot was claimed and no waiter was started for ENG-C8.

## 7. Questions returned (policy or template matters, not decided here)

- **Q-1 (template gap, returned with figures; pinned by a strict xfail).** Table 14-A row JET-09e (`ENGINE_SPEC_B.md:1897`) and S11-R-13 (`:1261`) post the termination acceleration "with `reason_code = TERMINATION_ACCELERATION`"; JET-09f (`:1894`; S11-R-12 `:1260`) "with `reason_code = CLAWBACK`". Stage 14 stamps only `LATE_EVENT` and `VOID` (`assign.py`); the acceleration posts inside the month's `CONTRACT_COST_AMORTIZATION` entry with no reason code: MOD-CHK-112 FY2027-P06 Dr `CONTRACT_COST_AMORTIZATION` 19,000.00 / Cr `COST_TO_OBTAIN_ASSET` 19,000.00 (18,000.00 acceleration + 1,000.00 JET-09b) in one entry. The key's `role_account` grain is indifferent (the amounts hold), so no oracle changes; a fix separates the entry by reason code (S14-R-12 groups by reason) and touches the engine — outside this test-only lane. `test_chk_112_acceleration_carries_its_reason_code` is `xfail(strict=True)` and flips when the reason code is stamped. **Ruled (D-98 candidate 19, supervisor 2026-09-19) and implemented on this lane — §9.**
- **Q-2 (item text vs posted entry; clarification only).** END-11's CHK-021 text reads "Dr `DEPOSIT_LIABILITY` 120.00 / Cr `CONTRACT_LIABILITY` 120.00"; the posted June `DEPOSIT` entry nets the role with the June receipt (Cr 20.00) to Dr `DEPOSIT_LIABILITY` 100.00, as the key's block states (S14-R-12: one entry per kind, class, subject and reason). The check asserts the netted entry and the identity 120.00 − 20.00 = 100.00. If the item text is meant per part rather than per entry, no change is needed; otherwise the BUILD_SPEC wording is the supervisor's.
- **Q-3 (observation, consistent).** END-12's CHK-084 text ("losses 6.00 and 6.00, gain 4.00 and loss 2.00; revenue USD 10,780.00") matches the engine's four JET-10d differences; the key's blocks show the P04 net of 2.00 (6.00 loss − 4.00 gain). No question.

## 8. Residual limits

- The probe plugin and its runner are lane scratch under `.run/ENG-C8/` (as `.run/mutations.py` and T1's plugin are), not committed; the record carries the probe table and the summary path.
- The conservation invariant against `revenue_cum` is asserted for the ten period-end worlds only; mid-period version dates compare partial-period cumulatives (the runner's to-date comparison covers them).
- `SALES_TAX`, `CREDIT_MEMO` (ERP-side kinds) and `RETURN_ASSET`, `PRE_STANDARD_REVENUE` (JET-07, JET-15) are asserted absent here and are witnessed by other suites (returns, LEGACY parity); JET-05a/b/c, JET-08 and JET-09f have no END-11 / END-12 world (JET-05c is the AD-14 / AD-15 leaf, held).

## 9. Q-1 ruling implemented — reason variants (D-98 candidate 19; S14-R-27)

Supervisor ruling on §7 Q-1 (2026-09-19 00:20Z, "D-98 candidate 19"): stage 14 stamps `reason_code = TERMINATION_ACCELERATION` on JET-09e (stage 11 cause `ACCELERATION`, EVENT-dated at d_T) and `CLAWBACK` on JET-09f (`COST_INCURRED` date); the acceleration is its own entry under S14-R-12; totals at `role_account` grain unchanged (MOD-CHK-112: 18,000.00 + 1,000.00 = 19,000.00); VOID wins as today; a late-placed acceleration or clawback keeps `reason_code = LATE_EVENT` with its origin; S15-R-17 gains the classification parenthetical docs-first; 04 needs no change (E-110 lists void/reopen reasons only; T-SL-04 `reason_code` is free text); lift the strict xfail; no key figure or golden changes. Follow-up correction (supervisor, on 8cb250b): no lane ENGINE_VERSION bump — a version names a release.

### 9.1 Commits

| Commit | Change |
|---|---|
| 4c0ac70 | Docs first: ENGINE_SPEC_B new rule (then S14-R-26, renumbered S14-R-27 at the merge, §9.4), Table 14-A JET-09e / JET-09f cells name the reason, S15-R-17 parenthetical, §14.6 variant `posting_target` nodes; ENGINE_SPEC §0.4 `PostedAmountInput.reason_code`; 05 RCP-05 `reason_code` grouping member. |
| aa21191 | Docs: S14-R-15 — `line_key` adds `reason_code` for a template-reason line only (found while implementing: the untagged and tagged lines of one role, period, origin, class and subject sit in two entries of one posting and collided on the line key and the `account_resolution` node; the EX-14-A vector stands). |
| 8cb250b | Engine, platform and tests (§9.2, §9.3). Carried `ENGINE_VERSION` 0.3.0 → 0.4.0, reverted by e04af87. |
| e04af87 | `ENGINE_VERSION` back to 0.3.0 with the pin; the bump is OWED at the release cut (§9.5). |
| b295737 | Merge main cdcf372 (F-WEB-R, P4, P1 GATE-BIND-1). main's ENB-9 rule already held S14-R-26, so the lane's rule is **S14-R-27** in every document, docstring and test; revision rows renumbered above main's (ENGINE_SPEC_B 1.12 → 1.14, ENGINE_SPEC 1.11 → 1.12; 05 stays 1.12, main's 05 being at 1.11). Renumbered again for the group-2 merge (§9.8). `assign.py`: main's `_Walker.cutovers` (ENB-9) and the lane's variant `zero_nodes` coexist. |
| b3b48b0 | Merge deb69ed (main's test-only fix of `test_supervisor_scripts.py::test_makefile_tf_validate_target`, which fails on cdcf372's wrapped Makefile). Default merge message (the lane never amends). |
| (this commit) | This record; the lane's chain scripts stay under `.run/ENG-C8/`. |

### 9.2 What the engine does now (S14-R-27)

- `templates.py`: `JetPart.reason_code` (JET-09e `TERMINATION_ACCELERATION`, JET-09f `CLAWBACK`); `TEMPLATE_REASONS`.
- `targets.py`: `_Share.reason`; `RoleVariant`; `RoleTarget.variants` — for a role key with a tagged share, one `posting_target` node per variant (`<subject>/<kind>/<role>/<reason|UNTAGGED>`, formula `post.role_target.v1` over the variant's part nodes) whose amounts sum to the role target (invariant); the role key, its target and its node are unchanged, and a role key without a tagged share publishes nothing new (trace byte-identical for every other key).
- `assign.py`: `PostedTotals` keeps, beside the pooled amounts, the tagged share per template reason and the (key, origin, class) set with an unattributable line (`LATE_EVENT`, `VOID`, any other reason). In a postable period of a subject without a new void, a role key with variants posts one delta per variant — the variant's movement less the posted lines carrying that reason (untagged: the lines without one) — **only when every posted line of that origin and class is attributable**; otherwise the single pooled delta as before (closed-period carry `LATE_EVENT` with origin; `VOID`; untagged). Variant deltas sum to the role key's delta (`ENGINE_INVARIANT_VIOLATED` otherwise); `reevaluate` stays exact through `post.delta.v1` over the variant nodes.
- Why the attributability condition (engineering, accepted by the supervisor): T-SL-04 has one `reason_code`; a sealed line whose reason was overridden to `LATE_EVENT` or `VOID` cannot be attributed back to a variant, and reconciling per variant against it would double-post or emit phantom offsetting entries. Pooled reconciliation is exact; the split only refines a delta whose origin is fully attributable. After a void of a tagged entry, later deltas of that origin post untagged (tested).
- `intents.py`: `line_key` adds `reason_code` for template-reason lines (S14-R-15).
- `bundle.py`: `PostedAmountInput.reason_code: str | None = None`; `hash_view()` omits it when None (the D-93 (5) `direction` precedent), `InputBundle.sha256` uses it — a bundle without tagged posted lines hashes as before apart from the version stamp.
- Platform `erev_api/domain/contracts/bundles.py`: the RCP-05 posted-amount query groups by `subledger_line.reason_code` and fills the member; `tests/support/intent_totals.posted` and `jet_lines.run_checkpoint(states=)` follow.

### 9.3 Tests (all in 8cb250b unless noted)

| Test | Asserts |
|---|---|
| `test_chk_jet_part2.py::test_chk_112_acceleration_carries_its_reason_code` (xfail lifted) | FY2027-P06 has two `CONTRACT_COST_AMORTIZATION` EVENT entries: 18,000.00 `TERMINATION_ACCELERATION` and 1,000.00 untagged; role total 19,000.00; acceleration lines cite the `…/TERMINATION_ACCELERATION:FY2027-P06` variant node, the monthly lines `…/UNTAGGED:…`; four distinct line keys; `revenue_cum` 180,000.00; entries balance. |
| `…::test_chk_112_late_placed_acceleration_keeps_late_event` | CHK-112 `after-credit-memo` with FY2027-P06 closed: ONE `LATE_EVENT` carry into P07 (origin P06) Dr 19,000.00 / Cr 19,000.00; no intent of the run carries `TERMINATION_ACCELERATION`; totals equal the open-period run. |
| `test_s14_deltas.py::test_s14_r27_clawback_is_its_own_entry_with_reason_code` | Capitalisation 10,000.00 and clawback 2,000.00 in one open month: JET-09a untagged, JET-09f `CLAWBACK` entry Dr `CONTRACT_COST_CLEARING` / Cr `COST_TO_OBTAIN_ASSET`; role totals 8,000.00 / −8,000.00; variant nodes 10,000.00 / −2,000.00 sum to the base 8,000.00; sealing → recompute is a no-op (round trip through `reason_code`). |
| `…::test_s14_r27_posted_clawback_then_capitalisation_change_stays_attributed` | After sealing, +500.00 capitalised posts untagged only; a further 1,000.00 clawback posts `CLAWBACK` only. |
| `…::test_s14_r27_void_pools_the_role_key_and_later_deltas_stay_untagged` | A new void reverses the sealed clawback as one pooled `VOID` delta per role (`VOID_REVERSAL`); recompute after the void is a no-op; a later change posts untagged (unattributable origin). |
| `…::test_s14_r27_late_placed_clawback_keeps_late_event` | January closed before posting: one pooled `LATE_EVENT` carry per role (8,000.00 net), never re-tagged; no variant delta node; recompute no-op. |
| `…::test_s14_r27_posted_totals_tag_template_reasons_only` | `PostedTotals.of`: pooled amounts, tagged share per template reason, `reasons_at`, `attributable` false for `LATE_EVENT` and a manual reason. |
| `kernel/test_bundle.py::test_posted_reason_code_hash_view_keeps_historical_hashes` | `hash_view` omits `reason_code` when None (equal to the pre-member form), keeps it when set; raw canonical keeps the field. |
| `kernel/test_stage_registry.py` pin | `ENGINE_VERSION == "0.3.0"` with the OWED note (e04af87). |
| DB (not runnable here) | `tests/domain/journals/test_subledger.py::test_posted_amounts_keep_repeated_compute_a_no_op` exercises the platform query change in the DB chain (§9.6). |

### 9.4 Gates (measured; CPU-only until the DB chain of §9.6)

| Gate | 8cb250b (pre-merge; `gates/q1-*`) | b295737 (main cdcf372 merged; `gates/merged-*`) | b3b48b0 (deb69ed merged) |
|---|---|---|---|
| `make lint` / `make typecheck` | OK / OK | OK / OK | OK / OK (`lint-b3b48b0.log`, `typecheck-b3b48b0.log`) |
| `pytest backend/tests/engine backend/tests/architecture` | 1321 passed, 1 xfailed (the lane's strict xfail lifted; +8 tests) | 1348 passed, 1 xfailed | not re-run (test-only merge outside these suites; supervisor) |
| `make answer-keys ID=<l10 rg-selection.txt>` | 200 selected; 200 passed | 220 selected; 220 passed (the merge brought the 220-id file) | — |
| `make answer-keys ID=<main's rg-selection.txt>` | 220 selected; 204 passed, **16 failed = exactly the 16 ENC-8 ids the 204 → 220 widening added, absent from that tree** (`failed == added` checked) | 220 selected; 220 passed, 0 failed | — |
| `make answer-keys` (all active) | 251 selected; 205 passed, 44 failed, 2 withdrawn — **0 new** against the ENG-C8 base (27da8d7, 44) | 251 selected; 221 passed, 28 failed, 2 withdrawn — **0 new** against the 44 and against the 58-id `.run/l9bgate/keys-all-failed.txt`; 16 turned green by main's merges (BRK ×6, MR ×4, ONB-CHK-121, POB-JS-05 ×2, ROY ×3) | — |
| focused suites | 453 passed (s14_posting, kernel, unit/answer_keys) | 541 passed, 1 xfailed (+ s13_books) | 37 passed (`unit/deploy/test_supervisor_scripts.py`, `unit/test_makefile_targets.py`) |

Guard: no answer-key expected value, golden file or key figure changed; the runner nets signed lines per grain, so the entry split is invisible at `role` and `role_account` grain (measured: 0 new failures everywhere).

### 9.5 Owed at the release cut (recorded, not done here)

- **`ENGINE_VERSION` 0.3.0 → 0.4.0**, once, under DG-ENG-10: `PostedAmountInput` gains the canonical member `reason_code` (the CV-25 view omits it when None, so historical inputs hash identically to their pre-member form apart from the stamp) and JET-09e / JET-09f post as their own entries with reason codes at unchanged role and account totals. Together with the identity `INPUT_TRANSFORM (0.3.0 → 0.4.0)` in the D-96 `erev_engine.upgrade` registry once it exists (absent on this tree). Supervisor ruling: a version names a release, not a lane merge.
- dev-guide DG-ENG-10 example row (supervisor-owned) not edited.

### 9.6 DB chain (ONE per lane; slot protocol)

Scripts `.run/ENG-C8/slot_lib.sh`, `gates-db.sh`, `wait-and-launch.sh`, `db_stages.py` (hashes in the launch report): per-worktree lock `.run/gates/chain-lock.d` (14:17 amendment), atomic two-slot `mkdir` claim with owner PID / start time and liveness (12:16), own-pid-only release trap, DB-stage admission by distinct (worktree root, stage) with every cwd under `<root>/.run/gates/ctx-*` normalised to `<root>` before the distinct count (19:25 amendment: one GATE-BIND-1 wrapped stage counts once; UNKNOWN = held), pass/fail by exit code. Stages `make test-pg`, `make ci`, `make parity K="not point_in_time_equivalence"`, `make parity`, `make properties` — each wrapped by `scripts/gate_context.sh` into an immutable execution context on the committed head. Results are appended below when the chain ends.

#### 9.6.1 Result (chain 90983; head bb00d176; slot 2; START 19:59:58, DONE 21:04:04 PDT, 2026-09-19)

Waiter 61698 (started 19:49:12) launched `gates-db.sh 2` at 20:00:03 when slot 2 freed with one other DB stage running; the chain held the l10 lock and slot 2 (owner 90983, lstart 19:59:58) and released both at END (`released slot-2`, `released worktree chain lock`; `db-chain.out`). Every stage ran in an immutable execution context of bb00d176 (`source_binding.mode = immutable-context`, `captured_sha = bb00d176`, tree and content hashes equal before and after; `gates/db-<stage>-report.json`). Pass/fail keyed on the make exit code.

| Stage | rc | Counts (`gates/db-<stage>.log`) |
|---|---|---|
| `make test-pg` | 0 | backend 291 passed, 0 failed, 0 skipped (1m) |
| `make ci` | 0 | backend 3025 passed, 0 failed, 1 skipped; vitest 96 files / 647 passed (54m) — includes `tests/domain/journals/test_subledger.py::test_posted_amounts_keep_repeated_compute_a_no_op` over the grouped-by-`reason_code` posted query |
| `make parity K="not point_in_time_equivalence"` | 0 | 121 selected; 121 passed (2m) |
| `make parity` (unfiltered) | 2 | 122 selected; 121 passed, 1 failed: `point_in_time_equivalence::shipped-db-equivalence` — the pending GPB-3 reader, failing before this lane (ENG-C7 record; supervisor batch "the known 121/122"); nothing of this lane touches it |
| `make properties` | 0 | 12 passed, 0 failed, 0 skipped (3m) |

Admission log: one `WAIT ci 20:01:45` (other DB-stage processes 2, claims 2) then `RUN ci 20:02:15`; `db_stages.py` counted wrapped stages once throughout (19:25 amendment).

### 9.8 Group-2 merge preparation (supervisor-assigned revision numbers; docs first)

Merge sequence C6 → C8 → C5. Before merging main 6e33ef27 into `sprint/l10` the lane's revision rows and header entries take the supervisor-assigned numbers so that no row collides by number with main's or C6's: `docs/05-ARCHITECTURE.md` 1.12 → **1.14** (main's 1.12 is P1's wording alignment, 1.13 P8 SOP-5); `docs/accounting/ENGINE_SPEC.md` 1.12 → **1.16** (C6 lands first with 1.12–1.15); `docs/accounting/ENGINE_SPEC_B.md` 1.14 → **1.15** (C6's 1.14 lands first). Cross-references swept: the three log rows' mutual "rev" mentions, RCP-05 "rev 1.14", S14-R-15 "rev 1.15", `bundle.py` and `test_bundle.py` docstrings ("ENGINE_SPEC §0.4 rev 1.16"), this record. C6's rows are not pre-included (the row-union resolver merges them at the supervisor's merge). The readiness matrix is not edited.

### 9.7 Notes

- `make fmt` (the Makefile's own ruff call from the repository root) created a root `.ruff_cache` twice; removed before each commit; no commit carried it (DG-LAY-01; 19:38 amendment).
- The `_posted` helper of `test_s14_deltas.py` had to pass `reason_code` — without it the sealed tagged lines lose their tag and the engine re-splits; the same dependency is why the platform query change is part of the ruling's implementation.

## 10. ENG-COST-ENC-1 — canonical identity of the estimate lookups (D-98 candidate 76)

Dispatched 2026-09-20 from Codex `PRODUCTION-F-RPS-STAGE11-REVIEW-0937e17.md` (three retained native worlds over the first checkpoint of `COST-S8-CONTRACT-COSTS-EX2`). Stage 01 indexes the estimate pins by the CV-21 encoded element key; `s11_costs_loss/capitalise.py` filtered that index with the RAW contract key (`key.startswith(f"{contract_key}/")`), so a contract id carrying `/` never found its approved `RENEWAL_EXPECTATION` and amortised over the 60-month term. Ruling: one canonical component representation for every lookup; a lookup that cannot find its key refuses by name. No key file or expected value changed.

| Commit | Change |
|---|---|
| 7e195f50 | Docs first: ENGINE_SPEC CV-21 gains the lookup sentence (provisional 1.17; renumbered 1.23 at the group merge, §10.1). |
| e976cc8c | `EstimatePins.of_contract` (encoded prefix; unencoded index entry refused by name, `ENGINE_INVARIANT_VIOLATED` rule CV-21); the five raw-prefix scans use it (`capitalise.renewal_versions`, `impair._eac`, `loss._has_eac`, `loss._eac`, stage 10 `reclass`); stage 14 `accounts.missing` names the contract through `contract_entity_subject_key`; one CV-21 table (`convert.KEY_ESCAPES` / `encode_key`, stage 14 `encode_component` delegating); `test_s11_identity.py` (5 tests). `enums.py` untouched (04 §3 mirror; `test_engine_enums_equal_data_model` refused a first attempt to host the encoder there). |
| (this commit) | This section. |

Survey of `startswith(f"{…` over the engine: the other pin scans already key on the encoded head (`s06 change_orders`, `s09 progress_inputs`, `s09 breakage`, `s10 customer_consideration`, `s04 returns / customer_consideration`, `royalties`); stage 01 `__init__` / `ledger.py` compare encoded subjects; `s14 assign.py` encodes. Only the six sites above were raw.

**Fail-first, the three retained worlds natively (`.run/ENG-C8/enc1/worlds.py`, `worlds-before.json` / `worlds-after*.json`; the key file is read, never written):**

| World | Estimate key in the bundle | Before (P01 carrying / amortisation) | After |
|---|---|---|---|
| 1 unmodified `C-COST-2` | `C-COST-2/AMORT-PERIOD` | 148,214.28 / 1,785.72 | 148,214.28 / 1,785.72 |
| 2 encoded-id-only `C-COST/2` (single entity) | `C-COST%2F2/AMORT-PERIOD` | **147,499.99 / 2,500.01** | 148,214.28 / 1,785.72 |
| 3 encoded id + US02 performer | `C-COST%2F2/AMORT-PERIOD` | **147,499.99 / 2,500.01** | 148,214.28 / 1,785.72 |

Codex's figures reproduced exactly before the fix (difference 714.29); the test `test_enc1_three_retained_worlds_amortise_over_the_approved_renewal` pins the three worlds after it.

**Gates (captured exit statuses; logs `.run/ENG-C8/enc1/`):** `make typecheck` rc 0; `make lint` rc 0 at the commit; `pytest backend/tests/engine backend/tests/architecture` rc 0 — 1367 passed, 1 xfailed (`engine-arch2.log`); stage 11 / 10 / 01 / kernel / s14 entries focused run 400 passed; `make answer-keys` on the nine COST / LOSS keys (COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT, COST-S8-CONTRACT-COSTS-EX1 / EX2 / EXPEDIENT / IMPAIRMENT, LOSS-GE-03, LOSS-S7-LOSS-OWN, JE-CHK-132, IFRS-SW11) rc 0 — 9 selected, 9 passed; `make answer-keys` on the 220-id release selection rc 0 — 220 passed (`keys-summary.txt`; run on the working tree of e976cc8c's code, one comment line shorter in the test file). CPU-only; no DB stage, no gate slot.

### 10.1 ENG-COST-LOOKUP-R1 — raw-prefix overlap is not malformedness (Codex key-only supplement 4/6 on e976cc8c)

Codex measured that `EstimatePins.of_contract("C%2F2")` raised `ENGINE_INVARIANT_VIOLATED` on `C%2F2/EAC`, the valid key of the distinct contract `C/2` (raw `C/2` encodes to `C%2F2`; raw `C%2F2`, a literal percent sequence, encodes to `C%252F2`): the first helper treated "under the raw prefix but not under the encoded one" as an unencoded entry. Ruling direction (within D-98 76): malformedness is a property of the entry's own structure, never of the requested raw prefix; select by the exact encoded prefix; refuse by name only a structurally malformed entry; do not weaken expectations or prohibit percent-containing ids.

| Commit | Change |
|---|---|
| b6407ce2 | Docs first: the CV-21 lookup sentence states the element-key form (`<head>/<element>`, no unencoded separator, `:` only as the `PORTFOLIO:` marker, only the five escapes), refusal by name of a malformed entry with its reason, and that a well-formed entry under the same raw prefix is another contract's valid key, simply not selected. |
| fb409b91 | `of_contract` selects exactly the keys under `encode_key(raw) + "/"`, ascending; `malformed_estimate_key(key)` decides malformedness structurally and a malformed entry anywhere in the index is refused by name (`estimate_key`, `contract_key`, `reason`) — a malformed pin key is a corrupt bundle, not another contract's data. Tests: the two-valid-id counterexample (each lookup returns exactly its own key), the malformed control `C/2/EAC`, the other separators / bad escape / empty parts, the `PORTFOLIO:` marker accepted. |
| (this commit) | ENGINE_SPEC provisional 1.17 → **1.23** (header, log row, CV-21 text, the test docstring, this record); this section. |

Fail-first on 5154c02a (`.run/ENG-C8/enc1/r1-fail-first.log`, rc 1): the counterexample raised on `C%2F2/EAC`; the control missed `C@1/EAC`. After fb409b91: identity tests 7 passed; engine + architecture 1369 passed, 1 xfailed (`r1-engine-arch.log`, rc 0); the three retained worlds 148,214.28 / 1,785.72 ×3 (`worlds-r1b.json`, rc 0).

### 10.2 Landing

`sprint/l10` at ba0a29f7 merged to main as **571b7dfe** (supervisor, 2026-09-20; merge-revrows on ENGINE_SPEC, the 1.23 row kept). Post-checks on main reported by the supervisor: typecheck rc 0; CPU suites rc 0 (2,500 passed, 1 xfailed); release selection 220/220; aggregate PASS. The lane's chains before landing: 0baa7d24 (typecheck, lint, engine + architecture + unit 2,368 passed / 1 xfailed, COST/LOSS 9/9, three worlds ×3, selection 220/220, all rc 0), cb02dc38 (lint, typecheck, 2,369 / 1 xfailed, 9/9, worlds ×3, all rc 0) and ba0a29f7 (lint, typecheck, 2,370 / 1 xfailed, all rc 0). Codex closed ENG-COST-LOOKUP-R1 narrowly at fb409b91 and R1a at 27c7025d (9/9 + 9/9), observing ba0a29f7 as the positive-control successor. The lane worktree is not fast-forwarded yet (P4 and P1 land behind this merge); new commits continue on top of ba0a29f7.

## 11. COST_ROLLFORWARD producer (D-98 candidate 85; rulings D-98 candidate 97)

The E-64 kind `contract_cost_rollforward` had a catalogue entry (`reports/catalogue.py`, tie-out `TO_COST_ROLLFORWARD_BALANCES`) and no builder in `framework.BUILDERS`. F-CLO's `KeySpec` on `sprint/l18` (aa90492b; S15-R-20a) keys the frozen dataset (`cost_kind`, `line_code`) with "design" provenance.

| Commit | Change |
|---|---|
| cf2632af | Docs first: SCREENS_B RPT-32 governed dataset shape (provisional 1.9); ENGINE_SPEC_B S15-R-20b (provisional 1.20); 04 T-CLS-05 companion (provisional 1.30). |
| (this commit) | SCREENS_B: grid = view-level pivot of the long dataset rows; ENGINE_SPEC_B S15-R-20b: per-kind opening / closing are the asset role's subledger balances (the platform holds no `cost_asset_version` table — `contract_cost_asset` / `cost_asset_version` appear only in migration allow-lists and the privacy classification), Σ kinds ties to T-CON-09 `cost_asset_carrying`; this section. |

**Rulings (supervisor, D-98 candidate 97).** (a) Eight line codes per S15-R-17 — `OPENING`, `ADDITIONS`, `CLAWBACKS`, `AMORTIZATION`, `ACCELERATION`, `IMPAIRMENT`, `IMPAIRMENT_REVERSAL`, `CLOSING`; F-CLO changes its `KeySpec` for `COST_ROLLFORWARD` to `measures = ("amount",)`, provenance "builder", in `relock_diff.py` at its own merge prep (this lane never touches l18). (b) Long shape: one signed `amount` per (`cost_kind`, `line_code`) and entity, functional currency default, `transaction` only when single-currency else refused by name (RPT-07 pattern); the screen may pivot to the wide grid at view level.

**Open (stated, not decided here).** Section 2 "By cost asset" of RPT-32 is DEFERRED until its own row key (contract external id + cost-asset event key) is ruled; it is not part of the `COST_ROLLFORWARD` frozen dataset.

**Merge-prep numbers — APPLIED at the wave-end merge of main 065e7f65** (main's ENGINE_SPEC_B already carried a 1.20 row, ENG-C2 ENC-6, so the provisional number could not survive the merge): SCREENS_B 1.9 → 1.14 (F-LMG takes 1.13); ENGINE_SPEC_B 1.20 → 1.27 (ENG-C4 1.25 / 1.26); 04 1.30 → 1.44 (ENG-C4 1.43); every in-text "rev" reference swept.

**Code slice — DONE (wave end; main 065e7f65 merged as 99bf0a9e; builder 4787a4bb).** See §11.1.

### 11.1 The builder (4787a4bb) and its gates

| Commit | Change |
|---|---|
| 99bf0a9e | Merge main 065e7f65 (wave end). Conflicts in the three governed docs' revision headers and SCREENS_B's log table resolved keeping both sides; the supervisor-assigned numbers applied at this merge because main's ENGINE_SPEC_B already carried a 1.20 row (ENG-C2 ENC-6): SCREENS_B 1.9 → 1.14, ENGINE_SPEC_B 1.20 → 1.27, 04 1.30 → 1.44, cross-references swept. Preflight 10 passed; lint OK. |
| 4787a4bb | `backend/erev_api/domain/reports/builders/contract_cost_rollforward.py` rewritten to the governed long shape and registered in `framework.BUILDERS` with `PARAMETER_DEFAULTS[contract_cost_rollforward] = {currency_view: functional}` (D-87 L6-3-Q-29); `test_contract_cost_rollforward.py` rewritten; `test_rpt32_rpt36_spec_crosscheck.py` bound to the rev 1.14 grid and the registration. |

**What main carried before this slice.** The F-RPS + ENG-E1 preparation (82f98a8e, a37032a0; `docs/reviews/loop/prod/F-RPS-ENG-E1-prep.md` ruling Q-2) had left an INTERIM wide builder on main — unregistered, category rows × seven money columns with a `TOTAL` row, a section 2 "by contract and category", the JET-09e acceleration folded into `amortization` "pending ENG-C8 Q-1". The supervisor's dispatch (D-98 85 / 97) supersedes it: the acceleration now has its own line (the D-98 19 reason code), the shape is long and governed, and the builder is registered with its DB path NOT RUN here (the Q-2 registration gate is the supervisor's call; recorded, not decided by the lane).

**The builder.** Pure minor-unit core — `classify(account_role, entry_kind, dr_cr, reason_code, amount_minor)` by entry kind, side and reason code (`CLAWBACK`, `TERMINATION_ACCELERATION`); `rollforward(movements)` → lines per (entity, cost kind) with `OPENING` from the lines before the range, `CLOSING` = `OPENING` + Σ movements, one currency per entity (a second refuses by name); `dataset_rows` → one row per (entity, `cost_kind`, `line_code`) in E-83 and S15-R-17 order with typed Money cells (`tie_outs.money`; Codex C6-RPT-R1), header `entity_code`, `cost_kind`, `line_code`, `category_label`, `line_label`, `currency`, `amount` (the F-CLO KeySpec names); `check_key_columns` → refusal by name (`CostRollforwardRefusal`, the column named) when a key column is outside its governed set or a key repeats; `control_totals` → `opening` / `closing` per currency; `cost_tie` → `TO_COST_ROLLFORWARD_BALANCES` on both identities (per-kind `OPENING` + Σ movements = `CLOSING`; Σ `CLOSING` per currency = Σ T-CON-09 `cost_asset_carrying` at the range end). `build` reads the T-SL-04 lines of the two asset roles (with `reason_code` and the entity code) as of `known_at` (D-98 96), applies the functional-view default (`transaction` only single-currency; `FUNCTIONAL_ONLY` refusal otherwise), and reads `balances_at` for the tie. The previous lock's snapshot `CLOSING` as `OPENING` waits for F-CLO's locked-dataset reader (CLO-8); until then the subledger balance before the range is the only opening (S15-R-20b "else" branch). DB path NOT RUN in this lane (CPU-only slice).

**Tests (CPU; fail-first `.run/ENG-C8/enc1/cr-fail-first.log` rc 2 — `ImportError` against the interim builder).** `test_contract_cost_rollforward.py` (7): the eight line codes and the KeySpec header; classification by kind / side / reason (ACCELERATION and CLAWBACK by reason; LATE_EVENT / VOID lines classify by kind and side); K-02 / K-09 September 2026 — OBTAIN `OPENING` 8,005.48, `ADDITIONS` 6,480.00, `AMORTIZATION` (670.52), `CLOSING` 13,814.96, the other lines 0.00, no FULFILL rows, control totals, tie `PASS` against Σ carrying 13,814.96 and `FAIL` with a balance missing (the F-RPS figures kept); the MOD-CHK-112 shape — amortisation (1,000.00), acceleration (18,000.00), clawback (2,000.00), closing 0.00 as a typed zero; CHK-131 IFRS reversal (opening 15,000.00, (5,000.00), 10,000.00, 20,000.00) with a FULFILL kind and a second entity (24 rows, entity-prefixed keys, per-entity currency); refusals by name (second currency in one entity; a repeated or missing key column); registration with the default. `test_rpt32_rpt36_spec_crosscheck.py`: RPT-32 grid ↔ builder columns, the eight codes and labels quoted from SCREENS_B, the pivot sentence, registration of `contract_cost_rollforward` with `balance_aging` still unregistered.

**Gates (captured exit statuses; logs `.run/ENG-C8/enc1/`).** On 4787a4bb (`gates-cr-summary.txt`, START 03:52:04 → DONE 04:02:41, dirty 0): `make typecheck` rc 0; `make lint` rc 0; `pytest backend/tests/engine backend/tests/architecture backend/tests/unit` rc 0 — 2,581 passed, 1 xfailed. Before the commit: `unit/reports` + `unit/answer_keys` 274 passed; `make lint` rc 0 at the commit. The release selection and the COST / LOSS keys are re-captured on the record head (§11.2).

**Open.** Section 2 "By cost asset" (its key); the CLO-8 snapshot-opening branch; the DB-bound `build` (RPS-12 database test `test_cost_rollforward_k09_k02` on the admitted run); F-CLO's `KeySpec` change to `measures = ("amount",)` / provenance "builder" at its merge prep (D-98 97).

### 11.2 Merge preparation — READY TO MERGE at the record head

Main 065e7f65 is merged (99bf0a9e) and the supervisor-assigned revision numbers are applied: SCREENS_B 1.9 → **1.14** (Date line, log row, RPT-32 rev references), ENGINE_SPEC_B 1.20 → **1.27** (header entry, log row, S15-R-20b body), 04 1.30 → **1.44** (header entry, log row, T-CLS-05 companion); governed files touched by the lane on this branch: `docs/design/SCREENS_B.md`, `docs/accounting/ENGINE_SPEC_B.md`, `docs/04-DATA_MODEL.md` (plus this record). No migration on the lane; `relock_diff.py` (l18) untouched.

Re-captured on 07b074bc (`.run/ENG-C8/enc1/gates-mp-summary.txt`, START 04:06:32 → DONE 04:11:15, dirty 0; each stage `cmd; rc=$?`): `make lint` rc 0; `make typecheck` rc 0; `pytest backend/tests/unit/reports backend/tests/unit/test_governed_docs_revisions.py backend/tests/unit/test_repository_layout.py` rc 0 — 37 passed; `make answer-keys` on the nine COST / LOSS keys rc 0 — 9 selected, 9 passed; `make answer-keys` on the 220-id release selection rc 0 — 220 selected, 220 passed. The full CPU suites were captured on 4787a4bb (§11.1: 2,581 passed, 1 xfailed, rc 0); the record commits since carry docs only.

## 12. Batch ci on main 065e7f65 — SSP_KEY_NOT_FOUND in two F-RPS platform DB tests (integration fix to F-RPS's modules)

Dispatch (supervisor, 2026-09-20): of the three DB-bound platform answer-key failures in the batch's ci stage, TWO raise `SSP_KEY_NOT_FOUND` (this section); the third is F-RPS's separate approval-id assertion (below); diagnose before the lane's merge. Read-only evidence: `~/dev/erev/.run/supervisor/main-gates/run-065e7f65/ci.log` (7 failed, 3,710 passed).

**Diagnosis (CPU, no database).** Two failures — `tests/domain/answer_keys/test_platform_following_db.py::test_estimate_route_emits_estimate_changed_from_the_keys_values` and `tests/domain/answer_keys/test_platform_reads_db.py::test_reads_rebuild_the_book_and_read_state_digest_and_approvals` — raise `EngineError: SSP_KEY_NOT_FOUND (CV-15)` from the estimate-submission dry run (`estimates._dry_run` → `erev_engine.compute` → stage 05) and the activation compute. The finding detail in the log is `product_code AVM-PART, rule S05-R-02, ssp_book_code ""`: stage 05 finds no SSP book for the line, because the modules' `_world` (entity AVM-DE, EUR, product AVM-PART on TPL-PROD-UNITS, contract NS-SO-DE-5002 for 57,500.00 EUR) copies `test_estimates.py`'s K06 world but omits its `ssp_book("DE-LIST", EUR)` + `approved_ssp_version(… range_entry(AVM-PART, 90.00 / 100.00 / 110.00, EUR))`. The modules were born in F-RPS (cacec626, 58de9729), are not in T1's base 4ed5f423, and their lane recorded them "not run — databases not provisioned" (F-RPS-ENG-E1-prep.md §18 / §19), so they had never passed anywhere. Between 4ed5f423 and 065e7f65 stages 02, 03 and 05 changed only by ENC-6's `PERIOD_VC` marker in `original.py`; the ENG-COST-ENC-1 merge (571b7dfe) touched no SSP path. The reproduction (`test_s05_ssp_book_precondition.py`) passes identically on the current engine and on the archived 4ed5f423 engine (`.run/ENG-C8/enc1/base-engine`): no engine or lane regression. Codex's terminal cause matrix agrees (supervisor: "their _world omits SSP setup present in the cited K06 test_estimates fixture; ENG-COST / CV-21 or ENC-6 root cause is not proved").

**Kept separate (not touched; F-RPS PLAT-OVR-1).** `test_platform_following_db.py::test_override_is_created_and_submitted_with_the_keys_value_and_rationale` fails on `assert row["rationale"] == declared.rationale and row["approval_request_id"] is None` — the rationale matches; `approval_request_id` is the UUID of the `POLICY_OVERRIDE` request that `submit_override` creates by design (`overrides.py`, unchanged in the wave). Its world gains the SSP book with the module (the world is shared), its assertion is F-RPS's.

**Fix (89933d40; test-only, minimal, an integration fix to F-RPS's modules).** `test_platform_following_db.py` and `test_platform_reads_db.py`: `_world` approves the DE-LIST EUR book exactly as `test_estimates.py` does (`ssp_book` + `approved_ssp_version` + `range_entry`), with a comment naming the cause. New CPU test `backend/tests/engine/s05_allocation/test_s05_ssp_book_precondition.py`: a NARROWER absent / present SSP-precondition check on the engine (Codex packet 1222) — its bundle uses a POINT_IN_TIME template, not the fixture's TPL_PROD_UNITS (`UNITS_DELIVERED`), and it does not replay the factory world or prove the DB approval / estimate / activation paths; it pins that the K06-shaped EUR bundle without a book refuses by name with the S05-R-02 detail and that with the DE-LIST book the one-line contract allocates 57,500.00 EUR to O1. The DB tests stay NOT RUN in this lane. Codex packet 1222 (`PRODUCTION-C8-SSP-CI-CORRECTION-SOURCE-89933d40.md`) verified 89933d40: both SSP setups AST-identical to K06, worlds restorable, 23 assertions unchanged, no engine or API change.

**Other batch failures observed, not diagnosed here (other lanes):** `test_audit_api::test_verify_on_demand_returns_job` (ValueError: not enough values to unpack), `test_platform_ledger_resolver_db::test_ledger_resolver_ids_equal_rows` (workspace_adapter invoke), `test_control_evidence::test_ctl_042_verification_producer_records_execution` (files/store.py AttributeError `'str' object has no attribute 'joinpath'`), `test_t_mig_tables::test_db_03_migration_batch_transitions` (trigger message `UPLOADED → PROMOTED` mismatch).

**Gates on 89933d40 (`.run/ENG-C8/enc1/gates-ssp-summary.txt`, START 04:54:23 → DONE 05:00:52, dirty 0; each `cmd; rc=$?`):** `make typecheck` rc 0; `make lint` rc 0 (also rc 0 as the commit guard); `pytest backend/tests/engine backend/tests/architecture backend/tests/unit` rc 0 — 2,583 passed, 1 xfailed.


## 13. Re-merges of main before the ENG-C8 slot — 05c30117 (F-CLO landed) as 9de65124; b179900b (fctr2 landed) as d2525692 with two GOV-MARK-1 shape repairs

Supervisor instruction (2026-09-20): merge main at the announced heads only, keep every revision row of both sides, repair the DG-ARC-14 (GOV-MARK-1) shapes that main carried, re-run the lane gates with captured statuses, and report READY. No engine, builder, test or answer-key change is part of either merge; the lane's own commits are unchanged. The readiness matrix was not edited.

**9de65124 — merge of main 05c30117 into sprint/l10 (F-CLO landed).** Conflicts in `docs/04-DATA_MODEL.md`, `docs/accounting/ENGINE_SPEC_B.md` and `docs/design/SCREENS_B.md` resolved by hand: descending revision chains in each header, every revision row of both sides kept. Rows that main carried joined on one line by ` || ` restored as one row per line (SCREENS_B `| Date | … |` and `| Status | … |`). Gates (`.run/ENG-C8/enc1/gates-remerge-summary.txt`, START 2026-09-20 08:13:05 → DONE 08:24:38, head 9de65124, dirty 0; each stage `cmd; rc=$?`): `make lint` rc 0; `make typecheck` rc 0; focused rc 0 (302 passed); engine-arch-unit rc 0 (2683 passed, 1 xfailed); keys-rg-220 rc 0 (220 selected, 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved). DB path NOT RUN (lane database absent; CPU-only chain).

**d2525692 — merge of main b179900b into sprint/l10 (fctr2 landed); parents 9de65124 and b179900b.** `git merge-tree --write-tree 9de65124 b179900b` → tree `acc5b3beecbcdd2829fa7e3c5b69f22a4c45140d`; `CONFLICT (content)` in `docs/04-DATA_MODEL.md` and `docs/accounting/ENGINE_SPEC_B.md`; `docs/design/SCREENS_B.md` auto-merged. Resolution by hand, both sides kept:

- `docs/04-DATA_MODEL.md`: the `| Revision |` header chain reads 1.50, 1.49, 1.45, 1.44, 1.43, 1.40, 1.39, 1.38, … (main's 1.49 / 1.45 entries and the lane's 1.44 entry both present); the lane's row 1.44 kept once next to main's 1.49 / 1.45 rows.
- `docs/accounting/ENGINE_SPEC_B.md`: the `| Revision |` header chain reads 1.28, 1.27, 1.26, 1.25, 1.23, 1.22, 1.21, 1.20, … (main's 1.28 entry first, the lane's 1.27 entry second); rows 1.23 and 1.28 kept once each in main's order, the lane's row 1.27 after them.
- `docs/design/SCREENS_B.md`: no conflict; the header keeps `| Date | 2026-09-20 (revision 1.14) |` and `| Status | … |` as separate rows (main b179900b line 6 still carries `| Date | 2026-09-20 (revision 1.13) || Status | …` on one line; the merge took the lane's separated rows); rows 1.9, 1.12, 1.13, 1.10 and 1.14 all present.

**The two GOV-MARK-1 repairs (DG-ARC-14: one governed table row per line, bracketed by `|`; `.run/ENG-C8/enc1/gov-mark-repair.py`, dry run identical to the applied result; Codex 1622 item 3).**

1. `docs/accounting/ENGINE_SPEC_B.md` row 1.23. Main b179900b carries the file's introductory paragraph as a fifth cell of the revision row (five cells between the brackets). Repaired: the row ends `…five cause components (ENG-C4's `revenue_from_prior_period_obligations` builder shape). |` and the paragraph beginning `This file specifies stages 09 to 15 of the calculation pipeline. `docs/accounting/ENGINE_SPEC.md` holds the index of both parts …` stands once, as a paragraph, after the last log row (1.27). Text unchanged; only its position.
2. `docs/design/SCREENS_B.md` row 1.10. Main b179900b carries the caption glued to the row: `… the labels. No screen, control or copy change otherwise. |**Table 1.2-A Applied.**`. Repaired: the row ends `… the labels. No screen, control or copy change otherwise. |` and `**Table 1.2-A Applied.**` stands once, on its own line, after the last log row (1.14), immediately before table 1.2-A.

Checks on d2525692: no conflict marker in any of the three files; no ` || ` in `docs/accounting/ENGINE_SPEC_B.md` or `docs/design/SCREENS_B.md`; the four ` || ` occurrences in `docs/04-DATA_MODEL.md` are SQL / legacy concatenation prose already on main b179900b (same count), not glued rows. `git diff --check 9de65124 d2525692` reports trailing whitespace only inside files main carried from F-CTR (`docs/reviews/loop/prod/F-CTR-VC113-CONCESSION-ORIGIN-R1.md` and the two `drafts/VC113-CAND109*-CODE-DRAFT.patch` files), none in a file this lane touched.

**Gates on d2525692 (`.run/ENG-C8/enc1/gates-final-summary.txt`, START 2026-09-20 09:32:32 → DONE 09:42:46, head d2525692, dirty 0; each stage `cmd; rc=$?`, never a pipeline tail):** `make lint` rc 0; `make typecheck` rc 0; focused rc 0 (302 passed in 25.48s); engine-arch-unit rc 0 (2743 passed, 1 xfailed in 380.68s); keys-rg-220 rc 0 (answer-keys counts: 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved). DB path NOT RUN (lane database absent; CPU-only chain). The engine-arch-unit count moved 2683 → 2743 between the two merges because main's own tests landed (F-CLO, P5, F-CTR); no lane test was added or removed in either merge.

**READY TO MERGE** at the record head (this section's commit on top of d2525692). Slot order per the supervisor: engc8 → fadm3 → frps → c1b. Merged is not gate-measured: the next integrated batch measures the merged head. Nothing in this section is accounting approval.

**Inherited metadata cleanup folded into this slice (Codex packet production-20260920-1649 item 2; supervisor dispatch 2026-09-20).** Codex reads both shape repairs above as closing at source on d2525692 (not acceptance). One inherited defect remained: the SCREENS_B header **Owner** row (line 5) on d2525692 equalled the short lane-parent row and omitted main b179900b's five attribution clauses for revisions 1.8 (F-LMG), 1.9 (F-ADM), 1.12 (ENG-C4), 1.13 (F-LMG) and 1.10 (F-CLO), although their revision-log rows were present. Repaired docs-first: main b179900b's Owner row restored verbatim (all twelve clauses, none reworded or reordered) and the lane's own clause appended as the union — `revision 1.14 by lane ENG-C8 (COST_ROLLFORWARD producer; D-98 85 / 97)`. Verified by clause-set comparison (split on `; revision`): main's twelve clauses ⊆ the new row; the lane parent's seven clauses ⊆ the new row; the only clause not on main is the 1.14 attribution. No other line of SCREENS_B changed.
