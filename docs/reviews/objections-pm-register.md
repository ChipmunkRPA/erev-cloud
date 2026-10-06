# Objections: pm-register (requirements register author)

| Field | Value |
|---|---|
| Author | Principal product manager, revenue systems (slug `pm-register`) |
| Date | 2026-09-12 |
| Status | Submitted to supervisor. The register follows the decisions as written until amended. |

## OBJ-PM-01: D-14 account-role enum lacks counterpart roles that 1.0 answer keys post to

**Decision cited.** D-14 (account roles, C-04).

**Facts.**

- Research 04 §14.3 derives "Recovery asset for returns: Dr 1310 Recovery asset / Cr 5000 Cost of revenue". The answer key `S3-EX22` (right of return) depends on it.
- Research 04 §8 (answer key `S8-CONTRACT-COSTS`) capitalizes commissions "Dr 1400 Capitalised costs to obtain / Cr 2020 Commissions payable" and fulfilment costs "Dr 1410 / Cr 2000 AP", and amortizes fulfilment costs "Dr 5000 Cost of revenue / Cr 1410".
- Research 04 §1.2 (answer key `S1-EX2`, implicit price concession) needs "1101 AR - implicit price concession (contra)" when the engine posts billing (`billing_posting = engine`, D-13).
- Research 04 §11 (answer key `S11-MODRETRO-OWN`) posts the cumulative effect "Dr 2100 / Cr Retained earnings".
- Research 04 §5.6 (answer key `S5-EX62`, call option as financing) uses "2500 Financing obligation".
- The D-14 enum has none of these five roles: `COST_OF_REVENUE`, a capitalization offset, a receivable contra, `RETAINED_EARNINGS`, `FINANCING_OBLIGATION`.

**Judgement.** The engine cannot produce balanced journal lines for returns recovery assets, contract cost capitalization or engine-posted implicit price concessions without a role for the other side. The 1.0 answer keys `S3-EX22` and `S8-CONTRACT-COSTS` are in G4 scope.

**Proposed amendment (D-14).** Append:

| Role | Use | Release |
|---|---|---|
| `COST_OF_REVENUE` | Offset of RETURN_ASSET recognition and remeasurement; fulfilment-cost amortization where policy presents it in cost of revenue | 1.0 |
| `CONTRACT_COST_OFFSET` | Credit side of contract-cost capitalization (commission expense reclass or accrued commissions, mapped by the tenant) | 1.0 |
| `RECEIVABLE_CONTRA` | Implicit price concession and other receivable contras when `billing_posting = engine` | 1.0 |
| `RETAINED_EARNINGS` | Cumulative-effect posting of a modified retrospective adoption | later (reserve enum value) |
| `FINANCING_OBLIGATION` | Repurchase agreements classified as financing | later (reserve enum value) |

**How the register follows D-14 meanwhile.** REQ-TP-008, REQ-CST-002 and REQ-TP-015 name only D-14 roles. REQ-BK-007 (adoption bridge) and REQ-REC-015 (repurchase classification) produce reports and scope flags only, with no postings. The question is also in `docs/03-REQUIREMENTS.md` §11 (Q1) with the recommended default above.
