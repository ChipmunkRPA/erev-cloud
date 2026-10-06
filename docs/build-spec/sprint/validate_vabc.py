#!/usr/bin/env python3
"""Independent validator of the V-ABC sprint plan, levels L2 onward (slug ``validate-vabc``).

Level L1 is the validated L1 of ``plan.json`` and counts as merged (D-82). The script does not import the planner's
generator (``plan_tools.py``, ``.scratch/sprint-vabc/*``). Its sources:

* BUILD_SPEC item blocks, derived edges, migration items, file touches and answer-key support, through the V-0
  validator's parser (``validate_plan.py``: ``parse_spec``, ``derive_edges``, ``migration_items``, ``item_touch``,
  ``serial_corroboration``, ``key_support``, ``merge_rule_files``, ``scope_minutes``);
* the planner's verified ``MANUAL_EDGES``, its contract lists and the approved ``RULING_R_RC_1``, read from
  ``plan_tools.py`` as literals with ``ast`` (nothing of that module runs);
* D-82 in ``docs/01-DECISIONS.md``, SPRINT-1.0rc.md §3.1, §3.2 and §4.3, SPRINT-vabc.md §5.3, ``sup-rc-smoke.md``;
* the edges, review entries and partial fragments this validator confirmed by reading the item text (below).

Checks of ``plan-vabc.json``:

(a) ordering: every edge of a scheduled item is done, in L1, at an earlier level or earlier in the same lane. A
    same-level edge to another lane passes only with an integration-after-merge note and a contract kind (engine
    state type, 04 API binding of a screen, or V-C: platform consumer of an engine item). Corroborated loop-order
    edges must be satisfied or reviewed. Integration notes must match a same-level, cross-lane edge;
(b) no in-scope item (L1, L2 onward, supervisor item) depends on a deferred item, except R-RC-1 dropped edges, review
    entries and recorded partial fragments; the moved set equals D-82; each dropped edge of a scheduled item carries
    its R-RC-1 note;
(c) the MVP capabilities of SPRINT-1.0rc.md §1 and §3 are covered; the §3.1 forced prerequisites are in scope or moved
    by R-RC-1; the J-01 fallback SUP-RC-SMOKE sits in the last level;
(d) per level at most two migration lanes, flags agree, the second is merged second and re-parented onto the first,
    and no edge joins them; cross-lane file overlaps are §4.3 regenerate or union files, or the V-A files between the
    two migration lanes; correction items keep ``backend/erev_engine/stages/`` to themselves;
(e) batches hold 1 to 4 items and at most 75 minutes, at most 5 lanes, lane ids and worktrees follow merge order,
    migration lanes merge first and lanes with screens last; lane box 240 minutes unless declared with a fallback;
(f) every in-scope item appears exactly once; done, in scope and deferred partition the 427 items; in scope equals the
    V-0 scope less the moved items;
(g) arithmetic and gates: batch, lane and level minutes, cumulative hours, merge gates (re-parenting, properties,
    answer keys, parity, e2e) and the release list of runnable keys.

Usage::

    python3 -B docs/build-spec/sprint/validate_vabc.py check [-v]
    python3 -B docs/build-spec/sprint/validate_vabc.py edges ID [ID…]
    python3 -B docs/build-spec/sprint/validate_vabc.py serial
    python3 -B docs/build-spec/sprint/validate_vabc.py record   # writes plan-vabc.json "validation"

Read-only except ``record``. It never runs make, pytest, servers or write-git.
"""
from __future__ import annotations

import ast
import datetime as _dt
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import validate_plan as vp  # noqa: E402

REPO = vp.REPO
PLAN = HERE / "plan-vabc.json"
PLAN_V0 = HERE / "plan.json"
SPRINT = HERE / "SPRINT-vabc.md"
TOOLS = HERE / "plan_tools.py"
DECISIONS = REPO / "docs" / "01-DECISIONS.md"
SUP = "SUP-RC-SMOKE"

ENGINE = {"ENA", "ENB", "ENC", "END", "EDS"}
PLATFORM = {"RFD", "CTR", "DIN", "CLO", "RPS", "WEB"}
MAX_MIG_LANES, MAX_LANES = 2, 5
LANE_BOX, BATCH_BOX = 240, 75
MERGE, MERGE_E2E, IAM_MIN, REPARENT_MIN = 35, 25, 10, 10
L1_MINUTES = 275
VA_FILES = {"backend/tests/pg/test_migrations.py", "backend/tests/pg/test_catalogue_lint.py"}
CORRECTION_SCOPE = "backend/erev_engine/stages/"
MEASURE_BLOCKERS = {"revenue_prior_period": "EDS-4"}   # ENGINE_SPEC_B §15.2.4 measure asserted in key traces
SCREENS_E2E = "make e2e SPEC=frontend/e2e/projects/screens.spec.ts"
SMOKE_E2E = "make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts"
REPARENT_GATE = 'make test-pg K="test_single_head or test_upgrade_downgrade_upgrade'

