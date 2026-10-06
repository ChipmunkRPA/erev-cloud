# Answer-key coverage: industry scenarios and capability families

| Field | Value |
|---|---|
| Owner | answer-keys-industries (design phase B2) |
| Date | 2026-09-12 |
| Status | 57 keys, all `active`, all passing the independent oracle; review status `pending` (G12) |
| Scope | List A of `docs/03-REQUIREMENTS.md` §12.1 (49 research 05 §26 scenarios of D01, D02, D04, D05, D08, D12), list B COV-B-32 (research 04 §6.1 via GE-02), and the capability families assigned to this role |
| Schema | `erev-answer-key/1`, `docs/dev-guide.md` §9.5 (DG-AK-01 to DG-AK-55) |
| Oracle | `research-harness/answer-keys/answer-keys-industries/` |

> **B3 adjudication (2026-09-12).** `_coverage/ADJUDICATION.md` rules on every discrepancy (D-1 to D-8) and every open question (OQ-AKI-01 to OQ-AKI-21) of this file. Where this file differs, `ADJUDICATION.md` governs. The key count stays 57 and all verify with 0 failures. The changes are:
>
> - **Loss scope.** LOSS-GE-03 carries `scope_605_35: true`; the book policy `loss.scope` workaround is removed (R-SCH-03).
> - **Financing.** SFC-FS-11-CASEB and SFC-CAP carry `compounding: MONTHLY`, and SFC-CAP carries `payment_schedule` (R-SCH-01, R-SCH-02).
> - **Renewal link.** REC-FS-06 names the original contract through `renewal_of` (R-SCH-06).
> - **Franchisor SKU.** POB-JS-05-CASEB marks its pre-opening SKU `is_franchisor_preopening_service` (R-SCH-12).
> - **Policy levels.** RET-BR-03, ROY-JS-08, REC-FS-06 and LOSS-GE-03 now place `returns.model`, `royalty.unreported_sales`, `licence.renewal_start` and `loss.unit` at allowed levels (R-POL-01).
> - **Impairment.** COST-CAP adds the anticipated-renewal term, which is nil, and the carrying-amount floor (R-COST-02).
> - **Build step.** `run_oracle.py build` now calls the shared `research-harness/answer-keys/adjudication.py`.
>
> The statement in section 4 that CHK-133, CHK-134, CHK-136 and CHK-137 are owned elsewhere still holds: they are carried by topics keys.

## 1. Result

- Every list A scenario id has at least one active key whose `derived_from.research05` contains it (49 of 49; checked mechanically).
- Every key asserts labelled balances with the contract asset and the unbilled receivable separated, and exact subledger lines by role and account for its key periods (closes M-RA-07 for these clusters).
- No key id collides with the concurrent corpora (answer-keys-topics, answer-keys-fx-entity-books): 181 files scanned, no duplicate id.
- No key carries a POLICIES CHK id. Where a capability has a research 04 topic key or a POLICIES CHK (owned by answer-keys-topics), the key here is an industry scenario with its own figures.

## 2. Rerun the oracle

```sh
cd ~/dev/erev/research-harness/answer-keys/answer-keys-industries
UV_OFFLINE=1 uv run --no-project --with pyyaml python run_oracle.py build    # regenerate the 57 keys from the scenario inputs
UV_OFFLINE=1 uv run --no-project --with pyyaml python run_oracle.py verify   # reload every YAML file, recompute from the key's inputs, lint, diff
```

How the oracle stays independent:

- `verify` loads each file with a DG-AK-31 loader (only null and bool resolvers; duplicate keys rejected).
- It reads the figures back from the file's `world`, `contracts` and `timeline`: prices, SSPs, dates, events, estimate versions and modifications.
- It recomputes every checkpoint with `fractions.Fraction`, using ALG-01 half-up rounding, largest remainder, cumulative rounding, ALG-11 conventions, ALG-02/ALG-03 netting and the JET templates.
- It compares the result field by field with the checkpoints in the file.
- The only oracle constants are the business terms that the engine never reads (FS-02 tier schedule, BR-02 rebate thresholds, GE-04 CPIF fee formula, royalty and fund rates). The oracle uses them to cross-check the estimate inputs.
- The library self-checks against CHK-001, CHK-003a, CHK-003d, CHK-140, CHK-141 and CHK-143(b).
- `lint.py` checks the DG-AK rules that can be checked offline:
  - id pattern, family directory and file name;
  - top-level fields;
  - REQ and POL ids exist in 03 and POLICIES;
  - `seq` continuity and `after_seq` existence;
  - E-01 roles, no reserved roles, and the `clearing_purpose` rule;
  - exactly one of `dr` and `cr` per line;
  - money places per currency (JPY 0);
  - every exact subledger block balances.

