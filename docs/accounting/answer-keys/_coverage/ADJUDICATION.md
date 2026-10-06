# Answer-key adjudication (design phase B3)

| Field | Value |
|---|---|
| Owner | Answer-key adjudicator, slug `ak-adjudicator` (design phase B3) |
| Date | 2026-09-12 |
| Status | Binding for the answer-key corpus. Under D-77 the corpus is frozen after B3; gaps found in the build are Spec questions in `PROGRESS.md`. Revenue-accountant review (G12) is still pending: every key keeps `review.status: pending` |
| Precedence | This file rules on every discrepancy and open question of the three coverage files in this directory. Where a coverage file differs, this file governs |
| Binding inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` §7 and §8 (D-11a, D-25b, D-76, D-77); `docs/dev-guide.md` rev 1.2 §9.5; `docs/accounting/POLICIES.md` rev 1.2; `docs/accounting/ENGINE_SPEC.md` and `ENGINE_SPEC_B.md` rev 1.2; `docs/04-DATA_MODEL.md` rev 1.2 (§3.4, T-CON-11, T-CON-13, §15.4, §16.1, §16.3); `docs/03-REQUIREMENTS.md` §12; `docs/design/SCREENS_B.md` RPT-36; `docs/reviews/B3-fix-dev-guide.md`; `docs/reviews/B3-fix-fix-policies.md` |
| Files edited | `docs/accounting/answer-keys/**` (including `_coverage/`) and `research-harness/answer-keys/**` only |
| Scratch | `.scratch/b3-ak-adjudicator/`: `backup/` (both trees before this pass), `survey.py`, `dupes.py`, `dupes_detail.py`, `loader-baseline.json`, `loader-final.json`, `verify-report-topics.json` |

## Revision log

| Rev | Date | Change |
|---|---|---|
| 1.0 | 2026-09-12 | First issue. Rulings R-SFC-01 to R-SFC-03, R-COST-01 and R-COST-02, R-CHK-01, R-DUP-01 and R-DUP-02, R-POL-01, R-SCH-01 to R-SCH-15, R-GAP-01 to R-GAP-03; 16 keys added, 4 renamed, 2 withdrawn; shared build step `research-harness/answer-keys/adjudication.py`; loader check `research-harness/answer-keys/loader_check.py` |
| 1.3 | 2026-09-12 | Post-B3 residue sweep (slug `numeric-residue`; supervisor-directed; D-77 opens no question). Section 10 "R-series post-B3": rulings R-SFC-04, R-SFC-05, R-COST-03, R-SGN-01, R-V1-01, R-RET-01, R-SCH-16, R-SCH-17, R-CHK-02, R-ALG-01. 1 key added (`SFC-S3-EX26-RETURN-RIGHT`); 33 keys regenerated with changed inputs or leaves; section 9 items 1 to 4 and 6 closed in the owner texts. Change record: `docs/reviews/B4-numeric-residue.md` |
| 1.4 | 2026-09-17 | Supervisor erratum (D-90; L8-E-Q-2). The `RND-CHK-003C` `after-credit` FY2026-P02 block (`grain: role_account_obligation`, `match: exact`) lists the JET-05c REFUND_LIABILITY 2110 credit per obligation, POB-001 Cr 33.34, POB-002 Cr 33.33 and POB-003 Cr 33.33 (total 100.00), in place of one Cr 100.00 line without `obligation_key` (ENGINE_SPEC_B Table 14-A JET-05c subject obligation, S14-R-13; D-87 L6-5-Q-10; D-88 L7-5-Q-4). Cause: the topics oracle `specs_mr_mod.sat_credit_oracle` posted the credit side without `cr_obl`; it now posts `cr_obl=o.key`, and the key summary names the per-obligation credits unsigned (mirrored in the oracle). 1 key regenerated through `akt_run.py generate` with changed leaves and no input change; every other topics key regenerates byte-identical. Revenue debits, contract and obligation figures, `match` and grain unchanged. For this key, D-77, D-83, D-84 and D-87, the D-89a membership and the Status line above read as amended by D-90. `review.status` stays `pending` (G12) |
| 1.5 | 2026-09-30 | Supervisor errata (ruling R-46 of 2026-09-30, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`; memo `docs/accounting/reviews/AD-13-14-34-MEMO-2026-09-29.md` and its independent review; number assigned by the supervisor). New section 11, one entry per key with every changed leaf before and after. `POB-S2-EX61` (R-46 (a); G12 AD-34): three leaves at `end-of-q1`, a realised royalty inside `transaction_price`, `allocated_amount` and `remaining_allocation`. `SFC-S3-EX26-RETURN-RIGHT` (R-46 (b); G12 AD-13; form A): seven leaves and the FY2026-P03 lines at `return-right-open`, the FY2026-P04 lines at `right-lapsed` and one clause of the summary, because the right lapses on its window-end day (D-87 L6-5-Q-25). Cause in both: the topics oracle (the royalty rule of `akt_engine.py`; the window test of `specs_b4.sfc_returns_oracle`), now corrected. 2 keys written by `akt_run.py generate-only` with changed leaves and no input change; `akt_run.py generate` is not run over the corpus, because it would also rewrite 13 keys that carry later rulings the generator does not hold (section 11.3); every other key file is unchanged. No engine change. Both keys return to the release selection (220 → 222 ids). For these two keys the Status line above and the `SFC-S3-EX26-RETURN-RIGHT` row of section 10.2 read as amended by R-46 (D-99 (8)). **Supervisor ruling pending the independent accountant**: `review.status` stays `pending` (G12) |

### Decisions taken in B3 (D-77)

None of these opens a question. Each is the most reasonable default and is applied in the keys.

| # | Decision | Where |
|---|---|---|
| B3-AK-01 | For S04-R-12, n counts the calendar month ends in (T, payment date]. A payment at the k-th month end after a transfer on the first day of a month is k months away. This reproduces POLICIES CHK-136 and CHK-137 and every earlier key. A strict floor of whole calendar months would put a 31 January instalment 0 months from a 1 January transfer | R-SFC-02 |
| B3-AK-02 | The JET-09c impairment never exceeds the carrying amount, so the asset floors at 0.00. A recoverable amount below zero is a loss-test matter under Subtopic 605-35, not a negative asset | R-COST-01 |
| B3-AK-03 | SFC-S3-EX26 asserts the financing component of FASB Example 26 without its 90-day return right. S04-R-12 accretes from transfer and has no rule that suspends accretion while expected returns exclude the whole consideration. The FASB accretion rate over 21 months is irrational | R-SFC-03 |
| B3-AK-04 | A `world.policies` value is placed at the broadest level POLICIES §1 allows, in the order T, E, B, then P (every product), then C (every contract). A key whose levels are not expressible ("import batch", "acquisition") is not written | R-POL-01 |
| B3-AK-05 | Test for a true duplicate: equal normalised inputs, ignoring names, rationales, handles and invoice or receipt references, with canonical decimals and explicit POLICIES defaults ignored. In addition, every shared assertion leaf agrees. The kept key is the one that carries the POLICIES CHK id, and it absorbs the unique leaves of the withdrawn key | R-DUP-01 |
| B3-AK-06 | A key that already asserts a CHK figure is renamed to contain the CHK id (and gets `derived_from.chk`). A second key with the same inputs is not added | R-CHK-01 |
| B3-AK-07 | Noncash consideration is carried by the booking member `noncash_consideration`. The line's `total_price` is 0.00, because S04-R-02 adds `noncash` to the fixed consideration | NCC-CHK-135-S3-EX31 |
| B3-AK-08 | A two-sided incentive element (bonus or penalty) keeps its signed outcomes in `scenarios` only. `most_conservative_amount` is omitted, because T-CON-12 amount columns are magnitudes | R-SCH-15 |
| B3-AK-09 | CHK-117 is asserted through the platform runner, report `balance_aging` (RPT-36). The row key is `contract:<external id>:<E-01 role>`. Age is measured from the effective date of the latest revenue event of the obligation the debit position is attributed to | POS-CHK-117 |
| B3-AK-10 | CHK-121: the acquisition on 1 January 2026 establishes the opening state with a cutover date of 31 December 2025. IFRS15 `revenue_cum` counts from the cutover (no baseline revenue, S07-R-08). Nothing posts in FY2025-P12 | ONB-CHK-121 |
| B3-AK-11 | The CHK-120 not-probable case posts a reduction in June 2026 and reverses it in December 2026 when version 2 makes vesting not probable | CPC-CHK-120-…-NOT-PROBABLE |
| B3-AK-12 | CHK-084 (a): the ERP credit memo debits the contract liability at spot. The engine's JET-04b credit at spot offsets it, no contract-liability layer is open, and no JET-10c difference arises. At window expiry JET-04b creates a layer at spot, and JET-04a relieves it | FX-CHK-084-A |
| B3-AK-13 | `is_franchisor_preopening_service: true` is set on the pre-opening SKU of every key that elects POL-202 | R-SCH-12 |

## 1. Result

- **Keys.** 233 files: 231 active and 2 withdrawn. By author: answer-keys-topics 109 (107 active, 2 withdrawn); answer-keys-industries 57; answer-keys-fx-entity-books 67.
  - Relative to the corpus before this pass: 16 keys added, 4 removed by renaming, 5 keys with changed checkpoints, and 131 keys with only inputs or text changed. The remaining 81 are unchanged.
- **Oracles.** Every key regenerates with its slice's build script, and all three verifiers report 0 failures:
  - topics: 109 keys, 0 errors;
  - industries: 57 keys, 0 failing;
  - fx-entity-books: 67 keys, 0 failing.
- **Golden cross-check.** 508 comparisons, 0 mismatches at 1e-4 (D-17).
- **fx document comparisons.** They agree with POLICIES rev 1.2 for the CHK-006 rows and the CHK-136 MONTHLY row. The 6 remaining differences are expected:
  - research 04 last-period plugs (D-11);
  - the research 04 ANNUAL figures, now asserted by SFC-CHK-136-S3-EX29-ANNUAL.
- **Loader check.** 233 keys, 0 errors, 0 corpus gaps, 0 notes. Coverage holds:
  - List A: 49 of 49;
  - List B: 46 of 46;
  - List C: 76 of 76 CHK ids;
  - `AK:` hints: 50 of 50;
  - `AK-FAM:` hints: 9 of 9;
  - family codes: 28 of 28.
- **Baseline before this pass.** 90 errors in 45 keys and 12 corpus gaps (section 7).

## 2. How to rerun

```sh
cd ~/dev/erev/research-harness/answer-keys/answer-keys-topics
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python akt_run.py generate   # writes the 109 topics keys, then verifies
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python check_golden.py       # parity oracle against docs/legacy/golden
cd ../answer-keys-industries
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python run_oracle.py build   # writes the 57 industries keys
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python run_oracle.py verify
cd ../answer-keys-fx-entity-books
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python build.py              # writes the 67 fx-entity-books keys
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python verify.py --quiet
cd ~/dev/erev
UV_OFFLINE=1 uv run --offline --no-project --with pyyaml python research-harness/answer-keys/loader_check.py [--json PATH]
```

| File | Role |
|---|---|
| `research-harness/answer-keys/adjudication.py` | `finalise(key)`, called by all three build scripts after a spec builds its inputs and before the oracle runs. It places policy values at allowed levels (R-POL-01), marks the withdrawn keys (R-DUP-01) and appends the variant cross-references to summaries (R-DUP-02). `WITHDRAWN`, `XREF` and `RENAMED` are the machine record of those rulings |
| `research-harness/answer-keys/loader_check.py` | Validates every key against dev-guide §9.5 rev 1.2 and the loader rules (section 7) |
| `answer-keys-topics/specs_b3.py`, `answer-keys-fx-entity-books/keys_b3.py` | Keys authored in this pass, with their oracles |

## 3. Required rulings

### R-SFC-01 SFC-S3-EX28-CASEB and CHK-137 (fx-entity-books section 7; D-T-08; D-AK-04)

- **Ruling.** The unbilled receivable after the first instalment is 837,959.00, under both conditions D-76 sets: MONTHLY compounding, and financing interest included in the position.
  - Revenue at transfer is round(CSP) = 848,346.53. The CSP discounts the 60 scheduled instalments of 18,871.00 at annual_rate ÷ 12 = 1%, instalment k at k months (R-SFC-02).
  - JET-11a posts the period change in round(exact cumulative interest) on the exact financed balance (S04-R-12; ALG-01 §2.1.3): month 1 8,483.47; month 2 8,379.59.
  - Net position after month 1 = 18,871.00 − 848,346.53 − 8,483.47 = −837,959.00. It is presented as an unbilled receivable because the right is unconditional and the accretion is in R_p (ALG-02 step 3 rev 1.2). This equals POLICIES CHK-137.
  - Month 2 unbilled receivable is 827,467.59. Total interest is 283,913.47, so the 60th instalment settles the balance to 0.00.
- **Superseded figures.** 846,527.30 and 836,121.57 came from an earlier generation and cannot be reproduced from the current inputs. The prior topics oracle rounded each month's interest on the rounded opening balance. That method gives the same months 1 and 2 but leaves 0.06 unsettled after 60 instalments, so the oracle now follows S04-R-12.
- **Keys changed.**
  - SFC-S3-EX28-CASEB is renamed SFC-CHK-137-S3-EX28-CASEB (R-CHK-01), with:
    - `derived_from.chk: [CHK-137]`;
    - `compounding: MONTHLY`;
    - `payment_schedule` of 60 points;
    - the leaf `financing_adjustment_amount` −283,913.47;
    - a new checkpoint `end-of-month-60`;
    - world periods extended to 2030-12.
  - The topics financing oracle is rewritten to S04-R-10 to S04-R-13, supporting MONTHLY and ANNUAL compounding, `payment_schedule` and the POL-025 renewal gate.

### R-SFC-02 Month count for the financing schedule (B3-AK-01)

- **Ruling.** n_i = the number of calendar month ends in (T, d_i]. With T = 1 January 2026 and a 31 January 2026 instalment, n = 1. With a 1 January 2026 advance and a 31 December 2027 transfer, n = 24. These values reproduce CHK-136 (4,508.64) and CHK-137 (848,346.53).
- **Spec question for the build.** ENGINE_SPEC S04-R-12 cites `dates.months_between` with a floor. D-§0 makes answer keys govern numbers.
- **Keys.** SFC-CHK-137-S3-EX28-CASEB, SFC-S3-EX29, SFC-CHK-136-S3-EX29-ANNUAL, SFC-S3-EX26, POB-S2-EX59.

### R-SFC-03 FASB Example 26 financing component (B3-AK-03)

- **Ruling.** SFC-S3-EX26 is authored without the return right:
  - delivery on 1 January 2026 for 121.00 payable on 31 December 2027;
  - CUSTOMER_CREDIT_RATE 0.10 with compounding ANNUAL, so CSP = 121.00 ÷ 1.1² = 100.00 exactly;
  - interest 10.00 in 2026 and 11.00 in 2027, spread monthly by cumulative rounding (0.83 in January 2026);
  - unbilled receivable 100.83, 110.00, then 0.00 after the invoice.
- **What remains open.** The return-right interaction is a Spec question for the build (section 9, item 2).
- **Keys.** SFC-S3-EX26 (new), closing hint `AK:S3-EX26`.

### R-COST-01 COST-S8-CONTRACT-COSTS-IMPAIRMENT negative carrying amount (fx-entity-books section 7; D-T-11)

- **Ruling.** A contract-cost asset cannot go below zero. JET-09c = min(carrying, max(0, carrying − recoverable)).
  - Recoverable = remaining expected consideration + consideration from the anticipated renewals and extensions used in the amortisation period (RENEWAL_EXPECTATION `expected_total_amount`; D-76; JET-09c rev 1.2; S11-R-09) − remaining direct costs.
  - The −85,000.00 came from an earlier generation. The key already asserted 15,000.00 at the end of 2026.
- **Figures now asserted.**
  - End of 2026: impairment 15,000.00 (carrying 30,000.00; recoverable 300,000.00 − 285,000.00 = 15,000.00). The renewal term is nil because the RENEWAL_EXPECTATION version carries no expected consideration.
  - End of 2027: carrying 10,000.00.
  - New checkpoint `end-2028-floor`, where version 2 of the EAC raises total costs to 500,000.00:
    - remaining consideration 100,000.00, remaining costs 215,000.00, recoverable −115,000.00;
    - the uncapped formula would impair 120,000.00 and leave a carrying amount of −115,000.00;
    - the key impairs 5,000.00 and the carrying amount is 0.00.
- **Keys and oracles changed.**
  - COST-S8-CONTRACT-COSTS-IMPAIRMENT: periods to 2028-12, EAC version 2, 2028 costs, the floor checkpoint, and summary.
  - Floor and renewal term implemented in all three impairment oracles: topics `cost_oracle`, fx `CostBook`, industries `costimp_compute`.
- **Spec gap.** The floor is missing from the owner texts (section 9, item 3).

### R-COST-02 Anticipated renewals in the impairment test (industries D-6)

- **Ruling.** D-76 and JET-09c rev 1.2 govern.
  - COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT tests after version 2 anticipates no renewal, so the renewal term is nil and the 20,000.00 impairment is unchanged.
  - JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL has no anticipated renewals, and its figures are unchanged.
- **Keys.** Summary of COST-CAP (text only).

### R-CHK-01 CHK-006, CHK-053 and CHK-136 re-baselines (OQ-AKT-01, OQ-AK-02, OQ-AK-05; D-T-01, D-T-02, D-T-05, D-AK-02, D-AK-05)

- **Ruling.** POLICIES rev 1.2 carries the D-11a and MONTHLY values, and the keys equal them:
  - **CHK-006 S2-WARRANTY-OWN:** 79.55 in months 13, 15, 17, 19, 21, 23 and 24; 79.54 otherwise.
  - **CHK-006 S5-EX63-OWNSSP:** 9,708.74 / 9,708.74 / 9,708.73.
  - **CHK-006 S12-FRANCHISOR-OWN:** 3,636.37 in years 2, 5, 7 and 10; 3,636.36 otherwise.
  - **CHK-053:** P2 3,492.91; contract liability 1,073.30.
  - **CHK-136 MONTHLY:** year 1 246.71, year 2 261.93, transfer 4,508.64.
  - **CHK-136 ANNUAL:** 240.00, 254.40, 4,494.40.
- **Keys changed.**
  - New SFC-CHK-136-S3-EX29-ANNUAL, the ANNUAL row that the POLICIES fixer requested.
  - `compounding: MONTHLY` made explicit in JE-CHK-136, SFC-S3-EX29, SFC-FS-11-CASEB and SFC-CAP.
  - fx `docexp.py` transcriptions updated to rev 1.2, so the document comparisons agree.
  - The RND-CHK-006-*, POB-* and MR-CHK-053 figures are unchanged.

### R-DUP-01 True duplicates withdrawn (D-76 ruling on OQ-AKT-18; B3-AK-05)

- **Method.** `.scratch/b3-ak-adjudicator/dupes.py` compared every cross-slice pair sharing a research 04 id, a research 05 id or a CHK id, plus the IFRS shipping pair: 74 pairs.
- **Result.** Two cross-slice pairs have equal normalised inputs and fully agreeing shared leaves.

| Withdrawn | Kept | Inputs | Leaves added to the kept key |
|---|---|---|---|
| POS-S9-PRESENTATION-EX38-CASEA | JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE | Equal apart from the invoice and receipt references; 6 shared leaves agree | `january-close` `billed_cum` 0.00; new checkpoint `receipt-1-march`: `billed_cum` 1,000.00, `revenue_cum` 0.00, contract liability 1,000.00 |
| POS-S9-PRESENTATION-EX38-CASEB | JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE | Equal apart from the invoice and receipt references; 8 shared leaves agree | `january-close` `billed_cum` 1,000.00 |

- **Status of the withdrawn keys.** They stay in the corpus with `status: withdrawn` (DG-AK-13: validated and reported, never run). List B COV-B-42 stays covered by six active S9-PRESENTATION keys.
- **Same-input groups kept.** Two same-author groups have equal inputs but disjoint assertions, and both are kept:
  - DISC-CHK-006-S10-DISCLOSURES-ROLLFORWARD-EX21, DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING and RND-CHK-004-CHK-006-S2-EX11-CASEA-OWNPRICES (engine balances, platform reports, schedule pattern);
  - DISC-S10-DISCLOSURES-ROLLFORWARD-EX21 and POB-S2-EX11-CASEA-OWNPRICES.

### R-DUP-02 Variants kept and cross-referenced

- Each pair below has distinct inputs. Both keys stay active.
- The build step appends "Cross-slice variants with distinct inputs, kept: …" to both summaries (`adjudication.XREF`).

| Key | Variant | Distinct inputs |
|---|---|---|
| RND-CHK-001 | RND-CHK-001-USD-EQUAL-SSP-THIRDS | Contract, prices, events |
| RND-CHK-003A, -003B, -003C, -003D | RND-CHK-003A-JPY-…, -003B-BHD-…, -003C-USD-NEGATIVE-CREDIT-MEMO-…, -003D-TIE-BROKEN-… | Contracts, prices, events; price concession versus credit memo for 003C |
| ALC-CHK-002-GT01-GT03 | RND-CHK-002-CHK-007-GT01-CONTRACT1 | Golden Contracts 1, 2 and 4 versus Contract 1 with CHK-007 |
| POS-CHK-010 | POS-CHK-010-UNBILLED-RECEIVABLE-AND-CONTRACT-ASSET-SPLIT | Obligations, prices, events |
| POS-CHK-011-GT06 | POS-CHK-011-GT06-CONTRACT2-SSP-DELIVERED-RECLASS | Golden steps and scope |
| POS-CHK-012-S9-PRESENTATION-NETTING | POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT | Contracts and dates; platform runner |
| POS-CHK-013-S9-PRESENTATION-EX39 | POS-CHK-013-EXAMPLE-39-CONDITIONAL-RIGHT-ENGINE-BILLING | Prices 500.00 / 500.00 versus 400.00 / 600.00; dates |
| REC-CHK-014-S5-PROGRESS-VARIANTS-RTI | POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE | Delivery events versus usage reports; terms |
| VC-CHK-100-S3-EX21-EXTENDED | JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP | Cost-to-cost versus output progress |
| VC-CHK-101-S3-EX23-CASEB | DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE | Estimate versions, events |
| VC-S3-EX24 | JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY | VOLUME_TIER versus REBATE; dates, invoices |
| TAX-S3-SALESTAX-OWN | JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING | Inception date, invoice terms |
| STP1-S1-EX2 | JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA | Estimate inputs, events |
| STP1-S1-EX1-CASEB-C-VARC | JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY | Receipts, dates, policies |
| POB-S2-EX11-CASEA-OWNPRICES | RND-CHK-004-CHK-006-S2-EX11-CASEA-OWNPRICES | Events, policies |
| POB-CHK-134-S2-WARRANTY-OWN | RND-CHK-006-S2-WARRANTY-OWN-EXTENDED-WARRANTY | Assurance accrual under POL-022 ENGINE versus schedule pattern only |
| REC-S5-EX63-OWNSSP | RND-CHK-006-S5-EX63-OWNSSP-CUSTODY | Custody 2027 to 2029 versus 2026 to 2028 |
| POB-S12-FRANCHISOR-OWN | RND-CHK-006-S12-FRANCHISOR-OWN-LICENCE-TEN-YEARS | Events, policies |
| REC-S5-UPFRONTFEE-OWN-B | RND-CHK-006-S5-UPFRONTFEE-OWN-OPTION-B-PATTERN | Lines, policies |
| MOD-S6-COMBINED-MOD-OWN | RND-CHK-006-S6-COMBINED-MOD-OWN-SUPPORT-PATTERN | Modification inputs |
| MOD-CHK-028-S6-EX5-CASEB | RND-CHK-006-S6-EX5-CASEB-UNITS-PATTERN | Modification inputs |
| LOSS-S7-LOSS-OWN | JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE | Unbilled versus invoiced yearly |
| COST-S8-CONTRACT-COSTS-EX2 | JE-CHK-130-S8-CONTRACT-COSTS-EX2-AMORTISATION | 600,000.00 over five years versus 700,000.00 over seven |
| COST-S8-CONTRACT-COSTS-IMPAIRMENT | JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL | Monthly test on a four-year contract versus years mapped to periods with the IFRS15 reversal |
| COST-S8-CONTRACT-COSTS-EXPEDIENT | JE-CHK-131-S8-EXPEDIENT-ONE-YEAR-COMMISSION-EXPENSED | Contract, events |
| SFC-S3-EX29 | JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION; SFC-CHK-136-S3-EX29-ANNUAL | Transfer 31 December 2027 versus 1 January 2028; compounding ANNUAL |
| DISC-S10-DISCLOSURES-ROLLFORWARD-EX21 | DISC-CHK-006-S10-DISCLOSURES-ROLLFORWARD-EX21 | Events, policies |
| DISC-S10-DISCLOSURES-RPO-EX42 | DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT | Contracts, figures; platform runner |
| IFRS-S13-SWITCH-SHIPPING | IFRS-SW04-SHIPPING-FULFILMENT-ELECTION-VS-SEPARATE-OBLIGATION | Lines, events |

## 4. Rulings on every coverage-file discrepancy

"Resolved by D-76" means the default recommended in the coverage file was adopted.

| Id | Discrepancy | Ruling | Keys changed |
|---|---|---|---|
| topics D-T-01 | CHK-053 period 2 | R-CHK-01 | None (figures already D-11a) |
| topics D-T-02 | CHK-006 three rows | R-CHK-01 | None; fx `docexp.py` |
| topics D-T-03 | S2-EX61 unbilled royalty | The key is right: the balance nets within the contract (D-12; POL-120; 606-10-45-1) | None |
| topics D-T-04 | S2-EX51 whole-dollar scaling | The key is right: exact cohort allocation (606-10-10-4) | None |
| topics D-T-05 | CHK-136 compounding | R-CHK-01 | SFC-S3-EX29 (compounding); new SFC-CHK-136-S3-EX29-ANNUAL |
| topics D-T-06 | POL-076 test (c) | Resolved by D-76 (OQ-AKT-02); POLICIES rev 1.2 adopts the comparison | ALC-CHK-034-S4-EX34-CASEA (summary text) |
| topics D-T-07 | ALG-06 step 2 versus step 6 | Resolved by D-76 (OQ-AKT-03): step 2 governs | None |
| topics D-T-08 | EMOD-18 position excludes interest | D-76 financing-interest ruling: accretion is in NP and R_p; R-SFC-01 | SFC-CHK-137-S3-EX28-CASEB |
| topics D-T-09 | Legacy JE cents | Deviation class DEV-002 (D-17a) | None |
| topics D-T-10 | Plugged last periods | Re-baselined under D-11 and C-07 | None |
| topics D-T-11 | S8 impairment example restated | R-COST-01 | COST-S8-CONTRACT-COSTS-IMPAIRMENT |
| topics D-T-12 | S4-EX35 Case A not expressible | Stays not authored. No input allocates fixed consideration only to POBs without targeted VC. COV-B-21 and hint `AK:S4-EX35` are covered by ALC-S4-EX35-CASEB | None |
| industries D-1 | BR-01 allocation | The key is right (REQ-CON-009; POL-076) | None |
| industries D-2 | JS-05 private allocation | The key is right | POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT (R-SCH-12) |
| industries D-3 | JS-01 3,968.26 | The key is right (D-11a) | None |
| industries D-4 | BR-02 adaptation | Accepted | None |
| industries D-5 | SFC rounding, position, presentation | D-76 financing-interest and SFC-rate rulings; ALG-02 step 3 rev 1.2 (OQ-AKI-12). Keys already round the exact cumulative interest | SFC-FS-11-CASEB (compounding); SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE (compounding, `payment_schedule`) |
| industries D-6 | Impairment with renewals | R-COST-02 | COST-CAP (summary) |
| industries D-7 | Uninstalled materials | D-76: zero margin, no COST_OF_REVENUE line; the key already follows | None |
| industries D-8 | Figures reproduced | No discrepancy | None |
| fx D-AK-01 | CHK id case | D-76: case-insensitive containment | None |
| fx D-AK-02 | CHK-006 rows | R-CHK-01 | fx `docexp.py` |
| fx D-AK-03 | Research 04 plugs | Expected re-baselines | None |
| fx D-AK-04 | NP and JET-11 | R-SFC-01 | SFC-CHK-137-S3-EX28-CASEB |
| fx D-AK-05 | CHK-136 | R-CHK-01 | JE-CHK-136 (compounding) |
| fx D-AK-06 | Same-day release order | Resolved by D-76 (OQ-AK-12); POLICIES ALG-08 rev 1.2 | None |
| fx D-AK-07 | CHK-081 class | The key keeps CONDITIONAL with its rationale | None |
| fx D-AK-08 | CHK-133 to CHK-135, CHK-137 blocked | D-76 schema additions adopted; authored (section 6) | CPC-CHK-133-S3-EX32, POB-CHK-134-S2-WARRANTY-OWN, NCC-CHK-135-S3-EX31, SFC-CHK-137-S3-EX28-CASEB |
| fx D-AK-09 | `_coverage/` would fail discovery | Resolved: DG-AK-30 rev 1.2 ignores `_coverage/` | None |
| fx D-AK-10 | POL-143 convention | The key sets MONTHLY_EVEN | None |
| fx D-AK-11 | Annual test on monthly periods | Accepted [A] | None |
| fx D-AK-12 | No `scope_605_35` | Schema adopted; R-SCH-03 | JE-CHK-132, LOSS-S7-LOSS-OWN, LOSS-GE-03 |
| fx D-AK-13 | Mid-period f(d) | Unit tests (DG-ENG-11) | None |
| fx section 7 | Duplicate scenarios | R-DUP-01, R-DUP-02 | Section 3 |
| fx section 7 | COST −85,000.00 | R-COST-01 | COST-S8-CONTRACT-COSTS-IMPAIRMENT |
| fx section 7 | SFC 846,527.30 / 836,121.57 | R-SFC-01 | SFC-CHK-137-S3-EX28-CASEB |
| OQ-AKT-01 to OQ-AKT-20, OQ-AKI-01 to OQ-AKI-21, OQ-AK-01 to OQ-AK-16 | Coverage open questions | Resolved by D-76. The schema rulings are applied in section 5; OQ-AKI-19 (class per billing-plan line) is not adopted by 04 B3-D05 | Section 5 |

## 5. Schema conformance (dev-guide §9.5 rev 1.2)

| Ruling | Member or rule | Keys |
|---|---|---|
| R-POL-01 | DG-AK-32 "the level is allowed" (POLICIES §0.5, §1 Levels). The shared build step `adjudication.conform_policy_levels`, rule B3-AK-04. The keys are listed below the table | 41 keys (37 topics, 4 industries) |
| R-SCH-01 | `sfc.discount_rate_basis` `{basis, annual_rate, compounding}` | SFC-CHK-137-S3-EX28-CASEB, SFC-S3-EX29, SFC-CHK-136-S3-EX29-ANNUAL, SFC-S3-EX26, POB-S2-EX59, SFC-FS-11-CASEB, SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE, JE-CHK-136 |
| R-SCH-02 | Contract `payment_schedule` (billing plan) | SFC-CHK-137-S3-EX28-CASEB, SFC-S3-EX26, POB-S2-EX59, SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE |
| R-SCH-03 | Contract `scope_605_35`; the book-level `loss.scope` workaround removed | LOSS-S7-LOSS-OWN, JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE, LOSS-GE-03-LOSS-CONTRACT-PROVISION |
| R-SCH-04 | `world.portfolios` with a portfolio-scoped estimate; one ESTIMATE_CHANGED per member | RET-CHK-116 |
| R-SCH-05 | Checkpoint block `groups` (DG-AK-57) | STP1-S1-COMBINATION-OWN, ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP |
| R-SCH-06 | Contract `renewal_of` | REC-FS-06-TERM-LICENCE-RENEWAL-START-GATE, POB-S2-EX59 |
| R-SCH-07 | Contract `consideration_payable` (the native members; DG-AK-34 encoding kept in CPC-BR-07-CASEA, CPC-BR-07-CASEB, CPC-WM-03) | CPC-CHK-133-S3-EX32, CPC-CHK-120 ×2, FX-CHK-084-C |
| R-SCH-08 | Contract `noncash_consideration`; PAYMENT_RECEIVED `form: NONCASH`, `units_received`, `asset_type` | NCC-CHK-135-S3-EX31 |
| R-SCH-09 | Product `assurance_cost_per_unit` with POL-022 ENGINE | POB-CHK-134-S2-WARRANTY-OWN |
| R-SCH-10 | SSP entry `observable_point` with POL-072 OBSERVABLE_POINT | SSP-CHK-030-S4-SSPRANGE-OWN-OBSERVABLE-POINT |
| R-SCH-11 | SSP entry `population`; `exceptions[].subject` (DG-AK-45) | SSP-CHK-031-RANGE-VALIDATION-AT-PUBLICATION |
| R-SCH-12 | Product `is_franchisor_preopening_service` | POB-S12-FRANCHISOR-OWN, RND-CHK-006-S12-FRANCHISOR-OWN-LICENCE-TEN-YEARS, POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT |
| R-SCH-13 | Estimate `parameters` of kind SHARE_BASED_CONSIDERATION (T-CON-13) | CPC-CHK-120 ×2 |
| R-SCH-14 | Report cell keys (DG-AK-35, table "Report cell keys"). The existing report keys already conform; `balance_aging` uses the "any other code" row | DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING, DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT (unchanged); POS-CHK-117 |
| R-SCH-15 | T-CON-12 amount columns are magnitudes; B3-AK-08 | VC-CHK-100-S3-EX21-EXTENDED, JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP |

**R-POL-01 moves.**

- **T → P (every product):** `returns.model`, `returns.returned_units_scope`, `material_right.ssp_method`, `breakage.method`, `costs.amortisation_pattern`, `costs.amortisation_period`.
- **T → C (every contract, with a rationale):** `concession.allocation_basis`, `cpc.incentive_asset_release_basis`, `royalty.unreported_sales`, `scope.repurchase_classification`, `vc.constraint`.
- **T → E:** `scope.lessor_combination_expedient`.
- **B → T:** `pob.shipping_as_fulfilment`, `step1.criteria_met_transition`, `loss.unit`.
- **T → B:** `licence.renewal_start`.
- **Not written (levels "import batch"):**
  - `migration.material_right_convention`, from the 10 LEGACY_PARITY keys (the preset supplies POL-212);
  - `onboarding.method`, from ONB-S11-MODRETRO-OWN.
- **Oracle reads.** The topics `akt_core.policy` now also reads contract overrides and product values (levels C and P), and raises when they disagree. No figure changed.

## 6. Keys added, renamed and withdrawn

| Key | Closes | Slice | Main figures (from the key) |
|---|---|---|---|
| SFC-CHK-137-S3-EX28-CASEB (renamed from SFC-S3-EX28-CASEB) | List C CHK-137 | topics | R-SFC-01 |
| SFC-CHK-136-S3-EX29-ANNUAL | CHK-136 ANNUAL row | topics | Contract liability 4,020.00 after January 2026, 4,240.00 at the end of 2026; revenue 4,494.40 at transfer |
| SFC-S3-EX26 | `AK:S3-EX26` | topics | R-SFC-03 |
| POB-S2-EX59 | `AK:S2-EX59` | topics | Revenue 225,628.66 at transfer; month 1 interest 1,128.14; total interest 14,371.34; renewal revenue 0.00 until 1 January 2028, then 225,628.66; unbilled receivable 216,756.80 after each first month |
| CPC-CHK-133-S3-EX32 (renamed from CPC-S3-EX32) | List C CHK-133 | topics | Incentive asset 1,500,000.00; January revenue 1,800,000.00; incentive asset 1,300,000.00 |
| POB-CHK-134-S2-WARRANTY-OWN (renamed from POB-S2-WARRANTY-OWN) | List C CHK-134 | topics | JET-16 Dr WARRANTY_EXPENSE / Cr WARRANTY_PROVISION 200.00 at transfer; extended warranty unchanged |
| NCC-CHK-135-S3-EX31 (renamed from NCC-S3-EX31) | List C CHK-135 | topics | Transaction price 52,000.00 from noncash consideration; January revenue 4,000.00; NONCASH_CONSIDERATION_ASSET Dr 3,000.00 net; BILLING_CLEARING (INVESTMENTS) Dr 1,000.00 |
| SSP-CHK-031-RANGE-VALIDATION-AT-PUBLICATION | List C CHK-031 | topics | RANGE_TOO_WIDE and COVERAGE_TOO_LOW (WARNING) on the ±25% version; none on the ±15% version |
| SSP-CHK-030-S4-SSPRANGE-OWN-OBSERVABLE-POINT | CHK-030 fifth variant (OQ-AKT-17) | topics | Licence SSP 150.00; allocations 140.00 / 280.00 |
| CPC-CHK-120-SHARE-BASED-WARRANTS-PROBABLE | List C CHK-120 | topics | Reductions 20,000.00 then 30,000.00; revenue 380,000.00 and 950,000.00 |
| CPC-CHK-120-SHARE-BASED-WARRANTS-NOT-PROBABLE | CHK-120 variant | topics | Reduction 20,000.00 reversed in December 2026; revenue 1,000,000.00 |
| ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION | List C CHK-121; `AK-FAM:business-combination` | topics | No lines in FY2025-P12. ASC606: 10,000.00 a month, liability 110,000.00 after January. IFRS15: 7,500.00 a month, liability 82,500.00 after January |
| FX-CHK-084-A-REFUND-LIABILITY-REMEASURED | List C CHK-084 | fx | JET-10d 6.00, 6.00, −4.00, 2.00; revenue 9,700.00 then 9,800.00; functional revenue 10,670.00 + 110.00 |
| FX-CHK-084-B-DEPOSIT-LIABILITY-REMEASURED | CHK-084 (b) | fx | Deposit 1,100.00 → 1,120.00; loss 10.00 at criteria met; contract-liability layer 1,130.00 |
| FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED | CHK-084 (c) | fx | Payable 55,000.00 → 54,500.00 (gain 500.00); incentive asset 55,000.00 |
| POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS | List C CHK-117 | fx (platform runner) | Unbilled receivable 3,000.00 and contract asset 2,000.00, both in `bucket_0_30`; equal to the JET-06 reclass |
| POS-S9-PRESENTATION-EX38-CASEA, -CASEB | Withdrawn | topics | R-DUP-01 |

## 7. Loader check

`research-harness/answer-keys/loader_check.py` implements the dev-guide §9.5 rules that can be checked without the product code:

- **Discovery and parsing:**
  - DG-AK-01 to DG-AK-04: path, family, id pattern, CHK containment, case-insensitive;
  - DG-AK-10 to DG-AK-27: top-level fields and types;
  - DG-AK-30: `_coverage/` ignored;
  - DG-AK-31: null and bool resolvers only; duplicate mapping keys raise.
- **Member sets.** §9.5.3 to §9.5.6, each object with extra members failing:
  - world, templates, products and SSP entries, including `population`;
  - portfolios and policies, with value shapes (literal, list, `{option, parameter}`, structured members of POL-047 and POL-073);
  - contracts and lines, including both modification line forms and questionnaire members;
  - estimates, including T-CON-13 parameter schemas and scenario probabilities summing to 1;
  - material rights and judgements;
  - the exact member sets of `payment_schedule`, `noncash_consideration` and `consideration_payable`;
  - timeline items, with payload members per event type parsed from 04 §16.3 plus the named handles;
  - checkpoints: contract blocks, T-CON-11 columns, API-S-ContractBalance fields, schedule, modifications, trace, subledger, journals, reports, `groups`, exceptions.
- **Cross-validation (DG-AK-32):**
  - handle resolution, including portfolios, combination groups and `renewal_of` booked at a lower seq;
  - enum literals from 04 §3.4 and E-01;
  - POL keys and allowed levels, and literals, from POLICIES §1;
  - REQ ids from 03, CHK ids from POLICIES, finding codes from 04 §15.4;
  - money places (DG-AK-51) and exact places (DG-AK-52);
  - runner restrictions; roles and clearing purposes (D-14a);
  - `tax_lines` exclusivity; `population` only with runner engine;
  - DG-AK-34: no EXPECTED_PURCHASES element that would be mapped, and no later version changing the promised amounts;
  - DG-AK-35 row keys and column keys;
  - labelled balances non-negative (T-CON-09).
- **DG-AK-54, static part:** exact subledger and journal blocks balance in transaction and functional amounts; DB-17 where the four fields are asserted.
- **DG-AK-33 coverage:**
  - `AK:` and `AK-FAM:` hints of 03;
  - POLICIES §0.7 family codes;
  - 03 §12.1 List A, §12.2 List B (the condition cell is parsed) and List C.

| Run | Keys | Errors | Coverage gaps |
|---|---|---|---|
| Baseline, before this pass | 221 | 90 in 45 keys: 85 policy levels (R-POL-01); 2 negative magnitudes (R-SCH-15); 2 MEMO_UPDATED `memo_1` and 1 unquoted-decimal report, both checker defects (04 writes `memo_1..3`; folded summaries), fixed in the checker | 12: `AK:S2-EX59`, `AK:S3-EX26`, `AK-FAM:business-combination`, List C CHK-031, CHK-084, CHK-117, CHK-120, CHK-121, CHK-133, CHK-134, CHK-135, CHK-137 |
| Final | 233 | 0 | 0 |

Not checked statically; the product loader and runners check these at run time:

- P1 and trace reevaluation (DG-AK-54);
- the DG-AK-34 mapping semantics;
- enum membership in `erev_engine.enums` (the checker uses 04 §3.4);
- report column keys of codes other than the four in the table "Report cell keys".

## 8. Final key counts

| Family | Active | Withdrawn | Family | Active | Withdrawn |
|---|---|---|---|---|---|
| ALC | 10 | 0 | MR | 12 | 0 |
| BRK | 6 | 0 | NCC | 1 | 0 |
| COST | 5 | 0 | ONB | 3 | 0 |
| CPC | 6 | 0 | POB | 16 | 0 |
| DISC | 8 | 0 | POS | 11 | 2 |
| DLT | 2 | 0 | REC | 24 | 0 |
| ENT | 5 | 0 | RET | 7 | 0 |
| FX | 11 | 0 | RND | 25 | 0 |
| IFRS | 4 | 0 | ROY | 3 | 0 |
| JE | 12 | 0 | SFC | 7 | 0 |
| LATE | 3 | 0 | SSP | 8 | 0 |
| LOSS | 2 | 0 | STP1 | 5 | 0 |
| MOD | 19 | 0 | TAX | 2 | 0 |
| | | | VC | 14 | 0 |
| **Total** | | | | **231** | **2** |

`PAR` keys appear as secondary families (15 keys); no key has `PAR` as `families[0]`.

## 9. Mechanical schema mismatches and open items for owners

None of these blocks `make answer-keys`. Each is recorded for the owner named, to be raised as a Spec question if the build meets it (D-77).

| # | Item | Owner | Effect on the corpus |
|---|---|---|---|
| 1 | ENGINE_SPEC S04-R-12 cites `dates.months_between` (floor). CHK-136, CHK-137 and the keys need the month-end count of R-SFC-02 | ENGINE_SPEC | Keys follow R-SFC-02 (D-§0: keys win for numbers) |
| 2 | S04-R-12 has no rule for accretion while expected returns exclude the whole consideration (FASB Example 26) | ENGINE_SPEC | SFC-S3-EX26 omits the return right (R-SFC-03) |
| 3 | ENGINE_SPEC_B §11.2.4 `impairment = max(0, total − recoverable)` and POLICIES JET-09c do not cap the impairment at the carrying amount | ENGINE_SPEC_B, POLICIES | Keys cap it (R-COST-01) |
| 4 | dev-guide §9.5.5 `tax_lines: [{tax_type, jurisdiction?, amount}]` differs from 04 §16.3 `{tax_type, amount, principal_or_agent}` | dev-guide, 04 (04 governs, D-73) | No key uses `tax_lines` |
| 5 | POL-210 and POL-212 (levels "import batch") and POL-216 and POL-217 ("acquisition") cannot be carried by `world.policies`, and 04 §16.3 has no election members on OPENING_BALANCE_ESTABLISHED | dev-guide, 04 | Values dropped (R-POL-01); CHK-121 expedient (b) not authored; the LEGACY_PARITY preset supplies POL-212 |
| 6 | §9.5.4 `judgements` has no `questionnaire` member, although ENGINE_SPEC reads T-CON-19 questionnaire outcomes: SFC_ASSESSMENT `significant` and `exception_32_17`, NOT_A_CONTRACT `consideration_nonrefundable`, BILL_AND_HOLD criteria, LICENCE_NATURE `nature` | dev-guide, ENGINE_SPEC | Keys carry the conclusion text only. The engine runner must resolve these records, for example so that a template with `sfc_assessment_required` does not raise SFC_REVIEW_REQUIRED |
| 7 | SCREENS_B RPT-36 lists `bucket_0_30` to `bucket_181_365` and the row key `contract:<external id>:<role>` without naming the role literal | SCREENS_B | POS-CHK-117 asserts `bucket_0_30` and `bucket_31_90` with E-01 role literals |
| 8 | The fx SfcBook implements `compounding` MONTHLY only; ANNUAL is asserted by the topics oracle | Harness | None |

## 10. R-series post-B3 (post-B3 residue sweep, 2026-09-12)

This is a supervisor-directed correction of known residue (slug `numeric-residue`). Under D-77 it opens no question: each ruling takes the most reasonable default. The owner texts changed are ENGINE_SPEC rev 1.3, ENGINE_SPEC_B rev 1.3, POLICIES rev 1.3 and dev-guide §9.5 (revision row 1.3). The requests for 04 are in `docs/reviews/B4-requests-for-04.md`, and the change record is `docs/reviews/B4-numeric-residue.md`.

### 10.1 Rulings

| Id | Residue | Ruling | Owner texts | Keys |
|---|---|---|---|---|
| R-SFC-04 | Section 9 item 1; R-SFC-02 | The month-end count of R-SFC-02 is the convention: n = the calendar month ends after the earlier and up to the later of the payment date and the transfer date, and ⌊n ÷ 12⌋ whole years under `ANNUAL`. Rationale: S04-R-12 accretes once per month end, so discounting on the same grid settles the schedule exactly. Under the floor of whole months, the CHK-137 cash selling price would be 856,830.00 instead of 848,346.53, and the 60th instalment would leave a residual above one minor unit (`SFC_SCHEDULE_UNSETTLED`). The oracle-verified keys were right | ENGINE_SPEC S04-R-12, EX-04-B2; POLICIES POL-047 notes, CHK-136, CHK-137 | None (the keys already followed R-SFC-02) |
| R-COST-03 | Section 9 item 3; R-COST-01 | JET-09c = min(carrying, max(0, carrying − recoverable)) is adopted in the owner texts. A negative recoverable amount impairs the whole carrying amount and no more; the excess belongs to the Subtopic 605-35 loss test when the contract is in that scope | ENGINE_SPEC_B §11.2.4, S11-R-08, EX-11-A floor row; POLICIES JET-09c | None (`COST-S8-CONTRACT-COSTS-IMPAIRMENT` already asserted the floor: 5,000.00 at `end-2028-floor`) |
| R-SGN-01 | BUILD_SPEC Appendix B.2 B3-BS2-13 | One sign convention: `expected_returns_amount` and `consideration_payable_amount` carry the S04-R-02 member sign and are ≤ 0. The 04 columns have no sign note, and DB-17 V1, DG-ENG-05, DG-AK-54 and dev-guide §9.7 P1 all read Σ `allocated_amount` = `transaction_price − consideration_payable_amount`; only the signed member makes that the gross allocation basis. Magnitudes would have required "+" in documents outside the corpus. Obligation `revenue_cum` is the gross stage 09 target (ENGINE_SPEC_B Table 14-A, JET-02 row); `contract_version.revenue_cum` is net of the JET-14 release | ENGINE_SPEC S04-R-02, EX-04-D; dev-guide §9.5.6, DG-AK-32; requests R04-01 to R04-03 | `RET-CHK-029-S3-EX22`, `RET-CHK-060-S3-EX22-REVISED`, `CPC-CHK-133-S3-EX32`, `CPC-BR-07-CASEB-MDF-EXCESS-OVER-FAIR-VALUE`, `CPC-WM-03-BUYER-PROMOTIONS-NEGATIVE-REVENUE-TEST` |
| R-V1-01 | Survey of every key that uses the memo members or asserts Σ `allocated_amount` against `transaction_price` | V1 holds in every key. `CPC-BR-07-CASEB` and `CPC-WM-03` keep the gross allocation (the allocation basis excludes consideration payable). `POB-JS-05-CASEA` and `-CASEB` include realised royalties in the licence allocation (ENGINE_SPEC_B S09-R-02), so the DB-17 obligation identity also holds. The loader check now tests V1 where a contract block outside a combination group asserts every obligation | None | `CPC-BR-07-CASEB-…`, `CPC-WM-03-…`, `POB-JS-05-CASEA-FRANCHISE-PUBLIC`, `POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT` |
| R-SFC-05 | Section 9 item 2; R-SFC-03 | New S04-R-12a. While expected returns exclude the whole consideration of a financed obligation (deferred payment), no interest accretes. From L, the first date on which the revenue target is positive, the total interest Σ payments − round(CSP) is recognised over the remaining months, weighted by the exact monthly interest of the inception schedule and cumulatively rounded; there is no catch-up and only integer powers are used (CV-31). An advance payment is never suspended | ENGINE_SPEC S04-R-12a, EX-04-H, §4.4 trace params; POLICIES POL-047 notes, JET-11 11a, FASB Example 26 paragraph | New `SFC-S3-EX26-RETURN-RIGHT`; `SFC-S3-EX26` (summary cross-reference) |
| R-RET-01 | S04-R-08 measures the memo on Y + E, with no example where Y > 0 | EX-04-G2 (verified by script). The two returns keys assert the memo and the transaction price after the returns and at window expiry | ENGINE_SPEC EX-04-G2 | `RET-CHK-029-S3-EX22`, `RET-CHK-060-S3-EX22-REVISED` |
| R-SCH-16 | Section 9 item 4 | `BILLING_RECORDED.tax_lines` members are those of 04 §16.3, `{tax_type, amount, principal_or_agent}`, which govern the payload (D-73). 04 T-SRC-05 holds another member set; request R04-04 aligns it | dev-guide §9.5.5, DG-AK-32; `loader_check.py` | None (no key uses `tax_lines`) |
| R-SCH-17 | Section 9 item 6 | Judgements gain the member `questionnaire`: exactly the 04 T-CON-19 members of the topic, typed, with resolving handles. It is required when the topic's schema has required members; otherwise the record is evidence only. The engine runner renders the members as strings in `JudgementInput.outcome`. Keys now supply the outcomes the engine reads: `SFC_ASSESSMENT` (so no `SFC_REVIEW_REQUIRED` is raised), `BILL_AND_HOLD` (ENGINE_SPEC_B S09-R-12), `OTHER` `claim_enforceable` and `discount_exception_bundle`, and the required members of `NOT_A_CONTRACT`, `CONTRACT_TERM`, `PRINCIPAL_AGENT` and `WARRANTY_TYPE` | dev-guide §9.5.4, DG-AK-32, DG-AK-40; ENGINE_SPEC Table 0.4-A title | 25 keys, section 10.2 |
| R-CHK-02 | POLICIES CHK-084 and the CHK-136 `ANNUAL` row | Covered, no key added. `FX-CHK-084-A` (JET-10d losses 6.00 in March and 2.00 net in April and May; functional revenue 10,670.00 + 110.00), `FX-CHK-084-B` (losses 20.00 and 10.00; contract liability 1,130.00) and `FX-CHK-084-C` (gain 500.00; incentive asset 55,000.00) equal CHK-084 (a) to (c). `SFC-CHK-136-S3-EX29-ANNUAL` (liability 4,020.00 after January 2026 and 4,240.00 at the end of 2026; December 2027 interest 21.20; revenue 4,494.40) equals the `ANNUAL` row | None | None |
| R-ALG-01 | Industries FS-03B, FS-10, JS-06, GE-08 against ALG-04 §2.5.5 | They agree to the cent. An independent recomputation, C_t = R_p + round((X′_p − R_p) × g_t) bounded by A′_p, compares 46 asserted post-modification leaves (allocated amounts, revenue and the FS-03B schedule), with 0 failures. The posted-share variant would give the same figures on these leaves | None | None |

### 10.2 Keys changed (old → new)

| Key | Change |
|---|---|
| `RET-CHK-029-S3-EX22` | `end-of-january` `expected_returns_amount` 300.00 → −300.00. New leaves: `end-of-february` `transaction_price` 9,700.00, `expected_returns_amount` −300.00, obligation `allocated_amount` 9,700.00; `window-expired` `transaction_price` 9,800.00, `expected_returns_amount` −200.00 |
| `RET-CHK-060-S3-EX22-REVISED` | `end-of-january` `expected_returns_amount` 400.00 → −400.00. New leaves: `end-of-february` `transaction_price` 9,600.00, `expected_returns_amount` −400.00, obligation `allocated_amount` 9,600.00; `window-expired` `transaction_price` 9,800.00, `expected_returns_amount` −200.00 |
| `CPC-CHK-133-S3-EX32` | `at-inception` `consideration_payable_amount` 1,500,000.00 → −1,500,000.00; new `transaction_price` 13,500,000.00 and obligation `allocated_amount` 15,000,000.00. `end-of-month-1` obligation `revenue_cum` 1,800,000.00 → 2,000,000.00. Summary |
| `CPC-BR-07-CASEB-MDF-EXCESS-OVER-FAIR-VALUE` | `consideration_payable_amount` 20,000.00 → −20,000.00 and obligation `allocated_amount` 980,000.00 → 1,000,000.00, at all three checkpoints. Summary |
| `CPC-WM-03-BUYER-PROMOTIONS-NEGATIVE-REVENUE-TEST` | `consideration_payable_amount` 15,000.00 → −15,000.00 and obligation `allocated_amount` 5,000.00 → 20,000.00, at both checkpoints. Summary |
| `POB-JS-05-CASEA-FRANCHISE-PUBLIC` | `year-1` `L1-LICENCE` `allocated_amount` 50,000.00 → 146,000.00; questionnaire |
| `POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT` | `year-1` `L1-LICENCE` `allocated_amount` 37,894.74 → 133,894.74; questionnaire |
| `SFC-S3-EX26-RETURN-RIGHT` (new; topics) | Before lapse: `transaction_price` 0.00, `expected_returns_amount` −100.00, `financing_adjustment_amount` −21.00, return asset 80.00, nothing posted in FY2026-P03. April 2026: revenue 100.00, interest 0.95, unbilled receivable 100.95. End of 2026: 108.51. Before the invoice: 121.00. December 2027: interest 1.04 |
| `SFC-S3-EX26` | Summary cross-reference to the new key; questionnaire |
| `REC-BR-04-BILL-AND-HOLD-CUSTODIAL` | Judgement topic `OTHER` → `BILL_AND_HOLD`, with questionnaire |
| `REC-S5-EX63-OWNSSP`, `RND-CHK-006-S5-EX63-OWNSSP-CUSTODY` | `BILL_AND_HOLD` judgements added (one, and two) |
| Questionnaire only | `SFC-CHK-137-S3-EX28-CASEB`, `SFC-S3-EX29`, `SFC-CHK-136-S3-EX29-ANNUAL`, `POB-S2-EX59` (two records), `SFC-FS-11-CASEA-UPFRONT-NO-FINANCING` (`significant` false), `SFC-FS-11-CASEB-UPFRONT-ADVANCE-ACCRETION`, `SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE`, `JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION`, `STP1-S1-EX1-CASEB-C-VARC`, `JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY`, `FX-CHK-084-B-DEPOSIT-LIABILITY-REMEASURED`, `DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO`, `POB-S2-EX45-AGENT-AGENT`, `POB-S2-EX45-AGENT-PRINCIPAL`, `POB-WM-01-THIRD-PARTY-COMMISSIONS-NET`, `ROY-JS-07-ADVERTISING-FUND-GROSS`, `POB-BR-01-ROBOTS-PLATFORM-EXTENDED-WARRANTY`, `MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM`, `ALC-CHK-032-S4-EX34-CASEC-ESTIMATED`, `ALC-CHK-032-S4-EX34-CASEC-REJECTED`, `ALC-CHK-033-S4-EX34-CASEB`, `ALC-CHK-034-S4-EX34-CASEA` |

Questionnaire values chosen without facts in the key: `NOT_A_CONTRACT` `consideration_nonrefundable` false (the three deposit keys assert no 606-10-25-7 revenue; false is the value under which S02-R-07 events (a) to (c) cannot fire); `CONTRACT_TERM` of GE-06 `enforceable_end_date` 2027-01-31 (the end of the base task order) and `termination_penalty_substantive` false (no `termination` member, so S02-R-06 truncates nothing); agent outcomes `FIXED_FEE` with the line amount (the lines already carry the retained consideration, so S03-R-09 leaves the stated price unchanged).

### 10.3 Harness, results and counts

- **Harness files changed.**
  - `adjudication.py`: variant pair `SFC-S3-EX26` / `SFC-S3-EX26-RETURN-RIGHT`.
  - Topics: new `specs_b4.py` (oracle `sfc_returns_oracle`); `specs_step1_3.py` (returns oracle memo on Y + E with the member sign; questionnaires); `specs_gaps.py` (CPC signs, gross obligation revenue, V1 leaves; agent questionnaires); `specs_rec.py`; `specs_mr_mod.py`; `akt_run.py` (module list; E-56 `BILL_AND_HOLD`).
  - Industries: `d01_fernhill_b.py`, `d02_bracken.py`, `d04_granitefield.py`, `d05_juniper.py`, `d12_wayfarer.py`, `capabilities.py`.
  - fx-entity-books: `keys_je.py`, `keys_b3.py`, `keys_rnd.py`.
  - `loader_check.py`: questionnaire per T-CON-19, `tax_lines` members, memo sign, V1.
- **Results (2026-09-12, after every change).**
  - Topics: `akt_run.py generate` 110 keys, then `verify` 110 keys, 0 errors.
  - `check_golden.py`: 508 comparisons, 0 mismatches.
  - Industries: `run_oracle.py build` and `verify`, 57 keys, 0 failing.
  - fx-entity-books: `build.py` and `verify.py`, 67 keys, 0 failing; the 6 document comparisons are the expected ones of section 1.
  - `loader_check.py`: 234 keys, 0 errors, 0 coverage gaps, 0 notes.
- **Counts.** 234 files: 232 active and 2 withdrawn. By author: topics 110 (108 active), industries 57, fx-entity-books 67. SFC 8 active.
- **Scratch.** `.scratch/b4-numeric-residue/`: `backup/` (both trees and the four owner texts before the sweep); `verify_b4.py` (75 checks, all pass); `alg04_check.py` (46 leaves, 0 failures); `survey_v1.py`; run logs.

### 10.4 Section 9 status

| Item | Status |
|---|---|
| 1 | Closed by R-SFC-04 |
| 2 | Closed by R-SFC-05 |
| 3 | Closed by R-COST-03 |
| 4 | Closed by R-SCH-16; 04 request R04-04 |
| 5 | Unchanged (outside this sweep) |
| 6 | Closed by R-SCH-17 |
| 7, 8 | Unchanged (outside this sweep) |

## 11. Errata under supervisor ruling R-46 (2026-09-30)

Ruling R-46 (`docs/reviews/loop/prod/RULINGS-2026-09-29.md`) corrects two topics keys through their oracle. It rests on the memo `docs/accounting/reviews/AD-13-14-34-MEMO-2026-09-29.md` (lane ACCT; commits `3df76d87` and `e6bf4195`) and on the memo's independent review, which the ruling names (`docs/accounting/reviews/AD-13-14-34-MEMO-REVIEW-2026-09-29.md`, a run record of the supervisor outside the repository; section 2.2 of the memo records it and the four reviews inside the lane). Both entries are **supervisor rulings pending the independent revenue accountant**: nothing here is an approval, and both keys keep `review.status: pending` (G12 AD-34 and AD-13). The keys change under D-99 (8), by a recorded ruling with its evidence. No engine code changes: after the corrections the oracle and the engine agree on every asserted leaf of both keys.

### 11.1 `POB-S2-EX61`: a realised royalty is inside the price and the allocation

| Field | Value |
|---|---|
| Ruling | R-46 (a). **Supervisor ruling pending the independent accountant** (G12 AD-34); `review.status: pending` |
| Memo | Section 3 (disposition 1 of its section 1; mechanics in sections 3.7 and 6) |
| Review | The independent review named in R-46 upheld the disposition and the three values. Its other findings on this key concern cited facts and authorities, and the argument on AD-34b (section 11.4) |
| Class | Defect of the oracle, corrected in the oracle. No input change, no engine change |
| Key file | `docs/accounting/answer-keys/pob/POB-S2-EX61.yaml`; SHA-256 `0cdc10c8…e27b` → `5a263468…958e` |

Cause. The topics oracle (`akt_engine.py`) left a royalty statement on a licence obligation out of `transaction_price` and `allocated_amount` and still subtracted its revenue. The key therefore held `remaining_allocation` 1,450,000.00 beside a fixed schedule with 1,500,000.00 still to recognise, an awaiting-trigger amount of −50,000.00. ENGINE_SPEC S04-R-02 and S04-R-06 and ENGINE_SPEC_B S09-R-02 put a realised royalty inside both measures; R-V1-01 (section 10.1) already records realised royalties inside the licence allocation of `POB-JS-05-CASEA` and `-CASEB`. The same gap of the same oracle was ruled the engine's way for `POS-CHK-010` (D-98 candidate 29); there the value was changed in the key file and the oracle left as it was (section 11.3).

Oracle correction. `Engine.royalty_statements` gives S, the sum of the royalty statements to the checkpoint date on an obligation that is not itself measured by usage, taken before the zero-progress test. `transaction_price` = the fixed and estimated price + S; `allocated_amount` = A + S; `remaining_allocation` = A + S − revenue; `allocated_exact` and `allocation_adjustment` follow; a statement realised before any satisfaction is awaiting trigger. Revenue, billing, balances, the schedule and the subledger are computed as before.

| Checkpoint | Block | Leaf | Before | After |
|---|---|---|---|---|
| `end-of-q1` (2026-03-31) | contract `C-LOGO`, `version` | `transaction_price` | "2000000.00" | "2050000.00" |
| `end-of-q1` | obligation `L1-LIC` | `allocated_amount` | "2000000.00" | "2050000.00" |
| `end-of-q1` | obligation `L1-LIC` | `remaining_allocation` | "1450000.00" | "1500000.00" |

Nothing else changes: no input; at `end-of-q1` `revenue_cum` "550000.00", `billed_cum` "2000000.00", the balances (contract liability "1450000.00"), the schedule and the subledger; the checkpoint `end-of-april`; the summary, which states neither measure.

### 11.2 `SFC-S3-EX26-RETURN-RIGHT`: the right lapses on its window-end day (form A)

| Field | Value |
|---|---|
| Ruling | R-46 (b): the reading that D-87 L6-5-Q-25 ruled for the engine, in form A. **Supervisor ruling pending the independent accountant** (G12 AD-13), to whom the merits remain; `review.status: pending` |
| Memo | Section 4 (disposition 3 of its section 1; form A of section 4.5; mechanics in sections 4.6 and 6) |
| Review | The independent review named in R-46 upheld the disposition. Its finding 4 added two passages of the build spec to those of section 4.5 (ENA-8 and ENC-7 of fragment 12), held the §9.2.7 pseudocode of ENGINE_SPEC_B to be binding text, and required the summary sentence to change under form A |
| Class | Defect of the oracle, corrected in the oracle. No input change, no checkpoint name or date change, no engine change |
| Key file | `docs/accounting/answer-keys/sfc/SFC-S3-EX26-RETURN-RIGHT.yaml`; SHA-256 `e80a43fa…3404` → `991bae05…2f81` |

Cause. The key's oracle (`specs_b4.sfc_returns_oracle`) expired the right on the day after the window (`t > window`, and `window_end_date` + 1 day as the candidate for L), the reading of the first text of ENGINE_SPEC_B S09-R-26. D-87 L6-5-Q-25 ruled for the engine that a return right expires at the end of `window_end_date` and that a measurement dated on or after it has E = 0. The checkpoint `return-right-open` is dated on the window end, 2026-03-31. The owner texts that still carried the day-after reading were aligned first (section 11.3). The merits, whether a right whose last exercisable day is the reporting date has lapsed at that date, remain the accountant's.

Oracle correction. `t >= window`, and the candidate for L is `window_end_date` itself. This is form A of the memo: values at the existing checkpoints only. No input, checkpoint name or checkpoint date changes, so the rule on amended inputs (`docs/reviews/loop/prod/readiness-matrix.md`, row FK-J) is not engaged.

| Checkpoint | Block | Leaf | Before | After |
|---|---|---|---|---|
| `return-right-open` (2026-03-31) | contract `C-EX26R`, `version` | `transaction_price` | "0.00" | "100.00" |
| `return-right-open` | contract `C-EX26R`, `version` | `expected_returns_amount` | "-100.00" | "0.00" |
| `return-right-open` | contract `C-EX26R`, `version` | `revenue_cum` | "0.00" | "100.00" |
| `return-right-open` | obligation `L1-PRODUCT` | `allocated_amount` | "0.00" | "100.00" |
| `return-right-open` | obligation `L1-PRODUCT` | `revenue_cum` | "0.00" | "100.00" |
| `return-right-open` | balances `US01` | `unbilled_receivable` | "0.00" | "100.00" |
| `return-right-open` | balances `US01` | `return_asset` | "80.00" | "0.00" |
| `return-right-open` | subledger FY2026-P03, `US01` (`role_account`, `exact`) | `lines` | `[]` | `COST_OF_REVENUE` 5000 dr "80.00"; `RETURN_ASSET` 1310 cr "80.00"; `REVENUE` 4000 cr "100.00"; `UNBILLED_RECEIVABLE` 1105 dr "100.00" |
| `right-lapsed` (2026-04-30) | subledger FY2026-P04, `US01` (`role_account`, `exact`) | `lines` | `COST_OF_REVENUE` 5000 dr "80.00"; `INTEREST_INCOME` 7000 cr "0.95"; `RETURN_ASSET` 1310 cr "80.00"; `REVENUE` 4000 cr "100.00"; `UNBILLED_RECEIVABLE` 1105 dr "100.95" | `INTEREST_INCOME` 7000 cr "0.95"; `UNBILLED_RECEIVABLE` 1105 dr "0.95" |
| (header) | `summary` | one clause | "From 1 April 2026 expected returns are nil: revenue 100.00, JET-07c reverses the return asset, and the 21.00 of financing interest …" | "The right lapses at the end of 31 March 2026 (D-87 L6-5-Q-25): revenue 100.00 and the JET-07c reversal of the return asset post in March 2026, the unbilled receivable is 100.00 at 31 March 2026, and the 21.00 of financing interest …" |

Unchanged: at `return-right-open` `financing_adjustment_amount` "-21.00", `billed_cum` "0.00", `contract_liability` "0.00", `refund_liability` "0.00" and the FY2026-P01 lines; every contract, obligation and balance leaf of `right-lapsed` (unbilled receivable "100.95"); the checkpoints `end-of-2026`, `before-settlement-invoice` and `settlement-invoice`; every interest figure (0.95 in April 2026, 8.51 for months 4 to 12, 12.49 for months 13 to 24, 1.04 in December 2027). The checkpoint keeps the name `return-right-open` although it now holds the lapsed state; form B of the memo, which re-dates it, was not taken. The row of this key in section 10.2 is the record of revision 1.3 and is not rewritten; for the leaves above this entry governs.

### 11.3 Harness, results and counts

- **Owner texts aligned first** (commit `9aef32e1`; no engine change, no figure change): ENGINE_SPEC rev 1.57 (S04-R-12a, EX-04-H), ENGINE_SPEC_B rev 1.64 (§9.2.7 pseudocode, S09-R-26), POLICIES rev 1.33 (JET-11, FASB Example 26 paragraph), 04 rev 1.116 (T-CON-13 `window_end_date`), BUILD_SPEC header 1.47 with fragment 12 rev 1.5 (ENA-8, ENC-7, AKS-3).
- **Harness files changed** (`research-harness/answer-keys/answer-keys-topics/`; commit `70c7c4e5`, with the two keys).
  - `akt_engine.py`: `Engine.royalty_statements`; `revenue`, `state` and `values` use it.
  - `specs_b4.py`: the window test and the candidate for L in `sfc_returns_oracle`; the summary clause of the key.
  - `akt_run.py`: new command `generate-only <ID> [<ID> ...]`, which writes the named keys and no other file.
- **How the two keys were written.** `akt_run.py generate-only POB-S2-EX61 SFC-S3-EX26-RETURN-RIGHT`: the generator's own functions build, materialise and emit the two specs; no expected value is typed by hand. `akt_run.py generate` was not run. At this state of the corpus it would also rewrite 13 keys that carry later rulings the generator does not hold: the `value_basis` line of D-93 (4) on twelve keys, and the `transaction_price` of `POS-CHK-010` under D-98 candidate 29 (the memo's section 6 lists them).
- **Results (2026-09-30).**
  - All 117 topics specs rendered in memory, nothing written. With the oracle as it was, 104 equal the committed files and 13 differ (the 13 above). With the corrected oracle, 102 and 15. The two renders differ in these two files only: no other topics key depends on the royalty rule or on the window test.
  - The commit changes two files under `docs/accounting/answer-keys/`, these two.
  - `akt_run.py verify`: 117 keys, 1 error, `POS-CHK-010` `end-of-p1` `transaction_price` expected "15000.00", computed "12000.00". The error exists before this erratum and stays until the right-to-invoice path of the oracle is corrected.
  - Engine, `make answer-keys` on the committed engine: the two ids, 2 selected, 2 passed; the eight keys that carry a return window and the variant `SFC-S3-EX26`, 9 selected, 9 passed; the twelve royalty and usage keys of the memo's section 3.1, 12 selected, 12 passed; the release selection, 222 selected, 222 passed; the corpus (`AK_SCOPE=full`), 254 selected: 246 passed, 1 failed (`VC-CHK-113-TC-POBVC-16`, section 11.4), 5 not run (the platform-runner keys: the lane's worktree has no database), 2 withdrawn.
- **Counts.** Unchanged: 254 files, 252 active and 2 withdrawn; of the active keys 247 engine-runner and 5 platform-runner. Release selection `docs/reviews/loop/sprint/rg-selection.txt`: 220 → 222 ids (R-46 (c); commit `2c8e867d`).

### 11.4 Not covered by R-46

- `VC-CHK-113-TC-POBVC-16` (G12 AD-14 and AD-15; D-98 questions 109 and 110). R-46 (d) does not rule it. The key, its builder, the oracle branch and the drafts are unchanged; the key fails as before (7 mismatches) and stays outside the release selection. The memo's recommendations on it (its section 5; dispositions 4 and 5) are the adjudication packet for Ray and the accountant.
- AD-34b (R-46 (e)): the presentation of an unbilled realised royalty against a contract liability stays a policy question for the accountant. `POB-S2-EX61` keeps its balances.
