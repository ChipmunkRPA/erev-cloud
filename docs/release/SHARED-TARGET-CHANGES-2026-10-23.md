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