## 3. List A: research 05 §26 scenarios → keys

| Scenario | Key id(s) | Families | Notes |
|---|---|---|---|
| FS-01 | REC-FS-01-SAAS-RAMP-ANNUAL-BILLING | REC, POS | Straight-line ramp; contract asset 50,000.00 at year ends |
| FS-02 | VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE | VC, REC, POS, DISC | PT-01 measurement-period estimate; prior-period revenue trace 25,000.00 |
| FS-03 | MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE; MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE | MOD, REC, POS / MOD, ALC, REC | research 05 §2 figures (net liability 89,100.00) |
| FS-04 | MR-FS-04-EARLY-RENEWAL-PRICE-CAP | MR, ALC, REC, POS | D-21a option SSP 16,000.00; CONTINUATION |
| FS-05 | SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL | SSP, ALC, REC, POB | Residual 304,000.00; PCS renewal as separate contract |
| FS-06 | REC-FS-06-TERM-LICENCE-RENEWAL-START-GATE | REC, POB, POS | POL-025 gate |
| FS-07 | REC-FS-07-FIXED-FEE-EAC-HOURS-REVISION | REC, VC, POS | Catch-up −2,307.69; contract asset 30,000.00 / 23,076.92 |
| FS-08 | REC-FS-08-TM-RIGHT-TO-INVOICE | REC, POS | Unbilled receivable 36,000.00 |
| FS-09 | MOD-FS-09-CANCELLATION-REFUND-COMMISSION | MOD, COST, RET, POS | JET-04b refund liability; JET-09e 8,400.00 |
| FS-10 | MOD-FS-10-CLOUD-CONVERSION-CREDIT | MOD, ALC, REC | 25-13(a) pool 100,000.00 |
| FS-11 | SFC-FS-11-CASEA-UPFRONT-NO-FINANCING; SFC-FS-11-CASEB-UPFRONT-ADVANCE-ACCRETION | SFC, REC / SFC, REC, POS | Case B TP 295,701.23; interest month 1 1,350.00 |
| BR-01 | POB-BR-01-ROBOTS-PLATFORM-EXTENDED-WARRANTY | POB, ALC, REC | Discrepancy D-1 |
| BR-02 | VC-BR-02-DISTRIBUTOR-RETRO-REBATE | VC, RET, POS | research 05 §8 figures reproduced; adaptation D-4 |
| BR-03 | RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION | RET, VC, POS | JET-07c / 07d; uses estimate `parameters` (OQ-AKI-01) |
| BR-04 | REC-BR-04-BILL-AND-HOLD-CUSTODIAL | REC, ALC, POB | Custody 11,278.20 by largest remainder |
| BR-05 | REC-BR-05-CONSIGNMENT-SELL-THROUGH | REC, POS | JPY (exponent 0); unbilled receivable |
| BR-06 | ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT | ALC, ONB, REC | Routing assertion per 03 §12 rule 1 |
| BR-07 | CPC-BR-07-CASEA-MDF-DISTINCT-SERVICE-FAIR-VALUE; CPC-BR-07-CASEB-MDF-EXCESS-OVER-FAIR-VALUE | CPC, POB | JET-14 in Case B; input encoding OQ-AKI-04 |
| BR-08 | REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST | REC, MOD, POS | 25-13(b) catch-up +2,941.18 |
| GE-01 | REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN | REC, MOD, POS | research 05 §6 figures reproduced exactly |
| GE-02 | MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM | MOD, VC, REC, POS | Also list B COV-B-32 (research 04 §6.1) |
| GE-03 | LOSS-GE-03-LOSS-CONTRACT-PROVISION | LOSS, REC, POS | Provision 100,000.00 → 50,000.00 → 0.00; OQ-AKI-03 |
| GE-04 | VC-GE-04-CPIF-EAC-REVISIONS | VC, REC, POS | research 05 §7 figures reproduced exactly |
| GE-05 | VC-GE-05-AWARD-FEE-POOL-CONSTRAINT | VC, REC, POS | Constraint to 0.00 then award history |
| GE-06 | DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO | DISC, STP1, REC, POS | RPO 700,000.00 and 1,191,666.67 |
| GE-07 | POS-GE-07-RETAINAGE-PRESENTATION | POS, REC | Retainage as contract asset |
| GE-08 | MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE | MOD, REC, ALC | Scope reduction under 25-13(a); the partial termination by units is a `CONTRACT_AMENDED` kind `QUANTITY_CHANGE` with the post-modification terms line (D-93 (2)) |
| JS-01 | MR-JS-01-POS-PORTFOLIO-POINTS-REDEMPTION | MR, BRK, VC, REC | Discrepancy D-3 |
| JS-02 | BRK-JS-02-GIFT-CARDS-BREAKAGE-ESCHEAT | BRK, REC | research 05 §9 gift cards reproduced; escheat variant |
| JS-03 | RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET | RET, REC, POS | Return re-estimate; OQ-AKI-01 |
| JS-04 | REC-JS-04-PAID-MEMBERSHIP-DAILY | REC, POS | DAILY convention |
| JS-05 | POB-JS-05-CASEA-FRANCHISE-PUBLIC; POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT | POB, ROY, REC | Case A reproduces 131,000.00; Case B discrepancy D-2 |
| JS-06 | MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION | MOD, POB, REC, ALC | Prospective schedule revision (PRD §2.10 mandatory scenario) |
| JS-07 | ROY-JS-07-ADVERTISING-FUND-GROSS | ROY, POB, REC | Principal, no supplier clearing |
| JS-08 | ROY-JS-08-ROYALTIES-LAGGING-REPORTS | ROY, VC, POS, LATE | Accrual and true-up +900.00 / −300.00; OQ-AKI-01 |
| RB-01 | VC-RB-01-SELF-PAY-IMPLICIT-CONCESSION-CREDIT-LOSS | VC, JE, POS, STP1 | ENGINE mode, RECEIVABLE_CONTRA (JET-04c); research 05 §12 net AR 360,000.00 |
| RB-02 | VC-RB-02-COMMERCIAL-PAYOR-CONTRACTUAL-QUALITY-BONUS | VC, POS, JE | Explicit adjustments; constrained bonus |
| RB-03 | REC-RB-03-DRG-IN-HOUSE-PATIENT-MONTH-END | REC, POS, JE | research 05 §12 9,000.00 / 6,000.00 |
| RB-04 | VC-RB-04-COST-REPORT-SETTLEMENT | VC, RET, JE, POS | Refund liability to settlement |
| RB-05 | REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT | REC, MOD, VC, JE | 32-40 period allocation; prospective amendment |
| RB-06 | ONB-RB-06-RELIEF-GRANT-ROUTED-OUT | ONB, STP1 | No revenue or journal lines; OQ-AKI-11 |
| WM-01 | POB-WM-01-THIRD-PARTY-COMMISSIONS-NET | POB, REC, JE | Agent JET-02 with AP_SUPPLIER clearing; OQ-AKI-05 |
| WM-02 | POB-WM-02-FIRST-PARTY-INVENTORY-GROSS | POB, REC, POS | EUR; in-transit liability |
| WM-03 | CPC-WM-03-BUYER-PROMOTIONS-NEGATIVE-REVENUE-TEST | CPC, POB | JET-14; OQ-AKI-04 |
| WM-04 | RET-WM-04-REFUNDS-AND-CHARGEBACKS | RET, VC, POS | Refund liability re-estimate |
| WM-05 | POB-WM-05-HOTEL-MERCHANT-VERSUS-AGENCY | POB, REC, POS | Merchant and agency models |
| WM-06 | BRK-WM-06-PLATFORM-CREDITS-BREAKAGE-RE-ESTIMATE | BRK, REC, VC | GBP; breakage catch-up |
| WM-07 | MR-WM-07-PARTNER-AIRLINE-TICKETS-WITH-MILES | MR, BRK, POB, REC | research 05 §18 figures reproduced exactly |
| WM-08 | TAX-WM-08-TAXES-AND-FEES-GROSS-OR-NET | TAX, JE, POB | ENGINE mode SALES_TAX_PAYABLE; OQ-AKI-10 |

