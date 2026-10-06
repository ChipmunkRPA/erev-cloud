# L8-C evidence: close cockpit and approvals platform rulings (Level 8, batch 1 of 2)

Lane worktree `~/dev/erev-wt/l2`, branch `sprint/l2`, fast-forwarded to main `0266227` before the
batch. Rulings implemented: D-88 L7-2-Q-1 (with the supervisor call), L7-2-Q-13 and L7-2-Q-8. No
Alembic revision was added.

## Commits

| Commit | Ruling | Files |
|---|---|---|
| `1c69059` | L7-2-Q-1 | `backend/erev_api/domain/close/gates.py`; `backend/tests/domain/close/test_gates.py`; `backend/tests/support/close_world.py` (new) |
| `1c957bf` | L7-2-Q-13 | `backend/erev_api/api/v1/approvals.py`; `backend/erev_api/domain/platform/approval_queries.py`; `backend/tests/api/test_cockpit.py`; `docs/api/openapi.json`; `frontend/src/lib/api/schema.d.ts`; `frontend/src/lib/api/queries/periods.ts`; `frontend/src/routes/close/__tests__/cockpit.test.tsx` |
| `5891f38` | L7-2-Q-8 | `backend/erev_api/domain/close/queries.py`; `backend/tests/domain/close/test_gates.py` |

## D-88 L7-2-Q-1: exception scope for the close

Implementation. `gates._open_exceptions` counts an item while its status is `OPEN` or
`IN_PROGRESS`, its severity is `BLOCKING` or `WARNING`, and its `period_id` is null or the period.
It also needs one of these: (a) `entity_id` is the entity; (b) `entity_id` is null and
`contract_id` is a contract of the entity; (b2) `entity_id` and `contract_id` are null and
`combination_group_id` is a group that holds a contract of the entity (`_entity_groups`); (c)
`entity_id`, `contract_id` and `combination_group_id` are all null. Code `CONTROL_TOTALS_MISMATCH`
is left out of `exceptions_open`, so it counts only in `interface_failures`. `unmapped_products`
uses the same clause. `blocker_statement` needed no other change: `interface_failures` still reads
the open mismatch items of failed imports. The module docstring `[J]` note now states the amended
rule.

Tests (`backend/tests/domain/close/test_gates.py`, world in `backend/tests/support/close_world.py`):

- Figure (1): `test_cockpit_blocker_counts[named]` and `[import-level]`. The import-level variant
  writes the two `PROGRESS_OVER_DELIVERY` findings as `validate._raise` writes them: source
  `IMPORT`, `import_upload_id` set, and entity, contract and group null. The named variant is kept.
  Both give `exceptions_open` 3, `EXCEPTIONS_CLEARED` FAILED 3, and BLK-02 = 3 − 1 = 2. BLK-03 is
  read through `GET /exceptions?code=VC_REASSESSMENT_MISSING&entity=AVM-US&period=FY2026-P09&count=true`.
- Figure (2): the same test adds an INFO item and an item of another period, each with and without
  an entity; `exceptions_open` stays 3.
- Figure (3): `test_ctl_002_failed_interface_run_fails_gate`. The open `CONTROL_TOTALS_MISMATCH`
  item (no entity, contract or group) gives `INTERFACES_COMPLETE` FAILED 1, while
  `EXCEPTIONS_CLEARED` stays PASSED 0 and API-S-Period blockers read `exceptions_open` 0 and
  `interface_failures` 1.
- `test_exception_scope_cases`: cases (a), (b), (b2) and (c) for AVM-US and a second entity
  (AVM-UK), plus a tenant-level `PRODUCT_UNMAPPED` item and a tenant-level mismatch item. Each
  entity gets `exceptions_open` 5 (its own a, b and b2, plus two case-(c) items) and
  `unmapped_products` 1. The mismatch item counts for neither.
- Targeted run: `make test TESTS=backend/tests/domain/close/test_gates.py`, 9 passed (including the
  L7-2-Q-8 test).

Figure (4), the seeded AVM-US FY2026-P09 counts at the sf-05-open capture:

- Method: `make seed` (`erev seed demo --tenants all`, the seed `scripts/e2e.sh` runs) on the lane
  dev database `erev_rv_l2_dev`. Tenant `avenmoor`, AVM-US, ASC606, FY2026-P09, state `open`. The
  counts come from `gates.blocker_counts` and `gates.derived_counts` under a tenant-wide system
  context. No Playwright run was made (see deviation D2).
