# Original acquisition asset maturity — October 24, 2026

Recomputed, principal, same-entity acquisition cutovers now retain original asset
attribution in evidence revision 43. This closes the report reader's refusal when
one acquired contract has multiple obligations with different current/noncurrent
eligibility and a nonzero contract asset.

The native capture reuses stage 10's POB_DEBIT_POSITIONS and
CUMULATIVE_SSP_DELIVERED allocation evaluators, including their rounding and fallback
weights. It retains the policy, date, allocation basis, integer CA/UR parts and
original billed/revenue source identities. It does not retain exact fractional
quotas or emit posting, schedule or balance targets. Unsupported original
attribution remains unavailable rather than failing an otherwise valid unmeasured
financial calculation.

The report adapter requires authenticated original computation files and checks
policy, date, obligation population, source identities, role totals and every
nonnegative integer part. The attributed CA/UR must equal the original rollforward
closing balances. Current CA is the sum of the original asset shares of eligible
obligations; it is not a newly invented member allocation. Earlier evidence
revisions retain their previous refusal for mixed maturity.

Eight focused native-to-report-adapter cases pass. The new two-obligation case has
100,000 total CA: POB debit allocation gives 20,000 current; cumulative SSP delivered
falls back to revenue weights and gives 60,000 current. Both reconcile. Tests also
verify unchanged posting intents, schedules and ordinary balances versus revision
42, refusal of old evidence, and refusal of a corrupted allocation. Scoped Ruff,
mypy and diff checks pass. These are adapter tests, not a public report-job fixture.

The separate no-persisted-balance-row reporting gap, multi-member group allocation,
and foreign-functional recomputation gaps remain open. No deployment or overall
readiness claim.
