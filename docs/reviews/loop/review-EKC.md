# EKC review: phase 02, items EKC-1 to EKC-12 and remediation items EKC-7a to EKC-7c

| Field | Value |
|---|---|
| Reviewed commit | `94e54d7` (EKC-12 backfill), worktree `~/dev/erev-rv/ekc`. The loop ran the GATE-EKC gates at `44a24b9`, which differs only in `PROGRESS.md` |
| Main HEAD at synthesis | `48c790a` (PLF-1; PLF-2 in flight). Two cited paths changed after `94e54d7`: `backend/tests/conftest.py` gained a `keyring` fixture, and `backend/erev_api/db/lint.py` changed check (a). Neither change touches a cited line, so every finding below is still current |
| Date | 2026-09-12 |
| Inputs | Setup baseline; four lenses (numerics, conformance, gates-remediation, security-purity); two verifier passes per lens (reproduction and authority); the lead's own reproduction of ER-N-01, ER-C-03 and ER-S-06 |
| Remediation | `~/dev/erev-rv/reports/ekc/SUPERVISOR-ITEM.md`: SUP-EKC-1, SUP-EKC-2 and SUP-EKC-3 |

## Result

**Phase EKC meets its BUILD_SPEC acceptance, and no finding is P1. The money kernel is numerically exact against an independent oracle. Six P2 findings remain:**

- **Engine helper (1):** `first_open_period_on_or_after` skips `closing` periods, so stage 08 would post late events into the wrong period (ER-N-01). This is latent until ENB-11 calls the helper.
- **Answer-key runner (2):** no engine that follows the spec can pass these keys: `RET-CHK-029-S3-EX22`, `RET-CHK-060-S3-EX22-REVISED` and `SFC-S3-EX26-RETURN-RIGHT` (ER-C-01), or `ALC-CHK-032-S4-EX34-CASEC-REJECTED` (ER-C-02). AKS-2 and AKS-3 require these keys and forbid key edits, so the loop could "fix" the engine against S09-R-23 or CV-15.
- **Gates (2):**
  - `make answer-keys` prints `OK` when the selection holds only withdrawn keys, and a selection that mixes active and withdrawn keys fails at collection (ER-G-01).
  - `make properties` prints `OK` with skipped property tests (ER-G-03).
- **Property (1):** P4 exempts any cumulative value that sits on a bound, so a schedule that posts everything in month 1 passes. ENC-10 copies the same wording (ER-N-02).

There are 8 P3 findings. Three findings are dropped (ER-N-03, ER-S-04, ER-S-05), and two parts of ER-S-03 are dropped. ER-C-04 and ER-S-01 are merged into ER-G-01.

**FND remediation:** all 23 FND finding ids of EKC-7a to EKC-7c are implemented, and their named tests pass.
- 20 of them fail again when the defect is reintroduced.
- FR-B-03, FR-B-04 and FR-M-06 carry built-in negative controls but were not mutation-probed.
- Residual gaps sit next to FR-G-01 (ER-G-04), FR-G-02 (ER-G-03, ER-G-05) and FR-C-02/FR-G-03 (ER-S-03).

**Placement:** put SUP-EKC-1 to SUP-EKC-3 directly after GATE-EKC in `docs/BUILD_SPEC.md`, and copy them into `docs/build-spec/12-engine.md` (BSF-D-01). The loop then takes them as soon as PLF-2 is ticked. SUP-EKC-1 must land before ENB-11 and ENC-10, and SUP-EKC-2 and SUP-EKC-3 before END-9.

## Baseline (setup reviewer, `setup/baseline.md`)

**Every GATE-EKC gate is green in the review environment, and the counts equal the loop's recorded evidence. `make answer-keys` fails closed, as B3-BS2-06 requires.**

| Gate | Result |
|---|---|
| `make setup` twice | exit 0 both runs; porcelain empty; DB-14 lint 0 findings |
| `make ci` | exit 0, 82 s. Backend 394 passed, 0 failed, 0 skipped; Vitest 197 passed; mypy clean over 64 files; `build_sha` 94e54d7, `worktree_dirty` false |
| `make test-pg` | 29 passed, 0 failed, 0 skipped |
| `make properties` (unfiltered) | 3 passed; the `thorough` profile is confirmed (`max_examples=1000`) |
| `make answer-keys` (unfiltered) | Fails closed, exit 2. All 234 files validate (232 active, 2 withdrawn). The 227 engine keys fail naming BUILD_SPEC END-9, and the 5 platform keys fail naming PRP-1. Coverage reports 0 gaps: List A 49/49, B 46/46, C 76/76, AK 50/50, AK-FAM 9/9, families 28/28. The unfiltered gate cannot pass vacuously at this commit |
| `erev controls-report --tags-only` | exit 0; 0 tagged tests |
| Exit-criteria modules | `test_engine_purity` 15; CHK-001 to CHK-007 (10 tests); `test_loader_discovery` 4; `test_loader_validation` 6; `test_coverage` 3; `test_runner_engine` 7; `test_assert_checkpoints` 7 |
| Probe `make answer-keys ID=POS-S9-PRESENTATION-EX38-CASEA` | exit 0 and `OK answer-keys`, with 0 keys run (setup F-1, now ER-G-01) |

