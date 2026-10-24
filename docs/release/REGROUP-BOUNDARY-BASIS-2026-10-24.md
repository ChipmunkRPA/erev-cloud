# Fixed allocation basis before an original boundary

`erev_engine.boundary_basis.fixed_boundary_basis` combines the original ordered boundary fold
with native segment measurement. It returns the fixed allocation, recognized target and
remaining amount for selected resolved obligations in a named book immediately before a
retained accepted event. Each row retains the original input digest, event, effective date,
contract, obligation, currency and book. Exact fractions and minor-unit amounts are separate;
remaining is the difference from the same native recognized target in each representation.

This replaces no posting and authorizes no regroup. In particular, it is fixed-component
evidence, not a claim to measure royalty, variable components, functional-currency balances or
historical ledger postings. Original combined components must be queried through their resolved
host; the function does not invent member allocations. Empty, duplicate, missing or out-of-scope
targets are refused. Unknown boundary/book handling uses the original fold's validation.

This addresses the dated-measurement prerequisite behind the withdrawn regroup path: latest
obligation-version remaining allocation is not the balance at the regroup date. The old public
after-posting refusal remains. Remaining integration must construct paired approved changes,
preserve source recognized revenue, start the target's future service at the effective boundary,
handle each book and consideration component, and apply both sides atomically. The helper
alone does not make contract splitting complete.

Necessary verification: six focused cases pass, including native unit delivery, exclusion of
later same-day delivery, time service through the day before the change, exact/minor-unit
reconciliation and target validation. Scoped lint/type checks pass. No deployment.


## Revision 35: incoming future service

Native after-posting REGROUPED IN events now build added obligations with service starting
no earlier than the effective transfer date. A later authored start is retained, missing starts
use the effective date, and a term ending before the transfer is refused. Authored event and
modification inputs remain intact; the effective calculation view supplies the future-service
term. Amount and quantity are not inferred or changed by this rule.

This applies before native PROSPECTIVE and SEPARATE_CONTRACT processing. OUT events and
before-posting booking moves retain their existing paths. Evidence revisions through 34 retain
old behavior for replay. Seven focused cases cover both treatments, old revision, earlier/missing/
later starts, expired terms, trace replay and the existing before-posting move. Scoped types/lint
pass. Public after-posting regroup remains refused: dated amounts and quantities, all relevant
components/books, paired approval and atomic transfer still require integration. No deployment.
