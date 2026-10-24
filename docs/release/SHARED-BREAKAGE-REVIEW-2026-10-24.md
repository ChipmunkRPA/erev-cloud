# Review saved shared breakage allocations — October 24, 2026

The shared breakage viewer now opens each saved book allocation with its original
member quantities, SSP, entitlements, dated FX sources and computation identities.
It compares the selected book's current preview with that saved basis, identifying
added targets, removed targets, changed quantities and changed sources. A source
change remains visible even when all allocated quantities are unchanged. Object
key and target ordering do not create differences.

The comparison is explicitly against the displayed preview, not a claim of current
approval or application. It hides when refreshing or when a refresh fails; the
saved basis remains accessible. Saving still uses the existing server-side locked
source validation and ETag. No monetary calculation or approval state changes.
Unrecognized saved shapes are shown as unavailable rather than as a match.

A focused browser-component workflow verifies saving, reloading the matching book,
source-only changes, added/removed targets, and hiding the obsolete comparison on
a refused refresh. TypeScript and scoped ESLint pass. No deployment.

Shared breakage submission/approval/application remains open: the current approval
workflow applies and recomputes atomically, so it cannot be enabled before the
owner resolves the expected-redemption denominator. This change provides allocation
review, not a partial approval state or financial impact preview.
