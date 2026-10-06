#!/usr/bin/env python3
"""eRev legacy golden-master replay harness.

Runs the ORIGINAL legacy eRev.py (a byte-identical copy in ./erev_copy) headless under
QT_QPA_PLATFORM=offscreen, replays the shipped UAT scenario from a reset database by
clicking the real FileBrowserWindow buttons, and snapshots database state and the four
built-in reports after every step.

Only UI and platform edges are stubbed (see install_stubs). No calculation line of
eRev.py is altered; the harness refuses to run if the copy's SHA-256 differs from the
legacy original.

Outputs
  <golden-dir>/NN-slug/        contract_live.csv, sku_ssp.csv, je_gross.csv, je_delta.csv,
                               contract_history.csv, latest_contracts.csv, popups.csv,
                               events.csv, step.json
  <golden-dir>/monthly/YYYY-MM  month-end JE, JE delta and contract history on the final DB
  <golden-dir>/compare-shipped  replay vs the shipped ops/libnew/libwarm/db/ASC606.db
  <golden-dir>/manifest.json    environment, hashes, step plan
  <out-dir>/NN-slug/            raw artefacts (ASC606.db copy, the app's own Excel exports,
                               un-normalised CSVs, Python warnings)
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import time
import warnings
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
COPY_DIR = HARNESS_DIR / "erev_copy"
FIXTURE_DB = HARNESS_DIR / "fixtures" / "ASC606.shipped.db"
DEFAULT_GOLDEN = HARNESS_DIR.parent / "docs" / "legacy" / "golden"
DEFAULT_OUT = HARNESS_DIR / "out"
LEGACY_SHA256 = "7fb658fbd72b9d7f8ca5dafa58ba34fabde9d101250b53f57ec45023e5e2bc14"
SHIPPED_DB_SHA256 = "6e35b508218420c670f3f19d0fb1df83b32ff498bb45e6bd47df68cbdf1aafc2"
DB_REL = Path("ops/libnew/libwarm/db/ASC606.db")
UAT = Path("ops/Example UATs")

# --------------------------------------------------------------------------------------
# Step plan. Order follows the task brief and the Processing Time Log order in the shipped
# DB (CS 1.1.2023 -> CS 2.1.2023 -> D&B 1.31.2023). Handler chosen from file name/template.
# --------------------------------------------------------------------------------------
STEPS = [
    dict(nn="00", slug="reset", button="button8", label="!Reset Database Completely!",
         handler="db_reset", file=None, date_input=None, effective=None),
    dict(nn="01", slug="ssp-upload", button="button1", label="Load SSPs",
         handler="browse_file_SSPs", file=UAT / "SSP Upload UAT/SKU SSP Template.xlsx",
         date_input=None, effective=None),
    dict(nn="02", slug="contract-setup-2023-01-01", button="button2", label="Load Contracts",
         handler="browse_file_Contracts",
         file=UAT / "Contract Setup UAT/Contract Setup Template 1.1.2023.xlsx",
         date_input=None, effective="2023-01-01"),
    dict(nn="03", slug="contract-setup-2023-02-01", button="button2", label="Load Contracts",
         handler="browse_file_Contracts",
         file=UAT / "Contract Setup UAT/Contract Setup Template 2.1.2023.xlsx",
         date_input=None, effective="2023-02-01"),
    dict(nn="04", slug="delivery-billing-2023-01-31", button="button3",
         label="Load Delivery and Billing", handler="browse_file_Deliveries",
         file=UAT / "Delivery and Billing UAT/Contract Progress Tracking Template 1.31.2023.xlsx",
         date_input="2023-01-31", effective="2023-01-31"),
    dict(nn="05", slug="delivery-billing-2023-02-28", button="button3",
         label="Load Delivery and Billing", handler="browse_file_Deliveries",
         file=UAT / "Delivery and Billing UAT/Contract Progress Tracking Template 2.28.2023.xlsx",
         date_input="2023-02-28", effective="2023-02-28"),
    dict(nn="06", slug="delivery-billing-2023-03-31", button="button3",
         label="Load Delivery and Billing", handler="browse_file_Deliveries",
         file=UAT / "Delivery and Billing UAT/Contract Progress Tracking Template 3.31.2023.xlsx",
         date_input="2023-03-31", effective="2023-03-31"),
    dict(nn="07", slug="delivery-billing-2023-04-30-return-zero", button="button3",
         label="Load Delivery and Billing", handler="browse_file_Deliveries",
         file=UAT / "Delivery and Billing UAT/Contract Progress Tracking Template 4.30.2023 - Return & Zero delivery billing.xlsx",
         date_input="2023-04-30", effective="2023-04-30"),
    dict(nn="08", slug="retro-mod-2023-05-15-vc-pob-increase", button="button5",
         label="Retrospective Contract Mod", handler="browse_file_RetroMod",
         file=UAT / "Contract Mod UAT/Contract Modification Template 05.15.2023 - retrospective vc + POB increases.xlsx",
         date_input="2023-05-15", effective="2023-05-15"),
    dict(nn="09", slug="pob-specific-vc-2023-05-31", button="button5_1", label="POB Specific VC",
         handler="browse_file_POB_specific_VC",
         file=UAT / "Contract Mod UAT/Contract Modification Template 05.31.2023 - retrospective POB specific VC.xlsx",
         date_input="2023-05-31", effective="2023-05-31"),
    dict(nn="10", slug="prospective-mod-2023-06-15-reduction", button="button4",
         label="Prospective Contract Mod", handler="browse_file_ProsMod",
         file=UAT / "Contract Mod UAT/Contract Modification Template 06.15.2023 - prospective reduction.xlsx",
         date_input="2023-06-15", effective="2023-06-15"),
    dict(nn="11", slug="prospective-mod-2023-07-15-pob-increase", button="button4",
         label="Prospective Contract Mod", handler="browse_file_ProsMod",
         file=UAT / "Contract Mod UAT/Contract Modification Template 07.15.2023 - prospective POB increases.xlsx",
         date_input="2023-07-15", effective="2023-07-15"),
    dict(nn="12", slug="retro-mod-2023-08-15-pob-reduction", button="button5",
         label="Retrospective Contract Mod", handler="browse_file_RetroMod",
         file=UAT / "Contract Mod UAT/Contract Modification Template 08.15.2023 - retrospective POB reduction.xlsx",
         date_input="2023-08-15", effective="2023-08-15"),
    dict(nn="13", slug="prospective-mod-2023-09-15-material-right-new-pob", button="button4",
         label="Prospective Contract Mod", handler="browse_file_ProsMod",
         file=UAT / "Contract Mod UAT/Contract Modification Template 09.15.2023 - material right exericse with new POB added (propsective).xlsx",
         date_input="2023-09-15", effective="2023-09-15"),
    dict(nn="14", slug="full-delivery-2023-10-31", button="button3",
         label="Load Delivery and Billing", handler="browse_file_Deliveries",
         file=UAT / "Delivery and Billing UAT/Full delivery 10.31.2023.xlsx",
         date_input="2023-10-31", effective="2023-10-31"),
]

SUCCESS_TITLES = {
    "ASC606 database reset", "SSPs are set up", "Contracts are set up", "Rev Rec Success",
    "Mod Success", "POB Specific VC Successfully Applied!",
}


def assign_report_windows(steps):
    """Step report window = [max(first of month, latest earlier step date + 1 day), step date]."""
    prior = []
    for s in steps:
        if not s["effective"]:
            s["window"] = None
            continue
        d = dt.date.fromisoformat(s["effective"])
        candidates = [d.replace(day=1)] + [p + dt.timedelta(days=1) for p in prior if p < d]
        s["window"] = (max(candidates).isoformat(), d.isoformat())
        prior.append(d)


# --------------------------------------------------------------------------------------
# Event capture shared by all stubs
# --------------------------------------------------------------------------------------
class EventLog:
    def __init__(self):
        self.records = []
        self.step = None
        self.phase = None

    def add(self, category, kind, title, text, answer=""):
        self.records.append(dict(step=self.step, phase=self.phase, seq=len(self.records) + 1,
                                 category=category, kind=kind, title=str(title), text=str(text),
                                 answer=str(answer)))

    def for_step(self, nn, category=None):
        return [r for r in self.records if r["step"] == nn and (category is None or r["category"] == category)]


EVENT_COLUMNS = ["step", "phase", "seq", "category", "kind", "title", "text", "answer"]
EVENTS = EventLog()
FILE_QUEUE: list[str] = []
INPUT_QUEUE: list[str] = []
CAPTURED_FRAMES: list = []


def install_stubs(legacy, QtWidgets):
    """Stub only UI/platform edges. Every stub records what the app asked and what was fed."""
    RealMB = QtWidgets.QMessageBox

    class FakeMessageBox:
        # Enum pass-through so expressions like QMessageBox.Yes | QMessageBox.No still evaluate.
        Yes = RealMB.StandardButton.Yes
        No = RealMB.StandardButton.No
        Ok = RealMB.StandardButton.Ok
        Information = RealMB.Icon.Information
        Warning = RealMB.Icon.Warning
        Critical = RealMB.Icon.Critical
        Question = RealMB.Icon.Question

        def __init__(self, *a, **k):
            self._title, self._text, self._icon = "", "", None

        def setWindowIcon(self, *a, **k):
            pass

        def setIcon(self, icon):
            self._icon = icon

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def exec(self):
            EVENTS.add("popup", "QMessageBox().exec", self._title, self._text, "Ok")
            return FakeMessageBox.Ok

        exec_ = exec

        @staticmethod
        def information(parent, title, text, *a, **k):
            EVENTS.add("popup", "QMessageBox.information", title, text, "Ok")
            return FakeMessageBox.Ok

        @staticmethod
        def warning(parent, title, text, *a, **k):
            EVENTS.add("popup", "QMessageBox.warning", title, text, "Ok")
            return FakeMessageBox.Ok

        @staticmethod
        def critical(parent, title, text, *a, **k):
            EVENTS.add("popup", "QMessageBox.critical", title, text, "Ok")
            return FakeMessageBox.Ok

        @staticmethod
        def question(parent, title, text, *a, **k):
            EVENTS.add("popup", "QMessageBox.question", title, text, "Yes")
            return FakeMessageBox.Yes

    class FakeInputDialog:
        @staticmethod
        def getText(parent, title, label, *a, **k):
            if not INPUT_QUEUE:
                EVENTS.add("input", "QInputDialog.getText", title, label, "<cancelled: queue empty>")
                return "", False
            value = INPUT_QUEUE.pop(0)
            EVENTS.add("input", "QInputDialog.getText", title, label, value)
            return value, True

    class FakeFileDialog:
        def __init__(self, *a, **k):
            pass

        def getOpenFileName(self, parent=None, caption="", *a, **k):
            if not FILE_QUEUE:
                EVENTS.add("file", "QFileDialog.getOpenFileName", caption, "", "<cancelled: queue empty>")
                return "", ""
            path = FILE_QUEUE.pop(0)
            try:
                shown = os.path.relpath(path, COPY_DIR)
            except ValueError:
                shown = path
            if shown.startswith(".."):
                shown = Path(path).name
            EVENTS.add("file", "QFileDialog.getOpenFileName", caption, shown, "selected")
            return path, ""

    class _FakeWinFunction:
        def __init__(self, dll, name):
            self.dll, self.name, self.argtypes, self.restype = dll, name, None, None

        def __call__(self, *args):
            arg0 = getattr(args[0], "value", args[0]) if args else ""
            EVENTS.add("platform", "ctypes.WinDLL", f"{self.dll}.{self.name}", arg0,
                       "1 (stubbed success, no encryption)")
            return 1

    class FakeWinDLL:
        def __init__(self, name, *a, **k):
            object.__setattr__(self, "_dll_name", name)

        def __getattr__(self, attr):
            if attr.startswith("_"):
                raise AttributeError(attr)
            fn = _FakeWinFunction(self._dll_name, attr)
            object.__setattr__(self, attr, fn)
            return fn

    def stub_load_license_key(self):
        EVENTS.add("platform", "license", "load_license_key", "stubbed: no .env read, no LicenseKeyDialog", "None")
        return None

    def stub_show_notification_and_disable(self):
        EVENTS.add("platform", "license", "show_notification_and_disable",
                   "stubbed: premium notice suppressed, premium buttons left enabled", "")

    RealPopup = legacy.DataFramePopup

    class RecordingDataFramePopup(RealPopup):
        def __init__(self, dataframe):
            CAPTURED_FRAMES.append(dataframe.copy())
            super().__init__(dataframe)

    # Module-global rebinding only; eRev.py source is untouched.
    legacy.QMessageBox = FakeMessageBox
    legacy.QInputDialog = FakeInputDialog
    legacy.QFileDialog = FakeFileDialog
    legacy.DataFramePopup = RecordingDataFramePopup
    legacy.FileBrowserWindow.load_license_key = stub_load_license_key
    legacy.FileBrowserWindow.show_notification_and_disable = stub_show_notification_and_disable
    ctypes.WinDLL = FakeWinDLL  # macOS has no WinDLL; eRev wraps EncryptFileW in try/except


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(pd, db_path: Path, table: str):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return None
        return pd.read_sql_query(f'SELECT * FROM "{table}" ORDER BY rowid', con)
    finally:
        con.close()


def table_schema(db_path: Path, table: str):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info("{table}")')]
    finally:
        con.close()


class TimeTokens:
    """Replace wall-clock Processing Time Log values with the step that wrote them."""

    def __init__(self):
        self.map: dict[str, str] = {}

    def register(self, raw_values, nn):
        new = sorted({str(v) for v in raw_values if v is not None and str(v) not in self.map})
        for i, v in enumerate(new):
            self.map[v] = f"step-{nn}" if len(new) == 1 else f"step-{nn}.{i + 1}"
        return new

    def token(self, v):
        if v is None:
            return v
        s = str(v)
        return self.map.get(s, s)

    def normalize(self, df):
        if df is None:
            return None
        df = df.copy()
        if "Processing Time Log" in df.columns:
            df["Processing Time Log"] = df["Processing Time Log"].map(self.token)
        if "Record Unique ID" in df.columns:
            def fix(v):
                if not isinstance(v, str):
                    return v
                for raw, tok in self.map.items():
                    if v.startswith(raw + " "):
                        return tok + v[len(raw):]
                return v
            df["Record Unique ID"] = df["Record Unique ID"].map(fix)
        return df


def write_csv(df, path: Path, columns_if_empty=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if df is None:
        import pandas as pd
        df = pd.DataFrame(columns=columns_if_empty or [])
    df.to_csv(path, index=False, lineterminator="\n")


def je_totals(df):
    if df is None or df.empty:
        return dict(lines=0, by_account=[], total_debit=0.0, total_credit=0.0, net=0.0)
    rows = []
    for acct, grp in df.groupby("Account", sort=True):
        debit = float(grp.loc[grp["Amount"] > 0, "Amount"].sum())
        credit = float(-grp.loc[grp["Amount"] < 0, "Amount"].sum())
        rows.append(dict(account=str(int(acct)) if float(acct).is_integer() else str(acct),
                         debit=round(debit, 2), credit=round(credit, 2), net=round(debit - credit, 2)))
    total_debit = float(df.loc[df["Amount"] > 0, "Amount"].sum())
    total_credit = float(-df.loc[df["Amount"] < 0, "Amount"].sum())
    return dict(lines=int(len(df)), by_account=rows, total_debit=round(total_debit, 2),
                total_credit=round(total_credit, 2), net=round(total_debit - total_credit, 6))


def collect_app_exports(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for f in COPY_DIR.glob("*.xlsx"):
        target = dest / f.name
        if target.exists():
            target.unlink()
        shutil.move(str(f), str(target))
        moved.append(f.name)
    return moved


def preflight(allow_modified: bool) -> str:
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        print("setting QT_QPA_PLATFORM=offscreen")
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    copy_sha = sha256(COPY_DIR / "eRev.py")
    if copy_sha != LEGACY_SHA256 and not allow_modified:
        sys.exit(f"erev_copy/eRev.py sha256 {copy_sha} != legacy {LEGACY_SHA256}; re-run setup.sh")
    if not FIXTURE_DB.exists() or sha256(FIXTURE_DB) != SHIPPED_DB_SHA256:
        sys.exit(f"fixture {FIXTURE_DB} missing or not the shipped DB; re-run setup.sh")
    return copy_sha


class Legacy:
    """The booted legacy app: eRev module (with stubs), QApplication and the real FileBrowserWindow."""

    def __init__(self):
        os.chdir(COPY_DIR)  # eRev uses relative paths for the DB and images
        if str(COPY_DIR) not in sys.path:
            sys.path.insert(0, str(COPY_DIR))
        from PySide6 import QtWidgets
        import eRev as legacy  # module import: the __main__ block (ShutdownNotifier, app.exec) never runs

        install_stubs(legacy, QtWidgets)
        self.QtWidgets = QtWidgets
        self.module = legacy
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["eRev-harness"])
        EVENTS.step, EVENTS.phase = "init", "FileBrowserWindow.__init__"
        self.window = legacy.FileBrowserWindow()
        self.app.processEvents()
        self.db_path = COPY_DIR / DB_REL

    def click(self, button_attr, label, file=None, date_input=None, phase=None):
        """Click a real main-window button with the file path and date queued for the stubbed dialogs."""
        button = getattr(self.window, button_attr)
        assert button.text() == label, f"button {button_attr} text {button.text()!r} != {label!r}"
        FILE_QUEUE[:] = [str(file)] if file else []
        INPUT_QUEUE[:] = [date_input] if date_input else []
        EVENTS.phase = phase or f"handler:{button_attr}"
        time.sleep(0.01)  # guarantee strictly increasing pd.Timestamp.now() between steps
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            button.click()
            self.app.processEvents()
        unused = FILE_QUEUE + INPUT_QUEUE
        FILE_QUEUE.clear()
        INPUT_QUEUE.clear()
        return list(caught), unused

    def report(self, dialog_cls, button_text, inputs, phase):
        """Open a real report dialog and click its button (the slot needs self.sender())."""
        QtWidgets = self.QtWidgets
        EVENTS.phase = phase
        CAPTURED_FRAMES.clear()
        INPUT_QUEUE[:] = list(inputs)
        dlg = getattr(self.module, dialog_cls)(self.window)
        buttons = [b for b in dlg.findChildren(QtWidgets.QPushButton) if b.text() == button_text]
        assert len(buttons) == 1, f"{dialog_cls} button {button_text!r} not found"
        buttons[0].click()
        self.app.processEvents()
        frame = CAPTURED_FRAMES[-1] if CAPTURED_FRAMES else None
        popup = getattr(self.window, "journal_window", None)
        if popup is not None:
            popup.close()
            popup.deleteLater()
            self.window.journal_window = None
        dlg.deleteLater()
        self.app.processEvents()
        leftover = list(INPUT_QUEUE)
        INPUT_QUEUE.clear()
        return frame, leftover

    def close(self):
        self.window.close()
        self.app.processEvents()


# --------------------------------------------------------------------------------------
# Main replay
# --------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--golden-dir", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--allow-modified-copy", action="store_true",
                    help="run even if erev_copy/eRev.py differs from the legacy original")
    args = ap.parse_args()
    golden = Path(args.golden_dir).expanduser().resolve()
    out = Path(args.out_dir).expanduser().resolve()
    copy_sha = preflight(args.allow_modified_copy)

    # Clean previous outputs produced by this harness only (probes.py manages golden/probes).
    golden.mkdir(parents=True, exist_ok=True)
    for child in golden.iterdir():
        if child.is_dir() and (re.match(r"^\d\d-", child.name) or child.name in {"monthly", "compare-shipped"}):
            shutil.rmtree(child)
        elif child.is_file() and child.name in {"manifest.json", "popups-all.csv", "summary.json"}:
            child.unlink()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # Start from the shipped DB so the Reset button has something to wipe; drop stray exports.
    shutil.copyfile(FIXTURE_DB, COPY_DIR / DB_REL)
    collect_app_exports(out / "_stray_exports_before_run")

    import numpy as np
    import openpyxl
    import pandas as pd
    import PySide6
    import dotenv

    L = Legacy()
    assign_report_windows(STEPS)
    live_cols = [c for c, _ in table_schema(FIXTURE_DB, "Contract_Live")]
    ssp_cols = [c for c, _ in table_schema(FIXTURE_DB, "SKU_SSP")]
    tokens = TimeTokens()
    summary_steps = []
    live_by_step = {}
    db_path = L.db_path

    for s in STEPS:
        nn = s["nn"]
        step_dir = golden / f"{nn}-{s['slug']}"
        raw_dir = out / f"{nn}-{s['slug']}"
        step_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        EVENTS.step = nn

        before = read_table(pd, db_path, "Contract_Live")
        rows_before = 0 if before is None else len(before)
        caught, unused_inputs = L.click(s["button"], s["label"], COPY_DIR / s["file"] if s["file"] else None,
                                        s["date_input"], f"handler:{s['handler']}")

        live = read_table(pd, db_path, "Contract_Live")
        ssp = read_table(pd, db_path, "SKU_SSP")
        rows_after = 0 if live is None else len(live)
        new_tokens = tokens.register(live["Processing Time Log"].unique() if live is not None else [], nn)
        live_by_step[nn] = live

        # Absent tables (steps 00-01) are written header-only using the shipped schema.
        write_csv(tokens.normalize(live), step_dir / "contract_live.csv", live_cols)
        write_csv(ssp, step_dir / "sku_ssp.csv", ssp_cols)
        if live is not None:
            write_csv(live, raw_dir / "contract_live.raw.csv")
        shutil.copyfile(db_path, raw_dir / "ASC606.db")

        je_gross = je_delta = history = None
        report_leftovers = {}
        latest, report_leftovers["latest_contracts"] = L.report(
            "LatestContractDialog", "Check All Latest Contract", [], "report:latest_contracts")
        if s["window"]:
            start, end = s["window"]
            je_gross, report_leftovers["je_gross"] = L.report(
                "CustomDialog", "Gross Revenue JEs", [start, end], "report:je_gross")
            je_delta, report_leftovers["je_delta"] = L.report(
                "CustomDialog", "Revenue Adjustment JEs", [start, end], "report:je_delta")
            history, report_leftovers["contract_history"] = L.report(
                "ContractDialog", "Check All Contract History", [start, end], "report:contract_history")
        write_csv(tokens.normalize(latest), step_dir / "latest_contracts.csv", live_cols)
        write_csv(je_gross, step_dir / "je_gross.csv", ["Record Unique ID without time", "Account", "Amount"])
        write_csv(je_delta, step_dir / "je_delta.csv", ["Record Unique ID without time", "Account", "Amount"])
        write_csv(tokens.normalize(history), step_dir / "contract_history.csv", live_cols)
        exports = collect_app_exports(raw_dir / "app_exports")

        step_events = EVENTS.for_step(nn)
        popups = [e for e in step_events if e["category"] == "popup"]
        write_csv(pd.DataFrame(popups, columns=EVENT_COLUMNS), step_dir / "popups.csv")
        write_csv(pd.DataFrame(step_events, columns=EVENT_COLUMNS), step_dir / "events.csv")

        warn_rows = []
        for w in caught:
            fn = str(w.filename)
            if fn.startswith(str(COPY_DIR)):
                fn = os.path.relpath(fn, COPY_DIR)
            warn_rows.append(dict(category=w.category.__name__, file=fn, line=w.lineno, message=str(w.message)))
        warn_df = pd.DataFrame(warn_rows, columns=["category", "file", "line", "message"])
        write_csv(warn_df, raw_dir / "python_warnings.csv")
        warn_summary = (warn_df.groupby(["category", "file", "line", "message"]).size()
                        .reset_index(name="count").to_dict("records")) if len(warn_df) else []

        handler_popups = [p for p in popups if p["phase"].startswith("handler:")]
        success = any(p["title"] in SUCCESS_TITLES for p in handler_popups) and not any(
            p["kind"] == "QMessageBox.critical" for p in handler_popups)
        rec = dict(
            nn=nn, slug=s["slug"], handler=s["handler"], button=s["button"], button_label=s["label"],
            file=str(s["file"]) if s["file"] else None,
            file_sha256=sha256(COPY_DIR / s["file"]) if s["file"] else None,
            date_input=s["date_input"], report_window=s["window"],
            contract_live_table_exists=live is not None, sku_ssp_table_exists=ssp is not None,
            rows_before=rows_before, rows_after=rows_after, rows_appended=rows_after - rows_before,
            new_version_tokens=[tokens.token(v) for v in new_tokens],
            sku_ssp_rows=0 if ssp is None else len(ssp),
            handler_success=success,
            handler_popups=[dict(kind=p["kind"], title=p["title"], text=p["text"]) for p in handler_popups],
            report_popups=len(popups) - len(handler_popups),
            unused_queued_inputs=unused_inputs, report_unused_inputs=report_leftovers,
            reports_captured=dict(latest_contracts=latest is not None, je_gross=je_gross is not None,
                                  je_delta=je_delta is not None, contract_history=history is not None),
            je_gross_totals=je_totals(je_gross) if s["window"] else None,
            je_delta_totals=je_totals(je_delta) if s["window"] else None,
            contract_history_rows=None if history is None else len(history),
            latest_contract_rows=None if latest is None else len(latest),
            app_excel_exports=sorted(exports),
            python_warnings=warn_summary,
        )
        (step_dir / "step.json").write_text(json.dumps(rec, indent=2, default=str) + "\n")
        summary_steps.append(rec)
        print(f"[{nn}] {s['slug']:<50} rows {rows_before:>3} -> {rows_after:>3}  success={success}  "
              f"popups={[p['title'] for p in handler_popups]}")

    # ---------------- month-end reports on the final DB ----------------
    EVENTS.step = "monthly"
    monthly = []
    for month in range(1, 11):
        start = dt.date(2023, month, 1)
        end = (dt.date(2023, month + 1, 1) - dt.timedelta(days=1))
        mdir = golden / "monthly" / f"2023-{month:02d}"
        mdir.mkdir(parents=True)
        g, _ = L.report("CustomDialog", "Gross Revenue JEs", [start.isoformat(), end.isoformat()], f"monthly:{month:02d}:je_gross")
        d, _ = L.report("CustomDialog", "Revenue Adjustment JEs", [start.isoformat(), end.isoformat()], f"monthly:{month:02d}:je_delta")
        h, _ = L.report("ContractDialog", "Check All Contract History", [start.isoformat(), end.isoformat()], f"monthly:{month:02d}:contract_history")
        write_csv(g, mdir / "je_gross.csv", ["Record Unique ID without time", "Account", "Amount"])
        write_csv(d, mdir / "je_delta.csv", ["Record Unique ID without time", "Account", "Amount"])
        write_csv(tokens.normalize(h), mdir / "contract_history.csv")
        monthly.append(dict(month=f"2023-{month:02d}", window=[start.isoformat(), end.isoformat()],
                            je_gross_totals=je_totals(g), je_delta_totals=je_totals(d),
                            contract_history_rows=None if h is None else len(h)))
    ydir = golden / "monthly" / "2023-full-year"
    ydir.mkdir(parents=True)
    g, _ = L.report("CustomDialog", "Gross Revenue JEs", ["2023-01-01", "2023-12-31"], "monthly:year:je_gross")
    d, _ = L.report("CustomDialog", "Revenue Adjustment JEs", ["2023-01-01", "2023-12-31"], "monthly:year:je_delta")
    write_csv(g, ydir / "je_gross.csv", ["Record Unique ID without time", "Account", "Amount"])
    write_csv(d, ydir / "je_delta.csv", ["Record Unique ID without time", "Account", "Amount"])
    monthly.append(dict(month="2023-full-year", window=["2023-01-01", "2023-12-31"],
                        je_gross_totals=je_totals(g), je_delta_totals=je_totals(d)))
    collect_app_exports(out / "monthly" / "app_exports")

    # ---------------- compare with the shipped DB ----------------
    cmp_dir = golden / "compare-shipped"
    cmp_dir.mkdir(parents=True)
    shipped = read_table(pd, FIXTURE_DB, "Contract_Live")
    shipped_ssp = read_table(pd, FIXTURE_DB, "SKU_SSP")
    final = live_by_step[STEPS[-1]["nn"]]
    final_ssp = read_table(pd, db_path, "SKU_SSP")

    def version_keys(df):
        return set(zip(df["Record Unique ID without time"], df["Current Period"]))

    shipped_keys = version_keys(shipped)
    matching_steps = [nn for nn, df in live_by_step.items()
                      if df is not None and len(df) == len(shipped) and version_keys(df) == shipped_keys]
    compare = dict(shipped_rows=len(shipped), shipped_versions=sorted(shipped["Processing Time Log"].unique().tolist()),
                   final_replay_rows=len(final), point_in_time_match_steps=matching_steps)

    ignore_cols = {"Processing Time Log", "Record Unique ID"}

    def ordinal(df):
        ranks = {v: i + 1 for i, v in enumerate(sorted(df["Processing Time Log"].unique()))}
        out_df = df.copy()
        out_df["_version"] = out_df["Processing Time Log"].map(ranks)
        return out_df.sort_values(["_version", "Record Unique ID without time"]).reset_index(drop=True)

    col_rows = []
    if matching_steps:
        rep = ordinal(live_by_step[matching_steps[0]])
        shp = ordinal(shipped)
        for col in shipped.columns:
            if col in ignore_cols:
                continue
            a, b = shp[col], rep[col] if col in rep.columns else None
            if b is None:
                col_rows.append(dict(column=col, status="missing in replay", mismatches=len(a), max_abs_diff=None))
                continue
            an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
            numeric = an.notna().sum() == a.notna().sum() and bn.notna().sum() == b.notna().sum() and a.notna().any()
            if numeric:
                both_nan = an.isna() & bn.isna()
                diff = (an - bn).abs()
                mism = int(((diff > 1e-9 * np.maximum(1.0, an.abs())) | (an.isna() != bn.isna())).sum())
                col_rows.append(dict(column=col, status="numeric", mismatches=mism,
                                     max_abs_diff=float(diff[~both_nan].max()) if (~both_nan).any() else 0.0))
            else:
                mism = int(((a.astype(str) != b.astype(str)) & ~(a.isna() & b.isna())).sum())
                col_rows.append(dict(column=col, status="text", mismatches=mism, max_abs_diff=None))
        compare["replay_extra_columns"] = [c for c in rep.columns if c not in shipped.columns and c != "_version"]
    col_df = pd.DataFrame(col_rows)
    write_csv(col_df, cmp_dir / "point_in_time_column_diffs.csv")
    compare["point_in_time_columns_with_mismatch"] = col_df.loc[col_df["mismatches"] > 0, "column"].tolist() if len(col_df) else None
    compare["schema_shipped"] = table_schema(FIXTURE_DB, "Contract_Live")
    compare["schema_replay"] = table_schema(db_path, "Contract_Live")
    compare["schema_differences"] = [
        dict(column=c, shipped=dict(compare["schema_shipped"]).get(c), replay=dict(compare["schema_replay"]).get(c))
        for c in dict(compare["schema_shipped"]) | dict(compare["schema_replay"])
        if dict(compare["schema_shipped"]).get(c) != dict(compare["schema_replay"]).get(c)]
    compare["sku_ssp_equal"] = bool(shipped_ssp.astype(str).equals(final_ssp.astype(str)))

    ver_rows = []
    fin = tokens.normalize(final)
    grp = fin.groupby(["Processing Time Log", "Current Period"]).agg(
        rows=("Record Unique ID without time", "size"),
        contracts=("Contract Unique Name", lambda x: ", ".join(sorted(set(map(str, x)))))).reset_index()
    for _, r in grp.iterrows():
        key_rows = final[final["Processing Time Log"].map(tokens.token) == r["Processing Time Log"]]
        in_shipped = all(k in shipped_keys for k in version_keys(key_rows))
        ver_rows.append(dict(version=r["Processing Time Log"], current_period=r["Current Period"], rows=int(r["rows"]),
                             contracts=r["contracts"], present_in_shipped=in_shipped))
    ver_df = pd.DataFrame(ver_rows)
    write_csv(ver_df, cmp_dir / "final_versions_vs_shipped.csv")
    write_csv(shipped, cmp_dir / "shipped_contract_live.csv")
    compare["final_versions_not_in_shipped"] = int((~ver_df["present_in_shipped"]).sum())
    compare["final_rows_not_in_shipped"] = int(ver_df.loc[~ver_df["present_in_shipped"], "rows"].sum())
    (cmp_dir / "compare.json").write_text(json.dumps(compare, indent=2, default=str) + "\n")

    # ---------------- manifest & aggregated popups ----------------
    all_events = pd.DataFrame(EVENTS.records)
    write_csv(all_events[all_events["category"] == "popup"], golden / "popups-all.csv")
    manifest = dict(
        harness="legacy-harness/replay.py",
        legacy_repo="~/dev/erev-legacy", legacy_commit="5ec25ffed763b561e86ac733d6583e762178791d",
        erev_py_sha256=copy_sha, erev_py_unmodified=copy_sha == LEGACY_SHA256,
        shipped_db_sha256=SHIPPED_DB_SHA256,
        environment=dict(python=platform.python_version(), platform=platform.platform(),
                         pandas=pd.__version__, numpy=np.__version__, PySide6=PySide6.__version__,
                         openpyxl=openpyxl.__version__, python_dotenv=getattr(dotenv, "__version__", "1.0.1"),
                         sqlite=sqlite3.sqlite_version, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM")),
        init_events=[e for e in EVENTS.records if e["step"] == "init"],
        steps=[dict(nn=s["nn"], slug=s["slug"], handler=s["handler"], button_label=s["label"],
                    file=str(s["file"]) if s["file"] else None, date_input=s["date_input"],
                    report_window=s["window"]) for s in STEPS],
        time_token_note="Processing Time Log and the timestamp prefix of Record Unique ID are replaced by "
                        "step-NN (the step that wrote the row); raw wall-clock values are in out/.",
    )
    (golden / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    (golden / "summary.json").write_text(json.dumps(dict(steps=summary_steps, monthly=monthly, compare=compare),
                                                    indent=2, default=str) + "\n")
    L.close()
    print("compare:", json.dumps({k: compare[k] for k in ("shipped_rows", "final_replay_rows",
                                                           "point_in_time_match_steps",
                                                           "point_in_time_columns_with_mismatch",
                                                           "final_versions_not_in_shipped")}, default=str))
    print(f"golden -> {golden}\nraw    -> {out}")


if __name__ == "__main__":
    main()
