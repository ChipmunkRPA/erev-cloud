# eRev Cloud legacy migration guide

This guide covers moving from legacy eRev, the desktop application over `ASC606.db`, to eRev Cloud: the two migration modes, the reconciliation report that gates promotion, the legacy-parity preset, how the source file is handled, the legacy field mapping, the parallel-run comparison, and acquired contracts and onboarding from other systems. It describes the API and the built screens at this revision and says where a specified step is not built yet. Everyday use of the product is in the [user guide](user-guide.md); the desktop-button map is its section "Coming from eRev desktop".

What release 1.0 does not do for a migration — replay mode and promotion, a legacy modification on a combined contract group, the tie-outs of onboarded history — is stated in [the limits of release 1.0](../release/LIMITS-1.0.md), section B.5.

A migration is a record (`MIG-000001`, …) with a mode, a source file and a status: `UPLOADED`, `PROFILING`, `PROFILED`, `IMPORTING`, `IMPORTED`, `RECONCILED`, `SUBMITTED`, `PROMOTED`, or `FAILED` and `CANCELLED`. Running a migration needs `migration.run` for all entities — a migration is an act on the workspace: the database holds the contracts of any entity and the import creates entities, so every route under `/api/v1/migrations` answers a member whose role names entities 403; approving its promotion needs `migration.approve` by a user other than the runner. The detail screen is `/data/migrations/:migrationId` with the steps profile, mapping, import, reconciliation and promotion; the migrations list and the new-migration screens are not routed at this revision, so a migration is created through the API and then opened by its id.

## Mode (a): opening balances with a cutover

Mode (a) takes the latest version of each obligation in `Contract_Live` as opening balances (allocation, cumulative revenue, cumulative billing, positions, remaining quantities) as of a cutover date you choose. The full legacy version history is attached read-only, labelled "Migrated, unattributed", and is never presented as audit-trail evidence: the audit log holds only the migration commands (REQ-MIG-001).

1. Upload the database: `POST /api/v1/files` with purpose `LEGACY_DATABASE`. Legacy databases must be SQLite files of at most 500 MiB.
2. Create the migration: `POST /api/v1/migrations` with `mode` `OPENING_BALANCES` and the `source_file_id`. The source is recognised as a legacy eRev database (otherwise 409 `legacy-database-unrecognized`) and its SHA-256 is recorded; a database already imported is refused by name (see Source file handling).
3. Profile it: `POST /api/v1/migrations/{migration_id}/profile` runs the profiling job; `GET /api/v1/migrations/{migration_id}` then shows the `profile`: table row counts, contracts, legacy obligation rows, `SKU_SSP` rows, the SSP version labels, the selling entities and the latest `Current Period`.
4. Confirm the mapping and run the import: `POST /api/v1/migrations/{migration_id}/import` with `mode` `OPENING_BALANCES`, the `cutover_date` (on or before the latest legacy period; set once, it cannot change), the `entity_mapping` (each legacy `Selling Entity` to an entity code, with a fiscal calendar and time zone for an entity that will be created, or `entity_defaults` for all of them), the `batch_parameters`, and the switches `create_missing_entities` and `create_missing_products` (both default true for legacy sources). The field mapping is fixed by the data model (see Legacy field mapping) and is shown read-only; `GET /api/v1/migrations/field-mapping` returns its 71 rows. The `MIGRATION_IMPORT` job stages the rows, dry-runs the load and captures the population; the migration moves `PROFILED` → `IMPORTING` → `IMPORTED`. A failure commits nothing.
5. Reconcile: `POST /api/v1/migrations/{migration_id}/reconcile` runs the `MIGRATION_RECONCILE` job, writes the reconciliation lines once and moves the migration to `RECONCILED` (see the report below). `GET /api/v1/migrations/{migration_id}/reconciliation-lines` pages the lines; `GET …/legacy-rows` pages the migrated `Contract_Live` rows in source order.
6. Promote: submitting the migration for promotion (subject `MIGRATION_PROMOTION`, approved by a Controller other than the runner with a fresh authenticator code) activates the contracts with `OPENING_BALANCE_ESTABLISHED` events dated at the cutover and applies the legacy-parity preset to the workspace. Promotion needs zero unexplained differences. Status at this revision: the submit and promotion commands are not in the API (the statuses `SUBMITTED` and `PROMOTED` exist; the migration reaches `RECONCILED`), so a reconciled opening-balances migration cannot be promoted yet.

`POST /api/v1/migrations/{migration_id}/cancel` cancels a migration that is not promoted. For periods before the cutover, the legacy exports and the `extract_legacy_contract_live` dataset read the migrated legacy rows unchanged, with no eRev lineage.

## Mode (b): replay into a sandbox, then promotion

Mode (b) replays the legacy template files in order into a sandbox workspace created for the migration, under the legacy-parity preset, committing each batch in order without per-batch approval; the reconciliation compares the sandbox with the reference database; after the promotion approval the same import batches are re-executed into the production workspace under that approval, each production batch recording the approval id. The sandbox itself is never converted to production (REQ-MIG-002).

