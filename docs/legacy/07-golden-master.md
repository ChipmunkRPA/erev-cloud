# 07 - Legacy eRev Behavioural Golden Master

Status: complete (2026-09-11).

This document records a headless replay of the ORIGINAL legacy `eRev.py` over the shipped UAT
scenario, the stubs used to make it run without a display or Windows, the resulting golden
snapshots, anomalies, and candidate golden tests for the eRev Cloud engine.

**Results**
- **The original code ran unmodified**; the copy's SHA-256 equals the legacy file. No fallback port was needed, so every number here comes from the original legacy code.
- **All 15 steps replayed in order** (00 reset, then 14 business steps). Every handler showed its success popup and no validation failed.
- **The replay matches the shipped `ASC606.db`** on all 69 compared columns of all 24 rows at the same point (after step 04). The shipped DB stops there.
- **Four probes on the original code** confirmed three silent defects that the UAT misses: a blank memo drops upload rows, mods re-post Pre-ASC606 revenue in the adjustment JE, and re-uploading a file double-counts. Over-delivery validation works.
- **The JE reports can be out of balance by 0.01**: October and May 2023.
- **Reruns are byte-identical**, including probes and analysis outputs. `golden/golden-tests.json` holds 122 expected-value cases for the new engine.

## 1. How to rerun

```bash
cd ~/dev/erev/legacy-harness
./setup.sh    # uv venv (Python 3.12) + pinned deps; rsync ~/dev/erev-legacy -> erev_copy/ (no .git);
              # copies the shipped DB to fixtures/ASC606.shipped.db
./run.sh      # QT_QPA_PLATFORM=offscreen, then:
              #   replay.py   UAT replay               -> docs/legacy/golden/NN-slug, monthly/, compare-shipped/
              #   probes.py   defect probes            -> docs/legacy/golden/probes/
              #   analyze.py  tables and test fixtures -> golden/golden-tests.json, contract-rollforward.csv,
              #                                           final-pob-positions.csv, out/analysis.md
```

The whole pipeline takes about 4 seconds on Apple Silicon. Qt's offscreen plugin prints "This plugin does not
support propagateSizeHints()" to stderr; this is harmless.

Determinism check (used for this document; no differences):

```bash
./run.sh --golden-dir ~/dev/erev/.scratch/legacy-golden/golden-rerun --out-dir ~/dev/erev/.scratch/legacy-golden/out-rerun
diff -r ~/dev/erev/docs/legacy/golden ~/dev/erev/.scratch/legacy-golden/golden-rerun
```

`replay.py` options: `--golden-dir` (default `~/dev/erev/docs/legacy/golden`), `--out-dir` (default
`legacy-harness/out`), `--allow-modified-copy` (off by default).

Checks run before replay starts (the run aborts if either fails):

| Check | Expected |
|---|---|
| `erev_copy/eRev.py` SHA-256 | `7fb658fbd72b9d7f8ca5dafa58ba34fabde9d101250b53f57ec45023e5e2bc14` (legacy commit `5ec25ff`) |
| `fixtures/ASC606.shipped.db` SHA-256 | `6e35b508218420c670f3f19d0fb1df83b32ff498bb45e6bd47df68cbdf1aafc2` |

