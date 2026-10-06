# VC113-CAND109-EVIDENCE — before / after of the draft correction (preparation only)

Lane F-CTR, slice VC113-CAND109-DRAFT. **Preparation only: the patch was applied to the worktree for measurement and reversed; the lane source at head `0812a6eb` is unchanged; nothing is marked approved; no original expectation changed.** Procedure (as instructed): `git apply --check` → apply in the worktree → focused stage-10 / VC-CHK-113 checks → `git apply -R` → `git status` clean (tracked files identical to HEAD; the new test file removed) → forward `git apply --check` on the clean tree OK. No `git checkout` / `restore`; no database; no broad suite.

## 1. Setup and statuses (measured; real `date` stamps, PDT, 2026-09-20)

| Step | Tree | Time | Exit | Result |
|---|---|---|---|---|
| Focused stage-10 tests incl. the 5 new candidate tests (fail-first) | unpatched 0812a6eb + new test file | 07:39:55 | 1 | 5 failed (the five new tests), 146 passed |
| VC-CHK-113 key (`run_engine` + `assert_checkpoints`) | unpatched | 07:39 | 0 (diagnostic completion) | 7 mismatches (§2 "before") |
| Draft patch applied; ruff format / check; mypy `--strict backend/erev_engine` | patched | 07:53 | 0 | ruff clean; mypy "no issues found in 145 source files" |
| Focused stage-10 + stage-14 tests | patched | 07:53:10 | 0 | 340 passed (incl. the 5 new tests and the 2 moved share-based expectations) |
| Focused stage-10 + stage-14 tests after the Codex 1438 extensions (same-period two-addition trace / replay / customer-consideration check; negative-exact zero-posted portion) | patched | 08:01:05 | 0 | 341 passed |
| `git apply -R`; `git status`; `git diff --quiet HEAD -- backend`; forward `git apply --check` (second cycle) | reversed | 08:02 | 0 | backend tracked files identical to HEAD; new test file removed; patch applies cleanly |
| Codex 1510 revision (aggregate over the component nodes via `rl.concession_total.v1`): kernel formula tests (`test_trace`, `test_stage_registry`, `test_formula_ownership`) + stage 10 + stage 14 | patched (109 revised) | 08:17:11 | 0 | 352 passed; mypy strict engine clean |
| VC-CHK-113 key (109 revised) | patched | 08:17 | 1 | 3 mismatches remain: October 400.00 vs 364.98; December CONTRACT_LIABILITY 21002 absent / 2100 unexpected |
| 109 + 109b (narrowed to the override step): the same test set | patched | 08:22:15 | 0 | 354 passed |
| VC-CHK-113 key (109 + 109b) | patched | 08:22 | 1 | **1 mismatch**: October only; December generated intent Dr REFUND_LIABILITY 2110 / Cr CONTRACT_LIABILITY 21002 60.00 |
| 21 focused refund-component keys (109 only, then 109 + 109b) | patched | 08:20 / 08:23 | 1 / 1 | 19 passed, 2 failed in both (MOD-CHK-115 pre-existing; VC-CHK-113) — no other key moves |
| `git apply -R` 109b then 109; `git status`; `git diff --quiet HEAD -- backend`; forward checks of both | reversed | 08:24 | 0 | backend identical to HEAD; both new test files removed; both patches apply on the clean tree |
| 109 + 109b revised to exact encoded owner identity (Codex 1517): the same test set | patched | 08:28:08 | 0 | 355 passed; VC-CHK-113 1 mismatch (October); December intent Cr CONTRACT_LIABILITY 21002, zero 2100 lines |
| `git apply -R` 109b then 109; verification; forward checks (third cycle) | reversed | 08:29 | 0 | backend identical to HEAD; new test files removed; both patches apply on the clean tree |
| VC-CHK-113 key | patched | 07:53 | 1 (3 mismatches remain) | §2 "after" |
| 13 focused concession / refund keys (`support.answer_keys.report`, `ID=`) | patched | 07:54:28 | 1 | 13 selected; 11 passed, 2 failed — MOD-CHK-115 (4 mismatches, pre-existing, in the main baseline) and VC-CHK-113 (3) |
| `git apply -R`; `git status`; `git diff --quiet` | reversed | 07:54 | 0 | tracked files identical to HEAD; new test file removed; only `drafts/` untracked |
| The same 13 keys | clean tree | 07:54:44 | 1 | 13 selected; 11 passed, 2 failed — MOD-CHK-115 (the SAME 4 mismatch lines, diff empty) and VC-CHK-113 (7) |
| `git apply --check` (forward) | clean tree | 07:54 | 0 | applies cleanly |

Focused key ids: MOD-LEGACY-POBVC-GT11, MOD-CHK-115, RND-CHK-003C, RND-CHK-003C-USD-NEGATIVE-CREDIT-MEMO-APPORTIONMENT, VC-CHK-101-S3-EX23-CASEB, VC-CHK-110, VC-D91-01-TARGETED-THEN-UNTARGETED-CHANGE, JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY, FX-CHK-084-A-REFUND-LIABILITY-REMEASURED, STP1-S1-25-7B-TERMINATION-REFUND-RELEASE, SFC-S3-EX26, RET-CHK-116, VC-CHK-113-TC-POBVC-16. Logs under `.run/F-CTR/cand109/` (scratch). Fixture hash of the key unchanged: `138684b1e6218db9b3e75311c7d5502c4886c491d3bc2a7ee3fa714efbc8a334`.

