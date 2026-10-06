# 06 — Journal Entries and Reports (legacy eRev)

| Item | Value |
|---|---|
| Legacy source (read-only) | `~/dev/erev-legacy/eRev.py`, lines 2540–3218 in full; shared state from lines 17–292 (main window, license gate), 293–533 (DB utilities), 621–1168 (contract setup, delivery/billing), 1170–2538 (mods) |
| Other sources | `README.md` (lines 81–87 describe the three reporting buttons); `ops/Blank Templates/*.xlsx`; `ops/Example UATs/**/*.xlsx`; shipped `ops/libnew/libwarm/db/ASC606.db` (copied to `.scratch/06-journal-entries-and-reports/ASC606.db`) |
| Method | Line-by-line reading, plus a headless replay harness that imports `eRev.py` read-only with scripted Qt dialogs (`.scratch/06-journal-entries-and-reports/harness.py`, outputs in `runs/<scenario>/`) |
| Citation convention | `[L1234]` = `eRev.py` line. **Fact** = observed in code or harness output. **Inference** = analyst judgement. |

---

## 1. Purpose, trigger, inputs, outputs

### 1.1 Purpose

This module covers the "Journals and Reporting" part of legacy eRev (README lines 81–87). It has three kinds of output, all read-only against `Contract_Live`:

1. **Revenue journal entries** for a date range, in two modes:
   - **Gross Revenue JEs** (`journal_entries`, [L2540–2668]). These recognise revenue out of deferred revenue and reclass any contract-level debit position to unbilled A/R (contract asset).
   - **Revenue Adjustment JEs** (`journal_entries_delta`, [L2862–3011]). These produce the same lines plus a reversal of the revenue the ERP already booked before ASC 606 ("net design"), so that only the ASC 606 delta posts to revenue.
2. **Contract history**: every version record whose `Current Period` falls in a date range, either all contracts ([L2670–2723]) or one contract ([L2725–2782]).
3. **Latest contract status**: the newest version of each `Contract + POB + SKU` key by `Processing Time Log`, either all contracts ([L2784–2818]) or one contract ([L2820–2860]).

It also contains two application-level utilities: `ShutdownNotifier`, the end-of-life kill switch ([L3077–3102], armed at [L3214–3216]), and `LicenseKeyDialog`, the premium-key capture ([L3175–3205]).

### 1.2 Triggers (buttons and chooser dialogs)

| Main-window button (row "Journals and Reporting", [L148–172]) | Handler | Chooser dialog | Choice → method |
|---|---|---|---|
| `button9` "Revenue Journal Entries" [L159] | `show_custom_dialog` [L241, L3013–3015] | `CustomDialog` "Choose A Revenue Journal Entry Option", 300×80 [L3106–3125] | "Gross Revenue JEs" → `journal_entries` [L3117, L3124]; "Revenue Adjustment JEs" → `journal_entries_delta` [L3118, L3125] |
| `button10` "Contract History" [L164] | `show_contract_dialog` [L242, L3017–3019] | `ContractDialog` "Choose A Contract History Option" [L3129–3148] | "Check All Contract History" → `contract_history` [L3147]; "Check Specific Contract" → `specific_contract_history` [L3148] |
| `button11` "Latest Contract Status" [L169] | `show_latest_contract_dialog` [L243, L3021–3023] | `LatestContractDialog` "Choose A Latest Contract Option" [L3152–3171] | "Check All Latest Contract" → `latest_contracts` [L3170]; "Check Specific Latest Contract" → `specific_latest_contracts` [L3171] |

**Fact.** None of these functions is license-gated. When no premium key is found, only the premium database buttons (`button6`, `button7`, `button8`, `button8_1`, `button8_2`) are disabled [L287–291]. The chooser dialogs are modal (`exec()`). Every method closes its chooser with `self.sender().parent().close()` once the output is ready ([L2659, L2714, L2773, L2809, L2851, L3002]). If the user cancels a date prompt or enters an invalid date, the chooser stays open.

### 1.3 Inputs

These functions read **no Excel template**. Their inputs are interactive prompts plus the `Contract_Live` table that the upstream template loaders built.

#### 1.3.1 Interactive prompts

| Method | Prompt 1 (title / label) | Prompt 2 | Prompt 3 | Parse rule |
|---|---|---|---|---|
| `journal_entries` [L2542–2553] | "Start Date Input" / "Enter the start date of the date range to retrieve the revenue journal entries (YYYY-MM-DD):" | "Date Input" / "…end date … revenue journal entries (YYYY-MM-DD):" | — | `QDate.fromString(text, "yyyy-MM-dd")`, then `isValid()` |
| `journal_entries_delta` [L2864–2875] | same as above | same | — | same |
| `contract_history` [L2672–2683] | "Start Date Input" / "…start date … revenue contract history (YYYY-MM-DD):" | "Date Input" / "…end date … revenue contract history (YYYY-MM-DD):" | — | same |
| `specific_contract_history` [L2727–2744] | same as `contract_history` | same | "Enter contract unique name" / "Please enter the specific contract unique name to retrieve the revenue history:" | name is **not** validated and `ok` is **not** checked [L2743] |
| `latest_contracts` [L2784] | — | — | — | none |
| `specific_latest_contracts` [L2823–2824] | "Enter contract unique name" / "Please enter the specific contract unique name to retrieve the latest contract version:" | — | — | `ok` not checked |
| `LicenseKeyDialog` [L3183–3193] | label "Enter your Chipmunk Premium License Key or enter anything to use the free version:" (password echo) | — | — | must be non-empty [L3199] |

Both dates are converted to midnight `datetime` values (`datetime.combine(date, datetime.min.time())`, e.g. [L2567–2568]). The filter is `start <= Current Period <= end` [L2574–2576]. Every legacy `Current Period` is stored at midnight ([L1025–1026, L1246, L1730, L2208]), so both ends of the range are inclusive.

#### 1.3.2 `Contract_Live` columns consumed

Declared SQLite types come from the shipped schema. **Fact:** `Current Rev Rec` is declared `INTEGER` but is stored as `real` whenever it has a fractional part (SQLite type affinity; confirmed with `typeof()` on the shipped DB). All amounts are therefore effectively floats.

| Column | Declared type | Used by | Upstream origin |
|---|---|---|---|
| `Contract Unique Name` | TEXT | JE grouping key for deferred revenue and UAR lines; history/latest filters | Contract Setup template col A [L630]; Mod template col A for new POBs [L1366–1367] |
| `Record Unique ID without time` | TEXT | JE grouping key for revenue lines; latest-version key | `Contract Unique Name + " " + POB Unique ID + " " + SKU Name` [L758–760, L1113–1117, L1333–1339] |
| `Current Period` | TIMESTAMP (text `YYYY-MM-DD HH:MM:SS`) | date-range filter | Setup template col M [L635]; delivery/mod prompt date [L1025, L1398, L1881, L2316] |
| `Deferred Revenue Account` | INTEGER | JE account | Setup template col K; Mod template col J for new POBs [L1391–1393] |
| `Unbilled A/R Account` | INTEGER | JE account | Setup template col L; Mod template col K for new POBs [L1394–1396] |
| `Revenue Account` | INTEGER | JE account | `SKU_SSP` col I via the setup merge on `SKU Name + ASC 606 Stratification + SSP Version` [L677–679] |
| `Current Rev Rec` | INTEGER (stored REAL) | JE amount | Delivery: `Current Delivery × Current Remaining Unit Rev Rec` [L1028–1029]; mods: cumulative catch-up [L1545–1546, L2035–2036, L2443–2444] |
| `Previous Reclass to UAR` | INTEGER (stored REAL) | JE reversal amount | Roll-forward of the prior version's `Current Reclass to UAR` [L1008, L1437, L1920, L2355] |
| `Current Reclass to UAR` | INTEGER (stored REAL) | JE reclass amount | Engine [L1081–1089, L1492–1500, L1589–1594, L1985–1993, L2063–2071, L2403–2411, L2470–2478] |
| `Current Pre-ASC606 Revenue (Net Design Only)` | INTEGER | Delta JE amount | Progress Tracking template col F [L847, L1020–1021] |
| `Processing Time Log` | TIMESTAMP (text) | latest-version selection | `pd.Timestamp.now()` at each load [L757, L1112, L1503, L1996, L2414] |
| All 71 columns | — | history and latest exports | see §4 |

#### 1.3.3 Template sheets feeding these outputs (upstream contract)

All four loaders require the header set to match **exactly**. A missing or extra header fails with "File Upload Error" ([L642–648, L856–862, L1200–1206, L552–558]). Only the first sheet is read (`pd.read_excel(file_path)` with no `sheet_name`).

