# ENG-C5: engine lane, ENB-9 opening-balance flows through stages 10, 13 and 14 (ONB-CHK-121)

Lane builder record for lane ENG-C5 on `sprint/l1` (worktree `~/dev/erev-wt/l1`, fast-forwarded to main 3f6a75e, the merge of ENG-D1, before the first change). Binding: `docs/reviews/loop/prod/lanes/ENG-C5.md`; `docs/accounting/ENGINE_SPEC.md` rev 1.9 S07-R-04, S07-R-05, S07-R-08, S07-INV-01 to S07-INV-03; `docs/accounting/ENGINE_SPEC_B.md` S10-R-03, S10-R-08, S10-INV-05, S12-R-03, S12-INV-03, §14.2.2 (rev 1.11 by this lane); BUILD_SPEC ENB-9; D-88 L7-5-Q-9 (directs the lane), D-90 :572 (the key left the rc selection and moves post-rc with ENB-9), D-91 register "ONB-CHK-121 pre-cutover"; the common terms with the 12:16 slot amendment and the 13:38 clarification. Acquisition-policy approval (AD-27) is separate and is not claimed here. Every figure asserted by a test was derived with Fraction arithmetic in `.run/eng-c5/derive.py` (output `derive-output.json`) before the tests were written; the key's expected values are untouched.

Status vocabulary: everything below is **committed (lane)** and **lane-gate measured** on the head named in §Gates; nothing is merged.

## Where it stops next (measured before the change, base 3f6a75e)

`.run/eng-c5/probe_flow.py` → `probe-flow-base.jsonl` traced the key's checkpoint bundles stage by stage; `key-base-3f6a75e.log` holds the key's 12 mismatches (report snapshot `report-base-3f6a75e.json`).

