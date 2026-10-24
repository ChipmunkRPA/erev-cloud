# Combined original-component termination — October 23, 2026

The native TERMINATION path now resolves original component REMOVE lines to the reviewed
combined obligation. It uses this path only when every original member has a removal line,
all deltas are nonpositive and no line changes the transfer dates. Original line members
remain intact as evidence; their signed quantities and consideration enter the existing
termination pool without a new allocation rule. Ordinary amendments retain the reassessment
guard for combined quantity, removal and term changes.

A PARTIAL contract termination may end a whole combined obligation by naming every original
member. Naming only some members, including only the host, requires reassessment. FULL
termination retains its existing unsatisfied-obligation selection. Treatment and SSP maps
resolve original keys with the existing conflict check before being passed to the native pool.

Six focused engine cases pass: full termination, named whole-combination termination, either
partial-member refusal, incomplete removal-line refusal and lease-predominant routing. A
10,000 combination with 9,000 forgone ends at 1,000 cumulative revenue when nonlease-led;
lease-led results retain 1,000 outside scope and zero ASC 606 revenue. All successful traces
re-evaluate exactly. Eight existing combined price-change cases and scoped lint/types pass.

This checkpoint covers the native computation path. Populated public preview, approval,
termination persistence and saved Reporting still need verification. Partial component
removals and quantity/term reassessment remain implementation gaps. No deployment.

## Public workflow and entry — completed

Both FULL contract termination and PARTIAL contract termination naming a complete combination
now pass public create/classify/preview/submit/independent-approval/persistence workflows.
The API derives the ended original keys from the REMOVE lines; the caller does not send an
extra termination.obligation_keys field. Both original lines remain on the applied modification,
and the stored event is CONTRACT_TERMINATED. A 108,000 allocation with 90,000 forgone reports
18,000 cumulative revenue; both saved reports rerun with identical output digests.

The wizard previously restricted all original non-host components to price changes. It now
passes retained combination member groups to the form builder and admits a termination only
when every original member has a REMOVE line and dates remain unchanged. Host-only/member-only
scope stays refused. The original-component labels and error text describe the supported paths.
Existing price-change entry remains supported; the two original amounts are not redistributed.

Two populated workflows, 17 form cases, the original-component wizard case, frontend types/lint
and scoped backend lint pass. The disposable database was stopped. No deployment. This closes
the public-verification gap recorded above; partial member removals and quantity/term
reassessment remain open, along with broader system gaps.

## Original-member quantity bounds and boundary amounts — repaired

A native reproduction accepted removal of 1.5 units from an original member booked for one
unit because the other member's quantity kept the combined total positive. Revision 10 now
checks each original member separately, accumulating its signed removal lines before testing
the bound. Unit-based measures deduct that member's counted deliveries less returns, using the
same control-transfer rules as recognition. Time-based measures retain the original quantity
bound and the existing combined remaining-quantity validation; no member progress is invented.

The same exercise exposed a boundary measurement defect: stage 06 read only the host's unit
ledger, although recognition consumed all original members. After another member's delivery
and return this could create a termination segment with zero quantity and nonzero net delivery.
Revision 10 boundary measurement now uses recognition's original-member tally strictly before
the boundary event, including held-delivery rules. Prospective price changes retain this full
original delivery baseline as well.

Nineteen focused native termination/price-change cases pass. Witnesses refuse the 1.5-of-1
removal; refuse a 0.5 removal after 0.75 of one unit was delivered; allow it after 0.5 was returned;
and successfully compute the resulting termination. A prospective 10,000-to-11,000 price change
after 0.5 of two units were delivered retains 2,500 earned revenue without further delivery.
Earlier revision 9 keeps its previous 2,750 result for retained replay; new platform inputs use
revision 10. Scoped types/lint pass. No deployment. This is a correction to supported complete
termination and price changes, not implementation of partial-member reassessment.
