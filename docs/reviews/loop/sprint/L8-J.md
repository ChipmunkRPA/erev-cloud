# L8-J lane evidence: smoke journey rewrite (SUP-RC-SMOKE)

Lane L8-J, worktree `~/dev/erev-wt/l3`, branch `sprint/l3`, batch 1 of 1 (Level 8 remediation after the L7 release gate). Rulings built: D-89 L7-3-Q-27, Q-28, Q-29 and Q-31, plus the journey halves of D-88 L7-3-Q-3 (RC-SMOKE.10) and D-89 L7-3-Q-32 (RC-SMOKE.7). The lane adds no Alembic revision.

Step 0: `git merge --ff-only main` fast-forwarded `sprint/l3` from 1a70ee8 to 0266227. `make setup` OK (`DB-14 lint: 0 findings`, `OK migrate`).

## Rulings and items

### D-89 L7-3-Q-28: RC-SMOKE.1 landing route and rail order are hard

- `frontend/e2e/journeys/rc-smoke.journey.ts`: `toHaveURL(/\/home(\?|$)/)` and the rail names are hard `expect` assertions. The rail order is Home, Contracts, Schedules, Close, Journals, Reports, Approvals, Policies, Data, Settings (DS-CMP-02; SCR-IA-01).
- The module header's note about soft assertions now reads "Every assertion is hard".

### D-89 L7-3-Q-27: RC-SMOKE.2 soft SSP summary removed

- Deleted: the soft assertion "SSP book version 2023-01-01 · 7 entries · method Legacy range" and its comment.
- Kept as hard checks: the Map columns caption "Not needed: legacy template headers matched", the h2 "Review changes", `SF-10-diff` visible, and the capture `rc-smoke-02-import-review`.
- RC-SMOKE.3 is unchanged: through the API, `LEGACY-SKU-SSP` version `2023-01-01` is `APPROVED` with `entry_count` 7 and seven `legacy_range` entries.

### D-89 L7-3-Q-29: RC-SMOKE.6 SF-04 with rows=obligation

- The step opens `/schedules?entity=AVM-US&period=FY2026-P09&book=ASC606&rows=obligation`. It waits for the opening run: `run=<uuid>` in the URL, `succeededRun`, then the grid "Revenue waterfall" visible. It hard-asserts `[?&]rows=obligation` in the URL.
- Removed: the toolbar Rows choice and the second `runReport`. `runReport` stays for RC-SMOKE.10.
- Kept: the column header "Sep 2026 (USD)", `a11y.check` SF-04, row `SF-04-row-sf-ord-10001-o1` and its button "Explain Sep 2026 (USD) · SF-ORD-10001 O1, USD 9,764.38".
- Added (E2E-02): `reportRows(page.request, runParam(page))` holds exactly one row with `row_key` `obligation:SF-ORD-10001:O1`. `amountOf(row['period:FY2026-P09'])` is the string '9764.38' (`expectDecimal`), and its `currency` is 'USD'.
- The D-89 unsettled note on which member carries the row values is closed by the passing run: the `items[]` rows of `GET /report-runs/{id}/data` carry the key `period:FY2026-P09` as an API-S-Money value.

### D-89 L7-3-Q-31: RC-SMOKE.8, RC-SMOKE.9 and the SF-06 export toasts

- RC-SMOKE.8:
  - Deleted: the soft chip Approved check.
  - Kept: the hard poll (`approved_at` set; state `approved` or `exported`) and the hard chip `/^(Approved|Exported)$/`.
  - The step title ends "the run is Approved or Exported".
