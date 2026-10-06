# Legacy parity deviations register (G3)

| Field | Value |
|---|---|
| Owner | Revenue accounting manager, parity adjudication (design slug `ra-deviations`) |
| Date | 2026-09-12 (rev 1.1) |
| Status | Binding build contract for `make parity`. B cases need revenue-accountant sign-off per approval unit: the DEV-002 cent-difference class once, every other B case individually (00-GOAL G3; D-17, D-17a; section 9.2) |
| Machine-readable companion | `docs/legacy/golden/deviations.json`: 122 keys, one per `golden-tests.json` id (schema `erev-parity-deviations/1`), generated under posting rule `EXACT-CUM` |
| Calculation evidence | `research-harness/deviations/`: `uat_inputs.py`, `legacy_exact.py`, `journal.py`, `probes_exact.py`, `build_deviations.py` |
| Binding inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` (D-11 to D-34 as amended by D-11a, D-17a, D-30a, D-73 and D-75); `docs/03-REQUIREMENTS.md`; `docs/accounting/POLICIES.md` (POL register, ALG-01, ALG-02, CHK-007, CHK-020, CHK-022); `docs/dev-guide.md` DG-PAR-06 (import outcome mapping, B1-002); `docs/04-DATA_MODEL.md` (E-40, section 15.2 problem slugs, section 15.4 finding codes) |
| Background inputs | `docs/legacy/01`-`07`; `docs/legacy/golden/` (golden-tests.json, probes P1-P4, step CSVs, summary.json); `docs/research/99-gaps.md` |
| Objections raised | `docs/reviews/objections-ra-deviations.md`: O-1 resolved by D-30a; O-2 resolved by D-17a; O-3 resolved by D-11a (ALG-01 §2.1.3 as published, posting rule `EXACT-CUM`; the contract-level `LR-CUM` is not adopted) |

## Revision log

| Rev | Date | Change | Findings and decisions applied |
|---|---|---|---|
| 1.0 | 2026-09-12 | Initial register (design phase B1). Posting composition round(A × f) with A the posted allocation (label `ALG01`) | none |
| 1.1 | 2026-09-12 | Posting rule `EXACT-CUM` (ALG-01 §2.1.3 as published) added as the default and the generator rerun. Regenerated §0, §3 PJR-1, §4.2, §7.1, §7.3, §8, §9 and `signoff_required`: A 48 → 56, B 23 → 9, C 51 → 57 (8 journal tests B → A, 6 journal tests B → C). Probe expectations restated under the DG-PAR-06 mapping, with `import_status_basis`, `error_code_source` and `findings` on every probe upload. DEV-002 approved once as a class (`signoff_units`). Blank memo = `PROGRESS_MEMO_BLANK` WARNING, rows processed. Duplicate file refused at upload with problem `duplicate-import`. OQ-D1 to OQ-D10 closed; OQ-D11 added. Label `ALG01` retired (sensitivity rule `POSTED-ALLOC`). PJR-5 table escaping fixed | B1-001, B1-002, B1-019, B1-039; D-11a, D-17a, D-30a, D-73, D-75 |

Evidence labels: **[F]** fact (Codification paragraph, legacy code line, or a value computed by the scripts); **[J]** judgement of this document's owner, with a one-line rationale; **[A]** assumption.

---

## 0. Bottom line

1. **Classification of the 122 golden tests: A 56, B 9, C 57.** [F] The per-kind split is in section 9 and the per-test table in section 8. Rev 1.0 counted A 48, B 23, C 51 under the retired round(A × f) composition; section 9.1 lists the 14 journal tests that changed class.
2. **The corrected values rest on a verified exact oracle.** [F] `legacy_exact.py` re-implements the five legacy handlers in `fractions.Fraction` and never imports `eRev.py`. It reproduces all 106 golden `Contract_Live` versions on every compared column within 2.274e-13, with 0 mismatches. A replica of the legacy JE report built on that oracle equals all 48 golden JE outputs (24 tests, gross and adjustment views) line by line. Every corrected value therefore comes from the same inputs as the legacy value, and the only change is the rule being corrected.
3. **B (9 cases).**
   - 5 journal tests change by one cent on some lines, because eRev Cloud posts under ALG-01 §2.1.3 as published (posting rule `EXACT-CUM`, D-11a): `je-step-08`, `je-step-14`, `je-month-2023-05`, `je-month-2023-10` and `je-month-2023-full-year`. They form the DEV-002 cent-difference class, approved once (D-17a). The two unbalanced legacy months, May and October 2023, are also DEV-001.
   - January 2023 (`je-step-04`, `je-month-2023-01`) equals legacy and POLICIES.md CHK-022 and CHK-020: Dr 21001 295.69 / Cr 5001 187.69, Cr 5002 118.53, Cr 5003 48.32, with Dr 15002 58.85 (gross, 354.54 / 354.54; adjustment view 240.22 / 240.22).
   - `final-pob-Contract3-POB5` records a creation-time Original allocation of 1,268.1139 where legacy stores NULL (DEV-052).
   - Three probes: blank memos are processed with a warning (DEV-010); a re-uploaded file is rejected (DEV-011); modifications carry no pre-ASC 606 amount (DEV-050).
   - No unit-level amount (initial allocations, contract positions, POB positions, catch-ups) departs from legacy by more than 1e-4, except that NULL.
4. **C (57 cases, 9 of them journal tests).** [F] These values are correct under legacy policies that the parity preset keeps (the `Parity` column of POLICIES.md) and the ASC 606 defaults replace:
   - returns restore undelivered quantity: Contract 1 from step 07 (DEV-078);
   - the retrospective template re-weights the whole contract: Contract 2 from step 08, Contracts 3 and 4 from step 12 (DEV-071, DEV-072);
   - material-right exercise as a modification: Contract 3 from step 13 (DEV-070);
   - legacy VC pseudo-lines (DEV-077).

   The parity suite asserts the legacy value for every C case.
5. **The 0.01 imbalances (section 4).** [F] Legacy rounds each version component to 4 dp, sums components per (key, account) and rounds each sum to 2 dp half-even, with no plug. In May 2023 three Contract 2 lines round up by 0.0042, 0.0048 and 0.0010, which sum to +0.0100. In October 2023 18 lines carry rounding differences that sum to −0.0100. Under ALG-01 §2.1.3 (D-11a) and D-16 the corrected entries balance per entity:
   - May: Dr 5001 5.31, Dr 15002 5.18 / Cr 5003 10.49;
   - October: Dr 21001 2,990.37, Dr 21002 2,053.48 / Cr 5001 2,060.35, 5002 1,108.63, 5003 1,784.69, 15002 90.18.
6. **Explicit validation (section 5).** 40 finding codes (37 ERROR, 3 WARNING) turn every legacy silent defect into a blocking error or a logged warning (D-30a, REQ-DAT-005). The deviation register (section 6) holds 76 DEV entries covering every item in the legacy 01-07 defect lists and probes P1-P4: 5 numeric, 34 import, 11 engine, 16 retained policies and 10 platform. Probe import outcomes are asserted through the DG-PAR-06 mapping (section 2.2).
7. **Supervisor rulings (section 11).** D-11a, D-17a, D-30a and D-75 close OQ-D1 to OQ-D10. One new item, OQ-D11 (worksheet row of a finding on aggregated rows), is open with a recommended default.

---

## 1. Scope, inputs and method

### 1.1 Inputs (facts)

| Input | Identity | Use |
|---|---|---|
| `docs/legacy/golden/golden-tests.json` | 122 tests; SHA-256 recorded in `deviations.json` `inputs.golden_tests_sha256` | Test ids, legacy values, windows |
| Legacy code | `eRev.py` SHA-256 `7fb658fb…e2bc14` (legacy commit `5ec25ff`), read through `legacy-harness/erev_copy` only | Line references |
| UAT workbooks | 14 files, every SHA-256 verified against `golden/NN-slug/step.json` before use (`uat_inputs.py`) | Oracle inputs |
| Probe workbooks | `legacy-harness/out/probes/inputs/` (P1, P2, P3), generated by `legacy-harness/probes.py` | Probe replays |
| Golden CSVs | `golden/NN-slug/contract_live.csv`, `je_gross.csv`, `je_delta.csv`; `golden/monthly/*` | Verification of oracle and JE replica |

### 1.2 Method

| Stage | Script | What it does | Self-check |
|---|---|---|---|
| Inputs | `uat_inputs.py` | Reads the first sheet of each workbook with openpyxl; converts spreadsheet numbers through their shortest decimal string (REQ-DAT-007) into `Fraction`; traps `decimal.FloatOperation` | SHA-256 per file |
| Oracle | `legacy_exact.py` | Exact replay of setup (L682-757), delivery (L980-1089), prospective mod (L1286-1597), retrospective mod (L1770-2071) and POB-specific VC (L2247-2478). Conditions under which legacy stores inf/NaN, drops rows or double counts raise instead (none occurs in the UAT). `corrected=True` applies DEV-010, 012, 021, 050, 051 and 052 | `--verify`: 106 versions, max abs diff 2.274e-13, 0 problems |
| Journals | `journal.py` | `legacy_report` replicates L2594-2651 and L2920-2994; `engine_report` implements PJR-1 to PJR-5 (section 3); `production_journal` emits balanced JET-06-style lines per entity | Replica equals golden on 48 of 48 views |
| Probes | `probes_exact.py` | Replays P1-P4 under the legacy switches and under the preset with corrections | The legacy oracle reproduces the P2 observation (Dr 5002 66.00, Dr 5003 88.00 / Cr 21001 154.00) |
| Generator | `build_deviations.py` | Classifies every test, computes expected values under posting rule `EXACT-CUM` (PJR-1), writes `deviations.json` and the value tables of this document (`.scratch/design-fix-deviations/fragments.md`) | Legacy and corrected oracles agree on every asserted UAT value except DEV-052; every corrected journal balances; monthly lines sum to full-year lines per line (REQ-JE-008); B exactly where a value departs from legacy beyond the D-17 tolerance; every changed journal line is a one-cent difference (D-17a); POLICIES.md CHK-007, CHK-020 and CHK-022 are reproduced; posted revenue equals TP and the net position is 0 per contract at completion; `signoff_units` partition `signoff_required`; probe outcomes follow the DG-PAR-06 mapping |

### 1.3 Rerun

```bash
# only if legacy-harness/erev_copy or legacy-harness/out/probes/inputs is missing
cd ~/dev/erev/legacy-harness && ./setup.sh && ./run.sh

PY=~/dev/erev/legacy-harness/.venv/bin/python          # Python 3.12.13, openpyxl 3.1.5
$PY ~/dev/erev/research-harness/deviations/legacy_exact.py --verify            # oracle vs golden master
$PY ~/dev/erev/research-harness/deviations/legacy_exact.py --verify --corrected # differs only in DEV-052 fields
$PY ~/dev/erev/research-harness/deviations/probes_exact.py                     # P1-P4 corrected values (JSON on stdout)
$PY ~/dev/erev/research-harness/deviations/build_deviations.py                 # EXACT-CUM (binding): writes deviations.json; exit 1 on any failed self-check
$PY ~/dev/erev/research-harness/deviations/build_deviations.py --posting-rule POSTED-ALLOC  # rev 1.0 composition; sensitivity, writes .scratch only
$PY ~/dev/erev/research-harness/deviations/build_deviations.py --posting-rule LR-CUM        # O-3 alternative; sensitivity, writes .scratch only
```

The generator is deterministic: two runs produce byte-identical `deviations.json` (rev 1.1: SHA-256 `a8ac329dccc955ca46de75f30868f668d343641612fa279fd2d1b23cfadd53ae`, two runs compared on 2026-09-12; top-level `posting_rule_id` = `EXACT-CUM`). Sensitivity runs write `.scratch/design-fix-deviations/deviations-<rule>.json` and `fragments-<rule>.md` and never write under `docs/`. `POSTED-ALLOC` reproduces rev 1.0 exactly (A 48, B 23, C 51, with no classification or non-probe value difference), which confirms that rev 1.1 changes only the posting composition and the probe encoding. The generator writes into `docs/legacy/golden/`, which is read-only for the build loop (`docs/01-DECISIONS.md` §0), so only the supervisor reruns it.

---

## 2. Classification rules

### 2.1 Definitions and precedence

| Class | Definition | Parity suite asserts |
|---|---|---|
| **A** | The legacy value is correct under ASC 606 and does not depend on any preset policy whose `Parity` value differs from the `606` default | The legacy value (normalised, section 2.2) |
| **B** | The legacy value is a defect or a rounding artefact. The expected value departs from legacy beyond the D-17 tolerance, or the expected behaviour differs (a finding, a rejection, a filled field) | The corrected value in `deviations.json`; revenue-accountant sign-off required |
| **C** | The legacy value is correct under a legacy policy that the preset keeps, and applying the `606` defaults to the same economic facts would change at least one asserted value or remove the object | The legacy-parity preset value (equal to legacy after normalisation) |

Precedence: B > C > A. A B case that also depends on a preset policy keeps its policy references (`related_dev_ids`, `policy_refs`).

Decision procedure used by `build_deviations.py` [J, deterministic so that the classification can be regenerated]:

1. Compute the expected value under the preset with corrections.
2. If it departs from legacy beyond tolerance, or the test is P1, P2 or P4 → B.
3. Otherwise, if a contract whose state the test reads is in a policy state listed in table 2.3 at the test's step, or the test reads a legacy VC row → C.
4. Otherwise → A.

For a journal test, the contracts read are those with a line in the legacy or corrected output, taken at the last step whose date is on or before the window end.

### 2.2 Expected-value encoding and tolerances (D-17)

| Topic | Rule |
|---|---|
| Money and quantities | Strings. Unit-level amounts at 4 dp: the exact oracle value rounded ROUND_HALF_UP, never negative zero (legacy `-0.0` and e-13 residues become `0.0000`, DEV-004). Journal amounts at 2 dp |
| Unit-level comparison | \|engine full-precision value − expected\| ≤ 0.0001 (`tolerance` `"0.0001"`) |
| Journal comparison | Posted journal amounts equal expected exactly to the cent (`tolerance` `"0.00"`), for `lines`, every `by_account` debit, credit and net, the totals and `line_items` |
| Codes and counts | Exact (`import_status`, `error_code`, finding codes, worksheet rows, version counts) |
| Import outcome (probes) | `import_status` is an outcome label derived from stored state by the DG-PAR-06 normative mapping (B1-002); E-40 gains no stored status. `COMMITTED` = E-40 `COMMITTED` with no findings. `COMMITTED_WITH_FINDINGS` = E-40 `COMMITTED` with at least one `WARNING` finding. `REJECTED` = E-40 `INVALID`, or an upload refused with problem `duplicate-import` and `errors[0].rule_id` `IMPORT_FILE_DUPLICATE`. `error_code` = the code of the first `ERROR` finding, or `errors[0].rule_id` of the problem (DG-KRN-ERR-05). Every probe upload in `deviations.json` restates its basis in `import_status_basis` (`e40_import_status`, and `problem` for a refused upload) and `error_code_source` |
| Aggregated finding rows | A finding raised on a POB key aggregated from several worksheet rows (DEV-012) carries `worksheet_row` = the lowest contributing Excel row and `worksheet_rows` = every contributing row, ascending (OQ-D11) |
| Known-at | Every test reads the state known after step `steps_through` (bitemporal `known_at`, D-19). Contract and POB tests read the latest version per POB at that point |
| Windows | Journal tests read effective dates in [`window[0]`, `window[1]`] (section 3, PJR window rule) |
| `contract_asset` | CONTRACT_ASSET + UNBILLED_RECEIVABLE combined. The preset maps both roles to each POB's Unbilled A/R Account (D-15, POL-122, REQ-REF-008) |

### 2.3 Policy states that make a case C

| Contract | From step | DEV | Preset value (POLICIES.md `Parity`) | 606 default and effect |
|---|---|---|---|---|
| Contract 1 | 07 (2023-04-30 return) | DEV-078 | POL-051 `ACTUAL_RETURNS_ONLY`, POL-052 `CURRENT_REMAINING_RATE`, POL-053 `RESTORE_REMAINING_QUANTITY`: 3 returned units become deliverable again and TP stays 1,300.00 | `EXPECTED_RETURNS`, `AVERAGE_CARRYING_RATE`, `REDUCE_CONTRACT_QUANTITY`: the units leave the contract and the credit reduces TP, so the 2023-06-15 reduction and every later Contract 1 value differ |
| Contract 2 | 08 (2023-05-15 retrospective) | DEV-071 | POL-100 `USER_SELECTED_TEMPLATE`, POL-102 `ALL_POBS_FULL_REALLOCATION`, POL-103 `TOTAL_TP`, POL-107 `LEGACY_BY_TEMPLATE`: catch-up +13.3761 on delivered distinct hardware POB #1 | Engine-proposed route, `PARTIALLY_SATISFIED_NONDISTINCT_ONLY`, `REMAINING_TP`, `POB_MEASURE`: prospective for distinct POBs, catch-up only on nondistinct POB #3 |
| Contract 3 | 12 (2023-08-15 retrospective) | DEV-071, DEV-072 | As Contract 2, plus POL-080 `LEGACY_CARRIED_PLUS_FILE_VERSION`, POL-081 `CLAMPED_MOD_PRICE` (4 units removed at SSP 306.00, not the carried 404.00) | `D18_DEFAULT`, `CARRIED_UNIT_SSP`; no catch-up on delivered software POB #2 |
| Contract 3 | 13 (2023-09-15 exercise) | DEV-070 | POL-028 `MODIFICATION`, POL-026 `ENTERED_AMOUNT`: 833.7676 released and 1,000.00 new consideration pooled over all remaining POBs | POL-028 `CONTINUATION` (legacy 03 TC-04): POB #5 1,833.7676, POBs #1-#3 unchanged, no catch-up |
| Contract 4 | 12 (2023-08-15 retrospective) | DEV-071 | As Contract 2: catch-ups +8.6276 (hardware) and +7.6690 (software) when consulting with no progress was reduced | No catch-up (POB #3 had no progress) |
| VC rows (Contract 2 VC #1, Contract 4 VC #1) | 02 / 03 | DEV-077 | REQ-TP-016, POL-040 `ENTERED_AMOUNT`, POL-041 `NOT_APPLIED`, POL-043 `DELTA`, POL-213: the VC row imports as a TP component with SSP 0, allocation 0, a tracked quantity and no revenue | VC estimate versions with a constraint; native policies reject VC pseudo-lines as POBs, so the row does not exist natively |

### 2.4 Policies consulted that do not make a case C

These policies have the same `Parity` and `606` value, or they only change grouping or presentation that the parity report fixes. [F, POLICIES.md section 1]

| Policy | Why no C |
|---|---|
| POL-001 to POL-003 rounding; POL-004 `ERP` billing; POL-120 netting unit | Parity = 606 default (FORCED or equal) |
| POL-070 SSP version basis | `NAMED_VERSION` = the only version (2023-01-01) = the version effective at every inception and modification date in the UAT |
| POL-071 `CONTRACT_PRICE`, POL-072 `NEAREST_BOUND` | Parity = 606 default |
| POL-005 `GROSS` with the adjustment-format report always generated; POL-006 `LEGACY_CONTRACT_POB` grain | The parity suite always evaluates the legacy-grain summary report, which every tenant can generate (D-33). Grain changes only the debit/credit split per account, never net amounts |
| POL-121 reclass attribution key | Attribution moves amounts between account strings only. Every UAT contract has one Deferred Revenue Account and one Unbilled A/R Account, and golden tests assert contract totals |
| POL-026 material-right SSP method (setup tests) | The entered 1,000 dollar-units equal a native approved estimate of 1,000; the allocation is identical (POL-212) |
| POL-080 SSP basis and POL-100 route (step 11) | 25-12 fails (added hardware priced 500.00 above the 153.00-207.00 range; added consulting not distinct), so the 606 route is 25-13(a) with a 25-13(c) catch-up on the partially satisfied nondistinct POB, identical to the legacy prospective algorithm (606-10-25-12, 25-13(a)-(c)) |

---

## 3. Parity journal rule (PJR)

The parity suite derives journal expectations from the preset state with the rules below. They apply POLICIES.md ALG-01 (sections 2.1.1-2.1.3) and ALG-02 to legacy-template events. `journal.py` implements them.

| Id | Rule | Authority |
|---|---|---|
| PJR-1 | **Posted cumulative revenue (posting rule `EXACT-CUM`).** For contract c (combination group), as of date t and known after step n, with the preset state from the oracle: X_p = cumulative revenue_p + remaining allocation_p, the exact allocation (with TP_c = Σ_p X_p, the exact quota TP_c × X_p ÷ Σ X equals X_p); TP_c is in cents for legacy data. A_p = largest-remainder apportionment of TP_c in cents over weights X_p (ties: larger fractional remainder, larger weight, ascending POB line key). f_p = cumulative revenue_p ÷ X_p. Posted cumulative revenue PCR_p(t) = round(X_p × f_p), bounded to [0, A_p] ([A_p, 0] for a negative allocation), and PCR_p(t) = A_p when f_p = 1; round = ROUND_HALF_UP to the cent. A POB with X_p = 0 posts 0. Rev 1.0 posted round(A_p × f_p) (label `ALG01`, retired; sensitivity rule `POSTED-ALLOC`) | ALG-01 §2.1.1-2.1.3 as published; D-11, D-11a; POL-001 to POL-003; REQ-REC-019, REQ-ALC-002 |
| PJR-2 | **Recognition pair.** For a window [s, e]: amount_p = PCR_p(e) − PCR_p(s − 1 day). Dr CONTRACT_LIABILITY (POB Deferred Revenue Account) / Cr REVENUE (POB Revenue Account); a negative amount swaps sides | D-16; REQ-JE-002; JET recognition template; POLICIES §0.9 |
| PJR-3 | **Netting.** NP_c(t) = cumulative billing_c(t) − Σ_p PCR_p(t) (cents; ERP-posted invoices, POL-123). CA_c(t) = max(0, −NP_c(t)). Window movement = CA_c(e) − CA_c(s − 1 day): Dr UNBILLED_RECEIVABLE / CONTRACT_ASSET (Unbilled A/R Account) / Cr CONTRACT_LIABILITY. A production period journal books CA at period end and reverses it on the first day of the next period, so a calendar-month window equals reversal plus booking | ALG-02 steps 1-5; JET-06; D-12, D-13, D-15; POL-121 |
| PJR-4 | **Adjustment format.** For each delivery event in the window with pre-ASC 606 revenue p_i: Dr REVENUE / Cr CONTRACT_LIABILITY, amount round(p_i). Modification and price-change events carry 0 | D-24, D-34; POL-005, POL-007, POL-008; JET-15 |
| PJR-5 | **Legacy summary grain.** Sum pair lines per (contract, balance-sheet account) and per (contract POB SKU key, revenue account). Drop a line only if its consolidated net is 0. `by_account` debit = Σ positive line nets, credit = Σ \|negative line nets\|; `lines` = number of non-zero consolidated lines | POL-006 `LEGACY_CONTRACT_POB`; REQ-JE-007, REQ-JE-008; legacy 06 P-JE-05 |

Properties verified by the generator [F]:

- Every one of the 48 corrected views balances in total and per entity, because every line pair derives from one amount.
- Monthly lines sum to the full-year lines per line (REQ-JE-008, legacy 06 TC-JE-09).
- At completion (2023-10-31) posted revenue equals TP per contract: Contract 1 800.00, Contract 2 1,100.00, Contract 3 2,600.00, Contract 4 1,200.00. Every net position is 0.00.
- POLICIES.md CHK-022 is reproduced. January 2023 (`je-step-04`, `je-month-2023-01`) posts Contract 1 Dr 21001 295.69 / Cr 5001 128.84, Cr 5002 118.53, Cr 5003 48.32, and Contract 2 Dr 21002 58.85 / Cr 5001 58.85 with netting Dr 15002 58.85 / Cr 21002 58.85; the summary view equals legacy (Dr / Cr 354.54). CHK-020 (adjustment view, Dr / Cr 240.22) and CHK-007 (P1 118.53, not 118.54; P2 cumulative 237.07, period 118.54) are also reproduced.
- The bound and the completion alignment of PJR-1 change a posted value on two POBs only, both on 2023-10-31: Contract 3 POB #3 (round(X) 189.34 → A 189.35, completion alignment) and Contract 4 POB #3 (round(X) 293.93 → A 293.92, bound).
- No largest-remainder tie occurred in the UAT.

Alternatives over the 24 journal tests, gross and adjustment views [F, J] (generator fragments, section "sensitivity"):

| Rule | Composition | Journal tests departing from legacy | Status |
|---|---|---|---|
| `EXACT-CUM` | round(X × f), bounded by A, equal to A at completion | 5 | Binding (D-11a) |
| `POSTED-ALLOC` | round(A × f) | 19, including half-cent ties and one-cent catch-ups on POBs a modification did not touch | Rev 1.0 composition (label `ALG01`); retired by D-11a |
| `LR-CUM` | Contract-level round(Σ exact cumulative revenue), apportioned by largest remainder | 7 | Objection O-3; not adopted (D-11a) |
| `POB-CUM` | round(exact cumulative revenue) per POB with no bound and no completion alignment | 5 | Rejected: posts 2,599.99 on Contract 3 and 1,200.01 on Contract 4 after full delivery, which leaves a 0.01 contract liability and a 0.01 contract asset on fully satisfied contracts and breaks the G5 invariant "recognition equals allocation at completion" |

---

## 4. The 0.01 imbalances in May and October 2023

### 4.1 Root cause (facts)

Legacy `journal_entries` (L2594-2651) builds six components per version row in the window:

- G1/G2: ± Current Rev Rec;
- G3/G4: ± Previous Reclass to UAR;
- G5/G6: ∓ Current Reclass to UAR.

It rounds each component to 4 dp and drops components whose 2-dp value is 0. It then sums per (key, account), with balance-sheet keys per contract and revenue keys per POB, drops sums whose 2-dp value is 0, and rounds each sum to 2 dp half-even. Nothing forces Σ Dr = Σ Cr after that final rounding.

**May 2023** (window 2023-05-01 to 2023-05-31; versions of step 08 on 2023-05-15 and step 09 on 2023-05-31, Contract 2 only):

| Line key | Account | Σ 4-dp components | Legacy 2-dp line | Rounding difference |
|---|---|---|---|---|
| Contract 2 | 15002 | 5.1858 | 5.19 | +0.0042 |
| Contract 2 POB #1 Hardware 1 | 5001 | 5.3052 | 5.31 | +0.0048 |
| Contract 2 POB #3 Consulting 1 | 5003 | −10.4910 | −10.49 | +0.0010 |
| Contract 2 | 21002 | 0.0000 (suppressed) | none | 0 |
| **Net** | | | **+0.01** | **+0.0100** |

The 21002 components cancel: catch-ups +13.3761 +10.4910 −18.6813, reversals +85.0000 +108.8671, bookings −108.8671 −90.1858.

**October 2023** (window 2023-10-01 to 2023-10-31; step 14 versions, all four contracts):

| Line key | Account | Σ 4-dp components | Legacy line | Difference |
|---|---|---|---|---|
| Contract 1 | 21001 | 638.4504 | 638.45 | −0.0004 |
| Contract 1 POB #2 Software 1 | 5002 | −92.5337 | −92.53 | +0.0037 |
| Contract 1 POB #3 Consulting 1 | 5003 | −43.0163 | −43.02 | −0.0037 |
| Contract 1 POB #4 Material Right - Hardware | 5001 | −502.9004 | −502.90 | +0.0004 |
| Contract 2 | 15002 | −90.1858 | −90.19 | −0.0042 |
| Contract 2 | 21002 | 1,080.0000 | 1,080.00 | 0.0000 |
| Contract 2 POB #1 Hardware 1 | 5001 | −519.6617 | −519.66 | +0.0017 |
| Contract 2 POB #2 Software 1 | 5002 | −385.1852 | −385.19 | −0.0048 |
| Contract 2 POB #3 Consulting 1 | 5003 | −84.9673 | −84.97 | −0.0027 |
| Contract 3 | 21001 | 2,351.9147 | 2,351.91 | −0.0047 |
| Contract 3 POB #1 Hardware 1 | 5001 | −678.0182 | −678.02 | −0.0018 |
| Contract 3 POB #2 Software 1 | 5002 | −311.1106 | −311.11 | +0.0006 |
| Contract 3 POB #3 Consulting 1 | 5003 | −94.6720 | −94.67 | +0.0020 |
| Contract 3 POB #5 Consulting 1 | 5003 | −1,268.1139 | −1,268.11 | +0.0039 |
| Contract 4 | 21002 | 973.4814 | 973.48 | −0.0014 |
| Contract 4 POB #1 Hardware 1 | 5001 | −359.7649 | −359.76 | +0.0049 |
| Contract 4 POB #2 Software 1 | 5002 | −319.7910 | −319.79 | +0.0010 |
| Contract 4 POB #3 Consulting 1 | 5003 | −293.9255 | −293.93 | −0.0045 |
| **Net** | | | **−0.01** | **−0.0100** |

The e-14 reclass residues on Contracts 3 and 4 (legacy 07 A2) round to 0 and are dropped, so they play no part.

Contributing condition [F]: the full-year report balances only by offset. Contract 3's revenue lines total 2,599.99 against a 2,600.00 deferred line, and Contract 4's total 1,200.01 against 1,200.00 (legacy 06 TC-JE-08, TC-JE-09).

### 4.2 Corrected journal lines under D-11 and D-16 (production period journals)

Lines are generated by `journal.production_journal` from PJR-1 to PJR-3 under posting rule `EXACT-CUM`. Roles follow D-14; accounts follow the preset mapping (REQ-REF-008). Currency USD, book `ASC606`. Every pair derives from one amount.

**May 2023, Mock Entity 2 (Contract 2).** Posted cumulative revenue (PJR-1):

- as of 2023-04-30: exact allocations X 470.769231 / 313.846154 / 115.384615 / 0 (TP 900.00; posted allocations A 470.77 / 313.85 / 115.38 / 0.00); POB #1 round(470.769231 × 1/8) = round(58.846154) = 58.85; POB #3 round(115.384615 × 0.4) = round(46.153846) = 46.15;
- as of 2023-05-31: X 573.202614 / 385.185185 / 141.612200 / 0 (TP 1,100.00; A 573.20 / 385.19 / 141.61 / 0.00); POB #1 round(573.202614 × 0.093407…) = round(53.540904) = 53.54; POB #3 round(141.612200 × 0.4) = round(56.644880) = 56.64;
- billing to date 20.00.

| # | Date | Type | POB | Dr (role) | Cr (role) | Amount |
|---|---|---|---|---|---|---|
| 1 | 2023-05-01 | Netting reversal (April balance: 105.00 − 20.00) | - | 21002 CONTRACT_LIABILITY | 15002 UNBILLED_RECEIVABLE / CONTRACT_ASSET | 85.00 |
| 2 | 2023-05-31 | Recognition: POB #1 posted 58.85 → 53.54 | POB #1 | 5001 REVENUE | 21002 CONTRACT_LIABILITY | 5.31 |
| 3 | 2023-05-31 | Recognition: POB #3 posted 46.15 → 56.64 | POB #3 | 21002 CONTRACT_LIABILITY | 5003 REVENUE | 10.49 |
| 4 | 2023-05-31 | Netting (NP = 20.00 − 110.18; auto-reverses 2023-06-01) | - | 15002 UNBILLED_RECEIVABLE / CONTRACT_ASSET | 21002 CONTRACT_LIABILITY | 90.18 |
| | | **Totals** | | **190.98** | **190.98** | |

Legacy-grain summary (PJR-5): Dr 5001 5.31, Dr 15002 5.18 / Cr 5003 10.49; total 10.49 / 10.49; 21002 nets to 0.00.

**October 2023.** Every POB reaches f = 1, so posted cumulative revenue equals the posted allocation A (PJR-1 completion rule). Posted cumulative amounts before the window are round(X × f) as of 2023-09-30.

| # | Entity | Date | Type | Contract / POB | Dr (role) | Cr (role) | Amount |
|---|---|---|---|---|---|---|---|
| 1 | Mock Entity 1 | 2023-10-31 | Recognition | C1 POB #2 (118.53 → 211.07) | 21001 CONTRACT_LIABILITY | 5002 REVENUE | 92.54 |
| 2 | Mock Entity 1 | 2023-10-31 | Recognition | C1 POB #3 (43.02 → 86.03) | 21001 CONTRACT_LIABILITY | 5003 REVENUE | 43.01 |
| 3 | Mock Entity 1 | 2023-10-31 | Recognition | C1 POB #4 (0.00 → 502.90) | 21001 CONTRACT_LIABILITY | 5001 REVENUE | 502.90 |
| 4 | Mock Entity 2 | 2023-10-01 | Netting reversal (September balance 90.18) | C2 | 21002 CONTRACT_LIABILITY | 15002 UNBILLED_RECEIVABLE / CONTRACT_ASSET | 90.18 |
| 5 | Mock Entity 2 | 2023-10-31 | Recognition | C2 POB #1 (53.54 → 573.20) | 21002 CONTRACT_LIABILITY | 5001 REVENUE | 519.66 |
| 6 | Mock Entity 2 | 2023-10-31 | Recognition | C2 POB #2 (0.00 → 385.19) | 21002 CONTRACT_LIABILITY | 5002 REVENUE | 385.19 |
| 7 | Mock Entity 2 | 2023-10-31 | Recognition | C2 POB #3 (56.64 → 141.61) | 21002 CONTRACT_LIABILITY | 5003 REVENUE | 84.97 |
| 8 | Mock Entity 1 | 2023-10-31 | Recognition | C3 POB #1 (0.00 → 678.02) | 21001 CONTRACT_LIABILITY | 5001 REVENUE | 678.02 |
| 9 | Mock Entity 1 | 2023-10-31 | Recognition | C3 POB #2 (153.41 → 464.52) | 21001 CONTRACT_LIABILITY | 5002 REVENUE | 311.11 |
| 10 | Mock Entity 1 | 2023-10-31 | Recognition | C3 POB #3 (94.67 → 189.35; round(X) 189.34 aligned to A) | 21001 CONTRACT_LIABILITY | 5003 REVENUE | 94.68 |
| 11 | Mock Entity 1 | 2023-10-31 | Recognition | C3 POB #5 (0.00 → 1,268.11) | 21001 CONTRACT_LIABILITY | 5003 REVENUE | 1,268.11 |
| 12 | Mock Entity 2 | 2023-10-31 | Recognition | C4 POB #1 (119.92 → 479.69) | 21002 CONTRACT_LIABILITY | 5001 REVENUE | 359.77 |
| 13 | Mock Entity 2 | 2023-10-31 | Recognition | C4 POB #2 (106.60 → 426.39) | 21002 CONTRACT_LIABILITY | 5002 REVENUE | 319.79 |
| 14 | Mock Entity 2 | 2023-10-31 | Recognition | C4 POB #3 (0.00 → 293.92; round(X) 293.93 bounded to A) | 21002 CONTRACT_LIABILITY | 5003 REVENUE | 293.92 |

| Entity | Σ Dr | Σ Cr |
|---|---|---|
| Mock Entity 1 | 2,990.37 | 2,990.37 |
| Mock Entity 2 | 2,053.48 | 2,053.48 |

Legacy-grain summary (PJR-5):

- Dr 21001 2,990.37, Dr 21002 2,053.48;
- Cr 5001 2,060.35, Cr 5002 1,108.63, Cr 5003 1,784.69, Cr 15002 90.18;
- total 5,043.85 / 5,043.85.

Versus legacy (Dr 21001 2,990.36; Cr 5001 2,060.34, 5002 1,108.62, 5003 1,784.70, 15002 90.19; total 5,043.84 / 5,043.85), the changed lines are:

| Line | Legacy | Corrected | Cause under PJR-1 |
|---|---|---|---|
| C1 POB #2 5002 | −92.53 | −92.54 | 211.07 − 118.53; legacy rounds the 92.5337 component |
| C1 POB #3 5003 | −43.02 | −43.01 | 86.03 − 43.02; legacy rounds the 43.0163 component |
| C2 15002 | −90.19 | −90.18 | Reversal of the posted September contract asset (110.18 − 20.00) |
| C3 21001 | 2,351.91 | 2,351.92 | Follows C3 POB #3 |
| C3 POB #3 5003 | −94.67 | −94.68 | Completion alignment: 189.35 − 94.67 |
| C4 POB #1 5001 | −359.76 | −359.77 | 479.69 − 119.92 |
| C4 POB #3 5003 | −293.93 | −293.92 | Bound: A 293.92 below round(X) 293.93 |

Final posted revenue per POB (PJR-1 at completion) differs from the legacy full-year revenue line on two POBs:

- Contract 3 POB #3: 189.35 (legacy 189.34). TP 2,600.00 over exact allocations 678.018250 / 464.523854 / 189.343962 / 0 / 1,268.113933 floors to 2,599.98, and the 2 cents go to the largest fractional remainders (0.825 and 0.3962 cents): A = 678.02 / 464.52 / 189.35 / 0.00 / 1,268.11. round(X) = 189.34, and the completion rule posts A.
- Contract 4 POB #3: 293.92 (legacy 293.93). TP 1,200.00 apportions A = 479.69 / 426.39 / 293.92 / 0.00. round(X) = 293.93 exceeds A, and the bound posts A.

---

## 5. Validation findings and codes (D-30)

Every legacy silent defect becomes an explicit finding in the dry-run diff and the exception queue (D-30, D-30a; REQ-DAT-001, 005, 006, 009).

- `ERROR` (a blocking error, D-30a) is raised where the input cannot be processed correctly. It blocks the commit of the whole file. The default is all-or-nothing (REQ-DAT-008).
- `WARNING` is raised where the input can be processed correctly, for example a blank memo (`PROGRESS_MEMO_BLANK`, rows processed). It is logged and does not block.
- Code authority: `docs/04-DATA_MODEL.md` §15.4 owns these codes (D-73) and absorbs the table below verbatim. Finding severity `ERROR` raises an `exception_item` of severity `BLOCKING` and `WARNING` raises `WARNING` (E-43). The parity suite asserts finding severities.

Stages follow REQ-DAT-001: header, type, cross-row, cross-file. Two further stages apply: engine (computation) and journal (generation or commit). Every message names worksheet, Excel row, column, rule id and failing key where the stage has them (REQ-DAT-006). The parity suite asserts the code, the severity and the worksheet rows. Message wording is not asserted.

| # | Code | Severity | Stage | Condition | Legacy behaviour | DEV | Authority |
|---|---|---|---|---|---|---|---|
| 1 | `TEMPLATE_HEADER_MISMATCH` | ERROR | header | Missing or extra columns against the exact legacy v1 header set of the template (case and whitespace sensitive; order ignored) | Rejected with missing and extra lists (VR-setup-02/06, VR-delivery-04, VR-prospective-mod-04, VR-retro-mod-04 to 06, VR-pob-vc-02 to 04) | - (correct) | REQ-DAT-002 |
| 2 | `VALUE_NOT_NUMERIC` | ERROR | type | Non-numeric value in a numeric column; every failing cell is reported | Rejected at the first failing column only | - (granularity per REQ-DAT-006) | REQ-DAT-006, 007 |
| 3 | `REQUIRED_VALUE_BLANK` | ERROR | type | Blank identifier (`Contract Unique Name`, `POB Unique ID`, `SKU Name`), setup price or quantity, SSP list price, discount or range, `Mod Billing`, `Mod Qty`, or progress `Current Delivery`, `Current Billing`, pre-ASC 606 amount | Progress and modification blanks rejected; setup and SSP blanks accepted as NaN (M-02, M-03); blank identifiers swallowed | DEV-026 | REQ-DAT-005 |
| 4 | `PROGRESS_MEMO_BLANK` | WARNING | type | Blank `Memo 1`, `Memo 2` or `Memo 3` on a progress row; the row is processed and keeps the prior memo | Row dropped with a success popup (P1) | DEV-010 | D-30a; REQ-REC-025, REQ-DAT-005 |
| 5 | `IMPORT_FILE_DUPLICATE` | ERROR | upload | (tenant, template version, file SHA-256) equals an import that is not `INVALID`, `REJECTED`, `CANCELLED` or `FAILED`. The upload is refused before validation with HTTP 409 problem `duplicate-import` and `errors[0].rule_id` = `IMPORT_FILE_DUPLICATE`; no `import_upload` row and no finding row are created | Accepted again; quantities and billings doubled (P4) | DEV-011 | D-30a; 05 IPL-01; REQ-DAT-001, 011 |
| 6 | `IMPORT_NO_DATA_ROWS` | ERROR | file | Header-only workbook | Success popup, 0 rows | DEV-017 | REQ-MOD-019, REQ-DAT-005 |
| 7 | `IMPORT_PROCESSING_FAILED` | ERROR | file | Any unexpected exception during validation or computation; nothing committed; correlation id logged | `except TypeError: pass`: silent abort | DEV-016 | REQ-DAT-005 |
| 8 | `SSP_DUPLICATE_KEY` | ERROR | cross-row | (`SKU Name`, `ASC 606 Stratification`, `SSP Version`) repeated in the file or equal to an approved version row | Join fans out rows; TP double counted | DEV-015 | REQ-SSP-013 |
| 9 | `SSP_KEY_NOT_FOUND` | ERROR | cross-file | Contract or modification row whose SKU, stratification and version resolve to no approved SSP row; the message shows the key, for example `Hardware X / Hardware 1 / 2023-01-01` | Rejected listing SKU names only ("databse") | DEV-034 | REQ-DAT-006, REQ-REF-014 |
| 10 | `SSP_DISTINCT_FLAG_INVALID` | ERROR | type | `Distinct or Nondistinct` not exactly `Distinct` or `Nondistinct` | Accepted; the prospective handler drops such rows (P-04) | DEV-025 | REQ-POB-003 |
| 11 | `SSP_PERCENT_OUT_OF_RANGE` | ERROR | type | `Midpoint Discount Percentage` < 0 or ≥ 1; `SSP Range Method (+-)` < 0 | Accepted (S23: negative SSP) | DEV-029 | REQ-DAT-005 |
| 12 | `SETUP_DUPLICATE_POB` | ERROR | cross-row | (`Contract Unique Name`, `POB Unique ID`) repeated in a setup file | Both rows written; TP double counted | DEV-014 | REQ-DAT-005 |
| 13 | `SETUP_QUANTITY_ZERO` | ERROR | type | `Original POB Total Qty` = 0 | NULL unit rates | DEV-027 | REQ-DAT-005 |
| 14 | `TOTAL_SSP_ZERO` | ERROR | cross-row | Contract total SSP = 0, for example a contract with only VC rows | NULL allocation | DEV-028 | POL-077 |
| 15 | `NEGATIVE_BOOKING_LINE` | ERROR | type | Setup row with negative quantity whose stratification is not `VC` | Inverted band; price clamped to Higher (S07) | DEV-033 | POL-078, REQ-SSP-004 |
| 16 | `SETUP_CONTRACT_EXISTS` | ERROR | cross-file | Setup row for a contract that is already activated; the message points to the modification workflow | New version appended; cumulative state reset (S14) | DEV-031 | REQ-DAT-017 |
| 17 | `DATE_INVALID` | ERROR | type | Date cell or prompt that is not a calendar date (ISO text or Excel serial accepted) | Prompts validated; template dates stored as text (M-01) | DEV-030 | REQ-DAT-007 |
| 18 | `DATE_RANGE_INVERTED` | ERROR | type | `POB End Date` before `POB Start Date`, `Mod End Date` before `Mod Start Date`, or report range start after end | Accepted | DEV-030 | REQ-RPT-012 |
| 19 | `PROGRESS_OUTSIDE_POB_TERM` | WARNING | cross-file | Progress event dated outside [POB Start Date, POB End Date] | Accepted silently | DEV-030 | legacy 02 §2 (absent checks) |
| 20 | `CONTRACT_NOT_FOUND` | ERROR | cross-file | Progress, modification or price-change row for a contract that does not exist | Modification templates create an orphan contract (P-02, S14, S06 05) | DEV-018 | REQ-MOD-019 |
| 21 | `POB_NOT_FOUND` | ERROR | cross-file | Progress or price-change row for an unknown POB key; modification row for an unknown POB that is not an add-POB row (DEV-018) | Phantom line (price change); rejection citing the merged index instead of the Excel row (progress) | DEV-018, DEV-019 | REQ-MOD-019, REQ-DAT-006 |
| 22 | `PROGRESS_OVER_DELIVERY` | ERROR | cross-file | Aggregated delivery for a POB exceeds remaining quantity (all strata); names contract, POB, product, requested and remaining quantity | Rejected without naming the POB (P3) | DEV-020 | REQ-REC-024 |
| 23 | `PROGRESS_OVER_BILLING` | ERROR | cross-file | Aggregated non-VC billing exceeds the remaining billing plan; names contract, POB, product, requested and remaining | As #22 | DEV-020 | REQ-REC-024 |
| 24 | `RETURN_EXCEEDS_DELIVERED` | ERROR | cross-file | A return would make cumulative delivered quantity negative | Accepted (E03: cumulative delivery −1) | DEV-021 | REQ-TP-009 |
| 25 | `REFUND_EXCEEDS_BILLED` | ERROR | cross-file | A credit would make non-VC cumulative billing negative | Accepted (E03: cumulative billing −50) | DEV-021 | REQ-TP-009 |
| 26 | `VC_CREDIT_EXCEEDS_ESTIMATE` | ERROR | cross-file | A credit on a VC element exceeds the magnitude of its current estimate version | Accepted (E13) | DEV-022 | REQ-TP-016 |
| 27 | `MOD_DUPLICATE_KEY` | ERROR | cross-row | Two modification or price-change rows for the same contract, POB and SKU | Duplicate same-timestamp versions (P-03, S03, S04 05) | DEV-013 | REQ-MOD-019 |
| 28 | `MOD_SIGN_MISMATCH` | ERROR | type | `Mod Qty` and `Mod Billing` both non-zero with opposite signs | Accepted (P-15) | DEV-036 | REQ-MOD-019 |
| 29 | `MOD_POB_SKU_MISMATCH` | ERROR | cross-file | Existing `POB Unique ID` uploaded with a different `SKU Name` | Second, new POB (P-14) | DEV-037 | REQ-MOD-019 |
| 30 | `MOD_ATTRIBUTE_CONFLICT` | ERROR | cross-file | Modification or price-change row whose `ASC 606 Stratification`, `Selling Entity`, `Deferred Revenue Account` or `Unbilled A/R Account` differs from the stored POB. `SSP Version` is exempt because it prices the increment (POL-080 parity) | Silently ignored (S05 04, DEF-pob-vc-12) | DEV-035 | REQ-CON-007 |
| 31 | `MOD_REMAINING_NEGATIVE` | ERROR | engine | After a modification or price change, remaining quantity < 0 or non-VC remaining billing < 0 (legacy VR-prospective-mod-09, VR-retro-mod-11, VR-pob-vc-08, kept by the preset) | Rejected with a generic message | DEV-041 | REQ-MOD-007, 008 |
| 32 | `MOD_PROGRESS_UNDEFINED` | ERROR | engine | Nondistinct catch-up where delivered + remaining quantity = 0 and cumulative revenue ≠ 0 | All recognised revenue reversed (D-14 03) | DEV-059 | 606-10-25-13(b) |
| 33 | `VC_QUANTITY_NOT_ALLOWED` | ERROR | type | Price-change (POB-specific VC template) row with `Mod Qty` ≠ 0 | Accepted; unit SSP diluted (S02 05) | DEV-038 | legacy 05 FIX-pob-vc-02 |
| 34 | `VC_TARGET_INVALID` | ERROR | cross-file | Price-change row targeting a VC element | Negative allocation on a zero-SSP line (S07 05) | DEV-039 | REQ-TP-016 |
| 35 | `VC_ALLOCATION_NEGATIVE` | ERROR | engine | Targeted POB total allocation (cumulative revenue + remaining allocation + change) < 0 | Accepted; negative cumulative revenue (S32 05) | DEV-040 | 606-10-32-44 |
| 36 | `ACCOUNT_MAPPING_MISSING` | ERROR | journal | A role needed by a line has no mapping; under the preset, a blank POB account column | Line dropped; JE out of balance (VR-reports-11) | DEV-042 | REQ-REF-008, REQ-JE-022 |
| 37 | `JOURNAL_UNBALANCED` | ERROR | journal | Deferred constraint guard at batch commit; never raised under PJR | 0.01 imbalances exported (A1) | DEV-001 | D-16, REQ-JE-001 |
| 38 | `NON_FINITE_AMOUNT` | ERROR | engine | A formula would divide a non-zero amount by zero or produce an undefined value; names formula id, contract and POB | inf or NaN persisted with a success popup (E20b, E22b, P-11, S15) | DEV-004 | D-11; REQ-RPT-018 |
| 39 | `LATE_EVENT` | WARNING | engine | Event effective in a closed period, or earlier than a committed later event of the same contract; posted under ALG-09 with `origin_period` | Accepted; prior JE ranges change retroactively (E09, P-10, S13, S20 05) | DEV-024 | D-19; REQ-CLS-004, 006 |
| 40 | `EVENT_BEFORE_INCEPTION` | ERROR | cross-file | Event effective before the contract inception date | Accepted | DEV-024 | D-19 |

There are 40 codes: 37 of severity ERROR and 3 of severity WARNING. POLICIES.md codes that the importer can also raise (`NEGATIVE_WEIGHT`, `TOTAL_WEIGHT_ZERO`, `POLICY_LEVEL_NOT_ALLOWED`, `TERM_NOT_WHOLE_MONTHS`) keep their POLICIES.md definitions.

---

## 6. Deviation register

Every defect in the legacy defect lists appears once, with every source id cited, together with the four probes (P1-P4). Source prefixes:

- L01: FIX, M, AA, S, VR-setup;
- L02: VR-delivery, AA-delivery, FX-delivery, E, TC-delivery;
- L03: D, G, A, P-, TC;
- L04: W, S, FIX, TC-RM;
- L05: DEF-pob-vc, SIM, S, TC-pob-vc;
- L06: VR-reports, E-, FX, TC-JE, TC-REP;
- L07: A1-A11, P1-P4, C1-C8, J1-J6.

"Affected golden tests" lists only `golden-tests.json` ids. For DEVs without a golden test, the corrected expectation quoted is the legacy document's own test case, carried as an answer-key candidate (family `PAR`).

### 6.1 Numeric and posting

| ID | Defect (sources) | Legacy behaviour [F] | Correct behaviour | Code | Refs | Affected golden tests and expected values |
|---|---|---|---|---|---|---|
| DEV-001 | JE summary out of balance by 0.01 (L07 A1, GT-17, GT-25; L06 VR-reports-10, E-3, FX-01, TC-JE-05, TC-JE-07; L02 AA-delivery-10, FX-delivery-18; L01 AA-16, FIX-09; L03 A-17, FX-14; research 07 L10) | May 2023 Dr 10.50 / Cr 10.49; October 2023 Dr 5,043.84 / Cr 5,043.85; mechanism in section 4.1 | PJR-1 to PJR-5: every pair from one amount; balance per entity, book, currency and period by construction; deferred constraint guard | `JOURNAL_UNBALANCED` (guard) | D-11, D-11a, D-16, D-17a; POL-001 to POL-003, POL-006; ALG-01, ALG-02; REQ-JE-001, 002, 009 | `je-step-14`, `je-month-2023-05`, `je-month-2023-10`: section 7.1 (May corrected Dr 5001 5.31, 15002 5.18 / Cr 5003 10.49; October total 5,043.85 / 5,043.85). Members of the DEV-002 class approval (D-17a) |
| DEV-002 | Period amounts rounded per consolidated line instead of ALG-01 posted cumulative amounts (L06 §3.3, TC-JE-09, TC-JE-14; L01 TC-setup-09; research 99 C-07) | Each component rounded to 4 dp, each consolidated line to 2 dp half-even. Monthly lines do not foot to the full year per line (C1 POB #2, C1 POB #3, C3 21001, C4 POB #1 differ by ±0.01). Full-year revenue lines total 2,599.99 on Contract 3 and 1,200.01 on Contract 4 | PJR-1 (`EXACT-CUM`): posted cumulative revenue = round(X × f) with X the exact allocation, bounded by the largest-remainder allocation A and equal to A at completion; period amount = difference of posted cumulative amounts; monthly lines sum to full-year lines. One deviation class, approved once; the case list is regenerated mechanically (D-17a) | none | D-11, D-11a, D-17a; POL-001 to POL-003; ALG-01 §2.1.2-2.1.3; REQ-REC-019, REQ-ALC-002, REQ-JE-008 | 5 journal tests (section 7.1): `je-step-08`, `je-step-14`, `je-month-2023-05`, `je-month-2023-10`, `je-month-2023-full-year` |
| DEV-003 | Sub-cent components dropped before aggregation (L06 VR-reports-08, E-4, FX-02, TC-JE-15) | Components whose 2-dp value is 0 are removed before summing; three components of 0.004 give an empty JE | Posting from cumulative amounts (PJR-1); no component pre-filter; only zero consolidated nets suppressed (PJR-5) | none | REQ-JE-009 | none. In the UAT only e-13 residues were dropped, and they are exactly 0 in the oracle |
| DEV-004 | Binary-float state: residues, negative zero, inf and NaN persisted (L07 A2, A11; L02 AA-delivery-09, FX-delivery-03, 11, E20b, E22a, E22b; L03 D-07, P-11; L04 W9, W14, S15; L05 DEF-pob-vc-06, 15) | `Current Contract Position - Contract Level` 5.684e-14; noise reclass 1.022e-13 on C3 POB #5 at step 14; `-0.0` contract assets; `inf` unit rates when quantity reaches 0 with a residue | Exact arithmetic (`Fraction` or a 38-digit `Decimal`, `FloatOperation` trapped); `NUMERIC` storage; no NaN or inf (CHECK constraints); values at 4 dp never negative zero | `NON_FINITE_AMOUNT` | D-11; REQ-REF-004 | Normalisation only; classification unchanged. Every legacy `-0.0` (for example `rollforward-02-Contract1` `contract_asset`, `rollforward-14-Contract3` `position`, `final-pob-Contract1-POB1` `Position POB`) is expected as `0.0000` |
| DEV-005 | No final-delivery true-up; rates re-derived by division (L02 §3.7, FX-delivery-03) | The last unit is recognised at q × rate; residues remain | When remaining quantity reaches 0, revenue = remaining allocation and rates = 0 | none | D-11 | none. The exact oracle reaches 0 exactly in every UAT step |

### 6.2 Import and validation (D-30)

| ID | Defect (sources) | Legacy behaviour [F] | Correct behaviour | Code | Refs | Affected golden tests |
|---|---|---|---|---|---|---|
| DEV-010 | Blank memo drops progress rows (L07 P1, GT-22; L02 VR-delivery-13, E01, E01b, AA-delivery-07, FX-delivery-01, TC-delivery-13; L06 VR-reports-18, E-6, FX-14, TC-JE-13) | `groupby` on Memo 1-3 with `dropna=True` (L909-913); success popup | Rows aggregate by POB key whatever their memos and are processed; each blank memo raises a warning; the version keeps the prior memo | `PROGRESS_MEMO_BLANK` (WARNING) | D-30a; REQ-REC-025, REQ-DAT-005 | `probe-P1-blank-memo-drops-progress-rows` → B (section 7.3) |
| DEV-011 | Re-upload of the same file double counts (L07 P4, GT-24; L02 E08, AA-delivery-08, FX-delivery-08, TC-delivery-17; L03 P-19, TC-12; L01 TC-setup-25) | Accepted; C1 POB #1 delivered cumulative 4.0; February gross 448.06 | Refused at upload by file hash with HTTP 409 problem `duplicate-import` and `errors[0].rule_id` `IMPORT_FILE_DUPLICATE`; corrections go through reversal events, never re-upload (REQ-JE-006) | `IMPORT_FILE_DUPLICATE` | D-30a; 05 IPL-01; REQ-DAT-001, 011; REQ-PLT-026 | `probe-P4-duplicate-upload-double-counts` → B (section 7.3) |
| DEV-012 | Same POB with different memos not aggregated (L02 VR-delivery-14, E04, E04b, FX-delivery-07, TC-delivery-16) | Two rows for one POB, each checked against the same remaining balance (6 of 5 accepted); next read keeps one | Sum by POB key before validation; memos kept as event detail; version memo = last non-blank value in worksheet order | none (over-delivery then applies) | REQ-REC-025 | none |
| DEV-013 | Duplicate modification or price-change keys (L03 D-04, P-03, G-02, TC-12; L04 S03, W6, TC-RM-10; L05 DEF-pob-vc-04, G3, TC-pob-vc-10) | Duplicate same-timestamp versions; contract position double counted | Reject | `MOD_DUPLICATE_KEY` | REQ-MOD-019 | none |
| DEV-014 | Duplicate POB key in a setup file (L01 M-05, S16, FIX-04, TC-setup-14) | Both rows written; TP 1,800 instead of 1,300 | Reject | `SETUP_DUPLICATE_POB` | REQ-DAT-005 | none |
| DEV-015 | Duplicate SSP key (L01 M-04, S08, FIX-04, TC-setup-13; L03 G-09; L04 S18, W6, TC-RM-16) | Join fans out; TP 2,170.77 in S18 | Reject; SSP versions append and are unique (REQ-SSP-001) | `SSP_DUPLICATE_KEY` | REQ-SSP-013 | none |
| DEV-016 | Swallowed `TypeError`; numeric identifiers abort silently (L01 VR-setup-04, 10, S11, FIX-03, TC-setup-15; L02 VR-delivery-12, E02, TC-delivery-14; L03 VR-prospective-mod-11, D-12, P-18; L04 VR-retro-mod-13, W13; L05 VR-pob-vc-10, DEF-pob-vc-11) | No popup, nothing written | Identifiers coerced to text (leading zeros kept) and accepted; any unexpected failure is explicit | `IMPORT_PROCESSING_FAILED` | REQ-DAT-005, 007 | none |
| DEV-017 | Header-only file reports success (L02 VR-delivery-15, E05; L03 D-11, P-07, G-10, TC-20; L04 S01, TC-RM-09; L05 G2, S18, TC-pob-vc-15) | Success popup, 0 rows | Reject | `IMPORT_NO_DATA_ROWS` | REQ-MOD-019 | none |
| DEV-018 | Unknown contract creates an orphan contract; unknown POB creates a phantom line (L03 D-02, P-02, G-01, TC-11; L04 S14, TC-RM-14; L05 DEF-pob-vc-05, G4, S05, S05b, S06, S06b, TC-pob-vc-11) | Orphan contract with allocation = billing; phantom line with +inf unit rate | Reject unknown contracts. In the v1 prospective and retrospective templates, a row for an existing contract with an unknown key is an add-POB row when `Mod Qty` > 0, `Mod Billing` ≥ 0 and the SSP key resolves (UAT 2023-09-15 adds POB #5 this way); otherwise reject. Progress and price-change rows never add POBs | `CONTRACT_NOT_FOUND`, `POB_NOT_FOUND` | REQ-MOD-019 | none (UAT step 13 is a valid add-POB row) |
| DEV-019 | Unmatched progress row cites the merged index (L02 VR-delivery-07, E06, E06b, TC-delivery-12) | Message "9" for data rows 1 and 2 | Name the Excel row and the key | `POB_NOT_FOUND` | REQ-DAT-006 | none |
| DEV-020 | Over-delivery rejection does not name the POB (L07 P3, GT-21; L02 VR-delivery-08, E11, E12, E18, TC-delivery-10) | Rejected, nothing written, generic message | Same rejection (E-40 `INVALID`), naming contract, POB, product, requested and remaining in an `ERROR` finding on the aggregated POB key | `PROGRESS_OVER_DELIVERY`, `PROGRESS_OVER_BILLING` | REQ-REC-024 | `probe-P3-over-delivery-validation` → A (section 7.3) |
| DEV-021 | Over-returns and over-refunds accepted; VR-delivery-09 tests remaining, not cumulative, balances (L02 VR-delivery-09, E03, AA-delivery-03, FX-delivery-02, TC-delivery-15; research 99 C-10) | Cumulative delivery −1, billing −50, revenue −64.420218 | Reject against cumulative delivered quantity and cumulative billing | `RETURN_EXCEEDS_DELIVERED`, `REFUND_EXCEEDS_BILLED` | D-22; REQ-TP-009 | none |
| DEV-022 | VC lines excluded from billing checks; credits beyond the estimate accepted (L07 A3; L02 E13, AA-delivery-04, FX-delivery-10, TC-delivery-18) | −150 credit against a −100 VC accepted; contract asset 208.846154 | Reject; route to a transaction-price change event | `VC_CREDIT_EXCEEDS_ESTIMATE` | REQ-TP-016; 606-10-32-42 to 32-44 | none |
| DEV-023 | Activity filter reads the stored pre-ASC 606 column; a contract whose only uploaded rows are modification-created POBs is skipped (L02 §3.2, E23, FX-delivery-06, FX-delivery-19, TC-delivery-21) | Success popup, 0 rows | Any matched row activates its contract | none | REQ-REC-025 | none (UAT step 14 uploads other Contract 3 rows as well) |
| DEV-024 | Backdated and out-of-order events accepted; "latest" = last processed (L02 E09, FX-delivery-09; L03 D-08, P-10, G-03, A-10, FX-08, TC-15; L04 W8, S13, FIX-06, TC-RM-13; L05 DEF-pob-vc-10, G5, S20, TC-pob-vc-14; L06 E-2, E-8, E-9, FX-05 to 07, TC-JE-11, TC-REP-07; L07 C5; L01 FIX-11) | JE for February reversed a March reclass (UAR −104.61); `Previous Period` > `Current Period` | Bitemporal events (effective date, `recorded_at`); replay in effective order; an effect in a closed period posts to the first open period with `origin_period` (ALG-09); "as of" reads | `LATE_EVENT` (WARNING), `EVENT_BEFORE_INCEPTION` | D-19; POL-180; REQ-CLS-004, 006; REQ-RPT-013 | none |
| DEV-025 | `Distinct or Nondistinct` domain unchecked; prospective handler drops other spellings (L01 M-12; L03 D-05, P-04, G-05, A-08, TC-13; L07 C2) | 6.23 of TP disappears from the latest view | Reject at SSP import | `SSP_DISTINCT_FLAG_INVALID` | REQ-POB-003 | none |
| DEV-026 | Blank numeric cells pass setup and SSP validation (L01 M-02, M-03, VR-setup-03, 07, S06, S06b, TC-setup-16) | NaN price: the rest of the contract absorbs TP | Reject | `REQUIRED_VALUE_BLANK` | REQ-DAT-005 | none |
| DEV-027 | Quantity 0 at setup (L01 M-09, S13, TC-setup-17) | NULL unit rates | Reject | `SETUP_QUANTITY_ZERO` | REQ-DAT-005 | none |
| DEV-028 | Zero total SSP at setup (L01 M-10, S12, TC-setup-18) | NULL allocation | Reject | `TOTAL_SSP_ZERO` | POL-077 | none |
| DEV-029 | Percent sanity (L01 M-08, S23, TC-setup-19) | Discount typed as 10: TSSP −70,482 | Reject | `SSP_PERCENT_OUT_OF_RANGE` | REQ-DAT-005 | none |
| DEV-030 | Dates unvalidated (L01 M-01, S26, VR-setup-19; L03 G-04; L06 VR-reports-04, FX-09, TC-REP-06; L02 §2 absent term check) | `Current Period = "abc"` stored; reversed ranges accepted | Reject invalid dates and inverted ranges; warn on delivery outside the POB term | `DATE_INVALID`, `DATE_RANGE_INVERTED`, `PROGRESS_OUTSIDE_POB_TERM` (WARNING) | REQ-DAT-007, REQ-RPT-012 | none |
| DEV-031 | Re-setup of an existing contract resets cumulative state (L01 M-06, S14, FIX-05, TC-setup-22) | New "latest" version with every cumulative field 0 | Reject for an activated contract; changes go through modifications | `SETUP_CONTRACT_EXISTS` | REQ-DAT-017 | none |
| DEV-032 | Contract split across setup files allocated per batch (L01 M-07, S15, AA-08, FIX-06, TC-setup-11; D-17) | C1 POB #4 347.826087 instead of 644.202180 | Setup rows for a contract still in draft add POBs; allocation runs at activation over all POBs (REQ-CON-005). A legacy replay (D-31 mode (b)) activates a contract after the last setup file dated on or before its first activity event. TC-setup-11 expected = TC-setup-01 values | none | POL-214; REQ-ALC-010 | none |
| DEV-033 | Negative quantity at setup: inverted band clamps to Higher (L01 FIX-01, M-11, AA-07, S07, TC-setup-12) | Price −90 inside [−103.5, −76.5] clamped to −103.5 | Never a negative POB (POL-078); returns are progress events | `NEGATIVE_BOOKING_LINE` | D-22; POL-078; REQ-SSP-004 | none |
| DEV-034 | SSP version typing drift; unmatched-SKU message lists SKU names only (L07 C7; L01 VR-setup-09, S09, FIX-07, FIX-08, TC-setup-20; L03 VR-prospective-mod-08) | `1` vs `1.0` fails; "databse" | Typed, effective-dated SSP versions; message names row and key | `SSP_KEY_NOT_FOUND` | REQ-SSP-001, 006; REQ-DAT-006, 007 | none |
| DEV-035 | Template attribute changes on existing POBs silently ignored (L03 D-13, G-07, FX-19; L04 W10, S05, FIX-08, TC-RM-04; L05 DEF-pob-vc-12, G8) | Account 29999 uploaded, 21002 kept | Reject; attribute changes are their own approved events | `MOD_ATTRIBUTE_CONFLICT` | REQ-CON-007 | none (UAT modification files repeat the stored attributes) |
| DEV-036 | Quantity and consideration of opposite signs accepted (L03 G-06, P-15, TC-17) | Consulting catch-up +11.594708 | Reject | `MOD_SIGN_MISMATCH` | REQ-MOD-019 | none |
| DEV-037 | Existing POB id with a different SKU becomes a second POB (L03 D-03, P-14) | Accidental add-POB | Reject; a SKU swap is a termination plus an add | `MOD_POB_SKU_MISMATCH` | REQ-MOD-019 | none |
| DEV-038 | POB-specific price change accepts `Mod Qty` ≠ 0 (L05 DEF-pob-vc-02, G6, S02, TC-pob-vc-08) | Unit SSP diluted 82.5 → 67.5 | Reject | `VC_QUANTITY_NOT_ALLOWED` | legacy 05 FIX-pob-vc-02 | none |
| DEV-039 | Price change may target a VC pseudo-line (L05 DEF-pob-vc-09, G7, S07, TC-pob-vc-12) | Allocation −50 on a zero-SSP line | Reject | `VC_TARGET_INVALID` | REQ-TP-016 | none |
| DEV-040 | No floor on price reductions (L05 DEF-pob-vc-08, G9, S32, TC-pob-vc-17) | Cumulative revenue −11.843712 | Reject unless an approved override exists | `VC_ALLOCATION_NEGATIVE` | 606-10-32-44 | none |
| DEV-041 | Concession on fully billed lines blocked by the negative-remaining-billing gate (L05 DEF-pob-vc-07, SIM-4, S31, S33, TC-pob-vc-16) | "Mod Failed" | Preset: explicit rejection. Native: refund liability or credit-memo expectation (REQ-TP-018; TC-pob-vc-16: CU −60, R 325.185185, refund liability 60) | `MOD_REMAINING_NEGATIVE` | 606-10-32-10; REQ-TP-018 | none |
| DEV-042 | Missing account on a POB silently drops JE lines (L06 VR-reports-11, E-5, FX-03, TC-JE-12; L01 M-13) | C2 UAR line dropped; JE Σ −58.85 | Journal generation fails closed with an exception naming contract, POB and role | `ACCOUNT_MAPPING_MISSING` | REQ-REF-008, REQ-JE-022 | none |
| DEV-043 | Reports crash on an empty database (L07 A7; L02 VR-delivery-10; L03 VR-prospective-mod-10; L04 VR-retro-mod-12; L05 VR-pob-vc-09) | `no such table: Contract_Live` popups at steps 00-01 | Empty reports with a zero row count | none | REQ-RPT-002 | none (no golden test runs a report before step 02) |

### 6.3 Engine state defects

| ID | Defect (sources) | Legacy behaviour [F] | Correct behaviour | Code | Refs | Affected golden tests |
|---|---|---|---|---|---|---|
| DEV-050 | Modification versions carry the previous period's pre-ASC 606 amount; the adjustment report re-posts it (L07 P2, GT-23; L03 D-10, P-08, A-16, FX-10, TC-14; L04 W7, S06, FIX-05, TC-RM-12; L05 DEF-pob-vc-03, S10, TC-pob-vc-13; L06 VR-reports-19, E-1, FX-04, TC-JE-10) | A no-op prospective mod on 2023-02-15 re-posts Dr 5002 66.00, Dr 5003 88.00 / Cr 21001 154.00 in February (L1469-1473, L2966-2979) | Modification and price-change events carry a pre-standard amount of 0; the cumulative field rolls on every event | none | D-24, D-34; POL-005, POL-008; JET-15 | `probe-P2-mod-reposts-pre-asc606-in-delta-je` → B (section 7.3). In UAT steps 08-13 every carried amount is 0, and legacy and corrected oracles agree |
| DEV-051 | SSP-delivered period amount carried on retrospective and price-change versions; `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative` not rolled on modification versions (L07 C1; L03 §3.4; L04 §3.8, §4; L05 §3.3; L06 §4.3) | History export shows stale period measures (S06: 200 / 184 / 75) | Every period measure is 0 on non-delivery events; every Previous measure rolls | none | D-33; REQ-RPT-012 | none (golden tests do not assert these columns) |
| DEV-052 | POB added by a modification stores NULL Original fields and NULL pre-ASC 606 fields (L07 A6; L03 D-15, FX-19; L04 W14, S04b; L02 FX-delivery-19) | Contract 3 POB #5: 11 NULL Original columns; pre-ASC 606 NULL until the next upload | Creation-time values: Original POB Total Selling Price = Mod Billing (1,000.00); Total Qty = Mod Qty (5); SSP Midpoint, Higher and Lower = the modification band (750.00 each); Extended SSP = clamped modification SSP (750.00); Total Contract Price = contract TP after the event (2,600.00); Total Contract SSP = Σ remaining SSP after the event (1,410.00); Allocation = allocation immediately after the event (1,268.1139); Unit SSP 150.0000; Unit Rev Rec 253.6228; pre-ASC 606 fields 0 | none | REQ-ALC-009; REQ-RPT-012 | `final-pob-Contract3-POB5` → B: `Original allocation` 1268.1139 (legacy null) |
| DEV-053 | A modification upload with only new-POB lines excludes the contract's existing POBs from pooling and versioning (L03 D-01, P-01, A-07, FX-02, TC-10; L04 W5, S04, S04b, FIX-04, TC-RM-11; L05 §3.2 consequence 2) | 1 row appended; allocation = billing (170.00) | All POBs of the contract are in scope and the add-POB joins the pool. TC-RM-11 corrected: TP 1,070.00; catch-up POB #1 2.239667, POB #3 1.756602; new POB allocation 135.746269 | none | REQ-MOD-019 | none (UAT step 13 has an existing-POB line) |
| DEV-054 | Pool dropped when the contract's remaining SSP is 0 (L03 D-06, P-05, A-05, FX-06, TC-08, OQ-07; L04 W15) | +50.00 on a fully delivered contract never recognised; TP stays 180.00 | Consideration relating to satisfied performance is recognised in the modification period, apportioned over the satisfied POBs by allocation (POL-104; ALG-01 §2.1.2). TC-08 corrected: revenue +50.00 on the modification date; TP 230.00 | none | 606-10-32-43, 32-44; POL-104 | none |
| DEV-055 | Quantity reduced to 0 strands allocation (L03 D-07, P-11, A-06, FX-07, TC-09; L04 W9, S15, FIX-07, TC-RM-15) | Hardware remaining SSP 27.00, unit SSP inf, remaining allocation 50.338983 | When a POB's remaining quantity reaches 0, its remaining SSP is set to 0 and its remaining allocation joins the pool (preset and native). TC-09 corrected: hardware 0.00 / 0.00; consulting remaining allocation 330.000000; TP 510.00 | `NON_FINITE_AMOUNT` (guard) | 606-10-25-13(a); POL-081 | none |
| DEV-056 | POB-specific price change re-trues untouched lines of the contract (L05 DEF-pob-vc-01, S09, TC-pob-vc-07) | Contract 3 POB #2 +17.157586 when only POB #1 was targeted | Catch-up only on targeted lines. TC-pob-vc-07 corrected: POB #2 catch-up 0, revenue 118.533201, remaining allocation 152.848373; contract position 226.158054 | none | 606-10-32-44; POL-106 | none (at UAT step 09 the latent term is 0 on every untouched line) |
| DEV-057 | Prospective final recompute omits the VC reclass override (L03 D-09, P-17, A-15, FX-09, TC-19; L06 VR-reports-20, E-11, FX-13) | Priced VC line gets reclass 10.00 in the modification path and 0.00 in the delivery path | One contract-position function for every event type; VC elements carry no reclass; total reclass = −position (TC-19: 190.00 in both paths) | none | ALG-02 step 5; POL-121 | none (UAT VC SSP is 0) |
| DEV-058 | Reclass undefined when a contract nets to an asset with zero cumulative SSP delivered (L07 C3; L02 §3.10, 6.4; L04 W14; L05 DEF-pob-vc-15) | NaN reclass stored as NULL | Attribution weights: cumulative SSP delivered, then cumulative revenue (ALG-02 step 5 parity), then POB allocations when both are 0 [J: the native fallback of ALG-02 step 5 applied last so a debit caused by a credit memo is still attributed] | `NON_FINITE_AMOUNT` (guard) | ALG-02; POL-121 | none |
| DEV-059 | Degenerate catch-up when delivered + remaining quantity = 0 (L03 D-14, §3.5) | Catch-up = −cumulative revenue (reverses everything) | Catch-up 0 when cumulative revenue is 0; otherwise reject | `MOD_PROGRESS_UNDEFINED` | 606-10-25-13(b) | none (UAT step 13 POB #4 has revenue 0) |
| DEV-060 | Return after full delivery or after a float residue reverses at an undefined rate (L07 C4; L02 AA-delivery-02, E19, E22, FX-delivery-04, TC-delivery-19, 20) | Reversal 0 after full delivery; −inf after a residue | Under the preset `CURRENT_REMAINING_RATE` (POL-052), when remaining quantity is 0 the average carrying rate (cumulative revenue ÷ cumulative delivered quantity) applies. TC-delivery-19 corrected: −118.533201; TC-delivery-20: −64.420218 | `NON_FINITE_AMOUNT` (guard) | 606-10-55-23; POL-052; REQ-TP-009 | none (the UAT return precedes full delivery, and both rates equal 64.420218) |

### 6.4 Legacy policies retained by the preset

These are not defects under the preset. They are the policy choices behind the C cases. The parity suite asserts the legacy values, and native tenants use the 606 defaults. [F, POLICIES.md section 1]

| ID | Legacy policy (sources) | Preset value | 606 default and effect | Refs | Affected golden tests |
|---|---|---|---|---|---|
| DEV-070 | Material-right exercise processed as a prospective modification that pools released consideration over all remaining POBs (L07 J1, GT-15; L03 A-03, FX-13, TC-04, TC-05, OQ-01; L06 OQ-07; L01 AA-10) | POL-028 `MODIFICATION`; POL-026 `ENTERED_AMOUNT`; POL-212 `KEEP_QUANTITY_CONVENTION`. POB #5 1,268.1139; POB #1 334.3408 → 678.0182; POB #3 catch-up +32.1394 | `CONTINUATION` with `CONVERT_TO_OPTION_RECORD`: POB #5 1,833.767587; POBs #1-#3 stay 334.340803 / 153.413236 / 62.532569; no catch-up; TP 2,600.00 (legacy 03 TC-04) | D-21; 606-10-55-42; DART 11.7 (TRG Q&A 15) | Contract 3 from step 13: `rollforward-13-Contract3`, `rollforward-14-Contract3`, `catchup-13-Contract3-POB3`, `final-pob-Contract3-POB1` to POB5, `je-step-13`, `je-step-14`, `je-month-2023-09`, `je-month-2023-10`, `je-month-2023-full-year` → C (B where DEV-001, 002 or 052 applies) |
| DEV-071 | Retrospective template: full relative-SSP re-allocation with catch-up on every delivered POB, distinct or not; SSP-delivered progress; a no-op retro after a prospective mod reverses the prospective effect (L07 J2, J3, GT-10, GT-14; L04 W1, W2, W4, S1, S3, FIX-01, FIX-02, TC-RM-02, 03, 06; L05 SIM-3; L06 §6.1) | POL-100 `USER_SELECTED_TEMPLATE`; POL-102 `ALL_POBS_FULL_REALLOCATION`; POL-103 `TOTAL_TP`; POL-107 `LEGACY_BY_TEMPLATE` | Engine-proposed route; catch-up only on partially satisfied nondistinct POBs; `REMAINING_TP`; POB measure. TC-RM-02 fix: no catch-up on distinct delivered software. TC-RM-03 fix: catch-up confined to POB #3, which is 0. TC-RM-06 fix: 0 | D-18(b), D-32; 606-10-25-13(a)-(c), 32-43; REQ-MOD-008 | Contract 2 from step 08; Contracts 3 and 4 from step 12 (table 2.3) → C (B where DEV-002 applies) |
| DEV-072 | Modification SSP of added or removed units = consideration clamped into the band, with the negative branch; removed units take out SSP at the clamped price; unit SSP drifts (L07 A5, J4, GT-14; L04 W2, W3, S2, FIX-03; L03 A-02, PR-02; L01 AA-03) | POL-080 `LEGACY_CARRIED_PLUS_FILE_VERSION`; POL-081 `CLAMPED_MOD_PRICE`: Contract 3 step 12 removes 306.00; remaining unit SSP 133.6667 | `D18_DEFAULT`; `CARRIED_UNIT_SSP`: removes 4 × 101.00 = 404.00 | D-18; REQ-SSP-004, REQ-MOD-007, 008 | Contract 3 from step 12 → C |
| DEV-073 | SSP range estimate: stated price inside the inclusive band is the SSP; outside, the nearest bound; midpoint unused (L01 AA-01, AA-03, OK-09; L04 S2; L06 OQ-11; research 04 §4.2) | POL-071 `CONTRACT_PRICE`; POL-072 `NEAREST_BOUND` | Same (parity = 606 default) | DART 7.3.3.6; REQ-SSP-005 | none changed; every `initial_allocation` test is A except the VC rows |
| DEV-074 | Contract asset and unbilled receivable conflated in one account (L01 AA-13, FIX-12; L02 §6.2, AA-delivery-05, FX-delivery-12; L03 A-14, FX-21; L04 S6; L06 §6.2 #1, FX-11) | POL-122 classification with both roles mapped to the POB's Unbilled A/R Account | Roles presented separately; posted totals equal legacy | D-15; 606-10-45-3, 45-4; REQ-REF-008 | `contract_asset` in every `contract_position` test holds the combined amount; no value changed |
| DEV-075 | Net contract asset attributed to POBs by cumulative SSP delivered; VC lines 0 (L02 PR-delivery-10, OQ2) | POL-121 `CUMULATIVE_SSP_DELIVERED` | `POB_DEBIT_POSITIONS`: account strings differ, totals do not | ALG-02 step 5 | none changed |
| DEV-076 | Netting across POBs of different selling entities (L07 J5; L01 AA-14; L04 W11; L06 §6.2 #7) | POL-120 `CONTRACT_ENTITY_BOOK` (FORCED, same as 606) | Same | D-12, D-23; REQ-ENT-004 | none (no UAT contract spans entities) |
| DEV-077 | Variable consideration as a negative-price pseudo-line with delivery quantity and no revenue (L07 A3, A4, J6, GT-02, GT-03; L01 AA-06, PAR-03; L02 PR-delivery-07; L05 SIM-1, SIM-2, FIX-pob-vc-09, 13) | REQ-TP-016; POL-040 `ENTERED_AMOUNT`; POL-041 `NOT_APPLIED`; POL-042 `NOT_ENFORCED`; POL-043 `DELTA`; POL-213 | Estimate versions with a constraint; native policies reject VC pseudo-lines as POBs | D-20, D-22; 606-10-32-5 to 32-14 | `setup-alloc-Contract2-VC1`, `setup-alloc-Contract4-VC1`, `final-pob-Contract2-VC1`, `final-pob-Contract4-VC1` → C |
| DEV-078 | Returns: actual returns only; reversal at the current remaining unit rate; returned units restore remaining quantity (L07 C4, GT-08; L01 AA-07; L02 AA-delivery-01, 02, FX-delivery-04, 05, TC-delivery-22) | POL-051 `ACTUAL_RETURNS_ONLY`; POL-052 `CURRENT_REMAINING_RATE`; POL-053 `RESTORE_REMAINING_QUANTITY` | `EXPECTED_RETURNS`; `AVERAGE_CARRYING_RATE`; `REDUCE_CONTRACT_QUANTITY` | D-22; 606-10-55-22 to 55-29; REQ-TP-009 | Contract 1 from step 07 → C (B where DEV-002 applies) |
| DEV-079 | Modification route chosen by template button; no 25-12 separate-contract path (L03 A-01, FX-01, TC-07; L04 S1; L07 J3) | POL-100 `USER_SELECTED_TEMPLATE`; POL-101 n/a | Engine proposes, preparer confirms; 25-12 price test | 606-10-25-12, 25-13; REQ-DAT-003 | `catchup-11-Contract3-POB3` and step 11 contract values stay A (25-12 fails in the UAT, section 2.4) |
| DEV-080 | Distinctness is a SKU attribute; no series flag (L01 AA-11; L03 A-04, FX-04, FX-05, OQ-06; L02 §6.2) | POL-211 `SINGLE_POB` | `REVIEW_QUEUE` questionnaire | 606-10-25-14(b), 25-15; REQ-MIG-006 | none changed |
| DEV-081 | Billing entries not produced by the subledger (L07 A9; L02 AA-delivery-05, OQ4; L06 OQ-01) | POL-004 `ERP` | Same | D-13 | none |
| DEV-082 | Progress = uploaded units only; POB dates unused (L01 AA-12; L02 §6.2, FX-delivery-14, 15; L03 A-13, FX-17; L04 S3) | POL-091 `UNITS_DELIVERED` | Measure per revenue policy template | 606-10-25-31 to 25-37 | none changed |
| DEV-083 | POB-specific price change moves the billing plan by the change (L05 SIM-4, P-pob-vc-06) | Retained (legacy L2372-2375) | Price change decoupled from invoicing (REQ-TP-018) | 606-10-32-10 | `tp_billing_basis` of Contract 2 from step 09 (already C through DEV-071) |
| DEV-084 | Pre-ASC 606 revenue keyed per event, with no ERP tie-out (L06 §6.2 #6, OQ-05; L02 OQ5) | POL-008 `PRE_STANDARD_EVENTS` | Same | D-24, D-34 | adjustment views of the journal tests (values per DEV-002) |
| DEV-085 | Step 1 and allocation features absent: combination, residual, discount exception, VC estimation and constraint, financing, noncash consideration, consideration payable, unpriced change orders, 32-45 routing (L01 AA-04, 05, 08, 09, FIX-13; L03 A-11, A-12, FX-16, FX-18; L04 S4, S5, W12, FIX-02, FIX-11; L05 SIM-5, SIM-6, DEF-pob-vc-13, 14) | POL-015, POL-016, POL-076 disabled; POL-075, POL-105, POL-106 not exercised | Enabled natively; the UAT exercises none | 606-10-25-9, 32-5 to 32-45 | none changed |

### 6.5 Platform and controls

| ID | Defect (sources) | Legacy behaviour [F] | Correct behaviour | Refs | Affected golden tests |
|---|---|---|---|---|---|
| DEV-090 | "Latest" = text `MAX(Processing Time Log)` with no transaction (L07 C5; L01 §4.3; L06 VR-reports-13, FX-07) | Concurrent use or clock changes corrupt version selection | Per-contract event sequence; `as_of` and `known_at` reads | D-19, D-43; REQ-RPT-013 | none |
| DEV-091 | SQL built with f-strings (L07 C6; L01 VR-setup-20, FIX-16; L06 VR-reports-05, 06, E-10, FX-08, TC-REP-04, 05) | `x" OR 1=1 OR "x` returns every contract | Parameterised queries; contract picker | REQ-RPT-012 | none |
| DEV-092 | Restore deletes the live database before verifying the backup; backup directory never created (L01 VR-setup-14, 15, S18, S19, FIX-15, TC-setup-23) | Data loss | Tenant snapshot, restore only to a sandbox | D-01 | none |
| DEV-093 | Purge ignores Cancel, reports success on 0 rows and breaks the reclass chain (L01 VR-setup-19, 20, S20, FIX-16, TC-setup-24; L06 E-7) | Chain broken; later JEs reverse non-existent reclasses | Void a contract through an approval; posted lines reverse | D-01; REQ-JE-006 | none |
| DEV-094 | Append-from-another inserts positionally with no de-duplication (L01 VR-setup-17, S17, FIX-17, TC-setup-25) | 24 → 48 → 72 rows | Legacy database import by column name; importing the same file twice creates no duplicates | D-31; REQ-MIG-004 | none |
| DEV-095 | Client-side licence gating and end-of-life shutdown (L07 C8; L01 VR-setup-12, 13, FIX-14; L06 FX-16) | App quits after 2025-12-31 | No licence keys | D-01 | none |
| DEV-096 | No user identity, approval, reason code, source-file hash or 32-40 evidence on events (L01 AA-17, FIX-18; L02 FX-delivery-17; L03 FX-15; L04 W13, FIX-10; L05 DEF-pob-vc-14, FIX-pob-vc-13) | Only `Processing Time Log` | Audited commands, maker-checker, file SHA-256, row lineage | D-30, D-43; REQ-PLT-019, REQ-DAT-001 | none |
| DEV-097 | JE output lacks entity, currency, period, JE id and dimensions; the grouping column mixes contract and POB keys (L07 A10; L06 FX-10; research 07 L10) | Balances only in total | Journal data model per REQ-JE-003; legacy grain kept as a report view (POL-006) | D-16; REQ-JE-003, 011 | none |
| DEV-098 | Full POB snapshot per event (L07 A8; L06 P-REP-04) | Rows multiply with contract size | Event-sourced engine; the 71-column history export reproduces snapshot rows | D-10, D-33; REQ-RPT-012 | none |
| DEV-099 | Windows EFS encryption on SSP load; export UX: overwrite, "File Saved", index column (L07 §2; L01 §1.3; L06 FX-15; research 99 M-ARCH-10) | Unverified on Windows; stray files | Server-side encryption; stamped exports without an index column | REQ-JE-011, REQ-RPT-024 | none |

---

## 7. Corrected expected values for B cases

`deviations.json` holds the complete expected objects: every `by_account` row, totals and `line_items`. This section lists what differs from legacy, so a reviewer can approve each difference.

### 7.1 Journal tests (DEV-001, DEV-002)

Posting rule `EXACT-CUM` (PJR-1, D-11a). Every listed difference is one cent and belongs to the DEV-002 class approved once (D-17a). Line differences use amount sign + debit, − credit; "adj." = Revenue Adjustment view. Lines not listed equal legacy.

| Test | Line key | Account | Legacy gross | Expected gross | Legacy adj. | Expected adj. |
|---|---|---|---|---|---|---|
| `je-step-08` | Contract 2 | 15002 | 23.87 | 23.86 | 23.87 | 23.86 |
| `je-step-08` | Contract 2 POB #1 Hardware 1 | 5001 | −13.38 | −13.37 | −13.38 | −13.37 |
| `je-month-2023-05` | Contract 2 | 15002 | 5.19 | 5.18 | 5.19 | 5.18 |
| `je-step-14`, `je-month-2023-10` | Contract 1 POB #2 Software 1 | 5002 | −92.53 | −92.54 | −92.53 | −92.54 |
| `je-step-14`, `je-month-2023-10` | Contract 1 POB #3 Consulting 1 | 5003 | −43.02 | −43.01 | −43.02 | −43.01 |
| `je-step-14`, `je-month-2023-10` | Contract 2 | 15002 | −90.19 | −90.18 | −90.19 | −90.18 |
| `je-step-14`, `je-month-2023-10` | Contract 3 | 21001 | 2,351.91 | 2,351.92 | 2,351.91 | 2,351.92 |
| `je-step-14`, `je-month-2023-10` | Contract 3 POB #3 Consulting 1 | 5003 | −94.67 | −94.68 | −94.67 | −94.68 |
| `je-step-14`, `je-month-2023-10` | Contract 4 POB #1 Hardware 1 | 5001 | −359.76 | −359.77 | −359.76 | −359.77 |
| `je-step-14`, `je-month-2023-10` | Contract 4 POB #3 Consulting 1 | 5003 | −293.93 | −293.92 | −293.93 | −293.92 |
| `je-month-2023-full-year` | Contract 3 POB #3 Consulting 1 | 5003 | −189.34 | −189.35 | 10.66 | 10.65 |
| `je-month-2023-full-year` | Contract 4 POB #3 Consulting 1 | 5003 | −293.93 | −293.92 | −293.93 | −293.92 |

Causes [F]: in `je-step-08` (2023-05-01 to 2023-05-15) and `je-month-2023-05`, legacy rounds the 13.3761 catch-up component and the netting components separately, where PJR-1 posts differences of rounded cumulative amounts. The October lines are explained in section 4.2. The full-year lines are the completion values of Contract 3 POB #3 (A 189.35) and Contract 4 POB #3 (A 293.92).

Totals and changed `by_account` rows:

| Test | Gross legacy Dr / Cr | Gross expected Dr / Cr | Adj. legacy Dr / Cr | Adj. expected Dr / Cr | Changed accounts (expected) |
|---|---|---|---|---|---|
| `je-step-08` | 23.87 / 23.87 | 23.86 / 23.86 | 23.87 / 23.87 | 23.86 / 23.86 | 5001 Cr 13.37, 15002 Dr 23.86 |
| `je-month-2023-05` | 10.50 / 10.49 | 10.49 / 10.49 | 10.50 / 10.49 | 10.49 / 10.49 | 15002 Dr 5.18 |
| `je-step-14`, `je-month-2023-10` | 5,043.84 / 5,043.85 | 5,043.85 / 5,043.85 | 5,043.84 / 5,043.85 | 5,043.85 / 5,043.85 | 5001 Cr 2,060.35, 5002 Cr 1,108.63, 5003 Cr 1,784.69, 15002 Cr 90.18, 21001 Dr 2,990.37 |
| `je-month-2023-full-year` | 5,700.00 / 5,700.00 | 5,700.00 / 5,700.00 | 5,208.63 / 5,208.63 | 5,208.62 / 5,208.62 | adj. 5003 Dr 12.62 / Cr 1,703.64; gross by-account unchanged (5003 Cr 1,979.02) |

Every B journal test keeps the legacy `lines` count in both views (3, 18 and 17 lines). Rev 1.0 catch-up lines on untouched POBs (steps 10, 11 and 13) no longer occur.

Tests that left B in rev 1.1 now expect the legacy values: `je-step-04` and `je-month-2023-01` (gross 354.54 / 354.54, adj. 240.22 / 240.22; CHK-022, CHK-020), `je-step-05` and `je-month-2023-02` (224.03 / 224.03, adj. 254.81 / 254.81), `je-step-06` and `je-month-2023-03` (263.61 / 263.61), `je-step-10` and `je-month-2023-06` (5.30 / 5.30, 2 lines), `je-step-11` and `je-month-2023-07` (6.99 / 6.99, 2 lines), `je-step-12` and `je-month-2023-08` (58.40 / 58.40), `je-step-13` and `je-month-2023-09` (32.14 / 32.14, 2 lines).

### 7.2 POB test (DEV-052)

| Test | Field | Legacy | Expected |
|---|---|---|---|
| `final-pob-Contract3-POB5` | `Original allocation` | null | 1268.1139 |
| `final-pob-Contract3-POB5` | other 8 fields | as legacy | 1268.1139 / 5.0000 / 1268.1139 / 1000.0000 / 0.0000 / 0.0000 / −268.1139 / 0.0000 |

### 7.3 Probes

Each probe upload asserts `import_status` through the DG-PAR-06 mapping (section 2.2), plus `error_code`, `findings[]` and, for a refused upload, the problem slug and `errors[0].rule_id`. Journal values follow PJR-1 (`EXACT-CUM`).

| Probe | Class | Expected (eRev Cloud, legacy-parity preset) | Legacy observed |
|---|---|---|---|
| P1 blank memo (DEV-010) | B | `import_status` `COMMITTED_WITH_FINDINGS` (E-40 `COMMITTED` with at least one `WARNING` finding). Findings `PROGRESS_MEMO_BLANK` WARNING on worksheet rows 3 (Contract 1 POB #2 Software 1, Memo 3) and 4 (Contract 1 POB #3 Consulting 1, Memo 3); the rows are processed (D-30a). Versions 8 → 16. Latest: POB #1 delivered 2.0000, billed 100.0000, revenue 128.8404, remaining qty 3.0000, remaining allocation 193.2607; POB #2 1.0000 / 100.0000 / 118.5332, pre-ASC 606 66.0000 (cumulative 66.0000), remaining 1.0000 / 118.5332; POB #3 0.5000 / 100.0000 / 48.3152, pre-ASC 606 88.0000 (88.0000), remaining 0.5000 / 48.3152; period 2023-01-31. January gross JE 6 lines, Dr / Cr 354.54: Cr 5001 187.69, Cr 5002 118.53, Cr 5003 48.32, Dr 15002 58.85, Dr 21001 295.69 (= `je-step-04`; CHK-022) | Success popup; POB #2 and #3 record 0 delivery and 0 billing; January gross Dr 15001 28.84, 15002 58.85, 21001 100.00 / Cr 5001 187.69 |
| P2 pre-ASC 606 re-posted (DEV-050) | B | February gross JE 0 lines. February adjustment JE 0 lines. January adjustment JE 6 lines, Dr / Cr 240.22: Cr 5001 187.69, Cr 5002 52.53, Dr 5003 39.68, Dr 15002 58.85, Dr 21001 141.69 (CHK-020). Latest after the 2023-02-15 no-op modification: POB #2 pre-ASC 606 period amount 0.0000 (cumulative 66.0000); POB #3 0.0000 (88.0000); other watched values as legacy | February adjustment Dr 5002 66.00, Dr 5003 88.00 / Cr 21001 154.00; period amounts 66 / 88 carried |
| P3 over-delivery (DEV-020) | A | `import_status` `REJECTED` (E-40 `INVALID`); `error_code` `PROGRESS_OVER_DELIVERY` = code of the first `ERROR` finding. Findings: one `PROGRESS_OVER_DELIVERY` ERROR on the aggregated key `Contract 1 POB #1 Hardware 1`, `worksheet_row` 2, `worksheet_rows` [2, 6] (delivery 6 + 1); no over-billing finding (billing 100.00 against remaining 500.00). Detail names `Contract 1 POB #1 Hardware 1`, requested 7, remaining 5; versions 8 → 8; POB #1 unchanged: delivered 0.0000, billed 0.0000, revenue 0.0000, remaining qty 5.0000, remaining allocation 322.1011, period 2023-01-01 | Rejected with a generic message; 8 rows before and after |
| P4 duplicate upload (DEV-011) | B | First 2.28 upload `COMMITTED` (E-40 `COMMITTED`, no findings). Second `REJECTED`: refused at upload with HTTP 409 problem `duplicate-import` and `errors[0].rule_id` `IMPORT_FILE_DUPLICATE` (= `error_code`); no `import_upload` row and no finding row; SHA-256 `37a9b8cee4a46385c60ebe8afa26e3aae44554fb7395baef1884ca17b396d547`. Versions 36 → 36. February gross JE 6 lines, Dr / Cr 224.03: Cr 5001 175.71, Cr 5003 48.32, Dr 21001 112.74, Dr 21002 111.29 (= `je-step-05`). Latest: C1 POB #1 delivered 3.0000, billed 200.0000, revenue 193.2607, remaining 2.0000 / 128.8404; C3 POB #3 0.5000 / 200.0000 / 48.3152, pre-ASC 606 200.0000 (200.0000), remaining 0.5000 / 48.3152; C4 POB #1 2.0000 / 150.0000 / 111.2940, pre-ASC 606 150.0000 (150.0000), remaining 6.0000 / 333.8821; period 2023-02-28 | Both uploads accepted; February gross 448.06; C1 POB #1 delivered cumulative 4.0 |

---

## 8. Classification of every golden test

Order follows `golden-tests.json`. DEV lists the primary id first. POL refs are the policies whose values the case depends on.

| # | Test id | Kind | Class | DEV | POL refs |
|---|---|---|---|---|---|
| 1 | `je-step-02` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 2 | `je-step-03` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 3 | `je-step-04` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 4 | `je-step-05` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 5 | `je-step-06` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 6 | `je-step-07` | journal_entry_totals | C | DEV-078 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-051, POL-052, POL-053 |
| 7 | `je-step-08` | journal_entry_totals | B | DEV-002, DEV-071 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-100, POL-102, POL-103, POL-107 |
| 8 | `je-step-09` | journal_entry_totals | C | DEV-071 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-100, POL-102, POL-103, POL-107 |
| 9 | `je-step-10` | journal_entry_totals | C | DEV-078 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-051, POL-052, POL-053 |
| 10 | `je-step-11` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 11 | `je-step-12` | journal_entry_totals | C | DEV-071, DEV-072 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 12 | `je-step-13` | journal_entry_totals | C | DEV-071, DEV-072, DEV-070 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 13 | `je-step-14` | journal_entry_totals | B | DEV-001, DEV-002, DEV-078, DEV-071, DEV-072, DEV-070 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-026, POL-028, POL-051, POL-052, POL-053, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 14 | `rollforward-02-Contract1` | contract_position | A | - | - |
| 15 | `rollforward-02-Contract2` | contract_position | A | - | - |
| 16 | `rollforward-03-Contract1` | contract_position | A | - | - |
| 17 | `rollforward-03-Contract2` | contract_position | A | - | - |
| 18 | `rollforward-03-Contract3` | contract_position | A | - | - |
| 19 | `rollforward-03-Contract4` | contract_position | A | - | - |
| 20 | `rollforward-04-Contract1` | contract_position | A | - | - |
| 21 | `rollforward-04-Contract2` | contract_position | A | - | - |
| 22 | `rollforward-04-Contract3` | contract_position | A | - | - |
| 23 | `rollforward-04-Contract4` | contract_position | A | - | - |
| 24 | `rollforward-05-Contract1` | contract_position | A | - | - |
| 25 | `rollforward-05-Contract2` | contract_position | A | - | - |
| 26 | `rollforward-05-Contract3` | contract_position | A | - | - |
| 27 | `rollforward-05-Contract4` | contract_position | A | - | - |
| 28 | `rollforward-06-Contract1` | contract_position | A | - | - |
| 29 | `rollforward-06-Contract2` | contract_position | A | - | - |
| 30 | `rollforward-06-Contract3` | contract_position | A | - | - |
| 31 | `rollforward-06-Contract4` | contract_position | A | - | - |
| 32 | `rollforward-07-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 33 | `rollforward-07-Contract2` | contract_position | A | - | - |
| 34 | `rollforward-07-Contract3` | contract_position | A | - | - |
| 35 | `rollforward-07-Contract4` | contract_position | A | - | - |
| 36 | `rollforward-08-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 37 | `rollforward-08-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 38 | `rollforward-08-Contract3` | contract_position | A | - | - |
| 39 | `rollforward-08-Contract4` | contract_position | A | - | - |
| 40 | `rollforward-09-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 41 | `rollforward-09-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 42 | `rollforward-09-Contract3` | contract_position | A | - | - |
| 43 | `rollforward-09-Contract4` | contract_position | A | - | - |
| 44 | `rollforward-10-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 45 | `rollforward-10-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 46 | `rollforward-10-Contract3` | contract_position | A | - | - |
| 47 | `rollforward-10-Contract4` | contract_position | A | - | - |
| 48 | `rollforward-11-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 49 | `rollforward-11-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 50 | `rollforward-11-Contract3` | contract_position | A | - | - |
| 51 | `rollforward-11-Contract4` | contract_position | A | - | - |
| 52 | `rollforward-12-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 53 | `rollforward-12-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 54 | `rollforward-12-Contract3` | contract_position | C | DEV-071, DEV-072 | POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 55 | `rollforward-12-Contract4` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 56 | `rollforward-13-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 57 | `rollforward-13-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 58 | `rollforward-13-Contract3` | contract_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 59 | `rollforward-13-Contract4` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 60 | `rollforward-14-Contract1` | contract_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 61 | `rollforward-14-Contract2` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 62 | `rollforward-14-Contract3` | contract_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 63 | `rollforward-14-Contract4` | contract_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 64 | `final-pob-Contract1-POB1` | pob_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 65 | `final-pob-Contract1-POB2` | pob_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 66 | `final-pob-Contract1-POB3` | pob_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 67 | `final-pob-Contract1-POB4` | pob_position | C | DEV-078 | POL-051, POL-052, POL-053 |
| 68 | `final-pob-Contract2-POB1` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 69 | `final-pob-Contract2-POB2` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 70 | `final-pob-Contract2-POB3` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 71 | `final-pob-Contract2-VC1` | pob_position | C | DEV-077 | POL-040, POL-041, POL-043 |
| 72 | `final-pob-Contract3-POB1` | pob_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 73 | `final-pob-Contract3-POB2` | pob_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 74 | `final-pob-Contract3-POB3` | pob_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 75 | `final-pob-Contract3-POB4` | pob_position | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 76 | `final-pob-Contract3-POB5` | pob_position | B | DEV-052, DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 77 | `final-pob-Contract4-POB1` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 78 | `final-pob-Contract4-POB2` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 79 | `final-pob-Contract4-POB3` | pob_position | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 80 | `final-pob-Contract4-VC1` | pob_position | C | DEV-077 | POL-040, POL-041, POL-043 |
| 81 | `je-month-2023-01` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 82 | `je-month-2023-02` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 83 | `je-month-2023-03` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 84 | `je-month-2023-04` | journal_entry_totals | C | DEV-078 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-051, POL-052, POL-053 |
| 85 | `je-month-2023-05` | journal_entry_totals | B | DEV-001, DEV-002, DEV-071 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-100, POL-102, POL-103, POL-107 |
| 86 | `je-month-2023-06` | journal_entry_totals | C | DEV-078 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-051, POL-052, POL-053 |
| 87 | `je-month-2023-07` | journal_entry_totals | A | - | POL-001, POL-002, POL-003, POL-005, POL-006 |
| 88 | `je-month-2023-08` | journal_entry_totals | C | DEV-071, DEV-072 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 89 | `je-month-2023-09` | journal_entry_totals | C | DEV-071, DEV-072, DEV-070 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 90 | `je-month-2023-10` | journal_entry_totals | B | DEV-001, DEV-002, DEV-078, DEV-071, DEV-072, DEV-070 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-026, POL-028, POL-051, POL-052, POL-053, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 91 | `je-month-2023-full-year` | journal_entry_totals | B | DEV-002, DEV-078, DEV-071, DEV-072, DEV-070 | POL-001, POL-002, POL-003, POL-005, POL-006, POL-026, POL-028, POL-051, POL-052, POL-053, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 92 | `catchup-08-Contract2-POB1` | cumulative_catchup | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 93 | `catchup-08-Contract2-POB3` | cumulative_catchup | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 94 | `catchup-09-Contract2-POB1` | cumulative_catchup | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 95 | `catchup-10-Contract1-POB3` | cumulative_catchup | C | DEV-078 | POL-051, POL-052, POL-053 |
| 96 | `catchup-11-Contract3-POB3` | cumulative_catchup | A | - | POL-080, POL-100, POL-103 |
| 97 | `catchup-12-Contract3-POB2` | cumulative_catchup | C | DEV-071, DEV-072 | POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 98 | `catchup-12-Contract3-POB3` | cumulative_catchup | C | DEV-071, DEV-072 | POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 99 | `catchup-12-Contract4-POB1` | cumulative_catchup | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 100 | `catchup-12-Contract4-POB2` | cumulative_catchup | C | DEV-071 | POL-100, POL-102, POL-103, POL-107 |
| 101 | `catchup-13-Contract3-POB3` | cumulative_catchup | C | DEV-071, DEV-072, DEV-070 | POL-026, POL-028, POL-080, POL-081, POL-100, POL-102, POL-103, POL-107 |
| 102 | `setup-alloc-Contract1-POB1` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 103 | `setup-alloc-Contract1-POB2` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 104 | `setup-alloc-Contract1-POB3` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 105 | `setup-alloc-Contract1-POB4` | initial_allocation | A | - | POL-026, POL-070, POL-071, POL-072 |
| 106 | `setup-alloc-Contract2-POB1` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 107 | `setup-alloc-Contract2-POB2` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 108 | `setup-alloc-Contract2-POB3` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 109 | `setup-alloc-Contract2-VC1` | initial_allocation | C | DEV-077 | POL-040, POL-041, POL-043, POL-070, POL-071, POL-072 |
| 110 | `setup-alloc-Contract3-POB1` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 111 | `setup-alloc-Contract3-POB2` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 112 | `setup-alloc-Contract3-POB3` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 113 | `setup-alloc-Contract3-POB4` | initial_allocation | A | - | POL-026, POL-070, POL-071, POL-072 |
| 114 | `setup-alloc-Contract4-POB1` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 115 | `setup-alloc-Contract4-POB2` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 116 | `setup-alloc-Contract4-POB3` | initial_allocation | A | - | POL-070, POL-071, POL-072 |
| 117 | `setup-alloc-Contract4-VC1` | initial_allocation | C | DEV-077 | POL-040, POL-041, POL-043, POL-070, POL-071, POL-072 |
| 118 | `shipped-db-equivalence` | point_in_time_equivalence | A | - | - |
| 119 | `probe-P1-blank-memo-drops-progress-rows` | legacy_probe | B | DEV-010 | - |
| 120 | `probe-P2-mod-reposts-pre-asc606-in-delta-je` | legacy_probe | B | DEV-050 | POL-005, POL-008 |
| 121 | `probe-P3-over-delivery-validation` | legacy_probe | A | DEV-020 | - |
| 122 | `probe-P4-duplicate-upload-double-counts` | legacy_probe | B | DEV-011 | - |

---

## 9. Summary and sign-off

### 9.1 Counts per classification

| Kind | A | B | C | Total |
|---|---|---|---|---|
| contract_position | 29 | 0 | 21 | 50 |
| journal_entry_totals | 10 | 5 | 9 | 24 |
| pob_position | 0 | 1 | 16 | 17 |
| initial_allocation | 14 | 0 | 2 | 16 |
| cumulative_catchup | 1 | 0 | 9 | 10 |
| legacy_probe | 1 | 3 | 0 | 4 |
| point_in_time_equivalence | 1 | 0 | 0 | 1 |
| **Total** | **56** | **9** | **57** | **122** |

Changes from rev 1.0 (posting rule `EXACT-CUM`, D-11a): `je-step-04`, `je-step-05`, `je-step-06`, `je-step-11`, `je-month-2023-01`, `je-month-2023-02`, `je-month-2023-03` and `je-month-2023-07` move B → A; `je-step-10`, `je-step-12`, `je-step-13`, `je-month-2023-06`, `je-month-2023-08` and `je-month-2023-09` move B → C, because their only departure from legacy was a one-cent POSTED-ALLOC artefact and their contracts are in a preset policy state. No other kind changes.

C cases by primary DEV [F]: DEV-071, 36 cases (Contract 2 from step 08; Contracts 3 and 4 from step 12, with DEV-072 on Contract 3 and DEV-070 from step 13); DEV-078 Contract 1 from step 07, 17; DEV-077 VC rows, 4. The 9 C journal tests are `je-step-07`, `je-step-09`, `je-step-10`, `je-step-12`, `je-step-13`, `je-month-2023-04`, `je-month-2023-06`, `je-month-2023-08` and `je-month-2023-09`.

### 9.2 Tests requiring revenue-accountant sign-off (B, 9; five approval units)

Approval units follow D-17a and are recorded in `deviations.json` `signoff_units`. `signoff_required` lists the 9 B test ids (DG-PAR-08).

| Unit | Approval | Tests | DEV | What the accountant approves |
|---|---|---|---|---|
| DEV-002 class | Once for the class (D-17a) | `je-step-08`, `je-step-14`, `je-month-2023-05`, `je-month-2023-10`, `je-month-2023-full-year` | DEV-002; DEV-001 is the primary id of `je-step-14`, `je-month-2023-05` and `je-month-2023-10` | One-cent line differences between legacy report rounding and amounts posted under D-11a (section 7.1). This includes the balanced corrected entries of section 4.2, which replace the May and October legacy lines that were out by ±0.01. `build_deviations.py` regenerates the case list mechanically |
| DEV-052 | Per case | `final-pob-Contract3-POB5` | DEV-052 | `Original allocation` 1268.1139 instead of null |
| DEV-010 | Per case | `probe-P1-blank-memo-drops-progress-rows` | DEV-010 | Rows processed with WARNING findings instead of silently dropped (D-30a) |
| DEV-050 | Per case | `probe-P2-mod-reposts-pre-asc606-in-delta-je` | DEV-050 | No February adjustment lines |
| DEV-011 | Per case | `probe-P4-duplicate-upload-double-counts` | DEV-011 | Second upload refused at upload; single-upload state |

### 9.3 Supervisor decisions applied (rev 1.1)

| Decision | Effect on values or classes | Section |
|---|---|---|
| D-11a posting composition (B1-001; O-3; OQ-D1, OQ-D2) | Posting rule `EXACT-CUM`. 14 journal tests leave B (8 → A, 6 → C); P1, P2 and P4 journal values equal legacy | 0, 3, 4.2, 7.1, 7.3, 8, 9.1 |
| D-17a cent-difference class (B1-039; O-2) | DEV-002 approved once; `signoff_units` added | 9.2 |
| D-30a findings (B1-019; O-1; OQ-D3) | Blank memo = `PROGRESS_MEMO_BLANK` WARNING, rows processed; no value change | 5, 6.2, 7.3 |
| DG-PAR-06 import outcome mapping (B1-002) | Probe `import_status` derived from E-40 state and problem responses; P3 and P4 carry `findings` | 2.2, 5, 7.3 |
| D-73 identifier authority | Finding codes are cited from 04 §15.4; no value change | 5 |
| D-75 rulings (OQ-D4 to OQ-D10) | Recommended defaults adopted; no value change | 11 |

The 57 C cases need no deviation sign-off. They are approved through the legacy-parity preset (REQ-POL-005, POL approval code CFG).

---

## 10. Gaps closed

| Gap (research 99) | How this document closes it |
|---|---|
| C-08 golden-test tolerance | One rule applying D-17: full-precision engine values within 1e-4 of 4-dp expectations, posted journal lines exact to the cent, codes and counts exact (section 2.2). Separate float-parity and production modes are unnecessary because the oracle is exact |
| C-10 legacy validation misstated | VR-delivery-09 tests remaining, not cumulative, balances. Over-returns and over-refunds were accepted, and the corrected checks are `RETURN_EXCEEDS_DELIVERED` and `REFUND_EXCEEDS_BILLED` (DEV-021) |
| C-14 delta posting sequencing (parity side) | The adjustment format is asserted in all 24 journal tests (PJR-4). The GT-07 January values equal legacy and POLICIES.md CHK-020 (`je-step-04`, `je-month-2023-01`; section 3) |
| C-18 harness environment provenance | The exact oracle reproduces the pandas 2.2.3 golden values within 2.3e-13, so the golden numbers do not depend on the float library version |
| C-07 residual policy (parity side) | Parity journal expectations use ALG-01 §2.1.3 cumulative rounding of the exact cumulative revenue, bounded by the largest-remainder allocation and aligned to it at completion (posting rule `EXACT-CUM`, D-11a; sections 3, 7.1) |
| M-ARCH-07 machine-readable answer keys (parity part) | `deviations.json` gives expected values for all 122 golden tests, generated deterministically |
| M-ARCH-08 evidence reproducibility and id hygiene | Scripts live in `research-harness/deviations/` (not scratch) with a rerun recipe and self-checks. DEV-NNN ids do not collide with probes P1-P4, invariants P1-P14 or priorities |
| M-ARCH-09 legacy repository contamination | The deviation scripts read workbooks only from `legacy-harness/erev_copy` with SHA-256 checks and never import `eRev.py` |
| M-PM-02 legacy-parity mode (values) | Every golden case is classified under the preset with corrected values; the shipped-DB case is tied to D-31 reconciliation (REQ-MIG-003) |
| M-RA-01 policy register (parity cross-check) | Every POL whose `Parity` value differs from `606` and that the golden suite exercises is mapped to DEV entries and tests (table 2.3, section 6.4) |
| U-08 vendor-blog authority (parity scope) | Corrected behaviours cite Codification paragraphs, POLICIES.md and REQ ids rather than vendor blogs |

---

## 11. Open questions for supervisor

| Id | Question | Recommended default [J] | Status and ruling |
|---|---|---|---|
| OQ-D1 | ALG-01 composition (O-3): keep round(A × f) with A the largest-remainder allocation (19 journal B tests, including one-cent catch-ups on untouched POBs), or amend to contract-level cumulative rounding (7 B tests)? | Keep ALG-01 and approve DEV-002 as one class (O-2). One schedule rule for native and parity books is simpler to build and audit | **Resolved by D-75** (with D-11a, D-17a). ALG-01 §2.1.3 as published governs native and parity books: C_t = round(X × f_t), bounded by A and equal to A at completion (posting rule `EXACT-CUM`, PJR-1). round(A × f) is retired and contract-level `LR-CUM` is not adopted. DEV-002 is approved once as a class. Result: 5 journal B tests |
| OQ-D2 | For preset state, PJR-1 recomputes A by largest remainder at each as-of date from exact allocations, with f = exact cumulative revenue ÷ exact allocation. Deliveries do not change exact allocations, so this equals recomputing at setup and modification events. If ALG-04 or ALG-10 (not yet published) define a carried posted allocation or another progress basis for legacy templates, values may change | Adopt PJR-1 as written; if POLICIES.md publishes a different basis, rerun `build_deviations.py` after updating `journal.posted_cumulative` | **Resolved by D-75.** PJR-1 is adopted as restated for `EXACT-CUM`: A is recomputed by largest remainder at each as-of date and serves only as the bound and the completion value; f = exact cumulative revenue ÷ exact allocation. POLICIES.md ALG-04 (catch-up = round(A′_p × f′_p) − R_p with A′_p exact) and ALG-10 as published use the exact allocation, consistent with PJR-1. If ENGINE_SPEC publishes another basis for legacy templates, the supervisor reruns `build_deviations.py` |
| OQ-D3 | Blank memo on a v1 progress row: WARNING with the row processed, or ERROR blocking the file (D-30 literal)? (O-1) | WARNING (REQ-REC-025, REQ-DAT-005) | **Resolved by D-75** (with D-30a). `PROGRESS_MEMO_BLANK` WARNING; rows processed |
| OQ-D4 | Duplicate file: always reject, or allow an explicit "process again" confirmation (legacy 02 FX-delivery-08)? | Always reject; corrections go through reversal events (REQ-JE-006) | **Resolved by D-75.** Always reject. The upload is refused with problem `duplicate-import` and `errors[0].rule_id` `IMPORT_FILE_DUPLICATE` (05 IPL-01); corrections go through reversal events |
| OQ-D5 | Creation-time Original fields for POBs added by a modification | The values in DEV-052 (only `Original allocation` is asserted by the golden suite) | **Resolved by D-75.** The DEV-052 values are adopted |
| OQ-D6 | Journal tests are C when any contract with a line is in a policy state (conservative). `je-step-07` and `je-month-2023-04` are C although a 606-default computation of the April return gives the same amounts | Keep conservative: ALG-06 native posting of returns (refund liability) is not yet published | **Resolved by D-75.** The conservative rule is kept. Under rev 1.1 it also classifies `je-step-10`, `je-step-12`, `je-step-13`, `je-month-2023-06`, `je-month-2023-08` and `je-month-2023-09` as C |
| OQ-D7 | `shipped-db-equivalence`: assert through the D-31 mode (b) replay reconciliation (numeric columns within 1e-4, text exact, timestamps excluded) | As stated | **Resolved by D-75.** As stated (DG §9.6 row `point_in_time_equivalence`) |
| OQ-D8 | DEV-058 reclass attribution fallback: cumulative SSP delivered, then cumulative revenue (ALG-02 parity), then POB allocations | As stated; POLICIES.md ALG-02 owner to confirm the third step | **Resolved by D-75.** The three-step fallback is adopted. The POLICIES.md ALG-02 owner records the third step (B1-consistency §6.2 item 6) |
| OQ-D9 | DEV-060: under the preset rate `CURRENT_REMAINING_RATE`, a return when remaining quantity is 0 uses the average carrying rate | As stated; POLICIES.md POL-052 owner to confirm | **Resolved by D-75.** Adopted. The POLICIES.md POL-052 owner records it (B1-consistency §6.2 item 6) |
| OQ-D10 | DEV-032 activation timing for legacy replays: activate a contract after the last setup file dated on or before its first activity event | As stated | **Resolved by D-75.** Adopted |
| OQ-D11 | A finding on a POB key aggregated from several worksheet rows (probe P3: rows 2 and 6) needs one `worksheet_row` for the DG-PAR-06 `findings[]` assertion. Which row? | `worksheet_row` = the lowest contributing Excel row; `worksheet_rows` = every contributing row, ascending; the `exception_item` message names every row (REQ-DAT-006). `deviations.json` probe P3 encodes this default | Open |
