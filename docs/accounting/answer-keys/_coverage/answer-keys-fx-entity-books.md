# Answer-key coverage: FX, multi-entity, books, disclosures, rounding, netting, posting templates and late events

| Field | Value |
|---|---|
| Author | Answer-key engineer, slug `answer-keys-fx-entity-books` (design phase B2) |
| Date | 2026-09-12 |
| Status | Draft for revenue-accountant review (G12). Every key has `review.status: pending` |
| Scope | Families FX, ENT, IFRS (books), DLT, DISC, RND, POS, JE, LATE. Closes M-RA-02 and M-RA-03 on the corpus side |
| Schema | `erev-answer-key/1`, `docs/dev-guide.md` §9.5 (DG-AK-01 to DG-AK-55) |
| Oracle | `research-harness/answer-keys/answer-keys-fx-entity-books/` |
| Result | 67 active keys (B3 adjudication); 67 lint clean; every checkpoint value recomputed exactly from the key inputs; 0 failing |

> **B3 adjudication (2026-09-12).** `_coverage/ADJUDICATION.md` rules on every discrepancy (D-AK-01 to D-AK-13), on the section 7 observations and on every open question (OQ-AK-01 to OQ-AK-16) of this file. Where this file differs, `ADJUDICATION.md` governs. The changes are:
>
> - **New keys** in `keys_b3.py`:
>   - FX-CHK-084-A-REFUND-LIABILITY-REMEASURED, -B-DEPOSIT-LIABILITY-REMEASURED and -C-CONSIDERATION-PAYABLE-REMEASURED (D-25b);
>   - POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS, platform runner.
> - **CHK coverage.** CHK-133, CHK-134, CHK-135 and CHK-137 are no longer blocked. The topics keys CPC-CHK-133-S3-EX32, POB-CHK-134-S2-WARRANTY-OWN, NCC-CHK-135-S3-EX31 and SFC-CHK-137-S3-EX28-CASEB carry them; this supersedes sections 3.2, 3.6 and D-AK-08. After B3 every POLICIES CHK id is covered.
> - **Duplicates.** JE-CHK-024 Cases A and B absorb the assertions of the withdrawn topics keys POS-S9-PRESENTATION-EX38-CASEA and -CASEB (R-DUP-01). The other section 7 duplicates are kept as cross-referenced variants (R-DUP-02).
> - **Section 7 observations.** The −85,000.00 and the 846,527.30 / 836,121.57 figures came from superseded generations (R-COST-01, R-SFC-01).
> - **Schema:**
>   - JE-CHK-132 carries `scope_605_35: true` (D-AK-12 superseded);
>   - JE-CHK-136 carries `compounding: MONTHLY`;
>   - ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP asserts `groups`;
>   - RND-CHK-006-S12 marks its pre-opening SKU;
>   - VC-TIMING drops its negative `most_conservative_amount` (R-SCH-15);
>   - CostBook caps the impairment at the carrying amount and adds anticipated renewals (R-COST-01).
> - **Document comparisons.** `docexp.py` now transcribes POLICIES rev 1.2 for the CHK-006 rows and the CHK-136 MONTHLY row, and those comparisons agree. The remaining differences are research 04 plugs and the ANNUAL figures of research 04 S3-EX29.
> - **Commands.** Add `UV_OFFLINE=1` and `--offline` to the commands of section 1. `build.py` calls the shared `research-harness/answer-keys/adjudication.py`.

## 1. How to rerun the oracle

```sh
cd ~/dev/erev/research-harness/answer-keys/answer-keys-fx-entity-books
uv run --no-project --with pyyaml python verify.py            # lint + exact recomputation + document comparisons
uv run --no-project --with pyyaml python verify.py --quiet    # failures and document comparisons only
uv run --no-project --with pyyaml python build.py             # regenerate the 63 YAML files from the specs
uv run --no-project --with pyyaml python build.py <KEY-ID>    # regenerate one key
```

| File | Role |
|---|---|
| `akcore.py` | ALG-01 round half up, largest remainder, cumulative posting C_t = round(X × f_t) bounded by A (D-11a); ALG-11 DAILY, MONTHLY_EVEN, MID_MONTH; monthly period keys. Standard library, `fractions.Fraction` only |
| `akyaml.py` | DG-AK-03 emitter; DG-AK-31 loader (implicit resolvers null and bool only, duplicate keys raise) |
| `aknative.py`, `akfill.py` | Input model and generic checkpoint filler: allocation, progress, schedules, ALG-02 position and reclass (POB_DEBIT_POSITIONS and CUMULATIVE_SSP_DELIVERED), JET-02, JET-03 (ENGINE with tax), JET-06 with reversal, JET-13 |
| `akvc.py` | Estimate versions and price-change modifications: TP at a date, catch-ups by cause, JET-04b refund targets, `revenue_prior_period` decomposition (ALG-10 §2.11.3) |
| `keys_fx.py` | FxBook: ALG-08 liability layers, asset layers, settlement, closing remeasurement, monetary override, ENGINE receivables |
| `keys_ent.py`, `keys_late.py`, `keys_books.py`, `keys_je.py`, `keys_disc.py`, `keys_rnd.py`, `keys_pos.py`, `golden.py`, `common.py` | Key specs (inputs and checkpoint skeletons) and topic models: LateMixin (ALG-09), DeltaBook (JET-15), Step1Book (JET-01b), ShippingBook (POL-021), CostBook (JET-09), LossBook (JET-12), SfcBook (JET-11b), ConcessionBook (JET-04c), ReportBook (report cells) |
| `build.py` | Writes each key: builder inputs, then oracle values computed over the loaded (string) inputs |
| `verify.py` | Loads every YAML file with the DG-AK-31 loader, lints DG-AK rules, re-runs the oracle over the loaded inputs and compares every asserted value; flags orphan files of this slice |
| `docexp.py` | Figures transcribed from POLICIES CHK rows, research 04 keys and PRD WLD-X-14. Used only for the comparisons in section 6, never to fill a key |

