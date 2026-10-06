# Legacy eRev: Delivery and Billing Upload (`browse_file_Deliveries`)

| Item | Value |
|---|---|
| Legacy source (read-only) | `~/dev/erev-legacy/eRev.py`, lines 826-1169 (`FileBrowserWindow.browse_file_Deliveries`) |
| Shared state skimmed | contract setup `browse_file_Contracts` (621-824), journal entries `journal_entries` (2540-2668) and `journal_entries_delta` (2862-3011), latest-version queries (2784-2860), window and license gating (18-291) |
| Templates | `ops/Blank Templates/Contract Progress Tracking Template.xlsx` (sheet `Progress Tracking`) |
| UAT files | `ops/Example UATs/Delivery and Billing UAT/` (5 workbooks, listed in Section 5) |
| Golden DB snapshot | `ops/libnew/libwarm/db/ASC606.db` (24 `Contract_Live` rows: setup 2023-01-01, setup 2023-02-01, delivery 2023-01-31) |
| Author role | Revenue-systems engineer and revenue accountant (clean-room reverse engineering) |
| Status | Draft for engine design; accounting conclusions need human review before adoption |

Conventions in this document:

- `L<n>` means a line number in `eRev.py`.
- **Fact** = read directly from code or data. **Verified** = reproduced by running the unmodified legacy functions headless (Section 5 method). **Inference** = my interpretation, flagged as such.
- Amounts are in the transaction currency. The legacy app has no currency field, so it assumes one currency per contract.
- Sign convention of the contract position (fact, L1073-1075): **positive = billed ahead of revenue (contract liability / deferred revenue); negative = revenue ahead of billing (contract asset / unbilled A/R).**

---

## 1. Purpose, trigger, inputs, outputs

### 1.1 Purpose

This function records one period's delivery and billing events against contracts already in `Contract_Live`. For every contract that has at least one uploaded row, it:

1. rolls each POB's "Current" state into "Previous";
2. recognizes revenue = delivered quantity x remaining unit revenue rate (the rate stays fixed, so recognition is linear in quantity);
3. updates the remaining quantity, SSP, allocation and billing balances, and recomputes the unit rates;
4. accumulates the cumulative delivery, revenue, billing, pre-ASC 606 revenue, catch-up (always 0 here) and SSP delivered;
5. computes the contract position per POB and per contract;
6. when the contract-level position is a net asset, allocates a reclass from deferred revenue to unbilled A/R across the POBs;
7. appends a new, timestamped version row for **every POB of every contract that had activity**, including POBs with no activity in the upload.

Journal entries are **not** posted here. `journal_entries` (L2540) and `journal_entries_delta` (L2862) derive them later from the versioned rows (Section 3.12).

### 1.2 Trigger

| Step | UI element | Code |
|---|---|---|
| 1 | Main window button **"Load Delivery and Billing"** (`self.button3`), first button row "Contract Operations" | L108-111, wired at L232 |
| 2 | `QFileDialog.getOpenFileName(self, "Select File")`, with no file-type filter | L827-828 |
| 3 | `QInputDialog.getText` with title "Date Input" and prompt "Enter current period in this format (YYYY-MM-DD) for delivery/billing upload:" | L832-833 |
| 4 | Strict parse `QDate.fromString(input_text, "yyyy-MM-dd")` | L835 |

The button is **not** license-gated. Only the five premium database buttons are disabled when the license key check fails (L287-291).

The "current period" is a free-form date stamped on every new version row as `Current Period` (L1025-1026). It is not validated against the prior period, POB dates or a period calendar. The downstream journal entry reports filter on `Current Period` (L2574-2576).

### 1.3 Inputs

**Workbook:** `pd.read_excel(file_path)` reads the **first worksheet only** (L843). The blank template's sheet is named `Progress Tracking`. The UAT file `Full delivery 10.31.2023.xlsx` uses `Sheet1` and still works, because only position matters.

**Header contract (L846-851):** the set of column titles must equal exactly these nine. Order does not matter. Matching is case- and whitespace-sensitive, and any extra column fails.

| # | Column | Type expected | Required (as enforced) | Sign / range | Role |
|---|---|---|---|---|---|
| 1 | `Contract Unique Name` | text | Header required. A blank value makes pandas `groupby` drop the row silently (L909, see VR-delivery-13) | n/a | Join key part 1 (L918-922) |
| 2 | `POB Unique ID` | text | As above. **Must be text:** a numeric-only ID breaks string concatenation with `TypeError`, which is silently swallowed (VR-delivery-12) | n/a | Join key part 2 |
| 3 | `SKU Name` | text | As above | n/a | Join key part 3 |
| 4 | `Current Delivery` | numeric (float allowed, e.g. 0.5) | Header required; no blank cells (L871) | Negative allowed (return) | Quantity delivered this period |
| 5 | `Current Billing` | numeric | Header required; no blank cells | Negative allowed (credit memo / refund) | Amount invoiced this period |
| 6 | `Current Pre-ASC606 Revenue (Net Design Only)` | numeric | Header required; no blank cells | Any | Revenue already booked in the ERP under the legacy method, used only by the "Revenue Adjustment JEs" report (L2965-2979) |
| 7 | `Memo 1` | text | Header required. **A blank value drops the row silently** (VR-delivery-13) | n/a | Free text; overwrites the memo on the POB version (L1015) |
| 8 | `Memo 2` | text | Same as Memo 1 | n/a | L1016 |
| 9 | `Memo 3` | text | Same as Memo 1 | n/a | L1017 |

Several rows may carry the same contract, POB, SKU and identical memos. They are **summed** into one event (L909-913), and the UAT file for 2023-01-31 exercises this. Rows that differ only in memo text are **not** summed (VR-delivery-14).

**State read from the database (L881-907):** the latest version of each POB. Latest means the rows whose `Processing Time Log` equals the maximum for their `Record Unique ID without time` (SQL self-join), de-duplicated again with pandas `idxmax`. The columns consumed are listed in Section 3.

### 1.4 Outputs

| Output | Detail | Code |
|---|---|---|
| **Database: `Contract_Live` append** | One new row per POB for every contract with activity in the upload. All 71 columns are written: the Contract_Live columns of the merged frame, with the `_progress` and `_merge` helper columns dropped. Nothing is updated in place, so history is append-only | L1092-1095, L1154 |
| Columns rolled forward (Previous <- Current, NaN -> 0) | `Previous Remaining Qty`, `Previous Remaining SSP`, `Previous Remaining Allocation`, `Previous Remaining Billing`, `Previous Unit SSP`, `Previous Remaining Unit Rev Rec`, `Previous Delivery - Cumulative`, `Previous Rev Rec - Cumulative`, `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative`, `Previous Billing - Cumulative`, `Previous Cumulative Catchup - Cumulative - Disclosure Only`, `Previous SSP Delivered - Cumulative`, `Previous Contract Position - POB`, `Previous Contract Position - Contract Level`, `Previous Reclass to UAR`, `Previous Period` (no fillna) | L980-1009 |
| Columns set from the upload | `Current Delivery`, `Current Billing`, `Current Pre-ASC606 Revenue (Net Design Only)` (NaN -> 0 for POBs without activity); `Memo 1-3` (upload value, else previous memo); `Current Period` (the dialog date at 00:00:00); `Current Cumulative Catchup - Disclosure Only` = 0 | L1011-1026 |
| Columns computed | `Current Rev Rec`, `Current SSP Delivered`, `Current Remaining Qty`, `Current Remaining SSP`, `Current Remaining Allocation`, `Current Remaining Billing`, `Current Unit SSP`, `Current Remaining Unit Rev Rec`, six cumulatives, `Current Contract Position - POB`, `Current Contract Position - Contract Level`, `Current Reclass to UAR` | L1028-1089 |
| Version keys | `Processing Time Log` = `pd.Timestamp.now()`, local, naive and identical for the whole batch; `Record Unique ID without time`; `Record Unique ID` | L1112-1121 |
| Carried unchanged | the 12 setup columns (contract, POB, SKU, POB dates, stratification, original price and quantity, selling entity, SSP version, deferred revenue and unbilled A/R accounts); 6 SKU_SSP attributes; 9 `Original ...` allocation columns | via merge |
| Excel files | **None** | n/a |
| Popups | Success: `QMessageBox.information("Rev Rec Success", "Rev Rec has been processed with uploaded deliveries and/or billings for the current date :)")`. Failures: see Section 2 | L1156-1157 |
| Transaction semantics | One `DataFrame.to_sql(..., if_exists="append")` call. No explicit transaction, duplicate check or idempotency key | L1154 |

