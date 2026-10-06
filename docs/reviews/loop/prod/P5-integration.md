# Lane P5 — actual integration, slice 1: consumer release identity and the persisted validation declaration

Worktree `l12`, branch `sprint/l12-p5` (continues `P5-prep.md`; that record's "Integration prerequisites"
section is the contract this slice starts to discharge). Dispatch: team-lead, 2026-09-19 ("P5 actual-integration
slice 1", after the merges of `941b447` → main `f4df47ef`; branch fast-forwarded onto main `9b611133`, which
contains `f4df47ef`). Codex's ownership table `PRODUCTION-P5-MERGED-REVIEW-c43718b.md` is cited by the dispatch;
the file was not found under `.run/supervisor` or `docs/` from this worktree, so the four consumers below are the
four `engine_release` selections by `engine_version` that the code contains — the same four the P5-prep record
named as the consumer sites (`summarise.py`, `reports/framework.py`, `compute_job.py`, `computation.py`).

## Scope of slice 1 (two commits, docs first)

1. **Consumer release identity.** The four consumers that write `engine_release_id` stop selecting "the latest
   `engine_release` row of the running `engine_version`" and stamp the row **this process** recorded at startup
   (`controls.release.current_release()`), through the resolver prepared in `bc41e59`
   (`controls.stamping.process_release_id`): production fails closed with `release-mismatch`; a process that never
   stamped (inline CLI, tests) or a non-production process falls back to the latest row of the running version
   with the `release.stamp_fallback` WARN line; a stamped row whose `engine_version` differs from the output's is
   refused.
2. **Persisted validation declaration and the global floor.** T-PLT-38 gains `validation_level` (text N,
   default `'PATCH'`, `ck_engine_release__validation_level`) in the code table and a PROVISIONAL Alembic revision
   `0097` on `down_revision` `0054` (the dispatch's placeholder; the supervisor assigns the final number and parent
   at merge; the lane never renumbers). `stamp_release` reads the REL-01 manifest key (absent → `PATCH`,
   undeclared; another literal → manifest error, REL-03 stop), persists it, and applies the semver floor against
   the previous **global** release for a version-changing new row (team-lead ruling (5)).

## Docs first (commit 1)

| Document | Revision | Change |
|---|---|---|
| `docs/04-DATA_MODEL.md` | 1.29 (1.22 at `0463301`; renumbered in 1b against the group-2 merges) | T-PLT-38: the rev 1.13 pending column `validation_level` becomes a column row (notes: REL-03 persistence at first insert; floor against the previous global release for version-changing new rows; restart checks nothing; same-version new build recorded and evaluated at T-PLT-43 creation through the REL-06 preparation path); pending paragraph lifted; §18 rule 9 (PROVISIONAL 0097 on 0054, `ALTER TABLE` of the step-0002 table, no new object group) |
| `docs/05-ARCHITECTURE.md` | 1.15 (1.14 at `0463301`; renumbered in 1b) | REL-03 gains the consumer rule (process release, version guard, production fail-closed, `release.stamp_fallback` fallback) and the stamping of `validation_level` with the floor |
| `docs/dev-guide.md` | 1.25 (1.24 at `0463301`; renumbered in 1b) | DG-KRN-JOB-13 consumer-stamping sentence (`process_release_id(current_release(), env=current_environment(), …)`; no `get_settings()` in domain code, DG-KRN-CFG-01); DG-ENG-10 persisted `validation_level` and the `stamping_decision` paths |

Revision numbers were the next free after main `9b611133` at `0463301` (04 1.22; 05 1.14; dev-guide 1.24) and are renumbered by slice 1b to 04 **1.29**, 05 **1.15**, dev-guide **1.25** — the team-lead's assignment against the group-2 lanes merging first (C6 04 1.22–1.24, C5 1.25–1.27, C4 1.28; C8 05 1.14; C4 dev-guide 1.24); the merge order is C6, C8, C5, C4, then P5;
header entries equal log rows in all three files (`test_governed_docs_revisions.py` + `test_guides.py`: 6 passed).
Fail-first on the docs-first tree (`.run/p5/int1/fail-first-docs-first-table-columns.txt`):
`test_dg_arc_09_table_columns_match` fails on `engine_release` — "Right contains one more item:
'validation_level'" — until commit 2 adds the column to the code table.

## Design decisions recorded in this slice (for the team-lead / Codex)

- **Same-version new build at stamping.** `check_declaration` (Codex P5-PREP R2, closed at `e0ea5aa`) refuses a
  same-version different-build pair without a `PreparationRow`. Stamping cannot make that call: the preparation
  artifact's own `engine_release` row must exist before a `PreparationRow` can name it (`preparation_release_id`),
  and every non-engine release (api / frontend change, `ENGINE_VERSION` unchanged) is a same-version new build.
  So `controls.validation_level.stamping_decision` names four paths — `FIRST_RELEASE`, `RESTART` (row present,
  nothing checked), `VERSION_CHANGE` (`check_declaration` against the previous global release; below the floor or
  "does not follow" → the process stops before the insert), `SAME_VERSION_REBUILD` (recorded with its declaration;
  the declaration is evaluated at T-PLT-43 creation through the REL-06 preparation path — the validation slice).
  Stated in 04 T-PLT-38, 05 REL-03 and DG-ENG-10. A rollback build (new build of an older version) is refused at
  stamping ("does not follow"); a restart of an already-stamped older release is a `RESTART` and is not refused.
- **Environment without `get_settings()` in domain code — D-98 60 (slice 1b supersedes the slice-1 text).**
  DG-KRN-CFG-01 forbids `get_settings()` in domain code, so the environment is established at the trusted
  entrypoint boundary: `stamp_release` (api lifespan, worker start, `erev seed`) and `cli.cli_services()` (every
  CLI command) record it into `controls.release` before any domain call, and the consumers pass
  `current_environment()`. Ruling applied: an unknown or unremembered environment is **production** (fail closed);
  a missing stamp never classifies a caller as non-production; the latest-per-version fallback is permitted only
  when the remembered environment is explicitly `dev` or `test` (`controls.stamping.FALLBACK_ENVIRONMENTS`); `e2e`
  fails closed too. Slice 1 had treated "unremembered" as non-production — that regression (P5-integration.md
  53–57 and REL-03 at `0463301`) is corrected in 05 REL-03, DG-KRN-JOB-13, the code and the tests (fail-first:
  unremembered + unstamped → refusal).
- **`RuntimeError` → `Problem("release-mismatch")`.** `compute_job._release_id` and
  `computation._engine_release_id` raised `RuntimeError` when no row existed; through `process_release_id` the
  not-found case is the REL-05 problem, as `summarise` and `framework` already did.
- **Alembic head moves to `0055` (drafted as the provisional `0097`; number assigned at slice 1c).** `code_head()` is the single head, so `schema_revision` of derived facts and
  a fresh `make release-manifest` read `0055`; a stale `release-manifest.json` naming `0054` is refused by
  `facts_from_manifest` ("names another schema revision"). Head pins in `tests/pg/test_migrations.py::test_single_head`
  and `tests/api/test_me.py` move to `0097` (DB-bound; NOT RUN here). The shared dev database stays at `0054`
  until migrated (`readyz` would report the mismatch); this lane runs no database.

## Slice 1b (team-lead dispatch after Codex 0515 `PRODUCTION-MAIN-PG-FAILURE-6e33ef27.md`; D-98 59, 60)

| Item | Ruling applied | Where | Evidence |
|---|---|---|---|
| (a) PG enum types for E-125 to E-130 + the reverse direction of DG-ARC-09 | The PROVISIONAL revision 0097 creates the six types (`ENUM_TYPES` literals = 04 §3.4 labels; `ops.create_enum`, downgrade `ops.drop_enum`, reverse order). `test_data_model_drift_pg.enum_drift` gains the reverse direction — a database-candidate StrEnum with no `erev.*` type is a finding. **Finding while doing it (static replay of all 55 committed `upgrade()`s under `migration_ops.recording()`, no database):** the committed revisions create **92** enum types for **114** database-candidate mirrors — **22** mirrors have no type: my six **and sixteen pre-existing** (E-04 `period_state`, E-23/24/25 modification enums, E-72 `sync_run_status`, E-73/74 AI proposal, E-75/76 migration, E-82 `reporting_entity_type`, E-83 `cost_kind`, E-84 `amortization_pattern`, E-85 `loss_unit`, E-86 `fx_layer_movement_kind`, E-92 `option_type`, E-100 `scenario_status`) whose tables are later-phase and not built. A bare reverse check would therefore go red on main for those sixteen. Resolution taken (for the team-lead to ratify): `tests/support/enum_mirrors.PENDING_ENUM_TYPES` names exactly those sixteen with their E-ids as a **reconciliation list** — a type that lands must leave the list (finding), a mirror neither created nor listed is a finding, every listed name must be a mirror; E-125 to E-130 are NOT on it. Nothing is marked API-only; no label or population changes | `0097_engine_release_validation_level.py`, `tests/support/enum_mirrors.py` (new: `database_enums`, `migration_enum_types`, `PENDING_ENUM_TYPES`, `type_gaps`), `tests/pg/test_data_model_drift_pg.py` (imports the shared helpers; both directions; probe asserts the reverse finding), `tests/architecture/test_data_model_drift.py` (+2: `test_dg_arc_09_every_database_enum_has_a_migration_type` — the static reverse direction, CPU; `test_provisional_0097_enum_literals_equal_the_mirrors`) | fail-first `.run/p5/int1/fail-first-1b.txt`: on the pre-1b tree the static reverse check lists the six E-125..E-130 mirrors ("no PostgreSQL enum type for …"), `ENUM_TYPES` absent; pass `pass-1b.txt`. The pg half is NOT RUN here (no lane database) |
| (b) D-98 60 fail-closed | See the corrected decision above: unknown / unremembered → production; fallback only for a remembered `dev` / `test`; boundary records the environment (`stamp_release`, `cli_services()`) | `controls/stamping.py` (`FALLBACK_ENVIRONMENTS`, predicate), `controls/release.py` (comment), `cli.py` (`remember_environment(settings.env)` in `cli_services()` — one call at the composition root, under the ruling), 05 REL-03, DG-KRN-JOB-13, 04 T-PLT-38 note | fail-first: `test_consumer_release_identity` "DID NOT RAISE Problem" ×4 for the unremembered case on the pre-1b code; `test_release_level_and_stamping` (ImportError for `FALLBACK_ENVIRONMENTS`, then the assertions); pass `pass-1b.txt` |
| (c) D-98 59 same-version rebuild | **Branch taken: RECORD at stamping, PENDING by default.** `initial_validation` gains the same-version branch: `status PENDING`, `enabled_at_creation False`, `effective_level PATCH`, reason `SAME_VERSION_REBUILD`, before `effective_level` (which raises on equal versions); `persist_admission` refuses a PENDING or absent row with `release-validation-pending`, so production serving stays behind ERR-51 until `prepare_release_baseline` (BASELINE) or a validation enables it; the Codex R2 refusal stays in `check_declaration` (tested again here). The guarantee is in the pure contract; its wiring at process start is the validation slice | `domain/contracts/release_validation.py`, `tests/unit/test_release_validation.py` (+1), 04 T-PLT-38 note, 05 REL-03, DG-ENG-10 | fail-first: ImportError for `SAME_VERSION_REBUILD` on the pre-1b tree (the pre-1b `initial_validation` raised "does not follow" for equal versions); pass `pass-1b.txt` |
| (d) Renumbering | 04 1.22 → 1.29, 05 1.14 → 1.15, dev-guide 1.24 → 1.25 in headers, log rows, every cross-reference in the three documents, code comments, tests and this record | docs-first commit of 1b; code commit | `test_governed_docs_revisions` + `test_guides` green; `grep` for the old numbers in the slice's files: none |

The DG-ARC-09 **count** fix (`122 - 14` → `130 - 2 - 14`) is the separate commit `d5a18902` on `sprint/l12-p5-fix-dgarc09` (parent main 6e33ef27), also merged into this branch (9564d08a); it is not repeated here.

## Requests to other lanes (never edited here)

- **P1 (`scripts/release_manifest.py`).** `make release-manifest` should write `validation_level` from an author
  input (`VALIDATION_LEVEL=PATCH|MINOR|MAJOR`, default absent → the consumer reads `PATCH` undeclared);
  `controls.validation_level.with_validation_level(manifest, level)` is the helper. Until then every manifest is
  undeclared `PATCH`, which the floor refuses for a MINOR/MAJOR version change — the intended fail-closed default.
- **P2 / P6.** Unchanged from `P5-prep.md` ("Integration prerequisites"): the metrics route, the request-limit
  middleware, RB-09 / RB-16 text and retention follow their merges; nothing here touches `config.py`, `worker.py`,
  `main.py`, `cli.py` or `pyproject.toml`.

## Commits

| Commit | Files | Change | Gate evidence |
|---|---|---|---|
| `0463301` (docs first) | `docs/04-DATA_MODEL.md` (rev 1.22), `docs/05-ARCHITECTURE.md` (rev 1.14), `docs/dev-guide.md` (rev 1.24), this record, `P5-prep.md` (pointer) | The governed statements of the slice, before any code | `test_governed_docs_revisions.py` + `test_guides.py` 6 passed; fail-first `test_dg_arc_09_table_columns_match` red on this tree (`.run/p5/int1/fail-first-docs-first-table-columns.txt`); `make lint` |
| `700f311` (code) | `backend/erev_api/controls/validation_level.py` (`stamping_decision`, `StampingDecision`, `StampingPath`), `backend/erev_api/controls/release.py` (`ReleaseFacts.validation_level` / `validation_declared`, `EngineRelease.validation_level`, `current_environment` / `remember_environment`, `facts_from_manifest` reads the key, `stamp_release` applies the decision before the insert and persists the column, `log_release` field), `backend/erev_api/controls/stamping.py` (`env` may be None, `engine_version` guard), `backend/erev_api/db/tables/platform.py` (`validation_level` column), `backend/erev_api/db/migrations/versions/0097_engine_release_validation_level.py` (PROVISIONAL, on 0054), the four consumers `domain/contracts/computation.py`, `domain/contracts/compute_job.py`, `domain/journals/summarise.py`, `domain/reports/framework.py` (`_release_id` / `_engine_release_id` → `process_release_id(current_release(), env=current_environment(), engine_version=…, latest_for_version=…)`), `backend/erev_api/privacy/classification.py` (the DOC_04 pending `validation_level` entry reconciled to ACTIVE — the PRV-01 gate for a landed column), tests: `tests/unit/test_release_level_and_stamping.py` (+3), `tests/unit/test_consumer_release_identity.py` (new, 12 = 3 × 4 consumers), `tests/pg/test_release_validation_level.py` (new, 4, pg-marked, NOT RUN), `tests/pg/test_migrations.py` and `tests/api/test_me.py` (head pin 0054 → 0097, NOT RUN), `tests/unit/test_privacy_classification.py` (the R1 paragraph example moves to a synthetic rev 1.13 copy because the real paragraph is lifted), this record | Slice 1 code: consumer release identity and the persisted declaration with the global floor | fail-first `.run/p5/int1/fail-first-unit.txt` (ImportError for `stamping_decision`; behavioural: on the pre-slice source all four consumers return the latest row `UUID(int=9)` instead of the process release); pass `.run/p5/int1/pass-unit.txt` (19 passed incl. the drift test) and `pass-suites.txt` (tests/unit + tests/architecture + `test_upgrade`: 959 passed, 4 privacy failures then reconciled → privacy + governed + architecture 90 passed; lane suites 83 passed; the 10 errors in `tests/unit` are database connection errors of DB-backed unit tests — `test_uow`, `test_lists`, `test_cli_*`, `test_time_zones` — no database on this worktree); `make typecheck` OK (mypy 582 files, tsc); `make lint` |

## NOT RUN (database-bound; first run is `make test-pg` after the merge)

- `tests/pg/test_migrations.py::test_single_head` (pin 0055) and `::test_upgrade_downgrade_upgrade` (the round trip
  that snapshots the new column, its default and `ck_engine_release__validation_level`), `::test_lint_after_upgrade`.
- `tests/pg/test_release_validation_level.py` (4): persisted declaration + restart + undeclared PATCH; a refusing
  decision stops stamping before the insert; column default and check (23514); the four consumers select the
  process's row against two persisted rows of the running version and fall back only when unstamped outside
  production. Written so that no test inserts a row of another engine version (it would become the previous
  global release for every later stamp in the shared database).
- `tests/api/test_me.py` (schema_revision pin 0055), `tests/pg/test_engine_release.py` (P1's; the row gains a column
  with a default, no assertion there enumerates columns), every DB-backed test that stamps through
  `support.factories.stamp_test_release` (same-version rebuild path, recorded, no floor).

## Measured on this worktree

| Check | Result |
|---|---|
| `tests/unit/test_release_level_and_stamping.py` + `test_consumer_release_identity.py` + `test_dg_arc_09_table_columns_match` | 19 passed |
| privacy catalogue + governed docs + `tests/architecture` | 90 passed |
| the nine lane suites | 83 passed |
| `tests/unit` + `tests/architecture` + `tests/engine/test_upgrade.py` | 959 passed before the privacy reconciliation (4 privacy failures fixed after), 10 DB-connection errors |
| `make typecheck` | OK |
| `make lint` | OK on both commits |

(Slice 1 measured at `700f311`; slice 1b rows below.)

## Codex runtime review of the lane head 9564d08a (relayed by the team-lead; folded into 1b)

`PRODUCTION-P5-INTEGRATION-REVIEW-9564d08.md` (SHA256 `c7ac5f45…`; manifest `5466d91b…`, 21 artifacts; raw
`6b95aa57…`): reviewed `9564d08a` (runtime `700f311b`, merge `9d041d31`, count-only `d5a18902`) — lane lineage,
NOT main integration. **67 controls, 63 pass / 4 fail.** The four failures are exactly the D-98 60 defect assigned
to slice 1b: all four consumer resolvers (computation, compute_job, journal, report) with `current_release() = None`
and `current_environment() = None` queried the latest release once, warned once and returned row B. **Oracle
satisfied at the 1b head:** `process_release_id` refuses before any fallback SELECT and before any WARN unless the
remembered environment is explicitly `dev` / `test` (unknown = production = refuse); `test_consumer_release_identity`
asserts the refusal with zero queries for the unremembered, `e2e` and `production` cases (fail-first on the pre-1b
code: "DID NOT RAISE Problem" ×4), and `test_release_level_and_stamping` asserts zero WARN through the injected
`warn`.

Passing and retained (Codex): explicit production refuses; stamped A vs newer same-version B; version mismatch;
dev / test fallback positives; all four new-row payload paths propagate the returned UUID (source evidence;
persistence unexecuted); consumer controls 28/32; native manifest parsing 10/10; pure floor 5/5; actual
`stamp_release` over seven hashed synthetic manifests with an inert `release_session` 14/14; retained preparation
3/3; emitted migration SQL 3/3; no harness adaptations.

Notes carried as stated (not claims):
- the global-predecessor query and its deterministic order (`deployed_at DESC, id DESC`) are verified, not
  concurrency — two simultaneous first stamps each see no existing row; the insert is `ON CONFLICT DO NOTHING`;
- restart uses `INSERT … ON CONFLICT DO NOTHING` and returns the supplied persisted level — **no physical
  no-new-row / immutability proof yet; owed:** a DB test that a restart adds no row and rewrites nothing, when a
  lane database exists;
- same-version new-build registration does not establish preparation authority (consistent with D-98 59's
  condition: the row starts `PENDING`; only `prepare_release_baseline` or a validation enables it);
- the reviewed provisional 0097 added only the `validation_level` column / CHECK, and the count-only correction adds
  no types — the six E-125 to E-130 PostgreSQL types and the bidirectional drift check are 1b's (`224a56a2`).

Not claimed or implied by this slice: no DB upgrade / backfill / grants executed, no real environment or manifest,
no per-tenant baseline, no replay / approval / report path, no gate / limiter / metrics wiring, no full P5
acceptance. Codex retests the unchanged oracles at the 1b head.

## Slice 1c (team-lead rulings on 1b; the last slice before the merge, which follows C4 in the group-2 order)

**Rulings recorded.** (c) RECORD + PENDING **ratified** — D-98 59's condition is met in the pure contract
(`initial_validation`: PENDING / enabled False / PATCH / `SAME_VERSION_REBUILD`; `persist_admission` refuses a PENDING
or absent row with `release-validation-pending`; the Codex R2 refusal kept in `check_declaration`); **the process-start
wiring — creating the T-PLT-43 row when a process of a new release starts — stays owed to the validation slice.**
(b) **accepted** — `FALLBACK_ENVIRONMENTS = {dev, test}`; unknown / unremembered / e2e / production fail closed;
`stamp_release` and `cli_services()` record the environment; **`e2e` fails closed by design — there is no e2e
fallback** (now stated in 05 REL-03 and DG-KRN-JOB-13 so it is not read as an omission).

**Alembic number assigned: 0055.** `0097_engine_release_validation_level.py` → `0055_engine_release_validation_level.py`,
`revision = "0055"`, `down_revision = "0054"` (P5 is the first migration-bearing lane to merge; P2, C1b, F-ADM, P4,
F-LMG and F-SNP re-parent at their turns). Applied everywhere in the worktree: the file, its docstring, the head pins
in `tests/pg/test_migrations.py` and `tests/api/test_me.py`, the architecture tests (`created[name].startswith("0055_")`,
`test_revision_0055_enum_literals_equal_the_mirrors`), the schema-revision literals of the unit tests, 04 §18 rule 9 /
T-PLT-38 / the lifted paragraph ("assigned at slice 1c; not applied to any database"), the privacy note, code comments,
this record. The revision is applied to no database by this lane: the dev database (`erev`, ports 8190 / 5270) is
migrated Ray-side after the merge and recorded by the team-lead.

**Committed artifacts that pin the Alembic head or the release identity — audit.**
- Root `release-manifest.json`: **gitignored and absent** from the tree (`git check-ignore` yes; REL-01 / DG-LAY-08). Nothing
  committed carries a manifest; `make ci` (`ci-gate` stages env, lint, typecheck, test, build) does **not** regenerate it;
  only `make release-manifest` / `make docker-build` (EMBEDDED) write it. A developer's *local* root manifest from an
  earlier `make release-manifest` names `0054` and is refused at startup by `facts_from_manifest` ("names another
  schema revision") until regenerated with P1's `scripts/release_manifest.py` — a local, not a committed, condition, so
  nothing was regenerated in 1c.
- `readyz` (`api/v1/health.py`) and `erev doctor` (`controls.doctor.observe_release` → `release_facts` → `code_head()`)
  compute the head live from the versions directory; no pin.
- `backend/tests/fixtures/manifest.json`, `docs/legacy/golden/manifest.json`, `research-harness/legacy-golden/*/manifest.json`
  are legacy-fixture file manifests (`path / sha256 / bytes`), not release manifests.
- Literal head pins: only the two tests above (now `0055`); every other test reads `code_head()`. `git grep 0054` outside the
  migrations directory and the review records finds no pin.
- Release identity: `support.factories.stamp_test_release` derives facts with an absent manifest path (build
  `tests-ctr-2`), no committed identity; `EngineRelease` / `ReleaseFacts` gained fields with defaults, no serialised shape
  changed (the `me` view keeps `engine_version`, `build_sha`, `schema_revision`).

**D-98 66 — the sixteen typeless mirrors, checked one by one against main's schema before listing.**
- **Finding 1 — E-04 `period_state` is not a pending type.** 04 T-REF-06 `period_state.state` and T-REF-07
  `from_state` / `to_state` are typed `erev.period_state`, but revision 0029 (RFD-2) implements them as `text` with a CHECK
  of the E-04 literals because table T-REF-06 owns the PostgreSQL row type `erev.period_state` (L1-1-Q-20; the code
  comment in `tables/reference.py`). An enum type of that name can never exist; 04's three column rows and the §3.4
  enumeration describe a type the schema deliberately does not have. Reported for a ruling (04 wording, or a differently
  named type); represented as `TEXT_CHECK_ENUM_TYPES` so the reverse check stays honest and green.
- **Finding 2 — E-82 `reporting_entity_type` has no typed column.** No 04 table types a column with it (REQ-REF-016 value
  list of the policy registry, T-PLT-31/32 values); no revision will create it unless a column appears. Reported;
  represented as `VALUE_ONLY_ENUM_TYPES`.
- **Fourteen pending entries** (`PENDING_ENUM_TYPES`, each with enumeration, table.column, owning item, planned revision):
  E-23 / E-24 / E-25 → T-CON-06 `modification` (CTR-17, `NNNN_ctr_17_modifications.py`); E-72 → T-INT-02 `sync_run.status`
  (DIN-12, `NNNN_din_12_integrations.py`; the table is not on main); E-73 / E-74 → T-AI-01 `ai_proposal` (AIX-1,
  `NNNN_ai_tables.py`); E-75 / E-76 → T-MIG-01 `migration_batch` (LMG-1, `NNNN_lmg_1_migration_batches.py`); E-83 / E-84 →
  T-CON-15 `contract_cost_asset`, E-85 → T-CON-17 `loss_provision_version.unit`, E-86 → T-CON-18
  `fx_layer_movement.movement_kind`, E-92 → T-CON-14 `material_right.option_type` (CTR-14,
  `NNNN_ctr_14_costs_material_rights_loss_fx.py`); E-100 → T-FC-01 `scenario.status` (FCS-1, `NNNN_forecast_tables.py`).
  None of those tables exists in `erev_api.db.tables`. Their 04 §3.4 rows carry "PostgreSQL type pending (owed by <item>,
  `<revision>`; D-98 66, rev 1.29)". Shrink-only: `type_gaps` reports a listed name whose type lands; no entry is added
  without a recorded ruling; nothing is marked API-only; no types created for other lanes' tables. Codex's label applies:
  source-qualified unfinished schema integration.

## Slice 1d (docs only; team-lead rulings on the two D-98 66 findings)

- **D-98 67 (E-04 `period_state`)** — 04 corrected, not the schema: T-REF-06 `state` and T-REF-07 `from_state` /
  `to_state` are typed text with a CHECK of the E-04 literals; the PostgreSQL row type `erev.period_state` belongs to
  table T-REF-06 (L1-1-Q-20), so an enum type of that name cannot exist; the §3.4 E-04 row says the value list is
  mirrored by the StrEnum and no PostgreSQL enum type is owed. `TEXT_CHECK_ENUM_TYPES` stands as the representation.
- **D-98 68 (E-82 `reporting_entity_type`)** — the §3.4 row says value list only (REQ-REF-016 policy-registry values,
  T-PLT-31 / T-PLT-32), no column types it, no type is owed unless a column appears (a ruling then).
  `VALUE_ONLY_ENUM_TYPES` stands.
- Applied inside the existing rev 1.29 scope (header entry and log row extended; no new revision number; no code
  change). Preflight: `test_governed_docs_revisions` + `tests/architecture` (replay twin); `make lint`.

## Codex correction retest at 9b6cb85d / runtime 224a56a2 (relayed by the team-lead) and slice 1e

`PRODUCTION-P5-CORRECTION-RETEST-9b6cb85.md` (SHA256 `c16faef2…`; manifest `7c1e8fa9…`, 28 artifacts). **Bounded D1
closure:** all four unknown-environment failures now refuse with `release-mismatch` and zero fallback SELECT / WARN.
Raw counts preserved as Codex reports them: the original 67 controls stay **raw 65/67** (two exact DDL-list expectations
predate the six added types); separate **28/28 supplements** verify the new DDL contract (upgrade = the old two ALTERs +
six CREATE TYPEs; downgrade = six reverse-order DROPs + the old ALTERs), six exact ordered label sets against 04 /
Python, E2E and unknown-string refusals, same-version rebuild planning (PENDING, disabled, `SAME_VERSION_REBUILD`) and
pure admission (refuses missing enablement; accepts supplied BASELINE / enablement facts); the original enum AST probe is
**raw 1/3** (its old exact diagnostic lists now receive additional correct missing-type diagnostics) with exact
diagnostic **supersets 3/3**. Never reported as 67/67; the AST results are not relabelled. Nothing claimed about real
rows, preparation, the persistence gate, upgrade, concurrency, a database or full acceptance.

Codex notes recorded: the all-migration recorder (`migration_enum_types`, 56 `upgrade()` replays under
`migration_ops.recording()`) was **not executed by Codex**; the fourteen pending enumerations have **no exact quoted
type-name occurrence in the frozen source** — source-qualified reconciliation debt, owned by the items named in
`PENDING_ENUM_TYPES`.

**Slice 1e (comments + record only; no semantics):**
1. The `enum_mirrors` docstring called the lists "a reconciliation list, not an exclusion" — corrected: every name in
   `PENDING_ENUM_TYPES` / `TEXT_CHECK_ENUM_TYPES` / `VALUE_ONLY_ENUM_TYPES` **is exempt** from the missing-type
   finding; the lists are explicit, shrink-only **exemption lists** in which every entry carries its disposition (owning
   item + planned revision, or the D-98 67 / 68 representation ruling), so no green count rests on an unexplained
   exemption.