Independence. The oracle reads prices, SSPs, quantities, dates, rates, payloads and policies from the YAML inputs. No expected number is copied from a document. `verify.py` compares 353 published figures across 52 keys against the recomputed keys; the 19 differences are explained in section 6 (D-AK-02, D-AK-03, D-AK-05).

## 2. Key inventory

Runner `engine` unless marked (P) for `platform`. Books ASC606 unless stated.

| Family | Key id | Source items | Books |
|---|---|---|---|
| FX | `FX-CHK-080-LIABILITY-LAYERS-AT-HISTORICAL-RATES` | CHK-080; ALG-08; IFRIC 22 | ASC606, IFRS15 |
| FX | `FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE` | CHK-081; JET-10a; JET-06 functional | |
| FX | `FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22` | CHK-082; D-25a; POL-163; JET-10b | ASC606, IFRS15 |
| FX | `FX-CHK-083-ENGINE-RECEIVABLE-REMEASUREMENT` | CHK-083; JET-10a′ | |
| FX | `FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15` | POL-160 US election vs IFRIC 22 forced | ASC606, IFRS15 |
| FX | `FX-POL-161-FIFO-TWO-LAYERS-IN-ONE-PERIOD` | POL-161 FIFO within a period | |
| FX | `FX-JPY-CONTRACT-USD-FUNCTIONAL-MINOR-UNITS` | C-06 JPY exponent 0 | |
| FX | `FX-BHD-FUNCTIONAL-USD-CONTRACT-MINOR-UNITS` | C-06 BHD exponent 3 | |
| ENT | `ENT-CHK-070-INTERCOMPANY-PAIR-PERFORMING-ENTITY` | CHK-070; JET-13; POL-170 default | |
| ENT | `ENT-CHK-070-CONTRACTING-ENTITY-RECOGNISES-REVENUE` | CHK-070 alternative | |
| ENT | `ENT-CHK-071-CONTRACT-ASSET-HELD-BY-CONTRACTING-ENTITY` | CHK-071 | |
| ENT | `ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP` | POL-120; REQ-ENT-002; group allocation across entities | |
| ENT | `ENT-CROSS-CURRENCY-PAIR-GBP-CONTRACT-USD-PERFORMER` | PRD WLD-K-04 and WLD-X-14; ALG-07 step 5; POL-171 | |
| IFRS | `IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK` | §6.2 #1; POL-011, POL-128; JET-01b | ASC606, IFRS15 |
| IFRS | `IFRS-SW04-SHIPPING-FULFILMENT-ELECTION-VS-SEPARATE-OBLIGATION` | §6.2 #4; POL-021 | ASC606, IFRS15 |
| IFRS | `IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY` | §6.2 #11; POL-151, POL-152 | ASC606, IFRS15 |
| DLT | `DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS` (P) | CHK-020, CHK-022; GT-04, GT-05, GT-07; JET-15 | ASC606, LEGACY |
| DLT | `DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT` | POL-005, POL-008; REQ-BK-005 | ASC606, LEGACY |
| DISC | `DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE` | CHK-101; S3-EX23; S10-DISCLOSURES | |
| DISC | `DISC-CHK-006-S10-DISCLOSURES-ROLLFORWARD-EX21` | CHK-006 row S10; S10-DISCLOSURES | |
| DISC | `DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING` (P) | S10-DISCLOSURES rollforward, opening-liability revenue, timing disaggregation | |
| DISC | `DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT` (P) | S10-DISCLOSURES rpo_ex42; POL-198, POL-201 | |
| DISC | `DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION` | REQ-MOD-015; 50-10; ALG-10 §2.11.3 | |
| JE | `JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY` | CHK-021; JET-01b | |
| JE | `JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING` | CHK-023; JET-03 | |
| JE | `JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE` | CHK-024 Case A; POL-123 | |
| JE | `JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE` | CHK-024 Case B | |
| JE | `JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY` | CHK-025; JET-04a, JET-04b | |
| JE | `JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP` | CHK-026, CHK-100; JET-04a; POL-204 | |
| JE | `JE-CHK-130-S8-CONTRACT-COSTS-EX2-AMORTISATION` | CHK-130; JET-09a, 09a′, 09b; CONTRACT_COST_CLEARING | |
| JE | `JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL` | CHK-131; JET-09c, 09d; §6.2 #10 | ASC606, IFRS15 |
| JE | `JE-CHK-131-S8-EXPEDIENT-ONE-YEAR-COMMISSION-EXPENSED` | CHK-131 expedient case; POL-140 | |
| JE | `JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE` | CHK-132; JET-12 | |
| JE | `JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION` | CHK-136; JET-11b | |
| JE | `JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA` | CHK-138; JET-04c; RECEIVABLE_CONTRA | |
| LATE | `LATE-CHK-090-GOLDEN-CONTRACT1-DELIVERY-AFTER-JANUARY-LOCK` | CHK-090; ALG-09; origin_period | |
| LATE | `LATE-CHK-091-TC-JE-11-EVENTS-RECORDED-OUT-OF-ORDER` | CHK-091; legacy TC-JE-11 | |
| LATE | `LATE-POL-181-FX-LATE-DELIVERY-AT-EFFECTIVE-DATE-RATES` | POL-181; ALG-09 step 5 | |
| POS | `POS-CHK-010-UNBILLED-RECEIVABLE-AND-CONTRACT-ASSET-SPLIT` | CHK-010; ALG-02, ALG-03 | |
| POS | `POS-CHK-011-GT06-CONTRACT2-SSP-DELIVERED-RECLASS` | CHK-011; GT-02, GT-05, GT-06; CUMULATIVE_SSP_DELIVERED | |
| POS | `POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT` (P) | CHK-012; S9-PRESENTATION | |
| POS | `POS-CHK-013-EXAMPLE-39-CONDITIONAL-RIGHT-ENGINE-BILLING` | CHK-013 | |
| POS | `POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE` | CHK-014 | |
| RND | `RND-CHK-001-USD-EQUAL-SSP-THIRDS` | CHK-001 | |
| RND | `RND-CHK-002-CHK-007-GT01-CONTRACT1` | CHK-002 (Contract 1), CHK-007; GT-01 | |
| RND | `RND-CHK-003A-JPY-EQUAL-SSP-THIRDS` | CHK-003a | |
| RND | `RND-CHK-003B-BHD-WEIGHTS-ONE-TWO` | CHK-003b | |
| RND | `RND-CHK-003C-USD-NEGATIVE-CREDIT-MEMO-APPORTIONMENT` | CHK-003c | |
| RND | `RND-CHK-003D-TIE-BROKEN-BY-LARGER-WEIGHT` | CHK-003d | |
| RND | `RND-CHK-004-CHK-006-S2-EX11-CASEA-OWNPRICES` | CHK-004; CHK-006 row S2-EX11 | |
| RND | `RND-CHK-005-USD-100-OVER-THREE-MONTHS` | CHK-005 | |
| RND | `RND-CHK-006-S2-WARRANTY-OWN-EXTENDED-WARRANTY` | CHK-006 row S2-WARRANTY-OWN | |
| RND | `RND-CHK-006-S5-EX63-OWNSSP-CUSTODY` | CHK-006 row S5-EX63-OWNSSP | |
| RND | `RND-CHK-006-S12-FRANCHISOR-OWN-LICENCE-TEN-YEARS` | CHK-006 row S12-FRANCHISOR-OWN | |
| RND | `RND-CHK-006-S5-UPFRONTFEE-OWN-OPTION-B-PATTERN` | CHK-006 row S5-UPFRONTFEE-OWN | |
| RND | `RND-CHK-006-S6-COMBINED-MOD-OWN-SUPPORT-PATTERN` | CHK-006 row S6-COMBINED-MOD-OWN | |
| RND | `RND-CHK-006-S6-EX5-CASEB-UNITS-PATTERN` | CHK-006 row S6-EX5-CASEB | |
| RND | `RND-CHK-140-DAILY-365-DAY-TERM` | CHK-140 | |
| RND | `RND-CHK-141-MONTHLY-EVEN-PARTIAL-MONTHS` | CHK-141 | |
| RND | `RND-CHK-142-MID-MONTH-DAY-15-RULE` | CHK-142 | |
| RND | `RND-CHK-143-MONTHLY-EVEN-WHOLE-AND-PARTIAL-TERMS` | CHK-143 | |
| RND | `RND-CHK-144-MID-MONTH-LATE-START-EARLY-END` | CHK-144 | |
| RND | `RND-CHK-145-MID-MONTH-EDGE-CASES` | CHK-145 | |