---

## 2. Validation rules

The rules run in the order listed. "Stop" means nothing is written. The Harness column cites the scenario IDs from Section 5.4, run against the unmodified legacy code.

| ID | Stage | Exact condition | Popup(s): kind, title, text | Effect | Lines | Harness |
|---|---|---|---|---|---|---|
| VR-delivery-01 | File pick | `if file_path:` is false (dialog cancelled) | none | No-op | L827-831 | n/a |
| VR-delivery-02 | Date prompt | `if ok:` is false (prompt cancelled) | none | No-op | L832-834 | n/a |
| VR-delivery-03 | Date parse | `QDate.fromString(input_text, "yyyy-MM-dd").isValid()` is false (wrong pattern or impossible date) | warning, "Invalid Date", "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." | Stop | L835-838 | E21 (`2023-02-30`; Qt parsing emulated) |
| VR-delivery-04 | Header | `missing_titles or extra_titles` against the 9 expected titles | information, "File Upload Error", "Error: The Excel file has incorrect or missing column titles."; then, if any, information "Missing fields:" with a comma-joined list; then, if any, information "Extra fields:" with a comma-joined list | Stop | L846-862 | E15 |
| VR-delivery-05 | Numeric type | `pd.to_numeric(df_progress[column], errors='raise')` raises `ValueError`/`TypeError`. Columns are checked in order `Current Delivery`, `Current Billing`, `Current Pre-ASC606 Revenue (Net Design Only)`; only the first failure is reported | information, "Format Error", "Error: The column '{column}' should contain numeric values." | Stop | L852-854, L866-870, L875-878 | E17 |
| VR-delivery-06 | Numeric blank | `df_progress[column].isna().any()`, same column order | same text as VR-delivery-05 | Stop | L871-874 | E16 |
| VR-delivery-07 | Match to contract | Outer merge of the latest `Contract_Live` rows with the aggregated upload on `Record Unique ID without time` (`"{Contract} {POB} {SKU}"`); any row with `_merge == 'right_only'` | information, "Delivery/Billing load failed", "Below deliveries are not found with a match in contracts. Re-upload the file after fixes! \nFile position(s): \n{failed_list}"; then `raise Exception` -> critical, "Error Notification", "The process is stopped for users to fix the file" | Stop | L918-942, L1163-1168 | E06, E06b. **Defect:** `failed_list` is the merged frame's index + 1, not the worksheet row. Both scenarios reported "9" for unmatched rows at data rows 2 and 1 |
| VR-delivery-08 | Over-delivery / over-billing (pre-calculation) | For rows of contracts with activity: `Current Remaining Qty < Current Delivery_progress` (**all** strata, VC included), or `Current Remaining Billing < Current Billing_progress` for `ASC 606 Stratification != "VC"`. Applied to the aggregated upload per key; exact float comparison, no tolerance | information, "Delivery/Billing load failed", "Qty or billing loaded are greater than the remaining of the POBs. Check your uploads please."; then critical, "Error Notification", "The process is stopped for users to fix the file" | Stop | L959-974 | E11, E12, E18 |
| VR-delivery-09 | Negative balances (post-calculation) | `(merged["Current Remaining Qty"] < 0).any()` (all strata), or `Current Remaining Billing < 0` for strata != "VC" | information, "Delivery/Billing load failed", "Qty returned or refund are greater than previous total delivery or total amount previously paid by the customer causing the total qty delivered or total billing to date to be negative. Check your uploads please."; then critical "Error Notification" | Stop | L1097-1108 | E03. **Defect:** the code tests *remaining* balances, which is logically the same as VR-delivery-08. The comment and message describe *cumulative* delivery or billing going negative, which is never tested. Over-returns and over-refunds pass |
| VR-delivery-10 | Table exists | `sqlite_master` lookup finds no `Contract_Live` | intended: critical, "Error Notification", "No contract table is found!" | Stop | L1126-1134, L1158-1160 | E10. **Unreachable:** the SELECT at L882-892 fails first, and the critical popup shows pandas' `Execution failed on sql '...': no such table: Contract_Live` |
| VR-delivery-11 | Catch-all | any other `Exception` | critical, "Error Notification", `str(e)` | Stop (append is a single call, so no partial writes were observed) | L1163-1168 | E06-E12 |
| VR-delivery-12 | Silent abort | `except TypeError: pass`, meant for a cancelled dialog, also swallows **any** `TypeError` during processing, such as a numeric-only `POB Unique ID` / `Contract Unique Name` / `SKU Name` in the concatenation at L918-922 | **none** | Stop with no feedback | L1161-1162 | E02 |
| VR-delivery-13 | Silent row drop | A blank value in any of the six groupby keys (`Contract Unique Name`, `POB Unique ID`, `SKU Name`, `Memo 1`, `Memo 2`, `Memo 3`) drops the row, because pandas `groupby` defaults to `dropna=True` | Success popup is still shown | Row lost; the rest is processed | L909-913 | E01 (0 rows appended, success shown), E01b (Contract 1 row lost, Contract 2 processed) |
| VR-delivery-14 | Silent duplicate | Same contract, POB and SKU but different memo text: rows are not aggregated, so the merge yields two rows for one POB. Each is checked against the same remaining balance (6 of 5 units accepted), both are appended with the same `Processing Time Log`, and the next read keeps only the first | Success popup | Double-counted contract position in that version; delivery lost in the next version | L909-913, L928-930, L900-902 | E04, E04b |
| VR-delivery-15 | Empty file | Header-only workbook | Success popup | Nothing appended | L843-1157 | E05 |
| VR-delivery-16 | Success | append completed | information, "Rev Rec Success", "Rev Rec has been processed with uploaded deliveries and/or billings for the current date :)" | Commit | L1154-1157 | all happy paths |

**Checks the legacy app never performs** (verified by harness where cited):

| Gap | Consequence | Harness |
|---|---|---|
| No idempotency or duplicate-upload detection | Re-uploading the same file doubles deliveries and billings, bounded only by VR-delivery-08 | E08 |
| No ordering check between the input period and `Previous Period` / latest version | Backdated events are accepted. The version order follows processing time while journal entry reports filter on `Current Period` | E09 |
| No check against `POB Start Date` / `POB End Date` | Delivery outside the POB term is accepted | code inspection |
| No floor on cumulative delivery or billing | Returns and refunds can exceed what was delivered or billed (cumulative delivery -1, billing -50) | E03 |
| VC lines excluded from billing checks | A VC credit memo larger than the estimated VC is accepted and pushes the contract into an asset position | E13 |
| No row-level error report; the Excel row number is not preserved | Users cannot locate failing rows (VR-delivery-07) | E06 |
| No user identity, approval, reason code, currency or entity-balancing checks | Weak SOX evidence: only `Processing Time Log` is logged | code inspection |

---

## 3. Calculation logic

### 3.0 Notation

For POB line *i* in contract *c* at upload event *t*, where t-1 is the latest stored version:

| Symbol | Column | Symbol | Column |
|---|---|---|---|
| q | aggregated upload `Current Delivery` (0 when the POB has no upload row) | RQ | `Current Remaining Qty` |
| b | aggregated upload `Current Billing` (0 when none) | RSSP | `Current Remaining SSP` |
| p | aggregated upload `Current Pre-ASC606 Revenue (Net Design Only)` (0 when none) | RALLOC | `Current Remaining Allocation` |
| RR | `Current Rev Rec` | RBILL | `Current Remaining Billing` |
| SSPdel | `Current SSP Delivered` | USSP | `Current Unit SSP` |
| CD, CRR, CB, CP606, CCU, CSSP | cumulative delivery, rev rec, billing, pre-606 revenue, catch-up, SSP delivered | URR | `Current Remaining Unit Rev Rec` |
| POS | `Current Contract Position - POB` | POSC | `Current Contract Position - Contract Level` |
| RECL | `Current Reclass to UAR` | f0(x) | `x.fillna(0)` |

All arithmetic is pandas `float64`/`int64`. There is no `Decimal`, no currency rounding in stored rows and no residual plug (Section 3.13).

### 3.1 Upstream state consumed (set by contract setup, L682-741; may be re-set by modifications)

