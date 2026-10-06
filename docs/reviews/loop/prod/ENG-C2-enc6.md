# ENG-C2 — ENC-6 right to invoice, usage, minimum commitments, prepaid drawdown (lane record)

Production-readiness programme, engine lane ENG-C2 (writer: the ENG-C1 / C1b agent, second
assignment; ownership confirmed FINAL by the supervisor on 2026-09-19 after a double dispatch — see
§7, 17:50). Worktree `~/dev/erev-wt/l21`, branch `sprint/l21-enc6` from main 8d76fea (main frozen
for the interim batch; merged in later on the supervisor's word). Governing text: BUILD_SPEC ENC-6
(`docs/BUILD_SPEC.md:5291-5317`), ENGINE_SPEC_B §9.2.6 S09-R-18 to S09-R-21 and EX-09-E, ENGINE_SPEC
S04-R-06, POLICIES POL-092, POL-240, ALG-03 Table 2.4-A (CHK-014), §5.1 PT-01 (CHK-110), D-87
L6-5-Q-16 ("delivered quantity × unit price is the right to invoice, before the invoiced-amount
fallback; S01-R-17 over-delivery does not apply"), the lane brief `lanes/ENG-C2.md`, the Codex
critical-path audit PRODUCTION-CRITICAL-PATH-AUDIT-8d76fea.md §1, and the common dispatch terms
(`.run/supervisor/d91/lane-dispatch-common.md` incl. the 12:16, 14:17 and 16:08 amendments).

Status legend: **not run — databases not provisioned** marks every DB-bound gate until the lane
databases `erev_rv_l21_{dev,test,e2e}` exist (Ray-side, DG-FORBID-03). CPU-only until then.

## 1. Setup (measured)

- `git worktree add ~/dev/erev-wt/l21 -b sprint/l21-enc6 8d76fea` — head 8d76fea ("Answer-key
  release selection: 205 → 220").
- Environment built without the setup script's database phases: `uv sync --project backend
  --frozen` (backend/.venv) and `npm --prefix frontend ci --ignore-scripts` (node_modules); lane
  `.env` written from the l5 template with the database names `erev_rv_l21_{dev,test,e2e}`
  (unprovisioned — nothing connects) and the l5 ports (no server is started in this lane).
- `make lint` OK on 8d76fea in l21 (`.run/l21-enc6/lint-0.log`).

## 2. Scope table

| Item | Rule | State on 8d76fea (measured) | Plan |
|---|---|---|---|
| `RIGHT_TO_INVOICE` recognition | S09-R-18; ALG-03 2.4-A; D-87 L6-5-Q-16 | not dispatched: `components.fixed_target` raises "the measure of progress is not built"; `progress_events.EVENT_FORMULAS` has no RTI method; no `PERIOD_VC` segment is ever created (the only marker-segment creation is `s05_allocation/original.py:106` for `ROYALTY`), so `schedule._realised_at` → `components.period_vc_realised` is unreachable | stage 05 opens a `PERIOD_VC` marker segment for RTI and DERIVED-usage obligations beside the `ROYALTY` one (S09-R-01: "right-to-invoice amounts" and DERIVED usage fees are `PERIOD_VC`); stage 09 `fixed_target` gains the `RIGHT_TO_INVOICE` / `USAGE` branches (the FIXED component — stand-ready fee or minimum — measured `TIME_ELAPSED`; X = 0 in the corpus keys); new `s09_recognition/usage.py` gives the RTI realised source in S09-R-18 / D-87 order — `USAGE_REPORTED.rated_amount` (usage_period_end ≤ d), else `DELIVERY_RECORDED` quantity × the line's `unit_price`, else invoiced amounts net of credit memos and taxes — consumed by the existing realised path |
| S04-R-06 realised amounts for RTI | S04-R-06 | `buildup.realised` prices `USAGE` (DERIVED) and royalty-bearing obligations only; an RTI line with `total_price 0.00` keeps TP 0 (REC-FS-08 expects TP = realised 36,000 / 72,000 / 108,000) | `buildup.realised` gains the RIGHT_TO_INVOICE case using the same source rule (one helper, shared with stage 09 — built once in `usage.py`, imported by both) |
| S01-R-17 over-delivery on RTI | D-87 L6-5-Q-16 | `ledger.py:222-228` fires `PROGRESS_OVER_DELIVERY` for delivered 120 against booked 1 (POS-CHK-010, REC-CHK-014) | method-aware exemption: the line's template method (product → default template version, or the line's template) is `RIGHT_TO_INVOICE` → no finding; a genuine unit over-delivery on a `UNITS_DELIVERED` obligation still fires (control test) |
| `USAGE` under POL-240 `DERIVED` | S09-R-19 | stage 04 realises the fees (TP); stage 09 fails at dispatch; no `PERIOD_VC` segment | as above; the realised amounts recognised at the end of their usage period through `period_vc_realised` (existing) |
| Minimum commitment / measurement-period TP | S09-R-20; PT-01; EX-09-E | ALREADY GREEN: VC-CHK-110 and VC-CAP-USAGE-QUARTERLY-MINIMUM-TRUEUP pass on 053813f (the FIXED component measured `TIME_ELAPSED`, TP re-estimated through stage 08 `TP_CHANGE`); Q1 35,000.00 / Q2 25,000.00 (`NORMAL` 35,000.00, `TP_CHANGE` (10,000.00)) | regression acceptance only (`test_chk_110_minimum_commitment_true_up` asserts the amounts; the `revenue_prior_period` (5,000.00) node is EDS-4 / ENG-C4 — recorded as the next stop, not built here) |
| Prepaid drawdown | S09-R-21 | ENG-C3's `breakage.redeemed_units` already counts non-royalty `USAGE_REPORTED.quantity` (merged in main) | `test_s09_r21_prepaid_drawdown` asserts the existing behaviour; no second implementation |
| POL-092 guard | S09-R-18 "POL-092 guard applied by stage 03" | stage 03 `measure.py` lists `RIGHT_TO_INVOICE` as a POL-091 option; no guard finding found (to confirm at slice 2) | if absent: a stage 03 finding when an RTI line's pricing carries an upfront fixed fee, minimum, tier, rebate or non-constant rate (`BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT`); `ALLOW` bypasses; REC-FS-08 ("no cap, minimum or upfront fee") stays allowed; POS-CHK-014 (`quantity 120 × unit_price 25 = total_price 3,000.00`, linear) stays allowed |
| Tier boundaries / period attribution / rating | S09-R-19, PT-01 | rating happens upstream (`rated_amount` on `USAGE_REPORTED`); no engine rating of tiers exists | no engine-side rating is built unless a key needs it (none of the six does); recorded |

## 3. Keys (failing set on 053813f; `.run/l21-enc6/report-053813f-all-active.json`)

| Key | Current failure | Facts | ENC-6 next stop |
|---|---|---|---|
| REC-FS-08-TM-RIGHT-TO-INVOICE | `ENGINE_INVARIANT_VIOLATED: the measure of progress is not built` | RTI; `USAGE_REPORTED` rated 36,000.00 per month (180 h × 200), line quantity 1, `total_price 0.00`, `unit_price 200`; expected TP = revenue_cum 36,000 / 72,000 / 108,000; unbilled receivable 36,000 at each month end (UNCONDITIONAL) | dispatch + `PERIOD_VC` marker + S04-R-06 RTI realisation |
| POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE | same invariant | RTI; `USAGE_REPORTED` 120 × 25 rated 3,000.00 in December; line 120 × 25 = 3,000.00 | as above (CHK-014: December revenue 3,000.00) |
| REC-CHK-014-S5-PROGRESS-VARIANTS-RTI | `PROGRESS_OVER_DELIVERY` (CV-15) | RTI; `DELIVERY_RECORDED` 120, booked quantity 1, `unit_price 25.00`, `total_price 0.00`; no `USAGE_REPORTED` | S01-R-17 exemption + D-87 delivered × unit price |
| POS-CHK-010 | `PROGRESS_OVER_DELIVERY` (CV-15) | same shape (P1-TM 120 × 25 = 3,000.00 beside MILESTONE and OUTPUT_PERCENT obligations); unbilled receivable 3,000.00, contract asset 2,000.00 | as above; then ALG-02/ALG-03 netting (existing stage 10) |
| POB-S2-EX12A-OWNVOLUMES | same invariant | `USAGE`, series, DERIVED; rated 20,000.00 / 15,000.00; `total_price 0.00`, `unit_price 0.01`; revenue_cum 20,000 / 35,000 | dispatch + `PERIOD_VC` marker (TP already realised by stage 04) |
| REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT | same invariant | `USAGE`, series; PMPM 50 → 55 by a `PRICE_CHANGE` amendment; rated 500,000.00 / 510,000.00 | as above; the amendment's effect on a `PERIOD_VC` series obligation is measured after the dispatch lands (next stop recorded then) |
| VC-CHK-110, VC-CAP-USAGE-QUARTERLY-MINIMUM-TRUEUP | PASS | S09-R-20 already built | regression acceptance |
| VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE | 2 mismatches: trace `revenue_prior_period:FS-02/L1-COMMIT:FY2026-P06` value 25,000.00 and formula `estimate.prior_period.v1` absent | VOLUME_TIER INCREASE under `ESTIMATE_MEASUREMENT_PERIOD_TP` | not ENC-6: EDS-4 / ENG-C4's node; the ruled figures (TP 220k / 280k / 295k, revenue 55k / 140k / 233,333.33 / 295k) are not touched |

AD-21 (measurement-period judgment for a VOLUME_TIER INCREASE under S09-R-20): the corpus scan
finds exactly one key carrying `VOLUME_TIER` with `direction: INCREASE` under
`ESTIMATE_MEASUREMENT_PERIOD_TP` — VC-FS-02. It is the only key blocked by AD-21; VC-CHK-110 and
VC-CAP-USAGE (also `ESTIMATE_MEASUREMENT_PERIOD_TP`) do not depend on it and pass. AD-21 is not a
blanket hold on the RTI / DERIVED work.

### 3.1 State after slice 1 (measured on the slice-1 tree, `.run/l21-enc6/keys-slice1e.log`)

`make answer-keys` on the eleven ids below, as measured on the pre-commit tree (`keys-slice1e.log`):
7 passed / 4 failed. **CORRECTION (Codex review of 9be54ed, PRODUCTION-ENC6-SLICE1-REVIEW-9be54ed.md):
the committed 9be54ed passes 3 of the 4 keys claimed green — REC-CHK-014 fails.** The measurement
was taken before the kernel's effective-date gate was removed to satisfy `test_s04_r06_realised_usage`;
the keys were not re-run after that change and before the commit (reproduced on a `git archive`
snapshot of 9be54ed: `enc6-r1-failfirst-9be54ed.log`, 1 failed / 3 passed). Base 8d76fea / 053813f:
3 / 8 of the same eleven — VC-CHK-110, VC-CAP-USAGE and POS-CHK-010-UNBILLED were already green.

| Key | State | Reason / next stop |
|---|---|---|
| REC-FS-08-TM-RIGHT-TO-INVOICE | PASS (turned green) | TP = allocated = revenue 36,000 / 72,000 / 108,000 |
| REC-CHK-014-S5-PROGRESS-VARIANTS-RTI | **FAIL at 9be54ed (CORRECTION)** — PASS from 8f33bf0 | Codex measured both checkpoints refusing `S04-R-02 Σ a_posted = allocation_basis` (600,000 vs 300,000 minor) at 9be54ed; this record's 7 / 4 claim was wrong for this key — see §7 (ENC6-R1). Green since 8f33bf0 (the kernel's effective-date gate) |
| POB-S2-EX12A-OWNVOLUMES | PASS (turned green) | DERIVED fees on `PERIOD_VC`; stage 13 re-pricing |
| REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT | PASS (turned green) | prospective `PRICE_CHANGE` on a `USAGE` series: boundary progress by time (S09-R-19), S06-INV-01 on basis − realised (`TpBuildUp.realised`) |
| POS-CHK-010-UNBILLED-RECEIVABLE-AND-CONTRACT-ASSET-SPLIT | PASS (unchanged) | control: no RTI line |
| VC-CHK-110, VC-CAP-USAGE-QUARTERLY-MINIMUM-TRUEUP | PASS (unchanged) | S09-R-20 regression acceptance |
| POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE | FAIL | revenue 6,000.00 vs 3,000.00: the line books `total_price` 3,000 = 120 × 25, so X = 3,000 on FIXED (time) plus 3,000 on `PERIOD_VC` — ruling D-98 candidate 28 (§6, R-1) |
| DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT | FAIL | same cause (`total_price` 12,000 = 480 × 25, term 2026-07-01 to 2028-06-30): expects revenue_cum 3,000 AND rpo_amount 9,000 = 12,000 − 3,000 — the FIXED allocation stays at the stated price — ruling 28 |
| POS-CHK-010 | FAIL (oracle) | only `end-of-p1` `transaction_price` 12,000.00 vs 15,000.00 (fixed 10,000 + 2,000 + realised P1-TM 3,000; S04-R-02 / 04 DB-17 V1); every other expectation green — ruling D-98 candidate 29 (§6, R-2) |
| VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE | FAIL (not ENC-6) | only the trace node `revenue_prior_period:FS-02/L1-COMMIT:FY2026-P06` (`estimate.prior_period.v1`, 25,000.00): stage 08 `decompose_prior_period` is exported but never called on main; sprint/l4 (C4, b8f56ae) wires it through stage 15 (S15-R-13) and VC-FS-02 passes there — closes when C4 merges; no orchestrator call added here |

## 4. Shared-component dependencies

| File / function | Owner today | ENC-6 change | Coordination |
|---|---|---|---|
| `s09_recognition/components.py` (`fixed_target` dispatch, `period_vc_realised`) | shared (ENG-T1F sprint/l19, C4 sprint/l4 active) | additive branches for `USAGE` / `RIGHT_TO_INVOICE`; the RTI source helper lives in `usage.py` | message sent to lane-eng-b3 (T1F) before editing; C4's agent name requested from the supervisor |
| `s05_allocation/original.py` (marker segments) | shared | `PERIOD_VC` marker beside the `ROYALTY` one | same |
| `s04_transaction_price/buildup.py` (`realised`) | shared | RIGHT_TO_INVOICE case | same |
| `s01_canonicalize/ledger.py` (`PROGRESS_OVER_DELIVERY`) | shared | method-aware exemption | same |
| `formulas.py` | shared | only NEW ids if any (existing ids and params untouched, DG-ENG-04) | same |
| `s09_recognition/breakage.py` (`redeemed_units`) | ENG-C3 (merged) | none (consumed) | — |
| `erev_engine/usage.py` (kernel: source rule, constants, S01-R-17 exemption predicate), `tests/engine/s09_recognition/test_s09_usage.py`, `tests/engine/s01_canonicalize/test_s01_right_to_invoice.py` | new (this lane) | built here; stage-neutral like `royalties.py` so stages 01/04/05/06/09 import no other stage's private module (DG-ENG-07) | layering adopted from lane-eng-c2-enc6's hand-over rationale (structure only; its "stated price is not fixed consideration" reading is overruled by D-98 candidate 28) |
| `stages/state.py` (`TpBuildUp.realised`, defaulted), `s13_books/__init__.py` (`_version_price` re-prices for `PERIOD_VC` as for `ROYALTY`), `s06_modifications/__init__.py` (S06-INV-01 = basis − realised), `s06_modifications/segments.py` (boundary progress of a realised-method FIXED segment by time) | shared | additive | T1F overlap map received (lane-eng-b3): no overlap with these; T1F touches `schedule.obligation_measures`/`_emit`, formula registries (new ids only) and narratives — this lane keeps its new formula id alphabetical and resolves any adjacent-insertion conflict at merge |

## 5. Slices

1. Fail-first tests on 8d76fea: `test_chk_014_right_to_invoice_revenue` (120 × 25 = 3,000.00 in
   December from `USAGE_REPORTED`; the D-87 delivery variant with booking quantity 1), the
   over-delivery control (`UNITS_DELIVERED` still raises `PROGRESS_OVER_DELIVERY`), `USAGE` DERIVED
   dispatch (EX-12A shape). Then the `PERIOD_VC` marker, the dispatch, the RTI source helper, the
   ledger exemption, S04-R-06 RTI realisation. Acceptance: REC-FS-08, POS-CHK-014, REC-CHK-014,
   POS-CHK-010, POB-S2-EX12A; REC-RB-05's next stop measured.
2. POL-092 guard (if absent) with its findings; `test_s09_r18_right_to_invoice_source` (all three
   sources), `test_s09_r19_usage_derived`, `test_s09_r21_prepaid_drawdown`,
   `test_chk_110_minimum_commitment_true_up` (regression amounts).
3. Gates: engine + architecture + unit CPU suites; `make answer-keys ID="$(cat
   docs/reviews/loop/sprint/rg-selection.txt)"`; all active against the base failing set
   (`~/dev/erev/.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; the ids this lane turns
   green listed); DB stages under the slot protocol once the lane databases exist.

### 5.1 Slice 1 — DONE (this commit)

Landed: `erev_engine/usage.py` (S09-R-18 source order as completed by D-87 L6-5-Q-16; S09-R-19
`derived_usage`; `right_to_invoice_lines` for the S01-R-17 exemption: product default template
version effective at the inception, no `POB_ASSIGNMENT` rule set in force, not the parity preset);
stage 05 `PERIOD_VC` marker segment for `RIGHT_TO_INVOICE` and DERIVED `USAGE`; stage 04
`realised()` RTI and USAGE cases through the kernel; stage 09 `fixed_target` dispatch (FIXED by time
for realised methods — superseded for RTI by ruling 28, slice 2) and `period_vc_realised` through
the kernel; stage 01 exemption with a `UNITS_DELIVERED` control and two withholding controls (rule
set in force; template version not effective); stage 13 `_version_price` re-pricing for `PERIOD_VC`
(the S04-R-02 identity failure every RTI/usage key died on: Σ allocated carried the realised amounts,
`tp_history[-1]` did not); stage 06 boundary progress for a realised-method FIXED segment (S06-R-17
on REC-RB-05); `TpBuildUp.realised` and S06-INV-01 on basis − realised (REC-RB-05 stopped at
allocated 0 vs basis 301,500,000).

Evidence (slice-1 tree): fail-first on 8d76fea `.run/l21-enc6/usage-failfirst-8d76fea.log` (4 failed);
`make lint` OK, `make typecheck` OK (566 files); stage suites s01 + s04 + s09 315 passed
(`derived_usage` unified the two usage loops: stage 04 now excludes royalty statements and stage 09
reads the same rule; `test_s04_r06_realised_usage` green); engine + architecture + unit
`.run/l21-enc6/suites-4.log`: **1,786 passed, 1 xfailed, 10 errors** — the 10 errors are the
DB-bound unit tests (`test_cli_idp` 2, `test_cli_operator`, `test_cli_tenant`, `test_lists` 2,
`test_time_zones`, `test_uow` 3) failing at fixture setup with `database "erev_rv_l21_test" does not
exist` — **not run — databases not provisioned**, not code failures (the same selection is green on
l5, which has its lane database); keys §3.1 7 / 4.

### 5.2 Slice 2 — ruling D-98 candidate 28 (this commit; docs first in 5c79178)

Landed: `progress.right_to_invoice_fraction` (public module; the shared arithmetic), kernel
`usage.above_stated` (the part of R above P, item by item — the S09-R-33 guarantee pattern),
formula `rec.progress.right_to_invoice.v1` (`formulas.py`, stage 09 `FORMULA_IDS`, narrative key
`rec.progress.right_to_invoice`), stage 09 `fixed_target` RTI branch (`_right_to_invoice_progress`:
f = min(1, R ÷ P); PROSPECTIVE g since the segment's boundary, Q-4) and `period_vc_realised` RTI
amounts above P, stage 04 `realised()` RTI amounts above P (S04-R-06 rev 1.21), stage 06 boundary
progress of an RTI FIXED segment by R ÷ P. The kernel gates deliveries, returns, invoices and credit
memos by their effective date and usage by its period end (an inception price never reads a later
delivery: REC-CHK-014 had briefly doubled to 6,000.00 when that gate was missing).

Fail-first on 5c79178 (`.run/l21-enc6/d98-28-failfirst-5c79178.log`): the three new tests failed
(POS-CHK-014 shape 3,000 not 6,000; DISC-S10 shape f = 0.25 with 9,000 of the FIXED allocation
unrecognised; R above P: FIXED 1,000 complete + 2,000 on `PERIOD_VC`). Now: `make lint` OK,
`make typecheck` OK, stage suites s01 + s04 + s05 + s06 + s09 + s13 558 passed / 1 xfailed
(`test_s09_usage.py` 7 / 7), eleven keys **8 passed / 3 failed** (`keys-slice2b.log`):
POS-CHK-014 turned green; POS-CHK-010 fails only on the candidate-29 oracle (12,000 vs 15,000, §5.3);
VC-FS-02 is C4's node (§3.1); DISC-S10-EX42 is a `runner: platform` key — the loader fails it
closed ("run_platform is not built yet, BUILD_SPEC PRP-1; XR-12") on every head, so its engine
shape is covered by `test_d98_28_disc_s10_partial_right_to_invoice_leaves_the_remainder_unrecognised`
and the key itself stays red until the platform runner exists (not ENC-6).

### 5.3 Slice 2 — ruling D-98 candidate 29 (this commit)

The ONLY answer-key expected-value edit of this lane, under the recorded ruling: the SHORT fixture
`docs/accounting/answer-keys/pos/POS-CHK-010.yaml`, checkpoint `end-of-p1`, contract `C-POS`
`transaction_price` 12,000.00 → **15,000.00** (= fixed 10,000.00 + 2,000.00 + realised P1-TM
3,000.00; S04-R-02 / 04 DB-17 V1, ASC 606-10-32-5 ff. and 32-40). The original 12,000.00 stays
visible in the key's block beside the ruled figure with the rationale and the flag "G12 accountant
review pending" (input/oracle preservation, not accounting-policy approval of 15,000.00). Every
other expectation unchanged and green (revenue 14,000; billed 9,000; contract asset 2,000; unbilled
receivable 3,000; P2 10,000; P3 2,000). The whole-engine test
`tests/engine/kernel/test_d98_29_right_to_invoice_price.py` asserts the realised 3,000.00 is priced
once (TP 15,000.00) and stays with P1-TM (allocations 3,000 / 10,000 / 2,000) — a regression guard
on the ruled behaviour, which the engine already produced (it passed on first run; the key run
`keys-pos-chk-010-d98-29.log` 1 / 1). The longer variant POS-CHK-010-UNBILLED-… has no RTI line and
is untouched (green throughout).

### 5.4 Codex review of 9be54ed — ENC6-R1 and ENC6-R2 (this commit for R2; R1 landed in 8f33bf0)

- **ENC6-R1 (future delivery counted twice)** — REC-CHK-014 at 9be54ed: the inception build-up dated
  1 Dec already carried the realised 3,000.00 of the 31 Dec delivery (the kernel's delivery / invoice
  branches admitted events by position only, without `effective_date ≤ at`), so stage 05 allocated
  3,000.00 to the FIXED segment and stage 09 realised another 3,000.00 on `PERIOD_VC` (600,000 vs
  300,000 minor). Fixed in 8f33bf0: `usage.right_to_invoice` counts deliveries, returns, invoices
  and credit memos from their effective date and usage by its period end, beside the caller's
  position predicate. Fail-first evidence: `enc6-r1-failfirst-9be54ed.log` (snapshot of 9be54ed,
  REC-CHK-014 both checkpoints refused; REC-FS-08, EX12A, REC-RB-05 passed); REC-CHK-014 passes from
  8f33bf0 (`keys-slice2b.log`). The 3,000.00 oracle and the identity guard are unchanged.
- **ENC6-R2 (override away from RTI bypassed the over-delivery guard)** — this commit: the stage 01
  exemption now reads every book's level-O POL-091 `recognition.measure_of_progress` pins
  (`usage.right_to_invoice_lines(measure_overrides=…)`, fed from `bundle.books`): an override that
  moves the obligation to another method withholds the exemption (the effective method decides); an
  override TO `RIGHT_TO_INVOICE` never grants it (the template version decides; fail closed). Tests
  (`test_s01_right_to_invoice.py`, 9): true-RTI success; direct UNITS refusal; UNITS overridden to RTI
  refusal; RTI overridden to UNITS refusal (the R2 shape: level O, scope OBLIGATION, subject
  `Contract 1/POB %231`, pin K, value `UNITS_DELIVERED`); RTI overridden to RTI keeps the exemption;
  future-effective RTI template, expired RTI template, `LEGACY_PARITY`, active `POB_ASSIGNMENT`
  refusals. Fail-first on a snapshot of d53d076 with the new tests: 1 failed (the R2 shape) / 8
  passed (`enc6-r2-failfirst-d53d076.log`); all 49 stage-01 tests pass on this tree.

### 5.5 Slice 2 — POL-092 guard, D-98 candidate 37 (this commit; docs first in a5072bc)

Landed: kernel `usage.expedient_blockers` (pure; reasons `ELEMENT:<type>:<estimate key>` for a
`VARIABLE_CONSIDERATION` element of type `VOLUME_TIER`, `REBATE`, `PRICE_PROTECTION` or `USAGE`
targeting the obligation — contract matched on the CV-21-encoded estimate-key prefix as
`royalties` does — and `NONLINEAR_PRICE:<total>≠<quantity>×<unit price>` when the line's
`total_price` differs from `quantity × unit_price`, both present and total ≠ 0); stage 09
`expedient_guard` before the targets: `RTI_EXPEDIENT_NOT_APPLICABLE` ERROR under POL-092
`BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT`, WARNING under `ALLOW` with `policy = ALLOW` in the detail
(the bypass recorded in the output and the explain trace — the finding is the record; no trace node
was added). Copy: 02-PRD IMP-114 (rev 1.10; DG-ARC-13 pin 113 → 114 in
`test_copy_catalogue_drift.py`). 04 rev 1.33 table 15.4-C row and ENGINE_SPEC_B rev 1.21 (S09-R-18
paragraph, §9.4 row) in a5072bc.

Tests (`test_s09_usage.py`, 13 / 13): linear rate line passes (POS-CHK-014 shape); total 0 rate line
passes (D-87 shape); upfront fee / non-constant rate blocks (3,500 ≠ 120 × 25); each of the four
element types blocks; an element targeting another obligation does not; `ALLOW` bypasses with the
WARNING and recognition unchanged (3,000.00). Fail-first on a snapshot of a5072bc with the new
tests: 3 failed (the blocking shapes) / 3 passed (`d98-37-failfirst-a5072bc.log`). Corpus: the
eleven keys unchanged at 9 / 2 (`keys-guard.log`); no RTI key carries a guarded element or a
non-linear total. Q-2 (§6) is closed by this section.

### 5.6 Codex ENC6-R3 — a zero FIXED component never marks the obligation satisfied (this commit; docs first in 85a1356)

Codex (retest at 4b87200, R1/R2 closed 49/49) found REC-FS-08's obligation `SATISFIED` on 1 Jan at
the January and February checkpoints and its April satisfied date rewound to 1 Jan: the P = 0
`FIXED` component's f = 1 convention (`progress.right_to_invoice_fraction` on an empty denominator)
was read by `components.segment_target` as complete and by `schedule` (S09-R-46) as the obligation's
completion. Ruling implemented: with P = 0 (a D-87 rate line, X = 0) the component's progress — the
S09-R-46 completion signal — is time elapsed over the service term under the resolved POL-090
convention (`components._open_term_or_time`; a line without an end date never completes, formula
params `reason = OPEN_TERM` → 0); stage 06 measures such a segment by time at a boundary too;
`right_to_invoice_fraction`'s f = 1 convention is read only with P > 0. ENGINE_SPEC_B rev 1.22:
§9.2.4 row, S09-R-18 clause, S09-R-46 zero-component sentence (85a1356).

Oracles ADDED (none changed) to REC-FS-08: January and February `satisfaction_status:
PARTIALLY_SATISFIED`, `satisfied_date: null`; April `SATISFIED`, `satisfied_date: 2026-03-31`.
Fail-first on a snapshot of 4b87200 with the edited key (`enc6-r3-failfirst-4b87200.log`): the three
new assertions fail exactly as Codex's field diff (Jan/Feb `SATISFIED`; April date 2026-01-01);
REC-FS-08 passes on this tree (`keys-rec-fs-08-r3.log`). Monetary outputs unchanged (36,000 /
72,000 / 108,000). Suites: s09 + s06 + kernel 444 passed; s01 + s04 + s05 + s13 + architecture 373
passed / 1 xfailed; lint OK, typecheck OK; eleven keys 9 / 2 unchanged (`keys-r3.log`).

### 5.7 Post-C4 re-merge of main 508c4652 (this merge commit; supervisor-assigned numbers)

Main 508c4652 (the ENG-C4 merge; C6 6c1afa18 and C8 30051b7e underneath) merged into
`sprint/l21-enc6` on f21e100. Six files conflicted and were resolved by hand: stage 09
`__init__.py` (C4's `decompose` import kept beside this lane's `EngineError` import; both
`FORMULA_IDS` entries, `expedient_guard` and C4's `decompose.measures_eac` wiring coexist),
`test_copy_catalogue_drift.py` (pin), and the four governed documents' headers / rows. Assigned
renumbering (the supervisor's map; other lanes' rows untouched): 02-PRD 1.6 → **1.10** (main 1.7 /
1.8 = C6; 1.9 = C5, not yet on main); 04 1.20 → **1.33** (main through 1.28 = C4; 1.29 P5;
1.30–1.32 F-CLO); ENGINE_SPEC 1.12 → **1.21** (main 1.16 C8; 1.17–1.19 C5; 1.20 C4);
ENGINE_SPEC_B 1.14 / 1.15 / 1.16 → **1.20 / 1.21 / 1.22** (main 1.15 C8; 1.16–1.18 C5; 1.19 C4).
Header entries strictly descending with the first = the max row. Copy catalogue: this lane's code
takes **IMP-114** (main ends at IMP-111 = C6; IMP-112 / 113 are C5's follow-up, not yet on main —
assumed per the dispatch), and the DG-ARC-13 pin becomes `len(active) == 114` with rows 1..114.
Consequence recorded plainly: until C5's IMP-112 / 113 land on main, `test_copy_catalogue_drift`
fails on this branch (rows 1..111 + IMP-114 leave a gap; active codes 112 ≠ 114) — the numbers are
the supervisor's and are not improvised here; the test goes green when C5 merges ahead of ENC-6 as
sequenced. Every cross-reference in this lane's docs, code comments, tests and this record was swept
to the new numbers (run-log lines keep the numbers as committed, annotated). The two ruled answer-key
edits (POS-CHK-010 candidate 29; REC-FS-08 R3 oracles) are byte-identical to f21e100 after the merge.
f21e100 gate line (measured before this merge, `.run/l21-enc6/measure-summary.txt` END 19:41:19):
selection 220 / 220; all active 251: 227 / 22 / 2 withdrawn, zero new failures, 36 turned green;
engine + architecture + unit 1,883 passed / 1 xfailed / 10 DB-fixture not-run / 1 failed
(`test_makefile_tf_validate_target`, arrived with cdcf372, fixed by main deb69ed — now merged);
`make properties` 12 / 0 / 0 (`properties-f21e100.log`); parity not run (the scenario runner and
probes open `tenant_session`; lane databases not provisioned). Merged-head counts in §7.

### 5.8 Second re-merge: main 69ee7324 (C5 b5cebc48 + P5) into the lane (this merge commit)

Five conflicts, resolved by hand with the assigned numbers kept (02 1.10; 04 1.33; ENGINE_SPEC 1.21;
ENGINE_SPEC_B 1.20–1.22; IMP-114): `test_copy_catalogue_drift.py` — pin **114** kept, rows 1..114,
the comment merged with C5's wording for IMP-112 / 113; `02-PRD.md` — header 1.10 ahead of C5's 1.9,
log row 1.10 after 1.9, IMP-114 after C5's IMP-112 / 113 (contiguous); `04-DATA_MODEL.md` — header
1.33 ahead of P5's 1.29, the `RTI_EXPEDIENT_NOT_APPLICABLE` row kept beside C5's updated onboarding
rows in table 15.4-C; `ENGINE_SPEC.md` — header 1.21 ahead of main's 1.20, log row after C5's
1.17–1.19; `ENGINE_SPEC_B.md` — header 1.22 / 1.21 / 1.20 ahead of main's 1.19, log rows after C5's
1.16–1.18. P5 did not conflict.

DG-ARC-13 classification: the one failed test on 4237df0e (`test_dg_arc_13_imp_rows_cover_codes`,
112 ≠ 114) was the pre-C5 catalogue state — IMP-114 was present, but C5's IMP-112 / 113 and their
04 codes were not yet on main — not a missing row and not engine code. After this merge the test
alone: rc=0, 1 passed (`drift-m69.log`).

Captured exit statuses on the merged tree (`statuses-m69.log`, 00:33:47–00:45:19, each `cmd; rc=$?`):
typecheck rc=0 (OK); lint rc=0 (OK); governed-docs revisions + repository layout + architecture
rc=0, 84 passed; focused ENC-6 suites (test_s09_usage, test_s01_right_to_invoice, test_d98_29 +
s04 / s06 / s09) rc=0, 431 passed; engine + architecture + unit rc=1 — 2,374 passed, 1 xfailed,
0 failed, 10 errors = the DB-bound unit fixtures on the unprovisioned lane database (**not run**);
release selection rc=0, 220 / 220. No keys-all rerun (no key touched in this slice); the previous
head's all-active read 254 selected: 234 / 18 / 2 withdrawn, zero new failures, 40 turned green
(`keys-all-4237df0e.log`).

### 5.9 Landed on main — b073e636

`sprint/l21-enc6` @ 1b7f8ada merged to main as **b073e636** by the supervisor (merge-revrows on 04
and ENGINE_SPEC; post-checks on main: typecheck rc=0, CPU suites rc=0, release selection 220 / 220;
aggregate PASS). Codex's retest target for ENC-6 on main is b073e636. This lane's branch is not
fast-forwarded; this record commit is the lane's last change. Lane DB stages were never run here
(databases not provisioned); the integrated batch on merged main measures test-pg / ci / parity /
properties / keys. Open items belong to the G12 accountant package (AD-39 POS-CHK-010 candidate 29;
AD-40 POL-092 candidate 37), not to this lane.

## 6. Questions returned (engineering choices recorded; policy to the supervisor)

- Q-1 (recorded choice, not policy): the RTI FIXED component is measured `TIME_ELAPSED` over the
  line's term when X > 0 (a fixed fee beside the T&M rate would in any case trip the POL-092 guard);
  in the six keys X = 0.
- Q-2 (to confirm at slice 2): whether the POL-092 guard exists anywhere on 8d76fea; if absent it is
  built as a stage 03 finding under the default `BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT`.
- Q-3 (policy, returned): none yet. AD-21 stays with VC-FS-02 as its only dependent key.
- R-1 — **D-98 candidate 28, CONFIRMED by the supervisor (2026-09-19 evening)**: for a
  `RIGHT_TO_INVOICE` obligation the stated price P is the expected total and the right to invoice R
  is the output measure of progress on the FIXED component (f = min(1, R/P), 606-10-55-18); R above P
  is `PERIOD_VC` in the transaction price (S04-R-06), mirroring the S09-R-33 guarantee pattern;
  P = 0 puts all of R on `PERIOD_VC`. Consistent with REC-FS-08, POS-CHK-014 (3,000) and DISC-S10
  (revenue_cum 3,000; rpo 9,000 = 12,000 − 3,000; RPO stated at P − R with the 606-10-50-14A
  expedient wording where the disclosure applies). Docs first: ENGINE_SPEC_B S09-R-18 progress
  sentence and §9.2.4 row, ENGINE_SPEC S04-R-06 sentence; additive formula id
  `rec.progress.right_to_invoice.v1` (DG-ENG-04). Slice 2 of this lane. Q-1 above is superseded for
  RTI by this ruling (a `USAGE` FIXED component stays time-measured, S09-R-19).
- R-2 — **D-98 candidate 29 (supervisor)**: POS-CHK-010 `end-of-p1` `transaction_price` 12,000.00 is
  the inconsistent oracle; the expected value becomes 15,000.00 BY RECORDED RULING (S04-R-02 / 04
  DB-17 V1: the transaction price includes realised usage; ASC 606-10-32-5 ff., 606-10-32-40), the
  only expected-value edit, on the SHORT fixture `pos/POS-CHK-010.yaml` only, keeping the original
  12,000.00 visible in the key's block beside the ruled figure with the rationale and the flag "G12
  accountant review pending"; every other expectation unchanged (revenue 14,000, billed 9,000,
  contract asset 2,000, unbilled receivable 3,000, P2 10,000, P3 2,000); a test asserts the realised
  RTI 3,000 is not allocated a second time to P2/P3. Slice 2 of this lane.
- R-3 — S08-R-16 wiring (VC-FS-02, JE-CHK-026): assigned by the supervisor to the C4 lane (EDS-4
  owner; sprint/l4 b8f56ae already wires `decompose_prior_period` through stage 15). Not this lane's.
- Q-4 (recorded choice, slice 2): the FIXED progress of an RTI segment on a `PROSPECTIVE` basis is
  g = min(1, (R(d) − R_b) ÷ max(P − R_b, 0)) with R_b the right to invoice before the boundary event
  (CV-63 shape; no corpus key modifies an RTI line — POS-CHK-010/014, REC-CHK-014, REC-FS-08 and
  DISC-S10 are all inception-basis).

## 7. Run log

- 2026-09-19 17:1x PDT: worktree, environment, `.env`, `make lint` OK; report snapshot taken from
  l5's 053813f all-active run; plan record written (fa832eb).
- 17:20–17:49: slice 1 built and measured (fail-first 4 on 8d76fea; identity fix in stage 13 at 17:39;
  stage 06 boundary progress 17:42; `TpBuildUp.realised` / S06-INV-01 17:49); eleven keys 7 / 4
  (`keys-slice1c.log`). Message to lane-eng-b3 (T1F) before touching components.py; overlap map
  received 18:0x (§4).
- 17:50:08–17:52:07: **another writer edited this worktree** — lane-eng-c2-enc6, a fresh ENC-6 agent
  the supervisor had dispatched at 17:12 to the same worktree and then paused read-only; it wrote an
  `erev_engine/usage.py` kernel and rewrote `s09_recognition/usage.py`, `components.py`,
  `buildup.py`, `specialist.py`, `s05 original.py` and `s01 __init__.py` (with the reading "an RTI
  line's stated price is not fixed consideration", which DISC-S10 contradicts and D-98 candidate 28
  overrules). Detected by mtime at 17:51; both agents stopped; supervisor ruling FINAL: this lane
  owns ENC-6 and l21, the other writer stood down. Its tree state is preserved as evidence at
  `.run/l21-enc6/other-writer-1750.patch` (mixed tree; never applied) and `snap-1750/`.
- 17:55–18:03: this lane's versions restored by replaying its own transcript edits onto `git show
  HEAD:` bases (`.run/l21-enc6/replay/replay.py`; the untracked intruder kernel removed); re-measured
  identical to the pre-intrusion state (lint OK, typecheck OK, 345 stage tests, eleven keys 7 / 4,
  `keys-slice1d.log`).
- 18:05–18:18: DG-ENG-07 layering adopted before the slice-1 commit (supervisor's order): the source
  rule, constants and the S01-R-17 predicate moved to the stage-neutral kernel `erev_engine/usage.py`
  (structure per the hand-over; logic per the rulings); `stages/s09_recognition/usage.py` removed;
  stages 01/04/05/06/09 import the kernel only. lint OK, typecheck OK, s01 + s04 + s09 315 passed,
  eleven keys 7 / 4 (`keys-slice1e.log`), engine + architecture + unit 1,786 / 1 xfailed / 10
  DB-bound errors (`suites-4.log`, §5.1). Slice-1 commit follows this record.
- 18:19–18:26: slice 1 committed 9be54ed; ruling-28 docs (ENGINE_SPEC_B 1.14, ENGINE_SPEC 1.12 as
  committed; renumbered 1.20 / 1.21 at the post-C4 merge, §5.7)
  committed 5c79178 after `tests/architecture` 72 passed.
- 18:27–18:50: ruling-28 code (§5.2); fail-first 3 failed on 5c79178; the first cut lost the
  effective-date gate on deliveries (REC-CHK-014 identity 6,000 vs 3,000) — restored in the kernel;
  lint OK, typecheck OK, 558 stage tests, eleven keys 8 / 3 (`keys-slice2b.log`). Committed after
  this record.
- 18:50–18:58: ruling-28 code committed 8f33bf0; ruling 29 applied to the short POS-CHK-010 fixture
  (§5.3) with the whole-engine no-double-allocation test; POS-CHK-010 1 / 1; committed after this
  record. `.run/l21-enc6/measure.sh` (selection, all active vs base, suites) runs on that head.
- 19:0x–19:2x: Codex review of 9be54ed received (3 / 4, ENC6-R1, ENC6-R2): §3.1 and §5.1 corrected
  (REC-CHK-014 failed at 9be54ed), R1 evidence reproduced on a snapshot, R2 implemented with the
  refusal controls (§5.4); committed; then main cdcf372 merged into l21 as ordered.
- 19:2x–19:5x: R2 committed ff06331 (the Codex retest head for R2 and the record correction); main
  cdcf372 merged as 4b87200 (no conflicts; post-merge lint OK, typecheck OK, 324 stage tests, eleven
  keys 9 / 2 — REC-CHK-014, POS-CHK-010 and POS-CHK-014 green). POL-092 guard: docs first a5072bc
  (04 1.33, ENGINE_SPEC_B 1.21), code + tests + IMP-114 committed after this record; fail-first
  `d98-37-failfirst-a5072bc.log`. `.run/l21-enc6/measure.sh` runs on that final head.
- 19:5x–20:1x: Codex closed R1/R2 at 4b87200 (49 / 49; 12 / 12 focused) and raised ENC6-R3;
  measure.sh on e3823ea: selection 220 / 220, all active 227 / 22 / 2 withdrawn, zero new failures,
  36 turned green vs the l9bgate base. R3 docs 85a1356, code + REC-FS-08 oracles committed after this
  record; measure.sh re-runs on that head.
- 2026-09-20 00:0x–00:20: main 508c4652 merged (4237df0e; §5.7); measure.sh on 4237df0e: selection
  220 / 220; all active 254: 234 / 18 / 2, zero new failures, 40 turned green; suites 2,331 passed /
  1 xfailed / 10 DB-bound / 1 failed (the DG-ARC-13 pin, pre-C5).
- 00:2x–00:45: main 69ee7324 merged (§5.8); captured statuses all rc=0 except the DB-bound suite
  fixtures; committed as this merge commit.
- 2026-09-20 0x:xx: landed on main as b073e636 (§5.9); lane closed.