## 3. Coverage mapping

### 3.1 Gaps closed

| Gap | Keys | Status |
|---|---|---|
| M-RA-02 FX answer keys (layers at historical rates, asset remeasurement, IFRIC 22 dates vs the US layer flag), C-11 | FX-CHK-080, FX-CHK-081, FX-CHK-082, FX-CHK-083, FX-POL-160, FX-POL-161, FX-JPY, FX-BHD, LATE-POL-181, ENT-CROSS-CURRENCY | Closed on the corpus side |
| M-RA-03 multi-entity worked example (contracting vs performing entity, intercompany pairs, entity-balanced JEs) | ENT-CHK-070 (both options), ENT-CHK-071, ENT-PER-ENTITY-NETTING, ENT-CROSS-CURRENCY | Closed on the corpus side |
| C-06 JPY and BHD minor units | RND-CHK-003A, RND-CHK-003B, FX-JPY, FX-BHD | Closed |
| C-07 cumulative rounding re-baseline | RND-CHK-004, RND-CHK-006 (six rows), DISC-CHK-006, JE-CHK-130 | Closed, with discrepancy D-AK-02 |
| C-14 delta posting | DLT-CHK-020-CHK-022, DLT-NATIVE | Closed |
| `AK-FAM:fx`, `AK-FAM:multi-entity` hints (REQ-FX-002, -004, -007, REQ-BIL-012, REQ-ENT-001 to -004) | Tag `fx` on 10 keys; tag `multi-entity` on 5 keys | Covered. REQ-FX-007 (FX movement line in rollforwards) has no report cell yet (OQ-AK-11) |

### 3.2 List C: POLICIES CHK ids in scope (03 §12.3)

