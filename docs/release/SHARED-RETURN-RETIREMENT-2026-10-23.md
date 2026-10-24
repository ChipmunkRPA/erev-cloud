# Shared return member exits — October 23, 2026

Removing members from portfolio metadata no longer leaves users without a way to end an applied
shared return estimate. A new version captures both current members and members leaving the
previous approved version. Saving a version for an empty current population is allowed when it
retires a previously applied population. An empty portfolio without such a predecessor remains
invalid. The version editor displays the exiting members explicitly.

Impact preview, locking and event recipients include both retained and exiting members, even
when their contracts are now in different combination groups. Approval uses the existing
independent approval flow and atomically appends events/recomputes all affected groups. The
native version distinguishes its active scope from event recipients: exiting members receive
the version without remaining under its override. A fully retired population is an explicit
empty active scope. An applicable local estimate can resume from the new version's effective
date; historical shared scope remains on the earlier version. Metadata removal alone does not
change recognized revenue. Frozen bindings and audit history remain immutable.

The additive retired-members field defaults to empty for existing saved bindings; preview
comparison normalizes that default without rewriting historical records or their hashes.
Shared return changes still require attached supporting evidence, including unchanged rates.

## Verification

- PostgreSQL public API: remove final member, save empty-scope successor, preview prior member,
  attach evidence, submit/independently approve, apply event and recompute; prior version becomes
  superseded while its original member scope remains in the computation input. Passed.
- 32 focused loader/native cases passed, including partial and complete exits, effective-date
  fallback, re-entry and duplicate application positions.
- 11 portfolio UI cases passed, including exit display and submit/approval navigation.
- Type checks, targeted lint and OpenAPI generation passed.

## Remaining work

This implements portfolio shared-return scope exits, not contract-combination reassessment.
Changing retained target definitions, onboarding new targets, other shared estimate kinds and
shared breakage application remain open. No deployment or full-readiness claim.
