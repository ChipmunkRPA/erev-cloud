# Step 1 posting-date approval — October 7, 2026

The implementation is included in this direct-main change. B1-13 retains the specific
verification work listed below, and the wider B1-2 remains open. This is a scoped engineering
change, not a production-readiness or independent accounting-sign-off claim.

Subsequent sandbox continuation resolves the loss/FX monetary-comparison omission found
during these checks. See PROGRESS.md for scoped positive and negative export/load evidence.
Step 1-specific attached-evidence export/load coverage remains separate and open.

Final scoped compatibility: **93 passed in 486.28 seconds**. A separate terminal-decision
regression passed in **16.56 seconds**: mixed batches are refused; rejection and withdrawal
leave accounting state unchanged; resubmission applies once; repeated decisions cannot append
or compute again. All six changed source modules pass Mypy. Repository-wide lint, frontend
checks and migration results are recorded below and in PROGRESS.md.

## Local implementation and current verification

- STEP1_EVENT uses event submissions with its own validation/derivation lifecycle and
  independent event.approve authority, no automatic approval. Old generic submissions
  retain their Step 1 refusals. Migration 0139 adds the subject enum.
- Pending requests preserve the stream, books, postings and holds. The approval appends
  the revalidated assessment/flag, any derived gate and system hold releases atomically;
  every effect carries the approval id, and applied_event_ids includes released holds.
- The hash binds group heads/status, enabled books, judgement content/reviewer/status
  and period state/lock ids. Locks protect those reads. Routing checks batch and derived
  release dates across the group and every dry-run posting destination. A local-day change
  makes the request stale before the current-day system release can use an unreviewed date.
- The preview stores computed figures and readable assessment dates/cited conclusions.
  The drawer reports the pending approval request. Schema/types/catalogues are updated.
- Initial successful lifecycle run: 2 passed in 18.88 seconds. Compatibility before the
  final routing/preview/day changes: 64 passed, 1 fixture failure in 304.33 seconds.
  Corrected the missing cancel-close reason. Latest targeted tests: **5 passed in 38.13
  seconds**, covering open, unrelated close, soft close with self-review refusal and
  independent application, changed period and superseded judgement. Applied event ids
  and approval references are asserted on all three resulting events.
- Frontend: 6 tests passed in 1.43 seconds. Source Mypy: four files clean. TypeScript,
  Ruff and whitespace checks passed. Logs: `/private/tmp/step1-date-review-*.log`.
- Full migration round trip and database lint passed in the 4-pass, 1-failure migration
  run (16.98 seconds); its sole failure was the old head assertion expecting 0138.
  Updated that expectation to 0139; the head recheck passed in 0.15 seconds.

Further October 7 verification: **8 cases passed in 51.23 seconds**, including reopened
and reopened-then-closing periods. The SSP publication regression reproduced approval
against changed calculation inputs. Retained preview provenance now includes the original
engine input hash and a comparison fingerprint; final approval rejects changed inputs.
Only synthetic pending-event timestamps are normalized for this comparison. The SSP drift
case passes with that check. **Four additional cases passed in 34.72 seconds**: same-day
delay, next-day staleness, busy submission and busy approval. Performing-entity periods now
join the locked basis; migration 0139 also updates stored report subject filters. Expanded compatibility finished with **73 passed in 349.91 seconds**. The migration
suite finished with **6 passed in 21.78 seconds**; a new test checks report-filter equality
with the runtime enum, removal on downgrade, restoration on upgrade and the immutability
trigger remaining enabled. Approval-detail and assessment-drawer suites finished with
**56 passed in 3.15 seconds**. These are scoped checks, not publication readiness. Logs: `/private/tmp/step1-date-review-input-basis.log` and
`/private/tmp/step1-date-review-concurrency-day.log`.

