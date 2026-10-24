# Shared return target changes — October 23, 2026

Shared return draft versions now accept their own common target-obligation keys. Each current
member must contain every selected key. Blank input keeps a saved draft's scope, otherwise the
latest approved scope or original definition. Explicit keys can also configure a definition that
was originally saved without targets. The immutable definition and earlier versions are unchanged.

A new version freezes original member/obligation IDs for the selected targets and retains the
previous approved targets that are leaving. These outgoing targets remain in application evidence
so they receive the scope-ending transition. Submission and independent approval use the existing
impact/basis guards; application appends member events and recomputes affected groups atomically.
The editor supports target entry and displays outgoing obligations separately from member exits.
Selected target lists are nonempty; complete population retirement retains its existing workflow.

Native evidence revision 13 carries optional original obligation subject scope alongside member
scope. Shared target selection checks both, so an obligation leaves the override from the new
version's effective event position while other obligations on that same contract can remain or
enter. When no shared source applies, its eligible local estimate resumes. The transaction-price
selector now excludes out-of-scope versions from its fallback as well; it cannot resurrect the
retired shared version. Earlier evidence revisions retain their behavior. The new optional field
is omitted from canonical hashes when absent, and old saved application bases remain readable.

## Necessary verification

- Public PostgreSQL API: reject a missing key; change a member's target to another original
  obligation; verify current/outgoing target bindings; preview, independently approve and apply;
  preserve the prior version's target set and the new native active-subject scope. Passed.
- 50 focused native/loader/conversion cases passed, including target entry/exit by effective
  date, duplicate events, local fallback in price and recognition, exact codec roundtrip and
  preserved absent-field canonical identity.
- 11 portfolio UI cases passed, including target authoring, submitted target display and outgoing
  obligations. Scoped types/lint and generated OpenAPI/client types passed.

This completes version-specific nonempty target changes alongside member onboarding/exits and
frozen unit-cost FX. Shared breakage application, other estimate kinds, combined percentage/
milestone progress, contract-combination reassessment and special-source opening attribution
remain unfinished. No deployment or full-system readiness claim.


## Shared breakage draft targets — October 24, 2026

Breakage drafts now accept version-specific common obligation keys through the API and editor.
Saving resolves and retains each current member's original obligation IDs and keys. Omitting keys
on a later edit retains the saved scope; an explicit unknown key is refused without changing it.
Original definitions and earlier versions remain unchanged.

The SSP allocation preview selects the saved version targets instead of reverting to the
original definition. It checks the current population, original contract identity and original
obligation identities against the saved binding. Changed membership or replaced targets require
saving the draft again; ineligible redemption/loyalty targets continue to refuse. Existing drafts
without a binding keep their prior definition-based preview behavior.

This retains target scope only. SSP remains a current-computation preview, not an approved
frozen effective-date allocation. Shared breakage submission/application and the expected-redemption
calculation choice remain open; no breakage posting was enabled by this change.

Necessary checks: 33 focused preview/engine cases, 12 portfolio UI cases, scoped Python lint/types
and frontend TypeScript pass. Public API verification covers selecting targets, rejecting a missing
key, retaining targets when an edit omits keys, and the existing membership/access workflow; passed.

## Book-specific breakage preview — October 24, 2026

The allocation workbench now exposes the existing backend book selection: primary by default,
or ASC606, IFRS15 and LEGACY. Requests and cached results are scoped to the selected book.
Switching books does not carry another book's allocation into the new view; the user explicitly
requests the new preview. Unavailable member/book computations continue to be refused by the
backend. This requires no additional configuration-read permission.

Necessary verification covers selecting IFRS15, the actual query parameter, clearing the primary
book's source rows, and hiding stale IFRS15 sources after a refused refresh. The focused UI case,
frontend TypeScript and scoped ESLint pass. This exposes existing per-book calculation; it does
not enable shared-breakage approval/application or freeze the effective-date allocation.


## October 24: original modification allocation basis

Native evidence revision 23 retains total entitlement quantity, the fixed segment's remaining
SSP and its separate segment quantity on both sides of stage-06 modification boundaries.
Exact rational parameters preserve the source weights without decimal rounding. Earlier
revision bundles retain their existing trace shape and accounting behavior.

A native golden-stream witness covers entitlement changing from 8 to 10 while the prospective
segment contains only 9 remaining units, preserving SSP 1485/2 across the next event. It also
compares the revision-22 accounting state and all original trace fields. The boundary-fold and
prospective-modification checks pass (9 cases). This is a prerequisite for effective-date shared
breakage allocation; it does not freeze or apply a shared estimate. Inception, non-modification
SSP changes, combined-member identity and approved allocation capture still need integration.
The existing preview remains explicitly current-computation based. No deployment.