After all runs, `git status --porcelain` was empty, no reviewer process remained, and ports 8192, 5272, 8193 and 5271 were free.

Several reviewers saw another agent's temporary probe edits in `money.py`, `guards.py`, `RND-CHK-001.yaml` and `runners.py`. Every cited line was re-read with `git show 94e54d7:`. The gates-remediation lens re-ran the affected first-batch probes (C-akeys, M-schedule-*, M-trace-vacuous, M-wrong-book), and only the reruns count.

## Confirmed findings

### P2

#### ER-N-01: `first_open_period_on_or_after` skips `closing` periods that S08-R-08 posts into

- **Where:**
  - `backend/erev_engine/dates.py:40` sets `OPEN_STATES = frozenset({"open", "reopened"})`, and `dates.py:205` filters on it.
  - `backend/tests/engine/kernel/test_dates.py:67-73` asserts that `closing` is skipped.
- **Contract:**
  - ENGINE_SPEC S08-R-08 (`ENGINE_SPEC:1549`): when the effective period is closed, the posting period is "the first later period whose state is `open`, `closing` or `reopened`".
  - The §8.2 `assign_posting_period` pseudo-code (`:1522-1530`) uses this helper's result directly.
  - 05 RCP-04 (`05:483`), CV-13 (`ENGINE_SPEC:176`) and dev-guide `POSTABLE_STATES` (`dev-guide:1025`; DB-07) all treat `closing` as postable.
  - Only DG-KRN-TIME-04 (`dev-guide:1039`), the platform `posting_period` rule, narrows the later period to `open` or `reopened`. BUILD_SPEC §2 (`:76-78`) ranks ENGINE_SPEC above the dev-guide for accounting behaviour.
  - POLICIES ALG-09 step 3 says "first open period" informally. Its step 2 also says "open" for the containing period, where S08-R-08 admits `closing`.
- **Reproduction** (re-run by the lead):
  - Command: `cd ~/dev/erev-rv/ekc/backend && PYTHONPATH=. .venv/bin/python ~/dev/erev-rv/reports/ekc/numerics/repro/first_open_closing.py`.
  - Output: `engine first_open_period_on_or_after(P01.end + 1 day) -> FY2023-P03`, where S08-R-08 expects `FY2023-P02 (state closing)`.
  - Output: `P01 closed, P02 closing, rest future -> engine None ; S08-R-08 expects FY2023-P02`.
  - The EKC-4 acceptance case (P01 `closed`, P02 `open`) cannot tell the two rules apart. The ENB-11 tests use only the `closed`, `permanently_locked`, `future` and `open` states, so the defect would reach stage 08 unseen.
- **Impact:** once ENB-11 calls the helper, a late event whose next period is `closing` posts one period late. When every later postable period is `closing`, it posts nothing. Period amounts and the out-of-period register would both be wrong. This is latent today, because the helper has no caller.
- **Fix:** SUP-EKC-1 (ruling on SPEC-Q-79).

#### ER-C-01: the DG-AK-54 basis identity sums the returns-adjusted `allocated_amount`, so correct outputs of the returns keys are reported as mismatches

- **Where:** `backend/tests/support/answer_keys/runners.py:1621-1637`. `identities()` sums obligation `allocated_amount` and requires the sum to equal the node `tp_allocation_basis:<group>:-`.
- **Contract:**
  - DG-AK-54 (`dev-guide:2128`) and DG-ENG-05 (`:1828`): Σ `a_posted` = `allocation_basis`.
  - ENGINE_SPEC S04-R-02 (`ENGINE_SPEC:1030`): the basis is total − expected_returns − consideration_payable, and the memo members are ≤ 0.
  - ENGINE_SPEC_B S09-R-23 (`ENGINE_SPEC_B:412`): `allocated_amount` = a_posted − round(r × (Y + E)).
  - ENGINE_SPEC rev 1.2, B3 decision 2 (`ENGINE_SPEC:21`): the memo equals −Σ round(r_p × (Y_p + E_p)).
  - Σ `allocated_amount` therefore equals the basis plus `expected_returns_amount`. V1 is already checked separately at `:1638-1646`.
- **Reproduction:**
  - Command: `cd ~/dev/erev-rv/ekc && PYTHONDONTWRITEBYTECODE=1 EREV_ENV=test PYTHONPATH=backend/tests backend/.venv/bin/python ~/dev/erev-rv/reports/ekc/conformance/probe_answer_key_runner.py`, probe [1].
  - Probe [1] builds the spec-correct `RET-CHK-029-S3-EX22` `end-of-february` book: TP 9700.00, ER −300.00, CP 0, `L1-PROD` allocated 9700.00 and basis node 10000.00.
  - Output: `DG-AK-54 sum allocated_amount = tp_allocation_basis: expected 10000.00, actual 9700.00`.
  - On a clean copy, the verifier also gets `10000.00 vs 9600.00` for RET-CHK-060 and `100.00 vs 0.00` for SFC-S3-EX26-RETURN-RIGHT. The corrected identity gives 10000.00, 10000.00 and 100.00.
  - `test_implicit_assertions` covers only RND-CHK-001, where expected returns are 0.