# Edges confirmed by this validator in the item text (item, dependency, evidence).
VABC_VERIFIED: list[tuple[str, str, str]] = [
    ("CTR-3", "END-9", "test_active_contract_posts_sealed_balanced_posting computes an activated K-11 and asserts O1 "
                       "revenue 53,504.59 EUR; postings are persisted from the erev_engine.compute output (END-9)"),
    ("CTR-4", "END-9", "test_create_draft_computes_provisional_version and test_allocation_walk_sf_ord_20417 assert the "
                       "KPIs and allocation walk (97,627.12) of a computed version (erev_engine.compute, END-9)"),
    ("DIN-15", "DIN-9", "the WLD-B-04 seed uploads avm-us-progress-2026-09-invalid.csv, a Progress events (CSV v2) "
                        "import (SCREENS §12.2 validate wireframe), then commits the corrected file; DIN-3 creates only "
                        "the customers and contracts emitters, progress_events.py is DIN-9"),
    ("DIN-16", "DIN-9", "the REQ-UX-021 step uploads avm-de-progress-2026-09.csv (WLD-F-21), uploaded with template "
                        "Progress events (CSV v2) (PRD J-04.1; DIN-9 test_progress_events_k11); the SF-10:detail capture "
                        "reads the WLD-B-04 import seeded by DIN-15"),
    ("DIN-17", "DIN-9", "SF-11:item captures a WLD-B-04 exception item, created by the DIN-15 seed through the CSV v2 "
                        "progress_events template (DIN-9)"),
]

# Edges of the supervisor item, read from sup-rc-smoke.md (prerequisites and steps). kind: hard | contract.
SUP_EDGES: list[tuple[str, str, str]] = [
    ("RPS-7", "hard", "SF-04 schedules (RC-SMOKE.6); previous batch of the lane"),
    ("RPS-6", "hard", "SF-08:report waterfall and RPO (RC-SMOKE.10)"),
    ("WEB-12", "hard", "personas and TOTP sign-in (RC-SMOKE.1)"),
    ("WEB-15", "hard", "SF-12:request approvals (RC-SMOKE.3, RC-SMOKE.8)"),
    ("CTR-20", "hard", "K-01, K-02 and K-09 seeded figures"),
    ("CTR-21", "hard", "SF-02 grid Contracts (RC-SMOKE.5)"),
    ("CTR-22", "hard", "SF-03 frame and obligation pane (RC-SMOKE.5)"),
    ("CTR-23", "hard", "SF-03:schedules (RC-SMOKE.6)"),
    ("CTR-26", "hard", "Explain panel (RC-SMOKE.6)"),
    ("DIN-4", "hard", "legacy SKU SSP template commits LEGACY-SKU-SSP 2023-01-01 (RC-SMOKE.2, RC-SMOKE.3)"),
    ("DIN-5", "hard", "legacy v1 progress findings"),
    ("DIN-10", "hard", "Map columns step 'Not needed: legacy template headers matched' (RC-SMOKE.2)"),
    ("DIN-15", "hard", "WLD-B-04 import seed (RC-SMOKE.4)"),
    ("DIN-16", "hard", "SF-10:new and SF-10:detail (RC-SMOKE.2, RC-SMOKE.4)"),
    ("CLO-8", "hard", "journal run calculation (RC-SMOKE.7)"),
    ("CLO-11", "hard", "journal run approval (RC-SMOKE.8)"),
    ("CLO-13", "hard", "CSV export and batch download manifest (RC-SMOKE.9)"),
    ("CLO-26", "hard", "SF-06 journal run screens (RC-SMOKE.7 to RC-SMOKE.9)"),
    ("RPS-3", "hard", "revenue_waterfall builder (RC-SMOKE.10)"),
    ("RPS-4", "hard", "rpo builder (RC-SMOKE.10)"),
    ("DIN-9", "hard", "RC-SMOKE.4 reads the WLD-B-04 import, seeded through the CSV v2 progress_events template"),
    ("RPS-22", "contract", "landing route /home and the completed rail (BS-D-08; SCREENS SCR-IA-01)"),
]

# Acceptance fragments that wait for a deferred item (item, deferred dependency) -> fragment. The lane runs the rest,
# records a SPEC-Q and leaves the item unticked, as for the partial answer-key items of SPRINT-1.0rc.md §3.3.
PARTIAL: dict[tuple[str, str], str] = {
    ("DIN-15", "DIN-9"): "the WLD-B-04 seed test and the SF-10 grid row of the WLD-B-04 import",
    ("DIN-16", "DIN-9"): "the REQ-UX-021 job-progress step on WLD-F-21 and the SF-10:detail WLD-B-04 capture",
    ("DIN-17", "DIN-9"): "the SF-11:item capture of a WLD-B-04 item",
    (SUP, "DIN-9"): "RC-SMOKE.4 (WLD-B-04 findings)",
}

# Derived edges reviewed by this validator as over-approximations (item, dependency) -> reason.
REVIEWED: dict[tuple[str, str], str] = {
    ("CTR-22", "CTR-14"): "API-R-28 has several producers; SF-03 frame and obligation pane bind CTR-4 reads, API-R-29, "
                          "API-R-30 and API-R-33, not the CTR-14 usage-commitment and cost routes",
    ("CLO-13", "DIN-14"): "adapters/gl/ does not exist on main; CLO-13 creates the package beside csv.py; DIN-14 only adds "
                          "the NetSuite module (plan_tools IGNORED_AUTO_EDGES)",
    ("RPS-22", "CLO-6"): "API-R-09 is the PLF approvals row bound by WEB-15; CLO-6 adds lock execution on approval only",
    ("RPS-7", "CLO-6"): "SF-04 binds GET /periods (RFD-1, blockers from CLO-4); lock routes are not called",
    ("RPS-7", "CLO-7"): "SF-04 does not call request-reopen",
}


