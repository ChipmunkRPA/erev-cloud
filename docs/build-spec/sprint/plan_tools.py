#!/usr/bin/env python3
"""eRev Cloud 1.0-rc sprint planner: BUILD_SPEC parser, scope closure, lane scheduler and plan checks.

Run from anywhere (standard library only; reads the repository and runs `git log` read-only; writes
only docs/build-spec/sprint/plan.json and .scratch/sprint-plan/*):

    python3 docs/build-spec/sprint/plan_tools.py all        # parse, closure, keys, schedule, variants, check, emit
    python3 docs/build-spec/sprint/plan_tools.py closure    # scope closure with the reasons each item is in scope
    python3 docs/build-spec/sprint/plan_tools.py keys       # answer-key support given the in-scope engine items
    python3 docs/build-spec/sprint/plan_tools.py check      # validate docs/build-spec/sprint/plan.json as written
    python3 docs/build-spec/sprint/plan_tools.py tables     # markdown tables to .scratch/sprint-plan/tables.md

Method (SPRINT-1.0rc.md section 2):
- The BUILD_SPEC "Prerequisites" field is the serial loop order (each item names its predecessor and the
  first item of a phase names the previous GATE), so its closure from late items is almost the whole
  document. `declared_closure` reports that number and scope does not use it.
- Scope uses technical edges: explicit non-predecessor ids in Prerequisites, file producers (the first
  item listing a path creates it), directory producers, fixture producers (worlds, golden streams,
  parity support), first producers of bound API-R rows and of created 04 tables, and MANUAL_EDGES
  verified by reading the items (engine state-type chain, registrations, bindings, seeds, captures,
  named tests and answer keys). IGNORED_AUTO_EDGES lists rejected auto edges with reasons.
- Edge kinds: "hard" (merged in an earlier level, or earlier in the same lane) and "contract" (code against
  the ENGINE_SPEC state contract; may sit in another lane of the same level; flagged integration-after-merge).
- The scheduler packs levels of at most MAX_LANES lanes, one migration lane per level, near-disjoint file
  scopes (HOTSPOTS excepted, each with a merge rule), batches of 1 to 4 items of at most BATCH_BOX minutes.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "BUILD_SPEC.md"
KEYS_DIR = ROOT / "docs" / "accounting" / "answer-keys"
OUT_DIR = ROOT / "docs" / "build-spec" / "sprint"
PLAN_JSON = OUT_DIR / "plan.json"
SCRATCH = ROOT / ".scratch" / "sprint-plan"

# --------------------------------------------------------------------------------------------------
# Planning parameters (minutes of agent work, gates included)
# --------------------------------------------------------------------------------------------------
LEVEL_BOX = 240  # lane work per level before the merge step
BATCH_BOX = 75  # SZ-01 upper bound per batch
BATCH_MAX_ITEMS = 4
MAX_LANES = 5
MAX_MIGRATION_LANES = 1  # supervisor rule; variant V-A evaluates 2 with revision re-parenting at merge
MERGE_MIN = 35  # sequential merges, openapi regeneration, make ci, make test-pg, selections
MERGE_MIN_E2E = 25  # extra when screen items merged (make e2e screens.spec.ts with seeding)
HORIZON_MIN = 570  # "about 9 hours": level boundaries reached by 9.5 h of wall-clock

COST = {
    "engine": 30, "aks": 60, "parity": 45, "deploy": 25, "journey": 70, "migration": 40, "seed": 50,
    "screen": 55, "frontend": 40, "backend": 35, "gate": 30,
}
COST_OVERRIDES = {
    "WEB-11": 70, "END-9": 45, "ENA-13": 40, "ENB-13": 40, "GPA-1": 60, "CTR-2": 50, "CTR-3": 45,
    "CTR-20": 60, "CLO-22": 60, "RFD-16": 60, "RPS-2": 45, "CLO-19": 45, "CLO-20": 50,
}

ENGINE_PHASES = {"EKC", "ENA", "ENB", "ENC", "END", "EDS"}
DONE_FALLBACK_PHASES = {"FND": 18, "EKC": 12, "PLF": 30}
IN_FLIGHT_TREATED_DONE = {"WEB-7"}

# GOAL capabilities (supervisor brief). Items listed here are the closure roots.
CAPABILITIES = {
    "C1": ("frontend shell, demo seed scaffold, e2e harness, sign-in, MFA, approvals",
           ["WEB-8", "WEB-10", "WEB-11", "WEB-12", "WEB-15"]),
    "C2": ("engine stages 01 to 15 needed for legacy parity and SaaS basics",
           [f"ENA-{i}" for i in range(1, 14)]
           + ["ENB-1", "ENB-2", "ENB-3", "ENB-6", "ENB-7", "ENB-8", "ENB-11", "ENB-13"]
           + ["ENC-1", "ENC-2", "ENC-3", "ENC-4", "ENC-7", "ENC-10", "ENC-11", "ENC-12", "ENC-13", "ENC-14"]
           + [f"END-{i}" for i in range(4, 11)] + ["EDS-1", "EDS-2", "EDS-3"]),
    "C3": ("golden parity and answer-key sweeps",
           [f"GPA-{i}" for i in range(1, 7)] + ["GPB-1", "GPB-2", "GPB-4"] + [f"AKS-{i}" for i in range(1, 9)]),
    "C4": ("reference data backend",
           ["RFD-1", "RFD-2", "RFD-3", "RFD-6", "RFD-7", "RFD-8", "RFD-9", "RFD-10", "RFD-11", "RFD-12", "RFD-13",
            "RFD-14", "RFD-16"]),
    "C5": ("contracts backend", ["CTR-1", "CTR-2", "CTR-3", "CTR-4", "CTR-5", "CTR-15", "CTR-19", "CTR-20"]),
    "C6": ("data in", ["DIN-1", "DIN-2", "DIN-3", "DIN-4", "DIN-5", "DIN-6", "DIN-11"]),
    "C7": ("close and journals", ["CLO-1", "CLO-2", "CLO-3", "CLO-8", "CLO-9", "CLO-11", "CLO-13"]),
    "C8": ("reports", ["RPS-1", "RPS-2", "RPS-3", "RPS-4", "RPS-5"]),
    "C9": ("MVP screens", ["CTR-21", "CTR-22", "CTR-23", "CTR-26", "DIN-15", "DIN-16", "DIN-17", "RPS-6", "RPS-7",
                           "CLO-23", "CLO-26", "RPS-22", "RFD-24"]),
    "C10": ("flagship journey J-01", ["RPS-23", "RPS-24"]),
    "C11": ("deploy images and compose", ["DEP-1", "DEP-2"]),
}
MVP_ROOTS: dict[str, str] = {}
for _cap, (_name, _ids) in CAPABILITIES.items():
    for _id in _ids:
        MVP_ROOTS.setdefault(_id, f"{_cap} {_name}")

# Roots named by the brief that do not fit, with the reason (the brief allows it).
ROOT_EXCLUSIONS = {
    "GPB-4": "C3: full G3 needs GPB-3 point_in_time_equivalence, which replays into a sandbox through LMG-4 and "
             "SNP-1 to SNP-3 (deferred); 121 of 122 cases are the rc selection",
    "AKS-8": "C3: the 221-key sweep cannot pass while ENC-5, ENC-6 and ENC-8 are deferred",
    "RPS-23": "C10: J-01 part 1 needs WEB-13, WEB-19, RFD-18, RFD-23 and the fresh-tenant invitation flow; "
              "replaced tonight by the proposed SUP-RC-SMOKE journey",
    "RPS-24": "C10: J-01 part 2 needs RPS-21 and DIN-18 and the QuickBooks Online realm of CLO-15; replaced "
              "tonight by SUP-RC-SMOKE",
}

# Files many items edit by design. They create no producer edge; cross-lane edits are allowed and resolved at
# merge by the rule given (SPRINT-1.0rc.md section 5.3).
HOTSPOTS = {
    "docs/api/openapi.json": "regenerate with make openapi on main after the last lane merges; never hand-merge",
    "frontend/src/lib/api/schema.d.ts": "regenerate with make openapi on main; never hand-merge",
    "frontend/src/app/router.tsx": "union of route objects; keep SCREENS §0.4 route order",
    "frontend/src/messages/en.json": "JSON key union by namespace; screen items never share keys",
    "frontend/e2e/projects/screens.spec.ts": "union of test blocks; keep capture order per BS-D-09",
    "frontend/src/routes/settings/index.tsx": "union of built-page links (SCR-IA-03)",
    "backend/erev_api/api/router.py": "union of ROUTERS entries (implicit edit for every new api/v1 module)",
    "backend/erev_api/db/tables/__init__.py": "union of imports (implicit edit for every new table module)",
    "backend/erev_engine/stages/__init__.py": "union of STAGES and BOUNDARY_HANDLERS entries in Table 0.2-A order",
    "backend/tests/engine/kernel/test_stage_registry.py": "union of PENDING_STAGES removals",
    "backend/tests/architecture/test_registries_complete.py": "union of PENDING_ tuple removals (BS-D-07)",
    "backend/erev_api/approvals/subjects.py": "union of SUBJECTS entries",
    "backend/tests/support/rows.py": "union of ROW_BUILDERS entries",
    "backend/tests/pg/test_db_invariants.py": "union of test functions",
    "backend/tests/pg/test_rls_isolation.py": "union of parametrised tables",
    "backend/tests/pg/test_immutability_and_grants.py": "union of test functions",
    "backend/erev_api/domain/platform/provisioning.py": "union of provisioning rows in 04 §14.3 order",
    "backend/erev_api/db/transitions.py": "union of TRANSITIONS entries",
    "backend/erev_api/domain/demo/builders.py": "union of builder registrations in WLD order",
    "backend/erev_api/domain/demo/__init__.py": "union of builder order entries",
    "backend/erev_api/cli.py": "union of Typer commands",
    "Makefile": "union of targets and .PHONY entries",
    "backend/tests/unit/test_makefile_targets.py": "union of target cases",
    "docs/guides/user-guide.md": "union of sections",
    "docs/guides/runbook.md": "union of RB sections",
    "backend/tests/support/fold.py": "union of fold helpers",
    "backend/tests/properties/test_prop_p01_allocation_sum.py": "union of stage-level and compute-level tests",
    "PROGRESS.md": "lanes never edit; the merge step appends the ticks in merge order",
}
IMPLICIT_ROUTER = "backend/erev_api/api/router.py"
IMPLICIT_TABLES = "backend/erev_api/db/tables/__init__.py"
MIGRATION_OVERRIDES = {"RFD-13": True}  # adds DB-04 and DB-05 triggers to the RFD-12 tables without naming the file
CORRECTION_SCOPE = "backend/erev_engine/stages/"
CORRECTION_ITEMS = {"AKS-1", "AKS-2", "AKS-3", "AKS-4", "AKS-5", "AKS-6", "AKS-7", "GPA-2", "GPA-3", "GPA-4", "GPA-5",
                    "GPB-2"}

# --------------------------------------------------------------------------------------------------
# Verified technical edges (item, dependency, kind, reason)
# --------------------------------------------------------------------------------------------------
MANUAL_EDGES: list[tuple[str, str, str, str]] = [
    # Engine: folds, registrations and the linear state-type chain (ENGINE_SPEC_B §0.2 table; S14-R-10)
    ("ENA-13", "ENA-5", "hard", "inception fold calls stages 01 to 03 (CV-10)"),
    ("ENA-13", "ENA-9", "hard", "inception fold calls stage 04"),
    ("ENA-13", "ENA-12", "hard", "inception fold calls stage 05; registers stages 02 to 05"),
    ("ENA-6", "ENA-3", "contract", "s04 consumes the PobState type of s03 (Table 0.2-A)"),
    ("ENA-10", "ENA-6", "contract", "s05 consumes the PricedState type of s04"),
    ("ENB-13", "ENA-13", "hard", "fold_book extends backend/tests/support/fold.py"),
    ("ENB-13", "ENB-1", "hard", "boundary fold test replays golden_streams"),
    ("ENB-13", "ENB-4", "hard", "BOUNDARY_HANDLERS complete for Table 0.3-A: CONTRACT_TERMINATED"),
    ("ENB-13", "ENB-5", "hard", "BOUNDARY_HANDLERS: MATERIAL_RIGHT_EXERCISED, LINE_ATTRIBUTES_CHANGED, REGROUPED"),
    ("ENB-13", "ENB-8", "hard", "legacy templates folded through step 09 of golden contract 2"),
    ("ENB-13", "ENB-9", "hard", "BOUNDARY_HANDLERS: OPENING_BALANCE_ESTABLISHED; stage 07 in STAGES"),
    ("ENB-13", "ENB-10", "hard", "BOUNDARY_HANDLERS: ESTIMATE_CHANGED; stage 08 in STAGES"),
    ("ENB-13", "ENB-11", "hard", "stage 08 late events registered"),
    ("ENB-13", "ENB-12", "hard", "stage 08 exports complete before registration"),
    ("ENC-4", "ENB-1", "hard", "golden delivery tests read backend/tests/support/golden_streams.py"),
    ("ENC-10", "ENC-2", "hard", "stage 09 registration after time-elapsed conventions"),
    ("ENC-10", "ENC-3", "hard", "stage 09 registration after output measures"),
    ("ENC-10", "ENC-4", "hard", "stage 09 registration after units measures"),
    ("ENC-10", "ENC-7", "hard", "stage 09 registration after returns"),
    ("ENC-10", "ENC-9", "hard", "schedule versioning over manual release, holds and cause decomposition"),
    ("ENC-11", "ENC-10", "contract", "s10 consumes the RecognitionState type of s09"),
    ("ENC-14", "ENC-12", "hard", "stage 10 registration after position and refund liabilities"),
    ("ENC-15", "ENC-11", "contract", "s11 consumes the BalanceState type of s10"),
    ("END-1", "ENC-15", "contract", "s12 consumes the CostLossState type of s11"),
    ("END-3", "END-2", "hard", "stage 12 registration after remeasurement"),
    ("END-4", "END-1", "contract", "s14 consumes FxState; S14-R-10 functional amounts come from stage 12"),
    ("END-5", "ENB-11", "contract", "assign.py calls s08 assign_posting_period (ENGINE_SPEC_B §0.4)"),
    ("END-6", "END-5", "hard", "stage 14 registration after role targets and deltas"),
    ("END-7", "ENA-13", "hard", "book loop runs registered stages 02 to 05"),
    ("END-7", "ENB-13", "hard", "book loop runs registered stages 06 to 08"),
    ("END-7", "ENC-10", "hard", "book loop runs stage 09"),
    ("END-7", "ENC-14", "hard", "book loop runs stage 10"),
    ("END-7", "ENC-16", "hard", "book loop runs stage 11"),
    ("END-7", "END-3", "hard", "book loop runs stage 12"),
    ("END-7", "END-6", "hard", "book loop runs stage 14"),
    ("END-9", "END-8", "hard", "compute orchestrates fold_book and the LEGACY book"),
    ("END-10", "END-9", "hard", "delta posting end to end through compute"),
    ("EDS-1", "END-9", "hard", "EDS-1 registers stage 15 and compute runs it"),
    ("EDS-1", "END-6", "contract", "s15 consumes the PostingState type of s14"),
    ("EDS-3", "EDS-2", "hard", "rollforward shares the waterfall measures"),
    ("EDS-4", "ENB-12", "hard", "prior-period revenue sums estimate.prior_period nodes (decompose_prior_period)"),
    ("EDS-4", "EDS-3", "hard", "stage 15 measures build on the rollforward"),
    ("EDS-5", "ENC-16", "hard", "cost rollforward over stage 11 cost assets (S11-INV-06)"),
    ("EDS-6", "EDS-4", "hard", "lock snapshot datasets include prior-period and disaggregation rows"),
    ("EDS-6", "EDS-5", "hard", "lock snapshot datasets include the cost rollforward"),
    # Answer-key sweeps: runner corrections land in the same stage files, so the sweeps stay serial
    ("AKS-1", "END-10", "hard", "engine-runner sweep over compute"),
    ("AKS-1", "EDS-1", "hard", "compute runs stage 15 during the sweep"),
    ("AKS-1", "RFD-13", "hard", "DG-AK-45 runners call erev_api.domain.ssp.range_validation.validate_ranges"),
    ("AKS-2", "AKS-1", "hard", "serial corrections in shared stage packages"),
    ("AKS-3", "AKS-2", "hard", "serial corrections in shared stage packages"),
    ("AKS-4", "AKS-3", "hard", "serial corrections in shared stage packages"),
    ("AKS-5", "AKS-4", "hard", "serial corrections in shared stage packages"),
    ("AKS-6", "AKS-5", "hard", "serial corrections in shared stage packages"),
    ("AKS-7", "AKS-6", "hard", "serial corrections in shared stage packages"),
    # Golden parity
    ("GPA-1", "DIN-4", "hard", "steps 01 to 03 replay through the legacy v1 setup and SKU SSP templates (DG-PAR-04)"),
    ("GPA-1", "DIN-3", "hard", "upload, validate, dry-run diff, submit, approve and commit"),
    ("GPA-1", "RFD-11", "hard", "LEGACY_PARITY preset version published before step 01"),
    ("GPA-1", "END-10", "hard", "parity reads obligation_version trace nodes produced by compute"),
    ("GPA-2", "DIN-5", "hard", "steps 04 to 07 through the progress template"),
    ("GPA-2", "ENC-14", "hard", "contract positions and reclass from stage 10"),
    ("GPA-3", "DIN-6", "hard", "steps 08 and 09 through the modification template"),
    ("GPA-3", "ENB-6", "hard", "LEGACY_RETROSPECTIVE template"),
    ("GPA-3", "ENB-7", "hard", "LEGACY_POB_VC template"),
    ("GPA-4", "ENB-5", "hard", "GT-15 material-right exercise"),
    ("GPA-4", "ENB-8", "hard", "LEGACY_PROSPECTIVE template"),
    ("GPA-6", "GPA-5", "hard", "GATE-GPA selection of 94 cases"),
    ("GPA-6", "DIN-7", "hard", "probe P3 compares row-level finding messages (DG-PAR-11)"),
    ("GPB-1", "GPA-6", "hard", "probes.py journal expectations"),
    ("GPB-1", "RPS-5", "hard", "journal_entry_totals reads report legacy_je_summary"),
    ("GPB-1", "DIN-8", "hard", "probes P1 and P4: blank memo and duplicate upload findings"),
    # Reference data
    ("RFD-3", "RFD-2", "hard", "tenant_currency provisioning and entity functional currencies"),
    ("RFD-7", "RFD-5", "hard", "mapping versions use the SM-04 lifecycle (/test, /submit, /publish)"),
    ("RFD-7", "RFD-6", "hard", "mapping rules resolve gl_account"),
    ("RFD-9", "RFD-7", "hard", "adds foreign key account_mapping_rule.product_id → product"),
    ("RFD-10", "RFD-9", "hard", "adds foreign key product.default_pob_template_id"),
    ("RFD-10", "RFD-5", "hard", "template versions use the lifecycle"),
    ("RFD-10", "ENA-5", "hard", "run_test_cases calls s03_pob_builder.build_lines"),
    ("RFD-11", "RFD-5", "hard", "policy versions use the lifecycle"),
    ("RFD-11", "RFD-2", "hard", "policy scopes name entities and books"),
    ("RFD-12", "RFD-9", "hard", "ssp_entry references product"),
    ("RFD-12", "RFD-3", "hard", "entry currency references tenant currencies"),
    ("RFD-13", "RFD-5", "hard", "maker-checker publication through the lifecycle"),
    ("RFD-14", "RFD-13", "hard", "resolution loads APPROVED versions"),
    ("RFD-14", "ENA-10", "hard", "calls s05_allocation.resolve_ssp"),
    ("RFD-15", "RFD-12", "hard", "creates draft SSP book versions"),
    ("RFD-16", "WEB-10", "hard", "registers in erev seed demo"),
    ("RFD-16", "RFD-1", "hard", "seeds calendars"), ("RFD-16", "RFD-3", "hard", "seeds FX rate sets"),
    ("RFD-16", "RFD-5", "hard", "seeds APPROVAL_ROUTING and AUTO_APPROVAL rule sets"),
    ("RFD-16", "RFD-8", "hard", "seeds customers"), ("RFD-16", "RFD-10", "hard", "seeds published templates"),
    ("RFD-16", "RFD-11", "hard", "seeds the tenant policy version"),
    ("RFD-16", "RFD-13", "hard", "seeds approved SSP books"),
    ("RFD-19", "RFD-2", "hard", "context pill binds entities, periods and books"),
    ("RFD-19", "RFD-6", "hard", "chart-of-accounts screen binds API-R-20 and API-R-21"),
    ("RFD-19", "RFD-11", "hard", "workspace settings post registry versions"),
    ("RFD-19", "RFD-16", "hard", "captures the Avenmoor reference seed"),
    ("RFD-19", "WEB-12", "hard", "screens.spec personas sign in"),
    ("RFD-22", "RFD-10", "hard", "binds API-R-24 lists"), ("RFD-22", "RFD-5", "hard", "binds API-R-25 and API-R-57"),
    ("RFD-22", "RFD-16", "hard", "captures seeded rule sets"), ("RFD-22", "WEB-12", "hard", "screens.spec personas"),
    ("RFD-24", "RFD-13", "hard", "binds API-R-26 publication"),
    ("RFD-24", "RFD-15", "hard", "binds API-R-27 calculator runs"),
    ("RFD-24", "RFD-22", "hard", "the rail item Policies is listed from RFD-22 (SCR-IA-01)"),
    ("RFD-24", "RFD-16", "hard", "captures US-LIST 2026-H1 from the reference seed"),
    # Frontend foundation
    ("WEB-11", "WEB-10", "hard", "scripts/e2e.sh seeds the demo tenants and personas"),
    ("WEB-11", "WEB-8", "hard", "sign-in route in the router"),
    ("WEB-15", "WEB-12", "hard", "personas sign in through e2e fixtures"),
    ("WEB-17", "WEB-12", "hard", "screens.spec personas"),
    # Contracts
    ("CTR-1", "RFD-2", "hard", "contracting entity references"), ("CTR-1", "RFD-8", "hard", "customer references"),
    ("CTR-1", "RFD-9", "hard", "product references"),
    ("CTR-2", "END-10", "hard", "computation.persist stores compute output bundles (DG-CMD-10)"),
    ("CTR-2", "EDS-1", "hard", "contract_version.rpo_amount comes from stage 15"),
    ("CTR-2", "RFD-14", "hard", "bundles.build pins SSP versions"),
    ("CTR-2", "RFD-15", "hard", "committed-obligation provider in domain/ssp/calculator.py"),
    ("CTR-2", "RFD-11", "hard", "bundles pin policy versions"), ("CTR-2", "RFD-10", "hard", "bundles pin template versions"),
    ("CTR-2", "RFD-7", "hard", "bundles carry the 33 account roles (D-14a)"),
    ("CTR-3", "RFD-7", "hard", "postings resolve accounts (resolve_account)"),
    ("CTR-5", "CTR-4", "hard", "event routes read contracts"),
    ("CTR-7", "CTR-4", "hard", "judgements reference contracts"),
    ("CTR-8", "CTR-5", "hard", "combination suggestions over booked contracts"),
    ("CTR-9", "CTR-7", "hard", "STEP1_RECORD and JUDGEMENT_RECORDS checklist items"),
    ("CTR-9", "CTR-8", "hard", "COMBINATION_SUGGESTIONS checklist item"),
    ("CTR-9", "RFD-5", "hard", "approval routing and AUTO-CON-01 rule evaluation"),
    ("CTR-10", "CTR-4", "hard", "holds and memos on contracts"),
    ("CTR-10", "ENC-9", "hard", "holds consumed (ENGINE_SPEC_B §9.2.12)"),
    ("CTR-11", "CTR-3", "hard", "void posts reversal lines"),
    ("CTR-11", "CTR-9", "hard", "void applies to activated contracts"),
    ("CTR-12", "CTR-5", "hard", "estimate versions append ESTIMATE_CHANGED"),
    ("CTR-12", "ENB-10", "hard", "estimate reassessment consumed (§8.3)"),
    ("CTR-14", "CTR-3", "hard", "persists stage 11 and 12 outputs beside postings"),
    ("CTR-14", "ENC-16", "hard", "cost assets and loss provisions"), ("CTR-14", "END-2", "hard", "FX layer movements"),
    ("CTR-15", "CTR-4", "hard", "obligation reads"), ("CTR-15", "RFD-11", "hard", "policy overrides"),
    ("CTR-15", "RFD-14", "hard", "SSP override resolution"),
    ("CTR-17", "CTR-15", "hard", "modification objects on obligations"),
    ("CTR-17", "CTR-9", "hard", "modification approvals after activation"),
    ("CTR-17", "ENB-13", "hard", "classification through the stage 06 proposal; CONTRACT_AMENDED fold"),
    ("CTR-19", "CTR-12", "hard", "test_history_lists_estimate_pairs (K-06 estimate versions)"),
    ("CTR-19", "CTR-2", "hard", "calc trace store"),
    ("CTR-20", "CTR-9", "hard", "key contracts activated through CONTRACT_ACTIVATED approvals"),
    ("CTR-20", "CTR-7", "hard", "WLD-B-03 judgement SUBMITTED"),
    ("CTR-20", "CTR-8", "hard", "K-05 and K-11 suggestion DISMISSED"),
    ("CTR-20", "CTR-10", "hard", "WLD-B-05 journal_export hold"),
    ("CTR-20", "CTR-12", "hard", "K-06 estimate versions"),
    ("CTR-20", "CTR-14", "hard", "K-09 commission cost asset"),
    ("CTR-20", "RFD-16", "hard", "Avenmoor reference data"),
    ("CTR-21", "CTR-20", "hard", "captures seeded contracts"), ("CTR-21", "CTR-10", "hard", "On hold quick list"),
    ("CTR-21", "CTR-4", "hard", "binds API-R-28 list"), ("CTR-21", "WEB-12", "hard", "screens.spec personas"),
    ("CTR-22", "CTR-5", "hard", "record events drawer binds API-R-30"),
    ("CTR-22", "CTR-7", "hard", "Step 1 review drawer binds API-R-33"),
    ("CTR-22", "CTR-8", "hard", "combine drawer"),
    ("CTR-22", "CTR-9", "hard", "activation failure lines (409 activation-checklist-failed)"),
    ("CTR-22", "CTR-10", "hard", "holds and memos drawers"), ("CTR-22", "CTR-11", "hard", "void drawer"),
    ("CTR-22", "CTR-15", "hard", "obligation pane binds API-R-29; policy override drawer"),
    ("CTR-22", "CTR-17", "hard", "regroup drawer"),
    ("CTR-23", "CTR-14", "hard", "billing plan, usage commitments and cost assets"),
    ("CTR-23", "CTR-5", "hard", "binds API-R-35"), ("CTR-23", "CTR-3", "hard", "binds API-R-36"),
    ("CTR-26", "CTR-19", "hard", "binds API-R-49"),
    ("CTR-26", "CTR-22", "hard", "explain panel placement on SF-03"),
    # Data in
    ("DIN-1", "CTR-5", "hard", "adds foreign key exception_item.import_upload_id"),
    ("DIN-1", "RFD-12", "hard", "adds foreign key ssp_book_version.import_upload_id"),
    ("DIN-1", "RFD-3", "hard", "adds foreign key fx_rate_set_version.import_upload_id"),
    ("DIN-2", "CTR-5", "hard", "adds foreign key exception_item.source_record_id"),
    ("DIN-2", "DIN-1", "hard", "source records carry import lineage"),
    ("DIN-3", "CTR-4", "hard", "contracts CSV emitter books contracts through commands"),
    ("DIN-3", "CTR-5", "hard", "import commits append events"),
    ("DIN-4", "RFD-13", "hard", "SKU SSP template creates LEGACY book versions"),
    ("DIN-4", "RFD-11", "hard", "legacy-parity preset"),
    ("DIN-4", "CTR-9", "hard", "setup import approval activates contracts"),
    ("DIN-5", "CTR-5", "hard", "progress rows emit fact-capture events"),
    ("DIN-6", "ENB-8", "hard", "legacy modification template modes consumed (§6.5)"),
    ("DIN-10", "DIN-3", "hard", "mapping profiles apply in the validation and diff pipeline"),
    ("DIN-11", "CTR-5", "hard", "exception items"), ("DIN-11", "DIN-1", "hard", "import-row reprocess"),
    ("DIN-12", "DIN-2", "hard", "adds foreign key source_record.sync_run_id"),
    ("DIN-14", "DIN-12", "hard", "mock router mounting and admin faults"),
    ("DIN-15", "DIN-10", "hard", "queries/mapping-profiles.ts binds API-R-43 mapping profiles"),
    ("DIN-15", "DIN-5", "hard", "WLD-B-04 progress import seed"),
    ("DIN-15", "CTR-20", "hard", "seeded contracts for WLD-B-04"),
    ("DIN-15", "WEB-12", "hard", "screens.spec personas"),
    ("DIN-16", "DIN-3", "hard", "diff and submit steps"),
    ("DIN-17", "DIN-11", "hard", "binds API-R-44"), ("DIN-17", "DIN-15", "hard", "WLD-B-04 items captured"),
    # Close and journals
    ("CLO-1", "CTR-3", "hard", "T-SL-01 to T-SL-04 and ledger_chain_head"),
    ("CLO-2", "RFD-2", "hard", "period locks reference period_state"),
    ("CLO-3", "RFD-2", "hard", "period_state transitions and POST /periods/{id}/open"),
    ("CLO-3", "DIN-3", "hard", "auto-approval suppressed for closing periods (domain/imports/commands.py)"),
    ("CLO-4", "CTR-10", "hard", "holds counted by gates"), ("CLO-4", "DIN-11", "hard", "exception items and actions"),
    ("CLO-6", "EDS-6", "hard", "lock snapshot content from s15_disclosures (§15.2.7)"),
    ("CLO-7", "EDS-6", "hard", "variance between closes (§15.2.8)"),
    ("CLO-7", "CTR-17", "hard", "k03_castellan world holds the J-06 modification"),
    ("CLO-7", "CTR-12", "hard", "k03_castellan world holds J-10 EAC versions"),
    ("CLO-7", "CTR-14", "hard", "k03_castellan cost versions"),
    ("CLO-8", "CLO-3", "hard", "post-close flag and period guard"),
    ("CLO-8", "CTR-10", "hard", "journal_export hold excludes lines"),
    ("CLO-8", "GPA-1", "hard", "tests replay golden steps through backend/tests/support/parity/"),
    ("CLO-8", "DIN-5", "hard", "legacy v1 pipeline"),
    ("CLO-9", "GPA-5", "hard", "TC-JE-04 to TC-JE-09 need golden steps 04 to 14 replayed"),
    ("CLO-10", "CLO-4", "hard", "JE_BALANCED and JE_COMPLETE gate signals"),
    ("CLO-11", "CLO-7", "hard", "test_reopened_period_needs_human_approval"),
    ("CLO-12", "CLO-4", "hard", "MANUAL_ADJUSTMENTS_CLEARED gate"),
    ("CLO-12", "CTR-5", "hard", "MANUAL_ADJUSTMENT_APPLIED fact capture"),
    ("CLO-13", "CLO-11", "hard", "exports approved runs"),
    ("CLO-15", "DIN-14", "hard", "NetSuite GL adapter and mock files"),
    ("CLO-15", "DIN-12", "hard", "mock router mounting"),
    ("CLO-16", "DIN-2", "hard", "source invoices T-SRC-04 and T-SRC-05"),
    ("CLO-17", "CLO-15", "hard", "GLAdapter.pull_trial_balance"),
    ("CLO-18", "ENC-14", "hard", "close_gate_facts (S10-R-19)"),
    ("CLO-19", "CLO-5", "hard", "run_monitors inside EXCEPTION_CHECK"),
    ("CLO-19", "CTR-5", "hard", "CONTRACT_COMPUTE recompute"),
    ("CLO-20", "CLO-8", "hard", "JOURNAL_SUMMARIZATION"), ("CLO-20", "CLO-14", "hard", "ACKNOWLEDGEMENT_WAIT"),
    ("CLO-20", "CLO-17", "hard", "GL_TIE_OUT"), ("CLO-20", "CLO-18", "hard", "EXCEPTION_CHECK AR tie-out"),
    ("CLO-20", "CLO-6", "hard", "DATASET_FREEZE through snapshots.freeze_datasets"),
    ("CLO-20", "END-2", "hard", "FX_REMEASUREMENT"),
    ("CLO-22", "CLO-20", "hard", "Jan to Aug closed through succeeded close runs"),
    ("CLO-22", "CLO-7", "hard", "Jun lock, reopen and relock history"),
    ("CLO-22", "CLO-15", "hard", "NetSuite trial balance fixture"),
    ("CLO-22", "CTR-20", "hard", "seeded contracts"),
    ("CLO-23", "CLO-4", "hard", "binds the cockpit"), ("CLO-23", "CLO-6", "hard", "locked capture"),
    ("CLO-23", "CLO-22", "hard", "captures seeded FY2026-P08 lock and FY2026-P09 blockers"),
    ("CLO-23", "RFD-19", "hard", "context pill binding"), ("CLO-23", "WEB-12", "hard", "screens.spec personas"),
    ("CLO-26", "CLO-8", "hard", "binds API-R-38"), ("CLO-26", "CLO-11", "hard", "approved runs"),
    ("CLO-26", "CLO-14", "hard", "every batch acknowledged capture"),
    ("CLO-26", "CLO-15", "hard", "NetSuite mock acknowledgements"),
    ("CLO-26", "CLO-22", "hard", "extends domain/demo/close_history.py"),
    ("CLO-26", "CTR-3", "hard", "binds API-R-36"), ("CLO-26", "DIN-2", "hard", "binds API-R-56 source records"),
    # Reports
    ("RPS-1", "CLO-2", "hard", "adds foreign key lock_snapshot.report_run_id"),
    ("RPS-3", "EDS-3", "hard", "rollforward projection"),
    ("RPS-3", "EDS-4", "hard", "revenue_from_prior_period_obligations"),
    ("RPS-3", "CLO-8", "hard", "TO_WATERFALL_EQ_JE_REVENUE (CTL-030)"),
    ("RPS-3", "CLO-7", "hard", "k03_castellan world"),
    ("RPS-3", "CTR-12", "hard", "k06_drossel estimate version 2"),
    ("RPS-4", "EDS-2", "hard", "RPO rollforward"), ("RPS-4", "CTR-17", "hard", "k02_marrowby modification"),
    ("RPS-4", "CTR-14", "hard", "k09 commission"),
    ("RPS-5", "GPA-5", "hard", "full UAT final state replay (WLD-X-28)"),
    ("RPS-6", "CTR-19", "hard", "report cell explain (SB-R-07)"), ("RPS-6", "RPS-4", "hard", "rpo report capture"),
    ("RPS-6", "RPS-5", "hard", "legacy export capture"),
    ("RPS-6", "CLO-22", "hard", "as-locked capture on the seeded lock"),
    ("RPS-6", "WEB-12", "hard", "screens.spec personas"),
    ("RPS-7", "RPS-3", "hard", "binds revenue_waterfall"), ("RPS-7", "RPS-5", "hard", "binds legacy_je_summary"),
    ("RPS-7", "CTR-5", "hard", "binds API-R-35"), ("RPS-7", "CLO-4", "hard", "GET /periods with blockers"),
    ("RPS-7", "DIN-11", "hard", "API-R-44 anomaly counts"), ("RPS-7", "CLO-22", "hard", "seeded lock capture"),
    ("RPS-17", "RPS-3", "hard", "revenue panel equals the waterfall"), ("RPS-17", "RPS-4", "hard", "rpo panel"),
    ("RPS-17", "CLO-4", "hard", "close panel equals API-S-Period"),
    ("RPS-17", "CLO-8", "hard", "drill chain from journal lines"),
    ("RPS-17", "DIN-3", "hard", "drill chain to the source row"),
    ("RPS-17", "CTR-20", "hard", "WLD-B-01 to WLD-B-03 pending approvals"),
    ("RPS-22", "RPS-17", "hard", "binds API-R-50"), ("RPS-22", "RPS-6", "hard", "rail destination Reports"),
    ("RPS-22", "RPS-7", "hard", "rail destination Schedules"), ("RPS-22", "CLO-23", "hard", "rail destination Close"),
    ("RPS-22", "CLO-26", "hard", "rail destination Journals"), ("RPS-22", "DIN-15", "hard", "rail destination Data"),
    ("RPS-22", "WEB-15", "hard", "rail destination Approvals"),
    ("RPS-22", "WEB-17", "hard", "rail destination Settings"),
    ("RPS-22", "RFD-22", "hard", "rail destination Policies"),
    ("RPS-22", "CTR-21", "hard", "rail destination Contracts"),
    # Deploy
    ("DEP-2", "DEP-1", "hard", "compose services use the images"),
    # Foreign keys named by table, not by T-id, in the Schema lines
    ("RPS-2", "RPS-1", "hard", "report runs insert T-RPT-02 report_run rows"),
    ("CLO-2", "CLO-1", "hard", "close runs reference journal runs (JOURNAL_SUMMARIZATION step)"),
    ("DIN-4", "DIN-2", "hard", "T-CON-02 contract_source_link references source_record"),
    # Sequence edges inside a capability that no shared file reveals
    ("GPA-3", "GPA-2", "hard", "the scenario replays golden steps in order; steps 08 and 09 follow 04 to 07"),
    ("GPA-4", "GPA-3", "hard", "steps 10 to 13 follow steps 08 and 09"),
    ("GPA-5", "GPA-4", "hard", "step 14 follows steps 10 to 13"),
    ("CTR-4", "CTR-2", "hard", "time-travel reads return computed versions, schedules and the allocation walk"),
    ("CTR-4", "CTR-3", "hard", "GET /contracts/{id}/subledger-lines reads postings"),
    ("CLO-6", "CLO-4", "hard", "lock with certification evaluates the close gates"),
    ("CLO-6", "CLO-5", "hard", "DATA_QUALITY_CLEAR gate signal"),
    ("CLO-3", "CLO-2", "hard", "start_close instantiates the system close checklist"),
    ("CLO-8", "CLO-1", "hard", "journal runs write T-SL-06 to T-SL-09"),
    ("ENA-12", "ENA-11", "hard", "targeted VC, discount exception and residual run after relative allocation"),
    ("ENB-3", "ENB-2", "hard", "catch-up and mixed modifications extend the prospective pools and segments"),
    ("ENC-13", "ENC-12", "hard", "contract asset versus unbilled receivable splits a debit net position"),
    ("DIN-6", "DIN-5", "hard", "modification template tests replay progress rows first (TC-DELIVERY-22)"),
    ("RFD-16", "RFD-7", "hard", "seeds mapping AVM-MAP-2026-01 PUBLISHED"),
    ("GPB-2", "GPB-1", "hard", "journal_entry_totals value source and probes are added by GPB-1"),
    ("GPB-2", "GPA-5", "hard", "steps 08 to 14 and months May to October replay the full scenario"),
    ("DIN-3", "DIN-2", "hard", "atomic commit writes source records and row lineage"),
]

IGNORED_AUTO_EDGES: dict[tuple[str, str], str] = {
    ("CLO-13", "DIN-14"): "adapters/gl/csv.py is a sibling module; the CSV adapter implements the CLO-13 ports.py protocol",
    ("RPS-2", "CLO-8"): "backend/erev_api/jobs/ exists since PLF; the first Paths mention is not a producer",
    ("CLO-19", "CLO-8"): "backend/erev_api/jobs/ exists since PLF; the first Paths mention is not a producer",
}

# Variant V-B: a supervisor descoping ruling for tonight's rc. Each dropped edge removes an acceptance
# fragment from the consuming item (captures of seeded close history, drawers of unbuilt commands, worlds
# built on deferred commands). Under XR-14 the fragment is hidden, and the item records a SPEC-Q.
RULING_R_RC_1: list[tuple[str, str, str]] = [
    ("CLO-23", "CLO-22", "SF-05 captures the FY2026-P09 open cockpit only; the seeded locked FY2026-P08 capture moves to DMO"),
    ("CLO-23", "CLO-6", "no Locked chip capture until CLO-6 lands"),
    ("CLO-26", "CLO-22", "SF-06 captures a run created in beforeAll through the API instead of seeded history"),
    ("CLO-26", "CLO-14", "run-batches capture shows CSV export without NetSuite acknowledgements"),
    ("CLO-26", "CLO-15", "no NetSuite mock acknowledgements"),
    ("RPS-6", "CLO-22", "the rpo as-locked capture moves to DMO"),
    ("RPS-7", "CLO-22", "the SF-04 as-locked capture moves to DMO"),
    ("RPS-3", "CLO-7", "contract balances test uses k01 only; k03_castellan moves with CLO-7"),
    ("RPS-3", "EDS-4", "revenue_from_prior_period_obligations (RPT-05) and its DISC keys move to post-rc"),
    ("RPS-3", "CLO-6", "as-locked run test moves with CLO-6; worlds.py k01 is created by RPS-3"),
    ("RPS-3", "CLO-16", "CONTRACT_BALANCE_ROLLFORWARD reconciliation moves with CLO-16"),
    ("RPS-4", "CLO-6", "worlds.py is created by RPS-3 in this variant"),
    ("RPS-4", "CTR-17", "rpo k02 test without the CR-MARROWBY-2026-09 modification"),
    ("RPS-4", "CTR-14", "k09 commission world moves with CTR-14"),
    ("CTR-22", "CTR-11", "void drawer hidden (XR-14)"),
    ("CTR-22", "CTR-17", "regroup drawer hidden (XR-14)"),
    ("CTR-23", "CTR-14", "billing tab without billing plan and usage commitments; costs panel hidden"),
    ("CTR-20", "CTR-12", "K-06 estimate versions seeded post-rc"),
    ("CTR-20", "CTR-14", "K-09 commission cost seeded post-rc"),
    ("CTR-19", "CTR-12", "explain history estimate-pair test moves with CTR-12"),
    ("CLO-11", "CLO-7", "reopened-period approval test moves with CLO-7"),
]

# Deferred items the brief's capabilities depend on, with the capability and the consequence.
DEFERRED_NOTES = {
    "ENC-5": ("C2, C3", "input measures (cost to cost, labour hours, cost recovery, uninstalled materials): keys with "
                        "those recognition methods fail closed"),
    "ENC-6": ("C2, C3", "right to invoice, usage and minimum commitments: usage and RTI keys fail"),
    "ENC-8": ("C2, C3", "breakage, material-right recognition and royalties: BRK, ROY and redemption-pattern MR keys fail"),
    "END-11": ("C2", "JET check tests part 1 only; the templates are built by END-4 to END-6"),
    "END-12": ("C2", "JET check tests part 2 only"),
    "END-13": ("C2", "P8 and P14 properties; trace re-evaluation stays covered by CTR-19 verify"),
    "END-14": ("C2", "metamorphic suite"),
    "EDS-7": ("C3", "DISC closure item; DISC keys stay green through the RPS-3 and RPS-4 selections"),
    "AKS-8": ("C3", ROOT_EXCLUSIONS["AKS-8"]),
    "GPB-3": ("C3", "point_in_time_equivalence needs LMG-4 and SNP-1 to SNP-3"),
    "GPB-4": ("C3", ROOT_EXCLUSIONS["GPB-4"]),
    "RPS-23": ("C10", ROOT_EXCLUSIONS["RPS-23"]),
    "RPS-24": ("C10", ROOT_EXCLUSIONS["RPS-24"]),
    "CTR-13": ("C5", "portfolio-scoped estimates; estimate.portfolio_id keeps no foreign key"),
    "CTR-16": ("C5", "policy impact simulation over contracts"),
    "CTR-18": ("C5", "subscription-change commands; MOD-FS keys still run through the engine runner"),
    "DIN-9": ("C6", "modern CSV v2 templates other than customers and contracts"),
    "DIN-13": ("C6", "Stripe mock adapter and the inbound adapter contract suite"),
    "CLO-10": ("C7", "journal line validation and completeness gates fail closed on the cockpit"),
    "CLO-12": ("C7", "manual adjustments; the MANUAL_ADJUSTMENTS_CLEARED gate fails closed"),
    "CLO-21": ("C7", "multi-entity close command"),
    "WEB-13": ("C1, C10", "invitation acceptance and MFA enrolment screens; fresh-tenant journeys wait"),
    "WEB-19": ("C10", "users screens visited by J-01"),
    "RFD-18": ("C10", "entities, calendars and currencies settings screens visited by J-01"),
    "RFD-23": ("C10", "accounting policy screens visited by J-01"),
    "DIN-18": ("C10", "integrations screens visited by J-01 part 2"),
    "RPS-21": ("C10", "audit log screen visited by J-01 part 2"),
    "DEP-5": ("C11", "supervisor target scripts; the supervisor validates the images and compose file by hand"),
}

# --------------------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------------------
HEADER = re.compile(r"^- \[( |x)\] \*\*((?:GATE-[A-Z]{3})|(?:[A-Z]{3}-\d+[a-z]?)) (.*?)\*\*")
ITEM_ID = re.compile(r"\b(GATE-[A-Z]{3}|(?:FND|EKC|PLF|WEB|ENA|RFD|ENB|ENC|END|AKS|CTR|DIN|GPA|EDS|CLO|RPS|SNP|LMG|GPB|PRP|"
                     r"FCS|AIX|SOP|DMO|PRF|DEP|REL)-\d+[a-z]?)\b")
TICK = re.compile(r"`([^`]+)`")
FILE_EXT = re.compile(r"[\w.\-]+\.(py|tsx?|jsx?|json|md|ya?ml|sql|conf|txt|toml|css|html|sh|cfg|lock|db|sqlite)")
ROOT_FILES = {"Makefile", "LICENSE", "NOTICE", "README.md", ".env.example", ".gitignore", ".dockerignore", "PROGRESS.md"}
PATH_PREFIXES = ("backend/", "frontend/", "scripts/", "deploy/", "docs/", "research-harness/", "legacy-harness/")


def norm_paths(text: str) -> list[str]:
    """Backticked repository paths of a Scope line; a bare file name inherits the previous directory."""
    out: list[str] = []
    last_dir: str | None = None
    for raw in TICK.findall(text or ""):
        tok = raw.strip().split("::", 1)[0].rstrip(",;")
        if not tok or " " in tok:
            continue
        if tok in ROOT_FILES:
            out.append(tok)
        elif "/" in tok:
            if tok.startswith(PATH_PREFIXES):
                out.append(tok)
                last_dir = tok if tok.endswith("/") else tok.rsplit("/", 1)[0] + "/"
        elif FILE_EXT.fullmatch(tok) and last_dir:
            out.append(last_dir + tok)
    seen: set[str] = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def parse_items() -> list[dict]:
    lines = SPEC.read_text(encoding="utf-8").split("\n")
    heads = [(i, m) for i, l in enumerate(lines) if (m := HEADER.match(l))]
    items = []
    for n, (i, m) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        block = lines[i:end]
        iid = m.group(2)
        d = {"id": iid, "title": m.group(3).rstrip("."), "line": i + 1, "order": n,
             "phase": "GATE" if iid.startswith("GATE-") else iid.split("-")[0], "block": "\n".join(block)}
        in_accept = False
        for l in block:
            for f in ("Prerequisites", "Read", "Gates"):
                if l.startswith(f"  - **{f}:**"):
                    d[f.lower()] = l.split("**", 2)[2].strip()
            if l.startswith("  - **Acceptance:**"):
                in_accept = True
            if l.startswith("  - **Read:**"):
                in_accept = False
            for f in ("Paths", "Schema", "API", "Engine", "Screens"):
                key = ("accept_" if in_accept else "") + f.lower()
                if l.startswith(f"    - {f}:") and key not in d:
                    d[key] = l.split(":", 1)[1].strip()
            for f in ("Answer keys", "Golden", "Journeys"):
                key = f.lower().replace(" ", "_")
                if in_accept and l.startswith(f"    - {f}:") and key not in d:
                    d[key] = l.split(":", 1)[1].strip()
        d["paths_list"] = norm_paths(d.get("paths", ""))
        d["prereq_ids"] = ITEM_ID.findall(d.get("prerequisites", ""))
        d["adds_migration"] = MIGRATION_OVERRIDES.get(iid, any("db/migrations/versions/" in p for p in d["paths_list"]))
        d["kind"] = classify(d)
        d["cost"] = COST_OVERRIDES.get(iid, COST[d["kind"]])
        items.append(d)
    return items


def classify(d: dict) -> str:
    if d["phase"] == "GATE":
        return "gate"
    if d["phase"] in ENGINE_PHASES:
        return "engine"
    if d["phase"] == "AKS":
        return "aks"
    if d["phase"] in ("GPA", "GPB"):
        return "parity"
    if d["phase"] == "DEP":
        return "deploy"
    if (d.get("journeys") or "none").split()[0] != "none":
        return "journey"
    if d["adds_migration"]:
        return "migration"
    if "GK-07" in (d.get("gates") or ""):
        return "screen"
    paths = d["paths_list"]
    if paths and all(p.startswith("frontend/") for p in paths):
        return "frontend"
    if any("/domain/demo/" in p for p in paths) and d["phase"] in ("WEB", "RFD", "CTR", "CLO"):
        return "seed"
    return "backend"


def done_ids(items: list[dict]) -> set[str]:
    ids = {d["id"] for d in items}
    try:
        subjects = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%s"], capture_output=True, text=True,
                                  check=True).stdout
        committed = set(re.findall(r"^(GATE-[A-Z]{3}|[A-Z]{3}-\d+[a-z]?)", subjects, flags=re.M))
    except (OSError, subprocess.CalledProcessError):
        committed = {f"{p}-{i}" for p, n in DONE_FALLBACK_PHASES.items() for i in range(1, n + 1)}
        committed |= {"EKC-7a", "EKC-7b", "EKC-7c", "PLF-3a", "PLF-3b", "PLF-3c", "GATE-FND", "GATE-EKC", "GATE-PLF"}
        committed |= {f"WEB-{i}" for i in range(1, 7)} | {"WEB-3a", "WEB-3b", "WEB-3c", "WEB-3d"}
    return (committed | IN_FLIGHT_TREATED_DONE) & ids


# --------------------------------------------------------------------------------------------------
# Edges and closure
# --------------------------------------------------------------------------------------------------
FIXTURE_NAME = re.compile(r"\b(k\d\d[a-z]?_[a-z_]+)\b")
FIXTURE_FILES = {
    "golden_streams": "backend/tests/support/golden_streams.py",
    "legacy_replay": "backend/tests/support/legacy_replay.py",
    "support/parity/": "backend/tests/support/parity/__init__.py",
    "activated_contract": "backend/tests/support/factories.py",
    "intent_totals": "backend/tests/support/intent_totals.py",
}
DIR_EDGE_EXCLUDED = {"backend/erev_api/api/v1/", "backend/erev_api/schemas/", "docs/guides/", "backend/tests/support/",
                     "backend/erev_api/jobs/", "backend/erev_api/"}


def auto_edges(items: list[dict], done: set[str]) -> dict[str, list[tuple[str, str, str]]]:
    by_id = {d["id"]: d for d in items}
    edges: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    file_producer: dict[str, str] = {}
    dir_producer: dict[str, str] = {}
    for d in items:
        for p in d["paths_list"]:
            file_producer.setdefault(p, d["id"])
            if not p.endswith("/"):
                dir_producer.setdefault(p.rsplit("/", 1)[0] + "/", d["id"])
    fixture_producer: dict[str, str] = {}
    for d in items:
        if "worlds.py" in d.get("paths", ""):
            for name in FIXTURE_NAME.findall(d.get("paths", "")):
                fixture_producer.setdefault(name, d["id"])
    for name, path in FIXTURE_FILES.items():
        if path in file_producer:
            fixture_producer.setdefault(name, file_producer[path])
    api_producer: dict[str, str] = {}
    table_producer: dict[str, str] = {}
    for d in items:
        api = d.get("api", "")
        if re.match(r"API-R-\d+", api):
            for row in re.findall(r"API-R-\d+", api.split("(binds")[0]):
                api_producer.setdefault(row, d["id"])
        for t in re.findall(r"\bT-[A-Z]{2,3}-\d+\b", d.get("schema", "")):
            table_producer.setdefault(t, d["id"])

    def add(item: str, dep: str, reason: str) -> None:
        if dep == item or dep in done or dep not in by_id or (item, dep) in IGNORED_AUTO_EDGES:
            return
        if by_id[dep]["order"] > by_id[item]["order"]:
            return  # forward references are fail-closed consumers (XR-12), never dependencies
        edges[item].append((dep, "hard", reason))

    for d in items:
        iid = d["id"]
        chain_pred = items[d["order"] - 1]["id"] if d["order"] > 0 else None
        for dep in d["prereq_ids"]:
            if not dep.startswith("GATE-") and dep != chain_pred:
                add(iid, dep, f"named in Prerequisites: {d.get('prerequisites', '')[:90]}")
        for p in d["paths_list"]:
            if p in HOTSPOTS:
                continue
            prod = file_producer.get(p)
            if prod and prod != iid:
                add(iid, prod, f"file {p} created by {prod}")
            if p.endswith("/") or (p.startswith("backend/tests/") and not p.startswith("backend/tests/support/")):
                continue
            parent = p.rsplit("/", 1)[0] + "/"
            dprod = dir_producer.get(parent)
            if dprod and dprod != iid and parent not in DIR_EDGE_EXCLUDED:
                add(iid, dprod, f"directory {parent} created by {dprod}")
        for name, prod in fixture_producer.items():
            if prod != iid and name in d["block"]:
                add(iid, prod, f"fixture {name} from {prod}")
        api = d.get("api", "")
        if api.startswith("none"):
            for row in re.findall(r"API-R-\d+", api):
                if row in api_producer:
                    add(iid, api_producer[row], f"binds {row} first built by {api_producer[row]}")
        for t in re.findall(r"\bT-[A-Z]{2,3}-\d+\b", d.get("schema", "")):
            prod = table_producer.get(t)
            if prod and prod != iid:
                add(iid, prod, f"schema {t} created by {prod}")
    return edges


# Screens code against the 04 API schemas with MSW fakes (brief: integration-after-merge); their e2e captures
# run in the merge gate. Seeds, personas, placements and worlds stay hard.
API_SCREEN_CONTRACTS = {
    ("CTR-21", "CTR-4"), ("CTR-22", "CTR-5"), ("CTR-22", "CTR-7"), ("CTR-22", "CTR-8"), ("CTR-22", "CTR-9"),
    ("CTR-22", "CTR-10"), ("CTR-22", "CTR-11"), ("CTR-22", "CTR-15"), ("CTR-22", "CTR-17"), ("CTR-23", "CTR-14"),
    ("CTR-23", "CTR-5"), ("CTR-23", "CTR-3"), ("CTR-26", "CTR-19"), ("DIN-15", "DIN-10"), ("DIN-16", "DIN-3"),
    ("DIN-17", "DIN-11"), ("CLO-23", "CLO-4"), ("CLO-23", "CLO-6"), ("CLO-23", "RFD-19"), ("CLO-26", "CLO-8"),
    ("CLO-26", "CLO-11"), ("CLO-26", "CLO-14"), ("CLO-26", "CLO-15"), ("CLO-26", "CTR-3"), ("CLO-26", "DIN-2"),
    ("RPS-6", "CTR-19"), ("RPS-6", "RPS-4"), ("RPS-6", "RPS-5"), ("RPS-7", "RPS-3"), ("RPS-7", "RPS-5"),
    ("RPS-7", "CTR-5"), ("RPS-7", "CLO-4"), ("RPS-7", "DIN-11"), ("RPS-22", "RPS-17"), ("RPS-22", "RPS-6"),
    ("RPS-22", "RPS-7"), ("RPS-22", "CLO-23"), ("RPS-22", "CLO-26"), ("RPS-22", "DIN-15"), ("RPS-22", "WEB-15"),
    ("RPS-22", "WEB-17"), ("RPS-22", "RFD-22"), ("RPS-22", "CTR-21"), ("RFD-19", "RFD-2"), ("RFD-19", "RFD-6"),
    ("RFD-19", "RFD-11"), ("RFD-22", "RFD-10"), ("RFD-22", "RFD-5"), ("RFD-24", "RFD-13"), ("RFD-24", "RFD-15"),
    ("RFD-24", "RFD-22"),
}
# Variant V-C: platform consumers of engine functions and compute outputs code against ENGINE_SPEC §0.5 and
# Table 0.2-A with fakes; their number-asserting tests turn green only in the merge gate.
COMPUTE_CONTRACTS = {
    ("CTR-2", "END-10"), ("CTR-2", "EDS-1"), ("RFD-10", "ENA-5"), ("RFD-14", "ENA-10"), ("CTR-10", "ENC-9"),
    ("CTR-12", "ENB-10"), ("CTR-14", "ENC-16"), ("CTR-14", "END-2"), ("CTR-17", "ENB-13"), ("CLO-6", "EDS-6"),
    ("CLO-7", "EDS-6"), ("CLO-18", "ENC-14"), ("CLO-20", "END-2"), ("RPS-3", "EDS-3"), ("RPS-3", "EDS-4"),
    ("RPS-4", "EDS-2"), ("DIN-6", "ENB-8"), ("AKS-1", "RFD-13"),
}
INTEGRATION_MERGE_MIN = 10  # merge-step minutes per integration-after-merge item


def all_edges(items: list[dict], done: set[str], dropped: set[tuple[str, str]] = frozenset(),
              contracts: set[tuple[str, str]] = frozenset(API_SCREEN_CONTRACTS)):
    by_id = {d["id"]: d for d in items}
    raw = auto_edges(items, done)
    manual: dict[str, dict[str, tuple[str, str, str]]] = defaultdict(dict)
    for item, dep, kind, reason in MANUAL_EDGES:
        assert item in by_id and dep in by_id, (item, dep)
        if dep not in done:
            manual[item][dep] = (dep, kind, f"verified: {reason}")
    out: dict[str, list[tuple[str, str, str]]] = {}
    for item in set(raw) | set(manual):
        best: dict[str, tuple[str, str, str]] = dict(manual.get(item, {}))
        for dep, kind, reason in raw.get(item, []):
            if reason.startswith("binds ") and by_id[item]["kind"] in ("screen", "frontend"):
                kind = "contract"
            best.setdefault(dep, (dep, kind, reason))
        lst = []
        for dep, (d2, kind, reason) in best.items():
            if (item, dep) in dropped:
                continue
            if (item, dep) in contracts:
                kind = "contract"
            lst.append((d2, kind, reason))
        out[item] = lst
    return out


def declared_closure(items: list[dict], roots: list[str]) -> set[str]:
    """Closure over the declared Prerequisites, where GATE-<code> stands for every item of that phase."""
    by_id = {d["id"]: d for d in items}
    phase_items = defaultdict(list)
    for d in items:
        if d["phase"] != "GATE":
            phase_items[d["phase"]].append(d["id"])
    seen: set[str] = set()
    q = deque(roots)
    while q:
        iid = q.popleft()
        if iid in seen or iid not in by_id:
            continue
        seen.add(iid)
        if iid.startswith("GATE-"):
            q.extend(phase_items[iid.split("-")[1]])
        q.extend(by_id[iid]["prereq_ids"])
    return seen


def technical_closure(items: list[dict], edges, done: set[str]) -> tuple[set[str], dict[str, list[str]]]:
    by_id = {d["id"]: d for d in items}
    roots = [r for r in MVP_ROOTS if r not in ROOT_EXCLUSIONS]
    why: dict[str, list[str]] = defaultdict(list)
    for r in roots:
        why[r].append(f"root {MVP_ROOTS[r]}")
    seen: set[str] = set()
    q = deque(roots)
    while q:
        iid = q.popleft()
        if iid in seen or iid in done:
            continue
        seen.add(iid)
        for dep, kind, reason in edges.get(iid, []):
            if dep in done or dep in ROOT_EXCLUSIONS:
                continue
            why[dep].append(f"{iid} ({kind}): {reason}")
            q.append(dep)
    return {i for i in seen if i in by_id}, why


# --------------------------------------------------------------------------------------------------
# Answer keys
# --------------------------------------------------------------------------------------------------
def key_facts() -> dict[str, dict]:
    facts = {}
    for f in sorted(KEYS_DIR.glob("*/*.yaml")):
        text = f.read_text(encoding="utf-8")
        m = re.search(r"^id:\s*(\S+)", text, flags=re.M)
        if not m:
            continue
        fam = re.search(r"^families:\s*\[([^\]]*)\]", text, flags=re.M)
        status = re.search(r'^status:\s*"?(\w+)', text, flags=re.M)
        runner = re.search(r'^runner:\s*"?(\w+)', text, flags=re.M)
        facts[m.group(1)] = {
            "families": [x.strip().strip('"') for x in (fam.group(1).split(",") if fam else [])],
            "status": status.group(1) if status else None,
            "runner": runner.group(1) if runner else None,
            "methods": set(re.findall(r"recognition_method:\s*\"?(\w+)", text)),
            "events": set(re.findall(r"event_type:\s*\"?(\w+)", text)),
        }
    return facts


def key_blockers(f: dict) -> list[str]:
    b = []
    if f["methods"] & {"COST_TO_COST", "LABOUR_HOURS", "COST_RECOVERY"}:
        b.append("ENC-5")
    if f["methods"] & {"RIGHT_TO_INVOICE", "USAGE"} or "USAGE_REPORTED" in f["events"]:
        b.append("ENC-6")
    if f["methods"] & {"REDEMPTION_PATTERN", "ROYALTY"} or "MATERIAL_RIGHT_EXPIRED" in f["events"]:
        b.append("ENC-8")
    if f["runner"] == "platform":
        b.append("PRP-1")
    return b


def item_key_ids(d: dict) -> list[str]:
    text = (d.get("answer_keys") or "") + " " + (d.get("gates") or "")
    ids: list[str] = []
    for m in re.finditer(r"ID=([A-Z0-9][A-Z0-9,\-]+)", text):
        ids.extend(x for x in m.group(1).split(",") if x)
    seen: set[str] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def key_support(items: list[dict], in_scope: set[str], done: set[str]) -> dict:
    facts = key_facts()
    avail = in_scope | done
    result = {"items": {}, "families": {}, "supported_ids": [], "blocked": {}}
    fam_tot: dict[str, list] = defaultdict(lambda: [0, 0, set()])
    for kid, f in sorted(facts.items()):
        if f["status"] != "active":
            continue
        blockers = [b for b in key_blockers(f) if b not in avail]
        fam = f["families"][0] if f["families"] else "?"
        fam_tot[fam][0] += 1
        if blockers:
            result["blocked"][kid] = blockers
            fam_tot[fam][2] |= set(blockers)
        else:
            fam_tot[fam][1] += 1
            if f["runner"] == "engine":
                result["supported_ids"].append(kid)
    result["families"] = {k: {"active": v[0], "runnable": v[1], "blocked_by": sorted(v[2])}
                          for k, v in sorted(fam_tot.items())}
    for d in items:
        ids = item_key_ids(d)
        if not ids or d["id"] not in in_scope:
            continue
        blocked = {k: result["blocked"][k] for k in ids if k in result["blocked"]}
        result["items"][d["id"]] = {"keys": len(ids), "runnable": len(ids) - len(blocked), "blocked": blocked}
    return result


# --------------------------------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------------------------------
def family(d: dict) -> str:
    if d["kind"] == "engine":
        return {"ENA": "eng-alloc", "ENB": "eng-mod", "ENC": "eng-rec", "END": "eng-post", "EDS": "eng-post"}[d["phase"]]
    if d["kind"] == "aks":
        return "eng-keys"
    if d["kind"] == "migration":
        return "mig"
    if d["kind"] in ("screen", "frontend", "journey", "deploy"):
        return "web"
    if d["kind"] == "parity":
        return "parity"
    return f"api-{d['phase'].lower()}"


def lane_class(fam: str) -> str:
    return "engine" if fam.startswith("eng-") else "platform"


def scope_files(d: dict) -> set[str]:
    files = set(d["paths_list"])
    if any(p.startswith("backend/erev_api/api/v1/") for p in files):
        files.add(IMPLICIT_ROUTER)
    if any(p.startswith("backend/erev_api/db/tables/") and not p.endswith("__init__.py") for p in files):
        files.add(IMPLICIT_TABLES)
    if "GK-03" in (d.get("gates") or ""):
        files |= {"docs/api/openapi.json", "frontend/src/lib/api/schema.d.ts"}
    if d["id"] in CORRECTION_ITEMS:
        files.add(CORRECTION_SCOPE)
    return files


def overlaps(a: set[str], b: set[str]) -> set[str]:
    hits = set()
    for x in a:
        if x in HOTSPOTS:
            continue
        for y in b:
            if y in HOTSPOTS:
                continue
            if x == y or (x.endswith("/") and y.startswith(x)) or (y.endswith("/") and x.startswith(y)):
                hits.add(x if len(x) <= len(y) else y)
    return hits


def successors(in_scope: set[str], edges) -> dict[str, list[str]]:
    succ = defaultdict(list)
    for item in in_scope:
        for dep, _kind, _r in edges.get(item, []):
            if dep in in_scope:
                succ[dep].append(item)
    return succ


def criticality(in_scope: set[str], edges, by_id) -> tuple[dict[str, int], dict[str, int]]:
    succ = successors(in_scope, edges)
    tail: dict[str, int] = {}
    mig: dict[str, int] = {}

    def t(i: str) -> int:
        if i not in tail:
            tail[i] = by_id[i]["cost"] + max((t(s) for s in succ[i]), default=0)
        return tail[i]

    def m(i: str) -> int:
        if i not in mig:
            mig[i] = int(by_id[i]["adds_migration"]) + max((m(s) for s in succ[i]), default=0)
        return mig[i]

    for i in in_scope:
        t(i)
        m(i)
    return tail, mig


SCHEDULER_USED = {"name": None}


def schedule(items: list[dict], in_scope: set[str], edges, done: set[str], max_mig_lanes: int = MAX_MIGRATION_LANES,
             level_box: int | None = None) -> list[dict]:
    """Run both packers and keep the plan with fewer estimated hours (ties: fewer levels)."""
    by_id = {d["id"]: d for d in items}
    best = None
    for packer in (schedule_ff, schedule_greedy):
        lv = packer(items, in_scope, edges, done, max_mig_lanes)
        minutes, _horizon = summarise_levels(lv, by_id, edges)
        key = (sum(minutes), len(lv))
        if best is None or key < best[0]:
            best = (key, lv, packer.__name__)
    SCHEDULER_USED["name"] = best[2]
    return best[1]


def schedule_ff(items: list[dict], in_scope: set[str], edges, done: set[str], max_mig_lanes: int = MAX_MIGRATION_LANES,
                level_box: int | None = None) -> list[dict]:
    """First fit in earliest-start order: each item takes the earliest level and lane its edges and the lane rules allow."""
    level_box = level_box or LEVEL_BOX
    by_id = {d["id"]: d for d in items}
    tail, _mig = criticality(in_scope, edges, by_id)
    es: dict[str, int] = {}

    def start(i: str) -> int:
        if i not in es:
            es[i] = max((start(dep) + by_id[dep]["cost"] for dep, _k, _r in edges.get(i, []) if dep in in_scope),
                        default=0)
        return es[i]

    for i in in_scope:
        start(i)
    order = sorted(in_scope, key=lambda i: (es[i], -tail[i], by_id[i]["order"]))
    levels: list[dict] = []
    pos: dict[str, tuple[int, int]] = {}
    for iid in order:
        d = by_id[iid]
        deps = [(dep, k) for dep, k, _r in edges.get(iid, []) if dep in in_scope]
        fam, files, cost = family(d), scope_files(d), d["cost"]
        cls = lane_class(fam)
        level = max((pos[dep][0] for dep, _k in deps), default=0)
        while True:
            if level == len(levels):
                levels.append({"lanes": [], "placed": {}})
            lanes = levels[level]["lanes"]
            same = {pos[dep][1] for dep, k in deps if k == "hard" and pos[dep][0] == level}
            mig_lanes = [n for n, l in enumerate(lanes) if l["adds_migrations"]]

            def compatible(n: int, dep_lane: bool) -> bool:
                lane = lanes[n]
                if lane["class"] != cls or lane["minutes"] + cost > level_box:
                    return False
                if d["adds_migration"] and not lane["adds_migrations"] and len(mig_lanes) >= max_mig_lanes:
                    return False
                if lane["adds_migrations"] and not d["adds_migration"] and not dep_lane:
                    return False  # keep migration-lane capacity for the schema chain
                return all(not overlaps(files, other["files"]) for k, other in enumerate(lanes) if k != n)

            target = None
            if len(same) == 1:
                n = next(iter(same))
                target = n if compatible(n, True) else None
            elif not same:
                pref = [n for n, l in enumerate(lanes) if l["family"] == fam and compatible(n, False)]
                if pref:
                    target = pref[0]
                elif len(lanes) < MAX_LANES and all(not overlaps(files, l["files"]) for l in lanes) and \
                        not (d["adds_migration"] and len(mig_lanes) >= max_mig_lanes):
                    lanes.append({"family": fam, "class": cls, "items": [], "minutes": 0, "files": set(),
                                  "adds_migrations": False})
                    target = len(lanes) - 1
                else:
                    others = [n for n in range(len(lanes)) if compatible(n, False)]
                    target = others[0] if others else None
            if target is None:
                level += 1
                continue
            lane = lanes[target]
            lane["items"].append(iid)
            lane["minutes"] += cost
            lane["files"] |= files
            lane["adds_migrations"] = lane["adds_migrations"] or d["adds_migration"]
            levels[level]["placed"][iid] = target
            pos[iid] = (level, target)
            break
    return levels


def schedule_greedy(items: list[dict], in_scope: set[str], edges, done: set[str],
                    max_mig_lanes: int = MAX_MIGRATION_LANES):
    """Level-by-level greedy by criticality (kept for comparison; `schedule` packs better)."""
    by_id = {d["id"]: d for d in items}
    tail, mig = criticality(in_scope, edges, by_id)
    merged = set(done)
    remaining = set(in_scope)
    levels = []
    while remaining:
        lanes: list[dict] = []
        placed: dict[str, int] = {}
        progress = True
        while progress:
            progress = False
            order = sorted(remaining - set(placed), key=lambda i: (-mig[i], -tail[i], by_id[i]["order"]))
            for iid in order:
                d = by_id[iid]
                deps = [(dep, k) for dep, k, _ in edges.get(iid, []) if dep in in_scope and dep not in merged]
                if any(dep not in placed for dep, _k in deps):
                    continue
                lane_deps = {placed[dep] for dep, k in deps if k == "hard"}
                if len(lane_deps) > 1:
                    continue
                fam, files, cost = family(d), scope_files(d), d["cost"]
                cls = lane_class(fam)
                mig_lanes = [n for n, l in enumerate(lanes) if l["adds_migrations"]]

                def fits(n: int, dep_lane: bool) -> bool:
                    lane = lanes[n]
                    if lane["class"] != cls or lane["minutes"] + cost > LEVEL_BOX:
                        return False
                    if d["adds_migration"] and not lane["adds_migrations"] and len(mig_lanes) >= max_mig_lanes:
                        return False
                    if lane["adds_migrations"] and not d["adds_migration"] and not dep_lane and fam != "mig":
                        return False  # keep migration-lane capacity for the schema chain
                    return all(not overlaps(files, other["files"]) for k, other in enumerate(lanes) if k != n)

                target = None
                if lane_deps:
                    n = next(iter(lane_deps))
                    target = n if fits(n, True) else None
                else:
                    same = [n for n, l in enumerate(lanes) if l["family"] == fam and fits(n, False)]
                    can_open = len(lanes) < MAX_LANES and all(not overlaps(files, l["files"]) for l in lanes) and \
                        not (d["adds_migration"] and len(mig_lanes) >= max_mig_lanes)
                    if same:
                        target = same[0]
                    elif can_open:
                        lanes.append({"family": fam, "class": cls, "items": [], "minutes": 0, "files": set(),
                                      "adds_migrations": False})
                        target = len(lanes) - 1
                    else:
                        others = [n for n in range(len(lanes)) if fits(n, False)]
                        target = others[0] if others else None
                if target is None:
                    continue
                lane = lanes[target]
                lane["items"].append(iid)
                lane["minutes"] += cost
                lane["files"] |= files
                lane["adds_migrations"] = lane["adds_migrations"] or d["adds_migration"]
                placed[iid] = target
                progress = True
                break  # recompute the order after each placement
        if not placed:
            raise SystemExit(f"scheduler stalled; remaining {sorted(remaining)[:12]}")
        levels.append({"lanes": lanes, "placed": placed})
        merged |= set(placed)
        remaining -= set(placed)
    return levels


def batches_for(lane_items: list[str], by_id) -> list[list[str]]:
    out: list[list[str]] = []
    cur: list[str] = []
    minutes = 0
    for iid in lane_items:
        c = by_id[iid]["cost"]
        if cur and (len(cur) >= BATCH_MAX_ITEMS or minutes + c > BATCH_BOX):
            out.append(cur)
            cur, minutes = [], 0
        cur.append(iid)
        minutes += c
    if cur:
        out.append(cur)
    return out


FAMILY_NAMES = {
    "mig": "Schema chain: the only lane adding Alembic revisions this level",
    "eng-alloc": "Engine: stages 01 to 05 and the inception fold",
    "eng-mod": "Engine: stages 06 to 08 and the boundary fold",
    "eng-rec": "Engine: stages 09 to 11",
    "eng-post": "Engine: stages 12 to 15 and compute",
    "eng-keys": "Engine: answer-key sweeps",
    "web": "Frontend screens, e2e harness and deploy artifacts",
    "parity": "Golden parity",
}
MERGE_PRIORITY = ["mig", "eng-alloc", "eng-mod", "eng-rec", "eng-post", "eng-keys", "parity"]


def gate_selections(d: dict) -> dict[str, list[str]]:
    g = (d.get("gates") or "") + " " + (d.get("golden") or "")
    sel: dict[str, list[str]] = {"properties": [], "parity": []}
    for m in re.finditer(r"make properties K=(\"[^\"]+\"|[\w\-]+)", g):
        sel["properties"].append(m.group(1).strip('"'))
    for m in re.finditer(r"make parity K=(\"[^\"]+\"|[\w\-]+)", g):
        if "<" not in m.group(1):
            sel["parity"].append(m.group(1).strip('"'))
    return sel


GPB_SELECTIONS = {
    "GPB-1": "je-step-02 or je-step-03 or je-step-04 or je-step-05 or je-step-06 or je-step-07 or je-month-2023-01 or "
             "je-month-2023-02 or je-month-2023-03 or je-month-2023-04 or probe-P1-blank-memo-drops-progress-rows or "
             "probe-P2-mod-reposts-pre-asc606-in-delta-je or probe-P4-duplicate-upload-double-counts",
    "GPB-2": "journal_entry_totals and not (je-step-02 or je-step-03 or je-step-04 or je-step-05 or je-step-06 or "
             "je-step-07 or je-month-2023-01 or je-month-2023-02 or je-month-2023-03 or je-month-2023-04)",
}


def level_gates(merged_open: list[str], level_items: set[str], by_id, support, screen_ready: bool) -> list[str]:
    gates = ["git status --porcelain  # empty after the merge commits",
             "make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts",
             "make ci", "make test-pg"]
    props, parity, keys = [], [], []
    for iid in merged_open:
        sel = gate_selections(by_id[iid])
        props += sel["properties"]
        parity += sel["parity"] + ([GPB_SELECTIONS[iid]] if iid in GPB_SELECTIONS else [])
        keys += [k for k in item_key_ids(by_id[iid]) if k not in support["blocked"]]
    if props:
        gates.append('make properties K="' + " or ".join(dict.fromkeys(props)) + '"')
    if keys:
        uniq = list(dict.fromkeys(keys))
        gates.append(f"make answer-keys ID={','.join(uniq)}  # {len(uniq)} keys named by merged items must pass")
    if parity:
        gates.append('make parity K="' + " or ".join(f"({p})" for p in dict.fromkeys(parity)) + '"')
    if screen_ready and any(by_id[i]["kind"] in ("screen", "journey") for i in level_items):
        gates.append("make e2e SPEC=frontend/e2e/projects/screens.spec.ts")
    return gates


def integration_items(lv: dict, edges) -> set[str]:
    return {iid for iid, n in lv["placed"].items()
            for dep, kind, _r in edges.get(iid, []) if kind == "contract" and dep in lv["placed"] and lv["placed"][dep] != n}


def summarise_levels(levels, by_id, edges) -> tuple[list[int], set[str]]:
    minutes = []
    horizon: set[str] = set()
    total = 0
    for lv in levels:
        items_lv = {i for l in lv["lanes"] for i in l["items"]}
        e2e = any(by_id[i]["kind"] in ("screen", "journey") for i in items_lv)
        m = max(l["minutes"] for l in lv["lanes"]) + MERGE_MIN + (MERGE_MIN_E2E if e2e else 0) + \
            INTEGRATION_MERGE_MIN * len(integration_items(lv, edges))
        minutes.append(m)
        total += m
        if total <= HORIZON_MIN:
            horizon |= items_lv
    return minutes, horizon


def build_plan(items, in_scope, deferred, done, edges, why, levels, support, variants) -> dict:
    by_id = {d["id"]: d for d in items}
    plan_levels = []
    merged: set[str] = set(done)
    total = 0
    integration = []
    minutes, horizon = summarise_levels(levels, by_id, edges)
    for li, lv in enumerate(levels, start=1):
        order = sorted(range(len(lv["lanes"])), key=lambda n: (
            MERGE_PRIORITY.index(lv["lanes"][n]["family"]) if lv["lanes"][n]["family"] in MERGE_PRIORITY else 50,
            1 if lv["lanes"][n]["family"] == "web" else 0, lv["lanes"][n]["family"]))
        lanes_out = []
        level_items: set[str] = set()
        for rank, n in enumerate(order, start=1):
            lane = lv["lanes"][n]
            lane_id = f"L{li}-{rank}"
            fam = lane["family"]
            phases = list(dict.fromkeys(by_id[i]["phase"] for i in lane["items"]))
            name = FAMILY_NAMES.get(fam) if fam in ("mig", "eng-alloc", "eng-mod", "eng-rec", "eng-post", "eng-keys") \
                else f"{'Frontend' if fam == 'web' else 'Platform'}: {', '.join(phases)}"
            if lane["adds_migrations"] and fam != "mig":
                name = f"Schema chain ({', '.join(phases)}): the only lane adding Alembic revisions this level"
            batches = []
            for bi, b in enumerate(batches_for(lane["items"], by_id), start=1):
                notes = []
                for iid in b:
                    for dep, kind, reason in edges.get(iid, []):
                        if kind == "contract" and dep in lv["placed"] and lv["placed"][dep] != n:
                            notes.append(f"{iid} integration-after-merge: codes against the contract of {dep} "
                                         f"({reason.replace('verified: ', '')})")
                            integration.append({"item": iid, "consumes": dep, "level": f"L{li}"})
                    if by_id[iid]["adds_migration"]:
                        notes.append(f"{iid} adds a revision (make revision ITEM={iid})")
                    ks = support["items"].get(iid)
                    if ks and ks["blocked"]:
                        blockers = sorted({x for v in ks["blocked"].values() for x in v})
                        notes.append(f"{iid} partial: {ks['runnable']} of {ks['keys']} named keys runnable; the rest "
                                     f"wait for deferred {', '.join(blockers)}; tick only when every key passes")
                batches.append({"id": f"{lane_id}-B{bi}", "items": b, "minutes": sum(by_id[i]["cost"] for i in b),
                                "notes": "; ".join(notes)})
            lanes_out.append({"id": lane_id, "name": name, "family": fam, "minutes": lane["minutes"],
                              "adds_migrations": lane["adds_migrations"],
                              "file_scope": sorted(f for f in lane["files"] if f not in HOTSPOTS),
                              "shared_hotspots": sorted(f for f in lane["files"] if f in HOTSPOTS),
                              "batches": batches})
            level_items |= set(lane["items"])
        merged |= level_items
        merged_open = sorted(merged - done, key=lambda i: by_id[i]["order"])
        gates = level_gates(merged_open, level_items, by_id, support, "WEB-11" in merged)
        total += minutes[li - 1]
        plan_levels.append({"id": f"L{li}", "estimate_minutes": minutes[li - 1], "cumulative_hours": round(total / 60, 1),
                            "lanes": lanes_out, "merge_order": [l["id"] for l in lanes_out], "merge_gates": gates})
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "python3 docs/build-spec/sprint/plan_tools.py all",
        "source": {"build_spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(), "items": len(items),
                   "done": len(done)},
        "parameters": {"level_box_minutes": LEVEL_BOX, "batch_box_minutes": BATCH_BOX, "batch_max_items": BATCH_MAX_ITEMS,
                       "max_lanes": MAX_LANES, "max_migration_lanes": MAX_MIGRATION_LANES, "merge_minutes": MERGE_MIN,
                       "merge_e2e_minutes": MERGE_MIN_E2E, "cost_minutes": COST, "cost_overrides": COST_OVERRIDES},
        "done": sorted(done, key=lambda i: by_id[i]["order"]),
        "levels": plan_levels,
        "estimate_hours": round(total / 60, 1),
        "horizon_9h": {"levels_complete": sum(1 for lv in plan_levels if lv["cumulative_hours"] <= HORIZON_MIN / 60),
                       "items_merged": sorted(horizon, key=lambda i: by_id[i]["order"])},
        "in_scope": sorted(in_scope, key=lambda i: by_id[i]["order"]),
        "deferred": sorted(deferred, key=lambda i: by_id[i]["order"]),
        "deferred_notes": {k: {"capability": v[0], "note": v[1]} for k, v in DEFERRED_NOTES.items() if k in deferred},
        "root_exclusions": ROOT_EXCLUSIONS,
        "integration_after_merge": integration,
        "answer_key_support": {"families": support["families"], "items": support["items"]},
        "variants": variants,
        "release_gate": release_gate(items, in_scope, support),
    }


def release_gate(items, in_scope, support) -> dict:
    by_id = {d["id"]: d for d in items}
    props = []
    for iid in sorted(in_scope, key=lambda i: by_id[i]["order"]):
        props += gate_selections(by_id[iid])["properties"]
    not_full = {k: v for k, v in support["families"].items() if v["runnable"] < v["active"]}
    return {
        "tree": "git status --porcelain empty after the last merge commit on main",
        "commands": [
            "make openapi && git diff --exit-code docs/api/openapi.json frontend/src/lib/api/schema.d.ts",
            "make ci",
            "make test-pg",
            'make properties K="' + " or ".join(dict.fromkeys(props)) + '"',
            f"make answer-keys ID=<answer_keys.runnable_engine_runner_ids>  # {len(support['supported_ids'])} keys",
            'make parity K="not point_in_time_equivalence"  # 121 of 122 cases',
            "make e2e SPEC=frontend/e2e/projects/screens.spec.ts",
            "make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts  # SUP-RC-SMOKE once the supervisor appends it",
        ],
        "answer_keys": {"runnable_engine_runner_ids": support["supported_ids"], "count": len(support["supported_ids"]),
                        "families_not_fully_runnable": not_full, "blocked_keys": support["blocked"]},
        "golden": {"kinds_green": {"initial_allocation": 16, "pob_position": 17, "contract_position": 50,
                                   "cumulative_catchup": 10, "legacy_probe": 4, "journal_entry_totals": 24},
                   "cases": 121, "not_green": {"point_in_time_equivalence": "GPB-3 deferred (LMG-4, SNP-1 to SNP-3)"}},
        "e2e": {"screens_spec": "every screens.spec.ts row of the in-scope screen items passes with no serious or critical "
                                "axe violation, both themes read against SCREENS",
                "smoke": "SUP-RC-SMOKE (SPRINT-1.0rc.md section 7.3)",
                "not_green": ["J-01 (RPS-23, RPS-24 deferred)", "J-02 to J-19, J-22, J-24 to J-26 (DMO)",
                              "J-20, J-21 (LMG)", "J-23 (CLO-27)"]},
        "supervisor_verification": [
            "docker build of the three deploy/docker Dockerfiles and docker compose -f deploy/compose.yaml config, by hand "
            "(DEP-5 scripts deferred)",
            "multi-role browser QA of the rc screens as maya, priya, marcus and robert (G12)",
        ],
    }


# --------------------------------------------------------------------------------------------------
# Variants (estimates only; the emitted plan is the compliant one)
# --------------------------------------------------------------------------------------------------
def variant(items, done, dropped, max_mig_lanes, contracts) -> dict:
    by_id = {d["id"]: d for d in items}
    edges = all_edges(items, done, dropped, contracts)
    scope, _why = technical_closure(items, edges, done)
    levels = schedule(items, scope, edges, done, max_mig_lanes)
    minutes, horizon = summarise_levels(levels, by_id, edges)
    compact = [[{"items": l["items"], "adds_migrations": l["adds_migrations"], "minutes": l["minutes"]} for l in lv["lanes"]]
               for lv in levels]
    return {"in_scope": len(scope), "migration_items": sum(1 for i in scope if by_id[i]["adds_migration"]),
            "levels": len(levels), "estimate_hours": round(sum(minutes) / 60, 1),
            "level_hours": [round(m / 60, 1) for m in minutes], "items_merged_by_9h": len(horizon),
            "integration_items": sum(len(integration_items(lv, edges)) for lv in levels), "scope": scope,
            "levels_compact": compact, "scheduler": SCHEDULER_USED["name"]}


def variants(items, done, base_scope: set[str]) -> list[dict]:
    dropped_b = {(a, b) for a, b, _ in RULING_R_RC_1}
    base_c = set(API_SCREEN_CONTRACTS)
    compute_c = base_c | COMPUTE_CONTRACTS
    out = []
    for vid, desc, dropped, mig, contracts in [
        ("V-0", "plan as emitted: one migration lane per level; screens code against 04 API schemas", set(), 1, base_c),
        ("V-A", "two migration lanes per level; the merge step re-parents the second lane's revisions onto the first "
                "(down_revision edit and renumber) and runs test_single_head and test_upgrade_downgrade_upgrade",
         set(), 2, base_c),
        ("V-B", "supervisor descoping ruling R-RC-1: captures of seeded close history, drawers of unbuilt commands and "
                "worlds built on deferred commands move to post-rc", dropped_b, 1, base_c),
        ("V-C", "platform consumers of engine functions and compute outputs code against ENGINE_SPEC §0.5 with fakes "
                "(integration-after-merge); number-asserting tests go green only in the merge gate", set(), 1, compute_c),
        ("V-ABC", "V-A, V-B and V-C together", dropped_b, 2, compute_c),
    ]:
        v = variant(items, done, dropped, mig, contracts)
        removed = sorted(base_scope - v["scope"], key=lambda i: next(d["order"] for d in items if d["id"] == i))
        out.append({"id": vid, "description": desc, "in_scope": v["in_scope"], "migration_items": v["migration_items"],
                    "levels": v["levels"], "estimate_hours": v["estimate_hours"], "level_hours": v["level_hours"],
                    "items_merged_by_9h": v["items_merged_by_9h"], "integration_after_merge_items": v["integration_items"],
                    "items_moved_to_post_rc": removed, "scheduler": v["scheduler"], "levels_compact": v["levels_compact"]})
    return out


# --------------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------------
def check_plan(plan: dict, items: list[dict], edges, done: set[str]) -> list[str]:
    errors: list[str] = []
    by_id = {d["id"]: d for d in items}
    all_ids = set(by_id)
    in_scope, deferred = set(plan["in_scope"]), set(plan["deferred"])
    max_mig = plan["parameters"]["max_migration_lanes"]
    if in_scope & deferred:
        errors.append(f"in_scope and deferred overlap: {sorted(in_scope & deferred)}")
    if (in_scope | deferred | done) != all_ids:
        errors.append(f"coverage gap: {sorted(all_ids - in_scope - deferred - done)[:10]}")
    if in_scope & done:
        errors.append(f"done items in scope: {sorted(in_scope & done)}")
    if plan["source"]["build_spec_sha256"] != hashlib.sha256(SPEC.read_bytes()).hexdigest():
        print("WARNING BUILD_SPEC.md changed since plan.json was generated; rerun plan_tools.py all")
    position: dict[str, tuple[int, str, int]] = {}
    notes_by_item: dict[str, str] = {}
    for li, lv in enumerate(plan["levels"]):
        if len(lv["lanes"]) > MAX_LANES:
            errors.append(f"{lv['id']}: {len(lv['lanes'])} lanes")
        mig = [l["id"] for l in lv["lanes"] if l["adds_migrations"]]
        if len(mig) > max_mig:
            errors.append(f"{lv['id']}: {len(mig)} lanes add migrations: {mig}")
        if sorted(lv["merge_order"]) != sorted(l["id"] for l in lv["lanes"]):
            errors.append(f"{lv['id']}: merge_order does not list every lane")
        for lane in lv["lanes"]:
            k, real_mig = 0, False
            for b in lane["batches"]:
                if not 1 <= len(b["items"]) <= BATCH_MAX_ITEMS:
                    errors.append(f"{b['id']}: {len(b['items'])} items")
                for iid in b["items"]:
                    if iid in position:
                        errors.append(f"{iid} scheduled twice")
                    position[iid] = (li, lane["id"], k)
                    notes_by_item[iid] = b["notes"]
                    k += 1
                    real_mig = real_mig or by_id[iid]["adds_migration"]
            if real_mig != lane["adds_migrations"]:
                errors.append(f"{lane['id']}: adds_migrations flag {lane['adds_migrations']} but items say {real_mig}")
        for a in range(len(lv["lanes"])):
            for b2 in range(a + 1, len(lv["lanes"])):
                hit = overlaps(set(lv["lanes"][a]["file_scope"]), set(lv["lanes"][b2]["file_scope"]))
                if hit:
                    errors.append(f"{lv['id']}: file scope overlap {lv['lanes'][a]['id']} / {lv['lanes'][b2]['id']}: "
                                  f"{sorted(hit)[:5]}")
    if set(position) != in_scope:
        errors.append(f"scheduled set differs from in_scope: missing {sorted(in_scope - set(position))[:10]}, "
                      f"extra {sorted(set(position) - in_scope)[:10]}")
    for iid, (li, lane_id, k) in position.items():
        for dep, kind, reason in edges.get(iid, []):
            if dep in done:
                continue
            if dep not in in_scope:
                errors.append(f"{iid} depends on deferred {dep} ({kind}: {reason[:90]})")
                continue
            dl, dlane, dk = position[dep]
            if dl < li:
                continue
            if dl > li:
                errors.append(f"{iid} (L{li + 1}) before its dependency {dep} (L{dl + 1})")
            elif dlane == lane_id:
                if dk > k:
                    errors.append(f"{iid} precedes {dep} inside lane {lane_id}")
            elif kind == "hard":
                errors.append(f"{iid} and hard dependency {dep} in different lanes of L{li + 1}")
            elif "integration-after-merge" not in notes_by_item.get(iid, ""):
                errors.append(f"{iid}: contract dependency {dep} in another lane without an integration note")
    return errors


# --------------------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------------------
def md(s: str) -> str:
    return s.replace("|", "/")


def tables(plan: dict, items, why) -> str:
    by_id = {d["id"]: d for d in items}
    out = ["### Scope table\n", "| Id | Title | Kind | Min | Why in scope (first reason) |", "|---|---|---|---:|---|"]
    for iid in plan["in_scope"]:
        d = by_id[iid]
        reason = md(why.get(iid, ["?"])[0].replace("verified: ", ""))
        out.append(f"| {iid} | {md(d['title'])} | {d['kind']} | {d['cost']} | {reason[:160]} |")
    out += ["\n### Deferred table\n", "| Id | Title | Capability | Reason |", "|---|---|---|---|"]
    for iid in plan["deferred"]:
        d = by_id[iid]
        note = plan["deferred_notes"].get(iid)
        if note:
            cap, reason = note["capability"], note["note"]
        elif d["phase"] == "GATE":
            cap, reason = "none", "phase checkpoint; needs every item of its phase"
        else:
            cap, reason = "none", "not required by the rc capabilities"
        out.append(f"| {iid} | {md(d['title'])} | {cap} | {md(reason)} |")
    out.append("\n### Levels\n")
    for lv in plan["levels"]:
        out.append(f"\n#### {lv['id']}: about {round(lv['estimate_minutes'] / 60, 1)} h "
                   f"(cumulative {lv['cumulative_hours']} h)\n")
        out += ["| Lane | Name | Adds migrations | Batches: items (minutes) | Notes |", "|---|---|---|---|---|"]
        for lane in lv["lanes"]:
            bl = "<br>".join(f"{b['id'].split('-')[-1]}: {', '.join(b['items'])} ({b['minutes']})" for b in lane["batches"])
            notes = "<br>".join(md(b["notes"]) for b in lane["batches"] if b["notes"])
            out.append(f"| {lane['id']} | {lane['name']} | {'yes' if lane['adds_migrations'] else 'no'} | {bl} | {notes} |")
        out.append(f"\nMerge order: {' → '.join(lv['merge_order'])}\n\nMerge gates:\n")
        for g in lv["merge_gates"]:
            out.append(f"- `{g}`" if len(g) < 300 else f"- `{g[:280]} …` (full selection in plan.json)")
    out += ["\n### Answer-key support by family\n", "| Family | Active | Runnable | Blocked by |", "|---|---:|---:|---|"]
    for fam, v in plan["answer_key_support"]["families"].items():
        out.append(f"| {fam} | {v['active']} | {v['runnable']} | {', '.join(v['blocked_by']) or 'none'} |")
    out += ["\n### Variants\n", "| Variant | Description | In scope | Migration items | Levels | Hours | Merged by 9 h | "
            "Moved to post-rc |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for v in plan["variants"]:
        out.append(f"| {v['id']} | {md(v['description'])} | {v['in_scope']} | {v['migration_items']} | {v['levels']} | "
                   f"{v['estimate_hours']} | {v['items_merged_by_9h']} | {', '.join(v['items_moved_to_post_rc']) or 'none'} |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "all"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    items = parse_items()
    by_id = {d["id"]: d for d in items}
    done = done_ids(items)
    edges = all_edges(items, done)
    in_scope, why = technical_closure(items, edges, done)
    deferred = set(by_id) - done - in_scope
    declared = declared_closure(items, [r for r in MVP_ROOTS if r not in ROOT_EXCLUSIONS]) - done
    extra = sorted(in_scope - set(MVP_ROOTS), key=lambda i: by_id[i]["order"])
    if cmd in ("closure", "all"):
        print(f"items {len(items)}; done {len(done)}; open {len(items) - len(done)}; declared-prerequisite closure "
              f"{len(declared)}; technical closure {len(in_scope)} ({sum(by_id[i]['adds_migration'] for i in in_scope)} "
              f"add revisions); deferred {len(deferred)}")
        print(f"forced prerequisites beyond the brief ({len(extra)}): {', '.join(extra)}")
        if cmd == "closure":
            for iid in sorted(in_scope, key=lambda i: by_id[i]["order"]):
                print(f"{iid:8s} {by_id[iid]['kind']:9s} {why[iid][0][:150]}")
        (SCRATCH / "closure.json").write_text(json.dumps({i: why[i] for i in sorted(in_scope)}, indent=1))
    support = key_support(items, in_scope, done)
    if cmd in ("keys", "all"):
        print(f"answer keys runnable with in-scope stages: {len(support['supported_ids'])} engine-runner ids; "
              f"blocked {len(support['blocked'])}")
        if cmd == "keys":
            for fam, v in support["families"].items():
                print(f"  {fam:5s} {v['runnable']:3d} of {v['active']:3d} blocked by {v['blocked_by']}")
            for iid, v in support["items"].items():
                print(f"  {iid}: {v['runnable']} of {v['keys']}")
            return 0
    if cmd == "check":
        plan = json.loads(PLAN_JSON.read_text())
        errors = check_plan(plan, items, edges, done)
        for e in errors:
            print(f"ERROR {e}")
        print("check OK" if not errors else f"check FAILED ({len(errors)} errors)")
        return 1 if errors else 0
    if cmd == "tables":
        plan = json.loads(PLAN_JSON.read_text())
        (SCRATCH / "tables.md").write_text(tables(plan, items, why))
        return 0
    if cmd in ("all", "schedule"):
        levels = schedule(items, in_scope, edges, done)
        vs = variants(items, done, in_scope) if cmd == "all" else []
        plan = build_plan(items, in_scope, deferred, done, edges, why, levels, support, vs)
        errors = check_plan(plan, items, edges, done)
        for e in errors:
            print(f"ERROR {e}")
        print(f"levels {len(plan['levels'])}; estimate {plan['estimate_hours']} h; lanes per level "
              f"{[len(l['lanes']) for l in plan['levels']]}; level hours "
              f"{[round(l['estimate_minutes'] / 60, 1) for l in plan['levels']]}; merged by 9 h "
              f"{len(plan['horizon_9h']['items_merged'])}")
        for v in vs:
            print(f"  {v['id']}: scope {v['in_scope']}, migrations {v['migration_items']}, levels {v['levels']}, "
                  f"{v['estimate_hours']} h, merged by 9 h {v['items_merged_by_9h']}, moved {len(v['items_moved_to_post_rc'])}")
        if cmd == "all":
            PLAN_JSON.write_text(json.dumps(plan, indent=1) + "\n")
            generated = tables(plan, items, why)
            (SCRATCH / "tables.md").write_text(generated)
            print(f"wrote {PLAN_JSON.relative_to(ROOT)} and {(SCRATCH / 'tables.md').relative_to(ROOT)}")
            doc = OUT_DIR / "SPRINT-1.0rc.md"
            begin, end = "<!-- generated by plan_tools.py: begin -->", "<!-- generated by plan_tools.py: end -->"
            if doc.exists():
                text = doc.read_text(encoding="utf-8")
                if begin in text and end in text:
                    head, rest = text.split(begin, 1)
                    doc.write_text(head + begin + "\n\n" + generated + "\n" + end + rest.split(end, 1)[1], encoding="utf-8")
                    print(f"refreshed the generated block of {doc.relative_to(ROOT)}")
        print("check OK" if not errors else f"check FAILED ({len(errors)} errors)")
        return 1 if errors else 0
    print(f"unknown command {cmd}; use all, closure, keys, check or tables")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