The deferral regression failed on the previous local implementation (1 failure in 14.28
seconds): approval succeeded while the book remained in its old state. STEP1_EVENT now
requires a successful computation within the approval transaction. The actual post-append
bundle is compared against the checked pending-event bundle, normalizing only SYSTEM append
attribution, recorded time and assigned sequence, with actual event order preserved. The
engine receives the unmodified actual bundle; no persisted input hash is rewritten. Failed
computation rolls back the decision and effects. Ordinary fact-capture paths still defer.
Three success controls passed in 30.37 seconds; failure/late-input checks passed in 23.63
seconds, including retry after failure. The late-input test injects an engine-version change;
real configuration-publication interleavings remain to be tested. Large decisions may take
longer without deferral; no latency guarantee has been verified. Expanded compatibility is
complete: **77 passed in 374.20 seconds**,
`/private/tmp/step1-date-review-atomic-compatibility.log`. The API-client case passed, including pending review and non-manual attribution.
Two actual concurrent SSP-publication cases passed in **23.96 seconds**: publication between
validation and the final calculation read voids the stale request without applying it;
publication after that read preserves the reviewed ledger amounts. The first publication
probes stopped at the fixture's old pre-MFA session; the current enrolled session fixed them.
Logs: `/private/tmp/step1-date-review-publication-client.log` (one pass, two fixture failures)
and `/private/tmp/step1-date-review-publication-interleavings.log` (two passes). FX and other
configuration interleavings still require coverage.

Draft-gate review now includes the current and proposed contract status in the retained
preview, rendered with the normal contract status labels. The frontend suite passed 59
checks in 2.92 seconds. The public-API draft/gate-boundary cases, two-book/API-client cases and immediate-path
control passed: **5 in 39.64 seconds**,
`/private/tmp/step1-date-review-draft-gate-compatibility.log`. Their initial
run exposed the missing status; later fixture corrections account for no hold on a draft
judgement and count only CONTRACT_COMPUTE jobs for the no-deferral assertion. The size
boundary is exercised by lowering the threshold, not by simulating real-volume performance.

Actual performing-entity verification passed two public-API cases in **22.88 seconds**.
AVM-US owns the contract and AVM-OPS performs its subscription in USD. An open performing
period preserves immediate append; soft-closing only AVM-OPS requires approval while AVM-US
stays open. Lock contention on the performing period refuses safely, and retry writes the
exact reviewed ledger deltas by entity/book/account role/side. Log:
`/private/tmp/step1-date-review-performing-entity.log`. The performing-period-change case
also passed (**1 in 17.33 seconds**): canceling its close voids the stale request without
changing the contract stream, ledger or hold. Log:
`/private/tmp/step1-date-review-performing-period-change.log`. This preserves the accepted contract-owner/group approval scope;
performing entities enter the posting-window checks. It is not multi-currency or volume proof.

Multi-currency performing-entity checks passed **2 cases in 25.67 seconds**. The contract
is denominated in USD and performed in a GBP-functional entity; published spot, average
and closing rates supply the calculation. The unchanged control compares both currencies'
posted amounts with the preview. A new average-rate publication makes the assessment stale.
Log: `/private/tmp/step1-date-review-performing-fx.log`. The real simultaneous publication
case passed (**1 in 17.48 seconds**): PostgreSQL confirms the publisher waits on the decision's
backend, then publication completes after the reviewed transaction and functional amounts
are posted. Log: `/private/tmp/step1-date-review-performing-fx-interleave.log`. Earlier probes
failed query matching (truncated table name and then lowercase matching); the passing probe
matches the visible reach CTE and verifies the publisher/holder backend identities.

The physical 201-obligation case passed (1 in 18.73 seconds) without lowering the budget.
This is functional verification, not a production performance guarantee. Full `make lint`
passed. Evidence-registry and snapshot-export checks passed 25 cases; one existing drift
guard exposed a real monetary-verification omission: stored loss provisions and FX layer
movements are not included in sandbox monetary comparisons. Keep that guard and resolve
the omission; do not treat regenerated rows as verified. Step 1 subject-reference cases pass.

