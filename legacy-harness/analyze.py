#!/usr/bin/env python3
"""Derive golden-master tables, anomaly scans and golden-tests.json from docs/legacy/golden.

Reads only replay outputs (no Qt, no legacy code). Writes:
  <out>                              markdown fragments used in docs/legacy/07-golden-master.md
  <golden>/golden-tests.json         machine-readable expected values for the eRev Cloud engine
  <golden>/contract-rollforward.csv  contract-level position after every step
  <golden>/final-pob-positions.csv   POB-level position after the last step
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_GOLDEN = HARNESS_DIR.parent / "docs" / "legacy" / "golden"
DEFAULT_OUT = HARNESS_DIR / "out" / "analysis.md"

K, POB, SKU = "Contract Unique Name", "POB Unique ID", "SKU Name"
STRAT, DN = "ASC 606 Stratification", "Distinct or Nondistinct"
EXT_SSP, ORIG_ALLOC, ORIG_UNIT_SSP = "Original Extended SSP", "Original Allocation", "Original Unit SSP"
REM_QTY, REM_SSP, REM_ALLOC, REM_BILL = ("Current Remaining Qty", "Current Remaining SSP",
                                         "Current Remaining Allocation", "Current Remaining Billing")
UNIT_SSP, UNIT_RR = "Current Unit SSP", "Current Remaining Unit Rev Rec"
DLV, RR, BILL, PRE = ("Current Delivery", "Current Rev Rec", "Current Billing",
                      "Current Pre-ASC606 Revenue (Net Design Only)")
CATCH, CATCH_CUM = ("Current Cumulative Catchup - Disclosure Only",
                    "Current Cumulative Catchup - Cumulative - Disclosure Only")
DLV_CUM, RR_CUM, BILL_CUM = "Current Delivery - Cumulative", "Current Rev Rec - Cumulative", "Current Billing - Cumulative"
SSP_DLV_CUM = "Current SSP Delivered - Cumulative"
POS_POB, POS_K, UAR = "Current Contract Position - POB", "Current Contract Position - Contract Level", "Current Reclass to UAR"
TOL = 0.005


# ------------------------------------------------------------------ formatting helpers
def fnum(x, nd=2):
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    try:
        if pd.isna(x):
            return "NULL"
    except (TypeError, ValueError):
        return str(x)
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    v = round(float(x), nd)
    if v == 0:
        v = 0.0
    return f"{v:,.{nd}f}"


def md(df, nd=2, nds=None):
    nds = nds or {}
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fnum(r[c], nds.get(c, nd)).replace("|", "\\|") for c in cols) + " |")
    return "\n".join(out)


def je_compact(t):
    if not t or not t["by_account"]:
        return "no lines"
    dr = [f"{a['account']} {a['debit']:,.2f}" for a in t["by_account"] if a["debit"] > 0.0049]
    cr = [f"{a['account']} {a['credit']:,.2f}" for a in t["by_account"] if a["credit"] > 0.0049]
    diff = round(t["total_debit"] - t["total_credit"], 2)
    bal = "balanced" if abs(diff) < TOL else f"**OUT OF BALANCE {diff:+.2f}**"
    return (f"Dr {', '.join(dr) or '-'} / Cr {', '.join(cr) or '-'} "
            f"(total {t['total_debit']:,.2f} / {t['total_credit']:,.2f}, {bal})")


def read_csv(path: Path):
    try:
        return pd.read_csv(path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return pd.DataFrame()


# ------------------------------------------------------------------ loading
def load(golden: Path):
    steps = []
    for d in sorted(p for p in golden.iterdir() if p.is_dir() and re.match(r"^\d\d-", p.name)):
        meta = json.loads((d / "step.json").read_text())
        live = read_csv(d / "contract_live.csv")
        steps.append(dict(nn=meta["nn"], dir=d, meta=meta, live=live,
                          new=live[live["Processing Time Log"] == f"step-{meta['nn']}"] if len(live) else live,
                          latest=read_csv(d / "latest_contracts.csv"), je=read_csv(d / "je_gross.csv"),
                          delta=read_csv(d / "je_delta.csv"), popups=read_csv(d / "popups.csv")))
    summary = json.loads((golden / "summary.json").read_text())
    compare = json.loads((golden / "compare-shipped" / "compare.json").read_text())
    return steps, summary, compare


def contract_rollup(latest: pd.DataFrame):
    if latest.empty:
        return pd.DataFrame()
    rows = []
    for k, x in latest.groupby(K, sort=True):
        position = float(x[POS_POB].fillna(0).sum())
        rows.append({
            "contract": k, "pobs": len(x),
            "tp_allocation_basis": float((x[RR_CUM].fillna(0) + x[REM_ALLOC].fillna(0)).sum()),
            "tp_billing_basis": float((x[BILL_CUM].fillna(0) + x[REM_BILL].fillna(0)).sum()),
            "revenue_cum": float(x[RR_CUM].fillna(0).sum()),
            "billing_cum": float(x[BILL_CUM].fillna(0).sum()),
            "remaining_allocation": float(x[REM_ALLOC].fillna(0).sum()),
            "position": position,
            "contract_liability": max(position, 0.0),
            "contract_asset": max(-position, 0.0),
            "uar_reclass_field": float(x[UAR].fillna(0).sum()),
            "catchup_cum_disclosure": float(x[CATCH_CUM].fillna(0).sum()),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden-dir", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT.parent))
    ap.add_argument("--allow-modified-copy", action="store_true", help="accepted for run.sh symmetry; unused")
    args = ap.parse_args()
    args.out = str(Path(args.out_dir).expanduser().resolve() / "analysis.md")
    golden = Path(args.golden_dir).expanduser().resolve()
    steps, summary, compare = load(golden)
    by_nn = {s["nn"]: s for s in steps}
    md_out = []
    tests = dict(generated_from="docs/legacy/golden (legacy eRev.py replay)", tolerance=dict(amount_4dp=1e-4, je_2dp=0.0),
                 note="Values are legacy behaviour, including legacy defects flagged in 07-golden-master.md section 6.",
                 tests=[])

    # ---------------- 3. step table
    rows = []
    for s in steps:
        m = s["meta"]
        hp = "; ".join(f"{p['title']}" for p in m["handler_popups"])
        delta_same = m["je_delta_totals"] == m["je_gross_totals"]
        rows.append({
            "Step": m["nn"], "Handler (button)": f"`{m['handler']}` ({m['button_label']})",
            "File": Path(m["file"]).name if m["file"] else "-",
            "Date input": m["date_input"] or "-",
            "Rows after (+new)": f"{m['rows_after']} (+{m['rows_appended']})" if m["rows_appended"] >= 0 else f"{m['rows_after']} ({m['rows_appended']})",
            "Handler popups": hp,
            "Report window": " to ".join(m["report_window"]) if m["report_window"] else "-",
            "JE gross by account (Dr / Cr)": je_compact(m["je_gross_totals"]) if m["report_window"] else "n/a",
            "JE delta": ("same as gross" if delta_same else je_compact(m["je_delta_totals"])) if m["report_window"] else "n/a",
        })
    md_out.append("### Step table\n\n" + md(pd.DataFrame(rows)))
    for s in steps:
        m = s["meta"]
        if m["report_window"]:
            tests["tests"].append(dict(id=f"je-step-{m['nn']}", kind="journal_entry_totals", steps_through=m["nn"],
                                       window=m["report_window"], gross=m["je_gross_totals"], delta=m["je_delta_totals"],
                                       source=f"golden/{s['dir'].name}/je_gross.csv, je_delta.csv"))

    # report popups
    rp = []
    for s in steps:
        if len(s["popups"]):
            x = s["popups"][~s["popups"]["phase"].str.startswith("handler:")]
            for (kind, title), g in x.groupby(["kind", "title"]):
                rp.append({"Step": s["nn"], "Report popup": f"{kind}: {title}", "Count": len(g),
                           "Text (first 120 chars)": str(g["text"].iloc[0]).replace("\n", " ")[:120]})
    md_out.append("### Report popups per step\n\n" + md(pd.DataFrame(rp)))

    # ---------------- contract rollforward
    roll = []
    for s in steps:
        r = contract_rollup(s["latest"])
        if r.empty:
            continue
        r.insert(0, "step", s["nn"])
        roll.append(r)
    roll_df = pd.concat(roll, ignore_index=True)
    roll_df.to_csv(golden / "contract-rollforward.csv", index=False, lineterminator="\n")
    for metric, title in [("tp_allocation_basis", "Transaction price (sum of cumulative revenue + remaining allocation)"),
                          ("revenue_cum", "Cumulative revenue"), ("billing_cum", "Cumulative billing"),
                          ("position", "Contract position (billing - revenue; + liability / - asset)")]:
        pv = roll_df.pivot(index="step", columns="contract", values=metric).reset_index()
        pv.columns.name = None
        md_out.append(f"### Rollforward: {title}\n\n" + md(pv))
    for _, r in roll_df.iterrows():
        tests["tests"].append(dict(id=f"rollforward-{r['step']}-{r['contract'].replace(' ', '')}", kind="contract_position",
                                   steps_through=r["step"], contract=r["contract"],
                                   expected={c: round(float(r[c]), 4) for c in roll_df.columns if c not in ("step", "contract", "pobs")},
                                   source="golden/contract-rollforward.csv"))

    # ---------------- 4. final positions
    final = by_nn[max(by_nn)]
    fk = contract_rollup(final["latest"])
    md_out.append("### Final contract positions (after step 14)\n\n" + md(fk))
    lt = final["latest"].sort_values([K, POB])
    pob = pd.DataFrame({
        "Contract": lt[K], "POB": lt[POB], "SKU": lt[SKU], "Strat": lt[STRAT], "D/N": lt[DN],
        "Original allocation": lt[ORIG_ALLOC],
        "Final allocation (rev cum + remaining)": lt[RR_CUM].fillna(0) + lt[REM_ALLOC].fillna(0),
        "Qty delivered cum": lt[DLV_CUM], "Revenue cum": lt[RR_CUM], "Billing cum": lt[BILL_CUM],
        "Remaining qty": lt[REM_QTY], "Remaining allocation": lt[REM_ALLOC],
        "Position POB": lt[POS_POB], "Catch-up cum (disclosure)": lt[CATCH_CUM],
    })
    pob.to_csv(golden / "final-pob-positions.csv", index=False, lineterminator="\n")
    md_out.append("### Final POB positions (after step 14)\n\n" + md(pob, nds={"Qty delivered cum": 1, "Remaining qty": 1}))
    for _, r in pob.iterrows():
        tests["tests"].append(dict(id=f"final-pob-{r['Contract'].replace(' ', '')}-{r['POB'].replace(' ', '').replace('#', '')}",
                                   kind="pob_position", steps_through=final["nn"], contract=r["Contract"], pob=r["POB"], sku=r["SKU"],
                                   expected={c: (None if pd.isna(r[c]) else round(float(r[c]), 4)) for c in pob.columns[5:]},
                                   source="golden/final-pob-positions.csv"))

    # ---------------- monthly JE
    mrows = []
    for m in summary["monthly"]:
        g, d = m["je_gross_totals"], m["je_delta_totals"]
        mrows.append({"Period": m["month"], "Gross JE (Dr / Cr by account)": je_compact(g),
                      "Delta JE": "same as gross" if g == d else je_compact(d)})
        tests["tests"].append(dict(id=f"je-month-{m['month']}", kind="journal_entry_totals", steps_through="14",
                                   window=m["window"], gross=g, delta=d, source=f"golden/monthly/{m['month']}/"))
    md_out.append("### Month-end and full-year JE on the final database\n\n" + md(pd.DataFrame(mrows)))

    # ---------------- catch-ups and setup allocations
    crow = []
    for s in steps:
        n = s["new"]
        if n.empty:
            continue
        x = n[n[CATCH].abs() > 1e-9]
        for _, r in x.iterrows():
            crow.append({"Step": s["nn"], "Contract": r[K], "POB": r[POB], "SKU": r[SKU], "D/N": r[DN],
                         "Catch-up (Current Rev Rec)": r[CATCH], "Remaining allocation after": r[REM_ALLOC],
                         "Revenue cum after": r[RR_CUM]})
    cdf = pd.DataFrame(crow)
    md_out.append("### Cumulative catch-up adjustments recorded by mods\n\n" + md(cdf, nd=4))
    for _, r in cdf.iterrows():
        tests["tests"].append(dict(id=f"catchup-{r['Step']}-{r['Contract'].replace(' ', '')}-{r['POB'].replace(' ', '').replace('#', '')}",
                                   kind="cumulative_catchup", steps_through=r["Step"], contract=r["Contract"], pob=r["POB"],
                                   expected=dict(catchup=round(float(r["Catch-up (Current Rev Rec)"]), 4),
                                                 remaining_allocation=round(float(r["Remaining allocation after"]), 4),
                                                 revenue_cum=round(float(r["Revenue cum after"]), 4))))
    for nn in ("02", "03"):
        n = by_nn[nn]["new"].sort_values([K, POB])
        for _, r in n.iterrows():
            tests["tests"].append(dict(id=f"setup-alloc-{r[K].replace(' ', '')}-{r[POB].replace(' ', '').replace('#', '')}",
                                       kind="initial_allocation", steps_through=nn, contract=r[K], pob=r[POB], sku=r[SKU],
                                       inputs=dict(price=float(r["Original POB Total Selling Price"]), qty=float(r["Original POB Total Qty"]),
                                                   list_price=float(r["SKU Unit List Price"]), midpoint_discount=float(r["Midpoint Discount Percentage"]),
                                                   range=float(r["SSP Range Method (+-)"])),
                                       expected=dict(ssp_midpoint=round(float(r["Original SSP - Midpoint"]), 4),
                                                     extended_ssp=round(float(r[EXT_SSP]), 4),
                                                     allocation=round(float(r[ORIG_ALLOC]), 4),
                                                     contract_price=float(r["Original Total Contract Price"]),
                                                     contract_ssp=round(float(r["Original Total Contract SSP"]), 4))))
    setup = pd.concat([by_nn["02"]["new"], by_nn["03"]["new"]]).sort_values([K, POB])
    md_out.append("### Initial allocation (steps 02-03)\n\n" + md(pd.DataFrame({
        "Contract": setup[K], "POB": setup[POB], "SKU": setup[SKU], "Price": setup["Original POB Total Selling Price"],
        "Qty": setup["Original POB Total Qty"], "SSP low": setup["Original SSP - Lower"], "SSP mid": setup["Original SSP - Midpoint"],
        "SSP high": setup["Original SSP - Higher"], "Extended SSP": setup[EXT_SSP], "Allocation": setup[ORIG_ALLOC]}), nd=4))

    # ---------------- 6. anomaly scans
    an = []
    for s in steps:
        m = s["meta"]
        for label, t in (("gross", m["je_gross_totals"]), ("delta", m["je_delta_totals"])):
            if t and abs(t["total_debit"] - t["total_credit"]) >= TOL:
                an.append({"Check": "JE out of balance", "Where": f"step {m['nn']} {label} {m['report_window']}",
                           "Detail": f"Dr {t['total_debit']:,.2f} vs Cr {t['total_credit']:,.2f} ({t['total_debit'] - t['total_credit']:+.2f})"})
    for mth in summary["monthly"]:
        for label, t in (("gross", mth["je_gross_totals"]), ("delta", mth["je_delta_totals"])):
            if abs(t["total_debit"] - t["total_credit"]) >= TOL:
                an.append({"Check": "JE out of balance", "Where": f"month {mth['month']} {label}",
                           "Detail": f"Dr {t['total_debit']:,.2f} vs Cr {t['total_credit']:,.2f} ({t['total_debit'] - t['total_credit']:+.2f})"})
    all_new = pd.concat([s["new"].assign(step=s["nn"]) for s in steps if len(s["new"])], ignore_index=True)
    neg_qty = all_new[all_new[REM_QTY] < 0]
    an.append({"Check": "Negative remaining qty (any version)", "Where": "all steps", "Detail": f"{len(neg_qty)} rows"})
    neg_alloc = all_new[(all_new[REM_ALLOC] < -TOL)]
    an.append({"Check": "Negative remaining allocation", "Where": "all steps",
               "Detail": f"{len(neg_alloc)} rows" + ("" if neg_alloc.empty else ": " + "; ".join(
                   f"step {r.step} {r[K]} {r[POB]} {r[REM_ALLOC]:.4f}" for _, r in neg_alloc.iterrows()))})
    stranded = all_new[(all_new[REM_QTY].abs() < 1e-12) & (all_new[REM_ALLOC].abs() > TOL)]
    an.append({"Check": "Remaining qty 0 but allocation left (stranded)", "Where": "all steps",
               "Detail": f"{len(stranded)} rows" + ("" if stranded.empty else ": " + "; ".join(
                   f"step {r.step} {r[K]} {r[POB]} {r[REM_ALLOC]:.4f}" for _, r in stranded.iterrows()))})
    neg_bill = all_new[(all_new[REM_BILL] < 0)]
    an.append({"Check": "Negative remaining billing", "Where": "all steps",
               "Detail": f"{len(neg_bill)} rows, strata {sorted(set(neg_bill[STRAT]))}"})
    num_cols = [c for c in all_new.columns if pd.api.types.is_numeric_dtype(all_new[c]) and c != "step"]
    inf_count = int(np.isinf(all_new[num_cols].to_numpy(dtype=float)).sum())
    an.append({"Check": "Infinite values", "Where": "all steps", "Detail": f"{inf_count}"})
    resid = []
    fin_live = final["live"]
    for c in num_cols:
        v = pd.to_numeric(fin_live[c], errors="coerce")
        tiny = v[(v != 0) & (v.abs() < 1e-6)]
        if len(tiny):
            resid.append(f"{c}: {len(tiny)} (e.g. {tiny.iloc[0]:.3e})")
    an.append({"Check": "Floating-point residuals 0 < |x| < 1e-6 in Contract_Live", "Where": "final DB",
               "Detail": "; ".join(resid) if resid else "none"})
    nulls = []
    for s in steps:
        n = s["new"]
        if n.empty:
            continue
        for c in [c for c in n.columns if c not in ("Previous Period",)]:
            cnt = int(n[c].isna().sum())
            if cnt:
                who = ", ".join(sorted(set(n.loc[n[c].isna(), K] + " " + n.loc[n[c].isna(), POB])))
                nulls.append(f"step {s['nn']} `{c}` x{cnt} ({who})")
    an.append({"Check": "NULLs in new versions (excluding Previous Period)", "Where": "per step",
               "Detail": "; ".join(nulls) if nulls else "none"})
    tp_mis = roll_df[(roll_df["tp_allocation_basis"] - roll_df["tp_billing_basis"]).abs() > TOL]
    an.append({"Check": "TP allocation basis != TP billing basis", "Where": "contract rollforward",
               "Detail": f"{len(tp_mis)} contract-steps" + ("" if tp_mis.empty else ": " + "; ".join(
                   f"step {r.step} {r.contract} {r.tp_allocation_basis:.4f} vs {r.tp_billing_basis:.4f}" for _, r in tp_mis.iterrows()))})
    uar_mis = roll_df[(roll_df["contract_asset"] - roll_df["uar_reclass_field"]).abs() > TOL]
    an.append({"Check": "Contract asset (-position) != sum of Current Reclass to UAR", "Where": "contract rollforward",
               "Detail": f"{len(uar_mis)} contract-steps" + ("" if uar_mis.empty else ": " + "; ".join(
                   f"step {r.step} {r.contract} {r.contract_asset:.4f} vs {r.uar_reclass_field:.4f}" for _, r in uar_mis.iterrows()))})
    drift = all_new[(all_new[REM_QTY] > 0) & ((all_new[UNIT_SSP] - all_new[ORIG_UNIT_SSP]).abs() > 1e-6) & all_new[ORIG_UNIT_SSP].notna()]
    an.append({"Check": "Unit SSP changed by a modification (open POBs)", "Where": "all steps",
               "Detail": "; ".join(sorted({f"step {r.step} {r[K]} {r[POB]}: {r[ORIG_UNIT_SSP]:.4f} -> {r[UNIT_SSP]:.4f}"
                                           for _, r in drift.iterrows()})) or "none"})
    vc = all_new[(all_new[STRAT] == "VC") & (all_new[DLV] != 0)]
    an.append({"Check": "VC line with delivery qty but zero revenue", "Where": "all steps",
               "Detail": "; ".join(f"step {r.step} {r[K]} delivery {r[DLV]} billing {r[BILL]} RR {r[RR]}" for _, r in vc.iterrows()) or "none"})
    fails = [f"step {s['nn']}" for s in steps if not s["meta"]["handler_success"]]
    an.append({"Check": "Handler validation failures / error popups", "Where": "handlers", "Detail": ", ".join(fails) or "none"})
    errs = [f"step {s['nn']} {r['phase']}: {r['title']}" for s in steps if len(s["popups"])
            for _, r in s["popups"].iterrows() if r["kind"] == "QMessageBox.critical"]
    an.append({"Check": "Report error popups", "Where": "reports", "Detail": "; ".join(errs) or "none"})
    # full-year revenue JE vs final cumulative revenue per POB
    fy = read_csv(golden / "monthly" / "2023-full-year" / "je_gross.csv")
    rev_lines = fy[fy["Account"].astype(int) < 10000].set_index("Record Unique ID without time")["Amount"]
    lt2 = final["latest"].assign(key=final["latest"]["Record Unique ID without time"])
    tie = []
    for _, r in lt2.iterrows():
        je_amt = -float(rev_lines.get(r["key"], 0.0))
        if abs(je_amt - round(float(r[RR_CUM]), 2)) > TOL:
            tie.append(f"{r['key']}: JE {je_amt:.2f} vs revenue cum {r[RR_CUM]:.4f}")
    an.append({"Check": "Full-year revenue JE per POB vs final cumulative revenue", "Where": "monthly/2023-full-year",
               "Detail": "; ".join(tie) or "all POBs tie to 0.01"})
    md_out.append("### Automated anomaly scan\n\n" + md(pd.DataFrame(an)))

    # ---------------- compare with shipped
    ver = read_csv(golden / "compare-shipped" / "final_versions_vs_shipped.csv")
    md_out.append("### Versions in final replay vs shipped DB\n\n" + md(ver))
    cols = read_csv(golden / "compare-shipped" / "point_in_time_column_diffs.csv")
    md_out.append(f"Point-in-time match step(s): {compare['point_in_time_match_steps']}; columns compared: {len(cols)}; "
                  f"columns with mismatches: {compare['point_in_time_columns_with_mismatch']}; max numeric abs diff: "
                  f"{cols['max_abs_diff'].max()}; schema differences: {compare['schema_differences']}; SKU_SSP equal: {compare['sku_ssp_equal']}")
    tests["tests"].append(dict(id="shipped-db-equivalence", kind="point_in_time_equivalence", steps_through="04",
                               expected=dict(rows=compare["shipped_rows"], columns_with_mismatch=compare["point_in_time_columns_with_mismatch"]),
                               source="golden/compare-shipped/"))

    # ---------------- probes (legacy behaviours outside the UAT scenario)
    prow = []
    for pj in sorted((golden / "probes").glob("*/probe.json")):
        p = json.loads(pj.read_text())
        last = p["sequence"][-1]
        popups = "; ".join(f"{x['title']}: {x['text'][:90]}" for x in last["popups"])
        rep = "; ".join(f"{k} {je_compact(v['totals'])}" for k, v in p["reports"].items()) or "-"
        watched = "; ".join(
            f"{w['contract']} {w['pob']} dlv cum {fnum(w['Current Delivery - Cumulative'], 1)}, bill cum "
            f"{fnum(w['Current Billing - Cumulative'])}, rev cum {fnum(w['Current Rev Rec - Cumulative'], 4)}, "
            f"Pre-606 current {fnum(w['Current Pre-ASC606 Revenue (Net Design Only)'])}"
            for w in p["watched_latest"])
        prow.append({"Probe": p["id"], "Question": p["question"],
                     "Last action": f"{last['button_label']} `{last['file']}` {last['date_input'] or ''} rows {last['rows_before']}->{last['rows_after']}",
                     "Popups": popups, "Reports": rep, "Watched POBs (latest version)": watched,
                     "Baseline": p["baseline"], "Code": p["code_ref"]})
        tests["tests"].append(dict(id=f"probe-{p['id']}", kind="legacy_probe", question=p["question"],
                                   observed=dict(last_action=last, reports=p["reports"], watched_latest=p["watched_latest"]),
                                   baseline=p["baseline"], source=f"golden/probes/{p['id']}/"))
    if prow:
        md_out.append("### Probes of behaviour outside the UAT scenario\n\n" + md(pd.DataFrame(prow)))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n\n".join(md_out) + "\n")
    (golden / "golden-tests.json").write_text(json.dumps(tests, indent=2, default=str) + "\n")
    print(f"analysis -> {args.out}\ntests    -> {golden / 'golden-tests.json'} ({len(tests['tests'])} cases)")


if __name__ == "__main__":
    main()
