# Objections: legacy parity deviations (slug `ra-deviations`)

| Field | Value |
|---|---|
| Author | Revenue accounting manager, parity adjudication |
| Date | 2026-09-12 |
| Status | Raised for supervisor decision. `docs/legacy/DEVIATIONS.md` follows the decisions as written. |

## O-1 D-30: "dropped rows on blank memo ... become explicit validation errors"

**Decision text.** D-30 lists "dropped rows on blank memo" among the legacy silent defects that "become explicit validation errors in the exception queue".

**Issue.** Read literally, a blank `Memo 1-3` cell in a legacy v1 progress file blocks the import. `docs/03-REQUIREMENTS.md` REQ-REC-025 ("blank memos never drop rows") and REQ-DAT-005 ("dropped blank-memo rows (processed instead)") require the rows to be processed. Memos are descriptive attributes with no accounting effect (legacy 02 FX-delivery-01). Blocking the import would create friction for migrating users without protecting any number.

**What DEVIATIONS.md does.** DEV-010: the rows are processed and each blank memo raises a non-blocking finding `PROGRESS_MEMO_BLANK` (severity `WARNING`). The finding is shown in the dry-run diff and logged in the exception queue, so the condition is never silent. The golden probe `probe-P1-blank-memo-drops-progress-rows` asserts this behaviour.

**Proposed amendment.** Amend D-30 to read "legacy silent defects become explicit validation findings in the exception queue: blocking errors where the input cannot be processed correctly (duplicate files, swallowed exceptions), warnings where it can (blank memos)". The amendment changes no number.

## O-2 D-17: "journal lines exact to the cent after half-up"

**Decision text.** D-17 compares journal lines "exact to the cent after half-up".

**Issue.** The legacy journal lines were never half-up rounded individually. They are 2-dp rounds (half-even) of sums of 4-dp components. POLICIES.md ALG-01 posts round(A × f), where A is the largest-remainder posted allocation. The two methods legitimately differ by one cent per line on 19 of the 24 golden JE tests, not only on the two unbalanced months that D-17 names. Under D-17 each such case becomes a DEVIATIONS entry that needs accountant sign-off.

**What DEVIATIONS.md does.** Every cent difference is listed as a B case under DEV-002 (DEV-001 for the unbalanced months), with the exact corrected lines.

**Proposed amendment.** Add to D-17: "Cent differences between legacy report rounding and ALG-01 posted amounts are a single deviation class (DEV-002). The revenue accountant approves the class once, and the case list is regenerated mechanically by `research-harness/deviations/build_deviations.py`." Approval effort then scales with the number of methods, not the number of lines.

## O-3 POLICIES.md ALG-01 §2.1.3 composition (posted allocation × progress)

**Algorithm text.** "For a POB with allocation A (minor units) and exact cumulative progress f_t: C_t = round(A × f_t) ... When A changes (transaction-price change, modification), C_t uses the new A."

**Issue (facts from `build_deviations.py`).** Applying ALG-01 to the legacy UAT produces three kinds of one-cent departures from the exact revenue:

- **Ties.** Rounding the allocation first creates half-cent ties. Contract 1 POB #2 in January: 237.07 × 0.5 = 118.535, posted 118.54, where the exact revenue is 118.533201.
- **Rounding catch-ups on untouched POBs.** Re-apportioning allocations at a modification posts ±0.01 on POBs the modification did not touch, with no economic change. Examples: Contract 1 POB #2 on 2023-06-15, Contract 3 POB #2 and Contract 4 POB #1 on 2023-07-15, Contract 3 POB #2 on 2023-09-15.
- **Count.** 19 of 24 golden JE tests become B cases.

A contract-level composition gives the same completion guarantee with 7 B JE tests (the unbalanced months, the retrospective-mod months and the full year) and no catch-ups on untouched POBs. It rounds Σ exact cumulative revenue per contract (half-up), apportions that total over the POBs' exact cumulative revenue by largest remainder, and takes period amount = difference of posted cumulative amounts. It is available as `build_deviations.py --posting-rule LR-CUM`.

**What DEVIATIONS.md does.** It follows ALG-01 as published (PJR-1).

**Proposed amendment (supervisor or POLICIES owner to decide).** Either keep ALG-01 unchanged and approve DEV-002 as one class (O-2), or amend ALG-01 §2.1.3 so that posted cumulative revenue is apportioned at the contract level. [J] Recommended: keep ALG-01. One schedule rule across native and parity books is simpler to build and audit, and each difference is at most one cent per line.
