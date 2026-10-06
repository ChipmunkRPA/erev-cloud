# 03 - Prospective Contract Modification (legacy eRev `browse_file_ProsMod`)

| Item | Value |
|---|---|
| Legacy source | `~/dev/erev-legacy/eRev.py` lines 1170-1653 (method `FileBrowserWindow.browse_file_ProsMod`) |
| Shared state read | `Contract_Live` (latest version per POB), `SKU_SSP` in `ops/libnew/libwarm/db/ASC606.db` |
| Related legacy code consulted | Contract setup 621-824, Delivery and billing 826-1168, Retrospective mod 1655-2131, POB-specific VC 2133-2538, Journal entries 2540-2668 and 2862-3011 |
| Template | `ops/Blank Templates/Contract Modification Template.xlsx` (shared with Retrospective Mod and POB Specific VC) |
| UAT files in scope | `ops/Example UATs/Contract Mod UAT/Contract Modification Template 06.15.2023 - prospective reduction.xlsx`, `... 07.15.2023 - prospective POB increases.xlsx`, `... 09.15.2023 - material right exericse with new POB added (propsective).xlsx` |
| Evidence basis | Line-by-line reading of the source, plus a headless replay of the full UAT sequence that executes the unmodified legacy methods against a scratch copy of the database (pandas 2.1.4 / numpy 1.26.4, Python 3.11; harness in `~/dev/erev/.scratch/prospective-mod/`) |

Conventions in this document: line numbers refer to `eRev.py`. "CL" means `Contract_Live`. "Row" means one POB row of a contract version. "Existing POB" means a row already in CL; "new POB" means a template row whose key is not in CL. Facts come from code or replay output. Anything marked **Inference** is reviewer judgement.

---

## 1. Purpose, trigger, inputs, outputs

### 1.1 Purpose

This process applies a contract modification prospectively as of a user-entered modification date. In one upload it can:

- add or remove quantity and consideration on existing POBs,
- add new POBs to an existing contract (for example, a new consulting POB), and
- run off or exercise a material right (a negative quantity on a material-right POB with zero billing).

Mechanically it (a) pools the unrecognised allocation of every POB in each modified contract with the net modification consideration and reallocates the pool on relative remaining SSP, (b) takes a cumulative catch-up for `Nondistinct` POBs only, and (c) appends a new version row for every POB of each modified contract to `Contract_Live`.

The README describes the intent as: "eRev supports cumulative catchup calculation for non-distinct POBs in a prospective contract modification" and "contract modifications are done in line with the existing POBs, meaning you can track the lifecycle of each POB continuously in its own line" (README.md lines 75 and 79).

### 1.2 Trigger

| Step | Behaviour | Lines |
|---|---|---|
| Button | `self.button4 = QPushButton("Prospective Contract Mod")` in the "Mod Operations" row | 128-131 |
| Wiring | `self.button4.clicked.connect(lambda: self.browse_file_ProsMod())` | 233 |
| File picker | `QFileDialog().getOpenFileName(self, "Select File")`. Any file type is accepted; no extension filter | 1171-1172 |
| Cancel file picker | `file_path == ''`, so `if file_path:` is false and nothing happens | 1175 |
| Date prompt | `QInputDialog.getText(self, "Date Input", "Enter the prospective contract mod date in this format (YYYY-MM-DD):")` | 1176-1177 |
| Cancel date prompt | `ok == False`, so nothing happens | 1178 |
| Parse date | `QDate.fromString(input_text, "yyyy-MM-dd")`, then `mod_date = datetime.combine(qdate.toPython(), datetime.min.time())` (midnight, naive) | 1179, 1246 |
| Read file | `pd.read_excel(file_path)`: first worksheet only, row 1 is the header | 1187 |

There is no premium-licence gate on this button. The licence check at 258-263 only disables features through `show_notification_and_disable`, which was out of scope and not traced.

### 1.3 Inputs - template columns

The sheet is `Sheet1` of the Contract Modification Template, with exactly 15 columns A-O. All 15 headers must be present and no others (VR-prospective-mod-04). The code enforces only the header set, the two numeric columns and the SSP lookup key. Every other column is "required" only in the sense that a blank value produces NaN downstream.

| Col | Header | Type as consumed | Enforced by code | How it is used | Lines |
|---|---|---|---|---|---|
| A | Contract Unique Name | text; cast `astype(str)` (a blank becomes the string `'nan'`) | header only | Part of the POB key `Contract + " " + POB + " " + SKU`; contract grouping for pooling | 1250-1251, 1333-1339 |
| B | POB Unique ID | text; cast `astype(str)` | header only | Part of the POB key | 1252-1254 |
| C | SKU Name | text; **not** cast | header only; must match `SKU_SSP` (VR-08) | Part of the POB key; SSP lookup key 1 | 1259-1262 |
| D | Mod Start Date | date | none | Overwrites `POB Start Date` on rows with a mod line; blank keeps the stored date | 1376-1378 |
| E | Mod End Date | date | none | Overwrites `POB End Date` the same way | 1379-1381 |
| F | ASC 606 Stratification | text | must match `SKU_SSP` (VR-08) | SSP lookup key 2; stored **only for new POBs**; the value `"VC"` is special-cased | 1259-1262, 1385-1386 |
| G | Mod Billing | number, signed (+ increases, - decreases consideration) | numeric and non-blank (VR-05, VR-06) | Incremental transaction price and incremental remaining billing | 1316-1328, 1448-1460 |
| H | Mod Qty | number, signed | numeric and non-blank (VR-05, VR-06) | Incremental remaining quantity; drives the SSP band; its sign selects the clamp branch | 1286-1328, 1440-1441 |
| I | Selling Entity | text | none | Stored **only for new POBs** (existing value wins) | 1387-1388 |
| J | Deferred Revenue Account | integer | none | Stored only for new POBs | 1391-1393 |
| K | Unbilled A/R Account | integer | none | Stored only for new POBs | 1394-1396 |
| L | SSP Version | date or text; cast `astype(str)` | must match `SKU_SSP` (VR-08) | SSP lookup key 3 (prices the mod quantity); stored only for new POBs | 1248-1249, 1389-1390 |
| M-O | Memo 1, Memo 2, Memo 3 | text | none | **Template value wins** on rows with a mod line; blank keeps the stored memo | 1372-1374 |

Reference-data inputs:

| Table | Read | Columns used |
|---|---|---|
| `Contract_Live` | `SELECT t1.* ... JOIN (SELECT "Record Unique ID without time", MAX("Processing Time Log") ... GROUP BY "Record Unique ID without time")`, then a second `groupby(...).idxmax()` de-duplication in pandas (1228-1236, 1343-1347). The latest version per POB is chosen by **processing timestamp**, not by `Current Period` | All 71 columns |
| `SKU_SSP` | `SELECT * FROM "SKU_SSP"` (1237-1239) | `SKU Unique ID`, `Distinct or Nondistinct`, `SKU Unit List Price`, `Midpoint Discount Percentage`, `SSP Range Method (+-)`, `Revenue Account`, plus the three join keys |

### 1.4 Outputs

| Output | Detail | Lines |
|---|---|---|
| `Contract_Live` append | `prospective_completed_df.to_sql("Contract_Live", conn, if_exists="append", index=False)`. Writes one row per POB of **each modified contract** (all POBs of that contract, not only the modified ones), with every one of the 71 columns. All rows share one `Processing Time Log` value. Detail in Section 4 | 1638-1639 |
| Excel files | **None.** Unlike Journal Entries and Contract History, this process saves no workbook | - |
| Success popup | `QMessageBox.information("Mod Success", "Prospective Mod has been processed with uploaded modifications for the current date :)")` | 1641-1642 |
| Error popups | See Section 2. Every raised `Exception` ends in `QMessageBox.critical("Error Notification", str(e))` | 1648-1653 |
| `SKU_SSP` | Read-only | - |
| EFS encryption | Not called by this process (SSP upload calls it at 604-607) | - |
| Downstream consumers | `journal_entries` (2540) posts `Current Rev Rec` (the catch-up) and the reclass reversal/re-post of each appended row whose `Current Period` falls in the JE date range. `journal_entries_delta` (2862) also posts `Current Pre-ASC606 Revenue (Net Design Only)` of each row in range (see defect D-10) | 2594-2651, 2966-2979 |

---

## 2. Validation rules

The rules run in the order listed. Every rule that shows an `information` popup and then raises an exception produces **two** popups: the specific message, then `critical` "Error Notification" with the exception text. No rule writes a partial result. The only database write is the final `to_sql` append (1638), so every failure before it leaves `Contract_Live` unchanged.

