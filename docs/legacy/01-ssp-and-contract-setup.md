# Legacy eRev: SSP Upload, Contract Setup, Premium Gating and Database Functions

| Field | Value |
|---|---|
| Source | `~/dev/erev-legacy/eRev.py` lines 1–825 (plus shared state skimmed at 826–1170, 1280–1400, 2540–2670, 2784–2862, 3077–3218) |
| Legacy commit | `5ec25ff` (Update README.md) |
| Templates | `ops/Blank Templates/SKU SSP Template.xlsx`, `ops/Blank Templates/Contract Setup Template.xlsx` |
| UAT files | `ops/Example UATs/SSP Upload UAT/SKU SSP Template.xlsx`; `ops/Example UATs/Contract Setup UAT/Contract Setup Template 1.1.2023.xlsx` and `... 2.1.2023.xlsx` |
| Legacy DB | `ops/libnew/libwarm/db/ASC606.db` (`SKU_SSP` 7 rows, `Contract_Live` 24 rows; rows 1–16 come from the two setup UAT files, rows 17–24 from a 2023-01-31 delivery/billing run) |
| Verification | Headless harness `~/dev/erev/.scratch/legacy-setup/harness.py` runs the legacy source unchanged with PySide6 stubbed (pandas 2.2.3, the version current when the legacy DB was written, 2025-05-09). It reproduces legacy DB rows 1–16 exactly (see Section 5.4) |
| Status | Draft for engine design |

Conventions in this document: `L123` means eRev.py line 123. "Fact" means observed in code or harness output. "Inference" is marked as such.

---

## 1. Purpose, triggers, inputs and outputs

### 1.1 Application shell (`FileBrowserWindow.__init__`, L17–263)

The whole product is a single fixed 800x800 window (L25) titled "ASC606 & IFRS15 Revenue System by Chipmunk Robotics ©2024" (L21). Buttons are grouped under four bold headings. The code lays them out in this order: Contract Operations, Mod Operations, Journals and Reporting, Premium Database Functions (L71–213). Each button calls one handler through a lambda (L230–243).

| # | Group (on-screen order) | Button label (exact) | Attribute | Handler | In scope here |
|---|---|---|---|---|---|
| 1 | Contract Operations | Load SSPs | `button1` | `browse_file_SSPs` (L534) | Yes |
| 2 | Contract Operations | Load Contracts | `button2` | `browse_file_Contracts` (L621) | Yes |
| 3 | Contract Operations | Load Delivery and Billing | `button3` | `browse_file_Deliveries` (L826) | Shared state only |
| 4 | Mod Operations | Prospective Contract Mod | `button4` | `browse_file_ProsMod` (L1170) | No |
| 5 | Mod Operations | Retrospective Contract Mod | `button5` | `browse_file_RetroMod` (L1655) | No |
| 6 | Mod Operations | POB Specific VC | `button5_1` | `browse_file_POB_specific_VC` (L2133) | No |
| 7 | Journals and Reporting | Revenue Journal Entries | `button9` | `show_custom_dialog` (L3013) | Shared state only |
| 8 | Journals and Reporting | Contract History | `button10` | `show_contract_dialog` (L3017) | No |
| 9 | Journals and Reporting | Latest Contract Status | `button11` | `show_latest_contract_dialog` (L3021) | Shared state only |
| 10 | Premium Database Functions | Backup Database | `button6` | `db_backup` (L293) | Yes |
| 11 | Premium Database Functions | Restore from Backup | `button7` | `db_restore` (L330) | Yes |
| 12 | Premium Database Functions | !Reset Database Completely! | `button8` | `db_reset` (L375) | Yes |
| 13 | Premium Database Functions | Append from Another | `button8_1` | `db_another` (L404) | Yes |
| 14 | Premium Database Functions | Purge Contracts | `button8_2` | `db_purge_contract` (L477) | Yes |

Fact: the UI has **14** buttons. The README still says "only 13 buttons" (README L7). Its own list is 6 template buttons + 3 reporting buttons + 5 database buttons (README L17, L51, L81), which is 14. The `button5_1` / `button8_1` / `button8_2` names suggest those buttons were added later (inference).

Other shell elements: a title image, two external links (chipmunkrpa.com, chipmunkrpa.com/erev), a copyright label and a background image (L32–64, L245–253). Every data path in the app is relative to the working directory (`ops/libnew/libwarm/db/ASC606.db`), so the app only works when started from the repo root.

Shared lifecycle state outside the scope lines: the `__main__` block (L3208–3218) creates a `ShutdownNotifier` with a hard-coded end-of-life of 2025-12-31 23:59. A `QTimer` checks every 60,000 ms (the comment says "every second"), shows "End of Life Notification" and calls `QApplication.quit()` (L3077–3102).

### 1.2 Premium gating (`load_license_key` L265–276, `show_notification_and_disable` L278–291, `LicenseKeyDialog` L3175–3205)

| Step | Behaviour | Lines |
|---|---|---|
| 1 | `load_dotenv()` loads `.env` from the working directory. It reads `os.getenv('Chipmunk_License_Key')`. | L267–268 |
| 2 | If the key is empty or unset, it opens the modal `LicenseKeyDialog`, prompting "Enter your Chipmunk Premium License Key or enter anything to use the free version:" (password echo). **Save** with text overwrites the entire `.env` with `Chipmunk_License_Key=<text>` and shows "Success" / "Chipmunk_License_Key saved successfully!". **Save** with empty text shows warning "Error" / "Chipmunk_License_Key cannot be empty." It then calls `load_dotenv()` again and returns the key, or `None` if the dialog was closed. | L269–274, L3197–3205 |
| 3 | Validation is positional: premium only if `key[2]=="r" and key[5]=="s" and key[9]=="y" and key[15]=="s"`. Any exception (None key, key shorter than 16 characters) is treated as a failure. | L258–263 |
| 4 | On failure it shows the information box "Notice for the Premium Database Functions": "Premium license key is not found. \nIf required, contact support for assistance support@chipmunkrpa.com\n\nNormal ASC606 Functions are still free to use." It then disables `button6`, `button7`, `button8`, `button8_1` and `button8_2` (all five database buttons). | L278–291 |

Assessment: the gate is client-side obfuscation, not licensing. Any 16-character string with r/s/y/s at positions 2/5/9/15 unlocks premium (harness confirms `"xxrxxsxxxyxxxxxs"` passes). The key is stored in plaintext in `.env`. The rebuild must not carry this forward. It should become server-side entitlements per tenant/plan (Section 7).

### 1.3 Load SSPs (`browse_file_SSPs`, L534–619)

**Trigger.** Button "Load SSPs" (L97, L230). A file dialog titled "Select File" has no file-type filter (L535–536). Cancel returns an empty path and does nothing (L539).

**Input.** `pd.read_excel(file_path)` reads the **first worksheet only**, with row 1 as headers (L540). In the template that sheet is `SKU Setup`. There is no row-level typing: pandas infers dtypes per column.

| Column (exact header) | UAT example | Legacy type after read | Validation in code | Practically required? | How used |
|---|---|---|---|---|---|
| SKU Unique ID | 1 | int64 | Header only | No | Carried to `Contract_Live`. Never used as a key |
| SKU Name | Hardware 1 | text | Header only | Yes (join key) | Join key 1 of 3 at contract setup (L678) |
| Distinct or Nondistinct | Distinct / Nondistinct | text | Header only. The value is not checked | No at setup | Carried to `Contract_Live`. Later handlers use it to choose prospective vs cumulative catch-up treatment (see Section 3.9) |
| SKU Unit List Price | 100 | int64 | `pd.to_numeric(errors='raise')` (L566). Blanks pass | Yes (a blank gives NaN SSP) | SSP range base |
| ASC 606 Stratification | Hardware 1, VC | text | Header only | Yes (join key) | Join key 2 of 3. The literal `VC` is a magic value in later handlers (L961, L1089) |
| Midpoint Discount Percentage | 0.1 (Excel format 0%) | float64 | Numeric only. No 0–1 range check | Yes | SSP midpoint discount |
| SSP Range Method (+-) | 0.15 (Excel format 0%) | float64 | Numeric only. No range check | Yes | +/- band around the midpoint |
| SSP Version | 2023-01-01 (Excel date) | datetime64, then `astype(str)` gives `"2023-01-01"` (L574) | Header only | Yes (join key) | Join key 3 of 3 |
| Revenue Account | 5001 | int64 | Header only | No at setup | Revenue account used for journal entries (L2604) |

**Outputs.**

