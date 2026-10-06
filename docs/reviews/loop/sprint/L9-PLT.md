# L9-PLT evidence: rc platform fixes from the G12 QA (D-90a)

Lane worktree `~/dev/erev-wt/l2`, branch `sprint/l2`, based on `5f303ad`. Rulings implemented:
D-90a QA-L9-7 (with L8-C-Q-2), D-90a QA-L9-5a and, as the optional item, D-90 L8-R-Q-4. No Alembic
revision was added. Main moved during the lane to `908a5fa` (`590709d`, `68301bd`, `908a5fa`: docs
only; `git log 5f303ad..main -- backend frontend` is empty). `590709d` narrowed the D-90a wording:
BLK-06 and BLK-15 are the reader-independent classes, BLK-03 still reads the permission-filtered
`GET /exceptions` count, and 04 rev 1.8 reads "not filtered by the reader's request visibility".
The code comments, tests and this record use the narrowed wording. The lane did not merge main, as
its rules require; the lane worktree's docs are the base copies, which already carry 04 rev 1.8 and
SCREENS_B rev 1.3.

## Commits

| Commit | Ruling | Files |
|---|---|---|
| `ef4837c` | D-90a QA-L9-7, L8-C-Q-2 | `backend/erev_api/domain/close/gates.py`; `backend/erev_api/domain/close/queries.py`; `backend/erev_api/schemas/close.py`; `backend/tests/api/test_cockpit.py`; `backend/tests/domain/close/test_gates.py`; `docs/api/openapi.json`; `frontend/src/lib/api/schema.d.ts`; `frontend/src/lib/api/queries/periods.ts`; `frontend/src/routes/close/cockpit.tsx`; `frontend/src/routes/close/__tests__/cockpit.test.tsx` |
| `b5c4f0d` | D-90a QA-L9-5a | `frontend/src/routes/approvals/request.tsx`; `frontend/src/routes/approvals/request.test.tsx`; `frontend/src/lib/api/queries/approvals.ts`; `frontend/src/lib/api/queries/journal-runs.ts`; `frontend/src/lib/i18n/t.ts`; `frontend/src/messages/en.json` |
| `7600b93` | D-90 L8-R-Q-4 | `frontend/src/routes/journals/entries.tsx`; `frontend/src/routes/reports/__tests__/viewer.test.tsx` |

`git diff --stat 5f303ad 7600b93`: 18 files, 819 insertions, 112 deletions. The evidence commit
follows.

## Adopted work

Two adoptions happened in this lane.

1. The first builder agent stopped during an API outage and left uncommitted QA-L9-7 work in 10
   files (the backend counts, the schema, the regenerated OpenAPI and TypeScript schema, the
   frontend subtraction and tests). Its `make setup` had finished at 16:44 (`.run/l9plt/setup.log`:
   migrate OK; DB-14 lint 0 findings; lane databases `erev_rv_l2_dev`, `erev_rv_l2_test` and
   `erev_rv_l2_e2e`). The second agent kept all of that work, narrowed the claims in comments and
   tests to BLK-06 and BLK-15, extended the pytest to three readers, reordered the vitest so it
   fails on the fetch rather than on a caption timeout, and made the three commits. It also recorded
   that the runner lane's `gate-slot-1` (owner PID 77831) was dead at the time; that observation is
   the second agent's and is not re-verifiable now.
