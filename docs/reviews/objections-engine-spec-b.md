# Objections: engine specification part B (design slug `engine-spec-b`)

| Field | Value |
|---|---|
| Author | Principal revenue engine designer (`engine-spec-b`) |
| Date | 2026-09-12 |
| Applies to | `docs/01-DECISIONS.md`; `docs/accounting/ENGINE_SPEC_B.md` follows every decision as published |

## OBJ-B-01: foreign-currency refund and deposit liabilities should be remeasured (D-25; POLICIES POL-164)

| Item | Content |
|---|---|
| Decision | D-25: contract assets and receivables are remeasured at the closing rate; contract liabilities are layered at historical rates and not remeasured. POL-164 (FORCED) lists only asset positions and, in `ENGINE` billing mode, accounts receivable |
| Objection | D-25 is silent on refund liabilities (606-10-32-10), deposit liabilities (606-10-25-8) and consideration payable to a customer (606-10-32-25). Each is an obligation to pay a fixed or determinable number of units of currency, so it is a monetary item: ASC 830-20-35-1 requires remeasurement of monetary balances at the current rate, and IAS 21.16 and 21.23(a) classify such liabilities as monetary and translate them at the closing rate. A contract liability is nonmonetary because it is settled by transferring goods or services; a refund or deposit liability is settled in cash. Leaving them at historical rates misstates the functional balance and shifts FX gains into the settlement period |
| Effect today | `ENGINE_SPEC_B.md` S12-R-11 follows POL-164: the engine does not remeasure refund liabilities, deposit liabilities or consideration payable. 05 OQ-ARC-04 (resolved by D-75) already records the same gap for deposit liabilities |
| Proposed amendment | **D-25b.** "Refund liabilities, deposit liabilities and consideration payable denominated in a currency other than the entity's functional currency are monetary items and are remeasured at the closing rate at every period end and at settlement, against `FX_GAIN_LOSS`, in every book. POLICIES adds JET-10d and extends POL-164 to `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES`." |
| Engine change if adopted | Stage 12 adds the three balances to `remeasure_period_end` (§12.2.3) with layer keys `REFUND_LIABILITY:<global event key>`, `DEPOSIT_LIABILITY:<global event key>` and `CONSIDERATION_PAYABLE:<global event key>`; T-CON-18 `balance_role` gains the three roles; E-86 gains `LIABILITY_LAYER_REMEASURED` (OQ-B-14) |
