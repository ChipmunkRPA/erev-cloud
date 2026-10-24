# Shared return impact preview — October 23, 2026

Saved open RETURN_RATE versions now offer Calculate shared impact in the portfolio editor.
The read-only endpoint loads the explicitly targeted shared version, simulates its approved
pin, and runs the native engine once per affected combination group. It shows primary-book
member balances before/after, revenue before/after/change by period, and absolute group
catch-up. Groups retain their transaction currency; no cross-currency grand total is shown.
Each result identifies its baseline computation/version and the actual simulated input hash.
Refresh errors hide preceding results. The preview uses saved values, not unsaved form edits.

The read transaction uses REPEATABLE READ so membership, authorization, baseline versions and
input sources use one database snapshot. Read permission must cover all affected group entities
and historical portfolio members. Empty populations, incomplete targets, stale primary-book
computations and unsupported breakage/member currency conversions refuse. No approval, event,
computation, journal or revenue result is persisted. Fresh preview event timestamps may change
the input fingerprint on another request even when the financial outcome is unchanged.

Public API verification creates a targeted shared draft, calls the real native calculation,
checks source identities and period rows, repeats the calculation to compare financial results,
and confirms the draft remains unapplied and the original computation remains current. Hidden
entity access refuses. Ten portfolio UI cases pass, including on-demand preview, period changes,
source display and clearing a failed refresh. OpenAPI/client types, TypeScript/ESLint and scoped
backend Ruff/mypy pass. This is not a public approval/posting workflow verification.

Shared approval/application and frozen membership transitions remain open. Breakage's expected
redemption input source remains an unanswered owner choice; this feature makes no assumption
about unclaimed-property treatment. No deployment.