| List entry | CHK | Keys | Notes |
|---|---|---|---|
| COV-C-01 | CHK-001 | RND-CHK-001 | |
| COV-C-01 | CHK-002 | RND-CHK-002-CHK-007 (Contract 1); POS-CHK-011 asserts Contract 2 | Contract 4 row not asserted here: parity VC-row import belongs to the PAR suite (GT-03) |
| COV-C-01 | CHK-003a to CHK-003d | RND-CHK-003A, -003B, -003C, -003D | Ids upper case (D-AK-01) |
| COV-C-01 | CHK-004, CHK-005 | RND-CHK-004, RND-CHK-005 | |
| COV-C-01 | CHK-006 | RND-CHK-004 (S2-EX11), RND-CHK-006 ×6, DISC-CHK-006 (S10), JE-CHK-130 (S8 ex2) | All nine rows covered; three rows differ from POLICIES (D-AK-02) |
| COV-C-01 | CHK-007 | RND-CHK-002-CHK-007 | |
| COV-C-02 | CHK-010, CHK-011, CHK-012 | POS-CHK-010, POS-CHK-011, POS-CHK-012 | |
| COV-C-03 | CHK-020, CHK-022 | DLT-CHK-020-CHK-022 | CHK-022 is asserted by the GROSS journal runs and the ASC606 subledger |
| COV-C-03 | CHK-021, CHK-023, CHK-024, CHK-025, CHK-026 | JE-CHK-021, JE-CHK-023, JE-CHK-024 (A, B), JE-CHK-025, JE-CHK-026-CHK-100 | |
| COV-C-03 | CHK-130, CHK-131, CHK-132, CHK-136, CHK-138 | JE-CHK-130, JE-CHK-131 (impairment, expedient), JE-CHK-132, JE-CHK-136, JE-CHK-138 | CHK-136 values differ (D-AK-05) |
| COV-C-03 | CHK-133 | none | No input representation for a promised payment to a customer (OQ-AK-08) |
| COV-C-03 | CHK-134 | none | No input for the SKU assurance cost rate (OQ-AK-06) |
| COV-C-03 | CHK-135 | none | No input for noncash units and fair value; the receipt line has no trigger (POLICIES OQ-13; OQ-AK-07) |
| COV-C-03 | CHK-137 | none | No billing-plan input for the 60 instalments, so the cash selling price cannot be derived (OQ-AK-09); see also D-AK-04 |
| COV-C-04 | CHK-013, CHK-014 | POS-CHK-013, POS-CHK-014 | |
| COV-C-08 | CHK-070, CHK-071 | ENT-CHK-070 ×2, ENT-CHK-071 | |
| COV-C-09 | CHK-080 to CHK-083 | FX-CHK-080, -081, -082, -083 | |
| COV-C-10 | CHK-090, CHK-091 | LATE-CHK-090, LATE-CHK-091 | |
| COV-C-11 | CHK-100, CHK-101 | JE-CHK-026-CHK-100, DISC-CHK-101 | |
| COV-C-12 | CHK-140 to CHK-145 | RND-CHK-140 to RND-CHK-145 | The mid-period f(d) values of CHK-140 to CHK-142 are not asserted: an obligation version's progress is as of its latest included event, not `as_of`, so they stay unit tests (DG-ENG-11) |

After this slice and the two other B2 answer-key slices, the CHK ids no key id contains are CHK-027, CHK-028, CHK-031 to CHK-035, CHK-042, CHK-043, CHK-050 to CHK-054, CHK-061, CHK-110 to CHK-113, CHK-115 to CHK-117, CHK-120, CHK-121 (outside this scope) and CHK-133, CHK-134, CHK-135, CHK-137 (this scope, blocked). `make answer-keys` reports them under "Corpus gaps (supervisor)" (DG-AK-33).

### 3.3 List B: research 04 topics touched

| List entry | Research 04 key | Keys of this slice |
|---|---|---|
| COV-B-42 §9 presentation | S9-PRESENTATION | POS-CHK-012, POS-CHK-013, JE-CHK-024 ×2 |
| COV-B-43 §10 disclosures | S10-DISCLOSURES | DISC-CHK-006, DISC-S10-REPORTS, DISC-S10-RPO-EX42, DISC-CHK-101, JE-CHK-026-CHK-100 |
| COV-B-46 §13 IFRS switch list | none (families contains IFRS) | FX-CHK-080, FX-CHK-082, FX-POL-160, IFRS-SW01, IFRS-SW04, IFRS-SW11, JE-CHK-131 |
| Incidental (posting views) | S1-EX1-CASEB-C, S1-EX2, S2-EX11-CASEA-OWNPRICES, S2-WARRANTY-OWN, S3-EX21-EXTENDED, S3-EX23, S3-EX24, S3-EX29, S3-SALESTAX-OWN, S5-PROGRESS-VARIANTS, S5-EX63-OWNSSP, S5-UPFRONTFEE-OWN, S6-COMBINED-MOD-OWN, S6-EX5-CASEB, S7-LOSS-OWN, S8-CONTRACT-COSTS, S12-FRANCHISOR-OWN | Keys listed in section 2. The topic owners' keys remain the primary list B satisfiers |

List A (research 05 §26 scenarios) is outside this slice; no key here claims a research 05 id.

### 3.4 POLICIES §6.2 IFRS 15 switch list

