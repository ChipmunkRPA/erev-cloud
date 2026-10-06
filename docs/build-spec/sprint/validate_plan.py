#!/usr/bin/env python3
"""Independent validator of the eRev Cloud 1.0-rc sprint plan (slug ``sprint-validator``).

This script neither imports nor reuses ``plan_tools.py``. It re-derives, from ``docs/BUILD_SPEC.md``, the working
tree and ``git log``:

* item blocks (id, title, phase, document order, prerequisites, Scope lines, files named in Acceptance);
* its own technical dependency edges (``derive_edges``);
* migration items (Paths naming ``db/migrations/versions/``, plus reviewed Schema-only items);
* answer-key support per family (``key_support``);

and checks ``docs/build-spec/sprint/plan.json``:

(a) every in-scope item's hard prerequisites are done, at an earlier level, or earlier in the same lane; a same-level
    edge to another lane passes only when it is a documented contract (engine state type of ENGINE_SPEC Table 0.2-A
    or 04 API schema) flagged integration-after-merge; loop-order edges (the declared predecessor or phase gate)
    that the item text corroborates must be satisfied or carry a review entry;
(b) no in-scope item has a hard edge, or a corroborated loop-order edge, to a deferred item;
(c) every MVP capability of the brief is covered (optional ids need a recorded exclusion);
(d) per level: at most one lane adds migrations and the plan flags agree; no two lanes touch a non-mergeable shared
    file (lock files, package manifests, Alembic versions); an overlap on a mergeable shared file of the brief needs a
    SPRINT-1.0rc.md section 4.3 rule; any other file overlap fails;
(e) batches hold 1 to 4 items, at most 5 lanes per level, and merge orders list every lane once;
(f) every in-scope item is scheduled exactly once; in_scope, deferred and done partition the 427 items.

Usage::

    python3 docs/build-spec/sprint/validate_plan.py check [-v]      # exit 1 when a check fails
    python3 docs/build-spec/sprint/validate_plan.py edges ID [ID…]   # derived edges of items
    python3 docs/build-spec/sprint/validate_plan.py serial           # loop-order edges not satisfied by position
    python3 docs/build-spec/sprint/validate_plan.py keys             # answer-key support by family
    python3 docs/build-spec/sprint/validate_plan.py critical         # critical path over hard edges
    python3 docs/build-spec/sprint/validate_plan.py apply            # write the validator layout fixes to plan.json
                                                                     # and the Levels tables of SPRINT-1.0rc.md
    python3 docs/build-spec/sprint/validate_plan.py json             # machine-readable result

Read-only except ``apply``; it never runs make, pytest, servers or write-git.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPEC = REPO / "docs" / "BUILD_SPEC.md"
PLAN = REPO / "docs" / "build-spec" / "sprint" / "plan.json"
SPRINT = REPO / "docs" / "build-spec" / "sprint" / "SPRINT-1.0rc.md"
KEYS_DIR = REPO / "docs" / "accounting" / "answer-keys"

ID = r"(?:GATE-[A-Z]{3}|[A-Z]{3}-\d+[a-z]?)"
ITEM_RE = re.compile(r"^- \[[ x]\] \*\*(" + ID + r") (.*?)\.?\*\*(.*)$")
ID_RE = re.compile(r"\b(" + ID + r")\b")
ROOT_DIRS = {"backend", "frontend", "docs", "scripts", "deploy", "research-harness", "legacy-harness", ".github",
             ".ralph"}
ROOT_FILES = {"Makefile", "LICENSE", "NOTICE", "README.md", "PROGRESS.md", "PROMPT.md", ".env.example",
              ".gitignore", ".dockerignore"}
EXTS = {"py", "ts", "tsx", "js", "mjs", "cjs", "json", "md", "yaml", "yml", "toml", "sql", "csv", "txt", "ini",
        "mako", "html", "css", "svg", "woff2", "db", "xlsx", "sh", "cfg", "lock", "example", "tf", "tfvars",
        "Dockerfile", "dockerignore", "conf", "jsonl", "xml", "pdf", "png", "gz", "zip", "hcl", "tmpl", "j2"}
PATH_TOKEN = re.compile(r"^[\w.\-/<>{}*\[\]@+]+$")
TEST_DIR_PREFIXES = ("backend/tests/", "frontend/e2e/")

# --------------------------------------------------------------------------------------------------
# Brief rules
# --------------------------------------------------------------------------------------------------
MAX_LANES = 5
BATCH_MIN, BATCH_MAX = 1, 4
MIGRATION_DIR = "backend/erev_api/db/migrations/versions/"
SHARED_NON_MERGEABLE = {"backend/pyproject.toml", "backend/uv.lock", "frontend/package.json",
                        "frontend/package-lock.json"}
SHARED_MERGEABLE = {
    "backend/erev_api/db/tables/__init__.py", "backend/erev_api/api/router.py",
    "backend/erev_api/approvals/subjects.py", "backend/erev_api/auth/permissions.py",
    "backend/erev_api/jobs/registry.py", "backend/erev_engine/stages/__init__.py",
    "backend/tests/architecture/test_registries_complete.py", "backend/tests/engine/kernel/test_stage_registry.py",
    "frontend/src/app/router.tsx", "docs/api/openapi.json", "frontend/src/lib/api/schema.d.ts", "Makefile",
}
CONTRACT_OK_KINDS = {"state", "api-bind"}   # interfaces documented in ENGINE_SPEC Table 0.2-A and 04 API schemas

CAPABILITIES = {
    "C1 frontend shell, seed scaffold, e2e harness, sign-in, MFA, approvals":
        {"required": ["WEB-8", "WEB-10", "WEB-11", "WEB-12", "WEB-15"]},
    "C2 engine stages 01-05, 06 paths, 09-10, 13-14 and compute, 15":
        {"required": [f"ENA-{n}" for n in range(1, 14)]
         + ["ENB-1", "ENB-2", "ENB-3", "ENB-6", "ENB-7", "ENB-8", "ENB-11", "ENB-13"]
         + ["ENC-1", "ENC-2", "ENC-3", "ENC-4", "ENC-7", "ENC-10", "ENC-11", "ENC-12", "ENC-13", "ENC-14"]
         + [f"END-{n}" for n in range(4, 11)] + ["EDS-1", "EDS-2", "EDS-3"]},
    "C3 golden parity and answer-key sweeps":
        {"required": [f"GPA-{n}" for n in range(1, 7)] + ["GPB-1", "GPB-2"],
         "optional": ["GPB-4"] + [f"AKS-{n}" for n in range(1, 9)], "min_optional_in_scope": 1},
    "C4 reference data backend":
        {"required": ["RFD-1", "RFD-2", "RFD-3", "RFD-6", "RFD-7", "RFD-8", "RFD-9", "RFD-10", "RFD-11", "RFD-12",
                      "RFD-13", "RFD-14", "RFD-16"]},
    "C5 contracts backend": {"required": ["CTR-1", "CTR-2", "CTR-3", "CTR-4", "CTR-5", "CTR-15", "CTR-19", "CTR-20"]},
    "C6 data in": {"required": [f"DIN-{n}" for n in range(1, 7)] + ["DIN-11"]},
    "C7 close and journals": {"required": ["CLO-1", "CLO-2", "CLO-3", "CLO-8", "CLO-9", "CLO-11", "CLO-13"]},
    "C8 reports": {"required": [f"RPS-{n}" for n in range(1, 6)]},
    "C9 MVP screens":
        {"required": ["CTR-21", "CTR-22", "CTR-23", "CTR-26", "DIN-15", "DIN-16", "DIN-17", "RPS-6", "RPS-7",
                      "CLO-23", "CLO-26", "RPS-22", "RFD-24"]},
    "C10 flagship journey J-01 (or a smoke subset)":
        {"optional": ["RPS-23", "RPS-24"], "min_optional_in_scope": 0, "fallback": "SUP-RC-SMOKE"},
    "C11 deploy images and compose": {"required": ["DEP-1", "DEP-2"]},
}

# Stage state chain (ENGINE_SPEC Table 0.2-A; ENGINE_SPEC_B §0.2): consumer package, producer package. The consumer is
# the first item listing the consumer package __init__.py; the producer the first item listing the producer's.
STAGE_CHAIN = [("s03_pob_builder", "s02_contract_identification"), ("s04_transaction_price", "s03_pob_builder"),
               ("s05_allocation", "s04_transaction_price"), ("s10_billing_balances", "s09_recognition"),
               ("s11_costs_loss", "s10_billing_balances"), ("s12_fx_entities", "s11_costs_loss"),
               ("s14_posting", "s12_fx_entities"), ("s15_disclosures", "s14_posting")]

# Edges confirmed by the validator in the item text (item, dependency, evidence).
VERIFIED_EDGES: list[tuple[str, str, str]] = [
    ("DIN-7", "DIN-4", "test_defects.py TC-setup-13 to TC-setup-20 run the SKU SSP and contract setup templates of "
                       "DIN-4 (legacy_v1/sku_ssp.py, contract_setup.py)"),
    ("DIN-8", "DIN-5", "TC-delivery-12, 14 and 17 upload progress files through the DIN-5 template; TC-delivery-13, 15 "
                       "and 16 are proved by DIN-5 tests"),
    ("DIN-8", "DIN-6", "TC-RM-09, 10, 16 and TC-pob-vc-10, 15 upload modification files through the DIN-6 modes"),
    ("DIN-11", "DIN-5", "test_dismiss_uncommitted_input dismisses the PROGRESS_OVER_DELIVERY items of an INVALID "
                        "progress import (DIN-5 TC-delivery-10)"),
    ("CTR-23", "CTR-22", "SF-03:schedules, :billing and :journals (RT-14 to RT-16) are tabs of the SF-03 frame "
                         "(workbench.tsx) built by CTR-22"),
    ("CTR-23", "CTR-20", "captures on seeded K-02 SF-ORD-10002 (FY2026-P09 9,863.01; INV-US-1002) need the CTR-20 "
                         "key-contracts seed"),
    ("ENB-3", "ENB-2", "formulas mod.pool.by_line.v1, mod.pool.total_tp.v1 and mod.weights.inception_all.v1 extend "
                       "pool.py and weights.py of ENB-2"),
    ("ENB-4", "ENB-2", "S06-R-21: classes and pools follow §6.3 (pool.py, segments.py of ENB-2)"),
    ("ENB-4", "ENB-3", "CHK-115 measures a cumulative catch-up (CU −15,555.56); S06-R-21 sends a remaining pool to "
                       "satisfied performance S06-R-09 (satisfied.py of ENB-3)"),
    ("ENB-13", "ENB-2", "BOUNDARY_HANDLERS maps CONTRACT_AMENDED to s06_modifications.apply (ENB-2)"),
    ("ENB-13", "ENB-4", "CONTRACT_TERMINATED maps to s06_modifications.apply over terminations.py (ENB-4)"),
    ("ENB-13", "ENB-5", "REGROUPED, LINE_ATTRIBUTES_CHANGED, MATERIAL_RIGHT_EXERCISED map to s06 apply (ENB-5)"),
    ("ENB-13", "ENB-7", "test_fold_golden_contract2_through_step_09 folds golden step 09, the POB-specific VC "
                        "template of ENB-7"),
    ("ENB-13", "ENB-9", "OPENING_BALANCE_ESTABLISHED maps to s07_onboarding.apply (ENB-9)"),
    ("ENB-13", "ENB-10", "ESTIMATE_CHANGED maps to s08_estimates_late_events.apply (ENB-10)"),
    ("ENB-13", "ENB-11", "stage 08 enters STAGES with its export assign_posting_period (ENB-11)"),
    ("ENB-13", "ENB-12", "stage 08 enters STAGES with its export decompose_prior_period (ENB-12)"),
    ("END-5", "ENB-11", "s14_posting/assign.py calls s08_estimates_late_events.assign_posting_period (ENB-11)"),
    ("ENC-7", "ENC-4", "S09-R-23 to S09-R-26 adjust the units-measure target of S09-R-10; test_chk_061_golden_return "
                       "replays delivered units through progress_events.py (ENC-4)"),
    ("CTR-2", "END-9", "computed versions persist(uow, bundle, output) the result of erev_engine.compute (END-9)"),
    ("CTR-5", "END-9", "the CONTRACT_COMPUTE job runs compute (END-9)"),
    ("END-10", "END-9", "test_chk_delta and test_tc_je sum the OutputBundle posting intents returned by compute"),
    ("RPS-3", "EDS-2", "revenue waterfall reads the s15_disclosures projection of ENGINE_SPEC_B §15.2.1 (EDS-2)"),
    ("RPS-3", "EDS-3", "contract balance rollforward reads the §15.2.2 projection (EDS-3)"),
    ("RPS-3", "EDS-4", "revenue from prior-period obligations reads the §15.2.4 projection (EDS-4)"),
]

# Loop-order edges the text corroborates (a created file stem or symbol appears) that were reviewed and found not
# technical. (item, predecessor) -> reason.
SERIAL_REVIEW: dict[tuple[str, str], str] = {
    ("CTR-10", "CTR-9"): "`field-locked-after-activation` is a problem slug; the tests need an ACTIVE contract and "
                         "CTR-7 judgements, not the CTR-9 checklist or routing",
    ("CLO-11", "CLO-10"): "`validation-failed` is a problem slug; submit, cancel and the E-34 table do not call "
                          "validate_lines or assert_completeness",
    ("RFD-19", "RFD-18"): "SF-15:setup creates its entity and period through the RFD-1 and RFD-2 API; the RFD-18 "
                          "settings screens are not visited",
    ("RFD-24", "RFD-23"): "the /policies routes of SF-13 bind API-R-26 and API-R-27; the template editor is not visited",
}

# Schema-only items reviewed for a migration revision without a versions/ path (item -> adds a revision).
MIGRATION_REVIEW: dict[str, bool] = {
    "RFD-13": True,  # Schema: "triggers added to the RFD-12 tables in this revision"
}

# Answer-key blockers: recognition method or event type -> deferred engine item; each is verified against the item
# title and Engine line by key_support().
KEY_BLOCKERS = {"COST_TO_COST": "ENC-5", "LABOUR_HOURS": "ENC-5", "COST_RECOVERY": "ENC-5",
                "RIGHT_TO_INVOICE": "ENC-6", "USAGE": "ENC-6", "USAGE_REPORTED": "ENC-6",
                "REDEMPTION_PATTERN": "ENC-8", "ROYALTY": "ENC-8", "MATERIAL_RIGHT_EXPIRED": "ENC-8"}
KEY_BLOCKER_EVIDENCE = {"ENC-5": ("cost to cost", "labour hours", "cost recovery"), "ENC-6": ("right to invoice", "usage"),
                        "ENC-8": ("material-right", "royalt")}

# Validator layout fixes (explicit lane batches for the levels that change). Lane names and families are taken from
# the lane of the previous plan holding the first item unless given.
LAYOUT: dict[str, list[dict]] = {
    "L1": [
        {"batches": [["RFD-1"], ["RFD-6"], ["RFD-2"], ["RFD-3"], ["RFD-8"]]},
        {"name": "Engine: stages 01 to 05", "family": "eng-alloc",
         "batches": [["ENA-1", "ENA-2"], ["ENA-3", "ENA-5"], ["ENB-1", "ENA-6"], ["ENA-10", "ENA-11"]]},
        {"name": "Engine: stages 07 to 09", "family": "eng-rec",
         "batches": [["ENC-1", "ENC-2"], ["ENC-3", "ENC-4"], ["ENC-7", "ENC-9"], ["ENB-9", "ENB-10"]]},
        {"batches": [["RFD-4", "RFD-5"], ["WEB-8"], ["WEB-9", "DEP-1"], ["DEP-2"]]},
        {"batches": [["WEB-10"]]},
    ],
    "L2": [
        {"batches": [["RFD-7"], ["RFD-9"], ["RFD-12"], ["RFD-13"], ["RFD-10"], ["RFD-15"]]},
        {"name": "Engine: stages 03 to 05 and the inception fold", "family": "eng-alloc",
         "batches": [["ENA-4", "ENA-7"], ["ENA-8", "ENA-9"], ["ENA-12", "ENA-13"]]},
        {"name": "Engine: stage 06 modifications", "family": "eng-mod",
         "batches": [["ENB-2", "ENB-3"], ["ENB-4", "ENB-5"], ["ENB-6", "ENB-7"], ["ENB-8"]]},
        {"name": "Engine: stages 09 to 11", "family": "eng-rec",
         "batches": [["ENC-10", "ENC-11"], ["ENC-12", "ENC-13"], ["ENC-14", "ENC-15"], ["ENC-16"]]},
        {"name": "Engine: stage 08 late events and stages 12 to 14", "family": "eng-post",
         "batches": [["ENB-11", "ENB-12"], ["END-1", "END-2"], ["END-3", "END-4"], ["END-5", "END-6"]]},
    ],
    "L3": [
        {"batches": [["CTR-1"]]},
        {"name": "Engine: boundary fold, books and compute, stage 15", "family": "eng-mod",
         "batches": [["ENB-13", "END-7"], ["END-8", "END-9"], ["END-10", "EDS-1"], ["EDS-2"]]},
        {"batches": [["RFD-11", "RFD-14"], ["RFD-16"]]},
        {"batches": [["WEB-11"], ["WEB-12"], ["WEB-15"], ["WEB-17"]]},
    ],
    "L5": [
        {"batches": [["CLO-1"], ["DIN-2"], ["CLO-2"], ["CTR-7"], ["CTR-15", "DIN-3"]]},
        {"batches": [["AKS-3"], ["AKS-4"], ["AKS-5"], ["AKS-6"]]},
        {"batches": [["CTR-8"]]},
    ],
    "L6": [
        {"batches": [["CTR-10"], ["CTR-12"], ["CTR-14"], ["DIN-12"], ["RPS-1"], ["DIN-10"]]},
        {"batches": [["AKS-7"]]},
        {"batches": [["CLO-3"]]},
    ],
    "L7": [
        {"batches": [["CLO-4", "CLO-5"], ["CLO-6", "CLO-16"], ["CLO-18"], ["CLO-19"]]},
        {"batches": [["CTR-9", "DIN-4"], ["CTR-17"], ["GPA-1"], ["DIN-5"]]},
        {"batches": [["CTR-19"]]},
        {"batches": [["DIN-14"]]},
    ],
    "L8": [
        {"batches": [["GPA-2"]]},
        {"batches": [["CLO-7", "CLO-8"], ["CLO-11", "CLO-13"], ["CLO-14", "CLO-15"]]},
        {"batches": [["CTR-20"], ["CTR-21"], ["CTR-11"], ["CTR-22"]]},
        {"name": "Platform: DIN legacy v1 modes, template defects and exception queue", "family": "api-din",
         "batches": [["DIN-6", "DIN-7"], ["DIN-8", "DIN-11"]]},
    ],
    "L9": [
        {"batches": [["GPA-3"], ["GPA-4"], ["GPA-5"], ["CLO-9"], ["GPA-6"]]},
        {"batches": [["CLO-17"], ["CLO-20"], ["CLO-22"], ["CLO-26"]]},
        {"batches": [["RPS-2"]]},
        {"batches": [["DIN-15"], ["CTR-26"], ["DIN-16"], ["DIN-17"]]},
        {"name": "Frontend: CTR workbench tabs", "family": "web", "batches": [["CTR-23"]]},
    ],
}
IAM_REMOVE = {("END-5", "ENB-11"), ("CTR-23", "CTR-14")}
IAM_ADD = [{"item": "RPS-6", "consumes": "RPS-3", "level": "L10",
            "reason": "a report cell opens the Explain panel through GET /explain/report-runs/{id}/cell (API-R-49)"}]

FIXES = [
    {"id": "V-01", "check": "(a)", "finding": "DIN-7 (L5-4) runs the SKU SSP and contract setup templates of DIN-4 "
     "(L7-2)", "change": "DIN-7 moves to L8-4 after DIN-6"},
    {"id": "V-02", "check": "(a)", "finding": "DIN-8 (L5-4) uploads progress and modification files through DIN-5 "
     "(L7-2) and DIN-6 (L8-4)", "change": "DIN-8 moves to L8-4 after DIN-6 and DIN-7; GPB-1 (L10) still follows"},
    {"id": "V-03", "check": "(a)", "finding": "DIN-11 (L5-4) dismisses PROGRESS_OVER_DELIVERY items of a DIN-5 "
     "progress import (L7-2)", "change": "DIN-11 moves to L8-4; DIN-17 (L9) and RPS-22 (L10) still follow; lane L5-4 "
     "is removed"},
    {"id": "V-04", "check": "(a)", "finding": "CTR-23 (L6-4) renders tabs of the CTR-22 frame and captures seeded "
     "K-02 from CTR-20 (both L8-3)", "change": "CTR-23 moves to new lane L9-5; lane L6-4, the L6 e2e gate and the "
     "CTR-23 integration note are removed"},
    {"id": "V-05", "check": "(a)", "finding": "ENA-3 (L1-2) consumes IdentifiedState returned by ENA-2 (L1-3, last "
     "batch), a same-level type edge with no integration note", "change": "ENA-1 and ENA-2 open L1-2; ENB-10 moves to "
     "L1-3; ENA-9 moves to L2-2 after ENA-8"},
    {"id": "V-06", "check": "(a)", "finding": "ENB-4 (L2-3) needs the catch-up of ENB-3 (L3-3) and the pools of ENB-2 "
     "(after ENB-4 in L2-3)", "change": "L2-3 holds ENB-2 to ENB-8 in document order; ENB-11 and ENB-12 open L2-5, "
     "which also removes the END-5 integration note; lane L3-3 is removed and L3-4, L3-5 become L3-3, L3-4"},
    {"id": "V-07", "check": "(a)", "finding": "ENC-7 (L1-3) adjusts the units measure of ENC-4 (L2-4)",
     "change": "ENC-4 moves to L1-3 before ENC-7; L2-4 holds ENC-10 to ENC-16 in document order"},
    {"id": "V-08", "check": "(a)", "finding": "RPS-6 (L10-2) binds the report-cell explain route of RPS-3 (L10-1) "
     "without an integration note", "change": "integration_after_merge gains RPS-6 on RPS-3"},
    {"id": "V-09", "check": "(a)", "finding": "declared predecessors later in the same lane: ENA-10/ENA-9, ENB-6/ENB-5,"
     " ENB-8/ENB-7, ENC-3/ENC-2, ENC-15/ENC-14, END-4/END-3, CLO-15/CLO-14, CLO-19/CLO-18",
     "change": "batches reordered in document order inside their lanes (no cost change)"},
    {"id": "V-10", "check": "(d)", "finding": "RFD-13 adds DB-04 and DB-05 triggers without naming a revision file",
     "change": "none: RFD-13 already sits in the L2-1 migration lane; recorded as a reviewed migration item"},
]


# --------------------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    title: str
    phase: str
    order: int
    prereq_text: str = ""
    paths: list[str] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)
    accept_files: list[str] = field(default_factory=list)
    paths_line: str = ""
    schema: str = ""
    api: str = ""
    engine: str = ""
    screens: str = ""
    accept: str = ""
    body: str = ""

    @property
    def is_gate(self) -> bool:
        return self.id.startswith("GATE-")


def code_spans(line: str) -> list[tuple[str, int]]:
    """Backticked spans with the parenthesis depth (outside code) at which each starts."""
    out, depth, i, n = [], 0, 0, len(line)
    while i < n:
        c = line[i]
        if c == "`":
            j = line.find("`", i + 1)
            if j < 0:
                break
            out.append((line[i + 1:j], depth))
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        i += 1
    return out


def is_path_token(tok: str) -> bool:
    tok = tok.split("::")[0]
    if not tok or tok.startswith("/") or tok.startswith("…") or not PATH_TOKEN.match(tok):
        return False
    if tok in ROOT_FILES:
        return True
    if tok.endswith("/"):
        return "/" in tok[:-1] or tok[:-1] in ROOT_DIRS or bool(re.match(r"^[a-z0-9_\-<>]+$", tok[:-1]))
    last = tok.rsplit("/", 1)[-1]
    m = re.search(r"\.([A-Za-z0-9]+)$", last)
    return bool(m and m.group(1) in EXTS)


def normalise_paths(line: str) -> tuple[list[str], list[str]]:
    """Paths at parenthesis depth 0; a bare or relative name inherits the directory of the previous path."""
    files, dirs, cur = [], [], ""
    for tok, depth in code_spans(line):
        if depth > 0:
            continue
        tok = tok.split("::")[0].strip()
        if not is_path_token(tok):
            continue
        first = tok.split("/", 1)[0]
        if tok in ROOT_FILES or first in ROOT_DIRS:
            full = tok
        else:
            full = (cur + tok) if cur else tok
        if full.endswith("/"):
            dirs.append(full)
            cur = full
        else:
            files.append(full)
            cur = full.rsplit("/", 1)[0] + "/" if "/" in full else ""
    return files, dirs


def parse_spec() -> dict[str, Item]:
    items: dict[str, Item] = {}
    cur: Item | None = None
    section = None
    order = 0
    for raw in SPEC.read_text(encoding="utf-8").split("\n"):
        m = ITEM_RE.match(raw)
        if m:
            iid = m.group(1)
            phase = iid.split("-")[1] if iid.startswith("GATE-") else iid.split("-")[0]
            cur = Item(id=iid, title=m.group(2).rstrip("."), phase=phase, order=order)
            order += 1
            items[iid] = cur
            section = None
            continue
        if cur is None:
            continue
        if raw.startswith("#") or raw.startswith("<!--"):
            cur = None
            continue
        cur.body += raw + "\n"
        s = raw.strip()
        if s.startswith("- **Prerequisites:**"):
            cur.prereq_text = s[len("- **Prerequisites:**"):].strip()
            section = "pre"
        elif s.startswith("- **Scope:**"):
            section = "scope"
        elif s.startswith("- **Acceptance:**"):
            section = "accept"
        elif s.startswith("- **Read:**") or s.startswith("- **Gates:**"):
            section = "other"
        elif section == "scope" and s.startswith("- Paths:"):
            cur.paths_line = s
            f, d = normalise_paths(s[len("- Paths:"):])
            cur.paths += f
            cur.dirs += d
        elif section == "scope" and s.startswith("- Schema:"):
            cur.schema = s[len("- Schema:"):].strip()
        elif section == "scope" and s.startswith("- API:"):
            cur.api = s[len("- API:"):].strip()
        elif section == "scope" and s.startswith("- Engine:"):
            cur.engine = s[len("- Engine:"):].strip()
        elif section == "scope" and s.startswith("- Screens:"):
            cur.screens = s[len("- Screens:"):].strip()
        elif section == "accept":
            cur.accept += raw + "\n"
            for tok, _ in code_spans(raw):
                t = tok.split("::")[0].strip()
                if is_path_token(t) and t.split("/", 1)[0] in ROOT_DIRS and not t.endswith("/"):
                    cur.accept_files.append(t)
    return items


def done_ids(items: dict[str, Item]) -> set[str]:
    out = subprocess.run(["git", "-C", str(REPO), "log", "--format=%s"], capture_output=True, text=True,
                         check=True).stdout
    ids = {m.group(1) for line in out.splitlines()
           if (m := re.match(r"^(GATE-[A-Z]{3}|[A-Z]{3}-[0-9]+[a-z]?)\b", line)) and m.group(1) in items}
    ids.add("WEB-7")  # in flight; the brief treats it as done
    return ids


def merge_rule_files() -> dict[str, str]:
    """Files with a merge rule in SPRINT-1.0rc.md section 4.3."""
    text = SPRINT.read_text(encoding="utf-8")
    m = re.search(r"### 4\.3 Shared files and merge rules\n(.*?)\n## ", text, re.S)
    rules: dict[str, str] = {}
    if not m:
        return rules
    for row in m.group(1).splitlines():
        if not row.startswith("| "):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("File", "---"):
            continue
        prev_dir = ""
        for t, _ in code_spans(cells[0]):
            if "/" in t or t in ROOT_FILES:
                full, prev_dir = t, (t.rsplit("/", 1)[0] + "/" if "/" in t else "")
            else:
                full = prev_dir + t
            rules[full] = cells[1]
    return rules


# --------------------------------------------------------------------------------------------------
# Edges
# --------------------------------------------------------------------------------------------------
@dataclass
class Edge:
    item: str
    dep: str
    kind: str      # serial | explicit | provenance | file | dir | table | api-bind | state | verified
    reason: str

    @property
    def hard(self) -> bool:
        return self.kind != "serial"


def split_prereq(text: str) -> tuple[list[str], list[str]]:
    depth, buf_o, buf_i = 0, [], []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        (buf_i if depth > 0 or ch == ")" else buf_o).append(ch)
    return ID_RE.findall("".join(buf_o)), ID_RE.findall("".join(buf_i))


def table_ids(schema: str) -> list[str]:
    return re.findall(r"\bT-[A-Z]{2,4}-\d+[a-z]?\b", schema)


def api_rows(api: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """(produced rows -> route text, bound (row, qualifier) pairs)."""
    produced: dict[str, str] = {}
    bound: list[tuple[str, str]] = []
    if api.lower().startswith("none"):
        m = re.search(r"binds\s+(.*?)\)?$", api)
        if m:
            parts = re.split(r"(API-R-\d+)", m.group(1))
            for k in range(1, len(parts), 2):
                bound.append((parts[k], parts[k + 1] if k + 1 < len(parts) else ""))
        return produced, bound
    parts = re.split(r"(API-R-\d+)", api)
    for k in range(1, len(parts), 2):
        produced[parts[k]] = produced.get(parts[k], "") + (parts[k + 1] if k + 1 < len(parts) else "")
    return produced, bound


def qualifier_words(q: str) -> set[str]:
    stop = {"and", "with", "list", "lists", "routes", "purpose", "counts", "anomaly", "the", "for", "get", "post",
            "patch", "put", "delete"}
    words = {w.lower().replace("_", "-") for w in re.findall(r"[A-Za-z_\-]{4,}", q)}
    return {w for w in words if w not in stop}


def created_by(items: dict[str, Item]) -> dict[str, str]:
    first: dict[str, str] = {}
    for it in sorted(items.values(), key=lambda x: x.order):
        if it.is_gate:
            continue
        for p in it.paths + it.accept_files:
            first.setdefault(p, it.id)
    return first


def derive_edges(items: dict[str, Item], done: set[str]) -> list[Edge]:
    order = sorted(items.values(), key=lambda x: x.order)
    by_phase: dict[str, list[Item]] = defaultdict(list)
    phase_seq: list[str] = []
    for it in order:
        if it.phase not in phase_seq:
            phase_seq.append(it.phase)
        if not it.is_gate:
            by_phase[it.phase].append(it)
    predecessor: dict[str, str] = {}
    for ph, its in by_phase.items():
        for i, it in enumerate(its):
            if i > 0:
                predecessor[it.id] = its[i - 1].id
            elif phase_seq.index(ph) > 0:
                predecessor[it.id] = f"GATE-{phase_seq[phase_seq.index(ph) - 1]}"

    shared = SHARED_MERGEABLE | SHARED_NON_MERGEABLE | set(merge_rule_files())
    edges: list[Edge] = []

    def add(item: str, dep: str, kind: str, reason: str) -> None:
        if dep != item and dep in items:
            edges.append(Edge(item, dep, kind, reason))

    for it in order:
        outside, inside = split_prereq(it.prereq_text)
        for d in outside:
            if d == predecessor.get(it.id) or d.startswith("GATE-"):
                add(it.id, d, "serial", "declared predecessor or phase gate (loop order)")
            else:
                add(it.id, d, "explicit", "declared prerequisite other than the loop predecessor")
        for d in inside:
            if not d.startswith("GATE-"):
                add(it.id, d, "provenance", "named in the prerequisite provenance note")

    first_lister = created_by(items)
    dir_first: dict[str, str] = {}
    for it in order:
        if it.is_gate:
            continue
        for p in it.paths + it.dirs:
            d = p if p.endswith("/") else p.rsplit("/", 1)[0] + "/"
            parts = d.rstrip("/").split("/")
            for k in range(2, len(parts) + 1):
                dir_first.setdefault("/".join(parts[:k]) + "/", it.id)
    for it in order:
        if it.is_gate:
            continue
        for p in dict.fromkeys(it.paths + it.accept_files):
            if p in shared or "<" in p or "*" in p:
                continue
            prod = first_lister.get(p)
            if prod and prod != it.id and not (REPO / p).exists():
                add(it.id, prod, "file", f"file {p} first listed by {prod}")
        for p in dict.fromkeys(it.paths + it.dirs):
            d = p if p.endswith("/") else p.rsplit("/", 1)[0] + "/"
            if "<" in d or d.startswith(TEST_DIR_PREFIXES) or "__tests__" in d or (REPO / d).exists():
                continue   # test directories carry no __init__.py in this repo, so they create no dependency
            prod = dir_first.get(d)
            if prod and prod != it.id and items[prod].order < it.order:
                add(it.id, prod, "dir", f"package directory {d} first used by {prod}")

    t_creator: dict[str, str] = {}
    for it in order:
        if not it.is_gate:
            for t in table_ids(it.schema):
                t_creator.setdefault(t, it.id)
    for it in order:
        for t in table_ids(it.schema):
            c = t_creator.get(t)
            if c and c != it.id:
                add(it.id, c, "table", f"table {t} created by {c}")
        for note in re.findall(r"\((.*)\)", it.prereq_text):
            for t in re.findall(r"\bT-[A-Z]{2,4}-\d+\b", note):
                c = t_creator.get(t)
                if c and c != it.id:
                    add(it.id, c, "provenance", f"table {t} named in the prerequisite note, created by {c}")
            for pre, a, b in re.findall(r"\b(T-[A-Z]{2,4})-(\d+) to T-[A-Z]{2,4}-(\d+)\b", note):
                for n in range(int(a), int(b) + 1):
                    c = t_creator.get(f"{pre}-{n:02d}")
                    if c and c != it.id:
                        add(it.id, c, "provenance", f"table {pre}-{n:02d} named in the prerequisite note")

    producers: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for it in order:
        prod, _ = api_rows(it.api)
        for r, text in prod.items():
            producers[r].append((it.id, text))
    for it in order:
        _, bound = api_rows(it.api)
        for r, q in bound:
            earlier = [(p, t) for p, t in producers.get(r, []) if items[p].order < it.order]
            if not earlier:
                continue
            words = qualifier_words(q)
            if words:
                chosen = [p for p, t in earlier if any(w in t.lower().replace("_", "-") for w in words)]
            elif q.strip(" ,;"):
                chosen = []        # qualifier of stopwords only ("list"): the row's first producer
            else:
                chosen = [p for p, _ in earlier]
            if not chosen:
                chosen = [earlier[0][0]]
            for p in chosen:
                add(it.id, p, "api-bind", f"binds {r}{(' ' + q.strip(' ,;')) if q.strip(' ,;') else ''} "
                                          f"produced by {p}")

    for consumer, producer in STAGE_CHAIN:
        c = first_lister.get(f"backend/erev_engine/stages/{consumer}/__init__.py")
        p = first_lister.get(f"backend/erev_engine/stages/{producer}/__init__.py")
        if c and p and not (REPO / f"backend/erev_engine/stages/{producer}/__init__.py").exists():
            add(c, p, "state", f"stage {consumer} consumes the state returned by {producer} (ENGINE_SPEC Table 0.2-A)")

    for a, b, why in VERIFIED_EDGES:
        add(a, b, "verified", why)
    rank = {"verified": 0, "explicit": 1, "provenance": 2, "table": 3, "state": 4, "file": 5, "dir": 6,
            "api-bind": 7, "serial": 9}
    best: dict[tuple[str, str], Edge] = {}
    for e in edges:
        k = (e.item, e.dep)
        if k not in best or rank[e.kind] < rank[best[k].kind]:
            best[k] = e
    return list(best.values())


def serial_corroboration(items: dict[str, Item], iid: str, dep: str) -> list[str]:
    """Stems of files created by the predecessor, and symbols it defines, that the item text mentions."""
    if dep.startswith("GATE-") or dep not in items:
        return []
    shared = SHARED_MERGEABLE | SHARED_NON_MERGEABLE | set(merge_rule_files())
    first = created_by(items)
    P, X = items[dep], items[iid]
    toks = set()
    for f in P.paths:
        if f in shared or first.get(f) != dep:
            continue
        stem = f.rsplit("/", 1)[-1].split(".")[0]
        if len(stem) >= 5 and stem not in ("__init__", "index"):
            toks.add(stem)
    for t, _ in code_spans(P.paths_line):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{7,}", t) and ("_" in t or re.search(r"[a-z][A-Z]", t)):
            toks.add(t)
    body = X.body.replace(X.prereq_text, "")
    return sorted(t for t in toks if re.search(r"(?<![\w/.-])" + re.escape(t) + r"(?![\w-])", body))


def migration_items(items: dict[str, Item]) -> dict[str, str]:
    out = {it.id: "Paths name db/migrations/versions/" for it in items.values()
           if any(p.startswith(MIGRATION_DIR) for p in it.paths + it.dirs)}
    for iid, adds in MIGRATION_REVIEW.items():
        if adds:
            out[iid] = "reviewed: adds database objects in its own revision without naming the file"
        else:
            out.pop(iid, None)
    return out


def schema_only_items(items: dict[str, Item], mig: dict[str, str]) -> list[str]:
    return [it.id for it in items.values() if not it.is_gate and it.id not in mig and it.id not in MIGRATION_REVIEW
            and it.schema.strip() and not it.schema.strip().lower().startswith("none")]


# --------------------------------------------------------------------------------------------------
# Plan access
# --------------------------------------------------------------------------------------------------
def load_plan() -> dict:
    return json.loads(PLAN.read_text(encoding="utf-8"))


def positions(plan: dict) -> dict[str, list[tuple[int, str, int, int]]]:
    pos: dict[str, list[tuple[int, str, int, int]]] = defaultdict(list)
    for li, level in enumerate(plan["levels"]):
        for lane in level["lanes"]:
            k = 0
            for bi, batch in enumerate(lane["batches"]):
                for item in batch["items"]:
                    pos[item].append((li, lane["id"], bi, k))
                    k += 1
    return pos


def item_touch(items: dict[str, Item], iid: str) -> set[str]:
    it = items[iid]
    s = set(it.paths) | set(it.dirs) | set(it.accept_files)
    for p in it.paths:
        if p.startswith("backend/erev_api/api/v1/") and not (REPO / p).exists():
            s |= {"backend/erev_api/api/router.py", "docs/api/openapi.json", "frontend/src/lib/api/schema.d.ts"}
        if p.startswith("backend/erev_api/db/tables/") and not (REPO / p).exists():
            s.add("backend/erev_api/db/tables/__init__.py")
    produced, _ = api_rows(it.api)
    if produced:
        s |= {"docs/api/openapi.json", "frontend/src/lib/api/schema.d.ts"}
    return s


def overlaps(a: set[str], b: set[str]) -> set[str]:
    res = set(a & b)
    for x in a:
        if x.endswith("/"):
            res |= {y for y in b if y.startswith(x)}
    for y in b:
        if y.endswith("/"):
            res |= {x for x in a if x.startswith(y)}
    return res


# --------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------
@dataclass
class Result:
    name: str
    ok: bool = True
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.failures.append(msg)


def run_checks(items: dict[str, Item], done: set[str], plan: dict, edges: list[Edge]):
    in_scope = list(plan["in_scope"])
    s_in = set(in_scope)
    deferred = set(plan["deferred"])
    pos = positions(plan)
    iam = {(x["item"], x["consumes"]) for x in plan.get("integration_after_merge", [])}
    by_item: dict[str, list[Edge]] = defaultdict(list)
    for e in edges:
        by_item[e.item].append(e)
    results: list[Result] = []

    rf = Result("(f) every in-scope item appears exactly once; in_scope, deferred and done partition the items")
    if len(in_scope) != len(s_in):
        rf.fail("in_scope holds duplicates")
    if set(plan["done"]) != done:
        rf.fail(f"plan done differs from git log: missing {sorted(done - set(plan['done']))}, "
                f"extra {sorted(set(plan['done']) - done)}")
    for a, b, name in ((s_in, deferred, "in_scope/deferred"), (s_in, done, "in_scope/done"),
                       (deferred, done, "deferred/done")):
        if a & b:
            rf.fail(f"overlap {name}: {sorted(a & b)}")
    if set(items) - s_in - deferred - done:
        rf.fail(f"items in no set: {sorted(set(items) - s_in - deferred - done)}")
    if (s_in | deferred) - set(items):
        rf.fail(f"unknown ids: {sorted((s_in | deferred) - set(items))}")
    for iid in in_scope:
        if len(pos.get(iid, [])) != 1:
            rf.fail(f"{iid} scheduled {len(pos.get(iid, []))} times")
    if set(pos) - s_in:
        rf.fail(f"scheduled but not in scope: {sorted(set(pos) - s_in)}")
    rf.notes.append(f"{len(s_in)} in scope, {len(deferred)} deferred, {len(done)} done, {len(items)} items")
    results.append(rf)

    re_ = Result("(e) batches hold 1 to 4 items; at most 5 lanes per level; merge orders list every lane once")
    for level in plan["levels"]:
        if len(level["lanes"]) > MAX_LANES:
            re_.fail(f"{level['id']} has {len(level['lanes'])} lanes")
        if sorted(level.get("merge_order", [])) != sorted(l["id"] for l in level["lanes"]):
            re_.fail(f"{level['id']} merge order does not list every lane exactly once")
        for lane in level["lanes"]:
            for b in lane["batches"]:
                if not BATCH_MIN <= len(b["items"]) <= BATCH_MAX:
                    re_.fail(f"{b['id']} holds {len(b['items'])} items")
    results.append(re_)

    ra = Result("(a) prerequisites are done, at an earlier level, earlier in the same lane, or a flagged contract")
    rb = Result("(b) no in-scope item depends on a deferred item")
    serial_open = []
    for iid in in_scope:
        if not pos.get(iid):
            continue
        li, lane, bi, k = pos[iid][0]
        for e in by_item.get(iid, []):
            d = e.dep
            if d in done:
                continue
            corr = serial_corroboration(items, iid, d) if not e.hard else []
            reviewed = (iid, d) in SERIAL_REVIEW
            if d in deferred or d not in s_in:
                if e.hard:
                    rb.fail(f"{iid} -> {d} [{e.kind}] {e.reason}")
                else:
                    serial_open.append((iid, d, "deferred", corr, reviewed))
                    if corr and not reviewed:
                        rb.fail(f"{iid} -> deferred {d}: loop-order edge corroborated by {corr}, not reviewed")
                continue
            dli, dlane, dbi, dk = pos[d][0]
            if dli < li or (dli == li and dlane == lane and (dbi, dk) < (bi, k)):
                continue
            same_level_other = dli == li and dlane != lane
            where = "same level, other lane" if same_level_other else (
                "later in the same lane" if dli == li else "later level")
            if e.hard:
                if same_level_other and (iid, d) in iam and e.kind in CONTRACT_OK_KINDS:
                    ra.notes.append(f"contract edge {iid} -> {d} in {plan['levels'][li]['id']} [{e.kind}]")
                    continue
                ra.fail(f"{iid} ({plan['levels'][li]['id']}/{lane}) -> {d} ({plan['levels'][dli]['id']}/{dlane}): "
                        f"{where} [{e.kind}] {e.reason}")
            else:
                serial_open.append((iid, d, where, corr, reviewed))
                if corr and not reviewed:
                    ra.fail(f"{iid} -> {d} ({where}): loop-order edge corroborated by {corr}, not reviewed")
    for x in plan.get("integration_after_merge", []):
        if (x["item"], x["consumes"]) not in {(e.item, e.dep) for e in edges if e.hard}:
            ra.notes.append(f"integration note {x['item']} on {x['consumes']} has no derived hard edge (kept)")
        elif not (pos.get(x["item"]) and pos.get(x["consumes"])
                  and pos[x["item"]][0][0] == pos[x["consumes"]][0][0]
                  and pos[x["item"]][0][1] != pos[x["consumes"]][0][1]):
            ra.fail(f"integration note {x['item']} on {x['consumes']} but they are not in other lanes of one level")
    ra.notes.append(f"{len(serial_open)} loop-order edges are not satisfied by position; none is corroborated "
                    f"without a review entry")
    results += [ra, rb]

    rc = Result("(c) every MVP capability is covered by in-scope items")
    excl = plan.get("root_exclusions", {})
    for cap, spec in CAPABILITIES.items():
        for iid in spec.get("required", []):
            if iid not in s_in and iid not in done:
                rc.fail(f"{cap}: {iid} is not in scope")
        opt = spec.get("optional", [])
        if opt:
            ins = [i for i in opt if i in s_in]
            outs = [i for i in opt if i not in s_in and i not in done]
            for i in outs:
                if i not in excl and not plan.get("deferred_notes", {}).get(i):
                    rc.fail(f"{cap}: optional {i} excluded without a recorded reason")
            if len(ins) < spec.get("min_optional_in_scope", 0):
                rc.fail(f"{cap}: fewer than {spec['min_optional_in_scope']} optional items in scope")
            if spec.get("fallback") and outs and spec["fallback"] not in SPRINT.read_text(encoding="utf-8"):
                rc.fail(f"{cap}: fallback {spec['fallback']} not described in SPRINT-1.0rc.md")
            rc.notes.append(f"{cap}: in scope {ins or 'none'}; excluded {outs or 'none'}")
    for i in ("GPB-4", "AKS-8", "RPS-23", "RPS-24"):
        if i in deferred:
            hard_def = sorted({e.dep for e in by_item.get(i, []) if e.dep in deferred and e.hard})
            rc.notes.append(f"exclusion {i}: derived hard edges to deferred items {hard_def or 'none'}; "
                            f"recorded reason: {excl.get(i, '')[:90]}")
    results.append(rc)

    rd = Result("(d) one migration lane per level; no unruled overlap on shared files; no other overlap")
    mig = migration_items(items)
    rules = merge_rule_files()
    for level in plan["levels"]:
        mig_lanes, touch = [], {}
        for lane in level["lanes"]:
            ids = [i for b in lane["batches"] for i in b["items"]]
            lm = [i for i in ids if i in mig]
            if lm:
                mig_lanes.append((lane["id"], lm))
            if bool(lm) != bool(lane.get("adds_migrations")):
                rd.fail(f"{lane['id']} adds_migrations={lane.get('adds_migrations')} but migration items {lm}")
            touch[lane["id"]] = set().union(*(item_touch(items, i) for i in ids)) if ids else set()
        if len(mig_lanes) > 1:
            rd.fail(f"{level['id']}: {len(mig_lanes)} lanes add migrations: {mig_lanes}")
        ids_l = [l["id"] for l in level["lanes"]]
        for i in range(len(ids_l)):
            for j in range(i + 1, len(ids_l)):
                for f in sorted(overlaps(touch[ids_l[i]], touch[ids_l[j]])):
                    tag = f"{level['id']} {ids_l[i]} x {ids_l[j]}: {f}"
                    if f in SHARED_NON_MERGEABLE or f.startswith(MIGRATION_DIR):
                        rd.fail(tag + " (non-mergeable shared file)")
                    elif f in rules:
                        rd.notes.append(tag + (" (brief shared file; 4.3 rule)" if f in SHARED_MERGEABLE
                                               else " (union file; 4.3 rule)"))
                    else:
                        rd.fail(tag + (" (brief shared file without a 4.3 rule)" if f in SHARED_MERGEABLE
                                       else " (file overlap without a merge rule)"))
    so = [i for i in schema_only_items(items, mig) if i in s_in]
    if so:
        rd.fail(f"in-scope items with a Schema change and no revision path, not reviewed: {so}")
    results.append(rd)
    return results, serial_open


# --------------------------------------------------------------------------------------------------
# Answer keys
# --------------------------------------------------------------------------------------------------
def key_support(items: dict[str, Item], plan: dict) -> dict:
    deferred = set(plan["deferred"])
    evidence = {}
    for owner, words in KEY_BLOCKER_EVIDENCE.items():
        text = (items[owner].title + " " + items[owner].engine).lower()
        evidence[owner] = {"deferred": owner in deferred, "title_names": all(w in text for w in words)}
    fam = defaultdict(lambda: {"active": 0, "runnable": 0, "blocked_by": set()})
    blocked: dict[str, list[str]] = {}
    for f in sorted(KEYS_DIR.rglob("*.yaml")):
        if f.parent.name.startswith("_"):
            continue
        t = f.read_text(encoding="utf-8")
        status = re.search(r'^status:\s*"?(\w+)"?', t, re.M)
        if not status or status.group(1) != "active":
            continue
        kid = re.search(r'^id:\s*"?([^"\n]+)"?', t, re.M).group(1).strip()
        runner = re.search(r'^runner:\s*"?(\w+)"?', t, re.M)
        values = set(re.findall(r'recognition_method:\s*"?([A-Z_]+)"?', t)) | \
            set(re.findall(r'event_type:\s*"?([A-Z_]+)"?', t))
        by = {KEY_BLOCKERS[v] for v in values if v in KEY_BLOCKERS and KEY_BLOCKERS[v] in deferred}
        if runner and runner.group(1) != "engine" and "PRP-1" in deferred:
            by.add("PRP-1")
        family = f.parent.name.upper()
        fam[family]["active"] += 1
        if by:
            blocked[kid] = sorted(by)
            fam[family]["blocked_by"] |= by
        else:
            fam[family]["runnable"] += 1
    return {"families": {k: {**v, "blocked_by": sorted(v["blocked_by"])} for k, v in sorted(fam.items())},
            "blocked": blocked, "runnable_total": sum(v["runnable"] for v in fam.values()),
            "active_total": sum(v["active"] for v in fam.values()), "blocker_evidence": evidence}


# --------------------------------------------------------------------------------------------------
# Minutes, critical path, apply
# --------------------------------------------------------------------------------------------------
def scope_minutes() -> dict[str, tuple[str, int]]:
    """Kind and minutes of each in-scope item from the SPRINT-1.0rc.md scope table (the plan's cost model)."""
    text = SPRINT.read_text(encoding="utf-8")
    m = re.search(r"### Scope table\n(.*?)\n### ", text, re.S)
    out = {}
    for row in (m.group(1).splitlines() if m else []):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.fullmatch(ID, cells[0]):
            out[cells[0]] = (cells[2], int(cells[3]))
    return out


def critical_path(plan: dict, edges: list[Edge]) -> tuple[float, list[str]]:
    s_in = set(plan["in_scope"])
    mins = scope_minutes()
    deps = defaultdict(set)
    for e in edges:
        if e.hard and e.item in s_in and e.dep in s_in:
            deps[e.item].add(e.dep)
    memo: dict[str, tuple[int, list[str]]] = {}

    def longest(i: str, stack: tuple = ()) -> tuple[int, list[str]]:
        if i in memo:
            return memo[i]
        if i in stack:
            raise RuntimeError(f"dependency cycle {stack + (i,)}")
        best = (0, [])
        for d in sorted(deps[i]):
            v = longest(d, stack + (i,))
            if v[0] > best[0]:
                best = v
        memo[i] = (best[0] + mins.get(i, ("", 35))[1], best[1] + [i])
        return memo[i]

    top = max((longest(i) for i in sorted(s_in)), key=lambda x: x[0])
    return round(top[0] / 60, 1), top[1]


def apply_layout(items: dict[str, Item], done: set[str], edges: list[Edge]) -> None:
    plan = load_plan()
    mins = scope_minutes()
    mig = migration_items(items)
    rules = merge_rule_files()
    old_lanes = {i: (lv["id"], ln) for lv in plan["levels"] for ln in lv["lanes"] for b in ln["batches"]
                 for i in b["items"]}
    fragments: dict[str, list[str]] = defaultdict(list)
    for lv in plan["levels"]:
        for ln in lv["lanes"]:
            for b in ln["batches"]:
                for frag in [x for x in re.split(r";\s+(?=" + ID + r"\b)", b.get("notes", "")) if x.strip()]:
                    m = re.match(r"^(" + ID + r")\b", frag)
                    if m:
                        fragments[m.group(1)].append(frag.strip())
    iam = [x for x in plan.get("integration_after_merge", []) if (x["item"], x["consumes"]) not in IAM_REMOVE]
    for add in IAM_ADD:
        if not any(x["item"] == add["item"] and x["consumes"] == add["consumes"] for x in iam):
            iam.append(add)
    for x in iam:
        pass
    iam_frag_removed = {f"{a} integration-after-merge: codes against the contract of {b}" for a, b in IAM_REMOVE}
    for iid in list(fragments):
        fragments[iid] = [f for f in fragments[iid] if not any(f.startswith(r) for r in iam_frag_removed)]
    for add in IAM_ADD:
        frag = f"{add['item']} integration-after-merge: codes against the contract of {add['consumes']} " \
               f"({add['reason']})"
        if frag not in fragments[add["item"]]:
            fragments[add["item"]].append(frag)

    for lv in plan["levels"]:
        spec = LAYOUT.get(lv["id"])
        if not spec:
            continue
        new_lanes = []
        for n, ls in enumerate(spec, start=1):
            first = ls["batches"][0][0]
            _, old = old_lanes[first]
            lane_id = f"{lv['id']}-{n}"
            ids = [i for b in ls["batches"] for i in b]
            old_ids = [i for b in old["batches"] for i in b["items"]]
            batches = []
            for k, b in enumerate(ls["batches"], start=1):
                notes = "; ".join(f for i in b for f in fragments.get(i, []))
                batches.append({"id": f"{lane_id}-B{k}", "items": b, "minutes": sum(mins[i][1] for i in b),
                                "notes": notes})
            lane = {"id": lane_id, "name": ls.get("name", old["name"]), "family": ls.get("family", old["family"]),
                    "minutes": sum(b["minutes"] for b in batches), "adds_migrations": any(i in mig for i in ids)}
            if sorted(ids) == sorted(old_ids):
                lane["file_scope"], lane["shared_hotspots"] = old["file_scope"], old["shared_hotspots"]
            else:
                touch = set().union(*(item_touch(items, i) for i in ids))
                hot = SHARED_MERGEABLE | SHARED_NON_MERGEABLE | set(rules)
                lane["file_scope"] = sorted(t for t in touch if t not in hot)
                lane["shared_hotspots"] = sorted(t for t in touch if t in hot)
                lane["file_scope_source"] = "validate_plan.py (Scope Paths and Acceptance files)"
            lane["batches"] = batches
            new_lanes.append(lane)
        lv["lanes"] = new_lanes
        lv["merge_order"] = [l["id"] for l in new_lanes]
    # batch notes of unchanged levels that carry iam fragments (for example RPS-6 in L10)
    for lv in plan["levels"]:
        if lv["id"] in LAYOUT:
            continue
        for ln in lv["lanes"]:
            for b in ln["batches"]:
                b["notes"] = "; ".join(f for i in b["items"] for f in fragments.get(i, []))

    # derived level fields
    params = plan["parameters"]
    web11_level = None
    cumulative = 0
    level_hours = []
    for li, lv in enumerate(plan["levels"]):
        ids = [i for ln in lv["lanes"] for b in ln["batches"] for i in b["items"]]
        if "WEB-11" in ids:
            web11_level = li
        screens = web11_level is not None and any(mins[i][0] == "screen" for i in ids)
        iam_items = {x["item"] for x in iam if x["level"] == lv["id"]}
        est = max(ln["minutes"] for ln in lv["lanes"]) + params["merge_minutes"] + \
            (params["merge_e2e_minutes"] if screens else 0) + 10 * len(iam_items)
        lv["estimate_minutes"] = est
        cumulative += est
        lv["cumulative_hours"] = round(cumulative / 60, 1)
        level_hours.append(round(est / 60, 1))
        e2e = "make e2e SPEC=frontend/e2e/projects/screens.spec.ts"
        gates = [g for g in lv["merge_gates"] if g != e2e]
        if screens:
            gates.append(e2e)
        lv["merge_gates"] = gates
    plan["integration_after_merge"] = iam
    plan["estimate_hours"] = round(cumulative / 60, 1)
    merged, cum = [], 0
    for li, lv in enumerate(plan["levels"]):
        cum += lv["estimate_minutes"]
        merged += [i for ln in lv["lanes"] for b in ln["batches"] for i in b["items"]]
        if cum / 60 >= 9.0:
            plan["horizon_9h"] = {"levels_complete": li + 1, "boundary_hours": round(cum / 60, 1),
                                  "items_merged": merged}
            break
    for v in plan.get("variants", []):
        if v["id"] == "V-0":
            v["estimate_hours"] = plan["estimate_hours"]
            v["level_hours"] = level_hours
            v["levels"] = len(plan["levels"])
            v["items_merged_by_9h"] = len(plan["horizon_9h"]["items_merged"])
            v["integration_after_merge_items"] = len({x["item"] for x in iam})
            v["levels_compact"] = [[{"items": [i for b in ln["batches"] for i in b["items"]],
                                     "adds_migrations": ln["adds_migrations"], "minutes": ln["minutes"]}
                                    for ln in lv["lanes"]] for lv in plan["levels"]]
            v["description"] = "plan as emitted, with the validator layout fixes V-01 to V-09 applied"
        else:
            v["validator_note"] = ("computed by plan_tools.py on the pre-validation layout; not re-validated. The "
                                   "V-01 to V-08 edges apply to this variant too")
    results, _ = run_checks(items, done, plan, edges)
    h, path = critical_path(plan, edges)
    plan["validation"] = {
        "validator": "sprint-validator", "script": "python3 docs/build-spec/sprint/validate_plan.py check",
        "run_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build_spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "checks": [{"name": r.name, "ok": r.ok, "failures": r.failures} for r in results],
        "fixes": FIXES, "critical_path_hours": h, "critical_path": path,
        "regeneration_warning": "plan_tools.py all rewrites plan.json and the generated block; add the VERIFIED_EDGES "
                                "of validate_plan.py to its MANUAL_EDGES first, or rerun validate_plan.py apply",
    }
    PLAN.write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    render_sprint_tables(plan)


def render_sprint_tables(plan: dict) -> None:
    text = SPRINT.read_text(encoding="utf-8")
    out = ["### Levels", ""]
    for lv in plan["levels"]:
        out += ["", f"#### {lv['id']}: about {lv['estimate_minutes'] / 60:.1f} h (cumulative {lv['cumulative_hours']} h)",
                "", "| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |", "|---|---|---|---|---|"]
        for ln in lv["lanes"]:
            bt = "<br>".join(f"B{k}: {', '.join(b['items'])} ({b['minutes']})" for k, b in enumerate(ln["batches"], 1))
            nt = "<br>".join(b["notes"] for b in ln["batches"] if b.get("notes"))
            out.append(f"| {ln['id']} | {ln['name']} | {'yes' if ln['adds_migrations'] else 'no'} | {bt} | {nt} |")
        out += ["", "Merge order: " + " → ".join(lv["merge_order"]), "", "Merge gates:", ""]
        for g in lv["merge_gates"]:
            out.append(f"- `{g}`" if len(g) <= 280 else f"- `{g[:280]} …` (full selection in plan.json)")
    block = "\n".join(out) + "\n\n"
    text = re.sub(r"### Levels\n.*?(?=### Answer-key support by family)", lambda _: block, text, flags=re.S)
    v0 = next(v for v in plan["variants"] if v["id"] == "V-0")
    text = re.sub(r"^\| V-0 \|.*$", lambda _: f"| V-0 | {v0['description']} | {v0['in_scope']} | "
                  f"{v0['migration_items']} | {v0['levels']} | {v0['estimate_hours']} | {v0['items_merged_by_9h']} | "
                  f"none |", text, count=1, flags=re.M)
    SPRINT.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    items = parse_spec()
    done = done_ids(items)
    edges = derive_edges(items, done)
    if cmd == "apply":
        apply_layout(items, done, edges)
        cmd = "check"
    plan = load_plan()
    if cmd == "edges":
        for iid in argv[2:]:
            it = items[iid]
            print(f"{iid} {it.title}\n  prereq: {it.prereq_text}\n  paths: {it.paths}\n  dirs: {it.dirs}")
            for e in sorted(edges, key=lambda x: x.dep):
                if e.item == iid:
                    st = "done" if e.dep in done else ("in" if e.dep in plan["in_scope"] else "DEFERRED")
                    print(f"   -> {e.dep:8} {st:8} [{e.kind}] {e.reason}")
        return 0
    results, serial_open = run_checks(items, done, plan, edges)
    if cmd == "serial":
        for iid, d, where, corr, reviewed in serial_open:
            print(f"{iid} -> {d}: {where}; corroboration {corr or 'none'}{'; reviewed' if reviewed else ''}")
        return 0
    if cmd == "keys":
        print(json.dumps(key_support(items, plan), indent=1))
        return 0
    if cmd == "critical":
        h, path = critical_path(plan, edges)
        print(h, " -> ".join(path))
        return 0
    if cmd == "json":
        h, path = critical_path(plan, edges)
        ks = key_support(items, plan)
        print(json.dumps({"checks": [{"name": r.name, "ok": r.ok, "failures": r.failures, "notes": r.notes}
                                     for r in results], "critical_path_hours": h, "critical_path": path,
                          "serial_open": serial_open, "in_scope": len(plan["in_scope"]),
                          "levels": len(plan["levels"]), "keys": {k: ks[k] for k in ("families", "runnable_total",
                                                                                     "active_total",
                                                                                     "blocker_evidence")}},
                         indent=1))
        return 0 if all(r.ok for r in results) else 1
    ok = True
    for r in results:
        print(("PASS " if r.ok else "FAIL ") + r.name)
        for f in r.failures:
            print("   x " + f)
        if "-v" in argv:
            for n in r.notes:
                print("   . " + n)
        ok &= r.ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
