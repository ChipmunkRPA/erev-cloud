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

This applies before native incoming addition processing. OUT events and
before-posting booking moves retain their existing paths. Evidence revisions through 34 retain
old behavior for replay. The original test-treatment scope was corrected below. Cases cover old revision, earlier/missing/
later starts, expired terms, trace replay and the existing before-posting move. Scoped types/lint
pass. Public after-posting regroup remains refused: dated amounts and quantities, all relevant
components/books, paired approval and atomic transfer still require integration. No deployment.


## Proposed-date basis and transfer lines

The fixed-basis query now also accepts a proposed effective date, mutually exclusive with an
original event key. It folds all already retained boundaries through that date and measures
before a prospective new command positioned after the retained records on the date. The
internal query marker is not appended or persisted; output explicitly has no original boundary
event key and labels its position AFTER_RETAINED_EVENTS_ON_DATE. Original-event queries
retain BEFORE_RETAINED_EVENT. Both include the segment's current service dates and original
input digest. These are current-known-input calculations, not historical knowledge snapshots.

The withdrawn posted regroup branch now reads this dated basis from assembled original input
instead of calling the latest-version remainder reader. REMOVE/ADD line construction uses
remaining quantity, fixed remaining minor-unit consideration, and current segment end date;
service starts at the later of the current start and effective transfer date. It requires matching
source/obligation/currency identity and representable positive remaining quantity. The original
booking remains intact. Before-posting draft moves keep their prior behavior.

Fifteen focused cases pass, including same-day accepted quantity changes, date/event selection,
exact original-source reconciliation and paired remaining-unit/current-term line serialization.
Scoped types/lint pass. This does not reopen the public after-posting command: other consideration
components, multi-book transfer amounts and paired approval/application still need integration.
No deployment.


## Revision 36: book-specific transfer pricing

Inspection found an additional native defect: REGROUPED was absent from the consideration
accumulator used by boundary/final transaction-price calculation. A posted incoming transfer
could therefore create an obligation with zero allocation. Revision 36 includes signed
consideration for posted transfers; moves already represented in original bookings are excluded
to avoid double counting. Earlier evidence retains its original calculation behavior.

The native modification handler and transaction-price source reader now consume the same
complete `regroup_book_lines` map for their calculation book. Missing books, changed member
populations, wrong direction/sign and mismatched money currencies refuse. Source references
identify the book-specific basis. The stage-06 memo key includes the selected book's map so
shared policy settings cannot cause one book's transfer to reuse another book's allocation.

The withdrawn API branch constructs signed source/target line maps for every enabled source
framework book and retains original input digest plus exact/minor-unit source basis in both
modification questionnaires. LEGACY transfer evidence is not fabricated. This is preparation
code behind the existing refusal, not a reopened public workflow or approval freshness proof.

Verification: 44 targeted book-loop, transfer and line cases pass. A populated two-book native
case applies 50,000 under ASC606 and 45,000 under IFRS15 and verifies corresponding transaction
price, allocation and exact trace replay. A missing book refuses; an ordinary unmapped posted
transfer now adds its consideration; before-posting moves are not double counted. Scoped
lint/types pass. Remaining work includes other consideration components, source-side transfer
conservation, target book compatibility, approval-time basis validation and atomic paired apply.
No deployment.


## Revision 37: source conservation

Outgoing native transfers now remeasure the resolved source obligations at the original event
position and require each REMOVE amount and quantity to equal the current fixed remainder.
Only PROSPECTIVE treatment is admitted for outgoing obligations so earlier income remains at
the source. Changed amounts or quantities require rebuilding the paired transfer. This check
uses the live original-input state for the calculation book; it does not trust a saved digest as
proof of freshness. Before-posting moves and evidence revisions through 36 retain prior behavior.

Focused native time-service and partial-unit-delivery cases now prove source revenue equals the
pre-transfer recognized amount, source remaining allocation becomes zero, target allocation
equals the removed remainder, and source retained allocation plus target received allocation
reconciles to the original. Exact trace replay passes; changed amounts, changed quantities and
catch-up treatment are refused. Incoming checks also now set the approved modification's actual
chosen treatments for the PROSPECTIVE path.

Evidence correction: earlier incoming fixtures changed only the event's treatments, while
REGROUPED reads chosen_treatments from the approved modification. The earlier claim of
SEPARATE_CONTRACT coverage was therefore unsupported. Those cases represented an unpooled
addition; their names and setup are corrected. This native handler still refuses an explicit
SEPARATE_CONTRACT chosen treatment, which uses a separate booking workflow and is not proven
by these regroup checks. Public paired approval/application, other consideration components,
other progress methods and target book compatibility remain outstanding. No deployment.


## Paired submission and approval consistency

