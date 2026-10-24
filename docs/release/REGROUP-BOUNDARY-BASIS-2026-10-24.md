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
