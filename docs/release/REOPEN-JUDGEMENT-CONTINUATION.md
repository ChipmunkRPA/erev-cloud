# Error-correction reopen evidence — October 7, 2026

B1-12 is implemented and verified for publication. Revision 0137 retains tenant-bound citations
in a separate `period_reopen_basis` record and immutable reopen history. Submission keeps the
period FOR SHARE lock and its existing row version; a per-period advisory lock serializes basis
replacements. The approval hash binds the judgement content and review identity; final approval
revalidates both under locks. Submitted evidence remains in the immutable request audit and is
shown only to authorized approval/history readers. The selector filters entity, applicable book,
topic and reviewed status and follows pagination.

Verification on October 7, 2026:

- 138 close, approval API, journal and judgement compatibility tests passed in 419.60 seconds.
  These include invalid/missing/cross-scope citations, submitted/superseded records, lost access,
  duplicate/withdrawn requests, immutable history and busy-judgement retries.
- Both close/reopen decision interleavings and the 14 reviewed-basis tests passed in the preceding
  57-pass run. Its sole failure expected a redacted header after all entity access was removed;
  the API correctly returned 404. The corrected expectation passed in the 138-test run.
- All 5 migration tests passed in 16.31 seconds, including full upgrade/downgrade/upgrade and
  database lint. The workflow tests also prove downgrade refuses retained citations outside
  the owner's current tenant scope.
- 742 unit/architecture/snapshot checks passed in 166.98 seconds. Frontend: 62 tests passed;
  TypeScript and ESLint passed. Source Mypy and Ruff passed. Design and secret scans were clean.

The earlier period-row storage design failed a concurrent later-period close; that evidence
motivated the separate basis table. A redundant mid-domain schema reset caused cached enum OID
errors and was removed; full migration round trips retain that coverage. Historical run details
remain in BUILD-HISTORY-2026-10-07.md. This scoped verification is not a full-backend or production
readiness claim. Independent accounting sign-off and other release gaps remain. No deployment.

The error-correction reopen must name a reviewed `ESTIMATE_VS_ERROR` judgement for a contract
of the same tenant and entity, applicable to the same book (or all books). The accounting
conclusion remains the accountant's responsibility; the application must not infer it from
free text. The existing two-person reopen approval, including a Controller, remains required.

## Evidence binding

- Keep the nullable current citation in `period_reopen_basis` (one row per tenant/period state)
  and nullable `judgement_record_id` on `period_lock`, with tenant-composite foreign keys and
  entity-scoped row security. Existing immutable history remains unaltered. A downgrade must
  refuse to discard retained citations, including those outside the owner's tenant context.
- Add `judgement_record_id` to the reopen request body. Require it for `ERROR_CORRECTION`;
  refuse a supplied citation for unrelated reasons instead of silently ignoring it.
- Hold the period using the existing command lock, validate the record, then persist its ID
  before submitting the approval. Preserve the state version and audit the citation. A fresh
  request replaces the current citation; a non-error request clears it. Never replace a live
  request's evidence without the kernel's existing-request checks.
- Include the citation, full accounting content, status and review identity in
  `period_reopen_content`. Content reads must not acquire judgement locks before the period:
  the approval kernel reads its hash before calling the close hook.
- At final approval, hold the period, acquire the judgement share lock with NOWAIT, validate
  the current record, and repeat the request's own content-hash check under those locks.
  Superseded or otherwise changed evidence voids the pending request through the existing
  stale-basis rollback path. Concurrent review produces a retryable conflict. Older pending
  error-correction requests without a citation must not reopen the period.
- Store the citation on the immutable REOPEN lock and expose it to the approver and history.
  Do not require a new citation on an ordinary LOCK or retroactively alter earlier history.

The validation foundation holds a share lock until the caller's transaction ends. A review
already holding the judgement row is refused immediately inside a savepoint, keeping the
caller's transaction usable and avoiding a judgement/period lock-order deadlock. It returns
canonical content and the review identity for binding; it does not submit or approve anything.

## User flow

For an error correction, select an existing reviewed judgement and show its number, conclusion
and reviewer with a link to the record. Filter by topic and review status, and make the entity
and book clear; the backend remains authoritative. A user without a reviewed record must
prepare it and complete independent review first. The error-correction form selects that reviewed record before requesting the reopen. The
separate optional judgement-authoring flow for other reasons and attachment retry behavior are
preserved. No deployment is required.

## Required integration evidence

Exercise the public API for missing, unknown, cross-tenant, cross-entity, wrong-book,
wrong-topic, draft/submitted/superseded and valid citations. Revalidate after the first reopen
approval, including supersession before the second decision. Verify transaction rollback,
unchanged period/history after refusal, immutable citation after success, both concurrency
orders, and legacy pending requests. Exercise the form's selection, validation, retry and
permission paths. Run migration upgrade/downgrade and ORM checks, regenerate the OpenAPI types,
and run the affected close/approval and frontend tests. Only then close B1-12 in LIMITS.