- RC-SMOKE.9:
  - Deleted: the soft "Export journals" check.
  - Added: with chip Exported visible, SF-06:run renders no button named `/^(Export journals|Export to .+|Retry export)$/` (`toHaveCount(0)`; SCREENS_B §3.2 Exported has no primary action). This covers "Export journals" and the two other primary export labels of §3.2.
  - "Export again": `GET /journal-runs/{id}/batches` is read just before the command. Each batch becomes the tuple [`external_id`, `state`, `exported_at`, `detail_sha256`, `row_version`, `acknowledgements.length`] (`batchTuple`). After the toast "The export was already recorded. No batch was posted again.", a fresh read gives the same ordered tuples for every batch.
  - `JournalBatchRef` gains `exported_at`, `detail_sha256`, `row_version` and `acknowledgements`.
  - All other hard assertions stay: `exported`, adapter CSV, KPI "0 of <m>", grid "Batches", and the ZIP manifest checks.
- `frontend/src/routes/journals/__tests__/run.test.tsx` 'export toasts':
  - Fixture: an approved run JR-000209 with two batches. "Export journals" opens the alertdialog "Export journal run JR-000209 to …". "Export" posts `{adapter: "CSV"}` and gets 202 with `Location: /api/v1/jobs/<id>`; the job answers SUCCEEDED.
  - The refreshed run is `exported` with one batch acknowledged and one exported. The toast reads "Journal run JR-000209 exported. 1 of 2 batches acknowledged." (distinct counts, so swapped arguments would fail).
  - Then "Export journals" is gone. "More actions" › "Export again" › "Export" posts a second time, and the toast reads "The export was already recorded. No batch was posted again.". The posted bodies are `[{adapter: "CSV"}, {adapter: "CSV"}]`.

### D-89 L7-3-Q-32 (journey half, RC-SMOKE.7): first green at the merge gate

Lane L8-R's `journal-runs.tsx` fix is not on main, and no lane branch held it during this batch (`git log main..sprint/l1|l2|l5|l6` empty). As instructed, the reopen workaround stays: `page.goto('/journals/runs/<id>?entity=AVM-US&period=FY2026-P09&book=ASC606')` after "Open run", and its `[J]` comment names the fix. The ruled form cannot pass in this lane, and a failure at RC-SMOKE.7 would stop the serial journey before RC-SMOKE.8 to RC-SMOKE.10. Final form, once `journal-runs.tsx` is on main:

```ts
await page.getByRole("button", { name: "Open run", exact: true }).click();
await expect(page).toHaveURL(
  new RegExp(`/journals/runs/${UUID}\\?entity=AVM-US&period=FY2026-P09&book=ASC606(&|$)`),
);
runId = /\/journals\/runs\/([0-9a-f-]{36})/.exec(page.url())?.[1] ?? "";
// delete the [J] L7-3-Q-32 comment and `await page.goto(`/journals/runs/${runId}?${CONTEXT}`);`
```

### D-88 L7-3-Q-3 (journey half, RC-SMOKE.10): first green at the merge gate

The API `difference` member is lane L8-R's, and neither `backend/erev_api/schemas/reports.py` nor `schema.d.ts` carries it on main. RC-SMOKE.10 keeps its hard checks: the `TO_WATERFALL_EQ_JE_REVENUE` result present, Expected USD and Actual USD, and "Difference USD" when the result is FAIL. It is FAIL in this world (N-4). Final form, once the member is on main:

```ts
/** DS-FMT-01: a negative amount in parentheses. */
function moneyText(value: string): string {
  return value.startsWith("-") ? `(${groupedText(value.slice(1))})` : groupedText(value);
}
// ReportRunRef.tie_out_results members gain `difference: unknown`.
const differences = [tieOut?.difference].flat().filter(
  (value): value is { readonly amount: string; readonly currency: string } =>
    typeof value === "object" && value !== null && "amount" in value && "currency" in value,
);
expect(differences.length).toBeGreaterThan(0);
for (const money of differences) {
  expect(typeof money.amount).toBe("string");
  await expect(item).toContainText(`Difference ${money.currency} ${moneyText(money.amount)}`);
}
```

## Tests added or changed