| Template (sheet) | Column | Type | Required | Validated | Feeds JE/report via |
|---|---|---|---|---|---|
| SKU SSP (`SKU Setup`) | A `SKU Unique ID` | int | header required | no | carried to history |
| | B `SKU Name` | text | yes (join key) | no | revenue-line key |
| | C `Distinct or Nondistinct` | text `Distinct`/`Nondistinct` | yes | no | catch-up path in mods |
| | D `SKU Unit List Price` | number | yes | `to_numeric` [L566] | SSP |
| | E `ASC 606 Stratification` | text; `VC` is special | yes (join key) | no | VC excluded from reclass |
| | F `Midpoint Discount Percentage` | decimal | yes | `to_numeric` | SSP |
| | G `SSP Range Method (+-)` | decimal | yes | `to_numeric` | SSP range |
| | H `SSP Version` | date/text (cast to str [L574]) | yes (join key) | no | SSP match |
| | I `Revenue Account` | int | yes | **no** | JE revenue account |
| Contract Setup (`Sheet1`) | A–C `Contract Unique Name`, `POB Unique ID`, `SKU Name` | text | yes | no | keys |
| | D–E `POB Start Date`, `POB End Date` | date | header only | no | history only |
| | F `ASC 606 Stratification` | text | yes | no | join key, VC flag |
| | G `Original POB Total Selling Price` | number (may be negative for VC, 0 for free POBs) | yes | `to_numeric` [L656] | allocation |
| | H `Original POB Total Qty` | number | yes | `to_numeric` | allocation |
| | I `Selling Entity` | text | header only | no | **not used in JEs** |
| | J `SSP Version` | date/text | yes | no | SSP join |
| | K `Deferred Revenue Account` | int | header only | **no** | JE account |
| | L `Unbilled A/R Account` | int | header only | **no** | JE account |
| | M `Current Period` | date | header only | **no** | setup version date |
| | N–P `Memo 1..3` | text | header only | no | history only |
| Contract Progress Tracking (`Progress Tracking`) | A–C keys | text | yes | no | match to live POB |
| | D `Current Delivery` | number (negative = return) | yes | `to_numeric` and no NaN [L870–874] | `Current Rev Rec` |
| | E `Current Billing` | number (negative = credit) | yes | same | position and reclass |
| | F `Current Pre-ASC606 Revenue (Net Design Only)` | number | yes | same | delta JE |
| | G–I `Memo 1..3` | text | header required; **blank memos silently drop the row** (see §3.10, VR-reports-24) | no | history |
| Contract Modification (`Sheet1`) | A–O as per [L1189–1193] | — | yes | `Mod Billing`, `Mod Qty` numeric, no NaN | catch-up `Current Rev Rec`, reclass |

### 1.4 Outputs

**Database writes: none.** Every method opens `ops/libnew/libwarm/db/ASC606.db`, runs a `SELECT`, and closes the connection ([L2558–2564, L2688–2694, L2746–2753, L2786–2798, L2826–2840, L2880–2886]). `LicenseKeyDialog` is the only write in scope, and it writes `.env` rather than the database ([L3200–3201]).

**Excel files.** Each output is written to the process working directory (the app folder), silently overwrites an existing file, and is saved **before** the popup opens.

| Method | File name | Index column | Columns |
|---|---|---|---|
| `journal_entries` | `Revenue JE Summary between {start} and {end}.xlsx` [L2654–2656] | no | `Record Unique ID without time`, `Account`, `Amount` |
| `journal_entries_delta` | `Revenue Adj. Summary between {start} and {end}.xlsx` [L2997–2999] | no | same 3 columns |
| `contract_history` | `Contract History between {start} and {end}.xlsx` [L2709–2711] | no | all 71 `Contract_Live` columns |
| `specific_contract_history` | `{contract_name} History between {start} and {end}.xlsx` [L2768–2770] | no | 71 columns |
| `latest_contracts` | `Latest Contract Details.xlsx` [L2806] | **yes** (pandas default; adds a leading unnamed index column) | index + 71 |
| `specific_latest_contracts` | `{contract_name} Latest Contract Details.xlsx` [L2848] | **yes** | index + 71 |

`{start}` and `{end}` are Python `date` strings (`YYYY-MM-DD`).

**Popups.**
- `DataFramePopup` ([L3026–3045]) is a `QMainWindow` titled "Summary", 800×600, containing a read-only `QTableView` with sorting disabled. Its constructor raises `QMessageBox.information(self, "File Saved", "Details are exported to an Excel within the folder :)")` [L3044–3045]. The window is stored in `self.journal_window`, so opening another popup replaces the previous reference.
- Cell rendering (`DataFrameTableModel`, [L3048–3074]): every cell is `str(value)`, so NaN shows as `nan` and timestamps as `2023-01-31 00:00:00`. The first **data row** is painted grey (240,240,240) although the comment says "column title" [L3063–3065]. Vertical headers show the DataFrame index, which is the original DB row position, not a 1..n sequence [L3071–3072].
- Errors: `QMessageBox.critical(self, "Error Notification", str(e))` (e.g. [L2663–2668]).

---

## 2. Validation rules

IDs VR-reports-01 to 17 are in scope (lines 2540–3218 plus the startup license gate these classes serve). IDs 18–20 are upstream behaviours that silently change what the JE module sees. They are listed because they surface as JE defects; the upstream docs own them. "Harness" means observed in `.scratch/06-journal-entries-and-reports/harness_out.txt`.

| ID | Function / lines | Exact condition | Outcome and exact message | Evidence |
|---|---|---|---|---|
| VR-reports-01 | `journal_entries` [L2545–2548]; `contract_history` [L2675–2678]; `specific_contract_history` [L2730–2733]; `journal_entries_delta` [L2867–2870] | `not QDate.fromString(start_text, "yyyy-MM-dd").isValid()` | `QMessageBox.warning` title "Invalid Date", text "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'."; the method returns and the chooser stays open | Harness: rejects `2023-1-31`, `2023/01/31`, `2023-02-30`, `2023-02-29`, `23-01-31`, and leading or trailing spaces; accepts `2024-02-29` |
| VR-reports-02 | same four methods [L2553–2556, L2683–2686, L2738–2741, L2875–2878] | `not QDate.fromString(end_text, "yyyy-MM-dd").isValid()` | same warning | Harness: blank end date rejected |
| VR-reports-03 | same four methods [L2544, L2552, L2674, L2682, L2729, L2737, L2866, L2874] | user presses Cancel on a date prompt (`ok == False`) | silent no-op, no message | Harness |
| VR-reports-04 | JE and history methods [L2574–2576, L2704–2706, L2763–2765, L2896–2898] | **no check** that `start <= end` | empty result; an Excel file with headers only is still saved and the popup with "File Saved" still opens | Harness: `2023-12-31..2023-01-01` gives 0 lines |
| VR-reports-05 | `specific_contract_history` [L2743–2750]; `specific_latest_contracts` [L2823–2836] | **no check** of `ok` on the contract-name prompt | a cancelled prompt proceeds with `''`: 0 rows, file `" History between 2023-01-01 and 2023-12-31.xlsx"` saved (leading space) | Harness |
| VR-reports-06 | same [L2747–2750, L2827–2836] | contract name interpolated into SQL as `"{contract_name}"` (f-string) | name containing `"` → `critical` "Error Notification" / `Execution failed on sql … near "1": syntax error`. `x" OR 1=1 OR "x` → **all 24 rows returned** (SQL injection). A name equal to a column identifier (e.g. `SKU Name`) is resolved as a column reference → 0 rows | Harness |
| VR-reports-07 | same | contract name matches no record | 0 rows, no warning; empty Excel saved; popup opens | Inference from code, consistent with VR-05 |
| VR-reports-08 | `journal_entries` [L2643–2644]; `journal_entries_delta` [L2986–2987] | component JE line kept only if `Amount.round(2) != 0` (NaN passes because `NaN != 0`) | sub-cent component lines are dropped **before** consolidation, so several sub-cent components that sum to ≥ 0.005 disappear | Harness H: 3 × 0.004 revenue gives an empty JE |
| VR-reports-09 | [L2650–2651]; [L2993–2994] | consolidated line kept only if `round(sum, 2) != 0`; survivors rounded to 2 dp | a contract's deferred-revenue line vanishes when release and reclass net to zero (e.g. Contract 2 on 2023-01-31) | Harness A |
| VR-reports-10 | [L2647–2656]; [L2990–2999] | **no JE balance check** (Σ debits = Σ credits) and no rounding plug | ±0.01 imbalances are exported without warning | Harness B: May 2023 gross Σ = +0.01; Oct 2023 gross Σ = −0.01; probe H Σ = −0.01 |
| VR-reports-11 | [L2647–2649]; [L2990–2992] | **no null-account check**; `groupby` drops rows whose `Account` is NaN (pandas default `dropna=True`) | the UAR side of the reclass disappears; the JE is out of balance by the full reclass; the `Account` column turns float (`21001.0`) | Harness F: Unbilled A/R Account NULL on Contract 2 gives Σ = −58.85 |
| VR-reports-12 | all six methods [L2663–2668, L2718–2723, L2777–2782, L2813–2818, L2855–2860, L3006–3011] | any exception, e.g. no `Contract_Live` table (`pandas.errors.DatabaseError`), target Excel file open or locked (`PermissionError`), contract name with characters invalid in a Windows file name | `QMessageBox.critical(self, "Error Notification", str(e))`; best-effort `conn.close()` | Code |
| VR-reports-13 | `latest_contracts` [L2787–2803]; `specific_latest_contracts` [L2827–2845] | SQL keeps rows whose `Processing Time Log` = MAX per `Record Unique ID without time`; pandas `idxmax` then keeps the first row per key | exactly one row per POB key even if timestamps tie; "latest" is by **processing time, not `Current Period`** | Harness D: a backdated 2023-02-28 load processed after a 2023-03-31 load becomes "latest" |
| VR-reports-14 | `LicenseKeyDialog.save_license_key` [L3197–3205] | `api_key == ""` | `QMessageBox.warning` "Error" / "Chipmunk_License_Key cannot be empty."; otherwise writes `.env` `Chipmunk_License_Key=<key>` (overwrites the whole file) and shows "Success" / "Chipmunk_License_Key saved successfully!" | Code |
| VR-reports-15 | startup [L256–263, L265–276, L278–291] | `not (key[2]=="r" and key[5]=="s" and key[9]=="y" and key[15]=="s")`, or any exception (e.g. `None`, key shorter than 16 characters) | information box "Notice for the Premium Database Functions" / "Premium license key is not found. \nIf required, contact support for assistance support@chipmunkrpa.com\n\nNormal ASC606 Functions are still free to use."; disables buttons 6, 7, 8, 8_1, 8_2. **Reports and JEs are not gated.** The check is a client-side character test and trivially bypassed | Code |
| VR-reports-16 | `ShutdownNotifier` [L3077–3102], armed at [L3214–3216] | on a 60,000 ms timer (the comment "Check every second" is wrong): `datetime.now() >= datetime(2025, 12, 31, 23, 59)` | stops the timer; information box "End of Life Notification" / "The software end of life period has been reached. The application will now shut down. Please download the latest version."; `QApplication.quit()`. **Inference:** today (2026-09-11) the shipped app quits about 60 s after launch | Code |
| VR-reports-17 | `DataFramePopup.__init__` [L3044–3045] | always | information "File Saved" / "Details are exported to an Excel within the folder :)", including for 0-row results and before the window is shown | Code, harness |
| VR-reports-18 (upstream) | `browse_file_Deliveries` [L909–913] | Progress Tracking rows with any blank `Memo 1/2/3` are dropped by `groupby([... 'Memo 1','Memo 2','Memo 3'])` (`dropna=True`) | the delivery or billing is never versioned, yet "Rev Rec Success" is shown; the JE silently omits the activity | Harness G: rows before/after 24/24 |
| VR-reports-19 (upstream) | all mod handlers [L1413–1437, L1896–1920, L2331–2355] | mods neither reset `Current Pre-ASC606 Revenue (Net Design Only)` nor roll its cumulative | the new version carries the prior delivery's pre-ASC 606 amount, so the delta JE **double-counts** it when both versions fall in the range | Harness C: Contract 1 POB #2 delta revenue line moves from −52.53 to +13.47 after a zero-value VC mod dated 2023-01-31 |
| VR-reports-20 (upstream) | prospective mod final recompute [L1586–1594] | after the distinct/non-distinct concat, reclass is recomputed **without** the VC override applied elsewhere [L1088–1089, L1499–1500, L1575–1576] | a VC line could receive reclass if its cumulative SSP delivered is non-zero; no effect with a VC list price of 0 (UAT) | Code; harness B: 0 VC rows with non-zero reclass |