- API-S-Period `blockers`: `exceptions_open` 2, `holds_open` 2, `unmapped_products` 0,
  `judgements_unreviewed` 1, `approvals_pending` 2, `interface_failures` 0, `jobs_failed` 0,
  `groups_dirty` 14, `batches_unexported` 0, `batches_unacknowledged` 0, `reconciliations_unsigned`
  0, `manual_adjustments_pending` 0.
- `derived_blockers`: `JOURNAL_RUN_NOT_CALCULATED` 1, `RECONCILIATIONS_NOT_GENERATED` 2.
- BLK-03 (`VC_REASSESSMENT_MISSING`, AVM-US, FY2026-P09, open) 0, so BLK-02 = 2 − 0 = 2. No SPEC-Q
  is raised under figure (4).
- The items counted in `exceptions_open`: two `PROGRESS_OVER_DELIVERY` items (source `IMPORT`,
  `BLOCKING`, case (c), an upload named, no period). These are WLD-B-04.
- Pending requests of AVM-US by subject type (`gates.request_of_entity`): `CONTRACT_ACTIVATION` 1
  and `JUDGEMENT_RECORD` 1. BLK-06 = max(0, 1 − 1) = 0 and BLK-15 = max(0, 0 − 0) = 0. These are
  the rows of the tenant, not what Maya can see; see L8-C-Q-2.
- Accepted consequences (i) to (iv) and the post-rc DIN backlog item are unchanged and not
  implemented here.

## D-88 L7-2-Q-13: approvals `entity` takes codes or ids

Implementation:

- `GET /approvals` `entity` is `list[str]` ("An entity code or id (API-C-11)"). The exact
  `FilterSpec` is removed from `APPROVAL_LIST`, and `entity` joins
  `approval_queries.CUSTOM_FILTERS`, so it still binds the cursor.
- `approval_queries._entity_clause` reads each value that parses as a UUID as an id and resolves
  the rest as codes through `legal_entity`. An unknown code answers 422 `validation-failed` with
  field `entity` and rule_id API-C-11. The clause is `gates.request_of_entity(entity_id)` OR-ed
  over the named entities.
- `_entity_ref` returns API-S-Ref `{id, code, name}` from one `legal_entity` read per page
  (`_entity_refs`) instead of raising.
- `frontend/src/lib/api/queries/periods.ts` `fetchBlockerCounts` passes `entity.code`.
- `make openapi` regenerated `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` in the
  same commit (XR-15).

Tests:

- `backend/tests/api/test_cockpit.py` `test_approvals_entity_counts_blockers`, in the WLD-B world:
  - `GET /approvals?status=PENDING&entity=AVM-US&count=true` gives `X-Erev-Total-Count` 3, equal to
    `approvals_pending`. The entity id form gives 3 as well.
  - Adding `subject_type=JUDGEMENT_RECORD` gives 1, so BLK-06 = 1 − 1 = 0. Adding
    `subject_type=MANUAL_ADJUSTMENT` gives 1, so BLK-15 = 0 − 1, clamped to 0.
  - A pending request whose subject is an AVM-UK contract and that names no entity: the AVM-US
    count stays 3 and the listing leaves it out. AVM-UK counts 1, and `entity=AVM-US&entity=<AVM-UK id>`
    counts 4.
  - The `MANUAL_ADJUSTMENT` request's `entity` is `{id, code "AVM-US", name}`; requests without an
    entity show null.
  - `entity=AVM-US&entity=AVM-XX` answers 422 `validation-failed` with `[("entity", "API-C-11")]`.
- `frontend/src/routes/close/__tests__/cockpit.test.tsx`: the approvals mock answers counts only
  when `entity` is the entity code, so the "blocker rows without unbuilt links" figures (judgements
  row 1, adjustments row 1) fail if the id is sent. `vitest --run cockpit.test.tsx`: 4 passed.
- Targeted run: `make test TESTS="backend/tests/api/test_cockpit.py backend/tests/api/test_approvals_api.py"`,
  11 passed and 1 deselected (not slow). `test_approvals_api.py` still asserts `entity` null for a
  request without one.