2. The second agent died when its supervisor session ended, after its `make ci` and `make test-pg`
   had written complete logs (`.run/l9plt/make-ci.log`, rc 2; `.run/l9plt/make-test-pg.log`, rc 0)
   and while this evidence file was an untracked draft with the gates and captures marked pending.
   This session (the third agent) adopted the three commits and the draft, re-verified every claim
   of the draft against the tree and the `.run/l9plt/` logs, reran every gate on `7600b93`, and
   completed this record. No further code commit was needed (see "Review against the binding
   text").

## Review against the binding text (this session)

Read: D-90a QA-L9-7 and QA-L9-5a and D-90 L8-R-Q-4 in `docs/01-DECISIONS.md` (with the `590709d`
narrowing read from `main`), 04 §16.8 API-S-PeriodCockpit `pending_requests` (rev 1.8), SCREENS_B
§1.1 (rev 1.3) and the diffs of the three commits.

| Binding text | Where | Result |
|---|---|---|
| `pending_requests` `[{subject_type, count}]`, JUDGEMENT_RECORD then MANUAL_ADJUSTMENT, both always present | `gates.BLOCKER_REQUEST_TYPES` seeds both keys in that order; `PendingRequestCountOut(subject_type: ApprovalSubjectType, count: int)`; `queries.cockpit` emits the dict in order | met |
| PENDING requests of the entity, entity-only like `blockers.approvals_pending`, not filtered by book | `pending_request_counts` filters `status == PENDING` and `request_of_entity(scope.entity_id)`, the same predicate `blocker_counts` uses for `approvals_pending` (gates.py 491-495); no book predicate | met |
| Counts only; no ids or summaries; the reader's request visibility does not apply to these counts | the query groups by `subject_type` and returns counts; no API-R-09 clause | met |
| SF-05 subtracts the counts for BLK-06 and BLK-15 and no longer reads `GET /approvals` for blockers | `cockpit.tsx` `pendingRequestCount`; `periods.ts` `fetchBlockerCounts` reads only the BLK-03 exceptions count; no consumer of the removed `pendingJudgementRequests`/`pendingAdjustmentRequests` members remains (grep over `frontend/src` and `frontend/e2e`) | met |
| BLK-03 still reads the permission-filtered `GET /exceptions` count (a 403 reads as 0) | unchanged `countOf(EXCEPTIONS_PATH, …)`; docstrings, test names and this record say so | met; precision kept |
| Tests: a reader without approval permission and an approver see the same BLK-06 and BLK-15; exact member order | `test_cockpit_request_counts_reader_independent` (maya, priya `revenue_reviewer` holding `judgement.review`, robert `viewer` holding no approval permission; `auth/permissions.py` 206-220, 274); vitest "BLK-06 and BLK-15 do not depend on the reader" | met |
| `make openapi` | `docs/api/openapi.json` and `schema.d.ts` in `ef4837c`; rerun in this session with no drift | met |
| QA-L9-5a: money and money arrays through the format module; period amounts with the calendar label, raw key fallback, never a throw; records "<label> <value>" joined " · " to depth 2; empty records as the no-value mark; `id` and `*_ids` hidden; member labels from catalogue keys reusing SCREENS copy | `request.tsx` `formatMember`, `periodLabeller` (try/catch, disagreeing rows read raw), `RECORD_DEPTH = 2`, `HIDDEN_MEMBER`, `memberLabel` with `hasMessage`; 19 `approvals.diff.member.*` keys in `en.json` | met |
| QA-L9-5a tests: CONTRACT_ACTIVATION preview, IMPORT_COMMIT `diff_summary` with nested and empty members, a record-array before-state | the four tests listed below | met |
| L8-R-Q-4: "Reference <job id prefix>" as SF-08:report does, once the entries run hook exposes the create job id | `entries.tsx` 333 takes `create` from `useReportRun`; line 443 mirrors `report.tsx` 466 (`create.jobId.slice(0, 8)`) | met |

No gap was found, so no further code commit was made.

## D-90a QA-L9-7: reader-independent BLK-06 and BLK-15

`test_cockpit_request_counts_reader_independent` (`backend/tests/api/test_cockpit.py`):

- Before WLD-B, `pending_requests` is `[JUDGEMENT_RECORD 0, MANUAL_ADJUSTMENT 0]`, so both keys are
  present when nothing is pending.
- After WLD-B, the cockpit is read by three readers:
  - Maya, the preparer.
  - Priya, `revenue_reviewer`, who holds the approval permission `judgement.review`.
  - Robert, `viewer`, who holds no approval permission.
- Each body has exact member order: `[["subject_type", "count"]] * 2` and
  `[JUDGEMENT_RECORD 1, MANUAL_ADJUSTMENT 1]`.
- The BLK-06 and BLK-15 inputs are identical for all three readers:
  `(judgements_unreviewed, manual_adjustments_pending, pending_requests)`. The whole
  `period.blockers` object is also equal for Priya and Robert. `approvals_pending` is 3,
  `judgements_unreviewed` is 1, and BLK-06 is max(0, 1 − 1) = 0.
- API-R-09 list visibility is unchanged and does differ between readers.
  `GET /approvals?status=PENDING&entity=AVM-US&subject_type=JUDGEMENT_RECORD&count=true` answers 1
  for Maya and 0 for Robert.

Other test changes:

- `test_approvals_entity_counts_blockers` takes the BLK-06 and BLK-15 arithmetic from the cockpit
  `pending_requests`.
- `test_cockpit_blocker_counts[named|import-level]` asserts
  `list(pending_request_counts(...).items()) == [("JUDGEMENT_RECORD", 1), ("MANUAL_ADJUSTMENT", 1)]`.
- vitest `BLK-06 and BLK-15 do not depend on the reader` renders an approver and a viewer whose
  approvals list answers 0. It records every `GET /approvals` and requires that none carries
  `subject_type` JUDGEMENT_RECORD or MANUAL_ADJUSTMENT. Both readers read "Blockers (5)" with the
  same caption and no judgement or adjustment row.
- `blocker rows without unbuilt links` keeps "Blockers (11)" with the counts coming from the cockpit
  fixture.

Scope as claimed: BLK-06 and BLK-15 no longer depend on the reader's request visibility. BLK-03
still reads the permission-filtered `GET /exceptions` count, where a 403 reads as 0. It is not
claimed reader-independent.

## D-90a QA-L9-5a: generic field-diff formatting on SF-12:request

`frontend/src/routes/approvals/request.tsx` (`displayValue`, `fieldChanges`, `memberLabel`,
`periodLabeller`, `GenericFieldDiff`):

- Money:
  - API-S-Money objects and money arrays are formatted with `formatMoney(..., { variant: "inline" })`
    (DS-FMT-01, DS-FMT-05), for example "USD 146,000.00" with a no-break space.
  - An unregistered currency shows the no-value mark (L3-3-Q-26).
  - `fetchPreviewDocument` registers the document's currencies before the diff renders.
- Period amounts `{period_key, amount}` read "<period label> <amount>":
  - The label comes from `periodLabel` over `GET /periods`, scoped to the request's entity when it
    names one.
  - The query runs only when the document holds a period amount.
  - A key without a row, a row that cannot be labelled, or a key whose rows disagree reads as the
    raw key. `periodLabeller` catches the throws.
- Records:
  - Records read "<label> <value>" joined with " · " to depth 2. A deeper record shows the no-value
    mark.
  - An empty record, or a record whose members are all hidden, shows the no-value mark.
  - Record arrays read one record per line at the top level (`whitespace-pre-line`); nested record
    arrays are joined with "; ".
  - API-S-Ref `{id, code, name}` reads its code, and `account_role` values read the `accountRole.*`
    catalogue labels.
- Hidden members:
  - `id`, `*_id`, `*_ids` and `object_type` are hidden.
  - `*external_id` business keys stay visible. The first run of the IMPORT_COMMIT test showed the
    `*_id` rule hiding `contract_external_id`.
- Member labels:
  - `approvals.diff.member.*` catalogue keys reuse SCREENS copy: "RPO", "Transaction price",
    "Revenue by period", "Journal lines", "Contracts affected", "Contracts created",
    "Allocation changes", "Revenue change by period", "Journal preview", "Account role", "Debit",
    "Credit", "Contract", "Obligation", "Before", "After", "Import", "GL account", "Status"
    (19 keys).
  - Other members keep sentence case. `hasMessage` was added to `lib/i18n/t.ts`.
- The skeptic correction to consolidate currency registration: `ensureCurrencyCodes` now lives once
  in `queries/approvals.ts`. `ensureCurrencies` delegates to it, and `queries/journal-runs.ts`
  re-exports it, so the consolidation needed no change in `queries/periods.ts` or
  `queries/reports.ts`.

Tests (`frontend/src/routes/approvals/request.test.tsx`; the existing WEB-15 assertions are
unchanged):

- `the generic field diff formats money, period amounts and member labels (D-90a QA-L9-5a)`, on a
  CONTRACT_ACTIVATION preview shaped like `contracts/activation.py` `_preview`:
  - Exact `fieldChanges` values, including "RPO" "USD 146,000.00".
  - "Sep 2026 USD 12,166.67\nFY2026-P10 USD 12,166.67" (the key without a calendar row stays raw).
  - The journal line "GL account 2300 · Account role Contract liability · Debit USD 0.00 · Credit
    USD 12,166.67".
  - No `{`, `}` or `"` in any value.
  - A money array, an unregistered currency, and unlabelled or unknown period keys.
- `an IMPORT_COMMIT diff_summary shows nested members to depth 2 and empty members as no value` (the
  RC-SMOKE.3 shape):
  - Nested allocation changes, revenue deltas with the calendar label, `journal_preview []` and
    `balances {}` as "—".
  - An empty `diff_summary {}` as no value, and the depth guard "Outer Inner —".
- `a record-array before-state shows one record per line and hides id and *_ids members`
  (ROLE_ASSIGNMENT `assignments[]` with `entity_ids`).
- `SF-12:request shows a CONTRACT_ACTIVATION preview formatted, without raw JSON`, rendered with the
  msw preview, currencies and periods reads:
  - Row "RPO" and row "Transaction price" contain "USD 146,000.00".
  - Row "Revenue by period" contains "Sep 2026 USD 12,166.67".
  - No row "Rpo", and no `{`, `}` or `"` in the diff.

## D-90 L8-R-Q-4: Reference line on SF-06:entries

Verified first: `entries.tsx` takes `create` from the same `useReportRun` hook that SF-08:report uses
for its Reference line (`report.tsx` 466). `create.jobId` is the 202 job of `POST /report-runs`. The
failed-run banner now adds `common.job.reference` with the first 8 characters of the job id.

Tests (`frontend/src/routes/reports/__tests__/viewer.test.tsx`):

- `a failed run the page created names its job reference`: "Reference 8e7d6c5b." (the test's
  `JOB_ID` is `8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b`), with 1 POST.
- `another failed adjustment run shows the job failed banner`: a run opened from the URL shows no
  Reference line.

## Fail-first proofs

Each proof ran the lane's final test files against the base code `5f303ad`. The overlay was
`git archive HEAD backend frontend` into `.run/l9plt/ff-base`, taken before the first commit, with
symlinks to `.env`, `docs` and `node_modules`. The overlay was removed before `make ci` (no
`.run/l9plt/ff-base*` directory exists). Logs are in `.run/l9plt/`; this session re-read every log
and the counts below are the logs' own summary lines.

| Item | Command | Base code result | Lane code result |
|---|---|---|---|
| QA-L9-7 pytest | `EREV_ENV=test PYTHONPATH=.run/l9plt/ff-base/backend pytest backend/tests/api/test_cockpit.py backend/tests/domain/close/test_gates.py` (overlay; `erev_api.__file__` checked to be the overlay) | 4 failed, 11 passed (`failfirst-pytest-qa-l9-7.log`): `KeyError: 'pending_requests'` (`test_approvals_entity_counts_blockers`, `test_cockpit_request_counts_reader_independent`); `AttributeError ... no attribute 'pending_request_counts'` (`test_cockpit_blocker_counts[named]`, `[import-level]`) | 15 passed (`pytest-qa-l9-7.log`; 15 passed again in `pytest-targeted-2.log`) |
| QA-L9-7 vitest | `vitest --run src/routes/close/__tests__/cockpit.test.tsx` | 2 failed, 3 passed (`failfirst-vitest-cockpit.log`): `BLK-06 and BLK-15 do not depend on the reader` "expected [ …(2) ] to deeply equal []" (two `GET /approvals` blocker reads); `blocker rows without unbuilt links` (no "Blockers (11)") | 5 passed |
| QA-L9-5a vitest | `vitest --run src/routes/approvals/request.test.tsx` | 4 failed, 11 passed (`failfirst-vitest-request.log`: `periodLabeller is not a function` in two tests). A scratch variant with a raw-key `periodLabeller` stub in the overlay copy also gave 4 failed, 11 passed, on content (`failfirst-vitest-request-stub.log`): proposed `{"amount":"146000.00","currency":"USD"}`, field "Rpo", field "Import no", `diff_summary` as raw JSON, assignments as raw JSON, and no row header "RPO" in the render | 15 passed |
| L8-R-Q-4 vitest | `vitest --run src/routes/reports/__tests__/viewer.test.tsx` | 1 failed, 14 passed (`failfirst-vitest-viewer.log`): "Unable to find an element with the text: Reference 8e7d6c5b." | 15 passed |

## Spec questions

- **L9-PLT-Q-1 (XR-06 copy keys).** The generic body adds `approvals.diff.member.*` catalogue keys.
  Their values are SCREENS copy (§2 "RPO" and "Revenue by period"; §4 "Transaction price"; §4.4
  "Journal lines"; §12.2 step 4 "Contracts affected", "Contracts created", "Allocation changes",
  "Revenue change by period", "Journal preview", "Account role", "Debit", "Credit", "Contract",
  "Obligation", "Before", "After"). SCREENS §15.8 does not list the keys. Ratify, or amend §15.8.
- **L9-PLT-Q-2 (generic body shapes the D-90a text leaves open).**
  - Record arrays read one per line at the top level and "; " when nested.
  - A record nested deeper than depth 2 shows "—".
  - API-S-Ref reads its code, and `account_role` reads the `accountRole.*` label.
  - `*_id` hiding is kept from WEB-15 alongside `*_ids`, while `*external_id` stays visible.
  - IMPORT_COMMIT `diff_summary` amounts are plain decimal strings without a currency
    (`imports/diff.py` `_amount`), so they show as the API string. DS-FMT-03 needs the currency's
    minor unit.
  - Status literals (`DRAFT`, `ACTIVE`) and ISO dates stay raw.
  - Ratify for the rc, or rule otherwise.
- **L9-PLT-Q-3 (period label source).** A request that names an entity reads `GET /periods?entity=`.
  A tenant-wide request, such as IMPORT_COMMIT, reads the first page of `GET /periods`, at most 200
  rows (`STRUCTURE_LIMIT`). A key outside that page, or a key whose rows disagree across calendars,
  reads as the raw key. Accept for the rc, or specify a calendar-period read post-rc.
- **L9-PLT-Q-4 (`make ci` red on a base defect outside the lane).** `make ci` fails on
  `backend/tests/unit/answer_keys/test_runner_engine.py::test_d85_key_implied_price_change_settlement`
  (run note reads `REFUND_LIABILITY cr 33.34`, the test expects `cr 100.00`). The failure is
  identical on a pure overlay of the base `5f303ad` (`.run/l9plt/pytest-d85-base-2.log`;
  `erev_api` imported from the overlay), so it is not caused by this lane; `main` has only docs
  commits since the base and carries the same failure. The runner lane fixes it: `sprint/l5`
  `9df7678` ("test_d85 expects the per-obligation REFUND_LIABILITY credits of the regenerated key …
  cr 33.34"). This lane did not touch the runner files. Merge order or a rerun of `make ci` after
  `sprint/l5` lands is the supervisor's call.

## Deviations and notes

- Test world: `wld_b` (`backend/tests/support/close_world.py`) seeds approval requests without
  approval steps (no `approval_step` rows). The second agent measured that Priya, holding the step
  permission, therefore lists 0 of them under API-R-09; the committed pytest does not assert Priya's
  list count. The list visibility contrast in the pytest uses the preparer (1) against the viewer
  (0). Priya is still one of the three readers with identical cockpit inputs.
- `ensureCurrencyCodes` in `queries/approvals.ts` reads `GET /currencies` with `limit` 200. The
  approvals list registration used `LIST_PAGE_SIZE` before.
- Out of lane: the second agent noted an independent review finding on runner commit `faf425a`
  (CONCESSION source grammar in `backend/tests/support/answer_keys/runners.py`). `faf425a` is a
  `sprint/l5` commit, superseded there by `6511ce3`; nothing was changed here. The review file it
  cited lives outside the repository and was not read by this session.
- Records: this lane fixes QA-L9-7 for BLK-06 and BLK-15, QA-L9-5a (generic formatting) and
  L8-R-Q-4. QA-L9-5b (the specialised CONTRACT_ACTIVATION view) remains unbuilt and deferred post-rc.
- The e2e report (`.run/reports/e2e/report.json`) was produced with this evidence file untracked in
  the worktree; the three code commits were the only tracked changes (`git status --short` showed
  only `?? docs/reviews/loop/sprint/L9-PLT.md` before and after every gate).

## Shared files touched

`docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` (`PendingRequestCountOut`,
`PeriodCockpitOut.pending_requests`); `frontend/src/messages/en.json` (`approvals.diff.member.*`);
`frontend/src/lib/api/queries/journal-runs.ts` (re-export).

## Gates

All measured on `7600b93` by this session on 2026-09-18 (logs under `.run/l9plt/`, suffix `-2`).
The second agent's 2026-09-17 runs on the same tree (`make-lint.log`, `make-typecheck.log`,
`make-ci.log`, `make-test-pg.log`, `vitest-full.log`, `make-build.log`) gave the same outcomes and
are superseded by the rows below. Gate slots: `make test-pg`, `make ci` and `make e2e` each ran
under `~/dev/erev-wt/logs/gate-slot-1` (owner file `L9-PLT <gate> <pid>`), taken by atomic `mkdir`
and removed after the gate exited; lane L9-ENG held `gate-slot-2` with its `make ci` during the ci
and e2e runs. No `.ruff_cache` or `.mypy_cache` existed at the worktree root before or after the
gates. No PostgreSQL "out of shared memory", `max_locks_per_transaction` or connect error occurred
(0 matches in every log), so no stage was rerun.

| Gate | Command | Result | Log |
|---|---|---|---|
| Targeted pytest | `EREV_ENV=test HYPOTHESIS_PROFILE=ci pytest backend/tests/api/test_cockpit.py backend/tests/domain/close/test_gates.py` | 15 passed in 28.26s | `pytest-targeted-2.log` |
| Targeted vitest | `vitest --run --root frontend src/routes/close/__tests__/cockpit.test.tsx src/routes/approvals/request.test.tsx src/routes/reports/__tests__/viewer.test.tsx` | 3 files, 35 passed (cockpit 5, request 15, viewer 15) | `vitest-targeted-2.log` |
| `make lint` | | OK lint (ruff, prettier, eslint, design/vocab/licence/secrets checks, `openapi_check.sh`, registry-seed and fixtures checks, 175 tagged control tests of 2506 collected, one alembic head) | `make-lint-2.log` |
| `make typecheck` | | OK typecheck; "Success: no issues found in 558 source files" | `make-typecheck-2.log` |
| `make openapi` | followed by `git status --porcelain -- docs/api/openapi.json frontend/src/lib/api/schema.d.ts` | OK openapi; the status output is empty (0 bytes), so the committed document and schema have no drift | `make-openapi-2.log`, `openapi-drift-2.txt`, `openapi-2.head` |
| `make test-pg` (slot 1) | | 290 passed, 0 failed, 0 skipped in 52.41s; "test-pg counts: backend 290 passed, 0 failed, 0 skipped"; OK test-pg | `make-test-pg-2.log` |
| `make ci` (slot 1) | | stages env, lint, typecheck OK; stage test: "ci counts: backend 2143 passed, 1 failed, 0 skipped" in 2210.12s (0:36:50); FAIL ci, exit 2. The one failure is `test_d85_key_implied_price_change_settlement` (L9-PLT-Q-4; pre-existing on the base). The failing pytest step stops `make test` before its vitest step and `make ci` before its build stage | `make-ci-2.log` |
| ci stages the failure skipped, run directly | `npm --prefix frontend run test -- --run` (full vitest); `make build` | vitest 94 files, 608 passed; OK build | `vitest-full-2.log`, `make-build-2.log` |
| D-85 base check | single test on a `git archive 5f303ad backend` overlay with `PYTHONPATH` on the overlay (`erev_api` from `.run/l9plt/ff-base3/backend`); overlay removed afterwards | 1 failed, 35 deselected: the same `cr 33.34` vs `cr 100.00` assertion | `pytest-d85-base-2.log` |
| `make e2e` (slot 1) | `make e2e PROJECT=screens SPEC="frontend/e2e/projects/screens.spec.ts:2067,…:394,…:413,…:442,…:461,…:481,…:2412"` | "e2e counts: 7 passed, 0 failed, 0 flaky, 0 skipped; projects without tests: none"; OK e2e; `report.json` `build_sha` 7600b93, exit 0 | `make-e2e-2.log`, `.run/reports/e2e/report.json` |

e2e lines and durations: 2067 "SF-05 cockpit maya" 5.9s; 394 "SF-12 empty inbox as tomas" 2.2s;
413 "SF-12:submitted seeded list as maya" 3.3s; 442 "SF-12:submitted empty as priya" 2.1s;
461 "SF-12:all with the deal desk analyst role change selected" 2.4s; 481 "SF-12:request of the deal
desk analyst role change" 28.6s; 2412 "SF-06:entries maya" 8.7s. Each ran as its own
`--workers=2` Playwright invocation; the SF-06 `beforeAll` created the AVM-US FY2026-P08 run.

## Captures read

All 14 files under `frontend/e2e/.screens/screens/` (gitignored), written 2026-09-18 10:08-10:09,
were opened and read in both themes.

| Capture | Light and dark | What is shown |
|---|---|---|
| `01-sf-05-open` | both read | Maya's SF-05 for AVM-US · Sep 2026 · ASC 606: KPI "Blockers 23"; "Blockers (23)" table with Pending approvals 2, Exceptions 2, Holds 2, Contracts changed since the last close run 14, Journal run not calculated 1, Reconciliations not generated 2 (sum 23). The checklist gate "Judgements reviewed" shows count 1 while no "Judgements not reviewed" blocker row is listed: BLK-06 = 1 − 1 pending JUDGEMENT_RECORD = 0, hidden as a zero row. "Manual adjustments cleared" Passed, count 0. Dark theme renders the same content. |
| `12-sf-12` | both read | Tomas: "Waiting for me 0", "No requests waiting for you", detail pane "Select a request to review its changes, impact and routing." |
| `13-sf-12-submitted` | both read | Maya: "Submitted by me", "417 requests · newest first", Import commit IMP-000002 and Review JDG-000196 … JDG-000189 judgement records, all Approved. |
| `14-sf-12-submitted-empty` | both read | Priya: "Waiting for me 2", "You have not submitted any requests." |
| `15-sf-12-all` | both read | Grace: "All requests", "16 requests · newest first", the role change "Add the custom role Deal desk analyst" selected; detail "Role change · Approved", "Approval · 1 of 1 recorded", "No impact on revenue or balances.", "Proposed changes (2)": "Is active" No → —, "Permissions" — → scenario.use. The request number is masked magenta (`data-volatile`). |
| `16-sf-12-request` | both read | The same master-detail state as `15-sf-12-all` (the request route with the same request selected). The dark files of 15 and 16 are byte-identical and the light files differ by one byte; both surfaces render the same deterministic page, which explains the sizes. The diff table shows the generic field diff of a ROLE_CHANGE with no raw JSON. |
| `17-sf-06-entries` | both read | Maya's "Journals · Entries by date range", AVM-US, 01 Aug 2026 to 31 Aug 2026, Gross: run stamp "Legacy journal summary v1", Rows 187, Engine 0.1.0, Run and Output SHA-256 masked; "Journal lines by account" 2100 Dr 547,053.23 / 4010 Cr 547,053.23, Total 0.00 net; "Journal lines by entity" AVM-US balanced Yes; "Line items 184 rows"; toast "Report Legacy journal summary ran. 187 rows." The run succeeded, so no failed-run banner and no Reference line appears; that line is covered by the vitest above. |

The captures show no raw JSON, no clipped text and no theme-specific rendering fault.

## Batch 2

Batch 2 of the lane: the platform job reference is bound to the displayed run. Base: `08d72b7` merged with
`main` at `198491c` as `ef985d6` (docs only: 11 files changed, 104 insertions(+), 30 deletions(-); `git diff 7600b93 ef985d6 --stat -- frontend`
is empty, so the frontend of `ef985d6` is the batch-1 code). Code commit `14100e7`. The evidence commit
follows. No Alembic revision, no OpenAPI change, no backend change.

### Finding

Supervisor workflow `erev-l9-asc606-review-verify`, finding `plt-job-reference` (record
`~/dev/erev/.run/l9/asc606-verify.json`; digest `~/dev/erev/.run/l9/asc606-verify-digest.md`, section
`plt-job-reference`, both skeptics' corrections applied):

- `useReportRun` kept `create.jobId` (the job of the run the mounted view created) for the life of the
  mount, while `runId` follows the URL. `entries.tsx` (D-90 L8-R-Q-4, `7600b93`) and `report.tsx`
  (pre-existing on `main`; `useReportRun.ts` and `report.tsx` were identical on `main` and the lane)
  rendered SCR-ST-12 "Reference <job id prefix>" from `create.jobId` whenever the displayed run was
  `FAILED`. A same-mounted navigation from created run A to a stored failed run B therefore showed A's
  job on B.
- Binding text: SCREENS.md:377 SCR-ST-12 ("Job `FAILED` for a command started on the screen … 'Reference
  <job id prefix>'"), SCREENS.md:318 SCR-URL-16, SCREENS_B.md:198 RV-01 and :211 RV-14 (lane copy after
  the merge), DESIGN_SYSTEM.md:1290 DS-CMP-24 ("failed (negative banner with the job id and Retry)"),
  01-DECISIONS.md:592 D-90 L8-R-Q-4. A stored run B was not started on the screen, so no job of B may be
  named from A's pair.
- Latent, as the skeptics corrected: no shipped UI affordance changes `run` on a mounted SF-08:report or
  SF-06:entries today (the catalogue recent-runs link crosses a route boundary, NTF-05 carries no
  `link_path`, in-view navigations are `replace: true`); any same-route `run` navigation while mounted (a
  supported router operation, and the likely path of the specified-but-unbuilt SF-08:run list) produces
  it. Fixed before the merge as RC hardening of a shared hook's state model.

### Fix (`14100e7`)

- `useReportRun.ts`: `created` state `{runId, jobId} | null` (line 80); set from the 202
  (`X-Erev-Report-Run-Id` header, `Location` job id via `outcome.jobId`) in `start` (line 95);
  cleared on a context change (line 112) and in `restart` (line 184) without
  touching the stored run; `createdJobId = created.runId === runId ? created.jobId : null` (line
  179); returned additively (line 188). `create`, `pendingJob`, `computing`
  and `restart` are unchanged.
- `entries.tsx` line 333 destructures `createdJobId`; the SCR-ST-12 line at 443 renders
  from it. `report.tsx` line 313 and 468 likewise (prettier reflowed the wrapped
  destructure). No `create.jobId` use remains under `frontend/src` outside tests.
- Third consumer `schedules/schedules.tsx` destructures a subset of the hook's return and is unaffected
  (its 5 tests pass below).
- `created.runId` is the raw header value and `runId` the URL-decoded `run`; equal for the T-RPT-02 uuids.

### Tests (`viewer.test.tsx`, describe at line 1127; six new, 15 existing unchanged)

The SF-06:entries suite lives in `viewer.test.tsx` since batch 1 (`LEGACY_JE` fixtures), so the new
block sits there and covers both screens; `journals/__tests__/journal-runs.test.tsx` covers SF-06 "Run
journals", not entries, and was run as the adjacent suite. Each test renders without `run=` so the view
creates A (one POST; msw answers 202 with `Location /api/v1/jobs/8e7d6c5b-…` and
`X-Erev-Report-Run-Id` A), serves A, B and C as `FAILED` with distinct problem titles, and drives the
same-mounted navigation with `router.navigate`:

| Test | Asserts |
|---|---|
| SF-06:entries A to B / SF-08:report A to B | "Reference 8e7d6c5b." and A's title on A, URL `run=A`, 1 POST; after `run=B`: B's title, A's title gone, still 1 POST, no `/^Reference /` text |
| SF-06:entries A to B to A / SF-08:report A to B to A | no reference on B; back on `run=A` the reference "Reference 8e7d6c5b." is shown again; 1 POST in total |
| SF-06:entries Retry from stored failed B / SF-08:report Retry from stored failed B | `servePairs` (line 1204) answers each POST with its own (run, job) pair; after Retry on B the run the retry created (the API names it C) shows "Reference c0ffee11.", A's reference is absent, 2 POSTs, URL `run=C` |

As built, Retry on a stored failed run creates a new run through `POST /report-runs`, and the pair binds
to that run: the API assigns the run id, so the reference is the new job's and never A's or a stale one.

### Fail-first proof

Overlay `.run/l9plt2/ff-base` = `git archive ef985d6 frontend` (batch-1 frontend, checked: the overlay
`useReportRun.ts` equals `HEAD`'s and `entries.tsx` equals `7600b93`'s by `cmp`), `frontend/node_modules`
a symlink to the lane's, vite cache mode `l9plt2ff`; the final `viewer.test.tsx` copied in (`cmp` equal).
Run: `vitest run src/routes/reports/__tests__/viewer.test.tsx` inside the overlay.

| Code | Result | Log |
|---|---|---|
| batch-1 (`ef985d6` frontend) | 6 failed, 15 passed (21); all six fail at the B assertion `expect(screen.queryByText(/^Reference /)).toBeNull()` with "Received: <p>Reference 8e7d6c5b.</p>" (6 occurrences) | `.run/l9plt2/ff-before-2.log` (first run, before the eslint fix of the test helper's typing, `ff-before.log`: same 6 failed, 15 passed) |
| lane (`14100e7`) | 21 passed | `.run/l9plt2/vitest-viewer-verbose.log` |

The overlay was removed after the run (no `.run/l9plt2/ff-base` exists).

### Measured counts (all on `14100e7`, 2026-09-18, logs under `.run/l9plt2/`)

| Gate | Command | Result | Log |
|---|---|---|---|
| Touched vitest | `vitest run --reporter=verbose src/routes/reports/__tests__/viewer.test.tsx src/routes/schedules/__tests__/schedules.test.tsx src/routes/journals/__tests__/journal-runs.test.tsx` | 3 files, 27 passed (viewer 21, schedules 5, journal-runs 1), 0 failed | `vitest-touched-verbose.log` (`vitest-touched-2.log`: 27 passed) |
| eslint, prettier on the 4 touched files | `eslint --config frontend/eslint.config.js --max-warnings 0 …`; `prettier --check …` | 0 problems; "All matched files use Prettier code style!" (a first eslint pass flagged one `no-non-null-assertion` in the test helper, fixed by typing `pairs` as a non-empty tuple, `eslint-touched.log`) | `eslint-touched-2.log`, `prettier-check-2.log` |
| `make lint` | | OK lint: prettier and eslint clean; design-check 275 files 0 errors; vocab-check 700 files 0 findings; licence-check 0 findings; secrets-check 2726 files 0 findings; openapi current; registry-seed current; fixtures 18 verified; control markers valid, 175 tagged tests of 2506 collected; one alembic head | `make-lint.log` |
| `make typecheck` | | OK typecheck: mypy "Success: no issues found in 558 source files"; the `tsc -b frontend` step printed nothing (it is the type gate; "OK typecheck" prints only after both steps) | `make-typecheck.log` |
| `make e2e` (gate-slot-1) | `make e2e PROJECT=screens SPEC="frontend/e2e/projects/screens.spec.ts:2536,frontend/e2e/projects/screens.spec.ts:2412"` | "e2e counts: 2 passed, 0 failed, 0 flaky, 0 skipped; projects without tests: none"; OK e2e; 2536 "SF-08:report marcus" 28.7s, 2412 "SF-06:entries maya" 4.8s, each its own `--workers=2` invocation; `report.json` `build_sha` `14100e7a8243…`, `worktree_dirty` false, `exit_code` 0 | `make-e2e.log`, `.run/reports/e2e/report.json` |

Gate slot: `~/dev/erev-wt/logs/gate-slot-1` taken by atomic `mkdir` (both slots were free), owner file
"L9-PLT e2e 60471", removed after the gate exited; `make lint` and `make typecheck` ran detached at the
same time without a slot. 0 matches for "out of shared memory", `max_locks_per_transaction` or a connect
error in the three logs, so no stage was rerun. No `.ruff_cache` or `.mypy_cache` at the worktree root
before or after; `git status --porcelain` empty after the gates (`make ci` is not required in this batch).

### Captures read (`frontend/e2e/.screens/screens/`, written 10:53, light and dark)

| Capture | What is shown |
|---|---|
| `18-sf-08-report-revenue-waterfall` | Marcus, AVM-US · Sep 2026 · ASC 606: "Revenue waterfall", From Jan 2026 To Dec 2026, Rows Contract, Month, Total, Currency view Transaction; run stamp "Revenue waterfall v1", Run and Run at and Output SHA-256 masked magenta, As of 30 Sep 2026, Source "Current, known at 18 Sep 2026 17:52 UTC", Engine 0.1.0, Run by Marcus Webb, Rows 104; "Tie-outs (0 pass, 1 fail)" Difference chip, Expected USD 0.00, Actual USD 2,930,936.47, Difference USD 2,930,936.47 (seeded-world figures; the spec asserts the heading pattern only); chart "Revenue by period · USD · ASC 606" Recognized/Scheduled/Awaiting trigger with the Open marker; toast "Report Revenue waterfall ran. 104 rows." Dark renders the same content with the dark palette. |
| `19-sf-08-report-legacy-contract-history-export` | Marcus: "Legacy contract history export", Effective from 01 Jan 2026 to 30 Aug 2026, Contract SF-ORD-10001; stamp Rows 12; 12-row grid (Contract Unique Name, POB Unique ID, SKU Name, POB Start/End Date, ASC 606 Stratification, …); toast "… ran. 12 rows." Both themes. |
| `17-sf-06-entries` | Maya, AVM-US · Aug 2026 · ASC 606: "Journals · Entries by date range", Entities AVM-US, 01 Aug 2026 to 31 Aug 2026, Gross; stamp "Legacy journal summary v1", Rows 187, Engine 0.1.0, Run by Maya Chen, Source "Current, known at 18 Sep 2026 17:53 UTC"; "Journal lines by account" 2100 Dr 547,053.23 / 4010 Cr 547,053.23, Total 0.00 net; "Journal lines by entity" AVM-US Balanced Yes; "Line items 184 rows"; toast "Report Legacy journal summary ran. 187 rows." Both themes. |

Both runs succeeded, so neither capture shows the failed-run banner or a Reference line; the Reference
binding is covered by the vitest above. No raw JSON, clipped text or theme-specific fault was seen.

### Accepted RC deviation (recorded explicitly)

A stored failed run rendered from `run=` (SCR-URL-16, RV-01), including one opened by a `run` navigation
in the same mounted view, shows SCR-ST-12 without a "Reference <job id prefix>" line. This deviates from a
literal reading of RV-14 + DS-CMP-24 ("negative banner with the job id and Retry"), because
API-S-ReportRun does not expose the run's job id: `report_run.job_id` exists in the table
(`backend/erev_api/db/tables/reports.py:73`) but `ReportRunOut` (`frontend/src/lib/api/schema.d.ts`
14598-14644) has no such member, so the view knows only the job of the run it created. Accepted for the
rc as the SCR-ST-12 reading ("a command started on the screen"); exposing `report_run.job_id` through
API-S-ReportRun (OpenAPI + backend + frontend) so a stored failed run names its own job is the post-rc
item (L9-PLT-Q-5).

### Not changed (adjacent)

`create.problem` (a failed `POST /report-runs`, 4xx/5xx) is not bound to a run either and persists across
a later `run=` navigation in the same mounted view until `restart()`: `report.tsx` line
639, `entries.tsx` line 613. Same latent shape, out of this finding's scope;
flagged as L9-PLT-Q-6.

### Spec questions

- **L9-PLT-Q-5 (stored run job reference).** Ratify for the rc: a stored failed run shows no Reference
  line (SCR-ST-12 as written); post-rc, expose `report_run.job_id` in API-S-ReportRun and render it for
  stored runs so RV-14 + DS-CMP-24 read literally. Supervisor's call on the post-rc item's owner.
- **L9-PLT-Q-6 (`create.problem` across `run=`).** Fold the same (run, problem) binding into the hook in
  a later lane commit, or log as post-rc P3. Not done here.
- **L9-PLT-Q-7 (Retry semantics wording).** The batch text reads "Retry from stored failed B binds the
  new job to B". As built and as tested, Retry issues `POST /report-runs`, which creates a new run; the
  pair binds to the run the API names in `X-Erev-Report-Run-Id` (C in the test), and the URL becomes
  `run=C`. The rc behaviour is "the new job is bound to the run the retry created"; ratify that wording.