---

## 3. Calculation logic

Sign convention throughout the JE module (**Fact**, from the code): **positive Amount = debit, negative Amount = credit**. There are no separate debit and credit columns.

### 3.1 Record selection (all JE and history functions)

```text
rows      = SELECT * FROM "Contract_Live"                   -- every version of every POB [L2559–2563]
rows.CP   = pandas.to_datetime(rows["Current Period"])      -- [L2571–2572]
start, end = date prompts at 00:00:00                        -- [L2567–2568]
F         = rows WHERE start <= CP <= end                    -- inclusive both ends [L2574–2576]
```

- Selection uses the **economic event date** entered at load time (`Current Period`), not `Processing Time Log`.
- Every version in the range is included: setup versions (all activity amounts 0), delivery versions, and mod versions. Deliveries and mods append a full new version for **every POB of a touched contract**, so untouched POBs contribute rows with zero activity but possibly non-zero reclass balances ([L948–956], [L1356–1363]).

### 3.2 Component lines per selected record `r`

| # | Mode | Output key (`Record Unique ID without time` column) | Account | Amount | Lines |
|---|---|---|---|---|---|
| G1 | gross and delta | `r.Contract Unique Name` | `r.Deferred Revenue Account` | `+ round(r.Current Rev Rec, 4)` | [L2594–2598], [L2920–2924] |
| G2 | gross and delta | `r.Record Unique ID without time` (= `Contract POB SKU`) | `r.Revenue Account` | `− round(r.Current Rev Rec, 4)` | [L2601–2605], [L2927–2931] |
| G3 | gross and delta | `r.Contract Unique Name` | `r.Deferred Revenue Account` | `+ round(r.Previous Reclass to UAR, 4)` | [L2608–2613], [L2934–2939] |
| G4 | gross and delta | `r.Contract Unique Name` | `r.Unbilled A/R Account` | `− round(r.Previous Reclass to UAR, 4)` | [L2616–2621], [L2942–2947] |
| G5 | gross and delta | `r.Contract Unique Name` | `r.Deferred Revenue Account` | `− round(r.Current Reclass to UAR, 4)` | [L2624–2629], [L2950–2955] |
| G6 | gross and delta | `r.Contract Unique Name` | `r.Unbilled A/R Account` | `+ round(r.Current Reclass to UAR, 4)` | [L2632–2636], [L2958–2962] |
| D1 | delta only | `r.Record Unique ID without time` | `r.Revenue Account` | `+ round(r.Current Pre-ASC606 Revenue (Net Design Only), 4)` | [L2965–2971] |
| D2 | delta only | `r.Contract Unique Name` | `r.Deferred Revenue Account` | `− round(r.Current Pre-ASC606 Revenue (Net Design Only), 4)` | [L2973–2979] |

Reading the entries as bookkeeping (**Inference** from the commented memos [L2599, L2606, L2614, L2622, L2630, L2637] and README L83):
- G1/G2: Dr Deferred revenue / Cr Revenue, for revenue recognised in the period.
- G3/G4: Dr Deferred revenue / Cr Unbilled A/R, reversing the prior reclass.
- G5/G6: Dr Unbilled A/R / Cr Deferred revenue, booking the current reclass.
- D1/D2: Dr Revenue / Cr Deferred revenue, reversing revenue the ERP already booked on invoices under a "net design".

Neither mode touches A/R or billings. The ERP is assumed to post invoices (Dr A/R / Cr Deferred revenue in gross mode; Cr Revenue for the pre-ASC 606 portion in net design).

`0 - s.round(4)` negates the already-rounded Series, so G2 = −G1 exactly.

### 3.3 Consolidation

```text
C = concat(G1..G6 [, D1, D2], ignore_index=True)                       -- [L2639–2642] / [L2981–2985]
C = C[ C.Amount.round(2) != 0 ]                                          -- pre-filter [L2643–2644]
S = C.groupby(["Record Unique ID without time", "Account"]).Amount.sum() -- NaN keys dropped, NaN amounts skipped [L2647–2649]
S = S[ S.round(2) != 0 ];  S = S.round(2)                                -- post-filter and round [L2650–2651]
export S (index=False) and show popup                                   -- [L2654–2661]
```

Properties:
1. **Periods are collapsed.** `Current Period` is carried into each component frame but is not a grouping key, so a multi-month range yields one summary line per contract per balance-sheet account and one per POB per revenue account.
2. **Balance-sheet lines are per contract; revenue lines are per POB.** No entity, currency, department, memo or JE number is emitted. `Selling Entity` is ignored, so a contract whose POBs sit in different entities yields a JE that balances in total but not by entity.
3. **Pre-rounding balance.** For every record G1+G2 = G3+G4 = G5+G6 = D1+D2 = 0.
4. **Rounding.** Amounts are rounded to 4 dp per component, filtered at 2 dp, summed as binary floats, then rounded to 2 dp per line, with no plug. Balance can break by ±0.01 (VR-reports-10). The monthly JEs do not foot to the full-year JE line by line (harness B: four lines differ by ±0.01, e.g. Contract 3 / 21001 monthly Σ 2,599.99 vs full year 2,600.00).
5. **Account dtype.** SQLite INTEGER → pandas int64; the column becomes float64 if any account is null (VR-reports-11).
6. **Row order and index.** Sorted by `groupby` keys (lexicographic key, then account). The DataFrame index keeps gaps after filtering (e.g. 0,1,2,3,4,6), and the popup shows them as row headers.

### 3.4 Telescoping of the reclass over a date range

For one POB key, let versions `v_k … v_m` be consecutive in processing order and all inside the range. Because `Previous Reclass(v_i) = Current Reclass(v_{i−1})` ([L1008], [L1437], [L1920], [L2355]):

```text
Σ_i (G5+G6 on UAR) + (G3+G4 on UAR) = Current Reclass(v_m) − Previous Reclass(v_k)
                                    = UAR balance at end of range − UAR balance at start of range
net Deferred JE (gross) = Σ Current Rev Rec − [Current Reclass(v_m) − Previous Reclass(v_k)]
net Deferred JE (delta) = the gross amount − Σ Current Pre-ASC606 Revenue
net Revenue JE (gross)  = − Σ Current Rev Rec          (per POB)
net Revenue JE (delta)  = − Σ Current Rev Rec + Σ Current Pre-ASC606 Revenue
```

This holds only when processing order equals `Current Period` order. With a backdated load (harness D), the February JE reversed a reclass first booked in a March version: UAR at 2023-02-28 showed −104.61, a credit balance in an asset account. Q1 in total was still correct to ±0.01.

Full-year check (harness B, all four UAT contracts fully delivered and billed by 2023-10-31):
- Deferred revenue full-year debit equals cumulative revenue: Contract 1 800.00, Contract 2 1,100.00, Contract 3 2,600.00, Contract 4 1,200.00.
- UAR nets to 0.
- Latest `Current Billing - Cumulative` equals `Current Rev Rec - Cumulative` for every contract.

With ERP billings credited to deferred revenue, every closing contract balance is therefore 0.

### 3.5 Upstream formulas that produce the JE source columns

These are summarised so that §5 can be traced; the owning docs (01–05) hold the full rules.

**SSP range (setup)** [L682–700]; the mod equivalents are [L1286–1331] and [L1770–1815]:

```text
Mid  = Qty × ListPrice × (1 − MidpointDiscount%)
High = Mid × (1 + Range%)
Low  = Mid × (1 − Range%)
ExtendedSSP = High      if SellingPrice > High
            = Low       if SellingPrice < Low
            = SellingPrice otherwise              -- price inside the range is used as SSP; outside, the nearer bound is used
Mods with Mod Qty <= 0 invert the comparisons (Mod Billing < High → High; > Low → Low) [L1322–1328]
```

**Relative-SSP allocation (setup)** [L704–717]. There is no residual approach, no specific discount allocation and no rounding; values are floats.

```text
TotalPrice_c = Σ_c SellingPrice;  TotalSSP_c = Σ_c ExtendedSSP
Allocation_p = ExtendedSSP_p / TotalSSP_c × TotalPrice_c        -- discount or premium spread pro rata to ALL lines
UnitSSP_p    = ExtendedSSP_p / Qty_p;   UnitRevRec_p = Allocation_p / Qty_p
```

A VC line has a negative selling price and SSP 0 (list price 0). It therefore reduces `TotalPrice_c` for everyone and receives 0 allocation itself.

**Delivery version** [L1011–1089]:

```text
CurrentRevRec     = Delivery × RemainingUnitRevRec(prior)            -- negative delivery = return reverses revenue
SSPDelivered      = Delivery × UnitSSP(prior)
Remaining Qty/SSP/Allocation/Billing -= Delivery / SSPDelivered / CurrentRevRec / Billing
UnitSSP, RemainingUnitRevRec = Remaining / RemainingQty  (NaN → 0 when fully delivered)
*_Cumulative      = prior cumulative + current
PositionPOB       = BillingCum − RevRecCum                              -- + = billed ahead (liability), − = revenue ahead (asset)
PositionContract  = Σ_contract PositionPOB                              -- includes VC and untouched POBs
ReclassToUAR_p    = −PositionContract × SSPDeliveredCum_p / Σ_contract SSPDeliveredCum   if PositionContract < 0 else 0
ReclassToUAR_p    = 0 where ASC 606 Stratification == "VC"
CurrentPreASC606  = uploaded column F summed per key; 0 for untouched POBs of the contract
```

**Mod versions.**
- `Current Delivery`, `Current Billing`, `Current Rev Rec` and `Current Cumulative Catchup - Disclosure Only` are reset to 0 ([L1469–1473], [L1965–1968], [L2383–2386]). `Current Rev Rec` is then overwritten with the cumulative catch-up:
  - prospective mod, Nondistinct SKUs only [L1526–1549];
  - retrospective mod and POB-specific VC, all POBs ([L2019–2040], [L2427–2447]): `ShouldBe = (RemainingAllocation + RevRecCum) / (RemainingSSP + PrevSSPDeliveredCum) × PrevSSPDeliveredCum`; catch-up = `ShouldBe − RevRecCum`.
- Reclass is recomputed with the same formula.
- `Current Pre-ASC606 Revenue` is **not** reset (VR-reports-19).

### 3.6 Contract position and "reclass to unbilled A/R"

- **Measured at contract level** ([L1076–1079] and equivalents). This is ASC 606 net contract-position presentation, not a gross per-POB split.
- **Attributed to POBs** in proportion to cumulative SSP delivered. The attribution is informational only, because the JE consolidates the UAR and deferred lines per contract.
- **Recomputed as a balance** at every version and posted as reverse-previous plus book-current, so the GL carries the latest balance.
- **Inference.** The design assumes the deferred revenue account holds, per contract, (billings − ASC 606 revenue); in delta mode that is (billings − pre-ASC 606 revenue − ASC 606 revenue + pre-ASC 606 revenue). The reclass then clears any debit balance in deferred revenue into UAR. It is correct only if the ERP posts **every** billing for the contract to the configured deferred revenue account (or to revenue up to the pre-ASC 606 amount in net design).

### 3.7 Pre-ASC 606 revenue (net design) and the delta JE

Assumed ERP invoice entry in net design (**Inference** from [L2965], [L2973] and README L83):

```text
Dr A/R                       Billing
   Cr Revenue                Pre-ASC606 revenue        (template column F)
   Cr Deferred revenue       Billing − Pre-ASC606 revenue
```

The eRev delta JE adds D1/D2 plus G1–G6:

```text
GL Revenue_p   = Pre606 − Pre606 + RevRec        = ASC 606 revenue            ✓
GL Deferred_c  = (Billing − Pre606) + Pre606 − RevRec − ΔReclass = Billing − RevRec − Reclass_end
GL UAR_c       = Reclass_end
```

Resulting behaviour:
- Template column F is **period activity**, not cumulative.
- It is keyed per POB. The legacy code does not validate it against billing (e.g. pre-ASC 606 revenue > billing is accepted).
- UAT 1.31.2023 rows mix designs: Contract 1 POB #2 billed 100 with 66 booked to revenue; POB #1 billed 100 with 0 to revenue.

### 3.8 Contract history

`contract_history` [L2670–2723] and `specific_contract_history` [L2725–2782]:
- Same period filter as §3.1; `specific` adds `WHERE "Contract Unique Name" = "{name}"` before the filter.
- Output is the unmodified 71-column version rows in **DB insertion order** (no `ORDER BY`), with `Current Period` converted to datetime.
- No computed columns and no version-to-version deltas. README L85 says users subtract versions in Excel.

### 3.9 Latest contract status

`latest_contracts` [L2784–2818] and `specific_latest_contracts` [L2820–2860]:

```sql
SELECT t1.* FROM Contract_Live t1
JOIN (SELECT "Record Unique ID without time", MAX("Processing Time Log") AS max_timestamp
      FROM Contract_Live [WHERE "Contract Unique Name" = "{name}"]
      GROUP BY "Record Unique ID without time") t2
  ON t1."Record Unique ID without time" = t2."Record Unique ID without time"
 AND t1."Processing Time Log" = t2.max_timestamp;
```

- Then `groupby(key).idxmax()` on the parsed timestamp keeps one row per key [L2801–2803].
- `MAX` over the text timestamp is lexicographic, which is chronological for pandas' `YYYY-MM-DD HH:MM:SS[.ffffff]` form.
- There is no "as of period" parameter: the view is "latest processed", not "latest as at a date".
- Excel export keeps the pandas index (72 columns incl. `Unnamed: 0`, harness A).
- The shipped DB returns 16 rows (Contracts 1–2 at 2023-01-31, Contracts 3–4 at 2023-02-01).

---

## 4. State transitions: how `Contract_Live` is versioned

The JE and report functions write nothing. Their correctness depends entirely on how the upstream handlers append versions, so this section documents that contract.

### 4.1 Append-only version log

| Event (button) | Handler | Rows appended | `Current Period` of new rows | Write |
|---|---|---|---|---|
| Load Contracts | `browse_file_Contracts` [L621–824] | one per template row | template column M | `to_sql(if_exists="append")` [L807]; `replace` only if the table does not exist [L812] |
| Load Delivery and Billing | `browse_file_Deliveries` [L826–1168] | one per POB of **every contract with at least one uploaded row** [L948–956] | prompt date [L1025–1026] | append [L1154] |
| Prospective Contract Mod | `browse_file_ProsMod` [L1170–1653] | one per POB of every contract named in the file, plus new POB rows [L1356–1363] | prompt date [L1398] | append [L1638] |
| Retrospective Contract Mod | `browse_file_RetroMod` [L1655–2131] | same | prompt date [L1881] | append [L2117] |
| POB Specific VC | `browse_file_POB_specific_VC` [L2133–2538] | same | prompt date [L2316] | append [L2524] |

Destructive or bulk operations that change the log:
- **Reset**: drops every table after a Yes/No confirmation [L375–395].
- **Purge Contracts**: `DELETE … WHERE "Contract Unique Name" = "{name}" AND "Current Period" BETWEEN "{start_date}" AND "{end_date}"`. This is another f-string SQL injection, and the name prompt's `ok` is not checked [L495–509].
- **Append from Another**: positional `INSERT INTO "Contract_Live" VALUES (?, …)` of every source row, with no de-duplication [L418–425].
- **Load SSPs**: `SKU_SSP` is replaced wholesale [L577]. Existing versions keep the SSP values they copied at setup.

No handler issues `UPDATE`.

### 4.2 Keys and timestamps

| Column | Formula | Notes |
|---|---|---|
| `Record Unique ID without time` | `Contract Unique Name + " " + POB Unique ID + " " + SKU Name` [L758–760, L1113–1117, L1333–1339, L1817–1821, L2250–2254] | Business key of a POB line. Space-joined without escaping, so `("A B","1","X")` and `("A","B 1","X")` collide (**Inference**). It is the JE revenue-line key. |
| `Processing Time Log` | `pd.Timestamp.now()`, once per load, identical for all rows of that load [L757, L1112, L1503, L1996, L2414] | Version order. "Latest" = MAX by key (§3.9). |
| `Record Unique ID` | `str(Processing Time Log) + " " + Contract + " " + POB + " " + SKU` [L761–762, L1118–1121, L1504–1507, L1997–2000, L2415–2418] | Version primary key by convention only; no constraint exists. |
| `Current Period` / `Previous Period` | setup: template date and `NaT` [L720]; later: `Previous Period ← prior Current Period`, `Current Period ← prompt date` [L1009, L1025, L1397–1398, L1880–1881, L2315–2316] | Economic date used by the JE filter. Nothing enforces monotonicity relative to `Processing Time Log`. |