## 4. Capability families → keys

| Capability family (task list) | Keys | Research 04 topic key or POLICIES CHK not duplicated (owner: answer-keys-topics) |
|---|---|---|
| Usage and minimum commitments with true-up | VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE; VC-CAP-USAGE-QUARTERLY-MINIMUM-TRUEUP | CHK-110 (PT-01) |
| Credits rollover | BRK-CAP-CREDITS-ROLLOVER-RENEWAL | CHK-111 (PT-02) |
| Cost-to-cost with EAC changes and uninstalled materials | REC-GE-01, MOD-GE-02, VC-GE-04, VC-GE-05, POS-GE-07, REC-BR-08, LOSS-GE-03 | S5-EX19, S5-PROGRESS-VARIANTS, CHK-115 |
| Loss provisions | LOSS-GE-03-LOSS-CONTRACT-PROVISION | S7-LOSS-OWN (CHK-132) |
| Contract costs with expected renewals and impairment | MOD-FS-09-CANCELLATION-REFUND-COMMISSION (expected renewals, acceleration); COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT (impairment 20,000.00) | S8-CONTRACT-COSTS (CHK-130, CHK-131), CHK-112 |
| Breakage | BRK-JS-02, BRK-WM-06, MR-JS-01, MR-WM-07, BRK-CAP-CREDITS-ROLLOVER-RENEWAL | S5-BREAKAGE-OWN, CHK-053 |
| Royalties with late reports | ROY-JS-08-ROYALTIES-LAGGING-REPORTS; ROY-JS-07, POB-JS-05 (statements) | S5-EX60 |
| Bill-and-hold | REC-BR-04-BILL-AND-HOLD-CUSTODIAL | S5-EX63-OWNSSP |
| Principal versus agent | POB-WM-01, POB-WM-05, POB-WM-02, ROY-JS-07, MR-WM-07 | S2-EX45-AGENT |
| Implicit price concessions, `ENGINE` billing, RECEIVABLE_CONTRA | VC-RB-01-SELF-PAY-IMPLICIT-CONCESSION-CREDIT-LOSS | S1-EX2 (CHK-138) |
| Consideration payable to a customer | CPC-BR-07-CASEB-MDF-EXCESS-OVER-FAIR-VALUE; CPC-BR-07-CASEA; CPC-WM-03 | S3-EX32 (CHK-133) |
| Significant financing | SFC-FS-11-CASEB (advance, JET-11b); SFC-FS-11-CASEA (tested, none); SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE (deferred, JET-11a) | S3-EX26, S3-EX28-CASEB, S3-EX29 (CHK-136, CHK-137) |