The delivery function never recomputes SSP or allocation. It consumes `Current Unit SSP` and `Current Remaining Unit Rev Rec` as fixed rates for the event. Those rates come from:

| Column | Formula | Lines |
|---|---|---|
| `Original SSP - Midpoint` | Qty x SKU Unit List Price x (1 - Midpoint Discount %) | L682-683 |
| `Original SSP - Higher` | Midpoint x (1 + SSP Range %) | L684-686 |
| `Original SSP - Lower` | Midpoint x (1 - SSP Range %) | L687-689 |
| `Original Extended SSP` | clamp(Selling Price, Lower, Higher): Higher if price > Higher; Lower if price < Lower; else the price itself | L692-700 |
| `Original Total Contract Price` | sum of selling prices in the contract, **including negative VC lines** | L704-705 |
| `Original Total Contract SSP` | sum of Extended SSP | L707-708 |
| `Original Allocation` | Extended SSP / Total SSP x Total Price (relative SSP) | L710-711 |
| `Original Unit SSP`, `Original Unit Rev Rec` | Extended SSP / Qty; Allocation / Qty | L713-717 |
| Initial `Current Remaining *` | Qty, Extended SSP, Allocation, Selling Price; all cumulatives 0 | L736-756 |

Consequences for delivery (facts):

- The discount or premium (Total Price vs Total SSP) is spread over **every** line in proportion to Extended SSP, including material-right lines. There is no specific discount allocation and no residual approach.
- A VC line (list price 0, so SSP 0) receives 0 allocation. Its negative price lowers Total Price, so the VC reduction is spread proportionally over all other lines, and delivering the VC line recognizes nothing (URR = 0).
- The SSP range acts as a "price within range is SSP" policy. Prices outside the range snap to the nearer bound.

### 3.2 Pre-processing

| Step | Logic | Lines |
|---|---|---|
| Aggregate upload | `groupby([Contract, POB, SKU, Memo 1, Memo 2, Memo 3]).sum()` over the three numeric columns. NaN keys are dropped (VR-delivery-13); differing memos are not merged (VR-delivery-14) | L909-913 |
| Join key | `"{Contract Unique Name} {POB Unique ID} {SKU Name}"` | L918-922 |
| Latest state | max `Processing Time Log` per key via SQL, then pandas `idxmax` | L881-907 |
| Merge | outer join on key; upload columns that overlap get the suffix `_progress` | L928-930 |
| Activity filter | `Contract Unique Name` is kept if any row has `Current Delivery_progress` not null **and** `Current Billing_progress` not null **and** `Current Pre-ASC606 Revenue (Net Design Only)` not null. **Bug:** the third test reads the `Contract_Live` copy, not `_progress`. POBs created by modifications store NULL there, so a contract whose only uploaded rows are such POBs is skipped silently (E23: success popup, 0 rows appended) | L948-956 |
| Scope | Every POB of an active contract is re-versioned, including POBs without upload rows | L955-956 |

### 3.3 Roll-forward (L980-1009)

`Previous X := f0(Current X)` for the 15 numeric state columns listed in Section 1.4. `Previous Period := Current Period` (not filled).

### 3.4 Event inputs (L1011-1026)

```
q      := f0(Current Delivery_progress)
b      := f0(Current Billing_progress)
p      := f0(Current Pre-ASC606 Revenue (Net Design Only)_progress)
Memo k := Memo k_progress if not null else prior Memo k          # L1015-1017
Current Cumulative Catchup - Disclosure Only := 0                # L1023
Current Period := datetime(prompt date, 00:00:00)                # L1025-1026, all rows of active contracts
```

### 3.5 Revenue and SSP delivered (L1028-1031)

```
RR_t     = f0(q) x f0(URR_{t-1})        # rate from the PRIOR version
SSPdel_t = f0(q) x f0(USSP_{t-1})
```

- The measure of progress is units delivered, and revenue is linear in quantity.
- A return (q < 0) reverses revenue at the **current remaining** unit rate, not the rate at which the units were recognized. Without modifications the two are equal. After a prospective modification they diverge (E25: returning 1 unit recognized at 118.533201 reversed only 92.533678, leaving 25.999523 of revenue on zero units delivered).
- After full delivery, URR is 0 (E19), so a later return reverses **no** revenue. If a floating residue survives, URR is `inf` and the return books `-inf` (E22).

### 3.6 Remaining balances (L1032-1042)

```
RQ_t     = f0(RQ_{t-1})     - q
RSSP_t   = f0(RSSP_{t-1})   - q x f0(USSP_{t-1})
RALLOC_t = f0(RALLOC_{t-1}) - RR_t
RBILL_t  = f0(RBILL_{t-1})  - b
```

### 3.7 Unit-rate refresh (L1045-1050)

```
USSP_t = (RSSP_t   / RQ_t).fillna(0)
URR_t  = (RALLOC_t / RQ_t).fillna(0)
```

- 0/0 gives NaN, which becomes 0. **Non-zero/0 gives +-inf, which is not caught.** Delivering all 5 units of Contract 1 POB #1 in one event leaves `RALLOC = 5.684341886080802e-14`, so `URR = inf` (E22a). The next event with q = 0 stores `RR = NaN` (0 x inf; E20b). A return stores `RR = -inf` and `POSC = NaN` (E22b).
- Without modifications and residues, RALLOC/RQ is invariant, so the rate stays constant across partial deliveries.
- There is **no final-delivery true-up**: the last unit is recognized at q x rate rather than the remaining allocation.

### 3.8 Cumulatives (L1053-1072)

```
CD_t    = f0(CD_{t-1})    + q
CRR_t   = f0(CRR_{t-1})   + f0(RR_t)
CB_t    = f0(CB_{t-1})    + b
CP606_t = f0(CP606_{t-1}) + p
CCU_t   = f0(CCU_{t-1})   + 0          # catch-up only arises from modifications
CSSP_t  = f0(CSSP_{t-1})  + f0(SSPdel_t)
```

### 3.9 Contract position (L1073-1079)

```
POS_i  = f0(CB_i) - f0(CRR_i)           # >0 contract liability (billed ahead); <0 contract asset (unbilled)
POSC_c = sum over i in c of POS_i       # includes VC lines and POBs of different Selling Entities
```

### 3.10 Reclass to unbilled A/R (L1081-1089)

```
if POSC_c < 0:
    RECL_i = (-POSC_c) / sum over j in c of CSSP_j  x  CSSP_i     # np.where evaluates both branches
else:
    RECL_i = 0
RECL_i := 0 where ASC 606 Stratification == "VC"                  # L1088-1089
```

