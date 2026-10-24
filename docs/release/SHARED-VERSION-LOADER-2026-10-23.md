# Shared return versions in native input loading — October 23, 2026

The computation loader no longer silently drops a portfolio-scoped version named by an
ESTIMATE_CHANGED event. A representable shared RETURN_RATE version carries a stable
PORTFOLIO:<portfolio ID>/<encoded element code> key, original version number, content hash,
rate and explicit obligation targets. The event reference uses the same version key.
Common target keys are deduplicated across member contracts for canonical bundle ordering.

Loading requires a retained nonempty member population, matching explicit obligation targets
for each member, a rate without a duplicated total quantity, and compatible currencies for
per-unit return costs. A target belonging to a nonmember within the computation refuses.
Shared BREAKAGE still needs frozen member allocations; it is refused rather than copied as
a per-member amount. These guards prevent unsupported inputs from silently having no effect.

This is calculation-input integration, not a complete user workflow. Portfolio definitions
currently have no public member-target editor; approval submission/application, frozen
per-member bindings and effective-date membership transitions remain open. Removing a member
cannot yet be treated as a completed estimate handoff. Historical member binding must be
implemented before enabling approval application. Existing stored bundles retain their inputs.

Verification: 25 focused shared-loader and local-adapter checks pass, including stable escaped
keys, event references, precise rates, missing/asymmetric targets, empty populations, total
quantities, unsupported breakage and currency mismatch. Scoped Ruff and mypy pass. The public
portfolio workflow and actual bundle build remain covered; no public approved-shared end-to-end
workflow is claimed. No deployment.
