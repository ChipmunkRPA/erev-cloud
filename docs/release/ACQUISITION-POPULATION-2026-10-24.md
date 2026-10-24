# Acquired contract balance population — October 24, 2026

Contract balances and contract balance rollforward now refuse an acquired contract
that has no persisted member balance rows, instead of silently leaving it out.
The error identifies the contract, contracting entity, selected version and requested
period. An authenticated original computation must contain an active, nonvoid
business-combination opening at or before that endpoint before the check applies.

The check follows the selected contract version chain, report scope and historical
commit cutoff. Locked endpoints retain their frozen population. Bound runs made
before this check retain their previous behavior; new runs record the
`acquisition_balance_population_v1` source-method marker. Contracts with a persisted
balance row continue through the existing balance and native-cutover readers.

This closes silent omission, not the full no-row reporting gap. Complete balances
for a contract with no ordinary measured period still need original evidence for
all reported measures. A native three-role cutover snapshot alone does not justify
inventing zero balances for other measures. Original closed-cutover cases with an
ordinary earlier period remain supported.

Necessary verification: public report jobs for both balances and rollforward name
the missing contract; the supported closed-cutover case still generates reports in
three currencies and reproduces its retained source run. Scoped Ruff and mypy checks.
No deployment; no overall readiness claim.
