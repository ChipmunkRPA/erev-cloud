# Shared return estimate workflow — October 23, 2026

Shared RETURN_RATE versions now support submission, independent approval, atomic application to
member streams and recomputation of each affected combination group. The portfolio version
editor exposes submission, withdrawal and the linked approval request. Unsaved edits must be
saved before submission; all commands use the current version ETag.

Submission requires supporting evidence (or the existing valid no-change attestation), saved
explicit member targets and a successful native impact preview. The approval request stores
group/member balance and period effects. Existing maker/editor exclusion and controller routing
apply. Multi-currency impacts are not presented as one functional-currency amount; the routing
threshold uses USD conversion and conservatively flags missing conversion evidence.

Approval rechecks the reviewed content basis, evidence, member bindings and current routing
under portfolio, version, group and FX publication locks. It supersedes the prior approved
version, appends ESTIMATE_CHANGED to each frozen member stream, records audit lineage and
recomputes each distinct group in the same transaction. A refusal rolls back the whole command.
Repeated references to the same version preserve its first application position in revision 12;
older evidence revisions retain their existing behavior. Rejection and withdrawal retain member
audit lineage. Withdrawal leaves the earlier approved version effective.

## Necessary verification

- Public PostgreSQL API workflow: evidence refusal, submission, self-approval refusal,
  independent approval, member event and new computation, follow-up withdrawal; passed.
- Native transaction-price cases: 23 passed, including duplicate applications, effective-date
  member scope and prior evidence revisions.
- Portfolio UI: 11 passed, including dirty-form submission prevention, ETag and approval link.
- Type checks, targeted lint and generated OpenAPI/types checked.

## Still open

Only shared return-rate versions are enabled for application. Other shared estimate kinds remain
in draft/preview workflows. Shared breakage has total/SSP preview, but its expected-redemption
input policy remains unresolved. Do not infer expected redemptions by subtracting breakage from
entitlements: that can change unclaimed-property liabilities. Empty-population retirement,
target changes and effective-date combination reassessment remain unfinished. This checkpoint
is not full-system production-readiness verification. No deployment was performed.