2. The 1b-era rationale for `period_state` ("no table column uses the type yet") was **wrong** and is superseded: E-04 is
   the deliberate TEXT + CHECK representation (revision 0029, L1-1-Q-20; the row type `erev.period_state` belongs to
   table T-REF-06; the migration's CHECK labels equal E-04 / Python), exactly as 04 rev 1.29 (slice 1d, D-98 67) states;
   the helper's bullet and entry now mirror that wording. The 1b table above keeps its original text as history.

## Slice 1f — pg test-support probe release made REL-03 compliant (team-lead dispatch after F-CTR's chain; D-98 candidate 94)

**Interaction.** F-CTR's chain on cb3fc282 (main 316177c9) ERRORed `tests/pg/test_late_events.py::test_ctl_017_…` at
setup: `ReleaseManifestError: validation_level PATCH is refused at stamping (REL-03; D-96 (3)): '0.0.0-probe.<token>' is
not a MAJOR.MINOR.PATCH engine version (DG-ENG-10)`. Cause: `support.rows.engine_release_values` (unchanged since L4)
stamped probe releases with `engine_version = "0.0.0-probe.<token>"`; once such a row is the latest `engine_release`
of the shared test database (the DB-07 test writes probe rows first), the next `stamp_release` (the CTL-017 world
factory) takes the VERSION_CHANGE path and `semver_level` refuses the version. **Ruling (D-98 candidate 94):** the
stamping rule stays strict; the test support becomes compliant — plain semver version, probe identity elsewhere.

**Change (additive; `backend/tests/support/rows.py::engine_release_values`).** `engine_version = ENGINE_VERSION`,
`build_sha = "probe-<token>"`, `schema_revision = "probe"` (the marker, already in the row), `validation_level = "PATCH"`
(explicit). Why the running engine version and not the ruling's example `0.0.0`: the stamp that follows a probe insert
is the factories' *undeclared PATCH* of `ENGINE_VERSION` with a new build; against a `0.0.0` predecessor that is a
VERSION_CHANGE whose semver floor is MINOR (or MAJOR) → refused all the same ("below the semver floor"); against a
same-version predecessor it is a recorded SAME_VERSION_REBUILD (or a RESTART when the pair exists) — no floor, no
weakening of the refusal. Consumers grepped: `rows.py` internal helpers (`_computation`, `contract_computation_row`,
the subledger-line builder, `insert_report_run`, `report_run_row`) and `tests/pg/test_report_tables.py:155` — every one
inserts the row and reads only `id`; none reads the version string. `PROBE_ENGINE_VERSION = "0.1.0"` (computation rows)
is untouched. No governed document describes the probe release (`dev-guide` grep: none), so no docs-first edit.

**Tests.** `tests/unit/test_probe_release_support.py` (new, CPU, 2): the probe row is a compliant previous global
release — plain MAJOR.MINOR.PATCH, identity in `build_sha` / `schema_revision`, `declared_validation_level` PATCH,
`stamping_decision` → SAME_VERSION_REBUILD for the factories' next stamp and RESTART for a restart, two probe rows are
distinct pairs; and the documented refusal of a `0.0.0` predecessor ("below the semver floor"). Fail-first
`.run/p5/int1/fail-first-probe-release.txt` (the unchanged support: `'0.0.0-probe.…'`), pass `pass-probe-release.txt`.
The pg proof (`test_late_events` and every pg module that stamps after a probe insert) is DB-bound: **NOT RUN** on l12
(no lane database); F-CTR's next chain or the second integrated batch measures it.

**CPU gates on this tree, measured** (`.run/p5/int1/gates-probe.txt`, `unit-probe.txt`, `answer-keys-probe*.log`):
`make typecheck` rc 0 (mypy 602 files, tsc); `make lint` OK (the commit guard); `tests/unit` + `tests/architecture` +
`tests/engine/test_upgrade.py`: 1,142 passed, 10 errors, pytest rc 1 — the ten are the known DB-fixture errors (`test_uow`,
`test_lists`, `test_cli_*`, `test_time_zones`: the lane database does not exist), no failures; the release selection
`make answer-keys-gate ID=…` (inner target on the working tree, engine-only, no database): the tracked
`docs/reviews/loop/sprint/rg-selection.txt` **220 / 220 passed, rc 0** (184.98 s); the older 174-id
`.run/supervisor/rg-selection.txt` also 174 / 174, rc 0.

### Slice 1f, part 2 — CTL-029 run record (T1's GPB-3 chain, main 4ed5f423 + GPB-3, lane DB present)

**Failure.** `tests/domain/reports/test_framework.py::test_ctl_029_run_record_and_rerun`:
`{'build_sha': 'tests-ctr-2'} != {'build_sha': '7605b060…26d5961c70ea'}` at the `record["engine_release"]` assertion
(`~/dev/erev-wt/l9/.run/t1/gpb3/logs/ci.log`). Orientation matters: the **left** side is the run record — it carries
the fixture release the world stamped (`stamp_test_release()`, build `tests-ctr-2`, the process release under REL-03
rev 1.15); the **right** side is the test's own expectation — "the latest `engine_release` row of the running engine
version", which in a shared database is whatever row another module deployed last (here a derived row whose build is
the tree's 40-hex sha). `engine_version` was identical on both sides. So `reports.framework` writes the **correct**
identity: `_insert_run` stamps `current_release()` through `process_release_id`, and the view maps
`engine_version` → semver, `build_sha` → sha, nothing swapped. The test's expectation encoded the pre-D-96 rule and
had to follow the new stamping; 04 API-S-ReportRun already says `engine_release` is "of the running process" and 05
REL-03 rev 1.15 states the consumer rule, so no docs edit.

**Change.** Test: the expectation is the process release (`controls.release.current_release()` after the world is
built; `build_sha == RELEASE_BUILD`; `stored["engine_release_id"] == process.id`). Code, without weakening: the two
run-record sites (`RunStamp` in the output stamp, `EngineReleaseRefOut` in `run_outs`) now go through
`controls.release.release_identity(engine_version, build_sha)` — the semver must parse as MAJOR.MINOR.PATCH
(`controls.validation_level.parse_engine_version`, public), so a swapped pair is refused rather than rendered; the
fields stay distinct. CPU test `test_run_record_release_identity_keeps_semver_and_sha_distinct` (correct pairs,
`EngineReleaseRefOut` shape, three swapped / malformed pairs refused). The DB test itself is DB-bound — **NOT RUN** on
l12; F-CTR's or T1's next chain measures it.

## Slice P5-DOCTOR-R1 — doctor pg tests: the verification job's CTL-039 evidence failed closed (integrated batch on 065e7f65)

**Failure.** `run-065e7f65` test-pg: `tests/pg/test_doctor.py::test_req_ctl_005_doctor_passes_on_fresh_database` and
`::test_doctor_detects_failed_verification` — setup logs `job.retry_scheduled attempt=1 error_class=Problem
job_kind=AUDIT_CHAIN_VERIFY`; doctor prints "latest verification PASS for 0 of 1 tenants; 1 awaiting their first
verification"; after `tamper_audit_event` the tamper is not detected because no verification record was written.

**Diagnosis (CPU-reproduced).** `audit/verify.py` records CTL-039 evidence through `controls.evidence.record_execution`
(P4, SOP-1), whose `_release_id` resolves `process_release_id(current_release(), env=current_environment(),
engine_version=ENGINE_VERSION, latest_for_version=…)`. The doctor tests' `workspace` fixture only *inserted* a probe
`engine_release` row (`insert_engine_release`); the job runtime process never stamped, so `current_release()` and
`current_environment()` were both None → the **unremembered-environment branch** (D-98 60: unknown = production) refused
with `release-mismatch` **before any lookup** — the inserted row was never consulted, so this is not the version /
lookup mismatch (the probe row shares `ENGINE_VERSION` since D-98 94). Reproduced in
`tests/unit/test_evidence_release_identity.py::test_unstamped_process_fails_closed_before_any_lookup` (refusal, zero
queries); the same module shows the two ways out: a stamped process records its own row without a lookup, and only a
remembered `dev` / `test` environment falls back to the inserted row.

**Fix at the right layer (no weakening; production semantics untouched; doctor wording and the tests' assertions
unchanged).** The job runtime process must carry a stamped release, as REL-03 requires of every process that writes
`engine_release_id`: the `workspace` fixture now calls `support.factories.stamp_test_release()` — the shared pg
support the world factories use (`stamp_release(Environment.TEST, …, build_sha=RELEASE_BUILD)`, which also remembers
the environment) — before `_verify`; the probe-row insert stays (SOP-1 comment). `rows.insert_engine_release`'s
docstring states that a row is not a stamp. The CTL-039 producer itself is untouched (P4's). The CPU tests document the
diagnosed branch and pass on the current code by design — the defect is in the pg fixture, whose fix is DB-bound:
**NOT RUN** on l12 (no lane database); the batch's next run or a DB lane verifies "PASS for 1 of 1 tenants" and the
detected tamper.

## Slice P5-LOCK-R1 — activation takes the group lock before the contract lock (D-98 candidate 101a)

**Defect.** `activation.submit_activation` (contract row `FOR UPDATE` at ~706, then `lock_group` at ~717) and `activate`
(~790 → ~794) took the two locks in the INVERSE order of the compute and void paths (`compute_group`: `lock_group` →
`_update_heads`; F-CTR VOID-2b e3383f4e). Two paths taking the same two locks in opposite orders can deadlock (PostgreSQL
40P01) or interleave. Ruling: one order platform-wide — group first, then contract — for every path that takes both.

**Docs first (dev-guide row 1.36 — first drafted as 1.29, which the team-lead's assignment table holds for T1 (T1 1.29–1.31, C1b 1.32, P2 1.33, F-LMG 1.34, P1 1.35); renumbered in place in P5-LOCK-R2).** The order was
stated in the dev-guide, not in 04: DG-KRN-DB-08 (1) named the inverse "the `contract` conditional update, then
`combination_group … FOR UPDATE`" — it now names the ruled order (group row first, then the contract row(s) in ascending
id order; the group id read without a lock; membership re-verified under the locks; no pre-lock check is the last check)
and records that the previous wording was the order activation followed; the DG-CMD-02 example shows the order. 04 has
no sentence on the row-lock order (05 TXN-05 / RCP-22 describe the per-group advisory lock of computations), so 04 row
1.49 was not taken and 05 is unchanged.

**Code.** `activation._lock_group_then_contract(session, contract_id)`: unlocked read of the contract for its group id →
`repo.lock_group` → `repo.get_contract(for_update=True)` → membership re-verified (a contract that joined another group in
between is refused `precondition-failed` 412 with the new `REGROUPED` message, never processed on the wrong group); both
commands use it and keep every validation under the locks.

**Tests.** CPU (`tests/unit/test_activation_lock_order.py`, 3 in R1, 6 after R2): the repository calls are recorded and the command stopped
after its second lock — `submit_activation` and `activate` take `[get_contract(unlocked), lock_group, get_contract(FOR
UPDATE)]`; the membership re-check refuses a regrouped contract. **Fail-first on the pre-1.36 order** (first call
`get_contract(for_update=True)`): `.run/p5/int1/fail-first-lock-order.txt`. DB (`tests/domain/contracts/
test_activation_lock_interleaving.py`, NOT RUN on l12): a holder session takes the group lock, a thread submits the activation,
the holder then takes the contract row — immediate under the ruled order, a 40P01 deadlock under the inverse order
(deterministic after PostgreSQL's deadlock_timeout), then releases; the request reaches its own verdict.

**Other paths that take both locks (grep; reported, not changed in this slice).** Inverse order like activation:
`domain/contracts/estimates.py::_approve_version` (~1052 `get_contract(for_update=True)` → ~1054 `lock_group`) and
`domain/contracts/commands.py::replace_draft` (~597 → ~618). Already in the ruled order: `combination.py` (~583 / ~796
`lock_group` then `get_contract(for_update=True)` ~808), `compute_job.compute_group` (~520 `lock_group` → `_update_heads`),
the void path (VOID-2b). Single-lock paths (contract row only, no `lock_group`): `holds.py`, `locks.py`, `events.py`,
`imports/csv_v2/recorded.py`, `imports/legacy_v1/progress.py` / `modification.py`.

## Slice P5-LOCK-R2 — the two remaining inverse paths on the shared helper; dev-guide row renumbered 1.36

- **Renumbering.** Dev-guide 1.29 is T1's assigned row (T1 1.29–1.31, C1b 1.32, P2 1.33, F-LMG 1.34, P1 1.35): the P5
  row is **1.36** (header entry, log row, the two "rev" mentions in DG-KRN-DB-08, code / test docstrings, this record).
  The rule lives in the dev-guide only — F-CTR's 04 §16.1 request-void sentence already names the order for its path;
  04 row 1.49 stays unused.
- **Shared helper.** `repo.lock_group_then_contract(session, contract_id)` (moved from `activation`, with `REGROUPED`)
  — unlocked read for the group id → `lock_group` → `get_contract(for_update=True)` → membership re-verified (412
  `precondition-failed`, `REGROUPED`). Callers: `activation.submit_activation` / `activate` (R1),
  `estimates._approve_version` (the `ESTIMATE_VERSION` `on_approved` hook; was `get_contract(for_update=True)` ~1052 →
  `lock_group` ~1054) and `commands.replace_draft` (was ~597 → ~618; every check now runs under both locks; the later
  `lock_group` line removed).
- **Tests.** CPU `tests/unit/test_activation_lock_order.py` (+3 → 6): `_approve_version` and `replace_draft` take
  `[get_contract(unlocked), lock_group, get_contract(FOR UPDATE)]`, and the helper is the one order all three modules
  call. **Fail-first on today's order** for both paths (`.run/p5/int1/fail-first-lock-order-r2.txt`: first call
  `('get_contract', True)`). DB (`tests/domain/contracts/test_activation_lock_interleaving.py`, +2 → 3, NOT RUN on l12):
  `replace-draft` under the same holder-then-thread interleaving; and the shared helper under real locks, driven
  directly because the estimate-approval hook needs a submitted estimate version to be reached end-to-end — stated as
  such, not as an end-to-end approval interleaving.
- **Grep once more** (`get_contract(..., for_update=True)` followed by `lock_group` within a function, every module
  that calls `lock_group`): **nothing left**. Group → contract already: `combination.py`, `compute_job.compute_group`,
  the void path. Single-lock (contract row only): `holds.py`, `locks.py`, `events.py`, `imports/csv_v2/recorded.py`,
  `imports/legacy_v1/progress.py` / `modification.py`.

## Slice P5-LOCK-R3 — the order platform-wide, by lock EFFECT (D-98 candidate 101b; Codex packet 1124)

**Codex's finding.** The R1 / R2 inventory was lexical (`lock_group` callers) and missed IMPLICIT locks and TRANSITIVE
callers: `events/stream.py::append_events` runs `_raise_head` (UPDATE `contract` :278 — an implicit contract row lock)
then `_mark_dirty` (UPDATE `combination_group` :320 — an implicit group row lock AFTER the contract); every entry path
that had locked the contract and then appended took contract → group. Source-derived cycle: A in `record_events` holds
C (`_locked_contract` :475), B in the reordered `submit_activation` holds G and waits for C, A's `_mark_dirty` waits for
G → deadlock (a source inference, not reproduced on PostgreSQL by Codex).

**Inventory by lock effect** (every unit of work touching both rows; explicit FOR UPDATE, implicit UPDATE, transitive):

| Path | Before R3 | Now |
|---|---|---|
| `events/stream.py::append_events` → `_raise_head` (UPDATE contract :278) → `_mark_dirty` (UPDATE group :320) | implicit contract → group inside every appender | unchanged; every appender below holds the group lock first |
| `computation.persist` → `_update_heads` (UPDATE group :952, UPDATE contract :957) under `compute_group`'s `lock_group` (compute_job :520) | group → contract | unchanged (already ruled order) |
| `domain/contracts/events.py::record_events` (:824 `_locked_contract` :475) → `append_events` :830 → `compute_group` :841; `request_preview` (:984) | contract → group | `_locked_contract` → `repo.lock_group_then_contract` |
| `domain/contracts/holds.py`: `_locked` (:176; `apply_hold` / `release_hold` → append :286 / :330), `apply_system_hold` (:353 → :363 → `compute`), `release_system_holds` (:388 → :394), `apply_rule_holds` (:509 → :571) | contract → group | all four → the helper |
| `domain/contracts/locks.py::update_memos` (:145 → append :177) | contract → group | helper |
| `domain/imports/csv_v2/recorded.py::append` (:135 → append :161 → compute :170); `legacy_v1/progress.py::apply` (:538 → :554 → :569); `legacy_v1/modification.py::apply` (:569 → :623 → :635) | contract → group | helper |
| `domain/contracts/estimates.py::create_version` (:658 `_visible_contract(for_update=True)`; no group effect today) | contract only | `_visible_contract(for_update=True)` → helper (one order, no future drift) |
| `approvals/subjects.py::_apply_event_submission` (SELECT contract … FOR UPDATE :983 → append :996) | contract → group | kernel helper (`erev_api.db.locking`) — the approvals kernel cannot import the domain |
| `domain/policies/overrides.py::_apply_ssp_override` (unlocked head read :554 → append :589: `_raise_head` then `_mark_dirty`) | implicit contract → group | helper before the append; expected head from the locked row |
| `activation.submit_activation` / `activate`, `estimates._approve_version`, `commands.replace_draft` | R1 / R2 | helper (now the kernel one via `repo`) |
| `combination.py` (`lock_group` :583 / :796 / :870 then member contracts :389 / :808; `_change` append :683; UPDATE contract :727 / group :746) | group → contract | unchanged; allowlisted in the source guard |
| `commands.book_contract` (:427 append), `commands._follow_inception` (UPDATE group :561), `imports/legacy_v1/contract_setup.py` (:345 / :946 append) | rows created in the same unit of work — invisible to other sessions, no contention | unchanged |
| `policies/judgements.py` (unlocked group id :438 → UPDATE group :444 → `compute_group` :455) | group only | unchanged |
| `platform/provisioning.py`, `auth/mfa.py`, `audit/*` `append_events` | the audit chain's `append_events`, not the contract stream | out of scope |

**Kernel helper.** `erev_api/db/locking.py::lock_group_then_contract(session, contract_id)` (with `REGROUPED`): unlocked
read of `contract.combination_group_id` → `SELECT combination_group … FOR UPDATE` → `SELECT contract … FOR UPDATE` →
membership re-verified (412 `precondition-failed`). `repo.lock_group_then_contract` / `repo.REGROUPED` re-export it, so
every R1 / R2 caller is unchanged; `approvals.subjects` imports the kernel module (DG-LAY-03: kernel never imports the
domain). Membership revalidation, If-Match and authorization checks are untouched: they still run after the locks.

**Tests.** CPU `tests/unit/test_activation_lock_order.py` rewritten around a statement-recording Session stand-in (which
table, FOR UPDATE or not; the helper's three statements answered; stop at the contract row lock): ten entry paths
(activation ×2, replace_draft, record_events, request_preview, apply_hold, apply_system_hold, release_system_holds,
update_memos, `_apply_event_submission`) + estimate approval + estimate version creation take
`[contract (unlocked), combination_group FOR UPDATE, contract FOR UPDATE]`; membership re-check; the helper is shared.
**Fail-first on today's order** (`.run/p5/int1/fail-first-lock-order-r3.txt`): the first recorded statement is the
contract row FOR UPDATE. CPU source guard `tests/architecture/test_lock_order.py`: outside `db/locking.py`, `repo.py`
(the primitive) and `combination.py` (group first, allowlisted with the reason) no module locks a contract row directly —
red on the pre-R3 tree, green now. DB (`tests/domain/contracts/test_activation_lock_interleaving.py`, +1 → 4, NOT RUN
on l12): the actual path — `POST /contracts/{id}/events` (BILLING on a seat-world contract, the append that reaches
`_mark_dirty`) while the holder has the group and then takes the contract row: 40P01 on the pre-1.36 order,
immediate on the ruled one.

**Docs first (dev-guide 1.36, in place).** DG-KRN-DB-08 (1) gains "including implicit `UPDATE` locks and transitive
callers" with the mechanism (`_raise_head` / `_mark_dirty`; every entry path takes the group lock first through
`erev_api.db.locking.lock_group_then_contract`); the 1.36 row records R3.

### P5-LOCK-R3b — Codex packet 1130: the combination paths and deterministic interleaving evidence

- **Codex's inventory (`PRODUCTION-P5-LOCK-DOCTOR-SOURCE-REVIEW-4fae8ff0.md`, c6b2f4f7…).** The four R1 / R2 callers and
  the doctor stamping are source-correct. Named paths to cover: the transitive memo / hold / import append paths (done in
  R3 above) and `combination.apply_combination` — destination group first (:796), contracts (:808), then `_change` (:683)
  appends against each member's CURRENT group (`_mark_dirty` on the original group) and `_dirty` (:746 / :819) updates
  the former group after the contract lock; a leave also moves members into singleton groups.
- **Fix.** `combination._lock_groups_then_contracts(session, group_ids=…, contract_ids=…)`: every group row the unit of
  work will update — the target, each member's original group, the leave singletons — `FOR UPDATE` in ascending id
  order, then the member contracts in ascending id order, each member's group re-verified against the locked set
  (`REGROUPED`). `apply_combination` reads the members and singleton ids without locks after `_review`, then locks the
  other groups (the target is already held) and the contracts through the helper; `_visible_contracts` (submit_group)
  locks the proposal's contracts in ascending id order through the same helper. Existing relative orders untouched: the
  target group lock still precedes the proposal (judgement record) lock, because `judgements._recompute_contract` marks a
  group dirty after its own record lock and moving the proposal read ahead of the target lock would invert that pair.
  **Residual (stated):** two concurrent combinations whose targets are each other's originals (members moving in both
  directions at once) can still cross (target-first, then the others sorted); PostgreSQL detects and aborts one (40P01)
  and the approval hook is retried — an exotic schedule, not silent interleaving. **WITHDRAWN in P5-LOCK-R3c (D-98 candidate 101c; Codex's sealed R3b
  source review): the automatic retry does not exist — the synchronous chain `api/v1/approvals.py` → `api/deps.py
  run_command` → `approvals/engine.py decide` → the subject hook rolls back and rethrows, `problems.py` had no 40P01
  mapping (a 500, which `_settle_failed_command` abandons — a mapped 409 is STORED, see R3d) and the frontend sends
  once. R3c removes the
  schedule itself (one globally ascending order over every group row, the target included) and maps a residual
  40P01 to 409 `lock-conflict`, resubmitted by the client.**
- **Deterministic interleaving evidence (all four DB cases).** `_interleave` no longer sleeps: it polls
  `pg_stat_activity` (same role and database) until another backend is blocked with `wait_event_type = 'Lock'` in a
  statement against `combination_group` — the request's `SELECT … FOR UPDATE` under the ruled order, its
  `UPDATE combination_group` (`_mark_dirty`) under the old one — and only then takes the contract row (immediate under
  the ruled order; 40P01 under the old). The R1 activation case now uses the same helper. Still NOT RUN on l12.
- **Tests.** CPU: `test_combination_locks_every_touched_group_before_the_member_contracts` (groups sorted first, then
  contracts, membership refusal); the source guard's combination allowlist narrowed to the helper (`test_combination_
  locks_contracts_only_inside_its_group_first_helper`: one direct lock site, after the helper's group locks) — red on
  the pre-R3b module (`.run/p5/int1/fail-first-lock-order-r3b.txt`). Docs: dev-guide 1.36 (in place) gains the
  multi-group clause.

### P5-LOCK-R3c — Codex packet production-20260920-1150 item 3: the R3b callers refused every ordinary proposal

- **Finding (Codex, a deterministic source-path reading at d2b1cdc3, not an executed DB result; confirmed here on the
  same lines).** `_visible_contracts` (:409) passed `group_ids=()` to `_lock_groups_then_contracts`; the helper builds its
  group map from the supplied ids only (:398) and then refuses every contract whose current group is not in the map
  (:401–402) — so every nonempty proposal was refused `precondition-failed`: `create_group` (:514) and both `submit_group`
  branches, JOIN (:609) and LEAVE (:647). `apply_combination` passed `touched - {group_id}` (:845–846): a leave's members
  belong to the target, so an ordinary approved LEAVE was refused too. A genuine R3b regression.
- **Why R3b's evidence missed it.** The CPU helper test drove `_lock_groups_then_contracts` with matching ids; the unit
  stand-in stops at the contract lock — before the membership check — for the entry paths; and the real-path DB tests
  (`tests/domain/contracts/test_combination.py`) are NOT RUN on l12 (no lane database). Recorded as a lesson: a helper
  test proves the helper, never the caller's argument set.
- **Fix.** `_visible_contracts` reads the proposal's contracts without locks for their CURRENT groups, locks those groups
  through the helper (ascending id order; a submit's target, already held, re-locks as a no-op), then the contracts
  (ascending), membership re-verified — an unmoved population is accepted; a contract that moved to a group outside the
  set is refused `REGROUPED`, the intended refusal (every locked contract's current group is held). `apply_combination`'s
  lock step is extracted to `_lock_members(session, group_id=…, proposal=…)`; its set is `{target} ∪ members' current
  groups ∪ leave singletons` — the target stays in (held above; the re-lock is a no-op) so a leave's members pass the
  check. Group-before-contract, every touched group ascending, membership revalidation: unchanged. No governed-doc
  change (the rule text describes exactly this; the defect was the callers' argument sets).
- **Tests (CPU, `tests/unit/test_activation_lock_order.py`, +4 → 19 in the module; the stand-in now records the locked
  group ids from each statement's bound parameter and answers unlocked group reads and the approval-request read).**
  `test_visible_contracts_lock_their_own_groups_before_the_contracts` — the real function: unlocked contract read, group
  lock, contract lock (`RULED_ORDER`), `locked_groups == [GROUP]`, population accepted, visibility checked once — RED on
  the pre-R3c module with `precondition-failed` (the regression itself).
  `test_apply_combination_lock_step_holds_every_touched_group[JOIN|LEAVE]` — `_lock_members`: JOIN locks
  `[GROUP, OTHER_GROUP]` (original, then the held target), LEAVE `[GROUP, SINGLETON]` (target, then the singleton looked
  up by code), then the contract; singletons map returned — `AttributeError` on the pre-R3c module (the function is new;
  not a behavioural red). `test_apply_combination_hands_the_held_target_to_the_lock_step` — the real `apply_combination`
  to its lock step (`_proposal` / `_review` / `_system_unit` stubbed; the helper replaced by a recorder that stops):
  handed `({GROUP, SINGLETON}, [CONTRACT])`, the target locked first — RED on the pre-R3c module: handed `{SINGLETON}`
  without the target (the leave regression itself). `.run/p5/int1/fail-first-lock-order-r3c.txt` (4 failed);
  `.run/p5/int1/pass-lock-order-r3c.txt` (26 passed: this module 19, architecture guard 2, evidence identity 3, probe 2).
- **Real-path DB proof (NOT RUN on l12; the integrated batch).** `test_combination.py::_combine` — `POST
  /combination-groups` 201 (`create_group`) → `POST …/submit` 200 (`submit_group` JOIN) → approve → `apply_combination`
  JOIN — under `test_combination_by_approved_command_reruns_group`; `test_uncombine_only_as_approved_error_correction`
  (`submit_group` LEAVE branch → approve → `apply_combination` LEAVE); `test_cross_currency_combination_rejected`
  (`create_group` validation 422 — under R3b it returned 412 first). All three would have failed the batch under R3b.
- **Codex's items left OPEN, not closed here:** target-first cross-group order, the actual retry behaviour behind the
  stated 40P01 residual, deterministic wait matching — Codex's independent review is ongoing and the residual is not
  closed from the CPU helper test or the documentation claim of a retry.
- **Deterministic wait-state confirmation (team-lead's ask).** Re-read `test_activation_lock_interleaving.py`: the only
  `sleep` is the poll interval inside `_await_lock_wait`'s `pg_stat_activity` loop (:97); `_interleave` awaits the blocked
  backend (`wait_event_type = 'Lock'` on a `combination_group` statement, :123) before `is_alive` (:124) and the holder's
  contract lock; all four cases go through `_interleave` (:72, :143, :171, :210). No case sleeps for a settle period.
- **Source guard, for the record (team-lead).** `tests/architecture/test_lock_order.py` will flag other lanes' direct
  contract row locks as they merge; F-CTR's `void.py` adopts `erev_api.db.locking.lock_group_then_contract` at its merge
  prep.
- **Gates.** ruff (format, import order, check) on the changed files; `make typecheck` (605 source files, no issues);
  CPU 26 passed; `make lint` before the commit.

## Slice P5-DOCTOR-R1b — the process stamp at every test JobRuntime that runs an evidence-writing job (batch ci: `test_verify_on_demand_returns_job`)

- **Symptom (team-lead, integrated batch ci).** `tests/api/test_audit_api.py::test_verify_on_demand_returns_job` —
  `ValueError: not enough values to unpack (expected 1, got 0)` at :213: no T-PLT-23 row. The on-demand
  `AUDIT_CHAIN_VERIFY` handler's CTL-039 `record_execution` failed closed (`release-mismatch`, D-98 60) because the test's
  `runtime` fixture (:79–80) built a `JobRuntime` in a process that never stamped. Same shape as P5-DOCTOR-R1.
- **Mechanism (read from source; an inference about the batch, not a measured run).** `conftest._forget_stamped_release`
  (autouse) clears the remembered release after every test but not the remembered environment; `process_release_id`
  with no release and a remembered TEST environment takes the latest-per-version fallback, while an unremembered
  environment fails closed. So a module whose runtime never stamps passes or fails with the order and worker placement
  of the tests that ran before it — `test_audit_api.py` sorts first in `tests/api`. **That is why the failure was
  intermittent:** it appeared in the batch's ci stage and vanished whenever a stamping test had run earlier in the
  same worker process. Explicit stamping at the runtime construction makes each test order-independent. Producer,
  doctor and assertions untouched (the DOCTOR-R1 rule).
- **Inventory — every `JobRuntime(` construction under `tests/api`, `tests/domain` (and `tests/support`), by what its
  jobs record.** Evidence producers (`controls.evidence.record_execution` callers): CTL-039 `audit/verify.py`
  (`AUDIT_CHAIN_VERIFY`, also SCH-02 `security_chain_verify`), CTL-012 `contracts/compute_job.py` (`CONTRACT_COMPUTE`;
  `compute_group` is also called in-process by `policies/judgements.py`), CTL-001 / CTL-044 `imports/commit.py`
  (`IMPORT_COMMIT`), CTL-022 `journals/summarise.py`, CTL-029 / CTL-030 `reports/framework.py` (`REPORT_RUN`).
  - *World factories that stamp:* `k11_world`, `k02_world`, `j03_world`, `seat_world` (factories), `report_world`
    (worlds; `k01_pellworth`, `k02_marrowby` through it), `legacy_world` (legacy_replay; `journal_world` through it),
    parity `scenario.build`. Modules whose evidence-writing runs ride on them, no change: `test_events_api`,
    `test_report_runs`, `test_compute_job`, `test_estimates`, `test_exception_queue`, `test_commit` (`j03` /
    `contract_importer`), csv_v2 `test_invoices` / `test_templates` (through `importer(place)`), `test_diff`,
    `test_period_states`; `test_framework` and `ssp/test_calculator` stamp explicitly already.
  - *Runtimes that run only non-evidence kinds, no change:* `OUTBOX_RELAY`, `WEBHOOK_DELIVERY`, `RETENTION_SWEEP`,
    `POLICY_SIMULATION` (`simulation.py` records nothing), patched `REPORT_RUN` / `CONTRACT_COMPUTE` handlers, deferred-only
    `AUDIT_CHAIN_VERIFY` — `test_jobs_api`, `test_webhooks_api`, `platform/test_jobs`, `test_outbox`, `test_webhooks`,
    `test_retention`, `test_support_grants`, `policies/test_presets`, `policies/test_registry_versions`.
  - *Unstamped by design, untouched:* `platform/test_release_stamping.py`.
  - **FIXED — `stamp_test_release()` at the runtime construction:** `tests/api/test_audit_api.py` `runtime` fixture
    (`AUDIT_CHAIN_VERIFY`, CTL-039); `tests/domain/platform/test_audit_verification.py` `runtime` fixture (CTL-039 for
    every `_verify` case and SCH-02); `tests/domain/platform/test_job_monitoring.py::test_krn_job_04_chain_verification_
    heartbeats` (the one real `AUDIT_CHAIN_VERIFY` run in that module; the other `_runtime` uses feed `fail_stalled`);
    `tests/domain/imports/test_mapping_profiles.py` `world` fixture (`run_import_job` → `IMPORT_COMMIT`, CTL-001 / CTL-044;
    builds its `ImportWorld` from a bare member); `tests/support/factories.py::import_world` (the one world factory that
    never stamped; its runtime runs `IMPORT_COMMIT` — covers `test_commit.py`'s `world` cases and csv_v2
    `test_fx_rates_csv_creates_version_for_approval`).
- **Fixture placement.** Not a `tests/api` conftest: one API module needs it, and every module that defines its own
  `runtime` would shadow a shared one anyway. The two `runtime` fixtures now depend on `committed_db` explicitly so the
  stamp's row lands in the test database before the job runs (function-scoped ordering made explicit).
- **Evidence.** DB NOT RUN on l12 (no lane database) — the proof is the next integrated batch. The CPU reproduction of
  the fail-closed producer remains `tests/unit/test_evidence_release_identity.py` (3 passed, in
  `pass-lock-order-r3c.txt`); the five touched modules import and collect (`--collect-only`: 25 tests across
  `test_audit_api`, `test_audit_verification`, `test_job_monitoring`, `test_mapping_profiles`, `test_commit`); ruff and
  `make typecheck` green; `make lint` before the commit.

## Slice P5-LOCK-R3c (D-98 candidate 101c) — Codex's sealed R3b source review: the order without a retry, equality, the subject content, the participant-bound wait, the certified cause

Team-lead ruling on `PRODUCTION-P5-LOCK-R3B-SOURCE-REVIEW-d2b1cdc3.md` (SHA256 c28ab8e4…): five items, all in R3c
before re-entry. Docs first (`64c7b7d6`: dev-guide 1.36 in place, 04 rev 1.49 assigned, PRD 1.11 provisional), then
the code (this commit).

- **(a) No automatic retry — the record corrected, the order resolved without one.** The R3b residual bullet claimed
  "the approval hook is retried"; Codex traced the synchronous chain (`api/v1/approvals.py` 214–227 → `api/deps.py`
  360–384 `run_command` → `approvals/engine.py` 874–875 `decide` → `approvals/subjects.py` 2243–2255 → the hook rolls
  back and rethrows; `problems.py` had no 40P01 mapping, so 500; `_settle_failed_command` 300–324 abandons the attempt;
  the frontend sends once). The bullet is marked WITHDRAWN in place (kept for the record). The order is now one
  **globally ascending id order over every `combination_group` row a unit of work touches, the target included** —
  `combination._lock_groups_then_contracts(session, group_ids=…, expected=…, between=…)` sorts `group_ids ∪
  expected.values()` and locks them; a caller never takes the target first (`submit_group` reads the group WITHOUT a
  lock to pick its branch, `apply_combination` reads the proposal WITHOUT a lock, and both pass the target's id into
  the set); **then** the proposal record (`between`: `_proposal(lock=True)` re-read and compared with the unlocked
  read — a difference is `precondition-failed` `PROPOSAL_CHANGED`; the status re-checked under the lock; the leave's
  membership checked there too); **then** the contracts ascending. `judgements.submit_judgement` / `review_judgement`
  join the order through `_locked_record`: the record is read unlocked for its contract, the kernel helper locks the
  contract's group, `between` locks the record, then the contract — the hold and the recompute that follow re-lock held
  rows (`erev_api.db.locking.lock_group_then_contract(session, contract_id, *, between=None)` gains the hook). A
  residual 40P01 is mapped in `problems.from_db_error` (`db/errors.DEADLOCK_DETECTED`) to **409 `lock-conflict`**
  (catalogue row, PRD ERR-52 copy "Another change to the same records was being saved at the same moment, so nothing
  was saved. Resubmit the request."; DG-KRN-ERR-02) — the client may resubmit; no automatic retry. The guide's
  "globally ascending" sentence is true for every path: the kernel helper (one group), the combination helper (the
  sorted set), `compute_group` (one group), `close_combination` (one group, then its record), the judgement paths
  (one group, the record between, the contract).
- **(b) Equality.** The combination helper takes `expected: {contract id: group id observed at the unlocked read}` and
  refuses `REGROUPED` when the row under the lock names any other group — presence in the locked set is not the check
  (`test_membership_revalidation_proves_equality_not_presence`: the new group is locked too and the refusal stands).
  The kernel helper already compared with the observed id; its docstring now says so.
- **(c) Subject content.** `approvals/subjects.combination_group_content` gains `members[]`
  `{contract_id, combination_group_id, head_stream_version}` for the submitted proposal's contracts (ascending id);
  `judgement_record_subject_content` (new; the `JUDGEMENT_RECORD` spec's `content`) is the record's reviewed content
  plus `contract {combination_group_id, head_stream_version}` when the record names a contract — the record's own
  T-CON-19 `content_sha256` stays `judgement_record_content`. Request time and decision time hash the same function
  (`engine.submit` / `current_content_sha256`), so a member moved or appended in between voids the request
  `STALE_SUBJECT` and the decision answers 409 `stale-approval` (the D-98 92 pattern). Stated in 04 §16.10 (rev 1.49).
- **(d) The wait bound to the participants.** `_interleave` registers a `checkout` listener on the app engine while the
  interleaving is open and records `pg_backend_pid` of every connection checked out (the request's; the holder's own
  is excluded by pid); `_await_lock_wait` polls `pg_stat_activity` for one of THOSE pids with `wait_event_type =
  'Lock'` and the holder's pid in `pg_blocking_pids(pid)`, returns the blocked backend and its statement, and the test
  asserts the statement is against `combination_group`. No same-database waiter outside the two participants can
  satisfy it. One helper, all four cases (DB NOT RUN on l12).
- **(e) The cause certified.** `tests/api/test_audit_api.py::test_verify_on_demand_without_a_stamped_release_fails_closed`
  runs the on-demand verification with a JobRuntime in a process whose release AND environment are unremembered
  (monkeypatched to None), drives every attempt of `VERIFY_RETRY` (3), and asserts `job.state == FAILED`,
  `job.problem.type == …/release-mismatch`, `status == 503`, and no T-PLT-23 row — the stamping refusal itself, not an
  inference from `runtime.engine_release is None` (DB NOT RUN on l12).

**Tests.** CPU (`.run/p5/int1/fail-first-101c.txt`: 11 red on the pre-101c source with the docs already in place —
`test_dg_arc_09_problems_equal_15_2` (49 ≠ 48), `test_dg_arc_13_err_rows_cover_slugs` stays in the run, the deadlock
mapping, the equality refusal, the helper's sorted set + `between` position, `_visible_contracts` (accepting; target in
the sorted set), `_lock_members` JOIN / LEAVE, the `apply_combination` driver (the target handed in the set, nothing
locked before the helper), the two judgement paths; `.run/p5/int1/pass-101c.txt`: 47 passed — unit lock-order 24,
problems 9, evidence identity 3, probe 2, copy-catalogue drift, data-model drift, architecture lock guard). The
stand-in now answers `judgement_record` reads, distinguishes the target's unlocked read from a singleton lookup by
the bound id, records DML tables, and `JUDGEMENT_ORDER` = record read, contract read, group lock, record lock, contract
lock. Pins: `test_copy_catalogue_drift` 48 → 49 slugs / ERR-01..52; `test_data_model_drift` 48 → 49 rows. DB (NOT RUN
on l12; the integrated batch): `test_combination.py::test_join_approval_is_stale_after_a_member_event`,
`::test_leave_approval_is_stale_after_a_member_event`, `test_judgements.py::test_review_is_stale_after_a_contract_event`
(a BILLING event appended to a member / the judged contract between the request and the decision → 409
`stale-approval`, VOIDED `STALE_SUBJECT`, nothing applied), the four interleaving cases on the bound predicate, the
fail-closed verification case, and the existing real-path cases (`_combine` create → submit → JOIN, the LEAVE
correction, cross-currency 422). Gates: ruff; `make typecheck` (605 files); `make lint` before the commit.

**Left open, as ruled:** Codex's independent review of the residual schedule continues; nothing here closes it from a
CPU test or a documentation claim. Numbers: PRD 1.11 CONFIRMED by the team-lead on acceptance of 1fb8491a (F-CTR,
merging after P5, takes 1.12); 04 1.49 as assigned; dev-guide 1.36 in place. Sequencing (wave-3 protocol): P5
re-merges the current main head immediately before its turn, after P1 lands — header cells united (dev-guide
strictly descending with 1.36 in place; 04 with 1.49; PRD with 1.11), lint + governed-docs tests, statuses
re-captured, READY reported.

## Slice P5-LOCK-R3d (D-98 candidate 101d) — Codex packet 1304: the approved basis, captured after the system hold and re-validated under the locks; the stored 409

Supervisor ruling D-98 candidate 101d on Codex's sealed review of 9f9e9e08 (`PRODUCTION-P5-LOCK-R3C-SOURCE-REVIEW-9f9e9e08.md`,
SHA256 ef8225d3…; 33-artifact manifest beeeb656…): the approved basis is captured after every system-side mutation of the
subject in the same unit of work (hold before hash) and re-validated under the protecting locks immediately before
application; the mapped 409 `lock-conflict` is a stored terminal status. Both findings re-verified on 2b99c354 by reading
the lines (`judgement_record_subject_content` 1071–1088 carries the head; `submit_judgement` hashed at `approvals.submit`
then held; `engine.decide` compared at ~801 and called the hook at ~875 before any of its locks). Docs first: dev-guide
**1.40** (assigned; 1.36 untouched, 1.39 is F-RPS's): DG-KRN-APR-05 gains the basis rule; DG-KRN-DB-08 and DG-KRN-ERR-02
replace the wrong "`_settle_failed_command` abandons the attempt" with what the code does. No other governed document.

- **(1) SELF-STALE-R1 — hold before hash.** `approvals.submit` evaluates the AUTO_APPROVAL rule from facts that never
  include the subject's content (subject type, preparer roles, setup state, source channel), so that evaluation is
  factored into `engine.auto_approval_rule(uow, subject_type, *, auto_approval=True)` — `submit` uses it unchanged — and
  `judgements.submit_judgement` calls it BEFORE hashing: a contract / obligation record that will wait for a person
  applies the REQ-POL-010 hold first (`HOLD_APPLIED` raises the head), then `approvals.submit` hashes
  `judgement_record_subject_content` with the new head. The post-submit hold block is gone (its `status == PENDING`
  condition is the same evaluation). Controls kept: `apply_system_hold` still answers None for a non-ACTIVE contract and
  the open same-reason hold without a new event; an auto-approved record never holds (the review would release it at
  once). Codex's reading was right: before this, the first unchanged approval of an ACTIVE contract's judgement voided
  STALE_SUBJECT with no external edit; the R3c stale-judgement test used `activate=False` and missed the branch.
- **(2) WAIT-FRESH-R2 — the basis re-validated under the locks.** `engine.assert_fresh_basis(uow, approval_request_id)`
  recomputes `current_content_sha256` and compares it with the request's stored `subject_content_sha256`; a difference
  raises `StaleBasis` (a `Problem`, slug `stale-approval`). Called by `apply_combination` after `_lock_members` (every
  group, the proposal record, the contracts) and before `_review`, and by `review_judgement` after `_locked_record`
  (group, record, contract) and before the REVIEWED transition. `decide` catches `StaleBasis` from `on_approved` and
  `_refuse_stale_basis` discards the decision and the hook's partial work (`uow.discard()`), re-locks the request, voids
  it `STALE_SUBJECT` exactly as the pre-lock check does, commits the void (REQ-PLT-014: the void survives the 409) and
  raises 409 `stale-approval`. The order, the equality check and the no-retry stance are unchanged; the auto-approval
  path (hook inside `submit`) compares the just-stored hash and passes. Not extended to the other hooks
  (`activation.activate`, `estimates._approve_version`, `_apply_event_submission`, `_apply_ssp_override`) in this slice
  — their content functions were not re-read for fields the decision itself changes before the hook; listed as an open
  candidate for the team-lead, not claimed.
- **(3) Wording.** DG-KRN-DB-08: a 409 `lock-conflict` is KEPT by `run_command` as the command's first response under its
  `Idempotency-Key` (DG-KRN-IDEM-03: only 401 / 403 / 409 `idempotency-in-progress` / 412 / 428 / 429 and 5xx are not
  kept) — a resubmission with the same key replays it (`Idempotent-Replay`), the client resubmits with a new key, which
  runs the command afresh; no automatic retry (the chain named without the abandon claim). DG-KRN-ERR-02 says the same
  in one sentence. The R3b WITHDRAWN bullet above is corrected too (the abandon applied to the unmapped 500).
- **Test support.** The participant-bound wait machinery moved to `tests/support/interleave.py`
  (`observing_checkouts()`, `backend_pid()`, `await_lock_wait()`, `RequestBackends`); the four interleaving cases use it.

**Tests.** CPU (`tests/unit/test_activation_lock_order.py`, 29 in the module; stand-in: `record` / `request` overrides,
`rowcount`, a principal stub and `audit()` on the unit-of-work stand-in): `test_submit_judgement_holds_the_active_
contract_before_the_basis_is_hashed` (order `["hold", "submit"]`, the record's locks first) — **red on the pre-101d source
by behaviour: `['submit'] == ['hold', 'submit']`**; `test_submit_judgement_never_holds_for_an_auto_approved_record` (a
control: passes on both, not evidence); `test_assert_fresh_basis_refuses_a_changed_subject` (`StaleBasis`, slug
`stale-approval`; unchanged passes) — red by `AttributeError` (the function is new); `test_apply_combination_revalidates_
the_basis_under_every_lock` (the check runs with `[contract F, group F, group T, group T, contract T]` recorded and
`_review` not yet called) — **red by behaviour: "applied before the basis check"**; `test_review_judgement_revalidates_
the_basis_under_every_lock` (`JUDGEMENT_ORDER` recorded at the check) — red (the pre-101d path ran on into `_supersede`).
`.run/p5/int1/fail-first-101d.txt`: 4 failed, 1 passed (the control), source stashed 2026-09-20T13:17:33Z, restored
13:17:35Z; `.run/p5/int1/pass-101d.txt`: 52 passed at 13:18:20Z (unit lock-order 29, problems 9, evidence identity 3,
probe 2, both drift modules, the lock guard). DB (NOT RUN on l12; the integrated batch): `test_judgements.py::
test_active_pending_judgement_holds_first_then_approves_unchanged` (HOLD_APPLIED last, approve 200, REVIEWED,
HOLD_RELEASED), `::test_active_pending_judgement_is_stale_after_a_later_event` (409, VOIDED STALE_SUBJECT, REJECTED),
`::test_resubmitted_judgement_reuses_its_open_hold` (reject → edit → resubmit: head unchanged, approve 200), the R3c
inactive case kept; `test_combination.py::test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append` — T1
(`unit_of_work` as SYSTEM) holds the member's group and contract through `holds.apply_system_hold` (HOLD_APPLIED, H+1,
uncommitted); T2 (approve, a thread) passes `decide`'s pre-lock check and is witnessed blocked by T1's backend on a
`combination_group` row (`await_lock_wait`); T1 commits; T2 is refused 409 `stale-approval`, the request VOIDED
STALE_SUBJECT, `first`'s head = H+1, both members still singletons, the group REJECTED — before this slice T2 applied the
JOIN against H+1. Gates: ruff; `make typecheck` (605 files); `make lint` before each commit; the CPU set without the
DB-fixture modules re-captured on the head.

### P5-LOCK-R3d-b — every `on_approved` hook re-validates the basis under its locks (team-lead ruling on the R3d scope note)

Ruling: 101d (2) reads "any on_approved path" — the under-lock check is not optional per hook. Added to the four hooks
left out of R3d, each after its own protecting locks and before its first write, with `assert_fresh_basis` unchanged:

| Hook | Subject content read | Finding | Check placed |
|---|---|---|---|
| `activation.activate` (CONTRACT_ACTIVATION) | `contract_activation_content`: contract_no, external_id, head_stream_version, document_ref, combination_group_id | Describes the subject only — the head and group pin it; no decision-derived field. The hook is also the BS3-D-19 factory path with `approval_request_id=None`, so the check runs when a request id is present. | after `lock_group_then_contract`, before the checklist and `append_events` |
| `estimates._approve_version` (ESTIMATE_VERSION) | `estimate_version_content`: an explicit field list of the version and its element (kind, method, amounts, scenarios, parameters, rationale, judgement record, supersedes …) | No status, `approval_request_id` or stamps — `submit_version` sets the request linkage after `approvals.submit`, and it is not in the content; no decision-derived field. | after the version row, the group, the contract and the earlier approved versions are locked, before the first `transitions.apply` |
| `subjects._apply_event_submission` (MANUAL_EVENT, MODIFICATION) | `event_submission_content`: the submission's contract id and stored events | Immutable after submission (the row's status is not in the content), so the content genuinely cannot change between `decide`'s pre-lock hash and the locks; the check is still called — cheap and uniform, as ruled. | after the submission, group and contract locks, before `append_events` |
| `overrides._apply_ssp_override` (SSP_OVERRIDE) | `proposal_content = ssp_override_content`: the proposal plus its base state (the obligation exists, its SSP pins, the proposed version's status) | Base state only; no decision-derived field. | after `lock_group_then_contract`, before the contract / entity read and `append_events` |

No content function needed a field removed (the D-98 101d note — decision-derived fields excluded from subject content —
is satisfied by all six as they stand). Docs: the unlanded dev-guide 1.40 row and the DG-KRN-APR-05 sentence extended in
place ("every `on_approved` hook", the six hooks named, the exclusion note); no new number.

**Tests (CPU, `tests/unit/test_activation_lock_order.py`, 33 in the module).** One test per hook
(`test_activation_…`, `test_estimate_approval_…`, `test_event_submission_…`, `test_ssp_override_revalidates_the_basis_
under_its_locks`): `assert_fresh_basis` replaced by a recorder that snapshots the locks taken and stops; the hook's
first write (`append_events` / `transitions.apply`) replaced by `pytest.fail("applied before the basis check")`; the
snapshot must be `RULED_ORDER` (unlocked contract read, group lock, contract lock). Stand-in extended for the hooks'
system units: a real `RequestContext` with the principal stub, a clock, kwargs construction, `first()` / `scalars()`, a
joined select answered as the contract ⋈ entity row, `obligation_version` (no pins), and the contract row now carries
an activatable `status` and `head_stream_version`. **Fail-first — all four behavioural:** on the pre-R3d-b source every
hook ran on to its write — `Failed: applied before the basis check` ×4 (`.run/p5/int1/fail-first-r3d-b.txt`; source
stashed 2026-09-20T13:32:25Z, restored 13:32:27Z); green `.run/p5/int1/pass-r3d-b.txt`: 56 passed at 13:32:29Z (unit
lock-order 33, problems 9, evidence identity 3, probe 2, both drift modules, the lock guard). DB (NOT RUN on l12): the
existing activation, estimate, manual-event and SSP-override approval cases exercise the four hooks with an unchanged
basis (they must keep passing — the check compares the just-stored hash); a concurrent-append case per hook is not
written here — the mechanism is the one `test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append` proves
for the combination hook, and `assert_fresh_basis` is one function. Gates: ruff; `make typecheck` (605 files, after the
hook edits); `make lint` before each commit; the CPU set without the DB-fixture modules re-captured on the head.

### P5-LOCK-R3D-CONTEXT-R1 — the stale-basis refusal lost the tenant context (Codex packet 1330)

**Finding (Codex, source-derived on 5ce7c458; `PRODUCTION-P5-R3D-CONTEXT-REGRESSION-5ce7c458.md`, SHA-256 de219b40…;
8-artifact manifest).** `engine._refuse_stale_basis` called `uow.discard()` — a transaction rollback — and then
`_lock_request` on the SAME session. The app engine's `rollback` listener drops `erev.context` (DG-KRN-DB-04) and
`_context_session` sets it only on entry, so the very next statement was refused `TenantContextMissing`: the persisted
VOID and the 409 were never reached (a 500 in production). Re-verified by reading `engine.py` and `db/session.py` on
8b438fd0. My R3d CPU cases did not exercise this error path (the void was stubbed); the participant-bound DB case would
have hit it and is still NOT RUN.

**Fix (Codex's constraints adopted: no guard bypass, the under-lock check kept).** `UnitOfWork.savepoint()` (new; DG-KRN-
UOW-03 rev 1.40): a nested transaction — on an exception the savepoint is rolled back and the audit events and hooks
buffered inside it are dropped, the session keeps its tenant context (only a transaction rollback clears it) and every
lock taken before it (the request lock from `decide`'s start), and the exception propagates; on success it is released.
`decide` runs the decision's writes and the hook (`_apply_decision`: the decision row, `_advance`, the audit event, the
hook, the notifications) inside `uow.savepoint()` and catches `StaleBasis` outside it; `_refuse_stale_basis` no longer
discards — it re-locks the request (a no-op re-lock, PENDING again), voids it `STALE_SUBJECT`, commits and raises 409
`stale-approval`. The admitted wait schedule (T1 append uncommitted → T2 approve blocked → T1 commits → T2) therefore
yields 409, a persisted VOIDED / STALE_SUBJECT request with its audit, and no applied membership or decision residue —
`test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append` (DB, NOT RUN on l12) is the case that would
have answered 500.

**Tests (CPU).** `test_refuse_stale_basis_keeps_the_tenant_context` — a fake session whose transaction rollback drops the
context and refuses the next statement (`TenantContextMissing`), `_void` and `current_content_sha256` stubbed: **red on
the pre-fix source exactly as Codex described (`TenantContextMissing: SQL on the app engine requires tenant_session`)**;
green: the request re-locked, `_void` called, `COMMIT`, 409 `stale-approval`, no `ROLLBACK`.
`test_savepoint_undoes_the_writes_and_keeps_the_context` — the real `UnitOfWork` on the fake session: `SAVEPOINT` /
`ROLLBACK TO SAVEPOINT`, the events and hooks buffered inside dropped, the earlier ones kept, the context intact, the
exception propagated; success releases (`AttributeError` on the pre-fix source — the method is new).

### P5-LOCK-R3D-ROUTING-R1 — the hold and the outcome read the published routing state twice (Codex packet 1337)

**Finding (Codex, source-derived on 5ce7c458; `source-observations/p5-judgement-routing-race-5ce7c458/source-note.md`,
SHA-256 15b9d6c3…; 13-artifact manifest 75ffd11f…).** `submit_judgement` evaluated the AUTO_APPROVAL state once for the
hold (`auto_approval_rule`) and `approvals.submit` evaluated it again for the outcome; `lifecycle.publish` admits a
concurrent supersession and routing reads current PUBLISHED status without locks, so under READ COMMITTED a custom
AUTO_APPROVAL v1 matching JUDGEMENT_RECORD, superseded between the two reads by a v2 matching only FX_RATE_SET_VERSION,
skipped the hold (v1) and routed the request PENDING (v2) — an unheld ACTIVE contract with a pending review (REQ-POL-010
broken). Re-verified on 8b438fd0.

**Fix (Codex's constraints adopted: one internal, trusted decision; no caller-controlled bypass; the hold stays before
the hash).** `engine.RoutingDecision` (internal dataclass: subject, amount, flags, the resolved `Routing`, the auto
rule) and `engine.route_submission(uow, subject_type, subject_id, *, auto_approval=True)` take the steps and the
AUTO_APPROVAL rule in ONE reading; `submit(..., routing_decision=None)` uses a given decision instead of reading again
(refusing another subject's decision with `ValueError`) and reads once itself when none is given. `submit_judgement`
calls `route_submission` under the record's locks, holds when `decision.auto_rule is None`, and hands the same decision
to `submit`. Never a request parameter — `submit`'s API surface is unchanged for routes. Controls kept: non-ACTIVE,
open same-reason hold, auto-approved (no hold). Docs: DG-KRN-APR-01 sentence and the 1.40 row (in place).

**Tests.** CPU: `test_submit_judgement_binds_the_hold_and_the_outcome_to_one_routing_decision` — `routing.auto_approval`
answers v1 then v2 (the other published reads stubbed), the fake `submit` uses the decision it is handed or, like the old
`submit`, reads again: **red on the pre-fix source by behaviour (`['PENDING']` — hold skipped, request pending)**; green:
one reading, no hold, `APPROVED` — consistent. `test_route_submission_reads_the_published_routing_once` (the decision
names its subject; one reading; `AttributeError` on the pre-fix source). The two R3d submit-order tests now stub
`route_submission` (they proved hold-before-hash and stay green). DB (NOT RUN on l12):
`test_judgements.py::test_hold_and_outcome_bind_to_one_routing_decision_across_a_publication` — `publish_rule_set`
publishes v1 (AUTO_APPROVAL, subject.type = JUDGEMENT_RECORD); a wrapper around `routing.auto_approval` supersedes v1 and
publishes an FX-only v2 in a committed second session right after the FIRST real reading; asserts `held == (status ==
PENDING)` and, now, APPROVED / REVIEWED / unheld / one reading (pre-fix: two readings, PENDING and unheld).

**Evidence for both.** `.run/p5/int1/fail-first-context-routing.txt`: 4 failed (context: `TenantContextMissing`; routing:
`['PENDING']`; the two new APIs absent), source stashed 2026-09-20T13:48:53Z, restored 13:48:55Z; `pass-context-routing.txt`:
60 passed at 13:48:57Z (unit lock-order 37, problems 9, evidence identity 3, probe 2, both drift modules, the lock
guard); `make typecheck` green (605 files); `make lint` before each commit; the CPU set without the DB-fixture modules
re-captured on the head.

### Codex retest at 3fff3baa — CONTEXT-R1 and ROUTING-R1 source objections resolved (packet production-20260920-1404 item 2)

Relayed by the team-lead: `PRODUCTION-P5-CONTEXT-ROUTING-SOURCE-3fff3baa.md` (SHA256 7cd721fa…, manifest ca5a5474…, 22
artifacts) resolves both source objections at 3fff3baa: the request lock precedes the nested transaction; the installed
SQLAlchemy `rollback_savepoint` dispatch differs from the outer `rollback` and the app has no Session rollback / soft-
rollback listener clearing the context; the new decision writes and buffers roll back inside the savepoint, then the VOID
commits in the outer transaction; one internal routing decision drives both the hold and `submit`, with no schema or API
parameter exposing it; all 173 prior assertions preserved. No further blocking source finding in the slice — the hold-lift
stands and 3fff3baa is the retest target through this record.

**Evidence distinctions kept, in substance.** (1) The actual app-engine concurrent-append / VOID / 409 / no-applied-residue
case (`test_combination.py::test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append`) and the approval cases
(the combination, judgement, activation, estimate, manual-event and SSP-override approval flows) remain **DB NOT RUN until
executed** — the source review resolves the objections, it does not execute them. (2) The new routing DB test
(`test_judgements.py::test_hold_and_outcome_bind_to_one_routing_decision_across_a_publication`) simulates the published-
state replacement through direct helper writes (`publish_rule_set` of a second rule set plus a direct status update to
SUPERSEDED on the first version), **not a full governed same-set publication** through `lifecycle.publish`. (3) This is
**not an all-routing-state atomic-snapshot or full-lifecycle proof**: the one reading binds the hold and the outcome of one
submission; it does not pin every routing-relevant fact against every concurrent publication schedule.

## Returned item P5-RET-1 — every legacy import COMMIT failed `StaleBasis` (integrated DB gate batch on main 0cb36c14)

**Measured (team-lead relay of `.run/supervisor/main-gates/run-0cb36c14-…-20260920T180217/`, read-only).** ci rc 2:
"134 failed, 4289 passed, 382 deselected, 2 xfailed, 42 errors"; parity-release 121 / 121 and parity-all 122 / 122
failed ("ScenarioBrokenError: golden step 02 did not commit"). ci.log: 58 `StaleBasis` mentions, `import.commit_failed
error_class=StaleBasis import_upload_id=…` for every `legacy_contract_setup` import; the import ends FAILED with
`IMPORT_PROCESSING_FAILED`; the fixtures assert COMMITTED (`tests/support/legacy_replay.py:383`). Failing suites include
`tests/domain/imports/legacy_v1/test_progress.py` (10), `test_modification.py` (6), `test_defects.py` (6),
`test_contract_setup.py` (6), reports / journals / api suites built on the legacy fixture, and every parity case. (The
`test_monitors` / `test_lock` / `test_reopen` / `test_export` failures and errors in the same run are F-CLO's area, not
this mechanism.)

**Root cause (from source, on main 0cb36c14 merged into the lane as cd17d293).** The raising hook is `activation.activate`
(activation.py:794, the R3d-b call). `legacy_v1/contract_setup._activate` — BR-DAT-06, "the import approval is the
activation approval" — calls `activation.activate(uow, contract_id=…, approval_request_id=context.approval_request_id,
on_behalf_of=uploader)` with the **IMPORT_COMMIT request id, for provenance** (it is stamped on `CONTRACT_ACTIVATED`).
`assert_fresh_basis` then re-hashed the IMPORT subject (`import_commit_content`: file / template / parameters / diff hash
and `contracts: [[external_id, head]]`, the stream head of every contract the rows name — [J] L5-1-Q-6) against the import
request's stored basis; the IMPORT_COMMIT job's OWN booking had just created / appended to exactly those contracts, so
the heads differ → `StaleBasis` → the job's `commit_failed`. A self-staleness composition: SELF-STALE-R1 handled the
judgement hold; the import → activation path passes a request the hook does not apply. No other hook receives the
import's request id (`_prepare_records` creates and REVIEWS its judgement records by direct transitions; the estimate
versions likewise; `void._approved` checks its own request). Reproduced on the CPU stand-in with an IMPORT_COMMIT request
and moved content: `StaleBasis` on the pre-fix source.

**Fix (101d kept: no retry, no skipped check for a hook's own request, no broader tolerance).** A hook re-validates the
basis of ITS OWN request — the request whose subject it applies. New `engine.assert_fresh_basis_for(uow,
approval_request_id, *, subject_type, subject_id) -> bool`: when the request names this hook's subject the check runs
(and refuses `StaleBasis`) and returns True; when it names another subject the id was carried for provenance — it is not
this hook's basis: nothing is hashed, False is returned. `activation.activate` uses it with `(CONTRACT_ACTIVATION,
contract_id)`. The import's basis was validated by `decide` before the IMPORT_COMMIT job was deferred; its application
is the job, which by design books the contracts the content pins — no `proposal_content` / `import_commit_content`
change, nothing for the imports owner. The other six hooks keep `assert_fresh_basis` (each receives its own request).

**Tests.** CPU (`tests/unit/test_activation_lock_order.py`, 41 in the module):
`test_activation_under_an_import_approval_does_not_revalidate_the_import_basis` — an IMPORT_COMMIT request on the
stand-in, `current_content_sha256` answering a moved hash: **red on the pre-fix source with exactly the production
error, `StaleBasis: stale-approval …`**; green: nothing hashed, the activation proceeds past the locks to its write.
`test_activation_under_its_own_approval_still_refuses_a_moved_basis` — the contract's CONTRACT_ACTIVATION request +
moved content → `StaleBasis` under the locks (passes on both sources: the no-weakening control).
`test_assert_fresh_basis_for_checks_only_the_hooks_own_request` (own → hashed, True; foreign → not hashed, False;
`AttributeError` on the pre-fix source). The R3d-b `test_activation_revalidates_the_basis_under_its_locks` now targets
`assert_fresh_basis_for` and asserts the subject it is asked for. `.run/p5/int1/fail-first-ret1.txt` (2 failed + 1
control, source stashed 2026-09-21T02:07:19Z, restored 02:07:21Z, under gate slot 2 pid 6326); green
`.run/p5/int1/pass-ret1.txt` (131 passed: unit lock-order 41, problems 9, architecture; under gate slot 1 pid 8268 after the batch's END at 19:07:24). DB (NOT RUN on l12 — the lane database is Ray-side; the next integrated batch measures):
the legacy_replay fixture suites named above, `tests/domain/reports/test_legacy_reports.py`, the api suites on the
fixture, parity-release and parity-all — an in-process CPU drive of the import commit + approval is not possible without
the database (the commit is a deferred job over real rows). Gates: ruff; `make typecheck` (641 files on the merged
tree); `make lint` before the commit; CPU gates under a pid-first slot-2 claim (slot 1 and the main lock held by the
batch).

**Docs.** The DG-KRN-APR-05 sentence stays true (a hook re-validates the basis of the decision it applies); a clarifying
clause — "a request id carried for provenance (BR-DAT-06) is not the hook's basis; `assert_fresh_basis_for`" — is
recommended and waits for a dev-guide number from the team-lead (1.40 has landed); code and record first, the clause when
the number arrives.

### P5-RET-1 refined — Codex production-20260921-0216 and ruling D-98 candidate 119: the consumed composition

**Ruling (team-lead; D-98 candidate 119 "a hook re-validates the basis of ITS OWN request (101d refinement)", quoting
Codex 0216, which confirmed the cause at frozen 0cb36c14: `PRODUCTION-PARITY-IMPORT-SELF-STALENESS-0cb36c14.md`, SHA
02c85d23…).** Codex's binding requirements: correct the SUBJECT-SPECIFIC consumption boundary under the authoritative
locks BEFORE importer effects; carry an explicit validated composition relationship into activation; preserve direct
CONTRACT_ACTIVATION freshness under the group / contract locks and the approval / event lineage; no global disabling,
no request-id erasure, no post-effect re-hash, no arbitrary request types. The first fix (687229c8, `assert_fresh_basis_for`
returning False for another subject type) is therefore **superseded** — "any other subject type skips" is not admitted.

**Design landed.**
- **Consumption, exactly once, under the authoritative locks, before any effect** — `imports/commit.py::commit_upload`,
  right after the `import_upload` row lock and before `_check_bases` / the first `store_source_record`: the contracts the
  VALID / WARNING rows name (`subjects.import_contract_keys`, factored out of `import_commit_content` so both pin the same
  keys) are locked on the ruled order by the new kernel helper `db/locking.lock_groups_then_contracts` (groups ascending,
  then contracts ascending, equality re-verified), then `engine.consume_fresh_basis(uow, request_id,
  subject_type=IMPORT_COMMIT, subject_id=import_id, keys=…)` re-hashes the import subject against the approved basis —
  a difference is `StaleBasis` with nothing written (the job's handler marks the import FAILED, IMPORT_PROCESSING_FAILED,
  as before; a dedicated finding code is the imports owner's call). The imports lane's own `_check_bases` (the diff-time
  heads, `StaleImport`) stays right after it, unchanged.
- **The composition** — `engine.ConsumedBasis` (frozen; internal, built only by `consume_fresh_basis`): the request, its
  subject, the covered business keys, the consuming transaction (`session`); `covers(uow, key=, approval_request_id=)`
  verifies same transaction, key among the keys, same request. It travels as `ApplyContext.consumed` (csv_v2 framework;
  None on a dry run) → `contract_setup._activate` → `activation.activate(..., consumed=)`.
- **Activation admits exactly two things** — its own CONTRACT_ACTIVATION request (`engine.assert_own_fresh_basis`: the
  request must name this contract's activation — `LookupError` otherwise — and its basis must hold under the group /
  contract locks — `StaleBasis` otherwise), OR a composition that covers it; a bare foreign request id is refused
  (`LookupError`), never re-hashed as the wrong subject (main) and never skipped (687229c8). The request id still stamps
  `CONTRACT_ACTIVATED` (lineage unchanged); the six other hooks keep `assert_fresh_basis`.

**Tests.** CPU (`tests/unit/test_activation_lock_order.py`, 45 in the module): `test_activation_under_a_consumed_import_
basis_proceeds_without_rehashing` (moved import content, the composition covers the contract → the write is reached,
nothing hashed); `test_activation_under_a_bare_foreign_request_is_refused_not_skipped` — **red on main 0cb36c14's
activation / engine with the production error (`StaleBasis`), red on the lane's 687229c8 by behaviour (proceeded to the
write instead of refusing)**; `test_activation_under_its_own_approval_still_refuses_a_moved_basis` (control, passes on
every baseline); `test_activation_refuses_a_composition_that_does_not_cover_it[another transaction | a contract outside
the keys | another request]`; `test_consume_fresh_basis_validates_once_and_yields_the_composition` (one hash; `LookupError`
for another subject; `StaleBasis` on a moved basis with nothing else done; the composition bound to the transaction);
`test_lock_groups_then_contracts_takes_every_group_before_every_contract` (groups ascending, contracts ascending, equality,
empty set locks nothing). The R3d-b activation test now records `assert_own_fresh_basis` and asserts the subject asked for.
Baselines: `.run/p5/int1/fail-first-ret1b-baseline-lane.txt` (source stashed → 687229c8), `fail-first-ret1b-baseline-main.txt`
(`activation.py` + `engine.py` checked out from main 0cb36c14); green `pass-ret1b.txt`. DB (NOT RUN on l12; the next
integrated batch measures): `test_contract_setup.py::test_setup_import_refuses_an_external_head_change_before_consumption_
atomically` (new: setup, then golden step 02 diffed → submitted → approved; a SYSTEM hold appended to Contract 1 between
the decision and the job; the job's consumption refuses — import FAILED, no event of the step on any named contract, the
approval still APPROVED), the fresh multi-contract composition `test_setup_import_approval_activates_contracts` (two ACTIVE
contracts, reviewed judgements, import lineage on CONTRACT_ACTIVATED, COLLECTIBILITY_ASSESSED before CONTRACT_ACTIVATED —
unchanged, must keep passing), `imports/test_commit.py::test_change_since_diff_voids_approval` (the decision-time stale
negative, unchanged), the legacy_replay fixture suites and parity-release / parity-all.

**Docs first: dev-guide 1.51** (assigned): DG-KRN-APR-05 gains "Own request only" — the hook's own request, the
provenance id, the deferred-job subject's single consumption under the authoritative locks before any effect, the
composition, activation's two admitted inputs, lineage kept, no global disabling, no post-effect re-hash; header entry
and log row.

**Codex production-20260921-0226 (relayed after the design above was written; folded in).** The committed-source baseline
"credits EXISTING controls rather than requiring duplicate whole-import hashing" — the job's `_check_bases` (diff-time
heads), the upload lock, immutable inputs and the downstream locked expected-head check — and names the remaining
interval: `_check_bases` compares with plain SELECTs and a later legacy `_book` re-reads a draft and passes THAT current
head to `replace_draft`, so an external edit after the initial check but before a later plan's re-read could be adopted
as the new expected head. Required: "retain approved bases / expected absence into protected consumption (or an
equivalent lock-bound design), with atomic rollback on a stale later plan". The design lands the lock-bound form: the
named contracts' groups and rows are locked at the consumption (before `_check_bases`) and HELD to the commit (one
transaction), so the initial check and every later plan's re-read run under the locks — an edit that landed before them
is refused before any effect (`consume_fresh_basis` / `_check_bases`), one that arrives after them waits for the commit
(its own `expected_stream_version` then decides) — and the approved bases travel in `ConsumedBasis.bases` (each key's
approved head from `diff.stored_bases`, None for an expected absence). The whole-import hash at consumption is kept: it is
the approved-basis form of the same facts, cheap, and binds the consumption to the approval; consolidating it with
`_check_bases` is the imports owner's call. A stale later plan rolls the whole job back (single unit of work; the handler
marks the import FAILED in a fresh one). DB (NOT RUN): `test_contract_setup.py::test_named_contracts_stay_locked_from_
the_consumption_to_the_commit` — the focused interleaving regression: an external append started between the initial
check and the second plan (a wrapper around `contract_setup.apply` starts it before plan 2) is witnessed BLOCKED by the
job's backend (participant-bound `await_lock_wait`), the job commits with both contracts activated, and the external
append then answers 412 (its `If-Match` head is behind) — never interleaved, no partial events. Codex 0226 also states no
evidence claims this race caused the parity failures and no public arbitrary-id exploit is alleged.

### P5-RET-1 residuals R1 / R2 — Codex production-20260921-0342 on 732cc1b7 (the p5r2 append HELD for them)

Codex: the generic foreign-subject skip is SOURCE-CLOSED and the named-contract lock protection SOURCE-ALIGNED at
732cc1b7; two bounded residuals return to this owner (fix forward, never amend).

- **R1 (high) — expected ABSENCE carried but not enforced at booking.** `commit.py` locked existing ids only;
  `ConsumedBasis.bases` had no production consumer; `contract_setup._book` looked the key up again and adopted a newly
  visible DRAFT's head / payload for `replace_draft`. Witness: key B approved absent; the initial check observes absent; an
  external transaction creates and commits a compatible DRAFT B before the import's plan; the plan adopts it. Fix: `_book`
  admits a plan only against the approved basis of its key (`contract_setup._admit_booking(consumed, name, existing)`):
  no basis entry → `StaleBasis` (the approval did not cover the key — distinct from approved None); approved None →
  the key must still be absent (a contract that appeared in between → `StaleBasis`); approved head H → the draft must
  exist with head H (the replace's expected head is the approved one, never a re-read the job did not approve). A refusal
  rolls the whole job back (one transaction). The tenant-unique `contract.external_id` (`ux_contract__external_id`) is
  the exclusion for an approved absence between the check and the insert. The dry run (no composition) enforces nothing.
  CPU: `tests/unit/test_import_consumption.py` (5: the witness refused; still-absent admitted; approved head admitted /
  moved refused / gone refused; missing entry refused; dry run enforces nothing). DB (NOT RUN): `test_contract_setup.py::
  test_setup_import_refuses_a_contract_that_appeared_for_an_approved_absent_key` — steps 01–02 committed, golden step 03
  (Contracts 3 and 4, approved absent) approved; at the job's second plan an external transaction books a compatible
  DRAFT "Contract 4" (Contract 1's booking payload under the new key); the job ends FAILED, Contract 3 absent (rolled
  back), Contract 4 carries only its external booking, the approval still APPROVED. Controls kept: the valid multi-contract
  composition (`test_setup_import_approval_activates_contracts`) commits whole.
- **R2 (medium) — the interleaving test could not witness the wait.** Its later plan targeted Contract 1, created by plan
  1 inside the uncommitted job, invisible to the external thread (`_contract` unpacked no row → error before the append).
  Restructured on an EXISTING committed contract: steps 01–02 committed (Contracts 1 and 2 ACTIVE), golden step 04
  (progress over both) approved; at the job's LATER plan an external BILLING append to that plan's contract — committed,
  visible, `If-Match` at its committed head — is started and witnessed BLOCKED by the job's backend (participant-bound
  `await_lock_wait`); the job commits whole (COMMITTED, the target's head advanced), the append then answers 412 and its
  event did not land; the writer thread is joined in `finally`. The expected-absence case stays separate (R1's test). The
  external-head-change case now also uses step 04 over the committed contracts (its earlier form re-imported step 02
  over ACTIVE contracts and would have failed for `CONTRACT_EXISTS`, the wrong reason).
- **Docs:** dev-guide 1.51 (unlanded) touched in place — the booking enforces the approved bases; a missing entry is
  refused; the tenant-unique external id is the exclusion.

### P5-RET-1 fixture corrections F1 / F2 — Codex production-20260921-0438 on ec3ddfd6 (p5r2 HELD again)

Codex 0438: **core 0342 R1 SOURCE-CLOSED** at ec3ddfd6 — the commit / context / apply / `_book` path consumes immutable
approved bases, distinguishes a missing entry from an approved absence, refuses an appeared row or a moved / missing
approved head before the insert / replacement, keeps the locked replacement / insert exclusion, and preserves own
intermediate writes and the foreign-request refusal; the R2 visibility defect is source-corrected (steps 01–02 committed,
step 04 over existing contracts). Two fixture defects returned, fixed forward here (never amend):

- **F1 — the approved-absence adversary could not reach its guard.** As authored, the external `booked_contract` ran
  synchronously at plan 2, after plan 1 had booked Contract 3 and while the outer import transaction still held the
  tenant / CONTRACT / empty-scope `numbering_series` row (`book_contract` → `numbering.next_number` → UPDATE); the
  external unit of work needs the same counter, so it would wait on the job while the job waits on it (a source-predicted
  wait to `lock_timeout`, not an observed run). Corrected: the external Contract 4 is created and committed AFTER the
  initial `_check_bases` / consumption and BEFORE plan 1's real apply (the numbering row is free); plan 1 then writes
  Contract 3 and plan 2 refuses the appeared Contract 4. The refusal is NAMED in the assertions — the wrapper records the
  exception type raised at each plan: `["Contract 4:StaleBasis"]` — beside FAILED, Contract 3 absent, Contract 4's sole
  external `CONTRACT_BOOKED`, the approval still APPROVED, the exact plan order.
- **F2 — the interleaving writer could escape `finally`.** `outcome["writer"]` was assigned only after `await_lock_wait`
  and the `is_alive` assertion, so an early failure bypassed the join. Corrected: the writer is registered the moment it
  has started; `finally` joins it after the import unwinds and asserts it terminated; the participant-bound wait, the 412
  and the no-external-BILLING-event assertions are kept.

**Wording corrections (Codex 0438).** R2 is not "closed": its visibility defect is source-corrected and its wait / timeout
defect fixture-corrected; every DB case here remains WRITTEN NOT RUN until the integrated batch executes it. The five
`test_import_consumption.py` unit witnesses are helper-level, not concurrency proof. The CPU set result (1616 passed, 10
errors — the ten `database "erev_rv_l12_test" does not exist` DB-fixture unit tests) is a reported RED (pytest rc 1), not
a CPU pass; the ten errors are the known lane-DB NOT RUN category and no other failure appears in it.

### Re-merge of main 82b112e6 and the p5r2 landing (returned item P5-RET-1 complete on main)

**Re-merge (45f91064).** The chain's v7 row-union resolver refuses every dev-guide conflict (its final marker check
matches the marker literals the dev-guide BODY legitimately contains — the 1.45 GOV-MARK-1 row and the DG-ARC-14 text),
so main 82b112e6 was merged into the lane by hand before READY-3: `docs/dev-guide.md` the only conflict file (pre-check
quoted, `.run/p5/merge-tree-precheck-82b112e6.txt`); header cell united strictly descending (1.51 P5, 1.48 F-SNP, 1.47,
1.46, 1.45, 1.43, 1.42, 1.41 …), both log rows kept (1.48, 1.51), both body texts present (F-SNP's DG-MIG-04 append-only
seed exception; P5's DG-KRN-APR-05 "Own request only"), zero line-anchored markers, 52 files staged clean; `uv sync
--project backend --frozen --all-extras` rc 0. Gates on 45f91064 (slot 1 pid 16252, 05:07:29Z–05:13:47Z;
`.run/p5/int1/merge-gates.log`): `make lint` rc 0 at the merge commit; `make typecheck` rc 0 (644 files); the green suites
rc 0 (141: import consumption 5, unit lock-order 45, problems 9, architecture); the full CPU set tests/unit +
tests/architecture rc 1 — **reported RED**: 1651 passed, 10 errors, all ten the `database "erev_rv_l12_test" does not
exist` DB-fixture unit tests, no other failure; the legacy DB module collects 10.

**Landing (chain step 54, controller v13 pid 67884).** Queue line 22:31:32 `p5r2|sprint/l12-p5|45f91064|…/msg-p5r2-45f91064.txt|`
(pre-check vs main d50299de rc 0, tree db865e18…, no allowed-conflict file). Terminal line verbatim: "22:41:22 p5r2 PASS:
merged p5r2 sprint/l12-p5@45f91064 onto d50299de: 6ee07d1f | POSTCHECKS: typecheck=rc0 cpu=rc0 selection=rc0
aggregate=PASS" — wrapper: typecheck rc 0; "engine+architecture+unit: 3194 passed, 1 xfailed in 400.91s"; cpu rc 0;
"selection keys: 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn; 220 not approved"; selection rc 0. Sealed
attempt (read-only): `.run/supervisor/lane-merge/attempts/p5r2-45f91064-20260920T223132-67884` (answer-keys-report.json
sha256 011fc84e…, captured_sha 6ee07d1f, tree db865e18… = the pre-check tree, validator dee51cfe… rc 0, at-start
tooling copies, rg-selection.at-start.txt 220 ids). **Main head 6ee07d1f.**

**Merged is not gate-measured.** The ~55 ci `StaleBasis` failures, the 117 + 4 parity outcomes and the three DB cases
(`test_progress_import_refuses_an_external_head_change_before_consumption_atomically`,
`test_named_contracts_stay_locked_from_the_consumption_to_the_commit`,
`test_setup_import_refuses_a_contract_that_appeared_for_an_approved_absent_key`) are measured by the next integrated
batch on the END head (after ENG-T1F's and F-RPS's lines land); until then they stay WRITTEN NOT RUN and nothing here is
called passed or repaired. Codex's committed targets: ec3ddfd6 / 916dfc96 / 45f91064.

## Integrated batch #4 on main c9110467 — the DB cases measured for the first time: eight failures returned to P5

**Measured (team-lead relay; run e2878d9d…, ci rc 2 "41 failed, 4511 passed, 382 deselected, 2 xfailed"; log
`.run/supervisor/main-gates/run-c9110467-…-20260920T232058/ci.log`, read-only).** Eight are P5's — the DB-bound cases the
p5r2 READY listed as NOT RUN, now executed. Main c9110467 merged into the lane first (clean; pre-check quoted in
`.run/p5/merge-tree-precheck-c9110467.txt`; `uv sync --frozen --all-extras` rc 0).

| Failure | Measured | Root cause | Disposition |
|---|---|---|---|
| `test_activation_lock_interleaving.py::test_record_events_waits_for_the_group_lock_and_never_deadlocks`; `test_combination.py::test_join_approval_is_stale_after_a_member_event`, `::test_leave_approval_is_stale_after_a_member_event`; `test_judgements.py::test_review_is_stale_after_a_contract_event`, `::test_active_pending_judgement_is_stale_after_a_later_event` (five oracles; the sixth, `_append_billing`, is the shared helper behind the two combination cases) | `assert 201 in (200, 202)` — `POST /contracts/{id}/events` answered 201 | **The tests' oracle was wrong, not the API.** 04 §16.3 API-S-EventAppend: "Response: 201 `{contract, events, computation}`; 202 API-S-Job when the computation exceeds 30 seconds; … 201 `{event_submission_id, approval_request_id}`"; `api/v1/events.py contract_events_append` declares `status_code=201` with `status_of=_append_status` (202 for the job). 200 was never a valid response of this endpoint. | **Engineering ruling (P5, recorded here): the expectation is corrected to the endpoint's documented contract `(201, 202)`, citing 04 §16.3 API-S-EventAppend — not loosened; the assertions' purpose (the append happened, the path that reaches `_mark_dirty` / moves the head was exercised) is unchanged.** No production change; no docs change. |
| `test_judgements.py::test_hold_and_outcome_bind_to_one_routing_decision_across_a_publication` | `submit` answered 403 `self-approval` (EREV-APR-001) | **The case's premise is inadmissible in this domain.** A custom AUTO_APPROVAL rule for JUDGEMENT_RECORD auto-approves at submission; `review_judgement` then records the preparer as the reviewer and DB-10 `tg_judgement_record__review` refuses `reviewer_id = created_by` (0042; 04 DB-10 "reviewer separation") → 403. Codex's premise ("an admitted custom rule") holds for the CPU case with stubbed routing, not for a real JUDGEMENT_RECORD auto-approval by a USER preparer. | Case re-oriented to the admissible direction: no auto rule at the first reading; a concurrent committed publication of an AUTO_APPROVAL rule matching JUDGEMENT_RECORD lands right after it. Pre-ROUTING-R1 code: hold applied on the first reading, the second reading matched the new rule → an auto-approval by the preparer → 403 (the submission failed although the hold decision had been taken). Now: one reading → PENDING, held, 200, `len(readings) == 1`. The hold-skipped / pending split stays covered by the CPU case. No production change. |
| `test_contract_setup.py::test_named_contracts_stay_locked_from_the_consumption_to_the_commit` | COMMITTED (as expected) but `plans == []`, no wait witnessed | **Test defect, not a production defect:** `commit_upload` resolves the emitter through `diff.emitter_of(code)` → the REGISTERED `CsvTemplate` object whose `apply` was captured at registration; my `monkeypatch.setattr(progress, "apply", …)` changed the module attribute only, so the wrapper never ran. | `_patched_template(monkeypatch, template, apply)` replaces the registered object for the test (`dataclasses.replace(TEMPLATE, apply=wrapper)` served through a patched `diff.emitter_of`). The case's assertions are unchanged. Still NOT RUN on the lane. |
| `test_contract_setup.py::test_setup_import_refuses_a_contract_that_appeared_for_an_approved_absent_key` | COMMITTED where FAILED was expected | Same test defect (`contract_setup.apply` patched on the module; the external Contract 4 was never created, so nothing appeared and the import committed correctly). The `_admit_booking` guard itself was not exercised by the batch. | Same `_patched_template` fix; assertions unchanged. Still NOT RUN on the lane. |

Not P5's: the other 33 failures of the run are routed by the team-lead. Nothing here changes production code or governed docs; the
two legacy fixture defects mean the batch has NOT yet measured `_admit_booking`'s refusal or the lock-bound wait — they
remain WRITTEN NOT RUN until the next integrated batch. The status-code ruling is recorded as P5's engineering ruling for the
team-lead's confirmation (the oracle corrected to the spec's contract; the alternative — changing the API to 200 / 202 —
would contradict 04 §16.3 and CTR-5).

### Codex production-20260921-0737 (relayed by the team-lead) — the two `test_contract_setup.py` adversaries: the wrong seam, confirmed; the fixture corrected to the prescribed registry replacement

Codex reviewed the two adversaries at c9110467 and reached the same root cause independently: "both reported
test_contract_setup.py adversaries never enter the consumed import path … Frozen CsvTemplate objects captured the original
apply callables when constructed (progress 585–594, contract_setup 1047–1056); legacy_v1.TEMPLATES retains them,
diff.emitter_of returns them, and commit_upload calls template.apply (339/424–425). Rebinding the module attribute cannot
replace that stored callable. … it is not evidence that an actually exercised approved-absence guard failed." Prescribed
correction — fixture seam only: replace ONLY that registry entry with `dataclasses.replace(original_template, apply=wrapper)`
in a copied mapping preserving every other entry; assert `diff.emitter_of(code).apply` resolves to the wrapper before the
job runs; the pattern of `tests/domain/imports/test_commit.py` 435–448; no production-dispatch change, no frozen-template
mutation. Everything else in both adversaries kept exactly (second-plan wrapper, participant-bound waiter, pre-job If-Match
head, thread registration before waiting, outer finally / join, exactly 2 plans / blocked proof / no writer error / advanced
head / HTTP 412 / no external BILLING event; the separately committed external Contract 4 BEFORE the first real apply, both
planned calls, FAILED + exact `Contract4: StaleBasis`, no Contract 3, only the external Contract 4 booking, the decision
still APPROVED; no generic-failure substitution; COMMITTED never accepted).

**Fold (this commit, on top of 0d26bd48).** 0d26bd48's `_patched_template` had replaced `diff.emitter_of` (a function
patch); it now follows the prescription verbatim: `MappingProxyType({**legacy_v1.TEMPLATES, code: dataclasses.replace(
template, apply=wrapper)})` set on `legacy_v1.TEMPLATES` (every other entry the original object — asserted), then
`diff.emitter_of(code).apply is wrapper` asserted before `run_import_job`. The two cases' assertions are byte-identical to
the batch's. Codex's source trace (named contracts locked before basis consumption; the import unit shares the outer session;
`_admit_booking` refuses covered-absence + existing contract or missing basis; activation validates composition; failure rolls
back before FAILED settlement) is source-supported, not measured — the native demonstration follows in the next integrated
batch; both cases stay NOT RUN on l12. The 201 / 403 oracle rulings above are outside this packet; the 201 ruling stands as
recorded. Also consistent with the ruling: dev-guide DG-CMD-09 ("the response still returns 201 with `computation.status`
… returns 202 (API-R-30)"). No governed-doc wording moves in this fold, so no revision number was requested.

**Gates measured on 0d26bd48 (slot-1, pid 90781, 2026-09-21 07:25:51Z–07:32:26Z; logs `.run/p5/int1/*batch4*`,
`make-lint-merge-c9110467.txt`).** Merge commit 628e6611 lint-gated on the merged tree ALONE (the corrections set aside and
restored; "OK lint"); corrections commit 0d26bd48 "OK lint"; `make typecheck` "Success: no issues found in 645 source files";
green suites (`test_import_consumption`, `test_activation_lock_order`, `test_problems`, `tests/architecture`) 141 passed
rc 0; the full CPU set 1662 passed, 10 errors rc 1 — the ten DB-fixture unit tests (`database "erev_rv_l12_test" does not
exist`), no other failure or error; the four DB modules collect (33 tests). Gates on THIS commit: ruff, `make typecheck`
("Success: no issues found in 645 source files", rc 0), `make lint` (the commit gate); the DB cases NOT RUN.

### Codex production-20260921-0829 §2 (relayed by the team-lead) — 0d26bd48's bounded fixture corrections SOURCE-CLOSED; qualifications carried

Codex: "P5 0d26bd48 — bounded fixture corrections SOURCE-CLOSED; original eight native failures remain unremeasured. The
delegating diff.emitter_of replacement returns dataclasses.replace(template, apply=wrapper) only for the target code; other
codes delegate to the original. It reaches the actual captured-template dispatch boundary. Both concurrency adversaries are
AST-identical after normalizing only that patch-call substitution, including every assertion, real writer/wait/cleanup,
two-plan order, named Contract4:StaleBasis/no Contract3, no unintended billing and approval state. HTTP 201/202 expectations
match events._append_status and 04 §16.3. The routing case retains pending/submitted/held/one-read conditions; a USER
self-review success would violate 0042 DB10. Its publication is a separately committed fixture transaction injected after
the first decision, not real parallel public authoring/approval/MFA lifecycle evidence. Production permissions, MFA and
approval controls are unchanged." (PRODUCTION-P5-CI-FIXTURES-SOURCE-0d26bd48.md, SHA 9ac882ab….)

Carried into this record, verbatim in substance: (1) the eight native failures remain UNREMEASURED — nothing here is a pass;
the next integrated batch measures them; (2) the routing case's concurrent publication is a fixture transaction injected
after the first decision, not parallel authoring / approval / MFA lifecycle evidence — the case proves the one-reading
property of `submit_judgement`, not the real-world lifecycle; (3) a USER self-review success would violate 0042 DB-10 — the
re-oriented case's PENDING outcome is the only admissible one; (4) production permissions, MFA and approval controls are
unchanged by any commit of this return. Note the seam: 0829 closes 0d26bd48's delegating `diff.emitter_of` replacement;
this commit already carries 0737's prescribed registry-copy form (the same dispatch boundary, the whole-registry
preservation asserted) — both reach `template.apply`; the 0737 form is retained as the one Codex prescribed.

## Landing: p5r3 PASS — 4a1b539c on main 32c480b2 (record only)

**Chain line (relayed by the team-lead, 2026-09-21 02:30:30 PDT):** "p5r3 PASS: merged p5r3 sprint/l12-p5@4a1b539c onto
a172b993: 32c480b2 | POSTCHECKS: typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS" — clean merge, merge-lane route,
committed 02:21:12; the line was appended 02:10:31 second behind F-LMG's 4ceabf2c (supervisor pre-checks vs 29100c12 and
33a7a02b both rc 0 clean). Captured post-checks: typecheck rc 0; the CPU set (engine + architecture + unit) 3,340 passed /
1 xfailed (400.22 s); selection 220 / 220 pending (139.64 s); retained report sha256 e5f5f8463a15d754…, run_id
bfdb02981cc647de8461e278f77a98da, build 32c480b2, tree 72947cc4. The eight batch-#4 corrections (the 201 / 202 oracles, the
DB-10 re-orientation, the registered-template seam) are on main 32c480b2.

**Merged ≠ gate-measured ≠ accepted.** Integrated batch #5 measures the eight DB-bound cases next (the `_admit_booking`
refusal and the lock-bound wait included); they remain WRITTEN NOT RUN on the lane and UNREMEASURED natively until that
batch reports. Codex's residual cross-group schedule review of 101c stays OPEN — not closed by this landing.

**Lane landing (this commit − 1 = dbdf4397):** `git merge --no-ff --no-commit 32c480b2` into sprint/l12-p5 — clean
(pre-check quoted in `.run/p5/merge-tree-precheck-32c480b2.txt`); `uv sync --frozen --all-extras` rc 0; the merge
commit gated on `make lint` AND the governed-document guards (`tests/architecture/test_governed_document_shape.py`,
`test_copy_catalogue_drift.py`, `test_data_model_drift.py`) in ONE condition — `make lint` "OK lint", guards 15 passed in 0.93s (slot-1, pid 41060, 09:32:02Z); the merged tree is main's tree 72947cc4 exactly (the lane head was already contained in 32c480b2). Post-commit on the lane:
`make typecheck` "Success: no issues found in 652 source files", rc 0; the full CPU set (tests/unit + tests/architecture) 1770 passed, 10 errors in 321.54 s, rc 1 (09:32:44Z–09:38:08Z) — reported RED as always for the
ten DB-fixture unit tests (`database "erev_rv_l12_test" does not exist`), no other failure or error (main's tree brought the CPU set from 1662 to 1770 tests). Codex production-20260921-0845 §2 (relayed
before the queue line): "P5 4a1b539c — stronger registered-dispatch fixture SOURCE-PRESERVED; no new source hold … All 25
other definitions including BOTH entire concurrency adversaries and their assertions are AST-identical … No production
change. Record attributes prior 0d26 CPU 1662 pass + 10 setup errors rc1 and keeps all 8 original native failures
UNREMEASURED and DB cases NOT RUN." (SHA 3641d01b….) Nothing to fold.
**Receipt — Codex production-20260921-0944 §3 (relayed by the team-lead), carried as a receipt:** the step 63 landing
(attempt p5r3-4a1b539c-20260921T022045-67884; main 32c480b2, tree 72947cc4…, parents a172b993 + 4a1b539c; terminal
02:30:30 rc 0, sealed PASS) is INDEPENDENTLY VERIFIED as an exact scoped native PASS — typecheck 652 files rc 0; CPU engine
+ architecture + unit 3,340 passed / 1 xfailed (400.22 s) rc 0; selection 220 passed, all pending approval; report
e5f5f846…, run bfdb0298…; all 32 checks, 220 key hashes and eight frozen input hashes agree. Codex's qualification, verbatim
in substance: this does NOT clear the eight prior P5 database-test failures or prove full CI, the full 254-key corpus,
batch-v5 execution or accounting approval — integrated batch #5 (on the post-COMMIT-65 head) measures the eight DB-bound
corrections. Nothing else is owed from P5 before batch #5's returns; any return is dispatched by name.

## P5-LOCK-R4 — the cross-group schedule of 101c (Codex's OPEN residual): design note, docs first

**Dispatch (team-lead, 2026-09-21, engineering):** the residual Codex left OPEN after the 101c review — "target-first
cross-group order": can any two units of work take two shared `combination_group` rows in opposite orders? Deliverables:
(a) a CPU proof in `tests/unit/test_activation_lock_order.py` that a unit of work touching two groups (join / leave across
groups; a target sitting below, between or above the members' groups) issues its `FOR UPDATE` set in ONE globally
ascending id order regardless of which group is the target — the EXACT order asserted; (b) a participant-bound
interleaving DB case with two units of work touching the same groups — no 40P01, both complete, the loser sees
REGROUPED where the membership moved (DB-bound, NOT RUN, named). Constraints: no kernel lock-order change unless the
proof demands it (docs first + tell the team-lead), no retry claim, no schema change; commit under lint + guards on slot 2.

**Source inventory — every path that locks a group row (grep `lock_group(` / `_lock_groups_then_contracts(` /
`lock_groups_then_contracts(` / `lock_group_then_contract(` over `erev_api`):**

| Path | Group rows it takes | Order source |
|---|---|---|
| kernel `locking.lock_group_then_contract` — `record_events`, `request_preview`, holds, memos, `replace_draft`, `submit_activation` / `activate`, estimate creation / approval, SSP override, event-submission hook, `judgements.submit_judgement` / `review_judgement` (record `between`) | ONE group: the contract's (unlocked read), then the contract | single row — trivially ascending |
| kernel `locking.lock_groups_then_contracts` — the import's consumption (`imports/commit.py`) | every observed group of the named contracts | `sorted(set(observed groups))` |
| `combination._lock_groups_then_contracts` via `_visible_contracts` — `create_group` (no target), `submit_group` JOIN / LEAVE (target = the submitted group) | `{target} ∪ {each member's observed group}` | `sorted({*group_ids, *expected.values()})` |
| `combination._lock_groups_then_contracts` via `_lock_members` — `apply_combination` JOIN (target + each member's group) / LEAVE (target + each member's singleton by code) | as above | as above |
| `combination.close_combination` (`on_rejected` / `on_voided`) | the target alone, then the proposal record | single row |

No path takes a group row outside those helpers (the implicit `UPDATE` locks — `_mark_dirty`, `_dirty`, `_move` — run
AFTER the helper's explicit locks on rows already held). Every sequence is therefore a sorted chain of the one global
order; two sorted chains agree on the relative order of every row they share, so no pair of units of work can take two
shared rows in opposite orders — the property (a) asserts by enumeration, not by "no deadlock".

**Where two units of work can share TWO group rows through real paths.** A JOIN requires singleton members
(`_member_errors` → ALREADY_COMBINED) and an APPLIED non-singleton group is never a JOIN target or source; so two units
of work share two or more group rows only as two proposals over the SAME singletons (T1 and T2 both over [X, Y]:
`{SX, SY, T1}` vs `{SX, SY, T2}`). A LEAVE (`{G, SX}`) and a JOIN over X after the leave share SX alone; an append on X
(`{SX}`) shares one row with anything. The DB case (b) is the two-proposals shape — the only real-path shape with two
shared rows.

**Id facts stated, not relied upon.** Ids are UUIDv7 (`db.new_id`), so a JOIN target (created by `create_group`) is
ordinarily newer — higher — than its members' singletons (`commands._insert_group` at booking): on the database, with
real paths, "the target lowest" is not ordinarily constructible, and under the pre-101c target-first order the two
proposals shape would still have taken the shared singletons in the same order (T first, then SX, SY). The kernel sorts
by id and never by role, so the CPU proof places the target LOWEST, BETWEEN and HIGHEST relative to the members' groups
and asserts the exact resulting order each time — that is where target-first would show, and it is CPU-provable only.

**(a) CPU design — `tests/unit/test_activation_lock_order.py` (P5-LOCK-R4 section).** A `_CrossGroupSession` stand-in
(subclass of the module's `_Session`) answers contract reads from a per-contract row map (each member with its OWN
group and contract number), the leave's singleton lookup by group code, and `is_singleton` per group; records
`locked_groups` (inherited) and `locked_contracts`. Members X (`UUID(int=21)`) in GX (`int=32`) and Y (`int=22`) in GY
(`int=34`); the target T parametrized `int=31` / `33` / `35` (lowest / between / highest). Cases, each asserting the EXACT
`locked_groups` list, `locked_contracts == [X, Y]`, and `between` positioned after every group lock and before the first
contract lock: `combination._lock_groups_then_contracts` (the helper); `_visible_contracts(target=T)` (submit's step);
`_lock_members` JOIN (apply's step); `_lock_members` LEAVE with the singletons both below / around / both above T;
`locking.lock_groups_then_contracts([X, Y])` across two groups (the import's step); the ENTRY paths `create_group`,
`submit_group` JOIN, `apply_combination` JOIN and LEAVE stopped right after their lock step (a `_Stop` at
`_member_errors` / `assert_fresh_basis`) — "the target is first iff it is the lowest id" asserted explicitly; and the
SCHEDULE proof: the lock sequences of every enumerated unit of work (including the single-group `record_events` on X and
two proposals over the same two singletons with targets on opposite sides, `[T1, SX, SY]` vs `[SX, SY, T2]`) are each
sorted and pairwise consistent on their shared rows (`_consistent(a, b)`: the shared rows appear in the same relative
order) — the cycle-freedom argument made executable over the enumerated paths.

**Fail-first for (a).** Attempt: the pre-101c `combination.py` (d2b1cdc3, the R3b module whose `submit_group` /
`apply_combination` took the target first through `repo.lock_group` before `_visible_contracts`, and 4fae8ff0 before it)
checked out over the working tree for the run only, the new entry-path cases run against it, the kind of red recorded
(an ORDER red — `locked_groups` target-first — or an import / signature red, which proves less); the current module
restored by `git checkout HEAD -- <file>` and the diff shown empty. Whatever the outcome it is stated verbatim below.

**(b) DB design — `tests/domain/contracts/test_combination.py` + `tests/support/interleave.py`.** Two active seat
contracts X, Y (singletons SX, SY); two PROPOSED groups T1 and T2 both over [X, Y], both submitted (two PENDING
requests). A holder session locks `min(SX, SY)` — the FIRST shared row on the ruled order — then both approvals start in
their own threads; the new support `await_lock_waits(holder, holder_pid=, backends=, count=2, timeout=)` (a counting
variant of `await_lock_wait`, participant-bound the same way) returns when TWO distinct request backends are blocked by
the holder's backend, each in a statement against `combination_group`; the holder releases; both requests complete
(joined, no error). Exactly one approval is 200 — its group APPLIED with members [X, Y], X and Y current in it — and the
other is 412 `precondition-failed` with `REGROUPED` (its `_lock_groups_then_contracts` revalidation found X's group ≠
the singleton it observed — before its own `assert_fresh_basis` under the locks), its request still PENDING and its group
still SUBMITTED (the command's transaction rolled back), no 409 `lock-conflict` / `stale-approval` in either response.
Which request wins is PostgreSQL's choice; the assertions are symmetric. DB-bound: WRITTEN NOT RUN on l12 (lane
database absent), named in the READY.

**Not in scope / not claimed:** no kernel change is expected (the proof is over the existing sort); no retry; no schema;
no governed-doc wording moves (DG-KRN-DB-08 already states the order) — no revision number requested. Codex's residual
is CLOSED only when Codex says so; this slice supplies the evidence.

## P5-LOCK-R4 — evidence (this commit): the CPU proof, the DB case, the fail-first probe, the gates

**Code (this commit; the design note is the section above).** `backend/tests/unit/test_activation_lock_order.py`
P5-LOCK-R4 section — `_CrossGroupSession` (members X `int=21` in GX `int=32`, Y `int=22` in GY `int=34`; the target
`int=31` / `33` / `35`; the leave singletons below / around / above `T_BETWEEN`); 34 cases: the lock step
(`_lock_groups_then_contracts`), the submit step (`_visible_contracts(target=)`), the apply steps (`_lock_members` JOIN
and LEAVE), the import consumption (`locking.lock_groups_then_contracts` over two groups), the ENTRY paths
`create_group` / `submit_group` JOIN / `apply_combination` JOIN + LEAVE stopped at the first statement after their lock
step (`_member_errors` / `assert_fresh_basis`) — every `locked_groups` list asserted EXACTLY as
`sorted({target, members' groups})`, "the target is first iff its id is the lowest" asserted explicitly, the proposal
record between the tiers, the contracts `[X, Y]` after every group lock (named Y, X in every proposal — the sort is the
code's); `test_every_unit_of_work_is_a_chain_of_the_one_global_order`: `[T_LOWEST, GX, GY]` vs `[GX, GY, T_HIGHEST]`
(two proposals over the same two singletons, targets on opposite sides), `[GX, T_BETWEEN, GY]` (a leave), `[GX, GY]`
(an import consumption), `[GX]` (an append) — each ascending, pairwise consistent on shared rows (`_consistent`).
`backend/tests/support/interleave.py`: `await_lock_waits(count=)`. `backend/tests/domain/contracts/test_combination.py`:
`test_two_approvals_over_the_same_singletons_take_the_groups_on_one_order` (DB-bound, NOT RUN on l12) as designed.

**Fail-first (the pre-101c ordering constructed cheaply: the R3b module checked out for the run only).** `git checkout d2b1cdc3 -- backend/erev_api/domain/contracts/combination.py`, the R4 section run: `no tests ran in 0.00s` (pytest rc as logged in `.run/p5/int1/r4/fail-first-r4-d2b1cdc3.txt`); 1 red cases — ERROR: file or directory not found: or; `locked_groups` ORDER assertions among them: 0. The module restored with `git checkout HEAD -- …` (diff vs HEAD empty), the section green again on the current module.

**Gates (slot 2; logs `.run/p5/int1/r4/`).** ruff clean on the three touched files; the R4 section on the current module: `no tests ran in 0.00s`; the whole unit module + tests/architecture: `152 passed in 17.82s`; the DB module collects; the commit gate = `make lint` AND the governed-document guards in ONE condition (this commit); `make typecheck` and the full CPU set on this head are measured after the commit and recorded in the follow-up record commit with their rc.

**Claims and non-claims.** The proof is by enumeration over the paths the source inventory names, on a stand-in
session — it shows the order the code ISSUES, not PostgreSQL's behaviour; the DB case (NOT RUN) is the participant-bound
demonstration of the only real-path two-shared-rows shape and is measured by the next integrated batch; no kernel
lock-order change was needed (the proof held on the existing sort — the team-lead was not asked for a number); no
retry claim; no schema change. Codex's residual is closed only by Codex.
**Receipt — Codex production-20260921-1113 §2 (relayed by the team-lead), carried as a receipt:** c190bd31 record /
source preservation VERIFIED, no discrepancy or hold — dbdf4397's tree equals reviewed main 32c480b2 across all 3,287
entries; the record adds 35 lines; the four reviewed test modules and ten production / control files exact; the p5r3
main PASS vs the lane's 1,770 / ten setup errors / rc 1 RED distinguished; the eight DB cases, the cross-group lock-order
follow-through (this slice, P5-LOCK-R4), the public-authoring / MFA limits and the 254 / accounting exclusions preserved;
no result transfers to the READY tip. Evidence: PRODUCTION-P5-READY-RECORD-c190bd31.md (4ee8246f…).

## Integrated batch #5 on main 020e5fd3 — two P5 DB cases measured RED and returned; the R4 probe's scripting defect disclosed and rerun

**Measured (team-lead relay; stage ci on main 020e5fd3, retained ci-report.json sha256 2c31eba4…, run 47a0dfbb…; 35
failed nodes / 4,668 passed; stage log `.run/supervisor/main-gates/run-020e5fd3-…-20260921T033759/ci.log`, read-only).**
Two of P5's eight DB-bound cases are in the failure set; the other six are not (they ran in the same stage — first native
measurement — and are not claimed beyond "not in the failure set").

| Failure | Measured | Root cause | Disposition |
|---|---|---|---|
| `test_combination.py::test_join_approval_is_stale_after_a_member_event` | the FIRST assertions passed — the approval was refused 409 `stale-approval`, the request VOIDED `STALE_SUBJECT` (the 101c subject content did its work); the LAST assertion failed: `after["subject"]["content_sha256"] == before[...]` (`42dab6e6…` both) | **Test oracle, not production.** The request KEEPS the hash the approver reviewed — `api/v1/approvals.py` shows the stored `subject_content_sha256` (REQ-PLT-014) and `engine._void` does not rewrite it; the CURRENT hash goes into the void audit (`approval_request.void`, `after.subject_content_sha256`). | Oracle corrected (team-lead ruling: accepted as a TEST ORACLE correction, no production change): the stored hash is unchanged (equality, documented); the member's head advanced by exactly one; the void audit's `after.subject_content_sha256` differs from the reviewed hash and its `void_reason` is `STALE_SUBJECT`. The leave case has no such assertion (not in the failure set). |
| `legacy_v1/test_contract_setup.py::test_named_contracts_stay_locked_from_the_consumption_to_the_commit` | `FAILED` where `COMMITTED` was expected; the job's problem: `import.commit_failed error_class=AssertionError` at 04:09:11 = the wrapper's `await_lock_wait(timeout=20.0)` raised — the external BILLING append was NEVER blocked: `POST /contracts/{id}/events` answered 201 in 310 ms at 04:08:51 while the job sat in its later plan | **PRODUCTION gap (the case's premise was right).** `commit_upload` derived its lock set from `subjects.import_contract_keys` alone, which returns `[]` unless the template's `import_template.target_object == "contract"` — `legacy_progress_tracking` is `contract_event` (0044 seed), `legacy_contract_modification` is `modification` — so a progress commit locked NOTHING before consuming its basis, although the approved basis (`diff.stored_bases`: the diff-pinned heads of Contracts 1 and 2) named those contracts. Codex 0226's interval (an external edit between the initial check and a later plan) was closed for setup imports only. `_check_bases` (StaleImport, diff-time vs commit-time heads) still refused a change BEFORE consumption — the sibling case `test_progress_import_refuses_an_external_head_change_before_consumption_atomically` passed — but nothing held the rows from the check to the commit. | **Fix forward (production, `imports/commit.py`; team-lead ruling: a CONTROL DEFECT FIX, no new D-98 candidate; P5 the owner as the 101c kernel-order / imports call-site owner):** the rows locked before the consumption are every contract the approved basis names — `sorted({*keys, *bases})` resolved to contract ids, through the unchanged kernel order `locking.lock_groups_then_contracts` (groups ascending, then contracts ascending); `keys` still travel into `consume_fresh_basis` as the template's keys. No kernel order change, no schema, no governed-doc wording move: DG-KRN-APR-05 rev 1.51 already says the basis is consumed "under the authoritative locks" — the code now locks what the basis names. CPU fail-first case `test_import_consumption.py::test_the_lock_set_is_every_contract_the_approved_basis_names` (below). The DB case is unchanged and stays NOT RUN. |

**Open item → dispatched by the team-lead as P5's NEXT slice, P5-SUBJ-1 (after this commit, the re-merge and READY; docs first under a new 04 number on request):** `import_commit_content` pins heads through the same
`import_contract_keys`, so a progress / modification import's APPROVAL binds its contracts' heads only indirectly — through
`diff_file_sha256` (the diff document carries the diff-time heads) and `_check_bases` at the commit (FAILED, not a
STALE_SUBJECT void). Widening the subject content to the basis's contracts' heads (so a member event after review voids STALE_SUBJECT,
consistent with 101c, with the existing `_check_bases` refusal retained) moves 04 §16.10 wording — the slice's docs-first step.

**R4 probe scripting defect (disclosed; the record section above was written by the script and is WRONG in its
fail-first sentence).** In `r4-all.sh` the `-k` expression was word-split (`${=R4}`), so pytest received `-k two_groups`
plus the literal `or` as a path: the "section only" runs and the pre-101c probe both ran NOTHING (`no tests ran in 0.00s`,
rc 4, "file or directory not found: or"). The evidence section's fail-first sentence therefore reports a no-op, not a probe.
The 34 R4 cases WERE executed and green in that same run's whole-module step (`152 passed` = the unit module + tests/architecture)
and the lint + guards gate held. This commit reruns the probe with the expression passed as ONE argument: `23 failed, 11 passed, 34 deselected in 0.74s` on d2b1cdc3's `combination.py`; red cases: test_apply_combination_join_entry_path_never_takes_the_target_first, test_apply_combination_leave_entry_path_sorts_the_singletons_with_the_target, test_apply_join_step_sorts_the_target_among_members_from_two_groups, test_apply_leave_step_sorts_the_target_among_the_singletons, test_create_group_entry_path_locks_the_members_groups_ascending, test_every_unit_of_work_is_a_chain_of_the_one_global_order, test_lock_step_sorts_the_target_among_members_from_two_groups, test_submit_group_entry_path_never_takes_the_target_first, test_submit_step_sorts_the_target_among_members_from_two_groups; first assertion line: `E       TypeError: _lock_groups_then_contracts() got an unexpected keyword argument 'expected'`; `locked_groups` / order lines in the output: 1. The module restored (`git checkout HEAD -- …`, diff empty); the section on the current module: `34 passed, 34 deselected in 0.44s`; the whole unit module + tests/architecture after the restore: `152 passed in 17.88s`.

**Codex production-20260921-1155 (relayed by the team-lead) — folded into this commit.** §2 on P5-LOCK-R4 7d73a91b:
"meaningful authored CPU coverage (real combination / kernel functions against DISTINCT groups with target lower / between /
higher; emitted statements inspected for the exact sorted sequence + between-record placement; 31 prior CPU functions
preserved)"; qualifications carried verbatim in substance — the final schedule assertion is five SEQUENTIAL stand-in prefixes,
not concurrent units of work or a native deadlock proof; "the only real-path two-shared-rows shape" is not exhaustive (scope
kept; no new runtime deadlock invented). **Count correction (NEXT-TOUCH):** the R4 section's ten added functions expand to
**24** authored parameter cases, not 34 — the "34 passed" of the scratch probe was the `-k` filter also matching ten
pre-existing cases; the evidence section above (7d73a91b) is corrected forward here, not rewritten. §3 on the two-approval DB
witness: R1 cleanup applied — the approval threads are tracked as started and joined in a `finally` that runs AFTER the
holder has released / unwound (the `with` blocks exit first), so a wait timeout, a query error or a failed assertion no
longer leaves an API transaction running into the fixture teardown; the original failure is preserved (no assertion inside
the `finally`); every wait / winner / loser / REGROUPED / membership assertion kept; ADDED the narrow loser-rollback
assertions — no `approval_decision` row for the loser's request, every step PENDING with no decisions, step 1 current (the
pre-hook decision write rolled back with the command; no production rollback bug alleged). Scope note carried:
`await_lock_waits` counts distinct captured app-engine pids directly blocked by the known holder — stronger than a sleep, not
a pid-to-approval mapping, a simultaneous-wait proof or an indirect-chain traversal. §4: the stale-approval oracle correction
is source-consistent; the assertions after the former hash assertion (rejected proposal, unmoved members) were not proved by
the failed run and are PRESERVED after the corrected oracle.

**Fail-first of the lock-set fix (this commit; commit.py stashed for the red run, popped after):** `1 failed, 5 deselected in 0.45s` on the returned `commit.py` — `E       AssertionError: assert [] == [['Contract 1', 'Contract 2']]`; on the fixed source `6 passed in 0.40s` (the whole consumption module).

**Gates (slot 2; logs `.run/p5/int1/r5/`):** ruff clean on the touched files; the commit gate = `make lint` AND the governed-document guards in ONE condition (this commit); `make typecheck` and the full CPU set on this head are measured after the commit and recorded in the follow-up record commit with their rc; the two DB modules collect; the DB cases stay NOT RUN.

### Codex production-20260921-1216 on 424ee07c (relayed by the team-lead) — the lock-set fix SOURCE-CLOSED; one new R1 folded here

§2: "the import lock-set omission is SOURCE-CLOSED for the reviewed approved-import path (sorted union of parsed keys +
stored diff-basis keys incl. progress / modification; visible existing ids to the unchanged helper — groups before contracts,
identity rechecked — before consume_fresh_basis and _check_bases; keys stay the parsed population; protections preserved; no
gap-lock / universal-schedule claim; the CPU witness calls the real commit_upload with empty parsed keys and reversed bases
and checks bound names + both ids)". Carried as stated: **native row locks / concurrency and the DB witness still need
candidate evidence** — the next integrated batch's; nothing here is a native pass. Credited: the `finally` cleanup and the
approval-hash oracle. Counters 95 → 100; 23 / 25 definitions AST-identical.

§1 R1 (this commit, test-side only): the loser-rollback oracle of 424ee07c required every approval STEP to be `PENDING`, but
`engine._insert_request` creates the REQUEST `PENDING` with the FIRST step `ACTIVE` and later steps `WAITING` (E-06;
`approval_queries` exposes the step statuses unchanged) — so an unchanged loser would have FAILED the new oracle
(source-predicted). Fixed as prescribed: each request's pre-approval step projection `[(step_no, status, decisions)]` is
captured before any approval and asserted to be the governed non-empty ACTIVE-then-WAITING sequence with empty decisions;
afterwards the loser's projection must EQUAL its captured one; zero `approval_decision` rows, `current_step_no = 1`, request
`PENDING`, group `SUBMITTED` / empty membership and every winner / loser / REGROUPED assertion kept; production status
semantics untouched. The cleanup comment now says a timed join is an ATTEMPT, not a guarantee (Codex 1216).

## Follow-up record: batch #5 returns commit measured; main 020e5fd3 re-merged before READY

**Gates measured on 424ee07c, the batch #5 returns commit (slot 2; logs `.run/p5/int1/r5/`); the test-only Codex 1216 R1 commit 1c9e75d5 on top of it was gated on lint + the governed-doc guards (its module is DB-bound, outside the CPU set):** `make typecheck` `OK typecheck`; the full CPU set
(tests/unit + tests/architecture) `1795 passed, 10 errors in 293.42s (0:04:53)`, rc 1 — reported RED as always for the ten DB-fixture unit tests (`database
"erev_rv_l12_test" does not exist`), no other failure or error. Fail-first and section results as recorded in the batch #5 section above.

**The R4 pre-101c probe, read (Codex-style classification of the 424ee07c run, `.run/p5/int1/r5/fail-first-r4-d2b1cdc3.txt`):**
on d2b1cdc3's `combination.py` the `-k` selection ran 34 cases (the 24 authored R4 cases + 10 pre-existing cases the filter
also matches): `23 failed, 11 passed`. The reds are the R3b module's own limits, not a target-first ORDER red: 7 ×
`precondition-failed` REGROUPED (R3b's `_visible_contracts(group_ids=())` refused every contract — the Codex 1150
regression — on the `submit_group` / `create_group` entry paths), 7 × `AttributeError: … has no attribute '_lock_members'`
(the apply lock step did not exist), 3 × `TypeError … 'target'` and 3 × `TypeError … 'expected'` (the R3c signatures),
3 × `KeyError: 'criterion'`. The old module never runs the new cases far enough to reach a `locked_groups` assertion, so a
CHEAP construction of the pre-101c ORDER red is not available — as the design note allowed ("state why not"). The order proof
therefore rests on the exact-order assertions against the CURRENT module (24 cases green; 152 with the whole unit module +
architecture), which is what the slice claimed; the `-k` word-split defect of 7d73a91b's run is corrected by this measured
run.

**Re-merge of main 020e5fd3 (the post-COMMIT-65 head named by the team-lead) = 7828a242:** `git merge --no-ff --no-commit
020e5fd3` — clean (pre-check quoted in `.run/p5/merge-tree-precheck-020e5fd3.txt`; main's 27-file delta since 32c480b2
touches none of P5's files); `uv sync --frozen --all-extras` rc 0; the commit gated on `make lint` AND the
governed-document guards in ONE condition — lint: OK lint; guards: 15 passed in 0.91s. Post-merge: `make typecheck` `Success: no issues found in 652 source files`; the full CPU set
`1802 passed, 10 errors in 290.72s (0:04:50)`, rc 1 (the ten DB-fixture errors alone).

**Standing qualifications carried:** the eight DB-bound cases — six not in batch #5's failure set, two returned and fixed
forward here — remain DB-bound and NOT RUN on l12; the two fixes (the staleness oracle; the consumption lock set) are
measured natively only by the next integrated batch; Codex's R4 residual is closed only by Codex; no accounting or
public-authoring / MFA lifecycle claim; the open item on `import_commit_content` stands for the team-lead / Codex.

## Re-merge of main 48e402e3 (COMMIT 66, the post-batch-5 head) before READY

**Merge = 645ad700:** `git merge --no-ff --no-commit 48e402e3` — clean (pre-check quoted in
`.run/p5/merge-tree-precheck-48e402e3.txt`, tree 72a7bf94; COMMIT 66 is docs-only on 020e5fd3, which 7828a242 had already
merged); `uv sync --frozen --all-extras` rc 0; the commit gated on `make lint` AND the governed-document guards in ONE
condition — lint: OK lint; guards: 15 passed in 0.82s. Post-merge on the lane: `make typecheck` `Success: no issues found in 652 source files`; the full CPU set `1802 passed, 10 errors in 310.92s (0:05:10)`, rc 1 — the ten DB-fixture
unit tests alone are the errors. Codex's independent review of the tip continues (receipt ≠ acceptance); the
qualifications of the sections above stand unchanged: the eight DB-bound cases NOT RUN on l12 (two fixed forward here,
measured only by the next integrated batch), no native pass claimed for anything on the lane.
**Receipt — Codex production-20260921-1258 §2 (relayed by the team-lead), carried as a receipt:** the step-state fixture R1
is SOURCE-CLOSED through 4f0b0c86 (424ee07c → 1c9e75d5 → merge 7828a242 → record 4f0b0c86): both requests' ordered
projections captured before either thread starts; non-empty ACTIVE then WAITING, no decisions; the loser preserves its
projection exactly; all prior controls unchanged; Counter 100 → 103; merges exact parent selections; CPU rc 1 / 10 setup
errors; DB cases NOT RUN; P5-SUBJ-1 and native concurrency OPEN.

## P5-SUBJ-1 — the import-commit approval subject content names the basis's contracts (docs first): design note

**Dispatch (team-lead, 2026-09-21, after the batch #5 rulings).** `import_commit_content` pins contract heads through
`subjects.import_contract_keys`, which returns keys only for a template whose `import_template.target_object` is
`contract` — so a progress / modification import's approval binds its contracts' heads only indirectly (the diff document's
hash, `diff_file_sha256`, carries the diff-time heads) and an event appended to a named contract after the review surfaces
as `FAILED` at the commit (`_check_bases`, StaleImport), not as a `STALE_SUBJECT` void at the decision. Widen the subject
content to the basis's contracts' heads so a member event after review voids the request `STALE_SUBJECT`, consistent with
101c; docs first — 04 §16.10 wording under a new 04 number (asked for when the wording is ready); then code + witnesses,
the existing `_check_bases` refusal retained.

**Source facts.**

| Item | Fact |
|---|---|
| Seeded templates (0044 `import_templates.json`) | `legacy_sku_ssp` → `ssp_book_version`; `legacy_contract_setup` → `contract`; `legacy_progress_tracking` → `contract_event`; `legacy_contract_modification` → `modification`. CSV_V2 templates: (0044 `CSV_TEMPLATES`, seeded with empty headers) `contracts` → `contract`; `invoices`, `progress_events`, `usage`, `cost_events`, `pre_standard_revenue` → `contract_event` (each keyed by its `contract` column: `key_column="contract"`); `modifications` → `modification`; `estimates` → `estimate_version` (also keyed by `contract`); the rest name no contract. |
| `import_contract_keys(session, import_id)` | `[]` unless `target_object == "contract"`; for LEGACY_V1 the business key's first segment ("<contract> / <POB> / <SKU>") is the contract external id; VALID / WARNING rows only. Used by `import_commit_content` (the approval content's `contracts: [[key, head]]`) and by `commit_upload` (the consumption's `keys`; the lock set since the batch #5 fix is `keys ∪ stored_bases`). |
| `diff.stored_bases(uow, row)` | the diff document's `contracts: [[key, head-or-None]]` for every plan key (`keys_in_order`) — progress and modification plans key on the contract name, so the diff pins their heads; needs `uow.files` + keyring (the encrypted diff file), so it is not readable from the subject-content seam (`session` only). |
| `_check_bases(uow, row)` | at the commit, each stored basis vs the current head; a difference → `StaleImport` → the import `FAILED`, nothing written. Retained. |
| `engine.assert_fresh_basis` / `decide` | the decision recomputes the subject content and compares with the stored hash; a difference voids `STALE_SUBJECT` (409 `stale-approval`), the void committed before the problem (REQ-PLT-014). |

**Design (one change at one seam).** `import_contract_keys` names the contracts of EVERY template whose rows key on a
contract: LEGACY_V1 templates with `target_object` in {`contract`, `contract_event`, `modification`} (the business key's
first segment), CSV_V2 templates with `target_object == "contract"` (as today) — for CSV_V2 the same rule by `target_object` — `contract`, `contract_event`, `modification` — with the business key AS the contract external id (their `key_column` is `contract`, `plan.key` the contract); `estimates` (target `estimate_version`, keyed by contract) is a question for the slice: its approval hook is the estimate version's own (F-CTR's `estimates._approve_version` revalidates), so it is EXCLUDED unless the team-lead rules otherwise. Nothing else moves:
`import_commit_content.contracts` then carries `[[external_id, head-or-None]]` for a progress / modification import too
(None for a contract that does not exist yet, as for a setup import), so an event appended to a named contract between the
request and the decision changes the hash → `STALE_SUBJECT` at the decision (the 101c pattern); `commit_upload`'s `keys`
grow accordingly (the lock set was already `keys ∪ stored_bases`; `ConsumedBasis.keys` / `covers()` gain the same keys —
`_admit_booking` is the setup template's and unchanged); `_check_bases` stays as the commit-time refusal for a change after
an approval that could not see it (an auto-approved API-client upload; a change between the diff and the submit is seen at
the submit's hash). No kernel change, no schema change; the content's SHAPE is unchanged (`contracts` existed; its
population widens), so the drift guards (`test_copy_catalogue_drift`, `test_data_model_drift`) are unaffected — verified
in the slice.

**04 §16.10 wording (docs first; number requested from the team-lead before editing):** append to the Subject content
paragraph: "For `IMPORT_COMMIT` (rev N — the number the team-lead assigns before the 04 edit; lane P5 slice P5-SUBJ-1) the content is the upload's `file_sha256`,
`template_code` / `template_version`, `parameters`, `diff_file_sha256` and `contracts[]` `[external_id, head_stream_version
or null]` for every contract the upload's VALID / WARNING rows name — a contract template's keys, and for the legacy v1
progress and modification templates the contract of each business key — so an event appended to a named contract between
the request and the decision voids the request `STALE_SUBJECT`; the commit's own check of the diff-time heads
(`_check_bases`) is retained for a change an approval could not see." Revision-log row + header cell under the assigned
number; no other governed doc moves (dev-guide DG-KRN-APR-05 1.51 already covers the consumption).

**Witnesses.** CPU (`tests/unit/test_import_consumption.py` or a new `tests/unit/test_import_subject_content.py` with a
stand-in session): `import_contract_keys` for a `contract_event` / `modification` LEGACY_V1 template returns the business
keys' contracts (fail-first: `[]` on the returned source); `import_commit_content.contracts` carries those heads; a moved
head changes the canonical hash. DB (NOT RUN, `tests/domain/imports/legacy_v1/test_contract_setup.py`): steps 01–02
committed, step 04 (progress) submitted and approved, then — before the IMPORT_COMMIT job — an external BILLING append on
Contract 1 → `approve` is 409 `stale-approval`, the request VOIDED `STALE_SUBJECT`, the import never commits (its request
void closes it per the existing `on_voided` hook — verified in the slice) — the void path; and the RETAINED refusal: an
auto-approvable path or a change after approval → `FAILED` via `_check_bases` (the sibling case
`test_progress_import_refuses_an_external_head_change_before_consumption_atomically` stays as is).

**Not claimed.** No native measurement on the lane (DB cases NOT RUN); Codex's review decides closure; no accounting claim.

## P5-SUBJ-1 docs first: 04 rev 1.65 — the `IMPORT_COMMIT` approval subject content names the basis's contracts

**p5r4 LANDED (team-lead relay):** READY head 8363ad9c merged onto 8b18b44c as main **1f704b82** at 07:39:17 PDT; post-checks
PASS 07:48:47 — typecheck rc 0; CPU engine + architecture + unit 3,408 passed / 1 xfailed (411.02 s); selection 220 / 220
passed, 0 failed, 220 not approved; answer-keys report SHA 9fb9d1bf3dae0289835b32ad782522bd918cafaa82f71fecaa200b37e6ade26d,
build_sha 1f704b82, run f8cff0b03fb041819ca6bb8359580389; attempt sealed `attempts/p5r4-8363ad9c-20260921T073847-63803`. The
six lane paths are on main; no governed-document change. Merged ≠ gate-measured ≠ accepted: the two-approvals DB witness, the
corrected stale-approval case, `test_named_contracts_stay_locked_from_the_consumption_to_the_commit` and the ten DB-fixture
cases stay NOT RUN until integrated batch #6 measures a head containing them. The lane then re-merged main (the head named in
the merge commit that precedes this one) under lint + the governed-document guards before this docs-first commit.

**Number and ruling (team-lead, 2026-09-21 06:40 PDT):** 04 revision **1.65** assigned (verified free across main and every
sprint branch — 1.62 l17, 1.63 l18, 1.64 l24-flmg; main at 1.61); supervisor engineering ruling **D-98 candidate 135**: the
widening as designed — one seam, `subjects.import_contract_keys`, names the contracts of every template whose rows key on a
contract (`target_object` ∈ {`contract`, `contract_event`, `modification`}, both families; LEGACY_V1 first business-key
segment; CSV_V2 business key = the contract) so the approval content and the commit's keys widen together; `_check_bases`
retained; no kernel or schema change; **`estimates` EXCLUDED, confirmed** — its approval binds the estimate version's own
revalidation and a contract-head binding there would double-bind one change to two approvals (stated in the 04 wording).

**Design-note correction (Codex production-20260921-1354 §1 on 7e61dc34, relayed by the team-lead; folded here, docs
first, before the code):** the design note's DECISION-time DB witness was written in an order that cannot exercise
freshness — "step 04 submitted AND APPROVED, then an external event before IMPORT_COMMIT, then approve → stale": an already
APPROVED request is refused `invalid-transition` by `decide`'s `_require_pending` BEFORE the subject comparison. The
witness sequence is corrected to: setup committed → the progress import SUBMITTED with its request still PENDING and the
reviewed hash retained → an external BILLING event APPENDED and COMMITTED to a named contract (head + 1) → the FIRST
authorized approval attempt with that reviewed basis → 409 `stale-approval`, the persisted VOIDED / `STALE_SUBJECT`, the
actual on-void import state (REJECTED by `_closed`) and no import effect on either contract. The distinct already-approved →
head change → consumption FAILED case (`test_progress_import_refuses_an_external_head_change_before_consumption_atomically`,
whose decision stays APPROVED) is kept unchanged; the pending-state guard is not weakened and neither outcome changes. This
corrects a written witness sequence, not a runtime bug; the widened key population and the code / family witnesses are
still owed (the next commit); `estimates` scope per the 06:40 ruling.

**This commit (docs only):** `docs/04-DATA_MODEL.md` — header cell (1.65 first, strictly descending), revision-log row
1.65, the §16.10 paragraph "Subject content of `IMPORT_COMMIT` (rev 1.65; lane P5 slice P5-SUBJ-1)" with the `estimates`
boundary. The header cell leads with 1.65 above main's 1.64 / 1.62 / 1.61 (strictly descending); the revision-log row is appended at the table tail — main's log carries 1.64 (F-LMG) before 1.62 (F-RPS), so the tail is the landing order, not the numeric one. The first run of this step failed on a stale header anchor (main's header had moved to 1.64 with the 1f704b82 merge) before any write — no commit, tree clean; the edit script was re-anchored to the header regex and the table tail and dry-run in place against the guards before this commit. Governed-document guards (shape, copy-catalogue drift, data-model drift) run in the commit's gate with `make lint`.
Code and witnesses follow in the next commit (docs first). This commit sits AFTER the p5r4 pinned head (the 1b9080e0 merge)
as the team-lead directed.

## P5-SUBJ-1 code (this commit): the widened key seam, its witnesses, the gates

**Code.** `backend/erev_api/approvals/subjects.py`: `CONTRACT_KEYED_TARGETS = {contract, contract_event, modification}`;
`import_contract_keys` names the contracts of every template whose `target_object` is in that set (LEGACY_V1: the first
business-key segment; CSV_V2: the business key, the row's contract); `estimates` and the non-contract templates name none
(the D-98 135 boundary). Through that one seam `import_commit_content.contracts` now pins a progress / modification
import's contract heads (the approval's `STALE_SUBJECT` trigger) and `commit_upload`'s `keys` widen with it (the lock set
was already `keys ∪ stored_bases`; `ConsumedBasis.keys` gains the same keys). `_check_bases` untouched. No kernel or schema
change; the content's shape is unchanged (drift guards unaffected — measured in the gate).

**Witnesses.** CPU (`tests/unit/test_import_consumption.py`): `test_contract_keys_name_the_contracts_of_every_contract_keyed_template`
— 7 parameter cases (legacy setup / progress / modification; CSV_V2 contract-event / modification; `estimates` excluded;
`legacy_sku_ssp` none); `test_a_progress_import_approval_pins_its_contracts_heads` — the content carries `[external_id,
head]` per contract and the canonical hash moves when a head moves (a shape witness: green before and after, not fail-first).
DB (`tests/domain/imports/legacy_v1/test_contract_setup.py`, NOT RUN): `test_progress_import_approval_is_stale_after_an_external_member_event`
— step 04 SUBMITTED (request PENDING, reviewed hash retained); external BILLING append on Contract 1 COMMITTED (head + 1); the FIRST approval attempt → 409 `stale-approval`, VOIDED `STALE_SUBJECT`,
the reviewed hash retained on the request, the import REJECTED by `_closed`, no step event on either contract; the
`_check_bases` FAILED sibling retained.

**Fail-first (subjects.py stashed for the red run, popped after):** `4 failed, 3 passed, 7 deselected in 0.49s` on the previous `subjects.py` — red cases csv-contract-event, csv-modification, legacy-modification, legacy-progress; first assertion line `E       AssertionError: assert [] == ['Contract 1', 'Contract 2']`; on the widened seam the consumption module `14 passed in 0.46s`.

**Gates (slot 2; logs `.run/p5/int1/subj1/`):** ruff clean on the three touched files; the DB module collects; the commit gate = `make lint` AND the governed-document guards in ONE condition (this commit); `make typecheck` and the full CPU set on this head are measured after
the commit and recorded in the follow-up. The DB case is NOT RUN on l12; native measurement is the next integrated batch's;
Codex's review decides closure; no accounting claim.

## P5-SUBJ-KEY-1 (Codex production-20260921-1521 §1, BLOCKING for SUBJ-1) — the contract key is read from the authoritative normalized row, never parsed from the display key

**Finding (Codex 1521 §1 on db77bd3f, tree ba50b378; report PRODUCTION-P5-SUBJECT-KEY-db77bd3f.md, SHA f24691d3…):**
`import_contract_keys` derived the LEGACY_V1 contract as `str(key).split(" / ", 1)[0]` of the display `business_key`, but
" / " is admissible inside a contract identifier (Key = length 1–255; LM-CL-01 exact text). Admitted case: contract
`ACME / West`, obligation P1, product SKU1 → `validate.py` builds the display key `ACME / West / P1 / SKU1` while the
normalized contract field, `Plan.key` and `diff.stored_bases` keep `ACME / West`; the helper returned `ACME`, so the
approval content pinned `[["ACME", null]]` or an unrelated `ACME` contract's head — (a) a real `ACME / West` head move while
PENDING was missed at decision time; (b) an unrelated `ACME` move falsely voided the request. Boundary kept precise by Codex:
`commit_upload` still locked `keys ∪ REAL stored_bases`, consumed the hash and `_check_bases` checked the real full-name head —
no unauthorized append, no lost lock; the decision-time identity was wrong nonetheless.

**Ruling (supervisor engineering ruling, D-98 candidate 135 AMENDMENT 1, relayed by the team-lead):** obtain the contract key
from the AUTHORITATIVE normalized row data (the validated row's contract field / `Plan.key` / the stored bases the importer keys
on) or an equivalent REGISTERED emitter key contract — never by parsing the unescaped display key; preserve the exact admitted
identifier, template eligibility, VALID / WARNING filtering, sorting / dedup, CSV_V2 semantics, the `estimates` exclusion, the
display format, the lock order and the stored-basis defence; FORBIDDEN: banning previously admitted separators, parsing the
display key differently, weakening stale checks. Witnesses through the REAL registered legacy importer with persisted rows.

**Fix (this commit; `backend/erev_api/approvals/subjects.py`):** `import_contract_keys` selects `import_row.normalized` of the
VALID / WARNING rows and reads the contract from it — LEGACY_V1: `legacy_templates.CONTRACT` ("Contract Unique Name", the
first T-IMP-03 key column); CSV_V2: the REGISTERED emitter's `key_column` (`csv_v2.TEMPLATES[code]`, a lazy import per the
module's convention; a seeded template without an emitter names nothing yet) — exact text, sorted, deduplicated; the display
`business_key` is no longer read at this seam; nothing else moves (eligibility set, filtering, `estimates` exclusion, the lock
set `keys ∪ stored_bases`, `_check_bases`). Docstring / comment next-touch items from Codex 1521 §2 applied:
`import_commit_content`'s "a contract template only" wording, `commit.py`'s "empty progress keys" comment.

**Witnesses.** CPU (`tests/unit/test_import_consumption.py`, a COMPOSITION-SHAPE witness on a stand-in, marked
source-derived): the key cases now feed NORMALIZED rows (the stand-in answers the previous seam's `business_key` read with the
rebuilt display keys, so the fail-first red is the truncation itself); new cases `legacy-progress-slash-in-name`
(`ACME / West`, `ACME` → `["ACME", "ACME / West"]`) and `csv-contract-event-slash-in-name` (`X / Y`, `X`); the CSV
`modifications` parameter marked PROSPECTIVE (no csv_v2 emitter yet → names nothing until one is registered). DB, through the
REAL legacy importer (`tests/domain/imports/legacy_v1/test_contract_setup.py`, NOT RUN on l12): steps 01–02 committed with the
golden contracts renamed `Contract 1 → ACME / West`, `Contract 2 → ACME` (setup rows through `workbook_bytes`, the real
validate / diff / submit / approve / commit); (1) `test_progress_approval_of_a_slash_named_contract_is_stale_after_its_own_event` —
a progress upload over `ACME / West` only, SUBMITTED / PENDING; the ACTUAL subject content inspected (`import_commit_content`
on a lane session) = `[["ACME / West", head]]`; external BILLING on `ACME / West` (head + 1); FIRST approval 409
`stale-approval`, VOIDED `STALE_SUBJECT`, import REJECTED, external-only effects; (2) `test_progress_approval_ignores_an_unrelated_prefix_named_contract` —
the same upload; external BILLING on the UNRELATED `ACME`; the subject unchanged, approval 200, IMPORT_COMMIT COMMITTED onto
`ACME / West`, `ACME` carries only its external event. The already-approved → real-head change → consumption FAILED sibling
retained. Legacy modification through its real emitter: NOT covered here (the 01–04 replay has no modification step; the
seam is shared, the normalized column identical) — stated, next-touch if asked.

**Attribution corrections (Codex 1521 §2, next-touch, applied to this record):** the already-approved sibling
(`test_progress_import_refuses_an_external_head_change_before_consumption_atomically`) now meets `consume_fresh_basis`'s
subject-hash check (engine.py) BEFORE `_check_bases`, so it no longer independently exercises `_check_bases` — the
`_check_bases` fallback is kept and stated as such; the CPU key test is a composition-shape witness; the CSV modification
parameter is prospective; docstring claims are source-derived; the ordinary-name witness credit stands (unit 3 → 8, DB 84 → 94,
none removed).

**Fail-first (subjects.py stashed to db77bd3f's for the red run, popped after):** `2 failed, 7 passed, 7 deselected in 0.61s` on the previous `subjects.py` — red cases csv-modifications-prospective, legacy-progress-slash-in-name; first assertion line `E       AssertionError: assert ['ACME'] == ['ACME', 'ACME / West']`; on the widened seam the consumption module `16 passed in 0.43s`.

**Gates (slot 2; logs `.run/p5/int1/key1/`):** ruff clean on the three touched files; the DB module collects; the commit gate = `make lint` AND the governed-document guards in ONE condition (this commit); `make typecheck` and the full CPU set on this head are measured after
the commit and recorded in the follow-up; the DB cases NOT RUN. This correction rides the SAME SUBJ-1 line (04 1.65 in place;
ONE READY).

## Integrated batch #6 on main 9e7d1031 — two batch-#5 nodes natively CLOSED; two R4 DB witnesses returned on first measurement

**Measured (team-lead relay; stage ci on 9e7d1031, report 6e1c2d8d…, run f9512985…; inventory
PRODUCTION-BATCH-9e7d1031-CI-FAILURE-INVENTORY-091129.md, SHA 86dfe34f…).** Natively CONFIRMED closed on main:
`test_combination.py::test_join_approval_is_stale_after_a_member_event` (the 424ee07c oracle) and
`legacy_v1/test_contract_setup.py::test_named_contracts_stay_locked_from_the_consumption_to_the_commit` (the 424ee07c
`commit.py` lock-set fix). Two NEW returns — the p5r4 R4 DB witnesses on their first native run.

| Return | Measured (stage log, read-only) | Root cause | Disposition |
|---|---|---|---|
| `test_combination.py::test_two_approvals_over_the_same_singletons_take_the_groups_on_one_order` | `only [10988] of the request backends [10988, 11851] were blocked by the holder 10978 within 20.0s (wanted 2)` (`support/interleave.py:95`); then BOTH approvals answered 500 after ~10.1 s with `psycopg.errors.LockNotAvailable` (SQLSTATE 55P03, `http.unhandled_error`) | **ESTABLISHED — the wait's predicate, not the lock order.** PostgreSQL queues row lockers on a TUPLE lock: the first waiter (A) waits on the holder's transaction and HOLDS the tuple lock; the second waiter (B) waits on that tuple lock, so `pg_blocking_pids(B)` names A, not the holder — "blocked by the holder" can never be true for B (hard block on the tuple lock; the docs' soft-block rule applies to the same lock object only). Both requests then hit the app's `lock_timeout` (10 s, `db/session.py`) → 55P03, which `problems.from_db_error` does not map → 500. The ruled order held: both requests queued on the FIRST shared row. | `await_lock_waits` accepts the chain — a request backend blocked by the holder directly OR by a request backend already so blocked (`_transitive_blockers`, a pure closure pinned by `tests/unit/test_interleave_support.py`); the "wanted 2" count and the timeout unchanged; the diagnostic on timeout dumps `pg_locks` × `pg_stat_activity` for the participants. The witness's assertions unchanged. **Production observation (not changed here; for the team-lead):** a lock wait beyond `lock_timeout` surfaces as an unhandled 500 (55P03 unmapped), unlike 40P01 → 409 `lock-conflict`; a named mapping would be a DG-KRN-ERR-02 / 04 §15.2 addition — a slice if wanted. |
| `test_combination.py::test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append` (line 767) | the backend blocked by T1 was executing the approval detail's ATTACHMENTS read (`approval_queries`: `SELECT … FROM file_attachment JOIN file_object … WHERE subject_type = $1 AND subject_id IN ($2) AND voided_at IS NULL ORDER BY …`), not the group-row lock; `assert "combination_group" in blocked_in.lower()` failed. The case PASSED in the earlier batches. | **NOT ESTABLISHED from source.** A plain SELECT waits on a heavyweight lock only for a relation-level conflict or a `FOR …` clause, neither visible in this statement; T1 (`apply_system_hold`) holds the member's group / contract rows and an appended event. Whether the blocked statement is a pooled backend's stale `query` text, a relation lock taken elsewhere in T2's transaction, or a change main brought between 020e5fd3 and 9e7d1031 in the approve path, only a native run with the lock named can say. | `await_lock_wait(expect="combination_group")`: the wait now returns only a backend blocked by the holder in a statement mentioning the expected table and, when none comes within the timeout, raises with every blocked statement seen and the `pg_locks` dump (locktype / relation / mode / granted / wait event / statement) of the holder and the request backends — the evidence the next batch needs. No production change; the assertions unchanged; cause OPEN — stated in the READY. |

Both fixes are test-support only and ride this SUBJ-1 line (small, with the root cause established for the first and the
diagnostic for the second). The eight p5r4 DB cases other than these two: six are not in the failure set and two are CLOSED
natively as above; nothing here is a native pass of anything on the lane.

**Fail-first / gates (this commit):** the closure pin on HEAD's `interleave.py` (stashed): `1 error in 0.08s`; on the new support `4 passed in 0.03s`; ruff clean; the DB module collects; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the CPU set on the line's head follow in the follow-up record.

## DG-ARC-01 fix-forward on the SUBJ-1 line — the CPU set on 75a3307b was RED beyond the ten DB-fixture cases

**Disclosed.** The full CPU set measured after 75a3307b answered `1 failed, 1839 passed, 10 errors` (rc 1): besides the
ten DB-fixture unit tests, `tests/architecture/test_layers.py::test_dg_arc_01_detects_upward_import` failed — two
findings, both in b84cb7a2's `approvals/subjects.py`: "kernel module imports domain module erev_api.domain.imports" at the
module-level `from erev_api.domain.imports import legacy_templates` and at the function-level
`from erev_api.domain.imports import csv_v2`. The KEY-1 commit's own gate ran ruff, the consumption module, lint and the
governed-document guards but NOT `tests/architecture` — the layer guard is a CPU architecture test the line's per-commit
gate omitted (the earlier R4 scripts ran the whole unit module + architecture before their commit; the SUBJ-1 / KEY-1
derivative did not). Corrected below; 75a3307b is not a READY head.

**Fix (this commit; team-lead: ACCEPTED — this registry IS the "equivalent REGISTERED emitter key contract" that D-98 candidate 135 AMENDMENT 1 named as the alternative to reading the normalized row directly).** The kernel keeps no domain knowledge: `approvals/subjects.py` gains a registry —
`register_import_contract_column(template_code, column)` / `import_contract_column(code)` — filled by the domain templates
when they load (the `register_lifecycle` pattern): `legacy_v1/__init__.py` registers `legacy_templates.CONTRACT`
("Contract Unique Name") for `legacy_contract_setup` / `legacy_progress_tracking` / `legacy_contract_modification`;
`csv_v2/__init__.py` registers each emitter's `key_column` for the templates whose `target_type` is `contract`,
`contract_event` or `modification` (`contracts` → `external_id`; `invoices`, `progress_events`, `usage`, `cost_events`,
`pre_standard_revenue` → `contract`; `estimates` not registered — the D-98 135 boundary). `import_contract_keys` reads the
registered column from the normalized row (KEY-1 semantics unchanged: exact text, sorted, deduplicated; an unregistered code
names nothing); both domain imports removed. The CPU witnesses import the two domain packages so the registry is populated as
in production; a new case pins the registrations. Gate rule (team-lead, for this and every later P5 commit): `tests/architecture` (incl. `test_layers`) green with the touched
unit modules BEFORE `make lint` + the governed-document guards, one condition (a red aborts and restores the tree; no commit);
then `make typecheck` + the full CPU set; the follow-up record; ONE READY.

**Fail-first / gates (this commit):** the layer guard on HEAD (fix stashed): `1 failed, 16 passed in 3.96s` — E       AssertionError: backend/erev_api/approvals/subjects.py:165 DG-ARC-01 kernel module imports domain module erev_ap; E         backend/erev_api/approvals/subjects.py:903 DG-ARC-01 kernel module imports domain module erev_api.domain.impor; on the fix, the consumption module + tests/architecture: `101 passed in 21.18s`; ruff clean; the DB modules collect; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the full CPU set on this head follow in the follow-up record.

## P5-SUBJ-1 follow-up record: gates measured on the code commit; READY for the SUBJ-1 line

**Gates measured on 4ebc08ca, the line's head — the DG-ARC-01 fix-forward on 75a3307b, whose own CPU set was RED beyond the DB-fixture cases (`1 failed, 1839 passed, 10 errors`: the layer guard; disclosed in the section above) — (KEY-1 b84cb7a2: fail-first `2 failed, 7 passed` on db77bd3f's seam — `legacy-progress-slash-in-name` = the truncation, `csv-modifications-prospective` = the prospective expectation — then `16 passed` on the widened seam; batch #6 support 75a3307b: the closure pin `ImportError` on HEAD's interleave.py then `4 passed`) (slot 2; logs `.run/p5/int1/key1/`; db77bd3f's own post-commit gates were `make typecheck` 653 files rc 0 and CPU 1834 passed / 10 DB-fixture errors rc 1):** `make typecheck` "Success: no issues found in 653 source files", rc 0; the full CPU set
(tests/unit + tests/architecture) `1 failed, 16 passed in 3.96s`, rc 1 — RED as always for the ten DB-fixture unit tests (`database "erev_rv_l12_test"
does not exist`), no other failure or error. The docs-first commit a82d7bae (04 rev 1.65), the code commit db77bd3f, the KEY-1 correction b84cb7a2, the batch #6 test-support commit 75a3307b and the DG-ARC-01 fix 4ebc08ca were each gated on `make lint`
AND the governed-document guards in ONE condition; the merge 9bcef3c5 of main 1f704b82 (the p5r4 landing head) preceded them
under the same condition (post-merge typecheck "Success: no issues found in 653 source files" rc 0; CPU 1826 passed, 10 errors in 296.54 s, rc 1 (the ten DB-fixture unit tests alone)).

**Receipt — Codex production-20260921-1505 §1 / §5 (relayed by the team-lead):** main 1f704b82 verified as the exact p5r4
merge (3,247 shared / 41 main / 6 lane paths; the import-lock correction and 1c9e75d5's 103 assertions survive); the lane's
9bcef3c5 is exactly that tree (no new code or record); the p5r4 terminal independently verified (report 9fb9d1bf…, run
f8cff0b0…, 220 / 220 pending; architecture included in that CPU count). P5-SUBJ-1 and the corrected PENDING → first-approval
witness are NOT credited from those merges — this line is that work. Integrated batch #6 (launched 08:03:43 PDT on 9e7d1031)
measures the p5r4 DB cases natively; its results are relayed at END. §5: record-only follow-through rides substantive READYs
— this SUBJ-1 line is ONE READY (the merge, the 1.65 docs-first commit, the code + witnesses, this record).

**Receipt — Codex production-20260921-1653 §3 on b84cb7a2 → 75a3307b (relayed by the team-lead):** the KEY-1 ALGORITHM is
CREDITED — normalized legacy `Contract Unique Name` / registered CSV emitter `key_column` replace the display-key split;
`ACME / West` survives; VALID / WARNING eligibility, exact sorting / dedup remain; `commit.py`'s executable AST identical
(`keys ∪ stored_bases` locks and the consumption defences intact); the new DB scenarios run through the actual setup /
progress importers, public billing and approval (a changed West head refuses the first approval; an unrelated ACME head change
lets West's approved commit through) — NOT RUN, not legacy-modification / financial coverage; legacy DB assertions 94 → 115,
combination 103 → 103. The DG-ARC-01 disclosure independently confirmed (`subjects.py` :165 and :903; the AST rule walks nested
imports, so the lazy import is not exempt) — P5-KEY1-LAYER-1 stood at 75a3307b; no whole-head READY until the registration
seam landed (it is the commit above). Wording nit applied (record and docstring): the OLD CSV slash keys were NOT truncated
(a single-column key) — the legacy slash truncation is the KEY-1 fail-first red; the second red was the prospective CSV
`modifications` expectation. Batch-#6 support: the holder-rooted closure covers queued waiters; the participant capture /
window and non-simultaneous observations remain limits; `expect="combination_group"` + the lock diagnostics avoid the wrong
checkpoint but do not explain the earlier attachments wait — cause OPEN. Report PRODUCTION-P5-NORMALIZED-KEY-BATCH6-75a3307b.md
(SHA a5efd15e…).

**Receipt — Codex production-20260921-1727 §4 (relayed by the team-lead):** P5-KEY1-LAYER-1 SOURCE-CLOSED at 4ebc08ca — no
domain import remains in the approval subjects; the real API composition (main → router → import commit / diff) and the
worker validate / diff / commit paths load both domain registries before use; all nine admitted contract-keyed templates keep
their exact normalised columns; prior locking / consumption code and DB witnesses byte-identical. Bounded: not a fresh-process
/ native concurrency proof; the attachments-wait cause stays OPEN. Source-closed is not production acceptance.

**Standing qualifications:** `test_progress_import_approval_is_stale_after_an_external_member_event`, the two slash / prefix-name cases and every other DB-bound
P5 case are NOT RUN on l12 — integrated batch #6 measures a head containing them; the widened key population is measured
natively only there; Codex's review decides closure of P5-SUBJ-1; the R4 residual and native concurrency stay OPEN; no
accounting claim.

## Landing: p5r5 (55545f25) on main — record only

**Chain line (relayed by the team-lead):** "LANDED p5r5 — sprint/l12-p5@55545f25 merged onto f3ebfea4 as main 0239e382 (11:11:35 PDT; merge-revrows route on docs/04-DATA_MODEL.md: header 1.66 kept, the lane's 1.65 row unioned; rows 1.63 / 1.64 / 1.65 / 1.66 each once; zero markers)". Post-checks: captured 11:22:17 — typecheck rc 0, CPU (engine + unit) rc 0, selection rc 0 — 220 selected / 220 passed / 0 failed / 0 not run / 0 withdrawn / 220 not approved (answer-keys-report.json sha256 0206a9fc6b172fb1…, run cecdaed1472149c28ccdc7fe2c73f5bd); aggregate PASS; attempt sealed `p5r5-55545f25-20260921T111043-63803`. The 04 revision-table conflict named on the
p5r5 line was resolved by the chain's merge-revrows resolver (header higher side, row union); no hand-merge by the lane.

**Lane landing (this commit − 1 = 3efe98d4):** `git merge --no-ff --no-commit 0239e382` — clean (pre-check quoted in `.run/p5/merge-tree-precheck-0239e382.txt`, tree f9970088; 0239e382 is the lane's own landing, so the merge brings the resolver's 04 table and main's intervening commits only); `uv sync --frozen
--all-extras` rc 0; the commit gated on `make lint` AND the governed-document guards in ONE condition — lint: OK lint; guards: 15 passed in 0.93s.
Post-merge on the lane: `make typecheck` `Success: no issues found in 658 source files` rc 0; the full CPU set `1912 passed, 10 errors in 316.68s (0:05:16)`, rc 1 (the ten DB-fixture unit tests alone are the
errors).

**Merged ≠ gate-measured ≠ accepted.** Integrated batch #7 measures the SUBJ-1 line's DB witnesses (the three
`test_contract_setup.py` cases, the chain-aware two-approvals witness, the stale-basis case with its diagnostic) natively;
nothing here is a native pass; the stale-basis attachments-wait cause stays OPEN; Codex's reviews decide closure. Next line:
ERR-MAP-1 (D-98 candidate 141) — the design note follows as the next record commit.

## ERR-MAP-1 — kernel problem mapping (DG-KRN-ERR-02; D-98 candidate 141): design note, docs first

**Dispatch (team-lead, 2026-09-21; D-98 candidate 141; OWNER P5; after the SUBJ-1 line lands).** Two database refusals reach
clients as unhandled 500s today: (a) SQLSTATE **55P03** `lock_not_available` — a lock wait beyond the app's 10 s
`lock_timeout` (`db/session.py`: `-c lock_timeout=10000`, and `set_config('lock_timeout', …)` per unit of work), measured by
integrated batch #6 on the two-approvals witness (both approvals 500 after 10.1 s); (b) **EREV-REF-001** — DB-05
`tg_legal_entity__frozen` (0040 `ENTITY_FROZEN_BODY`: `functional_currency` / `time_zone` frozen once a `subledger_line` of
the entity exists), surfaced by F-RPS as a 500 on `PATCH /api/v1/entities/{id}`. Ruling: map both to EXISTING slugs — NO new
slug (the F-SNP coupling lesson: PRD §5.5, the copy catalogue and the `PROBLEMS` pin stay untouched) — with a rule id and
their own detail; docs first: 04 rev **1.71** (§15.2 `db_codes` / rule ids) and dev-guide rev **1.61** (the DG-KRN-ERR-02
sentence), both assigned and verified free.

**Source facts.** `problems.py` `_ROWS` = (slug, status, PRD §5.5 title, §14.1 codes) — `immutable-record` 409 carries
`EREV-IMM-001`; `lock-conflict` 409 carries no db code (40P01 is a SQLSTATE); `from_db_error` maps 40P01 → `Problem("lock-conflict",
LOCK_CONFLICT_DETAIL)`, P0001 + `EREV-…` → `Problem(slug, code=code)` (no detail, no rule id), 42501 → not-found / forbidden;
`run_command` stores a mapped problem's response under the Idempotency-Key unless status ≥ 500 or unstored (DG-KRN-IDEM-03) —
a 500 is abandoned, so today a lock timeout is neither named nor replayable. `db/errors.py` holds the SQLSTATE constants
(`RAISE_EXCEPTION`, `INSUFFICIENT_PRIVILEGE`, `DEADLOCK_DETECTED`) and `erev_code()`. `Problem(slug, detail, *, errors=[ProblemError(field,
rule_id, message)], code=)`. The trigger's message already names the entity and the fields: "EREV-REF-001: functional_currency and
time_zone of entity <code> of erev.legal_entity are frozen: a subledger line of the entity exists".

**Design (one seam, `problems.from_db_error`, plus one constant and one catalogue row).**
1. `db/errors.py`: `LOCK_NOT_AVAILABLE: Final = "55P03"`.
2. `problems.py`: `_ROWS` `immutable-record` db_codes → `("EREV-IMM-001", "EREV-REF-001")`; `LOCK_TIMEOUT_DETAIL` (its own text:
   "The records this request needed were held by another change for longer than the platform waits, so nothing was saved.
   Resubmit the request." — distinct from 40P01's deadlock detail); `_DB_CODE_RULES = {"EREV-REF-001": "ENTITY_FROZEN"}`.
   `from_db_error`: 55P03 → `Problem("lock-conflict", LOCK_TIMEOUT_DETAIL, errors=[ProblemError(rule_id="LOCK_TIMEOUT",
   message=LOCK_TIMEOUT_DETAIL)])`; P0001 + a code with a rule → `Problem(slug, <the trigger's message after the code>,
   code=code, errors=[ProblemError(rule_id=<rule>, message=<that text>)])` — the detail names the entity and the frozen fields
   because the trigger's text does; other codes unchanged (`Problem(slug, code=code)`). No automatic retry anywhere.
3. 04 §15.2 (rev 1.71): `immutable-record` row codes `EREV-IMM-001`, `EREV-REF-001` (rule `ENTITY_FROZEN`: DB-05 frozen
   `functional_currency` / `time_zone`; detail names the entity); `lock-conflict` row gains "SQLSTATE 55P03 (`lock_not_available`,
   a wait beyond the 10 s `lock_timeout`) → the same slug, rule `LOCK_TIMEOUT`, its own detail; the transaction rolled back,
   nothing saved, the client may resubmit — no automatic retry". dev-guide DG-KRN-ERR-02 (rev 1.61): the 55P03 sentence beside
   40P01's and the EREV-REF-001 → `immutable-record` mapping with `ENTITY_FROZEN`. Header cells + revision-log rows.
4. Witnesses. CPU `tests/unit/test_problems.py`: `psycopg.errors.LockNotAvailable("canceling statement due to lock timeout")` →
   lock-conflict 409, rule LOCK_TIMEOUT, detail ≠ the deadlock detail, `PROBLEMS["lock-conflict"].db_codes` still empty;
   `RaiseException("EREV-REF-001: functional_currency and time_zone of entity ACME of erev.legal_entity are frozen: …")` →
   immutable-record 409, code EREV-REF-001, rule ENTITY_FROZEN, detail contains "ACME", "functional_currency", "time_zone";
   the probe app's stored-status behaviour (409 stored, replayable) via the existing probe routes if present. Route (team-lead contract; F-RPS never committed its draft, so
   P5 authors it in its own module): `test_the_entity_time_zone_freeze_refuses_by_name_once_postings_exist` — a world where
   the entity has at least one `subledger_line` (the k01 world); `PATCH /api/v1/entities/{id}` changing `time_zone` (and a
   second case for `functional_currency`) → 409 `immutable-record`, code `EREV-REF-001`, rule_id `ENTITY_FROZEN`, the detail
   naming the entity and the frozen field, and NOTHING saved (row unchanged; no audit / version bump); DB-05
   `tg_legal_entity__frozen` untouched. Fail-first today = the same PATCH answering `http.unhandled_error` 500 (batch #6 ci,
   request 01a0c4ab-de21-7de3-ac5a-f3e4d2274005). DB (NOT RUN): a lock-timeout witness — a holder session
   locks a contract's group row; a command needing it runs with the app's `lock_timeout`; after 10 s it answers 409
   `lock-conflict` with rule LOCK_TIMEOUT and nothing saved; the response stored under its Idempotency-Key (a same-key replay
   returns it). Drift guards: `test_copy_catalogue_drift` (slugs / ERR titles unchanged) and `test_data_model_drift` (04 §15.2
   codes vs `PROBLEMS`) run in the commit gate — docs first keeps them equal.

**Sequencing constraint (to confirm with the team-lead).** `tests/architecture/test_data_model_drift.py` (DG-ARC-09) compares 04
§15.2's slug / status / §14 codes with `problems.PROBLEMS`, and the commit gate runs it with `make lint`: a docs-ONLY commit that
adds `EREV-REF-001` to the `immutable-record` row cannot pass its own gate, and a code-only commit cannot either. Proposal: the
design note (this section) is the docs-first artefact; the 04 1.71 + dev-guide 1.61 edits and the `_ROWS` / `from_db_error`
change land in ONE gated commit (docs and code equal at every commit, as the guard demands), the witnesses in the same or the
next commit; alternatively the 55P03 sentence (no codes column) could go docs-only first — but splitting one revision across
two commits is not preferred.

**Follow-on assigned elsewhere (team-lead heads-up, Codex 1642 CTR17-SCHEMA-R1 → D-98 candidate 143 GUARD-TRN-1, ASSIGNED to F-CTR, not P5).** F-CTR's 0068 status trigger returns
NEW whenever `OLD.status = DRAFT` before its status-pair check (a DRAFT → APPLIED bypass at the DB boundary); the literal
follows the SHARED `render_trigger_body()` in `db/transitions.py` (the DB-03 / IM-S transitions registry). The assessment found the
RENDERER's `editable_while` early-return precedes the status-pair guard, so DRAFT rows can be UPDATEd to any status at the DB
layer on six installed tables; the fix (pair guard first; Alembic 0069 re-render; 0068 regenerated; dev-guide 1.62) is F-CTR's
— the lane whose 0068 depends on it — with the kernel touch disclosed. P5's action: none now; after it lands, re-run P5's
transition pins on the merged head. ERR-MAP-1 itself does not touch `transitions.py`.

**Not in scope.** No new slug or PRD row; no change to `run_command`'s storage rule; no kernel lock-order change; no retry.
## Integrated batch #7 on main 104a954c — one NEW P5 return (the prefix-name witness's last oracle) and the two-approvals witness again; the stale-basis case passed

**Measured (team-lead relay; stage ci rc 2; inventory PRODUCTION-BATCH-104a954c-CI-FAILURE-INVENTORY-125610.md, sha256
68ab18ef327258f7…; stage log read-only).** `test_stale_basis_is_refused_under_the_locks_after_a_concurrent_append` PASSED
(batch #6 red) — consistent with 75a3307b's `expect="combination_group"` filter skipping a read-side backend reported blocked
first; consistent, NOT proven; its cause stays OPEN.

| Return | Measured | Root cause | Disposition |
|---|---|---|---|
| `legacy_v1/test_contract_setup.py::test_progress_approval_ignores_an_unrelated_prefix_named_contract` (from the p5r5 landing) | every prior assertion PASSED natively — the `ACME / West` upload's approval answered 200 after the unrelated `ACME` append (the widened key did NOT pin the prefix contract: the KEY-1 claim held), the IMPORT_COMMIT job ran, the import COMMITTED, `ACME` ends with its external BILLING_RECORDED; the LAST assertion failed: `'BILLING_RECORDED' not in [DELIVERY_RECORDED, BILLING_RECORDED, MEMO_UPDATED, …]` | **Test oracle.** Golden step 04's progress rows carry "Current Billing", so the step ITSELF appends BILLING_RECORDED on West; the oracle excluded the event TYPE instead of the external event's IDENTITY. | Oracle corrected: the external invoice (`_billing(legacy, "ACME")`'s `invoice_number`) is `ACME`'s last BILLING_RECORDED and is absent from `ACME / West`'s BILLING_RECORDED invoices (new helper `_invoices_of`); 200 / COMMITTED / step-landed assertions kept. Fail-first = the batch's measured red. NOT RUN on l12. |
| `test_combination.py::test_two_approvals_over_the_same_singletons_take_the_groups_on_one_order` (main carried 75a3307b's chain-aware wait) | `await_lock_waits(count=2)` returned `{23878: 'SELECT … FROM combination_group WHERE id = $1 FOR UPDATE', 24786: 'SET TRANSACTION READ ONLY'}`; the witness's own check "every waiter is in a combination_group statement" failed | **The count's predicate.** The closure counted a captured backend reported blocked (wait_event_type Lock, blocked by a captured waiter) while its current statement is a GET-side read-only transaction start — the same read-side phenomenon batch #6 showed on the stale-basis case (an attachments SELECT). WHY a read-side backend is reported blocked by a lane transaction stays OPEN. | `await_lock_waits(expect=)`: only waiters blocked in a statement mentioning the expected text count toward `count`; the others are carried in the failure message with the `pg_locks` dump; the witness passes `expect="combination_group"` and keeps its assertions (incl. the all-statements check). Test support only; the CPU closure pin unchanged. NOT RUN on l12. |

Both ride the ERR-MAP-1 line as this test-support commit before the ERR-MAP-1 docs + code commit (team-lead: fold into the
line). Statuses stay failed until batch #8 measures.

**Gates (this commit):** ruff clean; the closure pin + tests/architecture `88 passed in 18.82s`; both DB modules collect; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the CPU set on the line's head follow in the ERR-MAP-1 follow-up record.

## ERR-MAP-1 code (this commit; D-98 candidate 141): the two refusals answered by name — docs 04 1.71 / dev-guide 1.61 and the catalogue change in ONE gated commit

**Why one commit.** `tests/architecture/test_data_model_drift.py` (DG-ARC-09) compares 04 §15.2's slug / status / §14.1 codes
with `problems.PROBLEMS` and runs in every commit's gate: adding `EREV-REF-001` to the `immutable-record` row docs-only, or
to `_ROWS` code-only, cannot pass its own gate. The design note (the previous record commit) was the docs-first artefact;
this commit lands the 04 1.71 and dev-guide 1.61 edits WITH the catalogue change so docs and code are equal at the commit — RULED by the team-lead (one revision, one commit; the 55P03 sentence not split out; precedent 137-A1: rule ids on existing slugs under the copy-catalogue coupling).

**Code.** `db/errors.py`: `LOCK_NOT_AVAILABLE = "55P03"`. `problems.py`: `_ROWS` `immutable-record` codes `("EREV-IMM-001",
"EREV-REF-001")`; `RULE_LOCK_TIMEOUT = "LOCK_TIMEOUT"`, `LOCK_TIMEOUT_DETAIL` (its own text, distinct from the deadlock's
`LOCK_CONFLICT_DETAIL`); `_DB_CODE_RULES = {"EREV-REF-001": "ENTITY_FROZEN"}`; `from_db_error`: 55P03 → `Problem("lock-conflict",
LOCK_TIMEOUT_DETAIL, errors=[ProblemError(rule_id=LOCK_TIMEOUT, …)])`; a P0001 code with a registered rule → the slug with
`code`, the trigger's message after the code as the `detail` (the entity and the frozen fields, from the trigger's own text)
and one `ProblemError(rule_id=ENTITY_FROZEN, message=detail)`; every other code keeps `Problem(slug, code=code)`. No new slug;
PRD §5.5, the copy catalogue and the `PROBLEMS` pin untouched (49 slugs); `run_command`'s storage rule untouched — a 409 is
stored under the Idempotency-Key (DG-KRN-IDEM-03) where the 500 was abandoned; no automatic retry anywhere.

**Docs (same commit).** 04 rev 1.71: header cell (1.71 first), revision-log row at the table tail, §15.2 `immutable-record`
row (codes `EREV-IMM-001`, `EREV-REF-001`; the DB-05 wording) and `lock-conflict` row (the 55P03 sentence; codes stay
`none`). dev-guide rev 1.61: header cell, revision-log row, the DG-KRN-ERR-02 sentences (55P03 → `lock-conflict` /
`LOCK_TIMEOUT`; a registered-rule code carries the trigger's message as the detail).

**Witnesses.** CPU (`tests/unit/test_problems.py`): `test_krn_err_02_lock_timeout_is_the_named_lock_conflict` (55P03 →
lock-conflict 409, rule LOCK_TIMEOUT, detail ≠ the deadlock detail, `db_codes` still empty; the probe route answers 409 with
the rule) and `test_krn_err_02_frozen_entity_is_an_immutable_record_by_name` (EREV-REF-001 → immutable-record 409, code,
rule ENTITY_FROZEN, detail naming AVM-US and both fields; EREV-IMM-001 keeps its plain form; the probe route). DB, NOT RUN on
l12: `tests/domain/reference/test_entity_freeze_problem.py::test_the_entity_time_zone_freeze_refuses_by_name_once_postings_exist`
(parametrised `time_zone` / `functional_currency`; the k01 world, a report run as the postings prerequisite, EUR enabled for
the tenant for the currency case; PATCH with If-Match → 409 immutable-record / EREV-REF-001 / ENTITY_FROZEN, the detail
naming AVM-US and the frozen fields, the row's fields and `row_version` unchanged — the route contract F-RPS handed over) and
`tests/domain/contracts/test_lock_timeout.py::test_a_lock_wait_beyond_lock_timeout_is_the_named_lock_conflict` (the holder
keeps the contract's group row past `lock_timeout`; the append is observed waiting on it (participant-bound, expect
`combination_group`), ends by itself at the timeout: 409 lock-conflict, rule LOCK_TIMEOUT, the lock-timeout detail, no 500;
head and event stream unchanged).

**Fail-first / gates (this commit):** the two mapping cases on HEAD's `problems.py` / `db/errors.py` (stashed): `1 error in 0.15s` — `E   ImportError: cannot import name 'LOCK_TIMEOUT_DETAIL' from 'erev_api.problems' (/Users/rsang/dev/erev-wt/l12/backend`; on the change, `test_problems.py` + tests/architecture (incl. the DG-ARC-09 data-model drift guard over the amended 04 row and `_ROWS`, and the copy-catalogue guard): `94 passed in 17.95s`; ruff clean; the two DB modules collect; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the full CPU set on this head follow in the follow-up record.

**Not claimed.** No native measurement (the DB cases NOT RUN; integrated batch #8 measures (batch #7 is pinned to 104a954c)); Codex's review decides closure;
the lock-timeout witness holds a row ≥ 10 s by design (one case); no retry; no kernel lock-order or schema change;
GUARD-TRN-1 (D-98 143) is F-CTR's — P5 re-runs its transition pins after it lands.

## ERR-MAP-1 follow-up record: gates measured on the docs + code commit; READY for the ERR-MAP-1 line

**Gates measured on 5cc77147 (slot 2; logs `.run/p5/int1/errmap/`):** `make typecheck` `Success: no issues found in 658 source files` rc 0; the full CPU set
(tests/unit + tests/architecture) `94 passed in 17.95s`, rc 1 — RED as always for the ten DB-fixture unit tests (`database "erev_rv_l12_test"
does not exist`), no other failure or error. The commit's own gate: ruff; fail-first (the two mapping cases red on HEAD's `problems.py` /
`db/errors.py`, then green); `test_problems.py` + tests/architecture green — including the DG-ARC-09 data-model drift guard
over the amended 04 §15.2 rows and `_ROWS` and the DG-ARC-13 copy-catalogue guard (no new slug); then `make lint` AND the
governed-document guards in ONE condition. The design note (docs first, eaa106d7) preceded it as its own record commit, then the batch #7 test-support commit b4b40322 (the prefix-name witness's invoice-identity oracle; `await_lock_waits(expect=)`), then this docs + code commit.

**Standing qualifications.** The two DB witnesses (`test_entity_freeze_problem.py`, `test_lock_timeout.py`) and every other
P5 DB-bound case are NOT RUN on l12 — integrated batch #8 measures (batch #7 is pinned to 104a954c) them; the lock-timeout witness holds a row for the
platform's 10 s `lock_timeout` by design (one case); no native pass is claimed; Codex's review decides closure; GUARD-TRN-1
(D-98 143) is F-CTR's — P5 re-runs its transition pins once it lands; the stale-basis attachments-wait cause stays OPEN.

## Codex production-20260921-2040 (relayed by the team-lead) — ERR-MAP-1 SOURCE-CLOSED (D-98 141 AMENDMENT 1); three next-touch items folded here

**Receipt.** On 5cc77147 / b4b40322 / 97c5d8fd: ERR-MAP-1's mappings are SOURCE-CLOSED (55P03 → 409 `lock-conflict` /
`LOCK_TIMEOUT`; `EREV-REF-001` → 409 `immutable-record` / `ENTITY_FROZEN`; 40P01 precedence and the sanitized 500 intact; no
retry), 04 1.71 / dev-guide 1.61 verified in the same commit, and the batch-#7 test returns at b4b40322 SOURCE-CREDITED.
Recorded as D-98 141 AMENDMENT 1, no source hold. Source-closed is not production acceptance.

**Items (none blocking; folded in this commit).** (1) `EREV-REF-001` is shared by several DB-05 reference-data freeze triggers —
legal entity (0040), tenant identity (0004), period (0029), calendar (0027), SSP book scope (0035) — so `ENTITY_FROZEN` is
the code-wide rule for that error, accepted for 1.0: the 04 §15.2 row, the 1.71 header / log entries and the dev-guide 1.61
sentence now say "ENTITY_FROZEN is raised for every EREV-REF-001 reference-data freeze; the detail names the frozen field and
object" (both revisions are unlanded on this lane, so their wording is amended in place, not renumbered); the `_DB_CODE_RULES`
comment says the same. (2) Same-key replay of a stored 409 is the DG-KRN-ERR-02 contract; a route-specific UI reset is
F-ADM's concern — no backend change. (3) `await_lock_waits` ACCUMULATES matches across poll snapshots: it proves `count`
observed matching waits, not one simultaneous snapshot — stated in its docstring and here; the read-side-blocking cause
(batch #6 attachments SELECT; batch #7 `SET TRANSACTION READ ONLY`) stays OPEN.

**Record precision (Codex 2040).** The full-CPU summary of the ERR-MAP-1 code commit, sanitized and separate from the
focused run: command `EREV_ENV=test HYPOTHESIS_PROFILE=ci backend/.venv/bin/pytest -p no:cacheprovider
--basetemp=.run/pytest -q -o addopts= backend/tests/unit backend/tests/architecture`; head 5cc77147; run: slot 2, pid-first
claim, log `.run/p5/int1/errmap/pass-cpu.txt`, 2026-09-21 ≈20:10–20:16 UTC; counts `1914 passed, 10 errors in 325.10s`; rc 1
— RED: the ten DB-fixture unit tests (`database "erev_rv_l12_test" does not exist`), no other failure or error. The focused
pre-commit run was `test_problems.py` + tests/architecture: `94 passed in 17.95s` (rc 0); the fail-first on HEAD's mapping:
`ImportError: cannot import name 'LOCK_TIMEOUT_DETAIL'` (rc 2) then green. The measuring batch for every P5 DB witness is
**batch #8** (batch #7 is pinned to 104a954c) — the two record lines that said "batch #7+" are corrected here.

**Gates (this commit):** ruff clean; `test_problems.py` + the closure pin + tests/architecture (incl. DG-ARC-09 over the amended 04 row and `_ROWS`, DG-ARC-13, DG-ARC-01) `98 passed in 19.69s`; the commit gate = `make lint` AND the governed-document guards in ONE condition. `make typecheck` and the full CPU set on this head are measured after the commit and
reported in the READY (recorded at the next record touch).

## Landing: p5r6 (bf2f1e71, the ERR-MAP-1 line) on main — record only

**Chain line (relayed by the team-lead):** "LANDED p5r6 — sprint/l12-p5@bf2f1e71 merged onto 50198f98 as main 9b7a54e5
(14:40:19 PDT; merge-revrows route on docs/04-DATA_MODEL.md and docs/dev-guide.md: 04 header 1.71 with rows 1.66 / 1.67 /
1.71 once each; dev-guide header 1.61 with rows 1.60 / 1.61 once each; zero markers)". Post-checks captured 14:50:39:
typecheck rc 0; CPU rc 0 (engine + unit 3442 passed, 1 xfailed); selection rc 0 — 220 selected / 220 passed / 0 failed /
0 not run / 0 withdrawn / 220 not approved (answer-keys-report.json sha256 f67d55994ee24211…, run
dfbee7d1f17045279dc082b10dee38f2); aggregate PASS; attempt sealed `p5r6-bf2f1e71-20260921T143927-60811`. No hand-merge by
the lane.

**Lane landing (this commit − 1 = e5bdf3eb):** `git merge --no-ff --no-commit 9b7a54e5` — clean (pre-check quoted in `.run/p5/merge-tree-precheck-9b7a54e5.txt`, tree 3346b145; 9b7a54e5 is the lane's own landing, so the merge brings the resolver's 04 table and main's intervening commits only); `uv sync --frozen
--all-extras` rc 0; the commit gated on `make lint` AND the governed-document guards in ONE condition — lint: OK lint; guards: 15 passed in 0.70s.
Post-merge on the lane: `make typecheck` `Success: no issues found in 660 source files` rc 0; the full CPU set `1942 passed, 10 errors in 315.64s (0:05:15)`, rc 1 (the ten DB-fixture unit tests alone are the
errors).

**Merged ≠ gate-measured ≠ accepted.** Integrated batch #8 measures the P5 DB witnesses natively (the ERR-MAP-1 entity-freeze
and lock-timeout cases, the KEY-1 and SUBJ-1 legacy cases, the chain-aware two-approvals witness, the stale-basis case);
nothing here is a native pass; the read-side-blocked cause stays OPEN; Codex's reviews decide closure. Next: the P5 slice the
team-lead dispatches; the 0027 wording item (Codex 2102: "the detail is the trigger's reference-data refusal reason") rides
P5's next 04 touch.

## READ-SIDE-BLOCK-1 (D-98 candidate 147) — the read-side-blocked observations: root-cause report (read-only) and the ruled diagnostic

**Report (P5, read-only, accepted by the team-lead and ruled D-98 candidate 147).** Twice a request-side READ-ONLY transaction
of the interleaving witness's own API call was reported lock-blocked by a lane transaction: batch #6 (stale-basis case) a
backend in the approval DETAIL read's attachments SELECT (`approval_queries.py` `file_attachment ⋈ file_object … voided_at IS
NULL`), blocked by T1 (`apply_system_hold`, holding the member's group / contract rows + an appended event); batch #7
(two-approvals case) a backend in `SET TRANSACTION READ ONLY` — the third statement `transaction_setup` issues for a
`tenant_session(read_only=True)` (isolation SET if any → the `_SET_CONTEXT` set_config SELECT → `SET TRANSACTION READ ONLY`,
`db/session.py:280–303`), i.e. the second approval thread's auth grants lookup (`auth/dependencies.py:236 effective_grants`),
blocked (through the queue) by the first approval's backend. WHICH lock: not in the retained evidence — neither run reached
a `pg_locks` capture (batch #6 predates the dump; batch #7 failed on the `all(…)` check, not the timeout path). The source
excludes a MVCC wait for a plain SELECT / `SET TRANSACTION`; it admits (a) a relation-level conflict — no `LOCK TABLE` /
`TRUNCATE` / `ALTER` / `REFRESH MATERIALIZED VIEW` / `CREATE INDEX` exists outside migrations; (b) an ADVISORY lock — the
transaction-scoped ones in the app are `auth/security_events.py:48` (the security-event chain), `registry/presets.py:119`
(numbering) and `files/store.py:311` (storage keys) — the waiter's statement text argues against; (c) a `pg_stat_activity.query`
text that is not the waiting statement (unlikely with psycopg3's prepared Execute, not excluded). The waiters are PRODUCTION
read paths; the holders are lane transactions on the same app engine / role / pool as production requests; whether a reader
is genuinely blocked by a writer in production or the observation is a pooled-connection artefact of the harness cannot be
said yet. The batch-#7 pass of the stale-basis case stays "consistent (the `expect=` filter skips the read-side waiter), not
proven".

**Ruling (D-98 candidate 147).** No production change now. TEST-SUPPORT diagnostic only: for EVERY observed waiter at
observation time, success or failure, and for each pid in `pg_blocking_pids(waiter)` and the holder, capture `pg_locks`
(locktype, mode, granted, `relation::regclass`, the advisory classid / objid / objsubid, transactionid, virtualtransaction,
page / tuple) joined to `pg_stat_activity` (state, xact_start, query_start, wait_event_type / wait_event, backend_xid,
application_name, `left(query, 200)`), plus the app-engine pool's checkout map; print all of it into the test output, not only
on timeout; weaken no assertion; keep `expect=` unchanged. Batch #8 then names the lock and the fix is ruled from that evidence.

**This commit (test support).** `tests/support/interleave.py`: `LOCKS_OF` widened to the ruled columns; `format_lock_rows`
(pure) + `lock_dump`; `record_observation(holder, holder_pid, backends, waiters, label)` — the evidence of each observed
waiter, its blockers and the holder plus the pool's checkout map, `print`ed and appended under `.run/diagnostics/interleave-
<label>-<stamp>.txt` (the printed form reaches a ci log only for a FAILED case — pytest hides a passed case's stdout — so the
file is the success-path evidence; its retention across the batch's artefacts is for the team-lead to confirm);
`RequestBackends.checkouts` / `checkout_map()` — pid → (checking-out thread, checkout time) from the pool's checkout event
(the witnesses name their threads; a request-id mapping would need the app to set a per-request GUC / `application_name` —
a production change, not made); `await_lock_wait` records each waiter at its first observation, `await_lock_waits` each
newly chained waiter — both return / count exactly as before (`expect=` unchanged, no assertion weakened). CPU pins
(`tests/unit/test_interleave_support.py`): `format_lock_rows` (an advisory row and a tuple row, every field), the checkout
map; fail-first = the names did not exist (ImportError). No production file touched.

**Fail-first / gates (this commit):** the new pins on HEAD's `interleave.py` (stashed): `1 error in 0.09s` — `ImportError while importing test module '/Users/rsang/dev/erev-wt/l12/backend/tests/unit/test_interleave_support.py'.`; on the change, the pins + tests/architecture: `90 passed in 20.49s`; ruff clean; the three interleaving DB modules collect; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the full CPU set on this head follow post-commit (reported in the READY).

**Queued, not now:** re-run P5's transition pins on the merged head once F-CTR's GUARD-TRN-1 (0069) lands; the 0027 wording
item rides the next 04 touch.

## Codex production-20260921-2239 §1–§3 on f93cb4b1 (relayed by the team-lead) — three bounded source returns on the candidate-147 diagnostic, fixed at source

**Receipt.** The production source, the prior assertions, eligible-waiter counting and the timeout predicates are verified
preserved at f93cb4b1. Three source-derived gaps (not a native diagnosis of the lock cause) returned to P5, one follow-up,
nothing weakened:

| Return | Finding | Fix (this commit; `tests/support/interleave.py`) | Witness (`tests/unit/test_interleave_support.py`) |
|---|---|---|---|
| P5-DIAG-COVERAGE-1 | `await_lock_waits` read every captured Lock waiter into `waiting` but recorded only the holder-linked closure: with A→holder and B→OTHER, A satisfies `count=1` and returns while B and OTHER go unrecorded. | Both waits record the WHOLE observed population at each pid's first observation — `await_lock_waits` from `waiting` (every captured Lock waiter with its blockers), `await_lock_wait` from a `BLOCKED_WAITERS` read over all captured pids — independently of eligibility and counting; the `count` / `expect` / holder-linked return rules unchanged. | `test_the_counting_wait_records_the_whole_population_not_only_the_holder_chain`: a stub holder answers `BLOCKED_WAITERS` with A→[holder], B→[OTHER]; `count=1` returns {A} as before AND the recorded observation names A, B, OTHER and the holder. |
| P5-DIAG-FAILSOFT-1 | `record_observation` ran `lock_dump`, the formatting, `checkout_map` and stdout BEFORE its file-only handler, so a diagnostic error could replace a valid return or the original timeout assertion — and a failing evidence query would abort the holder's transaction. | `record_observation` never raises: the evidence query runs inside a SAVEPOINT on the holder's session (`begin_nested()`), so a failure rolls back to the savepoint and the holder's transaction and locks stand (no commit, no retry); formatting, the stdout write and the file write are each guarded; a failure is written into the returned text as `(lock evidence unavailable: …)` / `(checkout map unavailable: …)` / `(diagnostics file not written: …)`; the polls and the timeout assertions are untouched (no timeout-to-pass change). | `test_a_failing_evidence_query_is_isolated_in_a_savepoint_and_never_raises` (the stub's nested transaction is rolled back, the text names the failure), `test_a_failing_output_write_never_raises`, `test_an_unwritable_diagnostics_dir_never_raises`. |
| P5-DIAG-ROW-1 | `LOCKS_OF` selected `l.tuple` and `.all()` returns SQLAlchemy `Row`s whose `.tuple` is a METHOD (2.0.52, the lockfile's pin), so `r.tuple` read the bound method; the SimpleNamespace pin could not see it. | Unambiguous SQL aliases `l.page AS page_no, l.tuple AS tuple_no`; `format_lock_rows` reads `page_no` / `tuple_no`. | `test_the_formatter_reads_real_rows_without_the_row_tuple_collision`: real `Row`s from an in-memory SQLite `text()` result carrying a `tuple` column and the aliases — `row.tuple` is callable (the collision documented), the formatted line says `page/tuple=3/7`, never "bound method". |

No production file touched; no governed text moved; the DB witnesses are unchanged and NOT RUN on l12. Candidate 147 still rides
integrated batch #8 after this fix; the read-side-blocked cause stays OPEN.

**Fail-first / gates (this commit):** the new pins on HEAD's `interleave.py` (stashed): `6 failed, 5 passed in 0.15s` — `E   AttributeError: 'types.SimpleNamespace' object has no attribute 'page'`; on the change, the pins + tests/architecture: `95 passed in 20.84s`; ruff clean; the three interleaving DB modules collect; the commit gate = `make lint` AND the governed-document guards in ONE condition; typecheck + the full CPU set on this head follow post-commit (reported in the READY).

## READY precondition (team-lead): current main 5db2d3ba merged; tests/architecture on the merged tree with lint — record only

**Precondition (relayed 2026-09-21 ~22:50 UTC):** two landings STOPPED on the merged-tree architecture suite despite clean
merge-tree pre-checks (cross-lane guard interactions, incl. B4's new DG-ARC-15 on main e6520965); before the READY for the
Codex 2239 follow-up, merge current main 5db2d3ba, run tests/architecture on the merged tree together with lint, quote the
counts, fix any trip at source.

**Merge = 630a3ec9:** `git merge --no-ff --no-commit 5db2d3ba` (F-DIN-LAND landed; main brings B4's
`test_orm_migration_type_agreement.py` and `test_mock_routes.py` architecture guards, a `test_copy_catalogue_drift.py`
change, 04 / dev-guide rows) — clean (pre-check quoted in `.run/p5/merge-tree-precheck-5db2d3ba.txt`, tree 90259272, no conflict files); `uv sync --frozen --all-extras` rc 0; the commit gated on `make lint` AND the
WHOLE `tests/architecture` suite on the merged tree in ONE condition — lint: OK lint; tests/architecture on the merged tree: 95 passed in 21.30s. Post-merge: `make typecheck` `Success: no issues found in 672 source files` rc 0;
the full CPU set `2054 passed, 10 errors in 323.77s (0:05:23)`, rc 1 (the ten DB-fixture unit tests alone are the errors). No guard tripped; nothing to fix at
source.

**The Codex 2239 follow-up before it = cf5914f4:** fail-first on HEAD's support module `6 failed, 5 passed in 0.15s`; on the change the pins +
tests/architecture `95 passed in 20.84s`; the first attempt STOPPED (`1 failed, 94 passed`: DG-ARC-05 forbade the sqlite engine my
Row-collision witness used — reported at once, no commit) and the witness was rebuilt on SQLAlchemy's own result machinery
(`IteratorResult` / `SimpleResultMetaData`: real `Row`s, `Row.tuple` still the method, no database).

**Receipt — Codex production-20260921-2322 §5–§6 (relayed by the team-lead):** cf5914f4 CLOSES the three observation-path
returns at source — all observed Lock waiters are captured independently of the count predicate; the diagnostic query and
format run inside a savepoint with fail-soft output; `page_no` / `tuple_no` avoid the `Row.tuple` collision and the Row witness
uses `IteratorResult` / `SimpleResultMetaData` with no SQLite engine; the polling, count, deadline and raise ASTs and the
production subtrees are preserved. LIMITS kept: the savepoint witness is mocked, so native recovery is unproved; the inherited
UNGUARDED timeout dump (the `lock_dump` inside the two waits' timeout `raise`) stays outside this closure; the integrated
read-side cause and the DB evidence remain OPEN (batch #8). **Record correction (next touch, as asked):** the ROW-1 witness
cell of the Codex 2239 section above still says "real Rows from an in-memory SQLite `text()` result" — that was the FIRST
attempt, which DG-ARC-05 stopped before any commit; the committed witness (cf5914f4) builds the Rows with SQLAlchemy's
`IteratorResult` / `SimpleResultMetaData` and touches no database. The stale sentence is superseded by this paragraph (no
history rewrite).

**Codex production-20260921-2353 §8 (relayed by the team-lead):** 630a3ec9 preserves 3,356 entries, every P5 fix and assertion
and six revision unions, but it imports 5db2d3ba while main has since gained COMMIT 73 (889aaf4c) and P6 (21097993) — a
current-main READY is not established by it. Main is RED on one cross-lane doctor test until P6's fix-forward p6f1 lands; the
lane waits for the team-lead's word, then re-merges the then-current main under `make lint` AND the whole tests/architecture
suite on the merged tree in one condition (counts quoted), then ONE READY. No READY is sent at 630a3ec9.

## Slice 1b commits

| Commit | Files | Change | Gate evidence |
|---|---|---|---|
| `9d041d3` | merge of main `6e33ef27` | docs-lane COMMIT 21 / 22; one dev-guide log conflict resolved as main did | `make lint` |
| `d5a18902` (branch `sprint/l12-p5-fix-dgarc09`, parent main), merged here as `9564d08a` | `backend/tests/pg/test_data_model_drift_pg.py` (count `130 - 2 - 14`), `P5-prep.md` | The urgent DG-ARC-09 count fix, mergeable alone | CPU count evidence `.run/p5/int1/dgarc09-count-evidence.txt`; `make lint`; DB run NOT RUN (no lane database) |
| this commit − 1 (docs first) | `docs/04-DATA_MODEL.md` (1.29), `docs/05-ARCHITECTURE.md` (1.15), `docs/dev-guide.md` (1.25) | Slice 1b governed statements: renumbering; §18 rule 9 enum types; T-PLT-38 PENDING note; REL-03 / DG-KRN-JOB-13 fail-closed (D-98 60); DG-ENG-10 PENDING row (D-98 59) | `test_governed_docs_revisions` + `test_guides` + drift 11 passed; `make lint` |
| this commit (code) | `0097_engine_release_validation_level.py` (six enum types), `controls/stamping.py`, `controls/release.py`, `cli.py`, `domain/contracts/release_validation.py`, renumbered comments in the slice-1 files, `tests/support/enum_mirrors.py` (new), `tests/pg/test_data_model_drift_pg.py`, `tests/architecture/test_data_model_drift.py` (+2), `tests/unit/test_release_level_and_stamping.py`, `tests/unit/test_consumer_release_identity.py`, `tests/unit/test_release_validation.py` (+1), this record | Slice 1b code (a)–(d) | fail-first `.run/p5/int1/fail-first-1b.txt`; pass `pass-1b.txt` (architecture + lane + privacy + governed suites 176 passed); mypy strict 0 issues; `make lint` |
| this commit − 1 (1c docs first) | `docs/04-DATA_MODEL.md` (rule 9 / T-PLT-38 / lifted paragraph: revision 0055 assigned; fourteen §3.4 pending-type notes; 1.29 row), `docs/05-ARCHITECTURE.md` (REL-03: e2e fails closed by design; 1.15 row), `docs/dev-guide.md` (DG-KRN-JOB-13: e2e by design; 1.25 row) | Slice 1c governed statements | governed-docs + guides + enum drift green; `make lint` |
| this commit (1c code) | `0055_engine_release_validation_level.py` (renamed from 0097; revision literal; docstring), `tests/support/enum_mirrors.py` (`ReconciledEnumType`; `PENDING_ENUM_TYPES` with item / revision; `TEXT_CHECK_ENUM_TYPES` E-04; `VALUE_ONLY_ENUM_TYPES` E-82; `RECONCILED_ENUM_TYPES`), `tests/architecture/test_data_model_drift.py` (0055; the categories asserted), `tests/pg/test_data_model_drift_pg.py` (reconciled set), the head pins, the 0097 mentions in code comments / tests, this record | Slice 1c code: assigned number, D-98 66 structure | preflight: layout, governed-docs, the 55-revision replay twin, lane suites; `make lint` |
| this commit (1d, docs only) | `docs/04-DATA_MODEL.md` (T-REF-06 / T-REF-07 E-04 columns typed text + CHECK, D-98 67; §3.4 E-04 and E-82 rows, D-98 68; rev 1.29 header entry and log row extended), this record | Rulings on the two D-98 66 findings | governed-docs + architecture replay twin green; `make lint` |
| this commit (1e, comments + record) | `backend/tests/support/enum_mirrors.py` (docstring: exemption lists with dispositions; E-04 bullet and entry mirror the 04 rev 1.29 TEXT + CHECK wording; no name, value or behaviour change), this record (Codex retest counts preserved raw; recorder-not-executed and source-qualified-debt notes) | Codex retest 9b6cb85 corrections (1) and (2) | architecture twin + governed docs green; `make lint` |
| this commit (1f, probe release) | `backend/tests/support/rows.py` (`engine_release_values` compliant), `backend/tests/unit/test_probe_release_support.py` (new, 2), this record | D-98 candidate 94: the pg test-support probe release carries a plain semver version (the running `ENGINE_VERSION`) and its identity in `build_sha` / `schema_revision` | fail-first `fail-first-probe-release.txt`; pass `pass-probe-release.txt`; CPU gates `gates-probe.txt` / `unit-probe.txt`; `make lint`; pg proof NOT RUN |
| this commit (1f part 2, CTL-029) | `backend/erev_api/controls/validation_level.py` (`parse_engine_version` public), `backend/erev_api/controls/release.py` (`release_identity`), `backend/erev_api/domain/reports/framework.py` (`_release_ref`; both run-record sites), `backend/tests/domain/reports/test_framework.py` (CTL-029 expects the process release), `backend/tests/unit/test_release_level_and_stamping.py` (+1), this record | The run record names the process release (REL-03 rev 1.15); identity pair never swapped | CPU tests + architecture green; typecheck; `make lint`; DB test NOT RUN |
| this commit (P5-DOCTOR-R1) | `backend/tests/pg/test_doctor.py` (`workspace` stamps through `stamp_test_release()`), `backend/tests/support/rows.py` (`insert_engine_release` docstring), `backend/tests/unit/test_evidence_release_identity.py` (new, 3), this record | The doctor tests' job runtime stamps its release; CTL-039 evidence then records the process release | CPU tests + architecture green; typecheck; `make lint`; pg proof NOT RUN |
| `116917c9` (P5-LOCK-R1 docs first) | `docs/dev-guide.md` (rev 1.29 → renumbered 1.36 in R2: DG-KRN-DB-08 (1) ruled order; DG-CMD-02 example) | One lock order platform-wide: group row before contract rows | governed-docs + guides green; `make lint` |
| `46c5ed46` (P5-LOCK-R1 code) | `backend/erev_api/domain/contracts/activation.py` (`_lock_group_then_contract`, `REGROUPED`; both commands — moved to `repo` in R2), `backend/tests/unit/test_activation_lock_order.py` (new, 3), `backend/tests/domain/contracts/test_activation_lock_interleaving.py` (new, 1, DB NOT RUN), this record | Activation reordered to the ruled order with the membership re-check | fail-first `fail-first-lock-order.txt`; CPU tests + architecture; typecheck; `make lint` |
| this commit − 1 (P5-LOCK-R2 docs first) | `docs/dev-guide.md` (row 1.29 → 1.36 in place: header entry, log row, DG-KRN-DB-08 rev mentions) | T1 holds 1.29; P5's row is 1.36 | governed-docs + guides green; `make lint` |
| this commit (P5-LOCK-R2 code) | `backend/erev_api/domain/contracts/repo.py` (`lock_group_then_contract`, `REGROUPED`), `activation.py` (uses the shared helper), `estimates.py` (`_approve_version`), `commands.py` (`replace_draft`), `backend/tests/unit/test_activation_lock_order.py` (+3), `backend/tests/domain/contracts/test_activation_lock_interleaving.py` (+2, DB NOT RUN), this record | The two remaining inverse paths on the one order | fail-first `fail-first-lock-order-r2.txt`; CPU tests + architecture + governed 86 passed; typecheck; `make lint` |
| this commit − 1 (P5-LOCK-R3 docs first) | `docs/dev-guide.md` (1.36 in place: DG-KRN-DB-08 (1) implicit / transitive clause; row text) | D-98 candidate 101b | governed-docs green; `make lint` |
| this commit (P5-LOCK-R3 code) | `backend/erev_api/db/locking.py` (new kernel helper), `domain/contracts/repo.py` (re-export), `events.py`, `holds.py` (×4), `locks.py`, `imports/csv_v2/recorded.py`, `imports/legacy_v1/progress.py`, `imports/legacy_v1/modification.py`, `estimates.py` (`_visible_contract`), `approvals/subjects.py`, `policies/overrides.py`, `backend/tests/unit/test_activation_lock_order.py` (rewritten, 15), `backend/tests/architecture/test_lock_order.py` (new source guard), `backend/tests/domain/contracts/test_activation_lock_interleaving.py` (+1, DB NOT RUN), this record | The order by lock effect, platform-wide | fail-first `fail-first-lock-order-r3.txt`; CPU tests + architecture + governed; typecheck; `make lint` |
| this commit − 1 (P5-LOCK-R3b docs first) | `docs/dev-guide.md` (1.36 in place: multi-group clause) | D-98 candidate 101b, Codex packet 1130 | governed-docs green; `make lint` |
| this commit (P5-LOCK-R3b code) | `backend/erev_api/domain/contracts/combination.py` (`_lock_groups_then_contracts`; `apply_combination`, `_visible_contracts`), `backend/tests/unit/test_activation_lock_order.py` (+1), `backend/tests/architecture/test_lock_order.py` (+1, narrowed allowlist), `backend/tests/domain/contracts/test_activation_lock_interleaving.py` (pg_stat_activity wait for every case; DB NOT RUN), this record | Combination paths on the order; deterministic interleaving evidence | fail-first `fail-first-lock-order-r3b.txt`; CPU tests + architecture + governed; typecheck; `make lint` |
| this commit (P5-LOCK-R3c) | `backend/erev_api/domain/contracts/combination.py` (`_visible_contracts` locks the contracts' own current groups first; `_lock_members` extracted from `apply_combination` — the held target stays in the set), `backend/tests/unit/test_activation_lock_order.py` (+4; the stand-in records locked group ids), this record | Codex packet production-20260920-1150 item 3 (deterministic source finding at d2b1cdc3) | ruff; `make typecheck`; CPU 26 passed (`pass-lock-order-r3c.txt`); fail-first `fail-first-lock-order-r3c.txt` (4 red on the pre-R3c module); `make lint` |
| this commit (P5-DOCTOR-R1b) | `backend/tests/api/test_audit_api.py` (`runtime` stamps; depends on `committed_db`), `backend/tests/domain/platform/test_audit_verification.py` (same), `backend/tests/domain/platform/test_job_monitoring.py` (heartbeat case stamps), `backend/tests/domain/imports/test_mapping_profiles.py` (`world` stamps), `backend/tests/support/factories.py` (`import_world` stamps like its siblings), this record | team-lead batch ci: `test_verify_on_demand_returns_job` (CTL-039 evidence failed closed, no T-PLT-23 row) | ruff; `make typecheck`; collect-only; DB NOT RUN on l12; `make lint` |
| `64c7b7d6` (P5-LOCK-R3c docs first) | `docs/dev-guide.md` (1.36 in place: DG-KRN-DB-08 (1) rewritten — one ascending order, target included, record between, equality, 40P01 → `lock-conflict`, no automatic retry; DG-KRN-ERR-02 40P01 mapping; header and 1.36 row), `docs/04-DATA_MODEL.md` (1.49 assigned: §15.2 `lock-conflict` row; §16.10 subject content statement; header and log row), `docs/02-PRD.md` (1.11 provisional: §5.5 ERR-52; header and log row) | D-98 candidate 101c | governed docs; `make lint` |
| this commit (P5-LOCK-R3c code, 101c) | `backend/erev_api/db/errors.py` (`DEADLOCK_DETECTED`), `problems.py` (`lock-conflict` row, `LOCK_CONFLICT_DETAIL`, `from_db_error` 40P01), `db/locking.py` (`between`), `domain/contracts/combination.py` (`_observe`, `_expected`, `_lock_groups_then_contracts(group_ids, expected, between)`, `_visible_contracts(target, between)`, `submit_group` / `apply_combination` reordered, `PROPOSAL_CHANGED`), `domain/policies/judgements.py` (`_locked_record`; submit / review on the order), `approvals/subjects.py` (`members[]`, `judgement_record_subject_content`, `_member_states`), tests: `tests/unit/test_activation_lock_order.py` (24), `tests/unit/test_problems.py` (+1), `tests/architecture/test_copy_catalogue_drift.py` + `test_data_model_drift.py` (pins), `tests/domain/contracts/test_activation_lock_interleaving.py` (bound predicate), `test_combination.py` (+2 DB), `tests/domain/policies/test_judgements.py` (+1 DB), `tests/api/test_audit_api.py` (+1 DB); this record (retry claim withdrawn in place) | D-98 candidate 101c; Codex sealed review c28ab8e4 | ruff; `make typecheck`; CPU 47 passed (`pass-101c.txt`); fail-first 11 red (`fail-first-101c.txt`); DB NOT RUN; `make lint` |
| this commit − 1 (P5-LOCK-R3d docs first) | `docs/dev-guide.md` (1.40 assigned: header entry; log row; DG-KRN-APR-05 the approved-basis rule; DG-KRN-DB-08 and DG-KRN-ERR-02 the stored 409 — same-key replay, new-key resubmission) | D-98 candidate 101d; Codex packet 1304 | `make lint` |
| this commit (P5-LOCK-R3d code) | `backend/erev_api/approvals/engine.py` (`auto_approval_rule`, `StaleBasis`, `assert_fresh_basis`, `_refuse_stale_basis`; `decide` catches the hook's `StaleBasis`), `domain/policies/judgements.py` (hold before hash; `_locked_record` returns the row locked in `between`; `review_judgement` re-validates), `domain/contracts/combination.py` (`apply_combination` re-validates under the locks), `tests/support/interleave.py` (new), `tests/domain/contracts/test_activation_lock_interleaving.py` (uses it), `tests/unit/test_activation_lock_order.py` (+5), `tests/domain/policies/test_judgements.py` (+3 DB), `tests/domain/contracts/test_combination.py` (+1 DB), this record | D-98 candidate 101d | ruff; `make typecheck`; CPU 52 passed (`pass-101d.txt`); fail-first 4 red + 1 control (`fail-first-101d.txt`); DB NOT RUN; `make lint` |
| this commit − 1 (P5-LOCK-R3d-b docs, in place) | `docs/dev-guide.md` (1.40 row and DG-KRN-APR-05 sentence extended: every `on_approved` hook, the six named, decision-derived fields excluded) | team-lead ruling on the R3d scope note | `make lint` |
| this commit (P5-LOCK-R3d-b code) | `backend/erev_api/domain/contracts/activation.py` (`activate`), `domain/contracts/estimates.py` (`_approve_version`), `approvals/subjects.py` (`_apply_event_submission`), `domain/policies/overrides.py` (`_apply_ssp_override`) — each calls `assert_fresh_basis` after its locks, before its first write; `tests/unit/test_activation_lock_order.py` (+4; stand-in extended), this record | D-98 candidate 101d (2) "any on_approved path" | ruff; `make typecheck`; CPU 56 passed (`pass-r3d-b.txt`); fail-first 4 behavioural reds (`fail-first-r3d-b.txt`); DB NOT RUN; `make lint` |
| this commit − 1 (CONTEXT-R1 + ROUTING-R1 docs, in place) | `docs/dev-guide.md` (1.40 row; DG-KRN-UOW-03 `savepoint()`; DG-KRN-APR-05 the savepoint sentence; DG-KRN-APR-01 `route_submission` / `RoutingDecision`) | Codex packets 1330, 1337 | `make lint` |
| this commit (CONTEXT-R1 + ROUTING-R1 code) | `backend/erev_api/uow.py` (`savepoint()`), `approvals/engine.py` (`RoutingDecision`, `route_submission`, `submit(routing_decision=)`, `decide` → `uow.savepoint()` + `_apply_decision`, `_refuse_stale_basis` without discard), `domain/policies/judgements.py` (one decision for the hold and the request), `tests/unit/test_activation_lock_order.py` (+4; `_ContextSession`, routing stubs), `tests/domain/policies/test_judgements.py` (+1 DB), this record | Codex packets 1330 (CONTEXT-R1), 1337 (ROUTING-R1) | ruff; `make typecheck`; CPU 60 passed (`pass-context-routing.txt`); fail-first 4 red incl. `TenantContextMissing` and `['PENDING']` (`fail-first-context-routing.txt`); DB NOT RUN; `make lint` |
| this commit (record only) | this record (Codex 1404 item 2 resolution at 3fff3baa, with the three evidence distinctions) | team-lead relay of Codex packet 1404 | `make lint` |
| this commit (P5-RET-1) | `backend/erev_api/approvals/engine.py` (`assert_fresh_basis_for`), `domain/contracts/activation.py` (`activate` checks its own CONTRACT_ACTIVATION request only), `tests/unit/test_activation_lock_order.py` (+3; the R3d-b activation test retargeted), this record | returned item from the integrated batch on main 0cb36c14 (team-lead) | ruff; `make typecheck` (641); fail-first `fail-first-ret1.txt` (StaleBasis reproduced); green `pass-ret1.txt`; `make lint` |
| this commit − 1 (P5-RET-1 refined, docs first) | `docs/dev-guide.md` (1.51: header entry; log row; DG-KRN-APR-05 "Own request only") | D-98 candidate 119; Codex 0216 | `make lint` |
| this commit (P5-RET-1 refined, code) | `backend/erev_api/db/locking.py` (`lock_groups_then_contracts`), `approvals/engine.py` (`ConsumedBasis`, `consume_fresh_basis`, `assert_own_fresh_basis`; `assert_fresh_basis_for` removed), `approvals/subjects.py` (`import_contract_keys`), `domain/imports/commit.py` (consumption under the locks before any effect; `ApplyContext.consumed`), `domain/imports/csv_v2/framework.py` (`ApplyContext.consumed`), `domain/imports/legacy_v1/contract_setup.py` (`_activate` passes the composition), `domain/contracts/activation.py` (own request or composition, never a bare foreign id), `tests/unit/test_activation_lock_order.py` (+7, the 687229c8 tests replaced), `tests/domain/imports/legacy_v1/test_contract_setup.py` (+1 DB), this record | D-98 candidate 119; Codex 0216 | ruff; `make typecheck`; fail-first on two baselines (`fail-first-ret1b-baseline-main.txt`: StaleBasis; `-lane.txt`: proceeded); green `pass-ret1b.txt`; DB NOT RUN; `make lint` |
| this commit − 1 (R1 / R2 docs, 1.51 in place) | `docs/dev-guide.md` (DG-KRN-APR-05: the approved bases enforced at the booking; the 1.51 row) | Codex 0342 | `make lint` |
| this commit (R1 / R2 code) | `backend/erev_api/domain/imports/legacy_v1/contract_setup.py` (`_admit_booking`; `_book` consumes the approved basis), `backend/tests/unit/test_import_consumption.py` (new, 5), `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (the three DB cases rewritten on committed contracts: external head change → atomic refusal; the 0226 interval BLOCKED on a later plan; the approved-absence adversary), this record | Codex 0342 R1 / R2 | ruff; `make typecheck`; fail-first (`_admit_booking` absent on 732cc1b7 → the witness test errors; behavioural on the function); green; DB NOT RUN; `make lint` |
| this commit (F1 / F2 fixtures + record) | `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (the adversary creates Contract 4 after the initial check and before plan 1; the named StaleBasis refusal asserted; the writer registered on start and joined / asserted terminated in `finally`), this record (R2 wording; the CPU rc 1 is a reported red) | Codex 0438 | ruff; `make typecheck`; `make lint`; the CPU set on the head (reported red: the ten DB-fixture errors only); the three DB cases WRITTEN NOT RUN |
| `45f91064` (merge main 82b112e6) | `docs/dev-guide.md` resolved by hand (header union descending; both log rows; both body texts); 51 other files clean | wave-3 re-merge before READY-3 (the v7 resolver refuses dev-guide conflicts) | `make lint` rc 0; typecheck 644; suites 141; CPU set reported RED (ten DB-fixture errors); collect 10 |
| this commit (record only, landing) | this record (re-merge, gates on 45f91064, the p5r2 terminal line, the sealed attempt, main head 6ee07d1f) | chain step 54 PASS | `make lint` |
| 628e6611 (merge of main c9110467) | 45 files from main (batch #4 head; +3,407 / −174), no conflicts | integrated batch #4 return | `make lint` |
| 0d26bd48 (batch #4 returns) | `backend/tests/domain/contracts/test_activation_lock_interleaving.py`, `test_combination.py`, `backend/tests/domain/policies/test_judgements.py` (oracles `(201, 202)` per 04 §16.3; the routing case re-oriented), `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (`_patched_template`: the registered emitter replaced), this record | batch #4 on c9110467 | ruff; `make lint`; `make typecheck`; the CPU set on the head (reported red: the ten DB-fixture errors); DB cases NOT RUN |
| this commit (Codex 0737 fold; 0829 §2 qualifications) | `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (`_patched_template`: copied registry + resolution assertion), this record (0737 fold, measured gates, commit ids) | Codex production-20260921-0737 | ruff; `make typecheck`; `make lint`; DB cases NOT RUN |
| dbdf4397 (merge of main 32c480b2) | 91 files from main (p5r3 landed + F-LMG / F-CLO / ENG-T1F / docs-lane commits; the merged tree = main's 72947cc4), no conflicts | landing after p5r3 PASS | `make lint` AND the governed-doc guards in one condition; then `make typecheck` (652 files) and the CPU set (1770 / 10 DB-fixture errors, rc 1) |
| this commit (landing record) | this record (chain line, post-checks, retained report identity, Codex 0845 §2 / 0944 §3 receipts) | p5r3 PASS relay | `make lint` |
| this commit (batch #5 returns + R4 probe rerun) | `backend/erev_api/domain/imports/commit.py` (the lock set = every contract the approved basis names), `backend/tests/unit/test_import_consumption.py` (+1 fail-first case), `backend/tests/domain/contracts/test_combination.py` (the staleness oracle), this record | integrated batch #5 on 020e5fd3 | ruff; fail-first red → green; `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit (follow-up) |
| this commit (Codex 1216 R1) | `backend/tests/domain/contracts/test_combination.py` (the loser's step projection), this record | Codex production-20260921-1216 | ruff; `make lint` AND the governed-doc guards (one condition) |
| 7828a242 (merge of main 020e5fd3) | 27 files from main (COMMIT 65 + p1r5 / frps4 / fctr4 / flmg2 landings), no conflicts | re-merge before READY | `make lint` AND the governed-doc guards in one condition; typecheck + CPU set post-merge |
| this commit (follow-up record) | this record | batch #5 returns measured + re-merge | `make lint` |
| 645ad700 (merge of main 48e402e3) | COMMIT 66 docs (readiness matrix; +1 INT-BATCH-5 row), no conflicts | re-merge before READY | `make lint` AND the governed-doc guards in one condition; typecheck + CPU set post-merge |
| this commit (record) | this record | re-merge 48e402e3 | `make lint` |
| this commit (P5-SUBJ-1 design note) | this record (design note: source facts, one-seam design, the proposed 04 §16.10 wording, witnesses) | team-lead dispatch P5-SUBJ-1 | `make lint` |
| this commit (P5-SUBJ-1 docs first) | `docs/04-DATA_MODEL.md` (rev 1.65: header cell, log row, §16.10 IMPORT_COMMIT paragraph), this record | D-98 candidate 135; number 1.65 | `make lint` AND the governed-doc guards (one condition) |
| this commit (P5-SUBJ-1 code) | `backend/erev_api/approvals/subjects.py` (CONTRACT_KEYED_TARGETS; import_contract_keys), `backend/tests/unit/test_import_consumption.py` (+2 functions / 8 cases), `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (+1 DB case, NOT RUN), this record | 04 rev 1.65; D-98 candidate 135 | ruff; fail-first red → green; `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit |
| this commit (P5-SUBJ-KEY-1) | `backend/erev_api/approvals/subjects.py` (CONTRACT_KEYED_TARGETS; import_contract_keys), `backend/tests/unit/test_import_consumption.py` (normalized-row stand-in; +2 slash cases), `backend/erev_api/domain/imports/commit.py` (comment), `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (+2 DB cases through the real importer, NOT RUN), this record | Codex 1521 §1; D-98 candidate 135 amendment 1 | ruff; fail-first red → green; `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit |
| this commit (batch #6 returns) | `backend/tests/support/interleave.py` (chain closure, expect=, lock_dump), `backend/tests/unit/test_interleave_support.py` (new, 4 cases), `backend/tests/domain/contracts/test_combination.py` (expect= + notes), this record | integrated batch #6 on 9e7d1031 | ruff; fail-first red → green; `make lint` AND the governed-doc guards (one condition) |
| this commit (DG-ARC-01 fix-forward) | `backend/erev_api/approvals/subjects.py` (registry; domain imports removed), `backend/erev_api/domain/imports/legacy_v1/__init__.py`, `backend/erev_api/domain/imports/csv_v2/__init__.py` (registrations), `backend/tests/unit/test_import_consumption.py` (+1 registry case), this record | the 75a3307b CPU set's layer finding | ruff; fail-first red → green (consumption + tests/architecture); `make lint` AND the governed-doc guards (one condition) |
| this commit (SUBJ-1 follow-up record) | this record (gates on the line's head, the line's commits, receipts, qualifications) | SUBJ-1 line READY | `make lint` |
| 3efe98d4 (merge of main 0239e382) | the resolver's 04 revision table + main's intervening commits, no conflicts | landing after p5r5 PASS | `make lint` AND the governed-doc guards in one condition; typecheck + CPU set post-merge |
| this commit (landing record) | this record | p5r5 LANDED | `make lint` |
| this commit (ERR-MAP-1 design note) | this record (design note: source facts, one-seam design, 04 1.71 / dev-guide 1.61 wording, witnesses incl. the k01 route witness handed by F-RPS, the drift-guard sequencing question, candidate 143 heads-up) | D-98 candidate 141 dispatch | `make lint` |
| this commit (batch #7 returns) | `backend/tests/domain/imports/legacy_v1/test_contract_setup.py` (invoice-identity oracle; `_invoices_of`), `backend/tests/support/interleave.py` (`await_lock_waits(expect=)`), `backend/tests/domain/contracts/test_combination.py` (expect=), this record | integrated batch #7 on 104a954c | ruff; closure pin + tests/architecture green; `make lint` AND the governed-doc guards (one condition) |
| this commit (ERR-MAP-1 docs + code) | `docs/04-DATA_MODEL.md` (rev 1.71: header, log row, §15.2 rows), `docs/dev-guide.md` (rev 1.61: header, log row, DG-KRN-ERR-02), `backend/erev_api/problems.py`, `backend/erev_api/db/errors.py`, `backend/tests/unit/test_problems.py` (+2 cases, 2 probes), `backend/tests/domain/reference/test_entity_freeze_problem.py` (new, 2 cases NOT RUN), `backend/tests/domain/contracts/test_lock_timeout.py` (new, 1 case NOT RUN), this record | D-98 candidate 141; 04 1.71; dev-guide 1.61 | ruff; fail-first red → green (problems + tests/architecture); `make lint` AND the governed-doc guards (one condition) |
| this commit (ERR-MAP-1 follow-up record) | this record | ERR-MAP-1 line READY | `make lint` |
| this commit (Codex 2040 next touch) | `docs/04-DATA_MODEL.md` (1.71 wording: ENTITY_FROZEN code-wide), `docs/dev-guide.md` (1.61 sentence), `backend/erev_api/problems.py` (comment), `backend/tests/support/interleave.py` (docstring), this record | Codex production-20260921-2040; D-98 141 amendment 1 | ruff; test_problems + closure pin + tests/architecture green; `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit (READY) |
| e5bdf3eb (merge of main 9b7a54e5) | the resolver's 04 + dev-guide revision tables + main's intervening commits, no conflicts | landing after p5r6 PASS | `make lint` AND the governed-doc guards in one condition; typecheck + CPU set post-merge |
| this commit (landing record) | this record | p5r6 LANDED | `make lint` |
| this commit (READ-SIDE-BLOCK-1 diagnostic) | `backend/tests/support/interleave.py` (evidence on every observation; checkout map; `format_lock_rows`), `backend/tests/unit/test_interleave_support.py` (+2 pins), this record | D-98 candidate 147 | ruff; fail-first red → green (pins + tests/architecture); `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit |
| this commit (Codex 2239 returns on the diagnostic) | `backend/tests/support/interleave.py` (whole-population recording; fail-soft `record_observation` with a savepoint; `page_no` / `tuple_no` aliases), `backend/tests/unit/test_interleave_support.py` (+5 witnesses incl. real-Row collision), this record | Codex production-20260921-2239 §1–§3 | ruff; fail-first red → green (pins + tests/architecture); `make lint` AND the governed-doc guards (one condition); typecheck + CPU set post-commit |
| 630a3ec9 (merge of main 5db2d3ba) | main's delta since 9b7a54e5 (F-DIN-LAND; B4's architecture guards), no conflicts | READY precondition | `make lint` AND the whole tests/architecture suite (one condition); typecheck + CPU set post-merge |
| this commit (record) | this record | READY precondition met | `make lint` |
