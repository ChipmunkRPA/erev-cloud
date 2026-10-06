# 05 - POB-Specific Variable Consideration (legacy `browse_file_POB_specific_VC`)

| Item | Value |
|---|---|
| Legacy source | `~/dev/erev-legacy/eRev.py` lines 2133-2539 (`FileBrowserWindow.browse_file_POB_specific_VC`) |
| UI trigger | Button `self.button5_1` labelled "POB Specific VC", row "Mod Operations" (eRev.py 138-141, wired at 235) |
| Template | `ops/Blank Templates/Contract Modification Template.xlsx` (shared with Prospective and Retrospective Mod) |
| UAT in scope | `ops/Example UATs/Contract Mod UAT/Contract Modification Template 05.31.2023 - retrospective POB specific VC.xlsx` |
| Related legacy docs | Contract setup (eRev.py 621-825), Delivery and billing (826-1168), Prospective mod (1170-1653), Retrospective mod (1655-2131), Journal entries (2540-2668, 2862-3011) |
| Status | Draft, reverse-engineered by static reading plus an instrumented replay of the legacy code under `.scratch/pob-vc/` |

Conventions in this document: "L2367" means eRev.py line 2367. "Fact" means observed in code or data; "Inference" means a reasoned interpretation that is not stated in code. Paragraph citations such as 606-10-32-40 refer to FASB ASC Topic 606.

Method: every line of L2133-2539 was read; the shared-state functions (setup L621-825, delivery L826-1168, prospective mod L1170-1653, retrospective mod L1655-2131, journal entries L2540-2668 and L2862-3011) were read for context. The legacy source was then replayed unmodified in-process with Qt dialogs stubbed (`.scratch/pob-vc/legacy_harness.py`, pandas 2.0.3 / numpy 1.24.4). The replay of SSP upload, contract setup and the 01.31.2023 delivery matches the shipped `ops/libnew/libwarm/db/ASC606.db` (24 rows, 71 columns, maximum absolute numeric difference 0.0), so the numbers in sections 5 and 7 come from the legacy code, not a re-implementation.

## 1. Purpose, trigger, inputs and outputs

### 1.1 Purpose

Fact. The function applies a change in transaction price to named POB lines of existing contracts. The change is added only to the targeted line's remaining allocation (L2367-2370); it is not re-spread across the contract's other POBs. A cumulative catch-up is then booked for the share of the change that relates to SSP already delivered (L2427-2447). The code is a copy of `browse_file_RetroMod` (L1655-2131) with three differences:

| # | Retrospective mod (L1655-2131) | POB-specific VC (this function) |
|---|---|---|
| D1 | Computes `Mod Midpoint/Lower_End/Higher_End SSP` and clamps `Mod Billing` into the range to get `Mod SSP Changes` (L1770-1815) | `Mod SSP Changes` is hard-coded to 0 (L2247-2248). No SSP range logic runs. |
| D2 | `Current Remaining Allocation` = the contract's pooled price re-spread by relative total SSP, minus revenue already recognised (L1932-1950) | `Current Remaining Allocation` = existing remaining allocation + `Mod Billing` on the same line (L2367-2370) |
| D3 | Success popup "Mod Success" | Success popup "POB Specific VC Successfully Applied!" (L2526-2527) |

Everything else is identical line for line, including the latent defects: the catch-up block, the Previous/Current roll-forward, contract position, reclass, the validations and the persistence.

Inference. The feature implements the allocation exception in ASC 606-10-32-40 (a variable amount and later changes to it go entirely to one POB), together with 606-10-32-44 (a change in transaction price allocated to some but not all POBs) and the catch-up requirement in 606-10-32-43. The README (L51) lists it as the third contract-mod button: "prospective contract mod, retrospective contract mod and POB specific variable consideration".

### 1.2 Trigger and dialog flow

| Step | Behaviour | Lines |
|---|---|---|
| 1 | User clicks button "POB Specific VC" (row "Mod Operations") | 138-141, 235 |
| 2 | `QFileDialog.getOpenFileName(self, "Select File")`. No file filter, so any file type can be picked. Cancel returns an empty path and the function does nothing. | 2134-2138 |
| 3 | `QInputDialog.getText` titled "Date Input", prompt "Enter the retrospective contract mod date in this format (YYYY-MM-DD):" (prompt copied from RetroMod). Cancel (ok False) does nothing. | 2139-2141 |
| 4 | `QDate.fromString(text, "yyyy-MM-dd")`. Invalid input gives a warning popup (VR-pob-vc-01) and exits. | 2142-2145 |
| 5 | `pd.read_excel(file_path)`: first worksheet, header in row 1, all rows read | 2150 |
| 6 | Validations VR-02 to VR-04, then the calculation, then validation VR-05, then append to `Contract_Live` | 2152-2530 |

### 1.3 Inputs

#### 1.3.1 Upload file (`Contract Modification Template.xlsx`, first sheet, named `Sheet1` in the template)

The column set must match exactly; order does not matter (L2152-2159). The UAT file has one data row.

| Column | Type as used | Required | How it is used | Lines |
|---|---|---|---|---|
| Contract Unique Name | text (`astype(str)`) | Yes. Not checked for blanks; a blank becomes the string `'nan'`. | Part of the join key `Record Unique ID without time` = Contract + " " + POB + " " + SKU | 2213-2214, 2250-2254 |
| POB Unique ID | text (`astype(str)`) | Yes (same caveat) | Join key | 2215-2216, 2250-2254 |
| SKU Name | text (not cast) | Yes. Must exist in `SKU_SSP` for the given Stratification and SSP Version. | SSP join key and part of the record key | 2221-2224, 2254 |
| Mod Start Date | date | Optional. Blank keeps the existing `POB Start Date`. | Overwrites `POB Start Date` (file value wins) | 2294-2296 |
| Mod End Date | date | Optional. Blank keeps the existing `POB End Date`. | Overwrites `POB End Date` (file value wins) | 2297-2299 |
| ASC 606 Stratification | text | Yes (SSP join key) | SSP join. The value `"VC"` exempts a line from the reclass to unbilled A/R and from the negative-remaining-billing check. The existing value wins over the file. | 2221-2224, 2303-2304, 2411, 2489-2491 |
| Mod Billing | numeric, no blanks | Yes | Change in transaction price. It is also treated as a change in future billing: added to `Current Remaining Allocation` and to `Current Remaining Billing`. Sign as entered (negative = price reduction). | 2160-2187, 2367-2375 |
| Mod Qty | numeric, no blanks | Yes (normally 0 for a pure price change) | Added to `Current Remaining Qty`. No SSP is added for it (see D1). | 2160-2187, 2358-2359 |
| Selling Entity | text | Optional. Used only where the existing line has no value (a new line). | fillna into the existing value | 2305-2306 |
| Deferred Revenue Account | number | Optional (new lines only) | fillna | 2309-2311 |
| Unbilled A/R Account | number | Optional (new lines only) | fillna | 2312-2314 |
| SSP Version | date or text, cast to str | Yes (SSP join key) | SSP join. The existing value wins. | 2210-2212, 2307-2308 |
| Memo 1, Memo 2, Memo 3 | text | Optional. A non-blank file value overwrites the memo on the targeted line. | Audit memo | 2289-2291 |

Precedence rule (fact). For identity and account attributes the existing `Contract_Live` value wins and the file only fills nulls (`existing.fillna(new)`, L2282-2286 and L2303-2329). For the dates and the memos the file value wins (L2289-2299). On a POB that already exists, a changed Selling Entity, account or SSP Version in the file is silently ignored.

#### 1.3.2 Prompted input

| Input | Used as | Lines |
|---|---|---|
| Mod date (YYYY-MM-DD) | `Current Period` on every appended row (midnight datetime). The prior `Current Period` moves to `Previous Period`. | 2208-2209, 2315-2316 |