| # | Switch | Keys | Not covered: reason and recommendation |
|---|---|---|---|
| 1 | Collectibility threshold (POL-011) | IFRS-SW01 | |
| 2 | Step 1 event (c) (POL-012) | none | The 25-7(c) fact (stopped transferring, nothing more to transfer) has no event or payload field. Recommend `CONTRACT_TERMINATED` with `termination_kind` FULL as the trigger (OQ-AK-13) |
| 3 | Immaterial promises (POL-020) | none | The parameterised option value (`APPLY_RELIEF` with `immaterial_threshold_pct`) has no documented value shape in `policies` (OQ-AK-16) |
| 4 | Shipping and handling (POL-021) | IFRS-SW04 | |
| 5 | Sales taxes (POL-045) | none | `BILLING_RECORDED` carries one `tax_amount` with no tax type or principal-or-agent attribute, so ASSESS_EACH_TAX cannot differ from the US election (OQ-AK-13) |
| 6 | Noncash measurement date (POL-048) | none | No noncash consideration input (OQ-AK-07) |
| 7 | Licence nature (POL-024) | none | The per-book questionnaire conclusion has no input: `judgements` has no book field (OQ-AK-13) |
| 8 | Licence renewals (POL-025) | none | No renewal attribute on a line or contract in the key schema (`renewal_of_contract_id` is not in DG §9.5.4) (OQ-AK-14) |
| 9 | Licence in a combined POB (POL-232) | none | Same behaviour in both books; informational |
| 10 | Cost impairment reversal (POL-144) | JE-CHK-131 impairment | |
| 11 | Onerous contracts (POL-150 to POL-152) | IFRS-SW11 | IAS 37.68A cost categories are not separable in inputs; the key uses equal costs [A] |
| 12 | Interim disclosures (POL-203) | none | Pack content, not a computed number |
| 13 | Nonpublic relief (POL-191 to POL-196) | none | Report suppression only; the data are always computed (POLICIES §1.12) |
| 14 | Franchisor expedient (POL-202) | none | No eligible-SKU mapping input (952-606-25-2 list) (OQ-AK-14). RND-CHK-006-S12 books the expedient's POB outcome directly |
| 15, 16 | Transition and effective date (POL-218) | none | ONB family; informational |
| 17 | ASU 2016-20 exemptions (POL-199, POL-200) | none | Recommend an IFRS15 variant of DISC-S10-RPO-EX42 once OQ-AK-11 fixes the report cell keys |
| 18 | Repurchase lease outcome (POL-233, POL-231) | none | Routed out; ONB family |
| extra | Business combinations (POL-215) | none | ONB family (PT-11, CHK-121) |
| extra | FX transaction date for advances (POL-160, POL-163) | FX-POL-160, FX-CHK-082, FX-CHK-080 | |

### 3.5 Assignment items

| Item | Keys |
|---|---|
| FX: liability layering at historical rates | FX-CHK-080, FX-POL-161, FX-JPY, FX-BHD |
| FX: contract asset and receivable remeasurement to FX_GAIN_LOSS | FX-CHK-081, FX-CHK-083, LATE-POL-181 |
| FX: IFRIC 22 dates in IFRS15 vs the US layer flag | FX-POL-160, FX-CHK-082, FX-CHK-080 |
| FX: refundable-advance monetary override (D-25a) | FX-CHK-082 |
| FX: JPY or BHD minor-unit case (C-06) | FX-JPY, FX-BHD, RND-CHK-003A, RND-CHK-003B |
| Multi-entity: contracting vs performing entity; due-to and due-from pairs | ENT-CHK-070 ×2, ENT-CHK-071, ENT-CROSS-CURRENCY |
| Multi-entity: per-entity netting | ENT-PER-ENTITY-NETTING, ENT-CHK-071 |
| Multi-entity: entity-balanced JEs | Every ENT subledger block (exact match per entity) plus DG-AK-54 |
| Books: IFRS15 switches | Section 3.4 |
| Books: LEGACY book with DELTA posting (GT-07 style) | DLT-CHK-020-CHK-022, DLT-NATIVE |
| Disclosures: rollforward separating modification catch-ups from estimate changes | DISC-CATCH-UP-BY-CAUSE (obligation `catch_up_modification_cum` and `catch_up_estimate_cum`, prior-period node); DISC-S10-REPORTS (rollforward cells) |
| Disclosures: RPO time bands with practical expedients (POL-201) | DISC-S10-RPO-EX42 (bands [12, 24]; POL-198 exemption) |
| Disclosures: disaggregation | DISC-S10-REPORTS (timing of transfer) |
| Disclosures: contract-cost rollforward | Partial: JE-CHK-130 and JE-CHK-131 assert capitalisation, amortisation, impairment, reversal and carrying by period. No `contract_cost_rollforward` report cells (OQ-AK-11) |
| Disclosures: revenue from prior-period POBs | JE-CHK-026-CHK-100, DISC-CHK-101, DISC-CATCH-UP-BY-CAUSE |
| ALG-01 composition and cumulative rounding | RND keys, JE-CHK-130, FX layer shares |
| ALG-02 netting and reclass; ALG-03 CA vs unbilled receivable | POS keys, ENT-CHK-071, FX-CHK-081, JE-CHK-026-CHK-100, DISC-CHK-101 |
| JET-01 to JET-17 | Table 3.6 |
| POL-090 DAILY, MONTHLY_EVEN, MID_MONTH | RND-CHK-140 to RND-CHK-145 |
| Late events with origin_period (D-19) | LATE-CHK-090, LATE-POL-181 (origin tagging); LATE-CHK-091 (ordering and the LATE_EVENT finding) |

### 3.6 JET templates, counter-entry roles and clearing purposes