New retained transfer pairs are validated both at submission and, under the existing protecting
locks, immediately before final approval/application. The pair must contain one REMOVE and one
ADD for distinct contracts, the same regroup ID, effective date and currency. Every book must
have the same obligation population and opposite signed amounts/quantities, matching products
and service terms. Primary-book rows must agree with their retained map. Both modifications
must carry identical source evidence; amounts/quantities reconcile to that evidence, including
integral minor units and source allocation less recognized income. Source service dates are now
retained and determine the permitted future service term.

Ordinary modifications bypass these pair checks. Historical pairs without the new book/evidence
fields retain the existing workflow; partially populated new evidence is refused. Existing apply
code appends OUT then IN and recomputes both groups in one unit of work, rolling back on engine
failure. This change establishes pre-write consistency, not proof that the currently disabled
public after-posting workflow is complete or that all source freshness cases are covered.

Twelve focused pair checks pass (valid/reordered/read-only, missing side, changed contract/date/
book/amount/quantity/term, edited primary line, differing source evidence, both sides changed
against the same source). One ordinary populated public modification workflow still passes
submission, approval, application and saved reports. Scoped lint/types pass. No deployment.


## Source freshness under approval locks

Submission and final approval now reconstruct every enabled source book's proposed-date basis
and compare the complete canonical snapshot with the retained evidence, after pair consistency
and while the caller holds source/target group and contract locks. The current target must have
the same enabled books and transaction currency. Changed original inputs, current terms,
amounts, quantities or book population require rebuilding and reviewing both sides.

The reconstruction excludes only the pending pair's own modification headers. It refuses when
an event for either pending modification is already present; accepted source events and every
other input remain in the calculation. The standard InputBundle.sha256 fingerprint excludes
known_at, so a later read timestamp alone does not invalidate the source. Snapshot serialization
is shared with preparation, avoiding divergent field definitions.

26 focused freshness/pair/boundary cases pass, including draft-header/read-time stability,
changed source terms, applied-event refusal, current-source comparison and incompatible target
books. Scoped types/lint pass. These tests use native source calculation with stubbed database
reads for the freshness entry; they do not prove a public post-posting approval round trip.
Public after-posting regroup remains gated pending other consideration/progress paths and
complete workflow validation. No deployment.


## Preview/application event alignment

Retained posted-transfer preview jobs now acquire both contracts/groups and both modification
rows, validate the pair and source freshness, and create the same REGROUPED OUT/IN event used
by application. Ordinary modifications retain their CONTRACT_AMENDED preview. A preview with
no counterpart is refused.

Bundle reconstruction now identifies a retained book-specific transfer draft as an after-posting
boundary even before it has an approval_request_id. Previously a REGROUPED dry run at that
point could be mistaken for a before-posting draft move and rewrite booking from inception.
Original booking events now remain intact for these previews; historical draft-edit moves keep
their existing reconstruction.

A retained transfer targeting a named receiving contract cannot choose the separate-contract
booking branch, which would create a different contract. Preview/submission structure checks
and final pair consistency refuse that unsupported destination change. This is a stated scope
limit, not automatic substitution of a different accounting treatment.

16 focused preview/pair cases pass, plus the populated ordinary K-02 preview job. Scoped types/
lint pass. Public after-posting regroup remains gated; per-row preview alignment does not prove
a full paired approval round trip or simultaneous two-sided preview within a shared group.
Other consideration/progress paths and supported separate-contract transfer treatment remain
outstanding. No deployment.


## Paired preview worker and retained transfer lifecycle

A populated two-contract, two-group retained transfer exposed a worker authorization defect:
the SYSTEM preview job called the interactive preparer permission helper and returned 404.
Locking the pair is now separate from interactive authorization. Preview requests authorize
both contracts before enqueueing; workers lock both groups/contracts/rows and retain pair
consistency and source-freshness checks without pretending to be a human preparer.

The engineering fixture bypasses only the two public regroup entry guards. Both sides are
classified and their questions confirmed before either preview, then previewed, submitted in
one request, independently approved and recomputed. Source O2 retains only the recognized
allocation; source/target transaction allocations sum to the original 384,000; target receives
the remaining consideration; repeating both group computations adds no ledger lines.

Necessary verification: that lifecycle, the unchanged public after-posting refusal, and an
ordinary populated K-02 preview all pass (3 cases); scoped types/lint pass. This is a fixed-price
seat-service witness across separate groups, not a general release of after-posting regroup.
Public guards remain. Same-group simultaneous preview, broader consideration/progress paths,
and separate-contract treatment remain outstanding. No deployment.


## Shared-group two-sided transfer preview

The bundle builder and common dry-run path now accept an ordered contract owner for each
pending event. Each contract advances its own stream version; record sequence follows the
complete application order. Missing owners, count mismatches and owners outside the group are
refused. Existing single-contract callers retain their original behavior.

