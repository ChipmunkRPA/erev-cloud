# Sprint L8 lane L8-R (reports and journals platform rulings): batch 1 evidence

Lane builder L8-R, worktree `~/dev/erev-wt/l1` (branch `sprint/l1`), fast-forwarded to main 0266227 and `make setup` OK. Rulings implemented from `docs/reviews/loop/sprint/D-88-rulings.md` as amended, with the Supervisor calls section (L7-1-Q-5 over L7-3-Q-6; L7-3-Q-3).

## Commits

| Commit | Ruling |
|---|---|
| 6919c60 | L7-1-Q-7: probe month window must equal the whole calendar month |
| 584576b | L7-1-Q-4: legacy JE summary January tests read the shipped world |
| bde453d | L7-1-Q-5 and L7-3-Q-3: report run data carries the dataset columns; the API serialises the tie-out difference (one commit, because both rulings touch schemas/reports.py, framework.py, the generated openapi.json and schema.d.ts, and viewer.test.tsx) |

## L7-1-Q-7 (probe P1 window key)

- `backend/tests/support/parity/probes.py`: `journal_window` takes `reports['je_<gross|delta>'].window` for a key `je_<gross|delta>_<YYYY>_<MM>` without its own report only when the window equals `[YYYY-MM-01, last day of that month]` (`_month_window`, `calendar.monthrange`; a month outside 1 to 12 gives no window). Otherwise None, so the key fails with `JOURNAL_NO_WINDOW`. The docstring reads as DG-PAR-06 amended.
- Test added: `backend/tests/unit/parity/test_probe_support.py::test_journal_window_of_a_month_label_is_the_whole_month`. It covers the ruled cases (`['2023-01-01', '2023-03-31']` gives None; `['2023-01-01', '2023-01-31']` gives that window), plus leap February 2024, a 29 February 2023 window refused, a one-date window, month 13, a non-month label, a key with its own report, and `JOURNAL_NO_WINDOW` from `compare`. The existing P1 assertion (`je_gross_2023_01` gives January 2023) stays.
- Counts: `make test TESTS=backend/tests/unit/parity/test_probe_support.py K=journal`: 2 passed.

## L7-1-Q-4 (test_legacy_reports uses the shipped fixture)

- `backend/tests/domain/reports/test_legacy_reports.py`: `test_legacy_je_summary_january_gross` and `_delta` take `shipped` and call `_run(shipped.world, JE_SUMMARY, {**JANUARY, "mode": mode})`. `_je_summary`, the `ledger` fixture and the `JournalWorld` and `uat_ledger_world` imports are removed; `worlds.uat_ledger_world` and its `tenant_code` parameter stay. The docstring `ledger` bullet is replaced by the ruled sentence. Every assertion is unchanged.
- Figures reproduce in the shipped world. GROSS: 5001 Cr 187.69, 5002 Cr 118.53, 5003 Cr 48.32, 15002 Dr 58.85, 21001 Dr 295.69; 6 lines; 354.54 = 354.54; net 0.00. By entity 295.69 / 295.69 and 58.85 / 58.85; the two line items. DELTA: 5001 Cr 187.69, 5002 Cr 52.53, 5003 Dr 39.68, 15002 Dr 58.85, 21001 Dr 141.69; 240.22 = 240.22. No mismatch, so no merge note on figures.
- Counts: `make test TESTS=backend/tests/domain/reports/test_legacy_reports.py SLOW=1 K=je_summary`: 2 passed, 12 deselected (22.6 s).

## L7-1-Q-5 (additive `columns` on GET /report-runs/{id}/data)

- Backend:
  - `framework.run_rows` returns `(rows, columns)` from the stored dataset document; its only caller is `api/v1/reports.py report_runs_data`.
  - `schemas/reports.py` adds `ReportColumnOut {key, header, kind}` and `ReportRunDataOut {items, next_cursor, columns}`. `ReportRunDataOut` is the route's `response_model`; `ListOut_ReportRowOut_` leaves the OpenAPI document.
  - `make openapi` regenerated `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` (committed with the change).