| Template or role | Keys of this slice | Other slices or reason |
|---|---|---|
| JET-01 activation (no lines) | Every key (no line at activation) | |
| JET-01b deposit, `UNAPPLIED_CASH` | JE-CHK-021, IFRS-SW01 | |
| JET-02 | Most keys | |
| JET-03 ENGINE invoice with tax; memo-only cancellable invoice | JE-CHK-023, JE-CHK-024 A and B, POS-CHK-013, FX-CHK-083, JE-CHK-138 | Credit memos under ENGINE: not asserted |
| JET-04a, JET-04b | JE-CHK-025, JE-CHK-026-CHK-100, DISC-CHK-101, DISC-CATCH-UP-BY-CAUSE | |
| JET-04c `RECEIVABLE_CONTRA` | JE-CHK-138 | |
| JET-05a | DISC-CATCH-UP-BY-CAUSE (price-change 25-13(b)) | JET-05b and 05c: MOD family (CHK-028) |
| JET-06 and reversal | POS keys, ENT-CHK-071, FX-CHK-081, LATE keys, DLT-CHK-020-CHK-022 | |
| JET-07c `COST_OF_REVENUE`, JET-07d `INVENTORY` | none | RET slice: `RET-CHK-029-S3-EX22`, `RET-CHK-060-S3-EX22-REVISED` |
| JET-08 | none | MR family (CHK-051) |
| JET-09a, 09a′ `CONTRACT_COST_CLEARING`, 09b, 09c, 09d | JE-CHK-130, JE-CHK-131 ×2 | JET-09e: termination slices (FS-09) |
| JET-10a, 10a′, 10b | FX-CHK-081, FX-CHK-083, FX-CHK-082, LATE-POL-181 | |
| JET-11a | none | CHK-137 blocked (OQ-AK-09) |
| JET-11b | JE-CHK-136 | |
| JET-12 | JE-CHK-132, IFRS-SW11 | |
| JET-13 | ENT keys | |
| JET-14 | none | CHK-133 blocked (OQ-AK-08); `EQUITY` purpose blocked by POLICIES OQ-14 |
| JET-15 | DLT keys | |
| JET-16 | none | CHK-134 blocked (OQ-AK-06); claim release has no trigger (POLICIES OQ-13) |
| JET-17 `INVESTMENTS` | none | CHK-135 blocked (OQ-AK-07; POLICIES OQ-13) |
| `AP_SUPPLIER` | none | POB slices (agent keys) |
| `BILLING` purpose | none | No 1.0 template emits it (POLICIES table 0.8-A) |

## 4. Input conventions adopted in the keys

These conventions fill silences of the schema. Each is stated in the affected key summaries and raised in section 8 where a ruling is needed.

| # | Convention | Keys |
|---|---|---|
| C-01 | An observable SSP `point_value` is per unit; extended SSP = point × line quantity (T-REF-31 note "per unit") | All native keys |
| C-02 | `billing.posting` ERP: invoices count in the position on `issue_date` (POL-123 ERP_POSTED_INVOICES); unreferenced invoices and credit memos are attributed per document by ALG-01 over posted allocations | All ERP keys; RND-CHK-003C |
| C-03 | ENGINE: `amount` excludes `tax_amount`; AR = amount + tax; cancellable invoices become unconditional on the receipt that applies them; the engine never reduces AR for cash (ERP cash application) | JE-CHK-023, JE-CHK-024 |
| C-04 | POB class `balance.right_to_consideration` is set explicitly by an obligation-level override wherever a debit position arises, except RIGHT_TO_INVOICE (table 2.4-A default UNCONDITIONAL) | POS, ENT, FX, JE, DISC keys |
| C-05 | Subledger `match: exact` aggregates net per (role, clearing purpose, account for `role_account`, obligation for `role_account_obligation`, origin period, counterparty); side from the functional sign when functional amounts are present; FX-only lines carry `dr`/`cr` "0.00" with the functional amount | All subledger blocks |
| C-06 | Time-elapsed revenue of a period is released before same-day events on the period's last day; event-driven items follow ENG-06 order, including within a day | FX-CHK-081, JE-CHK-025 |
| C-07 | Price-reducing VC elements (REBATE, IMPLICIT_PRICE_CONCESSION and the like) store the reduction as a positive magnitude in `constrained_amount`; JET-04b targets min(reduction, billed) for refund-settled types | JE-CHK-025, DISC-CHK-101 |
| C-08 | A contract cost asset amortises by POL-143 STRAIGHT_LINE over the related obligation's term under the tenant POL-090 convention; after an impairment or reversal the carrying amount amortises over the remaining periods with cumulative rounding restarted | JE-CHK-130, JE-CHK-131 |
| C-09 | Remaining direct costs = latest EAC `expected_total_amount` minus PROGRESS_INPUT costs to date; no EAC → 0 | JE-CHK-131, JE-CHK-132, IFRS-SW11 |
| C-10 | `sfc.discount_rate_basis` override value `{basis, annual_rate}` (05 EMOD-18); monthly rate annual_rate ÷ 12; cumulative interest round(P × ((1 + r)^m − 1)) | JE-CHK-136 |
| C-11 | LATE_EVENT findings: one row per late event, with `obligation_key` when the payload has one | LATE keys |
| C-12 | ALG-09: event-driven differences carry `origin_period_key`; remeasurement differences land untagged in the first open period; locked reclasses are not re-reversed | LATE-CHK-090, LATE-POL-181 |
| C-13 | Golden world codes: entities `ME1`, `ME2` (names "Mock Entity 1/2"), products `HARDWARE-1` and so on, contracts `CONTRACT-1`, `CONTRACT-2`, obligation keys verbatim ("POB #1") | RND-CHK-002-CHK-007, POS-CHK-011, LATE keys, DLT-CHK-020-CHK-022 |
| C-14 | Report cells (platform runner): row_key = entity code, contract external_id, `TOTAL` or `timing:<satisfaction_pattern>`; column keys are measure names (section 8, OQ-AK-11) | DISC-S10-REPORTS, DISC-S10-RPO-EX42 |

## 5. Agreements with published figures