| Output | Detail | Lines |
|---|---|---|
| DB table `SKU_SSP` | Whole-table **replace** (`if_exists="replace"`) with the 9 uploaded columns in file order. There is no append, no merge and no history. Column affinities come from pandas dtypes (legacy schema: INTEGER, TEXT, TEXT, INTEGER, TEXT, REAL, REAL, TEXT, INTEGER). | L576–579 |
| File encryption | Tries Windows EFS `EncryptFileW` on the DB file. All failures are silently ignored, including on non-Windows systems and non-NTFS volumes. | L582–607 |
| Popup (success) | "SSPs are set up" / "All company SSPs for the uploaded file are set up. To add or update, re-upload SSPs to refresh." | L609–610 |
| Excel files | None | n/a |

### 1.4 Load Contracts, i.e. contract setup and initial allocation (`browse_file_Contracts`, L621–824)

**Trigger.** Button "Load Contracts" (L103, L231). A file dialog titled "Select File" has no filter. Cancel does nothing (L626).

**Input.** The first worksheet of the Contract Setup template (sheet `Sheet1`), with one row per performance obligation (POB). There is no period prompt: `Current Period` comes from each row of the file.

| Column (exact header) | UAT example | Type after read | Validation in code | Practically required? | How used |
|---|---|---|---|---|---|
| Contract Unique Name | Contract 1 | text | Header only | Yes | Allocation group key (L704–708). Part of the record key (L758–762). A numeric value raises TypeError, which is swallowed (VR-setup-10) |
| POB Unique ID | POB #1, VC #1 | text | Header only | Yes | Part of the record key. The same numeric-value TypeError applies |
| SKU Name | Hardware 1 | text | Header only | Yes | SSP join key |
| POB Start Date | 2023-01-01 | datetime | None | No at setup | Stored only. Mod handlers can overwrite it |
| POB End Date | 2023-12-31 | datetime | None, and end >= start is not checked | No at setup | Stored only |
| ASC 606 Stratification | Hardware 1, VC | text | Header only | Yes | SSP join key. `VC` is a magic value later |
| Original POB Total Selling Price | 500, 0, -100 | int64 or float | Numeric (L656). Blanks pass | Yes | Contract price per POB. Summed into the transaction price |
| Original POB Total Qty | 5, 1000 | int64 or float | Numeric. Blanks pass | Yes | SSP range base and unit denominators |
| Selling Entity | Mock Entity 1 | text | Header only | No | Stored only. Not part of the allocation group |
| SSP Version | 2023-01-01 | datetime, then `astype(str)` (L664) | Header only | Yes | SSP join key |
| Deferred Revenue Account | 21001 | int64 | Header only | No at setup | Journal entry deferred revenue account |
| Unbilled A/R Account | 15001 | int64 | Header only | No at setup | Journal entry contract asset account |
| Current Period | 2023-01-01 | datetime | None | Yes for reporting (journal entries filter on it, L2574–2576) | Setup version date |
| Memo 1 / Memo 2 / Memo 3 | Initial setup 1 | text | Header only | No | Carried forward. Later uploads overwrite them when they supply values |

**Outputs.**

| Output | Detail | Lines |
|---|---|---|
| DB table `Contract_Live` | **Append** one row per uploaded POB (or create the table with `if_exists="replace"` if it does not exist). 71 columns: the 16 input columns, 6 attributes from `SKU_SSP` (`SKU Unique ID`, `Distinct or Nondistinct`, `SKU Unit List Price`, `Midpoint Discount Percentage`, `SSP Range Method (+-)`, `Revenue Account`), 9 "Original" computed columns, 16 "Previous" columns, 21 "Current" columns (21 plus the input `Current Period` gives 22 period-state columns), then `Processing Time Log`, `Record Unique ID without time` and `Record Unique ID`. Rows are sorted by `Record Unique ID without time` before writing (L782). Column affinities are fixed by the dtypes of the first upload that created the table. | L776–813 |
| DB table `SKU_SSP` | Read only | L667–674 |
| File encryption | Not attempted in this handler (inference: the DB was already encrypted by SSP load). | n/a |
| Popup (success) | "Contracts are set up" / "All contracts(s) within the uploaded file are successfully set up!" | L815–816 |
| Popup (failure) | See VR-setup table (Section 2) | L642–660, L764–773, L819–824 |
| Excel files | None | n/a |

### 1.5 Premium database functions (L293–532)

| Function | Trigger | Inputs | Effect | Popups (exact) | Lines |
|---|---|---|---|---|---|
| `db_backup` | "Backup Database" | None | `shutil.copyfile` of the live DB to `ops/libnew/libwarm/db/backup db/ASC606.db`. One slot, overwritten each time. Best-effort EFS encryption of the copy. | Success: "ASC606 database backup" / "ASC606 Database has been successfully backed up." Error: "Error Notification" / `str(e)` | L293–328 |
| `db_restore` | "Restore from Backup" | None, and no confirmation | **Deletes the live DB first** (`os.remove`, FileNotFoundError ignored), then copies the backup over it. Best-effort EFS. | Success: "ASC606 database restore" / "ASC606 Database has been restored using the backup file." Error: "Error Notification" / `str(e)` | L330–373 |
| `db_reset` | "!Reset Database Completely!" | Yes/No confirmation "Confirmation" / "Do you want to proceed wiping out the current database?" (default No) | `DROP TABLE IF EXISTS` on **every** table, including `SKU_SSP`. | "ASC606 database reset" / "ASC606 Database has been wiped out and reset!" Error: "Error Notification" / `str(e)` | L375–402 |
| `db_another` | "Append from Another" | File dialog "Select File" (any SQLite file) | `SELECT *` from the source `Contract_Live`, then **positional** `INSERT INTO "Contract_Live" VALUES (?, ...)` into the live DB. No dedupe, no schema check, no transaction boundary beyond commit. Best-effort EFS. | "ASC606 database appended" / "ASC606 Database has been appended with the new dataset from the database selected!" Error: "Error Notification" / `str(e)` | L404–475 |
| `db_purge_contract` | "Purge Contracts" | Three `QInputDialog` prompts: start date (YYYY-MM-DD), end date, contract unique name | `DELETE FROM "Contract_Live" WHERE "Contract Unique Name" = "{name}" AND "Current Period" BETWEEN "{start}" AND "{end}"`. Built with an f-string: string interpolation, no parameters, no confirmation. | Invalid date: warning "Invalid Date" / "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." Success: "Contract Records Purged" / "The contract records within the periods selected are successfully purged from the database." Error: "Error Notification" / `str(e)` | L477–532 |

---

## 2. Validation rules

Type legend: **E** = explicit check in code; **I** = implicit (enforced only because a library call throws); **G** = guard or branch. "Harness" lists the scenario in `.scratch/legacy-setup/harness.py` (output in `harness.log`) that exercised the rule. Popups are written as type / title / text.

### 2.1 Rule table