def tools_literal(name: str):
    for node in ast.parse(TOOLS.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def d82_moved() -> set[str]:
    text = DECISIONS.read_text(encoding="utf-8")
    m = re.search(r"\*\*D-82 .*?The moved items are (.*?) \|", text, re.S)
    out: set[str] = set()
    for part in re.split(r",\s*|\s+and\s+", m.group(1) if m else ""):
        r = re.match(r"([A-Z]{3})-(\d+) to [A-Z]{3}-(\d+)", part.strip())
        if r:
            out |= {f"{r.group(1)}-{n}" for n in range(int(r.group(2)), int(r.group(3)) + 1)}
        elif re.fullmatch(vp.ID, part.strip()):
            out.add(part.strip())
    return out


def phase(iid: str) -> str:
    return "SUP" if iid == SUP else iid.split("-")[0]


@dataclass
class Edge:
    item: str
    dep: str
    source: str   # derived | manual | vabc | sup
    kind: str
    reason: str

    @property
    def hard(self) -> bool:
        return self.kind != "serial"


@dataclass
class Result:
    name: str
    ok: bool = True
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.failures.append(msg)


class Ctx:
    def __init__(self) -> None:
        self.items = vp.parse_spec()
        self.done = vp.done_ids(self.items)
        self.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        self.v0 = json.loads(PLAN_V0.read_text(encoding="utf-8"))
        self.l1 = [i for ln in self.v0["levels"][0]["lanes"] for b in ln["batches"] for i in b["items"]]
        self.dropped = {(a, b) for a, b, _ in tools_literal("RULING_R_RC_1")}
        self.api_contracts = set(tools_literal("API_SCREEN_CONTRACTS"))
        self.moved = d82_moved()
        self.deferred = set(self.plan["deferred"])
        self.in_scope = list(self.plan["in_scope"])
        self.iam = {(x["item"], x["consumes"]): x for x in self.plan.get("integration_after_merge", [])}
        self.pos: dict[str, list[tuple[int, str, int, int]]] = defaultdict(list)
        for iid in self.l1:
            self.pos[iid].append((1, "L1", 0, 0))
        for lv in self.plan["levels"]:
            n = int(lv["id"][1:])
            for ln in lv["lanes"]:
                k = 0
                for bi, b in enumerate(ln["batches"]):
                    for iid in b["items"]:
                        self.pos[iid].append((n, ln["id"], bi, k))
                        k += 1
        self.edges = self._edges()

    def _edges(self) -> dict[str, list[Edge]]:
        out: dict[str, list[Edge]] = defaultdict(list)
        for e in vp.derive_edges(self.items, self.done):
            out[e.item].append(Edge(e.item, e.dep, "derived", e.kind, e.reason))
        for a, b, kind, why in tools_literal("MANUAL_EDGES"):
            out[a].append(Edge(a, b, "manual", kind, why))
        for a, b, why in VABC_VERIFIED:
            out[a].append(Edge(a, b, "vabc", "verified", why))
        for b, kind, why in SUP_EDGES:
            out[SUP].append(Edge(SUP, b, "sup", kind, why))
        for iid in list(out):
            out[iid] = [e for e in out[iid] if (e.item, e.dep) not in self.dropped and e.dep != e.item]
        return out

    def pairs(self, iid: str) -> dict[str, list[Edge]]:
        by: dict[str, list[Edge]] = defaultdict(list)
        for e in self.edges.get(iid, []):
            by[e.dep].append(e)
        return by

    def scheduled(self) -> list[str]:
        return [i for lv in self.plan["levels"] for ln in lv["lanes"] for b in ln["batches"] for i in b["items"]]

    def lane_notes(self, iid: str) -> str:
        for lv in self.plan["levels"]:
            for ln in lv["lanes"]:
                for b in ln["batches"]:
                    if iid in b["items"]:
                        return (ln.get("notes") or "") + " " + (b.get("notes") or "")
        return ""


# --------------------------------------------------------------------------------------------------
# (a), (b)
# --------------------------------------------------------------------------------------------------
def contract_ok(c: Ctx, iid: str, dep: str, edges: list[Edge]) -> bool:
    """Same-level cross-lane edge acceptable as integration after merge (D-81, D-82 V-C)."""
    vc = phase(iid) in PLATFORM and phase(dep) in ENGINE
    for e in edges:
        if e.source == "derived" and e.kind in ("state", "api-bind", "serial"):
            continue
        if e.source == "manual" and (e.kind == "contract" or (iid, dep) in c.api_contracts):
            continue
        if e.source == "sup" and e.kind == "contract":
            continue
        if vc:
            continue
        return False
    return True


def check_ab(c: Ctx) -> tuple[Result, Result, list[tuple]]:
    ra = Result("(a) ordering: edges done, in L1, earlier, or a flagged contract; integration notes match")
    rb = Result("(b) no in-scope item depends on a deferred item (R-RC-1, reviews and partial fragments excepted)")
    serial_open = []
    sched = c.scheduled()
    s_in = set(c.in_scope)
    for iid in c.l1 + sched:
        is_l2 = iid in sched
        where_i = c.pos[iid][0] if c.pos.get(iid) else None
        for dep, es in c.pairs(iid).items():
            if dep in c.done or (iid, dep) in REVIEWED or (iid, dep) in vp.SERIAL_REVIEW:
                continue
            hard = [e for e in es if e.hard]
            corr = [] if hard or iid == SUP else vp.serial_corroboration(c.items, iid, dep)
            if dep in c.deferred or (dep not in s_in and dep not in c.pos):
                if (iid, dep) in PARTIAL:
                    notes = c.lane_notes(iid)
                    if not re.search(re.escape(iid) + r" partial[^;]*" + re.escape(dep), notes):
                        rb.fail(f"{iid} -> {dep}: partial fragment without a batch note")
                    rb.notes.append(f"partial {iid} -> {dep}: {PARTIAL[(iid, dep)]}")
                elif hard:
                    rb.fail(f"{iid} -> deferred {dep} [{hard[0].source}/{hard[0].kind}] {hard[0].reason[:120]}")
                elif corr:
                    rb.fail(f"{iid} -> deferred {dep}: loop-order edge corroborated by {corr}")
                continue
            if not is_l2 or dep in c.l1 and not c.pos[dep][0][0] > 1:
                continue
            li, lane, bi, k = where_i
            dli, dlane, dbi, dk = c.pos[dep][0]
            if dli < li or (dli == li and dlane == lane and (dbi, dk) < (bi, k)):
                continue
            other = dli == li and dlane != lane
            where = "same level, other lane" if other else ("later in the same lane" if dli == li else "later level")
            if not hard:
                serial_open.append((iid, dep, where, corr))
                if corr:
                    ra.fail(f"{iid} -> {dep} ({where}): loop-order edge corroborated by {corr}, not reviewed")
                continue
            note = c.iam.get((iid, dep))
            if other and note and note["level"] == f"L{li}" and contract_ok(c, iid, dep, hard):
                ra.notes.append(f"contract {iid} -> {dep} in L{li} ({note['kind']})")
                continue
            ra.fail(f"{iid} ({lane}) -> {dep} ({dlane}): {where}; kinds "
                    f"{sorted({(e.source, e.kind) for e in hard})}; note {'yes' if note else 'no'}; {hard[0].reason[:100]}")
    for (iid, dep), x in c.iam.items():
        p, q = c.pos.get(iid), c.pos.get(dep)
        if not (p and q and p[0][0] == q[0][0] and p[0][1] != q[0][1] and x["level"] == f"L{p[0][0]}"):
            ra.fail(f"integration note {iid} on {dep} does not join two lanes of level {x['level']}")
        elif not any(e.hard for e in c.pairs(iid).get(dep, [])):
            ra.notes.append(f"integration note {iid} on {dep} has no hard edge (kept)")
        if x["kind"].startswith("V-C") and not (phase(iid) in PLATFORM and phase(dep) in ENGINE):
            ra.fail(f"integration note {iid} on {dep} is marked V-C but is not platform on engine")
    ra.notes.append(f"{len(serial_open)} loop-order edges not satisfied by position, none corroborated")
    # R-RC-1: moved set, deferral and notes
    moved_plan = set(c.v0["in_scope"]) - s_in
    if moved_plan != c.moved:
        rb.fail(f"moved items differ from D-82: plan {sorted(moved_plan)}, D-82 {sorted(c.moved)}")
    if c.deferred != set(c.v0["deferred"]) | c.moved:
        rb.fail("deferred is not the V-0 deferred set plus the moved items")
    for a, b in sorted(c.dropped):
        notes = c.lane_notes(a)
        if a in sched and b in c.moved and not (f"{a} R-RC-1" in notes and f"({b} post-rc" in notes):
            rb.fail(f"dropped edge {a} -> {b}: no R-RC-1 note on {a}")
    return ra, rb, serial_open


# --------------------------------------------------------------------------------------------------
# (e), (f)
# --------------------------------------------------------------------------------------------------
def screen_item(c: Ctx, iid: str) -> bool:
    if iid == SUP:
        return True
    it = c.items[iid]
    return "make e2e" in it.body.split("- **Gates:**")[-1]


def check_e(c: Ctx) -> Result:
    r = Result("(e) batches 1-4 items and <=75 min; <=5 lanes; lane ids, worktrees and merge order; lane box")
    exc = c.plan["parameters"].get("lane_box_exceptions", {})
    sprint_text = SPRINT.read_text(encoding="utf-8")
    for lv in c.plan["levels"]:
        lanes = lv["lanes"]
        if len(lanes) > MAX_LANES:
            r.fail(f"{lv['id']} has {len(lanes)} lanes")
        ids = [ln["id"] for ln in lanes]
        if lv["merge_order"] != ids or len(set(ids)) != len(ids):
            r.fail(f"{lv['id']} merge order {lv['merge_order']} differs from lane order {ids}")
        for n, ln in enumerate(lanes, 1):
            if ln["id"] != f"{lv['id']}-{n}" or ln.get("worktree") != f"~/dev/erev-wt/l{n}":
                r.fail(f"{ln['id']}: id or worktree {ln.get('worktree')} does not follow merge position {n}")
            for k, b in enumerate(ln["batches"], 1):
                if b["id"] != f"{ln['id']}-B{k}":
                    r.fail(f"batch id {b['id']} out of order")
                if not 1 <= len(b["items"]) <= 4:
                    r.fail(f"{b['id']} holds {len(b['items'])} items")
                if b["minutes"] > BATCH_BOX:
                    r.fail(f"{b['id']} {b['minutes']} min above {BATCH_BOX}")
            if ln["minutes"] > LANE_BOX:
                if exc.get(ln["id"]) == ln["minutes"] and "fallback" in sprint_text.lower():
                    r.notes.append(f"declared lane-box exception: {ln['id']} {ln['minutes']} min, with a fallback")
                else:
                    r.fail(f"{ln['id']} {ln['minutes']} min above the {LANE_BOX}-minute lane box")
        mig = [ln["id"] for ln in lanes if ln["adds_migrations"]]
        if mig and ids[:len(mig)] != mig:
            r.fail(f"{lv['id']}: migration lanes {mig} do not merge first")
        scr = [any(screen_item(c, i) for b in ln["batches"] for i in b["items"]) for ln in lanes]
        if True in scr and False in scr[scr.index(True):]:
            late = [ids[j] for j in range(scr.index(True), len(ids)) if not scr[j]]
            r.fail(f"{lv['id']}: lanes without screens {late} merge after a lane with screens")
    return r


def check_f(c: Ctx) -> Result:
    r = Result("(f) every in-scope item exactly once; done, in scope and deferred partition the items")
    s_in = set(c.in_scope)
    sched = c.scheduled()
    real = [i for i in sched if i != SUP]
    if len(c.in_scope) != len(s_in):
        r.fail("in_scope holds duplicates")
    if set(c.plan["done"]) != c.done:
        r.fail(f"done differs from git log: {sorted(c.done ^ set(c.plan['done']))}")
    if sorted(c.plan["l1_assumed"]) != sorted(c.l1):
        r.fail("l1_assumed differs from plan.json L1")
    for a, b, name in ((s_in, c.deferred, "in_scope/deferred"), (s_in, c.done, "in_scope/done"),
                       (c.deferred, c.done, "deferred/done")):
        if a & b:
            r.fail(f"overlap {name}: {sorted(a & b)}")
    if set(c.items) != s_in | c.deferred | c.done:
        r.fail(f"partition gap: {sorted(set(c.items) ^ (s_in | c.deferred | c.done))[:10]}")
    for iid in c.in_scope:
        if len(c.pos.get(iid, [])) != 1:
            r.fail(f"{iid} scheduled {len(c.pos.get(iid, []))} times (L1 included)")
    if set(real) - s_in:
        r.fail(f"scheduled but not in scope: {sorted(set(real) - s_in)}")
    if sched.count(SUP) != 1:
        r.fail(f"{SUP} scheduled {sched.count(SUP)} times")
    if s_in != set(c.v0["in_scope"]) - c.moved:
        r.fail("in_scope is not the V-0 scope less the D-82 moved items")
    sc = c.plan["scope_counts"]
    if (sc["in_scope"], sc["l1_assumed"], sc["scheduled_l2_onward"], sc["deferred"], sc["done"]) != \
            (len(s_in), len(c.l1), len(real), len(c.deferred), len(c.done)):
        r.fail(f"scope_counts {sc} disagree with the lists")
    r.notes.append(f"{len(s_in)} in scope = {len(c.l1)} L1 + {len(real)} L2 onward; {len(c.deferred)} deferred; "
                   f"{len(c.done)} done; {len(c.items)} items")
    return r


# --------------------------------------------------------------------------------------------------
# (c)
# --------------------------------------------------------------------------------------------------
D81_SCOPE = {"legacy template imports": ["DIN-4", "DIN-5", "DIN-6"],
             "journal runs and CSV export": ["CLO-8", "CLO-11", "CLO-13"],
             "waterfall, balance rollforward and RPO reports": ["RPS-3", "RPS-4", "EDS-2", "EDS-3"],
             "container images and compose": ["DEP-1", "DEP-2"]}


def forced_prerequisites() -> set[str]:
    text = vp.SPRINT.read_text(encoding="utf-8")
    m = re.search(r"### 3\.1 Forced prerequisites beyond the brief's list\n(.*?)\n### ", text, re.S)
    out: set[str] = set()
    for row in (m.group(1).splitlines() if m else []):
        cells = [x.strip() for x in row.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("Cause", "---"):
            continue
        cell = re.sub(r"\([^)]*\)", "", cells[1])
        for a, lo, hi in re.findall(r"([A-Z]{3})-(\d+) to [A-Z]{3}-(\d+)", cell):
            out |= {f"{a}-{n}" for n in range(int(lo), int(hi) + 1)}
        out |= set(vp.ID_RE.findall(cell))
    return out


def check_c(c: Ctx) -> Result:
    r = Result("(c) MVP capabilities of SPRINT-1.0rc.md §1 and §3 covered; forced prerequisites; J-01 fallback")
    s_in, have = set(c.in_scope), set(c.in_scope) | c.done
    excl, dnotes = c.plan.get("root_exclusions", {}), c.plan.get("deferred_notes", {})
    for cap, spec in vp.CAPABILITIES.items():
        for iid in spec.get("required", []):
            if iid not in have:
                r.fail(f"{cap}: {iid} not in scope")
        opt = spec.get("optional", [])
        ins = [i for i in opt if i in s_in]
        for i in opt:
            if i not in have and i not in excl and not dnotes.get(i):
                r.fail(f"{cap}: optional {i} excluded without a reason")
        if len(ins) < spec.get("min_optional_in_scope", 0):
            r.fail(f"{cap}: fewer than {spec['min_optional_in_scope']} optional items in scope")
        if spec.get("fallback"):
            sup = [x for x in c.plan.get("supervisor_items", []) if x["id"] == spec["fallback"]]
            last = c.plan["levels"][-1]["id"]
            if not sup or sup[0]["level"] != last or f"L{c.pos.get(SUP, [(0,)])[0][0]}" != last:
                r.fail(f"{cap}: fallback {spec['fallback']} is not scheduled in the last level {last}")
    for name, ids in D81_SCOPE.items():
        for iid in ids:
            if iid not in have:
                r.fail(f"D-81 scope '{name}': {iid} not in scope")
    forced = forced_prerequisites()
    for iid in sorted(forced - have - c.moved):
        r.fail(f"SPRINT-1.0rc.md §3.1 forced prerequisite {iid} neither in scope nor moved by R-RC-1")
    r.notes.append(f"§3.1 forced prerequisites: {len(forced & s_in)} in scope, {len(forced & c.moved)} moved by R-RC-1")
    for iid in ("GPB-4", "AKS-8", "RPS-23", "RPS-24"):
        if iid not in c.deferred or iid not in excl:
            r.fail(f"§3.2 excluded root {iid} not deferred with a recorded reason")
    moved_listed = {x["item"] for x in c.plan.get("moved_to_post_rc", [])}
    for iid in sorted(c.moved):
        if iid not in dnotes or iid not in moved_listed:
            r.fail(f"moved item {iid} lacks a deferred note or moved_to_post_rc entry")
    e2e = json.dumps(c.plan["release_gate"].get("e2e", {}))
    for (iid, dep), frag in PARTIAL.items():
        if dep not in e2e or iid not in e2e:
            r.fail(f"release gate e2e does not list the partial fragment {iid} on {dep} ({frag})")
    return r


# --------------------------------------------------------------------------------------------------
# (d)
# --------------------------------------------------------------------------------------------------
def lane_items(ln: dict) -> list[str]:
    return [i for b in ln["batches"] for i in b["items"]]


def check_d(c: Ctx) -> Result:
    r = Result("(d) <=2 migration lanes, re-parenting order, no edge between them; overlaps only on §4.3 or V-A files")
    mig = vp.migration_items(c.items)
    rules = vp.merge_rule_files()
    correction = set(tools_literal("CORRECTION_ITEMS"))
    sprint = SPRINT.read_text(encoding="utf-8")
    sec53 = re.search(r"### 5\.3 .*?\n(.*?)\n### ", sprint, re.S)
    for f in sorted(VA_FILES | {vp.MIGRATION_DIR}):
        if not sec53 or f.split("backend/")[-1] not in sec53.group(1):
            r.fail(f"SPRINT-vabc.md §5.3 has no rule for {f}")
    sched = set(c.scheduled())
    for lv in c.plan["levels"]:
        touch, mig_lanes = {}, []
        for ln in lv["lanes"]:
            ids = lane_items(ln)
            lm = [i for i in ids if i in mig]
            if bool(lm) != bool(ln["adds_migrations"]):
                r.fail(f"{ln['id']} adds_migrations={ln['adds_migrations']} but migration items {lm}")
            if lm:
                mig_lanes.append(ln["id"])
            t: set[str] = set()
            for i in ids:
                if i == SUP:
                    t |= {"frontend/e2e/journeys/rc-smoke.journey.ts", "frontend/e2e/projects/avenmoor-serial.spec.ts"}
                    continue
                t |= vp.item_touch(c.items, i)
                if i in correction:
                    t.add(CORRECTION_SCOPE)
            touch[ln["id"]] = t
        if len(mig_lanes) > MAX_MIG_LANES:
            r.fail(f"{lv['id']}: {len(mig_lanes)} migration lanes {mig_lanes}")
        if len(mig_lanes) == 2:
            a, b = mig_lanes
            lb = next(ln for ln in lv["lanes"] if ln["id"] == b)
            if lv["merge_order"][:2] != [a, b] or lb.get("reparented_onto") != a:
                r.fail(f"{lv['id']}: {b} must merge second and be re-parented onto {a}")
            ia, ib = set(lane_items(lv["lanes"][0])), set(lane_items(lb))
            for x in ia | ib:
                for dep in c.pairs(x):
                    if (x in ia and dep in ib) or (x in ib and dep in ia):
                        r.fail(f"{lv['id']}: edge {x} -> {dep} joins the two migration lanes")
            if not any(g.startswith(REPARENT_GATE) for g in lv["merge_gates"]):
                r.fail(f"{lv['id']}: no re-parenting test-pg gate")
            r.notes.append(f"V-A {lv['id']}: {b} re-parented onto {a}")
        ids_l = [ln["id"] for ln in lv["lanes"]]
        for i in range(len(ids_l)):
            for j in range(i + 1, len(ids_l)):
                both_mig = ids_l[i] in mig_lanes and ids_l[j] in mig_lanes
                corr_pair = CORRECTION_SCOPE in touch[ids_l[i]] or CORRECTION_SCOPE in touch[ids_l[j]]
                for f in sorted(vp.overlaps(touch[ids_l[i]], touch[ids_l[j]])):
                    tag = f"{lv['id']} {ids_l[i]} x {ids_l[j]}: {f}"
                    if f in vp.SHARED_NON_MERGEABLE:
                        r.fail(tag + " (non-mergeable)")
                    elif f.startswith(vp.MIGRATION_DIR) or f in VA_FILES:
                        (r.notes.append(tag + " (V-A pair)") if both_mig else r.fail(tag + " (V-A file outside the pair)"))
                    elif corr_pair and f.startswith(CORRECTION_SCOPE):
                        r.fail(tag + " (correction scope)")
                    elif f in rules:
                        r.notes.append(tag + " (§4.3 rule)")
                    else:
                        r.fail(tag + " (no merge rule)")
    so = [i for i in vp.schema_only_items(c.items, mig) if i in sched]
    if so:
        r.fail(f"scheduled items with a Schema change and no revision path: {so}")
    return r


# --------------------------------------------------------------------------------------------------
# (g)
# --------------------------------------------------------------------------------------------------
def key_sets(c: Ctx) -> tuple[set[str], dict[str, list[str]], set[str]]:
    active, blocked = set(), {}
    for f in sorted(vp.KEYS_DIR.rglob("*.yaml")):
        if f.parent.name.startswith("_"):
            continue
        t = f.read_text(encoding="utf-8")
        st = re.search(r'^status:\s*"?(\w+)"?', t, re.M)
        if not st or st.group(1) != "active":
            continue
        kid = re.search(r'^id:\s*"?([^"\n]+)"?', t, re.M).group(1).strip()
        runner = re.search(r'^runner:\s*"?(\w+)"?', t, re.M)
        values = set(re.findall(r'recognition_method:\s*"?([A-Z_]+)"?', t)) | \
            set(re.findall(r'event_type:\s*"?([A-Z_]+)"?', t))
        by = {vp.KEY_BLOCKERS[v] for v in values if v in vp.KEY_BLOCKERS and vp.KEY_BLOCKERS[v] in c.deferred}
        if runner and runner.group(1) != "engine" and "PRP-1" in c.deferred:
            by.add("PRP-1")
        for measure, owner in MEASURE_BLOCKERS.items():
            if owner in c.deferred and re.search(r"measure:\s*\"?" + measure + r"\b", t):
                by.add(owner)
        active.add(kid)
        if by:
            blocked[kid] = sorted(by)
    return active, blocked, active - set(blocked)


def named(it: vp.Item, what: str) -> set[str]:
    acc = it.accept
    if what == "keys":
        ids = set()
        for m in re.findall(r"make answer-keys ID=([A-Za-z0-9,\-]+)", acc):
            ids |= set(m.split(","))
        ids |= set(re.findall(r"answer-keys/[a-z0-9_]+/([A-Z0-9][A-Za-z0-9\-]+)\.yaml", acc))
        return ids
    if what == "props":
        line = next((ln for ln in acc.splitlines() if ln.strip().startswith("- Properties:")), "")
        body = line.split(":", 1)[-1].strip()
        return set() if body.lower().startswith("none") else {f"p{int(n):02d}" for n in re.findall(r"PROP:P(\d+)", body)}
    line = next((ln for ln in acc.splitlines() if ln.strip().startswith("- Golden:")), "")
    body = line.split(":", 1)[-1].strip()
    if body.lower().startswith("none"):
        return set()
    sels = set(re.findall(r'make parity K=("[^"]+"|[^`\s"]+)', body))
    if any(x.startswith('"<') for x in sels):   # "<the 13-case selection above>": the selection of the Tests line
        sels = set(re.findall(r'make parity K=("[^"<][^"]*")', acc))
    return sels


def check_g(c: Ctx) -> Result:
    r = Result("(g) minutes, level estimates and cumulative hours; merge gates; release key list")
    mins = {k: v[1] for k, v in vp.scope_minutes().items()}
    mins[SUP] = 70
    active, blocked, runnable = key_sets(c)
    cum, merged, web11 = L1_MINUTES, list(c.l1), False
    for lv in c.plan["levels"]:
        ids = [i for ln in lv["lanes"] for i in lane_items(ln)]
        merged += ids
        web11 = web11 or "WEB-11" in merged
        for ln in lv["lanes"]:
            for b in ln["batches"]:
                if b["minutes"] != sum(mins.get(i, -999) for i in b["items"]):
                    r.fail(f"{b['id']} minutes {b['minutes']} != cost model {sum(mins.get(i, -999) for i in b['items'])}")
            if ln["minutes"] != sum(b["minutes"] for b in ln["batches"]):
                r.fail(f"{ln['id']} minutes != sum of batches")
        screens = web11 and any(screen_item(c, i) for i in ids)
        iam_items = {x["item"] for x in c.iam.values() if x["level"] == lv["id"]}
        reparent = sum(1 for ln in lv["lanes"] if ln["adds_migrations"]) == 2
        est = max(ln["minutes"] for ln in lv["lanes"]) + MERGE + MERGE_E2E * screens + IAM_MIN * len(iam_items) + \
            REPARENT_MIN * reparent
        cum += est
        if lv["estimate_minutes"] != est or lv["cumulative_hours"] != round(cum / 60, 1):
            r.fail(f"{lv['id']}: estimate {lv['estimate_minutes']} / {lv['cumulative_hours']} h, expected {est} / "
                   f"{round(cum / 60, 1)} h")
        gates = lv["merge_gates"]
        for g in ("make ci", "make test-pg", "git status --porcelain"):
            if not any(x.startswith(g) for x in gates):
                r.fail(f"{lv['id']}: gate {g} missing")
        if screens != any(x == SCREENS_E2E for x in gates):
            r.fail(f"{lv['id']}: screens e2e gate {'missing' if screens else 'without screen items'}")
        if (SUP in ids) != any(x.startswith(SMOKE_E2E) for x in gates):
            r.fail(f"{lv['id']}: smoke e2e gate does not match the supervisor item")
        real = [i for i in merged if i in c.items]
        want_keys = set().union(*(named(c.items[i], "keys") for i in real)) & runnable
        kg = next((x for x in gates if x.startswith("make answer-keys ID=")), None)
        got = set(kg.split("ID=", 1)[1].split()[0].split(",")) if kg else set()
        if '"' in (kg or ""):
            r.fail(f"{lv['id']}: quoted key ids in the answer-keys gate")
        if got - runnable:
            r.fail(f"{lv['id']}: answer-keys gate selects blocked or unknown keys {sorted(got - runnable)[:6]}")
        if want_keys - got:
            r.fail(f"{lv['id']}: answer-keys gate misses runnable named keys {sorted(want_keys - got)[:6]}")
        want_props = set().union(*(named(c.items[i], "props") for i in real))
        pg = next((x for x in gates if x.startswith("make properties K=")), "")
        if want_props - set(re.findall(r"p\d\d", pg)):
            r.fail(f"{lv['id']}: properties gate misses {sorted(want_props - set(re.findall(r'p\d\d', pg)))}")
        par = next((x for x in gates if x.startswith("make parity K=")), "")
        want_par = {sel.strip('"') for i in real for sel in named(c.items[i], "golden")}
        k = par.split("K=", 1)[1].strip().strip('"') if par else ""
        groups = set(re.findall(r"\(((?:[^()]|\([^()]*\))*)\)", k))
        if want_par - groups:
            r.fail(f"{lv['id']}: parity gate misses selections {[x[:50] for x in sorted(want_par - groups)]}")
        if groups - want_par:
            r.fail(f"{lv['id']}: parity gate selects cases no merged item names {[x[:50] for x in sorted(groups - want_par)]}")
        if not want_par and par:
            r.fail(f"{lv['id']}: parity gate without merged GPA or GPB items")
    if c.plan["estimate_hours"] != round(cum / 60, 1):
        r.fail(f"estimate_hours {c.plan['estimate_hours']} != {round(cum / 60, 1)}")
    rel = c.plan["release_gate"]["answer_keys"]
    ids = set(rel["runnable_engine_runner_ids"])
    if ids != runnable or rel["count"] != len(runnable):
        r.fail(f"release keys: plan {len(ids)}, validator {len(runnable)}; only plan {sorted(ids - runnable)[:5]}, "
               f"only validator {sorted(runnable - ids)[:5]}")
    r.notes.append(f"{len(active)} active keys, {len(runnable)} runnable, {len(blocked)} blocked; estimate {round(cum / 60, 1)} h")
    return r


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------
ACCEPTED_PREFIXES = ("contract ", "partial ", "V-A ", "declared", "integration note")


def run(c: Ctx):
    ra, rb, serial_open = check_ab(c)
    return [check_f(c), check_e(c), ra, rb, check_c(c), check_d(c), check_g(c)], serial_open


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    c = Ctx()
    if cmd == "edges":
        for iid in argv[2:]:
            print(iid, c.pos.get(iid))
            for dep, es in sorted(c.pairs(iid).items()):
                st = "done" if dep in c.done else "L1" if dep in c.l1 else "DEFERRED" if dep in c.deferred else str(c.pos.get(dep))
                print(f"   -> {dep:8} {st:26} {sorted({(e.source, e.kind) for e in es})} {es[0].reason[:90]}")
        return 0
    results, serial_open = run(c)
    if cmd == "serial":
        for x in serial_open:
            print(x)
        return 0
    if cmd == "record":
        c.plan["validation"] = {
            "validator": "validate-vabc (independent validator)",
            "script": "python3 -B docs/build-spec/sprint/validate_vabc.py check",
            "run_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "build_spec_sha256": hashlib.sha256(vp.SPEC.read_bytes()).hexdigest(),
            "checks": [{"name": x.name, "ok": x.ok, "failures": x.failures,
                        "waived": [n for n in x.notes if n.startswith(ACCEPTED_PREFIXES)]} for x in results],
            "serial_edges_not_satisfied_by_position": len(serial_open),
            "verified_edges": [{"item": a, "dependency": b, "evidence": w} for a, b, w in VABC_VERIFIED],
            "partial_fragments": [{"item": a, "waits_for": b, "fragment": f} for (a, b), f in PARTIAL.items()],
            "note": "independent validation; the planner self-check of evaluate.py is superseded",
        }
        PLAN.write_text(json.dumps(c.plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = True
    for x in results:
        print(("PASS " if x.ok else "FAIL ") + x.name)
        for f in x.failures:
            print("   x " + f)
        if "-v" in argv:
            for n in x.notes:
                print("   . " + n)
        ok &= x.ok
    print(f"loop-order edges not satisfied by position: {len(serial_open)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
