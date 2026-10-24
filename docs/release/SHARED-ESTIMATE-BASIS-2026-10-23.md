# Shared estimate owner decisions and application groundwork

Owner decisions received October 23:
- Shared estimates take precedence over members' local estimates.
- Shared breakage is a portfolio total allocated by SSP.
- Quantity, term and partial-removal changes trigger reassessment effective from the change,
  retaining earlier combination history and recognized revenue.

Implemented: portfolio BREAKAGE drafts now record an explicit
`parameters.portfolio_total_breakage_quantity` decimal string. The editor exposes this total,
clears per-member rate/expected-redemption fields when entering it, and retains historical
read-only values. Saving requires the total and rejects simultaneous rate/expected_quantity.
Ordinary contract estimates reject the portfolio-only parameter. The field is distinct from
the native expected-redemption quantity; no reinterpretation of old values occurs.

The shared estimate approval-content reader now binds the portfolio row version, every historical
membership interval, affected current combination groups' contract stream heads, and latest
computation identities used for SSP selection. It also retains the selected precedence and
allocation basis. A new member, closed/reopened membership or new computation changes the basis;
missing member visibility refuses instead of shrinking the population. Contract-level estimate
approval content is unchanged. This prepares freshness checking, not an enabled shared approval
or posting workflow.

Verification: the populated portfolio API workflow passes with exact 18-decimal total retention,
missing/mixed basis refusal, original source computation retention and changed approval content
following rejoining. Eight portfolio UI cases pass. Five focused approval basis/content cases
pass; scoped types/lint pass and OpenAPI generation succeeds. A broader existing subject registry
test fails on ENGINE_RELEASE_VALIDATION missing from its tenant-level expectation list; this
change does not modify that registry and is not a full-suite pass.

Remaining: authoritative SSP allocation at the effective date, shared dry-run/routing and
submission/independent decision/application events, local-override handling, member recomputation,
retained Reporting inputs, and effective-date combination reassessment. No posting behavior is
claimed complete by the new editor or approval basis. No deployment.