- Frontend:
  - `lib/api/queries/reports.ts`: `fetchReportRows` reads `/data` with its own page reader (`read` plus `listSearch`, not `fetchListPage`). It returns `{rows, columns}`, with the first page's columns.
  - `viewer/useReportRun.ts`: two observers of the one rows query (`select` rows and `select` columns), so `rows.data` keeps its shape for SF-04, SF-06:entries and SF-08. The hook returns `columns`, and `report.tsx` passes them into `ColumnContext`.
  - `viewer/specs.ts`: `ColumnContext.columns` is optional. For kind `LEGACY_EXPORT`, `orderedKeys` takes the keys in `columns[].key` order; STRUCTURAL keys stay hidden, and a row field that names no column keeps its row order after them. Other reports keep the §5.6 rank order (post-rc per the ruling).
- Tests added:
  - `backend/tests/api/test_report_runs.py::test_data_columns_in_builder_order` (report_world K-01, AVM-US, 2026). A JSON `legacy_contract_history_export` run answers `[c['key'] for c in columns] == list(legacy_columns.NAMES)` (71), with the headers, on the first page and on a later page (`limit=1`, cursor). A `contract_history` run answers `[c.key for c in contract_history.COLUMNS]` in order, and the kinds match the builder.
  - `frontend/src/routes/reports/__tests__/viewer.test.tsx` 'legacy export column order'. It uses 71 synthetic keys 'Legacy column 01' to '71' (no DS-LINT-19 or REQ-UX-010 term), a columns permutation that is neither sorted nor reversed (01, 30, 59, 17, …), and row fields arriving in reverse order. The rendered headers equal the columns order. Mutation check: with the legacy branch returning row order, the test fails ('Legacy column 71' first); the file was restored and compared byte for byte.
  - `frontend/e2e/projects/screens.spec.ts` (SF-08:report legacy_contract_history_export step) asserts that the first three column headers are 'Contract Unique Name', 'POB Unique ID' and 'SKU Name'. It passes on the seeded demo world: `make e2e SPEC=frontend/e2e/projects/screens.spec.ts:2536 PROJECT=screens` ran only 'SF-08:report marcus', including its legacy_contract_history_export step, with 1 passed and 0 errors.
- Counts: `make test TESTS=backend/tests/api/test_report_runs.py SLOW=1`: 6 passed. Vitest `viewer.test.tsx` and `schedules.test.tsx`: 2 files, 16 passed. prettier, eslint and `tsc -b` clean.

## L7-3-Q-3 (tie-out `difference`, API-only at serialisation)

- Backend:
  - `tie_outs.difference(item)` returns actual − expected per currency in code order through `tie_outs.money()` (minor-unit quantize, no negative zero). It gives None when either side is not a list of API-S-Money (`NOT_APPLICABLE`).
  - `framework.run_outs` fills `difference` where the run is serialised: `TieOutResultOut.model_validate({**item, "difference": tie_outs.difference(item)})`.
  - `TieOutResultOut.difference: list[MoneyOut] | None` is required and nullable in the OpenAPI schema.
  - Unchanged: stored `tie_out_results` (T-RPT-02), the JSON dataset, manifests, XLSX and PDF, so output SHA-256 and rerun identity are unaffected (`test_framework.py::test_ctl_029_run_record_and_rerun` passes).
- Frontend: `viewer/TieOutStrip.tsx` renders the API `difference` for a failing result, per currency. `decimalDifference` is removed, so there is no money arithmetic in the browser (DG-FE-08).
- Tests added or changed:
  - New `backend/tests/unit/reports/test_tie_out_difference.py` (2 tests): a multi-currency failing result (EUR 1.01, JPY −5000, USD −1000.00) leaves the stored item without `difference`; a passing result gives 0.00, `-0.00` gives 0.00, and NOT_APPLICABLE gives None.
  - `test_balances_reports.py` (CTL-030 waterfall PASS 0.00, FAIL −250.00; rollforward PASS 0.00) and `test_rpo_disaggregation.py` (RPO PASS 0.00 twice; disaggregation PASS 0.00 twice, FAIL −250.00): the exact tie-out dicts gain the serialised `difference`.
  - `viewer.test.tsx`: the 'tie-out strip' fixtures carry `difference`, and the `decimalDifference` assertions are removed. New 'tie-out difference is the API figure': a failing result with USD difference −7.25, which is not actual − expected, renders 'Difference USD (7.25)' or '−7.25', and a currency without a `difference` entry (JPY) shows no Difference.
  - RC-SMOKE.10 (`frontend/e2e/journeys/rc-smoke.journey.ts`) is not edited: lane L8-J owns it.
