# Shared return member onboarding — October 23, 2026

A new portfolio member can now use an existing shared return definition when it contains all of
that definition's common obligation keys. Saving the next version resolves each current member's
own original obligation IDs and freezes them on that version. The definition's original target
IDs remain the source of its common keys. Earlier versions retain their saved members/targets;
joining metadata alone does not retroactively apply an approved estimate to a new contract.
Missing required keys refuse the draft instead of partially binding a new member.

The native loader now validates frozen targets against their actual obligation owners and keys,
so new members are not restricted to the definition's initial member IDs. A frozen ID that names
another member, or whose saved key differs from the original obligation, refuses calculation.
Scope exits and complete population retirement continue using their retained targets.

Approval basis and entity coverage now include the current combination peers of former members
as well as active members. A former member can receive a scope-ending event, and another contract
in its current group can change that recomputation. Those peers must therefore participate in
visibility/approval checks and stale-basis detection.

## Necessary verification

- Public PostgreSQL API: book and compute a second contract, join it after the original population
  has retired, save a version with its own IDs, retain the original version binding, preview,
  independently approve and apply the new member event. Passed.
- 17 focused loader/approval-basis cases passed, including mismatched owner/key refusals and
  former-member group coverage.
- 11 portfolio UI cases passed; scoped type/lint checks passed.

## Remaining work

This resolves new members using existing common target keys. Changing the common target-key set,
other shared estimate kinds, shared breakage application and effective-date contract-combination
reassessment remain unfinished. No deployment or full-readiness claim.