Environment used for the golden run (pinned in `legacy-harness/requirements.txt`, choosing
2024-era releases to match the code's 2024 copyright and 2025-12-31 end-of-life date):

| Component | Version |
|---|---|
| Python | 3.12.13 (uv-managed), macOS arm64 |
| pandas / numpy | 2.2.3 / 1.26.4 |
| PySide6 | 6.7.3 (`QT_QPA_PLATFORM=offscreen`) |
| openpyxl / python-dotenv | 3.1.5 / 1.0.1 |
| SQLite | 3.50.4 |

What a run does:

1. Copies the shipped DB into `erev_copy/ops/libnew/libwarm/db/ASC606.db`, imports `eRev` as a module
   (so the `__main__` block never runs), installs the stubs, and builds the real `FileBrowserWindow`.
2. For each step, clicks the real button on the main window. The harness asserts the button text
   (for example `button5` must read "Retrospective Contract Mod"), then feeds the file path and
   date through the stubbed dialogs.
3. After each step, writes `contract_live.csv` and `sku_ssp.csv`. It then runs the four built-in reports by clicking the
   real report dialog buttons: *Gross Revenue JEs*, *Revenue Adjustment JEs* (the JE delta report),
   *Check All Contract History* and *Check All Latest Contract*. The resulting DataFrames are saved as CSV.
4. After the last step, reruns the JE, JE delta and history reports for each calendar month from January
   to October 2023, plus the full year. It then compares the results with the shipped DB.

Output layout:

| Path | Content |
|---|---|
| `docs/legacy/golden/NN-slug/contract_live.csv` | every `Contract_Live` row after the step |
| `.../sku_ssp.csv` | `SKU_SSP` after the step |
| `.../je_gross.csv`, `je_delta.csv` | *Revenue Journal Entries* -> Gross / Revenue Adjustment for the step window |
| `.../contract_history.csv`, `latest_contracts.csv` | *Contract History* (step window) and *Latest Contract Status* |
| `.../popups.csv`, `events.csv`, `step.json` | popups; all stub interactions (file, date, license, EFS); step metadata and JE totals |
| `docs/legacy/golden/monthly/2023-MM/`, `monthly/2023-full-year/` | month-end and full-year JE / delta / history on the final DB |
| `docs/legacy/golden/compare-shipped/` | point-in-time column diffs, version inventory, `compare.json` |
| `docs/legacy/golden/manifest.json`, `summary.json`, `popups-all.csv` | environment, hashes, step plan, all totals |
| `docs/legacy/golden/probes/<probe-id>/` | probe DB state, popups, events, JE CSVs, `probe.json` (sequence, observed values, baseline, code references) |
| `docs/legacy/golden/golden-tests.json` | 122 expected-value cases for the eRev Cloud engine (section 7) |
| `docs/legacy/golden/contract-rollforward.csv`, `final-pob-positions.csv` | contract position after every step; POB positions after step 14 |
| `legacy-harness/out/probes/inputs/` (gitignored) | probe input workbooks generated from the shipped UAT files with openpyxl |
| `legacy-harness/out/NN-slug/` (gitignored) | raw DB copy per step, the app's own Excel exports, un-normalised CSV, Python warnings |

**Report window per step:** from the later of (a) the first day of the step's month and (b) the day after
the latest earlier step date, through the step date. For example, step 08 covers 2023-05-01 to 2023-05-15
and step 09 covers 2023-05-16 to 2023-05-31. Steps 00 and 01 have no date, so only *Latest Contract Status* is run
for them.

**Timestamp normalisation:** `Processing Time Log`, and the timestamp prefix of
`Record Unique ID`, hold wall-clock time from `pd.Timestamp.now()`. In the golden CSVs they are replaced by
`step-NN`, the step that wrote the row. Each handler call writes exactly one timestamp. Raw values stay
in `out/`. Nothing else is rewritten.

## 2. Stubs

No line of `eRev.py` was patched. Every stub rebinds a module-global name or overrides a method from
outside the file.

| Stub | Legacy call sites | Harness behaviour | Reason |
|---|---|---|---|
| `eRev.QFileDialog` -> `FakeFileDialog` | `getOpenFileName` in every loader (l.535, 622, 827, 1171, 1656, 2134) | returns the queued absolute path of the UAT file in `erev_copy/`; logged as `category=file` | no display, no user |
| `eRev.QInputDialog` -> `FakeInputDialog` | `getText` for the period / mod date (l.832, 1176, 1661, 2139) and report date ranges (l.2542/2550, 2672/2680, 2864/2872) | pops the next queued `YYYY-MM-DD` string with `ok=True`; logs the prompt and answer; an empty queue behaves like Cancel | date dialogs |
| `eRev.QMessageBox` -> `FakeMessageBox` | static `information/warning/critical/question` and instance `exec()` | records kind, title and text; `question` answers Yes (reset confirmation, l.378); enum values pass through so `QMessageBox.Yes \| QMessageBox.No` still evaluates | popups would block |
| `eRev.DataFramePopup` -> recording subclass | report popups (l.2660, 2715, 2810, 3003) | stores a copy of the DataFrame, then calls the original `__init__`, which builds the real `QTableView` offscreen and raises "File Saved" | capture report output exactly as displayed, without an Excel round trip |
| `FileBrowserWindow.load_license_key` -> returns `None` | l.256, 265-276 | no `.env` read and no blocking `LicenseKeyDialog.exec()` | license gating |
| `FileBrowserWindow.show_notification_and_disable` -> no-op | l.259-263, 278-291 | premium buttons stay enabled, so the real *Reset Database* button can be clicked | license gating |
| `ctypes.WinDLL` -> fake `Advapi32.EncryptFileW` returning 1 | `encrypt_file` in SSP load (l.582-607; fires in step 01), and in backup, restore and append (l.298-323, 342-367, 437-462), which the replay does not use | logs the path as `category=platform`; no encryption | Windows EFS. `from ctypes import wintypes` imports natively on macOS Python 3.12, so it needs no stub. Without the stub, the `AttributeError` would be swallowed by the code's `except: pass`, with the same result. |
| `__main__` block not executed | l.3208-3218 | the harness builds its own `QApplication`; `ShutdownNotifier(2025-12-31 23:59)` is never created | shutdown gating. The end-of-life date has passed, so the original app would quit within 60 s of launch. |

Deliberately **not** stubbed:
- all calculation code;
- pandas and SQLite I/O, including `pd.Timestamp.now()`;
- the app's `to_excel` exports, which are moved to `out/`;
- the real `CustomDialog`, `ContractDialog` and `LatestContractDialog`. Their buttons are clicked because the report slots call `self.sender().parent().close()`, which only works on a genuine signal;
- the real main-window buttons.

Python warnings were recorded for every step with `warnings.simplefilter("always")`. The capture
was verified in a slot probe (`.scratch/legacy-golden/warn_capture_test.py`). **The replay raised no
warnings** under pandas 2.2.3: the `.loc` filters rebind the same variable, so no live parent
triggers `SettingWithCopyWarning`, and pandas registers its own SQLite datetime adapters.

## 3. Step table

**Handler selection.** All three mod buttons use the same template, so the file name decides the handler:
- "retrospective" -> *Retrospective Contract Mod* (`browse_file_RetroMod`)
- "POB specific VC" -> *POB Specific VC* (`browse_file_POB_specific_VC`)
- "prospective" (spelled "propsective" in the 09.15 file) -> *Prospective Contract Mod* (`browse_file_ProsMod`)

The date typed into the dialog is the date in the file name. Contract setup has no date prompt; it takes `Current Period` from the file (2023-01-01, 2023-02-01).

**Order.** The replay runs CS 1.1 -> CS 2.1 -> D&B 1.31. This matches the `Processing Time Log` order in the shipped DB (2025-05-09 at 09:11:44, 09:11:53 and 09:12:33). The order does not affect any number, because the 1.31 upload touches only Contracts 1 and 2.

**JE conventions.**
- Sign: in the legacy report, Amount > 0 is a debit and Amount < 0 is a credit.
- Accounts: 5001-5004 are revenue (set per SKU), 21001/21002 are deferred revenue, and 15001/15002 are unbilled A/R (contract asset) for Mock Entity 1/2.
- Grouping: revenue lines are summarised per POB (`Contract POB SKU`); deferred revenue and unbilled A/R lines are summarised per contract.
- Scope: billing JEs (A/R against deferred revenue) are **not** produced. Legacy assumes the billing system posts them.

| Step | Handler (button) | File | Date input | Rows after (+new) | Handler popups | Report window | JE gross by account (Dr / Cr) | JE delta (Revenue Adjustment JEs) |
|---|---|---|---|---|---|---|---|---|
| 00 | `db_reset` (!Reset Database Completely!) | - | - | 0 (-24) | Confirmation (answered Yes); ASC606 database reset | - | n/a | n/a |
| 01 | `browse_file_SSPs` (Load SSPs) | SKU SSP Template.xlsx | - | 0 (+0); SKU_SSP 7 | SSPs are set up | - | n/a | n/a |
| 02 | `browse_file_Contracts` (Load Contracts) | Contract Setup Template 1.1.2023.xlsx | - | 8 (+8) | Contracts are set up | 2023-01-01 to 2023-01-01 | no lines | same as gross |
| 03 | `browse_file_Contracts` (Load Contracts) | Contract Setup Template 2.1.2023.xlsx | - | 16 (+8) | Contracts are set up | 2023-02-01 to 2023-02-01 | no lines | same as gross |
| 04 | `browse_file_Deliveries` (Load Delivery and Billing) | Contract Progress Tracking Template 1.31.2023.xlsx | 2023-01-31 | 24 (+8) | Rev Rec Success | 2023-01-02 to 2023-01-31 | Dr 15002 58.85, 21001 295.69 / Cr 5001 187.69, 5002 118.53, 5003 48.32 (total 354.54 / 354.54, balanced) | Dr 5003 39.68, 15002 58.85, 21001 141.69 / Cr 5001 187.69, 5002 52.53 (total 240.22 / 240.22, balanced) |
| 05 | `browse_file_Deliveries` (Load Delivery and Billing) | Contract Progress Tracking Template 2.28.2023.xlsx | 2023-02-28 | 36 (+12) | Rev Rec Success | 2023-02-02 to 2023-02-28 | Dr 21001 112.74, 21002 111.29 / Cr 5001 175.71, 5003 48.32 (total 224.03 / 224.03, balanced) | Dr 5001 38.71, 5003 151.68, 21001 64.42 / Cr 5001 64.42, 21001 151.68, 21002 38.71 (total 254.81 / 254.81, balanced) |
| 06 | `browse_file_Deliveries` (Load Delivery and Billing) | Contract Progress Tracking Template 3.31.2023.xlsx | 2023-03-31 | 48 (+12) | Rev Rec Success | 2023-03-01 to 2023-03-31 | Dr 15002 46.15, 21001 118.53, 21002 98.93 / Cr 5002 217.46, 5003 46.15 (total 263.61 / 263.61, balanced) | same as gross |
| 07 | `browse_file_Deliveries` (Load Delivery and Billing) | Contract Progress Tracking Template 4.30.2023 - Return & Zero delivery billing.xlsx | 2023-04-30 | 56 (+8) | Rev Rec Success | 2023-04-01 to 2023-04-30 | Dr 5001 193.26, 21002 20.00 / Cr 15002 20.00, 21001 193.26 (total 213.26 / 213.26, balanced) | same as gross |
| 08 | `browse_file_RetroMod` (Retrospective Contract Mod) | Contract Modification Template 05.15.2023 - retrospective vc + POB increases.xlsx | 2023-05-15 | 60 (+4) | Mod Success | 2023-05-01 to 2023-05-15 | Dr 15002 23.87 / Cr 5001 13.38, 5003 10.49 (total 23.87 / 23.87, balanced) | same as gross |
| 09 | `browse_file_POB_specific_VC` (POB Specific VC) | Contract Modification Template 05.31.2023 - retrospective POB specific VC.xlsx | 2023-05-31 | 64 (+4) | POB Specific VC Successfully Applied! | 2023-05-16 to 2023-05-31 | Dr 5001 18.68 / Cr 15002 18.68 (total 18.68 / 18.68, balanced) | same as gross |
| 10 | `browse_file_ProsMod` (Prospective Contract Mod) | Contract Modification Template 06.15.2023 - prospective reduction.xlsx | 2023-06-15 | 68 (+4) | Mod Success | 2023-06-01 to 2023-06-15 | Dr 5003 5.30 / Cr 21001 5.30 (total 5.30 / 5.30, balanced) | same as gross |
| 11 | `browse_file_ProsMod` (Prospective Contract Mod) | Contract Modification Template 07.15.2023 - prospective POB increases.xlsx | 2023-07-15 | 76 (+8) | Mod Success | 2023-07-01 to 2023-07-15 | Dr 21001 6.99 / Cr 5003 6.99 (total 6.99 / 6.99, balanced) | same as gross |
| 12 | `browse_file_RetroMod` (Retrospective Contract Mod) | Contract Modification Template 08.15.2023 - retrospective POB reduction.xlsx | 2023-08-15 | 84 (+8) | Mod Success | 2023-08-01 to 2023-08-15 | Dr 21001 42.10, 21002 16.30 / Cr 5001 8.63, 5002 42.55, 5003 7.22 (total 58.40 / 58.40, balanced) | same as gross |
| 13 | `browse_file_ProsMod` (Prospective Contract Mod) | Contract Modification Template 09.15.2023 - material right exericse with new POB added (propsective).xlsx | 2023-09-15 | 89 (+5) | Mod Success | 2023-09-01 to 2023-09-15 | Dr 21001 32.14 / Cr 5003 32.14 (total 32.14 / 32.14, balanced) | same as gross |
| 14 | `browse_file_Deliveries` (Load Delivery and Billing) | Full delivery 10.31.2023.xlsx | 2023-10-31 | 106 (+17) | Rev Rec Success | 2023-10-01 to 2023-10-31 | Dr 21001 2,990.36, 21002 2,053.48 / Cr 5001 2,060.34, 5002 1,108.62, 5003 1,784.70, 15002 90.19 (total 5,043.84 / 5,043.85, **OUT OF BALANCE -0.01**) | same as gross |

**Popups.**
- Every handler showed its success popup, and no validation popup fired. For step 00 there was also the reset confirmation question, answered Yes.
- Every report run showed "File Saved" (4 per dated step).
- *Latest Contract Status* on steps 00 and 01 raised `Error Notification: Execution failed on sql ... no such table: Contract_Live`.
- All 102 replay popups are in `golden/popups-all.csv`; per-step detail, including file and date prompts, is in `NN-slug/events.csv`.

**Rows after a step.** A delivery/billing upload writes a new version of **every POB in any contract with activity**, not only the POBs that were delivered. A mod writes a new version of every POB in the modified contract.

## 4. Per-contract final positions

Definitions, taken from the latest version of each POB:
- **Transaction price** = sum of (`Current Rev Rec - Cumulative` + `Current Remaining Allocation`). At every step it equals the billing basis, sum of (`Current Billing - Cumulative` + `Current Remaining Billing`); section 6 confirms this.
- **Allocation per POB** = `Current Rev Rec - Cumulative` + `Current Remaining Allocation`.
- **Net contract position** = sum of `Current Contract Position - POB` (billing minus revenue). Positive is a contract liability (deferred revenue); negative is a contract asset. Legacy books the asset as `Current Reclass to UAR`, split across POBs by cumulative SSP delivered and forced to 0 on VC lines.

### 4.1 Final contract positions (after step 14, 2023-10-31)

| Contract | POBs | Transaction price | Cumulative revenue | Cumulative billing | Remaining allocation | Net position | Contract asset (UAR) | Contract liability | Cumulative catch-up (disclosure) |
|---|---|---|---|---|---|---|---|---|---|
| Contract 1 | 4 | 800.00 | 800.00 | 800.00 | 0.00 | 0.00 | 0.00 | 0.00 | -5.30 |
| Contract 2 | 4 | 1,100.00 | 1,100.00 | 1,100.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5.19 |
| Contract 3 | 5 | 2,600.00 | 2,600.00 | 2,600.00 | 0.00 | 0.00 | 0.00 | 0.00 | 81.24 |
| Contract 4 | 4 | 1,200.00 | 1,200.00 | 1,200.00 | 0.00 | 0.00 | 0.00 | 0.00 | 16.30 |

All four contracts end fully delivered, fully billed and at zero net position. The full-year gross JE credits revenue with 5,700.00 in total (5001 2,233.81; 5002 1,487.17; 5003 1,979.02) and debits deferred revenue with 21001 3,400.00 and 21002 2,300.00. That total equals the final transaction prices (800 + 1,100 + 2,600 + 1,200), and every POB's full-year revenue line ties to its cumulative revenue within 0.01.

Transaction price bridge, from setup to final:
- **Contract 1:** 1,300 -500 (06.15 prospective reduction) = 800.
- **Contract 2:** 900 +400 (05.15 retrospective) -200 (05.31 POB-specific VC) = 1,100.
- **Contract 3:** 1,300 +500 (07.15) -200 (08.15) +1,000 (09.15 new POB) = 2,600.
- **Contract 4:** 950 +300 (07.15) -50 (08.15) = 1,200.

### 4.2 Final POB positions (after step 14)

| Contract | POB | SKU | D/N | Original allocation | Final allocation | Qty delivered cum | Revenue cum | Billing cum | Remaining qty | Remaining allocation | Position POB | Catch-up cum (disclosure) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Contract 1 | POB #1 | Hardware 1 | Distinct | 322.10 | 0.00 | 0.0 | 0.00 | 0.00 | 0 | 0.00 | 0.00 | 0.00 |
| Contract 1 | POB #2 | Software 1 | Distinct | 237.07 | 211.07 | 2.0 | 211.07 | 400.00 | 0 | 0.00 | 188.93 | 0.00 |
| Contract 1 | POB #3 | Consulting 1 | Nondistinct | 96.63 | 86.03 | 1.0 | 86.03 | 400.00 | 0 | 0.00 | 313.97 | -5.30 |
| Contract 1 | POB #4 | Material Right - Hardware | Distinct | 644.20 | 502.90 | 1,000.0 | 502.90 | 0.00 | 0 | 0.00 | -502.90 | 0.00 |
| Contract 2 | POB #1 | Hardware 1 | Distinct | 470.77 | 573.20 | 10.0 | 573.20 | 800.00 | 0 | 0.00 | 226.80 | -5.31 |
| Contract 2 | POB #2 | Software 1 | Distinct | 313.85 | 385.19 | 3.0 | 385.19 | 400.00 | 0 | 0.00 | 14.81 | 0.00 |
| Contract 2 | POB #3 | Consulting 1 | Nondistinct | 115.38 | 141.61 | 1.0 | 141.61 | 0.00 | 0 | 0.00 | -141.61 | 10.49 |
| Contract 2 | VC #1 | Variable Consideration | Nondistinct | 0.00 | 0.00 | 1.0 | 0.00 | -100.00 | 0 | 0.00 | -100.00 | 0.00 |
| Contract 3 | POB #1 | Hardware 1 | Distinct | 322.10 | 678.02 | 3.0 | 678.02 | 800.00 | 0 | 0.00 | 121.98 | 0.00 |
| Contract 3 | POB #2 | Software 1 | Distinct | 237.07 | 464.52 | 2.0 | 464.52 | 400.00 | 0 | 0.00 | -64.52 | 34.88 |
| Contract 3 | POB #3 | Consulting 1 | Nondistinct | 96.63 | 189.34 | 1.0 | 189.34 | 400.00 | 0 | 0.00 | 210.66 | 46.36 |
| Contract 3 | POB #4 | Material Right - Services | Nondistinct | 644.20 | 0.00 | 0.0 | 0.00 | 0.00 | 0 | 0.00 | 0.00 | 0.00 |
| Contract 3 | POB #5 | Consulting 1 | Nondistinct | NULL | 1,268.11 | 5.0 | 1,268.11 | 1,000.00 | 0 | 0.00 | -268.11 | 0.00 |
| Contract 4 | POB #1 | Hardware 1 | Distinct | 445.18 | 479.69 | 8.0 | 479.69 | 600.00 | 0 | 0.00 | 120.31 | 8.63 |
| Contract 4 | POB #2 | Software 1 | Distinct | 395.71 | 426.39 | 4.0 | 426.39 | 400.00 | 0 | 0.00 | -26.39 | 7.67 |
| Contract 4 | POB #3 | Consulting 1 | Nondistinct | 109.11 | 293.93 | 2.5 | 293.93 | 400.00 | 0 | 0.00 | 106.07 | 0.00 |
| Contract 4 | VC #1 | Variable Consideration | Nondistinct | 0.00 | 0.00 | 1.0 | 0.00 | -200.00 | 0 | 0.00 | -200.00 | 0.00 |

Machine-readable versions: `golden/final-pob-positions.csv` and `golden/contract-rollforward.csv`.

### 4.3 Contract rollforward after each step

Transaction price:

| Step | Contract 1 | Contract 2 | Contract 3 | Contract 4 |
|---|---|---|---|---|
| 02 | 1,300.00 | 900.00 | - | - |
| 03-07 | 1,300.00 | 900.00 | 1,300.00 | 950.00 |
| 08 | 1,300.00 | 1,300.00 | 1,300.00 | 950.00 |
| 09 | 1,300.00 | 1,100.00 | 1,300.00 | 950.00 |
| 10 | 800.00 | 1,100.00 | 1,300.00 | 950.00 |
| 11 | 800.00 | 1,100.00 | 1,800.00 | 1,250.00 |
| 12 | 800.00 | 1,100.00 | 1,600.00 | 1,200.00 |
| 13-14 | 800.00 | 1,100.00 | 2,600.00 | 1,200.00 |

Cumulative revenue / cumulative billing / net position (+ liability, - asset):

| Step | C1 rev | C1 bill | C1 pos | C2 rev | C2 bill | C2 pos | C3 rev | C3 bill | C3 pos | C4 rev | C4 bill | C4 pos |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 02 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - | - | - | - | - | - |
| 03 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 04 | 295.69 | 300.00 | 4.31 | 58.85 | 0.00 | -58.85 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 05 | 360.11 | 400.00 | 39.89 | 58.85 | 0.00 | -58.85 | 48.32 | 200.00 | 151.68 | 111.29 | 150.00 | 38.71 |
| 06 | 360.11 | 400.00 | 39.89 | 105.00 | 0.00 | -105.00 | 166.85 | 400.00 | 233.15 | 210.22 | 250.00 | 39.78 |
| 07 | 166.85 | 500.00 | 333.15 | 105.00 | 20.00 | -85.00 | 166.85 | 400.00 | 233.15 | 210.22 | 250.00 | 39.78 |
| 08 | 166.85 | 500.00 | 333.15 | 128.87 | 20.00 | -108.87 | 166.85 | 400.00 | 233.15 | 210.22 | 250.00 | 39.78 |
| 09 | 166.85 | 500.00 | 333.15 | 110.19 | 20.00 | -90.19 | 166.85 | 400.00 | 233.15 | 210.22 | 250.00 | 39.78 |
| 10 | 161.55 | 500.00 | 338.45 | 110.19 | 20.00 | -90.19 | 166.85 | 400.00 | 233.15 | 210.22 | 250.00 | 39.78 |
| 11 | 161.55 | 500.00 | 338.45 | 110.19 | 20.00 | -90.19 | 173.84 | 400.00 | 226.16 | 210.22 | 250.00 | 39.78 |
| 12 | 161.55 | 500.00 | 338.45 | 110.19 | 20.00 | -90.19 | 215.95 | 400.00 | 184.05 | 226.52 | 250.00 | 23.48 |
| 13 | 161.55 | 500.00 | 338.45 | 110.19 | 20.00 | -90.19 | 248.09 | 400.00 | 151.91 | 226.52 | 250.00 | 23.48 |
| 14 | 800.00 | 800.00 | 0.00 | 1,100.00 | 1,100.00 | 0.00 | 2,600.00 | 2,600.00 | 0.00 | 1,200.00 | 1,200.00 | 0.00 |

Contract 2 is the only contract carried as a contract asset (unbilled A/R 15002) from step 04 through step 13. Every other contract stays a net contract liability.

### 4.4 Initial allocation (steps 02-03)

Extended SSP = qty x list price x (1 - midpoint discount), clamped to the +/- range. A price inside the range is used as the SSP.
Allocation = extended SSP / contract SSP x contract price.

| Contract | POB | SKU | Price | Qty | SSP low | SSP mid | SSP high | Extended SSP | Allocation |
|---|---|---|---|---|---|---|---|---|---|
| Contract 1 | POB #1 | Hardware 1 | 500 | 5 | 382.5000 | 450.0000 | 517.5000 | 500.0000 | 322.1011 |
| Contract 1 | POB #2 | Software 1 | 400 | 2 | 272.0000 | 320.0000 | 368.0000 | 368.0000 | 237.0664 |
| Contract 1 | POB #3 | Consulting 1 | 400 | 1 | 150.0000 | 150.0000 | 150.0000 | 150.0000 | 96.6303 |
| Contract 1 | POB #4 | Material Right - Hardware | 0 | 1,000 | 1,000.0000 | 1,000.0000 | 1,000.0000 | 1,000.0000 | 644.2022 |
| Contract 2 | POB #1 | Hardware 1 | 600 | 8 | 612.0000 | 720.0000 | 828.0000 | 612.0000 | 470.7692 |
| Contract 2 | POB #2 | Software 1 | 400 | 3 | 408.0000 | 480.0000 | 552.0000 | 408.0000 | 313.8462 |
| Contract 2 | POB #3 | Consulting 1 | 0 | 1 | 150.0000 | 150.0000 | 150.0000 | 150.0000 | 115.3846 |
| Contract 2 | VC #1 | Variable Consideration | -100 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Contract 3 | POB #1 | Hardware 1 | 500 | 5 | 382.5000 | 450.0000 | 517.5000 | 500.0000 | 322.1011 |
| Contract 3 | POB #2 | Software 1 | 400 | 2 | 272.0000 | 320.0000 | 368.0000 | 368.0000 | 237.0664 |
| Contract 3 | POB #3 | Consulting 1 | 400 | 1 | 150.0000 | 150.0000 | 150.0000 | 150.0000 | 96.6303 |
| Contract 3 | POB #4 | Material Right - Services | 0 | 1,000 | 1,000.0000 | 1,000.0000 | 1,000.0000 | 1,000.0000 | 644.2022 |
| Contract 4 | POB #1 | Hardware 1 | 600 | 8 | 612.0000 | 720.0000 | 828.0000 | 612.0000 | 445.1761 |
| Contract 4 | POB #2 | Software 1 | 400 | 4 | 544.0000 | 640.0000 | 736.0000 | 544.0000 | 395.7121 |
| Contract 4 | POB #3 | Consulting 1 | 150 | 1 | 150.0000 | 150.0000 | 150.0000 | 150.0000 | 109.1118 |
| Contract 4 | VC #1 | Variable Consideration | -200 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### 4.5 Cumulative catch-ups recorded by modifications

| Step | Contract | POB | SKU | D/N | Catch-up (posted as Current Rev Rec) | Remaining allocation after | Revenue cum after |
|---|---|---|---|---|---|---|---|
| 08 | Contract 2 | POB #1 | Hardware 1 | Distinct | 13.3761 | 700.9804 | 72.2222 |
| 08 | Contract 2 | POB #3 | Consulting 1 | Nondistinct | 10.4910 | 84.9673 | 56.6449 |
| 09 | Contract 2 | POB #1 | Hardware 1 | Distinct | -18.6813 | 519.6617 | 53.5409 |
| 10 | Contract 1 | POB #3 | Consulting 1 | Nondistinct | -5.2988 | 43.0163 | 43.0163 |
| 11 | Contract 3 | POB #3 | Consulting 1 | Nondistinct | 6.9936 | 55.3087 | 55.3087 |
| 12 | Contract 3 | POB #2 | Software 1 | Distinct | 34.8800 | 153.4132 | 153.4132 |
| 12 | Contract 3 | POB #3 | Consulting 1 | Nondistinct | 7.2238 | 62.5326 | 62.5326 |
| 12 | Contract 4 | POB #1 | Hardware 1 | Distinct | 8.6276 | 359.7649 | 119.9216 |
| 12 | Contract 4 | POB #2 | Software 1 | Distinct | 7.6690 | 319.7910 | 106.5970 |
| 13 | Contract 3 | POB #3 | Consulting 1 | Nondistinct | 32.1394 | 94.6720 | 94.6720 |

The three mod handlers treat catch-ups differently:
- **Retrospective mods** (steps 08, 12) re-allocate the whole contract, then catch up **every** delivered POB, distinct or not.
- **POB-specific VC** (step 09) adds the price change to one POB only and catches up that POB.
- **Prospective mods** (steps 10, 11, 13) re-allocate only the unrecognised price across remaining SSP, and catch up **non-distinct** POBs only.

### 4.6 Month-end and full-year JE on the final database

| Period | Gross JE (Dr / Cr by account) | Delta JE (Revenue Adjustment JEs) |
|---|---|---|
| 2023-01 | Dr 15002 58.85, 21001 295.69 / Cr 5001 187.69, 5002 118.53, 5003 48.32 (total 354.54 / 354.54, balanced) | Dr 5003 39.68, 15002 58.85, 21001 141.69 / Cr 5001 187.69, 5002 52.53 (total 240.22 / 240.22, balanced) |
| 2023-02 | Dr 21001 112.74, 21002 111.29 / Cr 5001 175.71, 5003 48.32 (total 224.03 / 224.03, balanced) | Dr 5001 38.71, 5003 151.68, 21001 64.42 / Cr 5001 64.42, 21001 151.68, 21002 38.71 (total 254.81 / 254.81, balanced) |
| 2023-03 | Dr 15002 46.15, 21001 118.53, 21002 98.93 / Cr 5002 217.46, 5003 46.15 (total 263.61 / 263.61, balanced) | same as gross |
| 2023-04 | Dr 5001 193.26, 21002 20.00 / Cr 15002 20.00, 21001 193.26 (total 213.26 / 213.26, balanced) | same as gross |
| 2023-05 | Dr 5001 5.31, 15002 5.19 / Cr 5003 10.49 (total 10.50 / 10.49, **OUT OF BALANCE +0.01**) | same as gross |
| 2023-06 | Dr 5003 5.30 / Cr 21001 5.30 (total 5.30 / 5.30, balanced) | same as gross |
| 2023-07 | Dr 21001 6.99 / Cr 5003 6.99 (total 6.99 / 6.99, balanced) | same as gross |
| 2023-08 | Dr 21001 42.10, 21002 16.30 / Cr 5001 8.63, 5002 42.55, 5003 7.22 (total 58.40 / 58.40, balanced) | same as gross |
| 2023-09 | Dr 21001 32.14 / Cr 5003 32.14 (total 32.14 / 32.14, balanced) | same as gross |
| 2023-10 | Dr 21001 2,990.36, 21002 2,053.48 / Cr 5001 2,060.34, 5002 1,108.62, 5003 1,784.70, 15002 90.19 (total 5,043.84 / 5,043.85, **OUT OF BALANCE -0.01**) | same as gross |
| 2023 full year | Dr 21001 3,400.00, 21002 2,300.00 / Cr 5001 2,233.81, 5002 1,487.17, 5003 1,979.02 (total 5,700.00 / 5,700.00, balanced) | Dr 5003 12.63, 21001 3,046.00, 21002 2,150.00 / Cr 5001 2,083.81, 5002 1,421.17, 5003 1,703.65 (total 5,208.63 / 5,208.63, balanced) |

The delta report is the gross JE with `Current Pre-ASC606 Revenue (Net Design Only)` debited to revenue and credited to deferred revenue. Pre-ASC606 revenue was loaded in January (66 on 5002, 88 on 5003) and February (200 on 5003, 150 on 5001), 504 in total. Full-year delta revenue is therefore 5,700.00 - 504.00 = 5,196.00.

## 5. Comparison with the shipped ASC606.db

- **What the shipped DB contains** (read only, from `fixtures/ASC606.shipped.db`):
  - 24 `Contract_Live` rows in three versions: CS 1.1 at `2025-05-09 09:11:44.708286`, CS 2.1 at `09:11:53.453841` and D&B 1.31 at `09:12:33.441992`.
  - 7 `SKU_SSP` rows.
  - This is the state **after step 04**, not after the full UAT.
- **Point-in-time equivalence.** After step 04 the replay has the same 24 rows and the same version keys (`Record Unique ID without time`, `Current Period`). On all 69 compared columns, the maximum numeric absolute difference is **0.0** and there are **no** text mismatches. `Processing Time Log` and `Record Unique ID` were excluded because they hold wall-clock time. The SQLite declared column types are identical, and `SKU_SSP` is identical.
- **Final state differences.** The replay ends with 106 rows. The 82 rows in versions 05 to 14 do not exist in the shipped DB:

| Version | Current Period | Rows | Contracts | In shipped DB |
|---|---|---|---|---|
| step-02 | 2023-01-01 | 8 | Contract 1, Contract 2 | yes |
| step-03 | 2023-02-01 | 8 | Contract 3, Contract 4 | yes |
| step-04 | 2023-01-31 | 8 | Contract 1, Contract 2 | yes |
| step-05 | 2023-02-28 | 12 | Contract 1, Contract 3, Contract 4 | no |
| step-06 | 2023-03-31 | 12 | Contract 2, Contract 3, Contract 4 | no |
| step-07 | 2023-04-30 | 8 | Contract 1, Contract 2 | no |
| step-08 | 2023-05-15 | 4 | Contract 2 | no |
| step-09 | 2023-05-31 | 4 | Contract 2 | no |
| step-10 | 2023-06-15 | 4 | Contract 1 | no |
| step-11 | 2023-07-15 | 8 | Contract 3, Contract 4 | no |
| step-12 | 2023-08-15 | 8 | Contract 3, Contract 4 | no |
| step-13 | 2023-09-15 | 5 | Contract 3 | no |
| step-14 | 2023-10-31 | 17 | Contract 1, Contract 2, Contract 3, Contract 4 | no |

Inference, not verified against the author: the shipped DB is a partial UAT run left in the repository. The replay ran on a different OS, Python and library stack from the author's Windows build, yet matches exactly at the same point. That suggests the calculations do not depend on the platform for this data. It says nothing about steps 05 to 14, for which no shipped reference exists.

## 6. Anomalies

Findings are grouped by evidence strength:
- **6.1 Observed:** seen in the UAT replay.
- **6.2 Confirmed:** reproduced by a probe that runs the original code outside the UAT (`legacy-harness/probes.py`, output in `golden/probes/`).
- **6.3 Code reading:** found by reading the code, not executed.
- **6.4 Judgement:** accounting-judgement observations. These are inference for accounting review, not defects in code.

### 6.1 Observed in the UAT replay

| # | Anomaly | Evidence | Implication for eRev Cloud |
|---|---|---|---|
| A1 | **JE reports go out of balance by 0.01** | October 2023 (step 14 and month-end): Dr 5,043.84 / Cr 5,043.85. The difference is Contract 2: deferred revenue 1,080.00 less unbilled A/R 90.19 = 989.81, against revenue lines 519.66 + 385.19 + 84.97 = 989.82. May 2023 month-end: Dr 10.50 / Cr 10.49. Cause: each row is rounded to 4 dp and lines that round to 0.00 are dropped. Revenue is then summed per POB but deferred revenue and unbilled A/R per contract, and each group is rounded to 2 dp with no balancing plug (l.2598-2651). | Every entry must balance. Put the rounding residual on a defined line, and store amounts as decimals. |
| A2 | **Floating-point residue in stored amounts** | Final DB: `Current Contract Position - Contract Level` holds 13 tiny non-zero values (e.g. 5.684e-14), `Current Reclass to UAR` 7 (5.463e-14), `Current Rev Rec - Cumulative` 3 (2.842e-14), `Current Contract Position - POB` 3, and the two matching `Previous` fields 2 each. A contract level of about -5.7e-14 produces a non-zero unbilled A/R reclass, which the JE rounding then hides. | Use decimal amounts with an explicit zero tolerance. |
| A3 | **Billing validation skips VC lines** | 11 VC versions have negative `Current Remaining Billing` (for example Contract 4 VC -200 then -100). The over-billing and negative-billing checks filter `ASC 606 Stratification != "VC"` (l.961-964, 1103-1105). | Model variable consideration as its own object with its own validation, not as a POB with a negative price. |
| A4 | **VC lines take a delivery quantity with no revenue effect** | Contract 4 VC was delivered 0.5 at 03.31 and 0.5 at 10.31, and Contract 2 VC 1.0 at 10.31, each billed -100 with Current Rev Rec 0. The VC price reduces TP through allocation (VC SSP 0, allocation 0). Its POB position (-100 / -200) offsets the other POBs. | Separate price reductions (credit memos) from delivery tracking. |
| A5 | **Unit SSP drifts after modifications** | Contract 2 POB #1: 76.50 -> 82.50 (step 08; +2 units at clamped mod SSP 207). Contract 3 POB #1: 100.00 -> 101.00 (step 11) -> 133.67 (step 12; 4 units removed at clamped -306, leaving SSP 401 on 3 units). | Remaining SSP per unit is a blended rate, and it drives retrospective progress and returns. Keep SSP history per layer. |
| A6 | **POB added by a mod has NULL original fields** | Contract 3 POB #5 (step 13): 11 `Original *` columns are NULL. `Current Pre-ASC606 Revenue (Net Design Only)`, its cumulative field and its `Previous` field stay NULL until the next upload. | Record creation-time values for every POB, whatever event created it. |
| A7 | **Reports crash on an empty database** | *Latest Contract Status* on steps 00-01 raised `Error Notification: Execution failed on sql ... no such table: Contract_Live`. | Return empty reports. |
| A8 | **Version rows multiply with contract size** | Any activity rewrites every POB of the contract. For example, step 05 wrote 12 rows for a 3-line upload, and step 14 wrote 17 rows for a 15-line upload. The JE design needs this, because each version reverses the previous unbilled A/R reclass. | Use event-sourced postings rather than full snapshots. |
| A9 | **JE scope has no billing** | The full-year gross JE debits deferred revenue 5,700.00 with no billing credits, so JE balances in 21001/21002 are not contract liabilities. | Generate billing entries, or reconcile to billing, so contract balances tie to the GL. |
| A10 | **Misleading grouping column in the JE report** | `Record Unique ID without time` holds the contract name on deferred revenue and unbilled A/R lines, but contract + POB + SKU on revenue lines (l.2594-2636). | Use explicit dimensions (contract, POB, entity, account). |
| A11 | **Clean checks (no anomaly)** | No handler validation failures. No negative remaining quantity, no negative remaining allocation, no allocation left after full delivery, and no infinities. At every step TP on the allocation basis equals TP on the billing basis, and the contract asset equals the sum of unbilled A/R reclass. Each POB's full-year revenue JE ties to its cumulative revenue within 0.01. | Keep these as invariants. |

### 6.2 Confirmed by probes (original code, outside the UAT)

| # | Probe | Observed legacy behaviour | Cause | Severity |
|---|---|---|---|---|
| P1 | Blank `Memo 3` on Contract 1 POB #2 and POB #3 in the 1.31 upload | The loader shows "Rev Rec Success", but POB #2 and #3 record **0 delivery and 0 billing** (baseline: 1.0 / 100 and 0.5 / 100). The January gross JE changes to Dr 15001 28.84, 15002 58.85, 21001 100.00 / Cr 5001 187.69. | l.909-913 group the upload by `Memo 1-3`; pandas `groupby` drops rows whose keys are NULL by default (`dropna=True`). | High: silent data loss. |
| P2 | No-op prospective mod (qty 0, billing 0) on Contract 1, dated 2023-02-15, after the 1.31 upload | The February gross JE has no lines. The February **Revenue Adjustment JE posts Dr 5002 66.00, Dr 5003 88.00 / Cr 21001 154.00**, which repeats January's Pre-ASC606 amounts. | Mods never reset `Current Pre-ASC606 Revenue (Net Design Only)` (l.1469-1473, 1965-1968, 2383-2386), and the delta report posts that field for every version in range (l.2966-2979). The UAT missed it because each mod followed an upload with zero Pre-ASC606 for that contract. | High, for delta-JE users. |
| P3 | Contract 1 POB #1 delivery of 7 against 5 remaining | Two popups: "Delivery/Billing load failed: Qty or billing loaded are greater than the remaining of the POBs. Check your uploads please.", then "Error Notification: The process is stopped for users to fix the file". Nothing is written (8 rows before and after). | Validation at l.959-974 works, but the message does not name the POB. | Low. |
| P4 | 2.28 upload loaded twice | Both uploads are accepted. The February gross JE doubles to 448.06 (single upload: 224.03). Contract 1 POB #1 delivered cumulative reaches 4.0 (single upload: 3.0). Contract 3 POB #3 becomes fully delivered, with Pre-ASC606 cumulative 400. | There is no de-duplication by file, event or period (l.1112-1154). The quantity cap is the only guard. | High: no idempotency. |

### 6.3 From code reading (not executed)

| # | Finding | Where |
|---|---|---|
| C1 | `browse_file_RetroMod` and `browse_file_POB_specific_VC` do not reset `Current SSP Delivered`; only the prospective handler does (l.1472). They also never `fillna(0)` `Current SSP Delivered - Cumulative`, so a POB added through a retrospective mod gets NULL cumulative SSP delivered and a NULL unbilled A/R reclass. | l.1965-1981, 2383-2399 |
| C2 | The prospective handler keeps only rows whose `Distinct or Nondistinct` is exactly "Distinct" or "Nondistinct". Any other spelling drops the POB from the new version without an error. | l.1521-1523, 1583-1584 |
| C3 | Unbilled A/R reclass divides by the contract's cumulative SSP delivered. If a contract's net position is negative while nothing has been delivered (for example a VC credit billed before delivery), the result is `x/0 * 0 = NaN`: a NULL reclass and no contract asset. | l.1081-1086 and repeats |
| C4 | Returns reverse revenue at `Current Remaining Unit Rev Rec`, not at the rate originally recognised. After a mod changes the remaining rate, a return reverses a different amount than was booked. The UAT return (step 07) came before any mod, so it reversed exactly 193.2607. | l.1028-1029 |
| C5 | "Latest version" is the text `MAX("Processing Time Log")` per POB key, with no transaction around the read-compute-append cycle. Concurrent use or a clock change can corrupt version selection. | l.882-902 and repeats |
| C6 | The purge, specific-history and specific-latest queries build SQL with f-strings and double-quoted literals, so a contract name containing `"` breaks the query (SQL injection risk). | l.504-507, 2747-2750, 2827-2836 |
| C7 | The SSP join key is `SSP Version` as text (`astype(str)` of an Excel date gives "2023-01-01"). A version typed as text in another format fails the join with "not matched with a SKU". | l.574, 664, 1248, 1732 |
| C8 | End-of-life gate: `ShutdownNotifier(datetime(2025, 12, 31, 23, 59))` quits the app within 60 s of launch after that date, and that date has passed. | l.3077-3102, 3215-3216 |

### 6.4 Accounting-judgement observations (inference; for accounting review)

- **J1 - Material right exercise re-allocates to existing POBs.** Step 13 processes the exercise as a prospective mod. Contract 3 POB #4's unrecognised allocation (833.7676) and the new consideration (1,000) are pooled and spread over **all** remaining POBs by remaining SSP. New POB #5 receives 1,268.1139, but POB #1 (existing hardware, 3 units open) also rises from 334.3408 to 678.0182, and POB #2 from 153.4132 to 311.1106. A reviewer may prefer to direct the material right amount to the goods acquired on exercise. eRev Cloud should make this a policy choice with separate golden values.
- **J2 - Two progress measures for catch-ups.** Retrospective catch-ups measure progress by SSP delivered (l.2019-2024); prospective catch-ups for non-distinct POBs measure it by quantity (l.1526-1536). They agree only while unit SSP is constant, which A5 shows it is not.
- **J3 - Catch-up scope is decided by the button.** A retrospective mod catches up distinct POBs (steps 08 and 12); a prospective mod never does. The code does not assess which modification treatment applies and records no rationale. The engine should capture that judgement and its evidence.
- **J4 - SSP clamp on negative quantities.** Removing units is valued at the lower-magnitude end of the range (-306 rather than the midpoint -360 for 4 hardware units), which leaves inflated SSP on the remaining units (A5).
- **J5 - Contract-level netting only.** The asset/liability split is made at contract level. POB positions offset one another (Contract 1 final: POB #2 +188.93, POB #3 +313.97, POB #4 -502.90), and the unbilled A/R reclass is spread by SSP delivered.
- **J6 - VC modelled as a negative-price line.** There is no expected-value or most-likely-amount estimate, no constraint, and no reassessment except through a manual mod (steps 08-09).

## 7. Candidate golden tests

`golden/golden-tests.json` holds **122 machine-readable cases** generated by `analyze.py`:

| Kind | Cases |
|---|---|
| contract_position (per step and contract) | 50 |
| journal_entry_totals (per step window, plus months and full year) | 24 |
| pob_position (final state) | 17 |
| initial_allocation | 16 |
| cumulative_catchup | 10 |
| legacy_probe | 4 |
| point_in_time_equivalence | 1 |

Suggested tolerance: 1e-4 on 4-dp amounts and exact cents on JE lines. Run the section 3 UAT through the engine and compare. The curated set below is what the engine test suite should start with. "Deviate" marks legacy behaviour the engine should intentionally not reproduce.

| ID | Scenario | Expected (legacy) | Engine |
|---|---|---|---|
| GT-01 | Setup allocation with SSP clamp (step 02, Contract 1) | Extended SSP 500 / 368 / 150 / 1,000; allocation 322.1011 / 237.0664 / 96.6303 / 644.2022; TP 1,300 | match |
| GT-02 | Negative VC price and below-range clamp (step 02, Contract 2) | HW 600 below low 612 -> 612; SW 400 -> 408; VC SSP 0; allocation 470.7692 / 313.8462 / 115.3846 / 0; TP 900 | match |
| GT-03 | Setup allocation (step 03, Contract 4) | contract SSP 1,306; allocation 445.1761 / 395.7121 / 109.1118 / 0; TP 950 | match |
| GT-04 | Duplicate progress lines are summed (step 04) | Contract 1 POB #1: delivery 2, billing 100, revenue 128.8404, remaining qty 3, remaining allocation 193.2607 | match |
| GT-05 | Contract-level netting to unbilled A/R (step 04, Contract 2) | position -58.8462 -> unbilled A/R reclass 58.8462 on POB #1; JE Dr 15002 58.85 / Cr 5001 58.85 (21002 nets to 0) | match |
| GT-06 | Unbilled A/R reclass split by cumulative SSP delivered (step 06, Contract 2) | level -105.00 -> POB #1 58.8462, POB #3 46.1538; JE Dr 15002 46.15 / Cr 5003 46.15 | match |
| GT-07 | Revenue Adjustment JE with Pre-ASC606 revenue (Jan 2023) | Dr 5003 39.68, 15002 58.85, 21001 141.69 / Cr 5001 187.69, 5002 52.53 | match |
| GT-08 | Return (step 07, Contract 1 POB #1: -3 qty, -200 billing) | revenue -193.2607; remaining qty 5; remaining allocation 322.1011; billing cumulative 0; JE Dr 5001 193.26 / Cr 21001 193.26 | match |
| GT-09 | Billing without delivery (step 07, Contract 2 POB #1 +20) | position -85.00 -> unbilled A/R 47.6374 / 37.3626; JE Dr 21002 20.00 / Cr 15002 20.00 | match |
| GT-10 | Retrospective increase (step 08, Contract 2 POB #1 +2 qty / +400) | mod SSP 207; TP 1,300; catch-up +13.3761 (POB #1), +10.4910 (POB #3); remaining allocation 700.9804 / 385.1852 / 84.9673; JE Dr 15002 23.87 / Cr 5001 13.38, 5003 10.49 | match |
| GT-11 | POB-specific VC (step 09, Contract 2 POB #1 -200) | catch-up -18.6813; remaining allocation 519.6617; other POBs unchanged; TP 1,100; JE Dr 5001 18.68 / Cr 15002 18.68 | match |
| GT-12 | Prospective reduction (step 10, Contract 1 POB #1 -5 / -500) | TP 800; POB #1 allocation 0; remaining allocation POB #2 92.5337, POB #4 502.9004; non-distinct catch-up POB #3 -5.2988 (remaining 43.0163); JE Dr 5003 5.30 / Cr 21001 5.30 | match |
| GT-13 | Prospective increase (step 11) | Contract 3 POB #1 +2 / +500: remaining SSP 707, allocation 587.3033, POB #4 830.6977, POB #3 catch-up +6.9936. Contract 4 POB #3 +2 / +300: allocation 355.2772, TP 1,250. JE Dr 21001 6.99 / Cr 5003 6.99 | match |
| GT-14 | Retrospective reduction with negative-qty SSP clamp (step 12) | Contract 3 POB #1 -4 / -200: mod SSP -306, remaining SSP 401, TP 1,600, catch-up +34.8800 / +7.2238. Contract 4 POB #3 -0.5 / -50: mod SSP -75, TP 1,200, catch-up +8.6276 / +7.6690. JE Dr 21001 42.10, 21002 16.30 / Cr 5001 8.63, 5002 42.55, 5003 7.22 | match (policy J4) |
| GT-15 | Material right exercise with new POB (step 13, Contract 3) | POB #4 remaining allocation 833.7676 -> 0; POB #5 1,268.1139; POB #1 678.0182; POB #2 311.1106; POB #3 catch-up +32.1394; TP 2,600; JE Dr 21001 32.14 / Cr 5003 32.14 | match under the "prospective pool" policy; the alternative policy needs its own values (J1) |
| GT-16 | Full delivery end state (step 14) | all 17 POBs: remaining qty 0 and allocation 0; revenue = billing = TP per contract: 800 / 1,100 / 2,600 / 1,200; net position 0; POB detail in 4.2 | match |
| GT-17 | Month-end JE Jan-Oct 2023 by account (4.6) | e.g. Jan Dr/Cr 354.54; Feb 224.03; Mar 263.61; Apr 213.26; Aug 58.40; Sep 32.14 | match per account; **deviate** on May (+0.01) and Oct (-0.01): engine entries must balance (A1) |
| GT-18 | Full-year tie-out | revenue 5001 2,233.81, 5002 1,487.17, 5003 1,979.02 = 5,700.00; 21001 3,400.00; 21002 2,300.00; delta JE 5,208.63 balanced; each POB's revenue ties to cumulative revenue within 0.01 | match |
| GT-19 | Contract rollforward after each step (4.3; 50 cases) | TP, revenue, billing, position and unbilled A/R per contract and step | match |
| GT-20 | Shipped DB equivalence (after step 04) | 24 rows, 69 columns, 0 mismatches against `ASC606.db` | legacy regression lock (harness only) |
| GT-21 | Over-delivery rejected (P3) | load fails, 0 rows written | match; the message should name the POB |
| GT-22 | Blank memo must not drop progress lines (P1) | legacy: POB #2 / #3 get 0 delivery | **deviate**: expect the step-04 baseline (POB #2 1.0 / 118.5332; POB #3 0.5 / 48.3152) |
| GT-23 | A mod must not re-post Pre-ASC606 revenue (P2) | legacy Feb delta JE: Dr 5002 66, 5003 88 / Cr 21001 154 | **deviate**: no February delta lines |
| GT-24 | Duplicate upload (P4) | legacy Feb gross JE 448.06; Contract 1 POB #1 delivered cumulative 4.0 | **deviate**: reject or de-duplicate -> 224.03 and 3.0 |
| GT-25 | Rounding and zero tolerance (A1, A2) | legacy: 0.01 imbalances and e-14 residues | **deviate**: decimal amounts; each entry balances to the cent |

Mapping to legacy code: allocation l.681-717; delivery and billing l.1028-1089; prospective mod l.1440-1594; retrospective mod l.1923-2071; POB-specific VC l.2358-2478; JE reports l.2594-2651 and l.2920-2994.
