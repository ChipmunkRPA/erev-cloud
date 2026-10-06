# 04 - Retrospective Contract Modification (legacy `browse_file_RetroMod`)

Scope: `~/dev/erev-legacy/eRev.py` lines 1655-2132 (`browse_file_RetroMod`). Shared state was read from `browse_file_Contracts` (621-825), `browse_file_Deliveries` (826-1169), `browse_file_ProsMod` (1170-1654), `browse_file_POB_specific_VC` (2133-2539) and the journal-entry functions (2540-2669, 2862-3012).
Sources: legacy `eRev.py`, `README.md`, `ops/Blank Templates/Contract Modification Template.xlsx`, `ops/Example UATs/Contract Mod UAT/Contract Modification Template 05.15.2023 - retrospective vc + POB increases.xlsx` and `... 08.15.2023 - retrospective POB reduction.xlsx`, plus the other UAT files needed to rebuild state, and `ops/libnew/libwarm/db/ASC606.db` (opened read-only).

How the numbers were checked: the legacy module was run headlessly, with PySide6 stubbed, against a scratch SQLite DB (`~/dev/erev/.scratch/legacy-retro-mod/harness.py`). The full UAT sequence was replayed in date order: SSP upload, contract setups 1.1 and 2.1, deliveries 1.31-4.30, retro mod 05.15, POB-specific VC 05.31, prospective mods 06.15 and 07.15, retro mod 08.15, prospective mod 09.15, then delivery 10.31. The first 24 replayed rows match the 24 rows in the legacy `ASC606.db` (setup plus 1.31 delivery) to a maximum absolute difference of 5.7e-14. pandas 2.2.3 and pandas 3.0.5 give identical output (difference 0.0). Synthetic edge cases are in `scenarios.py` / `scenarios_out.txt` in the same folder. Every number below marked "harness" comes from those runs.

Conventions: "L1234" means eRev.py line 1234. c = contract (`Contract Unique Name`), i = a POB row. CRQ, CRS, CRA, CRB = Current Remaining Qty, SSP, Allocation and Billing. PSSPD = Previous SSP Delivered - Cumulative. RRC = Current Rev Rec - Cumulative.

---

## 1. Purpose, trigger, inputs, outputs

### 1.1 Purpose

This function accounts for a contract modification on a cumulative catch-up basis. For every contract with at least one row in the upload, it:

1. adds the modification quantity and consideration to the affected POB lines;
2. re-allocates the modified total transaction price across all POB lines by relative SSP, counting both delivered and undelivered SSP;
3. recognises in the modification period the difference between the revenue that "should" have been recognised to date on the new allocation and the revenue actually recognised.

README.md states that it "supports cumulative catchup calculation for all POBs in a retrospective contract modification" and that modifications are "done in line with the existing POBs". The same template also drives the prospective and POB-specific-VC buttons.

### 1.2 Trigger and UI flow

| Step | Behaviour | Lines |
|---|---|---|
| Button | `QPushButton("Retrospective Contract Mod")` in the "Mod Operations" row | L133-136 |
| Wiring | `self.button5.clicked.connect(lambda: self.browse_file_RetroMod())` | L234 |
| File pick | `QFileDialog.getOpenFileName(self, "Select File")`, with no file-type filter | L1656-1657 |
| Mod date | `QInputDialog.getText(..., "Date Input", "Enter the retrospective contract mod date in this format (YYYY-MM-DD):")` | L1661-1662 |
| Date parse | `QDate.fromString(input_text, "yyyy-MM-dd")`, converted to a midnight `datetime` (`mod_date`) | L1664, L1730 |
| Read | `pd.read_excel(file_path)` reads the first sheet only | L1672 |
| Validate | column titles, then numeric checks | L1674-1709 |
| Load DB | latest `Contract_Live` version per POB, plus all of `SKU_SSP` | L1711-1727 |
| Compute | SSP join, mod SSP, merge, re-allocation, catch-up | L1730-2077 |
| Gate | negative remaining qty or billing check | L2082-2087 |
| Persist | `merged_df.to_sql("Contract_Live", conn, if_exists="append", index=False)` | L2117 |
| Notify | success popup | L2119-2120 |

### 1.3 Inputs: template `Contract Modification Template.xlsx`, `Sheet1`, columns A-O

The title check is exact and case-sensitive, but column order does not matter (L1674-1681). The UAT files use Excel dates for D, E and L and integers for G, H, J and K; 08.15 row 3 has `Mod Qty` = -0.5 (float).

| Col | Title | Type (UAT) | Required by code | Use in this function | Lines |
|---|---|---|---|---|---|
| A | Contract Unique Name | text | title required; blanks not checked | cast to `str`; part of the POB key; selects which contracts are re-allocated. It is not checked against the DB, so an unknown name creates a new stand-alone contract (harness S14). | L1735, L1817-1821, L1839-1846 |
| B | POB Unique ID | text | title required | cast to `str`; part of the key. An unknown ID creates a new POB line. | L1737, L1817-1821 |
| C | SKU Name | text | title required | part of the key and the SSP join key; not cast to `str`. A numeric SKU name against the TEXT `SKU_SSP` column fails the merge with a critical popup: "You are trying to merge on int64 and object columns for key 'SKU Name'. If you wish to proceed you should use pd.concat" (harness S16). If both sides were numeric, the string concatenation at L1821 would raise `TypeError`, which L2124 swallows silently (inference from code). | L1744, L1821 |
| D | Mod Start Date | date | optional | overwrites `POB Start Date` on modified lines; a blank keeps the stored date. Not validated and not used in any calculation. | L1859-1861 |
| E | Mod End Date | date | optional | same as D, for `POB End Date` | L1862-1864 |
| F | ASC 606 Stratification | text | title required | SSP join key. For existing POBs the stored value wins (`fillna` order); the value is used for the VC exclusions. | L1744, L1868-1869, L1993, L2071, L2083 |
| G | Mod Billing | number, non-blank | yes (numeric, no NaN) | the incremental consideration, signed. It increases (+) or decreases (-) the contract transaction price, is added to remaining billing, and is clamped into the mod SSP range. | L1682, L1799-1811, L1936, L1952-1956 |
| H | Mod Qty | number, non-blank | yes (numeric, no NaN) | the incremental quantity, signed; added to remaining qty. Its sign selects the clamp branch. | L1682, L1798, L1923-1924 |
| I | Selling Entity | text | title required | used only when the POB is new (right-only merge row); ignored for existing POBs | L1870-1871 |
| J | Deferred Revenue Account | int | title required | only new POBs; ignored for existing POBs (harness S05: 29999 uploaded, 21002 kept) | L1874-1876 |
| K | Unbilled A/R Account | int | title required | only new POBs | L1877-1879 |
| L | SSP Version | date or text | title required | cast to `str` and used as the SSP join key, which prices the increment (list price, discount %, range %). For existing POBs the stored `SSP Version`, list price, discount and range stay unchanged. | L1732-1734, L1743-1746, L1872-1873, L1886-1892 |
| M-O | Memo 1-3 | text | titles required | mod values overwrite the stored memos on modified lines; a blank keeps the stored memo | L1855-1857 |

DB inputs:

- `Contract_Live`: the latest row per `Record Unique ID without time`, selected by `MAX("Processing Time Log")` in SQL (L1712-1720) and again by `idxmax` in pandas (L1825-1829).
- `SKU_SSP`: all rows (L1721-1723), columns `SKU Unique ID, SKU Name, Distinct or Nondistinct, SKU Unit List Price, ASC 606 Stratification, Midpoint Discount Percentage, SSP Range Method (+-), SSP Version, Revenue Account`.

### 1.4 Outputs

| Output | Detail | Lines |
|---|---|---|
| `Contract_Live` (append-only) | One new row for **every POB line of every contract that has at least one upload row**, not only the modified lines, plus one row per new POB. All 71 columns are written; see section 4 for which are recomputed, rolled or carried. | L1839-1846, L2117 |
| Excel files | None. The function writes no report; JE and history reports come from separate buttons. | - |
| Popups | See VR table in section 2: warning "Invalid Date"; information "File Upload Error" / "Missing fields:" / "Extra fields:" / "Format Error" / "Mod Upload Failed" / "Mod Failed" / "Mod Success"; critical "Error Notification". | L1666-2131 |
| Downstream effect | The gross revenue JE button books `Current Rev Rec` (catch-up) Dr deferred revenue / Cr revenue. It then reverses `Previous Reclass to UAR` and books `Current Reclass to UAR` for records whose `Current Period` falls in the chosen range. | L2594-2651 |

---

## 2. Validation rules

| ID | Condition (exact) | Popup type / title / message | Effect | Lines |
|---|---|---|---|---|
| VR-retro-mod-01 | `file_path` empty (dialog cancelled) | none | returns silently | L1660 |
| VR-retro-mod-02 | date dialog `ok` is False (cancelled) | none | returns silently | L1663 |
| VR-retro-mod-03 | `not QDate.fromString(input_text, "yyyy-MM-dd").isValid()`: needs a 4-digit year, 2-digit month and 2-digit day, and a real calendar date. `2023-5-15` is rejected (harness S12). | warning / "Invalid Date" / "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." | stop; nothing written | L1664-1667 |
| VR-retro-mod-04 | `missing_titles or extra_titles`, where missing = expected titles not in the sheet and extra = sheet titles not in the expected 15 | information / "File Upload Error" / "Error: The Excel file has incorrect or missing column titles." | stop (no exception) | L1674-1687 |
| VR-retro-mod-05 | as VR-04 with `missing_titles` non-empty | information / "Missing fields:" / comma-joined missing titles (harness S10: "Memo 3") | follows VR-04 | L1688-1689 |
| VR-retro-mod-06 | as VR-04 with `extra_titles` non-empty. Duplicate headers, which pandas renames `Memo 1.1`, count as extra. | information / "Extra fields:" / comma-joined extra titles | follows VR-04 | L1690-1691 |
| VR-retro-mod-07 | `pd.to_numeric(df[col], errors='raise')` raises `ValueError`/`TypeError` for `Mod Billing`, then `Mod Qty` | information / "Format Error" / "Error: The column '{column}' should contain numeric values." | stop at the first failing column. The converted result is discarded, but `read_excel` already infers numeric text (harness S02, "400" stored as text, processed normally). | L1695-1699, L1706-1709 |
| VR-retro-mod-08 | `df[col].isna().any()` for `Mod Billing` / `Mod Qty` (blank cell) | information / "Format Error" / "Error: The column '{column}' should contain numeric values." (harness S11) | stop | L1702-1705 |
| VR-retro-mod-09 | any upload row with `_merge == 'left_only'` after the left join to `SKU_SSP` on `['SKU Name','ASC 606 Stratification','SSP Version']` | information / "Mod Upload Failed" / "Some Mod POBs are not matched with the existing SSP databse. Re-upload the file after fixes! \nPOB with issues: \n{comma-joined SKU Names}", then `raise Exception("The process is stopped for users to fix the file")`, then critical / "Error Notification" / same text (harness S09) | stop; nothing written | L1749-1758, L2126-2131 |
| VR-retro-mod-10 | `Current Remaining SSP < 0` after adding the mod SSP change | none (silent correction) | floored to 0 | L1929 |
| VR-retro-mod-11 | `(Current Remaining Qty < 0).any()` over all rows, including VC, **or** `(Current Remaining Billing < 0).any()` over rows where `ASC 606 Stratification != "VC"`. Checked after all calculations. | information / "Mod Failed" / "Qty or Price modified cannot reduce the remaining qty or remaining billing to negative. Check your uploads please.", then critical / "Error Notification" / "The process is stopped for users to fix the file" (harness S08, S08b) | stop; nothing written | L2082-2087 |
| VR-retro-mod-12 | `Contract_Live` not found in `sqlite_master` at write time | critical / "Error Notification" / "No contract table is found!" | stop. Unreachable in practice: the L1725 read fails first. Harness S17 (SSP table present, no `Contract_Live`) shows critical / "Error Notification" / "Execution failed on sql '...SELECT t1.* FROM Contract_Live t1 ...': no such table: Contract_Live". | L2091-2098, L2121-2123 |
| VR-retro-mod-13 | any `TypeError` raised anywhere inside the `try` | none | **swallowed silently**; nothing written. Meant for a cancelled dialog, but it also hides real type errors. | L2124-2125 |
| VR-retro-mod-14 | any other exception | critical / "Error Notification" / `str(e)` | stop; `conn.close()` attempted with a bare except | L2126-2131 |
| VR-retro-mod-15 | success path | information / "Mod Success" / "Retrospective Mod has been processed with uploaded modifications for the current date :)" | rows appended | L2119-2120 |

Validations that do not exist, each confirmed by harness or code:

| Missing rule | Observed behaviour | Evidence |
|---|---|---|
| Header-only file (no data rows) | "Mod Success" shown, 0 rows written | harness S01 |
| Contract or POB in upload exists in `Contract_Live` | Unknown contract becomes a stand-alone contract; unknown POB becomes a new line | S14, S04 |
| Duplicate upload rows for the same POB | Fan-out: the existing line is duplicated and the contract re-allocation double counts | S03 |
| Mod date not earlier than the POB's latest `Current Period` | Back-dated mods accepted (`Current Period` 2023-01-15 with `Previous Period` 2023-04-30) | S13 |
| `Mod End Date >= Mod Start Date`; dates are dates | not checked | L1859-1865 |
| Key uniqueness in `SKU_SSP` (same SKU/stratification/version twice) | The left join fans out mod rows | L1743-1746 (code) |
| Selling entity or account changes on existing POBs | Silently ignored | S05 |
| Qty reduced to 0 while SSP or allocation remains | Written with `Current Unit SSP = inf`; allocation is stranded | S15 |
| Contract with zero total SSP | Allocation becomes NaN, then 0; transaction price is lost | L1949 (code) |

---

## 3. Calculation logic

All arithmetic is pandas float64. The function never rounds. Sums over a group skip NaN.

### 3.1 Preparation and scope