#### 1.3.3 Database inputs (`ops/libnew/libwarm/db/ASC606.db`)

| Table | Read | Lines |
|---|---|---|
| `Contract_Live` | Latest version of each `Record Unique ID without time`: SQL join on `MAX("Processing Time Log")`, then pandas `idxmax` again on the result | 2190-2198, 2203, 2258-2262 |
| `SKU_SSP` | All rows. Supplies SKU Unique ID, Distinct or Nondistinct, SKU Unit List Price, Midpoint Discount Percentage, SSP Range Method (+-), Revenue Account; these fill nulls only. | 2199-2204, 2317-2329 |

### 1.4 Outputs

| Output | Detail | Lines |
|---|---|---|
| `Contract_Live` append | One new row for every line of every contract named on at least one mod row: targeted lines, untouched POBs of the same contract, and VC pseudo-lines. Written with `to_sql(if_exists="append")`. Prior versions are never updated or deleted. | 2272-2279, 2524 |
| Columns recomputed | `Current Period`, `Previous Period`, `POB Start Date`, `POB End Date`, `Memo 1-3`, all 14 `Previous ...` roll-forward columns, `Current Remaining Qty/SSP/Allocation/Billing`, `Current Unit SSP`, `Current Remaining Unit Rev Rec`, `Current Delivery` (0), `Current Billing` (0), `Current Rev Rec` (= catch-up), `Current Cumulative Catchup - Disclosure Only`, `Current Cumulative Catchup - Cumulative - Disclosure Only`, `Current Rev Rec - Cumulative`, `Current Contract Position - POB`, `Current Contract Position - Contract Level`, `Current Reclass to UAR`, `Processing Time Log`, `Record Unique ID` | 2208-2481 |
| Columns carried over unchanged from the prior version | All `Original ...` columns, SKU attributes, accounts, `Current Delivery - Cumulative`, `Current Billing - Cumulative`, `Current SSP Delivered - Cumulative`, `Current Pre-ASC606 Revenue (Net Design Only) - Cumulative`. Defects: `Current SSP Delivered` and `Current Pre-ASC606 Revenue (Net Design Only)` are not reset to 0, and `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative` is not rolled forward (DEF-pob-vc-03). | (absence of assignment in L2315-2481) |
| Temporary columns dropped | `*_new`, `*_right_table`, `_merge`, `Mod Start Date`, `Mod End Date`, `Mod Billing`, `Mod Qty`, `Mod SSP Changes`, `Current Rev Rec - Cumulative Should Be` | 2240-2245, 2300, 2421-2424, 2481 |
| Excel files | None | - |
| Popups | Success: title "POB Specific VC Successfully Applied!", text "POB Specific VC has been processed retrospectively for the current date :)". Error popups are listed in section 2. | 2526-2527 |
| Downstream effect | The "Revenue Journal Entries" buttons select rows by `Current Period` in the entered range and post: `Current Rev Rec` as Dr Deferred Revenue / Cr Revenue (positive = debit); a reversal of `Previous Reclass to UAR`; and the new `Current Reclass to UAR`. Amounts are rounded to 4 dp, summed by contract and account, then rounded to 2 dp. The delta option also posts `Current Pre-ASC606 Revenue (Net Design Only)`. | 2594-2651, 2966-2994 |

## 2. Validation rules

Rules are evaluated in the order listed. "Observed" gives the scenario ID from the instrumented replay (`.scratch/pob-vc/edge_cases*.py`, outputs in `edge_cases*.out`).

| ID | Lines | Exact condition | Popup(s) (type, title, text) | Effect | Observed |
|---|---|---|---|---|---|
| VR-pob-vc-01 | 2141-2145 | `ok` is True and `QDate.fromString(text, "yyyy-MM-dd").isValid()` is False | warning, "Invalid Date", "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." | Exit, nothing written | S15 (`2023/05/31`) |
| VR-pob-vc-02 | 2157-2165 | `missing_titles` (expected not in actual) OR `extra_titles` (actual not in expected) is non-empty. Expected set: the 15 template columns of section 1.3.1. | information, "File Upload Error", "Error: The Excel file has incorrect or missing column titles." | Exit after VR-03/04 | S11 |
| VR-pob-vc-03 | 2166-2167 | `missing_titles` non-empty | information, title "Missing fields:", text = comma+space joined missing titles | Exit | S11 ("Memo 3") |
| VR-pob-vc-04 | 2168-2169 | `extra_titles` non-empty | information, title "Extra fields:", text = comma+space joined extra titles | Exit | S11 ("Foo") |
| VR-pob-vc-05 | 2160, 2173-2177, 2184-2187 | For each column in order `['Mod Billing', 'Mod Qty']`: `pd.to_numeric(col, errors='raise')` raises `ValueError` or `TypeError` | information, "Format Error", "Error: The column '{column}' should contain numeric values." | Stops at the first failing column; exit | S12 (`'abc'`) |
| VR-pob-vc-06 | 2180-2183 | Same loop: column contains any NaN (a blank cell) | information, "Format Error", "Error: The column '{column}' should contain numeric values." | Exit | S13 (blank Mod Qty) |
| VR-pob-vc-07 | 2221-2236 | Left join of upload to `SKU_SSP` on `['SKU Name', 'ASC 606 Stratification', 'SSP Version']` (SSP Version cast to str) leaves any row with `_merge == 'left_only'` | information, "Mod Upload Failed", "Some Mod POBs are not matched with the existing SSP databse. Re-upload the file after fixes! \nPOB with issues: \n{SKU Names joined by ','}"; then critical, "Error Notification", "The process is stopped for users to fix the file" | `raise Exception`; exit | S14 (SSP Version 2024-01-01) |
| VR-pob-vc-08 | 2489-2494 | After all calculations: `(Current Remaining Qty < 0).any()` over all rows being written, OR `(Current Remaining Billing < 0).any()` over rows whose `ASC 606 Stratification != "VC"` | information, "Mod Failed", "Qty or Price modified cannot reduce the remaining qty or remaining billing to negative. Check your uploads please."; then critical, "Error Notification", "The process is stopped for users to fix the file" | `raise Exception`; exit, nothing written | S03 (-2000 against 980 remaining billing). Also fires, with a misleading message, for a negative VC on an unknown POB (S05) or unknown contract (S06), because missing prior balances are filled with 0. |
| VR-pob-vc-09 | 2498-2507, 2528-2530 | `Contract_Live` missing from `sqlite_master` at write time | critical, "Error Notification", "No contract table is found!" | Exit | Unreachable in practice: `pd.read_sql_query` at L2203 fails first, giving critical "Error Notification" "Execution failed on sql '...': no such table: Contract_Live" (S17) |
| VR-pob-vc-10 | 2531-2532 | Any `TypeError` raised anywhere in the try block | None (silently swallowed) | Exit, nothing written | Intended only for a cancelled file dialog; it also hides genuine type errors |
| VR-pob-vc-11 | 2533-2538 | Any other `Exception` (for example, a non-Excel file passed to `read_excel`) | critical, "Error Notification", `str(e)` | Exit | S17 |

Silent paths (no validation, no popup):

