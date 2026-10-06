# Objections: principal data architect (`arch-data`)

| Field | Value |
|---|---|
| Author | Principal data architect, financial subledgers (design phase) |
| Date | 2026-09-12 |
| Status | Submitted to supervisor. `docs/04-DATA_MODEL.md` follows the decisions as written. |

## OBJ-01 D-14 `account_role` lacks two counter-entry roles

**Decision.** D-14 fixes `account_role` to 28 values.

**Fact.** Research 04 §14.3 derives two entries whose counter-account has no role in D-14:

| Trigger (research 04 §14.3) | Debit | Credit | Role available in D-14 |
|---|---|---|---|
| Recovery asset for expected returns (606-10-55-27, 55-29) | 1310 Return asset (`RETURN_ASSET`) | 5000 Cost of revenue | none for the credit |
| Cost capitalisation (340-40-25-1, 25-5) | 1400 / 1410 (`COST_TO_OBTAIN_ASSET` / `COST_TO_FULFILL_ASSET`) | Payables or commission expense | none for the credit |

**Consequence.** The engine cannot derive a balanced pair for these entries without reusing a role with a different meaning (for example crediting `CONTRACT_COST_AMORTIZATION` for capitalisation), which would misstate the expense roll-forward disclosed under ASC 340-40-50-3 and blur the return-asset remeasurement trail. D-16 requires every journal line pair to derive from one rounded amount and to balance, so an unpaired line is not an option.

**Proposed amendment D-14a.** Add:

- `COST_OF_REVENUE`: counter-entry for return assets and their remeasurement; also the fulfilment-cost release when a point-in-time POB transfers, if a tenant elects to post it.
- `CONTRACT_COST_CLEARING`: counter-entry for capitalised costs to obtain or fulfil a contract (the ERP has already expensed or accrued the cost; the subledger reclassifies it to the asset).

**Interim position in `docs/04-DATA_MODEL.md`.** `erev.account_role` has exactly the 28 D-14 values. An amendment is a single `ALTER TYPE erev.account_role ADD VALUE` migration; no table changes.

**Concurrence.** `docs/reviews/objections-ra-policies.md` O-1 and `docs/reviews/objections-pm-register.md` OBJ-PM-01 raise the same gap. The data model supports any of the three proposals without schema change beyond the enum: `COST_OF_REVENUE` and a capitalisation offset role are required by all three; a purpose-coded clearing role (O-1) would add one nullable `clearing_purpose` text column to `account_mapping_rule` and `subledger_line`. Recommended combined amendment: `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, and reserve `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` as later values.

## Other notes (not objections)

- `docs/03-REQUIREMENTS.md` REQ-PLT-007 reserves a column `user.external_id`. `user` is a PostgreSQL reserved word; the data model names the table `app_user` (NC-02) and reserves `app_user.external_id`. Recorded as OQ-01 in `docs/04-DATA_MODEL.md` §20.
- Migration opening balances (D-31 mode a) are held as engine state (`OPENING_BALANCE_ESTABLISHED` events and the resulting contract versions), not as journal lines, so no opening-balance clearing role is needed.
