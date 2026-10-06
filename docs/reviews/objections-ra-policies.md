# Objections to supervisor decisions: ra-policies

| Field | Value |
|---|---|
| Author | Chief technical accountant (design slug `ra-policies`) |
| Date | 2026-09-12 |
| Document affected | `docs/accounting/POLICIES.md` |
| Status | Raised. `docs/accounting/POLICIES.md` follows each decision as written until the supervisor amends it |

## O-1: D-14 lacks cost-of-revenue and clearing roles

**Decision.** D-14 fixes the `account_role` enum.

**Objection.** Several postings that D-22 (returns) and the 1.0 scope (contract costs, uninstalled materials, share-based consideration payable) require have a counter-entry that belongs to another subledger. The enum has no role for it:

| Posting | Economic counter-entry | Role D-14 offers |
|---|---|---|
| Return asset at transfer and on remeasurement (606-10-55-23(c), 55-27) | Cost of revenue | none |
| Return asset derecognised when goods come back | Inventory | none |
| Fulfilment-cost capitalisation (340-40-25-5) | Cost of revenue or the expense where the ERP booked the cost | none |
| Incremental-cost capitalisation (340-40-25-1) | Commission expense or commissions payable | none (`CONTRACT_COST_AMORTIZATION` is the amortisation account) |
| Share-based consideration payable to a customer (606-10-32-25A) | Additional paid-in capital | none |
| Agent billings passed to the supplier (606-10-55-38) | Payable to supplier | none |
| Receipts while a contract fails Step 1 (606-10-25-8) | Unapplied cash | none |

**Interim compliance.** `docs/accounting/POLICIES.md` §0.8 defines `BILLING_CLEARING` as the counter-entry role for amounts owned by another subledger. Because the D-14 mapping key is (role × entity × optional product or revenue category), all of these counter-entries resolve to one clearing account per entity unless the tenant maps by category. The tenant's ERP must then reclassify, which weakens traceability.

**Proposed amendment (D-14a).**

1. Add `COST_OF_REVENUE` (return-asset counter-entry, fulfilment-cost capitalisation, zero-margin uninstalled materials).
2. Rename `BILLING_CLEARING` to `SUBLEDGER_CLEARING` and add a mapping dimension `clearing_purpose ∈ {BILLING, UNAPPLIED_CASH, AP_SUPPLIER, INVENTORY, PAYROLL_COMMISSIONS, EQUITY, INVESTMENTS}`.

If adopted, `POLICIES.md` changes only the role literal in JET-01b, JET-02 (agent case), JET-07, JET-09, JET-14, JET-16 and JET-17. The amounts are unchanged.

**Concurrence.** `docs/reviews/objections-arch-data.md` OBJ-01 raises the same gap and proposes `COST_OF_REVENUE` and `CONTRACT_COST_CLEARING`. Either proposal resolves the capitalisation and return-asset cases. The combined recommendation is `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, and a purpose-coded clearing role for supplier payables, equity, unapplied cash and investments.

## O-2: D-21 states the option SSP formula incompletely

**Decision.** D-21: "SSP of an option = discount × likelihood of exercise (606-10-55-44)".

**Objection.** 606-10-55-44 requires the estimate to reflect the discount the customer would obtain on exercise, adjusted for (a) any discount the customer could receive without exercising the option and (b) the likelihood of exercise. Applied to an expected purchase amount (FASB Example 49: $50 × (40% − 10%) × 80% = $12), the literal D-21 formula would overstate the SSP whenever a general discount exists.

**Proposed amendment.** "SSP of an option = expected purchase amount × incremental discount (discount on exercise less the discount available without exercise) × likelihood of exercise (606-10-55-44), or the renewal practical alternative (55-45)."

**Interim compliance.** POL-026 and ALG-05 implement the full 55-44 formula. No answer key depends on the narrower wording.

## O-3: D-25 layering and refundable advance consideration

**Decision.** D-25: "Contract liabilities are layered at historical rates and not remeasured"; "The US GAAP layer approach is a policy flag."

**Objection.** Nonmonetary classification fits an obligation to transfer goods or services. An advance that the customer can demand back in cash is economically a monetary liability. The decision gives no contract-level route for that case.

**Proposed amendment.** Add: "A contract-level override may treat refundable advance consideration as monetary (remeasured at the closing rate) in the ASC606 book, with approval; the IFRS15 book always applies IFRIC 22."

**Interim compliance.** POL-163 implements the D-25 flag at entity level (default `ENABLED`, IFRS forced) and allows `DISABLED_REMEASURE_AS_MONETARY` only at contract level with OVR approval. This reads the flag as the D-25 policy flag and adds no new behaviour to the IFRS book.