## 2. VC-CHK-113-TC-POBVC-16 — the original checkpoints, before and after

**Before (7 mismatches, unchanged from the diagnostic):**
```
- full-delivery obligation Contract 2/POB #2 billed_cum: expected 400.00, actual 364.98
- after-concession balance Contract 2@US01 FY2023-P11 contract_liability: expected 0.00, actual 60.00
- after-concession balance Contract 2@US01 FY2023-P11 refund_liability: expected 60.00, actual 0.00
- after-concession subledger FY2023-P11 US01 REFUND_LIABILITY/2110 cr: expected 60.00, actual <absent>
- after-concession subledger FY2023-P11 US01 CONTRACT_LIABILITY/21002 line: expected <absent>, actual cr 60.00; functional cr 60.00
- after-credit-memo subledger FY2023-P12 US01 CONTRACT_LIABILITY/21002 cr: expected 60.00, actual <absent>
- after-credit-memo subledger FY2023-P12 US01 REFUND_LIABILITY/2110 dr: expected 60.00, actual <absent>
```
**After (3 mismatches):**
```
- full-delivery obligation Contract 2/POB #2 billed_cum: expected 400.00, actual 364.98
- after-credit-memo subledger FY2023-P12 US01 CONTRACT_LIABILITY/21002 cr: expected 60.00, actual <absent>
- after-credit-memo subledger FY2023-P12 US01 CONTRACT_LIABILITY/2100 line: expected <absent>, actual cr 60.00; functional cr 60.00
```

| Checkpoint | Measure | Expected (original) | Before | After |
|---|---|---|---|---|
| October (full-delivery) | contract billed / revenue / TP | 1,100.00 / 1,100.00 / 1,100.00 | same | same (unchanged) |
| October | POB #2 `billed_cum` | 400.00 | 364.98 | 364.98 — the separate question, untouched |
| October | RL / CL | 0 / 0 | 0 / 0 | 0 / 0 |
| November (after-concession) | contract billed / revenue / TP | 1,100.00 / 1,040.00 / 1,040.00 | same | same |
| November | RL | **60.00** | 0 | **60.00** (`refund_liability_txn` 6000) — restored |
| November | CL | **0.00** | 60.00 | **0** — restored |
| November | P11 entry | Dr REVENUE 5002 60 / Cr REFUND_LIABILITY 2110 60 (JET-05c) | Dr REVENUE 5002 60 / Cr CONTRACT_LIABILITY 21002 60 | Dr REVENUE 5002 60 / Cr REFUND_LIABILITY 2110 60 — restored |
| December (after-credit-memo) | contract billed / revenue | 1,040.00 / 1,040.00 | same | same |
| December | RL / CL balance | 0 / 0 | 0 / 0 (no release; CL drained by the ERP memo) | 0 / 0 (release posted) |
| December | P12 entry | Dr REFUND_LIABILITY 2110 60 / Cr CONTRACT_LIABILITY **21002** 60 (JET-04b) | absent | Dr REFUND_LIABILITY 2110 60 / Cr CONTRACT_LIABILITY **2100** 60 — the release is restored in role and amount; the CL leg lands on the default account, not POB #2's override (SPEC-DRAFT §4 item 1) |

Stage-10 intermediates after: `refund_components[POB #2]` = 60 / 6000 EMBEDDED (unchanged); the CONCESSION component is now `…/CONCESSION/Contract 2/EV-000015/Contract 2/POB %232`, created_on **2023-11-15**, created_ref `contract_event` **EV-000015** (the November `ESTIMATE_CHANGED`), consumptions `[(EV-000016, 2023-12-10, 6000)]` — the October 31 unreferenced 100.00 credit (EV-000014) consumes nothing; no refund-liability target exists before FY2023-P11 (the former P05–P09 60.00 artefact is gone). `_concession_event` still returns the May 31 amendment when called directly — it is now the fallback only.

## 3. Focused tests (CPU; new module `test_s10_cand109_dated_concession_origin.py`, 6 tests)