`AK-FAM` tags supplied (DG-AK-33): `usage` (VC-FS-02, VC-CAP-USAGE), `usage-rollover` (BRK-CAP), `termination` (MOD-FS-09, MOD-GE-08), `construction` (GE keys, BR-08), `portfolio` (JS-01 to JS-04, RB-01, WM keys), `subscription` (FS keys, JS-04, COST-CAP). The `fx`, `multi-entity` and `business-combination` slugs belong to answer-keys-fx-entity-books.

## 5. Items not covered, with reasons

| Item | Reason |
|---|---|
| POLICIES CHK ids (list C) | Owned by answer-keys-topics; no key here embeds a CHK id |
| JET-16 assurance-warranty accrual in BR-01 | 04 and DG have no product field for the SKU assurance cost rate, so BR-01 sets POL-022 `EXTERNAL` at entity level (OQ-AKI-14). CHK-134 is the topic key |
| PT-02 "not renewed" variant (credits lapse) | No schema route for rights lapsing on a non-option POB without a modification record; the lapse amount (68,571.43) is stated in the BRK-CAP summary only (OQ-AKI-20) |
| IFRS15 variants of loss provisions, cost impairment reversal and tax assessment | `IFRS` family and research 04 §13 belong to other corpora; industry keys here run the ASC606 book only |
| Retainage becoming an unconditional receivable at acceptance | The POB class is static in the schema; GE-07 invoices retainage on the acceptance date (OQ-AKI-19) |
| Credits rolled into a separate renewal contract (REQ-MOD-017 lineage) | The schema cannot express cross-contract lineage of a liability; BRK-CAP extends the same contract (OQ-AKI-20) |
| PRD §2.10 mandatory demo items BR-01 "extended warranty added at a discount", WM-05 "programme amendment", lock and reopen, invalid import files | Demo seeding content, not scenario keys; lock and reopen and imports need `runner: platform` |
| Credit-loss write-off and cash collection in RB-01 | Engine posts neither (POL-125; no cash-application posting); the key asserts that September has no engine lines (OQ-AKI-09) |

## 6. Discrepancies found and judgement