- **Impact:** AKS-3 requires all three keys (`BUILD_SPEC:5399-5400`) and forbids key edits. To pass them, the loop could lower the basis node, which breaks S04-R-02 and the ENA test `test_ex_04_g_expected_returns`. Or it could drop the S09-R-23 adjustment, which breaks V1.
- **Fix:** SUP-EKC-2 (ruling on SPEC-Q-112).

#### ER-C-02: the engine runner puts `expect_problem` items into the bundle and never compares `ERROR` exception rows

- **Where:**
  - `runners.py:356-373` and `:1041-1084` add every item with `seq ≤ after_seq` to the bundle.
  - `run_engine` (`:182-188`) does not catch `EngineError`.
  - `exceptions()` (`:1931-1942`) reads only `output.diagnostics`, which CV-41 and ENGINE_SPEC §0.5 limit to `WARNING` and `INFO`.
- **Contract:**
  - dev-guide §9.5.5 `expect_problem` (`dev-guide:2069`): "the step must fail with this problem code or engine code and leave state unchanged; the timeline continues".
  - §9.5.6 `exceptions` (`:2085`): `ERROR` maps to `BLOCKING`.
  - ENGINE_SPEC CV-15 (`:434`) and CV-41 (`:480`); `RESIDUAL_REJECTED` is `ERROR` under S05-R-12 (`:508`).
  - SPEC-Q-108 ("`expect_problem` items enter the bundle") contradicts §9.5.5.
- **Reproduction:**
  - Command: probe [2] of the same script.
  - Key `ALC-CHK-032-S4-EX34-CASEC-REJECTED`: seq 2 `CONTRACT_ACTIVATED` carries `expect_problem: {code: RESIDUAL_REJECTED}`. Checkpoint `activation-refused` expects `DRAFT`, TP 105.00 and the exceptions row `{RESIDUAL_REJECTED, ERROR, C-EX34, L4-D}`.
  - Output: `bundle events: [(1, CONTRACT_BOOKED), (2, CONTRACT_ACTIVATED)]`.
  - A stub `compute` that raises as CV-15 requires makes `run_engine` propagate the error (`run_engine raised EngineError RESIDUAL_REJECTED -> no checkpoint comparison`). A stub that returns the DRAFT book instead still fails on the `ERROR` row (`actual <absent>`).
- **Impact:** no engine that follows the spec can pass this key, and AKS-2 requires 40 of 40. It is the only engine key with `expect_problem` (lead grep).
- **Fix:** SUP-EKC-2 (ruling on SPEC-Q-108).

#### ER-G-01 (merges ER-C-04 and ER-S-01; setup F-1): `make answer-keys` mishandles withdrawn ids

A selection that holds only withdrawn keys passes vacuously, and a selection that mixes active and withdrawn keys can never pass.

- **Where:**
  - `backend/tests/support/answer_keys/report.py:186-188` selects with `include_withdrawn=True`.
  - `:198-199` runs pytest only `if active:`.
  - `:218` skips the coverage check on filtered runs.
  - `:232` exits 0 when `failures` is empty.
  - `backend/tests/answer_keys/test_answer_keys.py:18` parametrises over `load_all(**selection_from_env())`. That call selects active keys only and raises for a withdrawn id (`loader.py:1653`).
- **Contract:**
  - GK-05 (`BUILD_SPEC:104`): "Every selected key passes".
  - G4 (`dev-guide:2500`) and DG-MK-answer-keys step 2 (`:524`).
  - DG-AK-13 (`:1986`): withdrawn keys are "validated and reported, never run".
  - DG-AK-42 (`:2176`) and SPEC-Q-106.
  - The review brief: a gate must not pass vacuously.
- **Reproduction:**
  - `make answer-keys ID=POS-S9-PRESENTATION-EX38-CASEA` prints `answer-keys counts: 1 selected; 0 passed, 0 failed, 0 not run, 1 withdrawn; 1 not approved`, then `OK answer-keys`, and exits 0. `report.json` has `exit_code` 0, `failures` [] and no coverage member. Evidence: `gates-remediation/gate-reports/MK-answer-keys-withdrawn-only/report.json` and `setup/gate-reports/probe-answer-keys-ID_POS-S9-PRESENTATION-EX38-CASEA.json`.
  - `make answer-keys ID=RND-CHK-001,POS-S9-PRESENTATION-EX38-CASEA` exits 2 with `ValueError: ids POS-S9-PRESENTATION-EX38-CASEA select no answer key` at collection, and RND-CHK-001 is `not_run`. This mixed selection will still fail after END-9.
  - Controls: `ID=NO-SUCH-KEY` and `REQ=REQ-ZZZ-999` both fail.
- **Severity:** the conformance lens and one authority verifier rated this P3, because no BUILD_SPEC gate names a withdrawn id today. (The AKS item at `:5429` validates the withdrawn POS keys without naming them.) The lead keeps P2 for two reasons: the brief treats a gate that can pass vacuously as a defect, and the collection error makes a legitimate filtered G4 run impossible to pass.
- **Fix:** SUP-EKC-2.

#### ER-G-03: `make properties` (G5) reports `OK` with skipped property tests

- **Where:**
  - `Makefile:227-231`: the `properties` recipe passes `--counts-junit` and no skipped-test check.
  - `scripts/gate_report.py:112-114` accepts `--fail-on-skipped` only for a `--junit` label, and `:164-171` checks only those labels.
  - `backend/tests/support/markers.py` catches only the skip, skipif and xfail markers. It never sees a runtime `pytest.skip` or `importorskip`.