| Checkpoint | Stage where it stops | Measured | Expected (key) |
|---|---|---|---|
| january-2026-asc606 | 07 | baseline recorded: method `RECOMPUTE_FROM_INCEPTION`, revenue_cum 120,000.00, billed_cum 240,000.00; segments `INCEPTION` only | (stage 07 is complete; BUILD_SPEC ENB-9 ticked) |
| january-2026-asc606 | 10 | `billed_cum` 0 at every period end; `position_obligation` −120,000.00 at d_v; B_u 0 → NP = −R | contract liability 110,000.00 at FY2026-P01 |
| january-2026-asc606 | 14 | FY2026-P01 posts Dr CONTRACT_LIABILITY / Cr REVENUE 120,000.00 with origin FY2025-P12 (the closed cutover period's target carried as LATE_EVENT) beside the 10,000.00 movement; the netting reclass then moves the debit balance to CONTRACT_ASSET 130,000.00 | Dr CONTRACT_LIABILITY / Cr REVENUE 10,000.00 only |
| january-2026-ifrs15 | 07 | baseline: `OPENING_BALANCES_AT_CUTOVER` (FAIR_VALUE_IFRS3), revenue 0, billed = fair-value share 90,000.00; segments `INCEPTION`, `OPENING_BALANCE` (x 90,000) | (complete) |
| january-2026-ifrs15 | 10 | `billed_cum` 0; NP = −7,500.00 → CONTRACT_ASSET 7,500.00 | contract liability 82,500.00 |
| year-end-2026 (both) | 10 / 14 | CONTRACT_ASSET Dr 10,000.00 / 7,500.00 where CONTRACT_LIABILITY Dr is expected | CONTRACT_LIABILITY Dr 10,000.00 / 7,500.00 |
| cutover-no-postings | — | passes on base (FY2025-P12 closed, its carry lands in FY2026-P01) | no lines |

Reading: no consumer stage read the stage 07 `OpeningBaseline` (only stage 15's rollforward did), although ENGINE_SPEC S07-R-05 states both flows: "`billed_cum` = the payload value; the ledger's pre-cutover billing … replaced by the payload cumulative values from the cutover date. Stage 14 treats the baseline as posted for every period ending on or before the cutover: targets for those periods equal the baseline and emit no intent."

## Commits on `sprint/l1` (main..HEAD)

| Commit | Files | Change |
|---|---|---|
| 44fe148 | `docs/accounting/ENGINE_SPEC_B.md` (rev 1.11) | **Docs first.** S10-R-03: `billed_cum` counts the stage 07 opening baseline from the cutover date in place of the ledger's lines dated on or before it. New S14-R-26: a role key whose subject carries an opening baseline emits no delta for a period ending on or before the cutover (the baseline is deemed posted) and the first later period measures from it; CHK-121 figures stated. Revision row and header. |
| 80052f0 | `docs/accounting/ENGINE_SPEC_B.md` (rev 1.11 row extended) | S10-R-08: B_u counts Σ baseline `billed_cum` from the cutover when every obligation of (c, e) carries a baseline with one cutover. S12-R-03: the baselines enter the control role as one netted flow per `<contract>@<entity>` at the cutover (BILLING credit or CREDIT_MEMO debit, `record_seq` None, source `<contract>@<entity>@<D>/opening_billed_cum`), creating the opening liability layer and posting nothing. |
| d1f45c4 | `stages/s10_billing_balances/billing.py`, `stages/s13_books/__init__.py`, `stages/s14_posting/assign.py`, `tests/support/onboarding_worlds.py` (new), `tests/engine/s13_books/test_s13_opening_balances.py` (new) | **Code.** Stage 10 `_Emitter.billed`: from the baseline's cutover the baseline `billed_cum` replaces the ledger's lines dated on or before it (`_dated_after`), cited as the `OPENING_BALANCE_ESTABLISHED` event's `opening_billed_cum` value (`_baseline_ref`, so `billed_cum` re-evaluates, P14); `_Emitter.unconditional` (B_u) likewise per contract under `_baseline_cutover` (every obligation at the entity with one cutover); `_billed_before` counts the baseline as billing before an `OPENING_BALANCE` boundary (remaining_billing since the cutover). Stage 13 `_opening_flows(ctx, allocated, balances)` beside `_control_flows` (untouched): one control-role flow per `<contract>@<entity>` at the cutover, Σ baseline `billed_cum` − the pre-cutover in-position lines `_control_flows` already emitted, so the stage 12 layers tie to NP (S12-INV-03). Stage 14 `_cutovers(st)` + `_Walker.deltas`: no delta for a period ending on or before the subject's cutover; the next period measures from the baseline (S14-R-26). |
| d54e05d | `docs/reviews/loop/sprint/ENG-C5.md` | Lane record with the CPU gates on d1f45c4 (the DB chain ran on this tree). |
| 4c1d0ae | `stages/s10_billing_balances/billing.py`, `tests/support/onboarding_worlds.py`, `tests/engine/s13_books/test_s13_opening_balances.py` | **C5-R1** (Codex `PRODUCTION-C5-OPENING-REVIEW-d1f45c4.md`): `_billed_before` returns the baseline alone for an OPENING_BALANCE segment (the baseline replaces the pre-cutover lines, as `billed()` does), so T-CON-11 `remaining_billing` is 0 with a prior invoice of 240,000 / 300,000 (d1f45c4 gave 240,000 / 300,000). The D-97 (14) tie test `test_chk_121_stage_12_layers_tie_to_the_net_position_in_both_books`. `chk_121(policies=...)`. |
| b2d4996 | `docs/04-DATA_MODEL.md` (rev 1.17), `docs/accounting/ENGINE_SPEC.md` (rev 1.10) | **Docs first, D-97 (11) v3:** table 15.4-C `ONBOARDING_DIFFERENCE_UNPOSTED` (ERROR, X `ENGINE`, stage 07, CV-15 no-output, subject/event bindings, never an input 422); table 0.8-A row; S07-R-07 clause; §7.5 Findings. |
| 9488b79 | `docs/04-DATA_MODEL.md` | Wording: CV-15 raises the finding's own code with the findings in its detail. |
| 8d520d8 | `stages/s07_onboarding/difference.py`, `tests/support/onboarding_worlds.py`, `tests/engine/s07_onboarding/test_s07_rules.py`, `tests/engine/s13_books/test_s13_opening_balances.py` | **D-97 (11) interim containment** (a non-zero revenue onboarding difference records `ONBOARDING_DIFFERENCE_UNPOSTED`; the compute fails closed) and **D-97 (13) JET-03 controls** (cutover only, later ENGINE invoice, repeat compute). |
| 0a2bd57 | `docs/02-PRD.md` (rev 1.5) | IMP-108 `ONBOARDING_DIFFERENCE_UNPOSTED` copy row (DG-ARC-13: one IMP row per §15.4 code). |
| 2454b91 | `tests/architecture/test_copy_catalogue_drift.py` | DG-ARC-13 pins 108 active codes / IMP-01 to IMP-108 (found by the full architecture run on 8d520d8: `test_dg_arc_13_imp_rows_cover_codes` 108 ≠ 107). |
| (this record) | `docs/reviews/loop/sprint/ENG-C5.md` | Lane record: R1, D-97 (11)–(14), final counts. |

## Fail-first evidence

- `fail-first-base-3f6a75e.log` (working tree with the world and four tests, base engine): **3 failed, 1 passed** — ASC606 January carried `('FY2026-P01', 'REVENUE_RECOGNITION', 'EVENT', 'CONTRACT_LIABILITY', 'D', 12000000, 'FY2025-P12')`; IFRS15 January `contract_liability_txn` 0 ≠ 8,250,000; year-end carried the same FY2025-P12 lines. The control test (a compute known at the cutover posts nothing; a repeat compute posts nothing new) passes on base as well.
- `fail-first-overlay-3f6a75e.log` (the five committed tests against `git archive 3f6a75e backend/erev_engine backend/erev_api` on `PYTHONPATH`, `erev_engine.__file__` confirmed under `.run/eng-c5/old/`): **4 failed, 1 passed** — the pre-cutover invoice test added after the fix also fails on base.
- Key: `key-base-3f6a75e.log` 12 mismatches → `key-after-fix.log` 1 of 1 passed (report snapshots `report-base-3f6a75e.json`, `report-after-fix.json`).

## Tests (d1f45c4)

`support/onboarding_worlds.py`: `chk_121(as_of, states, books, payload, extra)` — the key's world as an InputBundle (entity periods FY2025-P01 to FY2026-P12, periods after `as_of` future, FY2025-P12 closed; books ASC606 and IFRS15; the contract booked and activated on the cutover with inception 2025-01-01; the OPENING_BALANCE_ESTABLISHED payload of the key; GROUP `recognition.time_convention` MONTHLY_EVEN). `test_s13_opening_balances.py`:

| Test | Asserts |
|---|---|
| `test_chk_121_asc606_january_relieves_the_opening_liability` | FY2026-P01 journal exactly Dr CONTRACT_LIABILITY / Cr REVENUE 10,000.00 (no origin line); `contract_liability_txn` 110,000.00, `contract_asset_txn` 0; `billed_cum` 240,000.00 at FY2025-P12 and FY2026-P01, 0 at FY2025-P11 (the ledger before the cutover); trace re-evaluates |
| `test_chk_121_ifrs15_january_relieves_the_fair_value_liability` | 7,500.00 posted; `contract_liability_txn` 82,500.00; `billed_cum` 90,000.00 (the fair-value share) |
| `test_chk_121_year_end_2026_settles_both_books` | no line carries FY2025-P12; FY2026-P12 posts 10,000.00 / 7,500.00; REVENUE −10,000.00 (−7,500.00) in each of the twelve months; contract liability and asset 0 |
| `test_chk_121_cutover_posts_nothing_and_a_repeat_compute_posts_nothing_new` | a compute known at 2025-12-31 posts nothing in either book; a compute with January's intents posted adds nothing (control; passes on base too) |
| `test_chk_121_pre_cutover_invoice_lines_are_replaced_by_the_baseline` | the acquiree's ERP invoice of 240,000.00 dated 2025-06-01 in the ledger: `billed_cum` 240,000.00 at FY2025-P06 (ledger), FY2025-P12 and FY2026-P01 (baseline replaces it, not 480,000.00); January posts 10,000.00 only; CL 110,000.00; NP ties (the netted opening flow is 0) |

BUILD_SPEC ENB-9's stage 07 tests (`test_ex_07_a_opening_balances_mode_a`, `test_chk_121_business_combination`, `test_s07_inv_02_allocation_sum`) pass unchanged.

## C5-R1 (Codex `PRODUCTION-C5-OPENING-REVIEW-d1f45c4.md`, SHA-256 358d5778…)

Measured on d1f45c4 (`fail-first-r1-d1f45c4.log`): IFRS15 with the acquiree's invoice of 240,000.00 (300,000.00) dated 1 June 2025 in the ledger and the payload's remaining billing 0 → `billed_before` 330,000 (390,000), T-CON-11 `remaining_billing` 240,000 (300,000) instead of 0; the baseline billing 90,000, January 7,500.00 and the contract liability 82,500.00 were right. Cause: `_billed_before` summed the pre-boundary lines and then added the baseline, while `billed()` replaced them. Fix (4c1d0ae): for an OPENING_BALANCE segment with a baseline the billing before the boundary is the baseline alone. Tests: `test_c5_r1_ifrs15_remaining_billing_is_not_double_counted_by_a_prior_invoice[240000.00 | 300000.00]` (remaining_billing 0, `billed_before` 9000000, `plan` 0; January unchanged) and `test_c5_r1_monotonic_record_times_reproduce_the_same_figures` (events recorded 2026-01-01 12:00:01–04 UTC in stream order, bundle order kept; both books unchanged). The review's third raw failure (a missing IFRS fair value refusing with `OPENING_BALANCE_INCONSISTENT`, S07-R-03 `fair_value`, before the S07-R-08 invariant) is an expected-code mismatch of the probe, not a defect; nothing was changed for it.

## D-97 rulings applied

- **(14) `_opening_flows` beside `_control_flows` — accepted.** S12-INV-03 tie stated: with the baseline counted in B_u, Σ open `CONTRACT_LIABILITY` layers − Σ open asset layers equals the net position at every period end because the opening flow (Σ baseline `billed_cum` less the pre-cutover in-position lines `_control_flows` already emitted) is the only other credit; the flow settles the relief's asset layer first and opens the liability layer at the net position (S12-R-03). Proven for both books by `test_chk_121_stage_12_layers_tie_to_the_net_position_in_both_books` (FY2025-P12 and FY2026-P01: 120,000 / 110,000 ASC606, 90,000 / 82,500 IFRS15; no S12-INV-03 finding; opening flow 240,000 / 90,000 dated the cutover).
- **(11) `ONBOARDING_DIFFERENCE_UNPOSTED` — interim containment (8d520d8; docs b2d4996, 9488b79).** Stage 07 records the finding (ERROR) for a recorded revenue difference other than 0; CV-15 raises the finding's code with the findings in its detail and the computation produces no output; a difference of 0 (CHK-121) records nothing. Fail-first on 4c1d0ae (`fail-first-d97-11-4c1d0ae.log`): EX-07-B's −290.41 difference recorded no finding; the compute-level case (imported 100,000 vs recomputed 120,000) computed. Negative cases: `test_s07_r07_zero_difference_records_no_finding`; the CHK-121 payload computes. **Open work (owed, not built here):** the stage 14 posting consumer (S07-R-07: the difference posted once, dated `cutover_date`, in the RCP-04 period, `reason_code = ONBOARDING_DIFFERENCE`, the ordinary JET template of the role); difference production for the other S07-R-07 roles (ENGINE billing, deposits, refund liabilities, return assets — `difference.py` measures the revenue role only, so the guard protects only the recorded family); the exact error and admission contracts of the API compute, import commit and job channels beyond "the computation's finding, never an input 422". Codex's 10,000 ONBOARDING_DIFFERENCE observation confirms the missing consumer.
- **(12) AD-27 [G12].** The IFRS15 opening liability = fair value V apportioned by `largest_remainder(V, remaining ASC606 allocations, keys)` stands as the engine rule; CHK-121 has one obligation (share = V; baselines 240,000.00 ASC606 / 90,000.00 IFRS15) and therefore cannot validate a multi-obligation split when V differs from the remaining ASC606 allocations — that evidence obligation stays open under AD-27 (the accountant's split-basis question).
- **(13) JET-03 under ENGINE billing after a baseline — confirmed, JET-03-only.** `test_d97_13_jet_03_engine_billing_after_a_baseline_counts_post_cutover_invoices_only`: cutover only posts no JET-03 line; a later ENGINE invoice of 1,000.00 on 15 January 2026 posts JET-03 for 1,000.00 only (billed_cum 241,000.00, contract liability 111,000.00, no 240,000.00 line); a repeat compute posts nothing new. This closes neither the onboarding-difference posting nor every receivable-ownership assumption (the ERP holds the cutover receivables).

## Gates

CPU gates on d1f45c4 (measured):

| Gate | Result |
|---|---|
| `make lint` | OK (exit 0) |
| `make typecheck` | OK |
| `backend/tests/engine` + `backend/tests/unit` + `backend/tests/architecture` | 1676 passed, 1 xfailed (`.run/eng-c5/full-engine-unit-arch.log`) |
| merged `rg-selection.txt` (192 ids) | 192 selected; 192 passed, 0 failed (`keys-selection.log`, `report-selection.json`) |
| `make answer-keys` all active | 251 selected; 202 passed, 47 failed, 2 withdrawn (`keys-all.log`, `report-all.json`); against the merged-main failing set of c85bae3 (48 ids) exactly one id left it, ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION, and none joined (`keys-all-failed-lane.txt`) |
| ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION | 1 selected; 1 passed (`keys-onb.log`, `report-onb.json`); the key file is unchanged and re-enters `rg-selection.txt` at merge (supervisor edits the selection) |
| corpus pins | 251 files / 249 active / 244 engine hold |

DB gates (one hardened chain, `.run/eng-c5/chain.sh`: worktree lock `.run/gates/chain-lock.d` with an owner file, atomic `mkdir` slot claim with owner file and legacy flat file, liveness by PID and start time, DB-stage count per process per worktree excluding our own, release of our own lock and slot only):

| Stage (chain 75431, slot 1, 14:23–15:17, tree at d54e05d = engine d1f45c4) | Result |
|---|---|
| lock and claim | worktree lock taken 14:21:49; slot 1 claimed 14:23:04 after removing a provably dead stale claim (owner 4798, no such pid) |
| `make test-pg` | OK: backend 290 passed, 0 failed, 0 skipped |
| `make ci` | OK: backend 2746 passed, 0 failed, 1 skipped; vitest 614 passed, 0 failed, 0 skipped (`gate-ci.log`) |
| `make properties` | OK: 12 passed |
| `make parity` (unfiltered, alone) | 122 selected; 121 passed, 1 failed (`point_in_time_equivalence`, the standing exclusion; 121/121 filtered) |
| release | own slot claim and own worktree lock released 15:17:11 (`chain-summary.txt`) |

The follow-up commits 4c1d0ae, b2d4996, 9488b79 and 8d520d8 are engine-only changes measured by CPU gates (below); their DB evidence comes from the supervisor's merged-main batch or one more chain on the final head, as the supervisor decides.

CPU gates on the final head (engine 8d520d8; docs 0a2bd57 and pins 2454b91 on top):

| Gate | Result |
|---|---|
| `make lint` | OK (exit 0) |
| `make typecheck` | OK |
| `backend/tests/engine` + `unit` + `architecture` | 1682 passed, 1 xfailed, 1 failed on 8d520d8 (`full-engine-unit-arch-2.log`: `test_dg_arc_13_imp_rows_cover_codes`, the copy catalogue needing IMP-108 for the new code); after 0a2bd57 / 2454b91 the architecture suite is 72 passed (`arch-after-imp108.log`); the engine and unit suites are unchanged by those two docs/pin commits |
| stage 07 + opening-balance modules | 18 passed (`after-d97-11.log`) |
| merged `rg-selection.txt` (192 ids) | 192 selected; 192 passed (`keys2-selection.log`, `report2-selection.json`) |
| `make answer-keys` all active | 251 selected; 202 passed, 47 failed, 2 withdrawn (`keys2-all.log`); the 47 ids are identical to those on d1f45c4 (`keys2-all-failed-lane.txt`), i.e. the merged-main set less ONB-CHK-121 |
| ONB-CHK-121 | 1 selected; 1 passed (`keys2-onb.log`) |

Codex closed C5-R1 at 8d520d8 (`PRODUCTION-C5-R1-RETEST-8d520d8.md`): both prior-invoice cases give `remaining_billing` 0, monotonic-recording controls 48/48, the key's hashes and native close passes identical to d1f45c4, all 251 keys byte-identical, guard / JET-03 supplement 78/78 over 9 cases; the billing correction and the interim revenue-only containment are accepted. Qualification recorded: the boundary raw run retains the missing-fair-value error-code mismatch (a probe expectation, not a defect) and the intended non-zero-difference refusal, whose 12 downstream assertions are unreached, not passes.

## Open rows (owed, not built here)

| Item | Owner / disposition |
|---|---|
| S07-R-07 difference producers for the other roles (ENGINE billing, deposits, refund liabilities, return assets) | `difference.py` measures revenue only; the interim guard protects only that family — follow-up lane |
| Stage 14 posting consumer of `ONBOARDING_DIFFERENCE` (once, dated `cutover_date`, RCP-04 period, `reason_code = ONBOARDING_DIFFERENCE`, ordinary JET template) and the removal of the interim guard | follow-up lane |
| Exact error / admission contracts of the API compute, import commit and job channels for the compute-time finding | follow-up lane (D-97 (11) v3) |
| AD-27: multi-obligation IFRS fair-value split when V differs from the remaining ASC606 allocations | G12 (accountant); CHK-121 cannot evidence it |
| Foreign-currency opening baselines, stored replay, ledger persistence, release gates | outside this lane's evidence (Codex residuals) |
| DB evidence for 4c1d0ae, b2d4996, 9488b79, 8d520d8, 0a2bd57, 2454b91 | the supervisor's merged-main batch or one more chain on the final head, as the supervisor decides |

## Questions returned (not decided)

- **C5-Q-1 (AD-27, acquisition policy).** The IFRS15 opening liability is the fair value V apportioned by `largest_remainder(V, remaining allocations measured in the ASC606 book, keys)` (S07-R-08, unchanged); the flow now presents that share as the opening contract liability (billed baseline) and recognises it from 0. Whether V may exceed or fall short of the ASC606 remaining allocation in ways that need a different split basis is an AD-27 question; CHK-121 has one obligation (share = V).
- **C5-Q-2 (JET-03 in ENGINE billing mode after a baseline).** `_Emitter.unconditional_obligation` (the JET-03 invoice inputs per obligation under `billing.posting = ENGINE`) does not count the baseline: an acquired contract whose post-cutover invoices are ENGINE-billed would post JET-03 for those invoices only, which is the intended scope (the ERP holds the cutover receivables). Confirm or rule otherwise.
- **C5-Q-3 (ONBOARDING_DIFFERENCE posting, S07-R-07).** Stage 07 records the differences under `RECOMPUTE_FROM_INCEPTION`; no consumer stage posts them (grep: `differences_of` is read by no stage). CHK-121's difference is 0 (imported 120,000.00 = recomputed 12 × 10,000.00), so the key does not exercise it; a follow-up item, not built here.
- **C5-Q-4 (ownership).** `_control_flows` (ENG-B4) is untouched; the baseline enters the stage 12 layers through the sibling `_opening_flows`, wired at the `FxFlows` call site. Confirmation requested.

## Residual limits

- The stage 13 `_opening_flows` nets the baseline against the ledger's pre-cutover in-position lines by `unconditional_date` (credit memos by effective date); `_control_flows` dates ERP lines the same way (`_eligible_lines`), and a memo-only pre-cutover line (no unconditional date) contributes to neither.
- Only `<contract>@<entity>` groups whose obligations all carry a baseline with one cutover are treated as opening state for B_u and the control flow; a contract with a mixed set keeps the ledger behaviour (`_baseline_cutover` None) and would trip S12-INV-03 only if stage 07 established such a state, which it does not today.
- DB gates: see §Gates (one hardened chain).

## Phase 2 — ONB-DIFF-ROLES (D-97 (11) completion; readiness row)

Assigned after the ENG-C5 merge (22d9305; Codex closed C5-R1 at 8d520d8). Base: main 8d76fea merged into `sprint/l1` as **16e2a6f**. Binding as above plus the phase 2 assignment (scope (1)–(5)), the 16:08 amendment (short targeted DB tests only; none were needed — every gate below is CPU) and the phase 1 rows "owed, not built here". Figures asserted by the new tests were derived with Fraction arithmetic in `.run/eng-c5p2/derive.py` (`derive-output.json`) before the assertions were written; no answer-key expected value, golden file or `ENGINE_VERSION` changed.

Status vocabulary: everything below is **committed (lane)** and **lane-gate measured (CPU)** on head **0861dbc**; nothing is merged; no DB chain has run on this head.

### Commits (16e2a6f..0861dbc)

| Commit | Kind | Content |
|---|---|---|
| 219972c, 1f73e8b | docs first | `ENGINE_SPEC.md` rev 1.17: S07-R-07 rewritten per role family (imported member, template, once-only cutover posting, deemed-posted continuation; `ONBOARDING_DIFFERENCE_UNPOSTED` narrowed to unmappable role keys); table 0.8-A row (stages 07, 14). `ENGINE_SPEC_B.md` rev 1.16: S14-R-26 "Onboarding differences" consumer rule; Table 14-A `ONBOARDING_DIFFERENCE` note row (no part of its own). `04-DATA_MODEL.md` rev 1.25: 15.4-C row narrowed (stage 14 detail `part`; CV-15 behaviour; never an input 422) |
| 50be60d, 9fd2ca0 | docs first | S10-R-03 / S10-R-08 / S12-R-03 / S14-R-26 rev 1.16: under `RECOMPUTE_FROM_INCEPTION` an `ENGINE`-mode line dated on or before D is recomputed, not replaced; with such lines the baseline `billed_cum` is not counted in `billed_cum`, B_u or the stage 13 opening flow, and the JET-03 difference exists only then (without them the imported billing is the ERP's: no difference) |
| **0861dbc** | code + tests | below |

### Design (as built)

- **Producers = the stage 14 cumulative role targets.** The S07-R-07 difference of a role key is the role target at the cutover period − the imported role amount − what is already posted for that period. Imported role amounts (`s14_posting/onboarding.py`): the stage 07 `OpeningBaseline` member of the part's family run through the part's **own** Table 14-A template (`_shares` over a synthetic `PartTarget` carrying the imported amount; a split side takes the whole amount on `CONTRACT_LIABILITY`, so JET-03 imports tax 0). Openings are per obligation and, when every obligation of a `<contract>@<entity>` shares one cutover and method, per contract subject (members summed).

| Family (parts) | Imported member | Difference posts through | Fixture |
|---|---|---|---|
| Revenue relief (JET-02 principal, JET-04a) | `revenue_cum` | Dr `CONTRACT_LIABILITY` / Cr `REVENUE` | `test_revenue_difference_posts_once_at_the_cutover` |
| ENGINE billing (JET-03 invoice; credit-memo part 0) | `billed_cum`, tax 0 — only where `engine_lines_through` (ENGINE-mode lines of the contract dated on or before D on the S10-R-03 date) | Dr `ACCOUNTS_RECEIVABLE` / Cr `CONTRACT_LIABILITY` | `test_engine_billing_difference_posts_through_jet_03`; ERP-only control `test_d97_13_…` (no JET-03 at the cutover) |
| Deposits (JET-01b receipt; criteria-met and refund parts 0) | `deposit_liability` (0 while the payload carries no member) | Dr `BILLING_CLEARING` / Cr `DEPOSIT_LIABILITY` | `test_deposit_difference_posts_through_jet_01b_receipt` |
| Refund liabilities (JET-04b), return assets (JET-07c) | 0 (role keys absent from the mapping; the walker reads 0, the whole recomputed cumulative is the difference) | the family's template | mapping unit test only (no compute-level world with a pre-cutover refund liability or return asset under RECOMPUTE exists — owed) |
| Outside S07-R-07 (JET-05c, JET-06, JET-09 to JET-17) | — | deemed posted at D, no difference | `JET-14 promised` absent in the mapping unit test |
| Unmappable: JET-02 agent (split credit), intercompany counterparty, foreign functional currency | — | `ONBOARDING_DIFFERENCE_UNPOSTED` (ERROR, stage 14, detail `part`/`reason`/`recomputed`/`role`/`rule`; CV-15) | mapping unit test (three refusals bound to the obligation and the opening event) |

- **Consumer (`assign._Walker.difference`).** In the cutover period of a RECOMPUTE subject (not on `CLOSE_RELEASE`): one `RoleDelta` per role key with `amount = target − imported − posted(by_origin)`, `reason_code = ONBOARDING_DIFFERENCE` (VOID when voiding), class `EVENT`, `effective_date = cutover`, RCP-04 posting period with origin = the cutover period when that period is closed; trace node `posting_delta` on subject `<role subject>/ONBOARDING_DIFFERENCE`, formula `post.delta.v1` (two inputs: the target node and a `source_record` whose value is imported + posted; formula id and arity unchanged). Periods ending on or before D and the cutover period itself are then deemed posted (`previous = current`), so later periods post target − posted as before and a repeat compute posts nothing new (asserted in every compute-level test).
- **Stage 10 / 13.** One public predicate `billing.engine_lines_through(documents, contract_key, cutover)` used by `billed()`, `unconditional()` (B_u) and the stage 13 `_opening_flows` (my phase 1 sibling; `_control_flows` untouched); `_kept(line, floor, recompute)` keeps ENGINE-mode pre-cutover lines under RECOMPUTE. The book-loop `CostsView` carries `balances` so stage 14 reads the stage 10 documents (runtime protocol `BalanceSource`, the `PartSource` precedent).
- **Stage 07.** The rev 1.11 interim guard is withdrawn in 0861dbc — the same commit that covers every family; the refusal survives only as the stage 14 finding for unmappable role keys (scope (3)). `difference.py` still records the revenue-family node `onboarding_difference@…` for the reconciliation report.

### Fixtures and fail-first

| Test (module) | Asserts | Fail-first on the 50be60d engine (same tests, `PYTHONPATH` overlay of `git archive 50be60d`) |
|---|---|---|
| `test_revenue_difference_posts_once_at_the_cutover` (`s13_books/test_s13_onboarding_differences.py`) | CHK-121 ASC606 payload revenue 100,000.00 / remaining 140,000.00: one intent Dr CL / Cr REVENUE 20,000.00 in FY2026-P01, origin FY2025-P12, reason `ONBOARDING_DIFFERENCE`; REVENUE net P01 −30,000.00; CL 110,000.00; IFRS15 book no difference; repeat posts nothing | FAILED: `EngineError: ONBOARDING_DIFFERENCE_UNPOSTED: a stage collected a blocking finding (CV-15)` (the interim guard) |
| `test_engine_billing_difference_posts_through_jet_03` | POL-004 ENGINE, acquiree invoice 240,000.00 dated 2025-06-01, payload billed 200,000.00: Dr AR / Cr CL 40,000.00; `billed_cum` P01 240,000.00; the only AR line is 40,000.00; repeat nothing | FAILED: `[] == [('FY2026-P01', … 'ACCOUNTS_RECEIVABLE', 'D', 4000000)]` (silent) |
| `test_deposit_difference_posts_through_jet_01b_receipt` (world `deposit_recompute`: goods 1,200.00 booked 2026-01-01 NOT_A_CONTRACT, receipt 1,200.00 on 2026-02-15, cutover 2026-06-30, P01–P06 closed) | Dr BILLING_CLEARING / Cr DEPOSIT_LIABILITY 1,200.00 in FY2026-P07 origin FY2026-P06; no other intents; `deposit_liability_txn` 1,200.00 at P07; no trace mismatch; repeat nothing | FAILED: `[] == [('FY2026-P07', … 'C', 120000)]` (silent) |
| `test_zero_differences_and_opening_balances_mode_post_nothing_extra` | CHK-121 payload (difference 0) and `OPENING_BALANCES_AT_CUTOVER`: no `ONBOARDING_DIFFERENCE` intent, no finding | passed on both (control) |
| `test_imported_role_amounts_cover_every_s07_r07_family_and_refuse_unmappable_parts` (`s14_posting/test_s14_onboarding_differences.py`) | mapping per (entry kind, role) above; JET-14 absent; JET-04b/JET-07c keys absent; ERP-only JET-03 maps nothing; refusals `agent_split` / `intercompany` / `foreign_currency` | not runnable on the base (the module under test does not exist there: ImportError) |
| `test_ex_07_b_recompute_from_inception` (amended: `twice.findings == ()` again) | EX-07-B's −290.41 difference records no finding | FAILED on 50be60d: the interim finding was recorded (`fail-first-overlay-50be60d-s07-s13.log`) |
| removed: `test_d97_11_non_zero_onboarding_difference_fails_the_compute_closed` | superseded by the revenue fixture (the same world now posts instead of refusing) | — |

Logs: `.run/eng-c5p2/fail-first-overlay-50be60d.log` (3 failed, 1 passed), `fail-first-overlay-50be60d-s07-s13.log` (1 failed, 16 passed).

### Gates (CPU, head 0861dbc)

| Gate | Result |
|---|---|
| `make lint` / `make typecheck` | OK / OK (the code commit was made inside `if make lint; then …`) |
| `backend/tests/engine` + `unit` + `architecture` | 1792 passed, 1 xfailed (`suites-final.log`; the phase 1 head had 1682) |
| stage 07, 10, 13 suites + the two new modules | 237 passed, 1 xfailed (the standing Q-11 xfail) |
| merged `rg-selection.txt` (220 ids, main 8d76fea) | 220 selected; 220 passed (`keys-selection.log`, `reports-selection/answer-keys/report.json`) |
| `make answer-keys` all active | 251 selected; 221 passed, 28 failed, 2 withdrawn (`keys-all.log`); the 28 ids (`keys-all-failed-lane.txt`) are **identical** to the pre-code baseline measured on the same tree with the 50be60d engine overlaid (`keys-all-base50be60d.log`, `keys-all-base-failed.txt`: 251 / 221 / 28 / 2) — none left, none joined |
| ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION | 1 selected; 1 passed (`keys-onb.log`) |
| DB gates | none run on this head (CPU-only per the assignment); one hardened chain under the l1 lock when admitted, or the supervisor's merged-main batch |

### Owed / not built here

| Item | Disposition |
|---|---|
| AD-27 evidence obligation (IFRS fair-value split basis) | open; record only (scope (5)) |
| Compute-level worlds for JET-04b / JET-07c differences and for a stage 14 refusal (agent split, intercompany, foreign functional currency) under RECOMPUTE | mapping is unit-tested; the CV-15 raise of a stage 14 ERROR finding is the unchanged phase 1 mechanism, but no end-to-end world asserts it for these role keys — follow-up |
| Foreign-currency openings | refused (`foreign_currency`), not measured; the difference node carries `amount_functional = amount_txn` only for the same-currency case |
| Stored replay / ledger persistence / release gates of the new deltas | outside this lane's evidence |
| Channel contracts (API compute, import commit, job) | the engine contract is pinned (CV-15 raises the finding's code with the findings in `detail`; never an input 422, 04 15.4-C); the channels' status mapping is the generic `EngineError` path and was not re-tested here |

### Questions returned (not decided)

- **P2-Q-1 (cutover inside a period).** The difference is measured against the role target at the end of D's period (stage 14 targets are per period end), so a cutover that is not a period end folds the post-D movements of that period into the `ONBOARDING_DIFFERENCE` line dated D. CHK-121 and every fixture use a period-end cutover. Either require D = period end under RECOMPUTE (a stage 07 finding) or measure the target at D exactly — policy.
- **P2-Q-2 (JET-03 credit memos).** The imported `billed_cum` is net of the ERP's credit memos while the JET-03 invoice part is the gross-billing target and the credit-memo part imports 0; a pre-cutover ENGINE credit memo under RECOMPUTE would therefore shift the difference between the two parts. No fixture has one; confirm the mapping or rule a gross/net split of the imported member.
- **P2-Q-3 (imported deposit member).** `OpeningBaseline.deposit_liability` is 0 while the payload carries no deposit member (S07-R-07), so every recomputed pre-cutover deposit posts in full at the cutover — the intended reading of "the acquirer's opening balance sheet holds none", to confirm.

### Residual limits (phase 2)

- `engine_lines_through` treats an ENGINE-mode invoice line without an unconditional date as dated through the cutover (it is not dated after it); such a line does not count in `billed_cum` either, so the two stay consistent.
- The `ONBOARDING_DIFFERENCE` delta's trace cites the target node and one `source_record` (imported + posted) because `post.delta.v1` takes two inputs; the imported and posted amounts are also carried as params (`imported`, `posted`, `cutover_date`).

### Phase 2 amendments — D-98 candidate 22 (P2-Q-1..3) and Codex C5-PH2-R1 / R2

Applied on `sprint/l1` after 366c329, before the admitted chain. Status vocabulary unchanged: **committed (lane)**, **lane-gate measured (CPU)** on the head named in the gate table below; nothing is merged.

| Commit | Kind | Content |
|---|---|---|
| db1d816 | docs first | 04 rev 1.26 (15.4-C `ONBOARDING_CUTOVER_NOT_PERIOD_END`, `ONBOARDING_MEMBER_MISSING`; §16.3 `cutover_date` period end, `obligations[].deposit_liability` optional member), ENGINE_SPEC rev 1.18 (S07-R-01 period-end cutover; S07-R-07 deposit member and credit-memo clause; table 0.8-A), ENGINE_SPEC_B rev 1.17 (S14-R-26), PRD rev 1.9 (IMP-112, IMP-113); DG-ARC-13 drift-test constants (110 active codes, IMP-01..110) |
| 2d90315 | docs | S07-R-07 credit-memo clause corrected to the measured mechanism: under `ENGINE` billing the JET-03 target is the net B_u carried by the invoice part, so the imported net `billed_cum` is compared net against net |
| 54707ad | code + tests | the three rulings (below) |
| ef9d262 | docs first | S14-R-26 explicit per-role-key eligibility (eligible / deemed posted / refused) and refund-component owner resolution (C5-PH2-R1, R2) |
| **e440a0d** | code + tests | C5-PH2-R1 and R2 |

**P2-Q-1 (ruled: D must be a period end).** `opening.consistency` records `ONBOARDING_CUTOVER_NOT_PERIOD_END` (ERROR; subject = the contract; detail `cutover_date`, `entity`, `period_key`, `period_end`; rule S07-R-01) when the cutover is not the end of the period containing it for a contracting entity of the contract's obligations; CV-15 raises it and nothing is established. Test `test_mid_period_cutover_is_refused_closed` (deposit world, cutover 2026-06-15 in FY2026-P06 ending 2026-06-30). Mid-period measurement "at D exactly" recorded post-rc. No corpus key or fixture carries a mid-period cutover (CHK-121 2025-12-31; EX-07 2023-01-31 / 2025-12-31; the deposit world 2026-06-30; the stage 01 test's 2023-02-02 never reaches stage 07).

**P2-Q-2 (ruled: net acceptable at rc).** `test_pre_cutover_engine_credit_memo_conserves_the_net_billing_difference[200000.00 | 190000.00]`: an ENGINE invoice of 240,000.00 and a credit memo of 40,000.00 before the cutover post nothing against an imported 200,000.00 and the net 10,000.00 once against 190,000.00; `billed_cum` 200,000.00. Measured mechanism (2d90315): under `ENGINE` billing the JET-03 target is the net B_u (S10-R-08) carried by the invoice part, the credit-memo part carries no target of its own, so net is compared with net — the gross-part limitation is recorded (no gross invoice / credit-memo cumulatives are imported; post-rc optional `credit_memo_cum`). The proof passes on the pre-ruling engine as well (a control, not fail-first).

**P2-Q-3 (ruled: never assume 0).** `MEMBERS` gains the optional `deposit_liability`; `Row.optional()` yields None when absent; `OpeningBaseline.deposit_liability: int | None` at all three construction sites; `Opening.members` carry None (contract-level sums None when any obligation omits the member). `imported_role_amounts` records `ONBOARDING_MEMBER_MISSING` (ERROR; the part's subject — the deposit's `<contract>@<entity>`; detail `member`, `part`, `recomputed`; rule S07-R-07) when the member is absent and the recomputed target is non-zero; an explicit 0 posts the whole recomputed deposit (the deposit world's default payload now carries `deposit_liability` 0.00); an absent member with a zero target records nothing (the CHK-121 worlds). Tests `test_absent_deposit_member_with_recomputed_deposits_is_refused_closed`, the mapping unit test's absent-member cases. `billed_cum` absent still reads 0 (a required-looking optional member) — the same principle would refuse it where JET-03 carries a difference; not applied without a ruling (P2-Q-5 below).

Fail-first on the db1d816 engine (`fail-first-overlay-db1d816.log`): 2 failed (both refusal tests DID NOT RAISE), 13 passed.

**C5-PH2-R1 (extra posting for deemed-posted families).** Root cause as Codex states: `difference()` ran for every opening role key and read an absent import as (0, 0), so a JET-14 promise of 1,000.00 dated 2025-01-01 posted Dr CUSTOMER_INCENTIVE_ASSET / Cr CONSIDERATION_PAYABLE 1,000.00 as `ONBOARDING_DIFFERENCE` in FY2026-P01. Fix: `onboarding.Imported(status, imported, recomputed)` per role key — `ELIGIBLE` (imported amount, a zero import included; recomputed = Σ shares of the eligible parts' actual targets), `DEEMED_POSTED` (family outside S07-R-07; JET-03 without recomputed ENGINE lines; absent optional member with a zero target) or `REFUSED`; precedence REFUSED > ELIGIBLE > DEEMED_POSTED; a key shared by an eligible and a deemed-posted part measures the eligible part only; `_Walker.difference` computes for `ELIGIBLE` only and never infers eligibility from key presence or amount; an unmappable part records its finding and no state (CV-15 blocks). Tests: `test_deemed_posted_family_posts_no_onboarding_difference` (Codex's counterexample through `erev_engine.compute`: no `ONBOARDING_DIFFERENCE`, no CONSIDERATION_PAYABLE / CUSTOMER_INCENTIVE_ASSET line, REVENUE and CONTRACT_LIABILITY journals identical to the plain CHK-121 world, January 10,000.00 posts, repeat posts nothing); the mapping unit test asserts the full state table (JET-04b / JET-07c `ELIGIBLE` with imported 0 and the whole recomputed cumulative; JET-14 `DEEMED_POSTED`; ERP-only JET-03 `DEEMED_POSTED`; absent deposit member `REFUSED`); the signed-zero controls and the existing revenue / billing / deposit fixtures unchanged.

**C5-PH2-R2 (component openings resolve the owner).** `onboarding.resolve(found, subject_key)`: exact lookup, else a refund-liability component `<group>@<entity>/<KIND>/<source>` with `KIND` in `RETURN`, `CONCESSION` resolves through its source to the owner obligation's opening (`source == owner` or `source.endswith("/" + owner)`); used by `imported_role_amounts` and `_Walker.deltas` before the cutover, eligibility and refusal checks; the role keys keep the component subject. Scope as ruled: not generalised to TERMINATION / VARIABLE_CONSIDERATION / UNCLAIMED_PROPERTY components or to the per-obligation return assets (P2-Q-4). Test `test_s14_component_openings.py::test_refund_component_resolves_its_owner_opening_and_posts_the_cutover_difference` (walker level on the CHK-121 allocated state after stage 07: native key `CG-1@US01/RETURN/C-ACQ-SUB/L1-SUB`, JET-04b 500 minor units from FY2025-P06): FY2025-P06 posts nothing; the zero-import difference posts once — Dr CONTRACT_LIABILITY 500 / Cr REFUND_LIABILITY 500, `ONBOARDING_DIFFERENCE`, FY2026-P01 with origin FY2025-P12 — on the component subject; FY2026-P01 no movement. This is also the zero-import positive control R1 requires.

Fail-first on the 54707ad engine (`fail-first-overlay-54707ad.log`): 2 failed, 8 passed — the counterexample posted the extra 100000 minor units (`CONSIDERATION_PAYABLE C 100000` in FY2026-P01 origin FY2025-P12), and the component posted `('FY2025-P06', '', None, 'CG-1@US01/RETURN/C-ACQ-SUB/L1-SUB', 'CONTRACT_LIABILITY', 500)` without the onboarding reason and nothing at the cutover, as Codex reported.

**Codex raw outcomes (recorded as stated, not re-derived):** public matrix 90/94 with four invalid `deposit_liability`-member oracles (the member did not exist in the canonical payload at 366c329; it exists from db1d816 / 54707ad with the semantics above — the four oracles remain Codex's to re-run); role-family helpers 18/21 (three failed assertions: H1 out-of-family posting, H2 component opening); 11 supported public cases 79/79; ONB-CHK-121 five checkpoints with zero comparator mismatches, key SHA unchanged. Phase 2 is not closed on the passing partial matrix; closure is Codex's after the corrections.

#### Gates (CPU) on the amendment head

Head **e440a0d** (R1/R2 code on top of ef9d262); the D-98 head 54707ad was measured the same way (`suites-final2.log` 1796 passed / 1 xfailed; `keys-*-run3.log` identical counts).

| Gate | Result |
|---|---|
| `make lint` / `make typecheck` | OK / OK (both code commits made inside `if make lint; then …`) |
| `backend/tests/engine` + `unit` + `architecture` | 1798 passed, 1 xfailed (`suites-final3.log`) |
| stage 07, the onboarding-difference modules, `s14_posting`, opening balances | 127 passed |
| merged `rg-selection.txt` (220 ids) | 220 selected; 220 passed (`keys-selection.log`) |
| `make answer-keys` all active | 251 selected; 221 passed, 28 failed, 2 withdrawn (`keys-all.log`); the 28 ids (`keys-all-failed-lane-r12.txt`) are identical to the pre-phase-2 baseline (`keys-all-base-failed.txt`) — none left, none joined |
| ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION | 1 selected; 1 passed (`keys-onb.log`) |
| DB gates | none on this head yet; the admitted chain follows the merge of main (post-P1 cdcf372) into `sprint/l1` |

#### Questions returned (not decided)

- **P2-Q-4 (component kinds outside the ruled scope).** TERMINATION, VARIABLE_CONSIDERATION and UNCLAIMED_PROPERTY refund components (sources: an event key or an estimate key) and the per-obligation return assets do not resolve to an opening; a RECOMPUTE contract carrying one before the cutover would post its pre-cutover movements ordinarily (the R2 shape). No fixture has one; scope was ruled narrow — confirm or extend.
- **P2-Q-5 (`billed_cum` absent).** An absent `billed_cum` reads 0 (`Row.value`), so under RECOMPUTE with ENGINE lines through the cutover the whole recomputed billing would post as the JET-03 difference; the P2-Q-3 principle ("never assume 0") would refuse it instead. Not applied without a ruling.

#### Codex retest of e440a0d at 534f4e7 (recorded verbatim, not re-derived) and the D-98 35a ruling correction

`PRODUCTION-C5-CORRECTION-RETEST-534f4e7.md` (SHA256 0ee33bdd…; manifest 45f13f7b…): **C5-PH2-R1 CLOSES** — the unchanged public CPC program 3/3 (2/3 on 366c329); input SHA 3b02dd46… unchanged; the extra USD 1,000 onboarding entry gone; every non-trace field and journal equals the pre-defect 50be60d baseline; replay and repeat pass. **R2 passes at the complete cumulative-target helper boundary** — June–December PartTargets 14/14 (4/14 before); RETURN and CONCESSION resolve the owner, preserve the component identity, suppress the pre-cutover posting and emit exactly Dr CONTRACT_LIABILITY 500 / Cr REFUND_LIABILITY 500 minor at 31 December with `ONBOARDING_DIFFERENCE`; a zero import is ELIGIBLE; the owner lookup precedes the FX refusal; deemed-posted emits nothing. Qualifications as Codex states them: the unchanged sparse helper stays 18/21 raw (one old expectation now sees explicit DEEMED_POSTED states; two June-only component vectors omit the cutover-period target) — the sparse 21/21 and the full phase 2 are **not** labelled complete; public 94/94 is qualified (ten revenue/billing inputs byte-identical 74/74; four deposit inputs use the revised fixture); the supplement 21/21 recalculating every event hash passes (imports 0 / 500 / 1,500 / 500 against receipts of 1,200 → signed differences 1,200 / 700 / −300 / −500); a truly absent deposit member with a non-zero target refuses `ONBOARDING_MEMBER_MISSING`; 90/94 and the old unsupported-input qualifications are preserved. Codex retest targets after this: dcd6c1a (P2-Q-4/5) and 320a92f (the merged tree the chain measures).

**Ruling correction (D-98 35a; the lead, Codex concurring).** The P2-Q-4 fail-closed refusal is the interim containment only. Owner resolution for `TERMINATION`, `VARIABLE_CONSIDERATION` and `UNCLAIMED_PROPERTY` refund components — with lane-synthesised fixtures per kind, since no corpus fixture exists — is an **ENG-C5 phase-3 slice owned by this lane, required before the final integrated gates**, not a post-rc item; per-obligation return assets are outside it (they carry the obligation subject and resolve already; deviation accepted). The spec wording "post-rc" was corrected docs-first in the commit preceding this record's. The slice starts after the admitted chain.

#### D-98 candidate 35 (P2-Q-4, P2-Q-5), the merges of main and the admitted chain

| Commit | Kind | Content |
|---|---|---|
| 87f48b3 | docs first | S07-R-07 / 0.8-A, S14-R-26, 04 15.4-C and §16.3: the three unresolved component kinds fail closed; an absent `billed_cum` with recomputed `ENGINE` billing refuses; per-obligation return assets resolve directly (rev 1.18 / 1.17 / 1.26 rows extended) |
| dcd6c1a | code + tests | P2-Q-4: `onboarding._unresolved_component` — a `TERMINATION` / `VARIABLE_CONSIDERATION` / `UNCLAIMED_PROPERTY` component whose source names a contract with a RECOMPUTE opening and whose part period ends on or before the cutover records `ONBOARDING_DIFFERENCE_UNPOSTED` (reason `component_owner_unresolved`, `kind`, `part`, `recomputed`; the component subject; the opening event) once per component and part; parts starting after the cutover are silent; per-obligation return assets carry the obligation subject and need no resolution (no refusal added — a refusal would contradict the S07-R-07 return-asset family; flagged to the lead). P2-Q-5: `OpeningBaseline.absent_members` (`OPTIONAL_MEMBERS` = `billed_cum`, `deposit_liability`; `Row.absent`) at all three construction sites (the IFRS fair-value baseline marks `deposit_liability` only); an omitted `billed_cum` with a non-zero JET-03 target where `ENGINE` lines are recomputed through the cutover records `ONBOARDING_MEMBER_MISSING` on the obligation (the ENGINE JET-03 invoice part is per obligation); an explicit 0 posts the full difference (240,000.00 once); without recomputed `ENGINE` lines JET-03 stays deemed posted; stages 10 and 13 keep the baseline's 0. Tests: `test_unresolved_component_kinds_of_a_recompute_contract_fail_closed[TERMINATION | VARIABLE_CONSIDERATION | UNCLAIMED_PROPERTY]`, `test_absent_billed_cum_with_recomputed_engine_billing_is_refused_closed`, the mapping unit test's absent-`billed_cum` cases. Fail-first on the 534f4e7 engine (`fail-first-overlay-534f4e7.log`: 4 failed, 1 passed — DID NOT RAISE; no finding for the three kinds) |
| 534f4e7 | merge | main cdcf372 (P1: GATE-BIND-1 wrapped gate targets, release manifest) into `sprint/l1`, clean; CPU on the merged tree: lint OK, typecheck OK, touched modules + architecture 199 passed, engine + unit + architecture 1 failed / 1880 passed / 1 xfailed (`suites-merge.log`: `backend/tests/unit/deploy/test_supervisor_scripts.py::test_makefile_tf_validate_target`, fixed on main by deb69ed after P1 — not a lane defect), rg-selection 220/220, all active 221 / 28 / 2 identical to the baseline, ONB 1/1 (`keys-*-run5.log`) |
| **320a92f** | merge | main 7b4ba7f (COMMIT 19; includes deb69ed) into `sprint/l1` after dcd6c1a, clean; CPU on the merged tree: lint OK, typecheck OK, touched modules + architecture + the tf-validate unit test 217 passed; engine + unit + architecture 1885 passed, 1 xfailed in 369.85s (0:06:09) (`suites-merge2.log`); rg-selection 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved (`keys-selection.log`); all active 251 selected; 221 passed, 28 failed, 0 not run, 2 withdrawn; 251 not approved (`keys-all.log`), the failing set identical to the pre-phase-2 baseline (`keys-all-failed-lane-merge2.txt`); ONB-CHK-121 1 selected; 1 passed, 0 failed, 0 not run, 0 withdrawn; 1 not approved |

The ONE admitted hardened chain (`.run/eng-c5p2/chain.sh`: worktree lock `.run/gates/chain-lock.d` with an owner file, atomic slot claim with owner file and legacy flat file, liveness by PID and start time, DB-stage count per process per worktree excluding this worktree, release of own claims only; the Makefile gates `test-pg`, `ci`, `properties`, `parity` run through the GATE-BIND-1 wrapper in an immutable context cloned from this clean tree) starts on the head of this record commit and queues behind the held slots; its handle (PID, start time, slot) and stage results are in `.run/eng-c5p2/chain-summary.txt` and are recorded in a follow-up commit after END. Codex retest targets: e440a0d (R1/R2), dcd6c1a (P2-Q-4/5), 320a92f (the merged tree the chain measures).

#### The admitted chain on 50f7bfa (DB gates), the counter defect, and the Codex Q4/Q5 verification

**Chain 58664 (19:09:16) stopped on the lead's order — a counter defect, not load.** It claimed gate-slot-1 at 19:25:35 and then slept on "2 other DB stages running" while only one foreign stage ran: the supervisor batch's GATE-BIND-1 wrapped `ci` on main appears as two processes with two cwds (the outer `gate_report.py --exec` in `~/dev/erev`, the inner runner in `~/dev/erev/.run/gates/ctx-ci-7b4ba7fccd02-51106`). Dispatch-common was amended 19:25 ("wrapped stages count once"). I stopped my own chain by exact PID (its only child was `sleep 30`), released only the claims naming 58664 (gate-slot-1.d owner + flat file; `l1/.run/gates/chain-lock.d`), archived its summary (`chain-summary-58664-before-stop.txt`), and patched `.run/eng-c5p2/chain.sh`: every DB-stage process's cwd (via `lsof`) is normalised from `<root>/.run/gates/ctx-*` to `<root>` before `sort -u`, an unreadable cwd is held (distinct per PID), this worktree is excluded, distinct roots are counted (verified 1 against the live batch); a TERM/INT trap now releases only the script's own claims. Relaunched ONE chain: **PID 2908, start 'Sat Sep 19 19:28:33 2026', head 50f7bfa** (tree clean, unchanged). Not a time-based restart.

| Stage (chain 2908, gate-slot-1 claimed 19:30:33 after P2's chain 2508 took the slot first at 19:28:24; GATE-BIND-1 wrapped, immutable contexts cloned from 50f7bfa) | Result |
|---|---|
| lock and claim | worktree lock 19:28:33; slot 1 claimed 19:30:33; proceeded at foreign = 1 |
| `make test-pg` | OK: backend 291 passed, 0 failed, 0 skipped (19:31:04–19:33:16) |
| `make ci` | OK: backend 2963 passed, 0 failed, 1 skipped (the Q-11 XFAIL); vitest 647 passed, 0 failed, 0 skipped; build / lint / typecheck pass (19:33:17–20:26:49) |
| `make properties` | OK: 12 passed, 0 failed, 0 skipped |
| `make parity` (unfiltered, alone) | 122 selected; 121 passed, 1 failed, 0 skipped — the failure is `point_in_time_equivalence` (`shipped-db-equivalence`: the missing point-in-time parity reader, T1's GPB item, assigned to T1); recorded as measured, not substituted by a filtered 121/121 |
| release | own slot-1 claim and own worktree lock released 20:32:26 (`chain-summary.txt`; `DONE head 50f7bfa`) |

Codex observed the same chain at exact 50f7bfa (`PRODUCTION-C5-GATE-OBSERVATION-50f7bfa.md`, SHA256 727e36e7…): test-pg 291/0/0; ci backend 2,963 / 0 / 1 actual Q-11 XFAIL, frontend 647/0/0, build / lint / typecheck pass; properties 12/0/0; FULL parity 122 / 121 / 1 (`shipped-db-equivalence`); chain ended 20:32:26 and released slot 1 and the lock.

**Codex Q4/Q5 verification at 320a92f / dcd6c1a (recorded verbatim, not re-derived; `PRODUCTION-C5-Q45-RETEST-320a92f.md`, SHA256 4ff54081…, manifest e66c089e…).** Public billing 21/21 (vs 20/21) with five identical input hashes — an omitted `billed_cum` with USD 240,000 ENGINE billing refuses before output; explicit imports 0 / 200,000 / 260,000 give signed receivable differences 240,000 / 40,000 / −20,000; the four successful controls unchanged with balance and replay verified; a missing member without an invoice stays valid; every payload hash valid. Native component containment 32/32 (vs 26/32) across the three kinds × ordinary / percent-encoded identities — ERROR once per component / part with the correct opening event; no-opening, after-cutover and other-method controls unaffected; the return asset keeps its obligation owner (Dr RETURN_ASSET 500 / Cr COST_OF_REVENUE 500 minor at the cutover); the raw initial helper 31/32 stays (Codex's own shorthand COGS expectation; corrected literal only). Prior CPC 3/3 and dense RETURN / CONCESSION 14/14 remain green. Qualification: this verifies the interim refusal and the missing-member distinction only — not component owner resolution (the phase-3 slice, D-98 35a) or full phase 2 / 3.

Next dispatch (on the lead's word): the phase-3 owner-resolution slice.

## Phase 3 — component owner resolution (D-98 35a)

Dispatched after the chain on 50f7bfa (record 010a36e). Binding: the phase-3 dispatch (per-kind resolution rule, lane-synthesised fixtures incl. a mixed contract, owner-naming trace nodes, owner / conservation checks, explicit unresolved-owner refusals replacing the interim containment; return assets excluded per the accepted deviation), docs first, fail-first on 50f7bfa, CPU gates only, no merge of main. Status vocabulary unchanged: **committed (lane)**, **lane-gate measured (CPU)** on head **c61e5f7**; nothing is merged; no DB stage (the integrated batch measures after the merge). Figures derived with Fractions in `.run/eng-c5p2/derive.py` (`p3_*`).

| Commit | Kind | Content |
|---|---|---|
| fe417bd | docs first | ENGINE_SPEC rev 1.19 (S07-R-07 component owners; 0.8-A row), ENGINE_SPEC_B rev 1.18 (S14-R-26 owner resolution per kind, `owner` param, `component_owner_unresolved` for mixed contracts; interim containment withdrawn), 04 rev 1.27 (15.4-C row) |
| **c61e5f7** | code + tests | below |

**Resolution rule (as built; `onboarding.resolve(found, subject, entity)`).** A refund-liability component key `<group>@<entity>/<KIND>/<source>` (S10-R-13) resolves to the opening of its owner before the cutover, eligibility and refusal checks: `RETURN`, `CONCESSION` and `UNCLAIMED_PROPERTY` to the obligation their source names (`<contract>/<obligation>`, exact or as the suffix of `<event key>/<obligation>`); `TERMINATION` (source = the `CONTRACT_TERMINATED` event key) and `VARIABLE_CONSIDERATION` (source = the estimate key) to the `<contract>@<entity>` opening of the contract the source's head names (raw or CV-21 encoded id, matched against the openings' `contract_key`) at the component's entity — the opening `openings()` forms only when every obligation of the contract at that entity carries a baseline with one cutover and one method. The role keys keep the component subject; `Opening.owner` names the owner and the difference node carries it as the additive `post.delta.v1` param `owner`. `onboarding.unresolved()` names an explicit refusal when the component's contract carries openings but no owner resolves (a mixed contract — an obligation without a baseline, differing cutovers or methods — for a contract-owned kind; an obligation-owned component naming an obligation without a baseline): `ONBOARDING_DIFFERENCE_UNPOSTED` (ERROR; the component subject; detail `reason` `component_owner_unresolved`, `kind`, `contract`, `entity`, `owner_candidates`, `part`, `recomputed`, `role`, `rule`; the first candidate's opening event) once per component and part for parts in periods ending on or before the latest candidate cutover; a contract without openings stays ordinary. The rev 1.18 interim containment (`COMPONENT_UNRESOLVED`, `_unresolved_component`) is removed. Per-obligation return assets carry the obligation subject and resolve directly (no change).

**Fixtures (lane-synthesised; `tests/engine/s14_posting/test_s14_component_openings.py`, walker level on the CHK-121 allocated state after stage 07 with native component keys).**

| Test | Asserts |
|---|---|
| `test_component_resolves_its_owner_and_conserves_its_amounts_across_the_cutover[RETURN \| CONCESSION \| UNCLAIMED_PROPERTY \| TERMINATION \| VARIABLE_CONSIDERATION]` | dense JET-04b targets of 500 minor units from FY2025-P06 through the cutover and 700 in FY2026-P01: the six pre-cutover periods post nothing; the zero-import difference posts the whole 500 once at the cutover (Dr CONTRACT_LIABILITY / Cr REFUND_LIABILITY, `ONBOARDING_DIFFERENCE`, FY2026-P01 with origin FY2025-P12) on the component subject; the January movement 200 posts ordinarily; **conservation**: Σ deltas per role = 700 = the P01 target (imported 0 + difference 500 + movement 200) on both roles and the onboarding lines balance; the two difference nodes name the owner (`C-ACQ-SUB/L1-SUB` for the obligation-owned kinds, `C-ACQ-SUB@US01` for TERMINATION / VARIABLE_CONSIDERATION) and the cutover |
| `test_component_whose_parts_start_after_the_cutover_posts_ordinarily` | a TERMINATION component created after the cutover: no difference, no refusal, ordinary January posting |
| `test_mixed_contract_refuses_a_component_without_a_resolvable_owner[TERMINATION \| VARIABLE_CONSIDERATION \| UNCLAIMED_PROPERTY]` | one obligation with a baseline, one without: no `<contract>@<entity>` owner (or, for UNCLAIMED_PROPERTY naming the obligation without a baseline, no obligation owner) → the explicit refusal with the full detail, once per component and part; parts after the cutover record nothing |
| `test_a_contract_without_openings_keeps_every_component_ordinary` | no opening for the component's contract: nothing resolved, nothing refused |

Fail-first on the 50f7bfa engine (`fail-first-overlay-50f7bfa.log`: 9 failed, 1 passed): TERMINATION / VARIABLE_CONSIDERATION / UNCLAIMED_PROPERTY were refused outright (the interim finding) and RETURN / CONCESSION named no owner (`KeyError: 'owner'`); the mixed-contract and no-opening tests fail structurally there (the old `Opening` arity). The mapping unit test's `Opening` construction gains the owner.

### Gates (CPU, head c61e5f7)

| Gate | Result |
|---|---|
| `make lint` / `make typecheck` | OK / OK (code committed inside `if make lint; then …`) |
| `backend/tests/engine` + `unit` + `architecture` | 1891 passed, 1 xfailed in 384.71s (0:06:24) (`suites-phase3.log`) |
| stage 07, onboarding-difference modules, `s14_posting`, opening balances | 137 passed |
| merged `rg-selection.txt` (220 ids) | 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved (`keys-selection.log`) |
| `make answer-keys` all active | 251 selected; 221 passed, 28 failed, 0 not run, 2 withdrawn; 251 not approved (`keys-all.log`); the failing set is identical to the pre-phase-2 baseline (28 ids; none left, none joined) (`keys-all-failed-lane-phase3.txt` vs `keys-all-base-failed.txt`) — the lead's "58-id base" list was not available to this lane; the comparison is against the same-tree pre-phase-2 baseline |
| ONB-CHK-121 | 1 selected; 1 passed, 0 failed, 0 not run, 0 withdrawn; 1 not approved (`keys-onb.log`) |
| DB gates | none (per dispatch; the integrated batch measures after the merge) |

### Owed / limits (phase 3)

- **Compute-level worlds per kind.** The fixtures are walker-level on the CHK-121 allocated state with native component keys and synthetic JET-04b targets (the boundary Codex accepted for R2). Compute-level worlds (a pre-cutover `CONTRACT_TERMINATED` with `refund_amount`, a refund-settled VC element with an explicit target, a credits obligation expiring before the cutover) need S07-R-03-consistent payloads derived from a pre-compute (revenue_cum and the price in force per obligation at D); not built in this slice — owed, with the derivation helper as the natural next step.
- **Owner named on difference nodes only.** A component whose difference is 0 posts nothing and names no owner in the trace (no node without a formula).
- **Source forms assumed.** UNCLAIMED_PROPERTY's source is the obligation subject (`refund_liability._key(..., UNCLAIMED_PROPERTY, subject_key)`); CONCESSION's is `<event key>/<obligation subject>`; VARIABLE_CONSIDERATION's head is the encoded contract id (`refund_liability.py` :810, :363, :259). A portfolio-scoped estimate head (`PORTFOLIO:<code>`) names no contract and stays unresolved (no refusal unless the contract carries openings — it cannot be matched, so none).
- **Mixed methods.** A contract whose obligations carry baselines with differing methods or cutovers has no `<contract>@<entity>` opening: contract-owned components refuse; obligation-owned ones resolve per obligation.

### Codex C5-PH3-R1 (D-98 candidate 53) — folded into phase 3 after the record commit 92498b7

`PRODUCTION-C5-PHASE3-REVIEW-c61e5f7.md` (SHA256 5b26457a…; manifest 7548b192…, 31 artifacts, binding 8ebef142…; a peer source / raw-result check found no material correction). **Cause (as Codex states it, confirmed in source):** `onboarding._contract_of` accepted a source head matching either a raw contract id or its encoded form and returned the first match, although the source head is already canonical CV-21-encoded; raw ids `K/A` and `K%2FA` are distinct (encoding to `K%2FA` and `K%252FA`), and the native sorted order puts the second contract first, so its raw id stole the first contract's encoded source head (native `assign._component_contract` resolves the same source to `K/A`). **Effect:** with `K/A` under RECOMPUTE and the collider under OPENING_BALANCES (both US01), TERMINATION source `K%2FA/EV-000002` and VARIABLE_CONSIDERATION source `K%2FA/VC-REFUND` gave 700 minor standalone (500 cutover difference + 200 movement) but only 200 with the collider present — the wrong opening method dropped the USD 5 difference. **Correction:** docs first 28a09e5 (S07-R-07 / S14-R-26: the source head is matched against the encoded ids of the openings' contracts exactly, never a raw id); code **27e29cb** — `_contract_of` matches `head == encode_component(contract_key)` only, consistent with the refund producer and `assign._component_contract`; the unresolved-refusal lookup uses the same function; `derive_deltas` gains the additive `openings` kwarg (the synthetic-openings test seam). Tests: Codex's exact counterexample on synthetic openings (collider sorted first; both kinds; owner `K%2FA@US01`; signed role totals 700 with the collider present as in the standalone control; onboarding lines balanced; owner named) and the production regression on a valid chronology — `onboarding_worlds.two_contracts()` (`K/A` RECOMPUTE, `K%2FA` OPENING_BALANCES via CONTRACT-scope `onboarding.method` rows; inception 2025-01-01, opening 2025-12-31; contracts sorted by key) folded through stage 07 with both `<contract>@<entity>` openings present. Fail-first on the c61e5f7 engine (`fail-first-overlay-c61e5f7.log`): the four colliding cases resolved to the collider's OPENING_BALANCES opening. Retained by Codex without relabeling (recorded as stated): duplicate-posting probe 3/3; dense RETURN / CONCESSION 14/14; missing-billed public 21/21 (three outputs add two trace `owner` parameters each); interim component probe 20/32 with the 12 failures retained (six formerly blanket-refused inputs are intentionally resolvable under phase 3 — a documented behaviour change, not new defects, not a manufactured 32/32); phase-3 edge checks 46/50 and canonical-key supplement 8/12 = one defect repeated across the two kinds. Full public worlds, merged-source integration and production gates remain pending.

Gates (CPU) on **27e29cb**: `make lint` OK, `make typecheck` OK; engine + unit + architecture 1895 passed, 1 xfailed in 412.82s (0:06:52) (`suites-phase3b.log`); the onboarding modules 141 passed; rg-selection 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved (`keys-selection.log`); all active 251 selected; 221 passed, 28 failed, 0 not run, 2 withdrawn; 251 not approved (`keys-all.log`), the failing set identical to the pre-phase-2 baseline (28 ids; none left, none joined) (`keys-all-failed-lane-phase3b.txt`); ONB-CHK-121 1 selected; 1 passed, 0 failed, 0 not run, 0 withdrawn; 1 not approved. No DB stage; no merge of main.

**Codex CLOSES C5-PH3-R1 at exact 27e29cb (docs 28a09e5) — recorded verbatim.** `PRODUCTION-C5-PH3-R1-RETEST-27e29cb.md` (SHA256 d2ad39a3…), manifest 2f8c1322… (20 artifacts): unchanged originals — identity 12/12 (old 8/12), edge 50/50 (old 46/50); programs, inputs and oracles unchanged; separate valid-chronology controls 18/18 (native stages 01–08 construct both openings; `derive_deltas` uses its default state lookup, not the new override seam); both TERMINATION- and VARIABLE_CONSIDERATION-shaped sources retain the intended encoded owner, USD 5 cutover + USD 2 movement, signed conservation, trace ownership / re-evaluation and repeat behaviour. Bounded: closed at the tested owner / role-delta boundary only; the refund target vector remains synthetic; native opening construction does not establish full termination / estimate producer behaviour; the original failures, the 20/32 interim refusal-oracle result, public producer worlds, DB / API posting, merged-source review and final gates keep their own scope. The merge into main waits for the lead's word (C5 is in the merge group after the batch).