| ID | Condition | Behaviour | Observed |
|---|---|---|---|
| VR-pob-vc-G1 | File dialog cancelled (empty path) or date prompt cancelled (`ok` False) | Nothing happens | S16, S24 |
| VR-pob-vc-G2 | Upload has headers but no data rows | Success popup shown, 0 rows appended | S18 |
| VR-pob-vc-G3 | Same POB appears twice in the upload | Not aggregated. Two rows with the same `Record Unique ID` and timestamp are appended, each carrying only its own `Mod Billing`, and the contract-level position double-counts the line. | S04 |
| VR-pob-vc-G4 | POB or contract not in `Contract_Live`, positive `Mod Billing` | See S05b/S06b in section 7: a phantom line is created with no SSP-derived originals | S05b, S06b |
| VR-pob-vc-G5 | Mod date earlier than the latest `Current Period` | Accepted. `Previous Period` ends up later than `Current Period`, and the catch-up posts into the earlier (possibly closed) period's JE range. | S20 |
| VR-pob-vc-G6 | `Mod Qty != 0` | Accepted. Quantity changes but SSP does not (D1), so unit SSP is diluted. | S02 |
| VR-pob-vc-G7 | Target is a `VC` pseudo-line | Accepted. Negative remaining allocation on a zero-SSP line; the VC line is exempt from VR-08. | S07 |
| VR-pob-vc-G8 | File values for Selling Entity, accounts, SSP Version or Stratification differ from the existing line | File value silently ignored (existing value wins) | code L2303-2314 |
| VR-pob-vc-G9 | A reduction larger than the line's remaining allocation | Not blocked while remaining billing stays at or above 0; can drive cumulative revenue for the line negative | S32 |
| VR-pob-vc-G10 | No evidence that the 606-10-32-40 criteria are met, no reason code, no approver | Not captured | - |

## 3. Calculation logic

### 3.1 Notation

For each line i (one row per `Record Unique ID without time`) of contract c, "old" means the latest `Contract_Live` version before the run.

| Symbol | Column | Source |
|---|---|---|
| Q_old | Current Remaining Qty | latest version |
| S_old | Current Remaining SSP | latest version |
| A_old | Current Remaining Allocation | latest version |
| B_old | Current Remaining Billing | latest version |
| R_old | Current Rev Rec - Cumulative | latest version |
| BC | Current Billing - Cumulative | latest version (unchanged by this function) |
| D | Current SSP Delivered - Cumulative (also copied to `Previous SSP Delivered - Cumulative`) | latest version (unchanged) |
| CC_old | Current Cumulative Catchup - Cumulative - Disclosure Only | latest version |
| M | Mod Billing | upload; NaN, i.e. 0, on untouched lines |
| q | Mod Qty | upload; 0 on untouched lines |

All `fillna(0)` calls are shown as "(NaN->0)". Arithmetic is pandas float64 (int64 where every operand is an integer); no rounding anywhere in the function.

### 3.2 Preparation and scoping (L2208-2329)

```
mod_date            = datetime(qdate, 00:00:00)                                  # L2208
upload.SSP Version  = str(SSP Version); Contract, POB = str(...)                 # L2210-2216
upload ⟕ SKU_SSP on (SKU Name, ASC 606 Stratification, SSP Version)              # L2221-2224, VR-07
Mod SSP Changes     = 0                                                          # L2247-2248  (no SSP range logic)
K                   = Contract + " " + POB + " " + SKU Name                      # L2250-2254
latest              = Contract_Live rows with MAX(Processing Time Log) per K     # L2190-2198, L2258-2262
merged              = latest ⟗ upload on K, suffixes ('', '_new')                # L2265-2267  (outer join)
touched_contracts   = merged.Contract Unique Name where Mod Qty and Mod Billing not null   # L2272-2275
merged              = merged where Contract Unique Name in touched_contracts     # L2278-2279
```

Consequences (facts):

1. Every existing line of a touched contract stays in scope: targeted lines, other POBs and VC pseudo-lines. Lines of other contracts are dropped and get no new version.
2. The filter reads the left-side `Contract Unique Name`, which is NaN for a right-only row (an upload row with no existing line). An upload row for an unknown POB therefore contributes NaN to the list. Unless another upload row matches an existing line of the same contract, the contract's existing lines are dropped from scope and the contract-level aggregates are computed over the phantom row alone (S05b).
3. Attribute precedence (L2282-2329): identity, accounts, SSP attributes and Stratification use `existing.fillna(new)`; `Memo 1-3` use `new.fillna(existing)`; `POB Start/End Date` = `Mod Start/End Date` if provided, else existing.

### 3.3 Roll-forward (L2315-2355)

```
Previous Period = Current Period_old ;  Current Period = mod_date
For X in {Remaining Qty, Remaining SSP, Remaining Allocation, Remaining Billing, Unit SSP,
          Remaining Unit Rev Rec, Delivery - Cumulative, Rev Rec - Cumulative, Billing - Cumulative,
          Cumulative Catchup - Cumulative - Disclosure Only, SSP Delivered - Cumulative,
          Contract Position - POB, Contract Position - Contract Level, Reclass to UAR}:
    Previous X = Current X_old (NaN->0)
```

Not rolled: `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative` keeps its old value. Not reset: `Current SSP Delivered` and `Current Pre-ASC606 Revenue (Net Design Only)` keep the values of the last delivery event (DEF-pob-vc-03).

### 3.4 Pass 1: balances (L2358-2411)

```
Q   = Q_old (NaN->0) + q (NaN->0)                                         # L2358-2359
S   = S_old (NaN->0) + 0 ;  if S < 0 then S = 0                           # L2360-2364  (Mod SSP Changes = 0)
A1  = A_old (NaN->0) + M (NaN->0)                                         # L2367-2370  POB-specific allocation
B   = B_old (NaN->0) + M (NaN->0)                                         # L2372-2375  billing plan moves with price
Current Unit SSP               = (S / Q) (NaN->0)                          # L2376-2378  (x/0 with x != 0 gives ±inf, not cleared)
Current Remaining Unit Rev Rec = (A1 / Q) (NaN->0)                         # L2379-2382  (overwritten in pass 2)
Current Delivery = 0 ; Current Rev Rec = 0 ; Current Billing = 0 ; Current Cumulative Catchup - Disclosure Only = 0   # L2383-2386
R  = R_old (NaN->0) ; BC (NaN->0) ; Delivery-Cum (NaN->0) ; CC_old (NaN->0)                                            # L2387-2394
Position POB, Position Contract Level, Reclass to UAR computed as in 3.6 using R (all overwritten in pass 2)             # L2395-2411
Processing Time Log = pd.Timestamp.now()  (one value for the whole run)                                               # L2414
Record Unique ID    = str(Processing Time Log) + " " + K                                                               # L2415-2418
drop *_new, Mod Billing, Mod Qty, Mod SSP Changes                                                                      # L2421-2424
```

### 3.5 Pass 2: cumulative catch-up (L2427-2460)

```
D_prev    = Previous SSP Delivered - Cumulative            (= D (NaN->0))
ShouldBe  = ((A1 + R) / (S + D_prev)) × D_prev   (NaN->0)                     # L2427-2432
CU        = ShouldBe − R                                                       # L2434-2437
Current Cumulative Catchup - Disclosure Only             = CU                  # L2434-2437
Current Cumulative Catchup - Cumulative - Disclosure Only = CC_old + CU        # L2438-2441
Current Rev Rec                 = CU (NaN->0)                                  # L2443-2444
Current Rev Rec - Cumulative    = R + CU                                       # L2445-2447
Current Remaining Allocation    = (A1 − CU) (NaN->0)                           # L2451-2453
Current Remaining Unit Rev Rec  = (Current Remaining Allocation / Q) (NaN->0)  # L2455-2460
```

Closed form (derived from the formulas above). With total line allocation T = A_old + R_old and total line SSP W = S + D:

```
CU = M × D / W                      <- share of the price change that relates to SSP already delivered
   + [ T × D / W − R_old ]          <- "latent true-up" term
```