- **Contract:**
  - DG-TST-09 (`dev-guide:1939`): `pytest.skip` is forbidden in property tests.
  - G5 (`:2501`): all properties pass under `thorough`.
  - The D-78 gate-integrity ruling applies DG-TST-09 to all five markers. EKC-7a added fail-on-skipped to `test-pg` only.
- **Reproduction:**
  - Scratch `backend/tests/properties/test_zz_*.py` files with a runtime `pytest.skip` and an `importorskip` (removed afterwards; porcelain clean):
    - `make properties K=zz_verify_repro` prints `0 passed, 0 failed, 2 skipped`, then `OK properties`, and exits 0;
    - unfiltered, it prints `3 passed, 0 failed, 2 skipped`, then `OK properties`.
  - A synthetic JUnit file passed through `--counts-junit` gives `OK properties`. `--fail-on-skipped properties` gives `names 'properties', which no --junit option labels`.
  - Contrast: the same runtime skip under pg gives `FAIL test-pg: 1 skipped test in backend (DG-TST-09)`.
- **Impact:** P5 to P14 depend on stages that are not built yet, so skipping at runtime is a realistic shortcut, and G5 would not catch it.
- **Fix:** SUP-EKC-3.

#### ER-N-02: PROP:P4 accepts schedules that post the whole allocation in period 1, or only at completion

- **Where:** `backend/tests/properties/test_prop_p04_schedule_bounds.py:42-43` skips the half-unit check whenever `value in (0, allocation)`, whether or not that bound actually binds.
- **Contract:**
  - dev-guide §9.7 P4 (`dev-guide:2416`): "cumulative lies within half a minor unit of exact", with no exemption.
  - BUILD_SPEC EKC-7 (`:1058`) and ENC-10 (`:4690`) add "unless C_t sits on a bound". An exemption is needed only where DG-KRN-MONEY-03 (`:992`) actually clamps.
  - BUILD_SPEC §2, row 83: BUILD_SPEC never changes behaviour that a higher document fixes.
- **Reproduction:**
  - Command: `cd ~/dev/erev-rv/ekc/backend && PYTHONPATH=. .venv/bin/python ~/dev/erev-rv/reports/ekc/numerics/repro/p04_front_loaded.py`.
  - Output: `C1 front-loaded: P4 assertions PASS; months 1-3 = [3500000, 0, 0], month 24 = 0` and `C2 back-loaded: P4 assertions PASS; months 1-3 = [0, 0, 0], month 24 = 3500000`. CHK-004 expects 1,458.33 / 1,458.34 / 1,458.33.
  - Mutation matrix (`numerics/mutants/matrix.txt`; verifier plugin at 100 and 1,000 examples): C1 and C2 pass P2 to P4. The kernel unit tests kill both (14 failures each).
  - The binding-only exemption held on the real code over 132,973 adversarial cases, with 0 violations.
- **Severity:** both verifiers call this borderline P3, since no number is wrong at this commit. It stays P2 because ENC-10 carries the same wording into the stage-09 schedule property, and no per-schedule CHK unit test backs that property.
- **Evidence correction:** mutant C8 survives because the strategy rarely produces a case near the bound, not because of the exemption.
- **Fix:** SUP-EKC-1 (the ruling amends the EKC-7 and ENC-10 wording).

### P3

#### ER-C-03: `MID_MONTH` `time_fraction` returns 1 on and after the term end, where ALG-11 gives less than 1

- **Defect:** ALG-11 reaches 1 only at the end of the counted period that contains e. Catch-ups effective in that window use the wrong fraction.
- **Where:** `backend/erev_engine/progress.py:112-113` returns 1 before `_mid_month` (`:144-154`) runs. `test_time_fraction_edges` uses only the CHK-140 term, where both rules give 1.
- **Contract:** POLICIES ALG-11 §2.12 (`POLICIES:1057`):
  - f(d) = (counted periods whose last day ≤ d) ÷ m, "at any date";
  - catch-ups use f at the effective date;
  - rule 2: progress steps on period ends.

  BUILD_SPEC §2 ranks POLICIES above EKC-4's "on and after the end 1".
- **Evidence:**
  - Lead re-run: `a f(2026-02-10)= 1`, `b f(2026-01-10)= 1`, `c f(2027-01-15)= 1` (while `f(2027-01-14)= 12/13`). ALG-11 gives 0, 0 and 12/13.
  - A literal ALG-11 implementation differs from the engine on 18, 21 and 16 days for CHK-145 (a), (b) and (c), and never at a period end.
- **Fix:** SUP-EKC-1 (ruling on SPEC-Q-78).

#### ER-C-05: checkpoint assertions pass when the checkpoint book is missing, or when a non-LEGACY book has no `contract_version`

- **Where:**
  - `runners.py:1565-1571` skips an output that lacks the checkpoint book.
  - `:1621` skips the V1, basis and DB-17 checks whenever `contract_version` is `None`.
- **Contract:**
  - 05 RCP-11 (`05:666`): every enabled book is computed.
  - ENGINE_SPEC §0.5 (`:413`): `contract_version` is `None` only for LEGACY.
  - DG-AK-54 applies per group and book.