| ID | Stage | Exact condition (as coded) | Popup type / title / text | Lines | Notes |
|---|---|---|---|---|---|
| VR-prospective-mod-01 | File pick | `if file_path:` is falsy (dialog cancelled) | None (silent no-op) | 1175 | - |
| VR-prospective-mod-02 | Date prompt | `if ok:` is false (dialog cancelled) | None (silent no-op) | 1178 | - |
| VR-prospective-mod-03 | Date format | `QDate.fromString(input_text, "yyyy-MM-dd").isValid()` is false | `warning` / "Invalid Date" / "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." | 1179-1182 | Strict zero-padded format; impossible dates are rejected. No range check and no chronology check against the contract's latest `Current Period` (gap G-03) |
| VR-prospective-mod-04 | Header set | `missing_titles or extra_titles`, where `missing = [t for t in expected if t not in actual]` and `extra = [t for t in actual if t not in expected]`; `expected` is the 15 headers in 1.3 | `information` / "File Upload Error" / "Error: The Excel file has incorrect or missing column titles."; then, if any are missing, `information` / "Missing fields:" / `", ".join(missing)`; then, if any are extra, `information` / "Extra fields:" / `", ".join(extra)` | 1189-1206 | Exact match, case- and whitespace-sensitive; column order does not matter. A stray value in an unlabelled column appears as "Unnamed: n". A duplicated header appears as "X.1". Processing stops; no exception is raised, so no critical popup |
| VR-prospective-mod-05 | Numeric type | For `column` in `['Mod Billing', 'Mod Qty']` in that order: `pd.to_numeric(df[column], errors='raise')` raises `ValueError` or `TypeError` | `information` / "Format Error" / "Error: The column '{column}' should contain numeric values." | 1197-1198, 1210-1225 | Stops at the first failing column. The converted series is discarded, but `pd.read_excel` already coerces numeric text (a cell holding the string "90") to a number, so text-formatted numbers process normally (probe P-06). Non-numeric text ("abc") fails with the message shown (probe VR05) |
| VR-prospective-mod-06 | Non-blank | Same loop: `df[column].isna().any()` | Same as VR-05 | 1218-1221 | A header-only template (zero rows) passes VR-05 and VR-06 (probe P-07) |
| VR-prospective-mod-07 | Reference tables | `pd.read_sql_query` fails because `Contract_Live` or `SKU_SSP` does not exist | `critical` / "Error Notification" / pandas `DatabaseError` text (for example "Execution failed on sql ...: no such table: Contract_Live") | 1227-1243, 1648-1653 | - |
| VR-prospective-mod-08 | SSP match | Left merge of the template to `SKU_SSP` on `['SKU Name', 'ASC 606 Stratification', 'SSP Version']` (`SSP Version` cast to str); any row with `_merge == 'left_only'` | `information` / "Mod Upload Failed" / "Some Mod POBs are not matched with the existing SSP databse. Re-upload the file after fixes! \nPOB with issues: \n{failed_list}", where `failed_list = ",".join(SKU Name of the failing rows)`; then `raise Exception("The process is stopped for users to fix the file")`, which gives `critical` / "Error Notification" / "The process is stopped for users to fix the file" | 1259-1274 | The typo "databse" is in the shipped text. The list names SKUs, not POBs. A blank SKU Name fails differently by upload size. In a single-row upload the column is float64, so pandas raises a MergeError and the user sees `critical` "You are trying to merge on float64 and object columns for key 'SKU Name'..." (probe VR08b). In a multi-row upload the failing row reaches `",".join`, which raises `TypeError`, and the run aborts **silently** (VR-11, probe P-18). `SKU_SSP` has no uniqueness constraint, so a duplicated SSP key silently fans a mod line out into two rows (gap G-09) |
| VR-prospective-mod-09 | Post-calculation integrity | `(prospective_completed_df["Current Remaining Qty"] < 0).any()` **or** `(prospective_completed_df[Stratification != "VC"]["Current Remaining Billing"] < 0).any()` | `information` / "Mod Failed" / "Qty or Price modified cannot reduce the remaining qty or remaining billing to negative. Check your uploads please."; then `critical` / "Error Notification" / "The process is stopped for users to fix the file" | 1602-1608 | Evaluated **after** all calculations and only over rows that survived the Distinct/Nondistinct split (1521-1523, defect D-05). No tolerance, so a floating-point residue such as -1e-13 fails the rule. A negative `Current Remaining SSP` is not rejected; it is silently floored to 0 (1446) |
| VR-prospective-mod-10 | Write | `SELECT name FROM sqlite_master WHERE type='table' AND name='Contract_Live'` returns nothing | `critical` / "Error Notification" / "No contract table is found!" | 1611-1621, 1643-1645 | Unreachable in practice, because VR-07 fails first |
| VR-prospective-mod-11 | Any stage | Any `TypeError` raised anywhere inside the `try` block | **None: silent abort, no write** | 1646-1647 | Intended only for a cancelled file dialog. It also swallows real data errors; for example, a multi-row upload with one blank SKU Name ends with no popup and no write (probe P-18) |
| VR-prospective-mod-12 | Any stage | Any other `Exception` | `critical` / "Error Notification" / `str(e)` (after `conn.close()` is attempted) | 1648-1653 | Covers pandas `MergeError` for key-dtype mismatches, `KeyError`, `ValueError`, and similar |

Absent validations that a port must add are listed as gaps G-01 to G-10 in Section 6.4.

---

## 3. Calculation logic

### 3.0 Pipeline

| # | Stage | Lines |
|---|---|---|
| 1 | Read template; validate headers and numeric columns (VR-04 to VR-06) | 1187-1226 |
| 2 | Load the latest CL version per POB and the full `SKU_SSP` table | 1227-1243 |
| 3 | Normalise: `mod_date` at midnight; `SSP Version`, `Contract Unique Name` and `POB Unique ID` cast to str | 1246-1254 |
| 4 | Left-join the template to `SKU_SSP`; reject unmatched rows (VR-08) | 1259-1283 |
| 5 | Compute the modification SSP band and the clamped `Mod SSP Changes` | 1286-1331 |
| 6 | Build the POB key; outer-join CL latest to the template rows; keep modified contracts only | 1333-1363 |
| 7 | Resolve attributes (fillna precedence) and roll `Current` into `Previous` | 1366-1437 |
| 8 | Update remaining qty/SSP/billing; **pool and reallocate** remaining allocation; recompute units, positions and reclass | 1440-1500 |
| 9 | Stamp `Processing Time Log` and `Record Unique ID`; drop helper columns; sort | 1502-1518 |
| 10 | Split into Distinct and Nondistinct rows; **cumulative catch-up** on Nondistinct rows | 1520-1580 |
| 11 | Concatenate; recompute contract-level position and reclass; sort | 1582-1597 |
| 12 | Integrity check (VR-09); append to CL; success popup | 1602-1642 |

Notation, per row *i* of contract *c*. Subscript "old" means the value on the stored latest CL row (NaN for a new POB; the code applies `fillna(0)` where noted). `ΣC[x]` is `groupby('Contract Unique Name')[x].transform('sum')` over the rows kept in stage 6. pandas `sum` skips NaN.

### 3.1 Modification SSP band and clamp (stage 5)

Price inputs come from the `SKU_SSP` row matched on the template's `(SKU Name, ASC 606 Stratification, SSP Version)`: list price *P*, midpoint discount *d*, range *r*. For an existing POB this can be a different SSP version from the one stored on the POB, and the stored version is not updated (3.3).

```
Mod Midpoint SSP   = ModQty * P * (1 - d)                       # 1286-1292
Mod Lower_End SSP  = ModQty * P * (1 - d) * (1 - r)             # 1293-1302
Mod Higher_End SSP = ModQty * P * (1 - d) * (1 + r)             # 1303-1312

Mod SSP Changes (compare_columns, 1314-1331):
  if ModQty > 0:                       # band is [Lower, Higher]
      Higher  if ModBilling > Higher
      Lower   if ModBilling < Lower
      ModBilling otherwise
  else:                                # ModQty <= 0: band is [Higher, Lower] because both ends are <= 0
      Higher  if ModBilling < Higher   # more negative than the band
      Lower   if ModBilling > Lower    # less negative than the band
      ModBilling otherwise
```

Consequences (facts):

- **SSP of a modification = the consideration clamped into the SSP band.** This is the same "price within range, otherwise nearest bound" rule as contract setup (692-700). Setup has no negative branch.
- **`ModQty = 0` (price-only modification)** makes Higher = Lower = 0, so `Mod SSP Changes = 0` whatever the billing. The consideration still enters the pool (3.4), but no SSP is added.
- **Reductions** remove SSP priced at the *template* SSP version and clamped to the credit amount. They do not remove SSP at the POB's carried unit SSP. The remaining SSP can therefore stay positive while the remaining quantity is 0 (probe P-11: `Current Unit SSP = inf`).
- **Sign mismatch** (for example qty -1 with billing +90) is accepted. The negative branch clamps +90 to the lower bound -76.5, so SSP falls while consideration rises (P-15).
- **Missing price fields** (NaN band): every comparison is False, so `Mod SSP Changes = ModBilling`.

Replay values:

| UAT | Row | ModQty | *P*, *d*, *r* | Band | ModBilling | Mod SSP Changes |
|---|---|---|---|---|---|---|
| 06.15 | C1 POB #1 Hardware 1 | -5 | 100, 0.10, 0.15 | [-517.5, -382.5] | -500 | -500 |
| 07.15 | C3 POB #1 Hardware 1 | +2 | 100, 0.10, 0.15 | [153, 207] | 500 | 207 |
| 07.15 | C4 POB #3 Consulting 1 | +2 | 300, 0.50, 0 | [300, 300] | 300 | 300 |
| 09.15 | C3 POB #4 Material Right - Services | -1000 | 1, 0, 0 | [-1000, -1000] | 0 | -1000 |
| 09.15 | C3 POB #5 Consulting 1 (new) | +5 | 300, 0.50, 0 | [750, 750] | 1000 | 750 |

### 3.2 Key, join and scope of the new version (stage 6)

```
Record Unique ID without time = Contract Unique Name + " " + POB Unique ID + " " + SKU Name       # 1333-1339
latest   = CL rows with max(Processing Time Log) per key, then groupby(key).idxmax()              # 1228-1236, 1343-1347
merged   = latest OUTER JOIN template_with_SSP ON key, suffixes ('', '_new')                      # 1350-1352
modified = merged.loc[ModQty.notna() & ModBilling.notna(), 'Contract Unique Name'].tolist()       # 1356-1359
merged   = merged[merged['Contract Unique Name'].isin(modified)]                                  # 1362-1363
```

- The outer join brings in **every CL POB of every contract** (all contracts in the database) plus the template rows. The filter then keeps the contracts named on template rows that matched an existing POB.
- The `Contract Unique Name` taken for the filter is the **left (CL) column**, which is NaN for a template row that did not match an existing key. `Series.isin([..., NaN])` matches NaN to NaN (verified with pandas 2.1.4), so unmatched template rows survive the filter. Their contract name is filled from the template afterwards (1366-1367).
- Result 1: when an upload has at least one line for an existing POB of contract *c*, **all** POBs of *c* are re-versioned, including fully delivered ones, and new POBs of *c* join the pool.
- Result 2 (defect D-01): when an upload has **only new-POB lines** for contract *c* (no existing-POB line), the existing POBs of *c* are excluded. The new POB is pooled alone, and its contract-level position ignores the rest of the contract (probe P-01).
- Result 3 (defect D-02): a line for a contract that does not exist creates an orphan contract without error (P-02).
- Result 4 (defect D-03): an existing POB ID uploaded with a different SKU Name is a *new* POB (the SKU is part of the key), with the Result 2 consequences (P-14).
- Result 5 (defect D-04): duplicate template lines for one key produce duplicate CL rows with the same timestamp. Each duplicate absorbs only its own line's quantity and SSP, but both are appended. The legacy "latest" SQL then returns two rows for that POB (P-03).

### 3.3 Attribute precedence (stage 7)

| Column(s) | Existing POB with a mod line | Existing POB without a mod line | New POB | Lines |
|---|---|---|---|---|
| Contract Unique Name, POB Unique ID, SKU Name | stored | stored | template | 1366-1370 |
| Memo 1, Memo 2, Memo 3 | **template**, else stored | stored | template | 1372-1374 |
| POB Start Date / POB End Date | **template `Mod Start Date` / `Mod End Date`**, else stored | stored | template (NaT if blank) | 1376-1382 |
| ASC 606 Stratification, Selling Entity, SSP Version, Deferred Revenue Account, Unbilled A/R Account | stored (template value **ignored**, no warning) | stored | template | 1385-1396 |
| SKU Unique ID, Distinct or Nondistinct, SKU Unit List Price, Midpoint Discount Percentage, SSP Range Method (+-), Revenue Account | stored | stored | `SKU_SSP` row for the template SSP version | 1399-1411 |
| Previous Period | stored `Current Period` | stored `Current Period` | NaT (stored as NULL) | 1397 |
| Current Period | `mod_date` | `mod_date` | `mod_date` | 1398 |
| Original POB Total Selling Price, Original POB Total Qty, Original SSP - Midpoint/Higher/Lower, Original Extended SSP, Original Total Contract Price, Original Total Contract SSP, Original Allocation, Original Unit SSP, Original Unit Rev Rec | unchanged (not re-based) | unchanged | **NULL** | not touched |

### 3.4 Roll-forward, pooled reallocation and positions (stages 7-8)

```
# Previous <- Current (all fillna(0))                                              1414-1437
Previous {Remaining Qty, Remaining SSP, Remaining Allocation, Remaining Billing, Unit SSP,
          Remaining Unit Rev Rec, Delivery - Cumulative, Rev Rec - Cumulative, Billing - Cumulative,
          Cumulative Catchup - Cumulative - Disclosure Only, SSP Delivered - Cumulative,
          Contract Position - POB, Contract Position - Contract Level, Reclass to UAR}
        = Current {same}_old.fillna(0)
# NOT rolled: 'Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative' (kept from the prior row; NULL for new POB)

RemQty_i   = RemQty_old_i.fillna(0) + ModQty_i.fillna(0)                          # 1440-1441
RemSSP_i   = RemSSP_old_i.fillna(0) + ModSSPChanges_i.fillna(0)                   # 1442-1444
RemSSP_i   = max(RemSSP_i, 0)                                                     # 1446 (silent floor)

Pool_c     = ΣC[RemAlloc_old] + ΣC[ModBilling]                                    # NaN skipped
RemAlloc_i = (Pool_c / ΣC[RemSSP] * RemSSP_i).fillna(0)                           # 1448-1455
RemBill_i  = RemBill_old_i.fillna(0) + ModBilling_i.fillna(0)                     # 1456-1460
UnitSSP_i  = (RemSSP_i / RemQty_i).fillna(0)                                      # 1461-1463  (x/0 -> ±inf, not replaced)
UnitRR_i   = (RemAlloc_i / RemQty_i).fillna(0)                                    # 1464-1468  (x/0 -> ±inf, not replaced)

Current Delivery = Current Rev Rec = Current Billing = Current SSP Delivered
                 = Current Cumulative Catchup - Disclosure Only = 0               # 1469-1473
# NOT reset: 'Current Pre-ASC606 Revenue (Net Design Only)' carries the prior row's period amount (D-10)
Cumulative {Delivery, Rev Rec, Billing, Catchup, SSP Delivered} = old.fillna(0)   # 1474-1483
# NOT touched: 'Current Pre-ASC606 Revenue (Net Design Only) - Cumulative'

PosPOB_i   = CumBilling_i - CumRevRec_i                                           # 1484-1488
PosC_c     = ΣC[PosPOB]                                                           # 1489-1491
Reclass_i  = -PosC_c / ΣC[CumSSPDelivered] * CumSSPDelivered_i  if PosC_c < 0 else 0   # 1492-1497
Reclass_i  = 0 where ASC 606 Stratification == "VC"                               # 1499-1500
```

What the pool does:

- **Discount and premium allocation.** The modified contract's total unrecognised consideration (`ΣC[RemAlloc_old]`, which equals the transaction price not yet recognised) plus the net modification consideration is spread over all remaining POBs in proportion to remaining SSP. Any discount or premium, old or new, is spread over **every** remaining POB, including POBs the upload did not touch (the relative SSP method). VC-stratified lines carry SSP 0, so they receive 0. Material-right lines receive a share in proportion to their SSP, which is quantity multiplied by a $1 list price.
- **Conservation.** `ΣC[RemAlloc_i] = Pool_c`, up to floating-point error, whenever `ΣC[RemSSP] > 0`. Across replay steps 10, 11 and 13, the contract transaction price `Σ(CumRevRec + RemAlloc)` equals prior TP + `ΣC[ModBilling]` to within 1e-6.
- **Residual handling.** None: there is no rounding, no penny plug and no last-line absorption. If `ΣC[RemSSP] = 0` (everything delivered, or all SSP floored to 0), `0/0 -> NaN -> 0`, so **the whole pool is dropped** and the modification consideration is never recognised (defect D-06, probe P-05).
- **Stranded allocation.** A POB with `RemQty = 0` but `RemSSP > 0` receives allocation it can never release through deliveries: `UnitRR = inf` and a later delivery of 0 gives `0*inf = NaN` (defect D-07, P-11).
- **Contract position** is net billing minus revenue, first per POB, then summed over the contract. Sign: `PosC > 0` means a net contract liability (billed ahead of revenue); `PosC < 0` means a net contract asset.
- **Reclass to UAR.** When the contract is net unbilled, the unbilled amount `-PosC_c` is attributed to POBs in proportion to cumulative SSP delivered. The JE layer then reverses each row's `Previous Reclass to UAR` and posts `Current Reclass to UAR`: Dr Unbilled A/R, Cr Deferred Revenue, using the POB's accounts (2608-2636). If `PosC_c < 0` and `ΣC[CumSSPDelivered] = 0`, the result is NaN and is stored as NULL.

### 3.5 Cumulative catch-up for Nondistinct POBs (stage 10)

