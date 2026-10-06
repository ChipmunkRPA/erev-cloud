# P5: preparation slice — D-96 replay/validation state machine, frozen-dataset and attribution tests, SAR-13 policy and MET definitions

Lane record for the P5 **preparation** slice on `sprint/l12-p5` (worktree `~/dev/erev-wt/l12`, base main
`eb5546a`, branch created from that commit on the team-lead's signal, 2026-09-19). Dispatch: team-lead,
from `PRODUCTION-CRITICAL-PATH-AUDIT-b2c0062.md` entry 1 and `docs/reviews/loop/prod/lanes/P5.md`, split
explicitly from the P2-dependent integration hold. CPU-only phase: no database was created or read, no
server, no Docker, no cloud call, no DB gate stage, no chain, no gate slot. Binding text: 05 RCP-28,
RCP-28a, RCP-29, REL-06, SAR-13, MET-01 to MET-11; 04 T-CON-25, T-CON-26, T-PLT-43 to T-PLT-46, T-SL-11,
E-125 to E-130 (rev 1.13, rev pending this lane); dev-guide DG-ENG-07, DG-ENG-10, DG-KRN-JOB-12,
DG-KRN-APR-06, DG-CMD-10; 01-DECISIONS D-96 with its v4/v5 follow-up bullets; BUILD_SPEC SOP-3
(`docs/build-spec/11-foundation-platform.md`) and SOP-4.

Common terms (`.run/supervisor/d91/lane-dispatch-common.md`, all amendments): own worktree and `.env`
(DB names `erev_rv_l12_*`; ports verified unused across `~/dev/erev-wt/*/.env` and not listening; never
8190/5270; no value printed); scratch under `.run/p5/`; nothing killed; no push, rebase, reset, stash,
amend, clean or checkout of another branch; `make lint` (never bare ruff) as the commit guard; every
commit made inside `if make lint; then …; fi` and ending with the co-author line.

## Commits (`sprint/l12-p5`, `eb5546a..HEAD`)

| Commit | Files | Change | Gate evidence |
|---|---|---|---|
| `7e2eb4f` | `docs/dev-guide.md` (header, rev 1.18, DG-ENG-07), `docs/04-DATA_MODEL.md` (header, rev 1.19, §3.4 E-125 to E-130 rows + pending paragraph, T-CON-25 evidence encoding), `backend/erev_api/enums.py` (six StrEnums), `backend/tests/architecture/test_data_model_drift.py` (E-01..E-130) | Docs first: DG-ENG-07 adds the orchestration-only public module `upgrade`; 04 lifts E-125 to E-130 from the rev 1.13 pending paragraph into the enumeration table together with the code enums; T-CON-25 bytes defined as the type-tagged evidence encoding (see "Codec finding") | `make lint` OK; mypy strict both packages 0 issues; drift/registry/catalogue tests green |
| `2f19508` | `backend/erev_engine/upgrade.py` (new, ~430 lines), `backend/tests/engine/test_upgrade.py` (new, 14 tests) | Evidence codec (`encode_input`/`decode_input`, tagged `Decimal`/`date`/`datetime`; `encode_output`, `output_mapping`, `raw_digest`), `INPUT_TRANSFORMS` + `transform_chain` + `candidate_input`, `cv25_view` (asserted equal to `InputBundle.sha256`), `normalised_input_sha256`, `attribution_view`/`attribution_comparison`, `l1_view`/`l1_sha256`, `representation_diff` (M/P/T/R) | 14 passed; fail-first `.run/p5/logs/fail-first-upgrade-and-release-validation.txt` (ModuleNotFoundError on the base) |
| `06d1e58` | `backend/erev_api/domain/contracts/release_validation.py` (new), `backend/tests/unit/test_release_validation.py` (new, 14 tests) | Level derivation and per-tenant effective level; creation (BOOTSTRAP / BASELINE / PATCH / PENDING); RCP-29 population; orchestration state, accepted pointer, aggregation; `TRANSITIONS`, `enablement_transition`, `persist_admission`; `ExecutionToken`, `execution_lock_key`, `verification_write` over `VerificationStore` and `ExecutionLock` ports | 14 passed; same fail-first log |
| `0240304` | `backend/erev_api/domain/contracts/replay_verify.py` (new), `backend/erev_api/domain/contracts/upgrade_report.py` (new), `backend/tests/unit/test_replay_verify_decisions.py` (13), `backend/tests/unit/test_upgrade_processing.py` (8), `docs/04-DATA_MODEL.md` (§15.2 pending note, 1.19 row) | RCP-28a decision with the four T-CON-26 CHECKs in Python; per-portion processing (v5 rule), attribution labels, frozen dataset, report-from-bytes, approval content hash, as-of register | 21 passed; fail-first `.run/p5/logs/fail-first-replay-verify-and-upgrade-report.txt` |
| `c928755` | `backend/erev_api/auth/ratelimit.py` (additive), `backend/erev_api/metrics.py` (new; moved in the next commit), `backend/tests/unit/test_rate_limit_policy.py` (4), `backend/tests/unit/test_metric_definitions.py` (2) | SAR-13 request-limit policy (`request_limits`, `RequestRateLimiter`, `OPENAPI_RATE_LIMIT_LINE`); MET-01..11 definitions asserted equal to the 05 table; label safety | 6 passed; fail-first `.run/p5/logs/fail-first-ratelimit-metrics.txt` |
| `ae7b10b` | `backend/erev_api/controls/metrics.py` (moved from `erev_api/metrics.py`), `backend/tests/unit/test_metric_definitions.py` (import), this record (first version) | `test_dg_arc_01_detects_upward_import` classified a module directly under `erev_api/` as belonging to no DG-LAY-03 layer; the definitions live in the kernel package `controls` (release stamping, doctor), importable by the api route and the worker emitters alike without amending the DG-LAY-03 kernel list | architecture suite green; `make lint` |
| `bc41e59` | `backend/erev_api/controls/stamping.py` (new), `backend/erev_api/controls/validation_level.py` (new), `backend/erev_api/domain/contracts/release_prepare.py` (new), `backend/erev_api/domain/contracts/release_validation.py` (`semver_level` re-imported from the kernel), `backend/tests/unit/test_release_level_and_stamping.py` (3), `backend/tests/unit/test_release_prepare.py` (4) | The four items the team-lead ruled P5-owned (below): consumer stamping resolver, manifest `validation_level` + T-PLT-38 column contract + semver floor, preparation-artifact identity, `release prepare` plan / verified backfill / summary | 7 passed; architecture 95 passed; mypy 0; fail-first `.run/p5/logs/fail-first-level-stamping-prepare.txt`; `make lint` |
| `3a2a9bf` | this record | Ruling, sequencing prerequisite, counts, `.env` note | `make lint` |
| `934c55d` | `backend/erev_api/domain/contracts/upgrade_report.py` (`conservative_origins` derived inside the boundary), `backend/erev_api/controls/stamping.py` (WARN-class fallback line), `backend/tests/unit/test_upgrade_processing.py` (+1 test, three call sites), `backend/tests/unit/test_release_level_and_stamping.py`, `docs/04-DATA_MODEL.md` (T-CON-26 L2 classification rule; revision renumbered 1.18 → 1.19 against main's ENG-C5 1.18), `docs/dev-guide.md` (revision renumbered 1.16 → 1.18 against main's 1.17), this record | Team-lead rulings on returned questions (2), (3), (4) applied (below); Codex CPU-only review of the slice requested by the team-lead | tests + architecture green; `make lint` |
| `8f61a98` | `backend/erev_api/controls/validation_level.py` (`check_declaration` docstring), `docs/04-DATA_MODEL.md` (T-PLT-46 cross-reference), this record | Team-lead ruling (5): the semver floor at stamping is against the previous **global** release only; the per-tenant chain stays at T-PLT-43 creation | tests green; `make lint` |
| `a6d5477` | this record | Codex CPU-review target named `934c55d` | `make lint` |
| `efe4220` | this record | Codex closure of P5-PREP R1–R3 at `e0ea5aa` recorded (54/56, 36/37); the R2 authorization-reference qualification added to the integration prerequisites | `make lint` |
| `c43718b4` | (main merge) | `efe4220` merged to main by the team-lead; the branch fast-forwarded onto it for the lift slice | post-merge checks the team-lead's |
| `51fbcbf` | `docs/02-PRD.md` (rev 1.6: §5.5 ERR-51 row; header entry; log row), `docs/04-DATA_MODEL.md` (rev 1.20: §15.2 `release-validation-pending` row; the rev 1.13 pending paragraph replaced by the lifted note; header entry; log row; the truncated "1.20 … rows lifted; 1.18" header entry left by the c43718b4 merge repaired to "1.19 (…; T-CON-25 evidence encoding)" so header entries equal log rows 1.3–1.20) | Docs first for the D-96 (6) §15.2 lift (supervisor sequencing ruling 2026-09-19; docs lane's sidecar texts byte for byte; generator `.run/p5/patches/apply_lift_set.py --prd-rev 1.6 --dm-rev 1.20 --only docs`) | fail-first `.run/p5/logs/lift-fail-first-docs-only.txt`: on this docs-only tree both drift tests fail (`assert 48 == 47` in `test_dg_arc_09_problems_equal_15_2` and `test_dg_arc_13_err_rows_cover_slugs`); `make lint` OK |
| this commit | `backend/erev_api/problems.py` (`release-validation-pending` 503 "Release validation in progress"), `backend/tests/architecture/test_data_model_drift.py` (catalogue pin 47 → 48), `backend/tests/architecture/test_copy_catalogue_drift.py` (`len(slugs) == 48`; ERR range `range(1, 52)`), this record | The code half of the lift (`--only code` = the three-hunk `release-validation-pending-lift.patch`); the coupled set is now one main state once merged | pass `.run/p5/logs/lift-pass-code-applied.txt` (both drift tests, the 82-test gate set, the eight lane suites, `make typecheck`); `make lint` |
| `e0ea5aa` | `backend/erev_api/domain/contracts/release_prepare.py` (R1 one-to-one summary reconciliation, `PrepareSummaryError`, `PrepareSummary.missing` / `.refused`; R2 `prepare_release_baseline`; R3 book-population check, `BACKFILL_BOOK_POPULATION_MISMATCH`), `backend/erev_api/controls/validation_level.py` (R2 `PreparationRow`, `SAME_VERSION_REBUILD`, `check_declaration` build / preparation parameters), `backend/tests/unit/test_release_prepare.py` (+3 tests; one pre-existing assertion reclassified from `OUTPUT_DRIFTED` to the R3 refusal), this record | The three Codex P5-PREP corrections (section below) | fail-first `.run/p5/logs/p5-prep-r1-r3-fail-first.log` (probe `.run/p5/probes/p5_prep_r1_r3_probe.py` over pre-existing names: 8 fail / 2 controls pass on the `a6d5477` modules); pass `.run/p5/logs/p5-prep-r1-r3-pass.log` (10/10 probes; P5 files + architecture 140 passed); `mypy --strict backend/erev_engine backend/erev_api` 0 issues in 570 files; `make test` see `make-test-cpu-no-db.txt`; `make lint` |

Measured: the six test files of the first seven commits **57 passed** (`.run/p5/logs/pass-all-new.txt`)
and the two of `bc41e59` **7 passed** (`pass-level-stamping-prepare.txt`) — 64 new tests at `bc41e59`;
**68** after `934c55d` (+1) and the P5-PREP corrections (+3): `test_release_prepare` 7,
`test_release_level_and_stamping` 3, `test_release_validation` 16, `test_replay_verify_decisions` 13,
`test_upgrade_processing` 9, `test_rate_limit_policy` 4, `test_metric_definitions` 2, `test_upgrade` 14
(`p5-prep-r1-r3-pass.log`, with `tests/architecture`: 140 passed). `make test` on this CPU-only worktree
(`make-test-cpu-no-db.txt`): 1848 passed; the 945 errors and two of the three failures are the absent
test database (no DB stage was run; nothing projected), the third a stray top-level `.ruff_cache`
from a direct ruff invocation, removed;
`backend/tests/architecture` (72 tests, including `test_layers`) + `tests/unit/reports/test_catalogue.py`
green (`pass-architecture.txt`; the first run at `c928755` had the one layering failure fixed by the move);
`mypy --strict backend/erev_engine backend/erev_api` 0 issues; `make lint` OK three times
(`make-lint-1..3.txt`). Not run (CPU-only phase): `make ci`, `make test-pg`, `make properties`,
`make typecheck`'s `tsc` (no frontend change), the chain; nothing projected from them.

## What the slice delivers (all pure, DB-free, injected facts)

1. **Evidence codec (T-CON-25; D-96 (2), R1).** Codec finding: flat canonical JSON cannot distinguish
   `Decimal` / `date` / `datetime` scalars from strings inside untyped payload members, and stage 01
   converts only `Decimal` payload members to fractions — so a flat encoding could not be replayed
   faithfully. The evidence encoding tags those scalars; `decode_input(encode_input(b)) == b`, the decoded
   bundle's CV-25 hash equals the original, and `compute(decoded).sha256() == compute(original).sha256()`
   on the answer-key checkpoint `MOD-LEGACY-PROS-GT12 / end-june-after-prospective`. Output evidence is
   untagged `canonical_bytes(output)`, so `output_file_sha256 = output_sha256` for `AT_COMPUTATION` rows
   (an invariant the replay checks). Recorded in 04 T-CON-25 (rev 1.19) as a docs-first amendment.
2. **Transforms and views (RCP-28a).** Registered identity links 0.1.0→0.2.0→0.3.0 (the `direction`
   member is a dataclass default the decoder applies to older evidence); `TransformUnavailable` =
   `NO_INPUT_TRANSFORM`; `cv25_view` mirrors `InputBundle.sha256` by test; L1 blanks exactly the three
   stamp paths (R = 3 for one book, n + 2 for n books); the attribution view keeps `known_at` and blanks
   only `engine_version` / `format_version`.
3. **Release validation (REL-06; D-96 (3), (4), (6), (7), B, C).** Per-tenant effective level over the
   declared chain (a globally PATCH build is MAJOR for a lagging tenant); BOOTSTRAP only when proven
   empty; a non-empty tenant without a BASELINE is `INCOMPLETE` (`PREPARATION_MISSING`); the BASELINE row
   names the preparation artifact's own release; RCP-29 population (3 + 20 with 400 and 100 remaining,
   < 20 takes all, ceil(5 %), strata over all enabled books, two-pass by `rank_sha256`, `NO_SOURCE`);
   orchestration state independent of the accepted pointer; aggregation on terminal jobs; MINOR fails on
   any `DIFFERENCES`; MAJOR routes to approval; `MISMATCH`/`UNVERIFIABLE`/exhausted/cancelled → `INCOMPLETE`;
   DB-03 transition table; `persist_admission` per process release; `verification_write` with the
   execution token and lock (duplicate, fenced, already_accepted; ERROR never accepted; prior rows kept).
4. **Replay decision (RCP-28a; A, B).** Evidence order runtime → present → raw digest → logical hash →
   output digest/CV-26/book set → transform → execution; `SOURCE_RUNTIME_UNAVAILABLE` stored with
   `engine_executed = false` and `compute` not invoked (spy); the four named CHECKs enforced in
   `VerificationRow.__post_init__` (malformed rows refused); altered T-CON-08 → `EXPECTED_HASH_DISAGREEMENT`
   (S02 preserved); candidate stamp-only → L1 `MATCH`; money change → `DIFFERENCES`, never `MISMATCH`.
5. **Upgrade processing and attribution (E v5, F, R7).** Seeding only for MINOR/MAJOR with an accepted
   attempt; `unresolved_origins` re-applies S08-R-08 via `dates.first_open_period_on_or_after` (asserted
   equal to the engine rule); January/March/June → July and A-posted/B-deferred cases; trace-only settle;
   duplicate appends nothing; `UPGRADE_CONTEXT` default, `UPGRADE_ONLY` only on attribution-view
   equality, `known_at`-only and period-state-only → `UPGRADE_AND_OTHER_INPUTS`; frozen dataset
   deterministic and order-insensitive; report rows and totals from the bytes alone; approval content
   hash binds dataset + attempt + entity set; register exact as of `known_at`.
6. **SOP-4 preparation.** SAR-13 buckets (token 30/min per client id; browser 1,200/min per session;
   API client `rate_limit_per_minute`, default 600) with `Retry-After` and refusals not counted;
   `client_ip` of `auth/dependencies.py` reused; MET-01..11 definitions equal to the 05 table; label
   values that look like a UUID or an amount are refused.
7. **Ruled P5-owned SOP-2 / D-96 items (team-lead ruling, 2026-09-19; `bc41e59`).** P1 keeps exactly
   candidate 11's delivered REL-05 scope; P5 owns (a) **consumer stamping** with the process's own
   release row — `controls/stamping.py` `process_release_id(current, env, latest_for_version)`: the
   row `controls.release.current_release()` retained wins; **production fails closed** with
   `release-mismatch` when nothing was stamped (REL-03 stamps before any work), while `dev` / `test`
   / CLI `run_inline` fall back to the latest row of the running version — the design call P1 left
   open, recorded here; (b) the **manifest `validation_level`** key and the **T-PLT-38 column** —
   `controls/validation_level.py`: `declared_validation_level` (absent → `PATCH`, undeclared),
   `with_validation_level` (generator helper), the column contract tuple the revision implements,
   `check_declaration` (a declaration may exceed but never fall below the semver floor between the
   previous global release and the candidate; D-96 (3)); `semver_level` now lives in this kernel
   module so the stamping hook can use it without an upward import, and the state machine re-imports
   it; (c) the **preparation artifact** — `domain/contracts/release_prepare.py`
   `is_preparation_artifact` (same `engine_version`, new `build_sha`) and `baseline_for_artifact`
   (the BASELINE row for the artifact's own release; refused for a candidate); (d) the **`erev release
   prepare`** logic — `plan_prepare`, `backfill_decision` (`BACKFILL_VERIFIED` only when the current
   bundle's CV-25 hash equals the head's `input_sha256` **and** the engine reproduces the stored
   output; `INPUT_DRIFTED` / `OUTPUT_DRIFTED` / `ENGINE_ERROR` → recompute under the baseline),
   `prepare_summary` (exit 0 only when zero heads lack evidence) and `format_summary` (counts and
   group ids only; no connection strings).

## D-96 acceptance scenarios → tests (CPU-only stand-ins; the named SOP-3 tests stay integration)

| Scenario | Test |
|---|---|
| Unknown runtime = not executed | `test_replay_verify_decisions.py::test_source_runtime_unavailable_is_stored_and_compute_is_not_invoked`; `::test_executed_identity_checks_refuse_malformed_rows` |
| Two-job execution lock | `test_release_validation.py::test_execution_lock_two_jobs_same_group_second_writes_nothing_new` (Procrastinate `lock` + advisory lock modelled by an `ExecutionLock` port; the DB primitives are integration) |
| Partial-origin deferral | `test_upgrade_processing.py::test_partial_origin_deferral_jan_mar_jun_then_july_opens`; `::test_a_posted_b_deferred_then_b_opens_group_terminal_only_after_both` |
| BASELINE identity | `test_release_validation.py::test_baseline_names_the_preparation_release_itself`; `::test_bootstrap_only_for_a_proven_empty_tenant`; `test_release_prepare.py::test_preparation_artifact_identity_and_its_own_baseline_row` |
| Verified backfill / prepare completeness | `test_release_prepare.py::test_backfill_verified_only_when_both_hashes_prove_identity`; `::test_summary_is_complete_only_when_no_head_lacks_evidence` |
| Consumer stamping, `validation_level`, semver floor | `test_release_level_and_stamping.py` (all three tests) |
| L0/L1/L2 comparison | `test_upgrade.py::test_l1_equal_for_a_stamp_only_release_and_r_counts_3_and_n_plus_2`; `::test_l2_classifies_money_posting_and_trace_changes`; `test_replay_verify_decisions.py::test_candidate_stamp_only_release_matches_on_l1_with_r_count_3` |
| MINOR fails on any L1 difference | `test_release_validation.py::test_minor_fails_on_any_l1_difference_and_major_routes_to_approval` |
| No invented causes | `test_upgrade_processing.py::test_cause_labels_known_at_and_period_state_changes_are_other_inputs`; `test_upgrade.py::test_attribution_comparison_labels` |
| Pending-note form for drift tests | 04 §3.4 rows E-125..E-130 lifted; E-08 / E-68 values and the §15.2 slug kept as pending paragraphs with the reason (below) |

## Integration prerequisites (stated, not assumed)

Nothing below is done by this slice; each names the interface this slice expects.

- **P1 (REL-05 and release identity).** Reply of 2026-09-19 (lane-p1-release-manifest, verified on
  `sprint/l2` 89b5f10): P1 delivers enqueuer stamping (`insert_job` → `params.engine_release_id` from
  `controls.release.current_release()`), worker retention (`JobRuntime(engine_release=…)`), the D-80 entry
  fence, `classify_release_pin`, 30 s ×10 re-defer then `release-mismatch` 503. **Not delivered by P1**
  and owned by P5 integration: consumer stamping with the process's own release row in
  `domain/journals/summarise.py:604-606` and `domain/reports/framework.py:558-560` (build on
  `current_release()`; fallback vs fail-closed is a P5 design call). Signatures to build on after P1's
  merge: `dispatch(session, *, job_id, tenant_id, queue, now, attempt=1, delay=None,
  release_mismatch_deferrals=0)` — P5 adds `lock=` as a keyword with a None default (DG-KRN-JOB-12);
  `_redispatch_if_owner(…)` is the re-defer helper `release-validation-pending` reuses (its counter is
  REL-05's; generalise the name rather than add a second field); Procrastinate's `JobContext` is what
  `worker.run_job` receives, `JobRuntime` gained `engine_release` — P5's `task_id`/`attempt` exposure
  attaches there. **Ruling (team-lead, 2026-09-19):** P1 keeps exactly candidate 11's delivered scope;
  P5 owns consumer stamping, the manifest `validation_level` key and T-PLT-38 column, the preparation
  artifact and the `erev release prepare` CLI — prepared here as pure modules (`bc41e59`). **Sequencing
  prerequisite:** none of the following is touched before P1's merge lands on main: the `lock=` keyword
  on `dispatch()`, `task_id` / `attempt` on the job context, the consumer sites `summarise.py:604`,
  `reports/framework.py:558` (and the same latest-per-version query in `compute_job.py:197` and
  `computation.py:279`), `facts_from_manifest` / `stamp_release` reading `validation_level`, the manifest
  generator's key set (`scripts/release_manifest.py`, P1's file), the Alembic revision (T-PLT-38 column,
  T-CON-25/26, T-PLT-43 to 46, T-SL-11), and the `erev release prepare` Typer command in `cli.py`.
- **R2 preparation path (Codex closure qualification, 2026-09-20).** `PreparationRow.authorization_ref` is
  a typed reference only — a non-blank string is not approval. The integration wires
  `prepare_release_baseline` inside the transaction that (i) resolves the reference to an approval the
  authority model accepts (`ENGINE_RELEASE_VALIDATION` `SubjectSpec`, DG-KRN-APR-06) or refuses, (ii)
  checks the persisted `engine_release` row's `(engine_version, build_sha)` against the process facts,
  (iii) writes the T-PLT-43 BASELINE row and the T-CON-25 evidence atomically, and (iv) surfaces the
  `REL-06-SAME-VERSION-REBUILD` and `PrepareSummaryError` refusals through startup (REL-03 stop), the
  `erev release prepare` exit code and the job path. None of this was tested at `e0ea5aa`.
- **P2 (runtime interfaces).** Shared `config.py`, `worker.py`, `pyproject.toml`; the metrics route and
  the request-limit middleware wire onto P2's listener/probes (extend, never replace); `prometheus-client`
  and the OTEL SDK dependency additions follow the P2 merge.
- **P6 (recovery and runbook).** RB-09 / RB-16 text is P5's, docs-first on this branch **after** the P6
  merge (P6's d4fbc61 carries the two runbook sections P5 extends). D-96 (6) retention and the
  `file.shred` retirement path depend on P6's storage decisions.
- **DB evidence.** T-CON-25/26, T-PLT-43 to 46, T-SL-11 tables and their Alembic revision (§18 rule 8),
  DB-03 transitions generated from `release_validation.TRANSITIONS`, the four T-CON-26 CHECKs as SQL,
  `computation.persist()` evidence capture + gate + T-PLT-46 / T-SL-11 writes, the `REPLAY_VERIFY`
  handler (`@task`, `PENDING_JOB_HANDLERS` removal, `verify:<group id>` lock, advisory lock), the
  `ENGINE_RELEASE_VALIDATION` `SubjectSpec` with the set-form `find_authority` (DG-KRN-APR-06), the two
  report builders mapped onto `ReportData`, T-RPT-01 seeds (`upgrade_validation`,
  `engine_trueup_register`: also PHASES §5.4 and SCREENS_B §5.6 rows, read by `test_seeded_codes`), and
  the four named SOP-3 tests with the CTR factories — all need `make test-pg`.

## Supervisor docs items found (not lane-editable)

- **§15.2 `release-validation-pending` — LANDED (lift slice, 2026-09-20).** The drift tests compare
  `PROBLEMS` with 04 §15.2 and with the PRD §5.5 ERR copy rows (`err_titles`, `test_dg_arc_13_err_rows_cover_slugs`),
  and `docs/02-PRD.md` is read-only for the build loop, so this lane first drafted and reverted the lift (the
  rev 1.19 pending paragraph recorded the reason). The supervisor's sequencing ruling (team-lead, 2026-09-19)
  then placed the whole coupled set on this branch as docs-first commits with the docs lane's sidecar texts:
  `51fbcbf` (PRD rev 1.6 ERR-51 "Release validation in progress"; 04 rev 1.20 row + lifted paragraph) and the
  code commit after it (`PROBLEMS` entry; `test_dg_arc_09` pin 47 → 48; `test_dg_arc_13` `len(slugs) == 48`,
  ERR range `range(1, 52)` — the second pin was found by the docs lane's dry run). Generator and texts:
  `.run/p5/patches/apply_lift_set.py` + README. The docs lane stamps the matrix / PLAN-SUMMARY after the merge.
- **E-08 `ENGINE_RELEASE_VALIDATION`, E-68 purposes.** Kept pending (paragraph in 04 §3.4): the E-08 value
  needs the `SUBJECTS` entry (registry completeness) and the E-68 values the file-store purpose policy —
  both integration.

## Codex P5-PREP review (`PRODUCTION-P5-PREP-REVIEW-934c55d.md`; 56 controls, 47 pass / 9 fail) — corrections, closed at `e0ea5aa`

Target `934c55d`, observations confirmed applicable at `a6d5477` (185/185 executable ASTs identical). Three
bounded corrections dispatched by the team-lead, CPU-only, fail-first tests mirroring the probe shapes:

| Item | Ruling applied | Where | Tests |
|---|---|---|---|
| **R1** completion summary (six failed controls) | Completion requires a one-to-one match between the planned `(group_id, head_computation_id)` identities and the outcome identities: a planned identity without an outcome → `complete = False`, exit 1, listed (`missing`); a duplicate outcome identity → refused, `PrepareSummaryError("SUMMARY_OUTCOME_DUPLICATE")`; an identity outside the plan (wrong group, wrong head, extra) → refused, `SUMMARY_OUTCOME_UNPLANNED`; neither substitutes for a missing head; drift / engine-error reporting and the explicit no-head case unchanged | `release_prepare.prepare_summary`, `PrepareSummary.missing`, `format_summary` | `test_p5_prep_r1_completion_requires_one_to_one_match_with_the_plan` — the six probe shapes (native head + empty outcomes; one of two omitted; duplicate masking the omission; wrong group; wrong head; complete two-head set) plus the drift and no-head controls |
| **R2** same-version new-build preparation (one failed control) | D-98 candidate REL-06-SAME-VERSION-REBUILD (supervisor): (a) explicit `prepare_release_baseline(facts, *, preparation_release_id, historical_release_id, authorization_ref)` accepts an artifact whose engine version equals the enabled release's when the build differs, requires the typed `authorization_ref` (no live actor), binds the artifact's **own** BASELINE row and returns a `PreparationRow`; (b) `check_declaration` gains `previous_build`, `candidate_build`, `preparation`: an equal `(version, build)` pair is accepted (same release restarting); "does not follow" applies only when the version differs; downgrade / under-declaration / forward-floor checks unchanged; (c) a same-version different-build pair is never accepted through the bare declaration path — `REL-06-SAME-VERSION-REBUILD` refusal. Docstrings state that build facts never infer calculation-code identity | `controls/validation_level.py` (`PreparationRow`, `check_declaration`), `release_prepare.prepare_release_baseline` | `test_p5_prep_r2_same_version_new_build_only_through_the_preparation_path` — the probe assertion (0.3.0 / new build / PATCH through the preparation path passes; the same pair through the bare path fails) plus the unchanged controls |
| **R3** backfill book population (two failed controls) | The helper enforces the invariant itself: the key set of `output_sha256_by_book` must equal the contract-version book population of the recomputed output (04 T-CON-25 `book_codes`); an unknown key, a missing book or an extra book → `BACKFILL_BOOK_POPULATION_MISMATCH` (refused, no evidence, no recompute; blocks completion via `PrepareSummary.refused`); per-book hash comparisons unchanged (`OUTPUT_DRIFTED`) | `release_prepare.backfill_decision` | `test_p5_prep_r3_backfill_reconciles_the_book_population` — `{'NOT_A_BOOK': sha}`, `{'ASC606': sha, 'IFRS15': sha}`, the correct single-book control, a missing book, the unchanged wrong-hash drift |

Not touched: answer keys, goldens, the DB layer; the wired startup / CLI / persistence remain the integration
dispatch after the P1 and P2 merges. The `.run/supervisor/d98` ruling text is the supervisor's; cited only.

**Closure — Codex retest at exact `e0ea5aa`** (`PRODUCTION-P5-PREP-RETEST-e0ea5aa.md`, SHA256 `6d89e938…`,
manifest `bb6f6401…`; relayed by the team-lead 2026-09-20; recorded verbatim). The unchanged 56-case probe:
**54/56** (was 47/56); the explicit-interface supplement: **36/37**. R1: all six original failures close
(missing outcomes → incomplete / non-zero exit; duplicate and unplanned identities refuse). R2:
`prepare_release_baseline` returns a `PreparationRow` accepted by `check_declaration` for the same-version
0.3.0 / different-build / PATCH facts; own baseline = preparation row; exact version/build and a non-blank
authorization reference required; the bare call intentionally refuses; foreign/missing build, wrong
version/baseline, blank reference, changed-version preparation, same-build preparation, downgrade and
under-declaration all refuse. R3: population checked before hashes; unknown / missing / extra /
extra-plus-bad-hash refuse with no evidence or recompute; same-population bad hashes still `OUTPUT_DRIFTED`.
The supplement's one failure is Codex's own case-sensitive formatter expectation ("prepare incomplete" vs the
producer's "prepare INCOMPLETE") — no producer fix requested; noted only. MOD-LEGACY-PROS-GT12 computation
and financial hashes unchanged. **P5-PREP R1–R3 CLOSED.**

**Qualification carried into the integration dispatch (next scope, not this slice):** the authorization
reference is synthetic trusted input — a non-blank string is not approval. The caller / transaction
integration must validate the approval and the persisted release/build identity, create the baseline and
the evidence atomically, and carry the refusals through startup, the CLI and jobs; no approval lookup, DB,
persisted evidence or release promotion was tested. Listed under "Integration prerequisites" below.

## Questions returned and the team-lead's rulings (2026-09-19)

1. Owner of the manifest `validation_level`, the T-PLT-38 column and the preparation artifact —
   **ruled**: P5; prepared in `bc41e59`, wired after P1's merge.
2. T-PLT-46 conservative origin set — **ruled**: assembled **inside the persistence boundary** from
   the frozen computation's own period keys (member events by effective date, posted rows with their
   origin periods, the book's schedule lines), never supplied by the caller, which could under-state
   it. Applied: `conservative_origins(entity, book_code, *, bundle, output)`; the test
   `test_origin_set_is_derived_inside_the_boundary_and_cannot_be_narrowed` asserts the signature has
   no key-list parameter and that the derived set equals the full closed-period union on a real
   computation.
3. L2 classification (`M` by monetary section incl. non-amount members, `trace_nodes` → `T`, the three
   stamp paths → `R`, everything else `T`) — **accepted as the documented rule**; stated in 04 T-CON-26's
   `difference_summary` note (rev 1.19; the L2 home is T-CON-26 / RCP-28a, not T-PLT-46, which holds the
   processing states) so Codex reviews the rule, not an implicit choice.
4. Consumer-stamping fallback — **ruled as proposed**: fail closed under `EREV_ENV=production`;
   latest-per-version only under `dev` / `test` with an explicit WARN-class line naming the fallback.
   Applied: `process_release_id(..., warn=None)` emits `release.stamp_fallback` (fields `fallback`,
   `detail`) through `erev_api.logging.get_logger`; injectable for tests; the production path never
   warns — it raises `release-mismatch`.
5. `check_declaration`'s semver floor at stamping — **ruled** (team-lead, 2026-09-19): against the
   previous **global** release only, in this slice; the per-tenant chain (declared levels of every
   release between the tenant's last enabled release and the candidate, max with the semver level) is
   evaluated at T-PLT-43 creation by `effective_level`, where D-96 (3) places it. The split is therefore:
   stamping guards the author's declaration (never below the digits between consecutive global
   releases); validation creation decides each tenant's effective transition. Built that way in
   `bc41e59`; docstring cites the ruling.

**Review target.** Codex's CPU-only review target is `934c55d` (team-lead, 2026-09-19 16:33; it
supersedes the earlier `3a2a9bf` designation and carries the applied rulings (2)–(4) and the renumbering).
The commits after it (`8f61a98` and this one) change only this record, the ruling (5) docstring citation
and the 04 T-PLT-46 cross-reference; nothing in the reviewed code changed.

**Codex CPU-only review of the slice:** requested by the team-lead (2026-09-19) against this branch's head;
the evidence-codec finding is reviewed in 04 T-CON-25 (rev 1.19 on this branch).

**Lift patch for the docs lane:** `.run/p5/patches/release-validation-pending-lift.patch` (unified diff
against this branch: the `PROBLEMS` entry, the drift count 47 → 48, the 04 §15.2 row and the pending
paragraph rewritten as lifted); re-applies cleanly; to be applied by the docs lane together with the
supervisor-authored PRD §5.5 ERR-51 row in one main state after the integration merge. Strings confirmed
with the docs lane: title `Release validation in progress`, 503, no EREV code.

## Residual limits

- The codec round trip is proven on `support.bundles` bundles and one answer-key checkpoint; a
  `slow`-marked sweep over every active key's checkpoint bundles is a follow-up.
- `DatasetReport` is this slice's shape; the integration slice maps it onto the framework's
  `ReportData` / `Column` objects.
- The E2E port keys of the inherited `.env` carried the same two values as the dev port keys (P3
  heritage). Fixed 2026-09-19 with values chosen programmatically and never printed: the four port
  keys now hold four distinct values, none declared by any other `~/dev/erev-wt/*/.env` or the dev
  root, none listening, neither 8190 nor 5270 (verified by key name only).

## Continuation

The actual integration (consumer release identity, persisted `validation_level`, then the CLI, the `REPLAY_VERIFY` path, the rate-limit / metrics wiring — one slice per dispatch) is recorded in `docs/reviews/loop/prod/P5-integration.md`.

## DG-ARC-09 pg enum count — bounded fix (team-lead dispatch, 2026-09-19; separate commit off main `6e33ef27`)

**Failure on main.** `make test-pg` on the integrated batch at `6e33ef27`: 1 failed / 291 passed —
`backend/tests/pg/test_data_model_drift_pg.py::test_dg_arc_09_pg_enum_labels_equal_python` asserts
`len(database_enums()) == 122 - 14` and finds 114. **Cause** (team-lead's blame, confirmed here): the D-96 prep commit
`7e2eb4f` added the six non-`API_ONLY` StrEnums of 04 §3.4 E-125 to E-130 (`VerificationOutcome`,
`ReleaseValidationStatus`, `ValidationAttemptStatus`, `PostingAttributionCause`, `ValidationGroupOrchestrationState`,
`UpgradeProcessingState`) to `erev_api.enums` without moving the DG-ARC-09 count; the P5 merges' post-checks were
non-DB, so it surfaced only in the batch.

**Fix (this commit, test file only).** The constant reads `130 - 2 - 14` — E-01 to E-130 less the 2 withdrawn and the
14 `API_ONLY` enums — with the comment corrected. Nothing else: no skip, no weakening, no restructuring; the label
comparison `enum_drift(...) == []` runs unchanged.

**Evidence.** CPU part (`database_enums()` is pure Python; `.run/p5/int1/dgarc09-count-evidence.txt`): on the tree
`len(database_enums()) = 114`; old constant 108 → FAIL (fail-first); new constant 114 → PASS; the six E-125..E-130
mirrors are counted; 14 `API_ONLY` StrEnums excluded. **DB stage NOT RUN from this worktree:** the lane database
`erev_rv_l12_test` named by the l12 `.env` does not exist (`psycopg.OperationalError … does not exist`; lane databases
are created Ray-side, no `CREATE DATABASE` by a lane), so neither the fail-first run of the whole test nor the green
run with the label comparison could be executed here and **no gate slot was taken**. The whole-test green is owed to
the first `make test-pg` that runs this commit (the team-lead's merge batch, or l12 once its database exists).

**Not in this commit, by design.** E-125 to E-130 have no PostgreSQL enum types yet: main's Alembic head is `0054`
and lane P5's validation-contract revision is the PROVISIONAL `0097`, which adds only the T-PLT-38 `validation_level`
column. DG-ARC-09's `enum_drift` is one-directional (every `erev.*` enum type needs a StrEnum mirror; a StrEnum without
a type is not reported), so the PG types stay owed to lane P5's integration slice that creates T-PLT-43 to 46,
T-CON-25/26 and T-SL-11 (04 §18 rule 8); the reverse check is not added here.