- **Evidence:**
  - Probe [3]: `ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION` checkpoint `cutover-no-postings` with `OutputBundle(books=())` gives `mismatches = 0`.
  - A sweep over 540 engine checkpoints finds 2 that pass with no book: that one and `IFRS-SW04…::asc606-april`.
  - With `contract_version=None`, the DG-AK-54 mismatches fall from 6 to 0.
- **Fix:** SUP-EKC-3.

#### ER-G-02: nine `assert_checkpoints` comparison paths have no test that can fail

Lead adjudication: the lens rated this P2. The affected paths:

- schedule rows in `amounts` form;
- the period-row amount and quantity;
- the trace value;
- book selection;
- a checkpoint with no run;
- `proposed_treatments`;
- leftover exception findings;
- diagnostics of other books.

- **Where:**
  - `runners.py:1374, 1568, 1780, 1790, 1799, 1808, 1828, 1941, 1965`.
  - `test_assert_checkpoints.py:128-133` builds books with `schedules=()` and `proposals=()`, no diagnostics, one book, and a run for every checkpoint.
- **Contract:** BUILD_SPEC header §5.3 SZ-03 ("no untested code"); DG-AK-55 (`dev-guide:2129`); the §9.5.6 members (`:2085, 2096-2098`).
- **Evidence:**
  - The verifier's in-memory mutation plugin (`verify-gates-remediation-repro/logs/mut/summary.txt`) leaves each of M1 to M9 at `27 passed`; the controls C1 and C2 give `1 failed`.
  - Corpus exposure: 30 keys with schedule rows, 24 with modifications, 6 with exceptions, 6 with trace nodes, and 10 checkpoint books other than ASC606.
- **Severity:** the code is correct today, and no gate runs these paths until END-9. The fix adds tests only, so P3 fits.
- **Fix:** SUP-EKC-3 (tests only).

#### ER-G-04: `make ci` can still be narrowed through internal Makefile variables and print `OK ci`

- **Where:** `Makefile:50-52` derive `PYTEST_PATHS`, `PYTEST_MARKERS` and `RUN_VITEST`. `:209` refuses only `TESTS`, `K` and `FRONTEND`.
- **Contract:** DG-MK-ci, "Variables: none" (`dev-guide:516`); the D-78 gate-integrity ruling.
- **Evidence:**
  - `make ci PYTEST_PATHS=backend/tests/engine/kernel/test_money.py` prints `ci counts: backend 9 passed … vitest 197 passed`, then `OK ci`, and exits 0 with `worktree_dirty` false (`gates-remediation/gate-reports/MK-ci-PYTEST_PATHS-only-bypass/report.json`).
  - A dry run shows `PYTEST_MARKERS` can be overridden the same way.
- **Severity:** P3, because the report's `command` field records the override, so the run stays traceable.
- **Fix:** SUP-EKC-3.

#### ER-G-05: two regression guards do not fail when their defect returns

Part (a) is the root conftest wiring of `markers.check`; part (b) is the active-key filter in `coverage`.

- **Where:**
  - (a) `backend/tests/conftest.py:122`. The tests in `test_controls_report.py` use their own `GATE_CONFTEST` (`:34-44`, `:126-136`), and `:178-188` asserts only exit 0.
  - (b) `loader.py:1757`. `test_coverage.py` only removes keys, never withdraws one.
- **Contract:** BUILD_SPEC EKC-7a (`:1090`); DG-TST-07 and DG-TST-09; DG-AK-33 (`dev-guide:2171`).
- **Evidence:**
  - (a) With the hook neutralised, both DG-TST tests give `2 passed`, and a scratch pg module marked `@pytest.mark.skip` runs `1 skipped` with exit 0. G6 `--fail-on-skipped` would still catch a skipped pg test, but the parity, answer_key and property markers have no second guard.
  - (b) When `coverage` counts withdrawn keys, `unit/answer_keys` still gives `27 passed`, even though `report.main` passes all 234 keys to `coverage`.
- **Fix:** SUP-EKC-3.

#### ER-S-02 (P2 lowered to P3): `registry-seed` keeps only the first code of compound `Appr` cells

- **Defect:** seven POLs lose a second approval code.
- **Where:** `backend/erev_api/registry/seed.py:483` uses `re.match`, which anchors at the start of the cell. Affected rows in the generated `policies.py`: POL-015, 029, 051, 105, 170, 210 and 244.
- **Contract:**
  - 04 T-PLT-31 (`04:1522`, one CHECK literal) and catalogue rule 1 (`04:1529`): `approval_code` comes from `Appr`.
  - POLICIES §0.6 (`:107`).
  - The `seed.py` docstring: "Any other cell raises SeedError".
- **Evidence:** `verify-security-purity-authority/er_s_02_appr.out` lists 11 multi-code cells. The 7 "X and Y" rows lose a code; for example, POL-105 "EST and JDG" seeds EST.
- **Why lowered:**
  - POL-015 (levels T, P), POL-105 (T) and POL-170 (T, E) cannot be overridden at level C or O (T-CON-23). So `test_jdg_override_needs_judgement` (`BUILD_SPEC:5969`) and PRD:279 are unaffected.
  - POL-244 keeps JDG.
  - No specified consumer reads EST or OVR from `approval_code`.