`verify.py` compares 353 published figures; 334 agree and 19 differ (section 6). Agreement is exact for CHK-001, CHK-002 (Contract 1 and Contract 2 posted amounts and 4 dp exact quotas), CHK-003a to CHK-003d, CHK-004, CHK-005, CHK-006 rows S2-EX11, S5-UPFRONTFEE-OWN, S6-COMBINED-MOD-OWN, S6-EX5-CASEB, S8 ex2 and S10, CHK-007, CHK-010 to CHK-014, CHK-020 to CHK-026, CHK-070, CHK-071, CHK-080 to CHK-083, CHK-090, CHK-091, CHK-100, CHK-101, CHK-130 to CHK-132, CHK-138, CHK-140 to CHK-145, research 04 rpo_ex42, and PRD WLD-X-14 (58,285.71 / 9,714.29; September schedule 4,790.61; pair 4,790.61).

## 6. Discrepancies

| Id | Where | Finding | Judgement |
|---|---|---|---|
| D-AK-01 | DG-AK-04 vs DG-AK-32 | The id pattern allows upper case only, but CHK-003a to CHK-003d contain lower case, so "CHK ids appear in `id`" cannot hold verbatim | Keys use `CHK-003A` and so on. The loader's containment check must be case-insensitive (OQ-AK-01) |
| D-AK-02 | POLICIES CHK-006 rows S2-WARRANTY-OWN, S5-EX63-OWNSSP, S12-FRANCHISOR-OWN | The published patterns equal round(A × f_t) with A the posted allocation. D-11a and ALG-01 §2.1.3 (and CHK-007) require round(X × f_t) | The keys follow D-11a. Correct values: warranty 79.55 in months 13, 15, 17, 19, 21, 23, 24 and 79.54 in months 14, 16, 18, 20, 22; custody 9,708.74 / 9,708.74 / 9,708.73; licence 3,636.37 in years 2, 5, 7, 10 and 3,636.36 otherwise (licence_year10 3,636.37). The other two B2 slices (POB-S2-WARRANTY-OWN, REC-S5-EX63-OWNSSP, POB-S12-FRANCHISOR-OWN) agree with these keys. POLICIES CHK-006 should be re-baselined (OQ-AK-02) |
| D-AK-03 | Research 04 S2-EX11 (month 24 1,458.41), S2-WARRANTY-OWN (month 24 79.50), S10-DISCLOSURES (122,499.96 / 17,500.04) | Plugged last-period figures | Expected re-baselines under D-11 (C-07). No action beyond CHK-006 |
| D-AK-04 | POLICIES ALG-02 and CHK-137 vs 05 EMOD-18 "Position" and REQ-BIL-007 | ALG-02 counts every CONTRACT_LIABILITY line, including JET-11, so CHK-137's NP is −837,959.00 (the financed receivable). EMOD-18 says the position excludes interest lines and REQ-BIL-007 excludes "financing interest", which would give −829,475.53 | POLICIES is right: the unbilled receivable of a deferred-payment sale equals the present value of the remaining instalments. Amend EMOD-18 and REQ-BIL-007 to exclude financing interest only from netting against unrelated balances, not from NP (OQ-AK-04). JE-CHK-136 follows ALG-02 |
| D-AK-05 | POLICIES CHK-136 and research 04 S3-EX29 | Annual compounding (240.00, 254.40, 4,494.40) against the monthly schedule of EMOD-18. CHK-137 month-1 interest 8,483.47 is 12% ÷ 12, so the two CHK rows use different conventions | The key uses annual_rate ÷ 12: 246.71, 261.93, 4,508.64. The topics slice key SFC-S3-EX29 uses the same convention and totals. Re-baseline CHK-136 or add a compounding field to the override value (OQ-AK-05) |
| D-AK-06 | ALG-08, RCP-08 | Order of period-end time-driven release against same-day billing is unspecified; CHK-081 needs release first (otherwise March revenue would be USD 1,160.00 from a new liability layer) | Release first (C-06; OQ-AK-12) |
| D-AK-07 | CHK-081 vs table 2.4-A | CHK-081 presents a contract asset for fixed-fee arrears billing; table 2.4-A classifies a completed billing period under a noncancellable contract as UNCONDITIONAL | The key sets CONDITIONAL with rationale (cancellable before quarter end). Recommend CHK-081 state the class |
| D-AK-08 | POLICIES JET-14, JET-16, JET-17, JET-11a and CHK-133, CHK-134, CHK-135, CHK-137 | Inputs missing from `erev-answer-key/1` and 04 (promised payment to a customer; SKU assurance cost rate; noncash units and fair value; billing plan); JET-16 claim release and JET-17 receipt have no trigger (POLICIES OQ-13) | Not authored; blocked (OQ-AK-06 to OQ-AK-09) |
| D-AK-09 | DG-AK-30 vs the answer-key assignment | `discover` raises on any non-YAML file other than README.md, so `docs/accounting/answer-keys/_coverage/*.md` would fail loading | Exempt `_coverage/` in DG-AK-30 or move coverage files to `docs/reviews/` (OQ-AK-15) |
| D-AK-10 | POL-143 vs CHK-130 | POL-143 STRAIGHT_LINE is "daily (POL-090)"; under DAILY the seven-year commission does not amortise 1,428.57 a year (leap years) | The key sets tenant POL-090 MONTHLY_EVEN. CHK-130 should name the convention |
| D-AK-11 | CHK-131 (years) vs monthly calendars | Annual impairment tests cannot be replicated on a monthly calendar without extra EAC versions; monthly tests are path dependent | The key maps "Year n" to period n [A] |
| D-AK-12 | POL-151 vs schema | No `scope_605_35` contract flag exists in 04 T-CON-01 or DG §9.5.4 | JE-CHK-132 sets `loss.scope` ALL_CONTRACTS_WITH_EAC at book level; IFRS-SW11 relies on the default and IFRS forcing (OQ-AK-10) |
| D-AK-13 | 05 §3.10 trace node names vs CHK-140 to CHK-142 f(d) values | Mid-period progress values are not observable through `obligations` at `as_of` | Left to unit tests (section 3.2) |