| ID | Handler | Type | Exact condition | Popup(s) | Effect | Lines | Harness |
|---|---|---|---|---|---|---|---|
| VR-setup-01 | Load SSPs | G | `file_path` is empty (dialog cancelled) | None | No-op | L535–539 | n/a |
| VR-setup-02 | Load SSPs | E | `missing_titles or extra_titles`. Expected = `SKU Unique ID, SKU Name, Distinct or Nondistinct, SKU Unit List Price, ASC 606 Stratification, Midpoint Discount Percentage, SSP Range Method (+-), SSP Version, Revenue Account`. Headers must match exactly (case- and whitespace-sensitive). Order is ignored. Only the first worksheet is read | information / "File Upload Error" / "Error: The Excel file has incorrect or missing column titles."; then, if any are missing, information / "Missing fields:" / comma-joined list; then, if any are extra, information / "Extra fields:" / comma-joined list | Stop. `SKU_SSP` untouched | L543–558 | S04 (`SSP version` lower-case gives missing `SSP Version` + extra `SSP version`) |
| VR-setup-03 | Load SSPs | E | For `SKU Unit List Price`, then `Midpoint Discount Percentage`, then `SSP Range Method (+-)`: `pd.to_numeric(df[col], errors='raise')` raises ValueError/TypeError. The loop stops at the first failing column. The coerced result is discarded, but `read_excel` has already turned numeric-looking text into numbers. **Blank cells (NaN) pass.** No range checks | information / "Format Error" / "Error: The column '{column}' should contain numeric values." | Stop | L549–570 | S05 (`10%` typed as text fails); S06b (blank list price passes); S23 (discount `10` = 1000% passes) |
| VR-setup-04 | Load SSPs | I | Any other exception. A `TypeError` outside the numeric loop is swallowed without a popup | critical / "Error Notification" / `str(e)`; TypeError: none | Stop | L612–619 | n/a |
| VR-setup-05 | Load Contracts | G | `file_path` is empty | None | No-op | L622–626 | n/a |
| VR-setup-06 | Load Contracts | E | `missing_titles or extra_titles` against the 16 titles in Section 1.4, with the same exact-match semantics as VR-setup-02 | Same three popups as VR-setup-02 | Stop. Nothing written | L630–648 | S04 (extra `Notes` + missing `Memo 3`; `Memo 1 ` with a trailing space) |
| VR-setup-07 | Load Contracts | E | Numeric check on `Original POB Total Selling Price`, then `Original POB Total Qty`, with the same semantics as VR-setup-03 (blanks pass) | information / "Format Error" / "Error: The column '{column}' should contain numeric values." | Stop | L639–660 | S05 (`abc` fails); S06 (blank price and blank qty pass, giving NaN allocations) |
| VR-setup-08 | Load Contracts | I | Table `SKU_SSP` must exist | critical / "Error Notification" / "Execution failed on sql '… SELECT * FROM "SKU_SSP" …': no such table: SKU_SSP" | Stop | L667–674, L819–824 | S03 |
| VR-setup-09 | Load Contracts | E | Every uploaded row must match at least one `SKU_SSP` row on exact string equality of `SKU Name`, `ASC 606 Stratification` and `SSP Version` (both sides `astype(str)`). Detected as `_merge == 'left_only'`. It runs after all columns are computed and before any DB write, so the whole file is rejected | information / "Contract Error" / "Those POBs below are not matched with a SKU within the SKU databse. Re-upload the file after fixes! \n '{unmatched SKU Names joined by ','}'"; then critical / "Error Notification" / "The process is stopped for users to fix the file" | Stop. Nothing written | L676–679, L764–773 | S02 (empty SSP table); S09 (version typing drift: `1.0` vs `1`; time component); S10 (a stratification mismatch is still reported by SKU Name); S22 (version removed by SSP re-upload) |
| VR-setup-10 | Load Contracts | I | `Contract Unique Name`, `POB Unique ID` and `SKU Name` must be text because the record key is built with `+ " " +`. A numeric column raises `TypeError`, and the handler-level `except TypeError: pass` swallows it | **None (silent failure)** | Stop. Nothing written. The user gets no feedback | L758–762, L817–818 | S11 (numeric POB IDs; numeric contract names) |
| VR-setup-11 | Load Contracts | I | Any other exception. DB writes are the last step, so a failure leaves no partial writes | critical / "Error Notification" / `str(e)` | Stop | L819–824 | n/a |
| VR-setup-12 | Premium gate | E | Premium only if `key[2]=="r" and key[5]=="s" and key[9]=="y" and key[15]=="s"`. Any exception (key `None` or shorter than 16 characters) fails | information / "Notice for the Premium Database Functions" / "Premium license key is not found. \nIf required, contact support for assistance support@chipmunkrpa.com\n\nNormal ASC606 Functions are still free to use." | Disables Backup, Restore, Reset, Append, Purge | L256–263, L278–291 | License block (`xxrxxsxxxyxxxxxs` gives premium) |
| VR-setup-13 | License dialog | E | `api_key` is empty on Save | warning / "Error" / "Chipmunk_License_Key cannot be empty."; success: information / "Success" / "Chipmunk_License_Key saved successfully!" | Dialog stays open, or `.env` is overwritten | L3197–3205 | n/a |
| VR-setup-14 | Backup | I | Directory `ops/libnew/libwarm/db/backup db/` must exist. The code never creates it and the repo does not contain it | critical / "Error Notification" / "[Errno 2] No such file or directory: 'ops/libnew/libwarm/db/backup db/ASC606.db'" | No backup | L295, L327–328 | S19 |
| VR-setup-15 | Restore | I | The backup file must exist, but this is only checked **after** the live DB has been deleted. No confirmation | critical / "Error Notification" / "[Errno 2] No such file or directory: 'ops/libnew/libwarm/db/backup db/ASC606.db'" | **Live DB deleted and nothing restored (data loss)** | L333–339, L372–373 | S18 |
| VR-setup-16 | Reset | E | `QMessageBox.question` "Confirmation" / "Do you want to proceed wiping out the current database?" answered Yes (default No) | information / "ASC606 database reset" / "ASC606 Database has been wiped out and reset!" | Drops **all** tables, including `SKU_SSP` | L378–395 | S21 |
| VR-setup-17 | Append from Another | G/I | Cancel is a no-op. The source must be SQLite ("file is not a database") and have `Contract_Live` with at least one row (`data[0]` gives "list index out of range"). The destination must have `Contract_Live` ("no such table: Contract_Live"). The insert is positional, so the column count and **order** must match; column order follows the header order of whichever setup file created the table (S04) | critical / "Error Notification" / `str(e)` | Stop | L406–425, L467–475 | S17, S17b–d |
| VR-setup-18 | Purge | E | Start date must satisfy `QDate.fromString(text, "yyyy-MM-dd").isValid()`. Cancel is a no-op | warning / "Invalid Date" / "Invalid date format. Please enter a valid date in the format 'YYYY-MM-DD'." | Stop | L479–485 | S20 (`2023/01/01`) |
| VR-setup-19 | Purge | E | End date is valid. Cancel is a no-op. Start <= end is **not** checked | Same warning | Stop | L487–493 | S20 (a reversed range deletes 0 rows and still shows the success popup) |
| VR-setup-20 | Purge | None | Contract name is not validated, and the `ok` flag is ignored (Cancel still runs `DELETE` with an empty name). The name is interpolated into double quotes: a `"` breaks the SQL, and a name equal to a column name (e.g. `Memo 1`) is resolved as a column identifier | exec / "Contract Records Purged" / "The contract records within the periods selected are successfully purged from the database." (**even when 0 rows are deleted**); syntax error: critical / "Error Notification" / `near "2": syntax error` | DELETE | L495–525 | S20, S20b |

### 2.2 Validations that do not exist at setup (harness-verified)

The README claims "user-input validations over dates, contents, and formats" (README L65). The setup path has none of the following:

| # | Missing check | Observed consequence | Harness |
|---|---|---|---|
| M-01 | Date typing and ordering (`POB Start Date`, `POB End Date`, `Current Period`) | `Current Period = "abc"` is stored as text. End date before start date is accepted. A blank `Current Period` gives NULL, and the journal entry date filter (L2574–2576) silently skips the row | S26 |
| M-02 | Blank numeric cells | NaN price leaves that POB's SSP and allocation NaN, and the rest of the contract absorbs the whole transaction price. NaN qty makes SSP equal the price (no band) and unit values NaN | S06 |
| M-03 | Blank list price in `SKU_SSP` | Band is NaN, so SSP = stated price with no clamp | S06b |
| M-04 | Duplicate SSP key (SKU Name + Stratification + Version) | Left join fans out: the POB row is duplicated, and transaction price and total SSP are double-counted (Contract 1 total price becomes 1,800 instead of 1,300) | S08 |
| M-05 | Duplicate POB key within a file | Both rows are written with the same `Record Unique ID`. Totals double-count. Latest-version SQL returns both rows | S16 |
| M-06 | Contract already exists in DB | A new setup version is appended, becomes "latest", and resets every cumulative field to 0 while the history rows remain | S14 |
| M-07 | Contract split across uploads | Each upload allocates independently (no contract combination) | S15 |
| M-08 | Percent sanity (0 <= d < 1, r >= 0) | Discount typed as `10` gives midpoint -4,500, total SSP -70,482 and inverted allocation signs | S23 |
| M-09 | Quantity != 0 | Unit SSP and unit revenue rate become NaN (0/0) and are stored as NULL | S13 |
| M-10 | Total contract SSP != 0 | All-VC contract gives NaN allocation | S12 |
| M-11 | Sign-aware SSP band for negative quantities | Price -90 inside band [-103.5, -76.5] is clamped to -103.5 | S07 |
| M-12 | Domain of `Distinct or Nondistinct` and of `ASC 606 Stratification = "VC"` | Any text is accepted. A typo silently disables mod-time catch-up (L1521–1523) or VC exclusions (L961, L1089) | Code |
| M-13 | Accounts populated or valid; entity/currency | Not checked | Code |
| M-14 | Stratification consistency between contract and SKU beyond the join; delimiter-safe keys | `"A B" + "C"` and `"A" + "B C"` produce the same `Record Unique ID without time` | Code (L758–760) |

---

## 3. Calculation logic (contract setup)

### 3.1 Notation

For each uploaded POB row *i* in contract group *c*: *P* = `Original POB Total Selling Price`, *Q* = `Original POB Total Qty`, *L* = `SKU Unit List Price`, *d* = `Midpoint Discount Percentage`, *r* = `SSP Range Method (+-)`. *c* is the set of rows **in the same uploaded file** with equal `Contract Unique Name` (L704–708).

### 3.2 SSP lookup (L664–679)