- RECL is a **balance**, not a movement. Each version holds the target reclass. Journal entries reverse `Previous Reclass to UAR` and book `Current Reclass to UAR` (Section 3.12).
- Weights are cumulative **SSP delivered**, not per-POB positions or revenue. A POB billed ahead can receive a share, and a POB with billing but no delivery receives none (E20b: POB #3 billed 400 got 0).
- With no modifications and zero billing, SSP weights reproduce each POB's own revenue (Contract 2, 2023-03-31: 58.846154 and 46.153846). After modifications changed unit rates they no longer do.
- The VC override is harmless only because VC lines have SSP 0. A VC SKU with a non-zero list price would make the sum of RECL differ from -POSC (inference).
- If POSC < 0 and the sum of CSSP is 0, the division yields NaN or inf (inference, not reproduced).

### 3.11 Versioning keys (L1112-1121)

See Section 4.

### 3.12 Downstream journal entry derivation (not in scope; needed for parity)

For each version row whose `Current Period` is within [start, end] (L2574-2576). Positive = debit.

| JE line | Account | Amount | Grouping key | Report |
|---|---|---|---|---|
| Relieve deferred revenue | `Deferred Revenue Account` | +round(RR, 4) | Contract | Gross (L2594-2598), Adjustment (L2920-2924) |
| Recognize revenue | `Revenue Account` | -round(RR, 4) | Contract POB SKU | both |
| Reverse prior reclass | Deferred Revenue / Unbilled A/R | +round(Previous RECL, 4) / -round(Previous RECL, 4) | Contract | both |
| Book current reclass | Deferred Revenue / Unbilled A/R | -round(RECL, 4) / +round(RECL, 4) | Contract | both |
| Reverse legacy revenue | `Revenue Account` / Deferred Revenue | +round(p, 4) / -round(p, 4) | POB / Contract | Adjustment only (L2965-2979) |

Lines with `round(Amount, 2) == 0` are dropped, grouped by (key, account), summed, dropped again if 0, then rounded to 2 dp (L2643-2651). **Billing entries (Dr A/R, Cr Deferred Revenue) are never produced**; eRev assumes the ERP posts them. Rounding per account after aggregation can leave a 0.01 imbalance, because there is no balancing plug (inference).

### 3.13 Numeric representation

| Topic | Behaviour | Evidence |
|---|---|---|
| Precision | IEEE float64 throughout; quantities may be fractional (0.4, 0.5, 2.5) | UAT 3.31, 10.31 |
| Stored rounding | None. Full floats are stored; residues appear as `-0.000000` (Contract 1 POB #1 after the 2023-04-30 return) and `5.68e-14` | harness |
| Report rounding | `round(4)` per line, then `round(2)` after grouping (Python/NumPy round-half-to-even) | L2598, L2651 |
| SQLite types | Column affinity comes from the first `to_sql(replace)` at contract setup (L812): `INTEGER` where setup wrote ints (for example `Current Rev Rec` = 0). Non-integral values are stored as REAL, so there is no truncation. In the final UAT table `Current Rev Rec` is stored as integer in 72 rows and real in 34 | harness typeof query |
| inf / NaN | Persist to SQLite (`NULL` for NaN, `Inf` for inf) with a success popup | E20b, E22b |
| Version independence | pandas 2.0.3 and pandas 3.0.5 produced identical 106-row final tables across all 69 non-timestamp columns | `diff_versions.py` |

---

## 4. State transitions and versioning

### 4.1 Record identity

| Column | Construction | Example (golden DB) | Lines |
|---|---|---|---|
| `Record Unique ID without time` | `"{Contract Unique Name} {POB Unique ID} {SKU Name}"` | `Contract 1 POB #1 Hardware 1` | L1113-1117 |
| `Processing Time Log` | `pd.Timestamp.now()`, local, timezone-naive, **one value for the whole batch**, so it doubles as a batch ID | `2025-05-09 09:12:33.441992` | L1112 |
| `Record Unique ID` | `str(Processing Time Log) + " " + key` | `2025-05-09 09:12:33.441992 Contract 1 POB #1 Hardware 1` | L1118-1121 |

The key is a space-joined string with no delimiter escaping. `Contract "A B"` + POB `"C"` collides with `Contract "A"` + POB `"B C"` when the SKU matches (inference).

### 4.2 Append-only version chain

```
version(t-1)  --event t-->  version(t)
  Previous X(t) = Current X(t-1)          # 15 numeric columns + Previous Period
  Current  X(t) = f(Current X(t-1), upload)
  Original X, setup and SKU attributes: carried unchanged
  Processing Time Log(t) = now()
```

| Property | Legacy behaviour | Evidence |
|---|---|---|
| Write mode | `to_sql(if_exists="append")`: no UPDATE and no DELETE | L1154 |
| Rows per event | One row per POB for every contract with a matched upload row. Other contracts get no new version | 2023-02-28 batch: 12 rows for Contracts 1, 3, 4; Contract 2 untouched |
| Current version | Max `Processing Time Log` per key. On a tie the first row wins | L882-902, E04b |
| Version order | Processing order, **not** `Current Period` order | E09 |
| Period semantics | `Current Period` is the event date. `Previous Period` is the prior version's event date (setup date, or a modification date) | harness tables |
| Status | No status column. States are implicit (below) | n/a |
| Undo | None in-app. Recovery is "Restore from Backup" (L330) or "Purge Contracts" (L477), both premium | code |

### 4.3 Implicit POB states (inference from balances)

| State | Condition | Transition in this function |
|---|---|---|
| Set up | CD = 0, CB = 0, version from setup (all cumulatives 0) | delivery or billing -> In progress |
| In progress | 0 < CD < original quantity, or CB > 0 | further delivery -> Fully delivered; return -> In progress or Set up |
| Fully delivered | RQ = 0; rates 0 (or inf with a residue) | return -> In progress, but URR = 0 recognizes no reversal (E19) |
| Over-returned (invalid, accepted) | CD < 0 or CB < 0 | none (E03) |
| Modified | mods append versions with re-set rates | later deliveries use new rates (E25) |

### 4.4 Interactions with other buttons

- Modifications (L1170-2539) append versions with the same 71-column layout. They may re-set `Current Unit SSP`, `Current Remaining Unit Rev Rec`, remaining balances and catch-up columns, and they leave `Current Pre-ASC606 Revenue (Net Design Only)` NULL on new POBs (E23).
- Journal entries, Contract History and Latest Contract read versions by `Current Period` (reports) or max `Processing Time Log` (latest).

---

## 5. Worked example (hand-traced, then verified)

### 5.1 Method

- **Harness:** the unmodified `eRev.py` is executed with PySide6 stubbed (dialog answers queued, popups recorded) in `~/dev/erev/.scratch/legacy-delivery/run/`, with Python 3.11, pandas 2.0.3 and numpy 1.24.4 (period-appropriate). It was repeated with pandas 3.0.5.
- **Sequence:** SKU SSP Template -> Contract Setup 1.1.2023 -> Contract Setup 2.1.2023 -> Delivery 1.31.2023 -> **golden check** -> Delivery 2.28 -> 3.31 -> 4.30 -> the six modification UATs (05.15 retro, 05.31 POB-specific VC, 06.15 prospective, 07.15 prospective, 08.15 retro, 09.15 prospective) -> Full delivery 10.31.2023.
- **Golden check:** the 24 rows produced after the 1.31 upload match `ops/libnew/libwarm/db/ASC606.db` on every non-timestamp column (0 mismatches, tolerance 1e-9).
- Period dates were taken from the file names. The legacy app takes the date from the prompt, not the file.

### 5.2 UAT files in scope

| File | Date entered | What it exercises | Rows appended |
|---|---|---|---|
| `Contract Progress Tracking Template 1.31.2023.xlsx` | 2023-01-31 | Contract 1 partial deliveries with a **duplicate POB #1 row** (aggregation) and pre-606 revenue; Contract 2 delivery with no billing (contract asset and reclass) | 8 |
| `Contract Progress Tracking Template 2.28.2023.xlsx` | 2023-02-28 | Further delivery; Contract 3 consulting billed ahead (liability); Contract 4 hardware | 12 |
| `Contract Progress Tracking Template 3.31.2023.xlsx` | 2023-03-31 | Fractional delivery 0.4; Contract 4 VC line delivery 0.5 with a -100 credit | 12 |
| `Contract Progress Tracking Template 4.30.2023 - Return & Zero delivery billing.xlsx` | 2023-04-30 | Return -3 units / -200; billing with zero delivery; billing 20 against an unbilled position | 8 |
| `Full delivery 10.31.2023.xlsx` (sheet `Sheet1`) | 2023-10-31 | Final delivery of every open POB after the modifications, including a material right (1,000 units) and a POB created by a modification (Contract 3 POB #5) | 17 |

### 5.3 Contract 2: setup allocation (L682-717)

| POB | Stratification | Qty | Price | List | Disc | Range | Midpoint | Higher | Lower | Extended SSP | Allocation (x 900/1170) | Unit SSP | Unit Rev Rec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POB #1 | Hardware 1 | 8 | 600 | 100 | 10% | 15% | 720 | 828 | 612 | **612** (price below Lower) | 470.769231 | 76.5 | 58.846154 |
| POB #2 | Software 1 | 3 | 400 | 200 | 20% | 15% | 480 | 552 | 408 | **408** (price below Lower) | 313.846154 | 136 | 104.615385 |
| POB #3 | Consulting 1 | 1 | 0 | 300 | 50% | 0% | 150 | 150 | 150 | **150** (price below Lower) | 115.384615 | 150 | 115.384615 |
| VC #1 | VC | 1 | -100 | 0 | 0% | 0% | 0 | 0 | 0 | **0** | 0 | 0 | 0 |
| **Total** | | | **900** | | | | | | | **1,170** | **900.000000** | | |

### 5.4 Contract 2: event 2023-01-31 (upload row: POB #1, delivery 1, billing 0, pre-606 0)

| Column | POB #1 formula -> value | POB #2 | POB #3 | VC #1 |
|---|---|---|---|---|
| RR | 1 x 58.846154 = **58.846154** | 0 | 0 | 0 |
| SSPdel | 1 x 76.5 = 76.5 | 0 | 0 | 0 |
| RQ / RSSP / RALLOC / RBILL | 7 / 535.5 / 411.923077 / 600 | 3 / 408 / 313.846154 / 400 | 1 / 150 / 115.384615 / 0 | 1 / 0 / 0 / -100 |
| USSP / URR | 535.5/7 = 76.5 / 411.923077/7 = 58.846154 | 136 / 104.615385 | 150 / 115.384615 | 0 / 0 |
| CD / CRR / CB / CSSP | 1 / 58.846154 / 0 / 76.5 | 0 | 0 | 0 |
| POS = CB - CRR | **-58.846154** | 0 | 0 | 0 |
| POSC | **-58.846154** (net contract asset) | same | same | same |
| RECL | 58.846154 x 76.5/76.5 = **58.846154** | 0 x ... = 0 | 0 | forced 0 |

Harness gross JE for 2023-01-31, Contract 2 (matches the golden DB state): **Dr 15002 Unbilled A/R 58.85 / Cr 5001 Revenue 58.85**. Account 21002 nets to zero (+58.85 revenue relief, -58.85 reclass) and is suppressed.

### 5.5 Contract 2: event 2023-03-31 (POB #3, delivery 0.4, billing 0)

| Column | POB #1 | POB #3 |
|---|---|---|
| RR | 0 | 0.4 x 115.384615 = **46.153846** |
| SSPdel | 0 | 0.4 x 150 = 60 |
| RQ / RSSP / RALLOC | 7 / 535.5 / 411.923077 | 0.6 / 90 / 69.230769 |
| USSP / URR | 76.5 / 58.846154 | 90/0.6 = 150 / 69.230769/0.6 = 115.384615 |
| CRR / CB / CSSP | 58.846154 / 0 / 76.5 | 46.153846 / 0 / 60 |
| POS | -58.846154 | -46.153846 |
| POSC | **-105.000000** | same |
| RECL = 105 x CSSP / 136.5 | 105 x 76.5/136.5 = **58.846154** | 105 x 60/136.5 = **46.153846** |
| Previous RECL | 58.846154 | 0 |

JE (harness): **Dr 15002 46.15 / Cr 5003 Revenue 46.15**. Account 21002 nets +46.15 relief +58.85 reversal -105.00 reclass = 0.

### 5.6 Contract 2: event 2023-04-30 (POB #1, delivery 0, billing 20)

| Column | POB #1 | POB #3 |
|---|---|---|
| RR | 0 | 0 |
| RBILL / CB | 600 - 20 = 580 / 20 | 0 / 0 |
| POS | 20 - 58.846154 = **-38.846154** | -46.153846 |
| POSC | **-85.000000** | same |
| RECL | 85 x 76.5/136.5 = **47.637363** | 85 x 60/136.5 = **37.362637** |

JE (harness): reverse 105.00 and book 85.00, giving **Dr 21002 20.00 / Cr 15002 20.00**. With the ERP invoice (Dr A/R 20 / Cr 21002 20), the net effect moves 20 from contract asset to receivable. That is the intended outcome.

### 5.7 Contract 1: setup allocation, then events 2023-01-31, 2023-02-28, 2023-04-30

| POB | Qty | Price | Midpoint / Higher / Lower | Extended SSP | Allocation (x 1300/2018) | Unit SSP | URR |
|---|---|---|---|---|---|---|---|
| POB #1 Hardware 1 | 5 | 500 | 450 / 517.5 / 382.5 | 500 (within range) | 322.101090 | 100 | 64.420218 |
| POB #2 Software 1 | 2 | 400 | 320 / 368 / 272 | 368 (capped at Higher) | 237.066402 | 184 | 118.533201 |
| POB #3 Consulting 1 | 1 | 400 | 150 / 150 / 150 | 150 | 96.630327 | 150 | 96.630327 |
| POB #4 Material Right - Hardware | 1000 | 0 | 1000 / 1000 / 1000 | 1000 | 644.202180 | 1 | 0.644202 |
| Total | | 1,300 | | 2,018 | 1,300.000000 | | |

**2023-01-31:** two identical POB #1 rows (1 unit, 50 billing each) are aggregated to q = 2, b = 100.

| POB | q | b | p | RR | CRR | CB | POS |
|---|---|---|---|---|---|---|---|
| #1 | 2 | 100 | 0 | 2 x 64.420218 = 128.840436 | 128.840436 | 100 | -28.840436 |
| #2 | 1 | 100 | 66 | 118.533201 | 118.533201 | 100 | -18.533201 |
| #3 | 0.5 | 100 | 88 | 48.315164 | 48.315164 | 100 | +51.684836 |
| #4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| POSC | | | | | | | **+4.311199**, so RECL = 0 |

- Gross JE (harness): **Dr 21001 295.69 / Cr 5001 128.84, Cr 5002 118.53, Cr 5003 48.32**.
- Adjustment JE (harness): Dr 21001 141.69 (295.69 - 66 - 88); Cr 5001 128.84; Cr 5002 52.53 (118.53 - 66); Dr 5003 39.68 (88 - 48.32).

**2023-02-28:** POB #1 q = 1, b = 100, so RR = 64.420218, CD = 3, CRR = 193.260654, CB = 200, POS = 6.739346, POSC = 39.890981, RECL = 0. JE: Dr 21001 64.42 / Cr 5001 64.42.

**2023-04-30 (return and zero-delivery billing):**

| POB | q | b | RR | RQ / RALLOC / RBILL | CD / CRR / CB | POS |
|---|---|---|---|---|---|---|
| #1 | -3 | -200 | -3 x 64.420218 = **-193.260654** | 5 / 322.101090 / 500 | 0 / ~0 (IEEE -0.000000) / 0 | ~0 |
| #2 | 0 | 300 | 0 | 1 / 118.533201 / 0 | 1 / 118.533201 / 400 | 281.466799 |
| #3 | 0 | 0 | 0 | 0.5 / 48.315164 / 300 | 0.5 / 48.315164 / 100 | 51.684836 |
| POSC | | | | | | **333.151635**, RECL = 0 |

JE (harness): **Dr 5001 193.26 / Cr 21001 193.26**. The -200 credit memo and +300 invoice are ERP entries outside eRev. After the return, POB #1 again shows 5 units remaining to deliver and 500 remaining to bill.

### 5.8 Full delivery 2023-10-31 (after the modification UATs)

- All 17 latest POB rows end with RQ = 0 and unit rates exactly 0.0; no `inf` arose in this UAT.
- Per contract, CRR equals CB: Contract 1 800, Contract 2 1,100, Contract 3 2,600, Contract 4 1,200. So POSC = 0 and RECL = 0.
- POB-level positions stay non-zero and offset within each contract (for example Contract 3 POB #5 = -268.113933; Contract 1 POB #4 material right = -502.900425).
- Gross JE totals (harness): Contract 1 Dr 21001 638.45; Contract 2 Dr 21002 1,080.00 / Cr 15002 90.19 (reversal of the prior reclass); Contract 3 Dr 21001 2,351.91; Contract 4 Dr 21002 973.48; each against revenue credits.

### 5.9 Harness scenario catalogue (edge cases; pandas 2.0.3)

| ID | Scenario | Observed legacy outcome |
|---|---|---|
| E01 | Only row has blank `Memo 1` | Success popup; **0 rows appended** |
| E01b | Blank-memo row (Contract 1) + valid row (Contract 2) | Contract 1 silently lost; Contract 2 processed |
| E02 | Numeric `POB Unique ID` | **No popup at all**; 0 rows |
| E03 | Return 3 of 2 delivered; refund 150 of 100 billed | Accepted: CD = -1, CB = -50, CRR = -64.420218, RQ = 6 (above the original 5) |
| E04 / E04b | Same POB twice with different memos (3 + 3 of 5) | Accepted; two rows for one POB, POSC doubled (213.478692); next event keeps only one (POSC 106.739346) |
| E05 | Header-only file | Success popup; 0 rows |
| E06 / E06b | Unmatched contract at data row 2 / data row 1 | "File position(s): 9" in both cases |
| E08 | Same 1.31 file uploaded twice | Accepted; deliveries doubled (POB #2 fully delivered) |
| E09 | Period 2022-12-31 after a 2023-01-31 version | Accepted; Current Period earlier than Previous Period |
| E10 | No `Contract_Live` table | Critical popup with the pandas SQL error text |
| E11 / E12 / E18 | Over-delivery, over-billing, VC over-delivery | Blocked (VR-delivery-08) |
| E13 | VC credit -150 against a VC of -100 | Accepted; POSC -208.846154, reclass 208.846154 |
| E19 | Return 1 unit after full delivery | RR = 0; revenue stays at the full allocation with 1 unit undelivered |
| E20 / E20b | Deliver all 5 units in one event, then another event | URR = inf, then RR = NaN (NULL) |
| E22 | Return after the inf rate | RR = -inf, CRR = -inf, POS = inf, POSC = NaN; success popup |
| E23 | Only row targets a POB created by a modification (NULL pre-606 column) | Success popup; 0 rows (activity-filter bug) |
| E24 | Numbers written as text cells | Read as numbers by `read_excel`; no defect reproduced |
| E25 | Return 1 unit after a prospective modification changed the rate | Reversed 92.533678 vs 118.533201 recognized; 25.999523 revenue left on 0 units |

Cross-check with the separate golden-master replay (doc 07, pandas 2.2.3, `docs/legacy/golden/`): steps 04-07 and 14 agree with the values above. Examples: `rollforward-04-Contract1` position 4.3112, `rollforward-07-Contract2` position -85.0, `je-step-07` account 5001 debit 193.26 and 15002 credit 20.00.

---

## 6. Accounting assessment

**Conclusion.** The delivery engine is a transparent "units delivered x fixed unit rate" model. Its contract-level net position is correct, and its journal design (store the balance, then telescope the movements) is sound. It is fit for point-in-time goods and unit-priced services in single-currency, single-entity contracts. It is incomplete for over-time obligations, returns and cross-entity contracts. Its numerical and completeness defects (inf/NaN, silent row drops, duplicate processing) would fail completeness and accuracy control objectives in production.

Source IDs in brackets refer to Section 6.5. Paragraph wording was checked against the FASB ASU 2014-09 text where [S-F1] is cited. **These are research conclusions for system design, not an accounting opinion, and require review by a qualified revenue accountant.**

### 6.1 Correct under ASC 606

| Area | Legacy behaviour | Assessment | Authority |
|---|---|---|---|
| Rates consumed by events | Unit rates come from relative-SSP allocation at inception and are not re-derived when SSPs change | Consistent with the relative-SSP basis and with the rule not to reallocate for later SSP changes | ASC 606-10-32-31 [S-D5]; 606-10-32-43 [S-D8, S-F1] |
| Contract discount | Spread over all POBs by relative SSP | Correct default | 606-10-32-36 [S-D6] |
| Contract-wide VC | Negative VC line lowers the transaction price and is spread by relative SSP; delivering the VC line recognizes nothing | Correct default when the criteria for allocating VC to specific obligations are not met. POB-specific VC is a separate button (doc 05) | 606-10-32-39 to 32-41 [S-D7] |
| $0-priced POB | Contract 2 POB #3 (price 0) recognizes its allocated 115.384615 when delivered | Correct: revenue follows the allocation, not the invoice price | 606-10-32-31 [S-D5] |
| SSP range | A price inside the band is used as SSP; outside, the nearest bound | An acceptable practice where the range is narrow and concentrated. The +-15% band is a policy judgement | DART 7.3.3.6 [S-D5] |
| Measure of progress | Units delivered; one method per POB | Units produced or delivered is a listed output method, applied as a single method per obligation | 606-10-55-17, 606-10-25-32 [S-D10, S-F1] |
| Net contract position | Billing minus revenue, summed per contract; asset or liability by sign | Matches presenting a contract as a contract asset or contract liability, netted within the contract | 606-10-45-1 [S-D2, S-F1]; BC317 [S-D2] |
| Invoice booked Dr A/R / Cr deferred revenue in the ERP | Receivable on invoice; liability when billed ahead | Acceptable where the invoiced amount is an unconditional right; practice accepts recording receivables on invoicing | 606-10-45-2, 45-4 [S-D4, S-F1] |
| Catch-up disclosure column | Always 0 for delivery events | Correct: deliveries are not transaction price changes. The column feeds the prior-period disclosure only through modifications | 606-10-50-12A [S-D13] |
| Journal design | Relieve deferred revenue for revenue; reverse the prior reclass; book the new reclass | Mechanically sound; movements telescope correctly (verified 2023-03-31 and 2023-04-30, Contract 2) | Bookkeeping design (no authority needed) |

### 6.2 Simplified (policy decisions; human review required)

| Area | Legacy simplification | Gap against the standard or practice | Authority |
|---|---|---|---|
| Contract asset vs receivable | Every net debit position goes to one "Unbilled A/R" account | A contract asset (conditional right) and a receivable (unconditional right) are presented separately, and each needs opening and closing balances disclosed | 606-10-45-3, 45-4 [S-D3, S-D4, S-F1]; 606-10-50-8 [S-D13] |
| Over-time obligations | No time-elapsed, input-method or right-to-invoice logic; `POB Start Date` / `End Date` unused; users type "units" | Progress must be remeasured each period, with changes treated as estimates; input methods and the right-to-invoice practical expedient are available | 606-10-25-32, 25-35, 55-18, 55-20, 55-21 [S-D10, S-F1] |
| Non-distinct bundles | Each SKU line progresses on its own quantity; `Distinct or Nondistinct` is ignored by delivery | Non-distinct promises are combined until a distinct bundle is identified, and measured with a single method of progress | 606-10-25-22 [S-F1]; 606-10-25-32 [S-D10] |
| Material rights | Recognized only when the user "delivers" the option line (1,000 units on 2023-10-31 recognized 502.900425) or through a modification | Option exercise and expiry need explicit events. Practice alternatives for exercise differ (separate contract vs modification), and consideration allocated to an option that expires unexercised is recognized as revenue at expiry | 606-10-55-42 [S-F1]; DART 11.7 [S-D12]; DART 11.12, 606-10-55-44 [S-D14] |
| Reclass allocation key | Net asset allocated to POB lines by cumulative SSP delivered | The standard does not prescribe how the net position is split across account strings. It is a presentation policy to document | Inference |
| Cross-entity contracts | Netting spans POBs with different `Selling Entity` and accounts | Netting within a contract is required for its presentation, but entity ledgers can then show debit balances in deferred revenue, so an entity-level policy is needed | [S-D2]; entity effect is inference |

### 6.3 Wrong or incomplete

| ID | Issue | Legacy behaviour (evidence) | Why it is wrong | Authority |
|---|---|---|---|---|
| AA-delivery-01 | No expected-returns model | Revenue is reversed only when an actual return is uploaded; there is no refund liability or recovery asset (UAT 4.30) | With a right of return, revenue is recognized only for products not expected to be returned, with a refund liability and an asset for the right to recover products, updated each period | 606-10-55-22 to 55-29 [S-D9, S-F1] |
| AA-delivery-02 | Return reverses the wrong amount | 0 after full delivery (E19); -inf after a residue (E22); the post-modification rate (E25: 25.999523 left on 0 units) | The reversal should equal the revenue recognized for the returned units, or be treated as a transaction price change | 606-10-32-42 to 32-45 [S-D8]; rate policy is inference |
| AA-delivery-03 | Over-returns and over-refunds accepted | CD -1, CB -50, CRR -64.420218 (E03) | Negative cumulative performance is meaningless; refunds above amounts billed are refund liabilities or payables, not negative billing | [S-D9]; inference |
| AA-delivery-04 | VC credits beyond the estimate accepted | A -150 credit against a -100 VC is accepted; allocation unchanged; asset rises to 208.846154 (E13) | A transaction price change is allocated to all POBs on the inception basis, with a catch-up for satisfied obligations, and the constraint is reassessed | 606-10-32-43 [S-D8, S-F1]; 606-10-32-11 to 32-13 [S-D9] |
| AA-delivery-05 | Invoice always treated as creating an unconditional right | eRev assumes the ERP grosses up A/R and deferred revenue on every invoice | A contract liability arises when payment is made or due, whichever is earlier; a receivable requires an unconditional right | 606-10-45-2, 45-4 [S-F1, S-D4] |
| AA-delivery-06 | No contract-balance roll-forward | Only per-version balances; no opening/closing split; no "revenue from opening contract liability" | Opening and closing receivables, contract assets and liabilities, and revenue recognized from the opening liability must be disclosed | 606-10-50-8 to 50-10 [S-D13] |
| AA-delivery-07 | Completeness failures reported as success | Blank memos (E01), numeric IDs (E02), POBs created by modifications uploaded alone (E23), duplicate memo keys (E04) | Revenue is understated or duplicated without detection | Control inference |
| AA-delivery-08 | No cutoff or duplicate controls | Same file twice doubles deliveries (E08); backdated events accepted (E09) | Revenue can be recorded twice or in a closed period, and period reports change retroactively | Control inference |
| AA-delivery-09 | Floating-point residues | `inf` rate after full delivery; NaN revenue; noise reclass (golden step 14: Contract 3 POSC -2.273737e-13 produced RECL 1.021751e-13 on POB #5) | Accuracy failure; non-finite values persist in the ledger source | Inference |
| AA-delivery-10 | JE rounding without a plug | Rounding per account after grouping | Entries can be off by 0.01 (not observed in UAT) | Inference |

### 6.4 Edge cases and expected treatment

| Edge case | Legacy outcome | Expected in eRev Cloud |
|---|---|---|
| Final delivery leaves a residue | URR = inf (E22a) | Recognize exactly the remaining allocation; rates 0 |
| Return after full delivery | RR 0 (E19) | Reverse at the carrying rate of the returned units |
| Return after a prospective modification | Reverses at the new rate (E25) | Reverse the revenue recognized for those units (default: average carrying rate; policy review) |
| Over-return / over-refund | Accepted (E03) | Reject, or send the excess to a refund liability |
| VC credit beyond the estimate | Accepted (E13) | Require a transaction-price-change event |
| POB created by a modification uploaded alone | Skipped silently (E23) | Processed |
| Same POB with different memos | Double-processed (E04) | Aggregate by POB; memos kept as event detail |
| Duplicate file | Doubled (E08) | Reject by batch hash / idempotency key |
| Backdated event | Accepted (E09) | Period lock plus an explicit adjustment workflow |
| Cross-entity contract | Nets across entities | Contract-level net for presentation; entity-balanced ledger entries |
| Billing above the POB price (reimbursables, tax) | Blocked (VR-delivery-08) | Non-revenue billing lines, or a transaction price change |
| Net asset with zero SSP delivered | NaN (inference) | Fallback allocation by POB position |
| Over-time service | Manual units only | Ratable / time-elapsed schedules from POB dates; input methods |

### 6.5 Sources

| ID | Source | Used for |
|---|---|---|
| S-D2 | Deloitte DART, Revenue Roadmap 14.1 Overview: [external website reference removed] | 606-10-45-1; BC317 net presentation per contract |
| S-D3 | DART 14.4 Contract Assets: [external website reference removed] | 606-10-45-3 contract asset vs receivable |
| S-D4 | DART 14.5 Receivables: [external website reference removed] | 606-10-45-4; receivables on invoicing (Example 14-3); gross receivable and liability for advance billing |
| S-D5 | DART 7.3 Determine the Stand-Alone Selling Price: [external website reference removed] | 606-10-32-31 to 32-35; SSP range practice (7.3.3.6) |
| S-D6 | DART 7.4 Allocation of a Discount: [external website reference removed] | 606-10-32-36 to 32-38 |
| S-D7 | DART 7.5 Allocation of Variable Consideration: [external website reference removed] | 606-10-32-39 to 32-41 |
| S-D8 | DART 7.6 Changes in the Transaction Price: [external website reference removed] | 606-10-32-42 to 32-45 |
| S-D9 | DART 6.3 Variable Consideration (incl. 6.3.5.3 right of return): [external website reference removed] | 606-10-32-5 to 32-13; 606-10-55-22 to 55-29 |
| S-D10 | DART 8.5 Measuring Progress: [external website reference removed] | 606-10-25-32, 25-35; 55-17 to 55-21 |
| S-D11 | DART 9.2 Types of Contract Modifications: [external website reference removed] | 606-10-25-12, 25-13 (context for E25) |
| S-D12 | DART 11.7 Customer's Exercise of a Material Right: [external website reference removed] | Material right exercise alternatives |
| S-D13 | DART 15.2 Contracts With Customers (disclosure): [external website reference removed] | 606-10-50-8 to 50-10, 50-12A |
| S-D14 | DART 11.12 Expiration of a Material Right: [external website reference removed] | Revenue on expiry of an unexercised option; 606-10-55-44 |
| S-F1 | FASB ASU 2014-09 Section A text, downloaded from [external website reference removed] by the 04-asc606-technical agent (`~/dev/erev/.scratch/04-asc606-technical/asu/ASU_2014-09_Section_A.txt`). The download URL was not recorded (open question) | Wording of 606-10-25-22, 25-31, 25-32, 25-35, 32-43, 32-44, 45-1 to 45-4, 55-17, 55-18, 55-23, 55-42 |

---

## 7. Port notes for eRev Cloud

### 7.1 Parity requirements (preserve)

| ID | Requirement | Legacy reference |
|---|---|---|
| PR-delivery-01 | Import the 9-column Progress Tracking template (contract, POB, SKU, delivery, billing, pre-606 revenue, memos 1-3) alongside API events | L846-848 |
| PR-delivery-02 | Sum rows for the same POB within one upload **before** validation | L909-913; UAT 1.31 |
| PR-delivery-03 | The user supplies the event date; revenue, positions and reports are dated by it | L1025-1026, L2574 |
| PR-delivery-04 | Revenue = quantity delivered x the POB's remaining unit revenue rate from the prior state; partial deliveries leave the rate unchanged | L1028, L1048-1050 |
| PR-delivery-05 | Roll remaining quantity, SSP, allocation and billing forward; keep cumulative delivery, revenue, billing, pre-606 revenue and SSP delivered | L1032-1072 |
| PR-delivery-06 | Support fractional quantities, negative quantities (returns), negative billing (credit memos) and billing with zero delivery | UAT 3.31, 4.30 |
| PR-delivery-07 | VC lines: quantity tracked, no revenue, negative billing allowed, excluded from the billing checks, reclass 0 | L961-964, L1088-1089, L1104 |
| PR-delivery-08 | Reject the whole upload on over-delivery (all strata) or over-billing (non-VC) against remaining balances per aggregated POB | L959-974 |
| PR-delivery-09 | POB position = cumulative billing - cumulative revenue; contract position = sum; positive = liability, negative = asset | L1073-1079 |
| PR-delivery-10 | When the contract position is negative, reclass the net amount to unbilled A/R, allocated across POB lines by cumulative SSP delivered (default policy, configurable) | L1081-1089 |
| PR-delivery-11 | Each event produces a snapshot of all POBs of the affected contracts, with Previous and Current values viewable for audit | L980-1009, L1154 |
| PR-delivery-12 | Journal derivation: Dr deferred revenue / Cr revenue; reverse the prior reclass and book the current one; gross and adjustment (pre-606 reversal) modes; balance-sheet lines consolidated by contract and account, revenue by POB | L2594-2651, L2965-2979 |
| PR-delivery-13 | Equivalent header, numeric, blank and match validations (VR-delivery-03 to 08), improved with row-level detail | Section 2 |
| PR-delivery-14 | Catch-up disclosure amount stays 0 for delivery events | L1023 |
| PR-delivery-15 | Parity mode reproduces the legacy UAT values within 1e-6 before production rounding is applied | Section 5; golden steps 04-07, 14 |

### 7.2 Behaviours to fix

| ID | Fix | Addresses |
|---|---|---|
| FX-delivery-01 | Typed schema validation; memos optional; IDs coerced to text; row-level errors with worksheet row numbers; never swallow exceptions | VR-delivery-07, 12, 13; E01, E02, E06 |
| FX-delivery-02 | Reject returns larger than cumulative delivery and refunds larger than cumulative billing (the intent of VR-delivery-09), or route the excess refund to a refund liability | E03 |
| FX-delivery-03 | Final-delivery true-up: when remaining quantity reaches 0, revenue = remaining allocation. Store amounts as `Decimal` at currency precision; forbid inf/NaN with DB check constraints | E20, E22 |
| FX-delivery-04 | Returns reverse at the carrying rate of the returned units (default: cumulative revenue / cumulative delivery), including after full delivery and after modifications | E19, E25 |
| FX-delivery-05 | Optional expected-returns policy per SKU: refund liability, recovery asset, remeasured each period | AA-delivery-01 |
| FX-delivery-06 | Activity filter counts any contract with an upload row | E23 (L948-951) |
| FX-delivery-07 | Aggregate by POB regardless of memo text; memo lines stored as event detail | E04 |
| FX-delivery-08 | Idempotency via batch ID plus file hash; duplicates rejected unless explicitly confirmed | E08 |
| FX-delivery-09 | Period calendar with open/closed status; reject events in closed periods; out-of-order events either recalculate later versions or post as current-period adjustments (policy) | E09 |
| FX-delivery-10 | VC credits beyond the VC estimate require a transaction-price-change event | E13 |
| FX-delivery-11 | Reclass guards: zero-denominator fallback and a tolerance (|POSC| < 0.005 -> 0) to suppress noise reclasses | golden step 14 |
| FX-delivery-12 | Separate contract asset (conditional) from unbilled/billed receivable (unconditional); configurable due-date basis for the liability | AA-delivery-05 |
| FX-delivery-13 | Entity-aware netting: contract net for presentation; per-entity balanced entries with intercompany where needed | Section 6.2 |
| FX-delivery-14 | Over-time progress from POB dates (ratable / time-elapsed), input methods and the right-to-invoice expedient | Section 6.2 |
| FX-delivery-15 | Single measure of progress for combined non-distinct POBs | Section 6.2 |
| FX-delivery-16 | Contract-balance roll-forward and disclosure data (opening/closing balances, revenue from opening liability, prior-period obligations) | AA-delivery-06 |
| FX-delivery-17 | Controls: user identity, approval thresholds, immutable audit log, void/reversal events instead of database restore, UTC timestamps, surrogate keys instead of space-joined strings | Section 4.1; AA-delivery-07, 08 |
| FX-delivery-18 | JE rounding at line level with a balancing plug; each entry balances per entity | AA-delivery-10 |
| FX-delivery-19 | POBs created by modifications initialise every state column (for example pre-606 cumulative = 0) | E23 |

### 7.3 Test cases to carry forward

"Parity" tests assert the legacy value (tolerance 1e-6 in float parity mode; 0.01 after production rounding). "Fix" tests assert the corrected behaviour and deliberately diverge from legacy.

| ID | Mode | Scenario (state -> event) | Expected |
|---|---|---|---|
| TC-delivery-01 | Parity | UAT setup 1.1.2023 -> 1.31.2023, Contract 1 (duplicate POB #1 rows) | POB #1 q 2, b 100, RR 128.840436, POS -28.840436; POB #2 RR 118.533201, POS -18.533201; POB #3 RR 48.315164, POS 51.684836; POSC 4.311199; RECL 0. Gross JE Dr 21001 295.69 / Cr 5001 128.84, 5002 118.53, 5003 48.32. Adjustment JE 21001 +141.69, 5001 -128.84, 5002 -52.53, 5003 +39.68 |
| TC-delivery-02 | Parity | Same event, Contract 2 (delivery without billing) | RR 58.846154; POSC -58.846154; RECL POB #1 58.846154, others 0; JE Dr 15002 58.85 / Cr 5001 58.85 |
| TC-delivery-03 | Parity | 2.28.2023 | Contract 1 POB #1 RR 64.420218, POSC 39.890981; Contract 3 POB #3 RR 48.315164, POSC 151.684836; Contract 4 POB #1 RR 111.294028, POSC 38.705972; RECL 0 for all |
| TC-delivery-04 | Parity | 3.31.2023, Contract 2 (fractional 0.4) | POB #3 RR 46.153846, RQ 0.6; POSC -105.000000; RECL POB #1 58.846154, POB #3 46.153846; JE Dr 15002 46.15 / Cr 5003 46.15 |
| TC-delivery-05 | Parity | 3.31.2023, Contract 4 (VC line delivery 0.5, credit -100) | VC RR 0, CB -100, POS -100; POB #2 RR 98.928025; POSC 39.777948; RECL 0 |
| TC-delivery-06 | Parity | 4.30.2023, Contract 1 (return -3/-200; zero-delivery billing 300) | POB #1 RR -193.260654, RQ 5, RBILL 500, CD 0, POS 0; POB #2 RBILL 0, CB 400, POS 281.466799; POSC 333.151635; JE Dr 5001 193.26 / Cr 21001 193.26 |
| TC-delivery-07 | Parity | 4.30.2023, Contract 2 (billing 20 against an asset) | POSC -85.000000; RECL POB #1 47.637363, POB #3 37.362637; JE Dr 21002 20.00 / Cr 15002 20.00 |
| TC-delivery-08 | Parity (production asserts exact 0.00) | Full UAT through 10.31.2023 | All RQ 0; per contract CRR = CB: 800 / 1,100 / 2,600 / 1,200; POSC 0 and RECL 0 (legacy shows about 1e-13 noise) |
| TC-delivery-09 | Parity | E20 -> E20b: Contract 1 POB #1 deliver 5 bill 0 and POB #3 bill 400; then POB #2 deliver 2 | Event 1 POSC +77.898910, RECL 0. Event 2 POSC -159.167493, RECL POB #1 91.686344, POB #2 67.481149, POB #3 0 |
| TC-delivery-10 | Parity | Over-delivery (E11), over-billing (E12), VC over-delivery (E18) | Upload rejected; no state change |
| TC-delivery-11 | Parity (message may change) | Missing `Memo 3` + extra `Notes` (E15); blank `Current Billing` (E16); `Current Delivery` = `abc` (E17) | Rejected, naming the missing/extra columns or the failing column |
| TC-delivery-12 | Fix | Unmatched `Contract 9 POB #1 Hardware 1` at data row 2 (E06) | Rejected citing Excel row 3 and the key (legacy says "9") |
| TC-delivery-13 | Fix | Blank `Memo 1` on Contract 1 POB #2, q 1, b 50 (E01) | Processed: RR 118.533201 (legacy: success popup, nothing written) |
| TC-delivery-14 | Fix | Numeric `POB Unique ID` (E02) | Explicit validation error (legacy: silent) |
| TC-delivery-15 | Fix | Return 3 of 2 delivered, refund 150 of 100 billed (E03) | Rejected (legacy: CD -1, CB -50) |
| TC-delivery-16 | Fix | Same POB twice with different memos, 3 + 3 of 5 (E04) | Aggregated to 6, rejected as over-delivery |
| TC-delivery-17 | Fix | Header-only file (E05); duplicate file (E08); backdated into a closed period (E09) | Warning/no-op; duplicate rejected; closed period rejected |
| TC-delivery-18 | Fix | VC credit -150 against a -100 VC (E13) | Rejected or routed to a transaction-price-change workflow |
| TC-delivery-19 | Fix | Contract 1 POB #2 fully delivered (CRR 237.066402), then return 1 (E19) | RR -118.533201; CRR 118.533201; RQ 1; RALLOC 118.533201 (legacy RR 0) |
| TC-delivery-20 | Fix | Contract 1 POB #1 deliver all 5 at once, then return 1 (E22) | Delivery RR 322.101090 = remaining allocation, URR 0 with no inf; return RR -64.420218 (legacy -inf) |
| TC-delivery-21 | Fix | Through 09.15 modification, deliver 1 on Contract 3 POB #5 only (E23) | Processed: RR 253.622787 (legacy: nothing written) |
| TC-delivery-22 | Fix (policy review) | Through 09.15 modification, return 1 unit of Contract 1 POB #2 (E25) | RR -118.533201, CRR 0 (legacy -92.533678, leaving 25.999523). The remaining-allocation effect needs a policy decision |

### 7.4 Open questions

1. **Returns policy.** Reverse at the average carrying rate, FIFO or the current rate? Does a return restore undelivered quantity (exchange) or extinguish the obligation (refund)?
2. **Reclass allocation key.** Keep cumulative SSP delivered as the default, or allocate by each POB's own net debit position?
3. **Entity presentation.** For contracts spanning selling entities: net only in the consolidated view, or per entity with intercompany entries?
4. **Billing JEs.** Should eRev Cloud post the billing entries (A/R and deferred revenue) and apply the 45-2 due-date rule, or keep assuming the ERP does?
5. **Pre-ASC 606 revenue.** Keep it as a per-event input, or derive it from an ERP revenue feed?
6. **Backdated events.** Recalculate later versions (effective-dated ledger), or post adjustments in the current open period?
7. **Source register.** Add the [external website reference removed] download URL for ASU 2014-09 Section A to the shared source register (the 04 agent did not record it).

