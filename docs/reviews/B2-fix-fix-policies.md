# B2 fix pass: `docs/accounting/POLICIES.md` (slug `fix-policies`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B2 (slug `fix-policies`) |
| Date | 2026-09-12 |
| File edited | `docs/accounting/POLICIES.md` only (rev 1.0 → rev 1.1; revision log added under the header) |
| Binding inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` including §7 D-11a to D-75; `docs/reviews/B1-consistency.md` |
| Scratch | `.scratch/design-fix-policies/` (backup `POLICIES.rev1.0.bak.md`; `verify_checks.py`, `lint_policies.py`, `lint_policies_b2.py`) |

## 1. Findings and decisions applied

| Finding or decision | Change made (section and id) | Status |
|---|---|---|
| B1-004 Ratable conventions | POL-090 options `DAILY`, `MONTHLY_EVEN`, `MID_MONTH`; new §2.12 ALG-11 with exact f(d) for each convention, five rules and CHK-140 to CHK-145; PT-01 CHK-110 uses `MONTHLY_EVEN`; `MONTHLY_WHOLE_MONTHS` and `TERM_NOT_WHOLE_MONTHS` retired | Applied |
| B1-005 Event names | §2.3 rules R8 and R9; table 2.3-A maps every rev 1.0 event name to its 04 E-03 literal or E-31 close-run pass; table 2.3-B lists triggers per template and accounts for all 30 E-03 literals; literals used in JET-01 to JET-05 headings, JET-01b and JET-08 rows, ALG-05 §2.6.2 and §2.6.4, ALG-06 §2.7.4, POL-078 and PT-11 | Applied. REQ-CON-004 part: not applicable (03) |
| B1-015 and D-14a Account roles | §0.8 role table rebuilt (33 values, reserved roles, templates column) and table 0.8-A `clearing_purpose`; JET-01b `UNAPPLIED_CASH`; JET-02 agent `AP_SUPPLIER`; new JET-04c `RECEIVABLE_CONTRA` with CHK-138 (research 04 S1-EX2); JET-07c credits `COST_OF_REVENUE`; new JET-07d `BILLING_CLEARING` (`INVENTORY`); JET-09a and 09a′ credit `CONTRACT_COST_CLEARING` (CHK-130 shows the line); JET-14 `EQUITY`; JET-16 claims credit `COST_OF_REVENUE`; JET-17 `INVESTMENTS`; PT-10; POL-021, POL-030, POL-125, POL-218; ALG-02 definition and excluded balances; CHK-029 and CHK-060 lines split between 07c and 07d (amounts unchanged); interim purpose-code text removed from §0.8, the JET tables and the OQ-01 default | Applied. `RECEIVABLE_CONTRA` follows D-14a, which departs from the B1-015 default |
| B1-020 Journal grain | POL-006 adds `CONTRACT_ACCOUNT_DIMENSIONS` (order as 04 E-33) with its grouping rule and REQ-JE-010 link | Applied |
| B1-027 Identifier collisions | §0.3 citation rules 1 to 3 (`POL PT-NN`, `POLICIES:OQ-nn`, `<document>:<id>` with document tokens); POL-008, POL-121, POL-211 and every §6.1 citation rewritten (for example `legacy-02:OQ2`, `research-06:Q8`) | Applied. 05 `NTR-` rename: not applicable (05) |
| JET-04a notation (B1-001 item 5) | JET-04a writes X′_p (exact) and bounds by A′_p (posted); ALG-04 §2.5.5 defines X′_p and §2.5.6 uses it; ALG-10 §2.11.2 and §2.11.3 (ΔX); ALG-06 §2.7.1 renames cumulative units transferred to N so X is only the allocation (CHK-029 input) | Applied |
| DEVIATIONS:OQ-D8 (DEV-058) | ALG-02 step 5 `CUMULATIVE_SSP_DELIVERED`: chain cumulative SSP delivered → cumulative revenue → posted allocation confirmed; a terminal fourth step (resolved SSP, positive by POL-077) makes the chain total and applies only when every non-VC posted allocation is 0. The native `POB_DEBIT_POSITIONS` fallback is made explicit in the same way | Applied (confirmed; the fourth step changes no DEV-058 expectation) |
| DEVIATIONS:OQ-D9 (DEV-060) | POL-052: under `CURRENT_REMAINING_RATE`, zero remaining quantity falls back to the average carrying rate on full-precision cumulative revenue ÷ cumulative delivered quantity; posting through ALG-01 §2.1.3 | Applied (confirmed) |
| POLICIES OQ-01 to OQ-12 (D-75) | §8 adds a "Status and ruling" column; every row reads "Resolved by D-75" with the ruling (OQ-05 carries the specific D-75 ruling; OQ-12 cites D-11a and D-17a) | Applied |
| D-11a | ALG-01 §2.1.3 [J] note; §6.4; OQ-12 | Applied |
| D-13a | POL-004 authority; §0.3 rule 3; §6.3; §6.4 | Applied |
| D-17a | POL-001 engine effect (class DEV-002); §6.4 | Applied |
| D-21a | POL-026 authority and formula text; POL-028 authority; ALG-05 heading and §2.6.1 | Applied |
| D-25a | POL-163 authority and engine effect (contract-level OVR, ASC606 book only; IFRS15 always IFRIC 22) | Applied |
| D-73 | §0.3 rule 3; POL-074 and §3.1, §3.2, POL-076 use 04 E-47 literals (`observable`, `adjusted_market`, `cost_plus_margin`, `residual`; parity `legacy_range`), which also applies the POL-074 part of B1-003; ALG-10 §2.11.1 kinds are the 04 E-09 literals; tables 2.3-A and 2.3-B use E-03 and E-31 literals | Applied |
| D-73 finding codes | Codes cited in POLICIES (for example `INVOICE_ON_NOT_A_CONTRACT`, `NEGATIVE_WEIGHT`, `RESIDUAL_REJECTED`) not checked against 04 §15.4 | Deferred: 04 §15.4 did not exist when this pass ran; §0.3 rule 3 makes 04 govern |
| D-74 | Header precedence row names `ENGINE_SPEC.md` and `ENGINE_SPEC_B.md` | Applied |
| D-75 specific rulings | Q3 → POL-090 and ALG-11; POLICIES OQ-05 → §0.8 and §8; Q11 (every CHK id in the G4 corpus) → new ids CHK-138 and CHK-140 to CHK-145 | Applied. The other rulings do not touch POLICIES |
| D-30a, D-40a, D-48a, D-72 | None | Not applicable |

## 2. New open questions (POLICIES §8)

| Id | Question | Recommended default |
|---|---|---|
| OQ-13 | 04 E-03 payloads carry no warranty claim cost and no noncash receipt, so the JET-16 claim line and the JET-17 receipt line have no trigger | 04 adds `WARRANTY_CLAIM` to `COST_INCURRED.purpose` and a noncash form of `PAYMENT_RECEIVED`; until then those lines stay ERP postings |
| OQ-14 | 04 E-09 has no kind for share-based consideration payable to a customer (PT-10) | 04 E-09 adds `SHARE_BASED_CONSIDERATION` |
| OQ-15 | D-14a names two `COST_OF_REVENUE` uses with no POL election behind them: fulfilment-cost release where elected, and zero-margin uninstalled materials | No new POL in 1.0; the engine posts `COST_OF_REVENUE` only in JET-07c and the JET-16 claim release under POL-022 `ENGINE` |

## 3. Follow-ups for other owners (not edited here)

| Document | Needed change | Reason |
|---|---|---|
| `docs/04-DATA_MODEL.md` E-21, OQ-04 | Values `DAILY`, `MONTHLY_EVEN`, `MID_MONTH`; close OQ-04 | B1-004; POL-090 |
| `docs/04-DATA_MODEL.md` §15.4 | Do not catalogue `TERM_NOT_WHOLE_MONTHS`, or mark it retired | ALG-11 rule 1 |
| `docs/04-DATA_MODEL.md` E-29 | An entry kind for JET-04c lines (for example `RECEIVABLE_CONTRA`) | JET-04c |
| `docs/04-DATA_MODEL.md` E-03 payloads, E-09 | OQ-13, OQ-14 | JET-16, JET-17, PT-10 |
| `docs/dev-guide.md` DG-ENG-06 and the answer-key world example | Drop `TERM_NOT_WHOLE_MONTHS`; replace `MONTHLY_WHOLE_MONTHS` with `MONTHLY_EVEN` | B1-004 |
| `docs/legacy/DEVIATIONS.md` §5 prose, OQ-D8, OQ-D9 | Drop `TERM_NOT_WHOLE_MONTHS` from the list of POL codes; mark OQ-D8 and OQ-D9 confirmed and note the fourth attribution step | ALG-02 step 5; POL-052 |
| `docs/05-ARCHITECTURE.md` §3 (return module postings, JET-09a open dependency) | Add JET-07d (`BILLING_CLEARING`, `INVENTORY`); JET-09a counter-role is `CONTRACT_COST_CLEARING` | D-14a |

## 4. Verification

| Check | Result |
|---|---|
| `.scratch/design-fix-policies/verify_checks.py` | Every rev 1.0 CHK reproduced unchanged. New: CHK-140 to CHK-145 period amounts and f values; CHK-143 (a) equals CHK-004 in all 24 periods; CHK-138 lines; JET-07c and JET-07d split of CHK-029 and CHK-060 (07d 120.00; 07c 180.00, 60.00, −60.00 and −120.00) |
| `.scratch/design-fix-policies/lint_policies.py` (normalises JET sub-parts a to e) | No duplicate ids; no undefined references; 0 malformed table rows; counts POL 130, CHK 75, JET 18, ALG 11, PT 11, ASU 27, OQ 15 |
| `.scratch/design-fix-policies/lint_policies_b2.py` | 0 problem classes: no PascalCase event outside table 2.3-A; retired literals appear only in retirement notes; every posting `BILLING_CLEARING` in §2 and §5 has a purpose; no `(purpose: …)` text; A′ is never the exact allocation; event, E-09 and E-31 literals exist in 04; JET Dr and Cr roles are among the 33 roles; every OQ row has a status |
