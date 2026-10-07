# Error-correction reopen evidence — October 7, 2026

B1-12 remains open. `close.reopen_judgements.reviewed_basis` is the validated database
foundation; the public reopen command and form do not call it yet. This document tracks the
remaining integration, not a release-readiness claim.

The error-correction reopen must name a reviewed `ESTIMATE_VS_ERROR` judgement for a contract
of the same tenant and entity, applicable to the same book (or all books). The accounting
conclusion remains the accountant's responsibility; the application must not infer it from
free text. The existing two-person reopen approval, including a Controller, remains required.

## Evidence binding

- Add nullable `reopen_judgement_record_id` to `period_state` and nullable
  `judgement_record_id` to `period_lock`, with tenant-composite foreign keys. Existing immutable
  history remains unaltered. A downgrade must refuse to discard retained citations.
- Add `judgement_record_id` to the reopen request body. Require it for `ERROR_CORRECTION`;
  refuse a supplied citation for unrelated reasons instead of silently ignoring it.
- Hold the period using the existing command lock, validate the record, then persist its ID
  before submitting the approval. Increment the state version and audit the citation. A fresh
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
prepare it and complete independent review first. The current form's sequence—request reopen,
then create an optional judgement—cannot satisfy this control and must change. Preserve the
separate judgement authoring flow and attachment retry behavior. No deployment is required.

## Required integration evidence

Exercise the public API for missing, unknown, cross-tenant, cross-entity, wrong-book,
wrong-topic, draft/submitted/superseded and valid citations. Revalidate after the first reopen
approval, including supersession before the second decision. Verify transaction rollback,
unchanged period/history after refusal, immutable citation after success, both concurrency
orders, and legacy pending requests. Exercise the form's selection, validation, retry and
permission paths. Run migration upgrade/downgrade and ORM checks, regenerate the OpenAPI types,
and run the affected close/approval and frontend tests. Only then close B1-12 in LIMITS.