| Step | Logic | Lines |
|---|---|---|
| Mod date | `mod_date = datetime.combine(qdate.toPython(), datetime.min.time())`; written to every output row as `Current Period` | L1730-1731, L1881 |
| Casts | `SSP Version`, `Contract Unique Name`, `POB Unique ID` are cast to `str`. An all-midnight date column renders as `YYYY-MM-DD`, which matches the string stored by the SSP upload (L574); the UAT join succeeds. | L1732-1738 |
| SSP enrichment | `upload LEFT JOIN SKU_SSP ON (SKU Name, ASC 606 Stratification, SSP Version)` adds SKU Unique ID, Distinct or Nondistinct, list price, midpoint discount %, range %, revenue account. Duplicate SSP keys fan out (harness S18). | L1743-1746 |
| POB key | `Record Unique ID without time = Contract + " " + POB + " " + SKU Name` | L1817-1821 |
| Latest state | latest `Contract_Live` row per key (SQL MAX, then `idxmax`) | L1712-1720, L1825-1829 |
| Merge | `latest FULL OUTER JOIN upload ON key`; overlapping upload columns get the suffix `_new` | L1832-1834 |
| Scope | `C = {Contract Unique Name of rows where Mod Qty and Mod Billing are both non-null}`; keep rows with `Contract Unique Name ∈ C` | L1839-1846 |

Scope caveat, confirmed in harness S04: the filter reads the left-side (stored) contract name before it is filled from `_new` (L1849). A new POB row therefore carries NaN, and `isin([NaN])` keeps only NaN rows. When an upload for an existing contract contains **only** new POBs, the existing lines drop out of scope. One row is written, with allocation equal to its own billing, and nothing is re-allocated. If the upload also has any existing POB of that contract (S04b), all lines are re-allocated.

### 3.2 Attribute coalescing (L1849-1894)

| Output column(s) | Rule |
|---|---|
| Contract Unique Name, POB Unique ID, SKU Name | stored value, else upload |
| Memo 1, Memo 2, Memo 3 | **upload value**, else stored |
| POB Start Date, POB End Date | **upload `Mod Start/End Date`**, else stored |
| ASC 606 Stratification, Selling Entity, SSP Version, Deferred Revenue Account, Unbilled A/R Account | stored value, else upload (changes on existing POBs are ignored) |
| SKU Unique ID, Distinct or Nondistinct, SKU Unit List Price, Midpoint Discount Percentage, SSP Range Method (+-), Revenue Account | stored value, else from the upload's SSP join |
| Previous Period | stored `Current Period` (NaN for new POBs) |
| Current Period | `mod_date` |
| Original POB Total Selling Price, Original POB Total Qty, Original SSP - Midpoint/Higher/Lower, Original Extended SSP, Original Total Contract Price, Original Total Contract SSP, Original Allocation, Original Unit SSP, Original Unit Rev Rec | not touched, so carried forward; NULL for new POBs (S04b) |

### 3.3 SSP of the increment: midpoint, range, clamp (L1770-1815)

For each upload row u, using the SSP attributes of the upload's `SSP Version`:

```
MidSSP_u  = ModQty_u * ListPrice_u * (1 - MidDisc_u)          # L1770-1775
LowSSP_u  = MidSSP_u * (1 - Range_u)                          # L1776-1785
HighSSP_u = MidSSP_u * (1 + Range_u)                          # L1786-1795
if ModQty_u > 0:                                              # L1798-1804
    ModSSP_u = HighSSP_u if ModBilling_u > HighSSP_u else LowSSP_u if ModBilling_u < LowSSP_u else ModBilling_u
else:                                                         # L1805-1811 (ModQty <= 0; interval is [High, Low], both <= 0)
    ModSSP_u = HighSSP_u if ModBilling_u < HighSSP_u else LowSSP_u if ModBilling_u > LowSSP_u else ModBilling_u
```

- Inside the range, the stated mod price becomes the SSP. Outside it, the **nearest bound** is used; there is no option to fall back to the midpoint. `Mod Midpoint SSP` is only the anchor for the range.
- `ModQty = 0` gives Mid = Low = High = 0, so `ModSSP = 0` whatever the billing. A price-only change (for example a VC re-estimate) adds consideration but no SSP (S05).
- Contract setup uses the same clamp but has no negative branch (L692-700).
- UAT values: 05.15 Contract 2 POB #1, +2 units at 400: Mid 180, Low 153, High 207, so ModSSP = **207**. 08.15 Contract 3 POB #1, -4 units at -200: Mid -360, Low -306, High -414; -200 > -306, so ModSSP = **-306**. 08.15 Contract 4 POB #3 (Consulting, range 0), -0.5 units at -50: Mid = Low = High = -75, so ModSSP = **-75**.

### 3.4 Remaining quantity, SSP and billing

```
Previous <- Current for the 14 roll fields (section 4)        # L1897-1920
CRQ_i' = CRQ_i + ModQty_i                                     # L1923-1924 (NaN -> 0)
CRS_i' = max(0, CRS_i + ModSSP_i)                             # L1925-1929 (silent floor)
CRB_i' = CRB_i + ModBilling_i                                 # L1952-1956
CurrentUnitSSP_i = CRS_i' / CRQ_i'   (NaN -> 0; x/0 -> inf is NOT caught)   # L1957-1959 (final value)
Current Delivery = Current Rev Rec = Current Billing = Current Cumulative Catchup - Disclosure Only = 0   # L1965-1968
Delivery/RevRec/Billing/CumCatchup cumulatives: fillna(0), otherwise carried   # L1969-1976
```

### 3.5 Re-allocating the modified transaction price (L1932-1950)

For each in-scope contract c, the sums run over the in-scope rows. `CRA_i` and `RRC_i` are the stored values from the latest version:

```
TP_c   = Σ CRA_i + Σ ModBilling_i + Σ RRC_i          # remaining allocation + mod consideration + revenue to date
SSP_c  = Σ CRS_i' + Σ PSSPD_i                        # undelivered SSP after mod + delivered SSP to date
r_c    = TP_c / SSP_c
CRA_i_pre = fillna0( r_c * (CRS_i' + PSSPD_i) ) - PRRC_i     # PRRC = Previous Rev Rec - Cumulative
```

- `r_c * (CRS_i' + PSSPD_i)` is the line's total allocation under a full relative-SSP re-allocation of the modified transaction price over **all** lines, delivered SSP included. Invariant (harness): `Σ(CRA + RRC) = TP_c`, which gives 1300.0 for Contract 2 at 05.15 (900 original + 400).
- The discount (`SSP_c - TP_c`) is spread proportionally to every line. There is no specific-discount or residual path.
- A VC line has SSP 0, so its total allocation is 0. Its negative consideration (`CRB` -100 on Contract 2) is already inside `TP_c` through the stored allocations and is spread over the real lines.
- The `Distinct or Nondistinct` flag is not consulted; every line gets the catch-up. By contrast, the prospective function catches up only non-distinct lines (L1521-1545).
- `SSP_c = 0` gives NaN (or inf × 0 = NaN), filled with 0, so the transaction price is lost (code inspection).

### 3.6 Cumulative catch-up (L2019-2053)

```
ShouldBe_i  = fillna0( (CRA_i_pre + RRC_i) / (CRS_i' + PSSPD_i) * PSSPD_i )   # = r_c * PSSPD_i when the line's total SSP != 0
CatchUp_i   = ShouldBe_i - RRC_i                        -> Current Cumulative Catchup - Disclosure Only        L2026-2029
CumCatchUp_i += CatchUp_i                               -> Current Cumulative Catchup - Cumulative - Disclosure Only   L2030-2033
Current Rev Rec_i = CatchUp_i                                                                                   L2035-2036
RRC_i'      = RRC_i + CatchUp_i  (= ShouldBe_i)                                                                 L2037-2040
CRA_i'      = CRA_i_pre - CatchUp_i  (= r_c * CRS_i')                                                           L2044-2046
Current Remaining Unit Rev Rec_i = CRA_i' / CRQ_i'   (NaN -> 0; inf possible)                                   L2048-2053
```