- **Fix:** not carried. Storing two approvals needs a T-PLT-31 ruling (recommendation below).

#### ER-S-03 (narrowed): the DG-ARC-02 scanner misses dynamic imports through builtins and clock reads on other owners

- **Defect:** the scanner misses dynamic imports through `eval`, `exec`, `compile` and `__builtins__`. It also misses clock reads made on anything other than `datetime`, `date` or their import aliases.
- **Where:** `backend/tests/architecture/test_engine_purity.py:54-59` lists only four bare-name calls, and `:93-108` checks the owner of a clock read. The module docstring (`:5-6`) promises that "dynamic imports through builtins" are findings.
- **Contract:** DG-ENG-01 (`dev-guide:1824`): no environment, filesystem or clock access; BUILD_SPEC XR-20 (`:174`); DG-ARC-02 (`:1763`) as extended by SPEC-Q-49 and D-78.
- **Evidence:**
  - `verify-security-purity-authority/er_s_03_purity.out` shows 0 findings for `eval(…__import__('os')…)`, `exec`, `compile`, `__builtins__['__import__']`, `getattr(datetime,'now')()`, `as_of.today()`, `datetime.min.now()` and `clock = datetime; clock.now()`.
  - No engine module violates the rule today. A lead grep finds no `.now` or `.today` attribute and no bare `eval`, `exec` or `compile` in `erev_engine`.
- **Fix:** SUP-EKC-1.

#### ER-S-06: `guards.no_floats` walks sets in hash order, so the `FLOAT_DETECTED` detail path changes with `PYTHONHASHSEED`

- **Where:** `backend/erev_engine/guards.py:53-54`.
- **Contract:** DG-ENG-02 (`dev-guide:1825`); ENGINE_SPEC CV-23 (`:445`). `canonical.py:73` and `rules.py:221` do sort sets.
- **Evidence:** lead re-run: `seed 1 {'path': '$[0]'}`, `seed 3 {'path': '$[1]'}`, `seed 10 {'path': '$[1]'}`. The defect is latent: `no_floats` has no caller until END-9, and `bundle.py` declares no set fields.
- **Fix:** SUP-EKC-1.

**Recommendation for ER-S-02 (supervisor ruling; not carried by any item).** One of two options:
- let T-PLT-31 store compound approvals (an additional-approvals member), and make the generator parse "X and Y" and "X; OVR at …" cells; or
- rule that `approval_code` holds the strictest code, and keep the full cell in the generated module.

Only after that ruling should `build_spec` raise `SeedError` for an unparsed remainder. Raising today would break 11 rows.

## Dropped findings

| Id | Reason |
|---|---|
| ER-N-03 | **Both verifiers refuted it.** dev-guide §9.7 P2 and P3, and EKC-7 (`BUILD_SPEC:1056-1058`), specify neither the tie order nor the tie direction, and P4 is specified as ≤ 1/2; the tests implement that text. DG-KRN-MONEY-02 and -03 leave tie order and half-up rounding to unit tests, and those tests kill every listed mutant (`numerics/mutants/logs/*.unit.log`): L1 `test_chk_002`; L3 `test_chk_003d`; L4 `test_chk_001`, `003a`, `003c`; L7 `003b`, `003d`, `002`; C5 and C6 `test_cumulative_posted`. The strengthened properties in `numerics/mutants/strengthened/` are optional hardening |
| ER-S-04 | **Lead adjudication: refuted.** DG-AK-31 (`dev-guide:2169`) limits implicit resolvers so that no value changes type "by accident", and it requires duplicate keys to raise. The EKC-8 acceptance holds: `12.30` stays a string, a literal duplicate raises, and a plain `<<` stays a string. The bypasses need deliberate `!!float`, `!!int`, `!!timestamp` or `!!merge` tags. The corpus is frozen (D-77) and holds 0 `!!` tags and 0 merge keys (lead grep), and DG-AK-32 rejects float money. This is optional hardening only |
| ER-S-05 | **Lead adjudication: refuted.** DG-AK-30 and DG-AK-01 say nothing about symlinks, and the corpus holds 0 symlinks (lead `find`). There is no trust boundary: the corpus is committed repository content read by a local test harness. A skipped key cannot cause a vacuous pass: `test_discover_corpus` asserts 234 paths (`test_loader_discovery.py:55`), an `ID` naming a skipped key raises (SPEC-Q-106), and an unfiltered run reports coverage gaps |
| ER-S-03: the `json.loads` and `1 / 3` parts | No contract names them. `json` is on the DG-ARC-02 allow-list, true division is not listed, and a static scanner cannot tell `Fraction / int` from `int / int`. The runtime DG-ENG-03 `no_floats` guard and the trapped `FloatOperation` are the backstop |
| ER-C-04, ER-S-01 | Merged into ER-G-01: same defect, same reproduction |
| Setup F-2 | Below the bar. The fail-closed message wording differs from the B3-BS2-06 literal, but EKC-11 and EKC-12 require only that the message names `BUILD_SPEC END-9`, and it does |

## FND remediation verification (EKC-7a to EKC-7c)

**Method** (gates-remediation lens, `gates-remediation/results.jsonl`): each probe made one exact source edit that reintroduced an FND defect, ran the gate or named test, restored the original bytes, and confirmed that `git status --porcelain` was empty. Before probing, the control runs passed: EKC-7a unit tests 11, EKC-7b 10, EKC-7c 27, pg remediation tests 21.