- Post-rc backlog items (i) and (ii) are recorded in the ruling and not implemented here.

## D-88 L7-2-Q-8: days to close in the entity time zone

Implementation. `queries.days_to_close` joins `legal_entity`. For a period in state `closed` or
`permanently_locked` with a current lock, days = (the lock's `created_at` converted with
`ZoneInfo(legal_entity.time_zone)`).date() − `period.end_date`. Any other state gives null. The
listing is unchanged: this period and the two before it, oldest first, ordered by
`period_state.period_end_date`.

Tests. `test_gates.py` `test_days_to_close_in_entity_time_zone` writes the rows directly (CLO-6 is
post-rc): an approved request, the open → closing → closed transitions, the `period_lock` with a
chosen `created_at`, and `current_lock_id`.

- FY2026-P07 locked at `2026-08-05T02:00:00Z` (2026-08-04 22:00 America/New_York) gives 4; the UTC
  date would give 5.
- FY2026-P08 locked at `2026-09-04T16:00:00Z` gives 4.
- FY2026-P09 open gives null through `GET /periods/{id}/cockpit`.
- After FY2026-P09 is locked at `2026-10-06T14:00:00Z`, `queries.days_to_close` gives 4, 4 and 6.

## Spec questions

- **L8-C-Q-1 (approvals `entity`: unknown ids and codes outside the reader's scope).** L7-2-Q-13
  rules only the unknown code. As built, a value that parses as a UUID is used as an id without a
  lookup, so an unknown or foreign id answers 200 with no rows. Codes are resolved through
  `legal_entity` under row-level security, so a code outside the caller's entity scope answers 422
  API-C-11 like an unknown code, as `GET /dashboard/home` does (`UNKNOWN_ENTITY`). Should an unknown
  id also answer 422, and should an out-of-scope code answer 422 or an empty page?
- **L8-C-Q-2 (BLK-06 and BLK-15 subtract only visible requests).** `approvals_pending` (BLK-01)
  counts every pending request of the entity. The approvals list, which the cockpit uses for the
  JUDGEMENT_RECORD and MANUAL_ADJUSTMENT counts, also applies `approval_queries.visible`: preparer,
  decider, or holder of a step permission for the entity. A reader who cannot see a pending
  judgement request gets a count of 0 there, so BLK-06 shows 1 instead of 0 for that reader. The
  Maya-visible counts at sf-05-open were not measured (D2). Accept as built for the rc, or should
  the cockpit counts come from API-S-PeriodCockpit instead?

## Deviations

- D1. The WLD-B world moves from `test_gates.py` to the new support module
  `backend/tests/support/close_world.py`: `CloseWorld`, `close_world`, `system_session`,
  `contract_of` (which now returns the group id too), `other_entity`, `submitted_judgement` and
  `wld_b(findings_named=...)`. `test_cockpit.py` needs the same world for the L7-2-Q-13 figures.
  The fixture shape is unchanged apart from the import-level variant.
- D2. The figure (4) counts come from a fresh `erev seed demo --tenants all` of the lane dev
  database, read through the domain functions. They were not taken inside the Playwright run of
  `screens.spec.ts` "SF-05 cockpit maya", which needs the e2e stack. Screens tests that run before
  SF-05 in the same Playwright run could change the counts, and the approval counts ignore Maya's
  visibility (L8-C-Q-2).
- D3. `days_to_close` subtracts `period.end_date`, as ruled, instead of
  `period_state.period_end_date`.

## Shared files touched

- `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` (generated by `make openapi`; other
  lanes that regenerate them will conflict on the `approvals_list` `entity` parameter).
- `backend/tests/support/close_world.py` (new support module).
- Named by the rulings: `backend/erev_api/domain/platform/approval_queries.py`,
  `backend/erev_api/api/v1/approvals.py` and `frontend/src/lib/api/queries/periods.ts`.

## Gates

- `make lint` OK and `make typecheck` OK after each ruling (mypy: no issues in 557 source files).
- `make openapi` OK (L7-2-Q-13).
- `make ci` on `5891f38` plus this evidence file: OK. Backend 2113 passed, 0 failed, 0 skipped (362
  deselected); vitest 595 passed in 93 files, 0 failed, 0 skipped; build OK.
- `make test-pg` on the same tree: OK. Stage pg 290 passed, 0 failed, 0 skipped (2185
  deselected). No PostgreSQL shared-memory or connection reruns were needed.

# Batch 2 of 2: D-88 L7-2-Q-7, L7-2-Q-14, L7-2-Q-16 and the SF-05 screens rows

Same worktree and branch, on top of batch 1 (`87249be`). No Alembic revision was added, and no
OpenAPI or schema change was needed.

## Commits (batch 2)

| Commit | Ruling | Files |
|---|---|---|
| `1cc040e` | L7-2-Q-7 | `backend/erev_api/approvals/subjects.py`; `backend/erev_api/approvals/engine.py`; `backend/erev_api/domain/platform/approval_queries.py`; `backend/erev_api/domain/close/commands.py`; `backend/tests/api/test_cockpit.py`; `backend/tests/domain/imports/test_exception_queue.py` |
| `c4e4877` | L7-2-Q-14 | `frontend/src/routes/close/cockpit.tsx`; `frontend/src/routes/close/__tests__/cockpit.test.tsx`; `frontend/src/lib/api/queries/periods.ts` |
| `38df15c` | L7-2-Q-16 | `frontend/src/routes/close/lock-drawer.tsx`; `frontend/src/routes/close/__tests__/cockpit.test.tsx` |

## D-88 L7-2-Q-7: checklist waiver link

Implementation:

- `subjects.CoveredLifecycle` gains `link: Callable[[Session, UUID], str | None]`.
- The new `subjects.covered_link(session, subject_type, subject_id)` returns the first non-null
  link among the covered lifecycles of the subject type.
- `engine._subject_link(session, spec, request)` tries `covered_link` first, then
  `spec.link_path`, then the request link. It is used for NTF-02 to NTF-04 and the void
  notification, with `uow.session` or the session in hand.
- `approval_queries._subject_href(session, row)` also tries `covered_link` before
  `spec.link_path`.
- `commands.checklist_item_link` is registered as the `close_checklist_item` link. It reads
  `close_checklist_item` joined to `legal_entity`, `period` and `close_checklist_template`. It
  returns `/close/<entity code>/<book code>/<period key>?drawer=task&task=<gate_check_code, or the
  template code of a manual task>`, or null when the id is not a checklist item.
- Exception items still link to `/data/exceptions/<id>`.
- The cockpit already opens that drawer through `drawer=task&task=<checklistRowKey>`
  (L7-2-Q-15 vii).

Tests:

- `backend/tests/api/test_cockpit.py` `test_waiver_routes_exception_waiver`: after Priya approves,
  `GET /approvals/{id}` answers `subject.href`
  `/close/AVM-US/ASC606/FY2026-P09?drawer=task&task=RECONCILIATIONS_GENERATED`. Marcus's
  `ITEM_APPROVED` notification is the only one of that kind, with the same `link_path` and the
  item as `subject_id`.
- `backend/tests/domain/imports/test_exception_queue.py` `test_committed_input_needs_waiver`: the
  pending waiver of an exception item answers `subject.href` `/data/exceptions/<item id>`. This is
  a regression guard for the fallback; the ruling does not name it.
- Targeted runs:
  - `make test TESTS="backend/tests/api/test_cockpit.py backend/tests/api/test_approvals_api.py"`:
    11 passed, 1 deselected.
  - `make test TESTS=backend/tests/domain/imports/test_exception_queue.py`: 6 passed.
  - `make lint` OK and `make typecheck` OK (mypy: no issues in 557 source files; tsc OK).

## D-88 L7-2-Q-14: cockpit R-RC-1 commands hidden

Implementation. `cockpit.tsx` holds one module constant, `UNBUILT_CLOSE_COMMANDS`, with the R-RC-1
note: `run-close` (API-R-39, CLO-19), `submit-lock` and `permanent-lock` (CLO-6), and
`request-reopen` (CLO-7). `commandBuilt(command)` gates each command. The owning item removes its
entry when it builds the route. "Lock period" is not listed. It stays rendered for `period.lock`
holders, aria-disabled with its reason line. The `periods.ts` `CLOSE_RUNS_PATH` comment now names
CLO-19.

Hidden fragments recorded for the CLO-23 tick (the CTR-22 precedent):

- "Run close": the secondary in `open`, and the primary in `closing` without a request and in
  `reopened`.
- "Submit for lock": the secondary in `closing` without a request.
- "Request reopen": the secondary in `closed`.
- "Permanently lock": the overflow entry in `closed`.
- Unreachable but kept: the `runClose` command with its JobProgress and problem banners, and the
  `SubmitForLockDialog`, `ReopenDrawer` and `PermanentLockDialog` copy for CLO-6, CLO-7 and CLO-19
  (L7-2-Q-15).

Tests (`frontend/src/routes/close/__tests__/cockpit.test.tsx`, "action bar per state", R-RC-1
subset):

- `open`, Maya: the primary is "Start soft close" (`bg-accent-solid`). There is no "Run close", no
  "Lock period" and no "Submit for lock".
- `closing` without a request, Maya: the soft close banner shows, and "More close actions" opens
  the menu item "End soft close". There is no "Run close", "Submit for lock", "Start soft close"
  or "Lock period" (Maya has no `period.lock`).
- `closing`, Marcus (`period.lock`): "Lock period" is aria-disabled, with no "Run close" or "Submit
  for lock".
- Added beyond the ruled subset: in `closed`, a holder of `period.lock` and
  `period.reopen_request` sees no "Request reopen" and no overflow menu, so no "Permanently lock".
- The "Run close" and "Submit for lock" assertions return with CLO-19 and CLO-6.
- `vitest --run src/routes/close/__tests__/cockpit.test.tsx`: 4 passed. `make lint` OK and `make
  typecheck` OK.

## D-88 L7-2-Q-16: lock drawer failingGates leaves out CONTROLLER_CERTIFIED

Implementation. `lock-drawer.tsx` `failingGates` counts items with `is_blocking` true, a status
other than PASSED, WAIVED or NOT_APPLICABLE, and `gate_check_code` other than
`CONTROLLER_CERTIFIED`. The lock guard, the reason-line count and its links use it. The KPI
"Checklist <passed> of <total> passed" still counts all 13 items, and `GateTable` still lists the
certification row with its chip. The backend half (request-lock evaluating 12 gates) is left to
CLO-6.

Tests (`cockpit.test.tsx`; the `checklist()` fixture fails CONTROLLER_CERTIFIED in every case):

- "lock period disabled with reason line", Marcus: APPROVALS_CLEARED, EXCEPTIONS_CLEARED and
  CONTROLLER_CERTIFIED fail. The reason line reads "Lock is not available: 2 close gates have not
  passed.", and its links are exactly ["No pending approvals", "Exceptions resolved, waived or
  dismissed"].
- "action bar per state", `closing` for Marcus: only CONTROLLER_CERTIFIED fails and no lock request
  is pending. The reason line is exactly "Lock is not available: the period has not been submitted
  for lock." (L7-2-Q-15 i).
- "blocker rows without unbuilt links": the old `toContain("11")` also matched the checklist
  figure, so the strip figures are now read by position. Blockers read "11" and Checklist reads
  "11 of 13 passed", with certification counted.
- `vitest --run src/routes/close/__tests__/cockpit.test.tsx`: 4 passed.
- `make lint` first failed on `prettier --check` for `lock-drawer.tsx`. After `prettier --write`
  it passed. `make typecheck` OK.

## SF-05 screens rows

Run: `make e2e PROJECT=screens SPEC="frontend/e2e/projects/screens.spec.ts:2067,frontend/e2e/projects/screens.spec.ts:2099"`
("SF-05 cockpit maya" and "SF-05:journal-preview maya") on `38df15c`, in a gate slot. Result: 2
passed, 0 failed, 0 flaky, 0 skipped; `OK e2e`. The `e2e.sh` SPEC filter treats any item other than
a journey as a Playwright file filter, so the rows are selected by `file:line`.

Captures read in light and dark (`frontend/e2e/.screens/screens/`):

- `01-sf-05-open` (Maya, AVM-US Sep 2026, open):
  - Action bar: only the primary "Start soft close". No "Run close" (L7-2-Q-14), and no "Lock
    period" or reason line, because Maya has no `period.lock`.
  - KPI strip: Blockers 23, Checklist 2 of 13 passed, Reconciliations reviewed 0 of 2, Journal
    difference —, and Days to close Jul, Aug and Sep 2026 "In progress".
  - Blockers (23): Pending approvals 2, Exceptions 2, Holds 2, Contracts changed since the last
    close run 14, Journal run not calculated 1, Reconciliations not generated 2. These agree with
    the batch 1 figure (4): BLK-02 2, and the judgements and adjustments rows are hidden at 0.
  - Both themes are legible, and no chip or label is clipped.
  - Observation O1: the capture is 1440×900 and ends at the 12th checklist row (Manual adjustments
    cleared). The shell scrolls inside the main region, so the full-page screenshot does not reach
    the 13th row (Controller certification). This behaviour predates this batch and no assertion
    depends on it.
- `02-sf-05-journal-preview` (Aug 2026):
  - Debits and Credits 547,053.23, Difference 0.00 with "Pass" and "Balanced".
  - The by-account-role table shows Revenue, Contract liability and Total.
  - "Journal run not calculated" appears beside "Run journals", and the action bar holds only
    "Start soft close".
  - Both themes are legible.

## Spec questions (batch 2)

- **L8-C-Q-3 (checklist waiver link under the reader's row-level security).**
  `checklist_item_link` reads through the caller's session. `close_checklist_item` is RLS-TE on
  `entity_id`, and `legal_entity` is scoped as well. The waiver request names no entity, and its
  step permission is checked tenant-wide. So a reader, or a decider, whose entity scope leaves out
  the item's entity can still list or decide the request. For that caller the covered link is
  null, and `subject.href` falls back to `spec.link_path`, `/data/exceptions/<item id>`, which
  names no exception item. When that caller decides, the preparer's notification gets the same
  fallback. Should the link read run under a tenant-wide system context, or should `href` be null
  when the item cannot be read?
- **L8-C-Q-4 (submit-for-lock 409 banner and failingGates).** L7-2-Q-16 says `failingGates` drives
  the submit-for-lock 409 banner. As built, `SubmitForLockDialog` lists the `close-gates-failed`
  problem errors, matched to checklist rows by `rule_id` = `gate_check_code`, and does not call
  `failingGates`. The dialog cannot be reached in the rc ("Submit for lock" is hidden under
  L7-2-Q-14), and CLO-6's request-lock evaluates 12 gates, so its errors will not name
  CONTROLLER_CERTIFIED. The banner is unchanged. Should CLO-6 filter it through `failingGates`, or
  keep listing the server's errors?

## Deviations (batch 2)

- D4. `checklist_item_link` percent-encodes the entity code, book code, period key and task code
  (`urllib.parse.quote`, `safe=""`), as `cockpitRoute` and `openTask` do in `cockpit.tsx`. The
  seeded codes contain only `[A-Z0-9_-]` and come out unchanged.
- D5. `CoveredLifecycle.link` is a required field with no default. `commands.py` holds the only
  registration.
- D6. With "Run close" hidden, a `period.close` holder in `closing` without a request has no
  primary. `reopened` keeps "Start soft close" as a secondary with no primary. The ruling promotes
  no other command, and `reopened` cannot be reached in the rc (CLO-7).

## Shared files touched (batch 2)

- Platform approvals, named by the ruling but shared:
  - `backend/erev_api/approvals/subjects.py`: `CoveredLifecycle` gains the required `link` field,
    so any other covered-lifecycle registration must pass `link`; new `covered_link`.
  - `backend/erev_api/approvals/engine.py`: `_subject_link` takes the session.
  - `backend/erev_api/domain/platform/approval_queries.py`: `_subject_href` takes the session.
- `backend/tests/domain/imports/test_exception_queue.py`: one href assertion; not named by the
  ruling.
- `frontend/src/lib/api/queries/periods.ts`: comment only.

## Gates (batch 2)

- `make lint` OK and `make typecheck` OK after each ruling.
- `make e2e` SF-05 screens rows: 2 passed, 0 failed, 0 skipped.
- `make ci` on `38df15c`, with the batch 2 evidence uncommitted: OK. Backend 2113 passed, 0
  failed, 0 skipped (362 deselected); vitest 595 passed in 93 files, 0 failed, 0 skipped; build OK.
- `make test-pg` on the same tree: OK. Stage pg 290 passed, 0 failed, 0 skipped (2185
  deselected). No PostgreSQL shared-memory or connection reruns were needed.
