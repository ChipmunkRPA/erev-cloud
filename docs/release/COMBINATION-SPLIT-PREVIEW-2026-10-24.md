# Prospective contract-combination split preview

The owner's confirmed rule allocates unrecognized consideration by remaining SSP at the
split effective date and preserves earlier grouping and recognized revenue. The existing
DATA_CORRECTION leave command recomputes from inception and remains a separate operation.

## Implemented

`GET /api/v1/combination-groups/{id}/split-preview` accepts `effective_date`, repeated
`leave_contract_ids` and optional `book_code`. Each selected member is shown with its own
singleton destination; unselected members stay together. This is a read-only allocation
preview, not a split submission, approval, membership change or posting command.

The reader verifies the complete group's original computation files and their hashes,
permissions, current source head and population. Dirty groups require recomputation.
Native boundary measurement uses retained input at the requested date. Time-based income
is measured through the prior day; admitted same-day quantity/boundary events retain their
original ordering. The native helper also supports a precise pre-retained-event query.
No latest-version remaining-balance column substitutes for a dated measurement.

Remaining SSP is resolved using native prospective remaining-service rules and original
SSP sources. Posted unrecognized consideration is first apportioned to original member
contracts, then to their obligations, using native largest remainder and original identity
ordering. Previously recognized posted income, including its rounding, is unchanged.
The result includes original member/obligation amounts, before/after remainder, SSP source
references, input/output hashes, source computation, currency minor unit and boundary basis.

## Scope still to develop

The preview currently covers original fixed principal TIME_ELAPSED/UNITS_DELIVERED
obligations in ASC606/IFRS15. Existing native eligibility guards refuse combined lessor
hosts, acquisitions, estimated consideration, specialist balances and cross-entity/agent
transfers rather than omitting their amounts. It does not preview newly proposed changed
terms or delta consideration. It does not imply approval/application support for a split.

Next: retain the reviewed basis in a split proposal, recheck sources at approval, preserve
historical membership and allocations, and install the planned remaining allocations from
the effective boundary. Broader consideration/progress/FX population support remains open. No DATA_CORRECTION fallback is used.

## Necessary verification

19 native boundary/split cases and one public combination API workflow pass. A two-contract
witness changes dated SSP weights from 2:1 to 1:1 while retaining original posted income of
113,095.89 and 56,547.95; the remaining 310,356.16 is apportioned 155,178.08 to each member.
The API test verifies complete population, original sources, amount conservation, repeatable
results and unchanged event/membership state. Scoped Ruff/mypy and frontend TypeScript pass.
OpenAPI and generated client types are updated. No deployment or system-readiness claim.


## Workbench preview entry

Active/completed non-singleton members now expose Preview combination split in the workbench.
The drawer loads the complete authorized member list, accepts a date/book/member selection,
and calls the read-only preview on demand. It shows preserved income, before/after remainder,
exact SSP, obligation allocations and original references. Changes to the selection clear old
results; fetching or refusal hides them. Partial member access does not enable calculation.
Amounts use integer-to-decimal conversion with the returned currency scale; unsafe numeric
values are not displayed as rounded financial amounts.

Two focused UI cases pass for exact selected query values, result clearing after edits/refusal,
and refusal of partial population. Frontend TypeScript and scoped ESLint pass. This completes
the preview entry, not split submission/approval/application. No deployment.


## Native prospective application boundary — revision 49

The native fold recognizes an explicit COMBINATION_CHANGED / LEAVE input carrying
`prospective_split_destinations`. At revision 49 it rebuilds the remaining-SSP plan strictly
before that event and installs prospective fixed-allocation segments for the complete group.
Earlier input revisions reject this new payload. Ordinary JOIN/LEAVE behavior is unchanged.
The API producer remains revision 48 until the durable workflow is connected.

The installer rechecks original amounts, posted income, remaining quantities and SSP sources.
The group pool stays constant; internal member allocations do not create price concessions,
refund components or changes to original stated prices/billing plans. Each new segment starts
at original posted income and recognizes its assigned remainder over remaining service.
Old segments remain intact. Existing native pool, share, catch-up and allocation-state trace
formulas describe the boundary and reevaluate successfully.

Seven split cases pass, including full native computation, preserved earlier monthly targets,
final revenue conservation, unit-delivery income retained without acceleration, stale/invented
member-allocation refusal and the revision gate. The existing boundary-query cases also pass;
scoped Ruff/mypy pass. No public approval/application claim is made: durable split proposals,
source freshness at approval, effective membership, destination computations and reporting
across membership boundaries still require integration. The calculation envelope continues to
contain the original group and is not itself a persisted membership split. No deployment.


The split group-pool trace uses a distinct event namespace from member pools and does
not place unescaped contract identities into obligation share node ids. Stage-10 group
balance traces now qualify their measure when the group and member entity subjects
coincide, retaining standard member measures and explicit output trace links. Nine focused
cases pass, including full native computation for equal group/contract codes, trace replay,
member balance evidence and group/member conservation. Scoped Ruff and mypy pass.
The durable split workflow and destination reporting remain open. No deployment.

## Successive effective-date splits

Native membership resolution now follows retained split events in effective-date, record
sequence and event-key order. Date queries include that date's retained events; exact-event
queries stop before the requested event. Canonicalized input preserves the existing void
handling. A later split must select all members of one current destination, and cannot
rejoin previously separated groups or reuse another current group's identity.

Preparation measures and allocates only that selected group's remaining consideration.
Application rechecks its effective population and leaves other members' allocation segments
unchanged. Fourteen focused cases pass, including three original members, successive splits
on different dates and on the same date, unchanged earlier exit revenue schedules, total
allocation conservation, trace replay, and rejection of incomplete or cross-group selections.
Scoped Ruff and mypy pass.

This resolves effective population selection inside the retained native calculation envelope.
It does not persist database membership, provide a durable approval command, isolate later
amendment allocation by destination, or partition destination balances/postings/report history.
Those integration steps remain required before a public split can be applied. No deployment.

## Destination balance calculation

`erev_engine.combination_split_balances.calculate` now resolves effective destinations
at a shared contracting-period end, folds original allocations through that date, and
runs native recognition and balance presentation separately for each destination. It
retains original billing/receipt ownership and the original events that produced allocation
segments, including boundaries owned by a member now in another destination. The result
contains group presentation, member balances/sums, current classification and a complete
replayable trace for each destination. It is a transaction-currency query, with no writes
or posting and no functional-currency carry-forward claim.

An original three-member group with billing on an exited member now presents that member's
liability separately from the other destinations' assets. The net of all destinations
reconciles to the original combined net, while gross liabilities are no longer incorrectly
offset by assets in other groups. A September query retains the two-member remainder before
its October split and excludes October billing. Repeated calculations are equal and original
input hashes remain unchanged. Eighteen focused split/allocation/balance cases pass; scoped
Ruff and mypy pass. Specialist/estimated/refund continuations, unavailable period ends and
missing effective split evidence are explicitly refused.

This calculation is not yet wired into durable split approval/application, posting or public
report routes. Effective database membership, destination recomputation and historical
report selection still remain open. No deployment.