```text
contract.SSP_Version := str(contract.SSP_Version)            # L664: datetime 2023-01-01 -> "2023-01-01"
SKU_SSP.SSP_Version  := str(SKU_SSP.SSP_Version) at upload   # L574
merged := contract LEFT JOIN SKU_SSP
          ON (SKU Name, ASC 606 Stratification, SSP Version)  # exact, case-sensitive string equality
```

Typing hazards (S09): `astype(str)` renders an all-midnight datetime column as `YYYY-MM-DD`, but renders every cell as `YYYY-MM-DD HH:MM:SS` if any cell has a time. A numeric version column containing a blank becomes float, so the version is stored as `"1.0"` and blanks as `"nan"`. The `_right_table` suffix drop (L776–777) is a no-op because non-key SSP columns never collide with contract columns. `_merge` is dropped (L778–779). SSP attributes are **copied** into `Contract_Live` (denormalised snapshot), so a later SSP re-upload does not change existing contracts.

### 3.3 SSP band (L682–689). Extended (quantity-scaled) amounts

```text
Original SSP - Midpoint = Q × L × (1 − d)                 # stored; never read again (only occurrence L682)
Original SSP - Higher   = Q × L × (1 − d) × (1 + r)
Original SSP - Lower    = Q × L × (1 − d) × (1 − r)
```

### 3.4 Extended SSP selection (`compare_columns`, L692–700)

```text
if   P > Higher: Original Extended SSP = Higher
elif P < Lower:  Original Extended SSP = Lower
else:            Original Extended SSP = P               # inclusive band: stated price is the SSP
```

| Case | Behaviour | Evidence |
|---|---|---|
| Price inside `[Lower, Higher]` | SSP = stated price | UAT Contract 1 POB #1: 500 in [382.5, 517.5] gives 500 |
| Price above band | Clamp to **Higher** (the boundary, not the midpoint) | Contract 1 POB #2: 400 > 368 gives 368 |
| Price below band | Clamp to **Lower** | Contract 2 POB #1: 600 < 612 gives 612 |
| Price on a boundary | Price kept (inclusive) | S31: 517.5 gives 517.5; 272 gives 272 |
| Zero-width band (r = 0) | SSP = Q × L × (1 − d) | Consulting 1: 150 |
| $0 stated price | Clamp up to Lower, so the free POB still receives an allocation | Contract 2 POB #3: 0 gives 150 |
| Material right SKU (L = 1, d = 0, r = 0) | SSP = Q. The quantity field carries the option's SSP in $1 units (inference: user convention) | Contract 1 POB #4: Q 1,000 gives SSP 1,000 |
| VC SKU (L = 0) | Band [0, 0], so SSP = 0 whatever the sign of P | Contract 2 VC #1: -100 gives 0; S12 positive VC +100 gives 0 |
| Negative Q (return line) | Band inverts (Higher < Lower). A price inside the band hits the first branch and is clamped to Higher. **Defect.** The prospective-mod handler has a sign-aware branch (L1314–1328), setup does not | S07: P -90, band [-103.5, -76.5], SSP -103.5 |
| P = NaN | Both comparisons False, so SSP = NaN | S06 |
| Band = NaN (blank Q, L, d or r) | Both comparisons False, so SSP = P | S06, S06b |

### 3.5 Transaction price, allocation and unit rates (L704–717)

```text
Original Total Contract Price  TP_c   = Σ_{i∈c} P_i                     # groupby transform('sum'); NaN skipped
Original Total Contract SSP    TSSP_c = Σ_{i∈c} SSP_i
Original Allocation            A_i    = SSP_i / TSSP_c × TP_c
Original Unit SSP                     = SSP_i / Q_i
Original Unit Rev Rec                 = A_i / Q_i
```

| Topic | Legacy behaviour | Lines / evidence |
|---|---|---|
| Discount or premium | TP − TSSP is spread proportionally across **every** row of the contract, including $0-price POBs and material rights. There is no path at setup for allocating a discount to specific POBs | L710–711 |
| Variable consideration | A `VC` row adds its stated amount (negative or positive) to TP. With SSP 0 it receives 0 allocation, so the VC is spread proportionally over all other POBs. No estimate or constraint is computed: the user types the VC amount | UAT Contract 2: TP 900 = 600 + 400 + 0 − 100 |
| Residual approach | Not supported | n/a |
| Rounding | None at setup. float64 end to end, stored REAL. Σ A_i = TP_c to floating-point precision (harness residual 0.0 for all four UAT contracts). Rounding happens only in journal entries: `round(4)` per line, lines with `round(2) == 0` dropped, grouped by key and account, then `round(2)` (L2598–2651). No penny-residual plug, so JE revenue lines can differ from the allocation by cents | S01 |
| int vs float | *P*, *Q* and `Original Total Contract Price` stay int64 when the columns have no blanks or decimals. Everything derived is float. SQLite column affinities are frozen by the first upload that creates `Contract_Live` (legacy schema: INTEGER for P, Q, TP and every zero-initialised cumulative or position field; REAL for SSP and allocation fields). Later decimals are stored as REAL inside INTEGER-affinity columns without truncation | L807, L812; S30 (399.99 stored as real) |
| Division by zero | TSSP_c = 0 gives A = NaN, stored NULL. Q = 0 gives unit values NaN (0/0) or ±inf | S12, S13 |
| Group key | `Contract Unique Name` only, **within one upload**. `Selling Entity` is ignored, which allows cross-entity allocation (README L59). A contract split across uploads is allocated twice, independently | S15 |
| Sign convention | Revenue and billing are positive. Return or credit rows carry negative P, SSP and A | S07 |

### 3.6 Initial roll-forward state written at setup (L719–757)

| Column(s) | Setup value |
|---|---|
| `Previous Period` | NaT (NULL) |
| `Previous Remaining Qty`, `Current Remaining Qty` | *Q* |
| `Previous Remaining SSP`, `Current Remaining SSP` | `Original Extended SSP` |
| `Previous Remaining Allocation`, `Current Remaining Allocation` | `Original Allocation` |
| `Previous Remaining Billing`, `Current Remaining Billing` | *P*. The unbilled amount starts at the stated price, so the billing plan equals the stated POB price, VC rows included (e.g. −100) |
| `Previous Unit SSP`, `Current Unit SSP` | `Original Unit SSP` |
| `Previous Remaining Unit Rev Rec`, `Current Remaining Unit Rev Rec` | `Original Unit Rev Rec` |
| Every `Previous … - Cumulative` field (Delivery, Rev Rec, Pre-ASC606 Revenue (Net Design Only), Billing, Cumulative Catchup - Disclosure Only, SSP Delivered) | 0 |
| `Previous Contract Position - POB`, `Previous Contract Position - Contract Level`, `Previous Reclass to UAR` | 0 |
| `Current Delivery`, `Current Rev Rec`, `Current Pre-ASC606 Revenue (Net Design Only)`, `Current Billing`, `Current Cumulative Catchup - Disclosure Only`, `Current SSP Delivered` and each `- Cumulative` version | 0 |
| `Current Contract Position - POB`, `Current Contract Position - Contract Level`, `Current Reclass to UAR` | 0 |
| `Processing Time Log` | `pd.Timestamp.now()`, evaluated once for the whole upload (naive local time, microseconds) |

### 3.7 How later events consume the setup state (shared state; skimmed from `browse_file_Deliveries` L980–1089 and the prospective mod L1520–1549)

These formulas give the zero-initialised setup fields their meaning. The full delivery and modification specifications belong to the companion documents.

```text
# delivery/billing event at user-entered Current Period (L1011–1089)
Previous_* := Current_* of latest version; Previous Period := Current Period
Current Rev Rec          = Delivery × Current Remaining Unit Rev Rec                 # L1028
Current SSP Delivered    = Delivery × Current Unit SSP                               # L1030
Remaining Qty           -= Delivery;  Remaining SSP -= Delivery × Unit SSP           # L1032–1036
Remaining Allocation    -= Current Rev Rec;  Remaining Billing -= Current Billing    # L1037–1042
Current Unit SSP         = Remaining SSP / Remaining Qty            (NaN -> 0)       # L1045
Current Remaining Unit Rev Rec = Remaining Allocation / Remaining Qty (NaN -> 0)     # L1048
each *_Cumulative       += current amount                                            # L1053–1072
Contract Position - POB  = Billing Cum − Rev Rec Cum     # + deferred revenue (liability); − revenue ahead of billing
Contract Position - Contract Level = Σ_c Contract Position - POB                     # L1076
Reclass to UAR_i         = −CP_contract × SSPDeliveredCum_i / Σ_c SSPDeliveredCum  if CP_contract < 0 else 0
Reclass to UAR (VC rows) = 0                                                         # L1081–1089
Pre-ASC606 Revenue (Net Design Only): user-supplied per upload, accumulated only; feeds journal_entries_delta (L2862+)
Cumulative Catchup - Disclosure Only: 0 at setup and delivery; for Nondistinct rows in a mod (L1526–1540):
    should_be = DeliveredCum / (DeliveredCum + RemainingQty) × (RevRecCum + RemainingAllocation)
    catch-up  = should_be − RevRecCum
```