- **Measure of progress** = SSP delivered to date, i.e. units delivered times the unit SSP at each delivery, carried in `Current SSP Delivered - Cumulative`. It is not units, cost or time. Increments priced at a different unit SSP make progress SSP-weighted: Contract 2 POB #1 delivered-SSP share is 76.5 / 819 = 9.34%, against a unit share of 1 / 10 = 10%.
- Sign convention: a positive catch-up increases revenue; a negative one reduces it (S05, VC -50: -11.064).
- A no-op retro mod (qty 0, billing 0) gives **zero** catch-up only if every past version shares one contract ratio (S07a). After a prospective mod, a no-op retro mod trues cumulative revenue up to the single contract ratio and reverses the prospective effect (S07b: +35.686 on Contract 3).
- The later delivery path uses the post-mod `Current Remaining Unit Rev Rec` (L1028-1029). Harness S19: 1 unit of Contract 2 POB #1 on 2023-05-31 recognises 77.886710.

### 3.7 Contract position and reclass to unbilled A/R (L2054-2071)

```
Position_POB_i = BillingCum_i - RRC_i'           # + = contract liability (deferred revenue), - = contract asset
Position_CL_c  = Σ_i Position_POB_i              # includes the VC line
Reclass_i      = (-Position_CL_c / Σ_c SSPDelivCum_i) * SSPDelivCum_i   if Position_CL_c < 0 else 0
Reclass_i      = 0 where ASC 606 Stratification == "VC"
```

- The contract asset is allocated to lines by delivered SSP share. When `Σ SSPDelivCum = 0` and the position is negative, the result is NaN (0/0) and is stored as NULL; a new POB row gets NaN (S04b).
- The same block runs once as a provisional calculation (L1977-1993) and again after the catch-up. Only the second result is persisted.
- JE consumption (L2594-2651) uses positive = debit, negative = credit:
  - Dr deferred revenue `Current Rev Rec`, Cr revenue `Current Rev Rec`;
  - Dr deferred / Cr UAR `Previous Reclass to UAR` (reversal);
  - Cr deferred / Dr UAR `Current Reclass to UAR`;
  - grouped by contract + account for balance-sheet lines and by POB key + account for revenue; `round(4)`, filter `round(2) != 0`, then `round(2)`.

### 3.8 Pre-ASC 606 revenue (net design) and other stale fields