- Counts: `make test SLOW=1` over the unit file, `test_balances_reports.py`, `test_rpo_disaggregation.py` and `test_framework.py`: 25 passed (72.6 s). Vitest as above.

## Gates

All gates ran on bde453d (the three ruling commits on main 0266227), with gate slots, detached, and bounded waits.

| Gate | Result |
|---|---|
| make lint | OK (design-check 274 files, 0 errors; vocab-check OK; licence-check 0 findings) |
| make typecheck | OK (mypy strict, tsc) |
| make openapi | regenerated and committed in bde453d |
| make ci | OK: backend 2113 passed, 0 failed, 0 skipped; vitest 597 passed, 0 failed, 0 skipped (main at the L7 gate: 2109 and 595; +4 backend and +2 vitest are this batch's new tests) |
| make test-pg | OK: 290 passed, 0 failed, 0 skipped |
| make parity K="not point_in_time_equivalence" | OK: 121 selected; 121 passed, 0 failed, 0 skipped (contract_position A 29, C 21; cumulative_catchup A 1, C 9; initial_allocation A 14, C 2; journal_entry_totals A 10, B 5, C 9; legacy_probe A 1, B 3; pob_position B 1, C 16) |
| make e2e SPEC=frontend/e2e/projects/screens.spec.ts:2536 PROJECT=screens (SF-08:report marcus only) | OK: 1 passed, 0 failed, 0 flaky, 0 skipped (28.8 s); the selected test ran its legacy_contract_history_export step with the new header assertions. The full screens project and the smoke journey were not rerun: L8-J owns rc-smoke.journey.ts. |

## Spec questions

- **L8-R-Q-1 (`ReportColumnOut.kind` vocabulary).** The 04 §16.9 amendment names `{key, header, kind}` without an enumeration. The batch types `kind` as a string that carries the builder ColumnKind literals (`code`, `integer`, `date`, `timestamp`, `codes`, `decimal`, `money`, `text`). The viewer uses the member only for the order; the cell kind still comes from row values for the rc. Should the OpenAPI schema enumerate the RPT-R-02 kinds (post-rc, with moving the other reports to column metadata)?
- **L8-R-Q-2 (`difference` of a passing result).** `difference` is computed for every result with amounts, so a PASS answers `[{amount: "0.00", currency}]`, and it is None only for NOT_APPLICABLE. `TieOutResultOut.difference` is required and nullable, while `expected` and `actual` stay optional `Any`. The strip renders it only on failing rows (RV-05). Confirm, or rule that PASS answers null.

## Deviations and notes

- `frontend/src/routes/schedules/__tests__/schedules.test.tsx` (not in lane scope) fakes `/data` without `columns`. The page reader keeps `columns` as `[]` when the first page names none, and SF-04 does not read the member, so the suite passes unchanged.

## Shared files touched

- Generated, likely to conflict with any lane that runs `make openapi`: `docs/api/openapi.json`, `frontend/src/lib/api/schema.d.ts`.
- Outside the files the rulings name, as tests of the ruled output: `backend/tests/domain/reports/test_balances_reports.py`, `backend/tests/domain/reports/test_rpo_disaggregation.py`, and the new `backend/tests/unit/reports/test_tie_out_difference.py`.
- `frontend/src/routes/reports/report.tsx` (passes `columns` into `ColumnContext`), `frontend/src/lib/api/queries/reports.ts`, `frontend/src/routes/reports/viewer/useReportRun.ts` (named by the ruling; L7-3 files), `frontend/e2e/projects/screens.spec.ts` (one SF-08:report step).
- Ruled files: `backend/erev_api/domain/reports/framework.py`, `tie_outs.py`, `backend/erev_api/api/v1/reports.py`, `backend/erev_api/schemas/reports.py`, `backend/tests/api/test_report_runs.py`, `backend/tests/support/parity/probes.py`, `backend/tests/unit/parity/test_probe_support.py`, `backend/tests/domain/reports/test_legacy_reports.py`, `frontend/src/routes/reports/viewer/specs.ts`, `TieOutStrip.tsx`, `__tests__/viewer.test.tsx`.

# Batch 2 evidence

Batch 2 of lane L8-R, on `sprint/l1` after batch 1 (5128a56). Rulings: D-88 L7-3-Q-2 and L7-3-Q-22 as amended (the verifier's AMEND text over the drafter's ruling, `.run/supervisor/d88-raw.json`), and D-89 L7-3-Q-32 (the journal-runs.tsx half only).

## Commits

| Commit | Ruling |
|---|---|
| c772b91 | L7-3-Q-2: report runs, exports and reruns stay while a lock snapshot is shown (SF-08:report, SF-04) |
| 3faebd7 | L7-3-Q-22: the entries grids carry the range caption; the Legacy book banner answers only the T-REF-03 refusal |
| 0bcc3eb | L7-3-Q-32: the SF-06 Open run toast carries the calculation's entity, period and book |

## L7-3-Q-2 (SCR-ST-10 on report surfaces)

- `frontend/src/routes/reports/report.tsx`: `ParametersToolbar` gets no `readOnly`, and `RunDetailsDrawer` gets no `canRerun={snapshot === null}`. The RV-04 default is unchanged: a locked context period sets `snapshot`, and every run posts `period_lock_id` = the snapshot (`specs.runParameters`).
- `frontend/src/routes/schedules/schedules.tsx` (amendment 2): the same two gates are removed (`readOnly={layout === "waterfall" && snapshot !== null}` and `canRerun={snapshot === null}`).
- `viewer/ParametersToolbar.tsx` (amendment 3): no caller still passed `readOnly`, so the prop and its read-only `<dl>` branch are removed.
- `viewer/RunDetailsDrawer.tsx`: "Rerun from the same source" always renders. With both snapshot gates removed, every caller passed `canRerun` true (SF-06:entries passed a bare `canRerun`), so the prop is removed, and the `entries.tsx` call site is edited to match. The header comment gives the ruling's reason: a rerun reads the stored source.
- Tests:
  - `frontend/src/routes/reports/__tests__/viewer.test.tsx::as locked banner` now asserts, while `snapshot` = the lock:
    - "Run report" is present, and the Rows field is an editable combobox;
    - the first run posts `period_lock_id` = the lock (existing assertion);
    - "Run details" opens the drawer with "Rerun from the same source".

    The drawer is then closed, and the Show current figures flow is unchanged.
  - New `frontend/src/routes/schedules/__tests__/schedules.test.tsx::as locked keeps run report and rerun`. AVM-US FY2026-P08 is closed with a lock, and the test asserts:
    - the URL gains `snapshot` = the lock;
    - the waterfall run posts `period_lock_id`;
    - "Run report" is present, and the Rows field is editable;
    - the SF-04 drawer holds "Rerun from the same source".
- Counts: vitest `viewer.test.tsx` and `schedules.test.tsx`, 2 files, 17 passed.
- Gate note: no period lock exists in the rc world (CLO-6 and CLO-22 are post-rc), so the as-locked path is covered only by these unit tests. The SF-08:report and SF-04 e2e rows exercise the current-source path.

## L7-3-Q-22 (SF-06:entries scope)

- Accepted as built: Entities is a toolbar field, with the URL `entity` as the context; there are no RPT-13 drills and no RV-04.
- Amendment 1:
  - `frontend/src/components/data-grid/DataGrid.tsx`: `DataGridProps.describedBy` (additive, optional) is set as `aria-describedby` on the `role="grid"` element.
  - `viewer/ReportGrid.tsx`: `describedBy` is passed through.
  - `types.ts` is unchanged, because `DataGridProps` lives in `DataGrid.tsx`.
- Caption:
  - `entries.tsx` renders a visually hidden `<p class="sr-only">` per grid and passes its id (`useId` plus the section id).
  - The text comes from the new keys `journals.entries.caption.gross`, "{grid}, {from} to {to}, gross view", and `journals.entries.caption.adjustment`, "{grid}, {from} to {to}, adjustment view", in `frontend/src/messages/en.json`.
  - `{grid}` is the grid's catalogue name ("Journal lines by account", "Journal lines by entity", "Line items").
  - `{from}` and `{to}` are the posted range through `formatDate` (DS-FMT-16).
  - Each grid and its caption sit in one wrapper `div`, so the parent `gap-6` layout is unchanged.
- Amendment 2:
  - `legacyBookRefused(problem)` is true only when `problem.errors` holds a finding with `rule_id` `T-REF-03` on field `mode` or `parameters.mode`. That is the `journals/views.py` LEGACY_NOT_KEPT refusal, raised in the REPORT_RUN job, so it arrives as the failed run's `problem`.
  - The info banner "The adjustment view needs the Legacy book. Enable it for <codes> to see pre-standard revenue reversals." renders only for a failed Adjustment run with that finding.
  - Any other failed run shows SCR-ST-12 "Running Legacy journal summary failed. Nothing was committed." with the problem title and Retry.
- Tests (viewer.test.tsx):
  - 'by account totals from the run and the gross parameters' asserts the three descriptions. The ruled one is "Journal lines by account, 01 Aug 2026 to 31 Aug 2026, gross view"; the others are "Journal lines by entity, …" and "Line items, …".
  - New 'legacy book banner answers only the T-REF-03 mode refusal': a failed DELTA run with the finding on `mode`, then on `parameters.mode`, shows the info banner and no SCR-ST-12.
  - New 'another failed adjustment run shows the job failed banner': T-REF-03 on `entity_codes`, and a 500 problem without findings, each show SCR-ST-12 with the problem title and Retry, and no Legacy book banner.
- Counts: vitest `viewer.test.tsx` plus the four `components/data-grid/` suites, 6 files, 29 passed.

## L7-3-Q-32 (Open run toast context)

- `frontend/src/routes/journals/journal-runs.tsx`:
  - `Calculation` gains `periodKey: string` and `book: string`.
  - `submit` pushes `{ jobId, entity: code, periodKey, book, periodLabel }`.
  - "Open run" navigates to `runRoute(runId)` plus `withParams("", {entity, period, book})`, with each value URI-encoded as the other `replace` callers do, so the search is in SCR-URL-20 order and uses the calculation's own context.
- New `frontend/src/routes/journals/__tests__/journal-runs.test.tsx::open run keeps the run context`:
  - The page search is `entity=AVM-US&period=FY2026-P09&book=ASC606&f.state=is:draft`, so a link that reused the page search would fail.
  - The dialog adds AVM-DE to AVM-US, and Calculate posts one run per entity.
  - The AVM-US toast's "Open run" gives `/journals/runs/<run id>?entity=AVM-US&period=FY2026-P09&book=ASC606`.
  - The AVM-DE toast's gives `/journals/runs/<run id>?entity=AVM-DE&period=FY2026-P09&book=ASC606`.
- Not edited: `frontend/e2e/journeys/rc-smoke.journey.ts` (RC-SMOKE.7 hard assert and reopen workaround), which lane L8-J owns.
- Counts: vitest `journal-runs.test.tsx` and `run.test.tsx`, 2 files, 11 passed.

## Gates (batch 2)

`make lint` and `make typecheck` ran after each ruling, and all three runs were OK. The batch gates ran on 0bcc3eb, detached, with gate slots and bounded waits.

| Gate | Result |
|---|---|
| make lint | OK (after each ruling; the last run: design-check 275 files, 0 errors; vocab-check 699 files, 0 findings; licence-check 0 findings; secrets-check 0 findings) |
| make typecheck | OK (mypy strict, tsc; after each ruling) |
| make ci | OK: backend 2113 passed, 0 failed, 0 skipped; vitest 601 passed, 0 failed, 0 skipped. Batch 1 gave 2113 and 597. The +4 vitest are this batch's new tests: schedules 'as locked keeps run report and rerun', the two viewer banner tests, and journal-runs 'open run keeps the run context'. |
| make test-pg | OK: 290 passed, 0 failed, 0 skipped |
| make parity K="not point_in_time_equivalence" | OK: 121 selected; 121 passed, 0 failed, 0 skipped (contract_position A 29, C 21; cumulative_catchup A 1, C 9; initial_allocation A 14, C 2; journal_entry_totals A 10, B 5, C 9; legacy_probe A 1, B 3; pob_position B 1, C 16) |
| make e2e SPEC=frontend/e2e/projects/screens.spec.ts:2205,…:2536,…:2652 PROJECT=screens | OK: 7 passed, 0 failed, 0 flaky, 0 skipped. The SF-06 describe ran SF-06, SF-06:run, SF-06:run-lines, SF-06:run-batches and SF-06:entries (5); SF-08:report marcus (1); SF-04 marcus (1). |

Captures read in light and dark:
- `01-sf-08-report-revenue-waterfall`, `02-sf-08-report-legacy-contract-history-export`
- `03-sf-06`
- `07-sf-06-entries`
- `08-sf-04-quarter`, `09-sf-04-avm-us-quarter`

What they show:
- SF-08:report and SF-04 show the editable toolbar with "Run report", with Current source (the rc has no lock).
- SF-06:entries keeps the three grids at their previous spacing, and the caption text is not visible.
- No clipping or contrast defect appears in either theme.

Observed, not touched by this batch: the AVM-US revenue waterfall tie-out reads "0 pass, 1 fail" (Expected USD 544,403.37, Actual USD 2,930,798.39) on SF-08:report and on SF-04.

## Spec questions (batch 2)

- **L8-R-Q-3 (caption of an empty entries section).** A section with no rows and no totals renders the static `<section>` of `ReportGrid` without `role="grid"`, so the caption paragraph is rendered but nothing references it. Should that region carry `aria-describedby` too, or should an empty section omit the caption (post-rc)?
- **L8-R-Q-4 (SCR-ST-12 Reference on SF-06:entries).** SCR-ST-12 names "Reference <job id prefix>". SF-08:report shows it from the create job, while SF-06:entries shows the title and Retry only, as the L7-3-Q-22 amendment names. Should the entries banner add the Reference line?

## Deviations and notes (batch 2)

- `RunDetailsDrawer.canRerun` is removed. The ruling removes the snapshot gates, and after that every caller passed true, so the prop and the bare `canRerun` in `entries.tsx` go. Amendment 3 names this cleanup only for `ParametersToolbar.readOnly`; the drawer prop is removed for the same reason.
- `frontend/src/components/data-grid/types.ts` is unchanged, although amendment 1 names it: `DataGridProps` is declared in `DataGrid.tsx`.
- `viewer.test.tsx::as locked banner` now asserts the reverse of the RPS-6 clause "commands are hidden while `snapshot` is present", which amendment 4 reads as met. Any BUILD_SPEC wording change is the supervisor's.
- No e2e row covers the as-locked path, because the rc world has no period lock (CLO-6 and CLO-22 post-rc).

## Shared files touched (batch 2)

- Shared components and catalogues:
  - `frontend/src/components/data-grid/DataGrid.tsx` (additive optional prop);
  - `frontend/src/messages/en.json` (two keys, `journals.entries.caption.*`).
- SF-04, named by the Q-2 amendment: `frontend/src/routes/schedules/schedules.tsx` and `frontend/src/routes/schedules/__tests__/schedules.test.tsx`.
- Ruled files:
  - `frontend/src/routes/reports/report.tsx`, `viewer/ParametersToolbar.tsx`, `viewer/RunDetailsDrawer.tsx`, `viewer/ReportGrid.tsx`, `__tests__/viewer.test.tsx`;
  - `frontend/src/routes/journals/entries.tsx`, `journal-runs.tsx`, and the new `__tests__/journal-runs.test.tsx`.
- Not touched: `frontend/e2e/journeys/rc-smoke.journey.ts`, `frontend/e2e/projects/screens.spec.ts`, the OpenAPI document, PROGRESS.md and every other doc.
