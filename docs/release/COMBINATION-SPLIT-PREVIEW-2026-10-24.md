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