Journal entries (L2594–2651) use debit-positive, credit-negative amounts:

| Line | Account | Amount |
|---|---|---|
| Recognise revenue | Deferred Revenue | +Current Rev Rec |
| Recognise revenue | Revenue | −Current Rev Rec |
| Reverse prior reclass | Deferred Revenue | +Previous Reclass to UAR |
| Reverse prior reclass | Unbilled A/R | −Previous Reclass to UAR |
| Book new reclass | Deferred Revenue | −Current Reclass to UAR |
| Book new reclass | Unbilled A/R | +Current Reclass to UAR |

Deferred revenue and unbilled A/R lines are keyed by contract; revenue lines by POB key. No billing entry is generated. Inference: the ERP posts invoices (Dr A/R, Cr Deferred Revenue) and eRev only moves amounts between deferred revenue, unbilled A/R and revenue.

---

## 4. State transitions and versioning

### 4.1 Model

`Contract_Live` is an **append-only snapshot log**. Each processing event writes a complete 71-column row per POB for every affected contract. Nothing is updated in place. Rows are removed only by Purge (range delete), by Reset (table drop) or by Restore (the whole file is replaced). The table has no primary key, no unique index and no foreign keys (legacy schema).

### 4.2 Identity fields

| Field | Formula | Lines | Meaning / hazard |
|---|---|---|---|
| `Record Unique ID without time` | `Contract Unique Name + " " + POB Unique ID + " " + SKU Name` | L758–760 | Logical POB identity. The unescaped space delimiter can collide (M-14). Changing a SKU on a POB creates a new logical POB |
| `Processing Time Log` | `pd.Timestamp.now()`, once per upload | L757 | Version timestamp. Naive local time stored as TEXT `YYYY-MM-DD HH:MM:SS.ffffff`, so lexicographic order equals chronological order. S01 shows one distinct timestamp per upload. No user identity is recorded |
| `Record Unique ID` | `str(Processing Time Log) + " " + Record Unique ID without time` | L761–762 | Version identity (not enforced unique) |
| `Current Period` | Template value at setup; user prompt at delivery (L1025); mod date in mods (L1398) | L630–635 | Accounting date of the version |
| `Previous Period` | NULL at setup; prior version's `Current Period` afterwards (L1009, L1397) | L720 | Points to a date, not to a version ID |

### 4.3 Latest-version resolution (L882–902, L2787–2803)

```sql
SELECT t1.* FROM Contract_Live t1
JOIN (SELECT "Record Unique ID without time", MAX("Processing Time Log") AS max_timestamp
      FROM Contract_Live GROUP BY "Record Unique ID without time") t2
  ON t1."Record Unique ID without time" = t2."Record Unique ID without time"
 AND t1."Processing Time Log" = t2.max_timestamp;
-- then pandas groupby(...).idxmax() keeps the first row per logical key
```

Consequences (code-derived unless a harness scenario is listed):

1. "Latest" means the **most recently processed** version, not the latest accounting date. A back-dated event processed later becomes the base for every subsequent event. There is no period lock (the README presents this as a feature, README L67).
2. Rows sharing a timestamp and key appear twice in the SQL result. Pandas keeps the first and silently drops the other (S16: 5 rows returned for 4 logical POBs; S17: 48 rows for 16 keys after two appends).
3. The journal entry report reads **all** rows in the date range (L2559–2576), so duplicated versions double-count revenue.

### 4.4 Transitions

| Event | Precondition | Rows written | `Previous_*` | `Current_*` | Lines / evidence |
|---|---|---|---|---|---|
| First contract setup | `Contract_Live` absent | Table created from the DataFrame (`replace`). Column order = setup-file header order plus the derived columns | Original values; `Previous Period` NULL | Original values; all activity and cumulative fields 0 | L785–813; S04 (column order) |
| Later setup | Table exists | Append | Same | Same | L793–808 |
| Setup of an existing contract | None checked | Append. The new version becomes latest and **resets cumulative state to 0**; old versions remain | Original | Original | S14 (24 rows become 32; latest Contract 1 shows `Current Billing - Cumulative` 0, `Previous Period` NULL) |
| Delivery / billing upload | Latest version exists | Append a new version for **every** POB of each contract with activity | Latest `Current_*` | Recomputed (Section 3.7) | L948–1154 |
| Prospective / retrospective mod, POB-specific VC | Latest version exists | Append | Latest `Current_*` | Recomputed | Out of scope |
| Purge | Three prompts | `DELETE` of versions whose `Current Period` is in the range for the named contract. Remaining versions are not repaired | n/a | n/a | L504–509; S20 (after purging the 2023-01-01 setup version, the 2023-01-31 version is latest and still says `Previous Period` 2023-01-01) |
| Append from Another | Tables exist | Positional insert of all source rows, with no dedupe | n/a | n/a | L418–428; S17 |
| Reset | Answer Yes | Drops all tables | n/a | n/a | L386–393; S21 |
| Restore | Backup exists | File replaced (live DB deleted first) | n/a | n/a | L333–339; S18, S19 |

State of `SKU_SSP`: absent, then created by the first SSP upload; each later SSP upload **replaces the whole table** (no history, no effective dating beyond the `SSP Version` label); Reset drops it. Contracts keep their copied SSP attributes, so removing a version from the SSP file only breaks **new** setups or mods that reference it (S22).

---

## 5. Worked example: `Contract Setup Template 1.1.2023.xlsx`

Inputs: the SSP UAT file (`SKU SSP Template.xlsx`, all versions `2023-01-01`), then the 1.1.2023 contract file. All numbers below are hand-computed and match the harness output and legacy DB rows 1–8 to 12 decimal places.

### 5.1 Contract 1 (four POBs including a material right; overall discount)

| POB | SKU / Stratification | Q | L | d | r | P | Midpoint = Q·L·(1−d) | Higher = Mid·(1+r) | Lower = Mid·(1−r) | Rule applied | Extended SSP |
|---|---|---|---|---|---|---|---|---|---|---|---|
| POB #1 | Hardware 1 | 5 | 100 | 10% | 15% | 500 | 450.0 | 517.5 | 382.5 | 382.5 <= 500 <= 517.5: keep P | 500.0 |
| POB #2 | Software 1 | 2 | 200 | 20% | 15% | 400 | 320.0 | 368.0 | 272.0 | 400 > 368: Higher | 368.0 |
| POB #3 | Consulting 1 | 1 | 300 | 50% | 0% | 400 | 150.0 | 150.0 | 150.0 | 400 > 150: Higher | 150.0 |
| POB #4 | Material Right - Hardware | 1,000 | 1 | 0% | 0% | 0 | 1,000.0 | 1,000.0 | 1,000.0 | 0 < 1,000: Lower | 1,000.0 |
| **Total** | | | | | | **TP = 1,300** | | | | | **TSSP = 2,018** |

Allocation factor = TP / TSSP = 1,300 / 2,018 = 0.644202180377. The implied discount is 2,018 − 1,300 = 718 (35.58% of total SSP), spread proportionally.

| POB | A = SSP × 1,300 / 2,018 | Unit SSP = SSP / Q | Unit Rev Rec = A / Q | Remaining Billing |
|---|---|---|---|---|
| POB #1 | 322.101090188305 | 100.000000000000 | 64.420218037661 | 500 |
| POB #2 | 237.066402378593 | 184.000000000000 | 118.533201189296 | 400 |
| POB #3 | 96.630327056492 | 150.000000000000 | 96.630327056492 | 400 |
| POB #4 | 644.202180376610 | 1.000000000000 | 0.644202180377 | 0 |
| **Total** | **1,300.000000000000** | | | **1,300** |

Accounting reading: 644.20 of the 1,300 is deferred into the material right. The stated $400 for consulting is reduced to a 96.63 allocation because its SSP (150) is far below its stated price.

### 5.2 Contract 2 (a $0 POB, a negative VC row, and prices below the SSP band)