Do not close B1-13 yet. Audit the remaining lifecycle controls and
configuration-publication races between comparison and computation, and the new
synchronous decision path; the fingerprint alone does not establish that concurrency guarantee. The retained preview now includes all-book revenue and all output posting lines with
entity, account, period and both currencies. One- and two-book public-API cases passed
(2 in 26.27 seconds); the expanded matrix compares preview amounts with actual ledger
entries after approval and passed all 13 cases in 98.92 seconds. Frontend checks passed (58 in 4.37 seconds), including a multi-entity,
multi-currency display fixture and suppression of a false primary-book-only no-impact claim.
Performing-entity and multi-currency integration results are recorded above.
Finish snapshot compatibility and final publication checks; report-filter migration checks passed.
No full-suite or accounting-sign-off claim is supported.

## Reproduced behavior

The public API creates and activates a contract, independently reviews its
NOT_A_CONTRACT judgement while September is open, and starts September's soft close.
The preparer then submits a September 8 significant-change flag and not-probable
assessment together. The current endpoint returns an appended result, advances the
stream from 4 to 7 and releases the judgement hold immediately. The open-period control
passes. This isolates the assessment-date defect from the separate judgement submission
and review posting paths in B1-2.

The first regression run on main `5ca602f` plus the local test produced one pass and one
failure in 17.70 seconds. Log: `/private/tmp/step1-date-review-regression.log`.
The final approval assertions added afterwards are acceptance criteria, not verified
behavior: the test currently fails before reaching them. Existing event submissions
return HTTP 201 with `event_submission_id` and `approval_request_id`; HTTP 202 is reserved
for computation jobs. Keep that response convention.

The final test rerun again produced one pass and one failure in 19.76 seconds:
`/private/tmp/step1-date-review-regression-final.log`. Ruff and whitespace checks pass.

## Implementation requirements

- Store the original assessment/flag batch as a pending submission when its effects
  reach soft close or a reopened period. Check every affected entity/book, including
  group computations and derived hold-release effects; do not inspect only the first
  event or assume the payload book is the entire posting scope. Hold period locks
  through the decision that chooses direct append versus pending review.
- Keep the stream, book status, ledger and holds unchanged while approval is pending.
  A reviewed accounting conclusion does not approve an effective date selected later.
  A different eligible person must review the date; automatic approval is forbidden.
- Use an explicit dedicated approval subject/lifecycle for the validated Step 1 batch.
  Legacy MANUAL_EVENT and ATTRIBUTE_CHANGE submissions must retain their rejection
  of assessments, flags, caller-supplied activation and forbidden voids. Merely removing
  `_submit`'s refusal or `step1.refuse_stored` would reopen existing security defects.
- Bind the original events, live contract/group basis, enabled books and cited reviewed
  judgement basis. At approval, lock and check them again before appending anything.
  Concurrent review must retry safely; supersession, later assessments, a changed booking
  or an incompatible book/period change must not apply a stale reviewed proposal.
- Reuse the authoritative Step 1 validation/gate calculation rather than appending the
  stored input directly. Its derived not-a-contract gate and system hold releases must
  be applied atomically with the approved assessment and the ensuing computation.
  Preserve preparer attribution, event evidence and the approval reference on effects.
- Handle rejection, withdrawal, lost scope and duplicate/retried decisions. A pending
  submission must remain reachable in the queue, show its date and reviewed conclusion,
  and give the preparer an accurate pending message instead of an “assessment saved” toast.
  Regenerate schema/types and preserve audit/snapshot/migration compatibility.

## Remaining verification

The scoped results above cover soft close, reopened state fixtures, open-period compatibility,
API-client inputs, two books, performing entities, independent/self review, period contention,
superseded judgements, draft gates, hold release, and selected SSP/FX publication races.
The reopened fixtures do not prove a complete certification/reopen workflow. Cover new-subject-specific lost scope,
later Step 1 events, book changes and attached-evidence retention through snapshot export/load.
Generic legacy-submission bypass controls are retained. The separate loss/FX comparison
omission has since been corrected with integration coverage, as noted above.

B1-2 also covers other event producers, holds, memos, judgements, integrations,
exception reprocessing, close recomputations and auto-approved activation. Completing
this Step 1 path alone cannot close that broader limitation. Independent accounting
sign-off and a passing current full backend suite are still required for readiness.