| FND id | Item | Result | Evidence (probe → outcome) |
|---|---|---|---|
| FR-G-01 | EKC-7a | **Verified; residual gap ER-G-04** | R-G01-recipe-refuse-removed and R-G01-refusal-logic-removed go red. `make ci TESTS=`, `K=` and `FRONTEND=` each give `FAIL ci: TESTS, K and FRONTEND are not accepted (DG-MK-ci)`. `PYTEST_PATHS=` still bypasses the refusal |
| FR-G-02 | EKC-7a | **Verified for G6 and marker placement; residual gaps ER-G-03 and ER-G-05 (a)** | R-G02-recipe-fail-on-skipped-removed, R-G02-skip-logic-removed and R-G02-markers-skip-check-removed go red. A runtime-skipped pg test gives `FAIL test-pg: 1 skipped test in backend (DG-TST-09)`. With the root hook unwired, the tests still pass (2 passed) |
| FR-C-01 | EKC-7a | Verified | R-C01-engine-guard-disabled goes red; a real engine test that requests a database fixture exits 4 |
| FR-B-01 | EKC-7a | Verified | R-B01-readiness-env-port and R-B01-dispatch-on-source go red |
| FR-G-04 | EKC-7a | Verified | R-G04-missing-junit-ignored goes red; `make ci RUN_VITEST=` gives `FAIL ci: JUnit summary vitest missing` |
| FR-C-03 | EKC-7a | Verified | R-C03-port-hardcoded goes red |
| FR-B-03 | EKC-7a | Implemented; not mutation-probed | `Makefile:44` appends `erev_api.worker` through `$(wildcard …)`. `test_dg_mk_build_imports_worker_when_present` (`test_makefile_targets.py:372-386`) carries the stand-in negative control and passes |
| FR-B-04 | EKC-7a | Implemented; not mutation-probed | `test_registry_seed.py:25-37` writes under `tmp_path`, and `test_proc_sh.py:13` uses `probe-<pid>`. The baseline found no stray `.run/` files |
| FR-M-01 | EKC-7b | Verified | R-M01-apply-class-no-partition-trigger, R-M01-partitions-no-trigger and R-M01-lint-partition-check-removed go red, in both build orders |
| FR-S-01 | EKC-7b | Verified | R-S01-config-query-refusal-removed, R-S01-check-env-refusal-removed and R-S01-connect-database-guard-removed go red |
| FR-M-06 | EKC-7b | Implemented; not mutation-probed | `test_dg_env_13_allow_list_helpers_agree` (`test_db_urls.py:102-124`) compares the three helpers over six URLs, plus the shared pattern and parameter tuples, and passes |
| FR-C-04 | EKC-7b | Verified | R-C04-identity-rule-broadened goes red |
| FR-M-03 | EKC-7b | Verified | R-M03-objects-narrowed goes red. The first rule-narrowing probe had a syntax error; the corrected probe goes red |
| FR-C-02, FR-G-03 | EKC-7b | **Verified for the named alias forms; residual gap ER-S-03** | R-C02-asname-dropped goes red |
| FR-M-04 | EKC-7b | Verified | R-M04-runbook-reverted goes red |
| FR-S-04 | EKC-7c | Verified | R-S04-kms-no-aad, R-S04-kek-loaded-from-secret-manager and R-S04-fixed-split go red |
| FR-S-02 | EKC-7c | Verified | R-S02-hide-parameters-off and R-S02-exc-info-for-db-errors go red |
| FR-S-03 | EKC-7c | Verified | R-S03-local-secret-serves-master and R-S03-gcp-secret-serves-kek go red |
| FR-S-05 | EKC-7c | Verified | R-S05-unicode-digits goes red |
| FR-S-06 | EKC-7c | Verified | R-S06-nested-keys-kept, R-S06-first-word-redaction and R-S06-log-guard-flat go red |
| FR-S-07 | EKC-7c | Verified | R-S07-uvicorn-not-bridged goes red |
| FR-S-09 | EKC-7c | Verified | R-S09-wildcard-check-removed and R-S09-no-validation go red |

The lead diffed `conftest.py`, `db/lint.py`, `db/session.py` and `migration_ops.py`: no PLF-1 commit after `94e54d7` changes a remediated line.

## Spec-question rulings (loop calls shown wrong)