| POB | SKU / Stratification | Q | L | d | r | P | Midpoint | Higher | Lower | Rule applied | Extended SSP |
|---|---|---|---|---|---|---|---|---|---|---|---|
| POB #1 | Hardware 1 | 8 | 100 | 10% | 15% | 600 | 720.0 | 828.0 | 612.0 | 600 < 612: Lower | 612.0 |
| POB #2 | Software 1 | 3 | 200 | 20% | 15% | 400 | 480.0 | 552.0 | 408.0 | 400 < 408: Lower | 408.0 |
| POB #3 | Consulting 1 | 1 | 300 | 50% | 0% | 0 | 150.0 | 150.0 | 150.0 | 0 < 150: Lower | 150.0 |
| VC #1 | Variable Consideration / `VC` | 1 | 0 | 0% | 0% | −100 | 0.0 | 0.0 | 0.0 | −100 < 0: Lower | 0.0 |
| **Total** | | | | | | **TP = 900** | | | | | **TSSP = 1,170** |

Allocation factor = 900 / 1,170 = 0.769230769231.

| POB | A | Unit SSP | Unit Rev Rec | Remaining Billing |
|---|---|---|---|---|
| POB #1 | 470.769230769231 | 76.500000000000 | 58.846153846154 | 600 |
| POB #2 | 313.846153846154 | 136.000000000000 | 104.615384615385 | 400 |
| POB #3 | 115.384615384615 | 150.000000000000 | 115.384615384615 | 0 |
| VC #1 | 0.000000000000 | 0.000000000000 | 0.000000000000 | −100 |
| **Total** | **900.000000000000** | | | **900** |

Accounting reading: the −100 VC (e.g. a price concession) lowers the transaction price and is spread over all three POBs. The $0 consulting POB receives 115.38 of revenue. The VC row carries −100 of billing (a credit to be issued) and never recognises revenue itself.

### 5.3 Contract 2 of `Contract Setup Template 2.1.2023.xlsx` (Contract 4, for regression)

| POB | P | Q | Band [Lower, Higher] | Extended SSP | A (TP 950 / TSSP 1,306) | Unit Rev Rec |
|---|---|---|---|---|---|---|
| POB #1 Hardware 1 | 600 | 8 | [612.0, 828.0] | 612.0 | 445.176110260337 | 55.647013782542 |
| POB #2 Software 1 | 400 | 4 | [544.0, 736.0] | 544.0 | 395.712098009188 | 98.928024502297 |
| POB #3 Consulting 1 | 150 | 1 | [150.0, 150.0] | 150.0 | 109.111791730475 | 109.111791730475 |
| VC #1 | −200 | 1 | [0, 0] | 0.0 | 0.000000000000 | 0.000000000000 |

Contract 3 in the same file is Contract 1 with `Material Right - Services` (Nondistinct) instead of `Material Right - Hardware`. Its allocation numbers are identical to Section 5.1.

### 5.4 Reproduction check

Running the unchanged legacy source headlessly (SSP UAT, then 1.1.2023, then 2.1.2023) produced 16 rows. All 69 non-timestamp columns equal legacy DB rows 1–16 (tolerance 1e-9). Both `CREATE TABLE` statements are byte-identical to the legacy schema, and the `Record Unique ID` suffixes match (`harness.log`, scenario S01).

### 5.5 How the setup state flows into the first period (legacy DB rows 17–24, 2023-01-31)

This is not part of setup. It shows what the zero-initialised fields become, using the delivery/billing UAT version already stored in the legacy DB. Journal entries were produced by running the legacy `journal_entries()` on a copy of the DB for 2023-01-01 to 2023-01-31 (`je_check.py`).

| POB | Delivered | Billed | Rev Rec = Delivered × Unit Rev Rec | SSP Delivered | Position - POB = Billed − Rev Rec | Position - Contract | Reclass to UAR |
|---|---|---|---|---|---|---|---|
| C1 POB #1 | 2 | 100 | 128.840436075322 | 200.0 | −28.840436075322 | +4.311199207136 | 0 (contract position >= 0) |
| C1 POB #2 | 1 | 100 | 118.533201189296 | 184.0 | −18.533201189296 | +4.311199207136 | 0 |
| C1 POB #3 | 0.5 | 100 | 48.315163528246 | 75.0 | +51.684836471754 | +4.311199207136 | 0 |
| C1 POB #4 | 0 | 0 | 0 | 0 | 0 | +4.311199207136 | 0 |
| C2 POB #1 | 1 | 0 | 58.846153846154 | 76.5 | −58.846153846154 | −58.846153846154 | 58.846153846154 (= 58.846 × 76.5 / 76.5) |
| C2 POB #2, #3, VC #1 | 0 | 0 | 0 | 0 | 0 | −58.846153846154 | 0 |

Legacy journal entry summary (debit positive), verified by running the legacy code:

| Key | Account | Amount |
|---|---|---|
| Contract 1 | 21001 Deferred revenue | 295.69 |
| Contract 1 POB #1 Hardware 1 | 5001 Revenue | −128.84 |
| Contract 1 POB #2 Software 1 | 5002 Revenue | −118.53 |
| Contract 1 POB #3 Consulting 1 | 5003 Revenue | −48.32 |
| Contract 2 | 15002 Unbilled A/R | 58.85 |
| Contract 2 POB #1 Hardware 1 | 5001 Revenue | −58.85 |

Contract 2's deferred revenue lines (+58.85 recognition, −58.85 reclass) net to zero and are suppressed.

---

## 6. Accounting assessment

### 6.1 Sources and scope

- ASC paragraph paraphrases below were checked against the Topic 606 text in FASB ASU 2014-09, Section A ([external website reference removed]). Wording changes made by later amending ASUs were **not** reviewed in this session (open question OQ-09).
- IFRS 15 equivalents, per the retained text of Commission Regulation (EU) 2016/1905 ([external website reference removed]): modifications IFRS 15.18–21; allocation 73–86 (SSP 76–80 including the residual approach in 79(c); discounts 81–83; variable consideration 84–86); changes in transaction price 87–90; presentation 105–109; customer options B39–B43. This session confirmed those ranges only through a fetched summary, so the analysis relies on the ASC text.
- This section assesses setup (Step 4 allocation) plus the setup-owned state that later events consume. Recognition timing and modification accounting are assessed in the companion documents.

### 6.2 Where the legacy logic is consistent with ASC 606