The rows are split exactly: `df_distinct = rows where 'Distinct or Nondistinct' == "Distinct"` and `df_nondistinct = rows where == "Nondistinct"` (1521-1523). **Rows with any other value (NaN, "distinct", "Non-distinct") are silently dropped**: they are neither appended nor counted in contract-level totals (defect D-05, P-04: 6.23 of TP disappeared from the latest-version view).

Distinct rows get no catch-up; the prospective reallocation in 3.4 applies to future deliveries through the new `UnitRR`.

Nondistinct rows (1526-1557), using `RemAlloc_i` after the 3.4 reallocation:

```
Progress_i     = CumDel_i / (CumDel_i + RemQty_i)                     # units-delivered output measure
ShouldBe_i     = (Progress_i * (CumRevRec_i + RemAlloc_i)).fillna(0)  # 1526-1536
CatchUp_i      = ShouldBe_i - CumRevRec_i                              # 1537-1540  (+ = more revenue, - = reversal)
CumCatchUp_i   = CumCatchUp_old_i + CatchUp_i                          # 1541-1543
CurrentRevRec_i= CatchUp_i                                             # 1545-1546  (flows to the JE)
CumRevRec_i    = CumRevRec_i + CatchUp_i                               # 1547-1549
RemAlloc_i     = RemAlloc_i - CatchUp_i                                # 1550-1552
UnitRR_i       = (RemAlloc_i / RemQty_i).fillna(0)                     # 1553-1557
PosPOB_i       = CumBilling_i - CumRevRec_i                            # 1558-1562
```