| Id | Source | Research or document value | Oracle value | Judgement |
|---|---|---|---|---|
| D-1 | research 05 §4 (BR-01) | Allocation 82,500 / 27,500 / 8,000; 2026 revenue 96,250; ending CL 21,750 ("combined without changing the allocation") | Relative SSP over the combined group: 82,968.75 / 27,656.25 / 7,375.00; 2026 revenue 96,796.88; CL 21,203.12 | The key is right under the default: combining contracts re-runs allocation (REQ-CON-009), and allocating the whole discount to devices and platform needs the 32-37 exception with evidence (POL-076). Research 05 is background only (D-§0) |
| D-2 | research 05 §13 (JS-05 private) | Services 15,384.62, licence 34,615.38; Year 1 revenue 144,846.15; fee liability 31,153.85 | Three POBs by relative SSP: 16,842.10 / 37,894.74 / 25,263.16; Year 1 revenue 141,894.73; licence liability 34,105.27 | The key is right. Research allocates the fee only between services and licence with equipment at its price, which again needs the 32-37 exception |
| D-3 | research 05 §9 (JS-01) | Points liability after Q1 3,968.25 | 3,968.26 | Revenue is round(X × f) = 3,968.25 and the posted allocation is 7,936.51 (D-11a), so the liability is 3,968.26. Research displays exact balances rounded. The key is right |
| D-4 | research 05 §8 (BR-02) | Thresholds on distributor purchases, with forecasts (21,000) above the shipped 20,000 units | Thresholds on sell-through (> 10,000 at 3%, > 18,000 at 5%) under one noncancellable blanket order | Design adaptation so that the enforceable quantity is fixed. Quarterly revenue and refund liabilities reproduce research exactly |
| D-5 | 05-ARCHITECTURE EMOD-18 vs POLICIES ALG-01 and ALG-02 (FS-11 Case B, SFC-CAP) | EMOD-18 has three conflicting rules: period interest = round(opening × monthly rate) with a cumulative-rounded final period; financing interest balances excluded from the net position; ALG-02 step 3 derives U from revenue relief only, so accreted interest on a deferred payment presents as a contract asset | Keys round the exact cumulative interest (D-11 and D-11a) and keep JET-11 lines in the CONTRACT_LIABILITY control balance (ALG-02; CHK-136, CHK-137). SFC-CAP presents the whole debit as unbilled receivable (445,810.79 at 31 January 2026; 470,952.67 at 31 December 2026) | Judgement: the right to a deferred payment and its accreted interest is unconditional (606-10-45-4). Recommend that ALG-02 counts financing accretion on UNCONDITIONAL POBs in U, and that EMOD-18 adopts cumulative rounding and drops the position exclusion (OQ-AKI-12) |
| D-6 | 05-ARCHITECTURE EMOD-16 vs 340-40-35-3 and 35-4 | Remaining expected consideration = TP of related POBs minus revenue recognised (current contract only) | The COST-CAP key tests impairment inside the initial term after the renewal expectation falls to 12 months (impairment 20,000.00) | Under EMOD-16 as written, an asset amortised over anticipated renewals would be fully impaired at the end of the initial term. 340-40-35-4 includes consideration from anticipated contracts. Recommend that ENGINE_SPEC includes expected renewal consideration (OQ-AKI-13) |
| D-7 | 03 REQ-REC-007 vs POLICIES OQ-15 (GE-01) | REQ says the cost of uninstalled materials posts to COST_OF_REVENUE | The key asserts no COST_OF_REVENUE line: zero-margin revenue only | POLICIES governs accounting behaviour (D-§0). The key follows OQ-15 until the supervisor rules |
| D-8 | research 05 §2, §3, §6, §7, §12, §13 (Case A), §18, §21 | none | Figures reproduced exactly: FS-03, FS-05, FS-07, FS-08, GE-01, GE-04, RB-01, RB-03, JS-02, JS-05 Case A, WM-07 | No discrepancy |

## 7. Open questions for supervisor