## 7. Observations on other B2 answer-key slices

| Observation | Recommendation |
|---|---|
| Duplicate scenarios with distinct ids: RND-CHK-001, RND-CHK-003A/B/D, POS-CHK-010/012/013, REC-CHK-014, VC-CHK-100, VC-CHK-101, COST-S8-CONTRACT-COSTS-*, LOSS-S7-LOSS-OWN, SFC-S3-EX29, TAX-S3-SALESTAX-OWN, POS-S9-PRESENTATION-EX38-*, IFRS-S13-SWITCH-SHIPPING, DISC-S10-DISCLOSURES-ROLLFORWARD-EX21, DISC-S10-DISCLOSURES-RPO-EX42 | No conflict in the figures checked (allocations, CHK-006 patterns, costs ex2 carrying, S10 rollforward, SFC totals). The supervisor may withdraw duplicates after review |
| `cost/COST-S8-CONTRACT-COSTS-IMPAIRMENT.yaml` asserts `cost_asset_carrying: "-85000.00"` in one checkpoint | A carrying amount cannot be negative (04 T-CON-16; labelled balances non-negative). Review that checkpoint |
| `sfc/SFC-S3-EX28-CASEB.yaml` asserts unbilled receivable 846,527.30 and 836,121.57; CHK-137 publishes 837,959.00 after the month-1 instalment | Reconcile with D-AK-04 (whether JET-11a lines enter NP) |

## 8. Open questions for supervisor

| Id | Question | Recommended default |
|---|---|---|
| OQ-AK-01 | DG-AK-32 requires CHK ids to appear in key ids, but DG-AK-04 forbids lower case (CHK-003a to CHK-003d) | Match CHK ids case-insensitively; key ids carry the upper-case form |
| OQ-AK-02 | POLICIES CHK-006 rows S2-WARRANTY-OWN, S5-EX63-OWNSSP and S12-FRANCHISOR-OWN use round(A × f) | Re-baseline them to the D-11a values of D-AK-02; keys already assert them |
| OQ-AK-03 | Attribution of unreferenced invoices and credit memos to obligations (ALG-02 step 3): per document or over cumulative billing | Per document, sign applied after apportioning |T| (RND-CHK-003C) |
| OQ-AK-04 | Does NP include JET-11 financing interest (ALG-02, CHK-137) or exclude it (05 EMOD-18, REQ-BIL-007)? | Include; amend EMOD-18 and REQ-BIL-007 |
| OQ-AK-05 | Periodic rate of the monthly effective-interest schedule | annual_rate ÷ 12 with cumulative rounding of exact cumulative interest; re-baseline CHK-136 to 246.71 / 261.93 / 4,508.64 |
| OQ-AK-06 | Input for the POL-022 SKU assurance cost rate (JET-16, CHK-134) | Add registry key `warranty.assurance_cost_per_unit` (levels P, O; money) or a product field; author CHK-134 afterwards |
| OQ-AK-07 | Inputs for noncash consideration (units, fair value per unit at the POL-048 date) and the receipt trigger (JET-17, CHK-135; POLICIES OQ-13) | Line-level `noncash_units` and an estimate kind `NONCASH_FAIR_VALUE`; noncash form of PAYMENT_RECEIVED as POLICIES OQ-13 recommends |
| OQ-AK-08 | Input for consideration payable to a customer (JET-14, CHK-133) | Contract-level `consideration_payable: [{reference, amount, promised_date, release_basis, expected_purchases_element}]` in API-S-ContractCreate and DG §9.5.4 |
| OQ-AK-09 | Billing-plan input for deferred-payment financing (CHK-137) | Contract-level `billing_plan: [{due_date, amount}]` (REQ-BIL-009) in DG §9.5.4 |
| OQ-AK-10 | No `scope_605_35` flag in 04 or the key schema (POL-151) | Add `scope_605_35` (boolean) to T-CON-01 and API-S-ContractCreate |
| OQ-AK-11 | Report cell keys for `rpo`, `contract_balance_rollforward`, `revenue_from_opening_liability`, `disaggregation` and `contract_cost_rollforward` are undefined | Adopt C-14: rows by entity code, contract external_id, `TOTAL` or `<dimension>:<value>`; columns `within_12_months`, `months_13_to_24`, `after_24_months`, `total`; `opening_contract_liability`, `billings`, `revenue_from_opening_liability`, `revenue_from_period_billings`, `fx`, `closing_contract_liability`; `revenue` |
| OQ-AK-12 | Same-day order of period-end release and billing (ALG-08) | Time-driven release first, then events in ENG-06 order |
| OQ-AK-13 | Inputs for per-book judgements (licence nature), 25-7(c) and tax types | Add `book` to `judgements` and to COLLECTIBILITY-style payloads; tax lines `[{tax_type, amount, principal_or_agent}]` on BILLING_RECORDED |
| OQ-AK-14 | Inputs for licence renewals (POL-025) and franchisor-eligible SKUs (POL-202) | `renewal_of` contract handle in DG §9.5.4; product attribute `franchisor_preopening_service` |
| OQ-AK-15 | DG-AK-30 rejects `_coverage/*.md` | Exempt `_coverage/` from `discover` |
| OQ-AK-16 | Value shapes of parameterised or list-valued registry options in `world.policies` (POL-020 threshold, POL-201 bands) | Objects `{option, <parameter>}` for parameterised options and string lists for list values, as used in DISC-S10-RPO-EX42 |