| SPEC-Q | Loop call | Ruling |
|---|---|---|
| SPEC-Q-79 | `first_open_period_on_or_after` returns the earliest period in state `open` or `reopened`, following DG-KRN-TIME-04. The question recorded only the argument-order conflict | **Wrong.** ENGINE_SPEC S08-R-08, 05 RCP-04, CV-13 and DB-07 include `closing`, and ENGINE_SPEC ranks above the dev-guide for accounting behaviour (BUILD_SPEC §2). **Ruling:** the engine helper searches `open`, `closing` and `reopened`. The later-period branch of DG-KRN-TIME-04 is amended to `POSTABLE_STATES`, so the platform `posting_period` agrees with RCP-04. SUP-EKC-1 applies the engine part; the supervisor edits the dev-guide |
| SPEC-Q-78 | f(d) = 1 for d ≥ e under every convention (EKC-4, "on and after the end 1") | **Wrong for `MID_MONTH`.** POLICIES ALG-11 defines f at any date and ranks above BUILD_SPEC. **Ruling:** `DAILY` and `MONTHLY_EVEN` keep the shortcut, which equals their formula. `MID_MONTH` evaluates ALG-11 at every d ≥ s. The EKC-4 `test_time_fraction_edges` wording is amended. Applied by SUP-EKC-1 |
| SPEC-Q-108 | "`expect_problem` items enter the bundle" | **Wrong.** dev-guide §9.5.5 requires the step to fail and leave state unchanged, and no higher-ranked source supports the call. **Ruling:** an item with `expect_problem` enters only the bundle of its own step, and that step must raise `EngineError` with that code. The item never enters a checkpoint bundle or a later bundle, and its CV-15 findings are that checkpoint's `ERROR` exception rows. Applied by SUP-EKC-2 |
| SPEC-Q-112 | DG-AK-54 basis: node `tp_allocation_basis:<group>:-`, checked for every book | **Incomplete, and the identity built on it is wrong.** **Ruling:** identity 1 compares the node with Σ obligation `allocated_amount` − `contract_version.expected_returns_amount`. Under S09-R-23 and the B3 memo decision, that equals Σ a_posted. V1 and DB-17 are unchanged. Applied by SUP-EKC-2 |
| SPEC-Q-106 (with SPEC-Q-113) | A filter value that selects no key raises; the driver runs pytest only over active keys | **Scope incomplete.** The driver and the test module select keys differently. A withdrawn id alone passes vacuously, and a withdrawn id mixed with active ids breaks collection. **Ruling:** selection runs over every key. Withdrawn keys are validated and reported but never collected, and a selection with no active key fails the run. Applied by SUP-EKC-2 |

### Supervisor rulings carried by the items

Proposed as D-79 "EKC review rulings". No spec question covered these:

- **P4:** a cumulative value is exempt from the half-unit bound only when the bound binds. This amends BUILD_SPEC EKC-7 (`:1058`) and ENC-10 `test_p04_stage09_schedules` (`:4690`). Applied by SUP-EKC-1.
- **DG-ARC-02** also forbids:
  - the bare calls `eval`, `exec`, `compile`, `globals`, `vars`, `breakpoint` and `input`;
  - the name `__builtins__`;
  - `now`, `today`, `utcnow`, `fromtimestamp` and `utcfromtimestamp` on any owner;
  - `getattr` of those names.

  Applied by SUP-EKC-1.
- **`no_floats`** iterates set members in a deterministic order (DG-ENG-02). Applied by SUP-EKC-1.
- **Answer-key assertions** require a `BookOutput` for every `BookInput`, and a `contract_version` for every book except LEGACY. Applied by SUP-EKC-3.
- **DG-TST-09 and G5** bind `make properties`, which fails on any skipped test. This extends D-78. Applied by SUP-EKC-3.
- **DG-MK-ci "Variables: none":** `make ci` refuses every command-line variable. This extends D-78. Applied by SUP-EKC-3.

## Observations below the finding bar

- **Numerics oracle (no defect).** A Fraction oracle that never imports `erev_engine` matched the engine with 0 mismatches over:
  - CHK-001 to CHK-007 (including CHK-003a to CHK-003d and every CHK-006 row), EX-00-A, CHK-140 to CHK-145, and the S04-R-12 month counts;
  - 20,000 random allocations and 20,000 rounding cases, 40% of them exact ties;
  - 22,000 schedules, 77,298 `time_fraction` evaluations and 5,000 month-end counts.

  The Decimal context has precision 38 and traps float operations. Scripts: `numerics/oracle.py`; output: `numerics/compare-output.txt`.
- **Engine-side conformance (no defect):**
  - canonical encoding DG-KRN-CAN-01 to DG-KRN-CAN-15 and the EX-14-A hash vector;
  - trace re-evaluation: a closed formula registry, an iterative DFS, and cycles that raise;
  - rule matching;
  - bundle hashing (CV-25, CV-26), with `known_at` excluded;
  - policy scope order (CV-17);
  - the 25 engine enumerations against 04 §3;
  - all 65 answer-key models forbid extra fields;
  - coverage counts that match `_coverage/ADJUDICATION.md` §1.
- **Watch item:** the module-level `_HANDLERS` dict in `erev_engine/stages/__init__.py`, under DG-ENG-08, once stages register handlers.
- **Registry migration:** revision 0003 seeds from the module at run time, so databases migrated before EKC-9 keep 147 rows until `make db-reset`. The loop recorded this as SPEC-Q-104.
- **POL-047:** its default fails its own value schema. This dates from FND-8 and matches the `SFC_RATE_MISSING` design.
- **Setup warnings:**
  - `PytestAssertRewriteWarning … anyio` appears inside `make lint`.
  - `npm ci` reports 2 moderate advisories: a vitest and `@vitest/mocker` path traversal. This belongs to the supervisor's `make audit-deps` run.
  - "234 not approved" is the corpus review state, reported as DG-AK-43 requires.
- **Worktree hygiene:** other agents' probe edits appeared briefly in shared source files. Every lens and verifier restored its own edits, and the final `git status --porcelain` is empty (lead check).