A retained regroup preview whose two contracts share a group now includes both modification
headers and both REGROUPED events, OUT then IN, matching approval's append order before one
group computation. Each row still displays its own contract's impact and retains its own
boundary provenance. Cross-group transfers continue to preview each affected group separately.

The populated engineering lifecycle covers both separate and shared groups. For each side of
the shared-group preview it inspects the real input/output: both OUT and IN are present, in
order, and total allocation is 384,000. Approval preserves that total, leaves the source's
recognized allocation intact, and repeated computation adds no ledger entries. Public
post-posting entry guards are bypassed only in the fixture and remain in production code;
this does not enable unsupported consideration/progress or separate-contract treatments.

Necessary verification: 3 populated workflow/ordinary-preview cases and 7 focused event/preview
cases pass, along with scoped types/lint. No deployment.


## Retained regroup modification causal reporting

The modification register's causal-analysis calculation now accepts retained after-posting
REGROUPED events, which the ordinary register already included but causal selection rejected.
Each OUT/IN remains an individual MODIFICATION contributor in original effective-date/record
order. Baseline plus event differences reconciles to reproduced period revenue. This remains
counterfactual causal analysis, not original journal attribution or a new posting allocation.

Regroup replay requires evidence revision 37 or later, the referenced modification, retained
book-specific transfer lines and source basis. Legacy/inception draft moves without that basis
refuse explicitly. The general close-variance driver allowlist is unchanged; no unsupported
historical grouping replay is enabled by this change.

Both cross-group and shared-group populated applied transfers pass native transaction/functional
causal reconciliation. The shared-group public report worker passes transaction, functional and
reporting views, identifies both source and target modifications, and retained reruns reproduce
the output hash in each view. This fixture uses USD transaction/functional/reporting currencies;
it verifies all view paths, not a new foreign-FX regroup rule. Existing causal foreign-currency
and offsetting-effect cases also pass. Ten causal cases passed before expanding the missing/
legacy evidence guard to three passing cases; scoped lint/types pass. Public regroup entry
remains gated for outstanding accounting scenarios. No deployment.


## Causal report event and transfer-pair context — October 24, 2026

New modification causal reports retain and expose the original event type, regroup pair identity
and OUT/IN direction. Context comes from the authorized, hash-verified computation input, not
current event rows. Missing selected events and invalid/missing regroup direction/identity refuse.
The report dataset supplies these columns to the viewer/export paths; no new posting amounts
or counterpart-contract reads are introduced. A retained feature flag keeps earlier report
bindings' column shape unchanged. Baseline/final and unselected event rows remain unlabelled.

Necessary verification: the populated shared-group transfer and full termination report workflows
pass in transaction/functional/reporting views and all saved reruns preserve output hashes.
Transfer rows retain the same pair identity and correct owner/direction; termination rows have
no fabricated pair. A focused retained-dataset case preserves amounts/control totals and old
output shape. Scoped lint/types pass. No deployment.


## Retained regroup close-variance replay — October 24, 2026

Close-variance replay now recognizes retained after-posting REGROUPED events as modification
drivers, preserving late-event precedence. It shares causal reporting admission checks: evidence
revision 37+, contract-owned modification evidence, book transfer lines, source basis, pair identity
and OUT/IN direction. Inception draft moves without retained evidence refuse before computation.

Two populated transfer workflows (cross-group and shared-group) reconcile every close-replay
measure and preserve separate event effects. They capture actual pre-transfer inputs and normalize
posted amounts/previous stream heads to the existing close-replay basis, with explicitly constructed
knowledge cutoffs. This is not a new public close/lock roundtrip. Twelve causal regression cases and
seven negative replay guards pass; scoped lint/types pass. Public after-posting regroup remains
gated for outstanding accounting scenarios. No deployment.


## Fixed transfer preparation eligibility — October 24, 2026

The retained after-posting preparation branch now explicitly requests fixed-transfer eligibility
when measuring source amounts. It refuses blocking native findings, inputs carrying estimate
versions, selected combined/acquired/material-right/variable-consideration obligations, agents
and cross-entity performance, unsupported progress methods, non-fixed allocation segments,
terminated obligations and exhausted/negative remaining service. These scenarios need their
complete transfer treatment; the fixed component alone must not create draft financial commands.
Value/engine failures are translated into a field validation response before either pair row is
inserted. Analytical boundary queries keep their existing broader fixed-component behavior.

Fifteen native boundary cases pass, including actual combined-host refusal, preservation of plain
fixed service amounts and targeted native-state eligibility cases. Both populated retained-pair
workflows still pass (cross-group and shared-group, with public entry guards bypassed only in
the fixture), including preview, approval, application, replay and causal report checks. Scoped
lint/types pass. These are preparation safeguards, not complete transfer coverage: public
after-posting entry remains gated, and foreign-currency, broader consideration/progress and
new-target transfer implementation remain open. No deployment.