| Module | Change | Result |
|---|---|---|
| `frontend/e2e/journeys/rc-smoke.journey.ts` | RC-SMOKE.1 two soft → hard; RC-SMOKE.2 one soft removed; RC-SMOKE.6 rows=obligation URL, Rows choice and second run removed, E2E-02 data row added (3 assertions); RC-SMOKE.8 one soft removed; RC-SMOKE.9 one soft replaced by a hard `toHaveCount(0)`, Export again tuples of 6 members per batch. `expect.soft` occurrences: 5 → 0 | 1 test (serial journey), passed |
| `frontend/src/routes/journals/__tests__/run.test.tsx` | 'export toasts' added | 11 passed (10 → 11) |

## Journey captures (light and dark)

Read from `frontend/e2e/.screens/rc-smoke.journey.ts/` after smoke run 1.
- `rc-smoke-02-import-review` (SCREENS §12.2): "Legacy v1: SKU SSP", Valid; stepper Upload · Map columns "Not needed: legacy template headers matched" · Validate "7 rows" · Review changes · Approval · Committed. Figures 0 0 0 0, "Affected records 0 changes", "No affected records / The dry run found nothing to change." (the L7-3-Q-27 rc deviation). Both themes match; nothing clips.
- `rc-smoke-06-schedules` (SCREENS §4.3): pill AVM-US · Sep 2026 Open · ASC 606. The KPI strip reads Transaction price 135,000.00, Billed 135,000.00, Recognized 35,077.81, Scheduled 99,922.19, Awaiting trigger 0.00, Contract liability 29,944.11 with Contract asset 0.00 and Unbilled receivable 0.00. The L6-4-Q-7 overlap seen at L7 is gone. The Revenue schedule (14 lines) ends at the bottom edge with Sep 2026 · O1 · Normal · Scheduled · 9,764.38. The docked Explain panel shows narrative, formula, inputs and steps. Its header line (the USD 9,764.38 title) is scrolled out of frame; the step asserts it before the capture.
- `rc-smoke-07-journal-run` (SCREENS_B §3.2): JR-000001 Calculated, AVM-US, ASC 606, Sep 2026, Gross; Debits and Credits 571,755.48, Difference 0.00 Balanced, Lines 2, Batches acknowledged 0 of 1; both balance checks 0.00 Balanced; primary "Submit for approval". No toast covers the figures.
- `rc-smoke-09-run-batches` (SCREENS_B §3.4): Exported, Approval APR-000435, secondary "Download batch files" and no primary export action; batch 1 · 1 USD Exported, 2 lines, 571,755.48 / 571,755.48, `erev:avenmoor:JR-000001:1:1`, CSV.
- `rc-smoke-10-waterfall` (SCREENS_B §5.2): toolbar, stamp "Revenue waterfall v1", Rows 104; "Tie-outs (0 pass, 1 fail)", Waterfall revenue equals revenue journal total, Expected USD 571,755.48, Actual USD 2,930,798.39, Difference USD 2,359,042.91 (N-4); the DS-CH-01 chart.
- `rc-smoke-10-rpo` (SCREENS_B §5.2): Time bands "12, 24 months", As of 30 Sep 2026, "Tie-outs (1 pass, 0 fail)" USD 4,259,001.61 both sides, and the band chart.

