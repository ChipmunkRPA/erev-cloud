# Effective combination split application — 2026-10-24

Ordinary supported same-currency combinations now support preview, submission, independent
approval and effective-date application. Submission binds the source hashes and allocation
plans for all active books. Approval appends a dated split event and recomputes atomically;
changed evidence rolls back the event, new computation and postings. The original calculation
envelope and earlier revenue remain intact. Repeated splits resolve effective membership;
retrospective membership corrections cannot erase an applied split history.

The drawer submits rationale and reviewed hashes, requires member-entity permissions, and
shows approved split history. Existing idempotency and separation-of-duties controls apply.

Necessary verification: database approval/application and rollback cases (3), drawer cases
(3), scoped Python/TypeScript checks and generated OpenAPI consistency. No deployment.

Remaining: foreign-currency split layer continuation and unsupported specialist methods;
this checkpoint does not claim complete system readiness.