### 4.3 Roll-forward (Previous ← Current) on every non-setup version

`fillna(0)` is applied throughout.

| Previous column ← Current column of the prior latest version | Delivery [L980–1009] | Prospective [L1414–1437] | Retro [L1897–1920] | POB VC [L2332–2355] |
|---|---|---|---|---|
| Remaining Qty, Remaining SSP, Remaining Allocation, Remaining Billing, Unit SSP, Remaining Unit Rev Rec | ✓ | ✓ | ✓ | ✓ |
| Delivery - Cumulative, Rev Rec - Cumulative, Billing - Cumulative | ✓ | ✓ | ✓ | ✓ |
| Cumulative Catchup - Cumulative - Disclosure Only, SSP Delivered - Cumulative | ✓ | ✓ | ✓ | ✓ |
| Contract Position - POB, Contract Position - Contract Level, **Reclass to UAR** | ✓ | ✓ | ✓ | ✓ |
| Pre-ASC606 Revenue (Net Design Only) - Cumulative | ✓ | **✗** | **✗** | **✗** |
| Period | ✓ | ✓ | ✓ | ✓ |

Current activity columns on the new version:

| Column | Setup | Delivery | Prospective | Retro | POB VC |
|---|---|---|---|---|---|
| `Current Delivery`, `Current Billing` | 0 | uploaded (0 for untouched POBs) | 0 | 0 | 0 |
| `Current Rev Rec` | 0 | Delivery × unit rev rec | catch-up (Nondistinct only), else 0 | catch-up (all POBs) | catch-up (all POBs) |
| `Current Pre-ASC606 Revenue (Net Design Only)` | 0 | uploaded (0 for untouched POBs) | **carried from prior version** | **carried** | **carried** |
| `Current SSP Delivered` | 0 | Delivery × unit SSP | 0 [L1472] | **carried** (not reset) | **carried** |
| `Current Reclass to UAR` | 0 | recomputed | recomputed | recomputed | recomputed |