- The function never reads, rolls or resets `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative`, `Current Pre-ASC606 Revenue (Net Design Only)` or `Current Pre-ASC606 Revenue (Net Design Only) - Cumulative` (absent from L1897-1920 and L1965-1968). They carry forward from the last delivery version.
- Harness S06 shows the effect. A retro mod dated 2023-02-01 on Contract 1 copied 66 (POB #2) and 88 (POB #3) into the mod version. `journal_entries_delta` over 2023-01-01..2023-02-28 then posts them twice: revenue 5002 +13.47 instead of -52.53, 5003 +127.68 instead of +39.68, deferred 21001 -12.31 instead of +141.69 (difference 154 = 66 + 88).
- `Current SSP Delivered` (period amount) is also carried forward, e.g. 200 / 184 / 75 in S06. JEs do not use it, but contract history shows it.

### 3.9 Types, precision, residuals

- The `Contract_Live` schema comes from the first `to_sql(..., if_exists="replace")` in contract setup (L812). With SQLite INTEGER affinity, non-integral values are stored as REAL and integral ones as INTEGER; nothing is truncated (legacy DB: `Current Rev Rec` 128.840436075322 in an INTEGER column).
- No rounding and no residual true-up. Harness sums match `TP_c` to about 1e-13 (e.g. catch-up -7.1e-15 in S06). Rounding happens only in JE reports.
- `inf` and NaN can be persisted: `Current Unit SSP` / `Current Remaining Unit Rev Rec` = inf when qty is 0 but SSP remains (S15); `Current Reclass to UAR` NaN for a new POB (S04b).

---

## 4. State transitions and versioning

- **Append-only versions.** Each successful run inserts one snapshot row per in-scope POB line with a single `to_sql(..., if_exists="append")` (L2117). There is no UPDATE or DELETE. Undo is only through "Restore from Backup" or "Purge Contracts" (README; L330, L477).
- **Keys.**
  - `Record Unique ID without time` = `"{Contract} {POB} {SKU}"` is the logical line key (L1817-1821).
  - `Processing Time Log` = `pd.Timestamp.now()`, evaluated once per run, so every row of the run shares it (L1996).
  - `Record Unique ID` = `str(PTL) + " " + key` (L1997-2000).
- **Latest version** is `MAX(Processing Time Log)` per key: wall-clock order, not business-date order (L1712-1720). A back-dated mod (S13) becomes the latest version even though its `Current Period` (2023-01-15) is earlier than its `Previous Period` (2023-04-30).
- **Business date.** `Current Period = mod_date`; `Previous Period` = the stored `Current Period`. JE and history reports filter on `Current Period` (L2574-2576), so any period can be hit, including closed ones.
- **Scope of new versions.**
  - Every line of each in-scope contract gets a version, including lines not in the upload. Their memos and dates are kept, `Current Delivery` and `Current Billing` become 0, and the catch-up and reclass are re-computed.
  - Contracts not in the upload get no version.
  - Duplicate upload rows produce two rows with the same PTL for one key. The latest query then returns both, and the fan-out persists (S03).
- **Previous <- Current roll**, each with `fillna(0)` (L1897-1920):

| Previous field | Source |
|---|---|
| Previous Remaining Qty / SSP / Allocation / Billing | Current Remaining Qty / SSP / Allocation / Billing |
| Previous Unit SSP / Previous Remaining Unit Rev Rec | Current Unit SSP / Current Remaining Unit Rev Rec |
| Previous Delivery / Rev Rec / Billing - Cumulative | Current Delivery / Rev Rec / Billing - Cumulative |
| Previous Cumulative Catchup - Cumulative - Disclosure Only | Current Cumulative Catchup - Cumulative - Disclosure Only |
| Previous SSP Delivered - Cumulative | Current SSP Delivered - Cumulative |
| Previous Contract Position - POB / Contract Level | Current Contract Position - POB / Contract Level |
| Previous Reclass to UAR | Current Reclass to UAR |
| Previous Period | Current Period |
| **Not rolled** | `Previous Pre-ASC606 Revenue (Net Design Only) - Cumulative` (defect) |

- **Recomputed current fields:**
  - Current Remaining Qty / SSP / Allocation / Billing
  - Current Unit SSP; Current Remaining Unit Rev Rec
  - Current Rev Rec (= catch-up); Current Rev Rec - Cumulative
  - Current Cumulative Catchup - Disclosure Only and its cumulative
  - Current Contract Position - POB / Contract Level; Current Reclass to UAR
- **Zeroed:** Current Delivery, Current Billing.
- **Carried unchanged:**
  - all `Original *` columns;
  - Current Delivery / Billing / SSP Delivered - Cumulative;
  - Current SSP Delivered and all Pre-ASC606 fields (stale);
  - SSP attributes, accounts, entity, stratification.
- **Gate before write.** Validation (L2082-2087) runs after the whole calculation and before the insert, so a failed mod writes nothing (S08, S08b, S09: 0 rows).
- **Lifecycle.**
  - Setup version: Previous = Current = Original.
  - Delivery versions: `Current Rev Rec = delivery * unit rev rec`.
  - Retro-mod version: `Current Rev Rec = catch-up`, deliveries 0, new unit rev rec.
  - Later deliveries use the new unit rev rec (S19).

---

## 5. Worked examples: hand-traced, then checked against the harness

### 5.1 Contract 2, UAT 05.15.2023: retrospective POB increase (full trace)

Note: despite its file name ("retrospective vc + POB increases"), the 05.15 file holds only one quantity increase and no VC row.

**Inputs.**

- `SKU_SSP` version 2023-01-01:
  - Hardware 1: list 100, discount 10%, range ±15%
  - Software 1: list 200, discount 20%, range ±15%
  - Consulting 1: list 300, discount 50%, range 0
  - Variable Consideration: list 0
- Setup 1.1.2023, Contract 2:
  - POB #1 Hardware 1: price 600, qty 8
  - POB #2 Software 1: price 400, qty 3
  - POB #3 Consulting 1: price 0, qty 1
  - VC #1: price -100, qty 1
- Upload: `Contract 2 | POB #1 | Hardware 1 | Mod Billing 400 | Mod Qty 2 | SSP Version 2023-01-01`, mod date `2023-05-15`.

**A. Inception (setup L682-717).**

| Line | SSP range | Price | Extended SSP |
|---|---|---|---|
| POB #1 | Mid 720, Low 612, High 828 | 600 < 612 | 612 |
| POB #2 | Mid 480, Low 408, High 552 | 400 < 408 | 408 |
| POB #3 | Mid = Low = High = 150 | 0 | 150 |
| VC #1 | 0 | -100 | 0 |

Transaction price 900; total SSP 1,170. Allocation: 470.769231 / 313.846154 / 115.384615 / 0.

**B. Activity before the mod.**

- 1.31: POB #1 delivered 1 unit at 58.846154 (= 470.769231 / 8); delivered SSP 76.5.
- 3.31: POB #3 delivered 0.4 at 115.384615 = 46.153846; delivered SSP 60.
- 4.30: POB #1 billed 20.

Latest version before the mod (4.30):

| Line | CRQ | CRS | CRA | CRB | RRC | Billing cum | SSP delivered cum |
|---|---|---|---|---|---|---|---|
| POB #1 | 7 | 535.5 | 411.923077 | 580 | 58.846154 | 20 | 76.5 |
| POB #2 | 3 | 408 | 313.846154 | 400 | 0 | 0 | 0 |
| POB #3 | 0.6 | 90 | 69.230769 | 0 | 46.153846 | 0 | 60 |
| VC #1 | 1 | 0 | 0 | -100 | 0 | 0 | 0 |

Contract position -85. `Current Reclass to UAR`: POB #1 47.637363, POB #3 37.362637.

**C. SSP of the increment (L1770-1815).** Mid = 2 × 100 × 0.9 = 180; Low = 153; High = 207. Billing 400 > 207, so **ModSSP = 207**.

**D. Remaining balances (L1923-1956).** POB #1: CRQ' = 9, CRS' = 742.5, CRB' = 980. The other lines are unchanged.

**E. Re-allocation (L1932-1950).**

```
TP_c  = (411.923077 + 313.846154 + 69.230769 + 0) + 400 + (58.846154 + 0 + 46.153846 + 0) = 795 + 400 + 105 = 1,300
SSP_c = (742.5 + 408 + 90 + 0) + (76.5 + 0 + 60 + 0) = 1,240.5 + 136.5 = 1,377      (= 612 + 207 + 408 + 150)
r_c   = 1,300 / 1,377 = 0.94408134
CRA_pre: POB #1 = r * 819 - 58.846154 = 773.202614 - 58.846154 = 714.356461
         POB #2 = r * 408 - 0          = 385.185185
         POB #3 = r * 150 - 46.153846  = 141.612200 - 46.153846 = 95.458354
         VC #1  = r * 0 - 0            = 0
```

**F. Catch-up (L2019-2053).**

| Line | ShouldBe = r × SSP delivered | Catch-up (`Current Rev Rec`) | CRA' | Unit rev rec |
|---|---|---|---|---|
| POB #1 | 0.94408134 × 76.5 = 72.222222 | 72.222222 - 58.846154 = **13.376068** | 714.356461 - 13.376068 = 700.980392 | 700.980392 / 9 = 77.886710 |
| POB #2 | 0 | 0 | 385.185185 | 128.395062 |
| POB #3 | 0.94408134 × 60 = 56.644880 | 56.644880 - 46.153846 = **10.491034** | 84.967320 | 84.967320 / 0.6 = 141.612200 |
| VC #1 | 0/0, filled with 0 | 0 | 0 | 0 |
| Total | 128.867102 | **23.867102** | 1,171.132898 | |

`Current Unit SSP` for POB #1 = 742.5 / 9 = 82.5. Invariant check: Σ(CRA' + RRC') = 1,171.132898 + 128.867102 = **1,300.000000**.

**G. Position and reclass (L2054-2071).**

- Position POB #1 = 20 - 72.222222 = -52.222222; POB #3 = -56.644880.
- Contract level = **-108.867102**. SSP delivered total = 136.5.
- Reclass POB #1 = 108.867102 / 136.5 × 76.5 = **61.013431**; POB #3 = × 60 = **47.853671**.

**H. Gross revenue JE for 2023-05-15..2023-05-15 (L2594-2651).** Positive = debit.

| Leg | Account | Amount |
|---|---|---|
| Catch-up Dr deferred / Cr revenue | 21002 / 5001, 5003 | +23.867102 / -13.376068, -10.491034 |
| Reverse previous reclass | 21002 / 15002 | +85.000000 / -85.000000 |
| Book current reclass | 21002 / 15002 | -108.867102 / +108.867102 |
| **Consolidated output (harness)** | 15002 Dr **23.87**; 5001 Cr **13.38**; 5003 Cr **10.49**; 21002 nets to 0 and is suppressed | sum 0.00 |

Every value above matches harness step 7 to better than 1e-9.

### 5.2 Contract 4, UAT 08.15.2023 row 3: retrospective reduction of a non-distinct consulting POB

Pre-state: the 07.15 prospective version, which added 2 consulting units at 300.

| Line | CRQ | CRS | CRA | RRC | SSP delivered cum | Billing cum | CRB |
|---|---|---|---|---|---|---|---|
| POB #1 Hardware | 6 | 459 | 362.382747 | 111.294028 | 153 | 150 | 450 |
| POB #2 Software | 3 | 408 | 322.117998 | 98.928025 | 136 | 200 | 200 |
| POB #3 Consulting | 3 | 450 | 355.277203 | 0 | 0 | 0 | 450 |
| VC #1 | 0.5 | 0 | 0 | 0 | 0 | -100 | -100 |

Upload: POB #3, Mod Billing -50, Mod Qty -0.5.

```
ModSSP  = -0.5 * 300 * 0.5 = -75  (range 0, so Low = High = Mid)      -> POB #3: CRQ' 2.5, CRS' 375, CRB' 400
TP_c    = 1,039.777948 - 50 + 210.222053 = 1,200.000000                (07.15 TP 1,250 less 50)
SSP_c   = (459 + 408 + 375 + 0) + (153 + 136) = 1,531;  r_c = 0.78380144
Catch-up: POB #1 = r*153 - 111.294028 = 119.921620 - 111.294028 = 8.627592
          POB #2 = r*136 -  98.928025 = 106.596995 -  98.928025 = 7.668971      total 16.296563
CRA':     POB #1 359.764860, POB #2 319.790986, POB #3 293.925539 (unit 117.570216), VC 0
Position: (150 - 119.921620) + (200 - 106.596995) + 0 + (-100) = +23.481385   -> no reclass
JE (harness): Dr 21002 16.30 | Cr 5001 8.63 | Cr 5002 7.67
```

Observation: the customer cut consulting scope at SSP, yet revenue on **already-delivered hardware and software rose** by 16.30. Their revenue-to-SSP ratio moves from the inception ratio 0.727412 (111.294028 / 153) to 0.783801. The cause: SSP-priced increments and decrements dilute the contract discount, and the retro function pushes the diluted discount back onto satisfied lines (see section 6).

### 5.3 Contract 3, UAT 08.15.2023 row 2: golden values (harness)

Upload: POB #1 Hardware 1, -4 units at -200.

```
ModSSP = -306 (Mid -360, Low -306, High -414; -200 > -306)
TP_c   = 1,800 - 200 = 1,600;  SSP_c = (401+184+75+1000) + (0+184+75+0) = 1,919;  r_c = 0.83376759
```

| Line | CRQ | CRS | Unit SSP | CRA | Current Rev Rec | RRC | CRB |
|---|---|---|---|---|---|---|---|
| POB #1 Hardware | 3 | 401 | 133.666667 | 334.340803 | 0 | 0 | 800 |
| POB #2 Software | 1 | 184 | 184 | 153.413236 | 34.880035 | 153.413236 | 200 |
| POB #3 Consulting | 0.5 | 75 | 150 | 62.532569 | 7.223824 | 62.532569 | 200 |
| POB #4 Material right | 1000 | 1000 | 1 | 833.767587 | 0 | 0 | 0 |

Contract position 184.054195, reclass 0. JE (harness): Dr 21001 42.10 | Cr 5002 34.88 | Cr 5003 7.22.

The removed units took out SSP at the clamped mod price (76.5 per unit), not at the line's carrying unit SSP (707 / 7 = 101). As a result the remaining unit SSP rose to 133.67 and the delivered lines' ratio rose from 0.644202 / 0.737450 to 0.833768.

---

## 6. Accounting assessment

**Conclusion.** The function is a consistent "full relative-SSP re-allocation with cumulative catch-up" engine, and the arithmetic ties out exactly (Σ allocation = TP). It gives the ASC 606 answer in two narrow cases:

- a modification of a single, partially satisfied, non-distinct performance obligation (606-10-25-13(b));
- a pure change in transaction price with no scope change (qty 0), allocated on the inception basis (606-10-32-43 to 32-44).

For every other modification it over-applies catch-up. It lets SSPs drift after inception, removes SSP at the wrong rate on reductions, and has data-integrity gaps that can misstate revenue. Items marked *inference* are my judgement, not codification text.

### 6.1 Where it is correct or defensible

| # | Behaviour | ASC 606 basis | Assessment |
|---|---|---|---|
| C1 | Transaction price allocated by relative SSP; any discount spread proportionally over all lines (L1932-1950) | 606-10-32-28/32-29 relative SSP basis ([external website reference removed]; [external website reference removed]); 606-10-32-36 proportional discount ([external website reference removed]) | Correct default. |
| C2 | Catch-up = total allocation × progress to date, less revenue to date, booked on the mod date (L2019-2046) | 606-10-25-13(b): the effect on transaction price and measure of progress is recognised "on a cumulative catch-up basis" ([external website reference removed]) | Correct mechanics **for the partially satisfied non-distinct POB**. |
| C3 | Price-only change (qty 0) adds consideration but no SSP; the delivered portion is trued up immediately (S05: -11.06) | 606-10-32-43 to 32-44: subsequent transaction price changes are allocated "on the same basis as at contract inception", with no reallocation for SSP changes; amounts for satisfied POBs go to revenue in the period of change ([external website reference removed]) | Correct when no prior prospective mod or quantity mod has altered SSPs. |
| C4 | VC line has zero SSP; negative consideration is spread over the real lines | Default allocation unless the 606-10-32-40 criteria for specific allocation are met ([external website reference removed]) | Correct default; specific allocation lives on the separate POB-specific VC button. |
| C5 | Contract asset or liability netted at contract level; asset reclassed only when the net is negative | 606-10-45-1; assets and liabilities from the same contract are presented net ([external website reference removed]) | Correct netting unit. |
| C6 | Cannot remove more quantity or billing than remains undelivered or unbilled (VR-11) | *inference*: a modification cannot un-transfer delivered goods | Sound control. |

### 6.2 Simplified (acceptable as policy but not general)

| # | Simplification | Evidence | Commentary |
|---|---|---|---|
| S1 | The user picks the model by button; there is no 25-12 / 25-13 decision logic | L133-141; code never reads `Distinct or Nondistinct` in retro | The codification decides by distinctness and by whether added goods are priced at SSP ([external website reference removed]). |
| S2 | SSP of added scope = mod price clamped to the nearest range bound | L1797-1815 | A bounded SSP range is an accepted estimation practice ([external website reference removed]). Nearest-bound vs midpoint is a policy choice; *inference*: it should be configurable and documented. |
| S3 | Measure of progress = SSP delivered (units × unit SSP) | L2019-2024 | An output method only; no cost-to-cost, time-elapsed or milestone measures. |
| S4 | No residual approach; no specific discount allocation | L1932-1950 | Residual only when SSP is highly variable or uncertain (606-10-32-34, [external website reference removed]). Specific discount allocation under 606-10-32-37 ([external website reference removed]). |
| S5 | VC is an input amount; no estimation or constraint logic | L1682 (upload value used as-is) | Estimates and constraint live outside the system. |
| S6 | "Unbilled A/R" is one account for all debit contract positions | L2063-2071, L2616-2636 | Contract assets (conditional right) and receivables (unconditional right) are presented separately (606-10-45-3/45-4, [external website reference removed]). |
| S7 | No rounding or currency precision; no residual true-up | section 3.9 | Adequate for analysis; a ledger needs minor-unit precision. |

### 6.3 Wrong, incomplete, or mishandled edge cases

| # | Defect | Evidence | ASC 606 / control impact |
|---|---|---|---|
| W1 | **Catch-up applied to every POB, including satisfied distinct POBs, for scope changes** | 08.15: consulting reduction lifts delivered hardware and software revenue by 16.30; hardware reduction lifts delivered software and consulting by 42.10 | When remaining goods are distinct, a modification is prospective (termination plus new contract, 606-10-25-13(a)). Added distinct goods at SSP are a separate contract (606-10-25-12) ([external website reference removed]). Revenue on satisfied distinct POBs should not move. |
| W2 | SSPs drift after inception: added units bring mod-date SSP, and the whole contract (satisfied lines included) is re-weighted | L1743-1746, L1932-1950 | For changes in transaction price, SSP is not updated after inception (606-10-32-43, [external website reference removed]). |
| W3 | Reductions remove SSP at the clamped mod price, not at the line's carrying unit SSP | 08.15 Contract 3: -306 removed vs 4 × 101 = 404 carried; remaining unit SSP becomes 133.67 | *inference*: terminated units should remove the SSP attributable to them; otherwise remaining SSP and the contract ratio are distorted. |
| W4 | A retro mod after any prospective mod reverses the prospective result, even when the mod itself is a no-op | S07b: qty 0 / billing 0 books +35.69 | Results depend on event order; prospective and retro events do not compose. |
| W5 | New-POB-only upload is not re-allocated; existing lines are dropped from scope | S04: 1 row, allocation 170 = billing | Misallocation; the contract's TP is split across two unrelated groups. |
| W6 | Duplicate upload rows or duplicate SSP keys inflate the transaction price | S03: TP 1,770.77 vs 1,300; S18: TP 2,170.77 | Revenue overstated; no preventive control. |
| W7 | `Current Pre-ASC606 Revenue (Net Design Only)` carried into mod versions, and its cumulative not rolled | S06: adjustment JE double-posts 66 and 88 | Adjustment JEs misstated whenever the date range includes both the delivery and the mod version. |
| W8 | Back-dated mods accepted with no period lock; `Previous Period` > `Current Period` | S13 | Posts into closed periods; breaks cut-off. |
| W9 | Qty reduced to 0 while SSP and allocation remain: stranded allocation, `inf` unit SSP and unit rev rec | S15: CRA 172.57 with CRQ 0 | Allocated revenue can never be recognised; corrupt numeric state persisted. |
| W10 | Upload changes to selling entity or accounts on existing POBs silently ignored | S05 (29999 uploaded, 21002 kept) | Mis-posting risk with no user feedback. |
| W11 | Contract-level netting and reclass run across lines with different selling entities and deferred-revenue accounts | L2060-2068 | *inference*: legal-entity books may need per-entity positions. |
| W12 | No distinction between a change in transaction price after a modification and a modification; no 32-45 routing | single button | 606-10-32-45 routes a VC change to pre-modification POBs in 25-13(a) cases, otherwise to modified-contract POBs ([external website reference removed]). |
| W13 | Control gaps: header-only file shows "Mod Success" (S01); any `TypeError` swallowed silently (L2124); unknown contract silently creates a contract (S14); no maker/checker, rationale or source-file trail | S01, S14, L2124 | Weak ITGC / application controls for a revenue subledger. |
| W14 | Reclass is NaN when the contract nets negative and no SSP has been delivered; new-POB rows get NaN reclass and NULL `Original *` | S04b | Incomplete data; JE grouping skips NaN silently. |
| W15 | Contract with zero total SSP loses its whole transaction price (NaN filled with 0) | L1949 | Transaction price silently dropped. |

---

## 7. Port notes for eRev Cloud

### 7.1 Behaviours to keep (parity)

| ID | Behaviour | Source |
|---|---|---|
| PAR-01 | Relative-SSP allocation over delivered plus undelivered SSP: `r_c = TP_c / SSP_c`, total allocation_i = `r_c × (CRS_i' + PSSPD_i)` (for events classified as catch-up) | L1932-1950 |
| PAR-02 | Catch-up = `r_c × SSPDelivered_i - RRC_i`, booked as period revenue; remaining allocation = `r_c × CRS_i'` | L2019-2046 |
| PAR-03 | Increment SSP = clamp(mod price) into `[Mid×(1-range), Mid×(1+range)]`, with a sign-aware branch for negative qty; qty 0 gives SSP 0 | L1770-1815 |
| PAR-04 | Remaining qty and billing += mod values; remaining SSP floored at 0 | L1923-1929, L1952-1956 |
| PAR-05 | VC stratification: zero SSP, excluded from the negative-billing gate and forced to zero reclass | L1993, L2071, L2083 |
| PAR-06 | Contract position = billing cum - revenue cum; net at contract level; contract asset allocated to lines by delivered-SSP share when the net is negative | L2054-2071 |
| PAR-07 | Every line of an in-scope contract gets a new version; other contracts untouched | L1839-1846, L2117 |
| PAR-08 | Previous <- Current roll of the 14 fields; `Current Period` = event date; `Current Delivery` and `Current Billing` = 0 on mod versions | L1880-1920, L1965-1968 |
| PAR-09 | Mod rows overwrite memos and POB start/end dates; the increment is priced with the upload's SSP version while the line keeps its stored attributes | L1855-1873, L1743-1746 |
| PAR-10 | Gates with no partial write: title set, numeric non-blank billing and qty, SSP key match, no negative remaining qty or non-VC billing | VR-03..VR-11 |
| PAR-11 | Full-precision calculation, rounded only in JE output (`round(4)`, filter `round(2) != 0`, `round(2)`); invariant `Σ(CRA + RRC) = TP` | L2598-2651 |
| PAR-12 | Catch-up posted as `Current Rev Rec` and tracked per line in the disclosure fields (period and cumulative) | L2026-2036 |
| PAR-13 | Later deliveries recognise at the post-mod unit rev rec | L1028-1029; S19 |

### 7.2 Behaviours to fix

| ID | Fix | Addresses |
|---|---|---|
| FIX-01 | Classify modifications: 25-12 separate contract; 25-13(a) prospective; 25-13(b) catch-up **only** on the partially satisfied non-distinct POB; 25-13(c) mixed. User override needs a rationale and approval. | W1, S1 |
| FIX-02 | Separate event type "change in transaction price": inception SSP basis, satisfied portion to revenue, optional 32-40 specific allocation, 32-45 routing | W2, W12 |
| FIX-03 | Freeze inception SSP per line; added units carry their own SSP layer; reductions remove SSP at the carrying unit SSP (or by layer) | W2, W3 |
| FIX-04 | Upload integrity: reject header-only files, duplicate keys, non-unique SSP keys, unknown contract or POB unless the row is an explicit "add POB"; always include all lines of the contract in scope | W5, W6, W13, W14 |
| FIX-05 | Reset all period fields on every event (`Current SSP Delivered`, Pre-ASC606 period amount); roll the Pre-ASC606 cumulative | W7 |
| FIX-06 | Effective date vs posting date; block back-dating into locked periods; order versions by sequence number, not wall clock | W8 |
| FIX-07 | Block qty-to-zero with remaining allocation, or run an explicit termination; database constraints against `inf`/NaN | W9, W14, W15 |
| FIX-08 | Explicit events for changing entity, accounts or SSP version; show a diff to the user | W10 |
| FIX-09 | Minor-unit Decimal arithmetic with a deterministic residual line; separate contract-asset and receivable accounts; per-entity netting option | S6, S7, W11 |
| FIX-10 | No blanket `except TypeError`; transactional write; idempotency key and source-file hash; audit log of who, when and which rule applied | W13 |
| FIX-11 | Configurable SSP-range policy (stated price in range, nearest bound or midpoint) and residual approach where criteria are met | S2, S4 |

### 7.3 Test cases to carry forward

Expected values are from the harness replay (pandas 2.2.3 and 3.0.5 identical). Tolerance 1e-6 unless shown to 2 dp.

| TC | Setup | Action | Expected (legacy parity unless marked FIX) |
|---|---|---|---|
| TC-RM-01 | UAT SSP + setup 1.1 + deliveries 1.31, 2.28, 3.31, 4.30 | Retro 05.15: Contract 2 POB #1 +2 / +400 | ModSSP 207; TP 1,300; Current Rev Rec POB #1 13.376068, POB #3 10.491034 (Σ 23.867102); CRA 700.980392 / 385.185185 / 84.967320 / 0; unit rev rec 77.886710 / 128.395062 / 141.612200; POB #1 unit SSP 82.5, CRB 980; contract position -108.867102; reclass 61.013431 / 47.853671; JE Dr 15002 23.87, Cr 5001 13.38, Cr 5003 10.49 |
| TC-RM-02 | Full UAT through 07.15 prospective | Retro 08.15 row 2: Contract 3 POB #1 -4 / -200 | ModSSP -306; TP 1,600; POB #1 CRQ 3, CRS 401, unit SSP 133.666667; catch-up POB #2 34.880035, POB #3 7.223824; CRA 334.340803 / 153.413236 / 62.532569 / 833.767587; position 184.054195; JE Dr 21001 42.10, Cr 5002 34.88, Cr 5003 7.22. **FIX-01 expected: no catch-up on distinct delivered software POB #2.** |
| TC-RM-03 | as TC-RM-02 | Retro 08.15 row 3: Contract 4 POB #3 -0.5 / -50 | ModSSP -75; TP 1,200; catch-up POB #1 8.627592, POB #2 7.668971; CRA 359.764860 / 319.790986 / 293.925539 / 0; POB #3 unit rev rec 117.570216; position 23.481385; JE Dr 21002 16.30, Cr 5001 8.63, Cr 5002 7.67. **FIX-01: catch-up confined to non-distinct POB #3 (0 delivered, so 0).** |
| TC-RM-04 | through 4.30 | Contract 4 VC #1 billing -50, qty 0, account 29999 | TP 900; catch-up POB #1 -5.857580, POB #2 -5.206738; VC CRB -150; account stays 21002 (legacy) / explicit change or rejection (FIX-08) |
| TC-RM-05 | through 4.30 | Contract 2 POB #2 qty 0 / billing 0 | Catch-up 0; TP 900; 4 rows appended |
| TC-RM-06 | through 07.15 | Contract 3 POB #2 qty 0 / billing 0 | Legacy +35.686144 (POB #2 30.320731, POB #3 5.365413). **FIX: 0.** |
| TC-RM-07 | through 4.30 | Contract 2 POB #2 -5 / -100; and POB #2 -1 / -500 | "Mod Failed" message; 0 rows |
| TC-RM-08 | through 4.30 | SKU "Hardware X"; missing "Memo 3"; blank Mod Qty; date "2023-5-15" | VR-09 / VR-05 / VR-08 / VR-03 messages; 0 rows |
| TC-RM-09 | through 4.30 | Header-only file | Legacy "Mod Success", 0 rows. **FIX: reject.** |
| TC-RM-10 | through 4.30 | Duplicate rows Contract 2 POB #1 +1 / +200 twice | Legacy 5 rows, TP 1,770.769231. **FIX: reject (or aggregate, giving TC-RM-01 values).** |
| TC-RM-11 | through 4.30 | New POB only: Contract 2 POB #4 Software 1 +1 / +170 | Legacy 1 row, CRA 170. **FIX: equals S04b: TP 1,070; catch-up POB #1 2.239667, POB #3 1.756602; new POB CRA 135.746269.** |
| TC-RM-12 | through 1.31 | Retro 2023-02-01 Contract 1 POB #2 qty 0 / billing 0, then adjustment JE 2023-01-01..2023-02-28 | Legacy mod version Pre-ASC606 = 66 / 88; JE 5002 +13.47, 5003 +127.68, 21001 -12.31. **FIX: JE 5002 -52.53, 5003 +39.68, 21001 +141.69.** |
| TC-RM-13 | through 4.30 | Mod date 2023-01-15 | Legacy accepted (`Previous Period` 2023-04-30). **FIX: blocked or back-dating workflow.** |
| TC-RM-14 | through 4.30 | Unknown "Contract 9" POB #1 +2 / +180 | Legacy creates a contract, CRA 180. **FIX: reject.** |
| TC-RM-15 | through 07.15 | Contract 3 POB #1 -7 / -100 | Legacy CRQ 0, CRS 171.5, unit SSP `inf`, CRA 172.565848, TP 1,700. **FIX: blocked / termination.** |
| TC-RM-16 | through 4.30 plus a duplicate SSP key row | UAT 05.15 file | Legacy 5 rows, TP 2,170.769231. **FIX: unique SSP key constraint.** |
| TC-RM-17 | after TC-RM-01 and 05.31 VC | Deliver 1 unit Contract 2 POB #1 on 2023-05-31 | Current Rev Rec 77.886710; SSP delivered 82.5 |
| TC-RM-18 | every retro run | invariants | `Σ(CRA + RRC) = TP_c`; `Σ reclass = -position` when the position is negative; no NaN or `inf` persisted (FIX) |

### 7.4 Sources (external)

- Deloitte DART Roadmap 9.2, Types of Contract Modifications (606-10-25-12, 25-13): [external website reference removed]
- Deloitte DART Roadmap 9.1, Defining a Contract Modification (606-10-25-10): [external website reference removed]
- Deloitte DART Roadmap 9.4, Change in Transaction Price After a Contract Modification (606-10-32-45): [external website reference removed]
- Deloitte DART Roadmap 7.6, Changes in the Transaction Price (606-10-32-42 to 32-44): [external website reference removed]
- Deloitte DART Roadmap 7.4, Allocation of a Discount (606-10-32-36 to 32-38): [external website reference removed]
- Deloitte DART Roadmap 7.2, Stand-Alone Selling Price (606-10-32-29, 32-30): [external website reference removed]
- Deloitte DART Roadmap 14.1, Presentation Overview (606-10-45-1; net within a contract): [external website reference removed]
- PwC Viewpoint 5.5, Impact of variable consideration (606-10-32-40): [external website reference removed]
- BillingPlatform, SSP allocation (606-10-32-28, 32-34 residual, SSP ranges): [external website reference removed]
- BillingPlatform, Contract assets vs receivables vs deferred revenue (606-10-45-3/45-4): [external website reference removed]

### 7.5 Open questions for Ray

1. Should eRev Cloud keep a user-elected "full retrospective re-allocation" policy for legacy parity? Or should catch-up be restricted to 25-13(b) lines by default, with full re-allocation as a documented override?
2. SSP of added units: inception SSP version, or mod-date version as the legacy does? Should reductions remove SSP at the carrying unit SSP (FIX-03)?
3. The 05.15 UAT file is named "retrospective vc + POB increases" but contains only a quantity increase. Was a VC row intended? No UAT exercises a VC re-estimate through this button.
4. Is "Unbilled A/R" meant as a contract asset or an unbilled receivable? Are separate accounts wanted? Should netting be per selling entity?
5. Required ledger precision (currency minor units) and residual-assignment rule?
6. Back-dated modifications: allowed with period-lock checks, or always posted in the open period with an effective-date memo?
7. Should an upload be able to change entity, accounts or SSP version on existing lines, and if so through which event?