- The POB's total allocation `CumRevRec + RemAlloc` is unchanged by the catch-up; revenue is only moved between "recognised" and "remaining".
- Degenerate cases: `CumDel + RemQty = 0` (for example, a material right fully run off with nothing delivered) gives `0/0 -> NaN -> ShouldBe 0`, so `CatchUp = -CumRevRec`. That is 0 in the UAT (09.15 C3 POB #4), but it would reverse all revenue on a fully returned nondistinct POB. `CumDel = 0` gives `CatchUp = -CumRevRec`.
- Lines 1565-1576 compute a contract-level position and reclass on the nondistinct subset only. The code comment itself says this is incomplete, and it is overwritten in stage 11.
- The "Disclosure Only" columns are informational. The catch-up is also posted as `Current Rev Rec`, so it is **not** disclosure-only in effect; it drives the JE.

### 3.6 Final recompute (stage 11)

```
out      = concat(df_distinct, df_nondistinct)                                    # 1583-1584
PosC_c   = ΣC[PosPOB]                                                             # 1586-1588
Reclass_i= -PosC_c / ΣC[CumSSPDelivered] * CumSSPDelivered_i if PosC_c < 0 else 0 # 1589-1594
sort by key                                                                       # 1596-1597
```

The VC override (`Reclass = 0` for Stratification "VC") is **not re-applied** after this recompute (defect D-09). It is latent while VC SKUs have a list price of 0, because their cumulative SSP delivered is then 0 (see probe P-17 for a priced VC line).

### 3.7 Numeric types, rounding and storage

- **No rounding** anywhere in 1170-1653. Amounts are float64 end to end (for example `RemAlloc = 587.303258...`). Quantities are floats; the UAT uses 0.5 units.
- **Storage types.** CL's declared column types were fixed by the first `to_sql(..., if_exists="replace")` at setup (812), where many amount columns held integers, so they are declared INTEGER (for example `"Current Rev Rec" INTEGER`, `"Previous Reclass to UAR" INTEGER`). SQLite INTEGER *affinity* stores non-integral values as REAL, so **nothing is truncated**. The replay reads back `Current Rev Rec = -5.298816` from an INTEGER-declared column. Integral floats are stored as INTEGER (500.0 becomes 500). `inf` is stored as REAL Inf (P-11).
- **Rounding happens only in reporting.** `journal_entries` rounds each line to 4 dp, drops lines with `round(2) == 0`, sums by (key, account), drops sums with `round(2) == 0`, and rounds to 2 dp (2598-2651). There is no rounding difference account, so a JE can be out of balance by a cent in principle (**Inference**; not observed in the replay).
- **JE sign convention:** positive Amount = debit, negative = credit (2598-2636).

### 3.8 Pre-ASC 606 revenue (net design)

The prospective modification computes no pre-ASC 606 revenue. `Current Pre-ASC606 Revenue (Net Design Only)` is **carried forward** from the prior row instead of being zeroed. `journal_entries_delta` posts that column for every row in the date range (2966-2979), so a modification dated in the same JE range as the delivery **double counts** the delivery's pre-ASC 606 amount. Probe P-08: a delivery on 2023-01-31 with pre-606 amounts of 360 and 70, then a modification on 2023-02-15, gives an extra Dr Revenue 430 / Cr Deferred 430 on 2023-02-15 (defect D-10). New POB rows hold NULL in all three pre-606 columns.

---

## 4. State transitions and versioning

### 4.1 Model

`Contract_Live` is an **append-only snapshot ledger**. Every event button (setup, delivery/billing, prospective mod, retrospective mod, POB-specific VC) appends one full 71-column row per affected POB. Nothing is updated in place; only Purge Contracts (477) deletes. The prospective modification performs one `to_sql(..., if_exists="append")` (1638). pandas 2.1 runs that insert inside a single sqlite3 transaction, so a run is all-or-nothing at the write step. The read at 1227-1243 and the write at 1638 are separate connections with no locking. That is acceptable for a single-user desktop app, but it is not safe multi-user behaviour.

### 4.2 Identity and "latest version"

| Field | Rule | Lines |
|---|---|---|
| `Record Unique ID without time` | `Contract Unique Name + " " + POB Unique ID + " " + SKU Name`. This is the stable POB identity across versions. For a new POB it comes from the template (1333-1339); existing rows keep the stored value | 1333-1339 |
| `Processing Time Log` | `pd.Timestamp.now()`, **one value for the whole run**, shared by all appended rows and stored as text `YYYY-MM-DD HH:MM:SS.ffffff` | 1503 |
| `Record Unique ID` | `str(Processing Time Log) + " " + Contract + " " + POB + " " + SKU`. Not enforced unique; P-03 produced two identical IDs | 1504-1507 |
| Latest version | Row with `MAX("Processing Time Log")` per key (SQL), then `groupby(key).idxmax()` | 1228-1236, 1343-1347 |

Consequences:

- **Ordering is by processing time, not by event date.** A modification dated before the latest delivery is accepted and becomes the latest version, with `Previous Period (2023-01-31) > Current Period (2023-01-15)` (P-10).
- **No event-type column.** A prospective-mod version is recognisable only by zero period activity, the memo text, and possibly a non-zero `Current Cumulative Catchup - Disclosure Only`. It cannot be told apart from a retrospective-mod or POB-VC version by type.
- **No idempotency key.** Uploading the same file twice applies the modification twice; P-19 shows `Current Remaining Qty` rising by 2, not 1.

### 4.3 Roll-forward (Current becomes Previous)

For each appended row: `Previous Period` takes the stored `Current Period`, and `Current Period` becomes the mod date. The 14 balance fields listed in 3.4 move from Current to Previous. Then the Current fields are recomputed per Sections 3.4-3.6. `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative` is **not** rolled.

### 4.4 Rows appended per run

| Run | Contracts modified | Rows appended | Of which have a mod line |
|---|---|---|---|
| UAT 06.15 | Contract 1 | 4 | 1 (POB #1) |
| UAT 07.15 | Contract 3, Contract 4 | 8 | 2 (C3 POB #1, C4 POB #3) |
| UAT 09.15 | Contract 3 | 5 | 2 (POB #4 existing, POB #5 new) |
| P-01 (new-POB-only upload) | A | 1 | 1 (existing POBs **not** re-versioned: D-01) |
| P-03 (duplicate lines) | A | 3 | 2 duplicates of POB #1 (D-04) |
| P-07 (header-only file) | none | 0 | "Mod Success" popup is still shown (D-11) |

### 4.5 Column-by-column transition (all 71 columns)

| Group (count) | Columns | Existing POB | New POB |
|---|---|---|---|
| Identity (4) | Contract Unique Name, POB Unique ID, SKU Name, Record Unique ID without time | unchanged | template |
| Versioning (2) | Processing Time Log, Record Unique ID | run timestamp; rebuilt ID | same |
| Periods (2) | Previous Period, Current Period | stored Current Period; mod date | NULL; mod date |
| Contract attributes (5) | POB Start Date, POB End Date, Memo 1, Memo 2, Memo 3 | template value if the row has a mod line and the cell is non-blank; else unchanged | template |
| Accounting attributes (5) | ASC 606 Stratification, Selling Entity, SSP Version, Deferred Revenue Account, Unbilled A/R Account | unchanged (template ignored) | template |
| SKU attributes (6) | SKU Unique ID, Distinct or Nondistinct, SKU Unit List Price, Midpoint Discount Percentage, SSP Range Method (+-), Revenue Account | unchanged | `SKU_SSP` |
| Setup snapshot (11) | Original POB Total Selling Price, Original POB Total Qty, Original SSP - Midpoint, Original SSP - Higher, Original SSP - Lower, Original Extended SSP, Original Total Contract Price, Original Total Contract SSP, Original Allocation, Original Unit SSP, Original Unit Rev Rec | unchanged | NULL |
| Previous balances (14) | Previous Remaining Qty, Previous Remaining SSP, Previous Remaining Allocation, Previous Remaining Billing, Previous Unit SSP, Previous Remaining Unit Rev Rec, Previous Delivery - Cumulative, Previous Rev Rec - Cumulative, Previous Billing - Cumulative, Previous Cumulative Catchup - Cumulative - Disclosure Only, Previous SSP Delivered - Cumulative, Previous Contract Position - POB, Previous Contract Position - Contract Level, Previous Reclass to UAR | stored Current value | 0 |
| Previous pre-606 (1) | Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative | unchanged (not rolled) | NULL |
| Remaining balances (6) | Current Remaining Qty, Current Remaining SSP, Current Remaining Allocation, Current Remaining Billing, Current Unit SSP, Current Remaining Unit Rev Rec | recomputed (3.4, 3.5) | recomputed |
| Period activity (3) | Current Delivery, Current Billing, Current SSP Delivered | 0 | 0 |
| Period revenue (2) | Current Rev Rec, Current Cumulative Catchup - Disclosure Only | 0 if Distinct; catch-up if Nondistinct | 0 (no delivery yet) |
| Period pre-606 (1) | Current Pre-ASC606 Revenue (Net Design Only) | **carried forward, not zeroed** (D-10) | NULL |
| Cumulative activity (3) | Current Delivery - Cumulative, Current Billing - Cumulative, Current SSP Delivered - Cumulative | unchanged | 0 |
| Cumulative revenue (2) | Current Rev Rec - Cumulative, Current Cumulative Catchup - Cumulative - Disclosure Only | unchanged if Distinct; + catch-up if Nondistinct | 0 |
| Cumulative pre-606 (1) | Current Pre-ASC606 Revenue (Net Design Only) - Cumulative | unchanged | NULL |
| Positions (3) | Current Contract Position - POB, Current Contract Position - Contract Level, Current Reclass to UAR | recomputed (3.4, 3.6) | recomputed |

### 4.6 Downstream effect of an appended version

- **Journal entries.** Each appended row with `Current Period` in the JE range posts four things: Dr Deferred Revenue / Cr Revenue for `Current Rev Rec` (the catch-up); the reversal of `Previous Reclass to UAR` (Dr Deferred, Cr UAR); the new `Current Reclass to UAR` (Dr UAR, Cr Deferred); and, in the delta JE only, the carried-forward pre-606 amount (2594-2651, 2966-2985).
- **Reports.** Contract History (2670) lists every version whose `Current Period` is in range. Latest Contract Status (2784) shows the version with the maximum processing timestamp.

---

## 5. Worked example (hand-traced): UAT 09.15.2023, Contract 3, material right exercise with new POB added

The hand trace below reproduces the legacy replay (see "Evidence basis" in the header table) to 6 decimal places.

### 5.1 Upload (mod date entered: 2023-09-15)

| POB | SKU / Stratification | Mod Billing | Mod Qty | Start / End | Memo 1 | Status |
|---|---|---|---|---|---|---|
| POB #4 | Material Right - Services (Nondistinct; *P* = 1, *d* = 0, *r* = 0) | 0 | -1000 | 2023-01-01 / 2024-05-31 | Mod 1 09.15.23 | existing |
| POB #5 | Consulting 1 (Nondistinct; *P* = 300, *d* = 0.50, *r* = 0) | 1000 | 5 | 2023-06-01 / 2024-05-31 | Mod 1 09.15.23 | **new** |

### 5.2 Opening state: latest CL rows after the 08.15.2023 retrospective mod

| POB | Distinct? | RemQty | RemSSP | RemAlloc | RemBill | CumDel | CumRevRec | CumBill | CumSSPDel | CumCatchUp |
|---|---|---|---|---|---|---|---|---|---|---|
| #1 Hardware 1 | Distinct | 3 | 401 | 334.340803 | 800 | 0 | 0 | 0 | 0 | 0 |
| #2 Software 1 | Distinct | 1 | 184 | 153.413236 | 200 | 1 | 153.413236 | 200 | 184 | 34.880035 |
| #3 Consulting 1 | Nondistinct | 0.5 | 75 | 62.532569 | 200 | 0.5 | 62.532569 | 200 | 75 | 14.217406 |
| #4 Material Right - Services | Nondistinct | 1000 | 1000 | 833.767587 | 0 | 0 | 0 | 0 | 0 | 0 |

The opening transaction price is `Σ(CumRevRec + RemAlloc)` = 215.945805 + 1384.054195 = **1,600.000000**. That equals setup 1,300 + 07.15 modification 500 - 08.15 retrospective reduction 200. The opening contract-level position is 184.054195.

### 5.3 Trace

**Step 1: SSP clamp (1286-1331)**
- POB #4: Mid = -1000 × 1 × 1 = -1000, so the band is [-1000, -1000]. ModQty ≤ 0 and billing 0 > Lower -1000, so **Mod SSP Changes = -1000**.
- POB #5: Mid = 5 × 300 × 0.5 = 750, so the band is [750, 750]. ModQty > 0 and billing 1000 > Higher 750, so **Mod SSP Changes = 750**.

**Step 2: Remaining qty, SSP and billing (1440-1460)**
- POB #4: RemQty 1000 - 1000 = 0; RemSSP 1000 - 1000 = 0; RemBill 0 + 0 = 0.
- POB #5: RemQty 0 + 5 = 5; RemSSP 0 + 750 = 750; RemBill 0 + 1000 = 1000.

**Step 3: Pool and reallocate (1448-1455)**
- Pool = (334.340803 + 153.413236 + 62.532569 + 833.767587 + NaN) + (0 + 1000) = 1384.054195 + 1000 = **2384.054195**
- ΣRemSSP = 401 + 184 + 75 + 0 + 750 = **1410**; ratio = 2384.054195 / 1410 = 1.690818578
- RemAlloc: #1 401 × ratio = **678.018250**; #2 184 × ratio = **311.110618**; #3 75 × ratio = 126.811393 (before catch-up); #4 0 × ratio = **0**; #5 750 × ratio = **1268.113933**
- Unit SSP: #1 401/3 = 133.666667; #5 750/5 = 150.
- Unit Rev Rec (distinct): #1 678.018250/3 = 226.006083; #2 311.110618/1 = 311.110618.

**Step 4: Cumulative catch-up on Nondistinct rows (1526-1557)**
- #3: Progress = 0.5/(0.5 + 0.5) = 0.5; ShouldBe = 0.5 × (62.532569 + 126.811393) = 94.671981; **CatchUp = 94.671981 - 62.532569 = 32.139412**; CumRevRec = 94.671981; RemAlloc = 126.811393 - 32.139412 = 94.671981; UnitRR = 94.671981/0.5 = 189.343962; CumCatchUp = 14.217406 + 32.139412 = 46.356818.
- #4: Progress = 0/(0 + 0) = NaN, so ShouldBe = 0 and CatchUp = 0 - 0 = 0.
- #5: Progress = 0/(0 + 5) = 0, so CatchUp = 0.

**Step 5: Positions and reclass (1558-1594)**
- PosPOB: #1 0 - 0 = 0; #2 200 - 153.413236 = 46.586764; #3 200 - 94.671981 = 105.328019; #4 0; #5 0.
- PosC = **151.914783**, which is > 0 (net contract liability), so Reclass = 0 on every row.

**Step 6: Validation (1602-1605)**
- Every RemQty ≥ 0 and every non-VC RemBill ≥ 0, so the append proceeds.

### 5.4 Result: appended rows (replay output matches the hand trace)

| POB | RemQty | RemSSP | RemAlloc | RemBill | UnitRR | Current Rev Rec | CumRevRec | CumCatchUp | PosPOB | PosC | Reclass | POB End Date | Previous Period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #1 | 3 | 401 | 678.018250 | 800 | 226.006083 | 0 | 0 | 0 | 0 | 151.914783 | 0 | 2024-05-31 | 2023-08-15 |
| #2 | 1 | 184 | 311.110618 | 200 | 311.110618 | 0 | 153.413236 | 34.880035 | 46.586764 | 151.914783 | 0 | 2023-12-31 | 2023-08-15 |
| #3 | 0.5 | 75 | 94.671981 | 200 | 189.343962 | **32.139412** | 94.671981 | 46.356818 | 105.328019 | 151.914783 | 0 | 2023-12-31 | 2023-08-15 |
| #4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 151.914783 | 0 | **2024-05-31** (from mod line) | 2023-08-15 |
| #5 (new) | 5 | 750 | 1268.113933 | 1000 | 253.622787 | 0 | 0 | 0 | 0 | 151.914783 | 0 | 2024-05-31 | NULL |

- Closing TP = 248.085217 + 2351.914782 = **2,599.999999 ≈ 2,600** (opening 1,600 + 1,000).
- Gross JE for 2023-09-15 to 2023-09-15 (replay popup): **Dr 21001 Deferred Revenue 32.14 / Cr 5003 Revenue 32.14** (key "Contract 3 POB #3 Consulting 1").
- After the 10.31.2023 full delivery, total revenue on Contract 3 is 678.018250 + 464.523854 + 189.343962 + 0 + 1268.113933 = 2,600.000000, which equals total billing 2,600, and the contract-level position is 0.

### 5.5 Where the material right's consideration went (observation)

POB #4 held 833.767587 of allocated consideration. The modification released it into the pool together with the new 1,000. The changes in allocation were: POB #1 hardware +343.677447 (334.340803 to 678.018250), POB #2 software +157.697382, POB #3 consulting +64.278824 (of which 32.139412 was recognised immediately), POB #5 new consulting +1,268.113933, POB #4 -833.767587. **Of the 1,833.767587 released or added, only 1,268.113933 (69%) went to the services obtained by exercising the right. 565.653653 moved onto hardware, software and the existing consulting POB, which were not part of the option.** Section 6 assesses this.

### 5.6 Compact traces for the other in-scope UATs (carry-forward expected values)

| UAT / contract | Pool | ΣRemSSP | Ratio | RemAlloc after (by POB) | Catch-up | PosC after | Gross JE on mod date |
|---|---|---|---|---|---|---|---|
| 06.15 / Contract 1 (POB #1 qty -5, billing -500) | 1133.151635 - 500 = 633.151635 | 0 + 184 + 75 + 1000 = 1259 | 0.502900425 | #1 0; #2 92.533678; #3 43.016348 (pre-catch-up 37.717532); #4 502.900425 | #3 **-5.298816** | 338.450451 | Dr 5003 Revenue 5.30 / Cr 21001 Deferred 5.30 |
| 07.15 / Contract 3 (POB #1 qty +2, billing +500; SSP 207) | 1133.151635 + 500 = 1633.151635 | 707 + 184 + 75 + 1000 = 1966 | 0.830697678 | #1 587.303258; #2 152.848373; #3 55.308745 (pre 62.302326); #4 830.697678 | #3 **+6.993581** | 226.158054 | Dr 21001 6.99 / Cr 5003 6.99 |
| 07.15 / Contract 4 (POB #3 qty +2, billing +300; SSP 300) | 739.777949 + 300 = 1039.777949 | 459 + 408 + 450 + 0 = 1317 | 0.789504897 | #1 362.382747; #2 322.117998; #3 355.277203; VC #1 0 | 0 (#3 CumDel 0; VC CumRevRec 0) | 39.777948 | none |

---

## 6. Accounting assessment

### 6.1 Conclusion

The prospective path is a sound, internally consistent implementation of ASC 606-10-25-13(a). It pools unrecognised consideration with the modification consideration and allocates the pool to the remaining POBs, and for partially satisfied non-distinct POBs it adds the 25-13(b) cumulative catch-up, which together is a 25-13(c) combination. Transaction price is conserved, and the catch-up formula is right.

It is **not** a complete modification engine:

- There is no 25-12 separate-contract path.
- Remaining goods are priced at inception SSP.
- Material-right exercise is available only under the modification approach, and the released consideration is spread over unrelated POBs.
- "Nondistinct" does not separate a series (25-14(b), prospective) from a single non-distinct POB (catch-up).
- Several data conditions silently lose consideration or double-count journal entries.

Use it as the parity reference for the pooled reallocation and catch-up mechanics only.

### 6.2 Where the logic is correct

| ID | Behaviour | Authority | Evidence |
|---|---|---|---|
| C-01 | Pool = consideration included in the TP estimate and not yet recognised, plus the consideration promised in the modification, allocated to the remaining POBs | 606-10-25-13(a)(1)-(2) [S1] | 3.4; replay TP conservation (5.4, 5.6) |
| C-02 | For a partially satisfied non-distinct POB, the modification's effect on TP and on the measure of progress is recognised as a cumulative catch-up at the modification date, either direction | 606-10-25-13(b) [S1]; 606-10-25-35 (update the measure of progress) [S1] | 3.5; UAT catch-ups -5.298816 (06.15), +6.993581 (07.15), +32.139412 (09.15) |
| C-03 | Mixed remaining items: (a)-style reallocation plus (b)-style catch-up on the partially satisfied POB is consistent with the (c) objective | 606-10-25-13(c) [S1], [S3] | 3.5; UAT 06.15, 07.15 C3 |
| C-04 | Scope reductions are handled prospectively under 25-13, not as separate contracts; 25-12 requires a scope *increase* | 606-10-25-12(a) [S1]; Deloitte 9.2.2.7 "Contract Modifications That Reduce the Scope of a Contract" [S3] | UAT 06.15 |
| C-05 | Relative-SSP allocation of the pooled consideration (discount or premium spread proportionally) | 606-10-32-29, 32-31 [S1] | 3.4 |
| C-06 | Contract asset or liability determined per contract (POB positions netted at contract level) | 606-10-45-1 [S1] | 3.4, 3.6 |
| C-07 | The catch-up is posted as revenue on the modification date and tracked separately (period and cumulative), which supports the disclosure of revenue from POBs satisfied or partially satisfied in previous periods | 606-10-50-12A [S2], [S7] | 3.5; `Current Cumulative Catchup - *` columns |
| C-08 | A modification is effective from the date the user enters (no retroactive restatement of prior versions) | 606-10-25-10 (a modification is accounted for once approved) [S1] | 4.2; see A-10 for the gap |

### 6.3 Where it is simplified, wrong or incomplete

| ID | Finding | Class | Authority | Evidence / impact |
|---|---|---|---|---|
| A-01 | **No separate-contract path.** A distinct add-on priced at SSP is pooled with the existing contract. The original discount or premium spreads onto the add-on, and non-distinct POBs receive a catch-up | Incorrect when the 25-12 criteria are met | 606-10-25-12 [S1], [S3] | P-16b: +1 hardware unit at SSP 90. Legacy: hardware RemAlloc 515.625000 and consulting catch-up +0.384221. Under 25-12: 516.393443 and 0. **Inference:** users may approximate 25-12 by loading the add-on through "Load Contracts" |
| A-02 | Remaining existing goods keep **inception** SSP (carried unit SSP); only modification lines are priced at the template SSP version | Simplification | 606-10-25-13(a) treats the modification as a new contract, and 606-10-32-31 requires SSP "at contract inception" [S1]. **Inference:** this points to SSP at the modification date; practice commentary in [S3] was not verified verbatim | Misallocation when SSPs have moved since inception |
| A-03 | **Material-right exercise** is handled only as a modification. The released consideration (833.767587) and the new consideration (1,000) are spread by SSP over all remaining POBs; only 69% reached the services obtained through the option (5.5) | Policy gap (acceptable approach, not the preferred one) | Deloitte 11.7 (citing TRG Implementation Q&A 15 and TRG Agenda Papers 18, 25, 32, 34): Alternative A, continuation of the contract, is "generally preferable"; Alternative B, contract modification, is "acceptable" [S5]; 606-10-55-42 [S1] | Under Alternative A, POB #5 = 1,833.767587 and POBs #1-#3 are unchanged, with no catch-up. The legacy output shifts revenue between categories (hardware +343.68), which affects disaggregated revenue (**Inference**) |
| A-04 | **"Nondistinct" does not separate series from single POBs.** 25-13(a) expressly covers "remaining distinct goods or services in a single performance obligation identified in accordance with 606-10-25-14(b)" (series), and those are prospective | Incorrect for series POBs | 606-10-25-13(a) [S1] | A SaaS or managed-service series flagged "Nondistinct" receives a catch-up where 606 requires prospective treatment |
| A-05 | **Price-only increase on a fully satisfied contract is lost** (pool 0/0, so 0). Billing +50 but no allocation, so the amount is never recognised | Incorrect | 606-10-32-43 (amounts allocated to satisfied POBs are recognised in the period of change) and 32-45 [S1], [S4] | P-05 (D-06) |
| A-06 | **Reductions remove SSP at the template price, not the carried unit SSP.** Allocation is stranded on a POB with 0 remaining units (`UnitRR = inf`) | Incorrect | 606-10-25-13(a) [S1] | P-11: 50.338983 stranded (D-07) |
| A-07 | New-POB-only uploads and SKU swaps skip pooling with the existing contract; the contract position is computed on partial rows | Incorrect (accidental 25-12 treatment without testing the criteria) | 606-10-25-12, 25-13 [S1] | P-01, P-14 (D-01, D-03) |
| A-08 | Rows with an unrecognised Distinct flag are dropped; TP disappears from the latest-version view | Incorrect (completeness) | 606-10-25-13 [S1] | P-04: 6.23 lost (D-05) |
| A-09 | Orphan contracts, duplicate lines and re-uploads are all accepted | Incorrect (existence, accuracy) | 606-10-25-10 (a modification of an existing, approved contract) [S1] | P-02, P-03, P-19 (D-02, D-04) |
| A-10 | No approval date versus effective date; back-dated modifications accepted; versions ordered by wall-clock time | Incomplete (cut-off risk) | 606-10-25-10 [S1] | P-10 (D-08) |
| A-11 | Unpriced change orders cannot be modelled: `Mod Billing` must be a firm number, with no estimate or constraint workflow | Incomplete | 606-10-25-11 → 32-5 to 32-9 and 32-11 to 32-13 [S1] | VR-05, VR-06 |
| A-12 | No boundary between pre- and post-modification POBs, so a later VC change cannot be allocated under 32-45(a) | Incomplete | 606-10-32-45(a)-(b) [S1], [S4] | Handled ad hoc by the POB-specific VC button (see doc 05) |
| A-13 | Measure of progress for non-distinct POBs is units delivered only; no input methods | Simplification | 606-10-25-31 to 25-37, 55-17 [S1] | Cost-to-cost projects cannot be modelled |
| A-14 | "Reclass to UAR" merges contract assets (conditional right) with receivables (unconditional right); attribution by cumulative SSP delivered is an entity convention | Simplification | 606-10-45-3, 45-4 [S1], [S6] | Account naming and classification |
| A-15 | Reclass policy for VC lines differs between the delivery path and the modification path | Incorrect (inconsistent) | 606-10-45-1 [S1] | P-17: for the same net contract asset of 190, the delivery path reclassifies 180 and the modification path 190 (D-09) |
| A-16 | The period pre-606 amount is carried into the modification version, so the delta JE double-counts it | Incorrect (ERP delta posting) | n/a (legacy JE design) | P-08: +430 (D-10) |
| A-17 | No currency rounding or residual control internally; JE rounding is at summary level with no balancing check | Simplification | n/a | 3.7 |

### 6.4 Defect register and absent validations

| ID | Defect | Lines | Evidence |
|---|---|---|---|
| D-01 | A new-POB-only upload excludes the contract's existing POBs from pooling and re-versioning | 1356-1363 | P-01 |
| D-02 | An unknown contract name creates an orphan contract with a success popup | 1350-1367 | P-02 |
| D-03 | An existing POB ID with a different SKU becomes a second, new POB | 1333-1339 | P-14 |
| D-04 | Duplicate lines append duplicate same-timestamp rows; a re-upload is applied again | 1350-1352, 1638 | P-03, P-19 |
| D-05 | Rows whose `Distinct or Nondistinct` is not exactly "Distinct" or "Nondistinct" are silently dropped | 1521-1523 | P-04 |
| D-06 | The pool is dropped when the contract's ΣRemSSP = 0 | 1448-1455 | P-05 |
| D-07 | SSP reduction at the template price strands allocation; `inf` unit values are stored | 1286-1331, 1461-1468 | P-11 |
| D-08 | Back-dated modification accepted; `Previous Period` > `Current Period` | 1246, 1397-1398, 1503 | P-10 |
| D-09 | VC reclass override not re-applied after the final recompute | 1589-1594 | P-17 |
| D-10 | `Current Pre-ASC606 Revenue (Net Design Only)` carried forward, so the delta JE double-counts it | 1469-1473 (omission), 2966-2979 | P-08 |
| D-11 | A header-only upload reports "Mod Success" | 1641-1642 | P-07 |
| D-12 | `except TypeError: pass` aborts silently on data errors | 1646-1647 | P-18 |
| D-13 | Template stratification, entity, accounts and SSP version are silently ignored for existing POBs | 1385-1396 | code |
| D-14 | Degenerate catch-up when CumDel + RemQty = 0 reverses all recognised revenue on the POB | 1526-1540 | code (not probed) |
| D-15 | New POB rows store NULL in the setup-snapshot and pre-606 columns | 3.3 | P-01, UAT 09.15 POB #5 |

| Gap | Absent validation | Evidence |
|---|---|---|
| G-01 | Contract must exist | P-02 |
| G-02 | Unique key per upload; idempotent modification reference | P-03, P-19 |
| G-03 | Modification date ≥ latest event date of the contract | P-10 |
| G-04 | Date types; Mod Start ≤ Mod End; required dates for new POBs | code |
| G-05 | `Distinct or Nondistinct` domain | P-04 |
| G-06 | Sign consistency between `Mod Qty` and `Mod Billing` | P-15 |
| G-07 | Conflicting template attributes on existing POBs (warn or apply) | code (D-13) |
| G-08 | Pool must be absorbable (ΣRemSSP > 0; RemSSP = 0 when RemQty = 0) | P-05, P-11 |
| G-09 | `SKU_SSP` key uniqueness (a duplicate key fans out mod lines) | code |
| G-10 | Non-empty upload; explicit error instead of a silent abort | P-07, P-18 |

---

## 7. Port notes for eRev Cloud

### 7.1 Parity requirements (preserve)

| ID | Requirement |
|---|---|
| PR-01 | A modification upload carries signed **deltas** (`Mod Qty`, `Mod Billing`) per POB key (contract, POB ID, SKU) plus optional dates, memos and SSP version. The 15-column template stays importable |
| PR-02 | Modification SSP = consideration clamped into the SSP band `qty × list × (1 - d) × (1 ± r)`, with the negative-quantity branch; `qty = 0` gives SSP 0 (3.1; TC-06) |
| PR-03 | 25-13(a) pooled reallocation: pool = Σ unrecognised allocation + Σ modification consideration, allocated by remaining SSP (floored at 0) across **all** remaining POBs of the contract, including material-right and VC lines |
| PR-04 | Non-distinct catch-up exactly per 3.5, posted as revenue on the modification date and accumulated in the period and cumulative catch-up disclosure fields |
| PR-05 | Distinct POBs get no catch-up; the future unit revenue rate = RemAlloc / RemQty |
| PR-06 | POBs are modified in line (continuous POB lifecycle, no separate modification lines); new POBs are added as rows; every POB of a modified contract gets a new version |
| PR-07 | Version roll-forward: Current → Previous for the 14 balance fields; Previous Period ← Current Period; Current Period = modification date |
| PR-08 | Attribute precedence: memo and dates come from the modification line; accounting attributes of existing POBs are retained (with a warning; see FX-19) |
| PR-09 | Contract-level netting of POB positions; reclass to unbilled A/R only for a net contract asset, attributed by cumulative SSP delivered; the JE reverses the previous reclass and posts the current one |
| PR-10 | Integrity rules: SSP key must match (VR-08); remaining qty ≥ 0 and remaining billing ≥ 0 for non-VC lines (VR-09); all-or-nothing write |
| PR-11 | TP conservation: Σ(CumRevRec + RemAlloc) after = before + Σ Mod Billing (tolerance 1e-6) |
| PR-12 | Internal amounts at full precision; currency rounding only at posting (legacy JE: 4 dp per line, 2 dp summary) |
| PR-13 | Catch-up JE: Dr Deferred Revenue / Cr Revenue (reversed for a negative catch-up), keyed by POB revenue account and contract deferred account |
| PR-14 | Golden values TC-01 to TC-05 and TC-16 reproduce to 1e-6 in parity mode |

### 7.2 Behaviours to fix

| ID | Fix | Addresses |
|---|---|---|
| FX-01 | Evaluate 25-12 first (distinct add-on and price within the SSP band or tolerance): create a separate contract with no pooling; allow a user override with documented rationale | A-01 |
| FX-02 | Any line targeting a contract re-versions **all** its POBs; new POBs need an explicit flag; a SKU change is an explicit swap (terminate + add) | D-01, D-03, A-07 |
| FX-03 | Reject unknown contracts, duplicate keys and repeated modification references (idempotency key) | D-02, D-04, G-01, G-02 |
| FX-04 | Validate the Distinct / Non-distinct / Series domain at SSP and POB setup; never drop rows | D-05, G-05, A-04 |
| FX-05 | Model series POBs (25-14(b)) as prospective under 25-13(a); catch-up only for single non-distinct POBs | A-04 |
| FX-06 | If ΣRemSSP = 0, recognise the change on satisfied POBs at the modification date (policy OQ-07) or reject; never drop consideration | D-06, A-05 |
| FX-07 | Reductions remove SSP at the carried unit SSP; RemQty = 0 forces RemSSP = 0 and RemAlloc = 0 into the pool; no `inf` or NaN is persisted | D-07, A-06 |
| FX-08 | Separate approval, effective and processing timestamps; order versions by effective date and sequence; block back-dating past the latest event unless re-sequencing is explicit | D-08, A-10 |
| FX-09 | One reclass policy for every event type (VC lines included or excluded consistently) | D-09, A-15 |
| FX-10 | Zero period activity fields (including pre-606) on modification versions; roll the pre-606 cumulative | D-10 |
| FX-11 | No success on empty uploads; replace silent `TypeError` handling with explicit, row-level errors | D-11, D-12, G-10 |
| FX-12 | Configurable SSP basis for remaining goods at a 25-13(a) modification (inception or modification date) | A-02 |
| FX-13 | Material-right exercise policy: continuation approach (Alternative A) by default, modification approach selectable | A-03 |
| FX-14 | Currency rounding with deterministic residual allocation (largest remainder) and a balanced-JE check | A-17 |
| FX-15 | Persist event type, modification reference, approval evidence, user and a before/after audit trail | 4.2 |
| FX-16 | Unpriced change orders: estimated consideration with the VC constraint | A-11 |
| FX-17 | Input and other output measures of progress for non-distinct POBs | A-13 |
| FX-18 | Track the pre-/post-modification POB boundary so later VC changes can be allocated per 32-45(a) | A-12 |
| FX-19 | Warn or apply when template attributes differ from stored values for existing POBs; populate setup-snapshot fields for new POBs | D-13, D-15, G-07 |
| FX-20 | Validate date types and order, qty/billing sign consistency, and SSP key uniqueness | G-04, G-06, G-09 |
| FX-21 | Separate contract assets from receivables in account mapping | A-14 |

### 7.3 Test cases to carry forward

State for TC-01 to TC-05 = the UAT sequence replayed in order: SSP upload; setup 1.1 and 2.1; deliveries 1.31, 2.28, 3.31, 4.30; retrospective mod 05.15; POB VC 05.31; then the modifications under test; retrospective mod 08.15 before 09.15; full delivery 10.31 for TC-05. Probe state (TC-07 to TC-20) = the probe scripts in the scratch folder.

| ID | Scenario | Expected (parity mode) | Expected (fixed engine) |
|---|---|---|---|
| TC-01 | UAT 06.15, Contract 1: POB #1 qty -5, billing -500 | RemAlloc #1 0, #2 92.533678, #3 43.016348, #4 502.900425; catch-up #3 -5.298816; PosC 338.450451; JE Dr 5003 5.30 / Cr 21001 5.30 | same |
| TC-02 | UAT 07.15, Contract 3: POB #1 qty +2, billing +500 | RemSSP #1 707; RemAlloc #1 587.303258, #2 152.848373, #3 55.308745, #4 830.697678; catch-up #3 +6.993581; PosC 226.158054; JE Dr 21001 6.99 / Cr 5003 6.99 | same (SSP basis per OQ-02) |
| TC-03 | UAT 07.15, Contract 4: POB #3 qty +2, billing +300 | RemAlloc #1 362.382747, #2 322.117998, #3 355.277203, VC 0; catch-up 0; PosC 39.777948; POB #3 dates 2023-06-01 to 2024-05-31 | same |
| TC-04 | UAT 09.15, Contract 3: material right -1000 / new POB #5 +5 for 1000 | Table 5.4; closing TP 2,600.000000; JE Dr 21001 32.14 / Cr 5003 32.14 | Continuation policy: POB #5 RemAlloc 1,833.767587; #1 334.340803, #2 153.413236, #3 62.532569; no catch-up; TP 2,600 |
| TC-05 | UAT end state after 10.31 full delivery | Contract 3 CumRevRec #1 678.018250, #2 464.523854, #3 189.343962, #4 0, #5 1,268.113933; PosC 0 | depends on TC-04 policy; PosC 0 |
| TC-06 | SSP clamp unit cases (3.1 table); qty 0 with billing 50 → 0; qty -1 with billing +90 → -76.5 | as listed | first five rows same; sign mismatch rejected |
| TC-07 | P-16b: discounted contract E, +1 hardware at SSP 90 | hardware RemAlloc 515.625000; consulting CumRevRec 70.056352 (catch-up +0.384221) | 25-12: hardware 516.393443 (or add-on as a separate contract at 90); consulting 69.672131; no catch-up |
| TC-08 | P-05: fully delivered B, price +50, qty 0 | RemBill 50, RemAlloc 0, TP stays 180 (50 lost) | revenue +50 at the modification date (or reject); TP 230 |
| TC-09 | P-11: D, remove 2 remaining hardware units for 0 | hardware RemSSP 27, UnitSSP inf, RemAlloc 50.338983; consulting 279.661017 | hardware RemSSP 0, RemAlloc 0; consulting RemAlloc 330.000000; TP 510 |
| TC-10 | P-01: new POB only on contract A | 1 row appended; existing POBs not re-versioned | 3 rows appended; identical PosC on all rows |
| TC-11 | P-02: unknown contract Z | orphan created, success | rejected |
| TC-12 | P-03 duplicate lines; P-19 re-upload | duplicate rows; RemQty 8 after re-upload | rejected |
| TC-13 | P-04: Distinct flag "distinct" | Widget row dropped; latest TP 413.767313 (should be 420) | rejected at SSP upload |
| TC-14 | P-08: delivery pre-606 360/70, then modification on 2023-02-15 | delta JE on 2023-02-15: Dr 5001 360, Dr 5003 70, Cr 21001 430 | delta JE on the modification date = 0 |
| TC-15 | P-10: modification dated 2023-01-15 after the 2023-01-31 delivery | accepted; Previous Period 2023-01-31 | rejected (or explicit re-sequence) |
| TC-16 | P-12: A consulting qty -0.5, billing -75 (down to delivered) | POB #2 RemQty 0, RemAlloc 0, CumRevRec 75, catch-up 0; hardware RemAlloc 540; TP 975 | same |
| TC-17 | P-15: qty -1 with billing +90 | hardware RemSSP 463.5; consulting catch-up +11.594708; PosC -11.594708 | rejected |
| TC-18 | Validation semantics VR-03 to VR-09 (exact legacy texts in Section 2) | messages as in Section 2 | semantic parity (row-level errors) |
| TC-19 | P-17: priced VC line, net contract asset 190 | delivery reclass 180 + VC 0; modification reclass 180 + VC 10 | one policy; total reclass = 190 in both paths |
| TC-20 | P-07: header-only upload | "Mod Success", 0 rows | error "no modification lines" |

### 7.4 Open questions

| ID | Question |
|---|---|
| OQ-01 | Default policy for material-right exercise: continuation (Alternative A, preferred per [S5]) or modification (legacy)? Is a parity mode required? |
| OQ-02 | SSP basis for remaining goods in a 25-13(a) modification: inception (legacy) or modification date? Configurable per tenant? |
| OQ-03 | Is the new-POB-only upload pattern (D-01) used deliberately to approximate 25-12? If so, FX-01 must ship before FX-02 |
| OQ-04 | VC reclass policy: exclude VC lines from attribution (delivery path) or include them (modification path)? |
| OQ-05 | Which pandas and numpy versions shipped in the production Windows build? The golden values here were generated with pandas 2.1.4 / numpy 1.26.4; confirm before locking golden masters (doc 07) |
| OQ-06 | Should a POB flagged "Nondistinct" be re-classified as series or single POB during migration? This needs a data-migration rule |
| OQ-07 | A price-only change on fully satisfied POBs: recognise immediately, or reject and route to POB-specific VC? |
| OQ-08 | Should a modification ever carry a pre-ASC 606 amount (for example an ERP credit memo posted as revenue)? The template has no such column |
| OQ-09 | UI parity: keep the legacy popup texts verbatim, or semantic parity only? |

---

## Sources

| ID | Source | Used for |
|---|---|---|
| S1 | FASB, ASU 2014-09 Section A (Topic 606 amendments): [external website reference removed] Paragraph text was verified against the extracted copy in `~/dev/erev/.scratch/04-asc606-technical/asu/ASU_2014-09_Section_A.txt` | 606-10-25-10, 25-11, 25-12, 25-13(a)-(c), 25-35, 32-29, 32-31, 32-43 to 32-45, 45-1, 45-3, 45-4, 55-17, 55-42 to 55-45 |
| S2 | FASB, ASU 2016-20 (Technical Corrections and Improvements to Topic 606): [external website reference removed] Verified against the extracted copy `ASU_2016-20.txt` | Adds 606-10-50-12A |
| S3 | Deloitte DART, Revenue Roadmap 9.2 "Types of Contract Modifications": [external website reference removed] | 25-12 and 25-13 discussion; 9.2.2.7 scope reductions |
| S4 | Deloitte DART, 9.4 "Change in Transaction Price After a Contract Modification": [external website reference removed] | 606-10-32-45(a)-(b) |
| S5 | Deloitte DART, 11.7 "Customer's Exercise of a Material Right": [external website reference removed] | Alternative A (continuation) generally preferable; Alternative B (modification) acceptable; TRG Implementation Q&A 15 (TRG Agenda Papers 18, 25, 32, 34) |
| S6 | Deloitte DART, 14.4 "Contract Assets": [external website reference removed] | 606-10-45-3; contract asset versus receivable |
| S7 | Deloitte DART, 15.2 "Contracts With Customers" (disclosure): [external website reference removed] | 606-10-50-12A; 50-8 to 50-10 |

Evidence artefacts (scratch, not product): `~/dev/erev/.scratch/prospective-mod/` contains `legacy_harness.py` (Qt-stubbed runner for the unmodified legacy methods), `replay_uat.py` / `replay_uat.out` (full UAT sequence; snapshots in `runs/uat_replay/snapshots/`), and `probes.py`, `probes2.py`, `probes3.py` with their `.out` files (P-00 to P-19, VR probes).