| # | Legacy behaviour | ASC reference (paraphrased) | Assessment |
|---|---|---|---|
| OK-01 | Transaction price allocated to every POB in proportion to extended SSP (L710–711) | 606-10-32-28 (allocate in an amount that depicts expected entitlement); 32-29 (relative SSP basis unless the discount or VC exceptions apply); 32-31 (determine SSP at inception and allocate proportionally) | Mechanically correct for the default relative-SSP method |
| OK-02 | Any discount (TSSP > TP) is spread proportionally across all POBs | 606-10-32-36 (a discount exists when total SSP exceeds promised consideration, and is allocated proportionally unless 32-37 applies) | Correct default |
| OK-03 | $0-price POBs receive an allocation (SSP clamps up to the band floor) | 606-10-32-31 | Correct |
| OK-04 | A material right is set up as its own POB with an SSP and receives allocated revenue | 606-10-55-42 (an option is a performance obligation only if it gives a material right); 55-44 (estimate the option's SSP) | Structurally correct. The estimate itself is outside the tool (see AA-10) |
| OK-05 | A contract-level VC amount lowers or raises the transaction price and is allocated across all POBs | 606-10-32-39 (VC may relate to the entire contract); 32-41 (VC not meeting 32-40 is allocated per 32-28 to 32-38) | Consistent with the default when the 32-40 criteria are not met |
| OK-06 | SSP attributes are copied at setup, so later SSP uploads do not reallocate existing contracts | 606-10-32-43 (no reallocation for post-inception SSP changes) | Consistent |
| OK-07 | Single-POB contracts end up with A = TP whatever the SSP | 606-10-32-30 (32-31 to 32-41 do not apply to single-POB contracts) | Correct outcome |
| OK-08 | Positions are netted at contract level, and a net debit moves from deferred revenue to a contract-asset account (L1073–1089) | 606-10-45-1 (present the contract as a contract asset or contract liability depending on performance versus payment); 45-2 (liability when payment is made or due first); 45-3 (asset when the entity performs first) | Consistent with presenting the **contract** net |
| OK-09 | A stated price inside the SSP band is used as SSP | 606-10-32-32 (best evidence is an observable standalone price; a stated or list price may be, but is not presumed to be, SSP); 32-33 (estimate using observable inputs when not directly observable) | Acceptable **only** as a documented policy backed by an SSP study supporting the band (inference) |

### 6.3 Simplified, incomplete or incorrect

| # | Area | Legacy behaviour | ASC reference | Classification | Consequence |
|---|---|---|---|---|---|
| AA-01 | SSP estimation evidence | Band = list × (1 − d) ± r, typed per SKU. No observable-price evidence, method or study linkage | 606-10-32-32 to 32-34 | Simplified | The engine stores an SSP but not why it is the SSP. Weak audit support |
| AA-02 | SSP at inception | `SSP Version` is any user-chosen string, not tied to the contract inception date | 606-10-32-31 (SSP determined at contract inception) | Incomplete | A version effective after inception can be applied without any warning |
| AA-03 | Price outside band | Clamps to the nearest boundary. The midpoint is computed but never used. No stored policy | 606-10-32-33 (an estimate meeting the allocation objective) | Simplified | Boundary vs midpoint is a policy choice (inference); the legacy hard-codes it |
| AA-04 | Residual approach | Not available | 606-10-32-34(c) (permitted only when SSP is highly variable or uncertain) | Incomplete | Cannot model uncertain-SSP software or IP cases |
| AA-05 | Discount to specific POBs | Not available at setup | 606-10-32-37 (allocate a discount entirely to some POBs when the three observable-evidence criteria are met); 32-38 | Incomplete | Forces proportional allocation even when 32-37 is met |
| AA-06 | Variable consideration | VC is a pseudo-POB row with magic stratification `VC`, the amount is typed in, and there is no estimation method or constraint. The specific-POB allocation is a separate later button | 606-10-32-5, 32-8 (expected value or most likely amount); 32-11 (constraint); 32-40 | Simplified | No evidence of estimate or constraint. VC also depends on a text literal (M-12) |
| AA-07 | Returns at setup | Negative-quantity POB rows with negative allocations, and the SSP band inverts (Section 3.4) | 606-10-55-22, 55-23 (right of return: recognise revenue net of expected returns, a refund liability and an asset for recovery) | **Incorrect** model plus defect | Returns become negative POBs rather than refund liabilities. The SSP clamp is wrong for negative quantities |
| AA-08 | Contract identity and combination | Contract = equal `Contract Unique Name` rows within one file. No 25-1 criteria. No combination. Split uploads are allocated separately (S15) | 606-10-25-1 (contract criteria); 25-9 (combine contracts negotiated as a package, with dependent pricing, or forming a single POB) | Incomplete; **incorrect** for split uploads | Allocation can differ materially (S15: Contract 1 POB #4 gets 347.83 instead of 644.20) |
| AA-09 | Other transaction price components | No significant financing, consideration payable to a customer or noncash consideration | 606-10-32-15; 32-25 | Incomplete | Must be pre-computed by the user into P |
| AA-10 | Material right measurement | The user enters SSP as a quantity of $1 units. No computation of discount × likelihood of exercise, no practical alternative, no breakage | 606-10-55-44 (reflect the incremental discount and the likelihood of exercise); 55-45 (practical alternative); 55-46 to 55-49 (unexercised rights) | Simplified | Estimate not auditable in the tool; breakage not supported |
| AA-11 | Distinctness | `Distinct or Nondistinct` is a SKU-master attribute, not an assessment per contract | 606-10-25-14 (identify POBs at contract inception for each contract); 25-19 (distinct criteria) | Simplified | The same SKU can be distinct in one contract and not in another. Later mod treatment depends on this flag (L1521–1523) |
| AA-12 | Measure of progress | POB start and end dates are not used. Revenue follows only uploaded quantities (an output measure) | 606-10-25-27 (over-time criteria); 25-31 (measure progress over time) | Incomplete | No ratable or time-based schedules. SaaS users must upload fractional quantities every period (inference) |
| AA-13 | Contract asset vs receivable | One "Unbilled A/R" account receives the net debit position | 606-10-45-3 (contract asset: conditional right); 45-4 (receivable: unconditional right) | Simplified | Unbilled receivables and contract assets are not separated for presentation or disclosure |
| AA-14 | Cross-entity netting | Positions net across POBs with different `Selling Entity` and account codes | 606-10-45-1 (contract-level presentation) | Open (inference) | Entity-level balance sheets can show reclassified amounts that do not belong to the entity |
| AA-15 | Billing plan | `Remaining Billing` starts at stated price per POB. There is no invoice schedule | n/a (systems) | Simplified | Bundle invoices must be split by the user. Billing overrun checks rely on stated price |
| AA-16 | Precision and rounding | Binary floats, no currency code, JE rounding per aggregated line with no residual plug | n/a (systems / audit) | Defect risk | Cent differences between allocation, recognised revenue and JE totals are possible |
| AA-17 | Integrity of the record | Append-only snapshots, but Purge, Append and Restore can corrupt history (Section 4.4) and no user identity is recorded | n/a (controls) | Control gap | Weak ITGC evidence for SOX-relevant revenue data |

### 6.4 Edge cases mishandled at setup (summary)

| Edge case | Legacy outcome | Correct/expected outcome |
|---|---|---|
| Negative quantity inside SSP band (S07) | SSP clamped to −103.5 | SSP −90 (sign-aware band), or reject and model as right of return |
| Duplicate SSP key (S08) | POB duplicated; TP 1,800 | Reject upload |
| Duplicate POB in file (S16) | Both kept; TP 1,800 | Reject upload |
| Contract split across files (S15) | Two independent allocations | Allocate across all POBs of the contract |
| Re-setup of existing contract (S14) | New "latest" version with cumulative state reset | Reject, or process as a governed restatement |
| Blank price or qty (S06) | NaN allocation; the rest absorbs TP | Row-level validation error |
| Qty 0 (S13) | NULL unit rates | Validation error, or an explicit zero-quantity policy |
| All-VC contract (S12) | NULL allocation | Validation error |
| Discount typed as whole number (S23) | Negative SSP and inverted allocations | Validation error (0 <= d < 1) |
| Numeric IDs (S11) | Silent no-op | Accept (cast to text) |
| SSP version typing (S09) | Rejects `1` vs `1.0`, and date vs datetime | Typed, effective-dated SSP versions |

---

## 7. Port notes for eRev Cloud

### 7.1 Parity requirements (preserve)

| ID | Requirement | Legacy source |
|---|---|---|
| PAR-01 | Relative-SSP allocation `A_i = SSP_i / Σ SSP × Σ P` over all POBs of the contract, including $0 POBs, material rights and VC rows (SSP 0); Σ A = TP | L704–711 |
| PAR-02 | SSP band: `Mid = Q·L·(1−d)`, `Higher = Mid·(1+r)`, `Lower = Mid·(1−r)`. Inclusive band; stated price used when inside; outside clamps to the nearest boundary (default policy "boundary"; the midpoint is stored for reporting) | L682–700 |
| PAR-03 | VC rows with zero SSP change the transaction price and are spread pro rata. The VC row's own allocation is 0 and its billing equals its stated amount | L700–711, L739 |
| PAR-04 | Material right imported from the legacy convention (L = 1, d = 0, r = 0, Q = SSP dollars) must yield identical allocations. The native model should hold an explicit SSP amount | UAT Contract 1 POB #4 |
| PAR-05 | Initial state: remaining qty, SSP, allocation and billing = originals; all activity, cumulative, position and reclass fields = 0; no previous period | L719–756 |
| PAR-06 | Unit rates `Unit SSP = SSP/Q`, `Unit Rev Rec = A/Q`, consumed later as `revenue = delivered qty × remaining unit rate` | L713–717, L1028 |
| PAR-07 | SSP attributes (list price, discount, range, revenue account, distinct flag, SKU id) snapshot onto the POB at setup and do not change with later SSP uploads | L677–679 |
| PAR-08 | SSP lookup by SKU + stratification + SSP version, with per-POB version choice (README L55) | L677–679 |
| PAR-09 | Allocation group is the contract, not the entity. Cross-entity POBs share one allocation, with deferred revenue and unbilled A/R accounts per POB | L704–708; README L59 |
| PAR-10 | Import of the 9-column SSP and 16-column contract templates unchanged (header names exact). All-or-nothing file rejection on header, numeric or unmatched-SKU errors | L543–558, L630–660, L764–773 |
| PAR-11 | Immutable version history per POB (processing timestamp + accounting date + previous/current roll-forward) with "latest status" and "history in date range" views | L757–762, L882–902 |
| PAR-12 | Contract position per POB (billing cum − revenue cum) and at contract level; net debit reclassified to the contract-asset account in proportion to cumulative SSP delivered; VC rows excluded | L1073–1089 |
| PAR-13 | JE summary: Dr deferred / Cr revenue for recognition; reverse the prior reclass and book the current one; debit-positive sign; zero-line suppression; 2-dp presentation | L2594–2651 |
| PAR-14 | Database capabilities re-expressed as tenant-safe features: backup/snapshot, restore, sandbox reset, import from another workspace, purge/void of contract versions | L293–532 |
| PAR-15 | Golden values in Section 5 reproduced to 1e-9 (store allocations at full precision; round only for presentation and posting) | S01 |

### 7.2 Behaviours to fix (do not port)

| ID | Fix | Legacy defect |
|---|---|---|
| FIX-01 | Sign-aware SSP band (`lo = min(Lower, Higher)`, `hi = max(...)`), or model returns as refund liability / VC | Section 3.4; S07 |
| FIX-02 | Row-level validation of blanks, types, qty != 0, total SSP != 0, 0 <= d < 1, r >= 0, date types and end >= start, with row numbers in messages | M-01 to M-11 |
| FIX-03 | Never swallow exceptions. Cast IDs to text | VR-setup-10 |
| FIX-04 | Uniqueness constraints: SSP (SKU, stratification, version); POB (contract, POB id); reject duplicates | M-04, M-05 |
| FIX-05 | Existing contract on setup: reject, or route to a governed restatement/modification workflow | M-06; S14 |
| FIX-06 | Allocate over all POBs of the contract regardless of upload batch. Support contract combination | M-07; AA-08 |
| FIX-07 | Typed, effective-dated SSP versions (default to the version in force at inception, override with reason and audit). Append SSP history instead of replacing the table | AA-02; S09, S22 |
| FIX-08 | Unmatched-SKU message identifies row and failing key (SKU, stratification or version); fix typo "databse" | VR-setup-09 |
| FIX-09 | Decimal arithmetic with currency-aware rounding and a largest-remainder penny plug so rounded allocations and JE lines sum to TP | AA-16 |
| FIX-10 | Surrogate IDs plus natural-key constraints; no space-delimited concatenated keys | M-14 |
| FIX-11 | Order versions by accounting date plus event sequence. Period close/lock. Explicit reprocessing for back-dated events | Section 4.3 |
| FIX-12 | Separate contract asset from unbilled receivable; decide entity-level netting | AA-13, AA-14 |
| FIX-13 | Add residual approach, discount-to-specific-POB allocation, VC estimation and constraint with 32-40 allocation, material-right estimate and breakage, contract-level distinctness, time-based schedules | AA-04 to AA-12 |
| FIX-14 | Replace client-side key gating and hard-coded end-of-life shutdown with server-side entitlements | Section 1.2; VR-setup-12 |
| FIX-15 | Restore never deletes before the snapshot is verified. Multi-slot immutable backups | VR-setup-14, VR-setup-15; S18 |
| FIX-16 | Purge: parameterised queries, confirmation, deleted-row count, honour Cancel, repair or void the chain | VR-setup-19, VR-setup-20; S20 |
| FIX-17 | Import from another workspace: map by column name, dedupe version keys, transactional | VR-setup-17; S17 |
| FIX-18 | Record the user, source file hash and approval on each event (audit trail) | AA-17 |

### 7.3 Test cases to carry forward

Expected values come from the harness or the legacy DB. "Legacy" = observed legacy output; "Expected" = target behaviour in eRev Cloud.

| ID | Input | Expected (eRev Cloud) | Legacy (observed) |
|---|---|---|---|
| TC-setup-01 | SSP UAT + `Contract Setup Template 1.1.2023.xlsx` | 8 POBs. Contract 1: TP 1,300, TSSP 2,018, A = 322.101090188305 / 237.066402378593 / 96.630327056492 / 644.202180376610. Contract 2: TP 900, TSSP 1,170, A = 470.769230769231 / 313.846153846154 / 115.384615384615 / 0 | Same |
| TC-setup-02 | `Contract Setup Template 2.1.2023.xlsx` | Contract 3 as Contract 1. Contract 4: TP 950, TSSP 1,306, A = 445.176110260337 / 395.712098009188 / 109.111791730475 / 0 | Same |
| TC-setup-03 | Hardware 1, Q 5, P 500 | Band [382.5, 517.5]; SSP 500 | Same |
| TC-setup-04 | Software 1, Q 2, P 400 | SSP 368 (clamped Higher) | Same |
| TC-setup-05 | Hardware 1, Q 8, P 600 | SSP 612 (clamped Lower) | Same |
| TC-setup-06 | P = 517.5 (Q 5) and P = 272 (Software 1, Q 2), one contract | SSP 517.5 and 272; A = P (TP = TSSP = 789.5) | Same |
| TC-setup-07 | Positive VC: Hardware 1 Q 5 P 500 + VC P +100 | TP 600, TSSP 500, A_HW 600, Unit Rev Rec 120, A_VC 0 | Same |
| TC-setup-08 | Rounded posting of TC-setup-01 and 02 | 2-dp allocations sum to TP: 322.10 + 237.07 + 96.63 + 644.20 = 1,300.00; 470.77 + 313.85 + 115.38 = 900.00; 445.18 + 395.71 + 109.11 = 950.00 | Same (no plug needed in these cases) |
| TC-setup-09 | 3 POBs with equal SSP, TP 100 (derived case) | Allocations 33.34 / 33.33 / 33.33 (largest remainder) | Full precision 33.333…; posted lines would total 99.99 (inference from L2598–2651) |
| TC-setup-10 | Legacy DB, JE 2023-01-01..2023-01-31 | Contract 1: Dr 21001 295.69; Cr 5001 128.84, 5002 118.53, 5003 48.32. Contract 2: Dr 15002 58.85; Cr 5001 58.85 | Same (`je_check.py`) |
| TC-setup-11 | Contract 1 split across two uploads (POB #1–2, then POB #3–4) | Whole-contract allocation as TC-setup-01 | 518.433180 / 381.566820 / 52.173913 / 347.826087 |
| TC-setup-12 | Hardware 1, Q −1, P −90 | SSP −90 (or rejected as a return) | SSP −103.5 |
| TC-setup-13 | Duplicate SSP key (Hardware 1 at list 100 and 120) | Upload rejected | POB duplicated; Contract 1 TP 1,800 |
| TC-setup-14 | Contract 1 POB #1 twice in one file | Upload rejected | TP 1,800; both rows stored |
| TC-setup-15 | Numeric POB IDs 1–4 | Accepted as text IDs | Silent no-op, no popup |
| TC-setup-16 | Blank price on Contract 1 POB #2 | Row error "price required" | A_POB2 NULL; others 272.727273 / 81.818182 / 545.454545 |
| TC-setup-17 | Q = 0 row | Row error | Unit SSP NULL |
| TC-setup-18 | Contract with only a VC row | Validation error | Allocation NULL |
| TC-setup-19 | Discount entered as 10 for Hardware 1 | Validation error | TSSP −70,482; A_HW 1,327.998638 |
| TC-setup-20 | SKU `Hardware X` | Whole file rejected; message names row 2 and key `Hardware X / Hardware 1 / 2023-01-01` | Popup lists 'Hardware X'; nothing written |
| TC-setup-21 | Headers: `Notes` added, `Memo 3` removed | Rejected with missing and extra lists | Three popups (VR-setup-06) |
| TC-setup-22 | Re-upload `Contract Setup Template 1.1.2023.xlsx` after deliveries | Rejected or restatement workflow | 8 rows appended; cumulative state reset |
| TC-setup-23 | Restore with no backup present | Live data intact; error shown | Live DB deleted |
| TC-setup-24 | Purge with contract-name Cancel | No delete, no success message | Success popup shown |
| TC-setup-25 | Append the same source DB twice | No duplicate versions | 24 → 48 → 72 rows |

### 7.4 Open questions

See the orchestrator return (`open_questions`). The main ones: default SSP out-of-range policy (boundary vs midpoint) and at what level to configure it; legacy-parity mode for split uploads and material-right quantity convention during migration; contract asset vs unbilled receivable classification; cross-entity netting; verification of current Codification wording.

---

## Appendix A. Harness scenario index (`~/dev/erev/.scratch/legacy-setup/`)

| Scenario | Purpose |
|---|---|
| S01 | Golden reproduction of legacy DB rows 1–16 |
| S02 / S03 | Blank SSP template; setup before SSP upload |
| S04 | Header mismatch, trailing space, column order |
| S05 / S06 / S06b | Non-numeric and blank numeric inputs |
| S07 | Negative quantity band inversion |
| S08 | Duplicate SSP key fan-out |
| S09 / S09b / S09c | SSP version typing drift |
| S10 | Unmatched SKU and stratification |
| S11 | Numeric IDs (silent TypeError) |
| S12 | All-VC, zero qty, zero price, positive VC |
| S14 | Re-setup of an existing contract |
| S15 / S16 | Split upload; duplicate POB row |
| S17 (b–d) | Append from Another |
| S18 / S19 | Restore without backup; backup directory missing; round trip |
| S20 / S20b | Purge variants |
| S21 | Reset confirmation |
| S22 | SSP re-upload replaces table |
| S23 | Whole-number percentages |
| S26 / S28 / S30 | Junk dates, blank contract name, decimal after INTEGER affinity |
| S31 | Band boundaries |
| `je_check.py` | Legacy journal entry output for 2023-01-01..2023-01-31 |