The plan is a list of files in the legacy order: for each file its `template_code` (`legacy_sku_ssp`, `legacy_contract_setup`, `legacy_progress_tracking`, `legacy_contract_modification`), for a modification file its `mode` (`prospective`, `retrospective`, `pob_price_change`), and for progress and modification files the `effective_date`. Status at this revision: `POST /api/v1/migrations` accepts `mode` `REPLAY`, but `POST /api/v1/migrations/{migration_id}/import` refuses a replay plan with "Replay imports (D-31 mode b) are not available yet; this migration cannot be imported.", so mode (b) cannot run yet. The legacy templates can still be imported one by one through the import wizard (`/data/imports/new`), each with its own dry-run diff and approval, which is the desktop button flow rather than the replay migration.

## Migration reconciliation report (RPT-41)

Report code `migration_reconciliation` (formats XLSX, CSV, PDF, JSON; run like any report with `POST /api/v1/report-runs` and parameter `migration_id`, optionally `only_differences`), also embedded on the reconciliation step of the migration. Per contract and per obligation ("Contract level" rows have no obligation key) it compares the legacy value with the eRev value for each measure: `POB_COUNT` (obligation count), `TRANSACTION_PRICE`, `ORIGINAL_ALLOCATION` (the obligation's creation-time allocation), `ALLOCATION`, `REVENUE_CUM` (revenue to date), `BILLED_CUM` (billed to date), `NET_POSITION` (billed less recognized), `RECLASS` (reclassification to contract asset) and `REMAINING_QTY`. Values are exact decimal text at full precision, never rounded to posted cents (billed to date is the one posted-cents billing fact); the tolerance is `0.0001`. Every difference above tolerance carries either a `deviation_ref` (a documented legacy deviation, `docs/legacy/DEVIATIONS.md`, for example `DEV-052`) or an exception item; a line with neither is unexplained. Control totals: contracts, legacy obligation rows, lines compared, differences above tolerance, explained, unexplained; the tie-out `TO_MIGRATION_UNEXPLAINED_ZERO` must pass before promotion (REQ-MIG-003).

## The legacy-parity preset

Migrated workspaces start with the legacy-parity preset (REQ-MIG-005): the accounting policy set whose every parameter takes its legacy-parity value, so the engine reproduces the desktop application's figures (the documented deviations excepted). `POST /api/v1/policies/presets/legacy-parity` (`config.author`) creates the preset as a `DRAFT` version of the tenant accounting policy set for a scope; it then follows the configuration lifecycle (submit, approval publishes). A promoted migration applies the preset to the workspace. Switching from the preset to native policies later is an ordinary prospective policy change: a new version, approved, effective from its date; history is not recomputed.

## Source file handling and SHA-256

The legacy database is opened from the uploaded copy, read-only (the reader sets `query_only` and refuses untrusted schema objects), and is never modified; the file's SHA-256 is computed at upload, recorded on the migration as `source_sha256` and shown on the detail screen next to the file name (REQ-MIG-004). The uploaded bytes never change, so the hash of the file after the journey equals the hash before it. Creating a second migration from a database with the same SHA-256 is refused with 409 `duplicate-import` and the message "This legacy database was already imported in migration <number> on <date>." — the same file never creates duplicates. The upload limit for the `LEGACY_DATABASE` purpose is 500 MiB; the file is stored encrypted at rest like every upload.

## Legacy field mapping (04 §17.2)

The 71 `Contract_Live` columns map to eRev Cloud as fixed by the data model; `GET /api/v1/migrations/field-mapping` returns the rows (`LM-CL-01` to `LM-CL-71`: legacy column, target `table.column`, transformation rule). The rules that matter when you read the result (REQ-MIG-006):

| Legacy | eRev Cloud |
|---|---|
| `Contract Unique Name` | the contract's external id (business key per workspace) |
| `POB Unique ID` | the obligation key |
| `SKU Name` | the product code; a product absent from the workspace is created by the import (`create_missing_products`) with the parity obligation template of the row |
| `ASC 606 Stratification` | the revenue category, except `VC`, which becomes a transaction-price component |
| `Distinct` / `Nondistinct` | distinctness `distinct` / `nondistinct`; reclassification to a series is a post-migration judgement record |
| `Selling Entity` | the contracting and performing entity (created when absent, with the calendar and time zone you map) |
| account columns (`Deferred Revenue Account`, `Unbilled A/R Account`, `Revenue Account`) | account mapping; an account absent from the chart is created when `create_missing_accounts` allows it |
| `Material Right` obligations | material rights under the preset convention |
| `SSP Version` | SSP book versions of the legacy SSP book, one version per distinct label |
| `Contract Position` | equals the labelled net position (billing less revenue); no sign inversion |

`SKU_SSP` (9 columns) maps to products and SSP entries the same way (04 §17.3); the four template header sets are 04 §17.4.

## Parallel-run comparison (RPT-42)

Report code `parallel_run_comparison` (REQ-MIG-007): for a migration and a period range (`migration_id`, `from_period_key`, `to_period_key`), section 1 compares the legacy journal lines by account with eRev's (legacy debit and credit, eRev debit and credit, difference) and section 2 compares contract balances per period end (legacy billed less recognized against eRev contract liability and contract asset plus unbilled receivable). Status at this revision: the definition is in the report catalogue, but no builder is registered for it, so a run produces no output yet.

## Acquired contracts and onboarding from other systems

What exists at this revision and what is pending are different layers (Codex production-20260922-0017 P8-DEP7-EVENT-1):

- Built — the event, its schema and the engine. The contract event kind `OPENING_BALANCE_ESTABLISHED` (04 §16.3; payload versions 1 and 2) carries a `reason` of `LEGACY_MIGRATION`, `SYSTEM_ONBOARDING` or `BUSINESS_COMBINATION`, the `cutover_date` and the per-obligation opening members (cumulative revenue, billing, positions, remaining quantities) and, for a business combination only, `fair_value_contract_liability`. Engine stage S07 establishes the opening balances for every reason (the cutover must be a period end, `ONBOARDING_CUTOVER_NOT_PERIOD_END`; inconsistent members are `OPENING_BALANCE_INCONSISTENT`) and applies the business-combination rules of the tenant's accounting policy set (ENGINE_SPEC S07-R-08; POL-215 to POL-217, including the fair-value member under IFRS 15); the contract balance rollforward shows balances established with reason `BUSINESS_COMBINATION` on the "Business combinations" line (S15-R-06). The legacy migration of mode (a) is the one producer today: its import appends the event with reason `LEGACY_MIGRATION`.
- Pending — the public generic intake. 04 §16 specifies onboarding through the `contracts` import template with the batch parameters `onboarding.method`, `cutover_date` and `onboarding_reason` (`SYSTEM_ONBOARDING` or `BUSINESS_COMBINATION`), the acquisition parameters `bc.expedient_modification_aggregation` and `bc.expedient_ssp_at_acquisition`, and optional `opening.<member>` columns per line, with the commit appending `CONTRACT_BOOKED`, `CONTRACT_ACTIVATED` and `OPENING_BALANCE_ESTABLISHED` on approval (REQ-MIG-008, REQ-MIG-009). The import pipeline does not read these parameters or columns at this revision, so neither intake can be run yet.

The ordinary `contracts` import creates or replaces contract drafts with their inception data; it is not an equivalent cutover or onboarding intake, and using it for in-flight or acquired contracts would recompute them from inception without an opening balance. The accounting treatment of acquired contracts follows the tenant's accounting policy set and its approvals; this guide makes no election.

## Legacy fixtures and provenance

The parity suite replays the legacy example UAT workbooks and compares the results with values recorded from legacy eRev (`docs/legacy/golden/`). The inputs are committed as fixtures, so every run uses the same bytes (DG-PAR-02).

| Fixture | Files | Read from | Verified against |
|---|---:|---|---|
| `backend/tests/fixtures/legacy_uat/NN-<slug>/<workbook>` | 14 | The step's `file` under `legacy-harness/erev_copy/`, else under the read-only legacy repository `~/dev/erev-legacy/` | `docs/legacy/golden/NN-<slug>/step.json` `file_sha256`, steps 01 to 14 |
| `backend/tests/fixtures/legacy_probes/<workbook>` | 3 | `legacy-harness/out/probes/inputs/`: the probe workbooks named in `docs/legacy/golden/probes/*/probe.json` `sequence` | The committed bytes; the golden documents record no hash for them |
| `backend/tests/fixtures/legacy_db/ASC606-shipped-step04.db` | 1 | `legacy-harness/fixtures/ASC606.shipped.db` | `docs/legacy/golden/manifest.json` `shipped_db_sha256` |

`backend/tests/fixtures/manifest.json` lists every fixture as `{path, sha256, bytes, source}`, sorted by path. `path` is relative to `backend/tests/fixtures/`. `source` names the provenance: `legacy:<path in the legacy repository>` for UAT workbooks and the harness path for the others.

| Command | Effect | Final line |
|---|---|---|
| `make fixtures` | Copies missing fixtures after verifying their sources, keeps identical ones and writes the manifest | `OK fixtures` |
| `make fixtures CHECK=1` | Verifies the manifest against the golden documents and the SHA-256 and size of every file. Writes nothing. Runs inside `make lint` | `OK fixtures` |

The builder `scripts/build_fixtures.py` follows these rules:

- It copies bytes only. It never imports legacy code, never writes outside `backend/tests/fixtures/` and runs with `PYTHONDONTWRITEBYTECODE=1`.
- It refuses to overwrite a fixture with different bytes. A changed source is investigated, never copied over the committed file.
- When a source is missing and the fixture is absent, it exits 1 with `BLOCKED: legacy fixture <path> unavailable`. When a source is missing but the committed fixture still matches its hash, it keeps the fixture.
- A failing run writes nothing.
- The shipped database is copied as a file and never opened. eRev Cloud reads legacy databases only read-only (D-40a).
- Every fixture is at most 5 MiB (DG-GIT-04).
