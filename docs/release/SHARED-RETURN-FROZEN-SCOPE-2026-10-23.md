# Version-scoped shared return membership — October 23, 2026

Native shared RETURN_RATE versions can now carry an explicit frozen member-contract set.
Input revision 12 interprets this set at the version's effective date and original event
position. A newer shared version excluding a member ends that member's previous shared pin;
it does not revive an older shared version. The member's local estimate then applies.
Conversely, a member newly included in the next version retains its local estimate beforehand.
Both price memo selection and revenue recognition use the same scope rule. Required-estimate
findings no longer treat an excluded-member shared pin as available evidence.

The scope participates in the input hash. Historical versions with no scope field keep their
previous hash view and behavior; an explicit scope requires revision 12, sorted unique keys,
and a portfolio RETURN_RATE source. An empty set deliberately ends that source for all members.

Verification: 51 targeted return cases passed with scoped Ruff/mypy. Added calculations show
January revenue 9,200 followed by February 9,600 when membership ends, and January 9,600 followed
by February 9,000 when membership begins. Before/after positions on the transition date select
the appropriate source. Earlier shared/local precedence and historical revision checks remain.

This is native input support, not persisted approval application. The API must still freeze
approved member bindings and supply this field when loading applied versions; submission,
approval/event persistence and recomputation remain open. Current portfolio membership metadata
alone is not a historical application snapshot. No deployment.