New POBs added by a mod (outer-join `right_only` rows) have NULL `Original …` columns and a NULL `Current Pre-ASC606 Revenue` (harness B: Contract 3 POB #5). The JE tolerates this because NaN amounts are skipped in the `sum`.

### 4.4 Transitions observed in the shipped DB and in the replay

- **Shipped DB (24 rows):**
  - `2025-05-09 09:11:44.708286`: setup 1.1.2023, 8 rows (Contracts 1–2, `Current Period` 2023-01-01).
  - `09:11:53.453841`: setup 2.1.2023, 8 rows (Contracts 3–4, 2023-02-01).
  - `09:12:33.441992`: delivery 1.31.2023, 8 rows (all POBs of Contracts 1–2, 2023-01-31).
- **Fresh replay** of the UAT files through the unmodified legacy handlers reproduced those 24 rows exactly on all 69 non-timestamp columns (SQL `EXCEPT` in both directions returned 0 rows).
- **Full replay** of the remaining UATs (2.28, 3.31, 4.30 deliveries; 5.15 retro; 5.31 POB VC; 6.15, 7.15, 9.15 prospective; 8.15 retro; 10.31 full delivery) grew the log to 106 rows.
- **Cross-check:** my monthly and full-year JE outputs are identical to `docs/legacy/golden/monthly/*` produced independently by the golden-master harness.

### 4.5 Consequences for the reports (**Inference**, confirmed where marked)

1. The JE for a range is the set of versions whose `Current Period` is in range. It equals period activity only when versions for a key are processed in `Current Period` order (confirmed by harness D).
2. Purging a middle version breaks the Previous/Current reclass chain: the next version still reverses the purged version's `Current Reclass`. JEs for later ranges then reverse amounts that no longer exist in the log.
3. Append-from-another can interleave two histories for the same key. "Latest" picks whichever was processed last on either machine.
4. There is no period lock (README L67: "doesn't freeze periods"). Re-running a JE range after a backdated load changes a period that may already have been posted.

---

## 5. Worked example: Delivery and Billing UAT 1.31.2023 on the shipped DB

Inputs:
- `ops/Example UATs/SSP Upload UAT/SKU SSP Template.xlsx`
- `Contract Setup UAT/Contract Setup Template 1.1.2023.xlsx`
- `Delivery and Billing UAT/Contract Progress Tracking Template 1.31.2023.xlsx`

Report run: Gross Revenue JEs and Revenue Adjustment JEs, range 2023-01-01 to 2023-01-31.

### 5.1 Contract setup (version at 2023-01-01)

Contract 1 (Mock Entity 1; Deferred 21001; UAR 15001):

| POB | SKU (rev acct) | Qty | Price | List | Mid disc | Range | Mid | High | Low | Extended SSP | Rule | Allocation = SSP/2,018 × 1,300 | Unit rev rec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| #1 | Hardware 1 (5001) | 5 | 500 | 100 | 10% | ±15% | 450.00 | 517.50 | 382.50 | 500.00 | price inside range | 322.101090 | 64.420218 |
| #2 | Software 1 (5002) | 2 | 400 | 200 | 20% | ±15% | 320.00 | 368.00 | 272.00 | 368.00 | price > High | 237.066402 | 118.533201 |
| #3 | Consulting 1 (5003) | 1 | 400 | 300 | 50% | 0% | 150.00 | 150.00 | 150.00 | 150.00 | price > High | 96.630327 | 96.630327 |
| #4 | Material Right - Hardware (5001) | 1,000 | 0 | 1 | 0% | 0% | 1,000.00 | 1,000.00 | 1,000.00 | 1,000.00 | price < Low | 644.202180 | 0.644202 |
| **Total** | | | **1,300** | | | | | | | **2,018.00** | | **1,300.000000** | |

Contract 2 (Mock Entity 2; Deferred 21002; UAR 15002):

| POB | SKU (rev acct) | Qty | Price | Mid | High | Low | Extended SSP | Allocation = SSP/1,170 × 900 | Unit rev rec |
|---|---|---|---|---|---|---|---|---|---|
| #1 | Hardware 1 (5001) | 8 | 600 | 720.00 | 828.00 | 612.00 | 612.00 (price < Low) | 470.769231 | 58.846154 |
| #2 | Software 1 (5002) | 3 | 400 | 480.00 | 552.00 | 408.00 | 408.00 (price < Low) | 313.846154 | 104.615385 |
| #3 | Consulting 1 (5003) | 1 | 0 | 150.00 | 150.00 | 150.00 | 150.00 (price < Low) | 115.384615 | 115.384615 |
| VC #1 | Variable Consideration (5004) | 1 | −100 | 0.00 | 0.00 | 0.00 | 0.00 (price < Low) | 0.000000 | 0.000000 |
| **Total** | | | **900** | | | | **1,170.00** | **900.000000** | |

These values match the shipped DB (e.g. `Original Total Contract SSP` = 2018.0; `Current Remaining Allocation` for Contract 2 POB #1 = 470.7692).

### 5.2 Delivery upload and new versions (2023-01-31)

The file has five rows. Contract 1 POB #1 appears twice (1 unit / 50 billed each) and is summed by the `groupby` at [L909–913].

| Key | Delivery | Billing | Pre-ASC 606 | Current Rev Rec = Dlv × unit | SSP delivered = Dlv × unit SSP | Position POB = Bill cum − RevRec cum |
|---|---|---|---|---|---|---|
| C1 POB #1 Hardware 1 | 2 | 100 | 0 | 2 × 64.420218 = **128.840436** | 2 × 100 = 200 | −28.840436 |
| C1 POB #2 Software 1 | 1 | 100 | 66 | **118.533201** | 184 | −18.533201 |
| C1 POB #3 Consulting 1 | 0.5 | 100 | 88 | 0.5 × 96.630327 = **48.315164** | 75 | +51.684836 |
| C1 POB #4 Material Right | 0 (untouched; re-versioned) | 0 | 0 | 0 | 0 | 0 |
| **Contract 1 position** | | | | | | **+4.311199 ≥ 0 → Reclass 0 on all POBs** |
| C2 POB #1 Hardware 1 | 1 | 0 | 0 | **58.846154** | 612/8 = 76.5 | −58.846154 |
| C2 POB #2, #3, VC #1 | 0 (re-versioned) | 0 | 0 | 0 | 0 | 0 |
| **Contract 2 position** | | | | | | **−58.846154 < 0 → Reclass POB #1 = 58.846154 × 76.5 / 76.5 = 58.846154** |

All figures agree with the shipped DB to the stored precision (e.g. `Current Rev Rec` 128.840436075322; `Current Contract Position - Contract Level` 4.31119920713579; `Current Reclass to UAR` 58.8461538461538).

### 5.3 JE components and consolidated output

Only the eight 2023-01-31 versions are in range; the setup versions are dated 2023-01-01 and 2023-02-01. `Previous Reclass to UAR` is 0 on all of them.

| Component | C1 21001 | C1 POB #1 5001 | C1 POB #2 5002 | C1 POB #3 5003 | C2 21002 | C2 15002 | C2 POB #1 5001 |
|---|---|---|---|---|---|---|---|
| G1 release | +128.8404 +118.5332 +48.3152 | | | | +58.8462 | | |
| G2 revenue | | −128.8404 | −118.5332 | −48.3152 | | | −58.8462 |
| G5/G6 reclass | | | | | −58.8462 | +58.8462 | |
| **Gross sum → round(2)** | **+295.69** | **−128.84** | **−118.53** | **−48.32** | 0.00 → **suppressed** | **+58.85** | **−58.85** |
| D1/D2 pre-ASC 606 (delta only) | −66 −88 | | +66 | +88 | | | |
| **Delta sum → round(2)** | **+141.69** | **−128.84** | **−52.53** | **+39.68** | suppressed | **+58.85** | **−58.85** |

Legacy exports:

`Revenue JE Summary between 2023-01-01 and 2023-01-31.xlsx` (Σ debits 354.54 = Σ credits 354.54):

| Record Unique ID without time | Account | Amount |
|---|---|---|
| Contract 1 | 21001 | 295.69 |
| Contract 1 POB #1 Hardware 1 | 5001 | -128.84 |
| Contract 1 POB #2 Software 1 | 5002 | -118.53 |
| Contract 1 POB #3 Consulting 1 | 5003 | -48.32 |
| Contract 2 | 15002 | 58.85 |
| Contract 2 POB #1 Hardware 1 | 5001 | -58.85 |

`Revenue Adj. Summary between 2023-01-01 and 2023-01-31.xlsx` (Σ debits 240.22 = Σ credits 240.22):

| Record Unique ID without time | Account | Amount |
|---|---|---|
| Contract 1 | 21001 | 141.69 |
| Contract 1 POB #1 Hardware 1 | 5001 | -128.84 |
| Contract 1 POB #2 Software 1 | 5002 | -52.53 |
| Contract 1 POB #3 Consulting 1 | 5003 | 39.68 |
| Contract 2 | 15002 | 58.85 |
| Contract 2 POB #1 Hardware 1 | 5001 | -58.85 |

Both outputs match the harness (`runs/A_shipped/out/`) and `docs/legacy/golden/04-delivery-billing-2023-01-31/je_*.csv`.

### 5.4 Implied ledger at 2023-01-31 (gross design; **Inference**: ERP credits every invoice to deferred revenue)

| Contract | Deferred revenue | Unbilled A/R | Legacy position | ASC 606 presentation |
|---|---|---|---|---|
| 1 | ERP Cr 300.00 − eRev Dr 295.69 = **Cr 4.31** | 0 | +4.311199 | contract liability 4.31 (net of four POBs, two of them in asset positions) |
| 2 | ERP Cr 0 − Dr 58.85 + Cr 58.85 = **0** | **Dr 58.85** | −58.846154 | contract asset 58.85 |

### 5.5 Supplementary traces (harness B, full UAT replay)

**Contract 2, April 2023. Reclass reversal mechanics.**
- At 2023-03-31: position −105.00; reclass is spread by SSP delivered (76.5 : 60), giving POB #1 105 × 76.5/136.5 = 58.846154 and POB #3 105 × 60/136.5 = 46.153846.
- The 4.30 upload bills 20 on POB #1, so position → −85.00 and reclass → 47.637363 / 37.362637.
- April JE:
  - G3/G4 reverse 105.00 (Dr 21002 / Cr 15002).
  - G5/G6 book 85.00 (Dr 15002 / Cr 21002).
  - Revenue 0.
- Output: `Contract 2 | 15002 | -20.00` and `Contract 2 | 21002 | 20.00`. The ERP's Cr 20 on the invoice leaves deferred revenue at 0 and UAR at Dr 85.

**Contract 2, May 2023. Catch-up and a rounding imbalance.**
- 5.15 retro mod: catch-up POB #1 +13.376068 and POB #3 +10.491049; reclass 85.00 → 108.867111.
- 5.31 POB-specific VC (−200 on POB #1): catch-up POB #1 −18.681319; reclass → 90.185792.
- May JE:
  - Revenue POB #1 = −(13.376068 − 18.681319) = +5.305251 → **+5.31**.
  - POB #3 = −10.491049 → **−10.49**.
  - UAR = +23.867111 − 18.681319 = +5.185792 → **+5.19**.
  - Deferred nets to 0 and is suppressed.
- **Σ = +0.01 (unbalanced export).**

---

## 6. Accounting assessment

External sources are public pages of the Deloitte DART *Roadmap: Revenue Recognition*, retrieved 2026-09-11. Paragraph content is paraphrased from those pages; no codification text is reproduced. The session's web-search budget was exhausted, so every citation below comes from a direct page fetch. Two DART pages on SSP estimation returned "not found", and SSP-range practice is therefore marked **Inference**.

| Ref | URL |
|---|---|
| [D14.1] | [external website reference removed] |
| [D14.2] | [external website reference removed] |
| [D14.4] | [external website reference removed] |
| [D14.5] | [external website reference removed] |
| [D9] | [external website reference removed] |
| [D9.2] | [external website reference removed] |
| [D9.4] | [external website reference removed] |
| [D7] | [external website reference removed] |
| [D7.4] | [external website reference removed] |
| [D7.5] | [external website reference removed] |
| [D7.6] | [external website reference removed] |
| [D11.7] | [external website reference removed] |
| [D15.2] | [external website reference removed] |

### 6.1 Where the legacy logic is correct

| Topic | Legacy behaviour | Requirement (fact, with source) | Assessment |
|---|---|---|---|
| Net contract position | Position = Σ over all POBs of one contract (billing − revenue); reclass only when the net is < 0; each contract is evaluated separately ([L1073–1089]) | ASC 606-10-45-1: once either party has performed, present the contract as a contract asset or a contract liability. Rights and obligations within the same contract are presented net (BC317 of ASU 2014-09); the guidance nets only within a contract [D14.1] | **Correct**: netting across POBs of one contract, no offset across contracts |
| Contract liability | Credit balance left in deferred revenue when billings exceed revenue | ASC 606-10-45-2: obligation to transfer goods or services for which consideration has been received or is due [D14.2] | **Correct** |
| Relative-SSP allocation | Allocation = SSP / ΣSSP × transaction price; any discount spread pro rata to all lines ([L704–717]) | Allocation objective based on relative SSP (606-10-32-28/29) [D7]; default proportionate allocation of a discount (606-10-32-36) [D7.4] | **Correct** default method |
| Price-change catch-up for satisfied POBs | Retrospective mod and POB-specific VC write the cumulative catch-up into `Current Rev Rec` on the event date; the JE posts it in that period (e.g. May 2023 Contract 2) | 606-10-32-43: allocate later changes on the same basis as at inception; 32-44: amounts allocated to satisfied POBs are recognised as revenue, or as a reduction, in the period of change [D7.6] | **Correct timing**. Caveat: the retro handler reallocates using remaining SSP, which can include post-inception SSP versions chosen in the mod file; 32-43 forbids reallocation for SSP changes after inception [D7.6] (**Inference**: review the mod doc) |
| VC tied to one POB | "POB Specific VC" adds `Mod Billing` to one POB's remaining allocation ([L2367–2370]) and catches up that POB | 606-10-32-39 to 32-41: VC may be allocated entirely to one POB when its terms relate specifically to that POB and the allocation objective is met [D7.5] | **Mechanism correct**; criteria are user judgement with no documentation gate |
| Modifications with non-distinct remaining goods | Prospective mod applies a cumulative catch-up only to `Nondistinct` SKUs ([L1526–1549]) | 606-10-25-13(a): distinct remaining goods → prospective (termination and new contract); 25-13(b): not distinct and part of a partially satisfied single POB → cumulative catch-up; 25-13(c): combination [D9.2] | **Broadly correct**, but driven by a static SKU flag rather than a per-modification assessment. Modification definition and approval (25-10/25-11) are covered in [D9] §9.1 and not re-verified here |
| Material-right exercise | UAT 9.15 removes the material-right quantity and adds a new POB through a prospective mod | Exercise may be accounted for as a continuation of the contract (the TRG-preferred view) or as a contract modification (acceptable), applied consistently [D11.7] | **Acceptable policy**; the choice should be an explicit tenant policy |
| JE simplicity | Maximum three account families per contract; UAR posted as change in balance | No GAAP requirement on JE granularity (**Inference**) | Practical and auditable at contract level |

### 6.2 Where it is simplified or incomplete

1. **Contract asset vs receivable conflated.** Legacy moves the whole net debit position into one "Unbilled A/R" account.
   - ASC 606-10-45-3: a contract asset is a right to consideration conditioned on something other than the passage of time, presented excluding amounts shown as receivables [D14.4].
   - ASC 606-10-45-4: a receivable is unconditional (only the passage of time is required) and may be recognised before invoicing [D14.5].
   - A delivered POB awaiting only an invoice date is a receivable, not a contract asset. Legacy cannot tell the two apart, which affects balance-sheet captions and the 50-8(a) balances.
2. **No contract-balance or disclosure reporting.** Requirements [D15.2]:
   - 606-10-50-8(a) opening and closing receivables, contract assets and contract liabilities;
   - 50-8(b) revenue recognised from the opening contract liability;
   - 50-10 explanation of significant changes, including cumulative catch-up adjustments;
   - 50-12A revenue from POBs satisfied in previous periods;
   - 50-13 remaining performance obligations.
   Legacy stores "Disclosure Only" catch-up columns and remaining allocations, but the reporting buttons expose only raw version rows. Users must build the roll-forwards in Excel.
3. **Changes in transaction price after a modification.** 606-10-32-45 allocates a change to the POBs that existed before the modification when the variable consideration was promised before it; otherwise to the POBs unsatisfied after the modification [D9.4]. Legacy leaves this to which button the user picks (retrospective, prospective or POB VC), with no decision support.
4. **Discount-allocation exception.** 606-10-32-37 allows allocating the entire discount to some POBs when three observable-evidence criteria are met, and 32-38 sequences this before any residual approach [D7.4]. Legacy supports only proportionate allocation; there is no residual approach.
5. **SSP range method.** Legacy uses the contract price as SSP inside ±range% of a list-price midpoint and the nearer bound outside it. **Inference:** this is an entity policy for estimating SSP. The estimation approaches listed at 606-10-32-34 (adjusted market assessment, expected cost plus margin, residual) [D7] are not modelled explicitly. The range method's support in practice could not be verified from a public source this session (open question).
6. **Delta (net-design) mode.** Correctness depends on user-keyed pre-ASC 606 revenue per POB per event, with no tie-out to ERP invoices, no check that pre-ASC 606 revenue ≤ billing, and no GL reconciliation (**Inference**).
7. **Entity dimension.** README L59 advertises cross-subsidiary contracts, but the JE balances only in total and the contract position nets POBs of different selling entities. **Inference:** entity-level statutory balance sheets and intercompany entries would be wrong for multi-entity contracts.
8. **Gross mode assumes every invoice credits deferred revenue.** If the ERP credits revenue on invoicing and the user runs Gross JEs, revenue double-counts. The legacy app has no control that ties the mode to the ERP design (**Inference**).

### 6.3 Where it is wrong: edge cases mishandled

| # | Edge case | Legacy result (evidence) | Accounting consequence |
|---|---|---|---|
| E-1 | Any mod in the same range as a delivery with pre-ASC 606 revenue | Delta JE reverses pre-ASC 606 revenue twice (VR-reports-19; harness C) | GL revenue understated and deferred revenue overstated by the carried amount; delta mode no longer yields ASC 606 revenue |
| E-2 | Events processed out of effective-date order | Reclass reversed in the wrong period; Contract 2 UAR at 2023-02-28 = −104.61 (harness D) | Interim contract asset/liability balances misstated (45-1 presentation; 50-8(a) balances). Totals self-correct later |
| E-3 | Floating rounding | ±0.01 unbalanced exports (May, Oct); monthly Σ ≠ full-year (VR-reports-10; harness B, H) | ERP rejects the JE or the user plugs manually; subledger-to-GL drift |
| E-4 | Sub-cent components | dropped before summing (VR-reports-08) | small completeness leakage |
| E-5 | Missing account on a POB | line silently dropped, JE out of balance (VR-reports-11; harness F) | GL misstatement with no exception report |
| E-6 | Progress rows with blank memos | delivery or billing ignored, success shown (VR-reports-18; harness G) | revenue and billings incomplete |
| E-7 | Purging a middle version (**Inference**) | Previous/Current reclass chain broken | later JEs reverse reclass that was never booked, or never reverse booked reclass |
| E-8 | No period lock | re-running a posted range after a backdated event gives a different JE | posted periods are mutable; SOX change-control gap |
| E-9 | "Latest" by processing time | backdated version reported as current (harness D) | status report misleading for cut-off review |
| E-10 | Contract-name input | SQL injection returns all contracts (VR-reports-06) | data exposure and wrong report scope |
| E-11 | Prospective recompute without the VC override (VR-reports-20) | no effect in UAT (VC SSP 0) | potential reclass to a VC line if a VC SKU has non-zero SSP |

### 6.4 Human review points for the new platform

These are accounting policy decisions that should require controller approval and be recorded per tenant:
- contract asset vs receivable classification (45-3/45-4);
- rounding policy and rounding account;
- material-right exercise approach [D11.7];
- VC single-POB allocation criteria [D7.5];
- modification classification under 25-12/25-13 [D9.2];
- ERP posting design (gross vs net) that selects the JE mode.

---

## 7. Port notes for eRev Cloud

### 7.1 Parity requirements (preserve)

| ID | Requirement | Legacy evidence |
|---|---|---|
| P-JE-01 | Two JE modes over an inclusive event-date range: **Gross** (ASC 606 revenue out of deferred revenue plus unbilled/contract-asset reclass) and **Adjustment/Delta** (gross plus reversal of pre-ASC 606 revenue already booked by the ERP) | [L3117–3125], §3.2 |
| P-JE-02 | Line semantics: Dr Deferred / Cr Revenue for period revenue; reverse the prior reclass and book the current reclass between Deferred and Unbilled A/R; delta mode adds Dr Revenue / Cr Deferred for pre-ASC 606 revenue | §3.2 G1–G6, D1–D2 |
| P-JE-03 | Contract position = Σ over the contract's POBs (incl. VC lines) of (billing cum − revenue cum). Reclass to Unbilled A/R = −position only when the position is < 0, attributed to POBs pro rata to cumulative SSP delivered; VC lines receive 0 | [L1073–1089] |
| P-JE-04 | UAR posting over a range equals the change in the contract's reclass balance (end − start), so repeated events never leave "back-and-forth" lines | §3.4; README L83 |
| P-JE-05 | Summarisation: balance-sheet lines per contract and account; revenue lines per POB and revenue account; zero net lines suppressed | [L2647–2651] |
| P-JE-06 | Accounts sourced per POB: Deferred and UAR from contract setup (and mods for new POBs); revenue account from the SKU/SSP catalogue | §1.3.2 |
| P-JE-07 | Golden outputs in §5.3 and TC-JE-01 to TC-JE-08 must be reproduced to the cent where legacy balances; the two unbalanced legacy months (May, Oct) must match line by line to ±0.01 | harness B = `docs/legacy/golden/monthly` |
| P-REP-01 | Contract History: every version whose event date is in range, all 71 fields, all contracts or one contract, downloadable | [L2670–2782] |
| P-REP-02 | Latest Contract Status: one current row per Contract+POB+SKU with all fields, all contracts or one contract, downloadable | [L2784–2860] |
| P-REP-03 | Each report produces a file export named with the date range, plus an on-screen grid | §1.4 |
| P-REP-04 | Setup versions carry zero activity. Deliveries and mods re-version all POBs of a touched contract, so history shows the whole contract at each event | §4.1 |

### 7.2 Behaviours to fix

| ID | Legacy behaviour | Fix in eRev Cloud |
|---|---|---|
| FX-01 | Unbalanced JEs (±0.01) and no balance check (VR-reports-10) | Compute in `NUMERIC` (≥ 6 dp), round once per final line with a documented rule (tenant policy; default half-up), post any difference to a configured rounding account or largest line, and block export unless Σ Dr = Σ Cr per JE and per entity |
| FX-02 | Component pre-filter drops sub-cent amounts before summing (VR-reports-08) | Filter only after consolidation |
| FX-03 | Null accounts silently dropped (VR-reports-11) | Account mapping is required and validated at setup/mod; JE generation fails with an exceptions report |
| FX-04 | Mods carry forward `Current Pre-ASC606 Revenue` (VR-reports-19) | Model pre-ASC 606 revenue as event-level activity; a mod event carries 0 unless supplied; roll the cumulative on every event |
| FX-05 | Reclass mis-attributed to periods when events are processed out of `Current Period` order (§3.4, harness D) | Derive contract balances **as at period end** from effective-dated events (sorted by effective date, then sequence). JE for a period = balance(end) − balance(start). Recompute later periods on a backdated event, and flag already-posted periods |
| FX-06 | No period close; ranges can be re-run with different answers (§4.5) | Accounting periods with open/closed status; posted JEs immutable; backdated activity into a closed period posts to the first open period with a prior-period flag (feeds 606-10-50-12A disclosure) |
| FX-07 | "Latest" = last processed, not effective-dated (VR-reports-13) | "As of" date parameter; latest version by effective date with processing sequence as tie-break |
| FX-08 | SQL injection and unchecked Cancel on contract-name prompts (VR-reports-05/06) | Parameterised queries, contract picker, explicit empty-result message |
| FX-09 | No start ≤ end validation (VR-reports-04) | Validate in UI and API |
| FX-10 | JE lacks entity, currency, period, JE number, memo, dimensions; balances only in total | Emit ERP-ready JE lines with posting period, subsidiary/entity, currency, department/class/location, line memo, source contract/POB references; balance per entity (intercompany when POBs span entities) |
| FX-11 | "Unbilled A/R" conflates contract asset and unbilled receivable | Configurable per contract/POB: contract asset (conditional right, 606-10-45-3) vs receivable (unconditional, 606-10-45-4) |
| FX-12 | Deferred-revenue balance assumes the ERP posts every invoice for the contract to the configured deferred account; no reconciliation | Ingest billing events with GL coding; produce a subledger-to-GL reconciliation (billings, revenue, contract asset, contract liability by contract and entity) |
| FX-13 | Reclass recompute in the prospective path omits the VC override (VR-reports-20) | One shared contract-position function for all event types |
| FX-14 | Blank memo rows silently dropped upstream (VR-reports-18) | No silent drops; row-level validation with exceptions output |
| FX-15 | Popup always says "File Saved"; files overwrite silently in the app folder; the latest export includes a pandas index column | Server-generated exports with unique names, audit log of generation, no index column |
| FX-16 | End-of-life kill switch (2025-12-31) and client-side license character test (VR-reports-15/16) | Remove; use tenant entitlements |
| FX-17 | Disclosure-only catch-up columns never reported | Contract-balance roll-forward report: opening/closing contract assets, contract liabilities, receivables; revenue from opening contract liability; revenue from POBs satisfied in prior periods (606-10-50-8 to 50-10, 50-12A) |
| FX-18 | Space-joined business key can collide (§4.2) | Surrogate IDs for contract, POB, version; display keys derived |

### 7.3 Test cases to carry forward (expected values)

Datasets:
- **"Shipped"**: the shipped `ASC606.db` state (setup 1.1 and 2.1, delivery 1.31).
- **"Full UAT"**: SSP → setup 1.1 → setup 2.1 → deliveries 1.31, 2.28, 3.31, 4.30 → retro 5.15 → POB VC 5.31 → prospective 6.15 → prospective 7.15 → retro 8.15 → prospective 9.15 → delivery 10.31, each with the date in the file name.

Amounts: + = Dr, − = Cr.

| ID | Dataset / action | Expected (legacy parity unless marked **New**) |
|---|---|---|
| TC-JE-01 | Shipped; Gross; 2023-01-01..2023-01-31 | C1 21001 +295.69; C1 POB#1 5001 −128.84; C1 POB#2 5002 −118.53; C1 POB#3 5003 −48.32; C2 15002 +58.85; C2 POB#1 5001 −58.85; no C2 21002 line; Σ 0.00 |
| TC-JE-02 | Shipped; Delta; same range | C1 21001 +141.69; 5001 −128.84; 5002 −52.53; 5003 +39.68; C2 15002 +58.85; C2 5001 −58.85; Σ 0.00 |
| TC-JE-03 | Shipped; Gross; 2023-01-01..2023-01-30 | no lines (the 2023-01-31 event is excluded; the end date is inclusive only of itself) |
| TC-JE-04 | Full UAT; Gross; 2023-04-01..2023-04-30 | C1 21001 −193.26; C1 POB#1 5001 +193.26 (return of 3 units); C2 15002 −20.00; C2 21002 +20.00 |
| TC-JE-05 | Full UAT; Gross; 2023-05-01..2023-05-31 | Legacy: C2 15002 +5.19; C2 POB#1 5001 +5.31; C2 POB#3 5003 −10.49 (Σ +0.01). **New:** full-precision UAR +5.185792, revenue POB#1 +5.305251, POB#3 −10.491049; export balanced at 2 dp with a rounding treatment per FX-01 |
| TC-JE-06 | Full UAT; Gross; 2023-02..2023-09 monthly | Feb: C1 21001 +64.42 / C1 POB#1 5001 −64.42 / C3 21001 +48.32 / C3 POB#3 5003 −48.32 / C4 21002 +111.29 / C4 POB#1 5001 −111.29. Mar: C2 15002 +46.15 / C2 POB#3 5003 −46.15 / C3 21001 +118.53 / C3 POB#2 5002 −118.53 / C4 21002 +98.93 / C4 POB#2 5002 −98.93. Jun: C1 21001 −5.30 / C1 POB#3 5003 +5.30. Jul: C3 21001 +6.99 / C3 POB#3 5003 −6.99. Aug: C3 21001 +42.10 / C3 POB#2 5002 −34.88 / C3 POB#3 5003 −7.22 / C4 21002 +16.30 / C4 POB#1 5001 −8.63 / C4 POB#2 5002 −7.67. Sep: C3 21001 +32.14 / C3 POB#3 5003 −32.14 |
| TC-JE-07 | Full UAT; Gross; 2023-10-01..2023-10-31 | C1 21001 +638.45; C1 POB#2 5002 −92.53; C1 POB#3 5003 −43.02; C1 POB#4 5001 −502.90; C2 15002 −90.19; C2 21002 +1,080.00; C2 POB#1 5001 −519.66; C2 POB#2 5002 −385.19; C2 POB#3 5003 −84.97; C3 21001 +2,351.91; C3 POB#1 5001 −678.02; C3 POB#2 5002 −311.11; C3 POB#3 5003 −94.67; C3 POB#5 5003 −1,268.11; C4 21002 +973.48; C4 POB#1 5001 −359.76; C4 POB#2 5002 −319.79; C4 POB#3 5003 −293.93 (legacy Σ −0.01; **New:** balanced) |
| TC-JE-08 | Full UAT; Gross and Delta; 2023-01-01..2023-12-31 | Gross deferred debits: C1 21001 +800.00; C2 21002 +1,100.00; C3 21001 +2,600.00; C4 21002 +1,200.00; no UAR lines. Revenue lines (gross): C1 POB#2 −211.07, POB#3 −86.03, POB#4 −502.90; C2 POB#1 −573.20, POB#2 −385.19, POB#3 −141.61; C3 POB#1 −678.02, POB#2 −464.52, POB#3 −189.34, POB#5 −1,268.11; C4 POB#1 −479.69, POB#2 −426.39, POB#3 −293.93. Delta differences: C1 21001 +646.00, C1 POB#2 −145.07, C1 POB#3 +1.97, C3 21001 +2,400.00, C3 POB#3 +10.66, C4 21002 +1,050.00, C4 POB#1 −329.69 |
| TC-JE-09 | Full UAT; Σ of monthly JEs vs full-year JE | **New:** equal per line. Legacy differs by ±0.01 on C1 POB#2 5002, C1 POB#3 5003, C3 21001, C4 POB#1 5001 |
| TC-JE-10 | Shipped + POB-specific VC with Mod Billing 0, Mod Qty 0 on C1 POB#1, dated 2023-01-31; Delta 2023-01 | **New:** identical to TC-JE-02. Legacy defect: C1 21001 −12.31; 5002 +13.47; 5003 +127.68 |
| TC-JE-11 | Shipped + C2 POB#2 delivery 1 unit dated 2023-03-31 (processed first) + C2 POB#1 billing 500 dated 2023-02-28 (processed second); Gross Feb and Mar | **New:** Feb C2 21002 +58.85 / C2 15002 −58.85 (Jan reclass reversed; position +441.15). Mar C2 21002 +104.62 / C2 POB#2 5002 −104.62; UAR 0 at both month-ends. Legacy: Feb C2 15002 −163.46 / 21002 +163.46; Mar C2 15002 +104.62 / 5002 −104.62 |
| TC-JE-12 | Shipped with C2 Unbilled A/R Account NULL; Gross 2023-01 | **New:** validation error naming the contract/POB. Legacy: C2 UAR line dropped; Σ −58.85 |
| TC-JE-13 | Shipped + Progress row C2 POB#2 (1 unit, 100 billed) with blank memos, dated 2023-02-28 | **New:** event recorded (memos optional) or explicit rejection. Legacy: success message, 0 rows appended |
| TC-JE-14 | Three revenue components of 0.335 in one contract, one period | Legacy: Deferred +1.01; each revenue −0.34; Σ −0.01. **New:** balanced (e.g. revenue −0.34, −0.34, −0.33 or a rounding line) |
| TC-JE-15 | Three revenue components of 0.004 | Legacy: empty JE (all dropped). **New:** per rounding policy (open question) |
| TC-REP-01 | Shipped; Contract History 2023-01-01..2023-01-31 | 16 rows × 71 columns (8 setup rows dated 2023-01-01, 8 delivery rows dated 2023-01-31) |
| TC-REP-02 | Shipped; specific history "Contract 2", 2023-01-01..2023-12-31 | 8 rows |
| TC-REP-03 | Shipped; Latest Contract Status all / "Contract 1" | 16 rows (C1–C2 at 2023-01-31, C3–C4 at 2023-02-01) / 4 rows |
| TC-REP-04 | Specific history with name `x" OR 1=1 OR "x` | **New:** 0 rows. Legacy: 24 rows |
| TC-REP-05 | Specific history with name `Contract "1` | **New:** 0 rows, no error. Legacy: SQL syntax error dialog |
| TC-REP-06 | Range start 2023-12-31, end 2023-01-01 | **New:** validation error. Legacy: empty export |
| TC-REP-07 | Latest "as of 2023-03-31" after the TC-JE-11 events | **New:** C2 versions effective 2023-03-31. Legacy (no as-of): Feb-dated versions, because they were processed last |

### 7.4 Open questions

| ID | Question | Why it matters |
|---|---|---|
| OQ-01 | Keep the legacy GL design (deferred revenue as the per-contract balance account, reclass to Unbilled A/R), or have eRev Cloud also post billing entries so contract assets and liabilities come from a complete subledger? | Determines whether GL tie-out is possible (FX-12) |
| OQ-02 | Split contract assets and unbilled receivables (45-3 vs 45-4) automatically from billing terms, or by manual flag? | Balance-sheet captions and 50-8(a) |
| OQ-03 | Rounding policy: half-up vs half-even (legacy uses binary-float numpy rounding: 0.125 → 0.12, 2.675 → 2.68), rounding account, carry of sub-cent residuals (TC-JE-15) | Balanced exports and parity to the cent |
| OQ-04 | JE granularity: legacy revenue lines per POB and balance-sheet lines per contract. Should the ERP export summarise by entity, account, period and dimensions, with drill-down to contract/POB? | ERP load size and audit drill-down |
| OQ-05 | Delta mode: keep pre-ASC 606 revenue as a keyed input, or derive it from ERP invoice lines; support mixed designs per tenant? | E-1, 6.2 item 6 |
| OQ-06 | Backdated activity into closed periods: catch-up in the current open period, or controlled reopen? | FX-05/FX-06 and 50-12A |
| OQ-07 | Material-right exercise default: continuation (TRG-preferred per [D11.7]) or modification (legacy UAT 9.15)? | Parity of UAT 9.15 values |
| OQ-08 | Default "Latest Contract Status": effective-dated as of today, or last processed (legacy)? | TC-REP-07 |
| OQ-09 | Multi-entity contracts: net position per contract across entities (legacy) or per entity with intercompany? | 6.2 item 7 |
| OQ-10 | Should the 71-column legacy history layout remain an export option for users' Excel subtraction workflow? | Migration comfort for legacy users |
| OQ-11 | Keep the "price inside ±range = SSP, else nearer bound" method as a tenant option alongside midpoint and residual approaches? No public source on range practice was retrieved this session | Engine SSP options |