The latent true-up is zero when cumulative revenue on the line equals its total allocation times the delivered-SSP share. That holds for lines built only by setup, deliveries and retrospective mods. It does not hold after a prospective mod has re-spread remaining allocation without a catch-up on distinct lines. In that case every line of the touched contract, targeted or not, receives a catch-up (DEF-pob-vc-01; S09: Contract 3 POB #2 +17.157586 when only POB #1 was targeted).

Edge behaviour of the formula:

| Case | Result | Evidence |
|---|---|---|
| Nothing delivered (D = 0) | ShouldBe = 0 so CU = 0; the whole M goes to remaining allocation | S22 |
| Fully delivered (S = 0, D > 0) | CU = M (immediate recognition). Remaining allocation is a float residual (−5.68e-14) and `Current Remaining Unit Rev Rec` = −inf. | S08 |
| Zero-SSP line such as a VC pseudo-line (S = 0, D = 0) | 0/0 gives NaN, so CU = 0; remaining allocation = A_old + M (can be negative) | S07 |
| Over-time nondistinct line (partially delivered) | CU = M × SSP-delivered share (same formula; progress is measured by SSP delivered) | S25 |

### 3.6 Contract position and reclass to unbilled A/R (L2461-2478)

```
Current Contract Position - POB            = BC (NaN->0) − Current Rev Rec - Cumulative (NaN->0)         # L2461-2466
Current Contract Position - Contract Level = Σ_{lines in c, in scope} Position POB                       # L2467-2469
Current Reclass to UAR = if PositionContract < 0:
                             (−PositionContract / Σ_{lines in c} D) × D        # D not NaN-filled; NaN rows give NaN
                         else 0                                                                           # L2470-2475
if ASC 606 Stratification == "VC": Current Reclass to UAR = 0                                             # L2477-2478
```

Sign conventions (facts from L2594-2636):

| Column | Positive means | JE generated |
|---|---|---|
| Mod Billing | Price increase (bonus); negative = price concession | none directly |
| Current Rev Rec (= CU) | Revenue credit | Dr Deferred Revenue (+), Cr Revenue (−) |
| Contract Position (POB or contract) | Contract liability (billing ahead of revenue); negative = contract asset | - |
| Current Reclass to UAR | Contract asset balance | Dr Unbilled A/R, Cr Deferred Revenue. The prior version's `Previous Reclass to UAR` is reversed in the same JE run. |

The reclass is allocated to lines in proportion to cumulative SSP delivered; VC lines are then forced to 0 without redistributing their share. If Σ D includes a VC line with D > 0 the reclass does not sum to the contract position. In practice VC lines have unit SSP 0, so D = 0.

### 3.7 Items that do not run in this function

| Topic | Behaviour in this function | Where it lives for other events |
|---|---|---|
| SSP range (midpoint, higher, lower) | Not applied; `Mod SSP Changes` = 0, so SSP never changes | Setup L682-700, Pros/Retro mod L1286-1331 / L1770-1815 |
| Relative-SSP allocation and discount allocation | Not applied; the entire change goes to the targeted line | Setup L702-717, Retro mod L1932-1950 |
| Residual approach | Not implemented anywhere in legacy | - |
| Distinct vs nondistinct split | Not used; the same catch-up formula applies to every line | Pros mod L1521-1597 |
| Pre-ASC 606 net-design revenue | Not recomputed; the prior event's periodic value is carried over (defect) | Delivery L995-1065 |
| Rounding | None; JE export rounds to 4 dp per row, then 2 dp after summing by contract and account | L2598-2651 |

### 3.8 Persistence (L2484-2530)

Rows are sorted by K (L2484) and VR-08 runs (L2489-2494). The code checks that the table exists (L2498-2507) and appends with `to_sql("Contract_Live", if_exists="append", index=False)` (L2524). The column list is the 71-column `Contract_Live` schema. SQLite column affinities come from the first contract-setup run (for example `Current Rev Rec` is declared INTEGER). Non-integral floats are still stored as REAL (verified with `typeof()` on the shipped DB), so nothing is truncated.

## 4. State transitions

| Aspect | Behaviour | Lines |
|---|---|---|
| Versioning model | Append-only snapshots. Each run appends one full row for every line of each touched contract; earlier versions are never modified. | 2272-2279, 2524 |
| Natural key | `Record Unique ID without time` = "Contract POB SKU" | 2250-2254 |
| Version key | `Record Unique ID` = "{Processing Time Log} Contract POB SKU". One `pd.Timestamp.now()` for the whole run, so all rows of an event share it. | 2414-2418 |
| Latest version | SQL `MAX("Processing Time Log")` per natural key (string comparison of the stored text timestamp), then pandas `idxmax`. Ordering is by processing time, not by `Current Period`. | 2190-2198, 2258-2262 |
| Period fields | `Current Period` = mod date; `Previous Period` = prior `Current Period`. There is no ordering check, so `Previous Period > Current Period` is possible (S20). | 2315-2316 |
| Previous X roll-forward | The 14 columns in 3.3 copy the prior current values | 2332-2355 |
| Periodic (flow) columns | `Current Delivery` = 0, `Current Billing` = 0, `Current Rev Rec` = catch-up, `Current Cumulative Catchup - Disclosure Only` = catch-up. `Current SSP Delivered` and `Current Pre-ASC606 Revenue (Net Design Only)` are not reset (stale). | 2383-2386, 2434-2444 |
| Cumulative columns | `Current Rev Rec - Cumulative` += CU; `... Catchup - Cumulative ...` += CU; delivery, billing, SSP-delivered and pre-ASC 606 cumulatives unchanged | 2438-2447 |
| Untouched lines of a touched contract | New version with the same balances, Current Rev Rec 0 (or a latent catch-up, see 3.5), and refreshed contract position and reclass | 2427-2478 |
| Duplicate upload rows | Duplicate versions with identical `Record Unique ID`. Later "latest" queries return both, pandas keeps the first; history and JE queries (all rows by `Current Period`) see both. | S04 |
| Atomicity | Read and write use separate connections. The append is a single `to_sql` call; all validations run before it, so a failed run writes nothing. | 2189-2205, 2498-2525 |
| Undo | None in-function. Recovery is "Restore from Backup" (premium) or "Purge Contracts" by contract and `Current Period` range (L477-532), which deletes every event in the range, not just this run. | 330-373, 477-532 |
| Event type | Not recorded. A VC run is distinguishable only by memo text and the pattern Current Delivery = Current Billing = 0 with Current Rev Rec ≠ 0. | - |

Lifecycle for the targeted line (text state diagram):

```
[Setup version] --deliveries/billings--> [Delivery versions] --retro/pros mods--> [Mod versions]
      \___________________________________________________________________________/
                                   |
                     POB Specific VC (mod date t)
                                   v
  new version: Previous* = prior Current*; allocation += M; remaining billing += M;
               Current Rev Rec = CU; cumulative revenue += CU; position and reclass refreshed
                                   |
                  next Delivery event uses Current Remaining Unit Rev Rec
                  = (A_old + M − CU) / Q to recognise the rest of M
```

## 5. Worked example (UAT `Contract Modification Template 05.31.2023 - retrospective POB specific VC.xlsx`)

### 5.1 Scenario and event order

UAT row: `Contract 2 | POB #1 | Hardware 1 | Mod Start 2023-01-01 | Mod End 2024-05-31 | Stratification Hardware 1 | Mod Billing -200 | Mod Qty 0 | Mock Entity 2 | 21002 | 15002 | SSP Version 2023-01-01 | Mod 1/2/3 05.31.23`, mod date 2023-05-31.

Replay order: SSP UAT, then setups 1.1.2023 and 2.1.2023, then deliveries 1.31, 2.28, 3.31 and 4.30, then retrospective mod 05.15, then this VC at 05.31. The later UATs (06.15, 07.15, 08.15, 09.15, full delivery 10.31) continue from here. The order is inferred from the file dates. It is supported by the 10.31 full-delivery file, which bills 780 on Contract 2 POB #1 (= 600 + 400 − 200 − 20) and delivers 9 units (= 8 + 2 − 1). That only reconciles if this VC ran after the 05.15 mod.

### 5.2 Contract 2 at inception (setup L682-717)

| Line | List | Midpoint disc. | Range ± | Qty | Price | Midpoint SSP | Higher | Lower | Extended SSP (clamp) | Allocation = SSP / 1,170 × 900 |
|---|---|---|---|---|---|---|---|---|---|---|
| POB #1 Hardware 1 | 100 | 10% | 15% | 8 | 600 | 720 | 828 | 612 | 612 (price below lower) | 470.769231 |
| POB #2 Software 1 | 200 | 20% | 15% | 3 | 400 | 480 | 552 | 408 | 408 (price below lower) | 313.846154 |
| POB #3 Consulting 1 (nondistinct) | 300 | 50% | 0% | 1 | 0 | 150 | 150 | 150 | 150 | 115.384615 |
| VC #1 Variable Consideration (Stratification VC) | 0 | 0% | 0% | 1 | −100 | 0 | 0 | 0 | 0 | 0.000000 |
| Total | | | | | 900 | | | | 1,170 | 900.000000 |

### 5.3 Events before the VC

| Date | Event | Contract 2 effect |
|---|---|---|
| 2023-01-31 | Delivery | POB #1 delivers 1 unit: revenue 58.846154, SSP delivered 76.5 |
| 2023-03-31 | Delivery | POB #3 delivers 0.4: revenue 46.153846, SSP delivered 60 |
| 2023-04-30 | Billing | POB #1 bills 20 |
| 2023-05-15 | Retrospective mod POB #1 +2 qty, +400 price | Mod SSP range for 2 units: midpoint 180, lower 153, higher 207, so the 400 clamps to 207. Remaining SSP becomes 742.5. Pooled ratio = (795 + 400 + 105) / (1,240.5 + 136.5) = 1,300 / 1,377 = 0.944081. POB #1 remaining allocation = 0.944081 × 819 − 58.846154 = 714.356461. Catch-up: POB #1 +13.376068, POB #3 +10.491034. |

State immediately before the VC (the 2023-05-15 versions, i.e. "old"):

| Line | Q | S | A | B | R | BC | D | CC | Position POB | Reclass to UAR |
|---|---|---|---|---|---|---|---|---|---|---|
| POB #1 | 9 | 742.5 | 700.980392 | 980 | 72.222222 | 20 | 76.5 | 13.376068 | −52.222222 | 61.013431 |
| POB #2 | 3 | 408 | 385.185185 | 400 | 0 | 0 | 0 | 0 | 0 | 0 |
| POB #3 | 0.6 | 90 | 84.967320 | 0 | 56.644880 | 0 | 60 | 10.491034 | −56.644880 | 47.853671 |
| VC #1 | 1 | 0 | 0 | −100 | 0 | 0 | 0 | 0 | 0 | 0 |
| Contract level | | | | | | | 136.5 | | −108.867102 | 108.867102 |

### 5.4 Hand trace of the VC run (mod date 2023-05-31)

POB #1 (M = −200, q = 0):

| Step | Formula | Value |
|---|---|---|
| Q | 9 + 0 | 9 |
| S | 742.5 + 0 | 742.5 |
| A1 | 700.980392 + (−200) | 500.980392 |
| B | 980 + (−200) | 780 |
| Current Unit SSP | 742.5 / 9 | 82.5 |
| ShouldBe | (500.980392 + 72.222222) / (742.5 + 76.5) × 76.5 = 573.202614 × 76.5 / 819 | 53.540904 |
| CU = Current Rev Rec | 53.540904 − 72.222222 (closed form −200 × 76.5 / 819; latent term 0) | −18.681319 |
| Current Rev Rec - Cumulative | 72.222222 − 18.681319 | 53.540904 |
| Cumulative Catchup - Cumulative | 13.376068 − 18.681319 | −5.305250 |
| Current Remaining Allocation | 500.980392 − (−18.681319) | 519.661711 |
| Current Remaining Unit Rev Rec | 519.661711 / 9 | 57.740190 |
| Contract Position - POB | 20 − 53.540904 | −33.540904 |

Other lines:
- POB #2: D = 0, so ShouldBe = 0 and CU = 0.
- POB #3: ShouldBe = (84.967320 + 56.644880) / 150 × 60 = 56.644880, so CU = 0.
- VC #1: 0/0 is NaN, filled to 0, so CU = 0.

Contract level:
- Position = −33.540904 + 0 − 56.644880 + 0 = −90.185784.
- Reclass POB #1 = 90.185784 × 76.5 / 136.5 = 50.543681.
- Reclass POB #3 = 90.185784 × 60 / 136.5 = 39.642103.
- POB #2 and VC #1 = 0.

Every value above matches the legacy replay to 6 dp (`.scratch/pob-vc/analyze_uat.out`, scenario S01).

### 5.5 Journal entry produced for 2023-05-31 (Revenue Journal Entries, range 2023-05-31 to 2023-05-31)

| Component (L2594-2642) | 21002 Deferred revenue | 15002 Unbilled A/R | 5001 Revenue (Hardware) |
|---|---|---|---|
| Current Rev Rec (Dr DR / Cr Rev as + / −) | −18.681319 | | +18.681319 |
| Reverse Previous Reclass to UAR (61.013431 + 47.853671) | +108.867102 | −108.867102 | |
| New Current Reclass to UAR (50.543681 + 39.642103) | −90.185784 | +90.185784 | |
| Net, rounded to 2 dp | 0.00 (suppressed) | −18.68 | +18.68 |

Legacy output (replay): `Contract 2 | 15002 | -18.68` and `Contract 2 POB #1 Hardware 1 | 5001 | 18.68`, i.e. Dr Revenue 18.68 / Cr Unbilled A/R (contract asset) 18.68. The adjustment-JE option gives the same result because these rows carry no pre-ASC 606 amounts. Over 2023-05-15 to 2023-05-31 (retro mod plus VC): 15002 +5.19, 5001 +5.31, 5003 −10.49.

### 5.6 Downstream check (full delivery 2023-10-31)

POB #1 delivers the remaining 9 units at 57.740190, giving revenue 519.661711. Line cumulative revenue = 573.202614; cumulative catch-up disclosure = −5.305250. Contract 2 cumulative revenue = 573.202614 + 385.185185 + 141.612200 + 0 = 1,100.000000, which equals the transaction price (900 + 400 − 200). Cumulative billing = 800 + 400 + 0 − 100 = 1,100, and contract position = 0.

Accounting reading. The −200 concession is allocated entirely to the hardware line. 76.5 / 819 = 9.34% of it relates to hardware SSP already transferred and is reversed immediately. The remaining 90.66% reduces revenue on the 9 undelivered units. Because the contract was in a net contract-asset position, the entry reduces unbilled A/R rather than deferred revenue.

## 6. Accounting assessment

Sources are listed in section 8. The paragraph texts come from Deloitte DART roadmap pages; the FASB Codification itself was not accessed.

### 6.1 Where the logic is correct

| # | Topic | Legacy behaviour | ASC 606 basis |
|---|---|---|---|
| OK-1 | Allocating a change to one POB | `Mod Billing` is added only to the targeted line's allocation (L2367-2370) | 606-10-32-39 to 32-41 allow a variable amount, and later changes to it, to be allocated entirely to one POB when both criteria in 32-40 are met. 606-10-32-44 applies the same criteria to changes in transaction price. [S1][S2] |
| OK-2 | Catch-up on satisfied portion | CU = M × SSP delivered / total line SSP is booked as revenue in the mod period (L2427-2447) | 606-10-32-43: amounts allocated to a satisfied POB are recognised as revenue, or a reduction of revenue, in the period the transaction price changes. [S2] |
| OK-3 | No SSP re-measurement | `Mod SSP Changes` = 0; the line's SSP basis is untouched | 606-10-32-43: an entity does not reallocate to reflect changes in SSP after inception. [S2] |
| OK-4 | Unsatisfied portion | The remainder of M flows into `Current Remaining Unit Rev Rec` and is recognised on future deliveries | Consistent with 606-10-32-43 for the unsatisfied part of the POB. [S2] |
| OK-5 | Contract-level netting | Position is summed per contract; a reclass to unbilled A/R is made only for a net asset position (L2461-2475) | 606-10-45-1 and ASU 2014-09 BC317: contract assets and liabilities within a contract are presented net. [S7] |
| OK-6 | Disclosure tracking | `Current Cumulative Catchup - Disclosure Only` and its cumulative accumulate prior-period effects | Supports 606-10-50-12A: revenue recognised in the period from POBs satisfied in previous periods, for example changes in transaction price. [S8] |
| OK-7 | Over-time nondistinct line | The same SSP-delivered share gives CU = M × progress (S25: +30 × 60/150 = 12.00) | Consistent with measuring the satisfied portion by the entity's measure of progress (inference) |

### 6.2 Where it is simplified

| # | Topic | Legacy | Standard / impact |
|---|---|---|---|
| SIM-1 | Estimation and constraint | The user enters the final delta. There is no expected-value or most-likely-amount estimate, no constraint, and no reassessment cadence. | 606-10-32-5 to 32-9 (estimate), 32-11 to 32-12 (constraint), 32-14 (update at each reporting date). Estimates, constraint judgements and support are not captured. [S5] |
| SIM-2 | 32-40 criteria | Nothing captures criterion (a) (terms relate specifically to the efforts or outcome for that POB) or criterion (b) (consistent with the allocation objective considering all POBs and payment terms) | 606-10-32-40(a)-(b), 32-28. Any line can be targeted, including a VC pseudo-line. [S1][S9] |
| SIM-3 | Measure of the satisfied portion | Fixed at SSP-delivered share. For a multi-unit distinct line this is an SSP-weighted unit count (76.5/819 = 9.34% vs 1/10 units = 10% in the UAT). | Inference: an acceptable proxy, but not configurable and not tied to a documented measure of progress |
| SIM-4 | Price vs billing | `Current Remaining Billing += M`: a price change is assumed to change future invoicing | Transaction price (step 3) is independent of invoicing. A concession on already-billed amounts produces a refund liability (606-10-32-10) or credit memo, but legacy rejects it (VR-08; S31, S33). [S5] |
| SIM-5 | Price-only modification vs VC resolution | One path; the prompt says "retrospective contract mod date" | A price-only change agreed by the parties is a modification under 606-10-25-10 to 25-13. A change after a modification follows 606-10-32-45. [S3][S4] |
| SIM-6 | Consideration payable to a customer | Not distinguished from price concessions | Consideration payable to a customer is its own reduction-of-transaction-price topic. [S6] |

### 6.3 Where it is wrong or incomplete (defects)

| ID | Defect | Failure scenario (inputs, then wrong output) | Evidence |
|---|---|---|---|
| DEF-pob-vc-01 | Untouched lines of a touched contract are re-trued ("latent true-up") | Contract 3 after the 07.15 prospective mod: VC +100 on POB #1 at 2023-07-31. POB #2 (not targeted) books CU +17.157586 and cumulative revenue moves 118.533201 → 135.690787. This silently converts earlier prospective treatment into a catch-up and contradicts 606-10-32-44 (allocate to one POB). | S09; L2427-2447 |
| DEF-pob-vc-02 | `Mod Qty ≠ 0` accepted with no SSP for the added units | VC −200 with Mod Qty +2: remaining qty 11, SSP stays 742.5, unit SSP diluted 82.5 → 67.5, unit rev rec 47.241974. Later SSP-delivered shares and reclass weights are distorted. | S02; L2247-2248, L2358-2378 |
| DEF-pob-vc-03 | Stale periodic columns | `Current Pre-ASC606 Revenue (Net Design Only)` and `Current SSP Delivered` are not reset, and `Previous Pre-ASC606 ... - Cumulative` is not rolled. The adjustment JE over 2023-02-28 to 2023-03-01 posts Contract 4 21002 −188.71 / 5001 +188.71 instead of −38.71 / +38.71: the 150 pre-ASC 606 revenue is duplicated. | S10 vs S10b |
| DEF-pob-vc-04 | Duplicate upload rows not aggregated | Two rows of −100 on POB #1 append two identical versions; contract position −142.408006 instead of −90.185784; reclass wrong | S04 |
| DEF-pob-vc-05 | No existence check for contract or POB | Positive amount on unknown `POB #9`: a phantom line (qty 0, SSP 0, allocation 200, unit rev rec +inf, NULL SSP delivered) is appended, and Contract 2's existing lines are not re-versioned. Unknown `Contract 9` creates a new contract with no originals. A negative amount gives the misleading "negative remaining billing" error. | S05, S05b, S06, S06b; L2272-2279 |
| DEF-pob-vc-06 | ±inf stored | Fully delivered line: remaining allocation float residual −5.68e-14 / qty 0 gives `Current Remaining Unit Rev Rec` = −inf; the phantom line gives +inf | S08, S05b; L2455-2460 |
| DEF-pob-vc-07 | Concession on fully billed lines is impossible | C2 POB #2 fully billed and delivered, −60: rejected by VR-08. C1 POB #2 billed 400 of 400, −40: rejected. Common real-world credit-memo and rebate cases cannot be processed. | S31, S33 |
| DEF-pob-vc-08 | No floor on reductions | −900 against remaining allocation 700.98: CU −84.065934, line cumulative revenue −11.843712, remaining allocation −114.953674, all accepted | S32 |
| DEF-pob-vc-09 | VC pseudo-line can be targeted | −50 on `VC #1`: allocation −50 on a zero-SSP line, recognised later at revenue account 5004 when the VC line is "delivered" | S07 |
| DEF-pob-vc-10 | No period-order or close control | Mod date 2023-01-15 after events to 2023-05-15: accepted. The catch-up posts into January's JE range and `Previous Period` > `Current Period`. | S20 |
| DEF-pob-vc-11 | Misleading outcomes | Header-only upload shows a success popup with 0 rows; any `TypeError` is swallowed silently (L2531); "No contract table is found!" is unreachable (VR-09) | S18, S17 |
| DEF-pob-vc-12 | File attributes silently ignored | Changed Selling Entity, account or SSP Version on an existing POB is dropped without a warning (existing value wins) | L2303-2314 |
| DEF-pob-vc-13 | 606-10-32-45 not supported | There is no lineage of pre- vs post-modification POBs, so variable consideration promised before a 25-13(a) modification cannot be routed to the original POBs | [S4] |
| DEF-pob-vc-14 | No audit metadata | No user, approver, reason code, 32-40 evidence, source-file name or hash. Memo 1-3 overwrite the prior memos on the targeted line. | L2289-2291 |
| DEF-pob-vc-15 | Reclass division | Reclass = −position / Σ SSP delivered × SSP delivered. When Σ SSP delivered is 0 or NULL (phantom rows) while the position is negative, the result is NaN or inf (code-path inference; not triggered in the scenarios run) | L2470-2475 |
| DEF-pob-vc-16 | Pass-1 computations are dead code | Position, contract level and reclass are computed twice (L2395-2411 then L2461-2478); only pass 2 persists | L2395-2411 |

## 7. Port notes for the eRev Cloud engine

### 7.1 Parity requirements (preserve)

| ID | Requirement | Legacy reference | Test |
|---|---|---|---|
| P-pob-vc-01 | A "POB-specific transaction price change" event targets existing lines. `M` is added only to the targeted line's allocation; other lines' allocations are unchanged. | L2367-2370 | TC-01, TC-05 |
| P-pob-vc-02 | Catch-up CU = M × D / (S + D), posted as revenue in the event period with the sign of M | L2427-2447 | TC-01, TC-03, TC-04 |
| P-pob-vc-03 | Remaining allocation = A_old + M − CU; remaining unit rev rec = remaining allocation / remaining qty | L2451-2460 | TC-01 |
| P-pob-vc-04 | SSP basis unchanged: no SSP range clamp, no relative-SSP re-spread, no SSP refresh | L2247-2248 | TC-01 |
| P-pob-vc-05 | Boundaries: nothing delivered gives CU 0; fully delivered gives CU = M; zero-SSP line gives CU 0 | L2427-2432 | TC-02, TC-06 |
| P-pob-vc-06 | By default the remaining billing plan moves by M. A rule equivalent to VR-08 blocks negative remaining quantity, and negative remaining billing on non-VC lines, unless the credit-memo path of FIX-07 is used. | L2372-2375, L2489-2494 | TC-09 |
| P-pob-vc-07 | Catch-up disclosure measures: periodic = CU, cumulative += CU, reportable for 606-10-50-12A | L2434-2441 | TC-01 |
| P-pob-vc-08 | Contract position = Σ over all lines of (billing cumulative − revenue cumulative). A negative position gives a contract-asset reclass allocated by cumulative SSP delivered; VC lines get 0. | L2461-2478 | TC-01, TC-06 |
| P-pob-vc-09 | JE = revenue change + reversal of the prior reclass + the new reclass, consolidated by contract and account, rounded to 2 dp. UAT: Dr 5001 18.68 / Cr 15002 18.68. | L2594-2651 | TC-01 |
| P-pob-vc-10 | Versioned history: the event creates a new effective version per line of the touched contract, sharing one event id and timestamp. Previous = prior Current for the 14 roll-forward measures; Previous Period = prior Current Period. The Contract History and Latest Contract reports must reproduce this view. | L2315-2355, L2414-2418 | TC-01 |
| P-pob-vc-11 | Event date = the user-entered mod date (stored as `Current Period`); periodic delivery and billing = 0 | L2208, L2383-2385 | TC-01 |
| P-pob-vc-12 | Upload contract: the 15 template columns; Mod Billing and Mod Qty numeric with no blanks; SKU + Stratification + SSP Version must exist in the SSP catalogue; dates and memos override when provided; identity and account fields keep existing values | L2152-2236, L2282-2329 | TC-18 |
| P-pob-vc-13 | Every validation completes before any write; a failed upload writes nothing | L2489-2530 | TC-09, TC-18 |
| P-pob-vc-14 | Over-time nondistinct lines use the same satisfied-share formula | L2427-2447 | TC-04 |
| P-pob-vc-15 | Tolerances: engine measures within 1e-6 of legacy on the parity fixtures; JE amounts within 0.01 | - | all |
| P-pob-vc-16 | Completion reconciliation: cumulative revenue = cumulative billing = transaction price and position 0 (Contract 2 at 2023-10-31 = 1,100.00) | L1053-1086 | TC-01b |

### 7.2 Behaviours to fix

| ID | Fixes | New behaviour | Test |
|---|---|---|---|
| FIX-pob-vc-01 | DEF-01 | Compute a catch-up only for the targeted lines. Untouched lines get no catch-up and no change in cumulative revenue. | TC-07 |
| FIX-pob-vc-02 | DEF-02 | Reject `Mod Qty ≠ 0` on this event type; quantity changes belong to modification events | TC-08 |
| FIX-pob-vc-03 | DEF-03 | Reset periodic measures (pre-ASC 606 revenue, SSP delivered, delivery, billing) to 0 on non-delivery events, and roll every Previous measure | TC-13 |
| FIX-pob-vc-04 | DEF-04 | Reject duplicate (contract, POB, SKU) rows, or aggregate them explicitly with a warning in the preview | TC-10 |
| FIX-pob-vc-05 | DEF-05 | Target must exist and be active; otherwise error `POB_NOT_FOUND` / `CONTRACT_NOT_FOUND` | TC-11 |
| FIX-pob-vc-06 | DEF-06, DEF-15 | Decimal arithmetic, zero-quantity and zero-SSP guards; never persist NaN or ±inf; explicit rounding policy with a rounding-difference line in JEs | TC-06 |
| FIX-pob-vc-07 | DEF-07, SIM-4 | Decouple price change from invoicing. A concession on billed amounts creates a refund liability or credit-memo expectation (606-10-32-10) instead of negative remaining billing. | TC-16 |
| FIX-pob-vc-08 | DEF-08 | Guard: line total allocation (A_old + R_old + M) ≥ 0, unless an approved override exists | TC-17 |
| FIX-pob-vc-09 | DEF-09 | Reject VC pseudo-lines as targets; model variable consideration as a transaction-price component with an allocation method, not as a fake POB | TC-12 |
| FIX-pob-vc-10 | DEF-10 | Event date must be on or after the contract's latest event date and inside an open period; backdating only through a controlled prior-period adjustment workflow | TC-14 |
| FIX-pob-vc-11 | DEF-11 | Empty upload gives an error; no swallowed exceptions; database errors surface with codes | TC-15, TC-18 |
| FIX-pob-vc-12 | DEF-12 | Warn or reject when file attributes differ from the existing line | - |
| FIX-pob-vc-13 | SIM-1, SIM-2, DEF-14 | Capture VC type, estimate method (expected value or most likely amount), constraint rationale, 32-40(a)/(b) attestation, reason code, approver, attachments, source-file hash; maker-checker above a threshold; posting preview of catch-up and JE before commit | - |
| FIX-pob-vc-14 | SIM-5, DEF-13 | Distinguish (i) VC estimate change or resolution (606-10-32-42 to 32-44), (ii) price-only modification (606-10-25-10 to 25-13), and (iii) a price change after a modification (606-10-32-45), with POB lineage across modifications | - |
| FIX-pob-vc-15 | DEF-16 | Single-pass computation; no dead intermediate recalculation | - |
| FIX-pob-vc-16 | UX | Prompt "Effective date of the POB-specific price change". Success message states rows affected and total catch-up. | TC-15 |

### 7.3 Test cases to carry forward

Fixture: replay the UAT sequence of 5.1 into a clean tenant. Legacy snapshots are at `.scratch/pob-vc/snapshots/after_step_NN.db`: 00 SSP, 01-02 setups, 03-06 deliveries 1.31-4.30, 07 retro mod 05.15, 08 this VC, 09-12 later mods, 13 full delivery 10.31. "Legacy" values were produced by the legacy code; "Fixed" gives the target behaviour where it differs.

Abbreviations: A = Current Remaining Allocation, B = Current Remaining Billing, R = Current Rev Rec - Cumulative, URR = Current Remaining Unit Rev Rec, CC = Current Cumulative Catchup - Cumulative, Pos = Contract Position.

| ID | Seed | Input (mod date) | Legacy expected | Fixed expected |
|---|---|---|---|---|
| TC-pob-vc-01 | step 07 | C2 POB #1 M −200, q 0 (2023-05-31) | POB #1: Q 9, S 742.5, A 519.661711, B 780, unit SSP 82.5, URR 57.740190, CU −18.681319, R 53.540904, CC −5.305250, Pos POB −33.540904. POB #2: A 385.185185, CU 0. POB #3: A 84.967320, R 56.644880, CU 0. Contract Pos −90.185784. Reclass: POB #1 50.543681, POB #3 39.642103. JE 2023-05-31: 15002 −18.68, 5001 +18.68. | same |
| TC-pob-vc-01b | full UAT to step 13 | - | C2 POB #1 R 573.202614, CC −5.305250; contract revenue 1,100.00, billing 1,100, Pos 0 | same |
| TC-pob-vc-02 | step 07 | C2 POB #2 M +90 | CU 0; POB #2 A 475.185185, B 490, URR 158.395062; contract Pos −108.867102 | same |
| TC-pob-vc-03 | step 07 | C2 POB #1 M +100 | CU +9.340659; R 81.562882; A 791.639733; B 1,080; URR 87.959970; CC 22.716728 | same |
| TC-pob-vc-04 | step 07 | C2 POB #3 (nondistinct, 0.4 of 1 delivered) M +30 | CU +12.000000; R 68.644880; A 102.967320; B 30; URR 171.612200; CC 22.491034 | same |
| TC-pob-vc-05 | step 07 | C2 POB #1 −200 and C2 POB #2 +100 in one file | POB #1 as TC-01; POB #2 A 485.185185, B 500, URR 161.728395, CU 0; contract Pos −90.185784 | same |
| TC-pob-vc-06 | step 13 | C2 POB #2 M +60 (2023-11-15) | CU +60; R 445.185185; B 60; Pos POB −45.185185; contract Pos −60; reclass POB #1 35.686275, POB #2 17.777778, POB #3 6.535948; A −5.684342e-14; URR −inf | A 0.00, URR 0; others same |
| TC-pob-vc-07 | step 10 (after 07.15 prospective mod) | C3 POB #1 M +100 (2023-07-31) | POB #1: CU 0, A 687.303258, B 1,100. POB #2 (untargeted): CU +17.157586, R 135.690787, A 135.690787. Contract Pos 209.000468. | POB #2: CU 0, R 118.533201, A 152.848373; contract Pos 226.158054 |
| TC-pob-vc-08 | step 07 | C2 POB #1 M −200, q +2 | Accepted: Q 11, unit SSP 67.5, URR 47.241974, CU −18.681319 | Rejected (quantity change on VC event) |
| TC-pob-vc-09 | step 07 | C2 POB #1 M −2,000 | Rejected with the VR-08 message; 0 rows | same (error code) |
| TC-pob-vc-10 | step 07 | Two identical rows C2 POB #1 M −100 | 5 versions appended; contract Pos −142.408006 | Rejected duplicate, or aggregated to TC-01 values |
| TC-pob-vc-11 | step 07 | C2 POB #9 +200; Contract 9 POB #1 +200; C2 POB #9 −200 | Phantom line (URR +inf) / new contract / misleading VR-08 message | Rejected `POB_NOT_FOUND` / `CONTRACT_NOT_FOUND` |
| TC-pob-vc-12 | step 07 | C2 VC #1 M −50 | VC #1 A −50, B −150, URR −50 | Rejected (VC pseudo-line target) |
| TC-pob-vc-13 | step 04 (after 2.28) | C4 POB #2 M +50 (2023-03-01); adjustment JE 2023-02-28 to 2023-03-01 | Contract 4: 21002 −188.71, 5001 +188.71; VC row carries Current Pre-ASC606 150 and Current SSP Delivered 153 | 21002 −38.71, 5001 +38.71; periodic measures 0 |
| TC-pob-vc-14 | step 07 | C2 POB #1 M −200 dated 2023-01-15 | Accepted; Previous Period 2023-05-15 > Current Period 2023-01-15 | Rejected (before latest event or in a closed period) |
| TC-pob-vc-15 | step 07 | Header-only file | Success popup, 0 rows | Rejected "no data rows" |
| TC-pob-vc-16 | step 13 | C2 POB #2 M −60 (fully billed and delivered) | Rejected by VR-08 | Accepted: CU −60, R 325.185185; refund liability or credit-memo expectation 60 |
| TC-pob-vc-17 | step 07 | C2 POB #1 M −900 | Accepted: CU −84.065934, R −11.843712, A −114.953674, URR −12.772630 | Rejected: line total 773.202614 − 900 < 0 (unless approved override) |
| TC-pob-vc-18 | step 07 or 00 | Missing Memo 3 + extra Foo; Mod Billing 'abc'; blank Mod Qty; SSP Version 2024-01-01; date '2023/05/31'; database without Contract_Live | Messages per VR-02/03/04, VR-05, VR-06, VR-07, VR-01, VR-11; 0 rows | Equivalent error codes |

## 8. Sources and evidence

External sources (paragraph texts as presented by the publisher; FASB Codification not accessed directly):

| Ref | Source | Used for |
|---|---|---|
| S1 | Deloitte DART, Revenue Roadmap 7.5 "Allocation of Variable Consideration": [external website reference removed] | 606-10-32-39 to 32-41; Example 35 (55-270 to 55-279) |
| S2 | Deloitte DART, 7.6 "Changes in the Transaction Price": [external website reference removed] | 606-10-32-42 to 32-45; recognising changes allocated to satisfied POBs; no SSP reallocation |
| S3 | Deloitte DART, 9.2 "Types of Contract Modifications": [external website reference removed] | 606-10-25-12, 25-13(a)-(c); price-only modifications |
| S4 | Deloitte DART, 9.4 "Change in Transaction Price After a Contract Modification": [external website reference removed] | 606-10-32-45(a)-(b) |
| S5 | Deloitte DART, 6.3 "Variable Consideration": [external website reference removed] | 606-10-32-5, 32-7, 32-8, 32-10, 32-11, 32-12, 32-14 |
| S6 | Deloitte DART, 6.6 "Consideration Payable to a Customer": [external website reference removed] | Topic reference only |
| S7 | Deloitte DART, 14.1 "Presentation - Overview": [external website reference removed] | 606-10-45-1; net contract asset/liability within a contract (BC317) |
| S8 | Deloitte DART, 15.2 "Contracts With Customers" (disclosure): [external website reference removed] | 606-10-50-12A |
| S9 | PwC Viewpoint, 5.5 "Impact of variable consideration": [external website reference removed] | Allocation objective (606-10-32-28) when applying 32-40; series |

Internal evidence (scratch, not product deliverables):

| File | Content |
|---|---|
| `.scratch/pob-vc/legacy_harness.py` | In-process replay of unmodified `eRev.py` with stubbed Qt dialogs |
| `.scratch/pob-vc/scenario_uat.py` | Full UAT sequence; parity check vs shipped DB (24 rows, diff 0.0) |
| `.scratch/pob-vc/analyze_uat.out` | Contract 2 history, 71-column before/after diff of the VC run, JE outputs |
| `.scratch/pob-vc/edge_cases.out`, `edge_cases2.out` | Scenarios S01-S33 cited in sections 2, 3, 6 and 7 |
| `.scratch/pob-vc/snapshots/after_step_NN.db` | Seed databases for the test cases |

Open questions for the product owner:

1. Should a POB-specific price change keep moving the billing plan by M (legacy), or be decoupled from invoicing with credit-memo or refund-liability handling (FIX-07)?
2. For multi-unit distinct lines, is SSP-delivered share the desired satisfied-portion measure, or should units be treated as distinct goods in a series (unit count)?
3. Should any usage-based VC need `Mod Qty ≠ 0` on this event, and if so what SSP applies to the added quantity?
4. Is the latent true-up of untouched lines ever desired (it is the retrospective-mod design), or only in explicit retrospective modifications?
5. Will eRev Cloud hold VC estimates and constraints with periodic reassessment (606-10-32-14), or only final deltas as legacy does?
6. What POB lineage is required to route variable consideration promised before a 25-13(a) modification (606-10-32-45(a))?
7. IFRS 15 paragraph mapping for this feature was not verified in this study (web search budget exhausted); confirm the converged equivalents before documenting the IFRS mode.
8. Scope of the 606-10-50-12A disclosure for nonpublic entities was ambiguous in the source fetched; confirm before building the disclosure report.