Observations for the supervisor (outside this lane's files; no journey assertion depends on them):
- `rc-smoke-10-waterfall` carries two identical toasts, "Report Revenue waterfall ran. 104 rows.", one for the opening run and one for "Run report". They cover the lower right of the chart (Nov and Dec 2026 bars) in both themes. `rc-smoke-10-rpo` carries one toast over the chart grid.
- SF-10:detail and SF-06:run render no context pill in the top bar (captures 02, 07 and 09), while SF-03:schedules and SF-08:report do. Captures 07 and 09 read entity, book and period from the record meta. Whether record screens hide the pill by design was not checked against SCREENS.
- The static tables "Affected records" (capture 02) and "Summary by account" (capture 07) end before the right edge of their card.

## Screens spec (`make e2e SPEC=frontend/e2e/projects/screens.spec.ts`)

52 passed, 0 failed, 0 flaky, 0 skipped (2.2 min; report `build_sha` 1216038, `worktree_dirty` false; log `.run/l8j/e2e-screens1.log`). No row fails, so there is no cause to report.

## Gates

| Gate | Result |
|---|---|
| Targeted | `vitest run src/routes/journals/__tests__/run.test.tsx`: 11 passed. prettier `--check` and eslint `--max-warnings 0` on both changed files: OK. `tsc -b frontend`: OK |
| `make lint` (log `.run/l8j/lint1.log`) | OK |
| `make typecheck` (log `.run/l8j/typecheck1.log`) | OK (mypy: no issues in 557 source files; tsc OK) |
| `make e2e SPEC=frontend/e2e/projects/avenmoor-serial.spec.ts`, smoke run 1 (log `.run/l8j/e2e-smoke1.log`; gate slot 1) | **1 passed, 0 failed, 0 flaky, 0 skipped (1.4 min), hard assertions only.** RC-SMOKE.1 to RC-SMOKE.10 and the DG-E2E-08 network step pass. Report `build_sha` 0266227 with `worktree_dirty` true. The dirty files were exactly the two changed files, committed unchanged as 1216038 right after the run |
| `make e2e SPEC=frontend/e2e/projects/screens.spec.ts` (log `.run/l8j/e2e-screens1.log`; gate slot 1) | 52 passed, 0 failed, 0 flaky, 0 skipped |
| `make ci` (log `.run/l8j/ci1.log`; gate slot 1) | OK: env, lint, typecheck, test and build pass; backend 2109 passed, vitest 596 passed (595 on main + 'export toasts'), 0 failed, 0 skipped. Report `build_sha` 1216038, `worktree_dirty` true (this untracked evidence file only) |
| `make test-pg` (log `.run/l8j/testpg1.log`; gate slot 1) | OK: 290 passed, 0 failed, 0 skipped |

Slot note: at the end of `make ci`, the directory `~/dev/erev-wt/logs/gate-slot-1`, which this lane had taken with owner "L8-J ci <pid>", was gone, although that ci PID was alive until the gate finished. This lane did not remove it. The lane took slot 1 again for `make test-pg`. When that gate exited, the slot's owner file already read "L8-C test-pg <pid>" (a live PID), so the lane left the directory alone. Slot 2 was held by lane L8-R (ci, then e2e) during both gates.

## Deviations

- RC-SMOKE.9 reads the batch tuples just before "Export again", not from the list read before the ZIP download. The download writes only the `journal_batch.download` audit event (`backend/erev_api/api/v1/journal_runs.py:450`), so both reads carry the same tuples, and the fresh read keeps the check tied to the command.
- RC-SMOKE.7 and RC-SMOKE.10 keep their pre-L8-R forms in this lane. The final forms above first go green at the merge gate, after lane L8-R's `journal-runs.tsx` fix and API `difference` member merge.

## Spec questions

- **L8-J-Q-1 (RC-SMOKE.8 chip).** The D-89 L7-3-Q-31 builder instruction keeps the hard chip `/^(Approved|Exported)$/`. The amended item text in the Spec amendment column reads "chip Approved, Running (caption "Exporting") or Exported (E-34; SMAP-07)". The journey follows the builder instruction. If SF-06:run loads while the JOURNAL_EXPORT job still runs, E-34 first shows Running "Exporting", and the web-first assertion keeps retrying until the chip becomes Approved or Exported. Confirm the regex, or widen it to the amended text.

## Shared files touched

None. Files changed: `frontend/e2e/journeys/rc-smoke.journey.ts`, `frontend/src/routes/journals/__tests__/run.test.tsx` and this evidence file.