| Test | Shape | Before | After |
|---|---|---|---|
| VC-CHK-113 shape | May 31 MODIFICATION segment; Nov 15 targeted DISCOUNT adds 60.00 (one dated addition); unreferenced Oct 31 credit 100.00; Dec 10 credit 60.00 | fails: component dated May 31 | component created 2023-11-15 from EV-000015 with `created_order`; October consumes 0; December consumes 6000; `concession_total` 0 at Oct 31, 6000 at Nov 30 |
| Multiple additions on one POB with a credit between them | March 3,000 + September 4,000 (quota 7,000); May credit 5,000; October credit 5,000 | fails: one 7,000 component | two components (Mar 3,000 / Sep 4,000); May consumes 3,000 from March only; October consumes 4,000 from September; `concession_total` 0 / 3,000 / 7,000 at Feb / Apr / Sep ends |
| Earlier same-day credit under the defined event ordering | addition Jun 10 record_seq 5; memos Jun 10 record_seq 4 and 6 | fails | record_seq 4 consumes nothing, record_seq 6 consumes 2,500; without `orders` the date rule alone applies (documented) |
| Fallback without conserving dated history | no history / history 6,000 ≠ quota 7,000 | fails (attribute) | aggregate component from `_concession_event` (May 31), `created_order` None — unchanged behaviour |
| Conservation | two additions + a zero-posted addition (a real event); then a negative-exact (−1/300), zero-posted deferred-cent portion | fails | Σ component amounts = quota 7,000; `check_history` still satisfied in both shapes; neither zero-posted portion creates a component; nothing dropped or re-rounded (Codex 1438 (c)) |
| Same-period two additions (Codex 1438 (a)) | Codex's two-concession fixture: 15 Aug 20,000.00 + 30 Aug 30,000.00 in FY2026-P08, book-level run | fails in the naive design (duplicate node id) | two distinct component nodes (20,000.00 / 30,000.00), one aggregate node 50,000.00 listing both component keys, no P07 node, every node replays, the element cites the portion node and never the aggregate, `aggregate_node` names the aggregate, JET-05c credits REFUND_LIABILITY 50,000.00 once in P08, every intent balanced |

Existing stage-10 / stage-14 tests after the patch: 340 passed (341 with the same-period test), with two share-based expectations moved as annotated in the patch (SPEC-DRAFT §4 item 3): cross-month P07 aggregate node now exists at 20,000.00 (was asserted absent), mixed-producers P07 aggregate node 20,000.00 (was 50,000.00); P08 50,000.00 in both, the portion nodes, element values, cutoffs and equity credits unchanged.

## 4. Preserved rules (checked)

Exact / posted conservation (`check_history` untouched and re-run); per-currency measurement (components in transaction currency, S10-R-13, unchanged); contract scoping (`_consume` still matches `component.contract_key == memo.contract_key`); obligation attribution (component `subject_key` = the receiving obligation; JET-04b netting by component key unchanged; JET-05c per obligation); KIND_ORDER unchanged; no new finding code; no migration; no answer key, oracle or S10-R-26 text changed by the patch (the spec wording is a separate draft, §SPEC-DRAFT).

## 5. Qualifications (Codex packet 1510)

The after-patch diagnostic proves GENERATED posting intents on the in-memory engine path (November RL 60 / CL 0; November Dr 5002 / Cr 2110; December Dr 2110 / Cr 2100 for 60 under 109, Cr 21002 under 109 + 109b) — not database postings. Under 109 alone three original mismatches remain (October 400.00 vs 364.98; December 21002 absent / 2100 unexpected); under 109 + 109b one remains (October). The 340 / 341 / 352 / 354-test logs are attributed producer evidence, not key acceptance; the draft stays unapplied and unmerged; approval pending with Ray / the G12 owner.

## 6. Labels and the patch base after the lane's landing (Codex packet production-20260920-1541 item 3; PRODUCTION-VC113-CAND109B-EVIDENCE-SUCCESSOR-66c077ff.md, SHA256 a53fdc683e6839eaf5f88c640b5867cdfcffb20dcbb0ebddd807ab31a18af664; manifest aa0f7f02045286cb46e3dae763331fa59d68dbbc53c8c391b66e4fcb4cf5f607; 15 artifacts)

The 21-key 19 / 2 table of the 109b proposal was measured for r109b2 (the first, broader variant) and is labelled historical there; the revised exact-identity 109b was RE-MEASURED on the merged base c0de02a1 (21 selected; 19 passed, 2 failed — MOD-CHK-115 identical 4 pre-existing lines; VC-CHK-113 1, October only). Every posting figure in this file is a GENERATED posting intent on the in-memory engine path, not a persisted journal. The diagnostic script's exit 1 with the original key retained means the original key still fails as authored (7 mismatches unpatched; 3 under 109; 1 under 109 + 109b), never acceptance. Test counts are attributed producer evidence, not key acceptance.

**Patch base.** After the final re-merge (5fa2555e, main d3166d0a; on main as 30e9709f / b179900b) the committed 109 patch (66c077ff / 01a96737) no longer applied to the lane tree: ENG-T1F's landing added formula ids beside `rl.concession.v1` in `s10_billing_balances/__init__.py`, so that one hunk's context drifted (every other hunk applied; checked per file). It applied with one line of context (`git apply -C1`); the 109b patch applied unchanged. Both patches were regenerated against the merged base c0de02a1 — 109: 960 lines, 7 files; 109b: 284 lines, 3 files (`intents.py`, the new `test_s14_cand109b_component_owner_accounts.py`, and the `group_into_entries` dimension case appended to `test_s14_entries.py`) — both apply cleanly on the clean merged tree; the lane source is unchanged. Statuses on the ported tree (2026-09-20 09:11 PDT, then reversed, tree identical to HEAD): kernel formula tests + stage 10 + 14 356 passed; mypy strict engine clean; VC-CHK-113 1 mismatch (October), zero 2100 lines in December.