| Id | Question | Recommended default |
|---|---|---|
| OQ-AKI-01 | DG §9.5.4 `estimates[].versions[]` has no `parameters`, but 04 T-CON-13 rev 1.1 requires them for `RETURN_RATE` (k, c_rec, window end) and `ROYALTY_ACCRUAL` (usage period) | Add optional `parameters` to DG §9.5.4 with the 04 schemas. BR-03, JS-03 and JS-08 already use it |
| OQ-AKI-02 | Are subledger `lines` gross or net per grain key? | Net per (role, account, clearing purpose[, obligation]) key. A key whose debits and credits cancel is omitted. `match: exact` with `lines: []` asserts that nothing posted (RB-01 September, RB-06) |
| OQ-AKI-03 | The DG contract has no `scope_605_35` flag (05 EMOD-17) | Add optional contract field `scope_605_35`. Until then GE-03 sets book policy `loss.scope: ALL_CONTRACTS_WITH_EAC` |
| OQ-AKI-04 | No input object carries a promised payment to a customer or the fair value of a distinct service | Adopt the key encoding on an `EXPECTED_PURCHASES` version: `expected_total_amount` = release base; `unconstrained_amount` = total promised payment; `constrained_amount` = the amount that reduces the TP after the 32-26 test. Record this in the 04 T-CON-13 parameter table |
| OQ-AKI-05 | Agent POB: where does the gross amount relieved by JET-02 come from? | Gross relief = billed consideration attributable to delivered units of the agent POB; supplier portion = gross − retained revenue, floored at 0; `gross_amount_memo` = billed gross |
| OQ-AKI-06 | Semantics of `modifications[].lines` and `price_change_amount` | `lines` carry the post-modification terms of each affected line; `price_change_amount` is the signed ΔC; removals use kinds `REMOVE_OBLIGATION` or `TERMINATION`. Where the route is 25-12, keys assert the proposed treatment, the unchanged original contract and entity-level revenue (subset) |
| OQ-AKI-07 | Is SSP `point_value` a unit SSP or an extended SSP? | Unit SSP; the allocation weight = point × line quantity (legacy convention; T-CON-11 `ssp_unit_list_price`, `original_ssp_selected`) |
| OQ-AKI-08 | Progress after a 25-13(a) modification on a time-elapsed or unit POB | C_t = R + round(s × g_t), where g is progress over the remaining term or remaining units with the POB's convention; no catch-up (FS-03B, FS-10, JS-06, GE-08) |
| OQ-AKI-09 | `ENGINE` billing: nothing relieves ACCOUNTS_RECEIVABLE for cash or write-offs | AR = invoices − credit memos in the engine; cash application and write-offs stay ERP postings. RB keys assert AR only before collections |
| OQ-AKI-10 | Does `BILLING_RECORDED.amount` include `tax_amount`? | No: `amount` is net of tax; AR = amount + tax_amount (WM-08) |
| OQ-AKI-11 | A contract whose only line is out of scope, and a single all-VC line with stated price 0.00 | Skip allocation without `TOTAL_SSP_ZERO` when no in-scope POB exists (RB-06). An all-VC line needs a positive SSP point (FS-08, JS-07, JS-08) |
| OQ-AKI-12 | SFC interest rounding, position inclusion and presentation split (D-5) | Round the exact cumulative interest; include JET-11 lines in the control balance; count accretion on UNCONDITIONAL POBs in U |
| OQ-AKI-13 | Impairment with anticipated renewals (D-6) | Include the consideration expected from the renewals already used in the amortisation period, less the related remaining costs |
| OQ-AKI-14 | No SKU assurance cost rate for JET-16 | Add a product field `assurance_cost_rate`; BR-01 stays on `EXTERNAL` until then |
| OQ-AKI-15 | T-REF-23 requires `OVER_TIME` for `REDEMPTION_PATTERN`; which criterion applies to points, gift cards and credits? | `OT_A` (keys use it) |
| OQ-AKI-16 | Which costs count as "loss already recognised through margin to date"? | `COST_INCURRED` progress-input costs to date minus revenue to date (GE-03) |
| OQ-AKI-17 | `contract_type` values | Free text; keys use CONSTRUCTION, PORTFOLIO, GOVERNMENT_CPIF, GOVERNMENT_CPAF, GOVERNMENT_IDIQ_TASK_ORDER and GOVERNMENT_FFP |
| OQ-AKI-18 | Portfolio cohorts | One contract per cohort (REQ-TP-017 estimates at contract level). Cohort processing across contracts is REQ-TP-019 `later` |
| OQ-AKI-19 | The contract asset or receivable class cannot change within a POB (for example retainage at acceptance) | Add billing-plan lines with a class per line to the schema (ALG-03 mixed lines) |
| OQ-AKI-20 | Cross-contract rollover lineage and lapse of rights on non-option POBs | Add a `CONTRACT_TERMINATED` variant for lapse without refund, and a rollover link on the renewal booking |
| OQ-AKI-21 | DG-AK-01 and DG-AK-30 allow only `README.md` besides YAML keys, so `_coverage/*.md` would make `discover` raise `AnswerKeyError` | Amend DG-AK-01 and DG-AK-30: the loader ignores the `_coverage/` directory, which holds non-key coverage notes per answer-key author |
